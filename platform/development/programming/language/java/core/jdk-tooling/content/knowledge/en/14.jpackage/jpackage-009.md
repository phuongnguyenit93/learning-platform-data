# Platform-Specific Options of jpackage

**jpackage** is a JDK tool for packaging a Java application into an application image with an included runtime or into an installer in a format native to the operating system. Beyond common options such as application name, version, icon, and output directory, jpackage provides **platform-specific options** to configure launchers, shortcuts, menus, package metadata, and signing for each platform.

Platform-specific options only take effect when running jpackage on the corresponding operating system. For example, **--win-menu** is for Windows only; **--linux-package-deps** is for Linux only; **--mac-sign** is for macOS only. Therefore, a cross-platform release workflow must build separately on each target operating system.

## 1. What Types of Output Does jpackage Produce?

There are two groups of outputs to distinguish:

### Application image

An application image is a packaged application directory, typically containing:

- A launcher to start the application.
- The application's JARs or modules.
- A Java runtime created by jlink or supplied via **--runtime-image**.
- Required configuration and resources.

You can create an application image with:

~~~bash
jpackage --type app-image --name HelloDesk --input input --main-jar hello.jar --main-class com.example.Main --dest dist
~~~

An application image is useful for testing and direct deployment. It is not yet a native installer such as MSI, DEB, or DMG.

### Native installer/package

jpackage can produce platform-specific installer packages:

| Platform | Common Formats | Meaning |
|---|---|---|
| Windows | .exe, .msi | Windows installers |
| Linux | .deb, .rpm | Installer packages for Linux distribution families |
| macOS | .pkg, .dmg | Installer package or disk image containing the application |

**app-image** is available on all supported platforms. Installer formats depend on the host operating system and the packaging software installed on the build machine.

In JDK 24, the list of formats described in the jpackage documentation includes app-image, exe, msi, rpm, deb, pkg, and dmg. When running **jpackage --help**, the tool displays only the options and package types valid on the current machine. For example, JDK 24 on Windows displays app-image, exe, and msi; Linux/macOS options appear when running on those operating systems.

## 2. Principles for Choosing Platform Options

A jpackage command typically consists of the following groups:

1. **Common options:** name, version, vendor, description, icon, and destination directory.
2. **Application input options:** directory containing JARs/resources, or module path and main module.
3. **Runtime options:** additional modules, jlink options, or a pre-built runtime image.
4. **Launcher options:** default arguments, JVM options, additional launchers, and console behavior.
5. **OS-specific package options:** installer type, shortcuts, menus, metadata, signing, or DMG content.

Some common general options:

| Option | Purpose |
|---|---|
| --type | Selects app-image, exe, msi, deb, rpm, pkg, or dmg if supported by the platform |
| --name | Application and package name |
| --app-version | Application/package version |
| --vendor | Application vendor |
| --description | Application description |
| --copyright | Copyright information |
| --icon | Path to an icon appropriate for the platform |
| --dest | Directory containing the output |
| --install-dir | Installation location following the platform's conventions |
| --license-file | License file |
| --about-url | Application homepage |
| --resource-dir | Directory overriding jpackage's default templates or resources |
| --verbose | Prints detailed packaging progress |

**--install-dir** is interpreted differently depending on the operating system: on Linux/macOS it is typically an absolute installation path; on Windows it is a relative subdirectory under the installation root, such as Program Files or AppData.

### Runtime and launcher options

jpackage typically invokes jlink to create a runtime image for the application. If **--runtime-image** is not specified, jpackage uses the tool's default jlink options; the JDK 24 documentation lists options such as **--strip-native-commands**, **--strip-debug**, **--no-man-pages**, and **--no-header-files**.

Useful options:

- **--runtime-image:** uses a runtime image pre-created with jlink.
- **--jlink-options:** passes additional options to jlink.
- **--add-modules:** adds required modules to the runtime image.
- **--module-path:** location of modules.
- **--module:** main module, optionally with the main class.
- **--input:** directory containing input files for a non-modular application.
- **--main-jar** and **--main-class:** specifies the JAR and main class of a non-modular application.
- **--arguments:** default arguments passed to the main class.
- **--java-options:** options passed to the JVM.
- **--add-launcher:** creates an additional launcher from a properties file.

