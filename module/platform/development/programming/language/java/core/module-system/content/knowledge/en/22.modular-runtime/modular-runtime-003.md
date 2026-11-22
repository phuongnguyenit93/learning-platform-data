# `java --add-modules`: Adding Root Modules

## 1. Purpose of --add-modules

The Java Platform Module System (JPMS) does not automatically include every observable module in the runtime configuration. The JVM starts resolution from a set of **root modules**. From these roots, the module system finds dependencies declared via `requires` and builds readability relationships between modules.

The **--add-modules** option of the Java launcher allows adding modules to the root set to be resolved, alongside the application's starting module:

    java --add-modules java.sql -cp app.jar com.example.Main

In the example, `java.sql` is requested as an additional root module. The JVM must locate this module among the observable modules, resolve it along with its required dependencies, and then launch the application.

This option is useful when:

- An application runs from the classpath but needs an API located in a named module that is not in the default root set.
- An application or library needs a specific JDK module that has not been included in the runtime configuration.
- A provider module needs to be added to the configuration so the application can use its corresponding functionality.
- An application wants to explicitly specify additional modules when launching a named module.
- You need to test a module or module path configuration without modifying the application's `module-info.java`.

**--add-modules only adds roots to the resolution process.** It does not add JARs to the module path, does not automatically create `requires` dependencies, does not export packages, and does not open packages for reflection.

## 2. Syntax and Position on the Command Line

Basic syntax:

    java --add-modules module[,module...] <main-class>

An equals sign can be used:

    java --add-modules=java.sql,java.xml -cp app.jar com.example.Main

Multiple modules can be specified in the same list, separated by commas. The names used are module names, not JAR names, package names, or class names.

Example with a named module as the main program:

    java --module-path mods \
         --add-modules com.example.metrics \
         --module com.example.application/com.example.application.Main

In the command above:

- **--module-path mods** specifies where the JVM looks for application modules.
- **--module com.example.application/...** selects the main module and main class.
- **--add-modules com.example.metrics** adds `com.example.metrics` as a root module.
- Dependencies declared via `requires` will be resolved according to module resolution rules.

Launcher options must appear before the main class name, the JAR name after `-jar`, or the module argument after `-m`/`--module`. Arguments appearing after the program entry point are passed to the `main` method and are no longer interpreted as launcher options.

On Windows, the separator between module path elements is a semicolon. On Linux and macOS, the separator is a colon.

## 3. Root Modules and the Resolution Process

Root modules are the starting point of the module resolution process. You can think of this process in the following steps:

1. The JVM identifies the application's main module and any additional roots requested via `--add-modules`.
2. The JVM finds the corresponding module descriptors in the set of observable modules.
3. `requires` directives are traversed recursively to determine necessary dependencies.
4. The JVM builds the readability graph, representing which modules can read which other modules.
5. If the configuration includes service binding, matching providers may also be included in the configuration according to JPMS service binding rules.

For example, suppose:

    module com.example.application {
        requires com.example.api;
    }

    module com.example.api {
        requires com.example.logging;
    }

If `com.example.application` is the root, module resolution will resolve the declared dependencies along the `requires` relationships. You do not need to add each dependency individually with `--add-modules` if they are already required and observable.

Conversely, if the application runs on the classpath and has no main named module, the application may need to add a named module with `--add-modules` so that module is resolved into the boot layer.

The default root set when running a named module is typically the application module specified to the launcher. When running a main class from the classpath or compiling code in the unnamed module, the default root set depends on the implementation. In the JDK, the default set includes observable modules on the upgrade module path or among system modules that export at least one package without a target-module restriction.

Key point to remember: **observable does not mean resolved**. A module may exist on the module path or in the runtime image without being part of the resolved module configuration. `--add-modules` tells the launcher to include that module in the root set for resolution.

## 4. Three Special Selectors

In addition to specific module names, the Java launcher supports three special values:

| Value | Meaning | Use Case |
|---|---|---|
| **ALL-DEFAULT** | The launcher's default root module set | When you want to explicitly state the default root set, often useful in source-file mode or launcher configurations that need to be explicit |
| **ALL-SYSTEM** | All observable system modules in the runtime image | When you need to resolve all JDK system modules for testing or special configurations |
| **ALL-MODULE-PATH** | All observable modules on the application module path | When you want to resolve every module provided via the module path |

Examples:

    java --add-modules ALL-DEFAULT -cp app.jar com.example.Main

    java --add-modules ALL-SYSTEM -cp app.jar com.example.Main

    java --module-path mods \
         --add-modules ALL-MODULE-PATH \
         --module com.example.application/com.example.application.Main

