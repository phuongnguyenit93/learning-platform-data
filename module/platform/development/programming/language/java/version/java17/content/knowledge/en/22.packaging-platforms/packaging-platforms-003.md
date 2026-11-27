# Creating a Custom Runtime with jlink in Java 17

> **Topic:** Java 17  
> **Chapter:** Packaging and Platforms  
> **Objective:** Understand how `jlink` builds a custom runtime image from JDK and application modules; know how to prepare modules, identify dependencies, create launchers, inspect the image, and distribute an application with its own private runtime.

## 1. What Problem Does jlink Solve?

A Java application normally needs a Java runtime to execute. If you only distribute a JAR file, users must install a compatible runtime or set up the Java environment themselves. This can lead to:

- The target machine not having Java installed.
- The target machine running an incompatible Java version.
- The runtime containing more modules and components than the application actually needs.
- Runtime installation and configuration becoming the user's responsibility.

`jlink` is a JDK tool introduced in Java 9 alongside the Java Platform Module System (JPMS). It links the required modules to produce a custom **runtime image**. The image contains a runtime capable of running the application without requiring users to install a separate JDK.

For example, an application that only needs `java.base` and `java.logging` can be packaged with a runtime containing just those required modules, rather than requiring users to install a full JDK.

### 1.1. What Is a Runtime Image?

A runtime image is a structured directory containing the components needed to run an application on a specific platform, typically including:

- Runtime launchers such as `bin/java` and any application-created launchers.
- The linked runtime modules.
- Required native libraries and configuration files.
- Metadata and resources required by the runtime.

General layout example:

```text
my-runtime/
  bin/
    java
    keytool
    orders
  conf/
  include/       (may be absent if header files were stripped)
  legal/
  lib/
    modules
    server/
    security/
    ...
```

The actual directories and files depend on `jlink` options and the linked modules. Do not rely on the internal layout of the image to manually edit runtime files; regenerate the image using `jlink` whenever configuration changes.

### 1.2. jlink Does Not Produce a Standalone Native Executable

The runtime image contains launchers to start the Java application, but the application still runs on the JVM inside the image. This is not compilation of Java into a standalone single-file native executable.

Nor is the image a full JDK: it typically omits the `javac` compiler, debugger, and full development toolset. Its goal is to provide just enough runtime for the application.

### 1.3. jlink Works Only with Modules

Inputs to `jlink` are resolvable modules, such as:

- JDK modules, provided as JMODs in `$JAVA_HOME/jmods`.
- Modular JARs containing `module-info.class`.
- Exploded modules (compiled module directories containing `module-info.class`).
- JMODs created by the `jmod` tool or provided by the JDK.

A classpath-only JAR or an automatic module cannot be linked by `jlink` as an explicit module. Those dependencies need to be modularized or handled via an appropriate packaging strategy before building the image.

## 2. Requirements for Creating a Runtime Image

### 2.1. Using JDK 17

`jlink` ships with the JDK. Verify:

```bash
java -version
jlink --version
javac -version
```

Use JDK 17 to compile, analyze, and link an application targeting Java 17. If using another JDK, make sure you understand compatibility for class files, module descriptors, and linked runtime modules.

### 2.2. The Application Must Be an Explicit Named Module

A modular application typically has a `module-info.java` file. For example:

```java
module com.acme.orders {
    requires java.logging;
}
```

In this example, the application module is named `com.acme.orders` and declares a dependency on `java.logging`.

A module may also declare `exports` to expose packages, `opens` for reflection, or `uses`/`provides` for services. These declarations can affect the module graph that `jlink` needs to resolve.

### 2.3. Dependencies Must Also Be Module-Path Compatible

If the application uses third-party libraries, determine whether each library has a module descriptor:

| Dependency Type | Can Be Passed Directly to jlink? | Handling Approach |
|---|---|---|
| JDK module | Yes | Provided by the JDK as JMODs |
| Modular JAR with explicit descriptor | Yes | Place on the module path |
| Exploded module | Yes | Place the directory containing the module on the module path |
| Valid JMOD | Yes | Place on the module path |
| Automatic module | No | Modularize the dependency before linking |
| Classpath-only JAR | Not directly | Convert to a named module or package using another architecture |

Do not confuse a JAR being usable on the module path at runtime with that JAR being linkable by `jlink`. `jlink` requires explicit modules to construct a runtime image.

## 3. Creating a Simple Modular Application

Before using `jlink`, create a small application with a module descriptor to clearly see the module path and module graph.

### 3.1. Source Structure

Example:

```text
orders-app/
  src/
    com.acme.orders/
      module-info.java
      com/acme/orders/Main.java
```

Contents of `module-info.java`:

```java
module com.acme.orders {
    requires java.logging;
}
```

Contents of `Main.java`:

```java
package com.acme.orders;

import java.util.logging.Logger;

public class Main {
    private static final Logger LOGGER =
            Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        LOGGER.info("Orders application is running on Java "
                + Runtime.version());
    }
}
```

Module `com.acme.orders` declares `requires java.logging` because the code uses `Logger`. `java.base` is always read implicitly by every module, so `requires java.base` is not needed.

### 3.2. Compiling into an Exploded Module

From the `orders-app` root directory:

```bash
javac --module-source-path src -d mods -m com.acme.orders
```

After compilation, the layout looks like:

```text
mods/
  com.acme.orders/
    module-info.class
    com/acme/orders/Main.class
```

The `mods` directory serves as the module path containing the exploded module `com.acme.orders`.

### 3.3. Testing the Module Before Linking

Run the module with the current JDK:

```bash
java --module-path mods --module com.acme.orders/com.acme.orders.Main
```

Or use the short `-m` syntax:

```bash
java --module-path mods -m com.acme.orders/com.acme.orders.Main
```

The log output displays the message that the application is running along with the Java version. Testing first helps separate application/module errors from runtime image creation errors.

## 4. Creating a Runtime Image with jlink

### 4.1. Basic Syntax

General command:

```bash
jlink --module-path <module-path> --add-modules <root-module>[,<root-module>...] --output <runtime-image>
```

Core parameters:

- `--module-path`: where `jlink` searches for modules. Can include the JDK's JMOD directory, modular JARs, JMODs, and exploded modules.
- `--add-modules`: the root modules to include in the image. `jlink` resolves their dependencies according to module descriptors.
- `--output`: output directory for the runtime image.

### 4.2. Creating an Image on Linux/macOS

Assuming `JAVA_HOME` points to JDK 17 and the module sources are compiled into `mods`:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders --output build/orders-runtime
```

Here:

- `$JAVA_HOME/jmods` provides the JDK modules.
- `mods` provides the exploded application module.
- `com.acme.orders` is the root module.
- `jlink` automatically resolves explicit dependencies, including `java.logging` and the modules it requires.

### 4.3. Creating an Image on Windows PowerShell

On Windows, the module path separator is a semicolon:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.orders --output build\orders-runtime
```

If running in CMD, environment variable syntax and line continuation characters differ from PowerShell. Use the syntax appropriate for your shell.

### 4.4. Running the Application from the Runtime Image

The basic image already includes the runtime launcher. On Linux/macOS:

```bash
build/orders-runtime/bin/java --module com.acme.orders/com.acme.orders.Main
```

On Windows PowerShell:

```powershell
build\orders-runtime\bin\java.exe --module com.acme.orders/com.acme.orders.Main
```

This command runs the application module using the newly built runtime. Users do not need to point to a separately installed JDK if the image is distributed completely and matches the target system.

## 5. Creating a Custom Launcher for the Application

When distributing a runtime to end users, you should not require them to type the module name and main class every time. The `--launcher` option creates a dedicated launch command in the image.

### 5.1. Launcher Syntax

```text
--launcher <command-name>=<module>[/<main-class>]
```

