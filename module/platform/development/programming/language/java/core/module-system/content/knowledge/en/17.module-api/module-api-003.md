# ModuleLayer and the configuration API

The Java Platform Module System (JPMS) does more than describe dependencies in module-info.java. At runtime, Java also needs to determine which set of modules participates in the application, resolve dependencies among them, and define those modules in the JVM. The two central APIs for this work are **Configuration** and **ModuleLayer**.

Configuration represents the result of module resolution: which modules are selected, which dependencies are satisfied, and the read relationships among them. ModuleLayer brings that configuration into runtime, associates modules with class loaders, and creates parent-child relationships between module groups. These APIs are the foundation for building modular applications, loading plugins dynamically, and organizing multiple module groups within the same process.

## 1. Distinguishing Configuration and ModuleLayer

These two concepts often appear together but handle two different jobs:

- **Configuration** describes the resolved module graph. It contains ResolvedModules and read relationships between modules in the configuration.
- **ModuleLayer** is a set of modules already defined at runtime. Each runtime module is bound to a class loader according to the layer definition strategy.
- **ClassLoader** locates bytecode and defines classes when requested by the application. ModuleLayer does not mean all classes in the layer's modules have already been loaded.

Overview of the processing flow:

~~~text
Module path / plugin location
          |
          v
ModuleFinder locates modules
          |
          v
Configuration.resolve(...)
          |
          v
Resolved module graph
          |
          v
ModuleLayer.defineModules(...)
          |
          v
Runtime Module + ClassLoader
          |
          v
Classes loaded on demand
~~~

A module can appear in a Configuration without yet being defined in a new ModuleLayer. After the layer is created, the module already has a runtime Module object, but classes inside it are still typically loaded on demand.

Therefore, when debugging, you need to determine whether you are observing the resolved configuration, the runtime module, or loaded classes. These three states cannot substitute for one another.

## 2. ModuleFinder supplies input for the resolution process

**ModuleFinder** locates module descriptors from specified locations. It is commonly used to find modular JARs, exploded modules, or automatic modules on the module path.

Example:

~~~java
import java.lang.module.ModuleFinder;
import java.nio.file.Path;

ModuleFinder pluginFinder =
    ModuleFinder.of(Path.of("plugins"));
~~~

The statement above creates a finder that searches for modules in the plugins directory. If the directory contains modular JARs, the finder reads their descriptors to determine module names and directives. A JAR without module-info.class placed on the module path can be recognized as an automatic module under JPMS rules.

Some commonly used factory methods:

| API | Purpose |
| --- | --- |
| ModuleFinder.of(Path...) | Finds modules in the specified directories or JARs |
| ModuleFinder.ofSystem() | Finds modules belonging to the JDK runtime image |
| ModuleFinder.of() | Creates an empty finder, often used as one of the inputs to resolve |
| ModuleFinder.compose(...) | Combines multiple finders into a single finder |

You can look up a module by name and read its descriptor:

~~~java
var reference =
    pluginFinder.find("com.example.plugin");

if (reference.isPresent()) {
    System.out.println(reference.get().descriptor().name());
    System.out.println(reference.get().location());
}
~~~

ModuleFinder only helps locate modules and metadata. It does not create runtime modules, does not load implementation classes, and does not execute code inside the module.

## 3. Configuration represents the module resolution result

**Configuration** is the result of resolving root modules along with their required dependencies. It contains a set of ResolvedModule objects, each representing a resolved module in the configuration.

When launching a typical modular application, the Java launcher performs resolution based on the module path, selected root modules, and platform modules. When an application needs to load plugins at runtime, it can call the Configuration API directly.

Example:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleLayer parent = ModuleLayer.boot();

ModuleFinder finder =
    ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    parent.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.example.plugin")
    );
~~~

Meaning of the resolve parameters:

- **finder** is where new modules to resolve are searched before considering modules already in the parent configuration.
- **ModuleFinder.of()** is an empty finder for the supplementary search location after the parent configuration in this overload.
- **Set.of("com.example.plugin")** specifies the root modules the application wants to bring into the configuration.
- **parent.configuration()** provides the parent configuration, typically the configuration of the boot layer.

