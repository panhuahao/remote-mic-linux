# SPDX-License-Identifier: GPL-3.0-only
import ast
import json
from pathlib import Path
import string
import tempfile
import unittest

from remote_bridge.i18n import (DEFAULT_LOCALE, ENGLISH, Translator, error_message,
                                load_locale, message_key, msg, render, save_locale)


class LocaleTests(unittest.TestCase):
    def test_missing_corrupt_and_unsupported_preferences_default_to_chinese(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'ui.json'
            self.assertEqual(load_locale(path),DEFAULT_LOCALE)
            for value in ('invalid','[]','null','{"language":"fr"}','{"language":null}'):
                path.write_text(value)
                self.assertEqual(load_locale(path),DEFAULT_LOCALE)

    def test_ui_preference_is_private_and_does_not_modify_speech_or_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'ui.json'
            config=path.with_name('config.json');config.write_text('{"voice":{"language":"ja","mode":"youdao"}}')
            credentials=path.with_name('youdao-credentials.json');credentials.write_text('test credential content')
            before=(config.read_bytes(),credentials.read_bytes())
            save_locale('en',path)
            self.assertEqual(load_locale(path),'en')
            self.assertEqual(json.loads(path.read_text()),{'language':'en'})
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertEqual((config.read_bytes(),credentials.read_bytes()),before)
            save_locale('zh',path)
            self.assertEqual(load_locale(path),'zh_CN')

    def test_invalid_saved_locale_is_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'new'/'ui.json'
            save_locale('unsupported',path)
            self.assertEqual(load_locale(path),DEFAULT_LOCALE)

    def test_message_keys_and_parameters_are_independent_of_display_language(self):
        source=msg('有道 · {service}',service=msg('实时短语音识别'))
        value=msg('最终识别结果 · {source}',source=source)
        self.assertEqual(render(value,'en'),'Final result · Youdao · Short streaming recognition')
        self.assertEqual(render(value,'zh_CN'),'最终识别结果 · 有道 · 实时短语音识别')
        self.assertEqual(message_key(value),'最终识别结果 · {source}')
        self.assertEqual(str(value),'最终识别结果 · 有道 · 实时短语音识别')
        self.assertEqual(render(msg('按键：{key}',key='KEY_UP'),'en'),'Key: KEY_UP')

    def test_internal_errors_translate_and_external_braces_remain_literal(self):
        internal=RuntimeError(msg('本次识别失败：{error}',error=msg('模型文件尚未就绪')))
        self.assertEqual(render(error_message(internal),'en'),'Recognition failed: Model files are not ready')
        for literal in ('Could not open {recording}.wav','Invalid JSON: {"error": 7}','unclosed {'):
            error=ValueError(literal)
            for locale in ('en','zh_CN'):
                self.assertEqual(render(error_message(error),locale),literal)
                self.assertEqual(render(msg('输入失败：{error}',error=error_message(error)),locale),
                                 ('Insertion failed: ' if locale=='en' else '输入失败：')+literal)

    def test_unknown_strings_and_user_content_are_unchanged(self):
        self.assertEqual(render('Uncatalogued text {value}','en'),'Uncatalogued text {value}')
        value=msg('打开应用：{app}',app='保存')
        self.assertEqual(render(value,'en'),'Launch: 保存')
        self.assertEqual(render(msg('识别完成：音频 {audio:.1f} 秒，处理 {elapsed:.1f} 秒',audio=1.23,elapsed=.16),'en'),
                         'Recognition complete: 1.2 s audio, 0.2 s processing')

    def test_catalog_retains_all_format_fields(self):
        formatter=string.Formatter()
        fields=lambda value:{name for _,name,_,_ in formatter.parse(value) if name is not None}
        for source,translation in ENGLISH.items():
            with self.subTest(source=source):self.assertEqual(fields(source),fields(translation))

    def test_visible_chinese_labels_have_english_translations(self):
        root=Path(__file__).resolve().parents[1]/'remote_bridge'
        # These are canonical status classifiers / Bluetooth advertisement data.
        exempt={'失败','等待','协商','有误','有道识别失败：','小米蓝牙语音遥控器'}
        for module in ('ui','gui','actions','action_editor','tray','bridge','speech','youdao','config','keyboard','audio','protocol'):
            for node in ast.walk(ast.parse((root/(module+'.py')).read_text())):
                if isinstance(node,ast.Constant) and isinstance(node.value,str) and any('\u4e00'<=ch<='\u9fff' for ch in node.value):
                    if node.value not in exempt:
                        with self.subTest(module=module,label=node.value):self.assertIn(node.value,ENGLISH)

    def test_widget_bindings_relabel_in_place_and_replace_old_status(self):
        class Label:
            def set_text(self,text):self.value=text
        label=Label();translator=Translator('zh_CN')
        translator.bind(label,'set_text','识别尚未启动')
        translator.bind(label,'set_text','识别完成')
        translator.set_locale('en')
        self.assertEqual(label.value,'Recognition complete')
        self.assertEqual(len(translator.bindings),1)
        translator.set_locale('zh_CN')
        self.assertEqual(label.value,'识别完成')


if __name__=='__main__':unittest.main()
