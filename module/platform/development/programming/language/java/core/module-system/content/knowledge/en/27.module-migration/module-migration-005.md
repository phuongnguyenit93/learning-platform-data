# Creating module-info.java for an Application

When migrating a Java application from the **classpath** to the Java Platform Module System (JPMS), a key step is creating the `module-info.java` file to declare the module's identity, which modules the application needs to read, and which packages or services the application wishes to expose. This file is called the **module descriptor**.

Adding `module-info.java` is not merely a syntax change. The application moves from the classpath model, where many packages are looked up across one broad class-loading space, to the **named modules** model with explicit boundaries. Therefore, you need to survey dependencies, choose module boundaries, add the descriptor, and test execution on the module path.

This guide walks through the workflow from a regular Java application to a modular JAR runnable with `java --module-path`.

## 1. What Does a Module Descriptor Solve?

A minimal descriptor:

```java
module com.acme.app {
}
```

When compiled, `javac` produces `module-info.class`. When packaged inside a JAR, the artifact can be recognized as an **explicit named module** when placed on the module path.

The module descriptor tells the JVM and tools:

- **Module name**, such as `com.acme.app`.
- **Dependencies** read via `requires`.
- **API packages** other modules are allowed to access via `exports`.
- **Packages for deep reflection** via `opens`.
- **Service consumers** via `uses`.
- **Service providers** via `provides ... with ...`.

A descriptor does not list individual JAR files, does not replace a dependency management tool, and does not automatically put missing dependencies onto the module path. It describes module relationships; the build tool and launch command must still supply the corresponding artifacts.

## 2. Identifying What Dependencies the Application Has

Before creating the descriptor, classify the application's dependencies:

| Group | Example | How to handle during modularization |
|---|---|---|
| Standard Java SE APIs | Logging, JDBC, XML, HTTP Client | Declare `requires java.logging`, `java.sql`, etc., if actually used |
| Libraries with module-info | Team-owned or third-party modular JARs | Use the module name published by the descriptor |
| JARs without descriptors | Legacy classpath libraries | Can operate as automatic modules on the module path during transition |
| Annotation processors | Lombok, code-generating processors | Configure processor path/module path at build time; do not add blindly as runtime dependencies |
| Frameworks using reflection | ORMs, JSON serializers, dependency injection | Identify packages needing `opens` for the exact framework module |
| Service providers | JDBC drivers, plugins, codecs | Verify `uses`, `provides`, and how providers enter the graph |

Use `jdeps` to inspect static dependencies:

```shell
jdeps --summary --recursive --class-path "libs/*" app.jar
```

If the application already has modular JARs and a module path, you can check with:

```shell
jdeps --module-path mods --check com.acme.app
```

`jdeps` is useful for identifying package and module dependencies, but does not fully detect dependencies used solely via reflection, `Class.forName`, framework configuration, or service discovery. Combine static analysis results with Maven/Gradle dependency trees and knowledge of live runtime features.

## 3. Choosing the Module Name and Placing module-info.java

Module names typically follow reverse-DNS conventions, for example:

```text
com.acme.app
com.acme.core
com.acme.greeting
```

The module name must be stable because other modules may declare `requires` against it. Do not rename a module merely to match a temporary directory layout.

For a single-module application, source can be organized as:

```text
src/
├── module-info.java
└── com/
    └── acme/
        └── app/
            └── Main.java
```

In conventional Maven or Gradle projects, the main descriptor is typically placed at:

```text
src/main/java/module-info.java
```

Do not place `module-info.java` inside the `com.acme.app` package. The descriptor declares the module at the module source root, not as a class inside a package.

If a project has multiple named modules in one source tree using `--module-source-path`, each module has its own root directory and descriptor. Each named module requires a corresponding `module-info.java`.

## 4. Writing requires Based on Actual Dependencies

Suppose the application uses a greeting library and Java Logging:

```java
import com.acme.greeting.Greeter;
import java.util.logging.Logger;
```

The application descriptor might be:

```java
module com.acme.app {
    requires com.acme.greeting;
    requires java.logging;
}
```

`requires com.acme.greeting` lets the application module read the greeting module. `requires java.logging` lets the application use packages belonging to the logging module when exported.

`java.base` is an implicit dependency of every named module, so you do not need to write `requires java.base;`.

Important: `requires` **does not automatically grant access to every package** of the required module. The required module must still export the packages containing the public types you need. If you import a type from an unexported internal package, the compiler will block access even when `requires` is correct.

