# How are provider modules pulled into the module graph?

## 1. Objectives

In the Java Platform Module System (JPMS), a module using a service does not have to declare `requires` directly on the module implementing that service. This is intentional in the Service Binding mechanism: the consuming module declares **the service it needs**, the provider module declares **the service it provides**, and the module resolver can automatically bring matching provider modules into the module graph.

Three things must be distinguished:

1. **Declaring the service contract:** the consumer uses `uses`, and the provider uses `provides ... with ...`.
2. **Service binding:** the resolver locates matching provider modules and adds them to the configuration/module graph.
3. **Using the service:** `ServiceLoader` locates providers and creates service instances when the application requests them.

Service binding determines which modules are present in the graph. It does not instantiate implementations by itself.

After this lesson, you will be able to explain why a consumer does not need to `requires` a provider, distinguish `resolve()` from `resolveAndBind()`, and check whether a provider module has been brought into a configuration.

## 2. Three-module example

Suppose there are three modules:

- `com.example.greeting.api`: defines the service interface.
- `com.example.greeting.app`: consumes the service.
- `com.example.greeting.provider`: supplies the implementation.

Desired relationship:

```text
com.example.greeting.app
        |
        | uses GreetingService
        v
GreetingService (API contract)
        ^
        | provides GreetingService with ...
        |
com.example.greeting.provider
```

The consumer depends on the API contract. It does not need to know the concrete implementation name. The provider module depends on the API to implement the interface.

## 3. Two directives that enable service binding

### API module

`module-info.java` of the API module:

```java
module com.example.greeting.api {
    exports com.example.greeting.api;
}
```

Service interface:

```java
package com.example.greeting.api;

public interface GreetingService {
    String greet(String name);
}
```

### Consumer module

`module-info.java` of the application:

```java
module com.example.greeting.app {
    requires com.example.greeting.api;

    uses com.example.greeting.api.GreetingService;
}
```

The `uses` directive states that the app module needs to find implementations of `GreetingService`. It does not specify a concrete implementation class or provider module.

### Provider module

`module-info.java` of the provider:

```java
module com.example.greeting.provider {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.provider.FormalGreetingService;
}
```

Implementation:

```java
package com.example.greeting.provider;

import com.example.greeting.api.GreetingService;

public final class FormalGreetingService implements GreetingService {

    public FormalGreetingService() {
        System.out.println("FormalGreetingService initialized");
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

The `provides S with P` directive registers class `P` as a provider for service type `S`. The provider module needs to read the module containing the service API, so it declares `requires com.example.greeting.api`.

The package containing the implementation does not need to be exported merely for `ServiceLoader` to discover the provider declared with `provides`. The module descriptor has already published the relationship between the service and the provider.

## 4. Why is normal requires not enough?

The module resolver starts from the root modules and resolves the modules they require via `requires` directives, continuing along their dependencies.

If the app only declares:

```java
requires com.example.greeting.api;
uses com.example.greeting.api.GreetingService;
```

then the normal dependency graph contains the API module, but there is no `requires` edge leading to `com.example.greeting.provider`.

The `uses` directive is not equivalent to `requires`. It declares a need for a service so that the service binding mechanism can find modules providing that service. As a result, the app is not tightly coupled to a single implementation and providers can be swapped without modifying the app's module descriptor.

This also means that placing a provider JAR on the module path does not automatically guarantee the provider module will be in the configuration. The provider must be visible to the resolver and service binding must be performed.

## 5. How do resolve() and resolveAndBind() differ?

Both methods resolve root modules and their required dependencies. The difference lies in the service binding step.

| Method | How the module graph is built |
| --- | --- |
| `Configuration.resolve(...)` | Resolves the roots along with the dependency closure following `requires` directives. |
| `Configuration.resolveAndBind(...)` | Performs normal resolution, then adds provider modules for services used in the graph; continues until no new provider modules remain. |

If a provider module is already pulled into the graph by `requires` or specified as a root, it is still present when using `resolve()`. Service binding is useful when providers are not explicit dependencies of the consumer.

### Service binding algorithm

The process can be pictured as follows:

1. The resolver resolves the root modules and all of their `requires` dependencies.
2. The resolver inspects the resolved modules to collect the service types declared in `uses` directives.
3. The resolver finds observable modules that have `provides` directives for those service types.
4. Matching provider modules are added to the graph; their `requires` dependencies are also resolved.
5. The resolver continues inspecting the newly added modules. If a provider module also declares `uses` for other services, corresponding providers can continue to be added.
6. The process stops when no more new provider modules are added.

This is a form of closure: the graph expands from roots, regular dependencies, and providers discovered through service binding.

If multiple visible provider modules provide the same used service, service binding can bring all matching providers into the graph. Choosing or using one or more implementations is an application-level decision made via `ServiceLoader` and application logic.

## 6. Creating a custom module layer with resolveAndBind()

Suppose the modules have been compiled into JARs in the `mods/` directory. We want to create a child layer with `com.example.greeting.app` as the root.

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class LayerBootstrap {

    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

        Configuration parentConfiguration =
            ModuleLayer.boot().configuration();

        Configuration configuration =
            parentConfiguration.resolveAndBind(
                finder,
                ModuleFinder.of(),
                Set.of("com.example.greeting.app")
            );

        ModuleLayer layer =
            ModuleLayer.boot().defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader()
            );

        System.out.println(
            "Provider module resolved: "
                + configuration.findModule("com.example.greeting.provider").isPresent()
        );
    }
}
```

