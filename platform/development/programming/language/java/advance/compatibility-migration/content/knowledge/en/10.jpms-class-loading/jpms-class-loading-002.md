# Unnamed Module, Automatic Module, and Named Module

When migrating a Java 8 application to Java 11 or a newer Java version, developers often encounter concepts such as *classpath*, *module path*, *unnamed module*, *automatic module*, and *named module*. These are core components of the **Java Platform Module System (JPMS)**, introduced to the platform in Java 9.

The most important point is: **using a newer JDK does not mean you must write `module-info.java` immediately**. Java 8 code placed on the classpath can still run under JPMS's compatibility model. However, when the application, libraries, or build tools begin using the module path, rules on module readability, package exports, and reflection will directly affect compilation, class loading, and execution.

This lesson explains the three module types from a **Java Advance Compatibility Migration** perspective, in the **JPMS and Class Loading** chapter: how they are created, how they see each other, what limitations they are subject to, and which migration approach to choose when a system has many legacy JARs.

## 1. Foundational Concepts Before Comparing

### 1.1. Classpath and Module Path

Before Java 9, most applications located classes via the **classpath**: the JVM and class loaders looked up classes in the specified directories/JARs, within the scope of class loading rules.

```bash
# Linux/macOS: : separates classpath entries
java -cp "app.jar:lib/*" com.example.Main

# Windows: ; separates classpath entries
java -cp "app.jar;lib/*" com.example.Main
```

Starting in Java 9, there is also the **module path**, where the JVM looks for JARs or directories treated as modules:

```bash
java --module-path mods -m com.example.app/com.example.app.Main
```

The two paths do not have the same meaning. **Where a JAR is placed** determines whether it is processed under the classpath model or the module path model; the same JAR can play different roles depending on how it is run.

### 1.2. Module Descriptor and Module Graph

An explicitly named module typically describes its dependencies and exposed packages in `module-info.java`:

```java
module com.example.app {
    requires java.sql;
    exports com.example.app.api;
}
```

When launching or compiling a modular program, the tool resolves modules starting from the *root modules* and `requires` relationships, forming a **module graph**. The mere presence of a module on the module path does not mean it is always resolved and included in the graph. `requires`, `--add-modules`, or an appropriate module resolution mechanism may be needed to bring it in.

### 1.3. Three Questions Often Conflated Into One

When a class cannot be used, you should distinguish:

1. **Can the class be found and loaded?** Depends on the JAR, path, class loader, and resolved modules.
2. **Can the calling module read the module containing the class?** Depends on readability relationships, such as `requires`.
3. **Is the package containing the class exported or opened for the access type being used?** Depends on `exports`, `opens`, and the corresponding JVM options.

An error can happen at any layer. For example, placing a JAR in the right directory does not automatically grant access to every package of a named module.

## 2. Unnamed Module: Code Running on the Classpath

### 2.1. Definition

An **unnamed module** is a module without a name, containing classes loaded by a class loader from the classpath. The code does not need to declare `module-info.java`. Each class loader has its own unnamed module; therefore, you should not assume that the entire JVM has only a single unnamed module.

Example of a legacy application:

```text
legacy-app/
├── app.jar
└── lib/
    ├── logging.jar
    ├── jdbc-driver.jar
    └── utils.jar
```

Launch:

```bash
java -cp "app.jar:lib/*" com.example.Main
```

On Linux/macOS use `:`; on Windows change it to `;`. Classes loaded by the application class loader from ordinary classpath JARs belong to the corresponding unnamed module, regardless of whether those JARs were originally built as separate libraries.

### 2.2. Access Characteristics

The unnamed module is designed to support legacy code:

- Neither needs nor has a module name to use in `requires`.
- Can read resolved modules in the module graph, while still constrained by the packages that named modules export to it.
- Exports and opens its own packages to support classpath code and reflection under the compatibility mechanism.
- Does not create clear module boundaries between JARs loaded by the same class loader into the unnamed module.

