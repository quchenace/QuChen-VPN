; QuChen VPN —— Inno Setup 脚本（由 CI 调用）
#define MyAppName "QuChen VPN"
; CI passes /DMyAppVersion=<version> from app/backend/service.py APP_VER; the fallback is for a local build
#ifndef MyAppVersion
#define MyAppVersion "1.0.11"
#endif
#define MyAppExe "QuChenVPN.exe"

[Setup]
AppId={{9E3B7A4C-6D1F-4C1E-9A0B-QUCHENVPN01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=QuChen
DefaultDirName={autopf}\QuChen VPN
DefaultGroupName=QuChen VPN
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=release
OutputBaseFilename=QuChenVPN-Setup
SetupIconFile=app\assets\app.ico
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExe}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"

[Files]
Source: "dist\QuChenVPN\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\QuChen VPN"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\QuChen VPN"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "启动 QuChen VPN"; Flags: nowait postinstall skipifsilent