These selectors vary in scope. `ALL-SYSTEM` can bring in many JDK modules that the application does not need. `ALL-MODULE-PATH` can resolve even modules that the application does not use directly. That can increase the number of modules in the configuration, expose package/module conflicts, and make dependency analysis harder.

In typical applications, prefer specifying explicit module names. Use broad selectors only when there is a clear reason, such as test environments, tools that need to inspect modules, or runtime configurations designed to include all modules.

## 5. Observable Modules: Modules Must Be Found First

`--add-modules` is not an option for adding JAR files or directories to the module search location. The module must already be in the runtime's set of observable modules.

Common sources:

- **System modules:** modules built into the JDK runtime image.
- **Upgrade module path:** location for replacement modules for certain upgradeable modules in the runtime image.
- **Application module path:** location for modular JARs or exploded modules of the application and libraries.

Example:

    java --module-path mods \
         --add-modules com.example.reporting \
         --module com.example.application/com.example.application.Main

If `com.example.reporting` is not among the module sources observable by the JVM, the launcher reports a module not found error. Check the module path and actual module name before changing the root list.

You can view observable modules with:

    java --list-modules

This command lists the modules that the runtime sees. It does not mean all modules in the list have been resolved into the boot layer.

You can view information about a module:

    java --module-path mods --describe-module com.example.reporting

To observe the module resolution process at startup:

    java --show-module-resolution \
         --module-path mods \
         --add-modules com.example.reporting \
         --module com.example.application/com.example.application.Main

The **--show-module-resolution** option helps you see which modules are resolved and their dependency relationships during startup.

## 6. Example: A Classpath Application Needing an API from a Named Module

Suppose a legacy application runs on the classpath:

    java -cp app.jar com.example.Main

Code in `app.jar` uses an API belonging to module `com.example.metrics`. The modular JAR for this module is in the `mods` directory.

It can be launched as follows:

    java --module-path mods \
         --add-modules com.example.metrics \
         -cp app.jar \
         com.example.Main

Module `com.example.metrics` is added as a root and resolved along with its dependencies. Application classes still run in the unnamed module because the main class is loaded from the classpath.

The unnamed module can read named modules in the appropriate configuration, but package accessibility still depends on `exports`. If a package is only conditionally exported to a specific module, adding the root module does not automatically grant access to the unnamed module.

For example, the library module has:

    module com.example.metrics {
        exports com.example.metrics.api;
        exports com.example.metrics.internal
            to com.example.metrics.tests;
    }

The classpath application can use APIs in the unconditionally exported package. Adding the module does not make the internal package public to the unnamed module.

## 7. Example: Main Module Requiring an Additional Module

For a modular application, the main module is selected with `-m` or `--module`:

    java --module-path mods \
         --module com.example.application/com.example.application.Main

If the main module does not declare `requires` on another module, yet the runtime still needs to resolve that module as an independent root, you can add it:

    java --module-path mods \
         --add-modules com.example.diagnostics \
         --module com.example.application/com.example.application.Main

This case often occurs with modules discovered dynamically or modules providing features enabled by configuration. If the dependency relationship is required by design and can be declared statically, express it in `module-info.java` using `requires` rather than relying long-term on deployment options.

If the module is used via `ServiceLoader`, distinguish two things:

- The consumer module declares **uses** to register its need for a service.
- The provider module declares **provides ... with ...** to register an implementation.

`--add-modules` can put the provider module into the root set, but it does not replace `uses`/`provides` and does not make an incorrectly typed provider valid.

## 8. Distinguishing from Other Module Options

The following options are often confused with `--add-modules`:

| Option | Effect | What It Does Not Do |
|---|---|---|
| **--module-path** | Specifies where to locate application modules | Does not automatically cause every module on the path to be resolved |
| **--add-modules** | Adds root modules to the set to resolve | Does not add paths or export packages |
| **--limit-modules** | Limits the set of observable modules | Does not add new modules to the observable set |
| **--add-reads** | Adds a readability relationship between two modules | Does not automatically resolve unobservable modules |
| **--add-exports** | Allows an additional package to be exported to target modules | Does not add root modules |
| **--add-opens** | Opens a package for deep reflection to target modules | Does not replace `requires` or module resolution |

Example:

    java --module-path mods \
         --add-modules com.example.library \
         --add-exports com.example.library/com.example.internal=ALL-UNNAMED \
         -cp app.jar com.example.Main

In this command, `--add-modules` puts `com.example.library` into the root set; `--add-exports` adjusts access to the internal package for unnamed modules. The two options solve two different problems.

