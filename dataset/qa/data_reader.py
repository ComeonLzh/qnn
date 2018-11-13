# -*- coding: utf-8 -*-

#-*- coding:utf-8 -*-

import os
import numpy as np
import tensorflow as tf

from collections import Counter
import pandas as pd

import random
import pickle
import preprocess
from tools.timer import log_time_delta

from nltk.corpus import stopwords
Overlap = 237
import random
from units import to_array 
from tools import evaluation
from preprocess.dictionary import Dictionary
from preprocess.embedding import Embedding
from preprocess.bucketiterator import BucketIterator

class DataReader(object):
    def __init__(self,opt):
        for key,value in opt.__dict__.items():
            self.__setattr__(key,value)        
      
        self.dir_path = os.path.join(opt.datasets_dir, 'QA', opt.dataset_name.lower())
        self.preprocessor = preprocess.setup(opt)
        self.datas = self.load(do_filter = opt.remove_unanswered_question)
        self.embedding = Embedding(self.get_dictionary(self.datas.values()))
        q_max_sent_length = max(map(lambda x:len(x),self.datas["train"]['question'].str.split()))
        a_max_sent_length = max(map(lambda x:len(x),self.datas["train"]['answer'].str.split()))    
        self.max_sequence_length = max(q_max_sent_length,a_max_sent_length)
#        self.q_max_sent_length = q_max_sent_length
#        self.a_max_sent_length = a_max_sent_length

        print('loading word embedding...')
        if opt.dataset_name=="NLPCC":     # can be updated
            self.embedding.get_embedding(dataset_name = self.dataset_name, language="cn",fname=opt.wordvec_path) 
        else:
            self.embedding.get_embedding(dataset_name = self.dataset_name, fname=opt.wordvec_path)
            
        self.nb_classes = 2
#        opt.embedding_size = self.embeddings.shape[1]
        if self.max_sequence_length > self.max_len:
            self.max_sequence_length = self.max_len
#        self.optCallback(opt)            
        
            
    def load(self, do_filter = True):
        datas = dict()
        clean_set = ['test','dev'] if self.train_verbose else ['train','test','dev']
        for data_name in ['train','test']: #'dev'            
            data_file = os.path.join(self.dir_path,data_name+".txt")
            data = pd.read_csv(data_file,header = None,sep="\t",names=["question","answer","flag"]).fillna('0')
            if do_filter == True and data_name in clean_set:
                data=self.remove_unanswered_questions(data)
                
            data['question'] = data['question'].apply(lambda x : self.preprocessor.run(x))
            data['answer'] = data['answer'].apply(lambda x : self.preprocessor.run(x))
            datas[data_name] = data
        return datas
    
    @log_time_delta
    def remove_unanswered_questions(self,df):
        counter = df.groupby("question").apply(lambda group: sum(group["flag"]))
        questions_have_correct = counter[counter>0].index
#        counter= df.groupby("question").apply(lambda group: sum(group["flag"]==0))
#        questions_have_uncorrect=counter[counter>0].index
#        counter=df.groupby("question").apply(lambda group: len(group["flag"]))
#        questions_multi=counter[counter>1].index
    
        return df[df["question"].isin(questions_have_correct) ].reset_index()  #&  df["question"].isin(questions_have_correct) & df["question"].isin(questions_have_uncorrect)

                
    def get_dictionary(self,corpuses = None,dataset="",fresh=True):
        pkl_name="temp/"+self.dataset_name+".alphabet.pkl"
        if os.path.exists(pkl_name) and not fresh:
            return pickle.load(open(pkl_name,"rb"))
        dictionary = Dictionary(start_feature_id = 0)
        dictionary.add('[UNK]')  
#        alphabet.add('END') 
        for corpus in corpuses:
            for texts in [corpus["question"].unique(),corpus["answer"]]:    
                for sentence in texts:                   
                    tokens = sentence.lower().split()
                    for token in set(tokens):
                        dictionary.add(token)
        print("alphabet size = {}".format(len(dictionary.keys())))
        if not os.path.exists("temp"):
            os.mkdir("temp")
        pickle.dump(dictionary,open(pkl_name,"wb"))
        return dictionary   
    
    
#    @log_time_delta
    def getTrain(self,shuffle = True,model=None,sess=None,overlap_feature= False,iterable=True,max_sequence_length=0):
        
        q,a,neg_a,overlap1,overlap2 = [],[],[],[],[]
        for question,group in self.datas["train"].groupby("question"):
            pos_answers = group[group["flag"] == 1]["answer"]
            neg_answers = group[group["flag"] == 0]["answer"]#.reset_index()
            if len(pos_answers)==0 or len(neg_answers)==0:
    #            print(question)
                continue
            for pos in pos_answers:                
                if model is not None and sess is not None:                    
                    pos_sent = self.embedding.text_to_sequence(pos)
                    q_sent,q_mask = self.prepare_data([pos_sent])                             
                    neg_sents = [self.embedding.text_to_sequence(sent) for sent in neg_answers]
                    a_sent,a_mask = self.prepare_data(neg_sents)                   
                    scores = model.predict(sess,(np.tile(q_sent,(len(neg_answers),1)),a_sent))
                    neg_index = scores.argmax()   
                    seq_neg_a = neg_sents[neg_index]
                else:    
#                    if len(neg_answers.index) > 0:
                    neg_index = np.random.choice(neg_answers.index)
                    neg = neg_answers.loc[neg_index,]
                    seq_neg_a = self.embedding.text_to_sequence(neg)
                
                seq_q = self.embedding.text_to_sequence(question)
                seq_a = self.embedding.text_to_sequence(pos)
                
                q.append(seq_q)
                a.append(seq_a)
                neg_a.append(seq_neg_a)
                if overlap_feature:
                    overlap1.append(self.overlap_index(seq_q,seq_a))
                    overlap2.append(self.overlap_index(seq_q,seq_neg_a))
        if overlap_feature:
            data= (q,a,neg_a,overlap1,overlap2)
        else:
            data = (q,a,neg_a)
