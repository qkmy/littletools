import xml.etree.ElementTree as ET
import pandas as pd
import argparse
import os
from bs4 import BeautifulSoup
import re
import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QLineEdit, QFileDialog, QComboBox,
                             QProgressBar, QTextEdit, QGroupBox, QMessageBox, QCheckBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QIcon

# 原有核心解析函数保持不变
def parse_coordinates(coords_str):
    """解析坐标字符串，提取经度、纬度和海拔"""
    if not coords_str:
        return {'longitude': None, 'latitude': None, 'altitude': None}
    
    # KML坐标格式通常是"经度,纬度,海拔"
    parts = coords_str.split(',')
    result = {'longitude': None, 'latitude': None, 'altitude': None}
    
    if len(parts) >= 2:
        try:
            result['longitude'] = float(parts[0].strip())
            result['latitude'] = float(parts[1].strip())
        except ValueError:
            pass
    
    if len(parts) >= 3:
        try:
            result['altitude'] = float(parts[2].strip())
        except ValueError:
            pass
    
    return result

def parse_description_table(description):
    """解析description中的HTML表格内容"""
    if not description:
        return {}
    
    # 尝试使用BeautifulSoup解析HTML
    try:
        soup = BeautifulSoup(description, 'html.parser')
        table = soup.find('table')
        
        if not table:
            # 检查是否有类似表格的结构（非HTML格式）
            return parse_plaintext_table(description)
        
        # 解析HTML表格
        table_data = {}
        rows = table.find_all('tr')
        
        for row in rows:
            cols = row.find_all(['th', 'td'])
            if len(cols) >= 2:
                key = cols[0].get_text(strip=True)
                value = cols[1].get_text(strip=True)
                if key:  # 只添加有键名的条目
                    # 替换键名中的特殊字符，使其适合作为列名
                    key = re.sub(r'[^\w\s]', '', key).replace(' ', '_').lower()
                    table_data[key] = value
        
        return table_data
    except Exception as e:
        print(f"解析表格时出错: {str(e)}")
        return {}

def parse_plaintext_table(text):
    """解析纯文本格式的表格（如使用|分隔的表格）"""
    table_data = {}
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    for line in lines:
        # 尝试常见的表格分隔符
        if '|' in line:
            parts = [part.strip() for part in line.split('|') if part.strip()]
            if len(parts) >= 2:
                key = parts[0]
                value = '|'.join(parts[1:])
                key = re.sub(r'[^\w\s]', '', key).replace(' ', '_').lower()
                table_data[key] = value
        elif ':' in line:
            # 处理类似"key: value"的格式
            parts = line.split(':', 1)
            if len(parts) == 2:
                key = parts[0].strip()
                value = parts[1].strip()
                key = re.sub(r'[^\w\s]', '', key).replace(' ', '_').lower()
                table_data[key] = value
    
    return table_data

def parse_kml(kml_file, progress_callback=None):
    """解析KML文件并提取地点数据"""
    try:
        tree = ET.parse(kml_file)
        root = tree.getroot()
        
        # KML命名空间
        ns = {'kml': 'http://www.opengis.net/kml/2.2'}
        
        # 存储提取的数据
        data = []
        
        # 查找所有Placemark元素
        placemarks = root.findall('.//kml:Placemark', ns)
        total_placemarks = len(placemarks)
        
        if progress_callback:
            progress_callback(10)  # 初始化进度
        
        for idx, placemark in enumerate(placemarks):
            # 更新进度
            if progress_callback:
                progress = 10 + int((idx / total_placemarks) * 80)
                progress_callback(progress)
            
            # 提取名称
            name_elem = placemark.find('kml:name', ns)
            name = name_elem.text if name_elem is not None else ""
            
            # 提取描述
            desc_elem = placemark.find('kml:description', ns)
            description = desc_elem.text if desc_elem is not None else ""
            
            # 解析描述中的表格内容
            table_data = parse_description_table(description)
            
            # 提取坐标
            coordinates = ""
            point = placemark.find('kml:Point', ns)
            if point is not None:
                coord_elem = point.find('kml:coordinates', ns)
                if coord_elem is not None:
                    coordinates = coord_elem.text.strip()
            
            # 解析经纬度和海拔
            coord_data = parse_coordinates(coordinates)
            
            # 提取多边形坐标（如果有）
            polygon = placemark.find('kml:Polygon', ns)
            polygon_coords = ""
            if polygon is not None:
                coord_elem = polygon.find('.//kml:coordinates', ns)
                if coord_elem is not None:
                    polygon_coords = coord_elem.text.strip()
            
            # 提取样式信息
            style_url_elem = placemark.find('kml:styleUrl', ns)
            style_url = style_url_elem.text if style_url_elem is not None else ""
            
            # 提取扩展数据
            extended_data = {}
            ext_data_elem = placemark.find('kml:ExtendedData', ns)
            if ext_data_elem is not None:
                data_elems = ext_data_elem.findall('kml:Data', ns)
                for data_elem in data_elems:
                    key = data_elem.get('name', '')
                    value_elem = data_elem.find('kml:value', ns)
                    value = value_elem.text if value_elem is not None else ""
                    extended_data[key] = value
            
            # 添加到数据列表
            entry = {
                'name': name,
                'description': description,  # 保留原始描述
                'original_coordinates': coordinates,  # 保留原始坐标字符串
                'polygon_coordinates': polygon_coords,
                'style_url': style_url
            }
            
            # 添加经纬度数据
            entry.update(coord_data)
            
            # 添加表格数据
            entry.update(table_data)
            
            # 添加扩展数据
            entry.update(extended_data)
            
            data.append(entry)
        
        if progress_callback:
            progress_callback(90)  # 解析完成
        
        return data
    
    except Exception as e:
        print(f"解析KML文件时出错: {str(e)}")
        return None

