
import os
import random
import unittest
from collections import defaultdict
from contextlib import contextmanager

import six
import pytest
from mock import Mock

from mltoolkit.datafs import *
from mltoolkit.utils import TemporaryDirectory, makedirs
from .standard_checks import StandardFSChecks, LocalFS


class ExceptionsTestCase(unittest.TestCase):

    def test_DataFileNotExist(self):
        e = DataFileNotExist('data file')
        self.assertEquals('data file', e.filename)
        self.assertEquals('Data file not exist: \'data file\'', str(e))

    def test_MetaKeyNotExist(self):
        e = MetaKeyNotExist('data file', 'meta key')
        self.assertEquals('data file', e.filename)
        self.assertEquals('meta key', e.meta_key)
        self.assertEquals('In file \'data file\': '
                          'meta key not exist: \'meta key\'', str(e))


class DataFSCapacityTestCase(unittest.TestCase):

    FLAGS = ('read_data', 'write_data', 'read_meta', 'write_meta',
             'list_meta', 'quick_count', 'random_sample')

    def test_empty(self):
        c = DataFSCapacity()
        c2 = DataFSCapacity()
        for flag in self.FLAGS:
            self.assertFalse(getattr(c, 'can_{}'.format(flag))())
        self.assertEquals('DataFSCapacity()', repr(c))
        self.assertEquals(c, c2)
        self.assertEquals(hash(c), hash(c2))
        for flag in self.FLAGS:
            c3 = DataFSCapacity(getattr(DataFSCapacity, flag.upper()))
            self.assertNotEquals(c, c3)

    def test_single(self):
        for flag in self.FLAGS:
            c = DataFSCapacity(getattr(DataFSCapacity, flag.upper()))
            c2 = DataFSCapacity(getattr(DataFSCapacity, flag.upper()))
            self.assertTrue(getattr(c, 'can_{}'.format(flag))())
            self.assertEquals(c, c2)
            self.assertEquals(hash(c), hash(c2))
            for f in self.FLAGS:
                if f != flag:
                    c3 = DataFSCapacity(getattr(DataFSCapacity, f.upper()))
                    self.assertFalse(getattr(c, 'can_{}'.format(f))())
                    self.assertNotEquals(c, c3)
            self.assertEquals('DataFSCapacity({})'.format(flag), repr(c))

    def test_all(self):
        c = DataFSCapacity(DataFSCapacity.ALL)
        c2 = DataFSCapacity(DataFSCapacity.ALL)
        for flag in self.FLAGS:
            self.assertTrue(getattr(c, 'can_{}'.format(flag))())
        self.assertEquals('DataFSCapacity({})'.format(','.join(self.FLAGS)),
                          repr(c))
        self.assertEquals(c, c2)
        self.assertEquals(hash(c), hash(c2))

    def test_read_write_data(self):
        c = DataFSCapacity(DataFSCapacity.READ_WRITE_DATA)
        self.assertEquals('DataFSCapacity(read_data,write_data)', repr(c))

    def test_read_write_meta(self):
        c = DataFSCapacity(DataFSCapacity.READ_WRITE_META)
        self.assertEquals('DataFSCapacity(read_meta,write_meta)', repr(c))


