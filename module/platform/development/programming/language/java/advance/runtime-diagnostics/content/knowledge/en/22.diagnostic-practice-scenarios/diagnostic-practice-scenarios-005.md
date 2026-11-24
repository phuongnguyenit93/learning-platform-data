# 22.5 Reproducing Reference Retention in a Collection and Tracing to GC Roots in a Heap Dump

A Java program can continue using high heap memory even after requests finish, not because the Garbage Collector (GC) "isn't running", but because **a collection still holds strong references** to objects no longer needed by business logic. As long as objects remain **reachable** from a GC root, the GC is not allowed to reclaim them. To investigate properly, trace from rising memory usage down to the **specific reference chain** connecting the memory-holding objects to a GC root.

This practice lab reproducibly holds 64 objects inside a `static HashMap`, each owning a 256 KiB `byte[]` array. We capture **two HPROF heap dumps** at different stages of **the same JVM**:

1. **RETAINED:** objects are inside the `HashMap` and still retained by the static field.
2. **RELEASED:** call `HashMap.clear()`, removing the map's strong references to those objects; then take a second heap dump containing only live objects.

Then use **Eclipse Memory Analyzer (MAT)**: Histogram → Dominator Tree → Path To GC Roots to pinpoint **what keeps the objects alive**, and compare the before/after snapshots. The example uses Java 17+ and JDK tools; heap dump commands run only against an isolated lab JVM. Never run heavy heap dumps on live production services without evaluating cost and access permissions.

## 1. Core Mindset: Allocated Objects vs. Retained Objects

Concepts to separate clearly:

- **Allocation:** the program creates new objects on the heap, such as `new byte[262144]`. High allocation does not automatically mean a memory leak, because short-lived objects can be reclaimed.
- **Reachability:** an object is considered live if there is a **strong reference path** from a GC root to it. Paths passing only through weak/soft/phantom references have different collection semantics and require separate analysis.
- **GC root:** starting points treated by the JVM as roots of the live object graph, such as static fields of reachable classes, Java threads, live local variables on stacks, JNI global references, and certain JVM internal structures.
- **Retention:** objects survive across one or more GC cycles because a reference path remains.
- **Memory leak in Java:** application logic keeps references to data that is **no longer needed**, preventing memory reclamation; it is not necessarily lost pointer management like in native code.
- **HPROF heap dump:** a point-in-time snapshot of the object graph, classes, fields, references, and root metadata. It explains **who is holding what**, without directly telling you how long every object has lived or when it was allocated.

An object can only be reclaimed by the GC once it is no longer reachable under the applicable reference/GC semantics. Therefore, **calling `System.gc()` does not fix a collection still holding strong references**. Nor does the JVM guarantee that `System.gc()` triggers an immediate GC under every configuration.

### How Does Strong Retention from a Collection Look?

~~~text
GC Root (class kept alive by the JVM)
    |
    v
static field CollectionRootLab.CACHE
    |
    v
java.util.HashMap
    |
    v
HashMap.table (HashMap$Node[] array)
    |
    +-- HashMap$Node(key=0, value=RetainedValue@...)
    |                                 |
    |                                 +-- RetainedValue.payload
    |                                              |
    |                                              v
    |                                          byte[262144]
    |
    +-- HashMap$Node(key=1, value=RetainedValue@...)
    |                                 |
    |                                 +-- byte[262144]
    |
    +-- ... 62 more entries
~~~

This is a **logical reference model**, not verbatim MAT text guaranteed line-by-line. Internal field names, node types, and how GC roots display depend on the JDK and parser. The key takeaway is: **static field → map → internal node → value → `byte[]`**. A single strong reference to the map can keep its entire set of values and payloads alive.

With 64 arrays × 256 KiB, total **array element** data is `64 × 262144 = 16,777,216 bytes = 16 MiB`. That is not yet total retained heap: object headers, references, map table, nodes, keys, and alignment also consume memory.

