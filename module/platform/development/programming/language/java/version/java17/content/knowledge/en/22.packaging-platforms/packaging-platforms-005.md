# Creating App Images and Installers with jpackage in Java 17

When developing a Java application, giving users a JAR file is often not enough. Users may not have Java installed, may not know which command to run, or may lack a standard operating-system way to install and uninstall the application. The **jpackage** tool in the JDK solves this packaging step: it builds an application image with a bundled launcher and runtime, or creates a native installer suited to the operating system.

In Java 17, `jpackage` is an official tool included in the JDK. It can package either classpath-based or modular applications, generate a runtime image via `jlink`, or accept a prebuilt runtime image. From the app-image, development teams can test the standalone application before producing an installer.

This lesson explains the difference between an app-image and an installer, how to package classpath and modular applications, how to customize the runtime and launcher, OS-specific installer formats, metadata, signing, and release testing workflows.

## 1. What Is jpackage?

**jpackage** is a tool for packaging a Java application into a distributable bundle for end users. It produces:

- **Application image (app-image):** an application directory containing a native launcher, the application payload, and the required Java runtime.
- **Native installer/package:** an installer in the operating system's native format, such as MSI/EXE on Windows, DMG/PKG on macOS, or DEB/RPM on Linux.

An application packaged this way runs using the bundled runtime. End users do not need to install a separate JDK to run the application, provided the runtime image includes all Java modules the application requires.

### 1.1. How Are an App-Image and an Installer Different?

| Criterion | App-image | Native installer |
| --- | --- | --- |
| Output | Packaged application directory | Platform-specific installer file |
| Usage | Run the launcher inside the directory | Open/run the installer to install the application |
| Runtime | Can contain a private runtime | Typically installs the app-image and runtime into an install location |
| Install/uninstall | Deployers distribute and remove the directory manually | Integrates with the platform's install/uninstall mechanisms |
| Shortcuts/menus | Can create a launcher, but does not provide an OS install experience like an installer | Supports options for platform shortcuts/menus |
| Best suited for | Testing, OS-specific portable distribution, or input for building an installer | End-user distribution following OS conventions |

An app-image is neither a JAR file nor a universal cross-OS package. It contains a launcher and runtime tailored to the platform and architecture it was built on. If you want to ship for Windows, macOS, and Linux, you must build corresponding artifacts on the appropriate build environments.

## 2. Checking jpackage in JDK 17

`jpackage` resides in the JDK's `bin` directory:

~~~bash
jpackage --version
jpackage --help
~~~

If the shell cannot find the command, check `JAVA_HOME` and `PATH`:

~~~bash
java --version
javac --version
where jpackage
~~~

On Linux/macOS, use `which jpackage` or `command -v jpackage`.

Use `jpackage` from the exact JDK 17 chosen by the team to build and verify the product. The packaging tool and bundled runtime should have explicitly managed versions in the release pipeline.

## 3. Preparing the Application Before Packaging

Before invoking `jpackage`, you need successfully built application artifacts. There are two common input styles:

1. Classpath application: a main JAR, optionally accompanied by dependency JARs.
2. Modular application: a main module and dependent modules on the module path.

Determine:

- the launcher name and display name of the application;
- the main class or module entry point;
- the dependent libraries;
- the Java modules the application needs, such as `java.sql` or `java.desktop`;
- configuration files, resources, and default data to package;
- version, vendor, icon, and metadata;
- target operating system and CPU architecture.

Never place passwords, API keys, private keys, tokens, or customer data into the input directory. Every file in the payload can be extracted from an app-image or installer.

## 4. Packaging a Classpath Application as an App-Image

Suppose the application is built as follows:

~~~text
build/
└── package-input/
    ├── acme-desk.jar
    ├── library-a.jar
    └── library-b.jar
~~~