Although an unnamed module has broad access in the direction of **using** other modules, that **does not mean** any named module can reference back to classes on the classpath. An ordinary named module cannot write `requires` targeting an unnamed module.

### 2.3. Why Is the Classpath Still Useful During Migration?

When upgrading from JDK 8 to 11, continuing to run on the classpath is usually the strategy with the fewest changes. This helps separate two tasks:

- **Upgrading the runtime:** updating the JDK, build tools, dependencies, and APIs that changed or were removed.
- **Modularization:** redesigning package boundaries, `requires`, `exports`, `opens`, and service loading mechanisms.

There is no need to combine both tasks into a single large migration. If the application primarily uses legacy frameworks or many libraries without stable module descriptors, staying on the classpath in the initial phase can help reduce risk.

### 2.4. Limitations of the Unnamed Module

Because classpath JARs usually lack independent module boundaries, legacy issues remain:

- Missing dependencies are only detected at compile time or when executing a code path.
- A package can be provided by multiple JARs; class selection depends on class loader and classpath configuration.
- You cannot explicitly express which modules are allowed to use internal APIs of another JAR via `exports`.
- Some dependencies are loaded indirectly via reflection and configuration, making a complete inventory difficult.

The unnamed module is a compatibility mechanism, not a complete replacement for explicit module design.

## 3. Automatic Module: A Bridge from Legacy JARs to the Module Path

### 3.1. When Does an Automatic Module Appear?

A JAR **without a module descriptor** placed on the **module path** can be treated as an **automatic module**. The JVM assigns it a module name and certain compatibility privileges so it can participate in the module graph.

Example:

```text
mods/
├── com.example.app/
└── legacy-utils-1.2.jar   # JAR without module-info.class yet
```

If `legacy-utils-1.2.jar` is placed on the module path and resolved into the graph, it will act as an automatic module rather than an ordinary classpath JAR.

Simply moving a file into a directory named `mods` does not automatically turn it into a module; the deciding factor is **how the Java tool is invoked with `--module-path`**.

### 3.2. Name of an Automatic Module

The automatic module name is determined in the usual order:

1. If the JAR manifest has the `Automatic-Module-Name` attribute, use that name.
2. Otherwise, the tool derives the name from the JAR filename according to normalization rules and strips the appropriate version portion.

Example manifest of a library:

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.vendor.legacyutils
```

A named module can declare the dependency:

```java
module com.example.app {
    requires com.vendor.legacyutils;
}
```

Using the module name published by the vendor is usually more stable than relying on a name derived from the filename. When a library changes its filename, versioning scheme, or migrates to a real module descriptor, the derived name can change and prevent `requires` from resolving.

You can check the actual name with:

```bash
jar --describe-module --file path/to/legacy-utils-1.2.jar
```

For a non-modularized JAR, the tool may report that no descriptor was found and display the derived automatic module name. This result is more reliable than guessing the name from the filename.

### 3.3. Access Characteristics of an Automatic Module

Automatic modules are designed for compatibility with legacy JARs. In principle, an automatic module:

- Has a **module name** so other named modules can `requires` it.
- Reads other resolved modules and can use code in the unnamed module under the automatic module compatibility mechanism.
- Exports all of its packages so other modules can use public types.
- Opens its packages for reflection, supporting legacy frameworks that require deep access.

These privileges reduce the effort needed to bring a legacy library into a modular graph. However, an automatic module **lacks an explicit encapsulation contract**: every package is exposed, including packages meant only as implementation details. Therefore, it should not be treated as the final module design.

### 3.4. Automatic Modules Do Not Solve Every Dependency

An automatic module can still encounter issues:

- Two JARs on the module path contain the same package (*split package*).
- A JAR uses an unstable derived module name.
- A library references reflection or JDK internal APIs that are strongly encapsulated.
- Runtime dependencies are not resolved or are missing from the required path.
- A framework dynamically generates classes, scans the classpath, or uses a custom class loader with assumptions different from the JPMS model.

If an automatic module needs to use another JAR on the classpath, that does not mean the enclosing named module application is also allowed to directly reference the classpath JAR. Each module and specific dependency path must be evaluated.

### 3.5. Transitional Role in the Migration Roadmap

An automatic module fits when a library does not yet have `module-info.java` but the new application needs to `requires` it. When the vendor releases an official module descriptor, you should check module name compatibility and package boundaries before replacing the JAR.

Do not move every dependency to the module path just to be "JPMS compliant". In many projects, keeping certain legacy JARs on the classpath is a more practical choice until the ecosystem provides full support.

## 4. Named Module: A Module with Clear Identity and Contract

### 4.1. What Is a Named Module?

A **named module** has a name recognized by JPMS. In application contexts, a named module usually refers to an **explicit named module**: a module that declares a descriptor via `module-info.java` and is compiled into `module-info.class`.

Example:

```java
module com.example.orders {
    requires java.sql;
    requires java.logging;

