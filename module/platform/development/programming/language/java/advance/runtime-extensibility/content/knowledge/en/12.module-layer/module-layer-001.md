# Relationships Between Configuration, ModuleLayer, Module, and Class Loader in Java

## 1. Four Concepts Participating in One Mechanism, Not Synonyms

Since Java 9, the **Java Platform Module System (JPMS)** introduced the concept of a *named module* and an explicit model for dependencies, readability, package exports (*exports*), and deep reflection permissions (*opens*). When a host needs to load extension modules at runtime, the following four entities commonly appear together:

- **`Configuration`** (`java.lang.module.Configuration`): a graph of **resolved modules** at the descriptor level; its vertices are `ResolvedModule` instances. It represents which modules are selected and which modules are permitted to *read* which modules before the modules are defined in the JVM.
- **`ModuleLayer`** (`java.lang.ModuleLayer`): a **runtime module layer** created from a `Configuration` and a mapping from each module to a `ClassLoader`. Creating the layer informs the JVM which named modules exist in that layer, which classes belong to which modules, and the corresponding module relationships.
- **`Module`** (`java.lang.Module`): the **concrete runtime module object**, created by the JVM when the layer is defined. Classes belonging to that named module can identify their module via `Class.getModule()`.
- **`ClassLoader`** (`java.lang.ClassLoader`): the mechanism for **finding and defining classes**, supplying classes and resources at runtime. Class loaders are associated with modules in a layer, though **a single class loader can serve multiple modules** depending on how the layer is created.

Conceptual flow:

```text
JAR/module directory
    └─ module-info.class + classes + resources
                     │
                     ▼
           ModuleFinder (discovers modules)
                     │
                     ▼
         Configuration.resolve(...)
           - root modules
           - requires / readability graph
           - parent Configuration(s)
                     │
                     ▼
         ModuleLayer.defineModules...
           + choose mapping module -> ClassLoader
           + specify parent layer(s)
                     │
                     ▼
        JVM creates java.lang.Module objects
        + links to layer
        + maps to class loaders
                     │
                     ▼
    Loader defines classes on demand
    Class<?>.getModule() -> runtime Module
    Module.getLayer()   -> runtime ModuleLayer
```

**Key takeaway:** `Configuration` answers “*what does the valid module graph consist of and who reads whom?*”; `ModuleLayer` answers “*in which layer is that graph realized into runtime modules?*”; `Module` is the “*concrete runtime module*”; `ClassLoader` answers “*by which loader is the module's code found/loaded?*”.

### Quick Comparison Table

| Aspect | `Configuration` | `ModuleLayer` | `Module` | `ClassLoader` |
| --- | --- | --- | --- | --- |
| Package | `java.lang.module` | `java.lang` | `java.lang` | `java.lang` |
| Unit | Resolved graph | Set of runtime modules in a layer | One runtime module | One class-loading object |
| Primary role | Determine dependencies and readability | Define modules in the JVM, bind modules to loaders | Represent a module and runtime access rights | Load/define classes, find resources |
| Contains / retrieves | `ResolvedModule` and `reads` edges | `Module`, parent layers, `Configuration` | Descriptor, packages, layer, loader | Loaded or loadable classes/resources |
| Common APIs | `modules()`, `findModule()`, `resolve()` | `configuration()`, `modules()`, `findLoader()`, `findModule()` | `getName()`, `getLayer()`, `getClassLoader()`, `canRead()` | `loadClass()`, `getResource()` |
| Exists before JVM defines new modules? | Yes | Not yet, for a new layer | Not yet, for a new module | Parent loader may already exist; child loader may be created when defining the layer |

`ResolvedModule` is **not** `java.lang.Module`: the former belongs to the resolution step, while the latter represents a module already defined at runtime.

## 2. From Module Descriptor to Configuration

### 2.1. The Descriptor Specifies Declared Relationships

A named module typically has a `module-info.java`:

```java
module plugin.greeting {
    requires app.api;
    provides app.api.GreetingService
        with plugin.greeting.HelloGreeting;
}
```

This is a **module descriptor**:

- `module plugin.greeting` names the module.
- `requires app.api` declares that the module depends on the shared API.
- `provides ... with ...` registers a provider so that `ServiceLoader` can discover the service in the appropriate layer.
- If the implementation package does not need to be called directly by other APIs, **`exports plugin.greeting` is not needed** solely for SPI to instantiate the provider.

In addition to `requires`, JPMS also has `requires transitive`, `requires static`, `exports`, `opens`, and `uses`. They address different requirements: module readability, public type usage, reflective access, and the service mechanism.

Those lines are merely **declarations**; the module name in the file does not by itself create a new runtime module for the JVM.

### 2.2. ModuleFinder Determines Observable Modules

`ModuleFinder` (`java.lang.module.ModuleFinder`) is the mechanism for finding **module artifacts**, such as a modular JAR or an exploded module directory.

