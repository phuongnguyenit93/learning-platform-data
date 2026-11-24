# 8.3 Reading thread names, Java thread IDs, native IDs, states, and stack frames

A **thread dump** is a point-in-time snapshot of the threads and call stacks observable by the JVM. When a Java 17+ service is slow, hangs, grows in thread count, or appears to use abnormal CPU, a thread dump helps answer: which threads are doing what; whether a thread is waiting on a monitor/condition/I/O or running code; which thread holds a lock; and which code segment a particular stack frame maps to.

Reading a dump correctly requires distinguishing at least **four kinds of information**: **thread name** (a label assigned by the program/JVM), **Java thread ID** (an identifier within the JVM), **native thread ID** (the operating-system thread identifier, if exposed by the implementation), and **state and stack frames**. On HotSpot, the `tid` field in the header is the address of an internal thread structure — **not** the Java thread ID and **not** the native thread ID. A small mix-up here can cause you to track the wrong thread in `top -H` or conclude that a Java thread is hung when it is simply waiting for work in a thread pool.

This Knowledge lesson focuses on **reading and interpreting**, rather than expanding into a full guide to all profiling tools. The illustrated commands apply to HotSpot/OpenJDK 17 when sufficient permissions are present. **Always verify the exact PID, JVM start time, and container namespace before taking a dump**; the data may contain internal paths, task names, endpoints, class names, and sensitive information.

## 1. Thread dump reading goals

After this lesson, you should be able to:

- Parse a thread's header: name, thread number like `#n`, `daemon`, `prio`, `os_prio`, `tid`, `nid`, state description, and CPU/elapsed if present.
- Explain Java `Thread.State`: `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, `TERMINATED` and their limits compared to OS scheduler states.
- Read frames in order where **the top is the most recent method**, and below are the callers; understand `Native Method`, `Unknown Source`, file/line numbers, and frames from Java libraries/frameworks.
- Recognize synchronization lines such as `- waiting to lock`, `- locked`, `- parking to wait for`, and `Locked ownable synchronizers`.
- Convert hexadecimal `nid` to a decimal native thread ID on Linux to correlate with `top -H` or `ps -L`, while avoiding confusion between `tid` and `Thread.getId()`.
- Use `ThreadMXBean` in Java 17 to read Java thread ID/name/state/frames and know that this standard API does not provide `nid`.
- Collect multiple dumps with timestamps/instance identities, group stacks, and verify hypotheses using metrics, JFR, GC logs, and OS counters instead of diagnosing from a single line.

## 2. Where do thread dumps come from?

### 2.1. Common methods on HotSpot/OpenJDK 17

With an example PID `12345` of the exact JVM to investigate:

```bash
# List JVMs visible to the tool.
jcmd -l

# Print Java thread dump, including java.util.concurrent lock info.
jcmd 12345 Thread.print -l

# Alternative command if the JDK includes jstack and the action is approved.
jstack -l 12345
```

`jcmd 12345 Thread.print -l` is the common choice; the `-l` option requests additional information about `java.util.concurrent` locks. According to JDK 17 documentation, `Thread.print` has **Medium impact**, depending on the number of threads. It is not a free “file read”: the JVM must collect stack/lock information, which can briefly slow down the application, especially with very many threads.

Some systems allow sending the `SIGQUIT` signal (Linux/Unix) so the JVM prints a dump to the output/log stream managed by the process. For example, `kill -QUIT <pid>` has specific meaning on HotSpot/Linux; **only use it when you know the signal handling, output destination, and operational procedures**. Do not treat `SIGQUIT` as a portable operation across all JVMs/OSes.

`jstack` can be useful, but JDK 17 documentation describes it as an experimental/unsupported tool. For a running JVM, prefer `jcmd` and management/JFR capabilities suitable for the actual runtime. Do not trigger dumps continuously across an entire cluster.

### 2.2. Targeting the right instance and attaching timestamps

Before reading the contents:

1. Confirm service, hostname/node, pod/container ID, **PID in the right namespace**, JVM start/uptime, build version, or image digest.
2. Record the UTC timestamp when collection starts and any necessary timestamps when collection finishes.
3. Verify the command is supported via `jcmd <pid> help Thread.print` if the tool is available in the environment.
4. Choose sample count based on incident duration and allowable impact: for example, three dumps a few seconds apart **when authorized**, rather than continuous polling.
5. Save in a location with restricted permissions and clear retention; do not post raw dumps directly into public issues/chats.

Example of redirecting the tool's stdout to a file **when the destination directory has been granted secure permissions beforehand**:

```bash
jcmd 12345 Thread.print -l > thread-20261029T081500Z.txt
```

The filename above is illustrative only. This operation writes output to the filesystem **where the tool is running**, not automatically inside the target JVM. Output can differ in headers, timestamps, thread counts, and frames across JDKs/vendors. Only target the exact PID; in containers, `jcmd -l` is not guaranteed to see JVMs in other namespaces.

### 2.3. A thread dump differs from an exception stack trace

| Source | Scope | What can it answer? |
| --- | --- | --- |
| JVM thread dump | Many live threads at capture time, plus JVM-specific data | “Where are the threads right now and what are they waiting on?” |
| Exception stack trace | Call path at the moment the exception was thrown/recorded | “Where did the exception originate and through which calls did it pass?” |
| `Thread.currentThread().getStackTrace()` | The single thread calling the API | “Where has this thread called into right now?” |
| `ThreadMXBean.getThreadInfo(...)` | Selected threads, with requested stack depth | Programmatic management diagnostics, Java ID/state/locks |
| JFR/profiler | Sequence of events or samples over time | “How did CPU, locks, allocations, and latency change?” |

An exception at 08:10 and a thread dump at 08:20 **cannot** be assumed to represent the same stack without correlating evidence. A thread dump is a **snapshot**, not the complete call history of a thread.

## 3. Structure of a HotSpot thread dump entry

An **illustrative composite example** (hex values, paths, and timings are not from a real JVM):

```text
"checkout-worker-7" #42 daemon prio=5 os_prio=0 cpu=220.12ms elapsed=31.01s
   tid=0x00007f1020032000 nid=0x2a3f waiting for monitor entry
   [0x00007f100abcc000]
   java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.PaymentService.charge(PaymentService.java:118)
    - waiting to lock <0x0000000700a01234> (a java.lang.Object)
    at com.example.CheckoutController.pay(CheckoutController.java:54)
    at java.base/java.lang.Thread.run(Thread.java:833)
