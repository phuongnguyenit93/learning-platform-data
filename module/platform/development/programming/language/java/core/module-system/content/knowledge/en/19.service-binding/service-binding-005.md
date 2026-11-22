# Service binding with multiple providers

## Objectives

After this lesson, you will be able to:

- Explain why a service can have multiple providers in the module system.
- Distinguish between multiple providers declared in the same module and providers residing in different modules.
- Understand the role of the `uses` and `provides` directives and the service binding step during module resolution.
- Use `Configuration.resolveAndBind()` and `ServiceLoader` to locate multiple providers.
- Handle provider ordering deliberately rather than relying on discovery order.

## 1. A service can have multiple providers

In the Java Platform Module System (JPMS), a service is an abstraction that a consuming module wants to use. A provider is an implementation supplying concrete capability for that service.

A service can have multiple implementations at the same time. For example, an application needs a data formatting service and can use different providers:

- A JSON provider converts data to JSON.
- An XML provider converts data to XML.
- A YAML provider converts data to YAML.

The providers implement the same service interface, so the consuming module only needs to know the service API. It does not need to depend directly on each implementation module.

There are two common ways to organize this:

1. One provider module declares multiple provider classes in a single `provides` directive.
2. Multiple separate provider modules each declare `provides` for the same service.

Both approaches can coexist in the same module graph.

## 2. Declaring a service API

Suppose the service API has the module name `com.example.format.api` and exports the package containing the interface:

~~~java
module com.example.format.api {
    exports com.example.format;
}
~~~

Service interface:

~~~java
package com.example.format;

public interface Formatter {
    String format(String input);
}
~~~

The API module only defines the contract. It does not need to know how the JSON or XML providers are implemented.

Both the consuming module and the providers need to read the API module. Therefore, each module using the service interface declares `requires com.example.format.api;`.

## 3. Multiple providers in different modules

### 3.1. JSON provider

The JSON provider is placed in its own module:

~~~java
module com.example.format.provider.json {
    requires com.example.format.api;

    provides com.example.format.Formatter
            with com.example.format.json.JsonFormatter;
}
~~~

Implementation:

~~~java
package com.example.format.json;

import com.example.format.Formatter;

public final class JsonFormatter implements Formatter {

    public JsonFormatter() {
    }

    @Override
    public String format(String input) {
        return "{\"value\":\"" + input + "\"}";
    }
}
~~~

### 3.2. XML provider

The XML provider also has its own module:

~~~java
module com.example.format.provider.xml {
    requires com.example.format.api;

    provides com.example.format.Formatter
            with com.example.format.xml.XmlFormatter;
}
~~~

Implementation:

~~~java
package com.example.format.xml;

import com.example.format.Formatter;

public final class XmlFormatter implements Formatter {

    public XmlFormatter() {
    }

    @Override
    public String format(String input) {
        return "<value>" + input + "</value>";
    }
}
~~~

Both provider modules declare the same service in the `provides` directive, but point to different implementations. Each provider class in this example is public and has a public no-argument constructor.

### 3.3. Service consumer module

The application module declares the API module and the service it uses:

~~~java
module com.example.format.app {
    requires com.example.format.api;

    uses com.example.format.Formatter;
}
~~~

The `uses` directive tells the module system that the application uses the `Formatter` service. The application does not need to declare `requires com.example.format.provider.json;` or `requires com.example.format.provider.xml;` merely to locate providers.

This is the key point of service binding: the consuming module depends on an abstraction, while providers can be added through module resolution.

## 4. Service binding during module resolution

Service binding is the step that expands the module graph based on the services that resolved modules declare they use.

Suppose the initial module graph contains the application and the API module:

~~~text
com.example.format.app
        |
        | requires
        v
com.example.format.api
~~~

The application declares:

~~~java
uses com.example.format.Formatter;
~~~

If the provider modules are observable in the input module set, service binding can add both providers to the graph:

~~~text
                     +-------------------------------+
                     |                               |
                     v                               v
com.example.format.provider.json       com.example.format.provider.xml
                     |                               |
                     +---------------+---------------+
                                     |
                                     | provides Formatter
                                     v
                           com.example.format.Formatter
                                     ^
                                     |
                                     | uses
                                     |
                           com.example.format.app
~~~

With multiple providers, the system does not need to pick a single provider during the binding step. All matching and observable provider modules can be added to the module graph.

When provider modules are added to the graph, dependencies declared by the providers via `requires` are also resolved. The service binding process continues until no new provider modules are added.

### 4.1. `resolve()` and `resolveAndBind()`

The `java.lang.module.Configuration` API provides two methods with different meanings:

| Method | Behavior |
|---|---|
| `resolve(...)` | Resolves the graph based on root modules and `requires` dependencies. |
| `resolveAndBind(...)` | Resolves the graph and additionally performs service binding based on `uses` / `provides` directives. |

Therefore, when building a module configuration manually and wanting matching provider modules to be automatically brought into the graph based on services, use `resolveAndBind()`.

Service binding can only add providers observable by the module finders or parent configurations. If a provider JAR is not in the supplied module path/finders, or if the module does not declare a matching provider, it will not appear in the graph automatically.

## 5. Creating a ModuleLayer with multiple providers

The following example creates a new layer from a modules directory. The `mods` directory is assumed to contain the API, app, JSON provider, and XML provider modules as modular JARs or exploded modules.

~~~java
import com.example.format.Formatter;

import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;

public class LayerBootstrap {

