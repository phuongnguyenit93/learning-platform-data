# Java Not Found Error

The **`java` command not found** error occurs when the operating system cannot locate the Java program in the current environment. The cause is usually that the JDK/JRE is not installed, Java's `bin` directory is not in `PATH`, or the terminal/IDE/service is using outdated environment variables.

You need to identify the exact layer that is failing before fixing it. The `java` command is used to run programs; `javac` is the compiler included in the JDK. A machine can run Java but fail to compile if it only has the runtime or if PATH does not point to the JDK.

## 1. Identifying the Error Message

Different operating systems typically display different messages:

| Message | Common Meaning |
|---|---|
| Linux/macOS: `java: command not found` | The shell cannot find an executable named `java` in PATH |
| PowerShell: `'java' is not recognized as the name of a cmdlet...` | The current PATH cannot find `java.exe` |
| Command Prompt: `'java' is not recognized as an internal or external command...` | Windows cannot find the Java executable |
| macOS: `Unable to locate a Java Runtime` or a no-runtime message | The macOS Java launcher cannot find a suitable runtime |
| `javac: command not found` while `java -version` works | A runtime may be installed, but the JDK compiler is not in PATH or only a JRE is installed |
| `java -version` runs but shows an old version | Multiple Java installations exist; PATH is prioritizing a different version |

Do not confuse an executable lookup error with an application runtime error:

| Message | Error Layer |
|---|---|
| `java: command not found` | Java launcher not found |
| `Could not find or load main class` | Java launcher ran; class or classpath is incorrect |
| `NoClassDefFoundError` | Missing class/dependency at runtime |
| `UnsupportedClassVersionError` | The runtime in use is older than the bytecode version required by the program |
| `Permission denied` when running a Java file | Execute permission or file access permission issue; check the path and permissions |

If `java -version` does not run, resolve the installation/PATH issue before investigating the classpath or source code.

## 2. Understanding the Role of PATH and JAVA_HOME

`PATH` is the list of directories the operating system searches when a user types a command name. If the directory containing `java` is not in PATH, the shell cannot find the command even if the Java files are already on the machine.

`JAVA_HOME` is an environment variable pointing to the root directory of the JDK. Many build tools such as Maven and Gradle use this variable to locate the Java installation.

For a JDK installed in an example directory:

~~~text
/opt/jdk-21
~~~

The proper configuration on Linux/macOS typically looks like:

~~~sh
export JAVA_HOME="/opt/jdk-21"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

On Windows, if the JDK is located at:

~~~text
C:\Program Files\Java\jdk-21
~~~

then:

- `JAVA_HOME` points to `C:\Program Files\Java\jdk-21`.
- `PATH` has an entry for `%JAVA_HOME%\bin`.

`JAVA_HOME` points to the JDK root directory—do not append `bin` and do not point directly to `java.exe`.

`PATH` requires the `bin` directory because `java` and `javac` are located inside it. For applications that only run Java, `JAVA_HOME` may not be mandatory if PATH already points to the right location; however, Maven, Gradle, and many development tools typically require this variable.

## 3. General Diagnostic Steps Before Changing Configuration

Run the commands appropriate for the shell you are using. The goal is to find out whether Java is installed, where the shell is looking for executables, and what values the environment variables hold.

### 3.1. Linux and macOS

~~~sh
java -version
javac -version
command -v java
command -v javac
printf '%s\n' "$JAVA_HOME"
printf '%s\n' "$PATH"
~~~

You can view all matching locations recognized by the shell:

~~~sh
type -a java
type -a javac
~~~

If `command -v java` returns no path and `java -version` reports command not found, the shell cannot find Java in PATH.

If `JAVA_HOME` already has a value, check the installation directly:

~~~sh
ls -ld "$JAVA_HOME"
ls -l "$JAVA_HOME/bin/java"
ls -l "$JAVA_HOME/bin/javac"
~~~

If the files exist, run them using their absolute paths to separate a PATH issue from an installation issue:

~~~sh
"$JAVA_HOME/bin/java" -version
"$JAVA_HOME/bin/javac" -version
~~~

If the commands work with absolute paths but `java` is still not found, the problem lies in PATH or the shell has not loaded the new configuration.

### 3.2. Windows PowerShell

