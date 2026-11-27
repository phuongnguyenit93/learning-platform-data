# Building Packages per Target Platform and Testing on Clean Machines

A JAR file containing Java bytecode can often run on multiple operating systems if the target machine has a compatible runtime. However, when distributing an application to end users, sending only a JAR may not be enough: users must install Java, configure classpaths manually, create shortcuts, and figure out how to launch it. The application may also rely on native libraries, OS-specific configuration, or resources tailored to Windows, macOS, or Linux.

Java 17 provides the **jpackage** tool to create application images and native installers per target platform. This tool can bundle the application with a Java runtime so users do not need to install a separate JDK. For modular applications, **jlink** can produce a custom runtime image containing only the required modules; `jpackage` then embeds that runtime image when building the package.

A reliable release workflow requires:

1. Identifying the target OS, CPU architecture, and runtime.
2. Building artifacts with a JDK and dependencies matching that platform.
3. Creating an application image to test upfront.
4. Creating the native installer for the target platform.
5. Installing and testing on a clean machine without a development environment.
6. Testing upgrades, uninstallation, permissions, and native dependencies.

## 1. How Do Portable JARs and Platform-Specific Installers Differ?

A JAR is an archive holding classes, resources, and metadata. If an application uses only standard Java APIs and pure Java libraries, the same JAR can usually run across multiple operating systems given a compatible Java runtime.

Native installers, by contrast, are platform-dependent:

| Artifact | Purpose | Platform Dependency |
| --- | --- | --- |
| Pure Java JAR | Run with the Java launcher | Requires a compatible runtime; JAR contents are generally shared |
| Application image | Application directory with launcher and runtime | Runtime and launcher are tied to target OS/CPU |
| Windows installer | Install application on Windows | Windows-specific installation format and build tools |
| macOS package/image | Install or distribute application on macOS | macOS bundle, package, signing, and platform rules |
| Linux package | Install on matching Linux distros | Package format and target system environment |

A pure Java JAR can be portable, but that does not mean every Java application is portable. The following factors can make an application platform-dependent:

- JNI or native libraries such as DLL, dylib, or SO files.
- External programs invoked via `ProcessBuilder`.
- File paths, separators, executable permissions, and filesystem rules.
- Fonts, codecs, drivers, graphics libraries, or printing subsystems.
- OS-specific behaviors such as services, registry entries, file associations, or keychains.
- CPU architecture and native library ABI.

Therefore, distinguish **bytecode portability** from **portability of the entire deployed product**.

### 1.1. Defining the Target Platform Matrix

Before building, clearly define which combinations your product supports. For example:

| Platform | Architecture | Package to Release |
| --- | --- | --- |
| Windows 11 | x64 | MSI or EXE |
| macOS | Apple Silicon arm64 | PKG or DMG |
| Linux Ubuntu/Debian | x64 | DEB |
| Linux Fedora/RHEL | x64 | RPM |

This is only an example. A real product may support fewer or more combinations. Do not claim "supports Linux" if you have only tested on a single distro and a single architecture.

### 1.2. Java Version and Platform Are Separate Requirements

If an application is compiled for Java 17, its bytecode can run on Java 17 or compatible newer runtimes, but will not run on older runtimes if it uses unsupported bytecode or APIs.

For example:

```bash
javac --release 17 -d out src/com/example/app/Main.java
```

The `--release 17` option sets the target language level, bytecode version, and Java APIs for compilation. It does **not** convert a Windows runtime image into a Linux runtime image, nor does it bundle native libraries for every architecture.

## 2. jpackage in JDK 17

`jpackage` is a tool for packaging Java applications into application images or native installers. It became an official feature in JDK 16 and is therefore included in JDK 17.

Common package types depend on the operating system:

| Build OS | Commonly Supported Package Types |
| --- | --- |
| Windows | app-image, exe, msi |
| macOS | app-image, dmg, pkg |
| Linux | app-image, deb, rpm |

The exact list depends on the JDK build and packaging tools installed on the host. Check directly:

```bash
jpackage --version
jpackage --help
jpackage --help-extra
```

`app-image` is a packaged application directory, typically containing a launcher and runtime. Formats like `msi`, `exe`, `dmg`, `pkg`, `deb`, and `rpm` build native installers or packages.

### 2.1. Building on the Target Platform

`jpackage` builds native packages for the platform on which the tool runs. Do not treat it as a cross-compiler capable of building Windows installers on Linux or macOS installers on Windows.

A release pipeline should execute on matching runners:

