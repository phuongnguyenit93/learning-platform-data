# The jpackage Command in Java

## 1. What is jpackage?

**jpackage** is a JDK tool used to package Java applications into an application image or an OS-specific installer package. Its goal is to let end users install and launch the application like a standard desktop application, rather than having to install a JDK themselves and run the `java` command with a long classpath.

A package created with jpackage can include:

- The application's JAR or modules.
- Required libraries and resources.
- A dedicated launcher to start the application.
- A bundled Java runtime image so users do not have to install Java separately, if the packaging configuration includes a runtime.

jpackage uses **jlink** to create the runtime image when you do not provide an existing runtime. As a result, this tool bridges two important steps of the Java release process: creating an appropriate runtime and packaging the application into a distributable product.

jpackage was introduced into the JDK as an experimental tool in JDK 14–15 and became a standard tool starting in JDK 16. For new projects, you should use a JDK supported by your project and check the available options with `jpackage --help` for that specific version.

## 2. Two Main Output Modes

jpackage has two commonly used output groups:

| Mode | Output | Purpose |
|---|---|---|
| `app-image` | An application directory containing the launcher, payload, and runtime | Testing, running directly, or serving as input to create an installer |
| Native installer | An OS-specific installer package | Distribution, installation, and OS integration |

Common installer types:

| Operating System | Common Package Types |
|---|---|
| Windows | `.exe`, `.msi` |
| macOS | `.dmg`, `.pkg` |
| Linux | `.deb`, `.rpm` |

The package types you can create depend on the operating system, JDK version, and the platform's packaging tools. Run `jpackage --help` on your build machine to see the exact supported types.

**An application image is not an installer.** It is a packaged directory that can run the application. An installer adds installation, uninstallation, and OS integration workflows.

## 3. Prerequisites Before Packaging

Before running jpackage, prepare the following:

1. A JDK that includes the `jpackage` and `jlink` tools.
2. A compiled application JAR or a modular application.
3. All required runtime dependencies and resources.
4. Application name, version, icon, and metadata if needed.
5. Native OS packaging tools when creating an installer.

Check versions:

~~~powershell
java -version
javac -version
jpackage --version
jpackage --help
~~~

jpackage creates native packages for the platform it is running on. Build on the target operating system and architecture: create `.msi` or `.exe` on Windows, `.dmg` or `.pkg` on macOS, and `.deb` or `.rpm` on Linux. Do not treat jpackage as a cross-compiler for generating installers for other operating systems.

On Windows, creating `.exe` or `.msi` installers typically requires installing the WiX Toolset and configuring WiX tools so jpackage can find them. Linux and macOS also have their own packaging tool requirements. An application image is usually a convenient starting point to verify the structure and launcher before creating an installer.

## 4. General Syntax

Basic syntax:

~~~bash
jpackage [options]
~~~

Some important options:

| Option | Meaning |
|---|---|
| `--type` | Selects the output type, e.g., `app-image`, `exe`, `msi`, `dmg`, `pkg`, `deb`, `rpm` depending on the platform |
| `--name` | Name of the application or package |
| `--dest` | Destination directory for the output |
| `--input` | Directory containing the input files to package |
| `--main-jar` | Main JAR, with a path relative to the input directory |
| `--main-class` | Fully qualified main class if the JAR does not declare a suitable `Main-Class` |
| `--module-path` | Location containing the modules |
| `--module` | Main module and optional main class name |
| `--runtime-image` | Pre-built runtime image |
| `--add-modules` | Modules to include in the runtime |
| `--jlink-options` | Options passed to jlink |
| `--app-version` | Application version |
| `--vendor` | Vendor name |
| `--description` | Application description |
| `--icon` | Icon file in the platform-specific format |

Some rules:

- Choose **one of** `--main-jar` or `--module`; do not use both in the same packaging run.
- `--main-class` is only used with `--main-jar`.
- For modular applications, the main module must be on the `--module-path`.
- If `--runtime-image` is not provided, jpackage invokes jlink automatically to create the runtime.
- If you already have a suitable runtime image, use `--runtime-image` so jpackage copies that runtime into the application image.

You can use `@filename` to read options from an argument file. This is useful when the command line is long or when you want to save a packaging configuration for reuse.

## 5. Packaging a Non-Modular Application

Traditional Java applications are usually packaged from a main JAR. The JAR should declare `Main-Class` in its manifest, or you can specify the main class with `--main-class`.

Example structure:

~~~text
project/
  src/
    demo/
      Main.java
  classes/
  input/
    hello.jar
  output/
~~~

Create `src/demo/Main.java`:

~~~java
package demo;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from jpackage");
        System.out.println("args=" + String.join(",", args));
    }
}
~~~

Compile with Java 17:

~~~powershell
New-Item -ItemType Directory -Force classes,input,output
javac --release 17 -d classes src\demo\Main.java
~~~

Package into a JAR and declare the main class in the manifest:

~~~powershell
jar --create --file input\hello.jar --main-class demo.Main -C classes .
~~~

Create an application image on Windows:

~~~powershell
jpackage --type app-image --name HelloApp --app-version 1.2.3 --vendor Example --description "Demo application" --input input --main-jar hello.jar --dest output --win-console
~~~

`--main-jar hello.jar` is the JAR name relative to the `input` directory. The `--win-console` option creates a console launcher on Windows, which is suitable for programs that print output to the terminal. For GUI applications, this option is usually not needed.

On Linux or macOS, you can use the same application configuration without `--win-console`:

~~~bash
jpackage --type app-image \
    --name HelloApp \
    --app-version 1.2.3 \
    --vendor Example \
    --input input \
    --main-jar hello.jar \
    --dest output
~~~

On Windows, the generated application image has the following general structure:

~~~text
output/
  HelloApp/
    HelloApp.exe
    app/
      hello.jar
      HelloApp.cfg
    runtime/
      bin/
      lib/
~~~

Run the launcher on Windows:

~~~powershell
.\output\HelloApp\HelloApp.exe one two
~~~

Output:

~~~text
Hello from jpackage
args=one,two
~~~

The application image already includes its own runtime. Users do not need to invoke `java -jar` and do not need to install a separate JDK to run this package.

## 6. Packaging a Modular Application

For applications using JPMS, specify the main module and module path instead of the main JAR:

~~~bash
jpackage --type app-image \
    --name ModularApp \
    --module-path mods \
    --module com.example.app/com.example.app.Main \
    --dest output
~~~

Where:

- `--module-path mods` specifies the directory containing compiled modules or modular JARs.
- `--module com.example.app/com.example.app.Main` specifies the main module and main class.
- jpackage uses the module graph to create an appropriate runtime image via jlink if no separate runtime is provided.

Module dependencies must be present on the module path and must be resolvable. If the application uses service providers, reflection, or special resources, check which modules are included in the runtime and test running the application image before releasing.

Do not mix `--module` with `--main-jar`. Choose the packaging approach that matches your application structure.

## 7. Runtime Image and jlink

When `--runtime-image` is not specified, jpackage automatically runs jlink to create a runtime image. The generated runtime can be smaller than a full JDK because it only needs the modules required by the application and necessary runtime components.

You can adjust the modules included in the runtime with:

~~~bash
jpackage --type app-image \
    --name HelloApp \
    --input input \
    --main-jar hello.jar \
    --add-modules java.base,java.desktop \
    --dest output
~~~

Only add the modules your application actually needs. For example, a Swing or AWT application needs `java.desktop`; a program that only handles basic logic may only need the appropriate base modules.

### Creating a Custom Runtime with jlink

When you need fine-grained control over the runtime, run jlink first:

~~~bash
jlink --add-modules java.base --output custom-runtime
~~~

Then pass that runtime to jpackage:

~~~bash
jpackage --type app-image \
    --name HelloAppCustom \
    --input input \
    --main-jar hello.jar \
    --runtime-image custom-runtime \
    --dest output
~~~

With a custom runtime image, ensure that:

- The runtime is built for the correct target operating system and architecture.
- All modules required by the application are included.
- The runtime version is compatible with the application's bytecode and libraries.
- All necessary native components and configurations for the deployment environment are present.

If a custom runtime image is provided, jpackage copies that runtime into the application image instead of creating a new one with jlink.

### Customizing jlink Options

`--jlink-options` lets you pass options to jlink. For example:

~~~bash
jpackage --type app-image \
    --name HelloApp \
    --input input \
    --main-jar hello.jar \
    --jlink-options "--strip-debug --no-man-pages --no-header-files" \
    --dest output
~~~

These options affect the runtime image and do not replace application-identifying options such as `--main-jar` or `--module`. Check `jlink --help` and test the application after trimming the runtime to avoid omitting required modules or data.

## 8. Creating a Native Installer

Once the application image has been tested, you can create an installer from the existing image directory using `--app-image`.