    exports com.example.orders.api;
}
```

The `com.example.orders` module explicitly states that it reads `java.sql`, `java.logging`, and exposes its own API package. Other non-exported packages can still be used inside the module, but do not become ordinary APIs for external modules.

Note on terminology: **an automatic module is also a named module**. When comparing the three categories in this lesson, "named module" is often used to mean **explicit named module**, in contrast to an automatic module whose name is assigned automatically. In the full technical classification, both groups have names.

### 4.2. Common Directives in `module-info.java`

| Directive | Meaning | Scenario |
| --- | --- | --- |
| `requires m` | Read module `m` to use exported APIs. | Application needs `java.sql`. |
| `requires transitive m` | Allows modules reading the current module to also read `m` transitively. | Public API of the current module returns a type belonging to `m`. |
| `requires static m` | Required at compile time but optional at runtime. | Dependency only needed for compilation/annotations. |
| `exports p` | Export package `p` to other modules. | Exposing an API package. |
| `exports p to m` | Export a package only to specified modules. | Controlled sharing of internal APIs. |
| `opens p` | Allow deep reflection on package `p`. | ORM/serializer accessing non-public fields. |
| `opens p to m` | Open a package only to specified modules. | Opening entities to an ORM framework. |
| `uses s` | Module uses service `s`. | `ServiceLoader` locating providers. |
| `provides s with impl` | Module provides an implementation of service `s`. | Module implementing an SPI. |

In addition, `open module` allows deep reflection into all packages of the module; this differs from exporting all packages for ordinary Java access. You should open specific packages whenever possible.

### 4.3. Example of Two Independent Named Modules

Suppose we have the source code structure:

```text
src/
├── com.example.greeting/
│   ├── module-info.java
│   └── com/example/greeting/api/Greetings.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

Module providing the API:

```java
// src/com.example.greeting/module-info.java
module com.example.greeting {
    exports com.example.greeting.api;
}
```

```java
// src/com.example.greeting/com/example/greeting/api/Greetings.java
package com.example.greeting.api;

public final class Greetings {
    private Greetings() {}

    public static String hello(String name) {
        return "Xin chào, " + name;
    }
}
```

Application module:

```java
// src/com.example.app/module-info.java
module com.example.app {
    requires com.example.greeting;
}
```

```java
// src/com.example.app/com/example/app/Main.java
package com.example.app;

import com.example.greeting.api.Greetings;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greetings.hello("Java"));
    }
}
```

Example of compiling per module from the project root directory:

```bash
# Step 1: compile the API-providing module
javac -d mods/com.example.greeting \
  src/com.example.greeting/module-info.java \
  src/com.example.greeting/com/example/greeting/api/Greetings.java

# Step 2: compile the application module with the module path
javac --module-path mods -d mods/com.example.app \
  src/com.example.app/module-info.java \
  src/com.example.app/com/example/app/Main.java

# Step 3: run the main class of the named module
java --module-path mods -m com.example.app/com.example.app.Main
```

