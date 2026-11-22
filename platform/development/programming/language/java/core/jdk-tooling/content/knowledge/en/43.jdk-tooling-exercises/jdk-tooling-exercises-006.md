# Creating an Installer with jpackage for Java Applications

jpackage is the packaging tool included with the JDK, used to turn a built Java application into an application image with its own launcher and runtime, or into an OS-native installer. Users can install and run the application without having to install Java separately, provided the runtime image is packaged completely.

A reliable workflow consists of two stages: create the application image, test-run that image with its bundled runtime, and only then create the installer. An application image is an application directory that can be run directly; installers such as MSI, EXE, DEB, RPM, PKG, or DMG add the operating system's installation experience. These two artifact types serve different purposes and should be tested separately.

This article practices with a Java 17+ application, then expands to multi-JAR applications, modular applications, custom runtime images, metadata, icons, shortcuts, file associations, signing, upgrades, and cross-platform CI. The jpackage commands in this article are verified against JDK 24.0.2; available options depend on the operating system and JDK version.

## 1. What Does jpackage Produce?

jpackage takes a compiled application along with its required resources. The tool produces:

- An application launcher to start the application.
- A directory containing JARs/modules, launcher configuration, and resources.
- A Java runtime image created by jlink or a pre-prepared runtime image.
- A native installer if an OS package type is selected.

Common output types:

| Operating System | Native Installer | Application Image |
|---|---|---|
| Windows | EXE, MSI | Application directory with an .exe file |
| Linux | DEB, RPM | Application directory with a launcher |
| macOS | PKG, DMG | .app bundle |

On Windows, EXE and MSI fit familiar installation workflows. On Linux, DEB/RPM integrate with the package manager. On macOS, DMG commonly distributes an application bundle to drag into Applications; PKG uses the package installation workflow.

jpackage does not cross-compile installers. You must run the tool on the target platform: create EXE/MSI on Windows, DEB/RPM on Linux, and PKG/DMG on macOS. If you need to release for multiple platforms, use a dedicated runner for each operating system.

## 2. Checking the JDK and Packaging Prerequisites

jpackage is located in the JDK's bin directory. Check the tool and its version:

Windows PowerShell:

~~~powershell
where.exe jpackage
jpackage --version
jpackage --help
~~~

Linux/macOS:

~~~bash
command -v jpackage
jpackage --version
jpackage --help
~~~

You should use a pinned JDK in your build pipeline. Record the versions of java, javac, jlink, and jpackage to avoid unknowingly compiling with one JDK and packaging with another.

Some platform-specific prerequisites:

| Platform | Prerequisites for Installer |
|---|---|
| Windows | WiX Toolset 3.0 or later to create EXE/MSI |
| Linux RPM | rpm-build on the RPM packaging system |
| Linux DEB | fakeroot and Debian packaging tools on the DEB packaging system |
| macOS | Xcode Command Line Tools when signing with --mac-sign or customizing DMG icons |

An application image can be created without native installer tools. This is why you should create and test the app-image first, even when the final target is MSI/DEB/DMG.

## 3. Preparing a Sample Application

Create the directory structure:

~~~text
jpackage-demo/
  src/
    demo/
      Main.java
  classes/
  input/
  dist/
~~~

File src/demo/Main.java:

~~~java
package demo;

import java.util.Arrays;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("JPACKAGE_OK");
        System.out.println("args=" + Arrays.toString(args));
    }
}
~~~

Compile targeting Java 17 APIs and bytecode:

Windows:

~~~powershell
javac --release 17 -encoding UTF-8 -d classes src\demo\Main.java
~~~

Linux/macOS:

~~~bash
javac --release 17 -encoding UTF-8 -d classes src/demo/Main.java
~~~

Create a JAR with Main-Class:

~~~powershell
jar --create --file input\jpackage-demo.jar --main-class demo.Main -C classes .
~~~

On Linux/macOS:

~~~bash
jar --create --file input/jpackage-demo.jar --main-class demo.Main -C classes .
~~~

Inspect the JAR:

~~~powershell
jar --list --file input\jpackage-demo.jar
~~~

This JAR is a non-modular application on the classpath. jpackage will use the main JAR and main class to create the launcher.

## 4. Creating the Application Image First

Create the app-image on Windows:

~~~powershell
jpackage --type app-image --name JPackageDemo --input input --main-jar jpackage-demo.jar --app-version 1.2.3 --vendor "Java Tooling Lab" --description "Java desktop packaging demo" --arguments packaged-default --win-console --dest dist
~~~

On Linux/macOS:

~~~bash
jpackage --type app-image --name JPackageDemo --input input --main-jar jpackage-demo.jar --app-version 1.2.3 --vendor "Java Tooling Lab" --description "Java desktop packaging demo" --arguments packaged-default --dest dist
~~~

For console apps on Windows, add --win-console so the launcher has a console. GUI applications typically omit this option.

After running successfully, Windows creates a directory layout like:

~~~text
dist/
  JPackageDemo/
    JPackageDemo.exe
    app/
      JPackageDemo.cfg
      jpackage-demo.jar
    runtime/
      ...
~~~

Linux typically has the launcher in bin, a lib/app directory, and runtime. macOS creates a JPackageDemo.app bundle with launcher, Resources, app, and runtime inside Contents.

Do not rely on the names or structure of internal files beyond what is documented; exact internal layouts may vary across JDK versions.

## 5. Testing the Application Image

On Windows:

~~~powershell
.\dist\JPackageDemo\JPackageDemo.exe
~~~

On Linux:

~~~bash
./dist/JPackageDemo/bin/JPackageDemo
~~~

On macOS:

~~~bash
open dist/JPackageDemo.app
~~~

If the launcher was created with --arguments packaged-default and the user passes no other arguments, the sample application's output is:

~~~text
JPACKAGE_OK
args=[packaged-default]
~~~

Additional checks:

- The launcher runs from the app-image directory.
- The application uses the runtime inside the app-image.
- All required JARs and resources are present in the payload.
- Exit codes and logs match expectations.
- Paths containing spaces do not break the launcher.
- The application works on a test machine without a system-wide JDK installed.

The application can print System.getProperty("java.home") and System.getProperty("java.version") to confirm the actual runtime. In a test run on JDK 24.0.2, the launcher reported java.version=24.0.2 and java.home pointed to the runtime directory inside the application image.

## 6. The Bundled Runtime Created by jlink

If --runtime-image is not passed, jpackage invokes jlink to create a runtime image. The default generated runtime strips debug symbols, native commands, man pages, and header files to reduce size.

This means the app-image's runtime directory typically does not contain a java.exe/java command for manual execution. On Windows, the default runtime image may not include runtime/bin/java.exe because jlink uses --strip-native-commands. The launcher created by jpackage still runs the application normally using the JVM inside the runtime image.

Therefore, when testing the app-image, run the application launcher and check java.home from inside the JVM. Do not conclude that the runtime is missing simply because java.exe is not found in the runtime directory.

By default, jpackage creates a runtime for a non-modular application with a module set similar to a standard classpath environment. If the application uses ServiceLoader or needs service providers from the runtime image, consider --bind-services:

~~~powershell
jpackage --type app-image --name JPackageDemo --input input --main-jar jpackage-demo.jar --jlink-options "--bind-services" --dest dist
~~~

You can add JDK modules required by the application using --add-modules:

~~~powershell
jpackage --type app-image --name JPackageDemo --input input --main-jar jpackage-demo.jar --add-modules java.sql,java.net.http --dest dist
~~~

Do not guess modules based solely on source imports. You can run jdeps --print-module-deps on the artifact to find static dependencies, then review reflection, ServiceLoader, native code, and runtime configuration as well.

## 7. Choosing the Right Target Java Runtime

