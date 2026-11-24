# Creating a Child Layer with defineModulesWithOneLoader in Java

## 1. Goal: Creating a Child Module Layer with Its Own Class Loader

When a Java application uses the **Java Platform Module System (JPMS)**, a program can load additional **named modules** into a new `ModuleLayer` instead of placing every module in the boot layer at JVM startup. This approach is especially useful when a host has a plugin system and wants to organize extension modules by configuration layer and lifecycle.

A `ModuleLayer` is a group of modules defined at runtime based on a previously resolved `Configuration`. A layer can reference a **parent layer** so its modules can use suitable modules above it. `ModuleLayer.boot()` is the layer created by the JVM at startup with the modules of the boot configuration.

The **`defineModulesWithOneLoader`** method creates a **child layer** and uses **one new class loader for every module defined in that layer**. This API does not mean the passed-in class loader itself is used directly to define all new modules; the `parentLoader` parameter is the **parent loader** of the new loader created by the system.

An overview:

```text
ModuleLayer.boot()          (parent layer, already exists)
        |
        | parent configuration + new module path
        v
Configuration.resolve(...)  (builds the resolved module graph)
        |
        | defineModulesWithOneLoader(configuration, parentLoader)
        v
child ModuleLayer
   +-- demo.api      --+
   +-- demo.plugin   --+--> same new loader of the child layer
        |
        +-- uses modules in parent layer if the graph permits
```

For example, two modules `demo.api` and `demo.plugin` can reside together in a child layer; `demo.plugin` requires `demo.api`. Both modules are loaded by the same new loader, while the host program can still run on the classpath with the system loader.

**Key distinction:** `Configuration` describes which modules are selected and their `requires` relationships; `ModuleLayer` defines actual modules at runtime and associates them with class loaders. Successfully creating a configuration does **not yet** mean the modules have been defined into a layer.

## 2. Prerequisites and Participating Components

### 2.1. ModuleFinder: Discovering Resolvable Modules

`java.lang.module.ModuleFinder` provides a list of modules from one or more paths:

```java
ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
```

This is an illustrative Java snippet, requiring `import java.lang.module.ModuleFinder` and `import java.nio.file.Path`. The `mods` directory in the example will contain two compiled **exploded named modules**:

```text
mods/
  demo.api/
    module-info.class
    example/api/Message.class
  demo.plugin/
    module-info.class
    example/plugin/Greeter.class
```

`ModuleFinder` can also read valid **modular JARs** in the provided paths. Do not confuse the module path with the classpath: a JAR loaded via the regular classpath does not automatically become a named module of a child layer. A discovered module can be an **explicit module** with `module-info.class` or an **automatic module** in appropriate cases; the example below intentionally uses explicit modules to keep behavior clear.

`ModuleFinder.of(...)` is only the step of specifying the module source. Errors in lookup, reading descriptors, or dependency resolution may only surface when calling `find`, `findAll`, or `Configuration.resolve`, so do not treat successful finder creation as proof of valid artifacts.

### 2.2. Configuration: Resolving the Module Graph

From the parent layer, obtain the parent's configuration and call `resolve`:

```java
ModuleLayer parent = ModuleLayer.boot();

Configuration config = parent.configuration().resolve(
        ModuleFinder.of(Path.of("mods")),
        ModuleFinder.of(),
        Set.of("demo.plugin"));
```

This is an illustrative snippet, requiring imports for `java.lang.module.Configuration`, `java.lang.module.ModuleFinder`, `java.nio.file.Path`, and `java.util.Set`.

Three core parameters of `Configuration.resolve(before, after, roots)`:

- **before:** the priority finder to search for new modules; here it searches in the `mods` directory.
- **after:** a fallback finder if a module was not found in higher-priority places or in the parent configuration; here it is an empty finder.
- **roots:** names of the root modules to resolve; here only `demo.plugin`.

If `demo.plugin` declares `requires demo.api;`, the resolver also brings `demo.api` into the configuration (assuming it is not already in the parent configuration and is found in the finder). Modules already resolved in the **parent configuration** can satisfy matching dependencies and do not need to be redefined in the child layer.