```

In a real dump, the header may be on **a single line** and have a different attribute order. Fields like `cpu=...`, `elapsed=...`, or the address bracket `[...]` depend on version and output format. **Do not build a production parser using a single regex assuming every HotSpot/JDK prints identically to the example**.

Reading from the outside in:

| Component | Example | Accurate interpretation |
| --- | --- | --- |
| Name | `"checkout-worker-7"` | Label assigned by Thread/Executor/JVM; may duplicate or change |
| `#42` | `#42` | Thread number/ID represented by HotSpot in the header; often used to identify the Java thread; verify by version, do not confuse with `tid` |
| `daemon` | `daemon` | Daemon thread; omitting the keyword usually means non-daemon in that format |
| `prio=5` | `prio=5` | Reported Java thread priority; not a CPU percentage |
| `os_prio=0` | `os_prio=0` | Priority mapped to native/OS scheduling as reported by HotSpot |
| `cpu=220.12ms` | `cpu=...` | Cumulative CPU time or CPU info printed by the runtime; not instantaneous %CPU |
| `elapsed=31.01s` | `elapsed=...` | Lifetime duration according to the runtime's thread clock, not request duration |
| `tid=0x...` | `0x00007f1020032000` | **Address of the native VM thread structure** in HotSpot; not the Linux TID |
| `nid=0x2a3f` | `0x2a3f` | **Native thread ID**, typically LWP/TID on Linux, printed in hex |
| `waiting for monitor entry` | header description text | Internal/OS-related state printed by the implementation, distinct from the Java enum below |
| `java.lang.Thread.State: BLOCKED` | `BLOCKED` | Java VM-level state, waiting to enter a `synchronized` monitor |
| `at ... (File.java:118)` | Java frame | Current method/caller and source location when line info is available |
| `- waiting to lock <0x...>` | monitor metadata | Waiting to acquire the monitor of the object with the printed identity |

**Most common pitfall:** in a HotSpot header, `tid=0x...` is **not** passed to `top -H` to look up a Linux thread. To correlate an OS native thread, use **`nid`**, converting from hex to decimal when needed. `Java Thread.getId()` is another identifier layer.

## 4. Thread names: useful, but not a unique key

### 4.1. How are names assigned?

In Java:

```java
Thread current = Thread.currentThread();
String name = current.getName();
current.setName("checkout-worker-7"); // Illustrative only, renames the current thread.
```

Names are typically created by a `ThreadFactory` in a pool, framework, container, executor, or application code. Common patterns:

- `main`: the main thread when the Java launcher executes `main`.
- `pool-3-thread-1`: thread naming style from some `Executors.defaultThreadFactory` implementations.
- `http-nio-8080-exec-12`: name assigned by certain servlet servers.
- `ForkJoinPool.commonPool-worker-2`: worker of the fork-join pool.
- `Reference Handler`, `Finalizer`, `Common-Cleaner`: JVM/Java runtime service threads, depending on implementation and version.
- `GC Thread#...` or `VM Thread`: may be **JVM internal/native threads**, not necessarily having a `java.lang.Thread` object with a regular Java ID.

Thread names help narrow down a subsystem, but **are not guaranteed to be unique**: one executor can generate the same names as another; multiple JVM generations all have a `main` thread; thread names can be changed. When aggregating across multiple dumps, combine **PID + JVM start + Java ID or nid + timestamp**; for threads that can terminate and be recreated, numeric IDs can be reused.

### 4.2. Naming threads for easier diagnostics

If creating threads manually in an application:

```java
java.util.concurrent.ThreadFactory factory = task -> {
    Thread t = new Thread(task);
    t.setName("payment-worker-" + t.getId());
    return t;
};
```

This code is a snippet for creating a `ThreadFactory`, not a complete program. Using `Thread.getId()` in the name is only a reference strategy; Java 17 `getId()` returns the Java thread ID, not `nid`. When a framework provides a naming mechanism, prefer configuring a centralized thread factory.

Do not put secrets, sensitive tenant identifiers, or user payloads into thread names: these names can appear in thread dumps, JMX, and logs. For thread pools, do not rename threads per request and forget to restore them; request context linking should be solved with trace/request IDs and proper logging context.

### 4.3. Are “idle” threads abnormal?

No. A thread pool waiting on a queue will show frames near `ThreadPoolExecutor.getTask`, `LinkedBlockingQueue.take`, `LockSupport.park`, and `WAITING`. That can be **normal** behavior. Names like `http-nio-...` or `pool-...` do not tell you which request is being processed unless the call stack or additional context proves it.

Do not equate “hundreds of WAITING threads” with a deadlock. You must check wait reasons, lock ownership, queue length, request rate, and whether counts/stacks grow abnormally over time.

## 5. Java thread ID, native ID, and `tid`: three different identifiers

### 5.1. Java thread ID

On Java 17:

```java
long javaThreadId = Thread.currentThread().getId();
```

`Thread.getId()` returns a positive `long` generated inside the JVM for the thread; it may be reused **after the thread terminates**. `ThreadMXBean` uses Java thread IDs to query `ThreadInfo`. The `ThreadInfo.getThreadId()` method also represents the Java thread ID.

For example, to look up a thread named `checkout-worker-7` in the management API, retrieve `ThreadInfo.getThreadId()`—do not pass the hex `nid` into `ThreadMXBean.getThreadInfo(long)` expecting to find the right thread.

Some HotSpot thread-dump formats display `#42` corresponding to the Java thread number; **header formatting is not a stable Java SE contract**, so when analyzing dumps from another vendor/JDK, verify the actual schema. In particular, do not equate `#42` with `tid=0x00007f...` just because both fields sit on the same header.

### 5.2. Native thread ID (`nid`)

The native ID is the OS thread's identifier. In a HotSpot dump on Linux, `nid=0x2a3f` typically corresponds to decimal TID/LWP **10815**. Verification math:

```text
0x2a3f = 2*4096 + 10*256 + 3*16 + 15 = 10815
```

Bash on Linux can convert it:

```bash
printf '%d\n' 0x2a3f
```

Exact output:

```text
10815
```

On Linux, when the JVM PID is `12345`, correlate threads of **the exact process**:

```bash
top -H -p 12345
ps -L -p 12345 -o pid,tid,stat,pcpu,comm
```

