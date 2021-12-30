# SPDX-License-Identifier: GPL-2.0+
import ctypes
import numpy as np


_index_t = ctypes.c_int64
_size_t = ctypes.c_int64


class _bounds14(ctypes.Structure):
    _fields_ = [("stride", _index_t), ("lbound", _index_t), ("ubound", _index_t)]


class _dtype_type(ctypes.Structure):
    _fields_ = [
        ("elem_len", _size_t),
        ("version", ctypes.c_int),
        ("rank", ctypes.c_byte),
        ("type", ctypes.c_byte),
        ("attribute", ctypes.c_ushort),
    ]


def _make_fAlloc15(ndims):
    class _fAllocArray(ctypes.Structure):
        _fields_ = [
            ("base_addr", ctypes.c_void_p),
            ("offset", _size_t),
            ("dtype", _dtype_type),
            ("span", _index_t),
            ("dims", _bounds14 * ndims),
        ]

    return _fAllocArray


_GFC_DTYPE_RANK_MASK = 0x07
_GFC_DTYPE_TYPE_SHIFT = 3
_GFC_DTYPE_TYPE_MASK = 0x38
_GFC_DTYPE_SIZE_SHIFT = 6

_BT_UNKNOWN = 0
_BT_INTEGER = _BT_UNKNOWN + 1
_BT_LOGICAL = _BT_INTEGER + 1
_BT_REAL = _BT_LOGICAL + 1
_BT_COMPLEX = _BT_REAL + 1
_BT_DERIVED = _BT_COMPLEX + 1
_BT_CHARACTER = _BT_DERIVED + 1
_BT_CLASS = _BT_CHARACTER + 1
_BT_PROCEDURE = _BT_CLASS + 1
_BT_HOLLERITH = _BT_PROCEDURE + 1
_BT_VOID = _BT_HOLLERITH + 1
_BT_ASSUMED = _BT_VOID + 1

_PY_TO_BT = {
    "int": _BT_INTEGER,
    "float": _BT_REAL,
    "bool": _BT_LOGICAL,
    "str": _BT_CHARACTER,
    "bytes": _BT_CHARACTER,
}


