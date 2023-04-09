# SPDX-License-Identifier: GPL-2.0+
import ctypes
import numpy as np


class fVar:
    def __new__(cls, obj, *args, **kwargs):
        if obj.is_derived():
            return fDT(obj, *args, **kwargs)
            # TODO: Handle arrays
        elif obj.is_array():
            if obj.is_explicit():
                return fExplicitArr(obj, *args, **kwargs)
            elif obj.is_assumed_size():
                return fAssumedSize(obj, *args, **kwargs)
            elif obj.is_assumed_shape() or obj.is_allocatable() or obj.is_pointer():
                return fAssumedShape(obj, *args, **kwargs)
            else:
                raise TypeError("Unknown array type")
        else:
            if obj.is_char():
                return fStr(obj, *args, **kwargs)
            elif obj.is_complex():
                return fCmplx(obj, *args, **kwargs)
            else:
                return fScalar(obj, *args, **kwargs)


class fParam:
    def __init__(self, obj):
        self.obj = obj

    @property
    def value(self):
        return self.obj.value()

    @value.setter
    def value(self, value):
        raise AttributeError("Parameters can't be altered")

    def __repr__(self):
        return repr(self.value)

    def __str__(self):
        return str(self.value)

    @property
    def module(self):
        return self._value.module


_index_t = ctypes.c_int64
_size_t = ctypes.c_int64


class _bounds14(ctypes.Structure):
    _fields_ = [("stride", _index_t), ("lbound", _index_t), ("ubound", _index_t)]


