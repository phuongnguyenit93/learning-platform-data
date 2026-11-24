# Concurrency Rules and Retention Scope for ServiceLoader Objects

`java.util.ServiceLoader<S>` is Java's SPI (Service Provider Interface) mechanism for locating implementations of a service without the application needing concrete class names at compile time. It is useful for plugins, codecs, drivers, adapters, and capabilities supplied on the class path or module path. However, **how `ServiceLoader` is used across multiple threads and how long the objects it creates are retained directly affect correctness, resources, and plugin reloadability**.

This lesson addresses two questions:

1. When multiple threads need providers simultaneously, **who is allowed to interact with the `ServiceLoader` object**, especially during discovery, iteration, streaming, and `reload()`?
2. **How long, where, and under which class loader should `ServiceLoader` and providers be retained**, and what happens during refresh, version replacement, or plugin unloading?

Guiding principle: **never share a `ServiceLoader` concurrently; share providers only after establishing dedicated lifecycle and thread-safety policies for those providers**.

## 1. Distinguishing Four Commonly Conflated Objects

A system can contain multiple components with distinct meanings:

| Component | What does it represent? | What must be managed? |
| --- | --- | --- |
| `ClassLoader` or `ModuleLayer` | Visibility space for classes/modules and providers | Application/plugin scope, isolation, and unloading capability |
| `ServiceLoader<S>` | Service discovery object, holding **internal state and caches** | Authorized owner for traversal, caching, and `reload()`; do not share concurrent operations |
| `ServiceLoader.Provider<S>` | Provider descriptor obtained from `stream()`; exposes `type()`, `get()` | Do not equate descriptor with service instance; define instance creation policy |
| `S` (provider instance) | Business-executing object supplied by the provider | Is it thread-safe, what state does it hold, who owns it, must resources be closed? |

A single `ServiceLoader` can locate and instantiate multiple providers. Yet **whether the service loader is thread-safe** and **whether a provider's implementation is thread-safe** are two *independent* questions. A provider with no mutable state can be used concurrently once safely published; that does not make `iterator()`, `stream()`, or `reload()` on the same `ServiceLoader` thread-safe.

## 2. Lazy Discovery and Caching in ServiceLoader

`ServiceLoader` discovers providers **on demand**. Simply calling `ServiceLoader.load(...)` does not instantiate all implementations immediately. Actual work occurs during traversal:

- `loader.iterator()` returns an iterator; `hasNext()` and `next()` can continue locating, loading, and instantiating providers.
- `loader.findFirst()` behaves equivalently to taking the iterator's first element, potentially instantiating a provider.
- `loader.stream()` returns `Stream<ServiceLoader.Provider<S>>`. `Provider.type()` lets you inspect types before instantiation; `Provider.get()` obtains an instance.
- Running a terminal operation such as `toList()`, `findFirst()`, or `forEach()` on the stream can trigger discovery; do not assume creating a stream has already captured an immutable snapshot.

### Caching Along the Iterator and Stream Paths

- **Iterator:** the loader stores **already traversed/instantiated service instances**. Later iterator passes on the same loader usually return cached instances first, then discover remaining providers. Hence, on the same loader with an uncleared cache, `loader.iterator().next()` can return *the exact same object*.
- **Stream:** the loader stores **discovered provider descriptors** for the `stream()` path. Calling `Provider.get()` returns an instance according to the provider's implementation; do not assume every `get()` call returns either a singleton or a fresh object. Do not interchange iterator and stream caches in lifecycle design.
- **`reload()`:** clears these caches so subsequent traversals rediscover from scratch. It **does not close**, **does not mutate**, and **does not automatically reclaim** provider instances already held by other code.

Core difference example:

```java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

// Iterator path: materializes service instances during traversal.
List<Codec> instances = new ArrayList<>();
for (Codec codec : loader) {
    instances.add(codec);
}

// Stream path: materializes provider descriptors; get() obtains instances.
List<ServiceLoader.Provider<Codec>> descriptions =
    loader.stream().toList();
```

The snippet above is an *API illustration*, requiring an existing `Codec` interface and configured providers; Section 6 provides a standalone runnable project.

### Cache Verification Rules