class fVar_t:
    def __init__(self, obj):
        self._obj = obj

        self.type, self.kind = self._obj.type_kind()

    def name(self):
        return self._obj.name

    def mangled_name(self):
        return self._obj.mangled_name

    def module(self):
        return self._obj.module

    def _array_check(self, value, know_shape=True):
        value = value.astype(self._obj.dtype())
        shape = self._obj.shape()
        ndim = self._obj.ndim

        if not value.flags["F_CONTIGUOUS"]:
            value = np.asfortranarray(value)

        if value.ndim != ndim:
            raise ValueError(
                f"Wrong number of dimensions, got {value.ndim} expected {ndim}"
            )

        if know_shape:
            if list(value.shape) != shape:
                raise ValueError(f"Wrong shape, got {value.shape} expected {shape}")

        value = value.flatten()
        self.__value = value
        return value

    def from_param(self, value):

        if self._obj.is_optional and value is None:
            return None

        if self._obj.is_array():
            if self._obj.is_explicit():
                value = self._array_check(value)
                ctype = self.ctype(value)(value)

                self.copy_array(ctypes.addressof(value),ctypes.addressof(ctype), self.sizeof(), self.size())

                return ctype
            elif self._obj.is_assumed_size():
                value = self._array_check(value, know_shape=False)
                ctype = self.ctype(value)(value)

                self.copy_array(ctypes.addressof(value), ctypes.addressof(ctype), self.sizeof(), np.size(value))
                
                return ctype

            elif self._obj.is_dummy():
                shape = self._obj.shape()
                ndim = self._obj.ndim()

                ct = _make_fAlloc15(ndim)()

                ct.dtype.elem_len = self.sizeof
                ct.dtype.version = 0
                ct.dtype.ndim = ndim
                ct.dtype.type = self.ftype()
                ct.dtype.attribute = 0
                ct.span = self.sizeof

                ct.offset = 0

                if value is None:
                    return ct
                else:
                    shape = value.shape
                    value = self._array_check(value, False)
                    #ct.base_addr = self.__value.ctypes.data
                    self.copy_array(self.__value.ctypes.data, ct.base_addr, self.sizeof(), np.size(value))

                    strides = []
                    for i in range(ndim):
                        ct.dims[i].lbound = _index_t(1)
                        ct.dims[i].ubound = _index_t(shape[i])
                        strides.append(ct.dims[i].ubound - ct.dims[i].lbound + 1)

                    sumstrides = 0
                    for i in range(ndim):
                        ct.dims[i].stride = _index_t(int(np.product(strides[:i])))
                        sumstrides = sumstrides + ct.dims[i].stride

                    ct.offset = -sumstrides
                    return ct

        if self.type == "INTEGER":
            return self.ctype(value)(value)
        elif self.type == "REAL":
            if self.kind == 16:
                print(
                    f"Object of type {self.type} and kind {self.kind} not supported yet, passing None"
                )
                return self.ctype(value)(None)

            return self.ctype(value)(value)
        elif self.type == "LOGICAL":
            if value:
                return self.ctype(value)(1)
            else:
                return self.ctype(value)(0)
        elif self.type == "CHARACTER":
            strlen = self.len(value).value

            if hasattr(value, "encode"):
                value = value.encode()

            if len(value) > strlen:
                value = value[:strlen]
            else:
                value = value + b" " * (strlen - len(value))

            self._buf = bytearray(value)  # Need to keep hold of the reference

            return self.ctype(value).from_buffer(self._buf)
        elif self.type == "COMPLEX":
            return self.ctype()(value.real, value.imag)

        raise NotImplementedError(f"Object of type {self.type} and kind {self.kind} not supported yet")

    def len(self, value=None):
        if self._obj.is_char():
            if self._obj.is_defered_len():
                l = len(value)
            else:
                l = self._obj.strlen
            
        elif self._obj.is_array():
            if self._obj.is_assumed_size():
                l = np.size(value)
        else:
            l = None
            
        return ctypes.c_int64(l)

    @property
    def ctype(self):
        cb_var = None
        cb_arr = None

        if self.type == "INTEGER":
            if self.kind == 4:

                def callback(*args):
                    return ctypes.c_int32

                cb_var = callback
            elif self.kind == 8:

                def callback(*args):
                    return ctypes.c_int64

                cb_var = callback
        elif self.type == "REAL":
            if self.kind == 4:

                def callback(*args):
                    return ctypes.c_float

                cb_var = callback
            elif self.kind == 8:

                def callback(*args):
                    return ctypes.c_double

                cb_var = callback
            elif self.kind == 16:
                # Although we dont support quad yet we can keep things aligned
                def callback(*args):
                    return ctypes.c_ubyte * 16

                cb_var = callback
        elif self.type == "LOGICAL":

            def callback(*args):
                return ctypes.c_int32

            cb_var = callback
        elif self.type == "CHARACTER":
            try:
                strlen = (
                    self._obj.sym.ts.charlen.value
                )  # We know the string length at compile time

                def callback(*args):
                    return ctypes.c_char * strlen

                cb_var = callback
            except AttributeError:

                def callback(
                    value, *args
                ):  # We de not know the string length at compile time
                    return ctypes.c_char * len(value)

                cb_var = callback
        elif self.type == "COMPLEX":
            if self.kind == 4:

                def callback(*args):
                    class complex(ctypes.Structure):
                        _fields_ = [("real", ctypes.c_float), ("imag", ctypes.c_float)]

                    return complex

                cb_var = callback
            elif self.kind == 8:

                def callback(*args):
                    class complex(ctypes.Structure):
                        _fields_ = [
                            ("real", ctypes.c_double),
                            ("imag", ctypes.c_double),
                        ]

                    return complex

                cb_var = callback
            elif self.kind == 16:

                def callback(*args):
                    class complex(ctypes.Structure):
                        _fields_ = [
                            ("real", ctypes.c_ubyte * 16),
                            ("imag", ctypes.c_ubyte * 16),
                        ]

                    return complex

                cb_var = callback

        if self._obj.is_array():
            if self._obj.is_explicit():

                def callback(*args):
                    return cb_var() * self._obj.size

                cb_arr = callback
            elif self._obj.is_assumed_size():

                def callback(value, *args):
                    return cb_var() * np.size(value)

                cb_arr = callback

            elif self._obj.is_dummy():

                def callback(*args):
                    return _make_fAlloc15(self._ndim())

                cb_arr = callback

        else:
            cb_arr = cb_var

        if cb_arr is None:
            raise NotImplementedError(
                f"Object of type {self.type} and kind {self.kind} not supported yet"
            )
        else:
            return cb_arr

    def from_ctype(self, value):
        if value is None:
            return None

        x = value

        if hasattr(value, "contents"):
            if hasattr(value.contents, "contents"):
                x = value.contents.contents
            else:
                x = value.contents

        if self._obj.is_array():
            if self._obj.is_explicit():
                v = np.zeros(self._obj.shape(), order='F', dtype=self.dtype())

                self.copy_array(ctypes.addressof(value), v.ctypes.data, self.sizeof(), self._obj.size)
        
                return v
            elif self._obj.is_assumed_size():
                v = np.zeros(self._obj.shape(), order='F', dtype=self.dtype())

                self.copy_array(ctypes.addressof(value), v.ctypes.data, self.sizeof(), tuple([len(x)]))
        
                return v

            elif self._obj.is_dummy():
                if x.base_addr is None:
                    return None

                shape = []
                for i in range(self._ndim()):
                    shape.append(x.dims[i].ubound - x.dims[i].lbound + 1)

                shape = tuple(shape)

                v = np.zeros(shape, order='F', dtype=self.dtype())

                self.copy_array(x.base_addr, v.ctypes.data, self.sizeof(), np.size(v))

                return v

        if self.type == "COMPLEX":
            return complex(x.real, x.imag)

        if hasattr(x, "value"):
            if self.type == "INTEGER":
                return x.value
            elif self.type == "REAL":
                if self.kind == 16:
                    raise NotImplementedError(
                        f"Object of type {self.type} and kind {self.kind} not supported yet"
                    )
                return x.value
            elif self.type == "LOGICAL":
                return x.value == 1
            elif self.type == "CHARACTER":
                return "".join([i.decode() for i in x])
            raise NotImplementedError(
                f"Object of type {self.type} and kind {self.kind} not supported yet"
            )
        else:
            return x

    @property
    def __doc__(self):
        return f"{self._obj.head.name}={self.typekind}"

    @property
    def typekind(self):
        if self.type == "INTEGER" or self.type == "REAL":
            return f"{self.type}(KIND={self.kind})"
        elif self.type == "LOGICAL":
            return f"{self.type}"
        elif self.type == "CHARACTER":
            try:
                strlen = (
                    self._obj.sym.ts.charlen.value
                )  # We know the string length at compile time
                return f"{self.type}(LEN={strlen})"
            except AttributeError:
                return f"{self.type}(LEN=:)"

    @property
    def sizeof(self):
        return self.kind()

    def ftype(self):
        if self.type == "INTEGER":
            return _BT_INTEGER
        elif self.type == "LOGICAL":
            return _BT_LOGICAL
        elif self.type == "REAL":
            return _BT_REAL
        elif self.type == "COMPLEX":
            return _BT_COMPLEX

        raise NotImplementedError(f"Array of type {self.type} and kind {self.kind} not supported yet")

    @property
    def sizeof(self):
        return self.kind()

    def set_ctype(self, ctype, value):
        if self._obj.is_array():
            v = self.from_param(value)
            if self._obj.is_explicit():
                # Copy array
                size = np.size(value) 
                length = self.sizeof()
            elif self._obj.is_dummy():
                # Copy just the array descriptor
                size = ctypes.sizeof(v)
                length = 1

            self.copy_array(ctypes.addressof(ctype),ctypes.addressof(v), length, size)

            return
        elif isinstance(ctype, ctypes.Structure):
            for k in ctype.__dir__():
                if not k.startswith("_") and hasattr(value, k):
                    setattr(ctype, k, getattr(value, k))
        else:
            ctype.value = self.from_param(value).value
            return

    def get_from_ctype(self, ctype):
        return self.from_ctype(ctype)


    def copy_array(self, inadd, outadd, length, size):
        ctypes.memmove(
            inadd,
            outadd,
            length*size,
        )
