# resolveAndBind and differences from resolve

## 1. Context: module resolution and service binding

The Java Platform Module System (JPMS) needs to build a **module graph** before creating module layers and running the application. Starting from one or more root modules, the resolver finds modules that the roots require directly or indirectly through `requires` directives. This process is called **module resolution**.

In an application that uses a Service Provider Interface (SPI), one module may declare `uses` to consume a service, while another module declares `provides ... with ...` to supply an implementation. The provider might not appear in the consumer's `requires` chain. If only normal dependencies are resolved, the provider module may not be included in the module graph.

JPMS provides two methods on `Configuration` to choose how resolution is performed:

- `resolve(...)`: resolves root modules and dependencies declared via `requires`.
- `resolveAndBind(...)`: performs resolution as above, while also running **service binding** to add modules that provide services for which modules in the graph declare `uses`.

Service binding addresses the situation where a consumer needs a service but should not depend directly on the module implementing that service.

## 2. Three-module example

Suppose there are three modules:

- `com.acme.spi`: defines the `Formatter` service interface.
- `com.acme.app`: consumer application, using `Formatter`.
- `com.acme.provider.json`: provider supplying the `JsonFormatter` implementation.

Service contract in the SPI:

```java
package com.acme.spi;

public interface Formatter {
    String format(String input);
}
```

Module descriptor of the SPI:

```java
module com.acme.spi {
    exports com.acme.spi;
}
```

Module descriptor of the consumer:

```java
module com.acme.app {
    requires com.acme.spi;

    uses com.acme.spi.Formatter;
}
```

The consumer depends on the SPI to reference the interface and declares `uses` to indicate that it needs to discover providers of this service type.

Implementation in the provider:

```java
package com.acme.provider.json;

import com.acme.spi.Formatter;

public final class JsonFormatter implements Formatter {
    public JsonFormatter() {
    }

    @Override
    public String format(String input) {
        return "{\"value\":\"" + input + "\"}";
    }
}
```

Module descriptor of the provider:

```java
module com.acme.provider.json {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.provider.json.JsonFormatter;
}
```

The provider depends on the SPI to implement the contract and declares `provides` to register its implementation. The consumer does not declare `requires com.acme.provider.json`; this is precisely what allows providers to be replaced or added independently.

## 3. Differences between resolve and resolveAndBind

Both methods start from the root modules, find required modules via `requires`, verify the consistency of the module graph, and return a new `Configuration`.

| Aspect | `resolve(...)` | `resolveAndBind(...)` |
|---|---|---|
| Resolves root modules | Yes | Yes |
| Resolves `requires` dependencies | Yes | Yes |
| Inspects `uses` directives to find providers | Does not perform service binding | Yes |
| Adds matching provider modules to the graph | Does not add automatically merely due to `provides` | Yes, if the provider is observable during resolution |
| Suitable for | Graphs that only need explicit dependencies | Applications that need to automatically link SPI providers |

Suppose the root is `com.acme.app` and all modules are placed in the same module finder:

**With `resolve(...)`:**

- Root `com.acme.app` is added to the graph.
- `com.acme.spi` is added to the graph because the consumer declares `requires com.acme.spi`.
- `com.acme.provider.json` is not added merely because it has `provides com.acme.spi.Formatter`.

**With `resolveAndBind(...)`:**

- The normal resolution steps still take place.
- The resolver sees that `com.acme.app` declares `uses com.acme.spi.Formatter`.
- If a matching and observable provider module is found, it adds `com.acme.provider.json` to the graph.
- The provider's dependencies are also resolved. If the newly added module also declares `uses` for other services, service binding continues processing those services until no more matching modules need to be added.

Therefore, `resolveAndBind` can produce a larger graph than `resolve`. The actual graph size depends on the root modules, dependencies, service directives, and the modules supplied to the resolver by the finders/parent configurations.

## 4. Example calling the two Configuration methods

You can compare the two configurations directly in code:

```java
import java.lang.module.ModuleFinder;
import java.lang.module.ResolvedModule;
import java.nio.file.Path;
import java.util.Set;

public class ResolutionExample {
    private static void printModules(String title,
                                     java.lang.module.Configuration config) {
        System.out.println(title);
        config.modules().stream()
                .map(ResolvedModule::name)
                .sorted()
                .forEach(name -> System.out.println("  " + name));
    }

    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

        java.lang.module.Configuration parent =
                ModuleLayer.boot().configuration();

        Set<String> roots = Set.of("com.acme.app");

        java.lang.module.Configuration normal =
                parent.resolve(finder, ModuleFinder.of(), roots);

        java.lang.module.Configuration bound =
                parent.resolveAndBind(finder, ModuleFinder.of(), roots);

        printModules("resolve:", normal);
        printModules("resolveAndBind:", bound);
    }
}
```

In the example:

- `ModuleFinder.of(Path.of("mods"))` locates modules present in the `mods` directory, including the application, SPI, and provider.
- `ModuleLayer.boot().configuration()` provides the boot layer's configuration as the parent.
- `Set.of("com.acme.app")` specifies the root module.
- `ModuleFinder.of()` is an empty finder for the remaining finder parameter.
- `Configuration.modules()` returns the modules belonging to the new configuration; modules already in the parent configuration are not counted in this set.

Illustrative output if the provider is linked only via SPI:

```text
resolve:
  com.acme.app
  com.acme.spi

resolveAndBind:
  com.acme.app
  com.acme.provider.json
  com.acme.spi
```

