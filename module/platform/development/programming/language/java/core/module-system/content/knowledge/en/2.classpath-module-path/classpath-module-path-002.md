# Module Path and How Modules Are Resolved

In the Java Platform Module System (JPMS), the **module path** is where Java tools look for named modules. However, having a modular JAR sit on the module path does not mean that module automatically appears in the running application. Before executing code, Java needs to select **root modules**, trace dependencies, and build a valid **module graph**. This process is called **module resolution**.

Understanding the module path and resolution helps explain common situations: a JAR is in the right directory yet Java still reports module not found; a module is found yet cannot access another module's package; a library moved from the classpath to the module path suddenly hits a package conflict; or a plugin is not resolved even though its JAR exists.

This lesson introduces the core concepts, a hands-on build-and-run example, how root modules and `requires` determine the module graph, the difference between readability and package access, along with tools for inspecting and diagnosing configurations.

## 1. Distinguishing Classpath and Module Path

The two search paths play different roles:

| Aspect | Classpath | Module Path |
| --- | --- | --- |
| Common option | --class-path or -cp | --module-path or -p |
| Search unit | Classes and resources | Modules and module descriptors |
| Module model | Unnamed module of the corresponding class loader | Named modules |
| Dependencies | No JAR-level requires declarations | Explicit modules use requires in the descriptor |
| Encapsulation | No named module boundaries between JARs on the same classpath | exports and opens control package access |
| Selection to run | Main class by fully qualified name | Main module and main class via -m |
| Notable risks | Duplicate classes, classpath order, and implicit dependencies | Missing modules, resolution conflicts, split packages, access permissions |

Example of running a traditional application:

~~~bash
java --class-path "out:libs/*" com.example.app.Main
~~~

Example of running a named module:

~~~bash
java --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

On Windows, entries in a multi-component path are typically separated by a semicolon **;** instead of the colon **:** on Linux/macOS. A directory containing multiple modular JARs can be passed as a single module path entry.

The classpath and module path can coexist in a single launch. In that case, classes from JARs on the classpath reside in the unnamed module, while selected modules on the module path participate in the named module graph.

## 2. The Module Path Is Where Modules Are Found, Not a List of Modules That Must Run

Suppose we have:

~~~text
project/
└── mods/
    ├── com.example.app.jar
    ├── com.example.catalog.jar
    ├── com.example.audit.jar
    └── com.example.metrics.jar
~~~

With the command:

~~~bash
java -p mods -m com.example.app/com.example.app.Main
~~~

Java can locate the modules inside the `mods` directory. However, Java is not obligated to place all four modules into the module graph just because all four JARs sit in that directory.

If the `app` module declares a direct dependency on `catalog`:

~~~java
module com.example.app {
    requires com.example.catalog;
}
~~~

then at least `app`, `catalog`, and their required dependencies must be considered for resolution. `audit` and `metrics` may remain **observable** modules without belonging to the selected configuration if no root or other dependency pulls them in.

That is why three questions must be separated:

1. Does Java **find the descriptor** of the module?
2. Is the module **selected for resolution** along with the roots and dependencies?
3. Does a consumer module have **permission to read and access the package** it needs to use?

A "yes" answer to the first question is not enough to imply the other two.

## 3. Three Concepts: Observable, Root, and Resolved Modules

**Observable modules** are the modules visible to the search mechanism in the resolution environment, typically consisting of modules in the runtime image and modules on the configured module paths.

**Root modules** are the entry points of the resolution process. When running an application with **-m**, the module containing the main class is a root. Additional roots can be added using **--add-modules**.

**Resolved modules** are the set of modules selected after JPMS starts from the roots, locates mandatory dependencies, and verifies the validity of the configuration.

For example:

~~~text
Observable modules:
    com.example.app
    com.example.catalog
    com.example.audit
    com.example.metrics
    java.base
    java.logging

Root:
    com.example.app

Dependencies:
    com.example.app -> com.example.catalog
    com.example.catalog -> java.logging
    all ordinary modules -> implicit java.base
~~~

When only the relationships above exist, the resolved module graph contains `app`, `catalog`, `java.logging`, and `java.base`; `audit` and `metrics` do not participate on their own.

In practice, other mechanisms such as service binding or additional roots can widen the set of resolved modules; check using **--show-module-resolution** rather than guessing from the number of JARs.

## 4. module-info.java Determines Dependencies of an Explicit Module

An explicit named module has a **module-info.java** file at the root of the module's source:

~~~java
module com.example.app {
    requires com.example.catalog;
}
~~~

The descriptor is compiled by the compiler into **module-info.class**. When the module is packaged into a modular JAR, this file sits at the root of the JAR.

Important directives:

| Directive | Primary effect |
| --- | --- |
| requires M | The current module needs to read module M |
| requires transitive M | The current module reads M and passes readability of M to modules that read the current module |
| requires static M | A dependency required at compile time but optional at runtime |
| exports p | Exposes package p to other modules with an appropriate read relationship |
| exports p to M | Exports package p only to the specified modules |
| opens p | Opens package p for deep reflection |
| opens p to M | Opens package p only to the specified modules |
| uses S | The module is a consumer of service S |
| provides S with I | The module provides implementation I for service S |

**requires** directly affects dependency lookup during resolution. **exports** and **opens** primarily determine package access permissions; they cannot be used in place of `requires`.

Every ordinary named module has an implicit read relationship to **java.base**; there is no need to declare `requires java.base` in `module-info.java`.

## 5. Complete Example with Two Modules

Create the source tree:

~~~text
module-demo/
└── src/
    ├── com.example.catalog/
    │   ├── module-info.java
    │   └── com/example/catalog/api/Book.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

Catalog descriptor:

~~~java
// src/com.example.catalog/module-info.java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

Catalog class:

~~~java
// src/com.example.catalog/com/example/catalog/api/Book.java
package com.example.catalog.api;

public record Book(String title) {
}
~~~

App descriptor:

~~~java
// src/com.example.app/module-info.java
module com.example.app {
    requires com.example.catalog;
}
~~~

Main class:

~~~java
// src/com.example.app/com/example/app/Main.java
package com.example.app;

import com.example.catalog.api.Book;

public final class Main {
    public static void main(String[] args) {
        Book book = new Book("Effective Modular Java");
        System.out.println(book.title());
    }
}
~~~

These are two explicit named modules: `catalog` provides the API and `app` consumes the API. The `app` module declares **requires**, while `catalog` declares **exports** so that `app` can use the `Book` class.

## 6. Compiling with Module Source Path

From the `module-demo` directory, run:

~~~bash
javac \
  --module-source-path src \
  -d mods \
  -m com.example.catalog,com.example.app
~~~

Explanation:

- **--module-source-path src** tells `javac` that the source code is organized by module directories.
- **-d mods** selects the output directory.
- **-m** specifies the source modules to compile.

After compilation, the result typically looks like:

~~~text
mods/
├── com.example.catalog/
│   ├── module-info.class
│   └── com/example/catalog/api/Book.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Each subdirectory is an **exploded module**: a compiled module that has not been packaged into a JAR. The Java launcher can use them on the module path.

Run the application:

~~~bash
java \
  --module-path mods \
  -m com.example.app/com.example.app.Main
~~~

Output:

~~~text
Effective Modular Java
~~~

Java takes `com.example.app` as the root, sees that `app`'s descriptor requires `com.example.catalog`, and resolves `catalog` along with the required system modules. Because the `api` package is exported by `catalog`, `Main` can use `Book`.

## 7. Packaging into Modular JARs

If you need to distribute JARs, you can package the two exploded modules:

~~~bash
mkdir -p dist
~~~

~~~bash
jar --create \
    --file dist/com.example.catalog.jar \
    -C mods/com.example.catalog .
~~~

~~~bash
jar --create \
    --file dist/com.example.app.jar \
    -C mods/com.example.app .
~~~

Inspect the descriptors inside the artifacts:

~~~bash
jar --describe-module \
    --file dist/com.example.catalog.jar
~~~

~~~bash
jar --describe-module \
    --file dist/com.example.app.jar
~~~

Then run:

~~~bash
java -p dist \
     -m com.example.app/com.example.app.Main
~~~

The JAR filename can differ from the module name. For an explicit module, the name inside `module-info.class` is the identity JPMS uses to resolve **requires** and the module name passed to **-m**.

Ensure every modular JAR contains `module-info.class` at the root. If the build accidentally omits this file, the JAR will no longer be recognized as an explicit named module as intended.

## 8. What Steps Does Resolution Follow?

With the command:

~~~bash
java --module-path dist \
     -m com.example.app/com.example.app.Main
~~~

the conceptual process is:

1. **Build the observable module sources.** Java can locate system modules and modules from the configured paths.
2. **Determine root modules.** Module `com.example.app` is a root because it was selected with `-m`; additional roots may exist.
3. **Read root descriptors.** Java obtains dependency information from `module-info.class`.
4. **Follow mandatory requires.** If `app` requires `catalog`, then `catalog` must be found within a resolvable configuration.
5. **Transitively resolve dependencies.** If `catalog` requires another module, resolution continues locating that module.
6. **Verify module constraints.** The module system detects various dependency, readability, and package conflicts.
7. **Create a valid configuration.** Resolved modules can be defined in a runtime layer.
8. **Begin executing the main class.** Actual class loading and initialization occur on demand according to the JVM.

This is a high-level model; the exact mechanics also depend on the Java launcher, root selection, service binding, and parent configurations.

Importantly, **module-level resolution does not mean the JVM has loaded all classes** across every resolved JAR.

## 9. Readability Differs from Exports

A module that is allowed to **read** another module does not automatically gain access to all public classes in that module.

Suppose `catalog` declares:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

Inside `catalog`, there is also a package:

~~~text
com.example.catalog.internal
~~~

The `app` module declares:

~~~java
module com.example.app {
    requires com.example.catalog;
}
~~~

At this point:

- `app` reads the `catalog` module.
- `app` can access public types in **com.example.catalog.api**.
- `app` cannot import types in **com.example.catalog.internal** as a normal API because that package is not exported.

These are two layers of control:

~~~text
requires -> module readability
exports  -> package accessibility
~~~

Adding `catalog` to the module path or adding `catalog` as a root does not alter `catalog`'s exports. If `app`'s source imports the internal package, `javac` can report **package ... is not visible** even when resolution finds all modules.

If a framework needs deep reflection, look at **opens**, which is distinct from `exports`. Do not try to fix a module-not-found error with `opens`, or fix missing package access permissions simply by adding `--module-path`.

## 10. requires transitive and Transitive Readability

Suppose there are three modules:

~~~text
com.example.app
     |
     v
com.example.service
     |
     v
com.example.catalog
~~~

If `service` declares:

~~~java
module com.example.service {
    requires com.example.catalog;
    exports com.example.service.api;
}
~~~

`app` requires `service`:

~~~java
module com.example.app {
    requires com.example.service;
}
~~~

`catalog` is resolved because `service` needs it, but `app` does not implicitly gain permission to read `catalog` directly solely through an ordinary `requires` chain.

If `service`'s public API exposes the `Book` type from `catalog` in a method signature, `service` can declare:

~~~java
module com.example.service {
    requires transitive com.example.catalog;
    exports com.example.service.api;
}
~~~

When `app` reads `service`, a readability relationship to `catalog` can be inferred via `requires transitive`. This is useful when a dependency is part of the public API that consumers need to see.

Note: **requires transitive** propagates readability; it does not automatically export internal packages of `catalog`. `catalog` still needs to export the package containing the API types that `app` uses.

## 11. requires static and Runtime-Optional Dependencies

For a dependency only needed at compile time or potentially absent at runtime:

~~~java
module com.example.app {
    requires static com.example.annotations;
}
~~~

**requires static** allows compilation against the `annotations` module without forcing the runtime to always resolve that module solely because of this directive.

If the runtime has a code path that actually uses classes belonging to the optional dependency, the application still needs to ensure that module and its classes are accessible during execution. Merely writing `requires static` does not guarantee every runtime scenario works when the module is absent.

Depending on the goal, an optional module can be brought into the graph via an additional root or because another dependency requires it. Design clear fallback code paths when the optional feature is unavailable.

The differences:

- **requires M**: mandatory dependency that must be satisfied during resolution.
- **requires transitive M**: mandatory dependency that also propagates readability to consumers.
- **requires static M**: required at compile time, but not mandatory during runtime resolution based solely on that directive.

## 12. --add-modules Adds Root Modules

Suppose the `dist` directory also contains:

~~~text
com.example.audit.jar
~~~

The `audit` module is observable, but neither `app` nor `catalog` requires it. If you want to bring `audit` into the boot layer at startup:

~~~bash
java --module-path dist \
     --add-modules com.example.audit \
     -m com.example.app/com.example.app.Main
~~~

The **--add-modules** option tells JPMS to treat `audit` as an additional root. `audit`'s dependencies are resolved according to its descriptor.

Multiple modules can be specified:

~~~bash
--add-modules com.example.audit,com.example.metrics
~~~

However, **--add-modules does not mean `app` automatically reads `audit`**. Read relationships and package access permissions still obey the descriptors and module graph. If `app`'s code needs to import APIs from `audit`, the sustainable way to declare the dependency is usually `requires com.example.audit`.

Some special values:

| Value | Meaning |
| --- | --- |
| ALL-DEFAULT | Adds the default root module group determined by the launcher |
| ALL-SYSTEM | Adds observable system modules as roots |
| ALL-MODULE-PATH | Adds all observable modules on the application module path as roots |

For example:

~~~bash
java -p dist \
     --add-modules ALL-MODULE-PATH \
     -m com.example.app/com.example.app.Main
~~~

Do not overuse `ALL-MODULE-PATH` just to work around missing module errors. Bringing too many modules into the graph can expose incompatible dependencies or package conflicts that would not happen when resolving only the required modules.

## 13. --limit-modules Restricts the Set of Observable Modules

Besides adding roots, the Java launcher also supports **--limit-modules** to restrict the set of observable modules.

Conceptual example:

~~~bash
java -p dist \
     --limit-modules java.base,com.example.app \
     -m com.example.app/com.example.app.Main
~~~

This option does not restrict the set strictly to the two listed names alone. Java also considers required dependencies according to its rules to form the limited set of observable modules.

If the application needs a module outside the remaining observable set, resolution may report module not found even though the physical artifact exists on the module path.

Therefore, when debugging missing module errors, inspect the module path, `--add-modules`, and `--limit-modules`. A launch command or container entrypoint may set different module limits than an IDE environment.

## 14. Automatic Modules on the Module Path

Not every JAR on the module path has a `module-info.class` file. For a non-modularized JAR placed on the module path, JPMS can recognize that JAR as an **automatic module**.

The automatic module name is derived from:

1. The **Automatic-Module-Name** manifest attribute, if present and valid.
2. Or rules inferring the name from the JAR filename.

For example, a legacy library:

~~~text
dist/legacy-json-2.0.jar
~~~

If recognized as an automatic module named **legacy.json**, another explicit module can write:

~~~java
module com.example.app {
    requires legacy.json;
}
~~~

The exact name must be confirmed from the artifact:

~~~bash
jar --describe-module \
    --file dist/legacy-json-2.0.jar
~~~

Automatic modules help older libraries participate in the module graph during a transition period. They typically export their packages and behave compatibly with non-modularized code.

However, an automatic module does not replace a well-designed explicit descriptor. Moving many legacy JARs onto the module path at once can cause package conflicts or poorly organized dependencies.

## 15. The Unnamed Module on the Classpath Cannot Be Directly Required

A non-modularized JAR placed on the **classpath** belongs to the unnamed module of the corresponding class loader. A named module cannot declare:

~~~java
module com.example.app {
    requires ALL-UNNAMED;
}
~~~

Because `ALL-UNNAMED` is not a valid module name in a `requires` directive.

During migration, you can temporarily use:

~~~bash
--add-reads com.example.app=ALL-UNNAMED
~~~

when the `app` module needs to reference a classpath library while configuring the classpath for that library. The `add-reads` option may be needed at compile time and runtime depending on the code being compiled and executed.

Example execution:

~~~bash
java --module-path mods \
     --class-path "libs/*" \
     --add-reads com.example.app=ALL-UNNAMED \
     -m com.example.app/com.example.app.Main
~~~

This is a controlled compatibility solution, not a long-term substitute for explicit dependency declarations. Once a library is converted into an automatic or explicit named module, it gets its own module identity; at that point, update the module descriptor accordingly.

## 16. Resolution and Service Binding

A module can declare a service consumer:

~~~java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.ReportProvider;
}
~~~

A provider module:

~~~java
module com.example.report.csv {
    requires com.example.spi;
    provides com.example.spi.ReportProvider
        with com.example.report.csv.CsvReportProvider;
}
~~~

JPMS has a service binding mechanism that helps locate additional matching provider modules during certain resolution processes. In the programmatic API, **Configuration.resolveAndBind** illustrates this clearly: beyond `requires` dependencies, the process can also locate modules providing services.

Therefore, one should not claim that a provider module can only appear in the graph when directly required or added via `--add-modules`. In a configuration with service binding, it can be included due to its provider role.

When an application uses `ServiceLoader`:

~~~java
ServiceLoader<ReportProvider> loader =
    ServiceLoader.load(ReportProvider.class);

for (ReportProvider provider : loader) {
    System.out.println(provider.getClass().getName());
}
~~~

it must ensure the service contract and provider modules are configured properly. However, the fact that a provider module was resolved does not mean every provider instance has been created: class loading and provider instantiation happen later on demand.

## 17. Module Graph vs. ClassLoader and Class Loading

Module resolution determines the set of modules and read relationships. Loading individual classes happens when the JVM needs to use each class.

High-level flow:

~~~text
module path
    |
    v
Find module descriptors
    |
    v
Select roots and resolve requires
    |
    v
Configuration / module graph
    |
    v
ModuleLayer defines runtime modules
    |
    v
ClassLoader loads specific classes on demand
    |
    v
Linking and initialization per JVM rules
~~~

A resolved module may contain hundreds of classes never used by the application. Conversely, a `NoClassDefFoundError` can appear late when the application first needs an unavailable dependency class, even though initial resolution succeeded.

For custom plugin layers, the **ModuleFinder**, **Configuration**, and **ModuleLayer** APIs allow an application to proactively build a module graph distinct from the boot layer. However, `--module-path` on the Java launcher does not automatically create an independent layer for each JAR.

## 18. Common Errors and How to Identify Causes

**Module not found**

For example:

~~~text
Error occurred during initialization of boot layer
java.lang.module.FindException: Module com.example.catalog not found,
required by com.example.app
~~~

Check the real module name in `module-info.class`, the artifact's location on the module path, JAR filenames, and `requires` dependencies. A module not being found is a different issue from an unexported package.

**Package is not visible**

The module was found, but the consumer cannot read the module owning the package, or the package has not been exported to the consumer. Check `requires`, then `exports`/qualified exports.

**Reads package ... from both ...**

A module reads the same package from two different exporting modules. This is a split package conflict in the module graph. Check the JARs containing duplicate packages, especially when moving multiple automatic modules onto the module path.

**Module is in the mods directory but not in the boot layer**

The module might only be observable and not yet selected as a needed root/dependency/provider. Use `--show-module-resolution` and check roots; do not assume a module must appear merely because the JAR is present.

**Java runs in the IDE but not in the terminal**

The IDE may automatically add module paths, `--add-modules`, classpaths, or `--add-reads`. Compare the actual command lines between the two environments.

**NoClassDefFoundError after resolution succeeds**

Check runtime dependencies, library versions, class loaders, and the code path first using the class. This is typically an error at the class loading/linking layer, not necessarily a descriptor lookup error.

**Framework reflection is blocked**

If the error is `InaccessibleObjectException`, check whether the package has been opened via `opens` to the right framework module. `exports` does not automatically allow deep reflection into private fields.

## 19. Tools for Inspecting Module Path and Resolution

### Inspect a JAR's Descriptor

~~~bash
jar --describe-module \
    --file dist/com.example.catalog.jar
~~~

This command shows the module name, `requires`, `exports`, and related descriptor details.

### List Observable Modules

~~~bash
java --module-path dist --list-modules
~~~

This command helps confirm which modules can be found; it is not a list of all modules guaranteed to be resolved for an application run.

### Show the Resolution Process

~~~bash
java --show-module-resolution \
     --module-path dist \
     -m com.example.app/com.example.app.Main
~~~

You can compare two commands with and without `--add-modules` to see which modules get added to the graph and which dependencies are chosen.

### Check Modules in the Boot Layer

~~~java
ModuleLayer boot = ModuleLayer.boot();

boot.modules().stream()
    .map(Module::getName)
    .sorted()
    .forEach(System.out::println);
~~~

Or check a specific module:

~~~java
boolean catalogResolved =
    boot.findModule("com.example.catalog").isPresent();

System.out.println("Catalog in boot layer: " + catalogResolved);
~~~

**ModuleLayer.findModule** returns a result from the runtime layer; it does not simply check whether a JAR exists on disk.

### Analyze Dependencies with jdeps

~~~bash
jdeps --module-path dist \
      --module com.example.app
~~~

`jdeps` helps view dependencies at the class/module level. Bytecode analysis results should be combined with module descriptors and the actual launch command, especially when the application loads classes or services via reflection.

## 20. Ordered Debugging Workflow

When encountering errors while switching to the module path, follow this order:

1. Record the JDK version, `javac`/`java` commands, and all JVM arguments.
2. Check whether the JAR is on the classpath or module path.
3. Use `jar --describe-module` to confirm the actual module name.
4. Check the root module selected with `-m` and additional roots from `--add-modules`.
5. Use `--list-modules` to confirm the module is observable.
6. Use `--show-module-resolution` to view the actual module graph.
7. Read `requires`, `requires transitive`, and `requires static` in the descriptor.
8. If resolution passed but the compiler reports package not visible, check readability and `exports`.
9. If framework reflection fails, check `opens` for the right caller module.
10. If class loading fails, check class loaders, runtime dependencies, and class loading logs.
11. When using automatic modules, check duplicate packages and derived module names.
12. Verify results on a JDK, build artifacts, and launch command equivalent to production.

A table for quick classification:

| Symptom | First layer to inspect |
| --- | --- |
| Module not found | Module discovery and resolution |
| Resolved module missing from boot layer | Root selection or runtime configuration |
| Package is not visible | Readability and exports |
| Reflection blocked | opens and caller module identity |
| ClassNotFoundException | ClassLoader and classpath/module path |
| NoClassDefFoundError | Runtime dependencies and linking |
| Split package conflict | Dependency graph and package ownership |

## 21. Practice Exercises

From the two-module project above:

1. Run the application with `--module-path` and `-m`; confirm the book title line is printed.
2. Use `--show-module-resolution` to identify the selected modules.
3. Create an independent `com.example.audit` module, place the artifact on the module path, and check whether the module appears in the boot layer.
4. Try `--add-modules com.example.audit`, then observe the difference.
5. Remove **requires com.example.catalog** from the `app` descriptor while keeping `import Book`; observe the `javac` message.
6. Restore `requires`, then remove `exports` for the `api` package in `catalog`; compare the error with step 5.
7. Create a `service` module with `requires transitive` to `catalog` and test the impact on consumers.
8. Try using a JAR without `module-info.class` on the module path; confirm the automatic module name with `jar --describe-module`.
9. Place a legacy JAR on the classpath and distinguish unnamed module behavior from automatic module behavior.
10. Record which flags change the set of observable modules, which flags add roots, and which declarations control package access permissions.

**The module path is not a command list that loads every module into the JVM.** It is a module search source for JPMS to build a valid configuration from root modules and dependencies. By clearly distinguishing observable modules, root selection, resolution, readability, and package access, you can configure modular applications more accurately, resolve dependency errors faster, and migrate classpath libraries to JPMS in a controlled manner.