import xml.etree.ElementTree as ET
import pandas as pd
import argparse
import os
from bs4 import BeautifulSoup
import re
import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QLineEdit, QFileDialog, QComboBox,
                             QProgressBar, QTextEdit, QGroupBox, QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt5.QtGui import QFont, QCursor, QDesktopServices

def parse_coordinates(coords_str):
    if not coords_str:
        return {'longitude': None, 'latitude': None, 'altitude': None}
    parts = coords_str.strip().split(',')
    result = {'longitude': None, 'latitude': None, 'altitude': None}
    if len(parts) >= 2:
        try:
            result['longitude'] = float(parts[0].strip())
            result['latitude'] = float(parts[1].strip())
        except:
            pass
    if len(parts) >= 3:
        try:
            result['altitude'] = float(parts[2].strip())
        except:
            pass
    return result

def parse_description_table(description):
    if not description:
        return {}
    try:
        soup = BeautifulSoup(description, 'html.parser')
        table = soup.find('table')
        if not table:
            return parse_plaintext_table(description)
        table_data = {}
        rows = table.find_all('tr')
        for row in rows:
            cols = row.find_all(['th', 'td'])
            if len(cols) >= 2:
                key = cols[0].get_text(strip=True)
                value = cols[1].get_text(strip=True)
                if key:
                    key = re.sub(r'[^\w\s]', '', key).replace(' ', '_').lower()
                    table_data[key] = value
        return table_data
    except:
        return parse_plaintext_table(description)

def parse_plaintext_table(text):
    table_data = {}
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    for line in lines:
        if '|' in line:
            parts = [part.strip() for part in line.split('|') if part.strip()]
            if len(parts) >= 2:
                key = parts[0]
                value = '|'.join(parts[1:])
                key = re.sub(r'[^\w\s]', '', key).replace(' ', '_').lower()
                table_data[key] = value
        elif ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2:
                key = parts[0].strip()
                value = parts[1].strip()
                key = re.sub(r'[^\w\s]', '', key).replace(' ', '_').lower()
                table_data[key] = value
    return table_data

def parse_kml(kml_file, progress_callback=None):
    try:
        with open(kml_file, 'r', encoding='utf-8') as f:
            content = f.read()
        root = ET.fromstring(content)

        data = []
        placemarks = root.findall('.//Placemark') or root.findall('.//{http://www.opengis.net/kml/2.2}Placemark')
        total = len(placemarks)
        for i, p in enumerate(placemarks):
            if progress_callback:
                progress_callback(10 + int(80*i/total))

            name = p.find('name')
            name = name.text.strip() if name is not None and name.text else ""

            desc = p.find('description')
            desc = desc.text if desc is not None else ""
            tdata = parse_description_table(desc)

            coords = ""
            pt = p.find('Point')
            if pt:
                c = pt.find('coordinates')
                if c: coords = c.text.strip()
            cd = parse_coordinates(coords)

            poly = ""
            pl = p.find('Polygon')
            if pl:
                c = pl.find('.//coordinates')
                if c: poly = c.text.strip()

            style = p.find('styleUrl')
            style = style.text.strip() if style is not None and style.text else ""

            ex = {}
            ed = p.find('ExtendedData')
            if ed:
                for d in ed.findall('Data'):
                    k = d.get('name','')
                    v = d.find('value')
                    v = v.text.strip() if v is not None and v.text else ""
                    if k: ex[k] = v

            entry = {'name':name, 'description':desc, 'original_coordinates':coords,
                     'polygon_coordinates':poly, 'style_url':style}
            entry.update(cd)
            entry.update(tdata)
            entry.update(ex)
            data.append(entry)

        if progress_callback: progress_callback(90)
        return data
    except Exception as e:
        return None

def save_to_file(data, output_file, fmt, progress=None):
    if not data: return False
    try:
        df = pd.DataFrame(data)
        if progress: progress(95)
        if fmt in ['xlsx','xls']:
            df.to_excel(output_file, index=False, engine='openpyxl')
        else:
            df.to_csv(output_file, index=False, encoding='utf-8-sig')
        if progress: progress(100)
        return True
    except:
        return False

class Worker(QThread):
    prog = pyqtSignal(int)
    log = pyqtSignal(str)
    done = pyqtSignal(bool, str)
    def __init__(self, i, o, f):
        super().__init__()
        self.i = i
        self.o = o
        self.f = f
    def run(self):
        self.log.emit("开始解析...")
        self.prog.emit(5)
        d = parse_kml(self.i, self.prog.emit)
        if d is None:
            self.done.emit(False, "解析失败")
            return
        self.log.emit(f"解析完成：{len(d)} 条")
        ok = save_to_file(d, self.o, self.f, self.prog.emit)
        self.done.emit(ok, "完成" if ok else "保存失败")

class MainUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KML转Excel/CSV - 情空明月")
        self.setGeometry(100,100,800,600)
        c = QWidget()
        self.setCentralWidget(c)
        lay = QVBoxLayout(c)
        lay.setSpacing(15)
        lay.setContentsMargins(20,20,20,20)

        t = QLabel("KML文件转换工具")
        f = QFont()
        f.setPointSize(16)
        f.setBold(True)
        t.setFont(f)
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)

        cr = QLabel('<a href=https://mooncn.win>作者：情空明月 | 博客：https://mooncn.win</a>')
        cr.setAlignment(Qt.AlignCenter)
        cr.setStyleSheet("color:#06c;font-size:12px;")
        cr.setOpenExternalLinks(True)
        cr.setCursor(QCursor(Qt.PointingHandCursor))
        lay.addWidget(cr)

        g = QGroupBox("文件设置")
        gl = QVBoxLayout(g)
        i_lay = QHBoxLayout()
        i_l = QLabel("输入文件：")
        i_l.setFixedWidth(80)
        self.i_e = QLineEdit()
        i_b = QPushButton("浏览")
        i_b.clicked.connect(self.si)
        i_lay.addWidget(i_l)
        i_lay.addWidget(self.i_e)
        i_lay.addWidget(i_b)
        gl.addLayout(i_lay)

        o_lay = QHBoxLayout()
        o_l = QLabel("输出文件：")
        o_l.setFixedWidth(80)
        self.o_e = QLineEdit()
        o_b = QPushButton("浏览")
        o_b.clicked.connect(self.so)
        o_lay.addWidget(o_l)
        o_lay.addWidget(self.o_e)
        o_lay.addWidget(o_b)
        gl.addLayout(o_lay)

        f_lay = QHBoxLayout()
        f_l = QLabel("格式：")
        f_l.setFixedWidth(80)
        self.f_c = QComboBox()
        self.f_c.addItems(['xlsx','csv','xls'])
        self.f_c.currentTextChanged.connect(self.up)
        f_lay.addWidget(f_l)
        f_lay.addWidget(self.f_c)
        f_lay.addStretch()
        gl.addLayout(f_lay)
        lay.addWidget(g)

        self.pbar = QProgressBar()
        self.pbar.setRange(0,100)
        lay.addWidget(self.pbar)

        lg = QGroupBox("日志")
        ll = QVBoxLayout(lg)
        self.logt = QTextEdit()
        self.logt.setReadOnly(True)
        ll.addWidget(self.logt)
        lay.addWidget(lg)

        bl = QHBoxLayout()
        self.st = QPushButton("开始转换")
        self.st.setStyleSheet("background:#4a0;color:white;padding:8px;font-size:14px;")
        self.st.clicked.connect(self.start)
        cl = QPushButton("清空日志")
        cl.clicked.connect(self.logt.clear)
        ex = QPushButton("退出")
        ex.setStyleSheet("background:#f44336;color:white;padding:8px;font-size:14px;")
        ex.clicked.connect(self.close)
        bl.addStretch()
        bl.addWidget(self.st)
        bl.addWidget(cl)
        bl.addWidget(ex)
        bl.addStretch()
        lay.addLayout(bl)
        self.th = None

    def si(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择KML", "", "KML(*.kml);;All(*.*)")
        if p:
            self.i_e.setText(p)
            if not self.o_e.text():
                b = os.path.splitext(p)[0]
                self.o_e.setText(f"{b}.{self.f_c.currentText()}")
    def so(self):
        f = self.f_c.currentText()
        p, _ = QFileDialog.getSaveFileName(self, "保存", "", f"{f}(*.{f});;All(*.*)")
        if p:
            if not p.endswith(f".{f}"): p += f".{f}"
            self.o_e.setText(p)
    def up(self):
        if self.o_e.text():
            b = os.path.splitext(self.o_e.text())[0]
            self.o_e.setText(f"{b}.{self.f_c.currentText()}")
    def start(self):
        i = self.i_e.text().strip()
        o = self.o_e.text().strip()
        f = self.f_c.currentText()
        if not i or not o:
            QMessageBox.warning(self, "提示", "请选择文件")
            return
        if not os.path.exists(i):
            QMessageBox.critical(self, "错误", "文件不存在")
            return
        self.st.setEnabled(False)
        self.pbar.setValue(0)
        self.logt.append("\n=== 开始 ===")
        self.th = Worker(i,o,f)
        self.th.prog.connect(self.pbar.setValue)
        self.th.log.connect(self.logt.append)
        self.th.done.connect(self.fin)
        self.th.start()
    def fin(self, ok, msg):
        self.st.setEnabled(True)
        self.logt.append(msg)
        if ok:
            QMessageBox.information(self, "成功", msg)
        else:
            QMessageBox.critical(self, "失败", msg)

def main():
    parser = argparse.ArgumentParser(description='将KML文件转换为XLSX或CSV格式，支持解析表格内容和分离经纬度')
    parser.add_argument('input_file', nargs='?', help='输入的KML文件路径（命令行模式）')
    parser.add_argument('-o', '--output', help='输出文件路径（可选）')
    parser.add_argument('-f', '--format', choices=['xlsx', 'csv', 'xls'], default='xlsx', help='输出文件格式，默认为xlsx')
    parser.add_argument('-gui', help='是否启动GUI界面（y/n）', default='y')
    
    args = parser.parse_args()

    if args.gui.lower() == 'y':
        app = QApplication(sys.argv)
        window = MainUI()
        window.show()
        sys.exit(app.exec_())
    else:
        if not args.input_file:
            parser.print_help()
            return
        if not os.path.exists(args.input_file):
            print(f"错误：文件不存在 {args.input_file}")
            return
        
        if args.output:
            output_file = args.output
        else:
            base = os.path.splitext(args.input_file)[0]
            output_file = f"{base}.{args.format}"
        
        print(f"解析中：{args.input_file}")
        data = parse_kml(args.input_file)
        if not data:
            print("解析失败")
            return
        
        ok = save_to_file(data, output_file, args.format)
        if ok:
            print(f"保存成功：{output_file}")
        else:
            print("保存失败")

if __name__ == "__main__":
    main()
