# Iterator, stream, and ServiceLoader.Provider in Java

`ServiceLoader<S>` is Java's standard **Service Provider Interface (SPI)** mechanism for an application to find and use an implementation of a service without hardcoding each implementation class name. There are two important ways to iterate over the discovered results:

- **`iterator()`** provides an `Iterator<S>`: each element is a **service instance `S`**. During iteration, ServiceLoader loads and **instantiates providers on demand**.
- **`stream()`** (since Java 9) provides a `Stream<ServiceLoader.Provider<S>>`: each element is **a provider descriptor**, allowing you to inspect `type()` first and only create the instance when calling `get()`.

This difference is not merely a choice between `for` syntax and the Stream API. It determines **when the constructor/provider factory is called**, the ability to **filter based on metadata before creating objects**, how **caching and reloading** work, how discovery/instantiation errors are handled, and how SPI integrates with class loaders, the thread context class loader (TCCL), and the Java Platform Module System (JPMS).

This article focuses specifically on `Iterator`, `stream`, and `ServiceLoader.Provider`, featuring a **compilable and runnable Java 17 example with verified stdout**, along with important limitations when used in a plugin system.

## 1. What does ServiceLoader iterate over?

A **service** is an interface or abstract class representing a contract. A **provider** is an implementation that can be discovered by a framework or application according to SPI metadata.

~~~text
                         Service type
                         codec.api.Codec
                               |
                +--------------+---------------+
                |                              |
        Provider A                        Provider B
        codec.impl.Alpha                  codec.impl.Beta
                |                              |
                +--------------+---------------+
                               |
                               v
                     ServiceLoader<Codec>
                         /            \
                        v              v
               iterator()             stream()
               Iterator<Codec>        Stream<Provider<Codec>>
                        |              |
                        v              v
                  Codec instance    Provider descriptor
                                         |
                               +---------+--------+
                               |                  |
                             type()              get()
                               |                  |
                               v                  v
                         Class<? extends    Codec instance
                            Codec>
~~~

In code:

~~~java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

Iterator<Codec> objects = loader.iterator();

Stream<ServiceLoader.Provider<Codec>> descriptions =
        loader.stream();
~~~

The snippet above is only an **API-style fragment**: to compile, `Codec` and the corresponding `import` statements must be declared. A complete program is provided in section 4.

**`ServiceLoader<S>` implements `Iterable<S>`**, so you can use an enhanced-for loop:

~~~java
for (Codec codec : loader) {
    System.out.println(codec.id());
}
~~~

Note, however: enhanced-for calls `iterator()` and receives a **`Codec` instance**, not a `ServiceLoader.Provider<Codec>`.

Conversely, each element of `loader.stream()` is a **`Provider<Codec>`**, not yet a `Codec` object. Therefore:

~~~java
loader.stream()
        .map(ServiceLoader.Provider::get)
        .forEach(codec -> System.out.println(codec.id()));
~~~

The `map(...::get)` call is the step that retrieves or creates an instance from each provider descriptor. You cannot call `codec.id()` directly on a variable of type `Provider<Codec>` before calling `get()`.

## 2. Comparing iterator, stream, Provider.type, and Provider.get

| API | Value type | Key point |
| --- | --- | --- |
| `loader.iterator()` | `Iterator<S>` | Iterates over **service instances**; each provider is located and lazily instantiated only when needed. |
| `for (S s : loader)` | `S` | Convenience syntax for `Iterable`; fundamentally based on `iterator()`. |
| `loader.findFirst()` | `Optional<S>` | Retrieves and instantiates the first provider if present; useful for fallback, though “first” depends on discovery order. |
| `loader.stream()` | `Stream<ServiceLoader.Provider<S>>` | Iterates over **descriptors**, allowing providers to be filtered before creating an instance. |
| `provider.type()` | `Class<? extends S>` | Returns the provider's type per the API contract, not a service instance. |
| `provider.get()` | `S` | Returns an instance of the provider; may invoke a constructor or a provider factory. |

Do not write code assuming that `stream()` returns `Stream<S>`. The correct type is:

~~~java
Stream<ServiceLoader.Provider<MyService>> descriptors =
        ServiceLoader.load(MyService.class).stream();
~~~