The cache belongs to **each `ServiceLoader` object**, not a JVM singleton. Two calls creating two separate `ServiceLoader` instances are not forced to share provider instances. Also do not treat "first provider" order as a default selection policy: provider ordering across named modules may not be deterministic as expected; when multiple implementations exist, define explicit selection criteria.

## 3. Concurrency Rules: ServiceLoader Is Not Thread-Safe

Java SE 17 explicitly specifies: **`ServiceLoader` instances are not safe for concurrent use by multiple threads**. This rule covers traversing and updating internal state on the same loader, even when application code only reads results.

Access patterns that must not run concurrently on the *same instance*:

- Thread A calls `iterator().hasNext()/next()` while Thread B traverses the same loader;
- Thread A executes a terminal operation on `loader.stream()` while Thread B calls `findFirst()` or `iterator()`;
- Thread A traverses providers while Thread B calls `loader.reload()`;
- Multiple requests share a singleton `ServiceLoader` for dynamic discovery.

A failure scenario:

```text
Thread A                         Thread B
-----------------------------    ------------------------------
Iterator<S> it = loader.iterator()
it.hasNext()  // discovery
                                 loader.reload() // clears cache
it.next()     // old iterator
               -> ConcurrentModificationException
```

After `reload()`, previously created iterators **must be discarded**; their `hasNext()` or `next()` calls can throw `ConcurrentModificationException`. Old streams must also be discarded because the backing spliterator fails fast if the cache is cleared. That is specific post-reload behavior, **not an automatic mechanism turning every race condition into a predictable error**: concurrent loader access in general violates the thread-safety contract.

Two common false inferences:

1. "Just calling `iterator()` to read is read-only, so multiple threads can share it." False: traversal can mutate the cache via lazy discovery.
2. "Declaring `volatile ServiceLoader<S> loader` is enough." False: `volatile` only provides visibility of the **reference**; it neither locks nor synchronizes the loader's internal state.

Similarly, `loader.stream().parallel()` is not a safe way to parallelize discovery. To process providers in parallel, discover on a single thread, build a snapshot of appropriate instances, and then process the snapshot under the providers' thread-safety policies.

## 4. Three Correct Access Strategies

### Strategy A — Discover Once, Publish an Immutable Snapshot (Usually Preferred)

A registry or bootstrap thread owns the `ServiceLoader`, traverses **sequentially**, validates providers, copies results into `List.copyOf(...)`, and publishes via `volatile` or `AtomicReference`. Request threads read only the **snapshot** and never touch the loader.

```text
Registry thread (single owner)       Request threads
--------------------------------     --------------------------------
ServiceLoader.load(...)
traverse / validate providers
List.copyOf(loaded)
atomic publish(snapshot) --------->  read published snapshot
                                     call providers per thread-safety contract
                                     never call ServiceLoader
```

This decouples non-thread-safe discovery state from the request path; well suited when the provider set changes infrequently. `List.copyOf` only makes *the list structure* immutable; **it does not make stateful providers thread-safe**. Provider state is addressed in Section 5.

When refreshing, the registry builds a complete new snapshot and **swaps the reference atomically once**. Requests holding the old snapshot can finish with the old providers. Do not close old providers while requests are still using them.

### Strategy B — Synchronize All Access to the Loader

If multiple threads truly must call the loader, use **the exact same lock** guarding discovery, iteration, stream terminal operations, and `reload()`. Locking works only if *every* path touching the loader obeys it. With lazy streams, do not lock while creating the stream and release the lock before consuming it.

```java
synchronized (loader) {
    List<Codec> snapshot = new ArrayList<>();
    for (Codec codec : loader) {
        snapshot.add(codec);
    }
    // Returned data should be a copy to avoid leaking the iterator.
}
```

This is merely an excerpt assuming an existing `loader` variable and `Codec` type. `synchronized(loader)` is an *application locking convention*, not synchronization promised by `ServiceLoader` itself. `reload()` must also execute under **the same lock**. This approach is correct when applied consistently, though it increases contention; publishing snapshots is usually better so requests never block on discovery.

### Strategy C — Dedicated Loader per Owner/Lifecycle