The application's main class is `com.acme.desktop.Main`. Create the app-image:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input build/package-input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --app-version 1.2.0 \
    --vendor "Acme Software" \
    --description "Task management application" \
    --dest build/dist
~~~

Explanation:

- `--type app-image`: requests creation of an application directory.
- `--name`: application name and primary artifact name.
- `--input`: directory containing the main JAR and other input files.
- `--main-jar`: entry-point JAR, relative to the input directory.
- `--main-class`: class containing the `main` method.
- `--app-version`, `--vendor`, `--description`: application metadata.
- `--dest`: destination directory for the output.

Upon success, the destination directory contains an application image named `AcmeDesk` (internal layout varies by OS). The image directory typically contains the launcher, the payload inside an `app` folder, and the runtime.

### 4.1. Dependencies of a Classpath Application

`jpackage` does not resolve dependencies like a dependency manager. Required JARs must be placed in the input directory or packaged so the application can locate them.

If the main JAR uses a manifest `Class-Path`, verify that relative paths to dependencies remain valid after `jpackage` copies the payload. For applications using frameworks or custom class loaders, verify how the framework resolves resources and libraries in the installed layout.

### 4.2. Testing the App-Image

The launcher path varies by platform:

~~~text
Windows: build/dist/AcmeDesk/AcmeDesk.exe
Linux:   build/dist/AcmeDesk/bin/AcmeDesk
macOS:   build/dist/AcmeDesk.app/Contents/MacOS/AcmeDesk
~~~

The paths above illustrate common layouts. Launch the executable directly from the generated app-image and verify that:

- the application starts without a separately installed JDK;
- resources and dependencies are found;
- configuration files are read from the expected locations;
- the application can write data to permitted user directories;
- the launcher works when invoked from a different working directory.

## 5. Packaging a Modular Application

For modular applications, the module descriptor declares the main module and its dependencies:

~~~java
module com.acme.desktop {
    requires java.desktop;
    requires com.acme.services;
}
~~~

Suppose the modules are compiled or packaged under `build/mods`:

~~~text
build/mods/
├── com.acme.desktop/
├── com.acme.services/
└── com.acme.common/
~~~

Create the app-image:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --module-path build/mods \
    --module com.acme.desktop/com.acme.desktop.Main \
    --app-version 1.2.0 \
    --vendor "Acme Software" \
    --dest build/dist
~~~

`--module-path` specifies where to locate modules. `--module` takes the form `module-name[/main-class]`; the main class portion can be omitted if the module descriptor declares a main class. The main module and all required modules must exist on the module path.

For modular applications, `jpackage` uses module metadata to build the launcher and runtime image. If modules are loaded dynamically, via reflection, service loading, or dependencies not fully captured by the module graph, verify the runtime image and add required modules in your configuration.

## 6. Runtime Images and jlink

A key benefit of `jpackage` is bundling the runtime with the application. If no prebuilt runtime image is supplied, `jpackage` invokes `jlink` to generate one. End users can then run the application without installing a separate JDK.

The runtime image contains only the execution environment, not the full JDK with its compiler, debugger, and development tools.

### 6.1. Customizing Modules in the Runtime Image

You can specify extra modules with `--add-modules` and module paths with `--module-path` when `jpackage` builds the runtime. For example:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input build/package-input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --add-modules java.desktop,java.logging,java.sql \
    --dest build/dist
~~~

The example above illustrates adding JDK modules needed by the application. The exact list must reflect actual dependencies; adding too many modules bloats the runtime image, while omitting needed modules can cause runtime failures.

`--add-modules` does not replace putting application dependency JARs into the payload. It only controls which Java modules are included in the runtime image.

### 6.2. Building a Separate Runtime Image with jlink

If you want finer control over the runtime, you can run `jlink` beforehand:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:build/mods" \
    --add-modules com.acme.desktop \
    --strip-debug \
    --no-header-files \
    --no-man-pages \
    --output build/runtime
~~~

