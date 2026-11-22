# What Is a Split Package?

## 1. The Split Package Concept

A package in Java is identified by its package name, for example **com.example.logging**. A **split package** occurs when classes belonging to the same package name are distributed across multiple modules. In legacy environments, those classes are also often packaged in multiple different JARs on the classpath.

For example, two libraries have the structure:

    logging-api.jar
      com/example/logging/Logger.class

    logging-impl.jar
      com/example/logging/ConsoleLogger.class

Both JARs contain classes belonging to the package **com.example.logging**. When the JARs are on the classpath of the same application, they are usually loaded into the unnamed module of the corresponding class loader. Therefore, having a package contributed by multiple JARs does not by itself create a JPMS split package error.

When converting the JARs into named modules, the situation changes. If logging-api.jar and logging-impl.jar become two separate modules while still containing the package **com.example.logging**, that is a split package between named modules. The configuration may be rejected by module resolution if a consuming module simultaneously reads the modules that both export that package.

It is important to distinguish:

- **Split package:** the same package name distributed across multiple modules or artifacts.
- **Duplicate class:** the same binary name of a class appearing multiple times, for example two JARs both containing **com.example.logging.Logger**.
- **Shared package on the classpath:** multiple JARs contributing different classes to one package belonging to the same unnamed module of a class loader. This organization can work on the classpath but causes difficulties when modularizing.

## 2. Why Do Split Packages Cause Problems in JPMS?

JPMS creates module boundaries to determine which module can read which module and which packages are exposed. If the same package is exported from multiple modules to a consuming module, the consuming module will not have a single clear source for the package.

For example:

    module com.example.logging.api {
        exports com.example.logging;
    }

    module com.example.logging.impl {
        exports com.example.logging;
    }

    module com.example.application {
        requires com.example.logging.api;
        requires com.example.logging.impl;
    }

Both library modules export **com.example.logging**, and application reads both. Module resolution can fail because application receives the same package from two different modules. A typical error is a **ResolutionException** reporting that the modules both export one package to the consuming module.

Not every occurrence of the same package name anywhere necessarily causes the entire runtime to fail. Conflicts are detected in the readability/export relationships of the module configuration. However, for a stable design, you should avoid letting the same package belong to multiple named modules that may be used simultaneously.

A module also cannot use additional access permissions to turn two packages into a unified package. **exports**, **opens**, and **reads** handle access permissions; they do not merge package contents from different modules.

## 3. Split Packages on the Classpath and Module Path

### Multiple JARs on the classpath

The traditional classpath allows multiple JARs to contribute classes to the same package:

    java -cp "lib/logging-api.jar;lib/logging-impl.jar;app.jar" com.example.Main

On Windows, the classpath separator is usually a semicolon. On Linux and macOS, use a colon:

    java -cp "lib/logging-api.jar:lib/logging-impl.jar:app.jar" com.example.Main

Classes in the same package can be seen as members of the unnamed module managed by the corresponding class loader. This organization has no module descriptor to define boundaries between logging-api and logging-impl.

If two JARs both contain a class with the exact same full name, a standard class loader will search in the order of the classpath. The class found first may shadow the remaining one. With custom class loaders, search behavior depends on how the loader is implemented.

### Multiple named modules on the module path

When each JAR becomes a named module, the module descriptor defines its packages and export relationships. If multiple modules contain the same package, a consuming module that reads those modules may encounter a split package error during resolution.

Example structure:

    mods/
      com.example.logging.api.jar
      com.example.logging.impl.jar
      com.example.application.jar

Inspect each JAR:

    jar --describe-module --file mods/com.example.logging.api.jar
    jar --describe-module --file mods/com.example.logging.impl.jar

If both modules contain and export **com.example.logging**, you should review the module boundaries instead of trying to resolve it by adding access permissions in the launcher.

### Automatic modules can also create conflicts

A JAR without module-info.class when placed on the module path can be treated as an automatic module. An automatic module exports its packages according to automatic module rules. Therefore, two legacy JARs that both contain the package **com.example.logging** when becoming two automatic modules can still create a split package in a JPMS configuration.

Adding the **Automatic-Module-Name** attribute only gives a stable name to an automatic module. It does not merge identically named packages and does not resolve package conflicts.

