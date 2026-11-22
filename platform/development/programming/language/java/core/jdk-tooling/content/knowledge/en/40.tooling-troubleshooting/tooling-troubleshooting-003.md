# Fixing an Incorrect JAVA_HOME in Java

JAVA_HOME is the environment variable pointing to the root directory of the JDK that a build tool or script needs to use. JAVA_HOME errors typically occur when the variable is unset, points to the wrong directory, points to the bin directory or the java.exe file, points to a JRE without javac, or points to a different JDK than the java found via PATH.

The right way to troubleshoot is to check three things separately: the value of JAVA_HOME, the java/javac executable that the shell is running, and the JDK that Maven/Gradle/IDE actually uses. Looking only at the output of java -version is not enough to conclude that JAVA_HOME is correct, because the java command may come from another directory in PATH.

This guide walks through diagnosing and fixing the issue on Windows, Linux, and macOS, handling multiple JDKs simultaneously, checking Maven/Gradle/IDE/CI, and using a small Java program to verify the actual runtime.

## 1. What is JAVA_HOME?

JAVA_HOME is an environment variable convention used by many Java tools to locate the JDK. Its value must be the path to the JDK installation root directory.

For example:

~~~text
Windows:
C:\Java\jdk-17

Linux:
/opt/jdk-17

macOS:
/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home
~~~

This directory typically contains subdirectories such as bin, conf, include, jmods, and lib. In a full JDK, the bin directory contains tools like java, javac, jar, javadoc, and jshell.

JAVA_HOME is not:

- A path to the bin directory.
- A direct path to java.exe or the java file.
- The Maven installation directory.
- The project directory.
- A runtime-only JRE if the task requires compiling source code with javac.

If JAVA_HOME points to C:\Java\jdk-17\bin, many tools will automatically append bin and mistakenly look for C:\Java\jdk-17\bin\bin. If it points to the java.exe file, tools expecting a JDK directory will fail.

## 2. Distinguishing JAVA_HOME, PATH, and java.home

These three values are related but not synonymous:

| Value | Role |
|---|---|
| JAVA_HOME | The JDK path preferred by build tools by convention |
| PATH | The list of directories the shell searches for executables when invoking java or javac |
| java.home | The system property indicating the runtime directory used by the running JVM |

The shell does not automatically use JAVA_HOME to find the java command. When you type java, the shell searches PATH. Some launchers, such as Maven, check JAVA_HOME first before looking for java in PATH.

Therefore, the following situation can occur:

- JAVA_HOME points to JDK 17.
- PATH finds java from JDK 21 first.
- Running java -version displays Java 21.
- Maven runs with JDK 17 instead if the Maven launcher prioritizes JAVA_HOME.

The reverse can also happen if an IDE, Gradle daemon, or toolchain configuration selects a separate JDK.

java.home is runtime information inside the JVM. On modern JDKs, this value usually points to the JDK runtime home; on some older Java layouts, especially JDK 8, it may point to the jre directory inside the JDK. Treat this as evidence of the running JVM, not as a replacement for checking JAVA_HOME.

## 3. Common Symptoms

Some common errors:

| Message/Symptom | Possible Cause |
|---|---|
| The JAVA_HOME environment variable is not defined correctly | Variable is unset, path is wrong, or points to bin/file |
| JAVA_HOME is set to an invalid directory | Directory does not exist or is not a JDK home |
| Could not find java in JAVA_HOME | Missing bin/java or bin/java.exe |
| javac is not recognized / command not found | PATH is missing JDK bin or only a runtime is installed |
| java -version is correct but mvn -version is wrong | Maven uses JAVA_HOME, an old terminal/IDE, or a different launcher |
| java and javac display different versions | PATH contains multiple JDKs or the two executables come from different directories |
| Changed JAVA_HOME but the result did not change | Shell/IDE/service has not picked up the new environment, or PATH has an earlier entry |
| Build runs locally but fails in CI | CI runner uses a different JDK/path or the variable is not passed to the job |

Read both the error message and the command that produced the error. Maven, Gradle, IDEs, and directly executed applications can select the JVM through different mechanisms.

