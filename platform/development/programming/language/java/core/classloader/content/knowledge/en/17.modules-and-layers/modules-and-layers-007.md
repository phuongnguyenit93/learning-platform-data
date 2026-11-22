# ModuleFinder, Configuration, and Module Dependency Resolution in Java 17

## 1. The Big Picture: Finding Modules Differs from Resolving Modules and Loading Classes

Since Java 9, the Java Platform Module System (JPMS) has introduced the concepts of **named module**, **module descriptor**, **module graph**, and **module layer**. When building a modular application or plugins with their own modules, you typically need to coordinate three components:

1. **`ModuleFinder`** answers: "Which modules are observable in a module source, and what are their descriptors?"
2. **`Configuration`** answers: "Given a set of root modules and `requires` relationships, which set of modules is resolved into a valid dependency graph?"
3. **`ModuleLayer`** answers: "Which layer will these resolved modules become runtime modules in, and which loader will define their classes?"

This can be expressed as a pipeline:

```text
Module artifacts (exploded modules / modular JARs / automatic modules)
                         |
                         v
                   ModuleFinder
                   find / findAll
                         |
                         v
            ModuleReference + ModuleDescriptor
                         |
                         v
       Configuration.resolve / resolveAndBind
       + Parent configuration + Root module names
                         |
                         v
             Resolved module graph
                         |
                         v
             ModuleLayer definition
       + mapping module -> ClassLoader
                         |
                         v
        Runtime Class<?> / services / reflective API
```

**Important:** a module found by `ModuleFinder` **does not yet mean** it is resolved. A module already included in a `Configuration` **does not yet mean** its classes have been loaded or `<clinit>` has run. A configuration only describes the module graph, whereas class loading/linking/initialization are subsequent JVM operations.

This article focuses on the mechanisms of **module discovery**, **descriptor-based dependency resolution**, **service binding**, and **turning a configuration into an executable layer**, while distinguishing them from Maven/Gradle dependency resolution, class loader delegation, and Java access control.

## 2. Module Descriptor: Source of Information for the Dependency Graph

A named module is declared in `module-info.java`. For example:

```java
module m.extension {
    requires m.core;
    exports plugin;
}
```

Common directives:

| Directive | Meaning |
|---|---|
| `requires m.core;` | The current module requires `m.core`; creates a dependency/readability relationship under JPMS |
| `requires transitive m.core;` | The dependency's readability is transitively propagated to modules that depend on the current module |
| `requires static m.optional;` | Dependency mandatory at compile time, optional at runtime according to `requires static` rules |
| `exports plugin;` | Allows access to public types in package `plugin` from modules that read this module |
| `exports internal to m.friend;` | Qualified export only to the specified module |
| `opens model to m.serializer;` | Allows deep reflection into package `model` to a specific module |
| `uses api.Greeter;` | The module consumes the `api.Greeter` service |
| `provides api.Greeter with impl.DefaultGreeter;` | The module declares a service provider implementation |

`module-info.java` is compiled into **`module-info.class`**. `ModuleFinder` reads the module metadata and provides a **`ModuleReference`**, from which the `ModuleDescriptor` is obtained. The descriptor describes requires/exports/opens/uses/provides, the name, packages, and related module information; it **does not already contain provider instances** and does not run code inside the module on its own.

Illustrative example when a `ModuleReference reference` is already available:

```java
java.lang.module.ModuleDescriptor descriptor =
        reference.descriptor();

System.out.println(descriptor.name());
descriptor.requires().forEach(System.out::println);
```

This is a **snippet**, not a standalone runnable application; `reference` must be obtained from a `ModuleFinder`. `descriptor.requires()` returns metadata of the declared dependencies; not all of them are necessarily resolved in the current configuration.

### Module Name Is Not a Java Package Name

A module name such as `m.extension` is the name of a named module. The `plugin` package is where the class `plugin.Worker` resides. The binary name of this class is `plugin.Worker`. JPMS resolution uses **module names**, whereas class loading uses **class names** via loaders.

Do not pass `"plugin.Worker"` as a root name to `Configuration.resolve` when `"m.extension"` is needed as the root. Conversely, `Class.forName` uses `"plugin.Worker"` and does not accept a module name as a class name.

## 3. What Is ModuleFinder?

`java.lang.module.ModuleFinder` is an interface used to **find observable modules** from a specific source. Two main methods:

```java
Optional<ModuleReference> find(String name);
Set<ModuleReference> findAll();
```

