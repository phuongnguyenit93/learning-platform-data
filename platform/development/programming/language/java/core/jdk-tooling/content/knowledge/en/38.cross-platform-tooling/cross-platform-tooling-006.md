# Writing PowerShell Scripts to Automate Java Tooling

PowerShell is a shell and scripting language well-suited for automating Java tasks such as locating a JDK, compiling source code, running applications, packaging JARs, verifying checksums, and collecting diagnostics. PowerShell provides an object-based pipeline, variables, functions, exception handling, and the ability to directly invoke native programs such as java, javac, jar, and jcmd.

When working across multiple operating systems, you should use **PowerShell 7 (pwsh)** because it runs on Windows, Linux, and macOS. Windows PowerShell 5.1 (powershell.exe) is Windows-only but remains common in legacy scripts and enterprise environments. The scripts in this article are written using syntax compatible with PowerShell 5.1 and later; actual testing was run on Windows PowerShell 5.1.26100.9711 with JDK 24.0.2.

## 1. PowerShell 5.1 and PowerShell 7

There are two PowerShell editions to distinguish:

| Version | Executable | Platform | Runtime |
|---|---|---|---|
| Windows PowerShell 5.1 | powershell.exe | Windows | .NET Framework |
| PowerShell 7+ | pwsh | Windows, Linux, macOS | .NET |
| PowerShell 7.3+ | pwsh | Windows, Linux, macOS | Improved argument passing for native commands |

Check the current version:

~~~powershell
$PSVersionTable | Format-List PSVersion, PSEdition, Platform, OS
~~~

Sample output on Windows PowerShell 5.1:

~~~text
PSVersion : 5.1.26100.9711
PSEdition : Desktop
~~~

PowerShell 7 typically displays PSEdition as Core. Do not infer the operating system solely from PSEdition because PowerShell 7 runs on multiple platforms.

Run a script from a command prompt or CI:

Windows PowerShell:

~~~powershell
powershell.exe -NoProfile -File .\scripts\build-java.ps1
~~~

PowerShell 7:

~~~powershell
pwsh -NoProfile -File ./scripts/build-java.ps1
~~~

If you are already inside a PowerShell session, you can use the call operator:

~~~powershell
& ./scripts/build-java.ps1 -MainClass com.example.HelloJava -Release 17
~~~

PowerShell 7 is the right choice when a script needs to run the same logic on Windows, Linux, and macOS. If you must maintain Windows PowerShell 5.1, avoid syntax or APIs that only exist in PowerShell 6/7.

## 2. Basic Structure of a Script

A script file consists of a parameter block, error configuration, functions, and execution logic. Place param at the top of the script, before any executable commands:

~~~powershell
param(
    [string]$Name = "Java",
    [int]$Release = 17
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Output "Hello $Name"
Write-Output "Target release: $Release"
~~~

Common concepts:

- Variables start with the $ character.
- Strings can use single or double quotes.
- Arrays hold multiple values.
- Hashtables store key/value pairs.
- Functions group logic for reuse.
- Pipelines pass objects from one command to another.
- try/catch/finally handles errors and cleanup.
- Parameters allow a script to accept configuration from the command line or CI.

PowerShell does not just pass text between commands. For example, Get-ChildItem returns FileInfo/DirectoryInfo objects, which can be filtered with Where-Object, sorted with Sort-Object, and have properties selected with Select-Object.

### Functions and Parameter Validation

~~~powershell
function Get-JavaReleaseLabel {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateRange(8, 99)]
        [int]$Release
    )

    return "Java SE $Release"
}

Get-JavaReleaseLabel -Release 17
~~~

Output:

~~~text
Java SE 17
~~~

ValidateRange blocks input outside the declared range. It does not prove that the installed JDK supports that release; javac still has to verify it upon execution.

## 3. Using Paths Safely Across Operating Systems

Windows typically uses backslashes in paths, while Linux/macOS use forward slashes. Avoid building paths manually through string concatenation:

~~~powershell
# Fragile: separator and quoting are hard-coded
$source = "C:\project\src\Main.java"
~~~

Use Join-Path to construct OS-appropriate paths:

~~~powershell
$projectRoot = $PSScriptRoot
$sourceDirectory = Join-Path $projectRoot "src"
$outputDirectory = Join-Path $projectRoot "build/classes"
~~~

Useful variables:

| Variable | Meaning |
|---|---|
| PSScriptRoot | Directory containing the current script |
| PSCommandPath | Full path of the current script |
| PWD | Current working directory |
| JAVA_HOME | Root directory of the JDK |
| PATH | Directories where the shell searches for executables |

