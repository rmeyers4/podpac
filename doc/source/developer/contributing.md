# Contributing

To get a sense of where the project is going, have a look at our [Roadmap](/roadmap)

There are a number of ways to contribute:

* Create new issues for feature requests or to report bugs
* Adding / correcting documentation
* Adding a new unit test
* Contributing a new node that accesses a specific datasource
* Contributing a new node that implements a domain-specific algorithm
* Commenting on issues to help out other users

To contribute:

* Fork the PODPAC repository on github
* Create a new feature branch from the `develop` branch

```bash
git checkout develop  # Assuming you've already checked out and tracked the develop branch
git branch feature/my_new_feature
```

* Make your changes / additions
* Add / modify the docstrings and other documentation
* Write any additional unit tests
* Create a new pull request

At this point we will review your changes, request modifications, and ultimately accept or reject your modifications. 

## Coding style

* Generally try to follow PEP8, but we're not strict about it. 
* Code should be compatible with both Python 2 and 3

### Docstrings

All classes and methods should be properly documented with docstrings.
Docstrings will be used to create the package documentation.

Many IDE's have auto docstring generators to make this process easier. See the [AutoDocstring](https://github.com/KristoforMaynard/SublimeAutoDocstring) sublime text plugin for one example.

Podpac adheres to the [numpy format for docstrings](https://numpydoc.readthedocs.io/en/latest/format.html):

```python
"""A one-line summary that does not use variable names or the
    function name.

    Several sentences providing an extended description. Refer to
    variables using back-ticks, e.g. `var`.

    Parameters
    ----------
    var1 : array_like
        Array_like means all those objects -- lists, nested lists, etc. --
        that can be converted to an array.  We can also refer to
        variables like `var1`.
    var2 : int
        The type above can either refer to an actual Python type
        (e.g. ``int``), or describe the type of the variable in more
        detail, e.g. ``(N,) ndarray`` or ``array_like``.
    long_var_name : {'hi', 'ho'}, optional
        Choices in brackets, default first when optional.

    Returns
    -------
    type
        Explanation of anonymous return value of type ``type``.
    describe : type
        Explanation of return value named `describe`.
    out : type
        Explanation of `out`.
    type_without_description

    Other Parameters
    ----------------
    only_seldom_used_keywords : type
        Explanation
    common_parameters_listed_above : type
        Explanation

    Raises
    ------
    BadException
        Because you shouldn't have done that.

    See Also
    --------
    otherfunc : relationship (optional)
    newfunc : Relationship (optional), which could be fairly long, in which
              case the line wraps here.
    thirdfunc, fourthfunc, fifthfunc

    Notes
    -----
    Notes about the implementation algorithm (if needed).

    This can have multiple paragraphs.

    You may include some math:

    .. math:: X(e^{j\omega } ) = x(n)e^{ - j\omega n}

    And even use a greek symbol like :math:`omega` inline.

    References
    ----------
    Cite the relevant literature, e.g. [1]_.  You may also cite these
    references in the notes section above.

    .. [1] O. McNoleg, "The integration of GIS, remote sensing,
       expert systems and adaptive co-kriging for environmental habitat
       modelling of the Highland Haggis using object-oriented, fuzzy-logic
       and neural-network techniques," Computers & Geosciences, vol. 22,
       pp. 585-588, 1996.

    Examples
    --------
    These are written in doctest format, and should illustrate how to
    use the function.

    >>> a = [1, 2, 3]
    >>> print [x + 3 for x in a]
    [4, 5, 6]
    >>> print "a\n\nb"
    a
    b

    """
```


### Lint

To help adhere to PEP8, we use the `pylint` module. This provides the most benefit if you [configure your text editor or IDE](https://pylint.readthedocs.io/en/latest/user_guide/ide-integration.html)  to run pylint as you develop. To use `pylint` from the command line:

```bash
$ pylint podpac                 # lint the whole module
$ pylint podpac/settings.py     # lint single file
```

Configuration options are specified in `.pylintrc`.

## Testing

We use `pytest` to run unit tests. To run tests, run from the root of the repository:

```
$ pytest
$ pytest -k "TestClass"    # run only the TestClass
```

Configuration options are specified in `setup.cfg`

## Code Coverage

We use `pytest-cov` to monitor code coverage of unit tests. To record coverage while running tests, run:

```bash
$ pytest --cov=podpac --cov-report html podpac   # outputs html coverage
```


## Governance

* We encourage and welcome contributions from the wider community
* Presently, a small group of core developers decide which contributions will be incorporated
    * This is a complex software library
    * Until the library is mature, the interfaces and features need tight control
    * Missing functionality for your project can be implemented as a 3rd party plugin
    * For now, we are trying to be disciplined to avoid feature creep. 