On Windows, the module path uses `;` instead of `:`. All module dependencies of `com.acme.desktop` must exist on the module path and resolve cleanly. For classpath applications, determine the required JDK modules and pass them explicitly; `jlink` cannot infer every dependency loaded dynamically via reflection.

Pass the prebuilt runtime image into `jpackage`:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input build/package-input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --runtime-image build/runtime \
    --dest build/dist
~~~

When `--runtime-image` is supplied, `jpackage` uses the existing runtime instead of invoking `jlink`. Choose one consistent runtime management approach; check JDK 17 documentation when combining with other runtime configuration options.

### 6.3. Optimizing Runtime Size

Common `jlink` options:

| Option | Effect |
| --- | --- |
| `--strip-debug` | Removes debug information from the runtime image. |
| `--no-header-files` | Excludes native header files from the runtime image. |
| `--no-man-pages` | Excludes man pages from the runtime image. |
| `--compress` | Compresses resources inside the runtime image at a JDK-supported level. |
| `--add-modules` | Selects modules to include in the runtime image. |
| `--bind-services` | Adds service provider modules referenced in the module graph per `jlink` rules. |

`jpackage` provides `--jlink-options` to pass appropriate options to `jlink` when it creates the runtime image. For example:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --module-path build/mods \
    --module com.acme.desktop/com.acme.desktop.Main \
    --jlink-options "--strip-debug --no-header-files --no-man-pages" \
    --dest build/dist
~~~

Measure size and test the runtime after stripping or compressing. Never drop modules based purely on size if the application requires them via reflection, service loading, or plugins.

## 7. Creating Native Installers

Once the app-image runs properly, you can build an installer by switching `--type` to a platform format:

| Build OS | Commonly Supported Formats in JDK 17 |
| --- | --- |
| Windows | `exe`, `msi` |
| macOS | `dmg`, `pkg` |
| Linux | `deb`, `rpm` |
| All platforms above | `app-image` |

Available native formats depend on the host platform and installed packaging tools. `jpackage` does not build a Windows installer on Linux or a macOS package on Windows.

### 7.1. Windows Installers

Create an MSI:

~~~powershell
jpackage --type msi --name AcmeDesk --input build/package-input --main-jar acme-desk.jar --main-class com.acme.desktop.Main --app-version 1.2.0 --vendor "Acme Software" --win-menu --win-shortcut --win-dir-chooser --dest build\installer
~~~

Common Windows options:

- `--win-menu`: adds a Start Menu entry.
- `--win-shortcut`: creates a desktop shortcut.
- `--win-dir-chooser`: allows the user to choose the installation directory.
- `--win-per-user-install`: configures a per-user installation where supported.
- `--win-upgrade-uuid`: MSI upgrade identifier; must remain stable across releases of the same product.
- `--win-console`: keeps a console window for console applications when appropriate.

On Windows, `jpackage` requires the corresponding packaging toolchain; JDK 17 requires WiX Toolset version 3.0 or later to generate EXE/MSI formats. Install and configure the tool according to your target JDK documentation before running the pipeline.

### 7.2. macOS Installers

Create a DMG:

~~~bash
jpackage \
    --type dmg \
    --name AcmeDesk \
    --input build/package-input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --app-version 1.2.0 \
    --vendor "Acme Software" \
    --mac-package-identifier com.acme.desktop \
    --dest build/installer
~~~

Some macOS options:

- `--mac-package-identifier`: stable bundle/package identifier, usually reverse-DNS.
- `--mac-package-name`: displayed package name.
- `--mac-app-category`: application category.
- `--mac-dmg-content`: additional content displayed in the DMG.
- `--mac-sign`: requests signing of the app/package in supported workflows.
- `--mac-signing-key-user-name` and `--mac-signing-keychain`: selects identity/keychain for signing.
- `--mac-entitlements`: entitlements file used during signing when needed.