Explanation of parameters:

- `finder`: where the resolver looks for observable modules, including the app, API, and provider in the example.
- `ModuleFinder.of()`: empty finder in the search position after the parent configurations.
- `Set.of("com.example.greeting.app")`: root module to launch.
- `resolveAndBind`: resolves dependencies and adds matching provider modules.
- `defineModulesWithOneLoader`: creates a new layer from the resolved configuration, using a single class loader for the modules in the layer per the API's policy.

The line `configuration.findModule(...).isPresent()` checks whether the provider module is in the configuration. This is evidence at the module graph level; it does not prove that the provider's constructor has run.

## 7. Using ServiceLoader after the layer has been created

Once the module layer contains the provider module, the application can look up the service in that layer:

```java
import com.example.greeting.api.GreetingService;
import java.util.ServiceLoader;

ServiceLoader<GreetingService> services =
    ServiceLoader.load(layer, GreetingService.class);

services.stream()
    .map(ServiceLoader.Provider::get)
    .forEach(provider ->
        System.out.println(provider.greet("Java"))
    );
```

In the app module, the `uses com.example.greeting.api.GreetingService` directive still must be declared so the module is permitted to use that service type via `ServiceLoader`.

There are two separate stages:

- When `resolveAndBind` is called, the resolver locates provider modules and adds them to the configuration.
- Only when `ServiceLoader` is called and a provider instance is requested with `Provider.get()` or iterated through an iterator is the implementation instantiated.

If you only want to inspect the provider type before instantiation, you can use `services.stream()` and `Provider.type()`. Service binding itself does not invoke provider constructors.

## 8. Conditions for a provider module to be pulled into the graph

A provider module can only be added when the necessary conditions are met:

- **Consumer declares `uses`:** the service type must appear in the module descriptor of an already resolved module.
- **Provider declares `provides`:** the provider module must register the exact service type using the `provides S with P` directive.
- **Provider can be found:** the module must be within the scope that the `ModuleFinder` instances and parent configurations allow the resolver to observe. Having a JAR file in a location that no finder searches is not enough.
- **Valid provider module:** the provider's dependencies must be resolvable and the descriptor/provider declaration must be valid.
- **Using a mechanism with service binding:** you must call `resolveAndBind` or use a launcher/packaging tool with appropriate service binding enabled. Plain `resolve()` does not perform this provider-adding step.

If no matching provider is found, the resolver does not synthesize an implementation and the service may have no providers. The application should decide whether that service is mandatory or optional and handle the zero-provider case at the usage layer.

## 9. Module path, classpath, and jlink

With named modules, providers are published in `module-info.java` using `provides ... with ...`; service consumers declare `uses`. This is the metadata the module resolver uses for service binding.

For providers placed on the classpath, the traditional registration mechanism is the file:

```text
META-INF/services/com.example.greeting.api.GreetingService
```

The file contains the fully qualified names of the provider classes. `ServiceLoader` can read this configuration via the class loader, but a classpath provider is not a named provider module for the resolver to add to the module graph via JPMS's `provides` mechanism.

During runtime image creation, the `jlink` tool has the `--bind-services` option to include needed provider modules and their dependencies in the image based on services used by selected modules. This is a service linking step when packaging the runtime image; it is not an operation that instantiates service objects when running the application.

## 10. Common misconceptions

- **`uses` is not `requires`:** `uses` declares a service dependency. It does not create an explicit dependency from the consumer to the provider module.
- **Being on the module path does not mean being in the graph:** the resolver only uses modules observable within the current finders and resolution rules.
- **`resolve()` does not automatically bind providers:** if you need to pull in provider modules based on service usage, use `resolveAndBind()`.
- **Service binding does not select a single provider:** multiple matching providers can be added to the graph together. The application decides which provider(s) will be used.
- **Being in the graph does not mean being instantiated:** configurations and module layers describe resolved modules. Service instances are only requested in the service usage step.
- **Consumers do not need to read implementation packages:** the app depends on the API contract; the provider module publishes its implementation via its descriptor and can keep the implementation package encapsulated.

## 11. Key Takeaways

- Consumers declare needed services with `uses`.
- Provider modules publish implementations with `provides S with P`.
- Normal resolution follows `requires`; service binding expands the graph according to used services.
- `Configuration.resolveAndBind()` repeats finding providers and resolving dependencies until no new modules remain.
- `ServiceLoader` consumes providers in a layer; `Provider.get()` is what requests a service instance.

When diagnosing why a provider does not appear, check in order: whether the consumer declares `uses` for the right service type, whether the provider declares `provides` for the right type, whether the module finder can see the provider, and whether the configuration was created with `resolveAndBind` rather than just `resolve`.