You can create separate `ServiceLoader` instances per application context, plugin manager, or thread (when partitioning is genuinely needed), and never use any single instance concurrently. Weigh discovery/cache cost and ensure the right class loader is chosen. **A separate loader per request** is usually wasteful and complicates lifecycle management; **a JVM-wide shared static loader** risks retaining references to unloaded applications.

No single option fits every system; the choice depends on provider hot-swap needs, tenant/app isolation, and resource ownership.

## 5. Policy for Sharing Provider Instances

Solving `ServiceLoader` thread-safety **is not enough**. After publishing `List<S>`, the same instance may be called concurrently by multiple requests. Clearly document the provider contract:

| Provider Kind | Can it be retained and shared? | Implementation Guidance |
| --- | --- | --- |
| Stateless, immutable, no non-thread-safe state | Usually yes, once safely initialized and published | Application/plugin-registry singleton; shared snapshot |
| Stateful yet self-synchronized or documented thread-safe | Yes, within contract bounds | Watch throughput, shutdown, and resources |
| Stateful, not thread-safe (mutable buffers, session, transaction state) | Do not call same instance concurrently | Create per-request/session instances, use a factory or governed pool |
| Provider holding resources that must be closed | Retain only within a clear ownership lifecycle | Define `close`/`AutoCloseable`, wait for in-flight requests to finish |
| Provider scoped to a specific tenant/plugin version | Do not mix scopes even with identical interface | Registry/snapshot/class loader or module layer per tenant/version |

**Do not infer instance scope from `ServiceLoader`.** Having the iterator cache an instance does not turn the provider into a thread-safe singleton. Conversely, calling `Provider.get()` is not an API guarantee that "each request gets an independent new object"; a provider's factory method can intentionally return a singleton. When request-scoped objects are needed, publish **a factory with an explicit new-instance contract** and verify implementation behavior.

For example, a provider doing pure `String` processing without mutable fields is usually safe to share. A provider holding a `StringBuilder` as a shared buffer across concurrent requests risks races; make the buffer a local variable or design proper isolation. Adding a `ConcurrentHashMap` to cache results does not automatically make all other fields/methods of the provider safe.

### Proper Publication Under the Java Memory Model

`List.copyOf(...)` returns a structurally unmodifiable list; assigning it to an ordinary shared field without a *happens-before* relationship gives no guarantee readers will observe the update. Use:

- `private static volatile List<S> active = List.of();` with a single writer building the list completely before assigning;
- or `AtomicReference<List<S>>` with `set/get`, suitable when additional atomic operations are needed.

Providers must be fully initialized before publication; never leak `this` during construction. Once published, shared providers must still uphold their own thread-safety rules if any internal state changes.

## 6. Standalone Java 17 Example: Single-Thread Discovery, Shared Snapshot, Controlled Reload

The example has **one** stateless provider that converts text to uppercase. The main thread owns `ServiceLoader`; two workers only use the published snapshot. After both workers finish, main calls `reload()` to rediscover. The program demonstrates iterator caching before reload, a new instance after reload, and that the old snapshot still works.

Create the structure:

```text
service-loader-demo/
├── src/
│   └── demo/
│       ├── api/Processor.java
│       ├── provider/UpperProcessor.java
│       └── App.java
└── resources/
    └── META-INF/
        └── services/
            └── demo.api.Processor
```

**`src/demo/api/Processor.java`**

```java
package demo.api;

public interface Processor {
    String process(String input);
}
```

**`src/demo/provider/UpperProcessor.java`**

```java
package demo.provider;

import demo.api.Processor;
import java.util.Locale;

public final class UpperProcessor implements Processor {
    public UpperProcessor() {}

    @Override
    public String process(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
```

**`resources/META-INF/services/demo.api.Processor`** (one line with provider class name, no file extension):

```text
demo.provider.UpperProcessor
```

This is **class-path** provider registration. The file must be under `META-INF/services/` on the runtime classpath; the filename is the **fully qualified name of the service interface**, and the content line is the **fully qualified name of the provider implementation**. For Java modules with `module-info.java`, `uses`/`provides ... with ...` can be used instead of the classpath configuration file.

**`src/demo/App.java`**