Example:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders --launcher orders=com.acme.orders/com.acme.orders.Main --output build/orders-runtime
```

After linking, the image has an `orders` launcher in the `bin` directory. On Windows, the launcher has the platform-appropriate executable extension.

### 5.2. Running the Launcher

Linux/macOS:

```bash
build/orders-runtime/bin/orders
```

Windows PowerShell:

```powershell
build\orders-runtime\bin\orders.exe
```

The launcher invokes the main class of the specified module using the bundled runtime. This is a convenient way to distribute an application without requiring users to know module names or classpath/module path flags.

### 5.3. Adding Launchers for Multiple Entry Points

A runtime image can have multiple launchers if the application has multiple main classes/modules to run:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders,com.acme.admin --launcher orders=com.acme.orders/com.acme.orders.Main --launcher admin=com.acme.admin/com.acme.admin.Main --output build/acme-runtime
```

All root modules must be present on the module path and resolvable. Adding a launcher alone does not automatically pull an unresolved module into the image; you must include that module via `--add-modules` or the dependency graph.

## 6. How jlink Selects Modules for the Image

### 6.1. Root Modules and Dependency Closure

`--add-modules` specifies root modules. `jlink` builds a module graph from those roots and resolves required dependencies according to `requires` directives in descriptors.

For example:

```java
module com.acme.orders {
    requires java.logging;
    requires com.acme.money;
}

module com.acme.money {
    requires java.base;
}
```

When linking `com.acme.orders`, `jlink` resolves `java.logging` and `com.acme.money` along with their dependencies. `java.base` is the foundational module and is always included.

This is why a runtime image can be smaller than a full JDK: only modules in the required module graph are linked.

### 6.2. Adding Multiple Root Modules

If an application has multiple independent entry points or needs service provider modules not pulled in through normal dependencies, you can specify multiple roots:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders,com.acme.admin --output build/acme-runtime
```

The module list is comma-separated. Each module must be found on the module path and have a valid descriptor.

### 6.3. Limiting the Observable Module Set

`--limit-modules` restricts the universe of modules considered during resolution:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders --limit-modules java.base,java.logging,com.acme.orders --output build/orders-runtime
```

This option can be useful when you want explicit control over the module universe. However, the list must include every module needed to resolve the graph. If any dependency is missing, linking will fail.

Normally, starting with `--add-modules` and letting `jlink` resolve dependencies is sufficient. Only use `--limit-modules` when you have a specific requirement and understand the module graph.

## 7. Service Binding and ServiceLoader

An application may use the Java Service Provider Interface (SPI) to locate implementations at runtime via `ServiceLoader`. In JPMS, the consumer declares `uses` and the provider declares `provides ... with ...`.

Consumer module example:

```java
module com.acme.orders {
    requires java.base;
    uses com.acme.orders.spi.PaymentGateway;
}
```

Provider module:

```java
module com.acme.payments.card {
    requires com.acme.orders;
    provides com.acme.orders.spi.PaymentGateway
        with com.acme.payments.card.CardPaymentGateway;
}
```

In practice, `java.base` can be omitted from the descriptor because it is always read implicitly. The example retains it to emphasize the base module, though descriptors normally do not need to declare it.

If provider modules are not included in the dependency graph via ordinary resolution, the `--bind-services` option instructs `jlink` to bind service provider modules and their dependencies:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders --bind-services --output build/orders-runtime
```

When an application uses `ServiceLoader`, check:

- Whether the consumer module declares `uses` for the exact service type.
- Whether the provider module declares `provides` with a valid implementation.
- Whether the provider module is on the module path.
- Whether `--bind-services` is needed to include providers in the runtime image.
- Whether the provider's constructor or provider method satisfies `ServiceLoader` requirements.

`--bind-services` can enlarge the image because it pulls in providers and their dependencies. Enable it only when the application needs service binding or packaging policies require it.

## 8. Optimizing Runtime Image Size

Once the module graph is correct, you can use `jlink` options to reduce image size.

### 8.1. Stripping Debug Information

`--strip-debug` removes debug information from classes inside the image:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders --strip-debug --output build/orders-runtime
```

