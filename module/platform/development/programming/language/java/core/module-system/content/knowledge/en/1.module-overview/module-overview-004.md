# Compiling, running, and distributing modular applications

A Java application using the Java Platform Module System (JPMS) goes through three interrelated stages: compiling source code into modules, running the modules on the module path, and packaging the necessary artifacts so users can deploy the application. At each stage, the Java compiler, JVM, and packaging tools rely on the module descriptor to understand module names, dependencies, and access boundaries.

This article uses JDK 21 and an example with two modules:

- `com.example.greeter`: a library providing a greeting API.
- `com.example.app`: the main application depending on the library.

The goal is to understand the workflow from source code to a runnable program, and then choose an appropriate distribution method.

## 1. Preparing a multi-module source structure

For a small application, the source code of each module can be placed in its own directory. Example:

~~~text
modular-demo/
└── src/
    ├── com.example.greeter/
    │   ├── module-info.java
    │   └── com/example/greeter/api/Greeter.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

The library descriptor:

~~~java
// src/com.example.greeter/module-info.java
module com.example.greeter {
    exports com.example.greeter.api;
}
~~~

The API class:

~~~java
// src/com.example.greeter/com/example/greeter/api/Greeter.java
package com.example.greeter.api;

public class Greeter {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

The application descriptor:

~~~java
// src/com.example.app/module-info.java
module com.example.app {
    requires com.example.greeter;
}
~~~

The main class:

~~~java
// src/com.example.app/com/example/app/Main.java
package com.example.app;

import com.example.greeter.api.Greeter;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println(new Greeter().greet(name));
    }
}
~~~

The example illustrates two different boundaries:

- Gradle/Maven or directory layout may treat these as two separate source projects/modules.
- JPMS treats them as two named modules because each module has `module-info.java`.
- `com.example.app` declares `requires com.example.greeter`, while the library module exports the package containing the API.

The module source directory names in the example match the module names for readability. This is a source layout convention; the actual module name is determined by the declaration in `module-info.java`.

## 2. Compiling multiple modules with javac

The Java compiler supports compiling one or more modules in a single invocation. The `--module-source-path` option specifies where module source code is located; `-d` specifies the output directory; `-m` or `--module` specifies the modules to compile.

From the `modular-demo` root directory, run:

~~~bash
javac --module-source-path src -d out -m com.example.greeter,com.example.app
~~~

Meaning of each part:

| Option | Role |
|---|---|
| `--module-source-path src` | Locate module sources under the `src` directory |
| `-d out` | Write bytecode into the `out` directory |
| `-m com.example.greeter,com.example.app` | Compile the two specified modules |

The compiler reads both modules' descriptors and checks dependencies and access rules. If the application imports a type from a package not exported by the library module, or if the application module has not declared a required dependency, the compiler reports an error.

After successful compilation, the output looks like:

~~~text
out/
├── com.example.greeter/
│   ├── module-info.class
│   └── com/example/greeter/api/Greeter.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Each direct subdirectory of `out` is a compiled module. `module-info.class` is the bytecode form of the module descriptor that Java tools use to identify the module.

### Compiling when dependencies are on the module path

If a module depends on an already compiled module or an external modular JAR, place the location containing the dependency on `--module-path`.

For example, if the `mods` directory already contains the library module:

~~~bash
javac --module-path mods --module-source-path src -d out -m com.example.app
~~~

The compiler will look for the `com.example.greeter` module in `mods` to compile `com.example.app`. The dependency must be present on the module path and the actual module name must match the name in the `requires` directive.

If the classpath is used instead of the module path, the compiler can compile in the traditional manner, but libraries on the classpath are then not treated as explicit named modules. Choose the right mechanism based on whether the application uses JPMS.

## 3. Running the application on the module path

After compilation, you can run directly from the module directories in `out`:

~~~bash
java --module-path out -m com.example.app/com.example.app.Main
~~~

Or pass arguments to the program:

~~~bash
java --module-path out -m com.example.app/com.example.app.Main Phuong
~~~

Parts of the command:

- `--module-path out` points to the location containing the compiled modules.
- `-m` or `--module` selects the module to launch.
- `com.example.app/com.example.app.Main` specifies the `com.example.app` module and the package-qualified main class.

At startup, the JVM resolves the main module along with its required dependencies. The `com.example.app` module needs to read `com.example.greeter`; the library's descriptor permits access to the `com.example.greeter.api` package. If a dependency is missing from the module path, the module name does not match, or the package is not exported, the program may fail to start or encounter class access errors.

