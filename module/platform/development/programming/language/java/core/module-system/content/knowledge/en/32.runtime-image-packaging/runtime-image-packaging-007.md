# jpackage Combined with Modular Applications

## Objectives

After this lesson, you will be able to package a JPMS application using `jpackage`, create an app image for testing, create an OS-specific installer, understand how `jpackage` combines the module path with a runtime image, customize the launcher, and prepare a distributable artifact for end users.

## 1. What Problem Does jpackage Solve?

A modular application typically needs several components to run:

- The application module containing the main class.
- Library modules that the application declares via `requires`.
- A compatible Java runtime to execute bytecode and the module graph.
- Accompanying configuration files, resources, or data.
- A launcher so users can start the application without having to type a `java` command themselves.

If only one or more JARs are distributed, users usually have to install the right Java version themselves, configure the module path, and run the right main module. `jpackage` helps package the application into an application image or native installer, and can also generate a suitable runtime image using `jlink`.

Common output types:

- **Application image**: a directory containing the launcher and the runtime needed to run the application.
- **Native installer**: a platform-specific installation package, such as MSI/EXE on Windows, DMG/PKG on macOS, or DEB/RPM on Linux.

`jpackage` is a JDK tool. Use a JDK that supports `jpackage` and `jlink`, not just a stripped-down JRE. Modular applications are described via module descriptors; the tool can analyze dependencies to create an appropriate runtime image.

## 2. Preparing a Modular Application

For example, an application has two modules:

~~~text
project/
  src/
    com.acme.greeter/
      module-info.java
      com/acme/greeter/Greeter.java
    com.acme.app/
      module-info.java
      com/acme/app/Main.java
  mods/
~~~

Library module:

~~~java
// src/com.acme.greeter/module-info.java
module com.acme.greeter {
    exports com.acme.greeter;
}
~~~

~~~java
// src/com.acme.greeter/com/acme/greeter/Greeter.java
package com.acme.greeter;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Application module:

~~~java
// src/com.acme.app/module-info.java
module com.acme.app {
    requires com.acme.greeter;
}
~~~

~~~java
// src/com.acme.app/com/acme/app/Main.java
package com.acme.app;

import com.acme.greeter.Greeter;

public final class Main {
    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Java";
        System.out.println(Greeter.greet(name));
    }
}
~~~

Compile the modules into the `mods` directory:

~~~bash
javac -d mods --module-source-path src -m com.acme.greeter,com.acme.app
~~~

After compilation, `mods` contains two exploded modules with `module-info.class` and their corresponding classes. You can test the application before packaging with:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
Hello, Java
~~~

Once the application runs with the standard modular launcher, we can proceed to the packaging step.

## 3. Creating an Application Image for a Modular App

Core syntax:

~~~bash
jpackage --type app-image \
  --name AcmeGreeter \
  --dest dist \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

Explanation:

- `--type app-image` requests creating an application image instead of an installer.
- `--name AcmeGreeter` sets the application and launcher name.
- `--dest dist` specifies the destination directory for the artifact.
- `--module-path mods` points to the location containing the application modules and dependencies.
- `--module com.acme.app/com.acme.app.Main` selects the root module and main class.

The part before the slash is the module name; the part after is the fully qualified name of the main class. If the module already has a main class recorded in the module descriptor, you can specify the module without writing the class after the slash.

The output structure depends on the platform, but an application image typically contains the launcher, an application directory, and a runtime image. Users can run the launcher generated in the image without having to write a `java -m` command themselves.

On Windows, the command is usually written on a single line or using backticks when run in PowerShell. Single-line example:

~~~powershell
jpackage --type app-image --name AcmeGreeter --dest dist --module-path mods --module com.acme.app/com.acme.app.Main
~~~

## 4. Why Create an App Image Before an Installer?

An application image lets you verify an artifact close to the final distributable product before creating an installer.

After running `jpackage --type app-image`, check:

1. Does the launcher appear in the output?
2. Does the application start on a machine without a development setup?
3. Are all module dependencies packaged completely?
4. Are the required resources and configuration files found?
5. Do logging, file output, and data paths work in the new layout?

Do not assume the launcher's working directory is always the source directory or the current directory in your IDE. A packaged application should explicitly determine the location of resources, configuration directories, and data directories according to OS-appropriate conventions.

