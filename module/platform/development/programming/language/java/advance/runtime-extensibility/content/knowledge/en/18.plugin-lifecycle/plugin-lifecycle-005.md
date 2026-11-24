# Publishing the Active Plugin Set Safely for Concurrent Readers

## 1. The Problem: Multiple Reader Threads While Plugins Are Replaced

A plugin system typically has multiple request threads continuously selecting and invoking plugins, while a management thread may add, update, disable, or replace plugins. At any point in time, the system needs to publish an **active plugin set** for readers to use.

If the registry is merely a mutable \`ArrayList\` or \`HashMap\` shared directly, a writer can mutate its structure while a reader is traversing it. Consequences include inconsistent data, selecting the wrong provider, \`ConcurrentModificationException\` in some cases, or memory visibility bugs due to a missing happens-before relationship. \`ConcurrentModificationException\` is **not a synchronization mechanism** and is not guaranteed to appear on every data race.

Design goals:

- Readers see **a complete, validated, and activated snapshot**, never a half-constructed state.
- Every registry lookup by a reader is a consistent read operation, requiring no lock on the hot path.
- Writers can prepare a new snapshot off the read path, and then **publish it in a single atomic operation**.
- A replaced plugin does not have its resources closed while old requests are still calling it.
- Lifecycle states such as \`NEW\`, \`STARTING\`, \`ACTIVE\`, \`DRAINING\`, and \`STOPPED\` are not conflated with whether an object still appears in a map.

The maintainable foundational solution is **immutable snapshot + atomic/volatile reference + lifecycle drain**.

## 2. What Layers of Safety Are Involved Here?

Four kinds of safety must be separated:

| Aspect | What Must Be Guaranteed | Example Bug If Missing |
|---|---|---|
| Memory visibility | Readers see writes made before publication | Seeing uninitialized configuration or fields |
| Atomic publication | Readers receive a complete registry version | Seeing new provider A while B is unexpectedly still the old version |
| Snapshot immutability | Writers do not mutate the registry object a reader received | Traversing a map mutated midway |
| Lifecycle safety | Plugins still in use are not closed prematurely | \`IllegalStateException\`, socket/loader closed mid-request |

**\`volatile\` or \`AtomicReference\` only solves publication of the reference**; it does not make a mutable object behind it immutable, and does not automatically make the plugins inside thread-safe.

The linearization point of a publication is typically the \`active.set(next)\` operation or writing to a \`volatile\` field. Readers fetching the snapshot before that point use the old version; readers fetching afterward can use the new version. With a single reference read, no global lock is needed to traverse an immutable structure.

## 3. Immutable Snapshot and AtomicReference

Basic model:

\`\`\`java
record PluginRegistry(long revision, Map<String, Plugin> plugins) {
    PluginRegistry {
        plugins = Map.copyOf(plugins);
    }
}

AtomicReference<PluginRegistry> active =
        new AtomicReference<>(new PluginRegistry(0, Map.of()));
\`\`\`

A writer builds a new registry:

\`\`\`java
Map<String, Plugin> nextPlugins = new HashMap<>(current.plugins());
nextPlugins.put("csv", readyCsvPlugin);
PluginRegistry next = new PluginRegistry(current.revision() + 1, nextPlugins);
active.set(next);
\`\`\`

A reader uses:

\`\`\`java
PluginRegistry snapshot = active.get();
Plugin selected = snapshot.plugins().get("csv");
\`\`\`

This is **copy-on-write at the registry level**, not cloning every plugin object. \`Map.copyOf\` creates an unmodifiable map through the API; the copy is **shallow**. Plugin objects inside the map may hold mutable state. Therefore you must ensure plugins are properly initialized, in an appropriate state, and handle concurrent calls per their contract.

Advantages:

- Readers only call \`get()\` and look up in the finalized map.
- No lock is required in the read loop.
- A retrieved snapshot cannot be structurally mutated by writers.
- Revisions make changes observable and easy to correlate in logs.

Disadvantages:

- Each change requires creating a new registry/map; best suited when updates are much less frequent than reads.
- The same plugin instance can be referenced by multiple snapshots.
- Does not by itself manage the lifetime of instances and resources.

## 4. Why Is AtomicReference or volatile Sufficient for Publication?

Under the Java Memory Model, a write to a \`volatile\` variable and a matching read establish a **happens-before** relationship. \`AtomicReference.set\`/\`get\` have the memory effects of \`volatile\`. Therefore, if the writer constructs the complete snapshot object **before** \`set\`, a reader receiving that reference will observe all writes validly published before it.

Model:

\`\`\`text
Writer thread                            Reader thread
-------------                            -------------
create Plugin A
initialize Plugin A
build immutable Map
build Registry revision 7
active.set(registry7)  -------->         registry = active.get()
                                        registry.plugins().get("A")
                                        invoke plugin A
\`\`\`

**Do not** do this:

\`\`\`java
Map<String, Plugin> mutable = new HashMap<>();
active.set(new PluginRegistryMutable(mutable));
mutable.put("A", plugin); // mutate after publication: wrong
\`\`\`

Also, merely using \`final\` fields inside an object does not automatically make reference-replacement operations observed by multiple readers safe if you assign to an unsynchronized plain variable.

## 5. Complete Java 17+ Example: Concurrent Snapshot Reads

The example uses one writer publishing a new registry version and two readers reading snapshots. It requires no external dependencies. Log output across threads may interleave because thread scheduling is non-deterministic, yet each reader consistently uses the same revision within a single read.

Create the file **\`PluginSnapshotDemo.java\`**:

\`\`\`java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;

public class PluginSnapshotDemo {
    interface Plugin {
        String run(String input);
    }

    record Registry(long revision, Map<String, Plugin> plugins) {
        Registry {
            plugins = Map.copyOf(plugins);
        }
    }

    static final class PluginManager {
        private final AtomicReference<Registry> active =
                new AtomicReference<>(new Registry(0, Map.of()));

        Registry snapshot() {
            return active.get();
        }

        void publish(Registry next) {
            active.set(next);
        }
    }

    public static void main(String[] args) throws Exception {
        PluginManager manager = new PluginManager();
        Plugin upper = s -> s.toUpperCase(java.util.Locale.ROOT);
        manager.publish(new Registry(1, Map.of("format", upper)));

        CountDownLatch readersCaptured = new CountDownLatch(2);
        CountDownLatch writerPublished = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);

        try {
            Runnable reader = () -> {
                Registry local = manager.snapshot();
                readersCaptured.countDown();
                try {
                    writerPublished.await();
                    System.out.println(
                            "reader revision=" + local.revision()
                            + " result="
                            + local.plugins().get("format").run("hello"));
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            };

            var first = executor.submit(reader);
            var second = executor.submit(reader);

            readersCaptured.await();
            Plugin lower = s -> s.toLowerCase(java.util.Locale.ROOT);
            Map<String, Plugin> changed =
                    new HashMap<>(manager.snapshot().plugins());
            changed.put("format", lower);
            manager.publish(new Registry(2, changed));
            writerPublished.countDown();

            first.get();
            second.get();

            Registry latest = manager.snapshot();
            System.out.println("latest revision=" + latest.revision()
                    + " result=" + latest.plugins().get("format")
                    .run("HELLO"));
        } finally {
            executor.shutdown();
        }
    }
}
\`\`\`

Run:

\`\`\`bash
javac PluginSnapshotDemo.java
java PluginSnapshotDemo
\`\`\`

A valid output (the two reader lines may swap order):

\`\`\`text
reader revision=1 result=HELLO
reader revision=1 result=HELLO
latest revision=2 result=hello
\`\`\`

Explanation:

1. The writer publishes registry revision 1 containing provider \`upper\`.
2. Both readers hold a reference to **the same snapshot revision 1** and wait for the writer to publish revision 2.
3. The writer replaces the registry with revision 2 containing \`lower\`.
4. Both readers finish using the old provider because their snapshot was not mutated.
5. A fresh read after publication receives revision 2 and uses \`lower\`.

This is a demonstration of **publication and snapshot consistency**. It does not close providers, manage in-flight requests, or handle competing writers; those parts must be designed additionally.

## 6. Concurrent Updates: set, compareAndSet, and updateAndGet

If there is only **a single serialized writer** (such as a control-plane thread), \`active.set(next)\` is sufficient for publication.

If there are multiple writers:

\`\`\`text
Writer A reads revision 4
Writer B reads revision 4
Writer A adds plugin X -> revision 5
Writer B adds plugin Y -> revision 5
Writer B set(...) overwrites X
\`\`\`

This is a **lost update**. It can be solved by:

- Using a writer lock or a serial executor for all registry mutations.
- Using a \`compareAndSet(expected, next)\` loop to publish only if the snapshot has not changed; if CAS fails, re-read and build a new snapshot.
- Using \`updateAndGet\` with a **side-effect-free** function that computes the new value, because that function may be retried under CAS contention.

CAS example:

\`\`\`java
// Integration snippet; active is AtomicReference<Registry>, plugin is ready.
for (;;) {
    Registry old = active.get();
    Map<String, Plugin> changed = new HashMap<>(old.plugins());
    changed.put("new-provider", plugin);
    Registry next = new Registry(old.revision() + 1, changed);
    if (active.compareAndSet(old, next)) {
        break;
    }
}
\`\`\`

**Do not call \`plugin.start()\` inside a CAS callback or \`updateAndGet\` function.** Because retries can occur, a lifecycle operation with side effects could run multiple times. Initialize the plugin before entering the update loop and publish only an already-ready instance; if it fails due to conflict, apply an explicit handling/reuse or cleanup policy.

CAS only resolves snapshot mutation conflicts; lifecycle cleanup when a writer fails must still be orchestrated by the manager.

## 7. Do Not Close a Plugin Immediately After Publishing a New Version

Dangerous scenario:

\`\`\`text
Reader A takes old snapshot containing Plugin V1
        |
Writer publishes new snapshot containing Plugin V2
        |
Writer calls V1.close() immediately
        |
Reader A is still running V1.run() --> resource-closed-mid-request error
\`\`\`

Publication does not mean **every reader has stopped using the old snapshot**.

A proper hot-swap procedure requires:

1. Creating, validating, and starting V2 first.
2. Atomically publishing the V2 snapshot so new requests receive V2.
3. Marking V1 as \`DRAINING\`, issuing no more new calls from the active registry.
4. Waiting for in-flight V1 calls to complete (with a timeout/cancellation policy).
5. Once no calls remain, closing V1 and releasing resources/class loaders.

Mechanisms that can be used to protect lifetime:

- **Reference-counted lease:** readers increment a usage counter before calling and decrement it in \`finally\`; writers wait for the counter to reach 0.
- **Reader-writer lock:** readers hold the read lock for the duration of use; writers acquire the write lock before stopping/closing the old version.
- **Epoch/quiescent-state reclamation:** readers enter an epoch; writers reclaim only after all relevant readers have exited that epoch. Requires careful implementation.
- **Grace-period drain:** stop accepting new requests and wait for in-flight requests tracked by the request manager.

**Warning about reference counting:** simply incrementing a counter **after** taking a snapshot is not enough if a writer can close the plugin right before the counter is incremented. You must design an **atomic lease-acquisition step combined with a state check**; if it fails, the reader re-reads the latest snapshot. Writers transition state from \`ACTIVE\` to \`DRAINING\` under the same protocol before waiting for the lease count to reach 0.

## 8. A Safer Lease Model

A holder object can be used for each plugin version:

\`\`\`text
PluginHolder {
    plugin
    state: ACTIVE | DRAINING | CLOSED
    activeLeases
}
\`\`\`

Minimal protocol:

**Reader**
1. Obtain the registry snapshot.
2. Identify the desired holder.
3. Attempt \`acquire()\`: succeeds only if the holder is still ACTIVE; increments the lease count via a synchronized/atomic operation with no race against DRAINING.
4. If acquisition fails, re-read the snapshot and retry or return an error.
5. Invoke the plugin.
6. \`release()\` in \`finally\`.

**Writer**
1. Prepare the new holder in a ready state.
2. Publish the new registry.
3. Transition the old holder to DRAINING, blocking new leases.
4. Wait for remaining leases to drop to 0.
5. Close the plugin and transition to CLOSED.

The protocol must guarantee that if a reader attempts to acquire at the exact time a writer drains, only one outcome is possible: either the reader owns a valid lease and the writer waits, or acquisition fails and the reader retries. Test races thoroughly.

A simpler option, often easier to prove correct when load is moderate, is using a **read/write lock guarding both snapshot acquisition and the usage phase**. That increases contention, but fits low-request applications. Atomic snapshots and lease protocols are a better choice for read-heavy workloads, though more complex.

## 9. Does ConcurrentHashMap Replace Snapshots?

\`ConcurrentHashMap\` provides thread-safe structural and lookup operations. However:

- A sequence of multi-key reads can observe different update timestamps.
- \`ConcurrentHashMap\` iterators generally have **weakly consistent** semantics, not a strictly consistent point-in-time versioned snapshot.
- Individual \`put\` or \`remove\` calls do not form an atomic transaction updating the entire registry.
- Plugin lifecycle is still not managed automatically.

Therefore, if the requirement is to **publish the entire plugin set as a logical version**, an atomically swapped immutable registry has clearer semantics. If you only update independent keys and do not need a unified snapshot, \`ConcurrentHashMap\` may suffice.

Similarly, \`Collections.synchronizedMap\` requires external synchronization for iteration and multi-step sequences; it does not automatically turn a multi-step publish workflow into an uninterrupted transaction.

## 10. Checking Immutability and Plugin Configuration

\`Map.copyOf\` protects map structure; every \`Plugin\` value is still a reference. If a plugin has mutable fields such as configuration, connection pools, or caches, readers may observe changes mid-request.

You should separate:

- **Immutable metadata**: ID, version, API compatibility, capabilities, selection order.
- **Immutable per-revision configuration**: each snapshot references a validated configuration.
- **Runtime state with explicit ownership**: resources and counters live inside the holder, managed separately from the metadata map.
- **Plugin concurrency contract**: single-threaded, thread-safe, per-request instance, or bounded pool.

If a plugin is **not thread-safe**, publishing it into a thread-safe map does not allow multiple readers to invoke it concurrently safely. The host must serialize invocations or instantiate per request.

A snapshot should carry a \`revision\` or \`generation\` to log plugin selection, aid tracing/auditing, and distinguish versions during hot updates.

## 11. Errors, Rollback, and State Management

A registry change can fail at multiple points:

| Phase | Error | Handling Approach |
|---|---|---|
| Preparation | Invalid JAR or metadata | Do not publish |
| Initialization | Plugin V2 fails start/health check | Keep snapshot V1 |
| Publication | CAS fails due to another writer | Recompute snapshot or reject per conflict policy |
| Drain | V1 has hanging requests | Timeout, stop accepting, cancellation, or operational policy |
| Cleanup | Plugin close fails | Log warning, reclaim remaining parts, and flag for attention |
| Rollback | V2 fails after publication | Build/publish a rollback snapshot; do not assume V1 still has resources if already closed |

Rollback here is **publishing a new revision** pointing back to a valid plugin (if still usable), not erasing traces of the previous revision. If V1 was already closed, rollback may require re-initializing it.

At shutdown, the system must stop accepting new requests, wait for in-flight operations, and close plugins in the proper dependency order. Avoid retaining references to old plugin class loaders in static caches, callbacks, or threads; otherwise, hot unloading can be blocked.

## 12. Concurrency Testing and Observability

Thread safety cannot be proven by a single demo run. Key test cases:

1. Multiple readers continuously fetch snapshots while a writer swaps revisions.
2. Writer builds a new snapshot but has not published yet: readers must not see half-built config.
3. Two writers concurrently add different keys: no lost updates.
4. Reader holds an old snapshot for a long time: writer must avoid premature close.
5. Reader acquires a lease right as writer transitions to DRAINING.
6. Plugin start fails: active snapshot remains unchanged.
7. Plugin run throws an exception: lease is still released in \`finally\`.
8. Repeated rollbacks, shutdowns, timeouts, and hot reloads.

You can combine JUnit concurrency tests, stress tests, and tools like JCStress to verify complex atomic/visibility protocols. Do not use \`Thread.sleep\` as proof of ordering; use \`CountDownLatch\`, barriers, or synchronized test harnesses to control races.

Log metrics/events with \`registryRevision\`, \`pluginId\`, \`pluginVersion\`, publish time, in-flight call count, drain duration, and cleanup status. Do not log sensitive data from requests/plugins.

## 13. Common Mistakes

- Sharing a mutable \`HashMap\` or \`ArrayList\` without synchronization.
- Storing a mutable map in \`AtomicReference\` and continuing to mutate that map.
- Thinking \`volatile\` makes the plugin objects inside thread-safe.
- Using \`ConcurrentHashMap\` while expecting the entire registry to be consistent at a single revision.
- Using \`set(next)\` with multiple writers without preventing lost updates.
- Initializing plugins with side effects inside a CAS function that may be re-invoked.
- Closing plugin V1 immediately after publishing V2 without waiting for V1 readers to finish.
- Incrementing a reference count unsynchronized with close/drain, creating an “acquire after close” race.
- Letting a reader look up the registry twice within the same request and accidentally use a provider from a different version.
- Neglecting cleanup of callbacks, threads, and class loaders during hot reload.
- Assuming \`Map.copyOf\` performs a deep copy of plugins and configuration.

## 14. Design Checklist

Before putting a plugin manager into production:

- Is the snapshot constructed completely and structurally immutable after publication?
- Is the active reference published via \`volatile\`/\`AtomicReference\`?
- Does each reader capture **one snapshot per logical task**?
- Do writers update via a single-writer policy or CAS/locks to avoid lost updates?
- Are new plugins initialized, compatibility-checked, and health-checked before publication?
- Is the old plugin's lifecycle protected by drain/lease or locks before closing?
- Does each plugin uphold thread-safety requirements during invocation?
- Do registry versions have explicit revisions, logs, and rollback capability?
- Are there tests for races, hot swaps, cleanup, start failures, and invoke failures?
- When plugins are untrusted, is there a security boundary beyond class loaders/snapshots?

**Takeaway:** the way to publish a plugin set for concurrent readers is to **build a complete immutable snapshot, then swap the reference with an atomic/volatile operation**. However, for safe hot swapping, you also need **usage rights (leases) or lifecycle synchronization** so you never close a plugin while an old request is still using it.
