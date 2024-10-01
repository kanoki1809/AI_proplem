# -*- coding: utf-8 -*-
"""problem3.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1K0wr_AZ3r63bLi-xJUiQM82-3zrXFmdJ

**問題3**:    IWSLT15(en-vi)のデータセットに対してより高い精度(BLEU)を実現するプログラム(PyTorch)を作成せよ。ただし、プログラムは第13回の講義資料のプログラム(もしくはLab  Work  (6)で作成したプログラム)を改良して作成せよ。その「プログラム」と「実行結果」およびそれらに関する「解説」をwordファイルにまとめて提出せよ。また、プログラムのソースコード(.py)も提出せよ。例:双方向LSTM, アテンション,サブワード, Transformer, ハイパーパラメータ調整など期待される精度(BLEU): 10%以上

**Problem 3**: Write a program (PyTorch) that achieves higher accuracy (BLEU) on the IWSLT15(en-vi) data set. The program should be an improved version of the program in the 13th lecture (or the program you wrote in Lab Work (6))  . Submit the “Program”, its “Execution Results”, and an “Explanation” of them in a word file. Also submit the source code (.py) of the program.
"""

# Prepare Data
import numpy as np
import matplotlib.pyplot as plt
import torch
import torch.nn.functional as F

# Prepare Model
from torch import Tensor
from torch import nn
from torch.nn import Transformer
import math
import torchtext.data as data

import requests
import tarfile
from tqdm import tqdm

def fix_str_data(string):
  string = string.replace(" &apos;", "'")
  string = string.replace("&quot;", '"')
  string = string.replace("&#91;", '[')
  string = string.replace("&#93;", ']')
  string = string.replace("--", '-')
  return string

def iwslt15(train_test):
  url = "https://github.com/stefan-it/nmt-en-vi/raw/master/data/"
  r = requests.get(url + train_test + "-en-vi.tgz")
  filename = train_test + "-en-vi.gz"
  with open(filename, 'wb') as f:
    f.write(r.content)
    tarfile.open(filename, 'r:gz').extractall("iwslt15")
iwslt15("train")
iwslt15("test-2013")

f = open("iwslt15/train.en")
train_en = [line.split() for line in f]
f.close()
f = open("iwslt15/train.vi")
train_vi = [line.split() for line in f]
f.close()
f = open("iwslt15/tst2013.en")
test_en = [line.split() for line in f]
f.close()
f = open("iwslt15/tst2013.vi")
test_vi = [line.split() for line in f]
f.close()

print('train EN:', len(train_en))
print('train VI:', len(train_vi))
print('test EN:', len(test_en))
print('test VI:', len(test_vi))

print(test_en[428])
print(test_vi[430])

def make_vocab(train_data, min_freq):
  vocab = {}
  for tokenlist in train_data:
    for token in tokenlist:
      if token not in vocab:
        vocab[token] = 0
      vocab[token] += 1
  vocablist = [('<unk>', 0), ('<pad>', 0), ('<cls>', 0), ('<eos>', 0)]
  vocabidx = {}
  for token, freq in vocab.items():
    if freq >= min_freq:
      idx = len(vocablist)
      vocablist.append((token, freq))
      vocabidx[token]=idx
  vocabidx['<unk>']=0
  vocabidx['<pad>']=1
  vocabidx['<cls>']=2
  vocabidx['<eos>']=3
  return vocablist, vocabidx

vocablist_en, vocabidx_en = make_vocab(train_en, 3)
vocablist_vi, vocabidx_vi = make_vocab(train_vi, 3)

print("vocab size EN:", len(vocablist_en))
print("vocab size VI:", len(vocablist_vi))

MODELNAME = 'attention.model'
EPOCH= 10
BATCHSIZE = 32
LR = 0.0001
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
print(DEVICE)

def preprocess(data, vocabidx):
  rr = []
  for tokenlist in data:
    tkl = ['<cls>']
    for token in tokenlist:
      tkl.append(token if token in vocabidx  else '<unk>')
    tkl.append('<eos>')
    rr.append(tkl)
  return rr

train_en_prep = preprocess(train_en, vocabidx_en)
train_vi_prep = preprocess(train_vi, vocabidx_vi)
test_en_prep = preprocess(test_en, vocabidx_en)

for i in range(5):
  print(train_en_prep[i])
  print(train_vi_prep[i])
  print(test_en_prep[i])

train_data = list(zip(train_en_prep, train_vi_prep))
train_data.sort(key = lambda x: (len(x[0]), len(x[1])))
test_data = list(zip(test_en_prep, test_en, test_vi))

for i in range(5):
  print(train_data[i])

