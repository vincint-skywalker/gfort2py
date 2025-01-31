# SPDX-License-Identifier: GPL-2.0+

import os, sys
import ctypes

os.environ["_GFORT2PY_TEST_FLAG"] = "1"

import numpy as np
import gfort2py as gf

import pytest

SO = "./tests/proc_ptrs.so"
MOD = "./tests/proc_ptrs.mod"

x = gf.fFort(SO, MOD)


@pytest.mark.skip
class TestProcPtrsMethods:
    def assertEqual(self, x, y):
        assert x == y

    def test_proc_ptr_ffunc(self):
        x.sub_null_proc_ptr()
        with pytest.raises(AttributeError) as cm:
            y = x.p_func_func_run_ptr(1)

        x.p_func_func_run_ptr = x.func_func_run
        y = x.p_func_func_run_ptr(1)
        self.assertEqual(y.result, 10)
        y = x.p_func_func_run_ptr(2)
        self.assertEqual(y.result, 20)

        y = x.func_proc_ptr(5)
        y2 = x.p_func_func_run_ptr(5)
        self.assertEqual(y.result, y2.result)

    def test_proc_ptr_ffunc2(self):
        x.sub_null_proc_ptr()
        with pytest.raises(AttributeError) as cm:
            y = x.p_func_func_run_ptr2(1)  # Allready set

        x.p_func_func_run_ptr2 = x.func_func_run
        y = x.p_func_func_run_ptr2(10)
        self.assertEqual(y.result, 100)

    def test_proc_update(self):
        x.sub_null_proc_ptr()
        x.p_func_func_run_ptr = x.func_func_run
        y = x.p_func_func_run_ptr(1)
        self.assertEqual(y.result, 10)

        x.p_func_func_run_ptr = x.func_func_run2
        y = x.p_func_func_run_ptr(1)
        self.assertEqual(y.result, 2)

    def test_proc_func_arg(self):
        y = x.func_func_arg_dp(5, x.func_real)
        self.assertEqual(y.result, 500)

        y = x.func_func_arg(x.func_func_run)
        self.assertEqual(y.result, 10)

    def test_proc_proc_func_arg(self):
        x.sub_null_proc_ptr()
        x.p_func_func_run_ptr = x.func_func_run

        y = x.proc_proc_func_arg(x.p_func_func_run_ptr)
        self.assertEqual(y.result, 90)