## 4. Quick Diagnostic Workflow

Follow these steps in order:

1. Print the value of JAVA_HOME in the exact terminal experiencing the error.
2. Verify that the JAVA_HOME directory exists.
3. Verify that it contains bin/java and bin/javac.
4. Find all java/javac executables that PATH can resolve.
5. Run java -version and javac -version.
6. Run mvn -version or gradle --version if the error occurs during a build.
7. Check the specific JDK configuration of your IDE, toolchain, or CI.
8. Fix the variable in the appropriate scope, open a new process, and verify again.

Do not change the variable before knowing which tool is selecting the wrong JDK. That helps avoid altering an environment that is already configured correctly.

## 5. Checking JAVA_HOME on Windows

Open PowerShell and run:

~~~powershell
Write-Output "JAVA_HOME=$env:JAVA_HOME"

if ([string]::IsNullOrWhiteSpace($env:JAVA_HOME)) {
    Write-Output "JAVA_HOME is not set in this process."
}
else {
    Test-Path -LiteralPath $env:JAVA_HOME -PathType Container
    Test-Path -LiteralPath (Join-Path $env:JAVA_HOME 'bin\java.exe') -PathType Leaf
    Test-Path -LiteralPath (Join-Path $env:JAVA_HOME 'bin\javac.exe') -PathType Leaf
}
~~~

All three Test-Path results should be True when the project requires a full JDK. If the first line is False, check whether JAVA_HOME is pointing to bin or an executable file.

Find all java/javac commands:

~~~powershell
Get-Command java -All | Select-Object CommandType, Source, Definition
Get-Command javac -All | Select-Object CommandType, Source, Definition

where.exe java
where.exe javac
~~~

Get-Command shows which command PowerShell will select. where.exe lists the executables found via PATH. If there are multiple results, the first entry is usually the command chosen when invoking java or javac from PATH.

Check versions:

~~~powershell
java -version
javac -version
mvn -version
~~~

Check the executables directly from JAVA_HOME, bypassing PATH:

~~~powershell
$javaExe = Join-Path $env:JAVA_HOME 'bin\java.exe'
$javacExe = Join-Path $env:JAVA_HOME 'bin\javac.exe'

& $javaExe -version
& $javacExe -version
~~~

If the executables directly from JAVA_HOME report the right version but java -version gives a different result, the problem lies in PATH or shell resolution. If the direct executables do not exist, JAVA_HOME is pointing to the wrong location or the JDK is not completely installed.

## 6. Temporarily Fixing JAVA_HOME on Windows

To test a JDK in the current terminal:

~~~powershell
$env:JAVA_HOME = 'C:\Java\jdk-17'
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"

java -version
javac -version
mvn -version
~~~

Replace C:\Java\jdk-17 with the actual JDK directory on your machine. Use quotes around the value so paths containing spaces are preserved.

Changes made with $env: apply only to the current PowerShell process and child processes launched from it. Closing the terminal will discard this change. This is a good way to test before making permanent configuration changes.

If there are already multiple Java bin directories in PATH, prepend the desired JDK in the current terminal as shown above. Verify again with where.exe java to confirm the first path.

## 7. Permanently Fixing JAVA_HOME on Windows

You can configure it through the Windows UI:

1. Open Start and search for Edit the system environment variables.
2. Select Environment Variables.
3. Under User variables, create or edit JAVA_HOME.
4. Set the value to the JDK root directory, for example C:\Java\jdk-17.
5. In Path, add %JAVA_HOME%\bin.
6. Check for older Java bin entries that appear earlier and cause conflicts; adjust or remove obsolete entries if no longer used.
7. Click OK to save, close the terminal, and open a new terminal.
8. Restart any IDE, service, or integrated terminal that needs to pick up the new variable.

If it needs to apply to all users, edit System variables, which requires administrator privileges. A User variable only affects the current account.

You can set JAVA_HOME for the current user using PowerShell:

~~~powershell
[Environment]::SetEnvironmentVariable(
    'JAVA_HOME',
    'C:\Java\jdk-17',
    'User'
)
~~~