#        print("samples size : " +str(len(q)))
        if iterable:
            return BucketIterator(data,batch_size=self.batch_size,shuffle=True,max_sequence_length=max_sequence_length) 
        else: 
            return data
        
    # calculate the overlap_index
    def overlap_index(self,question,answer,stopwords = []):

        qset = set(question)
        aset = set(answer)
        a_len = len(answer)
    
        # q_index = np.arange(1,q_len)
        a_index = np.arange(1,a_len + 1)
    
        overlap = qset.intersection(aset)
        for i,a in enumerate(answer):
            if a in overlap:
                a_index[i] = Overlap
        return a_index
            
    def getTest(self,mode ="test",overlap_feature = False, iterable = True):
        
        if overlap_feature:
            process = lambda row: [self.embedding.text_to_sequence(row["question"]),
                               self.embedding.text_to_sequence(row["answer"]), 
                               self.embedding.overlap_index(row['question'],row['answer'] )]
        else:
            process = lambda row: [self.embedding.text_to_sequence(row["question"]),
                               self.embedding.text_to_sequence(row["answer"])]
        
        samples = self.datas[mode].apply( process,axis=1)
        if iterable:
            return BucketIterator([i for i in zip(*samples)],batch_size=self.batch_size,shuffle=False)
        else: 
            return [i for i in zip(*samples)]
    


        
    def getPointWiseSamples4Keras(self, iterable = False ,onehot=False,unbalance=False):
        if unbalance:
            process = lambda row: [self.embedding.text_to_sequence(row["question"]),
                       self.embedding.text_to_sequence(row["answer"]), 
                       row['flag'] ]
            samples = self.datas["train"].apply(process,axis=1)
            while True:
                for batch in BucketIterator( [i for i in zip(*samples)],batch_size=self.batch_size,shuffle=True,max_sequence_length=self.max_sequence_length):
                    if onehot:
                        yield batch[:2],np.array([[0,1] if i else [1,0] for i in batch[2]])
                    else:
                        yield batch[:2], np.array(batch[2])
        else:
            while True:
                for batch in self.getTrain(iterable=True,max_sequence_length=self.max_sequence_length):
                    q,a,neg = batch
                    if onehot:
                        data = [[np.concatenate([q,q],0).astype(int),np.concatenate([a,neg],0).astype(int)],
                            np.array([[0,1]]*len(q) +[[1,0]]*len(q))]
                    else:
                        data = [[np.concatenate([q,q],0).astype(int),np.concatenate([a,neg],0).astype(int)],
                            [1]*len(q) +[0]*len(q)]
                    yield data
    
    def getPairWiseSamples4Keras(self, iterable = False):
        
        while True:
            for batch in self.getTrain(iterable=True,max_sequence_length=self.max_sequence_length):
                yield batch, batch
        
            
    def prepare_data(self,seqs):
        lengths = [len(seq) for seq in seqs]
        n_samples = len(seqs)
        max_len = np.max(lengths)
    
        x = np.zeros((n_samples, max_len)).astype('int32')
        x_mask = np.zeros((n_samples, max_len)).astype('float')
        for idx, seq in enumerate(seqs):
            x[idx, :lengths[idx]] = seq
            x_mask[idx, :lengths[idx]] = 1.0
         # print( x, x_mask)
        return x, x_mask
    
    def evaluate(self,predicted,mode= "test",acc=False):
        return evaluation.evaluationBypandas(self.datas[mode],predicted,acc=acc)
        

if __name__ == "__main__":
    
    
#    from dataset import qa
#    from params import Params
#    
#    params = Params()
#    config_file = 'config/qa.ini'    # define dataset in the config
#    params.parse_config(config_file)
#    
#    reader = qa.setup(params)
##    data1 = next(iter(reader.getTest()))
##    data = next(iter(reader.getTrain(overlap_feature=True)))
##    for data in reader.getTest(overlap_feature=True,shuffle=False):
##        print(len(data))
##    data = next(iter(reader.getTrain(overlap_feature=True,shuffle=False)))
##    data = next(iter(reader.getTest(overlap_feature=True)))
#    data = reader.getTrain(iterable=False)
    # -*- coding: utf-8 -*-
    import keras
    from keras.layers import Input, Dense, Activation, Lambda
    import numpy as np
    from keras import regularizers
    from keras.models import Model
    import sys
    from params import Params
    from dataset import qa
    import keras.backend as K
    import units
    from loss import *

    from models.match import keras as models
    from params import Params
    params = Params()

    config_file = 'config/qalocal.ini'    # define dataset in the config
    params.parse_config(config_file)
    
    reader = qa.setup(params)
    qdnn = models.setup(params)
    model = qdnn.getModel()
    
    from loss import *
    model.compile(loss = rank_hinge_loss({'margin':0.2}),
                optimizer = units.getOptimizer(name=params.optimizer,lr=params.lr),
                metrics=['accuracy'])
    model.summary()
    
    
    
    
#    generators = [reader.getTrain(iterable=False) for i in range(params.epochs)]
#    [q,a,score] = reader.getPointWiseSamples()
#    model.fit(x = [q,a,a],y = [q,a,q],epochs = 10,batch_size =params.batch_size)
    
#    def gen():
#        while True:
#            for sample in reader.getTrain(iterable = True):
#                yield sample
    model.fit_generator(reader.getPointWiseSamples4Keras(),epochs = 20,steps_per_epoch=1000)
