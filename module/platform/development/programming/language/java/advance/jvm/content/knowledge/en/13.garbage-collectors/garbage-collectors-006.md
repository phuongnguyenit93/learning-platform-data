# ZGC: concurrent collection aimed at low pause times

## 1. What problem does ZGC solve?

**ZGC (Z Garbage Collector)** is a garbage collector of the HotSpot JVM designed to minimize **stop-the-world GC pauses**, especially for Java services sensitive to tail latency or using large heaps. Instead of stopping all Java application threads to perform most of the marking and object relocation, ZGC does almost all of the heavy work **concurrently** while the application is still running.

However, it is necessary to distinguish:

- **Low pause time** does not mean no pauses at all.
- **GC cycle elapsed time** is not the same as **the total time the application is stopped**.
- **End-to-end response latency** also depends on CPU scheduling, lock contention, I/O, JIT, database, network, and allocation stalls.
- **Concurrent GC** consumes CPU, cache/memory bandwidth, and heap headroom; it is not free.
- **ZGC** does not automatically free objects that are still reachable through caches/listeners/ThreadLocal even if the business logic no longer needs them.
- **Java 17** ZGC and **Generational ZGC in Java 21+** have important differences in algorithms and parameters.

This article presents the **HotSpot ZGC architecture on Java 17** first, then compares the changes in Java 21–25. This is an **implementation detail** of HotSpot, not a mandatory GC algorithm in the Java Language Specification or JVMS.

### Objectives

After this lesson you can:

1. Distinguish **GC pause**, **concurrent GC cycle**, **allocation stall**, **live set**, **allocation rate**, **heap headroom**, and **throughput**.
2. Draw the basic phases of Java 17 non-generational ZGC: Pause Mark Start, Concurrent Mark, Pause Mark End, Concurrent Prepare for Relocation, Pause Relocate Start, Concurrent Relocate.
3. Describe **colored pointers**, **load barriers**, forwarding/remapping, and why Java object identity remains correct when GC moves objects concurrently.
4. Explain why ZGC must have **free memory headroom** to continue serving allocations while GC has not yet completed.
5. Distinguish Java 17 non-generational ZGC from Java 21 Generational ZGC, default from Java 23, and generational-only from Java 24.
6. Enable the collector, use GC logs, understand the flags **UseZGC**, **Xmx**, **Xms**, **SoftMaxHeapSize**, **ConcGCThreads**, and options for returning unused heap to the OS.
7. Evaluate ZGC against G1/Parallel on real workloads using pause distribution, p99 latency, throughput, CPU/RSS, and allocation stalls.

## 2. Latency and throughput are not the same

Suppose an API service has a **p99 request budget under 30 ms**. Some causes of slow requests:

~~~text
Request #1:
  Business execution     12 ms
  GC STW overlap          1 ms
  Scheduler/network       2 ms
  Total                  15 ms

Request #2:
  Business execution     12 ms
  GC STW overlap         40 ms
  Scheduler/network       2 ms
  Total                  54 ms

Request #3:
  Business execution     12 ms
  Database lock         300 ms
  GC STW overlap          0 ms
  Total                 312 ms
~~~

ZGC can improve large GC pause cases like Request #2, but cannot by itself fix the database lock in Request #3.

| Metric | What does it measure? | Why is it important? |
| --- | --- | --- |
| **GC pause time** | Application stop interval caused by GC | Direct target of ZGC |
| **Concurrent cycle elapsed time** | Duration of a GC cycle including concurrent phases | Not equal to STW duration |
| **p50/p95/p99/p99.9 request latency** | End-to-end latency distribution | User/SLA metric |
| **Throughput** | Transactions/requests completed over time | CPU spent on GC can affect it |
| **Allocation rate** | Bytes of objects created by the application per second | Can GC keep up? |
| **Live set** | Size of objects still reachable | Minimum memory requirement in terms of the object graph |
| **Heap headroom** | Sufficient capacity for allocations during concurrent GC | Avoid allocation stalls |
| **GC CPU usage** | CPU used by GC threads | Trade-off with application throughput |
| **RSS/committed/reserved** | Different forms of footprint measurement | Must not be equated with Xmx |

A collector with the **shortest pauses** does not necessarily have the **highest throughput** or lowest footprint. Depending on the SLA, G1 or Parallel may be a more reasonable choice.

## 3. How ZGC has changed across Java versions

| Java | ZGC Status | How to understand it |
| --- | --- | --- |
| **JDK 11** | JEP 333: experimental ZGC | Initial version requiring experimental flag |
| **JDK 15** | JEP 377: production ZGC | Enabled with -XX:+UseZGC |
| **JDK 16** | Improved concurrent thread-stack processing and relocation | Reduced some sources of STW |
| **JDK 17** | Production ZGC, **non-generational** | Used as the architectural baseline in this article |
| **JDK 21** | JEP 439: **Generational ZGC** is optional | -XX:+UseZGC -XX:+ZGenerational |
| **JDK 23** | JEP 474: generational mode chosen as default for ZGC | Non-generational is deprecated |
| **JDK 24** | JEP 490: non-generational mode removed | ZGenerational is no longer used as a selector |
| **JDK 25 LTS** | ZGC generational-only | Follow tuning documentation for JDK 25 |

**Big pitfall:** If reading Java 17 ZGC architecture, do not add young/old generations to that collector on your own. If running Java 25, do not continue teaching ZGC as a solely non-generational collector. Choosing the collector and observing logs must follow the **JDK vendor, major version, build**.

### Command to select ZGC on HotSpot Java 17

~~~bash
java -XX:+UseZGC -jar app.jar
~~~

**app.jar** is a placeholder name for an executable JAR. Enabling ZGC on JDK 17 **does not require** -XX:+UnlockExperimentalVMOptions just for ZGC; this option has been production since JDK 15.

Java 21 when wanting **Generational ZGC**:

~~~bash
java -XX:+UseZGC -XX:+ZGenerational -jar app.jar
~~~

JDK 24+:

~~~bash
java -XX:+UseZGC -jar app.jar
~~~

The **ZGenerational** flag is removed from JDK 24; do not copy a Java 21 command verbatim to JDK 25 and ignore the warning about an obsolete option.

## 4. Concurrent GC and Stop-The-World (STW)

**STW** is a phase where the JVM pauses application threads to coordinate the collector/runtime. Traditional GCs may perform a lot of tracing/evacuation inside STW.

**Concurrent** means GC threads do a large part of the work at the same time Java application threads continue executing. ZGC moves marking, most reference processing, and relocation out of long pauses.

~~~text
Time ------------------------------------------------------------------>

Application:
  RUN ---- [P1] ----- RUN ------------ [P2] ------ RUN ---- [P3] --- RUN

ZGC:
           MarkStart  Concurrent Mark/Remap  MarkEnd
                     Concurrent Prepare Relocation
                                                    RelocateStart
                                                      Concurrent Relocate
~~~

The figure is a **conceptual diagram**, not measured real time. Names/phases vary by JDK, especially Generational ZGC.

### 4.1. Why are there still short pauses?

ZGC needs synchronization points to start/end certain phases and establish global phase state. The key point is to avoid bringing work whose complexity scales heavily with the live heap into synchronization pauses.

Therefore, ZGC usually has **very short pauses compared to some STW collectors**, but **cannot promise an absolute 0 ms** or a fixed number for every OS/CPU/workload.

### 4.2. “Pauses do not grow with heap size” is a design goal

ZGC is designed so that pause time does not directly depend on whether the heap is 1 GiB or hundreds of GiB like a stop-the-world full-heap traversal. But real environments still have:

- CPU contention, CPU quotas/cgroup throttling.
- Scheduler/safepoint coordination.
- JNI/native activities.
- Concurrent GC starvation or memory pressure.
- OS page faults, container memory limits.
- JDK/architecture-specific bugs/overheads.
- Application data races, locks, and downstream I/O.

Read “size-independent pauses” as an **intentional architectural property**, not a guarantee of p99 latency for every request.

## 5. Lifecycle of a ZGC cycle on Java 17

Classic non-generational ZGC can be expressed through these steps:

~~~text
1. Pause Mark Start                     (small STW)
            |
2. Concurrent Mark / Remap              (mutators running)
            |
3. Pause Mark End                       (small STW)
            |
4. Concurrent Prepare for Relocation    (mutators running)
            |
5. Pause Relocate Start                 (small STW)
            |
6. Concurrent Relocate                  (mutators running)
            |
7. Completion, reuse/free pages, work per cycle protocol
~~~

### 5.1. Pause Mark Start

ZGC briefly synchronizes to open a marking cycle and set up appropriate state. It is not when the JVM scans every object in the entire heap during this pause.

### 5.2. Concurrent Mark / Remap

GC identifies objects to be kept alive by reachability from GC roots while mutators may create and modify references. Colored pointers/barriers maintain safety conditions for the marker. Across ZGC versions, some remapping work is combined with concurrent marking.

**Do not understand “marking” as all Java threads being stopped.**

### 5.3. Pause Mark End

Brief synchronization to complete marking according to the collector's protocol. Details of termination, weak roots, and fixpoint depend on implementation/version.

### 5.4. Concurrent Prepare for Relocation

The collector identifies suitable ZPages/regions to move live objects from, prepares forwarding metadata, selects the relocation set, and handles related bookkeeping. It does not need to move all objects in every cycle.

### 5.5. Pause Relocate Start

Brief synchronization point signaling the phase transition to start relocation. Mutators after the pause still need to see valid Java objects, even if objects are moved by the collector.

### 5.6. Concurrent Relocate

The collector moves the selected live objects while the application continues running. Barriers/forwarding help objects be found at their right locations and references get updated or healed gradually.

**A long GC cycle does not mean a long STW pause.** If logs show a concurrent phase running for 60 ms, that does not mean application threads were stopped for the entire 60 ms.

## 6. Challenge: moving objects while the application is reading

Suppose **Node X** is at hypothetical address A. A mutator holds reference r:

~~~text
t0:
  Mutator: r ------------> Node X @ A

t1:
  Collector concurrently moves X from A to B

t2:
  Mutator attempts to dereference r
~~~

If the VM simply changed X's address while the mutator still followed the old reference without a protocol, the read could be unsafe. ZGC uses a combination of:

- **Colored pointers** containing state information in the reference encoding.
- **Load barriers** checking the reference on read.
- **Forwarding/relocation metadata** identifying the new location.
- **Healing/remapping** updating the reference or returning the right referent to the mutator.

### 6.1. What are colored pointers?

“Color” is **internal metadata** represented in certain bits of the reference encoding. It helps the collector recognize whether a reference has a state consistent with the current phase.

~~~text
ZGC encoded reference (conceptual, not a fixed bit layout):

+-------------------------+------------------------+
| metadata/color bits     | address information    |
+-------------------------+------------------------+
           |
           v
     Load barrier checks reference
           |
           +-- good state -> fast path
           |
           +-- bad state -> slow path, remap/mark/heal
~~~

**Do not memorize that bit N is always marked on every JDK**. Pointer coloring and the number of virtual address/bits change across versions. A description of JDK 19 or Generational ZGC must not be treated as an invariant structure of JDK 17.

Color is not a Java field that the application can read from **Object**. **System.identityHashCode(x)** and **x.toString()** do not give the memory address or GC color.

### 6.2. Colored pointers differ from compressed oops

**Compressed oops** in standard HotSpot encode many object references in narrower slots. ZGC's colored pointers serve GC state/relocation and have different constraints on pointer encoding. Do not assume Java 17 ZGC uses 4-byte narrowOop just because another 64-bit JVM with G1 has UseCompressedOops=true.

Check actual **UseCompressedOops**, **UseCompressedClassPointers**, and other final flags on the running HotSpot build. Object reference compression and class pointer compression are two separate mechanisms.

## 7. Load barriers and fast/slow path

A load barrier is code inserted by the compiler/VM on the reference read path when needed to check/reconstruct a valid reference.

Pseudo-code:

~~~text
function loadObjectReference(slot):
    ref = load(slot)

    if gcStateOf(ref) is good:
        return validObject(ref)

    return slowPathFix(slot, ref)
~~~

**Pseudo-code** only describes responsibility; there is no public Java API named slowPathFix or gcStateOf, and HotSpot may optimize/inline operations differently.

### 7.1. Why is the fast path so important?

Java code reads references extremely frequently. If every load had to go through a slow path with expensive locks/metadata lookups, throughput would drop sharply. ZGC optimizes the **good** state so the common case is as cheap as possible.

On a bad state, the slow path may:

- Mark the referent if needed.
- Find the object's location after relocation.
- Update/heal the slot containing the reference.
- Synchronize with the runtime relocation protocol.
- Return the right reference to Java code.

### 7.2. Lazy healing

An old reference is not necessarily updated in every location immediately when the collector moves an object. The update may happen when a mutator loads the reference or when appropriate GC phases process it.

Therefore **“finished relocating the object” does not mean “every slot pointing to the object has been replaced with the new address in the same millisecond”**.

### 7.3. A GC load barrier is not a volatile memory fence

A GC barrier serves memory safety and liveness/relocation invariants. The **Java Memory Model (JMM)** and happens-before between application threads are a different matter.

Two threads writing to the same unsynchronized reference field can still have a data race. Switching from G1 to ZGC does not turn that field into volatile or a lock.

## 8. ZPages and concurrent compaction

ZGC manages the heap using **ZPages** with appropriate allocation/relocation mechanisms. In ZGC designs, pages can belong to different size classes to handle small/medium/large objects.

Conceptual diagram:

~~~text
Before:
  Page P1: [Live A][Dead ][Live B][Dead ][Live C]
  Page P2: [Live D][Dead ][Dead  ][Live E]

Chosen relocation set:
  P1, P2 or a subset depending on heuristics

Concurrent relocate:
  Move live objects as needed

After (model):
  Page Q: [Live A][Live B][Live C][Live D][Live E][free...]

References are remapped/healed according to the GC protocol.
~~~

Do not claim every cycle moves all objects, that all pages have the same size, or that object order after GC matches the diagram. The collector selects pages/regions based on live bytes, fragmentation, availability of free space, and cost-benefit.

### 8.1. Relocation needs memory headroom

While copying an object from an old region to a new region, the VM may need enough space to hold the new object before it can completely free the old region. Combined with mutators still allocating, a heap **full right up to the live set** easily leads to allocation stalls.

That is, a low-pause collector may **cost extra memory** to achieve low latency. You cannot just set -Xmx equal to the bare live heap on paper and expect ZGC to run well on every workload.

## 9. Heap headroom and allocation rate

Capacity planning concept:

~~~text
Required heap ≈
   Live object graph
 + bytes allocated while concurrent GC is running
 + relocation / fragmentation overhead
 + burst capacity / safety margin
~~~

The formula above is only a **budgeting model**, not ZGC's algorithm for computing Xmx.

Hypothetical example:

~~~text
Live set                 5 GiB
Allocation rate          600 MiB/s
Concurrent cycle length  3 seconds

New allocations generated in 3 s:
  600 * 3 = 1800 MiB ≈ 1.76 GiB
~~~

Not every newly allocated object lives until the end of GC, so you cannot mechanically add 5 GiB + 1.76 GiB to guarantee sufficiency. But the example helps show **why allocation headroom exists**: while the collector is working, mutators are still creating new objects.

### 9.1. Allocation stall

When GC cannot keep up with allocation, the heap has no space to serve some allocations and threads may have to wait for GC to make progress or the VM needs to handle the pressure.

Consequences:

- **GC pause histogram still looks good**, but request latency spikes.
- GC CPU may compete with mutators.
- Too frequent GC cycles can reduce throughput.
- May need to increase Xmx, reduce allocation rate, increase CPU headroom, or review GC tuning.

**An allocation stall is not the same as an STW GC pause.** When diagnosing p99, both must be measured.

### 9.2. Near 100% heap utilization is not ZGC's goal

A heap constantly near Xmx can force ZGC to work continuously or lack relocation space. Increasing heap can help reduce stalls but incurs RAM cost. Conversely, giving too much heap to hit p99 is bad if the container is short on native memory. Balance is needed:

- Tail-latency SLO.
- Live set + burst allocation.
- CPU cores/quotas.
- RSS/container limits.
- GC cycle frequency and bandwidth.
- Infrastructure cost.

## 10. Important JVM options

| Option | Role | Notes |
| --- | --- | --- |
| **-XX:+UseZGC** | Select ZGC | Only on supported HotSpot/JDK builds |
| **-Xmx<size>** | Hard max Java heap | Most important flag to ensure headroom |
| **-Xms<size>** | Configured initial/minimum heap capacity | Can affect uncommit behavior |
| **-XX:SoftMaxHeapSize=<size>** | Soft target that ZGC tries to operate below | Can be exceeded to avoid allocation problems |
| **-XX:ConcGCThreads=<n>** | Concurrent GC thread parallelism | GC CPU contention with mutator |
| **-XX:ParallelGCThreads=<n>** | Parallelism in VM-selected work parts | Not the same as number of application threads |
| **-XX:+PrintFlagsFinal** | Print final JVM flag values | Read together with startup arguments |
| **-Xlog:gc=info** | GC summary logging | Use -Xlog:help to see tags |
| **-Xlog:gc*=debug** | More detailed diagnostics | Can log a lot, increasing overhead |
| **-XX:+/-ZUncommit** | Enable/prevent uncommitting unused heap in supported builds | Implementation-specific |
| **-XX:ZUncommitDelay=<seconds>** | Control uncommit delay in supported builds | Does not determine GC reclaiming objects by an exact deadline |

### 10.1. Xmx is most important

ZGC tuning documentation emphasizes setting max heap large enough to hold both the **live set** and have space for allocations while GC is concurrent. Do not infer from “pauses of a few ms” that the heap can be sized right down to the live data.

### 10.2. SoftMaxHeapSize is not a hard cap

Illustrative command:

~~~bash
java -XX:+UseZGC -Xms256m -Xmx2g -XX:SoftMaxHeapSize=1g MyService
~~~

MyService must be a compiled class with main. SoftMaxHeapSize is a soft target; the collector may use more to avoid allocation problems. **Xmx** remains the primary maximum limit.

### 10.3. ConcGCThreads: more is not always better

If the server has a limited CPU quota, increasing concurrent GC threads may make GC progress faster but take CPU away from request threads; latency/throughput may worsen.

Conversely, reducing threads too much may prevent GC from finishing in time, causing stalls. Do:

1. Measure GC CPU + mutator CPU.
2. Observe concurrent cycle length/stalls.
3. Choose thread count according to workloads, CPU quotas.
4. Benchmark across multiple runs.
5. Avoid tuning from a single pause chart.

### 10.4. Uncommit unused heap

ZGC can return some unused committed pages to the OS under suitable conditions. This reduces footprint for fluctuating workloads, but:

- Uncommit does not happen instantaneously when an object becomes unreachable.
- **Reserved** heap can still be large.
- Xms=Xmx usually reduces the ability to lower committed heap below minimum.
- Committed heap differs from RSS/native memory.
- Flags and heuristics change across JDKs.

Do not take a single ZGC RSS number and assume it has created multiple copies of data if an implementation has multiple virtual address views.

## 11. Generational ZGC from Java 21

The foundation of generational GC is the observation: **many objects die young**. A system split into young/old can collect young frequently, avoiding repeatedly scanning the entire live old graph.

**JDK 17 non-generational ZGC:** whole-heap marking per cycle, without JEP 439 Young/Old ZGC generations.

**JDK 21+ Generational ZGC:** young/old generations, concurrent mechanisms, and appropriate barriers to maintain liveness/cross-generation references.

~~~text
ZGC Java 17:
  Heap -> one logical generation
  Concurrent whole-heap marking/relocation cycles

Generational ZGC:
  Heap
    +-- Young generation: new objects, many die early
    +-- Old generation: long-lived objects
  Collect generations according to separate policies
~~~

This is a **conceptual model**, not an exact address layout description.

### 11.1. Why is Generational ZGC beneficial?

For workloads creating many young objects while holding a large old live set, rescanning the entire heap frequently can incur CPU cost. Generational collection can focus on the young graph in many rounds, reducing:

- Work on long-lived objects.
- GC CPU overhead.
- Allocation-stall risk.
- Heap headroom needed to maintain progress in suitable cases.

Not all workloads are guaranteed to benefit equally; if objects are promoted/have different lifetimes, effectiveness depends on the pattern.

### 11.2. Additional write/store barriers

Generational ZGC needs to know **old → young** references and graph updates to collect each generation safely. Therefore, modern designs have **store/write barriers** alongside the load barrier/colored-pointer scheme.

Do not apply the statement “ZGC only has load barriers, no write barriers” to all JDKs. Nor should ZGC be treated as an exact copy of **G1 card table/remembered set**; tracking structures differ by collector.

### 11.3. Versioned commands

~~~bash
# JDK 17: non-generational
java -XX:+UseZGC -jar app.jar

# JDK 21: select generational
java -XX:+UseZGC -XX:+ZGenerational -jar app.jar

# JDK 24/25: generational-only
java -XX:+UseZGC -jar app.jar
~~~

Use version-explicit startup scripts; unsupported flags may be warned/ignored, creating a false impression that you are running the mode you chose.

## 12. Comparing ZGC, G1, Parallel, and Serial

| Goal | ZGC | G1 | Parallel | Serial |
| --- | --- | --- | --- | --- |
| Primary priority | Very low GC pauses | Balance throughput/latency | Throughput on multiple CPUs | Simplicity for small heaps |
| Concurrent marking | Yes | Yes in old-cycle work | Much STW work | Mostly STW |
| Concurrent relocation | Yes, core focus | CSet evacuation typically in pauses | Not equivalent | Not equivalent |
| Heap headroom | Extremely important | Also needs evacuation space | Needs adequate free space | Needs adequate free space |
| CPU overhead | Concurrent GC/barrier work | Concurrent/parallel GC work, RSet | High CPU during pauses | Fewer structures but potentially larger pauses |
| Choose when | p99/tail-latency is critical | Common server workloads | Throughput-centric batch | Small/few threads |

The table is only a **guideline**, not proof that ZGC always “beats G1”. The default collector also depends on version and resource constraints. On CPU-starved workloads, concurrent GC may affect throughput more than expected.

### 12.1. Selection process

- If p99 is dominated by GC pauses, consider ZGC.
- If CPU is already overloaded, evaluate concurrent GC cost.
- If the heap is small, G1/Serial may be good enough and simpler.
- If running batch jobs that can tolerate long pauses, Parallel throughput may fit.
- If services have sharp load variations, evaluate memory elasticity/uncommit.
- If the JVM is in a cgroup/container, measure actual CPU quota and native memory overhead.

## 13. Java 17+ Demo: correctness of the reference graph does not depend on GC

Create **ZgcReachabilityDemo.java**:

~~~java
public class ZgcReachabilityDemo {
    static final class Node {
        final int id;
        Node next;
        Node(int id) {
            this.id = id;
        }
    }

    public static void main(String[] args) {
        Node first = new Node(1);
        Node second = new Node(2);
        Node third = new Node(3);

        first.next = second;
        second.next = third;
        third.next = first; // cycle

        System.out.println("first=" + first.id);
        System.out.println("second=" + first.next.id);
        System.out.println("third=" + first.next.next.id);
        System.out.println("cycle=" +
                (first.next.next.next == first));
    }
}
~~~

Compile and run on HotSpot JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 ZgcReachabilityDemo.java
java -XX:+UseZGC ZgcReachabilityDemo
~~~

**Stdout from Java code only (when no extra logging is enabled):**

~~~text
first=1
second=2
third=3
cycle=true
~~~

Explanation: The cycle first→second→third→first remains reachable while main uses first. Once there is no root path to the group, the entire cycle can be reclaimed by GC. ZGC must not alter Java reference identity, regardless of whether objects are moved.

Run the same bytecode with:

~~~bash
java -XX:+UseG1GC ZgcReachabilityDemo
~~~

Java-level output is the same; the collector difference is how/when GC processes the heap. A small program like this may not trigger any GC cycle.

## 14. Java 17+ Demo: allocation workload to observe GC

Create **ZgcAllocationLab.java**:

~~~java
public class ZgcAllocationLab {
    private static final int BLOCK = 256 * 1024;
    private static final int KEEP = 16;
    private static final int ROUNDS = 120;
    private static final int TEMP_PER_ROUND = 32;

    public static void main(String[] args) {
        byte[][] retained = new byte[KEEP][];
        for (int i = 0; i < KEEP; i++) {
            retained[i] = new byte[BLOCK];
            retained[i][0] = (byte) i;
        }

        long checksum = 0;
        for (int r = 0; r < ROUNDS; r++) {
            for (int j = 0; j < TEMP_PER_ROUND; j++) {
                byte[] temp = new byte[BLOCK];
                temp[0] = 1;
                checksum += temp[0];
            }
        }

        long retainedBytes = (long) KEEP * BLOCK;
        System.out.println("retainedBlocks=" + retained.length);
        System.out.println("retainedBytes=" + retainedBytes);
        System.out.println("checksum=" + checksum);
        java.lang.ref.Reference.reachabilityFence(retained);
    }
}
~~~

Commands:

~~~bash
javac --release 17 -encoding UTF-8 ZgcAllocationLab.java
java -XX:+UseZGC -Xms64m -Xmx128m ZgcAllocationLab
~~~

**Stdout of Java logic (if the program finishes, with no extra logging):**

~~~text
retainedBlocks=16
retainedBytes=4194304
checksum=3840
~~~

Analysis:

- Retained array payload = 16 × 256 KiB = **4 MiB**, excluding array headers.
- There are 120 × 32 = **3840 iterations creating temporary byte[]** in Java source.
- Each temporary[0] is assigned 1 and added to checksum, so the total is **3840**.
- Many temporary arrays may die early, creating allocation pressure over time.
- **Reference.reachabilityFence(retained)** keeps strong reachability for the retained graph up to that point per the API; it does not force GC or pin addresses.
- The JIT may optimize while preserving semantics; **actual allocated bytes must be measured with a profiler/JFR**, not inferred with certainty from source.
- Number of collections, pauses, heap regions, and timing are not fixed stdout.

### 14.1. Enable GC log when running the demo

~~~bash
java -XX:+UseZGC -Xms64m -Xmx128m -Xlog:gc* ZgcAllocationLab
~~~

Many GC lines may be output with formats depending on JDK, workload, and heuristics. Application stdout lines still have the same content if the program completes, though logs may appear interleaved.

Multi-line Bash command:

~~~bash
java -XX:+UseZGC -Xms64m -Xmx128m \
  -Xlog:gc*=debug ZgcAllocationLab
~~~

In Windows PowerShell/Command Prompt, put all flags on one line; Bash backslash continuation does not work verbatim.

### 14.2. Compare with G1

~~~bash
java -XX:+UseG1GC -Xms64m -Xmx128m -Xlog:gc* ZgcAllocationLab
~~~

Measure across multiple runs, discard warm-up bias, and do not use this small demo to declare which collector is best for production.

### 14.3. Risks of the demo

- -Xmx128m too small for some machines/workloads may increase GC frequency or stalls.
- GC events may be few or many depending on VM/JIT/OS; do not guess exact counts.
- Debug/trace logs can consume disk space.
- Do not use System.gc() to turn a test into a timing guarantee.
- When wanting professional benchmarks, use JMH/JFR and realistic workloads.

## 15. Java 17+ Demo: monitoring GC beans

Java ManagementFactory provides **GarbageCollectorMXBean**. Bean names/counts/times depend on JVM/collector and may change between versions.

Create **GcBeansDemo.java**:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.List;

public class GcBeansDemo {
    public static void main(String[] args) {
        List<GarbageCollectorMXBean> beans =
                ManagementFactory.getGarbageCollectorMXBeans();

        System.out.println("hasBeans=" + !beans.isEmpty());

        for (GarbageCollectorMXBean bean : beans) {
            System.out.println("name=" + bean.getName());
            System.out.println("count=" + bean.getCollectionCount());
            System.out.println("timeMs=" + bean.getCollectionTime());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 GcBeansDemo.java
java -XX:+UseZGC GcBeansDemo
~~~

**There is no single exact universal stdout** for bean names/collection counts/timings across all JDKs and processes, so this article does not fabricate output. The exercise is to observe **which beans are currently present** and correlate the data with GC logs.

In HotSpot Java 17, you may see beans for ZGC pauses/cycles. But when moving to JDK25 Generational ZGC, do not hardcode Java17 bean names as logic conditions.

## 16. Analyzing ZGC GC logs

Start with lightweight logs:

~~~bash
java -XX:+UseZGC -Xlog:gc=info ZgcAllocationLab
~~~

More detail for experiments:

~~~bash
java -XX:+UseZGC -Xlog:gc*=debug ZgcAllocationLab
~~~

Tag names/structures may differ between JDK 17/21/25; to see the logging configuration supported by the **current runtime**:

~~~bash
java -Xlog:help
~~~

### 16.1. Distinguish pause, concurrent cycle, and stall

| Fact | Read correctly |
| --- | --- |
| **Pause Mark Start** | A synchronization pause |
| **Pause Mark End** | A synchronization pause |
| **Pause Relocate Start** | A synchronization pause |
| **Concurrent Mark** | GC works while the application is still running |
| **Concurrent Relocate** | GC can move objects concurrently with mutators |
| **Allocation Stall** | Mutator may have to wait to allocate; must be treated as a separate latency source |
| **Used before/after GC** | Heap occupancy, not total process RSS |
| **Cycle duration** | Total elapsed phase processing, not synonymous with STW |

### 16.2. If GC pauses are low but p99 is still high

Check in order:

1. Do timestamps of request traces and GC logs overlap?
2. Are there **allocation stalls** or is the heap near Xmx?
3. What are CPU utilization and cgroup throttling like?
4. Are concurrent GC threads competing for CPU with request threads?
5. Does the application have locks/monitor contention/ThreadLocal leaks?
6. Do database/network calls account for most of the latency?
7. Are JIT compilation, class loading, or other safepoint operations spiking?
8. Did traffic levels and cache misses change when testing the collector?

**A 300 ms GC cycle** only means that GC work spanned 300 ms elapsed; the application may have been running for most of that time.

## 17. Virtual memory and memory footprint

Some ZGC designs use **virtual memory multi-mapping**/multiple address views to serve colored pointer semantics. When reading memory tools:

- **Virtual address space reserved** does not equal committed physical pages.
- One physical page may appear through multiple virtual views in some implementations.
- **Heap used**, **heap committed**, **heap reserved**, **process RSS**, and **container working set** are different metrics.
- Do not conclude a memory leak just from a large virtual address space number.
- This layout may change between versions; do not treat the JDK17 diagram as a guaranteed API for JDK25.

Besides the Java heap there are Metaspace, JIT code cache, thread stacks, native buffers, GC metadata, and runtime libraries. Therefore **-Xmx is not the limit on total process RSS**.

### 17.1. Uncommit unused heap

When traffic drops, ZGC can return unused committed heap memory to the OS under appropriate conditions. This is useful for services with uneven load.

But:

- There is no contract that “every time GC reclaims 1 GiB, RSS drops by 1 GiB immediately”.
- Xms can establish a memory floor.
- OS accounting and native allocations still affect RSS.
- If verification is needed, measure **used/committed/reserved** via logs/JMX and measure process memory separately.

## 18. ZGC and memory leaks

ZGC is still a tracing garbage collector: an object graph **strongly reachable** from GC roots is not considered garbage just because the application “no longer uses it in business logic”.

Example:

~~~text
Static Cache ROOT
      |
      +--> Map
             |
             +--> Expired session
                       |
                       +--> Large data arrays
~~~

If the application does not remove/evict sessions, ZGC still has to keep that graph. Replacing Parallel/G1 with ZGC **does not cure logical memory leaks**.

Common sources of retention:

- Unbounded static collections.
- ThreadLocal values in pooled threads.
- Unsubscribed event listeners.
- Scheduled tasks holding captured objects.
- Long-lived class loaders or JNI global references.
- Session caches/queues without backpressure.

To fix: heap dump, dominator tree, path-to-GC-root, fix lifecycle; not just increasing -Xmx or changing GC.

## 19. Common misconceptions

1. **“ZGC has no STW.”** False: there are short synchronization pauses.
2. **“ZGC p99 response is always under 1 ms.”** False: GC pause is not end-to-end latency.
3. **“Concurrent GC takes no CPU from the application.”** False: GC threads compete for resources.
4. **“ZGC always has higher throughput than G1.”** False: depends on workload and CPU headroom.
5. **“A 100 ms ZGC cycle means 100 ms STW.”** False: there are concurrent phases.
6. **“A heap exactly equal to the live set is enough.”** False: there is also allocation/relocation headroom.
7. **“Java 17 ZGC is generational.”** False; Generational ZGC appeared in JDK21.
8. **“JDK25 needs -XX:+ZGenerational.”** False; non-generational mode was removed from JDK24.
9. **“A colored pointer is a readable Java Object property.”** False: VM-private encoding.
10. **“A load barrier is a volatile memory fence.”** False: GC barriers differ from JMM synchronization.
11. **“Every reference load must run the slow path.”** False: the good-color fast path is optimized.
12. **“ZGC does not move objects.”** False: concurrent relocation/compaction is a defining feature.
13. **“GC moving changes a==b.”** False: identity semantics do not change.
14. **“ZGC automatically reclaims reference cycles that are still rooted.”** False: strong reachability still keeps objects alive.
15. **“All ZGC versions use the same color bit layout.”** False: internals evolve across versions.
16. **“ZGC only uses load barriers forever.”** False when speaking of modern Generational ZGC.
17. **“The default GC log points to the exact source line causing allocation.”** False: profiling/tracing is needed.
18. **“Increasing ConcGCThreads always lowers latency.”** False: there is a CPU contention trade-off.
19. **“SoftMaxHeapSize is a hard limit.”** False: a soft target.
20. **“Xmx limits all JVM native memory.”** False: heap differs from native allocations.
21. **“System.gc() definitely triggers a ZGC cycle and finishes reclaiming.”** There is no such timing guarantee.
22. **“A 1-second microbenchmark result is enough to pick a collector.”** False: warm-up, realistic live set, and long-tail need to be measured.
23. **“Low committed heap means high GC pause.”** There is no direct relationship sufficient to conclude that.
24. **“ZGC is supported on every JVM/OS regardless of vendor.”** False: check implementation/build/platform.
25. **“Just enabling ZGC makes allocation stalls disappear.”** False if headroom or GC progress is lacking.
26. **“Setting Xms=Xmx is always best.”** False: it can affect memory elasticity/uncommit.
27. **“With colored pointers, hashCode is the physical address.”** False.
28. **“Generational ZGC is a copy of G1 under a different name.”** False: collector architecture/barriers differ.
29. **“A larger heap always creates linearly longer ZGC pauses.”** Not a design characteristic; measure in practice.
30. **“OutOfMemoryError can be ignored because ZGC is concurrent.”** False: memory capacity is still finite.

## 20. Self-check exercises with answers

**Exercise 1.** What does ZGC optimize?

**Answer:** Stop-the-world GC pause latency, by performing almost all marking and relocation concurrently.

**Exercise 2.** A concurrent cycle takes 400 ms; was the application definitely stopped for 400 ms?

**Answer:** No. You must look at the pause phases separately; most of the cycle can run concurrently.

**Exercise 3.** Object X moves from A to B while a mutator holds the old reference. Which technologies handle this?

**Answer:** Colored pointers, load barriers, and relocation/forwarding metadata.

**Exercise 4.** When Java 17 uses -XX:+UseZGC, does it already have young/old generations per JEP439?

**Answer:** No. That is non-generational ZGC.

**Exercise 5.** How does JDK21 enable generational?

**Answer:** -XX:+UseZGC -XX:+ZGenerational.

**Exercise 6.** Why does JDK24/25 not need ZGenerational?

**Answer:** JDK24 removed non-generational mode; ZGC is generational-only.

**Exercise 7.** Live set = 8 GiB, -Xmx=8g, high allocation rate. Is there a risk?

**Answer:** Yes: lack of headroom, allocation stalls/OOME. Capacity must be provisioned for the workload.

**Exercise 8.** GC pauses are steady at <1 ms but request p99 is bad. What should be checked?

**Answer:** Allocation stalls, CPU quota, I/O, locks, JIT, and downstream operations, not just STW.

**Exercise 9.** Is increasing ConcGCThreads without limit good?

**Answer:** No; faster-progressing GC can compete for CPU with mutators and reduce throughput.

**Exercise 10.** Is SoftMaxHeapSize allowed to be exceeded?

**Answer:** Yes; it is a soft target, the max heap limit is Xmx.

**Exercise 11.** Do colored pointers change Object.equals/==?

**Answer:** No. The JVM must preserve Java reference/object identity semantics.

**Exercise 12.** Can an entire cycle A→B→A with no remaining root path be reclaimed by ZGC?

**Answer:** Yes, like other tracing GCs; a cycle does not by itself create a memory leak.

**Exercise 13.** Why is Generational ZGC often more efficient than non-generational with many temporary objects?

**Answer:** It can process the young generation frequently without having to traverse the entire old live set every young cycle, while tracking cross-gen references correctly.

**Exercise 14.** Does 1 TiB reserved heap mean 1 TiB of physical RAM is in use?

**Answer:** No. Reserved virtual address space differs from committed/used memory and RSS.

**Exercise 15.** If a collection has not occurred in a demo, did -XX:+UseZGC fail?

**Answer:** No. A small program may finish before GC needs to run; check final flags/log initialization.

**Exercise 16.** Will an application with a memory leak from a static HashMap stop leaking when switching to ZGC?

**Answer:** No. The rooted object graph is still reachable; cache eviction/lifecycle must be fixed.

**Exercise 17.** GC pauses are small, but there are large allocation stalls. What does ZGC tuning prioritize?

**Answer:** Measuring allocation rate, live set, headroom/Xmx, concurrent GC CPU/progress, and container budget.

**Exercise 18.** An older JDK only supports experimental ZGC: can the Java17 flag be used right away?

**Answer:** Not necessarily. Check JDK version, platform, and flags; JDK11 initially required experimental unlock.

**Exercise 19.** Does a GC load barrier make a Java data race thread-safe?

**Answer:** No. Thread safety belongs separately to JMM locks/volatile/atomics.

**Exercise 20.** When choosing a collector, is comparing only average request latency enough?

**Answer:** No. You must measure p95/p99/p99.9, throughput, CPU/memory costs, GC pauses, and stalls under an equivalent workload.

## 21. Checklist for applying in a real environment

1. Record **JDK vendor/version/build, OS/architecture, CPU/container quotas** before tuning.
2. Distinguish **JDK17 non-generational** and **JDK21+ Generational ZGC**.
3. Enable **-XX:+UseZGC** on supported HotSpot, check final JVM flags.
4. Keep **-Xmx** sufficient for live set + allocation/relocation headroom.
5. Monitor both **STW pauses** and **concurrent cycle durations**.
6. Especially watch **allocation stalls** and GC CPU contention.
7. If using **SoftMaxHeapSize**, understand it is a soft target and can be exceeded.
8. Do not use the unsupported **ZGenerational** flag on JDK24+.
9. Read **java -Xlog:help** before building parsing rules for logs.
10. Compare G1/ZGC on the same realistic workload, JIT warm-up, and SLA.
11. Track application p99 and JVM metrics on the same timestamps.
12. Distinguish Java heap from process RSS/native memory and reserved address-space regions.
13. Do not rely on System.gc() to create a benchmark with deterministic timing.
14. Use heap dump/path-to-GC-roots when suspecting a memory leak; GC does not reclaim rooted graphs.
15. Read documentation for the exact major version because coloring, barriers, and pause logs can change.

### Official and in-depth documentation

- **Oracle Java SE 17 — The Z Garbage Collector:** https://docs.oracle.com/en/java/javase/17/gctuning/z-garbage-collector1.html
- **Oracle Java SE 17 — Available Collectors:** https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html
- **Oracle JVM Performance — Tuning ZGC:** https://ops.java/performance/jvm/articles/tuning-zgc/
- **OpenJDK JEP 333 — ZGC (experimental):** https://openjdk.org/jeps/333
- **OpenJDK JEP 377 — ZGC (production):** https://openjdk.org/jeps/377
- **OpenJDK JEP 439 — Generational ZGC:** https://openjdk.org/jeps/439
- **OpenJDK JEP 474 — Generational Mode by Default:** https://openjdk.org/jeps/474
- **OpenJDK JEP 490 — Remove Non-Generational Mode:** https://openjdk.org/jeps/490
- **Dev.java — Deep-dive of ZGC's Architecture:** https://dev.java/learn/jvm/tool/garbage-collection/zgc-deepdive/
- **Oracle Java SE 17 — java Command / Unified JVM Logging:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html

**Core takeaway:** ZGC achieves its very short pause goal by performing most object marking and relocation **concurrently with the application**, using **colored pointers/load barriers** to keep references safe. This is a trade-off between **tail latency, CPU, and memory dedicated to concurrent GC**; to optimize, you must measure **GC pauses, allocation stalls, throughput, and p99**, and identify the exact **ZGC version** rather than applying Java 17 mechanisms to Java 25.