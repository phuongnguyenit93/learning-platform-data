# Optional dependencies and requires static

In the Java Platform Module System (JPMS), the **requires** directive declares a module that must be read. With a standard dependency, the required module must be present when resolving the runtime module graph. However, there are libraries needed only at compile time, or that provide an optional feature the application can run without when that library is absent.

The **requires static** directive expresses this kind of dependency: a dependency mandatory at compile time that may be absent at runtime. It is a useful tool for designing modules with optional integrations, though classes that actually reference that dependency must be handled carefully.

## 1. Standard dependencies with requires

A named module declares a mandatory dependency using **requires** in **module-info.java**:

~~~java
module com.example.orders {
    requires com.example.payment;
}
~~~

This means the orders module needs to read the payment module. The payment module must be findable and resolvable at compile time as well as when launching the application.

If the payment module is not on the runtime module path, module graph resolution will fail, even if a particular code path does not call payment during that run.

Standard dependencies are appropriate when a module is an essential part of the application. If the application cannot function properly without that module, use **requires**.

## 2. requires static expresses a runtime-optional dependency

Syntax:

~~~java
module com.example.orders {
    requires static com.example.metrics;
}
~~~

The orders module needs the metrics module at compile time, yet the metrics module is not required to be present at runtime.

This can be understood across two phases:

- **Compile time:** the compiler must locate the metrics module to check imports, types, and API calls in source code.
- **Runtime:** the metrics module may be absent while the orders module itself still resolves. If metrics is present and resolved in the runtime configuration, readability to it is established.

Thus, **requires static** does not mean the dependency is ignored completely. It remains a declared module relationship that takes effect when the dependency exists. The difference is that the module system does not force the dependency to be present at runtime.

## 3. Example of a module with optional metrics integration

Suppose the orders application can send metrics to a metrics library. Core ordering functionality still works if the metrics library is not installed.

Module descriptor:

~~~java
module com.example.orders {
    requires static com.example.metrics;
}
~~~

A separate adapter uses the library's API:

~~~java
package com.example.orders.internal;

import com.example.metrics.MetricsRegistry;

public final class MetricsAdapter {
    private MetricsAdapter() {
    }

    public static void recordOrderCreated() {
        MetricsRegistry.increment("orders.created");
    }
}
~~~

The optional integration can be loaded when the metrics module is present in the boot layer:

~~~java
package com.example.orders;

import java.lang.reflect.Method;
import java.util.Optional;

public class OptionalMetrics {
    public static void recordIfAvailable() throws Exception {
        Optional<Module> metrics =
                ModuleLayer.boot().findModule("com.example.metrics");

        if (metrics.isEmpty()) {
            return;
        }

        Class<?> adapter = Class.forName(
                "com.example.orders.internal.MetricsAdapter");

        Method record = adapter.getMethod("recordOrderCreated");
        record.invoke(null);
    }
}
~~~

This example illustrates isolating integration code that references an optional library. When the metrics module is not resolved into the boot layer, the application skips the adapter. When the module is present, the adapter can be loaded and used.

In real-world applications, choose a detection mechanism suited to how modules are loaded. If the dependency is placed in a separate module layer instead of the boot layer, check the layer containing that dependency. Also handle reflection exceptions and linkage errors according to the application's policy.

## 4. requires static does not make code safe when the dependency is missing

A common misconception is that merely changing **requires** to **requires static** lets all code referencing the dependency run when that module is removed from runtime.

That is incorrect. **requires static** only makes the dependency optional during module graph resolution. It does not substitute for the library's classes or APIs.

If the application actually loads a class referencing types from the absent module, the JVM can throw a linkage error such as **NoClassDefFoundError** or another **LinkageError** when the type is resolved or used.

For example, if the main flow always calls **MetricsRegistry.increment(...)** directly yet the metrics module is absent, the application can still fail when executing that branch. Depending on when the JVM resolves symbolic references, the error may occur during class loading, linking, or execution.

