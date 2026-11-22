# Native Installers with jpackage

**jpackage** is a JDK tool for packaging Java applications into an application image or an operating system native installer. A native installer can integrate with the platform's installation workflow, application menu, shortcuts, installation directory, and software management mechanisms.

A native installer typically bundles the application together with a dedicated Java runtime created or provided during packaging. Users can install and run the application without manually installing a compatible JDK/JRE on their machine, provided the package is built for the matching operating system and architecture.

A basic command on Windows:

~~~bash
jpackage --type msi --name HelloDesk --input build/input --main-jar hello.jar --main-class com.example.hello.Main --dest build/installers
~~~

On Linux, you can build DEB or RPM packages; on macOS, you can build PKG or DMG packages. The set of supported formats depends on the platform running `jpackage`.

## 1. Native installer, application image, and runtime image

These three concepts are related but distinct:

- **Runtime image:** a Java runtime linked from the required modules, typically created by `jlink`. It contains the runtime modules and libraries needed by the application.
- **Application image:** an application directory containing a launcher, application libraries, configuration, and the bundled runtime image. You can run an application image without installing it through an installer.
- **Native installer:** an installation package in the operating system's native format. It installs the application image into the appropriate location and can integrate menus, shortcuts, metadata, and uninstallation.

Typical packaging flow:

~~~text
Java source / JAR / modular application
                  |
                  v
             javac / jar
                  |
                  v
              jpackage
                  |
          +-------+--------+
          |                |
          v                v
    Application image   Native installer
          |                |
          v                v
      test run      install on machine
                           |
                           v
                    run application
~~~

`jpackage` can create an application image first, or build a native installer directly. When no existing runtime image is passed, `jpackage` typically invokes `jlink` to generate a runtime suited to the application. You can pass a pre-built runtime image using the `--runtime-image` option.

An application image is useful for testing and directory-based deployment. A native installer is appropriate when end users expect a familiar installation experience.

## 2. Package formats by operating system

Main package types:

| Platform | Format | Purpose |
|---|---|---|
| Windows | exe | Windows executable installer |
| Windows | msi | Windows Installer package |
| Linux | deb | Package for the Debian/Ubuntu ecosystem |
| Linux | rpm | Package for the RPM ecosystem such as Fedora/RHEL |
| macOS | pkg | macOS installer package |
| macOS | dmg | Disk image containing the application or installer package |
| All supported platforms | app-image | Application image as a directory or bundle |

The package names and build capabilities depend on the operating system where `jpackage` runs. `jpackage` is not a general-purpose cross-compile installer tool: you typically must build Windows packages on Windows, macOS packages on macOS, and Linux packages on Linux.

An application image is also platform-specific because the runtime contains native libraries and an executable tailored to the operating system/architecture. Do not copy a Linux image to Windows and expect it to run as a Windows application.

### Windows

You can create an MSI:

~~~bash
jpackage --type msi --name HelloDesk --input build/input --main-jar hello.jar --dest build/installers
~~~

Or an EXE:

~~~bash
jpackage --type exe --name HelloDesk --input build/input --main-jar hello.jar --dest build/installers
~~~

Common options:

- **--win-menu:** creates a shortcut in the Start Menu.
- **--win-shortcut:** creates a desktop shortcut.
- **--win-menu-group:** sets the group name in the Start Menu.
- **--win-dir-chooser:** allows choosing the installation directory.
- **--win-upgrade-uuid:** a stable upgrade identifier across versions of the same application.

For MSI, the build machine requires the Windows packaging toolset required by the JDK version in use, typically the WiX Toolset. Check the `jpackage` documentation for your specific JDK for required versions and installation prerequisites.

### Linux

Create a DEB:

~~~bash
jpackage --type deb --name hellodesk --input build/input --main-jar hello.jar --dest build/installers
~~~

Create an RPM:

~~~bash
jpackage --type rpm --name hellodesk --input build/input --main-jar hello.jar --dest build/installers
~~~

Selected Linux options:

- **--linux-package-name:** package name in the package management system.
- **--linux-deb-maintainer:** maintainer information for DEB.
- **--linux-rpm-license-type:** license type in RPM metadata.
- **--linux-app-category:** application category.
- **--linux-shortcut:** creates a desktop shortcut when supported by the environment.
- **--linux-package-deps:** declares OS-level package dependencies if needed.