    public static void main(String[] args) {
        Path modulesPath = Path.of("mods");

        ModuleFinder finder = ModuleFinder.of(modulesPath);

        Configuration configuration =
                ModuleLayer.boot()
                        .configuration()
                        .resolveAndBind(
                                ModuleFinder.of(),
                                finder,
                                Set.of("com.example.format.app"));

        ModuleLayer layer =
                ModuleLayer.boot()
                        .defineModulesWithOneLoader(
                                configuration,
                                ClassLoader.getSystemClassLoader());

        ServiceLoader<Formatter> loader =
                ServiceLoader.load(layer, Formatter.class);

        loader.forEach(formatter ->
                System.out.println(formatter.format("hello")));
    }
}
~~~

Main steps:

1. `ModuleFinder.of(modulesPath)` creates a module finder for the directory containing the modules.
2. `resolveAndBind(...)` starts from the root module `com.example.format.app`, resolves dependencies, and adds matching provider modules.
3. `defineModulesWithOneLoader(...)` defines the resolved modules in a new layer.
4. `ServiceLoader.load(layer, Formatter.class)` locates service providers belonging to the specified layer.
5. Iterating the loader receives instances from the discovered providers.

In the example, the first `ModuleFinder.of()` is an empty finder in the search position before the parent configuration. The second finder contains the application's modules. If the API module is already in the boot layer, that dependency can be satisfied from the parent configuration; if not, place the API module in the input modules directory.

Note that `resolveAndBind()` only resolves the module graph. It does not instantiate providers. Instantiation happens when the application consumes `ServiceLoader`, such as via `forEach()`, an iterator, or a stream.

## 6. Multiple providers in the same module

JPMS also allows a single module to declare multiple provider classes for the same service in one `provides` directive.

Example:

~~~java
module com.example.format.provider.bundle {
    requires com.example.format.api;

    provides com.example.format.Formatter
            with com.example.format.json.JsonFormatter,
                 com.example.format.xml.XmlFormatter;
}
~~~

In this case, one provider module packages both implementations. When this module is resolved into a layer, `ServiceLoader` can find both provider classes.

The two ways of organizing can be distinguished as follows:

| Organization | Example | Unit added to the module graph |
|---|---|---|
| Multiple modules, one provider each | `provider.json`, `provider.xml` | Each provider module |
| One module, multiple provider classes | `provider.bundle` declaring two classes | One provider module; the loader finds the declared provider classes |

Choose the organization based on packaging and deployment needs. Splitting modules enables independent distribution of providers; grouping multiple providers into one module lets them be deployed as a single unit.

## 7. Receiving and handling multiple providers with ServiceLoader

Once providers are in the layer searched by the loader, the application can retrieve all providers:

~~~java
ServiceLoader<Formatter> loader =
        ServiceLoader.load(Formatter.class);

for (Formatter formatter : loader) {
    System.out.println(formatter.format("hello"));
}
~~~

In an application using a custom layer, use the overload taking a layer:

~~~java
ServiceLoader<Formatter> loader =
        ServiceLoader.load(layer, Formatter.class);
~~~

If you want to inspect provider types before creating instances, use `stream()`:

~~~java
loader.stream()
        .filter(provider ->
                provider.type().getPackageName()
                        .startsWith("com.example.format"))
        .map(ServiceLoader.Provider::get)
        .forEach(formatter ->
                System.out.println(formatter.format("hello")));
~~~

`stream()` returns `ServiceLoader.Provider<Formatter>` objects. The application can use `type()` to inspect the provider type and only then call `get()` for selected providers.

### 7.1. Do not rely on discovery order

You should not assume providers are always returned in JSON-then-XML order, or in the order declared in the module descriptor. Provider discovery order is not a contract for an application to rely on.

If a deterministic order is needed, sort explicitly before obtaining instances:

~~~java
loader.stream()
        .sorted((left, right) ->
                left.type().getName()
                        .compareTo(right.type().getName()))
        .map(ServiceLoader.Provider::get)
        .forEach(formatter ->
                System.out.println(formatter.format("hello")));
~~~

If business order needs to be based on priority, define explicit priority metadata/contract in the service API or provider, then sort according to that rule. Class names are only appropriate when lexicographical order is genuinely what the application wants.

## 8. Situations to check

When a provider does not appear in the results, check in order:

- Has the consumer module declared `uses ServiceType;`?
- Has the provider module properly declared `provides ServiceType with ProviderClass;`?
- Is the provider module observable via a module finder or parent configuration?
- Was the provider module added to the configuration/layer currently in use?
- Is the application calling the right `ServiceLoader.load(...)` overload for the boot layer or custom layer?
- Does the provider class follow `ServiceLoader`'s provider rules and can it be instantiated?

A common mistake is merely placing the provider JAR in a directory on disk and expecting the loader to find it automatically. The provider must belong to the module configuration/layer being searched by the loader.

During iteration or instantiation, an invalid provider configuration can lead to a `ServiceConfigurationError`. Handle the error at an appropriate application boundary while preserving cause information to diagnose which provider failed.

## 9. Summary

A service can be provided by multiple provider classes in the same module or by multiple independent provider modules. Consumers declare `uses` to express their need for a service; provider modules declare `provides ... with ...` to register implementations.

When you need to resolve a module graph with service binding, `Configuration.resolveAndBind()` adds matching observable provider modules. Once modules are defined in a layer, `ServiceLoader` locates and instantiates providers. Applications should handle provider ordering explicitly if order affects business logic.

References:

- [Configuration — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html)
- [ModuleLayer — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html)
- [ServiceLoader — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html)
