import xml.etree.ElementTree as ET
import pandas as pd
import argparse
import os
from bs4 import BeautifulSoup
import re

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

def parse_kml(kml_file):
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
        
        for placemark in placemarks:
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
        
        return data
    
    except Exception as e:
        print(f"解析KML文件时出错: {str(e)}")
        return None

def save_to_file(data, output_file, format_type):
    """将数据保存为XLSX或CSV文件"""
    if not data:
        print("没有可保存的数据")
        return False
    
    try:
        # 创建DataFrame
        df = pd.DataFrame(data)
        
        # 保存文件
        if format_type == 'xlsx':
            df.to_excel(output_file, index=False, engine='openpyxl')
        else:  # csv
            df.to_csv(output_file, index=False, encoding='utf-8')
        
        print(f"成功保存到 {output_file}")
        return True
    
    except Exception as e:
        print(f"保存文件时出错: {str(e)}")
        return False

def main():
    # 设置命令行参数
    parser = argparse.ArgumentParser(description='将KML文件转换为XLSX或CSV格式，支持解析表格内容和分离经纬度')
    parser.add_argument('input_file', help='输入的KML文件路径')
    parser.add_argument('-o', '--output', help='输出文件路径（可选）')
    parser.add_argument('-f', '--format', choices=['xlsx', 'csv'], default='xlsx',
                      help='输出文件格式，默认为xlsx')
    
    args = parser.parse_args()
    
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
    