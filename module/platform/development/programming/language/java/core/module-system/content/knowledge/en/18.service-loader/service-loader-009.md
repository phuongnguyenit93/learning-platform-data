# Testing a service when the provider is in another layer

The Java Module System allows an application to create multiple independent ModuleLayers. A service interface can reside in a parent layer, while an implementation is loaded into a child layer or another layer. Therefore, when testing ServiceLoader, it is necessary to clearly identify the layer containing the provider and use the right overload to locate the provider.

A typical case is an application having a stable service API in the boot layer, while plugins/providers are loaded dynamically from a separate module directory. Tests need to prove that the application finds the provider in the specified layer, that the provider actually belongs to that layer, and that layers without a parent-child relationship are not mixed together.

## 1. Two ways to load a service and the key difference

ServiceLoader has common overloads:

| API | How providers are searched |
|---|---|
| ServiceLoader.load(Service.class) | Uses the thread context class loader |
| ServiceLoader.load(Service.class, loader) | Uses the specified class loader |
| ServiceLoader.load(layer, Service.class) | Searches providers in the specified layer and its parent layers |

When a provider is deployed in a custom ModuleLayer, use the overload taking a ModuleLayer. This accurately expresses the search scope and avoids relying on the thread context class loader.

Suppose the runtime structure is as follows:

~~~text
ModuleLayer.boot()
    |
    |-- com.example.spi
    |      exports com.example.spi
    |
    |-- com.example.app
           requires com.example.spi
           uses com.example.spi.GreetingService

ModuleLayer child
    |
    |-- com.example.provider
           requires com.example.spi
           provides GreetingService with FormalGreeting
~~~

The service interface is shared from the parent layer. The provider is loaded into the child layer. When calling ServiceLoader.load(childLayer, GreetingService.class), ServiceLoader searches for providers in childLayer and its parent layers.

A sibling layer is not within the search scope. For example, if childA and childB are both created directly from the boot layer, a loader bound to childA does not automatically find providers that exist only in childB.

## 2. Declaring the service and provider in modules

The example uses a simple service for testing.

Module containing the service API:

~~~java
module com.example.spi {
    exports com.example.spi;
}
~~~

Service interface:

~~~java
package com.example.spi;

public interface GreetingService {
    String greet();
}
~~~

Provider module:

~~~java
module com.example.provider {
    requires com.example.spi;

    provides com.example.spi.GreetingService
        with com.example.provider.FormalGreeting;
}
~~~

Provider implementation:

~~~java
package com.example.provider;

import com.example.spi.GreetingService;

public final class FormalGreeting implements GreetingService {
    public FormalGreeting() {
    }

    @Override
    public String greet() {
        return "Hello from child layer";
    }
}
~~~

With the provides ... with ... declaration, the provider class in the example is public and has a public no-argument constructor. The provider module must be able to read the module containing the service interface.

Application or test module calling ServiceLoader:

~~~java
module com.example.app {
    requires com.example.spi;

    uses com.example.spi.GreetingService;
}
~~~

The uses directive is critical. The module making the ServiceLoader call must declare the service it uses. If the caller is a named module without uses, loading the service can throw ServiceConfigurationError.

## 3. Creating a child layer containing the provider

To properly test the scenario where the provider is in another layer, do not put the provider in the boot layer. Assume the SPI module and application module are already loaded in the boot layer, while the provider module is packaged in a separate directory, such as plugins/.

A child layer can be created using ModuleFinder, Configuration, and ModuleLayer:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

public final class PluginLayers {

    private PluginLayers() {
    }

    public static ModuleLayer createProviderLayer(Path pluginsDirectory) {
        ModuleFinder finder = ModuleFinder.of(pluginsDirectory);

        Configuration configuration =
                ModuleLayer.boot()
                        .configuration()
                        .resolve(
                                finder,
                                ModuleFinder.of(),
                                Set.of("com.example.provider"));

        return ModuleLayer.defineModulesWithOneLoader(
                configuration,
                List.of(ModuleLayer.boot()),
                ClassLoader.getSystemClassLoader())
                .layer();
    }
}
~~~

