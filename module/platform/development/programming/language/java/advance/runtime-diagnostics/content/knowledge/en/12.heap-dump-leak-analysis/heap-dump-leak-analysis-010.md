# 12.10. Identifying Collections, Caches, Listeners, ThreadLocals, or Class Loaders Retaining Data

## 1. Objectives and Diagnostic Questions

When heap usage climbs steadily, it is not enough to know **which class occupies the most memory**; you must pinpoint **which reference chain keeps objects alive past their business lifecycle**. Five common culprits are collections, caches, listeners, `ThreadLocal`, and class loaders. They share one trait: a longer-lived object holds strong references to data from a finished task, request, session, or deployment.

After this lesson, you will be able to:

- Read a heap dump from retained object → container/registry → GC root, distinguishing **shallow heap**, **retained heap**, **incoming references**, and **dominator**.
- Recognize five data-retention patterns by their reference graph structure, symptoms, evidence, and ownership lifecycle.
- Distinguish "many objects present" from a **true memory leak**, avoiding blaming every large cache or surviving class loader as a bug.
- Use Eclipse Memory Analyzer (MAT) to inspect retained size, paths to GC roots, threads, and class loaders, and compare snapshots before and after cleanup.
- Specify fixes at the **reference creation and release points**, verifying that expired data becomes eligible for collection.

The scope is **Java heap dumps and object retention**. Most class metadata lives in Metaspace (native memory), so a heap dump can reveal references pinning a loader without reflecting total Metaspace bytes.

## 2. Principle: GC Collects by Reachability, Not by "Done Using It"

GC marks objects still reachable from **GC roots**, such as stack references on active threads, static fields of live classes, and JVM/native references registered as roots. If an object with zero remaining business value stays reachable from a root via a chain of strong references, GC cannot guess that the developer meant to release it.

Example retention flow:

~~~text
GC Root
  -> application singleton / live class
  -> static Map<String, Report>
  -> HashMap table / Node
  -> value Report
  -> List<ReportRow>
  -> byte[] or String[] / many small objects
~~~

Suppose a report is used for a single request yet placed into a map with no eviction policy. Ending the request does not alter the reference path from the singleton to the report. That is **retention beyond the intended lifecycle**. A heap dump proves the retention path at snapshot time; concluding a "leak" further requires evidence that the data **ought to have expired** and keeps accumulating over time.

### Four concepts you must distinguish

