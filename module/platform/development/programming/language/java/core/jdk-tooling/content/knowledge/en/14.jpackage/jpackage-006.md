# Package Versioning with jpackage

`jpackage` is the JDK tool used to package Java applications into an application image or native installers for Windows, Linux, and macOS. When releasing multiple versions, you need to set the package version clearly so users can identify the installed version, the operating system can manage upgrades, and the development team can distinguish between releases.

The central option is `--app-version`. However, the application version, the Linux package revision, and the product-line identifier on Windows/macOS are different pieces of information. Understanding each value correctly helps avoid setting the wrong version or breaking the upgrade flow.

This lesson uses JDK 21 syntax as the baseline.

## 1. Distinguishing Different Types of Versions

| Value | Meaning | Tool / Option |
|---|---|---|
| Application / package version | The packaged product version, e.g. `2.4.1` | `jpackage --app-version` |
| Tool version | The version of the `jpackage` program in the running JDK | `jpackage --version` |
| Linux package revision | The RPM/DEB packaging revision, e.g. `2` | `--linux-app-release` |
| Windows upgrade identity | UUID identifying a family of related products for Windows Installer upgrades | `--win-upgrade-uuid` |
| macOS application identifier | Stable identifier of the application in the macOS ecosystem | `--mac-package-identifier` |
| Version in source code / build | Version managed by Maven, Gradle, manifest, or the application itself | Separate build / metadata configuration |

These values are not interchangeable. For example, changing `--app-version` from `2.4.1` to `2.4.2` does not mean you should change the Windows upgrade UUID or the macOS application identifier.

## 2. Using --app-version

Syntax:

~~~text
jpackage --app-version version [other-options]
~~~

`--app-version` specifies the version of the application and/or package. If not specified, JDK 21 defaults the version to `1.0`.

Example:

~~~bash
jpackage --name DynamicTreeDemo \
  --app-version 2.0 \
  --input myApps \
  --main-jar DynamicTree.jar
~~~

In this example:

- `--name DynamicTreeDemo` sets the application/package name.
- `--app-version 2.0` sets the product version.
- `--input myApps` specifies the directory containing the application contents.
- `--main-jar DynamicTree.jar` selects the main JAR.

The package name is generated from the application name and version. Oracle documentation illustrates the resulting output as `DynamicTreeDemo-2.0.exe` when creating a Windows package.

### 2.1. Default Version

If you run:

~~~bash
jpackage --name VersionDemo \
  --input input \
  --main-jar VersionDemo.jar
~~~

without providing `--app-version`, the package uses the default version `1.0`.

When you want to release a new version, specify the version explicitly:

~~~bash
jpackage --name VersionDemo \
  --app-version 2.4.1 \
  --input input \
  --main-jar VersionDemo.jar
~~~

Do not rely on the default version in a release pipeline, because the artifact name and package metadata may not reflect the actual product version.

### 2.2. --version vs. --app-version

These two options serve completely different purposes:

~~~bash
jpackage --version
~~~

This command prints the version of the `jpackage` tool and exits.

~~~bash
jpackage --app-version 2.4.1 --help
~~~

`--app-version` is product metadata used when creating the package; it does not change the JDK version or the tool version.

When inspecting a build, you can record both:

~~~bash
java --version
jpackage --version
~~~

This way, CI logs show which JDK/toolchain produced the artifact and which product version was requested.

## 3. Choosing a Versioning Convention for the Application

A common convention is `MAJOR.MINOR.PATCH`:

| Part | Common Meaning | Example |
|---|---|---|
| MAJOR | Major or incompatible changes | `3.0.0` |
| MINOR | Backward-compatible feature additions | `2.5.0` |
| PATCH | Backward-compatible bug fixes | `2.4.2` |

This is a project release-management convention, not an automatic algorithm enforced by `jpackage`.

Example release sequence:

- `2.4.0`: feature release.
- `2.4.1`: bug-fix release.
- `2.5.0`: compatible feature addition.
- `3.0.0`: major release.

You should choose a single source of truth for the version in your build configuration and pass that value into the `jpackage` command. Avoid having Maven/Gradle use `2.4.2` while the package carries version `2.3.0`.

### 3.1. Versions with Suffixes

Projects may use pre-release versions such as `2.5.0-rc.1` or build metadata such as `2.5.0+build.12`.

However, package version formats also depend on the operating system and native packaging tools. Do not assume that every SemVer suffix is accepted identically by Windows Installer, RPM, DEB, and macOS.

To have a value that works across platforms, you can use a numeric version such as `2.5.0` for `--app-version`, while recording release candidate, commit, or build number details separately in application metadata or the release system. If you need to use a suffix directly in the package version, test it on each target platform.

