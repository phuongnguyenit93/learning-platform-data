# ServiceLoader: Provider Caching, Reloading, and Concurrency Limitations

`java.util.ServiceLoader<S>` is a Java utility for finding **service providers** that implement an interface or service class known to the application in advance. It is very useful in an SPI/plugin architecture because the host can depend only on a **service contract**; implementations are declared in `META-INF/services` (classpath) or `provides ... with ...` (JPMS).

However, `ServiceLoader` is not a “rescan every JAR and create new objects on every call” mechanism, nor is it a thread-safe registry or an automatic hot-reload system. Java 17 defines three decisive characteristics:

1. **Providers are located and loaded on demand; the loader has a cache.** A new iterator traverses the cached providers first before continuing to discover the remaining providers. Along the iterator path, previously created instances are reused.
2. **`reload()` clears the `ServiceLoader`’s own cache.** Re-traversing can discover and instantiate new providers; iterators/streams **obtained before the reload must be discarded**. However, `reload()` **does not change `Class<?>` types already defined by the JVM**, does not close the class loader, and does not replace JARs in the process.
3. **A single `ServiceLoader` instance is not safe when used concurrently by multiple threads.** Do not concurrently invoke `iterator()`/`hasNext()`/`next()`/`stream()`/`reload()` on the same instance without an external synchronization design. Thread safety of a **provider object** is a separate concern.

This lesson belongs to **Java core – classloader / Service Loading**, focusing specifically on **provider caching, reloading, and concurrency limitations**. The examples run on **JDK 17+** and clearly explain when a provider constructor runs, what gets cached, when a new loader must be created, and how to organize the lifecycle without retaining old plugins in memory.

## 1. Diagram Distinguishing Objects Easily Referred to Collectively as “Loader”

A simple plugin architecture:

```text
     HOST APPLICATION
  ┌─────────────────────────────────────┐
  │ Service API: spi.GreetingService    │
  │             │                       │
  │ ServiceLoader<GreetingService>      │
  │   ├─ provider discovery/cache       │
  │   └─ iterator()/stream()/reload()   │
  └─────────────┬───────────────────────┘
                │ uses a ClassLoader for lookup
                ▼
  ┌─────────────────────────────────────┐
  │ ClassLoader (app/URLClassLoader)     │
  │   ├─ find META-INF/services/...     │
  │   ├─ load provider implementation   │
  │   └─ identify runtime Class<?>    │
  └─────────────┬───────────────────────┘
                │
                ▼
  ┌─────────────────────────────────────┐
  │ Provider object(s)                  │
  │ impl.FriendlyService, ...           │
  │ Has state, constructor and lifecycle│
  └─────────────────────────────────────┘
```

Three distinct things:

- **`ServiceLoader<S>` object:** holds the service-lookup context and the provider cache; `reload` acts on **the cache inside this object**.
- **`ClassLoader` object:** responsible for seeing the resource/service descriptor and defining/loading Java classes. `ServiceLoader.reload()` **does not invoke an arbitrary “unload/redefine” mechanism** on this object.
- **Provider instance:** the concrete object created by a constructor or a provider factory method. It may be stateless, mutable, hold threads/sockets/file handles, or implement `AutoCloseable`. `ServiceLoader` is not a lifecycle manager that automatically calls `close()` for every provider.

An API interface must be resolved by both the host and the provider to the **same runtime type**. If the plugin loader defines its own copy of `spi.GreetingService`, the provider may not be assignable to the host interface even if the binary name is identical.

## 2. How Are Providers Found? Discovery Differs from Instantiation

There are two common deployment styles.

**Classpath/unnamed module:** the provider class is specified in a resource named `META-INF/services/<binary-name-of-service>`. For example:

```text
META-INF/services/spi.GreetingService
```

Resource contents:

```text
impl.FriendlyService
```

The name in the file is the **binary name of the implementation**, not the `.class` file name. The file may contain multiple provider names, one per line; Java 17 requires service-configuration files to be **UTF-8** encoded, supporting blank lines and `#` comments.

**Named module (JPMS):** the module declares:

```java
module com.example.plugin {
    requires com.example.api;
    provides spi.GreetingService with impl.FriendlyService;
}
```

This is an **illustrative `module-info.java`**, not a standalone program yet. The host module needs `uses spi.GreetingService;` when calling SPI discovery; module exports/readability and `ModuleLayer` must be validly configured. A named module can use a **public static provider() factory** under the conditions specified by the Javadoc, unlike classpath providers which typically use a public zero-argument constructor.

**Discovery does not mean creating an instance:** when you have `ServiceLoader<GreetingService> loader = ServiceLoader.load(GreetingService.class)`, do not assume every provider constructor has already run. Only **iterator traversal**, `findFirst()`, or `Provider.get()` requires those instances according to their respective mechanisms.

## 3. What Does Caching Mean for `iterator()`?

The Java 17 Javadoc specifies that providers are located/loaded/instantiated **lazily**. When using `iterator()`:

1. A new iterator **returns the cached provider instances** of that loader first, in the order they were loaded.
2. After the cached portion, the iterator continues to **locate providers that have not yet been traversed**, and instantiates them on demand.
3. Instances created through iterator traversal are **added to the cache**.
4. Another call to `iterator()` on the **same `ServiceLoader`**, when `reload()` has not yet been called, may return **the exact same cached objects**.
5. If `reload()` has been called, the old cache is not replayed by a new traversal of that loader.

