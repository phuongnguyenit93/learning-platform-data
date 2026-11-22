# uses Declares a Service Consumer

## 1. Service Consumer and the Role of uses

The Java Platform Module System (JPMS) supports the **service** model so that one module can use functionality provided by another module without directly depending on a specific implementation class.

In this model, there are three components:

- **Service type**: an interface or abstract class that describes the contract implementations must follow.
- **Service consumer**: a module that needs to use the functionality and declares a uses directive for the service type.
- **Service provider**: a module that provides an implementation and registers it using the provides ... with ... directive.

The **uses** directive in a module descriptor declares that the current module is a consumer of a service type:

~~~java
module com.acme.application {
    requires com.acme.greeting.api;
    uses com.acme.greeting.api.GreetingService;
}
~~~

This declaration states that the application module needs the GreetingService service. It does not specify which implementation will be used, nor does it create a direct requires to each provider module.

As a result, the consumer depends on a stable service contract. Providers can be replaced or added without modifying the consumer code, as long as the implementation complies with the contract and is validly registered.

## 2. How does uses differ from requires?

The two directives serve different purposes:

- **requires** establishes a readability relationship between the current module and another module. The consumer needs to require the module containing the service type so it can reference the interface or abstract class in source code.
- **uses** declares the need to use a service type. It lets the service loading mechanism know which module is consuming the service and is part of the module contract.

Example:

~~~java
module com.acme.application {
    requires com.acme.greeting.api;
    uses com.acme.greeting.api.GreetingService;
}
~~~

The consumer needs `requires com.acme.greeting.api` because GreetingService is a type located in the API module. The consumer does not need `requires com.acme.greeting.provider` just to discover the implementation.

Overview of the relationships:

~~~text
com.acme.application
    | requires
    v
com.acme.greeting.api
    |
    | exports package containing GreetingService
    v
GreetingService (service contract)

com.acme.greeting.application
    | uses GreetingService
    |
    | ServiceLoader discovers providers
    v
Provider registered by implementation module
~~~

uses does not replace requires to the module containing the service type. Conversely, requiring the API module does not automatically declare that the consumer wants to use the service via ServiceLoader.

## 3. Declaring a Service Type in the API Module

The service type should be a small, stable contract placed in a public package of the API module.

Example structure:

~~~text
src/
└── com.acme.greeting.api/
    ├── module-info.java
    └── com/acme/greeting/api/
        └── GreetingService.java
~~~

Module descriptor:

~~~java
module com.acme.greeting.api {
    exports com.acme.greeting.api;
}
~~~

Service interface:

~~~java
package com.acme.greeting.api;

public interface GreetingService {
    String greet(String name);
}
~~~

The API module exports the package so that consumers and providers can reference GreetingService. The API module does not need to know which implementation will be loaded.

A service type can also be an abstract class if the contract needs to inherit shared state or behavior. However, an interface is usually more suitable for a service extension point because it separates the contract from the implementation.

A good service contract should:

- Contain only the methods that consumers actually need.
- Use public and stable data types in method signatures.
- Avoid depending on internal packages of providers.
- Clearly define the meaning of parameters, results, and potential errors.
- Avoid requiring consumers to know the implementation class or how providers are instantiated.

## 4. Consumer Declaring uses and Calling ServiceLoader

The consumer declares a dependency on the API module and the service it uses:

~~~text
src/
└── com.acme.greeting.consumer/
    ├── module-info.java
    └── com/acme/greeting/consumer/
        └── Main.java
~~~

Module descriptor:

~~~java
module com.acme.greeting.consumer {
    requires com.acme.greeting.api;
    uses com.acme.greeting.api.GreetingService;
}
~~~

The consumer code uses ServiceLoader to locate implementations:

~~~java
package com.acme.greeting.consumer;

import com.acme.greeting.api.GreetingService;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<GreetingService> services =
                ServiceLoader.load(GreetingService.class);

        boolean found = false;

        for (GreetingService service : services) {
            found = true;
            System.out.println(service.greet("Phuong"));
        }

        if (!found) {
            System.out.println("No GreetingService provider available");
        }
    }
}
~~~

ServiceLoader is Java's standard API for locating and loading registered providers. The consumer does not need to manually scan the classpath, look up implementation class names, or invoke the constructor of a specific class.

In a named module, the module calling ServiceLoader must declare uses for the service type. If uses is missing, loading the service may fail with a ServiceConfigurationError because the module has not declared its need to use that service.