## 4. Application Version and Package Name

Some related options:

| Option | Role |
|---|---|
| `--name` | Application and package name |
| `--app-version` | Application/package version |
| `--vendor` | Vendor name |
| `--description` | Application description |
| `--copyright` | Copyright information |
| `--dest` | Directory for output artifacts |
| `--type` | Type of package to create |
| `--linux-package-name` | Package name on Linux |

Example:

~~~bash
jpackage --type app-image \
  --input input \
  --main-jar VersionDemo.jar \
  --name VersionDemo \
  --app-version 2.4.1 \
  --vendor "Example Studio" \
  --description "Versioning demonstration application" \
  --copyright "Copyright 2026 Example Studio" \
  --dest dist
~~~

This command creates an application image containing the launcher, the application, and the runtime image. You can use the application image to test before creating a native installer.

Common package types:

| Platform | Package Type |
|---|---|
| Windows | `exe`, `msi` |
| Linux | `deb`, `rpm` |
| macOS | `pkg`, `dmg` |
| Application image | `app-image` |

Native packages must be built on the target platform. To release for multiple operating systems, you must run the packaging process on each corresponding operating system.

## 5. Version and Revision on Linux

Linux package managers typically distinguish between the software version and the distribution package revision.

In `jpackage`, the option:

~~~text
--linux-app-release release
~~~

is used as:

- The `Release` value in the RPM spec.
- The Debian revision in the DEB control file.

Example:

~~~bash
jpackage --type deb \
  --input input \
  --main-jar VersionDemo.jar \
  --name VersionDemo \
  --app-version 2.4.1 \
  --linux-app-release 2 \
  --linux-package-name versiondemo \
  --dest dist
~~~

Here:

- `2.4.1` is the application version.
- `2` is the Linux package revision.
- `versiondemo` is the Linux package name.

### 5.1. When to Increment linux-app-release?

Suppose the application is still at version `2.4.1`, but the development team needs to rebuild the package due to changes in installation scripts or packaging metadata.

You can release:

| Packaging Run | Application Version | Linux Package Release |
|---|---|---|
| Initial build | `2.4.1` | `1` |
| Packaging script fix | `2.4.1` | `2` |
| Application bug fix | `2.4.2` | `1` |

The table above is an example project management convention. Follow the versioning/revision policy of the DEB or RPM repository where the product is published.

Do not use `--linux-app-release` as a substitute for the product version. If the software actually moves from `2.4.1` to `2.4.2`, update `--app-version`.

## 6. Versioning and Upgrades on Windows

Windows packages can use EXE or MSI. The option related to the upgrade line is:

~~~text
--win-upgrade-uuid id
~~~

This is the UUID associated with package upgrades. In Windows Installer, `UpgradeCode` is used to identify a group of related products across versions.

Example:

~~~powershell
jpackage --type msi `
  --input input `
  --main-jar VersionDemo.jar `
  --name VersionDemo `
  --app-version 2.4.1 `
  --vendor "Example Studio" `
  --win-upgrade-uuid "12345678-1234-5678-9abc-def012345678" `
  --dest dist
~~~

When releasing version `2.4.2` of the same product, you normally keep the same upgrade UUID:

~~~powershell
jpackage --type msi `
  --input input `
  --main-jar VersionDemo.jar `
  --name VersionDemo `
  --app-version 2.4.2 `
  --vendor "Example Studio" `
  --win-upgrade-uuid "12345678-1234-5678-9abc-def012345678" `
  --dest dist
~~~

Guidelines:

- Keep the UUID stable for the same product line that Windows Installer should recognize as related versions.
- Use a different UUID when creating an independent product or product family.
- Increment `--app-version` when releasing a new application version.
- Do not generate a different random UUID for each update if you want to maintain the same upgrade family.

The upgrade UUID identifies product relationships. It is not a version, not a filename, and does not by itself guarantee that every upgrade scenario will succeed. Test fresh installation, upgrades, and uninstallation with the exact MSI/EXE installer your product ships.

## 7. Versioning and Identifiers on macOS

On macOS, `jpackage` supports `pkg` and `dmg` packages.

The option:

~~~text
--mac-package-identifier identifier
~~~

sets a unique identifier for the application. If not specified, the default value is based on the main class name.

Example:

~~~bash
jpackage --type pkg \
  --input input \
  --main-jar VersionDemo.jar \
  --name VersionDemo \
  --app-version 2.4.1 \
  --mac-package-identifier com.example.versiondemo \
  --dest dist
~~~

You should use a stable reverse-DNS identifier, such as `com.example.versiondemo`, and keep it unchanged across releases of the same application.

