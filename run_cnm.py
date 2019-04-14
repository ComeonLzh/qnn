# -*- coding: utf-8 -*-
from params import Params
from dataset import qa
import keras.backend as K
#import units
import pandas as pd
from layers.loss import *
from layers.loss.metrics import precision_batch
from tools.units import to_array, getOptimizer
import argparse
import itertools
from numpy.random import seed
from tensorflow import set_random_seed
import tensorflow as tf
import os
import random
from models import match as models   
from tools.evaluation import matching_score

def run(params,reader):
    test_data = reader.getTest(iterable = False, mode = 'test')
    dev_data = reader.getTest(iterable = False, mode = 'dev')
    qdnn = models.setup(params)
    model = qdnn.getModel()

    history=[]
    data_generator = None
    if 'onehot' not in params.__dict__:
        params.onehot = 0
    if params.match_type == 'pointwise':
        test_data = [to_array(i,reader.max_sequence_length) for i in test_data]
        dev_data = [to_array(i,reader.max_sequence_length) for i in dev_data]
        if params.onehot:
            loss_type,metric_type = ("categorical_hinge","acc") 
        else:
            loss_type,metric_type = ("mean_squared_error","mean_squared_error")
            
        model.compile(loss =loss_type, #""
                optimizer = getOptimizer(name=params.optimizer,lr=params.lr),
                metrics=[metric_type])
        data_generator = reader.getPointWiseSamples4Keras(onehot = params.onehot)
#            if "unbalance" in  params.__dict__ and params.unbalance:
#                model.fit_generator(reader.getPointWiseSamples4Keras(onehot = params.onehot,unbalance=params.unbalance),epochs = 1,steps_per_epoch=int(len(reader.datas["train"])/reader.batch_size),verbose = True)        
#            else:
#                model.fit_generator(reader.getPointWiseSamples4Keras(onehot = params.onehot),epochs = 1,steps_per_epoch=len(reader.datas["train"]["question"].unique())/reader.batch_size,verbose = True)        
    elif params.match_type == 'pairwise':
        test_data.append(test_data[0])
        test_data = [to_array(i,reader.max_sequence_length) for i in test_data]
        dev_data.append(dev_data[0])
        dev_data = [to_array(i,reader.max_sequence_length) for i in dev_data]
        model.compile(loss = identity_loss,
                optimizer = getOptimizer(name=params.optimizer,lr=params.lr),
                metrics=[precision_batch],
                loss_weights=[0.0, 1.0,0.0])
        data_generator = reader.getPairWiseSamples4Keras()
          
    print('Training the network:')
    for i in range(params.epochs):
        model.fit_generator(data_generator,epochs = 1,steps_per_epoch=int(len(reader.datas["train"]["question"].unique())/reader.batch_size),verbose = True)          
        print('Validation Performance:')
        y_pred = model.predict(x = dev_data) 
        score = matching_score(y_pred, params.onehot, params.match_type)
        metric = reader.evaluate(score, mode = "dev")
        history.append(metric)
        print(metric)
    print('Done.')
    print('Test Performance:')
    y_pred = model.predict(x = test_data) 
    score = matching_score(y_pred, params.onehot, params.match_type)    
    metric = reader.evaluate(score, mode = "test")
    print(metric)
              
    return history, metric
            

    
if __name__ == '__main__':
#def test_match():
    
    grid_parameters ={
#        "dataset_name":["MR","TREC","SST_2","SST_5","MPQA","SUBJ","CR"],
        "wordvec_path":["glove/glove.6B.50d.txt","glove/glove.6B.100d.txt","glove/glove.6B.200d.txt","glove/glove.6B.300d.txt"],#"glove/glove.6B.300d.txt"],"glove/normalized_vectors.txt","glove/glove.6B.50d.txt","glove/glove.6B.100d.txt",
#        "loss": ["categorical_crossentropy"],#"mean_squared_error"],,"categorical_hinge"
        "optimizer":["rmsprop", "adagrad"],#,"adadelta","adam" ,"adamax","nadam"
        "batch_size":[16,32],#,32
#        "activation":["sigmoid"],
#        "amplitude_l2":[0.0000005],
#        "phase_l2":[0.00000005],
#        "dense_l2":[0],#0.0001,0.00001,0],
        "measurement_size" :[300,500],#,50100],
#        "ngram_value":["1,2,3","2,3,4","1,3,4"],
#        "margin":[0.1,0.2],
        "lr" : [0.5,0.1,0.025],#,1,0.01
#        "dropout_rate_embedding" : [0.9],#0.5,0.75,0.8,0.9,1],
#        "dropout_rate_probs" : [0.8,0.9]#,0.5,0.75,0.8,1]   
#            "ngram_value" : [3]
#        "max_len":[100],
#        "one_hot": [1],
#        "dataset_name": ["wiki","trec"],
#        "pooling_type": ["max","average","none"],
        "distance_type":[6],
        "train_verbose":[0,1],
        "remove_punctuation": [0],
        "stem" : [0],
        "remove_stopwords" : [1],        
        "max_len":[100],
        "one_hot": [0],
    }


    params = Params()
    parser = argparse.ArgumentParser(description='Running the Complex-valued Network for Matching.')
    parser.add_argument('-gpu_num', action = 'store', dest = 'gpu_num', help = 'please enter the gpu num.',default=1)
    parser.add_argument('-gpu', action = 'store', dest = 'gpu', help = 'please enter the gpu num.',default=0)
    parser.add_argument('-config', action = 'store', dest = 'config', help = 'please enter the config path.',default='config/qalocal_pair_trec.ini')
    args = parser.parse_args()
    parameters= [arg for index,arg in enumerate(itertools.product(*grid_parameters.values())) if index%args.gpu_num==args.gpu]
    params.parse_config(args.config)
    
#   Reproducibility Setting
    seed(params.seed)
    set_random_seed(params.seed)
    random.seed(params.seed)
    
    session_conf = tf.ConfigProto(intra_op_parallelism_threads=1, inter_op_parallelism_threads=1)
    sess = tf.Session(graph=tf.get_default_graph(), config=session_conf)
    K.set_session(sess)
    
    file_writer = open(params.output_file,'w')
    for parameter in parameters:
#        old_dataset = params.dataset_name
#        old_dataset = params.dataset_name
        params.setup(zip(grid_parameters.keys(),parameter))
#        if old_dataset != params.dataset_name:   # batch_size
#            print("switch %s to %s"%(old_dataset,params.dataset_name))
#            reader=dataset.setup(params)
#            params.reader = reader
   
        reader = qa.setup(params)
        history, performance = run(params, reader)
        df=pd.DataFrame([list(performance)],columns=["map","mrr","p1"])
        file_writer.write(params.to_string()+'\n')
        file_writer.write(df+'\n')
        file_writer.write('_________________________\n\n\n')
        file_writer.flush()
        K.clear_session()
        
            
                
    
        
    
    
    