### Distinguishing module path and classpath at runtime

The classpath is the traditional class-lookup mechanism. The module path is JPMS's module-lookup mechanism.

~~~bash
# Classpath model
java -cp libs/greeter.jar:app.jar com.example.app.Main

# JPMS model
java --module-path mods -m com.example.app/com.example.app.Main
~~~

The path separator in the classpath/module path depends on the operating system: Windows uses a semicolon (`;`), while Linux and macOS use a colon (`:`). The two commands above only illustrate Linux/macOS syntax; when running on Windows, substitute the appropriate separator.

Do not mix the two models arbitrarily. A modular application must ensure named modules are on the module path so the JVM can enforce descriptors. Legacy libraries without a module descriptor can still participate on the module path as automatic modules; if placed on the classpath, they belong to the unnamed module.

## 4. Packaging each module into a modular JAR

The post-compilation output directory can be run directly, but to distribute a library or application, we usually package modules into JARs.

Create a directory for artifacts:

~~~bash
mkdir -p mods
~~~

Package the library module:

~~~bash
jar --create --file mods/com.example.greeter.jar -C out/com.example.greeter .
~~~

Package the application module:

~~~bash
jar --create --file mods/com.example.app.jar --main-class com.example.app.Main -C out/com.example.app .
~~~

The `-C` option instructs the jar tool to change into the module's output directory before collecting files into the archive. Because the output contains `module-info.class`, the resulting JAR preserves the module descriptor and becomes a modular JAR.

The `--main-class` option records the main class for the artifact. When an explicit launch specification is needed, you can still specify both the module and main class using `-m module/class`.

After packaging:

~~~text
mods/
├── com.example.greeter.jar
└── com.example.app.jar
~~~

Run the modular JARs:

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

The JVM finds both modules in `mods`, reads their descriptors, and resolves dependencies. A directory containing multiple modular JARs can be used as a module path; there is no need to extract each JAR.

## 5. Inspecting JAR contents and descriptors

Before distribution, verify that the JAR contains the correct module descriptor and required packages/classes.

List archive contents:

~~~bash
jar --list --file mods/com.example.greeter.jar
~~~

View the module descriptor advertised by the JAR:

~~~bash
jar --describe-module --file mods/com.example.greeter.jar
~~~

The module description output typically shows the module name, packages, `requires` dependencies, and `exports` packages. This is a quick way to check the module name that Java tools recognize from the artifact.

Module-level dependencies can be inspected with:

~~~bash
jdeps --module-path mods --check com.example.app
~~~

The `jdeps` command helps analyze dependencies and certain module issues. Results depend on structure and JDK version; if the module has external dependencies, include them on the module path during analysis.

Java can be asked to validate modules on the module path:

~~~bash
java --validate-modules --module-path mods
~~~

These steps help catch packaging errors, missing modules, or invalid dependency configurations early. They do not replace functional testing of the application.

## 6. Running a modular JAR with a main class

There are two common ways to specify the entry point when running a module.

The explicit way, always naming both the module and the main class:

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

The way that only names the module:

~~~bash
java --module-path mods -m com.example.app
~~~

The second way requires the runtime to determine the module's default main class. The main class information can be set during packaging with `jar --main-class` as in the example above; with other packaging workflows, check the artifact's actual metadata. If no main class is declared or you want to avoid relying on that metadata, use the explicit `module/class` form.

A modular JAR is a module artifact. It is not necessarily a standalone application that can run without its dependency modules. If the application requires `com.example.greeter`, the corresponding JAR must still be present on the module path at startup.

## 7. Distributing modular applications

There are multiple levels of distribution, from providing JARs for an existing Java environment to creating a custom runtime or an OS-specific installer.

### 7.1. Distributing modular JARs

This is the simplest approach:

~~~text
distribution/
├── mods/
│   ├── com.example.app.jar
│   ├── com.example.greeter.jar
│   └── third-party-module.jar
└── README.txt
~~~

Recipients need a compatible JDK/JRE installed and run the documented command:

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Advantages:

- Small artifacts and easy to update individual modules.
- Dependencies are separated into distinct JARs.
- Suitable for internal applications, libraries, or environments where a Java runtime is already managed.

Items to prepare:

- Specify the minimum Java version and how to install the runtime.
- Supply all required dependency modules, including third-party dependencies.
- Document the launch command, arguments, and required configuration.
- Ensure module names are stable and match `requires` directives.
- Verify read permissions for files, configurations, and resources needed by the application in the deployment environment.