Distinguish between:

- `--app-version 2.4.1`: the product version.
- `--mac-package-identifier com.example.versiondemo`: the application identity on macOS.
- `--name VersionDemo`: the displayed/packaged application name.

Do not change the identifier just because the application is upgraded from `2.4.1` to `2.4.2`. A new identifier can cause the operating system or management tools to treat the application as a different product.

## 8. Package Version Does Not Automatically Update Source Code Versions

`--app-version` sets the version for the packaging step. Do not treat it as a command that updates all other versions in the project.

A project may store its version in multiple places:

- Version in Maven `pom.xml`.
- Version in the Gradle build file.
- Version in the JAR filename.
- Version in the application manifest or resources.
- Module version in `module-info.java` or module metadata.
- Version displayed in the application's About window or logs.
- Package version set by `jpackage --app-version`.

If each place is entered manually, the values can drift out of sync.

You should choose a single version source in the build pipeline, then pass that same value to every required step. For example, the pipeline reads `2.4.1` from the `APP_VERSION` variable to:

1. Assign the version to the Maven/Gradle artifact.
2. Write the version into the manifest/resources if the application needs to display it.
3. Set `--app-version` when running `jpackage`.
4. Set the platform-specific package revision or upgrade identifier.
5. Record the version and checksum in the release manifest.

Example shell command using an environment variable:

~~~bash
APP_VERSION=2.4.1

jpackage --type app-image \
  --input input \
  --main-jar VersionDemo.jar \
  --name VersionDemo \
  --app-version "$APP_VERSION" \
  --dest dist
~~~

In PowerShell:

~~~powershell
$env:APP_VERSION = "2.4.1"

