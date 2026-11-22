# Class Path, Module Path, and Module Types

When upgrading Java, especially from pre-Java 9 applications to a modern JDK, you cannot simply swap the JDK and keep the same packaging and library loading approach without understanding the **class path** and **module path**. Both mechanisms can coexist within a single JVM process, but they apply different rules for code identification, dependency resolution, module readability, package accessibility, and reflection.

The **class path** is the traditional model: the application loads classes from directories or JARs, most of which belong to *unnamed modules*. The **module path** is the input to the Java Platform Module System (JPMS): the JVM and Java tools locate and resolve *named modules*, thereby building a module graph with read/readable relationships and clear access boundaries. A regular JAR placed on the module path can become an *automatic module*, whereas when placed on the class path it still belongs to an unnamed module. Therefore, **the same JAR, placed in two different locations, can have different roles**.

The goal of this article is to accurately distinguish the mechanisms above, identify the module types in JPMS, and learn how to design a Java compatibility migration roadmap without causing class loading, split package, module resolution, or reflective access errors.

## 1. Class Path and Module Path Solve Two Different Problems

### 1.1. Class Path: Finding Classes/Resources by Path

Before JPMS, programs were typically run as follows:

```bash
java -cp "app.jar:lib/*" com.example.Main
```

The `-cp` (or `-classpath`, `--class-path`) option provides a list of directories and JARs for class loaders to locate classes/resources. On Linux/macOS, class path elements are typically separated by `:`; on Windows, `;` is used:

```powershell
java -cp "app.jar;lib/*" com.example.Main
```

The `*` in a class path wildcard is expanded by the launcher to place the JARs in the directory onto the class path according to the Java launcher rules. Ordering and class/resource conflicts still need to be controlled; you should not rely on wildcards for stable dependency resolution.

The traditional class path has no concept of `requires`, `exports`, or a module graph for each JAR. If a library is on the class path and a class loader can see it, code can reference appropriate public types according to Java's access rules. There is no separate module boundary for each JAR placed on the class path.

However, that **does not mean the class path bypasses all protection rules of a modern JDK**. Starting in Java 9, the Java runtime itself is also organized into modules. Packages belonging to JDK named modules may not be exported/opened to class path applications; in particular, strong encapsulation in a modern JDK cannot be bypassed merely by placing the application on the class path.

### 1.2. Module Path: Finding Modules and Building the Module Graph

A modular application can be run with:

```bash
java --module-path mods -m com.example.app/com.example.app.Main
```

Here:

- `--module-path` (short form `-p`) tells the module finder where to find modules.
- `mods` can contain modular JARs or compiled module directories with the appropriate structure.
- `-m` (or `--module`) specifies the startup module, and may specify the main class after `/`.
- The JVM resolves a set of modules consisting of root modules and their dependencies according to JPMS rules, rather than treating all JARs on the module path as a flat set of classes by default.

A named module can declare: which modules it requires, which packages are publicly accessible, which packages allow deep reflection, and which services are consumed/provided.

Importantly: **being present on the module path does not guarantee being resolved into the module graph**. Depending on how the application is launched and the root modules, a JAR may exist on the path yet not be read or even participate in the graph. When debugging, distinguish between “module file exists”, “module is resolved”, and “module is readable/exported”.

### 1.3. Operational-Level Comparison

| Criterion | Class path | Module path |
|---|---|---|
| Core entity | Classes, JARs, and resources | Named modules (explicit/automatic) |
| Configuration unit | List of paths/JARs | Module descriptor or automatic module name |
| Dependency relationships | Not declared via JPMS between class path JARs | `requires`, `requires transitive`, `requires static` |
| API access | Primarily based on visibility/class loader | Also considers readability and `exports` |
| Deep reflection | No separate module boundary between class path JARs; still subject to JDK named module boundaries | Requires `opens` or appropriate package-opening permissions |
| Package conflicts | Multiple JARs can contain the same package, easily causing shadowing | Split packages among resolved named modules are generally rejected |
| Loading libraries without descriptors | Belongs to an unnamed module | Can become an automatic module |
| Launch input | `-cp` + main class | `-p` + `-m` / module main class |
| Migration goal | Continue running legacy systems | Establish clear module boundaries and control dependencies |

## 2. Names, Descriptors, and Module Identity

JPMS has several terms that are easily confused:

- **Package:** a group of Java types sharing the same package name, for example `com.example.catalog.api`.
- **Class binary name:** the binary name of a class, for example `com.example.catalog.api.Product`.
- **Module name:** the module name used by JPMS, for example `com.example.catalog`.
- **Module descriptor:** the `module-info.java` or `module-info.class` declaration.
- **Module graph:** the set of resolved named modules and their established readability/exports relationships.
- **Class loader:** the component that defines classes at runtime; class identity consists of the binary name and the defining class loader.

A package is not automatically a module. Neither does a Maven group ID or a Gradle project name automatically become a module name. A JAR can contain multiple packages, and a module can be built from a JAR or a compiled module directory.

In systems using custom class loaders, a class with the same binary name loaded by two different defining class loaders can still be two incompatible types. Therefore, JPMS does not replace understanding the class loader hierarchy; it adds an organizational and access-control layer.