To build DEB or RPM packages, the build machine needs the corresponding packaging tools. For example, a DEB environment typically uses tools from the `dpkg` ecosystem; an RPM environment requires RPM build tools. Package names, dependencies, and metadata should follow the conventions of the target Linux distribution.

### macOS

You can create a PKG:

~~~bash
jpackage --type pkg --name HelloDesk --input build/input --main-jar hello.jar --dest build/installers --mac-package-identifier com.example.hellodesk
~~~

Or a DMG:

~~~bash
jpackage --type dmg --name HelloDesk --input build/input --main-jar hello.jar --dest build/installers
~~~

Selected macOS options:

- **--mac-package-identifier:** reverse-domain package identifier.
- **--mac-package-name:** display package name.
- **--mac-sign:** requests signing the application according to `jpackage` signing configuration.
- **--mac-signing-key-user-name:** signing certificate identity.
- **--mac-signing-keychain:** keychain containing the certificate.
- **--mac-entitlements:** entitlements file used when signing where applicable.

Building macOS packages generally requires Apple's system tools and an appropriate signing environment if distributed externally. For publicly released applications, review Apple's Developer ID signing and notarization process; creating a PKG/DMG does not by itself guarantee the application is notarized.

## 3. General jpackage syntax and options

General syntax:

~~~bash
jpackage [options]
~~~

Commonly used options:

| Option | Purpose |
|---|---|
| --type | Output type: `app-image`, `exe`, `msi`, `deb`, `rpm`, `pkg`, or `dmg` depending on the platform |
| --name | Application name |
| --input | Directory containing input files to package |
| --dest | Output directory |
| --main-jar | Main JAR of a non-modular application |
| --main-class | Main class of the application |
| --module | Module and main class of a modular application |
| --module-path | Where to locate modules |
| --runtime-image | Pre-built runtime image |
| --add-modules | Modules to add to the runtime image |
| --jlink-options | Options passed to `jlink` when creating the runtime |
| --app-version | Application version |
| --vendor | Application vendor |
| --description | Application description |
| --copyright | Copyright notice |
| --license-file | License file included in the package |
| --icon | Application or installer icon if supported by the platform |
| --resource-dir | Directory containing custom resources for the packager |
| --verbose | Display verbose logs |

Specific options and support may vary by JDK version. Run the following command to view help on your build machine:

~~~bash
jpackage --help
~~~

To view options for a specific package type:

~~~bash
jpackage --type msi --help
~~~

If the platform does not support the requested package type, `jpackage` will report an error. Always verify the option list for the exact JDK and operating system used for building.

## 4. Packaging non-modular applications

Non-modular applications are typically packaged from a main JAR along with its dependent libraries.

For this approach, you typically use:

- **--input:** directory containing the main JAR and dependencies to package.
- **--main-jar:** name of the main JAR relative to the input directory.
- **--main-class:** fully qualified name of the class with the `main` method, if you do not want to rely on `Main-Class` in the manifest.

Example:

~~~bash
jpackage \
    --type app-image \
    --name HelloDesk \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --dest build/app-image
~~~

If the JAR already has a valid `Main-Class` manifest entry, you can omit `--main-class`. In a reliable build pipeline, you should either verify the manifest or specify the main class explicitly.

Other dependency JARs must be present in the input directory and configured so the launcher can locate them. If the application uses a complex classpath, inspect the launcher configuration file inside the application image after packaging and test running it on a clean machine.

## 5. Packaging modular applications

Modular applications use a module descriptor and module path.

Syntax:

~~~bash
jpackage \
    --type app-image \
    --name Greeter \
    --module-path mlib \
    --module com.example.greeter/com.example.greeter.Main \
    --dest build/app-image
~~~

Where:

- **--module-path mlib:** location containing modular JARs or exploded modules.
- **--module com.example.greeter/com.example.greeter.Main:** the module and main class to run.
- **--name Greeter:** name of the application image.
- **--dest:** output directory for the image.

If the module descriptor already declares `Main-Class` via the `ModuleMainClass` attribute, omitting the main class may work in some cases; however, explicitly specifying `module/main-class` makes the configuration easier to read and verify.

For modular applications, `jpackage` uses the module graph to determine dependencies. If additional runtime modules are needed, you can use `--add-modules`. Do not place automatic modules or arbitrary classpath JARs on the module path and assume `jlink` will be able to link them.

