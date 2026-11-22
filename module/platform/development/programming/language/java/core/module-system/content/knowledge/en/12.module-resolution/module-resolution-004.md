# Configuration.resolve and resolveAndBind

The Java Platform Module System (JPMS) does not just describe dependencies in `module-info.java`; it also needs to locate the actual modules and resolve all dependency relationships before creating a module layer. The two methods `Configuration.resolve(...)` and `Configuration.resolveAndBind(...)` perform that resolution step.

Both methods create a new `Configuration` object from root modules, observable modules found via `ModuleFinder`, and existing parent configurations. The key difference is that `resolveAndBind` additionally performs **service binding**: it locates providers of services used by modules in the configuration and adds those provider modules along with their required dependencies to the result.

These methods do not load classes or instantiate plugins by themselves. They produce a module configuration; the application then uses `ModuleLayer` to define and load those modules.

## 1. What Is a Configuration?

`Configuration` represents the result of resolving a set of modules. It contains the resolved module graph along with its relationships to parent configurations.

In a typical application, the baseline configuration can be obtained from the boot layer:

~~~java
Configuration bootConfiguration =
    ModuleLayer.boot().configuration();
~~~

The boot layer contains the foundational modules and those initialized for the current runtime. When an application needs to load plugins or an additional group of modules, it can create a child configuration based on the boot layer's configuration.

It is important to distinguish:

- **`ModuleFinder`**: locates and provides information about observable modules from a source.
- **`Configuration`**: the result of resolving roots and dependencies into a valid module graph.
- **`ModuleLayer`**: the runtime environment that defines modules from a configuration and associates them with class loaders.

Overall flow:

~~~text
ModuleFinder + root module names + parent Configuration
                         |
                         v
            Configuration.resolve(...)
                         |
                         v
              Resolved Configuration
                         |
                         v
          ModuleLayer.defineModules...
                         |
                         v
             Runtime ModuleLayer
                         |
                         v
             Load classes / services
~~~

Therefore, being able to create a configuration does not mean the plugins have been started. The application still needs to create a layer and use classes or services from that layer.

## 2. ModuleFinder: Module Discovery Source

`ModuleFinder` is an abstraction for finding modules by name and listing the modules provided by that source.

A common source is a directory containing modular JARs, automatic modules, or exploded modules:

~~~java
import java.lang.module.ModuleFinder;
import java.nio.file.Path;

ModuleFinder pluginFinder =
    ModuleFinder.of(Path.of("plugins"));
~~~

`ModuleFinder.of(Path...)` can locate modules in the specified paths. Those paths are typically:

- A modular JAR containing `module-info.class`.
- A JAR without a descriptor, which can be recognized as an automatic module.
- A directory containing a compiled module structure (an exploded module).

You can inspect the modules found by the finder:

~~~java
pluginFinder.findAll().forEach(reference ->
    System.out.println(reference.descriptor().name())
);
~~~

Each `ModuleReference` provides a descriptor and reference information to the module's contents. `ModuleFinder` does not resolve dependencies by itself; it only helps locate modules for the resolution step to use.

Some useful factory methods:

- `ModuleFinder.of(paths...)`: finds modules from specific paths.
- `ModuleFinder.ofSystem()`: finds the modules of the runtime image.
- `ModuleFinder.of()`: creates an empty finder that provides no modules.

Multiple finders can be combined with `ModuleFinder.compose(...)` if the application needs to search modules from multiple sources. When duplicate module names exist within the same observable source set, module lookup may fail; avoid placing versions or copies with the same module name in conflicting locations.

## 3. Meaning of before, after, and roots

The two methods `resolve` and `resolveAndBind` accept important parameters:

~~~java
Configuration.resolve(
    ModuleFinder before,
    ModuleFinder after,
    Collection<String> roots
);
~~~