- `find(name)` searches for a module by **module name**, returning `Optional<ModuleReference>`. If not found, it returns `Optional.empty()`.
- `findAll()` returns the modules that the finder can observe; the order of the `Set` **is not a contract used as the dependency processing order**.
- A `ModuleReference` describes a named module and allows the runtime or tools to open the module's contents via a `ModuleReader` under appropriate conditions.
- `ModuleFinder` **is not a class loader**; the finder seeing a descriptor does not mean any `Class<?>` is required to be defined by the JVM yet.

### Three Common Ways to Create a ModuleFinder

**Finding modules at given paths:**

```java
ModuleFinder finder = ModuleFinder.of(
        Path.of("out/mods"),
        Path.of("libs/plugin-module.jar"));
```

This is a snippet requiring imports of `java.lang.module.ModuleFinder` and `java.nio.file.Path`. The finder can traverse **exploded modules** or **modular JARs** at the appropriate paths. If a path is invalid or contains conflicting metadata, the lookup operation may fail according to its contract.

**Finding system modules:**

```java
ModuleFinder system = ModuleFinder.ofSystem();
```

The system finder provides the system modules in the runtime image. It is not synonymous with `ClassLoader.getSystemClassLoader()`: one is **module discovery**, while the other is a **class loader object**.

**An empty finder:**

```java
ModuleFinder empty = ModuleFinder.of();
```

Passing no paths creates a finder that sees no modules from any path source. An empty finder is often used for the `after` parameter when you do not want to provide an additional fallback source.

### Is ModuleFinder.of(path) a Snapshot of Loaded Classes?

**No.** A finder works with **artifact/module references**; it does not provide a registry of loaded `Class<?>` instances. If a JAR/module file is replaced while the program is running, do not assume the finder and a previously defined configuration/layer will automatically update the entire graph or class definitions.

A plugin/hot-reload mechanism typically needs to **create a new finder/configuration/layer**, and manage the lifecycle of the old layer/loader and references to class instances.

## 4. ModuleReference and ModuleDescriptor: Knowing a Module Before Having Class<?>

When `finder.find("m.extension")` returns a `ModuleReference`:

```java
var reference = finder.find("m.extension")
        .orElseThrow();

String moduleName = reference.descriptor().name();
```

You can inspect:

- The module name `reference.descriptor().name()`.
- The module's `requires` via `reference.descriptor().requires()`.
- The `exports` and `opens` packages.
- Service usage/provision metadata.
- Depending on the case, `reference.location()` returns an `Optional<URI>` pointing to where the module was found, though not every reference is required to have a location.

`ModuleReference` and `ModuleDescriptor` do not create classes:

```text
Finder finds: m.extension
Descriptor says: requires m.core
Configuration will then resolve dependencies
Layer will then define modules
JVM then loads classes on demand
```

If the goal is only to **analyze module dependencies** or build a module path inspection tool, you can use a finder and descriptor without creating a layer containing executable classes.

### Automatic Modules

An ordinary JAR placed on the module path can be recognized as an **automatic module** under JPMS rules when there is no explicit `module-info.class`. An appropriate finder can observe the automatic module and provide its corresponding descriptor.

The automatic module name can be influenced by `Automatic-Module-Name` in the manifest, or derived from the JAR name according to JDK rules. Do not blindly rely on the file name if you want a stable API module name.

An automatic module generally has different readability and export relationships from explicit modules. It can be a transitional tool, but it **does not replace** testing the dependency graph, split packages, and name stability when designing long-term plugins.

## 5. What Is Configuration?

`java.lang.module.Configuration` represents **a resolved module configuration**: a set of `ResolvedModule` instances along with their `reads` relationships and associated **parent configurations**.

In a typical Java application:

```java
Configuration bootConfig =
        ModuleLayer.boot().configuration();
```

The boot configuration is already created by the runtime when the launcher starts the application. You can create a new **child configuration** based on the boot configuration without mutating the boot configuration.

Differences:

| Object | Contains/Represents | What Does It Not Do? |
|---|---|---|
| `ModuleFinder` | Observable module references from a source | Does not resolve the graph on its own |
| `ModuleReference` | Metadata/location/reader of a module | Does not define classes on its own |
| `ModuleDescriptor` | Module declaration: requires/exports/uses/... | Does not validate the entire graph |
| `Configuration` | Graph of resolved modules and parent configurations | Does not initialize a runtime ModuleLayer on its own |
| `ResolvedModule` | Resolved module with read edges | Is not a `Class<?>` |
| `ModuleLayer` | Runtime modules assigned to loaders and layer parents | Does not guarantee class initialization on its own |

In `Configuration`:

```java
Optional<ResolvedModule> module =
        configuration.findModule("m.extension");
```

