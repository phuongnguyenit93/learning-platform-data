# ServiceLoader Discovery and Lazy Providers

## Objectives

After this lesson, you will be able to:

- Explain how ServiceLoader discovers providers from the classpath and named modules.
- Choose the appropriate `ServiceLoader.load(...)` overload for a class loader or ModuleLayer.
- Distinguish provider discovery from provider instantiation.
- Use `iterator()` and `stream()` to consume providers on demand.
- Use `Provider.type()` to inspect metadata before calling `Provider.get()`.
- Understand caching, `reload()`, `ServiceConfigurationError`, and thread-safety limitations.

## 1. Discovery and Instantiation Are Two Different Steps

`ServiceLoader<S>` is a mechanism for finding and using implementations of a service type `S`. The application depends only on the service interface; providers can be added at packaging or deployment time.

For example, a service API:

~~~java
package com.example.codec;

public interface Codec {
    String name();
    byte[] encode(String input);
}
~~~

There may be multiple providers such as `JsonCodec`, `XmlCodec`, or `BinaryCodec`. The consumer does not need to instantiate concrete classes directly. It asks `ServiceLoader` to find providers for `Codec`:

~~~java
ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class);
~~~

Creating a `ServiceLoader` does not mean all providers have been instantiated. ServiceLoader locates providers using a mechanism suited to the environment, then creates instances when the application consumes providers. This approach lets the application avoid instantiating implementations it does not need.

Two concepts to keep separate:

- **Discovery:** determining which providers are configured and visible within the search scope.
- **Instantiation:** creating an instance of a provider so the application can invoke service methods.

Discovery also does not guarantee that every provider will succeed during instantiation. A provider may be discovered yet fail when the class is loaded or when the constructor/factory method runs.

## 2. Where Are Providers Declared?

How providers are registered depends on how the application is deployed.

### 2.1. Providers on the Classpath

For providers residing in an unnamed module, the library registers class names in a service configuration file:

~~~text
META-INF/services/com.example.codec.Codec
~~~

The file contents are the fully qualified names of each provider class, one name per line:

~~~text
com.example.codec.json.JsonCodec
com.example.codec.xml.XmlCodec
~~~

Comments can be added using the `#` character. Blank lines are ignored, and duplicate provider names do not create an additional provider.

For example, a JSON provider JAR contains:

~~~text
codec-json.jar
└── META-INF/
    └── services/
        └── com.example.codec.Codec
~~~

When the service configuration file is present on the classpath used for lookup, ServiceLoader reads this file to discover providers. Provider classes under the classpath mechanism must satisfy the provider class rules, including being a public class with a public no-argument constructor.

### 2.2. Providers in a Named Module

With JPMS, a provider is declared in the module descriptor using the `provides` directive:

~~~java
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.Codec
            with com.example.codec.json.JsonCodec;
}
~~~

The consumer module declares the service it uses:

~~~java
module com.example.codec.app {
    requires com.example.codec.api;

    uses com.example.codec.Codec;
}
~~~

In a named module, `uses` and `provides` are metadata that the module system uses to determine service relationships. There is no need to create `META-INF/services` for providers already registered via a module descriptor.

Multiple provider modules may provide the same service. ServiceLoader locates matching providers within the requested module layer or class loader scope.

## 3. Choosing Discovery Scope with ServiceLoader.load

ServiceLoader has several overloads to specify where to look for providers.

| Call | Search Scope |
|---|---|
| `ServiceLoader.load(Service.class)` | Uses the current thread's thread context class loader |
| `ServiceLoader.load(Service.class, classLoader)` | Uses the passed-in class loader |
| `ServiceLoader.load(layer, Service.class)` | Looks up providers in the specified ModuleLayer and its parent layers |
| `ServiceLoader.loadInstalled(Service.class)` | Uses the extension/platform class loader according to this API's mechanism |

Example with context class loader:

~~~java
ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class);
~~~

Example with explicit class loader:

~~~java
ClassLoader pluginLoader =
        Thread.currentThread().getContextClassLoader();

ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class, pluginLoader);
~~~

Example with custom module layer:

~~~java
ServiceLoader<Codec> loader =
        ServiceLoader.load(pluginLayer, Codec.class);
