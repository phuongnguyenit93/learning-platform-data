# Provider streams and lazy instantiation in ServiceLoader

## 1. Objectives

Since Java 9, `ServiceLoader` provides the `stream()` method to work with the list of providers via `ServiceLoader.Provider<S>`. This approach allows the application to inspect the service implementation class type, filter or select a provider, and only then request instance creation when truly needed.

The key point is to distinguish between **provider discovery**, **loading the provider class**, and **instantiating the service instance**. These three things do not necessarily happen at the same time. Provider streams help defer instance creation, which is especially useful when an application has many plugins or providers with resource-intensive constructors or factory methods.

After this lesson, you will be able to:

- Explain the roles of `ServiceLoader`, `ServiceLoader.Provider<S>`, and the service instance.
- Use `stream()` to inspect a provider's type before creating an instance.
- Filter providers by class and instantiate only the selected provider.
- Distinguish between Java Stream lazy evaluation and ServiceLoader lazy instantiation.

## 2. Three components to distinguish

When using ServiceLoader, separate the following three concepts:

| Component | Role |
| --- | --- |
| `ServiceLoader<S>` | Discovers and manages providers for the service type `S`. |
| `ServiceLoader.Provider<S>` | Represents a provider; allows inspecting the type and requesting a service instance. |
| `S` | The actual instance the application calls to use the functionality. |

Example:

```java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

var providers = loader.stream();
```

At the time `loader` and the `providers` pipeline are created, the application has not yet requested a concrete `Codec` instance. Each element supplied by `stream()` is a `Provider<Codec>` object, not a `Codec` object.

Two key methods of `Provider<S>` are:

- `type()`: returns the provider's class so the application can inspect the class name, annotations, or metadata on the class. This may cause the provider class to be loaded, but does not invoke the constructor or provider method to create a service instance.
- `get()`: requests a service instance from the provider. This is the point where the application actively moves into the instantiation phase.

Therefore, **knowing the provider class is not synonymous with having created a service instance**.

## 3. Service example in the Java Module System

Suppose the application has a `Codec` service and a provider `JsonCodec`.

### Module declaring the service API

The `module-info.java` file of the API module:

```java
module com.example.codec.api {
    exports com.example.codec.api;
}
```

Service interface:

```java
package com.example.codec.api;

public interface Codec {
    String format();

    String encode(String input);
}
```

### Module supplying the implementation

The provider module declares the implementation using the `provides ... with ...` directive:

```java
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.api.Codec
        with com.example.codec.json.JsonCodec;
}
```

The implementation can log in its constructor to observe the timing of instantiation:

```java
package com.example.codec.json;

import com.example.codec.api.Codec;

public final class JsonCodec implements Codec {

    public JsonCodec() {
        System.out.println("JsonCodec instantiated");
    }

    @Override
    public String format() {
        return "json";
    }

    @Override
    public String encode(String input) {
        return "encoded:" + input;
    }
}
```

### Module consuming the service

The module using the service declares `uses`:

```java
module com.example.app {
    requires com.example.codec.api;

    uses com.example.codec.api.Codec;
}
```

The application depends only on the service API. It does not need to import directly or declare `requires com.example.codec.json` to invoke ServiceLoader by implementation name. The provider module must be present on the module path and included in the module layer being used.

## 4. Inspecting the provider type without creating an instance

Use `stream()` combined with `Provider.type()` to obtain the list of classes:

```java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

List<Class<? extends Codec>> providerTypes = loader.stream()
    .map(provider -> provider.type())
    .toList();

providerTypes.forEach(type ->
    System.out.println(type.getName())
);
```

The pipeline above iterates over the providers and retrieves the corresponding classes. It does not call `Provider.get()`, so `JsonCodec`'s constructor is not called merely by retrieving the type.

You can use the class to inspect metadata before instantiation:

```java
loader.stream()
    .map(provider -> provider.type())
    .filter(type -> type.getSimpleName().endsWith("Codec"))
    .forEach(type -> System.out.println("Provider: " + type.getName()));
```

Note: retrieving `type()` may require loading the provider class and can raise a configuration error if the provider is invalid or cannot be loaded. Lazy instantiation does not mean all class discovery steps are deferred until after `get()`.

## 5. Instantiating only the selected provider

The clearest benefit of provider streams appears when there are multiple implementations, but the application only needs one suitable implementation.

```java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

Codec codec = loader.stream()
    .filter(provider ->
        provider.type().getSimpleName().equals("JsonCodec")
    )
    .findFirst()
    .map(ServiceLoader.Provider::get)
    .orElseThrow(() ->
        new IllegalStateException("JsonCodec not found")
    );

System.out.println(codec.format());
System.out.println(codec.encode("hello"));
```

Processing flow:

1. `loader.stream()` supplies the providers.
2. `filter(...)` inspects each provider's class. This check does not create a service instance.
3. `findFirst()` stops as soon as the first matching provider is found.
4. `map(Provider::get)` calls `get()` on the selected provider.
5. The provider's constructor or factory mechanism executes to supply the service instance.

