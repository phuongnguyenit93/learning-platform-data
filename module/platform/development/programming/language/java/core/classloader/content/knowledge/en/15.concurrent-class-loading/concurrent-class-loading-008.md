# Designing a Thread-Safe Bytecode and Resource Cache in Java ClassLoader

When multiple threads concurrently request to load classes or resources from JARs, directories, memory, or remote sources, a custom `ClassLoader` must solve **two concurrent yet distinct problems**:

1. **Safe runtime class definition:** a defining loader cannot define the same binary class name twice. Competing threads must receive **the same `Class<?>`**, rather than calling `defineClass` concurrently.
2. **Efficient bytecode/resource lookup and reading:** multiple threads may need the same `.class` data, images, templates, or configuration. The cache must ensure no incomplete data is leaked, avoid redundant reads, manage errors, and preserve the correct source version/generation.

The key distinction: **caching `byte[]` is not caching `Class<?>`**. The JVM/ClassLoader already tracks loaded class state per defining/initiating loader; a byte cache only stores **raw material for definition**, whereas a resource cache typically stores **immutable data** or source metadata. You must never take a `Class<?>` defined by loader A and "reuse it as a class of loader B".

This article explains the concurrency contract of `ClassLoader`, how to choose cache keys, safe publication, single-flight, read-through, invalidation, failure/retry, resource streams, performance, class unloading, and a runnable Java 17+ example.

## 1. Three Memory Layers That Should Not Be Merged

~~~text
                   Multiple application threads
                       |              |
                 loadClass(...)    readResource(...)
                       |              |
                       v              v
                  ClassLoader      Resource service
                       |              |
            findLoadedClass(name)   Cache data/metadata
                       |              |
             find .class bytecode   find bytes/resource
                       |              |
              defineClass(...)       InputStream per caller
                       |
                       v
                    Class<?>
                       |
                 JVM type identity
            (binary name, defining loader)
~~~

| Layer | Stored Entity | Purpose | Notes |
|---|---|---|---|
| JVM/class-loading state | Loaded/defined class information | Prevent redefining a type in the same loader, support type linkage | `findLoadedClass` relates to the initiating loader; follow proper delegation rules |
| Bytecode source cache | `byte[]` or bytecode read results | Reduce redundant source I/O/transformation/verification | Must be tied to source version/loader generation |
| Resource cache | Bytes, parsed content, metadata, or lifecycle-managed handles | Avoid redundant resource reads | Never share a single `InputStream` being consumed |
| External cache (optional) | JAR index, HTTP artifact, disk cache | Reduce remote read overhead | Requires integrity, expiration, and version policy |

**Common mistake:** using `ConcurrentHashMap<String, Class<?>>` as a global store across all loaders. Keying only by class name is insufficient, because **type identity = (binary name, defining class loader)**. Furthermore, holding strong references to `Class<?>` can accidentally keep old loaders alive.

## 2. Avoiding Duplicate Class Definition Even With Cached Bytes
Caching `byte[]` only stores source data; it **has no authority to replace** the class state recorded by the JVM. With the default `loadClass`, the same name is protected by `getClassLoadingLock(name)`, and `findLoadedClass` checks whether the class is already loaded before `findClass` gets a chance to call `defineClass`. Therefore, two threads that both successfully load `plugin.Task` will receive the same `Class<?>`, regardless of whether the byte cache performed one or multiple reads.
Do not call `findClass` directly from multiple threads to "use the cache"; that method does not replace the synchronization of `loadClass`. The article **Avoiding Race Conditions Between findLoadedClass and defineClass** demonstrates this race using a barrier.

## 3. Parallel Loading and Caching Are Two Separate Layers
A subclass registered as **parallel-capable** from its static initializer allows the default `loadClass` to lock per binary name instead of the entire loader. This only gives **different names** the opportunity to proceed concurrently; it does not make `ConcurrentHashMap`, `FutureTask`, streams, or resource services thread-safe automatically. Inside `findClass`, keep buffers local and synchronize shared state properly.
If you only change the byte source and keep parent-first delegation, **override only `findClass`**. When you must override `loadClass`, check for an already loaded class under the same lock before defining; see the previous locking and race articles.

## 4. Cache Keys Must Describe Source and Version

For a **private cache of an immutable loader instance**, a class name may suffice as the key:

~~~text
class cache key = "plugin.impl.Task"
resource key    = "plugin/config.txt"
~~~

