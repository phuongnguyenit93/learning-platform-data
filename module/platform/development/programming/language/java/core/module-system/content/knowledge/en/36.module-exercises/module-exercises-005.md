# Creating a Custom ModuleLayer from ModuleFinder

## Objectives

After this lesson, you can:

- Explain the roles of `ModuleFinder`, `Configuration`, and `ModuleLayer`.
- Find modules from a directory containing modular JARs or exploded modules.
- Resolve plugin dependencies based on a parent layer.
- Create a custom layer using `defineModulesWithOneLoader()` or `defineModulesWithManyLoaders()`.
- Use `ServiceLoader.load(layer, serviceType)` to locate providers in a custom layer.
- Distinguish normal resolution from service binding with `resolveAndBind()`.
- Manage resolution errors, class loaders, and plugin lifecycles.

## 1. Why do we need a custom ModuleLayer?

JPMS organizes applications into named modules. When launching an application, the JVM creates a module graph and places resolved modules into a `ModuleLayer`. The JDK platform modules and initial application modules typically reside in the boot layer:

~~~java
ModuleLayer boot = ModuleLayer.boot();

System.out.println(boot.modules());
~~~

An application may need to load plugins after the program has started. For example, a host application provides a `Codec` service API, while JSON and XML plugins are packaged as separate modular JARs.

If you want to add these modules without including them in the startup module graph, the application can:

1. Use `ModuleFinder` to find modules in the plugin directory.
2. Resolve those modules along with their dependencies into a `Configuration`.
3. Create a new `ModuleLayer` from the configuration.
4. Use the new layer to access modules or discover service providers.

A custom layer has a parent relationship with an existing layer. Modules in the child layer can read appropriate modules in the parent according to the resolved module graph. Modules in the child layer do not automatically become members of the boot layer.

## 2. Three main components

### 2.1. ModuleFinder: finding modules

`ModuleFinder` is an abstraction used to find a `ModuleReference` by module name. The JDK provides common ways to create finders:

~~~java
ModuleFinder systemFinder = ModuleFinder.ofSystem();

ModuleFinder pluginFinder =
        ModuleFinder.of(Path.of("plugins"));
~~~

- `ModuleFinder.ofSystem()` locates the system modules of the runtime image.
- `ModuleFinder.of(path...)` locates modules in the specified paths, including modular JARs and exploded modules.
- `find(moduleName)` finds a module by name and returns `Optional<ModuleReference>`.
- `findAll()` returns the set of module references discovered by the finder.

Example checking the contents of a plugin directory:

~~~java
Path pluginDirectory = Path.of("plugins");

ModuleFinder finder = ModuleFinder.of(pluginDirectory);

finder.findAll().forEach(reference ->
        System.out.println(reference.descriptor().name()));
~~~

`ModuleFinder` only helps locate module metadata and content locations. It does not define modules in the JVM yet and does not create class loaders for plugins.

### 2.2. Configuration: resolving the module graph

`Configuration` represents the result of resolving a module graph. It determines the required modules, `requires` dependencies, and module relationships needed to create a layer.

You can obtain the configuration of a parent layer:

~~~java
Configuration parentConfiguration =
        ModuleLayer.boot().configuration();
~~~

Then resolve root modules from the finder:

~~~java
Configuration configuration =
        parentConfiguration.resolve(
                pluginFinder,
                ModuleFinder.of(),
                Set.of("com.example.codec.json"));
~~~

Parameters of `resolve(before, after, roots)`:

- `before`: finder searched before the parent configuration.
- Parent configuration: modules already present in the parent layer.
- `after`: finder searched after the parent configuration.
- `roots`: set of module names starting the resolution process.

For instance, placing `pluginFinder` in the `before` position ensures plugin modules are searched first in the plugin directory; dependencies already available in the parent configuration, such as an API module already in the boot layer, can be reused from the parent.

If a requested module is not found, a dependency is missing, or the graph is invalid, resolution fails with a resolution error. Therefore, check module names, module paths, and dependency descriptors.

### 2.3. ModuleLayer: defining modules at runtime

Once you have a configuration, use the parent layer to create a child layer:

~~~java
ModuleLayer parent = ModuleLayer.boot();

ModuleLayer.Controller controller =
        parent.defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader());

ModuleLayer pluginLayer = controller.layer();
~~~

`ModuleLayer` is the runtime container for resolved modules. A layer maintains its relationship to parent layers and maps modules to class loaders.

The API returns a `ModuleLayer.Controller` so the application can retrieve the newly created layer and, when truly necessary, adjust certain module relationships using controller methods.

## 3. Example: creating a custom layer from a plugin directory

Suppose the host application already has a service API in the boot layer:

~~~java
package com.example.codec;

public interface Codec {
    String name();
    byte[] encode(String input);
}
~~~

The API module is exported:

~~~java
module com.example.codec.api {
    exports com.example.codec;
}
~~~

Plugins are separate named modules. Example JSON plugin:

~~~java
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.Codec
            with com.example.codec.json.JsonCodec;
}
~~~

