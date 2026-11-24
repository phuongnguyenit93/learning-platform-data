# 12.8 Distinguishing Shallow Size from Retained Size and the Role of Dominators

## 1. Why Do These Two Numbers Govern How You Read a Heap Dump?

When opening a Java heap dump in Eclipse Memory Analyzer (MAT) or an equivalent tool, you typically see two columns: **Shallow Heap / Shallow Size** and **Retained Heap / Retained Size**. They answer two distinct questions:

- **Shallow size:** *How many bytes does this object itself occupy on the Java heap?*
- **Retained size:** *How many heap bytes does this object keep alive—counting itself plus any objects that would lose all retention paths if it were no longer referenced?*

For example, a cache manager object may take only a few dozen shallow bytes, yet retain a graph spanning hundreds of MB. Conversely, an object pointing to a 100 MB array **does not necessarily** gain 100 MB in retained size if that array is also kept alive by another branch.

The **dominator tree** computes and reveals the memory **exclusively** kept alive by an object within the reference graph at dump time. Without understanding dominators, it is easy to double-count memory, confuse "holds a reference" with "exclusively retains," or declare a memory leak solely from a large retained value.

This lesson focuses on the **Java heap**: object sizes, arrays, reference relationships, and GC roots within a snapshot. A Java heap dump is not a complete measurement of process RSS, direct/native memory, Metaspace, or off-heap allocations.

## 2. Three Concepts to Keep Separate

### 2.1. Shallow size — the size of the object itself

A Java object requires memory for its header, the fields stored directly inside that object (primitive values or **reference slots**), and padding/alignment if any. Shallow size **does not add the sizes of objects referenced by its fields**.

For arrays, elements live inside the array object itself, so:

- `byte[1_000_000]` has a shallow size of roughly 1,000,000 bytes **plus header and alignment**; never assert an exact byte figure without knowing the JVM layout.
- `int[1_000_000]` holds roughly 4,000,000 bytes of primitive data, plus header/alignment.
- `Object[1_000_000]` contains one million **reference slots** in its shallow size. If one slot points to a 5 MB object, **those 5 MB are not automatically added** to `Object[]`'s shallow size.
- `ArrayList` is a separate object; its backing `Object[]`, its elements, and downstream graphs are separate objects.
- `String` is a separate object; its backing character/byte array, where present, is a separate object according to that JDK's layout.

Header details, reference sizes, pointer compression (`UseCompressedOops` and related settings), alignment, array type, JVM/JDK, and dump format all affect actual shallow sizes. A rule of thumb like "object header is always 12 bytes, reference is always 4 bytes" **is not true for every JVM**.

Illustration:

```java
final class Box {
    byte[] payload = new byte[1024 * 1024];
}
```

This is an **illustrative snippet, not a standalone program**. The `Box` object has a tiny shallow size because its `payload` field holds only a reference. The `byte[]` array holds the ~1 MiB payload. If that array has only a single retention path through `Box`, then `Box`'s retained size will be much larger than its shallow size; if the array has another independent retention path, the result differs.

### 2.2. Reachable graph — everything reachable via references

Let `Reach(X)` denote the set of objects reachable from X along directed reference edges in the graph. This concept **follows references outward from an object to everything it points to**.

However, just because X points to Y **does not mean Y will be collected if X disappears**. Another object Z might also point to Y, or Y may have another path from a GC root. Therefore, **the sum of shallow sizes across all of `Reach(X)` is not X's retained size**.

### 2.3. Retained size — the heap exclusively kept alive

In graph terms, given the set of nodes reachable from GC roots under the tool's reachability rules:

- `RetainedSet(X)` consists of X and all objects for which **every path from a GC root to them passes through X**.
- `RetainedSize(X) = Σ ShallowSize(Y)` for all `Y ∈ RetainedSet(X)`.

Retained size is the **sum of shallow sizes of a specific object set**, not an independent measurement of a "physical subgraph." It is commonly interpreted as the Java heap space *potentially* freed if **all retention paths to X were removed**, while all other retention paths stayed intact and GC ran.

Within a snapshot, an object's retained size is never less than its own shallow size because its retained set includes X by definition. Yet retained size can be **far lower** than the total size of all objects X points to due to shared references.

