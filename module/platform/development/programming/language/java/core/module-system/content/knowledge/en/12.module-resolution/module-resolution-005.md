# Parent Configuration During Resolution

In the Java Platform Module System (JPMS), an application can resolve modules in multiple stages. For example, a host starts up first with a set of foundational modules and API modules, and plugins are loaded afterward. When resolving a plugin, Java needs to know which modules were already resolved in the earlier stage so it can reuse dependencies instead of finding and redefining them again.

That is the role of the **parent configuration** during resolution. A child `Configuration` retains references to parent configurations, uses modules already present in the parent to satisfy dependencies of new modules, and resolves any additional modules found from the supplied `ModuleFinder` instances.

Parent configurations are the foundation for JPMS's layered model: shared modules live in the parent configuration; additional modules such as plugins are resolved in child configurations; and then a `ModuleLayer` is created to define the new modules at runtime.

## 1. What Is a Configuration?

`java.lang.module.Configuration` represents the result of the module resolution process. It contains the modules selected by resolution, the dependencies between them, and one or more parent configurations.

A configuration is metadata for the resolved module graph. It is not yet the running module objects in the JVM. To define modules into the runtime, the application creates a `ModuleLayer` from that configuration.

You can picture it as:

```text
ModuleFinder(s)
     |
     | discover modules
     v
Configuration.resolve(...)
     |
     | produce resolved module graph
     v
Configuration
     |
     | ModuleLayer.defineModules...
     v
ModuleLayer and runtime Modules
```

The three concepts have distinct responsibilities:

- `ModuleFinder` locates modules from the runtime image, module directories, or JARs.
- `Configuration` determines which modules are needed and how dependencies are satisfied.
- `ModuleLayer` defines the resolved modules in the runtime and associates them with class loaders.

Simply finding a JAR does not mean the module has been resolved. It must be selected by resolution, either directly as a root or indirectly as a dependency.

## 2. What Is a Parent Configuration?

A configuration can have one or more parent configurations. A parent holds a previously resolved module graph. When resolving a new configuration, the resolver can use modules in the parent to satisfy dependencies of the new modules.

Example of a plugin application:

```text
Boot Configuration
       |
       v
Host Configuration
       |
       v
Plugin Configuration
```

The host configuration may contain shared API modules. The plugin configuration contains plugin modules loaded later. If a plugin declares `requires com.example.host.api;`, the resolver can use the API module already present in the parent configuration.

This avoids forcing each plugin to bundle its own copy of the API module and avoids redefining the same module in multiple layers.

A child configuration is not a full copy of the parent configuration. It contains the modules resolved in itself and references to its parent configuration(s). You can inspect the parent structure via:

```java
Configuration configuration = ModuleLayer.boot().configuration();

for (Configuration parent : configuration.parents()) {
    System.out.println(parent);
}
```

For a child configuration, `parents()` reveals its direct parent configurations. This relationship is the basis for resolution to look up previously resolved modules.

## 3. When Is a Parent Configuration Used?

Parent configurations are especially useful in staged resolution scenarios:

- A host application starts first, and plugins are loaded later.
- A runtime layer contains shared APIs and services.
- Multiple module groups need to reuse foundational dependencies that have already been defined.
- An application creates multiple independent plugin layers that all use the same API module.
- A tool needs to resolve a new group of modules based on an existing module graph.

For example, the host has the module:

```java
module com.example.host.api {
    exports com.example.host.api;
}
```

The plugin declares:

```java
module com.example.plugin.alpha {
    requires com.example.host.api;
}
```

When resolving the plugin, the parent configuration supplies the `com.example.host.api` module. The plugin does not need to package a copy of the API module in the plugin directory. The API module is referenced from the parent configuration and can be used to satisfy the dependency.

## 4. Configuration's resolve API

An existing configuration can be used as a parent to resolve additional modules. The commonly used instance method is:

```java
Configuration childConfiguration =
        parentConfiguration.resolve(
                beforeFinder,
                afterFinder,
                roots
        );
```

The parameters are:

- `beforeFinder`: locates modules from this source before searching parent configurations.
- `afterFinder`: locates modules from this source after searching parent configurations.
- `roots`: names of the root modules to resolve for the new configuration.

The instance method uses the current configuration as the parent. The result is a new configuration containing the modules resolved in the current stage along with a link to the parent configuration.

