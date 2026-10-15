import pytest

import natalia
from natalia import llm


def test_package_imports():
    assert natalia.__version__ == "0.1.0"


def test_llm_stub_is_not_implemented_yet():
    with pytest.raises(NotImplementedError):
        llm.generate("hello")