For external distribution, check Apple's current code signing and notarization requirements. Successfully generating a DMG/PKG does not automatically mean the app is signed, notarized, and ready to pass security checks on user machines.

### 7.3. Linux Packages

Create a DEB:

~~~bash
jpackage \
    --type deb \
    --name acme-desk \
    --input build/package-input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --app-version 1.2.0 \
    --linux-package-name acme-desk \
    --linux-deb-maintainer "release@example.invalid" \
    --linux-shortcut \
    --dest build/installer
~~~

The maintainer address in the example is a placeholder; replace it with your organization's real contact information. Do not ship fake addresses in real packages.

Common Linux options:

- `--linux-package-name`: package name.
- `--linux-deb-maintainer`: maintainer information for DEB.
- `--linux-menu-group`: menu group.
- `--linux-package-deps`: OS package dependencies to declare.
- `--linux-rpm-license-type`: license type for RPM metadata.
- `--linux-app-release`: package release number.
- `--linux-app-category`: application category.
- `--linux-shortcut`: creates a desktop shortcut where supported by the platform.

DEB requires Debian packaging tools such as `dpkg-deb`; RPM requires corresponding tools such as `rpmbuild`. Verify tools and versions on the build host against JDK 17 and target OS documentation.

## 8. Building an Installer from a Tested App-Image

Splitting the workflow into two stages is useful when you want to test the app-image first before producing an installer. `jpackage` supports `--app-image` to use an existing application image as input:

~~~bash
jpackage --type msi --name AcmeDesk --app-image build/dist/AcmeDesk --dest build/installer
~~~

This example is for a Windows host that already has a Windows app-image built and verified in a compatible environment. On macOS or Linux, use the package type and app-image matching that platform.

Benefits of this workflow:

1. Build the app-image once for the target platform.
2. Run the launcher and verify the runtime/dependencies.
3. Once verified, build the installer from the app-image.
4. Install the installer on a clean test machine.

The app-image and installer must match in platform, architecture, and runtime assumptions. Do not use a Linux app-image as input to build a Windows MSI.

## 9. Customizing Launchers, Icons, and Resources

### 9.1. Icons and Metadata

You can supply an icon with `--icon`:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input build/package-input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --icon src/packaging/acme-desk.png \
    --app-version 1.2.0 \
    --vendor "Acme Software" \
    --copyright "Copyright 2026 Acme Software" \
    --dest build/dist
~~~

Supported icon formats depend on the platform and package type. For example, Windows typically uses ICO, macOS uses ICNS, and Linux typically uses PNG. Use the format and dimensions required by the JDK and target platform.

Metadata can include:

- `--app-version`;
- `--vendor`;
- `--description`;
- `--copyright`;
- `--about-url`;
- `--license-file`.

Metadata should remain consistent with the application's release details, license, and branding.

### 9.2. Adding Configuration Files or Bundled Content

`--input` places input files into the application payload. `--app-content` allows adding extra application content as supported by `jpackage`. `--resource-dir` lets you supply custom packaging resources, such as platform-specific installer templates or icons.

Example:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input build/package-input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --app-content build/default-config \
    --resource-dir src/packaging/resources \
    --dest build/dist
~~~

Only include default non-secret configuration files and resources in the package. Environment-specific configs, credentials, and secrets should be supplied via secure post-install configuration mechanisms.

### 9.3. Creating Additional Launchers with --add-launcher

An application may provide multiple launchers, such as a primary launcher and an admin tool. Create a properties file:

**admin.properties**

~~~properties
main-class=com.acme.desktop.AdminMain
arguments=--mode,admin
java-options=-Xmx1g
~~~

Invoke `jpackage`:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input build/package-input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --add-launcher admin=src/packaging/admin.properties \
    --dest build/dist
~~~

Additional launchers can inherit certain properties from the main launcher and override properties declared in the properties file. Check JDK 17 documentation for supported properties and exact inheritance rules.

