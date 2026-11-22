# javac Not Found Error: Checking JDK, JAVA_HOME, and PATH

The **javac not found error** occurs when a shell, IDE, or build runner cannot locate the Java compiler at the location the current environment is searching. On Windows, the message is typically “javac is not recognized as the name of a cmdlet” or “not recognized as an internal or external command”. On Linux/macOS, it is typically “javac: command not found”.

javac is the Java compiler, located in the JDK's bin directory. A machine can run java -version successfully and still not have javac on PATH: the runtime may have been installed separately, the JDK may not have been added to PATH yet, or PATH may be pointing to a different Java installation.

An effective way to diagnose this is to check three things in order: whether a JDK is actually installed, whether the compiler file exists in that JDK, and whether the current shell finds that exact file.

## 1. Distinguishing java and javac

| Command | Function | Use when |
|---|---|---|
| java | Launches the JVM to run an application/class/JAR | Running a Java program |
| javac | Compiles .java source into .class bytecode | Developing and building Java source |
| jar | Creates, inspects, or manipulates Java archives | Packaging a JAR |
| jshell | Interactive REPL for Java | Testing expressions and small code snippets |

A full JDK contains the javac compiler in its bin directory. A runtime-only package or custom runtime image may only include the components needed to run applications. Therefore, the two commands below answer two different questions:

~~~bash
java -version
javac -version
~~~

If java -version succeeds but javac -version fails, you cannot conclude that Java is fully installed for development.

javac belongs to the jdk.compiler module. A custom runtime image created with jlink can omit this module to reduce size; such an image can run applications but does not provide a compiler. Oracle describes jdk.compiler as the module that implements the system Java compiler and the javac command-line tool.

## 2. Understanding JAVA_HOME and PATH

JAVA_HOME should point to the **JDK root directory**. PATH needs to contain the bin directory inside the JDK so the shell can find javac.

Example on Windows:

~~~text
JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-17
PATH=...;%JAVA_HOME%\bin;...
~~~

Example on Linux:

~~~text
JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
PATH=...:$JAVA_HOME/bin:...
~~~

Example on macOS:

~~~text
JAVA_HOME=/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home
PATH=...:$JAVA_HOME/bin:...
~~~

Do not set JAVA_HOME to the path of bin, javac.exe, or java.exe. Setting the root directory properly helps Maven, Gradle, IDEs, and Java tools locate JDK components automatically.

PATH is the list of directories the OS/shell searches for executables. Windows separates entries with semicolons; Linux and macOS separate them with colons. When multiple JDKs are present, the entry that appears first can determine which version of javac is invoked.

JAVA_HOME by itself does not make the shell find the javac command. Tools that read JAVA_HOME can use that variable directly; when you type javac, however, the shell still needs to find JAVA_HOME/bin in PATH, or you must invoke the compiler using its full path.

## 3. Quick Diagnosis Before Changing Configuration

Record both the Java runtime and compiler versions:

~~~bash
java -version
javac -version
~~~

Next, identify which executable the shell is selecting.

Windows PowerShell:

~~~powershell
$env:JAVA_HOME
Get-Command javac -All
where.exe javac
where.exe java
~~~

Windows cmd.exe:

~~~bat
echo %JAVA_HOME%
where javac
where java
~~~

Linux/macOS:

~~~bash
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
command -v javac
type -a javac
command -v java
type -a java
~~~

In PowerShell, where is an alias for Where-Object in many versions; use where.exe to invoke the Windows file-search utility. Get-Command javac -All also helps detect aliases, functions, or duplicate executables with the same name.

If the lookup command returns multiple paths, inspect each path and its priority order. The goal is for java and javac to belong to the same JDK required by the project.

## 4. Checking the Compiler File Inside the JDK

If JAVA_HOME is already set, verify the actual file before modifying PATH.

PowerShell:

~~~powershell
$javacPath = Join-Path $env:JAVA_HOME 'bin\javac.exe'
Test-Path $javacPath
& $javacPath -version
~~~

cmd.exe:

~~~bat
if exist "%JAVA_HOME%\bin\javac.exe" (
  "%JAVA_HOME%\bin\javac.exe" -version
) else (
  echo javac.exe was not found under JAVA_HOME
)
~~~

Linux/macOS:

~~~bash
test -x "$JAVA_HOME/bin/javac" && "$JAVA_HOME/bin/javac" -version
ls -l "$JAVA_HOME/bin/javac"
~~~

If the file exists and invoking it by full path succeeds, the compiler is installed. The issue usually lies in PATH, the shell session, or the ordering of JDKs.

If the file does not exist, re-check JAVA_HOME. If the path is right but bin/javac is still missing, the package in use may be runtime-only or a custom runtime image. Install a full JDK.

## 5. Temporary Fix in Windows PowerShell

To test quickly in the current PowerShell window, set JAVA_HOME to the actual JDK directory and prepend bin to PATH:

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Eclipse Adoptium\jdk-17'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java -version
javac -version
Get-Command javac -All
~~~

Replace the example path with the JDK directory installed on your machine. Quote the value when assigning so PowerShell preserves spaces in the path.

This configuration only affects the current PowerShell session and child processes launched from it. When the window closes, this session change is lost. It is a good way to confirm the root cause before making permanent changes.

## 6. Permanent Fix on Windows 10/11

1. Open Start and search for Edit the system environment variables.
2. Click Environment Variables.
3. Create or edit the JAVA_HOME variable under User variables or System variables.
4. Set its value to the JDK root directory, for example C:\Program Files\Eclipse Adoptium\jdk-17.
5. Select the Path variable, click Edit, and add %JAVA_HOME%\bin.
6. Place the desired JDK entry above older Java paths if multiple installations exist.
7. Confirm the dialogs and open a new terminal.

Verify in the new terminal:

~~~powershell
$env:JAVA_HOME
where.exe javac
where.exe java
javac -version
java -version
~~~

If using cmd.exe:

~~~bat
echo %JAVA_HOME%
where javac
javac -version
java -version
~~~

Close and reopen the terminal after changing Environment Variables because new processes inherit their environment when launched. An IDE opened before editing PATH may also retain the old environment; restart the IDE and re-check its integrated terminal.

Do not use setx PATH "%PATH%;..." carelessly to modify PATH. That approach can create duplicate entries, save already-expanded values, or truncate part of PATH in some Windows environments. Use the Environment Variables UI to make permanent edits while preserving existing entries.

## 7. Installing a JDK on Windows When Only a Runtime Is Present

If JAVA_HOME\bin\javac.exe does not exist, install a JDK from a trusted provider such as Eclipse Temurin, Oracle JDK, Microsoft Build of OpenJDK, or Azul Zulu.

Choose the right:

- Java version required by the project, such as 17 or 21.
- Machine architecture, typically x64 or ARM64.
- JDK package, which includes the compiler and development tools.
- Vendor and update release aligned with project policy.

After installation, identify the actual installation directory. Oracle JDK on Windows typically installs under C:\Program Files\Java\jdk-<FEATURE>; other vendors may use their own directories. Point JAVA_HOME to that exact directory and add bin to PATH.

You do not need to uninstall an older runtime just to install a JDK. If multiple Java installations exist, use where.exe java and where.exe javac to see which one is selected first.

## 8. Fixing on Linux

First, identify the shell and executable currently in use:

~~~bash
echo "$SHELL"
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
command -v javac || echo "javac is not on PATH"
type -a javac
ls -ld "$JAVA_HOME" "$JAVA_HOME/bin" 2>/dev/null
~~~

If a JDK is already present but PATH is missing bin, test fixing it in the current terminal:

~~~bash
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
~~~

The path /usr/lib/jvm/java-17-openjdk-amd64 is a common example on Ubuntu/Debian x86-64; the directory name depends on the distro, architecture, and vendor. Verify the actual directory before assigning it.

In Bash, permanent configuration usually goes in ~/.bashrc for interactive shells or ~/.profile for login environments. Add the two appropriate export lines to the file your terminal reads, then reload it:

~~~bash
source ~/.bashrc
~~~

If you use a login shell and placed the variables in ~/.profile, open a new login session or source the corresponding file. For Zsh, check ~/.zprofile and ~/.zshrc depending on how your terminal starts the shell.

## 9. Installing a JDK on Ubuntu/Debian

To install the OpenJDK 17 development kit:

~~~bash
sudo apt update
sudo apt install openjdk-17-jdk
~~~

The openjdk-17-jdk package provides the development toolkit, including javac. Runtime-only packages such as openjdk-17-jre are designed for running Java and may not include the compiler.

Verify:

~~~bash
javac -version
java -version
command -v javac
readlink -f "$(command -v javac)"
~~~

If the machine has multiple OpenJDK versions, Debian/Ubuntu can manage the active choice with update-alternatives:

~~~bash
sudo update-alternatives --display javac
sudo update-alternatives --config javac
sudo update-alternatives --display java
~~~

Select the compiler and runtime that match the project's version. update-alternatives is a mechanism on Debian/Ubuntu systems; other distros may use their own package manager or version management tool.

## 10. Fixing on macOS

Oracle JDK is typically installed under:

~~~text
/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home
~~~

To list installed JDKs:

~~~bash
/usr/libexec/java_home -V
~~~

Select JDK 17 for the current terminal:

~~~bash
export JAVA_HOME=$(/usr/libexec/java_home -v 17)
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
command -v javac
~~~

/usr/libexec/java_home selects a JDK by version and returns the actual home path. If the command reports that JDK 17 is not found, install JDK 17 first or select a version that is already installed.

For permanent configuration in Zsh, you can add the export lines to ~/.zprofile (login shell) or the startup file appropriate for your terminal. Then open a new terminal and verify again. On Intel and Apple Silicon macOS, make sure to download the JDK package matching your architecture.

## 11. Selecting the Right JDK When Multiple Versions Are Installed

When a machine has Java 8, 11, 17, and 21, having multiple JDKs installed does not automatically guarantee the shell is using the version you want.

Windows:

~~~powershell
where.exe java
where.exe javac
$env:JAVA_HOME
Get-Command javac -All
~~~

Linux:

~~~bash
type -a java
type -a javac
readlink -f "$(command -v java)"
readlink -f "$(command -v javac)"
~~~

macOS:

~~~bash
/usr/libexec/java_home -V
/usr/libexec/java_home -v 17
~~~

Compare the actual paths of java and javac. If the two commands point to different JDKs, reorder PATH or select the JDK explicitly via JAVA_HOME.

In Bash, the shell may cache resolved executable paths. After changing PATH, run:

~~~bash
hash -r
command -v javac
~~~

In Zsh, you can use rehash. If you still see the old path, open a new terminal and check whether startup files are prepending another PATH entry.

## 12. javac Exists, Yet the Terminal Still Reports It Not Found

This situation is usually caused by one of the following:

- PATH contains JAVA_HOME instead of JAVA_HOME/bin.
- PATH contains the bin directory of a runtime-only package.
- PATH has an older JDK or a shim directory ahead of the right JDK.
- JAVA_HOME contains literal quotes or mistakenly points into bin.
- The terminal/IDE was opened before the environment variables were updated.
- A shell alias/function or command cache is shadowing the real executable.
- The installation path contains special characters or spaces that are improperly concatenated in a script.

Invoke the compiler by its full path to distinguish a PATH issue from an installation issue:

PowerShell:

~~~powershell
& "$env:JAVA_HOME\bin\javac.exe" -version
~~~

Bash/Zsh:

~~~bash
"$JAVA_HOME/bin/javac" -version
~~~

If direct invocation succeeds, fix PATH and restart the shell. If direct invocation also fails, check file existence, execute permissions, symlinks, and the type of JDK installed.

## 13. java Runs, but javac Is Missing

This is a common symptom when only a runtime is installed or when using a stripped-down runtime image.

Inspect the active runtime:

~~~bash
java -version
java --list-modules
~~~

Search for the compiler module:

Windows PowerShell:

~~~powershell
java --list-modules | Select-String '^jdk.compiler@'
~~~

Linux/macOS:

~~~bash
java --list-modules | grep '^jdk.compiler@'
~~~

If jdk.compiler is absent from the image, that image does not provide the system compiler. This is common in runtime images built with jlink using a minimal module list, or in container images intended solely for running applications.

Use a full JDK in the build environment. For production applications, you can continue using a compact runtime image after compiling and packaging the artifact in the build stage.

## 14. Verifying Whether a JDK Is Truly Complete

A JDK directory typically contains components such as:

~~~text
jdk/
├── bin/
│   ├── java
│   ├── javac
│   ├── jar
│   └── javadoc
├── conf/
├── include/
├── jmods/
└── lib/
~~~

Executable filenames on Windows typically have the .exe extension. Some runtime images lack the full set of directories or launchers found in a full JDK.

You can do a quick check:

PowerShell:

~~~powershell
Get-ChildItem "$env:JAVA_HOME\bin\javac*"
Test-Path "$env:JAVA_HOME\jmods\jdk.compiler.jmod"
~~~

Linux/macOS:

~~~bash
ls -l "$JAVA_HOME/bin/javac"
test -f "$JAVA_HOME/jmods/jdk.compiler.jmod" && echo "Compiler module file exists"
~~~

Do not rely solely on the presence of jmods as the only criterion: custom packages may distribute modules differently. The best direct evidence is invoking bin/javac -version and compiling a test Java file.

## 15. Checking in the IDE

An external terminal may find javac while the IDE still reports a missing compiler, or vice versa. IDEs can use separate JDKs for the project and build tools.

Check:

- The workspace's Project SDK/JDK.
- The JDK used by the Maven runner.
- Gradle JVM or Gradle's Java toolchain.
- The JDK configured in the VS Code Java extension.
- The environment inherited by the IDE at the time it was launched.

In IntelliJ IDEA, check Project Structure for the Project SDK; for Gradle, check Gradle JVM; for Maven, check the Maven runner's JRE. These settings can be independent of the terminal PATH.

In VS Code, check the Java runtime configured for the workspace and the integrated terminal. After installing a JDK or changing PATH, restart the IDE if the IDE process is still holding the old environment.

## 16. Checking Maven and Gradle

Maven Wrapper and Gradle Wrapper select the project's build tool version. A wrapper does not turn a runtime-only installation into a JDK with a compiler.

Check Maven:

~~~bash
mvn -version
./mvnw --version
~~~

On Windows:

~~~powershell
mvn -version
.\mvnw.cmd --version
~~~

Maven output displays the Java version and Java home that Maven is using. If it differs from the expected JDK, check JAVA_HOME, PATH, or Maven Toolchains configuration.

Check Gradle:

~~~bash
gradle --version
./gradlew --version
./gradlew javaToolchains
~~~

On Windows:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat javaToolchains
~~~

Gradle can use one JVM to run the Gradle daemon and a separate Java toolchain for compile tasks. If the build declares a toolchain, check the installed JDK versions and how the project's resolver locates toolchains.

## 17. Configuring the JDK in GitHub Actions

A CI runner needs a JDK with a compiler before running compile tasks. Use actions/setup-java to install the JDK, set JAVA_HOME, and add the JDK to PATH:

~~~yaml
name: Java compile check

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  compile:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - name: Set up JDK 17
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - name: Verify compiler
        run: |
          java -version
          javac -version

      - name: Compile and test
        run: ./mvnw --batch-mode --no-transfer-progress clean verify
~~~

For Gradle, replace the final step with:

~~~yaml
      - name: Compile and test
        run: ./gradlew --no-daemon clean build
~~~

If running on a Windows runner, use .\mvnw.cmd or .\gradlew.bat. setup-java is responsible for installing the JDK and updating the job's environment; Maven/Gradle caching only speeds up dependency downloads and does not replace the JDK.

## 18. JDK in Docker and Containers

A build container requires a compiler. If a Dockerfile uses a runtime-only base image, the javac command will not exist.