```java
Path pluginJar = Path.of("dist/plugins/plugin.greeting.jar");
ModuleFinder finder = ModuleFinder.of(pluginJar);
```

This is **illustrative code** (requiring `import java.nio.file.Path;` and `import java.lang.module.ModuleFinder;`, plus a valid JAR file). `ModuleFinder.of(path)` does not by itself create a `ModuleLayer`, launch `main`, or invoke SPI providers. It only provides a way to locate module references and metadata for the resolution step.

In real-world applications, plugin artifacts should have their origin, integrity, version, and policy verified before being passed to a module finder if untrusted. Finding artifacts is not a security isolation mechanism.

### 2.3. Configuration.resolve Creates the Readability Graph

A common pattern using the **boot layer as parent**:

```java
ModuleLayer parent = ModuleLayer.boot();

Configuration cf = parent.configuration().resolve(
    finder,                 // search new modules first
    ModuleFinder.of(),     // supplemental finder (empty here)
    Set.of("plugin.greeting") // root module name to resolve
);
```

This is an **illustrative snippet** importing `java.lang.module.Configuration`, `ModuleFinder`, and `java.util.Set`; a complete runnable example is in section 5.

Meaning of the parameters:

- `parent.configuration()` is the resolved module graph of the boot layer; modules in the boot layer—for example `java.base` and `app.api` if the application was launched with that API module—can serve as dependencies for the new module.
- `finder` is the set of modules searched **before** the parent configurations during resolution.
- `ModuleFinder.of()` is the supplemental finder searched **after** parent configurations; left empty in this example.
- `Set.of("plugin.greeting")` specifies the root modules (*roots*) of resolution, not necessarily all modules required in the configuration. `requires` clauses can pull in additional modules from the finder.

With `resolve(before, after, roots)`, resolution applies the search order before → parent configuration → after to locate required modules. **Modules already found in a parent configuration are not “copied” into the new configuration**; the new graph can reference modules in the parent. Therefore, with `plugin.greeting requires app.api`, if `app.api` is already in the boot configuration, the new layer usually only needs to define `plugin.greeting`, while `app.api` continues to live in the parent layer.

### 2.4. Configuration Holds ResolvedModule, Not Class Loaders

A `Configuration` provides:

```java
for (ResolvedModule m : cf.modules()) {
    System.out.println(m.name());
    for (ResolvedModule dependency : m.reads()) {
        System.out.println("  reads: " + dependency.name());
    }
}
```

This is an **illustrative snippet** using `import java.lang.module.ResolvedModule;`, executed after `cf` is created. `cf.modules()` lists only the `ResolvedModule` instances **directly in that configuration**; `cf.findModule(name)` can search in the configuration or parent configurations. Distinguishing this is important when debugging a dependency graph.

`Configuration` describes the *module readability graph* but does not dictate the class loader for each module. It can be computed before the host chooses whether to use a shared loader or one loader per module. Information such as version, module descriptors, references, and `reads` edges does not equate to classes having been loaded into the JVM.

**Successful resolution does not guarantee runtime code will run cleanly**: bytecode files may be corrupt, libraries may have linkage errors, reflective access permissions may be missing, service providers may fail to instantiate, or application logic may require other configuration. These are subsequent steps to verify.

### 2.5. Distinguishing resolve and resolveAndBind

- `resolve(...)` resolves starting from the **root modules** and their required dependencies.
- `resolveAndBind(...)` additionally performs **service binding**, which can pull in observable provider modules that match services being used, according to JPMS rules.

If the plugin is explicitly passed in the roots (`Set.of("plugin.greeting")`), `resolve(...)` is sufficient for this example. Do not assume that merely declaring `uses` causes `resolve(...)` to automatically gather every provider module on disk; when you want to discover provider modules via service binding, look into `resolveAndBind` and the scope of `ModuleFinder`.

## 3. From Configuration to ModuleLayer

### 3.1. A Layer Realizes the Resolved Graph

Typical API:

```java
ModuleLayer parent = ModuleLayer.boot();

ModuleLayer child = parent.defineModulesWithOneLoader(
    cf,
    ClassLoader.getSystemClassLoader()
);
```

When called:

1. The JVM checks the validity of the configuration against the parent layer; when using the instance method, the new configuration must have **exactly one parent configuration**, namely `parent.configuration()`.
2. The API creates a new class loader for all modules **in the new configuration** (for `defineModulesWithOneLoader`), using the passed-in class loader as the **parent of the new loader**.
3. The JVM creates a `java.lang.Module` corresponding to each `ResolvedModule` in the new configuration and associates it with the new `ModuleLayer`.
4. The runtime establishes the resolved module read edges; new modules can read modules in their own layer or in parent layers according to the graph.
5. The new layer is ready for classes to be loaded on demand, though **defining the layer does not mean all classes are loaded/initialized or providers have executed**.

