import sys
import os.path
import shutil
import logging
import uuid
import json    
import numpy as np
import h5py

from keras.utils.np_utils import to_categorical
from sklearn import metrics

def count_parameters(model):
    if hasattr(model, 'count_params'):
        return model.count_params()
    else:
        n = 0
        for layer in model.layers:
            for param in layer.params:
                n += np.prod(param.shape.eval())
        return n

class ModelConfig:
    def __init__(self, **entries): 
        self.__dict__.update(entries)

    def __repr__(self):
        return str(vars(self))

class LoggerWriter:
    def __init__(self, level):
        # self.level is really like using log.debug(message)
        # at least in my case
        self.level = level

    def write(self, message):
        # if statement reduces the amount of newlines that are
        # printed to the logger
        if message != '\n':
            self.level(message)
                
    def flush(self):
        # create a flush method so things can be flushed when
        # the system wants to. Not sure if simply 'printing'
        # sys.stderr is the correct way to do it, but it seemed
        # to work properly for me.
        self.level(sys.stderr)

def callable_print(s):
    print(s)

def load_model_data(path, data_name, target_name, n=sys.maxsize):
    hdf5 = h5py.File(path, 'r')
    datasets = [hdf5[d].value.astype(np.int32) for d in data_name]
    for i,d in enumerate(datasets):
        if d.ndim == 1:
            datasets[i] = d.reshape((d.shape[0], 1))
    data = np.concatenate(datasets, axis=1)
    target = hdf5[target_name].value.astype(np.int32)
    hdf5.close()

    if len(data) > n:
        target = target[0:n]
        data = data[0:n, :]

    return data, target

def setup_logging(log_path=None):
    logging.basicConfig(filename=log_path,
            format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
            datefmt='%m-%d %H:%M',
            level=logging.DEBUG)
    stdout = LoggerWriter(logging.info)
    stderr = LoggerWriter(logging.warning)
    return stdout, stderr

def build_model_id(config):
    if config.model_dest:
        return config.model_dest
    else:
        return uuid.uuid1().hex

def build_model_path(config, model_id):
    # TODO: Windows compatibility.
    if len(config.model_dest):
        return config.model_dest + '/'
    else:
        return config.model_dir + '/' + model_id + '/'

def setup_model_dir(config, model_path):
    if 'persistent' in config.mode:
        if not os.path.exists(model_path):
            os.mkdir(model_path)

def load_model_json(config, x_train=None, n_classes=None):
    # Load the base model configuration.
    json_cfg = json.load(open(config.model_dir + '/model.json'))

    # Copy command-line arguments.
    for k,v in vars(config).items():
        json_cfg[k] = v
    # Copy (overriding) model parameters provided on the command-line.
    for k,v in config.model_cfg:
        str_to_bool = { 'True': True, 'False': False }
        if isinstance(v, str) and v.title() in ['True', 'False']:
            v = str_to_bool[v.title()]
        json_cfg[k] = v

    # Add some values are derived from the training data.
    if x_train is not None:
        json_cfg['n_embeddings'] = max(config.n_embeddings, np.max(x_train) + 1)
        json_cfg['input_width'] = x_train.shape[1]

    if n_classes is not None:
        json_cfg['n_classes'] = n_classes
    
    return json_cfg

def balanced_class_weights(y, n_classes, class_weight_exponent=1):
    n_samples = len(y)
    weights = float(n_samples) / (n_classes * np.bincount(y))
    weights = weights**class_weight_exponent
    return dict(zip(range(n_classes), weights))

