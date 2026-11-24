# Iterator Traversal and When Providers Are Loaded and Instantiated on Demand

## 1. The Problem to Understand

In plugin-capable Java systems, `ServiceLoader<S>` is the tool for discovering providers of a service type `S` without requiring the application to list implementations at compile time. The key point is that **creating a `ServiceLoader` does not mean creating all providers**. `ServiceLoader` performs discovery and creates providers on demand as the program traverses its iterator or stream.

Four events must be distinguished:

1. **Creating the loader:** calling `ServiceLoader.load(S.class)` or an overload taking a classloader.
2. **Metadata discovery:** reading provider information from `META-INF/services/<service-binary-name>` on the classpath or from appropriate module descriptors on the module path.
3. **Loading and linking classes:** the JVM needs to access/verify the provider class when performing discovery or instantiation; the exact moment the JVM loads/links/initializes each class should not be inferred merely from creating the loader.
4. **Creating the provider object:** the constructor or provider factory is invoked when the iterator must supply a new instance. For streams, reading `Provider.type()` and calling `Provider.get()` are two distinct operations.

Confusing these steps easily leads to assuming every plugin is already ready just because a `ServiceLoader` exists, or assuming a single `hasNext()` call always creates an instance. Behavior must be evaluated according to the specific API.

## 2. Runnable Java 17+ Example: Observing `Iterator`

The example consists of an interface, two providers, an SPI registration file, and a runner class. Both providers print messages in their static initializer and constructor to observe the corresponding timing.

Structure:

```text
example/
├── src/
│   ├── demo/spi/Greeter.java
│   ├── demo/plugins/EnglishGreeter.java
│   ├── demo/plugins/VietnameseGreeter.java
│   └── demo/Main.java
└── resources/
    └── META-INF/services/demo.spi.Greeter
```

`src/demo/spi/Greeter.java`:

```java
package demo.spi;

public interface Greeter {
    String greet();
}
```

`src/demo/plugins/EnglishGreeter.java`:

```java
package demo.plugins;

import demo.spi.Greeter;

public final class EnglishGreeter implements Greeter {
    static {
        System.out.println("English: static initializer");
    }

    public EnglishGreeter() {
        System.out.println("English: constructor");
    }

    @Override
    public String greet() {
        return "Hello";
    }
}
```

`src/demo/plugins/VietnameseGreeter.java`:

```java
package demo.plugins;

import demo.spi.Greeter;

public final class VietnameseGreeter implements Greeter {
    static {
        System.out.println("Vietnamese: static initializer");
    }

    public VietnameseGreeter() {
        System.out.println("Vietnamese: constructor");
    }

    @Override
    public String greet() {
        return "Xin chào";
    }
}
```

`resources/META-INF/services/demo.spi.Greeter`:

```text
demo.plugins.EnglishGreeter
demo.plugins.VietnameseGreeter
```

`src/demo/Main.java`:

```java
package demo;

import demo.spi.Greeter;
import java.util.Iterator;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        System.out.println("1. Before load");
        ServiceLoader<Greeter> loader = ServiceLoader.load(Greeter.class);
        System.out.println("2. Loader created");

        Iterator<Greeter> iterator = loader.iterator();
        System.out.println("3. Iterator created");

        System.out.println("4. hasNext=" + iterator.hasNext());
        System.out.println("5. Calling next");
        Greeter first = iterator.next();
        System.out.println("6. First result=" + first.greet());

        System.out.println("7. hasNext=" + iterator.hasNext());
        System.out.println("8. Calling next");
        Greeter second = iterator.next();
        System.out.println("9. Second result=" + second.greet());
    }
}
```

From the `example` directory, run in a shell with `cp` and `find` (e.g. bash):

```bash
mkdir -p out
javac -d out src/demo/spi/Greeter.java src/demo/plugins/EnglishGreeter.java src/demo/plugins/VietnameseGreeter.java src/demo/Main.java
cp -R resources/. out/
java -cp out demo.Main
```

A typical output with the exact two providers and declaration order in the example:

```text
1. Before load
2. Loader created
3. Iterator created
4. hasNext=true
5. Calling next
English: static initializer
English: constructor
6. First result=Hello
7. hasNext=true
8. Calling next
Vietnamese: static initializer
Vietnamese: constructor
9. Second result=Xin chào
```

Observations:

- No constructor is called at `ServiceLoader.load(...)` or `loader.iterator()`.
- `hasNext()` answers whether another provider can be retrieved; in this simple classpath example, it does not invoke the constructor.
- Whenever `next()` needs a new provider, the corresponding provider is created and placed into the cache.
- The static initializer appears before the constructor when the class is initialized by the JVM. That is a consequence of creating an instance; it is not a promise that every `hasNext()` call will never perform class loading/linking.

**Limits of this observation:** the example runs on the classpath, with valid service configuration, without using a named-module provider factory, and with no previously created providers. Under JPMS, streams and metadata verification may produce a different sequence of operations, while still adhering to the public contract of `ServiceLoader`.

