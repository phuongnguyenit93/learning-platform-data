# Scoping Caches Properly Without Retaining Expired ClassLoaders

## 1. The Problem: Caching Is Faster, but Can Prevent Plugins from Ever Being Unloaded

A plugin system typically creates a dedicated `ClassLoader` for each plugin or each version. To reduce reflection, lookup, or metadata processing overhead, the host may cache `Class<?>`, `Method`, `Constructor`, provider instances, parsers, or computed objects.

For example:

```java
static final Map<String, Class<?>> CLASSES = new ConcurrentHashMap<>();
```

This is an illustrative snippet that requires imports and placement inside a class. If this map is a **static field of the host that lives for the entire process** and holds a class defined by a plugin loader, the map can keep the class → defining loader → the entire set of plugin class metadata reachable. The plugin has been "stopped" from a business perspective, yet the Java heap/Metaspace still retains traces of the old-generation loader.

**Core principle:** **A cache's lifetime must not exceed the lifetime of the data/classes/plugins it owns, unless the cache uses a mechanism that does not keep old objects alive and has a properly understood eviction policy.**

A quick decision table:

| What is being cached? | Appropriate owner | When to release? |
|---|---|---|
| Immutable JDK/shared API metadata | Host cache, if it holds no plugin-private references | Host lifecycle or capacity-bounded policy |
| Plugin `Class<?>`/`Method` | Cache tied to **plugin session/generation** | When the plugin stops or reloads |
| Provider/plugin instance | Registry tied to active deployment | On stop, after stopping callbacks/tasks |
| Parse result of a single request | Request-local cache | End of request |
| Metadata computed per runtime `Class<?>` | Consider `ClassValue` | Follows Class association lifecycle; still check external references |
| Negative "class not found" result | At most within a defined finder/version snapshot scope | Discard when sources change; do not cache indefinitely |
| Reflection method lookup | Per-plugin cache keyed properly by class + signature | Clear along with the plugin loader |

There is no simple answer like "always use weak refs" or "always use a static map." You must know **who holds the cache**, **what the cache holds**, **what the key is**, **whether the value points back to the loader**, and **which lifecycle event removes entries**.

## 2. JVM Fundamentals: Why Retaining a Class<?> Can Retain a Loader

According to JLS 17 `12.7, a class/interface **may be unloaded only if its defining class loader may be reclaimed by GC**. "May" does not mean the JVM will unload it immediately.

A common reference graph:

```text
Host GC root
     |
     v
static ConcurrentHashMap<String, Class<?>>
     |
     v
plugin.Worker.class
     |
     v
Defining PluginClassLoader
     |
     v
Runtime classes / metadata defined by the loader
```

A cache can retain a loader indirectly:

```text
Host static cache
   -> java.lang.reflect.Method
   -> declaring Class<?> of the plugin
   -> defining loader of the plugin
```

Or:

```text
Host event registry
   -> plugin callback/lambda
   -> plugin object/class
   -> plugin defining loader
```

Therefore, simply setting `loader = null` is not enough if a `Method`, `Class<?>`, provider object, callback, or thread context class loader is still pointing to that plugin generation.

### Defining loader vs. initiating loader

`pluginLoader.loadClass("api.Plugin")` may delegate to the parent to obtain **the host's same `api.Plugin.class`**. Caching this shared API class does not mean retaining a class defined by the plugin loader. Conversely, `pluginLoader.loadClass("plugin.Worker")` usually returns a class defined by the plugin loader if the parent does not have that name.

You must distinguish:

- **Defining loader:** the loader that actually defines the runtime class; directly affects class unloading eligibility.
- **Initiating loader:** the loader that the JVM records as having initiated the lookup, which may receive a class back from the parent.
- **Class identity:** binary name + defining loader, not just the class name.

Do not assume "I called `loadClass` via the plugin loader, so every `Class<?>` returned is owned by the plugin loader."

## 3. ClassLoader Already Remembers Loaded Classes; Avoid Pointless Duplicate Caching

In the default `ClassLoader.loadClass(String, boolean)`, the JVM/loader checks `findLoadedClass(name)` before searching the parent or `findClass`. Calling it again:

```java
Class<?> a = loader.loadClass("plugin.Worker");
Class<?> b = loader.loadClass("plugin.Worker");
System.out.println(a == b);
```

This is a snippet requiring a `loader` variable and `ClassNotFoundException` handling. With a properly functioning loader, the same runtime class name/loader lookup policy typically returns the same `Class<?>`; in that case, it prints `true`. In other words, creating an extra `static Map<String, Class<?>>` just to "avoid loading a class a second time" can yield very little benefit while carrying a huge risk of retaining old plugins.

Additional caching should only exist after measuring/knowing the cost you need to optimize, such as:

- Reflection lookups with `getMethod`, `getDeclaredConstructor`, or member scanning.
- Annotation/schema analysis metadata.
- Method handles or serializers/deserializers compiled for a specific class.
- Resolution results from a plugin registry with a known structure.

**Measure cache hit rate, allocation, and lookup latency** before turning an internal cache into a global static. Caching has its own synchronization, key construction, memory, and invalidation costs.

## 4. Choose Cache Scope by Lifecycle, Not by Static Field Convenience

There are at least four scopes:

| Scope | Example | Suitable for plugin-private Class<?>? |
|---|---|---|
| Method/request | Local map used during the current request | Possibly, if truly needed only for the request |
| Operation/job | Cache for a batch/job executing inside the plugin | Possibly, provided the job finishes and is not held indefinitely by a queue |
| Plugin session/generation | `PluginSession` holding the loader and reflection caches | **Usually a good choice** |
| Host process/global singleton | Static map of the application loader | **Dangerous** if it retains private classes/loaders across reloads |

A **plugin generation** is a specific load instance: plugin X v1 has loader L1; reloading plugin X v2 creates loader L2. Two deployments may share the same logical plugin ID and the same binary class name, but they are **two different cache scopes**.

### Wrong: global cache keyed by binary name

```java
static final Map<String, Class<?>> TYPES = new ConcurrentHashMap<>();

