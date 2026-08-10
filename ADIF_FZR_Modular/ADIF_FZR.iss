; =====================================================================
;  ADIF FZR 2.4 - Script Inno Setup (build PyInstaller ONEFILE)
;  Compila l'installer aprendo questo file con Inno Setup -> Compila (F9)
;  Prerequisito: aver gia' generato  dist\ADIF_FZR.exe  con PyInstaller
; =====================================================================

#define MyAppName        "ADIF FZR"
#define MyAppVersion     "2.4"
#define MyAppPublisher   "IW1FZR - Luca"
#define MyAppURL         "https://iw1fzr.it"
#define MyAppExeName     "ADIF_FZR.exe"

[Setup]
; AppId univoco: NON cambiarlo tra un aggiornamento e l'altro (serve a Windows
; per riconoscere che e' la stessa app e sostituire la versione precedente)
AppId={{A7F3C2E9-8B41-4D6A-9E2C-ADIFFZR24IW1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

DefaultDirName={autopf}\ADIF FZR
DefaultGroupName=ADIF FZR
DisableProgramGroupPage=yes
OutputBaseFilename=ADIF_FZR_2.4_Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Icona dell'installer e disinstallatore (se presente accanto allo script)
; SetupIconFile=adif_fzr.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
; L'app e' a 64 bit: installa in Program Files (non x86)
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

[Languages]
Name: "italiano"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english";  MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; L'eseguibile onefile prodotto da PyInstaller
Source: "dist\ADIF_FZR.exe"; DestDir: "{app}"; Flags: ignoreversion
; Risorse opzionali: vengono incluse SOLO se esistono accanto allo script.
; (Con il .spec sono gia' dentro l'exe; qui le copio anche a fianco per sicurezza.)
Source: "adif_fzr.ico"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "splash.png";   DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "logo.png";     DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "README*.txt";  DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "LICENSE*.txt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
; Voce nel menu Start
Name: "{group}\ADIF FZR"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,ADIF FZR}"; Filename: "{uninstallexe}"
; Collegamento sul Desktop (se l'utente ha lasciato la spunta)
Name: "{autodesktop}\ADIF FZR"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; Offri di avviare l'app al termine dell'installazione
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,ADIF FZR}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Pulisce eventuali file temporanei creati dall'app nella sua cartella
Type: filesandordirs; Name: "{app}\__pycache__"
