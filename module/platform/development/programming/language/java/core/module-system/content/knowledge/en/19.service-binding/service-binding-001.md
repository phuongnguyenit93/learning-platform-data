# Binding service providers into the module graph

## Objectives

After this lesson, you will be able to declare a service consumer and provider using JPMS, explain how service binding locates provider modules, use `Configuration.resolveAndBind(...)` to bring providers into the module graph, and use `ServiceLoader` to locate and instantiate providers at runtime.

## 1. Services in Java and the role of the module graph

A service is a contract that multiple implementations can provide. A consumer depends on the service interface, while a provider module supplies one or more implementations. This structure lets an application select an implementation based on the environment, configuration, or installed components without requiring the consumer to depend directly on each provider.

In Java, `ServiceLoader<S>` is the standard API for locating providers of service type `S`. In JPMS, two directives describe this relationship:

- `uses` declares that a module requires a service type.
- `provides ... with ...` declares that a module supplies a service type using one or more provider classes.

Service binding is a step during module resolution. The module system finds provider modules matching the services used by modules in the graph, then adds the provider modules and their required dependencies to the configuration. As a result, providers can be brought into a layer without the consumer declaring `requires` directly on each provider.

Two phases must be distinguished:

1. **Service binding** decides which provider modules belong to the configuration/module graph.
2. **Service loading** uses `ServiceLoader` to locate providers and create instances when the application needs them.

The fact that a provider module has been bound into the graph does not mean the provider object has been instantiated.

## 2. Declaring the service API, consumer, and provider

The example uses a `Formatter` service to transform strings.

### Service API module

Structure:

~~~text
com.acme.spi/
  module-info.java
  com/acme/spi/Formatter.java
~~~

`module-info.java`:

~~~java
module com.acme.spi {
    exports com.acme.spi;
}
~~~

Service interface:

~~~java
package com.acme.spi;

public interface Formatter {
    String format(String input);
}
~~~

The package containing the service interface is exported so that consumers and providers can reference the `Formatter` type.

### Consumer module

Structure:

~~~text
com.acme.app/
  module-info.java
  com/acme/app/Main.java
~~~

`module-info.java`:

~~~java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.Formatter;
}
~~~

The two directives have distinct meanings:

- `requires com.acme.spi` creates a dependency so the consumer can read the service API.
- `uses com.acme.spi.Formatter` declares that the consumer uses this service and enables service binding to locate modules that provide it.

The consumer does not need to declare `requires com.acme.provider.upper`. This is the key point: the consumer depends on the service API abstraction, not on the list of implementations.

### Provider module

Structure:

~~~text
com.acme.provider.upper/
  module-info.java
  com/acme/provider/upper/UppercaseFormatter.java
~~~

`module-info.java`:

~~~java
module com.acme.provider.upper {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.provider.upper.UppercaseFormatter;
}
~~~

The provider module needs to read the module containing the service interface, because the implementation references `Formatter`. The `provides` directive registers the implementation with the service type.

Implementation:

~~~java
package com.acme.provider.upper;

import com.acme.spi.Formatter;
import java.util.Locale;

public final class UppercaseFormatter implements Formatter {
    public UppercaseFormatter() {
    }