If a module is not on the module path or in the runtime image, adding `--add-reads` or `--add-exports` cannot make the JVM find that module. First, ensure the module is observable.

## 9. Combining with --limit-modules

**--limit-modules** restricts the runtime's set of observable modules. This option is often used when testing whether an application can run with a smaller set of modules or creating a scoped runtime.

Example:

    java --limit-modules java.base,java.logging \
         --add-modules java.sql \
         -cp app.jar com.example.Main

If `java.sql` is not in the observable set after applying the limit, the launcher cannot resolve it merely because it is named in `--add-modules`. The module must be allowed to be observed and found under the limited configuration.

When combining the two options, consider the observable set first, and then determine the root modules. `--add-modules` selects modules from the observable set; `--limit-modules` defines the boundary of that set itself.

Avoid adding a very broad root list while simultaneously limiting modules without understanding the dependency closure. A module added as a root may pull in other modules via `requires`; if a dependency is excluded from the observable set, resolution will fail.

## 10. Inspection and Diagnostics

When the launcher reports a module not found error or the application cannot access an API, you can check in order:

1. Determine the actual module name using `jar --describe-module` or `java --list-modules`.
2. Confirm whether the module is in system modules, the upgrade module path, or the application module path.
3. Confirm that the `--module-path` option points to the right directory or JAR.
4. Check whether the module name passed to `--add-modules` matches the module descriptor.
5. Inspect the module's dependency closure through `requires` directives.
6. Use `--show-module-resolution` to observe which modules are resolved.
7. If the error is `IllegalAccessError` or `InaccessibleObjectException`, check `exports`, `opens`, and readability; adding a root module does not fix access permissions.
8. If the error is a package not found or a class failing to load, identify the module containing the package and the loader being used.

Useful commands:

    java --list-modules

    jar --describe-module --file mods/com.example.metrics.jar

    java --module-path mods \
         --add-modules com.example.metrics \
         --show-module-resolution \
         --module com.example.application/com.example.application.Main

    java --module-path mods --validate-modules

**--validate-modules** checks the validity of the module configuration on the module path and exits. It does not run the `main` method and does not replace functional testing of the application.

## 11. Common Mistakes

### Module Not Found

The cause is usually that the module is not yet on the module path, the module name is wrong, or the module was excluded from the observable set by `--limit-modules`. Inspect the JAR with `jar --describe-module`, then re-check the path.

### Module Resolved but Package Still Inaccessible

`--add-modules` does not alter `exports` or `opens`. If the application is not permitted to access a package, fix the module descriptor according to your design or use the appropriate additional option for the intended run/test purpose.

### Module Added but Dependencies Still Fail

When a module is added as a root, the JVM continues resolving its dependencies. If the module declares `requires` on an unobservable module or has a package conflict, the entire resolution can fail. Check the dependency closure rather than only checking the root module.

### Using ALL-MODULE-PATH Causes Conflicts

Making every module on the module path a root can expose package or module name conflicts that a minimal configuration does not encounter. Only use `ALL-MODULE-PATH` when you genuinely need to resolve the entire set of modules on the path.

### Confusing --add-modules with --add-reads

A module may already be resolved while another module cannot yet read it. In that case, the issue is readability rather than the root set. `--add-reads` adjusts read edges; `--add-modules` brings a module into resolution. Choose the option based on the actual error type.

## 12. Takeaways

- **--add-modules** adds root modules to the set of modules to resolve, alongside the starting module.
- Root modules pull in dependencies through `requires` directives during resolution.
- A module must be in the observable set; `--add-modules` does not replace `--module-path`.
- You can specify explicit module names or use `ALL-DEFAULT`, `ALL-SYSTEM`, and `ALL-MODULE-PATH`.
- `ALL-DEFAULT` represents the default root set; `ALL-SYSTEM` selects all system modules; `ALL-MODULE-PATH` selects all modules on the application module path.
- `--add-modules` does not automatically add `requires`, `exports`, `opens`, or readability.
- `--limit-modules` limits the set of observable modules; modules excluded from this set cannot be added as roots.
- Use `--show-module-resolution` to inspect the actual module configuration at startup.
- Prefer adding specific modules instead of resolving everything if the application only needs a few modules.

**--add-modules is the tool for controlling the starting point of module resolution.** When you clearly distinguish root modules, dependencies, observable modules, and package access permissions, you can use this option to supply the right modules for your application without confusing it with other JPMS mechanisms.

## References

- Java SE 21 Tool Specifications — java launcher: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Java SE 21 API — java.lang.module package summary: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/package-summary.html
- Java SE 21 Tool Specifications — javac: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html