# Generational ZGC: Mechanisms and Mode/Option Changes Across JDK Versions

## Lesson Objectives

**ZGC (Z Garbage Collector)** is a HotSpot garbage collector aimed at **low pause latency** by performing most of the GC work concurrently with application threads. ZGC initially used a **non-generational** model: processing the heap without dividing objects into two young/old generations in the manner of generational collection. **Generational ZGC**, introduced in **JDK 21 via JEP 439**, adds the ability to collect young objects more frequently without having to process the entire set of old objects in every cycle. Subsequently, the default mode and **the very JVM flags used to select the mode** changed across JDK 23, 24, and 26.

This is the easiest detail to misapply when upgrading the JDK: a command with `-XX:+ZGenerational` is required on **JDK 21** to actively select generational mode, but it should not be carried over as-is into a shared configuration for **JDK 26**.

After this lesson, you will be able to:

- Distinguish **ZGC** from **Generational ZGC**, generational GC from concurrent GC, and GC pause from end-to-end request latency.
- Explain **young/old generations, object survival, promotion/tenuring, remembered references, and barriers** without mistakenly assuming that Java source has fixed heap addresses.
- Recount the milestones **JDK 11 → 15 → 17 → 21 → 22 → 23 → 24 → 25 → 26** accurately, especially JEP 439, 474, and 490.
- Write the correct ZGC selection command for each stage; distinguish **enabled/disabled, deprecated, obsolete, and removed/expired options**.
- Understand the cost of **store barriers** and how classifying old-to-young references helps the collector avoid scanning all old objects when processing young.
- Tune safely using **-Xmx, -Xms, SoftMaxHeapSize, ZUncommit/ZUncommitDelay, and GC logging**, without using outdated flags.
- Design verification using `java -version`, `-Xlog:gc*`, `jcmd`, JFR, and A/B testing with SLAs.
- Run Java 17+ examples with deterministic output, knowing clearly that the examples do not guarantee triggering a specific type of GC cycle.

## 1. What Is ZGC? What Makes It Different From Other GCs?

With collectors oriented toward **Stop-The-World (STW)**, certain large mark/copy/compact workloads occur while application threads are paused. ZGC tries to move most of the expensive work into **concurrent phases** to reduce the pause time perceived by users.

Key points:

1. **Concurrent** does not mean completely pause-free. ZGC still has short synchronization/safepoint phases by design and in the actual implementation of each HotSpot release.
2. **Low pause** is not **zero overhead**. Marking/relocation, GC worker threads, and load/store barriers consume CPU, cache, memory bandwidth, and heap headroom.
3. ZGC **is not the default collector of every JVM**. For many HotSpot server configurations, the default is still G1; only use `-XX:+UseZGC` when you want to select ZGC.
4. A collector that handles multi-GiB heaps well is not automatically suitable for a microservice with only 1 vCPU and a tight memory limit.
5. **Non-generational** and **generational** are two algorithmic modes in ZGC's history; they are not two independent public GC names like `UseZGC` and `UseG1GC`.

ZGC appeared as an experimental feature in JDK 11 (JEP 333) and became a production feature in JDK 15 (JEP 377). Before JDK 21, ZGC's mode in upstream OpenJDK/HotSpot was **non-generational**. Generational mode was added afterward, and then gradually replaced the non-generational algorithmic path entirely.

## 2. Why Add Generations to ZGC?

The *generational hypothesis* states that in many real-world workloads, **most newly created objects become unreachable fairly quickly**, while a subset of objects live long. If the same set of old objects had to be processed in every GC run simply because many temporary young objects appear, the collector could end up doing a lot of unnecessary work.

Model:

~~~text
     Application allocations
               |
               v
       YOUNG GENERATION
       new / young-age objects
               |
          Young collection
          /           \
         v             v
    Dead: reclaim   Survivors
                       |
              may stay in young
              or be PROMOTED
                       |
                       v
              OLD GENERATION
              long-lived objects
                       |
              Old/major collection
              per ZGC's policy
~~~

This is a **semantic diagram**; it does not require ZGC on every release to use the exact same layout as G1/Eden/Survivor/Old regions. ZGC has its own memory organization and way of tracking generations; **do not** take G1's region names and infer ZGC's byte layout.

### Young collection

A young collection cycle focuses on the young area and the references needed to know which young objects are still reachable. Many short-lived objects can be reclaimed without processing the entire old generation like a full-heap traversal.

### Old collection

The old generation still needs collection. Long-lived objects in caches, queues, or large graphs do not become garbage on their own; old collections run according to the collector's heuristics/scheduling. Having generations **does not** cure a memory leak where objects remain reachable from static fields/GC roots.

### Promotion and adaptive heuristics

Objects that survive collections may be kept in young or moved to old depending on policy, age, space, and allocation pressure. Generational ZGC is designed to **self-adapt** to load, generation sizes, and tenuring thresholds. Do not infer that an object "surviving exactly 3 young GCs will always move to old" on every JDK, or a fixed threshold equivalent to G1.

## 3. The Major Challenge: References From Old to Young

Suppose there is a long-lived `SessionCache` object in the old generation:

~~~java
static final class SessionCache {
    byte[] currentPayload;
}
~~~

This is an **illustrative class**, not a standalone program. When the program runs:

~~~java
cache.currentPayload = new byte[1024];
~~~

if `cache` is already in old while `new byte[1024]` is a young object, we create an **old-to-young edge**:

~~~text
OLD                         YOUNG
+------------------+        +----------------+
| SessionCache     |        | byte[1024]     |
| currentPayload --+------->| new payload    |
+------------------+        +----------------+
~~~