    @Override
    public String format(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

With this common declaration style, the provider class is a public class implementing the service interface and having a public no-argument constructor so `ServiceLoader` can instantiate it.

A service can have multiple provider classes:

~~~java
provides com.acme.spi.Formatter with
    com.acme.provider.upper.UppercaseFormatter,
    com.acme.provider.lower.LowercaseFormatter;
~~~

Providers can reside in the same module or be supplied by multiple different modules. The package containing the implementation does not need to be exported merely for `ServiceLoader` to use the provider declared in the module descriptor.

## 3. Provider methods in module descriptors

In addition to a provider class directly implementing the service interface, JPMS also supports provider methods. In that case, the provider class declares a public static method named `provider`, taking no parameters and returning a type compatible with the service type.

Example:

~~~java
package com.acme.provider.json;

import com.acme.spi.Formatter;

public final class FormatterProvider {
    private FormatterProvider() {
    }

    public static Formatter provider() {
        return new JsonFormatter();
    }
}
~~~

Module descriptor:

~~~java
module com.acme.provider.json {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.provider.json.FormatterProvider;
}
~~~

In this case, `FormatterProvider` is the provider class declared in the directive; the object received by the service loader is the return value from the `provider()` method. This approach is useful when creating the implementation requires a factory, configuration, or internal implementation selection.

Do not confuse the provider class name in the directive with the final service object type: when using a provider method, the method must return the service type or a compatible subtype.

## 4. `resolve` and `resolveAndBind`

`Configuration` represents the result of module resolution. Two commonly used methods are:

- `resolve(...)` resolves the root modules along with dependencies declared with `requires`.
- `resolveAndBind(...)` performs resolution and adds matching service provider modules for the services used in the graph.

If only `resolve` is used, provider modules are not automatically added to the graph just because a module has a `uses` directive. If you want the module system to locate and bind provider modules during resolution, use `resolveAndBind`.

Example of creating a configuration for an application:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

Configuration configuration =
        ModuleLayer.boot()
                .configuration()
                .resolveAndBind(
                        ModuleFinder.of(),
                        finder,
                        Set.of("com.acme.app"));
~~~

In the example:

- `mods` is the directory containing module JARs or exploded modules such as `com.acme.app`, `com.acme.spi`, and `com.acme.provider.upper`.
- `ModuleFinder.of(Path.of("mods"))` creates a finder to locate modules in that directory.
- The first `ModuleFinder.of()` is an empty finder placed before the parent configurations.
- `Set.of("com.acme.app")` specifies the root module to launch.
- The boot layer's configuration is the parent configuration; platform modules already present in the boot layer continue to be used from the parent.

When resolving the root `com.acme.app`, the module system processes dependencies such as `com.acme.spi`, reads the `uses` directive, finds modules with the corresponding `provides` directive, and adds the provider module along with its dependencies into the configuration. The binding process continues when modules newly added to the graph also use other services.

Discovered modules must have valid descriptors and resolvable dependencies. If a module is missing, a dependency cannot be resolved, or the graph violates JPMS rules, the process can fail with errors such as `FindException` or `ResolutionException`.

## 5. Checking that provider modules have been bound

You can inspect the modules in a configuration using `Configuration.modules()`:

~~~java
configuration.modules().stream()
        .map(resolvedModule -> resolvedModule.name())
        .sorted()
        .forEach(System.out::println);
~~~

With the example above, the list might include:

~~~text
com.acme.app
com.acme.spi
com.acme.provider.upper
~~~

The exact output depends on the actual modules and dependencies in the `mods` directory. The point to verify is that the provider module has appeared in the configuration even though the consumer did not declare `requires com.acme.provider.upper`.

You can query for a specific module:

~~~java
boolean providerWasBound = configuration
        .findModule("com.acme.provider.upper")
        .isPresent();

System.out.println(providerWasBound);
~~~

`findModule` returns an `Optional<ResolvedModule>`. The result tells you whether the module is in this configuration; it does not indicate whether a provider object has been created.

## 6. Creating a layer from a configuration

After obtaining a configuration, the application can create a new layer:

~~~java
ModuleLayer layer =
        ModuleLayer.boot().defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader());
~~~

The new layer contains the modules resolved in the configuration and uses one class loader for the modules defined in that layer. Modules in the boot layer can still be referenced through the parent layer relationship.

You can check the provider module in the layer:

~~~java
Module providerModule = layer
        .findModule("com.acme.provider.upper")
        .orElseThrow();

System.out.println(providerModule.getName());
System.out.println(providerModule.getLayer() == layer);
~~~

Service binding belongs to the configuration creation phase; defining a layer brings that configuration into runtime. If an application only runs modules on the boot layer, the JVM already created the initial layer during startup and you do not need to create a new layer yourself.

## 7. Locating and using providers with `ServiceLoader`

In code belonging to the consumer module `com.acme.app`, use `ServiceLoader` to obtain providers:

~~~java
package com.acme.app;

import com.acme.spi.Formatter;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<Formatter> providers =
                ServiceLoader.load(Formatter.class);

        for (Formatter formatter : providers) {
            System.out.println(formatter.format("Java modules"));
        }
    }
}
~~~

Because `Main` belongs to the `com.acme.app` module, this module has declared `uses com.acme.spi.Formatter`. When running in the corresponding module layer, `ServiceLoader.load(Formatter.class)` searches for provider modules in the caller's layer and its ancestor layers.

If you are managing layers explicitly, you can specify the layer:

~~~java
ServiceLoader<Formatter> providers =
        ServiceLoader.load(layer, Formatter.class);