Use PSScriptRoot so the script locates source or config files relative to the script file itself. This is more reliable than depending on whichever working directory CI chooses.

Use LiteralPath when working with filenames containing characters like square brackets:

~~~powershell
Get-Item -LiteralPath $sourceDirectory
Test-Path -LiteralPath $sourceDirectory -PathType Container
~~~

LiteralPath treats the string as an exact path without interpreting wildcards such as square brackets or asterisks.

### Paths and Case-Sensitive Filesystems

Windows typically uses a case-insensitive filesystem; Linux is typically case-sensitive. Files named HelloJava.java and hellojava.java can be treated as two different names on Linux. Keep exact casing consistent across filenames, packages, classes, and paths.

Do not hard-code path separators or assume every machine has a C: drive. Join-Path, Split-Path, and PSScriptRoot help scripts work across different platforms.

## 4. Finding the JDK and Checking JAVA_HOME

JAVA_HOME should point to the JDK root directory, i.e., the directory containing bin, lib, and conf. Do not point JAVA_HOME directly to bin or to a stripped-down JRE.

Check:

~~~powershell
$env:JAVA_HOME
Get-Command java -CommandType Application
Get-Command javac -CommandType Application
java -version
javac -version
~~~

A machine may have multiple JDKs installed. If PATH points to a different JDK than JAVA_HOME, java and javac may come from an unintended version.

The following function prioritizes tools in JAVA_HOME, then falls back to PATH. It appends .exe on Windows and uses the executable name without an extension on Linux/macOS.

~~~powershell
function Get-JdkToolPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $fileName = if ($env:OS -eq "Windows_NT") {
        "$Name.exe"
    } else {
        $Name
    }

    if (-not [string]::IsNullOrWhiteSpace($env:JAVA_HOME)) {
        $candidate = Join-Path (Join-Path $env:JAVA_HOME "bin") $fileName

        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }

    $command = Get-Command $fileName -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if ($null -eq $command) {
        throw "Cannot find $fileName. Install a JDK and set JAVA_HOME or PATH."
    }

    return $command.Source
}

$java = Get-JdkToolPath -Name "java"
$javac = Get-JdkToolPath -Name "javac"

Write-Output "java: $java"
Write-Output "javac: $javac"
~~~

On Windows, the OS environment variable typically has the value Windows_NT. On Linux and macOS, this variable is usually unset, so the function uses the tool name without .exe.

PowerShell 6+ provides automatic variables such as IsWindows, IsLinux, and IsMacOS. These variables do not exist in Windows PowerShell 5.1. If a script needs 5.1 compatibility, do not use them without a fallback.

## 5. Invoking java, javac, and jar from PowerShell

PowerShell uses the call operator & to run executables:

~~~powershell
$javac = Get-JdkToolPath -Name "javac"

& $javac --version
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    throw "javac --version failed with exit code $exitCode"
}
~~~

Commands like java, javac, jar, and jcmd are native executables, not PowerShell cmdlets. Because of this, there are several important differences:

- $LASTEXITCODE holds the exit code of the most recent native command.
- $? only indicates whether the last command succeeded from PowerShell's perspective; it does not replace the numeric exit code.
- $ErrorActionPreference = "Stop" handles PowerShell terminating errors, but in Windows PowerShell 5.1 it does not automatically turn every non-zero native exit code into an exception.
- Save $LASTEXITCODE immediately after each native command, before running any other command.

Example:

~~~powershell
& $java -version
$javaVersionExit = $LASTEXITCODE

if ($javaVersionExit -ne 0) {
    throw "java -version failed with exit code $javaVersionExit"
}

& $javac -version
$javacVersionExit = $LASTEXITCODE

if ($javacVersionExit -ne 0) {
    throw "javac -version failed with exit code $javacVersionExit"
}
~~~

Do not wait until the end of the script to read $LASTEXITCODE. Another native command can overwrite that value.

### Passing Arguments with Arrays and Splatting

Do not build a command string and execute it with Invoke-Expression. That approach is prone to quoting bugs and creates a command injection risk if the string contains external data.

Use an argument array:

~~~powershell
$arguments = @(
    "--release", "17",
    "-encoding", "UTF-8",
    "-d", $outputDirectory,
    $sourceFile
)

& $javac @arguments
$compileExitCode = $LASTEXITCODE
~~~