~~~powershell
java -version
javac -version
Get-Command -All java -ErrorAction SilentlyContinue
Get-Command -All javac -ErrorAction SilentlyContinue
where.exe java
where.exe javac
$env:JAVA_HOME
$env:Path -split ';'
~~~

`where.exe` is a Windows program. In PowerShell, `where` is usually an alias for `Where-Object`, so use the full name `where.exe`.

If `JAVA_HOME` is already set, check it directly:

~~~powershell
Test-Path "$env:JAVA_HOME\bin\java.exe"
Test-Path "$env:JAVA_HOME\bin\javac.exe"
& "$env:JAVA_HOME\bin\java.exe" -version
& "$env:JAVA_HOME\bin\javac.exe" -version
~~~

If the absolute path works but `java` does not, fix PATH or reopen the terminal to pick up the new environment.

### 3.3. Command Prompt (cmd.exe)

~~~bat
java -version
javac -version
where java
where javac
echo %JAVA_HOME%
echo %PATH%
~~~

If `where java` returns no path, Windows cannot find Java through the PATH of the current Command Prompt window.

## 4. How to Fix on Windows

### 4.1. Install the JDK if Not Already Installed

You can install the Microsoft Build of OpenJDK 21 using Windows Package Manager:

~~~powershell
winget install Microsoft.OpenJDK.21
~~~

Or install Eclipse Temurin 21:

~~~powershell
winget install EclipseAdoptium.Temurin.21.JDK
~~~

If you do not use `winget`, download the installer from the vendor's official website and choose the appropriate Windows x64 or ARM64 architecture.

After installation, check the actual JDK directory. For example:

~~~text
C:\Program Files\Microsoft\jdk-21.0.x.x-hotspot
~~~

The directory name depends on the version and vendor; do not copy the example path verbatim if it does not exist on your machine.

### 4.2. Set JAVA_HOME and PATH Permanently

1. Open Start and search for `Edit the system environment variables`.
2. Select **Environment Variables**.
3. Under User variables or System variables, create `JAVA_HOME` if it does not exist.
4. Set its value to the JDK root directory, for example `C:\Program Files\Microsoft\jdk-21.0.x.x-hotspot`.
5. Select the `Path` variable, click Edit, and add the entry `%JAVA_HOME%\bin`.
6. Move the desired JDK entry above older Java entries if multiple installations exist.
7. Save the changes and open a new PowerShell/Command Prompt window.

Do not put quotation marks around individual PATH entry values in the Environment Variables window. Use a separate entry for `%JAVA_HOME%\bin`.

### 4.3. Test Immediately in the Current PowerShell Session

To test before making permanent configuration changes, assign the variables in the current PowerShell window. Replace the example path with your actual JDK:

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Microsoft\jdk-21.0.x.x-hotspot'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

java -version
javac -version
~~~

Settings in `$env:` only apply to the current PowerShell process and child processes launched from it. Closing this window will discard the temporary changes.

Do not use `setx PATH ...` to overwrite the entire PATH with a manually concatenated string. This approach can easily lose existing entries or produce an invalid PATH. Using the Environment Variables UI to edit individual entries is safer.

### 4.4. If Windows Still Runs an Old Java Version

Windows searches for executables in the order of directories listed in PATH. If multiple JDKs or shims exist, an earlier entry may be selected.

Check:

~~~powershell
where.exe java
where.exe javac
Get-Command -All java | Format-Table CommandType, Source, Definition -AutoSize
~~~

Compare each path against the desired JDK. A `javapath` from an older installer may appear before the new JDK. Adjust the PATH order so the desired JDK takes precedence, or remove the old installation using the vendor's uninstaller if it is no longer needed.

After fixing PATH, open a new terminal and run `where.exe java` and `java -version` again. If an IDE or service was already running, restart that process so it picks up the new environment variables.

## 5. How to Fix on macOS

### 5.1. Check Installed JDKs

macOS provides the `/usr/libexec/java_home` tool to locate installed JDKs:

~~~sh
/usr/libexec/java_home -V
java -version
javac -version
command -v java
echo "$JAVA_HOME"
~~~

If `/usr/libexec/java_home -V` lists no JDKs, install a JDK from a trusted vendor. Choose the package matching your architecture: macOS x64 for Intel or macOS AArch64 for Apple Silicon.

JDKs installed via an installer are typically located under:

~~~text
/Library/Java/JavaVirtualMachines/jdk-<FEATURE>.jdk/Contents/Home
~~~

