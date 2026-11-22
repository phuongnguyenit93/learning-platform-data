# jmap Dump Format: HPROF Heap Dump

## 1. What is a heap dump?

A heap dump is a snapshot of a JVM's Java heap at a specific point in time. The dump file records objects, classes, fields, primitive values, object references, and the information needed to analyze which objects are being retained in memory.

With the HotSpot JDK, the `jmap -dump:format=b` command creates a heap dump in the HPROF (Heap/HPROF) binary format. This is a standard format that can be opened with Eclipse Memory Analyzer (MAT) and other compatible heap analysis tools.

A heap dump is useful when:

- Investigating memory leaks and unexpectedly retained objects.
- Finding classes or object types consuming a large amount of heap.
- Tracing reference paths from Garbage Collection (GC) roots to an object.
- Checking unboundedly growing collections, caches, or sessions holding data for too long.
- Analyzing object state after an abnormal memory spike.

It is important to distinguish between three types of artifacts:

| Artifact | Scope | Purpose |
|---|---|---|
| Java heap dump (HPROF) | Java heap objects and structure | Analyze objects, references, GC roots |
| OS core dump | Process address space and native state at the OS level | Analyze crashes, native memory, JVM internals |
| Thread dump | Stack traces and thread states at a point in time | Investigate deadlocks, blocking, hung requests |

An HPROF file is not a copy of the process's entire RAM. It does not contain all native allocations, shared libraries, registers, or OS state like a core dump does. It is also not an allocation history over time; if you need to know where and when objects were allocated, collect data using Java Flight Recorder (JFR) or a profiler.

## 2. What is the HPROF binary format?

The `format=b` option instructs `jmap` to write the heap dump in binary HPROF format. The file is not plain text meant to be read directly in Notepad or a standard text editor. The bytes in the file are organized into a header and a sequence of records with tags, timestamps, and payloads.

On the tested HotSpot JDK 24.0.2, the file header starts with the string:

~~~text
JAVA PROFILE 1.0.2
~~~

Following the header string are a null terminator byte, the identifier size, a timestamp, and the records. An HPROF record has the following general structure:

| Component | Size | Meaning |
|---|---:|---|
| TAG | 1 byte | Record type |
| Time offset | 4 bytes | Relative time from the timestamp in the header |
| Body length | 4 bytes | Number of bytes in the payload |
| BODY | Variable (per length) | Record contents |

Records can describe UTF-8 names, loaded classes, stack frames, stack traces, threads, objects, arrays, fields, and heap metadata. Identifiers are used to link objects, classes, strings, and stack traces within the file; the identifier size is recorded in the header, so you should not assume every identifier is 4 bytes.

### HPROF 1.0.1 and 1.0.2

HPROF has multiple header versions. HPROF 1.0.2 adds the ability to split a heap dump into multiple segment records, ending with an end-of-dump record. Segmenting allows large dumps to be represented without needing a single monolithic heap record.

Oracle's release documentation notes that binary HPROF 1.0.2 is used for binary heap dumps in modern JDKs. However, let a compatible parser handle the header and records rather than parsing with fixed offsets manually.

## 3. HPROF file structure and contents

A binary HPROF file typically contains:

- Class metadata: class names, superclasses, class loaders, and field information.
- Object records: object instances and references to other objects.
- Primitive values: numeric or boolean values stored in fields and primitive arrays.
- Array records: object arrays and primitive arrays.
- GC roots: starting points used by the GC to determine reachable objects, such as stack/local variables, static fields, or JNI references depending on the root type.
- Thread and stack information: thread data, stack frames, and stack traces included in the dump.
- Heap metadata: records describing heap state and structure.

HPROF is a snapshot. It shows the objects that exist or are recorded in the snapshot and their references. It does not directly answer:

- Which line of code allocated an object, unless separate allocation traces are available.
- How long an object has existed.
- How many times an object was allocated over the entire runtime.
- Which native memory outside the Java heap is consuming RAM.
- What operations a thread performed before the dump, without other trace data.

Use JFR or a profiler to analyze allocations over time; use Native Memory Tracking, OS tools, or a core dump when the question lies outside the Java heap.

## 4. Creating an HPROF dump with jmap

Check the options supported by the installed JDK:

~~~bash
jmap -h
~~~

General dump syntax:

~~~bash
jmap -dump:<dump-options> <pid>
~~~

Key options:

| Option | Meaning |
|---|---|
| `live` | Write only live objects |
| `all` | Write all objects currently in the heap, including uncollected unreachable objects |
| `format=b` | Write binary HPROF |
| `file=<path>` | Output file path |
| `gz=<1..9>` | Write HPROF compressed with gzip at compression level 1 to 9 on the tested JDK 24.0.2 |

