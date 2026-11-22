# Garbage Collector, Used Memory, and Image Size

In Java Advance CRaC, three metrics often placed side by side are used heap, process memory footprint, and checkpoint image size. They are related to one another, but they do not measure the same thing.

- **Heap used** indicates how much memory the JVM currently records for Java objects.
- **Process memory** reflects the memory pages that the process holds or that are resident in RAM, including areas outside the heap.
- **CRaC image size** reflects the data that must be stored to restore the process state at checkpoint, according to the format of the runtime and checkpoint tool in use.

The Garbage Collector (GC) can change used heap and sometimes reduce the data that must be stored in the checkpoint image. However, you cannot take a post-GC heap number to directly infer the image size. To optimize CRaC, it is necessary to understand each metric and measure them in the same scenario.

## 1. Distinguishing Heap, Process Memory, and Checkpoint Image

A Java application does not only use the heap. Beyond the heap, there are Metaspace, compiled machine code memory, thread stacks, direct buffers, native libraries, file-mapped regions, and many internal JVM structures.

| Metric | What does it describe? | Commonly used tools or APIs |
|---|---|---|
| Heap used | Amount of heap the JVM currently records as used | `MemoryMXBean`, `Runtime` |
| Heap committed | Amount of heap the JVM has committed and can use | `MemoryMXBean` |
| Heap max | Maximum heap limit that the JVM can use | `MemoryMXBean`, `Runtime.maxMemory()` |
| Non-heap | Memory managed by the JVM outside the heap, such as Metaspace and Code Cache | `MemoryMXBean.getNonHeapMemoryUsage()` |
| Native memory | Off-heap memory managed by the JVM, native libraries, or the application | Native Memory Tracking, operating system tools |
| RSS | Memory pages of the process currently resident in RAM | Operating system tools |
| Container memory | Memory usage recorded by the container resource controller | Cgroup or container tools |
| Checkpoint image size | Size of the image files generated to restore the process | Operating system tools on the checkpoint directory |

These metrics answer different questions. For example, heap used can drop sharply after GC while heap committed remains nearly unchanged. RSS may also decrease less than heap used because the process still holds stacks, Metaspace, direct buffers, and other native pages. The checkpoint image, in turn, depends on the set of state data that the checkpoint mechanism must store.

### Heap used, committed, and max

The JVM manages the heap within a memory address region. The three key figures have the following meanings:

- **used**: the amount of heap currently in use from the JVM's perspective. This figure can include objects no longer referenced by the application that GC has not yet reclaimed.
- **committed**: the amount of heap the JVM has committed so it can allocate objects. The difference between committed and used is the free space currently available within the committed heap region.
- **max**: the maximum heap limit. The value may be undefined on some environments or JVMs, in which case the API returns a negative value.

For example, if the heap has used = 400 MiB, committed = 768 MiB, and max = 2 GiB, that means the JVM records 400 MiB of heap in use, has 768 MiB of committed heap, and has a growth limit up to 2 GiB. It does not mean the process only occupies 400 MiB of RAM.

`Runtime.freeMemory()` is not the machine's free RAM either. It represents the free space inside the committed heap at the time of the call. To read heap metrics consistently, you can use `MemoryMXBean`.

## 2. How Does the Garbage Collector Work?

Java allocates most ordinary objects on the heap. When an application creates an object, the JVM reserves memory for that object. During execution, some objects continue to be used; others become garbage when there is no longer a valid reference path from the live state of the program.

GC identifies objects that are still reachable by starting from **GC roots**, such as:

- References from the stacks of running threads.
- References in static fields held by live class loaders.
- JNI references and certain internal references managed by the JVM.

From these roots, the JVM traverses the reference graph. An object reachable from a root is considered reachable. An object that cannot be reached from any root can be reclaimed. A group of objects referencing each other in a cycle can still be reclaimed if the entire group no longer has a path from GC roots. Therefore, GC does not rely simply on reference counting.

### Generations and Collection Cycles

Many collectors take advantage of the observation that most objects exist only for a short time. The heap is therefore often organized or processed in regions with corresponding roles:

- **Young generation**: where many new objects are allocated. Collection of this region typically occurs more frequently.
- **Old generation**: where long-lived objects are retained after multiple collection cycles or allocated according to the collector's strategy.

Region names, organization, and collection schedules depend on the selected GC. G1, Parallel GC, ZGC, and other collectors have different strategies regarding memory regions, concurrency level, pause times, and memory compaction capability. You should not assume all JVMs operate the same way.

GC may perform one or more tasks:

1. Identify live objects and objects that are no longer reachable.
2. Reclaim the memory of objects that are no longer alive.
3. Move or compact objects to reduce fragmentation, if the collector uses that mechanism.
4. Adjust the committed heap amount or return some memory regions to the operating system when the strategy and runtime conditions allow.

Reclaiming objects does not mean the JVM must immediately return the entire corresponding heap region to the operating system. The JVM may retain committed regions to serve subsequent allocations, avoiding repeated memory requests.

### Unused Objects and GC-Reclaimed Objects

These two states must be distinguished:

- An object that is no longer needed from a business perspective but is still held by an existing reference remains reachable. GC cannot infer on its own that the application does not need it.
- An object that is already unreachable but has not yet gone through an appropriate GC cycle can still occupy space in heap used.

For example, a cache holding references to millions of old records keeps those records reachable. Invoking GC does not solve the issue of the cache retaining data for too long. You need to set size limits, time-to-live, or evict entries that are no longer needed.

GC also does not replace closing resources outside the heap. Files, sockets, database connections, and native resources must be managed with explicit lifecycle mechanisms such as try-with-resources or CRaC callbacks. You should not wait for GC to run to close these resources.

### Why Does GC Affect Checkpoint?

Checkpoint saves the process state at a point in time. If the heap still contains many uncollected garbage objects, the memory pages containing them may still belong to the state that the checkpoint mechanism has to inspect and save. A GC cycle before checkpoint can:

- Reduce heap used by reclaiming objects that are no longer reachable.
- Change the contents of heap pages.
- Under certain conditions, help the collector compact the heap or return some committed memory regions.
- Reduce the amount of memory data that needs to be saved in the checkpoint image.

The effect depends on the collector, how the heap is committed, how pages are tracked, and how the checkpoint tool creates the image. If most of the heap contains live objects, GC cannot reclaim them. If memory growth comes mainly from native allocations or direct buffers still being held, GC on the Java heap will not immediately free that portion on its own either.

`System.gc()` is only a request for the JVM to consider running GC. The JVM may ignore or handle the request according to its configuration and strategy. This call should not be treated as a guarantee that all garbage has been reclaimed or that the checkpoint image will definitely be smaller.

## 3. Reading Memory Metrics in Java

You can use the Java Management API to read heap and cumulative GC statistics. The following code snippet does not require a specific collector:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.util.Locale;

public final class MemoryReport {

    private static final long MIB = 1024L * 1024L;

    private MemoryReport() {
    }

    public static void print(String phase) {
        MemoryMXBean memoryBean = ManagementFactory.getMemoryMXBean();
        MemoryUsage heap = memoryBean.getHeapMemoryUsage();
        MemoryUsage nonHeap = memoryBean.getNonHeapMemoryUsage();

        System.out.printf(
                Locale.ROOT,
                "[%s] heap: used=%s, committed=%s, max=%s%n",
                phase,
                mib(heap.getUsed()),
                mib(heap.getCommitted()),
                mib(heap.getMax())
        );

        System.out.printf(
                Locale.ROOT,
                "[%s] non-heap: used=%s, committed=%s, max=%s%n",
                phase,
                mib(nonHeap.getUsed()),
                mib(nonHeap.getCommitted()),
                mib(nonHeap.getMax())
        );

        for (GarbageCollectorMXBean gc
                : ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.printf(
                    Locale.ROOT,
                    "[%s] GC %s: collections=%d, time=%s%n",
                    phase,
                    gc.getName(),
                    gc.getCollectionCount(),
                    millis(gc.getCollectionTime())
            );
        }
    }

    private static String mib(long bytes) {
        if (bytes < 0) {
            return "unknown";
        }
        return String.format(Locale.ROOT, "%.1f MiB", bytes / (double) MIB);
    }

    private static String millis(long value) {
        return value < 0 ? "unknown" : value + " ms";
    }
}
```

The GC counters are cumulative values since JVM startup. `getCollectionCount()` indicates the number of collections recorded by the MXBean; `getCollectionTime()` is the cumulative time in milliseconds. Some collectors or JVMs may not provide full metrics, in which case the API returns a negative value. You should not compare two measurements if runtime duration, load, or GC configuration differ without accounting for those differences.

You can call `MemoryReport.print("warm")` after the application has started and loaded the necessary data, and then call it again before checkpoint. The output helps show how the heap and GC counters change. It does not yet tell you the RSS or the checkpoint image size.

### Reading Sample Output

Suppose a measurement records:

```text
[before-gc] heap: used=920.0 MiB, committed=1024.0 MiB, max=2048.0 MiB
[after-gc]  heap: used=310.0 MiB, committed=1024.0 MiB, max=2048.0 MiB
```

You can conclude that heap used decreased by about 610 MiB after the observed GC cycle. However, committed is still 1024 MiB. The JVM still retains the committed heap region at that level, so you cannot conclude that the process returned 610 MiB of RAM to the operating system. Nor can you conclude that the checkpoint image decreased by exactly 610 MiB.

If heap used does not decrease after GC, check whether data is still being held by caches, static fields, thread locals, queues, or live references. If heap used is small but RSS remains high, check native memory, thread stacks, direct buffers, Metaspace, Code Cache, and mapped regions.

## 4. What Does a CRaC Checkpoint Image Contain?

CRaC allows checkpointing the state of a JVM process so that the process can be restored later. The checkpoint image is the data generated by the runtime and checkpoint mechanism to reconstruct the process state. On Linux environments commonly used with CRaC, this process relies on the checkpoint/restore capabilities of the operating system and the corresponding tool.

Conceptually, the state that needs to be restored can include:

- Process memory pages, including pages containing the Java heap.
- Thread state and execution information needed to resume the process.
- Memory mappings and resource states that the checkpoint tool supports saving.
- Auxiliary data and metadata according to the format of the checkpoint tool.

Exact details depend on the CRaC JDK, runtime version, operating system, checkpoint tool, configuration, and how the image is stored. You should not assume the image is always a single file or that every memory region is stored in the same way.

### Image Size Is Not Equal to Heap Used

Image size can be influenced by many factors:

1. **Heap pages with data to restore**: the number and contents of memory pages recorded by the checkpoint.
2. **Heap committed and how the JVM manages pages**: committed heap may hold pages that the application no longer directly uses.
3. **Off-heap memory**: thread stacks, Metaspace, Code Cache, direct buffers, JNI, and native libraries.
4. **Number of threads and runtime structures**: each thread has its own state and stack region.
5. **Resources and memory mappings**: mapped files, libraries, sockets, and other resources depending on what the environment supports.
6. **Storage format**: an image may consist of multiple files; how pages are written, compression, sparse files, or page sharing affect the number of bytes shown on disk.

Therefore, the following three situations can occur:

- Heap used drops sharply, but the image shrinks little, because committed heap or native regions still need to be saved.
- Heap used stays nearly constant, but the image changes because threads, native allocations, or other memory regions change.
- The image size on disk differs significantly from the process memory resident in RAM, due to storage format, compression, or sparse files.

When measuring the image directory on Linux, `du -sh` typically reflects the block space allocated on disk; `ls -lh` reflects the logical size of the files. The two numbers can differ if there are sparse files. Clearly state whether you are comparing logical size or actual disk usage.

### Distinguishing CRaC Checkpoint Image and Docker Image

In container environments, the word "image" can also mean **OCI/Docker image**. These two types of images are different:

| Image type | Main contents | Commonly influencing factors |
|---|---|---|
| OCI/Docker image | Filesystem layers used to create a container | JRE/JDK, libraries, application, resources, and build layers |
| CRaC checkpoint image | State of a running process to be restored | Heap and native memory, threads, mappings, process state, and checkpoint format |

Reducing JAR size or Docker layers can reduce the OCI image size, but does not automatically make the checkpoint image correspondingly smaller. Conversely, reducing live data in the process can affect the checkpoint image without changing the Docker image layers.

## 5. How Much Can GC Reduce CRaC Image Size?

GC can help reduce image size when the heap contains many garbage objects and the pages containing them no longer need to be preserved intact in the image. However, the reduction does not have a fixed ratio to the number of bytes reclaimed.

Consider three cases:

**Case A — many temporary objects at the end of their lifecycle.** The application has just loaded and processed a large amount of temporary data. After processing, references have been cleared. If GC reclaims most of that data before checkpoint, heap used can drop significantly. Memory pages that are no longer needed can make the image smaller, depending on how the JVM and checkpoint tool manage pages.

**Case B — a large cache still in use.** The cache holds references to data to serve requests after restore. Those objects remain reachable, so GC must keep them. If you want to reduce the image, you need to review the cache policy: size limits, time-to-live, reloadable data, and the cost of warming up the cache after restore.

**Case C — memory growth outside the heap.** The application holds many direct buffers or allocates native memory via JNI. GC on the Java heap does not mean this memory is freed immediately. You need to manage the lifecycle of buffers and native resources according to their respective APIs, then re-measure RSS and the checkpoint image.

A full GC before checkpoint is sometimes useful in a controlled experiment, but it should not be run by default on every checkpoint. A full GC can cause long pauses, increase latency, diminish the fast-startup benefit, and still not guarantee a smaller image. Keep this step only if metrics on the target environment demonstrate an overall benefit.

### Should You Call System.gc() in beforeCheckpoint?

There is no single right answer for every application. `beforeCheckpoint` is the appropriate time to prepare application state and resources according to the CRaC contract. You can experiment with requesting GC at this stage, but you should evaluate at least:

- Whether GC actually runs, as shown by GC counters and heap used.
- Additional pause time before checkpoint.
- Image size before and after the change.
- Restore time and memory after restore.
- Impact on latency and throughput once the application resumes running.

If `System.gc()` is disabled by JVM configuration or the JVM ignores the request, the call will not produce the expected effect. Do not use a `System.gc()` call as proof that the heap has been cleaned.

## 6. Measuring Memory in the CRaC Lifecycle

A useful measurement approach is to record metrics at meaningful milestones:

1. After the JVM starts and completes the required warm-up.
2. After loading the data or cache that the application expects to keep in the image.
3. Immediately before checkpoint.
4. After restore and completion of resource restoration callbacks.

CRaC provides `Resource` for applications to prepare before checkpoint and recover after restore. The following example registers a resource to print heap metrics in both callbacks. It only observes metrics; it does not call GC itself and does not change the cache policy.

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CheckpointMemoryMetrics implements Resource {

    public CheckpointMemoryMetrics() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context) {
        MemoryReport.print("beforeCheckpoint");
    }

    @Override
    public void afterRestore(Context<? extends Resource> context) {
        MemoryReport.print("afterRestore");
    }
}
```

Instantiate the resource once during application startup so that it is registered with the global context. Ensure this class is compiled against the CRaC JDK/API matching the running runtime. Real-world applications typically have other resources to close or prepare connections, threads, and external resources before checkpoint, and then reopen or verify them after restore.

Metrics printed from the callbacks help observe the heap at two milestones. To evaluate image size, you must separately measure the checkpoint directory after the checkpoint operation finishes. To evaluate process memory, you must retrieve RSS or container metrics from the operating system. Do not substitute `MemoryMXBean` for these measurements.

### Additional Measurement Tools

Depending on the runtime environment, you can combine:

- **JMX / `MemoryMXBean`**: heap used, committed, max, and non-heap.
- **`GarbageCollectorMXBean`**: cumulative GC count and time.
- **`jcmd <pid> GC.heap_info`**: heap information of the running JVM, if supported by the command and JVM.
- **`jcmd <pid> VM.native_memory summary`**: native memory breakdown when the JVM is started with appropriate Native Memory Tracking, for example `-XX:NativeMemoryTracking=summary`.
- **Operating system tools**: RSS, thread count, memory mappings, and container memory.
- **`du` / `ls` on the checkpoint directory**: size of the image stored on disk.

Native Memory Tracking has overhead and does not cover every allocation from native libraries outside the JVM. RSS also does not tell you exactly which portion is heap. Use multiple measurement perspectives to explain why changes occur instead of looking for a single metric.

## 7. Experimental Procedure to Evaluate the Impact of GC

To find out whether GC helps make the CRaC image smaller in a specific application, design a repeatable comparison.

### Preparing Two Runs

- **Run 1 — baseline**: run the application with the same configuration and data, bring the application to a checkpoint-ready state, and then create the image.
- **Run 2 — with GC requested**: repeat the same process, but request GC at a defined point before checkpoint. Record whether GC actually occurred.

Keep the factors that can affect results identical: CRaC JDK version, collector, `-Xms`, `-Xmx`, input data, cache, thread count, load, warm-up time, and how the image is created. Use a fresh process for each run to avoid leftover state from the previous run.

### Recording the Metrics

| Stage | Heap used | Heap committed | GC count/time | RSS | Image size |
|---|---:|---:|---:|---:|---:|
| After warm-up | Record measurement | Record measurement | Record measurement | Record measurement | Not available yet |
| Before checkpoint | Record measurement | Record measurement | Record measurement | Record measurement | Not available yet |
| After image creation | Not applicable if process was checkpointed | Not applicable | Save pre-checkpoint log | Record using an appropriate method | Record image size |
| After restore | Record measurement | Record measurement | Record measurement | Record measurement | Use created image |

Do not record only the final number. If heap used decreases but RSS does not decrease, that indicates the reclaimed memory has not correspondingly reduced the process's RAM pages. If RSS decreases but image size stays unchanged, other pages or metadata may dominate the image size. You need to further inspect the image structure and storage characteristics.

### Evaluating Results

A change is only useful when it improves a real goal without creating a larger cost elsewhere. Look simultaneously at:

- How many bytes and what percentage the checkpoint image decreases.
- How much checkpoint preparation time increases.
- Whether restore time changes.
- Whether RSS and container memory after restore fit deployment limits.
- Whether the application still has the necessary data, connections, and correct behavior after restore.
- Whether first-request latency and cache warm-up time after restore increase.

Repeat measurements multiple times and compare under identical conditions. GC and the operating system can introduce variance between runs. A single measurement is not enough to conclude that a GC option makes the image smaller.

## 8. Ways to Reduce Memory and Checkpoint Image

Measures should start with data and application lifecycle:

1. **Limit caches**: set maximum size, TTL, or eviction policies. Keep only data that has value after restore.
2. **Remove unnecessary references**: remove entries from collections, queues, listeners, or ThreadLocals when work finishes.
3. **Avoid keeping temporary data for too long**: process in moderate batches, release references upon completion, and avoid storing all intermediate results if unnecessary.
4. **Manage direct buffers and native resources**: use APIs with explicit lifecycles; close resources on time instead of waiting for GC.
5. **Manage threads**: avoid creating unnecessary threads and configure pools appropriately. Many threads can increase stack memory and state that must be checkpointed.
6. **Prepare resources according to CRaC**: close or pause resources that cannot be kept across checkpoint; reopen or verify them in `afterRestore`.
7. **Choose heap configuration based on metrics**: tune `-Xms`, `-Xmx`, and the collector according to actual load. An overly large heap can increase memory pressure; an overly small heap can increase GC frequency and reduce throughput.

Reducing `-Xmx` only changes the heap limit and does not guarantee a smaller checkpoint image. Reducing `-Xms` may change initial committed heap, but the actual impact depends on how the JVM expands the heap and application load. Measure changes on the target CRaC runtime.

Some applications need to keep caches to achieve low latency right after restore. Clearing the entire cache may make the image smaller, but forces the first request to reload or recompute data. Balance image size, restore time, warm-up time, and post-restore experience.

## 9. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| If heap used drops by 500 MiB, the image definitely shrinks by 500 MiB. | Heap used and the image measure different scopes; the reduction depends on memory pages and checkpoint format. |
| Heap committed equals RSS. | Committed is a JVM heap metric; RSS is the process memory pages currently resident in RAM. |
| Calling `System.gc()` guarantees all garbage is collected. | It is a GC request; the JVM may ignore it or handle it according to configuration. |
| GC frees sockets, files, and all native memory. | GC manages Java objects; off-heap resources require their own lifecycle management. |
| Low heap used means the process is lightweight. | Native memory, thread stacks, Metaspace, direct buffers, and mappings can still be large. |
| A small Docker image means a small CRaC checkpoint image. | OCI images and checkpoint images contain different types of data. |
| Clearing caches is always optimal. | Caches may make the image larger, but they reduce post-restore latency; both goals must be measured. |

## 10. Checklist Before Concluding

- [ ] Identified whether "image" refers to an OCI/Docker image or a CRaC checkpoint image.
- [ ] Recorded heap used, committed, max, and non-heap at the same measurement milestones.
- [ ] Recorded GC count/time and confirmed GC actually occurred during testing.
- [ ] Measured RSS or container memory using operating system tools.
- [ ] Measured checkpoint directory size and clearly noted whether logical size or disk usage was used.
- [ ] Kept the JDK, GC, heap flags, data, and warm-up procedure unchanged across comparison runs.
- [ ] Checked checkpoint time, restore time, and application behavior after restore.
- [ ] Kept the proactive GC step only if metrics show the benefit justifies the pause cost.

The core takeaway when operating CRaC is that GC manages object reclamation on the Java heap, whereas checkpoint must save state broader than the heap. GC can reduce live data and contribute to a smaller image, but the outcome can only be confirmed by separately measuring the heap, process memory, and checkpoint image in the same scenario.