~~~

This call must originate from a module that declares `uses` for the service type. For example, call it from code belonging to `com.acme.app` if that module has the `uses com.acme.spi.Formatter` directive.

`ServiceLoader` typically instantiates providers lazily: a provider is created when the iterator reaches that provider. You can use `stream()` to work with `ServiceLoader.Provider<S>` objects before calling `get()` to obtain the service instance:

~~~java
ServiceLoader.load(Formatter.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .forEach(formatter ->
                System.out.println(formatter.format("JPMS")));
~~~

Service binding does not replace `ServiceLoader`. Binding ensures that provider modules are present in the graph; `ServiceLoader` performs discovery and instantiation when the program needs them. If a module has been bound but the provider cannot be instantiated or is misconfigured, iterating over providers can throw a `ServiceConfigurationError`.

## 8. Service binding with multiple providers and multiple services

A module can use multiple services:

~~~java
module com.acme.app {
    requires com.acme.spi;
    requires com.acme.metrics;

    uses com.acme.spi.Formatter;
    uses com.acme.metrics.MetricsSink;
}
~~~

A provider module can also provide multiple services:

~~~java
module com.acme.adapters {
    requires com.acme.spi;
    requires com.acme.metrics;

    provides com.acme.spi.Formatter
        with com.acme.adapters.JsonFormatter;

    provides com.acme.metrics.MetricsSink
        with com.acme.adapters.ConsoleMetricsSink;
}
~~~

When resolving and binding `com.acme.app`, the module system can add `com.acme.adapters` because this module provides the services that the graph uses. The provider's dependencies are also resolved like regular module dependencies.

If there are multiple providers for a service, `ServiceLoader` may return multiple providers. You should not build business logic that depends on provider ordering unless the application defines its own selection rule. If only one implementation is allowed, check the provider count and handle the zero-provider or multiple-provider cases explicitly.

## 9. Module path, class path, and limits of service binding

Service providers in a named module are declared with the `provides` directive in `module-info.java`. When using the module path and wanting provider modules to be automatically added to the configuration via service binding, make sure the provider modules are in the module finders used during resolution.

Traditional class-path applications can register providers using the file:

~~~text
META-INF/services/com.acme.spi.Formatter
~~~

This file contains the fully qualified names of provider classes, one per line. This mechanism still plays a role for providers on the class path / unnamed module and in compatibility scenarios. It differs from declaring `provides` in a module descriptor and does not automatically bring a named provider module into the configuration via service binding.

Automatic modules are also named modules, but compatibility rules and service metadata handling may differ from explicit modules. For newly designed JPMS applications, `uses` and `provides` should be declared explicitly in the module descriptor so the graph and service contract are easy to verify.

## 10. Debugging when providers do not appear

When `ServiceLoader` does not find providers as expected, check in this order:

1. **Service type**: do the consumer and provider reference the exact same service API module/type?
2. **Consumer descriptor**: has the module calling `ServiceLoader` declared `uses` for the right service type?
3. **Provider descriptor**: has the provider module properly declared `provides Service with Provider`?
4. **Provider dependencies**: does the provider module `requires` the module containing the service API?
5. **Module finder**: can the finder used in `resolveAndBind` locate the provider module?
6. **Configuration**: does `configuration.findModule("...")` return the provider module?
7. **Layer**: is the provider module in the layer passed to `ServiceLoader.load(layer, service)`, or in an appropriate ancestor layer?
8. **Provider construction**: does the provider class satisfy instantiation requirements or is the provider method valid?

Some common mistakes:

- Using `resolve` while expecting provider modules to be bound automatically.
- Forgetting `uses` in the consumer module.
- Forgetting `provides` in the provider module or writing the wrong service type/provider class.
- The provider module not being in the module finder used for resolution.
- The provider module having unresolvable dependencies.
- Calling `ServiceLoader` from a named module that does not declare `uses`.
- Binding the provider into a configuration, but looking up the service in a different layer that does not contain that provider.

## Key Takeaways

`uses` describes the consumer's service need; `provides ... with ...` describes the provider's implementation. `Configuration.resolveAndBind(...)` resolves dependencies and automatically adds matching provider modules to the module graph. After creating a layer, `ServiceLoader` discovers and instantiates provider instances. The consumer only needs to depend on the service API, while providers are selected through the module system's binding and loading mechanisms.