`top -H` or `ps -L` can display decimal native TIDs; correlate with `nid` **from the same timestamp and the same PID namespace**. TIDs can be recycled after a native thread exits. CPU% from `top` is the result of **the tool's measurement interval**, and does not match an instantaneous dump if collected far apart in time.

On Windows, OS-native thread IDs and inspection tools differ from Linux; `ps -L`/`top -H` do not apply. On macOS, mappings and tools also differ. Do not call every native ID on every OS a “Linux LWP”.

### 5.3. What is `tid=0x...`?

In many HotSpot dumps, `tid` is a pointer/address to the JVM's internal structure representing the Java thread (value in hexadecimal). It is **not**:

- the Java `Thread.getId()` value;
- the native ID from `nid`;
- the PID of the JVM process;
- the thread index in an executor;
- a timestamp or the address of a waited-on object monitor.

Therefore, do not convert hex `tid` to decimal to search in `top -H`, and do not treat a large `tid` as “a thread consuming lots of memory”. Analysis tools or dumps on different versions may use different notations; distinguish their meanings according to the actual format.

### 5.4. Identifier comparison table

| Field | Example | Scope/source | Used to join with |
| --- | --- | --- | --- |
| Thread name | `"checkout-worker-7"` | Set by application/JVM, not unique | Functional grouping when reading stacks |
| Java ID | `42` / `#42` in some dumps | Java Thread / `ThreadMXBean` | `ThreadInfo.getThreadId()`, Java telemetry |
| Native ID | `nid=0x2a3f` | OS thread; hex in HotSpot dumps | Linux decimal LWP/TID `10815` |
| HotSpot `tid` | `0x00007f1020032000` | Address of HotSpot thread structure | Only within the appropriate VM/dump context |
| Process PID | `12345` | OS process (may vary by namespace) | `jcmd <pid>`, container/host process identity |
| Object monitor ID | `<0x0000000700a01234>` | Printed identity for a Java object lock in the dump | `waiting to lock` / `locked` lines within **the same dump** |

A Java SE 17 API like `ThreadMXBean` **has no standard method returning the native thread ID**. To join a Java ID with an OS TID, rely on a HotSpot dump containing both or authorized JVMTI/JFR/native tools that provide proper mapping.

### 5.5. Why should you not rely on only one ID across multiple dumps?

- JVM restart: Java thread IDs can start over; OS PIDs can be reused.
- Thread pool scaling up/down: an old worker terminates, a new worker gets the exact same name.
- Containers: PID/TID seen from the host and inside the container can differ; the same number “1” in two PID namespaces is not the same process.
- Garbage collection/JVM internals: pointers and object identities printed in dumps are not immutable global identifiers.
- Dump files may be shipped late by a collector, arriving in a different order than captured.

For long-term correlation, use **UTC timestamp + JVM start/uptime + service/node/container identity + the appropriate IDs**.

## 6. Reading `java.lang.Thread.State` accurately

Java 17 defines six values in the `Thread.State` enum. These are **VM states**, not the OS scheduler state table (Linux `R/S/D/T/Z`). A thread has only one enum state at a given point of observation.

| Java state | Meaning | Common frames/cases | Interpretation trap |
| --- | --- | --- | --- |
| `NEW` | `Thread` created but `start()` not yet called | Thread object before running; usually absent from live dumps | Do not conclude “about to die” |
| `RUNNABLE` | Executable in the JVM / native call | CPU work, event loop, socket read, native poll | **Does not equate to** actually burning CPU |
| `BLOCKED` | Waiting to enter a `synchronized` monitor | `- waiting to lock`, entering a synchronized method/block | Does not cover every kind of lock wait |
| `WAITING` | Waiting indefinitely for another thread's action | `Object.wait()`, `Thread.join()`, `LockSupport.park()` | Can be a normal idle worker |
| `TIMED_WAITING` | Waiting with a timeout | `Thread.sleep`, timed `wait/join/park` | Does not guarantee the thread will run immediately upon timeout |
| `TERMINATED` | Thread has finished | Still-referenced Thread object; not normally in live dumps | Does not mean the JVM crashed |

In a JVM thread dump, a line like `java.lang.Thread.State: ...` shows the Java enum; descriptions at the end of the header such as `runnable`, `waiting on condition`, `in Object.wait()`, or `waiting for monitor entry` are implementation-specific descriptions. Do not treat that header string as a second Java enum.

### 6.1. `RUNNABLE` does not equate to “using 100% CPU”

Example:

```text
"nio-worker" #26 ...
   java.lang.Thread.State: RUNNABLE
        at sun.nio.ch.EPoll.wait(Native Method)
        at sun.nio.ch.EPollSelectorImpl.doSelect(EPollSelectorImpl.java:...)
        at java.base/java.nio.channels.Selector.select(Selector.java:...)
```

This is an **illustrative sample with line numbers omitted**, not a fixed Java 17 output. A thread in state RUNNABLE that is inside a native poll, waiting for I/O readiness, can consume very little CPU. To detect CPU hotspots, you need **per-thread CPU time across two samples, OS `top -H`/`ps -L`, or JFR/profiler**, rather than counting RUNNABLE lines.

Conversely, a CPU-bound thread running computation may show RUNNABLE with repeated frames in calculation code. Still, **one** dump placing that frame on top is not enough to conclude high CPU; observe consecutive samples and CPU metrics.

### 6.2. `BLOCKED` only waits for a `synchronized` monitor

Example:

```text
"request-17" #91 ...
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.Cache.read(Cache.java:87)
        - waiting to lock <0x0000000700a00111> (a java.lang.Object)
        at com.example.Service.handle(Service.java:32)
```

The thread is waiting to acquire a Java monitor to enter a `synchronized` section. You need to find the thread **holding the same monitor** `<0x0000000700a00111>`, typically shown by a `- locked <0x0000000700a00111>` line or owner info in a full dump/`ThreadInfo`.

A `ReentrantLock.lock()` or `Condition.await()` using `LockSupport.park` can appear as **WAITING** instead of `BLOCKED`. Thus counting BLOCKED threads alone is insufficient to detect all lock contention.

### 6.3. `WAITING` has many reasons

Common patterns:

```text
java.lang.Thread.State: WAITING (on object monitor)
    at java.base/java.lang.Object.wait(Native Method)

java.lang.Thread.State: WAITING (parking)
    at java.base/jdk.internal.misc.Unsafe.park(Native Method)
    at java.base/java.util.concurrent.locks.LockSupport.park(...)

java.lang.Thread.State: WAITING
    at java.base/java.lang.Thread.join(Thread.java:...)
```