## 4. How to Identify a Split Package

Start by inspecting the contents of each JAR:

    jar --list --file logging-api.jar
    jar --list --file logging-impl.jar

Look for paths with the same package prefix, for example:

    com/example/logging/Logger.class
    com/example/logging/ConsoleLogger.class

Next, inspect the module descriptors:

    jar --describe-module --file logging-api.jar
    jar --describe-module --file logging-impl.jar

The output helps identify the module name, contained packages, and exported packages. For an explicit module, pay attention to the **exports** and **contains** lines. For an automatic module, look at the inferred module name and the list of exported packages.

You can inspect the list of modules visible to the runtime:

    java --module-path mods --list-modules

And observe the resolution process:

    java --show-module-resolution \
         --module-path mods \
         --module com.example.application/com.example.application.Main

If the configuration has a package conflict, the module resolution error message usually points out the names of the modules and the conflicting package. Use the exact package and module names from the message to trace back to the JARs containing the classes.

For complex dependencies, **jdeps** helps inspect module and package dependency relationships:

    jdeps --module-path mods --check com.example.application

**jdeps** does not replace reading JAR contents or analyzing module resolution, but it can help determine which module is reading or depending on the libraries involved.

## 5. How to Handle Split Packages When Modularizing

### Merge classes in the same package into one module

If two JARs are actually parts of the same library and need to co-own the package, the clear solution is usually to package them into a single named module.

For example, instead of:

    com.example.logging.api
      com.example.logging.Logger

    com.example.logging.impl
      com.example.logging.ConsoleLogger

It can be organized into:

    com.example.logging
      com.example.logging.Logger
      com.example.logging.ConsoleLogger

Single module descriptor:

    module com.example.logging {
        exports com.example.logging;
    }

Merging can be performed in the build step or by restructuring the artifacts. When merging, you must preserve the library's required dependencies, service metadata, and resources.

### Separate packages by responsibility

If the API and implementation can be independent, you should place them in different packages:

    com.example.logging.api
    com.example.logging.internal

For example:

    module com.example.logging.api {
        exports com.example.logging.api;
    }

    module com.example.logging.impl {
        requires com.example.logging.api;
        provides com.example.logging.api.LoggerProvider
            with com.example.logging.internal.ConsoleLoggerProvider;
    }

The implementation module does not need to export its internal package if the application only interacts through the service API. This creates clear module boundaries and reduces the likelihood of package conflicts.

### Move classes to the module that owns the package

When a package is split across multiple modules, determine which module is the logical owner. Move the remaining classes into that module or change their package so that the package has a single owner in the architecture.

Do not just rename the module while keeping the same package in both places; different module names do not make a split package disappear.

### Isolate modules across independent module layers

A plugin application can use separate module layers to isolate independent groups of modules. Different layers can contain modules with the same package name without automatically merging them into a shared package.

This approach is only suitable when plugins are genuinely independent in terms of types and dependencies. If the host needs to pass objects belonging to that package between plugins, the two sides may have different classes in terms of runtime identity. APIs shared between the host and plugins should reside in a common module that both read.

## 6. Role and Limitations of --patch-module

The **--patch-module** option allows adding classes and resources to an existing module. It is often useful in testing, instrumentation, or when patching a module in a controlled deployment environment.

For example:

    java --patch-module com.example.logging=patches/logging \
         --module-path mods \
         --module com.example.application/com.example.application.Main

Classes and resources from the patch path are treated as contents of the target module at runtime. If the patch contains a package owned by the target module, those classes belong to the target module rather than creating a new named module.

However, **--patch-module is not a general solution for merging two independent named modules**. It does not replace redesigning module boundaries, does not fix incorrect dependencies, and should not be used to hide conflicting package structures long-term.

When using it in tests, restrict the patch path to the exact target module and test environment. Do not put internal patches into production commands without a clear operational reason.

## 7. Options That Do Not Solve Split Packages

| Option | Function | Does it merge packages? |
|---|---|---|
| **--add-modules** | Adds root modules to the resolution process | No |
| **--add-reads** | Adds readability relationships | No |
| **--add-exports** | Exports additional packages to target modules | No |
| **--add-opens** | Opens packages for deep reflection | No |
| **--module-path** | Specifies where to find named modules | No |
| **--patch-module** | Adds classes/resources to a target module | Only adds to the target module; does not redesign conflicting modules |