Resolution starts from the root modules. JPMS continues finding the modules they require directly or indirectly, checks dependencies, and builds read relationships. Modules that are neither in the root set nor required dependencies will not automatically be added to the configuration just because they are present in the plugins directory.

You can inspect the modules in the result:

~~~java
configuration.modules().forEach(resolved -> {
    System.out.println(resolved.name());
});
~~~

This list shows the modules belonging directly to the current Configuration. Modules already present in the parent configuration are referenced through the parent relationship, and do not necessarily appear as new modules in the child configuration.

## 4. ResolvedModule and dependency information

**ResolvedModule** represents a module selected in a Configuration. It provides access to the name, descriptor, ModuleReference, and resolved dependencies.

Example:

~~~java
configuration.modules().forEach(resolved -> {
    System.out.println("Name: " + resolved.name());
    System.out.println("Descriptor: " + resolved.reference().descriptor());
    System.out.println("Dependencies: " + resolved.reads());
});
~~~

Important information:

- **name()** returns the module name.
- **reference()** returns the ModuleReference of the located module.
- **configuration()** indicates the Configuration to which the ResolvedModule belongs.
- **reads()** indicates the modules that this module reads in the resolved configuration.

ResolvedModule is still information from the resolution process. It is not a runtime Module object and does not provide a class loader for loading classes.

You can inspect dependencies by name by iterating over the elements in reads(). When a dependency is not found or a module constraint cannot be satisfied, resolution fails before the layer is defined.

## 5. resolve and resolveAndBind

Configuration provides two commonly used resolution methods:

- **resolve(...)** locates the root modules along with dependencies declared with requires.
- **resolveAndBind(...)** performs resolution combined with service binding to find additional provider modules matching services used in the module graph.

Example using service binding:

~~~java
Configuration configuration =
    parent.configuration().resolveAndBind(
        pluginFinder,
        ModuleFinder.of(),
        Set.of("com.example.app")
    );
~~~

Suppose the application module declares:

~~~java
module com.example.app {
    requires com.example.plugin.api;
    uses com.example.plugin.api.PluginService;
}
~~~

And the plugin module declares:

~~~java
module com.example.plugin.csv {
    requires com.example.plugin.api;

    provides com.example.plugin.api.PluginService
        with com.example.plugin.csv.CsvPlugin;
}
~~~

When using resolveAndBind, the module system can find provider modules for services used by the module graph, based on modules discoverable in the finder and parent configurations. The provider's dependencies are also included in the resolution process.

Service binding only determines which provider modules participate in the configuration. It does not mean the provider's constructor has run or that all implementation classes have been loaded. Obtaining and using providers is still typically done via ServiceLoader at runtime.

Choose resolve when you only need the root modules and requires dependencies. Choose resolveAndBind when you want the module system to automatically expand the configuration with modules providing matching services.

## 6. Multiple parent Configurations

A Configuration can be resolved against multiple parent configurations. This case is useful when an application has independent module groups already resolved in different parent layers.

The static Configuration API accepts a list of parent configurations:

~~~java
Configuration configuration =
    Configuration.resolve(
        finderBefore,
        List.of(parentA.configuration(),
                parentB.configuration()),
        finderAfter,
        Set.of("com.example.plugin")
    );
~~~

Where:

- **finderBefore** is used to look up new modules before considering the parent configurations.
- The parent list provides existing modules and their read relationships.
- **finderAfter** is the supplementary search source after the parent configurations.
- The roots set specifies the root modules to resolve.

When defining the corresponding ModuleLayer, you must pass parent layers matching the list of parent configurations. The layer's parent structure must be consistent with the configuration used for resolution; you cannot arbitrarily pair a Configuration with non-corresponding layers.

For typical applications, a single parent—the boot layer—is usually sufficient. Only use multiple parents when the architecture genuinely has multiple parent module groups that need to be shared.

## 7. What is ModuleLayer?

**ModuleLayer** represents a set of modules defined in the JVM. It combines a resolved Configuration with a class loader strategy and parent layers.

