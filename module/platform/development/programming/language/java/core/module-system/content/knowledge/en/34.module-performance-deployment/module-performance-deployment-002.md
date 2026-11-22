# Class Loading in One-Loader and Many-Loader Layers

> Scope: Java Platform Module System (JPMS) and **ModuleLayer**. A module layer combines a resolved module configuration with how modules are defined and loaded by class loaders. Java provides two common ways to create a layer: using a single shared class loader for the modules, or creating a separate class loader for each module.

## Objectives

After this lesson, you will be able to:

- Explain the relationship between **ModuleLayer**, **Configuration**, **Module**, and **ClassLoader**.
- Distinguish how classes are loaded by **defineModulesWithOneLoader** and **defineModulesWithManyLoaders**.
- Create a child layer from a module path for plugins.
- Retrieve a module's class loader using **ModuleLayer.findLoader**.
- Understand class identity, parent delegation, and readability/exports boundaries.
- Choose an appropriate loader strategy for modular applications and plugins.
- Troubleshoot common class loading errors when using multiple layers or multiple loaders.

## 1. What Is ModuleLayer?

**ModuleLayer** represents a layer of modules that have been resolved and defined at runtime. A layer contains the modules belonging to a **Configuration** and can have one or more parent layers.

When the JVM starts, Java creates the boot layer containing the platform modules and the modules resolved for the application. You can obtain this layer with:

~~~java
ModuleLayer bootLayer = ModuleLayer.boot();
~~~

An application can create additional child layers to load plugins or another group of modules after the program has started.

A layer is not a class loader. A layer manages module relationships and maps modules to class loaders. How that mapping works depends on the method used to define the layer.

Key components:

| Component | Role |
|---|---|
| **Configuration** | Describes the resolved module graph: which modules are present and which dependencies are satisfied |
| **ModuleLayer** | Represents a layer containing modules defined from a configuration |
| **Module** | Runtime representation of a specific module |
| **ClassLoader** | Loads classes/resources; a single loader can define classes belonging to one or more modules depending on how the layer is created |
| **ModuleLayer.Controller** | Provides authority to adjust module relationships in the created layer, such as adding reads, exports, or opens when needed |

The module system and class loading work together. The class loader is responsible for finding and defining classes; the module system enforces readability, exports, and opens between modules.

## 2. How Do Configuration and ModuleLayer Differ?

**Configuration** answers the question: which module graph has been resolved? It holds information about modules and dependencies, but does not itself create class loaders or load classes.

**ModuleLayer** uses a configuration to define modules at runtime and associate them with class loaders.

General workflow:

1. Find modules using **ModuleFinder**.
2. Resolve dependencies to create a **Configuration**.
3. Choose how to define the layer: one-loader, many-loaders, or custom loader mapping.
4. Obtain the layer from **ModuleLayer.Controller**.
5. Load classes or locate service providers in the layer.

This can be visualized as:

~~~text
ModuleFinder
    |
    v
Configuration.resolve(...)
    |
    v
Resolved module graph
    |
    v
ModuleLayer.defineModulesWith...
    |
    +---- one-loader: one loader for the modules in the layer
    |
    +---- many-loaders: one loader for each module
    |
    v
ModuleLayer
    |
    v
Class loading / ServiceLoader / reflection
~~~

Key point: **resolving the module graph** and **defining class loaders** are two separate steps. If the configuration cannot resolve dependencies, a valid layer cannot be created yet.

## 3. What Is a One-Loader Layer?

Creating a layer with **ModuleLayer.defineModulesWithOneLoader** defines all modules in the configuration into a single new class loader.

Example:

~~~java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithOneLoader(
                configuration,
                List.of(ModuleLayer.boot()),
                ClassLoader.getSystemClassLoader()
        );

ModuleLayer layer = controller.layer();
~~~

Meaning:

- **configuration** is the resolved configuration for the modules to load.
- **List.of(ModuleLayer.boot())** specifies the boot layer as the parent.
- **ClassLoader.getSystemClassLoader()** is the parent loader of the loader created for the layer.
- **controller.layer()** returns the new layer.

In a one-loader layer, modules are defined by a shared loader. This can reduce the number of class loaders to manage and simplify the class loading structure across a group of related modules.

However, **a shared loader does not mean the modules are merged into a single module**. Each module still retains its own descriptor, module name, package ownership, readability, and exports. Having classes defined by the same loader does not automatically grant package access between modules.