All providers can be iterated using a loop as shown above. ServiceLoader loads providers on demand during iteration, so it does not necessarily instantiate all implementations immediately when load is called.

## 5. Provider Registering an Implementation with provides

The provider module depends on the API module because its implementation must implement GreetingService:

~~~text
src/
└── com.acme.greeting.provider/
    ├── module-info.java
    └── com/acme/greeting/provider/impl/
        └── VietnameseGreetingService.java
~~~

Module descriptor registering the implementation:

~~~java
module com.acme.greeting.provider {
    requires com.acme.greeting.api;

    provides com.acme.greeting.api.GreetingService
        with com.acme.greeting.provider.impl.VietnameseGreetingService;
}
~~~

Implementation:

~~~java
package com.acme.greeting.provider.impl;

import com.acme.greeting.api.GreetingService;

public final class VietnameseGreetingService
        implements GreetingService {

    public VietnameseGreetingService() {
    }

    @Override
    public String greet(String name) {
        return "Xin chao, " + name + "!";
    }
}
~~~

The provides ... with ... directive resides in the provider's module descriptor. It registers that this module provides an implementation for the specified service type.

For a conventional provider class, the implementation class must be public, non-abstract, and have a public no-argument constructor so ServiceLoader can create an instance. Java also supports a public static provider method named provider in the provider class; this approach is useful when creating the service requires a factory or custom configuration.

The package containing the implementation does not need to be exported just for ServiceLoader to find a named module's provider. The consumer only needs to know the public service type; implementation details can remain encapsulated inside the provider module.

## 6. Relationship Between the Three Modules

A complete example has three independent modules:

~~~text
com.acme.greeting.api
    exports com.acme.greeting.api
    └── GreetingService

com.acme.greeting.provider
    requires com.acme.greeting.api
    provides GreetingService with VietnameseGreetingService

com.acme.greeting.consumer
    requires com.acme.greeting.api
    uses GreetingService
    └── Main -> ServiceLoader
~~~

The key point is that both the consumer and the provider depend on the API module, but do not depend directly on each other:

- The API module owns the service contract.
- The consumer module declares its need via uses.
- The provider module registers its implementation via provides.
- ServiceLoader connects the consumer to available providers in the module layer environment.

There can be multiple providers for the same service type. The consumer can iterate over all of them, select based on metadata, or apply its own policy. You should not rely on the order in which providers are found unless that order is part of the application contract.

## 7. Compiling and Running the Modular Example

With the source structure placed in module directories as shown above, all three modules can be compiled using:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.acme.greeting.api,com.acme.greeting.consumer,com.acme.greeting.provider
~~~

After compiling, the mods directory contains the corresponding module directories:

~~~text
mods/
├── com.acme.greeting.api/
├── com.acme.greeting.consumer/
└── com.acme.greeting.provider/
~~~

Running the consumer:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --module com.acme.greeting.consumer/com.acme.greeting.consumer.Main
~~~

During module resolution, Java can perform service binding to include matching provider modules in the configuration when they are on the module path and provide a service used by a resolved module. Depending on the runtime configuration and custom module layers, it may be necessary to add provider modules as roots or explicitly configure the modules to include in the layer.

The --show-module-resolution option helps observe which modules are resolved and assists in diagnosing cases where a provider does not appear as expected.

## 8. ServiceLoader and Module Layers

ServiceLoader does not work only with the boot layer. An application can create custom module layers to load plugins or independent groups of providers.

Once you have a ModuleLayer, you can locate services within that layer:

~~~java
ServiceLoader<GreetingService> services =
        ServiceLoader.load(pluginLayer, GreetingService.class);
~~~

This approach is useful when an application needs to load plugins after startup, isolate groups of providers by module layer, or control the lifecycle of a module configuration.

It is important to distinguish:

- A module layer holds a resolved module configuration.
- ServiceLoader searches for providers registered within the layer or class loader corresponding to the overload used.
- Simply having a JAR on disk does not guarantee that the provider will be visible in the layer being queried.

When creating a custom layer, you must specify the module roots, module finder, configuration, and class loader appropriate for the plugin design. If a provider is not found, check which layer ServiceLoader is querying and whether the provider module has been included in that layer's configuration.

## 9. Multiple Providers and Handling the No-Provider Case

A service can have multiple implementations:

~~~java
ServiceLoader<GreetingService> services =
        ServiceLoader.load(GreetingService.class);

for (GreetingService service : services) {
    System.out.println(service.greet("An"));
}
~~~

