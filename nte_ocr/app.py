from dataclasses import asdict, replace
import json
import queue
import sys
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import cv2
import numpy as np

from . import __version__
from .paths import application_directory
from .rules import STAT_LABELS, default_rules, describe_rule, decide, parse_affix
from .runner import Options, Runner, Stopped
from .ui_rules import RuleEditor
from .vision import Reader, RecognitionError, find_panel
from .windows import WindowError, is_game, key_down, list_windows, restart_elevated

ROOT = application_directory()


class App:
    def __init__(self, root, *, auto_start=False):
        self.root = root
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.busy = False
        self.closing = False
        self.reader = None
        self.auto_start = auto_start
        self.windows = []
        self.editor = None
        self.key_states = {0x77: False, 0x78: False}
        root.title(f'ReelKeeper {__version__} · 驱动块筛选助手')
        root.geometry('1180x910')
        root.minsize(1080, 850)
        root.configure(bg='#f4f6fa')
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI', 10))
        style.configure('TFrame', background='#f4f6fa')
        style.configure('TLabel', background='#f4f6fa', foreground='#263449')
        style.configure('TLabelframe', background='#f4f6fa')
        style.configure('TLabelframe.Label', background='#f4f6fa', foreground='#263449')
        style.configure('TCheckbutton', background='#f4f6fa')
        style.configure('TButton', padding=(12, 7))
        style.configure('Primary.TButton', background='#285fcb', foreground='white')
        style.map('Primary.TButton', background=[('active', '#1e4ca6'), ('disabled', '#bdc9dc')])
        style.configure('Treeview', rowheight=32, font=('Microsoft YaHei UI', 9))
        self.status = tk.StringVar(value='就绪 · F8 开始 / F9 停止')
        self.model_status = tk.StringVar(value='PP-OCRv6 Tiny · 正在准备模型…')
        self.mode = tk.StringVar(value='自动循环')
        self.rounds = tk.StringVar(value='1')
        self.dry_run = tk.BooleanVar(value=False)
        self.rules = list(default_rules())
        self.setting_controls = []
        self.records = {}
        self.kept = self.discarded = self.target = self.completed_rounds = 0
        self.summary = tk.StringVar(value='尚未开始')
        self.rule_summary = tk.StringVar()
        self.cost = tk.StringVar()
        self.detail = tk.StringVar(value='选中一行，查看判定原因和完整词条。')
        self.build()
        self.load_settings()
        self.refresh_rules()
        self.mode.trace_add('write', lambda *_: self.update_run_settings())
        self.rounds.trace_add('write', lambda *_: self.update_run_settings())
        self.update_run_settings()
        self.refresh_windows()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(70, self.poll)
        root.after(100, self.preload_reader)

    def build(self):
        outer = ttk.Frame(self.root, padding=22)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='ReelKeeper', font=('Microsoft YaHei UI', 22, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='读副属性 → 按规则筛选 → 保留的锁定，其余标记丢弃',
                  foreground='#637189').pack(anchor='w', pady=(3, 0))
        ttk.Label(outer, textvariable=self.model_status,
                  foreground='#637189', font=('Microsoft YaHei UI', 9)).pack(anchor='w', pady=(3, 14))
        window_row = ttk.Frame(outer)
        window_row.pack(fill='x')
        ttk.Label(window_row, text='游戏窗口').pack(side='left', padx=(0, 10))
        self.window_box = ttk.Combobox(window_row, state='readonly')
        self.setting_controls.append((self.window_box, 'readonly'))
        self.window_box.pack(side='left', fill='x', expand=True)
        self.refresh_button = ttk.Button(window_row, text='重新检测', command=self.refresh_windows)
        self.refresh_button.pack(side='left', padx=(10, 0))
        self.setting_controls.append((self.refresh_button, 'normal'))
        controls = ttk.Frame(outer)
        controls.pack(fill='x', pady=14)
        rules = ttk.LabelFrame(controls, text='1 · 设置保留规则', padding=12)
        rules.pack(side='left', fill='both', expand=True, padx=(0, 12))
        ttk.Label(rules, text='满足任意一条启用的规则就保留；都不满足才标记丢弃。').pack(anchor='w')
        rule_list = ttk.Frame(rules)
        rule_list.pack(fill='x', pady=8)
        self.rule_table = ttk.Treeview(rule_list, columns=('enabled', 'name', 'count'), show='headings', height=3)
        for column, title, width in [('enabled', '状态', 65), ('name', '规则名称', 260), ('count', '至少满足', 80)]:
            self.rule_table.heading(column, text=title)
            self.rule_table.column(column, width=width, minwidth=55)
        self.rule_table.pack(side='left', fill='x', expand=True)
        scroll = ttk.Scrollbar(rule_list, orient='vertical', command=self.rule_table.yview)
        scroll.pack(side='right', fill='y')
        self.rule_table.configure(yscrollcommand=scroll.set)
        self.rule_table.bind('<<TreeviewSelect>>', self.show_rule)
        self.rule_table.bind('<Double-1>', lambda _: self.edit_rule())
        buttons = ttk.Frame(rules)
        buttons.pack(fill='x')
        for label, callback in [('添加', lambda: self.edit_rule(new=True)), ('编辑', self.edit_rule),
                                ('启用 / 停用', self.toggle_rule), ('删除', self.delete_rule),
                                ('恢复默认', self.restore_rules)]:
            button = ttk.Button(buttons, text=label, command=callback, padding=(8, 4))
            button.pack(side='left', padx=(0, 5))
            self.setting_controls.append((button, 'normal'))
        ttk.Label(rules, textvariable=self.rule_summary, wraplength=620, justify='left',
                  foreground='#637189', font=('Microsoft YaHei UI', 9)).pack(anchor='w', pady=(8, 0))
        run_box = ttk.LabelFrame(controls, text='运行设置', padding=12)
        run_box.pack(side='left', fill='both', ipadx=4)
        self.mode_box = ttk.Combobox(run_box, values=('自动循环', '只筛选当前十连结果'),
                                     textvariable=self.mode, state='readonly', width=24)
        self.mode_box.pack(fill='x')
        self.setting_controls.append((self.mode_box, 'readonly'))
        round_row = ttk.Frame(run_box)
        round_row.pack(fill='x', pady=10)
        ttk.Label(round_row, text='处理').pack(side='left')
        self.round_spin = ttk.Spinbox(round_row, from_=1, to=999, textvariable=self.rounds, width=5)
        self.round_spin.pack(side='left', padx=8)
        self.setting_controls.append((self.round_spin, 'normal'))
        ttk.Label(round_row, text='轮，每轮 10 件').pack(side='left')
        preview = ttk.Checkbutton(run_box, text='只看结果，不修改标记', variable=self.dry_run, command=self.preview_changed)
        preview.pack(anchor='w')
        self.setting_controls.append((preview, 'normal'))
        ttk.Label(run_box, textvariable=self.cost, wraplength=280, foreground='#637189',
                  font=('Microsoft YaHei UI', 9)).pack(anchor='w', pady=(10, 0))
        ttk.Label(run_box, text='自动循环可从投币、动画或结果页接续。\n每轮结束确认回到投币页。',
                  foreground='#637189', font=('Microsoft YaHei UI', 9)).pack(anchor='w', pady=(8, 0))
        action_row = ttk.Frame(outer)
        action_row.pack(fill='x', pady=(0, 10))
        self.start_button = ttk.Button(action_row, text='开始筛选  F8', command=self.start, style='Primary.TButton')
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(action_row, text='停止  F9', command=self.stop, state='disabled')
        self.stop_button.pack(side='left', padx=8)
        self.image_button = ttk.Button(action_row, text='用截图试算', command=self.open_image)
        self.image_button.pack(side='left')
        save_button = ttk.Button(action_row, text='保存设置', command=self.save_settings)
        save_button.pack(side='left', padx=8)
        self.setting_controls.append((save_button, 'normal'))
        ttk.Label(action_row, text='开始时自动保存', foreground='#637189', font=('Microsoft YaHei UI', 9)).pack(side='left')
        ttk.Label(outer, textvariable=self.status, foreground='#225bd6').pack(anchor='w', pady=(0, 8))
        self.progress = ttk.Progressbar(outer, mode='determinate')
        self.progress.pack(fill='x')
        ttk.Label(outer, textvariable=self.summary, foreground='#637189').pack(anchor='w', pady=(5, 10))
        notebook = ttk.Notebook(outer)
        notebook.pack(fill='both', expand=True)
        result_tab, log_tab = ttk.Frame(notebook, padding=8), ttk.Frame(notebook, padding=8)
        notebook.add(result_tab, text='筛选结果')
        notebook.add(log_tab, text='运行记录')
        table_frame = ttk.Frame(result_tab)
        table_frame.pack(fill='both', expand=True)
        self.table = ttk.Treeview(table_frame, columns=('item', 'action', 'rule', 'matched', 'affixes'),
                                 show='headings', height=5)
        for column, title, width in [('item', '轮 / 件', 65), ('action', '处理结果', 150), ('rule', '命中规则', 160),
                                      ('matched', '命中保留词条', 250), ('affixes', '完整副属性', 500)]:
            self.table.heading(column, text=title)
            self.table.column(column, width=width, minwidth=50)
        self.table.grid(row=0, column=0, sticky='nsew')
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        yscroll = ttk.Scrollbar(table_frame, orient='vertical', command=self.table.yview)
        yscroll.grid(row=0, column=1, sticky='ns')
        xscroll = ttk.Scrollbar(table_frame, orient='horizontal', command=self.table.xview)
        xscroll.grid(row=1, column=0, sticky='ew')
        self.table.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.table.bind('<<TreeviewSelect>>', self.show_record)
        self.table.tag_configure('keep', foreground='#18764b')
        self.table.tag_configure('discard', foreground='#9a5438')
        ttk.Label(result_tab, textvariable=self.detail, wraplength=1040, justify='left',
                  foreground='#45546c', font=('Microsoft YaHei UI', 9)).pack(anchor='w', pady=(8, 0))
        self.log = scrolledtext.ScrolledText(log_tab, height=6, state='disabled', font=('Microsoft YaHei UI', 9),
                                             relief='flat', bg='#e9edf5', fg='#45546c')
        self.log.pack(fill='both', expand=True)
        ttk.Label(outer, text='游戏保持打开且未最小化。鼠标保持原位，游戏窗口可能短暂闪动。丢弃只打标，不分解。',
                  foreground='#637189', font=('Microsoft YaHei UI', 9)).pack(anchor='w', pady=(10, 0))

    def refresh_rules(self, selected=0):
        self.rule_table.delete(*self.rule_table.get_children())
        for index, rule in enumerate(self.rules):
            self.rule_table.insert('', 'end', iid=str(index), values=(
                '已启用' if rule.enabled else '已停用', rule.name, f'{rule.minimum_matches} 条'))
        if self.rules:
            self.rule_table.selection_set(str(min(selected, len(self.rules)-1)))
        self.show_rule()

    def selected_rule(self):
        selected = self.rule_table.selection()
        return int(selected[0]) if selected else None

    def show_rule(self, _=None):
        index = self.selected_rule()
        self.rule_summary.set(describe_rule(self.rules[index]) if index is not None else '请添加一条保留规则。')

    def edit_rule(self, *, new=False):
        if self.busy:
            return
        index = None if new else self.selected_rule()
        if index is None and not new:
            return

        def saved(rule):
            if index is None:
                self.rules.append(rule)
            else:
                self.rules[index] = rule
            self.refresh_rules(len(self.rules)-1 if index is None else index)
            self.status.set('规则已更新；开始时自动保存，也可点击“保存设置”')

        self.editor = RuleEditor(self.root, None if new else self.rules[index], saved)

    def toggle_rule(self):
        index = self.selected_rule()
        if not self.busy and index is not None:
            self.rules[index] = replace(self.rules[index], enabled=not self.rules[index].enabled)
            self.refresh_rules(index)

    def delete_rule(self):
        index = self.selected_rule()
        if not self.busy and index is not None:
            del self.rules[index]
            self.refresh_rules(index)

    def restore_rules(self):
        if not self.busy:
            self.rules = list(default_rules())
            self.refresh_rules()

    def preview_changed(self):
        if self.dry_run.get():
            self.mode.set('只筛选当前十连结果')
        self.update_run_settings()

    def update_run_settings(self):
        current = self.mode.get() == '只筛选当前十连结果'
        self.round_spin.configure(state='disabled' if self.busy or current else 'normal')
        self.mode_box.configure(state='disabled' if self.busy or self.dry_run.get() else 'readonly')
        if current:
            self.cost.set('只处理当前 10 件，不投币。\n预览仍会选中读取，结束后回到投币页。' if self.dry_run.get()
                          else '只处理当前 10 件，不投币。')
        else:
            try:
                rounds = int(self.rounds.get())
                text = f'最多消耗 {rounds*600:,} 金币。已有结果计作第一轮。' if 1 <= rounds <= 999 else '轮数须为 1～999。'
            except ValueError:
                text = '请输入处理轮数。'
            self.cost.set(text)

    def show_record(self, _=None):
        selection = self.table.selection()
        if selection:
            record = self.records[selection[0]]
            self.detail.set(record['reason'] + '\n' + ' / '.join(a['raw'] for a in record['affixes']))

    def update_progress(self):
        count = self.kept + self.discarded
        self.progress.configure(maximum=max(self.target, 1), value=count)
        self.summary.set(f'已读 {count}/{self.target} 件  ·  保留 {self.kept} 件  ·  不保留 {self.discarded} 件'
                         f'  ·  已返回投币页 {self.completed_rounds} 轮')

    def set_busy(self, busy):
        self.busy = busy
        for control, state in self.setting_controls:
            control.configure(state='disabled' if busy else state)
        for button in (self.start_button, self.image_button):
            button.configure(state='disabled' if busy else 'normal')
        self.stop_button.configure(state='normal' if busy else 'disabled')
        self.update_run_settings()

    def write_log(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def refresh_windows(self):
        if self.busy:
            return
        self.windows = list_windows()
        self.windows.sort(key=lambda w: (not is_game(w), w.title))
        self.window_box['values'] = [w.label for w in self.windows]
        games = [i for i, window in enumerate(self.windows) if is_game(window)]
        if len(games) == 1:
            self.window_box.current(games[0])
            self.status.set('已找到游戏 · 自动循环可从高级难度投币页、动画页或十连结果页开始')
        else:
            self.window_box.set('')
            self.status.set('未找到唯一游戏窗口，请从列表手动选择')

    def options(self):
        options = Options(mode='current' if self.mode.get() == '只筛选当前十连结果' else 'loop',
                          rounds=int(self.rounds.get()), dry_run=self.dry_run.get(),
                          rules=tuple(self.rules))
        options.validate()
        return options

    def save_settings(self):
        try:
            options = self.options()
            (ROOT / 'settings.json').write_text(json.dumps(asdict(options), ensure_ascii=False, indent=2),
                                               encoding='utf-8')
            self.status.set('设置已保存，下次启动自动恢复')
        except (ValueError, OSError) as error:
            messagebox.showerror('无法保存设置', str(error), parent=self.root)

    def load_settings(self):
        path = ROOT / 'settings.json'
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            options = Options.from_dict(data)
        except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError) as error:
            messagebox.showerror('配置文件无效', str(error))
            return
        self.mode.set('只筛选当前十连结果' if options.mode == 'current' else '自动循环')
        self.rounds.set(str(options.rounds))
        self.rules = list(options.rules)
        self.dry_run.set(options.dry_run)

    def emit(self, kind, value):
        self.events.put((kind, value))

    def preload_reader(self):
        self.launch_worker(lambda _: None)

    def launch_worker(self, task):
        self.set_busy(True)
        self.stop_event.clear()
        self.table.delete(*self.table.get_children())
        self.records.clear()
        self.detail.set('选中一行，查看判定原因和完整词条。')

        def work():
            try:
                if self.reader is None:
                    local = all((ROOT / 'models' / name).is_file() for name in
                                ('PP-OCRv6_det_tiny.onnx', 'PP-OCRv6_rec_tiny.onnx'))
                    loading = '正在加载本地 OCR 模型并预热…' if local else '正在下载 OCR 模型并预热…'
                    self.emit('model_loading', loading)
                    self.emit('status', loading)
                    self.reader = Reader()
                    self.emit('model_ready', self.reader.load_seconds)
                    self.emit('status', f'OCR 已就绪：检测＋识别模型均已加载并通过预热（{self.reader.load_seconds:.2f} 秒）')
                if self.stop_event.is_set():
                    raise Stopped('已停止')
                task(self.reader)
            except (Stopped, WindowError, RecognitionError, ValueError, OSError) as error:
                if self.reader is None and not isinstance(error, Stopped):
                    self.emit('model_error', str(error))
                if not isinstance(error, Stopped):
                    (ROOT / 'logs').mkdir(exist_ok=True)
                    (ROOT / 'logs' / 'error.log').write_text(traceback.format_exc(), encoding='utf-8')
                self.emit('status', str(error))
            except Exception:
                # 工作线程边界：保留完整异常，反馈到界面；不重试鼠标动作。
                details = traceback.format_exc()
                if self.reader is None:
                    self.emit('model_error', '加载失败，详情见 logs/error.log')
                (ROOT / 'logs').mkdir(exist_ok=True)
                (ROOT / 'logs' / 'error.log').write_text(details, encoding='utf-8')
                self.emit('error', details)
            finally:
                self.emit('done', None)

        threading.Thread(target=work, daemon=True).start()

    def start(self):
        if self.busy or (self.editor is not None and self.editor.winfo_exists()):
            return
        try:
            options = self.options()
            index = self.window_box.current()
            if index < 0:
                raise ValueError('请先选择游戏窗口')
            window = self.windows[index]
            (ROOT / 'settings.json').write_text(json.dumps(asdict(options), ensure_ascii=False, indent=2),
                                               encoding='utf-8')
            if window.needs_elevation():
                self.status.set('游戏为管理员权限，正在请求 Windows 授权并重启…')
                self.root.update_idletasks()
                restart_elevated(start=True)
                self.close()
                return
        except (ValueError, OSError, WindowError) as error:
            messagebox.showerror('无法开始', str(error))
            return
        def task(reader):
            runner = Runner(window, reader, options, self.stop_event, self.emit)
            window.start_capture()
            try:
                runner.run()
            finally:
                window.close_capture()

        self.kept = self.discarded = self.completed_rounds = 0
        self.target = 10 * (1 if options.mode == 'current' else options.rounds)
        self.update_progress()
        self.launch_worker(task)

    def stop(self):
        if self.busy:
            self.stop_event.set()
            self.status.set('正在停止…')

    def open_image(self):
        path = filedialog.askopenfilename(title='选择游戏结果页或词条详情截图',
                                          filetypes=[('图片', '*.png *.jpg *.jpeg *.bmp')])
        if not path:
            return
        try:
            options = self.options()
        except ValueError as error:
            messagebox.showerror('配置无效', str(error))
            return

        def task(reader):
            image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise RecognitionError('无法读取这张图片')
            panel = find_panel(image)
            if panel is not None and reader.is_result(image):
                affixes = reader.affixes(image, panel)
            else:
                texts = reader.texts(image)
                affixes = [affix for text in sorted(texts, key=lambda t: t.y)
                           if text.score >= .88 and (affix := parse_affix(text.text)) is not None]
            decision = decide(affixes, options.rules)
            self.emit('item', dict(round='图', item=1, action='保留' if decision.keep else '丢弃',
                                  matched=decision.matched, affixes=[asdict(a) for a in affixes],
                                  reason=decision.reason, rule_name=decision.rule_name, dry_run=True))
            self.emit('status', '截图验算完成；未操作游戏')

        self.kept = self.discarded = self.completed_rounds = 0
        self.target = 1
        self.update_progress()
        self.launch_worker(task)

    def poll(self):
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == 'model_loading':
                self.model_status.set(value)
            elif kind == 'model_ready':
                self.model_status.set(f'文字识别已就绪（{value:.2f} 秒）· 本地识别 · PP-OCRv6 Tiny')
            elif kind == 'model_error':
                self.model_status.set(f'OCR 未就绪：{value}')
            elif kind == 'item':
                affixes = ' / '.join(a['raw'] for a in value['affixes'])
                action = '保留（锁定）' if value['action'] == '保留' else '不保留（丢弃标记）'
                if value['dry_run']:
                    action = '预览：' + value['action']
                row = self.table.insert('', 'end', values=(f"{value['round']}/{value['item']}",
                                  action, value['rule_name'] or '未命中',
                                  '、'.join(STAT_LABELS[s] for s in value['matched']) or '无', affixes),
                                  tags=('keep' if value['action'] == '保留' else 'discard',))
                self.records[row] = value
                if value['action'] == '保留':
                    self.kept += 1
                else:
                    self.discarded += 1
                self.update_progress()
                self.table.selection_set(row)
                self.table.yview_moveto(1)
                prefix = '[预览] ' if value['dry_run'] else ''
                self.write_log(f"{prefix}第 {value['item']} 件：{value['action']}，{value['reason']}")
            elif kind == 'round_complete':
                self.completed_rounds = value['round']
                self.update_progress()
            elif kind == 'status':
                self.status.set(value)
                self.write_log(value)
            elif kind == 'error':
                self.status.set('发生错误，完整信息见 logs/error.log')
                self.write_log(value)
            elif kind == 'done':
                self.set_busy(False)
                if self.closing:
                    self.root.destroy()
                    return
                auto_start, self.auto_start = self.auto_start, False
                if auto_start and self.reader is not None:
                    self.root.after(100, self.start)
        for key in self.key_states:
            down = key_down(key)
            if down and not self.key_states[key]:
                self.start() if key == 0x77 else self.stop()
            self.key_states[key] = down
        self.root.after(70, self.poll)

    def close(self):
        self.stop_event.set()
        if self.busy:
            self.closing = True
            self.status.set('正在停止并释放后台截图…')
        else:
            self.root.destroy()


def main():
    root = tk.Tk()
    App(root, auto_start='--start' in sys.argv)
    root.mainloop()
