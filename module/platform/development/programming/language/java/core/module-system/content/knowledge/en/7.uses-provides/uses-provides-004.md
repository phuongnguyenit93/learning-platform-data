# ServiceLoader Discovers Providers via the Module Graph

In Java, an application may need to use a service without wanting to depend directly on a concrete implementation class. For example, an application may need to encode data while choosing among multiple encoders; a payment system may switch payment gateways; or an application may discover plugins installed at runtime.

Java provides `ServiceLoader` to locate and instantiate implementations of a service. When using the Java Platform Module System (JPMS), this mechanism works with two directives in the module descriptor:

- `uses` declares that a consuming module needs a service.
- `provides ... with ...` declares that a module provides an implementation of a service.

These directives inform the module system of service relationships. Resolution can use that information to bring provider modules into the module graph. Once modules have been defined in a `ModuleLayer`, `ServiceLoader` locates and instantiates providers within the specified loader or layer scope.

## 1. Service, Provider, and ServiceLoader

A **service** is a type known in advance to the application, usually an interface or an abstract class. The service defines the contract that implementations must adhere to.

A **provider** is a concrete implementation of a service. A service may have zero, one, or multiple providers. The application only needs to know the service interface; it does not necessarily need to know which JAR packages the provider or which module contains it.

For example, a service describing a format converter:

```java
package com.example.codec.api;

public interface Codec {
    String format();
    byte[] encode(byte[] input);
}
```

Providers might be JSON, XML, or binary encoders. Each provider implements the same contract with its own handling logic.

`ServiceLoader` is an API in `java.util` used to locate providers available in the runtime environment:

```java
ServiceLoader<Codec> codecs =
        ServiceLoader.load(Codec.class);

for (Codec codec : codecs) {
    System.out.println(codec.format());
}
```

The application iterates over the providers found by the loader. It can select a provider based on provider characteristics, application configuration, or business requirements. You should not assume there is always at least one provider; the application needs to handle the case where no suitable provider is found.

## 2. Two Sides of a Service in JPMS

A modular service model has three components:

1. The module containing the service interface.
2. The module consuming the service.
3. One or more modules supplying providers.

Example structure:

```text
codec-api/
└── module com.example.codec.api
    └── com.example.codec.api.Codec

application/
└── module com.example.application
    └── com.example.application.Main

codec-json/
└── module com.example.codec.json
    └── com.example.codec.json.JsonCodec
```

The service interface should reside in a package accessible to the consuming module. The provider module depends on the module containing the service in order to implement the exact interface type.

### 2.1. Service Module Exposing the Interface

API module descriptor:

```java
module com.example.codec.api {
    exports com.example.codec.api;
}
```

The `exports` directive allows other modules to reference the `Codec` type under standard Java access rules.

### 2.2. Consuming Module Declaring uses

Application descriptor:

```java
module com.example.application {
    requires com.example.codec.api;

    uses com.example.codec.api.Codec;
}
```

The two directives have different roles:

- `requires com.example.codec.api` allows the application module to read the module containing the service interface.
- `uses com.example.codec.api.Codec` declares that the application needs to locate providers for this service.

A named module using `ServiceLoader` must declare `uses` for the corresponding service. Without this directive, obtaining or using a service loader from an explicit module may fail with a `ServiceConfigurationError`.

### 2.3. Provider Module Declaring provides

JSON provider descriptor:

```java
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.api.Codec
        with com.example.codec.json.JsonCodec;
}
```

The `provides` directive identifies the service being supplied and the corresponding provider class.

Implementation class:

```java
package com.example.codec.json;

import com.example.codec.api.Codec;

public final class JsonCodec implements Codec {
    @Override
    public String format() {
        return "json";
    }

    @Override
    public byte[] encode(byte[] input) {
        // Illustration: actual encoding depends on the format.
        return input.clone();
    }
}
```

The provider module needs to read the module containing the interface in order to compile the implementation. The package containing the provider class does not need to be exported just for `ServiceLoader` to locate the provider declared in the descriptor. In fact, Java documentation recommends that provider modules not export their implementation packages unless there is another API that needs to be made public.

## 3. How Does the Module Graph Relate to Finding Providers?

The module graph represents resolved modules and the readability relationships among them. `requires` directives create regular dependencies. For services, JPMS uses additional information from `uses` and `provides` to perform **service binding** during resolution.

Three steps should be distinguished:

1. **ModuleFinder locates observable modules:** for example, modular JARs on the module path.
2. **Resolution builds a configuration:** starting from root modules, the system follows `requires` directives to determine needed modules and readability.
3. **Service binding can add provider modules:** if resolved modules declare `uses`, the system locates modules with matching `provides` for that service, adds those provider modules and their dependencies to the configuration, and continues checking for any newly introduced service dependencies.

Therefore, `provides` by itself is not a command to load and instantiate a provider. It records metadata indicating which module can supply an implementation. The provider must be observable and present in the module layer or class loader scope used by `ServiceLoader`.

### 3.1. Regular Resolution vs. Resolution with Service Binding

The `java.lang.module.Configuration` API has two commonly mentioned methods:

- `resolve(...)` resolves modules based on `requires` dependency relationships.
- `resolveAndBind(...)` performs resolution with service binding.

`resolveAndBind` first resolves root modules like standard resolution. Then, it examines service dependencies of the resolved modules and parent configurations. Observable modules that provide implementations for requested services are added to the module graph. The process repeats if newly added provider modules themselves use other services.

High-level overview:

```text
Root modules
     |
     v
Resolve requires dependencies
     |
     v
Read uses directives
     |
     v
Find modules with matching provides
     |
     v
Add provider modules and their dependencies
     |
     v
Check new service dependencies
     |
     v
Final Configuration / module graph
```

This is how provider modules can be brought into the runtime configuration without the consuming module declaring direct `requires` to each provider.

If only regular resolution is used, a module is not included in the configuration solely because it has `provides`. In that case, `ServiceLoader` cannot locate providers from a module not defined in the layer being searched.

## 4. Why Should an Application Not Directly require Providers?

A key benefit of service binding is decoupling the consuming module from implementation modules.

Suppose the application declares:

```java
module com.example.application {
    requires com.example.codec.api;
    uses com.example.codec.api.Codec;
}
```

If the application also declares:

```java
requires com.example.codec.json;
```

then the application depends directly on a specific provider. When replacing JSON with XML or installing additional providers, the consuming module may have to change its descriptor and build configuration.

Service design generally recommends that consuming modules:

- Require the API module containing the service interface.
- Declare `uses` for the service.
- Avoid directly requiring modules that act solely as providers, if the goal is for service binding to discover providers.

This keeps primary dependencies on the abstraction. Providers can be added, replaced, or selected per deployment environment without making each implementation a direct dependency of the application.

That does not mean providers magically appear from anywhere. Provider modules must still be discoverable, included in the appropriate configuration/layer, and satisfy the service contract.

## 5. ServiceLoader Locating Providers in a ModuleLayer

`ModuleLayer` is the runtime class holding a set of modules defined from a `Configuration`. An application can have a boot layer and create additional child layers to load plugins or independent module groups.

There are two notable ways to use `ServiceLoader`:

**Using the current class loader**

```java
ServiceLoader<Codec> codecs =
        ServiceLoader.load(Codec.class);
```

This overload uses the current thread's context class loader. Provider lookup covers named modules associated with the class loader/module layer as well as providers in the unnamed module via service configuration files on the classpath.

If the caller resides in an explicit named module, the caller's descriptor must include `uses` for the service.

**Specifying a ModuleLayer**

```java
ServiceLoader<Codec> codecs =
        ServiceLoader.load(pluginLayer, Codec.class);
```

This overload searches for providers in the passed module layer and its parent layers. It does not look for providers in the unnamed module.

The second approach is useful when an application creates its own plugin layer and wants to restrict provider discovery to that layer and its ancestor hierarchy.

### 5.1. Boot Layer and Child Layers

When the JVM starts a modular application, platform modules and application modules are defined in their respective layers; the boot layer is the primary initial layer of the application.

A plugin system can create a new layer from a configuration resolved from a plugin directory:

```java
Configuration configuration =
        ModuleLayer.boot()
                .configuration()
                .resolveAndBind(
                        ModuleFinder.of(),
                        pluginFinder,
                        Set.of()
                );

ModuleLayer pluginLayer =
        ModuleLayer.boot()
                .defineModulesWithOneLoader(
                        configuration,
                        ClassLoader.getSystemClassLoader()
                );

ServiceLoader<Codec> codecs =
        ServiceLoader.load(pluginLayer, Codec.class);
```

This snippet illustrates the idea: use a configuration with service binding, define the modules as a child layer of the boot layer, and ask `ServiceLoader` to locate services in that layer and its parents. In a real application, `pluginFinder` must be created from the location containing the plugin modules; service and provider modules must also have valid dependencies.