## 2. Distinguishing Shallow Size and Retained Size Before Reading MAT

An object's **Shallow heap** is the size of that object itself. For example:

- A `HashMap` object typically has a relatively small shallow size because it mainly holds fields like size and the table reference.
- A `byte[262144]` has a shallow size slightly larger than 256 KiB once header/alignment are included.
- A `RetainedValue` holds only an `int id` and a `byte[] payload` reference, so its shallow size is far smaller than its total payload.

The **Retained heap** of object X is the sum of shallow sizes of all objects that would become unreachable if **all paths keeping X alive** were removed, per the dominator/retained-set model. A map with a small shallow size can **indirectly** retain tens of MiB via its values.

| Question | Check in MAT | Do Not Conclude |
| --- | --- | --- |
| How many bytes does this object itself occupy? | **Shallow Heap** | Confusing it with all memory it keeps alive in the JVM |
| How much memory depends exclusively on this object? | **Retained Heap / Retained Set** | Summing retained sizes of overlapping nodes |
| Which class has many instances? | **Histogram** | That the class with the highest instance count is definitely the culprit |
| What prevents an instance from being GC'd? | **Path To GC Roots** | That a single shortest path is the entire cause |
| Which object dominates many other objects? | **Dominator Tree** | That every edge in the dominator tree is an actual Java field reference |

By definition, X **dominates** Y when every path from GC roots to Y must pass through X. The dominator tree is derived from the full object graph; its edges **need not match direct field references** in code. To see the actual field reference chain, use **Path To GC Roots**.

A snapshot with 16 MiB held in a cache may be completely valid by design if the cache is bounded and actively serving requests. Only when data has outlived its lifecycle yet remains held without proper eviction is it a **leak** relative to application requirements.

## 3. Controlled Java 17+ Program to Reproduce the Scenario

Create **`CollectionRootLab.java`** with the full contents:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

public final class CollectionRootLab {
    private static final int ENTRY_COUNT = 64;
    private static final int PAYLOAD_BYTES = 256 * 1024;

    // GC root will lead through the live class and this static field.
    private static final Map<Integer, RetainedValue> CACHE = new HashMap<>();

    private static final class RetainedValue {
        private final int id;
        private final byte[] payload;

        private RetainedValue(int id) {
            this.id = id;
            this.payload = new byte[PAYLOAD_BYTES];
            this.payload[0] = (byte) id;
        }
    }

    private static void populate() {
        for (int i = 0; i < ENTRY_COUNT; i++) {
            CACHE.put(i, new RetainedValue(i));
        }
    }

    private static void releaseReferences() {
        // Clear entries. RetainedValue and byte[] instances are no longer
        // referenced by CACHE after this method returns.
        CACHE.clear();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 0) {
            throw new IllegalArgumentException("Run without arguments");
        }

        populate();

        BufferedReader input = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8));

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("Stage=RETAINED");
        System.out.println("Cache entries=" + CACHE.size());
        System.out.println("Capture first dump, then press Enter");

        // Wait for the jcmd command in the second terminal to capture RETAINED state.
        if (input.readLine() == null) {
            return;
        }

        releaseReferences();
        System.out.println("Stage=RELEASED");
        System.out.println("Cache entries=" + CACHE.size());
        System.out.println("Capture second dump, then press Enter");

        // Wait for the second jcmd command, without retaining references to RetainedValue.
        input.readLine();
        System.out.println("Done");
    }
}
~~~

### Why Does This Example Produce a Clear GC Root Chain?