```text
ServiceLoader<GreetingService> L
  ├─ iterator #1
  │     ├─ provider A → creates instance A1 → cache
  │     └─ provider B → not yet reached → not yet created
  │
  ├─ iterator #2
  │     ├─ provider A → returns A1 from cache
  │     └─ provider B → when its turn comes, creates B1 → cache
  │
  └─ reload()
        ├─ cache cleared
        └─ new iterator → may create A2, B2 when needed
```

**The cache is not a JVM-wide singleton.** Another `ServiceLoader` object has its own cache. Even on the same class loader and the same service type, calling `ServiceLoader.load(...)` again creates a **new ServiceLoader instance** with its own cache.

**The cache also does not promise thread-safe providers.** If the same cached instance `A1` is handed to two consumers, that object may still have mutable state and must be synchronized according to the implementation's contract.

## 4. `findFirst()` and Instance Reuse

`findFirst()` (Java 9+) is semantically equivalent to “get the first provider via the iterator”. In the case where a service has exactly one provider configured and successfully instantiated:

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

GreetingService first = loader.findFirst().orElseThrow();
GreetingService again = loader.findFirst().orElseThrow();
System.out.println(first == again);
```

This is an **illustrative snippet** that requires importing `java.util.ServiceLoader` and the service interface `GreetingService`. The result is `true` when two lookups find the same cached provider through the iterator of the **same loader**, before a reload.

**Do not confuse caching with selection order:** if there are multiple providers, the “first” provider depends on discovery order across classpath/service files or module ordering. Some orderings in JPMS are **unspecified**. If an application needs to select a provider by priority, design clear metadata/selection rules; do not assume the class name that comes first alphabetically.

`findFirst()` can also return `Optional.empty()` when there is no provider; and it can throw `ServiceConfigurationError` if the configuration/provider is invalid. It does not silently turn every error into empty.

## 5. Lab A — Cache Before Reload, New Object After Reload

We set up exactly **one service and one provider**, so that the output does not depend on the discovery order across multiple JARs. The program creates a `ServiceLoader`, retrieves the provider twice, calls `reload`, and retrieves it again.

File tree:

```text
service-cache-lab/
├── src/
│   ├── api/spi/GreetingService.java
│   ├── provider/impl/FriendlyService.java
│   └── host/demo/CacheDemo.java
├── api-out/       (created by javac)
├── provider-out/  (javac and service descriptor)
└── host-out/      (created by javac)
```

**File `src/api/spi/GreetingService.java`:**

```java
package spi;

public interface GreetingService {
    String hello(String name);
}
```

**File `src/provider/impl/FriendlyService.java`:**

```java
package impl;

import spi.GreetingService;

public final class FriendlyService implements GreetingService {
    private static int constructions;

    public FriendlyService() {
        int number = ++constructions;
        System.out.println("provider ctor #" + number);
    }

    @Override
    public String hello(String name) {
        return "Hello, " + name;
    }
}
```

The static variable `constructions` is for **observation in a single-threaded demo**, not a thread-safe counter for production use. The `hello` method does not write mutable state, so it can be used as a stateless operation in this exercise.

**File `src/host/demo/CacheDemo.java`:**

```java
package demo;

import spi.GreetingService;
import java.util.ServiceLoader;

public final class CacheDemo {
    public static void main(String[] args) {
        ServiceLoader<GreetingService> loader =
                ServiceLoader.load(GreetingService.class);

        GreetingService first =
                loader.findFirst().orElseThrow();
        GreetingService second =
                loader.findFirst().orElseThrow();

        System.out.println("before reload same object=" +
                (first == second));
        System.out.println("first result=" + first.hello("Java"));

        loader.reload();

        GreetingService after =
                loader.findFirst().orElseThrow();
        System.out.println("after reload same object=" +
                (first == after));
        System.out.println("after reload same class=" +
                (first.getClass() == after.getClass()));
        System.out.println("after result=" + after.hello("Java"));
    }
}
```

Compile from the `service-cache-lab` directory using JDK 17+:

```sh
javac --release 17 -d api-out src/api/spi/GreetingService.java
javac --release 17 -cp api-out -d provider-out src/provider/impl/FriendlyService.java
javac --release 17 -cp api-out -d host-out src/host/demo/CacheDemo.java
```

**Creating the service descriptor is required** at `provider-out/META-INF/services/spi.GreetingService`. On **Windows PowerShell**:

```powershell
New-Item -ItemType Directory -Force provider-out\META-INF\services | Out-Null
Set-Content -Path provider-out\META-INF\services\spi.GreetingService -Value "impl.FriendlyService" -Encoding Ascii
```

On **Linux/macOS**:

```sh
mkdir -p provider-out/META-INF/services
printf 'impl.FriendlyService\n' > provider-out/META-INF/services/spi.GreetingService
```

Here the provider and service names contain only ASCII characters, so creating the file in ASCII encoding is also valid UTF-8, satisfying the Javadoc.

Run on **Windows** (classpath separated by `;`):

```powershell
java -cp "host-out;api-out;provider-out" demo.CacheDemo
```

Run on **Linux/macOS** (separated by `:`):

```sh
java -cp "host-out:api-out:provider-out" demo.CacheDemo
```

**Stdout in a new JVM process:**

```text
provider ctor #1
before reload same object=true
first result=Hello, Java
provider ctor #2
after reload same object=false
after reload same class=true
after result=Hello, Java
```

### Exact Explanation of Each Result

- The constructor prints `#1` because the first `findFirst()` forces instantiation of the first provider instance.
- The second `findFirst()` from the **same `ServiceLoader`** receives the cached object; the constructor is not called again.
- `reload()` clears the loader's own provider cache; the next `findFirst()` traverses again and creates a new object, and the constructor prints `#2`.
- `first == after` evaluates to `false` because these are two instances.
- `first.getClass() == after.getClass()` evaluates to `true` because we **did not replace the class loader** and did not redefine the class; we only created a new instance of the **same runtime provider class**.
- `reload()` does not call `close()` on the `first` object. The `first` variable still holds a reference to the old object, and `first.hello(...)` can certainly be called after reload if the application's API/lifecycle permits.

