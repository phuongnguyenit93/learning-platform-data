# Humongous Objects, Evacuation Failure, and Full GC in G1

In HotSpot, **G1 (Garbage-First Garbage Collector)** manages the Java heap as many small areas called **regions**. Instead of always collecting the entire heap, G1 prioritizes sets of regions that are likely to reclaim a lot of memory within a pause time consistent with the latency target. However, three special phenomena can cause G1 to do more work than expected:

- **Humongous objects**: objects that are large relative to a region, must occupy **a contiguous sequence of regions**, and are managed differently from small objects in Eden.
- **Evacuation failure / to-space exhausted**: when G1 attempts to copy live objects out of the collection set but **does not have enough destination regions** to move them to.
- **Full GC**: a heap-wide collection path, which may include **in-place compaction**, usually serving as a fallback when G1 cannot free enough memory through normal young/mixed/concurrent mechanisms.

These three concepts have a cause-and-effect relationship in many situations, but they are **not synonymous**. Having a humongous object does not necessarily cause an evacuation failure; having an evacuation failure does not necessarily trigger a Full GC immediately; and a Full GC can occur for other reasons.

This article follows **HotSpot/OpenJDK Java 17** and the **Oracle Java SE 17 G1 Garbage Collector / G1 Tuning** documentation. The memory region policies and JVM options mentioned are **implementation/version-specific details**, not mandatory requirements for every JVM or every G1 release.

## 1. Reviewing G1 Structure: A Heap Made of Regions

G1 divides the Java heap into **equal-sized regions**. The region size is usually chosen by the JVM based on the heap size, or configured with `-XX:G1HeapRegionSize` within the limits supported by the build. A region at any given time has a role such as Eden, Survivor, Old, Free, or an area dedicated to a humongous object.

```text
Java heap in the G1 model:

+---------+---------+---------+---------+---------+---------+
| Eden R0 | Eden R1 | Surv R2 | Old R3  | Free R4 | Free R5 |
+---------+---------+---------+---------+---------+---------+
| Old R6  | Hum S   | Hum C   | Free R9 | Old R10 | Free R11|
+---------+---------+---------+---------+---------+---------+

Hum S = StartsHumongous
Hum C = ContinuesHumongous

Each cell illustrates an equal-sized region.
Region types are logical roles, not required to be contiguous
by Eden/Survivor/Old groups.
```

G1 typically collects **collection sets (CSet)** selected during young/mixed collections:

1. Identify the set of regions to collect.
2. Find references to objects in the CSet from GC roots and from regions outside the CSet; remembered sets/card tracking assist with this work.
3. **Evacuate** (copy) live objects to appropriate destination regions.
4. Update/redirect references so that Java object identity and access remain correct.
5. When safe, reclaim the source regions that were successfully processed.

An important point: **G1 concurrent marking** can run concurrently with Java application threads to evaluate liveness, but **G1 Java 17 young/mixed evacuation primarily happens during stop-the-world pauses**. Do not infer that "G1 concurrent" means all object copying operations occur concurrently like collectors designed for concurrent relocation.

## 2. How Is a Humongous Object Identified?

According to **Java 17** G1 documentation, an object whose total size is **greater than or equal to half the size of a region** is classified as **humongous**.

```text
R = size of one G1 region

If object size >= R/2
  => humongous object

Example R = 1 MiB:
  threshold for total object size ≈ 512 KiB
```

**Note:** the size considered is the **object size in the heap**, including object header and appropriate alignment/padding, not simply the number of payload bytes the programmer passes to `new byte[n]`. Therefore, `new byte[512 * 1024]` can exceed the threshold even when the payload is exactly 512 KiB. Do not treat array length or `String.length()` as the exact object size while forgetting the actual layout.

### Common Examples Where Humongous Objects Appear

- A very large `byte[]` used to hold an image, compressed data, a file, or a network payload copied as a whole.
- A large `char[]`, `int[]`, `long[]`, or `Object[]`.
- A large backing array of a collection or buffer **on the Java heap**.
- An object containing a large primitive data area whose size exceeds the threshold (in practice, large Java objects are usually arrays).
- Intermediate allocations in serialization or batch processing with very large payloads.

Do not confuse this with **direct buffer backing memory**: `ByteBuffer.allocateDirect` has a backing region outside the Java heap according to the API. The Java wrapper of a direct buffer is still a Java object, but a large native allocation **does not automatically mean a G1 humongous Java heap object**.

## 3. Where Are Humongous Objects Allocated?

A humongous object is managed by G1 as a **contiguous sequence of regions** in the logical old-generation space. G1 uses the following region types:

- **`StartsHumongous`**: the first region containing the start of the object.
- **`ContinuesHumongous`**: one or more subsequent regions for the remainder if the object is larger than one region.

The object starts at the beginning of the first region. If the object size does not completely fill the last region, the remainder of the last region **cannot be allocated to another object** until the entire humongous object is reclaimed.

```text
Suppose region size = 1 MiB
Object H has total size ~1.25 MiB

+----------------------+----------------------+
| StartsHumongous      | ContinuesHumongous   |
| H occupies full 1 MiB| H uses ~0.25 MiB     |
|                      | ~0.75 MiB left unused|
|                      | for other objects    |
+----------------------+----------------------+

Each region = 1 MiB; this is a simplified rounded example.
```

If the object size is `S` and region size is `R`, the number of regions needed at the model level is:

```text
neededRegions = ceil(S / R)

reservedRegionBytesForObject = neededRegions * R
unusedTailBytes = reservedRegionBytesForObject - S
```

This formula helps understand **internal waste in the last region**, not HotSpot's exact object size calculation algorithm across every layout. Waste increases noticeably when an object is just slightly larger than an integer multiple of the region size, for example about 1.01 MiB in a 1 MiB region requires 2 regions but leaves nearly 0.99 MiB empty at the end.

### Humongous Allocation Does Not Go Through the Normal Eden Path

Because it requires a sequence of regions, this allocation is accounted for directly in the old generation according to G1, instead of going through the normal `Eden → Survivor → Old` lifecycle of a small object. Therefore:

- The allocation rate of humongous objects can cause **old occupancy to rise rapidly**.
- Bursts of large arrays can affect **IHOP/concurrent marking**, even when they are very short-lived.
- You need to measure the **size and count of humongous objects**, not just total allocation bytes/second.

An object being classified as humongous does not mean it has to be long-lived in business logic. It can be created, used for a few milliseconds, and discarded, yet it still requires its own reclamation mechanism.

## 4. Two Forms of Memory Waste: Unused Tail and Inter-Region Fragmentation

**First: unused tail in the last region.** The unused portion of the humongous region sequence assigned to that object that cannot be allocated to another object. For example, a 1.1 MiB object needs two 1 MiB regions and wastes about 0.9 MiB (model number).

**Second: fragmentation at the contiguous regions level.** G1 needs to find **a contiguous sequence of free regions** long enough to place the humongous object. The total number of free regions may be large, but if the free runs are broken up, large allocations still run into trouble.

```text
Each dot . is 1 free region; X is an occupied region.

Heap regions in address order:

.. X . XX .... X .. X .

Free runs: lengths 2, 1, 4, 2, 1
Total free regions = 10
Longest contiguous free run = 4

Object needing 5 contiguous regions:
  NO free run long enough in this layout,
  even though total free regions = 10.
```

This is an illustrative example independent of an actual heap snapshot. G1 also has recovery mechanisms, concurrent reclamation, and Full GC; one cannot conclude from the diagram that the VM will definitely throw OOME immediately.

### Why Free Heap Does Not Guarantee Humongous Allocation Success?

`-Xmx - used` is a total capacity difference, not a measure of "longest contiguous region run". A G1 heap can have **large total free space** and still struggle to allocate an object requiring multiple contiguous regions. That is why an application can hit Full GC/OOME before the overall heap dashboard reports 100% occupancy.

## 5. Java 17: Calculating the Threshold and Region Count with a Deterministic Model

Create the file **`HumongousMath.java`**:

```java
public class HumongousMath {
    private static final long KIB = 1024L;
    private static final long MIB = 1024L * KIB;

    private static long regionsNeeded(long objectBytes, long regionBytes) {
        if (objectBytes <= 0 || regionBytes <= 0) {
            throw new IllegalArgumentException("positive sizes required");
        }
        return 1 + (objectBytes - 1) / regionBytes;
    }

    public static void main(String[] args) {
        long region = 1 * MIB;
        long threshold = region / 2;
        long object = MIB + 256 * KIB; // 1.25 MiB, assumed total size
        long regions = regionsNeeded(object, region);
        long tail = regions * region - object;

        System.out.println("regionKiB=" + region / KIB);
        System.out.println("thresholdKiB=" + threshold / KIB);
        System.out.println("objectKiB=" + object / KIB);
        System.out.println("humongous=" + (object >= threshold));
        System.out.println("regionsNeeded=" + regions);
        System.out.println("unusedTailKiB=" + tail / KIB);
    }
}
```

```bash
javac --release 17 HumongousMath.java
java HumongousMath
```

**Exact stdout:**

```text
regionKiB=1024
thresholdKiB=512
objectKiB=1280
humongous=true
regionsNeeded=2
unusedTailKiB=768
```

The program only simulates a **known size**: it does not call any API to measure actual object size on HotSpot. The line `object = MIB + 256 * KIB` is an **assumed** total object bytes value, not a guarantee that `new byte[...]` has an object size equal to that exact value.

### How to Calculate Carefully Based on Actual Payload?

A `byte[]` has a header, length field, and alignment. On HotSpot, overhead depends on 32-/64-bit, compressed oops/class pointers, object alignment, and runtime build. If you need to predict class size close to reality, use appropriate profilers/diagnostics and verify against the running JVM; do not apply a fixed "16 bytes" header number across all configurations. When the threshold is too close to the payload, leave a safety margin or measure bytecode/runtime to avoid being on the wrong side of the boundary.

## 6. What Is the Impact of Changing Region Size?

Commonly used HotSpot flag:

```bash
java -Xms128m -Xmx512m -XX:+UseG1GC \
  -XX:G1HeapRegionSize=2m -jar app.jar
```

`app.jar` is an illustrative JAR that must exist; the command uses Unix/Bash line continuation. On Windows PowerShell, put it on one line or change the line-continuation syntax accordingly. Region size is bounded by G1/HotSpot per build; do not pick an arbitrary value and assume the JVM will always accept it.

If the region size increases from 1 MiB to 2 MiB, the humongous threshold increases from around 512 KiB to **1 MiB**. An object with a total size of around 768 KiB can:

- Be humongous when regions are 1 MiB.
- Become a regular object on the normal allocation path when regions are 2 MiB.

**However, do not infer "the larger the region size, the better":**

- Larger regions mean fewer regions, reducing granularity when G1 selects collection sets.
- More bytes per region can affect pause predictability, mixed collection flexibility, humongous tail waste for other sizes, remembered-set behavior, and fragmentation.
- Objects larger than the new threshold are still humongous.
- Increasing region size can introduce trade-offs across different workloads and heap sizes.

Adjust only when a histogram shows **many allocations sitting right above the old threshold**, and benchmarks on the exact JDK 17 build/workload prove a benefit.

## 7. Humongous Reclamation: When Does G1 Reclaim the Regions?

In Java 17 G1, unreachable humongous objects can be reclaimed through:

1. **Cleanup after concurrent marking** when liveness allows and the collector finishes an appropriate cycle.
2. **Eager reclaim** during some GC pauses for **humongous primitive arrays** that meet conditions where the collector determines they are no longer referenced using safe heuristics. This mechanism depends on the `-XX:G1EagerReclaimHumongousObjects` flag and implementation policy.
3. **Full GC**, if the object truly no longer needs to be kept alive and the collector performs a whole-heap collection/fallback.

Do not say "G1 must always wait for a Full GC to reclaim humongous objects." Also do not say "dropping a reference frees the region immediately": a GC phase/cycle must safely determine that it can be reclaimed.

### Why Are Primitive Arrays Highlighted?

Oracle Java 17 documentation notes **eager reclamation** for humongous objects that are **arrays of primitive types** (for example `byte[]`, `int[]`). Because elements of a primitive array **are not Java object references**, the algorithm and safety determination for reclamation can be simpler than for an array containing object references.

However:

- Do not promise that **every** unreachable primitive array will be reclaimed at the very next pause.
- This heuristic depends on the state of references/regions and the JVM build.
- Humongous `Object[]` should not be assumed to have the exact same eager reclaim behavior as `byte[]`.
- Use GC logs to confirm actual reclamation, rather than relying on a `System.gc()` in code.

### Why Might a Humongous Object Not Be Moved?

G1 normally excludes humongous regions from **young/mixed evacuation collection sets**: they are handled by a separate mechanism, not copied on every Young GC like small objects in Eden. Java 17 G1 documentation describes them as mostly staying in place along with contiguous-region constraints, even during Full GC. **Do not claim that Full GC will always compact/move every humongous object to a new location to solve fragmentation.** Specific movement/fallback policies vary by JDK version and implementation; evaluate the exact Java 17 build being run.

## 8. Humongous Allocation Can Trigger Concurrent Marking Early

In G1, each humongous allocation can trigger an **Initiating Heap Occupancy (IHOP)** check. If old/heap occupancy per policy exceeds the threshold and no appropriate marking cycle is active, G1 can start a **Concurrent Start young collection** to initiate concurrent marking.

Consequences:

- An application creating many large temporary arrays can generate **many marking requests** even though the data dies fairly quickly.
- Old region occupancy can rise due to humongous allocations before reclamation can catch up.
- Marking uses **Snapshot-At-The-Beginning (SATB)**; an object that was alive at the start of the snapshot but dies mid-cycle may still be considered alive for that cycle, delaying reclamation until a later appropriate time.
- Allocation bursts while marking is running can still fill up additional regions.

An important point about logs: a "Concurrent Start" message near a humongous allocation is a sign they may be related, **not proof that every humongous allocation causes a new cycle**.

### IHOP and Adaptive Marking

G1 can calculate the threshold to start marking based on predictions such as old allocation/promotion rate and the time marking takes. Related parameters:

- `-XX:InitiatingHeapOccupancyPercent`
- `-XX:+G1UseAdaptiveIHOP` or `-XX:-G1UseAdaptiveIHOP` depending on specific tuning
- `-XX:G1ReservePercent`
- `-XX:ConcGCThreads`

Do not tune all flags according to a generic table. If marking starts too late relative to the **rate at which old/humongous occupancy grows**, G1 may not finish marking/mixed reclamation before headroom runs out. Conversely, if it starts too early, it can consume extra CPU/GC work and hurt throughput.

## 9. Evacuation: Why Is To-Space Needed?

During a young/mixed GC, G1 usually moves live objects from the CSet to **to-space** (destination regions) so that source regions can be reclaimed.

```text
Before pause:

CSet:
  Eden R0  : 30 MiB allocated, 5 MiB live
  Eden R1  : 30 MiB allocated, 8 MiB live
  Old  R2  : 30 MiB allocated, 20 MiB live

Outside CSet:
  Free destination capacity (model) = 40 MiB

Live bytes to preserve/potentially copy ~33 MiB.
In this simple model, destination appears sufficient.
```

These model numbers do not represent actual G1 region sizes, because if a region were 30 MiB it would have to follow the collector's size rules; they only illustrate **region set capacity**, not three 30 MiB G1 regions of a real JVM.

When G1 moves objects, forwarding metadata ensures that two references pointing to the same logical object continue to resolve to one valid destination, while reference updating/processing maintains correctness before the application resumes.

**To-space is not a separate RAM area outside `-Xmx`.** It resides within heap regions used by G1 policy as destinations, and requires usable **headroom**.

### Live Ratio Determines Copy Pressure

Suppose a CSet already has 300 MiB of objects:

| Scenario | Live bytes | Dead bytes | Survival ratio |
| --- | ---: | ---: | ---: |
| Young data dies quickly | 30 MiB | 270 MiB | 10% |
| Many long-lived objects | 250 MiB | 50 MiB | 83.33% |

The second CSet may need to preserve/copy far more bytes, even when the allocation volume before GC is similar. This increases to-space pressure, can cause more promotion to old, and can make evacuation pauses more expensive.

## 10. What Is Evacuation Failure / To-Space Exhausted Really?

**Evacuation failure** occurs when G1 tries to copy survivors/living objects out of the CSet but does not have enough **destination capacity** to copy them all. The log signature on many HotSpot 17 builds is **`to-space exhausted`**.

Points to distinguish:

- **A GC succeeding in terms of correctness** does not mean every object was copied as planned.
- G1 may have already moved **some objects** before discovering the lack of to-space.
- Remaining objects may be **kept in their old locations**, with forwarding/self-forwarding or appropriate internal mechanisms.
- G1 adjusts references and metadata so the Java application still accesses the right objects; it must never leave a reference pointing to improperly reclaimed memory.
- After the pause, the application **can continue normally** if it has enough capacity to operate, even though the event signaled memory pressure.
- If G1 cannot reclaim fast enough or to-space pressure persists, it may progress to a **Full GC**.

Oracle Java 17 describes evacuation failure as a path that attempts to complete the current collection by keeping already-copied objects in their new locations and **not copying** objects that could not be moved yet, while fixing references between them.

### Illustrative Timeline

```text
T0  Application continuously allocates; old/humongous occupancy is high
T1  Young/mixed GC starts; CSet is selected
T2  G1 scans roots, copies some live objects successfully
T3  Destination/to-space can no longer satisfy remaining copy volume
T4  Evacuation failure: uncopied objects are kept in place
    and reference/region metadata are fixed accordingly
T5  JVM returns to application if progress is still possible
T6  If pressure persists -> Full GC may be needed
```

Do not assume that a GC failure at T4 immediately crashes the JVM or must always open a Full GC in the very same pause. **Evacuation failure**, **Full GC**, and **OutOfMemoryError** are distinct events.

## 11. Why Does Evacuation Failure Happen When the Heap Is Not Reported as 100% Full?

Several causes can appear together:

1. **High live set/survival:** more bytes must be copied than the GC model predicted.
2. **High old occupancy:** many old regions already hold data, reducing free destination regions.
3. **Marking/reclamation too late:** concurrent marking has not finished to start mixed collections, so old garbage is not reclaimed fast enough.
4. **Humongous object pressure:** many old regions are held by humongous objects; tail waste makes usable region space lower than expected.
5. **Region fragmentation:** free runs sufficient for ordinary destination allocations may differ from the contiguous-region requirements of humongous allocations; both pressures reduce the allocator's options.
6. **Allocation spikes:** the application creates objects much faster than predicted.
7. **Promotion pressure:** many young survivors need space in old.
8. **Overly tight heap sizing:** the application live set is close to heap maximum, lacking buffer room for GC and concurrent work.
9. **Reserve/ergonomics mismatched to workload:** pause goal, adaptive IHOP, or free-region reserve do not reflect bursts.
10. **Container/native pressure:** OS/container resource limits can hinder heap expansion or runtime progress, though **this does not mean every OOMKilled is caused by G1 to-space**.

A `heap max - used` number on a dashboard is only total capacity. It does not immediately provide **free destination regions** or the collector's reclamation schedule.

## 12. How Does `G1ReservePercent` Help?

`-XX:G1ReservePercent=N` relates to the amount of heap G1 tries to reserve as a **false ceiling** to reduce the risk of allocation/promotion/to-space failure.

Example test command:

```bash
java -Xms512m -Xmx2g -XX:+UseG1GC \
  -XX:G1ReservePercent=15 -jar app.jar
```

This is not 15% of new physical RAM allocated outside `-Xmx`. The reserve is part of **heap management policy**, which can reduce the effective headroom the application is encouraged to use before GC reacts.

**Trade-offs:**

- Reserving more can reduce the risk of running out of destination space for some patterns.
- However, the portion of heap available for the application to accumulate objects under the policy becomes tighter sooner; this can cause GC to run more frequently if total heap stays the same.
- Changing the reserve can interact with **adaptive IHOP** and G1 heuristics.
- Do not pick a value just because you see one warning; measure old occupancy, survived bytes, to-space failure frequency, and throughput/p99 pauses.

If all **live data is already close to heap maximum**, adjusting the reserve does not create extra physical heap capacity. You must reduce retention/peak working set, adjust the workload, or consider heap/container sizing after proving a valid need.

## 13. What Is Full GC in G1?

When G1 can no longer make sufficient progress via young/mixed collections and concurrent marking/reclamation, it can fall back to **Full GC** as a last resort.

In Java 17 G1, Full GC can perform **in-place compaction across the entire heap** with a large stop-the-world pause compared to a normal collection. The goal is to reclaim truly dead objects and reorganize regions eligible for compaction to make room for continued allocation.

**Full GC is not "a faster GC that deletes a bit more."** It can:

- Traverse the liveness of far more data than a typical CSet.
- Spend time updating/moving/reorganizing objects and metadata.
- Block application threads longer, heavily impacting tail latency.
- Still **fail to reclaim** objects that are strongly reachable, even if business logic no longer needs them.
- Still **fail to guarantee** resolving a humongous contiguous-region allocation if the required regions cannot be created in that situation.

### Does Full GC Always Follow Evacuation Failure?

**No.** Java 17 G1 documentation states that G1 can continue running after an evacuation failure if enough memory remains and concurrent reclamation soon frees up space. Full GC usually appears when bad conditions persist or an allocation failure has no viable path forward.

### Full GC Is Not Always a Sign of a Memory Leak

Other causes include:

- Heap genuinely too small for the legitimate live set/peak concurrency.
- Humongous allocation needing contiguous regions that the current heap cannot provide.
- Concurrent marking not completing early enough.
- Application or diagnostic tools calling `System.gc()` depending on flags.
- Misconfigured GC/logging or heavy workload bursts preventing the collector from maintaining its reserve.

You need to read the **GC cause** and **timeline**. Only when a heap dump/path-to-GC-roots and post-GC live-set trend show that objects with no remaining value are still retained should you conclude a logical memory leak.

## 14. Three Different Events on the Timeline

| Event | Direct target | Main indicator | Guaranteed immediate Full GC? |
| --- | --- | --- | --- |
| **Humongous allocation** | An object of size ≥ half a region, needing contiguous old regions | `Humongous regions` increases; sometimes Concurrent Start | No |
| **Evacuation failure** | Copying CSet survivors/living objects lacks destination | `to-space exhausted`/evacuation failure logs | No |
| **Full GC** | Whole-heap collection/compaction per fallback policy or other cause | `Pause Full` / compaction pause; long pause | Is itself a Full GC |

A humongous burst can trigger early marking, hold many old regions, and reduce free headroom, causing G1 to hit to-space pressure. But this is only **one possible causal chain**, not an "A ⇒ B ⇒ C" law.

### Model Examples Not to Confuse

```text
Case A:
  Many humongous byte[] are created but discarded early.
  Eager reclaim/cleanup happens in time.
  => May have no evacuation failure or Full GC at all.

Case B:
  No significant humongous objects.
  Cache retains many live objects; survivor/promotion is high.
  => Can still run out of to-space and hit Full GC.

Case C:
  Humongous allocations need 5 contiguous regions,
  but longest free run is only 3 regions.
  => Can trigger GC/Full GC even though total free >= 5 regions.
```

## 15. Java 17: Computing Free-Region Runs with a Standalone Program

Create the file **`RegionRunDemo.java`**:

```java
public class RegionRunDemo {
    static int totalFree(boolean[] free) {
        int count = 0;
        for (boolean value : free) {
            if (value) {
                count++;
            }
        }
        return count;
    }

    static int longestRun(boolean[] free) {
        int current = 0;
        int best = 0;
        for (boolean value : free) {
            if (value) {
                current++;
                best = Math.max(best, current);
            } else {
                current = 0;
            }
        }
        return best;
    }

    public static void main(String[] args) {
        boolean[] free = {
                true, true, false, true,
                false, false, true, true, true, true,
                false, true, true
        };

        int needed = 5;
        System.out.println("totalFree=" + totalFree(free));
        System.out.println("longestRun=" + longestRun(free));
        System.out.println("needed=" + needed);
        System.out.println("contiguousEnough=" + (longestRun(free) >= needed));
    }
}
```

```bash
javac --release 17 RegionRunDemo.java
java RegionRunDemo
```

**Exact stdout:**

```text
totalFree=9
longestRun=4
needed=5
contiguousEnough=false
```

The program simulates **contiguous region availability** using a `boolean[]`; it does **not** read G1's free-region list at runtime. There are 9 free regions in total, but the longest free run is only 4, so a request for 5 contiguous regions cannot be placed in this model. The regions G1 actually uses have more complex policies and metadata than this check.

## 16. Java 17: Creating Humongous Pressure to Observe GC Logs

Create the file **`HumongousPressureDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class HumongousPressureDemo {
    private static final int CHUNK_BYTES = 768 * 1024;
    private static final int ROUNDS = 32;
    private static final int PER_ROUND = 8;
    private static final int RETAIN_LIMIT = 8;

    static volatile int checksum;

    public static void main(String[] args) {
        List<byte[]> retained = new ArrayList<>();

        for (int round = 0; round < ROUNDS; round++) {
            for (int i = 0; i < PER_ROUND; i++) {
                byte[] block = new byte[CHUNK_BYTES];
                block[0] = (byte) round;
                checksum += block[0];

                if (i < 2) {
                    retained.add(block);
                }
            }

            while (retained.size() > RETAIN_LIMIT) {
                retained.remove(0);
            }
        }

        System.out.println("arraysCreated=" + ROUNDS * PER_ROUND);
        System.out.println("nominalAllocatedMiB="
                + (long) ROUNDS * PER_ROUND * CHUNK_BYTES
                / (1024 * 1024));
        System.out.println("retainedArrays=" + retained.size());
        System.out.println("retainedNominalMiB="
                + (long) retained.size() * CHUNK_BYTES
                / (1024 * 1024));
        System.out.println("checksum=" + checksum);
    }
}
```

Compile:

```bash
javac --release 17 HumongousPressureDemo.java
```

Test run on **HotSpot Java 17** with a 1 MiB region size and a bounded heap sufficient for the example workload:

```bash
java -Xms64m -Xmx64m -XX:+UseG1GC \
  -XX:G1HeapRegionSize=1m \
  -Xlog:gc*,gc+heap=info \
  HumongousPressureDemo
```

**Stdout written by `System.out`, ignoring runtime-dependent GC logging lines:**

```text
arraysCreated=256
nominalAllocatedMiB=192
retainedArrays=8
retainedNominalMiB=6
checksum=3968
```

Explanation:

- `768 KiB` is the payload of each `byte[]`. With a 1 MiB G1 region, the array's object size is **greater than** the 512 KiB threshold, so it falls into the humongous category on the chosen configuration.
- The program creates **256 arrays**, totaling **192 MiB of cumulative nominal payload**, which does not mean the heap holds 192 MiB of arrays at the same time.
- Each round keeps 2 arrays; after exceeding 8, the oldest are removed. At the end, there are 8 arrays in `retained`, with a total payload of 6 MiB.
- `checksum` sums the first byte of each array per `round`, 8 times per round: `8 × (0 + 1 + ... + 31) = 3968`.
- Because the loop creates many humongous arrays on a 64 MiB heap, GC activity can be observed, but **the number of GC events, pauses, humongous region counts, and Full GCs do not have a fixed stdout**.
- The example **does not try to cause OOME or force an evacuation failure**. Intentionally pushing a process into Full GC in production is not a safe way to test.

### What to Look for in the Logs

Look for lines similar to:

```text
Humongous regions: X->Y
Pause Young (Concurrent Start) ...
Concurrent Mark Cycle
Pause Remark ...
Pause Cleanup ...
```

`X` and `Y` are **illustrative variables**, not measurements fabricated from a specific run. Event names/formats can vary depending on HotSpot build and logging level. If an expected event does not appear, do not jump to claiming "GC is not working"; check the JVM flags, actual region size, and whether the right version of the code was run.

## 17. A Humongous Object Must Be Large Enough Including the Array Header

A Java program can know the element count `byte[].length`, but **does not** have a standard API to directly get the exact HotSpot object size for every JVM. Tools like Java agents via `Instrumentation.getObjectSize` can provide a size estimate per API/implementation, but are unnecessary for basic testing.

Example:

```java
byte[] imageBytes = new byte[768 * 1024];
System.out.println(imageBytes.length);
```

This is a **Java snippet**, not a standalone file. `length` is exactly 786432, but actual heap object size has overhead/alignment. If the threshold is close to the payload, verify with runtime diagnostics instead of assuming `new byte[512 * 1024]` has an object size of exactly 512 KiB.

### Comparison with Object Arrays

An `Object[]` containing 100,000 references has a byte size depending on compressed oops/reference width, headers, and alignment. The array can be humongous even if **all the objects it references** are small; and a `byte[]` can be humongous even with no reference elements. Do not sum the sizes of all referenced objects and claim that the array object itself is humongous.

## 18. Does Full GC Solve Humongous Fragmentation?

It is necessary to distinguish **fragmentation of ordinary movable objects** from **contiguous-region pressure of humongous allocations**.

- In some situations, Full GC compacts movable objects and can reclaim regions from dead objects, creating more free regions.
- However, Java 17 G1 has limitations regarding humongous objects; Oracle 17 documentation emphasizes that they are not moved like ordinary evacuated objects and can still cause fragmentation.
- Therefore, **Full GC does not always guarantee** creating a contiguous sequence of regions long enough for a new humongous object.
- If a Full GC has already run and still cannot find the required region sequence, the JVM may report OOME/fail to complete the allocation.

This is why you should not say "the heap has N MiB free so it can definitely allocate a `byte[N]`." Free space may be split into chunks that the allocator cannot use to create a large object under G1's policy.

### Example of Two Heaps with the Same Free Bytes

```text
R = 1 MiB, needs 5 contiguous regions

Heap A:
  ..XX.....XXX.
      ^^^^^
  Has free run >= 5 => model has enough space.

Heap B:
  ..XX..XX..XX..
  Has similar total free bytes,
  but free runs are scattered => may not be enough.
```

The diagram only illustrates contiguity; it does not replace HotSpot's region allocator metadata.

## 19. Different Types of G1 Pressure Require Different Handling

| Symptom | Potentially related mechanism | How to verify |
| --- | --- | --- |
| `Humongous regions` rises sharply with large array allocations | Many humongous objects or live retention | GC heap logs, allocation profile, heap dump |
| `Humongous regions` drops after pauses/cleanup | Eager reclaim or marking reclaim freed objects | Before–after logs with GC IDs |
| Humongous allocations repeatedly trigger Concurrent Start | IHOP threshold hit multiple times or old occupancy rising | Concurrent marking timeline, log cause |
| `to-space exhausted` with few humongous objects | High survival/promotion, high old occupancy, insufficient reserve | Evacuation phases and survivor/old regions |
| `Pause Full (Allocation Failure)` | G1 not making enough progress via young/mixed/concurrent reclamation | Full GC cause, preceding events |
| Full GC yet old/live heap stays near max | Large retained graph | Heap dump, retained size, GC roots |
| Full GC leaves many free regions yet humongous allocation fails | Cannot find a suitable contiguous run | Humongous sizes, region fragmentation, and logs |
| Container OOMKilled while heap used is still low | Process/native/cgroup pressure outside heap | Cgroup events, RSS, native memory |
| Long GC pauses without Full GC | Heavy evacuation/reference-processing work or CPU contention | G1 phase logs, JFR, machine CPU |

**Do not lump "GC pressure" into a single cause.** Effective action depends on where the bottleneck is: allocation volume, live data, contiguous old regions, to-space reserve, or total process/container memory.

## 20. GC Logging and Diagnostic Commands on Java 17

When a real Java server runs long enough, enable GC logging deliberately:

```bash
java -Xms512m -Xmx2g -XX:+UseG1GC \
  -Xlog:gc*,gc+heap=info,gc+phases=debug \
  -jar app.jar
```

To write logs to rotating files, use an `-Xlog` configuration appropriate for your build; avoid letting GC logs grow unbounded and fill the disk. Keep sufficient duration/timestamps to correlate events with throughput, latency, and OOME.

Commonly used JDK diagnostic commands:

```bash
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
jcmd <PID> Thread.print
jstat -gc <PID> 1000 5
```

`<PID>` is a placeholder for the process ID of a live JVM, not a literal runnable PID. `app.jar` is a placeholder for the application JAR name. `jstat` returns GC counters/heap utilization whose meaning can vary by collector, not directly the longest contiguous free region run.

### What Specifically Should Be Recorded?

- Java version/vendor/build, command-line flags, container limit.
- Actual G1 region size (logged at JVM startup).
- Heap used/committed/max and old/young region occupancy by GC ID.
- `Humongous regions: X->Y` before–after pauses.
- G1 concurrent marking Start/Remark/Cleanup.
- Evacuation failure / to-space exhausted events.
- Full GC cause, duration, before–after occupancy.
- Allocation rate by endpoints/batches; sizes of large arrays/objects.
- Post-GC live set/retention via heap dump when suspected.
- RSS/cgroup memory if the process is OOMKilled or `-Xmx` has not been reached.

### How Does a Heap Dump Differ from a GC Log?

- **GC log:** collector/collection phases, region occupancy, pauses, and failure events.
- **Heap dump:** object graph, shallow/retained size, and paths to GC roots to see who is holding large arrays.
- **Allocation profiler/JFR:** methods/stack traces allocating large volumes of objects; watch out for sampling/overhead and metrics semantics.

You cannot replace all three with a single `used heap` number.

## 21. A Workflow for Diagnosing Full GC on G1

**Step 1 — Confirm whether it is truly a Full GC.** Look for `Pause Full` logs and the cause; do not treat every `Pause Young` as a Full GC.

**Step 2 — Inspect the preceding 1–5 minutes of events.** Are there rising `Humongous regions`, `to-space exhausted`, high old occupancy, or repeated Concurrent Starts? Did `System.gc()` or a diagnostic tool force a GC?

**Step 3 — Distinguish the two pressure paths.**

- **Humongous path:** many large allocations, needing contiguous old regions, unused tails, and fragmentation.
- **Evacuation path:** many survivors/live bytes in the CSet, insufficient destination/to-space, slow marking/mixed reclamation.

They can occur simultaneously and amplify each other.

**Step 4 — Measure allocation sizes.** If many byte arrays are just over the half-region threshold, consider breaking an allocation into smaller chunks, switching to a streaming architecture, or evaluating region sizing. Do not apply this if the data model genuinely requires a contiguous array.

**Step 5 — Measure live set and root paths.** If large arrays live long due to cache/request retention, GC flags cannot reclaim them. Use heap dumps and lifecycle analysis to fix the owner.

**Step 6 — Check the marking cycle.** Does marking start early enough for mixed collections to reclaim old regions? Does adaptive IHOP predict well under burst patterns?

**Step 7 — Check heap/GC reserve.** Are free regions sufficient for evacuation/promotions? It may be necessary to increase `-Xmx`, change reserve policy, or reduce peak concurrent workload — while considering cgroup/native budgets.

**Step 8 — Test one measured change at a time.** One change at a time, run the same workload, and compare before–after humongous region count, Full GC frequency, p99 pause, throughput, RSS, and GC CPU.

**Step 9 — Verify against regression.** After the fix, the large object count stabilizes, `to-space exhausted` no longer occurs under the load conditions that caused the error, and Full GC does not appear outside explained situations.

**Step 10 — State clearly what remains uncertain.** Only conclude "the memory leak is fixed" when evidence from retained graphs/lifecycles and sufficiently long monitoring supports it, not just because a single load test did not OOME.

## 22. Prioritize Fixing the Application Before Tuning GC Flags

### Reduce Large Heap Allocations

- **Streaming** instead of reading an entire file/request into a single `byte[]` when semantics allow.
- Split batches into reasonable chunks, without creating too many tiny objects that cause unnecessary overhead.
- Use `InputStream`/`OutputStream` APIs for incremental processing when possible.
- Avoid unnecessary `toByteArray()`/copies on hot paths if payloads are very large.
- Avoid allocating an `Object[]` with capacity far exceeding the entries actually used.
- Consider backpressure/concurrency limits for batches that hold multiple buffers simultaneously.
- If a large array is strictly required, consider peak working set and memory budget instead of forcing a split.

### Reduce Retention Time of Large Arrays

- Evict entries from caches according to proper TTL/eviction policies.
- Cancel subscriptions/listeners holding object graphs that contain large arrays.
- Clear `ThreadLocal` values when a task/request finishes.
- Stop holding batch buffers in static fields/queues after a job completes.
- Close unused resources; remember that removing a Java heap reference does not automatically guarantee native resource closure.

### Consider Off-Heap in the Right Cases

Direct buffers or memory-mapped files can reduce some **Java heap humongous allocations**, but:

- They still consume native/process/cgroup memory.
- Wrappers/cleaners/lifecycles must be managed properly to avoid native leaks.
- They are not free and do not automatically improve throughput in every workload.
- A system getting container OOMKilled due to total memory cannot be solved just by "moving off-heap" without a new budget.

## 23. When to Consider `G1HeapRegionSize`, `G1ReservePercent`, and IHOP?

| Situation with evidence | Direction to test | Trade-off/caution |
| --- | --- | --- |
| Many objects around half-region threshold | Try a larger region size on the same heap/JDK | G1 granularity, pause predictability, tail waste |
| Evacuation failure and lack of destination headroom | Evaluate reserve, total heap, and live set | Reserve reduces effective allocation capacity |
| Old occupancy rises quickly, marking falls behind | Evaluate adaptive IHOP, marking start timing, concurrent threads | Concurrent GC uses CPU; starting too early also costs |
| Full GC due to large retained objects | Reduce retention/caches, improve lifecycle | GC tuning does not solve strong reachability |
| Bursts create too many humongous arrays | Streaming, chunking, bounded concurrency | Code complexity and different memory copies |
| Full GC after allocation failure even though heap max not reached | Read fragmentation/region topology, GC cause | Do not equate total free with contiguous space |

**Avoid "fixing with a single flag" without knowing the constraints.** For example, increasing `G1HeapRegionSize` may turn previously humongous arrays into non-humongous ones, but larger arrays or other heap demands can still cause fragmentation/evacuation pressure.

### Reasonable Tuning Order

1. Verify GC mode/version and correctness of observability.
2. Optimize allocation sizes/retention if there is a clear bug.
3. Check peak memory/concurrency/budget.
4. Test heap sizing/reserve/region size when backed by evidence.
5. Re-measure latency/CPU/throughput/memory; roll back if trade-offs are worse.

## 24. Sixteen Common Reasoning Mistakes

| Misconception | Reality |
| --- | --- |
| "Humongous means object > 1 GiB" | In G1, the threshold relates to **half a region**, usually much lower than 1 GiB |
| "Humongous is any object stored in the old generation" | Humongous is a size-based classification; old also holds regular objects |
| "A humongous object uses its exact byte size" | Uses an integer number of **contiguous regions**; the last region has an unused tail |
| "Enough total free regions means any large object can be allocated" | Needs a suitable **contiguous run** |
| "Humongous objects always start in Eden before moving to old" | G1 allocates them directly into old humongous regions |
| "Humongous objects always require Full GC to be reclaimed" | There are marking cleanup and eager reclaim under appropriate conditions |
| "Every primitive array is eagerly reclaimed as soon as scope ends" | Reachability/GC phase decides; there is no such deadline |
| "G1 young GC always moves humongous objects" | Humongous objects are handled specially, not via normal CSet evacuation |
| "Evacuation failure means GC corrupts Java references" | G1 fallback must still preserve reference correctness |
| "To-space exhausted means heap used is 100%" | Lack of **destination capacity**, which can happen before metrics report max |
| "Evacuation failure always triggers an immediate Full GC" | The JVM may continue and reclaim in a subsequent cycle |
| "Full GC means every object was moved and no fragmentation remains" | Not guaranteed, especially with humongous region constraints |
| "Full GC is synonymous with a memory leak" | Can be due to legitimate live set, allocation burst, fragmentation, or external GC request |
| "`G1ReservePercent` allocates extra memory outside `-Xmx`" | It is a reserve policy within the heap, not increasing total heap capacity |
| "Increasing region size is always optimal" | Has trade-offs and depends on size distributions |
| "Increasing `-Xmx` always fixes the error" | Does not fix unbounded retention and must account for container/native memory |

## 25. Self-Check Questions

**Question 1:** With a 1 MiB G1 region size, is an object with a **total size** of 600 KiB humongous?

**Yes.** The threshold is 512 KiB, and a 600 KiB object uses one humongous region (with an unused tail).

**Question 2:** An object with total size 1.25 MiB in a 1 MiB region needs how many regions, and how much tail waste?

**Two regions**; the modeled unused tail is 0.75 MiB.

**Question 3:** A heap has 20 free regions, but the longest free run is 3. Can it immediately allocate a humongous object needing 5 contiguous regions?

**No** in that simulated layout; total free cannot substitute for a contiguous run.

**Question 4:** Why can many short-lived `byte[]` arrays still cause old occupancy pressure in G1?

They can be allocated directly into old humongous regions. Reclamation is not necessarily synchronized with when the application drops references.

**Question 5:** Is evacuation failure a failure of all Java objects or a failure to copy according to the collection plan?

It is **insufficient to-space to copy all objects planned for evacuation**; the JVM must still preserve Java object correctness.

**Question 6:** After an evacuation failure, is a Full GC guaranteed to happen immediately?

**No.** G1 can let the mutator continue and hope concurrent reclamation finishes in time.

**Question 7:** Why might Full GC still fail to resolve a humongous allocation?

Because fragmentation and contiguous old-region/humongous-movement constraints may still persist, or live data cannot be reclaimed.

**Question 8:** Can `-XX:G1HeapRegionSize=2m` help arrays around 768 KiB avoid being humongous?

**Possibly**, because the threshold rises to about 1 MiB, provided the actual array size does not exceed the threshold and the flag is accepted by the JVM.

**Question 9:** Does `G1ReservePercent=15` increase `-Xmx` by 15%?

**No.** It adjusts the reserve policy within the heap.

**Question 10:** To prove a memory leak in an application with many humongous arrays, is looking at `Humongous regions: X->Y` alone enough?

**Not yet.** You need an allocation profile, heap dump, retained owners, and liveness/lifecycle evidence.

## 26. Java 17 References

- [Oracle Java SE 17 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html): regions, humongous allocations, eager reclaim, marking, and behavior when space is exhausted.
- [Oracle Java SE 17 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-garbage-collector-tuning.html): analysis of Full GC, `to-space exhausted`, humongous fragmentation, and G1 flags.
- [Oracle Java SE 17 — Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/17/gctuning/index.html): collectors and GC goals.
- [Oracle Java SE 17 — `java` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xmx`, `-Xms`, `-Xlog`, and flags supported by the runtime.
- [Oracle Java SE 17 — `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `VM.flags` and `GC.heap_info`.
- [Oracle Java SE 17 — `jstat`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): GC/memory counters by collector.
- [Oracle Java SE 17 — `MemoryUsage`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html): distinguishing used, committed, and max.
- [JVMS Java SE 17 — Heap (2.5.3)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3): automatically managed GC heap semantics.
- [Java SE 17 — `Reference` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html): reference reachability and reclamation process.
- [OpenJDK — G1 GC overview](https://wiki.openjdk.org/display/HotSpot/Garbage+First+Garbage+Collector): G1 design and background documentation; verify version before relying on internal details.

**Takeaway:** G1 treats objects with **size from half a region** as humongous, allocating them via **a contiguous sequence of old regions**, which can produce **unused tails and contiguous-region fragmentation**. During young/mixed pauses, G1 needs **to-space** to copy live objects; lacking destination space can cause **evacuation failure**, though the VM must still preserve references and may continue. If old/humongous pressure persists, G1 can escalate to **Full GC**, which is expensive and not guaranteed to resolve a lack of contiguous regions. Proper investigation requires inspecting **allocation sizes, live set, GC logs, regions, marking timeline, headroom, and retained references**, rather than reading only a single heap-used number.