**Specify roots by module name, not package name or JAR name.** `Set.of("demo.plugin")` indicates the root module; the resolver follows dependencies automatically. If a root cannot be found or a required dependency cannot be satisfied, resolution can fail with `java.lang.module.ResolutionException` or `FindException` depending on the cause.

### 2.3. ModuleLayer: Defining the New Layer

After obtaining the `Configuration`:

```java
ModuleLayer child = parent.defineModulesWithOneLoader(
        config,
        ClassLoader.getSystemClassLoader());
```

This is an **instance method** on `ModuleLayer`. It creates a child layer with **one parent layer**, which is `parent`. An important condition is that `config` must be resolved against the configuration of the corresponding parent layer; you cannot resolve a configuration from a different parent graph and combine them arbitrarily.

`ClassLoader.getSystemClassLoader()` is used in the example as the `parentLoader` of the new loader. In a real application, choose the parent loader based on the host architecture, shared API versions, and module layer constraints. Modules in the child layer still have linking/delegation mechanisms to modules in parent layers per the JPMS graph; do not infer that passing the system loader automatically makes every package on the classpath or parent layer readable by child modules.

After creation, use:

```java
ClassLoader loader = child.findLoader("demo.plugin");
Module module = child.findModule("demo.plugin").orElseThrow();
```

`child.findLoader(...)` returns the class loader associated with that module. With `defineModulesWithOneLoader`, modules **newly defined in the same child layer** return the same loader. `child.findModule(...)` searches the layer and its parent layers; when you need to verify that a module actually belongs to the new layer, inspect `child.modules()`.

## 3. Complete Java 17+ Example: Two Named Modules in One Child Layer

The example consists of **two separately compiled named modules** and a launcher program running on the classpath. Module `demo.plugin` uses class `Message` from module `demo.api`. The launcher creates the child layer itself, gets each module's class loader, and invokes plugin code via reflection.

### 3.1. Source Structure

Create the directory tree under your working directory:

```text
src/
  demo.api/
    module-info.java
    example/
      api/
        Message.java
  demo.plugin/
    module-info.java
    example/
      plugin/
        Greeter.java
  LayerDemo.java
```

The directory names directly under `src` must match the module names so `javac --module-source-path src` recognizes the modular sources properly.

**File `src/demo.api/module-info.java`:**

```java
module demo.api {
    exports example.api;
}
```

This module exports package `example.api` to other modules; classes inside that package can be used at runtime if module relationships permit.

**File `src/demo.api/example/api/Message.java`:**

```java
package example.api;

public final class Message {
    private Message() {}

    public static String text() {
        return "hello";
    }
}
```

**File `src/demo.plugin/module-info.java`:**

```java
module demo.plugin {
    requires demo.api;
    exports example.plugin;
}
```

`requires demo.api` creates a controlled dependency on the API module. `exports example.plugin` lets the launcher outside the module invoke public classes/methods in this package using standard reflection.

**File `src/demo.plugin/example/plugin/Greeter.java`:**

```java
package example.plugin;

import example.api.Message;

public final class Greeter {
    public Greeter() {}

    public String greet() {
        return Message.text() + " from child layer";
    }
}
```

`Greeter` is an implementation belonging to `demo.plugin`. When loaded in the child layer, it calls a class belonging to module `demo.api`, which is resolved in the same layer.

### 3.2. Program Creating the Layer