The commands illustrate a Unix shell, where `\` continues lines. On Windows PowerShell or `cmd`, write each command on a single line or use the appropriate line-continuation syntax. With Maven/Gradle, let the build plugin manage the module path and compile tasks instead of hardcoding all the commands manually.

### 4.4. Cannot `requires` an Unnamed Module

For example, legacy code placed in `legacy.jar` on the classpath provides `com.legacy.Helper`. An explicit named module cannot write:

```java
module com.example.app {
    // Invalid: an unnamed module has no name for requires.
    requires unnamed;
}
```

To handle this, you can choose to:

1. Move `legacy.jar` to the module path to use it as an automatic module (if there are no package conflicts).
2. Upgrade to a library version that already has an explicit module descriptor.
3. Keep the part of the application that still depends on that JAR on the classpath during the transition period.
4. Only in special situations, use the `--add-reads` option to add a readability edge to `ALL-UNNAMED`, while configuring it consistently at compile time and runtime.

The migration path should prioritize dependencies with stable module names; `--add-reads` is usually a limited workaround and cannot replace explicit dependency design.

## 5. Comparison Table of the Three Models

| Criterion | Unnamed module | Automatic module | Explicit named module |
| --- | --- | --- | --- |
| Common class source | Classpath | JAR without a descriptor on the module path | JAR/directory with `module-info.class` on the module path |
| Has module name? | No | Yes, from manifest or derived | Yes, explicitly declared in descriptor |
| Requires `module-info.java`? | No | No | Yes in the corresponding source, or descriptor generated when building the module |
| Readability | Broad compatibility mechanism with resolved modules | Reads broadly for legacy library compatibility | According to `requires` and JPMS rules |
| Package exports | Its own packages are broadly exported | All packages are exported | Only `exports` packages or additional configuration |
| Deep reflection | Its own packages are broadly opened | Packages are opened for compatibility | According to `opens`, `open module`, or additional configuration |
| API encapsulation level | Low | Low, since many packages are auto-exported | Can be high, thanks to declared boundaries |
| Use cases | Legacy applications/JARs, initial migration | Bridge for named modules depending on legacy JARs | Modules with clear architecture and contracts |

Key takeaway: **an automatic module has a name but no explicit descriptor**, whereas **an unnamed module has no name even though the code inside it is still managed by JPMS**.

## 6. Readability, Exports, Opens, and Class Loading Capability

### 6.1. "Reading a Module" Differs from "Accessing a Package"

With the explicit named module `com.example.app`:

```java
module com.example.app {
    requires com.example.library;
}
```

If `com.example.library` does not export the package `com.example.library.internal`, source code in `com.example.app` cannot use types in that package through ordinary Java access, even though it declared `requires com.example.library`.

All of the following must be satisfied simultaneously:

```text
Calling module reads target module
                 +
Target package is exported to the calling module
                 +
Java public/protected/package/private rules allow it
                 =