This is a fragment; `MyService` must be declared. If you want a `Stream<MyService>`, you can transform it using `map(Provider::get)`; however, doing so **triggers instantiation** when the stream is consumed.

### Difference in execution timing

When creating a `ServiceLoader` or merely calling `stream()`, all provider instances do not need to be created yet. The stream pipeline is **lazy**: intermediate operations such as `filter`, `map`, and `sorted` normally do not run on their own until a terminal operation like `findFirst()`, `toList()`, `count()`, or `forEach()` is present.

~~~text
ServiceLoader.load(...)                obtains a loader for the service
        |
        +-- iterator()                 creates an iterator
        |      |
        |      +-- next()              needs an S, may instantiate
        |
        +-- stream()                   creates Stream<Provider<S>>
               |
               +-- filter(p -> p.type()...)
               |       (evaluated during traversal)
               |
               +-- findFirst()
                       |
                       v
                  Provider<S>
                       |
                       +-- get()        creates/retrieves an S instance
~~~

Precise note: **“lazy” does not mean that all metadata/discovery cannot raise errors until `get()` is called**. Locating providers, reading SPI metadata, and loading the provider type while consuming the stream can themselves throw `ServiceConfigurationError`. The strength of `Provider.type()` is that **you can decide whether an instance needs to be created before calling `get()`**.

## 3. What type is ServiceLoader.Provider<S>?

`ServiceLoader.Provider<S>` is a nested interface inside `ServiceLoader` and **extends `Supplier<S>`**. It represents a provider located by ServiceLoader and provides two core methods:

~~~java
Class<? extends S> type();
S get();
~~~

These are **summary signatures**, not a separate interface declaration to create in a project.

### Provider.type(): inspecting the type without instantiating

A typical scenario is filtering providers by annotation, class name, or type characteristics:

~~~java
Optional<ServiceLoader.Provider<Codec>> candidate =
        loader.stream()
              .filter(p -> p.type()
                            .isAnnotationPresent(FastCodec.class))
              .findFirst();
~~~

This is a fragment: `Codec`, the `FastCodec` annotation, and `loader` need to be declared. Checking `p.type()` only requires type metadata; **it does not require calling the service object's constructor**. However, the JVM may still have to load the class and query metadata/annotations, so one cannot say that “type() does nothing at all” or that there are no side effects from related classes.

If the filter finds the matching provider:

~~~java
Codec codec = candidate.orElseThrow().get();
~~~

Only at this point does `get()` obtain the instance. Using a filter before `get()` helps avoid creating objects for unsuitable providers, especially when constructors are resource-intensive or a plugin has many implementations.

### Provider.get(): creating an instance as declared by the provider

For a regular provider on the classpath or a provider class declared in a named module, `get()` can invoke the constructor/provider creation mechanism. For a named module, Java supports a **provider factory method**, which is a public static no-arg `provider()` method meeting the conditions of the `ServiceLoader` API.

~~~java
// Fragment in a named module; the class implementing the service is external.
public final class CodecProviderFactory {
    public static Codec provider() {
        return new AlphaCodec();
    }
}
~~~

This is **not part of the compilable example in section 4**. In a named module, the descriptor can declare a suitable provider factory class using `provides ... with ...`. Points to remember:

- If a factory method is used, `Provider.type()` returns the **return type of `provider()`**, not necessarily `CodecProviderFactory.class`.
- `Provider.get()` executes the instance creation mechanism for the corresponding provider and can throw `ServiceConfigurationError` if a valid object cannot be created.
- **Do not assume by default that calling `get()` multiple times always returns the same object.** `Provider<S>` is a supplier, and the API should not be understood as a singleton registry.
- The provider factory mechanism in a named module should not be equated with listing the name of a factory-only class (without a public no-args constructor) in `META-INF/services` on the classpath. Classpath provider-configuration requires an implementation with a suitable provider constructor.

Therefore, if you filter based on an annotation placed on the **factory class**, `p.type().isAnnotationPresent(...)` may not find that annotation: `type()` may be the **return type** of the factory method, not the class containing the method.

## 4. Complete Java 17 program: testing laziness, caching, and reload

This example uses a **named module** `codec.demo`, inside which it declares the service `codec.api.Codec` and a provider `codec.impl.Alpha`. To measure the number of instantiations, the provider constructor increments the counter `Probe.created`.

