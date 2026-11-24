# 10.3. Capturing Virtual-Thread Dumps with `jcmd Thread.dump_to_file` (Plain and JSON)

## Objectives

After this lesson, you will be able to:

1. Explain why traditional thread dumps can miss virtual threads that are temporarily suspended.
2. Identify the right Java process and generate both `plain` and `json` dumps using `jcmd`.
3. Locate a virtual thread's stack trace in the output file, read the JSON structure, and recognize signals that warrant further investigation.
4. Understand snapshot limitations and troubleshoot common errors when collecting dumps on servers/containers.

> **Naming distinction:** `Thread.dump_to_file` here is a **HotSpot/JVM diagnostic command**, invoked via the `jcmd` command-line tool. It is **not** a `java.lang.Thread.dump_to_file()` method to call in Java code.

## 1. Context: Virtual Threads Change How We Observe Applications

- A **platform thread** is typically bound to an OS thread for its entire lifetime.
- A **virtual thread** (permanent since Java 21, JEP 444) is scheduled by the JVM onto a platform thread called a **carrier**. When encountering a wait operation that supports unmounting (such as supported I/O or `LockSupport.park`), the virtual thread is suspended and the carrier can serve other work.
- As a result, an application can have huge numbers of waiting virtual threads even with few carrier/platform threads. Traditional dumps such as `jstack` or `jcmd <PID> Thread.print` are not a complete way to list unmounted virtual threads.
- `jcmd <PID> Thread.dump_to_file` is designed to write the stacks of **both platform threads and virtual threads** to a file. This is well-suited when you need to find where tasks are waiting on I/O, locks, latches, or queues, or to trace a stalled task.

**A thread dump is a point-in-time snapshot of state**, not an execution history. An `await`, `park`, or `sleep` frame alone does not prove a deadlock or bug; you must correlate it with actual load and compare multiple samples.

### Scope and Prerequisites

- Use **JDK 21 or later** for the sample application and this diagnostic command; the `jcmd` utility from the JDK must be available.
- `jcmd` must run on the **same machine/process namespace able to attach** to the target JVM and usually requires the same effective user/group. Inside containers, the PID seen from the host may differ from the PID inside the container.
- The target JVM process must be running, support the diagnostic command, and have permission to **create the file at the target path**. The dump file is written by the **target JVM**, not by the shell invoking `jcmd`.
- Exact command names and options can be checked directly with `jcmd <PID> help Thread.dump_to_file`.

## 2. Syntax of `Thread.dump_to_file`

```bash
jcmd <PID> Thread.dump_to_file [-format=plain|-format=json] [-overwrite] <file-path>
```

Examples on Linux/macOS (replace `<PID>` with the actual PID; ensure `/tmp` is writable by the target JVM):

```bash
# Plain (default); the following two commands have the same intent:
jcmd <PID> Thread.dump_to_file /tmp/vthreads-plain.txt
jcmd <PID> Thread.dump_to_file -format=plain /tmp/vthreads-plain-2.txt

# JSON for analysis tools:
jcmd <PID> Thread.dump_to_file -format=json /tmp/vthreads-json.json
```

On Windows, use an existing path that the JVM is allowed to write to, for example:

```powershell
jcmd <PID> Thread.dump_to_file -format=plain "C:\temp\vthreads-plain.txt"
jcmd <PID> Thread.dump_to_file -format=json "C:\temp\vthreads-json.json"
```

| Component | Meaning |
| --- | --- |
| `<PID>` | The JVM process ID to inspect; not a thread ID. |
| `-format=plain` | Human-readable plain text, which is the default in the diagnostic command help. |
| `-format=json` | Structured JSON for filtering with scripts/analysis tools. |
| `-overwrite` | Allows replacing an existing file; by default **it does not overwrite**. Use only when you genuinely intend to discard the previous copy. |
| `<file-path>` | File location **on the target JVM process's filesystem**. |

Some Oracle articles use `-format=text` to refer to the plain-text format. On HotSpot, the built-in help for `Thread.dump_to_file` lists the two options as **`plain` and `json`**. For consistency and ease of verification, use `-format=plain` or omit `-format` altogether for plain text.

