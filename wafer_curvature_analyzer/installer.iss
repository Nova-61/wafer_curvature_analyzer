#define AppName "Wafer Curvature Analyzer"
#define AppVersion "1.0.0"
#define AppExeName "WaferCurvatureAnalyzer.exe"

[Setup]
AppId={{B1E4F782-6233-47D8-A348-FAC0BECC4C7E}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Wafer Curvature Analyzer
DefaultDirName={autopf}\Wafer Curvature Analyzer
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
OutputDir=dist
OutputBaseFilename=WaferCurvatureAnalyzerSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
Source: "dist\WaferCurvatureAnalyzer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch application"; Flags: postinstall nowait skipifsilent