**Takeaway:** reloading the **provider cache** is different from reloading a **class definition**. It does not replace the source JAR, does not update the bytecode of an already loaded class, and does not reset the static field `constructions` to 0.

## 6. Things `reload()` Does Not Do

When calling:

```java
serviceLoader.reload();
```

This is a snippet requiring an already declared `serviceLoader`. The method has the effect of **clearing that `ServiceLoader`'s provider cache** so that subsequent iterator/stream passes perform discovery lazily from the beginning.

It **does not**:

- Force the JVM to **unload** already loaded provider classes.
- Redefine the bytecode of classes already defined in the same defining loader.
- Change the `ClassLoader` object, `ModuleLayer`, or TCCL implicitly.
- Change the `META-INF/services` path if the class loader is not configured to see a new source.
- Call `close()`/`stop()` on provider objects already handed out to the host.
- Interrupt tasks holding old provider instances.
- Guarantee that a new JAR copied over the old one will replace the implementation of an already loaded class.
- Create a safe “atomic switchover” across consumers on multiple threads.
- Make `ServiceLoader` thread-safe.

If the system needs **plugin hot reload**, you must handle **plugin lifecycle, a new class loader, discovery scope, dependency identity, and references**. `reload()` is only one step that can be useful when provider discovery changes in a way that the current class loader can actually see.

### When Is `reload` Still Useful?

For example, if the class loader or module configuration is updated through a supported mechanism and **the discovery source of the same ServiceLoader context** can see a previously undiscovered provider, `reload` forces the next traversal to rescan. However, if the class loader has already loaded `impl.Plugin` from an old JAR version, `reload` **does not turn `impl.Plugin` into a different runtime class**.

## 7. Old Iterators After `reload()`: Must Be Discarded, Do Not Reuse

The Java 17 Javadoc explicitly states: an iterator obtained from `ServiceLoader.iterator()` **before a reload** is no longer usable after the cache is cleared. The `hasNext()` and `next()` methods may throw **`ConcurrentModificationException`** under a fail-fast mechanism.

```text
ServiceLoader L
   │
   ├─ Iterator old = L.iterator()
   │
   ├─ old.hasNext()          → works before reload
   │
   ├─ L.reload()             → provider cache cleared
   │
   ├─ old.hasNext()/next()   → ConcurrentModificationException
   │
   └─ Iterator fresh = L.iterator()
                              → new discovery, from new cache
```

**The name `ConcurrentModificationException` does not necessarily mean two threads are involved.** Even a single thread calling `reload()` and then continuing to use the old iterator can encounter this exception. That is **iterator invalidation**, distinct from a race caused by multiple executing threads.

Do not catch this exception and **continue using the old iterator**. Create a **new iterator** after reloading, and define clear ownership boundaries.

## 8. Lab B — Demonstrating Fail-Fast Iterators After Reload

Keep the service, provider, descriptor, and the `api-out` and `provider-out` directories from Lab A. Add the file **`src/host/demo/IteratorDemo.java`**:

```java
package demo;

import spi.GreetingService;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.ServiceLoader;

public final class IteratorDemo {
    public static void main(String[] args) {
        ServiceLoader<GreetingService> loader =
                ServiceLoader.load(GreetingService.class);

        Iterator<GreetingService> old = loader.iterator();
        System.out.println("old has provider=" + old.hasNext());

        loader.reload();

        try {
            old.hasNext();
            System.out.println("old iterator invalidated=false");
        } catch (ConcurrentModificationException expected) {
            System.out.println("old iterator invalidated=true");
        }

        GreetingService fresh =
                loader.findFirst().orElseThrow();
        System.out.println("fresh result=" + fresh.hello("B"));
    }
}
```

Compile:

```sh
javac --release 17 -cp api-out -d host-out src/host/demo/IteratorDemo.java
```

Run on Windows:

```powershell
java -cp "host-out;api-out;provider-out" demo.IteratorDemo
```

Or Linux/macOS:

```sh
java -cp "host-out:api-out:provider-out" demo.IteratorDemo
```

**Stdout with exactly one provider:**

```text
old has provider=true
old iterator invalidated=true
provider ctor #1
fresh result=Hello, B
```

`old.hasNext()` before the reload determines that a provider exists without **needing to create an instance** of it; the constructor is called later when `findFirst()` retrieves the fresh provider. Because the program runs in **a new JVM**, the static constructor counter starts over and prints `#1`.

**Do not generalize that every `hasNext()` is harmless:** lazy discovery may need to read descriptors and load provider metadata; a `ServiceConfigurationError` can arise in `hasNext()` or `next()` depending on the situation. Simply note that this example does not instantiate the provider via `old.hasNext()`.

## 9. How Do `stream()` and `ServiceLoader.Provider<S>` Differ from the Iterator?