These are **illustrative stack snippets**; specific files/lines and frames vary by JDK. Semantics:

- `Object.wait`: the thread normally **released** the corresponding monitor upon entering wait and must be notified/woken up and then reacquire the monitor to proceed.
- `LockSupport.park`: the thread waits for a permit or an action from a concurrency mechanism, typically in a queue/thread pool/lock.
- `Thread.join`: waits for another thread to finish.

A thread `WAITING` in `LinkedBlockingQueue.take` may be an idle pool worker. If that thread is holding another resource while waiting, indirect risk still exists; you must read the entire stack, locks, and workload.

### 6.4. `TIMED_WAITING` is a bounded wait, not automatically an error

Example:

```text
java.lang.Thread.State: TIMED_WAITING (sleeping)
    at java.base/java.lang.Thread.sleep(Native Method)
    at com.example.RetryLoop.backoff(RetryLoop.java:47)
```

A retry thread sleeping 500 ms is normal behavior if aligned with policy. When latency is high, check whether request threads are inadvertently sleeping too long, repeating backoff, using an oversized timeout, or stuck behind a congested queue. `sleep` **does not release any held Java monitors**; this differs from `Object.wait()` and can cause lock contention if called inside `synchronized`.

### 6.5. `NEW` and `TERMINATED` are rarely seen in live JVM dumps

The Java API `Thread.getState()` on a Thread object can return NEW before `start`, or TERMINATED after finishing. However, a thread dump of **live/JVM-listed threads** usually does not list every unstarted or dead Thread object. Do not conclude “the JVM has no Thread.State.NEW” just because the dump lacks NEW entries.

### 6.6. Java states differ from OS states

A Linux thread can be running/runnable `R`, sleeping `S`, uninterruptible sleep `D`, or other states. Java RUNNABLE can correspond to OS sleeping in native I/O; Java WAITING can correspond to OS `S`. To correlate:

1. Find the `nid` (native TID) of **the same thread** in the dump.
2. Convert hex → decimal for the right platform.
3. Inspect OS state/CPU in the exact PID namespace and timestamp.
4. Do not rush into a one-to-one mapping between Java state and OS state.

## 7. Reading stack frames: from the top line to the call chain

### 7.1. Order of stack frames

An example:

```text
"http-worker-12" #64 ...
   java.lang.Thread.State: RUNNABLE
        at com.example.db.Client.read(Client.java:146)
        at com.example.order.OrderRepository.find(OrderRepository.java:77)
        at com.example.order.OrderService.get(OrderService.java:118)
        at com.example.web.OrderController.get(OrderController.java:41)
        at java.base/java.lang.Thread.run(Thread.java:833)
```

The line near the top, `Client.read`, is **the frame closest to where the thread is currently executing/captured**; subsequent lines below are deeper **callers**. Do not read from bottom to top and conclude `Thread.run` is the slow code. With many frameworks, a stack can have dozens or hundreds of frames in proxies/reflection/Netty/servlets; the important part is usually the group of frames in business code and blocking primitives.

General notation:

```text
at [module/]package.Class.method(File.java:line)
```

- `package.Class.method`: class/method name known to the stack walker.
- `module/`: Java module name when printed by the format.
- `File.java:line`: source line if bytecode/build retained line number metadata.
- `Native Method`: native method frame; no corresponding Java line exists.
- `Unknown Source`: insufficient file/line info; not automatically malicious or buggy.
- `...` or truncated frames: output may be truncated due to depth/policy.
- `<init>`, `<clinit>`: constructor and static class initializer in the respective frame.

Do not treat a line number as the guaranteed site of a **bottleneck**: it is merely the execution point at snapshot time, and may be inside a waiting method caused by an API/JVM or JIT. Proving a CPU hotspot requires multiple samples and CPU attribution.

### 7.2. What does the same frame appearing across many threads mean?

If 200 threads all show:

```text
at java.base/jdk.internal.misc.Unsafe.park(Native Method)
at java.base/java.util.concurrent.locks.LockSupport.park(...)
at java.base/java.util.concurrent.LinkedBlockingQueue.take(...)
at java.base/java.util.concurrent.ThreadPoolExecutor.getTask(...)
```

then it may simply be an **idle thread pool**. If 200 threads all show:

```text
at java.base/java.net.SocketInputStream.socketRead0(Native Method)
at com.example.client.InventoryClient.call(InventoryClient.java:88)
at com.example.web.CheckoutController.submit(CheckoutController.java:59)
```

then it may suggest **many requests simultaneously waiting on downstream I/O**, warranting checks on timeouts, connection pools, dependency latency, queue lengths, and request metrics. Both snippets illustrate how to read meaning, and are not necessarily the exact frames of every JDK 17 runtime (socket implementation internals may differ).

Therefore, group by **stack signature** such as 3–8 relevant frames instead of counting only the top frame `Unsafe.park` or `Thread.run`. When thousands of threads exist, grouping by call path is far more valuable than reading line by line sequentially.

### 7.3. Native frames and JIT

A `Thread.print` thread dump primarily provides Java stacks; some threads in native calls show `Native Method` without showing the full C/C++ stack from JNI/OS. For crashes in native code, you need `hs_err_pid*.log`, native stacks/core dumps, or an authorized native profiler.

JIT/inlining optimizations, `safepoint` behavior, running in JNI, or missing debug symbols can make frames/lines differ from the original source; do not assume JDK 17 always reveals every frame exactly like an unoptimized call. Use debug symbols/JFR/native tooling when needed rather than guessing from `Unknown Source`.

### 7.4. Thread dumps do not store local variable values

A frame `OrderService.get(OrderService.java:118)` does **not** tell you what the order ID object is, what the SQL query string is, or any local variable values. Nor does it suffice to prove which branches above it executed in the past. Do not infer sensitive data from thread names, monitor addresses, or frames; if you need request context, use properly designed logging/tracing rather than dumping full request payloads to “correlate quickly”.

## 8. Lock and synchronization lines: `waiting to lock`, `locked`, `parking to wait for`

### 8.1. Monitors: owner and waiter

An illustrative thread group:

```text
"lock-holder" #50 ...
   java.lang.Thread.State: TIMED_WAITING (sleeping)
        at java.base/java.lang.Thread.sleep(Native Method)
        at com.example.Cache.refresh(Cache.java:101)
        - locked <0x0000000700a01111> (a java.lang.Object)

"lock-waiter" #51 ...
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.Cache.read(Cache.java:89)
        - waiting to lock <0x0000000700a01111> (a java.lang.Object)
```