## 3. Unnamed Module: Code Residing on the Class Path

### 3.1. A Class Path JAR Does Not Become a Named Module

Suppose:

```text
lib/
  legacy-utils.jar
  jdbc-helper.jar
app/
  Main.class
```

The command:

```bash
java -cp "app:lib/*" com.example.Main
```

places the classes from `app` and the class path JARs into the unnamed modules corresponding to their defining class loaders. In a simple launcher configuration, most classes of the application class loader reside in that loader's unnamed module.

It should not be phrased as “there is only one unnamed module across the entire JVM”: each class loader has its own unnamed module. This matters for application servers, plugin frameworks, test runners, and custom class loaders.

### 3.2. Readability and Accessibility of Unnamed Modules

An unnamed module is a compatibility mechanism for non-modularized code:

- It can read the modules permitted by JPMS rules at runtime, including resolved named modules.
- Packages in an unnamed module are exported and opened to other modules under the JPMS model.
- However, an **explicit named module does not automatically read unnamed modules**. This interaction direction is often what causes difficulties when converting an application into a named module.

The fact that packages of an unnamed module are considered open does not mean the application can perform deep reflection into any package in the JDK. Packages belonging to JDK named modules remain controlled by `exports`/`opens` and strong encapsulation rules.

### 3.3. When Should You Continue Using the Class Path?

Keeping the class path can be a reasonable choice when:

- The application has many legacy libraries without module descriptors and relies on classpath scanning.
- Frameworks or plugins require dynamic class loading mechanisms that are not yet well-compatible with modularization.
- The team prioritizes upgrading the JDK before re-partitioning module boundaries.
- Reflection accesses, bytecode generation, agents, or complex dependencies have not yet been inventoried.

There is no mandatory requirement that every application running on Java 17/21 must convert itself into a named module. Modern JDKs still support the class path. Migrating from Java 8 to Java 17/21 and migrating from the class path to the module path are two distinct decisions; they can be separated into two phases to reduce risk.

## 4. Explicit Named Module: A Module with `module-info.java`

### 4.1. Basic Module Descriptor

An explicit module has a descriptor in source:

```java
module com.example.catalog {
    requires java.sql;

    exports com.example.catalog.api;
}
```

The directives mean:

- `module com.example.catalog`: identifies the named module.
- `requires java.sql`: declares a dependency on the `java.sql` module.
- `exports com.example.catalog.api`: grants other modules access to the public types/members of the exported package according to normal visibility rules.

An unexported package `com.example.catalog.internal` is an implementation detail even if the classes inside it are `public`. From another module, `public` is not sufficient if the package is not exported to the caller.

The module descriptor resides in `module-info.class` in the compiled artifact. When a JAR has an appropriate descriptor and is placed on the module path, it is an explicit named module.

### 4.2. Qualified Exports: Exposing an API Only to Specified Modules

Exports can be restricted:

```java
module com.example.catalog {
    exports com.example.catalog.api;

    exports com.example.catalog.spi
        to com.example.catalog.testkit;
}
```

In the example above, the `api` package is exported to any module that can read `com.example.catalog`. The `spi` package is exported only to the named module `com.example.catalog.testkit`.

A qualified export is not a form of data encryption or a complete security sandbox. It is an access boundary at the language/JVM module level, helping control dependencies and keep APIs internal.

### 4.3. `opens` for Deep Reflection

Serialization, dependency injection, and ORM frameworks often need to access non-public fields or constructors via reflection. JPMS distinguishes:

- `exports`: provides normal access to the package's public API.
- `opens`: allows deep reflection into the package within the scope of the specified modules.
- `open module`: opens all packages of the module for deep reflection, which is usually a broader choice that warrants careful consideration.

Example:

```java
module com.example.orders {
    requires com.fasterxml.jackson.databind;

    exports com.example.orders.api;
    opens com.example.orders.model
        to com.fasterxml.jackson.databind;
}
```

The `model` package may not be exported as a compile-time API, yet it allows Jackson to perform deep reflection. You must use the framework's exact module name in the actual environment rather than guessing from the Maven artifact ID.

`exports` does not replace `opens` for all types of deep reflection, and `opens` does not mean a public compile-time API for other modules. A package can be both exported and opened if both purposes are needed.

### 4.4. `requires transitive` and `requires static`

Example:

```java
module com.example.catalog.api {
    requires transitive com.example.types;
    requires static java.compiler;

    exports com.example.catalog.api;
}
```

- `requires transitive`: expresses a dependency whose readability is propagated; modules that read `com.example.catalog.api` can read `com.example.types` under JPMS rules. This is suitable when a public API uses types from the dependent module and you want consumers to be able to use them without declaring a direct dependency everywhere.
- `requires static`: a dependency that must be checked at compile time but may be absent at runtime, commonly seen with annotations or compile-only libraries.

These two modifiers are not replicas of Maven scopes or Gradle configurations. You need to understand both the module graph and the build tool's dependency graph. A module may be declared in the build file yet not resolved at runtime, or vice versa.

### 4.5. `open module` Is Not a New Module Kind in Terms of Identity

You can declare:

```java
open module com.example.legacy.bridge {
    requires java.sql;
    exports com.example.legacy.bridge.api;
}
```

This is still an **explicit named module**. The `open` keyword makes all packages in the module open for deep reflection. It does not automatically export unexported packages as compile-time APIs. You cannot write explicit `opens` directives inside an `open module` because all packages are already open.

During migration, `open module` can be used as a transitional solution for frameworks needing broad reflection, then gradually narrowed down to `opens ... to ...` once the modules needing access are known. Opening all packages should be a deliberate decision.

## 5. Automatic Module: A JAR Without a Descriptor on the Module Path

### 5.1. A Legacy JAR Can Be Named by JPMS

Suppose the library `common-tools.jar` does not contain `module-info.class`. When placed on the class path:

```bash
java -cp "app:lib/common-tools.jar" com.example.Main
```

it belongs to the class loader's unnamed module.

However, when that same JAR is placed on the module path:

```bash
java --module-path lib -m com.example.app/com.example.app.Main
```

the module finder can treat it as an **automatic module** (if the JAR is valid and has a determined module name). An automatic module has a **name** so that other modules can declare `requires`, but it does not have a vendor-authored `module-info.class` descriptor.

### 5.2. Where Does the Automatic Module Name Come From?

JPMS can derive the module name from:

1. The `Automatic-Module-Name` attribute in `META-INF/MANIFEST.MF`.
2. If absent, the name is derived from the JAR file name according to the module finder's rules, typically stripping the version part and normalizing the name.

Example manifest:

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.commons
```

In that case, the module has the stable name `com.example.commons` even though the JAR does not yet contain a module descriptor.

**You should not depend on a name automatically derived from the JAR file name** when building a long-term modular API. When the file/artifact name or packaging rules change, the module name may change and break consumers' `requires` directives. You should verify with tooling and prefer a stable name published by the vendor.

### 5.3. Access Permissions of an Automatic Module

Automatic modules are designed for migration convenience:

- Has a module name and participates in the module graph.
- Can be referenced by other named modules via `requires <module-name>`.
- Exports and opens its packages according to automatic module rules.
- Has flexible readability to interact with named modules and the legacy class path.
- Can be derived from an existing JAR without modifying source code.

This is a **bridge**, not equivalent to a well-designed explicit module. An automatic module lacks the fine-grained package export/open boundaries of `module-info.java` and can still suffer from split packages, class conflicts, unstable module names, or unresolved dependencies.

### 5.4. Automatic Modules Do Not Solve All Legacy Dependencies

An automatic module can depend on classes from unnamed modules; this fits the transitional model. However, the fact that module finder/resolution can load an automatic module does not prove that every dependency outside the module path is present at runtime.

With a hybrid configuration, you must check everything:

- Which legacy libraries are on the class path.
- Which named/automatic modules are on the module path.
- Which root modules are resolved.
- Which names are assigned to automatic modules.
- Whether named consumers read that exact module.
- Whether the automatic module calls classes that are unreachable via class loaders or missing dependencies.

You should not turn the entire `lib/` directory into the module path in a single step and assume the system will adapt automatically. Some older JARs have split packages or unsuitable metadata that can cause resolution to fail.

## 6. Module Types in JPMS: Summary Table

| Type | Has a name? | Has `module-info.class`? | Common location | Package export/open | Use case |
|---|---|---|---|---|---|
| Explicit named module | Yes | Yes | Module path or runtime image | Per descriptor | Modularized APIs/applications |
| Automatic module | Yes | No | JAR on module path | Per automatic module rules, broader than explicit | Bridge from legacy JARs |
| Unnamed module | No | No | Class path | Per unnamed module model | Legacy applications and libraries |
| Open module | Yes | Yes, using `open module` | Module path | All packages open for deep reflection; exports per descriptor | Frameworks requiring broad reflection |
| System/JDK module | Yes | Descriptor provided by the JDK | Runtime image | Per JDK descriptor | `java.base`, `java.sql`, `java.logging`... |

Classification note: `open module` is **a form of declaring an explicit named module**, whereas “system module” describes the origin/modules of the JDK runtime rather than a fourth module type replacing named/automatic/unnamed. JDK modules can be explicitly declared and are pre-present in the runtime image. Some tools also use concepts such as module layer, module finder, and upgrade module path; those are organizational/lookup mechanisms and should not be confused with the module type of an individual JAR.

### 6.1. The `java.base` Module

Every named module has a mandatory readability relationship to `java.base`, which contains foundational APIs such as `java.lang`, `java.util`, and `java.io`. There is no need to write `requires java.base;` in a regular descriptor.

Other JDK modules, such as `java.sql`, `java.xml`, and `java.net.http`, are used through appropriate module relationships. Do not assume every JDK module is automatically resolved under all launch modes. Check the root modules configuration and actual module graph.

## 7. Module Resolution, Readability, and Accessibility

These three steps explain why “the JAR is already on disk” yet the application still fails.

### 7.1. Resolution: Is the Module in the Graph?

When the JVM launches a modular application, the system determines the root modules and then resolves the required modules (and service-provider relationships where applicable). A module that cannot be found can cause an error before the main method runs:

```text
java.lang.module.FindException:
    Module com.example.catalog not found, required by com.example.app