```java
package demo;

import demo.api.Processor;
import java.util.*;
import java.util.concurrent.*;

public final class App {
    // Reference published atomically after discovery.
    private static volatile List<Processor> active = List.of();

    // Only the registry/main thread calls this method.
    private static void publish(ServiceLoader<Processor> loader) {
        List<Processor> found = new ArrayList<>();
        for (Processor p : loader) {
            found.add(p);
        }
        if (found.isEmpty()) {
            throw new IllegalStateException("No providers");
        }
        active = List.copyOf(found);
    }

    public static void main(String[] args) throws Exception {
        // Avoid depending on arbitrary worker pool TCCL.
        ServiceLoader<Processor> loader =
            ServiceLoader.load(Processor.class, App.class.getClassLoader());

        publish(loader);
        List<Processor> first = active; // capture snapshot once

        System.out.println("providers=" + first.size());
        System.out.println(
            "cached=" + (loader.iterator().next() == first.get(0)));

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            // Workers use only the stateless provider in the snapshot,
            // never touching the ServiceLoader object itself.
            Future<String> a =
                pool.submit(() -> first.get(0).process("hello"));
            Future<String> b =
                pool.submit(() -> first.get(0).process("world"));

            // Retrieve results in deterministic order a then b for stable stdout.
            System.out.println("one=" + a.get());
            System.out.println("two=" + b.get());
        } finally {
            pool.shutdown();
        }

        // Both Futures completed; main now operates on the loader.
        loader.reload();
        publish(loader);

        System.out.println(
            "newAfterReload=" + (active.get(0) != first.get(0)));
        System.out.println(
            "oldStillWorks=" + first.get(0).process("java"));
    }
}
```

From the `service-loader-demo` directory, run using **PowerShell** on Windows:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out src/demo/api/Processor.java src/demo/provider/UpperProcessor.java src/demo/App.java
Copy-Item -Recurse -Force resources/META-INF out/
java -cp out demo.App
```

The commands compile class files into `out` and copy SPI metadata to `out/META-INF/services`; thus Java locates the provider via classpath `out`. On macOS/Linux, replace the copy step with `cp -R resources/META-INF out/`.

**Stdout verified with `javac --release 17` and `java`:**

```text
providers=1
cached=true
one=HELLO
two=WORLD
newAfterReload=true
oldStillWorks=JAVA
```

Analysis:

1. `ServiceLoader.load(..., App.class.getClassLoader())` specifies the class loader to search for SPI. `publish` traverses the iterator on the main thread, instantiates `UpperProcessor`, and stores it in `List.copyOf`. The `volatile active` field publishes the reference with proper visibility.
2. `loader.iterator().next() == first.get(0)` is `true`: the same `ServiceLoader` cached the instance from the previous pass; `reload()` has not been called yet.
3. Both tasks use the same stateless provider; neither touches the loader. `Future.get()` retrieves results in deterministic order and guarantees tasks complete before reload.
4. `reload()` clears the cache. The next `publish` re-instantiates the classpath provider with its public no-arg constructor, resulting in a different identity. This is **the behavior in this example**, not a guarantee that every provider/factory in all configurations always creates a new object.
5. The `first` variable still holds the old snapshot reference, so `oldStillWorks=JAVA`. This proves `reload()` **neither destroys nor closes objects already handed to the application**.

**Intentional limitations of this example:** only one provider is configured; the main thread is the sole owner of the loader; `reload` occurs after both tasks finish. If implementing hot reload while requests are running, manage snapshot lifetimes and resource closing per the next section. Do not infer from this code that every provider is shareable across threads.

## 7. Reload, Snapshot Versions, and Resource Reclamation

`reload()` serves to rediscover providers on an existing loader. It **does not**:

- invalidate `ServiceLoader.Provider<S>` or `S` objects held elsewhere;
- call `close()` on providers or wait for requests using providers to complete;
- destroy class loaders, unload classes, or expand the set of classes/modules visible to the current loader;
- lock other threads using the loader;
- guarantee providers after reload have new identity across all configuration modes.

A safe refresh workflow in a multi-threaded application:

1. Only one **registry thread** performs discovery/reload. With multiple refresh commands, serialize them via an appropriate lock/queue.
2. Build and validate the **new snapshot**: correct service type, version, features/capabilities, configuration, and initialization state; if validation fails, keep serving the current snapshot depending on error policy.
3. Publish the new snapshot with a single `volatile` write or `AtomicReference.set`. New requests read the current snapshot; requests already holding the old snapshot continue with consistent data.
4. Stop issuing new requests against the old snapshot. **Wait for in-flight operations to finish** or use reference counting/leases/grace periods before closing old providers per contract.
5. Clear references from registries, static caches, listeners, thread-locals, executors/tasks, and other registrations to old providers/class loaders when unloading plugins. The garbage collector reclaims them only when no strong references actually remain.

This can be visualized as:

```text
T0: active -> Snapshot V1 -> Provider V1
                    ^ request A already acquired V1