// Host calls across multiple plugin generations:
TYPES.put("plugin.Worker", workerClass);
```

This snippet is illustrative and needs imports/a containing class for the field. If plugins A and B both have `plugin.Worker` defined by different loaders, keying solely by `"plugin.Worker"` will cause a **cache collision**. The host could return plugin A's class to B, leading to cast/linkage errors or continuing to pin the old loader.

**Two independent bugs:**

1. **Wrong identity:** a class name is not sufficient as a cache key across multiple defining loaders.
2. **Wrong lifetime:** a static map can retain classes from already-stopped generations.

Even if you add `pluginId` to the key, e.g., `"plugin-a:plugin.Worker"`, you still need a version/generation and an eviction policy. An ID can be reused on reload, whereas the new loader object has a different identity.

### Better: cache inside a PluginSession

```text
Host registry (contains only active sessions)
  -> Session plugin-A generation 42
     -> URLClassLoader L42
     -> Method / Class<?> cache belonging to L42
  -> Session plugin-B generation 7
     -> URLClassLoader L7
     -> dedicated cache

When stopping plugin-A:
  stop tasks/callbacks
  registry.remove(plugin-A)
  session.clearCaches()
  session.closeLoader()
  drop all strong references to the old session
```

In this model, **strong references inside the session are not wrong**. They are useful while the plugin is active. What matters is that the session is genuinely **removed from long-lived roots** when the plugin ends.

## 5. Complete Java 17 Example: Caching Method Within PluginSession Scope

This example uses a dedicated `URLClassLoader` to load `plugin.Greeter`, memoizes the reflection `Method` by class and signature, and clears the cache/closes the loader when the session ends.

Do not assume that closing the loader will immediately trigger a class-unload event; this only demonstrates deterministic cache hits and **lifecycle-driven cleanup**.

### 5.1. File structure

```text
src/
  plugin/
    plugin/
      Greeter.java
  host/
    SessionCacheDemo.java

out/
  plugin/
  host/
```

`out` is created during the compilation step.

### 5.2. Plugin class

File `src/plugin/plugin/Greeter.java`:

```java
package plugin;

public final class Greeter {
    static {
        System.out.println("PLUGIN_INITIALIZED");
    }

