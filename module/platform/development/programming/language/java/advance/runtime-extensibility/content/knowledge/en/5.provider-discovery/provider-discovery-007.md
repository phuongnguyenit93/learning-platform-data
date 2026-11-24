# Iterator Caching, Stream Caching, and the Effect of reload in Java ServiceLoader

## 1. Context: How Does ServiceLoader Discover Providers?

`ServiceLoader<S>` (Java 6+, extended with `stream()` since Java 9) helps an application locate implementations of a **service contract** at runtime. For example, a host defines `TaskProvider`, while provider JARs register implementations via `META-INF/services/<fully-qualified-service-name>` on the class path or via `provides ... with ...` in a named module. The host can traverse providers without directly depending on implementation classes.

This topic focuses on a detail that heavily affects runtime behavior: **`ServiceLoader` performs lazy loading and retains discovered/loaded providers in a cache**. Two key traversal APIs are:

- `iterator()`: returns `Iterator<S>`; when traversing, the elements obtained are **actual instances** of the service.
- `stream()`: returns `Stream<ServiceLoader.Provider<S>>`; each element is a **provider descriptor/handle** (`Provider<S>`), from which you can inspect `type()` or call `get()` to obtain an instance.

The `reload()` method **clears the provider cache of the `ServiceLoader` object currently in use**. It does not immediately instantiate new instances and is not a mechanism for replacing class bytecode, unloading old classes, or automatically updating JARs.

### Four Objects That Must Be Distinguished

| Object | Role | Retains instances/providers itself? |
| --- | --- | --- |
| `ServiceLoader<S>` | Holds service info, provider search scope (class loader/module layer), and its own caches | **Yes**, caches already loaded/traversed providers |
| `Iterator<S>` | Instance traversal cursor, created by `serviceLoader.iterator()` | Re-reads cached instances, then searches/loads unvisited ones |
| `Stream<Provider<S>>` | One-shot pipeline for traversing provider metadata | Uses `ServiceLoader`'s provider descriptor source; a stream is **not** a default list of instances |
| `Provider<S>` | Handle for `type()` and `get()` | `get()` obtains/creates an instance; do not assume it always returns the same object |

"Cache" here is the cache of **a single `ServiceLoader` instance**, not a JVM-wide cache; standard `Stream`s are also lazy, yet that is a different concept from `ServiceLoader`'s cache. Calling `ServiceLoader.load(...)` again creates **another `ServiceLoader`** with its own cache; having both loaders see the same class does not force them to share created provider objects.

## 2. Iterator Cache: Load as Needed, Remember What Was Loaded

According to the Java SE 17 API:

1. Calling `ServiceLoader.load(TaskProvider.class)` creates a service loader. Providers are not guaranteed to be instantiated at this step.
2. `loader.iterator()` creates an iterator; providers are located and instantiated **as traversal demands**, instead of instantiating everything when creating the loader.
3. When the iterator encounters a provider that needs instantiation, `ServiceLoader` adds that **instance** to the corresponding cache.
4. Another call to `loader.iterator()` on the **same loader** returns cached instances **in the order they were previously loaded**, then continues finding and instantiating remaining providers as needed.
5. `loader.findFirst()` is a convenience method to retrieve the first provider via the iterator mechanism; if the first is already cached, it can return that cached instance.

Suppose there are three providers A, B, C. If the first traversal stops after taking only A, the current instance cache contains only A. A second traversal can return A from cache, then instantiate B and C if actually traversed to. **Creating a new iterator does not discard the cache.**

Therefore, `for (TaskProvider p : loader) { ... }` across multiple loops on the same loader usually reuses previous instances. This behavior is important to consider if a constructor opens connections, a provider holds mutable state, or it implements `close()`: repeated traversals do not automatically create fresh resources, and `ServiceLoader` does not automatically call `close()` on providers.

### Laziness Does Not Mean Errors Cannot Occur

`hasNext()` or `next()` can throw `ServiceConfigurationError` while reading metadata/provider configurations, loading classes, resolving dependencies, or instantiating providers. Do not claim "all errors only occur in `next()`". A broken provider can interrupt discovery midway; recovering by continuing traversal is described in the API docs only as best-effort, **not guaranteed**.