This approach has an advantage: **only one provider**, so it does not depend on discovery order across multiple modules or multiple JARs. The output can therefore be verified accurately.

Create **five files** following this structure:

~~~text
spi-demo/
└── src/
    └── codec.demo/
        ├── module-info.java
        └── codec/
            ├── api/
            │   ├── Codec.java
            │   └── Probe.java
            ├── impl/
            │   └── Alpha.java
            └── app/
                └── Main.java
~~~

### File 1 — src/codec.demo/module-info.java

~~~java
module codec.demo {
    exports codec.api;

    uses codec.api.Codec;

    provides codec.api.Codec with codec.impl.Alpha;
}
~~~

Explanation:

- `exports codec.api`: exposes the contract package when other modules need to use the service type.
- `uses codec.api.Codec`: indicates that code in this named module consumes the `Codec` service.
- `provides codec.api.Codec with codec.impl.Alpha`: registers a provider for the service.
- The `codec.impl` package **does not need to be exported**: ServiceLoader has a mechanism to instantiate providers according to the JPMS contract, without requiring us to expose the implementation package to every module.

### File 2 — src/codec.demo/codec/api/Codec.java

~~~java
package codec.api;

public interface Codec {
    String id();
}
~~~

`Codec` is the API contract that callers use. In a multi-module system, providers must implement **this exact interface definition**, not merely another copy with the same binary name.

### File 3 — src/codec.demo/codec/api/Probe.java

~~~java
package codec.api;

public final class Probe {
    private Probe() { }

    public static int created;
}
~~~

`Probe.created` is used to measure when the provider constructor is called. This is a static variable serving the example; production applications should not use an unsynchronized mutable counter to record provider instantiations across multiple threads.

### File 4 — src/codec.demo/codec/impl/Alpha.java

~~~java
package codec.impl;

import codec.api.Codec;
import codec.api.Probe;

public final class Alpha implements Codec {
    public Alpha() {
        Probe.created++;
    }

    @Override
    public String id() {
        return "alpha";
    }
}
~~~

Each time `new Alpha()` succeeds, the constructor increments the counter by one. `ServiceLoader` will create an instance when requested via the iterator path or `Provider.get()`.

### File 5 — src/codec.demo/codec/app/Main.java

~~~java
package codec.app;

import codec.api.Codec;
import codec.api.Probe;
import java.util.Iterator;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<Codec> loader =
                ServiceLoader.load(Codec.class);

        System.out.println("Initial count: " + Probe.created);

        ServiceLoader.Provider<Codec> provider = loader.stream()
                .filter(p -> p.type().getSimpleName().equals("Alpha"))
                .findFirst()
                .orElseThrow();

        System.out.println("After type filter: " + Probe.created);

        Codec selected = provider.get();

        System.out.println("After Provider.get: " + Probe.created);
        System.out.println("Selected id: " + selected.id());

        // Use a DIFFERENT ServiceLoader to observe its own iterator cache.
        ServiceLoader<Codec> other =
                ServiceLoader.load(Codec.class);

        Iterator<Codec> firstIterator = other.iterator();
        Codec first = firstIterator.next();

        System.out.println("After iterator.next: " + Probe.created);

        Codec again = other.iterator().next();
        System.out.println("Iterator reused instance: " + (first == again));

        other.reload();

        Codec fresh = other.iterator().next();
        System.out.println("After reload next: " + Probe.created);
        System.out.println("Fresh after reload: " + (first != fresh));
    }
}
~~~

Run from the `spi-demo` directory with **JDK 17 or later**:

~~~bash
javac --release 17 -d out --module-source-path src -m codec.demo
java --module-path out -m codec.demo/codec.app.Main
~~~

**Exact stdout** verified by compiling and running with a JDK supporting `--release 17`:

~~~text
Initial count: 0
After type filter: 0
After Provider.get: 1
Selected id: alpha
After iterator.next: 2
Iterator reused instance: true
After reload next: 3
Fresh after reload: true
~~~

### Line-by-line explanation