The @ before the array name is splatting: each element is passed as a separate argument. This ensures paths with spaces are passed properly in normal cases.

PowerShell 7.3 improved argument serialization for native commands and introduced the PSNativeCommandArgumentPassing variable. Windows PowerShell 5.1 uses the legacy mechanism. If passing arguments containing nested double quotes, trailing backslashes, or special native program syntax, test on every supported shell/version.

## 6. Distinguishing PowerShell Errors from Java Program Errors

PowerShell has two common categories of errors:

**Cmdlet or script errors:** for example, a non-existent path, an invalid parameter, or an unreadable file. These can be handled using try/catch and ErrorActionPreference.

**Native process errors:** for example, javac compilation failure or a Java application returning exit code 7. These require checking LASTEXITCODE.

Example:

~~~powershell
try {
    & $java -cp $outputDirectory "com.example.HelloJava"
    $runExitCode = $LASTEXITCODE

    if ($runExitCode -ne 0) {
        throw "Java application failed with exit code $runExitCode"
    }
}
catch {
    Write-Error "Build step failed: $($_.Exception.Message)"
    exit 1
}
~~~

If you need to return the exact exit code of the Java process to CI, you can use:

~~~powershell
& $java -jar $jarPath
$runExitCode = $LASTEXITCODE

if ($runExitCode -ne 0) {
    exit $runExitCode
}
~~~

When using exit, the script terminates immediately. If there are temporary files or resources that need cleanup, place the cleanup in a finally block and structure the control flow so that finally runs before exiting.

PowerShell 7.3+ can configure PSNativeCommandUseErrorActionPreference to turn non-zero native exit codes into errors according to the preference. However, scripts shared across versions should still check LASTEXITCODE explicitly.

## 7. Java 17+ Example: Building and Running a Project with PowerShell

Project structure:

~~~text
java-demo/
├── scripts/
│   └── build-java.ps1
├── src/
│   └── com/
│       └── example/
│           ├── HelloJava.java
│           └── ExitCodeDemo.java
└── build/
    └── classes/
~~~

### HelloJava.java

~~~java
package com.example;

public final class HelloJava {
    public static void main(String[] args) {
        System.out.println("Hello from Java on PowerShell");
    }
}
~~~

### ExitCodeDemo.java

~~~java
package com.example;

public final class ExitCodeDemo {
    public static void main(String[] args) {
        System.err.println("intentional failure");
        System.exit(7);
    }
}
~~~

### scripts/build-java.ps1

Put the following script into build-java.ps1:

~~~powershell
param(
    [string]$MainClass = "com.example.HelloJava",
    [int]$Release = 17
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-JdkToolPath {
    param([Parameter(Mandatory = $true)][string]$Name)

    $fileName = if ($env:OS -eq "Windows_NT") {
        "$Name.exe"
    } else {
        $Name
    }

    if (-not [string]::IsNullOrWhiteSpace($env:JAVA_HOME)) {
        $candidate = Join-Path (Join-Path $env:JAVA_HOME "bin") $fileName

        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }

    $command = Get-Command $fileName -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if ($null -eq $command) {
        throw "Cannot find $fileName. Install a JDK and set JAVA_HOME or PATH."
    }

    return $command.Source
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceDirectory = Join-Path $projectRoot "src"
$outputDirectory = Join-Path $projectRoot "build/classes"

if (-not (Test-Path -LiteralPath $sourceDirectory -PathType Container)) {
    throw "Source directory not found: $sourceDirectory"
}

$sourceFiles = @(
    Get-ChildItem -LiteralPath $sourceDirectory -Filter "*.java" -File -Recurse |
        Sort-Object -Property FullName |
        ForEach-Object { $_.FullName }
)

if ($sourceFiles.Count -eq 0) {
    throw "No Java source files found in $sourceDirectory"
}

$null = New-Item -ItemType Directory -Force -Path $outputDirectory

$javac = Get-JdkToolPath -Name "javac"
$java = Get-JdkToolPath -Name "java"

$compileArgs = @(
    "--release", $Release.ToString(),
    "-encoding", "UTF-8",
    "-d", $outputDirectory
) + $sourceFiles

Write-Output "Compiling $($sourceFiles.Count) Java source file(s) with JDK release $Release"

& $javac @compileArgs
$compileExitCode = $LASTEXITCODE

if ($compileExitCode -ne 0) {
    throw "javac failed with exit code $compileExitCode"
}

Write-Output "Running $MainClass"

& $java "-cp" $outputDirectory $MainClass
$runExitCode = $LASTEXITCODE

if ($runExitCode -ne 0) {
    throw "java exited with code $runExitCode"
}

Write-Output "Build and run succeeded"
~~~

### Running on Windows PowerShell

From the project directory:

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-java.ps1
~~~

Or from an already open PowerShell session:

~~~powershell
& .\scripts\build-java.ps1 -MainClass "com.example.HelloJava" -Release 17
~~~

### Running on PowerShell 7

~~~powershell
pwsh -NoProfile -File ./scripts/build-java.ps1 -MainClass com.example.HelloJava -Release 17
~~~

On Linux/macOS, install PowerShell 7 and a JDK, set JAVA_HOME if needed, and then invoke pwsh. The script uses Join-Path, PSScriptRoot, and OS-specific executable names so it does not require hard-coded Windows paths.

### Output on Successful Run

On Windows PowerShell 5.1.26100.9711 and JDK 24.0.2, the test project located in a path containing spaces produced the following output:

~~~text
Compiling 2 Java source file(s) with JDK release 17
Running com.example.HelloJava
Hello from Java on PowerShell
Build and run succeeded
~~~

The script compiles both source files with javac --release 17, then runs the main class.

### Testing Exit Code Failure

Run the class that intentionally returns exit code 7:

~~~powershell
powershell.exe -NoProfile -File .\scripts\build-java.ps1 -MainClass "com.example.ExitCodeDemo"
~~~

Relevant output:

~~~text
Compiling 2 Java source file(s) with JDK release 17
Running com.example.ExitCodeDemo
intentional failure
java exited with code 7
~~~

The PowerShell script exits with a non-zero exit code (1 in this test run due to the unhandled exception). This allows CI to mark the job as failed instead of continuing as if Java succeeded.

## 8. Packaging and Running a JAR

After compiling, you can invoke jar to package the classes:

~~~powershell
$jar = Get-JdkToolPath -Name "jar"
$jarPath = Join-Path $projectRoot "build/java-demo.jar"

$jarArgs = @(
    "--create",
    "--file", $jarPath,
    "-C", $outputDirectory,
    "."
)

& $jar @jarArgs
$jarExitCode = $LASTEXITCODE

if ($jarExitCode -ne 0) {
    throw "jar failed with exit code $jarExitCode"
}
~~~

This command creates a JAR containing the class files. To run it with java -jar, the archive needs a manifest with Main-Class. You can create a manifest file and pass it to jar:

~~~text
Main-Class: com.example.HelloJava

~~~

Example of creating the manifest and packaging:

~~~powershell
$manifestPath = Join-Path $projectRoot "build/MANIFEST.MF"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$manifestContent = "Main-Class: com.example.HelloJava" + [Environment]::NewLine + [Environment]::NewLine

[System.IO.File]::WriteAllText($manifestPath, $manifestContent, $utf8NoBom)

& $jar "--create" "--file" $jarPath "--manifest" $manifestPath "-C" $outputDirectory "."
$jarExitCode = $LASTEXITCODE

if ($jarExitCode -ne 0) {
    throw "jar packaging failed with exit code $jarExitCode"
}

& $java "-jar" $jarPath
$runExitCode = $LASTEXITCODE

if ($runExitCode -ne 0) {
    throw "java -jar failed with exit code $runExitCode"
}
~~~

Paths are passed as separate arguments so they can contain spaces. Use UTF-8 without BOM for script-generated manifest files and end the manifest with a blank line according to the JAR manifest format.

## 9. Encoding and Newlines Between Windows and Unix

Encoding is a common source of bugs when scripts generate Java, properties, manifest, or checksum list files.

Windows PowerShell 5.1 and PowerShell 7 differ in behavior:

| Command | Windows PowerShell 5.1 | PowerShell 7 |
|---|---|---|
| Set-Content -Encoding UTF8 | UTF-8 with BOM | UTF-8 without BOM |
| Out-File default | UTF-16LE | UTF-8 |
| Set-Content default | System-dependent encoding | UTF-8 without BOM |

To create UTF-8 files without BOM consistently, use .NET:

~~~powershell
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

[System.IO.File]::WriteAllText(
    $filePath,
    $content,
    $utf8NoBom
)
~~~

When writing multi-line files, decide whether newlines need to be fixed. Windows typically uses CRLF, while Unix-like systems typically use LF. For Java source files, javac accepts both, but if a file is used in a reproducible build or checksum comparison, different newlines produce different byte contents.

In a repository, you can normalize line endings with .gitattributes and maintain consistent encoding.

## 10. Handling Output and Logs

PowerShell has multiple output streams: Success, Error, Warning, Verbose, Debug, and Information. Using the appropriate stream helps CI categorize logs.

~~~powershell
Write-Output "Normal build information"
Write-Warning "Optional configuration is missing"
Write-Verbose "Resolved javac path: $javac"
Write-Error "Build failed"
~~~

Enable verbose output when needed:

~~~powershell
$VerbosePreference = "Continue"
~~~

Record logs:

~~~powershell
Start-Transcript -Path "./build/powershell-build.log" -Append

try {
    & ./scripts/build-java.ps1
    $scriptExit = $LASTEXITCODE
}
finally {
    Stop-Transcript
}
~~~

Transcript records the commands and output of the PowerShell session. In CI, you can also redirect the job's stdout/stderr or upload the log as an artifact.

Do not merge stderr into stdout if the pipeline needs to distinguish the two streams. PowerShell 7 and Windows PowerShell 5.1 have some differences in how they handle native stderr; test the script on the target shell version.

## 11. Integrating PowerShell into CI

PowerShell can serve as a unified shell for Windows, Linux, and macOS jobs if the runner has PowerShell 7 installed.

### GitHub Actions

Example workflow running on Ubuntu:

~~~yaml
name: Java PowerShell build

on:
  push:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"

      - name: Build with PowerShell
        shell: pwsh
        run: ./scripts/build-java.ps1
~~~

To test on Windows or macOS, you can add corresponding jobs with windows-latest or macos-latest runners. Those runners should use the pwsh shell if you want to keep the same PowerShell version.

### GitLab CI

~~~yaml
stages:
  - build

java-build:
  stage: build
  script:
    - pwsh -NoProfile -File ./scripts/build-java.ps1
~~~

The runner needs pwsh and a JDK. If the runner only has Windows PowerShell 5.1, use powershell.exe and verify script compatibility.

### Jenkins

On an agent with PowerShell 7:

~~~groovy
pipeline {
    agent any

    stages {
        stage('Java build') {
            steps {
                pwsh './scripts/build-java.ps1'
            }
        }
    }
}
~~~

On a Windows agent using Windows PowerShell:

~~~groovy
pipeline {
    agent { label 'windows' }

    stages {
        stage('Java build') {
            steps {
                powershell '.\\scripts\\build-java.ps1'
            }
        }
    }
}
~~~

In CI, ensure the script returns a non-zero exit code when compilation or execution fails. Do not catch an exception, only call Write-Warning, and let the job continue.

## 12. Parameters, Environment, and Configuration

Do not hard-code every value into the script. Use parameters so callers or CI can choose the release, main class, and output directory.

~~~powershell
param(
    [ValidateRange(8, 99)]
    [int]$Release = 17,

    [string]$MainClass = "com.example.HelloJava",

    [string]$OutputDirectory = "./build/classes"
)
~~~

You can pass parameters:

~~~powershell
pwsh -File ./scripts/build-java.ps1 -Release 21 -MainClass com.example.HelloJava
~~~

Environment variables are suitable for CI-provided configuration:

~~~powershell
$env:JAVA_HOME
$env:CI
$env:BUILD_NUMBER
~~~

Do not store passwords, access tokens, or private keys directly in scripts or logs. Use your CI's secret store and read secrets only at the moment they are needed.

## 13. Security When Writing PowerShell Scripts

Several important principles:

- Do not use Invoke-Expression to run strings containing external data.
- Do not concatenate commands from unvalidated filenames, branch names, or inputs.
- Use argument arrays and the call operator.
- Use LiteralPath when a path might contain wildcards.
- Validate inputs before passing them to java, jar, or jcmd.
- Do not print tokens or credentials to logs.
- Do not run scripts downloaded from untrusted sources.
- Do not disable Execution Policy machine-wide just to run a single CI script.
- Pin JDK and build tool versions in release environments.
- Use signatures or provenance to verify artifacts when high security is required.

Execution Policy controls how PowerShell loads scripts on Windows. It is not a complete security boundary. On Linux/macOS, this mechanism does not have the same meaning as on Windows. For CI, use the runner's policy and manage script sources in the repository.

## 14. Common Errors

### java or javac Not Found

Check whether JAVA_HOME points to the JDK root, whether the executable exists in bin, and whether PATH includes the right JDK. Use Get-Command to see which file the shell is selecting.

### Running the Wrong Java Version

java and javac might come from different JDKs. Resolve both using the same JAVA_HOME and print their versions in CI logs.

### Paths with Spaces Cause Commands to Fail

Do not build a command as one long string. Use argument arrays and splatting. Check the project, JDK, and output paths.

### Script Reports Success Even Though Java Returned a Non-Zero Exit Code

Save LASTEXITCODE immediately after the java or javac command and check the numeric value. ErrorActionPreference does not replace this step in Windows PowerShell 5.1.

### Script Works Locally but Fails in CI

CI may have a different working directory, PATH, JAVA_HOME, user permissions, and shell version. Use PSScriptRoot to locate files, log versions, and verify tool paths.

### Script Fails to Run Due to Execution Policy

Check Get-ExecutionPolicy -List. Use a policy appropriate for your organization and runner. On Windows CI, you can set the Process scope when permitted; do not change the machine-wide policy.

### Script Works on Windows but Fails on Linux

Check path separators, casing, file permissions, executable extensions, and non-JDK dependencies. Use pwsh instead of powershell.exe on Linux/macOS.

### Java Source Has Garbled Characters After Script Creates the File

Check encoding and BOM. Windows PowerShell 5.1 writes UTF-8 with BOM when using Set-Content -Encoding UTF8; if you need UTF-8 without BOM, use UTF8Encoding(false).

### Native stderr Is Treated as a PowerShell Error

Stream differences between Windows PowerShell and PowerShell 7 can cause the pipeline to handle stderr differently. If you need to capture stderr, redirect deliberately and still check LASTEXITCODE separately.

## 15. Script Writing and Testing Workflow

1. Identify the minimum shell to support: Windows PowerShell 5.1 or PowerShell 7.
2. Choose how to invoke native tools and verify the JDK version.
3. Use PSScriptRoot and Join-Path to construct paths.
4. Use parameters instead of hard-coded configuration.
5. Use StrictMode and ErrorActionPreference for PowerShell errors.
6. Invoke javac/java using the call operator and argument arrays.
7. Check LASTEXITCODE immediately after each native command.
8. Test with project paths containing spaces.
9. Test both success paths and failure paths.
10. Run on each supported OS/shell.
11. Verify encoding, newlines, and output logs.
12. Integrate the script into CI and ensure exit codes are propagated properly by the job.

When modifying shared scripts, test on the exact PowerShell versions the repository commits to supporting. A script that runs on PowerShell 7 does not automatically prove compatibility with Windows PowerShell 5.1.

## 16. PowerShell Commands to Remember

~~~powershell
# PowerShell version
$PSVersionTable

# Locate Java tools
Get-Command java -CommandType Application
Get-Command javac -CommandType Application
Get-Command jar -CommandType Application

# Inspect JDK environment
$env:JAVA_HOME
$env:PATH

# Build paths portably
$source = Join-Path $PSScriptRoot "src"
$output = Join-Path $PSScriptRoot "build/classes"

# Find Java source files
Get-ChildItem -LiteralPath $source -Filter "*.java" -File -Recurse

# Run javac and check its exit code
& $javac "--release" "17" "-d" $output $sourceFile
$compileExitCode = $LASTEXITCODE

# Run an application
& $java "-cp" $output "com.example.HelloJava"
$runExitCode = $LASTEXITCODE

# Run a JAR
& $java "-jar" $jarPath
$jarExitCode = $LASTEXITCODE

# Check a file or directory
Test-Path -LiteralPath $output -PathType Container

# Create UTF-8 without BOM
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($filePath, $content, $utf8NoBom)

# Run scripts with the intended shell
powershell.exe -NoProfile -File .\scripts\build-java.ps1
pwsh -NoProfile -File ./scripts/build-java.ps1
~~~

PowerShell helps automate Java tooling by combining an object pipeline, functions, path APIs, and the ability to invoke native executables. To keep scripts reliable across environments, clearly choose your PowerShell version, locate the JDK from JAVA_HOME/PATH, build paths with Join-Path, pass arguments via arrays, and check LASTEXITCODE after every Java command. Then test both success and failure cases on every runner your project supports.

## References

- [PowerShell Documentation](https://learn.microsoft.com/powershell/)
- [PowerShell 7 overview](https://learn.microsoft.com/powershell/scripting/overview)
- [about Automatic Variables](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_automatic_variables)
- [about Preference Variables](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_preference_variables)
- [about Quoting Rules](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_quoting_rules)
- [about Operators](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_operators)
- [Java Compiler javac — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
- [Java Launcher — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