For example, if application reads both modules that export the package **com.example.logging**, adding:

    --add-reads com.example.application=com.example.logging.api

does not turn the packages of the two modules into one. Similarly, --add-exports only adjusts which packages can be accessed, not moving classes from one module to another.

You need to identify the exact type of issue: missing module, missing readability, missing export, missing open for reflection, or split package. Each issue has its own resolution mechanism.

## 8. Process for Migrating a Classpath Application to JPMS

When a legacy system has multiple JARs contributing classes to the same package, you should check before creating module descriptors:

1. List the dependency JARs and the packages each JAR contains.
2. Use jar --list to detect duplicate package names across artifacts.
3. Use jar --describe-module to determine the module names and exported packages of already modular or automatic JARs.
4. Determine which packages need to be public APIs and which are for internal use only.
5. Merge artifacts that share ownership of a package or separate packages by responsibility.
6. Write module-info.java with appropriate requires, exports, uses, and provides.
7. Rebuild the JARs and verify the module descriptors.
8. Run java --validate-modules or the application with --show-module-resolution to detect remaining conflicts.
9. Run integration tests to confirm class loading, service discovery, and reflection.

Do not modularize by merely adding module-info.java to each JAR without reviewing the package layout. A valid classpath structure can become an invalid module configuration after splitting JARs into multiple named modules.

## 9. Illustrative Example

Suppose there are two legacy JARs:

    legacy-api.jar
      com/example/payment/Payment.class
      com/example/payment/PaymentRequest.class

    legacy-adapter.jar
      com/example/payment/LegacyPaymentAdapter.class

When running on the classpath:

    java -cp "legacy-api.jar;legacy-adapter.jar;app.jar" com.example.Main

The classes above can belong to the same package of the unnamed module managed by the application class loader.

If converted into two modules:

    module com.example.payment.api {
        exports com.example.payment;
    }

    module com.example.payment.adapter {
        exports com.example.payment;
    }

and application requires both:

    module com.example.application {
        requires com.example.payment.api;
        requires com.example.payment.adapter;
    }

then application reads two modules that both export **com.example.payment**. Module resolution may reject the configuration due to a split package.

An alternative design is to change the implementation package:

    module com.example.payment.api {
        exports com.example.payment.api;
    }

    module com.example.payment.adapter {
        requires com.example.payment.api;
        exports com.example.payment.adapter;
    }

The classes are reorganized:

    com/example/payment/api/Payment.class
    com/example/payment/api/PaymentRequest.class
    com/example/payment/adapter/LegacyPaymentAdapter.class

Application only needs to read the API and adapter modules. The packages now have clear boundaries, and the same package is no longer exported from two modules.

## 10. Key Takeaways

- A split package is the condition where the same package name is divided across multiple modules.
- On the classpath, multiple JARs can contribute classes to a package of the unnamed module; this is not synonymous with a JPMS split package conflict.
- On the module path, multiple named modules exporting the same package to a consuming module can cause module resolution to fail.
- Automatic modules can also cause package conflicts when multiple JARs contain the same package and are read together.
- Split packages differ from duplicate classes: one case splits classes within a package, while the other duplicates the same class name.
- **--add-reads**, **--add-exports**, and **--add-opens** do not merge packages.
- **--patch-module** supplements content into a target module but does not replace a good module design.
- Prefer merging artifacts that share ownership of a package or separating packages by responsibility.
- For independent plugins, module layers can support isolation, but shared APIs need to reside in a shared module.
- Use **jar --list**, **jar --describe-module**, **jdeps**, and **--show-module-resolution** to find the source of conflicts.

**Split packages often reveal library boundary issues when an application migrates from the classpath to JPMS.** A sustainable way to handle this is to identify a single module that owns each API package, reorganize the packages, and declare dependencies clearly.

## References

- Java Language Specification, Java SE 21 — Packages: https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html
- Java SE 21 API — java.lang.module package: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/package-summary.html
- Java SE 21 Tool Specifications — java launcher: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Java SE 21 Tool Specifications — jar: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html