## 10. Passing Arguments and JVM Options

`--arguments` sets default arguments passed to the application. `--java-options` sets flags for the JVM running the application:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input build/package-input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --arguments "--profile,desktop" \
    --java-options "-Dfile.encoding=UTF-8" \
    --java-options "-Xms256m" \
    --java-options "-Xmx2g" \
    --dest build/dist
~~~

Distinguish:

- `--arguments`: application arguments received in `main(String[] args)`.
- `--java-options`: JVM flags such as system properties, heap sizes, or module options.

Do not place secrets in `--arguments` or `--java-options`: those values can appear in launcher config files or system process listings. For secrets, use a secret manager or secure runtime credential provisioning.

## 11. Platform Configuration and Build Requirements

`jpackage` creates native packages for the OS it runs on. Cross-platform release pipelines usually require dedicated build workers:

| Artifact | Build Environment | Required Checks |
| --- | --- | --- |
| Windows EXE/MSI | Windows | JDK 17, compatible WiX Toolset, signing tool if signing |
| macOS DMG/PKG | macOS | JDK 17, required Apple tools, signing identity and notarization workflow for distribution |
| Linux DEB | Appropriate Linux | JDK 17 and DEB packaging tools |
| Linux RPM | Appropriate Linux | JDK 17 and RPM packaging tools |
| App-image | Target OS/architecture | JDK 17 and matching runtime; app-image remains platform-specific |

Do not assume an artifact built on one OS works as an installer on another OS. Build artifacts on runners/VMs matching the target OS and architecture.

## 12. Code Signing and Release Integrity

Native installers may require digital signatures so the operating system can verify the publisher and integrity:

- Windows: sign executables and installers using Windows ecosystem code-signing tools, then verify signatures.
- macOS: sign apps/packages with an appropriate identity; for distribution outside the App Store, complete Apple's notarization workflow.
- Linux: sign repository metadata or packages according to your organization's and repository's distribution model.

`jpackage` provides several signing options for macOS; do not assume a single `jpackage` command handles every signing, timestamping, notarization, or distribution step. Store certificates/private keys in your CI secret store, restrict access, and never place private keys inside the app-image.

After signing:

1. Verify the signature on the final artifact.
2. Compute checksums and store them alongside release metadata.
3. Confirm the signed artifact is the exact one tested.
4. Retain build logs and provenance per release policy.

## 13. Versioning, Upgrades, and Uninstallation

`--app-version` sets the application version inside the package. On Windows MSI, `--win-upgrade-uuid` is the product's upgrade identifier and must remain stable across upgrades of the same product. On macOS, the bundle/package identifier must also stay consistent.

Do not confuse `jpackage` with an auto-update system. `jpackage` builds app-images and installers; checking for new versions, downloading updates, verifying them, silent installation, or rollback must be designed with a separate update/distribution mechanism or rely on the platform's package manager.

When planning upgrades, decide:

- whether the new installer upgrades the existing version or installs side-by-side;
- where user data is stored;
- whether config files are preserved across upgrades;
- whether data schemas require migration;
- whether uninstall removes or preserves user data;
- how rollback works if the new version fails to start.

Never store long-lived user data inside the application installation directory if the installer may replace or delete that directory. Use OS-appropriate user data locations.

## 14. Testing the App-Image and Installer

A `jpackage` command completing without errors only proves the tool produced an artifact. It does not prove the application runs properly on user machines.

A testing workflow should cover:

1. **Test the app-image:** run the launcher and confirm the application starts.
2. **Clean machine:** test on a machine/VM with no separate JDK installed to confirm the bundled runtime is sufficient.
3. **Dependencies:** verify all libraries, native libraries, resources, and service providers.
4. **Working directory:** launch via shortcut or from a path different from the install directory.
5. **Write permissions:** confirm the app writes logs, cache, and user data to writable locations.
6. **Installation:** install the package on supported OS versions.
7. **Upgrade:** upgrade from the previous version and verify user data.
8. **Uninstallation:** confirm program files are removed and user data is handled per policy.
9. **Signing:** verify signatures and OS trust prompts.
10. **Architecture:** test on x64/ARM64 or every announced architecture.