However, for a **cache shared across multiple loaders or multiple plugin generations**, the key must include additional fields:

~~~text
CacheKey = (
    artifact/source identity,
    artifact version or content hash,
    relative path / binary name,
    transformation pipeline version,
    possibly runtime target version
)
~~~

Why?

- Two plugins may contain `plugin.impl.Task` with the same name but different bytecode.
- The same JAR path can be overwritten from v1 to v2; **a path does not prove content immutability**.
- A class transformer/instrumentation may alter bytes differently depending on configuration.
- A multi-release JAR may serve different bytes depending on the runtime version.
- Resources across plugins may share the path `config.properties` but have different contents.
- If a source file changes between two reads, the cache must not silently produce classes and resources from two different versions.

For a local cache of a loader tied to an immutable deployment, the simplest approach is usually to **create a new loader per plugin generation**, rather than hot-swapping bytes of already-defined classes inside an old loader.

## 5. Safe Publication and Immutability of Cached Data

A `ConcurrentHashMap` makes concurrent map access safe across threads, but **does not automatically make mutable values immutable**:

~~~java
ConcurrentHashMap<String, byte[]> cache = new ConcurrentHashMap<>();
~~~

A `byte[]` can be modified by other code after being stored. If one thread mutates the contents while another thread calls `defineClass` or reads a resource, the runtime may encounter corrupted bytecode or inconsistent data.

Rules:

1. When receiving `byte[]` from an external source, create a **snapshot** before publishing if external code might still mutate the array.
2. Never return a mutable `byte[]` directly from a public cache API to untrusted callers.
3. If a resource must be provided as a stream, create **a separate `ByteArrayInputStream` per caller** from an immutable snapshot, instead of caching/handing out the same `InputStream` to multiple threads.
4. Keep metadata bound to the snapshot, such as source URI, content hash, and generation; never update fields piecemeal such that a reader sees "metadata v2 + bytes v1".
5. Use immutable objects (e.g., a record holding a copy of bytes/metadata) or cache entries that are never mutated after publication.

### Why Not Cache a Shared `InputStream`?

An `InputStream` maintains read position state. Two threads reading from the same stream will contend over the cursor and may receive incomplete, duplicated, or interleaved data. One thread closing the stream will also cause the other thread to fail.

**Cache the bytes or source information instead**, then issue a new stream:

~~~java
byte[] bytes = immutableCachedBytes;
try (InputStream in = new ByteArrayInputStream(bytes)) {
    // Each caller has its own read stream position.
}
~~~

This is an illustrative snippet; ensure `bytes` is genuinely free from external mutation throughout the lifetime of the stream.

## 6. Single-Flight: Many Requests, One Source Load

There are three common caching strategies:

| Approach | Prevents duplicate I/O on cache miss? | Notes |
|---|---|---|
| Plain `HashMap`, unlocked | No; also has data races | Do not share across threads |
| `ConcurrentHashMap.get` then `putIfAbsent` after I/O | **Not guaranteed**: two threads may both perform I/O before one wins `putIfAbsent` | Safe publication is possible, but duplicate work occurs |
| `ConcurrentHashMap.computeIfAbsent` with I/O in mapping function | Atomic per key, can prevent duplicate computation | Mapping function must be short and not update the map; long I/O causes blocking |
| `ConcurrentHashMap<Key, FutureTask<byte[]>>` and `putIfAbsent` before running task | Yes: multiple callers wait on the same future | Controls failure/retry and avoids running I/O under the CHM mapping lock |
| `CompletableFuture` placeholder + producer | Yes if put-if-absent is used before the producer loads | Must handle complete/completeExceptionally, timeout/cancel/lifecycle |

### Why Avoid Arbitrary Network I/O Inside `computeIfAbsent`?

According to JDK 17 `ConcurrentHashMap.computeIfAbsent`, the mapping computation runs atomically; some other updates may be blocked while computation is in progress, so the mapping function should be **short and simple**. The mapping function must not modify the map itself while running; recursive updates may throw `IllegalStateException`.

Example to avoid for heavy network I/O:

~~~java
byte[] b = cache.computeIfAbsent(key, k -> {
    // Not recommended: long HTTP/disk I/O inside mapping function.
    return slowRemoteDownload(k);
});
~~~

This is **illustrative pseudocode** with custom `cache`, `key`, and `slowRemoteDownload`, not a standalone program. Beyond blocking, checked exceptions from the source must also be converted and managed carefully.