Implementation:

~~~java
package com.example.codec.json;

import com.example.codec.Codec;

public final class JsonCodec implements Codec {

    public JsonCodec() {
    }

    @Override
    public String name() {
        return "json";
    }

    @Override
    public byte[] encode(String input) {
        return ("{\"value\":\"" + input + "\"}")
                .getBytes(java.nio.charset.StandardCharsets.UTF_8);
    }
}
~~~

Plugin JARs are placed in the `plugins` directory. The host application can load the plugin as follows:

~~~java
import com.example.codec.Codec;

import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;

public class PluginLoader {

    public static void main(String[] args) {
        ModuleLayer parent = ModuleLayer.boot();

        ModuleFinder pluginFinder =
                ModuleFinder.of(Path.of("plugins"));

        Configuration configuration =
                parent.configuration().resolve(
                        pluginFinder,
                        ModuleFinder.of(),
                        Set.of("com.example.codec.json"));

        ModuleLayer.Controller controller =
                parent.defineModulesWithOneLoader(
                        configuration,
                        ClassLoader.getSystemClassLoader());

        ModuleLayer pluginLayer = controller.layer();

        ServiceLoader<Codec> codecs =
                ServiceLoader.load(pluginLayer, Codec.class);

        codecs.forEach(codec ->
                System.out.println("Loaded: " + codec.name()));
    }
}
~~~

Steps in the example:

1. Obtain the boot layer as the parent.
2. Create a `ModuleFinder` for the `plugins` directory.
3. Resolve root module `com.example.codec.json` along with dependencies not yet present in the parent.
4. Create a custom layer with a shared class loader for modules in the configuration.
5. Use the `ServiceLoader.load(pluginLayer, Codec.class)` overload to locate providers in the plugin layer and its parent layers.
6. Iterate through providers to instantiate and use the service.

The example assumes `com.example.codec.api` is already resolved in the boot layer and exports package `com.example.codec`. If the API module is also placed in the plugin directory, the finder may resolve it into the child layer instead of using the API class from the parent. Do not let host and plugin accidentally use two different copies of the service API, because two classes with the same name belonging to different modules/class loaders are not necessarily the same Java type.

## 4. Loading multiple plugin modules

A directory can contain multiple modular JARs:

~~~text
plugins/
├── com.example.codec.json.jar
├── com.example.codec.xml.jar
└── com.example.codec.binary.jar
~~~

You can specify multiple root modules:

~~~java
Set<String> roots = Set.of(
        "com.example.codec.json",
        "com.example.codec.xml",
        "com.example.codec.binary");

Configuration configuration =
        parent.configuration().resolve(
                pluginFinder,
                ModuleFinder.of(),
                roots);
~~~

During resolution, `requires` dependencies of each root are also handled. If a dependency already exists in the parent configuration, the child module graph can use the module in the parent instead of redefining that module.

After creating the layer, ServiceLoader can locate all matching providers:

~~~java
ServiceLoader<Codec> codecs =
        ServiceLoader.load(pluginLayer, Codec.class);

for (Codec codec : codecs) {
    System.out.println(codec.name());
}
~~~

If a plugin does not declare `provides` for the service, the module can still be resolved but will not appear as a provider of `Codec`. Having a module present in a layer and having a module provide a service are two distinct conditions.

## 5. resolve() and resolveAndBind()

`Configuration.resolve()` handles root modules and `requires` dependencies. `Configuration.resolveAndBind()` additionally performs service binding to add provider modules matching services declared as used by resolved modules.

For example, a host module in the finder declares:

~~~java
module com.example.plugin.host {
    requires com.example.codec.api;

    uses com.example.codec.Codec;
}
~~~

If you want the resolver to automatically find observable `Codec` providers in the plugin finder, you can use:

~~~java
Configuration configuration =
        parent.configuration().resolveAndBind(
                ModuleFinder.of(),
                pluginFinder,
                Set.of("com.example.plugin.host"));
~~~

In this example:

- The first finder is empty; modules not in the parent will be searched in the second finder.
- `com.example.plugin.host` is the root module.
- The `uses` directive indicates the service the host needs.
- Modules in `pluginFinder` declaring `provides` for the matching service can be added to the graph.

`resolveAndBind()` does not instantiate providers. It only adds modules to the configuration. Instantiation is still performed by `ServiceLoader` when the application consumes providers.

When you already know the exact plugins to load, `resolve()` with an explicit list of roots is usually easier to control. When you want to discover providers by service declaration, `resolveAndBind()` is more suitable.

## 6. Choosing class loaders for a layer

ModuleLayer provides several ways to map modules to class loaders.

### 6.1. One class loader for the entire layer

~~~java
ModuleLayer.Controller controller =
        parent.defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader());
~~~

`defineModulesWithOneLoader()` defines the modules in the configuration using one shared class loader. This approach is usually simple for a group of plugins that have dependency relationships with one another.

### 6.2. One class loader per module