Choose only one of the two ways to declare the entry point: **--module** for modular applications or **--main-jar** for regular JAR applications. Do not use both in the same configuration.

## 3. Windows-Specific Options

Windows options are only available when running jpackage on Windows.

### Launcher options

| Option | Purpose |
|---|---|
| --win-console | Creates a console launcher; used for applications that need console I/O such as CLIs |

Desktop GUI applications generally do not need a console launcher. CLI tools, terminal-interactive programs, or applications that need to display stdout/stderr should consider **--win-console**.

### Installer options

| Option | Purpose |
|---|---|
| --win-dir-chooser | Displays a dialog allowing the user to choose the installation directory |
| --win-help-url | Help or technical support URL |
| --win-menu | Requests adding a shortcut to the Start Menu |
| --win-menu-group | Group name in the Start Menu |
| --win-per-user-install | Requests a per-user installation |
| --win-shortcut | Requests creating a Desktop shortcut |
| --win-shortcut-prompt | Displays an option letting the user decide whether to create shortcuts |
| --win-update-url | Application update information URL |
| --win-upgrade-uuid | UUID used to identify the application in upgrade mechanisms |

**--win-menu** and **--win-shortcut** are suitable when you want to integrate the application into the Windows desktop experience. If using **--win-shortcut-prompt**, combine it with a menu or shortcut request so the installer has the corresponding option to prompt for.

### Example: Creating an MSI on Windows

Assuming the input directory contains hello.jar, where the manifest or build configuration specifies the main class com.example.Main:

~~~powershell
jpackage --type msi --name HelloDesk --input input --main-jar hello.jar --main-class com.example.Main --app-version 1.0.0 --vendor "Example Team" --win-menu --win-menu-group "Example Apps" --win-shortcut --win-dir-chooser --win-per-user-install --dest dist
~~~

To create an EXE installer, change **--type msi** to **--type exe**. If the application is a CLI tool, add **--win-console** to the launcher configuration.

### Required tools on Windows

To create EXE/MSI installers, the build machine requires the WiX Toolset. JDK 24 supports WiX Toolset versions 3, 4, and 5; older JDK releases may have different WiX requirements. Check the release notes for your JDK version and ensure the WiX tools are properly installed.

If you only build **--type app-image**, no MSI/EXE installer is generated, so you can test the application image before installing native packaging tools.

## 4. Linux-Specific Options

Linux options are only available when running jpackage on Linux. jpackage can create DEB packages for Debian/Ubuntu and RPM packages for RPM-based systems such as Fedora or Red Hat Enterprise Linux.

### Linux options

| Option | Purpose |
|---|---|
| --linux-package-name | Linux package name; defaults to the application name |
| --linux-deb-maintainer | Email of the DEB package maintainer |
| --linux-menu-group | Desktop menu group |
| --linux-package-deps | Declares required system packages or capabilities |
| --linux-rpm-license-type | License value in the License field of the RPM spec |
| --linux-app-release | RPM release or DEB Debian revision |
| --linux-app-category | RPM Group or DEB Section |
| --linux-shortcut | Requests creating an application shortcut |

### Creating a DEB

Example of creating a DEB package for Debian/Ubuntu:

~~~bash
jpackage \
  --type deb \
  --name HelloDesk \
  --input input \
  --main-jar hello.jar \
  --main-class com.example.Main \
  --app-version 1.0.0 \
  --linux-package-name hellodesk \
  --linux-deb-maintainer "packaging@example.com" \
  --linux-app-category utils \
  --linux-menu-group Utility \
  --linux-shortcut \
  --dest dist
~~~

**--linux-deb-maintainer** takes the package maintainer's email. **--linux-app-category** maps to Section in the DEB metadata. Choose values that match the conventions of your target distribution and package repository.

