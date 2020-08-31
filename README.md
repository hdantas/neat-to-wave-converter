Simple script to convert banking extracts from [Neat](https://dashboard.neatcommerce.com/)
into a format [Wave](https://www.waveapps.com/) supports.

## Install
`pipenv run install`

## Run
`pipenv run python run.py`

The script will prompt for the location of the csv file from Neat as well as the latest
transaction you imported into Wave to prevent duplicates. It performs some basic
validation to prevent overwriting files.