| Concept | Meaning | Proper usage |
| --- | --- | --- |
| **Shallow heap** | Memory of the object itself (header and fields; for arrays, includes array elements) | An `ArrayList` has tiny shallow size even when holding millions of entries |
| **Retained heap** | Memory of the object plus any other objects that would become unreachable if it were removed from the graph (per MAT's model) | Locates where an entire cluster of data is "held" |
| **Dominator** | Object X dominates Y when every path from root to Y passes through X | `Dominator Tree` locates accumulation points; dominator edges are not necessarily literal field references |
| **Path to GC Roots** | One or more reference chains walking backward from a suspect to a root | Explains **who** holds it; check additional paths if multiple owners exist |

**Note:** a large object can be referenced from multiple places, so individual owners' retained sizes do not simply sum to the object's size. "Shortest path to GC root" offers a clue, not necessarily the sole or sufficient proof of ownership. Inspect incoming references and multiple paths when needed.

## 3. Investigation Workflow from Symptom to Root Cause

### Step 1: Confirm memory growth

Observe the same workload type across several cycles: **post-GC heap used**, live-object growth rate, GC frequency/pauses, active requests/sessions, cache entry counts, thread counts, and deployments. High heap right after allocation is not automatically a leak; the JVM may keep heap **committed** for reuse even after live objects drop.

Example: after 10,000 requests and once every request finishes, live `ReportContext` count climbs from 10 to 10,010 and `Listener` count grows in lockstep. That pattern warrants investigation far more than a single snapshot with thousands of objects serving 10,000 **genuinely active** requests.

### Step 2: Pick the right moment to take a heap dump

First confirm the real JVM PID. On HotSpot/JDK supporting `jcmd`:

~~~bash
# Replace <pid> with the actual PID; run on the host/namespace with JVM access
jcmd <pid> VM.version
jcmd <pid> GC.heap_info
jcmd <pid> GC.heap_dump /path/to/heap-before.hprof
~~~

`GC.heap_dump` writes an HPROF heap file; on modern HotSpot builds, it requests a full GC by default unless `-all` is passed. Dumping can cause pauses, consume I/O/disk, and capture sensitive application data. Choose an appropriate environment, window, and access controls; use staging or reproducible fixtures whenever possible. **Do not pass `-all` when hunting for live-object leaks unless you understand it includes unreachable objects**; otherwise you may mistake "uncollected garbage" for retained data.

Capture the snapshot in the target state: after suspect workloads finish while the app remains running; for comparisons, match JDK, config, load, and relative timing. Two dumps are supporting evidence and cannot prove a leak on their own when workloads differ.

### Step 3: Open the heap dump in Eclipse Memory Analyzer

1. **Overview / Leak Suspects Report**: use as a starting point; the report is heuristic, not a verdict.
2. **Histogram**: inspect instance counts and shallow size by class; group by package or **class loader** to spot old deployments.
3. **Dominator Tree / Top Consumers**: find object groups holding high retained heap; drill down to identify the accumulating container or structure.
4. **Incoming References / Path to GC Roots**: from an instance surviving past its lifecycle, trace back to a root; choose exclude weak/soft/phantom references to focus on strong retention paths.
5. **Object Attributes / Collection Analysis**: inspect `size`, backing arrays, `Map.Node`, keys, cache entries, thread names, thread-local values, and callback/registry owners.
6. **Class Loader Explorer / Duplicate Classes**: check which loader defined a class, live instance counts, and whether old loaders survive undeploy/redeploy.

Your findings should form a concrete chain, e.g.: "`ApplicationRegistry.listeners` (app singleton) still holds an `ExportListener` from a canceled session; the listener holds `SessionContext`; ~18 MB under that context is no longer in use." A histogram screen showing only large `byte[]` is **not enough**.

## 4. Identifying Signatures of the Five Retention Groups

| Group | Typical reference path | Suspicious signs | Verification questions |
| --- | --- | --- | --- |
| Collection | `static List/Map/Set -> backing array/entry -> value` | `size` grows with finished requests/users/files; many similar entries | Who adds, when is it removed, how long does the collection live? |
| Cache | `singleton cache -> entry -> key/value` | No size/weight/TTL limit; values are huge graphs; keys never evicted | Is key cardinality unbounded? Are eviction/expiry actually working? |
| Listener | `event bus/registry -> callback -> captured owner/payload` | Listener registered per screen/session creation without unregister | Is there lifecycle-tied cleanup? Are real consumers still active? |
| `ThreadLocal` | `live pooled Thread -> threadLocals -> Entry.value` | Request ended yet context sits on long-lived worker threads | Is `remove()` called in `finally` on the same thread that called `set()`? |
| Class loader | `long-lived registry/thread -> plugin object/Class/TCCL -> old ClassLoader` | Multiple loaders for the same module across redeploys; old classes never unload | Does any root still hold the old loader? Were resources closed and deregistered? |

These paths are **conceptual templates**; field layouts and MAT views change across JDKs and frameworks. Do not force-fit one fixed path onto every dump.

### 4.1. Collection: long-lived container holding short-lived elements

Scenario: a service keeps `static final List<RequestInfo> HISTORY`, calling `HISTORY.add(info)` on every completed request and never removing items. `ArrayList` only manages references; it has no idea which records have lost value.

In a dump, millions of `RequestInfo` objects might be held via:

~~~text
GC root -> class Service -> static HISTORY
         -> ArrayList.elementData -> RequestInfo -> request body / attachments
~~~

What to inspect:

- Actual `size`, unique entry count, and graph depth behind each entry; the top-level `ArrayList` is tiny while its backing array and elements can be huge.
- Are entries needed business data or records from closed requests/sessions? Is there a cap on count, bytes, or age?
- Does a `Map` hold heavy key objects, large values, or accidental reference cycles? Both keys and values can be retained.
- Was an item "removed from map A" while remaining in list B or queue C? One surviving GC root path suffices to keep an object alive.
- With `ConcurrentHashMap`, `CopyOnWriteArrayList`, or cache wrappers, you may need to expand several layers of nodes, tables, or wrappers; do not stop at a wrapper class name as the true owner.

**Proper fix:** align collection ownership with lifecycle; remove inside `finally` or session-close callbacks; cap history, use bounded queues, and apply backpressure where needed. Switching from `List` to `Set` does not fix a leak if entries are still never removed.

### 4.2. Cache: intentional storage lacking bounds or expiration

Valid caches are meant to retain objects across requests to improve hit rates. Therefore, **a cache with high retained heap is not sufficient to declare a leak**. Suspicion grows when keys grow endlessly such as `userId + timestamp`, values are huge graphs, TTL is inactive, there is no size/weight limit, or expiration only triggers on subsequent access.

~~~text
GC root -> singleton CacheManager
         -> Map table -> Entry(key = unique-request-id, value = byte[])
~~~

Record hit/miss rates, entry count, estimated weight, eviction count, plus TTL and max size/weight settings. **Maximum entry count** does not equal **maximum bytes** when entries vary widely in size. TTL only defines logical validity; when physical eviction runs depends on the implementation and may require maintenance/eviction sweeps when the cache is rarely accessed.

Example capping **entry count** in a single-threaded `LinkedHashMap`; not a complete production concurrent cache:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

class BoundedHistory {
    private final Map<String, byte[]> recent =
        new LinkedHashMap<String, byte[]>(16, 0.75f, true) {
            @Override
            protected boolean removeEldestEntry(Map.Entry<String, byte[]> eldest) {
                return size() > 100;
            }
        };
}
~~~

Setting `accessOrder = true` enables LRU ordering, and `removeEldestEntry` evicts the oldest entry upon insertion; it does **not** automatically clear references to the value held elsewhere. `LinkedHashMap` is not thread-safe by default; multi-threaded apps should use a cache with proper eviction, weight/TTL, concurrency, and monitoring.

`WeakHashMap` is not a universal "leak cure": it relies on weak **keys**, while values remain strongly referenced; if a value references back to its key, the key can remain reachable. Switch map types only when ownership truly matches weak-reference semantics.

### 4.3. Listener and callback: registered but never unregistered

Suppose a view object registers a callback on a global event bus. Inside the callback, a lambda captures `this`, models, sessions, or large arrays. The view closes, yet the event bus keeps holding the callback:

~~~text
GC root -> global EventBus
         -> listeners -> lambda/Listener
         -> captured ViewModel
         -> model -> session objects
~~~

Investigate by locating `EventBus`/`PropertyChangeSupport`/registries in the Dominator Tree or incoming references from `ViewModel`. Check whether listener counts grow with each view open/close, whether duplicate registrations occur, and whether invalidated callbacks stay registered.

Fix with an explicit **subscribe/unsubscribe** contract. Registration must tie to a lifecycle owner and keep the token/callback needed for removal, e.g. (illustrative hypothetical API snippet, not a standalone program):

~~~java
Registration registration = eventBus.subscribe(event -> handle(event));
try {
    runScreenOrSession();
} finally {
    registration.close(); // Actually removes the callback from the registry
}
~~~

Where frameworks provide `AutoCloseable`, `Disposable`, lifecycle hooks, or managed subscriptions, use them. A "weak listener" fits only when event handlers are allowed to disappear spontaneously; never blindly convert all listeners to weak references or valid events may be silently dropped.

### 4.4. `ThreadLocal`: values live by **thread** lifetime, not request lifetime

`ThreadLocal<T>` stores per-thread values. In a thread pool, a thread can stay alive for hours across thousands of requests. If a task calls `set(context)` and forgets `remove()`, the old request context stays retained long after the request ends—or bleeds into the next task if code reads the same `ThreadLocal`.

~~~text
GC root -> live worker Thread
         -> Thread.threadLocals -> ThreadLocalMap.Entry
         -> Entry.value = RequestContext -> payload / User / buffer
~~~

In OpenJDK's `ThreadLocalMap` implementation, **the key is a weak reference to the `ThreadLocal`, while `Entry.value` remains a strong reference**. An entry whose key was GC'd becomes a "stale entry"; stale entry cleanup happens opportunistically during map operations and is not guaranteed to occur immediately. Therefore, **never** rely on setting the `ThreadLocal` variable to `null` or on weak keys to fix a leak; the proper fix is calling `remove()`.

Place cleanup in `finally`, directly **on the thread that called `set`** (illustrative method snippet; define `Request` and `handle` in a real app):

~~~java
private static final ThreadLocal<Request> CURRENT = new ThreadLocal<>();

void process(Request request) {
    CURRENT.set(request);
    try {
        handle(request);
    } finally {
        CURRENT.remove();
    }
}
~~~

Key distinctions:

- Calling `remove()` on thread A **does not clear** a value set by thread B.
- Calling `set(null)` alone expresses lifecycle less clearly than `remove()`; with `ThreadLocalMap`, prefer `remove` to clear the entry.
- `InheritableThreadLocal` can also propagate state across thread creation; executors/pools and async callbacks require explicit context-propagation/cleanup design rather than assuming per-request isolation.
- `ThreadLocal` is poorly suited for automatically passing request context across coroutines, virtual threads, and async tasks. Virtual threads are typically short-lived, though huge numbers of values can still consume memory while those threads live.
- In MAT, inspect **live threads**, pool names, `threadLocals`, actual values, and task lifecycles. A value for an active request is normal; a value from a request finished hours ago is suspect.

### 4.5. Class loader: data from old deployments never freed

Every class is identified by **binary name + defining class loader**, so after reloads/redeploys multiple classes with identical names can be defined by different loaders. Normal case: an old loader along with its classes and instances becomes unreachable once a plugin or sub-application unloads, allowing the JVM to collect/unload them when conditions permit. Leak case: a longer-lived host still retains at least one object or loader from the old plugin.

Example retention path:

~~~text
GC root -> host application EventBus (long-lived loader)
         -> plugin v1 listener instance
         -> plugin Class -> defining ClassLoader v1
         -> related classes, instances, and metadata remain pinned
~~~

Other frequent paths: global caches holding `Class<?>`/`Method`/`MethodHandle` or plugin instances, live threads spawned by the plugin, unremoved schedulers/drivers/MBeans/registries, or `Thread.contextClassLoader` still pointing to the old loader. **Static fields on classes loaded by the old loader do not by themselves form permanent external GC roots**: look for which long-lived component keeps the loader/class/instance reachable.

In MAT, use **Class Loader Explorer**, group Histogram by class loader, and inspect **Duplicate Classes** and `Path to GC Roots` for old loaders/objects. Cross-check version/deploy timestamps and count how many loaders should already be dead. Some duplicate classes are legitimate in plugin or isolation architectures; growing loader counts after each redeploy coupled with unintended root paths provide strong evidence.

**Fix:** deregister listeners, schedulers, tasks, MBeans, JDBC drivers, or resources opened by the plugin on unload; stop plugin threads and restore context class loaders if modified; purge global maps/callbacks holding classes or instances; close `URLClassLoader` when appropriate. `URLClassLoader.close()` releases loader-opened resources (such as JAR handles) and **does not force class unloading** if objects, classes, or the loader remain reachable.

Note: Metaspace sits outside the Java heap. HPROF reveals loader and object retention clues, not the full native memory picture. Cross-check NMT, JFR, or appropriate memory metrics if Metaspace grows.

## 5. Java 17+ Hands-On: Creating Five Intentional Retention Chains

This lab uses two source files with no external libraries beyond the JDK. It deliberately retains several byte arrays so they are **easy to trace in a heap dump**; this is a diagnostic fixture, not a recommended application design. Create a fresh working directory and place both files inside it.

**File `ExamplePlugin.java`** (compiled only into `plugin-out/`, so the application class loader cannot see `ExamplePlugin.class` directly):

~~~java
public final class ExamplePlugin implements Runnable {
    private final byte[] payload = new byte[1_000_000];

    @Override
    public void run() {
        System.out.println("plugin bytes=" + payload.length);
    }
}
~~~

**File `LeakRetentionLab.java`:**

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class LeakRetentionLab {
    static final List<byte[]> COLLECTION = new ArrayList<>();
    static final Map<String, byte[]> CACHE = new HashMap<>();
    static final List<Runnable> LISTENERS = new ArrayList<>();
    static final ThreadLocal<byte[]> LOCAL = new ThreadLocal<>();

    private static void registerLambdaListener() {
        byte[] captured = new byte[2_000_000];
        LISTENERS.add(() -> System.out.println("listener bytes=" + captured.length));
    }

    private static void registerPluginListener() throws Exception {
        URL pluginDir = Path.of("plugin-out").toAbsolutePath().toUri().toURL();

        // Child loader loads ExamplePlugin. Host retains Runnable in static registry.
        try (URLClassLoader loader = new URLClassLoader(
                new URL[] { pluginDir },
                LeakRetentionLab.class.getClassLoader())) {
            Class<?> type = Class.forName("ExamplePlugin", true, loader);
            LISTENERS.add((Runnable) type.getDeclaredConstructor().newInstance());
        }
        // close() finished, but LISTENERS still retains the plugin instance.
    }

    public static void main(String[] args) throws Exception {
        long pauseMs = args.length == 0 ? 60_000L : Long.parseLong(args[0]);

        COLLECTION.add(new byte[3_000_000]);
        CACHE.put("historical-report", new byte[4_000_000]);
        registerLambdaListener();
        registerPluginListener();

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            // Task finishes, yet the worker thread stays alive in the pool:
            pool.submit(() -> LOCAL.set(new byte[5_000_000])).get();

            System.out.println("BEFORE_CLEANUP pid=" + ProcessHandle.current().pid());
            Thread.sleep(pauseMs); // Capture heap-before.hprof during this window.
        } finally {
            // remove() must run on the exact worker thread that called set().
            pool.submit(LOCAL::remove).get();
            pool.shutdown();
            COLLECTION.clear();
            CACHE.clear();
            LISTENERS.clear();
        }

        System.out.println("AFTER_CLEANUP pid=" + ProcessHandle.current().pid());
        Thread.sleep(pauseMs); // Can capture heap-after.hprof here.
    }
}
~~~