| Property | Shallow size | Retained size |
| --- | --- | --- |
| Scope | Object X alone: header, fields, array elements, padding | X and objects **dominated** by X |
| Question answered | "How much does this object itself occupy?" | "How much does this branch exclusively keep alive?" |
| Counts referenced objects? | No | Yes, **only if no path from a root bypasses X** |
| Typical large examples | Large `byte[]`, `int[]`, `Object[]` arrays | Cache managers, root maps, session managers, class loaders, thread holders |
| Equals `.hprof` file size, RSS, or `-Xmx`? | No | No |
| Proves a memory leak? | No | No; must compare with business lifecycle and further evidence |

## 3. GC Roots and Why "Who Keeps Whom Alive" Matters

The garbage collector starts from **GC roots**: anchors the VM treats as live, such as references on thread stacks, static fields of active classes, JNI handles, and other runtime structures. From roots, it follows valid references to mark reachable objects.

In a heap dump, an object may have many **incoming references** from different places. A path `GC root → ... → object` explains why the object remains on the heap. Do not confuse these terms:

- **Outgoing reference:** X has a field or array slot pointing to Y.
- **Incoming reference:** another object points to X.
- **Path to GC roots:** one or more chains walking backward from X to a root.
- **Dominator:** a node sitting on **every** path from root to another node; a stricter condition than merely "having a reference."

Tools may handle `WeakReference`, `SoftReference`, `PhantomReference`, and unreachable objects differently. When verifying why an object stays alive, note options to exclude weak/soft paths and the snapshot's reachability rules; **an edge shown in a dump is not automatically a strong reference blocking GC**.

## 4. Dominators: Definition, Immediate Dominators, and the Dominator Tree

Imagine adding a **virtual super-root** connected to every GC root under consideration. In the directed graph rooted at super-root:

> Node A **dominates** node B when **every path** from super-root to B passes through A.

Every node is considered to dominate itself. If A ≠ B and A dominates B, A is a **strict dominator** of B. B's **immediate dominator**, written `idom(B)`, is the strict dominator closest to B. Every reachable object (except super-root) has a unique immediate dominator in this tree construction.

The **dominator tree** connects each node B to `idom(B)`. It has key properties:

1. Nodes in **A's subtree** are precisely the objects dominated by A—that is, A's retained set.
2. Summing shallow sizes of nodes in A's subtree yields A's retained size.
3. **An edge in the dominator tree is not necessarily a direct reference edge in the Java program.** It expresses a retention-dependency relationship. To see which fields point where, inspect incoming/outgoing references or paths to GC roots in the **original object graph**.
4. Two sibling branches in the dominator tree have disjoint retained sets; by contrast, the retained sets of **parent and child overlap**. Never sum retained sizes of parent and child when totaling heap usage, or you will double-count.

### 4.1. Graph example with a shared object

Suppose seven objects have **hypothetical** shallow sizes (unit B is purely for hand calculation, not real JVM header/layout numbers). There are two independent root paths:

```text
GC root R1 ──> A:Cache(40) ──> B:Map(64) ──> C:Entry(24) ──> D:Payload(1024)
                    │
                    └──────────────────────────┐
                                               v
                                          S:Shared(512)
                                               ^
                    ┌──────────────────────────┘
                    │
GC root R2 ──> E:Service(48) ───────────────────┘
                    │
                    └────────────> F:Audit(256)
```

There are two paths to `S:Shared`: `R1 → A → S` and `R2 → E → S`. Hence neither A **dominates** S nor E **dominates** S. Conversely, every path to D passes through A, B, and C; thus A, B, and C all dominate D.

**Resulting dominator tree:**

```text
super-root
├── A:Cache
│   └── B:Map
│       └── C:Entry
│           └── D:Payload
├── E:Service
│   └── F:Audit
└── S:Shared
```

Notice the edge `super-root → S` is a **dominance edge in the tree**, not a literal field reference in the program. An object with multiple incoming references from two branches often surprises analysts when it appears outside both branches' subtrees.

### 4.2. Hand calculation without double-counting

| Object | Hypothetical shallow | Retained set | Retained size |
| --- | ---: | --- | ---: |
| D:Payload | 1,024 B | D | 1,024 B |
| C:Entry | 24 B | C, D | 1,048 B |
| B:Map | 64 B | B, C, D | 1,112 B |
| A:Cache | 40 B | A, B, C, D | **1,152 B** |
| F:Audit | 256 B | F | 256 B |
| E:Service | 48 B | E, F | **304 B** |
| S:Shared | 512 B | S | **512 B** |