Meaning of the steps:

1. ModuleFinder.of(pluginsDirectory) locates provider modules in the plugin directory.
2. configuration().resolve(...) resolves the module graph starting from the root module com.example.provider. Dependencies can be found in the parent layer.
3. ModuleLayer.defineModulesWithOneLoader(...) defines the resolved modules into a new layer. Modules in the new layer use a single class loader whose parent is the passed class loader.
4. layer() retrieves the newly created ModuleLayer from the Controller.

In this example, the provider is explicitly specified as a root so resolve() is sufficient to bring it into the configuration. If the goal is to test automatic service binding, you can use resolveAndBind() with a root module consuming the service so the service binding algorithm discovers additional matching providers in the module finder.

Having a JAR present in the plugin directory does not automatically mean that module belongs to the layer. The module must be found and resolved into the configuration before being defined in the layer.

## 4. Testing that the provider actually resides in the child layer

The test should verify both conditions:

- ServiceLoader finds the provider.
- The provider's class is defined in the right child ModuleLayer.

You can use ServiceLoader.stream() to retrieve Providers before instantiating the implementation. Provider.type() lets you check the provider's class and module.

JUnit example:

~~~java
package com.example.app;

import com.example.spi.GreetingService;
import java.nio.file.Path;
import java.util.List;
import java.util.ServiceLoader;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ServiceLayerTest {

    @Test
    void discoversProviderFromChildLayer() {
        ModuleLayer childLayer =
                PluginLayers.createProviderLayer(Path.of("plugins"));

        List<ServiceLoader.Provider<GreetingService>> providers =
                ServiceLoader.load(childLayer, GreetingService.class)
                        .stream()
                        .collect(Collectors.toList());

        assertTrue(
                providers.stream().anyMatch(provider ->
                        provider.type().getModule().getLayer() == childLayer),
                "Must find provider belonging to child layer");

        List<String> messages = providers.stream()
                .map(ServiceLoader.Provider::get)
                .map(GreetingService::greet)
                .collect(Collectors.toList());

        assertTrue(messages.contains("Hello from child layer"));
    }
}
~~~

The first check verifies that the provider type belongs to the right child layer. The second check invokes the provider and verifies actual behavior. These two assertions catch two different classes of bugs: failing to find the provider, and finding the provider but having it not behave as expected.

Do not check only the provider count. A provider from a parent layer can also be found by ServiceLoader.load(childLayer, service). Checking getModule().getLayer() identifies exactly where the provider came from.

Also do not assume the first provider in the list is the child layer's provider. Provider order is not a contract that tests should depend on. Filter by module layer, module name, or business result.

## 5. Testing parent layer and sibling layer scopes

ServiceLoader.load(layer, service) searches for providers in the specified layer and its parent layers. This behavior has two consequences to include in tests.

**Providers in parent layers can be found.** If the boot layer already has a provider for the same service, a loader created from a child layer can see that provider. Therefore, a test checking only providers.isEmpty() or providers.size() may give misleading results for the goal of testing the child layer.

**Providers in sibling layers are not automatically found.** If childA and childB both have the boot layer as their parent, a provider residing only in childB is not within the scope of a loader created from childA.

The search scope can be illustrated as:

~~~text
                 boot layer
                 /        \
             childA      childB
               |            |
           provider A    provider B

ServiceLoader.load(childA, Service.class)
    searches in childA and boot layer
    does not find providers located only in childB
~~~

When testing sibling isolation, create two independent layers from the same parent, place a separate provider in each layer, and verify that layer A's loader does not return providers whose module belongs to layer B. Each layer must be created from an appropriate configuration and the service type must be the same Class shared from the parent layer.

Do not compare module names alone to identify a layer. The same module name can appear in independent runtime configurations. Comparing ModuleLayer objects from Class.getModule().getLayer() accurately indicates the provider's origin.

## 6. Why might load(service) miss the provider?

ServiceLoader.load(GreetingService.class) uses the thread context class loader. This approach is common when providers are on the classpath or within the class loader scope the application is using.

