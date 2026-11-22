# Multiple Provider Implementations and Ordering

The Java Platform Module System (JPMS) integrates the service provider mechanism so that one module publishes an implementation of a service, while another module uses the service without directly depending on each implementation class. This mechanism is typically invoked via `ServiceLoader`.

A service can have one implementation or multiple implementations. Multiple providers can be declared within the same module, or supplied from several different modules. When multiple providers exist, the application needs to understand how Java discovers them and define its own policy for selecting the appropriate provider.

The key point is that **a module descriptor declares which providers exist; it is not the place to define business priority order**. If the application needs to choose a default implementation, express that criterion through an explicit API or configuration.

## 1. Service, Consumer, and Provider

Suppose an application needs to convert data into multiple formats. We define a service interface:

~~~java
package com.example.format.spi;

public interface Formatter {
    String format(String input);
}
~~~

The `Formatter` interface is the contract that implementations must follow. The module containing the service API can declare:

~~~java
module com.example.format.api {
    exports com.example.format.spi;
}
~~~

The consumer module uses the service via the `uses` directive:

~~~java
module com.example.app {
    requires com.example.format.api;

    uses com.example.format.spi.Formatter;
}
~~~

The `uses` directive states that the application module needs to discover providers of `Formatter`. It does not specify a concrete implementation and creates no direct dependency on any provider module.

A provider module declares an implementation with `provides ... with ...`:

~~~java
module com.example.format.json {
    requires com.example.format.api;

    provides com.example.format.spi.Formatter
        with com.example.format.json.JsonFormatter;
}
~~~

Implementation class:

~~~java
package com.example.format.json;

import com.example.format.spi.Formatter;

public final class JsonFormatter implements Formatter {
    public JsonFormatter() {
    }

    @Override
    public String format(String input) {
        return "{\"value\":\"" + input + "\"}";
    }
}
~~~

The provider class must meet service provider rules, such as having a public no-argument constructor as in the example above. JPMS also supports provider methods per `ServiceLoader` rules; when using that approach, the class listed after `with` provides a static `provider()` method returning the service type.

The consumer does not need to import or directly call `JsonFormatter`. It works solely with the `Formatter` interface.

## 2. Multiple Providers in the Same Module

A single module can supply multiple implementations for the same service. List multiple provider classes in the same `provides` directive, separated by commas:

~~~java
module com.example.format.builtin {
    requires com.example.format.api;

    provides com.example.format.spi.Formatter with
        com.example.format.builtin.JsonFormatter,
        com.example.format.builtin.XmlFormatter,
        com.example.format.builtin.TextFormatter;
}
~~~

All three classes must fulfill the `Formatter` contract and meet Java's provider rules.

The source structure might look like this:

~~~text
com.example.format.builtin/
├── module-info.java
└── com/example/format/builtin/
    ├── JsonFormatter.java
    ├── XmlFormatter.java
    └── TextFormatter.java
~~~

The package containing the implementations does not need to be exported just for `ServiceLoader` to discover providers declared in the descriptor. The module can keep the implementation classes inside an internal package, exposing only the service interface from the API module.

Multiple providers in one module are useful when implementations are released, tested, and managed as a single deployment unit.

## 3. Multiple Modules Providing the Same Service

A service can also be extended with independent provider modules. For example:

~~~text
application
    │
    ├── com.example.format.api
    │
    ├── com.example.format.json
    │
    ├── com.example.format.xml
    │
    └── com.example.format.csv
~~~

Each provider module has its own descriptor:

~~~java
// module com.example.format.json
module com.example.format.json {
    requires com.example.format.api;

    provides com.example.format.spi.Formatter
        with com.example.format.json.JsonFormatter;
}
~~~

~~~java
// module com.example.format.xml
module com.example.format.xml {
    requires com.example.format.api;

    provides com.example.format.spi.Formatter
        with com.example.format.xml.XmlFormatter;
}
~~~

~~~java
// module com.example.format.csv
module com.example.format.csv {
    requires com.example.format.api;

    provides com.example.format.spi.Formatter
        with com.example.format.csv.CsvFormatter;
}
~~~

The consumer only needs to know the API module:

~~~java
module com.example.app {
    requires com.example.format.api;

    uses com.example.format.spi.Formatter;
}
~~~

The provider modules are placed on the module path and included in the appropriate module graph. When the service loader searches for providers in a module layer, it can discover providers declared by modules in that layer.

This organization allows adding a new format by adding a provider module without forcing the consumer to change direct dependencies on implementation classes. The consumer still requires the API module, and the deployment configuration must place provider modules into the runtime environment.

## 4. Discovering Providers with ServiceLoader

The consumer uses `ServiceLoader` to locate implementations:

~~~java
package com.example.app;

import com.example.format.spi.Formatter;

import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<Formatter> loader =
            ServiceLoader.load(Formatter.class);

        for (Formatter formatter : loader) {
            System.out.println(formatter.format("hello"));
        }
    }
}
~~~

`ServiceLoader.load(Formatter.class)` creates a service loader for the service type. Provider discovery and instantiation happen lazily: providers are discovered and instantiated as the application iterates over the iterator or requests instances.