The actual list depends on the contents of the module directory and other dependencies. You can add other modules to the `mods` directory to observe how service binding adds the corresponding providers.

Both methods are instance methods on `Configuration`. The `before` and `after` parameters are `ModuleFinder` instances participating in module discovery during resolution; when designing a custom configuration, ensure the application and provider modules are within the observable scope of the finders/parent configurations.

## 5. Service binding is not provider instantiation

An important point is that `resolveAndBind` only builds a configuration containing matching provider modules. It **does not invoke provider constructors, does not execute implementations, and does not create service objects itself**.

The complete workflow has distinct stages:

1. Module descriptors declare `uses` and `provides`.
2. `resolveAndBind` resolves dependencies and adds provider modules to the configuration.
3. The application creates a `ModuleLayer` from the configuration.
4. The consumer uses `ServiceLoader` to retrieve implementations in the layer and invoke service behavior.

Consumer-side example:

```java
import com.acme.spi.Formatter;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<Formatter> loaders =
                ServiceLoader.load(Formatter.class);

        for (Formatter formatter : loaders) {
            System.out.println(formatter.format("Java modules"));
        }
    }
}
```

If the provider is already in the layer used by the consumer, `ServiceLoader` can locate that implementation. If the provider is not brought into the layer, `ServiceLoader` cannot load it from that layer just because some module elsewhere declares `provides`.

With a custom `ModuleLayer`, you can use the overload `ServiceLoader.load(layer, Formatter.class)` to explicitly specify the layer to search for providers. Creating the layer and loading providers are separate operations from resolution.

## 6. resolve can still work with ServiceLoader

You should not assume that calling `resolve` disables SPI or prevents `ServiceLoader` from working.

If a provider has been brought into the graph by another route, such as:

- The provider is specified directly as a root module.
- A module in the graph declares `requires` on the provider.
- The provider is already present in an appropriate parent layer.

then the consumer can still use `ServiceLoader` to locate that provider. The difference is that `resolve` does not automatically expand the graph to locate providers solely based on `uses`/`provides` relationships.

Conversely, `resolveAndBind` also cannot locate providers outside the observable scope of the `ModuleFinder` instances and parent configurations. Placing a JAR in an arbitrary directory on disk does not mean the resolver will automatically find it; the module must be in the search sources supplied to resolution.

## 7. Multiple providers and iterative service binding

A service can have multiple providers. If multiple matching provider modules are observable together, service binding can add those multiple modules to the configuration. `resolveAndBind` is not a mechanism for picking a single provider, nor does it define business priority ordering for the application.

Suppose we also have:

```java
module com.acme.provider.xml {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.provider.xml.XmlFormatter;
}
```

When both provider modules are observable by the resolver, the configuration created with `resolveAndBind` can contain both `com.acme.provider.json` and `com.acme.provider.xml`.

The consumer must decide how to use multiple implementations: run all of them, filter by metadata/configuration, choose based on data type, or report an error if multiple options exist when only a single provider is expected. You should not rely on `ServiceLoader`'s iteration order as a stable priority rule.

Service binding is transitive: providers added to the graph can also have their own `requires` dependencies and `uses` directives. The resolver continues processing related dependencies and services until a steady state is reached.

## 8. Limitations and errors to check

| Symptom | How to check |
|---|---|
| `resolveAndBind` does not bring the provider into the graph | Check that the consumer has `uses` for the right service type; the provider has `provides` for the right type; and the provider is in an observable finder or parent configuration |
| Provider fails to compile | Check `requires` to the SPI and that the package containing the service interface is exported |
| `ServiceLoader` does not return the provider | Check that the provider is actually in the searched layer and the consumer module declares `uses` |
| Configuration reports a missing dependency | Check the `requires` directives of the roots and provider modules, as well as the finders passed in |
| More providers than expected | Check all modules declaring `provides` for the service type and the consumer's selection rules |

If the consumer is a named module, the `uses` directive is part of the module descriptor. Calling `ServiceLoader.load` from a module that does not declare using the corresponding service can throw a `ServiceConfigurationError`.

JPMS service binding works with the module graph. Classpath/unnamed-module applications can use the traditional registration mechanism via `META-INF/services`, but that is not `Configuration.resolveAndBind` scanning the entire classpath.

## 9. Which method to choose?

Use `resolve` when the module graph is determined by roots and `requires` dependencies, and the application explicitly controls providers by other means.

Use `resolveAndBind` when the application wants JPMS to automatically add modules providing services for modules that have declared `uses`. This is the right choice for plugin systems or SPI architectures, where consumers depend on contracts while providers can be added independently.

Before choosing, clearly verify:

- Are the providers placed in a module finder or parent layer observable by the resolver?
- Has the consumer declared `uses` properly?
- Has the provider declared `provides ... with ...` properly?
- Does the application accept multiple providers or need a specific selection policy?
- Are you trying to build a configuration, create a layer, or actually load and invoke implementations? These are distinct steps.

## Key Takeaways

- `resolve` resolves root modules and `requires` dependencies.
- `resolveAndBind` performs those steps and then adds matching provider modules based on `uses`/`provides` relationships.
- A provider is only found if it is within the module scope observable by the resolver.
- Service binding builds the module graph; it does not instantiate providers itself.
- `ServiceLoader` performs discovery and loading of implementations when the application uses the service.
- `resolve` can still be used with `ServiceLoader` if the provider is already present in the layer by another means.
