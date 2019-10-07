import torch
from utils.plaintext import PlaintextParser
from utils.sentence_feature import SentenceFeature
import warnings
warnings.simplefilter("ignore", UserWarning)

class Vocab():
    def __init__(self, embed, word2id):
        self.embed = embed
        self.word2id = word2id
        self.id2word = {v: k for k, v in word2id.items()}
        assert len(self.word2id) == len(self.id2word)
        self.PAD_IDX = 0
        self.UNK_IDX = 1
        self.PAD_TOKEN = 'PAD_TOKEN'
        self.UNK_TOKEN = 'UNK_TOKEN'

    def __len__(self):
        return len(self.word2id)

    def i2w(self, idx):
        return self.id2word[idx]

    def w2i(self, w):
        if w in self.word2id:
            return self.word2id[w]
        else:
            return self.UNK_IDX

    def make_features(self, batch, sent_trunc=50, doc_trunc=100, split_token='\n'):
        sents_list, targets, doc_lens = [], [], []
        # trunc document
        sentents_featuress = []
        for doc, label in zip(batch['doc'], batch['labels']):
            sents = doc.split(split_token)
            labels = label.split(split_token)
            labels = [int(l) for l in labels]
            max_sent_num = min(doc_trunc, len(sents))
            sents = sents[:max_sent_num]
            labels = labels[:max_sent_num]
            sents_list += sents
            targets += labels
            doc_lens.append(len(sents))
            parser = PlaintextParser(sents)
            st_feature = SentenceFeature(parser)
            for index, sent in enumerate(sents):
                features = st_feature.get_all_features(index)
                sentents_featuress.append(features)
        # trunc or pad sent
        max_sent_len = 0
        batch_sents = []
        # print("Sents_list====================")
        # print(sents_list)
        # print(len(sents_list))
       # parser = PlaintextParser(sents_list)
        #st_feature = SentenceFeature(parser)

        for index, sent in enumerate(sents_list):

            words = sent.split()
            if len(words) > sent_trunc:
                words = words[:sent_trunc]
            max_sent_len = len(words) if len(words) > max_sent_len else max_sent_len
            batch_sents.append(words)

        # print("sent_features===============================")
        # print(sentents_featuress[0])

        features = []
        # print("batch_sents==================")
        # print(batch_sents)
        for sent in batch_sents:
            feature = [self.w2i(w) for w in sent] + [self.PAD_IDX for _ in range(max_sent_len - len(sent))]
            features.append(feature)

        features = torch.LongTensor(features)
        sent_features = torch.FloatTensor(sentents_featuress)
        targets = torch.LongTensor(targets)
        summaries = batch['summaries']
        # print("sent_features===============================")
        # print(sent_features[0])

        return features, sent_features, targets, summaries, doc_lens

    def make_summaries(self, batch, doc_trunc=100, split_token='\n'):
        sents_list, targets, doc_lens = [], [], []
        # trunc document
        for doc, label in zip(batch['doc'], batch['labels']):
            sents = doc.split(split_token)
            labels = label.split(split_token)
            labels = [int(l) for l in labels]
            max_sent_num = min(doc_trunc, len(sents))
            sents = sents[:max_sent_num]
            labels = labels[:max_sent_num]
            sents_list += sents
            targets += labels
            doc_lens.append(len(sents))

        doc = batch['doc']

        labelss = batch['labels']

        return doc, labelss, doc_lens

    def make_predict_features(self, batch, sent_trunc=150, doc_trunc=100, split_token='. '):
        sents_list, doc_lens = [], []
        for doc in batch:
            sents = doc.split(split_token)
            max_sent_num = min(doc_trunc, len(sents))
            sents = sents[:max_sent_num]
            sents_list += sents
            doc_lens.append(len(sents))
        # trunc or pad sent
        max_sent_len = 0
        batch_sents = []
        for sent in sents_list:
            words = sent.split()
            if len(words) > sent_trunc:
                words = words[:sent_trunc]
            max_sent_len = len(words) if len(words) > max_sent_len else max_sent_len
            batch_sents.append(words)

        features = []
        for sent in batch_sents:
            feature = [self.w2i(w) for w in sent] + [self.PAD_IDX for _ in range(max_sent_len - len(sent))]
            features.append(feature)

        features = torch.LongTensor(features)

        return features, doc_lens
