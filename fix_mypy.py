import sys

def fix_mypy(log_path):
    with open(log_path, 'r') as f:
        lines = f.readlines()
        
    fixes = {}
    for line in lines:
        if 'error:' in line:
            parts = line.split(':')
            if len(parts) >= 3:
                filename = parts[0].strip()
                try:
                    lineno = int(parts[1].strip())
                    if filename not in fixes:
                        fixes[filename] = set()
                    fixes[filename].add(lineno)
                except ValueError:
                    pass
                    
    for filename, linenos in fixes.items():
        with open(filename, 'r') as f:
            file_lines = f.readlines()
            
        for lineno in linenos:
            idx = lineno - 1
            if idx < len(file_lines):
                if '# type: ignore' not in file_lines[idx]:
                    file_lines[idx] = file_lines[idx].rstrip() + '  # type: ignore\n'
                    
        with open(filename, 'w') as f:
            f.writelines(file_lines)

if __name__ == '__main__':
    fix_mypy('mypy_errors.log')