Type/member access via ordinary Java code
```

### 6.2. `exports` Does Not Automatically Allow Deep Reflection

Frameworks such as ORMs or serializers sometimes need to access non-public constructors/fields via reflection. Exporting a package does not mean allowing arbitrary deep reflection.

Example:

```java
module com.example.orders {
    exports com.example.orders.api;
    opens com.example.orders.entity to org.hibernate.orm.core;
}
```

In this example, the entity package is opened to the correspondingly named ORM module; the API package is exported for ordinary Java access. The ORM's module name must be determined from the actual library version. If the framework is on the classpath or the module graph is organized differently, the configuration also needs adjustment.

When a system uses libraries that dynamically generate proxies, reflection, or serialization, you must examine **both the module graph and the actual class loaders**. A successfully loaded class can still throw `InaccessibleObjectException` when a framework attempts deep access to an unopened member.

### 6.3. Named Modules and Unnamed Modules Do Not Have a Symmetric Relationship

In practice, this often causes confusion:

- Code in an unnamed module can call APIs exported by resolved named modules.
- An explicit named module does not automatically read code in an unnamed module; you cannot add `requires` by name because an unnamed module has no name.
- An automatic module is designed as a bridge and has broader readability rules than an explicit named module.

Therefore, dependency direction matters greatly. **A classpath application calling a modular library** and **a modular application calling a classpath library** are not symmetric cases.

## 7. JPMS Does Not Replace ClassLoader

### 7.1. Modules and Class Loaders Solve Different Problems

Class loaders are responsible for locating, defining, and loading classes under the class loading model. The module system describes readability relationships between modules and package visibility. A class is associated with a module during definition, yet there must still be a class loader responsible for loading it.

In real-world applications there may be:

- The JVM's bootstrap/platform/application class loaders.
- Class loaders created by an application server, servlet container, or framework.
- `URLClassLoader` and custom class loaders for plugins or external JARs.
- Thread context class loader used to select the scope for finding providers/resources.

Each class loader has its own unnamed module. Classes loaded by different class loaders may carry the same package and class name without being the same runtime type.

### 7.2. Identifying a Class's Module at Runtime

Java 9+ provides the `Class.getModule()` API:

```java
public final class ModuleInspector {
    public static void main(String[] args) {
        inspect(String.class);
        inspect(ModuleInspector.class);
    }

    private static void inspect(Class<?> type) {
        Module module = type.getModule();
        System.out.println("Class: " + type.getName());
        System.out.println("Module: " + module.getName());
        System.out.println("Named: " + module.isNamed());
        System.out.println("Loader: " + type.getClassLoader());
    }
}
```

`String` belongs to the named module `java.base`. If `ModuleInspector` runs on the classpath, `getModule().isNamed()` for this class is `false` and `getName()` returns `null`. If it is placed in an explicit named module, the result will correspond to that module.

The `ClassLoader` of platform classes may display `null` if the class is loaded by the bootstrap loader. Do not treat `null` as an error.

### 7.3. Module Layers and Plugin Architecture

JPMS also has the concept of a **module layer**, which allows creating sets of modules with their own resolution configuration and class loaders. A plugin architecture can use a new layer to load modules added after application startup.

However, using layers does not eliminate readability, package export, or service loading rules. You need to design the module graph, class loaders, and plugin lifecycle consistently; you cannot simply drop a JAR into a directory and expect every class to become visible from every module.

For applications with pre-Java 9 custom class loaders, migration should examine both the class loader selection mechanism and how plugins are packaged. Do not replace the entire plugin architecture with layers in the same JDK upgrade batch unless there is a clear need.

## 8. Transitional Example: A Named Module Depending on a Legacy JAR

Suppose the application `com.example.app` wants to use the library `vendor-utils.jar`, which was released for Java 8 and does not yet have `module-info.class`.

### Option A: The Entire Application Still Uses the Classpath

```bash
java -cp "app.jar:lib/*" com.example.Main
```

This is an appropriate choice when prioritizing a runtime upgrade first, and libraries/frameworks are not yet ready for modularization. No `module-info.java` is needed for the application.

### Option B: Place the Legacy JAR on the Module Path as an Automatic Module

The library may declare in its manifest:

```text
Automatic-Module-Name: com.vendor.utils
```

Then the explicit named module application can declare:

```java
module com.example.app {
    requires com.vendor.utils;
}
```

Launch using the module path:

```bash
java --module-path "mods:lib/vendor-utils.jar" \
  -m com.example.app/com.example.app.Main