- **`before`**: the finder used to locate modules before checking parent configurations.
- **`after`**: the finder used to locate modules after checking parent configurations.
- **`roots`**: the set of root module names the application wants to include in the new configuration.

This search order allows the application to combine the new layer's module sources with modules already present in parent layers. In a simple plugin setup, it is common to pass the plugin finder as `before` and an empty finder as `after`.

Example:

~~~java
ModuleFinder pluginFinder =
    ModuleFinder.of(Path.of("plugins"));

Configuration parent =
    ModuleLayer.boot().configuration();

Configuration configuration = parent.resolve(
    pluginFinder,
    ModuleFinder.of(),
    Set.of("com.example.plugin")
);
~~~

Here:

1. `com.example.plugin` is the root module.
2. JPMS locates this module from `pluginFinder`.
3. The `requires` directives in the plugin's descriptor are traversed.
4. Required dependency modules are looked up in the observable sources and parent configurations.
5. If all modules can be found and the dependency graph is valid, the method returns the new configuration.

`roots` is not a list of all dependencies. You only need to declare the modules the application wants to start from; JPMS automatically resolves dependencies declared with `requires` according to module system rules.

If a root module does not exist, a dependency is missing, there is a split package, or the module graph is invalid, resolution may fail.

## 4. Configuration.resolve(): Resolving Explicit Dependencies

`resolve(...)` resolves root modules and the dependencies they declare. This process follows directives such as `requires`, including transitive dependencies pulled in through other modules.

Plugin module example:

~~~java
module com.example.plugin {
    requires com.example.plugin.api;
    requires java.logging;
}
~~~

The application can resolve the plugin:

~~~java
ModuleFinder finder =
    ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    ModuleLayer.boot().configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.example.plugin")
    );
~~~

The new configuration contains the plugin root and the required modules according to the dependency graph. If `com.example.plugin.api` is already in the parent configuration, JPMS can use the module from the parent; otherwise, it must be found in the supplied finders.

When should you use `resolve`?

- The application knows exactly which modules need to be loaded.
- Dependencies between modules are already declared with `requires`.
- There is no need to automatically add provider modules simply because they provide a service used by a root module.
- The application wants explicit control over roots and the set of resolved modules.

`resolve` does not perform service binding. If a plugin provider is not required by the root module via `requires`, the provider may not appear in the configuration just because it has a `provides` directive.

## 5. Configuration.resolveAndBind(): Resolving with Service Binding

`resolveAndBind(...)` performs resolution like `resolve(...)`, and then performs service binding. JPMS inspects the `uses` directives in the resolved modules, finds observable provider modules with matching `provides` directives, and adds those provider modules to the configuration.

Service API example:

~~~java
package com.example.plugin.api;

public interface Plugin {
    void start();
}
~~~

API module:

~~~java
module com.example.plugin.api {
    exports com.example.plugin.api;
}
~~~

Application module declaring service usage:

~~~java
module com.example.app {
    requires com.example.plugin.api;

    uses com.example.plugin.api.Plugin;
}
~~~

A provider module:

~~~java
module com.example.plugin.audit {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.plugin.audit.AuditPlugin;
}
~~~

The application can resolve the root module `com.example.app` and let JPMS locate providers:

~~~java
ModuleFinder pluginFinder =
    ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    ModuleLayer.boot().configuration().resolveAndBind(
        pluginFinder,
        ModuleFinder.of(),
        Set.of("com.example.app")
    );
~~~

If `com.example.app` declares `uses com.example.plugin.api.Plugin` and `com.example.plugin.audit` is observable in the search sources, service binding can add the provider module along with its dependencies to the configuration.

Service binding can continue finding providers for services used by the newly added provider modules. Therefore, the resulting configuration may contain more modules than the initial root set and direct `requires` dependencies.

Keep in mind:

- `resolveAndBind` does not instantiate provider objects.
- It only includes matching provider modules in the configuration.
- Creating provider instances is still performed by `ServiceLoader` when the application requests them.
- The provider must be within the scope of the module finders/layers being searched.
- The consumer must still declare `uses`; the provider must declare `provides`.