## 6. Bundled runtime image

A native installer can include its own Java runtime. This is a key advantage that lets users install the application without installing a separate JDK.

There are two ways to provide a runtime:

### Let jpackage create the runtime

If `--runtime-image` is not specified, `jpackage` can invoke `jlink` to create a runtime image for the application.

~~~bash
jpackage \
    --type app-image \
    --name HelloDesk \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --add-modules java.base \
    --dest build/app-image
~~~

The `--add-modules` option specifies which modules to include in the runtime. For applications using Swing/AWT, JDBC drivers, logging, or other APIs, the required module set may be larger than `java.base`. Select modules based on actual dependencies and test the application after building the image.

`jpackage` can pass `jlink` options to customize the runtime image. For example:

~~~bash
jpackage \
    --type app-image \
    --name HelloDesk \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --jlink-options "--strip-debug --no-header-files --no-man-pages" \
    --dest build/app-image
~~~

Valid `jlink` options depend on the JDK. Passing an unsupported option will cause image creation to fail.

### Provide a pre-built runtime image

If you have already created a runtime with `jlink`, you can pass it:

~~~bash
jpackage \
    --type app-image \
    --name HelloDesk \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --runtime-image build/runtime \
    --dest build/app-image
~~~

When using `--runtime-image`, `jpackage` packages the existing runtime instead of generating a new one. The runtime image must match the target platform and contain all modules required by the application.

Do not bundle a runtime image from one operating system into an installer for another operating system. Build and test separately for each platform.

## 7. Launcher and application execution configuration

`jpackage` generates a launcher for the application. The launcher resides inside the application image and is installed along with the application by the installer.

Options that control the launcher:

- **--arguments:** default arguments passed to the main class when a user launches the application.
- **--java-options:** options passed to the JVM, such as heap settings or system properties.
- **--add-launcher:** adds an additional launcher with its own configuration.
- **--icon:** launcher icon if supported by the platform.

Example:

~~~bash
jpackage \
    --type app-image \
    --name HelloDesk \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --arguments "production" \
    --java-options "-Xmx512m" \
    --java-options "-Dapp.profile=production" \
    --dest build/app-image
~~~

Application arguments are passed to `String[] args`. Java options are applied to the JVM before running the main class.

Do not confuse `--arguments` with `--java-options`. A value like `production` is an application argument; `-Xmx512m` is a JVM option.

### Multiple launchers

You can add a second launcher using `--add-launcher`:

~~~bash
jpackage \
    --type app-image \
    --name HelloDesk \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --add-launcher diagnostics=build/diagnostics.properties \
    --dest build/app-image
~~~

The `diagnostics.properties` file holds the additional launcher's configuration, such as `main-jar`, `main-class`, `module`, `arguments`, `java-options`, or `icon` as supported by `jpackage`. Check valid properties and syntax against `jpackage --help` for your JDK.

Multiple launchers are useful when a single application image needs several entry points, such as the main application, an admin utility, or a diagnostics mode. Each launcher must point to a valid entry point, and its dependencies must be present in the image.

## 8. Metadata, icon, license, and file associations

An installer needs metadata to display the name, version, vendor, and support information.

Example:

~~~bash
jpackage \
    --type app-image \
    --name HelloDesk \
    --app-version 1.2.0 \
    --vendor "Example Company" \
    --description "Desktop greeting application" \
    --copyright "Copyright 2026 Example Company" \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --dest build/app-image
~~~

Metadata fields may be displayed in the installer UI or by the operating system depending on the platform.

### Icon

Use `--icon` to specify an icon file appropriate for the operating system. Accepted formats depend on the platform; for example, Windows typically uses ICO, macOS uses ICNS, and Linux can use PNG.

~~~bash
jpackage --type app-image --name HelloDesk --icon src/packaging/hellodesk.png ...
~~~

The icon path must exist on the build machine. Verify that the icon renders properly in both the application image and the actual installer.

### License

Use `--license-file` to include a license file in the package if supported by the package type.

~~~bash
jpackage --type msi --name HelloDesk --license-file packaging/LICENSE.rtf ...
~~~

License file formats and how the installer displays them can vary by platform. Verify the final package.

### File associations

`jpackage` supports configuring file associations via a properties file passed with `--file-associations`. The configuration can specify file extensions, MIME types, descriptions, and corresponding icons.

