# macOS Differences When Developing and Building Java

macOS has a Unix foundation and fully supports the Java Development Kit (JDK), but its development environment differs from Linux and Windows in how the JDK is installed, how multiple versions are managed, CPU architecture, shell, filesystem, native libraries, file execution permissions, and application protection mechanisms.

When migrating a Java project to Mac, check the JDK used by the terminal, the JDK used by the IDE, and the JDK in CI. On Apple Silicon, you need to determine whether the process is running native ARM64 or via Rosetta x86_64. For projects with native libraries or desktop application packaging, binary architecture and code signing are also part of the build process.

## 1. Two Mac Architectures to Distinguish

Intel Macs use an x86_64 CPU. Apple Silicon Macs use ARM64, often referred to as arm64 or AArch64. JDKs are distributed separately for each architecture; downloading the right build is the first step during installation.

| Mac Model | Hardware Architecture | Corresponding JDK Package |
|---|---|---|
| Intel Mac | x86_64 | macOS x64 |
| Apple Silicon Mac | ARM64 | macOS AArch64/ARM64 |

Oracle JDK provides installers for both macOS x64 and macOS AArch64. Do not assume that a JDK directory or native library can be shared between the two architectures.

### 1.1. Checking Machine and Process Architecture

Open Terminal:

~~~sh
sw_vers
uname -m
arch
~~~

Common results:

- `uname -m` returns `arm64` on Apple Silicon.
- `uname -m` returns `x86_64` on Intel Macs.
- On Apple Silicon, an x86_64 process running via Rosetta may report a process architecture different from the hardware architecture.

Check the Java executable:

~~~sh
command -v java
file "$(command -v java)"
file "$JAVA_HOME/bin/java"
~~~

On Apple Silicon, you can check whether the process is being translated via Rosetta:

~~~sh
sysctl -in sysctl.proc_translated 2>/dev/null || echo 0
~~~

A value of `1` indicates that the current process is running via Rosetta. If the command is not available on the machine or does not apply, use `uname -m` and `file` to identify the binary.

### 1.2. Rosetta Does Not Replace a Native JDK

Rosetta 2 allows running some x86_64 programs on Apple Silicon. This is useful when a build tool or native dependency does not yet have an ARM64 build. However, running an x86_64 JDK via Rosetta can make builds slower and forces native libraries to also be x86_64.

For new projects, prefer an ARM64 JDK and ARM64 native dependencies on Apple Silicon. Only use Rosetta when there is a specific compatibility reason, and then keep the architecture consistent across the entire process and native libraries.

If Java runs as ARM64 but a JNI library is only available for x86_64, the JVM cannot load that library. Similarly, an x86_64 JDK running via Rosetta cannot load a native library built only for ARM64.

## 2. Installing the JDK on macOS

There are two common approaches: a vendor installer or Homebrew. Both can coexist, but you need to select the right JDK for the terminal, IDE, and build process.

### 2.1. Installing via Vendor Installer

For Oracle JDK, download the package for the right architecture:

- Intel Mac: file with the `macos-x64` suffix.
- Apple Silicon: file with the `macos-aarch64` suffix.

The `.dmg` installer opens a `.pkg` package; run the installer and grant administrator privileges when prompted. The JDK is placed in:

~~~text
/Library/Java/JavaVirtualMachines/jdk-<FEATURE>.jdk/Contents/Home
~~~

For example, JDK 24 may be located at:

~~~text
/Library/Java/JavaVirtualMachines/jdk-24.jdk/Contents/Home
~~~

The `.jdk` directory is a macOS bundle. `JAVA_HOME` must point to `Contents/Home`, not to the outer `.jdk` directory.

Do not delete or replace the Java files in `/usr/bin`. This location contains tools managed by macOS; install and uninstall JDKs in `/Library/Java/JavaVirtualMachines`.

### 2.2. Installing via Homebrew

Homebrew provides current OpenJDK builds and versioned formulas such as `openjdk@21`.

