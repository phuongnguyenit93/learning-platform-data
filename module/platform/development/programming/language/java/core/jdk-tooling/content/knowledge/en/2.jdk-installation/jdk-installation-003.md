# JDK by Operating System

The JDK (Java Development Kit) is the toolkit used to develop and run Java applications. A modern JDK includes the `javac` compiler, the virtual machine and `java` launcher, the `jar` packaging tool, the `javadoc` documentation tool, and the `jshell` interactive environment. When learning or building Java projects, install the **full JDK** rather than just a stripped-down runtime: running `javac` is the fastest way to confirm your machine has a compiler.

The installation steps differ across Windows, macOS, and Linux, but the end result is the same: the operating system locates the right JDK directory, the `JAVA_HOME` variable points to the JDK root directory, and `java` and `javac` use the same major version.

The command examples below use JDK 21. If your course or project requires a different version, substitute the corresponding version number and package name. Prioritize the version declared in your project configuration, such as a Gradle toolchain or Maven compiler release.

## 1. Choose the Right JDK Before Installing

A JDK distribution is defined by three factors:

- **Java version:** Choose the exact major version required by your project. Two builds with the same major version may differ in patch number, such as 21.0.1 and 21.0.2.
- **Vendor:** OpenJDK is the open-source project; vendors package and test distributions such as Eclipse Temurin, Oracle JDK, Amazon Corretto, Azul Zulu, or Microsoft Build of OpenJDK. Use a source approved by your organization or project.
- **CPU architecture:** Choose the package matching your machine, typically x64/amd64 or ARM64/aarch64. A package for the wrong architecture may fail to install or run.

You can check the architecture on macOS and Linux with:

```sh
uname -m
```

Common outputs are `x86_64` for 64-bit Intel/AMD machines and `arm64` or `aarch64` for 64-bit ARM. On Windows, check **Settings → System → About → System type** to see your operating system and processor architecture.

Download the installer from the vendor's official website. Verify the version name and architecture before installing; do not obtain installers from unverified third-party sharing sites. If your project has specific requirements regarding vendor, version, or license, follow those requirements.

## 2. Installing the JDK on Windows

### 2.1. Installing with the MSI Installer

1. Determine whether your machine is x64 or ARM64.
2. Download the appropriate JDK package, such as Eclipse Temurin JDK 21 for Windows.
3. Run the MSI file and follow the installation wizard.
4. If the installer offers options to add the JDK to `PATH` or set `JAVA_HOME`, you can enable those options. Option names vary by vendor and installer version.
5. Complete the installation, then open a new PowerShell window.