```

How to debug: check whether the file/JAR is on the right module path, whether the module name is correct, and whether the launcher received the path. Do not just look at the artifactId or file name and guess the module name.

### 7.2. Readability: Does the Calling Module Read the Target Module?

Example:

```java
module com.example.app {
    requires com.example.catalog;
}
```

The `com.example.app` module has a readability relationship to `com.example.catalog`. Without an appropriate readability relationship, code in an explicit named module cannot directly reference the API of another named module just because its JAR is also on the module path.

This differs from the class path, where JARs have no descriptor separating dependency boundaries.

### 7.3. Accessibility: Is the Package Exported or Opened?

Even when module A reads module B, a `public` class located in an unexported package of B still does not become a public API for A. The compiler may report that the package is “not visible”, or a binary built with a different configuration may encounter `IllegalAccessError`.

If a framework uses deep reflection, the issue is usually that the package is not opened to the module performing reflection, leading to `InaccessibleObjectException` when attempting to call `setAccessible(true)`.

It can be visualized as:

```text
Is the module found?
      |
      v
Is the module resolved in the graph?
      |
      v
Does the caller read the target module?
      |
      v
Is the target package appropriately exported/opened?
      |
      v
Are Java visibility, class loader, and runtime linkage valid?
      |
      v
Only then does the call/reflective access actually work.
```

Each layer has different errors and remedies. Adding `requires` does not automatically open private fields for reflection; adding `opens` does not fix a missing module during resolution.

## 8. Complete Example: Explicit Module Library and Application

Suppose we create two modules with the structure:

```text
src/
  catalog/
    module-info.java
    com/example/catalog/api/ProductCatalog.java
  store/
    module-info.java
    com/example/store/Main.java
```

### 8.1. Library Module `com.example.catalog`

File `src/catalog/module-info.java`:

```java
module com.example.catalog {
    exports com.example.catalog.api;
}
```

File `src/catalog/com/example/catalog/api/ProductCatalog.java`:

```java
package com.example.catalog.api;

public final class ProductCatalog {
    private ProductCatalog() {
    }

    public static String findName(long id) {
        return "Product-" + id;
    }
}
```

### 8.2. Application Module `com.example.store`

File `src/store/module-info.java`:

```java
module com.example.store {
    requires com.example.catalog;
}
```

File `src/store/com/example/store/Main.java`:

```java
package com.example.store;

import com.example.catalog.api.ProductCatalog;

public class Main {
    public static void main(String[] args) {
        System.out.println(ProductCatalog.findName(42L));
    }
}
```

### 8.3. Compile and Run

Example on Linux/macOS with a JDK supporting JPMS:

```bash
mkdir -p mods/com.example.catalog mods/com.example.store

javac -d mods/com.example.catalog \
    src/catalog/module-info.java \
    src/catalog/com/example/catalog/api/ProductCatalog.java

javac --module-path mods -d mods/com.example.store \
    src/store/module-info.java \
    src/store/com/example/store/Main.java

java --module-path mods \
    -m com.example.store/com.example.store.Main
```

Expected output:

```text
Product-42
```

In this example, the `mods` directory contains two exploded modules. The compiler for `store` needs the module path pointing to `mods` to find `com.example.catalog`. The application needs `requires com.example.catalog` because the code directly uses APIs from that module. The library needs `exports com.example.catalog.api` so consumers can call the public class.

On Windows, adjust paths/line continuations for PowerShell or run each command on a single line. The commands in this article are meant to illustrate the mechanism; in real projects, use a build tool and managed source set structures.

### 8.4. What Happens If the Package Is Not Exported?

If you remove the `exports com.example.catalog.api;` line from the library module while keeping `requires` in the application, the module can still be found and read. However, `Main.java` is not allowed to use `ProductCatalog` because the package is not exported.

This is an accessibility error, not a missing-JAR error. The proper solution is to decide whether that package is truly a public API; if so, export it deliberately. You should not turn the entire module into an open module to fix a compile-time export error.

## 9. Running a Class Path Application Using Libraries on the Module Path

A common migration keeps the main application on the class path while moving some libraries to named/automatic modules. For example:

```bash
java --module-path "mods:lib/modular.jar" \
     --add-modules com.example.catalog \
     -cp app.jar \
     com.example.Main
```

Here `--add-modules com.example.catalog` is used to ensure that module is included as a root module during resolution in situations where the launcher does not resolve it automatically under the current configuration. The path separator syntax on Windows must be adjusted accordingly.

If `com.example.Main` on the class path uses a package exported by `com.example.catalog`, the call can work once the module is resolved and accessibility conditions are met.

Not every named module on the module path is automatically accessible to a class path application in all launch modes. Use:

```bash
java --show-module-resolution \
     --module-path mods \
     --add-modules com.example.catalog \
     -cp app.jar com.example.Main