class _dtype_type(ctypes.Structure):
    _fields_ = [
        ("elem_len", _size_t),
        ("version", ctypes.c_int32),
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


def _make_dt():
    class _fDerivedType(ctypes.Structure):
        pass

    return _fDerivedType


class fVar_t:
    def __init__(self, obj, allobjs=None, cvalue=None):
        self.obj = obj
        self.allobjs = allobjs
        self._cvalue = cvalue

        self.type, self.kind = self.obj.type_kind()

        self._ctype_base = ctype_map(self.type, self.kind)

    @property
    def name(self):
        return self.obj.name

    @property
    def mangled_name(self):
        return self.obj.mangled_name

    @property
    def module(self):
        return self.obj.module

    def ctype_len(self):
        return None

    def from_ctype(self, ct):
        self._cvalue = ct
        return self.value

    def from_address(self, addr):
        self._cvalue = self.ctype().from_address(addr)
        return self._cvalue

    def in_dll(self, lib):
        self._cvalue = self.ctype().in_dll(lib, self.mangled_name)
        return self._cvalue


class fArray_t(fVar_t):
    def _array_check(self, value, know_shape=True):
        value = value.astype(self.obj.dtype())
        shape = self.obj.shape()
        ndim = self.obj.ndim

        if not value.flags["F_CONTIGUOUS"]:
            value = np.asfortranarray(value)

        if value.ndim != ndim:
            raise ValueError(
                f"Wrong number of dimensions, got {value.ndim} expected {ndim}"
            )

        if know_shape:
            if not self.obj.is_allocatable and list(value.shape) != shape:
                raise ValueError(f"Wrong shape, got {value.shape} expected {shape}")

        value = value.ravel(order="F")
        return value

    @property
    def ndim(self):
        return self.obj.ndim

    def _copy_array(self, src, dst, length, size):
        ctypes.memmove(
            dst,
            src,
            length * size,
        )


class fScalar(fVar_t):
    def ctype(self):
        return self._ctype_base

    def from_param(self, param):
        if self._cvalue is None:
            self._cvalue = self.ctype()(param)
        else:
            self._cvalue.value = param
        return self._cvalue

    @property
    def value(self):
        if self.type == "INTEGER":
            return int(self._cvalue.value)
        elif self.type == "REAL":
            if self.kind == 16:
                raise NotImplementedError(f"Quad precision floats not supported yet")
            return float(self._cvalue.value)
        elif self.type == "LOGICAL":
            return self._cvalue.value == 1

    @value.setter
    def value(self, value):
        self.from_param(value)

    def sizeof(self):
        return ctypes.sizeof(self.ctype)

    def __doc__(self):
        return f"{self.type}(KIND={self.kind}) :: {self.name}"


class fCmplx(fVar_t):
    def ctype(self):
        return self._ctype_base

    def from_param(self, param):
        if self._cvalue is None:
            self._cvalue = self.ctype()()

        self._cvalue.real = param.real
        self._cvalue.imag = param.imag
        return self._cvalue

    @property
    def value(self):
        x = self._cvalue

        if self.kind == 16:
            raise NotImplementedError(
                f"Quad precision complex numbers not supported yet"
            )
        return complex(x.real, x.imag)

    @value.setter
    def value(self, value):
        self.from_param(value)

    def sizeof(self):
        return ctypes.sizeof(self.ctype)

    def __doc__(self):
        return f"{self.type}(KIND={self.kind}) :: {self.name}"


class fExplicitArr(fArray_t):
    def ctype(self):
        return self._ctype_base * self.obj.size

    def from_param(self, value):
        if self._cvalue is None:
            self._cvalue = self.ctype()()

        self._value = self._array_check(value)
        self._copy_array(
            self._value.ctypes.data,
            ctypes.addressof(self._cvalue),
            ctypes.sizeof(self._ctype_base),
            self.obj.size,
        )
        return self._cvalue

    @property
    def value(self):
        return np.ctypeslib.as_array(self._cvalue).reshape(self.obj.shape(), order="F")

    @value.setter
    def value(self, value):
        self.from_param(value)

    def __doc__(self):
        return f"{self.type}(KIND={self.kind})({self.obj.shape()}) :: {self.name}"

    def sizeof(self):
        return ctypes.sizeof(self.ctype)

    def len(self):
        return len(self._value)


class fAssumedShape(fArray_t):
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

    def ctype(self):
        return _make_fAlloc15(self.obj.ndim)

    def from_param(self, value):
        if self._cvalue is None:
            self._cvalue = self.ctype()()

        if value is not None:
            self._value = self._array_check(value, False)

            # self._copy_array(
            #     self._value.ctypes.data,
            #     self._cvalue.base_addr,
            #     ctypes.sizeof(self._ctype_base()),
            #     np.size(value)
            # )
            self._cvalue.base_addr = self._value.ctypes.data

            self._cvalue.span = ctypes.sizeof(self._ctype_base())

            strides = []
            shape = np.shape(value)
            for i in range(self.ndim):
                self._cvalue.dims[i].lbound = _index_t(1)
                self._cvalue.dims[i].ubound = _index_t(shape[i])
                strides.append(
                    self._cvalue.dims[i].ubound - self._cvalue.dims[i].lbound + 1
                )

            spans = []
            for i in range(self.ndim):
                spans.append(int(np.prod(strides[:i])))
                self._cvalue.dims[i].stride = _index_t(spans[-1])

            self._cvalue.offset = -np.sum(spans)

        self._cvalue.dtype.elem_len = self._cvalue.span
        self._cvalue.dtype.version = 0
        self._cvalue.dtype.rank = self.ndim
        self._cvalue.dtype.type = self.ftype()
        self._cvalue.dtype.attribute = 0

        return self._cvalue

    @property
    def value(self):
        if self._cvalue.base_addr is None:
            return None

        shape = []
        for i in range(self.obj.ndim):
            shape.append(self._cvalue.dims[i].ubound - self._cvalue.dims[i].lbound + 1)

        shape = tuple(shape)
        size = (np.prod(shape),)

        PTR = ctypes.POINTER(self._ctype_base)
        x_ptr = ctypes.cast(self._cvalue.base_addr, PTR)

        return np.ctypeslib.as_array(x_ptr, shape=size).reshape(shape, order="F")

    @value.setter
    def value(self, value):
        self.from_param(value)

    def __doc__(self):
        return f"{self.type}(KIND={self.kind})(:) :: {self.name}"

    def ftype(self):
        if self.obj.type() == "INTEGER":
            return self._BT_INTEGER
        elif self.obj.type() == "LOGICAL":
            return self._BT_LOGICAL
        elif self.obj.type() == "REAL":
            return self._BT_REAL
        elif self.obj.type() == "COMPLEX":
            return self._BT_COMPLEX

        raise NotImplementedError(
            f"Assumed shape array of type {self.type} and kind {self.kind} not supported yet"
        )

    def __del__(self):
        if self._cvalue is not None:
            self._cvalue.base_addr = None

    def print(self):
        if self._cvalue is None:
            return ""

        print(f"base_addr {self._cvalue.base_addr}")
        print(f"offset {self._cvalue.offset}")
        print(f"dtype")
        print(f"\t elem_len {self._cvalue.dtype.elem_len}")
        print(f"\t version {self._cvalue.dtype.version}")
        print(f"\t rank {self._cvalue.dtype.rank}")
        print(f"\t type {self._cvalue.dtype.type}")
        print(f"\t attribute {self._cvalue.dtype.attribute}")
        print(f"span {self._cvalue.span}")
        print(f"dims {self.ndim}")
        for i in range(self.ndim):
            print(f"\t lbound {self._cvalue.dims[i].lbound}")
            print(f"\t ubound {self._cvalue.dims[i].ubound}")
            print(f"\t stride {self._cvalue.dims[i].stride}")


class fAssumedSize(fArray_t):
    def ctype(self):
        return self._ctype_base * np.prod(self._value.shape)

    def from_param(self, value):
        self._value = self._array_check(value)
        if self._cvalue is None:
            self._cvalue = self.ctype()()

        self._copy_array(
            self._value.ctypes.data,
            ctypes.addressof(self._cvalue),
            ctypes.sizeof(self._ctype_base),
            np.size(value),
        )
        return self._cvalue

    @property
    def value(self):
        return np.ctypeslib.as_array(self._cvalue, shape=np.size(self._value)).reshape(
            self._value.shape, order="F"
        )

    @value.setter
    def value(self, value):
        self.from_param(value)

    def __doc__(self):
        return f"{self.type}(KIND={self.kind})(*) :: {self.name}"

    def sizeof(self):
        return ctypes.sizeof(self.ctype)

    def len(self):
        return len(self._value)

    def ctype_len(self):
        return ctypes.c_int64(self.len())

    @property
    def ndim(self):
        return 1


class fStr(fVar_t):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._len = None

    def ctype(self):
        return self._ctype_base * self.len()

    def from_param(self, value):
        if self.obj.is_deferred_len():
            self._len = len(value)

        if self._cvalue is None:
            self._cvalue = self.ctype()()

        self._value = value

        if hasattr(self._value, "encode"):
            self._value = self._value.encode()

        if len(self._value) > self.len():
            self._value = self._value[: self.len()]
        else:
            self._value = self._value + b" " * (self.len() - len(self._value))

        # self._buf = bytearray(self._value)  # Need to keep hold of the reference
        self._cvalue.value = self._value

        return self._cvalue

    @property
    def value(self):
        try:
            return self._cvalue.value.decode()
        except AttributeError:
            return str(self._cvalue)  # Functions returning str's give us str not bytes

    @value.setter
    def value(self, value):
        self.from_param(value)

    def len(self):
        if self._len is None:
            if self.obj.is_deferred_len():
                self._len = len(self._cvalue)
            else:
                self._len = self.obj.strlen.value
        return self._len

    def ctype_len(self):
        return ctypes.c_int64(self.len())

    def __doc__(self):
        try:
            return f"{self.type}(LEN={self.obj.strlen}) :: {self.name}"
        except AttributeError:
            return f"{self.type}(LEN=:) :: {self.name}"

    def sizeof(self):
        return ctypes.sizeof(self.ctype)


class fDT:
    def __init__(self, obj, allobjs=None, cvalue=None):
        self.obj = obj
        self.allobjs = allobjs
        self._cvalue = cvalue

        # Get obj for derived type spec
        self._dt_obj = self.allobjs[self.obj.sym.ts.class_ref.ref]

    def ctype(self):
        pass

    @property
    def name(self):
        return self.obj.name

    @property
    def mangled_name(self):
        return self.obj.mangled_name

    @property
    def module(self):
        return self.obj.module

    def from_ctype(self, ct):
        self._cvalue = ct
        return self.value

    def from_address(self, addr):
        self._cvalue = self.ctype().from_address(addr)
        return self._cvalue

    def in_dll(self, lib):
        self._cvalue = self.ctype().in_dll(lib, self.mangled_name)
        return self._cvalue

    @property
    def value(self):
        pass

    @value.setter
    def value(self, value):
        self.from_param(value)

    def keys(self):
        pass

    def values(self):
        pass

    def items(self):
        pass

    def __getattr__(self, key):
        if key in self.__dict__:
            return self.__dict__[key]

    def __setattr__(self, key, value):
        self.__dict__[key] = value

    def __contains__(self, key):
        pass


def ctype_map(type, kind):
    if type == "INTEGER":
        if kind == 4:
            return ctypes.c_int32
        elif kind == 8:
            return ctypes.c_int64
        else:
            raise TypeError("Integer type of kind={kind} not supported")
    elif type == "REAL":
        if kind == 4:
            return ctypes.c_float
        elif kind == 8:
            return ctypes.c_double
        elif kind == 16:
            # Although we dont support quad yet we can keep things aligned
            return ctypes.c_ubyte * 16
        else:
            raise TypeError("Float type of kind={kind} not supported")
    elif type == "LOGICAL":
        return ctypes.c_int32
    elif type == "CHARACTER":
        return ctypes.c_char
    elif type == "COMPLEX":
        if kind == 4:
            ct = ctypes.c_float
        elif kind == 8:
            ct = ctypes.c_double
        elif kind == 16:
            ct = ctypes.c_ubyte * 16
        else:
            raise TypeError("Complex type of kind={kind} not supported")

        class complex(ctypes.Structure):
            _fields_ = [
                ("real", ct),
                ("imag", ct),
            ]

        return complex
    else:
        raise TypeError(f"Type={type} and kind={kind} not supported")