## 3. Stream Cache: Provider Descriptors First, Instances Later

`loader.stream()` returns `Stream<ServiceLoader.Provider<S>>`. It does **not** return `Stream<S>` directly. Stream traversal is deferred until a terminal operation such as `findFirst()`, `toList()`, or `forEach(...)`.

~~~java
ServiceLoader<TaskProvider> loader = ServiceLoader.load(TaskProvider.class);

// Read metadata: no need to create instances to filter by provider kind.
List<Class<? extends TaskProvider>> types = loader.stream()
        .map(ServiceLoader.Provider::type)
        .toList();

// Only retrieve instances when actually needed.
List<TaskProvider> instances = loader.stream()
        .map(ServiceLoader.Provider::get)
        .toList();
~~~

**This is an illustrative snippet**, requiring the `TaskProvider` interface and registered providers to run standalone. `Provider.type()` supports inspecting types and annotations without calling the service implementation's constructor. For a named-module provider created via a static `provider()` factory method, `type()` returns **the return type of the provider method**, not necessarily the class containing the method.

As the stream traverses, `ServiceLoader` remembers **provider descriptors** discovered from previous stream runs. A fresh `loader.stream()` call can process already-cached descriptors first and then discover remaining providers. Provider ordering depends on lookup rules and configuration/modules; **do not rely on arbitrary ordering across JARs/modules** to determine business priority.

Easily confused boundaries:

- `Provider.type()` **does not mean** a provider instance has been created.
- `Provider.get()` returns an instance. The API does not promise it is a singleton or reference-identical to another `get()` call. For class-path providers created via a public no-arg constructor, repeated `get()` calls can construct multiple objects. Do not use `==` as a provider selection contract through this API.
- **Do not assume the caches of `iterator()` and `stream()` share the exact same object instances or creation timing.** One side works with instances, the other with `Provider` descriptors; if business logic needs a single managed object, the host should own an explicit registry/snapshot.
- `stream()` creates a Java `Stream` on which **only one terminal operation may be executed**. Reusing an already-consumed stream can throw `IllegalStateException`; this error is completely different from a stream invalidated by `reload()`.
- `sorted()`, `collect()`, or `toList()` can force discovery of the entire descriptor list. `findFirst()` can stop early. Having metadata for all providers **does not mean** `get()` has been called for all of them.

## 4. Java 17+ Practice: Runnable Observation of Cache and Reload

The example below uses **a single provider** whose constructor prints creation counts. It clearly shows: the iterator reuses instances; reload drops the cache; an instance already handed to a caller remains alive; streams fetch metadata before creating objects.

### 4.1. Directory Structure

~~~text
service-cache-demo/
├── src/
│   ├── demo/
│   │   ├── TaskProvider.java
│   │   ├── CountingProvider.java
│   │   ├── IteratorCacheDemo.java
│   │   └── StreamReloadDemo.java
│   └── META-INF/
│       └── services/
│           └── demo.TaskProvider
└── out/                  # Generated when compiling
~~~

The provider-configuration file must reside on the **runtime class path** and match the **fully qualified binary name** of the service interface.

File `src/demo/TaskProvider.java`:

~~~java
package demo;

public interface TaskProvider {
    String name();
}
~~~

File `src/demo/CountingProvider.java`:

~~~java
package demo;

public final class CountingProvider implements TaskProvider {
    private static int sequence;
    private final int id;

    public CountingProvider() {
        id = ++sequence;
        System.out.println("constructor #" + id);
    }

    @Override
    public String name() {
        return "provider-" + id;
    }
}
~~~

Contents of `src/META-INF/services/demo.TaskProvider`:

~~~text
demo.CountingProvider
~~~

With the class-path mechanism, `CountingProvider` is a public class implementing the service with a public no-argument constructor. **Named modules** also allow declaring providers via `provides ... with ...` and can use a public static `provider()` factory method; this example intentionally uses the class path to make constructor observation easy.

### 4.2. Iterator: Same Cache Before Reload, New Instance After Reload

File `src/demo/IteratorCacheDemo.java`:

~~~java
package demo;

import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.ServiceLoader;

