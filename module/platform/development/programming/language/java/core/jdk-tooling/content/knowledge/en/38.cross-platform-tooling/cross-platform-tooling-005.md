# Cross-Platform Shell Scripts for Java Projects

Shell scripts automate tasks around Java applications: checking the JDK, compiling source code, running Maven, building artifacts, running tests, and packaging releases. A script that runs well on a developer's machine is not guaranteed to run on Windows, Linux, and macOS because each environment has different shells, path conventions, quoting rules, and argument-passing behavior.

To build cross-platform tooling, you must first identify the target interpreter. Bash/POSIX shell fits Linux, macOS, Git Bash, or WSL; PowerShell 7 can run on Windows, Linux, and macOS; Windows PowerShell 5.1 is only available on Windows. A Bash script cannot run directly in PowerShell, and vice versa. Projects often provide a pair of scripts per shell or use Maven Wrapper to reduce the number of OS-dependent commands.

This article covers how to organize scripts, handle paths/arguments/environments, check exit codes, run Java/Maven safely, standardize line endings, and test on CI. The final example uses a Java 17+ program together with two launchers—Bash and PowerShell—that have identical behavior.

## 1. What are shell scripts used for in Java tooling?

A shell script is a text program read and executed by a command interpreter. In Java projects, scripts typically handle:

- Checking Java/JDK/Maven before building.
- Selecting the JDK via JAVA_HOME or PATH.
- Invoking javac, java, javadoc, or jcmd.
- Running Maven Wrapper with standardized parameters.
- Preparing output directories and configuring the environment.
- Running tests, creating packages, or building images.
- Returning the proper exit code so CI knows whether the build succeeded or failed.
- Collecting logs and cleaning up temporary resources.

Scripts should orchestrate existing tools. Complex business logic, data processing, or critical build rules should usually live in Java, a Maven plugin, or a dedicated tool so they are easier to test and less dependent on the shell.

## 2. Choosing a shell and defining the support scope

Common shells have different syntax and runtimes:

| Shell | Common platforms | Notes |
|---|---|---|
| POSIX sh | Linux, Unix, macOS | Basic syntax, suitable for scripts needing broad compatibility |
| Bash | Linux, macOS, Git Bash, WSL | Has arrays, [[ ]], pipefail, and many shell-specific utilities |
| PowerShell 7 (pwsh) | Windows, Linux, macOS | Cross-platform shell with an object pipeline and .NET APIs |
| Windows PowerShell 5.1 | Windows | Legacy version bundled with Windows; not available on Linux/macOS |
| cmd.exe / batch | Windows | Separate syntax, commonly used for .bat/.cmd files |

Do not write a single file and expect every shell to understand the same syntax. Choose one of these strategies:

1. Provide separate scripts: run.sh and run.ps1, both invoking a single Java/Maven task.
2. Use PowerShell 7 if the organization has standardized pwsh across all runners.
3. Use Maven Wrapper to standardize build commands, leaving the script to handle only environment checks.
4. Move critical cross-platform logic into Java or a Maven plugin instead of the shell.

State the minimum shell version clearly in the README and CI. If you use Bash arrays, pipefail, or BASH_SOURCE, the script must require Bash and cannot declare itself as POSIX sh.

## 3. Shebang and how to launch scripts

A shebang is the first line of a file on Unix-like systems, specifying the interpreter:

~~~bash
#!/usr/bin/env bash
~~~

This line locates bash via PATH. Common ways to invoke it:

~~~bash
chmod +x scripts/run.sh
./scripts/run.sh
~~~

Or invoke the interpreter directly:

~~~bash
bash scripts/run.sh
~~~

If the script uses POSIX sh syntax, you can declare:

~~~sh
#!/bin/sh
~~~

For PowerShell, the explicit way to invoke it is:

~~~powershell
pwsh -File ./scripts/run.ps1
~~~

On Windows PowerShell 5.1:

~~~powershell
powershell.exe -NoProfile -File .\scripts\run.ps1
~~~