If a young collection only directly scans **young roots** and ignores references from old, it could wrongly conclude that the payload is unreachable. This is why a generational collector must maintain enough information to **find/track references across generations**.

### Store/write barrier

When a mutator writes a reference into a field or array element, a **store barrier** can notify the collector/record the necessary information about the graph. Generational ZGC adds appropriate store barriers to track generational relationships, alongside the load barrier logic that is already central to ZGC.

Concepts:
- **Write/store barrier:** VM code or handling path around certain reference writes, helping the GC keep metadata accurate.
- **Load barrier:** handling around certain reference reads, useful for relocation/remapping and correctness when the collector moves objects concurrently.
- **Remembered-set-like metadata:** information that allows identifying locations that may contain cross-generational references. Not necessarily the exact same data structure as G1's remembered set/card table.
- **Forwarding/remapping:** ensuring a valid reference still points to the right logical object after the object changes physical location.

**Do not state** that every Java assignment must write a card-table entry with a specific exact byte layout. The compiler/GC has the right to optimize/coalesce/filter barriers, and the implementation can change across JDKs.

### The cost of generations

Generational ZGC can:
- Reduce repeated marking/collection work on old objects.
- Reduce the risk of allocation stalls and heap headroom requirements in many workloads.
- Introduce some additional **store-barrier bookkeeping**, metadata, or concurrent work to track old-to-young references.
- Have a different benefit profile when a workload consists mostly of long-lived objects, has heavy reference mutations, or does not clearly exhibit the generational hypothesis.

Therefore, Generational ZGC is not a claim that every program will be faster by a fixed percentage. Benchmarking on a real workload is what determines the trade-off.

## 4. Official Timeline by JDK Version

Three core JEPs:

- **JEP 439:** Generational ZGC, delivered in JDK 21.
- **JEP 474:** ZGC: Generational Mode by Default, delivered in JDK 23.
- **JEP 490:** ZGC: Remove the Non-Generational Mode, delivered in JDK 24.

The table below focuses on **upstream OpenJDK/HotSpot**; for vendor custom builds or backports, you must check the exact binary being run.

| JDK | ZGC Status | Default When Selecting `UseZGC` | How to Specify Generational Mode |
| --- | --- | --- | --- |
| **11** | ZGC introduced as experimental (JEP 333) | Non-generational | No Generational ZGC yet |
| **15** | ZGC production (JEP 377) | Non-generational | No Generational ZGC yet |
| **17 (LTS)** | ZGC production | Non-generational | **No** `ZGenerational` flag to enable JDK 21's mode |
| **21 (LTS)** | JEP 439 adds Generational ZGC | **Non-generational**, if only `-XX:+UseZGC` is used | `-XX:+UseZGC -XX:+ZGenerational` |
| **22** | Both modes continue to coexist | **Non-generational** | `-XX:+UseZGC -XX:+ZGenerational` |
| **23** | JEP 474 changes default and deprecates non-gen mode | **Generational** | `-XX:+UseZGC` is sufficient; `-XX:-ZGenerational` selects legacy non-gen in this release |
| **24** | JEP 490 removes non-generational implementation | **Generational only** | `-XX:+UseZGC`; `ZGenerational` is **obsolete, accepted but ignored/warned** per HotSpot option life cycle |
| **25 (LTS)** | Continues generational-only | **Generational only** | `-XX:+UseZGC`; the legacy `ZGenerational` flag remains in the obsolete/warning phase |
| **26** | Generational-only; legacy option compatibility period ends | **Generational only** | `-XX:+UseZGC`; **do not pass `ZGenerational`**, as it has expired/been removed and may cause the JVM to refuse startup |

**Important note on terminology:** JEP 490 **removed the non-generational mode in JDK 24**; that is different from when the **`ZGenerational` flag syntax itself** finishes its obsolete period. HotSpot typically has a period where it accepts an old option, prints a warning, and **ignores** it to reduce sudden breakage across version upgrades, before the option becomes **expired** and turns into an error. OpenJDK discussions for JDK 26 confirm that the `ZGenerational` flag is removed from the obsolete list in this release. Check the exact startup behavior on your JDK/vendor build rather than relying on warning/ignore.

### Misconceptions From Release Names

- JDK 21 is the **first release with Generational ZGC**, **not** the first release to choose generational as the default.
- JDK 23 switches the **default once ZGC is selected** to generational, **not** the JVM-wide default GC from G1 to ZGC.
- JDK 24 removes the **non-generational ZGC** path, not ZGC itself.
- JDK 26 does not require the `ZGenerational` flag; putting this flag in the configuration can cause the application **not to start**.

## 5. Correct Command Matrix for Each JDK Group

### JDK 17: ZGC is still non-generational

~~~bash
java -XX:+UseZGC -version
~~~

This command selects ZGC on a supported HotSpot build. **Do not** add `-XX:+ZGenerational` to Java 17: this is not yet JDK 21's Generational ZGC option.

To check if a JVM supports ZGC in a real environment, read `java -version` and run a real smoke test with `-XX:+UseZGC -Xlog:gc*=info`. If the flag or collector is not supported by the build, the JVM may report an error; do not infer solely from the Java file name.

### JDK 21–22: must explicitly select generational

~~~bash
java -XX:+UseZGC -XX:+ZGenerational -version
~~~

If `-XX:+ZGenerational` is omitted in JDK 21/22, **non-generational ZGC** is the default mode. This is an important point when migrating from Java 17 to Java 21 and wanting to measure the improvements of JEP 439.

To run a non-gen baseline comparison in JDK 21:

~~~bash
java -XX:+UseZGC -version
~~~

These are two modes of **the same ZGC collector**, not ZGC and G1.