Do not assume users have the same working directory, environment variables, or Java configuration as the development machine.

### 7.2. Creating a custom runtime with jlink

If you want to distribute an application together with a Java runtime trimmed down to the required modules, `jlink` can be used. This tool builds a runtime image from resolved modules, including the necessary platform modules.

Example on Linux/macOS:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --output runtime-image
~~~

On Windows PowerShell, the module path separator is a semicolon:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output runtime-image
~~~

Meaning:

- `--module-path` supplies the JDK's platform modules and the application modules.
- `--add-modules com.example.app` selects the root module for the runtime image.
- `--output runtime-image` specifies the directory to hold the generated runtime.

`jlink` traverses the dependency graph to include the necessary modules in the runtime image. If the application requires a module that cannot be found, linking fails. Non-modular libraries or components needing special handling must be evaluated separately; `jlink` cannot arbitrarily package every classpath JAR as though it were a named module.

The newly created runtime image can be used to run the application:

~~~bash
runtime-image/bin/java --module-path mods -m com.example.app/com.example.app.Main
~~~

On Windows, the executable is located at `runtime-image/bin/java.exe`.

If you want to package the entire application into a deployment layout, organize the runtime image and the `mods` directory in a fixed layout, then test the launch command using the distributed runtime itself. Do not test only with the JDK on a development machine and assume the trimmed runtime will behave identically.

Advantages of `jlink`:

- Users do not have to install a separate full JDK.
- The runtime contains only the platform modules required by the application.
- Better control over the Java environment bundled with the application.

Limitations:

- The runtime image is tied to the target OS platform and architecture; separate builds are needed for each supported platform.
- Dependencies must be resolvable as appropriate modules.
- The runtime image must be tested after creation, especially for reflection, service loading, locales, charsets, and runtime features used by the application.

### 7.3. Creating an installer with jpackage

`jpackage` supports packaging a Java application into an application image or platform-dependent installer format, such as MSI/EXE on Windows, DMG/PKG on macOS, and DEB/RPM on Linux (depending on the OS, system tools, and JDK configuration).

Example creating an application image from modules:

~~~bash
jpackage \
  --name ModularDemo \
  --module-path mods \
  --module com.example.app/com.example.app.Main \
  --type app-image
~~~

If a runtime image has already been created with `jlink`, `jpackage` can be instructed to use that runtime:

~~~bash
jpackage \
  --name ModularDemo \
  --runtime-image runtime-image \
  --module-path mods \
  --module com.example.app/com.example.app.Main \
  --type app-image
~~~

To create an installer, replace `app-image` with a package type supported by the platform, such as `msi`, `exe`, `dmg`, `deb`, or `rpm`. Not every package type can be built on every OS; build and test on the target platform.

`jpackage` helps users install and launch the application in a way similar to a normal desktop application. It does not automatically fix dependency errors or guarantee compatibility across every operating system. Verify the icon, product name, version, installation directory, permissions, runtime, and upgrade/uninstall workflows against product requirements.

## 8. Third-party dependencies and non-modular libraries

Real-world applications commonly use external libraries. When distributing, determine whether each dependency is an explicit module, an automatic module, or a library used solely via the classpath.

Ways to inspect:

~~~bash
jar --describe-module --file libs/example-library.jar
~~~

If the JAR lacks a module descriptor, the tool can display the derived automatic module name. A module name derived from the file name can change if the JAR name changes; libraries can provide the `Automatic-Module-Name` manifest attribute to keep the name stable.

When a dependency sits on the module path, the application's descriptor must `requires` the exact module name. When a dependency is only used on the classpath, it belongs to the unnamed module and lacks an explicit descriptor to control packages like an explicit module.

When assembling a distribution package, you need to:

- Place all dependency JARs where the runtime can find them.
- Avoid having two different versions of the same library causing conflicts.
- Verify automatic module names and actual module names with JDK tools.
- Confirm which dependencies are needed at runtime and which are only for compile or test.
- Ensure licenses and redistribution terms of third-party libraries are satisfied.

The module descriptor does not manage library versions like a dependency manager. JPMS resolves module names and module relationships; Gradle/Maven remains the appropriate place to manage artifact versions, repositories, and dependency resolution.

## 9. Service loading and runtime images

If an application uses `ServiceLoader`, the consuming module must declare `uses` and the providing module must declare `provides ... with ...`. Provider modules must be present in the module resolution environment for services to be discovered.