Example on Windows:

~~~powershell
jpackage --type msi --name HelloApp --app-image output\HelloApp --dest installers --win-per-user-install --win-menu --win-shortcut
~~~

You can use `--type exe` instead of `msi` if you want an EXE installer format supported on the build machine. Common Windows options:

- `--win-per-user-install`: installs per user.
- `--win-menu`: creates a Start Menu entry.
- `--win-shortcut`: creates a shortcut.
- `--win-dir-chooser`: allows the user to choose the installation directory.
- `--win-menu-group`: group name in the Start Menu.
- `--win-console`: creates a console launcher for applications that need a terminal.

On Windows, the WiX Toolset is a common requirement for creating MSI/EXE installers. If jpackage reports that WiX or the corresponding tool cannot be found, install and configure the exact version supported by the JDK you are using.

Example on macOS:

~~~bash
jpackage --type dmg \
    --name HelloApp \
    --input input \
    --main-jar hello.jar \
    --dest installers
~~~

You can create a PKG package with `--type pkg` if you need that installer type. macOS has additional options for bundle identifier, application signing, and DMG configuration; option names and requirements depend on the JDK version.

Example on Linux:

~~~bash
jpackage --type deb \
    --name helloapp \
    --input input \
    --main-jar hello.jar \
    --dest installers
~~~

You can use `--type rpm` if the build system supports the RPM format. Linux has specific options such as package name, maintainer, category, dependencies, and shortcuts. Check `jpackage --help` on the target Linux distribution to see which packaging tools need to be installed.

jpackage does not automatically turn a single application image into installers for every operating system. Installers must be built and tested on the target platform.

## 9. Metadata, Icons, and Additional Resources

A good installer should have a consistent name, version, vendor, description, and icon.

Example:

~~~bash
jpackage --type app-image \
    --name InventoryClient \
    --app-version 2.4.0 \
    --vendor "Example Company" \
    --description "Inventory desktop client" \
    --copyright "Copyright 2026 Example Company" \
    --icon assets/app-icon.ico \
    --input input \
    --main-jar inventory.jar \
    --dest output
~~~

The icon format must match the platform, such as ICO on Windows and ICNS on macOS. Linux typically uses PNG. Check the platform documentation and icon dimensions before packaging.

Some other options:

- `--license-file`: includes a license file in the installer if supported by the platform.
- `--about-url`: application homepage or information page.
- `--install-dir`: subdirectory under the default installation location.
- `--app-content`: adds files or directories to the application payload.
- `--resource-dir`: overrides jpackage's default resources/templates when deep customization is needed.

`--input` places all files in the input directory into the application payload. Dependencies must be organized so the launcher can find them, such as via the main JAR's manifest `Class-Path` or the module path. jpackage does not replace Maven/Gradle for resolving dependency versions.

## 10. Creating Multiple Launchers for the Same Application

An application image can have additional launchers with different configurations using `--add-launcher`.

For example, create `admin.properties`:

~~~properties
main-jar=hello.jar
arguments=--mode=admin
java-options=-Xmx512m
description=Administrative launcher
~~~

Then run:

~~~bash
jpackage --type app-image \
    --name HelloApp \
    --input input \
    --main-jar hello.jar \
    --add-launcher Admin=admin.properties \
    --dest output
~~~

The main launcher uses the original command-line configuration; the `Admin` launcher receives the additional configuration from the properties file. You can create multiple secondary launchers by repeating `--add-launcher`.

Supported keys in launcher properties include:

- `main-jar`, `main-class`, `module`.
- `description`, `arguments`, `java-options`.
- `app-version`, `icon`.
- `win-console`, `win-shortcut`, `win-menu`.
- `linux-app-category`, `linux-shortcut`.
- `launcher-as-service` on supported platforms.

Supported keys depend on the platform and jpackage version. Run `jpackage --help` to check before using them.

## 11. Configuring File Associations and Installer Resources

jpackage supports describing file associations using a properties file. For example, `document.properties`:

~~~properties
extension=example
mime-type=application/x-example
description=Example document
~~~

Pass this file to the installer packaging command on Windows:

~~~powershell
jpackage --type exe --name ExampleEditor --input input --main-jar editor.jar --file-associations document.properties --dest installers
~~~

File associations require OS integration and may only apply when building an appropriate installer. Verify the result after installation on the target operating system; an application image alone does not guarantee that the OS has registered the file association.

