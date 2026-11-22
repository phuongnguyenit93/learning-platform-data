# Verifying Installers Built with `jpackage`

`jpackage` packages Java applications into an **application image** or a **native installer** for the target platform. Verifying an installer is not just confirming that an `.msi`, `.exe`, `.pkg`, `.dmg`, `.deb`, or `.rpm` file was generated. You need to confirm that the package contains the right application, launcher, Java runtime, resources, and metadata; installs cleanly on a clean environment; launches properly; and upgrades and uninstalls without leaving unexpected state behind.

There are three output categories to distinguish:

- **Application image (`app-image`):** an application directory containing the launcher, application contents, and a runtime image if bundled together.
- **Native installer:** an installation package integrated with the operating system, with appropriate metadata, installation paths, shortcuts, file associations, and uninstall mechanisms.
- **Runtime package:** a standalone runtime image package, not necessarily containing an application.

A successful build only proves that the tool produced an artifact. Release quality must be confirmed by verifying contents, metadata, signatures, installation, application execution, upgrades, and uninstallation on the target operating system.

## 1. Distinguishing Application Images and Native Installers

`jpackage` can create an application image first and then use that image as input for the installer packaging step.

| Output Type | Purpose | Key Checks |
|---|---|---|
| `app-image` | Directory containing launcher, application, and runtime | File structure, launcher, runtime, resources, and behavior |
| `exe` | Windows executable installer | Signature, metadata, installer UI, logs, install/uninstall |
| `msi` | Windows Installer package | MSI tables, ProductCode/UpgradeCode, logs, install/upgrade/uninstall |
| `pkg` | macOS installer package | Signature, package metadata, payload, Gatekeeper, and install |
| `dmg` | macOS application distribution disk image | DMG integrity, mounted contents, app signature, and copy/install workflow |
| `deb` | Linux Debian package | Control metadata, dependencies, file payload, and install/remove |
| `rpm` | Linux RPM package | Package metadata, dependencies, signature, and install/erase |

Supported installer types depend on the operating system and JDK. `jpackage --help` displays the valid types for the current platform. On a Windows environment tested with JDK 24.0.2, the list includes `app-image`, `exe`, and `msi`. On Linux or macOS, run `jpackage --help` directly on the target build machine to confirm the supported package types and platform options.

Typically, `jpackage` builds native packages for the operating system it is running on. You cannot build an MSI on Linux or a DMG on Windows simply by changing `--type`; you must build on the corresponding platform or use the corresponding build environment.

## 2. Checking the Toolchain Before Packaging

Record the tool versions and platform details:

~~~text
java --version
javac --version
jpackage --version
jpackage --help
~~~

Verify:

- The JDK has `jpackage` in its `bin` directory.
- The JDK used for packaging matches the target release and application dependencies.
- The build machine's operating system and architecture match the artifact to be released.
- The native packaging tools required by the platform are available.
- Version, vendor, product name, and icon are defined.
- Permissions exist to create the output directory and temporary directory.

Depending on the operating system and package type, native tools may include the WiX Toolset on Windows, `.deb`/`.rpm` packaging tools on Linux, or built-in packaging/signing tools on macOS. Check the documentation for your exact JDK and operating system rather than assuming every package type is built solely by `jpackage`.

Save the JDK version, operating system, architecture, command line, and native tool versions in the build log. This data is essential when reproducing an older installer or investigating discrepancies between CI and developer machines.

## 3. Inputs That Affect the Installer

`jpackage` has two main ways to declare an application:

- **Non-modular application:** uses `--input`, `--main-jar`, and optionally `--main-class`.
- **Modular application:** uses `--module-path` and `--module`.

Do not use `--module` and `--main-jar` simultaneously in the same application configuration.

Key options:

| Option | Effect |
|---|---|
| `--type` | Selects `app-image` or a platform-appropriate native package type |
| `--name` | Application/package name |
| `--dest` | Directory for the output artifact |
| `--input` | Directory containing JARs and files to package |
| `--main-jar` | Main JAR, path relative to the input directory |
| `--main-class` | `main` class when using `--main-jar` |
| `--module-path` | Where to find modules for modular applications |
| `--module` | Module name, optionally with main class |
| `--app-content` | Additional files/directories in the payload |
| `--runtime-image` | Pre-built runtime image |
| `--add-modules` | Additional modules to include in the runtime image |
| `--app-version` | Application/package version |
| `--vendor` | Vendor name |
| `--description` | Application description |
| `--copyright` | Copyright information |
| `--icon` | Application/package icon |
| `--license-file` | License file bundled with the installer |
| `--about-url` | Application homepage/info URL |
| `--verbose` | Prints additional packaging activity |
| `--temp` | Specifies a temporary directory; if specified, it is kept after the run |

`--input` contains the files to be packaged. For applications requiring configuration files or resources outside the JAR, verify they are actually present in the payload. Do not assume `jpackage` automatically discovers and copies every file in the project's source directory.

## 4. Building an Application Image First for Verification

Building an image separately lets you verify the launcher and runtime before investigating the native installer. If the image does not run properly, the issue lies in the application or packaging configuration, and there is no need to inspect the installer UI yet.

A non-modular project layout:

~~~text
project/
  src/
    demo/
      Main.java
  classes/
  input/
    inventory.jar
  dist/
  installers/
~~~

Create `src/demo/Main.java`:

~~~java
package demo;

public class Main {
    public static void main(String[] args) {
        System.out.println("Installer smoke test OK");
    }
}
~~~

From the `project` directory, compile and create the JAR:

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force classes, input, dist, installers | Out-Null
javac --release 17 -d classes src\demo\Main.java
jar --create --file input\inventory.jar --main-class demo.Main -C classes .
~~~

macOS/Linux:

~~~sh
mkdir -p classes input dist installers
javac --release 17 -d classes src/demo/Main.java
jar --create --file input/inventory.jar --main-class demo.Main -C classes .
~~~

Create the application image on Windows:

~~~powershell
jpackage --type app-image --name Inventory --input input --main-jar inventory.jar --main-class demo.Main --app-version 1.2.0 --vendor "Example Corp" --dest dist --win-console --verbose
~~~

`--win-console` creates a console launcher on Windows, which fits this stdout-printing example. For GUI applications, choose the appropriate launcher configuration and check the application logs rather than expecting a console window.

On Linux/macOS, omit `--win-console` and use the launcher options for the corresponding platform. If you want to package an app image from a custom runtime image built with `jlink`, use `--runtime-image` to supply the prepared runtime.

## 5. Verifying the Application Image

After creating the image, inspect the entire file tree:

Windows PowerShell:

~~~powershell
Get-ChildItem -Force -Recurse dist\Inventory |
    Select-Object FullName, Length
~~~

macOS/Linux:

~~~sh
find dist/Inventory -type f -print
~~~

The exact structure varies by platform and JDK, but typically includes equivalent components:

- Application launcher.
- Directory containing JARs and resources.
- Launcher configuration.
- Bundled runtime image if `jpackage` created or copied the runtime.
- Platform-specific support files.

Check the following points:

1. The launcher has the right name and is in the expected location.
2. The main JAR and all required resources are present in the payload.
3. The runtime is bundled if the application requires a self-contained runtime.
4. No unnecessary build/test/debug files are included.
5. Icon, product name, and metadata are applied correctly.
6. The launcher configuration file has the expected main class/module, JVM options, and arguments.
7. No absolute paths point back to the build directory on the development machine.

Run the launcher directly from the image:

Windows:

~~~powershell
.\dist\Inventory\Inventory.exe
~~~

Linux:

~~~sh
./dist/Inventory/bin/Inventory
~~~

macOS uses an application bundle with a `.app` structure; the launcher is inside `Contents/MacOS`:

~~~sh
./dist/Inventory.app/Contents/MacOS/Inventory
~~~

Stdout of the console example:

~~~text
Installer smoke test OK
~~~

If the image contains a runtime, check the runtime modules:

Windows:

~~~powershell
.\dist\Inventory\runtime\bin\java.exe --list-modules
~~~

Linux:

~~~sh
./dist/Inventory/lib/runtime/bin/java --list-modules
~~~

macOS:

~~~sh
./dist/Inventory.app/Contents/runtime/Contents/Home/bin/java --list-modules
~~~