```text
Windows x64 runner  ──> Windows app-image / MSI / EXE
macOS arm64 runner  ──> macOS app-image / PKG / DMG
Linux x64 runner    ──> Linux app-image / DEB / RPM
```

Runtime images are also tied to the OS and architecture of the JDK that built them. To ship for Windows, macOS, or Linux, build runtimes/packages on the corresponding platform and test on each target combination.

### 2.2. What Needs to Be Prepared?

Before running `jpackage`, prepare:

- JDK 17 matching the target platform and architecture.
- Built application JAR.
- Directory containing dependencies if external JARs are needed.
- Application name, version, vendor, and required metadata.
- Platform-appropriate icons or resources if customizing.
- System tools required by the target installer format.

Some installer formats require additional native packaging tools. For instance, creating MSI/EXE on Windows requires a compatible WiX Toolset; macOS and Linux formats likewise depend on their respective system tools. Consult `jpackage --help` and JDK 17 documentation on the build machine to confirm exact prerequisites.

## 3. Preparing Inputs for jpackage

Suppose a non-modular application has this layout:

```text
release/
├── input/
│   ├── desktop-app.jar
│   ├── logging.jar
│   └── database-driver.jar
└── output/
```

The `input` directory holds the main JAR and required dependencies. `jpackage` uses this directory as the source of application content.

If the main JAR already declares `Main-Class` in its manifest, you can specify that JAR as the entry point. Otherwise, use `--main-class` to provide the fully qualified class name.

Example entry-point class:

```java
package com.example.desktop;

public class Main {
    public static void main(String[] args) {
        System.out.println("Desktop application started");
    }
}
```

The fully qualified class name is `com.example.desktop.Main`.

## 4. Creating an Application Image Before Creating an Installer

Create an `app-image` first to verify the deployment payload:

```bash
jpackage --type app-image --name DesktopApp --app-version 1.0.0 --vendor ExampleOrg --input input --main-jar desktop-app.jar --main-class com.example.desktop.Main --dest output
```

Options:

| Option | Purpose |
| --- | --- |
| --type app-image | Builds an application image instead of an installer. |
| --name DesktopApp | Application name and image directory name. |
| --app-version 1.0.0 | Application version. |
| --vendor ExampleOrg | Vendor information. |
| --input input | Directory containing main JAR and dependencies. |
| --main-jar desktop-app.jar | Main application JAR. |
| --main-class ... | Class containing the main method. |
| --dest output | Directory for output artifacts. |

If the main JAR already defines `Main-Class` in its manifest, `--main-class` can be omitted; specifying it explicitly keeps the command self-documenting and reduces reliance on metadata generated in earlier steps.

### 4.1. Testing the Application Image

`jpackage` creates an image directory under `output`. Exact layout varies by OS; inside are typically the launcher, application directory, and runtime image.

Run the launcher generated by `jpackage`:

- On Windows, run the `.exe` launcher inside the application image.
- On macOS, open the launcher or `.app` bundle.
- On Linux, run the launcher inside the image directory.

Do not test only with `java -jar desktop-app.jar`. The goal of this step is verifying that the launcher, bundled runtime, resources, and dependencies inside the application image all work together.

### 4.2. Dependencies Must Be Inside Input

If `desktop-app.jar` depends on `logging.jar` and `database-driver.jar`, those files must exist inside the `input` directory or be supplied via another packaging configuration. `jpackage` does not parse Maven/Gradle dependency graphs to fetch external libraries.

For applications using manifest `Class-Path`, check that relative paths remain valid after packaging. For applications using custom classpaths or frameworks with special launchers, follow the artifact layout supported by that framework.

## 5. Creating OS-Native Installers

Once the application image works, build the installer on a runner for the target platform.

### 5.1. Windows: MSI or EXE

Example creating an MSI:

```powershell
jpackage --type msi --name DesktopApp --app-version 1.0.0 --vendor ExampleOrg --input input --main-jar desktop-app.jar --main-class com.example.desktop.Main --dest output --win-menu --win-shortcut
```

`--win-menu` adds a Start Menu shortcut; `--win-shortcut` requests a desktop shortcut per tool options. You can pass `--icon` to specify a Windows icon.

Create an EXE by changing the package type:

```powershell
jpackage --type exe --name DesktopApp --input input --main-jar desktop-app.jar --main-class com.example.desktop.Main --dest output
```

MSI and EXE are different installer formats. Choose the format matching your organization's deployment workflow and software management tools.