One-loader is suitable when the modules form a cohesive deployment unit, need to share a class loading namespace, and do not require per-module loader isolation.

## 4. What Is a Many-Loader Layer?

Creating a layer with **ModuleLayer.defineModulesWithManyLoaders** creates a separate class loader for each module in the configuration.

Example:

~~~java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithManyLoaders(
                configuration,
                List.of(ModuleLayer.boot()),
                ClassLoader.getSystemClassLoader()
        );

ModuleLayer layer = controller.layer();
~~~

Each module has its own loader. The created loaders use the specified parent loader; accessing other modules must still follow the module graph and the loader delegation mechanism created by Java.

Many-loaders is useful when an application wants to separate class loading per module, such as a plugin system with many independent modules. It creates clearer loader boundaries, helps detect wrong assumptions about class identity early, and avoids having all classes in the layer share a single defining loader.

In return, multiple loaders increase the number of objects to manage and can make debugging, resource lookup, reflection, or API sharing more complex. You should not assume many-loaders is always faster or safer; measure against your actual application.

## 5. Comparing One-Loader and Many-Loaders

| Criterion | One-loader | Many-loaders |
|---|---|---|
| Number of loaders for modules in configuration | One shared loader | One loader per module |
| Class loader boundary | Shared within the layer | Separated per module |
| Module descriptor and exports | Still enforced per module | Still enforced per module |
| Loader management overhead | Usually lower | Can be higher with many modules |
| Class loading isolation | Less between modules in the same layer | Clearer per module |
| Common use cases | Cohesive deployment group of modules | Plugins or modules needing separate loaders |

Loader choice does not replace module design. Whether using one-loader or many-loaders, modules still need to declare dependencies with **requires**, publish APIs with **exports**, and open packages for reflection with **opens** when needed.

## 6. Creating a Configuration and Child Layer from a Plugin Directory

Suppose an application has a **plugins** directory containing modular JARs:

~~~text
application/
├── app/
└── plugins/
    ├── com.acme.plugin.alpha.jar
    └── com.acme.plugin.beta.jar
~~~

Each plugin is an explicit module and has a module descriptor. For example, module alpha:

~~~java
module com.acme.plugin.alpha {
    requires com.acme.plugin.api;
}
~~~

The API module should reside in the boot layer or a parent layer that plugins can read. This ensures the application and plugins share the same API definition rather than loading two copies of an interface with different class identities.

Creating a configuration for the plugins:

~~~java
Path pluginPath = Path.of("plugins");

ModuleFinder finder = ModuleFinder.of(pluginPath);

Configuration parentConfiguration =
        ModuleLayer.boot().configuration();

Configuration pluginConfiguration =
        parentConfiguration.resolve(
                finder,
                ModuleFinder.of(),
                Set.of("com.acme.plugin.alpha", "com.acme.plugin.beta")
        );
~~~

Explanation:

- **ModuleFinder.of(pluginPath)** finds modules in the plugin directory.
- **ModuleLayer.boot().configuration()** retrieves the boot layer's configuration as the parent configuration.
- **resolve** creates a new configuration from the discovered modules and required dependencies.
- The roots set specifies the plugin modules to load.

If a plugin has a dependency on another module in the same directory, the resolver attempts to resolve that dependency from the module finder. If a dependency is missing or a descriptor is invalid, the resolve step fails before creating the layer.

## 7. Creating a Child Layer with One-Loader or Many-Loaders

Once you have **pluginConfiguration**, choose one of the two approaches.

### Using One-Loader

~~~java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithOneLoader(
                pluginConfiguration,
                List.of(ModuleLayer.boot()),
                ClassLoader.getSystemClassLoader()
        );

ModuleLayer pluginLayer = controller.layer();
~~~

Plugin modules in the configuration are defined by the same loader. This can be used when plugins need to share class loading and be managed as a group.

### Using Many-Loaders

~~~java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithManyLoaders(
                pluginConfiguration,
                List.of(ModuleLayer.boot()),
                ClassLoader.getSystemClassLoader()
        );

ModuleLayer pluginLayer = controller.layer();
~~~

Each plugin module has its own loader. This is a suitable choice when you want to isolate class loading per module.

Do not create both layers for the same configuration in a real application just to pick arbitrarily. Decide the strategy upfront based on relationships between plugins, how APIs are shared, and isolation requirements.

## 8. Finding a Module's Class Loader in a Layer