This reduces size but also reduces available debug information. If you need to debug a production runtime or inspect stack traces with line numbers for special diagnostics, weigh the trade-off before stripping.

### 8.2. Compressing Resources

The `--compress` option supports these levels in JDK 17:

| Value | Meaning |
|---|---|
| `0` | No compression |
| `1` | Constant string sharing |
| `2` | ZIP compression for resources in the image |

Example:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders --compress=2 --output build/orders-runtime
```

Compression can reduce storage footprint but may alter read/decompression overhead at runtime. Measure both image size and startup/runtime performance on realistic workloads.

### 8.3. Omitting Header Files and Man Pages

End-user runtimes usually do not need C/C++ header files or man pages:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders --no-header-files --no-man-pages --output build/orders-runtime
```

These two options omit:

- `--no-header-files`: header files used for native/JNI development.
- `--no-man-pages`: man pages.

They are well suited for deployment runtime images if the application does not need these docs/headers.

### 8.4. Combining Common Options

Example of a leaner image with a launcher:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders --launcher orders=com.acme.orders/com.acme.orders.Main --strip-debug --compress=2 --no-header-files --no-man-pages --output build/orders-runtime
```

Do not enable every plugin blindly by default. Clarify deployment goals, debuggability, and performance requirements before choosing.

### 8.5. Viewing Available Plugins

The list of plugins depends on the JDK version:

```bash
jlink --list-plugins
```

This command shows the plugins and options supported by the current `jlink` binary. It is a reliable reference for verifying exact syntax in JDK 17.

## 9. Analyzing Dependencies Before Linking with jdeps

Before building an image, you need to know which modules the application depends on. `jdeps` is a dependency analysis tool for classes/JARs/modules provided with the JDK.

### 9.1. Printing the Module Dependency List

With modular JARs and dependencies placed on the module path:

```bash
jdeps --print-module-deps --module-path "$JAVA_HOME/jmods:mlib" --recursive mlib/com.acme.orders.jar
```

`--print-module-deps` prints a comma-separated list of module dependencies suitable for passing to `--add-modules`. `--recursive` requests recursive dependency analysis.

Example output:

```text
java.base,java.logging,com.acme.money
```

This is an illustrative example; actual output depends on the referenced classes and the module descriptors of the application and its dependencies.

### 9.2. Creating the Runtime Image from the Module List

After reviewing the dependency list and ensuring all modules are present on the module path:

```bash
jlink --module-path "$JAVA_HOME/jmods:mlib" --add-modules com.acme.orders --output build/orders-runtime
```

Usually you should choose the application module as the root. `jlink` resolves required modules according to descriptors. `jdeps` output serves to cross-check and uncover missing dependencies, not as an excuse to skip understanding the module graph.

### 9.3. Analyzing JARs Without Descriptors

`jdeps` can also analyze legacy JARs and suggest module dependencies. For a non-modular JAR, you can try:

```bash
jdeps --print-module-deps legacy-library.jar
```

However, dependency analysis output does not turn a JAR into an explicit named module or make it linkable. To include a library in a runtime image, convert it into an explicit module, such as creating an appropriate descriptor and packaging it as a modular JAR or JMOD.

### 9.4. Generating Starter Module Descriptors for Legacy Libraries

`jdeps` provides `--generate-module-info` to generate an initial `module-info.java` source for non-modular JARs:

```bash
jdeps --generate-module-info generated-modules legacy-library.jar
```

The generated descriptor is only a starting point. Read and edit it to:

- Confirm the module name.
- Declare accurate dependencies.
- Export only packages that are genuinely public API.
- Add `uses`/`provides` if the library uses SPI.
- Add `opens` when a framework needs reflection for a specific reason.

Then recompile the library as a modular JAR and test it on the module path before running `jlink`. Do not treat an auto-generated descriptor as a finished module contract.

## 10. JAR, Exploded Module, and JMOD

`jlink` accepts different module formats. Understanding their differences helps you choose the right packaging approach.

| Format | Contents | Typical Use Case |
|---|---|---|
| Exploded module | Directory containing `module-info.class` and compiled packages | Development, testing, and internal builds |
| Modular JAR | JAR with `module-info.class` at the root or a valid multi-release module descriptor | Distributing modular libraries/applications |
| JMOD | JDK's own module format; can contain classes, native libraries, commands, config, and headers | Building JDK/runtimes and modules needing special native components |

### 10.1. Using Modular JARs

You can package an exploded module into a JAR:

```bash
jar --create --file mlib/com.acme.orders.jar --main-class com.acme.orders.Main -C mods/com.acme.orders .
```

The JAR retains `module-info.class`, preserving the module descriptor. You can then use `mlib` as the module path:

```bash
jlink --module-path "$JAVA_HOME/jmods:mlib" --add-modules com.acme.orders --launcher orders=com.acme.orders/com.acme.orders.Main --output build/orders-runtime
```

### 10.2. When Do You Need JMOD?

JMOD is useful when a module needs to carry native components or build/runtime resources that modular JARs do not package in the same way. The JDK modules in `$JAVA_HOME/jmods` are a familiar example.

For pure Java applications containing only classes and resources, modular JARs or exploded modules are usually sufficient. You do not need to create JMODs solely to use `jlink`.

### 10.3. Do Not Put an Installed JDK/JRE on the Module Path as an Arbitrary Directory

The module path must point to directories containing valid modules, such as `$JAVA_HOME/jmods` or a directory containing modular JARs. Pointing to a general JDK installation directory does not substitute for a valid module path.

Inspect module paths and module names with JDK tools:

```bash
java --list-modules
jmod describe "$JAVA_HOME/jmods/java.base.jmod"
```

`java --list-modules` lists modules observable by the current runtime. `jmod describe` displays the module metadata inside a JMOD.

## 11. Non-Modular Applications: Link Only the Runtime, Distribute JARs Separately

Not every application can migrate immediately to JPMS. You can use `jlink` to create a small runtime containing the JDK modules needed by a classpath application, and distribute the application JARs alongside it.

In this approach:

- `jlink` creates a runtime image only from the selected JDK modules.
- The application JAR and classpath libraries remain distributed next to the image.
- `jlink` does not package or convert arbitrary classpath dependencies into modules inside the image.
- The user runs the image's `java` launcher with `-cp`.

### 11.1. Analyzing Required JDK Modules

Example:

```bash
jdeps --print-module-deps --class-path "lib/*" app.jar
```

The result might be:

```text
java.base,java.logging,java.sql
```

This is an illustrative result. If the application uses reflection, service loaders, dynamically generated class names, or dependencies not visible to static analysis, you may need to add modules manually and verify at runtime.

### 11.2. Linking a Runtime Containing JDK Modules

```bash
jlink --module-path "$JAVA_HOME/jmods" --add-modules java.base,java.logging,java.sql --output build/legacy-runtime
```

### 11.3. Distributing JARs Alongside the Runtime

Example layout:

```text
distribution/
  runtime/
    bin/java
    lib/modules
    ...
  app/
    app.jar
    lib/
      dependency-a.jar
      dependency-b.jar