The runtime location may vary depending on the image structure and platform. Locate the `java` executable inside the bundled runtime rather than hard-coding a single path across all OSes.

## 6. Building an Installer from a Verified Application Image

Once the application image runs properly, use `--app-image` to build the native installer. This approach separates application content verification from native package verification.

Windows MSI example:

~~~powershell
jpackage --type msi --name Inventory --app-image dist\Inventory --app-version 1.2.0 --vendor "Example Corp" --dest installers --win-menu --win-shortcut --win-upgrade-uuid "123e4567-e89b-42d3-a456-426614174000" --verbose
~~~

Key points:

- `--app-image` points to the created and verified application image.
- `--type msi` requests a native Windows Installer package.
- `--win-menu` and `--win-shortcut` request the appropriate shortcuts.
- `--win-upgrade-uuid` defines the MSI product's `UpgradeCode`; it must remain stable across releases in the same product line.
- `--app-version` must follow the versioning rules of the package format and native tools.

The artifact filename is typically based on the application name and version, such as `Inventory-1.2.0.msi`. Read the actual filename from the `installers` directory rather than assuming it if your build script has custom naming rules.

On the tested Windows JDK, `jpackage --help` confirms `app-image`, `exe`, and `msi` are valid types. For an EXE installer, replace `--type msi` with `--type exe` if you want that format and the required native tools are installed.

## 7. Verifying Installer Metadata and Contents on Windows

### 7.1. Checking Signatures and Checksums

Inspect the Authenticode signature:

~~~powershell
Get-AuthenticodeSignature .\installers\Inventory-1.2.0.msi |
    Format-List Status, StatusMessage, SignerCertificate
~~~

For the `.exe` launcher:

~~~powershell
Get-AuthenticodeSignature .\dist\Inventory\Inventory.exe |
    Format-List Status, StatusMessage, SignerCertificate
~~~

If the release process signs with the Windows SDK, you can verify using:

~~~text
signtool verify /pa /v installers\Inventory-1.2.0.msi
signtool verify /pa /v dist\Inventory\Inventory.exe
~~~

`NotSigned` can be normal in an unsigned test build. For release artifacts, release policy should require a valid signature, a certificate from the proper publisher, and a timestamp according to organizational standards.

Generate a SHA-256 checksum:

~~~powershell
Get-FileHash .\installers\Inventory-1.2.0.msi -Algorithm SHA256
~~~

Store the hash in the release manifest and compare it after downloading the artifact from distribution channels. A checksum proves the file contents have not changed relative to the trusted hash; it does not replace digital signatures or publisher verification.

### 7.2. Inspecting the MSI Database

Use Orca (Windows SDK) to inspect key MSI tables:

- `Property`: product name, version, vendor, and package metadata.
- `File`: list of installed files.
- `Component`: installation components and key paths.
- `Directory`: installation directory structure.
- `Shortcut`: shortcuts to be created.
- `Registry`: registry entries.
- `Feature`: installation features.
- `Upgrade`: version detection and upgrade rules.

Cross-check metadata against release information. Verify that shortcuts point to the right launcher, the install directory is sensible, and no unwanted files are present.

You can create an administrative installation image for inspection or internal distribution with:

~~~text
msiexec /a installers\Inventory-1.2.0.msi TARGETDIR=C:\PackageInspection
~~~

An administrative install extracts the MSI deployment structure into the target directory; it is not equivalent to a full application installation and does not replace actual installation testing.

## 8. Installing, Running, and Uninstalling the MSI in a Test Environment

Perform installation on a clean virtual machine or test machine—do not use the build machine as sole evidence. Capture detailed logs:

~~~powershell
msiexec /i .\installers\Inventory-1.2.0.msi /qn /l*v install.log
~~~

After installation:

- Confirm the installation process exits with a success code; code `3010` means installation succeeded but a reboot is required.
- Identify the actual install directory from the MSI log or installer configuration.
- Verify the installed launcher and runtime.
- Verify Start Menu/Desktop shortcuts if requested.
- Launch the application both via the shortcut and directly from the install directory.
- Verify write permissions for files, configuration, logs, and user data.
- Verify file associations if the product registers custom file types.