This is a **composite sample**; line numbers and formatting vary by JDK. The shared monitor identity `<0x0000000700a01111>` suggests `lock-holder` is holding the monitor that `lock-waiter` must wait for. Even though the holder is TIMED_WAITING in `Thread.sleep`, it **can still be holding the monitor**, because `Thread.sleep` does not release locks. This is a design mistake that easily causes widespread latency.

Check which `synchronized` block the holder's method is inside and whether it calls I/O, sleeps, or processes for too long. Do not just look at “waiter BLOCKED” and try to fix locking on that thread; the cause usually lies with **the holder** or how the critical section is scoped.

### 8.2. `Object.wait` vs. `Thread.sleep`

| Behavior | Monitor relationship | Commonly seen thread state |
| --- | --- | --- |
| Entering `synchronized` when monitor is held | Waiting to acquire monitor | `BLOCKED` |
| `Object.wait()` while owning monitor | Releases the waited monitor, waits for notify/interruption; must reacquire afterward | `WAITING` or `TIMED_WAITING` |
| `Thread.sleep(...)` inside synchronized | **Does not** automatically release held monitors | `TIMED_WAITING` |
| `LockSupport.park(...)` | Waits for permit/unpark; does not automatically release any held application locks | `WAITING` or `TIMED_WAITING` |
| `ReentrantLock.lock()` when forced to wait | Synchronizes via `AbstractQueuedSynchronizer`, not a Java monitor `BLOCKED` in the strict sense | Usually `WAITING (parking)` |

This is a common model, not a guarantee that every frame will show the exact wording. Crucial rule: **state WAITING does not prove a thread holds no locks**.

### 8.3. “Locked ownable synchronizers”

The `-l` flag typically adds a section for locks from `java.util.concurrent`, such as `ReentrantLock` or ownable synchronizers, when supported by the JVM:

```text
Locked ownable synchronizers:
    - <0x0000000700abc777> (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
```

This is an example format of one lock owned by the thread, not all locks in the application. For code using `ReadWriteLock`, `StampedLock`, asynchronous locks, or custom synchronization, visibility may differ. A `- parking to wait for <0x...>` line and the “Locked ownable synchronizers” section must be read within **the lock mechanism's context**, not merely by matching hex IDs without understanding ownership.

### 8.4. What does `ThreadInfo` have as an equivalent?

`java.lang.management.ThreadInfo` provides:

- `getLockInfo()`, `getLockName()`: the lock the thread is waiting on;
- `getLockOwnerId()`, `getLockOwnerName()`: the Java thread owning the lock if known;
- `getLockedMonitors()`: Java monitors currently owned;
- `getLockedSynchronizers()`: ownable synchronizers currently owned;
- `getBlockedCount()`/`getWaitedCount()`;
- `getBlockedTime()`/`getWaitedTime()` when contention monitoring is supported and enabled.

`getLockOwnerId() == -1` may mean no owner is identified; it does **not** prove the program is not waiting at all. `getBlockedTime() == -1` may occur because contention monitoring is not enabled. When calling `ThreadMXBean.dumpAllThreads(true, true)`, verify `isObjectMonitorUsageSupported()` and `isSynchronizerUsageSupported()` first, and consider the cost of capturing all threads.

### 8.5. Deadlock requires a wait cycle, not just one BLOCKED thread

A classic deadlock: thread A holds monitor L1 and waits for L2, thread B holds L2 and waits for L1. If only A is BLOCKED waiting for L2, we do not yet have proof of deadlock; B might release L2 in a few milliseconds.

On HotSpot, a full thread dump may print a “Java-level deadlock” detection section. In Java:

- `ThreadMXBean.findMonitorDeadlockedThreads()` finds deadlocks across **object monitors**;
- `ThreadMXBean.findDeadlockedThreads()` extends to **ownable synchronizers** depending on support.

These APIs cannot find every type of deadlock outside the JVM, such as two requests waiting on a database/remote service or an application waiting indefinitely on a future without forming a JVM-detectable lock cycle. A `null` result does **not** prove there is no starvation or distributed deadlock.

## 9. Java 17+ program with deterministic stdout: name, ID, state, and stack

This example uses only standard Java interfaces and does not attach to another JVM. Save file **`ThreadBasicsDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;

public class ThreadBasicsDemo {
    public static void main(String[] args) {
        Thread current = Thread.currentThread();
        current.setName("diagnostic-main");

        Thread notStarted =
                new Thread(() -> {}, "sample-worker");

        ThreadMXBean mx = ManagementFactory.getThreadMXBean();
        ThreadInfo info =
                mx.getThreadInfo(current.getId(), 8);

        System.out.println("current.name=" + info.getThreadName());
        System.out.println("current.id.positive="
                + (info.getThreadId() > 0));
        System.out.println("current.state=" + info.getThreadState());
        System.out.println("current.stack.present="
                + (info.getStackTrace().length > 0));
        System.out.println("new.name=" + notStarted.getName());
        System.out.println("new.state=" + notStarted.getState());
    }
}
```

Compile/run with JDK 17+:

```bash
javac ThreadBasicsDemo.java
java ThreadBasicsDemo
```

**Exact stdout** of the standard example:

```text
current.name=diagnostic-main
current.id.positive=true
current.state=RUNNABLE
current.stack.present=true
new.name=sample-worker
new.state=NEW
```

Because the example sets the current thread's name explicitly, it does not depend on the launcher's default `main` name. `getThreadInfo(current.getId(), 8)` snapshots the currently executing thread, returning its Java ID/state and up to 8 stack frames. `notStarted` has been created but not yet `start()`ed, so it is NEW; **it is not expected to appear in the live threads list of `ThreadMXBean.getAllThreadIds()`**.

Key lesson: `ThreadInfo.getThreadId()` shares the same ID space as `Thread.getId()`, and there is no `getNativeThreadId()` in the standard Java 17 management interface. `getStackTrace()` is returned with the top frame at index 0 and callers below.

## 10. Java 17+ program with deterministic stdout: converting hex native ID

Save file **`NativeIdMathDemo.java`**:

```java
public class NativeIdMathDemo {
    public static void main(String[] args) {
        String nidFromDump = "0x2a3f";
        long nativeTid = Long.parseLong(
                nidFromDump.substring(2), 16);

        long illustrativeJavaThreadId = 42L;

        System.out.println("nid.hex=" + nidFromDump);
        System.out.println("nid.decimal=" + nativeTid);
        System.out.println("java.id=" + illustrativeJavaThreadId);
        System.out.println("idsAreDifferent="
                + (nativeTid != illustrativeJavaThreadId));
    }
}
```

Run:

```bash
javac NativeIdMathDemo.java
java NativeIdMathDemo
```

**Exact stdout:**

```text
nid.hex=0x2a3f
nid.decimal=10815
java.id=42
idsAreDifferent=true
```

`illustrativeJavaThreadId` is a **simulated number for the example**, not the actual ID of the thread running the program. Purpose: to illustrate that `nid` is a hex native ID for OS comparison, whereas the Java thread ID is a different value from a different source. When parsing real dumps, validate that the input format has a valid `0x` prefix and numeric bounds; do not treat this arithmetic as a full thread dump parser.

## 11. Java 17+ program: reading multiple threads with `ThreadMXBean`

`ThreadMXBean` belongs to the `java.management` module. Use it when you want to retrieve Java thread data programmatically instead of parsing full HotSpot text output. The following is a snippet placed inside a method:

```java
java.lang.management.ThreadMXBean mx =
        java.lang.management.ManagementFactory
                .getThreadMXBean();

long[] ids = mx.getAllThreadIds();
for (long id : ids) {
    java.lang.management.ThreadInfo info =
            mx.getThreadInfo(id, 10);
    if (info == null) {
        // The thread may have terminated between the two calls.
        continue;
    }
    System.out.println(info.getThreadId() + " "
            + info.getThreadName() + " "
            + info.getThreadState());
}
```

**Note:** the code intentionally avoids printing full frames to reduce data volume and improve security. `getAllThreadIds()` reflects a set of live threads at the time of the call; between fetching IDs and reading `getThreadInfo`, a thread can terminate, so `info == null` is a normal condition.

To retrieve lock information (only on supporting VMs):

```java
boolean monitors = mx.isObjectMonitorUsageSupported();
boolean synchronizers = mx.isSynchronizerUsageSupported();

java.lang.management.ThreadInfo[] snapshot =
        mx.dumpAllThreads(monitors, synchronizers);

for (java.lang.management.ThreadInfo t : snapshot) {
    // Select only truly relevant threads and redact sensitive data.
    System.out.println(t.getThreadId() + " "
            + t.getThreadName() + " " + t.getThreadState());
}
```

This is a snippet placed inside a method where `mx` is declared as above. `dumpAllThreads` can be expensive on processes with very many threads. Schedule/scope it appropriately and write only to secure destinations. If you need to cap excessively deep stacks, Java 17 provides the overload `dumpAllThreads(boolean, boolean, int maxDepth)`; limiting depth reduces data volume, though it may omit callers that explain the root cause.

### 11.1. ThreadMXBean does not replace native/thread-dump tools

- It uses **Java thread IDs**, and does not return standard native `nid`.
- It returns Java stack traces, and does not by default include full C/C++ native frames.
- It can return `-1` for blocked/waited time when contention monitoring is disabled or unsupported.
- It does not guarantee a **strictly simultaneous** snapshot of every thread while the system continues running.
- The API can incur overhead; enabling thread CPU time or contention monitoring is a **management state change** that must be weighed carefully.

If matching with Linux TIDs is needed, HotSpot `nid` or native/OS tools may be necessary. If the goal is comparing Java-level states and lock owners, `ThreadInfo` has a cleaner contract than text parsing.

## 12. Correlating thread dumps with CPU and OS threads

### 12.1. Identifying a CPU-hot thread step by step

Suppose `top -H` output for a Linux process shows native TID `10815` using significant CPU. To identify the Java stack:

1. Confirm the process PID and namespace; note the timestamp when `top` measured CPU.
2. Convert decimal TID `10815` to hexadecimal: `0x2a3f`.
3. In the **thread dump of the same JVM**, search for the header containing `nid=0x2a3f`.
4. Read the Java state and stack frames; note whether it is application code, GC/JIT/native, or I/O.
5. Take a few closely spaced dumps **if impact allows** or use JFR/profiler, and compare stack signatures.
6. Correlate process CPU/time, request rate, GC pauses, and container CPU quota.

Do not compare a `top` snapshot at 08:00 with a dump at 08:20 because native thread IDs may have been reused or the workload may have changed. If no matching Java thread is found, the native thread may be a JVM internal/native thread, a JNI worker, or a thread that exited between measurements.

### 12.2. CPU time is a cumulative counter, not an instantaneous rate

Some HotSpot dumps include headers like `cpu=220.12ms elapsed=31.01s`. **Do not** read `cpu=220ms` as “the thread used 220ms of CPU over the last 1 second” unless the format specifies so. To calculate CPU ratio over time, you need two samples within the same thread's lifetime using a consistent CPU time counter:

```text
thread_cpu0_ns = 2_000_000_000
thread_cpu1_ns = 2_500_000_000
wall0_ns       = 10_000_000_000
wall1_ns       = 11_000_000_000

delta_thread_cpu_ns = 500_000_000
delta_wall_ns       = 1_000_000_000
one_core_fraction   = 0.50  (50% of one CPU core)
```

These are simulated numbers. `ThreadMXBean.getThreadCpuTime(javaThreadId)` can provide per-thread CPU time when supported and enabled by the VM. Before using it, check `isThreadCpuTimeSupported()` and `isThreadCpuTimeEnabled()`. A value of `-1` can indicate unsupported/unavailable/dead thread; do not convert it to zero and do not sum across two JVM lifetimes.

### 12.3. Matching with OS states

A native thread with Java `RUNNABLE` but Linux `S` may be waiting inside a native syscall. A Java `BLOCKED` thread waiting on a monitor may appear as OS sleeping. This difference is not necessarily a tool bug: the two layers describe **different semantics** and samples are taken at different moments.

When suspecting CPU starvation or throttling in containers, add cgroup `cpu.stat`, quota, scheduler run queue, and host contention data. A thread dump does not display a standard “throttled CPU time” counter per Java thread.

## 13. Method for reading multiple dumps to find real issues

### 13.1. Do not conclude from a single snapshot

One snapshot of thread `request-12` in `Socket.read` proves the thread **was waiting on I/O at capture time**, not that the dependency hung for 30 seconds. If that thread appears with the same stack after 5 seconds and 10 seconds while latency metrics rise, the I/O wait hypothesis grows stronger.