In addition to the instance method, there is a static method that accepts a list of parent configurations:

```java
Configuration childConfiguration =
        Configuration.resolve(
                beforeFinder,
                List.of(parentConfiguration),
                afterFinder,
                roots
        );
```

The static form is useful when specifying multiple parent configurations or when wanting explicit control over the parent set. For a single parent, the instance method is usually easier to read.

### 4.1. Why Are There beforeFinder and afterFinder?

Resolution can look up modules from three places in order:

1. The finder passed in the `beforeFinder` position.
2. The parent configurations.
3. The finder passed in the `afterFinder` position.

This order matters when the same module name may appear in multiple sources. A finder before the parent has discovery precedence first; a finder after the parent is only considered after the resolver has checked the parent configurations.

In a typical plugin setup, you usually want to reuse modules already in the parent. You can pass the plugin finder in either the `beforeFinder` or `afterFinder` position depending on your module selection policy. A common example:

```java
Configuration pluginConfiguration =
        hostConfiguration.resolve(
                pluginFinder,
                ModuleFinder.of(),
                Set.of("com.example.plugin.alpha")
        );
```

Here:

- `pluginFinder` locates plugin modules.
- `ModuleFinder.of()` is an empty finder for the post-parent source.
- `hostConfiguration` is the parent configuration.
- `com.example.plugin.alpha` is the root module.

With this approach, the plugin finder is checked before the parent configuration. If the system needs to prioritize modules already in the parent when names collide, you should design the finder sources and search order accordingly, while avoiding providing two versions with the same name within the same configuration.

## 5. How Does Resolution Use Modules in the Parent?

Suppose the parent configuration already contains:

```text
com.example.host.api
java.base
java.logging
```

The plugin finder contains:

```text
com.example.plugin.alpha
com.example.plugin.beta
```

Plugin alpha has the descriptor:

```java
module com.example.plugin.alpha {
    requires com.example.host.api;
    requires java.logging;
}
```

When the resolver processes the root `com.example.plugin.alpha`, it checks the dependencies:

- `com.example.host.api` is already in the parent configuration, so it can be used to satisfy the dependency.
- `java.logging`, if already in the parent configuration, can also be used from the parent.
- Dependencies not yet in the parent will continue to be looked up in the finders according to resolution order.

The resulting child configuration contains the new plugin module and any newly resolved dependencies. Modules already in the parent remain part of the parent configuration and are not duplicated into separate modules simply because the child needs to read them.

If a dependency is neither in the parent nor found by any finder, resolution fails. This is a module graph error, not a source code import error.

## 6. Complete Example: Resolving a Plugin from a Host Configuration

Suppose the host API has been compiled into an exploded module in the `mods` directory, while the plugin JAR resides in `plugins`.

Structure:

```text
application/
├── mods/
│   └── com.example.host.api/
│       ├── module-info.class
│       └── com/example/host/api/HostService.class
└── plugins/
    └── com.example.plugin.alpha.jar
```

Host API module:

```java
module com.example.host.api {
    exports com.example.host.api;
}
```

Plugin module:

```java
module com.example.plugin.alpha {
    requires com.example.host.api;
}
```

### Step 1: Create the parent configuration

You can start from the boot configuration and resolve the host API:

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleFinder hostFinder =
        ModuleFinder.of(Path.of("mods"));

Configuration hostConfiguration =
        ModuleLayer.boot()
                .configuration()
                .resolve(
                        hostFinder,
                        ModuleFinder.of(),
                        Set.of("com.example.host.api")
                );
```

The host configuration uses the boot configuration as its parent. The root is the host API module; dependencies of the host API are resolved from the parent or finder.

### Step 2: Discover the plugin

```java
ModuleFinder pluginFinder =
        ModuleFinder.of(Path.of("plugins"));
```

This finder locates modules in the plugin directory. It can recognize modular JARs and automatic modules according to module path rules.

### Step 3: Resolve the plugin based on the parent configuration

```java
Configuration pluginConfiguration =
        hostConfiguration.resolve(
                pluginFinder,
                ModuleFinder.of(),
                Set.of("com.example.plugin.alpha")
        );
```

In this step, `hostConfiguration` is the parent. When the plugin declares `requires com.example.host.api;`, the resolver can satisfy the dependency from the parent configuration.

### Step 4: Inspect the result

```java
pluginConfiguration.modules().stream()
        .map(resolved -> resolved.name())
        .sorted()
        .forEach(System.out::println);