Example of dumping live objects:

~~~bash
jmap "-dump:live,format=b,file=heap-live.hprof" <pid>
~~~

Dumping all objects:

~~~bash
jmap "-dump:all,format=b,file=heap-all.hprof" <pid>
~~~

If neither `live` nor `all` is specified, the JDK 24.0.2 help indicates that the default is `all`. If both are passed, `live` takes precedence.

The `live` option ensures the dump contains only objects that are reachable according to the JVM state at capture time. The `all` option can retain unreachable objects that are still present in the heap because they have not yet been collected. The two options answer different questions: `live` is suitable for inspecting retained objects; `all` can be useful when you want to observe unreachable objects before GC collects them.

Do not confuse the default of `jmap` with `jcmd GC.heap_dump`: `jcmd` defaults to dumping live objects and requests a full GC, unless `-all` is used.

## 5. Creating a gzip-compressed HPROF dump

A heap dump can be nearly as large as the captured Java heap size. On JDK 24.0.2, `jmap -h` provides the `gz` option:

~~~bash
jmap "-dump:live,format=b,gz=1,file=heap-live.hprof.gz" <pid>
~~~

Compression levels:

- `gz=1`: fastest compression, typically uses less CPU.
- `gz=9`: stronger compression, but typically takes more CPU and time.
- Intermediate levels balance file creation time and storage size.

Gzip simply wraps the binary HPROF inside. When decompressed, the HPROF header still starts with `JAVA PROFILE 1.0.2`. A gzip file typically has magic bytes `1F 8B`; you can verify this with the `gzip` tool or a hex viewer.

Example of verifying a gzip file:

~~~bash
gzip -t heap-live.hprof.gz
~~~

Do not rename the file extension to turn a regular HPROF into a gzip file or vice versa. The extension should reflect the actual contents, such as `.hprof` for binary HPROF and `.hprof.gz` for gzip-compressed HPROF.

Compression reduces disk usage and file transfer costs. In return, the analysis tool must decompress or read the compressed stream, which can increase parsing and query times.

## 6. Generating a histogram to inspect before dumping

If you only need to know which classes have the most instances or consume the most bytes, you can use a histogram instead of creating a large heap dump:

~~~bash
jmap -histo <pid>
~~~

Count only live objects:

~~~bash
jmap -histo:live <pid>
~~~

On JDK 24.0.2, the histogram can be written to a file:

~~~bash
jmap "-histo:live,file=heap-histogram.txt" <pid>
~~~

The output typically includes these columns:

| Column | Meaning |
|---|---|
| `num` | Row index |
| `#instances` | Number of instances of the class |
| `#bytes` | Total shallow size of the instances |
| `class name` | Class name or array name |

A histogram only provides per-class statistics; it does not show the full reference paths between objects. If the histogram reveals an unusual object type, open a heap dump in MAT to find GC roots and retention paths.

## 7. Using jcmd GC.heap_dump as the modern alternative

Oracle recommends using `jcmd` instead of `jmap` in modern diagnostic workflows because `jmap` is an experimental/unsupported tool and may not be present in future JDKs.

Check the syntax on the target JVM:

~~~bash
jcmd <pid> help GC.heap_dump
~~~

Create a live HPROF dump:

~~~bash
jcmd <pid> GC.heap_dump heap-live.hprof
~~~

Create a dump including unreachable objects:

~~~bash
jcmd <pid> GC.heap_dump -all heap-all.hprof
~~~

Create a gzip-compressed HPROF:

~~~bash
jcmd <pid> GC.heap_dump -gz=1 heap-live.hprof.gz
~~~

Default differences to remember:

| Tool | Default | How to capture all objects |
|---|---|---|
| `jmap -dump` | `all` if neither `live` nor `all` is specified | Default or specify `all` |
| `jcmd GC.heap_dump` | Live objects only; requests a full GC | Add `-all` |

According to JDK 24 help, `GC.heap_dump` has `Impact: High`, depending on heap size and contents. `-gz` accepts compression levels 1 to 9; `-overwrite` allows overwriting an existing file; `-parallel` adjusts the number of threads used for dumping. Check the help of your exact JVM before using these options.

JDK 15 and later can create chunked gzip HPROF files with `jcmd GC.heap_dump -gz=1`. Eclipse MAT version 1.12 and later supports reading this chunked gzip format. This differs from a standard gzip HPROF file produced by the OS `gzip` tool.

## 8. Complete Java 17 example: creating a heap dump