To design optional dependencies safely:

1. Keep code directly referencing the optional library in a separate adapter or package.
2. Only load and invoke the adapter when the dependency is actually present.
3. Ensure the main business flow does not require types from the optional dependency.
4. Handle cases where the dependency is missing, the wrong version, or fails to initialize according to a clear policy.
5. Test both configurations: with the dependency and without the dependency.

Avoid letting types from an optional library appear in mandatory API signatures of classes always used by the application, unless a missing library is intended as a deliberate error.

## 5. How requires static differs from requires and requires transitive

The variants of the directive address different needs:

| Directive | Required at compile time | Required at runtime | Propagates readability |
|---|---|---|---|
| **requires M** | Yes | Yes | No |
| **requires static M** | Yes | No | No |
| **requires transitive M** | Yes | Yes | Yes |
| **requires static transitive M** | Yes | No | Yes, when the module is resolved |

**requires transitive** is used when the current module's API depends on types from another module and modules reading the current module also need to read that dependency.

**requires static transitive** combines both meanings: the dependency is required in the compile environment and readability is propagated, yet the dependency may still be absent at runtime.

Example:

~~~java
module com.example.api {
    requires static transitive com.example.annotations;
    exports com.example.api;
}
~~~

If the public API uses annotations or types from the annotations module, consuming modules may need to read that module at compile time. With **static transitive**, readability is propagated in the compile environment; at runtime, the dependency remains optional.

Carefully consider exposing types from an optional dependency in a public API. If callers must load or interact with those types at runtime, the dependency must be provided in the corresponding runtime configuration. Optionality in the module graph does not make data types available when the library is missing.

## 6. Does requires static need the dependency on the module path?

Yes. At compile time, the compiler still must locate the module declared in **requires static** to check source code.

Example:

~~~bash
javac --module-path libs \
      --module-source-path src \
      -d out \
      -m com.example.orders
~~~

The **libs** directory must contain the metrics module or a compatible module used by the source. If the metrics module is not in the observable module sources at compile time, the compiler will report module not found or fail to resolve the dependency.

At runtime, the metrics module can be omitted from the module path:

~~~bash
java --module-path out \
     --module com.example.orders/com.example.orders.Main
~~~

The runtime command contains only the orders module. Because the dependency is declared static, the module graph can resolve without the metrics module. However, the application must avoid loading or calling code needing metrics in this configuration.

To enable the metrics feature, place that module on the runtime module path:

~~~bash
java --module-path "out:libs" \
     --module com.example.orders/com.example.orders.Main
~~~

When the metrics module is present and resolved, the orders module can read it according to the declared static relationship.

On Windows, the separator between module path entries is a semicolon (**;**); on Linux and macOS, it is a colon (**:**).

## 7. Using requires static for annotation libraries

A common case is a dependency needed only for the compiler to read annotations or metadata in source code.

Example:

~~~java
module com.example.domain {
    requires static com.example.nullness;
}
~~~

Source code can use the annotation:

~~~java
package com.example.domain;

import com.example.nullness.NonNull;

public class CustomerService {
    public String display(@NonNull String name) {
        return name.trim();
    }
}
~~~

If the annotation serves only compile-time checks and does not need to be read at runtime, the annotation dependency can be declared with **requires static**.

Check the annotation's retention policy:

- **SOURCE:** the annotation is discarded from the class file after compilation.
- **CLASS:** the annotation is retained in the class file but not necessarily available via runtime reflection.
- **RUNTIME:** the annotation can be accessed via reflection at runtime.

If a runtime framework needs to read annotations with **RUNTIME** retention, the module containing the annotation must be present at runtime when the framework accesses it. Declaring **requires static** does not make a runtime annotation appear if its JAR was omitted from the runtime path.

## 8. Optional dependencies and ServiceLoader

If the goal is to let the application automatically discover an optional implementation, consider the Java Service Provider Interface (SPI) and **ServiceLoader**.

A module declares the service it uses:

~~~java
module com.example.orders {
    uses com.example.orders.spi.OrderObserver;
}
~~~

A plugin module provides an implementation:

~~~java
module com.example.metrics {
    requires com.example.orders;

    provides com.example.orders.spi.OrderObserver
        with com.example.metrics.MetricsObserver;
}
~~~

The application looks up providers:

~~~java
ServiceLoader<OrderObserver> observers =
        ServiceLoader.load(OrderObserver.class);

for (OrderObserver observer : observers) {
    observer.onOrderCreated();
}
~~~

If no matching provider exists in the service configuration, the application may receive no implementations and proceed according to its defined policy.

SPI solves discovering implementations against a contract. **requires static** solves allowing a module dependency to be absent at runtime. The two mechanisms can complement each other, yet do not replace each other. If the application module directly imports types from an optional module, it still needs to declare the appropriate module relationship at compile time.

In the plugin example, the API module and provider module are separated. This approach typically keeps the application module from depending directly on the metrics implementation.

## 9. When should requires static be used?

Consider **requires static** when:

- A library is needed only for the compile step, such as certain annotations or metadata.
- An integration feature is optional and the application can run properly when the library is absent.
- A module provides compile-time APIs yet runtime does not necessarily have to use the dependency's types.
- A separate adapter can isolate code needing the dependency and is loaded only when the module is present.

Do not use **requires static** if:

- The module is a mandatory component for processing the main business flow.
- Classes that are always loaded or instantiated require types from the dependency.
- A public API requires consuming modules to have the dependency at runtime, yet the configuration does not guarantee it.
- The real goal is merely delaying object initialization; that calls for lazy initialization design, not changing the dependency directive.

An optional dependency must be optional in application behavior as well. If removing the JAR prevents the application from completing its core function, the static directive does not make that dependency optional in business terms.

## 10. Common errors

**Compiler reports module not found despite using requires static**

Static does not mean compile-time optional. The module must still be present on the module path at compile time.

**Application launches yet throws NoClassDefFoundError when using the optional feature**

The module graph can resolve when the dependency is absent, yet code is loading or calling classes that depend on the library. Isolate the adapter, check for the module's presence before loading, and handle linkage errors.

**Changing requires to requires static loses readability to the module at runtime**

If the dependency is absent from the runtime configuration, the module is not resolved and there is no readability edge to it. If the dependency is present and resolved, the static readability relationship still takes effect.

**Using requires static for a mandatory dependency**

If the application always needs that module to operate, use **requires** so the module system catches the missing dependency immediately during resolution.

**Public API uses types from an optional dependency**

API consumers may need the dependency at compile time and runtime. Consider **requires static transitive** if compile-time readability must be propagated, while still ensuring the dependency is provided when those types are used at runtime.

**Confusing requires static with ServiceLoader**

Requires static does not automatically discover or instantiate providers. If optional implementations need to be discovered, design an SPI and use ServiceLoader.

## 11. Key takeaways

- **requires M** declares a dependency mandatory at compile time and runtime.
- **requires static M** is mandatory at compile time yet allows the dependency to be absent at runtime.
- If a static dependency is present and resolved at runtime, readability to it remains in effect.
- requires static does not load libraries automatically, does not substitute missing classes, and does not guarantee code directly referencing the dependency will run when the library is absent.
- Isolate optional integration in an adapter and load it only when the required module is present.
- **requires static transitive** propagates readability at compile time while keeping the dependency optional at runtime.
- Annotation dependencies must be evaluated according to their retention policy.
- **ServiceLoader** supports discovering optional providers; it solves a different problem from requires static.
- Only use static when the application can genuinely run properly when the dependency is absent.

When designing a module graph, determine whether a dependency is mandatory for the entire application or only serves a specific feature. Use **requires** for core dependencies and **requires static** for compile-time dependencies or optional runtime integrations. Then test both configurations with and without that module to ensure optionality is accurately reflected in application behavior.