def load_target_data(config, n_classes):
    if not config.target_data:
        return n_classes, None, None

    target_names_dict = json.load(open(config.target_data))

    try:
        target_data = target_names_dict[config.target_name]
    except KeyError:
        raise ValueError("Invalid key " + config.target_name +
                " for dictionary in " + config.target_data)

    if isinstance(target_data, dict):
        try:
            target_names = target_data['names']
            class_weight = target_data['weights']
        except KeyError as e:
            raise ValueError("Target data dictionary from " +
                    config.target_data + "is missing a key: " + str(e))
    elif isinstance(target_data, list):
        target_names = target_data
        class_weight = None
    else:
        raise ValueError("Target data must be list or dict, not " +
                str(type(target_data)))

    if class_weight is not None:
        # Keys are strings in JSON; convert them to int.
        for key in class_weight.keys():
            v = class_weight[key]
            del class_weight[key]
            class_weight[int(key)] = v

    n_classes = len(target_names)

    if config.verbose:
        print(n_classes, target_names, class_weight)

    return n_classes, target_names, class_weight

def save_model_info(config, model_path):
    assert config.description is not None
    assert config.model_dir is not None
    assert model_path is not None

    with open(model_path + '/README.txt', 'w') as f:
        f.write(config.description + '\n')

    # Save model hyperparameters and code.
    for model_file in ['model.py', 'model.json']:
        shutil.copyfile(config.model_dir + '/' + model_file,
                model_path + '/' + model_file)

    model_info = {}
    for k,v in vars(config).items():
        if k not in ['stdout', 'stderr', 'callback_logger']:
            model_info[k] = v

    json.dump(model_info, open(model_path + '/config.json', 'w'))

def load_all_model_data(data_file, model_cfg, n=sys.maxsize):
    data, target = load_model_data(data_file,
            model_cfg.data_name, model_cfg.target_name, n=n)

    target_one_hot = to_categorical(target, model_cfg.n_classes)

    results = {
            'data': data,
            'target': target,
            'target_one_hot': target_one_hot
            }

    seen_keys = list(model_cfg.data_name)
    seen_keys.append(model_cfg.target_name)

    f = h5py.File(data_file, 'r')

    for key in f.keys():
        if key in seen_keys:
            continue

        if key in results.keys():
            newkey = '_' + key
        else:
            newkey = key

        results[newkey] = f[key].value[0:n]

    f.close()

    # Return dict as namespace for easy tab completion.
    config = ModelConfig(**results)

    return config

def load_model(model_dir, model_weights=None):
    config_json = json.load(open(model_dir + '/config.json'))
    model_json = json.load(open(model_dir + '/model.json'))
    model_json.update(config_json)

    if 'model_cfg' in model_json:
        for k,v in model_json['model_cfg']:
            model_json[k] = v

    if model_weights:
        if isinstance(model_weights, bool) and model_weights is True:
            # Original behavior: only one weights file exists and it has
            # the weights from the best epoch.
            model_json['model_weights'] = model_dir + '/model.h5'
        elif isinstance(model_weights, str):
            # New behavior: multiple weights files may exist.
            if os.path.exists(model_dir + '/' + model_weights):
                model_json['model_weights'] = model_dir + '/' + model_weights
            else:
                model_json['model_weights'] = model_weights
        else:
            raise ValueError('unexpected type for "model_weights" %s (%s)' %
                    (model_weights, type(model_weights)))

    # Re-instantiate ModelConfig using the updated JSON.
    sys.path.append(model_dir)
    from model import build_model
    model_cfg = ModelConfig(**model_json)
    model = build_model(model_cfg)

    return model, model_cfg

def predict_proba(model, data):
    probs = model.predict_proba(data)
    preds = np.argmax(probs, axis=1)
    return probs, preds

def save_probs_preds_to_file(hdf5_path, probs, preds):
    if os.path.exists(hdf5_path):
        f = h5py.File(hdf5_path, 'r+')
        try:
            del f['prob']
        except KeyError:
            pass
        try:
            del f['pred']
        except KeyError:
            pass
    else:
        f = h5py.File(hdf5_path, 'w')
    f.create_dataset('prob', data=probs, dtype=np.float32)
    f.create_dataset('pred', data=preds, dtype=np.int32)
    f.close()