`ModuleLayer.boot()` is the boot layer created by the JVM at startup, containing `java.base` and other modules resolved for that run. An application can create multiple child layers from the boot layer or build a tree/DAG of layers; a layer is not a single JVM-wide namespace.

**Note on the `parentLoader` parameter name:** This is the **parent loader of the new loader**, not an instruction to the JVM to place all new modules directly into the exact loader object passed in. In the example `defineModulesWithOneLoader(cf, ClassLoader.getSystemClassLoader())`, the loader for the plugin is a **new loader**, normally not equal to the system loader.

### 3.2. Module → Loader Mapping Options

| Layer creation method | How are modules mapped? | When to consider? |
| --- | --- | --- |
| `parent.defineModulesWithOneLoader(cf, parentLoader)` | **All modules in the new configuration share one new loader** | A group of modules packaged together, simple, without package/delegation conflicts |
| `parent.defineModulesWithManyLoaders(cf, parentLoader)` | **Each module gets its own new loader** | Stronger separation between modules, more complex dependency/module graphs |
| `parent.defineModules(cf, moduleName -> loader)` | Host maps module names to loaders per custom policy | Integrating custom class loaders or specialized code-loading mechanisms |
| Static `ModuleLayer.defineModules...(cf, parents, ...)` methods | Allows multiple parent layers, returns `ModuleLayer.Controller` | Multi-parent layer structures or needing runtime control over reads/exports/opens |

For the **instance** forms, `defineModulesWithOneLoader` and `defineModulesWithManyLoaders` return `ModuleLayer`. For the **static forms taking a list of parent layers**, the return value is `ModuleLayer.Controller`; call `controller.layer()` to obtain the layer. Do not mix up the two API signatures.

`defineModulesWithOneLoader` can fail if modules in the same layer have overlapping packages or if a loader's delegation for a package is split across multiple loaders. `defineModulesWithManyLoaders` creates a separate loader per module, yet **does not automatically solve** all dependency/version, readability, or package conflict issues under JPMS rules. `defineModules` with custom loaders requires the host to guarantee delegation rules compatible with readability, avoiding duplicate package/module definitions and concurrent class-loading deadlocks.

### 3.3. Layer Parent and Class Loader Parent Are Two Different Relationships

A common mistake is equating:

- **Parent ModuleLayer:** the relationship between *runtime module layers*. `child.parents()` returns the parent layers; they reflect the structure from parent configurations when the layer was created.
- **Parent ClassLoader:** the class-lookup delegation relationship between loaders. It is determined by how the class loader is constructed—for example, `defineModulesWithOneLoader(cf, parentLoader)` uses a new loader whose parent is `parentLoader`.

These two relationships **do not have to share the same structure**. A parent layer can contain modules loaded by multiple built-in class loaders. A loader in a child layer can use direct delegation to the specific loader of a dependency module rather than merely following a conventional parent chain. Do not conclude that “layer A is the parent of B” means every class in A is loaded by the direct parent of every loader in B.

Example diagram:

```text
            ModuleLayer.boot()
             configuration0
           /               \
   java.base             app.api
   bootstrap loader      app/system loader
           \               /
            \  readability
             \            /
             ModuleLayer child
               configuration1
               plugin.greeting
               loader L (new)
                      │
               parentLoader = system
```

This is a conceptual model; the exact class loaders for boot modules depend on how the JVM organizes built-in modules. `plugin.greeting` is resolved with a dependency on `app.api` in the boot configuration; the plugin's classes are defined in loader L; `app.api` classes remain in the loader that defined the API in the boot layer. Module readability constraints and the class-loading mechanism cooperate, yet solve two distinct aspects.

## 4. Runtime Modules and API Query Paths

### 4.1. Distinguishing the Two “modules()” Sets

`Configuration.modules()` returns a set of **`ResolvedModule`**, whereas `ModuleLayer.modules()` returns a set of **`java.lang.Module`**.

```java
Set<ResolvedModule> resolved = cf.modules();
Set<Module> runtime = child.modules();
```

This is an illustrative snippet after obtaining `cf` and `child`.

If module `app.api` resides in the boot layer, while `plugin.greeting` resides in the child layer:

- `child.modules()` contains `plugin.greeting` and **does not automatically contain** `app.api` merely because the plugin reads the API.
- `child.findModule("app.api")` **can locate** the `app.api` module in the parent layer.
- `cf.modules()` contains the newly resolved modules in the child's configuration; `cf.findModule("app.api")` can look up through parent configurations.

Therefore, if you want to check “was this module created **in the new layer itself** or does it just reside in a parent?”, check `child.modules().contains(module)` rather than just `child.findModule(name).isPresent()`.

### 4.2. Using Class and Module to Check Actual Placement

Once a class has been loaded:

```java
Module module = provider.getClass().getModule();
ModuleLayer ownerLayer = module.getLayer();
ClassLoader loader = provider.getClass().getClassLoader();
```

Illustrative snippet after `provider` has been instantiated.

