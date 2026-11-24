# OS-Level Resource Limits and the Limits of Java Thread Interruption

A Java application capable of loading plugins, running scripts, or executing extension code must solve two distinct problems: **how to request a task to stop**, and **how to ensure running code does not exceed its resource budget**. They cannot substitute for one another.

- `Thread.interrupt()`, `Future.cancel(true)`, and Java-level timeouts belong primarily to **cooperative cancellation**. They can deliver an interruption signal to a task, but they are not mechanisms to forcibly halt arbitrary running bytecode.
- Cgroups, container quotas, OS process/job limits, and OS-level isolation policies are where **ceilings on CPU, memory, process/thread count, file descriptors, disk space, or resource access privileges** are enforced according to platform capabilities.
- `ProcessBuilder` lets the host start and manage the lifecycle of a child process; `Process.destroyForcibly()` can forcibly terminate the process. However, **managing a process timeout does not automatically impose CPU/RAM quotas**, nor does it automatically clean up all descendant processes.

For the **trust boundary** of a Java extensibility mechanism, the principle is: sufficiently trusted code can use `interrupt` to shut down tasks cleanly; untrusted or potentially uncooperative code must be placed inside an **independent process/OS boundary** with quotas, least privilege, and reclamation mechanisms.

This lesson uses Java 17+ and a runnable program to observe: a cooperative thread stopping when interrupted; a task intentionally ignoring interrupts staying alive even though its `Future` reports cancelled; and a child process terminated by the host after a deadline. The examples intentionally bound execution time rather than running infinite loops in the host JVM without a cleanup path.

## 1. Why Do Plugins or Scripts Create Resource Risks?

Suppose a server receives a request and invokes a plugin via SPI:

```text
HTTP request
     |
     v
Host Java server
     |
     v
Plugin API / ScriptEngine / dynamically loaded class
     |
     +--> CPU loop
     +--> Heap and direct memory allocation
     +--> Spawning new threads/processes
     +--> Opening files/sockets
     +--> Calling native libraries or unbounded I/O
```

Even a plugin with no malicious intent can accidentally:

1. Loop infinitely due to a buggy condition.
2. Build unbounded data structures.
3. Hold too many threads, sockets, or file descriptors.
4. Call external APIs that hang.
5. Attempt to access resources outside the scope of its work.

If a plugin runs **in the same JVM** as the host, it shares the process space, heap, and many process resources. A plugin that triggers `OutOfMemoryError` or starves CPU can impact unrelated requests. Sharing a class loader or separating class loaders **does not turn a plugin into a sandbox**.

For externally supplied scripts/plugins, ask about the **trust boundary** before picking timeout APIs. Merely adding `Future.get(2, TimeUnit.SECONDS)` creates no CPU, RAM, or OS privilege limits.

## 2. Three Control Layers — Three Different Guarantees

| Control layer | Typical tools | What can it guarantee? | What should not be expected? |
|---|---|---|---|
| **Java cooperative** | `Thread.interrupt()`, stop flags, `Future.cancel(true)`, interruptible APIs | **Properly written** tasks receive the signal and actively exit and clean up | Forcing code that intentionally ignores interrupts to stop |
| **Process lifecycle management** | `ProcessBuilder`, `Process.waitFor(timeout, unit)`, `destroy()`, `destroyForcibly()` | The host can monitor and terminate the managed **child process** | Automatically enforcing CPU/RAM quotas or guaranteeing all grandchild processes terminate |
| **OS isolation and quotas** | Linux cgroups, namespaces, containers/VMs, Windows Job Objects, process limits, access policies | Limiting/observing resources and privileges within the applied OS/config scope | Automatically capping every Java thread individually per request |

You must further distinguish **wall-clock deadlines** (elapsed time) from **CPU quotas** (CPU time consumed per measurement period). A process blocked on I/O may consume almost no CPU while still exceeding its deadline. A process throttled by a CPU quota can still live forever if the host enforces no timeout.

Similarly, the `-Xmx` heap limit only caps the **Java heap** managed by the JVM; it does not fully cap RSS, metaspace, direct buffers, code cache, native allocations, or thread stacks.

## 3. How Does Java `interrupt` Actually Work?

### 3.1. Interruption Is a Signal, Not a Thread-Kill Command

The call:

```java
worker.interrupt();
```

sends an **interruption request** to a `Thread`. The JVM is not asked to terminate the thread on the spot. The reaction depends on the thread's state and currently executing code:

- If the thread is executing an **interruptible** operation such as `Thread.sleep`, `Object.wait`, `Thread.join`, or certain methods in `java.util.concurrent`, it may throw `InterruptedException`.
- If the thread is running ordinary computational code, interrupting normally only sets the thread's interrupt flag. The code must check the flag and exit on its own at an appropriate point.
- Some I/O/channel or synchronization operations respond to interruption in specific ways, such as closing the channel or throwing a dedicated exception. Never assume every I/O call stops immediately upon interruption.
- If code catches `InterruptedException`, ignores it, and continues looping forever, `interrupt()` **cannot force** it to stop.
- If waiting to acquire a `synchronized` monitor, waiting on the monitor does not become interruptible simply because the thread is interrupted.

Example of a **cooperative** computation loop:

```java
while (!Thread.currentThread().isInterrupted()) {
    processOneBoundedChunk();
}
```

This is an **illustrative snippet**; `processOneBoundedChunk()` must be defined by the application. The critical condition is that each iteration covers a finite amount of work and returns frequently to the check; if an inner call never returns, the outer loop never gets a chance to read the flag.

### 3.2. `isInterrupted()` vs. `Thread.interrupted()`

Two easily confused APIs:

```java
boolean stillSet = Thread.currentThread().isInterrupted();
boolean beforeClearing = Thread.interrupted();
```

- `isInterrupted()` checks the thread object's flag **without clearing** it.
- `Thread.interrupted()` is a static method that checks the **current thread** and **clears the flag** upon reading.

Using `Thread.interrupted()` in a loop condition can accidentally "swallow" the signal if surrounding code also needs to propagate cancellation upward. Inside a task loop, `isInterrupted()` is typically used to check while preserving the signal.

### 3.3. `InterruptedException` and Restoring the Flag

Some blocking operations **clear the interrupt status** when throwing `InterruptedException`. If the handling layer cannot declare `throws InterruptedException` for its caller, the usual pattern is to clean up resources and **re-set the flag** so higher layers see the cancellation request:

```java
try {
    Thread.sleep(1_000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

In a method already declaring `throws InterruptedException`, you can let the exception propagate after appropriate cleanup without necessarily restoring the flag only to rethrow.

Do not do this:

```java
// ANTI-PATTERN: swallowing interrupt and continuing forever.
try {
    Thread.sleep(1_000);
} catch (InterruptedException ignored) {
    // Keep running despite cancellation request.
}
```

The demo in section 7 **intentionally** uses this anti-pattern in a bounded task to prove why interruption must never be treated as an enforcement mechanism.

### 3.4. Resources Still Need Cleanup

If a task opened files, connections, locks, or registered callbacks, responding properly to an interrupt is more than just `return`. Depending on business logic, use `try/finally`, `try-with-resources`, and suitable rollback/compensation strategies:

```java
try {
    doWorkWithResource();
} finally {
    closeOrReleaseResource();
}
```

This is **conceptual code**, not standalone runnable Java; `doWorkWithResource` and `closeOrReleaseResource` stand for business operations. Avoid cleanup calls without deadlines that might hang indefinitely while the system is trying to cancel.

## 4. Timeout/Cancel APIs Are **Not** Execution Quotas

Several very common misconceptions:

| API | Actual meaning | Limit to remember |
|---|---|---|
| `Future.get(2, SECONDS)` | The thread **calling `get`** waits at most the specified duration | Timeout does not stop the running task |
| `Future.cancel(true)` | Attempts to cancel the `Future`, **may request an interrupt** if already running | `isCancelled()==true` does not prove the code exited |
| `Future.cancel(false)` | Cancels the Future state without requesting interruption of a running thread | Running work may continue |
| `ExecutorService.shutdownNow()` | Attempts to stop active tasks and halt queued ones | Usually acts via interrupt; **no guarantee** every task terminates |
| `Thread.join(timeout)` | The thread calling `join` waits up to a limit | The waited-on thread is not killed when time expires |
| `CompletableFuture.orTimeout(...)` | Completes the future exceptionally on timeout if no result yet | Does not stop work in the executing thread |
| `CompletableFuture.cancel(true)` | Transitions completion state to cancelled | For `CompletableFuture`, `mayInterruptIfRunning` **does not control interrupting the task** like executor Futures |

**The `cancelled` flag is a state of the `Future` abstraction, not an OS thread liveness check.** If a plugin intentionally ignores the interrupt flag, a `Future` may already be cancelled while the execution thread still holds CPU, memory, or locks.

Never use `Thread.stop()` as a workaround. This API is unsafe: abrupt termination can leave objects in inconsistent states and break synchronization invariants. In modern JDKs it is further restricted; it is not a reliable plugin-killing mechanism.

### `synchronized`, I/O, and Native Code

A task may fail to respond promptly to an interrupt even when the developer wrote flag checks. For example:

- A computation loop processes one very long chunk without returning to the checkpoint.
- The thread waits to enter a `synchronized` monitor held by another thread.
- An older native/driver API lacks clear cancellation support.
- A network/disk call has no configured timeout or has different interrupt semantics than expected.
- Code holds a lock in a way that blocks cleanup or shutdown from proceeding.

When deadlines must be met, prefer **APIs with built-in timeouts** (socket connect/read timeouts, HTTP client deadlines, database statement timeouts, `Lock.lockInterruptibly()`, etc.) alongside interruption. Yet for **untrusted code**, both must still sit behind an enforced process/OS execution boundary.

## 5. Why Can't You Enforce Reliable CPU/RAM Quotas for a Plugin Using Just a Thread?

Multiple Java plugins loaded in the same JVM typically share:

- One **Java heap**, where plugin and host objects are allocated together.
- Metaspace/class metadata, JIT code cache, and other native regions.
- File descriptors, sockets, environment variables, system properties, and process resources.
- Native libraries or singletons/static state tied to class loaders.
- CPU budgets and process-level limits applied by the OS to **the entire JVM**.

No standard Java SE 17 API lets you declare: "Plugin A's thread may allocate at most 64 MiB of heap; if exceeded, kill only thread A and safely reclaim all its objects." Interrupting a thread does not roll back executed bytecode, undo side effects, or unwind object graphs automatically.

`ThreadMXBean` or profiling tools can help **measure** per-thread CPU time under supported conditions, but measurement does not mean an OS quota is enforced. A Java monitor can detect budget overruns and request stopping, yet it still relies on cooperative code.

### `-Xmx` Is Not a Total Memory Limit

For example:

```bash
java -Xms64m -Xmx192m -jar plugin-runner.jar
```

`-Xmx192m` sets the maximum Java heap size of that JVM. **It does not cap total RSS at 192 MiB**, nor does it individually cap one script inside the process. The JVM also uses metaspace, direct buffers, stacks, JIT, JNI, and the OS memory allocator.

If a container/process has a memory limit lower than total demand, the process can be killed by the OS upon exceeding the quota. In that case, **never expect Java to always catch `OutOfMemoryError` and run `finally`/cleanup**. Worker resources must be designed so the OS can reclaim them while the host survives.

## 6. Resource Limits to Enforce at the OS Level

| Budget type | Sources of consumption | Environment-specific controls | Key observation |
|---|---|---|---|
| **CPU** | Computation, JIT, loops | Cgroup CPU quotas, container limits, Windows Job CPU controls | CPU quotas reduce throughput; deadlines must still be tracked separately |
| **RAM / memory** | Heap, metaspace, direct/native memory, stacks | Cgroup/container memory limits, Job memory limits | Limits apply to the process/group; `-Xmx` is only one piece |
| **Process/thread count** | Unbounded thread, process, or subprocess creation | Cgroup `pids.max`, container `--pids-limit`, Job process controls, RLIMITs | Child processes must remain inside the bounded group |
| **File descriptors / handles** | Files, sockets, pipes, many open files | `RLIMIT_NOFILE`, OS/container policies, Windows handle monitoring/limits | Unclosed resources can break the entire worker |
| **Disk / I/O** | Logs, temp files, caches, uploads | Filesystem quotas, tmpfs size, container storage policies, I/O controllers | A read-only filesystem differs from space quotas; bound temp files |
| **Network** | HTTP, internal connections, data access | Network namespaces, firewall/egress policies, service identities | CPU/RAM limits do **not** stop reading data over the network |
| **Execution time** | Hung tasks, sleeps, I/O waits | Supervisor deadlines + process termination | Cannot be replaced by CPU quotas if the process is blocked |
| **Rate/frequency** | Bursts of parallel tasks | Admission control, queue caps, rate limits | Block excess workers before the system runs out of resources |

Each mechanism has its own scope. For example, container-level limits apply to processes **inside that container**; if a plugin can call external services or trigger side effects, resources and privileges of those external systems must be governed separately.

### Linux: Cgroups and Namespaces

On modern Linux systems, **cgroups** provide resource controllers at the process-group level, such as:

```text
memory.max   -> cgroup memory ceiling
cpu.max      -> periodic CPU quota
pids.max     -> ceiling on processes/tasks in cgroup
io.max       -> throttling for certain block I/O
```

These are **illustrative** cgroup v2 interface names, not files you should arbitrarily write to directly from the host. Configuration should normally be delegated to a container runtime or service manager with proper privileges and lifecycle management.

**Namespaces** separate scopes like process IDs, mounts, and networking; **seccomp**, AppArmor/SELinux, and OS permissions add behavioral constraints. Cgroups are only resource quotas, **not a complete security mechanism**.

### Windows: Processes and Job Objects

On Windows, **Job Objects** can group processes and apply limits supported by the OS (such as memory/process counts or certain CPU policies), and configure cleanup when the job ends. Using Job Objects generally requires native APIs/orchestration; Java SE's `ProcessBuilder` **does not automatically create a quota-enforced Job Object**.

Do not try to replace job policies with a separate "watchdog" Java thread: if the host JVM fails, that watchdog thread may stop running too.

### Deployment-Oriented Container Configuration Example

After packaging a **verified** worker into an image, a Linux Docker deployment command might look like:

```bash
docker run --rm \
  --cpus=1 \
  --memory=256m \
  --memory-swap=256m \
  --pids-limit=64 \
  --network=none \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  --user=65534:65534 \
  my-plugin-runner:17
