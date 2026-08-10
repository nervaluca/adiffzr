; ════════════════════════════════════════════════════════════
;  ADIF FZR 2.4 — Script Inno Setup (build PyInstaller ONEFILE)
;  IW1FZR Amateur Radio Tools
;  Prerequisito: dist\ADIF_FZR.exe generato dal .spec
; ════════════════════════════════════════════════════════════

#define MyAppName "ADIF FZR"
#define MyAppVersion "2.5"
#define MyAppPublisher "IW1FZR Amateur Radio Tools"
#define MyAppURL "https://iw1fzr.it"
#define MyAppExeName "ADIF_FZR.exe"

[Setup]
AppId={{B7E1C8A4-3F2D-4E9A-9C1B-ADIFFZR24001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes

OutputDir=installer_output
OutputBaseFilename=ADIF_FZR_v2.5_Setup
; Icona dell'installer (togli il ; se hai icon.ico nella cartella)
; SetupIconFile=icon.ico

WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes

ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Licenza e info: righe attive solo se i file esistono (vedi note).
; Se NON hai questi txt, lascia commentate queste due righe.
; LicenseFile=LICENSE_ADIF_FZR.txt
; InfoBeforeFile=README_ADIF_FZR.txt

UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "fileassoc"; Description: "Associa i file .adi e .adif ad ADIF FZR"; GroupDescription: "Associazioni file:"; Flags: unchecked

[Files]
; ── ONEFILE: un solo eseguibile ──
Source: "dist\ADIF_FZR.exe"; DestDir: "{app}"; Flags: ignoreversion
; Documentazione: inclusa solo se presente (niente errore se manca)
Source: "README_ADIF_FZR.txt"; DestDir: "{app}"; Flags: ignoreversion isreadme skipifsourcedoesntexist
Source: "LICENSE_ADIF_FZR.txt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
; ── Associazione file .adi / .adif ──
Root: HKA; Subkey: "Software\Classes\.adi"; ValueType: string; ValueName: ""; ValueData: "ADIFFZR.LogFile"; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\.adif"; ValueType: string; ValueName: ""; ValueData: "ADIFFZR.LogFile"; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\ADIFFZR.LogFile"; ValueType: string; ValueName: ""; ValueData: "File log ADIF"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\ADIFFZR.LogFile\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\ADIFFZR.LogFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: fileassoc

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