- `Class.getModule()` indicates the runtime module to which the class belongs.
- `Module.getLayer()` returns the layer containing that named module; it may be `null` for an unnamed module.
- `Module.getClassLoader()` returns the class loader that defines the module (which may be `null` for the bootstrap loader).
- `Class.getClassLoader()` returns the defining loader of the class, which can also be `null` for classes from the bootstrap loader.

With the plugin as a named module created by `child`, `provider.getClass().getModule().getLayer() == child`. With the service API residing in `app.api` in the boot layer, `GreetingService.class.getModule().getLayer() == ModuleLayer.boot()`.

### 4.3. Finding Modules and Loaders by Name

```java
Module pluginModule = child.findModule("plugin.greeting")
    .orElseThrow();

ClassLoader pluginLoader = child.findLoader("plugin.greeting");
```

`ModuleLayer.findModule(name)` returns `Optional<Module>`, searching the current layer and then parent layers in order. `ModuleLayer.findLoader(name)` also checks parent layers, except:

- It returns `ClassLoader` directly; **`null` is a valid value** when the module belongs to the bootstrap loader.
- It throws `IllegalArgumentException` if no module with that name exists in the layer or its parent layers.
- It **does not** return `Optional<ClassLoader>`, precisely because it must represent the bootstrap loader as `null`.

These APIs help diagnose which module actually owns a class loader. They do not imply that the loader itself determines module reads or exports.

### 4.4. Readability, Exports, Opens, and Class Loaders

Suppose `plugin.greeting` needs a public class from `app.api`.

- `requires app.api` makes `plugin.greeting` **read** `app.api` according to the resolved graph.
- `app.api` must **export** the package containing the public API to `plugin.greeting` (an unqualified or appropriate qualified export) so plugin code can legally use the type.
- `opens` primarily relates to deep reflective access; `opens` cannot substitute for `exports` when compiling normal module code that references public types.
- The class loader must actually locate the matching bytecode, but **being able to load a class does not automatically grant access permission** if readability/exports are violated.

The Module API provides `canRead(other)` and `isExported(package, other)` to observe runtime relationships. The loader helps locate classes, while the JVM enforces module access rules. This differs from the classpath/unnamed module, where the default access model is broader.

### 4.5. Modules with the Same Name Can Exist in Different Layers

A host can have two separate layers, each defining a module named `plugin.greeting` (with separate loaders) to serve two plugin sets/versions. Those two `java.lang.Module` objects are **not a single runtime module**. Classes with the same fully qualified name defined by two different loaders do not by default share the same runtime type either.

This is useful for side-by-side versions, subject to certain constraints:

- The shared API should live in a stable module/loader from which plugins read the same type.
- Do not cast an instance of version A's class to version B's class if their defining loaders differ.
- Do not let the old version retain threads, TCCL, static caches, or listeners that prevent the loader from being garbage collected.
- A new `ModuleLayer` does not automatically migrate state or stop old code.

## 5. Java 17+ Example: From Configuration to ModuleLayer and Runtime Provider

The program below builds three modules:

1. **`app.api`:** the `GreetingService` contract.
2. **`app.host`:** the launcher program, running in the **boot layer**, which knows the contract and consumes the service via `uses`.
3. **`plugin.greeting`:** a named module packaged in a **separate JAR**, resolved by the host and placed into a **child layer** at runtime.

The goal is to observe directly: `Configuration` resolves the provider module, `ModuleLayer` defines it, `Module` attaches to the new layer, and `ClassLoader` is mapped for the provider. The program uses `ServiceLoader.load(layer, ...)` to invoke the provider, verifying that the shared contract remains compatible across parent and child layers.

### 5.1. Directory Structure

```text
demo/
├── src/
│   ├── app.api/
│   │   ├── module-info.java
│   │   └── app/api/GreetingService.java
│   ├── app.host/
│   │   ├── module-info.java
│   │   └── app/host/Main.java
│   └── plugin.greeting/
│       ├── module-info.java
│       └── plugin/greeting/HelloGreeting.java
├── mods/                       # compilation output directory
└── dist/plugins/               # directory for plugin module JARs
```

Each `module-info.java` file must be compiled together with the classes of its corresponding module. Creating `mods` and `dist` is shown in the PowerShell commands section.

### 5.2. Shared API Module

**`src/app.api/module-info.java`**

```java
module app.api {
    exports app.api;
}
```

**`src/app.api/app/api/GreetingService.java`**

```java
package app.api;

public interface GreetingService {
    String greet(String name);
}
```

`exports app.api` allows named modules that read `app.api` to use this public interface. The contract resides in a module that the host places in the boot layer, preventing each plugin from having its own copy of `GreetingService` defined by a separate loader.

### 5.3. Separate Provider Module

**`src/plugin.greeting/module-info.java`**

```java
module plugin.greeting {
    requires app.api;
    provides app.api.GreetingService
        with plugin.greeting.HelloGreeting;
}
```

**`src/plugin.greeting/plugin/greeting/HelloGreeting.java`**

