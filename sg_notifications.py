"""Windows generation-completion notifications through the installed GIMP identity."""

from __future__ import annotations

import base64
import json
import os
import subprocess

from pathlib import Path

_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$message = [Console]::In.ReadToEnd() | ConvertFrom-Json
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = [Windows.Data.Xml.Dom.XmlDocument]::new()
$xml.LoadXml('<toast><visual><binding template="ToastGeneric"><text/><text/></binding></visual></toast>')
$nodes = $xml.GetElementsByTagName('text')
$nodes.Item(0).AppendChild($xml.CreateTextNode($message.title)) | Out-Null
$nodes.Item(1).AppendChild($xml.CreateTextNode($message.body)) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
$appId = '{6D809377-6AF0-444B-8957-A3773F02200E}\GIMP 3\bin\gimp-3.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
"""


def notify_generation_finished(title: str, body: str) -> None:
    powershell = Path(os.environ["SYSTEMROOT"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    subprocess.run(  # noqa: S603
        [
            str(powershell), "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-OutputFormat", "Text",
            "-EncodedCommand",
            base64.b64encode(_SCRIPT.encode("utf-16-le")).decode("ascii"),
        ],
        input=json.dumps({"title": title, "body": body}, ensure_ascii=False).encode("utf-8"),
        capture_output=True, check=True, timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
