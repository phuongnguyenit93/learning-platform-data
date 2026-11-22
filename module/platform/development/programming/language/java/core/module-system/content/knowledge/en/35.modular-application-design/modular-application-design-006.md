# Choosing Layers When Plugins or Isolation Are Needed

The Java Module System allows an application to create multiple `ModuleLayer` instances within the same JVM. Each layer holds a resolved module configuration and has parent relationships with one or more other layers. This is a useful foundation when an application needs to load plugins dynamically, manage multiple module groups, or scope provider visibility.

Not every application needs to create custom layers. If all modules are statically determined at startup, a single module graph in the boot layer or a single module layer is usually simpler. Create new layers only when there is a real need for plugin lifecycles, changing module sets, multiple plugin versions, or separate service scopes.

## 1. What does `ModuleLayer` represent?

`ModuleLayer` is a collection of modules defined at runtime, together with relationships to parent layers. A layer is created from a resolved `Configuration` and one or more parent layers.

Related components:

| Component | Role |
|---|---|
| `ModuleFinder` | Locates modules from a module path, runtime image, or other module source |
| `ModuleDescriptor` | Describes module name, `requires`, `exports`, `opens`, `uses`, and `provides` |
| `Configuration` | Result of resolving the module graph, determining present modules and dependencies |
| `ModuleLayer` | Contains the defined modules and parent-child relationships between layers |
| `ModuleLayer.Controller` | Controls a newly created layer and can adjust certain module relationships at runtime |
| `ClassLoader` | Loads module classes according to how the layer was defined |

Typical layer creation flow:

~~~text
Plugin directory
      |
      v
ModuleFinder
      |
      v
Configuration.resolve(...)
      |
      v
ModuleLayer.defineModulesWithOneLoader(...)
      |
      v
ModuleLayer child
      |
      v
ServiceLoader.load(childLayer, Service.class)
~~~

`Configuration` is the resolution result, whereas `ModuleLayer` is the runtime environment where the modules in that configuration are defined. Merely finding a JAR with `ModuleFinder` does not mean that module has been loaded into a layer.

## 2. When should you create a separate layer?

Common suitable scenarios:

- **Plugins installed after the application has started:** the application can scan a plugin directory and create a new layer for the plugin.
- **Multiple independent plugin groups:** each group can be placed in a separate child layer to control which modules are visible.
- **Separate dependency versions needed:** two plugins can use different module dependencies if the module graph and class loaders are designed appropriately.
- **Specific `ServiceLoader` scoping needed:** the application can search for providers in a specific layer and its parent layers.
- **Deployment boundaries needed:** plugin modules are resolved and initialized at their own timing or configuration.

Do not create layers just to organize packages neatly. If modules are always loaded together, share the same lifecycle, and do not need separate discovery scopes, a single layer is usually easier to operate.

## 3. Host and plugin architecture

A typical plugin design places the service API in the parent layer. Both the host and the plugin reference the exact same service interface definition. Plugin implementations live in child layers.

~~~text
Boot layer
|-- com.example.plugin.api
|      exports com.example.plugin.api
|
|-- com.example.host
       requires com.example.plugin.api
       uses com.example.plugin.api.Plugin

Child layer A
|-- com.example.audit.plugin
       requires com.example.plugin.api
       provides Plugin with AuditPlugin

Child layer B
|-- com.example.export.plugin
       requires com.example.plugin.api
       provides Plugin with ExportPlugin
~~~

The host knows only the `Plugin` contract. It does not need to import `AuditPlugin` or `ExportPlugin`. Each plugin is discovered and loaded into the appropriate layer.

Service API:

~~~java
package com.example.plugin.api;

public interface Plugin {
    String name();

    void start();
}
~~~

API module:

~~~java
module com.example.plugin.api {
    exports com.example.plugin.api;
}
~~~

Host module:

~~~java
module com.example.host {
    requires com.example.plugin.api;

    uses com.example.plugin.api.Plugin;
}
~~~

Plugin module:

~~~java
module com.example.audit.plugin {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.audit.plugin.AuditPlugin;
}
~~~

Implementation:

~~~java
package com.example.audit.plugin;

import com.example.plugin.api.Plugin;

public final class AuditPlugin implements Plugin {
    public AuditPlugin() {
    }

    @Override
    public String name() {
        return "audit";
    }

