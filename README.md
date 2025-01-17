# Ocean Data Parser

The `ocean data parser` has for primary objectif to streamline the data parsing the different oceanographic data format to a standard xarray object. This object can then easily be used for:
- Data Analysis
- NetCDF conversion
- Data Pipeline Ingestion

## Installation
With miniconda, create a new environement:
```console
conda create --name ocean_parser 
````

Get in the environment:
```console
conda activate ocean_parser
```

Install the present package:
```console
pip install git+https://github.com/HakaiInstitute/ocean-data-parser.git
```


For development, clone locally the package :
```console
git clone git+https://github.com/HakaiInstitute/ocean-data-parser.git
```
and install the package:
```console
cd ocean-data-parser
pip install -e .
```
For development purposes, it is recommended to install the development requirements:
```console
pip install -e ".[dev]"
```

## How to
To parse seabird file:
```python
from ocean_data_parser.read import searbird

PATH_TO_SEABIRD_CNV = "PATH_TO_SEABIRD_CNV"
ds = seabird.cnv(PATH_TO_SEABIRD_CNV)
```