```

Running on Linux/macOS:

```bash
distribution/runtime/bin/java -cp "distribution/app/app.jar:distribution/app/lib/*" com.acme.Main
```

On Windows, use a semicolon in the classpath:

```powershell
distribution\runtime\bin\java.exe -cp "distribution\app\app.jar;distribution\app\lib\*" com.acme.Main
```

This is a useful transitional option. If you want `jlink` to package the application itself into the image, modularize the application and its dependencies into explicit named modules.

## 12. Verifying the Runtime Image After Creation

Do not rely solely on `jlink` exiting without errors. Verify that the image has the required modules and runs the application.

### 12.1. Checking Runtime Version

Linux/macOS:

```bash
build/orders-runtime/bin/java -version
```

Windows PowerShell:

```powershell
build\orders-runtime\bin\java.exe -version
```

Confirm that the runtime image uses the expected Java version.

### 12.2. Listing Modules in the Image

Linux/macOS:

```bash
build/orders-runtime/bin/java --list-modules
```

Windows:

```powershell
build\orders-runtime\bin\java.exe --list-modules
```

The module list confirms that the image does not accidentally omit required modules or include more modules than expected.

### 12.3. Running the Application Launcher

Linux/macOS:

```bash
build/orders-runtime/bin/orders
```

Windows:

```powershell
build\orders-runtime\bin\orders.exe
```

Run smoke tests with representative configuration and data. If the application relies on config files, certificates, timezones, locales, native libraries, or service providers, verify all of them inside the image environment.

### 12.4. Checking Footprint

Compare sizes:

- The full JDK used as the source.
- The newly created runtime image.
- The complete distribution after adding the application, configs, and required libraries.

The goal is to optimize the overall distribution package, not merely shrink the runtime folder while forgetting required accompanying files.

## 13. Distributing the Runtime Image

### 13.1. Packaging the Image Directory

After testing, you can archive the entire runtime image directory together with launchers, configs, and required resources into a distribution bundle. Preserve the directory structure because launchers and the runtime rely on relative/internal paths.

Example:

```text
orders-distribution/
  runtime/
  config/
  data/
  README.txt
