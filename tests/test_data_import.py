from openpyxl import Workbook
from labelate.data_import import read_data


def test_csv_headers_and_values(tmp_path):
    path = tmp_path / 'rows.csv'
    path.write_text('\ufeffSN,extra\n001,ignored\n002,x\n', encoding='utf-8')
    assert read_data(path, ['SN']) == [{'SN': '001'}, {'SN': '002'}]
    assert read_data(path, ['missing']) == [{'missing': ''}, {'missing': ''}]
    assert read_data(path, ['SN', 'missing']) == [
        {'SN': '001', 'missing': ''}, {'SN': '002', 'missing': ''}]


def test_xlsx_first_sheet(tmp_path):
    path = tmp_path / 'rows.xlsx'
    book = Workbook()
    book.active.append(['SN', 'value'])
    book.active.append(['001', 0])
    book.create_sheet().append(['ignored'])
    book.save(path)
    assert read_data(path, ['SN', 'value']) == [{'SN': '001', 'value': '0'}]


def test_missing_cells_and_blank_rows_are_retained(tmp_path):
    path = tmp_path / 'rows.csv'
    path.write_text('SN,value\n001\n\n,\n002,ok\n', encoding='utf-8')
    assert read_data(path, ['SN', 'value']) == [
        {'SN': '001', 'value': ''}, {'SN': '', 'value': ''},
        {'SN': '', 'value': ''}, {'SN': '002', 'value': 'ok'}]


def test_xlsx_missing_column_preserves_rows(tmp_path):
    path = tmp_path / 'rows.xlsx'
    book = Workbook()
    book.active.append(['SN'])
    book.active.append(['001'])
    book.active.append([None])
    book.active.append(['002'])
    book.save(path)
    assert read_data(path, ['SN', 'missing']) == [
        {'SN': '001', 'missing': ''}, {'SN': '', 'missing': ''},
        {'SN': '002', 'missing': ''}]
