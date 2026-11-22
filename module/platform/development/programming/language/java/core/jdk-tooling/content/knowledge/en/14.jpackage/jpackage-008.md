# Runtime image in jpackage

`jpackage` is a JDK tool used to package Java applications into an application image or an OS-specific installer. Applications typically need a suitable Java runtime to run. A runtime image is a prepared runtime containing the required modules; `jpackage` can generate a runtime image automatically using `jlink` or use a pre-built runtime image via the `--runtime-image` option.

It is important to distinguish between three artifacts:

- **Runtime image:** a Java runtime linked from modules, typically created with `jlink`. It contains the Java launcher and the required runtime components.
- **Application image:** an application directory created by `jpackage --type app-image`. It contains the application launcher, application files, and the bundled runtime.
- **Installer:** an OS-specific installation package, such as MSI/EXE, DMG/PKG, DEB, or RPM. An installer is typically built from the same application and runtime configuration.

This guide uses JDK 17 or later and explains how to let `jpackage` generate a runtime automatically, how to provide a custom runtime, how to package modular and classpath applications, and how to verify the output before release.

## 1. What is a runtime image?

A runtime image is a directory containing a Java runtime linked for a specific set of modules. It typically includes:

- The Java launcher in the `bin` directory.
- The linked modules in the runtime.
- Native libraries and platform-specific support files.
- Required runtime configuration and data.

A runtime image can be created directly using `jlink`. For example:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods" --add-modules java.base,java.logging --output runtime
~~~

This command creates the `runtime` directory with the selected modules and their required dependencies. You can inspect the modules included in the image with:

~~~powershell
.\runtime\bin\java.exe --list-modules
~~~

On Linux/macOS:

~~~bash
./runtime/bin/java --list-modules
~~~

A runtime image does not necessarily contain your application. It provides the Java environment for the application to run. `jpackage` bundles both the application and the runtime into an application image or installer.

## 2. Distinguishing between a runtime image and an application image

These two concepts are often confused:

| Artifact | Created by | Main contents | Purpose |
|---|---|---|---|
| Runtime image | `jlink` or generated internally by `jpackage` | Java runtime and required modules | Provides the Java execution environment |
| Application image | `jpackage --type app-image` | Application launcher, application, resources, and runtime | Runs the application without requiring a separate Java installation |
| Installer | `jpackage` with an OS package type | Application image along with installation metadata | Installation, shortcut creation, and OS integration |

An example application image structure might look like:

~~~text
ExampleApp/
├── app/
│   ├── ExampleApp.cfg
│   └── app.jar or application modules
├── runtime/
│   ├── bin/
│   └── lib/
└── bin/
    └── application launcher
~~~

The exact structure varies by operating system and application type. On macOS, an application image is typically a `.app` bundle; on Windows and Linux, the image directory has its own launcher in the corresponding structure.

An application image is an artifact that can be tested and distributed as a directory. An installer is an additional packaging layer that installs the application image onto the user's machine.

## 3. How does jpackage create a runtime image?

When creating an application image or installer without specifying `--runtime-image`, `jpackage` can invoke `jlink` to build a runtime tailored to the application.

For modular applications, `jpackage` can determine dependencies from the module descriptor and build the runtime based on the module graph.

For classpath applications, the tool can analyze the application's dependencies to determine the required platform modules. When automatic analysis is insufficient, additional modules can be specified using the corresponding runtime options.

Some related options:

| Option | Role |
|---|---|
| `--add-modules` | Specifies modules to include in the runtime image when `jpackage` creates the runtime |
| `--bind-services` | Links required service providers |
| `--jlink-options` | Passes additional options to `jlink` |
| `--runtime-image` | Uses a pre-built runtime image |
| `--module-path` | Specifies where to find application modules or dependencies |
| `--module` | Specifies the main module and main class |

`--jlink-options` is used to fine-tune the automatically generated runtime image, such as stripping debug information or man pages. Check `jpackage --help` for the JDK version you are using to see the exact list of options and defaults for that version.

If you need control over the module set, service binding, or how the runtime is built, create a dedicated runtime using `jlink` and pass it to `jpackage` via `--runtime-image`.

## 4. Packaging a modular application with a custom runtime

A modular application has a `module-info.java` file. The following example creates the `com.example.app` module.

Project structure:

~~~text
project/
├── src/
│   ├── module-info.java
│   └── com/
│       └── example/
│           └── app/
│               └── Main.java
├── mods/
├── runtime/
└── packages/
~~~

Contents of `src/module-info.java`:

~~~java
module com.example.app {
    requires java.logging;
}
~~~

Contents of `src/com/example/app/Main.java`:

~~~java
package com.example.app;