```

to see which modules are resolved and the reasons they were brought into the graph.

## 10. Interactions Among Explicit, Automatic, and Unnamed Modules

### 10.1. Dependency Direction Table

| Caller | Callee | Key conditions/limitations |
|---|---|---|
| Unnamed module | Unnamed module | Follows class loader/class path and Java visibility |
| Unnamed module | Explicit named module | Target must be resolved; package must be properly exported |
| Explicit named module | Explicit named module | Requires readability and proper package export/access |
| Explicit named module | Automatic module | Can `requires` automatic module by name; needs a stable name and resolved target |
| Explicit named module | Unnamed module | Cannot `requires` an unnamed module; requires structural changes or limited workarounds |
| Automatic module | Named/unnamed module | Has a flexible readability model to support migration; still requires dependencies to actually be present |

This table is a directional model. Final runtime access is still governed by class loaders, visibility, the module graph, and the type of operation (public API access vs. deep reflection).

### 10.2. Why Can an Explicit Module Not `requires` a Class Path Library?

A named module with a descriptor:

```java
module com.example.app {
    requires com.example.legacy;
}
```

is valid only if the `com.example.legacy` module can be found as a named module (explicit or automatic). A JAR placed **only on the class path** belongs to an unnamed module and therefore has no module name to `requires`.

There are several migration options:

1. Keep the application on the class path in the initial phase.
2. Move the legacy library JAR to the module path as an automatic module, checking its name and split packages.
3. Choose a library version that already has an explicit module descriptor.
4. Create a dedicated adapter to isolate the legacy dependency.
5. Only consider launcher workarounds like `--add-reads ...=ALL-UNNAMED` when truly necessary and with a removal plan.

`--add-reads` should not be treated as a long-term module design approach, because it creates a special relationship not directly expressed in the source descriptor and can be hard to reproduce consistently across IDE, CI, tests, and production.

### 10.3. Layered Transition Model

A large system can be organized in stages:

```text
Initial stage:
  [Application + all libraries] -> class path / unnamed modules

Intermediate stage:
  [Legacy application] -> class path
  [Modular/automatic libraries] -> module path

Next stage:
  [Explicit named module application]
      -> [Explicit named module libraries]
      -> [Automatic module libraries]

Target stage:
  [Modules with descriptors and clear module boundaries]
```

This is a viable roadmap, not a mandatory requirement for every system. If the cost of modularization outweighs the benefits, you can still use the class path on a modern JDK and focus on runtime compatibility.

## 11. Split Packages and Duplicate Classes

### 11.1. What Is a Split Package?

A split package occurs when classes belonging to the same package are distributed across multiple JARs/modules. For example:

```text
legacy-api.jar
  com/example/shared/A.class

legacy-impl.jar
  com/example/shared/B.class