A custom ModuleLayer may be defined with its own class loader. If the thread context class loader cannot see the provider in that layer, the default class-loader overload fails the test's objective.

Therefore:

~~~java
// Search for providers via the thread context class loader
ServiceLoader<GreetingService> defaultLoader =
        ServiceLoader.load(GreetingService.class);

// Search for providers in a specific ModuleLayer
ServiceLoader<GreetingService> layerLoader =
        ServiceLoader.load(childLayer, GreetingService.class);
~~~

The two loaders above have different search scopes. Do not use the result of defaultLoader to conclude whether a provider exists in childLayer. When testing plugins by ModuleLayer, pass the layer explicitly.

If the system intentionally uses class loaders to manage plugins, you can test the load(service, loader) overload, but that test answers questions about provider visibility via a class loader. It does not replace testing ModuleLayer scoping.

## 7. Checking module descriptors and configuration errors

When a provider is not found, check module configuration in order:

1. Was the provider module actually included in the layer's configuration?
2. Does the provider module declare requires on the module containing the service interface?
3. Does the provider module have provides Service with ProviderClass in module-info.java?
4. Does the module calling ServiceLoader declare uses Service?
5. Can the provider class be instantiated according to ServiceLoader rules?
6. Does the service interface have the same Class identity between the caller and the provider?

You can inspect descriptors before creating the layer:

~~~java
ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));

finder.find("com.example.provider")
        .ifPresent(reference -> {
            var descriptor = reference.descriptor();

            System.out.println("Module: " + descriptor.name());
            descriptor.requires().forEach(System.out::println);
            descriptor.provides().forEach(System.out::println);
        });
~~~

ModuleDescriptor.provides() shows the services the module provides. ModuleDescriptor.uses() shows the services the module consumes. This is a useful way to catch declaration mistakes before running integration tests.

ServiceConfigurationError usually indicates a configuration error or a failure when locating/instantiating a provider. When encountering an error, preserve the cause and module information in logs to identify the problematic provider class, constructor, module descriptor, or class loader.

Do not catch ServiceConfigurationError and return an empty list. Doing so turns a configuration error into a "no provider" test outcome, making the real root cause hard to find.

## 8. Recommended test matrix

| Scenario | Expected outcome |
|---|---|
| Provider resolved into child layer | load(childLayer, service) finds the provider |
| Provider in parent layer | Child layer loader can find the parent provider |
| Provider only in sibling layer | Child layer loader does not find the sibling provider |
| Provider JAR only on disk, not resolved into layer | Not treated as a provider of the layer |
| Provider module missing provides | ServiceLoader does not find the provider by module declaration |
| Caller module missing uses | May receive ServiceConfigurationError |
| Provider fails to instantiate | Receives ServiceConfigurationError; test must fail |
| Using load(service) with a context loader that cannot see the plugin | Cannot use this result to draw conclusions about childLayer |

For integration tests, include at least one provider residing only in the child layer and a test confirming layer identity. If the system supports multiple plugin layers, add a sibling isolation test to avoid accidentally sharing providers across plugins.

## 9. Practical guidelines

- Use ServiceLoader.load(layer, service) when you want to test providers in a specific ModuleLayer.
- Ensure the module calling ServiceLoader has a uses directive for the service.
- Ensure the provider module has been resolved and defined in the layer.
- Use provides ... with ... in the provider module's module descriptor.
- Verify the provider belongs to the right layer using provider.type().getModule().getLayer().
- Do not rely on provider order.
- Distinguish providers in a parent layer from providers in a child layer.
- Do not expect a layer's loader to find providers located only in a sibling layer.
- Keep ServiceConfigurationError visible in tests so module descriptor or provider instantiation errors are not hidden.

When testing services across multiple ModuleLayers, what must be verified is not just that the service returns the right result. Tests must also verify that the provider is discovered from the right layer, with the right parent-child relationship and the right module configuration. This is how to catch common bugs early in plugin systems or applications that load modules dynamically.