### JDK 23: generational becomes ZGC's default

~~~bash
java -XX:+UseZGC -version
~~~

JDK 23 defaults to generational **once ZGC has been selected**. During the transition, legacy mode can be selected with:

~~~bash
java -XX:+UseZGC -XX:-ZGenerational -version
~~~

**Only use the JDK 23 legacy example to understand history or perform a migration test**; do not put this minus flag into configurations for JDK 24+ because non-generational mode has been removed.

### JDK 24–26: only select ZGC

~~~bash
java -XX:+UseZGC -version
~~~

This is the more stable command when operating generational-only ZGC. Do not add `-XX:+ZGenerational` or `-XX:-ZGenerational`. JDK 24/25 may warn/ignore the legacy flag; JDK 26 may error because the flag has expired. Multi-JDK configurations should **generate args per version**, rather than simply appending a ZGenerational flag for every machine.

### What Does a Command With a Selected GC Mean?

Do not read `java -XX:+UseZGC -version` as proof that an application has GC events: it can only start the VM and report the version. To see the selected collector, add logging:

~~~bash
java -XX:+UseZGC -Xlog:gc*=info -version
~~~

Log messages and formats vary by HotSpot release. You may see a line describing the collector, but neither stdout nor a fixed number of collection events is guaranteed.

## 6. When Upgrading the JDK: JVM Option States Have Practical Impact

Common states in HotSpot's option lifecycle:

| State | Common Meaning | Impact When Old Config Remains |
| --- | --- | --- |
| **Supported/active** | Option exists and has effect per semantics and release | Can be used per documentation |
| **Deprecated** | Option still has effect but emits a warning; may be removed later | Need to plan migration |
| **Obsolete** | Option is accepted but no longer has effect; VM may warn | Easy to mistakenly think the option still enables the feature |
| **Expired/removed** | Option is no longer accepted by the startup parser | Can cause the JVM to fail immediately at startup |

The transition of `ZGenerational` creates an **operational trap**:

~~~text
JDK 21:  -XX:+ZGenerational
         actually ENABLES generational mode

JDK 23:  -XX:+ZGenerational
         no longer needed to select default generational

JDK 24/25:
         legacy option is obsolete/ignored
         no longer changes mode

JDK 26:
         legacy option expired
         should not appear in startup args
~~~

**CI/CD failure example:** a Helm chart contains the environment variable `JAVA_TOOL_OPTIONS="-XX:+UseZGC -XX:+ZGenerational"` applied uniformly to both JDK 21 and JDK 26 images. On JDK 21, the chart helps select generational mode. On JDK 26, the old option can prevent all pods from starting. You need to fix the image/tag→options template mapping and run a smoke test with **the exact production image** before rolling out.

**Do not guess from `java --version` alone if the application actually uses a different JDK than the shell**. Container images, embedded runtimes, IDEs, Maven/Gradle toolchains, and launcher scripts can run different binaries. Check the running process/runtime using diagnostics.

## 7. Reading the Generational Mechanism Correctly: Young Objects May Survive Multiple Cycles

Object age is not defined by a simple number of seconds in Java source. The VM tracks object survival and promotion eligibility based on collector policy.

~~~text
Create Payload at t0:
  Payload is in young

t1: Young GC
  Payload unreachable? -> reclaim
  Payload reachable?   -> survives per policy

t2: Another Young GC
  Payload continues to survive
  Collector may keep in young or promote to old

t3: Old generation has many dead objects
  Old collection runs per ZGC's scheduling
~~~

Not every object is "young for two seconds," and there is no universal public Java API to definitively determine the generation of an arbitrary object at any point in time. A JFR/GC log can provide generation/tenuring statistics, **not** turn a Java variable into an age-control handle.

### Young vs old is not synonymous with weak vs strong references

- **Young/old** refers to lifetime/generation management organization.
- **Strong/weak/soft/phantom reference** refers to reachability/reference processing semantics.
- An object in the old generation can still become unreachable and need to be collected.
- An object in young can still be reachable from a static field or an old object and need to be kept.

Do not mechanically apply G1's garbage collection order to ZGC. Although both are generational, they have different barrier/region/evacuation/coordination mechanisms.

## 8. Generational ZGC Is Still a Moving Concurrent Collector

Generational ZGC still relies on ZGC's **concurrent marking and relocation** mechanisms. When GC moves an object from an old physical address to a new location, the Java program must still observe the same logical object:

~~~java
Object a = new Object();
Object b = a;
System.out.println(a == b); // true
~~~

This is a snippet inside a method. After a concurrent relocation, the VM must ensure `a == b` remains true unless the code itself changes the references. A Java reference **is not a raw pointer with an immutable address managed by code**.

What the collector must guarantee:
1. Trace the appropriate references to identify live objects.
2. Coordinate relocation/forwarding with mutator threads.
3. Preserve the identity and correctness of references/fields as objects move.
4. Do not reclaim an object that is still reachable from roots or old-to-young references.
5. Serve concurrent allocation within allowed heap/CPU limits.

Different load/store barrier techniques can have costs on hot execution paths. An application that mutates references very frequently may experience different store-barrier overhead than an application that mainly reads immutable graphs. **Do not automatically claim** that generational always increases throughput by a certain percentage or always reduces pauses.

## 9. Most Important Tuning: -Xmx and Headroom

ZGC tuning documentation emphasizes that **max heap size** is the primary tuning knob. Because GC does a lot of work concurrently with the application, the heap must have enough room for:
- the **live set** being retained,
- new allocations occurring while GC is running,
- destination/headroom related to relocation and collector bookkeeping.

Example:

~~~bash
java -XX:+UseZGC -Xms2g -Xmx4g -jar app.jar
~~~

This is an **application run template**; you must replace `app.jar` with a valid JAR and reserve a memory limit larger than the entire JVM's footprint. **It is not a general recommendation** to set 4 GiB for every service.

### If the heap is too small

What can happen:
- GC has to work very frequently.
- Concurrent cycles cannot reclaim fast enough before allocations consume headroom.
- Allocation stalls, latency spikes, and eventual OOME.
- CPU contention between GC workers and mutators.

Even though ZGC targets low pauses, **there is no guarantee requests will never stall** when the heap budget is insufficient. Short GC safepoints do not by themselves solve throughput or memory pressure issues.

### If the heap is too large

It can:
- Increase RSS/memory cost and reduce deployment density.
- Mask a memory retention bug for longer.
- Increase committed/reserved memory depending on configuration.
- Fail to improve p99 if the bottleneck is the database, locks, JIT, or CPU throttling.

**Choose -Xmx based on live set, allocation spikes, and SLO**, while reserving space for JVM native memory (metaspace, code cache, thread stacks, direct buffers). `-Xmx=4g` does not mean a 4 GiB container RAM limit is always enough.

## 10. SoftMaxHeapSize: A Soft Limit Is Not a Hard Limit

Option:

~~~bash
java -XX:+UseZGC -Xmx5g -XX:SoftMaxHeapSize=4g -jar app.jar
~~~

Meaning:
- `-Xmx5g` is the hard maximum of the Java heap.
- `-XX:SoftMaxHeapSize=4g` is the **soft target** that ZGC tries to stay within when conditions allow.
- ZGC **is allowed to exceed the soft limit** up to the hard max to avoid situations where the application stalls due to lack of memory.
- This is not a guarantee that process RSS will stay below 4 GiB.

When testing, do not just look at committed heap at a single point in time and conclude that exceeding the soft limit is a bug. The collector may proactively use more memory during an allocation spike or when needed to complete concurrent work.

Setting a soft limit smaller than the heap budget is useful when you want to reduce average committed memory while still keeping **burst headroom**. The optimal value depends on the workload; there is no fixed ratio recommended for all applications.

## 11. Uncommit: Returning Unused Heap to the OS

ZGC supports returning a portion of **unused committed memory** to the operating system via the **uncommit** mechanism under suitable conditions.

Common flags:

| Flag | Meaning | Notes |
| --- | --- | --- |
| `-XX:+ZUncommit` | Allows returning unused committed heap memory; typically enabled by default in ZGC | Does not mean all garbage is returned immediately to the OS |
| `-XX:-ZUncommit` | Disables the uncommit mechanism | Can keep committed memory for reuse |
| `-XX:ZUncommitDelay=300` | Time memory must remain unused before it can be uncommitted (default 300 seconds per documentation) | Not a timer forcing GC at that exact second |
| `-Xms` | Heap size floor: ZGC will not uncommit to shrink the heap below min heap | When `-Xms=-Xmx`, uncommit becomes practically ineffective |

Example:

~~~bash
java -XX:+UseZGC -Xms1g -Xmx4g -XX:ZUncommitDelay=300 -jar app.jar
~~~

These options belong to supporting HotSpot releases; they must be tested on the exact production JDK. Committing/uncommitting pages also has a cost. If ultra-low latency is the priority and RAM is plentiful, a configuration with `-Xms=-Xmx` plus `-XX:+AlwaysPreTouch` **may** suit some environments, at the cost of committed memory/startup time; do not treat it as a default recipe for every container.

### Heap used, committed, and RSS are not the same

~~~text
-Xmx     : maximum Java heap
-Xms     : minimum/initial Java heap
Used heap / live set : object state
Committed heap       : committed memory
RSS/container memory : includes heap and native components
~~~

ZGC can reduce footprint via uncommit, but system RSS is affected by many other OS/native factors. Memory metrics must be collected from both the VM and the container simultaneously.

## 12. Tuning Concurrent Work: Be Cautious With Too Many Flags

ZGC is designed to be **self-tuning**. Beyond max heap, knobs that may appear in documentation/flags for specific JDKs include:

- `-XX:ConcGCThreads=N`: adjusts the number of concurrent GC worker threads, but overriding automatic selection can starve GC of resources or cause CPU contention.
- `-XX:ZCollectionInterval=...`: policy/interval trigger in supported versions, not a promise that GC runs every N seconds exactly.
- `-XX:ZAllocationSpikeTolerance=...`: guides heuristics on the rate of allocation spikes; do not use unless there are signs of stalls.
- `-XX:ZFragmentationLimit=...`: affects relocation/compaction policy in specific ZGC versions; has a CPU vs. fragmentation trade-off.
- `-XX:SoftMaxHeapSize=...`: soft footprint target.
- `-XX:ZUncommitDelay=...`: delay before returning unused pages.

**Do not copy a tuning flag list verbatim from one JDK version to another.** JDK 21/23/24/25/26 have changes in modes, heuristics, and diagnostic/product flags. Check with:

~~~bash
java -version
java -XX:+PrintFlagsFinal -version
~~~

If you only want to view flags containing the letter Z in PowerShell:

~~~powershell
java -XX:+PrintFlagsFinal -version 2>&1 |
    Select-String "UseZGC|ZGenerational|SoftMaxHeapSize|ZUncommit"
~~~

The command above is a **shell guide**, not a guaranteed stable output: a flag may not appear in a newer release because it was removed, or may not be printed without an unlock level. For production, record the exact command line from the launcher/systemd/Helm environment, not just JVM flags printed in an arbitrary shell.

