# Part of PING-Mapper software
#
# Co-Developed by Cameron S. Bodine and Dr. Daniel Buscombe
#
# Inspired by PyHum: https://github.com/dbuscombe-usgs/PyHum
#
# MIT License
#
# Copyright (c) 2022-23 Cameron S. Bodine
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


# Imports
from funcs_common import *
import os
os.environ['TF_CPP_MIN_LOG_LEVEL']='3'
import json
import numpy as np
import tensorflow as tf
import tensorflow.keras.backend as K
from tensorflow.python.client import device_lib

import itertools

from transformers import TFSegformerForSemanticSegmentation
from transformers import logging
logging.set_verbosity_error()

# Fixes depth detection warning
tf.get_logger().setLevel('ERROR')

from doodleverse_utils.imports import *
from doodleverse_utils.model_imports import *
from doodleverse_utils.prediction_imports import *

################################################################################
# model_imports.py from segmentation_gym                                       #
################################################################################
'''
Utilities provided courtesy Dr. Dan Buscombe from segmentation_gym
https://github.com/Doodleverse/segmentation_gym
'''

#=======================================================================
def initModel(weights, configfile, USE_GPU=False):
    '''
    Compiles a Tensorflow model for bedpicking. Developed following:
    https://github.com/Doodleverse/segmentation_gym

    ----------
    Parameters
    ----------
    None

    ----------------------------
    Required Pre-processing step
    ----------------------------
    self.__init__()

    -------
    Returns
    -------
    self.bedpickModel containing compiled model.

    --------------------
    Next Processing Step
    --------------------
    self._detectDepth()
    '''
    SEED=42
    np.random.seed(SEED)
    AUTO = tf.data.experimental.AUTOTUNE # used in tf.data.Dataset API

    tf.random.set_seed(SEED)

    if USE_GPU == True:
        os.environ['CUDA_VISIBLE_DEVICES'] = '0' # Use GPU
    else:

        os.environ['CUDA_VISIBLE_DEVICES'] = '-1' # Use CPU

    #suppress tensorflow warnings
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

    #suppress tensorflow warnings
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

    # Open model configuration file
    with open(configfile) as f:
        config = json.load(f)
    globals().update(config)


    ########################################################################
    ########################################################################

    # Get model architecture
    if MODEL == 'resunet':
        model =  custom_resunet((TARGET_SIZE[0], TARGET_SIZE[1], N_DATA_BANDS),
                        FILTERS,
                        nclasses=[NCLASSES+1 if NCLASSES==1 else NCLASSES][0],
                        kernel_size=(KERNEL,KERNEL),
                        strides=STRIDE,
                        dropout=DROPOUT,#0.1,
                        dropout_change_per_layer=DROPOUT_CHANGE_PER_LAYER,#0.0,
                        dropout_type=DROPOUT_TYPE,#"standard",
                        use_dropout_on_upsampling=USE_DROPOUT_ON_UPSAMPLING,#False,
                        )

    elif MODEL == 'segformer':
        id2label = {}
        for k in range(NCLASSES):
            id2label[k]=str(k)
        model = segformer(id2label,num_classes=NCLASSES)


    # # Compile model and load weights
    # if MODEL != 'segformer':
    #     try:
    #         # model = tf.keras.models.load_model(weights)
    #         model.load_weights(weights)
    #     except:
    #         model.compile(optimizer = 'adam', loss = dice_coef_loss, metrics = [mean_iou, dice_coef])
    #         model.load_weights(weights)
    #
    # else:
    #     model.compile(optimizer = 'adam')
    #     model.load_weights(weights)

    model.load_weights(weights)
    # model = compile_models([model[0]], MODEL)

    return model, MODEL, N_DATA_BANDS

################################################
# prediction_imports.py from doodleverse_utils #
################################################