Compile and run inside that directory:

~~~bash
mkdir plugin-out
javac -d plugin-out ExamplePlugin.java
javac LeakRetentionLab.java
java -cp . LeakRetentionLab
~~~

Output lines follow this format; PID is an **actual runtime value varying per run**:

~~~text
BEFORE_CLEANUP pid=<actual pid>
AFTER_CLEANUP pid=<actual pid>
~~~

The two lines print roughly 60 seconds apart with default arguments. Use `java -cp . LeakRetentionLab 10` for a quick smoke test (10 ms per phase); when taking dumps, pass a long enough duration such as `60000`. Listener/plugin `run()` methods are never called, so they print no extra text.

In another terminal, once `BEFORE_CLEANUP` appears:

~~~bash
jcmd <pid> GC.heap_dump /path/to/heap-before.hprof
~~~

Once `AFTER_CLEANUP` appears (while the JVM is still alive):

~~~bash
jcmd <pid> GC.heap_dump /path/to/heap-after.hprof
~~~

Subject to JDK and GC conditions, the post-cleanup dump can show the fixture objects are no longer reachable. However, there is **no guarantee** of an exact 15 MB drop or immediate class loader unloading: real memory includes overhead, and GC timing, Java stacks, and JVM implementation can affect snapshots. Ensure sufficient disk space and remember dumping can cause pauses.

