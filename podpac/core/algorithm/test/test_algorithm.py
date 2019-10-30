from __future__ import division, unicode_literals, print_function, absolute_import

import pytest
import numpy as np
from collections import OrderedDict

import podpac
from podpac.core.algorithm.algorithm import Algorithm, Arange, CoordData, SinCoords, Arithmetic, Generic


class TestAlgorithm(object):
    def test_not_implemented(self):
        node = Algorithm()
        c = podpac.Coordinates([])
        with pytest.raises(NotImplementedError):
            node.eval(c)

    def test_base_definition(self):
        # note: any algorithm node with attrs and inputs would be fine here
        setting = podpac.settings["ALLOW_PYTHON_EVAL_EXEC"]
        podpac.settings.set_allow_python_eval_exec(True)
        node = Arithmetic(A=Arange(), B=Arange(), eqn="A+B")
        d = node.base_definition

        assert isinstance(d, OrderedDict)
        assert "node" in d
        assert "attrs" in d

        # base (node, params)
        assert d["node"] == "core.algorithm.algorithm.Arithmetic"
        assert d["attrs"]["eqn"] == "A+B"

        # inputs
        assert "inputs" in d
        assert isinstance(d["inputs"], dict)
        assert "A" in d["inputs"]
        assert "B" in d["inputs"]

        # TODO value of d['inputs']['A'], etc
        podpac.settings.set_allow_python_eval_exec(setting)


class TestArange(object):
    def test_Arange(self):
        coords = podpac.Coordinates([[0, 1, 2], [0, 1, 2, 3, 4]], dims=["lat", "lon"])
        node = Arange()
        output = node.eval(coords)
        assert output.shape == coords.shape


class TestCoordData(object):
    def test_CoordData(self):
        coords = podpac.Coordinates([[0, 1, 2], [0, 1, 2, 3, 4]], dims=["lat", "lon"])

        node = CoordData(coord_name="lat")
        np.testing.assert_array_equal(node.eval(coords), coords.coords["lat"])

        node = CoordData(coord_name="lon")
        np.testing.assert_array_equal(node.eval(coords), coords.coords["lon"])

    def test_invalid_dimension(self):
        coords = podpac.Coordinates([[0, 1, 2], [0, 1, 2, 3, 4]], dims=["lat", "lon"])
        node = CoordData(coord_name="time")
        with pytest.raises(ValueError):
            node.eval(coords)


class TestSinCoords(object):
    def test_SinCoords(self):
        coords = podpac.Coordinates(
            [podpac.crange(-90, 90, 1.0), podpac.crange("2018-01-01", "2018-01-30", "1,D")], dims=["lat", "time"]
        )
        node = SinCoords()
        output = node.eval(coords)
        assert output.shape == coords.shape


class TestArithmetic(object):
    def test_Arithmetic(self):
        coords = podpac.Coordinates([podpac.crange(-90, 90, 1.0), podpac.crange(-180, 180, 1.0)], dims=["lat", "lon"])
        sine_node = SinCoords()
        setting = podpac.settings["ALLOW_PYTHON_EVAL_EXEC"]
        podpac.settings.set_allow_python_eval_exec(True)
        node = Arithmetic(A=sine_node, B=sine_node, eqn="2*abs(A) - B + {offset}", params={"offset": 1})
        output = node.eval(coords)

        a = sine_node.eval(coords)
        b = sine_node.eval(coords)
        np.testing.assert_allclose(output, 2 * abs(a) - b + 1)
        podpac.settings.set_allow_python_eval_exec(setting)

    def test_missing_equation(self):
        setting = podpac.settings["ALLOW_PYTHON_EVAL_EXEC"]
        podpac.settings.set_allow_python_eval_exec(True)
        sine_node = SinCoords()
        with pytest.raises(ValueError):
            node = Arithmetic(A=sine_node, B=sine_node)
        podpac.settings.set_allow_python_eval_exec(setting)


class TestGeneric(object):
    def test_Generic_allowed(self):
        setting = podpac.settings["ALLOW_PYTHON_EVAL_EXEC"]
        podpac.settings.set_allow_python_eval_exec(True)
        coords = podpac.Coordinates([podpac.crange(-90, 90, 1.0), podpac.crange(-180, 180, 1.0)], dims=["lat", "lon"])
        a = SinCoords()
        b = Arange()
        node = Generic(code="import numpy as np\noutput = np.minimum(a,b)", inputs={"a": a, "b": b})
        output = node.eval(coords)

        a = node.eval(coords)
        b = node.eval(coords)
        np.testing.assert_allclose(output, np.minimum(a, b))
        podpac.settings.set_allow_python_eval_exec(setting)

    def test_Generic_not_allowed(self):
        setting = podpac.settings["ALLOW_PYTHON_EVAL_EXEC"]
        podpac.settings.set_allow_python_eval_exec(False)
        a = SinCoords()
        b = Arange()
        with pytest.raises(PermissionError):
            node = Generic(code="import numpy as np\noutput = np.minimum(a,b)", inputs={"a": a, "b": b})
