# Choosing Classpath or Module Path in Java

## 1. Two Mechanisms for Finding and Organizing Dependencies

Java has two common ways to provide classes and libraries to the compiler or the JVM:

- **Classpath** is the traditional mechanism. It lists directories containing classes and JARs that the application needs to locate.
- **Module path** is the mechanism of the Java Platform Module System (JPMS), introduced in Java 9. It lists named modules so the compiler and JVM can resolve dependency relationships between them.

Both help Java locate bytecode, but they differ in how they express boundaries and access permissions. The classpath primarily answers the question "where is the class located?". The module path also answers "which module requires which module, which packages are exported publicly, and which packages are only for reflection?".

There is no mandatory choice for every project. Traditional Java applications can continue using the classpath. Applications that want to use JPMS need module descriptors and a module path for the modules they depend on.

## 2. How Does the Classpath Work?

The classpath is a list of locations for searching classes and resources. Each entry is typically:

- A directory with a package structure.
- A JAR file.
- A wildcard such as `lib/*` to include the JARs in the lib directory on the classpath.

For example, a project has:

```text
legacy-app/
├── app.jar
├── lib/
│   ├── json.jar
│   └── logging.jar
└── config/
```

Running the application on Windows:

```powershell
java -cp "app.jar;lib/*" com.example.app.Main
```

On Linux or macOS:

```bash
java -cp 'app.jar:lib/*' com.example.app.Main
```

The classpath entry separator is a semicolon (`;`) on Windows and a colon (`:`) on Linux/macOS. Use quotes so the shell does not expand the wildcard unexpectedly.

You can use the equivalent forms `-cp`, `-classpath`, or `--class-path`. When no classpath is explicitly passed, the Java launcher uses the `CLASSPATH` environment variable if set; otherwise, it defaults to the current directory. In build scripts and CI, it is best to specify the classpath explicitly so results do not depend on machine configuration.

The classpath is also used during compilation:

```bash
javac --release 17 -cp "lib/json.jar" -d out src/com/example/app/Main.java
```

`javac` writes classes to the `out` directory. At runtime, that directory and the dependency JARs must appear on the classpath.

## 3. The Unnamed Module and Limitations of the Classpath

Since Java 9, code loaded from the classpath belongs to the **unnamed module** of the corresponding class loader. This module has no name and does not require `module-info.java`.

The unnamed module can read observable modules, and its packages are exported/opened according to the rules of the unnamed module. However, code on the classpath does not receive explicit dependency boundaries like named modules do.

The classpath does not declare:

- Which module this module requires.
- Which packages are the public API of a module.
- Which packages are only opened for reflection.
- Which dependencies are required at compile time versus only needed at runtime.

Therefore, classpath applications often rely on conventions, dependency managers, and classpath ordering to avoid conflicts.

A classpath can contain multiple JARs declaring the same package. Two JARs can also contain a class with the same name. When the class loader finds the first class in search order, that version can shadow the other. This is a source of hard-to-diagnose errors when an application uses multiple versions of a library.

## 4. How Does the Module Path Work?

The module path contains modules that the compiler or JVM can observe and resolve. A module path entry can be:

- A modular JAR with a `module-info.class` file at the root of the archive.
- An unpacked module directory (exploded module).
- A JAR without a descriptor that is treated as an automatic module when placed on the module path.

Example of running a modular application:

```bash
java --module-path mods -m com.example.app/com.example.app.Main
```

`--module-path` (short form `-p`) specifies where to find modules. The `-m` option specifies the launch module and main class. The `module/class` syntax tells the launcher which module the main class belongs to.

Unlike the classpath, the module path enables the JVM to build a module graph. The module graph determines the root modules, required modules, and readability relationships between them. If a required module is missing or there is a module/package conflict, resolution can fail before `main` runs.

## 5. Module Descriptor: module-info.java

An explicit module declares its name and directives in a `module-info.java` file. This file resides at the source root of the module, not inside a regular package.

Example:

```java
module com.example.greeter {
    exports com.example.greeter;
}
```

An application module can require a library module:

```java
module com.example.app {
    requires com.example.greeter;
}
```

Important directives:

| Directive | Meaning |
|---|---|
| `requires` | Declares a module dependency |
| `requires transitive` | Consumer modules can also read this dependency through the current module |
| `requires static` | Dependency needed at compile time, optionally absent at runtime |
| `exports` | Exposes a package for other modules to access at compile time and runtime |
| `opens` | Opens a package for deep reflection at runtime |
| `uses` | Declares that the module uses a service |
| `provides ... with ...` | Registers an implementation for a service |

A `public` class is not necessarily accessible to other modules. The package containing the class must be exported by the module via `exports`, and the consumer module must be able to read the module providing that package.

## 6. Readability and Accessibility Are Two Separate Conditions

The module system distinguishes two questions:

1. **Readability:** Does the current module have a read relationship to the module containing the type it wants to use?
2. **Accessibility:** Are the package and type being used appropriately exposed by the other module?

For example, module A declares `requires B` to read module B. However, if B does not `exports` the package containing the desired class, A still cannot access that class through normal Java APIs.

`exports` controls API access between modules. `opens` serves deep reflection, such as when a framework needs to read private fields to inject or deserialize. `opens` does not replace `exports` when code needs to import and call types in a package at compile time.

You can open a specific package for a framework:

```java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.internal to com.example.json;
}
```

Only the `com.example.json` module is granted open access to the `internal` package under the directive above. Using qualified opens preserves encapsulation better than opening the entire module.

`open module` opens all packages for deep reflection, but does not mean all packages automatically become exported APIs at compile time. Use it only when a framework truly requires broad reflection permissions.

## 7. Direct Comparison of Classpath and Module Path

| Criterion | Classpath | Module path |
|---|---|---|
| Search unit | Directories and JARs | Named modules, automatic modules, exploded modules |
| Descriptor | Optional | Explicit modules have `module-info` |
| Dependency graph | Not declared in Java | `requires` and module resolution |
| Encapsulation | Packages have no module boundary | `exports` and `opens` |
| Module name | Unnamed module | Stable module name |
| Split package | Can occur across multiple JARs | Package conflicts between named modules are controlled |
| Legacy dependencies | Directly compatible | Can be used via automatic module or classpath bridge |
| Launch | Main class name | Module and main class |
| Best suited for | Legacy applications, scripts, unmodularized libraries | Applications with clear module boundaries |

The module path provides stronger architectural control but requires managing module names, descriptors, and package exports. The classpath readily accommodates legacy libraries and usually requires fewer configuration changes.

## 8. When Should You Choose the Classpath?

The classpath is usually a reasonable choice when:

- The application does not have module descriptors yet and does not need module boundaries.
- A legacy system has many older dependencies without stable module names.
- Frameworks or plugins rely on loading classes from the classpath.
- The project is small, such as learning Java, a command-line tool, or a standalone script.
- Modularization does not yet bring enough benefit to outweigh migration costs.

Keeping the classpath does not mean the application cannot use a newer JDK. Java 17+ still runs classpath applications normally. JPMS is an architectural choice, not a prerequisite for using modern Java language features.

With the classpath, you still need to manage dependency versions, avoid JARs with duplicate classes, control classpath order, and verify the runtime classpath in CI.

## 9. When Should You Choose the Module Path?

The module path is worth considering when:

- An application has multiple modules developed by independent teams or groups.
- Explicit dependency declarations between parts are needed.
- You want to restrict public packages and hide implementation packages.
- Missing dependencies or split packages need to be detected early.
- You need to integrate Java ServiceLoader according to module descriptors.
- You want to prepare the application for a custom runtime image using `jlink`.
- Reflection and access permissions between modules need to be controlled.

Do not modularize just to rename the classpath to the module path. The main value is creating verifiable boundaries. If all packages remain broadly exported, module descriptors do not reflect the actual API, and dependencies are out of sync, the benefits diminish.

## 10. Explicit Module, Automatic Module, and Unnamed Module

Java has three common dependency cases:

| Type | Identification | Characteristics |
|---|---|---|
| Explicit module | JAR with `module-info.class` | Explicitly declares dependencies and package exports |
| Automatic module | JAR without a descriptor placed on the module path | Module name determined from manifest or JAR filename; exports/opens all packages and reads observable modules |
| Unnamed module | Code/JAR placed on the classpath | Has no module name; compatible with pre-Java 9 organization |

An explicit module is the best target when a library is ready for modularization.

An automatic module is a useful bridge when a library does not yet have `module-info.java` but needs to be required via `requires` by an explicit module. It has no explicit dependency list and opens all packages, so it does not provide strong encapsulation like an explicit module.

The unnamed module is suitable for classpath applications. Explicit modules do not automatically read the unnamed module; bridging the two models requires special module-system options or moving dependencies to appropriate modules.


## 11. Automatic-Module-Name and Stable Module Names

A JAR without `module-info.class` can be treated as an automatic module when placed on the module path. The module name can be taken from the `Automatic-Module-Name` attribute in the manifest. If this attribute is absent, Java derives the name from the JAR filename according to module naming rules.

Example of adding a stable name for a library being migrated gradually:

```groovy
tasks.named('jar') {
    manifest {
        attributes('Automatic-Module-Name': 'com.example.greeter')
    }
}
```

Then another module can declare:

```java
module com.example.app {
    requires com.example.greeter;
}
```

`Automatic-Module-Name` does not create an explicit module descriptor. The JAR remains an automatic module; it simply has a stable module name so consumers do not depend on the JAR filename. When the library releases an actual `module-info.class`, the descriptor will provide explicit module metadata.

Inspect the module name of a JAR:

```bash
jar --describe-module --file lib/greeter.jar
```

Do not use Maven `artifactId` or Gradle project names to guess a module name. These names can differ. Read the descriptor or manifest of the artifact itself.

## 12. Why Can Unmodularized Libraries Cause Friction During Migration?

An explicit module cannot directly declare `requires` on the unnamed module. For example, if an older library is just a plain JAR kept on the classpath, a new module cannot write `requires legacy.library` to read it.

Approaches to handle this:

1. Upgrade the library to a version with an explicit module descriptor.
2. Use a library version with `Automatic-Module-Name` and place it on the module path.
3. Add `Automatic-Module-Name` when you publish the library yourself.
4. Create an adapter module for the legacy dependency if needed.
5. Use `--add-reads` as a controlled compatibility measure during the transition.

An automatic module can read the unnamed module in some situations, but this is a one-way bridge more useful for migration; it should not be treated as a long-term module design. Before migrating dependencies, check whether the actual library has a module descriptor or an automatic module name.

## 13. Split Packages and Duplicate Classes

The classpath can contain the same package across multiple JARs, or two JARs can contain the same class. Classpath order can determine which class gets loaded. This makes errors environment-dependent and hard to reproduce.

The module path controls packages at the module level. Two named modules cannot both contribute the same package in a valid module configuration. Some legacy structures that rely on split packages therefore cannot be moved directly to JPMS without restructuring.

How to investigate:

- List actual JARs and module dependencies.
- Find duplicate class names or packages split across artifacts.
- Use `jdeps` to analyze dependencies.
- Use `jar --describe-module` to inspect module names and packages.
- Split packages or consolidate related classes into a single module.

Do not work around split packages by changing module path order. Fix the artifact structure or choose an appropriate compatibility run mode.

## 14. Compiling an Application Using the Classpath

Example with a `Greeter` library and a `Main` class. Neither file has `module-info.java`.

```java
package com.example.greeter;

public final class Greeter {
    private Greeter() { }

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

```java
package com.example.app;

import com.example.greeter.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.greet("JPMS"));
    }
}
```

Compile the library and package it into a JAR:

```bash
javac --release 17 -d out/lib src/com/example/greeter/Greeter.java
jar --create --file lib/greeter.jar -C out/lib .
```

Compile the application against the JAR:

```bash
javac --release 17 -cp lib/greeter.jar -d out/app src/com/example/app/Main.java
```

Run on Windows:

```powershell
java -cp "out/app;lib/greeter.jar" com.example.app.Main
```

Run on Linux/macOS:

```bash
java -cp 'out/app:lib/greeter.jar' com.example.app.Main
```

Exact stdout:

```text
Hello, JPMS!
```

Both the library and the application belong to the unnamed module of their respective class loader. There is no need to declare `requires` or `exports` relationships.

## 15. Compiling Two Explicit Modules

Create the source tree:

```text
src/
├── com.example.greeter/
│   ├── module-info.java
│   └── com/example/greeter/Greeter.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

Library descriptor:

```java
module com.example.greeter {
    exports com.example.greeter;
}
```

Application descriptor:

```java
module com.example.app {
    requires com.example.greeter;
}
```

The two Java files `Greeter` and `Main` use the same content as in the classpath example. Compile both modules at once:

```bash
javac --release 17 --module-source-path src -d out -m com.example.greeter,com.example.app
```

`--module-source-path` specifies the source structure of the modules. `-m` lists the modules to compile. Output is organized into `out/com.example.greeter` and `out/com.example.app` directories.

Run directly from exploded modules:

```bash
java --module-path out -m com.example.app/com.example.app.Main
```

Exact stdout:

```text
Hello, JPMS!
```

Package each module into a modular JAR:

```bash
jar --create --file mods/com.example.greeter.jar -C out/com.example.greeter .
jar --create --file mods/com.example.app.jar -C out/com.example.app .
java --module-path mods -m com.example.app/com.example.app.Main
```

The output is still `Hello, JPMS!`. The module path can contain exploded modules or modular JARs. The module path must resolve properly and module names must match `requires` directives.

## 16. Gradle and Module Path Inference

The Gradle Java Plugin supports JPMS. When a source set has `module-info.java` and a dependency is an eligible module, Gradle can automatically place the dependency on the module path instead of the classpath.

You can declare it explicitly:

```groovy
plugins {
    id 'application'
}

java {
    modularity.inferModulePath = true
}

application {
    mainModule = 'com.example.app'
    mainClass = 'com.example.app.Main'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

File `src/main/java/module-info.java`:

```java
module com.example.app {
}
```

File `src/main/java/com/example/app/Main.java`:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Gradle module path: OK");
    }
}
```

Run with Gradle Wrapper:

```bash
./gradlew clean run
```

Exact stdout:

```text
Gradle module path: OK
```

The Gradle Java Plugin enables module path inference by default in modern versions; declaring it explicitly helps build script readers see the project's intent. It can be disabled with `modularity.inferModulePath = false` for special compatibility cases, but consider the impact on module compilation and launch.

Gradle recognizes modules based on `module-info.class` or the JAR's `Automatic-Module-Name` attribute. Dependencies without module metadata may still be placed on the classpath. When the application is an explicit module, dependencies in the unnamed module may not be readable; you need to upgrade them, create automatic modules, or configure an intentional bridge.

## 17. Synchronizing module-info.java with Gradle Dependencies

When using `java-library`, dependency declarations in Gradle and `module-info.java` need to reflect the same intent.

| Directive in module-info | Gradle configuration | Meaning |
|---|---|---|
| `requires` | `implementation` | Dependency for module implementation |
| `requires transitive` | `api` | Consumers also need to read the dependency |
| `requires static` | `compileOnly` | Needed at compile time, not necessarily at runtime |
| `requires static transitive` | `compileOnlyApi` | Compile-time API dependency not needed at runtime |

Example:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'org.example:internal-helper:1.4'
    api 'org.example:public-api:2.0'
}
```

```java
module com.example.library {
    requires org.example.internal.helper;
    requires transitive org.example.public.api;
}
```

Gradle does not currently verify that all Gradle declarations and module descriptors are always in sync. Review both when adding or changing dependencies. If Gradle has a dependency but the module descriptor is missing `requires`, module compilation can fail. If the module descriptor requires a module but Gradle does not provide it on the module path, the build also fails.

## 18. ServiceLoader in the Module System

JPMS supports declaring service providers directly in the descriptor:

```java
module com.example.api {
    exports com.example.api;
}
```

```java
module com.example.provider {
    requires com.example.api;
    provides com.example.api.GreetingService
        with com.example.provider.DefaultGreetingService;
}
```

The module using the service declares:

```java
module com.example.app {
    requires com.example.api;
    uses com.example.api.GreetingService;
}
```

`uses` indicates that the module needs a service; `provides ... with ...` registers an implementation. This allows the module resolver and `ServiceLoader` to work according to the module graph, without relying solely on `META-INF/services` files as in the traditional classpath approach.

When migrating an application using `ServiceLoader` from the classpath to the module path, check provider descriptors and how frameworks package services. A service that is not declared properly may not appear when the modular application runs.

## 19. Reflection, exports, and opens

Dependency injection frameworks, JSON mappers, ORMs, and serialization libraries may need reflection into application packages.

- `exports` exposes public/protected types and members of a package to other modules.
- `opens` allows deep reflection into a package at runtime.
- `open module` opens all packages for reflection, but does not automatically turn all packages into compile-time APIs.

Example:

```java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.json;
}
```

If a framework reports `InaccessibleObjectException`, check whether the package has been opened to the right module. Do not open the entire module immediately if only one package needs reflection.

Compatibility flags can help older applications:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp app.jar com.example.Main
```

`ALL-UNNAMED` applies to code in unnamed modules, typically code on the classpath. `--add-opens` grants runtime reflection permission; `--add-exports` adjusts package access at compile/runtime; `--add-reads` adds a readability relationship. These are controlled migration or integration measures and should not replace proper module descriptors.

## 20. Module Diagnostic Tools

The following commands are useful when building or running with the module path:

```bash
jar --describe-module --file mods/com.example.greeter.jar
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
java --module-path mods --validate-modules
jdeps --print-module-deps app.jar
```

| Tool | Purpose |
|---|---|
| `jar --describe-module` | View module name, exports, and requires of a JAR |
| `java --show-module-resolution` | Print the JVM's module resolution process |
| `java --validate-modules` | Check for conflicts on the module path |
| `jdeps` | Analyze dependencies between classes, packages, and modules |
| `javac -verbose` | View compilation details and class/module searches |

Use `jdeps` to discover dependencies before migration, but read and verify the results before writing `module-info.java`. Bytecode analysis tools do not replace understanding the application's public API, reflection, and service providers.

## 21. Common Errors

| Error or Symptom | Cause | How to Check |
|---|---|---|
| `ClassNotFoundException` | Missing JAR/directory on the classpath | Check `-cp` and paths |
| `NoClassDefFoundError` | Dependency present at compile time but missing at runtime | Compare compile and runtime paths |
| `FindException: Module not found` | Missing module or wrong module name | Use `jar --describe-module` |
| `ResolutionException` | Conflicting module graph or packages | Use `--validate-modules` |
| `package ... is not visible` | Module does not export the package or is not readable | Check `requires` and `exports` |
| `IllegalAccessError` | Runtime access to a non-exported type/package | Check descriptors and module path |
| `InaccessibleObjectException` | Reflection into an unopened package | Check `opens` or `--add-opens` |
| Automatic module not found | `requires` name differs from actual module name | Check manifest and JAR filename |
| Split package | Multiple modules contribute the same package | Split packages or restructure modules |
| Gradle places legacy JAR on classpath | JAR lacks module descriptor and automatic name | Check module path inference and metadata |
| ServiceLoader cannot find provider | Missing `uses`/`provides` or service metadata | Check module descriptor |
| Works in IDE, fails in CI | IDE uses different classpath/module path than build script | Run using Gradle Wrapper and pinned JDK |

## 22. Roadmap for Migrating from Classpath to Module Path

You should not migrate the entire application at once if the dependency graph is complex. A controlled roadmap:

1. **Inventory:** record the JDK, libraries, plugins, frameworks, reflection, and service providers in use.
2. **Analyze dependencies:** use `jdeps` and inspect each JAR's manifest.
3. **Choose module boundaries:** identify public packages and internal packages.
4. **Name modules:** prefer stable names; use `Automatic-Module-Name` for transitional libraries.
5. **Create descriptors:** declare `requires`, `exports`, `opens`, `uses`, and `provides` as needed.
6. **Move dependencies:** place explicit/automatic modules on the module path; handle legacy JARs remaining on the classpath.
7. **Run tests:** compile, unit tests, integration tests, reflection, and `ServiceLoader`.
8. **Verify runtime:** confirm launcher commands, module resolution, and the CI environment.
9. **Narrow bridges:** gradually remove `--add-reads`, `--add-exports`, and `--add-opens` flags once module boundaries are fixed.
10. **Package:** if needed, use `jlink` to create a runtime image from the controlled module graph.

Keep module names stable across versions. Changing a module name is a breaking change for consumers because `requires` depends on that name.

## 23. Decision Checklist

- [ ] Does the application need module boundaries and an explicit dependency graph?
- [ ] Do the libraries have module descriptors or `Automatic-Module-Name`?
- [ ] Are any packages split across multiple JARs?
- [ ] Do any frameworks need deep reflection?
- [ ] Are service providers declared properly?
- [ ] Are module names stable and independent of JAR filenames?
- [ ] Do Gradle dependencies match module descriptors?
- [ ] Do both compile and runtime use the right paths?
- [ ] Does CI use the same JDK and Gradle Wrapper as the development environment?
- [ ] Can temporary access-opening flags be removed after migration?

## 24. Summary

The classpath is the traditional mechanism, easy to use and suitable for legacy applications or unmodularized dependencies. The module path adds a module graph, explicit dependencies, and package-level encapsulation.

Choose the classpath when the application does not yet need module boundaries and compatibility with older libraries is the priority. Choose the module path when you want to control dependencies, package exports, reflection, and service integration at the module level. When migrating, understand explicit modules, automatic modules, and unnamed modules; verify both module descriptors and build configuration.

**Official References:**

- [Oracle JDK 24 — javac command and module source path](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
- [Oracle Java Language Specification — Packages and Modules](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html)
- [Oracle Java SE — ModuleDescriptor and automatic modules](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/ModuleDescriptor.html)
- [Oracle Java SE — Module and unnamed modules](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html)
- [Gradle User Manual — Java Library Plugin and Java Module System](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle User Manual — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Oracle JDK Migration Guide — Strong Encapsulation](https://docs.oracle.com/en/java/javase/26/migrate/jdk-migration-guide.pdf)