~~~

The overload accepting `ModuleLayer` is appropriate when the application creates a plugin layer via `ModuleLayer.defineModules...` and wants to find providers belonging to that layer. It avoids accidentally searching only via a class loader that does not represent the plugin layer.

In a named module, the module calling ServiceLoader must declare `uses` for the corresponding service. If this directive is missing, calling the API in a named module context can fail with `ServiceConfigurationError`.

## 4. Lazy Loading When Using iterator()

You can iterate over providers using an iterator:

~~~java
ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class);

Iterator<Codec> iterator = loader.iterator();

while (iterator.hasNext()) {
    Codec codec = iterator.next();

    System.out.println(codec.name());
}
~~~

ServiceLoader's iterator has two characteristics:

1. Previously cached provider instances are returned first in the order they were added to the cache.
2. Providers not yet loaded are located and instantiated when the iterator needs the next element; the new instance is added to the cache.

Therefore, the application can process providers one by one instead of being forced to instantiate all providers upfront. However, if the loop traverses the entire iterator, all providers discovered within that scope will eventually be consumed and instantiated.

If you only need the first provider, stop iteration early. Do not convert the iterator into a full list if your goal is to avoid instantiating the remaining providers.

## 5. Lazy Loading with stream() and Provider<S>

`ServiceLoader.stream()` returns a stream of `ServiceLoader.Provider<S>`, not a stream of service instances `S`:

~~~java
ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class);

Stream<ServiceLoader.Provider<Codec>> providers =
        loader.stream();
~~~

`Provider<S>` provides two key methods:

| Method | Result | Role |
|---|---|---|
| `type()` | `Class<? extends S>` | Inspect the provider type |
| `get()` | `S` | Obtain the service instance |

The useful feature of `stream()` is that the application can inspect provider metadata before requesting instance creation.

For example, selecting only providers whose class belongs to the JSON package:

~~~java
List<Codec> codecs = loader.stream()
        .filter(provider ->
                provider.type().getPackageName()
                        .equals("com.example.codec.json"))
        .map(ServiceLoader.Provider::get)
        .toList();
~~~

The pipeline executes when a terminal operation such as `toList()` is invoked. `filter` inspects `type()` first; `map(Provider::get)` is only executed for providers passing the filter condition. As a result, unsuitable providers can be excluded without calling `get()`.

You can sort based on class name before instantiation:

~~~java
List<Codec> codecs = loader.stream()
        .sorted(Comparator.comparing(
                provider -> provider.type().getName()))
        .map(ServiceLoader.Provider::get)
        .toList();
~~~

The order in which providers are discovered should not be treated as business priority order. If the application needs to prioritize JSON over XML, define explicit metadata or a priority contract and sort according to that rule.

## 6. Provider Factory Method in a Named Module

A named module can declare a provider via a public static method named `provider` with no parameters and a return type compatible with the service.

Example:

~~~java
package com.example.codec.json;

import com.example.codec.Codec;

public final class JsonCodecFactory {

    private JsonCodecFactory() {
    }

    public static Codec provider() {
        return new JsonCodec();
    }
}
~~~

Module descriptor:

~~~java
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.Codec
            with com.example.codec.json.JsonCodecFactory;
}
~~~

In this approach, the class listed after `with` is a factory class. It does not necessarily have to implement `Codec`; the `provider()` method creates and returns the actual implementation.

When using `ServiceLoader.Provider`:

- `Provider.get()` invokes the factory method to obtain the service instance.
- `Provider.type()` returns the declared return type of the factory method.
- Therefore, `type()` may return `Codec.class` instead of `JsonCodecFactory.class`.

This matters if the application filters providers by annotation or package. Place metadata on the type that `Provider.type()` actually returns and check the module descriptor to see whether a provider uses a constructor or a factory method.

## 7. Cache and reload()

ServiceLoader caches provider instances discovered through the iterator. When a subsequent iterator is created, cached instances are returned first; then ServiceLoader continues finding providers not yet loaded.

When the application needs to reload provider configuration, it can call:

~~~java
loader.reload();
~~~

`reload()` clears the current cache and resets the provider lookup state. Subsequent traversals can detect new providers if the class loader or configuration environment has changed in a way visible to ServiceLoader.