```

This is an **illustrative configuration sample**, not a command for the Java demo, and cannot run without a compatible `my-plugin-runner:17` image, runtime, and privilege policy. Values like `256m`, `64`, and `1 CPU` are **example** budgets that must be validated against real workloads. Some flags and enforcement levels depend on the Linux kernel, cgroup mode, runtime, and daemon privileges.

Reading the flags:

- `--cpus=1`: caps the container's CPU budget.
- `--memory=256m`: sets a memory ceiling enforced by the container runtime via platform mechanisms.
- `--memory-swap=256m`: in supported configurations, caps total memory+swap at the memory limit; do not assume every host enforces swap identically.
- `--pids-limit=64`: caps tasks/processes inside the container per runtime configuration.
- `--network=none`, `--read-only`, `--tmpfs`: restricts networking and ordinary filesystem writes; mounts/host sharing and special privileges still need evaluation.
- `--cap-drop=ALL`, `--security-opt=no-new-privileges`, `--user=...`: drops privileges; does not remove the need for seccomp/policies and real isolation.

A container **is not automatically an absolute sandbox**. For code with very low trust, consider stronger boundaries such as microVMs/VMs, separate hosts and identities, alongside egress, secrets, and input policies.

## 7. Java 17 Example: Cooperation, Ignoring Interrupts, and Process Deadlines

We write a single program `RuntimeBoundaryDemo.java`, **requiring no external libraries**. It runs three controlled experiments:

1. A thread sleeping in a loop catches `InterruptedException`, restores the flag, and exits: **cooperative cancellation**.
2. A task in an `ExecutorService` intentionally swallows `InterruptedException`. After `Future.cancel(true)`, the Future reports cancelled yet the task **remains alive**. Then the host sets an explicit stop flag to clean up and end the test.
3. Spawns a **child JVM** via `ProcessBuilder`; if it exceeds 300 ms, the host stops the process with `destroy()` and escalates to `destroyForcibly()` if needed. This is **process deadline management**, not RAM/CPU quota enforcement.

The program is designed **never to leave the interrupt-ignoring task running forever** after the demo. It reclaims the task using the stop flag and waits for the executor to shut down. The child worker in `"child"` mode sleeps for a long time, yet is always handled by the host in the `finally` branch during normal execution. If the host is killed abruptly, `finally` cleanup is not an OS guarantee; production systems need appropriate process groups/cgroups/Job Objects.

### 7.1. Complete Source Code

File `RuntimeBoundaryDemo.java`:

```java
import java.nio.file.Path;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class RuntimeBoundaryDemo {
    private static void interruptibleWorker() throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        Thread worker = new Thread(() -> {
            started.countDown();
            try {
                for (;;) {
                    Thread.sleep(1_000);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "cooperative");

        worker.start();
        started.await();
        worker.interrupt();
        worker.join(2_000);
        if (worker.isAlive()) {
            throw new IllegalStateException("Cooperative worker did not stop");
        }
        System.out.println("Cooperative interrupt stopped thread: true");
    }

    private static void ignoringInterruptWorker() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        AtomicBoolean stop = new AtomicBoolean(false);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);

        try {
            Future<?> future = executor.submit(() -> {
                started.countDown();
                try {
                    while (!stop.get()) {
                        try {
                            Thread.sleep(100);
                        } catch (InterruptedException ignored) {
                            // DEMO ONLY: intentionally ignore cancellation.
                        }
                    }
                } finally {
                    finished.countDown();
                }
            });

            started.await();
            future.cancel(true);
            System.out.println("Future cancelled: " + future.isCancelled());
            System.out.println("Ignored interrupt task still alive: "
                    + (finished.getCount() != 0));

            stop.set(true);
            executor.shutdownNow();
            if (!executor.awaitTermination(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Demo executor did not stop");
            }
            System.out.println("Explicit stop flag ended task: "
                    + (finished.getCount() == 0));
        } finally {
            stop.set(true);
            executor.shutdownNow();
        }
    }

    private static void timedChildProcess() throws Exception {
        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win");
        Path javaExecutable = Path.of(System.getProperty("java.home"),
                "bin", windows ? "java.exe" : "java");

        Process process = new ProcessBuilder(
                javaExecutable.toString(),
                "-cp", System.getProperty("java.class.path"),
                RuntimeBoundaryDemo.class.getName(), "child")
                .redirectOutput(ProcessBuilder.Redirect.DISCARD)
                .redirectError(ProcessBuilder.Redirect.DISCARD)
                .start();

        try {
            boolean timedOut = !process.waitFor(300, TimeUnit.MILLISECONDS);
            if (!timedOut) {
                throw new IllegalStateException("Child ended unexpectedly");
            }
            System.out.println("Child process timed out: " + timedOut);

            process.destroy();
            if (!process.waitFor(2, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                if (!process.waitFor(3, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Child still alive");
                }
            }
            System.out.println("Child process stopped: " + !process.isAlive());
        } finally {
            if (process.isAlive()) {
                process.destroyForcibly();
                process.waitFor(3, TimeUnit.SECONDS);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("child")) {
            for (;;) {
                Thread.sleep(60_000);
            }
        }
        interruptibleWorker();
        ignoringInterruptWorker();
        timedChildProcess();
    }
}
```

### 7.2. Compiling and Running

Requires **JDK 17 or newer**; in the directory containing `RuntimeBoundaryDemo.java`, run:

```bash
javac --release 17 -encoding UTF-8 RuntimeBoundaryDemo.java
java RuntimeBoundaryDemo
```

Both commands work on Linux, macOS, and Windows PowerShell when `java`/`javac` are in `PATH`. When executed, Java spawns a child JVM using the executable in `java.home`; thus the environment must permit spawning child processes.

### 7.3. Standard Stdout

When the environment permits starting and terminating processes normally:

```text
Cooperative interrupt stopped thread: true
Future cancelled: true
Ignored interrupt task still alive: true
Explicit stop flag ended task: true
Child process timed out: true
Child process stopped: true
```

The program intentionally prints booleans instead of PIDs/exit codes, because PIDs, exact timings, exit codes, and termination signals depend on the operating system.

If child processes cannot be spawned, or the host is suspended/interfered with causing `waitFor` to return differently, the program may throw an exception; the lines above represent the **successful execution path**, not a guarantee every machine can always run it. A real runtime environment must be able to spawn, monitor, and terminate child JVMs.

## 8. Interpreting the Experiment: Why Are the Results Like This?

### 8.1. Cooperative Thread

`interruptibleWorker()` creates a thread and waits on a `CountDownLatch` confirming the thread started. It sends `interrupt()` and waits up to two seconds via `join(2_000)`. If the thread is still alive, it throws an error.

`Thread.sleep` responds to interruption with `InterruptedException`. The worker stops looping, restores the flag, and reaches the end of the lambda to finish. **Here the thread stopped because the code actively exited**, not because the JVM killed the thread.

For a real worker, put cleanup logic in `finally` and let interruption propagate according to your API design.

### 8.2. `Future` Cancelled Yet Task Still Running

The second task loops on `while (!stop.get())`. It intentionally catches `InterruptedException` and **does not exit**, so `future.cancel(true)` has no authority to force the loop to end.

After `future.cancel(true)`, the program observes:

```text
Future cancelled: true
Ignored interrupt task still alive: true
```

In the example, `CountDownLatch finished` only decrements when the task **truly finishes**. Checking `finished.getCount() != 0` differs from `future.isCancelled()`. This avoids conflating `Future` status with the liveness of the underlying work.

Once the host sets `stop.set(true)` and calls `shutdownNow()`, the task has a clear exit path; `awaitTermination(...)` lets us verify the executor stopped within budget. In real code, `shutdownNow` still only attempts to interrupt, so it cannot replace a stop flag for a worker that intentionally ignores interrupts.

**Do not copy this anti-pattern into production tasks.** Well-behaved tasks must respect interrupts, exit paths, and cleanup; the anti-pattern merely demonstrates the limits of cancellation in Java.

### 8.3. A Separate Process Is an Independently Terminable Unit

`timedChildProcess()` starts the same program in `"child"` mode inside **a separate JVM**. The child worker waits inside a long `Thread.sleep(...)` loop; it never receives `Thread.interrupt()` from the host JVM.

The host monitors:

```java
boolean finished = process.waitFor(300, TimeUnit.MILLISECONDS);
```

In the full code, equivalent logic is written as `timedOut = !process.waitFor(...)`. Timing out only indicates **the host finished waiting**; `waitFor(timeout)` itself does not kill the process.

The host then **proactively** calls `destroy()` and, if the process fails to exit in time, escalates to `destroyForcibly()` followed by `waitFor(...)` to confirm termination. Signal/termination details depend on the OS. The code has a `finally` block to attempt process cleanup if errors arise during handling.

**Example limitation:** there is only one child process and it spawns no grandchildren. For a process that spawns subprocesses, `Process.destroyForcibly()` on the parent PID does not guarantee the entire process tree terminates. In real systems, place the plugin's process group under an appropriate OS cgroup/Job Object/container and clean up **the whole group** on expiration.

## 9. Separating Deadlines from Quotas in Supervisor Design

A plugin supervisor should have two independent control layers:

```text
                       Host (trusted)
                             |
                    Submit plugin work
                             |
                             v
                  Admission / rate limit
                             |
                             v
                    Create worker process
                   (OS quota & least privilege)
                             |
                 +-----------+-----------+
                 |                       |
             Monitor wall time      Monitor health
                 |                       |
            Deadline over?        Memory/CPU/PIDs signals
                 |                       |
                 +-----------+-----------+
                             |
                Graceful stop if possible
                             |
                    Wait bounded grace
                             |
                  Terminate worker group
                             |
                   Reap/verify cleanup
                             |
                Return timeout / failure
```

Limits to decide based on workload:

- **Wall time:** e.g., 2 seconds for a short calculation; whether that includes queue wait time or only execution time must be clearly defined.
- **CPU budget:** can be bounded via OS CPU quotas, though quotas do not automatically kill a process upon exceeding a total CPU time unless the monitor also defines an enforcement action.
- **Memory:** pick a cgroup/job limit sufficient for the whole JVM (heap + native + thread stacks), aligning `-Xmx` with total memory. If total memory is too close to `-Xmx`, the worker can be OS-killed before the JVM reports OOM.
- **PIDs/threads:** account for native threads/JVM worker threads, subprocesses, and worker counts in the same group.
- **I/O/temporary files:** use dedicated temp directories, storage quotas, and restricted mounts; avoid letting plugins write freely into host directories.
- **Network:** deny unnecessary egress by default; when external APIs are permitted, enforce timeouts, allowlists, and secret scoping.
- **Cleanup:** after a timeout, never let a new request reuse a worker in an unknown state. You may choose to discard the whole process and spawn a fresh worker.

OS resource limits **only take effect if the worker is actually placed within the limited scope**. Launching `java -jar plugin.jar` via `ProcessBuilder` without attaching an appropriate cgroup/Job Object **creates no automatic quotas**.

### Why Isn't a Thread Pool in the Host Enough?

An `ExecutorService` limits **the number of queued/running tasks** via thread counts and queue capacity, yet **does not cap per-task memory** and **cannot forcibly stop uncooperative code**. A hung task can pin a pool slot, connection, or lock; once the pool is exhausted, other requests suffer too.

Even increasing thread count to compensate can worsen the situation due to higher process-level resource usage. Admission control, bounded queues, and worker process boundaries are needed for untrusted code.

## 10. Designing Trust Boundaries by Level of Code Control

| Code category | Usually appropriate structure | Warning |
|---|---|---|
| Reviewed, tested internal business logic | Same JVM, `ExecutorService`, interrupts/timeouts on relevant APIs | Bugs can still cause OOM or hang the process |
| Trusted partner plugin with complex dependencies | Consider a separate process to isolate faults and dependencies; clear SPI/protocol | Separating class loaders alone does not protect CPU/RAM |
| Internal-user scripts with bounded privileges | Depending on risk, dedicated worker process, restricted APIs, quotas, deadlines | `ScriptEngine`/Bindings are not a sandbox |
| Untrusted Java/scripts from the Internet | Strongly isolated process/container/VM, least privilege, no secrets, OS quotas, network policies | Never run directly in the host JVM relying solely on `Thread.interrupt()` |

The goal is separating **fault containment** from **API extensibility**. SPI/`ModuleLayer`/`ClassLoader` solve wiring and code loading; container/OS policies solve resource and privilege safety. They can be combined, but cannot substitute for one another.

### A Process Boundary Requires a Protocol

When a plugin runs in another JVM, the host cannot simply pass a Java object from the host's class loader and invoke methods directly across processes. A contract-based communication protocol is required, such as:

```text
Host Java  --request ID + JSON/Protobuf-->  Worker Java
Host Java  <--status + result/error-------  Worker Java
```

Depending on complexity, you can use framed stdin/stdout, local sockets, gRPC, or message queues. The protocol should define versioning, size limits, deadlines, cancellation requests, access controls, and idempotency policies.

If a plugin performs side effects such as database writes or sending emails, **killing the process does not automatically roll back external transactions**. On timeout, the host may not know whether the operation succeeded; design idempotency keys, request states, and reconciliation mechanisms instead of blind retries.

## 11. Proper Lifecycle When a Worker Exceeds Its Deadline

A practical workflow:

1. **Create resource group:** container/cgroup/Job Object/worker process with least privilege and quotas.
2. **Register deadline:** start counting from a defined point (request receipt, execution start, or post-warm-up).
3. **Send cooperative cancel:** if supported by the protocol, ask the worker to stop; allow a finite grace period.
4. **Track liveness:** do not look only at `Future.isCancelled()` or client-side timeouts; verify whether the process/group is still alive.
5. **Forcible termination:** terminate/kill the **worker group** via the appropriate OS mechanism once grace expires.
6. **Clean up:** close pipes, handles, temp files, remove the worker from registries, and return quotas/slots; avoid zombies/leaks.
7. **Report status:** timeouts, resource-limit kills, child process errors, and client cancellations are distinct causes.
8. **Prevent bad retries:** retain request IDs and idempotency semantics when outcomes are uncertain.

A `finally` block in the host is necessary but insufficient if the host itself crashes. To guarantee cleanup even if the supervisor dies, use lifecycle controls from the OS or container orchestrator with appropriate policies.

### Check the Entire Process Tree

Java provides `ProcessHandle` and `ProcessHandle.descendants()` to **observe** child/descendant processes at a point in time, yet listing descendants is only a snapshot: the process tree can mutate while cleaning up. You cannot assume `destroyForcibly()` on one PID guarantees all descendants die.

When reliable forcible cleanup is required, organize workers inside an OS-controlled **process group/cgroup/container/Job Object** and terminate the entire group using platform operations. Never allow a worker to escape its group or spawn higher-privilege processes unless policy permits.

## 12. Failure Types and Monitoring Signals to Distinguish

| Event | Symptom | Suggested action |
|---|---|---|
| Cooperative thread receives interrupt | Task exits via `InterruptedException` or stop flag | Clean up, return cancelled status |
| Future timeout | Calling thread stops waiting; task may still be running | Decide on cancellation and confirm task completion |
| Future cancelled yet thread continues | `isCancelled=true` while worker keeps running | Do not equate Future status with a kill; use process boundaries for untrusted code |
| Process exceeds deadline | `waitFor(timeout)` returns `false` | Send terminate, wait grace, force kill, and verify |
| Memory quota exceeded | Worker may be killed by OS/container | Record OOM signals from orchestrator/cgroup; do not assume Java cleanup ran |
| CPU quota exhausted | Worker throttled or slowed down | Monitor throttling, deadlines, and sizing |
| PIDs/threads exhausted | Spawning new threads/processes fails | Cap concurrency, handle resource errors, adjust budgets |
| Too many file descriptors | `Too many open files` or I/O failures | Track leaks, configure limits, and clean up |
| Worker makes unauthorized network call | Access blocked by policy | Verify network namespace/firewall and identity; audit |
| Worker dies mid-operation with side effects | Host unsure if operation committed | Query/trace state, idempotency, reconciliation |

Do not hard-code a single exit code like `"137"` as the sole indicator of OOM. Platforms/container runtimes report kills in multiple ways; read **orchestrator state, cgroup events, logs, and process info** together.

Similarly, the absence of exceptions in Java logs **does not prove** there was no failure: an OS kill can terminate the process without letting the JVM run shutdown hooks or `finally`.

## 13. Common Design Mistakes

| False assumption | Why is it wrong? | Better approach |
|---|---|---|
| "`Thread.interrupt()` kills any thread" | Interrupt is a cooperative signal | Design checkpoints/cancellation and process boundaries for uncooperative code |
| "`Future.cancel(true)` returning true means the task stopped" | Future status does not reliably reflect thread state | Track task completion, resources, and process liveness |
| "`get(timeout)` cancels the running work" | It only bounds how long the caller waits | Call cancel and perform verified shutdown |
| "`shutdownNow()` can kill any task" | It only attempts interruption | Restrict to cooperative tasks or use OS process termination |
| "`Thread.stop()` is a safe last resort" | Can break invariants and skip cleanup | Do not use; design cooperative cancellation/process isolation |
| "`-Xmx` caps total memory" | Native, stacks, metaspace, and direct buffers remain | Set OS memory limits and size heap within that budget |
| "Separating class loaders separates privileges, CPU, and heap" | Loaders remain in the same process | Use OS/container/VM boundaries with least privilege |
| "`ProcessBuilder` creates a cgroup/quota automatically" | New processes do not automatically get individual quotas | Supervisor/orchestrator must attach workers to proper quotas |
| "Killing the parent PID cleans up all grandchildren" | Descendants may stay alive | Manage the entire worker group via the OS |
| "A container with a memory limit is safe enough" | Networking, filesystem, privileges, and syscalls remain | Combine namespaces, seccomp/MAC, least privilege, and egress policies |
| "Any request can be retried after a timeout" | External operations may already have committed | Define idempotency and uncertain outcomes |
| "Having interrupt checks removes the need for I/O timeouts" | API calls may block and never return to check the flag | Configure API-level timeouts and external deadlines |
| "Closing a thread reclaims all memory" | Objects may stay referenced; native resources have separate lifecycles | Manage resource lifetimes or terminate the worker process |

## 14. Tests to Run in a Safe Environment

Build an **isolated test worker with low quotas** and verify these scenarios:

1. **Cooperative task:** a task sleeping/waiting on a queue gets interrupted, exits cleanly, and closes resources; thread is no longer alive after deadline.
2. **Interrupt-ignoring task:** Future is cancelled yet task keeps running; supervisor can still terminate the worker process cleanly.
3. **Busy CPU loop:** bounded-duration test workload observing CPU throttling and deadlines; **do not** run unbounded loops without process quotas.
4. **Over-budget memory:** test only inside an environment with verified memory limits and reclamation; record whether the worker is OS-killed or throws OOM per platform.
5. **Many threads/processes:** use bounded workloads to verify PID/thread quotas and admission control; do not run unbounded fork programs.
6. **Slow I/O:** test read/connect timeouts, socket cleanup, and handling of abandoned requests.
7. **Worker spawning subprocesses:** verify whether terminating the worker cleans up the whole OS group.
8. **Host supervisor restart/crash:** verify orphaned workers are tracked and reclaimed by the orchestrator/Job Object/cgroup.
9. **Side effects on timeout:** prove retries with an idempotency key do not double-write.
10. **Concurrent other tenants:** a killed/OOMed plugin does not starve other tenants' requests or leak data when properly isolated.

All resource-limit tests should occur on dedicated test machines/containers with appropriate permissions; avoid shared production environments or trying to overload the host "to see if limits work" without isolation in place.

## 15. Trust Boundary Implementation Checklist for Java Runtime Extensibility

Before allowing plugins/scripts to run:

- **Trust:** who supplies the code, and what access does it have to secrets/network/host filesystem?
- **Boundary:** same JVM, separate class loader, separate process, container, or VM? Is the rationale strong enough?
- **Quota:** are CPU, RAM, PIDs, disk/tmpfs, FDs/handles, network, and concurrent request counts controlled at the right scope?
- **Timeout:** where does the deadline start, how long is the grace period, and who kills the worker group when grace expires?
- **Concurrency:** are queues and worker counts bounded so scaling workers cannot exceed the total host budget?
- **Cancellation:** do tasks check interrupts, clean up resources, and propagate cancel signals across the protocol where possible?
- **Process cleanup:** do you know which processes/subprocesses belong to a worker, and verify termination afterward?
- **Heap sizing:** is `-Xmx` chosen well below the OS memory limit, leaving room for native memory?
- **Isolation:** are least privilege, seccomp/AppArmor/SELinux/Job policies applied per environment, blocking unnecessary mounts/egress?
- **Recovery:** when a process dies, does the system distinguish timeouts, crashes, OOMs, and manual cancellations, avoiding blind retries of side effects?
- **Observability:** are deadlines, CPU throttling, memory highs/OOMs, task counts, and process states tracked with non-sensitive request IDs?
- **Tests:** have cooperative code, interrupt-ignoring code, and cleanup failures been tested in an isolated environment?

## 16. Reinforcement Exercises

1. **Understanding interrupts:** in the demo, replace the second task's `catch (InterruptedException ignored)` with `Thread.currentThread().interrupt(); return;` and observe how `finished` changes. Why can `Future.cancel(true)` then make the task exit cleanly?
2. **Understanding `Future`:** call `future.cancel(false)` on an already-running task and observe why cancelled status does not mean an interrupt request reached the worker.
3. **Understanding timeouts:** remove `process.destroy()` and `destroyForcibly()` in a **test run supervised externally**. Predict whether `waitFor(300ms)` stops the child on its own; never leave a hung worker behind after testing.
4. **Estimating memory:** a JVM has `-Xmx=192m`, metaspace, direct buffers, thread stacks, and native libraries. Explain why container `--memory=192m` may be insufficient.
5. **Choosing OS limits:** for a worker needing no network that only receives JSON and returns JSON, propose file/network permissions and memory/CPU/PIDs limits.
6. **Managing process trees:** suppose a plugin spawns a subprocess. Compare killing the parent PID against killing the entire worker group via cgroups/Job Objects; which fits cleanup requirements?
7. **Distinguishing responsibilities:** label each item as Java cooperative, supervisor deadline, or OS quota: `Thread.interrupt`, `Future.get(timeout)`, `Process.destroyForcibly`, cgroup `memory.max`, Windows Job Objects, network namespace.
8. **Protocol design:** add deadlines, request IDs, `COMPLETED/TIMED_OUT/FAILED/CANCELLED` statuses, and idempotency keys to the host↔worker protocol.

**Conclusion:** `Thread.interrupt()` is a **cooperative request mechanism**; Future timeouts/cancellations are not thread-kill switches; `ProcessBuilder` is a **process lifecycle mechanism** that does not impose resource limits on its own; and **OS quotas together with process isolation** form the foundation of reliable resource boundaries when running untrusted plugins or scripts. Never entrust protecting the host from uncooperative code to an interrupt flag inside the very JVM under threat.