## 6. Comparing resolve and resolveAndBind

| Criterion | `resolve(...)` | `resolveAndBind(...)` |
|---|---|---|
| Resolves roots | Yes | Yes |
| Resolves `requires` dependencies | Yes | Yes |
| Locates providers via service binding | No | Yes |
| Adds a module merely because it provides a used service | No | Yes |
| Instantiates provider instances | No | No |
| Best suited for | Explicit dependencies | Plugins / service providers |

An easy example to remember:

- The application declares `requires com.example.plugin.audit`: `resolve` will include the provider module because it is an explicit dependency.
- The application only declares `uses Plugin`, and the provider module is found by the finder: `resolveAndBind` can automatically add the provider module via service binding.
- Both methods require a `ModuleLayer` creation step before classes in the new modules can be loaded and used at runtime.

Do not use `resolveAndBind` expecting it to find every plugin anywhere on the machine. It only searches among modules observable through the provided finders and parent configurations.

## 7. Creating a ModuleLayer from a Configuration

After obtaining a valid configuration, the application can create a child layer:

~~~java
ModuleFinder pluginFinder =
    ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    ModuleLayer.boot().configuration().resolve(
        pluginFinder,
        ModuleFinder.of(),
        Set.of("com.example.plugin")
    );

ModuleLayer pluginLayer =
    ModuleLayer.boot().defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
    );
~~~

`defineModulesWithOneLoader` defines the modules in the configuration using a single shared class loader for the new layer, with the specified class loader as its parent.

Another option is `defineModulesWithManyLoaders`, which creates a separate loader for each module. Choosing one loader or many loaders depends on the plugin architecture, class isolation approach, and whether packages/classes need to be shared between modules.

A few notes:

- The configuration must have been created from the parent configuration corresponding to the layer on which you call `defineModules...`.
- The new module layer can read modules in the parent according to JPMS rules; the parent does not automatically read modules in the child layer in reverse.
- Creating a layer does not mean every class in every module is initialized.
- You can check whether a module has been defined:

~~~java
pluginLayer.findModule("com.example.plugin")
    .ifPresent(module ->
        System.out.println(module.getName()));
~~~

## 8. Plugin Example Using resolveAndBind

Suppose the `plugins/` directory contains the modules:

~~~text
plugins/
├── com.example.app.jar
├── com.example.plugin.api.jar
├── com.example.plugin.audit.jar
└── com.example.plugin.metrics.jar
~~~

The application declares:

~~~java
module com.example.app {
    requires com.example.plugin.api;

    uses com.example.plugin.api.Plugin;
}
~~~

Audit provider:

~~~java
module com.example.plugin.audit {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.plugin.audit.AuditPlugin;
}
~~~

Metrics provider:

~~~java
module com.example.plugin.metrics {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.plugin.metrics.MetricsPlugin;
}
~~~

The application can be resolved along with its providers via:

~~~java
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;

ModuleFinder finder =
    ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    ModuleLayer.boot().configuration().resolveAndBind(
        finder,
        ModuleFinder.of(),
        Set.of("com.example.app")
    );

ModuleLayer layer =
    ModuleLayer.boot().defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
    );

ServiceLoader<Plugin> plugins =
    ServiceLoader.load(layer, Plugin.class);

for (Plugin plugin : plugins) {
    plugin.start();
}
~~~

In this example, `com.example.app` is the root. Its module descriptor declares `uses Plugin`; both provider modules are observable in `finder`. Service binding can include both providers in the configuration. Once the layer is created, `ServiceLoader.load(layer, Plugin.class)` locates providers in that layer and its ancestor layers according to the API's rules.

The consumer does not need to write `requires com.example.plugin.audit` or `requires com.example.plugin.metrics`. Adding a new provider can be done by placing the provider module in the plugin directory and ensuring it is visible to the finder/layer.