### requires, requires transitive, and requires static

There are three common forms:

```java
requires com.acme.greeting;
requires transitive com.acme.api;
requires static com.acme.annotations;
```

- `requires M;`: the current module can read `M`.
- `requires transitive M;`: in addition to reading `M`, modules reading the current module also gain readability to `M`. Typically used when a library's public API exposes types from `M`.
- `requires static M;`: a mandatory compile-time dependency that is optional at runtime. Suitable for certain compile-only annotations/APIs, if the design truly does not need them when running.

Do not add `transitive` to every dependency just for convenience. For an application module not consumed as a library, most ordinary dependencies only need `requires`.

## 5. Complete Example with Two Modules

This example includes library `com.acme.greeting` and application `com.acme.app`.

Source layout:

```text
project/
├── src-lib/
│   ├── module-info.java
│   └── com/acme/greeting/Greeter.java
└── src-app/
    ├── module-info.java
    └── com/acme/app/Main.java
```

Library descriptor:

```java
// src-lib/module-info.java
module com.acme.greeting {
    exports com.acme.greeting;
}
```

Library code:

```java
// src-lib/com/acme/greeting/Greeter.java
package com.acme.greeting;

public final class Greeter {
    private Greeter() {
    }

    public static String sayHello(String name) {
        return "Hello, " + name + "!";
    }
}
```

Application descriptor:

```java
// src-app/module-info.java
module com.acme.app {
    requires com.acme.greeting;
    requires java.logging;
}
```

Main class:

```java
// src-app/com/acme/app/Main.java
package com.acme.app;

import com.acme.greeting.Greeter;
import java.util.logging.Logger;

public class Main {
    private static final Logger LOG =
        Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        LOG.info(Greeter.sayHello("JPMS"));
    }
}
```

Notably, the application **does not need to export** package `com.acme.app` just for the JVM to run `Main.main` with `-m`. Exporting a package is only needed when other modules must access public APIs in that package.

## 6. Compiling, Packaging, and Running the Application

The following example uses the command line, suitable when run from the `project` directory. Create `build/library`, `build/app`, and `mods` directories before compiling.

Compile the library:

```shell
javac -d build/library \
  src-lib/module-info.java \
  src-lib/com/acme/greeting/Greeter.java
```

Package the library's modular JAR:

```shell
jar --create --file mods/com.acme.greeting.jar \
  -C build/library .
```

Compile the application with the module path pointing to the library:

```shell
javac --module-path mods -d build/app \
  src-app/module-info.java \
  src-app/com/acme/app/Main.java
```

Package the application:

```shell
jar --create --file mods/com.acme.app.jar \
  -C build/app .
```

Run using the module path:

```shell
java --module-path mods \
  --module com.acme.app/com.acme.app.Main
```

On Windows, trailing `\` characters in shell examples are not line-continuation syntax for PowerShell/cmd; run on one line or use the appropriate line-continuation syntax. If a module path contains multiple directories/JARs, the separator is `:` on Linux/macOS and `;` on Windows.

You can inspect the descriptors after packaging:

```shell
jar --describe-module --file mods/com.acme.app.jar
jar --describe-module --file mods/com.acme.greeting.jar
```

The output confirms the module name, dependencies, and package exports of the actual final artifacts.

## 7. exports Is for Libraries; Not Every Package Needs Exporting

A module should only export the packages other modules need to use as a public API.

Example:

```java
module com.acme.greeting {
    exports com.acme.greeting.api;
}
```

Implementation can live in `com.acme.greeting.internal` without being exported. A public class in an internal package still does not automatically become an API accessible to other modules.

If an application is split into UI, service, and data modules, each library module should expose only its API packages. A module holding startup logic, CLI, or entry points typically does not need to export all internal packages.

Qualified exports are meant for cases where only a specific module needs an API:

```java
module com.acme.greeting {
    exports com.acme.greeting.integration to com.acme.app;
}
```

This grants access to the package solely to `com.acme.app`, not to every module.

## 8. opens Is for Frameworks Using Deep Reflection

ORM frameworks, serializers, or dependency-injection containers may access non-public constructors/fields via reflection. When migrating to named modules, reflection behavior that worked on the classpath may be blocked by strong encapsulation.

Example:

```java
module com.acme.app {
    requires com.acme.greeting;

    opens com.acme.app.model to com.acme.json;
}
```

Here `com.acme.json` is the framework's **actual module name** in the example, not a package name. In practice, replace it with the module name used by your framework.

Distinctions:

- `exports P;` allows other modules to use public types in package `P` under standard Java access rules.
- `opens P;` opens package `P` for deep reflection at runtime.
- `opens P to M;` opens package `P` solely to module `M`.
- `open module X { ... }` opens all packages of the module, usually too broad for an application seeking tight encapsulation.

Do not use `opens` in place of `exports` when another module needs to import and call public APIs. Conversely, `exports` does not automatically allow frameworks to read private fields via deep reflection.

## 9. Declaring Service Consumers and Providers

JPMS integrates the `ServiceLoader` mechanism with module descriptors. If an application uses an SPI defined in an API module:

```java
package com.acme.spi;

public interface ReportExporter {
    void export(String report);
}
```

The application module declares its requirement:

```java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.ReportExporter;
}
```

The application can call:

```java
ServiceLoader<ReportExporter> exporters =
    ServiceLoader.load(ReportExporter.class);

for (ReportExporter exporter : exporters) {
    exporter.export("Report");
}
```

A provider in another module declares:

```java
module com.acme.export.csv {
    requires com.acme.spi;

    provides com.acme.spi.ReportExporter
        with com.acme.export.csv.CsvReportExporter;
}
```

The API module must export the package containing `ReportExporter`. The provider module does not need to export its implementation package just for `ServiceLoader` to instantiate the provider.

Separating service interfaces, consumers, and providers helps reduce coupling to concrete implementations. However, the provider module must actually be included in the appropriate graph or layer via root modules or service binding; `ServiceLoader` does not automatically create modules from an unresolved JAR.

## 10. Handling Unmodularized Libraries

During migration, many third-party libraries only provide traditional JARs.

When a JAR without `module-info.class` is placed on the module path, Java can handle it as an **automatic module**: a module assigned a name from metadata or the artifact filename, exporting all packages in the JAR, and having broader readability than an explicit module.

Example:

```java
module com.acme.app {
    requires legacy.utilities;
}
```

You must verify that `legacy.utilities` is indeed the artifact's module name, rather than guessing from Maven's `artifactId` without checking:

```shell
jar --describe-module --file libs/legacy-utils.jar
```

A library may declare a stable name via the `Automatic-Module-Name` manifest entry; otherwise, a name derived from the filename can change if the artifact is renamed.

Automatic modules are a useful intermediate step, not a permanent replacement for explicit modules. They have weak encapsulation and can create hurdles when building a runtime image with `jlink`. Prefer libraries with explicit module descriptors when architecture allows.

If a library can only run on the classpath, reconsider migration boundaries: a modular application should not assume it can declare `requires` against classpath JARs. Mixing classpath and module path requires explicit design rather than repeating the old launch pattern and merely adding `module-info.java`.

## 11. Avoiding Split Packages When Splitting Modules

A **split package** occurs when the same package has classes in multiple different modules. Example:

```text
com.acme.api:
    com.acme.shared.Customer

com.acme.impl:
    com.acme.shared.CustomerMapper
```

Both modules contain `com.acme.shared`. Depending on the graph and loaders, this can fail because a consumer reads the same package from multiple sources or due to package ownership rules.

The fix is separating packages along module boundaries:

```text
com.acme.api:
    com.acme.api.Customer

com.acme.impl:
    com.acme.impl.CustomerMapper
```

Or moving cohesive classes belonging to the same package into one unified module.

Adding `exports`, `opens`, or `--add-exports` does not solve split packages; those mechanisms change access permissions, not which module owns a package.

When splitting a large application into multiple named modules, determine **which single module will own each package** before creating descriptors en masse.

## 12. Adopting a Phased Migration Approach

You do not need to split the entire application into many modules right away. A realistic roadmap can be:

**Phase 1 — Inventory:** identify JARs in use, direct/transitive dependencies, entry points, reflection, service providers, and build-time-only libraries.

**Phase 2 — Create one application module:** add `module-info.java` for the application, declare `requires`, and try moving a set of dependencies onto the module path.

**Phase 3 — Address unmodularized dependencies:** prefer modular JARs, accept automatic modules as a transitional step where suitable, detect split packages, and verify stable module names.

**Phase 4 — Resolve encapsulation:** declare `exports` for exposed APIs, `opens` for frameworks that genuinely need reflection, and `uses`/`provides` for SPIs.

**Phase 5 — Run real tests:** compile, run unit/integration tests, run `java -m`, and verify module resolution and reflection/plugin code paths.

**Phase 6 — Optimize deployment:** once the graph is stable, consider building a runtime image with `jlink` if modules and dependency types permit.

Phased migration separates descriptor errors, dependency errors, reflection errors, and pre-existing application bugs.

## 13. Diagnostic Commands

Check modules available in the JDK:

```shell
java --list-modules
```

View a JDK module descriptor:

```shell
java --describe-module java.logging
```

View a packaged JAR's descriptor:

```shell
jar --describe-module --file mods/com.acme.app.jar
```

Trace application module resolution:

```shell
java --show-module-resolution \
  --module-path mods \
  -m com.acme.app/com.acme.app.Main
```

Inspect dependencies with `jdeps`:

```shell
jdeps --module-path mods --check com.acme.app
```

These commands answer different questions. `jar --describe-module` inspects the packaged module contract; `--show-module-resolution` shows the runtime graph; `jdeps` analyzes static dependencies. Combining them with specific error messages is far more effective than blindly adding `--add-exports` flags.

## 14. Common Errors After Adding module-info.java

| Symptom | Possible cause | Fix |
|---|---|---|
| `module not found: com.acme.greeting` | Dependency missing from module path or wrong module name | Check `--module-path`, descriptor, and artifact name |
| `package ... is not visible` | Missing `requires` on module or package not exported | Check readability and `exports` |
| `reads package ... from both ...` | Split package or multiple modules exporting the same package to consumer | Separate packages, remove duplicate dependencies, merge artifacts |
| `InaccessibleObjectException` | Framework needs deep reflection into an unopened package | Open the right package to the right framework module |
| `ServiceConfigurationError` | Missing `uses`, wrong provider declaration, or invalid provider | Check consumer/provider descriptors |
| `ClassNotFoundException` in plugin | Class/module not in the loader or layer the code uses | Check module resolution and class loading |
| JAR works on classpath but fails on module path | Changed package visibility, service discovery, or automatic module semantics | Check descriptor and deployment layout |
| `IllegalAccessError` at runtime | Compile and runtime differ in exports, module graph, or access modifiers | Align artifacts and verify module access at runtime |

When encountering an error, look for the **first root cause** in the stack trace or compiler output. Do not edit descriptors to open every package just to make one code path work temporarily.

## 15. module-info.java and Build Tools

With Maven, `module-info.java` typically belongs in `src/main/java`, while dependencies live in `pom.xml`. A compiler plugin compatible with the JDK can detect and compile modular sources when dependencies are organized properly.

With Gradle, the descriptor also typically lives in `src/main/java`. Ensure the Java toolchain and module-path inference are configured compatibly with your Gradle version.

There are two distinct configuration layers:

1. **Build file** specifies artifact coordinates, versions, repositories, and dependency scopes.
2. **Module descriptor** specifies module names to read, packages to export/open, and service bindings.

For example, Maven dependency `com.acme:greeting-library:1.0` does not mean the JPMS module name is `greeting-library`. The JAR's descriptor determines the module name.

For annotation processors, processor dependencies usually must be configured on a separate annotation processor path/module path rather than merely adding `requires` to the application module.

## 16. Pre-Release Checklist

An application module is ready for the module path when you can confirm:

- `module-info.java` uses consistent module names and declares actual dependencies.
- Modular JARs are distributed with expected descriptors and module names.
- No conflicting split packages exist in the graph.
- API packages are intentionally exported; implementation packages remain encapsulated.
- Frameworks needing reflection have appropriate `opens`.
- Service consumers/providers have matching `uses` and `provides`.
- The application compiles and runs with `java --module-path ... --module ...`.
- The test suite genuinely covers JDBC, reflection, serializers, plugins, and dynamic configuration features if present.
- Build output and runtime use identical dependency versions, avoiding cases where compilation succeeds but runtime lacks exports or APIs.
- Final artifacts are checked with `jar --describe-module` and the graph with `--show-module-resolution`.

**Conclusion:** `module-info.java` is the application's module contract, not a list of JARs. Start with a small descriptor, declare accurate `requires`, use `exports`/`opens` only where genuinely needed, and verify by compiling and running on the module path. That approach migrates an application from the classpath to JPMS step by step while keeping module boundaries understandable and maintainable.