public final class IteratorCacheDemo {
    public static void main(String[] args) {
        ServiceLoader<TaskProvider> loader = ServiceLoader.load(
                TaskProvider.class, IteratorCacheDemo.class.getClassLoader());

        TaskProvider first = loader.iterator().next();
        TaskProvider again = loader.iterator().next();
        System.out.println("same before reload = " + (first == again));

        Iterator<TaskProvider> staleIterator = loader.iterator();
        loader.reload();

        try {
            staleIterator.hasNext();
            System.out.println("unexpected");
        } catch (ConcurrentModificationException e) {
            System.out.println("stale iterator = ConcurrentModificationException");
        }

        TaskProvider fresh = loader.iterator().next();
        System.out.println("same after reload = " + (first == fresh));
        System.out.println("old object = " + first.name());
    }
}
~~~

Explanation:

- The first `next()` creates `CountingProvider` id=1 and caches the instance.
- The second `next()` on **a new iterator from the same loader** retrieves id=1 again; the constructor does **not** run again.
- `staleIterator` was created **before** `reload()`. After the cache is cleared, `hasNext()` on the old iterator throws `ConcurrentModificationException`, even though there are not two threads.
- A fresh iterator after reload creates id=2 on demand. The old instance `first` stays alive because the `first` variable still holds a reference, so `first.name()` still works.

### 4.3. Stream: type First, Provider.get() Later; Old Stream Becomes Invalid

File `src/demo/StreamReloadDemo.java`:

~~~java
package demo;

import java.util.ConcurrentModificationException;
import java.util.ServiceLoader;
import java.util.stream.Stream;

public final class StreamReloadDemo {
    public static void main(String[] args) {
        ServiceLoader<TaskProvider> loader = ServiceLoader.load(
                TaskProvider.class, StreamReloadDemo.class.getClassLoader());

        Stream<ServiceLoader.Provider<TaskProvider>> metadataStream = loader.stream();
        System.out.println("stream created");

        ServiceLoader.Provider<TaskProvider> entry =
                metadataStream.findFirst().orElseThrow();
        System.out.println("type = " + entry.type().getSimpleName());

        System.out.println("first get = " + entry.get().name());
        System.out.println("second get = " + entry.get().name());

        Stream<ServiceLoader.Provider<TaskProvider>> staleStream = loader.stream();
        loader.reload();

        try {
            staleStream.findFirst();
            System.out.println("unexpected");
        } catch (ConcurrentModificationException e) {
            System.out.println("stale stream = ConcurrentModificationException");
        }

        var newEntry = loader.stream().findFirst().orElseThrow();
        System.out.println("type after reload = " + newEntry.type().getSimpleName());
    }
}
~~~

Here `metadataStream.findFirst()` runs a terminal operation and retrieves only the provider metadata; the constructor does not need to run yet. Only `entry.get()` requests an instance. With this example's provider class and Java 17 behavior, two calls to `get()` create two new objects and print two constructor lines. However, **do not design around a singleton or specific identity assumption when using `Provider.get()`**; manage lifecycle in the host if a single shared instance is required.

`staleStream` was created before `reload()` without executing a terminal operation yet. The spliterator obtained from `ServiceLoader.stream()` checks for cache modifications; when traversal starts after reload, it detects the changed generation and throws `ConcurrentModificationException`. We create a **fresh stream** after reload to continue traversing.

### 4.4. Compiling and Running

Run the following commands **from the `service-cache-demo` directory** in PowerShell with JDK 17+ installed:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 -d out src/demo/TaskProvider.java src/demo/CountingProvider.java src/demo/IteratorCacheDemo.java src/demo/StreamReloadDemo.java
Copy-Item -Recurse -Force src/META-INF out/META-INF
java -cp out demo.IteratorCacheDemo
java -cp out demo.StreamReloadDemo
~~~

Output of `IteratorCacheDemo`:

~~~text
constructor #1
same before reload = true
stale iterator = ConcurrentModificationException
constructor #2
same after reload = false
old object = provider-1
~~~

Output of `StreamReloadDemo` (the second `java` process is a new JVM so static `sequence` starts from 0 again):

~~~text
stream created
type = CountingProvider
constructor #1
first get = provider-1
constructor #2
second get = provider-2
stale stream = ConcurrentModificationException
type after reload = CountingProvider
~~~