The installation directory is usually under `C:\Program Files\`, though the exact folder name depends on the vendor and release. For example:

```text
C:\Program Files\Eclipse Adoptium\jdk-21...
```

The ellipsis represents the actual version string on your machine; use the exact directory that was installed.

### 2.2. Setting JAVA_HOME and PATH

`JAVA_HOME` must point to the **JDK root directory**, not the `bin` directory. Inside the root directory, there should be a `bin` subdirectory containing `java.exe` and `javac.exe`.

To configure it permanently via the Windows UI:

1. Open Start and search for **Edit the system environment variables**.
2. Click **Environment Variables**.
3. Under User variables (applies only to the current account) or System variables (applies system-wide), create the `JAVA_HOME` variable.
4. Set the value of `JAVA_HOME` to the JDK root directory path, for example `C:\Program Files\Eclipse Adoptium\jdk-21...`.
5. Select the `Path` variable, click Edit, and add a new entry: `%JAVA_HOME%\bin`.
6. Save and close the configuration windows. Open a new PowerShell or Terminal window to pick up the updated environment variables.

Do not put quotation marks around the value in the Environment Variables dialog. When editing `Path`, add a separate entry and keep the existing entries; do not replace the entire `Path` with a single Java path.

If you only want to test in the current PowerShell window, run the following commands and replace the path with your actual JDK directory:

```powershell
$env:JAVA_HOME = 'C:\Program Files\Eclipse Adoptium\jdk-21...'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
```

These PowerShell commands only modify the environment for the current window and processes launched from it. To apply changes permanently, use the Environment Variables UI or configure the environment according to your machine's policies.

### 2.3. Verifying on Windows

```powershell
$env:JAVA_HOME
java -version
javac -version
where.exe java
where.exe javac
```

`where.exe` lists all matching executables found in `PATH` lookup order. When multiple results appear, the first entry is typically the one invoked. That first path should belong to your intended JDK. In PowerShell, you can also inspect further with:

```powershell
Get-Command java -All
Get-Command javac -All
```

## 3. Installing the JDK on macOS

### 3.1. Choosing the Right Architecture Installer

Check your architecture with:

```sh
uname -m
```

- `arm64`: typically Apple Silicon Macs.
- `x86_64`: typically Intel-based Macs.

Download the macOS JDK package for the matching architecture from your chosen vendor. For `.pkg` installers, open the file and follow the prompts. macOS typically installs JDKs under:

```text
/Library/Java/JavaVirtualMachines/<jdk-name>.jdk/Contents/Home
```

The actual directory name varies by vendor and version. You do not need to create this directory manually; the installer manages the installation location.

### 3.2. Selecting the JDK and Setting JAVA_HOME

macOS provides the `/usr/libexec/java_home` utility to locate installed JDKs. List all installed JDKs:

```sh
/usr/libexec/java_home -V
```

Select JDK 21 for the current Terminal session:

```sh
export JAVA_HOME=$(/usr/libexec/java_home -v 21)
export PATH="$JAVA_HOME/bin:$PATH"
```

To persist this across future zsh Terminal sessions, append those two `export` lines to `~/.zshrc`, then reload the configuration:

```sh
source ~/.zshrc
```

zsh is the default shell on modern macOS versions. If you are using bash or another shell, place the configuration in the appropriate startup file for that shell. Do not copy zsh configuration verbatim into a shell with different initialization rules.

When multiple JDKs are installed, the `-v 21` flag selects major version 21. If the requested version is not installed, `java_home` may report an error; install the required version before setting `JAVA_HOME`.

### 3.3. Verifying on macOS

```sh
echo "$JAVA_HOME"
java -version
javac -version
command -v java
command -v javac
```

`command -v` shows the exact path the shell resolves for a command. That path should point to the JDK you just selected.

## 4. Installing the JDK on Linux

Linux has many distributions. Installation methods depend on each distribution's package manager and software repositories. The two examples below use Debian/Ubuntu and Fedora; adjust the package names for your OS version.

### 4.1. Debian or Ubuntu

Update the package index and install the JDK:

```sh
sudo apt update
sudo apt install openjdk-21-jdk
```

The `openjdk-21-jdk` package provides the development toolkit, including the `javac` compiler. Package availability depends on your OS release and enabled repositories. If the package manager cannot find the package, check your Ubuntu/Debian version and official repositories; do not install a random similarly named package.

### 4.2. Fedora

Install the OpenJDK development package using DNF:

```sh
sudo dnf install java-21-openjdk-devel
```

The `-devel` suffix indicates the development package containing tools such as the compiler. If you need a different major version, search for the corresponding package in your Fedora release's repositories.

### 4.3. Choosing the Default Version When Multiple JDKs Are Installed

On Debian/Ubuntu, `update-alternatives` can manage the default versions of Java commands. View and select the default launcher:

```sh
sudo update-alternatives --config java
```

Next, select the compiler version:

```sh
sudo update-alternatives --config javac
```

Make sure `java` and `javac` are selected from the same major version. Not all Linux distributions use `update-alternatives`; use the version management mechanism provided by your operating system.

### 4.4. Setting JAVA_HOME on Linux

Once the right JDK is selected, you can derive the JDK directory from the real path of `javac` on systems that support GNU `readlink -f`:

```sh
JAVAC_PATH="$(readlink -f "$(command -v javac)")"
export JAVA_HOME="$(dirname "$(dirname "$JAVAC_PATH")")"
export PATH="$JAVA_HOME/bin:$PATH"
```

For example, if the real path to the compiler is `/usr/lib/jvm/java-21-openjdk-amd64/bin/javac`, then `JAVA_HOME` will be `/usr/lib/jvm/java-21-openjdk-amd64`.

To persist this configuration for new shell sessions, add the `export` lines to your shell's startup file, typically `~/.bashrc` for bash or `~/.zshrc` for zsh. Then reload the file, for example:

```sh
source ~/.bashrc
```

If your system does not have `readlink -f`, look up the JDK path from installed package metadata or your distribution's version management tool. Do not set `JAVA_HOME` to `/usr/bin` or to the JDK's `bin` directory.

### 4.5. Verifying on Linux

```sh
echo "$JAVA_HOME"
java -version
javac -version
command -v java
command -v javac
```

When multiple JDKs are present, some distributions also support `which -a java` to list all matching commands found on `PATH`.

## 5. Verifying the JDK Works by Compiling a Program

Being able to run `java -version` alone is not enough to prove a full JDK is installed; your machine might only have a runtime. Check `javac` as well, then compile and run a small program.

Create a file named `JdkCheck.java` with the following content:

```java
public class JdkCheck {
    public static void main(String[] args) {
        System.out.println("JDK is ready");
    }
}
```

Open a Terminal in the directory containing the file and run:

```sh
javac JdkCheck.java
java JdkCheck
```

Expected output:

```text
JDK is ready
```

If `javac` produces `JdkCheck.class` and `java` prints the line above, the basic compiler and runtime are working. Delete the test files afterward if you no longer need them.

Compare the major versions of both tools:

```sh
java -version
javac -version
```

For example, if your project requires Java 21, both commands should report major version 21. Patch numbers and version string formatting may vary by vendor.

## 6. Understanding and Configuring JAVA_HOME and PATH

These two variables serve different purposes:

- `JAVA_HOME` specifies the JDK root directory that build tools or scripts can reference.
- `PATH` is the list of directories the operating system searches when you type a command. Adding `%JAVA_HOME%\bin` (Windows) or `$JAVA_HOME/bin` (macOS/Linux) to `PATH` lets you invoke `java` and `javac` from any directory.

Example of a valid structure:

```text
JAVA_HOME
└── JDK root
    └── bin
        ├── java
        ├── javac
        ├── jar
        └── javadoc