```

If a launcher was created inside the runtime image, users only need to run the executable in `runtime/bin`.

### 13.2. Runtime Images Are Platform-Dependent

A runtime image contains native libraries and launchers tailored to the platform supported by the source JDK/JMODs. Therefore:

- A Windows image is not a universal bundle for Linux/macOS.
- CPU architecture differences (x64, AArch64, etc.) must also be accounted for.
- Third-party native libraries must match the OS/architecture and be ABI-compatible.
- Build and test a separate image for each target platform.

You cannot take a single runtime image and assume it runs on every OS just because Java bytecode is portable.

### 13.3. Security Updates for Bundled Runtimes

When distributing a private runtime image, the application carries the runtime linked at build time. Updating Java on the user's machine does not automatically update the runtime inside the application bundle.

When a JDK 17 update is released with security patches or bug fixes, you must:

1. Update the build JDK to the supported patch release.
2. Rebuild the runtime image with `jlink`.
3. Run regression and compatibility tests.
4. Re-release the application/runtime package.
5. Maintain a policy for tracking deployed runtime versions.

This is a key responsibility when distributing applications with a self-contained runtime.

## 14. Common Errors When Using jlink

| Error / Symptom | Possible Cause | Resolution |
|---|---|---|
| `Module ... not found` | Module path lacks the JMOD, modular JAR, or exploded module | Check `--module-path`, module name, and paths |
| `Module ... not found, required by ...` | Dependency declared via `requires` is missing from the module path | Add the explicit module dependency and inspect the module graph |
| `Automatic modules are not supported` | An automatic JAR is on the module path being linked by `jlink` | Modularize the library into an explicit named module |
| `Invalid module name` | Module name in descriptor or inferred name is invalid | Fix the module descriptor/manifest and check the module name |
| Main class not found when running launcher | Wrong module name, package, or main class in `--launcher` | Verify module name, class name, and that the class has a valid `main` method |
| Application runs on full JDK but fails in image | Image is missing dynamically loaded modules, service providers, resources, or native libraries | Analyze dependencies, use `--bind-services` if needed, and test on the image |
| `ServiceLoader` finds no providers | Provider module is missing from the image or descriptor lacks `provides` | Check `uses`/`provides` and try `--bind-services` |
| Reflection fails in runtime image | Package is not open to the framework needing reflection | Declare scoped `opens` directives and test the framework |
| Image fails on another machine | Different OS, CPU architecture, or native dependencies | Build and test images for each target platform |
| Image size did not shrink much | Large module graph, heavy resources, or suboptimal plugins | Review module list, check dependencies, and measure compression/stripping |
| `jlink` says output path already exists/non-empty | Output directory contains leftovers from a previous build | Choose a fresh output directory or clean the build output owned by the pipeline |
| Runtime image lacks security patches | Application package carries an older runtime | Rebuild the image with an updated JDK and re-release |

### 14.1. Diagnosing Missing Modules

Check module names and module paths:

```bash
java --list-modules
jmod describe "$JAVA_HOME/jmods/java.logging.jmod"
```

For a modular JAR, use:

```bash
jar --describe-module --file mlib/com.acme.orders.jar
```

This command displays the module descriptor and module name of the JAR. Do not guess the module name from package names.

### 14.2. Diagnosing Missing Dependencies

Run `jdeps` on the application and its dependencies:

```bash
jdeps --print-module-deps --module-path "$JAVA_HOME/jmods:mlib" --recursive mlib/com.acme.orders.jar
```

Compare the output against the module path. If a dependency lacks a descriptor, modularize it before passing it to `jlink`.

### 14.3. Diagnosing Service Providers

`jlink` supports:

```bash
jlink --module-path "$JAVA_HOME/jmods:mlib" --suggest-providers java.sql.Driver
```

This option suggests modules that provide implementations for the service type. Use it together with consumer/provider descriptors to decide which modules belong in the image.

## 15. Limitations and Design Considerations

### 15.1. jlink Does Not Automatically Detect All Dynamic Dependencies

Module graph analysis relies heavily on descriptors and statically analyzable bytecode. The following cases may require additional configuration:

- Loading classes by name from configuration files.
- Plugins discovered at runtime.
- Reflection or frameworks scanning for implementations.
- Service providers needing binding.
- JNI/native libraries loaded by configuration.
- Resources read via dynamically constructed paths.

Run the application on the runtime image across real features, not just a trivial `main` smoke path.

### 15.2. jlink Does Not Replace a Build System

`jlink` builds runtime images, but applications still need a build pipeline to:

- Compile source code.
- Run tests.
- Package modular JARs.
- Manage dependencies.
- Create launchers/runtime images.
- Package configs and resources.

You can integrate `jlink` commands into Maven, Gradle, or build scripts, while keeping the module path, JDK version, and link options consistent.

### 15.3. Do Not Optimize Size by Arbitrarily Deleting Modules

If an application needs a module for a feature, omitting that module may cause failures only when that feature is invoked. Start from the resolved module graph, then use `jdeps`, JMC/logs, and real tests to determine what can be safely excluded.

### 15.4. Retain Appropriate Diagnostics

`--strip-debug` shrinks the image but removes debug information. For applications needing production support, consider keeping symbols/debug metadata in separate artifacts or producing environment-specific image variants. Do not trade away incident troubleshooting capability without a plan.

### 15.5. A Runtime Image Is Not an Installer

`jlink` produces a runtime image directory. Installation, shortcuts, service registration, environment variable setup, updates, and uninstallation belong to a dedicated packaging/installer system.

## 16. Repeatable Runtime Image Build Workflow

A typical release workflow includes:

1. Select a specific JDK 17 release and record its vendor/build version.
2. Compile the application into explicit named modules.
3. Package dependencies as modular JARs or JMODs.
4. Use `jdeps` to analyze module dependencies.
5. Run the application on the module path before linking.
6. Select root modules with `--add-modules`.
7. Add `--bind-services` if service provider binding is needed.
8. Choose launchers and appropriate optimization plugins.
9. Build the image into a fresh output directory.
10. Verify version, module list, launchers, and application behavior.
11. Run tests on each target OS/architecture.
12. Package the runtime together with needed configs/resources.
13. Record the JDK build and `jlink` options to reproduce the image.
14. Rebuild and re-release the image when JDK patches arrive.

Combined command example:

```bash
jlink --module-path "$JAVA_HOME/jmods:mlib" --add-modules com.acme.orders --bind-services --launcher orders=com.acme.orders/com.acme.orders.Main --strip-debug --compress=2 --no-header-files --no-man-pages --output build/orders-runtime
```

This is an example configuration for a modular application. If the application does not use service providers, you can omit `--bind-services`. If debugging is required, consider omitting `--strip-debug`.

## 17. Practice Exercises

### Exercise 1 — Create a Runtime Image for a Modular Application

Create module `com.acme.hello` with `module-info.java` and a `Main` class that prints a message. Carry out these steps:

1. Compile the module into a `mods` directory.
2. Run the module using the current JDK.
3. Use `jlink` to create an image containing only the required modules.
4. Run the application using `bin/java` inside the image.
5. Check `--list-modules` and record which modules are present in the image.

### Exercise 2 — Create a Custom Launcher

Using the application from Exercise 1, pass `--launcher hello=com.acme.hello/com.acme.hello.Main`. Run the launcher from the image without re-entering the module name and main class.

### Exercise 3 — Analyze Dependencies with jdeps

Add a modular dependency to the application. Run:

```bash
jdeps --print-module-deps --module-path "$JAVA_HOME/jmods:mlib" --recursive mlib/com.acme.hello.jar
```

Cross-check the output with the `requires` directives in the descriptor. Then build the image and explain why each dependent module was included.

### Exercise 4 — Handle a Non-Modular Library

Given a JAR without `module-info.class`:

1. Place the JAR on the module path and attempt to run `jlink`.
2. Note the error stating automatic modules are not supported.
3. Use `jdeps --generate-module-info` to create a starter descriptor.
4. Edit the descriptor, compile, and package as a modular JAR.
5. Try linking again.

Explain why a JAR being runnable on the classpath or as an automatic module does not mean it can be directly linked by `jlink`.

### Exercise 5 — Use Service Providers

Create a service interface, a consumer module declaring `uses`, and a provider module declaring `provides ... with ...`. Create the image:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.consumer --bind-services --output build/service-runtime
```