```

On the traditional class path, this packaging may work, yet it easily causes class/resource conflicts or depends on the class loader search order.

On the module path, JPMS does not allow resolved named modules to share the same package in a conflicting manner within the same module layer. A set of libraries that previously ran on the class path may not be movable as-is to the module path.

### 11.2. Symptoms During Migration

Errors may relate to:

- Two automatic modules containing the same package.
- An automatic module and an explicit module containing the same package.
- A new app module and a JDK/third-party module having overlapping packages.
- One copy of a library on the class path and another on the module path.
- A shaded JAR with overlapping packages without proper relocation.

There is no universal fix by adding `requires` or `opens`. You must determine package ownership and eliminate duplication: upgrade libraries, exclude one artifact, relocate code during the build, or keep the system on the class path until an appropriate modular structure is in place.

### 11.3. Duplicate Classes and Class Loaders

Even when there is no split package in the JPMS sense, two JARs can both provide the same class binary name. On the class path, the class loader may select whichever copy is found first according to the loader's rules, causing behavior to change with dependency order. In plugin environments, the same class can exist across multiple loaders, resulting in `ClassCastException` even though the class names look identical.

During migration, export the dependency graph for compile/runtime and inspect the actual JARs and class loaders, rather than looking only at versions in the build file.

## 12. ServiceLoader in Modular Systems

### 12.1. Service Contract and Provider Do Not Have to Be in the Same Module

JPMS provides the directives:

- `uses <ServiceInterface>` in the module consuming the service.
- `provides <ServiceInterface> with <Implementation>` in the module providing the implementation.

Example consumer module:

```java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.GreetingService;
}
```

Provider module:

```java
module com.example.provider {
    requires com.example.spi;
    provides com.example.spi.GreetingService
        with com.example.provider.impl.DefaultGreetingService;
}
```

SPI module:

```java
module com.example.spi {
    exports com.example.spi;
}
```

The implementation package does not need to be exported merely for `ServiceLoader` to instantiate the provider according to a valid declaration. The provider must be found and resolved via service binding or brought into the graph through appropriate configuration.

For class path JARs, service providers are typically declared in the file:

```text
META-INF/services/com.example.spi.GreetingService
```

whose content is the binary name of the provider class. When moving a JAR from the class path to the module path, understand how automatic modules read provider configurations and translate them properly to `provides` when creating an explicit descriptor.

### 12.2. Service Errors Are Usually Not Caused by Missing `requires`

A provider JAR may be on the module path yet remain unresolved, or the descriptor may lack `provides`, or the provider class may be invalid. In that case, `ServiceLoader` may fail to find the provider or throw `ServiceConfigurationError`.

Verification procedure: identify the module containing the service interface, the provider module/name, the descriptor, the module graph, service binding, and how the runtime is launched. Do not assume that merely copying the JAR into a directory is enough.

## 13. Class Loading, Reflection, and Module Boundaries

### 13.1. Class Loaders Still Exist in the JPMS World

The JVM's class loading mechanisms such as the bootstrap, platform, and application class loaders continue to operate. JPMS does not eliminate class loaders. A module can be defined in a layer and associated with an appropriate class loader; applications using containers/plugins can still create custom loaders or separate module layers.

It is important to distinguish:

- **Module resolution:** determining which named modules are in the graph.
- **Class loading:** locating and defining the actual class.
- **Readability:** whether the calling module is allowed to read the target module.
- **Accessibility:** whether the package is exported/opened for the required type of access.
- **Linkage:** whether descriptors, class/interface hierarchies, and binary APIs match.

A `ClassNotFoundException` may occur because the class loader could not find the class; a `FindException` may occur because the module resolver could not find the module; an `IllegalAccessError` may stem from access permissions; a `NoSuchMethodError` may come from a binary API mismatch. These errors should not be handled with the same workaround.

### 13.2. Deep Reflection Is a Risk Area When Upgrading the JDK

Code such as:

```java
Field field = SomeType.class.getDeclaredField("internalState");
field.setAccessible(true);
```

may fail if `SomeType` belongs to a named module that does not open the package to the caller, resulting in `InaccessibleObjectException`.

With modern frameworks, identify the module name of the reflecting library/framework and use `opens package to module` deliberately. Even when the application is not yet modularized, JDK named modules can still reject reflection into internal packages.

If forced to use a launcher flag:

```bash
--add-opens java.base/java.lang=ALL-UNNAMED
```

document clearly why, which system requires that access, and the removal plan. The flag above only illustrates the syntax and **is not a recommended system-wide configuration**. Starting in JDK 17, relying on `--illegal-access` to broadly open internal packages is no longer a viable measure.

### 13.3. API Compatibility Differs from Module Compatibility

A JAR can have a bytecode major version suitable for the target JDK and still fail on the module path because:

- A module specified in `requires` is missing.
- A package is not exported or opened.
- Split package.
- Incorrect module name.
- Service provider is not resolved.
- A framework assumes only class path scanning.
- Native code/agents/tooling do not understand module boundaries.

Therefore, verifying the bytecode/source target is not enough to assert that the system is JPMS-compatible. You must test directly in the exact launch mode intended for release.

## 14. JPMS Tool Options to Know

| Option/tool | Purpose | Notes |
|---|---|---|
| `--module-path` / `-p` | Search path for modules | Does not mean all modules are resolved |
| `--module` / `-m` | Run main module | Differs from running a main class with `-cp` |
| `--add-modules` | Add root modules during resolution | Useful for hybrid configurations |
| `--show-module-resolution` | Print resolved module information | Helps investigate the actual graph |
| `--list-modules` | List available modules in the runtime | Does not prove application modules are resolved |
| `--describe-module` | View a module's descriptor | Useful for understanding exports/requires |
| `--add-reads` | Add a readability edge at runtime | Limited workaround |
| `--add-exports` | Export an additional package to target module(s) | Workaround for unexported APIs |
| `--add-opens` | Open an additional package for reflection | Does not replace exports in all contexts |
| `--patch-module` | Add/replace classes in a named module in allowed environments | Mainly used in testing/compatibility tooling |
| `jdeps` | Analyze class/package/module dependencies | Does not replace runtime testing |
| `jar --describe-module` | View a JAR's module description | Also useful for automatic modules |
| `jlink` | Create a custom runtime image from supported modules | Requires evaluating dependencies/automatic modules |

### 14.1. Practical Inspection Commands

```bash
java --version
java --list-modules

jar --describe-module --file lib/example.jar

jdeps --summary app.jar
jdeps --print-module-deps app.jar

java --module-path mods \
     --show-module-resolution \
     -m com.example.app/com.example.app.Main
```

The commands above are purely inspection tools. `jdeps` infers static dependencies and has limitations with reflection/dynamic loading; it does not know every class that will be loaded via runtime configuration. For JARs with external dependencies, you may need to provide the appropriate classpath/module path to `jdeps`.

### 14.2. Overrides Have Different Effects

Syntax examples:

```bash
--add-modules com.example.catalog
--add-reads com.example.app=ALL-UNNAMED
--add-exports java.base/jdk.internal.misc=ALL-UNNAMED
--add-opens java.base/java.lang=ALL-UNNAMED
```

Do not apply all of them at once as a “fix-all bundle”. Each flag affects a distinct layer:

- `--add-modules` helps bring modules into the graph.
- `--add-reads` modifies readability.
- `--add-exports` allows package access across export boundaries.
- `--add-opens` allows deep reflection into a package within the specified scope.

Each override must have a rationale, an owner, tests, and a removal plan. Do not let configurations exist only on developer machines while missing from CI, containers, or the production JVM.

## 15. Impact on Build Tools, Testing, and Packaging

### 15.1. Gradle and Java Toolchains

A Gradle project with `module-info.java` may need configuration for module path and dependency detection. For supported Gradle versions, an example in Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
    modularity.inferModulePath = true
}

application {
    mainModule = 'com.example.store'
    mainClass = 'com.example.store.Main'
}
```