**A cleaner alternative:** map from key to `FutureTask<byte[]>`. The thread that wins `putIfAbsent` performs the I/O outside the map update operation, while remaining threads wait on the same task. If the task fails, remove the exact `(key, future)` pair to avoid permanently caching transient failures.

## 7. Complete Java 17+ Example: Multi-Threaded Bytecode and Resource Cache

The program below uses:

- A loader directly extending `ClassLoader` and registered as `parallel-capable`.
- A `findClass` method that reads `plugin/Task.class` through a **single-flight** cache.
- A separate `openResource` API that reads `plugin/config.txt` through a similar cache, returning a new stream for each caller.
- `ConcurrentHashMap<String, FutureTask<byte[]>>` to share a single read per key.
- `Executors.newFixedThreadPool(8)` for **24 tasks**, all requesting the same `plugin.Task` and the same resource.
- Counters for **successful source reads**, rather than API call counts.

The goal is to prove that **all threads receive the same runtime class, complete resource data, and only one class file read + one resource file read occur** on a successful cache miss.

### 7.1. Directory Structure

~~~text
project/
  src/
    plugin/Task.java
    host/CacheDemo.java
  plugin-out/
    plugin/
      Task.class
      config.txt
  host-out/
    CacheDemo.class
    CacheDemo$DirectoryLoader.class
~~~

The two output directories are generated by `javac`. The plugin class **must not be added to the application classpath** when running the host.

### 7.2. File `src/plugin/Task.java`

~~~java
package plugin;

public final class Task {
    public String message() {
        return "task-ok";
    }
}
~~~

### 7.3. File `src/host/CacheDemo.java`

~~~java
import java.io.ByteArrayInputStream;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class CacheDemo {

    static final class DirectoryLoader extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "Cannot register parallel class loader");
            }
        }

        private final Path root;
        private final ConcurrentHashMap<String, FutureTask<byte[]>> flights =
                new ConcurrentHashMap<>();

        private final AtomicInteger classReads = new AtomicInteger();
        private final AtomicInteger resourceReads = new AtomicInteger();

        DirectoryLoader(Path root) {
            super(ClassLoader.getPlatformClassLoader());
            this.root = root.toAbsolutePath().normalize();
        }

        private byte[] loadOnce(String key, String relativePath,
                                AtomicInteger successfulReads)
                throws IOException {

            Path source = root.resolve(relativePath).normalize();
            if (!source.startsWith(root)) {
                throw new IOException("Outside configured directory");
            }

            FutureTask<byte[]> future = flights.get(key);

            if (future == null) {
                FutureTask<byte[]> candidate = new FutureTask<>(() -> {
                    byte[] data = Files.readAllBytes(source);
                    successfulReads.incrementAndGet();
                    return data;
                });

                FutureTask<byte[]> previous =
                        flights.putIfAbsent(key, candidate);

                if (previous == null) {
                    future = candidate;
                    candidate.run();
                } else {
                    future = previous;
                }
            }

            try {
                return future.get();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IOException("Interrupted waiting for " + key, ex);
            } catch (ExecutionException ex) {
                flights.remove(key, future);
                throw new IOException("Failed loading " + key, ex.getCause());
            }
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!"plugin.Task".equals(name)) {
                throw new ClassNotFoundException(name);
            }

            try {
                byte[] bytes = loadOnce(
                        "class:plugin.Task",
                        "plugin/Task.class",
                        classReads);

                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }

        // Separate resource API: does not pretend to replace ClassLoader.getResource.
        InputStream openResource(String name) throws IOException {
            if (!"plugin/config.txt".equals(name)) {
                throw new FileNotFoundException(name);
            }

            byte[] data = loadOnce(
                    "resource:" + name, name, resourceReads);

            // Each caller has its own read stream position.
            return new ByteArrayInputStream(data);
        }

        int classReads() {
            return classReads.get();
        }

        int resourceReads() {
            return resourceReads.get();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: CacheDemo <plugin-directory>");
        }

        DirectoryLoader loader =
                new DirectoryLoader(Path.of(args[0]));

        ExecutorService workers = Executors.newFixedThreadPool(8);
        CountDownLatch ready = new CountDownLatch(8);
        CountDownLatch go = new CountDownLatch(1);
        List<Future<Class<?>>> results = new ArrayList<>();

        try {
            for (int i = 0; i < 24; i++) {
                Callable<Class<?>> action = () -> {
                    ready.countDown();
                    go.await();

                    Class<?> type = loader.loadClass("plugin.Task");

                    try (InputStream stream =
                            loader.openResource("plugin/config.txt")) {
                        String content = new String(
                                stream.readAllBytes(),
                                StandardCharsets.UTF_8).strip();

                        if (!"config-ok".equals(content)) {
                            throw new IllegalStateException(
                                    "Unexpected resource: " + content);
                        }
                    }

                    return type;
                };

                results.add(workers.submit(action));
            }

            // Wait for all 8 worker threads to start, then open the gate together.
            ready.await();
            go.countDown();

            Class<?> first = results.get(0).get();
            boolean sameClass = true;

            for (Future<Class<?>> result : results) {
                if (result.get() != first) {
                    sameClass = false;
                }
            }

            System.out.println("parallel capable: "
                    + loader.isRegisteredAsParallelCapable());
            System.out.println("same runtime class: " + sameClass);
            System.out.println("defined by custom loader: "
                    + (first.getClassLoader() == loader));
            System.out.println("successful class reads: "
                    + loader.classReads());
            System.out.println("successful resource reads: "
                    + loader.resourceReads());
            System.out.println("tasks completed: " + results.size());
        } finally {
            go.countDown(); // Do not leave tasks waiting at the gate if main fails.
            workers.shutdown();
            if (!workers.awaitTermination(10, TimeUnit.SECONDS)) {
                workers.shutdownNow();
            }
        }
    }
}
~~~