    @Override
    public void start() {
        System.out.println("Audit plugin started");
    }
}
~~~

The service API should be defined and loaded from the parent layer. Do not bundle a copy of the API into each plugin. If the host and plugin see two different `Plugin` classes defined by two different class loaders, they do not share class identity, and casting or invoking the service can fail.

## 4. Finding and resolving plugin modules

Suppose the host receives a plugin directory path. `ModuleFinder` can locate the root module and then resolve dependencies based on the boot layer's configuration.

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

Path pluginPath = Path.of("plugins", "audit");
ModuleFinder finder = ModuleFinder.of(pluginPath);

Configuration configuration =
        ModuleLayer.boot()
                .configuration()
                .resolve(
                        finder,
                        ModuleFinder.of(),
                        Set.of("com.example.audit.plugin"));
~~~

Meaning:

1. `ModuleFinder.of(pluginPath)` discovers modules in the plugin directory.
2. The boot layer's `Configuration` acts as the parent configuration for resolving dependencies.
3. `finder` supplies the plugin module and dependencies residing in that directory.
4. `ModuleFinder.of()` in the after-finder position adds no modules from another source.
5. `Set.of(...)` specifies the root modules to resolve.

Dependencies can be satisfied by modules in the parent configuration or module finders according to resolution rules. If a plugin needs its own libraries, place them on the appropriate module path and manage module name conflicts.

`resolveAndBind()` can be used instead of `resolve()` when you want service binding to automatically pull in matching provider modules from the finders during resolution. Do not use it mechanically: identify which services are declared with `uses` and which providers need to be included in the configuration.

## 5. Defining a layer with one class loader

Once you have a `Configuration`, create the layer:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

public final class PluginLayerFactory {

    private PluginLayerFactory() {
    }

    public static ModuleLayer create(Path pluginPath) {
        ModuleFinder finder = ModuleFinder.of(pluginPath);

        Configuration configuration =
                ModuleLayer.boot()
                        .configuration()
                        .resolve(
                                finder,
                                ModuleFinder.of(),
                                Set.of("com.example.audit.plugin"));

        ModuleLayer.Controller controller =
                ModuleLayer.defineModulesWithOneLoader(
                        configuration,
                        List.of(ModuleLayer.boot()),
                        Plugin.class.getClassLoader());

        return controller.layer();
    }
}
~~~

`defineModulesWithOneLoader` defines all modules in the new configuration using a single new class loader. This class loader's parent is the class loader passed in. In the example, the parent loader can see the service API defined in the parent layer.

This approach fits when modules within the same plugin layer can share one class loader. It also helps manage a group of plugins as a single unit.

Do not pass a parent loader that cannot see the service API or public types the plugin needs to use. If the API class is loaded a second time in the child layer, its class identity will differ from the API class the host is using.

## 6. Using `ServiceLoader` to find providers in a layer

After creating the layer, the host can look up providers using the overload that takes a `ModuleLayer`:

~~~java
import java.util.ServiceLoader;

ModuleLayer pluginLayer =
        PluginLayerFactory.create(Path.of("plugins", "audit"));

ServiceLoader<Plugin> loader =
        ServiceLoader.load(pluginLayer, Plugin.class);

for (Plugin plugin : loader) {
    System.out.println(plugin.name());
    plugin.start();
}
~~~

`ServiceLoader.load(pluginLayer, Plugin.class)` searches for providers in the specified layer and its parent layers. It does not find providers residing only in a sibling layer.

If you need to inspect which layer a provider belongs to before instantiating it, use `stream()`:

~~~java
ServiceLoader.load(pluginLayer, Plugin.class)
        .stream()
        .forEach(provider -> {
            Class<?> providerType = provider.type();

            System.out.println(providerType.getName());
            System.out.println(providerType.getModule().getLayer());
        });
~~~

Note that parent layers can also contain providers. If the requirement is to run only providers originating from a specific plugin layer, filter by `provider.type().getModule().getLayer()` before calling `get()`.

`ServiceLoader` does not manage the full plugin lifecycle on its own. The host still needs to define how plugins are started, stopped, error-handled, stateful, and cleaned up.

## 7. One layer or multiple layers?

You can create one layer containing multiple plugins or create a separate layer for each plugin.

### One layer for a group of plugins