### 5.2. Select a JDK and Set PATH

Example of selecting JDK 21 in the current terminal:

~~~sh
export JAVA_HOME="$(/usr/libexec/java_home -v 21)"
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
~~~

If `java_home` reports that version 21 was not found, check the list of JDKs with `/usr/libexec/java_home -V` and install the appropriate version.

You can run an executable directly to verify:

~~~sh
/usr/libexec/java_home -v 21 --exec java -version
/usr/libexec/java_home -v 21 --exec javac -version
~~~

### 5.3. Save Configuration for the Shell

Modern macOS typically uses zsh. For a login shell, environment configuration is usually placed in `~/.zprofile`; interactive shell configuration is usually placed in `~/.zshrc`.

Add the following snippet to the file appropriate for how your terminal is launched:

~~~sh
export JAVA_HOME="$(/usr/libexec/java_home -v 21)"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Reload the file or open a new terminal:

~~~sh
source ~/.zprofile
java -version
javac -version
~~~

If you use bash, place the configuration in the appropriate bash initialization file, usually `~/.bash_profile` for a login shell or `~/.bashrc` for an interactive shell.

Do not delete files in `/usr/bin` to fix Java errors. macOS JDK installations reside in `/Library/Java/JavaVirtualMachines`; use the installer or a JDK management tool to install/uninstall them.

## 6. How to Fix on Linux

### 6.1. Install Java from the Package Manager

On Ubuntu/Debian, refresh the package list and install the runtime if you only need to run applications:

~~~sh
sudo apt update
sudo apt install openjdk-21-jre
~~~

If you need the compiler and development tools, install the JDK:

~~~sh
sudo apt install openjdk-21-jdk
~~~

Package names and versions may vary depending on the distribution release and enabled repositories. Check available packages before installing:

~~~sh
apt-cache policy openjdk-21-jdk
apt-cache search openjdk
~~~

On Fedora or some RHEL-family distributions:

~~~sh
sudo dnf install java-21-openjdk
~~~

If you need `javac` and development tools, install the corresponding devel package:

~~~sh
sudo dnf install java-21-openjdk-devel
~~~

If the repository does not have Java 21, choose a version provided by your distribution or add an appropriate repository/vendor according to your machine's policy.

### 6.2. Check and Select the Default Java

On Ubuntu/Debian, view the registered alternatives:

~~~sh
sudo update-alternatives --display java
sudo update-alternatives --display javac
~~~

Select the default Java:

~~~sh
sudo update-alternatives --config java
~~~

Select the corresponding compiler if multiple JDKs are installed:

~~~sh
sudo update-alternatives --config javac
~~~

`java` and `javac` are two alternative groups that can be managed separately. After switching Java, check both the runtime and the compiler to avoid a situation where `java -version` and `javac -version` belong to two different JDKs.

On Fedora/RHEL, the equivalent tool is usually named `alternatives`:

~~~sh
sudo alternatives --display java
sudo alternatives --config java
~~~

Specific commands and options depend on the installed packages. Do not manually create a symbolic link to `/usr/bin/java` if the distribution manages that path with alternatives.

### 6.3. If Installing the JDK from an Archive

If you download a `.tar.gz` JDK archive and extract it into a user directory, the package may not automatically register with alternatives or PATH.

For example, if the JDK is extracted to `$HOME/opt/jdk-21`:

~~~sh
export JAVA_HOME="$HOME/opt/jdk-21"
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
~~~

Check the actual files:

~~~sh
ls -l "$JAVA_HOME/bin/java"
ls -l "$JAVA_HOME/bin/javac"
"$JAVA_HOME/bin/java" -version
~~~

If running directly works but typing `java` does not, the PATH configuration is missing `$JAVA_HOME/bin`.

### 6.4. Save Configuration for the Shell

For a bash interactive shell, you can add it to `~/.bashrc`; for a login shell, check `~/.bash_profile` or `~/.profile` depending on the distribution.

~~~sh
export JAVA_HOME="$HOME/opt/jdk-21"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

For zsh, use `~/.zshrc` or `~/.zprofile` depending on the type of shell session.

Reload the configuration:

~~~sh
source ~/.bashrc
java -version
javac -version
~~~

If bash has cached an old command location, refresh the command hash:

~~~sh
hash -r
command -v java
~~~

In zsh, you can run:

~~~sh
rehash
command -v java
~~~