Run the application and confirm the provider is found. Try omitting `--bind-services` and observe the difference in the image.

### Exercise 6 — Compare Image Sizes

Build images with:

- No compression.
- `--compress=2`.
- `--strip-debug --no-header-files --no-man-pages`.

Compare disk footprints and verify the application still runs properly. Note which option combination fits your deployment requirements.

### Exercise 7 — Distribute a Classpath Application

For a non-modular application, use `jdeps` to find required JDK modules, build a runtime image from JDK JMODs only, and run the JAR with `-cp`. Explain what `jlink` puts into the image and what still must be distributed separately.

### Exercise 8 — Build Images for Multiple Platforms

Create runtime images for two different environments (for example Windows x64 and Linux x64) using the platform-appropriate JDK/JMODs. Inspect launchers, native dependencies, and packaging for each environment.

## 18. Official Java 17 Documentation

- [Java 17 jlink command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html): syntax, module path, root modules, launchers, and linking options.
- [Java 17 jdeps command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): dependency analysis and generating starter module descriptors.
- [Java 17 jmod command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jmod.html): describing and creating JMODs.
- [Java 17 jar command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): creating and inspecting modular JARs.
- [Java Language Specification 17 — Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): module declarations, `requires`, `exports`, `uses`, and `provides`.
- [JEP 282 — jlink: The Java Linker](https://openjdk.org/jeps/282): design goals and capabilities of the `jlink` tool.
- [Java Platform Module System — Module Resolution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): module declaration rules and module dependencies.

**Key Takeaway:** `jlink` creates custom runtime images from explicit modules and resolved dependencies. Start with accurate module descriptors, analyze dependencies with `jdeps`, specify root modules via `--add-modules`, add `--bind-services` when providers are needed, then configure launchers and appropriate optimization plugins. A runtime image is a platform-specific runnable bundle, not a standalone native executable or a full JDK. Inspect the module list, run the application on the image, distribute for the matching OS/architecture, and rebuild the runtime whenever JDK 17 receives security updates.