The `--resource-dir` option is for cases where you need to replace default icons, templates, or packaging resources. Only use it when you genuinely need to customize the installer UI; keep the resource structure compatible with the jpackage version in use.

## 12. Verifying Output and Diagnostics

After packaging, do not just check that the jpackage command exited successfully. Verify the entire output:

1. The application image contains the launcher and runtime directory.
2. The payload contains the required JARs, dependencies, and resources.
3. The launcher runs from the output directory.
4. The application works without relying on a JDK installed on the build machine.
5. The installer installs, launches, and uninstalls properly.
6. The version, icon, shortcuts, and file associations display correctly.

Some diagnostic commands:

~~~powershell
jpackage --version
jpackage --help
jar --list --file input\hello.jar
Get-ChildItem -Recurse output
~~~

If the launcher fails to run, check the configuration file in the `app` directory, the bundled runtime, the main class, and dependencies. If errors occur during class loading, check the manifest `Class-Path` or module path before concluding that the runtime is missing.

When you need to keep intermediate files for investigation, you can use `--temp` pointing to a new or empty directory. If `--temp` is specified, the temporary directory is retained after packaging and you must clean it up manually when it is no longer needed.

## 13. Common Errors and Troubleshooting

### jpackage is not recognized

The usual cause is using a JRE instead of a JDK, or the JDK's `bin` directory is not in `PATH`. Check `java -version`, `jpackage --version`, and the actual path to the tool. You can invoke `jpackage` using the full path to the JDK's `bin` directory.

### Main class not found

For non-modular applications, confirm that the main JAR has a valid `Main-Class` manifest entry or provide `--main-class`. The class name must be fully qualified with its package and must not have a `.class` extension.

For modular applications, confirm that the module name and main class in `--module` are correct, and that the module is on the `--module-path`.

### Missing dependencies at runtime

jpackage can package files in the input directory, but it does not automatically resolve all project dependencies. Verify that dependency JARs are included in the payload and properly referenced via the manifest `Class-Path` or module path. Test the application image in a clean environment to catch dependencies accidentally picked up from the build machine.

### jlink fails to create the runtime

The module path may be missing dependencies, a module name may be incorrect, or the module graph may fail to resolve. Inspect with `jdeps`, `java --list-modules`, and `jlink --list-plugins` as needed. Make sure native or specialized modules are included in the runtime.

### Installer fails to build

Common causes include missing native packaging tools, invalid icon formats, invalid metadata, or options only supported on another operating system. Read the specific error message, check `jpackage --help` on the build machine, and install the required platform tools.

### Package works on the build machine but fails on another machine

The application image may be missing the runtime, dependencies, or resources. Test on a machine without a JDK installed, running the same OS and architecture as target users. Do not just run the JAR with `java -jar` and conclude that the installer is working.

### Package size is too large

The default runtime may include more modules than the application needs. Identify module dependencies, then trim them using `--add-modules` or build a custom runtime with jlink. After trimming, run through all application flows to catch any missing modules.

## 14. Recommended Release Workflow

A practical workflow can be divided into the following steps:

1. Compile and test the application using the target JDK.
2. Prepare the input directory containing the JAR, dependencies, and resources.
3. Create an application image using `--type app-image`.
4. Run the launcher in a clean environment without relying on the build machine's JDK.
5. Verify the runtime, logs, icon, and configuration.
6. Create the native installer on the target platform using `--app-image` or direct packaging.
7. Test installation, upgrade, launch, and uninstallation.
8. Sign the code according to the OS requirements if required by the product.
9. Archive the artifacts, checksums, JDK version, and build configuration to reproduce the release.

jpackage creates distributable packages; it does not provide an application auto-update system, manage runtime dependencies, or replace your organization's signing and release processes.

## 15. Pre-Release Checklist

- [ ] Verified JDK version and options using `jpackage --version` and `jpackage --help`.
- [ ] Selected the appropriate `app-image` or installer mode.
- [ ] Selected the appropriate `--main-jar` or `--module`.
- [ ] Accurately specified `Main-Class` or the main module.
- [ ] Included all required dependencies and resources in the payload.
- [ ] Runtime image contains all required modules and matches the target platform.
- [ ] Tested the launcher on a machine without a pre-installed JDK.
- [ ] Verified metadata, icon, version, and shortcuts.
- [ ] Built the installer on the correct operating system and architecture.
- [ ] Tested installation, execution, upgrade, and uninstallation.
- [ ] Signed the application/installer package if required.
- [ ] Saved checksums and build information for artifact reproducibility.
