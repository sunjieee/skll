# License: BSD 3 clause
'''
Module for running a bunch of simple unit tests. Should be expanded more in
the future.

:author: Michael Heilman (mheilman@ets.org)
:author: Nitin Madnani (nmadnani@ets.org)
:author: Dan Blanchard (dblanchard@ets.org)
:author: Aoife Cahill (acahill@ets.org)
'''

from __future__ import absolute_import, division, print_function, unicode_literals

import glob
import itertools
import os
import re
import subprocess

from io import open
from os.path import abspath, dirname, exists, join

from nose.tools import eq_, assert_almost_equal
from numpy.testing import assert_array_equal, assert_allclose

from skll.data import FeatureSet, NDJWriter
from skll.data.readers import EXT_TO_READER
from skll.data.writers import EXT_TO_WRITER
from skll.experiments import _setup_config_parser
from skll.learner import Learner, _DEFAULT_PARAM_GRIDS
from skll.utilities.compute_eval_from_predictions \
    import compute_eval_from_predictions
from skll.utilities.generate_predictions import Predictor

from utils import make_classification_data


_ALL_MODELS = list(_DEFAULT_PARAM_GRIDS.keys())
SCORE_OUTPUT_RE = re.compile(r'Objective Function Score \(Test\) = '
                             r'([\-\d\.]+)')
GRID_RE = re.compile(r'Grid Objective Score \(Train\) = ([\-\d\.]+)')
_my_dir = abspath(dirname(__file__))


def setup():
    train_dir = join(_my_dir, 'train')
    if not exists(train_dir):
        os.makedirs(train_dir)
    test_dir = join(_my_dir, 'test')
    if not exists(test_dir):
        os.makedirs(test_dir)
    output_dir = join(_my_dir, 'output')
    if not exists(output_dir):
        os.makedirs(output_dir)


def tearDown():
    test_dir = join(_my_dir, 'test')
    output_dir = join(_my_dir, 'output')
    other_dir = join(_my_dir, 'other')
    os.unlink(join(test_dir, 'test_generate_predictions.jsonlines'))
    for model_chunk in glob.glob(join(output_dir, 'test_generate_predictions.model*')):
        os.unlink(model_chunk)
    for model_chunk in glob.glob(join(output_dir, 'test_generate_predictions_console.model*')):
        os.unlink(model_chunk)
    for f in glob.glob(join(other_dir, 'test_skll_convert*')):
        os.unlink(f)


def test_compute_eval_from_predictions():
    pred_path = join(_my_dir, 'other',
                     'test_compute_eval_from_predictions.predictions')
    input_path = join(_my_dir, 'other',
                      'test_compute_eval_from_predictions.jsonlines')

    scores = compute_eval_from_predictions(input_path, pred_path,
                                           ['pearson', 'unweighted_kappa'])

    assert_almost_equal(scores['pearson'], 0.6197797868009122)
    assert_almost_equal(scores['unweighted_kappa'], 0.2)


def check_generate_predictions(use_feature_hashing=False, use_threshold=False):

    # create some simple classification data without feature hashing
    train_fs, test_fs = make_classification_data(num_examples=1000,
                                                 num_features=5,
                                                 use_feature_hashing=use_feature_hashing,
                                                 feature_bins=4)

    # create a learner that uses an SGD classifier
    learner = Learner('SGDClassifier', probability=use_threshold)

    # train the learner with grid search
    learner.train(train_fs, grid_search=True, feature_hasher=use_feature_hashing)

    # get the predictions on the test featureset
    predictions = learner.predict(test_fs, feature_hasher=use_feature_hashing)

    # if we asked for probabilities, then use the threshold
    # to convert them into binary predictions
    if use_threshold:
        threshold = 0.6
        predictions = [int(p[1] >= threshold) for p in predictions]
    else:
        predictions = predictions.tolist()
        threshold = None

    # save the learner to a file
    model_file = join(_my_dir, 'output',
                      'test_generate_predictions.model')
    learner.save(model_file)

    # now use Predictor to generate the predictions and make
    # sure that they are the same as before saving the model
    p = Predictor('output/test_generate_predictions.model',
                  threshold=threshold)
    predictions_after_saving = p.predict(test_fs)

    eq_(predictions, predictions_after_saving)


def test_generate_predictions():
    '''
    Test generate predictions API with hashing and a threshold
    '''

    yield check_generate_predictions, False, False
    yield check_generate_predictions, True, False
    yield check_generate_predictions, False, True
    yield check_generate_predictions, True, True


def check_generate_predictions_console(use_threshold=False):

    # create some simple classification data without feature hashing
    train_fs, test_fs = make_classification_data(num_examples=1000,
                                                 num_features=5)

    # save the test feature set to an NDJ file
    input_file = join(_my_dir, 'test',
                      'test_generate_predictions.jsonlines')
    writer = NDJWriter(input_file, test_fs)
    writer.write()

    # create a learner that uses an SGD classifier
    learner = Learner('SGDClassifier', probability=use_threshold)

    # train the learner with grid search
    learner.train(train_fs, grid_search=True)

    # get the predictions on the test featureset
    predictions = learner.predict(test_fs)

    # if we asked for probabilities, then use the threshold
    # to convert them into binary predictions
    if use_threshold:
        threshold = 0.6
        predictions = [int(p[1] >= threshold) for p in predictions]
    else:
        predictions = predictions.tolist()
        threshold = None

    # save the learner to a file
    model_file = join(_my_dir, 'output',
                      'test_generate_predictions_console.model')
    learner.save(model_file)

    # now call generate_predictions.py on the command line
    generate_cmd = ['generate_predictions']
    if use_threshold:
        generate_cmd.append('-t {}'.format(threshold))
    generate_cmd.extend([model_file, input_file])

    p = subprocess.Popen(generate_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate()
    predictions_after_saving = [int(x) for x in out.decode().strip().split('\n')]

    eq_(predictions, predictions_after_saving)


def test_generate_predictions_console():
    '''
    Test generate_predictions as a console script with a threshold
    '''

    yield check_generate_predictions_console, False
    yield check_generate_predictions_console, True


def check_skll_convert(from_suffix, to_suffix):

    # create some simple classification data
    orig_fs, _ = make_classification_data(train_test_ratio=1.0)

    # now write out this feature set in the given suffix
    from_suffix_file = join(_my_dir, 'other',
                         'test_skll_convert_in{}'.format(from_suffix))
    to_suffix_file = join(_my_dir, 'other',
                         'test_skll_convert_out{}'.format(to_suffix))

    writer = EXT_TO_WRITER[from_suffix](from_suffix_file, orig_fs, quiet=True)
    writer.write()

    # now run skll convert to convert the featureset into the other format
    skll_convert_cmd = ['skll_convert', from_suffix_file, to_suffix_file, '--quiet']
    retcode = subprocess.call(skll_convert_cmd)

    # now read the converted file
    reader = EXT_TO_READER[to_suffix](to_suffix_file, quiet=True)
    converted_fs = reader.read()

    # ensure that the original and the converted feature sets
    # have the same ids and classes and the features
    assert_array_equal(orig_fs.ids, converted_fs.ids)
    assert_array_equal(orig_fs.classes, converted_fs.classes)
    assert_allclose(orig_fs.features.todense(), converted_fs.features.todense())


def test_skll_convert():
    for from_suffix, to_suffix in itertools.permutations(['.jsonlines', '.ndj',
                                                          '.megam', '.tsv',
                                                          '.csv', '.arff',
                                                          '.libsvm'], 2):
        yield check_skll_convert, from_suffix, to_suffix