If the app image works properly, you can use the same module settings to build the installer.

## 5. Creating a Native Installer

Example on Windows:

~~~powershell
jpackage --type msi --name AcmeGreeter --app-version 1.0.0 --vendor "Acme" --dest dist --module-path mods --module com.acme.app/com.acme.app.Main
~~~

You can use `--type exe` if you want to create an EXE installer in a supported Windows environment.

Example on macOS:

~~~bash
jpackage --type dmg --name AcmeGreeter --app-version 1.0.0 --vendor "Acme" --dest dist --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Example on Linux:

~~~bash
jpackage --type deb --name acme-greeter --app-version 1.0.0 --vendor "Acme" --dest dist --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Linux can also create RPMs if the environment supports it:

~~~bash
jpackage --type rpm --name acme-greeter --dest dist --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Supported installer types depend on the platform and JDK version. The tool often requires corresponding OS packaging or signing utilities. Check the `jpackage` documentation for the JDK in use and install the native tools required by the platform.

A native installer is built for the current platform. To release for Windows, macOS, and Linux, build and test on each target platform or use an appropriate build machine for each operating system. `jpackage` is not an arbitrary cross-compilation tool for installers across operating systems.

## 6. jpackage and Runtime Images

If an existing runtime image is not specified, `jpackage` can invoke `jlink` to create a runtime image for the modular application. A runtime image helps eliminate the need for users to install a full JDK.

The module system provides the dependency graph from module descriptors. The tool can determine the application modules and required dependencies to build a suitable runtime. This is especially helpful when the application uses only a subset of the Java platform.

Options can be passed to `jlink` via `--jlink-options`. Example:

~~~bash
jpackage --type app-image \
  --name AcmeGreeter \
  --dest dist \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main \
  --jlink-options "--strip-debug --no-header-files --no-man-pages"
~~~

Options such as `--strip-debug`, `--no-header-files`, and `--no-man-pages` help remove some unnecessary components in the runtime image. Only enable options that match the application's debugging, native integration, and operational requirements.

If the application uses service providers and needs provider modules linked into the runtime image, consider `jlink`'s `--bind-services` option via `--jlink-options`. Thoroughly test the services needed by the application after creating a stripped-down image.

### Using a Custom-Built Runtime Image

You can create the runtime image yourself with `jlink` when you need control over which modules are included in the runtime:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.acme.app \
  --output runtime-image
~~~

The example above uses a colon on Linux/macOS. On Windows, replace it with a semicolon and use the corresponding JDK path.

Then, pass the created runtime image to `jpackage`:

~~~bash
jpackage --type app-image \
  --name AcmeGreeter \
  --dest dist \
  --runtime-image runtime-image \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

The runtime image must be compatible with the application and target platform, and must contain all required Java modules. If using a custom-built runtime image, check modules needed for the application, reflection, service loading, charsets, logging, and native integration before releasing.

## 7. Including Resources and Auxiliary Files in the Package

A real-world application often needs default configuration files, templates, licenses, or initial data. `--input` specifies a directory containing additional files to include in the package.

Example:

~~~text
project/
  mods/
  package-input/
    config/
      defaults.properties
    templates/
      welcome.html
~~~

Package:

~~~bash
jpackage --type app-image \
  --name AcmeGreeter \
  --dest dist \
  --input package-input \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

Files in the input directory are placed into the application image according to the tool's layout. Inspect the actual location in the image and use appropriate relative paths in the application.

Do not write user data into the installation directory because that directory may require administrator privileges or be replaced during upgrades. Data that changes during use should reside in an OS-appropriate user data directory.

You can use `--resource-dir` to provide custom resources for the packaging process itself, such as launcher templates or installer-specific configuration files. Distinguish resources used during package creation from application files needed at runtime.

## 8. Customizing the Launcher and Metadata

Some useful options:

| Option | Purpose |
| --- | --- |
| `--name` | Application and launcher name. |
| `--app-version` | Display version of the application/package. |
| `--vendor` | Publisher name. |
| `--description` | Application description in installer metadata if supported by the platform. |
| `--icon` | Application or installer icon in the format required by the platform. |
| `--arguments` | Default arguments passed to the application when the launcher runs. |
| `--java-options` | JVM options passed to the application's runtime. |
| `--add-launcher` | Creates an additional launcher with its own configuration from a properties file. |
| `--dest` | Output directory. |
| `--type` | Artifact type, such as `app-image`, `msi`, `dmg`, `deb`, or `rpm`. |

