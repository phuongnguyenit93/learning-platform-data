# Configuration for Creating a New Layer in Java ModuleLayer (JPMS)

## 1. Objectives

In the Java Platform Module System (JPMS, since Java 9), a program can create additional `ModuleLayer` instances at runtime to load modules outside the set resolved at startup. A common scenario is that the main application runs stably in the boot layer, while plugins are discovered in a separate directory and loaded into a child layer when needed.

To do that, you need to distinguish two concepts:

- `Configuration` (`java.lang.module.Configuration`) is **the graph of resolved modules**: which modules are selected, which module requires which module, and what the parent configurations are. A Configuration does not yet create runtime `Module` objects and does not yet load classes.
- `ModuleLayer` (`java.lang.ModuleLayer`) is **the runtime module environment** created from a `Configuration`, binding the resolved modules to their corresponding `ClassLoader` instances and to parent layers.

Basic flow:

```text
Modular JARs in plugins/
            |
            v
    ModuleFinder.of(...)
            |
            v
ModuleLayer.boot().configuration()
    .resolve(finder, after, roots)
            |
            v
       Configuration
            |
            v
bootLayer.defineModulesWithOneLoader(config, parentLoader)
            |
            v
       New ModuleLayer
            |
            v
  ServiceLoader / findLoader / findModule
```

This is how a new layer is constructed; a `Configuration` does not automatically become a layer merely by calling `resolve`.

## 2. Related Components

| Component | Role |
| --- | --- |
| `ModuleFinder` | Finds module descriptors in a directory or modular JARs, e.g. `plugins/`. |
| `ModuleDescriptor` | Describes `requires`, `exports`, `uses`, `provides`, and module attributes. |
| `Configuration` | Result of module resolution; holds `ResolvedModule` entries and read relationships at the configuration level. |
| `ModuleLayer.boot()` | The default layer after the JVM starts; commonly used as a parent layer. |
| `ModuleLayer.defineModulesWithOneLoader(...)` | Defines the new configuration's modules in a child layer, sharing one loader for the modules in that layer. |
| `ModuleLayer.findModule(...)` | Looks up a module by name in the current layer and its parent layers. |
| `ModuleLayer.findLoader(...)` | Gets the loader assigned to a module located in this layer. |
| `ServiceLoader.load(layer, serviceType)` | Finds service implementations in the specified layer and appropriate parent layers. |

A new `Configuration` can reference modules that already exist in a parent configuration. Those parent modules are not copied into the child layer.

## 3. Creating a Configuration from ModuleFinder

Suppose the host application has started and `plugins/` contains `com.example.plugin.jar`. The module `com.example.plugin` will be loaded into a new layer.

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class CreateConfiguration {
    public static void main(String[] args) {
        ModuleLayer parentLayer = ModuleLayer.boot();
        Configuration parentConfig = parentLayer.configuration();

        ModuleFinder before = ModuleFinder.of(Path.of("plugins"));
        ModuleFinder after = ModuleFinder.of(); // Do not search for more modules beyond the chosen source

        Configuration childConfig = parentConfig.resolve(
                before,
                after,
                Set.of("com.example.plugin")
        );

        childConfig.modules().forEach(resolved ->
                System.out.println(resolved.name())
        );
    }
}
```

Meaning of the `resolve(before, after, roots)` parameters:

1. `before` is the module source searched first before consulting parent configurations. In the example, this is the modules in `plugins/`.
2. `after` is the additional source used to find modules not yet found in `before` or parent configurations. `ModuleFinder.of()` creates an empty finder.
3. `roots` is the set of root module names to resolve. The resolver also brings required `requires` dependencies into the graph.

A `Configuration` is immutable once created. If you need to select a different set of modules, create another configuration and define a new layer from it.

When a plugin depends on `com.example.api` already present in the boot layer, the resolver can use the module from the parent configuration. The plugin does not need to bundle a duplicate copy of the API.

## 4. Complete Example: Loading a Plugin via SPI

The following example consists of three modules:

- `com.example.api` defines the service interface; present in the boot layer.
- `com.example.host` is the main application; present in the boot layer.
- `com.example.plugin` implements the service; placed into a child layer at runtime.

Source structure:

```text
src/
  api/
    module-info.java
    com/example/api/GreetingProvider.java
  host/
    module-info.java
    com/example/host/Main.java
  plugin/
    module-info.java
    com/example/plugin/HelloProvider.java
mods/       # API and host at runtime
plugins/    # Plugin JAR discovered dynamically
```

### 4.1. API Module

`src/api/module-info.java`:

```java
module com.example.api {
    exports com.example.api;
}
```

`src/api/com/example/api/GreetingProvider.java`:

```java
package com.example.api;

public interface GreetingProvider {
    String greet(String name);
}
```

### 4.2. Plugin Module

`src/plugin/module-info.java`:

```java
module com.example.plugin {
    requires com.example.api;

    provides com.example.api.GreetingProvider
            with com.example.plugin.HelloProvider;
}
```

`src/plugin/com/example/plugin/HelloProvider.java`:

```java
package com.example.plugin;

import com.example.api.GreetingProvider;