A layer can use one shared class loader for all modules or a separate class loader per module. `ServiceLoader.load(layer, service)` still locates providers across the layer's modules via the layer API, without requiring all modules to share the same class loader.

## 6. Provider Discovery and Instantiation Lifecycle

Creating a `ServiceLoader` does not mean all providers are immediately instantiated. Discovery and instantiation typically occur lazily as the application iterates over the results.

### 6.1. Iterating with an Iterator

```java
ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class);

for (Codec codec : loader) {
    System.out.println(codec.format());
}
```

The loop invokes the loader's iterator. Providers are located and instantiated as the next element is requested. If there are no providers, the loop ends with zero elements.

### 6.2. Using stream to Inspect Providers Before Instantiation

```java
ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class);

loader.stream()
        .filter(provider -> provider.type().getSimpleName()
                .contains("Json"))
        .map(ServiceLoader.Provider::get)
        .forEach(codec -> System.out.println(codec.format()));
```

`stream()` yields `ServiceLoader.Provider` objects. You can inspect the provider type via `type()` and filter before calling `get()` to obtain an instance.

This is useful when an application wants to check metadata or characteristics of a provider before instantiating the implementation. However, processing the stream can still trigger provider discovery and class loading as the pipeline executes.

### 6.3. Caching and reload

A `ServiceLoader` caches providers that have already been loaded. Subsequent iterations may return cached providers before discovering remaining providers.

If the environment allows installing new providers while the JVM is running, you can call:

```java
loader.reload();
```

This clears the cache so that subsequent iterations rediscover providers. Existing iterators or streams should be discarded after calling reload. A `ServiceLoader` instance is not thread-safe for concurrent use by multiple threads; if concurrent access is required, the application must manage sharing and synchronization appropriately.

## 7. What Conditions Must a Provider Module Satisfy?

For a provider declared in a named module:

- The `provides` directive must specify the service type and provider type.
- The provider type must be a valid type under ServiceLoader rules and must be public, not an inner class.
- If there is no provider method, the provider must have a public no-argument constructor and must implement or extend the service type.
- If there is a provider method, the method must be `public static`, named `provider`, take no parameters, and return a type compatible with the service. In that case, the provider class itself does not have to implement the service interface.
- The provider module must read the module containing the service type to reference the service.
- The provider's implementation package does not need to be exported just for ServiceLoader to discover the provider from the descriptor.

Example of a provider using a constructor:

```java
public final class JsonCodec implements Codec {
    public JsonCodec() {
    }

    @Override
    public String format() {
        return "json";
    }

    @Override
    public byte[] encode(byte[] input) {
        return input.clone();
    }
}
```

Example of a provider using a provider method:

```java
public final class JsonCodecFactory {
    private JsonCodecFactory() {
    }

    public static Codec provider() {
        return new JsonCodec();
    }
}
```

The descriptor can declare the factory class:

```java
provides com.example.codec.api.Codec
    with com.example.codec.json.JsonCodecFactory;
```

A provider method lets the module control instance creation, such as returning a configured implementation or one constructed via a factory. If there is no provider method, ServiceLoader instantiates the provider class via its public no-argument constructor.

## 8. Providers on the Classpath vs. Providers in Named Modules

ServiceLoader supports both traditional classpath providers and providers declared in module descriptors.

| Deployment Mode | Where Provider Is Declared | Discovery Mechanism |
|---|---|---|
| Provider in a named module | `provides Service with Provider` in `module-info.java` | By module/class loader or ModuleLayer |
| Provider in the unnamed module on the classpath | `META-INF/services/<fully qualified name of service>` | Reads service configuration file via class loader |
| Provider in an automatic module | Service configuration file in the JAR per automatic module rules | Discovered like a named module on the module path; provider requires a constructor |

On the classpath, the configuration file is named after the fully qualified binary name of the service, located in the `META-INF/services` directory. The file contains the fully qualified name of each provider, one name per line.

Example:

```text
META-INF/services/com.example.codec.api.Codec
```

Contents:

```text
com.example.codec.json.JsonCodec
```

When a JAR is placed on the module path as an automatic module, ServiceLoader supports providers declared via this configuration file, but does not support provider methods in automatic modules. The provider must have a suitable constructor.

For explicit named modules, prefer the `provides` directive over the traditional configuration file. If the same provider is declared in both the descriptor and the configuration file, a provider deployed in a named module will not be duplicated from the configuration file.