### 14.1. Testing the Launcher on a Machine Without a JDK

If the application works only on a developer machine that already has a JDK installed, the app-image may be missing runtime modules or the app may inadvertently be picking up Java from `PATH`. Test in a clean environment and confirm the launcher uses the runtime inside the image.

### 14.2. Checking for Missing Runtime Modules

Common symptoms when a runtime image is over-minimized:

- `ClassNotFoundException` or `NoClassDefFoundError` when loading classes;
- missing service provider errors;
- Java Desktop/AWT/Swing errors when `java.desktop` is missing;
- JDBC driver or related API failures when required modules are absent.

Inspect module dependencies, `--add-modules`, service binding, and dynamically loaded classes. If needed, test with a broader runtime to isolate the cause, then narrow down with controlled testing.

## 15. Complete Release Workflow Example

Suppose a classpath application has this layout:

~~~text
build/
├── libs/
│   ├── acme-desk.jar
│   ├── library-a.jar
│   └── library-b.jar
└── package/
    └── resources/
~~~

### Step 1: Create the App-Image

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input build/libs \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --app-version 1.2.0 \
    --vendor "Acme Software" \
    --description "Acme desktop application" \
    --icon packaging/acme-desk.png \
    --dest build/dist
~~~

### Step 2: Run and Verify the App-Image

Launch the OS-specific executable, test logging into a staging/test environment, read/write data, and confirm dependencies work. Never use production accounts or real customer data in packaging smoke tests.

### Step 3: Build the Installer on the Matching Runner

Windows example:

~~~powershell
jpackage --type msi --name AcmeDesk --app-image build\dist\AcmeDesk --app-version 1.2.0 --win-menu --win-shortcut --dest build\installer
~~~

On macOS/Linux, build DMG/PKG or DEB/RPM from the same-platform app-image on the corresponding runner.

### Step 4: Sign and Verify

Perform platform signing, then verify signatures, checksums, and metadata. Retrieve certificates/private keys from the pipeline's secret management system.

### Step 5: Test on a Clean Machine

Install the package, run the application, upgrade from the previous version, and uninstall. Once all checks pass, store the artifacts and release metadata in a distribution repository with appropriate access controls and retention.

## 16. Common Errors and How to Fix Them

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `jpackage` not found | Using a JRE or `PATH` pointing to another JDK. | Use `jpackage` from JDK 17's `bin` directory and verify `JAVA_HOME`. |
| Cannot create EXE/MSI on Windows | Missing or incompatible WiX Toolset version. | Install WiX compatible with JDK 17 and configure `PATH` per documentation. |
| Cannot create DEB/RPM | Missing Linux native packaging tools. | Install required tools such as `dpkg-deb` or `rpmbuild` on the runner. |
| Cannot create DMG/PKG | Not running on macOS or missing required tools. | Build on macOS with the proper toolchain. |
| Launcher reports main class not found | Wrong `--main-class`, `--main-jar`, or input layout. | Check the JAR, manifest, and relative paths. |
| App-image runs on dev machine but fails on clean machine | Missing runtime modules, dependencies, or native libraries. | Test without a JDK installed; inspect the runtime image and payload. |
| App cannot find config files | Relying on working directory or source-tree paths. | Use image resource paths and explicit user config directories. |
| Runtime image is too large | Including more modules than needed. | Determine needed modules and build a verified runtime with `jlink`. |
| App fails after minimizing runtime | Missing dynamically loaded modules or service providers. | Check module graph, reflection/service loading, and add needed modules. |
| Installer succeeds but shortcut fails to launch | Misconfigured launcher or argument paths. | Check launcher, `--arguments`, `--java-options`, and test on a clean machine. |
| Installer triggers publisher warning | Unsigned, invalid signature, or unnotarized per OS rules. | Perform signing/notarization workflow and verify the artifact. |
| Upgrade installs as a separate product | Upgrade identifier or package identifier changed unintentionally. | Keep `--win-upgrade-uuid` and package identifiers stable across releases. |
| User data deleted during upgrade/uninstall | Storing data inside the installation directory. | Separate user data from the application install directory. |
| Expecting installer to auto-update the app | Confusing `jpackage` with an auto-update service. | Design a dedicated update channel or rely on a package manager. |