**Why this lab is easy to trace:**

| Data | Root/retention path before cleanup | Cleanup action |
| --- | --- | --- |
| `3_000_000` bytes | Static `COLLECTION -> ArrayList.elementData -> byte[]` | `COLLECTION.clear()` |
| `4_000_000` bytes | Static `CACHE -> HashMap.Node -> byte[]` | `CACHE.clear()` |
| `2_000_000` bytes | Static `LISTENERS -> lambda -> captured byte[]` | `LISTENERS.clear()` |
| `5_000_000` bytes | Live executor worker `Thread -> threadLocals -> Entry.value` | `LOCAL.remove()` on the same worker |
| Plugin `1_000_000` bytes | Host `LISTENERS -> ExamplePlugin instance -> Class/loader` | Remove listener; loader already closed resources |

Key plugin detail: `ExamplePlugin.class` must reside only in `plugin-out`; the host program must run with classpath `.` only. If `ExamplePlugin.class` sits in the host directory or `plugin-out` is added to the classpath, the parent loader will load the class and the exercise will no longer reproduce the intended child-loader relationship. Always start from a clean directory.

## 6. Reading Lab Results and Gathering Unambiguous Evidence

**Collection/cache:** locate byte arrays matching the fixture sizes, select an instance, and inspect **incoming references**. For the collection, trace to `ArrayList.elementData` and static `COLLECTION`; for the cache, trace through `HashMap.Node.value` to static `CACHE`. The Histogram only shows many `byte[]` without saying which area owns them. `Retained heap` quantifies data dependent on the container, though it can differ from raw array sizes due to differing reference paths.