The total shallow size of all seven objects is `40 + 64 + 24 + 1024 + 48 + 256 + 512 = 1968 B`. Meanwhile, the set **reachable from A** consists of A, B, C, D, and S, totaling `1664 B`. Yet A's retained size is only `1152 B` because S remains kept alive by E even if A is no longer retained.

Removing only root path `R1 → A` theoretically frees **1,152 B**, while S stays alive via E. Removing only `R2 → E` can free **304 B**. Removing **both** paths simultaneously leaves S unretained too, allowing all seven objects (`1,968 B`) to be reclaimed. The combined result **does not equal simple addition** `retained(A) + retained(E)`, because the group of two objects has a shared retained set larger than the sum of their individual retained sets.

Likewise, never add `retained(A) + retained(B)` because B, C, and D belong to **both** retained sets. In a tree, a parent node's retained value already includes its children's retained values.

### 4.3. Two misleading counterexamples

**Holds a reference but does not dominate:** A points to S and E also points to S. A has an outgoing reference to S, yet does not exclusively retain S. Finding an `A.shared` field pointing to S is not enough to add S into `retained(A)`.

**Has a cycle but is not necessarily a leak:** A points to B and B points to A. If a GC root reaches A and then B, A may dominate B; if **no path from GC roots reaches either**, GC can collect the cycle. Java GC does not rely purely on reference counting, so a reference cycle alone is not proof of a leak.

## 5. Reading Retained Size Properly in Eclipse Memory Analyzer (MAT)

### 5.1. Histogram answers "which object types are numerous?"

Open the heap dump and select **Histogram**; inspect `Class Name`, `Objects`, and `Shallow Heap`. For objects of the same class, shallow heap is typically the sum of shallow sizes for that group's instances. For instance, a million `byte[]` or many `HashMap$Node` objects can occupy substantial space, yet a histogram cannot answer **who keeps them alive**.

The retained column at the **object-set / class** level may require running a separate calculation; MAT distinguishes computing **Minimum Retained Size** (a faster lower bound) from computing exact retained size for a set. **Never sum retained sizes of individual instances or classes to get total heap:** retained sets can overlap, and the same object can be dominated by multiple ancestors at different depths.

### 5.2. Dominator Tree answers "which anchor retains a large heap slice?"

Select **Dominator Tree**, typically sorted by **Retained Heap** descending. Expand large subtrees to examine retention structure:

- A manager/cache object with **tiny shallow size and huge retained size** may be holding references to large volumes of data.
- A `byte[]` with **large shallow size** will also have retained size roughly equal to its shallow size, yet fixing the issue requires walking backward to find **the object, collection, or root keeping that array alive**.
- A cache retaining many objects may be **legitimate** behavior if bounded with expiration policies. Large retained size shows **how much is currently kept**, not **retention past business expiration**.

In the Dominator Tree, click a suspect object and inspect **outgoing references** to see the components it points to; inspect **incoming references / Path to GC Roots** to see why it stays alive. **The Dominator Tree is a map of retention dependencies, whereas Path to GC Roots and references are evidence of actual reference edges.**

### 5.3. Path to GC Roots: finding the true retention path

For a suspect object or collection:

1. Select the object in MAT and open **Path to GC Roots**; where appropriate, use the tool's **exclude weak/soft/phantom references** variant to focus on strong retaining paths.
2. Identify the relevant root: static field, live thread, `ThreadLocal` chain, JNI global ref, class loader, session/cache registry, listener, executor queue, etc.
3. Read each field and container along the path; determine which object **should have ended its lifecycle** yet remains referenced.
4. If **multiple paths exist from different roots**, severing one path may not free the object. That explains why one branch's retained size can be smaller than the total objects it can reach.
5. Map the reference path to business flow: when are entries added, who removes them, is there a TTL/size cap, and do threads/loaders terminate?

**Proper interpretation example:** a `static Map<Id,Session>` holds 200,000 sessions while only about 10,000 sessions are active. If path to roots runs through the static map, the map's retained size is huge, and counts climb over time, the missing-eviction hypothesis is well supported. Still verify session policy, traffic, and entry age; a single snapshot does not prove a leak.

## 6. Hands-On with Java 17+ and an HPROF Containing a Shared Object

The example below creates two holders, each with a **private array**, both pointing to **one shared array**. Static fields keep the holders alive so they can be observed in a dump. The program runs standalone on JDK 17+; an interactive terminal is needed to keep the process alive.