**File `src/LayerDemo.java`:**

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class LayerDemo {
    public static void main(String[] args) throws Exception {
        ModuleLayer parent = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
        Configuration config = parent.configuration().resolve(
                finder, ModuleFinder.of(), Set.of("demo.plugin"));

        ModuleLayer child = parent.defineModulesWithOneLoader(
                config, ClassLoader.getSystemClassLoader());

        ClassLoader apiLoader = child.findLoader("demo.api");
        ClassLoader pluginLoader = child.findLoader("demo.plugin");
        Class<?> greeterType = pluginLoader.loadClass("example.plugin.Greeter");
        Object greeter = greeterType.getDeclaredConstructor().newInstance();

        System.out.println("modules: " + child.modules().size());
        System.out.println("same loader: " + (apiLoader == pluginLoader));
        System.out.println("boot is parent: " + child.parents().contains(parent));
        System.out.println("provider module: " + greeterType.getModule().getName());
        System.out.println("result: " + greeterType.getMethod("greet").invoke(greeter));
    }
}
```

This is a **standalone runnable** program when accompanied by the modules above. It uses reflection to access the child layer's class because the launcher on the classpath does not declare `requires demo.plugin` at compile time. The `ModuleLayer` API is built into the JDK and requires no external libraries.

### 3.3. Compiling and Running

Run the following commands from the **parent directory containing `src`**, with JDK 17+:

```bash
javac --release 17 --module-source-path src -d mods --module demo.api,demo.plugin
javac --release 17 -d out src/LayerDemo.java
java -cp out LayerDemo
```

The first command places classes and module descriptors into `mods/demo.api` and `mods/demo.plugin`. The second compiles the launcher into `out`. The final command runs the launcher on the classpath; it explicitly reads the modules from `mods` and creates the new layer.

**Output** verified with `javac --release 17` and `java` on the JDK:

```text
modules: 2
same loader: true
boot is parent: true
provider module: demo.plugin
result: hello from child layer
```

Output explanation:

1. `modules: 2`: when root `demo.plugin` is resolved, `demo.api` is also brought into the child configuration due to the `requires` relationship. The new layer contains exactly two new modules.
2. `same loader: true`: `child.findLoader("demo.api")` and `child.findLoader("demo.plugin")` are the **same class loader instance**, as promised by `defineModulesWithOneLoader`.
3. `boot is parent: true`: `child.parents()` contains `ModuleLayer.boot()`, meaning the new layer has a parent relationship with the boot layer.
4. `provider module: demo.plugin`: `Greeter` belongs to a named module defined in the child layer, not an unnamed class loaded from the classpath.
5. `result: hello from child layer`: the public constructor and method run successfully; module `demo.plugin` reads the API it declared with `requires`.

**Why not use `Class.forName("example.plugin.Greeter")` with the default overload?** That overload uses the loader associated with the calling code (which for this launcher is the host classpath loader), which does not automatically know about classes in the newly created child layer. You must explicitly obtain `child.findLoader("demo.plugin")` and use `loadClass` or the appropriate `Class.forName(name, initialize, loader)`.

## 4. What Is Actually Shared When Using “One Loader”?

`defineModulesWithOneLoader` means **the modules of the new layer share one defining class loader created by the JVM**. It does **not** mean all modules become a single module or bypass encapsulation checks.

| Property | When Using One Loader in a Child Layer |
| --- | --- |
| Class loader for `demo.api` and `demo.plugin` | Same instance |
| Module identity | Still two distinct modules |
| `requires`, `exports`, `opens` | Still enforced by JPMS |
| Parent module layer | Remains a separate layer |
| Class loader passed as `parentLoader` | Is the parent loader of the new loader, not the new loader itself |
| Loadability via default host classpath | Does not happen automatically unless the host references the new loader/layer |
| Isolation between two modules with the same loader | Less than in the many-loaders model; module access boundaries still remain |
| Module/class loader lifecycle | Affected by references to layers, modules, classes, instances, and threads |

An important constraint: **two modules defined in the same class loader cannot contain the same package**. For example, if both `demo.api` and `demo.plugin` define package `example.shared` in the same layer, creating a one-loader layer can fail with `LayerInstantiationException` due to package conflict. `Configuration.resolve` and layer instantiation are not the same step; succeeding at resolution does not guarantee all class-loader/package constraints are satisfied.

If you need to load plugins whose dependencies have overlapping packages at different versions, **one loader for all plugins** is usually not the right approach. You can design **one child layer per plugin group** (each group with its own loader) or use `defineModulesWithManyLoaders` when configuration permits. However, do not choose many loaders merely to “make errors go away”: Java types shared across boundaries still require a consistent API and class-identity strategy.

## 5. Comparing Module Layer Definition APIs

| API | Characteristics | When to Consider |
| --- | --- | --- |
| `parent.defineModulesWithOneLoader(cf, parentLoader)` | Instance method; returns `ModuleLayer`; new modules share one loader | One child layer under one parent, wanting a module group to share a loader |
| `parent.defineModulesWithManyLoaders(cf, parentLoader)` | Instance method; each new module is bound to its own loader | Wanting separate loaders for modules in the same configuration |
| `parent.defineModules(cf, nameToLoader)` | Explicitly specifies module name → loader mapping | Custom loader architectures; requires consistent design and control |
| `ModuleLayer.defineModulesWithOneLoader(cf, parents, parentLoader)` | Static method; accepts a list of parent layers and returns `ModuleLayer.Controller` | Multiple parent layers or needing a controller for controlled adjustments |

For the case of a single parent without needing a controller, the **instance method** shown in the example is the simplest and clearest choice.

If the static version is needed:

```java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithOneLoader(
                config,
                java.util.List.of(parent),
                ClassLoader.getSystemClassLoader());