PowerShell 7 can run across multiple OSes; Windows PowerShell 5.1 only runs on Windows. A PowerShell shebang on Unix-like systems only matters when pwsh is installed and the file has execute permission. On Windows, use pwsh -File or powershell.exe -File.

Git Bash and WSL provide Unix-like environments on Windows. They are not PowerShell and not Windows CMD. You need to check JAVA_HOME paths in the format that the Bash environment understands.

## 4. POSIX sh and Bash are not identical

If a script needs to run across multiple Unix shells, stick to POSIX syntax:

- Use [ ... ] instead of [[ ... ]].
- Avoid Bash arrays and process substitution.
- Do not use pipefail if compatibility with every /bin/sh is required.
- Do not use BASH_SOURCE; POSIX shell only has $0.
- Avoid relying on GNU-only flags if the script also runs on macOS/BSD.
- Use command -v to locate executables.
- Always quote variables containing paths and arguments.

If you have chosen Bash, declare the shebang explicitly and optionally enable:

~~~bash
set -Eeuo pipefail
~~~

Here -e exits when certain commands fail, -u reports an error when reading an unset variable, and pipefail causes a pipeline to fail if any intermediate command fails. Bash has exceptions for set -e in conditionals, loops, and pipelines; for critical steps, you should still check the exit code explicitly.

Do not set a /bin/sh shebang and then use Bash syntax. On some systems /bin/sh is dash or another POSIX shell and will throw a syntax error.

## 5. Quoting and passing arguments with spaces

The most common shell script bug is splitting a path or argument into multiple parts due to missing quotes.

Bash:

~~~bash
java -cp "$CLASSPATH" demo.App "$@"
~~~

"$@" passes each original argument as a separate argument, even when it contains spaces. Do not use unquoted $@ or "$*" if you want to preserve argument boundaries.

PowerShell:

~~~powershell
& $javaExe -cp $classPath demo.App @AppArgs
~~~

@AppArgs splats the argument array into separate arguments. Quote paths with spaces and verify how PowerShell passes arguments to native executables.

Example invocation:

~~~powershell
./scripts/run.ps1 "hello world" "two words"
~~~

The application must receive exactly two arguments:

~~~text
arg[0]=<hello world>
arg[1]=<two words>
~~~

Quoting rules in Bash and PowerShell differ. Bash uses single quotes to keep literals and double quotes while still allowing variable/command expansion. PowerShell uses single quotes for literal strings and double quotes for expandable strings. Backslash is not PowerShell's general escape character; PowerShell uses backtick for escaping inside strings.

PowerShell 7.3 changed how arguments are passed to native commands compared to Windows PowerShell 5.1. If a script relies on arguments with nested quotes or empty strings, test it on the exact PowerShell version you support. Avoid building a command string manually and calling eval or Invoke-Expression.

## 6. Paths: working directory differs from script directory

The working directory is the current directory where the user runs the command. The script directory is where the script file resides. These two directories can be different.

Do not assume the user always runs the script from the repository root. Determine the root based on the script's location.

Bash:

~~~bash
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
~~~

PowerShell:

~~~powershell
$scriptDir = $PSScriptRoot
$projectRoot = Split-Path -Parent $scriptDir
~~~

Use Join-Path, Split-Path, and Resolve-Path in PowerShell; use dirname, cd, and pwd -P in Bash. Avoid concatenating paths manually with slashes when you can use the shell's path APIs.

Notes:

- Quote every path that might contain whitespace.
- Do not hardcode usernames or home directories.
- Do not assume Windows paths can be used directly in Bash.
- Do not rely on paths relative to the current terminal.
- Verify that files/directories exist before running.
- Use absolute paths for critical input files after determining the project root.

Git Bash typically represents Windows drives as /c/Users/...; a JAVA_HOME like C:\Program Files\... may need conversion with cygpath -u before being used in Bash. PowerShell uses Windows paths directly.

## 7. Environment variables and JDK configuration

Java tools commonly use environment variables:

| Variable | Purpose |
|---|---|
| JAVA_HOME | Root of the JDK/JRE selected by environment convention |
| PATH | List of directories where the shell searches for executables |
| MAVEN_HOME | May point to the Maven installation if used by the environment |
| MAVEN_OPTS | JVM options for the Maven process |
| JDK_JAVA_OPTIONS | JVM options appended by the Java launcher |
| JAVA_TOOL_OPTIONS | JVM options picked up by the VM on initialization |

JAVA_HOME should point to the JDK root directory, not bin or java.exe. If compilation is needed, javac must exist in the bin directory.

Bash sets environment variables for child processes using export:

~~~bash
export JAVA_HOME="/opt/jdk-17"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

PowerShell:

~~~powershell
$env:JAVA_HOME = 'C:\Java\jdk-17'
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
~~~

Environment changes inside a script normally affect only the current process and child processes, without permanently modifying user/system configuration. Do not overwrite the entire PATH; prepend or append the needed directory according to project policy.

Do not trust that JAVA_HOME is valid just because the variable is set. Verify that java and javac actually exist inside it, and print their versions when diagnostics are needed.

## 8. Selecting java/javac and checking the JDK

Bash on Linux/macOS can select the JDK from JAVA_HOME or PATH:

~~~bash
if [[ -n "${JAVA_HOME:-}" ]]; then
  JAVA="$JAVA_HOME/bin/java"
  JAVAC="$JAVA_HOME/bin/javac"
else
  JAVA="$(command -v java || true)"
  JAVAC="$(command -v javac || true)"
fi

if [[ -z "$JAVA" || ! -x "$JAVA" ]]; then
  printf '%s\n' "Cannot find executable java" >&2
  exit 2
fi

if [[ -z "$JAVAC" || ! -x "$JAVAC" ]]; then
  printf '%s\n' "Cannot find executable javac; install a JDK" >&2
  exit 2
fi
~~~

PowerShell can find an executable in PATH using Get-Command:

~~~powershell
$javaCommand = Get-Command java -CommandType Application -ErrorAction Stop
$javaExe = $javaCommand.Source
~~~

If JAVA_HOME is set, join the path to bin/java or bin/java.exe depending on the OS and check it with Test-Path -LiteralPath.

In Git Bash on Windows, executables usually have the .exe suffix and JAVA_HOME may be in Windows path format. The Bash script needs to select java.exe/javac.exe and convert JAVA_HOME to a POSIX path using cygpath -u. The complete example in section 15 illustrates both points.

Do not rely solely on java -version output if the script needs javac. A runtime-only installation can run Java but cannot compile. Running javac -version confirms the compiler is present.

## 9. Invoking Maven and Maven Wrapper

Maven Wrapper provides two launchers in the repository:

- mvnw for Unix-like shells.
- mvnw.cmd for Windows CMD/PowerShell.

In Bash:

~~~bash
"$PROJECT_ROOT/mvnw" -f "$PROJECT_ROOT/pom.xml" clean verify
~~~

In PowerShell:

~~~powershell
& (Join-Path $projectRoot 'mvnw.cmd') -f (Join-Path $projectRoot 'pom.xml') clean verify
$buildExit = $LASTEXITCODE
if ($buildExit -ne 0) {
    exit $buildExit
}
~~~

The wrapper pins the Maven distribution via .mvn/wrapper/maven-wrapper.properties. It does not install a JDK automatically and does not replace controlling JAVA_HOME or Maven Toolchains.

On Unix-like systems, the executable bit on mvnw must be preserved. When cloning on Windows, Git may not preserve the executable bit in every configuration; invoke bash ./mvnw if needed or check the file mode in Git.

## 10. Exit codes and error handling

Standard conventions for command-line tools:

- Exit code 0: success.
- Non-zero exit code: failure or a special status.
- Bash stores the exit status of the most recent command in $?.
- PowerShell uses $LASTEXITCODE for native executables and $? for the success status of the most recent command.

Always read the exit code immediately after a native command. If you run another command before saving it, $LASTEXITCODE may have changed.

Bash:

~~~bash
javac --release 17 -d "$BUILD_DIR" "$SOURCE_FILE"
compile_status=$?
if (( compile_status != 0 )); then
  exit "$compile_status"
fi
~~~