Java 9+ provides:

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

loader.stream()
      .filter(provider -> provider.type().getName()
              .startsWith("impl."))
      .map(ServiceLoader.Provider::get)
      .forEach(service ->
              System.out.println(service.hello("Java")));
```

This is a **snippet**, requiring imports for `ServiceLoader` and `GreetingService`. `stream()` provides **`Provider<S>` descriptors**:

- `provider.type()` returns the provider type so you can inspect metadata/annotations without having to create a service instance yet.
- `provider.get()` returns an instance of the provider; for named modules, a provider factory method may be used.
- `stream()` is also **lazy**: only a terminal operation actually performs traversal.
- `ServiceLoader` has a mechanism to **cache providers discovered by the stream**; the Javadoc describes processing cached providers before locating the remaining ones.
- **Do not infer that calling `Provider.get()` multiple times always returns the same singleton instance.** `Provider.get()` is an API that creates/obtains an instance according to the provider implementation; the Javadoc does not promise cached-instance identity like iterator traversal does.
- For service providers in named modules, `Provider.type()` may reflect the return type of the provider factory method, not necessarily the provider factory class itself.

### The `stream` Cache Should Not Be Equated with the `iterator` Instance Cache

The iterator uses an instance cache for traversing `S`. The stream traverses `Provider<S>` descriptors and obtains an instance only when `Provider.get()` is called. Treat **caching behavior as documented by the Javadoc per API**; do not rely on an internal detail assuming that all provider instances returned via `stream` and `iterator` have a specific identity.

If the goal is **a service object for repeated use**, retrieve the instance exactly once, place it in an application-owned registry, and then manage the concurrency/lifecycle of that registry.

### Old Streams After Reload

The Javadoc also requires **discarding streams obtained before reload**. The stream's underlying `spliterator` has fail-fast behavior if the cache has been cleared and may throw `ConcurrentModificationException`. Do not call `reload()` while a stream pipeline is being consumed or between stream creation and its terminal operation; create a new stream after reloading.

## 10. `ServiceLoader` Is Not Thread-Safe: Understanding the Exact Scope of the Warning

The Java 17 Javadoc explicitly states: **instances of `ServiceLoader` are not safe for use by multiple concurrent threads**.

This warning is about **the `ServiceLoader<S>` object itself**, because it maintains a cache and lazy traversal state that can be mutated when calls interact. Operation pairs to avoid:

- Thread A iterates with `for (S s : loader)` while thread B calls `loader.reload()`.
- Two threads share **a single `ServiceLoader`** and concurrently open/advance two uncoordinated iterators.
- One thread uses `stream()` while another thread mutates the cache via iteration/reload.
- Storing a VM-wide `ServiceLoader` and letting tenants/applications with different TCCLs share access to it.
- Calling `parallel()` directly on a `ServiceLoader` stream to discover providers without considering thread safety.

Even if a run happens not to report an error, that **does not make `ServiceLoader` thread-safe**.

However, there is another boundary: **whether the provider implementation is thread-safe**. Once the host has selected a `GreetingService` instance, whether two threads calling `service.hello(...)` concurrently is safe depends on the **implementation contract**, not on the `ServiceLoader` cache.

Therefore, distinguish:

```text
ServiceLoader object  ── not thread-safe under concurrent access
        │
        ▼
Provider instance    ── may or may not be thread-safe; check the contract
        │
        ▼
Business operation   ── mutable state must be protected if present
```

## 11. Three Reasonable Approaches to Concurrency

### Approach A: Initialize on One Thread, Snapshot, Then Distribute

1. Create and traverse `ServiceLoader` during a **sequential** discovery phase.
2. Store the provider instances or provider factories in a list/registry with clear ownership.
3. Publish a **structurally immutable** snapshot to worker threads.
4. Call a provider instance concurrently only if the provider itself **is designed to be thread-safe**; otherwise, protect it with a lock or create a separate instance per worker.

For stateless services, this is usually the simplest and most effective approach.

### Approach B: Synchronize All Interactions with the Same ServiceLoader

For example:

```java
final Object guard = new Object();
final ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

synchronized (guard) {
    for (GreetingService service : loader) {
        // Put the results into an internal registry.
    }
}
```

This is a **snippet**, not a standalone program. **Every call path invoking `iterator`, `stream`, or `reload` on the same loader must follow the same synchronization policy**. You must not lock only when obtaining the `Iterator` and then release the lock to iterate on another thread — the lazy state continues to be mutated during `hasNext/next`.

Synchronization also **does not automatically protect** provider objects already handed out to consumers; that is a separate concurrency layer.

### Approach C: Create a Separate ServiceLoader per Task

If cache sharing is not needed, tasks can use **separate ServiceLoader instances** with the same service type and an appropriately configured loader. This avoids sharing ServiceLoader state, but may create multiple provider instances and increase discovery overhead. Do not treat providers as thread-safe just because the ServiceLoader is not shared.

**Context-based recommendation:** for applications with long-lived provider lifecycles, it is generally better to perform **discovery once**, build an immutable registry, and manage version replacement through an explicit mechanism rather than calling `ServiceLoader` concurrently on every request.

## 12. Lab C — Sequential Snapshot, Invoking the Provider on Two Worker Threads

Reuse `GreetingService`, `FriendlyService`, and the descriptor from Lab A. New file **`src/host/demo/SnapshotDemo.java`**:

```java
package demo;