An **absolute** path avoids confusion. If a relative path is given, the JVM resolves it relative to the **target process's** working directory; consequently, the file may not appear in the working directory of the terminal where `jcmd` was invoked.

## 3. Hands-On: Create Three Easily Searchable Virtual Threads

Create the file **`VirtualThreadDumpDemo.java`** with the following complete Java 21 program:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class VirtualThreadDumpDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch release = new CountDownLatch(1);
        List<Thread> threads = new ArrayList<>();

        for (int i = 1; i <= 3; i++) {
            Thread thread = Thread.ofVirtual()
                    .name("vt-demo-" + i)
                    .start(() -> {
                        try {
                            release.await();
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                        }
                    });
            threads.add(thread);
        }

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("3 virtual threads are waiting.");
        System.out.println("Press Enter to stop...");
        System.in.read();

        release.countDown();
        for (Thread thread : threads) {
            thread.join();
        }
        System.out.println("Done.");
    }
}
```

**Why is this example well-suited for taking a dump?** `Thread.ofVirtual()` creates real virtual threads; `name("vt-demo-" + i)` names them `vt-demo-1` through `vt-demo-3`. Each thread waits at `CountDownLatch.await()` until `main` calls `countDown()`. `main` waits for the user to press Enter, providing plenty of time to collect dumps from another terminal. `join()` ensures the program exits cleanly after all three virtual threads finish.

### Terminal A — Start the Program

```bash
javac --release 21 VirtualThreadDumpDemo.java
java VirtualThreadDumpDemo
```

Sample output (the PID value depends on your machine):

```text
PID=12345
3 virtual threads are waiting.
Press Enter to stop...
```

**Keep Terminal A open and do not press Enter yet.** The program is running, and the virtual threads remain waiting on the latch.

### Terminal B — Identify the JVM and Collect Both Formats

```bash
jcmd -l
jcmd 12345 help Thread.dump_to_file
jcmd 12345 Thread.dump_to_file -format=plain /tmp/vthreads-demo.txt
jcmd 12345 Thread.dump_to_file -format=json /tmp/vthreads-demo.json
```

Here `12345` is **only an illustrative PID**: replace it with the actual PID printed in Terminal A. The two files must have different names so both outputs are preserved. Once `jcmd` reports that file creation succeeded, check on the **machine/container where the target JVM is running**:

```bash
ls -lh /tmp/vthreads-demo.txt /tmp/vthreads-demo.json
grep -n "vt-demo-" /tmp/vthreads-demo.txt
```

Once finished, return to Terminal A and **press Enter**. Expected final line:

```text
Done.
```

If you are on Windows, replace `/tmp/...` with a Windows path as shown in Section 2. If the JVM runs inside Docker/Kubernetes, execute the command inside the appropriate container or use an appropriate attach mechanism, then copy the file out of the container filesystem as needed.

## 4. How to Read a `plain` Dump

Open the file with `less`, `grep`, an editor, or a text search tool. Focus on:

1. **Thread name**: search for `vt-demo-1`, `vt-demo-2`, `vt-demo-3`, or your application's task/request naming convention.
2. **Virtual thread indicator**: the plain format may display a `virtual` label; exact presentation details depend on the JDK release.
3. **Stack trace**: read from the top frame downward to find the waiting method and the business methods that called it. In the demo, look for `CountDownLatch.await` (possibly alongside `LockSupport.park` or internal JVM frames).
4. **Repeating patterns**: many threads stopped at the same JDBC, HTTP, queue, or latch call may suggest a bottleneck, though it is not yet enough to confirm the root cause.

Example searching for thread names in the dump using Unix tools:

```bash
grep -n -A 15 "vt-demo-" /tmp/vthreads-demo.txt
```

`-n` adds line numbers, and `-A 15` shows 15 lines following each match. How many frames you need to read depends on the case; never conclude a deadlock from a single `grep` result.

**Do not confuse them:** `Thread.print -l` is useful when analyzing platform threads/monitors and certain traditional JVM details, but it does not replace `Thread.dump_to_file` when the goal is to find **unmounted virtual threads**. For a complex incident, the two dump types complement each other.

## 5. How to Read a `JSON` Dump

JSON is ideal when a JVM has thousands of virtual threads, because you can filter by thread container, name, and stack without scanning the entire file manually.

In JDK 21, commonly seen fields include:

| JSON Path | Meaning |
| --- | --- |
| `threadDump.processId` | PID of the JVM that generated the dump. |
| `threadDump.time` | Timestamp of collection. |
| `threadDump.runtimeVersion` | Version of the JVM that generated the dump. |
| `threadDump.threadContainers[]` | Thread containers/groups, typically with `container`, `parent`, `owner`. |
| `threadContainers[].threads[]` | Threads belonging to each group; typically with `tid`, `name`, `stack`. |
| `threadContainers[].threadCount` | Number of threads recorded in the container. |

In JDK 21–26, values such as `processId`, `tid`, and `threadCount` may be **numeric strings**; newer JDK releases may use numeric JSON types and add new fields. Therefore, parsers should tolerate version differences instead of treating every field and representation across JDK versions as immutable. Specifically, **do not assume JDK 21 JSON includes `state`, lock-owner, or per-thread timestamp fields** found in newer JDKs.

Use `jq` (installed separately, not part of the JDK) to inspect metadata:

```bash
jq '.threadDump | {processId, time, runtimeVersion}' /tmp/vthreads-demo.json
```

List containers and thread counts:

```bash
jq -r '
  .threadDump.threadContainers[]
  | [.container, .threadCount]
  | @tsv