## 7. Distinguishing Missing Runtime from Missing JDK

Some machines have a Java runtime to run applications but do not have a Java compiler. In that case:

~~~sh
java -version
~~~

may work, while:

~~~sh
javac -version
~~~

reports command not found.

If you are only running an already-compiled Java application, an appropriate runtime may be sufficient. If you are learning Java, compiling source code, running Maven/Gradle builds, or creating JARs, install a JDK.

A standard JDK includes both `java` and `javac` in its `bin` directory. Check directly:

~~~sh
ls "$JAVA_HOME/bin/java" "$JAVA_HOME/bin/javac"
~~~

On Windows:

~~~powershell
Test-Path "$env:JAVA_HOME\bin\java.exe"
Test-Path "$env:JAVA_HOME\bin\javac.exe"
~~~

If only `javac` is missing, check the installed package and `JAVA_HOME` before installing another runtime.

## 8. Environments That Often Have Separate PATHs

### 8.1. WSL and Windows Are Two Separate Environments

Installing a JDK in Windows does not automatically install a JDK in Ubuntu running under WSL. Each environment has its own filesystem, PATH, and package manager.

In WSL, check:

~~~sh
uname -a
command -v java
java -version
echo "$JAVA_HOME"
~~~

If using a Linux toolchain in WSL, install the JDK using the package manager inside WSL and use Linux paths such as `/usr/lib/jvm/...`. Do not mix a Windows `JAVA_HOME` with Linux paths in the same build configuration.

### 8.2. Docker Containers

Java installed on the host does not automatically appear inside a container. Check directly inside the running container:

~~~sh
docker exec -it <container-name> sh
java -version
command -v java
echo "$JAVA_HOME"
~~~

If the container lacks Java, update the base image or Dockerfile. Example of a build image using a JDK:

~~~dockerfile
FROM eclipse-temurin:21-jdk
WORKDIR /app
COPY . .
RUN ./mvnw --batch-mode verify
~~~

A runtime image may contain only a JRE if it only runs an already-built application. The build stage requires a compiler, so it must use a JDK. Make sure to check the right container, stage, and image tag.

### 8.3. IDEs and Build Tools

The terminal may use the correct Java while an IDE or Maven/Gradle uses a different JDK. Desktop applications can launch with their own environment and may not load the terminal's shell configuration files.

Check:

- Project SDK or Project Structure in IntelliJ IDEA.
- Java runtime and Java configuration in VS Code.
- Gradle JVM selected in the IDE.
- Maven importer JDK and Maven runner JDK.
- Which runtime the Run Configuration is pointing to.

With Maven, run:

~~~sh
mvn -version
~~~

With the Gradle wrapper:

~~~sh
./gradlew --version
~~~

Both commands show which Java the build tool is using. If `java -version` in the terminal is correct but Maven/Gradle reports a missing Java, check `JAVA_HOME` and the IDE's own JVM settings.

### 8.4. Services and CI Runners

Services running via systemd, launchd, or Windows Service may not read `.bashrc`, `.zshrc`, or the environment of an open terminal. Explicitly declare `JAVA_HOME` and the executable path in the service configuration or service manager.

In CI, each job has its own environment. Install/set up the JDK within the job itself before the build step, then print:

~~~sh
java -version
javac -version
echo "$JAVA_HOME"
~~~

On a PowerShell runner:

~~~powershell
java -version
javac -version
$env:JAVA_HOME
where.exe java
~~~

Do not rely on results from a terminal on a developer machine to conclude that the runner has Java. Always check inside the exact runner/container executing the job.

## 9. Using a Java Program to Confirm the Actual Runtime

Once `java` works, you can use the following program to print the process's version, vendor, architecture, and JDK home.

Create the file `JavaRuntimeProbe.java`:

~~~java
public class JavaRuntimeProbe {
    public static void main(String[] args) {
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("os.name=" + System.getProperty("os.name"));
        System.out.println("os.arch=" + System.getProperty("os.arch"));
        System.out.println("java.home=" + System.getProperty("java.home"));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~sh
javac --release 17 JavaRuntimeProbe.java
java JavaRuntimeProbe
~~~

The program prints the properties of the current runtime. `java.home` shows the actual Java home that the process is using; `java.version` and `java.vendor` help identify the version/vendor; `os.arch` helps check the architecture.

If `javac` is not found but `java` runs, fix the JDK/PATH before compiling this program.

## 10. Quick Troubleshooting Table

| Symptom | First Check | Resolution |
|---|---|---|
| `java: command not found` | `command -v java`, `echo "$PATH"` | Install JDK/runtime or add the bin directory to PATH |
| Windows does not recognize `java` | `where.exe java`, `$env:Path` | Set JAVA_HOME and add `%JAVA_HOME%\bin` |
| macOS cannot find runtime | `/usr/libexec/java_home -V` | Install a JDK for the right architecture and select the version |
| `java` runs but `javac` is missing | Check `JAVA_HOME/bin/javac` | Install a JDK or fix PATH to point to the JDK |
| Java runs an old version | `type -a java` or `where.exe java` | Fix PATH order or select the default JDK |
| Java works in terminal but not in IDE | Check Project SDK, Maven/Gradle JVM | Select the correct JDK in the IDE |
| Java works on host but not in Docker | Check inside the container | Update the base image/Dockerfile |
| Java works in Windows but not in WSL | Check `command -v java` in WSL | Install a Linux JDK inside WSL |
| `JAVA_HOME is not defined correctly` | Check the path and bin subdirectory | Set JAVA_HOME to the JDK root directory |
| `Could not find or load main class` | Check classpath and class name | Fix classpath/working directory; Java launcher already ran |
| `UnsupportedClassVersionError` | Compare compiler and runtime versions | Run with a newer runtime or compile with a lower target |
| `Permission denied` | Check file permissions and executable path | Fix permissions or invoke the correct executable |

## 11. Step-by-Step Troubleshooting Workflow

1. Run `java -version` to record the exact error message.
2. Use `command -v java` on Linux/macOS or `where.exe java` on Windows to locate the executable.
3. Check `JAVA_HOME` and confirm that the `bin` directory contains the Java files.
4. If the JDK/runtime is not installed, install it from a trusted vendor or package manager.
5. If it is already installed, add the correct `bin` directory to PATH.
6. If multiple JDKs exist, select the desired version and fix the PATH order or alternatives.
7. Open a new terminal; restart the IDE/service if they are holding onto an old environment.
8. Run `java -version` and `javac -version` again.
9. Run `mvn -version` or `./gradlew --version` if the error occurs in a build tool.
10. If using WSL, Docker, or CI, check inside that specific environment.
11. If the Java launcher already runs but the application still fails, move on to checking the classpath, runtime version, or dependencies according to the specific error message.

### Checklist

- [ ] Identified the exact error message and OS/shell.
- [ ] Checked `java -version`.
- [ ] Checked the executable with `command -v`, `where.exe`, or `Get-Command`.
- [ ] Confirmed that the JDK/runtime actually exists on the machine.
- [ ] Checked that JAVA_HOME points to the JDK root directory.
- [ ] Added the correct bin directory to PATH.
- [ ] Checked PATH order when multiple JDKs exist.
- [ ] Distinguished a missing runtime from a missing javac/JDK.
- [ ] Opened a new terminal after editing environment variables.
- [ ] Checked the IDE, Maven, or Gradle if the error only occurs in that tool.
- [ ] Checked WSL, Docker, service, or CI runner separately if in use.
- [ ] Confirmed the actual version/vendor after fixing.

Java-not-found errors are usually resolved by installing the right JDK/runtime and ensuring the `bin` directory is added to PATH in the exact environment running the command. Re-check `java -version`, `javac -version`, and `JAVA_HOME` after fixing to confirm that the terminal, IDE, and build tools are all using the right Java.

## References

- [Microsoft Learn — Get started with Java on Windows](https://learn.microsoft.com/en-us/windows/dev-environment/java)
- [Microsoft Learn — Install the Microsoft Build of OpenJDK](https://learn.microsoft.com/en-us/java/openjdk/install)
- [Oracle JDK 26 — Installation of the JDK on Linux Platforms](https://docs.oracle.com/en/java/javase/26/install/installation-jdk-linux-platforms.html)
- [Oracle JDK 26 — Installation of the JDK on macOS](https://docs.oracle.com/en/java/javase/26/install/installation-jdk-macos.html)
- [Oracle — How do I set or change the PATH system variable?](https://www.java.com/en/download/help/path.html)
- [Oracle Java Tutorials — PATH and CLASSPATH](https://docs.oracle.com/javase/tutorial/essential/environment/paths.html)