### 7.4. Compiling and Running

Bash commands, executed inside the `project` directory:

~~~bash
mkdir -p plugin-out/plugin host-out

javac -d plugin-out src/plugin/Task.java

printf 'config-ok\n' > plugin-out/plugin/config.txt

javac -d host-out src/host/CacheDemo.java

java -cp host-out CacheDemo plugin-out
~~~

**Note:** the run command puts only `host-out` on the application classpath. `plugin-out` is the data/bytecode directory that the custom loader searches; do not add it to `-cp`, otherwise the example no longer isolates host and plugin loading.

**Expected stdout when all files are present and all tasks complete successfully:**

~~~text
parallel capable: true
same runtime class: true
defined by custom loader: true
successful class reads: 1
successful resource reads: 1
tasks completed: 24
~~~

This is the intended result of fixed cache keys, unchanged source files, single-flight, and class loader locking. Task completion order inside the thread pool is non-deterministic, but the program **does not print per-thread logs**, so the lines above still follow `main`'s print order.

### 7.5. Why Is It Correct Despite 24 Concurrent Tasks?

- `registerAsParallelCapable` succeeds when the loader class is initialized, because it directly extends `ClassLoader`, which is already parallel-capable.
- Calls to `loadClass("plugin.Task")` on the same loader use the class-loading lock for the name `plugin.Task`; one successful `findClass` calls `defineClass`, and subsequent calls use the already-loaded class.
- `loadOnce` uses `putIfAbsent` to publish a `FutureTask` per key **before** reading the file; only one thread executes the task on a cache miss.
- Other threads call `future.get()` to wait; completion of the `FutureTask` safely publishes the data to all receiving threads.
- `resourceReads == 1` because every call opening `plugin/config.txt` uses the same key `resource:plugin/config.txt`.
- Each call to `openResource` returns a **new `ByteArrayInputStream`**; tasks never contend over a shared stream cursor.
- All 24 results are the exact same `Class<?>` defined by the custom loader. No thread calls `defineClass` outside the locked `loadClass` path.

**Explicit example limitation:** the loader intentionally loads only **one known binary class name** and allows reading **one known resource name**. Using a whitelist avoids introducing arbitrary bytecode paths into the demo. This is a concurrency/caching learning pattern, not a general-purpose production loader supporting package sealing, code signing, arbitrary source formats, or sandboxing.

### 7.6. Testing I/O Errors and Retries

If `plugin/config.txt` is missing, `Files.readAllBytes` causes the `FutureTask` to fail. `ExecutionException` is wrapped into `IOException`, and the failed mapping is removed via `flights.remove(key, future)`.

Effects:

- Transient failures are **not cached permanently**.
- Subsequent requests have a chance to retry if the file appears.
- `remove(key, future)` does not accidentally delete a newer future added later.
- Multiple requests waiting on the same failed future may receive the same error; once the future is removed, a new request can initiate **a new load attempt**. Therefore, you should not claim "at most one I/O over the loader's lifetime" **when errors and retries occur**.
- A production system should apply backoff/jitter and distinguish permanent errors (invalid file, disallowed name) from transient errors (I/O, timeout).