This command saves the variable persistently for the user but does not update the environment of the currently open terminal. Open a new process to read the new value. Manage PATH ordering in Environment Variables to avoid conflicts with old Java bin entries; do not overwrite the entire PATH with a setx PATH command.

In CMD, the way to inspect variables is:

~~~cmd
echo %JAVA_HOME%
where java
where javac
~~~

In PowerShell, use $env:JAVA_HOME; the %JAVA_HOME% syntax is CMD variable expansion syntax, not PowerShell.

## 8. Checking and Fixing on Linux

Print the variable, executables, and versions:

~~~bash
printf 'JAVA_HOME=%s\n' "${JAVA_HOME:-<unset>}"

if [ -n "${JAVA_HOME:-}" ]; then
  ls -ld "$JAVA_HOME"
  ls -l "$JAVA_HOME/bin/java" "$JAVA_HOME/bin/javac"
fi

command -v java
command -v javac
type -a java
type -a javac
java -version
javac -version
mvn -version
~~~

If JAVA_HOME is unset or pointing to the wrong location, select the actual JDK directory. For example, if JDK 17 is installed at /opt/jdk-17:

~~~bash
export JAVA_HOME="/opt/jdk-17"
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
~~~

If the JDK is located under /usr/lib/jvm, list the directory first:

~~~bash
ls -1 /usr/lib/jvm
~~~

On Debian/Ubuntu, you can view the available Java alternatives:

~~~bash
update-alternatives --list java
update-alternatives --list javac
update-alternatives --config java
update-alternatives --config javac
~~~

The --config commands modify system symlinks and may require sudo privileges. Only use them when you want to change the system-wide default Java selection. A shell's JAVA_HOME can still point to a different JDK than that default symlink.

On distributions that use alternatives instead of update-alternatives, the command name and options may differ. Check your OS package management tool before making changes.

## 9. Persisting JAVA_HOME on Linux

For a Bash interactive shell, you can add it to ~/.bashrc:

~~~bash
export JAVA_HOME="/opt/jdk-17"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Then reload it:

~~~bash
source ~/.bashrc
~~~

For Zsh, ~/.zshrc is typically used. For a login shell, check ~/.profile or ~/.bash_profile depending on how the shell is launched. Avoid setting conflicting values across multiple startup files because login shells and interactive shells may load different files.

System-wide configuration for all users can be placed in a file like /etc/profile.d/java.sh, though this requires administrator privileges and must follow machine policy. In containers or CI, declare environment variables in the image/job definition rather than relying on personal shell files.

## 10. Checking and Fixing on macOS

macOS provides the /usr/libexec/java_home tool to locate installed JDKs:

~~~bash
/usr/libexec/java_home -V
~~~

This command lists the JDKs recognized by the system. To select JDK 17:

~~~bash
/usr/libexec/java_home -v 17
~~~

Set it for the current terminal:

~~~bash
export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
mvn -version
~~~

Modern macOS typically uses Zsh. To persist the configuration for Zsh, add the export lines to ~/.zshrc or the appropriate login file for how your terminal launches the shell. Open a new terminal and verify again.

Some JDKs installed via a package manager or SDK manager may reside in a separate location. Use /usr/libexec/java_home -V to see which JDKs macOS recognizes before setting a path manually.

## 11. Handling Multiple JDKs Simultaneously

Different projects may require Java 8, 11, 17, or 21. You should not hard-switch the system-wide JDK every time you switch projects.

Some ways to manage this:

- Use SDKMAN! on Linux/macOS to install and select JDKs per shell/project.
- Use jEnv to manage versions per user or project directory.
- Use your organization's or IDE's JDK management tools.
- Use Maven Toolchains to select a separate compiler JDK per POM requirement.
- Use Gradle Java Toolchains to select the compiler/test launcher for a project.
- Use a CI matrix to run tests across supported runtimes.

With Maven, toolchains.xml describes installed JDKs, and the Maven Toolchains Plugin/Compiler Plugin selects the appropriate JDK. The toolchain can differ from the JAVA_HOME of the Maven runtime.

With Gradle, a Java toolchain can request a language version, vendor, or implementation. Gradle locates a matching installed JDK or can auto-provision one if repository provisioning is enabled.

Do not change JAVA_HOME just to change the class-file target. JAVA_HOME selects the runtime/compiler launcher environment for the tool; release/source/target or a Java toolchain are separate build configurations.

## 12. JAVA_HOME is Correct but java is Still Wrong

If JAVA_HOME is valid but java -version still shows a different JDK, check PATH:

Windows:

~~~powershell
$env:PATH -split ';'
where.exe java
Get-Command java -All
~~~

Linux/macOS:

~~~bash
printf '%s\n' "$PATH" | tr ':' '\n'
command -v java
type -a java
~~~

Find the old JDK entry appearing before $JAVA_HOME/bin. Reorder PATH or remove the unused entry according to machine policy.

Bash and some other shells may cache command locations. After updating PATH, refresh the cache:

~~~bash
hash -r
~~~

Then run command -v java and java -version again. If it is still wrong, open a new shell to rule out a stale environment.

On Windows, PowerShell resolves commands using the current process environment. If you just changed a persistent variable, an already open terminal still holds the old environment. Open a new window and check again.

## 13. Checking Which JDK Maven Uses

The Maven launcher usually prioritizes JAVA_HOME. The most important command to verify the Maven runtime is:

~~~powershell
mvn -version
~~~

Or on Linux/macOS:

~~~bash
mvn -version
~~~

The output includes the Maven version, Java version, vendor, and Java home. If Maven uses the wrong JDK:

1. Check JAVA_HOME in the exact terminal running Maven.
2. Check which Maven executable is being invoked using where.exe mvn or command -v mvn.
3. Run mvn -version to inspect the actual JVM.
4. Check whether Maven launched by an IDE has a different environment than the terminal.
5. Check Maven Toolchains if the compiler uses a different JDK than the Maven runtime.

Maven Toolchains do not necessarily change the JVM running Maven itself. For example, Maven may run on JDK 21 while the Compiler Plugin uses JDK 17. Check the toolchain logs and compiler configuration when you need to identify javac.

MAVEN_HOME is the Maven installation path, not the JDK home. Do not set JAVA_HOME to the Maven directory or MAVEN_HOME to the JDK directory.

## 14. Checking Which JDK Gradle Uses

Use the Gradle Wrapper if the project has one:

~~~powershell
.\gradlew.bat --version
~~~

On Linux/macOS:

~~~bash
./gradlew --version
~~~

The output displays the Gradle version and the JVM used to run Gradle. The Gradle daemon may keep a previously started JVM alive; after changing JDKs, stop the daemon:

~~~powershell
.\gradlew.bat --stop
~~~

Or:

~~~bash
./gradlew --stop
~~~

Check configurations that can override it:

- org.gradle.java.home in gradle.properties.
- JAVA_HOME of the process running Gradle.
- JVM configured in the IDE.
- Java toolchain in build.gradle/build.gradle.kts.

Example toolchain requesting Java 17:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

A toolchain configuration controls the JDK used for the corresponding Java tasks. It does not necessarily change the JVM running the Gradle daemon.

## 15. Checking the JDK in an IDE

An IDE can store its own JDK settings, so a working terminal does not guarantee the project is configured correctly.

In IntelliJ IDEA, check:

- Project Structure > Project SDK.
- Project language level.
- Settings > Build Tools > Maven > Runner > JRE.
- Settings > Build Tools > Gradle > Gradle JVM.
- Per-module JDK configuration, if any.

In Eclipse, check:

- Installed JREs.
- Execution Environments.
- Java Compiler compliance level.
- The project's JRE System Library.

In Visual Studio Code, check Java runtimes in the Java extension settings and the project's build tool configuration.

After changing JAVA_HOME on Windows/Linux/macOS, close and reopen the IDE so it picks up the new environment. An IDE that was already running before the variable change may continue passing the old environment to child Maven/Gradle processes.

## 16. Checking in CI, Docker, and Services

A CI runner has its own environment. A working JAVA_HOME on your laptop does not prove the variable is set in the workflow.

In a CI job, print the necessary values:

~~~bash
printf 'JAVA_HOME=%s\n' "${JAVA_HOME:-<unset>}"
command -v java
command -v javac
java -version
javac -version
mvn -version
~~~

Do not print the entire environment if it contains secrets. Only log the variables and tool versions needed for diagnosis.

In a Dockerfile, set JAVA_HOME to point to the JDK/JRE in the image and add bin to PATH:

~~~dockerfile
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH="${JAVA_HOME}/bin:${PATH}"
~~~

The actual path depends on the base image. Verify the image with java -version and test -x "$JAVA_HOME/bin/javac" if the image needs a compiler.

Windows services, scheduled tasks, IDE services, and CI agents may run under a different user. Each user has its own environment. When a service does not pick up a new JAVA_HOME, check the account running the service and restart the service after updating the environment.

## 17. Paths with Spaces, Symlinks, and Permissions

A JDK path can contain spaces, such as C:\Program Files\Java\jdk-17. Always quote paths in the shell:

PowerShell:

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-17'
& "$env:JAVA_HOME\bin\java.exe" -version
~~~

Bash:

~~~bash
export JAVA_HOME="/opt/Java Development Kit/jdk-17"
"$JAVA_HOME/bin/java" -version
~~~

Do not split strings on spaces or embed quotes directly inside the JAVA_HOME value itself. The variable should hold the raw path; quote it when using it.

If JAVA_HOME is a symlink, verify that the symlink target still exists and that the user running the build has read/execute permissions. A JDK may have been uninstalled or upgraded, leaving an old symlink pointing to a non-existent directory.

On Linux, you can inspect a symlink:

~~~bash
ls -ld "$JAVA_HOME"
readlink "$JAVA_HOME"
~~~

On macOS, readlink may only display a relative target; do not assume the readlink -f option is available as on GNU/Linux.

On Windows, check directory read permissions and execute permissions on files in bin. Also confirm the JDK matches the OS/runner architecture if the build involves native tools or JNI libraries.

## 18. A Java Program to Verify the Actual Runtime

Create a file named JdkProbe.java:

~~~java
public final class JdkProbe {
    private JdkProbe() {
    }

    public static void main(String[] args) {
        System.out.println("Runtime version: " + Runtime.version());
        System.out.println("Java version: " + System.getProperty("java.version"));
        System.out.println("Java vendor: " + System.getProperty("java.vendor"));
        System.out.println("Java home: " + System.getProperty("java.home"));
        System.out.println("OS: " + System.getProperty("os.name"));
        System.out.println("Architecture: " + System.getProperty("os.arch"));
    }
}
~~~

Compile with the selected JDK:

~~~powershell
javac --release 17 -encoding UTF-8 JdkProbe.java
~~~

Run:

~~~powershell
java JdkProbe
~~~

Sample output when running with JDK 17:

~~~text
Runtime version: 17.0.12+7
Java version: 17.0.12
Java vendor: Eclipse Adoptium
Java home: C:\Java\jdk-17
OS: Windows 11
Architecture: amd64
~~~

Actual values vary by JDK, vendor, OS, and machine. This program shows which JVM is running the application. It does not prove that the javac executable came from the same directory; check Get-Command/where.exe or command -v and javac -version separately.

If compiled with JDK 24 using --release 17, the class file still targets Java 17 while the runtime output may show Java 24. These are two separate pieces of information.

## 19. Troubleshooting Table by Symptom

| Symptom | Check | Fix |
|---|---|---|
| JAVA_HOME is not set | echo/Write-Output the variable value | Set the variable in the session or environment settings |
| JAVA_HOME points to bin | Inspect directory structure | Remove the bin segment, use the JDK root directory |
| JAVA_HOME points to java.exe | Test-Path directory and child files | Reset to the directory containing bin |
| Missing javac | Check bin/javac | Install a full JDK, do not use a runtime-only package |
| java and javac have different versions | where/Get-Command/type -a | Fix PATH so both commands use the same JDK |
| Maven uses a different Java than the terminal | mvn -version | Check JAVA_HOME and Maven launcher/IDE |
| Gradle uses an old Java | gradlew --version, org.gradle.java.home | Fix configuration, stop daemon, and rerun |
| IDE uses an old JDK | Project SDK, Maven Runner, Gradle JVM | Select the right JDK in the IDE and restart |
| Fails only in CI | Print JAVA_HOME, java/javac paths, tool versions | Fix workflow image/variables or service account |
| Changing the variable has no effect | Open a new shell/process, check PATH | Restart terminal, IDE, daemon, or service |
| Path with spaces fails | Quote variables and paths | Store raw path in variable, quote at usage sites |
| Broken symlink | ls -ld/readlink or Test-Path | Update symlink/JAVA_HOME to an existing JDK |

## 20. Safe Fixing and Post-Fix Verification Workflow

A repeatable fixing workflow:

1. Record the current JAVA_HOME and the output of java/javac -version.
2. Identify the required JDK and its actual installation directory.
3. Verify the directory contains bin/java and bin/javac.
4. Set JAVA_HOME to point to the JDK root.
5. Place JAVA_HOME/bin before older Java bin entries in PATH.
6. Open a new terminal or reload the shell config.
7. Verify command resolution and versions of java/javac.
8. Run mvn -version or gradle --version.
9. Check toolchain/IDE settings if the build still selects a different JDK.
10. Rerun the build/tests in the exact original environment that failed.

If fixing for CI, rerun the exact job on the corresponding runner. If fixing for a service, restart the service so the new process picks up the environment. There is no need to change the system-wide JDK if only one project needs a specific JDK; Maven/Gradle toolchains or IDE project SDKs are usually more appropriate.

## 21. Best Practices to Avoid JAVA_HOME Errors

- Point JAVA_HOME to the JDK root, not bin or the java file.
- Use a full JDK when javac, javadoc, or build tools are needed.
- Ensure PATH does not unintentionally prioritize an older JDK.
- Quote paths containing spaces in Bash/PowerShell.
- Use a consistent JDK version management source across the team.
- Pin the compiler JDK with Maven/Gradle Toolchains when the project requires it.
- Use Maven Wrapper or Gradle Wrapper.
- Verify mvn -version/gradle --version in CI.
- Configure IDE Project SDK and build runners explicitly.
- Restart terminals, IDEs, daemons, or services after changing environment variables.
- Never log secrets when debugging CI.
- Document the JDK vendor, version, and architecture in build documentation.

## 22. JAVA_HOME Diagnostic Checklist

- [ ] JAVA_HOME is set in the right process/user/service.
- [ ] The value points to the JDK root directory.
- [ ] The JAVA_HOME directory exists and is accessible.
- [ ] bin/java or bin/java.exe exists.
- [ ] bin/javac or bin/javac.exe exists if compilation is needed.
- [ ] PATH has the desired JDK bin in priority order.
- [ ] Get-Command/where.exe or command -v resolves to the right executable.
- [ ] java -version and javac -version display the expected version.
- [ ] mvn -version or gradle --version uses the right JVM.
- [ ] Maven/Gradle Toolchains do not unexpectedly override it.
- [ ] IDE Project SDK, Maven Runner, and Gradle JVM are correct.
- [ ] Terminal/IDE/daemon/service has been restarted after the fix.
- [ ] CI runner uses the same JDK policy as the project.
- [ ] The JdkProbe program confirms the actual runtime when needed.

A valid JAVA_HOME must point to the JDK root, while PATH determines which java/javac executable the shell invokes. When troubleshooting, inspect the variable, the executables, and the Maven/Gradle/IDE runtime separately. After fixing, open a new process and verify again using versions, executable paths, and an actual build.

## References

- Oracle Java SE 17 — The java Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle Java SE 17 — The javac Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Apache Maven — Installation: https://maven.apache.org/install.html
- Apache Maven — Guide to Using Toolchains: https://maven.apache.org/guides/mini/guide-using-toolchains.html
- Gradle — Compatibility and Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
- Microsoft Learn — Environment Variables: https://learn.microsoft.com/en-us/windows/win32/procthread/environment-variables
- Microsoft Learn — PowerShell Environment Variables: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_environment_variables
