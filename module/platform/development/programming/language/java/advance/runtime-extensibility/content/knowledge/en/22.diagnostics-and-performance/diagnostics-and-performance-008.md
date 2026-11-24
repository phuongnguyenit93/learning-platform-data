# Choosing Cache Scope and Detecting Memory Growth Across Repeated Plugin Replacements in Java

## 1. The Problem: Caches Speed Up Calls While Retaining Replaced Plugin Versions

A plugin-capable Java runtime may use a separate class loader per version (*generation*): loading version A, switching to B, and continuing to C without restarting the JVM. Caches cut the cost of reflection, class lookups, serializer construction, config parsing, or provider initialization. However, if a **cache outlives a plugin generation** and retains an object defined by the old loader, classes from the old generation may never be reclaimed.

Two questions must be solved **together**:

1. **Cache scope:** should this data live per request, per plugin generation, per tenant, per class, or host-wide? Does the cache key include *generation identity*? Who performs invalidation when a plugin is replaced?
2. **Memory diagnosis:** after 10, 100, or 1,000 plugin replacements, are references genuinely retaining old loaders, or are you seeing temporary allocation peaks, unrun GC, JIT warmup, JAR caches, or Metaspace metrics that have not yet reflected class unloading?

Do not conclude "memory leak" solely from an upward RSS graph after a few redeploys. Conversely, if the host stores `Class<?>` or plugin instances for every generation inside a `static Map`, that is a **provable strong reference chain** requiring no guesswork about GC behavior.

**Goal:** choose cache scope by ownership and lifecycle, spot caches retaining loaders through either keys or values, reproduce the difference between cleaned and accumulating caches in Java 17, design multi-round plugin-replacement benchmarks with a consistent baseline, and use heap dumps plus class-loader stats to pinpoint root causes.

## 2. Why Can Even a Small Cache Retain an Entire Class Loader?

Suppose a plugin contains `demo.plugin.UpperRule` defined by `URLClassLoader` A. The host stores an instance of that class:

```text
GC Root
  -> HostRegistry static field (defined by host loader)
  -> Map / cache
  -> UpperRule instance (generation A)
  -> Class<UpperRule>
  -> defining ClassLoader A
  -> classes / metadata owned by A
```

A cache can also retain a class or loader **directly**:

```text
GC Root -> static Map<Class<?>, Handler> -> Class defined by A
GC Root -> static Map<PluginId, ClassLoader> -> URLClassLoader A
GC Root -> host serializer cache -> Method / Constructor of A
```

Key takeaways:

- **A host cache object is a GC-root-reachable holder** if the cache is held by a live static field or registry. It can retain a plugin loader even when the plugin itself uses no cache.
- **Holding a class can also retain the loader:** `Class<?>`, reflection metadata, method handles, lambdas, callbacks, proxies, providers, or plugin instances must all be audited—not only fields typed as `ClassLoader`.
- **A static field on a class belonging solely to plugin A does not prove a leak by itself.** If the entire loader A graph has lost all paths from GC roots, an internal cycle of A's own classes and objects can be reclaimed by GC. Look for paths holding A *from outside its graph*.
- **`URLClassLoader.close()` does not force class unloading.** It closes loader-managed resources such as JAR handles; class/loader reachability still depends on live references and GC conditions.
- **Class identity includes the defining loader.** Two classes with the same binary name from loaders A and B are not the same `Class<?>` object. Using class name as the sole key can cause cache collisions across generations in addition to retaining old references.