~~~text
Boot layer
    |
    v
Plugin layer
    |-- audit plugin
    |-- export plugin
    |-- reporting plugin
~~~

Suitable when plugins are deployed, upgraded, and started together; share dependencies; or need to share classes among plugin modules.

### One layer per plugin

~~~text
                 Boot layer
                /     |     \
               v      v      v
           Audit    Export  Report
           layer    layer   layer
~~~

Suitable when plugins have separate dependencies, need to be loaded or unloaded independently, or need `ServiceLoader` scope isolation. Each child layer can have its own configuration and class loader.

However, separate layers do not automatically isolate everything. Plugins still run in the same process and can share OS resources, threads, the filesystem, and any APIs permitted by the process's privileges. If untrusted code must be run, use process/container boundaries and OS-level access controls.

## 8. Choosing a class loader strategy

`ModuleLayer` provides several ways to define modules and attach class loaders.

| API | Loader organization | When appropriate |
|---|---|---|
| `defineModulesWithOneLoader` | One loader for all modules in the new layer | Modules in a plugin group need to share a loader |
| `defineModulesWithManyLoaders` | One loader per new module | Loaders need to be separated across modules |
| `defineModules` | Application supplies a function mapping module name to class loader | Fine-grained control over loader strategy is needed |

With `defineModulesWithManyLoaders`, modules still belong to the same `ModuleLayer` but have separate loaders. With `defineModules`, the mapping function must return an appropriate class loader for each module.

Choose a loader strategy based on dependencies and runtime requirements. Multiple loaders can make class visibility more complex. If one module needs to share types with another module, ensure appropriate readability relationships and class-loading capabilities.

A class in Java is identified not only by its fully qualified name, but also by the class loader that defined it. Two classes with the same name defined by two different loaders are two distinct types. This is a common cause of `ClassCastException` when a plugin bundles a duplicate copy of the service API.

## 9. Parent-child and sibling layer relationships

A child layer can read modules from parent layers according to configuration and readability rules. Sibling layers, however, do not automatically read each other's modules.

~~~text
                 Boot layer
                 /        \
             childA      childB
               |            |
          Plugin A      Plugin B
~~~

If `childA` and `childB` both have the boot layer as their parent:

- Plugins in `childA` can read eligible modules from the boot layer.
- Plugins in `childB` can read eligible modules from the boot layer.
- `childA` does not automatically read modules that exist only in `childB`.
- `childB` does not automatically read modules that exist only in `childA`.

This is the basis for scoping providers or dependencies between plugins. If two plugins need to communicate, design a contract in a parent layer or exchange data through a host-managed API instead of directly accessing the other layer's implementation.

Also distinguish visibility from package access. One module may read another module and still be unable to access an unexported package. Readability and `exports` are two separate conditions.

## 10. Controller and runtime module adjustments

The `defineModules...` methods return a `ModuleLayer.Controller`. The controller enables certain controlled changes to modules in the created layer, for example:

- `addReads`: adds a readability relationship.
- `addExports`: exports a package to a target module.
- `addOpens`: opens a package for deep reflection.

Illustrative example:

~~~java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithOneLoader(
                configuration,
                List.of(ModuleLayer.boot()),
                Plugin.class.getClassLoader());

ModuleLayer layer = controller.layer();
~~~

Retain the `Controller` only if the application genuinely needs to adjust module relationships after layer creation. Do not use `addReads`, `addExports`, or `addOpens` to mask a poorly designed module descriptor. Declare `requires`, `exports`, and `opens` directly in `module-info.java` when they are stable contracts.

Runtime adjustments can introduce coupling that is hard to see in descriptors and complicate diagnostics. Clearly document the reason, source module, target module, and opened package whenever `Controller` must be used.

## 11. Plugin lifecycle and layer reclamation

`ModuleLayer` does not have a `close()` method like `URLClassLoader`. Creating a layer does not imply the application can unload a plugin immediately.

Classes and resources loaded by a plugin's class loader can be reclaimed once the class loader becomes unreachable and the garbage collector can reclaim the corresponding classes. Therefore, the application must release every reference that could keep the plugin alive:

- Stop threads created by the plugin.
- Cancel executors, schedulers, and timers.
- Unregister listeners or callbacks registered with the host.
- Remove plugin objects from registries and caches.
- Clear `ThreadLocal` values created by the plugin if held by long-lived threads.
- Restore the thread context class loader if the plugin changed it.
- Close files, sockets, database connections, and resources owned by the plugin.
- Do not retain `ServiceLoader`, `Provider`, or plugin `Class` objects in global caches.

Even after dropping references to `ModuleLayer`, a running thread executing plugin code or a static cache on the host can still keep the class loader alive. Reclamation does not happen instantaneously and should not rely on `System.gc()`.

Plugin design needs a lifecycle contract—such as `start()` and `stop()`—so the host can ask the plugin to release resources before removing registry entries and references to the layer.

## 12. `ModuleLayer` is not a security sandbox

`ModuleLayer` organizes module graphs, readability, `exports`, `opens`, and class-loading scope. It is not a security sandbox for untrusted code.

A plugin running in the same JVM can exercise whatever privileges the process holds if it can access the corresponding APIs. Module encapsulation controls access between modules, but it does not replace operating system permissions.

If plugins come from untrusted sources or require restrictions on file access, network access, native code, or host resources, consider running plugins in a separate process, container, or OS-controlled environment. Communicating over IPC or a network contract provides a stronger boundary than layers inside the same JVM.

## 13. Testing plugin layers

At minimum, test the following scenarios:

| Scenario | Expected result |
|---|---|
| Valid plugin module in plugin directory | `ModuleFinder` locates it and `Configuration` resolves successfully |
| Plugin missing a dependency | Resolution fails with missing module information |
| Plugin properly declares `provides` for the service | The layer's `ServiceLoader` finds the provider |
| Provider resides in the parent layer | Child layer loader can see the parent provider |
| Provider resides only in a sibling layer | Another layer's loader does not find that provider |
| Plugin bundles a duplicate copy of the service API | Class identity or module configuration error is detected |
| Two plugins use the same module name in the same configuration | Module name conflict is detected |
| Plugin `stop` fails to release threads/listeners | The class loader may remain alive |

Example of checking layer identity:

~~~java
ServiceLoader.load(pluginLayer, Plugin.class)
        .stream()
        .filter(provider ->
                provider.type().getModule().getLayer() == pluginLayer)
        .forEach(provider -> {
            Plugin plugin = provider.get();
            plugin.start();
        });
~~~

If a layer has multiple providers or providers from parent layers, do not assume iteration order. Identify providers by module name, metadata, or business contract.

Beyond unit tests, run integration tests using the actual plugin module directory and target JDK. Tests on the classpath do not prove that the module path and layer resolution behave as expected.

## 14. Layer selection workflow

When deciding whether to create a separate layer, answer in order:

1. Do modules/plugins need to be discovered or loaded after the host has started?
2. Do plugins have separate dependency graphs or dependency versions?
3. Does the host need to control `ServiceLoader` scope per plugin?
4. Do plugins need to be loaded and lifecycle-managed independently?
5. Can the service API be shared from a parent layer without duplicating classes?
6. Is one loader needed for the whole module group, or separate loaders per module?
7. Is security isolation required? If so, `ModuleLayer` alone does not satisfy it.
8. Is there a plan to stop threads, listeners, and resources before dropping a layer?

If there is no need for dynamic discovery, dependency isolation, or separate lifecycles, using a single module layer reduces complexity. If dynamic plugins exist, multiple child layers with a shared service API in the parent are usually an appropriate structure.

## 15. Key takeaways

`ModuleLayer` is the runtime unit that defines a set of resolved modules and their parent-child relationships. Use separate layers when you need dynamic plugin loading, provider scope control, or management of module groups with independent dependencies and lifecycles. Place the stable service API in a parent layer, resolve plugins with `ModuleFinder` and `Configuration`, and define the layer with an appropriate class loader.

A child layer can see modules in its parents according to module system rules; sibling layers do not automatically see each other. Choose one loader for an entire plugin group when they need to share a loader, or multiple loaders when class loading must be separated. Finally, remember that `ModuleLayer` is not a security sandbox, and reclaiming plugins requires releasing class loaders, threads, listeners, and resources held by the plugin.

## References

- Java API — ModuleLayer: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ModuleLayer.html
- Java API — Configuration: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/Configuration.html
- Java API — ServiceLoader: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html
- Java Platform Module System — Module API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/package-summary.html