#=======================================================================
def doPredict(model, MODEL, arr, N_DATA_BANDS, NCLASSES, TARGET_SIZE, OTSU_THRESHOLD):

    '''
    '''

    model = compile_models([model[0]], MODEL)

    # Read array into a cropped and resized tensor
    image, w, h, bigimage = seg_file2tensor(arr, N_DATA_BANDS, TARGET_SIZE, MODEL)

    image = standardize(image.numpy()).squeeze()

    if NCLASSES == 2:

        E0, E1 = est_label_binary(image, model, MODEL, False, NCLASSES, TARGET_SIZE, w, h)

        e0 = np.average(np.dstack(E0), axis=-1)

        e1 = np.average(np.dstack(E1), axis=-1)

        est_label = (e1 + (1 - e0)) / 2

        softmax_scores = np.dstack((e0,e1))

        if OTSU_THRESHOLD:
            thres = threshold_otsu(est_label)
            est_label = (est_label > thres).astype('uint8')
        else:
            est_label = (est_label > 0.5).astype('uint8')

    else: # NCLASSES>2
        est_label, counter = est_label_multiclass(image, model, MODEL, False, NCLASSES, TARGET_SIZE)

        est_label /= counter + 1
        # est_label cannot be float16 so convert to float32
        est_label = est_label.numpy().astype('float32')

        if MODEL=='segformer':
            est_label = resize(est_label, (1, NCLASSES, TARGET_SIZE[0],TARGET_SIZE[1]), preserve_range=True, clip=True).squeeze()
            est_label = np.transpose(est_label, (1,2,0))
            est_label = resize(est_label, (w, h))
        else:
            est_label = resize(est_label, (w, h))

        softmax_scores = est_label.copy()

        est_label = np.argmax(softmax_scores, -1)


    return est_label, softmax_scores


#=======================================================================
def seg_file2tensor(bigimage, N_DATA_BANDS, TARGET_SIZE, MODEL):#, resize):
    """
    "seg_file2tensor(f)"
    This function reads a jpeg image from file into a cropped and resized tensor,
    for use in prediction with a trained segmentation model
    INPUTS:
        * f [string] file name of jpeg
    OPTIONAL INPUTS: None
    OUTPUTS:
        * image [tensor array]: unstandardized image
    GLOBAL INPUTS: TARGET_SIZE
    """

    image = resize(bigimage,(TARGET_SIZE[0], TARGET_SIZE[1]), preserve_range=True, clip=True)
    image = np.array(image)
    image = tf.cast(image, tf.uint8)

    w = tf.shape(bigimage)[0]
    h = tf.shape(bigimage)[1]

    if MODEL=='segformer':
        if np.ndim(image)==2:
            image = np.dstack((image, image, image))
        image = tf.transpose(image, (2, 0, 1))

    return image, w, h, bigimage


