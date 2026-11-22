# Packaging Java Applications with jpackage

**`jpackage`** is a JDK tool for packaging a Java application into an application image or a native installer suitable for the target operating system. The generated package can include a launcher, application files, dependencies, and a dedicated Java runtime, allowing users to install or run the application without installing a full JDK themselves.

`jpackage` was introduced in Java 14 as an incubator tool and became a standard tool in JDK 16. This guide uses common syntax for JDK 17 and later; specific options may vary across versions and platforms, so check `jpackage --help` for the JDK you are using.

## 1. What Problem Does jpackage Solve?

Normally, to run a Java application, users need a compatible Java runtime, must know how to configure the classpath or module path, and must run the `java` command themselves. This can make distributing applications to end users difficult.

`jpackage` automates many packaging tasks:

- Creating a launcher to start the application with a recognizable name.
- Bundling JARs, resources, and dependencies into an application image.
- Creating or using a dedicated runtime image for the application.
- Building OS-specific native installers.
- Embedding metadata such as name, version, vendor, and description.
- Supporting application icons, JVM options, default arguments, and additional launchers.

General workflow:

```text
Java source code
      |
      | javac / build tool
      v
JAR or modular application
      |
      | jpackage
      v
Application image
      |
      | jpackage --type msi / dmg / deb / ...
      v
Native installer
      |
      v
User installs and runs the application
```

`jpackage` performs packaging; it does not replace the source compilation step. Before running the tool, you must prepare a successfully built JAR, module, or application artifact.

## 2. Application Image and Native Installer

`jpackage` has two main output categories.

An **application image (`app-image`)** is a packaged application directory. It typically contains the launcher, application files, and required runtime. You can test running the image before creating an installer.

A **native installer** is a platform-specific installation package that integrates with the operating system's installer and software management mechanisms.

| Operating System | Application Image | Common Native Installers |
| --- | --- | --- |
| Windows | Application directory with `.exe` launcher | `.exe`, `.msi` |
| macOS | `.app` bundle | `.dmg`, `.pkg` |
| Linux | Application directory with launcher | `.deb`, `.rpm` |

Supported formats depend on the platform and JDK. Not every package type can be built on every operating system.

You should build and test `app-image` first. Once the launcher, runtime, and dependencies work properly, create the installer for users.

## 3. Checking jpackage and the Environment

Open a terminal and run:

```bash
jpackage --version
jpackage --help
```

If the command is not recognized:

- Verify that JDK 16 or later is installed.
- Verify that the JDK `bin` directory is in `PATH`.
- Verify that `JAVA_HOME` points to the JDK root directory.
- Open a new terminal after updating environment variables.

You can invoke `jpackage` directly from the JDK `bin` directory. To generate the default runtime image, the tool uses `jlink`; therefore, the JDK must include the tools and modules required for linking.

**Platform-specific packaging:** `jpackage` builds packages for the platform it is running on. Build installers on the target operating system and choose the right CPU architecture, such as x64 or ARM64. Do not treat Windows, macOS, and Linux packages as artifacts that can be arbitrarily cross-built from a single build machine.

## 4. Common jpackage Options

| Option | Purpose |
| --- | --- |
| `--type` | Selects the output type such as `app-image`, `msi`, `exe`, `dmg`, `pkg`, `deb`, or `rpm` depending on the platform |
| `--name` | Application and launcher name |
| `--dest` | Directory to place the output artifact |
| `--input` | Directory containing input JARs and resources for classpath applications |
| `--main-jar` | Main JAR, relative to the `--input` directory |
| `--main-class` | Class containing the main method |
| `--module-path` | Where to find modules for modular applications |
| `--module` | Startup module, optionally with the main class name |
| `--runtime-image` | Prebuilt runtime image, typically created with `jlink` |
| `--app-version` | Application version |
| `--vendor` | Application vendor |
| `--description` | Application description |
| `--icon` | Application icon in a platform-supported format |
| `--java-options` | Options passed to the JVM when the launcher runs |
| `--arguments` | Default arguments passed to the application |
| `--add-launcher` | Declares an additional launcher with its own configuration |
| `--resource-dir` | Directory containing custom resources for the packager |
| `--add-modules` | Specifies additional modules for the runtime image |
| `--jlink-options` | Additional options passed to `jlink` when creating the runtime image |