### 5.2. macOS: DMG or PKG

Example creating a DMG:

```bash
jpackage --type dmg --name DesktopApp --app-version 1.0.0 --vendor ExampleOrg --input input --main-jar desktop-app.jar --main-class com.example.desktop.Main --dest output
```

You can also create a PKG:

```bash
jpackage --type pkg --name DesktopApp --input input --main-jar desktop-app.jar --main-class com.example.desktop.Main --dest output
```

DMG is commonly used as an application distribution disk image; PKG is an installer package. Distribution outside development environments must account for signing, notarization, and Apple's current Gatekeeper policies.

### 5.3. Linux: DEB or RPM

Example creating a DEB:

```bash
jpackage --type deb --name desktop-app --app-version 1.0.0 --vendor ExampleOrg --input input --main-jar desktop-app.jar --main-class com.example.desktop.Main --dest output
```

Example creating an RPM:

```bash
jpackage --type rpm --name desktop-app --input input --main-jar desktop-app.jar --main-class com.example.desktop.Main --dest output
```

DEB and RPM target different distro families. A DEB built on one Linux release is not automatically guaranteed to run on every Debian/Ubuntu version; define a baseline and verify the system libraries required by the application or native dependencies.

### 5.4. Package Names and Application Names

Some operating systems distinguish display names from package names. For example, Linux package names typically follow distro package-naming rules; macOS has its own bundle identifier. Use the platform-specific options in `jpackage --help` when declaring these fields.

Do not use a name containing invalid characters across every OS assuming installers will normalize it identically.

## 6. Creating a Minimal Runtime Image with jlink

Normally `jpackage` can generate a runtime image for your application. If you want finer control over runtime modules, build one beforehand with `jlink` and pass it to `jpackage` via `--runtime-image`.

`jlink` assembles modules and their module dependencies into a runtime image. It fits modular applications best, where module descriptors declare dependencies with `requires`.

Example application module:

```java
module com.example.desktop {
    requires java.desktop;
}
```

Compile the module into `mods`:

```bash
javac -d mods --module-source-path src -m com.example.desktop
```

Create the runtime image:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.desktop --output runtime-image --strip-debug --no-header-files --no-man-pages
```

In this example, `--add-modules` selects the root module; required module dependencies are pulled into the graph along module edges. `--strip-debug`, `--no-header-files`, and `--no-man-pages` reduce image size if your application does not need those components.

Adjust the module path separator for your OS and shell. On Windows, the module path separator is a semicolon; on Linux/macOS, it is a colon.

### 6.1. Packaging with a Prebuilt Runtime Image

Once you have a runtime image for the target platform:

```bash
jpackage --type app-image --name DesktopApp --input input --main-jar desktop-app.jar --main-class com.example.desktop.Main --runtime-image runtime-image --dest output
```

`--runtime-image` specifies the runtime image to embed in the application. The image must match the target OS/architecture and be compatible with the application.

### 6.2. Why Must Runtime Modules Be Verified?

If the runtime image lacks a module required by the application or a dependency, the application can fail at startup or when entering a specific feature.

For modular applications, verify the module graph using JDK tools and test real business flows. Do not open only the main window and assume the runtime image has every module; infrequently used features like printing, TLS, logging, XML, or desktop integration may only trigger later.

Classpath applications without module descriptors require extra care when determining runtime modules. You can use `jdeps` for static analysis, then supplement with dynamically loaded modules, reflection, service loaders, and native integrations that static analysis may miss.

## 7. Native Dependencies and CPU Architecture

If an application uses JNI or native libraries, every binary must be compatible with:

- Target operating system.
- CPU architecture (`x64`, `arm64`, etc.).
- Required system ABI and runtime versions.
- Version of the native library linked by the application.

For example:

```text
native/
├── windows-x64/
│   └── engine.dll
├── macos-arm64/
│   └── libengine.dylib
└── linux-x64/
    └── libengine.so