```

The command uses `:` as the path separator on Linux/macOS; on Windows use `;`. Ensure the module name matches the JAR's metadata, and that the library's packages do not cause a split package with other modules.

### Option C: Use a Library Version That Already Has a Descriptor

When the vendor releases a library with `module-info.class`, use the exact module name published by the vendor and recheck exported APIs, opened packages, service provider names, and compatibility with the running version.

Option C usually yields clearer module boundaries, but you should not assume the new library keeps every internal API previously broadly exported as an automatic module. If the application is using internal packages, switching from an automatic module to an explicit module can produce compile or runtime errors.

## 9. Split Packages, Duplicate Modules, and Resolution Errors

### 9.1. What Is a Split Package?

A **split package** occurs when a single package is distributed across multiple modules. Example:

```text
legacy-a.jar  -> com.vendor.shared.A
legacy-b.jar  -> com.vendor.shared.B
```

On the classpath, these two JARs can be loaded by the same class loader. However, when placed as two modules on the module path, JPMS enforces stricter encapsulation constraints; the module graph may fail to resolve or raise an error if the same package appears in modules that cannot coexist in the selected configuration.

Handling options may include:

- Upgrading to a library version whose package structure fits JPMS.
- Merging the JARs if supported by the vendor.
- Removing duplicate dependencies or replacing the implementation.
- Keeping components whose packages cannot yet be separated on the classpath during phased migration.

Do not apply shading or bulk package renaming without evaluating reflection, serialization, resource names, and compatibility with other clients.

### 9.2. Duplicate or Unstable Module Names

If two different JARs have the same module name on the module path, selection/resolution may behave unexpectedly or fail. With automatic modules, names derived from filenames make this issue even harder to track.

Good practice is to record:

- The actual JAR path.
- The module name determined by the tool.
- The dependency version.
- Which JARs are included in the module graph.

Instead of guessing, use `jar --describe-module` and module resolution display modes.

### 9.3. Errors When a Module Is Not Resolved

A JAR located on the module path that is not resolved into the graph is not guaranteed to be usable. For an application launched on the classpath that needs a named module outside the JDK, `--add-modules` must sometimes be specified:

```bash
java --module-path mods \
  --add-modules com.example.greeting \
  -cp app.jar \
  com.example.Main
```

Condition: `com.example.greeting` must exist and export the package used by classpath code. `--add-modules` adds the module to the resolved set; it does not open internal packages or bypass `exports`.

## 10. Reflection, `exports`, `opens`, and Transitional Flags

### 10.1. Two Types of Access That Need Separate Handling

When moving a library or application from an unnamed/automatic module to an explicit named module, a framework may report errors because a package that was previously broadly opened is no longer open.

| Symptom | Possible Cause | Preferred Resolution |
| --- | --- | --- |
| Compiler reports package is not visible | Module does not read the module containing the API, or package is not exported | Fix `requires`, `exports`, and the dependency graph. |
| `IllegalAccessError` | Bytecode accesses a module-restricted package/type | Upgrade the library or fix the module descriptor to export the appropriate scope. |
| `InaccessibleObjectException` | Framework attempts deep reflection on an unopened package | Upgrade the framework; use `opens` for the needed package. |
| `ClassNotFoundException` | Class loader cannot find the class or JAR is not loaded on the right path | Check classpath, module path, plugin configuration, and class sources. |
| `NoClassDefFoundError` | Class missing at runtime or earlier initialization failure | Check dependency/runtime configuration and deeper root causes in logs. |

### 10.2. `--add-exports` and `--add-opens`

Two options can be used as transitional workarounds when a library's descriptor cannot yet be modified:

```bash
# Example: open a package to code on the classpath for deep reflection
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar

# Example: export an internal package to code on the classpath
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -jar app.jar
```

`ALL-UNNAMED` targets unnamed modules, commonly used when the framework is on the classpath. You need to specify the exact target module if the framework is already a named module. Only use the flags that are truly needed and have a plan to remove them; do not open many packages just to mask errors.

### 10.3. `--add-reads` in Special Situations

If an explicit named module cannot yet drop its dependency on classpath code, you may encounter a transitional example:

```bash
--add-reads com.example.app=ALL-UNNAMED
```

This option adds a readability relationship from the specified module to unnamed modules. It does not automatically package, distribute, or fix class loaders for classpath JARs. For source code compiled modularly, corresponding compiler configuration must also usually be arranged; adding flags only at runtime does not make source compilation bypass all JPMS constraints.

Do not rely on this flag as a long-term design if the dependency can be converted into a module with a stable name.

## 11. `ServiceLoader` and Module Boundaries

Older Java applications typically discover implementations via `META-INF/services/<service-interface>` files in classpath JARs. Named modules have a clearer way to declare services using `uses` and `provides`.

Example service-defining module:

```java
module com.example.spi {
    exports com.example.spi;
}
```

Consumer module:

```java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.MessageProvider;
}
```

Provider module:

```java
module com.example.provider {
    requires com.example.spi;
    provides com.example.spi.MessageProvider
        with com.example.provider.SimpleMessageProvider;
}
```

At runtime, the consumer can use:

```java
ServiceLoader<MessageProvider> providers =
    ServiceLoader.load(MessageProvider.class);