```java
package plugin.greeting;

import app.api.GreetingService;

public final class HelloGreeting implements GreetingService {
    public HelloGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

The provider has a public no-arg constructor, suitable for demonstrating SPI. The `plugin.greeting` package is **not exported** externally just because the module uses `provides`; the host does not need to access the implementation class directly and only needs to view it through the `GreetingService` contract.

### 5.4. Host Module and Program Creating the Child Layer

**`src/app.host/module-info.java`**

```java
module app.host {
    requires app.api;
    uses app.api.GreetingService;
}
```

`uses` declares that the host is a service consumer. In a named module, when calling `ServiceLoader`, the caller module must declare the used service under JPMS rules.

**`src/app.host/app/host/Main.java`**

```java
package app.host;

import app.api.GreetingService;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.module.ResolvedModule;
import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;

public final class Main {
    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Usage: Main <plugin-modular-jar>");
        }

        // (1) The boot layer already contains app.host and app.api.
        ModuleLayer boot = ModuleLayer.boot();

        // (2) Let resolution observe the plugin modular JAR.
        ModuleFinder finder = ModuleFinder.of(Path.of(args[0]));

        // (3) Resolve the plugin module name and its related requires.
        Configuration cf = boot.configuration().resolve(
            finder,
            ModuleFinder.of(),
            Set.of("plugin.greeting")
        );

        boolean inNewConfig = cf.modules().stream()
            .map(ResolvedModule::name)
            .anyMatch("plugin.greeting"::equals);

        // (4) Define the child layer; one NEW loader for the new module.
        ModuleLayer child = boot.defineModulesWithOneLoader(
            cf,
            ClassLoader.getSystemClassLoader()
        );

        // (5) Runtime Module and the mapped loader.
        Module pluginModule = child.findModule("plugin.greeting")
            .orElseThrow();
        ClassLoader mappedLoader = child.findLoader("plugin.greeting");

        // (6) ServiceLoader uses this layer to locate/instantiate the provider.
        GreetingService provider = ServiceLoader
            .load(child, GreetingService.class)
            .findFirst()
            .orElseThrow(() -> new IllegalStateException(
                "No GreetingService provider in layer"));

        System.out.println("Config parent is boot: "
            + (cf.parents().get(0) == boot.configuration()));
        System.out.println("Resolved plugin in config: "
            + inNewConfig);
        System.out.println("Plugin belongs to child layer: "
            + child.modules().contains(pluginModule));
        System.out.println("Provider module is plugin module: "
            + (provider.getClass().getModule() == pluginModule));
        System.out.println("API module belongs to boot: "
            + (GreetingService.class.getModule().getLayer() == boot));
        System.out.println("Provider loader is mapped loader: "
            + (provider.getClass().getClassLoader() == mappedLoader));
        System.out.println("Plugin loader differs from system loader: "
            + (mappedLoader != ClassLoader.getSystemClassLoader()));
        System.out.println(provider.greet("JPMS"));
    }
}
```

The above is a **complete program** for Java 17+. Meaning of each operation:

1. `boot` is the layer already present when the host is launched as a named module.
2. `finder` observes the plugin module JAR specified via the argument.
3. `cf` contains the resolved module `plugin.greeting`; `app.api` is found from the parent configuration because the host placed it into boot.
4. `child` defines the new runtime module; `defineModulesWithOneLoader` creates a **new loader** with the system loader as its parent.
5. `child.findModule(...)` returns the runtime `java.lang.Module`; `child.findLoader(...)` returns the actual mapped loader.
6. `ServiceLoader.load(child, GreetingService.class)` searches for providers in the child layer and relevant parent layers; in this demo only one provider is declared in the plugin. `findFirst()` instantiates the provider and invokes it through the shared API.

`ServiceLoader` **does not** automatically invoke business lifecycle methods such as `start`/`stop`; this example only performs `greet` to focus on the differences between configuration, layer, module, and loader.

### 5.5. Compiling on Windows PowerShell (JDK 17+)

From the `demo` directory; requires `java`, `javac`, and `jar` on `PATH`:

```powershell
# Build the API module first.
New-Item -ItemType Directory -Force mods/app.api | Out-Null
javac -encoding UTF-8 -d mods/app.api src/app.api/module-info.java src/app.api/app/api/GreetingService.java

# The host needs to read the compiled API.
New-Item -ItemType Directory -Force mods/app.host | Out-Null
javac -encoding UTF-8 --module-path mods/app.api -d mods/app.host src/app.host/module-info.java src/app.host/app/host/Main.java

# The provider also needs the API, but not the host implementation.
New-Item -ItemType Directory -Force mods/plugin.greeting, dist/plugins | Out-Null
javac -encoding UTF-8 --module-path mods/app.api -d mods/plugin.greeting src/plugin.greeting/module-info.java src/plugin.greeting/plugin/greeting/HelloGreeting.java

