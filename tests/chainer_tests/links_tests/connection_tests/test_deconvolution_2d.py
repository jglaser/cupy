import unittest

import numpy

import chainer
from chainer import cuda
from chainer import gradient_check
from chainer import links as L
from chainer import testing
from chainer.testing import attr
from chainer.testing import condition
from chainer.testing import parameterize
from chainer.utils import conv


def _pair(x):
    if hasattr(x, '__getitem__'):
        return x
    return (x, x)


@parameterize(
    {'in_channels': 3, 'out_channels': 2, 'ksize': 3,
     'stride': 2, 'pad': 1, 'nobias': True},
    {'in_channels': 3, 'out_channels': 2, 'ksize': 3,
     'stride': 2, 'pad': 1, 'nobias': False},
)
class TestDeconvolution2D(unittest.TestCase):

    def setUp(self):
        self.link = L.Deconvolution2D(
            self.in_channels, self.out_channels, self.ksize,
            stride=self.stride, pad=self.pad, nobias=self.nobias)
        self.link.W.data[...] = numpy.random.uniform(
            -1, 1, self.link.W.data.shape).astype(numpy.float32)
        if not self.nobias:
            self.link.b.data[...] = numpy.random.uniform(
                -1, 1, self.link.b.data.shape).astype(numpy.float32)

        self.link.zerograds()

        N = 2
        h, w = 3, 2
        kh, kw = _pair(self.ksize)
        out_h = conv.get_deconv_outsize(h, kh, self.stride, self.pad)
        out_w = conv.get_deconv_outsize(w, kw, self.stride, self.pad)
        self.gy = numpy.random.uniform(
            -1, 1, (N, self.out_channels, out_h, out_w)).astype(numpy.float32)
        self.x = numpy.random.uniform(
            -1, 1, (N, self.in_channels, h, w)).astype(numpy.float32)

    def check_forward_consistency(self):
        x_cpu = chainer.Variable(self.x)
        y_cpu = self.link(x_cpu)
        self.assertEqual(y_cpu.data.dtype, numpy.float32)

        self.link.to_gpu()
        x_gpu = chainer.Variable(cuda.to_gpu(self.x))
        y_gpu = self.link(x_gpu)
        self.assertEqual(y_gpu.data.dtype, numpy.float32)

        gradient_check.assert_allclose(y_cpu.data, y_gpu.data.get())

    @attr.cudnn
    @condition.retry(3)
    def test_forward_consistency(self):
        self.check_forward_consistency()

    @attr.gpu
    @condition.retry(3)
    def test_forward_consistency_im2col(self):
        self.link.use_cudnn = False
        self.check_forward_consistency()

    def check_backward(self, x_data, y_grad):
        x = chainer.Variable(x_data)
        y = self.link(x)
        y.grad = y_grad
        y.backward()

        f = lambda: (self.link(x).data,)
        gx, gW = gradient_check.numerical_grad(
            f, (x.data, self.link.W.data), (y.grad,), eps=1e-2)
        if not self.nobias:
            gb, = gradient_check.numerical_grad(
                f, (self.link.b.data,), (y.grad,), eps=1e-2)

        gradient_check.assert_allclose(gx, x.grad)
        gradient_check.assert_allclose(gW, self.link.W.grad)
        if not self.nobias:
            gradient_check.assert_allclose(gb, self.link.b.grad)

    @condition.retry(3)
    def test_backward_cpu(self):
        self.check_backward(self.x, self.gy)

    @attr.cudnn
    @condition.retry(3)
    def test_backward_gpu(self):
        self.link.to_gpu()
        self.check_backward(cuda.to_gpu(self.x), cuda.to_gpu(self.gy))

    @attr.gpu
    @condition.retry(3)
    def test_backward_gpu_im2col(self):
        self.link.use_cudnn = False
        self.link.to_gpu()
        self.check_backward(cuda.to_gpu(self.x), cuda.to_gpu(self.gy))


testing.run_module(__name__, __file__)