### Creating an RPM

Example of creating an RPM package:

~~~bash
jpackage \
  --type rpm \
  --name HelloDesk \
  --input input \
  --main-jar hello.jar \
  --main-class com.example.Main \
  --app-version 1.0.0 \
  --linux-package-name hellodesk \
  --linux-rpm-license-type Apache-2.0 \
  --linux-app-release 1 \
  --linux-app-category Applications/Utilities \
  --linux-shortcut \
  --dest dist
~~~

**--linux-rpm-license-type** writes the license type in the RPM spec. **--linux-app-release** is the RPM package release; for DEB, this value is used as the Debian revision.

### Declaring system dependencies

If the application depends on system libraries outside the Java runtime, you can declare them using **--linux-package-deps**. Values must follow the package/capability syntax of the packaging ecosystem and the package names on the target distribution.

Do not declare a dependency simply because it exists on the build machine. List only libraries that users actually need when installing the package; test the installer on a clean system to catch missing dependencies.

### Required tools on Linux

- Creating a DEB on Ubuntu requires the **fakeroot** tool according to Oracle's packaging guide.
- Creating an RPM on Red Hat Linux requires the **rpm-build** package.
- Build on a Linux system appropriate for the package format and test the package on the target distribution.

Package names and dependencies can differ across distribution versions. A DEB package built on Ubuntu is not guaranteed to fit every Debian/Ubuntu release; similarly, an RPM may depend on system version and dependency metadata.

## 5. macOS-Specific Options

macOS options are only available when running jpackage on macOS. jpackage can create a .app application bundle, a .pkg installer, or a .dmg disk image.

### Launcher and application identification options

| Option | Purpose |
|---|---|
| --mac-package-identifier | Unique identifier of the application on macOS |
| --mac-package-name | Name displayed in the Menu Bar and Info window |
| --mac-app-category | Value of LSApplicationCategoryType in Info.plist |

**--mac-package-identifier** can default to a value derived from the main class. The value should only contain ASCII letters, digits, hyphens, and periods. For example: com.example.hellodesk.

**--mac-package-name** must be shorter than 16 characters according to the JDK 24 documentation. Choose a short, display-friendly name; the package name and display name can differ.

### Code signing options

| Option | Purpose |
|---|---|
| --mac-sign | Requests signing the application image or package |
| --mac-signing-keychain | Specifies the keychain to search for the signing identity |
| --mac-signing-key-user-name | Team or user name portion of the Apple signing identity |
| --mac-package-signing-prefix | Prefix for identifiers of components that need signing but lack an identifier |
| --mac-entitlements | Path to the entitlements file used when signing executables and libraries |
| --mac-app-store | Marks the output for the Mac App Store |

Code signing helps verify the publisher and supports macOS security workflows. For wide distribution, you must design a code signing and notarization workflow following Apple's requirements; **--mac-sign** alone does not mean notarization is complete.

Xcode command line tools are required when using **--mac-sign** and when using a custom icon for a DMG. The signing identity must be present in the specified keychain or the default keychain.

### Additional DMG content

**--mac-dmg-content** allows adding files or directories to the disk image. It can be used multiple times. For example, adding an installation guide or accompanying documentation:

~~~bash
jpackage \
  --type dmg \
  --name HelloDesk \
  --input input \
  --main-jar hello.jar \
  --main-class com.example.Main \
  --app-version 1.0.0 \
  --mac-package-identifier com.example.hellodesk \
  --mac-package-name HelloDesk \
  --mac-app-category public.app-category.utilities \
  --mac-dmg-content docs/README.txt \
  --dest dist
~~~

### Example: Signing a package on macOS

~~~bash
jpackage \
  --type pkg \
  --name HelloDesk \
  --input input \
  --main-jar hello.jar \
  --main-class com.example.Main \
  --app-version 1.0.0 \
  --mac-package-identifier com.example.hellodesk \
  --mac-sign \
  --mac-signing-key-user-name "Developer ID Installer: Example Team" \
  --mac-signing-keychain login.keychain-db \
  --mac-entitlements entitlements.plist \
  --dest dist
