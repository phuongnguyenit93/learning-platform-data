# Installing JDK 17 for the Right Operating System and CPU Architecture

You can install Java successfully and still be unable to compile a program if you accidentally choose **JRE instead of JDK**, confuse **Windows with Linux**, mix up **x64 and ARM64**, or leave the terminal pointing to an older Java installation. This lesson shows you how to choose the right **Java Development Kit (JDK) 17** package, configure your environment, and verify everything end to end on Windows, macOS, and Linux.

## 1. Understanding What You Need to Download

**JDK (Java Development Kit)** contains the tools to **write, compile, run, and inspect** Java applications:

| Component | Role | Check |
|---|---|---|
| `java` | Runs programs on the JVM | `java --version` |
| `javac` | Compiles `.java` source code into `.class` bytecode | `javac --version` |
| `jar` | Packages/inspects JAR file contents | `jar --version` |
| `jshell` | Evaluates Java expressions interactively | `jshell --version` |
| `javadoc` | Generates API documentation from source code | `javadoc --version` |

The JDK already includes the components needed to run Java programs; **you do not need to install a separate JRE to learn Java 17 programming**. When a download page offers a choice between **JDK/JRE**, select **JDK**.

In a Java 17 course, choose the **version 17 branch**, such as `17.0.x`, and prefer the latest security update in that branch. A higher Java version number (21, 25, 27...) does not automatically substitute for a Java 17 project requirement. `17.0.21` is an update in the Java 17 line, whereas `21.0.x` belongs to the Java 21 line.

### Which Vendor's JDK?

Common distributions include:

- **Eclipse Temurin (Adoptium):** an OpenJDK build well suited for learning and development across many operating systems. Download page: [adoptium.net/temurin/releases?version=17](https://adoptium.net/temurin/releases?version=17).
- **Microsoft Build of OpenJDK:** provides JDK 17 for multiple platforms, including **Windows ARM64** installers. Download page: [Microsoft Learn — Download OpenJDK](https://learn.microsoft.com/en-us/java/openjdk/download).
- **OpenJDK packages from OS repositories:** convenient on Ubuntu/Debian or RHEL/Fedora because they can be updated through the package manager.
- **Oracle JDK:** also an option, though you need to review its licensing and support terms for your intended use. Guide: [JDK 17 Installation Guide](https://docs.oracle.com/en/java/javase/17/install/).

Choose **an official source that supports your exact OS and CPU**, rather than downloading a similarly named file from an untrusted site.

## 2. Identifying the Right Triad: Java Version — Operating System — Architecture

Do not pick a package merely because a machine is described as "64-bit." The **x64** (Intel/AMD) and **ARM64** architectures are both 64-bit, but they use two different machine instruction sets.

| Machine in Use | Common Architecture Names | JDK 17 Package to Look For |
|---|---|---|
| Windows on 64-bit Intel/AMD CPU | `x64`, `amd64`, `x86_64` | **Windows x64**: usually `.msi` or `.exe` |
| Windows on 64-bit ARM CPU | `ARM64`, `aarch64` | **Windows ARM64**: pick a vendor offering an ARM64 build |
| Mac with Intel chip | `x86_64` | **macOS x64** |
| Mac with Apple Silicon (M1/M2/M3/M4/...) | `arm64`, `aarch64` | **macOS ARM64 / Apple Silicon** |
| Linux on 64-bit Intel/AMD CPU | `x86_64`, `amd64` | **Linux x64** |
| Linux on 64-bit ARM CPU | `aarch64`, `arm64` | **Linux ARM64** |

`amd64` is a common name for the 64-bit x86 architecture; **it does not mean the machine must use an AMD CPU**. `aarch64` is generally synonymous with ARM64. Suffixes such as `.msi`, `.pkg`, `.deb`, `.rpm`, and `.tar.gz` indicate the **distribution format**, not the architecture.

Environments to watch out for:

- **32-bit Windows:** even if the CPU is 64-bit capable, a 32-bit OS cannot run an x64 JDK. Java 17 for 32-bit x86 is only available from select vendors; if no suitable build exists, use a supported 64-bit OS.
- **Apple Silicon Mac:** if Terminal is running under **Rosetta**, some commands may report the process as `x86_64`. Check the **Chip** entry in *About This Mac* for the real hardware; prefer a native ARM64 build.
- **WSL on Windows:** when opening an Ubuntu/Debian terminal **inside WSL**, install a **Linux JDK** matching the WSL environment's architecture, not a Windows installer.
- **Docker/containers:** choose the JDK matching **the OS and architecture of the container being run**; cross-platform builds or native libraries may require specific configuration.
- **Alpine Linux:** typically uses **musl libc**, unlike many Linux distributions that use **glibc**. Choose a compatible **Alpine/musl** image/package rather than blindly extracting a Linux glibc `.tar.gz` archive.

### 2.1. Checking on Windows

Go to **Settings → System → About** and look at **System type**. The machine may show an **x64-based** or **ARM-based** processor.

To check via PowerShell:

```powershell
Get-CimInstance Win32_Processor | Select-Object Name, Architecture
```

In Windows' `Architecture` property, `9` typically indicates x64 and `12` indicates ARM64. Also read the CPU name if the result is unclear. The `PROCESSOR_ARCHITECTURE` variable only reflects the process environment in some situations, which can be misleading when running an application under an emulation layer.

### 2.2. Checking on macOS

Select **Apple menu → About This Mac**:

- Shows **Chip: Apple M...** → download **macOS ARM64/aarch64**.
- Shows **Processor: Intel...** → download **macOS x64**.

In Terminal:

```bash
uname -m
```

The output is typically `arm64` or `x86_64`. If using Rosetta, rely on the chip info in *About This Mac*.

### 2.3. Checking on Linux

```bash
uname -m
cat /etc/os-release
```

For example, `uname -m` returns `x86_64`, while `/etc/os-release` indicates whether the system is Ubuntu, Debian, Fedora, etc. The specific distribution determines whether to use `apt`, `dnf`, or another package format.

## 3. Installing JDK 17 on Windows

### Option A — Windows x64: Installing Eclipse Temurin via MSI

1. Open the [Temurin 17 download page](https://adoptium.net/temurin/releases?version=17).
2. Choose **Version 17**, **Operating System: Windows**, **Architecture: x64**, **Package Type: JDK**, and the **MSI** file.
3. Run the downloaded `.msi` file and follow the installer wizard.
4. Under installation options, enable **Add to PATH**. Also enable **Set/Update JAVA_HOME** if offered by the installer; with the Temurin MSI, the `JAVA_HOME` option may need to be explicitly selected.
5. When installation finishes, **close old terminals and open a new PowerShell window**.

Verify:

```powershell
java --version
javac --version
where.exe java
where.exe javac
```

The first two commands must report **Java 17**; `javac` must exist. The path is usually under `C:\Program Files\Eclipse Adoptium\...` (the exact folder name depends on the patch version).

> **Note:** Temurin's MSI documentation states that its Windows MSI installer is for **Windows x64**. For Windows ARM64, choose a vendor/installer that genuinely supports ARM64.

### Option B — Windows ARM64: Using a Native ARM64 JDK 17 Package

1. Open [Microsoft Build of OpenJDK — Downloads](https://learn.microsoft.com/en-us/java/openjdk/download).
2. Find the **OpenJDK 17** section, under **Windows — AArch64 / ARM64**.
3. Choose `.msi`/`.exe` if provided on the page, or `.zip` for manual installation.
4. Install and verify `java` and `javac` just like on Windows x64.

Do not rename an x64 file to ARM64: filenames do not convert architectures. Some x64 programs can run under emulation on Windows ARM, but a **native ARM64 JDK build** is usually the better choice when supported.

### Manually Setting `JAVA_HOME` and `Path` on Windows

Only needed if the installer did not set them or they point to the wrong JDK:

1. Open **Edit the system environment variables → Environment Variables**.
2. Create/edit **JAVA_HOME** to point to **the JDK 17 root directory**, for example `C:\Program Files\Eclipse Adoptium\jdk-17.0.x...-hotspot`. Do **not** append `\bin` to the `JAVA_HOME` value.
3. In the appropriate user or system **Path** variable, add `%JAVA_HOME%\bin`.
4. If `Path` contains another Java path earlier in the list, adjust the order so JDK 17 takes precedence (do not carelessly delete entries that other applications still rely on).
5. Open a new terminal:

```powershell
$env:JAVA_HOME
Get-Command java | Select-Object Source
Get-Command javac | Select-Object Source
java --version
javac --version
```

If you only want to test **in the current PowerShell session**, you can configure it temporarily after replacing the example path with the real directory:

```powershell
$env:JAVA_HOME = 'C:\Program Files\Eclipse Adoptium\jdk-17.0.x...-hotspot'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
```

Temporary settings expire when the window closes. When editing environment variables permanently, use the system dialog so you can clearly inspect the full `Path` and avoid accidental overwrites.

## 4. Installing JDK 17 on macOS

### Option A — Downloading the Official PKG File

1. Open [Temurin 17 Releases](https://adoptium.net/temurin/releases?version=17).
2. Select **macOS x64** for Intel or **macOS aarch64/ARM64** for Apple Silicon.
3. Select **JDK** and the **PKG** file; open the file to install.
4. Open a new Terminal and check:

```bash
/usr/libexec/java_home -V
java --version
javac --version
```

On macOS, PKG-installed JDKs are typically placed under `/Library/Java/JavaVirtualMachines/`. `/usr/libexec/java_home` is a built-in macOS utility for locating system-recognized JDKs.

### Option B — Using Homebrew If Already Installed

```bash
brew install --cask temurin@17
```

The `temurin@17` cask is listed in [Homebrew Formulae](https://formulae.brew.sh/cask/temurin@17). If using Homebrew, verify compatibility of the cask with your running macOS version.

### Selecting JDK 17 When Multiple Versions Exist

```bash
/usr/libexec/java_home -V
/usr/libexec/java_home -v 17 --exec javac --version
```

To use JDK 17 in the current Terminal session:

```bash
export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
export PATH="$JAVA_HOME/bin:$PATH"
java --version
javac --version
```

With **zsh**, you can add those two `export` lines to `~/.zshrc` if you want them applied to new interactive shell sessions. If using bash or another shell startup setup, edit the corresponding configuration file. After editing, open a new Terminal.

> If `/usr/libexec/java_home -v 17` does not find a JDK, confirm that you installed a **JDK** package matching macOS and your machine's architecture, then check `/usr/libexec/java_home -V`.

## 5. Installing JDK 17 on Linux

### 5.1. Ubuntu/Debian: Using `apt`

On Ubuntu/Debian releases that provide a JDK 17 package in the configured repositories:

```bash
sudo apt update
sudo apt install openjdk-17-jdk

java --version
javac --version
```

`apt` automatically picks the package matching the OS architecture. There is no need to manually download an `x64` file for an ARM64 machine when the repository already provides the corresponding variant.

Check the actual resolved paths:

```bash
readlink -f "$(command -v java)"
readlink -f "$(command -v javac)"
```

If multiple Java versions are installed, Ubuntu/Debian typically uses `update-alternatives`:

```bash
sudo update-alternatives --config java
sudo update-alternatives --config javac
```

Choose the **JDK 17** entry for **both** commands. Do not switch only `java` and forget `javac`.

### 5.2. Fedora/RHEL: Using `dnf` When the Repository Has JDK 17

```bash
sudo dnf install java-17-openjdk-devel

java --version
javac --version
```

The `-devel` suffix identifies the package containing development tools such as `javac`. On RHEL/Fedora systems, JDK version availability depends on the release and enabled repositories; if the package is not found, check the enabled package sources and distribution documentation instead of blindly substituting a newer Java version.

When multiple JDKs are present, on systems using `alternatives` you can select:

```bash
sudo alternatives --config java
sudo alternatives --config javac
```

### 5.3. Setting `JAVA_HOME` on Linux

Most JDK packages managed via `apt`/`dnf` already configure executable paths. Some build tools still require `JAVA_HOME`. You can determine the root directory from the selected `javac`:

```bash
readlink -f "$(command -v javac)"
```

For example, if the output is `/usr/lib/jvm/java-17-openjdk-amd64/bin/javac`, then the corresponding `JAVA_HOME` is `/usr/lib/jvm/java-17-openjdk-amd64`. Paths on ARM64 or other distributions may differ; **do not copy the example path verbatim**.

To derive the path dynamically in the current bash session:

```bash
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
export PATH="$JAVA_HOME/bin:$PATH"

printf '%s\n' "$JAVA_HOME"
"$JAVA_HOME/bin/javac" --version
```

When persisting configuration across sessions, place the appropriate `export` lines in the **user's** shell configuration file, taking existing system configuration into account. For build servers, containers, and CI, it is generally better to declare the specific JDK in the environment configuration or project toolchain rather than changing the machine-wide Java default.

### 5.4. When a Package Manager Cannot Be Used

You can download a `.tar.gz` archive from an official source matching **Linux + CPU + libc**, extract it into a directory you manage, and point `JAVA_HOME` to the directory containing `bin/java` and `bin/javac`:

```bash
mkdir -p "$HOME/.local/jdks"
tar -xzf /path/to/jdk-17-matching-os-and-cpu.tar.gz -C "$HOME/.local/jdks"
```

The name in the command is an **illustrative path**; replace it with the actual downloaded filename. Inspect the extracted directory before setting variables:

```bash
ls "$HOME/.local/jdks"
```

Using a compressed archive is convenient when lacking admin privileges or maintaining multiple JDK versions for different projects. However, you must actively update the JDK and adjust the path when switching patches.

## 6. Verifying You Are Actually Using the Right JDK 17

Do not stop at seeing a Java icon or having one app launch. Complete all of the following steps in a **new terminal**.

### Step 1 — Check Runtime and Compiler Versions

```text
java --version
javac --version
```

A valid output looks like:

```text
openjdk 17.0.x ...
...
javac 17.0.x
```

The `x` represents a patch level that may vary. What matters is that **both tools are version 17**, not a specific fixed patch number.

### Step 2 — Identify Which Java Is Actually Running

On **Windows PowerShell**:

```powershell
Get-Command java | Select-Object Source
Get-Command javac | Select-Object Source
java -XshowSettings:properties -version 2>&1 | Select-String 'java.home|os.arch'
```

On **macOS/Linux**:

```bash
command -v java
command -v javac
java -XshowSettings:properties -version 2>&1 | grep -E 'java.home|os.arch'
```

`java.home` indicates the runtime the process is actually using. `os.arch` describes the architecture of the **running JVM** (typically `amd64` or `aarch64`); if running under emulation, this value may differ from the physical hardware architecture. Compare it with the CPU detection results from Section 2.

### Step 3 — Write, Compile, and Run Your First Program

Create **`HelloJdk17.java`** with the exact filename and contents:

```java
public class HelloJdk17 {
    public static void main(String[] args) {
        System.out.println("Java " + Runtime.version().feature());
        System.out.println("JVM architecture: " + System.getProperty("os.arch"));
        System.out.println("JVM vendor: " + System.getProperty("java.vendor"));
    }
}
```

In a terminal positioned in the directory containing the file:

```bash
javac --release 17 HelloJdk17.java
java HelloJdk17
```

Example output:

```text
Java 17
JVM architecture: amd64
JVM vendor: Eclipse Adoptium
```

The architecture and vendor lines depend on your machine and distribution. If `HelloJdk17.class` is produced and the program prints `Java 17`, you have verified that both the **compiler** and **runtime** work. The `--release 17` flag tells the compiler to produce target bytecode/APIs for Java 17; here, JDK 17 itself is being used.

## 7. Troubleshooting Common Errors by Symptom

| Symptom | Common Cause | How to Fix |
|---|---|---|
| `java` or `javac` is not recognized | Terminal has not picked up new `Path`; wrong path; only JRE installed | Open a new terminal; check `Path` and the **JDK** `bin` directory |
| `java` works but `javac` is missing | Using a runtime/JRE or wrong binary selected | Install **JDK 17** and put the JDK `bin` directory in `Path` |
| `java` shows 21/25 while `javac` shows 17, or vice versa | Multiple JDKs installed with misaligned `Path`/alternatives order | Check each command's path and select the same JDK 17 for both |
| `JAVA_HOME` reported invalid | Points to `bin`, deleted directory, or outdated patch folder name | Set `JAVA_HOME` to the **root directory** containing `bin/java` and `bin/javac` |
| Windows says the app cannot run | Wrong OS/architecture selected, or unsupported environment | Download the matching **Windows x64/ARM64** build; check 32/64-bit OS |
| macOS reports `bad CPU type in executable` | Binary does not match architecture/environment | Choose the right **macOS x64** or **macOS ARM64**, check Rosetta |
| Linux reports `Exec format error` | Executable does not match CPU/OS | Check `uname -m` and select the Linux build for that architecture |
| Linux reports `No such file or directory` even though the file exists | Likely wrong dynamic loader/libc (e.g., glibc vs. musl), or incompatible binary | Check distro/libc; choose a native package for the running system |
| macOS `Unable to locate a Java Runtime` | Proper JDK not installed or not recognized by macOS | Install an official PKG and check `/usr/libexec/java_home -V` |
| `UnsupportedClassVersionError` when running a class | Bytecode was compiled for a newer Java than the running runtime | Compare compile/run versions; use Java 17 or build with `--release 17` when appropriate |

**If the terminal works correctly but the IDE reports the wrong JDK:** inspect **Project SDK**, **Gradle JVM**, **Maven JDK**, or **Java Toolchain** separately in the IDE/project settings. The IDE and OS can pick two different JDKs; do not alter source code to work around an environment selection issue.

**Do not** attempt to fix errors by deleting every other JDK, always running the terminal as administrator, or applying `chmod -R 777` to the Java directory. First identify the exact version, path, and architecture being invoked.

## 8. Updating, Safety, and Working Across Multiple Projects

- **Update within the 17 branch:** Java 17 continues receiving patches on each vendor's cadence. Periodically check official release pages, install the appropriate Java 17 update, and re-verify `java`/`javac`.
- **Verify downloaded files:** if the publisher provides a SHA-256 hash, check it against the downloaded file. On Windows PowerShell use `Get-FileHash .\file-name.msi -Algorithm SHA256`; on macOS use `shasum -a 256 file-name.pkg`; on Linux use `sha256sum file-name.tar.gz`. The value must **match exactly** the published checksum for that specific file.
- **Avoid hardcoding a patch-specific path:** directory names may change from `jdk-17.0.x` to `jdk-17.0.y` during updates. After each upgrade, re-check `JAVA_HOME` if you set it to an absolute path manually.
- **Distinguish system JDK from project JDK:** Maven, Gradle, IDEs, CI, and containers can each have their own settings. A project requiring Java 17 should explicitly declare a Java 17 toolchain/target; do not expect every teammate's machine to default to 17.
- **Keep build and runtime compatible:** Java 17 bytecode runs on JVM 17 and compatible newer Java runtimes, but if newer APIs are present, consider targeting `--release 17` and testing against the actual deployment environment.

## 9. Three Scenarios for Choosing Your Own Download

**Scenario 1 — Windows 11, Intel Core i5 CPU:** OS is Windows, CPU is 64-bit x86. Choose **JDK 17 / Windows / x64 / MSI**. After installation, check `java --version` and `javac --version`.

**Scenario 2 — MacBook with M2 chip:** Apple Silicon is ARM64. Choose **JDK 17 / macOS / aarch64 / PKG** or `brew install --cask temurin@17`. Confirm with `/usr/libexec/java_home -V`.

**Scenario 3 — Ubuntu running in WSL on an x64 Windows machine:** Inside WSL you need **Linux x64 JDK**, installed via `sudo apt install openjdk-17-jdk` if available in the package repository. Installing Windows JDK on the host side does not automatically configure JDK inside Linux WSL.

**Self-check:** Answering these four questions confirms you selected and configured the right environment: (1) Which OS is the machine/terminal running? (2) What is the architecture of the environment where Java needs to run? (3) Is **JDK 17** installed from a trusted source? (4) Are `java` and `javac` both version 17, and can they compile and run `HelloJdk17.java`?

## Official References

- [Eclipse Adoptium — Download Temurin 17](https://adoptium.net/temurin/releases?version=17)
- [Eclipse Adoptium — Supported Platforms and Architectures](https://adoptium.net/supported-platforms/)
- [Eclipse Adoptium — Windows MSI Installation](https://adoptium.net/installation/windows)
- [Eclipse Adoptium — Linux RPM/DEB/APK Installation](https://adoptium.net/installation/linux)
- [Microsoft Learn — Microsoft Build of OpenJDK Downloads](https://learn.microsoft.com/en-us/java/openjdk/download)
- [Ubuntu — Setting Up the Java Environment](https://ubuntu.com/developers/docs/howto/java-setup/)
- [Red Hat — Installing Red Hat Build of OpenJDK 17 on RHEL](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/17/html-single/installing_and_using_red_hat_build_of_openjdk_17_on_rhel/index)
- [Homebrew Formulae — temurin@17](https://formulae.brew.sh/cask/temurin@17)
- [Oracle — JDK 17 Installation Guide](https://docs.oracle.com/en/java/javase/17/install/)