This is an illustrative configuration example, not a guarantee that every plugin/version behaves identically automatically. If a library is non-modular, Gradle may place the dependency on the classpath instead of the module path depending on metadata and inference behavior; verify the actual compiler args and runtime args.

When converting to a named module, check:

- The `compileJava`, `test`, and `run` tasks.
- Custom source sets and integration tests.
- Convention plugins, included builds, and annotation processors.
- Whether `module-info.java` is located in the correct source set.
- Whether the test framework supports JPMS/module path on the version in use.
- Whether the application plugin launches with the correct module name and main class.

A successful CI build does not prove that `java -m` on a production container will also work if the test task and runtime use different classpaths.

### 15.2. Maven and Plugins

In Maven, check the Maven Compiler Plugin, Surefire/Failsafe, module path support, compiler release, and how the test engine runs. Example Java level declaration:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

`release` controls the source/API/bytecode target; it **does not automatically turn a JAR into an explicit module**. Modularization requires a descriptor, module resolution setup, and actual testing. Maven artifact coordinates also do not automatically determine the JPMS module name.

Review the parent POM, plugin management, test runtime, annotation processors, and generated sources. For dependencies with `Automatic-Module-Name`, verify the exact module name before writing `requires`.

### 15.3. Testing and Mocking Frameworks

Unit tests may run on the classpath or module path depending on the plugin, version, and configuration. A modular application does not necessarily have its test JVM launched modularly like production.

Common risks:

- Frameworks reflecting into unopened packages.
- Test code needing to be patched into the application module.
- Test dependencies being unnamed modules while the test module does not read them.
- Bytecode manipulation and Java agents requiring compatible configuration.
- Tests passing on the classpath but failing when packaged and run on the module path.

If `--patch-module`, `--add-opens`, or `--add-reads` are used for tests, clearly document why the test configuration differs from runtime. Do not unconditionally carry all test workarounds into production.

### 15.4. Uber JARs, Shading, and Modular Metadata

Shadowing/shading can merge multiple JARs into a single artifact. With modular JARs, combining classes from different modules under a single `module-info.class` or stripping module descriptors can alter module identity, exports, service providers, and how the runtime loads classes.

Check:

- Which `module-info.class` the final artifact contains.
- Whether the manifest has `Automatic-Module-Name`.
- Whether there are split packages, duplicate classes, or relocated packages.
- Whether `META-INF/services` files are merged properly.
- Whether a multi-release JAR preserves `META-INF/versions/...` and an appropriate manifest.

A JAR that runs on the classpath after shading may not necessarily run on the module path. Test the final artifact directly, not just individual compiled classes.

### 15.5. Multi-Release JARs and the Module Path

A multi-release JAR can contain different classes under `META-INF/versions/N/`. The Java runtime selects the implementation matching the running version according to multi-release rules when enabled in the manifest. This affects class loading and the executed APIs, even when the module name remains unchanged.

When analyzing module compatibility, inspect the manifest, the descriptor applied per runtime, and which classes are selected on each target JDK. Do not assume the implementation at the JAR root is always the one running.

## 16. Common Errors When Moving from Class Path to Module Path

| Symptom | Possible cause | What to check |
|---|---|---|
| `Module ... not found` | Wrong name, missing from module path, missing root dependency | `jar --describe-module`, `--module-path`, descriptor |
| Package “not visible” at compile time | Caller does not read the module, or package is not exported | `requires`, `exports`, qualified export |
| `IllegalAccessError` | Module/class access permissions mismatch at runtime | Readability/export and binary build/runtime |
| `InaccessibleObjectException` | Deep reflection into an unopened package | `opens ... to ...` and caller module |
| `ServiceConfigurationError` | Missing provider, misdeclared, unresolved, or invalid | `uses`/`provides`, META-INF/services, resolution |
| Split package/resolution failure | Two named modules contain overlapping packages | Inventory JARs/modules, adjust dependency structure |
| `ClassNotFoundException` | Loader cannot find class or provider is misconfigured | Actual classpath/module path/class loader |
| `NoClassDefFoundError` | Required class fails to load during linkage/initialization | JAR contents, class loader, dependencies, cause |
| `NoSuchMethodError` | Bytecode compiled against a binary API different from runtime | Descriptor and loaded JAR version |
| Tests pass but `java -m` fails | Test and production launch modes differ | Compare test JVM args and runtime command |
| Cannot access legacy library from named module | Legacy JAR is only on classpath/unnamed module | Choose automatic module/adapter or controlled workaround |
| `requires` breaks after renaming JAR file | Automatic module name was derived from file name | Establish a stable module name using Automatic-Module-Name/explicit descriptor |

Do not add batches of flags just to make errors disappear. Identify the failing layer: module discovery, resolution, readability, export/open, class loader, or ABI. An error caused by a changed method descriptor cannot be fixed with `--add-opens`.

## 17. Safe Migration Roadmap

### Step 1: Lock In the Goal

Clarify whether the migration aims to:

- Run the application on a newer JDK while keeping the classpath.
- Move certain libraries onto the module path.
- Fully modularize the application.
- Build a custom runtime image with `jlink`.
- Isolate internal APIs with module boundaries.