Save as `RetainedSizeLab.java`:

```java
public final class RetainedSizeLab {
    private static volatile Holder cache;
    private static volatile Holder service;

    static final class Holder {
        final byte[] unique;
        final byte[] shared;

        Holder(byte[] unique, byte[] shared) {
            this.unique = unique;
            this.shared = shared;
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] common = new byte[512 * 1024];

        cache = new Holder(new byte[1024 * 1024], common);
        service = new Holder(new byte[256 * 1024], common);

        // Drop the extra local reference; both holders still retain common together.
        common = null;

        System.out.println("Heap graph ready");
        System.out.println("Press Enter to stop");
        System.in.read();
    }
}
```

Compile and run in the **first terminal**:

```bash
javac RetainedSizeLab.java
java -Xms128m -Xmx128m RetainedSizeLab
```

Stdout before pressing Enter, **exact for this program**:

```text
Heap graph ready
Press Enter to stop
```

Keep the program paused at the prompt. Open a **second terminal** and find the application PID:

```bash
jcmd -l
jcmd 12345 GC.heap_dump retained-size.hprof
```

Replace `12345` with the actual PID from `jcmd -l`. `GC.heap_dump` produces an HPROF file; on JDK 21, it requests a **full GC before dumping** by default unless `-all` is selected. This command has high impact and can cause a long pause; run only in an appropriate environment and window. Ensure the dump path is writable with adequate disk space. Relative filenames resolve in the target JVM's context; prefer absolute paths for easier artifact management. Dumps can contain sensitive data, so control access permissions.

**Expected observations in MAT, without asserting fixed byte figures:**

- Two `RetainedSizeLab$Holder` instances exist, retained via static fields `cache` and `service`.
- `cache`'s unique array has **1,048,576 byte elements**, and `service`'s has **262,144 byte elements**; both have large shallow sizes matching payload plus header/alignment.
- The `common` array has **524,288 byte elements** and has at least two reference paths from the two holders. In the object graph, both `cache.shared` and `service.shared` lead to the **same `byte[]` object**, not two distinct arrays.
- In the dominator tree, `common` is **not inside the exclusive retained set** of either `cache` or `service`, because a retention path exists through the other holder.
- Each `Holder` has a tiny shallow size compared to the retained size of its unique array. **Exact retained values** are also affected by JVM layout, root/class metadata, thread stacks at dump time, and how MAT interprets the snapshot; observe the real figures rather than plugging in numbers from the hypothetical diagram in Section 4.

To compare:

1. Open `retained-size.hprof` in MAT and locate `RetainedSizeLab$Holder` in the Histogram.
2. Switch to Dominator Tree and inspect where the two holders and their `byte[]` arrays appear.
3. Inspect outgoing references on both holders and verify the object identity of `shared`.
4. On the shared array, run Path to GC Roots and observe multiple retention paths.
5. If you modify the program so only **one holder** points to `common`, take **a new dump** and compare: `common` can then move into that remaining holder's retained set. Inspect actual root paths, since stack state, JIT, and tool root-building also influence results.

**Why not measure retained size with `Instrumentation.getObjectSize`?** That method returns only the shallow storage size of the **passed object** under the JVM implementation; it **does not recursively compute graph traversal, reachability, GC roots, or dominators**. Its result is no substitute for heap-graph retained size analysis.

## 7. Three Calculation Mistakes That Lead to Wrong Conclusions

### Mistake 1: "Sum of outgoing objects = retained size"

If X holds references to Y and Z, you add `shallow(X) + shallow(Y) + shallow(Z)`. That merely sums a subset of reachable nodes, potentially **missing** deeper nodes while **miscounting** shared nodes. You must identify which objects are genuinely **dominated by X**.

### Mistake 2: "Sum the retained sizes of the top rows to get total heap usage"

Suppose A dominates B and B dominates C. Then:

- `retained(A)` **already includes** `shallow(B)` and `shallow(C)`.
- `retained(B)` **already includes** `shallow(C)`.
- Summing `retained(A) + retained(B) + retained(C)` counts C three times.

To measure the total memory of **a set of objects**, determine the retained set of **the whole set** and take the deduplicated union, or sum appropriate independent branches. In MAT, computing the retained size of a group of objects is a different operation from simply adding column rows.

### Mistake 3: "Large retained size proves a memory leak"

