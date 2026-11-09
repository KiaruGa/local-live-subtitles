; Inno Setup script for Local Live Subtitles.
; Build the app first:  powershell -ExecutionPolicy Bypass -File scripts\build.ps1
; Then compile:          iscc installer\LocalLiveSubtitles.iss

#define AppName "Local Live Subtitles"
#define AppVersion "1.0.0"
#define AppPublisher "Local Live Subtitles contributors"
#define AppExeName "LocalLiveSubtitles.exe"
#define AppId "{{8F3C2A6E-5B41-4C7D-9A2F-1D6E8B0C4A73}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\LocalLiveSubtitles
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=LocalLiveSubtitles-Setup-{#AppVersion}
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=no
MinVersion=10.0
#ifdef SIGNTOOL
SignTool={#SIGNTOOL}
#endif

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Запускать Local Live Subtitles при входе в Windows (иконка в трее)"; GroupDescription: "Автозапуск:"; Flags: unchecked

[Files]
Source: "..\dist\LocalLiveSubtitles\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Удалить {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "LocalLiveSubtitles"; ValueData: """{app}\{#AppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM {#AppExeName} /F >NUL 2>&1"; Flags: runhidden; RunOnceId: "StopApp"