If the constructor prints fewer/extra times, first check that the provider-configuration file was copied intact to `out/META-INF/services/demo.TaskProvider`, that the class path truly contains only the intended example, and that the program runs in a fresh JVM. You can use `jar tf` when packaging into a JAR.

## 5. What Does reload() Actually Do to Old Iterators, Streams, and Instances?

Java SE 17 describes `reload()` as clearing **the `ServiceLoader`'s provider caches**. *New* `iterator()` or `stream()` calls after reload return to lazy provider lookup from scratch; iterators/streams obtained *before reload* must be discarded.

| Item | Before `reload()` | After `reload()` |
| --- | --- | --- |
| Iterator instance cache | Holds provider instances already traversed | Cleared; fresh traversals may re-instantiate |
| Stream provider descriptor cache | Holds providers discovered via stream | Cleared; new streams look up again on demand |
| Previously created iterator | Can advance or pull cached instances | `hasNext()/next()` throws `ConcurrentModificationException` when used |
| Previously created stream | Can execute one terminal operation | Backing spliterator is fail-fast after reload; discard old stream and create a new one |
| Object instance already returned to caller | Caller may hold references | **Not destroyed**; remains alive while references exist |
| Provider class already loaded in JVM | Defined by class loader | **Not unloaded/redefined** just by reload |
| Visible provider JARs/modules | Determined by class loader/module layer | **Does not automatically expand** class/JAR/module lookup scope |
| Threads currently using plugin | May have in-flight requests | **Not stopped** by reload |

**Biggest consequence:** `reload()` refreshes **one loader's discovery/instantiation cache**, not the entire runtime state. If a request holds an old provider instance, that request can continue; if the old instance holds file handles, threads, connection pools, or a `ClassLoader`, `reload()` does not release them automatically.

### 5.1. Why Does ConcurrentModificationException Happen?

This is **fail-fast behavior for cache state changes**. An iterator/stream tied to an old cache/generation state cannot traverse consistently after the cache has been reset. Java SE 17 specifies:

- Iterator `hasNext()` and `next()` after `reload()`: throws `ConcurrentModificationException`.
- Backing spliterator of `stream()`: fail-fast if the provider cache is cleared.

The exception name is often associated with concurrency, yet **a single thread** calling `reload()` between two operations can trigger it too. Conversely, fail-fast is **not** a locking mechanism or a multi-thread safety guarantee.

### 5.2. Reload Is Not "Reusable Stream"

Two errors to distinguish by example:

~~~java
// Standalone illustration: loader is a valid ServiceLoader<TaskProvider>.
var once = loader.stream();
once.count();          // First terminal operation
once.count();          // IllegalStateException: stream already consumed

var stale = loader.stream();
loader.reload();
stale.findFirst();     // ConcurrentModificationException due to cache reset
~~~

This is a **non-standalone illustrative snippet** deliberately showing two errors; do not put it into a production app. In practice, the safest rule is **create a new stream for each traversal** and **do not hold iterators/streams across a reload point**.

### 5.3. Reload Does Not Guarantee Seeing New JARs

Several misconceptions to eliminate:

- If you copy a new plugin JAR into `plugins/` but **the current class loader lacks that URL**, calling `reload()` does not add the URL/class path. You need a loader capable of seeing that provider or create an appropriate new loader/module layer.
- If the provider class was already loaded by a class loader, editing bytecode on disk and calling `reload()` **does not** redefine that class from new bytecode. Java class identity is tied to binary name and defining class loader.
- To hot-deploy/hot-swap implementations or isolate versions, you usually need to manage **a new plugin loader generation** (such as an appropriate `URLClassLoader` or `ModuleLayer`), initialize new providers, switch traffic, stop old providers, and drop old references. Calling `reload()` alone is insufficient.
- If `ServiceLoader.load(Service.class)` uses the one-argument overload, it captures the **thread context class loader** at loader creation time. Changing the thread's TCCL later does not change the scope of the already-created `ServiceLoader`; you must create a new loader with the right class loader.

## 6. How to Design Safe Provider Refreshing in Real Applications

`ServiceLoader` is **not thread-safe**. Do not let one thread traverse while another calls `reload()` on the same instance, and do not share iterators/streams whose generation may change without coordination.

