'''
Implementation of Word Representations via Gaussian Embedding.
    https://arxiv.org/abs/1412.6623
'''

import argparse
import numpy as np
import tensorflow as tf

# Parse command line arguments
parser = argparse.ArgumentParser(description='Train Gaussian embeddings.')

parser.add_argument('data_file', type=str,
                    help='Name of data file. Must be a TFRecord.')
parser.add_argument('vocab_size', type=int,
                    help=('Number of unique tokens in the vocabulary. Must '
                          'include the not-a-word token!'))
parser.add_argument('window_size', type=int,
                    help='Window size (i.e. "diameter" of window).')
parser.add_argument('embed_dim', type=int,
                    help='Dimensionality of the embedding space.')
parser.add_argument('batch_size', type=int, nargs='?', default=512,
                    help='Batch size.')
parser.add_argument('margin', type=float, nargs='?', default=2.0,
                    help='Margin in max-margin loss. Defaults to 2.')
parser.add_argument('num_epochs', type=int, nargs='?', default=100,
                    help='Number of epochs. Defaults to 500.')
parser.add_argument('C', type=float, nargs='?', default=100.0,
                    help='Maximum L2 norm of mu. Defaults to 100.')
parser.add_argument('m', type=float, nargs='?', default=1e-2,
                    help='Minimum covariance eigenvalue. Defaults to 1e-2.')
parser.add_argument('M', type=float, nargs='?', default=1e2,
                    help='Maximum covariance eigenvalue. Defaults to 1e2.')

args = parser.parse_args()

center_id = tf.placeholder(tf.int32, [None])
context_ids = tf.placeholder(tf.int32, [None, args.window_size])
negative_ids = tf.placeholder(tf.int32, [None, args.window_size])

# Data
features = {
    'center': tf.FixedLenFeature([], tf.int64),
    'context': tf.FixedLenSequenceFeature([], tf.int64, allow_missing=True),
    'negative': tf.FixedLenSequenceFeature([], tf.int64, allow_missing=True)
}
dataset = (tf.data.TFRecordDataset([args.data_file])
             .map(lambda x: tf.parse_single_example(x, features))
             .batch(args.batch_size))
dataset = dataset.repeat()
iterator = dataset.make_one_shot_iterator()
next_batch = iterator.get_next()

# Initialize embeddings
mu = tf.get_variable('mu', [args.vocab_size, args.embed_dim], tf.float32,
                     tf.random_normal_initializer)
sigma = tf.get_variable('sigma', [args.vocab_size, args.embed_dim], tf.float32,
                        tf.keras.initializers.Constant(0.5))

# Look up embeddings
# [BATCH_SIZE, EMBED_DIM, 1]
center_mu = tf.expand_dims(tf.nn.embedding_lookup(mu, center_id), -1)
center_sigma = tf.expand_dims(tf.nn.embedding_lookup(sigma, center_id), -1)
# [BATCH_SIZE, EMBED_DIM, WINDOW_SIZE]
context_mus = tf.linalg.transpose(tf.nn.embedding_lookup(mu, context_ids))
context_sigmas = tf.linalg.transpose(tf.nn.embedding_lookup(sigma, context_ids))
negative_mus = tf.linalg.transpose(tf.nn.embedding_lookup(mu, negative_ids))
negative_sigmas = tf.linalg.transpose(tf.nn.embedding_lookup(sigma, negative_ids))

'''
# Compute log expected likelihood
logdet_pos = tf.log(tf.reduce_prod(center_sigma + context_sigmas, axis=1))
quadform_pos = tf.reduce_sum(
    (center_mu - context_mus)**2 / (center_sigma + context_sigmas),
    axis=1
)
log_positive_energies = -0.5 * (logdet_pos + quadform_pos
                                + args.embed_dim*np.log(2*np.pi))
positive_energies = tf.exp(log_positive_energies)

logdet_neg = tf.log(tf.reduce_prod(center_sigma + negative_sigmas, axis=1))
quadform_neg = tf.reduce_sum(
    (center_mu - negative_mus)**2 / (center_sigma + negative_sigmas),
    axis=1
)
log_negative_energies = -0.5 * (logdet_neg + quadform_neg
                                + args.embed_dim*np.log(2*np.pi))
negative_energies = tf.exp(log_negative_energies)
'''

# Compute KL
trace_pos = tf.reduce_sum(1/context_sigmas * center_sigma, axis=1)
quadform_pos = tf.reduce_sum(
    (context_mus - center_mu)**2 / (context_sigmas),
    axis=1
)
logdet_pos = tf.log(
    tf.reduce_prod(context_sigmas, axis=1) / tf.reduce_prod(center_sigma)
)
positive_energies = 0.5 * (trace_pos
                           + quadform_pos
                           - args.embed_dim
                           - logdet_pos)

trace_neg = tf.reduce_sum(1/negative_sigmas * center_sigma, axis=1)
quadform_neg = tf.reduce_sum(
    (negative_mus - center_mu)**2 / (negative_sigmas),
    axis=1
)
logdet_neg = tf.log(
    tf.reduce_prod(negative_sigmas, axis=1) / tf.reduce_prod(center_sigma)
)
negative_energies = 0.5 * (trace_neg
                           + quadform_neg
                           - args.embed_dim
                           - logdet_neg)

max_margins = tf.maximum(0.0,
                         args.margin
                         - positive_energies
                         + negative_energies)
loss = tf.reduce_mean(max_margins)

# Minimize loss
train_step = tf.train.AdamOptimizer().minimize(loss)

# Regularize means and covariance eigenvalues
with tf.control_dependencies([train_step]):
    clip_mu = tf.clip_by_norm(mu, args.C)
    bound_sigma = tf.maximum(args.m, tf.minimum(args.M, sigma))

# Training
sess = tf.Session()
sess.run(tf.global_variables_initializer())

for i in range(args.num_epochs):
    data = sess.run(next_batch)
    foo, _, _, _ = \
        sess.run([loss, train_step, clip_mu, bound_sigma],
                 feed_dict={center_id: data['center'],
                            context_ids: data['context'],
                            negative_ids: data['negative']})
    print(foo)

# Save embedding parameters as .npy files
mu_np = mu.eval(session=sess)
sigma_np = sigma.eval(session=sess)
np.save('mu.npy', mu_np)
np.save('sigma.npy', sigma_np)