    public static String greet(String name) {
        return "Hello " + name;
    }
}
```

### 5.3. Host with a dedicated cache per session

File `src/host/SessionCacheDemo.java`:

```java
import java.io.IOException;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class SessionCacheDemo {
    static final class PluginSession implements AutoCloseable {
        private record MethodKey(
                String owner, String name, List<Class<?>> parameterTypes) {
        }

        private final URLClassLoader loader;
        private final Map<MethodKey, Method> methodCache =
                new HashMap<>();
        private int misses;
        private boolean closed;

        PluginSession(URL source, ClassLoader parent) {
            loader = new URLClassLoader(
                    "plugin-session", new URL[]{source}, parent);
        }

        Method method(String owner, String name, Class<?>... params)
                throws ReflectiveOperationException {
            if (closed) {
                throw new IllegalStateException("Session closed");
            }

            MethodKey key = new MethodKey(
                    owner, name, List.copyOf(Arrays.asList(params)));
            Method cached = methodCache.get(key);
            if (cached != null) {
                return cached;
            }

            Class<?> type = Class.forName(owner, false, loader);
            Method found = type.getMethod(name, params);
            methodCache.put(key, found);
            misses++;
            return found;
        }

        ClassLoader loader() {
            return loader;
        }

        int missCount() {
            return misses;
        }

        int cacheSize() {
            return methodCache.size();
        }

        @Override
        public void close() throws IOException {
            if (!closed) {
                closed = true;
                methodCache.clear();
                loader.close();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        URL pluginRoot = Path.of("out/plugin").toUri().toURL();
        ClassLoader sharedParent =
                SessionCacheDemo.class.getClassLoader();

        try (PluginSession session =
                     new PluginSession(pluginRoot, sharedParent)) {

            Method first = session.method(
                    "plugin.Greeter", "greet", String.class);
            Method second = session.method(
                    "plugin.Greeter", "greet", String.class);

            System.out.println("Same cached Method: "
                    + (first == second));
            System.out.println("Reflection cache misses: "
                    + session.missCount());
            System.out.println("Declaring loader is plugin: "
                    + (first.getDeclaringClass().getClassLoader()
                       == session.loader()));
            System.out.println("Before invocation");

            System.out.println(first.invoke(null, "Ada"));
            System.out.println(second.invoke(null, "Bao"));

            System.out.println("Cache entries before close: "
                    + session.cacheSize());
        }

        System.out.println("Session closed");
    }
}
```

**Why does the key contain `Class<?>` instead of parameter type name strings?** `MethodKey` holds the declaring binary name, method name, and **runtime parameter classes**. `Class<?>` instances in the `List` are compared by identity in Java; `Class<?>` objects defined by two different loaders will not be treated as the same type just because `getName()` matches. The session scope ensures the declaring name is only looked up through that session's loader.

`List.copyOf(Arrays.asList(params))` keeps an immutable snapshot of the parameter types list; never use a mutable varargs array as a key.

**For production:** the key can directly use the declaring `Class<?>` if you already have the type and exact method signatures; if a cache is shared among classes from multiple loaders, never use string names alone. If inherited methods or overloads/varargs are involved, ensure the lookup contract and parameter descriptors are handled accurately.

### 5.4. Compile/run on JDK 17

Bash:

```bash
mkdir -p out/plugin out/host
javac -d out/plugin src/plugin/plugin/Greeter.java
javac -d out/host src/host/SessionCacheDemo.java
java -cp out/host SessionCacheDemo
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out/plugin,out/host
javac -d out/plugin src/plugin/plugin/Greeter.java
javac -d out/host src/host/SessionCacheDemo.java
java -cp out/host SessionCacheDemo
```

**Do not** include `out/plugin` on the host's `-cp`, otherwise the parent loader could provide `plugin.Greeter` before the session's `URLClassLoader` is consulted under the parent-first policy.

Deterministic stdout on a clean run:

```text
Same cached Method: true
Reflection cache misses: 1
Declaring loader is plugin: true
Before invocation
PLUGIN_INITIALIZED
Hello Ada
Hello Bao
Cache entries before close: 1
Session closed
```

### 5.5. Understanding the output

1. Two lookups with the same `MethodKey` within a session return the same `Method` instance, proving a cache hit.
2. Only the first lookup performs `Class.forName(..., false, loader)` and `getMethod`; `missCount` is 1.
3. The `Method`'s declaring `Class<?>` is indeed defined by the session `URLClassLoader`.
4. `Class.forName(..., false, ...)` locates the class without requiring initialization. The static initializer `PLUGIN_INITIALIZED` runs only when the reflective invocation of the static method is executed.
5. The cache strongly retains the `Method` and the `Class<?>` instances referenced by keys/values **while the session is active**. That is intentional.
6. `close()` clears the cache and closes the `URLClassLoader` resources.
7. After exiting the scope and with no other roots retaining the session/Method/Class, the defining loader **may** become eligible for GC. The example does **not** claim that the JVM has already GC'd or unloaded the class as soon as `Session closed` is printed.

The local variables `first` and `second`, along with JVM stack/liveness, can also affect GC eligibility near the end of the `try` block. That is why the demo intentionally does **not** print an `"unloaded=true"` boolean after closing.

### 5.6. Concurrent deployment considerations

The `HashMap` in the demo is only for sequential access. If a `PluginSession` serves multiple threads concurrently, do not share an unsynchronized `HashMap` as if it were thread-safe. You can:

- Use `ConcurrentHashMap<MethodKey, Method>` and `computeIfAbsent` with an appropriate exception/lookup policy.
- Or synchronize the cache lookup region in a controlled manner.
- More importantly, **coordinate `close` with in-flight tasks** so you do not close the loader and clear the cache while a worker still needs to load classes or execute the plugin.

Do not use a single global lock for all plugins if they can operate independently; avoid unnecessary contention.

## 6. Clearing Caches on Plugin Stop: Order Matters

A sensible lifecycle:

```text
ACTIVE
  |
  v
STOPPING: stop accepting new requests
  |
  v
DRAIN: wait for in-flight tasks to complete
  |
  v
UNREGISTER: listeners / scheduled jobs / providers
  |
  v
CLEAR: session's method/class/provider caches
  |
  v
CLOSE: streams / JAR handles / URLClassLoader
  |
  v
REMOVE: remove session from the host registry
  |
  v
Leave the old loader with no strong reachability
  |
  v
JVM can GC/unload when appropriate (no deadline)
```

The exact order may vary by framework; the invariant is that **no new work accesses a closed session** and all unnecessary roots must be removed. Sometimes you need to remove the registry entry **before** closing the loader to forbid new lookups, while keeping a local/session handle for the drain and close phases. Synchronize state transitions `ACTIVE → STOPPING → CLOSED` to avoid races.

### Host registry holding active sessions

Architectural snippet:

```java
Map<String, PluginSession> active = new ConcurrentHashMap<>();

// Start: add active session
active.put(pluginId, session);

// Stop: block new requests first, drain tasks, then:
PluginSession old = active.remove(pluginId);
if (old != null) {
    old.close();
}
```

This is a **snippet**, not a standalone program: you must declare types/variables and implement appropriate request-blocking/draining policies. Never keep removed sessions in a static `List<PluginSession> oldSessions` "for debugging" indefinitely; that recreates the leak through another path.

**A cache may use strong references as long as its lifetime is bounded and explicitly cleaned up.** Not every cache has to be weak.

## 7. The WeakHashMap Trap: Weak Keys, but Values Keep the Loader Alive

`WeakHashMap<K,V>` holds **keys via weak references**, but **values via strong references**. The Java SE 17 documentation specifically warns: if a value has a **direct or indirect** strong path back to its key, the key will not be discarded by GC.

Dangerous example:

```java
static final Map<ClassLoader, Class<?>> CACHE =
        new WeakHashMap<>();

CACHE.put(pluginLoader, pluginLoader.loadClass("plugin.Greeter"));
```

This is a snippet requiring appropriate variables/imports. The host's static map holds:

```text
Host static WeakHashMap
    |
    +-- weak key ----> pluginLoader
    |
    +-- STRONG value -> plugin.Greeter.class
                             |
                             v
                      defining pluginLoader
```

Even though the key is weak, the **value** is a `Class<?>` of a class defined by that very loader, so the value can keep the loader key strongly reachable. The entry does not vanish on its own as you might expect.

Similarly:

```java
Map<ClassLoader, Method> methods = new WeakHashMap<>();
methods.put(pluginLoader, pluginMethod);
```

`Method` is linked to its declaring class, which can pull in the defining loader. If the map lives as long as the host, "switching `HashMap` to `WeakHashMap`" **does not automatically fix** every classloader leak.

### What if the value is just a String?

`WeakHashMap<ClassLoader, String>` where the value does not retain the key or plugin graph can be suitable in some scenarios. Even then, you must still consider:

- Other strong references to the key.
- `WeakHashMap` is not thread-safe by default.
- Cleanup depends on GC; there is no deterministic deadline.
- Do not rely on a weak-key cache to guarantee business correctness or lifecycle shutdown.

Use weak keys only when **weak ownership semantics are genuinely needed** and you have verified there is no strong reference path back from the value to the key.

### Does WeakReference for the value automatically solve everything?

You might try:

```java
Map<ClassLoader, WeakReference<Class<?>>> cache =
        new WeakHashMap<>();
```

Still, this is only an **architectural snippet**. A weak value can avoid one root-retaining path, but the cached value can be GC'd at any time, making hits/misses unstable. If `ref.get()` returns non-null, you must hold the referent in a strong local variable throughout its use. You must also account for concurrency, key identity, stale entries, and cleanup. Never use weak refs as a tool to force unloading.

**For plugins with a clear lifecycle, a per-session strong cache + explicit teardown is usually easier to understand and control** than a complex web of weak maps.

## 8. ClassValue: Metadata Attached to Class<?> Instead of a Global Map<Class<?>, V>

`java.lang.ClassValue<T>` associates a *lazy computed value* with a runtime `Class<?>`. It is useful for per-class metadata, dispatch tables, or reflection info, and avoids building a global static map keyed by `Class<?>` that could pin plugin classes.

Standalone Java 17 example — file `ClassValueDemo.java`:

```java
import java.lang.reflect.Method;

public final class ClassValueDemo {
    private static final ClassValue<Integer> PUBLIC_METHOD_COUNT =
            new ClassValue<>() {
                @Override
                protected Integer computeValue(Class<?> type) {
                    return type.getMethods().length;
                }
            };

    public static void main(String[] args) {
        Class<?> type = String.class;
        int a = PUBLIC_METHOD_COUNT.get(type);
        int b = PUBLIC_METHOD_COUNT.get(type);

        System.out.println("Same computed value: " + (a == b));
        System.out.println("Nonnegative method count: " + (a >= 0));

        PUBLIC_METHOD_COUNT.remove(type);
        int afterRemove = PUBLIC_METHOD_COUNT.get(type);
        System.out.println("Recomputed value is nonnegative: "
                + (afterRemove >= 0));
    }
}
```

Compile/run:

```bash
javac ClassValueDemo.java
java ClassValueDemo
```

Deterministic stdout:

```text
Same computed value: true
Nonnegative method count: true
Recomputed value is nonnegative: true
```

This example uses `Integer` and compares numeric values rather than relying on `Integer` wrapper identity or a specific count of public methods on `String`, which may vary across JDKs.

**Limitations to understand:**

1. `ClassValue.get(type)` computes/retrieves a value bound to **runtime class identity**, not just the binary name.
2. `computeValue` may be invoked multiple times under a race; the API guarantees one value is chosen upon installation, **not that computation runs only once**.
3. `remove(type)` removes the association so the next `get` can recompute; it is not a class-unloading command.
4. `ClassValue` does not automatically make a metadata value safe to share across loader boundaries.
5. If the value or class token is retained in **another global cache**, `ClassValue` cannot fix that external strong reference path.
6. Do not additionally cache plugin-defined `Method`/MethodHandle/`Class<?>` in other static maps while forgetting lifecycle.

Use `ClassValue` when **the cache is truly a property of the class**. Use a per-session cache when logic depends on plugin configuration, version, permissions, or a dedicated lifecycle.

## 9. Choosing Cache Keys with Proper Class Identity, Not Just getName()

Loader generations A and B can both define `plugin.Service`:

```text
("plugin.Service", LoaderA) != ("plugin.Service", LoaderB)
```

If the cache lives on the host:

```java
Map<String, Method> cache = new ConcurrentHashMap<>();
cache.put(method.getDeclaringClass().getName() + "#run", method);
```

This snippet does not distinguish loader A from B, and the `Method` value can pin the old loader. Even if the key is extended with `pluginId`, if plugin v1 and v2 share the same `pluginId`, you will need a generation discriminator and explicit invalidation.

### When the cache lives inside a session

If a session owns exactly one loader generation and is cleared on stop, the binary name can be part of the key; the scope already provides identity. However, method overloading must still account for parameter types:

```java
record MethodKey(
    Class<?> declaringClass,
    String methodName,
    List<Class<?>> parameterTypes) {}
```

This is an illustrative type declaration requiring `import java.util.List`. `Class<?>` keys strongly retain runtime classes — **acceptable within an active session**, but not in an unbounded static map.

### Caching lookup vs. caching compiled metadata

If computed metadata is instance-independent and belongs to the runtime class, consider `ClassValue`. If metadata depends on application configuration, locale, plugin version, or tenant, the key must include all dimensions affecting the result; do not use `Class<?>` as the sole key when the result actually depends on multiple parameters.

**A wrong cache key can cause functional bugs even when there is no memory leak.**

## 10. Caching "Class Not Found" Is a Special Case

Some plugin systems cache negative results to avoid rescanning JARs on every request:

```java
Set<String> notFound = ConcurrentHashMap.newKeySet();
```

This snippet needs imports and placement inside a class. Negative caching is only valid within a **fixed source snapshot** under a fixed lookup policy.

If a plugin directory/`ModuleLayer`/classpath is updated, a previously missing name may become available. A global negative cache could cause the system to throw `ClassNotFoundException` forever even after the artifact is deployed. Conversely, a positive cache could retain a class from an old version after reload.

Rules:

- Bind the negative cache to the **plugin generation**.
- When the version/artifact/finder/layer changes, discard the old negative cache.
- Do not cache every failure as "not found": `LinkageError`, `SecurityException`, initialization failure, and dependency failure have different semantics.
- If using a TTL, remember that a TTL does not replace lifecycle events: on stop/reload, invalidate immediately rather than waiting for time to expire.
- If the loader does not actually reread dynamic sources within the same generation, designing an **immutable snapshot** makes negative caching easier to reason about.

## 11. TCCL, Thread Pools, and ThreadLocal Are Non-Obvious Cache Roots

Even after the session cache is cleared, a loader can stay alive because a worker thread retains the **thread context class loader (TCCL)**:

```text
Long-lived Executor worker
   -> Thread.contextClassLoader
   -> Old PluginClassLoader
```

Or:

```text
Worker Thread
   -> ThreadLocalMap.value
   -> plugin-specific context
   -> plugin class
   -> plugin loader
```

Changing the TCCL on the submitting thread **does not necessarily** change the TCCL of an existing pooled worker. If a framework requires using the TCCL, you must set and restore it **on the actual worker**:

```java
Thread thread = Thread.currentThread();
ClassLoader old = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    invokeLegacyFramework();
} finally {
    thread.setContextClassLoader(old);
}
```

This is an illustrative snippet, requiring `pluginLoader` and `invokeLegacyFramework()` in scope. Do not use `setContextClassLoader(null)` as a default reset; restore the exact `old` value.

For `ThreadLocal`, call `remove()` in `finally` on the worker thread itself before returning the worker to the pool. The fact that `ThreadLocal` keys are weak does not make values weak; a plugin value living in a long-lived worker can still pin the loader.

### Async tasks after session close

A callback sitting in a queue may contain a lambda class/closure defined by the plugin loader, or capture a plugin object. Even if the main registry entry is removed, a lingering scheduled task can still keep the old generation alive.

**Cache lifecycle and task lifecycle must be coordinated**: stop accepting new work, cancel scheduled tasks, drain in-flight work, unregister listeners/callbacks, clean up `ThreadLocal`s and TCCL, and then clear caches/close the loader.

## 12. ServiceLoader, Proxies, Reflection, and MethodHandle

Frameworks commonly cache various kinds of metadata:

| Cached value type | What can it retain? | Suggested scope |
|---|---|---|
| `ServiceLoader<S>` | Service/provider metadata and instances, loader/layer depending on configuration | Per plugin/provider registry; do not cache indefinitely by TCCL |
| `Method` / `Constructor` / `Field` | Declaring class and related metadata | Per-class `ClassValue` or per-session |
| `MethodHandle` / `MethodHandles.Lookup` | Method/type/access context | Per-session or per-class depending on ownership |
| Dynamic proxy class/instance | Interface types, invocation handler, defining loader | Do not let a host singleton retain a proxy from an old plugin |
| Lambda/callback | Captured objects/instances and classes | Unregister/cancel when the plugin stops |
| Serializer/deserializer compiled for private DTO | Runtime class metadata | Per-class/per-session, not global unbounded |
| `URLClassLoader` | JAR/resource handles and class loader object | Close when work finishes; drop strong references |

`ServiceLoader.load(Plugin.class)` uses the TCCL, whereas the `ServiceLoader.load(Plugin.class, chosenLoader)` overload lets you specify the loader explicitly. For a plugin registry where the loader is known, minimize reliance on implicit TCCL.

If you want to cache providers, cache them inside a **lifecycle-managed session/layer**, rather than keeping plugin v1's `ServiceLoader` in a host singleton after v2 has reloaded.

## 13. A Weak Cache Does Not Replace Resource Lifecycle Management

`WeakReference` and `ReferenceQueue` help observe GC eligibility, but they do not call `URLClassLoader.close()` at the right time or terminate running threads.

Observation example:

```java
WeakReference<ClassLoader> weak = new WeakReference<>(loader);
```

This snippet requires `import java.lang.ref.WeakReference` and a `loader` variable. If another strong reference exists, `weak.get()` can still return the loader. If `weak.get() == null`, the collector has processed the referent according to weak-reference semantics; **this does not guarantee a class-unload log or immediate RSS reduction**.

Do not write tests based on:

```java
System.gc();
if (weak.get() != null) {
    throw new AssertionError("Leak!");
}
```

`System.gc()` is a hint, not a guarantee that the collector has reclaimed the loader. A single `get() != null` does not prove a leak; the JVM may simply not have collected yet.

If using `WeakReference.get()` to operate on the referent:

```java
ClassLoader alive = weak.get();
if (alive != null) {
    // Use alive immediately within this strong local scope.
    java.lang.ref.Reference.reachabilityFence(alive);
}
```

This snippet illustrates that `alive` must not be stored into an unbounded host cache; `reachabilityFence` guarantees reachability past the fence point per its contract. It does not replace a lifecycle owner.

### WeakReference is an observation tool, not the sole source of truth

When a loader is collected, the Java API does not provide a synchronous, portable "class unload event" across all JVMs. Combine weak reference monitoring with GC/class-unload logs, classloader statistics, and heap reference graphs as appropriate.

If using `Cleaner` to clean up resources, ensure the cleaning action **does not capture the referent itself** or a plugin instance/loader, otherwise it can keep it alive. For `URLClassLoader`, close it proactively according to lifecycle rather than relying solely on cleaners or finalization.

## 14. ClassValue, WeakHashMap, and Per-Session Maps: A Practical Comparison

| Design | Pros | Risks / caveats | When suitable |
|---|---|---|---|
| Static `Map<String, Class<?>>` | Simple lookup | Key collision across loaders, retains old Class/loader | Avoid for plugin-private classes |
| Static `Map<Class<?>, Method>` | Accurate identity key | Strong key and value → pins plugin | Avoid without lifecycle-based eviction |
| Static `WeakHashMap<ClassLoader, Class<?>>` | Weak key | Value Class points indirectly back to key → pins loader | **Usually wrong** when value is a class of the key |
| `WeakHashMap<ClassLoader, WeakReference<V>>` | Avoids strongly retaining value | Nondeterministic GC, race/cleanup complexity | Only when weak semantics are deliberately designed |
| `ClassValue<V>` | Automatically binds value to runtime Class identity | Does not solve roots in other caches; `computeValue` can race | Per-class derived metadata |
| `PluginSession` + `HashMap`/`ConcurrentHashMap` | Clear lifecycle, fast lookup, easy to test | Must close/clear at the right time and synchronize in-flight work | **Good default choice** for many plugin systems |
| Host bounded cache with explicit eviction | Caps entry count | Eviction does not mean stopping the plugin; key/value must still be correct | Shared, non-plugin metadata or caches with versioned ownership |

**No option is universally right for every workload.** Choose ownership/lifecycle first; only then choose the collection type and concurrency policy.

## 15. Concurrency: Races Between Cache Hit, Lookup, and Close

If request R1 is looking up a method in a session while R2 issues a plugin stop, the following can happen:

```text
R1: reads session ACTIVE
R2: sets session STOPPING
R2: clears cache and closes loader
R1: attempts findClass from already-closed JAR
R1: ClassNotFoundException or unexpected behavior
```

Java SE 17 `URLClassLoader.close()` explicitly notes: when another thread is loading classes concurrently with `close`, **class loading results are unspecified** per the contract. Therefore, simply using `ConcurrentHashMap` is not enough to protect the lifecycle.

A production design can use:

1. An `ACTIVE / STOPPING / CLOSED` state machine.
2. An active-operations counter or read–write lock.
3. On stop: prevent new operations from starting, wait for already-started operations to finish.
4. Cancel scheduled work, clear caches, and close the loader.
5. Remove from the registry and drop references.

**Do not hold a global lock** across all plugins when you only need to serialize stop/lookup within the same plugin session. For a cached `Method`, if the value has already been returned to a worker, clearing the map **does not revoke the reference the worker is holding**; you must drain workers first.

### Should you use ConcurrentHashMap.computeIfAbsent?

It works when the mapping function has no dangerous side effects and exception behavior is appropriate. `getMethod`/`Class.forName` throw checked exceptions, so you need proper wrapping/synchronization rather than swallowing errors or turning every failure into `null`.

A `ConcurrentHashMap` keyed by `MethodKey` still holds strong keys/values. It fixes **thread safety**, not **classloader retention**, if placed in an infinitely lived host singleton.

## 16. Measure Performance Before Caching

The cost of a cache is not just class lookup time:

- **Cache hit rate**: how many calls actually reuse metadata?
- **Miss cost**: how expensive are reflective lookup/annotation parsing/method handle creation?
- **Memory footprint**: how many `Class<?>`, `Method`, metadata objects, and plugin generations are retained?
- **Invalidation cost**: are entries accurately removed when a plugin reloads?
- **Concurrency**: do lock contention, racing computations, or publication visibility hurt?
- **Cold start**: does cache warm-up create many unnecessary classes/proxies?
- **Lifecycle effects**: does Metaspace grow over 100 reloads even though active plugins remain constant?

If class loading is already cached by the VM, adding another global map for `ClassLoader.loadClass` may only add overhead and leaks. Only optimize after a profiler/JMH or real benchmark proves a bottleneck.

**Do not use `System.nanoTime` to measure a single cold reflection call and conclude "the cache is X times faster"**: JIT, warm-up, GC, and class initialization can skew results dramatically. With real workloads, measure both p95/p99 latency and memory retention across deploy cycles.

## 17. Observing Metaspace and Class Unloading

To evaluate **whether a cache is pinning a loader**, run multiple start/stop/reload cycles with a constant number of active plugins. If class loaders from old generations remain after quiescing, investigate **retaining paths from host static maps, `Method`/`Class<?>`, `ServiceLoader`, TCCL, or queued tasks**. A cache with the wrong lifetime typically shows up as a chain: root → cached value → declaring class → defining loader.

On HotSpot JDK 17 you can inspect `-Xlog:class+unload=info`, `jcmd PID VM.classloader_stats`, JFR, heap dumps, and Metaspace used/committed. A very short example session may finish **without an unload event**: closing/clearing creates the conditions, but the JVM does not guarantee GC/unloading at an exact moment. Never use a single `System.gc()` or `WeakReference` check to conclude a leak.

To prove a cache fix works, compare the same workload across multiple generations before/after, logging cleared cache entries, currently loaded classes, reachable old loaders, and heap **paths to GC roots**. Metaspace committed or RSS may not drop immediately even after metadata has been reclaimed; avoid drawing conclusions from a single metric.

## 18. Nuances of ClassLoader.close and ClassValue.remove

**`URLClassLoader.close()` is not "unload all classes immediately."** JDK 17 documents that already-loaded classes/resources may continue to be usable after close; closing primarily stops new lookups from URLs and closes open resources. If the host still holds a `Method`/instance, the class/loader can remain reachable.

**`ClassValue.remove(clazz)` is not "request unloading `clazz`."** It only removes that specific `ClassValue`'s association for `clazz`. If `clazz` remains reachable through a host map or static field, the loader can stay alive.

**Clearing a `HashMap` does not guarantee all other roots are gone either**: a worker may hold a `Method` in a local variable, a listener registry may retain a plugin object, TCCL may retain the loader, a `ModuleLayer` may be managed by the host, or a service provider cache may still hold a reference.

**Lifecycle cleanup is a design condition that enables GC eligibility, not an API that guarantees unloading.**

## 19. Cache Review Checklist at Plugin Boundaries

- [ ] The cache lives in the right plugin session/generation or has explicit eviction.
- [ ] No static host cache retains plugin `Class<?>`/`Method` unboundedly.
- [ ] Keys properly distinguish runtime `Class<?>` identity; do not use binary name alone when multiple loaders coexist.
- [ ] Hit/miss/size metrics exist to justify whether the cache should exist.
- [ ] `WeakHashMap` is not used blindly when values can reference back to the key/loader.
- [ ] If using `ClassValue`, metadata is genuinely per-class and not stored strongly in another global map.
- [ ] On reload, old-generation caches and negative caches are discarded.
- [ ] Stopping a plugin blocks new tasks, drains active tasks, unregisters listeners/jobs, then clears/closes.
- [ ] `ThreadLocal` is `remove()`d on the proper thread; TCCL is restored in `finally`.
- [ ] `ServiceLoader`/provider registries and reflection/proxy caches are released by owner.
- [ ] Concurrent lookup and close cannot race on `URLClassLoader`.
- [ ] Regression tests cover multiple start/stop/reload cycles and inspect old loader roots.
- [ ] `System.gc()` or a single `WeakReference.get()` is not used to decide unload test pass/fail.
- [ ] The exact JDK's `ClassLoader`, `WeakHashMap`, and `ClassValue` contracts have been consulted.

## 20. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| "Caching by String name is enough." | Runtime type identity also includes the defining loader; the same name can be two distinct classes. |
| "`ClassLoader.loadClass` always redefines the class." | By default it checks already-loaded classes and may return the same `Class<?>`. |
| "`WeakHashMap` uses weak keys so it cannot leak loaders." | Values are strongly held and can point back to the loader key. |
| "`Method` does not retain `Class<?>`." | Reflection metadata is linked to its declaring class; reachability must be considered. |
| "Clearing the map means the loader is unloaded." | It only removes one set of references; JVM GC/unloading is independent. |
| "`URLClassLoader.close` unloads classes immediately." | Closing resources/lookups is not class unloading. |
| "Changing plugin version still keeps a name-keyed cache valid." | A new generation has a new loader/type identity. |
| "`ConcurrentHashMap` fixes classloader leaks." | It fixes thread safety, not key or lifecycle semantics. |
| "A 10-minute TTL is enough when stopping a plugin." | Stopping must invalidate by lifecycle, not wait for a timer while still pinning resources. |
| "`ClassValue` guarantees all plugin references are cleaned up." | It only manages per-class associations; external cache roots still exist. |
| "You must use weak references everywhere to be safe." | A per-session strong cache + explicit cleanup is usually simpler. |
| "No unload event in a short test means a leak." | GC/class unloading is nondeterministic and depends on many roots. |
| "The host holds the parent loader, so the child must stay alive." | Children usually hold the parent; the parent does not by default hold the child. |
| "A plugin having no active requests means threads/lambdas are gone." | Worker queues, callbacks, and `ThreadLocal`s can still retain the loader. |

## 21. Self-Check Exercises

**Q1.** The host has a static `Map<String, Class<?>>` storing `plugin.Worker` from an old version. The plugin has been stopped and the local `loader` variable is set to `null`. Is the old loader eligible for reclamation?

**Answer:** You cannot conclude it is eligible; the static map still holds the plugin's `Class<?>`, which can keep the defining loader reachable. You must remove the entry and any other roots.

**Q2.** Is using `WeakHashMap<ClassLoader, Method>` sufficient because the key is weak?

**Answer:** No. The `Method` value can retain its declaring class → defining loader back to the key; values are strongly held by `WeakHashMap`.

**Q3.** Why does calling `ClassLoader.loadClass` multiple times not necessarily create multiple runtime classes?

**Answer:** By default, the loader checks whether the class is already loaded and returns it if appropriate. A global `Class<?>` cache may be an unnecessary optimization.

**Q4.** Two plugin loaders define the same binary name `plugin.Service`. Is a cache key using only `"plugin.Service"` safe?

**Answer:** Not if the cache is shared. The key lacks loader/runtime class identity, risking returning the wrong class generation.

**Q5.** How does `ClassValue` primarily differ from `static Map<Class<?>, Metadata>`?

**Answer:** `ClassValue` provides an association tied to the runtime class, avoiding retaining per-class data via a self-managed global strong-key map. However, it does not cure other strong roots and you must understand `computeValue` concurrency.

**Q6.** Does `ClassValue.remove(clazz)` unload that class?

**Answer:** No. It only removes `ClassValue`'s associated value; unloading depends on defining loader reachability and VM decisions.

**Q7.** Why must in-flight tasks be drained before `URLClassLoader.close()`?

**Answer:** Concurrent class loading during `close` has unspecified results per the contract; workers still holding plugin instances/metadata also block cleanup.

**Q8.** What is the risk of caching `ClassNotFoundException` or a "name not found" state across plugin versions?

**Answer:** A new artifact/snapshot may contain that name; the old negative cache will serve stale results. Invalidate on generation/source changes.

**Q9.** Using a weak reference to check for a loader leak after one `System.gc()`, is `weak.get() != null` sufficient proof of a leak?

**Answer:** No. GC/unloading has no guaranteed timing; you need GC-root path analysis and multiple lifecycle cycles.

**Q10.** Why are `Same cached Method` true and `Reflection cache misses` 1 in the demo?

**Answer:** Both lookups use the same `MethodKey` within one `PluginSession`, so the first creates the entry and the second receives the exact same `Method` instance.

**Q11.** What is the effect of TCCL still pointing to an old plugin loader on a worker thread after reload?

**Answer:** A live worker can keep the old loader strongly reachable even after the session cache is cleared. Restore TCCL on the worker itself in `finally`.

**Q12.** Should a plugin's `Method`/`MethodHandle` cache live in a host singleton for the entire process?

**Answer:** Only with clear ownership/eviction and without retaining expired plugin generations; by default, a per-plugin session is an easier design to manage.

## 22. Key Takeaways and Official Documentation

**Five core conclusions:**

1. **Scope the cache before optimizing the collection**: strong references in a per-plugin/per-generation cache are normal if cleared on stop with no external roots left behind.
2. **A wrong cache key causes both logic bugs and leaks**: a class name alone cannot distinguish defining loaders, and `Method`/`Class` tokens can pin old loaders.
3. **`WeakHashMap` is not an automatic cure**: strong values can reference back to weak keys via `Class<?>` or `Method`.
4. **`ClassValue` fits per-class metadata**, but does not replace plugin lifecycle or eliminate root references from host caches/threads.
5. **Close + clear + unregister + drain create the opportunity for reclamation**, without guaranteeing immediate class unloading; observe GC roots and Metaspace over multiple cycles.

**Official Java 17 sources:**

- [ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass`, parent delegation.
- [URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): classpath URLs, `close`, and concurrency caveats.
- [WeakHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): weak keys, strong values, and key/value reference cycles.
- [ClassValue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html): `computeValue`, `get`, `remove`.
- [WeakReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): weak reachability.
- [Reference.reachabilityFence](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html): guaranteeing reachability while using a referent.
- [JLS 17 `12.7 — Unloading](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7): unloading conditions by defining loader.
- [JVMS 17 `5 — Loading/Linking](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class identity and loading.
- [Java SE 17 java command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xlog:class+unload` and JVM diagnostics.