import spi.GreetingService;
import java.util.ArrayList;
import java.util.List;
import java.util.ServiceLoader;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class SnapshotDemo {
    public static void main(String[] args) throws Exception {
        ServiceLoader<GreetingService> loader =
                ServiceLoader.load(GreetingService.class);

        List<GreetingService> found = new ArrayList<>();
        for (GreetingService provider : loader) {
            found.add(provider);
        }
        List<GreetingService> snapshot = List.copyOf(found);

        // Run concurrent tasks only after discovery finishes.
        GreetingService service = snapshot.get(0);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> a =
                    pool.submit(() -> service.hello("A"));
            Future<String> b =
                    pool.submit(() -> service.hello("B"));

            System.out.println("job A=" + a.get());
            System.out.println("job B=" + b.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile:

```sh
javac --release 17 -cp api-out -d host-out src/host/demo/SnapshotDemo.java
```

Run on Windows:

```powershell
java -cp "host-out;api-out;provider-out" demo.SnapshotDemo
```

Run on Linux/macOS:

```sh
java -cp "host-out:api-out:provider-out" demo.SnapshotDemo
```

**Stdout:**

```text
provider ctor #1
job A=Hello, A
job B=Hello, B
```

- The provider is instantiated on the **main thread** while traversing `loader`; there is one provider, so only one constructor marker is printed.
- `List.copyOf` creates a structurally immutable list. It **does not automatically make the provider's contents immutable or thread-safe**.
- Both workers call the `hello` method of **the same provider instance**. This exercise is safe because `FriendlyService.hello` does not mutate shared state; the constructor counter is not modified in those calls.
- Both futures are awaited/printed in **A then B order**, so stdout is deterministic even though the two tasks may actually execute in any order.
- `ServiceLoader` **is not called by worker threads**. This is the main point of the snapshot strategy, not incidentally using `synchronized` inside the provider.

If the service is stateful (for example, a mutable counter or using a non-thread-safe parser), you need to design **instance per task, pooling, synchronization**, or a serial executor at the provider layer. Snapshotting only prevents races on provider discovery/cache.

## 13. `reload()` and Concurrency Do Not Create an Atomic Hot-Swap

Suppose the host is running requests through `oldProvider`. An administrator calls `serviceLoader.reload()` and then selects `newProvider`. What happens?

- `reload()` **does not revoke** the `oldProvider` object from threads already holding a reference.
- Threads currently invoking methods on `oldProvider` can still continue using it.
- If the provider owns a socket/file/thread, `reload()` does not call cleanup.
- If consumers directly read a mutable list that is modified concurrently, they may observe inconsistent state.
- If a reload occurs while an old iterator/stream is traversing, `ConcurrentModificationException` or a race outside the thread-safety contract may occur.

One way to design a registry:

```text
  New discovery phase (sequential, separate loader when needed)
           │
           ▼
  Validate all provider candidates
           │
           ▼
  Create a complete new snapshot registry
           │
           ▼
  Publish the new snapshot via an atomic assignment
           │
           ▼
  Stop accepting new requests to the old registry
           │
           ▼
  Wait for/cancel old tasks per the lifecycle contract
           │
           ▼
  Close provider resources and old loader when safe
```

This diagram is an **architectural pattern**, not a guarantee provided by `ServiceLoader`. You can use `AtomicReference<Registry>` or a volatile reference for an immutable registry along with a quiescence/active request tracking protocol. **Atomic publish** solves the visibility of the new reference, whereas completing work on the old provider still requires a lifecycle protocol.

## 14. A New ClassLoader Is Completely Different from `ServiceLoader.reload()`

The following two processes are not equivalent:

**A. Same ClassLoader, calling reload:**

```text
URLClassLoader L1 defines impl.FriendlyService → Class C1
ServiceLoader S1 (using L1)
  → first provider instance P1
  → S1.reload()
  → next provider instance P2

P1 != P2
P1.getClass() == P2.getClass()    (same C1)
```

**B. New ClassLoader, new discovery:**

```text
URLClassLoader L1 defines impl.FriendlyService → Class C1
URLClassLoader L2 defines impl.FriendlyService → Class C2

C1 != C2                        (different defining loader)
```

Case B is commonly used to load **a different plugin version** after replacing the artifact and creating a new loader. However, shared API identity is required: `spi.GreetingService` in the host and in both plugins must resolve to **the same runtime interface Class<?>**, typically via a parent API loader.

One note: if the parent has already defined `impl.FriendlyService` and `URLClassLoader` uses parent-first delegation, both L1 and L2 may return **the same class from the parent** instead of defining C1/C2 themselves. Therefore, an integration test must **not place the provider implementation on the host classpath** when testing per-plugin class loaders.

## 15. Lab D — Two ClassLoaders and Cache Reload Within One Loader

Reuse **the same `provider-out`** from Lab A, but this time **do not put it on the application classpath**. Only the host and the shared API are on the application loader; two child `URLClassLoader` instances are both given a URL pointing to `provider-out`.

File **`src/host/demo/LoaderIdentityDemo.java`**:

```java
package demo;

import spi.GreetingService;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class LoaderIdentityDemo {
    public static void main(String[] args) throws Exception {
        URL location = Path.of("provider-out")
                .toAbsolutePath().toUri().toURL();
        URL[] urls = { location };
        ClassLoader sharedApiLoader =
                GreetingService.class.getClassLoader();

        try (URLClassLoader firstLoader =
                     new URLClassLoader(urls, sharedApiLoader);
             URLClassLoader secondLoader =
                     new URLClassLoader(urls, sharedApiLoader)) {

            ServiceLoader<GreetingService> firstServices =
                    ServiceLoader.load(
                            GreetingService.class, firstLoader);
            ServiceLoader<GreetingService> secondServices =
                    ServiceLoader.load(
                            GreetingService.class, secondLoader);

            GreetingService a =
                    firstServices.findFirst().orElseThrow();
            GreetingService b =
                    secondServices.findFirst().orElseThrow();

            System.out.println("same provider Class across loaders=" +
                    (a.getClass() == b.getClass()));
            System.out.println("a defined by first=" +
                    (a.getClass().getClassLoader() == firstLoader));
            System.out.println("b defined by second=" +
                    (b.getClass().getClassLoader() == secondLoader));
            System.out.println("both implement host API=" +
                    (GreetingService.class.isInstance(a)
                            && GreetingService.class.isInstance(b)));

            firstServices.reload();
            GreetingService a2 =
                    firstServices.findFirst().orElseThrow();

            System.out.println("same object after reload=" +
                    (a == a2));
            System.out.println("same Class after reload=" +
                    (a.getClass() == a2.getClass()));
        }
    }
}
```

Compile (reading the shared API from `api-out`, without needing the provider implementation at compile time):

```sh
javac --release 17 -cp api-out -d host-out src/host/demo/LoaderIdentityDemo.java
```

**Windows:**

```powershell
java -cp "host-out;api-out" demo.LoaderIdentityDemo
```

**Linux/macOS:**

```sh
java -cp "host-out:api-out" demo.LoaderIdentityDemo
```

**Stdout in the configuration described above:**

```text
provider ctor #1
provider ctor #1
same provider Class across loaders=false
a defined by first=true
b defined by second=true
both implement host API=true
provider ctor #2
same object after reload=false
same Class after reload=true
```

**Why does the constructor print `#1` twice?** The static field `constructions` belongs to the runtime class `impl.FriendlyService` defined by **each separate defining loader**. Because the two classes have different class identities, each class starts its static counter from 0. When `firstServices` is reloaded, the class from the first loader **does not change**, so the next constructor invocation of **the first class** prints `#2`.

`ServiceLoader.load(GreetingService.class, firstLoader)` accepts an explicit loader to locate the descriptor/provider, while the provider still delegates the `spi.GreetingService` interface up to the shared parent. Thus host casting/API assignability remains valid.

**Closing loaders:** `try-with-resources` closes `URLClassLoader` resources when the block ends; it does not guarantee that the JVM immediately unloads objects/classes that still have references. In a real application where a provider is serving requests, **do not close the class loader before its lifecycle ends**.

## 16. Provider Ordering and Caching: Do Not Design Around Implicit Ordering

For classpath providers, discovery order typically follows:

- the order in which the class loader's `getResources("META-INF/services/...")` returns service configuration files;
- the order of provider names within each descriptor;
- duplicate provider name handling as specified by the Javadoc.

For named modules, `ServiceLoader` follows its own module/layer rules, and certain orderings are **unspecified**. Therefore, do not assume `findFirst()` always chooses the “best provider” or that all modules are traversed by name.

If the application has multiple providers and requires prioritization:

1. Each provider declares its capability/priority under an **explicit contract**.
2. Discover all candidates sequentially.
3. Validate type/capability.
4. Sort/select according to the application's criteria, handling cases of equal priority.
5. Cache the selected instance/registry after the decision has been made.

Do not let the incidental ordering of JAR files decide which provider handles sensitive transactions.

## 17. `ServiceConfigurationError` During Lazy Loading

Because ServiceLoader is **lazy**, errors do not necessarily occur immediately when calling `ServiceLoader.load(...)`. The Javadoc explicitly notes:

- `Iterator.hasNext()` and `next()` may throw `ServiceConfigurationError` when reading descriptors, loading providers, or creating instances.
- Stream operations may throw errors at **the time of actual traversal**, and `Provider.get()` may fail when creating the provider.
- `findFirst()` can also report an error when the first provider is invalid.
- If the provider-configuration file is malformed, the class name does not exist, the provider is not assignable to the expected service type, or the constructor/factory fails, the error may carry a related cause.

Some common errors:

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| No provider found, `findFirst()` empty | Descriptor/module declaration is not visible to the runtime loader | Check `META-INF/services`, JAR entries, TCCL/explicit loader, JPMS |
| `ServiceConfigurationError: Provider ... not found` | Provider class is not present in the classpath/module scope | Check binary name, JAR, loader URL/delegation |
| Provider not a subtype | Host and plugin use two runtime copies of the service API, or the provider declaration is incorrect | Compare `Class<?>`, defining loader, shared API graph |
| Constructor/factory error | Provider init/constructor method throws an exception or configuration is invalid | Inspect cause, log provider identity, fix lifecycle |
| Iterator `ConcurrentModificationException` after reload | Reusing an invalidated old iterator | Discard the old iterator, create a new iterator after reload |
| Erratic concurrent iteration/reload | A single `ServiceLoader` is accessed from multiple threads | Serialize discovery/reload or snapshot/ownership |
| Provider “unchanged” despite updating JAR | ClassLoader already defined the old class; reload only clears the provider cache | Implement loader/version lifecycle; do not call reload as a redefine |
| Memory leak when reloading plugins repeatedly | Host retains provider instance, registry, ServiceLoader, ClassLoader, TCCL, or threads | Unregister callbacks, stop tasks, close resources, release references |

### Do Not Blindly Swallow Configuration Errors

Do not do this:

```java
try {
    return loader.findFirst().orElse(null);
} catch (Throwable ignored) {
    return null;
}
```

This is an **incorrect pattern**, not a standalone method; it swallows even class linking/JVM errors and equates “no provider” with “provider broken”. `ServiceConfigurationError` is an `Error` indicating a serious runtime configuration issue. If an application wants optional plugins, it can catch that error specifically at the **plugin management** layer, preserving context/cause and applying a defined fail-fast or skip-provider policy; do not assume that continuing the iterator after an error will always recover cleanly.

## 18. TCCL, Explicit Loaders, and Cross-Application Cache Limitations

`ServiceLoader.load(ServiceType.class)` uses the **thread context class loader (TCCL)** at the time the ServiceLoader is created:

```java
ServiceLoader<GreetingService> viaContext =
        ServiceLoader.load(GreetingService.class);

ServiceLoader<GreetingService> explicit =
        ServiceLoader.load(GreetingService.class, pluginLoader);
```

These are **snippets**, requiring a declared `pluginLoader` variable and interface. In a container, two threads may have different TCCLs and see different providers.

The Javadoc notes that **`ServiceLoader.load(service)` should not be cached VM-wide** in a multi-application environment: that object retains the **discovery context** bound to the TCCL at creation time, its provider caches may be inappropriate for another application, and it risks keeping a class loader alive.

**Do not mistake TCCL for the defining loader.** TCCL selects the discovery context; which loader actually defines the provider class depends on delegation, the module graph, and URL sources. If the host passes a service interface `Class<?>` defined by the host, the plugin loader must still resolve to the exact shared API identity.

Related APIs:

- `ServiceLoader.load(Class<S> service)`: uses the TCCL.
- `ServiceLoader.load(Class<S> service, ClassLoader loader)`: selects an explicit loader.
- `ServiceLoader.load(ModuleLayer layer, Class<S> service)`: discovers named-module providers in the layer/ancestors; it **does not** pick up unnamed-module classpath providers like the class loader overloads do.
- `ServiceLoader.loadInstalled(service)`: uses the platform loader; it is not a replacement for loading plugins on the application classpath.

**Do not use `reload()` to “switch the TCCL” of an already created ServiceLoader.** If the loader/layer context needs to change, create a **new ServiceLoader** with the new context.

## 19. Provider Lifecycle Is Not Managed by ServiceLoader on Your Behalf

A provider may be just a pure function, or it may hold resources:

```java
public final class ConnectionProvider
        implements SomeService, AutoCloseable {
    // May own a connection, executor, or subscription.

    @Override
    public void close() {
        // Release resources according to the application contract.
    }
}
```

This is **illustrative code**, requiring the `SomeService` interface and concrete implementation methods if you want to compile it into a program; it is not a standalone runnable example.

`ServiceLoader.reload()` **does not automatically call `close()`** on providers already returned to the host. If the caller keeps references, the object can remain alive.

A registry with a proper lifecycle should:

- Have a `start/stop/close` interface or its own lifecycle adapter.
- Prevent creating new requests on a replaced provider.
- Wait for in-flight requests to complete, or cancel them in a controlled manner.
- Unregister listeners/callbacks, stop background tasks, and clean up `ThreadLocal`/TCCL if the framework modified them.
- Close the provider's files/sockets/resources; only afterward close the `URLClassLoader` if the loader is owned by the registry.
- Drop references to old instances/`Class<?>`/`Method`/`Provider<?>`/ServiceLoader/streams when you want to allow class unloading.

**GC/class unloading is not immediate:** even after `URLClassLoader.close()`, a single strong reference from the host registry or a thread can keep the plugin loader and all of its classes alive.

## 20. Caching Costs and Architectural Choices

Caching has benefits:

- Avoids re-instantiating provider instances on every iterator pass.
- Avoids repeated discovery/constructor calls when the registry needs to use the service multiple times.
- Keeps provider object identity/state stable within a `ServiceLoader` before a reload.

However, caching has trade-offs:

- **Shared provider state**: if a provider is mutable, callers sharing a cached instance may interfere with one another.
- **Extended lifetime**: `ServiceLoader` may keep provider instances and classes alive longer than expected.
- **Changes are not automatically detected**: adding a JAR/module, changing config, or updating an implementation version requires an explicit discovery plan.
- **Concurrency risk** if multiple threads traverse the cache and reload simultaneously.
- **Version management difficulty** if a single ServiceLoader object is kept JVM-wide while tenants have different TCCLs.

If you only need **a provider selected once at startup**, storing an immutable registry of validated providers is usually simpler. If you need to **replace providers at runtime**, design a version/generation-based registry and class loader ownership, rather than just calling `reload()`.

### Whose Decision Is a “Singleton Provider”?

`ServiceLoader` helps cache instances along the iterator path, but **it is not a container that manages program-wide singletons**. A provider constructor can create a second instance when:

- using a different `ServiceLoader` object;
- calling `reload()` and then iterating again;
- using a provider factory that creates instances according to its own contract;
- another class loader defines the provider type;
- the application calls the constructor/factory directly outside ServiceLoader.

If a service must be a singleton per business rules, design that invariant/lifecycle at the provider/container layer; do not infer it solely from caching behavior.

## 21. Safe Implementation Checklist

Before using `ServiceLoader` in a host/plugin framework:

1. **Choose service API identity**: the interface must be the same `Class<?>` in both the host and the provider.
2. **Choose the discovery context**: explicit `ClassLoader`, TCCL, or `ModuleLayer`; do not mix them without a reason.
3. **Package descriptors properly**: `META-INF/services/<service binary name>` for classpath, `uses`/`provides` for named modules.
4. **Know lazy semantics**: `load` does not necessarily create providers yet; iterator/stream/findFirst perform discovery when traversed.
5. **Know caching semantics**: iterator emits cached instances first; `stream` supplies descriptors; do not assume `Provider.get()` is a singleton.
6. **Define rules for `reload`**: clear the cache, discard old iterators/streams, and do not use concurrently.
7. **Do not share a `ServiceLoader` without synchronization** across threads. If throughput is needed, snapshot providers after sequential discovery.
8. **Verify provider thread safety** independently; stateful services need synchronization/factory/instance-per-call.
9. **Verify provider configuration errors** with context/cause; do not swallow errors.
10. **Do not confuse cache reload with class reload**; select a new class loader when you need to load different definitions.
11. **Publish the registry atomically with a lifecycle** if hot-swapping, ensuring old consumers finish.
12. **Clean up references and close resources** of providers/URLClassLoaders at the right time.
13. **Test with proper runtime packaging**; an IDE classpath can easily mask missing descriptors/duplicate APIs.
14. **Test concurrency**: overlapping iterate/reload calls must be prevented by design; concurrent use of service objects must be verified separately.

## 22. Self-Check Questions with Answers

**1. Does `ServiceLoader.load(S.class)` immediately create all provider instances?** No. Provider discovery and instantiation are lazy; iterator/stream/findFirst perform the work on demand.

**2. Can two calls to `findFirst()` on the same ServiceLoader before a reload return the same object?** Yes. When a provider is created/cached via the iterator, the next call receives the cached instance again.

**3. What does `reload()` clear?** The provider caches of that ServiceLoader instance so that a new traversal rediscovers them.

**4. Does `reload()` change the bytecode of an already loaded class?** No. It does not redefine or unload the runtime class.

**5. Why does example A print `provider ctor #2` after reload yet `same class=true`?** A new object is created from the same `Class<?>` of the same defining loader, so the static construction counter continues to increment.

**6. Can an old iterator be used after `reload()`?** No. The Javadoc requires discarding it; `hasNext/next` may throw `ConcurrentModificationException`.

**7. Does `ConcurrentModificationException` after reload prove two threads ran concurrently?** No. A single thread can also invalidate an old iterator with `reload`.

**8. Does `stream()` directly return service instances?** No. It returns `Stream<ServiceLoader.Provider<S>>`; call `Provider.get()` to obtain an instance.

**9. Can you call `Provider.get()` repeatedly and be certain of getting the same object?** No. The API does not promise singleton identity like that.

**10. Is a `ServiceLoader` thread-safe?** No. The Java 17 Javadoc explicitly warns that instances are not safe for multiple concurrent threads.

**11. After snapshotting providers, is every provider automatically thread-safe?** No; provider thread safety is a separate contract of the implementation.

**12. Why should `ServiceLoader.load(service)` not be cached VM-wide in a container?** Because this overload uses the TCCL; applications have different discovery contexts and caching it can keep class loaders/providers alive.

**13. A plugin updates its JAR, yet `reload()` still runs the old code: why?** The ClassLoader may have already defined the runtime class from the old bytes; reload only changes the provider cache.

**14. If two separate URLClassLoaders define a provider with the same binary name, is the static counter shared?** No. Two runtime class identities have separate static states.

**15. The host interface has the same name as the plugin's copy, yet casting fails; what could be the cause?** The shared API was defined twice by different defining loaders; delegation to the right API class is needed.

**16. Does `ServiceLoader.reload()` call `AutoCloseable.close()` on old provider objects?** No. The application must manage their lifecycle itself.

**17. When should you create a new ServiceLoader instead of reloading the old one?** When you need to change the discovery loader/TCCL/layer, build a generation-based registry, or do not want to share caches.

**18. Can errors about a provider class in a service-configuration file be ignored?** They should not be. You must distinguish “no provider” from a `ServiceConfigurationError` caused by a configuration, class loading, or instantiation failure.

## 23. Authoritative Reference Documentation

- [Java SE 17 — `ServiceLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider discovery, caching, `iterator`, `stream`, `findFirst`, `reload`, concurrency, TCCL, and module layers.
- [Java SE 17 — `ServiceLoader.Provider` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html): `type()`, `get()`, and provider descriptors.
- [Java SE 17 — `ClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, runtime class visibility, and resource lookup.
- [Java SE 17 — `URLClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): plugin class loaders from URLs, `close()`, and lookup scope.
- [Java SE 17 — `ModuleLayer` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): named module layers when deploying providers.
- [Java Virtual Machine Specification, Java SE 17 — Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): defining loader, class identity, loading/linking, and class lifecycle.

**Conclusion:** `ServiceLoader` **caches providers for lazy discovery/iteration**, and `reload()` **clears the cache and invalidates old iterators/streams**, but **does not reload the bytecode of provider classes**. A single `ServiceLoader` **is not safe for concurrent use**; discover providers in a controlled phase, build a registry/snapshot, evaluate each provider's thread safety, and manage hot-swapping with proper lifecycle and class loader ownership.