```

`modules()` returns the modules resolved directly in the current configuration. Modules belonging to the parent are not repeated as new modules in this set. To inspect parents, use `parents()`.

## 7. How Are Parent Configuration and Parent ModuleLayer Related?

Configuration is the result of resolution; ModuleLayer is the runtime structure defined from a configuration.

When defining a child layer, the parent layer must correspond to the parent configuration used for resolution. The usual way is to call the method on the parent layer:

```java
ModuleLayer hostLayer =
        ModuleLayer.boot()
                .defineModulesWithOneLoader(
                        hostConfiguration,
                        ClassLoader.getSystemClassLoader()
                );

ModuleLayer pluginLayer =
        hostLayer.defineModulesWithOneLoader(
                pluginConfiguration,
                ClassLoader.getSystemClassLoader()
        );
```

Here:

- `hostLayer` is created from the host configuration, with the boot layer as its parent.
- `pluginLayer` is created from the plugin configuration, with the host layer as its parent.
- The plugin layer can reference the API module already defined in the host layer once dependencies have been resolved properly.

You should not resolve a plugin from one parent configuration and then define it under an unrelated layer. The parent configuration and parent layer must match so the runtime module graph remains consistent.

## 8. Parent Configuration Does Not Automatically Grant Readability

This is an important point to remember when debugging.

Suppose module `com.example.plugin.alpha` is in the child configuration and `com.example.host.api` is in the parent configuration. The parent relationship does not automatically make the plugin read the host API.

The plugin still needs:

```java
requires com.example.host.api;
```

In addition, the host API module must export the package containing the types the plugin wants to use:

```java
exports com.example.host.api;
```

The conditions play distinct roles:

- The parent configuration helps the resolver find the previously resolved API module.
- `requires` establishes the readability relationship from the plugin to the API.
- `exports` allows the plugin to access the API package under JPMS rules.

Readability does not equate to access to every package. One module can read another module and still be unable to access a package that has not been exported or opened for reflection.

## 9. Multiple Parent Configurations

JPMS supports configurations with multiple parents. This is useful when a new layer needs to reuse modules from multiple independently resolved layer branches.

Example structure:

```text
             Boot Configuration
               /           \
              v             v
       Data Configuration  UI Configuration
               \           /
                v         v
             Plugin Configuration
```

You can use the static overload of `Configuration.resolve`:

```java
Configuration pluginConfiguration =
        Configuration.resolve(
                pluginFinder,
                List.of(dataConfiguration, uiConfiguration),
                ModuleFinder.of(),
                Set.of("com.example.plugin.dashboard")
        );
```

The resolver can use modules in the parent configurations to satisfy the plugin's dependencies.

However, multiple parents make the structure more complex. You must ensure there are no module name conflicts and that the parent configurations can participate together in a valid configuration graph. If the same module name appears in multiple parents with incompatible contents or identities, resolution may fail or the layer structure may not meet the intended design.

## 10. resolve and resolveAndBind with a Parent

Configuration has two common groups of resolution methods:

- `resolve(...)` handles roots and dependencies declared with `requires`.
- `resolveAndBind(...)` additionally performs service binding based on `uses` and `provides`.

If a plugin uses ServiceLoader and you want provider modules to be discovered automatically from observable sources, you can use:

```java
Configuration pluginConfiguration =
        hostConfiguration.resolveAndBind(
                pluginFinder,
                ModuleFinder.of(),
                Set.of("com.example.plugin.host")
        );
```

Service binding can add provider modules and their dependencies to the child configuration. Modules already present in the parent configuration can still be used to satisfy dependencies.

Distinguish between a provider being found and a provider being instantiated. Resolution adds the provider module to the configuration; ModuleLayer defines the module; ServiceLoader is what locates and instantiates providers within the chosen loader or layer scope.

## 11. How to Inspect Parent Configurations and the Module Graph

Several APIs help inspect the configuration structure:

| API | Meaning |
|---|---|
| `Configuration.parents()` | Direct parent configurations |
| `Configuration.modules()` | Modules resolved in the current configuration |
| `Configuration.findModule(name)` | Finds a module in the configuration graph |
| `Configuration.resolve(...)` | Resolves roots and dependencies |
| `Configuration.resolveAndBind(...)` | Resolution with service binding |
| `ModuleLayer.configuration()` | Configuration used to define the layer |
| `ModuleLayer.parents()` | Runtime parent layers |
| `ModuleLayer.modules()` | Modules defined directly in the layer |
| `Module.canRead(other)` | Checks readability between two runtime modules |

Example inspecting parents and current modules:

```java
System.out.println("Child modules:");