If the application needs to select a single provider, define an explicit selection policy. For example, you can use application configuration to select a provider by name or business attribute, rather than relying on iteration order.

If no provider is found, ServiceLoader does not necessarily throw an error simply because the list is empty. The consumer should decide the appropriate behavior: use a fallback, skip the optional feature, or report a configuration error if the service is required.

During provider iteration, configuration errors or instantiation failures may surface as a ServiceConfigurationError. You should inspect the root cause, such as an invalid provider class, missing suitable constructor, failure to implement the service type, or a provider dependency missing at runtime.

## 10. Services on the Classpath and META-INF/services

The service model predates JPMS and still works with classpath applications. When the consumer and provider reside on the classpath, the consumer typically does not declare uses in a module descriptor because the classpath belongs to the unnamed module.

Traditional providers register using a configuration file:

~~~text
META-INF/services/com.acme.greeting.api.GreetingService
~~~

The file lists the fully qualified name of each implementation, one provider per line:

~~~text
com.acme.greeting.provider.impl.VietnameseGreetingService
com.acme.greeting.provider.impl.EnglishGreetingService
~~~

The consumer can still use:

~~~java
ServiceLoader<GreetingService> services =
        ServiceLoader.load(GreetingService.class);
~~~

When migrating to named modules, provider registration is expressed explicitly in module-info.java using provides ... with ..., and consumer demand is expressed using uses. This is structured metadata that helps Java tools and the module system understand service relationships without relying solely on configuration files inside JARs.

You should not arbitrarily register the same provider in multiple ways. Choose the model that matches the packaging and class loader/module layer setup your application uses.

## 11. Common Mistakes When Using uses

**Consumer forgets to declare uses**

A module calls ServiceLoader for a service, but its module descriptor lacks the corresponding uses directive. Add the exact service type to the consumer's module-info.java.

**Consumer lacks requires for the API module**

The consumer declares uses but cannot read the module containing the service type. Add a requires to the API module and ensure the API module exports the package containing the service type.

**Provider does not declare provides**

The implementation class exists in the JAR, but the named module does not register the service with provides. Add provides ServiceType with ProviderImplementation to the provider's module descriptor.

**Provider module is not resolved or not in the searched layer**

Check the module path, module roots, service binding, and the module layer passed to ServiceLoader. A provider in a different layer will not automatically appear in every query.

**Invalid provider implementation**

Check whether the implementation is compatible with the service type and has a valid instantiation mechanism. For a standard provider class, a public class and a public no-argument constructor are required; for a provider method, verify there is a public static no-argument provider method with an appropriate return type.

**Service type is not a shared API**

If the package containing the service type is not exported or the provider/consumer cannot read the API module, the modules cannot reference the same contract. Place the service type in an exported API package and declare requires in both consumer and provider.

**Consumer depends directly on the implementation**

If the consumer imports the implementation class or invokes the provider constructor directly, the substitutability of the service is lost. The consumer should reference only the service type and use ServiceLoader to locate providers.

## 12. Service Consumer Design Principles

When writing a consumer module, apply these principles:

- Declare uses for the exact service type that the module actually consumes.
- Only require the module containing the service contract and other direct dependencies the code needs.
- Do not declare requires on individual providers just to use ServiceLoader.
- Define clear behavior when no provider is present or when multiple providers exist.
- Do not assume provider order is stable unless an explicit contract guarantees it.
- Use explicit module layers when plugins need their own lifecycle or scope.
- Keep the service type in an exported API package and avoid exposing implementation details.
- Handle ServiceConfigurationError to report meaningful provider registration errors.

A good consumer knows what capability and contract it needs, without needing to know which specific class will perform that capability.

## 13. Key Takeaways

- uses declares a service consumer in a module descriptor.
- requires establishes a readability relationship to the module containing the service type; uses declares the need to use the service.
- Providers register implementations with provides ServiceType with Implementation.
- ServiceLoader discovers and loads providers, keeping consumers decoupled from concrete implementation classes.
- The package containing the service type must be exported so consumers and providers can access the contract.
- A provider's implementation package can remain unexported.
- Named modules must declare uses; traditional classpath applications can register providers using META-INF/services.
- The module layer determines the scope of providers that can be found when using ServiceLoader with a specific layer.

When you need to extend an application with plugins or multiple implementations, design an independent service contract, declare uses in the consumer, and declare provides in the provider. This organization allows implementations to change without modifying the code that uses the service.