**Listener:** locate the `2_000_000`-byte array, inspect the lambda class and captured field, and trace up to `LISTENERS`. Trace all the way to the registry owner, because clearing the local `captured` variable after creating the lambda does not clear the reference held inside the callback.

**ThreadLocal:** locate the `5_000_000`-byte array, verify `Thread -> threadLocals -> Entry.value` and the live executor thread. Do not confuse it with local stack data from a finished task; the worker thread and `ThreadLocalMap` themselves retain the value when `remove()` is omitted.

**Class loader:** find `ExamplePlugin` in Histogram grouped by class loader or in `Class Loader Explorer`. Trace from the instance in `LISTENERS` to the class defined by `URLClassLoader`. After the registry clears the callback and no other root path remains, the old loader becomes eligible for collection; having closed its JAR **does not** prove classes can unload right away. Another path via `Thread.contextClassLoader` or a separate registry (if present in a real app) can still keep the loader alive.

**Before/after comparison:** verify that corresponding class/instance counts and root paths disappear after cleanup. If objects still appear in the later dump, investigate any remaining strong paths and temporary local references. Comparing total "heap size" alone is insufficient to evaluate the five groups; cross-check retained sets and business lifecycles.

A concise evidence summary suitable for handing to the engineer fixing the code:

~~~text
Suspect: 1_200 ReportContext retained after batch completion
Expected lifetime: one batch; actual: persists >30 minutes
Retainer: AppCache.entries -> HashMap.Node.value -> ReportContext
GC root: application singleton class
Growth: +200 ReportContext after each new batch, never drops after cleanup
Likely cause: cache keyed by batchId lacks invalidation/eviction
Fix hypothesis: remove batchId at end of batch + bound maximum weight
Validation: run same workload, verify entry count and post-GC dump
~~~