~~~sh
brew search openjdk
brew info openjdk@21
brew install openjdk@21
~~~

Homebrew marks OpenJDK formulas as keg-only. This means the formula does not automatically replace the system Java tools. If you need macOS applications or `/usr/libexec/java_home` to recognize this JDK, read the caveats printed by `brew info openjdk@21`.

For the `openjdk@21` formula, Homebrew instructs creating a bundle symlink in the system JDK directory:

~~~sh
sudo ln -sfn "$(brew --prefix)/opt/openjdk@21/libexec/openjdk.jdk" \
  /Library/Java/JavaVirtualMachines/openjdk-21.jdk
~~~

This command creates a symbolic link in `/Library`; it requires administrator privileges. Check the formula's caveat path before running, especially when using a different formula or version.

Do not hardcode the Homebrew prefix. `brew --prefix` automatically returns the prefix of the current installation; Apple Silicon and Intel typically have different default prefixes.

### 2.3. Comparing Installer and Homebrew

| Criterion | Vendor Installer | Homebrew |
|---|---|---|
| Installation | `.dmg`/`.pkg` or archive | `brew install` |
| Typical location | `/Library/Java/JavaVirtualMachines` | Homebrew prefix |
| Recognized by `java_home` | Usually recognized directly | Keg-only formulas may require linking the bundle |
| Updates | Per vendor installer/release | Via Homebrew formula |
| Vendor/build selection | Depends on package provider | Depends on available formulas |
| Privileges | Installer may require admin | Installs formula into prefix; system link may require admin |

Use a consistent installation method in each CI environment to reduce path and update differences.

## 3. Selecting the Right JDK with `java_home` and `JAVA_HOME`

macOS provides the `/usr/libexec/java_home` tool to find and select installed JDKs. This is a notable difference compared to managing `JAVA_HOME` manually on many Linux machines.

### 3.1. Listing Installed JDKs

~~~sh
/usr/libexec/java_home -V
~~~

Check the default JDK:

~~~sh
java -version
javac -version
echo "$JAVA_HOME"
command -v java
command -v javac
~~~

Note: `java` and `javac` are resolved via `PATH`. A JDK may be installed without being the JDK that the terminal is currently using.

### 3.2. Selecting a Feature Release

Select JDK 21 for the current shell:

~~~sh
export JAVA_HOME="$(/usr/libexec/java_home -v 21)"
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
~~~

Select JDK 17 for a single command without changing the shell configuration:

~~~sh
/usr/libexec/java_home -v 17 --exec java -version
/usr/libexec/java_home -v 17 --exec javac -version
~~~

This is convenient when testing the same project across multiple feature releases. If no matching JDK is present, `java_home` will not be able to return a path; install the required version before building.

### 3.3. Saving Configuration for `zsh`

Modern macOS versions typically use `zsh` as the default shell. For login shells, environment configuration is usually placed in `~/.zprofile`; interactive shell configuration is usually placed in `~/.zshrc`.

Example to add to the appropriate configuration file:

~~~sh
export JAVA_HOME="$(/usr/libexec/java_home -v 21)"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

After saving, open a new terminal or reload the configuration file:

~~~sh
source ~/.zprofile
java -version
javac -version
~~~

Choose the right initialization file based on how the terminal is opened. Do not append the same block multiple times whenever switching JDKs; update the version value in one place to avoid duplicate `PATH` entries.

IDEs launched from Finder, desktop applications, or `launchd` may not receive the same shell environment as Terminal. If the IDE uses the wrong Java, check Project SDK/Gradle JVM/Maven JDK in the IDE and the runtime configuration of the application itself.

## 4. Paths and Environment Variables Differing from Windows

macOS and Linux use POSIX-style paths; Windows uses backslashes in many paths and semicolons to separate `PATH` entries.

| Property | macOS/Linux | Windows |
|---|---|---|
| Directory separator | `/` | `\` |
| `PATH` entry separator | `:` | `;` |
| Shell environment variable | `$JAVA_HOME` | `$env:JAVA_HOME` in PowerShell |
| Common JDK home | `.../Contents/Home` | `...\jdk-<version>` |
| Common default shell | `zsh` | PowerShell/Command Prompt |

In Java, do not concatenate paths using a hardcoded separator. Use the Java API:

~~~java
import java.nio.file.Path;

public class PathProbe {
    public static void main(String[] args) {
        Path config = Path.of("config", "application.yml");
        System.out.println(config);
        System.out.println("file.separator=" + System.getProperty("file.separator"));
        System.out.println("path.separator=" + System.getProperty("path.separator"));
    }
}
~~~

`Path.of("config", "application.yml")` automatically creates a path suitable for the operating system. `file.separator` is typically `/` on macOS and Linux, and `\` on Windows; `path.separator` is `:` on macOS/Linux and `;` on Windows.

Do not assume an absolute path such as `/Users/alice/project` or `C:\Users\alice\project` exists on every runner. Use the working directory, environment variables, or per-platform configuration.

## 5. APFS and Case Sensitivity in File Names

APFS is the common filesystem on Mac. The default APFS volume is case-insensitive yet case-preserving: the system does not distinguish between uppercase and lowercase when looking up files, but preserves the original casing of the file name. Users can create case-sensitive APFS volumes.

This creates differences when a project is developed on Mac and built on Linux:

- On default APFS, `Config.java` and `config.java` may refer to the same file.
- On a case-sensitive filesystem, those two names are two different paths.
- An import or resource path with the wrong casing may work on a Mac machine but fail on Linux CI.

Use exact, consistent casing in file names, packages, resource paths, and build commands. Avoid creating two files that differ only by case in the same directory.

If you need to rename a file differing only by case on a default volume, use an intermediate name with Git:

~~~sh
git mv Config.java Config.tmp
git mv Config.tmp config.java
~~~

Inspect changes before committing:

~~~sh
git status --short
git diff --summary
~~~

Do not rely on whether the local machine is case-sensitive to conclude that a repository is portable.

## 6. Executable Permissions and Line Endings of Shell Scripts

macOS uses Unix-style file permissions. Maven/Gradle wrapper scripts need the executable bit to be invoked directly with `./mvnw` or `./gradlew`.

If you encounter a `Permission denied` error, check and fix the permissions:

~~~sh
chmod +x mvnw gradlew
git add --chmod=+x mvnw gradlew
git ls-files --stage mvnw gradlew
~~~

In the Git index, executable files typically have mode `100755`. If the mode is `100644`, a checkout on Unix may not be able to run `./mvnw`.

Shell scripts on macOS should also use `LF` line endings. Script files with `CRLF` can cause interpreter errors, for example a `^M` character appended to the shebang path.

You can specify this in `.gitattributes`:

~~~gitattributes
*.sh text eol=lf
mvnw text eol=lf
gradlew text eol=lf
~~~

Then normalize existing files in the repository when needed:

~~~sh
git add --renormalize .
git diff --cached --check
~~~

Only commit line-ending changes after reviewing the diff to avoid creating an unintended mass-change commit.

## 7. BSD Tools vs. GNU Tools on macOS

macOS includes many command-line utilities from the BSD family. They do not always support all options of GNU coreutils.

Some scripts that run on Linux may fail on macOS because:

- GNU and BSD `sed -i` have different syntax.
- `date -d` is a common option on GNU `date` but is not compatible with BSD `date`.
- `readlink -f` is not available in the same way across all macOS versions.
- `stat` has different options between BSD and GNU.

When writing build scripts:

1. Prefer POSIX commands and options available across target platforms.
2. Use Java, Python, or Node for complex file processing that requires consistent behavior.
3. If GNU coreutils are genuinely needed, declare the dependency and install it via Homebrew in the Mac environment.
4. Do not assume `sed`, `date`, or `stat` on Mac behave identically to Linux.

Check which tool is being invoked:

~~~sh
command -v sed
sed --version
command -v date
date
~~~

On BSD `sed`, `sed --version` may not be supported. This is an example for identifying implementation differences, not a mandatory general check command for every shell script.

## 8. Native Libraries and JNI on macOS

Java bytecode usually runs across multiple operating systems, but native libraries are not automatically portable. JNI/JNA libraries must be built for the exact OS and CPU architecture.

| Platform | Common Native Library Format |
|---|---|
| macOS | `.dylib` |
| Linux | `.so` |
| Windows | `.dll` |

A JAR can contain multiple native libraries by classifier or separate directories per platform. The build needs to select the right artifact for macOS ARM64 or macOS x64.

If the JVM reports that it cannot load a native library:

1. Check the path configured in `java.library.path`.
2. Check whether the actual file exists and has read permissions.
3. Check the architecture of the JVM and the library.
4. Check the dynamic dependencies required by the library.

On macOS:

~~~sh
file path/to/libexample.dylib
otool -L path/to/libexample.dylib
~~~

`file` shows the binary architecture; `otool -L` lists dynamic library dependencies. On Linux, `file` and `ldd` are typically used; on Windows, equivalent tools such as `dumpbin` exist.

Do not force all native libraries to share a single cache key. Caches or artifacts for native code should be separated by OS, architecture, compiler/toolchain, and dependency version.

## 9. Xcode Command Line Tools When Building Native Code

A pure Java project usually only needs the JDK to compile Java. However, projects with JNI, C/C++, native image, certain packages, or build scripts with steps that invoke a native compiler may require Xcode Command Line Tools.

Check:

~~~sh
xcode-select -p
clang --version
xcrun --find clang
~~~

If the machine does not have the required development tools installed, macOS may prompt to install Command Line Tools:

~~~sh
xcode-select --install
~~~

Only install when the build actually needs Apple's compiler or SDK. Do not confuse Xcode Command Line Tools with the JDK; `javac` belongs to the JDK, whereas `clang` is the native compiler.

When building native libraries for Apple Silicon and Intel, run the build on each architecture or configure intentional cross-compilation. Do not treat an ARM64 binary as a usable artifact for an Intel runner.

## 10. Gatekeeper, Code Signing, and Notarization

macOS uses Gatekeeper to check software downloaded from outside the Mac App Store. Installers, desktop applications, and native plugins distributed to Mac users need to account for Developer ID code signing and notarization.

This is especially important when using `jpackage` to package a Java application into a `.app` or `.pkg` installer.

- **Code signing** attaches a signature to identify the publisher and verify the signed contents.
- **Notarization** submits the signed software to Apple so an automated system can check for security and code-signing issues.
- **Gatekeeper** uses signature/notarization information to decide how to warn and allow opening the software.
- Notarization is not App Review.

For installers or app bundles downloaded from vendors, use official sources and verify the signature. Do not disable Gatekeeper or remove the quarantine attribute as the default workaround for installation errors. If legitimate software is blocked, check the signature, notary status, and the publisher's instructions.

Some verification commands:

~~~sh
pkgutil --check-signature path/to/jdk-installer.pkg
codesign --verify --deep --strict --verbose=2 path/to/MyApp.app
spctl --assess --type execute --verbose path/to/MyApp.app
~~~

For Java applications distributed outside an organization, the release process typically requires:

1. Building the application and native dependencies for the target architecture.
2. Creating the app bundle or installer.
3. Signing executables and bundles in the proper order.
4. Notarizing with the Apple notary service.
5. Stapling the ticket when the deliverable type supports it.
6. Retesting on a clean Mac machine before release.

Do not store private signing keys, certificate passwords, or notarization credentials in the source repository or public build caches. Store them in the CI secret store and restrict which jobs have access.

## 11. Background Services on macOS Using `launchd`

Linux typically uses `systemd` for services; macOS uses `launchd` for `LaunchAgent` and `LaunchDaemon`.

A Java service that runs from Terminal may work there but fail when launched by `launchd`. Common causes are differences in the environment:

- `PATH` is shorter than in an interactive shell.
- `JAVA_HOME` is not declared.
- The working directory differs from the project directory.
- Log files or directories lack write permissions.
- The service is not permitted to access certain user locations.

In the plist, explicitly declare the executable path, arguments, working directory, and required environment. You can invoke Java using the absolute path under the JDK home rather than relying on a shell profile being loaded.

Example executable path:

~~~text
/Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home/bin/java
~~~

Inspect services using the `launchctl` tool. Do not use `systemctl` on macOS.

## 12. GitHub Actions: Testing macOS Intel and Apple Silicon

macOS runners can differ in operating system, CPU architecture, Xcode, and preinstalled tools. For GitHub-hosted runners, the `macos-26` label currently targets Apple Silicon ARM64, while `macos-26-intel` targets x64.

Example matrix testing Java on Linux, Windows, macOS ARM64, and macOS Intel:

~~~yaml
name: Cross-platform Java

on:
  push:
  pull_request:

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: ubuntu-24.04
          - os: windows-2025
          - os: macos-26
          - os: macos-26-intel

    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '21'

      - name: Inspect Java toolchain
        shell: bash
        run: |
          java -version
          javac -version
          java -XshowSettings:properties -version

      - name: Build and test
        shell: bash
        run: ./mvnw --batch-mode verify
~~~

In this matrix:

- `macos-26` runs on Apple Silicon ARM64.
- `macos-26-intel` runs on Intel x64.
- `ubuntu-24.04` and `windows-2025` verify Linux/Windows differences.
- `setup-java` installs the same vendor and Java feature release for fair comparison of results.
- `java -XshowSettings:properties -version` prints runtime information to compare `java.home`, `java.vendor`, and `os.arch`.

Runner labels and images are updated by the platform over time. Pin specific labels when a stable environment is needed; monitor runner image retirement/upgrade schedules before upgrading versions.

If a workflow only needs to test Java bytecode without packaging native libraries, an ARM64/x64 matrix can help catch architecture issues. If the application has JNI or packages a `.app`, run additional tests and packaging on each target architecture.

## 13. Java 17+ Example to Inspect the Runtime Environment

The following program prints the properties to compare when moving a project between macOS, Linux, and Windows.

Create `MacEnvironmentProbe.java`:

~~~java
public class MacEnvironmentProbe {
    public static void main(String[] args) {
        String[] keys = {
            "os.name",
            "os.version",
            "os.arch",
            "java.version",
            "java.vendor",
            "java.home",
            "file.separator",
            "path.separator",
            "line.separator"
        };

        for (String key : keys) {
            String value = System.getProperty(key)
                .replace("\n", "\\n")
                .replace("\r", "\\r");
            System.out.println(key + "=" + value);
        }
    }
}
~~~

Compile and run:

~~~sh
javac --release 17 MacEnvironmentProbe.java
java MacEnvironmentProbe
~~~

Important values to observe on Mac:

- `os.name` identifies macOS.
- `os.arch` reflects the architecture of the running JVM; the exact value may vary by vendor.
- `java.home` shows the JDK actually used by the process.
- `file.separator` and `path.separator` show path differences.
- `line.separator` shows the runtime's line ending.

Do not hardcode one machine's output into tests. Use these properties to select platform-specific behavior or print diagnostics when CI fails.

## 14. Common Errors When Moving a Project to macOS

| Symptom | Common Cause | Resolution |
|---|---|---|
| `Unable to locate a Java Runtime` | JDK not installed or Java launcher cannot find a JDK | Install the right package, check `/usr/libexec/java_home -V` |
| Terminal uses the wrong Java version | `PATH` points to another JDK | Select `JAVA_HOME` and check `command -v java` |
| Homebrew JDK does not appear in `java_home` | Formula is keg-only | Read `brew info` and link the bundle per the caveat |
| `Bad CPU type in executable` | `x86_64`/`ARM64` binary does not match the process or machine | Check `uname -m`, `file`, and use the right JDK |
| JNI reports `Library not loaded` | Missing `.dylib` dependency, wrong `rpath`, or wrong architecture | Use `otool -L` and `file` |
| `./mvnw: Permission denied` | Wrapper lacks executable bit | `chmod +x mvnw` and commit mode `100755` |
| Shell reports error at strange end of line | Script has `CRLF` or invalid shebang | Normalize `LF` with `.gitattributes` |
| Build passes on Mac but fails on Linux CI | Local filesystem is case-insensitive | Check exact file names and resource paths |
| Script runs on Linux but fails on Mac | Uses GNU-only options of `sed`, `date`, or `stat` | Use POSIX-compatible commands or explicit dependencies |
| IDE uses a different JDK than Terminal | Project SDK or Gradle/Maven JVM is configured separately | Select the JDK in the IDE and check the build tool's runtime |
| Application triggers a Gatekeeper warning | Package/app lacks valid signature or notarization | Verify download source, signature, and notarization status |
| Service cannot see `JAVA_HOME` | `launchd` does not load shell profiles | Declare environment and executable path in service config |

## 15. Checklist Process for Verifying a Java Project on Mac

1. Run `sw_vers` and `uname -m` to identify the OS and architecture.
2. Run `/usr/libexec/java_home -V` to list installed JDKs.
3. Select the appropriate JDK with `JAVA_HOME` and verify `java -version` and `javac -version`.
4. Check that the Java executable has the matching architecture using `file`.
5. Check that Maven/Gradle wrappers have the executable bit and `LF` line endings.
6. Check that file/resource names have exact casing to run on Linux.
7. Check native `.dylib` dependencies and architecture if the project uses JNI/JNA.
8. Check Xcode Command Line Tools if the build has native steps.
9. Check signing/notarization if creating an app bundle or installer for distribution.
10. Run tests on both macOS ARM64 and Intel if supporting both.
11. Re-run the build on Linux and Windows to catch Mac-specific assumptions.
12. Document the JDK vendor/version/architecture in build and CI documentation.

### Checklist

- [ ] Identified whether the Mac is Intel x64 or Apple Silicon ARM64.
- [ ] Installed the right JDK package for the architecture.
- [ ] Checked the `.jdk/Contents/Home` path.
- [ ] Know how to list and select JDKs using `/usr/libexec/java_home`.
- [ ] Verified `JAVA_HOME`, `PATH`, `java`, and `javac`.
- [ ] Distinguished Homebrew keg-only from installer-installed JDKs.
- [ ] Avoided mixing ARM64 and x86_64 JDKs/native libraries.
- [ ] Checked path separator and file separator via the Java API.
- [ ] Preserved executable bit and `LF` for Maven/Gradle wrappers.
- [ ] Checked file/resource casing on the filesystem.
- [ ] Checked BSD/GNU command compatibility.
- [ ] Checked JNI/JNA dependencies and `.dylib` if applicable.
- [ ] Verified signing/notarization for distributed apps or installers.
- [ ] Ran CI on macOS ARM64 and Intel if they are target platforms.

macOS differences directly affect how the JDK is installed and selected, binary architecture, shell environment, filesystem, and native dependencies. Use `java_home` to select the JDK, verify architecture before loading native libraries, keep scripts portable, and test on both ARM64 and x64 when the project supports both types of Mac.

## References

- [Oracle JDK 24 — Installation of the JDK on macOS](https://docs.oracle.com/en/java/javase/24/install/installation-jdk-macos.html)
- [Homebrew — Language Runtimes and Packages: Java](https://docs.brew.sh/Language-Runtimes-and-Packages#java)
- [Homebrew Formulae — openjdk@21](https://formulae.brew.sh/formula/openjdk@21)
- [Apple Developer — Notarizing macOS Software Before Distribution](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
- [Apple Developer — Signing Mac Software with Developer ID](https://developer.apple.com/developer-id/)
- [Apple Support — APFS formats, including case-sensitive volumes](https://support.apple.com/guide/disk-utility/dsku19ed921c/mac)
- [GitHub — Actions Runner Images and macOS architectures](https://github.com/actions/runner-images)