PowerShell:

~~~powershell
& $javacExe --release 17 -d $buildDir $sourceFile
$compileExit = $LASTEXITCODE
if ($compileExit -ne 0) {
    exit $compileExit
}
~~~

In PowerShell, $ErrorActionPreference = 'Stop' turns many non-terminating cmdlet errors into terminating errors. It does not replace checking $LASTEXITCODE after calling java.exe, javac.exe, or mvnw.cmd.

Do not use echo/Write-Host to report an error while still returning exit code 0. CI relies on the exit code, not on wording in the logs.

## 11. Pipelines, traps, and cleanup

A pipeline can hide a failure in an earlier command if you only check the final status.

Bash can enable pipefail:

~~~bash
set -o pipefail
some_command | tee build.log
~~~

PowerShell pipelines pass objects between cmdlets; when invoking native executables through a pipeline, check exit codes and handle stderr/stdout appropriately.

Cleaning up temporary files and processes requires a cleanup mechanism:

Bash:

~~~bash
TEMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf -- "$TEMP_DIR"
}
trap cleanup EXIT
~~~

PowerShell:

~~~powershell
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempDir | Out-Null
try {
    # Run the build steps.
}
finally {
    if (Test-Path -LiteralPath $tempDir) {
        Remove-Item -LiteralPath $tempDir -Recurse -Force
    }
}
~~~

Only delete temporary directories created by the script itself and stored in a validated variable. Never run rm -rf or Remove-Item on an empty path, a root path, or an unverified variable.

## 12. Encoding, line endings, and executable bit

Cross-platform scripts often break due to incorrect line endings or encoding.

- Bash scripts should use UTF-8 and LF.
- PowerShell 7 reads UTF-8 well; Windows PowerShell 5.1 differs in default encoding, especially for non-ASCII files.
- Avoid smart quotes or unusual Unicode characters in scripts.
- If Windows PowerShell 5.1 compatibility is required, check file encoding and prefer UTF-8 with BOM when non-ASCII characters are present.
- Git can normalize line endings using .gitattributes.
- Bash scripts need the executable bit if run directly via ./script.sh.

Example .gitattributes:

~~~text
*.sh text eol=lf
*.ps1 text eol=crlf
*.bat text eol=crlf
~~~

You can use LF for PowerShell 7 across all platforms; if Windows PowerShell 5.1 is needed, agree on encoding and line endings with the team and test on the target host.

If Bash reports /usr/bin/env: bash\r: No such file or directory, the file likely uses CRLF and the carriage return character was included in the shebang. Convert the .sh file to LF.

## 13. Security when passing input to the shell

The shell performs expansion, quote removal, and metacharacter interpretation before executing a command. If untrusted input is concatenated into a command string, data may be interpreted as commands or options.

Principles:

- Pass arguments separately; do not concatenate them into a single command string.
- Quote variables in Bash and use argument arrays/splatting in PowerShell.
- Do not use eval or Invoke-Expression with user-supplied data.
- Validate path values before deleting or writing files.
- Do not print tokens/passwords or sensitive environment variables to logs.
- Do not pass secrets on the command line if the process list is readable.
- Use an allowlist for profile, task, or environment names.
- Do not download and execute scripts from unverified URLs.

Safer Bash example:

~~~bash
java -cp "$CLASSPATH" demo.App "$USER_INPUT"
~~~

PowerShell example:

~~~powershell
& $javaExe -cp $classPath demo.App $UserInput
~~~

If input must be passed as multiple arguments, use an array and preserve argument boundaries. Do not manually escape by replacing spaces or quotes and then concatenating into a command string.

## 14. Shared Java example for both shells

Create src/main/java/demo/ArgsDemo.java:

~~~java
package demo;

public final class ArgsDemo {
    private ArgsDemo() {
    }

    public static void main(String[] args) {
        System.out.println("Arguments: " + args.length);
        for (int i = 0; i < args.length; i++) {
            System.out.println("arg[" + i + "]=<" + args[i] + ">");
        }
    }
}
~~~

The program prints the argument count and each value wrapped in angle brackets so it is easy to verify whether the shell preserved strings containing spaces.

