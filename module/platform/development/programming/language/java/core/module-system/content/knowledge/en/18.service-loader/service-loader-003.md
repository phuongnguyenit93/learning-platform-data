# ServiceLoader.load with ModuleLayer

## Objectives

After this lesson, you will be able to explain how Java locates service providers within a module layer, configure the three roles of API, consumer, and provider with JPMS, and load providers from a plugin directory at runtime using ServiceLoader.

## 1. Why combine ServiceLoader with ModuleLayer?

ServiceLoader is Java's Service Provider Interface (SPI) mechanism. An application depends on a service interface, while other modules provide classes implementing that interface. The consumer knows only the service type; it does not need to depend directly on each provider.

The Java Platform Module System (JPMS) describes these relationships in module descriptors:

- The module defining the API exports the package containing the interface using exports.
- The module using the service declares uses.
- The module providing an implementation declares provides ... with ....

When all modules are present at startup, providers can be resolved into the boot layer. However, in plugin-based applications, we often want to discover and load provider modules from a directory after the application has already started. ModuleLayer allows creating a new layer of modules based on a Configuration and one or more parent layers.

The ServiceLoader.load(ModuleLayer, Class) overload connects these two mechanisms: it searches for providers of the service type in the specified layer and its parent layers. Therefore, an application can load plugins layer by layer without adding the plugin modules to the process's module path upfront.

## 2. Three components of the example

We will build a greeting service with three modules:

| Module | Role | Responsibility |
|---|---|---|
| com.acme.greeting.api | Service API | Declare and export GreetingService |
| com.acme.greeting.app | Consumer | Declare uses, create the layer, and call ServiceLoader |
| com.acme.greeting.vi | Provider | Implement GreetingService and declare provides |

At runtime, the API and application reside in the boot layer. The provider is packaged as a modular JAR in the plugins directory and loaded into a child layer.

The source structure can be organized as follows:

~~~text
src/
  com.acme.greeting.api/
    module-info.java
    com/acme/greeting/api/GreetingService.java
  com.acme.greeting.app/
    module-info.java
    com/acme/greeting/app/Main.java
  com.acme.greeting.vi/
    module-info.java
    com/acme/greeting/vi/VietnameseGreetingService.java

mods/
  com.acme.greeting.api.jar
  com.acme.greeting.app.jar

plugins/
  com.acme.greeting.vi.jar
~~~

The key point is that the provider JAR is in plugins, not in mods when launching the application. Because of this, the provider is resolved into the new layer instead of the boot layer.

## 3. Declaring the API module

The module-info.java file for the API module:

~~~java
module com.acme.greeting.api {
    exports com.acme.greeting.api;
}
~~~

The service interface:

~~~java
package com.acme.greeting.api;

public interface GreetingService {
    String greet(String name);
}
~~~

The package containing the interface must be exported so that the consumer and provider can reference the GreetingService type. This is the shared contract type across modules; the consumer does not need to know the concrete implementation class name.

## 4. Declaring the provider module

The module-info.java file for the provider:

~~~java
module com.acme.greeting.vi {
    requires com.acme.greeting.api;

    provides com.acme.greeting.api.GreetingService
        with com.acme.greeting.vi.VietnameseGreetingService;
}
~~~

The implementation class:

~~~java
package com.acme.greeting.vi;

import com.acme.greeting.api.GreetingService;

public final class VietnameseGreetingService implements GreetingService {

    public VietnameseGreetingService() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

The provider requires the API module because it implements the interface declared there. The provides directive registers the implementation class for the service type. With this registration, the package containing the provider class does not need to be exported to the consumer just for ServiceLoader to locate and instantiate the provider.

The provider module must be packaged as a module that ModuleFinder can discover, typically a modular JAR containing module-info.class. The plugin directory should not contain a duplicate copy of the API module if the API already resides in a parent layer.

## 5. Declaring the consumer module

The module-info.java file for the application:

~~~java
module com.acme.greeting.app {
    requires com.acme.greeting.api;