Uninstall using the package:

~~~powershell
msiexec /x .\installers\Inventory-1.2.0.msi /qn /l*v uninstall.log
~~~

After uninstallation, confirm:

- The application no longer appears in the list of installed programs.
- Shortcuts created by the installer have been removed.
- Files and registry entries owned by the installer have been cleaned up.
- User data intended to be retained is handled according to product policy.
- A clean reinstall succeeds after uninstallation.

Do not manually delete the installation directory before running uninstall, as doing so can prevent you from testing the real uninstallation workflow.

## 9. Verifying EXE Installers and Windows Upgrade Workflows

An EXE installer may provide a wizard or bootstrapper wrapping the installation process. Check:

- Name and publisher displayed in the UI.
- Default installation path and directory change option if `--win-dir-chooser` is enabled.
- Start Menu/Desktop shortcuts per `--win-menu` and `--win-shortcut`.
- Per-user vs. per-machine installation behavior.
- Error messages when permissions are insufficient or a version is currently running.
- Authenticode signature and SmartScreen warnings according to the release environment.

If releasing multiple MSI versions, test upgrades on a virtual machine:

1. Install the old version.
2. Record version, install path, shortcuts, and user data.
3. Install the new version with the same `UpgradeCode`.
4. Confirm the new version replaces the old version per policy.
5. Check retained data and updated files.
6. Uninstall the new version and inspect the final state.

`--win-upgrade-uuid` is the upgrade identifier for the MSI product line. Do not generate a new random UUID for every release if the goal is to upgrade the same product. Store this UUID in release configuration for reproducible builds.

## 10. Verifying Packages on Linux

On Linux, native package types may include `.deb` or `.rpm` depending on the distro, JDK, and available native tools. Run `jpackage --help` on the Linux machine to confirm supported options and package types.

### 10.1. Verifying Debian Packages

Inspect metadata:

~~~sh
dpkg-deb --info Inventory.deb
dpkg-deb --field Inventory.deb Package Version Architecture Depends
~~~

List files in the payload:

~~~sh
dpkg-deb --contents Inventory.deb
~~~

Extract for inspection:

~~~sh
mkdir -p extracted
dpkg-deb --extract Inventory.deb extracted
~~~

Cross-check package name, version, architecture, dependencies, file paths, and launcher. Install on a matching Debian/Ubuntu VM, run a smoke test, and remove using the package manager:

~~~sh
sudo apt install ./Inventory.deb
sudo apt remove inventory
~~~

The actual package name may differ from the filename; read the `Package` field from metadata before running the remove command.

`dpkg-deb` inspects metadata and payload, whereas APT repository signatures are typically verified at the repository metadata level. Do not treat a successful `dpkg-deb --info` as proof that the package is signed or from a trusted publisher.

### 10.2. Verifying RPM Packages

Inspect metadata and payload files:

~~~sh
rpm -qpi Inventory.rpm
rpm -qpl Inventory.rpm
rpm -qp --requires Inventory.rpm
~~~

Check digest/signature if the package is signed:

~~~sh
rpm -K Inventory.rpm
~~~

Install and remove on a matching VM:

~~~sh
sudo dnf install ./Inventory.rpm
sudo dnf remove inventory
~~~

On systems using `yum` or another package manager, adjust commands per distro. Read the actual package name from metadata before removing.

Check scriptlets, dependencies, file permissions, system menu/desktop entries, and data locations. Unsigned RPM packages may report a missing signature; evaluate this according to release policy rather than automatically treating it as a payload error.

## 11. Verifying Packages on macOS

On macOS, `jpackage` can create an application image, a `.pkg` installer, or a `.dmg` disk image depending on the JDK and operating system.

### 11.1. Verifying DMG

Verify the disk image:

~~~sh
hdiutil verify Inventory.dmg
~~~

Mount to inspect contents:

~~~sh
hdiutil attach Inventory.dmg
~~~

Inspect the `.app` application and accompanying files. After inspection, unmount the volume using `hdiutil detach` with the actual mount point.

### 11.2. Verifying PKG

Check the installer signature:

~~~sh
pkgutil --check-signature Inventory.pkg
spctl --assess --type install --verbose Inventory.pkg
~~~

You can inspect the package structure:

~~~sh
pkgutil --expand Inventory.pkg expanded-pkg
~~~

Cross-check package identifier, version, payload, install location, and scripts if present. Install on a macOS test machine:

~~~sh
sudo installer -pkg Inventory.pkg -target /
~~~

Then verify the app opens, the runtime works, and Gatekeeper does not unexpectedly block the application.

### 11.3. Verifying App Signatures and Notarization

For macOS application releases, check the bundle signature:

~~~sh
codesign --verify --deep --strict --verbose=2 Inventory.app
spctl --assess --type execute --verbose Inventory.app
~~~

For applications distributed outside internal environments, signing and notarization must follow your organization's Apple Developer policy. Verify the package and app bundle status separately; a package signature alone does not prove every binary inside is properly configured.

## 12. Verifying File Associations, Shortcuts, and Metadata

If using `--file-associations`, check both the association configuration file and post-install behavior. Common keys include:

- `extension`: file extension.
- `mime-type`: MIME type.
- `icon`: associated icon.
- `description`: file type description.

Verify on a clean machine:

1. Install the application.
2. Confirm the file type is registered properly.
3. Open a sample file by double-clicking it.
4. Check that the application receives the correct file path and processes the content.
5. Uninstall and confirm the association is cleaned up as expected.

Metadata such as `--name`, `--app-version`, `--vendor`, `--description`, `--copyright`, icon, license file, and about URL should align with the download page, release manifest, and OS-displayed information.

## 13. Runtime Image and Dependencies to Verify

A self-contained Java installer typically bundles a runtime image. Confirm:

- The runtime matches the target Java version.
- All modules required by the application are present in the runtime.
- Reflection, service providers, plugins, and JNI work inside the trimmed runtime.
- Native libraries match the operating system and architecture.
- Required resources, configurations, and truststores are present.
- Default launcher JVM options and arguments are correct.
- No dependencies accidentally point back to the JDK on the build machine.

If `--runtime-image` is passed, `jpackage` uses the provided runtime image. If omitted, the tool may invoke `jlink` to create a runtime image with the default options of that JDK version. Check `jpackage --help` to see the defaults and `--jlink-options`.

On the JDK tested in this guide, help lists `--strip-debug`, `--no-header-files`, `--no-man-pages`, and `--strip-native-commands` as defaults when `jpackage` creates a runtime image. Defaults can vary across JDKs; if you need a runtime with specific modules or native commands, create a custom runtime with `jlink` and supply it via `--runtime-image`.

## 14. Logs, Temporary Directories, and Reproducing Packaging Errors

When an installer build fails, enable verbose output:

~~~text
jpackage --verbose ...
~~~

You can retain the temporary directory for investigation:

~~~text
jpackage --temp build-temp --verbose ...
~~~

Per `jpackage --help`, the `--temp` directory must be new or empty; when specified, it is not automatically deleted after the command finishes. Inspect logs, WiX configurations, or platform-specific intermediate files in this directory.

When logging an error, record:

- Full command line and exit code.
- `java`, `javac`, and `jpackage` versions.
- OS version and architecture.
- Native packaging tool and version.
- `stdout`/`stderr` output.
- Temporary directory and log files.
- Requested package type.
- Input metadata and payload file list.

Do not conclude a build succeeded merely because an output file appeared. Check `jpackage`'s exit code and confirm the artifact has a reasonable size and is readable by native OS tools.

## 15. Pre-Release Installer Testing Matrix

| Check Group | Question to Confirm | Evidence |
|---|---|---|
| Build | Did `jpackage` exit successfully? | Exit code, verbose log |
| Artifact | Correct type, name, version, and architecture? | File/package metadata |
| Payload | Contains JARs, resources, launcher, and runtime? | App image/package contents |
| Runtime | Does the app run on a machine without a JDK installed? | Clean VM smoke test |
| Metadata | Are vendor, description, icon, and license accurate? | Installer UI/package database |
| Signature | Are signature and certificate valid? | Authenticode/codesign/pkg verification |
| Install | Installs to the right location and creates shortcuts? | Install log, filesystem, OS menu |
| Operation | Does the app open and accept arguments/file associations? | Functional test |
| Upgrade | Does the new version properly replace the old one? | Upgrade test, retained data |
| Uninstall | Are shortcuts and installed files cleaned up properly? | Uninstall log, filesystem |
| Integrity | Is the artifact unchanged after upload? | SHA-256 checksum |
| Portability | Correct OS/CPU package and native dependencies? | Target VM test |