import java.util.logging.Logger;

public class Main {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger(Main.class.getName());
        logger.fine("Application started");

        String target = args.length == 0 ? "jpackage" : String.join(" ", args);
        System.out.println("Hello from " + target + "!");
    }
}
~~~

Compile the module using JDK 17 or later:

~~~powershell
New-Item -ItemType Directory -Force -Path mods/com.example.app, packages | Out-Null
javac -d mods/com.example.app src/module-info.java src/com/example/app/Main.java
~~~

You can run the module before packaging:

~~~powershell
java --module-path mods --module com.example.app/com.example.app.Main "modular app"
~~~

Output:

~~~text
Hello from modular app!
~~~

Create a custom runtime image with `jlink`:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --strip-debug --no-header-files --no-man-pages --output runtime
~~~

`jlink` resolves the dependencies of `com.example.app`, including `java.logging` and `java.base`, and creates the runtime image in `runtime`.

Use that runtime when packaging the application image:

~~~powershell
jpackage --type app-image --name ExampleApp --app-version 1.0.0 --module-path mods --module com.example.app/com.example.app.Main --runtime-image runtime --dest packages
~~~

The application image is created in the `packages` directory. On Windows, the launcher is typically located in the image directory with the application name and an executable extension; on Linux, the launcher is in the `bin` directory of the image; on macOS, the application is typically packaged as a `.app` bundle.

You can run the application image launcher and pass arguments to the application. For example, for a Windows image, the launcher path is typically:

~~~powershell
.\packages\ExampleApp\ExampleApp.exe "packaged app"
~~~

Output from the application:

~~~text
Hello from packaged app!
~~~

The launcher path varies by operating system. Inspect the actual structure inside `packages` rather than assuming all platforms use the same path.

## 5. Letting jpackage generate the runtime image automatically

You do not always need to invoke `jlink` manually. With a compiled application module, you can let `jpackage` create both the runtime image and the application image in a single command:

~~~powershell
jpackage --type app-image --name ExampleApp --app-version 1.0.0 --module-path mods --module com.example.app/com.example.app.Main --dest packages
~~~

In this case:

1. `jpackage` reads the application module and its dependency information.
2. The tool uses `jlink` to create the required runtime image.
3. The tool builds the application image with the launcher, application, and runtime.
4. The output is written to the destination directory.

This approach is suitable when module dependencies are fully declared and you do not need custom runtime tuning.

You can pass additional required modules or options for the runtime creation step using parameters supported by `jpackage`, such as `--add-modules`, `--bind-services`, and `--jlink-options`. Do not pass runtime creation options together with `--runtime-image` if they are incompatible with using a pre-built runtime; check the help output for your exact JDK version.

## 6. Packaging a classpath application

Applications that do not use a module descriptor can still be packaged with `jpackage`.