jpackage --type app-image `
  --input input `
  --main-jar VersionDemo.jar `
  --name VersionDemo `
  --app-version $env:APP_VERSION `
  --dest dist
~~~

Make sure the version variable is derived from a reliable tag or release metadata and recorded in the build logs.

## 9. Practice: Packaging a Versioned Application

Create the file `src/VersionDemo.java`:

~~~java
public final class VersionDemo {
    public static void main(String[] args) {
        System.out.println("VersionDemo 2.4.1");
    }
}
~~~

Create the input directories and compile:

~~~bash
mkdir -p build/classes input
javac -d build/classes src/VersionDemo.java
jar --create --file input/VersionDemo.jar \
  --main-class VersionDemo \
  -C build/classes .
~~~

On Windows PowerShell, create the directories with:

~~~powershell
New-Item -ItemType Directory -Force build/classes,input | Out-Null
~~~

Inspect the JAR:

~~~bash
jar --list --file input/VersionDemo.jar
~~~

The output may include:

~~~text
META-INF/
META-INF/MANIFEST.MF
VersionDemo.class
~~~

Create the application image:

~~~bash
jpackage --type app-image \
  --input input \
  --main-jar VersionDemo.jar \
  --name VersionDemo \
  --app-version 2.4.1 \
  --vendor "Example Studio" \
  --dest dist
~~~

The application image contains the launcher, the JAR, and the runtime image generated by `jpackage`/`jlink`. Run the launcher inside the image directory to verify the application works. The program prints:

~~~text
VersionDemo 2.4.1
~~~

When you need to create a native installer, run the command for the target platform.

**Windows MSI:**

~~~powershell
jpackage --type msi `
  --input input `
  --main-jar VersionDemo.jar `
  --name VersionDemo `
  --app-version 2.4.1 `
  --win-upgrade-uuid "12345678-1234-5678-9abc-def012345678" `
  --dest dist
~~~

**Linux DEB:**

~~~bash
jpackage --type deb \
  --input input \
  --main-jar VersionDemo.jar \
  --name VersionDemo \
  --app-version 2.4.1 \
  --linux-app-release 1 \
  --linux-package-name versiondemo \
  --dest dist
~~~

**macOS PKG:**

~~~bash
jpackage --type pkg \
  --input input \
  --main-jar VersionDemo.jar \
  --name VersionDemo \
  --app-version 2.4.1 \
  --mac-package-identifier com.example.versiondemo \
  --dest dist
~~~

Native commands must be run on the target operating system with the required packaging tools installed. For example, JDK 21 documentation lists WiX 3.0 or later as a requirement for Windows packaging; Linux requires the corresponding DEB/RPM build tools; macOS requires platform tools when signing or customizing packages.

## 10. Verifying the Version After Packaging

Do not rely solely on the filename to conclude that the version is correct. Inspect the metadata inside the artifact and test installation.

### 10.1. Verifying the Version Requested in the Build Command

Record all details:

- JDK and `jpackage` version.
- `--app-version`.
- `--type`.
- `--name`.
- Platform-specific version/revision/upgrade options.
- Output filename or directory.

You can use `--verbose` to view more information during packaging:

~~~bash
jpackage --verbose --type app-image \
  --input input \
  --main-jar VersionDemo.jar \
  --name VersionDemo \
  --app-version 2.4.1 \
  --dest dist
~~~

### 10.2. Verifying Linux Package Metadata

For DEB:

~~~bash
dpkg-deb --field dist/versiondemo*.deb Package Version
~~~

For RPM:

~~~bash
rpm -qp --queryformat '%{NAME} %{VERSION}-%{RELEASE}\n' dist/*.rpm
~~~

Compare `VERSION` with the application version and `RELEASE` with the Linux package release you specified.

### 10.3. Verifying Windows and macOS

For MSI/EXE, inspect the installer metadata using a Windows Installer inspection tool or file properties, then test installing the new version on a machine with the previous version to confirm the upgrade flow.

For macOS, inspect the application bundle metadata in `Info.plist`, including the identifier and version information; then test installing the package on a system with the previous version to confirm the application is recognized properly.

Specific tools and metadata fields depend on the package format. The key point is to verify both the displayed version and the product identity used for upgrades.

## 11. Common Errors

| Symptom | Cause | Solution |
|---|---|---|
| Package always has version `1.0` | `--app-version` was not passed | Pass the release version explicitly |
| Ran `jpackage --version` but package name did not change | Checked the tool version instead of setting the application version | Use `--app-version` |
| Artifact name has the wrong version | `--app-version` is not sourced from the same value as the build version | Synchronize the version variable from the build pipeline |
| DEB/RPM has the right version but wrong revision | `--linux-app-release` was not set or has the wrong value | Separate the application version and package release |
| Windows does not recognize the new version as the same product | Upgrade UUID was changed or upgrade configuration is incorrect | Check `--win-upgrade-uuid` and Windows Installer configuration |
| macOS recognizes the application as a different app | Application identifier was changed | Keep `--mac-package-identifier` stable |
| Package builds successfully but does not install/upgrade as expected | Only checked the filename without testing the actual installer | Test fresh install, upgrade, and uninstall |
| Version with suffix is rejected by the package backend | Version format is incompatible with the platform | Use a version format supported by the package manager |
| Another machine shows a different version from the application | Package metadata and version in code differ | Synchronize versions across source/build/package |
| Cannot create native package | Missing packaging tools for the target OS | Install prerequisites and run on the appropriate platform |

## 12. Recommended Release Workflow

For each release, you can follow this sequence:

1. **Choose the application version:** determine the product version, e.g. `2.4.2`.
2. **Lock the version source:** read it from a Git tag or build variable to avoid manual entry in multiple places.
3. **Build the JAR/module:** compile, run tests, and produce the artifact.
4. **Create the application image:** run `jpackage --type app-image` to verify the launcher, runtime, and resources.
5. **Select the package type:** `msi`/`exe`, `deb`/`rpm`, or `pkg`/`dmg` depending on the platform.
6. **Set version metadata:** use `--app-version`.
7. **Set platform identity/revision:** keep the Windows upgrade UUID and macOS identifier stable; increment the Linux package release when a packaging revision is needed.
8. **Build the native package:** run on the target operating system.
9. **Inspect metadata:** read the version, revision, package name, and identifier from the artifact.
10. **Test upgrades:** test fresh installation, upgrading from the previous version, and uninstallation.
11. **Save the release manifest:** record the version, JDK version, package type, platform, checksum, and commit source.

## 13. Key Takeaways

- `--app-version` is the application/package version; the JDK 21 default is `1.0`.
- `--version` prints the version of the `jpackage` tool.
- The package name is generated based on the application name and version.
- Linux has a separate `--linux-app-release` option for the RPM Release or Debian revision.
- Windows has `--win-upgrade-uuid` to identify related package families during upgrades.
- macOS has `--mac-package-identifier` to provide a stable application identifier.
- The package version does not automatically synchronize versions in Maven, Gradle, manifests, or the application UI.
- Always build and test packages on the target operating system.

References:

- [The jpackage Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jpackage.html)
- [Packaging Tool User's Guide — Java SE 21, Basic Packaging and Package Metadata](https://docs.oracle.com/en/java/javase/21/jpackage/packaging-tool-user-guide.pdf)
- [Packaging Overview — Java SE 21](https://docs.oracle.com/en/java/javase/21/jpackage/packaging-overview.html)
- [Microsoft: Preparing an Application for Future Major Upgrades](https://learn.microsoft.com/en-us/windows/win32/msi/preparing-an-application-for-future-major-upgrades)