## 9. Provider Ordering and Choosing an Implementation

ServiceLoader is not a mechanism that automatically selects the best implementation. It locates observable providers; the application decides which provider to use.

You should not rely on the ordering between modules in the same layer, as that order is not guaranteed. If a single module declares multiple providers for the same service, the order of providers in the descriptor is preserved when locating providers from that module, but you cannot infer a stable overall order across all modules.

The application should make an explicit choice based on business attributes:

```java
Optional<Codec> jsonCodec =
        ServiceLoader.load(Codec.class)
                .stream()
                .filter(p -> p.type().getSimpleName().contains("Json"))
                .map(ServiceLoader.Provider::get)
                .findFirst();
```

The snippet above illustrates filtering by provider type. In a real system, use metadata or service methods to evaluate capabilities, version, supported algorithms, or configuration policies, rather than relying on class names.

You should also handle the case where no provider exists. Depending on application requirements, you can fall back to a default implementation, report a configuration error, or disable the feature.

## 10. Common Errors When Locating Providers

### Missing uses

If the consuming module is an explicit named module and its descriptor does not declare `uses` for the service, ServiceLoader may throw a `ServiceConfigurationError`. Check the module calling `ServiceLoader.load` and add the exact service type to its descriptor.

### Provider module is not resolved

If a module has `provides` but is not present in the module layer being searched by the loader, the provider will not appear in the results. Check the module finder, module path, root modules, and how the configuration is built. For plugins or service binding, consider `resolveAndBind`.

### Incorrect module or service type name

The service names in `uses` and `provides` must refer to the exact same service type. The provider must be compatible with that service. Check the package, fully qualified name, and dependencies of the provider module.

### Service package is not exported

The consuming module needs to reference the service interface. The module owning the interface must export the package containing the service to the consuming module, and the consuming module must declare `requires` on that module.

### Provider cannot be instantiated

The provider class may lack a public no-argument constructor, be incompatible with the service, or throw an exception from its constructor/provider method. Inspect the `ServiceConfigurationError` and its root cause during instantiation.

### Searching the wrong ModuleLayer

`ServiceLoader.load(layer, service)` searches for providers only in the specified layer and its parent layers; it does not search providers in the unnamed module. If the provider resides in another layer, pass the right layer or use the appropriate class-loader overload.

## 11. Workflow for Designing and Verifying Service Binding

When building a plugin system with JPMS, you can proceed in this order:

1. **Define the service interface:** place the interface or abstract class in a stable API module.
2. **Export the service package:** allow consuming and provider modules to reference the service type.
3. **Declare uses:** the consuming module declares the exact service type in its descriptor.
4. **Declare provides:** each provider module declares the service and provider implementation.
5. **Verify observability:** ensure provider modules can be found by the appropriate module finder or module path.
6. **Resolve with service binding:** use resolution with binding when provider modules need to be automatically brought into the configuration.
7. **Define the ModuleLayer:** create the runtime layer from the resolved configuration.
8. **Create ServiceLoader:** use the class loader or layer matching how the application deploys plugins.
9. **Iterate and select:** handle multiple providers or the absence of providers.
10. **Handle errors:** watch for `ServiceConfigurationError`, and check provider constructors/provider methods and runtime dependencies.

You can inspect each JAR's descriptor:

```shell
jar --describe-module --file libs/codec-api.jar
jar --describe-module --file libs/codec-json.jar
jar --describe-module --file libs/application.jar
```

Cross-check the `uses`, `provides`, `requires`, and `exports` directives against your build configuration. Even a properly declared provider must still be present within the module graph or loader scope used to search for it.

## Conclusion

ServiceLoader locates implementations of a service based on providers observable in the runtime environment. With JPMS, the consuming module declares `uses`, the supplying module declares `provides ... with ...`, and service binding during resolution can bring provider modules and their dependencies into the module graph.

Once modules are defined in a ModuleLayer, `ServiceLoader.load(layer, service)` discovers providers in that layer and its parent layers. Loader creation and provider iteration happen lazily; the application must actively select an implementation and handle cases where no provider is available or a provider fails to instantiate.

The key takeaway is that `provides` describes where an implementation lives, the module graph determines which modules are resolved at runtime, and `ServiceLoader` performs discovery and instantiation within the appropriate loader/layer scope. By separating the service contract from its implementations, applications can be extended with plugins without directly depending on individual concrete providers.