~~~

The signing identity name and entitlements must match your actual account, certificate type, and distribution policy. The example only illustrates option placement; replace them with your organization's valid identity and entitlements file.

## 6. Icons, File Associations, and Platform Resources

### OS-specific icons

Icons must be in the format expected by the platform:

| Platform | Common Format |
|---|---|
| Windows | .ico |
| Linux | .png |
| macOS | .icns |

You can pass an icon using **--icon**. If using **--resource-dir**, jpackage can pick up override resources by naming convention, such as launcher-name.ico on Windows, launcher-name.png on Linux, and launcher-name.icns on macOS.

### File associations

**--file-associations** takes a properties file describing the file types the application registers to handle. Common keys include:

~~~properties
extension=hello
mime-type=application/x-hello
description=HelloDesk document
icon=hello-document.ico
~~~

Multiple association files can be used. Icons and association registration depend on the platform; verify the package after installation on the target operating system.

### Resource directory

**--resource-dir** lets you override jpackage's default templates or resources. This provides deep customization for the packaging process, such as desktop files on Linux, launcher icons, WiX templates on Windows, or bundle resources on macOS.

Only override resources once you understand the structure and lifecycle of the template files. An incorrect template can cause the installer to fail, shortcuts not to be created, or a macOS package to fail code signing requirements.

## 7. Example: Preparing a Shared Application Across Platforms

The platform examples above assume **input/hello.jar** already exists. You can create a small JAR using JDK 17 or later.

File src/com/example/Main.java:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println("Hello, " + name + "!");
    }
}
~~~

Create the input directory:

~~~bash
mkdir -p input
~~~

On Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force input
~~~

Compile:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

Package the JAR with Main-Class:

~~~bash
jar --create --file input/hello.jar --main-class com.example.Main -C out .
~~~