## 17. Self-Practice Exercises

### Exercise 1 — Create an App-Image for a Classpath App

An app has `desktop.jar`, main class `com.example.desktop.Main`, and two dependency JARs. Write a `jpackage` command to build an app-image named `DesktopTool`, version `1.0.0`, into destination `dist`.

### Exercise 2 — Package a Modular Application

Module `com.example.desktop` requires `java.desktop` and `com.example.service`. Write the module descriptor and a `jpackage` command using `--module-path` and `--module`.

### Exercise 3 — Choosing the Runtime

An application uses Swing, JDBC, and logging. Identify the JDK modules it likely needs, explain the role of `--add-modules`, and explain why reflection-loaded classes must be checked.

### Exercise 4 — App-Image and Installer

Explain why you should test the app-image before creating an MSI/DMG/DEB. List errors that running the launcher on a clean machine can catch.

### Exercise 5 — Cross-Platform Builds

A team wants to release for Windows, macOS, and Linux from a single Linux machine. Explain the limitations of `jpackage` and propose how to organize build runners per OS.

### Exercise 6 — Protecting Data and Signing

A developer plans to put an API key inside a properties file in the app-image and a private signing key inside the packaging directory. Identify the risks and propose proper ways to manage config and secrets.

### Exercise 7 — Upgrade Plan

A Windows application using MSI needs to upgrade from 1.2.0 to 1.3.0. Explain the roles of `--app-version`, `--win-upgrade-uuid`, user data storage locations, and steps to test upgrade/uninstall.

## 18. Key Reminders for Using jpackage

- `jpackage` in JDK 17 creates app-images or native installers for Java applications.
- An app-image is a directory containing a launcher, payload, and runtime; an installer is an OS-native installation package.
- For classpath applications, use `--input`, `--main-jar`, and `--main-class`; for modular applications, use `--module-path` and `--module`.
- If no runtime image is provided, `jpackage` builds one using `jlink`; customize modules via `--add-modules` and `--jlink-options`.
- You can prebuild a custom runtime with `jlink` and pass it to `jpackage` via `--runtime-image`.
- Use `--app-image` to build an installer from a verified app-image.
- Windows formats include EXE/MSI, macOS formats include DMG/PKG, Linux formats include DEB/RPM; native packaging depends on the host OS and toolchain.
- `jpackage` is not a cross-platform installer generator; build artifacts on runners matching each target platform.
- Use metadata, icons, a resource directory, and `--add-launcher` to polish the application experience.
- Never embed secrets in payloads, launcher arguments, JVM options, or release config files.
- Code signing, notarization, and package signing require platform-specific pipelines; do not assume generated artifacts are automatically signed.
- Maintain stable versions and identifiers; `jpackage` does not provide an auto-update service.
- Test the app-image on a clean machine, then verify installation, upgrade, uninstall, write permissions, and runtime modules before release.

### References

- [Java SE 17 jpackage tool documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html) — package types and packaging options.
- [Java SE 17 jlink tool documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html) — creating custom runtime images.
- [Java SE 17 JDK tools reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/index.html) — JDK 17 tools.
- [JEP 392: Packaging Tool](https://openjdk.org/jeps/392) — `jpackage` becoming an official JDK tool.