1. `ServiceLoader.load(Codec.class)` creates the service loader; there are no provider instances yet. `Probe.created` is initially `0`.
2. `loader.stream()` creates a stream of `Provider<Codec>`. The `filter(p -> p.type()...)` expression runs when `findFirst()` consumes the pipeline, but **does not call `p.get()`**. Thus the counter remains `0` after the filtering step.
3. `provider.get()` returns an actual `Codec`, the `Alpha` constructor runs, and `Probe.created` is incremented to `1`.
4. The `id()` method returns `alpha`.
5. `other` is **a different ServiceLoader**. The first `other.iterator().next()` call needs a service instance and creates another `Alpha`, bringing the counter to `2`.
6. The subsequent `other.iterator().next()` call returns the provider instance already **cached within `other` itself**, so the reference comparison `first == again` yields `true`. No third constructor invocation occurs before reload.
7. `other.reload()` clears the provider caches of `other`. The next `other.iterator().next()` call re-discovers/reloads the provider, creating a new object; the counter becomes `3` and `first != fresh` is `true`.

**Intentional limitations of the example:** With only one provider, the demo does not rely on the loading order of multiple providers. That `Provider.get()` creates an instance here is observed for **one call**; do not infer from this that `Provider.get()` has a caching contract like the iterator. After `reload`, the `first`/`again` references still point to the old object; reload only clears the ServiceLoader cache, **it does not destroy objects already held by the caller**.

## 5. Caching: differences between iterator and stream

ServiceLoader locates providers **lazily** and maintains caches for the traversal paths.

### With iterator()

According to the API, each `iterator()` first returns the **provider instances already cached by previous iterator traversals** in the order they were created, and only then locates and creates additional remaining providers as needed. Therefore, calling `loader.iterator()` again does not mean the program will re-instantiate every provider from scratch.

~~~java
ServiceLoader<Codec> services = ServiceLoader.load(Codec.class);

Codec a = services.iterator().next();
Codec b = services.iterator().next();

System.out.println(a == b);
~~~

This is a **fragment depending on a valid SPI**. If there is only one provider as in the program in section 4, the printed line is `true`; if there are multiple providers, it is still the first cached element when `reload` has not been called.

However, **caching does not turn `ServiceLoader` into a global singleton factory**: the cache belongs to each `ServiceLoader` object, not to all instances for that service. Another `ServiceLoader.load(...)` has its own cache.

### With stream()

`stream()` traverses **`Provider<S>` descriptors**. Processing a stream can locate providers and record information into the loader's separate cache for the stream path. `stream()` does not require invoking the constructor just to provide `Provider.type()`.

Example:

~~~java
List<String> types = loader.stream()
        .map(p -> p.type().getName())
        .sorted()
        .toList();
~~~

This is a fragment requiring `List` and `loader` to be declared. It retrieves **type names**, without instantiating service objects just to execute `map(...type...)`. `sorted()` requires consuming the descriptors needed for sorting, so it may force discovery of **all** providers, even though `get()` is not called.

If you subsequently write:

~~~java
List<Codec> instances = loader.stream()
        .map(ServiceLoader.Provider::get)
        .toList();
~~~

this is also a fragment. Now the terminal operation consumes the stream and **calls `get()`** for the elements traversed, so it may create provider objects.

### Do not confuse the two caches and identity

- The **iterator cache** is tied to the provider **instances** that `iterator()` has actually returned.
- The **stream cache** is tied to the provider descriptions located via `stream()`; do not equate it with a singleton instance cache.
- **`Provider.get()` does not promise to always return the exact same object as a previous `get()` call**; do not compare object identity on your own and treat it as an application contract.
- After `reload()`, the caches are cleared and the next traversal re-discovers providers; any objects, streams, or descriptors **still held by external code** do not automatically disappear.
- `ServiceLoader` is documented as **not safe for arbitrary concurrent use across multiple threads**. If a plugin system has multiple threads concurrently discovering/reloading, you need clear synchronization/ownership design or to use a ServiceLoader instance scoped to the appropriate context.

## 6. reload(): when to use it and when to avoid misusing it?

`reload()` clears the provider caches of **that ServiceLoader object itself**:

~~~java
ServiceLoader<Codec> services = ServiceLoader.load(Codec.class);

// ... iterate over providers ...

services.reload();

// Use a NEW iterator() or stream() to observe the cleared cache.
~~~

This is a fragment. Cases where reloading may be needed:

- The system detects a new provider artifact that is **already visible to the chosen class loader**.
- The application explicitly requests re-discovery of metadata.
- Tests modify the provider source visible to the loader and want to reset the cache between traversals.

**What must not be inferred from `reload()`:**

1. It **does not automatically create a new class loader**, does not add URLs/JARs to a loader, does not create a new module layer, and does not alter `requires`/`exports`/`opens` relationships.
2. It **does not unload** previously created Class or service objects.
3. It does not guarantee finding a new provider if the current class loader/module layer **cannot see** that provider.
4. It does not switch the `Codec` definition currently used by the consumer to an interface with the same name from another loader.
5. Any **iterators and streams created before `reload()` should be discarded** and not used further. The API has a fail-fast mechanism and may throw `ConcurrentModificationException` when old iterators/streams are consumed after the cache has been cleared.

Example of proper lifecycle error handling:

~~~java
Iterator<Codec> oldIterator = services.iterator();
services.reload();

// Do not continue using oldIterator: obtain a new iterator.
Iterator<Codec> newIterator = services.iterator();
~~~

This is a fragment requiring the `services` variable to exist; calling `newIterator` does not guarantee that a provider is available if the metadata/source is unsuitable.

### How does findFirst() relate?

`findFirst()` is a convenience method equivalent to using an iterator to retrieve the first provider:

~~~java
Codec chosen = ServiceLoader.load(Codec.class)
        .findFirst()
        .orElseGet(DefaultCodec::new);
~~~

This is a fragment assuming `DefaultCodec implements Codec`; it is not a standalone program. `findFirst()` **may instantiate** the first provider, and is not an alternative to `stream().filter(p -> p.type()...)` when you want to inspect metadata first.

## 7. Should you choose iterator or stream in each case?

| Need | Appropriate usage | Notes |
| --- | --- | --- |
| Run every provider in turn | `for (S s : loader)` / `iterator()` | Creates instances during traversal; suitable for processing each service one by one. |
| Need only the first provider | `loader.findFirst()` | Discovery order is not always stable across multiple named modules. |
| Select only providers with an annotation on the type | `loader.stream().filter(p -> p.type()...).map(Provider::get)` | Filters before creating an instance. |
| List provider types for diagnostics | `loader.stream().map(p -> p.type().getName())` | No need to instantiate the service object just to print its name. |
| Sort providers by type | `stream().sorted(comparing(p -> p.type().getName()))` | Sorting forces discovery of the required elements and does not guarantee the same selection when the provider set changes. |
| Want to re-discover after changes | `loader.reload()` then obtain a new iterator/stream | Do not keep old streams/iterators across a reload. |
| Need a specific provider lifecycle/singleton | Manage instances yourself via an application registry | Do not treat `Provider.get()` as a singleton contract. |

### Filtering by metadata: a conceptually safe example

Suppose implementations are annotated with a runtime annotation `@CodecPriority` and the service type has multiple providers:

~~~java
List<Codec> selected = loader.stream()
        .filter(p -> p.type().isAnnotationPresent(CodecPriority.class))
        .map(ServiceLoader.Provider::get)
        .toList();
~~~

This is a fragment illustrating selection only; to run it, you must declare the `CodecPriority` annotation with `@Retention(RUNTIME)`, the `Codec` service, and matching providers. Providers that do not pass the filter **do not have `get()` called on them by this pipeline**. However, locating/inspecting classes and metadata can still raise errors or incur overhead.

**Factory caveat:** If a provider in a named module declares a static factory, `p.type()` can be **the return type of the factory**. Annotations placed on the factory class are not necessarily visible via `p.type()`. Select metadata from where the ServiceLoader API actually provides it.

## 8. SPI discovery: differences between the classpath and named modules

`ServiceLoader` does not automatically scan every class that `implements Codec`. It requires **provider registration** according to SPI rules.

### 8.1. Providers on the classpath / unnamed module

A JAR/classpath provider typically contains a resource:

~~~text
META-INF/services/codec.api.Codec
~~~

Contents (UTF-8), for example:

~~~text
codec.impl.Alpha
codec.impl.Beta
~~~

This is an **illustration of a provider-configuration file**. To run a complete classpath project, `Codec`, `Alpha`, `Beta`, and the resource must be present in the proper location on the classpath. This is not the file used in the named-module demo in section 4.