## 9. Inspecting Resolution Results

After creating the configuration, you can inspect the resolved modules:

~~~java
configuration.modules().forEach(resolvedModule ->
    System.out.println(resolvedModule.name())
);
~~~

This list is useful for checking:

- Whether the root modules were included.
- Whether `requires` dependencies were resolved.
- Whether provider modules were added when using `resolveAndBind`.
- Whether unexpected modules were pulled in through dependencies or service binding.

You can inspect the service providers discovered in the layer:

~~~java
ServiceLoader<Plugin> plugins =
    ServiceLoader.load(layer, Plugin.class);

plugins.stream().forEach(provider ->
    System.out.println(provider.type().getName())
);
~~~

`Provider.type()` allows inspecting the provider type before calling `Provider.get()`. This is useful for confirming which providers were found without instantiating all of them.

If the configuration does not contain an expected provider, check whether the finder locates that module, whether the provider module `provides` the exact service type, whether the consumer `uses` the exact service type, and whether the provider is within the observable scope of the resolution process.

## 10. Common Errors

**Root module not found.** A name in `roots` does not exist in the search sources or parent configuration. Verify the module name with `jar --describe-module` and the finder path.

**Missing plugin dependency.** A provider module has a `requires` for a module not present in the finder or parent configuration. Resolution will fail.

**Using `resolve` and expecting providers to appear automatically.** `resolve` only handles roots and explicit dependencies. If service binding is needed, consider `resolveAndBind`.

**Using `resolveAndBind` with no providers found.** Check the consumer's `uses`, the provider's `provides`, the module finder, the module layer, and the deployment configuration.

**Confusing Configuration with ModuleLayer.** Configuration is only the resolved module graph; a layer must be defined to have a runtime environment for loading modules.

**Calling ServiceLoader on the wrong layer.** If plugins reside in a custom layer, use `ServiceLoader.load(layer, Service.class)` with the right layer instead of searching only in the default layer.

**Assuming resolveAndBind instantiates plugins.** Service binding only adds provider modules to the configuration. Provider objects are created when ServiceLoader requests instances.

**Relying on provider order to determine the default plugin.** JPMS does not provide a business priority policy. Use an ID, priority, or application configuration instead.

## 11. When to Choose Which Method?

Choose `resolve` when the application already knows which modules must be placed into the layer and dependencies are described via `requires`. This suits explicit module graphs with little reliance on service discovery.

Choose `resolveAndBind` when the application uses an SPI and wants JPMS to automatically locate provider modules for services declared with `uses` by resolved modules. This is the right choice for plugin systems where providers can be added without modifying the consumer's direct dependencies.

In both cases, keep responsibilities clear:

- The module descriptor declares dependencies and service contracts.
- ModuleFinder defines the observable module sources.
- Configuration resolves the module graph.
- ModuleLayer defines the modules at runtime.
- ServiceLoader discovers and instantiates providers.
- The application decides which providers are used and in what order.

## 12. Self-Check

When building dynamic module layers, answer:

1. Which root modules need to be resolved?
2. Which directory, JAR, or source is ModuleFinder searching for modules?
3. Are the `requires` dependencies of the roots complete?
4. Has the consumer declared `uses` for the service to look up?
5. Has the provider module declared `provides` with the exact service type?
6. Should `resolve` or `resolveAndBind` be used?
7. Which modules are in the new configuration after resolution?
8. Is the layer created with one class loader or many class loaders?
9. Is ServiceLoader searching in the right layer?
10. If there are multiple providers, where is the policy for selecting or running providers defined?

Understanding `resolve`, `resolveAndBind`, and `ModuleLayer` helps build extensible plugin mechanisms while keeping dependencies under control. JPMS handles locating and resolving modules; the application remains responsible for lifecycle, configuration, and provider usage policy.