When creating a runtime image, check whether providers are actually included in the image. Additional root modules can be specified when needed:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app,com.example.payment.card \
  --output runtime-image
~~~

The example above assumes `com.example.payment.card` is a provider module on the module path. The set of root modules to select depends on application design and service binding mechanisms; do not add modules by guesswork. Verify by running the features that use services on the created runtime image.

Reflection and resources also need to be tested in a trimmed runtime. Some frameworks rely on classpath scanning, reflection, or dynamic metadata; these behaviors may require additional module, resource, or runtime image configuration. If the application uses `opens`, confirm the descriptor was packaged properly and the framework module is present at runtime.

## 10. Common errors during compiling, running, and packaging

**Required module not found.** Check the module path, the module name shown by `jar --describe-module`, and the `requires` directive. Ensure the dependency is provided in both compile and runtime environments as appropriate.

**Package not exported.** If the application accesses an API from another module, check whether that package is exported in the providing module's descriptor. A public class in an unexported package is still not an API freely accessible from another named module.

**Running with classpath and expecting full JPMS enforcement.** If you want to verify readability and encapsulation of named modules, run with the module path and actual module descriptors.

**Packaging a JAR but forgetting module-info.class.** Check the list of files in the JAR and run `jar --describe-module`. If the descriptor is missing from the artifact, review the compile output and packaging command.

**JAR runs on the development machine but misses dependencies when distributed.** The development machine may have libraries in caches or custom environment settings. Assemble a distribution directory from identified artifacts, then run with the exact command users will execute.

**Main class not found.** Check the fully qualified class name, the module containing the main class, the `--main-class` declaration during packaging if launching by module name alone, or specify `module/class` explicitly.

**jlink reports module not found.** Check whether `--module-path` includes the JDK `jmods` and the application modular JARs. Inspect the dependency graph and ensure root modules are specified properly.

**Application behaves differently on the runtime image.** Check service providers, resources, locales, charsets, reflection, native libraries, and required platform modules. A trimmed runtime image must be tested as a separate deployment product.

**Installer only builds on certain machines.** `jpackage` depends on the target platform and OS packaging tools. Build the installer on the target platform and test installation, launch, upgrade, and uninstallation.

## 11. Recommended deployment workflow

A repeatable workflow for modular applications:

1. **Design modules:** name modules, separate API/internal packages, and declare `requires`, `exports`, `opens`, `uses`, and `provides` as needed.
2. **Compile:** use `javac --module-source-path` or build tool configuration so the compiler handles the module path properly.
3. **Run from output:** launch with `java --module-path ... -m module/class` to verify module resolution.
4. **Package:** create a modular JAR for each module to be distributed.
5. **Inspect artifacts:** use `jar --list`, `jar --describe-module`, `jdeps`, and `java --validate-modules` where appropriate.
6. **Choose distribution format:** JARs for managed Java environments; `jlink` when a custom runtime image is needed; `jpackage` when an application image or installer is needed.
7. **Test in a clean environment:** run from a freshly assembled distribution directory, without relying on classpath, caches, or environment variables that only exist on the development machine.
8. **Document:** record Java version, supported platforms, installation steps, launch command, arguments, configuration, and update procedures.

The distribution format should be chosen according to the users and deployment environment. A library used in a Java-managed system may only need a modular JAR. An internal application needing a consistent runtime can use `jlink`. A desktop application for end users may need `jpackage` to provide an OS-appropriate installer.

## 12. Self-check

Before considering a modular release ready, answer:

1. Does every source module have its descriptor in the right place?
2. Has the compiler compiled all required modules and checked dependencies?
3. Do the modules run via the module path in a clean environment?
4. Does the modular JAR contain `module-info.class` and the right packages/classes?
5. Do module names in `requires` match the actual names of dependencies?
6. Have third-party libraries been properly classified as explicit modules, automatic modules, or classpath dependencies?
7. If using `jlink`, does the runtime image include all needed platform modules, service providers, and resources?
8. If using `jpackage`, has the installer been built and tested on the target operating system?
9. Does distribution documentation state the Java version, run command, configuration, and required dependencies?

Compiling, running, and distributing are three continuous stages of a modular application. The compiler checks source code and module relationships; the JVM resolves modules at launch; tools like `jar`, `jlink`, and `jpackage` turn the result into artifacts suited for deployment. Keeping the module descriptor, module path, and build dependencies consistent across these steps gives the application clear boundaries and makes it easier to package and operate.