A 2 GB cache can be completely valid if designed with a 2 GB cap and active demand. By contrast, a 20 MB listener map can be a leak if it retains tens of thousands of listeners already unsubscribed in business logic. Retained size shows **heap impact of keeping objects alive**, whereas a leak concerns **unintended lifetime**, requiring time, context, and evidence of growth/non-release.

## 8. Practical Scenarios: Reasoning Correctly from a Heap Dump

### 8.1. `HashMap`, `ArrayList`, caches, and session stores

A manager may hold a `Map`, entry objects, keys/values, bucket arrays, strings, and payloads. The manager's shallow size is tiny; its retained size can be large if nothing else holds most of those entries. When investigating:

- Check entry count, capacity, record age, hit/miss ratio, or genuinely active session count.
- Inspect the **dominator** to locate the manager/collection holding major capacity.
- Inspect **Path to GC Roots** to see what keeps the manager alive (singleton, static, thread, component/container).
- Check eviction/TTL/size-limit policies; a large map is not automatically a leak.

In particular, an **oversized backing array** can consume shallow memory even with few active elements. That calls for a different optimization than a leak of unneeded objects.

### 8.2. `ThreadLocal` and thread pools

A worker thread can outlive individual requests. If request data is attached to a `ThreadLocal` and never cleared, path to roots can go through the thread, `ThreadLocalMap`, and value; retained size can stay large even after the request finishes. When the lifecycle contract requires cleanup, use `try/finally` to call `remove()`.

Do not assume that merely dropping the `ThreadLocal` key variable frees all values immediately: `ThreadLocalMap`'s stale-entry cleanup and other references must be evaluated in context. Analyze the **actual retention chain in the snapshot**.

### 8.3. Listeners, callbacks, executor queues, and class loaders

- Listeners remaining in a list after the registering screen or object has closed can retain large view models or payloads.
- Tasks queued in an executor can retain large request contexts while waiting.
- Class loaders that fail to unload can pin class metadata and static references of loaded classes. When investigating redeploy/plugin leaks, examine the **class loader tree**, GC roots, thread context class loaders, and linked objects.
- When multiple managers share references, do not blame the entire shared subtree on the first manager you inspect.

### 8.4. One dump vs. multiple dumps

A heap dump is only a **snapshot**. It shows who holds objects alive **at that moment**; it generally **does not show the stack trace where an object was allocated**. To investigate trends:

1. Capture at comparable workload points after warm-up.
2. Compare class counts, total shallow sizes, retained roots/subtrees, and data age distribution.
3. Correlate with GC logs, post-GC heap / live set, JFR allocation events, profilers, traffic, cache policies, and throughput.
4. Identify object groups climbing steadily without being freed according to lifecycle.
5. Verify after a fix that the abnormal retained set/root path disappeared and memory/latency improved.

Values between dumps can shift due to dump timing, pre-dump GC, thread stacks, or how tools strip unreachable objects. **Never treat the difference between two retained sizes as sole proof of the exact leak rate.**

## 9. Reading Results: A Repeatable Investigation Workflow

| Step | Where to look | Question to answer | Signal to advance |
| --- | --- | --- | --- |
| 1 | Overview, Histogram | Which object types fill the heap? Where is large shallow memory concentrated? | A class/array group occupies notable space |
| 2 | Dominator Tree | Which object/manager exclusively retains the largest subtree? | Specific technical owner with high retained size |
| 3 | Outgoing References | Which maps, entries, arrays, and payloads does the owner hold? | Understand subtree structure and footprint |
| 4 | Incoming References, Path to GC Roots | Which root prevents GC of the owner? Are there multiple independent paths? | Identify the real reference chain |
| 5 | Domain lifecycle | Should those objects still be alive? Are TTL, close, unregister, remove working? | Hypothesis of retention past lifecycle |
| 6 | Time tracking, profiler/JFR | Does the set accumulate under constant load, and where is it allocated? | Strong enough evidence to fix root cause |
| 7 | After fix | Did retained subtree, post-GC heap, and CPU/latency drop? | Confirm effectiveness with independent measurements |

**Deciding where to fix:** retained size only helps **prioritize where memory sits**. Root path shows who holds the reference; the allocation site may live elsewhere; the leak cause might be forgetting to remove from a map, forgetting to unregister a listener, missing cache TTL, non-terminating threads, or buffering excessive data. Connect all three: **retained subtree → root path → application lifecycle rules**.

## 10. Limitations and Caveats When Using Metrics