- `CACHE` is a **static field** in class `CollectionRootLab`. While the JVM keeps this class live, the map stays reachable via class/static state.
- `CACHE.put(i, new RetainedValue(i))` creates 64 values, each holding one `byte[]`. The payload arrays total 16 MiB.
- `populate()` returns before `main` pauses. Objects stay alive **without** needing local variables from that method; the path to trace goes through `CACHE`.
- `BufferedReader.readLine()` merely pauses the main thread awaiting user input. It is a lab coordination mechanism, not a direct root for `RetainedValue` instances.
- `releaseReferences()` calls `CACHE.clear()` to drop mappings; it does **not** need to zero out payload data or call `System.gc()` to drop the references.
- The map object and part of its hash table **capacity backing array** can remain after `clear()`, because the static field `CACHE` still points to the map. What disappears from a *live-object dump* are the `RetainedValue`/payload objects that no longer have strong references.
- There is no infinite allocation loop; the goal is small, safe retention on a test machine without intentionally triggering OOM.

### 3.1. Compiling and Running

Use JDK 17+ with `javac`, `java`, and `jcmd`, on a **non-production** machine:

~~~bash
javac CollectionRootLab.java
java -Xms32m -Xmx128m CollectionRootLab
~~~

When `main` pauses at the first stage, stdout printed by the program is:

~~~text
PID=<actual PID assigned by the OS>
Stage=RETAINED
Cache entries=64
Capture first dump, then press Enter
~~~

`PID` is a dynamic integer; the other lines are fixed when the program starts normally. The JVM is now waiting for **Enter** in terminal A, giving you plenty of time to capture the first heap dump. Do not press Enter before the first capture completes.

**Important note:** the PID line here is not text to copy verbatim into your shell. The `jcmd` command must use the actual PID of the **running lab process**.

## 4. Capturing the First HPROF While the Collection Still Holds References

Open **terminal B** on the same host and inside the matching process namespace. In JDK 21, `GC.heap_dump` takes **filename as a positional argument**, so the typical syntax is:

~~~bash
jcmd -l
jcmd 12345 help GC.heap_dump
jcmd 12345 GC.heap_dump /var/tmp/collection-retained-12345.hprof
~~~

Here **12345 is only an illustrative PID**. Before running, replace it with the PID printed by the program and make sure the output file is new and `/var/tmp` exists/is writable by the JVM process on Linux/macOS accordingly. On Windows, substitute an existing directory path such as `C:/jfr-lab/collection-retained.hprof`.

If `jcmd -l` does not list the process due to container namespaces, check the PID with `ps`/container tooling in the right context. `jcmd` attach usually requires the same effective user/group as the JVM. The HPROF path is opened by the target JVM **on the filesystem where the JVM runs**, not where a remote terminal happens to be open.

On HotSpot JDK 21, `GC.heap_dump` writes an **HPROF Java heap** and is classified as **High impact**. Without `-all`, it triggers a **Full GC** before dumping to focus on live objects. In this lab **do not pass `-all`**, because we want to observe retention after GC has had a chance to collect unreachable objects.

Wait for the command to finish cleanly. Verify the file on the right host/volume:

~~~bash
ls -lh /var/tmp/collection-retained-12345.hprof
~~~

File size is not an exact measurement of retained heap: the HPROF format includes metadata, references, class records, and other JVM objects. Do not expect the file to be exactly 16 MiB.

### Risks of Real Heap Dumps

Although less risky than `jhsdb` live SA attach in many situations, a heap dump can still pause the JVM significantly, trigger GC, consume CPU/I/O, write huge files, fill disks, and capture secrets/PII. **Practice only on disposable/lab JVMs.** In real operations, estimate heap size, disk quota, pause duration, attach permissions, storage location, and data protection plans beforehand.

## 5. Capturing the Second HPROF After Dropping References

Return to terminal A and **press Enter once**. The program executes `releaseReferences()` and prints:

~~~text
Stage=RELEASED
Cache entries=0
Capture second dump, then press Enter
~~~

In terminal B, use the same PID as before but a **different filename**:

~~~bash
jcmd 12345 GC.heap_dump /var/tmp/collection-released-12345.hprof
ls -lh /var/tmp/collection-released-12345.hprof
~~~