Several points to note:

- `reload()` does not itself install additional JARs or modules into a class loader/module layer.
- If the class loader cannot see the new provider, calling `reload()` will not make that provider appear.
- Do not call `reload()` while an iterator of the same loader is being traversed; the result of reloading during active iteration is undefined.
- `reload()` does not replace creating a new class loader or ModuleLayer when plugin deployment requires a different module loading scope.

Example:

~~~java
ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class, pluginLoader);

// Load and use existing providers
loader.forEach(codec ->
        System.out.println(codec.name()));

// Clear cache before the next traversal
loader.reload();

loader.forEach(codec ->
        System.out.println(codec.name()));
~~~

If plugins are deployed by version or need to be unloaded independently, consider creating a dedicated class loader or module layer per plugin lifecycle rather than relying solely on `reload()`.

## 8. Errors During Provider Discovery or Instantiation

ServiceLoader may throw `ServiceConfigurationError` when it detects an invalid provider configuration or cannot use a provider. Common causes include:

- Malformed service configuration file or invalid provider class name.
- Provider class cannot be found by the active class loader.
- Provider is not a subtype of the service.
- Provider class does not satisfy constructor or factory method rules.
- Constructor or factory method throws an exception.
- Named module is missing the `uses` directive or has an invalid provider declaration.

Example error handling at a plugin loading boundary:

~~~java
try {
    ServiceLoader.load(Codec.class, pluginLoader)
            .forEach(codec ->
                    System.out.println(codec.name()));
} catch (ServiceConfigurationError error) {
    logger.error("Unable to load a Codec provider", error);
}
~~~

Do not catch the error and ignore it silently. Log the offending provider or configuration so operators know why an implementation did not appear. If the application can continue when an optional provider is missing, decide on an explicit fallback policy.

Errors can occur while consuming the iterator/stream, not necessarily immediately upon calling `ServiceLoader.load(...)`. Therefore, place error handling around the code that actually traverses or retrieves instances.

## 9. Thread-Safety and Loader Lifecycle

`ServiceLoader` instances are not safe for concurrent use from multiple threads. The loader's internal cache and discovery state are not designed as a concurrent collection.

If multiple threads need to access services, you can:

- Create a separate loader per thread or per component, if the discovery scope allows.
- Complete discovery during a controlled initialization step, then publish an immutable list of service instances to threads.
- Use external synchronization if sharing a single loader is unavoidable.
- Explicitly manage class loader/module layer lifecycles to avoid retaining references to stopped plugins.

Also do not assume every call to `Provider.get()` returns the same singleton instance. A provider may create an instance via its constructor or factory method. If the application requires a singleton, define and manage instance lifecycle within the application itself or the provider contract.

## 10. Choosing iterator or stream?

| Need | Suitable Approach |
|---|---|
| Traverse each service instance in discovery order | `iterator()` or enhanced for |
| Process sequentially and stop at the first match | `iterator()` or stream with a short-circuit terminal operation |
| Filter by class, package, or annotation before creating instances | `stream()` and `Provider.type()` |
| Sort by provider metadata | `stream().sorted(...)` and only then call `get()` |
| Need all instances for batch processing | `stream().map(Provider::get).toList()` |
| Reload cache after class loader configuration changes | `reload()` and traverse again |

Remember that a terminal operation can cause a pipeline to consume providers. A pipeline without a terminal operation has not performed the full discovery and instantiation work yet.

## 11. Summary

ServiceLoader discovers providers from service configuration files on the classpath or from `provides` directives in named modules. The search scope is chosen via the `load(...)` overload, such as context class loader, explicit class loader, or ModuleLayer.

Discovery and instantiation happen lazily. The iterator creates instances when the next element is needed; stream returns `Provider<S>` so the application can inspect `type()` before calling `get()`. Caching allows reusing provider instances across iterator traversals, while `reload()` clears the cache and restarts lookup. Applications must handle `ServiceConfigurationError`, manage loader lifecycles, and avoid sharing a single ServiceLoader across multiple threads without synchronization.

References:

- [ServiceLoader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html)
- [ServiceLoader.Provider — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.Provider.html)
- [The Java Module System — JLS, Chapter 7](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html)