T1: registry builds Snapshot V2, not yet published
T2: active -> Snapshot V2 -> Provider V2
                                 ^ new request B
    request A still has V1, finishes safely
T3: zero requests holding V1 -> close V1 resources (if ownership permits)
T4: drop references to V1 and old loader when retiring version
```

In real implementations, the condition "zero requests holding V1" requires an explicit mechanism; **`List.copyOf` and `volatile` do not wait for in-flight work**. If a provider is shared across V1/V2, closing per snapshot can break a provider still in use; define ownership clearly and close only once.

Providers are not required to implement `AutoCloseable`. If the SPI contract needs resource management, define an interface extending `AutoCloseable` or a lifecycle adapter explicitly. Never treat `reload()` as releasing sockets, threads, files, or database connections.

## 8. Retention Scope for ServiceLoader by ClassLoader and ModuleLayer

### `load(Service.class)` and the Thread Context Class Loader

`ServiceLoader.load(S.class)` uses the **thread context class loader (TCCL)** at call time. In application servers, plugin hosts, or thread pools, TCCL can vary across threads/apps. Therefore two call sites invoking the exact same API can discover **different provider sets**.

An important note from the Javadoc: do not cache a loader created via `load(S.class)` at **JVM-wide** scope when multiple apps/contexts have separate class loaders. Long-lived caches can see providers from another application or retain class loaders, causing memory leaks.

When the owner is known, prefer an explicit design:

- `ServiceLoader.load(S.class, selectedClassLoader)`: explicitly specifies the class loader scope matching the SPI and providers.
- `ServiceLoader.load(moduleLayer, S.class)`: traverses providers in the specified module layer and its ancestor layers per the API; do not use this for unnamed modules such as the classpath.
- Keep loaders/registries at the appropriate **application/plugin-manager/tenant level**; do not turn them into context-blind global caches.

Classes with the same fully qualified name defined by two different class loaders are two **distinct types**. The service API must be shared via the proper class-loader/module relationship; if a plugin reloads under a new loader yet a provider gets cast to an old copy of the interface, `ClassCastException` or `ServiceConfigurationError` can occur.

### Reload Does Not Equal Hot Deployment

`reload()` only forces the loader to **look up again** within the environment it currently knows. To actually add/replace plugin code, the system may need a new class loader/module layer, a new provider registry, and a version-switching policy. If you keep using the old class loader and retaining references to old classes, Java does not overwrite classes just because `reload()` was called. To unload cleanly, ensure static caches, TCCLs, background threads, and listeners do not inadvertently retain the old loader.

## 9. Access via stream and Provider.get(): Notes on Instance Scope

`ServiceLoader.Provider<S>` allows inspecting `type()` before calling `get()`. For modules with provider factory methods, the type from `type()` reflects the provider method's return type, not necessarily the factory's implementation class.

Avoid the following form if the goal is **a single instance per application** without an explicit policy:

```java
ServiceLoader.load(Codec.class)
    .stream()
    .map(ServiceLoader.Provider::get)
    .forEach(codec -> register(codec));