At this point `CACHE.size() == 0`. Under the default live-objects-only dump behavior, `CollectionRootLab$RetainedValue` instances and their owned payload arrays **typically no longer appear as reachable objects** in the second HPROF because no path retains them from the static map. Other JVM/JDK `byte[]` arrays still exist, so **do not** expect every `byte[]` to vanish from the histogram.

After the second command finishes, press Enter in terminal A so the program prints:

~~~text
Done
~~~

**Never use the same filename for both snapshots.** JDK 21 by default refuses to overwrite an existing heap dump (unless the corresponding override option is passed), so unique filenames prevent losing evidence. Keep both before/after files for comparison.

### When `clear()` Does Not Free Objects

`clear()` only removes references inside that collection. If somewhere else you have:

~~~java
// Illustrative snippet, NOT part of CollectionRootLab.java above.
static RetainedValue LAST_VALUE;
LAST_VALUE = someValueFromCache;
CACHE.clear();
~~~

then `LAST_VALUE` still keeps `RetainedValue` and `byte[]` alive. The same applies to `ThreadLocal`, listener registries, callbacks/closures, task queues, secondary caches, other static lists, or live local variables. **Do not assume objects are dead just because a map is empty**; inspect GC roots in the heap dump and check all remaining strong paths.

## 6. Opening HPROFs and Finding Suspects in Eclipse Memory Analyzer

**Eclipse Memory Analyzer (MAT)** is a heap dump analysis tool offering Histogram, Dominator Tree, Path To GC Roots, Leak Suspects, OQL, and snapshot comparison. On a machine with sufficient RAM/CPU, open:

1. `collection-retained-12345.hprof` — RETAINED state.
2. `collection-released-12345.hprof` — RELEASED state.

MAT needs to build indexes/parse the dump, consuming extra RAM and writing index files alongside the HPROF. For large heap dumps, use a dedicated analysis machine; never open them on a memory-starved production host.

### 6.1. Start with the Histogram

In the first snapshot, open **Histogram** (menu/button placement depends on MAT version). Search for classes:

~~~text
CollectionRootLab$RetainedValue
byte[]
java.util.HashMap
java.util.HashMap$Node
~~~

Logical expectation in the RETAINED dump: there are **64 instances** of `CollectionRootLab$RetainedValue` held by the map; those instances point to 64 payload arrays of 256 KiB each. The total `byte[]` histogram will be larger and include many other JVM/JDK arrays.

**Warning about counts:** MAT can display classes grouped by package, class loader, nested names, or other groupings. Never take the entire `byte[]` histogram as "exactly 16 MiB leaked", because only a subset of `byte[]` arrays belong to the lab. The class instance count, given the right stage and a valid heap dump, is a lead for deeper inspection.

In the second snapshot, search for `CollectionRootLab$RetainedValue` again. If zero live instances remain or the count drops as expected, that confirms dropping the references worked. Class metadata or the `HashMap` table may still remain; that **does not mean the 64 payloads are still retained**.

### 6.2. Use Dominator Tree to See "Indirectly Retained Memory"

Open **Dominator Tree** and sort by **Retained Heap**. Look for `CollectionRootLab`, `HashMap`, the `byte[]` region, or use **Top Consumers / Big Drops** if there are many classes.

Goal: identify an **accumulation point** — an object/structure keeping many values/payloads reachable. `HashMap` has a small shallow size, yet its retained set contains `HashMap$Node`, `RetainedValue`, and `byte[]` instances when no other strong reference path reaches those objects.

**Note:** the dominator tree reflects domination relationships in the object graph. Large retained heap might appear on the class object or collection root rather than immediately showing `HashMap` at the very top depending on sorting. Do not give up if the initial table does not show "16 MiB" at first glance.

## 7. Path To GC Roots: Tracing the Exact Retention Chain

This is the most important step for answering **"Why hasn't GC collected this object?"**