File associations can alter OS behavior when users open a file type. Only register associations that genuinely belong to your application, and test installation, upgrades, and uninstallation.

## 9. Hands-on Java 17+ example: creating an application image and installer

This example creates a simple `HelloDesk` application from a non-modular JAR, then uses `jpackage` to build an application image and a native installer.

Source structure:

~~~text
jpackage-demo/
└── src/
    └── com/
        └── example/
            └── hello/
                └── Main.java
~~~

### Step 1: Write the application

Create `src/com/example/hello/Main.java`:

~~~java
package com.example.hello;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Hello from HelloDesk.");

        if (args.length > 0) {
            System.out.println("profile=" + args[0]);
        }
    }
}
~~~

The program prints a greeting and prints the first argument if provided.

### Step 2: Compile with Java 17

From the `jpackage-demo` root directory:

~~~bash
mkdir -p build/classes build/input
javac --release 17 -d build/classes src/com/example/hello/Main.java
~~~

In PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path "build/classes" | Out-Null
New-Item -ItemType Directory -Force -Path "build/input" | Out-Null
javac --release 17 -d "build/classes" "src/com/example/hello/Main.java"
~~~

### Step 3: Create a JAR with Main-Class

~~~bash
jar --create \
    --file build/input/hello.jar \
    --main-class com.example.hello.Main \
    -C build/classes .
~~~

Inspect the manifest if needed:

~~~bash
jar --describe-module --file build/input/hello.jar
~~~

A non-modular JAR can be described as an automatic module when used on the module path, but in this example we use `--main-jar`, so there is no need to convert it into a named module.

### Step 4: Create the application image

~~~bash
jpackage \
    --type app-image \
    --name HelloDesk \
    --app-version 1.0.0 \
    --vendor "Example Company" \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --arguments "production" \
    --dest build/app-image
~~~

`jpackage` creates the application image in `build/app-image`. The image contains the launcher, application, and runtime packaged according to the `jpackage` configuration.

The launcher's location and file extension inside the image vary by platform. On Windows, the launcher is typically an `.exe` file; on Linux, an executable binary; on macOS, the application image can be a `.app` bundle.

### Step 5: Test the application image

Run the launcher created inside the image. On Linux, the path typically looks like:

~~~bash
./build/app-image/HelloDesk/bin/HelloDesk
~~~

On Windows, the launcher typically looks like:

~~~powershell
.\build\app-image\HelloDesk\HelloDesk.exe
~~~

On macOS, open the application bundle created in the destination directory or run the executable inside the bundle according to the image layout.

Output:

~~~text
Hello from HelloDesk.
profile=production
~~~

If no output appears, check the launcher, configuration file, main class, input JAR, and runtime image. Some GUI applications do not open a console and therefore do not display `stdout` like a CLI example.

### Step 6: Create a native installer on Windows

On Windows, run:

~~~powershell
jpackage --type msi --name HelloDesk --app-version 1.0.0 --vendor "Example Company" --input "build/input" --main-jar "hello.jar" --main-class "com.example.hello.Main" --win-menu --win-shortcut --dest "build/installers"
~~~

If you need an EXE installer:

~~~powershell
jpackage --type exe --name HelloDesk --app-version 1.0.0 --input "build/input" --main-jar "hello.jar" --main-class "com.example.hello.Main" --dest "build/installers"
~~~

The installer file name and location are determined by `jpackage` based on the application name, version, and platform conventions. Check the output directory after the build.

### Step 7: Create a native installer on Linux

On a DEB-based system:

~~~bash
jpackage --type deb --name hellodesk --app-version 1.0.0 --vendor "Example Company" --input build/input --main-jar hello.jar --main-class com.example.hello.Main --dest build/installers
~~~

On an RPM-based system:

~~~bash
jpackage --type rpm --name hellodesk --app-version 1.0.0 --vendor "Example Company" --input build/input --main-jar hello.jar --main-class com.example.hello.Main --dest build/installers
~~~

Only build the format matching the package ecosystem and packaging tools available on the build machine.

### Step 8: Create a native installer on macOS

Create a PKG:

~~~bash
jpackage --type pkg --name HelloDesk --app-version 1.0.0 --vendor "Example Company" --input build/input --main-jar hello.jar --main-class com.example.hello.Main --mac-package-identifier com.example.hellodesk --dest build/installers
~~~

Or create a DMG:

~~~bash
jpackage --type dmg --name HelloDesk --app-version 1.0.0 --vendor "Example Company" --input build/input --main-jar hello.jar --main-class com.example.hello.Main --dest build/installers
~~~

The Windows, Linux, and macOS commands are platform-specific alternatives. A single build machine cannot simultaneously produce native installers for all three operating systems simply by changing `--type`.

## 10. Installing, running, and uninstalling

After creating a native installer, test it as an end user would.

### Windows

For MSI, you can install via the Windows Installer UI or run:

~~~powershell
msiexec /i "HelloDesk-1.0.0.msi"
~~~

Uninstall:

~~~powershell
msiexec /x "HelloDesk-1.0.0.msi"
~~~

Replace the file name with the actual artifact generated by `jpackage`. Verify the Start Menu entry, desktop shortcut, installation directory, and the Uninstall entry in Windows Settings.

### Debian/Ubuntu

Install DEB:

~~~bash
sudo apt install ./hellodesk_1.0.0-1_amd64.deb
~~~

Uninstall by package name:

~~~bash
sudo apt remove hellodesk
~~~

The package name and file name depend on metadata, version, and architecture. Do not copy the illustrative file name if your actual artifact has a different name.

### Fedora/RHEL

Install RPM:

~~~bash
sudo dnf install ./hellodesk-1.0.0-1.x86_64.rpm
~~~

Uninstall:

~~~bash
sudo dnf remove hellodesk
~~~

Depending on the distribution, the package manager command may differ. Use the appropriate tool for the target operating system.

### macOS

For DMG, open the disk image and follow the instructions inside. For PKG, open the installer package or use the macOS `installer` tool according to administrative policies.

Verify that the application appears in the expected location, launches properly, and can be removed as intended. For applications distributed outside the App Store, test Gatekeeper, signing, and notarization on a clean machine.

## 11. Versioning, upgrades, and package identifiers

Installers require stable metadata so the operating system can identify the application and handle upgrades.

- **--app-version:** application version displayed in the package.
- **--name:** application name, which also typically affects the artifact file name.
- **--vendor:** vendor name.
- **--win-upgrade-uuid:** upgrade identifier for Windows installers; must remain stable across versions of the same product.
- **--mac-package-identifier:** macOS package identifier.
- **--linux-package-name:** Linux package name.

Do not change the upgrade UUID between MSI versions if the goal is to upgrade an existing installation as the same product. Manage the UUID in release configuration and test the upgrade path from the previous version.

Increment the app version according to your project's release rules. Check how each platform normalizes versions; some package formats impose specific rules on version components and characters.

You should test all three paths:

1. Fresh installation on a machine without the application.
2. Upgrading from a previous version.
3. Uninstalling and confirming that user data is preserved or removed as designed.

Do not store persistent user data inside the installation directory if the installer may replace or delete that directory during updates or uninstallation.

## 12. Code signing and secure distribution

Native installers are executable artifacts and must be released through a proper security pipeline.

### Windows

Installers can be signed with Authenticode after packaging. Signing identifies the publisher and detects file tampering after signing. The signing workflow typically uses a certificate and signing tools from the Windows SDK.

Do not modify an MSI/EXE file after signing; any change invalidates the signature. Verify the signature and timestamp before release.

### macOS

Publicly distributed macOS applications typically need to be signed with an appropriate Developer ID and notarized according to Apple's requirements. Depending on the package type, you may need to sign the application bundle, the installer package, and complete notarization.

`jpackage` provides several macOS signing options, but generating a PKG/DMG does not by itself mean the artifact is properly signed and notarized for distribution.

### Linux

DEB/RPM packages can be distributed through repositories with signed metadata or an organization's package verification mechanism. Protect artifacts and repositories, control write access, and publish checksums/signatures according to your release process.

### Software supply chain

- Pin the JDK and dependency versions used for builds.
- Record the `jpackage` command or configuration.
- Verify the origin and licenses of packaged libraries.
- Scan dependencies and artifacts before release.
- Sign the final artifact after all modifications are complete.
- Store checksums and build provenance.
- Distribute installers only through official channels.

## 13. CI/CD integration

`jpackage` can be integrated into a release pipeline:

1. Check out the source and install the exact JDK.
2. Build the application and dependencies.
3. Run unit tests.
4. Create the JAR or modular artifact.
5. Build the application image with `jpackage`.
6. Run a launcher smoke test.
7. Build the native installer for the current platform.
8. Verify metadata, icon, launcher, and runtime.
9. Sign the artifact if required.
10. Test installation in a clean environment.
11. Store the artifact, checksums, and build metadata.

Use separate runners for Windows, Linux, and macOS to build platform-native packages. They can share the same source and version, while each runner produces its own artifact.

Do not build installers on shared runners with stale package state without cleaning the output. Scope output directories by version/build number or clean the destination directory before creating new artifacts.

Separate platform-specific packaging configuration in scripts or build tools so you do not accidentally pass `--win-*` options to a Linux build or `--mac-*` options to a Windows build.

## 14. Common errors and troubleshooting

**jpackage cannot find the main JAR**

Check `--input` and `--main-jar`. The main JAR name is typically resolved relative to the input directory. Ensure the file has been copied into the input directory before running.

**Main class not found**

Check the `Main-Class` manifest attribute or specify `--main-class` with the fully qualified package and class name. Ensure the class actually exists in the JAR and has a valid `main` method.

**Module not found**

For modular apps, check `--module-path`, `--module`, `module-info.class`, and `requires` dependencies. For non-modular apps, use `--main-jar` instead of trying to run them as named modules.

**Runtime image is missing modules**

Check the APIs used by the application and its dependencies. Use `--add-modules` or provide a pre-built runtime image with all required modules. Test on a machine without a JDK to catch dependencies accidentally resolved from the developer environment.

**Failed to build native installer**

Verify that the package type is supported on the build OS and that the required platform packaging tools are installed. Inspect the full `jpackage` error output and run `jpackage --help` on the exact JDK.

**Installer runs but the launcher fails**

Test running the application image before building the installer. Check the launcher, runtime, configuration, dependency files, and default arguments.

**Icon or metadata does not appear**

Check the resource path, icon format, and platform-specific options. Inspect the generated package because some metadata renders differently across operating systems.

**Package manager does not recognize dependencies**

Declare dependencies at the right layer: Java module dependencies in the module graph and OS package dependencies in package metadata. These two types of dependencies are distinct.

**Installer does not upgrade properly**

Check the app version, package identifier, and Windows upgrade UUID. Test upgrading from the same package type of a previous version and verify user data handling.

**Application triggers security warnings**

Check code signing, certificate chain, timestamp, notarization, and distribution source. Do not bypass warnings by instructing users to disable OS security protections.

## 15. Pre-release checklist for native installers

- [ ] Application launches from its JAR or module before packaging.
- [ ] Main class/module is configured accurately.
- [ ] All required dependencies and resources are present in input or runtime.
- [ ] Runtime image has the right modules and Java version.
- [ ] Application image runs on the target platform.
- [ ] Native installer is built on the matching operating system.
- [ ] Metadata, version, vendor, icon, and license are accurate.
- [ ] Shortcuts, menu entries, and file associations work as expected.
- [ ] Fresh install, upgrade, and uninstall have been tested.
- [ ] Signing and notarization are completed where required.
- [ ] Installer has been tested on a clean machine without a JDK installed.
- [ ] Checksums and build provenance are stored alongside the artifact.

## 16. Concise workflow to remember

~~~bash
# Compile application
javac --release 17 -d build/classes src/com/example/hello/Main.java

# Create input JAR
jar --create --file build/input/hello.jar \
    --main-class com.example.hello.Main \
    -C build/classes .

# Create an application image first
jpackage --type app-image \
    --name HelloDesk \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --dest build/app-image

# Create a native installer on the target OS
jpackage --type <platform-package> \
    --name HelloDesk \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --dest build/installers
~~~

Replace `<platform-package>` with the appropriate type: `msi` or `exe` on Windows, `deb` or `rpm` on Linux, `pkg` or `dmg` on macOS. Required options and packaging tools depend on the platform.

`jpackage` turns a Java application into an application image or native installer ready for end-user distribution. For reliable releases, choose the right package format, include the necessary runtime and dependencies, test install/upgrade/uninstall flows, and sign and verify artifacts according to each operating system's requirements.

## References

- [The jpackage Command — Java Platform, Standard Edition](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [The jlink Command — Java Platform, Standard Edition](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [Packaging Tool User Guide — Java Platform, Standard Edition](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-tool-user-guide.pdf)