```

You cannot pack a DLL into a macOS package and expect the JVM to translate it into a dylib. Build or obtain the proper native binary for each platform and place it where the application can load it.

### 7.1. Checking Native Library Loading

When using `System.loadLibrary`, check:

- Library naming per JVM/OS conventions.
- `java.library.path` or how the application resolves library paths.
- Appropriate read and execute permissions.
- Binary architecture matching the JVM process architecture.
- Dependent native libraries already present on the target machine.

`UnsatisfiedLinkError` typically indicates a missing library, incompatible architecture, or missing native dependency.

### 7.2. Do Not Mix x64 and arm64 Artifacts

An x64 runtime image does not become arm64 merely by copying it to an ARM machine. If you support both architectures, build the runtime image and matching native payloads on appropriate runners, then test each package on compatible hardware or virtualization.

### 7.3. Linux and System Library Baselines

Linux native binaries can depend on specific `glibc` or system library versions. A package built on a newer distro may fail on an older distro if it relies on newer symbols or ABIs.

Choose a baseline distro/build image according to your product support policy. Inspect native dependencies with platform tools and test on a clean baseline distro, not only on the build machine.

## 8. What Does Testing on a Clean Machine Mean?

A clean machine is an isolated test environment that does not inherit leftovers accidentally present on a developer workstation. Examples include:

- A freshly installed virtual machine running the target OS.
- A freshly provisioned physical machine/runner from a standard image.
- A clean container for Linux checks that do not require a desktop installer.

For native installers, a VM running the target OS is usually preferable to a container because you can test the installer UI, shortcuts, user permissions, registry, services, desktop integration, and uninstallation.

### 8.1. What Should Not Exist on a Clean Machine

To verify the product is truly self-contained as designed, the environment should lack:

- Pre-installed JDK or JRE if the package claims to bundle its own runtime.
- Pre-configured `CLASSPATH` or `JAVA_HOME`.
- Dependency JARs outside the install folder that the app might accidentally pick up.
- Native libraries present only on developer workstations.
- Config files, caches, or sample data copied manually from the build machine.
- Administrator/root privileges when the app is meant to run as a normal user.

If the product intentionally requires users to install Java separately, document the minimum runtime version and test under that exact condition. Do not call it a runtime-bundled package.

### 8.2. Which Bugs Do Clean Machines Catch?

A developer workstation usually has extra tools and supporting libraries already installed. A clean machine catches:

- Missing dependency JARs or resources.
- Launchers depending on `PATH`, `JAVA_HOME`, or working directory.
- Missing runtime modules in the image.
- Incorrect file permissions or install locations.
- Paths containing spaces or Unicode characters.
- Native libraries with the wrong OS/architecture.
- Installers failing to create shortcuts or uninstall cleanly.
- Applications attempting to write data into a read-only install directory.
- TLS, proxy, font, locale, or timezone differences from dev machines.

## 9. Workflow for Testing Installers on a Clean Machine

Use reproducible VM snapshots or base images so every test run starts from a known state.

### Step 1 — Record Environment Information

Record:

- Exact OS and version.
- CPU architecture.
- Account used to install and account used to run the app.
- Whether any Java runtime is pre-installed.
- System language, locale, and timezone.
- Disk space and access permissions.

This helps reproduce bugs and document support scope.

### Step 2 — Install the Exact Release Artifact

Copy the exact installer generated by the pipeline. Never copy `build/classes`, extra JARs, or config files from a dev machine onto the test machine unless they belong to the release package.

Perform installation following end-user instructions. If the installer requires administrator/root rights, verify that requirement and then test running the installed application under a standard user account.

### Step 3 — Verify the Bundled Runtime

If the package claims to include a runtime, test on a machine with no Java installed:

- Do not set `JAVA_HOME`.
- Do not add Java to `PATH`.
- Run the installed launcher.
- Confirm the application starts and verify the reported runtime/version appropriately.

If distributing only a JAR, install the supported Java runtime and run `java -jar`. Both deployment models should be clearly documented for users.

### Step 4 — Test Core User Flows

Do not check only the splash screen or startup message. Exercise key workflows:

- Reading and writing data.
- Loading and updating configuration.
- Connecting to external services or databases if applicable.
- Handling input and output files.
- Writing logs and reporting errors.
- Features relying on native libraries or optional modules.

### Step 5 — Test Paths and Permissions

Test installing into paths containing spaces and Unicode characters if allowed by the OS. Verify:

- The app launches from shortcuts as well as the direct executable.
- It does not depend on the current working directory.
- User data is written to an appropriate user data directory.
- The app does not attempt to write into the install folder when running without admin privileges.
- File and directory paths are handled via cross-platform APIs.

### Step 6 — Test Upgrade and Uninstallation

Exercise these cases:

1. Install the initial version.
2. Launch it and generate user data.
3. Install the upgrade package following the intended procedure.
4. Verify preserved user data and configuration.
5. Uninstall the application.
6. Confirm program files are removed and user data is kept or deleted per policy.
7. Reinstall to confirm a clean state.

Data retention during uninstallation must be designed intentionally. Do not accidentally wipe user data or leave stale runtimes/binaries behind without user awareness.

## 10. Platform-Specific Testing

### 10.1. Windows

Verify:

- Installing MSI/EXE as a standard user or administrator as designed.
- Start Menu and desktop shortcuts.
- Install paths containing spaces.
- Write permissions in the user data folder.
- Windows Defender/SmartScreen behavior and installer signatures.
- Uninstalling via Settings/Apps or standard software management tools.
- Upgrading from the previous version and shortcut behavior.

If the application uses the Windows registry, services, or file associations, verify permissions and behavior across install, upgrade, and uninstall.

### 10.2. macOS

Verify:

- Installing/opening the app from DMG or PKG.
- App bundle containing the proper launcher and runtime.
- Permissions for accessing user folders, Documents, Downloads, and needed locations.
- Gatekeeper, quarantine attributes, and release signing/notarization flow.
- Running on all Intel/Apple Silicon architectures claimed as supported.
- App removal and handling of user data.

A package that runs on the build machine may still be blocked by OS security on user machines if signing and distribution steps are incomplete.

### 10.3. Linux

Verify:

- Installing DEB or RPM on supported distributions.
- Executable permissions on the launcher.
- Desktop entry/shortcut if it is a desktop application.
- Native libraries and system package dependencies.
- Standard user permissions when writing logs, caches, and configs.
- Removing the package via the package manager.
- Running on a clean distro at the baseline system library level.

Do not test solely on the exact distro where the package was built. If multiple distros are supported, test each package family and announced baseline.

## 11. Verifying Artifacts and Integrity

Before releasing, record metadata:

- Artifact name and package type.
- Application version.
- Target OS/architecture.
- JDK and build tool versions.
- Source commit or build ID.
- Dependency list and versions.
- SHA-256 checksum.
- Digital signature status if signed.

Generate checksums with standard OS tools, for example:

```bash
sha256sum DesktopApp-1.0.0.deb
```

On Windows PowerShell:

```powershell
Get-FileHash .\DesktopApp-1.0.0.msi -Algorithm SHA256
```

Checksums detect file modification during storage or transfer. They do not replace digital signatures for authenticating the publisher.

### 11.1. Signing and Distribution

For applications distributed externally:

- Windows typically signs installers and executables with an organization code-signing certificate.
- macOS requires signing and notarization per Apple's current distribution rules.
- Linux can distribute via signed repositories/packages following distro or organizational practices.

Signing must use securely managed keys. Never place private keys or signing passwords in source repositories or bundle them inside an application image.

### 11.2. Checking Versions and Metadata

Ensure versions inside installers, artifact filenames, manifests, and release pages match. Operators should be able to identify which build is installed and which source revision produced it.

## 12. Automating Per-Platform Builds in CI

For multiple platforms, use a build matrix so each runner builds artifacts for its own OS:

```text
CI matrix:
  windows runner:
    setup JDK 17
    build application
    jpackage --type msi
    test installer on clean Windows VM

  macOS runner:
    setup JDK 17 for target architecture
    build application
    jpackage --type dmg
    sign and notarize
    test on clean macOS VM

  Linux runner:
    setup JDK 17
    build application
    jpackage --type deb or rpm
    test on clean target distro