1. In the Histogram of the RETAINED snapshot, expand `CollectionRootLab$RetainedValue`.
2. Pick **any single instance**, such as instance id=0. Do not choose the class definition; choose an **object instance**.
3. Right-click and choose **Path To GC Roots** or **Shortest Paths To GC Roots** (exact menu wording varies by MAT version).
4. When prompted, select **Exclude Weak/Soft/Phantom References** to focus on strong retention paths. In this example, links through `HashMap` are strong, so they are preserved.
5. Expand the reference tree from root to instance; inspect the **field name** or reference label at each hop.
6. Follow further from `RetainedValue.payload` to a 256 KiB `byte[]` to verify the actual retained payload.

Expected logical chain:

~~~text
GC Root: class / system class (CollectionRootLab)
   |
   +-- static CollectionRootLab.CACHE
         |
         +-- java.util.HashMap
               |
               +-- table: HashMap$Node[]
                     |
                     +-- HashMap$Node
                           |
                           +-- value: CollectionRootLab$RetainedValue
                                 |
                                 +-- payload: byte[262144]
~~~

**This is an interpretation, not fixed MAT output.** The actual path may traverse a class mirror, class loader, different node/table fields, or show multiple GC roots. MAT returns shortest paths per query; **one shortest path does not prove it is the only path**.

### 7.1. "Path to GC Roots" vs. "Incoming References"

- **Incoming references** show which objects **point directly** to the selected instance. For example, a `HashMap$Node` has field `value` pointing to `RetainedValue`.
- **Path To GC Roots** walks backward *across multiple hops* to trace the reference chain connecting the object to a GC root. This answers "why is it still alive".
- **Dominator Tree** helps assess how much memory depends on a structure; it does not require every tree edge to be a direct field reference.

An object can have multiple incoming paths. If you clear only one map while the object also sits in a `ThreadLocal` or another static collection, MAT will reveal **the remaining root path**. That is why you should check multiple paths (or merged shortest paths across a group of instances) when suspecting multiple owners.

### 7.2. Why Exclude Weak/Soft/Phantom Paths?

Java has special reference types:

| Reference | Basic Effect | How to Read in MAT |
| --- | --- | --- |
| **Strong** | Keeps object normally reachable | Must find every strong path keeping the object alive |
| **WeakReference** | Does not prevent GC when only weakly reachable | Usually exclude weak `referent` paths when hunting leaks |
| **SoftReference** | GC may clear under memory pressure policies | Can exclude initially to prioritize strong chains, yet inspect if soft caches cause pressure |
| **PhantomReference** | Provides no strong reachability to referent; mainly for cleanup tracking | Do not treat phantom paths as strong owners |
| **Finalizer-related references** | Can affect death timing / cleanup eligibility | Analyze separately, especially in legacy code |

Depending on MAT and dump type, excluding weak/soft/phantom/finalizer references cuts down noise. **Do not exclude all special reference types blindly**: if the issue involves a `SoftReference` cache or a cleanup queue, that very reference type may be what you need to investigate.

## 8. Before/After Comparison to Confirm the Fix

Place the two heap dumps side by side and verify:

| Item | RETAINED Snapshot | RELEASED Snapshot | Interpretation |
| --- | --- | --- | --- |
| `CACHE.size()` | 64 | 0 | Code removed mappings |
| `CollectionRootLab$RetainedValue` live instances | Expected 64 | Expected none held by map | Verifies retention after dropping references |
| Lab-owned `byte[262144]` | 64 payload arrays | No longer retained via `CACHE` | Verify via incoming/paths, not `byte[]` class alone |
| `HashMap` object | Present | Still present | Static field still references the map object |
| `HashMap.table` | Table holding nodes | Table capacity may remain, entries empty | `clear()` is not required to shrink internal table |
| Owner's Retained Heap | Includes ~16 MiB payloads plus overhead | Drops dramatically | Do not demand exact 16 MiB equality |
| Total HPROF file size | Depends on whole JVM | Also depends on whole JVM | **Never** treat file size delta as exact retained size |

Two ways to compare:

- Open **Histogram** in both, filter for `CollectionRootLab$RetainedValue`, and compare **object count** and shallow heap.
- Use **Compare Snapshots** or compare **Dominator Tree/Leak Suspects** if supported by your MAT version. Ensure both snapshots come from the same JVM, same configuration, and correct chronological order.

Important: HPROF **does not store allocation timestamps for every object** and is itself a snapshot. One dump with 64 objects does not prove a "continuous leak". This lab creates intentional retention; the drop after `clear()` confirms the reachability principle rather than automatically diagnosing a specific production bug.

## 9. Why Calling GC Repeatedly Still Does Not Resolve Retention

Suppose a program allocates an object and stores it in a map:

~~~java
// Principle illustration, not a standalone runnable file.
byte[] payload = new byte[1024 * 1024];
sessionCache.put("user-42", payload);
payload = null;
System.gc();
~~~

Assigning `payload = null` only clears the **local reference**. `sessionCache` still holds a reference to the same array. GC cannot reclaim it while the map stays reachable from a GC root. The logical fix is removing the entry when its lifecycle ends:

~~~java
// Principle illustration, not a standalone runnable file.
sessionCache.remove("user-42");
// Or sessionCache.clear() when the entire cache may be evicted.
~~~

Once references are dropped, the object becomes **eligible** for GC reclamation; it does not mean the JVM immediately reduces OS RSS or returns committed heap to the OS. Heap used and OS resident memory are two distinct measurements.

### When Is `clear()` Still Not Enough?

1. **Another collection** also holds the object; e.g., `HISTORY.add(value)`.
2. **`ThreadLocal`** holds the object inside a long-lived thread pool.
3. **Listener/event bus registries** fail to unsubscribe callbacks.
4. **Scheduled tasks or executor queues** hold closures capturing the object.
5. **Another static field** or class loader is pinned by an unremoved registry/plugin.
6. **Local stack variables** are still live at capture time, especially if dumping inside a method still holding the reference.
7. **JNI global references** or native agents pin objects through JVM mechanisms.

Each case needs **Path To GC Roots** to identify the real owner rather than guessing by class name. Clearing `CACHE` yet still seeing objects in the next snapshot is a clue to investigate, not proof that GC "isn't working".

## 10. Practical Extension: How Real Leaks Happen in Service Code

Real applications rarely contain an obvious standalone `CACHE.put(...)`. Common business causes include:

- **Session caches without TTL/eviction**: users log out, yet objects stay in an ID-keyed map.
- **Unbounded-cardinality map keys**: caching by request ID or random UUID; every request creates a new key so the cache never reuses entries.
- **`ConcurrentHashMap`** used properly for thread safety but lacking eviction policy; a concurrent container **does not manage memory lifecycle automatically**.
- **Listener registries**: every request registers a callback object into a static list without unregistering.
- **`ThreadLocal` in thread pools**: requests end while pool threads live on; without `remove()` in `finally`, payloads remain pinned.
- **Backed-up queues**: producers outpace consumers; objects queued are validly reachable yet exceed processing capacity.

In particular, with `WeakHashMap`: only the **key** is weak; a value can reference its key back, preventing the key from ever being collected. Never replace strong maps blindly with `WeakHashMap` as a "leak-fix trick" when data lifetimes should be explicitly bounded.

### 10.1. Choosing Code Fixes by Root Path

| What Path To GC Roots Shows | Hypothesis to Verify | Appropriate Fix |
| --- | --- | --- |
| Static cache → map → old request values | Cache lacks eviction/TTL | Bound entry count, TTL/size limits, lifecycle cleanup |
| Thread → `ThreadLocalMap` → value | Thread pool reuses threads without cleanup | `try/finally` + `ThreadLocal.remove()` |
| EventBus/listener list → callback → owner | Listener never unregistered | Registration token / unsubscribe in `close()`/`destroy()` |
| Executor queue → `Runnable` → captured payload | Downstream stall or unbounded retries | Bounded queue, backpressure, timeouts, task cancellation |
| Static registry → class loader → classes | Hot redeploy/plugin classloader leak | Clear registries, threads, timers, listeners belonging to old classloader |
| Local stack variable → payload | Snapshot captured while method was still running | Wait until frame exits; review capture timing before declaring a leak |