```

This snippet illustrates an app needing a `Codec` interface and `register` function. It can work for sequential registration, yet is **insufficient** to prove `get()` returns a singleton, a new instance each time, or a thread-safe object. To select providers by metadata, filter `Provider.type()` first, call `get()` where ownership is clear, and store results in a snapshot/registry per policy.

Once a stream is obtained from a loader, **process it under the registry thread's ownership**; do not hand streams/iterators out for other requests to keep traversing. `stream().parallel()` does not solve loader thread-safety either; for parallel execution, complete discovery first and then apply concurrency to eligible providers.

## 10. Common Operational Failures

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `ConcurrentModificationException` on `next()` or stream traversal | `reload()` cleared cache after iterator/stream was created | Discard old iterators/streams; do not reload mid-traversal; serialize registry |
| Missing results/different providers across threads | Discovery used different TCCLs or different module layers | Specify class loader/layer per application/plugin scope |
| Concurrent calls to provider produce wrong results | Provider holds non-thread-safe mutable state | Make stateless/immutable, synchronize properly, or use per-request instances |
| Plugin unloaded yet RAM/class loader not reclaimed | Snapshot, static cache, listener, thread-local, or thread still holds provider/loader | Close per lifecycle then remove all relevant strong references |
| Old objects still execute after `reload()` | Callers still hold references to old providers | Need versioned snapshots and a retire/drain procedure |
| New plugin still invisible after `reload()` | Current class loader/layer cannot see the new provider | Check deployment, SPI metadata, and loader scope; may need a new loader |
| `ServiceConfigurationError` during traversal | Bad `META-INF/services`, unloadable class, failing constructor/provider method | Check packaging, module `uses/provides`, permissions, and root error; fail fast at bootstrap |
| Same provider instantiated multiple times unexpectedly | Creating multiple `ServiceLoader`s, arbitrary `Provider.get()` calls, reloads | Define scope and cache in a registry; do not rely on implicit singletons |
| Slow requests when picking providers | Lazy discovery/constructors running on the request path | Discover and validate before accepting requests; publish ready snapshots |

**Note on `ServiceConfigurationError`:** this is a subclass of `Error`; lazy discovery can cause `hasNext()`, `next()`, or stream terminal operations to fail late. Wrap handling at the bootstrap/registry boundary to surface useful configuration details. Do not catch all `Throwable` and silently proceed with a partial provider set; that can create inconsistent behavior.

## 11. Rules for Choosing Scope by Use Case

| Use Case | Scope to Consider | Access Pattern |
| --- | --- | --- |
| Services unchanged throughout app lifetime | One registry per application, immutable snapshot | Registry traverses once; requests read snapshot only |
| Hot-reloadable plugins | Registry per plugin context with versioned snapshots | Sequential discovery/reload; atomic publish; drain old versions |
| Multiple tenants/apps sharing a JVM | Isolated loader/layer/registry per tenant/app | Never cache `ServiceLoader.load(S.class)` VM-wide |
| Stateless, thread-safe provider | Shared instance per application/plugin lifetime | Safely publish, call directly from snapshot |
| Stateful, non-thread-safe provider | Instance or state bound to request/session | Factory/pool by contract, do not share instance blindly |
| Multiple threads genuinely need direct loader access | Shared lock on loader or partitioned owner | All iteration/stream/reload goes through one serialization mechanism |
| Need to unload plugins and reclaim resources | Explicit owner/lifecycle, not just GC | Wait for in-flight, close if owned, clear strong references |

### Pre-Production Checklist

- [ ] Identify who owns `ServiceLoader`; no two threads concurrently discover/reload on the same instance.
- [ ] Choose the right `ClassLoader`/`ModuleLayer` and avoid accidental caching at overly broad JVM/tenant scope.
- [ ] Distinguish iterator's provider-instance cache from stream's descriptor cache; do not rely on `Provider.get()` as a singleton/per-request policy.
- [ ] Discover and validate before requests; publish snapshots via `volatile`/`AtomicReference` or an equivalent happens-before mechanism.
- [ ] Prove or specify thread-safety, scope, and resource ownership of **provider instances** separately.
- [ ] On reload, discard old iterators/streams, build a new versioned snapshot, manage in-flight requests, and close old resources at the right time.
- [ ] Test SPI metadata, `ServiceConfigurationError`, provider ordering, and behavior with zero or multiple providers.
- [ ] When unloading a class loader, audit static caches, listeners, thread-locals, background threads, and lingering references.

Official API references for Java 17: [`ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html) and [`ServiceLoader.Provider`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html).

**Conclusion:** `ServiceLoader` is a **stateful, lazily cached, non-thread-safe discovery** object. Providers are **execution objects with their own thread-safety and lifecycle policies**. A reliable design normally gives a single registry ownership of discovery/reload, safely publishes snapshots to requests, and releases old instances/class loaders only once no consumers depend on them.