After creating a layer, use **findLoader** to get the loader associated with a module:

~~~java
ClassLoader loader =
        pluginLayer.findLoader("com.acme.plugin.alpha");
~~~

Or obtain it from the Module object:

~~~java
Module module =
        pluginLayer.findModule("com.acme.plugin.alpha")
                   .orElseThrow();

ClassLoader loader = module.getClassLoader();
~~~

For modules defined by the bootstrap loader, **Module.getClassLoader()** may return **null**. For plugin modules defined by a layer's loader, you normally receive the corresponding loader.

You can load a class by name using the retrieved loader:

~~~java
Class<?> pluginClass =
        Class.forName(
                "com.acme.plugin.alpha.PluginMain",
                true,
                pluginLayer.findLoader("com.acme.plugin.alpha")
        );
~~~

Successfully loading a class does not mean every access operation is allowed. Module readability, exports, opens, constructor visibility, and reflection rules still apply.

If the application needs to invoke plugin APIs, use interfaces/service APIs exported from a shared API module. Avoid relying on internal class names or reflecting into unopened packages.

## 9. Class Identity and ClassCastException Errors

In the JVM, class identity is tied to the binary name of the class and its defining class loader. Therefore, two classes with the same name defined by two different loaders are two distinct runtime types.

Example:

- Loader A defines **com.acme.api.Plugin**.
- Loader B also defines another copy of **com.acme.api.Plugin**.
- An object implementing the interface version defined by Loader B cannot be cast to the interface version defined by Loader A.

This can cause the error:

~~~text
ClassCastException: com.acme.api.Plugin cannot be cast to com.acme.api.Plugin
~~~

The class name in the message is identical, but the defining loaders differ.

To prevent this error:

1. Place shared interfaces/APIs in the boot layer or a parent layer.
2. Have plugins declare **requires** on the shared API module.
3. Do not bundle duplicate copies of the API inside each plugin if they need to interact with the host.
4. Use the layer's loader to load implementations, while keeping API types in the parent layer.
5. Inspect defining loaders when debugging.

Inspection example:

~~~java
System.out.println(type.getClassLoader());
System.out.println(type.getModule());
~~~

For an object:

~~~java
System.out.println(plugin.getClass().getClassLoader());
System.out.println(plugin.getClass().getModule());
~~~

Comparing both the module and the loader helps determine which layer/module an object belongs to.

## 10. Readability, Exports, and Class Loader Are Three Distinct Concerns

When one module needs to use a type from another module, distinguish:

- **Class loading**: the loader finds and defines bytecode.
- **Readability**: whether the source module can read the module containing the type, typically declared with **requires**.
- **Exports**: whether the target module exports the package containing the type to the source module.

If the class loader finds the class, yet the module cannot read the module containing the class or the package is not exported, access can still fail.

Example:

~~~java
module com.acme.plugin.api {
    exports com.acme.plugin.api;
}
~~~

Plugin:

~~~java
module com.acme.plugin.alpha {
    requires com.acme.plugin.api;
}
~~~

The host or another module wanting to call the API must have the appropriate readability relationship. Internal unexported packages do not become public API simply by using one-loader.

For deep reflection, the target module may need to **opens** the package to the module performing reflection. **exports** is primarily for normal compile/runtime access to public types; **opens** serves deep reflection.

## 11. Using ServiceLoader with ModuleLayer

If plugins provide implementations of a service, use **ServiceLoader** instead of assembling class names manually and calling reflection.

API module:

~~~java
module com.acme.plugin.api {
    exports com.acme.plugin.api;
}
~~~

Service interface:

~~~java
package com.acme.plugin.api;

public interface Plugin {
    String name();
    void start();
}
~~~

Provider module:

~~~java
module com.acme.plugin.alpha {
    requires com.acme.plugin.api;

    provides com.acme.plugin.api.Plugin
        with com.acme.plugin.alpha.AlphaPlugin;
}
~~~

After creating the plugin layer, locate providers in the layer:

~~~java
ServiceLoader<Plugin> plugins =
        ServiceLoader.load(pluginLayer, Plugin.class);

for (Plugin plugin : plugins) {
    System.out.println(plugin.name());
    plugin.start();
}
~~~

The **ServiceLoader.load(layer, service)** overload locates providers in the specified layer and its parent layers. The module containing the call must also declare **uses** for the service when the caller is an explicit named module.