The program is shell-independent. The same class can be invoked from Bash, PowerShell, CMD, Maven, or CI.

## 15. Bash launcher example: scripts/run.sh

Create scripts/run.sh in the repository:

~~~bash
#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
SOURCE_FILE="$PROJECT_ROOT/src/main/java/demo/ArgsDemo.java"
BUILD_DIR="$PROJECT_ROOT/build/classes"

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    JAVA_NAME=java.exe
    JAVAC_NAME=javac.exe
    if [[ -n "${JAVA_HOME:-}" ]] && command -v cygpath >/dev/null 2>&1; then
      JAVA_HOME="$(cygpath -u "$JAVA_HOME")"
    fi
    ;;
  *)
    JAVA_NAME=java
    JAVAC_NAME=javac
    ;;
esac

if [[ -n "${JAVA_HOME:-}" ]]; then
  JAVA="$JAVA_HOME/bin/$JAVA_NAME"
  JAVAC="$JAVA_HOME/bin/$JAVAC_NAME"
else
  JAVA="$(command -v java || true)"
  JAVAC="$(command -v javac || true)"
fi

if [[ -z "$JAVA" || ! -x "$JAVA" ]]; then
  printf '%s\n' "Cannot find java. Set JAVA_HOME or update PATH." >&2
  exit 2
fi

if [[ -z "$JAVAC" || ! -x "$JAVAC" ]]; then
  printf '%s\n' "Cannot find javac. Install a JDK and set JAVA_HOME." >&2
  exit 2
fi

if [[ ! -f "$SOURCE_FILE" ]]; then
  printf 'Source file not found: %s\n' "$SOURCE_FILE" >&2
  exit 2
fi

mkdir -p "$BUILD_DIR"
"$JAVAC" --release 17 -encoding UTF-8 -d "$BUILD_DIR" "$SOURCE_FILE"

exec "$JAVA" -cp "$BUILD_DIR" demo.ArgsDemo "$@"
~~~

Explanation:

- BASH_SOURCE[0] retrieves the path of the current script file.
- PROJECT_ROOT is computed relative to the scripts directory.
- On Git Bash, the script selects java.exe/javac.exe and converts a Windows-style JAVA_HOME path using cygpath -u.
- On Linux/macOS/WSL, the script uses java/javac without the .exe suffix.
- JAVA_HOME takes precedence; if unset, it looks up java/javac in PATH.
- All paths are quoted.
- javac uses release 17 and UTF-8.
- exec replaces the shell process with the Java process; Java's exit code becomes the script's exit code.
- "$@" preserves each argument passed by the caller.

Grant execute permission on Linux/macOS/Git Bash:

~~~bash
chmod +x scripts/run.sh
~~~

Run:

~~~bash
./scripts/run.sh "hello world" "two words"
~~~

## 16. PowerShell launcher example: scripts/run.ps1

Create scripts/run.ps1:

~~~powershell
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $AppArgs
)

$ErrorActionPreference = 'Stop'

$scriptDir = $PSScriptRoot
$projectRoot = Split-Path -Parent $scriptDir
$sourceFile = Join-Path $projectRoot 'src/main/java/demo/ArgsDemo.java'
$buildDir = Join-Path $projectRoot 'build/classes'

if ($env:OS -eq 'Windows_NT') {
    $javaRelative = 'bin/java.exe'
    $javacRelative = 'bin/javac.exe'
}
else {
    $javaRelative = 'bin/java'
    $javacRelative = 'bin/javac'
}

if (-not [string]::IsNullOrWhiteSpace($env:JAVA_HOME)) {
    $javaExe = Join-Path $env:JAVA_HOME $javaRelative
    $javacExe = Join-Path $env:JAVA_HOME $javacRelative
}
else {
    $javaCommand = Get-Command java -CommandType Application -ErrorAction Stop
    $javacCommand = Get-Command javac -CommandType Application -ErrorAction Stop
    $javaExe = $javaCommand.Source
    $javacExe = $javacCommand.Source
}

