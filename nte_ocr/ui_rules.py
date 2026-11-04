import tkinter as tk
from tkinter import messagebox, ttk

from .rules import KeepRule, RetainCondition, STAT_LABELS


class RuleEditor(tk.Toplevel):
    """只在保存成功时将完整规则交回主界面。"""

    def __init__(self, parent, rule, on_save):
        super().__init__(parent)
        self.title('编辑保留规则' if rule else '添加保留规则')
        self.resizable(False, False)
        self.transient(parent)
        self.on_save = on_save
        self.name = tk.StringVar(value=rule.name if rule else '')
        self.enabled = tk.BooleanVar(value=rule.enabled if rule else True)
        self.minimum = tk.StringVar(value=str(rule.minimum_matches if rule else 2))
        body = ttk.Frame(self, padding=20)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='这组条件全部满足时，锁定保留', font=('Microsoft YaHei UI', 14, 'bold')).grid(
            row=0, column=0, columnspan=3, sticky='w', pady=(0, 12))
        ttk.Label(body, text='规则名称').grid(row=1, column=0, sticky='w')
        entry = ttk.Entry(body, textvariable=self.name, width=30)
        entry.grid(row=1, column=1, sticky='ew')
        ttk.Checkbutton(body, text='启用', variable=self.enabled).grid(row=1, column=2, padx=10)
        ttk.Label(body, text='至少满足几条').grid(row=2, column=0, sticky='w', pady=10)
        ttk.Spinbox(body, from_=1, to=4, textvariable=self.minimum, width=5, state='readonly').grid(
            row=2, column=1, sticky='w')
        ttk.Label(body, text='只看词条种类与组合，不比较数值。“必备”也计入条数。',
                  foreground='#637189').grid(row=3, column=0, columnspan=3, sticky='w', pady=(0, 12))
        for column, title in enumerate(('保留词条', '参与方式')):
            ttk.Label(body, text=title, font=('Microsoft YaHei UI', 10, 'bold')).grid(
                row=4, column=column, sticky='w', pady=(0, 6))
        existing = {c.stat: c for c in rule.conditions} if rule else {}
        self.rows = {}
        for row, (stat, label) in enumerate(STAT_LABELS.items(), 5):
            condition = existing.get(stat)
            mode = tk.StringVar(value=('必备' if condition.required else '计入条数') if condition else '不参与')
            ttk.Label(body, text=label).grid(row=row, column=0, sticky='w', padx=(0, 14), pady=4)
            ttk.Combobox(body, values=('不参与', '计入条数', '必备'), textvariable=mode,
                         state='readonly', width=11).grid(row=row, column=1, sticky='w', pady=4)
            self.rows[stat] = mode
        ttk.Label(body, text='固定值与百分比分开识别；不同大小驱动块的同类词条同样计数。',
                  foreground='#637189').grid(row=16, column=0, columnspan=3, sticky='w', pady=12)
        actions = ttk.Frame(body)
        actions.grid(row=17, column=0, columnspan=3, sticky='e')
        ttk.Button(actions, text='取消', command=self.destroy).pack(side='left', padx=8)
        ttk.Button(actions, text='保存规则', command=self.save, style='Primary.TButton').pack(side='left')
        self.bind('<Escape>', lambda _: self.destroy())
        self.grab_set()
        entry.focus_set()

    def save(self):
        try:
            conditions = tuple(RetainCondition(stat, required=mode.get() == '必备')
                               for stat, mode in self.rows.items() if mode.get() != '不参与')
            rule = KeepRule(self.name.get().strip(), conditions, int(self.minimum.get()), self.enabled.get())
            rule.validate()
        except ValueError as error:
            messagebox.showerror('请检查规则', str(error), parent=self)
            return
        self.on_save(rule)
        self.destroy()