Not every option works with every package type. Run `jpackage --help` on the target operating system to see supported platform options and formats.

## 5. Preparing a JAR-Based Java Application

This example creates a simple classpath application to package into an application image.

Project structure:

```text
project/
  src/
    com/
      example/
        Main.java
  out/
  input/
  dist/
```

Create **`src/com/example/Main.java`**:

```java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from packaged Java app");

        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "]=" + args[i]);
        }
    }
}
```

Create the output directories if they do not already exist.

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force out, input, dist | Out-Null
```

**macOS/Linux:**

```bash
mkdir -p out input dist
```

Compile the source code:

```bash
javac -d out src/com/example/Main.java
```

Package into a JAR:

```bash
jar --create --file input/hello.jar --main-class com.example.Main -C out .
```

In this example, the JAR already has the `Main-Class` attribute; when running `jpackage`, we will also specify the main class explicitly so the packaging command is easy to read and inspect.

Inspect the JAR before packaging:

```bash
jar --list --file input/hello.jar
```

The listing should contain the class:

```text
com/example/Main.class
```

## 6. Creating an Application Image with --type app-image

From the `project` root directory, run:

```bash
jpackage --type app-image --input input --name HelloApp --main-jar hello.jar --main-class com.example.Main --app-version 1.0.0 --vendor "Example" --dest dist
```

Explanation:

- `--type app-image`: creates an application image.
- `--input input`: takes JARs and resources from the `input` directory.
- `--name HelloApp`: sets the application name.
- `--main-jar hello.jar`: selects the main JAR inside the input directory.
- `--main-class com.example.Main`: specifies the startup class.
- `--app-version 1.0.0`: attaches the application version.
- `--vendor "Example"`: sets the vendor name.
- `--dest dist`: writes the image into the `dist` directory.

For classpath applications, other JARs placed in the `input` directory are also packaged as dependencies. Keep the exact directory structure and filenames that the application expects.

`jpackage` creates a runtime image for the application if you do not pass `--runtime-image`. The bundled runtime lets the application run with its packaged Java environment, reducing reliance on a system-wide Java installation on the user's machine.

## 7. Running the Application Image

The launcher path depends on the operating system.

**Windows PowerShell:**

```powershell
.\dist\HelloApp\HelloApp.exe
```

**macOS:**

```bash
./dist/HelloApp.app/Contents/MacOS/HelloApp
```

You can open the bundle via Finder or with:

```bash
open dist/HelloApp.app
```

**Linux:**

```bash
./dist/HelloApp/bin/HelloApp
```

When running the example without arguments, the terminal output is:

```text
Hello from packaged Java app
```

An application image can contain its own runtime, launcher, and application directory. There is no need to invoke `java -cp` manually as when running a JAR directly; the launcher generated by `jpackage` is already configured to start the application.

On Windows, if the application is a console program and needs to display stdout/stderr in a terminal window, use the `--win-console` option when creating the image. GUI applications usually do not need this option.

## 8. Packaging External Dependencies

If the application uses additional JAR libraries, place them in the input directory alongside the main JAR.

Example:

```text
input/
  hello.jar
  lib/
    helper.jar
    logging.jar
```

The application's paths and classpath must match how the dependencies are packaged. For classpath applications, you can configure the main JAR's classpath in the manifest or build artifact to match the exact structure used by the launcher.

A common approach is to package all dependency JARs into the input directory according to project conventions and verify that the launcher can locate them after building the image.

If the project uses Maven or Gradle, create a distribution directory containing the main JAR and runtime dependencies using a dedicated build task, then pass that directory as `--input`. This keeps packaging repeatable and avoids accidentally picking up libraries that only exist on the development machine.

**Check:** if the application runs from the IDE but throws `ClassNotFoundException` after packaging, verify that the runtime dependencies were included in the artifact and that the launcher references the correct locations.

## 9. Packaging Modular Applications

For applications using JPMS, you can specify the module path and startup module instead of `--input` and `--main-jar`.

For example, suppose module `com.example.app` has been compiled into the `mods` directory:

```text
mods/
  com.example.app/
    module-info.class
    com/example/app/Main.class