### 7.7. Why Not Call `defineClass` Inside the FutureTask?

The cache future in the example only manages **bytes read from the source**. `defineClass` is called in `findClass` and executed under the coordination of `loadClass`. Putting `defineClass` inside a task shared across loaders or outside the class-loading lock easily conflates bytecode caching with type definition and leads to duplicate definitions.

In particular, **do not cache `Class<?>` globally** and return it from another loader based solely on binary name. The JVM requires class identity and loading constraints to be handled properly according to the loader hierarchy.

## 8. The Bytecode Cache Does Not Need to Live Forever

The example keeps `FutureTask<byte[]>` in `flights` for the entire lifetime of the loader. This works for a small demo, but can be wasteful in systems with many classes:

- Once the JVM has defined a class, it is usually **unnecessary to keep bytecode `byte[]` forever** in the loader's cache just to serve future `loadClass` calls; `findLoadedClass` and the JVM already hold the runtime class state.
- If transformation/verification needs bytes for auditing or multiple source loaders reuse an artifact, caching helps, provided there is a memory budget.
- Use a **bounded cache**, LRU/weight-based policy, or explicit eviction for large source bytes/resources.
- If a `reload` feature is required, **replacing bytes in the cache does not change already-defined classes**. A new plugin generation typically requires a **new loader instance**.
- For a cache shared across multiple loaders, keys must include source version/content hash. Never mix v1/v2 bytes for the same class path.
- Snapshot an immutable artifact per generation instead of reading individual files from a deployment being overwritten in place.

A strategy often better than unbounded byte caching is **caching the index and immutable artifact metadata**, letting each loader hold its own runtime state; large payloads can be shared in a controlled manner by content hash and evicted when unused.

## 9. Resource Cache: `byte[]` or Parsed Object?

| Cache Form | Suitable When | Risks |
|---|---|---|
| `byte[]` snapshot | Small resources, repeated reads, independent streams needed | Heap growth; must prevent mutation and bound size |
| Immutable parsed config | Structured data, read concurrently by many threads | Parser/representation must be thread-safe and immutable |
| URI/Path + metadata | Large files, infrequent reads, want to avoid holding bytes | Each caller still performs I/O; races if source changes |
| Open `InputStream` | **Should never be shared across threads** | Shared read cursor, close races, handle leaks |
| Mmap/FileChannel (specialized) | Large files, controlled random access by design | Mapping/channel lifetime, OS resources, bounds/cleanup |
| Cached future of bytes | Many concurrent misses on the same key | Must handle failure, cancellation, invalidation, and wait cycles |

For large resources, `readAllBytes()` can be memory-intensive. Use per-request streaming or enforce byte limits; do not cache all data simply because multiple threads exist.

### Concurrent Readers/Writers When Configuration Changes

If you need to reload a resource while it is being read, avoid mutating **`byte[]` in place**:

~~~text
generation 1 -> immutable snapshot v1
generation 2 -> immutable snapshot v2

Reader A gets v1 and reads consistently until completion.
Reader B starts after the new publish and gets v2.
~~~

You can use an immutable snapshot object swapped atomically via `AtomicReference<Snapshot>` or a versioned map. For multiple resources that must update consistently together, swap **the entire snapshot/generation** in a single step, rather than invalidating individual keys without a protocol.

**Do not apply the same rule to "reload" already-defined classes.** The JVM does not change class identity merely because source bytes change; you need a different mechanism such as a new loader generation or instrumentation/redefinition with its own constraints.

## 10. Watch Out for Interactions Between Locks, Futures, and I/O

### Lock Ordering

Per-class load locks prevent duplicate definitions by name, but if `findClass(A)` holds lock A and waits on another operation requiring lock B, while another thread holds lock B and waits on lock A, a deadlock can occur.

~~~text
Thread 1: lock A -> waits on B
Thread 2: lock B -> waits on A
=> cyclic wait
~~~

Parallel-capable **reduces** whole-loader blocking, but does not automatically eliminate all deadlocks if the delegation graph, transformation, cache callbacks, or plugin initialization create cyclic wait dependencies.

Keep lock durations short, prefer simple hierarchical delegation, avoid callbacks that trigger loading other classes while processing a cache key, and avoid unnecessary global synchronization.