    uses com.acme.greeting.api.GreetingService;
}
~~~

The uses directive is the essential declaration on the consumer side. The module containing the code that calls ServiceLoader must declare that it uses that service type. If uses is missing in a named module, the service loading call may fail with IllegalCallerException.

The consumer depends only on the API. It does not need to declare requires com.acme.greeting.vi, because the provider will be discovered dynamically when creating the layer.

## 6. Creating a new layer and loading the provider

In Main.java, we locate the plugin module, resolve a configuration based on the boot layer, create a child layer, and then pass that layer to ServiceLoader:

~~~java
package com.acme.greeting.app;

import com.acme.greeting.api.GreetingService;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.ServiceLoader;
import java.util.Set;

public class Main {

    public static void main(String[] args) {
        Path pluginDirectory = Paths.get(
            args.length == 0 ? "plugins" : args[0]
        );

        // Find modules located in the plugin directory.
        ModuleFinder pluginFinder = ModuleFinder.of(pluginDirectory);

        // Specify the provider module to include in the new layer.
        Set<String> roots = Set.of("com.acme.greeting.vi");

        // Resolve the provider and its dependencies.
        // Dependencies already present in the boot layer are taken from the parent layer.
        Configuration configuration = ModuleLayer.boot()
            .configuration()
            .resolve(pluginFinder, ModuleFinder.of(), roots);

        // Create a child layer. New modules share a single class loader.
        ModuleLayer pluginLayer = ModuleLayer.defineModulesWithOneLoader(
            configuration,
            List.of(ModuleLayer.boot()),
            ClassLoader.getSystemClassLoader()
        ).layer();

        // Find service providers in pluginLayer and its parent layers.
        ServiceLoader<GreetingService> services =
            ServiceLoader.load(pluginLayer, GreetingService.class);

        // Providers are instantiated as we iterate through the results.
        services.forEach(service ->
            System.out.println(service.greet("Java"))
        );
    }
}
~~~

The steps mean the following:

1. ModuleFinder.of(pluginDirectory) searches for modules in the plugin directory. In this example, the directory contains the JAR for com.acme.greeting.vi.
2. roots specifies the root module to resolve. The fact that ModuleFinder finds a JAR does not mean the module is automatically added to the layer; the module must belong to the graph resolved from the roots.
3. Configuration.resolve(...) resolves the module graph. The boot layer's configuration is the parent configuration; pluginFinder supplies new modules, while ModuleFinder.of() as the second argument is an additional finder searched after the first finder.
4. ModuleLayer.defineModulesWithOneLoader(...) defines the resolved modules in the child layer. The new layer has the boot layer as its parent and uses a single shared class loader for the new modules.
5. ServiceLoader.load(pluginLayer, GreetingService.class) looks for providers in pluginLayer and its parent layers. Iterating over the ServiceLoader triggers the instantiation of the discovered providers.

If there are multiple independent plugin modules, add each module's name to roots. If a provider depends on another module located in the plugin directory, those dependencies will be pulled into the graph during resolution.

## 7. Running the example

Package the API module and the application module into the mods directory. Package the provider module into a separate JAR in the plugins directory. When compiling the provider, the module path must contain the API JAR so javac can resolve the requires directive.

Launch the application with the command:

~~~bash
java --module-path mods \
     --module com.acme.greeting.app/com.acme.greeting.app.Main \
     plugins
~~~

The plugins argument is passed to Main and used as the path to search for provider modules. Expected output:

~~~text
Hello, Java!
~~~

In this run, the API and consumer modules belong to the boot layer. The provider module is found from the plugins directory, resolved, and defined in the child layer. There is no need to place the provider JAR on the application's startup module path.

## 8. Differences between the two common load overloads

ServiceLoader has two loading approaches commonly used in modular applications:

- ServiceLoader.load(GreetingService.class) uses the thread context class loader to locate providers. This approach fits many classpath applications and class-loader-based discovery scenarios.
- ServiceLoader.load(pluginLayer, GreetingService.class) explicitly specifies a module layer as the search scope. Providers are searched within that layer and its parent layers, which is suitable when the application creates its own layers for plugins.

If an application manages plugins with ModuleLayer, passing the layer explicitly makes the provider search scope clear and less dependent on the state of the thread context class loader. Regardless of which overload is used, a named module calling ServiceLoader still needs to declare uses for the corresponding service type.

## 9. Lifecycle and iterating over ServiceLoader

ServiceLoader is lazy: creating a ServiceLoader object does not mean all providers have been instantiated. Providers are created when the application iterates the iterator, calls forEach, or retrieves providers from a stream.

You can iterate directly:

~~~java
for (GreetingService service : services) {
    System.out.println(service.greet("Java"));
}
~~~

Or use a stream to inspect provider information before obtaining an instance:

~~~java
services.stream()
    .map(ServiceLoader.Provider::get)
    .forEach(service ->
        System.out.println(service.greet("Java"))
    );
~~~

ServiceLoader caches providers that have been discovered and created during that loader's lifetime. Calling reload() clears the cache so the next iteration discovers providers again. reload() does not recreate the ModuleLayer and does not modify the resolved module graph.

## 10. Common errors

| Symptom | Common cause | What to check |
|---|---|---|
| IllegalCallerException when calling load(layer, service) | Named module calling the API has not declared uses for the service type | Check module-info.java of the exact module containing the call |
| No provider found | JAR is not in the directory scanned by ModuleFinder, provider module is not in roots, or missing provides | Check plugin path, module name, and module descriptor |
| FindException or ResolutionException | Root module not found or dependency cannot be resolved | Check module name, module path, and requires directives |
| ServiceConfigurationError when iterating | Provider is misdeclared or cannot be instantiated | Check provider class, constructor, and provides directive |
| ClassCastException or provider not recognized as service type | API was loaded as two different Class types by different class loaders/layers | Place the API module in a parent layer and avoid packaging a copy of the API in the plugin |

When no providers are found, check both sides: whether the provider module declares provides for the correct service type, and whether that module was actually brought into the layer. Simply placing a JAR in the plugin directory is not enough if its module name is neither in the roots set nor a dependency of another root.

## 11. Choosing how to create class loaders

The example uses defineModulesWithOneLoader because this configuration creates a single class loader for the new modules in the layer. It suits many simple plugin systems where plugin modules can share one loader.

defineModulesWithManyLoaders creates a separate class loader for each module in the layer. This can be useful when clearer class loader boundaries between modules are needed. Whichever approach is chosen, module readability is still governed by the JPMS graph; separate class loaders do not turn ModuleLayer into a security sandbox.

A ModuleLayer is also not a separate process. Plugin code still runs inside the same JVM and can use the permissions the process holds. If untrusted code needs to be isolated, security boundaries must be designed at the process level or in another execution environment.

## 12. When should you use ServiceLoader.load with ModuleLayer?

This approach is suitable when an application needs to:

- Load plugins after the application has already started.
- Keep the service API stable in a parent layer while providers vary by plugin directory.
- Resolve a group of plugin modules and their dependencies into a separate layer.
- Search for providers against a specific module graph instead of relying on the thread context class loader.

If an application uses only the classpath and does not create custom module layers, ServiceLoader.load(service) is usually simpler. When an application already manages plugins using JPMS and ModuleLayer, ServiceLoader.load(layer, service) explicitly expresses where providers should be searched.

## Key takeaways

ServiceLoader defines how a consumer discovers and uses providers; JPMS declares the uses/provides relationship; ModuleLayer groups resolved modules into a runtime layer with parent-child relationships. The typical plugin loading flow is to find modules with ModuleFinder, resolve with Configuration, create a ModuleLayer, and then call ServiceLoader.load(layer, service).