### Level 1: Only Need to Reload Cache at Safe Pauses

Use when all discovery queries run sequentially and provider sources remain within the same loader scope:

1. Stop issuing new traversals on the old loader and wait for current traversals to finish.
2. Ensure all old iterators and streams are discarded; if old objects are still running, separate their lifecycles.
3. Call `loader.reload()`.
4. For each new lookup, create a fresh `loader.iterator()` or `loader.stream()`. Only start using new instances after validating configuration.
5. Close host-managed resources of the old generation once no requests are using them.

### Level 2: Immutable Snapshot for Concurrent Requests

For a host serving requests across multiple threads, it is cleaner to use discovery to build a **snapshot of selected instances**, then have requests read the snapshot. On refresh, build the new snapshot on a coordinator thread and validate it thoroughly before publishing; traffic reads an atomically replaced reference.

**Non-standalone** illustrative snippet, assuming `TaskProvider`, `pluginClassLoader`, and `activeProviders` are properly declared:

~~~java
ServiceLoader<TaskProvider> discovery =
        ServiceLoader.load(TaskProvider.class, pluginClassLoader);

List<TaskProvider> nextProviders = discovery.stream()
        .map(ServiceLoader.Provider::get)
        .toList();                    // Materialize and validate before publishing

List<TaskProvider> previous =
        activeProviders.getAndSet(nextProviders); // AtomicReference<List<TaskProvider>>

// Only stop/close providers in previous when no requests are still using them.
~~~

`Stream.toList()` (Java 16+) produces a list unmodifiable via `List` add/remove operations; that **does not make individual provider instances thread-safe**. You may need a `Generation` object holding the provider list, class loader, version, and lifecycle tracker to coordinate stopping/releasing the right generation. If the host does not track when old requests finish, closing providers prematurely can cause in-flight requests to fail.

### Level 3: Plugins Whose JARs/Versions Are Replaced at Runtime

Create a new class loader/module layer for the new generation, discover and validate providers in the new generation, and swap snapshots only once ready. After the old generation has no remaining requests, stop providers, close plugin resources, drop references to instances/`Class`/`ClassLoader`, and close `URLClassLoader` when appropriate. `URLClassLoader.close()` closes loader resources, yet **does not force the JVM to unload classes immediately**.

Class loaders/JPMS are also not security sandboxes: load only trusted plugin code, or isolate into separate processes/containers if untrusted code must execute.

## 7. Real-World Scenarios and Sound Decisions

| Scenario | Do | Do Not Infer |
| --- | --- | --- |
| Loop uses `iterator()` multiple times on the same loader | Understand cached provider instances will be reused; manage state/thread-safety | "Every loop gets a fresh provider" |
| Want to list implementations by annotation without instantiating | `stream().filter(p -> p.type()...).toList()` | "`stream()` always calls constructors" |
| Need to instantiate a provider after selection | `Provider.get()` and host-owned instance management | "`get()` is always a singleton like the iterator cache" |
| After one traversal, want to re-read provider sources | `reload()` at a safe coordination point, then create new iterator/stream | "Can keep using old iterator/stream" |
| Seeing `ConcurrentModificationException` | Check for reload mid-traversal and any multi-thread access | "Two threads definitely modified the same collection" |
| New provider does not appear | Check SPI metadata, class loader visibility, module layer, runtime class path | "Calling reload repeatedly will find the new JAR" |
| Old provider still runs after reload | Complete lifecycle/drain requests, drop references, release resources at the right time | "Reload will call stop/close" |
| Need safe refresh under load | Build/validate new snapshot then atomically swap, drain old generation | "`ServiceLoader` has built-in multi-thread synchronization" |

## 8. Common Pitfalls When Handling Exceptions and State

### 8.1. Confusing Discovery Errors with Cache Invalidation Errors

- `ServiceConfigurationError`: provider configuration error, provider load/instantiation error, metadata resource or dependency error (can arise during `hasNext()`/`next()` or stream terminal operations).
- `ConcurrentModificationException`: in this lesson's context, an old iterator/stream used after `reload()`; can happen even on a single thread.
- `IllegalStateException`: Java `Stream` reused after a terminal operation.
- `ClassNotFoundException`/`NoClassDefFoundError`: class not found or cannot be defined/initialized within the loader scope; investigate root cause and dependencies rather than blaming "stale cache".

