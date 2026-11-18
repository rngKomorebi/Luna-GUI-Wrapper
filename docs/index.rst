.. Luna GUI Wrapper documentation master file

Luna GUI Wrapper
================

A browse-and-batch Qt front end for ASI Luna's ``tpx3dump`` and ``tpx4dump``:
queue Timepix3 ``.tpx3`` or Timepix4 ``.tpx4`` files, get sensibly named
``.hdf5`` files, and inspect the results.

.. important::

   Luna is **not included**. This is a GUI wrapper around the ``tpx3dump`` /
   ``tpx4dump`` command-line tools from your own licensed ASI Luna
   installation, which it runs unmodified as subprocesses. It cannot process
   a single raw file without one.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   intro
   installation
   usage
   inspect
   tdc
   timewalk
   troubleshooting
   contribute
   license

.. toctree::
   :maxdepth: 2
   :caption: API (Qt-free core):

   modules

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