Create the file `src/demo/HeapDumpDemo.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

/** A small process that retains objects for heap dump practice. */
public final class HeapDumpDemo {
    private static final List<byte[]> RETAINED = new ArrayList<>();

    /**
     * Retains four byte arrays and waits for inspection.
     *
     * @param args command-line arguments
     * @throws InterruptedException if the wait is interrupted
     */
    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 4; i++) {
            RETAINED.add(new byte[1024 * 1024]);
        }

        System.out.println("READY retainedMiB=" + RETAINED.size());
        Thread.sleep(120_000);
    }
}
~~~

Compile:

~~~bash
javac --release 17 -d classes src/demo/HeapDumpDemo.java
~~~

Open Terminal 1 and run:

~~~bash
java -Xms32m -Xmx128m -cp classes demo.HeapDumpDemo
~~~

Exact stdout:

~~~text
READY retainedMiB=4
~~~

Keep the process running. Open Terminal 2 and find the PID:

~~~bash
jps -l
~~~

Create a live dump with `jmap`:

~~~bash
jmap "-dump:live,format=b,file=heap-live.hprof" <pid>
~~~

Create a gzip dump:

~~~bash
jmap "-dump:live,format=b,gz=1,file=heap-live.hprof.gz" <pid>
~~~

Replace `<pid>` with the actual PID of `demo.HeapDumpDemo`. On Windows PowerShell, enclose the entire `-dump:...` argument in double quotes so it is passed as a single argument to `jmap`.

You can use `jcmd` instead:

~~~bash
jcmd <pid> GC.heap_dump heap-live-jcmd.hprof
~~~

Once finished, return to Terminal 1 and press Ctrl+C. The `.hprof` file is the dump for analysis; the `.hprof.gz` file is the gzip-compressed version.

## 9. Opening and analyzing HPROF with Eclipse MAT

Eclipse Memory Analyzer (MAT) reads binary HPROF heap dumps and provides an interface to analyze the object graph.

Basic workflow:

1. Open MAT.
2. Select File → Open Heap Dump.
3. Select the `.hprof` file or a gzip HPROF file supported by your MAT version.
4. Wait for MAT to parse and index the dump.
5. Check the Overview to see total size, classes, and object counts.
6. Use the Histogram to find classes occupying the most shallow heap.
7. Use the Dominator Tree to find objects or groups of objects retaining the most retained heap.
8. Use Path to GC Roots to find why an object is still reachable.

Key concepts:

- **Shallow heap**: memory directly consumed by an object itself, excluding referenced objects.
- **Retained heap**: amount of memory that could be freed if that object or group of objects were no longer retained.
- **Dominator**: an object that controls the reachability of other objects in the graph.
- **GC roots**: starting points used by the GC to determine live objects.
- **Unreachable objects**: objects with no reference path from GC roots; they may not have been collected yet at dump time.

MAT can analyze binary HPROF files, but the results also depend on the dump type, JVM, and how the dump was created. If you need to inspect unreachable objects, make sure the dump includes them; use `jmap` with `all` or `jcmd` with `-all` when appropriate.

## 10. Automatic heap dump on OutOfMemoryError

You can configure the JVM to create an HPROF file when an `OutOfMemoryError` occurs:

~~~bash
java \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=./heap-dumps \
  -jar application.jar
~~~

The target directory must exist and have sufficient space, and the user running the JVM must have write permissions. You can specify a specific file path according to operational policy.

This configuration is useful when an error occurs outside business hours or when you cannot attach in time to take a manual dump. However, heap dumps can be large, and writing the file requires significant time, I/O, and storage space. Check available disk space before enabling this in production.

The legacy HPROF agent `-agentlib:hprof=heap=dump,format=b` was removed in Java 9. Do not reuse old instructions requiring the HPROF agent on modern JDKs.

## 11. Risks of creating and sharing heap dumps

Creating a heap dump can significantly impact an application:

- Large dumps take time and I/O to write to disk.
- `jcmd GC.heap_dump` requests a full GC by default; the JVM may pause during this process.
- `jmap` may need to attach to the process and perform heap inspection operations; duration depends on heap size, collector, and environment.
- Writing the file can fill up the disk or container volume.
- Dump files may contain tokens, passwords, personal information, request payloads, cached data, and business data.
- Anyone with the HPROF file can read much of the data currently residing in the heap.

Before taking a dump in production:

1. Identify the exact PID and JVM.
2. Check free disk space, output directory, and write permissions.
3. Choose `live` or `all` based on your investigation goal.
4. Choose gzip if you need to reduce storage or transfer size.
5. Record the timestamp, JDK version, PID, and exact command executed.
6. Restrict file access permissions and retention duration.
7. Only transfer the file through approved secure channels.

Do not upload heap dumps to public services or share them in tickets/chats with broad audiences without checking for sensitive data and organizational policies.

## 12. Common errors and troubleshooting

### jmap is not recognized

`jmap` is a JDK tool. Verify that you are using a JDK whose `bin` directory contains the tool and that `PATH` points to the right JDK.

### More than one non-option argument

The shell may have split the `-dump:...` string into multiple arguments. Pass the entire dump option as a single argument:

~~~bash
jmap "-dump:live,format=b,file=heap-live.hprof" <pid>
~~~

### Unable to open socket file or attach failed

Check that the PID is still running, user/group permissions, the attach mechanism, the tool's JDK, and the target JVM. Do not use a PID from another machine or namespace.

### Insufficient disk space or unable to write file

Check the disk, volume, directory permissions, and the path actually visible to the process. Choose a location with sufficient space and write permissions.

### Unable to open .hprof file

Check whether the dump finished writing, whether the file size is reasonable, whether it is actually a binary HPROF file, and whether MAT supports that version/variant. Gzipped HPROF files must be opened with a MAT version that supports the corresponding gzip format.

### Unable to open gzip file

Check whether the file is truly gzipped or merely renamed. Gzip files typically start with magic bytes `1F 8B`. Use `gzip -t` to verify the integrity of the compressed stream.

### MAT reports missing or unseen unreachable objects

Check whether the dump was created with `live` or `all`. If only `live` was dumped, unreachable objects were excluded from the file. Recreate the dump with `jmap` `all` or `jcmd` `-all` if your investigation requires them.

### Dump is too large or analysis is too slow

Try gzip, ensure the analysis machine has enough RAM and disk space, or use a histogram first to identify notable classes. Do not discard needed data with `live` if you need to analyze unreachable objects.

## 13. Checklist before creating and analyzing a dump

- [ ] Confirm whether the goal is a Java heap dump (HPROF) or an OS core dump.
- [ ] Check `jmap -h` on the current JDK for the exact options.
- [ ] Choose `live` or `all` based on the question you need to answer.
- [ ] Specify `format=b` to create a binary HPROF dump.
- [ ] Choose an output file path with sufficient space and write permissions.
- [ ] Consider `gz` to reduce file size.
- [ ] Remember that `jmap` and `jcmd GC.heap_dump` have different defaults.
- [ ] Verify that the file finished writing and has a valid HPROF/gzip header.
- [ ] Use MAT or a compatible tool for analysis.
- [ ] Protect the file, as dumps may contain sensitive data.
- [ ] Record the PID, timestamp, JDK version, dump type, and command.
- [ ] Prefer `jcmd GC.heap_dump` on modern JDKs; `jmap` is an experimental/unsupported tool.

## 14. Core dumps and jhsdb jmap

If you need to analyze an OS core file, use the Serviceability Agent instead of passing the core file to `jmap`'s PID syntax:

~~~bash
jhsdb jmap --core ./core.1234 --exe ./java
~~~

The `--core` and `--exe` pair must be specified together. For a running JVM, `jhsdb jmap --pid <pid>` can perform the operations supported by the tool, but the Serviceability Agent may pause the JVM while attached; only use it when you understand the impact and have appropriate permissions.

Help:

~~~bash
jhsdb jmap --help
~~~

Some dump-related options:

- `--binaryheap`: dump the Java heap in HPROF format.
- `--dumpfile <name>`: output file name.
- `--gz <1-9>`: gzip compression level.
- `--core` and `--exe`: specify the core file along with its corresponding executable.

## 15. References

- [Oracle JDK 17 — The jmap Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jmap.html): `-dump`, `live`, `format=b`, `file` syntax, and the unsupported status of `jmap`.
- [Oracle JDK 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html): `GC.heap_dump` options, `-all`, `-gz`, `-overwrite`, and impact level.
- [Oracle JDK 24 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html): JVM diagnostic guidance and recommendation to use `jcmd` for modern workflows.
- [Eclipse MAT — Acquiring Heap Dumps](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/tasks/acquiringheapdump.html): how to create and open HPROF, gzip, and chunked gzip support.
- [OpenJDK — HPROF heap dump implementation](https://github.com/openjdk/jdk11u/blob/master/src/hotspot/share/services/heapDumper.cpp): description of HPROF headers, records, and heap dump segments.

`jmap -dump:...,format=b,file=...` creates a binary HPROF heap dump for analyzing the Java heap. Understanding HPROF headers/records, distinguishing `live` from `all`, choosing appropriate gzip compression, and opening the file with a compatible tool will make memory leak investigations more accurate. On modern JDKs, consider `jcmd GC.heap_dump` and always protect dumps as sensitive data.