A few points to remember:

- The consumer declares `uses Formatter` in its module descriptor.
- Provider modules declare `provides Formatter with ...`.
- The consumer depends only on the service API, without needing `requires` for each provider module.
- Providers are created on demand; do not assume all providers are instantiated immediately when `ServiceLoader` is created.
- A `ServiceLoader` caches loaded providers. You can call `reload()` to clear the cache and allow rediscovering providers.
- `ServiceLoader` is not designed for multiple threads to concurrently mutate or iterate over a single instance without synchronization; if concurrent use is needed, manage instance creation and sharing appropriately.

If the application uses a custom `ModuleLayer` for plugins, you can locate services in that specific layer:

~~~java
ServiceLoader<Formatter> loader =
    ServiceLoader.load(pluginLayer, Formatter.class);
~~~

This is useful when plugins are loaded into a dedicated module layer. `ServiceLoader.load(Formatter.class)` and `ServiceLoader.load(layer, Formatter.class)` have different provider search scopes; choose the right layer containing the providers you need to use.

For providers on the classpath using the legacy mechanism, Java can read `META-INF/services/<service-name>` configuration files. In named modules, the standard way to declare providers is the `provides` directive in `module-info.java`.

## 5. Discovery Order Is Not Priority Order

When multiple providers exist, the following loop can return multiple implementations:

~~~java
for (Formatter formatter : ServiceLoader.load(Formatter.class)) {
    // process each provider
}
~~~

However, you should not treat the first provider returned as a rule for picking a default implementation if the application has not defined such a policy.

A module descriptor has no attribute like `priority = 1` for the `provides` directive. The list of classes after `with` only declares the service's providers; declaration order or discovery order is not a business priority contract that the application should rely on.

For example, if the application needs to pick the JSON formatter as default, do not rely on `JsonFormatter` happening to be returned first. Express priority in the service API, metadata, or application configuration.

Three scenarios should be distinguished:

1. **Iterate all providers:** order does not matter if every implementation is processed independently.
2. **Select one provider:** an explicit selection policy is needed, such as configuring the provider name or priority level.
3. **Run multiple providers in a pipeline:** pipeline ordering must be defined in the application, not inferred from descriptors.

## 6. Defining Priority in the Service API

If the application needs to rank providers, a priority method can be added to the service interface:

~~~java
package com.example.format.spi;

public interface Formatter {
    String format(String input);

    // Lower number has higher priority.
    default int priority() {
        return 100;
    }
}
~~~

Providers can override the priority level:

~~~java
public final class JsonFormatter implements Formatter {
    @Override
    public String format(String input) {
        return "{\"value\":\"" + input + "\"}";
    }

    @Override
    public int priority() {
        return 10;
    }
}
~~~

~~~java
public final class XmlFormatter implements Formatter {
    @Override
    public String format(String input) {
        return "<value>" + input + "</value>";
    }

    @Override
    public int priority() {
        return 20;
    }
}
~~~

The consumer can retrieve providers and sort them by policy:

~~~java
List<Formatter> formatters =
    ServiceLoader.load(Formatter.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .sorted(
            Comparator.comparingInt(Formatter::priority)
                .thenComparing(p -> p.getClass().getName())
        )
        .toList();
~~~

In this example:

- Lower priority values come first.
- If two providers have the same priority, the class name serves as a secondary criterion so the result order is deterministic.
- `Provider::get` instantiates the instance; sorting by an instance method will therefore load the iterated providers.

If class name ordering has no meaning for the product, replace the tie-breaker with another business rule or reject duplicate priorities. For example, if the application requires only a single provider at the highest priority:

~~~java
List<Formatter> candidates =
    ServiceLoader.load(Formatter.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .toList();

Formatter selected = candidates.stream()
    .min(Comparator.comparingInt(Formatter::priority))
    .orElseThrow(() ->
        new IllegalStateException("No Formatter provider is available"));
~~~

This snippet selects the provider with the smallest priority value. If multiple providers share the same lowest priority value, `min` returns one element according to the current iteration order. If a tie is a configuration error, the application should check and report an error when multiple candidates share the best priority, rather than accepting a result that depends on discovery order.

## 7. Selecting a Provider via Configuration

Not every service needs priority encoded in the interface. The application can let configuration specify the desired provider.

Example configuration file:

~~~properties
formatter.default=com.example.format.json.JsonFormatter
~~~

The consumer can retrieve the provider list and select by class name:

~~~java
String configuredName =
    System.getProperty("formatter.default");

Formatter selected = ServiceLoader.load(Formatter.class)
    .stream()
    .map(ServiceLoader.Provider::get)
    .filter(provider ->
        provider.getClass().getName().equals(configuredName))
    .findFirst()
    .orElseThrow(() ->
        new IllegalStateException(
            "Configured Formatter provider was not found: "
                + configuredName));
~~~

In a real system, read configuration from the application's configuration source, validate the value, and report a clear error if the provider does not exist. Class name is a simple configuration option; larger systems can use a stable provider ID exposed by the service interface to avoid depending on class names.

Providers can be selected by:

- A stable ID returned by the provider.
- Priority level or capabilities.
- Input/output formats supported by the provider.
- Environment or tenant configuration.
- Fallback rules when the primary provider is unavailable.

The policy must clearly define how to handle no provider, multiple matching providers, or a provider failing during instantiation.

## 8. ServiceLoader.Provider and Streams

Beyond iterators, `ServiceLoader` provides `stream()` to access provider descriptor objects:

~~~java
ServiceLoader<Formatter> loader =
    ServiceLoader.load(Formatter.class);

loader.stream().forEach(provider -> {
    Class<? extends Formatter> providerType = provider.type();
    System.out.println(providerType.getName());
});
~~~

`ServiceLoader.Provider` lets you inspect the provider type before requesting an instance via `get()`. This is useful when the application needs to filter by metadata or inspect classes before instantiation.

Example of filtering providers by a custom annotation:

~~~java
loader.stream()
    .filter(provider ->
        provider.type().isAnnotationPresent(PreferredFormatter.class))
    .map(ServiceLoader.Provider::get)
    .forEach(formatter ->
        System.out.println(formatter.format("hello")));
~~~

Annotations and filtering rules are mechanisms defined by the application itself. JPMS does not automatically interpret a `PreferredFormatter` annotation, nor does it automatically pick marked providers. When using metadata, maintain a clear contract and check for cases where zero or multiple providers carry the marker.

Note that `stream()` does not mean every operation is free: calling `Provider.get()` instantiates the provider. If you only need to inspect the type, use `Provider.type()` before deciding to instantiate.

## 9. Common Mistakes with Multiple Providers

**Consumer forgets to declare `uses`.** The consumer module must declare the service type in its descriptor. If missing, using the service in a named module may fail when the service loader checks usage permissions.

**Provider module is not in the searched module layer.** The descriptor has the right `provides`, but the provider module has not been placed on the module path or in the corresponding custom layer. Check the runtime configuration and the layer passed to `ServiceLoader`.

**Provider class does not satisfy instantiation rules.** Check whether the provider class has a valid public no-argument constructor or a valid provider method.

**Provider does not properly implement the service.** Check the return type of the provider method or the inheritance/`implements` relationship between the implementation and the service interface.

**Consumer depends directly on the implementation.** If the consumer only needs the service, have the consumer depend on the API module and declare `uses`. Direct dependencies on individual providers reduce the extensibility of SPI.

**Relying on returned provider order.** If business logic requires a default implementation, use explicit priority or configuration.

**Multiple providers share the same priority without a tie-breaker.** Selection results may be unstable or fail to reflect intent. Choose a secondary rule or report an error on conflict.

**Instantiating all providers when only one is needed.** `stream().map(Provider::get)` instantiates every iterated provider. If there are many heavy plugins, filter metadata before calling `get()` when possible, or design a dedicated registry/lifecycle.

## 10. Inspecting Service Providers in Modular JARs

You can inspect a provider module's descriptor after packaging:

~~~bash
jar --describe-module --file build/libs/format-json.jar
~~~

The module info should show the provided service, for example:

~~~text
provides com.example.format.spi.Formatter
    with com.example.format.json.JsonFormatter
~~~

For a module containing multiple providers, the `provides` section should list the corresponding implementations.

At runtime, ensure that:

- The API module is present and resolved.
- The consumer module declares `uses` for the exact service type.
- Provider modules are included in the module layer being searched.
- Provider dependencies are also resolved.
- The service interface and provider implementations are version-compatible.

If using a plugin layer, verify that the created layer contains the expected provider modules. Simply having a modular JAR on disk does not mean it is automatically added to every module layer.

## 11. When to Use Multiple Providers?

Multiple providers fit well when a service has multiple interchangeable implementations, such as:

- Multiple serializer/deserializer formats.
- Multiple drivers or adapters for external systems.
- Multiple storage strategies.
- Multiple processors by data type.
- Plugins installed independently per deployment environment.

If implementations do not share a single stable contract or have completely different lifecycles, consider designing separate service APIs instead of cramming everything into an overly broad service interface.

Service providers reduce direct coupling between consumers and implementations. When multiple providers exist, the responsibility for picking one provider or orchestrating multiple providers belongs to the application's policy. The module descriptor only declares service relationships; it does not replace a product's registry, configuration, or priority rules.

## 12. Self-Check

When designing a service with multiple implementations, answer these questions:

1. Which API module contains the service interface, and is that package exported?
2. Has the consumer module declared `uses` for the exact service type?
3. Has each provider module declared `provides ... with ...`?
4. Are there multiple providers in one module or multiple independent provider modules?
5. Do providers have valid constructors or provider methods?
6. Is runtime searching the boot layer or which custom module layer?
7. Does the application need to iterate all providers, select one provider, or run them as a pipeline?
8. If selecting one provider, which priority, ID, or configuration decides the result?
9. If two providers share the same priority or no provider exists, how does the application handle it?

By distinguishing provider declarations, `ServiceLoader`'s discovery mechanism, and the application's selection policy, you can extend a system with multiple implementations while keeping consumers loosely coupled and selection behavior explicit.