If a provider is excluded at the filtering step, the application does not call `get()` for that provider. This is how to avoid instantiating unused implementations.

You can also select by annotation, marker interface, or package naming convention. For example:

```java
Optional<Codec> selected = loader.stream()
    .filter(provider ->
        provider.type().isAnnotationPresent(PreferredCodec.class)
    )
    .findFirst()
    .map(provider -> provider.get());
```

In this example, the annotation is read from the provider class. Only the first provider matching the condition is asked to create an instance.

## 6. Stream lazy evaluation vs. provider lazy instantiation

These two mechanisms are related but not identical:

**Java Stream lazy evaluation** means that intermediate operations such as `filter`, `map`, and `peek` do not run until there is a terminal operation, such as `toList()`, `findFirst()`, or `forEach()`.

**ServiceLoader.Provider lazy instantiation** means that the application can traverse and inspect provider types without creating service instances. An instance is requested only when `Provider.get()` is called.

Example:

```java
var stream = ServiceLoader.load(Codec.class)
    .stream()
    .filter(provider -> provider.type().getSimpleName().contains("Codec"));
```

The statement above only builds the pipeline. There is no terminal operation yet, so the pipeline has not traversed the providers.

When calling:

```java
List<ServiceLoader.Provider<Codec>> candidates = stream.toList();
```

The stream executes and the matching providers are collected. However, this operation still does not call `get()`, so it has not yet requested creating the service instances.

Only when calling:

```java
Codec first = candidates.get(0).get();
```

does the application request an instance from the first provider.

## 7. Comparing stream() with iterator()

Both approaches use ServiceLoader to iterate over providers, but the level of control differs.

| Traversal method | Value received | Can inspect provider type before creating an instance? |
| --- | --- | --- |
| `iterator()` or for-each loop | Service instance | Not through the standard iterator API; calling `next()` gets an instance. |
| `stream()` | `Provider<S>` | Yes; call `type()` first and only call `get()` when needed. |

Example using iterator:

```java
for (Codec codec : ServiceLoader.load(Codec.class)) {
    System.out.println(codec.format());
}
```

This approach fits when the application intentionally uses every implementation. When iterating with an iterator, each fetch of the next element supplies a service instance.

Example using a provider stream:

```java
ServiceLoader.load(Codec.class)
    .stream()
    .map(provider -> provider.type().getName())
    .forEach(System.out::println);
```

This approach fits when the application needs to inspect or select an implementation before creating an instance.

## 8. Points to keep in mind

- **Do not call `get()` too early:** If the goal is only to list classes, provider names, or annotations, use `type()`. Calling `get()` requests instance creation and may trigger expensive work.
- **Do not confuse class loading with object creation:** `type()` may cause a class to be loaded. That is still different from running a constructor or provider method.
- **Terminal operations determine when the Stream runs:** If you only build a pipeline and hold onto it, intermediate operations have not executed yet.
- **Do not rely on provider order as a priority policy:** If the application needs to choose a provider based on criteria, express those criteria explicitly with filters or selection logic.
- **Handle configuration errors:** ServiceLoader can throw `ServiceConfigurationError` when a provider declaration is wrong, a class cannot be found, or an instance cannot be created. Handle errors at an appropriate plugin-loading boundary.
- **Mind concurrency:** A `ServiceLoader` object is not designed to be modified or iterated concurrently by multiple threads without synchronization. If concurrent use is needed, manage the loader lifecycle and access safely.
- **Distinguish module path and classpath:** For named modules, the consumer declares `uses` and the provider declares `provides ... with ...`. For the classpath, providers are typically registered in `META-INF/services/<fully-qualified-service-name>`. Both approaches require the correct service type and discoverable providers in the runtime environment.

## 9. When should you use Provider streams?

Use `ServiceLoader.stream()` when the application needs one or more of the following:

- Having many plugins but wanting to instantiate only the plugin matching the current configuration.
- Needing to read annotations or metadata of an implementation before deciding to use it.
- Wanting to display the list of providers for diagnostics without instantiating all of them.
- Wanting to avoid side effects or overhead in constructors/provider methods of unselected implementations.

If the application definitely needs to run all implementations, looping over ServiceLoader may be simpler and easier to read. If conditional selection before instantiation is needed, provider streams give the appropriate control.

## 10. Key takeaways

- `ServiceLoader<S>` manages provider discovery for a service.
- `stream()` returns `Provider<S>` elements, not service instances directly.
- `Provider.type()` allows inspecting the provider class without requesting a service instance.
- `Provider.get()` is the operation that requests a service instance.
- Java Stream executes a pipeline only when there is a terminal operation; this is independent of whether providers are instantiated.

When reading ServiceLoader code, look for where `Provider.get()` is called. That location indicates when the application actually requests creating an implementation, while operations on `Provider.type()` generally serve prior discovery and selection.
