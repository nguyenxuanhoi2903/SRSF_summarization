#!/usr/bin/env python3

import json
import models
import utils
import argparse, random, logging, numpy, os
import torch
import torch.nn as nn
import numpy as np
from torch.autograd import Variable
from torch.utils.data import DataLoader
from torch.nn.utils import clip_grad_norm
from time import time
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format='%(asctime)s [INFO] %(message)s')
parser = argparse.ArgumentParser(description='extractive summary')
# model
parser.add_argument('-save_dir', type=str, default='checkpoints/')
parser.add_argument('-embed_dim', type=int, default=100)
parser.add_argument('-embed_num', type=int, default=100)
parser.add_argument('-pos_dim', type=int, default=50)
parser.add_argument('-pos_num', type=int, default=100)
parser.add_argument('-seg_num', type=int, default=10)
parser.add_argument('-kernel_num', type=int, default=100)
parser.add_argument('-kernel_sizes', type=str, default='3,4,5')
parser.add_argument('-model', type=str, default='RNN_RNN')
parser.add_argument('-hidden_size', type=int, default=200)
# train

parser.add_argument('-lr', type=float, default=1e-3)
parser.add_argument('-batch_size', type=int, default=32)
parser.add_argument('-epochs', type=int, default=4)
parser.add_argument('-seed', type=int, default=1)
parser.add_argument('-train_dir', type=str, default='data/train_dailymail.json')
parser.add_argument('-val_dir', type=str, default='data/val_dailymail.json')
parser.add_argument('-embedding', type=str, default='data/embedding.npz')
parser.add_argument('-word2id', type=str, default='data/word2id.json')
parser.add_argument('-report_every', type=int, default=1500)
parser.add_argument('-seq_trunc', type=int, default=50)
parser.add_argument('-max_norm', type=float, default=1.0)
# test
parser.add_argument('-load_dir', type=str, default='checkpoints/RNN_RNN_seed_1.pt')
parser.add_argument('-test_dir', type=str, default='data/test_cnn.json')
parser.add_argument('-ref', type=str, default='outputs/ref')
parser.add_argument('-origin', type=str, default='outputs/origin')
parser.add_argument('-hyp', type=str, default='outputs/hyp')
parser.add_argument('-pre', type=str, default='outputs/predict')
parser.add_argument('-filename', type=str, default='x.txt')  # TextFile to be summarized
parser.add_argument('-topk', type=int, default=4)
# device
parser.add_argument('-device', type=int)
# option
parser.add_argument('-test', action='store_true')
parser.add_argument('-train', action='store_true')
parser.add_argument('-debug', action='store_true')
parser.add_argument('-predict', action='store_true')
parser.add_argument('-predict_all', action='store_true')  # predict all
args = parser.parse_args()
use_gpu = args.device is not None

if torch.cuda.is_available() and not use_gpu:
    print("WARNING: You have a CUDA device, should run with -device 0")

# set cuda device and seed
if use_gpu:
    torch.cuda.set_device(args.device)
torch.cuda.manual_seed(args.seed)
torch.manual_seed(args.seed)
random.seed(args.seed)
numpy.random.seed(args.seed)


def eval(net, vocab, data_iter, criterion):
    net.eval()
    total_loss = 0
    batch_num = 0
    for batch in data_iter:
        features, targets, _, doc_lens = vocab.make_features(batch)
        features, targets = Variable(features), Variable(targets.float())
        if use_gpu:
            features = features.cuda()
            targets = targets.cuda()
        probs = net(features, doc_lens)
        loss = criterion(probs, targets)
        total_loss += loss.data.item()
        batch_num += 1
    loss = total_loss / batch_num
    net.train()
    return loss