A provider line is a **binary name**, not a `.class` path; comments starting with `#` and blank lines are allowed according to the API rules. A classpath provider must meet the appropriate instantiation requirements, typically a **public class with a public no-arg constructor** that implements/extends the service type. You cannot take an arbitrary class containing only a static method and treat it as a valid classpath provider in the same way as a named-module provider factory.

ServiceLoader uses resource lookup (`ClassLoader.getResources(...)`) when searching for provider-configuration files in unnamed modules. **Configuration ordering** depends on the order in which resources are found by the loader and the order of provider names in the file; duplicate names are ignored per the API. You should not expect every runtime/classpath to return the same list of providers if the classpath or class loader changes.

### 8.2. Providers in a named module / module layer

A named module declares:

~~~java
module codec.demo {
    exports codec.api;
    uses codec.api.Codec;
    provides codec.api.Codec with codec.impl.Alpha;
}
~~~

This is the exact metadata of the **runnable example**. For a consumer in a **named module**, declaring `uses service.Type` is an important requirement when using ServiceLoader from that module. A provider in a named module is defined with `provides ... with ...`; a module should not declare a provider belonging to another module.

A provider in a named module can:

- Have a suitable provider constructor, or
- Have a public static no-arg `provider()` factory method following the `ServiceLoader` contract.

Classpath provider-configuration is a mechanism intended for unnamed modules and has different requirements; do not assume that factory method applies to providers on the classpath.

### 8.3. ServiceLoader.load(ModuleLayer, Class)

When a program creates a dynamic `ModuleLayer` for plugins, the API:

~~~java
ServiceLoader<MyService> services =
        ServiceLoader.load(pluginLayer, MyService.class);
~~~

is a **fragment** requiring `pluginLayer` and `MyService` to be declared. This overload discovers providers in **named modules** of the chosen layer and its parent layers according to the API rules; **it does not search for providers in unnamed modules** with this overload.

The scan order is **the specified layer first, followed by its parent layers** according to the API's traversal rules. The order among modules within the same layer is undefined; therefore, do not pick the first provider in a critical application without explicit priority criteria.

### 8.4. Loading with TCCL or an explicit class loader?

The following two overloads can observe different sets of providers:

~~~java
ServiceLoader<MyService> a =
        ServiceLoader.load(MyService.class);

ServiceLoader<MyService> b =
        ServiceLoader.load(MyService.class, pluginClassLoader);
~~~

This is a fragment. Calling `load(MyService.class)` uses the **thread context class loader (TCCL)**; the two-argument call uses the specified class loader. In a thread pool, the worker thread's TCCL **is not automatically equal to the submitting thread's TCCL**, so discovery results may differ. Plugin systems with dedicated class loaders should choose to provide the loader/mapping explicitly and avoid holding a ServiceLoader in a global cache across multiple deployments.

Even if the right TCCL is chosen, the provider must still have a **compatible type identity** with the consumer's `MyService` interface. Two copies of a service interface with the same name defined by two different class loaders remain two separate JVM types; reordering provider resources cannot fix split identity.

## 9. Errors occurring in iterator, stream, and Provider.get

Not all ServiceLoader errors occur immediately when calling `ServiceLoader.load(...)`. Because loading/filtering/instantiation happens lazily, exceptions usually surface **when you begin consuming the results**.

| Timing | Error that may occur |
| --- | --- |
| `iterator().hasNext()` / `iterator().next()` | `ServiceConfigurationError` when metadata/provider is invalid or cannot be loaded/instantiated. |
| Terminal operation on `stream()` | `ServiceConfigurationError` when discovery, loading, or inspecting the provider type fails. |
| `Provider.get()` | `ServiceConfigurationError` if the constructor/factory fails, returns null in the factory case, or the provider cannot be instantiated. |
| Using an old iterator/stream after `reload()` | `ConcurrentModificationException` due to the API's fail-fast mechanism. |
| Provider class uses an API type with a different defining loader | `ServiceConfigurationError` or a related type/linkage error, depending on where the mismatch is detected. |
| Provider is declared but missing a dependency | Possibly `ServiceConfigurationError` with a cause such as `ClassNotFoundException`/`NoClassDefFoundError`, depending on the situation. |

