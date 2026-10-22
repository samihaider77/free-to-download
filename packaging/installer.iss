; Inno Setup script for the Windows installer.
;   iscc /DAppVersion=0.5.2 packaging\installer.iss
; Expects the PyInstaller output in dist\Free-to-Download and writes dist\Free-to-Download-Setup.exe.
; Installs per user (no administrator prompt): the app keeps its queue and settings in a data folder
; beside the executable, which must stay writable.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{A321730C-9CA8-48A0-BE1C-DD91FC450349}
AppName=Free-to-Download
AppVersion={#AppVersion}
AppVerName=Free-to-Download {#AppVersion}
AppPublisher=Free-to-Download contributors
AppPublisherURL=https://github.com/samihaider77/free-to-download
AppSupportURL=https://github.com/samihaider77/free-to-download/issues
AppUpdatesURL=https://github.com/samihaider77/free-to-download/releases
DefaultDirName={localappdata}\Programs\Free-to-Download
DefaultGroupName=Free-to-Download
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Free-to-Download-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\Free-to-Download.exe
UninstallDisplayName=Free-to-Download
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\dist\Free-to-Download\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\browser-extension\*"; DestDir: "{app}\browser-extension"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\THIRD-PARTY-LICENSES\*"; DestDir: "{app}\THIRD-PARTY-LICENSES"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\THIRD-PARTY-NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Free-to-Download"; Filename: "{app}\Free-to-Download.exe"
Name: "{group}\Browser extension folder"; Filename: "{app}\browser-extension"
Name: "{group}\Uninstall Free-to-Download"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Free-to-Download"; Filename: "{app}\Free-to-Download.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Free-to-Download.exe"; Description: "Launch Free-to-Download"; Flags: nowait postinstall skipifsilent
Filename: "{app}\browser-extension"; Description: "Open the browser extension folder (Chrome: Load unpacked)"; Flags: postinstall shellexec skipifsilent unchecked