### `FutureTask` and Self-Wait

In the example, the producer only calls `Files.readAllBytes` for a fixed path; it does not recursively call `loadOnce` for the very key currently executing. In complex systems, if producer code calls `future.get()` on its own future, the thread will **wait on itself indefinitely**. Therefore, forbid recursive loads of the same key or detect cycles when resolving remote dependencies.

### Interruption and Cancellation

An interrupted waiter should:

- Restore the interrupt flag via `Thread.currentThread().interrupt()`.
- Report the error according to the caller contract.
- **Not arbitrarily cancel a shared future**, because other callers may still be waiting on it.

Timeouts can be useful for remote I/O, but should only be applied at the layer that actually controls network reads/cancellation. Calling `Future.get(timeout)` in a waiter does not mean the producer has stopped running.

### Races When Closing Sources

Do not close a `URLClassLoader` or file/resource provider while another thread is loading classes. The `URLClassLoader.close()` Javadoc states that if another thread is loading when `close` is called, the result of that load is **undefined**.

A plugin runtime can use lifecycle states:

~~~text
ACTIVE -> DRAINING -> CLOSED

ACTIVE: accept new requests
DRAINING: stop accepting new ones, wait for in-flight operations to finish
CLOSED: close loader, streams, and underlying sources
~~~

For caches with background executors or remote downloads, stop producers, cancel unused tasks per contract, and never publish data from a closed generation into a new loader.

## 11. Caching Negative Results and Retry Pitfalls

Not finding a class/resource is also a meaningful outcome, but caching errors improperly can introduce bugs:

- If you permanently cache `ClassNotFoundException` in a loader whose source URLs can still receive new files, a new plugin will never be found even after the file appears.
- If you try to cache `null` in `ConcurrentHashMap`, the `put` operation will throw `NullPointerException` because `ConcurrentHashMap` does not allow null keys or values.
- If a file fails transiently, immediate retries across all threads can cause an I/O/network **thundering herd**. Use backoff/timeout or short-TTL negative caching when appropriate.
- If an artifact is immutable (frozen generation) and a class is guaranteed not to exist, negative caching can make sense, but it must be tied to the **artifact generation**.
- If bytecode fails with `ClassFormatError`, `VerifyError`, or `SecurityException`, do not treat it like a transient network error; report the error accurately and inspect the source.
- Never swallow `LinkageError` and try to define another class with the same name as a "retry".

**Lesson:** invalidation policy must follow **error type**, **source reliability**, and **generation immutability**, not merely "whether an exception was caught".

## 12. Performance: Measuring the Right Bottleneck

Increasing parallelism does not always increase throughput. Some common limits:

| Cost | If Done Wrong | Recommendation |
|---|---|---|
| Disk/network reads | Multiple threads read the same file concurrently | Single-flight for cache misses; bound concurrency |
| CPU transform/verify | Repeating bytecode transformations multiple times | Cache results by hash + transform version when valid |
| Class-loading locks | Holding a global loader lock for all classes | Register parallel-capable if the design supports it |
| Cache memory | Holding unbounded `byte[]`, duplicating in heap/metaspace | Enforce memory limits and eviction |
| Resource streams | Sharing one stream or forgetting to close | One stream per caller, try-with-resources |
| Source snapshot | Reading class v2 but resource v1 during deployment | Pin immutable generation and publish atomically |
| Logging | Detailed per-class per-thread logging | Use sampling/structured metrics to reduce overhead |
| Retry | I/O error triggers immediate retries by all threads | Backoff + single-flight + error taxonomy |

### Metrics Worth Collecting

- `cache_hits` / `cache_misses` by class/resource and generation.
- `inflight_loads`, waiter count, and future wait time.
- `source_read_count` and file/JAR/network latency.
- `class_load_failures` by `ClassNotFoundException`, `LinkageError`, and I/O errors.
- `resource_read_failures`, `resource_bytes_cached`, and eviction count.
- CPU, heap pressure, metaspace, and number of live classloaders.
- When needed: analyze JFR/JVM Unified Logging `-Xlog:class+load=info,class+unload=info` on an appropriate JDK.

Do not log full bytecode, resource secrets, or paths containing credentials. When diagnosing, log controlled source identifiers/hashes and loader identity.

## 13. Concurrency Testing: Essential Cases

**Test 1 — Multiple threads, same class name:** returns the same `Class<?>`, with no duplicate `defineClass` or `LinkageError`.