```

Create the application image:

```bash
jpackage --type app-image --name ModularApp --module-path mods --module com.example.app/com.example.app.Main --dest dist
```

Where:

- `--module-path mods` points to compiled modules and modular dependencies.
- `--module com.example.app/com.example.app.Main` specifies the module and main class.
- `--name ModularApp` sets the launcher name.
- `--dest dist` sets the output location for the application image.

The module descriptor must properly declare `requires`, `exports`, `uses`, and `provides` according to the application design. All dependent modules must be resolvable on the module path.

For complex modular applications, inspect the module graph using `java`, `jdeps`, and `jlink` before packaging.

## 10. Creating a Custom Runtime Image with jlink

By default, `jpackage` creates a runtime image for the application via `jlink`. If you need exact control over runtime modules or already have a tested runtime image, you can build the image first and pass it to `jpackage` with `--runtime-image`.

Example with module `com.example.app`:

**macOS/Linux:**

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --output runtime
```

**Windows PowerShell:**

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output runtime
```

After creating the runtime image, verify it:

```bash
runtime/bin/java --list-modules
```

On Windows:

```powershell
.\runtime\bin\java.exe --list-modules
```

Pass the runtime to jpackage:

```bash
jpackage --type app-image --name ModularApp --module-path mods --module com.example.app/com.example.app.Main --runtime-image runtime --dest dist
```

When `--runtime-image` is used, `jpackage` uses the provided runtime image. Ensure the image contains all modules required by the application, targets the right architecture, and was built with a toolchain compatible with the target environment.

## 11. Passing JVM Options and Application Arguments

You can configure the launcher to always pass specific JVM options or application arguments.

Example:

```bash
jpackage --type app-image --input input --name HelloApp --main-jar hello.jar --main-class com.example.Main --java-options "-Dapp.mode=production" --java-options "-Xmx512m" --arguments "first-run" --dest dist
```

Meaning:

- `--java-options "-Dapp.mode=production"`: sets a system property for the JVM.
- `--java-options "-Xmx512m"`: sets the maximum heap size.
- `--arguments "first-run"`: passes a default argument to the application when the launcher runs.

In Java code, default arguments can be read through `args` in `main(String[] args)`. If the user passes additional arguments at runtime, check how the platform launcher combines them with the default configuration.

Do not place passwords, tokens, or secrets in `--java-options`, `--arguments`, or launcher configuration files, as these values may be stored in the artifact and remain readable.

## 12. Creating Native Installers on Windows

On Windows, `jpackage` can create `.exe` or `.msi` packages. These installer formats require the corresponding Windows packaging tools; the JDK requires a compatible WiX Toolset to build installer packages.

Example creating an MSI:

```powershell
jpackage --type msi --input input --name HelloApp --main-jar hello.jar --main-class com.example.Main --app-version 1.0.0 --vendor "Example" --win-menu --win-shortcut --win-dir-chooser --win-console --dest dist
```

Common Windows options:

| Option | Purpose |
| --- | --- |
| `--win-menu` | Creates a Start Menu shortcut |
| `--win-shortcut` | Creates a desktop shortcut |
| `--win-menu-group` | Chooses the Start Menu group |
| `--win-dir-chooser` | Allows choosing the installation directory |
| `--win-console` | Creates a console-enabled launcher |
| `--win-per-user-install` | Configures a per-user installation |
| `--win-upgrade-uuid` | Identifier for managing MSI upgrades |

To create an EXE package, change `--type msi` to `--type exe` if your JDK and Windows environment support that format.

Before releasing, test installation, execution, upgrade, and uninstallation on a clean Windows machine. For widely distributed applications, digitally sign the installer and verify the publisher identity according to your organization's release process.

## 13. Creating Native Installers on macOS

On macOS, `jpackage` supports formats such as `.dmg` and `.pkg`.

Example creating a DMG:

```bash
jpackage --type dmg --input input --name HelloApp --main-jar hello.jar --main-class com.example.Main --app-version 1.0.0 --vendor "Example" --mac-package-identifier com.example.hello --dest dist
```

Example creating a PKG:

```bash
jpackage --type pkg --input input --name HelloApp --main-jar hello.jar --main-class com.example.Main --app-version 1.0.0 --vendor "Example" --mac-package-identifier com.example.hello --dest dist
```

Common macOS options:

- `--mac-package-identifier`: reverse-DNS bundle identifier, for example `com.example.hello`.
- `--mac-package-name`: display name of the package where applicable.
- `--mac-package-signing-prefix`: identifier prefix used during signing.
- `--mac-sign`: requests signing the application/package with an appropriate signing identity.
- `--mac-signing-key-user-name`: selected signing identity.
- `--mac-signing-keychain`: keychain containing the certificate.
- `--mac-entitlements`: entitlements file for signing when needed.

Depending on your distribution workflow, macOS applications may require code signing and notarization. Successfully generating a DMG/PKG does not by itself prove the artifact satisfies Gatekeeper requirements or Apple's distribution policies. Sign, notarize, staple, and verify the artifact according to the appropriate release process.

## 14. Creating Native Installers on Linux

On Linux, `jpackage` can create `.deb` or `.rpm` packages, depending on the packaging tools available on the system.

Example creating a DEB:

```bash
jpackage --type deb --input input --name helloapp --main-jar hello.jar --main-class com.example.Main --app-version 1.0.0 --vendor "Example" --linux-package-name helloapp --linux-shortcut --dest dist
```

Example creating an RPM:

```bash
jpackage --type rpm --input input --name helloapp --main-jar hello.jar --main-class com.example.Main --app-version 1.0.0 --vendor "Example" --linux-package-name helloapp --linux-shortcut --dest dist
```

Common Linux options:

| Option | Purpose |
| --- | --- |
| `--linux-package-name` | Package name |
| `--linux-deb-maintainer` | Maintainer information for DEB packages |
| `--linux-package-deps` | System package dependencies |
| `--linux-app-release` | Package release number |
| `--linux-app-category` | Application category |
| `--linux-shortcut` | Creates a desktop shortcut when supported |
| `--linux-rpm-license-type` | License type for RPM packages |

To build a DEB, the build machine needs the corresponding Debian packaging tools; to build an RPM, it needs RPM build tools. Install the tools appropriate for your distribution and check the requirements of the JDK you are using.

Test the package on the target Linux distribution. OS package dependencies, native libraries, and CPU architecture can cause a package to work on the build machine but fail on another machine.

## 15. Creating Additional Launchers with --add-launcher

An application may need multiple launchers with different configurations, such as a default launcher and a launcher running in admin or diagnostic mode.

Create the configuration file **`admin-launcher.properties`**:

```properties
module=com.example.app/com.example.app.Main
java-options=-Dapp.mode=admin
arguments=--admin
```

For a modular application, pass the configuration file to `--add-launcher`:

```bash
jpackage --type app-image --name MainApp --module-path mods --module com.example.app/com.example.app.Main --add-launcher Admin=admin-launcher.properties --dest dist
```

`Admin` is the name of the additional launcher. Launcher configuration can declare a module or JAR entry point along with JVM options and default arguments appropriate for the application type.

Supported syntax and keys depend on the JDK version; see the `--add-launcher` section in `jpackage --help`. Do not copy a modular application's configuration to a classpath application without updating the entry point keys accordingly.

## 16. Icons, Metadata, and Custom Resources

You can add an icon and identity metadata to the package:

```bash
jpackage --type app-image --input input --name HelloApp --main-jar hello.jar --main-class com.example.Main --app-version 1.0.0 --vendor "Example" --description "Example Java application" --icon icons/hello.ico --dest dist
```

Icon formats depend on the operating system. For example, Windows typically uses `.ico`, macOS uses `.icns`, and Linux supports image formats suitable for the desktop environment. Use the exact format supported by your platform and JDK version.

`--resource-dir` lets you provide custom resources for the packager, such as templates or platform resources. Use it only when you need to override default resources, and verify the filenames required by the JDK.

Metadata should stay consistent across application name, release version, vendor, and identifier. Avoid changing names or identifiers arbitrarily between upgrades if the platform uses them to identify the installed application.

## 17. Verifying Artifacts After Packaging

After creating an image or installer, verify that the artifact works in a clean environment.

Verification steps:

1. Confirm that the `jpackage` command completes successfully and the artifact appears in the `--dest` directory.
2. Inspect the generated launcher and runtime.
3. Run the application from the application image without relying on a system-wide JDK.
4. Test core functionality, configuration files, resources, logging, and dependencies.
5. Install the native installer on a clean test machine or virtual machine.
6. Verify shortcuts, menu entries, installation path, permissions, and uninstallation.
7. Test updating/upgrading between two versions if the installer supports it.
8. Verify digital signatures and metadata before release.

A simple test is to run the application on a machine without a separate JDK installed. If the app-image works, it shows that the bundled runtime is sufficient for the tested execution path. You still need to test all application features and native dependencies.

## 18. Common Errors When Using jpackage

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `jpackage` is not recognized | Suitable JDK not installed or `PATH` is incorrect | Check `JAVA_HOME` and the `bin` directory |
| Main JAR not found | Incorrect `--main-jar` name or not inside `--input` | Check the relative path and input directory contents |
| Main class not found | Wrong package/class name or class file missing from JAR | Check manifest, `--main-class`, and `jar --list` |
| App runs in IDE but fails in image | Missing runtime dependencies or resources | Package all dependencies and retest the image |
| Runtime missing modules | Runtime image lacks modules needed by the app | Check `--add-modules`, module path, or build runtime with jlink |
| Cannot create MSI/EXE | Missing or incompatible WiX Toolset version | Install compatible WiX and check environment configuration |
| Cannot create DEB/RPM | Missing Linux packaging tools | Install the corresponding tools and check JDK requirements |
| Installer builds but fails on another machine | Different architecture, native libraries, OS version, or package dependencies | Build and test on the target platform |
| macOS warns about unverified app | Artifact not signed/notarized per distribution policy | Perform proper code signing and notarization |
| Output artifact already exists | Destination directory contains an artifact with the same name | Use a new destination directory or manage old artifacts in the build process |

When diagnosing issues, keep the full command log and check `jpackage --help` output on the exact JDK being used. An option may be supported on one platform and unavailable on another.

## 19. Best Practices for Packaging and Release

- Build the application with a repeatable process, such as Maven or Gradle.
- Keep input artifacts separate from the jpackage output directory.
- Build and test `app-image` before creating an installer.
- Package all required runtime dependencies and resources.
- Use a minimal, tested runtime image when you want strict control over included modules.
- Record the JDK version, operating system, architecture, and package type in the release process.
- Build installers on the target operating system.
- Digitally sign the application and installer according to platform policies.
- Test installation, execution, upgrades, and uninstallation on a clean environment.
- Do not embed secrets in the manifest, launcher properties, or JVM options.
- Store artifacts and checksums per the release process so distributed builds can be traced.

## 20. Key Takeaways

- `jpackage` packages Java applications into application images or native installers.
- You must build the JAR or modules first; `jpackage` does not compile Java source code.
- Use `--input` and `--main-jar` for classpath applications; use `--module-path` and `--module` for modular applications.
- `--type app-image` is useful for testing before creating an installer.
- If `--runtime-image` is not passed, `jpackage` creates a runtime image for the application; you can use `jlink` to customize the runtime.
- Installer formats depend on the platform: Windows `.msi`/`.exe`, macOS `.dmg`/`.pkg`, Linux `.deb`/`.rpm`.
- Platform-specific packaging tools are required, and builds should run on the target operating system.
- Always test artifacts on a clean environment before release.

Once you understand the workflow of building artifacts → creating an application image → creating a native installer → testing and signing for release, you can distribute Java applications with an appropriate launcher and runtime for end users.