```

This is a structural outline. In real projects, build commands and input paths must match repository scripts; macOS runners may need explicit architecture selection; Windows runners may need WiX installed; signing/notarization steps must also follow release policy.

### 12.1. Build Once, Package Many Times?

Pure Java bytecode can be shared across platforms if it contains no OS-specific components. However, application images, runtime images, and native installers must be built for each target platform.

A pipeline can:

1. Build portable JARs once from source.
2. Distribute those JARs to target runners.
3. On each runner, supply the matching native dependencies and runtime.
4. Run `jpackage` on that runner.
5. Install and test the artifact on a clean machine of the same platform.

If building the JAR generates OS-specific resources or code, split that build step per platform instead of sharing a single artifact.

### 12.2. Keeping Builds Reproducible

To investigate release incidents, retain:

- JDK and build tool versions.
- `jpackage`/`jlink` arguments.
- Input JARs and dependencies.
- Selected runtime modules.
- Runner OS image and architecture.
- Output checksums.
- Clean-machine test results.

Do not save only the final installer while discarding details of the runtime image and inputs used to build it.

## 13. Common Errors and How to Fix Them

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `jpackage` cannot build requested installer type | Running on an OS that doesn't support that package type or missing native tools. | Build on a runner of the target OS and install tools required by `jpackage --help`. |
| App image works on build machine but fails on clean machine | Build machine had Java, native libraries, or configs outside the package. | Test on a clean VM; confirm runtime and dependencies are bundled. |
| `ClassNotFoundException` at launch | Missing dependency JAR or wrong main/classpath setup. | Check `--input`, main JAR, and dependency packaging. |
| `UnsatisfiedLinkError` | Missing native library, wrong architecture, or missing system dependency. | Supply binary for target OS/CPU and inspect ABI/dependencies. |
| Runtime image missing module | `jlink` omitted needed module or dynamically loaded dependency. | Analyze module graph, add needed modules, and test all features. |
| Linux package works on build distro but fails on another distro | Different `glibc` or system library baseline. | Document supported distros and test on clean baseline images. |
| Shortcut launches app but config file is not found | Code relies on current working directory. | Use bundled resource locations or explicit config data directories. |
| Install requires elevation and normal user cannot write | App writes data inside protected install directory. | Move mutable data to user/app data directories. |
| macOS package blocked by Gatekeeper | Signing/notarization or quarantine not handled properly. | Complete release signing/notarization per Apple's current requirements. |
| Upgrade erases configuration | Installer or app overwrites/deletes user data. | Separate user data from install directory and test upgrade/uninstall. |
| Artifact has wrong architecture for target machine | Runtime/native library built for a different CPU. | Build runtime images and dependencies for the exact target architecture. |

## 14. Clean-Machine Testing Checklist

Before releasing each package, verify these items:

- [ ] Correct supported OS, version, and CPU architecture.
- [ ] Installer built on a runner matching the target platform.
- [ ] Test machine has no JDK/JRE pre-installed if the package bundles a runtime.
- [ ] Installation succeeds following end-user instructions.
- [ ] Launcher starts cleanly after installation.
- [ ] Both Java and native dependencies are present.
- [ ] Core features work, including rarely used paths.
- [ ] Paths containing spaces/Unicode characters work properly.
- [ ] Application runs under a standard user account.
- [ ] Configs, caches, logs, and data are written to the right locations.
- [ ] Upgrades preserve expected user data.
- [ ] Uninstallation cleanly handles program files and user data.
- [ ] Signatures, checksums, and release metadata are verified.
- [ ] Test results, environment details, and artifact checksums are archived.

## 15. Practice Exercises

### Exercise 1 — Create an App Image

Create a Java 17 app with `Main-Class`, prepare an `input` directory with the main JAR and dependencies, and run `jpackage --type app-image`. Inspect the image folder and identify the launcher, runtime, and app content.

### Exercise 2 — Create an Installer on the Target Platform

On Windows, build an MSI; on macOS, build a DMG or PKG; on Linux, build a DEB or RPM. Record the build OS and required system tools.

### Exercise 3 — Compare a JAR and a Runtime-Bundled Package

Run the JAR on a machine with Java 17. Then run the app image on a VM with no Java installed. Document differences in runtime prerequisites and distribution structure.

### Exercise 4 — Create a Runtime Image with jlink

For a modular application, identify root modules and build a runtime image. Remove a required module to observe the failure; restore the module and test features relying on it.

### Exercise 5 — Test Native Dependencies

Integrate a native library matching your test environment. Build a package for one architecture, then verify why that binary cannot be used directly on another architecture.

### Exercise 6 — Test on a Clean Machine

Provision a fresh VM without Java, install the runtime-bundled package, exercise main flows, upgrade, and uninstall. Record OS version, architecture, artifact checksums, and test outcomes.

## 16. Official Java 17 Documentation

- [Java SE 17 jpackage tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html): building application images and platform installers; options for input, main class, runtime image, and package type.
- [Java SE 17 jlink tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html): creating custom runtime images from the module graph.
- [Java SE 17 jar tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): creating and inspecting JARs, manifests, and module metadata.
- [Java SE 17 jdeps tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): static dependency analysis for applications and libraries.
- [Java SE 17 Launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): options for running applications, classpaths, and module paths.

A pure Java JAR can often be shared across multiple operating systems, whereas application images, runtime images, and native installers must match the target OS and CPU architecture. In Java 17, use `jpackage` to create packages and `jlink` when you need a custom runtime image. Build on matching runners, verify the application image first, and then install the package on a clean machine free of development-environment leftovers. Testing must cover dependencies, native libraries, permissions, upgrades, and uninstallation—only that proves the artifact is ready for real user environments.