def load_predict(model_dir, data_file, model_weights=None):
    model, model_cfg = load_model(model_dir, model_weights=model_weights)
    model_data = load_all_model_data(data_file, model_cfg)
    probs, preds = predict_proba(model, model_data.data)
    return model, model_cfg, model_data, probs, preds

def load_predict_save(model_dir, data_file, model_name=None, output_dir=None, model_weights=None):
    if model_name is None:
        model_name = os.path.basename(os.path.dirname(model_dir))
    data_name = os.path.basename(data_file)
    data_prefix = os.path.splitext(data_name)[0]

    if output_dir is None:
        output_dir = os.path.dirname(data_file)
    output_prefix = output_dir + '/' + data_prefix + '-' + model_name

    cfg_output_file = output_prefix + '-cfg.json'
    pred_output_file = output_prefix + '-pred.h5'

    model, model_cfg, model_data, probs, preds = load_predict(model_dir,
            data_file, model_weights=model_weights)

    # Save the configuration.
    model_json = dict(vars(model_cfg))
    json.dump(model_json, open(cfg_output_file, 'w'))
    print('Saved model config to %s' % cfg_output_file)

    # Save the predictions.
    save_probs_preds_to_file(pred_output_file, probs, preds)
    print('Saved predictions to %s' % pred_output_file)

def print_classification_report(target, pred, target_names, digits=4):
    print(metrics.classification_report(target, pred, target_names=target_names, digits=digits))

def precision_recall_fscore_support(target, pred, beta=1.0, average='weighted'):
    prfs = metrics.precision_recall_fscore_support(target, pred, beta=beta, average=average)
    prfs = list(prfs)
    if average is not None:
        prfs[-1] = len(target)
    return prfs

def predict_with_absolute_threshold(probs, target, threshold=0.7):
    preds = np.argmax(probs, axis=1)
    preds_with_thresh = []
    indices_used = []

    for i in np.arange(0, len(preds)):
        pred = preds[i]
        prob = probs[i]
        if max(prob) >= threshold:
            preds_with_thresh.append(np.argmax(prob))
            indices_used.append(i)

    return np.array(preds_with_thresh), np.array(indices_used)

def predict_with_min_margin_top_two(probs, target, current_word_target, margin=0.5):
    preds = np.argmax(probs, axis=1)
    preds_with_margin = np.zeros_like(target)

    for i in np.arange(0, len(preds)):
        pred = preds[i]
        prob = probs[i]
        next_most_prob, most_prob = prob[np.configort(prob)[[-2,-1]]]

        if most_prob - next_most_prob < margin:
            preds_with_margin[i] = current_word_target[i]
        else:
            preds_with_margin[i] = np.argmax(prob)

    return preds_with_margin

def predict_with_min_margin_vs_actual(probs, target, current_word_target, min_margin=0.3):
    preds = np.argmax(probs, axis=1)
    preds_with_margin = np.zeros_like(preds)

    for i in np.arange(0, len(preds)):
        pred = preds[i]
        prob = probs[i]
        most_prob = prob[np.configort(prob)][-1]
        actual_prob = prob[current_word_target[i]]
        margin = most_prob - actual_prob 

        if margin <= min_margin:
            preds_with_margin[i] = current_word_target[i]
        else:
            preds_with_margin[i] = np.argmax(prob)

    return preds_with_margin

def predict_with_minmax_margin(probs, target, current_word_target, min_margin=0.025, max_margin=0.25):
    preds = np.argmax(probs, axis=1)
    preds_with_margin = np.zeros_like(preds)

    for i in np.arange(0, len(preds)):
        pred = preds[i]
        prob = probs[i]
        most_prob = prob[np.configort(prob)][-1]
        actual_prob = prob[current_word_target[i]]
        margin = most_prob - actual_prob 

        if margin > min_margin and margin < max_margin:
            preds_with_margin[i] = current_word_target[i]
        else:
            preds_with_margin[i] = np.argmax(prob)

    return preds_with_margin