Then run jpackage on each target operating system and select the appropriate **--type**. This JAR is non-modular; if your application is modular, use **--module-path** and **--module** instead of **--input**/**--main-jar**.

### Testing the application image before building an installer

You can create an application image:

~~~bash
jpackage --type app-image --name HelloDesk --input input --main-jar hello.jar --dest dist
~~~

Run the launcher inside the application image to verify the runtime and resources. Once the image works properly, use **--app-image** to build the native installer on the same operating system.

For example on Windows, if the application image was created at dist/HelloDesk:

~~~powershell
jpackage --type msi --name HelloDesk --app-image dist/HelloDesk --win-menu --win-shortcut --dest installer
~~~

On macOS, the application image is typically a HelloDesk.app bundle; you can use that bundle as input for PKG or DMG. On Linux, use the application image directory to create DEB or RPM.

## 8. Cross-Platform Builds and CPU Architectures

jpackage does not support cross-platform packaging: a native package must be built on the operating system it targets. You cannot run jpackage on Windows to directly produce a DEB for Linux or a DMG for macOS.

A cross-platform release pipeline typically has separate jobs:

| Build agent | Output | What to verify |
|---|---|---|
| Windows | app-image, EXE, MSI | WiX, shortcuts, install scope, uninstall, and launcher |
| Linux | app-image, DEB, RPM | Package metadata, dependencies, desktop entry, and install/uninstall |
| macOS | app bundle, PKG, DMG | Bundle structure, icon, code signing, and notarization |

In addition to the operating system, pay attention to CPU architecture:

- Choose a JDK and runtime image compatible with the target architecture.
- Verify that JNI and native libraries match the OS, CPU architecture, and ABI.
- If releasing for both x64 and ARM64, build and test artifacts for each architecture using supported toolchains.
- Do not mix runtime images or native libraries from another platform into the current package.

You can use CI with Windows, Linux, and macOS runners to produce the corresponding artifacts. Each job should record the JDK vendor/version, OS, architecture, package type, and jpackage options.

## 9. Common Errors

### Unrecognized option

An option such as **--win-menu** only exists on Windows. If run on Linux or macOS, jpackage may report an invalid option. Check **jpackage --help** on the exact build agent and pass only options for that platform.

### Failed to create EXE/MSI

The Windows machine may be missing WiX or PATH may not recognize the tools properly. Check the WiX version, JDK release, and error messages from jpackage.

### Failed to create DEB or RPM

Check the corresponding packaging tool: **fakeroot** for DEB workflows on Ubuntu or **rpm-build** for RPM on Red Hat Linux. Also check destination directory permissions and package metadata.

### Failed to sign macOS package

Check Xcode command line tools, signing identity, keychain, entitlements, and certificate access permissions. Ensure the identifier and bundle resources are valid. If distributing outside an internal environment, complete a separate notarization workflow per Apple's requirements.

### Missing or invalid icon format

Use the correct icon format for the target OS and check relative/absolute paths. With **--resource-dir**, filenames must match the resource naming convention jpackage looks for.

### Package installs, but application fails to launch

Check the main class/JAR or module, dependencies, runtime image, default arguments, JVM options, and resources. Test the application image before building the installer to isolate launcher/runtime issues from installer issues.

### Missing Linux dependencies

Declare actually required system packages with **--linux-package-deps** and test on a clean distribution. Dependency names must match the target package manager.

### Package built on wrong OS or architecture

Build native artifacts on a build agent with the matching platform and architecture. Do not use an installer from one OS as output for another OS; verify native libraries and runtime images before release.

## 10. Platform Packaging Checklist

- Explicitly specify **--type**; do not rely on the default platform type in release builds.
- Determine whether the application is modular or non-modular and choose **--module** or **--main-jar**.
- Verify JARs, modules, resources, and dependencies before packaging.
- Choose the right icon format: ICO, PNG, or ICNS.
- Use **--app-image** to test the launcher/runtime before building the installer.
- Only use **--win-*** on Windows, **--linux-*** on Linux, and **--mac-*** on macOS.
- Install all required native tools: WiX on Windows, fakeroot/rpm-build on Linux, and Xcode command line tools when needed on macOS.
- Correctly configure shortcuts, menu groups, install directories, package dependencies, and metadata.
- Use a valid signing identity and entitlements when signing macOS applications.
- Verify code signing and notarization according to Apple's distribution requirements.
- Build separately for each target OS and CPU architecture.
- Install, run, upgrade, and uninstall the package on a corresponding clean environment.
- Record the JDK version, OS, architecture, package type, and build command to reproduce artifacts.

## 11. Key Terms

| Term | Meaning |
|---|---|
| jpackage | Tool for packaging a Java application into an application image or installer |
| Platform-specific option | Option available only on a single operating system |
| Application image | Application directory containing the launcher and required runtime |
| Native installer | Installer package in the operating system's native format |
| MSI / EXE | Windows installer formats |
| DEB / RPM | Linux package formats |
| PKG / DMG | macOS installer or disk image formats |
| WiX Toolset | Toolset used by jpackage to build Windows installers |
| File association | Associating a file extension with an application |
| Signing identity | Identity/certificate used to sign an application |
| Entitlements | Permissions granted to a signed macOS application |
| Notarization | Apple's process for checking software before distribution |
| Runtime image | Java runtime created by jlink or supplied externally |
| Resource directory | Directory containing override templates and resources for jpackage |

jpackage's platform-specific options help integrate Java applications with the familiar installation and launch experience on each operating system. Choose the right installer type, use the appropriate Windows/Linux/macOS options, build on the target platform, and test the package just as an end user would install it.

## References

- Oracle JDK 24 — The jpackage Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jpackage.html
- Oracle JDK 24 — Packaging Overview: https://docs.oracle.com/en/java/javase/24/jpackage/packaging-overview.html
- Oracle — JDK 24 Release Notes, WiX Toolset support: https://www.oracle.com/java/technologies/javase/24-relnote-issues.html