Each dump has value as **instantaneous evidence**, yet dynamic behavior (CPU, lock contention, pool starvation) usually requires comparison. Only collect additional samples when authorized and overhead is acceptable.

### 13.2. A consistent workflow

```text
1. Lock JVM identity (pid + start + container/node)
2. Lock incident window and UTC timestamps
3. Capture dump t0 (+ lock info if needed)
4. Attach CPU/latency/GC/thread snapshots near t0
5. Wait an appropriate observation interval, capture t1/t2 if permitted
6. Normalize header fields and group stack signatures
7. Compare changes in states, lock owners, and top user frames
8. Verify with JFR/traces/OS metrics
9. Write conclusion with confidence level + minimal remediation step
```

Do not compare `tid`/`nid` across dumps from two different JVMs and treat them as the same thread. If the PID is identical but JVM start time changed, you must treat it as a new process generation.

### 13.3. Grouping threads by stack signature

Instead of listing every thread individually, you can group them:

| Group | Sign | Initial possibility | Follow-up evidence |
| --- | --- | --- | --- |
| HTTP request blocked monitor | Multiple `BLOCKED` with same `waiting to lock <x>` | Lock holder/oversized critical section | Find owner and compare multiple dumps |
| HTTP request native read | Multiple `RUNNABLE` in socket native read | Slow downstream I/O | Tracing/timeouts/network metrics |
| Pool workers WAITING | `LinkedBlockingQueue.take`/`park` | Idle pool, usually normal | Queue depth, active/idle counts |
| Pool workers BUSY | Repeated application code frames | CPU work or concurrency issue | CPU time/JFR, request rate |
| Threads TIMED_WAITING sleep | `Thread.sleep` from retry/backoff | Retry delay/periodic task | Retry count, deadline/timeout |
| Threads WAITING on future | `CompletableFuture.join`/`FutureTask.get` | Unfinished async dependency | Completion chain, pool starvation |
| Multiple threads BLOCKED cyclically | Ownership/wait cycle across monitors/synchronizers | Deadlock | Deadlock detector and owner chain |
| Many threads in native code | JNI/VM internal frames | Native wait/CPU or runtime work | Native profiler, crash logs |

The groups above are **hypotheses**, not a guaranteed bug list. For example, `CompletableFuture.join` in a worker may be intended work; it becomes starvation when pool tasks are waiting for work that also needs that same pool to run.

### 13.4. Analyzing “long-stuck” threads

The same thread by Java ID/name/nid appearing at the same frame at t0, t1, t2 is not sufficient to prove *it is not running*: it may be looping rapidly through that same method many times. Check cumulative CPU deltas, application event counters, lock ownership, request/trace IDs, and operation progress.

Conversely, if a thread waits on a monitor and the owner holds the lock across multiple dumps while request latency climbs, that is stronger evidence of sustained lock contention.

## 14. Three hands-on scenarios

### Case A — High CPU: finding the right thread from native ID

**Context:** Linux JVM process PID `12345`. `top -H` reports TID `10815` using substantial CPU.

**Reading steps:**

1. Compute `10815` = `0x2a3f`.
2. In a dump of the same JVM near the same time, find `nid=0x2a3f`.
3. Read the Java state and stack; suppose the top frames are `calculateScore`, `applyRules` in application code.
4. Collect additional samples over time or JFR CPU profiling. If the same code frames persist and CPU time climbs, there is basis to investigate hotspots/algorithmic complexity.
5. Check request counts, data sizes, thread pool sizes, and GC/JIT load before optimizing.

**Common mistake:** searching for `tid=0x2a3f` or Java `#10815` instead of `nid`; reading `RUNNABLE` and claiming one thread uses 100% CPU.

### Case B — Rising latency: BLOCKED waiting on monitor

**Context:** 60 request threads show `java.lang.Thread.State: BLOCKED` and `- waiting to lock <0x0000000700a01111>`.

**Reading steps:**

1. Find the **owner** of the same monitor ID in the dump.
2. Check which frame the owner is executing; suppose it is sleeping inside a `synchronized` method.
3. Verify the owner still holds the monitor across several dumps; check when latency increased.
4. Conclude the issue lies in a long critical section/holding a lock during sleep/I/O if stacks and source support it.
5. Fix by shrinking the monitor scope or moving blocking operations outside the critical section according to application logic; test concurrency after the change.

**Common mistake:** only changing the number of request threads or restarting the pod, temporarily hiding the symptom without resolving lock contention.

### Case C — Mass WAITING: idle pool or starvation?

**Context:** 200 threads have state WAITING and stacks near `LockSupport.park`/`LinkedBlockingQueue.take`.

**Reading steps:**

1. Check whether they are idle workers of a pool, or waiting on a future/lock.
2. Read **caller frames**: `ThreadPoolExecutor.getTask` usually means fetching tasks; `CompletableFuture.join` inside a request worker suggests waiting for completion.
3. Correlate active tasks, queue size, submitted/completed counters, and request latency.
4. For starvation, check whether all workers are waiting on results of tasks that also need to run in **the very same exhausted pool**.
5. Do not immediately call it “deadlock” without a proven lock/logic cycle.

**Common mistake:** counting every WAITING thread as a severe bug; increasing thread counts indefinitely without analyzing the dependency graph.

## 15. Frequent interpretation mistakes

