import io
import os
import subprocess
import sys
import time
import unittest

from mlsnippet.utils import timed_wait_proc, exec_proc, TemporaryDirectory


def _strip(text):
    return '\n'.join(l.lstrip()[1:] for l in text.split('\n'))


class TimedWaitTestCase(unittest.TestCase):

    def test_timed_wait_proc(self):
        # test no wait
        wait_time = -time.time()
        proc = subprocess.Popen(
            [sys.executable, '-c', 'import sys; sys.exit(123)'])
        self.assertEquals(123, timed_wait_proc(proc, 1.5))
        wait_time += time.time()
        self.assertLess(wait_time, 1.)

        # test wait
        wait_time = -time.time()
        proc = subprocess.Popen(
            [sys.executable, '-c', 'import sys, time; time.sleep(10); '
                                   'sys.exit(123)'])
        self.assertIsNone(timed_wait_proc(proc, 1.5))
        wait_time += time.time()
        self.assertGreater(wait_time, 1.)
        self.assertLess(wait_time, 3.)


class ExcProcTestCase(unittest.TestCase):

    def test_exec_proc_io(self):
        with TemporaryDirectory() as tempdir:
            with open(os.path.join(tempdir, 'test_payload.txt'), 'wb') as f:
                f.write(b'hello, world!')

            args = ['bash', '-c', 'ls && echo error_message >&2 && exit 123']

            # test stdout only
            stdout = io.BytesIO()
            with exec_proc(args, on_stdout=stdout.write, cwd=tempdir) as proc:
                proc.wait()
            self.assertEquals(123, proc.poll())
            self.assertIn(b'test_payload.txt', stdout.getvalue())
            self.assertNotIn(b'error_message', stdout.getvalue())

            # test separated stdout and stderr
            stdout = io.BytesIO()
            stderr = io.BytesIO()
            with exec_proc(args, on_stdout=stdout.write, on_stderr=stderr.write,
                           cwd=tempdir) as proc:
                proc.wait()
            self.assertEquals(123, proc.poll())
            self.assertIn(b'test_payload.txt', stdout.getvalue())
            self.assertNotIn(b'error_message', stdout.getvalue())
            self.assertNotIn(b'test_payload.txt', stderr.getvalue())
            self.assertIn(b'error_message', stderr.getvalue())

            # test redirect stderr to stdout
            stdout = io.BytesIO()
            with exec_proc(args, on_stdout=stdout.write, stderr_to_stdout=True,
                           cwd=tempdir) as proc:
                proc.wait()
            self.assertEquals(123, proc.poll())
            self.assertIn(b'test_payload.txt', stdout.getvalue())
            self.assertIn(b'error_message', stdout.getvalue())

    def test_exec_proc_kill(self):
        interruptable = _strip('''
        |import time
        |try:
        |  while True:
        |    time.sleep(1)
        |except KeyboardInterrupt:
        |  print("kbd interrupt")
        |print("exited")
        ''')
        non_interruptable = _strip('''
        |import time
        |while True:
        |  try:
        |    time.sleep(1)
        |  except KeyboardInterrupt:
        |    print("kbd interrupt")
        |print("exited")
        ''')

        # test interruptable
        stdout = io.BytesIO()
        with exec_proc(
                ['python', '-u', '-c', interruptable],
                on_stdout=stdout.write) as proc:
            timed_wait_proc(proc, 1.)
        self.assertEquals(b'kbd interrupt\nexited\n', stdout.getvalue())
        self.assertEquals(0, proc.poll())

        # test non-interruptable, give up waiting
        stdout = io.BytesIO()
        with exec_proc(
                ['python', '-u', '-c', non_interruptable],
                on_stdout=stdout.write,
                ctrl_c_timeout=1) as proc:
            timed_wait_proc(proc, 1.)
        self.assertEquals(b'kbd interrupt\n', stdout.getvalue())
        self.assertNotEquals(0, proc.poll())


if __name__ == '__main__':
    unittest.main()