# Package the modular JAR, including module-info.class.
jar --create --file dist/plugins/plugin.greeting.jar -C mods/plugin.greeting .

# Only the API and host are on the startup module path.
# The host creates a ModuleFinder for the plugin JAR at runtime.
java --module-path 'mods/app.api;mods/app.host' --module app.host/app.host.Main dist/plugins/plugin.greeting.jar
```

Note the semicolon `;` in the **Windows** module path; put it inside quotes so PowerShell preserves it as a single argument. On Linux/macOS use a colon `:`, for example `--module-path 'mods/app.api:mods/app.host'`. `dist/plugins/plugin.greeting.jar` is not placed on the startup module path; it serves as the source for the host's `ModuleFinder`.

**Expected stdout, exact:**

```text
Config parent is boot: true
Resolved plugin in config: true
Plugin belongs to child layer: true
Provider module is plugin module: true
API module belongs to boot: true
Provider loader is mapped loader: true
Plugin loader differs from system loader: true
Hello, JPMS!
```

The program uses `boolean` values and fixed strings so that stdout does not depend on `ClassLoader.toString()`, `Set` ordering, or how the JVM names loader classes. When run on JDK 17 with the exact structure and commands above, these lines illustrate the observable relationships.

### 5.6. Reading the Output from an API Perspective

`Config parent is boot: true` proves the new configuration is built on top of the boot layer's configuration. `Resolved plugin in config: true` shows the plugin module was resolved in the new configuration.

`Plugin belongs to child layer: true` proves the plugin's `Module` object belongs to `child.modules()`; it was not merely found via a parent layer. `Provider module is plugin module: true` shows the provider implementation class is indeed a member of that runtime module.

`API module belongs to boot: true` shows the service contract comes from the parent module, avoiding duplicate `GreetingService` definitions between host and plugin. `Provider loader is mapped loader: true` and `Plugin loader differs from system loader: true` prove `defineModulesWithOneLoader` creates a new loader and maps the plugin to it; the `parentLoader` argument does not become the plugin's loader.

Finally, `Hello, JPMS!` proves the host obtains the provider via `ServiceLoader.load(child, GreetingService.class)` and invokes the method through the shared service contract.

### 5.7. Trying Failure Cases

**JAR not found or wrong module name:** replace the argument with a path to a missing file, or change roots from `plugin.greeting` to a nonexistent name. Resolution can fail with `FindException` or a related error when the module is not observable; `ModuleFinder` does not automatically download missing JARs from Maven Central.

**Missing `requires app.api`:** the provider implementation references `app.api.GreetingService`; when compiling the named module, an error occurs indicating the package/module cannot be read, unless supplemental flags alter the conditions. This proves readability is a property of the module graph, not whether a class loader can see `GreetingService.class`.

**Missing `exports app.api`:** the host/plugin cannot access the public interface from another named module under standard JPMS access rules, even if the API module has been resolved.

**Missing `provides` declaration:** the plugin can still be resolved and defined in the layer, but `ServiceLoader` will not see the provider through the module declaration. This is a clear example that “a module exists in the layer” and “a service is registered” are two different concepts.

**Missing `uses` in the host:** calling `ServiceLoader` from the named host module can fail with `ServiceConfigurationError` because the caller module has not declared usage of the service. Even with a valid class loader and module graph, SPI enforces its own constraints.

**Switching to `defineModulesWithManyLoaders`:** with a single plugin module, the business result remains similar, though the class-loading architecture may differ; if there are multiple new modules, each module in the configuration is assigned its own loader. Do not infer that a module is isolated for OS-level permissions merely because it has its own loader.

## 6. Putting APIs Side by Side to Avoid Confusion

| API | Returns | What Actually Happens |
| --- | --- | --- |
| `ModuleFinder.of(paths...)` | `ModuleFinder` | Enables locating module references from artifacts |
| `Configuration.resolve(...)` | `Configuration` | Resolves the module graph and readability |
| `Configuration.resolveAndBind(...)` | `Configuration` | Resolves with service binding |
| `cf.modules()` | `Set<ResolvedModule>` | Views modules resolved **directly in the configuration** |
| `cf.findModule(name)` | `Optional<ResolvedModule>` | Searches in the configuration and parent configs |
| `parent.defineModulesWithOneLoader(cf, loader)` | `ModuleLayer` | Creates a layer with **one new loader** for all new modules |
| `parent.defineModulesWithManyLoaders(cf, loader)` | `ModuleLayer` | Creates a layer with a new loader **for each module** |
| `ModuleLayer.defineModulesWithOneLoader(cf, parents, loader)` | `ModuleLayer.Controller` | Static layer creation supporting multiple parent layers |
| `child.configuration()` | `Configuration` | Gets the configuration used to define the layer |
| `child.modules()` | `Set<Module>` | Gets runtime modules directly in the layer |
| `child.findModule(name)` | `Optional<Module>` | Finds a module in the layer or parent layers |
| `child.findLoader(name)` | `ClassLoader` (may be `null`) | Finds the loader of a runtime module, or throws if no such module exists |
| `SomeClass.class.getModule()` | `Module` | Identifies the runtime module containing the class |
| `module.getLayer()` | `ModuleLayer` (may be `null`) | Identifies the layer of a named runtime module |
| `module.getClassLoader()` | `ClassLoader` (may be `null`) | Loader defining the module |
| `ServiceLoader.load(layer, Service.class)` | `ServiceLoader<Service>` | Discovers service providers in the defined layer |

**Common type mistakes:**

```java
// WRONG: Configuration.modules() does not return Set<Module>.
// Set<Module> wrong = cf.modules();