Numbers in this template are **illustrative examples**, not outputs from the lab or any real system.

## 7. Cases Prone to Misdiagnosis

| Observation | Premature conclusion to avoid | Additional evidence needed |
| --- | --- | --- |
| Large `HashMap` retained heap | "Every cache leaks" | Does the cache have limits, TTL/eviction, good hit rate, and flat entry count under steady load? |
| Many `byte[]` | "`byte[]` is the root cause" | Who holds `byte[]`? Which images/files/network payloads are valid? |
| Non-empty `ArrayList` | "Request finished so `List` must be empty" | Is the collection a valid history/audit/queue with TTL and SLA? |
| `ThreadLocalMap` holding context | "Every `ThreadLocal` is a leak" | Does the context belong to a running task? Are threads pooled long-term? |
| Multiple classes with same name | "Definitely a class loader leak" | Is there valid plugin isolation? Do old-version loaders persist after undeploy? |
| `Metaspace` growing | "Heap dump must hold all Metaspace bytes" | Loader graph + NMT/JFR/process native memory; heap is only part of the picture |
| Heap used did not drop after `clear` | "GC refuses to free memory" | Are you reading used or committed? Are other paths holding it? Did GC run? |
| GC root is a thread | "That thread is always the culprit" | Is it a transient stack local, or a `ThreadLocal`/task registry persisting across requests? |

**GC paths span multiple reference types.** MAT usually offers an option to exclude weak/soft/phantom references when tracing paths. A single weak reference is insufficient to prove strong retention. Conversely, a "soft reference" follows memory-pressure collection rules; never treat it as a deterministic TTL contract or rely on its presence as sole evidence. Inspect all strong paths and verify whether removing a given edge eliminates retainability.