Example adding metadata and a JVM option:

~~~bash
jpackage --type app-image \
  --name AcmeGreeter \
  --app-version 1.2.0 \
  --vendor "Acme Software" \
  --description "Modular greeting application" \
  --java-options "-Dapp.environment=production" \
  --dest dist \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

`--java-options` is for JVM options, such as system properties, heap size, or required module openings. `--arguments` is for application arguments. Do not confuse these two groups: JVM options are processed by the Java runtime, whereas application arguments appear in `main(String[] args)`.

To create additional launchers, `--add-launcher` accepts a launcher name and a properties file describing the separate main module/class, arguments, or JVM options. This is useful when a product has multiple execution modes, such as a main UI and an administrative tool.

## 9. Integrating `--add-opens` and JVM Options

An older framework might need deep reflection into a specific package. When running with the `java` command, we usually add `--add-opens` directly to the JVM arguments. For a packaged application, JVM options can be configured via `--java-options`:

~~~bash
jpackage --type app-image \
  --name AcmeGreeter \
  --dest dist \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main \
  --java-options "--add-opens=java.base/java.lang=ALL-UNNAMED"
~~~

This option will be passed to the JVM of the generated launcher. Only add packages and target modules that are genuinely needed. If the framework is a named module, prefer the specific target module rather than `ALL-UNNAMED`.

If using a separate launcher configuration file with `--add-launcher`, JVM options can be managed per launcher. Verify that the options appear in the final launcher and test with the application image itself, because running from an IDE does not guarantee the packaged environment shares the same configuration.

## 10. Testing the Artifact Before Release

A practical workflow:

1. Compile the modules and verify module descriptors.
2. Test-run using `java --module-path ... --module ...`.
3. Create an app image using `jpackage --type app-image`.
4. Run the launcher from the app image on a clean machine or an environment close to end users.
5. Check resources, logs, data, JVM options, and update behavior.
6. Create the installer for the target platform.
7. Install, run, uninstall, and test upgrades if the product supports them.
8. Sign the artifact if required by the distribution workflow or operating system.

Do not just check that the `jpackage` command finishes successfully. An artifact can be produced yet still lack resources or have runtime errors that only appear on machines without a pre-installed JDK.

For native installers, check the package name, version, vendor, installation location, shortcuts/menu entries, and uninstall behavior according to platform conventions.

## 11. Common Errors

### Module not found or dependency unresolved

Check whether `--module-path` contains the root module and dependencies. Use `jar --describe-module` to view the actual module name in the JAR, and run the application with `java -p ... -m ...` before packaging.

### Main class not found

Check the `module/main-class` part in `--module`. The class name must be package-qualified. If the main class is omitted, the module must have a main class recorded in its descriptor.

### jlink fails to create runtime image

Check the module path, dependencies, JDK in use, and `jlink-options`. If the application uses native libraries or service providers, verify that the corresponding modules are included in the runtime image.

### Installer is not supported on the build machine

Some package types require native OS tools. Use a build environment matching the target platform and install the utilities required by the `jpackage` version. If you only need to inspect the app image, use `--type app-image` to separate runtime packaging issues from installer creation issues.

### Application cannot find files after installation

Do not assume the current working directory is the same as when running from an IDE. Inspect the application image layout, input file locations, and how the application resolves resources. For mutable files, use a user data directory instead of writing to the installation directory.

### JVM options have no effect

Confirm the options were passed via `--java-options` and are present in the right launcher. For `--add-opens`, verify that the source module, package, and target module match the reflection error message.

## Key Takeaways

`jpackage` packages a modular application into an app image or native installer. For modular apps, use `--module-path` to point to modules and `--module module/main-class` to select the entry point. If no runtime image is provided, the tool can use `jlink` to create an appropriate runtime; you can supply a custom-built image with `--runtime-image`. Create and test an app image first, then build the installer on the target platform. Use `--java-options` for JVM options and `--arguments` for application arguments.