def train():
    logging.info('Loading vocab,train and val dataset.Wait a second,please')

    embed = torch.Tensor(np.load(args.embedding)['embedding'])
    with open(args.word2id) as f:
        word2id = json.load(f)
    vocab = utils.Vocab(embed, word2id)

    with open(args.train_dir) as f:
        examples = [json.loads(line) for line in f]
    train_dataset = utils.Dataset(examples)

    with open(args.val_dir) as f:
        examples = [json.loads(line) for line in f]
    val_dataset = utils.Dataset(examples)

    # update args
    args.embed_num = embed.size(0)
    args.embed_dim = embed.size(1)
    args.kernel_sizes = [int(ks) for ks in args.kernel_sizes.split(',')]
    # build model
    net = getattr(models, args.model)(args, embed)
    if use_gpu:
        net.cuda()
    # load dataset
    train_iter = DataLoader(dataset=train_dataset,
                            batch_size=args.batch_size,
                            shuffle=True)
    val_iter = DataLoader(dataset=val_dataset,
                          batch_size=args.batch_size,
                          shuffle=False)
    # loss function
    criterion = nn.BCELoss()
    # model info
    params = sum(p.numel() for p in list(net.parameters())) / 1e6
    print('#Params: %.1fM' % (params))
    min_loss = float('inf')
    optimizer = torch.optim.Adam(net.parameters(), lr=args.lr)
    net.train()
    t1 = time()
    print(t1)
    for epoch in range(1,args.epochs+1):
        print("Epoch====================")
        print(str(epoch))
        for i, batch in enumerate(train_iter):
            features, targets, _, doc_lens = vocab.make_features(batch)
            features, targets = Variable(features), Variable(targets.float())
            if use_gpu:
                features = features.cuda()
                targets = targets.cuda()
            probs = net(features, doc_lens)
            loss = criterion(probs, targets)
            optimizer.zero_grad()
            loss.backward()
            clip_grad_norm(net.parameters(), args.max_norm)
            optimizer.step()
            if args.debug:
                print('Batch ID:%d Loss:%f' % (i, loss.data[0]))
                continue
            if (i % 1000 == 0):
                print(str(i))
            if i % args.report_every == 0:
                print(str(i))
                cur_loss = eval(net, vocab, val_iter, criterion)
                if cur_loss < min_loss:
                    min_loss = cur_loss
                    net.save()
                logging.info('Epoch: %2d Min_Val_Loss: %f Cur_Val_Loss: %f' % (epoch, min_loss, cur_loss))
    t2 = time()
    logging.info('Total Cost:%f h' % ((t2 - t1) / 3600))


def test():
    embed = torch.Tensor(np.load(args.embedding)['embedding'])
    with open(args.word2id) as f:
        word2id = json.load(f)
    vocab = utils.Vocab(embed, word2id)

    with open(args.test_dir) as f:
        examples = [json.loads(line) for line in f]
    test_dataset = utils.Dataset(examples)

    test_iter = DataLoader(dataset=test_dataset,
                           batch_size=args.batch_size,
                           shuffle=False)

    if use_gpu:
        checkpoint = torch.load(args.load_dir, map_location='cuda:0')
    else:
        checkpoint = torch.load(args.load_dir, map_location='cpu')

    # checkpoint['args']['device'] saves the device used as train time
    # if at test time, we are using a CPU, we must override device to None
    if not use_gpu:
        checkpoint['args'].device = None
    net = getattr(models, checkpoint['args'].model)(checkpoint['args'])
    net.load_state_dict(checkpoint['model'])
    if use_gpu:
        net.cuda()
    net.eval()

    doc_num = len(test_dataset)
    time_cost = 0
    file_id = 1
    for batch in tqdm(test_iter):
        features, _, summaries, doc_lens = vocab.make_features(batch)
        t1 = time()
        if use_gpu:
            probs = net(Variable(features).cuda(), doc_lens)
        else:
            probs = net(Variable(features), doc_lens)
        t2 = time()
        time_cost += t2 - t1
        start = 0
        for doc_id, doc_len in enumerate(doc_lens):
            stop = start + doc_len
            prob = probs[start:stop]
            topk = min(args.topk, doc_len)
            topk_indices = prob.topk(topk)[1].cpu().data.numpy()
            topk_indices.sort()
            doc = batch['doc'][doc_id].split('\n')[:doc_len]
            hyp = [doc[index] for index in topk_indices]
            ref = summaries[doc_id]
            with open(os.path.join(args.ref, str(file_id) + '.txt'), 'w') as f:
                f.write(ref)
            with open(os.path.join(args.hyp, str(file_id) + '.txt'), 'w') as f:
                f.write('\n'.join(hyp))
            start = stop
            file_id = file_id + 1
    print('Speed: %.2f docs / s' % (doc_num / time_cost))


def initDataset():
    embed = torch.Tensor(np.load(args.embedding)['embedding'])
    with open(args.word2id) as f:
        word2id = json.load(f)
    vocab = utils.Vocab(embed, word2id)

    with open(args.test_dir) as f:
        examples = [json.loads(line) for line in f]

    test_dataset = utils.Dataset(examples)

    test_iter = DataLoader(dataset=test_dataset,
                           batch_size=args.batch_size,
                           shuffle=False)
    file_id = 1
    for batch in tqdm(test_iter):
        targets, summaries, doc_lens = vocab.make_summaries(batch)
        for doc_id, doc_len in enumerate(doc_lens):
            doc = batch['doc'][doc_id].split('\n')[:doc_len]
            print(doc)
            labels = targets[doc_id]
            print(labels)
            with open(os.path.join(args.ref, str(file_id) + '.txt'), 'w') as f:
                f.write(ref)
            file_id = file_id + 1