This is a snippet requiring the `configuration` variable. `findModule` can find a resolved module in the configuration or its parent configurations per its contract; when you want to know which modules are resolved **within** the child configuration itself, inspect the `configuration.modules()` set or the detailed graph instead of inferring solely from `findModule`.

## 6. Configuration.resolve: From Roots to Dependency Closure

A key method in Java 17:

```java
Configuration child = parent.resolve(
        beforeFinder,
        afterFinder,
        Set.of("m.extension"));
```

Where:

- `parent`: the parent configuration, typically `ModuleLayer.boot().configuration()`.
- `beforeFinder`: the prioritized module finder used when searching for unsatisfied roots/dependencies.
- `afterFinder`: the supplementary finder for lookup according to resolution rules.
- `roots`: the names of the modules that start the resolution process, **not class names**.
- Result: a **new Configuration** containing the necessary resolved modules and parent configuration; the original parent is not modified.

Example module:

```java
module m.extension {
    requires m.core;
}
```

If the root is `m.extension` and `m.core` is not available in the parent configuration, the resolver needs to find a `ModuleReference` for `m.core` in the applicable finder sources. When successful, the child configuration typically includes both `m.extension` and `m.core`.

### Are Only the Roots Resolved?

**No.** The resolver follows the necessary `requires` relationships rather than merely recording the exact root names and stopping. That is the meaning of dependency closure.

For example:

```text
Root: m.extension
     requires m.core
          requires java.logging
               requires java.base

Child configuration: m.extension, m.core
Parent boot configuration: java.base, java.logging, ...
```

The diagram above is only an **illustration** where `java.logging` is already in the parent configuration; it does not assert that every boot layer is guaranteed to contain `java.logging`. The actual set of resolved modules depends on launcher roots, the runtime image, the parent graph, and the finders.

You **should not** ask the resolver to define an additional copy of `java.base` into the child layer. Modules already provided by the parent configuration have their own role in the graph; inspect the parent before assuming another copy is needed.

### Role of the Before/After Finders

The resolver searches for modules across sources according to the order and rules defined by `Configuration`, involving the **before finder**, the parent configurations, and the **after finder**. The two finders are not simply "classpath prepend" and "classpath append" for each `ClassLoader.loadClass`.

- `before` typically contains plugin/module artifacts that the caller wants to resolve before fallback sources.
- `after` can provide additional application modules when a name has not yet been found in earlier sources.
- A parent configuration is an **already resolved** graph, not a directory to be arbitrarily rescanned.
- When a module with the same name appears in multiple places, lookup/configuration rules may select one reference or report an error depending on the situation. Do not rely on ambiguous filesystem ordering.

Module path order and JPMS configuration are **not** a Maven-style dependency solver: the Java resolver does not automatically choose the "highest" version based on semver or download artifacts from the internet.

## 7. Checks Performed by Resolution

The resolver must build a graph with a valid module structure. Typical issues:

1. **Root module not found**: the name `m.extension` is requested, but it is not present in an applicable finder or parent.
2. **Missing requires dependency**: the descriptor declares `requires m.core`, but the resolver cannot find `m.core`.
3. **Invalid module descriptors**: improper module/package names or metadata, or faulty artifacts.
4. **Package or graph structure conflicts**: for example, readability leading to situations with a package that a module is not allowed to read from two sources causing ambiguity, or modules being assigned invalidly when defining a layer.
5. **Parent constraints**: when parent configurations/layers are present, the solution must be compatible with the existing structure and cannot arbitrarily replace modules in the parent.
6. **Service binding**: when `resolveAndBind` is requested, the required set of modules may expand to supply providers for the services being used.

Errors may be reported via `FindException`, `ResolutionException`, or layer definition errors such as `LayerInstantiationException`. **Do not lump all errors into ClassNotFoundException**: if a root module has not been resolved, the error can occur **before** the application asks the loader to look up any class.

### Configuration Does Not Guarantee Every Class Will Work

Resolution validates the module graph according to JPMS; it does not by itself prove that all method invocations, reflection, native libraries, or resources in the program will work.

After the layer is defined, a class may still encounter:

- `ClassNotFoundException` if the loader does not see the requested binary name.
- `NoClassDefFoundError` due to dependency/linking or initialization failure.
- `IllegalAccessError` when bytecode access violates module/package/member visibility.
- `InaccessibleObjectException` when deep reflection is blocked because the package is not open.
- `ServiceConfigurationError` if the provider configuration or provider type is invalid.

Therefore, **successful module resolution is a necessary step, not a certification that the entire application runs correctly**.

## 8. Complete Java 17 Example: ModuleFinder → Configuration → ModuleLayer

The following example runs with **two explicit modules** on a child layer:

- `m.core` exports package `api` containing class `api.Greeting`.
- `m.extension` `requires m.core` and exports package `plugin` containing class `plugin.Worker`.
- The host `LayerDemo` runs from the class path, creates its own `ModuleFinder`, resolves root `m.extension`, defines a child `ModuleLayer`, and then invokes a public method.

Observable behavior: the finder sees **two modules**, the resolver selects both the root and its dependency, and the runtime creates the layer and loads classes from the correct loader of the layer.

### 8.1. Source Tree

```text
src/
  m.core/
    module-info.java
    api/
      Greeting.java
  m.extension/
    module-info.java
    plugin/
      Worker.java
  host/
    LayerDemo.java
out/
  mods/
    m.core/
    m.extension/
  host/
```

`out` is a directory that **will be created by compilation**; there is no need to write class files manually.

### 8.2. Code for m.core

Create file `src/m.core/module-info.java`:

```java
module m.core {
    exports api;
}
```

Create file `src/m.core/api/Greeting.java`:

```java
package api;

public final class Greeting {
    public String text() {
        return "Hello modules";
    }
}
```

### 8.3. Code for m.extension

Create file `src/m.extension/module-info.java`:

```java
module m.extension {
    requires m.core;
    exports plugin;
}
```

Create file `src/m.extension/plugin/Worker.java`:

```java
package plugin;

import api.Greeting;

public final class Worker {
    public static String message() {
        return new Greeting().text();
    }
}
```

`m.extension` compiles because `m.core` exports package `api`, and `m.extension` has `requires m.core`. `plugin` is exported so that host code from the unnamed module can invoke the public member via reflection. If you remove `exports plugin`, class lookup can still succeed, but invocation from the host can be rejected due to module accessibility.

### 8.4. Host Using the Finder and Resolver

Create file `src/host/LayerDemo.java`:

```java
import java.lang.module.Configuration;
import java.lang.module.FindException;
import java.lang.module.ModuleFinder;
import java.lang.ModuleLayer;
import java.nio.file.Path;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class LayerDemo {
    public static void main(String[] args) throws Exception {
        ModuleFinder finder = ModuleFinder.of(Path.of("out/mods"));

        Set<String> available = finder.findAll().stream()
                .map(ref -> ref.descriptor().name())
                .collect(Collectors.toCollection(TreeSet::new));
        System.out.println("Available: " + available);

        Configuration parent = ModuleLayer.boot().configuration();
        Configuration resolved = parent.resolve(
                finder, ModuleFinder.of(), Set.of("m.extension"));

        System.out.println("Resolved core: " +
                resolved.findModule("m.core").isPresent());
        System.out.println("Resolved extension: " +
                resolved.findModule("m.extension").isPresent());

        ModuleLayer layer = ModuleLayer.boot().defineModulesWithOneLoader(
                resolved, ClassLoader.getSystemClassLoader());

        ClassLoader extensionLoader = layer.findLoader("m.extension");
        Class<?> worker = Class.forName(
                "plugin.Worker", false, extensionLoader);

        System.out.println("Worker in child layer: " +
                (worker.getModule().getLayer() == layer));
        System.out.println("Invocation: " +
                worker.getMethod("message").invoke(null));

        try {
            parent.resolve(
                    finder, ModuleFinder.of(), Set.of("m.absent"));
            System.out.println("Unexpected missing root success");
        } catch (FindException expected) {
            System.out.println("Missing root rejected");
        }
    }
}
```

### 8.5. Compiling and Running

From the directory containing `src` and `out`, use JDK 17+.

With Bash (Linux/macOS):

```bash
mkdir -p out/mods/m.core out/mods/m.extension out/host

javac -d out/mods/m.core \
  src/m.core/module-info.java \
  src/m.core/api/Greeting.java

javac --module-path out/mods -d out/mods/m.extension \
  src/m.extension/module-info.java \
  src/m.extension/plugin/Worker.java

javac -d out/host src/host/LayerDemo.java

java -cp out/host LayerDemo
```

With Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out/mods/m.core,out/mods/m.extension,out/host

javac -d out/mods/m.core src/m.core/module-info.java src/m.core/api/Greeting.java

javac --module-path out/mods -d out/mods/m.extension src/m.extension/module-info.java src/m.extension/plugin/Worker.java

javac -d out/host src/host/LayerDemo.java