pluginConfiguration.modules().stream()
        .map(resolved -> resolved.name())
        .sorted()
        .forEach(System.out::println);

System.out.println("Parent configurations:");

for (Configuration parent : pluginConfiguration.parents()) {
    parent.modules().stream()
            .map(resolved -> resolved.name())
            .sorted()
            .forEach(System.out::println);
}
```

Note that `Configuration.findModule(name)` can search in the current configuration and its parent configurations. Meanwhile, `modules()` only lists modules resolved directly in that configuration.

To verify readability after layers have been defined, obtain both `Module` objects and call `canRead`:

```java
boolean readable = pluginModule.canRead(hostApiModule);
System.out.println(readable);
```

This is an actual runtime check. If you are only inspecting the configuration, check the dependencies in the descriptors and the resolution result.

## 12. Common Errors When Using Parent Configurations

**A dependency is in the directory, yet resolution still reports a missing module.**

The finder may not be pointing to the right directory, or the module may not have been resolved into the parent configuration. Check the module path, module name, and root set.

**Assuming modules in the parent are automatically read.**

The parent configuration allows the module to be found to satisfy dependencies, but the plugin still needs `requires` to obtain readability.

**Using the wrong order for beforeFinder and afterFinder.**

The finder before the parent is searched with priority first; the finder after the parent is checked afterward. If modules with the same name exist in multiple sources, this order can change which module is selected. Avoid supplying unnecessary duplicates with the same name.

**Resolving the child from the boot configuration instead of the host configuration.**

If the API module was only resolved in the host configuration, using the boot configuration as the parent for the plugin will not provide that module. Resolve the child from the proper parent configuration.

**Defining a layer with a parent that does not match the configuration.**

A configuration resolved from a parent graph should be defined under the corresponding layer. Mismatching them can lead to an invalid runtime structure.

**Assuming a parent layer grants access to internal packages.**

Readability and exports are still enforced. If deep reflection is needed, separate opens are required; a parent relationship does not bypass encapsulation.

**Confusing configuration with layer.**

A configuration describes the resolved module graph. A layer contains the module objects defined in the runtime and associated with class loaders. A configuration that has not been used to define a layer has not created new runtime modules yet.

## 13. Design Principles for Parent Configurations

When designing a multi-stage module resolution system:

1. **Place shared APIs in the parent:** stable interfaces and contract types should be resolved before plugins.
2. **Keep dependencies explicit:** plugins declare `requires` on the API modules they actually use.
3. **Use the right parent configuration:** child resolution must be based on the configuration corresponding to the intended parent layer.
4. **Choose finders deliberately:** decide which module sources take precedence before the parent and which are searched afterward.
5. **Avoid duplicate module names:** there should be only one matching module for each name in the configuration graph.
6. **Distinguish resolution and definition:** resolve first, then define the layer; do not treat a finder as a loader.
7. **Check exports:** a dependency may resolve, yet packages still must be exported for source code access.
8. **Use resolveAndBind when services are needed:** enable service binding only when the provider model requires it.
9. **Inspect the configuration before defining the layer:** check roots, resolved modules, and parents for easier diagnosis.
10. **Keep the layer graph simple:** introduce multiple parents only when there is a genuine requirement to reuse modules.

## Conclusion

A parent configuration supplies a previously resolved module graph for the resolver to use when creating a new configuration. When a child module declares `requires` on a module already in the parent, the dependency can be satisfied from the parent instead of locating and resolving a new copy.

`Configuration.resolve` and `resolveAndBind` take finders, parent configurations, and root modules to build the graph. The search order across `beforeFinder`, parent configurations, and `afterFinder` matters when multiple sources contain modules with the same name. After resolution, the child configuration is used to define the corresponding child layer.

A parent configuration does not automatically grant readability or package access. The plugin still needs `requires`, the owning module needs `exports`, and Java's access modifier rules continue to apply. Understanding the distinction between discovery, resolution, parent configurations, and ModuleLayer helps build plugin systems with clear dependencies, shared module reuse, and easier diagnostics.