for (MessageProvider provider : providers) {
    System.out.println(provider.message());
}
```

For a legacy library that is an automatic module or on the classpath, check the corresponding provider metadata. If the provider is not resolved/loaded in the modular configuration, having the class present in the JAR is not enough for `ServiceLoader` to find it.

During migration, check `META-INF/services` resources, module descriptors, context class loaders, and the providers actually used at runtime.

## 12. JPMS Inspection and Diagnostic Tools

### 12.1. View the Runtime's Module List

```bash
java --list-modules
```

The command displays the modules visible to the current runtime/configuration according to how the command is invoked. Do not treat this list as proof that every application JAR dependency has been resolved into the graph when launched with its own configuration.

### 12.2. View a Module's Descriptor

```bash
java --describe-module java.sql
```

The command helps inspect dependencies, exported packages, and descriptor information of a named module.

### 12.3. View a JAR's Module Name

```bash
jar --describe-module --file path/to/library.jar
```

Useful when distinguishing explicit modules from automatic modules, especially before writing `requires`.

### 12.4. Observe Module Resolution at Runtime

```bash
java --show-module-resolution \
  --module-path mods \
  -m com.example.app/com.example.app.Main
```

Replace the path and module name according to the project. The log shows root modules and resolved relationships. Do not use the result of a single run to draw conclusions for all profiles if each profile has a different module path.

### 12.5. Analyze Dependencies with `jdeps`

```bash
# Analyze dependencies at the class/package level
jdeps --recursive path/to/application.jar