class DataFSTestCase(unittest.TestCase):

    def test_props(self):
        self.assertFalse(DataFS().strict)
        self.assertTrue(DataFS(strict=True).strict)

    def test_as_flow(self):
        class DummyFS(DataFS):
            def __init__(self):
                super(DummyFS, self).__init__()
                self.clone = Mock(return_value=cloned)
                self._capacity = DataFSCapacity(DataFSCapacity.ALL)

            @property
            def capacity(self):
                return self._capacity

        cloned = object()
        fs = DummyFS()

        # as_flow with default args
        flow = fs.as_flow(123)
        self.assertIsInstance(flow, DataFSFlow)
        self.assertIs(cloned, flow.fs)
        self.assertEquals(123, flow.batch_size)
        self.assertTrue(flow.with_names)
        self.assertIsNone(flow.meta_keys)
        self.assertFalse(flow.is_shuffled)
        self.assertFalse(flow.skip_incomplete)
        self.assertIsNone(flow.names_pattern)

        # as_flow with customized args
        flow = fs.as_flow(123, with_names=False, meta_keys=['a', 'b'],
                          shuffle=True, skip_incomplete=True,
                          names_pattern='.*\.jpg$')
        self.assertIsInstance(flow, DataFSFlow)
        self.assertIs(cloned, flow.fs)
        self.assertEquals(123, flow.batch_size)
        self.assertFalse(flow.with_names)
        self.assertEquals(('a', 'b'), flow.meta_keys)
        self.assertTrue(flow.is_shuffled)
        self.assertTrue(flow.skip_incomplete)
        self.assertTrue(hasattr(flow.names_pattern, 'match'))
        self.assertEquals('.*\.jpg$', flow.names_pattern.pattern)

        # as_random_flow with default args
        flow = fs.as_random_flow(123)
        self.assertIsInstance(flow, DataFSRandomFlow)
        self.assertIs(cloned, flow.fs)
        self.assertEquals(123, flow.batch_size)
        self.assertTrue(flow.with_names)
        self.assertIsNone(flow.meta_keys)
        self.assertFalse(flow.skip_incomplete)

        # as_random_flow with customized args
        flow = fs.as_random_flow(123, with_names=False, meta_keys=['a', 'b'],
                                 skip_incomplete=True)
        self.assertIsInstance(flow, DataFSRandomFlow)
        self.assertIs(cloned, flow.fs)
        self.assertEquals(123, flow.batch_size)
        self.assertFalse(flow.with_names)
        self.assertEquals(('a', 'b'), flow.meta_keys)
        self.assertTrue(flow.skip_incomplete)

        # as_random_flow with capacity check
        fs._capacity = DataFSCapacity(
            DataFSCapacity.ALL & ~DataFSCapacity.RANDOM_SAMPLE)
        with pytest.raises(UnsupportedOperation):
            _ = fs.as_random_flow(123)


class ExtendedLocalFS(LocalFS):
    """
    Extended :class:`LocalFS`, for testing inherited methods from
    :class:`DataFS`.
    """

    def __init__(self, *args, **kwargs):
        super(ExtendedLocalFS, self).__init__(*args, **kwargs)
        self._file_meta_dict = defaultdict(lambda: {})
        self._capacity = DataFSCapacity(DataFSCapacity.ALL)

    def sample_names(self, n_samples):
        return random.choices(self.list_names(), k=n_samples)

    def list_meta(self, filename):
        return list(self._file_meta_dict[filename].keys())

    def get_meta(self, filename, meta_keys):
        meta_dict = self._file_meta_dict[filename]
        return [meta_dict.get(k, None) for k in meta_keys]

    def put_meta(self, filename, meta_dict=None, **meta_dict_kwargs):
        merged = {}
        if meta_dict:
            merged.update(dict(meta_dict))
        if meta_dict_kwargs:
            merged.update(meta_dict_kwargs)
        self._file_meta_dict[filename].update(merged)

    def clear_meta(self, filename):
        self._file_meta_dict[filename] = {}


class ExtendedLocalFSTestCase(unittest.TestCase, StandardFSChecks):

    def get_snapshot(self, fs):
        ret = {}
        for name in iter_files(fs.root_dir):
            with open(os.path.join(fs.root_dir, name), 'rb') as f:
                cnt = f.read()
            meta_dict = fs._file_meta_dict[name]
            if meta_dict:
                ret[name] = (cnt, meta_dict)
            else:
                ret[name] = (cnt,)
        return ret

    @contextmanager
    def temporary_fs(self, snapshot=None):
        with TemporaryDirectory() as tempdir:
            if snapshot:
                for filename, (content,) in six.iteritems(snapshot):
                    file_path = os.path.join(tempdir, filename)
                    file_dir = os.path.split(file_path)[0]
                    makedirs(file_dir, exist_ok=True)
                    with open(file_path, 'wb') as f:
                        f.write(content)
            yield ExtendedLocalFS(tempdir)

    def test_standard(self):
        self.run_standard_checks(DataFSCapacity.ALL)


if __name__ == '__main__':
    unittest.main()