if (-not (Test-Path -LiteralPath $javaExe -PathType Leaf)) {
    throw "Cannot find java executable: $javaExe"
}
if (-not (Test-Path -LiteralPath $javacExe -PathType Leaf)) {
    throw "Cannot find javac executable: $javacExe"
}
if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) {
    throw "Source file not found: $sourceFile"
}

New-Item -ItemType Directory -Path $buildDir -Force | Out-Null

& $javacExe --release 17 -encoding UTF-8 -d $buildDir $sourceFile
$compileExit = $LASTEXITCODE
if ($compileExit -ne 0) {
    exit $compileExit
}

& $javaExe -cp $buildDir demo.ArgsDemo @AppArgs
$runExit = $LASTEXITCODE
exit $runExit
~~~

Explanation:

- PSScriptRoot determines the script location independently of the working directory.
- Join-Path handles OS-specific path separators.
- JAVA_HOME is used if set; otherwise, Get-Command locates the executables.
- The & operator invokes an executable from a resolved path.
- @AppArgs passes the argument array as separate arguments.
- $LASTEXITCODE is saved immediately after each native executable.
- exit returns the javac or Java exit code to the caller/CI.

Run on Windows:

~~~powershell
powershell.exe -NoProfile -File .\scripts\run.ps1 "hello world" "two words"
~~~

Run on PowerShell 7:

~~~powershell
pwsh -NoProfile -File ./scripts/run.ps1 "hello world" "two words"
~~~

On Linux/macOS, install a JDK and PowerShell 7 and use pwsh. Windows PowerShell 5.1 is not an interpreter for Linux/macOS.

## 17. Expected output and argument verification

Run either the Bash or PowerShell launcher with two arguments: hello world and two words.

Java stdout:

~~~text
Arguments: 2
arg[0]=<hello world>
arg[1]=<two words>
~~~

If the output shows four arguments instead of two, the script split the arguments during expansion. If Java receives quote characters as part of the value, the shell or native invocation is passing quotes incorrectly.

You can check the exit code after running:

Bash:

~~~bash
./scripts/run.sh "hello world"
printf 'exit=%s\n' "$?"
~~~

PowerShell:

~~~powershell
& ./scripts/run.ps1 "hello world"
$scriptExit = $LASTEXITCODE
Write-Output "exit=$scriptExit"
~~~

When a launcher uses exit, run it as a separate process to check the exit code from the calling shell. In PowerShell, if a script is invoked directly with &, distinguish PowerShell exceptions from the exit code of a native process.

## 18. CI matrix and multi-OS testing

A cross-platform script must be executed on each target environment. Portability cannot be proven merely by reading the code on Windows.

CI should include a minimal matrix for the OSes actually supported:

| Runner | Shells to test |
|---|---|
| Ubuntu | Bash, and PowerShell 7 if supported |
| macOS | The runner's default Bash, and PowerShell 7 if supported |
| Windows | PowerShell 7/5.1 per policy, and Git Bash if supported by the project |

Each job should:

1. Check out a clean source tree.
2. Install the pinned JDK version.
3. Print java -version and javac -version.
4. Run shell syntax/lint checks.
5. Run the launcher from a working directory other than the project root.
6. Pass arguments containing spaces and special characters.
7. Verify stdout and the exit code.
8. Run the project's actual build/tests.
9. Collect logs on failure.

Use ShellCheck to lint Bash and PSScriptAnalyzer to lint PowerShell. A CI matrix helps catch differences across shell versions, paths, encodings, and native argument passing.

## 19. Common errors and fixes

