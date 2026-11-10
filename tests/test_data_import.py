import pytest
from openpyxl import Workbook
from labelate.data_import import read_data


def test_csv_headers_and_values(tmp_path):
    path = tmp_path / 'rows.csv'
    path.write_text('\ufeffSN,extra\n001,ignored\n002,x\n', encoding='utf-8')
    assert read_data(path, ['SN']) == [{'SN': '001'}, {'SN': '002'}]
    with pytest.raises(ValueError, match='Missing variable columns'):
        read_data(path, ['missing'])


def test_xlsx_first_sheet(tmp_path):
    path = tmp_path / 'rows.xlsx'
    book = Workbook()
    book.active.append(['SN', 'value'])
    book.active.append(['001', 0])
    book.create_sheet().append(['ignored'])
    book.save(path)
    assert read_data(path, ['SN', 'value']) == [{'SN': '001', 'value': '0'}]