1. **Confusing `tid` with `nid`.** HotSpot `tid` is a JVM structure address; `nid` is the native thread ID.
2. **Passing `nid` to `ThreadMXBean.getThreadInfo`.** That API takes a Java thread ID.
3. **Assuming thread names are unique.** Names can duplicate, change, and repeat across restarts.
4. **Assuming `RUNNABLE` = 100% CPU.** The thread may be in a native I/O wait.
5. **Assuming `WAITING` = deadlock.** Idle pools and legitimate `Object.wait` also show WAITING.
6. **Assuming `BLOCKED` covers every kind of lock.** `ReentrantLock` can appear as WAITING/parking.
7. **Treating the top stack line as the root cause.** It is only the snapshot location; callers and context are needed.
8. **Reading stacks upside down.** `Thread.run` near the bottom is the entry point, not necessarily the active line.
9. **Ignoring `- waiting to lock` and `- locked`.** These two lines are critical for finding monitor owners.
10. **Forgetting the `Locked ownable synchronizers` section.** You may miss ReentrantLock/AQS locks.
11. **Confusing hex monitor IDs with Java thread IDs.** Monitor IDs represent object locks in the snapshot.
12. **Comparing Linux TIDs between host and container without checking namespaces.** Leads to wrong mappings.
13. **Concluding from a single dump far removed from the incident.** Threads may have changed work or exited.
14. **Taking too many dumps on a heavily loaded JVM.** `Thread.print` has overhead and can increase latency.
15. **Assuming `jcmd -l` not showing a process means the process is not running.** It can be due to namespaces/permissions.
16. **Believing `cpu=...` in the header is CPU% over the last second.** It is not by default a rate.
17. **Adding CPU time nanoseconds to epoch milliseconds or uptime.** Different units and origins.
18. **Reading `Unknown Source` as a guaranteed application bug.** It may simply lack debug line metadata.
19. **Ignoring JVM/GC/JIT/native internal threads.** They can also consume CPU or affect the application.
20. **Failing to distinguish an exception stack trace from a thread dump.** One is at error time, the other at snapshot time.
21. **Using `Thread.dumpStack()` expecting to dump the whole JVM.** That method prints the current thread's stack, not all threads.
22. **Enabling per-thread contention monitoring/CPU time without assessing cost.** It changes management state.
23. **Posting raw dumps containing endpoints, tokens in thread names, or file paths in chat.** Carries information disclosure risk.
24. **Treating multiple threads at the same frame as a guaranteed bug.** It can be steady-state pool behavior.
25. **Failing to attach JVM start/PID when correlating dumps.** PIDs/Java IDs can be reused, especially after restarts.

## 16. Checklist when reading a thread entry

- [ ] Was the dump taken from the right **JVM instance**, PID/container namespace, with a UTC timestamp?
- [ ] What does the thread name mean and could it be duplicated?
- [ ] Did you distinguish Java ID/`#n`, HotSpot `tid`, and native `nid`?
- [ ] If joining with Linux `top -H`, did you convert hex `nid` to decimal properly and check timestamps?
- [ ] Did you distinguish the **Java enum state** from header descriptions/OS states?
- [ ] Could `RUNNABLE` be waiting on native I/O, requiring a CPU time check?
- [ ] Which monitor is `BLOCKED` waiting on? Can the holder be found?
- [ ] Does `WAITING`/`TIMED_WAITING` come from a queue, lock, join, future, sleep, or request path?
- [ ] Were stack frames read top-to-bottom; were relevant user-code frames/callers identified?
- [ ] Are there `waiting to lock`, `locked`, `parking to wait for`, or ownable synchronizers lines?
- [ ] Could stack/line info be incomplete, or could JIT/native calls affect observability?
- [ ] Is there reason to need a second/third dump, JFR/metrics/GC logs to verify hypotheses?
- [ ] Were monitor deadlock, lock contention, starvation, and I/O wait distinguished?
- [ ] Was dump access restricted and sharing of sensitive data avoided?
- [ ] Do conclusions state only what is proven by the snapshot(s), without guessing causes?

## 17. Self-check exercises

**Exercise 1 — Header.** In a HotSpot entry with `"worker-2" #17 tid=0x00007f0000201000 nid=0x2a3f runnable`, identify the name, Java thread number, hex native thread ID, decimal ID on Linux, and which value is an internal pointer. Answer: name `worker-2`; `#17` is the thread number/Java ID in the illustrative HotSpot format; `nid=0x2a3f` corresponds to **10815**; `tid=0x00007f...` is the VM structure address, **not** passed to `top -H`. Verify against the actual JDK format in production.

**Exercise 2 — State.** A `RUNNABLE` thread has top frame `EPoll.wait(Native Method)`. Can you conclude the thread is causing 100% CPU? **No**: it may be waiting on I/O in a native syscall; CPU counters/JFR and multiple samples are needed.

**Exercise 3 — Monitor.** Thread A shows `- locked <0xAAA>` and is sleeping; thread B shows `- waiting to lock <0xAAA>`. Who is most likely holding the monitor, and what is the next verification step? A holds the monitor; inspect A's `synchronized` frame, lock hold duration, and persistence across dumps; do not simply increase thread counts.

**Exercise 4 — WAITING.** Are one hundred threads in `ThreadPoolExecutor.getTask`/`LinkedBlockingQueue.take` a deadlock? **Not by default**. If the pool is idle, that is normal. Check active tasks, queue depth, request latency, and owner/lock cycles.

**Exercise 5 — ThreadMXBean.** Can `ThreadInfo.getThreadId()` be used as a Linux LWP ID? **Not guaranteed**. Java IDs differ from native IDs; mapping from `nid` or appropriate native tooling is required.

**Exercise 6 — Reading over time.** A thread appears at the same `calculate()` frame across three dumps 5 seconds apart. Is it definitely stuck? **Not yet**; it could be looping rapidly through the same function. You need CPU deltas, progress counters, and lock/request context.

## References

- Oracle Java SE 17, [Diagnostic Tools](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): thread dump structure, headers, `tid`, `nid`, `Thread.State`, and examples.
- Oracle Java SE 17, [`jcmd` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `Thread.print -l`, permissions, impact, and JVM support.
- Oracle Java SE 17, [`jstack` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstack.html): stack traces and `-l`, tool limitations.
- Oracle Java SE 17, [`Thread.State` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html): the six enum states of Java 17 and differences from OS states.
- Oracle Java SE 17, [`ThreadMXBean` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): Java thread IDs, stack traces, locks, deadlocks, CPU/contended time.
- Oracle Java SE 17, [`ThreadInfo` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html): thread name, state, Java ID, lock owner, frames, and synchronization.
- Oracle Java SE 17, [`StackTraceElement` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackTraceElement.html): class/method names, source file/line, native method.
- Oracle Java SE 17, [`Thread` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `getName()`, `getId()`, `getState()`, `getStackTrace()`.
- OpenJDK Java Operations, [How to Obtain a Thread Dump on Linux](https://ops.java/howto/articles/thread-dump-linux/): `jstack`, `jcmd`, and `SIGQUIT`.

**Conclusion:** reading a thread dump properly means connecting **name + Java ID + native ID + state + stack frames + locks** within the right JVM lifecycle. A snapshot tells you the observed position at one point in time, and does not directly give you root cause, CPU percentage, or wait duration. Only after correlating multiple snapshots with CPU/GC/thread metrics, tracing, and OS/container context can you distinguish idle workers, I/O waits, lock contention, starvation, or CPU hotspots with solid evidence.