**Test 2 — Multiple threads, different class names:** with a parallel-capable loader, loads can proceed concurrently if the source/cache supports it; no races or deadlocks.

**Test 3 — Same resource path:** every stream reads the full content without sharing a read cursor.

**Test 4 — Missing resource:** fails with a clear cause, retries according to policy, and does not cache null permanently.

**Test 5 — Missing class/dependency:** distinguishes `ClassNotFoundException` from `NoClassDefFoundError`; does not blindly retry linkage errors.

**Test 6 — Corrupt bytecode:** propagates `ClassFormatError`/verification errors properly, without swallowing or caching them as valid data.

**Test 7 — Source updated between reads:** enforces immutable generations; never mixes bytes/configs from two releases.

**Test 8 — Cache pressure:** enforces memory limits and proper eviction, without evicting a future still needed by the loader before its state is handled.

**Test 9 — Shutdown and in-flight loads:** stops new requests, drains, then closes; prevents other threads from calling a closed loader.

**Test 10 — Plugin redeploy:** old loader retains no stray references via static caches, TCCL, or background executors; new loader has its own generation.

**Test 11 — Parent delegation:** if the parent has the class, the custom child returns the parent's class without unnecessarily trying to redefine it.

**Test 12 — Duplicate resource names:** class policy and resource lookup policy are tested separately if parent/child share the same path.

**Test 13 — Interruption:** waiters receive/preserve interrupts properly without inadvertently canceling a shared producer.

**Test 14 — Cache failures:** after a transient failure, a new load can retry; metrics reflect attempt counts instead of assuming the cache is always exactly-once.

**Test 15 — Malicious/untrusted paths:** validate class/resource names and sources; prevent path traversal, symlink surprises, zip-slip when extracting JARs, and loading untrusted bytecode.

## 14. Common Pitfalls and How to Identify Them

| Symptom | Typical Cause | Resolution |
|---|---|---|
| `LinkageError: duplicate class definition` | Two code paths calling `defineClass` for the same name/loader | Route through `loadClass` lock, avoid calling `findClass` directly |
| Class loading deadlock | Delegation cycle or lock ordering between A/B | Take thread dumps, analyze locks, use parallel capability |
| `ClassNotFoundException` despite file existing | Wrong parent/source path/negative cache | Check binary name, URL/JAR, and generation |
| `NoClassDefFoundError` | Missing dependency, failed static init, or linkage error | Inspect `Caused by` and bytecode source |
| Partial resource reads across threads | Sharing a single `InputStream` | Cache bytes + create a new stream per caller |
| Resource unchanged after deploy | Cache key lacks version/generation | Invalidate or switch generation at the right time |
| GC retains old plugin | Global cache holds `Class<?>`/ClassLoader | Reduce strong references, manage lifecycle |
| `OutOfMemoryError: Java heap space` | Cache holds unbounded large bytes | Bound size, add eviction/streaming |
| `IllegalStateException` in `computeIfAbsent` | Recursive map update inside mapping function | Do not update the same map from the mapping callback |
| Multiple file reads after error | Future removed for retry while many requests arrive | Apply backoff and single-flight per attempt |
| Load fails during shutdown | Source closed while threads are still reading | Use ACTIVE/DRAINING/CLOSED protocol |
| Class cache returns wrong type | Global cache keyed only by class name | Key by loader identity/generation; never cache `Class` across loaders |

## 15. Practical Rules

**Do:**

1. Extend `ClassLoader` and override **`findClass`** if keeping default delegation.
2. Register `parallel-capable` once in static initialization when genuinely designed for concurrency.
3. Let `getClassLoadingLock(name)` coordinate class loading by name; do not invent a second catch-all lock unnecessarily.
4. Use `ConcurrentHashMap` and immutable cache entries; apply single-flight when cache misses are expensive.
5. Distinguish `Class<?>` runtime identity from `byte[]` source artifacts.
6. Return a new stream per caller, close streams promptly, and manage memory budgets.
7. Pin version/content hash/generation, and define invalidation and retry rules.
8. Log class/resource source along with loader identity and failure cause.
9. Ensure shutdown waits for in-flight operations before closing the source provider.
10. Test data contention, failures, version switches, and lifecycle under realistic workloads.

**Avoid:**