## 13. Distinguishing GC Flag Groups and Their Lifecycle

| Group | Example | What to Know |
| --- | --- | --- |
| **Collector selection** | `-XX:+UseZGC` | Selects ZGC; currently generational-only on JDK 24+ |
| **Mode selection during transition** | `-XX:+ZGenerational` or `-XX:-ZGenerational` | Only effective in releases that support both modes |
| **Heap budget** | `-Xms`, `-Xmx`, `SoftMaxHeapSize` | Does not reduce to a single heap value |
| **Memory returning** | `ZUncommit`, `ZUncommitDelay` | Depends on policy/JDK version; has commit/uncommit cost |
| **Concurrent GC work** | `ConcGCThreads` | Has a CPU trade-off with application threads |
| **Diagnostics** | `-Xlog:gc*`, JFR, `jcmd` | Observes behavior, does not select GC mode |
| **Deprecated/obsolete legacy** | `ZGenerational` on versions without both modes | Needs to be removed from startup scripts |

### Which Flags Can Be Used Across Multiple Versions?

If an application must run on both JDK 21 and JDK 26 and **must** use Generational ZGC, you must branch:

~~~text
if runtime JDK == 21 or 22:
    append "-XX:+UseZGC -XX:+ZGenerational"
else if runtime JDK >= 23:
    append "-XX:+UseZGC"
else:
    Generational ZGC unavailable; choose migration strategy
~~~

This is **configuration pseudocode**, not Bash/PowerShell syntax. For JDK 23, generational mode is the default when `UseZGC` is set, and for JDK 24+ it is the only mode. You should not rely on `-XX:+ZGenerational` if you want the same manifest to work on JDK 26.

If a vendor has backported/modified flags, use the exact production binary to verify, rather than blindly following the upstream table.

## 14. Java 17+: Old → Young Reference Model With Deterministic Output

To learn the reason behind store barriers **without fabricating GC events**, a Java program can use a static owner holding a reference to a payload created later. The program has no API to force the owner into old, so it only illustrates the **reference relationship** — it does not prove which generation an object actually belongs to.

Create the file **`GenerationalReferenceDemo.java`**:

~~~java
public class GenerationalReferenceDemo {
    static final class Holder {
        byte[] payload;
    }

    static final Holder LONG_LIVED = new Holder();