Mismanaged caches commonly cause two bugs at once: **stale behavior** (returning A's implementation or metadata while B is active) and **retained memory** (A is no longer needed yet remains pinned by the cache).

## 3. Choosing Cache Scope by Owner, Data, and Lifecycle

A cache is only safe when it has an **explicit owner** and a clear **termination event**. The table below lists recommended scopes:

| Cached Item | Typical Appropriate Scope | Key and Invalidation |
|---|---|---|
| Temporary request parse/validation results | Request / task | Discard when request finishes; never put plugin objects into global state |
| Provider instances, reflective methods, plugin-generated adapters | **Plugin generation** | Bind to `pluginId + generation`; clear when generation is retired |
| Per-`Class<?>` metadata | Per class or generation | Consider `ClassValue` / scoped caches; avoid unbounded global `Map<Class<?>, ...>` |
| Serializers / DI factories using plugin schemas | Plugin generation, sometimes tenant + generation | Remove by exact version; close resource-owning objects on retire |
| Pure Java-platform immutable data without class/loader/plugin objects | Host-wide **if genuinely version-independent** | Bounded capacity/TTL; include schema/config version in key if semantics change |
| Mutable per-tenant configuration | Tenant + plugin generation | Key includes tenant, plugin ID, generation/config version; clean up on tenant + gen |
| Computed results keyed by input yet produced by plugin code | Usually generation + input key | Invalidate when code/schema changes to avoid serving A's results to B |
| Per-loader provider/resource discovery results | Loader / generation | Never store old `ServiceLoader`, `Provider`, or `Class<?>` in a host-global cache |
| Files/JARs/indexes genuinely shared across plugins | Host-wide with explicit ref-count/lease | Close when no owners remain; verify permissions and versions |

**Decision rule:** ask "Can a cached value remain valid and avoid retaining the plugin loader after this plugin is retired?" If the answer is **no**, do not let that value live in a host-global cache without a generation key and an eviction path.

Do not pick scope simply because "the data is small" or "we need a quick optimization". A cache with just a handful of entries holding `Class<?>` objects of old plugins is enough to block class unloading. Conversely, a host-wide cache holding immutable strings, numbers, or templates with zero plugin references can be reasonable if bounded and semantically stable across versions.

## 4. Generation Identity: Plugin Name Alone Is Insufficient as a Key

A deployment may have:

```text
pluginId = "pricing"
generation = 41   -> loader A, code A
generation = 42   -> loader B, code B
generation = 43   -> loader C, code C
```

A key of only `"pricing"` cannot distinguish objects belonging to A, B, or C. A key of only `"com.acme.pricing.Rule"` still lacks the defining loader. Even if two generations compile a class with the exact same name, runtime class identity differs when defined by different loaders.

**Code-dependent cache keys should include generation identity**, for example:

```java
record CacheKey(String pluginId, long generation, String resourceName) {}
```

This is an **illustrative snippet**, not a standalone program. The generation ID should be host-assigned and immutable for a given installation; never use `System.identityHashCode(loader)` as a permanent ID because it can collide and carries no business/version meaning.

Two valid designs:

1. **A dedicated cache inside a `PluginScope`/`PluginGeneration` object.** Each scope owns its loader and resources; on retire, call `close()/clear()` on the scope and remove the scope from the host registry. Inside the scope-local cache, simple keys like `"entry"` are safe because generation is represented by the owner.
2. **A shared cache required across generations:** keys must include `pluginId`, `generation`, and any dimensions like tenant/config/schema that affect results. Eviction must filter by the exact generation so retiring A does not delete B's entries.

**Do not assume a cache has "updated" to B merely because a `currentPlugin = B` variable was reassigned.** Every other map entry, callback, future, `ThreadLocal`, and reflection metadata structure can still retain A.

## 5. Plugin Replacement Cycle and When to Clear Caches

A runtime that swaps plugins should have an explicit state machine:

```text
DISCOVERED -> LOADING -> ACTIVE -> DRAINING -> RETIRED -> CLOSED
                             |
                             +--- generation B may become ACTIVE
                                  while A is DRAINING
```

This is a suggested application model, **not a Java enum**.

A sensible sequence when transitioning from A to B:

1. Prepare loader B and **B's own cache** separately; validate code/API/config before publishing.
2. Route new requests to B using an appropriate atomic swap mechanism (such as updating a generation pointer/registry).
3. Mark A as `DRAINING`; reject creating new cache entries/tasks/subscriptions for A from this point on.
4. Wait for or cancel in-flight requests/callbacks on A in a controlled manner. An active request on A may still need A's own cache until it finishes.
5. Unregister listeners, stop schedulers/jobs, and clear worker `ThreadLocal`/TCCL per ownership rules.
6. **Evict generation A's cache** and release resources held by cached values (streams, handles, watchers, lifecycle-bound providers).
7. Remove scope A from the host registry, close its loader, and drop strong references once all valid consumers have finished.
8. Monitor retired loader A using weak probes/metrics if needed, ensuring the monitoring system itself does not hold a strong reference to A.

Do not wipe A's cache too early while in-flight requests are still executing; they may fail or repopulate entries for A after eviction. On the other hand, do not retain A's cache indefinitely merely out of uncertainty over whether requests remain. Production hosts can use **leases/ref-counts**, draining state, and deadlines to determine safe cleanup.

A common race bug:

```text
Thread 1: begins clearing cache A
Thread 2: in-flight old request calls computeIfAbsent(A, ...)
Thread 1: sees empty map and reports "unloaded"
Thread 2: recreates value A in host cache -> retains loader A
```

To prevent this, block writes to scope A first, then drain consumers, and only then clear. Simply calling `Map.clear()` does not form a concurrency-safe retirement protocol.

## 6. Anti-Pattern: Host-Global Cache Retaining Classes and Instances of All Old Versions

The following **bad example** is not a standalone program:

```java
// Class HostRegistry defined by the application class loader.
static final Map<String, Class<?>> COMPILED_TYPES = new HashMap<>();

// Every time a plugin is loaded, the host stores that generation's Class<?>.
COMPILED_TYPES.put(pluginId + "#" + generation, implementationClass);

// When the generation is retired, the code forgets to remove that key.
```

Result: `HostRegistry` lives for the lifetime of the process, so every `Class<?>` of A, B, and C stays pinned in the map. Even if you call `URLClassLoader.close()` on each old loader, the JVM still holds strong references to their classes.

Equally dangerous variants:

- `Map<Class<?>, Serializer>`: both **keys** and **values** can retain plugin loaders.
- `Map<String, MethodHandle>`: values can retain plugin methods and classes.
- `Map<String, Supplier<?>>`: lambdas capture plugin instances without obvious class names in logs.
- `LoadingCache` with unbounded size: missing TTL or max size, or never evicted at retire time.
- `Map<PluginId, List<Callback>>`: callbacks left registered in host registries after switching generations.
- `WeakHashMap<ClassLoader, Scope>`: if the `Scope` value holds the loader used as the key, a strong path from map → value → key prevents the weak key from ever releasing the loader.
- Service provider caches: `ServiceLoader`, `Provider<?>`, listeners, or DI objects retaining provider classes and defining loaders.

The critical clue in a heap dump is a **path from a host-owned root to a retired generation's class/instance**—not every cache in the system should be wiped indiscriminately.

## 7. Runnable Java 17 Example: Generation-Scoped Cache vs. Retaining History

The example creates a host interface, a plugin implementation, and a host manager. On each "plugin swap", the host creates a **new `URLClassLoader` for the same bytecode** to reproduce class/loader lifecycles. Production systems use distinct versioned JARs; the demo reuses the same class file to isolate the *cache scope* factor.

There are two modes:

- **`clean`:** retires the prior generation before keeping the new generation; the host map always holds only one active scope.
- **`leak`:** intentionally omits retiring the prior generation inside the loop; the host registry accumulates 1 → 2 → 3 scopes. Despite sharing the implementation name, each scope owns a fresh loader.
- Both modes clean up remaining scopes in `finally` before the process exits. Thus `leak` **simulates in-flight runtime retention**, rather than intentionally leaving leaked resources after exit.

This demo **measures deterministic entry counts**, not the exact moment the JVM unloads classes.

### 7.1. Directory Structure

```text
cache-scope-demo/
  src/
    api/demo/api/Rule.java
    plugin/demo/plugin/UpperRule.java
    host/demo/app/CacheScopeDemo.java
  build/
    api/
    plugin/
    host/
```

**File `src/api/demo/api/Rule.java`:**

```java
package demo.api;

public interface Rule {
    String apply(String input);
}
```

**File `src/plugin/demo/plugin/UpperRule.java`:**

```java
package demo.plugin;

import demo.api.Rule;
import java.util.Locale;

public final class UpperRule implements Rule {
    @Override
    public String apply(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
```

**File `src/host/demo/app/CacheScopeDemo.java`:**

```java
package demo.app;

import demo.api.Rule;
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class CacheScopeDemo {
    record GenKey(String pluginId, int generation) {}

    private static final Map<GenKey, Scope> SCOPES = new LinkedHashMap<>();

    private static final class Scope implements AutoCloseable {
        private final URLClassLoader loader;
        private final Map<String, Rule> cache = new HashMap<>();

        Scope(Path pluginDirectory) throws IOException {
            this.loader = new URLClassLoader(
                    new URL[] { pluginDirectory.toUri().toURL() },
                    Rule.class.getClassLoader());
        }

        Rule getRule() throws Exception {
            Rule cached = cache.get("entry");
            if (cached != null) {
                return cached;
            }
            Class<?> implementation = Class.forName(
                    "demo.plugin.UpperRule", true, loader);
            Rule result = implementation.asSubclass(Rule.class)
                    .getDeclaredConstructor().newInstance();
            cache.put("entry", result);
            return result;
        }

        boolean ownsRule(Rule rule) {
            return rule.getClass().getClassLoader() == loader;
        }

        int cacheSize() {
            return cache.size();
        }

        @Override
        public void close() throws IOException {
            cache.clear();
            loader.close();
        }
    }

    private static void retire(GenKey key) throws IOException {
        Scope scope = SCOPES.remove(key);
        if (scope != null) {
            scope.close();
        }
    }

    public static void main(String[] args) throws Exception {
        String mode = args.length == 0 ? "clean" : args[0];
        if (!mode.equals("clean") && !mode.equals("leak")) {
            throw new IllegalArgumentException("Use clean or leak");
        }
        System.out.println("mode=" + mode);
        Path pluginDirectory = Path.of("build/plugin").toAbsolutePath();
        GenKey prior = null;

        try {
            for (int i = 1; i <= 3; i++) {
                if (mode.equals("clean") && prior != null) {
                    retire(prior);
                }
                GenKey key = new GenKey("upper", i);
                Scope scope = new Scope(pluginDirectory);
                SCOPES.put(key, scope);
                Rule rule = scope.getRule();
                int entries = SCOPES.values().stream()
                        .mapToInt(Scope::cacheSize).sum();
                System.out.println("round-" + i
                        + ":scopes=" + SCOPES.size()
                        + ",cache-entries=" + entries
                        + ",result=" + rule.apply("java")
                        + ",child-defined=" + scope.ownsRule(rule));
                prior = key;
            }
            System.out.println("retired-left=" + (SCOPES.size() - 1));
        } finally {
            for (GenKey key : List.copyOf(SCOPES.keySet())) {
                retire(key);
            }
            System.out.println("after-close=" + SCOPES.size());
        }
    }
}
```

**Key mechanisms to note:**

1. `Rule` is compiled onto the host's classpath; child loaders inherit that exact interface via the parent, avoiding class identity mismatches between host and plugin.
2. `pluginDirectory` is **not** on the runtime host classpath. Accidentally adding `build/plugin` to `-cp` would let the application loader find the plugin implementation via delegation, breaking the child boundary test.
3. Each `new Scope(pluginDirectory)` creates a new `URLClassLoader`, allowing the same class name to be defined separately per generation. `scope.ownsRule(rule)` verifies this.
4. `Scope.cache` holds implementation instances, giving the scope clear ownership. Host `SCOPES` may retain only active/draining scopes.
5. In `clean` mode, `retire(prior)` removes the old scope from the host map and clears its cache before closing the loader.
6. In `leak` mode, the host map accumulates old scopes; this is a retained reference strong enough to **prevent old loader graphs from becoming unreachable during the simulated run**.
7. The `finally` block cleans up the map at the end of the demo even if an error occurs in the loop. In production, teardown must handle each scope's exceptions independently so a close failure on one loader does not block cleaning up other scopes.
8. `LinkedHashMap`/`HashMap` here are intentionally **not thread-safe** to keep the demo easy to read. Real concurrent hosts need explicit leases, locks, and `DRAINING`/`RETIRED` states; do not copy this code verbatim into a concurrent system.

### 7.2. Compile and Run on Windows PowerShell

From inside `cache-scope-demo/`, using JDK 17 or newer:

```powershell
New-Item -ItemType Directory -Force -Path build/api,build/plugin,build/host | Out-Null
javac --release 17 -d build/api src/api/demo/api/Rule.java
javac --release 17 -cp build/api -d build/plugin src/plugin/demo/plugin/UpperRule.java
javac --release 17 -cp build/api -d build/host src/host/demo/app/CacheScopeDemo.java
java -cp "build/api;build/host" demo.app.CacheScopeDemo clean
java -cp "build/api;build/host" demo.app.CacheScopeDemo leak
```

### 7.3. Compile and Run on Linux/macOS

```bash
mkdir -p build/api build/plugin build/host
javac --release 17 -d build/api src/api/demo/api/Rule.java
javac --release 17 -cp build/api -d build/plugin src/plugin/demo/plugin/UpperRule.java
javac --release 17 -cp build/api -d build/host src/host/demo/app/CacheScopeDemo.java
java -cp "build/api:build/host" demo.app.CacheScopeDemo clean
java -cp "build/api:build/host" demo.app.CacheScopeDemo leak
```

### 7.4. Exact Stdout, Clean Mode

```text
mode=clean
round-1:scopes=1,cache-entries=1,result=JAVA,child-defined=true
round-2:scopes=1,cache-entries=1,result=JAVA,child-defined=true
round-3:scopes=1,cache-entries=1,result=JAVA,child-defined=true
retired-left=0
after-close=0
```

### 7.5. Exact Stdout, Leak Mode

```text
mode=leak
round-1:scopes=1,cache-entries=1,result=JAVA,child-defined=true
round-2:scopes=2,cache-entries=2,result=JAVA,child-defined=true
round-3:scopes=3,cache-entries=3,result=JAVA,child-defined=true
retired-left=2
after-close=0
```

Both outputs were verified by compiling with `javac --release 17` and running both modes. The results prove **how many scopes the registry/caches retain** and that implementations come from child loaders at runtime; they **do not prove how many classes GC unloaded**.

In particular, `after-close=0` only confirms the host map was cleared in the demo; stack/JIT local variables, GC timing, and references from other components can still influence class unloading. Do not write a unit test asserting "`close()` makes Metaspace drop immediately" based on this example.

## 8. Reading the Experiment: Retention, Eviction, and Memory Leaks Are Three Different Things

In `clean` mode, the registry always holds exactly one scope when printing metrics; in `leak` mode, the registry holds 3 scopes and 3 entries by round 3. The retention chain is:

```text
CacheScopeDemo.class
  -> static SCOPES
  -> LinkedHashMap entry (GenKey of upper#1)
  -> Scope generation 1
  -> Scope.loader (URLClassLoader #1)
  -> Scope.cache["entry"]
  -> UpperRule instance of generation 1
```

An identical structure exists for generation 2. These are **strong references still reachable from the host**—you do not need to run GC to know the objects remain referenced.

However:

- **Intentional retention:** an old generation may legitimately be `DRAINING` due to in-flight requests, so keeping its cache briefly is correct. Define a grace period/lease before calling it a leak.
- **Proper eviction:** once no consumer uses the old generation, `retire` removes map entries, clears caches, and closes resources. This is deterministic behavior you can assert.
- **True leak:** after a generation is `RETIRED`/`CLOSED` and its grace window has elapsed, the host still retains entries/loaders via one or more paths, and that accumulation grows across repeated replacements.
- **Not yet GC'd is not a leak:** even with a clean registry, the JVM may not have unloaded classes or returned Metaspace/native pages to the OS yet.
- **GC collecting a loader does not guarantee the app uses the right cache:** stale pure-`String`/DTO cache values can still be served to a new generation. Write separate correctness tests for resource ownership.

**Measure two separate things:** (1) whether references and cache entries obey lifecycle rules; (2) whether heap/Metaspace/native memory shows abnormal growth across many swaps and comparable GC opportunities.

## 9. TTL, LRU, WeakHashMap, ClassValue: Which Technique to Pick?

### 9.1. Capacity- and Time-Bounded Caches

LRU/maximum size or TTL is helpful to prevent unbounded growth for request results or plain data. Yet **TTL does not replace retirement**: a callback/class from plugin A sitting in a cache for 30 minutes can pin loader A for all 30 minutes even when policy expects 1 minute. TTL expiration may also run lazily on access or via a separate sweep depending on implementation.

For caches storing plugin objects, prioritize **explicit per-generation eviction**, using size/TTL as a secondary defense. If cached values own resources (streams, scheduled tasks, closeable adapters), eviction must also invoke their close/dispose methods rather than merely deleting the map entry.

### 9.2. Weak Keys Are Not a Default Fix

Look at this anti-pattern:

```java
// Illustrates the risk only, not a standalone code snippet.
WeakHashMap<ClassLoader, PluginScope> registry = new WeakHashMap<>();
registry.put(pluginLoader, new PluginScope(pluginLoader));
```

If the `PluginScope` value holds a strong reference to `pluginLoader`, there is a `registry → value → key` chain, so weak keys cannot auto-expire. Even when weak keys/values fit a narrow use case, they **do not** run resource/registration cleanup, impose no GC deadline, and never replace owner-defined `close()`.

### 9.3. `ClassValue` for Per-Class Metadata

Java 17 provides `ClassValue<T>` to associate computed values with each `Class<?>`. For metadata depending solely on a type:

```java
// Illustrative: values are bound to the type instead of a host-global Map<Class<?>,...>.
private static final ClassValue<String> BINARY_NAMES = new ClassValue<>() {
    @Override
    protected String computeValue(Class<?> type) {
        return type.getName();
    }
};
```

This snippet must sit inside a class. It caches only a `String` class name; a real system may store a plan structure with clear ownership. `ClassValue` avoids many bugs from hand-rolled host maps keyed by `Class<?>`, yet using `ClassValue` does not guarantee a loader will unload. Other references, resource/closure-holding values, static registries, `ThreadLocal`s, and callbacks still require cleanup. `ClassValue.remove(type)` removes one association; it does not "unload a class from the JVM".

### 9.4. Caches Inside the Plugin Scope

This is the best default for factories/reflection/providers sharing the generation's lifetime:

```text
Host plugin registry
  -> PluginScope generation 42
     -> Loader42
     -> Cache42
     -> subscriptions42
     -> worker/timer handles42

retire(42):
  stop new work -> drain -> unregister -> Cache42.clear()
  -> close resources -> remove PluginScope42 from host registry
```

When the owner and scope share the same lifetime, auditing becomes straightforward. If a cache is shared across multiple plugins, define an explicit sharing policy so it does not automatically inherit the lifetime of the longest-lived generation.

## 10. Scope Selection Also Depends on Tenant, Request, and Schema

Four levels are commonly conflated:

1. **Request-scoped:** temporary objects, transactions, request contexts. Never retain them in static caches after the request completes. If a request executes on plugin A, release A's lease when the task finishes.
2. **Tenant-scoped:** same plugin code, yet tenant configuration, permissions, schema, or data differ. Keying by `pluginId + generation` is insufficient if values depend on the tenant. Unpartitioned caches risk **data leaks**, not only memory leaks.
3. **Plugin-generation-scoped:** classes, method handles, providers, adapters, compiled rules, serialization plans. Derive code identity from generation, not only binary class name.
4. **Host-wide:** genuinely shared data holding no class/loader/plugin instances. Global caches still need bounds/metrics/expiration because input cardinality can be unbounded.

A sample key might be:

```java
record Key(String tenantId, String pluginId,
           long generation, String schemaVersion, String item) {}
```

This is an **illustrative snippet**. Do not force a multi-field key onto every cache when fields are irrelevant; the goal is to express **the exact factors that alter semantics/values** while avoiding holding strong `ClassLoader` or `Class<?>` keys outside the required owner scope.

When plugin B replaces A under an identical contract, the host may **explicitly migrate a pure-data cache** to B after compatibility checks. Never migrate A's runtime objects, `Class<?>`, method handles, classloader-bound proxies, or provider instances by default.

## 11. Measuring Memory Across Many Plugin Replacements Under Matching Conditions

To determine whether memory truly grows across reloads, run controlled tests instead of casual observation:

**Preparation:** a test JVM with a steady workload, fixed JDK/GC flags, identified plugin generations, identical concurrency/queue depth, and logs identifying loaders. Warm up the runtime before recording the baseline to reduce noise from framework class loading and JIT.

**On each test cycle** (e.g., A→B, B→C, ...):

1. Create the new generation; measure newly created cache entries and classes/loaders.
2. Shift new traffic to the new generation.
3. Stop new traffic to the old generation and wait for in-flight consumers to finish.
4. Retire the old generation: unregister callbacks, cancel tasks, clean up TCCL/`ThreadLocal`, clear generation-scoped caches, close the loader, and remove the registry entry.
5. After an **equivalent stabilization window** between rounds, snapshot remaining active/draining/retired scopes, cache entries, loader counts, and memory. If your staging procedure triggers GC, record exactly when; never rely on a single `System.gc()` as a guarantee.
6. Repeat enough rounds to see a trend, recording both peaks and **post-collection baselines** when actual GC data is available.

Metrics to compare:

| Metric | Explanation | What to Distinguish |
|---|---|---|
| Active generation count | Valid plugin versions currently serving | May exceed 1 during rolling replacement |
| Retired generation references | Scopes/caches/registrations still holding retired versions | Should drop to 0 after the grace period by design |
| Cache entries/weight per generation | Size of caches still reachable | Bounded size/TTL does not replace eviction on retire |
| Current loaded class count | Classes currently loaded in the JVM | Growth from frameworks/JIT/new features is not automatically a leak |
| Total loaded / total unloaded classes | Cumulative JVM counters | Total loaded rises monotonically by definition; never expect it to fall |
| Heap used after comparable GC opportunities | Object payloads and registries | Allocation peaks differ from retained heap floors |
| Metaspace used/committed | Class metadata and related structures | Used, committed, and reserved differ; not always returned immediately to OS |
| RSS / native memory | Process memory beyond heap plus resident heap | Can grow from direct buffers, code cache, threads/JNI |
| Class unload events | Whether the JVM reports classes being unloaded | Absence of events in a short window does not prove a leak |

**Inference pattern:** if after 100 cycles the app always has 1 active generation yet the cache/loader registry still retains 100 generations and Metaspace climbs steadily, that is solid evidence to investigate. If the registry holds only 1 scope and loaded class count stays flat over time while RSS still rises, inspect heap/native allocations and fragmentation rather than jumping straight to a class-loader leak conclusion.

## 12. Monitoring via JMX/MXBeans from Java

Java 17 provides `ClassLoadingMXBean` and `MemoryPoolMXBean` via `ManagementFactory`. An application can periodically record:

```java
// Illustrative snippet placed in a class and invoked at snapshot time.
var classStats = java.lang.management.ManagementFactory
        .getClassLoadingMXBean();
int currentLoaded = classStats.getLoadedClassCount();
long everLoaded = classStats.getTotalLoadedClassCount();
long everUnloaded = classStats.getUnloadedClassCount();

for (var pool : java.lang.management.ManagementFactory
        .getMemoryPoolMXBeans()) {
    if (pool.getType() == java.lang.management.MemoryType.NON_HEAP
            && pool.getName().contains("Metaspace")) {
        var usage = pool.getUsage();
        if (usage != null) {
            long used = usage.getUsed();
            long committed = usage.getCommitted();
            // Log used/committed + timestamp + plugin generation ID.
        }
    }
}
```

This is **illustrative code**, not a standalone program and prints no fixed stdout. Pool names depend on the JVM/vendor; this snippet picks a pool containing `Metaspace` on typical HotSpot builds, which may not exist identically on other JVMs. Record metadata such as Java version, collector, process ID, and test configuration.

Valid comparisons:

- `getLoadedClassCount()` is the **current count**, not the count of plugin-owned classes. Distinguishing plugin A vs. B requires instrumenting the registry or inspecting classloader-specific data.
- `getTotalLoadedClassCount()` and `getUnloadedClassCount()` are **cumulative totals since JVM startup**; do not treat rising total loaded counts as a leak.
- A `Metaspace` pool has distinct `used` and `committed` figures; memory returned to the OS also depends on the runtime/GC and may not mirror every fluctuation.
- Tie samples to **post-retire timestamps** and GC events to compare across rounds. A sample taken at an allocation peak does not represent steady state.
- Do not enforce rigid thresholds like "after 3 swaps heap must equal the exact baseline byte-for-byte". JIT, class initialization, framework caches, and async cleanup create legitimate variance.

Security/cost note: metrics are less sensitive than heap dumps yet can still expose plugin names, classes, tenants, or internal paths. Log approved generation IDs and bound metric label cardinality.

## 13. Deep Investigation with `jcmd`, GC Logs, and Native Memory Tracking

On HotSpot/JDK 17 in attach-permitted environments, `jcmd` complements in-host counters:

```bash
# Replace <pid> with the PID of the Java process to inspect.
jcmd <pid> VM.classloader_stats
jcmd <pid> GC.class_histogram
jcmd <pid> GC.heap_info
jcmd <pid> GC.heap_dump /path/to/plugin-retention.hprof
```

- `VM.classloader_stats` reports class loader / class-loader data statistics; it does not automatically tell you which cache retains which loader.
- `GC.class_histogram` reports heap object statistics and can have high impact per tool docs. Do not run it continuously in production without consideration.
- `GC.heap_dump` writes an HPROF file, which can consume disk, cause pauses, and by default request a full GC. Heap dumps may contain credentials, customer data, and sensitive payloads: enforce approval, encryption/secure storage, and post-analysis deletion.
- `GC.heap_info` shows the heap picture and excludes full native/JNI allocations.
- In tests launching a JVM with matching logging, you can observe class unloading:

```bash
java -Xlog:class+unload=info -cp "build/api:build/host" demo.app.CacheScopeDemo clean
```

This command illustrates Linux/macOS usage and produces output that varies with GC and timing; it has **no fixed stdout**. On Windows, replace the classpath separator with `;`. Seeing no unload logs in a short demo does not prove a cache still pins the loader.

### Native Memory Tracking (NMT)

When RSS rises while heap/Metaspace metrics do not explain it, NMT helps categorize JVM-native allocations. On HotSpot, NMT must be enabled at startup:

```bash
java -XX:NativeMemoryTracking=summary -cp "build/api:build/host" demo.app.CacheScopeDemo clean
```

While a test process is actually alive (the demo above exits quickly), the following commands apply in a **separate long-lived test workflow**:

```bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
```

NMT incurs overhead and does not track all third-party/JNI native allocations. The sequence above is **not** meant to attach to an already exited demo; it requires an active host process started with NMT enabled. `summary.diff` compares against the NMT baseline, not "post-GC Java heap memory". Cross-check NMT data with host metrics, GC/JFR, and profilers to avoid misattributing growth to plugin loaders.

## 14. Using Heap Dumps to Find Path to GC Roots

When metrics show `RETIRED` generations still have live class loaders, the decisive diagnostic step is the **reference path**:

1. Pick the exact retired plugin ID/generation; do not confuse a newly active loader with an old one.
2. In Eclipse Memory Analyzer (MAT) or an equivalent profiler, locate `java.net.URLClassLoader`/custom `PluginClassLoader` or a `Class<?>` defined by that loader.
3. Run **Path to GC Roots** and inspect strong references first; depending on the tool, filter out weak/soft/phantom-only paths to see strong owners.
4. Trace each edge back to host classes, static fields, cache keys/values, threads, executor queues, listeners, or DI containers. Never stop at an internal `HashMap$Node` without identifying which registry owns it.
5. If you see `HostRegistry → Map → Class<PluginType>`, fix eviction in the map's owner. If you see `Thread → ThreadLocalMap.value → PluginContext`, clean up context on that worker. If you see `EventBus → listeners → callback`, unregister the generation's subscriptions.
6. After fixing, repeat the plugin replacement sequence and compare retained paths under the same scenario. A loader may have **multiple independent strong paths**; removing one path only reveals the next.

Example cache retained path:

```text
GC Root: HostCache.class
  -> HostCache.ACTIVE_AND_OLD
  -> ConcurrentHashMap$Node.value
  -> PluginScope(upper, generation=12)
  -> Scope.cache["serializer"]
  -> PluginSerializer instance
  -> Class<PluginSerializer> defined by Loader12
```

The actionable fix message is not "GC stopped working", but: **HostCache still retains generation 12 after `RETIRED`**. Locate where `retire(12)` should have run, inspect exceptions/races, and add a regression test.

If the heap analyzer shows the loader is held by a **thread stack** of a still-running request A, that can be valid temporary retention. Concluding a leak requires knowing drain SLAs, task state, and whether that path persists beyond a reasonable deadline.

## 15. `WeakReference` to Observe Old Loaders Without Forcing GC

The host can keep a `WeakReference<ClassLoader>` *probe* for loader A when releasing strong references:

```java
// Illustrative pattern, not a standalone program.
java.lang.ref.WeakReference<ClassLoader> probe =
        new java.lang.ref.WeakReference<>(loaderA);
// After retiring: must not retain loaderA in static registries,
// callbacks, tasks, class metadata caches, or a monitor strong reference.
// probe.get() == null may appear once the JVM actually collects the referent.
```

**Do not** treat `probe.get() != null` immediately after `close()` as proof of a bug: the JVM may not have run GC, JIT/stack locals may remain live, or the runtime may legitimately hold the loader briefly. `System.gc()` is only a hint and creates no mandatory collection deadline. On the other hand, `probe.get() == null` is a useful signal that the referent was collected at the observation point, though it **does not** prove every native resource, file handle, or plugin callback was closed cleanly.

When tracking hundreds of generations, keep a list of **weak references and plain metadata** (`pluginId`, `generation`, retirement timestamp)—never store strong `Class<?>` or loader references in a metrics registry. A "leak detector" storing `Map<GenerationId, ClassLoader>` to check later can itself cause the very leak it aims to diagnose.

You can use a `ReferenceQueue` to receive notifications when referents become eligible/cleared per reference semantics, though timing still depends on GC; never use a fixed number of seconds as the primary criterion. Stronger assertions check **empty owner maps, unsubscribed callbacks, restored TCCL, and loader no longer registered**.

## 16. When Caches Are Cleaned Up Yet Memory Still Grows

Not all post-reload memory growth comes from caches. Expand the investigation based on the observed signal:

| Symptom After Many Cycles | Source to Investigate | How to Verify |
|---|---|---|
| Retired scope count grows with generations | Broken registry/cache lifetime | Count scopes/entries per generation; inspect owner maps |
| Heap floor rises, retained path from host static → plugin object | Cache/DI/callback holding strong reference | MAT Path to GC Roots; fix eviction/unregistration |
| Heap floor rises, root from thread | `ThreadLocal`, TCCL, pending tasks, target threads | Thread dump + heap dump; clean up on the exact workers |
| Metaspace and loaded classes rise, retired loaders stay reachable | Class metadata / loader retention | Classloader stats, heap paths, class unload events |
| RSS rises while Java heap stays flat | Native/direct buffers, code cache, thread stacks, mmap/JAR/JNI | NMT where applicable, OS metrics, buffer pool metrics |
| Class unloading occurs yet RSS does not drop immediately | Native allocator / committed vs. resident | Distinguish used/committed/RSS; monitor over longer windows |
| Memory scales with workload, not reload count | Request/tenant caches, queues, traffic | Compare equal workloads and cache hit/eviction rates |
| Appears only under concurrency | Race between generation drain and `computeIfAbsent` | Concurrent repro; guard state and write gates |
| JAR files cannot be deleted on Windows | Loader / JAR streams still open | Close resources properly; inspect open file handles |
| CPU/latency climbs after each reload | Cache thrashing, lingering old listeners/tasks running | Event counts, worker/task queues, allocation profiles |

**Proper analysis identifies which memory pool is growing:** object heap, metaspace/class metadata, JVM-native allocator, direct buffers, code cache, or thread stacks. Only then can you pick the right diagnostic tool. "Task Manager graph going up" does not point to a specific reference path.

## 17. Regression Testing: Deterministic Ownership First, GC Trends Second

A solid test suite should have two layers.

### 17.1. Unit/Integration Tests with Deterministic Assertions

- After `install(A)`, cache scope A exists and all values/classes belong to generation A.
- After `install(B)` + `retire(A)`, the host registry no longer contains key A; cache A is cleared and `AutoCloseable` values are closed exactly once.
- B continues working normally; evicting A does not remove B.
- No new A requests are accepted after `DRAINING`; in-flight tasks complete or are canceled per contract.
- Two classes with the same binary name from loaders A and B are never conflated by a `String className` cache key.
- Tenant-dimensioned caches never return another tenant's values.
- Callbacks, timers, listeners, executor tasks, TCCL, and `ThreadLocal`s are cleaned up per generation.
- Inject an exception into one cleanup step; remaining independent steps still execute rather than falsely claiming retirement succeeded.
- Test concurrency between `retire(A)` and `cache.get(A, key)`; disallow recreating cache A once the scope is closing.

The section 7 demo code is an entry-level test: `clean` mode yields `retired-left=0`, while `leak` mode yields `retired-left=2` after three installs. These assertions **do not depend on GC**.

### 17.2. Multi-Round Plugin Replacement Soak Tests

In staging:

1. Warm up the host and record a baseline once the application stabilizes.
2. Run 50–200 install/retire cycles under realistic workload; on each cycle record active/retired scope counts, cache size/weight, process memory, classloader/class counters, and GC events.
3. After each batch of cycles, verify owner maps are clean; take memory snapshots at **points with comparable measurement conditions**, avoiding comparing allocation peaks with post-GC lows.
4. Track trends of retained loader/class counts across multiple suitable GC opportunities rather than demanding `WeakReference.get()==null` by a tight deadline.
5. If an upward trend appears, capture a heap dump, trace the path from GC roots, fix the cache owner, and rerun the exact test.
6. Measure latency and cache hit rates after adding eviction to confirm you have not accidentally forced overly frequent plugin re-initialization.

**Never automatically declare a leak just because "Metaspace did not return to the exact baseline byte-for-byte".** GC/class unloading may lag; some new host/framework classes are loaded once and validly retained. What matters are *retired generation counts/retaining paths* and memory trends across equivalent phases.

## 18. Common Design Mistakes

1. **Process-wide cache keyed only by class name.** Two generations share a name yet have distinct class identities and semantics.
2. **Omitting generation from owners and metrics.** Cannot tell retired version A's cache apart from active version B's.
3. **Using TTL instead of teardown.** Loader A stays pinned for the entire TTL, or caches are never swept while idle.
4. **Using weak keys and assuming leaks are solved.** Values can point back to keys or loaders.
5. **Storing plugin instances in cache values owned by a host singleton.** Host roots pin old loaders even after `close()`.
6. **Tracking only total loaded classes.** That is a cumulative counter, not currently retained classes.
7. **Reading RSS/Metaspace peaks as retained memory.** Distinguish peak, used, committed, post-GC, and OS accounting.
8. **Evaluating after a single reload.** Multiple cycles and a steady workload are needed.
9. **Creating strong references inside the leak detector itself.** Metrics/registries can become the culprit.
10. **Closing the class loader before draining tasks.** Tasks from A still needing lazy classes or resources can fail.
11. **Clearing the cache while letting old tasks call `computeIfAbsent` again.** Cache A can reappear after teardown.
12. **Wiping all host-wide caches when retiring A.** Breaks B and causes cache stampedes; evict only the right owner.
13. **Measuring on one JDK/collector and extrapolating identically to every JVM.** GC, NMT, `MemoryPool` names, and tuning are runtime-dependent.
14. **Taking production heap dumps without controlling sensitive data.** HPROF files can contain all live objects and secrets.
15. **Treating `URLClassLoader.close()` as `unloadClass()`.** The API makes no such promise.
16. **Using `ClassValue` while forgetting to clean up threads/callbacks.** Fixing one cache type does not eliminate other retention paths.
17. **Swapping the current generation while ignoring rollback.** If B proves invalid, A may need to stay briefly, yet `ACTIVE`/`ROLLBACK` state and release deadlines must be explicit.
18. **Explaining native memory growth with a heap dump without checking JNI/direct buffers.** Different memory pools require different tools.

## 19. Architecture Checklist and Conclusion

Before shipping runtime extensibility, walk through this checklist:

- [ ] Every plugin installation has immutable `pluginId` and `generationId`; defining loaders are identified in logs.
- [ ] Caches holding plugin classes, providers, serializers, or metadata are generation-scoped, or use global keys + equivalent eviction contracts.
- [ ] Host-global caches hold only genuinely code/loader-independent data, or are properly partitioned by tenant/version.
- [ ] `ACTIVE` → `DRAINING` → `RETIRED` is defined; new cache writes are blocked once an old generation begins retiring.
- [ ] Callbacks and in-flight requests are stopped/drained before clearing caches and closing loaders.
- [ ] Owners clear entries, close cached values/resources, and remove registration handles, `ThreadLocal`s, and TCCL/threads cleanly.
- [ ] Metrics track **cache entries/weight and retired generation counts**, not only memory MB.
- [ ] JMX/GC/NMT/profilers are configured per environment and permissions; memory is compared at equivalent lifecycle points.
- [ ] A heap analyzer runbook exists to trace **Path to GC Roots** when retired loaders stay reachable.
- [ ] Multi-cycle replacement soak tests + fault injection + race tests do not rely on a single `System.gc()`.
- [ ] Leak-detector metrics hold only plain metadata and weak probes, never strong references to old loaders.
- [ ] Post-eviction performance—cache hit rate, recomputation cost, and new-generation latency—has been verified.

**Key takeaway:** *Cache scope is an ownership and lifecycle decision, not merely a data-structure choice.* Caches holding `Class<?>` or plugin instances must be bound to a **plugin generation** and cleared when that generation retires. To detect memory growth across repeated plugin swaps, combine **deterministic reference counts and eviction assertions**, **multi-round trends of heap/Metaspace/classloaders**, and **retaining paths from GC roots**. Never rely on `URLClassLoader.close()`, weak references, or a single GC call as sole proof.

**Official Java 17 Documentation:** [ClassLoadingMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html), [MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html), [ClassValue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html), [URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html), [jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html), [java launcher / NMT options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html), [Java 17 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/17/troubleshoot/).