`ServiceConfigurationError` is an **Error**, not a checked exception. You should not catch `Error` broadly or silently swallow all errors to “skip broken providers”. Usually you should log the **service name, provider name/type, class loader, module/layer, and cause**, then fail in a controlled manner. According to the API, some traversals can attempt to continue after an error, but **recovery from an invalid provider configuration is not always guaranteed**.

### Diagnostic pattern at the boundary

The following fragment assumes `loader` is a `ServiceLoader<Codec>` created from a compatible service:

~~~java
try {
    for (ServiceLoader.Provider<Codec> p :
            loader.stream().toList()) {

        Class<? extends Codec> type = p.type();

        System.out.println("Provider type: " + type.getName());
        System.out.println("Defining loader: " + type.getClassLoader());
        System.out.println("Module: " + type.getModule().getName());

        Codec instance = p.get();
        System.out.println("Instance: " + instance.id());
    }
} catch (java.util.ServiceConfigurationError error) {
    System.err.println("SPI discovery/creation failed: " + error);
}
~~~

This is a **fragment**, not a standalone program. In a real project, you should separate enumerating all providers (via `toList()`) from creating instances (via `get()`), and log the cause in detail. `getModule().getName()` can return `null` for an **unnamed module**; do not assume it always has a name.

If the provider class loads successfully but `serviceType.isAssignableFrom(providerType)` is false, check for **duplicate API JARs** and defining loaders; fixing discovery alone will not make two interfaces with the same name become the same type.

## 10. Performance and resource management: lazy does not mean free

Even though ServiceLoader is lazy, the following steps can still incur significant cost:

- Looking up `META-INF/services` via URLClassLoader may access JARs, the filesystem, or remote URLs depending on configuration.
- Loading metadata of many provider types for filtering/sorting.
- Reflection/validation to confirm that a class implements the service and is permitted to be instantiated.
- Running static initialization or constructors when calling `Provider.get()` / iterator, including I/O, thread creation, or caches maintained by the provider itself.
- `sorted(...)`, `toList()`, or a full traversal may force discovering all providers, whereas `findFirst()` can stop early according to discovery order.

When you only need to select one qualifying implementation, a pipeline based on `Provider.type()` followed by `findFirst()` avoids instantiating all providers just to read metadata. However, **do not rely on the first provider's order** if using multiple named modules or when there are business priority requirements: define explicit criteria such as an annotation priority, name, or configuration, and account for conflicts.

ServiceLoader does not own a provider's lifecycle once it has been handed to the caller. If a provider opens sockets, thread pools, or native resources, manage and close them **according to your own service contract**. `reload()` does not call `close()` on old objects.

## 11. Common misconceptions

**“`ServiceLoader.stream()` directly returns `Stream<Codec>`.”** False: it returns `Stream<ServiceLoader.Provider<Codec>>`. To obtain instances, you need `map(Provider::get)` or the iterator path.

**“`Provider.type()` creates the service object and calls `getClass()`.”** False: it returns the provider type without needing to instantiate the service object. However, locating/loading metadata can still occur.

**“`Provider.type()` is always the factory class in a named module.”** False: if the module uses a public static `provider()`, `type()` returns **the return type of the factory**, which may differ from the class containing the factory.

**“Calling `Provider.get()` twice is guaranteed to return the same singleton.”** Not guaranteed. If you need a singleton or a specific lifecycle, manage the cache/object yourself according to the application contract.

**“The iterator has no cache, so iterating again creates new providers.”** False: ServiceLoader caches the instances already returned by the iterator; the Java 17 example demonstrates retrieving the cached instance again via a new iterator from the **same loader**.

**“`reload()` will automatically detect any new JAR placed on disk.”** False: it only clears the cache; the current class loader/module layer must be able to see the artifact, and discovery requirements must still be satisfied.

**“`findFirst()` always gives the highest-priority provider.”** No. The order among named modules can be unspecified; use explicit criteria if you need to select an optimal implementation.

**“All errors are thrown immediately by `ServiceLoader.load`.”** No. Lazy discovery/instantiation means errors usually arise from `hasNext`, `next`, a terminal stream operation, or `Provider.get`.