    public static void main(String[] args) {
        byte[] first = new byte[] {1, 2, 3};
        LONG_LIVED.payload = first;

        System.out.println("sameFirst=" +
                (LONG_LIVED.payload == first));
        System.out.println("first0=" + LONG_LIVED.payload[0]);

        byte[] second = new byte[] {7, 8, 9};
        LONG_LIVED.payload = second;

        System.out.println("sameSecond=" +
                (LONG_LIVED.payload == second));
        System.out.println("second0=" + LONG_LIVED.payload[0]);
        System.out.println("firstStill=" + first[0]);
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac --release 17 GenerationalReferenceDemo.java
java GenerationalReferenceDemo
~~~

**Exact stdout:**

~~~text
sameFirst=true
first0=1
sameSecond=true
second0=7
firstStill=1
~~~

Explanation:
- `LONG_LIVED` is a static field holding a reference to `Holder`; there is no guarantee the object has been **promoted** at any point in this short program.
- Assigning `payload` changes a **reference field**, not copying the array.
- If `Holder` is actually in old and `second` is actually in young in a long-running workload, this is the kind of **old-to-young reference** that a generational collector must handle correctly.
- After reassignment, `first` is still referenced by the local variable, so it does not disappear immediately.
- Generational ZGC may use store-barrier bookkeeping for appropriate real-world cases, but **stdout does not prove a barrier was executed**.

## 15. Java 17+: A Workload Creating Objects and Some Survivors

This is an executable program across multiple JDK versions to test GC with **the same data logic**. It does not require any ZGC-specific Java API.

Create the file **`ZgcWorkloadDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ZgcWorkloadDemo {
    static volatile byte[] latest;

    public static void main(String[] args) {
        List<byte[]> survivors = new ArrayList<>();
        long checksum = 0;

        for (int i = 0; i < 50_000; i++) {
            byte[] payload = new byte[1024];
            payload[0] = (byte) i;

            checksum += Byte.toUnsignedInt(payload[0]);

            if (i % 1000 == 0) {
                survivors.add(payload);
            } else {
                latest = payload;
            }
        }

        System.out.println("survivors=" + survivors.size());
        System.out.println("checksum=" + checksum);
        System.out.println("last=" +
                Byte.toUnsignedInt(latest[0]));
    }
}
~~~

Compile with **JDK 17+**:

~~~bash
javac --release 17 ZgcWorkloadDemo.java
~~~

Run with **non-generational ZGC in JDK 17**:

~~~bash
java -Xms32m -Xmx128m -XX:+UseZGC ZgcWorkloadDemo
~~~

Run with **Generational ZGC in JDK 21/22**:

~~~bash
java -Xms32m -Xmx128m -XX:+UseZGC -XX:+ZGenerational ZgcWorkloadDemo
~~~

Run with **default generational ZGC in JDK 23+**:

~~~bash
java -Xms32m -Xmx128m -XX:+UseZGC ZgcWorkloadDemo
~~~

**Exact business stdout** if the VM starts and runs successfully, without separate logging enabled on stdout:

~~~text
survivors=50
checksum=6367960
last=79
~~~

How to verify the numbers:
- There are 50,000 iterations.
- Indices divisible by 1000 are 0, 1000, …, 49000 → **50 survivor references in the list**.
- `Byte.toUnsignedInt((byte)i)` cycles through 0..255, so the sum over 50,000 elements is **6,367,960**.
- The last `i` is 49999; 49999 modulo 256 = **79**, so `last=79`.
- Although the source contains 50,000 `new byte[1024]` statements, at runtime **do not automatically assume a profiler must record exactly 50,000 physical allocations**: JIT can optimize, and GC can behave differently.
- A JVM/container that is too resource-constrained or lacks ZGC support may fail to run; the command is a **smoke test**, not a production benchmark.

### Why Not Print a Fixed GC-Count?

Young/old GC frequency and generation distribution depend on the JDK, heap sizing, CPU, object liveness, heuristics, JIT, and scheduling. The same code can produce zero, one, or multiple GC cycles in a short run. **Do not write stdout predicting "3 Young GCs"** when it cannot be guaranteed.

## 16. Verifying Which Collector Actually Runs in the Environment

Start with:

~~~bash
java -version
java -XX:+UseZGC -Xlog:gc*=info -version
~~~

For Java 21 if you want generational, add the flag:

~~~bash
java -XX:+UseZGC -XX:+ZGenerational -Xlog:gc*=info -version
~~~

Read the startup logs to confirm ZGC and the corresponding mode. Tags/log messages **change across HotSpot releases**, so do not hardcode a single log string without verifying on the exact release.

### Test Run With GC Log to File

On JDK 24+:

~~~bash
java -Xms256m -Xmx1g -XX:+UseZGC -Xlog:gc*:file=zgc.log:time,uptime,level,tags ZgcWorkloadDemo
~~~

The `zgc.log` file can provide GC init/heap statistics/young–old phases depending on log level and VM build. A program that is too short **may not trigger the desired number of GCs**, so do not use a single run to evaluate the collector's policy.

If you want to see more while avoiding excessive logging, start at `info` level and expand to `debug/trace` only when truly needed. Large GC logs can affect disk and performance; rotation/retention is needed in production.

### Identifying the Flags of the Actually Running JVM

With a valid process ID (replace with the actual PID number):

~~~bash
jcmd PID VM.command_line
jcmd PID VM.flags
jcmd PID GC.heap_info
~~~

These are example commands supported by the JDK. Do not use the literal string `PID` if the process has a different ID, and check attach permissions/actual JVM configuration. An app launcher may add flags from `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, a start script, or a service manager.

### JFR and GC Events

JFR can help observe:
- GC pauses, concurrent cycles, heap usage, and allocation activity depending on event settings;
- total CPU/process behavior;
- large objects or allocation hotspots when corresponding events are enabled;
- stalls/delays and their correlation with request latency.

However, JFR recording, event sampling, and output depend on configuration. Do not treat a short recording as proof that ZGC always has a lower p99 than another collector in production.

## 17. Migration Checklist: Java 17 → 21 → 23/24/25/26

### Step 1: confirm requirements

First determine:
- Does the runtime need **low GC pause**, throughput-first, or is it memory-constrained?
- What is the end-to-end p99/p99.9 latency SLO?
- What are the heap live set, allocation rate, largest bursts, and CPU quota?
- Are there pinned/native interactions or special large arrays?
- Must multiple JDKs run side by side in a fleet?

Do not automatically decide to switch to ZGC just because you are upgrading Java. The default GC (usually G1) may already meet the SLO with less CPU/memory.

### Step 2: check the exact binary/flags

~~~bash
java -version
java -XX:+UseZGC -Xlog:gc*=info -version
~~~

On JDK 21/22, run a comparison of the two modes if needed to understand Generational ZGC:

~~~bash
java -XX:+UseZGC -version
java -XX:+UseZGC -XX:+ZGenerational -version
~~~

On JDK 23, generational is already the default when ZGC is selected. On JDK 24+, legacy non-gen is gone. On JDK 26, **completely remove** the `ZGenerational` flag from startup scripts/Helm charts.

### Step 3: migrate configuration by release

| Source | Target | Minimal Change When Actively Choosing Generational ZGC |
| --- | --- | --- |
| JDK 17 ZGC → JDK 21 | Try generational | Add `-XX:+ZGenerational` to `-XX:+UseZGC` |
| JDK 21 generational → JDK 23 | Generational default | Can remove `-XX:+ZGenerational`; keep `-XX:+UseZGC` |
| JDK 23 non-gen → JDK 24 | No more non-gen | Remove `-XX:-ZGenerational`; accept the algorithm transition |
| JDK 24/25 → JDK 26 | Remove obsolete flag | Remove `-XX:±ZGenerational` completely; keep `-XX:+UseZGC` |
| JDK 17/G1 → JDK 26/ZGC | Change collector and algorithm | Enable `UseZGC`, measure latency/CPU/RSS, do not blindly reuse G1 tuning flags |

**Note:** "Removing the flag" is a config syntax change; however, performance behavior may change due to the underlying generational collector. You must test workload/heap sizing after migration, not just prove that VM startup succeeds.

### Step 4: controlled comparison

On the same benchmark/service:
1. Fix the workload, application versions, and inputs.
2. Record exact JDK build, CPU quota, memory limit, and GC flags.
3. Use equivalent warmup; run long enough to observe concurrent/old collection cycles.
4. Collect p50/p95/p99 request latency, throughput, errors, CPU, RSS, live heap, allocation stalls, and GC pause distribution.
5. Repeat runs to reduce noise; do not draw conclusions from one pretty log.
6. Canary on real traffic with a rollback plan.

**Do not compare two configurations with different heap limits and attribute every difference to the collector**. If you have to change the heap for ZGC to run stably, record that as part of the configuration cost.

## 18. ZGC Can Still Cause Allocation Stalls

ZGC optimizing pause times does not mean the JVM cannot hit **allocation stalls** if concurrent GC cannot reclaim memory fast enough.

Possible causes include:
- `-Xmx` is too small relative to live set + allocation bursts.
- CPU quota prevents concurrent GC workers from getting enough CPU cycles.
- Allocation rate spikes suddenly.
- Many long-lived objects or cache retention.
- Memory outside the Java heap (direct/native) causes container memory pressure, destabilizing the application despite low GC pauses.

When seeing p99 spikes, inspect simultaneously:
- GC log markers for stalls and cycle progress.
- Heap used/committed, available headroom.
- Process/container CPU throttling.
- JFR event timeline and requests.
- Memory leak/retention ownership.

**Do not default to fixing with `ConcGCThreads`**. Increasing concurrent workers can help the collector but also takes CPU away from the application, making service latency worse on low-vCPU instances. Measure first, then test one controlled change.

## 19. JDK Version-Specific Tuning and Upgrade Pitfalls

### Pitfall 1: interpreting "default Generational ZGC" as "the default GC is ZGC"

**False.** JEP 474 only changes the default mode **within ZGC** when ZGC is selected. The VM may still choose G1 by default depending on platform/heap.

### Pitfall 2: believing Java 21 automatically uses Generational ZGC when `UseZGC` is selected

**False.** JDK 21 still selects non-gen when only `-XX:+UseZGC` is passed. Add `-XX:+ZGenerational` if you want generational.

### Pitfall 3: using `ZGenerational` across all of Java 21–26

**False.** The flag has real meaning in 21/22, is no longer needed in 23, is obsolete in 24/25, and is expired in 26 per the upstream lifecycle. Version-specific configuration is required.

### Pitfall 4: setting `-XX:-ZGenerational` on JDK 24 to revert to the old mode

**Impossible.** JEP 490 removed the non-generational implementation. Even if an obsolete flag is still accepted, it is ignored and cannot restore the algorithm.

### Pitfall 5: thinking Generational ZGC collects the old generation for free

**False.** It still must mark/copy/relocate old objects in appropriate cycles. Generations help avoid unnecessary work during many young collections, not eliminate the cost of all old objects.

### Pitfall 6: thinking ZGC has no reference store barrier

**Inaccurate for Generational ZGC.** Tracking old-to-young references requires appropriate barriers/metadata; the compiler/runtime has specific optimizations.

### Pitfall 7: treating "sub-millisecond GC pause" as an SLA

**False.** That is a design goal, not a hard deadline for every pause and not p99 request latency. CPU contention, allocation stalls, and application logic can still cause latency.

### Pitfall 8: lowering `-Xmx` because generational is more efficient

This can increase stalls if headroom is insufficient. You need to verify live set, spikes, CPU quota, and memory footprint before lowering the budget.

### Pitfall 9: setting `-Xms=-Xmx` when wanting ZUncommit to reduce RSS

When minimum heap equals maximum heap, ZGC cannot uncommit below the minimum. That configuration effectively disables the uncommit benefit for unused heap.

### Pitfall 10: comparing ZGC with G1 using GC logs alone

GC logs are not enough for end-to-end latency. You must measure throughput, p99 service latency, errors, process CPU, RSS, and container throttling.

### Pitfall 11: assuming Java source has an API to measure the generation of an arbitrary object

There is no general Java SE API that guarantees reporting the generation of every object. Diagnostics may provide internal information, but it varies by collector/build.

### Pitfall 12: turning `java -version` into a "benchmark"

A startup command checks config; it does not run enough workload/GC cycles to say anything about throughput/latency.

## 20. Practice Analyzing a Configuration Incident

**Scenario:** A service was running on JDK 21 with the command:

~~~text
java -XX:+UseZGC -XX:+ZGenerational -Xmx4g -jar service.jar
~~~

When switching the container image to JDK 26, the process fails to start due to the legacy `ZGenerational` flag.

### Diagnosis

1. Check the exact JVM from startup logs or `java -version` inside the same container.
2. Inspect all JVM arguments: command line, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, Helm chart/start script.
3. Cross-reference JEP 490: JDK 24 removed non-generational mode; the old flag is no longer needed.
4. Cross-reference expiration in JDK 26: the obsolete flag is past its compatibility window.
5. **Remove the `-XX:+ZGenerational` flag**, keeping `-XX:+UseZGC` if you still want to select ZGC.
6. Run a smoke test on the exact production image, enabling `-Xlog:gc*=info` to confirm the collector.
7. Measure a production-like workload, CPU/RSS/GC events, and SLOs to verify the upgrade is complete.

**Fixed configuration for JDK 26:**

~~~bash
java -XX:+UseZGC -Xmx4g -jar service.jar
~~~

The file `service.jar` is an example name and must be replaced with the actual application artifact. Removing the legacy flag fixes startup, but does not automatically guarantee that the new release's throughput/latency matches the old release.

## 21. Exercises and Solutions

**Question 1.** Which JDK first added Generational ZGC?

**Answer:** **JDK 21**, via **JEP 439**. On this release, you still need to select generational mode with `-XX:+UseZGC -XX:+ZGenerational`.

**Question 2.** Does upstream JDK 17 have Generational ZGC?

**Answer:** No. ZGC on upstream JDK 17 is **non-generational**.

**Question 3.** Which JDK switched ZGC's default mode to generational?

**Answer:** **JDK 23** per **JEP 474**. This does not mean the default garbage collector for the entire JVM changed to ZGC.

**Question 4.** Which JDK removed non-generational ZGC?

**Answer:** **JDK 24**, per **JEP 490**.

**Question 5.** Why might the `ZGenerational` flag still not cause a startup error on JDK 25 even though it is useless?

**Answer:** HotSpot has an **obsolete option** phase that accepts/warns/ignores before expiring, in order to support the transition process.

**Question 6.** When using JDK 26, which command selects ZGC?

**Answer:** `java -XX:+UseZGC ...`, **without** adding the `ZGenerational` flag.

**Question 7.** Why does Generational ZGC need to track old-to-young references?

**Answer:** A young object may be reachable through a field of an old object; if ignored, the collector could mistakenly reclaim a live object.

**Question 8.** Is a store barrier related to `volatile` in Java source?

**Answer:** They are different concepts. A GC store barrier is instrumentation/runtime logic serving GC; `volatile` is visibility/ordering semantics in the Java Memory Model.

**Question 9.** When `Xmx=5g, SoftMaxHeapSize=4g`, is ZGC allowed to exceed 4g?

**Answer:** Yes, up to the hard max when needed, for example to avoid allocation stalls. A soft limit is not a hard limit.

**Question 10.** Why does `-Xms=-Xmx` reduce the effectiveness of ZUncommit?

**Answer:** ZGC does not uncommit below minimum heap; setting minimum equal to maximum leaves no room to shrink.

**Question 11.** Does ZGC guarantee the application will have no pauses >1 ms or p99 <10 ms?

**Answer:** No. Low pause is a design goal; application latency has many sources and the collector can still hit allocation stalls when resources are insufficient.

**Question 12.** Can `java -XX:+UseZGC -version` be used to compare ZGC vs G1 throughput?

**Answer:** No. That is a startup smoke test, not a benchmark.

**Question 13.** When upgrading to JDK 23, what does `-XX:-ZGenerational` do?

**Answer:** In JDK 23, it can select **legacy non-generational mode**; that mode is deprecated and removed in JDK 24.

**Question 14.** When might switching ZGC mode not help an application?

**Answer:** When the workload does not have much young garbage, has many old-to-young mutations, low CPU quota, a heap that is too tight, or the bottleneck lies outside GC. You must measure.

**Question 15.** Why shouldn't you infer young/old counts from the stdout of the ReferenceDemo example?

**Answer:** Java source does not guarantee that the `Holder` object has been promoted. The example only demonstrates reference semantics, not heap age/generation observation.

## 22. Cheat Sheet

~~~text
HISTORY OF ZGC MODE SELECTION

JDK 11: ZGC experimental (non-gen)
    |
JDK 15/17: ZGC production, non-gen
    |
JDK 21: JEP 439 -> Generational mode ADDED
        -XX:+UseZGC                 => non-gen default
        -XX:+UseZGC -XX:+ZGenerational => gen
    |
JDK 22: same transitional behavior
    |
JDK 23: JEP 474 -> Generational DEFAULT if UseZGC
        -XX:+UseZGC                 => gen
        -XX:-ZGenerational          => legacy non-gen
    |
JDK 24: JEP 490 -> non-gen IMPLEMENTATION REMOVED
        -XX:+UseZGC                 => gen only
        ZGenerational legacy option obsolete
    |
JDK 25: gen only; legacy option still obsolete
    |
JDK 26: gen only; ZGenerational legacy option expired
        -XX:+UseZGC                 => recommended syntax


WHY GENERATIONAL?

New objects -> YOUNG -> usually die early
Survivors -> may be promoted -> OLD
OLD --> YOUNG reference requires tracking
  store barrier + GC metadata
Concurrent mark/relocation + load-barrier logic

WHAT TO MEASURE?

SLO p99 + throughput + CPU + RSS + heap headroom
GC logs + JFR + jcmd + container metrics
NEVER infer exact GC cycles from Java stdout
~~~

**Summary:** **Generational ZGC began in JDK 21**, became **ZGC's default mode on JDK 23**, and is the **only mode from JDK 24 onward**. The `ZGenerational` flag is therefore effective on JDK 21/22, unnecessary for JDK 23, obsolete on JDK 24/25, and no longer valid on JDK 26. Mechanistically, generational separation helps focus work on young objects and uses barriers/metadata to preserve old→young references correctly. To operate safely, choose flags matching the exact runtime version, provide sufficient heap headroom, and measure **latency/CPU/throughput/RSS** using real workloads.

## Official References and Version Cross-Reference Sources

- [JEP 333 — ZGC: A Scalable Low-Latency Garbage Collector (JDK 11)](https://openjdk.org/jeps/333).
- [JEP 377 — ZGC: A Scalable Low-Latency Garbage Collector (Production) (JDK 15)](https://openjdk.org/jeps/377).
- [JEP 439 — Generational ZGC (JDK 21)](https://openjdk.org/jeps/439).
- [JEP 474 — ZGC: Generational Mode by Default (JDK 23)](https://openjdk.org/jeps/474).
- [JEP 490 — ZGC: Remove the Non-Generational Mode (JDK 24)](https://openjdk.org/jeps/490).
- [Oracle JDK 24 Migration Guide — ZGC non-generational removal](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html).
- [Inside Java — Introducing Generational ZGC](https://inside.java/2023/11/28/gen-zgc-explainer/).
- [Oracle Java SE 21 — Z Garbage Collector and heap tuning](https://docs.oracle.com/en/java/javase/21/gctuning/z-garbage-collector2.html).
- [Oracle Java SE 26 — java command and GC flags](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html).
- [OpenJDK HotSpot review — Remove expired ZGC flags for JDK 26](https://mail.openjdk.org/pipermail/hotspot-runtime-dev/2025-October/082324.html).
- [Oracle JDK 21 Release Notes — Generational ZGC](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html).