Every fix must be verified under **comparable load** and fresh snapshots/metrics: object counts/retained sets drop as intended, post-GC heap stabilizes, and latency/throughput do not degrade from eviction logic.

## 11. A Practical Leak Investigation Workflow

### Step A — Establish the Symptom Over Time

Track **post-GC** heap used, GC logs/JFR, `-Xmx`, container RSS, throughput, and request mix. A valid cache warm-up raises memory once and then plateaus; that differs from a rising post-GC baseline under steady load.

### Step B — Take Snapshots at the Right Time Within Safety Budgets

Prefer reproducible staging/canary environments. If a production dump is necessary, `GC.heap_dump` is **High impact** and normally runs a Full GC; account for pause time, file size, disk I/O, permissions, and PII protection. Do not trigger repeated dumps every minute unthinkingly. Do not pass `-all` when testing *live reachable objects* in a retention comparison.

### Step C — Start from the Largest Consumers

In MAT, inspect **Overview, Histogram, Top Consumers, and Dominator Tree**. Do not stare only at `byte[]`: it appears heavily in nearly all Java apps; check who **owns** those arrays and most of the retained size.

### Step D — Trace Paths to GC Roots

Select an instance or accumulation point; open **Path To GC Roots**, usually excluding weak/soft/phantom references to reduce noise; read every reference field along the chain. Record root type, class, field, object count, and retained size. When multiple owners exist, inspect merged paths rather than just one shortest path.

### Step E — Cross-Check Application Logic

Is the reference valid or stale? Is the session still active? Has the request completed? Is TTL/eviction running? Does lifecycle cleanup unregister? The root chain explains **why the object stays alive**, while business knowledge determines **whether it should stay alive**.

### Step F — Verify the Fix

Run workload long enough past warm-up and compare two or more dumps under identical conditions alongside post-GC heap used. Large memory kept for a legitimate bounded cache differs from a memory leak. If references are released properly yet RSS does not drop immediately, the JVM and native allocator may keep committed heap; do not jump straight to blaming a leak.

## 12. Common Mistakes in the Lab and MAT Analysis

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| `jcmd 12345` fails to connect | Didn't replace example PID, process exited, different host/user/namespace, attach disabled | Use the real PID printed in terminal A; check permissions and environment |
| HPROF file missing in terminal B | Path opened on target JVM filesystem, different container mount, or missing permission | Check target machine/volume, directory, disk quota |
| File already exists error | `GC.heap_dump` does not overwrite by default | Choose a new filename; never delete important evidence |
| First dump lacks 64 `RetainedValue` | Captured after pressing Enter, wrong PID/file, weird `-all`/settings | Follow sequence strictly; verify "Stage=RETAINED" |
| Second dump still shows many `byte[]` | JVM/JDK has many other byte arrays | Filter `RetainedValue` and payload paths, not all `byte[]` |
| `CACHE.size()=0` yet heap did not drop completely | Map table capacity, JVM baseline, committed heap, or other references | Inspect retained set/paths; compare post-GC used rather than RSS alone |
| `RetainedValue` still reachable after `clear()` | Object still held by local/`ThreadLocal`/listener/another static owner | Run Path To GC Roots on that exact instance and analyze each owner |
| Map Retained Heap does not equal 16 MiB | Headers/alignment/other paths, GC roots, and dominator accounting | Inspect individual payloads, references, shared ownership; do not force 16 MiB |
| MAT throws `OutOfMemoryError` | Parser/indexing needs memory; dump too large | Increase MAT heap or run on an analysis machine with sufficient RAM; avoid production hosts |
| MAT shows multiple shortest paths | One instance has multiple owners or equivalent paths | Inspect multiple paths; separate strong from weak references |
| MAT path does not match diagram line-for-line | JDK version, class loader, parser, and internal `HashMap` implementation differ | Follow `CACHE`/`value`/`payload` fields rather than matching exact text lines |
| Heap dump file size differs from expectation | HPROF contains runtime metadata, class records, different object layouts | Never treat file size as exact retained heap |
| Creating a dump stalls the service | Dump is High impact, runs Full GC and disk I/O | Lab only; production requires change/incident approval |
| Later analysis gets mixed up with earlier run | Opened wrong file, same PID after JVM restart, missing timestamps | Use distinct filenames; record PID/time/JDK build and artifact hashes |