--release 17 during compilation only restricts the language features, bytecode, and Java SE APIs that the source code is allowed to use. It does not force jpackage to create a Java 17 runtime.

If you run jpackage from JDK 24 without passing a separate runtime image, the runtime created by jlink belongs to JDK 24. The application image in the earlier example behaved this way: the source was compiled with --release 17, but the bundled runtime was Java 24.0.2.

If your product requires users to run Java 17:

1. Use JDK 17 to run jpackage, or
2. Create a runtime image from JDK 17 using jlink and pass it via --runtime-image.

Example of creating a custom runtime from JDK 17:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods" --add-modules java.base,java.desktop,java.logging --strip-debug --no-header-files --no-man-pages --output runtime-17
~~~

This command must be run with JAVA_HOME pointing to JDK 17, and the module list must match the actual application. Then package that runtime:

~~~powershell
jpackage --type app-image --name JPackageDemo --input input --main-jar jpackage-demo.jar --runtime-image runtime-17 --dest dist
~~~

The runtime image must match the target operating system and architecture. Do not create a Windows runtime and use it as the payload for Linux or macOS.

## 8. Packaging Applications with Multiple Dependency JARs

For non-modular applications, the --input directory contains the main JAR and any auxiliary JARs/resources to distribute. The main JAR's manifest should declare Class-Path for dependency JARs.

Example manifest:

~~~text
Manifest-Version: 1.0
Main-Class: demo.Main
Class-Path: helper.jar logging.jar
~~~

Place the files in the same input directory:

~~~text
input/
  app.jar
  helper.jar
  logging.jar
  config/
    default.properties
~~~

Package:

~~~powershell
jpackage --type app-image --name MultiJarDemo --input input --main-jar app.jar --dest dist
~~~

jpackage adds the JARs declared in the manifest Class-Path to the launcher's classpath configuration. In the generated launcher configuration file, this list appears under the app.classpath property. Paths in the manifest are relative URLs to the main JAR; verify exact filenames, case sensitivity, and directory locations.

Another option is creating a fat/uber JAR with the Maven Shade Plugin or Gradle Shadow Plugin. When using a fat JAR, check service descriptors, resource merging, signature files, and the manifest after packaging.

Do not simply copy dependency JARs into input and assume the launcher will automatically find every file. Inspect the generated launcher configuration file and run the app-image on a clean machine.

## 9. Packaging Modular Applications

A modular application has module-info.java and modular JARs/JMODs on the module path. Example:

~~~java
module com.example.jpackage {
    requires java.desktop;
    requires java.logging;
}
~~~

Assuming the main class is com.example.Main and the module has been built into the mods directory:

~~~powershell
jpackage --type app-image --name ModularDemo --module-path mods --module com.example.jpackage/com.example.Main --app-version 1.0.0 --dest dist
~~~

--module specifies the main module and can include the main class. jpackage/jlink includes the main module and its transitive dependencies in the runtime image.

If additional modules beyond the dependency graph are needed, use --add-modules. If the application uses service providers, consider --jlink-options "--bind-services". Verify the module graph and runtime with jdeps and jlink, then run a smoke test on the image.

Do not use both --module and --main-jar in the same command; these two ways of specifying the application are mutually exclusive.

## 10. Metadata, Icons, and Resources

A professional installer should declare product information:

| Option | Meaning |
|---|---|
| --name | Application/package name |
| --app-version | Application/package version |
| --vendor | Vendor |
| --description | Description |
| --copyright | Copyright information |
| --about-url | Homepage or support URL |
| --license-file | License file |
| --icon | Application/package icon |
| --dest | Output directory |
| --resource-dir | Directory to override default resources/templates |

Common icon formats:

- Windows: .ico.
- macOS: .icns.
- Linux: .png.

Windows example:

~~~powershell
jpackage --type app-image --name AcmeDesk --input input --main-jar app.jar --main-class com.acme.Main --app-version 2.4.0 --vendor "Acme Example" --description "Acme desktop application" --copyright "Copyright Acme Example" --icon packaging\acme.ico --license-file LICENSE.txt --dest dist
~~~

Store icons and licenses in packaging sources managed in the repository. Do not use copyrighted icons without distribution rights. Do not include secrets, signing keys, or build environment details in application resources.

--app-content can add files or directories outside input to the application payload. Use it for extra resources when the existing input layout does not fit.

## 11. Creating Secondary Launchers and Configuring JVM Options

A product may provide multiple launchers, such as a main application and an administration tool. Create a properties file for the secondary launcher:

~~~text
main-jar=app.jar
main-class=com.acme.Main
description=Acme maintenance console
arguments=--mode=maintenance
java-options=-Xmx512m
win-console=true
~~~

Add the secondary launcher:

~~~powershell
jpackage --type app-image --name AcmeDesk --input input --main-jar app.jar --add-launcher Maintenance=packaging\maintenance.properties --dest dist
~~~

Supported keys include module, main-jar, main-class, description, arguments, java-options, app-version, icon, and several platform-specific options. Supported key names and options depend on the JDK/OS; check jpackage --help before using them.

--arguments sets default arguments when the user launches without passing any others. --java-options passes JVM options to the runtime. Do not use JVM options to store passwords, tokens, or secrets.

## 12. File Associations

You can instruct the installer to register your application to open a specific file type. Create a properties file:

~~~text
extension=acme
mime-type=application/x-acme
description=Acme project file
icon=acme-file.ico
~~~

Package:

~~~powershell
jpackage --type msi --name AcmeDesk --app-image dist\AcmeDesk --file-associations packaging\acme-file.properties --dest dist\installers
~~~

Verify the extension, MIME type, icon, and file-opening behavior. On Windows, file associations can affect the user's default application choices; do not silently alter associations if the installer does not clearly disclose this behavior.

## 13. Creating MSI or EXE Installers on Windows

After the app-image has been tested, create an MSI:

~~~powershell
jpackage --type msi --name JPackageDemo --app-image dist\JPackageDemo --app-version 1.2.3 --vendor "Java Tooling Lab" --win-upgrade-uuid 123e4567-e89b-42d3-a456-426614174000 --win-menu --win-shortcut --win-dir-chooser --dest dist\installers
~~~

Or create an EXE installer:

~~~powershell
jpackage --type exe --name JPackageDemo --app-image dist\JPackageDemo --app-version 1.2.3 --vendor "Java Tooling Lab" --win-upgrade-uuid 123e4567-e89b-42d3-a456-426614174000 --win-menu --win-shortcut --dest dist\installers
~~~

WiX Toolset 3.0 or later must be installed on the build machine to create Windows EXE/MSI installers. Install WiX according to machine policy and ensure the tool can be found by jpackage. Machines that only create an app-image do not need WiX.

Some Windows options:

- --win-menu creates a Start Menu shortcut.
- --win-menu-group sets the Start Menu group.
- --win-shortcut creates a Desktop shortcut.
- --win-shortcut-prompt asks the user whether to create a shortcut.
- --win-dir-chooser allows choosing the installation directory.
- --win-per-user-install selects a per-user installation; the default is typically machine-wide.
- --install-dir sets the subdirectory under the default installation location.
- --win-upgrade-uuid identifies the product's upgrade identity.

Keep the same upgrade UUID across releases of the same product. Do not generate a new UUID on every build if you want the installer to recognize upgrades. Increment the version according to release rules and test upgrading from an older version on a test machine.

## 14. Creating DEB or RPM on Linux

On Debian/Ubuntu, create a DEB:

~~~bash
jpackage --type deb --name acmedesk --input input --main-jar app.jar --main-class com.acme.Main --app-version 2.4.0 --linux-deb-maintainer packaging@example.com --linux-package-deps "libc6" --linux-menu-group Utility --linux-shortcut --dest dist
~~~