## 3. `hasNext()`, `next()`, and the Difference Between Discovery and Instantiation

`ServiceLoader.iterator()` returns an iterator that uses an internal discovery and caching mechanism. The operations have distinct roles:

| Operation | Meaning | Guaranteed to create a new provider? |
| --- | --- | --- |
| `ServiceLoader.load(S.class)` | Creates a loader for discovery | No |
| `loader.iterator()` | Obtains an iterator to traverse providers | No |
| `iterator.hasNext()` | Checks if a next element exists; may need to read/verify metadata | No |
| `iterator.next()` | Retrieves the next provider instance | Maybe: creates a new one if not cached; no if returning a cached instance |
| `loader.reload()` | Clears the loader's provider cache to rediscover | Does not create providers by itself |
| `loader.stream()` | Creates a stream of `Provider<S>` objects | Does not directly create all providers |
| `Provider.type()` | Reports the provider's class/type per the stream API | Does not require a provider instance |
| `Provider.get()` | Requests a provider instance | May create an instance; each call may create a new instance |

**Do not equate `hasNext()` with `next()`.** Knowing a provider's metadata does not prove that provider initializes successfully. For instance, if the registration file references a nonexistent name or the provider has a throwing constructor: the failure may only surface during discovery or when requesting an instance. Do not rely on a fixed exception type/throw site; depending on the error, `ServiceConfigurationError` can appear at different traversal steps.

If the goal is to verify that every provider is usable, you must **actually traverse and use** each instance rather than just creating the loader or seeing the registration file.

## 4. How Does `ServiceLoader`'s Cache Affect Laziness?

A `ServiceLoader` caches provider instances already created through the iterator. Subsequent traversals may pull instances from the cache before discovering/instantiating remaining providers.

The following snippet continues using the `loader` created in the previous section:

```java
for (Greeter greeter : loader) {
    System.out.println(greeter.greet());
}
```

Because both providers were already created during the previous traversal, the second traversal can reuse both cached instances **without calling the constructors again**.

There are two consequences:

- Lazy initialization is a property of **each loader and its cache state**. The statement "`next()` always calls the constructor" is false if that element is already in the cache.
- `ServiceLoader`'s cache does not equal an application-wide singleton. Creating another `ServiceLoader` or calling `Provider.get()` via a stream can yield different instances, depending on the provider and implementation style.

An appropriate mental model:

```text
ServiceLoader created
      |
iterator() / stream()
      |
discover provider info on demand
      |
request provider instance
      |
cached? ---- Yes ----> return cached instance (iterator)
      |
     No
      |
verify/instantiate provider
      |
store in cache (iterator)
      |
return instance
```

This diagram is a conceptual model for the iterator. Do not use it to infer that `stream().map(Provider::get)` necessarily shares the exact same instance-caching policy as `iterator()`.

## 5. Partially Traversed Iterators and the Effect of `reload()`

Suppose a plugin directory changes after creating the loader, or code calls:

```java
loader.reload();
```

`reload()` clears the existing cache. Iterators or streams obtained before the `reload()` call may become invalid; with this API, using an old iterator after a reload can cause `ConcurrentModificationException`. Obtain a fresh iterator/stream from the loader after reloading.

Standalone in-method example:

```java
ServiceLoader<Greeter> loader = ServiceLoader.load(Greeter.class);
Iterator<Greeter> oldIterator = loader.iterator();
loader.reload();

Iterator<Greeter> freshIterator = loader.iterator();
while (freshIterator.hasNext()) {
    Greeter greeter = freshIterator.next();
    System.out.println(greeter.greet());
}
```

**Important:** `reload()` does not automatically add JARs to the classpath/classloader, does not fix broken descriptors, and does not unload already-loaded classes from the JVM. It only makes the loader drop its cache so rediscovery runs on the next traversal. If the classloader cannot see a new JAR, reloading still will not find that plugin. For systems supporting hot deployment, you must coordinate management of the loader, JAR files, and plugin instance lifecycle.

## 6. `stream()` Provides a Different Level of Laziness than `iterator()`

Since Java 9, `ServiceLoader.stream()` returns a stream of `ServiceLoader.Provider<S>`. Each `Provider` exposes:

- `type()`: type information for the provider to filter by annotations or class metadata.
- `get()`: retrieves a provider instance; calling `get()` can trigger instantiation and initialization.

Example filtering by class name before creating an instance:

```java
ServiceLoader<Greeter> loader = ServiceLoader.load(Greeter.class);
loader.stream()
    .filter(provider -> provider.type().getSimpleName().equals("EnglishGreeter"))
    .map(ServiceLoader.Provider::get)
    .forEach(greeter -> System.out.println(greeter.greet()));
```

Output with the example's providers and a fresh loader:

```text
English: static initializer
English: constructor
Hello
```