def predict2():
    embed = torch.Tensor(np.load(args.embedding)['embedding'])
    with open(args.word2id) as f:
        word2id = json.load(f)
    vocab = utils.Vocab(embed, word2id)
    with open(args.test_dir) as f:
        examples = [json.loads(line) for line in f]
    pred_dataset = utils.Dataset(examples)

    pred_iter = DataLoader(dataset=pred_dataset,
                           batch_size=args.batch_size,
                           shuffle=False)
    if use_gpu:
        checkpoint = torch.load(args.load_dir, map_location='cuda:0')
    else:
        checkpoint = torch.load(args.load_dir, map_location='cpu')

    # checkpoint['args']['device'] saves the device used as train time
    # if at test time, we are using a CPU, we must override device to None
    if not use_gpu:
        checkpoint['args'].device = None
    net = getattr(models, checkpoint['args'].model)(checkpoint['args'])
    net.load_state_dict(checkpoint['model'])
    if use_gpu:
        net.cuda()
    net.eval()

    doc_num = len(pred_dataset)
    time_cost = 0
    file_id = 1
    for batch in tqdm(pred_iter):
        features, doc_lens = vocab.make_predict_features(batch)
        t1 = time()
        if use_gpu:
            probs = net(Variable(features).cuda(), doc_lens)
        else:
            probs = net(Variable(features), doc_lens)
        t2 = time()
        time_cost += t2 - t1
        start = 0
        print(probs)
        for doc_id, doc_len in enumerate(doc_lens):
            stop = start + doc_len
            prob = probs[start:stop]
            topk = min(args.topk, doc_len)
            topk_indices = prob.topk(topk)[1].cpu().data.numpy()
            topk_indices.sort()
            doc = batch[doc_id].split('. ')[:doc_len]
            hyp = [doc[index] for index in topk_indices]
            with open(os.path.join(args.pre, str(file_id) + '.txt'), 'w') as f:
                f.write('. '.join(hyp))
            start = stop
            file_id = file_id + 1
    print('Speed: %.2f docs / s' % (doc_num / time_cost))


def predict(examples):
    embed = torch.Tensor(np.load(args.embedding)['embedding'])
    with open(args.word2id) as f:
        word2id = json.load(f)
    vocab = utils.Vocab(embed, word2id)
    pred_dataset = utils.Dataset(examples)

    pred_iter = DataLoader(dataset=pred_dataset,
                           batch_size=args.batch_size,
                           shuffle=False)
    if use_gpu:
        checkpoint = torch.load(args.load_dir, map_location='cpu')
    else:
        checkpoint = torch.load(args.load_dir, map_location='cpu')

    # checkpoint['args']['device'] saves the device used as train time
    # if at test time, we are using a CPU, we must override device to None
    if not use_gpu:
        checkpoint['args'].device = None
    net = getattr(models, checkpoint['args'].model)(checkpoint['args'])
    net.load_state_dict(checkpoint['model'])
    if use_gpu:
        net.cuda()
    net.eval()

    doc_num = len(pred_dataset)
    time_cost = 0
    file_id = 1
    for batch in tqdm(pred_iter):
        features, doc_lens = vocab.make_predict_features(batch)
        t1 = time()
        if use_gpu:
            probs = net(Variable(features).cuda(), doc_lens)
        else:
            probs = net(Variable(features), doc_lens)
        t2 = time()
        time_cost += t2 - t1
        start = 0
        for doc_id, doc_len in enumerate(doc_lens):
            stop = start + doc_len
            prob = probs[start:stop]
            topk = min(args.topk, doc_len)
            topk_indices = prob.topk(topk)[1].cpu().data.numpy()
            topk_indices.sort()
            doc = batch[doc_id].split('. ')[:doc_len]
            hyp = [doc[index] for index in topk_indices]
            with open(os.path.join(args.pre, str(file_id) + '.txt'), 'w') as f:
                f.write('. '.join(hyp))
            start = stop
            file_id = file_id + 1
    print('Speed: %.2f docs / s' % (doc_num / time_cost))


if __name__ == '__main__':
    # if args.test:
    #     test()
    # elif args.predict:
    #     with open(args.filename) as file:
    #         bod = [file.read()]
    #     predict(bod)
    # elif args.pre:
    #     predict2()
    # else:
    #     train()
    if args.test:
        test()
    elif args.predict:
        with open(args.filename) as file:
            bod = [file.read()]
        print(bod)
        predict(bod)
    else:
        train()