| Symptom | Common cause | Fix |
|---|---|---|
| bad interpreter or bash\r not found | Bash script uses CRLF | Convert .sh to LF |
| Permission denied when running ./run.sh | Missing executable bit | Run chmod +x and commit the file mode |
| java runs but javac is not found | Only a runtime is installed or JAVA_HOME is wrong | Install a full JDK and check bin/javac |
| Paths with spaces get split | Missing quotes or improper argument passing | Quote paths and use "$@" / @array |
| Script only works from project root | Relative paths tied to terminal cwd | Compute project root from script location |
| Maven uses the wrong Java | JAVA_HOME/PATH or toolchain differs from expected | Print mvn -version and check toolchain logs |
| PowerShell reports command not found | Wrong executable path or command type | Use Get-Command and check Source/Path |
| CI always reports success despite javac failure | Exit code not propagated | Check $LASTEXITCODE or $? immediately after the command |
| Bash script fails on macOS | Uses GNU-only commands/options | Use POSIX-compatible commands or install pinned dependencies |
| Git Bash does not read JAVA_HOME | JAVA_HOME uses Windows path syntax | Use POSIX paths or convert with cygpath |
| PowerShell 5.1 and 7 pass args differently | Differences in native argument passing | Test on the exact version and keep argument arrays |
| Script works locally but fails in CI | Different shell/JDK/working directory/environment | Pin versions, log environment, and run a CI matrix |

## 20. Best practices for shell tooling

- State the interpreter and minimum version clearly.
- Keep Bash and PowerShell scripts short and focused on orchestration.
- Compute the project root from the script's location.
- Quote paths and pass arguments using arrays.
- Validate JAVA_HOME rather than blindly trusting the environment variable.
- Check javac separately if compilation is required.
- Save the exit code of native commands immediately after execution.
- Do not mix POSIX, Bash, PowerShell, and CMD syntax.
- Do not hardcode absolute paths or usernames.
- Standardize encoding and line endings.
- Pin Maven/JDK/plugins via Wrapper, Toolchains, and build configuration.
- Never use eval/Invoke-Expression with untrusted input.
- Clean up temporary files with trap or try/finally.
- Run ShellCheck/PSScriptAnalyzer and a CI matrix.
- Write clear output, send errors to stderr, and return a non-zero exit code on failure.

## 21. Cross-platform shell script checklist

- [ ] Target OSes and shells are defined.
- [ ] Bash scripts have the proper shebang; PowerShell scripts have a clear invocation method.
- [ ] No Bash syntax is used in scripts declared as POSIX sh.
- [ ] Working directory does not affect how the project root is located.
- [ ] Paths with spaces are properly quoted.
- [ ] Arguments with spaces are preserved using "$@" or arrays.
- [ ] JAVA_HOME points to the correct JDK root.
- [ ] java and javac are checked independently.
- [ ] Maven Wrapper is invoked appropriately for the OS.
- [ ] Exit codes from native commands are propagated to the caller.
- [ ] Pipelines and cleanup are handled explicitly.
- [ ] Scripts do not concatenate input into command strings for eval.
- [ ] .sh files use LF and have the executable bit set when needed.
- [ ] .ps1 file encoding matches the target PowerShell version.
- [ ] Scripts are linted with ShellCheck/PSScriptAnalyzer.
- [ ] CI matrix runs on all declared OSes/shells.
- [ ] Tests include paths with spaces and arguments with special characters.
- [ ] Build logs record the JDK, Maven, and shell versions.

Cross-platform shell scripts require respecting differences in interpreters, paths, quoting, environments, and exit codes. Use separate scripts for Bash and PowerShell when needed, keep application logic in Java/Maven, and verify on the exact supported OSes/shells. A solid launcher always finds the right project root, preserves arguments, verifies the JDK, and returns the exact result of the build command.

## References

- GNU Bash Reference Manual — Quoting: https://www.gnu.org/software/bash/manual/html_node/Quoting.html
- GNU Bash Reference Manual — Shell Expansions: https://www.gnu.org/software/bash/manual/html_node/Shell-Expansions.html
- GNU Bash Reference Manual: https://www.gnu.org/software/bash/manual/bash.html
- Microsoft Learn — PowerShell about_Quoting_Rules: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_quoting_rules
- Microsoft Learn — PowerShell about_Parsing: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing
- Microsoft Learn — PowerShell about_Automatic_Variables: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_automatic_variables
- Microsoft Learn — PowerShell about_Environment_Variables: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_environment_variables
- Apache Maven — Maven Wrapper: https://maven.apache.org/tools/mavenwrapper.html
- Oracle Java SE 17 — The java Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