# ### Model for custom res-unet ###
# #=======================================================================
# def custom_resunet(sz,
#     f,
#     nclasses=1,
#     kernel_size=(7,7),
#     strides=2,
#     dropout=0.1,
#     dropout_change_per_layer=0.0,
#     dropout_type="standard",
#     use_dropout_on_upsampling=False,
#     ):
#     """
#     res_unet(sz, f, nclasses=1)
#     This function creates a custom residual U-Net model for image segmentation
#     INPUTS:
#         * `sz`: [tuple] size of input image
#         * `f`: [int] number of filters in the convolutional block
#         * flag: [string] if 'binary', the model will expect 2D masks and uses sigmoid. If 'multiclass', the model will expect 3D masks and uses softmax
#         * nclasses [int]: number of classes
#         dropout (float , 0. and 1.): dropout after the first convolutional block. 0. = no dropout
#
#         dropout_change_per_layer (float , 0. and 1.): Factor to add to the Dropout after each convolutional block
#
#         dropout_type (one of "spatial" or "standard"): Spatial is recommended  by  https://arxiv.org/pdf/1411.4280.pdf
#
#         use_dropout_on_upsampling (bool): Whether to use dropout in the decoder part of the network
#
#         filters (int): Convolutional filters in the initial convolutional block. Will be doubled every block
#     OPTIONAL INPUTS:
#         * `kernel_size`=(7, 7): tuple of kernel size (x, y) - this is the size in pixels of the kernel to be convolved with the image
#         * `padding`="same":  see tf.keras.layers.Conv2D
#         * `strides`=1: see tf.keras.layers.Conv2D
#     GLOBAL INPUTS: None
#     OUTPUTS:
#         * keras model
#     """
#     inputs = tf.keras.layers.Input(sz)
#
#     ## downsample
#     e1 = bottleneck_block(inputs, f)
#     f = int(f*2)
#     e2 = res_block(
#          e1,
#          f,
#          strides=strides,
#          kernel_size = kernel_size,
#          dropout=dropout,
#          dropout_type=dropout_type)
#     f = int(f*2)
#     dropout += dropout_change_per_layer
#     e3 = res_block(
#          e2,
#          f,
#          strides=strides,
#          kernel_size = kernel_size,
#          dropout=dropout,
#          dropout_type=dropout_type)
#     f = int(f*2)
#     dropout += dropout_change_per_layer
#     e4 = res_block(
#          e3,
#          f,
#          strides=strides,
#          kernel_size = kernel_size,
#          dropout=dropout,
#          dropout_type=dropout_type)
#     f = int(f*2)
#     dropout += dropout_change_per_layer
#     _ = res_block(
#         e4,
#         f,
#         strides=strides,
#         kernel_size = kernel_size,
#         dropout=dropout,
#         dropout_type=dropout_type)
#
#     ## bottleneck
#     b0 = conv_block(
#          _,
#          f,
#          strides=1,
#          kernel_size = kernel_size,
#          dropout=dropout,
#          dropout_type=dropout_type)
#     _ = conv_block(
#         b0,
#         f,
#         strides=1,
#         kernel_size = kernel_size,
#         dropout=dropout,
#         dropout_type=dropout_type)
#
#     if not use_dropout_on_upsampling:
#         dropout = 0.0
#         dropout_change_per_layer = 0.0
#
#     ## upsample
#     _ = upsamp_concat_block(_, e4)
#     _ = res_block(
#         _,
#         f,
#         kernel_size = kernel_size,
#         dropout=dropout,
#         dropout_type=dropout_type)
#     f = int(f/2)
#     dropout -= dropout_change_per_layer
#
#     _ = upsamp_concat_block(_, e3)
#     _ = res_block(
#         _,
#         f,
#         kernel_size = kernel_size,
#         dropout=dropout,
#         dropout_type=dropout_type)
#     f = int(f/2)
#     dropout -= dropout_change_per_layer
#
#     _ = upsamp_concat_block(_, e2)
#     _ = res_block(
#         _,
#         f,
#         kernel_size = kernel_size,
#         dropout=dropout,
#         dropout_type=dropout_type)
#     f = int(f/2)
#     dropout -= dropout_change_per_layer
#
#     _ = upsamp_concat_block(_, e1)
#     _ = res_block(
#         _,
#         f,
#         kernel_size = kernel_size,
#         dropout=dropout,
#         dropout_type=dropout_type)
#
#     # ## classify
#     if nclasses==1:
#         outputs = tf.keras.layers.Conv2D(nclasses, (1, 1), padding="same", activation="sigmoid")(_)
#     else:
#         outputs = tf.keras.layers.Conv2D(nclasses, (1, 1), padding="same", activation="softmax")(_)
#
#     #model creation
#     model = tf.keras.models.Model(inputs=[inputs], outputs=[outputs])
#
#     # Trying for multithreaded prediction
#     # model = keras.Model(inputs=[inputs], outputs=[outputs])
#     # model.make_predict_function()
#     return model
#
#
# #=======================================================================
# def segformer(
#     id2label,
#     num_classes=2,
# ):
#     """
#     https://keras.io/examples/vision/segformer/
#     https://huggingface.co/nvidia/mit-b0
#     """
#
#     label2id = {label: id for id, label in id2label.items()}
#     model_checkpoint = "nvidia/mit-b0"
#
#     model = TFSegformerForSemanticSegmentation.from_pretrained(
#         model_checkpoint,
#         num_labels=num_classes,
#         id2label=id2label,
#         label2id=label2id,
#         ignore_mismatched_sizes=True,
#     )
#     return model
#
#
# ### Model subfunctions ###
# #=======================================================================
# def upsamp_concat_block(x, xskip):
#     """
#     upsamp_concat_block(x, xskip)
#     This function takes an input layer and creates a concatenation of an upsampled version and a residual or 'skip' connection
#     INPUTS:
#         * `xskip`: input keras layer (skip connection)
#         * `x`: input keras layer
#     OPTIONAL INPUTS: None
#     GLOBAL INPUTS: None
#     OUTPUTS:
#         * keras layer, output of the addition between residual convolutional and bottleneck layers
#     """
#     u = tf.keras.layers.UpSampling2D((2, 2))(x)
#
#     return tf.keras.layers.Concatenate()([u, xskip])
#
# #=======================================================================
# def bottleneck_block(x, filters, kernel_size = (2,2), padding="same", strides=1):
#     """
#     bottleneck_block(x, filters, kernel_size = (7,7), padding="same", strides=1)
#
#     This function creates a bottleneck block layer, which is the addition of a convolution block and a batch normalized/activated block
#     INPUTS:
#         * `filters`: number of filters in the convolutional block
#         * `x`: input keras layer
#     OPTIONAL INPUTS:
#         * `kernel_size`=(3, 3): tuple of kernel size (x, y) - this is the size in pixels of the kernel to be convolved with the image
#         * `padding`="same":  see tf.keras.layers.Conv2D
#         * `strides`=1: see tf.keras.layers.Conv2D
#     GLOBAL INPUTS: None
#     OUTPUTS:
#         * keras layer, output of the addition between convolutional and bottleneck layers
#     """
#     conv = tf.keras.layers.Conv2D(filters, kernel_size, padding=padding, strides=strides)(x)
#     conv = conv_block(conv, filters, kernel_size=kernel_size, padding=padding, strides=strides, dropout=0.0,dropout_type="standard")
#
#     bottleneck = tf.keras.layers.Conv2D(filters, kernel_size=(1, 1), padding=padding, strides=strides)(x)
#     bottleneck = batchnorm_act(bottleneck)
#
#     return tf.keras.layers.Add()([conv, bottleneck])
#
# #=======================================================================
# def res_block(x, filters, kernel_size = (7,7), padding="same", strides=1, dropout=0.1,dropout_type="standard"):
#     """
#     res_block(x, filters, kernel_size = (7,7), padding="same", strides=1)
#     This function creates a residual block layer, which is the addition of a residual convolution block and a batch normalized/activated block
#     INPUTS:
#         * `filters`: number of filters in the convolutional block
#         * `x`: input keras layer
#     OPTIONAL INPUTS:
#         * `kernel_size`=(3, 3): tuple of kernel size (x, y) - this is the size in pixels of the kernel to be convolved with the image
#         * `padding`="same":  see tf.keras.layers.Conv2D
#         * `strides`=1: see tf.keras.layers.Conv2D
#     GLOBAL INPUTS: None
#     OUTPUTS:
#         * keras layer, output of the addition between residual convolutional and bottleneck layers
#     """
#     res = conv_block(x, filters, kernel_size=kernel_size, padding=padding, strides=strides, dropout=dropout,dropout_type=dropout_type)
#     res = conv_block(res, filters, kernel_size=kernel_size, padding=padding, strides=1, dropout=dropout,dropout_type=dropout_type)
#
#     bottleneck = tf.keras.layers.Conv2D(filters, kernel_size=(1, 1), padding=padding, strides=strides)(x)
#     bottleneck = batchnorm_act(bottleneck)
#
#     return tf.keras.layers.Add()([bottleneck, res])
#
# #=======================================================================
# def conv_block(x, filters, kernel_size = (7,7), padding="same", strides=1, dropout=0.1,dropout_type="standard"):
#     """
#     conv_block(x, filters, kernel_size = (7,7), padding="same", strides=1)
#     This function applies batch normalization to an input layer, then convolves with a 2D convol layer
#     The two actions combined is called a convolutional block
#
#     INPUTS:
#         * `filters`: number of filters in the convolutional block
#         * `x`:input keras layer to be convolved by the block
#     OPTIONAL INPUTS:
#         * `kernel_size`=(3, 3): tuple of kernel size (x, y) - this is the size in pixels of the kernel to be convolved with the image
#         * `padding`="same":  see tf.keras.layers.Conv2D
#         * `strides`=1: see tf.keras.layers.Conv2D
#     GLOBAL INPUTS: None
#     OUTPUTS:
#         * keras layer, output of the batch normalized convolution
#     """
#
#     # dropout_type =  "standard"
#     # dropout=0.1
#
#     if dropout_type == "spatial":
#         DO = tf.keras.layers.SpatialDropout2D
#     elif dropout_type == "standard":
#         DO = tf.keras.layers.Dropout
#     else:
#         raise ValueError(f"dropout_type must be one of ['spatial', 'standard'], got {dropout_type}")
#
#     if dropout > 0.0:
#         x = DO(dropout)(x)
#
#     conv = batchnorm_act(x)
#     return tf.keras.layers.Conv2D(filters, kernel_size, padding=padding, strides=strides)(conv)
#
# #=======================================================================
# def batchnorm_act(x):
#     """
#     batchnorm_act(x)
#     This function applies batch normalization to a keras model layer, `x`, then a relu activation function
#     INPUTS:
#         * `z` : keras model layer (should be the output of a convolution or an input layer)
#     OPTIONAL INPUTS: None
#     GLOBAL INPUTS: None
#     OUTPUTS:
#         * batch normalized and relu-activated `x`
#     """
#     x = tf.keras.layers.BatchNormalization()(x)
#     return tf.keras.layers.Activation("relu")(x)
#
# ### Losses and Metrics ###
# #=======================================================================
# def mean_iou(y_true, y_pred):
#     """
#     mean_iou(y_true, y_pred)
#     This function computes the mean IoU between `y_true` and `y_pred`: this version is tensorflow (not numpy) and is used by tensorflow training and evaluation functions
#
#     INPUTS:
#         * y_true: true masks, one-hot encoded.
#             * Inputs are B*W*H*N tensors, with
#                 B = batch size,
#                 W = width,
#                 H = height,
#                 N = number of classes
#         * y_pred: predicted masks, either softmax outputs, or one-hot encoded.
#             * Inputs are B*W*H*N tensors, with
#                 B = batch size,
#                 W = width,
#                 H = height,
#                 N = number of classes
#     OPTIONAL INPUTS: None
#     GLOBAL INPUTS: None
#     OUTPUTS:
#         * IoU score [tensor]
#     """
#     yt0 = y_true[:,:,:,0]
#     yp0 = tf.keras.backend.cast(y_pred[:,:,:,0] > 0.5, 'float32')
#     inter = tf.math.count_nonzero(tf.logical_and(tf.equal(yt0, 1), tf.equal(yp0, 1)))
#     union = tf.math.count_nonzero(tf.add(yt0, yp0))
#     iou = tf.where(tf.equal(union, 0), 1., tf.cast(inter/union, 'float32'))
#     return iou
#
# #=======================================================================
# def dice_coef(y_true, y_pred):
#     """
#     dice_coef(y_true, y_pred)
#
#     This function computes the mean Dice coefficient between `y_true` and `y_pred`: this version is tensorflow (not numpy) and is used by tensorflow training and evaluation functions
#
#     INPUTS:
#         * y_true: true masks, one-hot encoded.
#             * Inputs are B*W*H*N tensors, with
#                 B = batch size,
#                 W = width,
#                 H = height,
#                 N = number of classes
#         * y_pred: predicted masks, either softmax outputs, or one-hot encoded.
#             * Inputs are B*W*H*N tensors, with
#                 B = batch size,
#                 W = width,
#                 H = height,
#                 N = number of classes
#     OPTIONAL INPUTS: None
#     GLOBAL INPUTS: None
#     OUTPUTS:
#         * Dice score [tensor]
#     """
#     smooth = 1.
#     y_true_f = tf.reshape(tf.dtypes.cast(y_true, tf.float32), [-1])
#     y_pred_f = tf.reshape(tf.dtypes.cast(y_pred, tf.float32), [-1])
#     intersection = tf.reduce_sum(y_true_f * y_pred_f)
#     return (2. * intersection + smooth) / (tf.reduce_sum(y_true_f) + tf.reduce_sum(y_pred_f) + smooth)
#
# #=======================================================================
# def dice_coef_loss(y_true, y_pred):
#     """
#     dice_coef_loss(y_true, y_pred)
#
#     This function computes the mean Dice loss (1 - Dice coefficient) between `y_true` and `y_pred`: this version is tensorflow (not numpy) and is used by tensorflow training and evaluation functions
#
#     INPUTS:
#         * y_true: true masks, one-hot encoded.
#             * Inputs are B*W*H*N tensors, with
#                 B = batch size,
#                 W = width,
#                 H = height,
#                 N = number of classes
#         * y_pred: predicted masks, either softmax outputs, or one-hot encoded.
#             * Inputs are B*W*H*N tensors, with
#                 B = batch size,
#                 W = width,
#                 H = height,
#                 N = number of classes
#     OPTIONAL INPUTS: None
#     GLOBAL INPUTS: None
#     OUTPUTS:
#         * Dice loss [tensor]
#     """
#     return 1.0 - dice_coef(y_true, y_pred)
#
#
# ################################################################################
# # prediction_imports.py from segmentation_gym                                  #
# ################################################################################
#
# #=======================================================================
# def seg_file2tensor(bigimage, TARGET_SIZE):#, resize):
#     """
#     "seg_file2tensor(f)"
#     This function reads a jpeg image from file into a cropped and resized tensor,
#     for use in prediction with a trained segmentation model
#     INPUTS:
#         * f [string] file name of jpeg
#     OPTIONAL INPUTS: None
#     OUTPUTS:
#         * image [tensor array]: unstandardized image
#     GLOBAL INPUTS: TARGET_SIZE
#     """
#
#     # bigimage = imread(f)#Image.open(f)
#     smallimage = resize(bigimage,(TARGET_SIZE[0], TARGET_SIZE[1]), preserve_range=True, clip=True)
#     #smallimage=bigimage.resize((TARGET_SIZE[1], TARGET_SIZE[0]))
#     smallimage = np.array(smallimage)
#     smallimage = tf.cast(smallimage, tf.uint8)
#
#     w = tf.shape(bigimage)[0]
#     h = tf.shape(bigimage)[1]
#
#     return smallimage, w, h, bigimage
#
#
#
# ################################################################################
# # imports.py from segmentation_gym                                             #
# ################################################################################
#
# #=======================================================================
# def fromhex(n):
#     """ hexadecimal to integer """
#     return int(n, base=16)
#
# #=======================================================================
# def standardize(img, mn=0, mx=1, doRescale=False):
#     #standardization using adjusted standard deviation
#
#     N = np.shape(img)[0] * np.shape(img)[1]
#     s = np.maximum(np.std(img), 1.0/np.sqrt(N))
#     m = np.mean(img)
#
#     img = (img - m) / s
#     if doRescale:
#         img = rescale(img, mn, mx)
#     del m, s, N
#
#     # if np.ndim(img)==2:
#     #     img = np.dstack((img,img,img))
#
#     return img
#
# #===============================================================================
# def rescale( dat,
#              mn,
#              mx):
#     '''
#     rescales an input dat between mn and mx
#     '''
#     m = min(dat.flatten())
#     M = max(dat.flatten())
#     return (mx-mn)*(dat-m)/(M-m)+mn
#
# #=======================================================================
# def label_to_colors(
#     img,
#     mask,
#     alpha,#=128,
#     colormap,#=class_label_colormap, #px.colors.qualitative.G10,
#     color_class_offset,#=0,
#     do_alpha,#=True
#     ):
#     """
#     Take MxN matrix containing integers representing labels and return an MxNx4
#     matrix where each label has been replaced by a color looked up in colormap.
#     colormap entries must be strings like plotly.express style colormaps.
#     alpha is the value of the 4th channel
#     color_class_offset allows adding a value to the color class index to force
#     use of a particular range of colors in the colormap. This is useful for
#     example if 0 means 'no class' but we want the color of class 1 to be
#     colormap[0].
#     """
#
#
#     colormap = [
#         tuple([fromhex(h[s : s + 2]) for s in range(0, len(h), 2)])
#         for h in [c.replace("#", "") for c in colormap]
#     ]
#
#     cimg = np.zeros(img.shape[:2] + (3,), dtype="uint8")
#     minc = np.min(img)
#     maxc = np.max(img)
#
#     for c in range(minc, maxc + 1):
#         cimg[img == c] = colormap[(c + color_class_offset) % len(colormap)]
#
#     cimg[mask==1] = (0,0,0)
#
#     if do_alpha is True:
#         return np.concatenate(
#             (cimg, alpha * np.ones(img.shape[:2] + (1,), dtype="uint8")), axis=2
#         )
#     else:
#         return cimg
#
# #=======================================================================
# def doPredict(model, MODEL, arr, N_DATA_BANDS, NCLASSES, TARGET_SIZE):
#
#     '''
#     '''
#
#     # Read array into a cropped and resized tensor
#     image, w, h, bigimage = seg_file2tensor(arr, TARGET_SIZE)
#
#     # Standardize
#     image = standardize(image.numpy()).squeeze()
#
#     if MODEL == 'segformer':
#         if np.ndim(image)==2:
#             image = np.dstack((image, image, image))
#         image = tf.transpose(image, (2, 0, 1))
#
#     # Do prediction
#     try:
#         if MODEL == 'segformer':
#             softmax_score = model.predict(tf.expand_dims(image, 0), batch_size=1).logits
#         else:
#             softmax_score = model.predict(tf.expand_dims(image, 0), batch_size=1).squeeze()
#     except:
#         if MODEL=='segformer':
#             softmax_score = model.predict(tf.expand_dims(image[:,:,0], 0), batch_size=1).logits
#         else:
#             softmax_score = model.predict(tf.expand_dims(image[:,:,0], 0), batch_size=1).squeeze()
#
#     # softmax_score cannot be float16 so convert to float32
#     softmax_score = softmax_score.astype('float32')
#
#     # Resize to original dimensions
#     if MODEL=='segformer':
#         softmax_score = resize(softmax_score, (1, NCLASSES, TARGET_SIZE[0],TARGET_SIZE[1]), preserve_range=True, clip=True).squeeze()
#         softmax_score = np.transpose(softmax_score, (1,2,0))
#
#     softmax_score = resize(softmax_score, (w, h))
#
#     return softmax_score