Multi-stage build example:

~~~dockerfile
FROM eclipse-temurin:17-jdk AS build
WORKDIR /app
COPY HelloJavac.java .
RUN javac --release 17 HelloJavac.java

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/HelloJavac.class .
CMD ["java", "HelloJavac"]
~~~

The build stage uses a JDK to compile. The runtime stage only needs an environment to run the compiled class. This is the appropriate pattern when you want a smaller deployment image.

If the build runs inside a container, install the JDK in the build container. A JDK on the host machine does not automatically appear inside the container because each container has its own filesystem and PATH.

## 19. Difference Between javac Errors and Source/Classpath Errors

Not every error mentioning Java means the compiler could not be found.

| Message | Meaning | Where to check |
|---|---|---|
| javac: command not found | Shell cannot find the compiler | JDK, PATH, JAVA_HOME |
| javac is not recognized | Windows cannot resolve the command | JDK bin, PATH, new terminal |
| error: file not found: Hello.java | Compiler ran but cannot find the source file | Current directory and filename |
| package ... does not exist | Missing dependency or source/module path | Classpath/module path |
| cannot find symbol | Cannot resolve class, method, or field | Source, dependency, import, generated source |
| invalid source release: 17 | Compiler is too old for the requested release | javac -version, PATH order |
| Could not find or load main class | JVM cannot find the class at runtime | Classpath, package, working directory |
| java is not recognized | Runtime launcher is not on PATH | JDK/JRE and PATH |

If javac -version already runs, move on to checking source files, classpath, module path, and compiler version. Do not reinstall the JDK just because of a file not found or cannot find symbol error.

## 20. invalid source release Error After javac Is Found

For example, the project requires Java 17, but the shell is invoking a Java 8 or Java 11 compiler:

~~~bash
javac --release 17 HelloJavac.java
~~~

If the compiler does not support release 17, the command will fail even though javac exists.

Check:

~~~bash
javac -version
java -version
command -v javac
command -v java
~~~

On Windows, use where.exe javac and where.exe java. Place JDK 17 or newer at the front of PATH, then open a new terminal. If Maven/Gradle uses toolchains, check the JDK selected for the compile task rather than only checking java -version in the terminal.

## 21. Verification Workflow After Fixing PATH

After configuring, follow these steps in order:

1. Open a new terminal.
2. Print JAVA_HOME.
3. Locate the paths of java and javac.
4. Run java -version and javac -version.
5. Invoke javac once by its full path.
6. Compile a test Java 17 source file.
7. Run the generated class.
8. Re-run the Maven/Gradle build if the error occurred in a project.

Do not rely solely on a JAVA_HOME value that looks right. You must confirm which executable is selected and that the program actually compiles source code.

## 22. Java 17+ Example to Test the Compiler

Create HelloJavac.java:

~~~java
public final class HelloJavac {
    public static void main(String[] args) {
        System.out.println("JAVAC_OK release=17");
    }
}
~~~

Compile and run on Bash, Linux, macOS, or PowerShell:

~~~bash
mkdir -p "out classes"
javac --release 17 -d "out classes" HelloJavac.java
java -cp "out classes" HelloJavac
~~~

PowerShell can use:

~~~powershell
New-Item -ItemType Directory -Force 'out classes' | Out-Null
javac --release 17 -d 'out classes' .\HelloJavac.java
java -cp 'out classes' HelloJavac
~~~

In cmd.exe:

~~~bat
if not exist "out classes" mkdir "out classes"
javac --release 17 -d "out classes" HelloJavac.java
if errorlevel 1 exit /b 1
java -cp "out classes" HelloJavac
~~~

Exact output:

~~~text
JAVAC_OK release=17
~~~

The --release 17 option tells the compiler to check source, bytecode target, and Java SE APIs against Java 17. This option has been available since JDK 9; this example requires JDK 17 or later.

## 23. Invoking javac by Absolute Path

If PATH is still not fixed, you can verify or run the compiler using its full path.

PowerShell:

~~~powershell
$javac = Join-Path $env:JAVA_HOME 'bin\javac.exe'
& $javac --release 17 -d 'out classes' .\HelloJavac.java
~~~

Bash/Zsh:

~~~bash
"$JAVA_HOME/bin/javac" --release 17 -d "out classes" HelloJavac.java
~~~

This is useful for testing a specific JDK or a build script that needs to select the compiler explicitly. However, tools like Maven, Gradle, IDEs, and other scripts may still use the JDK from JAVA_HOME, PATH, or their own toolchain; configure the environment consistently across the entire build.

## 24. Execute Permission, Symlink, and Architecture Errors

If the javac file exists but fails to run, the message may be Permission denied, No such file or directory, Exec format error, or a DLL loading error.

On Linux/macOS:

~~~bash
ls -l "$JAVA_HOME/bin/javac"
file "$JAVA_HOME/bin/javac"
readlink -f "$JAVA_HOME/bin/javac"
~~~

Check execute permissions and whether the symlink points to an existing file. Do not run chmod indiscriminately across the entire JDK; if the package is corrupted or missing files, reinstall the JDK from an official source.

On Windows, check the javac.exe file, JDK architecture, and OS architecture. If the wrong package was installed or the file was quarantined by antivirus/device management, fix the installation according to machine policy.

## 25. Commonly Overlooked Causes in CI and Team Environments

- The JDK is installed on the developer's machine but missing in the runner.
- The build container uses a runtime image instead of a JDK image.
- The job installs Java after the compile step.
- The runner's JAVA_HOME points to a different Java installation than PATH.
- A matrix build selects a different runtime version from the compiler toolchain.
- A self-hosted runner has a stale PATH from a service account.
- The IDE and terminal use two different JDKs.
- A custom jlink image omits jdk.compiler.
- The wrapper is fully committed, but the environment running the wrapper lacks a compatible JDK.

In a pipeline, print java -version, javac -version, mvn -version, or gradle --version right before the build step. These lines help identify the job's actual environment when a build fails.

## 26. Checklist for Resolving javac Not Found

- Confirm the message is a compiler-lookup error, not a source or classpath error.
- Run java -version and javac -version separately.
- Verify JAVA_HOME points to the JDK root directory.
- Confirm JAVA_HOME/bin/javac or JAVA_HOME\bin\javac.exe exists.
- Invoke the compiler by full path to verify the installation.
- Add JDK bin to PATH using the OS's correct separator.
- Check the order of multiple JDKs and duplicate executables.
- Open a new terminal/IDE after updating the environment.
- Check Project SDK, Maven runner JDK, and Gradle JVM.
- Install a JDK development package if only a runtime is present.
- Check the jdk.compiler module if using a custom runtime image.
- Run the HelloJavac example with --release 17.
- Re-verify inside the actual CI runner or container doing the build.

Once the right JDK and compiler are found, the javac not found error will disappear. Recording JAVA_HOME, the executable path, the compiler version, and the compile result helps the team catch early when a developer machine, IDE, or CI runner is using a different Java environment than expected.

## References

- Oracle JDK 26 — [The javac Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html).
- Oracle JDK 26 — [JDK Installation Guide](https://docs.oracle.com/en/java/javase/26/install/index.html).
- Oracle JDK 26 — [Installation of the JDK on Windows](https://docs.oracle.com/en/java/javase/26/install/installation-jdk-microsoft-windows-platforms.html).
- Oracle JDK 26 — [Installation of the JDK on macOS](https://docs.oracle.com/en/java/javase/26/install/installation-jdk-macos.html).
- Oracle Java SE 26 — [jdk.compiler Module](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/module-summary.html).
- Microsoft Learn — [Get started with Java on Windows](https://learn.microsoft.com/en-us/windows/dev-environment/java/).
- Microsoft Learn — [PATH command](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/path).
- Microsoft Learn — [where command](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/where).
- Ubuntu for Developers — [Set up a Java development environment](https://ubuntu.com/developers/docs/howto/java-setup/).
- GitHub — [actions/setup-java](https://github.com/actions/setup-java).