java -cp out/host LayerDemo
```

**Module path note:** the classpath used to run `LayerDemo` contains only `out/host`; `out/mods` is **explicitly passed by the program to `ModuleFinder`**. If everything were placed on the application class path, the example would no longer accurately illustrate the host actively resolving a child configuration/layer.

### 8.6. Exact Stdout

With a clean module structure and the commands above:

```text
Available: [m.core, m.extension]
Resolved core: true
Resolved extension: true
Worker in child layer: true
Invocation: Hello modules
Missing root rejected
```

Lines explaining the mechanisms:

1. `Available: ...` — `ModuleFinder` sees two modules in `out/mods`. `TreeSet` provides a stable name order when printing; `findAll()` itself makes no ordering guarantee.
2. `Resolved core: true` — `requires m.core` in the descriptor of `m.extension` was followed by the resolver to locate the dependency.
3. `Resolved extension: true` — root `m.extension` is present in the configuration.
4. `Worker in child layer: true` — after defining the layer and finding the loader for `m.extension`, class `plugin.Worker` belongs to the runtime module in the newly created **child layer**.
5. `Invocation: Hello modules` — the call via reflection succeeds because `plugin` is exported, and `Worker`'s dependency on `api.Greeting` has been resolved/permitted for access.
6. `Missing root rejected` — `parent.resolve(..., Set.of("m.absent"))` cannot find root `m.absent` and throws `FindException`, **not ClassNotFoundException**.

### 8.7. What Changes If requires or exports Is Removed?

- Remove `requires m.core` from `m.extension/module-info.java` while keeping `import api.Greeting`: the Java compiler will not allow `m.extension` code to read `m.core` under ordinary modular compilation; that is a **readability** error, not a "broken finder".
- Remove `exports api` in `m.core`: `m.extension` reads the module, but cannot import and use the public `api.Greeting` from a non-exported package; pure module-name resolution differs from compile/access checking.
- Remove `exports plugin` from `m.extension`: the child module can still be resolved and `Class.forName` can still locate `plugin.Worker` via the loader, but reflective invocation from the unnamed host module can be blocked because the package is not exported.
- Change `requires m.core` to `requires m.nonexistent`: if the required named module is missing, resolution/compilation will fail before the example can run.
- Change the root from `"m.extension"` to `"m.core"`: the resolver does not have to select `m.extension` if no dependency or service binding leads to it; the finder can still **observe** the extension, but the configuration is not required to include it.

These changes illustrate three independent layers: **module discovery**, **module resolution**, and **compile/runtime accessibility**.

## 9. ModuleLayer: Bringing a Configuration into the JVM Runtime

A `Configuration` is only a module graph. For an application to use modules as runtime modules, you must define a **`ModuleLayer`** with an appropriate loader mapping.

In the example:

```java
ModuleLayer layer = ModuleLayer.boot()
        .defineModulesWithOneLoader(
                resolved, ClassLoader.getSystemClassLoader());
```

This is code from `LayerDemo` once the `resolved` variable is available.

- The parent layer is `ModuleLayer.boot()`.
- Configuration `resolved` is created with the corresponding parent configuration.
- Java creates a new loader to define the modules in this child layer; the loader passed to the method is the **parent loader** for the new loader, not the new loader returned directly.
- Modules defined in the child layer can be obtained via `layer.findModule(name)`.
- The loader serving a module can be obtained via `layer.findLoader(moduleName)`.

A common misconception: `ClassLoader.getSystemClassLoader()` in the `defineModulesWithOneLoader` call **does not mean** all classes of `m.extension` have become classes defined by the system loader. The API creates the runtime module-to-loader mapping for the layer; in the example, class `plugin.Worker` belongs to the loader managed by the new layer.

### One Loader, Many Loaders, Custom Mapping

`ModuleLayer` provides several ways to define a module layer depending on your needs:

- `defineModulesWithOneLoader`: multiple modules in the configuration are defined with a single new loader.
- `defineModulesWithManyLoaders`: an arrangement with multiple loaders, typically one loader per module.
- `defineModules` with a function mapping module names to loaders as designed by the caller; constraints regarding packages and loader ownership must be respected.

There is no single "best" choice for every plugin. One-loader is convenient when modules within a plugin group need to share a loader; multiple loaders/layers can support different levels of isolation, though they increase complexity around identity, resources, and lifecycle.

**Do not use the same binary name/package within a single loader/layer in a conflicting way**. If two versions of the same module/library need to coexist, you may have to use different layers/loaders and keep shared API types stable; JPMS does not automatically handle semantic version selection.

### The Parent Configuration Must Match the Parent Layer

When the child configuration is resolved based on `boot.configuration()`, defining the child layer also uses `boot` as the parent in the example. When using multiple parent configurations or layers, ensure the mappings and parent relationships match; do not take an arbitrary configuration and attach it indiscriminately to a mismatched parent layer.

## 10. How Do resolve and resolveAndBind Differ?

Both `Configuration.resolve(...)` and `Configuration.resolveAndBind(...)` perform **module resolution**, but `resolveAndBind` also performs **service binding** to include observable provider modules when needed.

An architectural outline:

```java
Configuration graph = parent.resolve(
        finder, ModuleFinder.of(), Set.of("m.client"));