public class HelloProvider implements GreetingProvider {
    public HelloProvider() {}

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

The plugin provides the service using `provides ... with ...`. `exports com.example.plugin` is not required just for `ServiceLoader` to instantiate a validly declared provider.

### 4.3. Host Module and Layer Creation Point

`src/host/module-info.java`:

```java
module com.example.host {
    requires com.example.api;
    uses com.example.api.GreetingProvider;
}
```

`src/host/com/example/host/Main.java`:

```java
package com.example.host;

import com.example.api.GreetingProvider;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;

public class Main {
    public static void main(String[] args) {
        ModuleLayer boot = ModuleLayer.boot();

        // Step 1: discover modular JARs outside the host's module-path.
        ModuleFinder plugins = ModuleFinder.of(Path.of("plugins"));

        // Step 2: resolve the plugin module and its required dependencies.
        Configuration config = boot.configuration().resolve(
                plugins,
                ModuleFinder.of(),
                Set.of("com.example.plugin")
        );

        // Step 3: define the resolved modules in a child layer.
        ModuleLayer pluginLayer = boot.defineModulesWithOneLoader(
                config,
                ClassLoader.getSystemClassLoader()
        );

        // Step 4: obtain providers from the child layer via the shared API contract.
        ServiceLoader<GreetingProvider> providers =
                ServiceLoader.load(pluginLayer, GreetingProvider.class);

        for (GreetingProvider provider : providers) {
            System.out.println(provider.greet("Minh"));
        }

        // Observe the module loading result for diagnostics.
        pluginLayer.findModule("com.example.plugin")
                .ifPresent(module ->
                        System.out.println("Loaded: " + module.getName())
                );
    }
}
```

Expected output:

```text
Hello, Minh!
Loaded: com.example.plugin
```

The host application and the API must use the same `GreetingProvider` definition from the parent layer. If the host and plugin use two copies of the API class loaded in different loaders, type errors (`ClassCastException`) or failure to recognize the SPI properly may occur.

### 4.4. Compiling and Running

Create the directories `build/api`, `build/plugin`, `build/host`, `mods`, and `plugins` beforehand. With JDK 9 or later, from the example's root directory:

```bash
javac -d build/api \
  src/api/module-info.java \
  src/api/com/example/api/GreetingProvider.java

jar --create --file mods/com.example.api.jar -C build/api .

javac --module-path mods -d build/plugin \
  src/plugin/module-info.java \
  src/plugin/com/example/plugin/HelloProvider.java

jar --create --file plugins/com.example.plugin.jar -C build/plugin .

javac --module-path mods -d build/host \
  src/host/module-info.java \
  src/host/com/example/host/Main.java

jar --create --file mods/com.example.host.jar -C build/host .

java --module-path mods -m com.example.host/com.example.host.Main
```

The trailing `\` in the snippet above is for line continuation in a Unix shell. In PowerShell or CMD, you can enter each command on a single line. The key point is that `mods/` contains the host and API, while `plugins/` is read by the program at runtime; placing the plugin on the boot module path would alter the initial resolution structure.

## 5. Choosing How to Create a Layer from a Configuration

Once you have a configuration, JPMS offers several ways to map modules to class loaders:

### One Loader for the Layer

```java
ModuleLayer layer = ModuleLayer.boot()
        .defineModulesWithOneLoader(config, ClassLoader.getSystemClassLoader());
```

This is a concise option when the new group of modules can share a loader. The modules in the new layer are mapped to a single loader set up by the API, while the `parentLoader` argument specifies the parent loader used for delegation.

### A Separate Loader per Module

```java
ModuleLayer layer = ModuleLayer.boot()
        .defineModulesWithManyLoaders(config, ClassLoader.getSystemClassLoader());
```

This approach creates a more separated mapping among the layer's modules. Splitting loaders does not automatically turn a plugin into a security sandbox.

### Custom Loader Mapping

```java
// Template only; the mapping function must return a suitable loader for each module.
ModuleLayer layer = ModuleLayer.boot()
        .defineModules(config, moduleName -> chooseLoader(moduleName));
```

`defineModules` accepts a function mapping a module name to a `ClassLoader`. This is an advanced option when the application already manages loaders and package ownership explicitly.

With multiple parent layers, the static API group such as `ModuleLayer.defineModulesWithOneLoader(config, parentLayers, parentLoader)` returns a `ModuleLayer.Controller`; obtain the new layer with `controller.layer()`. The parent layers passed in must correspond to the parent configurations list of `config`.

## 6. How Do `resolve` and `resolveAndBind` Differ?

`resolve(...)` starts from the `roots` set and follows mandatory dependencies (`requires`). This is the straightforward choice when you already know the plugin module names to load.

`resolveAndBind(...)` also performs service binding: when resolved modules declare `uses`, the resolver can discover additional matching provider modules in the supplied module sources. This is useful for SPI-based extension systems where the host does not want to list every provider name in advance.

Example replacing the resolution step above:

```java
Configuration config = ModuleLayer.boot().configuration()
        .resolveAndBind(
                ModuleFinder.of(Path.of("plugins")),
                ModuleFinder.of(),
                Set.of("com.example.plugin")
        );
```

`resolveAndBind` does not replace declaring `uses` and `provides` properly in `module-info.java`; nor does it automatically scan every directory on the machine. The search scope depends on the `ModuleFinder` instances passed in.

When there is only one plugin already identified by name, `resolve` is sufficient for the example in Section 4.

## 7. Inspecting the Graph and Layer After Creation

```java
Configuration config = pluginLayer.configuration();

// Modules belonging to the child layer's own configuration.
config.modules().forEach(rm -> {
    System.out.println("Module: " + rm.name());
    rm.reads().forEach(dep ->
            System.out.println("  reads -> " + dep.name())
    );
});

// Runtime modules defined directly in the child layer.
pluginLayer.modules().forEach(m ->
        System.out.println("Runtime module: " + m.getName())
);

// Can find modules in this layer or in parent layers.
System.out.println(pluginLayer.findModule("com.example.api").isPresent());

// findLoader requires the module to belong to the queried layer itself.
ClassLoader pluginLoader = pluginLayer.findLoader("com.example.plugin");
System.out.println(pluginLoader);
```

Both `Configuration.modules()` and `ModuleLayer.modules()` reflect the direct modules of the target object; do not assume they contain all modules from parent layers. To inspect parent layers, use `pluginLayer.parents()`.

When you need to manually load a specific plugin class, you can get the loader via `findLoader` and use `Class.forName(className, true, loader)`. However, finding a class does not automatically grant access to packages that are not `exports` or `opens`. When you only need to invoke an extension point, SPI generally reduces dependence on internal plugin class names.

## 8. Common Errors and Troubleshooting

| Symptom | Common cause | How to address |
| --- | --- | --- |
| `FindException` | Root module or dependency not found; JAR is not the expected module. | Check the `Path` passed to `ModuleFinder`, the actual module name, and the JAR structure. |
| `ResolutionException` | Module graph has a conflict, e.g. overlapping packages or read constraints. | Check `requires`, duplicate packages, and transitively readable dependencies. |
| `LayerInstantiationException` | Cannot define the graph with the chosen class loader mapping, such as overlapping packages in the same loader. | Change the loader mapping strategy or adjust the module/package structure. |
| Provider not found via `ServiceLoader` | Missing `uses`/`provides`, provider not included in the graph, or calling `load` on the wrong layer. | Check descriptors, roots/`resolveAndBind`, and the layer passed to `ServiceLoader.load`. |
| `IllegalAccessException` / `InaccessibleObjectException` | Code outside the module attempts to access a non-`exports` package or reflective access without `opens`. | Design a public API and declare `exports`/`opens` appropriately; avoid granting unnecessary permissions. |
| `ClassCastException` / `ServiceConfigurationError` | Different class identity for the service interface or invalid provider. | Share the API from a parent layer, check constructors and `provides` declarations. |

A few points to remember:

- If a module already exists in the boot layer, calling `resolve` for a child layer does not mean the JVM will “reload” that module into the child layer. The module in the parent configuration continues to be used from the parent.
- Modules with the same name can belong to different layers, but the existence of layers does not allow bypassing module readability rules, package exports, or class loader identity.
- Creating a new layer does not automatically update an old layer or replace already-loaded classes. To swap plugin versions, you usually need to create a new configuration/layer and manage the lifecycle of references to the old version.
- A layer is a mechanism for organizing and linking modules, **not** a security sandbox for running untrusted code.

## 9. When Should You Use Configuration + ModuleLayer?

Consider it when an application needs to load a chosen set of modules at runtime, manage plugins from a directory independent of the boot module path, or create separate module spaces for different extension versions.

If all modules are known at packaging time and there is no need for dynamic loading, configuring the module path and letting the JVM build the boot layer is usually simpler.

Operational workflow to master:

1. Identify the parent layer and retrieve `parentLayer.configuration()`.
2. Create a `ModuleFinder` to locate new modules.
3. Call `resolve` or `resolveAndBind` with intentional roots.
4. Choose a class loader strategy and define the new `ModuleLayer`.
5. Access modules via SPI, `findModule`, or `findLoader`.
6. Inspect the graph and resolution errors when modules/dependencies are invalid.

## 10. Practice Exercises

1. Add a `com.example.plugin.fr` module also implementing `GreetingProvider`, and place its JAR in `plugins/`. Include both plugin modules in the roots set and observe that two providers are found.
2. Try removing `requires com.example.api` from the plugin and compiling to see the role of dependencies in the module descriptor.
3. Try removing `provides ... with ...` and compare the result of `ServiceLoader.load(pluginLayer, GreetingProvider.class)`.
4. Print the lists of `config.modules()`, `pluginLayer.modules()`, and `pluginLayer.parents()`, and explain which modules belong to the parent layer.
5. Switch `defineModulesWithOneLoader` to `defineModulesWithManyLoaders` and inspect the plugin's loader via `findLoader`.

**Takeaway:** `Configuration` decides **which modules are included and how they read each other**; `ModuleLayer` decides **how the resolved modules are realized at runtime and which class loaders they are bound to**.