**Heap dumps are point-in-time.** Leak Suspects reports rely on snapshot structure and dominance, knowing nothing about when objects were allocated or which business events ended. Multiple snapshots with metadata, allocation profiling/JFR, request counts, and application counters confirm trends. When documenting hard-to-reproduce leaks, include a timeline rather than asserting conclusions from one snapshot.

## 8. Rules for Fixing at the Proper Lifecycle

Do not start by adding `System.gc()` or bumping `-Xmx` to "fix a leak." Neither removes a reachable strong reference. Fix the code owning the lifecycle:

1. **Collection:** whoever calls `add` must define `remove/clear` conditions; use bounded queues or retention policies for historical data.
2. **Cache:** enforce size **and/or weight** caps, expiry, and event-driven invalidation; monitor size and evictions. Avoid caching on keys with unbounded cardinality.
3. **Listener:** subscribe once in the proper scope, store the registration token, and unregister in `close`/`dispose`/`finally`; avoid lambdas capturing huge objects when a small immutable ID suffices.
4. **`ThreadLocal`:** `set` and `remove` within the same task and thread; always use `try/finally`; audit libraries that silently attach request context to pooled threads.
5. **Class loader:** on undeploy, detach registries/callbacks, cancel scheduled jobs, stop plugin threads, clear caches referencing `Class`/`Method`/instances, restore TCCL if altered, close loaders/resources, and verify unload eligibility.

After fixing, rerun the **exact scenario**: repeat creating/using/closing 100 or 1,000 sessions/plugins/tasks; measure live object counts after each cycle and owner retained heap; take a steady-state heap dump. Expect a **plateau** or drop after cleanup, not growth proportional to completed cycles. If the app holds valid long-lived caches, document expected upper bounds and compare against measured figures.

## 9. Self-Check Questions

**Question 1.** In MAT, an `ArrayList` has only dozens of bytes of shallow heap yet hundreds of MB of retained heap. Why? Because the container via its backing array keeps a child object graph alive; inspect root paths and business lifetime before calling it a leak.

**Question 2.** A `Map<SessionId, SessionData>` grows endlessly even though sessions expire. Where do you look? Inspect entry count, actual TTL/eviction, the singleton → map → value chain, and whether session close triggers invalidation.

**Question 3.** A listener was unsubscribed yet the view model stays alive. What next? Search **all** other incoming references and root paths, including schedulers, caches, other callbacks, active stacks, and thread/task registries; unsubscribing from one place does not guarantee no references remain.

**Question 4.** A `ThreadLocal` is created in a local variable, and that variable goes out of scope. Is the value guaranteed to be cleaned up? No. In OpenJDK, the weak key can leave a strong value inside a stale entry on a live thread. Call `remove()` on the right thread when the request finishes.

**Question 5.** `URLClassLoader.close()` was called yet MAT still shows `PluginV1`. Is that a JVM bug? No. `close()` releases I/O resources; all root paths to the loader, classes, and instances must be eliminated before class unloading can happen.

**Question 6.** A post-cleanup heap dump still contains objects, and `GC.heap_dump -all` was used. What conclusion needs correction? The dump includes unreachable objects, so mere presence of an object cannot prove "a root still holds it"; verify reachability and dump mode.

**Question 7.** After three deploy cycles, 3 class loaders containing the same class name appear. How do you prove a leak? Identify which loaders belong to undeployed versions, inspect paths to GC roots, find which old-version instances remain pinned, and track across cleanup/GC cycles; never conclude solely from duplicate classes.

## Reference Documentation

- Eclipse MAT: [Basic Tutorial — Histogram, Dominator Tree, Path to GC Roots](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/gettingstarted/basictutorial.html).
- Eclipse MAT: [Finding Memory Leak — workflow and queries](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/findingmemoryleak.html).
- Eclipse MAT: [Analyzing Class Loader](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/tasks/analyzingclassloader.html) and [Duplicate Classes](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/inspections/duplicate_classes.html).
- Oracle Java SE 25: [ThreadLocal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ThreadLocal.html) — lifecycle and `remove()`.
- OpenJDK: [ThreadLocalMap implementation](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/lang/ThreadLocal.java) — weak keys, strong values, and stale entries in the current implementation.
- Oracle Java SE 25: [jcmd](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html) — `GC.heap_dump`, `-all`, and operational impact.