def save_to_file(data, output_file, format_type, progress_callback=None):
    """将数据保存为XLSX或CSV文件"""
    if not data:
        print("没有可保存的数据")
        return False
    
    try:
        # 创建DataFrame
        df = pd.DataFrame(data)
        
        if progress_callback:
            progress_callback(95)  # 准备保存
        
        # 保存文件
        if format_type in ['xls', 'xlsx']:
            df.to_excel(output_file, index=False, engine='openpyxl')
        else:  # csv
            df.to_csv(output_file, index=False, encoding='utf-8')
        
        if progress_callback:
            progress_callback(100)  # 保存完成
        
        print(f"成功保存到 {output_file}")
        return True
    
    except Exception as e:
        print(f"保存文件时出错: {str(e)}")
        return False

# 后台处理线程
class KmlProcessThread(QThread):
    progress_update = pyqtSignal(int)
    log_update = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)
    
    def __init__(self, input_file, output_file, format_type):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.format_type = format_type
    
    def run(self):
        try:
            self.log_update.emit(f"开始解析文件: {self.input_file}")
            self.progress_update.emit(5)
            
            # 解析KML文件
            kml_data = parse_kml(self.input_file, self.progress_update)
            
            if kml_data is None:
                self.finished_signal.emit(False, "KML文件解析失败")
                return
            
            self.log_update.emit(f"解析完成，共提取 {len(kml_data)} 个地点")
            
            # 保存文件
            success = save_to_file(kml_data, self.output_file, self.format_type, self.progress_update)
            
            if success:
                self.finished_signal.emit(True, f"文件已成功保存至: {self.output_file}")
            else:
                self.finished_signal.emit(False, "文件保存失败")
                
        except Exception as e:
            self.log_update.emit(f"处理出错: {str(e)}")
            self.finished_signal.emit(False, f"处理出错: {str(e)}")