// CORRECT:
Set<ResolvedModule> description = cf.modules();
Set<Module> runtimeModules = child.modules();
```

This snippet is illustrative, assuming `cf` and `child` are declared and `Set`, `ResolvedModule` are imported. `ResolvedModule` differs from `Module` in both meaning and data type.

Another mistake:

```java
// WRONG: passing a configuration whose parent does not match the receiver layer.
// ModuleLayer unrelated = ...;
// unrelated.defineModulesWithOneLoader(cf, someLoader);

// CORRECT: use the parent layer corresponding to the parent Configuration.
ModuleLayer child = boot.defineModulesWithOneLoader(
    cf, ClassLoader.getSystemClassLoader());
```

In the snippet above, `boot` and `cf` come from the earlier setup; the incorrect statements are just a counterexample. If there are **multiple parent configurations**, use the static method accepting `List<ModuleLayer>` in the exact matching order and work through `Controller`.

## 7. Design Scenarios in Real Plugin Systems

### 7.1. A Single Simple Plugin Module

The host can keep `app.api` and `app.host` in the boot layer and place `plugin.greeting` into a child layer. `requires app.api` and `exports app.api` ensure the implementation sees the API. `ServiceLoader.load(child, Service.class)` selects the provider, and the host manages the business contract.

Pros: clear structure without placing every plugin on the module path at JVM startup. Cons: still requires handling versions, dependencies, metadata, module-loading failures, provider initialization, logging, shutdown, and class loader leaks.

### 7.2. Multiple Plugins Sharing a Dependency Library

Suppose `plugin.report` and `plugin.export` both read `lib.common`. You can resolve `lib.common` together in the new configuration or place the shared library in a stable parent layer, depending on compatibility and upgrade policies. Choosing `defineModulesWithOneLoader` places the new modules into **the same loader**; choosing `defineModulesWithManyLoaders` gives each its own loader.

Neither option is universally best for every application: separate loaders offer better class-namespace and lifecycle isolation, but require careful management of type handoffs, context, and dependencies. Both must respect `requires`/`exports` and JPMS package constraints.

### 7.3. Two Plugin Versions Side by Side

Create two child layers from the same boot layer, each resolving a different version of `plugin.greeting` from its respective JAR (if configuration and identity permit). Each layer has its own runtime `Module`/loader. The host can prepare the new version, health-check it, and then switch traffic before stopping the old version.

**Do not** pass an instance of the old version's implementation class directly where the new version's implementation class is expected; two identically named classes defined by different loaders are not automatically compatible. Keep contracts/DTOs in a shared module or transfer state via a neutral format.

### 7.4. A Layer with Multiple Parent Layers

A plugin may require modules from two layer branches. Static API:

```java
ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithManyLoaders(
        childConfiguration,
        List.of(parentLayerA, parentLayerB),
        ClassLoader.getSystemClassLoader()
    );