The snippet above is **code inside a method with `Greeter` and `ServiceLoader` imported**. Place it in the sample app and run with the same classpath as before to observe the output. Providers that do not pass the filter do not have `get()` called; however, `type()` may cause the JVM to load/link the class or perform metadata verification. Thus `type()` does not mean "never touches the class" — it means "does not request creating a provider instance".

In a named module, a provider can be declared with `provides ... with ...` and have a provider method. In that case, the type supplied by `Provider.type()` may be the return type of the provider method, not necessarily the factory class named in the module descriptor. Do not assume strict equivalence with classpath provider classes.

**When to choose which API?**

- Use `iterator()` or enhanced `for` if you want instances sequentially and will use them immediately.
- Use `stream()` if you want to screen via metadata/type before calling `Provider.get()`, or build a conditional provider discovery pipeline.
- Do not use `ServiceLoader` as a sandbox tool, policy enforcement mechanism, or performance guarantee; plugin code can execute when the provider is initialized.

## 7. Errors and Runtime Observability

### Configuration Errors vs. Initialization Errors

Several errors can be wrapped in `ServiceConfigurationError`, for example:

- A malformed `META-INF/services/` descriptor or one pointing to a nonexistent class.
- A provider incompatible with the service type.
- A provider that fails instantiation requirements, or whose constructor/provider method throws an exception.
- A provider inaccessible due to module accessibility or classloader issues.

Do not catch broadly and ignore all errors:

```java
try {
    for (Greeter greeter : ServiceLoader.load(Greeter.class)) {
        System.out.println(greeter.greet());
    }
} catch (java.util.ServiceConfigurationError error) {
    throw new IllegalStateException("Invalid plugin deployment", error);
}
```

This is a snippet for use inside a method. It preserves the root cause so operations can locate the failing provider. In a system with specific plugin isolation, you may decide to continue after logging the error, but it must be handled explicitly per product requirements; never swallow errors by default.

### What Should Instrumentation Actually Measure?

When benchmarking or debugging lazy loading:

1. Place measurement probes immediately before/after `ServiceLoader.load`, `iterator()`, `hasNext()`, `next()`, `Provider.type()`, and `Provider.get()`.
2. Record timestamps for constructor calls, static initialization, resource reads, external connections, or config file reads.
3. Run both cold and repeated passes to compare cache/JIT/warmup state; do not merge the two results.
4. To verify laziness, use a provider with an observable side effect in its constructor, and confirm the loading method was not called before the measurement.
5. Run with real distribution artifacts and classloaders; an IDE classpath can hide missing metadata.

Do not infer speed from the word "lazy": deferred initialization avoids paying costs before needed, but can push latency onto the first request. Measure under realistic load.

## 8. Several Design Scenarios

### Deferring Expensive Plugins

If a plugin initializes a connection client or reads large configs in its constructor, an iterator lets you create each provider only when actually reached. However, **iterating `for (Greeter g : loader)` to the end of the list creates every provider**, failing the goal of using only one plugin. You can use a stream to filter by type before calling `get()`, or design a separate metadata registry if selection depends on an ID only obtainable from an instance.

### Non-Thread-Safe Providers

`ServiceLoader` **is not safe for concurrent use by multiple threads**. Do not share a loader instance and call traversal/reload operations from multiple threads without a proper synchronization strategy. Provider caching also does not automatically make implementations thread-safe: lifecycle and provider access must be governed by their own contract.

### Updating Plugins While the Application Runs

If a plugin archive changes on disk, the old classloader may still retain already-loaded classes; `reload()` is not guaranteed to read new bytecode. To swap versions, you typically need to create a new appropriate classloader/module layer, swap references, and clean up the old loader's lifecycle. Provider resource shutdown must be controlled to avoid leaking threads, file handles, or classloaders.

## 9. Checklist for Using `ServiceLoader` Correctly

- [ ] Verify the service type name and the `META-INF/services` or `module-info.java` descriptor.
- [ ] Traverse with an iterator when instances are needed; use a stream when filtering provider info before `get()`.
- [ ] Distinguish reading metadata, loading/linking classes, class initialization, and creating provider instances.
- [ ] Understand that `hasNext()` does not prove a provider initializes successfully; `next()` may return a cached instance.
- [ ] Do not assume calling `load(...)` eagerly creates all plugins.
- [ ] If calling `reload()`, create a fresh iterator/stream and manage classloader replacement separately.
- [ ] Test initialization timing using controlled output/side effects rather than guessing.
- [ ] Test real plugins on release artifacts and with the actual runtime classloader.
- [ ] Handle `ServiceConfigurationError` with logging/cause and a clear error policy.

**Core point:** `ServiceLoader` enables on-demand discovery and instantiation of providers; the iterator is where a provider may be asked to create an instance, and caching can make later traversals return already-created instances. To instantiate only the selected plugin, separate inspecting metadata via `stream()` from calling `Provider.get()`, and verify initialization timing in the real runtime environment.