A minimal workflow should include clean install, launch, functional smoke test, upgrade, and uninstall. For critical applications, add tests for user permissions, paths with spaces/Unicode characters, offline install, multiple user profiles, file associations, services, firewall, and antivirus based on the deployment environment.

## 16. Common Errors When Verifying Installers

### `jpackage` reports unsupported package type

**Cause:** The package type does not match the current operating system or JDK.

**Resolution:** Run `jpackage --help` on the build host, use a listed package type, and build on the target OS.

### WiX or native packaging tool not found

**Cause:** Required native tools are missing or not on `PATH`.

**Resolution:** Install the exact version per JDK/platform documentation, verify the executable, and rerun `jpackage --verbose`.

### Invalid `main class` or `main JAR`

**Cause:** Incorrect path relative to `--input`, missing main class in manifest, or invalid main class declaration.

**Resolution:** Inspect the JAR with `jar --list --file`, confirm the class has `public static void main(String[] args)`, and pass accurate `--main-jar`/`--main-class` values.

### Installer builds successfully but the application fails to run

**Cause:** Missing resources, runtime modules, JVM options, native libraries, or configuration paths.

**Resolution:** Run the app image before packaging the native installer; inspect launcher config, runtime `--list-modules`, and application logs.

### Application runs on the build machine but fails on a clean machine

**Cause:** The build machine has a JDK, `PATH`, environment variables, config files, or external dependencies not packaged by the installer.

**Resolution:** Test on a clean VM without a JDK, verify all resources/native dependencies, and use the bundled runtime.

### MSI does not upgrade the old version

**Cause:** Unstable `UpgradeCode`, version violating MSI rules, or changed upgrade configuration.

**Resolution:** Keep `--win-upgrade-uuid` consistent across the same product line, inspect the `Upgrade` table in the MSI, and test upgrading from the old version to the new version.

### Invalid signature or OS warnings

**Cause:** Unsigned artifact, untrusted certificate, missing/expired timestamp, or binary modified after signing.

**Resolution:** Sign during the release step with an appropriate certificate, verify the signature afterward, and do not modify binaries after signing. On macOS, verify code signing, Gatekeeper, and notarization per distribution requirements.

### Installs cleanly but uninstall leaves shortcuts/files behind

**Cause:** Files created outside the installer payload or the application writing data to locations not managed by the package.

**Resolution:** Distinguish installer-owned files from user data; add appropriate cleanup and confirm via uninstall testing on a clean VM.

## 17. Release Checklist

- [ ] Recorded JDK, `jpackage`, OS, and architecture.
- [ ] Checked `jpackage --help` on the build host.
- [ ] Verified `--type`, `--name`, `--app-version`, `--vendor`, and destination.
- [ ] Confirmed input JARs/modules and resources.
- [ ] Built and successfully ran the application image before packaging the installer.
- [ ] Runtime image has all required modules and native dependencies.
- [ ] Installer payload and metadata inspected with native tools.
- [ ] Signatures and certificates verified per release policy.
- [ ] SHA-256 checksum recorded in the release manifest.
- [ ] Clean install succeeded on the target VM.
- [ ] Launcher, shortcuts, file associations, and resources work.
- [ ] Upgrade from the previous version tested.
- [ ] Uninstall cleans up files/shortcuts properly and preserves necessary data.
- [ ] Logs, command line, and toolchain saved for reproducibility.
- [ ] Artifact tested on the target operating system/architecture.

`jpackage` produces distributable artifacts, but only testing on a clean environment confirms the installer works under conditions close to a user's machine. Verify the application image first, validate metadata and signatures with OS tools, and then run the full install, launch, upgrade, and uninstall flow before release.