If you only need to upgrade the JDK from 17 to 21, do not add modularization as a goal without clear benefits and cost justification.

### Step 2: Inventory Dependencies and Class Loading Mechanisms

List JARs, the dependency graph, module descriptors, Automatic-Module-Name, unnamed/automatic/explicit status, plugin/framework scanning, and custom class loaders.

You must inspect the exact compile/runtime/test classpaths, especially transitive dependencies. A library may be present at build time yet missing from the runtime image.

### Step 3: Check for Split Packages and Conflicts

Find packages appearing in multiple JARs, duplicate classes, shaded dependencies, and colliding module names. Fix package ownership before moving artifacts en masse to the module path.

### Step 4: Choose Module Boundaries

Create modules along actual API and dependency boundaries; decide which packages to export/open. Avoid exporting all packages out of convenience if they are internal APIs. Check for cycles between modules: JPMS does not allow a module graph with circular `requires` dependencies that violate resolution.

### Step 5: Handle Non-Modular Libraries

Prefer versions with an explicit descriptor or a stable automatic module name. If unavailable, consider automatic modules, keeping the classpath, or creating an adapter. Do not force a legacy library with many split packages onto the module path without understanding the consequences.

### Step 6: Update Build, Tests, and Launcher

Ensure the compiler uses the module path, runtime launch `-m` is correct, and the module graph resolves as designed. Document temporary `--add-modules`, `--add-reads`, `--add-exports`, and `--add-opens` flags.

### Step 7: Verify Reflection, Services, and Resources

Run integration tests for DI, ORM, JSON, ServiceLoader, scanners, agents, JPA entities, configuration, and dynamic plugins. Review string-based class names, resource paths, and native/JNI usage if any.

### Step 8: Run the Final Artifact on the Real Runtime

Test the modular JAR or packaged app in a production-like setup. Compare the actual module graph and dependency graph, and record the JDK vendor/build, container image, JVM args, and artifact checksums.

### Step 9: Release Incrementally and Prepare Rollback

Choose canary/rolling/blue-green depending on the system. If module resolution errors appear, rollback must restore the exact set of JARs, module path, classpath, launcher flags, and runtime image, not just a single class.

## 18. Handover Documentation and Checklist

### 18.1. Module Inventory Template

| Module/artifact | Location | Type | Module name | Required modules | Exported/opened APIs | Notes |
|---|---|---|---|---|---|---|
| `store-app` | Module path | Explicit named | `com.example.store` | `com.example.catalog` | Per `module-info` | Main module |
| `catalog.jar` | Module path | Explicit named | `com.example.catalog` | `java.base` (implicit) | `com.example.catalog.api` | Internal library |
| `legacy-utils.jar` | Class path | Unnamed | None | Per class loader | Unnamed model | Not yet modularized |
| `third-party.jar` | Module path | Automatic | Verify from JAR | Per resolution | Broad per automatic module | Monitor for stable name |

This table illustrates the structure. The actual report must record versions, checksums, the source of the module name, and verified build/runtime commands.

### 18.2. Technical Checklist

- [ ] Class path, module path, and module graph have been distinguished.
- [ ] Explicit named, automatic, and unnamed module status has been identified for each artifact.
- [ ] Automatic module names have been verified using metadata/tooling, not merely guessed from JAR names.
- [ ] Root modules and runtime module resolution have been verified.
- [ ] `requires`/`requires transitive`/`requires static` have been declared deliberately.
- [ ] `exports` for public APIs and `opens` for deep reflection have been checked.
- [ ] Framework module names and qualified exports/opens have been reviewed.
- [ ] Split packages and duplicate classes have been resolved.
- [ ] Dependencies on unnamed modules have been analyzed before modularizing consumers.
- [ ] ServiceLoader providers and module/service bindings have been verified.
- [ ] Framework scanning, serializers, ORMs, agents, and plugin loaders have been checked.
- [ ] Gradle/Maven compiler/test/runtime args have been checked on the actual tool versions.
- [ ] Shaded/multi-release/final JARs have been inspected after packaging.
- [ ] Integration tests have been run using the exact launcher mode to be used in production.
- [ ] Every `--add-reads`, `--add-exports`, and `--add-opens` flag has a rationale and an owner.
- [ ] Module inventory, commands, artifact checksums, logs, and rollback plan have been saved.

### 18.3. Completion Criteria

A move to the module path should only be considered to have compatibility evidence when the team has demonstrated that: the right modules are found and resolved, callers read the right dependencies, package exports/opens meet requirements, class loaders and service providers actually work, business tests pass on the final artifact, and the build/runtime environment is reproducible.

**In summary:** the class path and module path do not differ solely in the `java` option name. The class path preserves the legacy model based on class loaders and unnamed modules; the module path places JARs into a module graph governed by readability, exports, opens, and resolution rules. Explicit named modules are the destination when clear boundaries are desired; automatic modules serve as a bridge; unnamed modules remain a valid choice for non-modularized systems. Understanding these three forms properly enables upgrading the JDK or evolving Java architecture without confusing module errors with bytecode, dependency, or framework errors.