"""Map table headers to label variables without mutating the editor."""
from pathlib import Path
from .tableloader import TableLoader


def read_data(path, names):
    names = list(names)
    if not names:
        raise ValueError('Add {variables} in the Label tab before importing data.')
    path = Path(path)
    if path.suffix.lower() not in ('.csv', '.xlsx'):
        raise ValueError('Choose an XLSX or CSV file.')
    loader = TableLoader(str(path), encoding='utf-8-sig', sheet=0)
    try:
        source = iter(loader.rows())
        header = next(source, None)
        if header is None:
            raise ValueError('The file is empty.')
        header = [str(value).strip() if value is not None else '' for value in header]
        populated = [value for value in header if value]
        if len(populated) != len(set(populated)):
            raise ValueError('Column names must be unique.')
        missing = [name for name in names if name not in header]
        if missing:
            raise ValueError('Missing variable columns: ' + ', '.join(missing))
        columns = [(name, header.index(name)) for name in names]
        result = []
        for values in source:
            if all(value is None or value == '' for value in values):
                continue
            row = {}
            for name, index in columns:
                value = values[index] if index < len(values) else None
                row[name] = '' if value is None else str(value)
            result.append(row)
            if len(result) * max(1, len(names)) > 10000:
                raise ValueError('Data table exceeds 10,000 cells.')
        if not result:
            raise ValueError('The file has no data rows.')
        return result
    finally:
        loader.close()