# 主窗口界面
class Kml2ExcelGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        # 窗口基本设置
        self.setWindowTitle("KML转Excel/CSV工具 - 情空明月@https://mooncn.win")
        self.setGeometry(100, 100, 800, 600)
        self.setMinimumSize(700, 500)
        
        # 中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题
        title_label = QLabel("KML文件转Excel/CSV工具")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 版权信息
        copyright_label = QLabel("作者：情空明月 | 博客：https://mooncn.win")
        copyright_label.setAlignment(Qt.AlignCenter)
        copyright_label.setStyleSheet("color: #666; font-size: 12px;")
        main_layout.addWidget(copyright_label)
        
        # 文件选择组
        file_group = QGroupBox("文件设置")
        file_layout = QVBoxLayout(file_group)
        
        # 输入文件选择
        input_layout = QHBoxLayout()
        input_label = QLabel("输入KML文件：")
        input_label.setFixedWidth(80)
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("请选择KML文件")
        input_btn = QPushButton("浏览")
        input_btn.clicked.connect(self.select_input_file)
        input_layout.addWidget(input_label)
        input_layout.addWidget(self.input_edit)
        input_layout.addWidget(input_btn)
        file_layout.addLayout(input_layout)
        
        # 输出文件选择
        output_layout = QHBoxLayout()
        output_label = QLabel("输出文件：")
        output_label.setFixedWidth(80)
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("请选择输出文件路径")
        output_btn = QPushButton("浏览")
        output_btn.clicked.connect(self.select_output_file)
        output_layout.addWidget(output_label)
        output_layout.addWidget(self.output_edit)
        output_layout.addWidget(output_btn)
        file_layout.addLayout(output_layout)
        
        # 格式选择
        format_layout = QHBoxLayout()
        format_label = QLabel("输出格式：")
        format_label.setFixedWidth(80)
        self.format_combo = QComboBox()
        self.format_combo.addItems(['xlsx', 'csv', 'xls'])
        self.format_combo.currentTextChanged.connect(self.update_output_ext)
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()
        file_layout.addLayout(format_layout)
        
        main_layout.addWidget(file_group)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)
        
        # 日志输出
        log_group = QGroupBox("处理日志")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("font-family: Consolas; font-size: 10pt;")
        log_layout.addWidget(self.log_text)
        main_layout.addWidget(log_group)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始转换")
        self.start_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px; font-size: 14px;")
        self.start_btn.clicked.connect(self.start_conversion)
        
        self.clear_btn = QPushButton("清空日志")
        self.clear_btn.clicked.connect(self.clear_log)
        
        self.exit_btn = QPushButton("退出")
        self.exit_btn.setStyleSheet("background-color: #f44336; color: white; padding: 8px; font-size: 14px;")
        self.exit_btn.clicked.connect(self.close)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.clear_btn)
        btn_layout.addWidget(self.exit_btn)
        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)
        
        # 初始化状态
        self.thread = None
    
    def select_input_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择KML文件", "", "KML文件 (*.kml);;所有文件 (*.*)"
        )
        if file_path:
            self.input_edit.setText(file_path)
            # 自动填充输出文件名
            if not self.output_edit.text():
                base_name = os.path.splitext(file_path)[0]
                default_output = f"{base_name}.{self.format_combo.currentText()}"
                self.output_edit.setText(default_output)
    
    def select_output_file(self):
        current_format = self.format_combo.currentText()
        filters = f"{current_format.upper()}文件 (*.{current_format});;所有文件 (*.*)"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存文件", "", filters
        )
        if file_path:
            # 确保扩展名正确
            if not file_path.lower().endswith(f".{current_format}"):
                file_path += f".{current_format}"
            self.output_edit.setText(file_path)
    
    def update_output_ext(self):
        """更新输出文件扩展名"""
        if self.output_edit.text():
            current_path = self.output_edit.text()
            base_name = os.path.splitext(current_path)[0]
            new_path = f"{base_name}.{self.format_combo.currentText()}"
            self.output_edit.setText(new_path)
    
    def start_conversion(self):
        """开始转换过程"""
        input_file = self.input_edit.text().strip()
        output_file = self.output_edit.text().strip()
        format_type = self.format_combo.currentText()
        
        # 验证输入
        if not input_file:
            QMessageBox.warning(self, "警告", "请选择输入KML文件！")
            return
        
        if not output_file:
            QMessageBox.warning(self, "警告", "请选择输出文件路径！")
            return
        
        if not os.path.exists(input_file):
            QMessageBox.critical(self, "错误", f"输入文件不存在：{input_file}")
            return
        
        # 禁用按钮防止重复点击
        self.start_btn.setEnabled(False)
        
        # 重置进度条和日志
        self.progress_bar.setValue(0)
        self.log_text.append("\n=== 开始新的转换任务 ===")
        
        # 创建并启动线程
        self.thread = KmlProcessThread(input_file, output_file, format_type)
        self.thread.progress_update.connect(self.update_progress)
        self.thread.log_update.connect(self.update_log)
        self.thread.finished_signal.connect(self.process_finished)
        self.thread.start()
    
    def update_progress(self, value):
        """更新进度条"""
        self.progress_bar.setValue(value)
    
    def update_log(self, message):
        """更新日志"""
        self.log_text.append(message)
        # 自动滚动到最后
        self.log_text.moveCursor(self.log_text.textCursor().End)
    
    def process_finished(self, success, message):
        """处理完成回调"""
        self.start_btn.setEnabled(True)
        self.update_log(f"任务完成：{message}")
        
        if success:
            QMessageBox.information(self, "成功", message)
        else:
            QMessageBox.critical(self, "失败", message)
    
    def clear_log(self):
        """清空日志"""
        self.log_text.clear()
        self.log_text.append("日志已清空")

def main():
    # 设置命令行参数
    parser = argparse.ArgumentParser(description='将KML文件转换为XLSX或CSV格式，支持解析表格内容和分离经纬度')
    parser.add_argument('input_file', nargs='?', help='输入的KML文件路径（命令行模式）')
    parser.add_argument('-o', '--output', help='输出文件路径（可选）')
    parser.add_argument('-f', '--format', choices=['xlsx', 'csv', 'xls'], default='xlsx',
                      help='输出文件格式，默认为xlsx')
    parser.add_argument('-gui', help='是否启动GUI界面（y/n）', default='y')
    
    args = parser.parse_args()
    
    # 判断是否启动GUI
    if args.gui.lower() == 'y':
        # GUI模式
        app = QApplication(sys.argv)
        window = Kml2ExcelGUI()
        window.show()
        sys.exit(app.exec_())
    else:
        # 命令行模式
        if not args.input_file:
            parser.print_help()
            return
        
        # 验证输入文件
        if not os.path.exists(args.input_file):
            print(f"错误：输入文件 '{args.input_file}' 不存在")
            return
        
        # 确定输出文件路径
        if args.output:
            output_file = args.output
        else:
            # 使用输入文件名，更改扩展名
            base_name = os.path.splitext(args.input_file)[0]
            output_file = f"{base_name}.{args.format}"
        
        # 解析KML文件
        print(f"正在解析 {args.input_file}...")
        kml_data = parse_kml(args.input_file)
        
        if kml_data is None:
            return
        
        # 保存到文件
        save_to_file(kml_data, output_file, args.format)

if __name__ == "__main__":
    main()