If plugin modules are created in a child layer, providers must be resolved into that layer or an appropriate parent layer. Simply placing a JAR in the plugin directory is not enough if the module finder, configuration, or roots do not include the module in the layer.

## 12. Parent Loader and Parent Layer

When creating a layer, distinguish **parent layer** and **parent class loader**:

- The parent layer determines module configuration inheritance and the inherited module graph.
- The parent class loader is the loader that the new loader uses as its parent in the class loading hierarchy.

The two concepts are related, not interchangeable. A module can read modules from a parent layer according to the configuration, while class loading still goes through the corresponding loaders.

Example using the boot layer as parent:

~~~java
List<ModuleLayer> parents = List.of(ModuleLayer.boot());
ClassLoader parentLoader = ClassLoader.getSystemClassLoader();
~~~

Choose a parent loader suited to the runtime environment. In container applications or plugin environments with custom class loaders, do not assume the system class loader is always the right choice. Identify which loader sees the shared API and platform libraries that plugins require.

## 13. When Should You Choose One-Loader or Many-Loaders?

Choose **one-loader** when:

- Modules in the layer form a cohesive deployment unit.
- You want to reduce the number of loaders to manage.
- Per-module class loading separation is not needed.
- APIs and dependencies among the modules are clearly designed.

Choose **many-loaders** when:

- Each module/plugin needs its own loader.
- You want to separate class loading to limit conflicts between modules.
- You need to manage multiple independent plugins and can control their dependencies.
- You can accept the loader management overhead and added complexity.

Neither approach is a security sandbox. Separate class loaders do not replace plugin vetting processes, restricting system permissions, verifying artifact provenance, or process isolation when running untrusted code.

Performance depends on module count, class count, dependency size, class loading frequency, and how the application uses reflection/services. Measure on a real workload instead of concluding that one-loader or many-loaders is always faster.

## 14. Common Errors and How to Handle Them

| Symptom | Common Cause | How to Handle |
|---|---|---|
| **FindException** during resolve | Missing module or unresolvable dependency | Check ModuleFinder, module path, roots, and requires directives |
| **ResolutionException** | Invalid module graph, possibly due to split packages or other conflicts | Read module/package names in the error; inspect descriptors and package inventory |
| **LayerInstantiationException** | Cannot define modules in the layer with the chosen loader mode | Check configuration, parent layers, and package/loader conditions |
| **ClassNotFoundException** | Wrong class name or using a loader not associated with the target module | Use the exact fully qualified name and retrieve the loader via findLoader |
| **NoClassDefFoundError** | Runtime dependency not found or class initialization failed | Check module graph, dependencies, and root cause |
| **ClassCastException** despite identical class names | Two copies of the class defined by two different loaders | Place shared API in a parent layer and avoid bundling duplicate APIs |
| **IllegalAccessError** | Missing readability or package is not exported | Check requires, exports, and the module graph |
| Reflection blocked | Package is not opened to the module performing deep reflection | Use opens in the descriptor or appropriate opening configuration |
| Provider not found via ServiceLoader | Provider not resolved into the layer or missing uses/provides | Check module descriptors, roots, layer, and use the load(layer, service) overload |

Debugging workflow:

1. Print the module names and configuration being used.
2. Verify that the module finder locates the right plugin JARs.
3. Confirm the configuration resolves with the right roots.
4. Identify the parent layer and how loaders are created.
5. Use **findLoader** to obtain the module's loader.
6. Print **Class.getClassLoader()** and **Class.getModule()** of the failing type.
7. Check requires, exports, and opens.
8. If using services, check uses/provides and look up providers in the right layer.

## 15. Takeaways

- **ModuleLayer** holds modules that have been resolved and defined at runtime.
- **Configuration** describes the module graph; it does not create class loaders by itself.
- **defineModulesWithOneLoader** uses a single shared loader for modules in the configuration.
- **defineModulesWithManyLoaders** creates a separate loader for each module.
- A shared loader does not merge modules; readability, exports, and opens are still checked.
- Classes with the same name but different defining loaders are two distinct runtime types.
- Placing shared APIs in a parent layer lets the host and plugins share the same class identity.
- Use **ModuleLayer.findLoader** to retrieve a module's loader.
- Use **ServiceLoader.load(layer, service)** when locating providers in a plugin layer.
- One-loader and many-loaders are architectural choices; measure performance and test class identity on real workloads.

## References

- [ModuleLayer — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html)
- [Configuration — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html)
- [ClassLoader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html)
- [ServiceLoader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