ModuleLayer child = controller.layer();
```

This is an **illustrative API snippet**, assuming `config` was resolved against the corresponding list of parent configurations, and `parent` is the matching parent layer. `Controller` has capabilities to adjust certain reads/exports/opens relationships for modules in the new layer within API limits; having a controller does not mean you can arbitrarily disable every JPMS restriction or replace compatibility checks.

In a multi-parent layer setup, you cannot arbitrarily replace `List.of(parent)` with a list that does not match the resolved configuration. The relationship between `Configuration.parents()` and the actual parent layers must match in the exact order per the contract.

## 6. Common Design Issues

### 6.1. Package Exports/Opens and Reflection

The `Greeter` example above has a `public class`, `public constructor`, and `public method`. If module `demo.plugin` **does not export** package `example.plugin`, a launcher in the unnamed module may be able to load/see the class, yet cannot invoke public members via ordinary reflection from outside the module. In that case, `IllegalAccessException` can occur. For deep reflection on non-public members, an appropriate `opens` directive may be needed; `exports` does not automatically grant deep reflection rights.

**Do not confuse “same class loader” with “every package is open”.** `requires` determines module readability, `exports` determines access to public types/members by package, and `opens` primarily serves reflective access. Exact rules depend on the relationship between caller and target module.

### 6.2. Where Should API/SPI Live?

If both host and plugin need an interface such as `com.acme.spi.Plugin`, establish **one API/SPI copy with a shared runtime identity**. Typically the host provides the API in a parent layer, and child modules declare `requires` on that API module. Then plugin and host reference the exact same `Class<?>` for the interface, avoiding duplicate definitions on both sides.

This article's example placed `demo.api` in the child layer to illustrate a dependency between two new modules; in a real plugin system, if the host needs to cast providers directly to an interface, the shared API must usually already be visible to the host (in a parent layer or a compatible arrangement). Placing the API in the child layer does not automatically make a host on the classpath aware of that type at compile time.

When using `ServiceLoader.load(layer, serviceType)`, ensure the service type used by the consumer has the right identity, the provider module declares `provides ... with ...`, and the consumer/module is permitted to use the service under JPMS rules. `ServiceLoader` relies on the layer and actual provider configuration; it does not fabricate missing `requires`/`exports`.

### 6.3. Do Not Use Classpath Instead of Module Resolution

A common mistake is building a plugin JAR, adding it only to `-cp`, and expecting `ModuleFinder.of(Path)` or `Configuration.resolve` to automatically locate it as a named module. You must place valid artifacts in the path supplied to the finder; the JAR must be a modular or automatic module under JPMS rules. Conversely, adding a JAR to `--module-path` at startup does not by itself verify that the module was resolved into the child layer you intend to create.

There is no “shortcut” allowing `defineModulesWithOneLoader` to turn an arbitrary file into a valid module. Module discovery, descriptor parsing, and resolution must be carried out properly.

### 6.4. Missing Dependencies, Split Packages, Versions

Errors can surface at different stages:

| Stage | Example Issue | How to Handle |
| --- | --- | --- |
| Find modules | Wrong path, unreadable artifact, corrupt descriptor | Check build output, module name, `ModuleFinder`, and `FindException` |
| Resolve configuration | Root not found, unsatisfied `requires`, conflicting graph | Check `Configuration.resolve` and `ResolutionException` |
| Define layer | Invalid package/class loader constraint for one-loader | Check `LayerInstantiationException` and package layout |
| Load class | Calling with host loader, wrong class name, missing class | Use `child.findLoader(moduleName)`, verify binary name |
| Reflective access | Module does not `exports`/`opens` as required by the call | Fix module descriptor per contract; do not rely solely on `setAccessible(true)` |
| Instantiate/invoke | Plugin constructor or method throws an exception | Inspect cause and exception chain, verify environment |
| Service discovery | Wrong `provides`/service type or loader/layer | Check module metadata, SPI identity, and `ServiceLoader` |

JPMS **does not automatically solve plugin semantic versioning** merely by putting a version in the JAR filename. If the host enforces a compatibility policy, check the API version, Java baseline, and dependency ranges separately before admitting the artifact at runtime. `Configuration.resolve` primarily resolves the module graph, not dependency version ranges like Maven/Gradle.

### 6.5. A New Layer Is Not Automatically “Installed” into the Boot Layer

`ModuleLayer.boot()` does not change after creating a child layer. Modules in the child layer do not by default become part of the startup module graph or automatically become visible to all existing class loaders.

The host should hold an explicit reference to the `ModuleLayer` and use `findModule`/`findLoader`/`ServiceLoader.load(layer, ...)` at integration points. Do not arbitrarily mutate global state or the classpath to “trick” running classes into thinking a plugin is already in the boot layer.

### 6.6. ModuleLayer Is Not a Security Sandbox

Layers and class loaders provide **module boundaries, namespaces, and lifecycle organization**. They do not by default prohibit plugins from reading files, making network connections, or calling privileged APIs that the host permits. When executing untrusted code, separate security boundaries are needed—such as processes, OS permissions, containers, IPC, and authorization policies. Do not treat `defineModulesWithOneLoader` as proof that a plugin is strictly isolated.

## 7. Lifecycle, Reload, and Structural Choices

Once modules and classes have been defined in a layer, you cannot simply swap a `Configuration` and force existing classes to switch to another loader. A plugin update typically involves:

1. Preparing and validating the new artifact.
2. Creating a new `ModuleFinder` and configuration from the appropriate parent.
3. Creating a **new child layer** using the chosen method.
4. Initializing/verifying the new implementation, then switching the host's registry or routing to it under a clear strategy.
5. Removing listeners, tasks, caches, thread context class loaders, service instances, and references to the old layer/classes/loader once no longer in use.

`ModuleLayer` is not a standard `AutoCloseable` and has no “immediate module unload” operation. Whether the old loader/layer can be garbage collected depends on whether strong references remain to classes, instances, loaders, threads, or caches. Repeatedly creating new layers without cleaning up registrations can cause memory/metaspace growth.

With multiple independent plugins, one child layer **containing all modules of all plugins** and a shared loader can reduce the number of loaders, but is unsuitable if plugins have package conflicts or need separate lifecycles. Choosing layer-per-plugin, group-per-layer, or many-loaders depends on the `requires` graph, the number of dependency versions that must coexist, and API boundaries.

## 8. Design and Testing Checklist

- **Artifacts:** are all roots/dependencies to be resolved valid named modules on the right module path, with `module-info.class` when using explicit modules?
- **Configuration:** does `parent.configuration()` match the parent layer, and does `resolve` specify the right roots and include transitive dependencies?
- **Layer:** does `defineModulesWithOneLoader` succeed; are `child.parents()` and `child.modules()` as expected?
- **Class loaders:** does `findLoader` return the same loader for **new modules** in the child layer; does the host use the right loader when loading classes?
- **Type identity:** are shared APIs/SPIs not erroneously redefined in the child layer/plugin?
- **Access control:** are `requires`, `exports`, and `opens` sufficient for imports, reflection, callbacks, and service providers?
- **Package constraints:** do modules assigned to the same loader avoid defining overlapping packages?
- **Service discovery:** do `provides`/`uses` and `ServiceLoader` match the intended service type and layer?
- **Failure modes:** are errors logged clearly at the find, resolve, define, load, reflect, and initialize steps?
- **Lifecycle:** does the application have a strategy for creating a new layer on upgrade and releasing references to the old layer?

**Technical conclusion:** to create a child layer with `defineModulesWithOneLoader`, **find modules (`ModuleFinder`) → resolve the configuration (`Configuration.resolve`) → define the layer (`parent.defineModulesWithOneLoader`) → obtain loaders/modules from the new layer (`findLoader`/`findModule`)**. A shared loader only dictates the class-definition strategy for new modules; JPMS still enforces dependency graphs, exports/opens, and required boundaries.