### Naming and Protecting Artifacts

HPROF files can contain passwords, API tokens, session data, URLs, and business object contents. Name files with **environment, JVM/PID, timestamp, and state**, restrict read access, encrypt in transit/at rest, and delete per retention policy. Never upload real production heap dumps publicly for help without redacting/auditing sensitive data.

## 13. Self-Check Questions

**Question 1.** The program called `System.gc()`, yet `CACHE` still holds 64 values. Why haven't the arrays disappeared?

*Answer:* `CACHE` is a static collection still reachable from class/JVM roots; the map holds nodes, each node holds a value, and each value holds an array. While a strong path exists from a GC root, GC cannot collect those arrays.

**Question 2.** In MAT, `HashMap` shows only tens of bytes of shallow heap, yet its retained heap can be huge. Is that a contradiction?

*Answer:* No. Shallow size measures the `HashMap` object itself; retained size includes objects kept alive exclusively via paths through the map, such as nodes, values, and payload arrays.

**Question 3.** Why inspect Path To GC Roots instead of looking only at the `byte[]` Histogram?

*Answer:* The Histogram shows object counts per class, not **who holds** each object. Path To GC Roots reveals the owner through the reference chain, such as the class's static `CACHE`.

**Question 4.** After `CACHE.clear()`, the second HPROF still contains many `byte[]` objects. Did the lab fail?

*Answer:* Not necessarily. The JVM and runtime still hold many `byte[]` arrays. Inspect `CollectionRootLab$RetainedValue` instances and their payloads rather than taking the whole `byte[]` class as the lab result.

**Question 5.** Is a GC root path from a static cache to a session enough to prove a memory leak?

*Answer:* Not yet. It proves the object **is currently retained**. You must compare against session lifetime, cache bounds, retained-set growth rate, and whether cleanup occurs when expected.

**Question 6.** Does passing `jcmd GC.heap_dump -all` to "capture everything" make sense in a before/after retention test?

*Answer:* Not recommended. `-all` includes unreachable objects and skips the default Full GC. That can leave already-eligible dead objects in the dump, adding noise when your goal is finding objects still kept alive.

## References

- Oracle JDK 21 — **The jcmd Command**, `GC.heap_dump`, `-all`, High impact, filename parameter: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — **Troubleshoot Memory Leaks**, live set, strong references retained in collections, and leak analysis: https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html
- Eclipse Memory Analyzer — **Basic Tutorial**, Histogram, Dominator Tree, Path To GC Roots: https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/gettingstarted/basictutorial.html
- Eclipse Memory Analyzer — **Path to GC Roots**, exclude filters and reference paths: https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/inspections/path_to_gc_roots.html
- Eclipse Memory Analyzer — **Shallow vs. Retained Heap**, retained set definition: https://help.eclipse.org/latest/ntopic/org.eclipse.mat.ui.help/concepts/shallowretainedheap.html
- Eclipse Memory Analyzer — **Dominator Tree**, domination relation vs. reference graph: https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/dominatortree.html
- Eclipse Memory Analyzer — **Leak Suspects Report**, suspect hints rather than standalone proof of bugs: https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/tasks/runningleaksuspectreport.html