# View module dependencies identified by the tool
jdeps --print-module-deps path/to/application.jar
```

`jdeps` is useful for finding static dependencies and suggesting required platform modules. The tool does not automatically know about every class loaded via reflection, names read from configuration, dynamically loaded plugins, or native integration. Therefore, when building a custom runtime image with `jlink`, you need to supplement it with real testing and verify required providers.

## 13. Migration Process from Classpath to the Modular Model

### Phase 1: Keep the Classpath to Validate the New JDK

Run the legacy application on the target JDK without full modularization. Update build tools, dependencies, split-out APIs, and runtime configuration; record a baseline for builds, tests, and startup.

### Phase 2: Inventory JARs and Class Loaders

List direct/transitive dependencies, JARs provided by the application server, plugin directories, reflection, service providers, and dynamic class generation/loading mechanisms. Separately record components outside the dependency graph.

### Phase 3: Classify Each Library

Divide dependencies into three groups:

- Already has an explicit module descriptor.
- Has no descriptor yet, but has a stable automatic module name or can be used on the module path.
- Not ready for the module path due to split packages, reflection, special class loaders, or unclear dependencies.

Do not assume that a library supporting Java 11 means it already supports the module path well.

### Phase 4: Pilot Modularizing a Core Area with Clear Boundaries

Start with a module that has a small public API, few dependencies, and is not a system-wide bootstrap framework. Write `module-info.java` with minimal `requires` and `exports`, then test compiling/running on the module path.

### Phase 5: Handle Reflection and Service Loading

For frameworks needing deep reflection, use `opens` per specific package/module. For providers, use `uses`/`provides` or compatible service metadata. Verify the module graph and the actual source from which classes are loaded.

### Phase 6: Resolve Split Packages and Legacy Dependencies

Upgrade libraries, remove duplicate JARs, adjust package structures, or temporarily keep a portion on the classpath. Avoid bundling API-breaking changes into the same batch unless necessary.

### Phase 7: Standardize Build and Release

Ensure Maven/Gradle, CI, packaging, and runtime configurations agree on the module path/classpath. Document official module names, JDK versions, the module graph, and any remaining workarounds such as `--add-opens`/`--add-reads`.

### Phase 8: Testing and Rollback Plan

Run integration tests, startup/shutdown, reflection, serialization, database drivers, logging, security agents, and plugin loading. Maintain a rollback plan in case errors appear only in one production profile. Modularization is an architectural change and requires more testing than merely getting `javac` to succeed.

## 14. Common Misconceptions

**"Placing a JAR on the module path means it is always used."** Not necessarily. The module must be resolved into the graph; an entry on the path does not guarantee all classes are loaded.

**"An automatic module is just a renamed unnamed module."** Incorrect. An automatic module has a name and can be used in `requires`; an unnamed module has no name. Automatic modules have compatibility readability/export/open rules applied, but their placement and relationship with the module graph differ from the classpath.

**"A named module only needs `requires` to access any class."** False. The target package must also be exported, members must satisfy Java access control, and the class must be loadable under the configuration.

**"`exports` is enough for ORM reflection."** Not always true. Deep reflection usually requires `opens`, and you must account accurately for whether a named module or an unnamed module invokes reflection.

**"A Java 11 application must have `module-info.java`."** False. The classpath and unnamed module remain a valid model.

**"A JAR with `Automatic-Module-Name` is already an explicit module."** False. The manifest attribute only provides a stable name when the JAR is used as an automatic module; it is not equivalent to a module descriptor with its own `requires`, `exports`, and `opens`.

**"If `jdeps` reports no errors, then it is JPMS-compatible."** Insufficient. Static analysis can miss reflection, service loading, native libraries, configuration, and dynamically loaded plugins.

**"The module system replaces class loaders."** False. Class loaders remain responsible for loading classes; the module graph adds constraints on readability and package visibility.

## 15. Checklist for Java Advance Compatibility Migration Projects

- [ ] Identified which parts of the application run on the classpath and which use the module path.
- [ ] Distinguished unnamed, automatic, and explicit named modules in the current runtime.
- [ ] Obtained the exact automatic module name via `jar --describe-module`, without guessing from the filename.
- [ ] Verified that required modules are actually resolved, not merely present on the module path.
- [ ] Evaluated `requires`, readability, and package `exports` of explicit modules.
- [ ] Checked reflection and packages that must be `opens` for frameworks.
- [ ] Searched for split packages, duplicate module names, and JARs incompatible with the module path.
- [ ] Reviewed class loaders of the application server, plugins, and dependencies loaded outside the build.
- [ ] Checked `META-INF/services`, `uses`/`provides`, and runtime providers.
- [ ] Identified all remaining `--add-modules`, `--add-reads`, `--add-exports`, and `--add-opens` flags and planned workaround removal.
- [ ] Tested building/running on the target JDK and tested business flows involving reflection, drivers, serialization, or plugins.
- [ ] Updated build/deploy documentation, dependencies, module graph, and rollback plan.

## 16. Conclusion

The three models—**unnamed module**, **automatic module**, and **explicit named module**—enable Java to combine compatibility with legacy applications and a modular architecture with clear boundaries. Unnamed modules support the traditional classpath; automatic modules act as a bridge allowing non-modularized JARs to participate in the module graph; explicit named modules explicitly declare dependency relationships, package exports, and reflection permissions.

For Java compatibility migration, a safe approach is to **upgrade the runtime first if needed, and modularize selectively afterward**, checking each dependency and distinguishing three layers of issues: whether the class can be loaded, whether the modules can read each other, and whether the package allows the access type being used. When these questions are answered through configuration and real testing, migrating to JPMS becomes much more controllable instead of turning into a sweeping change that is hard to diagnose.