Layers form a hierarchical structure:

~~~text
Boot ModuleLayer
       |
       v
Application / Plugin Layer
       |
       v
Child Plugin Layer
~~~

A layer can contain application modules, plugin modules, or dynamically loaded modules. A child layer can read modules in parent layers according to the resolved module graph.

Commonly used APIs:

| API | Role |
| --- | --- |
| ModuleLayer.boot() | Gets the application's boot layer |
| ModuleLayer.empty() | Gets the empty layer, often used as a starting point for an independent configuration |
| parents() | Returns direct parent layers |
| modules() | Returns modules defined directly in the layer |
| configuration() | Gets the Configuration used to create the layer |
| findModule(name) | Finds a module by name in the layer hierarchy |
| findLoader(name) | Finds the class loader associated with a module in the layer hierarchy |

Example observing the boot layer:

~~~java
ModuleLayer boot = ModuleLayer.boot();

System.out.println("Module count: " + boot.modules().size());
System.out.println("Parents: " + boot.parents());

boot.modules().forEach(module -> {
    System.out.println(module.getName());
});
~~~

modules() shows the modules belonging directly to the layer under inspection. If you want to find modules visible through the parent structure, use findModule(name) by module name.

## 8. Defining a layer with a shared ClassLoader

Once a Configuration has resolved successfully, the application can define the modules into a new layer.

The simplest approach for a group of plugins is **defineModulesWithOneLoader**:

~~~java
ModuleLayer.Controller controller =
    parent.defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer pluginLayer = controller.layer();
~~~

This API creates a new class loader to define the modules in the configuration. The new modules in the layer share that loader; the passed-in loader serves as the parent to support delegation.

Suitable when:

- Plugin modules need to share classes within the same group.
- Modules have relatively tight dependency relationships.
- Separate loader isolation per module is not needed.
- You want to simplify sharing APIs and data types between plugins.

Note that the **parentLoader** parameter is the parent of the newly created loader. It does not mean the plugin modules are defined directly by the system class loader.

After creating the layer, you can verify:

~~~java
System.out.println(
    pluginLayer.findModule("com.example.plugin").isPresent()
);

ClassLoader pluginLoader =
    pluginLayer.findLoader("com.example.plugin");

System.out.println(pluginLoader);
~~~

A module has been defined in the layer when findModule finds it. findLoader returns the loader associated with the module; this operation does not load all classes in the module.

## 9. Defining a layer with multiple ClassLoaders

If you want each new module to have its own loader, use **defineModulesWithManyLoaders**:

~~~java
ModuleLayer.Controller controller =
    parent.defineModulesWithManyLoaders(
        configuration,
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer pluginLayer = controller.layer();
~~~

The API creates one class loader for each module in the configuration. The loaders are configured with appropriate parent relationships to support delegation and module readability.

This approach is useful when modules need separate class-loading scopes, such as plugins with different internal dependencies. However, the shared API between them must be clearly designed. If each plugin packages a copy of the same interface, classes with the same name defined by different loaders are still different types in the JVM.

Comparison of the two approaches:

| Criterion | One loader | Many loaders |
| --- | --- | --- |
| Number of new loaders | One shared loader for modules in the configuration | One loader per module |
| Sharing classes within layer | More convenient when sharing a loader | Must rely on module relationships and delegation |
| Class-loading isolation | Less separated | Clearer per-module separation |
| Complexity | Usually simpler | Requires more careful management of class identity and shared APIs |
| Best suited for | Tightly cooperating module groups | Modules needing separate loader scopes |

Neither option is automatically safer. Choose a strategy based on dependencies, how APIs are shared, and the plugin lifecycle of the application.

## 10. Mapping modules to ClassLoaders manually

When one-loader or many-loaders does not fit the architecture, you can use **defineModules** with a function mapping module names to class loaders.

~~~java
ModuleLayer.Controller controller =
    parent.defineModules(
        configuration,
        moduleName -> loaderFor(moduleName)
    );

ModuleLayer pluginLayer = controller.layer();
~~~

The loaderFor function is application logic and must return an appropriate ClassLoader for each module name being defined. This approach lets you group modules into loaders according to a custom policy.

You can use the static overload to supply multiple parent layers:

~~~java
ModuleLayer.Controller controller =
    ModuleLayer.defineModules(
        configuration,
        List.of(parent),
        moduleName -> loaderFor(moduleName)
    );
~~~

When mapping loaders manually, ensure that:

- Every module in the configuration is bound to an appropriate loader.
- Modules that need to share an API use the same API class definition.
- Parent loaders support finding dependencies already present in parent layers.
- Two incompatible API class definitions are not created across plugins.
- Loader lifecycles are managed alongside plugin lifecycles.

This API provides higher control but also requires a thorough understanding of delegation and class identity. It should only be used when specific requirements cannot be met by the built-in loader strategies.

## 11. ModuleLayer.Controller and permission to adjust runtime modules

The defineModules APIs return **ModuleLayer.Controller**. The controller provides a reference to the newly created layer and several operations for adjusting access relationships at runtime.

Main operations include:

- **layer()** returns the newly defined ModuleLayer.
- **addReads(source, target)** adds a read edge from the source module to the target module.
- **addExports(source, packageName, target)** exports a package of the source module to the target module.
- **addOpens(source, packageName, target)** opens a package of the source module for deep reflection from the target module.

Example:

~~~java
ModuleLayer.Controller controller =
    parent.defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer pluginLayer = controller.layer();

Module source =
    pluginLayer.findModule("com.example.plugin").orElseThrow();

Module target =
    parent.findModule("com.example.plugin.api").orElseThrow();

controller.addReads(source, target);
~~~

In a proper design, requires dependencies should be declared in module-info.java. Controller is suitable for runtime scenarios that need to add read, export, or open edges after the layer has already been defined.

Controller is an object with privileges to modify modules belonging to the created layer. Only pass it to components that actually need this privilege; do not distribute permission to mutate the module graph arbitrarily.

## 12. Complete example: loading a plugin with ModuleLayer

Suppose the application has an API module in the boot layer:

~~~java
module com.example.plugin.api {
    exports com.example.plugin.api;
}
~~~

Service interface:

~~~java
package com.example.plugin.api;

public interface PluginService {
    String name();
    void execute();
}
~~~

The plugin module is packaged as a JAR in the plugins directory:

~~~java
module com.example.plugin.csv {
    requires com.example.plugin.api;

    provides com.example.plugin.api.PluginService
        with com.example.plugin.csv.CsvPlugin;
}
~~~

The application has started and wants to load the plugin:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;

ModuleLayer parent = ModuleLayer.boot();

ModuleFinder finder =
    ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    parent.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.example.plugin.csv")
    );

ModuleLayer.Controller controller =
    parent.defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer pluginLayer = controller.layer();

ServiceLoader<PluginService> services =
    ServiceLoader.load(pluginLayer, PluginService.class);

for (PluginService service : services) {
    System.out.println(service.name());
    service.execute();
}
~~~

How the workflow operates:

1. The API module is already in the parent layer so the application and plugin share the same interface definition.
2. ModuleFinder finds the plugin JAR in the plugins directory.
3. Configuration.resolve resolves the plugin module and its dependencies.
4. defineModulesWithOneLoader creates a child layer and loader for the new module.
5. ServiceLoader.load(pluginLayer, PluginService.class) locates providers in the specified layer and parent layers.
6. When iterating over and using providers, implementation classes are loaded and instantiated on demand.

The example assumes the plugin has a valid descriptor, the API dependency is already in the parent layer, and the root module has the exact name. In a real application, you must handle missing plugin directories, unfound modules, incompatible dependencies, or provider instantiation failures.

## 13. Plugin lifecycle and manageability

ModuleLayer does not provide an API to unload an individual module. Dropping references to the layer and associated class loaders can allow the garbage collector to reclaim them when no live references remain, but that only happens once all references to classes, instances, threads, callbacks, static state, and loaders have been released.

A plugin can retain references from:

- Running threads or executors.
- Thread context class loaders.
- Listeners or callbacks registered on longer-lived objects.
- Static collections or caches in a parent layer.
- Plugin instances held in an application registry.