Configuration graphWithProviders = parent.resolveAndBind(
        finder, ModuleFinder.of(), Set.of("m.client"));
```

This is an **illustrative snippet** requiring properly declared `parent` and `finder` variables. You do not need to run both methods simultaneously in the same application; use one method depending on your needs.

Suppose the module descriptors are:

```java
module m.client {
    requires m.api;
    uses api.Greeter;
}
```

```java
module m.provider {
    requires m.api;
    provides api.Greeter with impl.GreeterImpl;
}
```

These two blocks are **two module-info.java files for two different modules**, not a single program compiled in the same file. When `m.client` is the root, `resolve` typically only follows `requires` and does not necessarily add `m.provider` if there is no dependency causing the provider module to be selected. `resolveAndBind` can locate modules providing services used by the resolved modules, add those provider modules to the configuration, and continue resolving their corresponding dependencies.

**Service binding does not instantiate providers.** Creating provider instances is typically performed later via `ServiceLoader` according to its contract and the appropriate layer/loader. `uses` and `provides` are metadata in descriptors; they do not invoke constructors at the resolution step.

### Using ServiceLoader After Defining a Layer

With a `ModuleLayer layer` and the interface `api.Greeter` accessible at the boundary:

```java
ServiceLoader<api.Greeter> providers =
        ServiceLoader.load(layer, api.Greeter.class);
```

This is a snippet requiring an import of `java.util.ServiceLoader` and the `api.Greeter` class/interface. In practice, the class identity of the passed-in service interface must match how the provider modules resolve that interface. If the host and child layer have **two different runtime identities for the same API binary name**, provider discovery or casting may fail.

The `ServiceLoader.load(service)` overload uses the thread context class loader (TCCL), which **is not equivalent** to using provider modules in the newly created layer. When you know which layer to query, the `ServiceLoader.load(layer, service)` overload usually expresses the intent more clearly.

### Is resolveAndBind Always Used?

No. For a straightforward modular application with no requirement to resolve additional provider modules, `resolve` may be sufficient. For service-based plugin discovery, `resolveAndBind` can be useful, though it can also bring extra modules into the graph; you must inspect the set of observed providers and the desired plugin boundaries.

If using the standard Java launcher with `--bind-services` or other module linker options, resolution/service binding during startup has corresponding mechanisms, but you should not assume that calling `ModuleFinder.findAll()` performs service binding.

## 11. requires, requires transitive, and requires static

### requires: Direct Dependency

`requires m.core;` represents a dependency of the current module on `m.core`. When the current module is resolved and the dependency is not already provided by a parent, the resolver searches for the requested module in the appropriate sources.

### requires transitive: Propagating Readability

Suppose:

```java
module m.facade {
    requires transitive m.core;
    exports facade;
}
```

```java
module m.client {
    requires m.facade;
}
```

These are illustrative descriptors of **two separate modules**. When `m.client` reads `m.facade`, `requires transitive m.core` can propagate readability to `m.core` under JPMS. That does **not** automatically export all packages of `m.core`: module `m.core` still needs to declare the appropriate exports for the client to use public types in the package in question.

### requires static: Runtime-Optional Dependency

Example:

```java
module m.extension {
    requires static m.optional;
}
```

`requires static` makes the dependency required in a **compile time** context, but not a strict requirement to be present at runtime. Do not treat it as "if missing, Java will automatically download it from Maven" or "even when missing, every class of the optional module still works normally".

If the code actually uses a class from the optional module on an execution path, you still need to check that the module is supplied/read and the relevant class resolves properly when that path executes. Optional feature designs must have corresponding guards/fallbacks.

### Why Distinguish the Three Kinds?

- The dependency graph is not simply a list of every JAR that the build tool downloaded.
- `requires` and `requires transitive` affect how modules are resolved/read.
- `requires static` affects dependency semantics at compile/runtime.
- `exports`/`opens`, on the other hand, determine package accessibility and are not automatically inferred from `requires`.

## 12. ModuleFinder Does Not Resolve Dependency Versions Like Maven/Gradle

JPMS primarily uses the **module name** as the identifier in module configurations and `requires` relationships; it is **not** a dependency manager that selects versions according to range `[1.2,2.0)`, downloads transitive artifacts from a repository, or replaces a lockfile.

If you have:

```text
libs/v1/m.core.jar
libs/v2/m.core.jar
```

and both provide the same module name `m.core`, you should not expect `ModuleFinder` to automatically pick the "latest version" based on semantic versioning. A configuration is not built as a list of two independent modules with duplicate module names that JPMS will automatically reconcile.

Handling approaches depend on the case:

1. Choose **one** unified version when the same module must be shared.
2. Design **separate plugin layers/loaders** to isolate implementations while ensuring shared API types share a common identity.
3. Validly rename packages/modules via **relocation/shading** if building the artifact requires it.
4. Separate into distinct processes if you need isolation of state/native dependencies or a higher level of safety.

With named modules and multiple layers, do not overlook module exports, readability, and which loader a class can be defined under. Classloader isolation does not automatically solve every compatibility issue between versions.

## 13. Practical Errors in Module Discovery, Resolution, and Layer Definition

### Error 1: Module Exists on Disk, but ModuleFinder Does Not See It

Check:

- Did you pass the **correct directory/JAR path** into `ModuleFinder.of(Path...)`?
- If pointing to a directory containing multiple module directories, is that structure a valid module-path entry according to the JDK?
- Does the JAR have a valid `module-info.class` or automatic-module metadata?
- Does the actual module name match the name you passed to `finder.find(name)`?
- Is there an artifact with a conflicting module name or invalid format causing the finder to throw `FindException`?

`findAll()` returns metadata, not a classloader cache. You can print the list of names in a stable order for diagnosis:

```java
Set<String> names = finder.findAll().stream()
        .map(ref -> ref.descriptor().name())
        .collect(java.util.stream.Collectors.toCollection(
                java.util.TreeSet::new));
