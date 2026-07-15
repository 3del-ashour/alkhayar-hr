; installer.iss — Inno Setup script for الخيار HR v4
; Produces: AlkhayarHR_Setup.exe
; Download Inno Setup: https://jrsoftware.org/isdl.php

#define AppName      "الخيار HR"
#define AppNameEn    "AlkhayarHR"
#define AppVersion   "4.0"
#define AppPublisher "شركة الخيار للسيارات وقطع غيارها"
#define AppExeName   "AlkhayarHR.exe"
#define SourceDir    "dist\AlkhayarHR"

[Setup]
AppId={{B7C2A1D4-3E5F-4A8B-9C6D-0E1F2A3B4C5D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppNameEn}
DefaultGroupName={#AppName}
AllowNoIcons=no
; Single output installer file
OutputDir=installer_output
OutputBaseFilename=AlkhayarHR_Setup_v{#AppVersion}
; Compression
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
; Require admin for install (writes to Program Files)
PrivilegesRequired=admin
; Minimum Windows version: Windows 10
MinVersion=10.0
; Architecture
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
; Installer appearance
WizardStyle=modern
WizardResizable=no
; Icon (use .ico if available, else skip)
; SetupIconFile=assets\sa_logo.ico
; Uninstaller
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
; Don't allow running installer from within a ZIP
DisableWelcomePage=no
; Show license page (optional — remove if you don't have one)
; LicenseFile=LICENSE.txt

[Languages]
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";    Description: "إنشاء اختصار على سطح المكتب";     GroupDescription: "اختصارات إضافية:"; Flags: checkedonce
Name: "startmenuicon";  Description: "إضافة إلى قائمة ابدأ";           GroupDescription: "اختصارات إضافية:"; Flags: checkedonce

[Files]
; Copy all built app files to install directory
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu
Name: "{group}\{#AppName}";         Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{group}\إلغاء تثبيت {#AppName}"; Filename: "{uninstallexe}"
; Desktop shortcut (optional, based on task selection)
Name: "{autodesktop}\{#AppName}";   Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; Offer to launch app immediately after install
Filename: "{app}\{#AppExeName}"; Description: "تشغيل {#AppName} الآن"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up any .pyc files left behind
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
// Show a friendly message if 64-bit Windows is not detected
function InitializeSetup(): Boolean;
begin
  Result := True;
  if not Is64BitInstallMode then
  begin
    MsgBox('هذا البرنامج يتطلب نظام Windows 64-bit.' + #13#10 +
           'This installer requires a 64-bit Windows system.', mbError, MB_OK);
    Result := False;
  end;
end;
