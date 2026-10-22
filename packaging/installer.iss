; Inno Setup script for the Windows installer.
;   iscc /DAppVersion=0.5.2 packaging\installer.iss
; Expects the PyInstaller output in dist\Free-to-Download and writes dist\Free-to-Download-Setup.exe.
; Installs per user (no administrator prompt): the app keeps its queue and settings in a data folder
; beside the executable, which must stay writable.
;
; Optional: /DChromeStoreId=<id> and/or /DEdgeStoreId=<id> register the store-published extension so the
; browser offers "New extension added → Enable" on its next start (only works for store-listed extensions).

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
Name: "startup"; Description: "Start Free-to-Download when I sign in to Windows (minimized), so the browser button always works"; GroupDescription: "Browser integration:"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Free-to-Download"; ValueData: """{app}\Free-to-Download.exe"" --minimized"; Flags: uninsdeletevalue; Tasks: startup
#ifdef ChromeStoreId
Root: HKCU; Subkey: "Software\Google\Chrome\Extensions\{#ChromeStoreId}"; ValueType: string; ValueName: "update_url"; ValueData: "https://clients2.google.com/service/update2/crx"; Flags: uninsdeletekey
#endif
#ifdef EdgeStoreId
Root: HKCU; Subkey: "Software\Microsoft\Edge\Extensions\{#EdgeStoreId}"; ValueType: string; ValueName: "update_url"; ValueData: "https://edge.microsoft.com/extensionwebstorebase/v1/crx"; Flags: uninsdeletekey
#endif

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
#ifndef ChromeStoreId
; Until the extension is store-listed: open Chrome's extensions page and the folder side by side, so adding
; the button is one "Load unpacked" click. The extension then connects to the app by itself.
Filename: "{code:BrowserPath|chrome.exe}"; Parameters: "chrome://extensions/"; Description: "Add the browser button to Chrome (opens the extensions page and the extension folder)"; Flags: nowait postinstall skipifsilent; Check: HasBrowser('chrome.exe')
Filename: "{app}\browser-extension"; Flags: nowait postinstall shellexec skipifsilent; Check: HasBrowser('chrome.exe'); Description: "Open the extension folder"
#endif

[Code]
function BrowserPath(Exe: String): String;
begin
  Result := '';
  if not RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\' + Exe, '', Result) then
    RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\' + Exe, '', Result);
end;

function HasBrowser(Exe: String): Boolean;
begin
  Result := (BrowserPath(Exe) <> '') and FileExists(BrowserPath(Exe));
end;