System.out.println(names);
```

This is a snippet requiring `finder` and an appropriate `Set` import.

### Error 2: Root Module Not Found During Resolve

`Configuration.resolve` takes **module names** as roots, not class names or file paths. If you pass `plugin.Worker` instead of `m.extension`, the root is wrong and the resolver can throw `FindException`.

When a module requires another module that is missing, you must provide that module in the before/after finder or an appropriate parent graph; it cannot be fixed by switching to `Class.forName`.

### Error 3: Dependency Module Resolved, but Code Fails to Compile

This may be due to an unexported package, missing `requires`/readability, or Java access modifiers. It is not necessarily a `ModuleFinder` error.

For example, if `m.extension` `requires m.core` but `m.core` does not export `api`, then `import api.Greeting` in the extension is blocked. Choosing a different loader does not change module exports.

### Error 4: Configuration Succeeds, but defineModules... Fails

`Configuration` is graph metadata; `ModuleLayer` definition also enforces classloader/layer mapping constraints and package ownership. Some errors only surface when assigning modules to loaders—for example, module packages that cannot validly be defined together on the chosen loader.

Use the `LayerInstantiationException` and its actual message to see which constraint was violated; do not assume that `ResolutionException` and `LayerInstantiationException` are the same.

### Error 5: findLoader Does Not Find the Module

`layer.findLoader("m.extension")` looks up the module within that layer; if the module is not in the queried layer, it may throw `IllegalArgumentException`. Distinguish `Configuration.findModule` (which may consider parent configurations) from `ModuleLayer.findLoader`, which requires the module name to be within the layer's scope per the API.

When a plugin system creates multiple layers, do not always call `ModuleLayer.boot().findLoader(...)` to look up a plugin's loader in a child layer.

### Error 6: Class Loads Successfully, but Reflection Is Blocked

`Class.forName("plugin.Worker", false, pluginLoader)` can return a `Class<?>`, yet calling `getMethod(...).invoke(...)` still depends on package `exports`, Java modifiers, and module access rules.

You need to check:

- Does the caller module read the target module?
- Is the public class's package exported to the caller?
- If performing deep reflection into a private member, is the package opened to the proper scope?
- Does the method/constructor have the right signature and access modifier?

`--add-exports` and `--add-opens` handle **access permissions**; they do not replace module resolution when a root or dependency has not been found.

### Error 7: Service Provider Does Not Appear

If you only use `resolve`, a provider module **is not necessarily** selected unless it is a root or a required dependency. `resolveAndBind` can bring service providers into the graph if the `uses`/`provides` descriptors and finder sources match.

After defining the layer, you still must use `ServiceLoader` with the proper API/layer and share the service interface type identity properly.

## 14. Tools for Inspecting the Module Graph

On JDK 17, you can use:

```bash
java --list-modules
java --describe-module java.base
java --module-path out/mods --describe-module m.extension
```

Note that `--describe-module` describes **modules visible in the launcher configuration**; not every child layer created later is automatically displayed like a launcher root. For custom layers, logging/printing `finder.findAll()`, `configuration.modules()`, and `layer.modules()` within the program itself is usually closer to the actual context.

You can observe module resolution when the JVM launches a modular app:

```bash
java --show-module-resolution --module-path mods -m m.app/app.Main
```

This is an **illustrative command**, requiring `mods` to contain module `m.app` and main class `app.Main`. It is not the command to run the `LayerDemo` example in section 8, because `LayerDemo` intentionally resolves modules programmatically. Do not confuse launcher boot resolution with custom child configuration resolution.

For class loading in HotSpot:

```bash
java -Xlog:class+load=info -cp out/host LayerDemo
```

The log can be very long; module discovery/resolution and class loading are two different levels. Looking at a single class-load line does not prove that the entire module graph or service binding is correct.

## 15. Self-Check Exercises

**Question 1.** Does `ModuleFinder.find("m.extension")` mean `m.extension` has already been resolved into the current configuration?

**Answer:** No. The finder indicates an observable module reference; the resolver still has to resolve roots/dependencies and validate the graph.

**Question 2.** Root `m.extension` has `requires m.core`. If `m.core` is present in the finder but not in the list of roots, will the resolver select it?

**Answer:** Yes, when it is a required dependency and has not already been provided by a parent configuration. The resolver follows `requires` to form the dependency closure.

**Question 3.** Does `Configuration.resolve` automatically create a class loader and run `static { ... }` of `plugin.Worker`?

**Answer:** No. It creates the module graph. Layer definition assigns modules to loaders; JVM class loading and initialization occur later on demand.

**Question 4.** Why does the example print `Available: [m.core, m.extension]` in alphabetical order?

**Answer:** The code uses `TreeSet` to sort names before printing; `ModuleFinder.findAll()` returns a `Set` without guaranteeing that ordering.

**Question 5.** `m.extension` `requires m.core`, but `m.core` does not export `api`. Is this a module-not-found error or a package access permission issue?

**Answer:** Primarily package accessibility in modular compilation/bytecode access. The dependency module may already be resolved, yet the public type in the package has not been exported to the client.

**Question 6.** How does `resolveAndBind` differ from `resolve`?

**Answer:** `resolveAndBind` includes a service binding step to find/add provider modules for services used by the resolved modules. It does not automatically instantiate provider objects.

**Question 7.** Why does class `plugin.Worker` in the example belong to the child layer rather than the boot layer?

**Answer:** The host creates a child `Configuration` and defines a child `ModuleLayer`, retrieves the loader via `layer.findLoader("m.extension")`, and then loads that module's class.

**Question 8.** A module exists on the module path and is visible to the finder, but no `requires` or root leads to it. Will it necessarily appear in the `Configuration`?

**Answer:** No. Resolution selects roots and dependencies (along with providers during service binding); it does not automatically include every module observed by the finder.

**Question 9.** Two JARs both provide different versions of module `m.core`. Does JPMS automatically select the "newer version" based on semver?

**Answer:** No. JPMS module resolution is not a Maven/Gradle dependency version resolver. You must specifically manage your artifact/graph/loader architecture.

**Question 10.** When `parent.resolve(... Set.of("m.absent"))` cannot find the root, what error is expected?

**Answer:** `FindException`, as in the runnable example in section 8; different from `ClassNotFoundException` in class lookup.

## 16. Summary and Official Documentation

**Five milestones to distinguish:**

1. **Discover:** `ModuleFinder` looks up `ModuleReference` by module name and module path/system image.
2. **Describe:** `ModuleDescriptor` provides `requires`, `exports`, `opens`, `uses`, `provides`, and metadata.
3. **Resolve:** `Configuration.resolve` builds a module graph from roots, dependencies, and the parent configuration; `resolveAndBind` adds service binding.
4. **Define:** `ModuleLayer` defines the resolved modules into the runtime with the appropriate loader mapping.
5. **Load/use:** `ClassLoader`/`Class.forName` retrieves `Class<?>`; JPMS readability/exports/opens and Java access rules continue to govern how code uses classes/members.

**Official Java 17 Documentation:**

- [Java SE 17 — ModuleFinder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html): `of`, `ofSystem`, `find`, and `findAll`.
- [Java SE 17 — Configuration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html): `resolve`, `resolveAndBind`, parent configurations, `findModule`, and `modules`.
- [Java SE 17 — ModuleReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleReference.html) and [ModuleDescriptor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html): module metadata.
- [Java SE 17 — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): layer definition, loader mapping, and `findLoader`.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): service providers in modules/layers.
- [JLS 17 — `7.7 Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7): `requires`, `exports`, `opens`, `uses`, and `provides`.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): JPMS architecture, launcher/module path, and resolution.