On RPM-based systems such as Fedora/RHEL, create an RPM:

~~~bash
jpackage --type rpm --name acmedesk --input input --main-jar app.jar --main-class com.acme.Main --app-version 2.4.0 --linux-rpm-license-type MIT --linux-app-release 1 --linux-app-category Applications/Utilities --dest dist
~~~

An RPM build machine needs rpm-build; an Ubuntu environment creating DEB packages needs fakeroot as required by the packaging platform. Dependency names, categories, license types, and maintainers must match actual distribution policies.

You can use --linux-package-deps to declare OS packages that the application requires. Do not declare system dependencies arbitrarily; verify package names on each target distribution.

## 15. Creating PKG or DMG on macOS

Create a DMG:

~~~bash
jpackage --type dmg --name AcmeDesk --input input --main-jar app.jar --main-class com.acme.Main --app-version 2.4.0 --mac-package-identifier com.acme.desk --icon packaging/AcmeDesk.icns --dest dist
~~~

Create a PKG by changing --type dmg to --type pkg. --mac-package-identifier should remain stable across versions; it is the application's unique identifier on macOS.

When distributing outside the Mac App Store, sign the application/package with an appropriate certificate. jpackage supports --mac-sign along with --mac-signing-key-user-name and related signing options. Xcode Command Line Tools are required for this signing process and certain DMG customization operations.

After signing, releasing outside the App Store typically also requires notarization via the Apple notary service and stapling the ticket. Example with a profile configured in Keychain:

~~~bash
xcrun notarytool submit dist/AcmeDesk.dmg --keychain-profile ACME_NOTARY --wait
xcrun stapler staple dist/AcmeDesk.dmg
~~~

Signing identity names, keychain profiles, and entitlements must come from a real distribution account. Do not commit certificate private keys or credentials to the repository.

## 16. Signing Installers on Windows

Windows installers should be Authenticode-signed before wide distribution. With the Windows SDK, signtool can sign EXE/MSI files and verify signatures:

~~~powershell
signtool sign /fd SHA256 /tr TIMESTAMP_SERVER /td SHA256 /a dist\installers\JPackageDemo-1.2.3.msi
signtool verify /pa /v dist\installers\JPackageDemo-1.2.3.msi
~~~

Replace TIMESTAMP_SERVER with the timestamp service used by your organization or certificate provider. You can sign EXE and MSI files separately if releasing both.

Certificates should be stored in a certificate store or CI secret manager. Restrict access to the signing identity, never commit PFX files or passwords, and log verification results. Verify signatures after all artifact-modifying steps are complete.

## 17. Installation, Upgrade, and Uninstallation

Successfully creating an installer does not prove the installation experience works properly. You need to verify:

1. Fresh installation on a clean machine.
2. Launching the application from the Start Menu/Desktop or application menu.
3. Checking the bundled runtime and resource files.
4. Upgrading from an older version.
5. Checking shortcuts and file associations after an upgrade.
6. Uninstalling and confirming that application files are cleaned up properly.
7. Checking whether user data is preserved according to policy.
8. Installing with both standard user accounts and administrator accounts if both are supported.

Do not store user data in the installation directory where it can be overwritten or removed by the installer. Use user home/AppData or the OS-appropriate application data location. Clearly define whether uninstallation deletes or preserves user data.

For Windows, keep the upgrade UUID stable. For Linux, package name and version must be consistent so the package manager recognizes upgrades. For macOS, verify the bundle identifier and signing identity across releases.

## 18. Testing on Clean Machines and in CI

CI should build artifacts on a runner for each target operating system. Example strategy:

| Stage | Checks |
|---|---|
| Build | Compile, unit tests, package JAR/module |
| App image | Run launcher, verify runtime, arguments, and resources |
| Installer | Create MSI/EXE, DEB/RPM, or PKG/DMG |
| Install test | Install on a clean machine/VM and run the application |
| Upgrade test | Install old version, upgrade to new version, and verify data |
| Security | Verify signature, certificate chain, and timestamp |
| Release | Archive checksums, version, build logs, and installers |