for i in range(5):
  print(test_data[i])

def make_batch(data, batchsize):
  bb = []
  ben = []
  bvi = []
  for en, vi in data:
    ben.append(en)
    bvi.append(vi)
    if len(ben) >= batchsize:
      bb.append((ben, bvi))
      ben = []
      bvi = []
  if len(ben) > 0:
    bb.append((ben, bvi))
  return bb

train_data = make_batch(train_data, BATCHSIZE)

for i in range(5):
  print(train_data[i])

def padding_batch(b):
  maxlen = max([len(x) for x in b])
  for tkl in b:
    for i in range(maxlen - len(tkl)):
      tkl.append('<pad>')

def padding(bb):
  for ben, bvi in bb:
    padding_batch(ben)
    padding_batch(bvi)

padding(train_data)

for i in range(3):
  print(train_data[i])

train_data = [([[vocabidx_en[token] for token in tokenlist] for tokenlist in ben],
               [[vocabidx_vi [token] for token in tokenlist] for tokenlist in bvi]) for ben, bvi in train_data]
test_data = [([vocabidx_en[token] for token in enprep], en, vi) for enprep, en, vi in test_data]

for i in range (3):
  print(train_data[i])
for i in range(3):
  print(test_data[i])

class PositionalEncoding(nn.Module):
    def __init__(self, emb_size, dropout, maxlen = 5000):
        super(PositionalEncoding, self).__init__()
        den = torch.exp(- torch.arange(0, emb_size, 2)* math.log(10000) / emb_size)
        pos = torch.arange(0, maxlen).reshape(maxlen, 1)
        pos_embedding = torch.zeros((maxlen, emb_size))
        pos_embedding[:, 0::2] = torch.sin(pos * den)
        pos_embedding[:, 1::2] = torch.cos(pos * den)
        pos_embedding = pos_embedding.unsqueeze(-2)

        self.dropout = nn.Dropout(dropout)
        self.register_buffer('pos_embedding', pos_embedding)

    def forward(self, token_embedding):
        return self.dropout(token_embedding + self.pos_embedding[:token_embedding.size(0), :])

class TokenEmbedding(nn.Module):
    def __init__(self, vocab_size, emb_size):
        super(TokenEmbedding, self).__init__()
        self.embedding = nn.Embedding(vocab_size, emb_size)
        self.emb_size = emb_size

    def forward(self, tokens):
        return self.embedding(tokens.long()) * math.sqrt(self.emb_size)

class Seq2Seq(nn.Module):
    def __init__(self,
                 num_encoder_layers,
                 num_decoder_layers,
                 emb_size,
                 nhead,
                 en_vocab_size,
                 vi_vocab_size,
                 dim_feedforward = 512,
                 dropout: float = 0.1):
        super(Seq2Seq, self).__init__()
        self.transformer = nn.Transformer(d_model=emb_size,
                                       nhead=nhead,
                                       num_encoder_layers=num_encoder_layers,
                                       num_decoder_layers=num_decoder_layers,
                                       dim_feedforward=dim_feedforward,
                                       dropout=dropout)
        self.generator = nn.Linear(emb_size, vi_vocab_size)
        self.en_tok_emb = TokenEmbedding(en_vocab_size, emb_size)
        self.vi_tok_emb = TokenEmbedding(vi_vocab_size, emb_size)
        self.positional_encoding = PositionalEncoding(emb_size, dropout=dropout)

    def forward(self, en, vi, en_mask, vi_mask, en_padding_mask, vi_padding_mask, memory_key_padding_mask):
        en_emb = self.positional_encoding(self.en_tok_emb(en))
        vi_emb = self.positional_encoding(self.vi_tok_emb(vi))
        outs = self.transformer(en_emb, vi_emb, en_mask, vi_mask, None, en_padding_mask, vi_padding_mask, memory_key_padding_mask)
        return self.generator(outs)

    def encode(self, en, en_mask):
        return self.transformer.encoder(self.positional_encoding(self.en_tok_emb(en)), en_mask)

    def decode(self, vi, memory, vi_mask):
        return self.transformer.decoder(self.positional_encoding(self.vi_tok_emb(vi)), memory, vi_mask)

def generate_square_subsequent_mask(sz):
    mask = (torch.triu(torch.ones((sz, sz), device=DEVICE)) == 1).transpose(0, 1)
    mask = mask.float().masked_fill(mask == 0, float('-inf')).masked_fill(mask == 1, float(0.0))
    return mask


def create_mask(en, vi):
    en_seq_len = en.shape[0]
    vi_seq_len = vi.shape[0]
    vi_mask = generate_square_subsequent_mask(vi_seq_len)
    en_mask = torch.zeros((en_seq_len, en_seq_len),device=DEVICE).type(torch.bool)
    en_padding_mask = (en == vocabidx_en['<pad>']).transpose(0, 1)
    vi_padding_mask = (vi == vocabidx_en['<pad>']).transpose(0, 1)
    return en_mask, vi_mask, en_padding_mask, vi_padding_mask

def greedy_decode(model, en, en_mask, max_len, start_symbol):
    en = en.to(DEVICE)
    en_mask = en_mask.to(DEVICE)

    memory = model.encode(en, en_mask)
    ys = torch.ones(1, 1).fill_(start_symbol).type(torch.long).to(DEVICE)
    for i in range(max_len-1):
        memory = memory.to(DEVICE)
        vi_mask = (generate_square_subsequent_mask(ys.size(0))
                    .type(torch.bool)).to(DEVICE)
        out = model.decode(ys, memory, vi_mask)
        out = out.transpose(0, 1)
        prob = model.generator(out[:, -1])
        _, next_word = torch.max(prob, dim=1)
        next_word = next_word.item()

        ys = torch.cat([ys, torch.ones(1, 1).type_as(en.data).fill_(next_word)], dim=0)
        if next_word == vocabidx_en['<eos>']:
            break
    return ys

def translate(model, en_sentence):
    model.eval()
    en = torch.tensor([en_sentence], dtype=torch.int64).transpose(0,1).to(DEVICE)
    num_tokens = en.shape[0]
    en_mask = (torch.zeros(num_tokens, num_tokens)).type(torch.bool)
    vi_tokens = greedy_decode(model,  en, en_mask, max_len=num_tokens + 5, start_symbol=vocabidx_en['<cls>']).flatten()
    pred_sentence = []
    for i in vi_tokens:
      if(vocablist_vi[i.item()][0] != '<eos>' and vocablist_vi[i.item()][0] != '<cls>'):
          pred_sentence.append(vocablist_vi[i.item()][0])
    return pred_sentence

def train():
    model = transformer.to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr = LR)
    for epoch in range(EPOCH):
        losses = 0
        step = 0
        for ben, bvi in train_data:
            ben = torch.tensor(ben, dtype = torch.int64).transpose(0,1).to(DEVICE)
            bvi = torch.tensor(bvi, dtype = torch.int64).transpose(0,1).to(DEVICE)

            vi_input = bvi[:-1, :]
            en_mask, vi_mask, en_padding_mask, vi_padding_mask = create_mask(ben, vi_input)
            logits = model(ben, vi_input, en_mask, vi_mask,en_padding_mask, vi_padding_mask, en_padding_mask)
            optimizer.zero_grad()

            vi_out = bvi[1:, :]
            loss = loss_fn(logits.reshape(-1, logits.shape[-1]), vi_out.reshape(-1))
            loss.backward()
            optimizer.step()

            losses = losses + loss.item()

            if step % 500 == 0:
                print("step:", step, "batchloss:", loss.item())
            step += 1
        print("epoch", epoch,  "loss:", losses, '\n')
    torch.save(model.state_dict(), MODELNAME)

def test():
    model.eval()
    model.load_state_dict(torch.load('attention.model'))
    ref = []
    pred = []

    for enprep, en, vi in test_data:

        p = translate(model, enprep)
        print("INPUT: ", en)
        print("REF: ", vi)
        print("MT:", p, '\n')

        ref.append([vi])
        pred.append(p)
    bleu = torchtext.data.metrics.bleu_score(pred, ref)
    print("Total:", len(test_data))
    print("BLEU:", bleu)

EN_VOCAB_SIZE = len(vocablist_en)
VI_VOCAB_SIZE = len(vocablist_vi)
EMB_SIZE = 512
NHEAD = 8
FFN_HID_DIM = 512
NUM_ENCODER_LAYERS = 2
NUM_DECODER_LAYERS = 2

transformer = Seq2Seq(NUM_ENCODER_LAYERS, NUM_DECODER_LAYERS, EMB_SIZE, NHEAD, EN_VOCAB_SIZE, VI_VOCAB_SIZE, FFN_HID_DIM)
# transformer = Seq2Seq(2, 2, 512, 2, EN_VOCAB_SIZE, VI_VOCAB_SIZE, 512)

for p in transformer.parameters():
    if p.dim() > 1:
        nn.init.xavier_uniform_(p)


model = transformer.to(DEVICE)
loss_fn = torch.nn.CrossEntropyLoss(ignore_index=vocabidx_en['<unk>'])
optimizer = torch.optim.Adam(transformer.parameters())

EPOCH = 10
train()
test()