Example source `src/com/example/Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        String target = args.length == 0 ? "classpath app" : String.join(" ", args);
        System.out.println("Hello from " + target + "!");
    }
}
~~~

Compile and create the JAR:

~~~powershell
New-Item -ItemType Directory -Force -Path out, input, packages | Out-Null
javac -d out src/com/example/Main.java
jar --create --file input/app.jar --main-class com.example.Main -C out .
~~~

Package into an application image:

~~~powershell
jpackage --type app-image --name ClasspathApp --input input --main-jar app.jar --main-class com.example.Main --dest packages
~~~

Where:

- `--input` is the directory containing the main JAR and any dependency JARs/resources to package.
- `--main-jar` specifies the main JAR inside the input directory.
- `--main-class` specifies the class containing the `main` method if the manifest does not provide it or if you want to declare it explicitly.
- `--dest` is the directory that will contain the application image.

If the application depends on other JARs, place them in the `input` directory and test to ensure the launcher has the complete classpath.

For large classpath applications or those with complex dependencies, analyze dependencies beforehand with `jdeps` and confirm that the runtime image includes all required platform modules. If you need explicit control over the module set, create a dedicated runtime with `jlink` and pass it via `--runtime-image`.

## 7. Selecting a pre-built runtime image with --runtime-image

`--runtime-image` accepts the path to a pre-built runtime image, usually created with `jlink`. When using this option, `jpackage` packages the application with the specified runtime instead of generating a new one.

Example:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output runtime

jpackage --type app-image --name ExampleApp --module-path mods --module com.example.app/com.example.app.Main --runtime-image runtime --dest packages
~~~

Use a pre-built runtime when:

- You need to specify the exact modules included in the runtime.
- You need to use `jlink` with specialized options.
- You need to enable service binding for the application.
- You want to test the runtime independently before packaging.
- Multiple applications share a single verified runtime configuration.

The runtime image must be compatible with the target platform and contain sufficient modules for the application. Do not use a Windows runtime image to package a Linux application or vice versa. If the runtime contains native libraries, the CPU architecture must also match.

`--runtime-image` is not a path to a full JDK installation or the `jmods` directory. It must point to a validly created runtime image, typically containing `bin` and `lib` directories.

## 8. Creating an installer from an application image

`jpackage` supports creating application images and OS-specific installers.

| Operating system | Common output types |
|---|---|
| Windows | `app-image`, `exe`, `msi` |
| macOS | `app-image`, `dmg`, `pkg` |
| Linux | `app-image`, `deb`, `rpm` |

Example creating an MSI package on Windows:

~~~powershell
jpackage --type msi --name ExampleApp --app-version 1.0.0 --module-path mods --module com.example.app/com.example.app.Main --dest installers
~~~

Example creating a DEB package on Linux:

~~~bash
jpackage --type deb --name exampleapp --app-version 1.0.0 --module-path mods --module com.example.app/com.example.app.Main --dest installers
~~~

Example creating a DMG package on macOS:

~~~bash
jpackage --type dmg --name ExampleApp --app-version 1.0.0 --module-path mods --module com.example.app/com.example.app.Main --dest installers
~~~

Installer formats are only available on supported platforms and may require the corresponding OS packaging tools. For example, creating a DEB requires system tools that support the DEB format; creating MSI/EXE packages has specific requirements depending on the JDK and Windows environment.

`jpackage` is not a cross-compiler for building installers for every operating system from an arbitrary machine. Build and test packages on the target platform using the corresponding JDK and runtime image.

## 9. Configuring the launcher and runtime parameters

`jpackage` lets you configure how the launcher starts the application.

Some useful options:

| Option | Purpose |
|---|---|
| `--java-options` | Passes options to the JVM, such as `-Xmx1g` |
| `--arguments` | Default arguments passed to the application |
| `--add-launcher` | Creates an additional launcher with its own configuration |
| `--icon` | Sets the icon for the application or installer |
| `--resource-dir` | Specifies a directory containing custom resources |
| `--license-file` | Includes a license file in the packaging process |
| `--app-version` | Sets the application version |
| `--vendor` | Sets the vendor name |
| `--description` | Application description |

Example setting heap size for the JVM running the application:

~~~powershell
jpackage --type app-image --name ExampleApp --module-path mods --module com.example.app/com.example.app.Main --java-options "-Xms256m" --java-options "-Xmx1g" --dest packages
~~~

Distinguish between:

- `--java-options` affects the JVM running the application.
- `--arguments` are the arguments the application receives in the `args` array.
- Compiler JVM options, such as `javac -J-Xmx1g`, do not affect the heap of the packaged application.

You can create an additional launcher using a properties file. For example, `admin.properties`:

~~~properties
module=com.example.app/com.example.app.Main
java-options=-Xmx2g
arguments=--mode admin
~~~

Create the additional launcher:

~~~powershell
jpackage --type app-image --name ExampleApp --module-path mods --module com.example.app/com.example.app.Main --add-launcher Admin=admin.properties --dest packages
~~~

The `Admin` launcher has its own configuration. Check the properties syntax and supported values in the `jpackage` documentation for the JDK you are using.

## 10. Organizing resources and application data

The input directory of a classpath application can contain the main JAR, dependencies, and resources to be distributed. For modular applications, resources reside inside the module or are provided through an appropriate build configuration.

Do not assume that every file in the current working directory will be packaged automatically. Explicitly identify:

- Default configuration files.
- Resources, templates, and static data.
- Log files or writable data directories.
- Native libraries and external dependencies.
- License files and version information.

Applications should not write mutable data into the installation directory if the operating system or installation policy restricts write permissions. Use an application data location appropriate for the operating system and user.

If the application uses relative paths, verify the actual working directory when launched from the launcher generated by `jpackage`. Do not assume the working directory is always the source directory or project root.

## 11. Verifying the runtime image and application image

After creating a runtime image with `jlink`, check the modules:

~~~powershell
.\runtime\bin\java.exe --list-modules
~~~

Check the Java version of the runtime:

~~~powershell
.\runtime\bin\java.exe -version
~~~

You can run the module directly using the runtime image:

~~~powershell
.\runtime\bin\java.exe -m com.example.app/com.example.app.Main
~~~

After creating an application image, verify:

- The application launcher is present.
- The bundled runtime directory is present if the configuration requires bundling a runtime.
- Required modules appear in the runtime.
- Configuration files, resources, and dependencies are placed in the correct locations.
- Arguments and JVM options are passed properly.
- The application runs on a clean machine without the project's JDK installed.

On Windows, use PowerShell to list the image contents:

~~~powershell
Get-ChildItem -Recurse packages/ExampleApp
~~~

On Linux/macOS:

~~~bash
find packages/ExampleApp -maxdepth 4 -type f
~~~

Launcher names and locations can vary by OS and packaging type. Use the actual file listing to determine the executable path.

## 12. Platform limitations and considerations

### 12.1. Runtime images are tied to OS and architecture

A runtime image contains native JDK binaries. Therefore, build the image for the target OS/architecture. You cannot use a Windows image as a runtime for a Linux application simply by renaming directories.

### 12.2. Native libraries must match the platform

If the application uses JNI or native libraries, include the correct binaries for the target platform and test in the corresponding environment. Ensure that any native dependencies required by those libraries are also available.

### 12.3. Dynamically loaded modules must be added explicitly

`jlink` builds the runtime from the module graph and statically analyzable information. Reflection, plugins, services, or class names read from configuration may require modules to be added explicitly. Test actual features on the packaged runtime image.

### 12.4. Build tools differ from the user runtime

`jpackage` and `jlink` are JDK tools. The runtime image distributed to users typically contains only the runtime components needed to run the application, not necessarily these packaging tools.

## 13. Common errors when creating a runtime image or application image

| Symptom | Common cause | Resolution |
|---|---|---|
| `jpackage` is not recognized | `PATH` points to a JRE or JDK `bin` is not configured | Use an appropriate JDK and check `jpackage --version` |
| `Module ... not found` | Module path is missing the application module or a dependency | Check `--module-path`, `module-info.java`, and module names |
| `jlink` reports missing dependency | Root module lacks required modules on the module path | Analyze dependencies and add the missing modules |
| Application image is missing classes | Main JAR or dependencies were not included in input/module path | Check `--input`, `--main-jar`, `--module-path`, and JAR contents |
| Application runs with JDK but fails in image | Runtime image is missing modules, services, resources, or native libraries | Check `--list-modules`, service binding, and dynamic dependencies |
| Launcher cannot find configuration file | Relative paths rely on a different working directory than expected | Use an appropriate data path and test from the actual launcher |
| Installer creation fails | Missing OS packaging tools or wrong installer type | Check OS/tooling requirements and `jpackage --help` |
| Runtime image does not run on target machine | Image was built for a different OS/CPU or lacks native dependencies | Rebuild on the target platform and test |
| Application fails on modules loaded via reflection | Module is not included in the runtime image | Add the required modules and test dynamic loading paths |
| Installer has wrong version or icon | Metadata/resources were not configured properly | Check `--app-version`, `--icon`, `--resource-dir`, and vendor details |

## 14. Recommended release workflow

A reliable workflow can follow these steps in order:

1. Determine whether the application is modular or classpath-based.
2. Identify the target operating system and architecture.
3. Build the JAR or modules from source using the selected JDK.
4. Identify module dependencies, service providers, reflection usage, and native libraries.
5. Decide whether to let `jpackage` generate the runtime automatically or create a custom runtime with `jlink`.
6. Create the application image using `jpackage --type app-image`.
7. Test the launcher in a clean environment without relying on the build machine's installed JDK.
8. Verify resources, configuration, logs, arguments, heap settings, and native dependencies.
9. Build the platform-specific installer.
10. Test installation, upgrade, launch, and uninstallation on the target machine.

Creating and testing the application image before building the installer helps separate runtime/launcher issues from packaging-system-specific issues.

## 15. Pre-release checklist

- [ ] Determined whether the application is modular or classpath-based.
- [ ] Selected the target OS and architecture.
- [ ] Decided whether to let `jpackage` generate the runtime or pass `--runtime-image`.
- [ ] If using a custom runtime, created and verified it with `jlink`.
- [ ] Runtime includes all required modules, service providers, and dependencies.
- [ ] Verified launcher, application arguments, and `--java-options`.
- [ ] Packaged all JARs, dependencies, resources, and configuration files.
- [ ] Native libraries match the target platform and architecture.
- [ ] Tested the application image on a clean machine.
- [ ] Selected the appropriate installer format: MSI/EXE, DMG/PKG, DEB, or RPM.
- [ ] Tested installation, upgrade, execution, and uninstallation.
- [ ] Verified version, vendor, icon, and license metadata.

A runtime image provides a linked Java runtime for the application; an application image created by `jpackage` adds the launcher and application contents; an installer packages the application image for the operating system. For simple applications, let `jpackage` generate the runtime automatically if dependencies are fully resolved. When you need control over module closure, service binding, or runtime contents, build a separate image with `jlink` and pass it via `--runtime-image`. Always test both the application image and the installer on the actual target release platform.