```

Do not set `JAVA_HOME` to a path ending in `/bin` or `\bin`. If `JAVA_HOME` points to the wrong location, many tools will fail to locate the JDK layout even if `java` still runs via another entry in `PATH`.

The order of entries in `PATH` matters. When multiple JDKs are installed, the operating system generally runs the command from the first matching entry. Therefore, check the actual resolved path rather than relying solely on the `JAVA_HOME` value.

## 7. Using Multiple JDK Versions

A machine can have multiple major versions installed to support different projects. How you switch the default depends on the operating system:

- **Windows:** Update `JAVA_HOME` and the order of `%JAVA_HOME%\bin` in `Path`, then open a new Terminal. You can set environment variables per PowerShell window to test without changing permanent configuration.
- **macOS:** Use `/usr/libexec/java_home -v <major>` to get the path to the desired major version, then set `JAVA_HOME`.
- **Debian/Ubuntu:** Use `update-alternatives --config java` and `update-alternatives --config javac` if the JDKs are registered with the system.

Do not assume every tool picks up Java from the same place. An IDE may have its own Project SDK setting; Gradle may use the JVM configured in the IDE or the project's toolchain; Maven may also run with a different JDK than the one you check in the Terminal.

When you need to confirm which JVM a build tool is using, run the corresponding command from the project directory:

```sh
./gradlew -version
mvn -version
```

Run only the command for the build tool your project actually uses. On Windows, the Gradle Wrapper is typically invoked as `gradlew.bat -version`. If you just switched JDKs but the IDE or Gradle still reports the old version, close and reopen the Terminal/IDE; for Gradle, you can stop the old daemon with:

```sh
./gradlew --stop
```

Then run the check command again. If the project defines a toolchain configuration, check that configuration before changing the system-wide default JDK.

## 8. Common Issues and Troubleshooting

| Symptom | Common Cause | How to Check and Fix |
|---|---|---|
| Windows reports `java is not recognized`; macOS/Linux reports `command not found` | The JDK's `bin` directory is not in `PATH`, or the Terminal was opened before updating environment variables | Check `JAVA_HOME`, add the correct `bin` directory to `PATH`, open a new Terminal, and try again |
| `java` runs, but `javac` is missing | Only a runtime is installed, or `PATH` points to an installation without development tools | Install the full JDK and ensure `PATH` points to that JDK's `bin` directory |
| `java -version` reports an older version | Another JDK appears earlier in `PATH`, or a different system default is selected | Run `where.exe java` on Windows or `command -v java` / `which -a java` on macOS/Linux; fix the `PATH` order or reselect alternatives |
| `JAVA_HOME` is invalid | The variable points to `bin`, a non-existent directory, or an uninstalled JDK | Reset the variable to the actual JDK root directory containing the `bin` subdirectory |
| Terminal uses the right Java, but the IDE uses a different one | The IDE stores a separate Project SDK or Gradle JVM setting | Select the right JDK in the project's SDK/JVM settings and restart the IDE process if needed |
| `java` and `javac` report different major versions | The two commands resolve to different installations | Check the resolved path of both commands; align `PATH`, `JAVA_HOME`, and the default version selector |
| Installer fails to run or reports wrong architecture | Downloaded the wrong x64/ARM64 package or wrong OS | Check your machine's architecture and re-download the matching package from the vendor |
| Package manager cannot find the JDK package | The repository or OS version does not provide that major version | Check official repositories and package names for your distribution; use an official vendor package if needed |

Some compilation or runtime errors do not stem from the JDK installation. For example, errors caused by a project requiring a newer Java version, an incompatible Gradle plugin, or mismatched source/target settings must be resolved in the project configuration. Before modifying source code, determine the exact JDK version required by the project and the version currently used by the build tool.

## 9. Post-Installation Checklist

Before starting to learn or run a project, verify each item in order:

1. The right major version is selected according to project requirements.
2. The installer matches your operating system and CPU architecture.
3. `JAVA_HOME` points to the JDK root directory.
4. `PATH` includes the `bin` directory of the desired JDK.
5. `java -version` and `javac -version` report the same major version.
6. `JdkCheck.java` compiles and runs successfully.
7. Your IDE and project build tools are also using the correct JDK version.

Once these steps are complete, your machine has a working baseline JDK environment for compiling and running Java programs.