~~~java
ModuleLayer.Controller controller =
        parent.defineModulesWithManyLoaders(
                configuration,
                ClassLoader.getSystemClassLoader());
~~~

`defineModulesWithManyLoaders()` creates a separate class loader for each module in the layer. This can be useful when you want to separate class loading across modules.

### 6.3. Custom class loader mapping

If finer control is needed, use `defineModules()` and supply a function mapping module names to class loaders:

~~~java
ModuleLayer.Controller controller =
        parent.defineModules(
                configuration,
                moduleName -> chooseLoaderFor(moduleName));
~~~

The mapping function must return an appropriate class loader for each module as designed. It must not return `null` for a module that needs to be defined.

Using multiple class loaders does not automatically create a security sandbox. Module readability, exports, and opens remain JPMS's access control mechanisms; class loaders primarily determine how classes are loaded and identified at runtime.

## 7. Inspecting modules in a custom layer

After creating the layer, you can inspect the defined modules:

~~~java
ModuleLayer layer = controller.layer();

layer.modules().forEach(module ->
        System.out.println(module.getName()));

Module jsonModule =
        layer.findModule("com.example.codec.json")
                .orElseThrow();

System.out.println(jsonModule.getClassLoader());
~~~

Useful APIs:

- `modules()` returns the set of modules belonging to the current layer.
- `findModule(name)` searches for a module in the layer and can also find modules in parent layers according to API rules.
- `configuration()` returns the configuration associated with the layer.
- `parents()` returns the direct parent layers.
- `findLoader(moduleName)` finds the class loader mapped to a module in the layer.

If you want to inspect only the modules defined directly in the child layer, use `layer.modules()`; do not confuse it with all modules accessible through the parent hierarchy.

## 8. Controller and adjusting access permissions

`ModuleLayer.Controller` is returned when defining a layer. The controller provides operations such as:

- `layer()` gets the created layer.
- `addReads(source, target)` supplements readability.
- `addExports(source, packageName, target)` supplements package export permission.
- `addOpens(source, packageName, target)` opens a package for deep reflection.

For example, if a framework needs reflection into a plugin package and opening the package was not declared in advance in the descriptor, the controller can add that permission at runtime:

~~~java
Module source = pluginLayer.findModule("com.example.codec.json")
        .orElseThrow();

Module target = PluginFramework.class.getModule();

controller.addOpens(
        source,
        "com.example.codec.json",
        target);
~~~

Use the controller only when there is a specific runtime requirement. If access permission is a stable part of the plugin design, declare `exports` or `opens` in the module descriptor so the permission is expressed explicitly.

## 9. Common errors when creating layers

| Symptom | Common cause | What to check |
|---|---|---|
| `FindException` | Module finder cannot read module or module path is invalid | Check paths and JARs |
| `ResolutionException` | Missing dependency, module conflict, or invalid graph | Check `requires`, module names, and parent configuration |
| `LayerInstantiationException` | Cannot define modules in the layer per class loader/package configuration | Check split packages and class loader mapping |
| `ServiceConfigurationError` | Invalid provider or consumer module missing `uses` | Check `uses`, `provides`, and provider rules |
| Provider not found | Using the wrong layer or plugin does not declare `provides` | Use `ServiceLoader.load(layer, Service.class)` and check descriptors |
| `ClassCastException` despite same class name | Service API loaded as two different classes across different loaders/modules | Place shared API in the parent layer and share the same class identity |

A common design mistake is packaging the service API inside each plugin JAR. When each plugin loads its own copy of the API, the consumer may receive an object that is not assignable to the interface the host is using. Place the service API in the parent layer, export the required package, and have plugins `requires` that API module.

## 10. Plugin lifecycle and creating a new layer

ModuleLayer has no `close()` API to automatically unload all modules. When a plugin needs a version update, the common approach is to create a new layer from a new module finder/configuration, then route traffic to the new layer.

For old class loaders to be reclaimed by the garbage collector, the application must release references holding the layer, class loaders, modules, classes, service instances, threads, thread context class loaders, and plugin resources. Reclamation does not happen immediately and is not guaranteed at a specific point in time.

You cannot replace class definitions of a running module merely by calling `resolve()` again or `reload()` on ServiceLoader. To load another plugin version, create a new module layer and manage the lifecycle of the old layer.

## 11. Summary

`ModuleFinder` locates module metadata from the module path; `Configuration.resolve()` or `resolveAndBind()` builds the module graph; `ModuleLayer` defines that graph at runtime with specific parent relationships and class loaders.

To create a plugin layer, start from the parent layer's configuration, resolve root modules from the finder, then use `defineModulesWithOneLoader()` or `defineModulesWithManyLoaders()`. Use `ServiceLoader.load(layer, serviceType)` to discover providers in the layer. Place the shared service API in the parent layer so host and plugins share the same class identity, and explicitly manage layer lifecycle when updating plugins.

References:

- [ModuleFinder — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleFinder.html)
- [Configuration — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html)
- [ModuleLayer — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html)
- [ServiceLoader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html)