- **Heap dump ≠ RSS:** dumps focus on the Java object graph. Direct `ByteBuffer`s, native allocations, off-heap thread stacks, code cache, Metaspace, and VM overhead are not fully reflected as OS memory.
- **Snapshot ≠ timeline:** to learn when and on which stack objects were created, combine with JFR/allocation profilers; retained size carries no allocation history.
- **GC roots and reference types:** weak/soft/phantom references, JNI, and thread stacks have distinct semantics. Some objects in a dump may be unreachable under analysis settings or collected right afterward.
- **JVM layout is not absolute:** comparing shallow sizes across different JDKs/configs requires checking compressed oops, object alignment, collector/build, and parser interpretation.
- **Default dumps impact the system:** `jcmd GC.heap_dump` on JDK 21 usually requests a full GC and consumes CPU/I/O/disk; `-all` is not a "free dump" and also includes unreachable objects.
- **Security:** heap dumps can contain tokens, access strings, customer data, and sensitive objects. Store/share only within authorized boundaries, and delete or protect dumps once investigation concludes.
- **Dump file size ≠ retained size:** HPROF includes class tables/metadata and its own encoding; compressed or uncompressed file size does not directly equal total shallow heap.

## 11. Self-Check Exercise

**Question 1.** A points to B, B points to C, but a second root also points directly to C. Does A dominate C?

*Answer:* No. There is a path from the second root to C that bypasses A. A can reach C, but does not exclusively keep C alive.

**Question 2.** A `Controller` object has 48 B shallow size and 250 MiB retained size. Can we conclude the controller itself occupies 250 MiB?

*Answer:* No. 48 B is the controller's shallow size; 250 MiB is the sum of shallow sizes of the controller and all objects it dominates in the snapshot. Expand the subtree to see which objects occupy most of that space.

**Question 3.** A dominates B, with `retained(A) = 80 MiB` and `retained(B) = 60 MiB`. Can we say these two objects "use 140 MiB"?

*Answer:* No. B's 60 MiB is already included inside A's 80 MiB. Adding them double-counts.

**Question 4.** If a `HashMap` has 500 MiB retained size, what must be checked before calling it a leak?

*Answer:* The GC root/path keeping the map alive, entry count and types, TTL/eviction policy, legitimate business entry count, changes across multiple snapshots, and GC/live-set trends.

**Question 5.** Why might process RSS not drop immediately after clearing a reference field?

*Answer:* Other retention paths may exist; GC may not have run/reclaimed yet or heap stays committed; RSS also includes native/off-heap memory and heap regions the JVM retains for reuse. Retained size predicts retention structure in the snapshot, not immediate RSS reduction.

## 12. Checklist for Heap-Growth Incidents

- [ ] Distinguished object/array **shallow** size from subtree **retained** size.
- [ ] Understood retained size comes from the **dominator tree** and never double-counted parent/child retained sizes.
- [ ] Verified **every path to the object passes through the dominator**; checked for shared references.
- [ ] Opened **Path to GC Roots** and inspected real fields/reference chains.
- [ ] Checked **weak/soft references**, stack/static/JNI roots, and relevant parser settings.
- [ ] Mapped numbers to **business lifecycle**: caches, sessions, listeners, `ThreadLocal`, queues, class loaders.
- [ ] Separated **Java heap** from direct/native/RSS and **snapshots** from trends over time.
- [ ] Recorded **before/after** evidence and a plan to re-measure after the change.

**Key takeaway:** *shallow size* measures the footprint of **one object**; *retained size* measures the Java heap that object **exclusively keeps alive** in the snapshot; **dominator** is the graph condition that pinpoints that retention relationship. When seeing large retained sizes, use the **dominator tree** to locate memory regions, **path to GC roots** to find retention paths, and **business lifecycle** to judge whether a leak exists.

## Reference Documentation

- Eclipse Memory Analyzer — [Shallow vs. Retained Heap](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/shallowretainedheap.html).
- Eclipse Memory Analyzer — [Dominator Tree](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/dominatortree.html).
- Eclipse Memory Analyzer — [Path to GC Roots](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/inspections/path_to_gc_roots.html).
- Eclipse Memory Analyzer — [Basic Tutorial / Histogram and Dominator Tree](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/gettingstarted/basictutorial.html).
- Eclipse Memory Analyzer — [Heap Dump](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/heapdump.html).
- Oracle JDK 21 — [jcmd: GC.heap_dump](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
