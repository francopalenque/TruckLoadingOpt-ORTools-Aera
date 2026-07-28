# python dependencies
import os
import uuid
import re
import json
import shutil
import time
import pickle
import pandas as pd


class CommonUtility:
    """
    CommonUtility is a class which provide basic functionality for Business Logic service
    """

    @staticmethod
    def get_file_size(file_path, unit="bytes"):
        # calculating the file size
        file_size = os.path.getsize(file_path)
        exponents_map = {'bytes': 0, 'kb': 1, 'mb': 2, 'gb': 3}
        if unit not in exponents_map:
            raise ValueError("Must select from ['bytes', 'kb', 'mb', 'gb']")
        else:
            size = file_size / 1024 ** exponents_map[unit]
            return round(size, 3)