- Sharing unlocked mutable `HashMap`/`ArrayList` as a loader cache across threads.
- Using `if (!map.containsKey(k)) map.put(k, read())` and assuming it is atomic.
- Sharing an `InputStream` as a resource cache value.
- Calling `defineClass` repeatedly to "cache classes", or holding `Class<?>` indefinitely in a global static map.
- Placing long network I/O and complex callbacks inside `computeIfAbsent`.
- Treating `registerAsParallelCapable` as an automatic guarantee for all subclass shared state.
- Treating `close` as equivalent to immediate class unloading.
- Relying on a classloader as a sandbox for running untrusted code.

## 16. Self-Check

**Q1.** Two threads concurrently call `loader.loadClass("p.Task")`. Why shouldn't both call `defineClass` directly from outside `loadClass`?

**Answer:** The JVM does not allow two definitions for the same binary name in one defining loader; it can throw `LinkageError`. Use locking inside `loadClass` and check whether the class is already loaded.

**Q2.** Does registering `registerAsParallelCapable` make a loader's own `HashMap` thread-safe?

**Answer:** No. It only changes the class-loading lock mechanism; any mutable cache in the subclass still requires synchronization/safe publication.

**Q3.** Does `ConcurrentHashMap<String, byte[]>` protect `byte[]` from being modified by another thread?

**Answer:** Not yet. The map is thread-safe, but the array remains mutable. Use immutable snapshots, never hand out the underlying array to code that might mutate it, or return a copy when needed.

**Q4.** Why use `FutureTask<byte[]>` with `putIfAbsent` instead of letting multiple threads read bytes concurrently and then call `putIfAbsent`?

**Answer:** The placeholder future is published **before** I/O begins, so threads requesting the same key wait on one task instead of performing duplicate I/O.

**Q5.** Can we cache an `InputStream` and hand the same stream to 24 threads?

**Answer:** No: a stream has read-position state and a close lifecycle, so one thread can corrupt another thread's result. Cache immutable bytes and create a new stream per caller.

**Q6.** If we want to update `plugin.Task` from bytecode v1 to v2, does replacing bytes in the same `ClassLoader`'s cache update the `Class<?>` currently in use?

**Answer:** No. An already-defined runtime class is not automatically replaced with new bytes through normal classloader mechanisms. Use a new loader generation or dedicated class redefinition mechanisms with their own constraints.

**Q7.** Why does `URLClassLoader.close()` need to coordinate with in-flight loads?

**Answer:** The API leaves the result undefined if one thread is loading a class while another closes the loader. Stop accepting new loads and drain before closing.

**Q8.** If `computeIfAbsent` runs a network request taking several seconds, is that always a good design?

**Answer:** No. The JDK recommends short, simple mapping functions because other updates can be blocked; use a future placeholder/single-flight and manage timeouts/retries outside the map operation.

**Q9.** Is a cache key containing only `plugin.Task` sufficient for a cache shared across two plugin generations?

**Answer:** No. You also need the artifact/source identity and version/hash/generation to avoid serving bytes with different content.

## 17. Recommended Design Diagram

~~~text
                 Concurrent requests for key K
                           |
                           v
                  Check loader/generation
                           |
                           v
             CHM<K, FutureTask<bytes>>
                  /                \
           Future exists         Not present
                 |                   |
             future.get()      putIfAbsent(new task)
                 |                   |
              receive bytes     Winner runs task
                 |                   |
                 +---------+---------+
                           |
                     Immutable bytes
                           |
           +---------------+----------------+
           |                                |
    Class-loading path                Resource path
           |                                |
      getClassLoadingLock(name)       new InputStream
           |                           per caller
       findLoadedClass
           |
       findClass / defineClass
           |
       Runtime Class<?>
           |
    Follows its own loader lifecycle
~~~

**Remember three principles:**

1. **Locking class definition is the responsibility of the class-loading path.** Use `loadClass`/`getClassLoadingLock` properly and define each class only once per loader.
2. **The bytecode/resource cache is a separate layer.** Use versioned keys, immutable data, single-flight, and independent streams.
3. **Lifecycle determines long-term safety.** Handle failure/retry, invalidation, memory budgets, and shutdown before closing loaders/sources.

### Official Documentation

- [Java SE 17 — ClassLoader: parallel-capable, getClassLoadingLock, loadClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — ConcurrentHashMap: computeIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#computeIfAbsent(K,java.util.function.Function))
- [Java SE 17 — FutureTask: concurrent computation and get](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html)
- [Java SE 17 — URLClassLoader: close concurrency caveat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html#close())
- [JVMS 17 §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3)