**“ServiceLoader is thread-safe, so just share one instance across all workers.”** No. The API documentation does not guarantee safe concurrent use of a mutable ServiceLoader; you must synchronize or establish clear ownership when using/reloading it.

**“Classpath SPI and JPMS module registration are identical.”** No. Unnamed modules primarily use `META-INF/services`; named modules use `provides ... with ...`, along with the corresponding `uses`/factory/visibility requirements.

## 12. Checklist for applying in a project

1. Identify a **single service type** and where the API contract is defined.
2. Choose the provider registration mechanism: `META-INF/services` for the classpath, `provides ... with ...` for a named module.
3. If the caller is in a named module, declare `uses service.Type` as required.
4. Determine the **loader/layer used for discovery** and the TCCL when the API reads the context loader.
5. Use `iterator()` or enhanced-for when you genuinely want **service instances**.
6. Use `stream()` with `Provider.type()` when you need to **filter/inspect metadata first**.
7. Only call `Provider.get()` after deciding to obtain the instance.
8. Do not rely on the identity of `Provider.get()` as a singleton guarantee.
9. Only use `findFirst()` when provider order is suitable or does not matter; if priority is needed, sort/filter using explicit criteria.
10. With `reload()`, discard old iterators/streams and understand that the lifecycle of old instances remains managed by the caller.
11. Catch and properly report `ServiceConfigurationError` at the discovery/instantiation boundary; do not swallow broken configuration errors.
12. When debugging, print the type, module, **defining class loader**, cause, and provider metadata location.
13. Avoid globally caching a ServiceLoader across different plugins/TCCLs/deployments.
14. Test a broken provider, a provider missing a dependency, a failing provider constructor, metadata filtering, and discovery after reload.

## 13. Self-check questions

**Question 1.** What is the element type of `ServiceLoader<Codec>.iterator()`? What is it for `stream()`?

**Answer:** The iterator returns `Codec` instances; the stream returns `ServiceLoader.Provider<Codec>` descriptors.

**Question 2.** Why is `stream().filter(p -> p.type()...).findFirst()` usually cheaper than iterating with an iterator and checking `object.getClass()`?

**Answer:** You can filter by type metadata **before instantiating objects**, avoiding the constructors of excluded providers. Discovery/type loading still has a cost.

**Question 3.** Does `Provider.get()` guarantee always returning the same instance like a singleton?

**Answer:** No. It returns a valid instance, with no singleton identity guarantee across calls.

**Question 4.** Does calling `loader.iterator()` again on the **same ServiceLoader object** necessarily create new provider instances for all providers?

**Answer:** No. Instances already loaded through the iterator are cached and returned first; only unloaded providers are lazily created.

**Question 5.** Why is calling `reload()` and then using an old iterator wrong?

**Answer:** Reloading clears the cache and makes existing iterators/streams stale; the API may throw `ConcurrentModificationException` via its fail-fast mechanism. Create a new iterator/stream instead.

**Question 6.** A named module uses a provider factory with `public static Codec provider()`. Which type does `Provider.type()` return?

**Answer:** **The return type of the `provider()` method**, according to the ServiceLoader API, not necessarily the class containing the factory.

**Question 7.** A plugin has a provider implementing `api.Codec`, yet the host does not accept it as a subtype despite having the same name. What should be checked?

**Answer:** The **defining class loader and identity** of the `api.Codec` interface in the host/plugin; two copies of an interface with the same name defined by different loaders are not compatible based on name alone.

## Key takeaways

**`iterator()` works with service instances, while `stream()` works with `ServiceLoader.Provider<S>` descriptors.** `Provider.type()` lets you inspect the provider type **before instantiating**; `Provider.get()` is what returns the instance. ServiceLoader supports lazy discovery, caching, and `reload`, but you should avoid assumptions about singletons, ordering among named modules, or concurrency. In a plugin system, choosing the **right service interface, class loader/module layer, and provider registration** is just as important as choosing between iterator and stream.

**Official documentation (Java SE 17):**

- `ServiceLoader` — iterator, stream, load, reload, findFirst, discovery, caching, errors: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- `ServiceLoader.Provider` — type and get: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html
- `ModuleLayer` — dynamic layers and class loader mapping: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- `ClassLoader` — resource lookup and type loading: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