Do not swallow `ServiceConfigurationError` and silently skip providers: it can leave the host running without features and without warning. Log the service type, class loader/module source, provider-configuration location (when possible), and exception cause; in plugin systems with error isolation, document the skip/fallback policy clearly.

### 8.2. Memory Leaks from Caches and Old References

A long-lived `ServiceLoader` can hold instances/provider metadata, keeping the class loader, plugin classes, and resources alive indirectly. `reload()` clears the cache inside that loader, yet **does not clear references in other registries**, thread-locals, static fields, listeners, or requests holding instances. Investigate where strong references are held instead of treating `reload()` as a GC command.

### 8.3. Wrong Assumptions About Ordering

The cache preserves **loaded** order; it does not mean a certain provider always comes first in every class path/module layer configuration. If the host requires priority or capabilities, use explicit metadata and sorting/selection rules. `findFirst()` is suitable when whichever provider comes first in discovery order genuinely suffices.

### 8.4. Confusing Cache Scope with Service Lifecycle

`ServiceLoader` manages finding/instantiating providers, not the full application lifecycle. If a provider is a stateful service, host-wide singleton, or needs start/stop/health-check, build a dedicated service registry/container. Default caching helps discovery, not full service management.

## 9. QA Checklist and Reinforcement Exercises

Run these tests against the sample app (each test isolated or creating a fresh loader per scenario):

1. **Lazy iterator:** create the loader without calling `next()`; confirm no constructor line appears yet, then after `next()` confirm it appears once.
2. **Instance cache:** call `loader.iterator().next()` twice on the same loader, confirm `== true` and constructor runs once.
3. **Partial discovery:** add a second provider in `META-INF/services/demo.TaskProvider`. First retrieve only one provider; next traverse all and verify the cache expands on demand.
4. **Stream metadata:** run only `stream().map(Provider::type).toList()` and check for zero provider constructor logs; then call `Provider.get()` to observe instantiation.
5. **Two `Provider.get()` calls:** in the `CountingProvider` example, two calls create new instances; do not rely on this identity as a general singleton contract.
6. **Reload:** create an iterator and stream, call `reload()`, reuse the old traversals to see `ConcurrentModificationException`; create new traversals and verify they work.
7. **Old reference:** keep object id=1 before reload; after reload confirm `name()` still works on the old object and a new object is obtained via the iterator.
8. **One-shot Stream:** try running two terminal operations on the same stream; distinguish `IllegalStateException` from cache invalidation.
9. **TCCL/loader visibility:** try changing the class loader passed to `load(service, loader)`. When the provider JAR is invisible to that loader, `reload()` does not fix it.
10. **Concurrency/lifecycle:** create a single coordinator that performs refresh, publishes an immutable snapshot, and test multiple concurrent requests; clearly define when the old generation is closed.

### Self-Check Questions

- Does the cache belong to `ServiceLoader` or to each `iterator()` call?
- Why does `stream()` return `Provider<S>` instead of `S`?
- Does calling `type()` necessarily instantiate the implementation?
- Does the API guarantee two `Provider.get()` calls return the same instance?
- Does `reload()` make all old instances disappear?
- Why can using an old iterator after reload throw `ConcurrentModificationException` even on a single thread?
- If a new JAR is copied into a directory not yet on the class loader, what effect does `reload()` have?
- When refreshing for multiple requests, why is a new snapshot + traffic swap safer than sharing a `ServiceLoader` that is reloading?

If you can answer via the **mechanics** and verify with constructor/identity logs and exceptions, you have grasped the core: **the iterator caches instances, streams let you inspect provider descriptors, and reload resets discovery state on that `ServiceLoader` while invalidating old iterators/streams**.

## 10. Standard References

- Java SE 17 API — `ServiceLoader` (especially "Timing of provider discovery", "iterator", "stream", "reload", "Concurrency"): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17 API — `ServiceLoader.Provider`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html
- Java SE 17 API — `Stream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html
- Java SE 17 API — `ConcurrentModificationException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ConcurrentModificationException.html