' /tmp/vthreads-demo.json
```

Filter the three named threads and extract the top stack frame:

```bash
jq -r '
  .threadDump.threadContainers[]
  | .container as $container
  | .threads[]?
  | select((.name // "") | startswith("vt-demo-"))
  | [$container, .tid, .name, (.stack[0] // "")]
  | @tsv
' /tmp/vthreads-demo.json
```

**Query explanation:** iterate over each `threadContainer`; extract each element of `threads`; keep only names starting with `vt-demo-`; output the container name, thread ID, thread name, and top frame as tab-separated text. Specific container strings/names and IDs change between runs.

If `jq` is unavailable, you can use a standard JSON syntax checker, for example:

```bash
python3 -m json.tool /tmp/vthreads-demo.json > /dev/null
```

The Python command above only verifies that the file is valid JSON; it does not analyze stall causes. For deeper inspection, write a JSON parser using an appropriate library or load the file into an analysis tool compatible with your JDK version.

## 6. Using Dumps to Investigate a Real Incident

Suppose a service handles requests using virtual threads and many requests become slow:

1. **Confirm the exact PID and symptom window.** Record load, affected endpoints, and timestamps; avoid capturing a dump from the wrong JVM.
2. **Capture at least two or three samples a short interval apart**, using different filenames such as `vthreads-01.json`, `vthreads-02.json`, `vthreads-03.json`. Each capture is an independent snapshot.
3. **Group stacks by business call:** many threads paused at `socketRead`, `Future.get`, `CountDownLatch.await`, a connection pool, or holding a lock may point to where to look; identify what is supposed to satisfy the wait condition.
4. **Compare across samples:** stacks stuck at the exact same point may indicate a long wait or stall, or simply normal worker behavior. Check timeouts, queue depths, I/O durations, dependencies, and logs.
5. **Combine with other evidence** when needed: JFR (especially `jdk.VirtualThreadPinned` when investigating pinning), application logs, metrics, or `jcmd <PID> Thread.print -l` to examine platform threads and locks.

Do not assign `BLOCKED`/`WAITING` labels just by guessing from a stack frame in a JDK 21 dump; full thread states and lock metadata depend on the JDK version. A dump is not a CPU measurement, profiler, or automatic deadlock detector.

### Two Other Useful Command Patterns

```bash
# List the JVMs visible to jcmd on the machine:
jcmd -l

# Traditional platform-thread dump written to a file by the shell:
jcmd <PID> Thread.print -l > /tmp/platform-threads.txt
```

Distinguish the two file-writing mechanisms: `>` in `Thread.print` causes the **calling shell** to create the file; whereas `<file-path>` in `Thread.dump_to_file` is passed to the **target JVM** so the JVM writes the file itself.

## 7. Limitations, Overhead, and Operational Safety

- **Not a fully synchronized snapshot:** threads may continue progressing while the dump is collected; ordering and stacks do not represent an absolute "stop-the-entire-JVM instant."
- **Size and overhead:** tens of thousands to millions of virtual threads can produce huge files and make dump collection costly in time and resources; avoid rapid-fire collection on an overloaded system.
- **Does not replace traditional dumps:** in JDK 21, this format focuses on thread/stack info and lacks full object address, JNI, heap, monitor/lock details, or automatic deadlock detection provided by some other tools.
- **Security:** class/method names, paths, and runtime info inside dumps can be sensitive. Store files with proper permissions, redact before sharing, and delete according to retention policies.
- **JDK versions:** format, JSON fields, lock presentation, and thread states evolve across releases. Check `runtimeVersion`, `jcmd <PID> help Thread.dump_to_file`, and analysis tool schemas after upgrading the JDK.
- **Existing files:** by default existing files are not overwritten; it is best to use fresh timestamped filenames. Add `-overwrite` only when replacement is genuinely intended.

## 8. Troubleshooting Common Errors

| Symptom | Causes to Check | Resolution |
| --- | --- | --- |
| `Thread.dump_to_file` is unrecognized | Target JVM is too old, does not support the command, or is a non-HotSpot VM | Check `java -version` of the target JVM and `jcmd <PID> help`; use a supporting JDK 21+. |
| `jcmd -l` does not list the PID | JVM is in another container/PID namespace, running as another user, or has exited | Confirm the actual process and run `jcmd` in an environment that can see and attach to the JVM. |
| Attach fails or permission denied | User/group mismatch, attach disabled by config, or OS/container restrictions | Run with valid privileges on the right host/container and check attach policies. |
| Error that file already exists | Default behavior does not overwrite | Pick a new filename; consider `-overwrite` only when overwriting the old copy is acceptable. |
| File not found in Terminal B | The target JVM created the file at its own path | Use an absolute path; check the JVM's filesystem and working directory, especially in containers. |
| `vt-demo-` not found | Pressed Enter too early, wrong PID, or program already exited | Re-run the demo, keep Terminal A open, and dump before `countDown()`. |
| `jq` errors or missing fields | File is incomplete, wrong file selected, or JDK schema differs from expectations | Wait for `jcmd` to finish, inspect `runtimeVersion` and actual structure; do not assume all versions share identical fields. |

## 9. Self-Check

1. Why might `Thread.print` fail to show all waiting virtual threads? **Because virtual threads may have unmounted from their carriers**, while traditional dumps focus on platform threads.
2. How do `-format=plain` and `-format=json` differ? **Plain** is convenient for direct reading; **JSON** is convenient for automated processing and filtering by container/thread/stack.
3. Why might the file not appear in the working directory of the terminal invoking `jcmd`? Because `Thread.dump_to_file` instructs the **target JVM to write the file** using the JVM's own filesystem and working directory.
4. Does a virtual thread stopped at `CountDownLatch.await()` definitely indicate a deadlock? **No**; in this demo it is an intentional wait released upon pressing Enter. Context and multiple snapshots are required.
5. Why keep `runtimeVersion` when parsing JSON dumps? Because thread dump fields and data types can differ across JDK versions.

## References

- [Oracle Java 21 — Virtual Threads, section Viewing Virtual Threads in jcmd Thread Dumps](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Oracle — `jcmd` command (how to list PIDs, run diagnostic commands, and check help)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [Oracle — `jcmd` in newer JDKs, describing `-format`/`-overwrite` options](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Inside Java — numeric field type changes in JSON thread dumps in JDK 27](https://inside.java/2026/05/20/quality-heads-up/)