ModuleLayer child = controller.layer();
```

This is an **illustrative snippet**, not a standalone program. `childConfiguration` must have parent configurations matching `List.of(parentLayerA, parentLayerB)` **exactly and in the same order**. The instance API `parentLayerA.defineModulesWithManyLoaders(...)` only applies when the configuration has a single parent. `Controller` provides runtime adjustment capabilities such as adding read/export/open edges within API limits; it does not eliminate the need for runtime plugin lifecycle management.

### 7.5. Needing Plugin Resources or Reflection

If the host wants to read resources from a named module, it must pay attention to resource encapsulation rules and module openness. `ClassLoader.getResourceAsStream(...)` is not guaranteed to read every resource from a named module because resources may be encapsulated; use `Module.getResourceAsStream` or resource APIs from code in the appropriate module when suitable.

If a framework needs deep reflection into a plugin's package, `requires` and `exports` alone may not suffice; `opens` to the permitted target is needed. Opening every package indiscriminately weakens module encapsulation boundaries.

### 7.6. Service Discovery Does Not Equate to Module Resolution

A module can be resolved and defined in a layer without registering `provides` for any service; in that case `ServiceLoader` finds no provider. Conversely, a service declaration may be valid in metadata while instantiation fails due to implementation or dependency issues. Therefore, clearly distinguish:

1. **Module observed:** Did `ModuleFinder` locate the artifact?
2. **Module resolved:** Does `Configuration` contain the matching `ResolvedModule`?
3. **Module defined:** Has `ModuleLayer` created the runtime `Module`?
4. **Class loaded:** Has the class loader defined the required class?
5. **Provider instantiated:** Did `ServiceLoader`/factory successfully create an instance?
6. **Plugin ready:** Has the host validated configuration, business dependencies, and invoked lifecycle start?

Do not treat those six states as a single event “plugin loaded”.

## 8. Diagnosing Errors by Boundary

| Stage | Symptom / Error API | Common Cause | How to Handle |
| --- | --- | --- | --- |
| Finder | Root module not found | Wrong path/JAR; missing module-info; wrong module name | Inspect JAR with `jar --describe-module`, check path and name |
| Resolve | `FindException` | Root module or dependency not observable | Check before/after finders, parent configs, `requires` |
| Resolve | `ResolutionException` | Inconsistent graph; package/readability conflict or invalid resolution constraints | Inspect module/package names and read edges |
| Define layer | `IllegalArgumentException` | Parents of `Configuration` do not match passed layer(s) | Build cf from the right `parent.configuration()`, in the same order |
| Define layer | `LayerInstantiationException` | Package/loader conflict, special Java module, or invalid loader mapping | Review one/many/custom loader policy and module packages |
| Class link/load | `ClassNotFoundException` / `NoClassDefFoundError` / `LinkageError` | Missing dependency, binary incompatibility, wrong loader mapping | Check artifacts, module graph, versions, and class loaders |
| Java access | `IllegalAccessError` or reflection error | Missing `requires`, `exports`, or `opens` | Separate readability from accessibility; fix module descriptors |
| Service lookup | `ServiceConfigurationError` | Incorrect `uses/provides`, invalid provider constructor/class | Check module declarations and implementation |
| Runtime | Provider not found despite module being present | Module is in layer without service registration or wrong layer selected | Use `ServiceLoader.load(layer, ...)`, verify `provides` |
| Reload | Old classes remain | Old layer/loader/instance still referenced; misunderstanding `reload()` | Manage versions, stop, callbacks, threads, and class loaders |

When issues arise, print **verifiable information**, such as module names, `cf.modules()`, `layer.modules()`, `module.getLayer()`, `module.getClassLoader()`, `layer.parents()`, and runtime descriptors. Do not print secrets or rely on a loader's `toString()` string as a stable identifier.

### Design Mistakes to Avoid

- **Confusing `Configuration` with `ModuleLayer`:** having a `ResolvedModule` does not mean the JVM has defined a runtime module.
- **Confusing `ResolvedModule` with `Module`:** they are two different types and stages.
- **Confusing parent layer with parent class loader:** one is the module graph, while the other is the class-loading delegation mechanism.
- **Assuming `defineModulesWithOneLoader(..., parentLoader)` uses the passed loader itself:** the API **creates a new loader** with `parentLoader` as its parent.
- **Assuming `child.modules()` includes all parent modules:** it includes only runtime modules directly in the child; `findModule` searches across parents.
- **Assuming a loader seeing bytecode allows using every public class:** `requires` and `exports` still apply; deep reflection requires `opens`.
- **Assuming the same module/class name in two layers is one identity:** runtime module/class and defining loader must both be considered.
- **Assuming a layer is a sandbox boundary:** module graphs and loaders do not by themselves isolate process privileges; untrusted plugins require proper process/OS boundaries.
- **Assuming defining a layer automatically starts/stops a plugin:** the host must still execute the business lifecycle.

## 9. Checklist When Designing ModuleLayer for Plugins

- [ ] Clearly identify contract modules in a stable layer and provider modules to load dynamically.
- [ ] Declare `module-info.java` accurately: `requires`, `exports`, `uses`, `provides`, and `opens` where needed.
- [ ] Use `ModuleFinder` to observe the right modular JARs/paths and verify their origin.
- [ ] Resolve `Configuration` against the proper parent configurations; distinguish `resolve` from `resolveAndBind`.
- [ ] Inspect `ResolvedModule` and the `reads` graph before defining the layer when diagnosing dependencies.
- [ ] Choose one/many/custom loader mapping based on packages, dependencies, and upgrade needs.
- [ ] Distinguish parent layer, parent configuration, and parent class loader.
- [ ] After creating the layer, verify `ModuleLayer.modules()`, `Module.getLayer()`, and `findLoader()` instead of guessing.
- [ ] Select providers via the service contract and `ServiceLoader.load(layer, ...)`; do not confuse provider discovery with instance readiness.
- [ ] Manage start, invocations, stop, cleanup, and old loader references in the plugin manager; do not treat `ServiceLoader.reload()` as hot swap.

**Official Java SE 17 Documentation:** [`Configuration`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html), [`ResolvedModule`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ResolvedModule.html), [`ModuleFinder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html), [`ModuleLayer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html), [`Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html), [`ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html).