Do not create a Windows installer on a Linux runner by passing --type msi; jpackage does not cross-compile. Use a Windows runner with WiX, a Linux runner with the appropriate packaging prerequisites, and a macOS runner for PKG/DMG.

Record the JDK version, jpackage command, OS image, architecture, dependency locks, and artifact checksums. You can generate SHA-256 checksums:

Windows:

~~~powershell
Get-FileHash dist\installers\JPackageDemo-1.2.3.msi -Algorithm SHA256
~~~

Linux/macOS:

~~~bash
shasum -a 256 dist/installers/*
~~~

## 19. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| jpackage cannot find JDK tools | Incorrect PATH/JAVA_HOME or using a JRE | Use a full JDK and verify jpackage/jlink |
| Cannot create MSI/EXE | Missing WiX or WiX not found | Install WiX Toolset and check PATH |
| App image builds but launcher fails | Incorrect main class/JAR or classpath | Check --main-jar, --main-class, and manifest |
| ClassNotFoundException | Missing dependency JAR in payload/classpath | Add the JAR and manifest Class-Path |
| NoClassDefFoundError at runtime | Missing runtime dependency or service provider | Check modules, Class-Path, and --bind-services |
| java.exe not found in runtime | Default runtime stripped native commands | Run the application launcher and check java.home |
| App fails on older Java | Runtime image created from a newer JDK | Use jpackage/runtime image from the target JDK |
| New icon not visible | Wrong format or icon path | Use OS-appropriate .ico/.icns/.png and rebuild image |
| ServiceLoader cannot find provider | jlink runtime did not bind service providers | Try --jlink-options "--bind-services" |
| Installer upgrade creates separate install | Unstable upgrade identity/version | Keep upgrade UUID and package identity consistent |
| App runs locally but fails on clean machine | Missing native dependency, config, or resource | Test app-image on a clean VM of the target OS |
| Invalid signature | Signed before modifying artifact or wrong certificate | Sign last and re-verify |

## 20. jpackage Release Checklist

- [ ] JDK and jpackage versions are pinned.
- [ ] Application is built and tested before packaging.
- [ ] Main JAR/class or module is declared properly.
- [ ] All required dependencies and resources are in the payload.
- [ ] Manifest Class-Path or module path is verified.
- [ ] Runtime image matches the minimum Java version.
- [ ] Service providers and additional modules are reviewed.
- [ ] App-image runs successfully on a clean machine.
- [ ] Metadata, version, vendor, icon, and license are accurate.
- [ ] Installer is built on the matching OS/architecture.
- [ ] Windows WiX or Linux/macOS packaging prerequisites are ready.
- [ ] Shortcuts, menus, file associations, and install directory are tested.
- [ ] Upgrade, uninstall, and user data handling are verified.
- [ ] Installer is signed and verified if required.
- [ ] CI archives checksums, logs, and toolchain versions.

jpackage helps distribute Java applications as native desktop software while bundling the runtime so users do not need to install Java themselves. Test the application image first, choose the right runtime version, verify dependencies and service providers, and build the installer on the matching operating system. Release quality is determined by the launcher, runtime, installer, signing, upgrade, and uninstall experience together—not merely by the jpackage command exiting successfully.

## References

- Oracle Java SE 24 — Packaging Overview: https://docs.oracle.com/en/java/javase/24/jpackage/packaging-overview.html
- Oracle Java SE 24 — The jpackage Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jpackage.html
- Oracle Java SE 24 — Support Application Requirements: https://docs.oracle.com/en/java/javase/24/jpackage/support-application-features.html
- Oracle Java SE 24 — The jlink Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html
- Oracle Java SE 24 — The jar Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html
- Microsoft — SignTool: https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool
- Apple — Notarizing macOS Software: https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution
