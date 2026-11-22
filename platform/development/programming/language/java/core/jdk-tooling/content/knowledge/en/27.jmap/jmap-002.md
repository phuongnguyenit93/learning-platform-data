# JVM Heap Summary with jmap and jcmd

## 1. What is a heap summary?

A **heap summary** is a snapshot of the Java Heap memory state at a specific point in time. It shows how the heap is organized, which garbage collector (GC) is in use, how much heap space is currently used, and how much memory has been committed or reserved by the JVM.

A heap summary typically helps answer:

- Which garbage collector is the JVM using?
- How much heap space is currently used?
- How much memory has the JVM committed for the heap?
- How far can the heap expand?
- For generational or region-based collectors, what is the current state of Eden, Survivor, Old, or G1 regions?
- How much memory are Metaspace and Compressed Class Space using?

A heap summary is a point-in-time snapshot taken at the moment of the query. It helps quickly assess memory pressure, but a single result is not enough to conclude that an application has a memory leak.

## 2. jmap -heap and changes across JDK versions

In older documentation and JDK releases, you may encounter the command:

~~~bash
jmap -heap <pid>
~~~

This command was previously used to print GC information, heap configuration, and the usage of each generation/space. However, supported options vary across JDK releases and platforms.

On JDK 24.0.2 tested in the current environment:

- `jmap -h` does not list the `-heap` option.
- Running `jmap -heap <pid>` exits with exit code 1 and the message: `Cannot connect to core dump or remote debug server. Use jhsdb jmap instead.`
- For a running JVM, the recommended command to obtain a heap summary is `jcmd <pid> GC.heap_info`.

Therefore, before using syntax from older documentation, check the help output for your exact JDK:

~~~bash
jmap -h
jcmd -h
jhsdb jmap --help
~~~

Oracle marks `jmap` as experimental and unsupported, and recommends using `jcmd` for modern diagnostics because it offers more diagnostic commands and reduces performance overhead.

## 3. Obtaining a heap summary from a running JVM with jcmd

Basic workflow:

List running JVMs:

~~~bash
jcmd -l
~~~

Check whether the target JVM supports the command:

~~~bash
jcmd <pid> help GC.heap_info
~~~

Retrieve the heap summary:

~~~bash
jcmd <pid> GC.heap_info
~~~

For example, if the application PID is `12345`:

~~~bash
jcmd 12345 GC.heap_info
~~~

On JDK 24.0.2, `GC.heap_info` is described as providing general information about the Java heap. The command help reports `Impact: Medium`; consider the impact before running it in production and avoid calling it repeatedly at high frequency.

`jcmd` must run on the same machine as the target JVM and under the same effective user/group that launched the JVM. If the process cannot be found or attach fails, check the PID, user, container namespace, and Attach mechanism configuration.

## 4. Creating a sample JVM for practice

Create the file **HeapSummaryProbe.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class HeapSummaryProbe {
    private static final List<byte[]> KEEP = new ArrayList<>();

    public static void main(String[] args) throws Exception {
        for (int i = 0; i < 24; i++) {
            KEEP.add(new byte[1024 * 1024]);
        }

        System.out.println(
                "HeapSummaryProbe ready; pid=" +
                ProcessHandle.current().pid());
        System.out.println("retainedMiB=" + KEEP.size());

        Thread.sleep(120_000);
    }
}
~~~

The program retains 24 byte arrays of 1 MiB each so that the heap holds actual data during observation. `Thread.sleep` keeps the JVM running for two minutes.

Compile with JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 HeapSummaryProbe.java
~~~

Run with a 128 MiB heap limit and G1 GC:

~~~bash
java -Xms64m -Xmx128m -XX:+UseG1GC -Dprobe.heap=summary HeapSummaryProbe
~~~

Stdout looks like:

~~~text
HeapSummaryProbe ready; pid=12345
retainedMiB=24
~~~

The PID changes on each run. Open a second terminal, take the printed PID, and run:

~~~bash
jcmd 12345 GC.heap_info
~~~

After completing the check, return to the first terminal and press Ctrl+C to stop the sample program.

This example was compiled with `javac --release 17` and verified on JDK 24.0.2.

## 5. Example heap summary with G1 GC

A representative result from the test JVM on JDK 24.0.2:

~~~text
12345:
 garbage-first heap   total reserved 131072K, committed 83968K, used 50900K
 region size 1024K, 2 young (2048K), 1 survivors (1024K)
 Metaspace       used 337K, committed 512K, reserved 1114112K
  class space    used 21K, committed 128K, reserved 1048576K
~~~

Actual values vary depending on timing, JDK, collector, configuration, and object count. Memory region addresses may also be printed at the end of the heap line.

Key fields:

- **total reserved:** the heap address space reserved by the JVM. This is virtual address space, not necessarily physical RAM currently consumed.
- **committed:** the amount of memory the JVM has committed for the heap and made available for allocations.
- **used:** the amount of heap space currently occupied by objects and heap structures.
- **region size:** the size of a single G1 region.
- **young:** the number of regions currently belonging to the young generation and their total capacity.
- **survivors:** the number of survivor regions and their corresponding capacity.
- **Metaspace:** native memory used to store class metadata.
- **class space:** the Compressed Class Space region used for class metadata when compressed class pointers are enabled.

In this example, G1 has a total reserved space of 131072K (128 MiB), committed 83968K, and used 50900K. The region size is 1024K (1 MiB).

Do not interpret `reserved` as consumed RAM. Distinguishing `reserved`, `committed`, and `used` helps avoid false conclusions when comparing heap figures against OS-reported RAM usage.

## 6. Reading committed, used, and maximum heap

Commonly confused concepts:

| Value | Meaning |
|---|---|
| Initial heap (-Xms) | The initial heap size configured for the JVM. |
| Maximum heap (-Xmx) | The maximum heap limit configured for the JVM. |
| Committed heap | The amount of memory the JVM has committed for the heap at the time of the query. |
| Used heap | The amount of memory currently used in the heap at the time of the query. |
| Reserved heap | The virtual address space the JVM has reserved for the heap. |

To inspect the related VM flags:

~~~bash
jcmd 12345 VM.flags
~~~

With the sample program started using `-Xms64m -Xmx128m`, the output may contain:

~~~text
-XX:InitialHeapSize=67108864
-XX:MaxHeapSize=134217728
-XX:+UseG1GC
~~~

The corresponding byte values:

- 67108864 bytes = 64 MiB.
- 134217728 bytes = 128 MiB.

`VM.flags` shows the configured flags, while `GC.heap_info` shows the current heap state. Use both commands together to distinguish configured limits from committed and used memory.

Do not assume `committed` is always equal to `-Xmx`. The JVM can commit heap memory gradually on demand while keeping the maximum limit higher.

## 7. Metaspace is not part of the Java Heap

A heap summary typically displays Metaspace and Class Space alongside the heap section, but these two areas are not part of the Java object heap.

- **Java Heap:** stores objects and arrays allocated by the application and the JVM.
- **Metaspace:** stores metadata related to classes, methods, and runtime types.
- **Compressed Class Space:** the area dedicated to compressed class pointers when this mechanism is enabled.
- **Native memory:** also includes thread stacks, code cache, GC structures, direct buffers, and other native allocations.

An application can have low heap usage yet still consume significant native memory or Metaspace. Therefore, do not use a heap summary alone to explain total RSS or process RAM consumption.

If you need to inspect native memory, you can use Native Memory Tracking (NMT) when enabled at JVM startup:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Then query it:

~~~bash
jcmd 12345 VM.native_memory summary
~~~

NMT must be enabled when the JVM starts. If it was not enabled at startup, you cannot retroactively start collecting full native memory data with a later `jcmd` command.

## 8. Heap summary depends on the garbage collector

The output structure reflects how the collector manages the heap. Not all JVMs share the same generations or spaces.

### G1 GC

G1 divides the heap into equal-sized regions. Regions are dynamically assigned roles such as Eden, Survivor, and Old.

The heap summary may display:

- Total reserved, committed, and used.
- Region size.
- Number of young regions and survivor regions.
- Metaspace and class space.

The number of young/survivor regions changes with allocations and GC cycles. Do not treat the region counts at a single moment as fixed configuration.

### Serial GC

With Serial GC, the output may display traditional generational spaces such as DefNew, Eden, From Space, To Space, and Tenured.

Example actual output from the test JVM on JDK 24.0.2:

~~~text
DefNew     total 19648K, used 10664K
 eden space 17472K, 48% used
 from space 2176K, 98% used
 to   space 2176K, 0% used
Tenured    total 43712K, used 15472K
 the space 43712K, 35% used
Metaspace  used 337K, committed 512K, reserved 1114112K
 class space used 21K, committed 128K, reserved 1048576K
~~~

In Serial GC:

- **Eden:** the space that typically receives new object allocations.
- **From Space / To Space:** two survivor spaces that alternate during young collections.
- **Tenured:** the space holding objects promoted to the old generation.

Utilization percentages change depending on when the snapshot is taken and the GC cycle.

### Parallel GC and other collectors

Parallel GC also uses a traditional young/old generation model, though thread counts and space allocation depend on configuration.

ZGC, Shenandoah, and other collectors have their own organization and output formats. Do not mechanically apply Eden/Survivor/Old interpretation to every collector.

Always confirm the active collector via VM flags or JVM configuration and read the actual fields present in the target output.

## 9. A heap summary is a snapshot, not a memory leak report

A single run of:

~~~bash
jcmd 12345 GC.heap_info
~~~

reflects only the state at the moment the command is processed.

The `used` value can rise due to normal allocation and then drop after GC reclaims unreferenced objects. A high `used` value before GC does not automatically mean the application has a leak.

To investigate trends:

1. Collect heap summaries at multiple timestamps with reasonable intervals.
2. Record the timestamp, collector, `-Xms`, `-Xmx`, and workload.
3. Compare `used` levels after equivalent GC cycles.
4. Check whether the post-GC live set grows continuously.
5. Combine with GC logs or Java Flight Recorder (JFR) to inspect allocation rates and GC duration.
6. If you need to identify which objects retain memory, take a heap dump following approved procedures and analyze it with a dedicated tool.

If `used` increases continuously across equivalent GC cycles and does not return to a baseline, that is a signal worth investigating. Still, review workload, caches, sessions, queues, and object retention before concluding a memory leak.

Do not force a Full GC just to make a `used` number look cleaner. Forcing GC can introduce long pauses and alter application behavior.

## 10. When do you need a heap histogram or heap dump?

A heap summary gives an overview of capacity, but it does not show which classes consume memory.

### Heap histogram

A histogram reports instance counts and total bytes per class.

You can use `jmap`:

~~~bash
jmap -histo 12345
~~~

Or `jcmd`:

~~~bash
jcmd 12345 GC.class_histogram
~~~

A histogram is useful for finding classes with large object counts or byte totals. It does not provide the full object reference graph needed to determine why objects are still retained.

### Heap dump

A heap dump writes out the contents of the object heap for deep analysis:

~~~bash
jcmd 12345 GC.heap_dump filename=heap.hprof
~~~

Heap dumps can be very large, increase I/O, and cause significant pauses. The file may contain passwords, tokens, personal data, and in-flight application payloads. Ensure sufficient disk space, restricted access permissions, and an appropriate retention policy.

A heap dump is not a heap summary. Only generate one when object retention analysis is needed and operational impact has been assessed.

## 11. jhsdb jmap --heap and core dumps

JDK 24 provides `jhsdb jmap --heap` to print a heap summary via the Serviceability Agent. For postmortem analysis, it can read a core dump:

~~~bash
jhsdb jmap --heap --core core.12345 --exe /path/to/java
~~~

Where:

- `--heap`: requests printing the Java heap summary.
- `--core`: path to the core dump.
- `--exe`: the Java executable corresponding to that core dump.

Both `--core` and `--exe` must be supplied together. The executable must match the JVM that produced the core dump; do not arbitrarily use a Java binary from a different version.

The help output also lists `--pid` to attach to a running JVM:

~~~bash
jhsdb jmap --heap --pid 12345
~~~

However, `jhsdb` is an experimental and unsupported tool. JDK documentation warns that attaching to a running process can cause the process to hang and may crash it when the debugger detaches. Therefore, use `jcmd GC.heap_info` for routine live heap summaries; reserve `jhsdb jmap --heap` for core dump/postmortem analysis when appropriate.

## 12. Permissions and impact when running diagnostic commands

For `jcmd` to connect to a JVM:

- Run on the same machine as the target JVM.
- Use the same effective user/group that started the JVM.
- Verify the PID still exists and belongs to the right application.
- Check that the Attach mechanism has not been disabled.
- In containers, run inside the matching PID namespace and an environment that can access the JVM.

Check the impact of the heap command:

~~~bash
jcmd 12345 help GC.heap_info
~~~

On JDK 24.0.2, the command reports `Impact: Medium`. Do not run it in a tight loop or attach to every JVM without a clear purpose.

`jmap` and `jhsdb` are experimental/unsupported tools in the JDK 24 documentation. For new operational workflows, prefer `jcmd` diagnostic commands and check the help output of the target JVM itself.

## 13. Common errors when retrieving a heap summary

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `jmap -heap` returns an error | Legacy option is not supported by the current JDK binary. | Use `jcmd PID GC.heap_info` for a live JVM. |
| `jcmd` cannot find the PID | Wrong PID, process exited, or running in a different namespace. | Re-run `jcmd -l` in the correct environment. |
| Attach permission denied | Current user lacks attach permissions. | Use the matching service account and check OS permissions. |
| `GC.heap_info` is not supported | JVM/collector/vendor does not provide the command. | Run `jcmd PID help` and check for an appropriate tool. |
| Output differs from examples | Different JDK, GC, flags, or snapshot timing. | Read the actual collector name and fields rather than relying on fixed line positions. |
| Low `used` heap but high process RAM | Native memory, Metaspace, direct buffers, stacks, or code cache consume memory. | Check NMT, OS metrics, and runtime configuration. |
| High `used` heap in one snapshot | Allocation is in progress or GC has not reclaimed objects yet. | Monitor multiple snapshots and compare after equivalent GC cycles. |
| Heap summary does not show which class consumes memory | Summary only provides aggregate figures. | Use a class histogram or heap dump when needed. |
| `jhsdb` hangs the process | Serviceability Agent attached to a live process. | Avoid on live processes; prefer `jcmd` or core dump analysis. |
| Heap dump runs out of disk space | Dump file exceeds available free space. | Verify disk capacity and retention policy before dumping. |

## 14. Workflow for retrieving and reading a heap summary

A practical workflow:

1. Identify the JDK and running JVM version.
2. Run `jcmd -l` to locate the target PID.
3. Check `jcmd PID help GC.heap_info`.
4. Run `jcmd PID GC.heap_info` and save the output if needed.
5. Read the collector, reserved, committed, used, regions/generations, and Metaspace.
6. Run `jcmd PID VM.flags` to cross-check `InitialHeapSize`, `MaxHeapSize`, and GC flags.
7. Compare multiple snapshots under similar workloads and equivalent timing.
8. If a memory leak is suspected, use GC logs/JFR and histograms to narrow down the investigation.
9. Only capture a heap dump after evaluating pause impact, disk space, and data sensitivity.
10. For a crashed JVM, use the core dump with `jhsdb jmap --heap --core ... --exe ...`.

Do not hardcode a single run's PID, heap size, or region count into static configuration. These values depend on the process and runtime state.

## 15. Checklist before concluding the heap is running out of memory

- [ ] Confirmed the target JVM and PID.
- [ ] Checked the JDK version and garbage collector.
- [ ] Used `jcmd PID GC.heap_info` for the live heap summary.
- [ ] Distinguished reserved, committed, used, and maximum heap.
- [ ] Checked `-Xms` and `-Xmx` with `jcmd PID VM.flags`.
- [ ] Distinguished Java Heap from Metaspace and native memory.
- [ ] Reviewed generation/region layout appropriate for the active collector.
- [ ] Compared multiple snapshots rather than concluding from a single point in time.
- [ ] Cross-referenced GC logs or JFR when trend analysis is needed.
- [ ] Used histogram/heap dump only when class-level or object retention analysis is required.
- [ ] Assessed impact, attach permissions, disk space, and data sensitivity.
- [ ] Avoided attaching `jhsdb` directly to a live production process.

## 16. References

- Oracle JDK 24 — Diagnostic Tools, jmap and heap configuration/usage sections: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- Oracle JDK 24 — The jhsdb Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jhsdb.html
- Oracle JDK 24 — The jcmd Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html

A heap summary provides a quick view of the Java Heap state and how the collector organizes memory. On modern JDKs, `jcmd PID GC.heap_info` is the right choice for a running JVM; interpret the figures alongside the collector, VM flags, and GC trends to draw accurate conclusions.