If these references still exist, the plugin's class loader and classes may not be reclaimed.

Therefore, when designing a plugin lifecycle, include steps to close resources, stop threads, unregister listeners, clear registries, and release references. Do not treat creating a new ModuleLayer as an automatic mechanism to unload old plugins.

ModuleLayer is also not a security sandbox. Module encapsulation and class loaders help manage dependencies, readability, and class-loading scopes, but they do not isolate untrusted code from the process or operating system resources.

## 14. Common errors when using Configuration and ModuleLayer

**FindException**

ModuleFinder cannot locate a module, the descriptor is invalid, or the module path location is incorrect. Check the directory, module name, and JAR contents using jar --describe-module.

**ResolutionException**

A requires dependency is not found, the module graph has conflicts, or resolution constraints cannot be satisfied. Check the root modules, dependencies, and parent Configurations.

**LayerInstantiationException**

Configuration resolved, but the layer cannot be defined under the chosen loader strategy. Check package relationships, duplicate modules, or class loader mapping issues.

**Module present in Configuration but class not found**

Configuration only describes the module graph. Check whether ModuleLayer has been created, the loader bound to the module, and whether the JAR contains the needed class.

**ServiceLoader does not find provider**

Check whether the provider module provides the right service, the consumer module uses it, the provider participates in the configuration, and ServiceLoader uses the right layer. If you need automatic provider discovery during resolution, consider resolveAndBind.

**ClassCastException between plugins**

The same API may have been defined by multiple loaders. Place the shared API in a parent layer and have plugins requires that API module.

**Plugin not reclaimed after dropping layer**

Look for live references to instances, classes, threads, context class loaders, listeners, or static caches. Dropping only the reference to ModuleLayer is not enough to guarantee the loader can be reclaimed.

## 15. Tools for observing modules and layers

Use jar to inspect a plugin's descriptor:

~~~bash
jar --describe-module --file plugins/com.example.plugin.jar
~~~

Use the Java launcher to view the application's module resolution:

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

In code, you can print layer information:

~~~java
System.out.println("Layer: " + pluginLayer);
System.out.println("Configuration: " + pluginLayer.configuration());
System.out.println("Parents: " + pluginLayer.parents());

pluginLayer.modules().forEach(module -> {
    System.out.println("Module: " + module.getName());
    System.out.println("Loader: " + module.getClassLoader());
});
~~~

Observation sources have distinct roles:

- **jar --describe-module** shows the artifact's descriptor.
- **Configuration.modules()** shows modules participating in the resolved configuration.
- **ModuleLayer.modules()** shows modules defined directly in the layer.
- **ModuleLayer.findModule()** helps find a module by name in the layer hierarchy.
- **ModuleLayer.findLoader()** shows the class loader bound to a module.
- **-Xlog:class+load=info** shows which classes are actually loaded.

When you need to determine whether a module is missing, resolution failed, or class loading failed, compare results at the corresponding stage.

## 16. Design principles

- Use ModuleFinder to specify module sources and Configuration to resolve the module graph.
- Choose root modules explicitly; modules present in a finder are not automatically added to the configuration.
- Use resolve for requires dependencies and resolveAndBind when providers need to be discovered via service binding.
- Use the boot layer as parent when plugins need to share API modules already in the application.
- Use defineModulesWithOneLoader for module groups that need to share a loader.
- Use defineModulesWithManyLoaders when separate loaders per module are needed.
- Only use a custom loader mapping function when specific architectural requirements exist.
- Keep shared APIs in a parent layer to avoid class identity conflicts.
- Use Controller purposefully to adjust reads, exports, or opens at runtime.
- Manage threads, listeners, caches, and references so plugins can end their lifecycle.
- Do not treat ModuleLayer as a sandbox or an automatic unloading mechanism.

When you understand Configuration, ResolvedModule, ModuleLayer, and Controller, you can control dependency resolution, create runtime layers, and load plugins in a structured way. This is the core API group for building extensible modular applications while keeping the module graph, class loaders, and access permissions observable and manageable.
