# Taking Thread Dumps and Identifying Blocked, Waiting, or Contended Threads

## 1. What Questions Does a Thread Dump Answer?

When a Spring Boot application is still running but requests respond slowly or never complete, you need to know which code each thread is executing and what it is waiting on. A **thread dump** is a snapshot of a JVM's thread information at collection time: state, call stack, and lock information observable by the tool.

Picture a service counter with several staff members:

- Some are actively working.
- Some have no work yet and are waiting.
- Some have work but must wait for someone else to release a resource.
- Two people might each hold a different resource while each waits for the other's resource.

Simply counting how many people are waiting is not enough to find the cause. The same holds for Java threads: you must connect **state → location in code → condition or resource awaited → thread holding the resource → ability to make progress**.

Within the "Logging and Memory" knowledge group, thread dumps add evidence about concurrent execution. Logs recount recorded events; a thread dump shows the execution points observed at that instant. It is not a snapshot of all objects on the heap and does not by itself prove a memory leak.

After this lesson, the learner can capture a dump via Actuator, distinguish normal waiting from lock contention, trace lock-holding threads, and form testable hypotheses. The lesson uses Spring Boot 3.3.x; the standalone Java example is compatible with Java 17+, with a separate note for JDK 21.

## 2. Obtaining a Thread Dump from Spring Boot Actuator

### 2.1. Prerequisites and Practice Environment Configuration

The application already has an appropriate web starter, such as Spring MVC, and the Actuator dependency. In a Gradle project already configured with Spring Boot and dependency management, add the following to the existing `dependencies` block:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
```

This is a dependency addition for an existing application, not a complete Spring Boot project.

In Boot 3.3, enabling an endpoint and exposing it over HTTP are two separate things. By default, only `health` is exposed over HTTP. The practice configuration below exposes only `health` and `threaddump`; `exclude`, if set, still takes precedence over `include`. If Spring Security is present, exposing an endpoint does not replace authentication/authorization rules. [Boot 3.3 endpoint documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Merge into the configuration for your practice environment, avoiding duplicate `management` YAML keys:

```yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: "health,threaddump"
  endpoint:
    threaddump:
      enabled: true
```

A dedicated management port on `8081` and the loopback address allow practice from the same machine. `management.server.address` is used together with the separate management port; the default path is `/actuator`. If the project changed the base path or endpoint path mapping, use the project's effective address. Inside a container, `127.0.0.1` belongs to the container's network namespace; a command from the host outside may not reach it. [Boot 3.3 management HTTP configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

A dump can expose class names, system structure, and execution locations. In shared environments, use an approved administrative access mechanism and protect dump files as well; do not casually expose this endpoint to the Internet.

### 2.2. Choosing JSON or Plain Text

The endpoint accepts `GET` requests. Use `Accept: application/json` for structured processing; use `Accept: text/plain` to read stacks directly. JSON contains a `threads` list; actual data depends on the JVM and capture time. [Boot 3.3 threaddump API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/threaddump.html).

In PowerShell, invoke `curl.exe` to use the actual curl executable:

```powershell
curl.exe --fail --silent --show-error --connect-timeout 2 --max-time 15 -H "Accept: application/json" -o threads.json "http://127.0.0.1:8081/actuator/threaddump"

curl.exe --fail --silent --show-error --connect-timeout 2 --max-time 15 -H "Accept: text/plain" -o threads.txt "http://127.0.0.1:8081/actuator/threaddump"
```

The two commands save two snapshots taken at two different moments, not two serializations of the same snapshot. On Unix shells, use `curl` with the corresponding arguments.

The commands assume local access is permitted. If using HTTP Basic, you can add `--user operator` so curl prompts for the password; the username must be a real administrative account. With another authentication mechanism, use your system's method. Do not record passwords or tokens in lessons, filenames, or shared command history.

Success typically returns HTTP `200` and dump content; there is no single fixed stdout for a real application. `--fail` makes curl return a non-zero exit code on HTTP errors, so check the exit code before using the file.

### 2.3. Taking Multiple Samples While an Incident Is Ongoing

A single snapshot does not show how long a thread has been at that location. You can take three samples spaced about three seconds apart on **the same process/instance**. This is a practice choice, not a mandatory sampling interval.

```powershell
$baseUri = "http://127.0.0.1:8081"
for ($sample = 1; $sample -le 3; $sample++) {
    $capturedAt = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ")
    $outputFile = "threads-$sample-$capturedAt.json"
    curl.exe --fail --silent --show-error --connect-timeout 2 --max-time 15 -H "Accept: application/json" -o $outputFile "$baseUri/actuator/threaddump"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to collect thread dump: $outputFile"
    }
    if ($sample -lt 3) {
        Start-Sleep -Seconds 3
    }
}
```

With multi-instance applications, pin the target to one instance; consecutive calls through a load balancer can hit three different JVMs. Record the timestamp, instance, deployed version, slowdown symptom, and current load. If the process restarted, do not link thread IDs across two runs.

Do not take dumps rapidly in an unthrottled loop. Overhead depends on thread count and tooling; collect only enough samples to test your hypothesis.

## 3. Distinguishing States Before Drawing Conclusions

`Thread.State` describes state inside the JVM, which is not identical to OS thread state:

| State | Meaning to remember |
| --- | --- |
| `NEW` | `start()` has not been called yet. |
| `RUNNABLE` | Executable; does not guarantee it is currently using CPU. |
| `BLOCKED` | Waiting to acquire a `synchronized` monitor. |
| `WAITING` | Waiting indefinitely, such as `wait()`, `join()`, `park()`. |
| `TIMED_WAITING` | Waiting with a timeout, such as `sleep()` or `parkNanos()`. |
| `TERMINATED` | Finished. |

A dump of live threads normally does not contain `NEW` or `TERMINATED`. Waiting to enter `synchronized` and waiting on a condition are two different mechanisms. [Thread.State definition in Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html).

**"Blocked" in everyday speech is broader than the `BLOCKED` constant.** In the section 6 example, a thread waiting on a `ReentrantLock` is in `WAITING` even though it is contending for a lock. Conversely, a thread waiting on an empty queue is also in `WAITING` yet may be completely normal.

A `RUNNABLE` thread appearing in a socket read or native call is also not enough to prove it is computing continuously. To conclude high CPU usage, correlate process/thread CPU or a JFR/profiler recording for the exact timeframe.

### Does Waiting Release Locks?

`Object.wait()` releases the monitor of the specific object on which `wait` is called and must re-acquire that monitor before returning. It does not automatically release all other locks the thread holds. Thus a thread can transition to `BLOCKED` while re-acquiring the monitor after being woken up. Always check the condition in a loop when using `wait`. [Object.wait contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html#wait()).

In the experiment below, `CountDownLatch.await()` inside a `synchronized` block does not release the enclosing monitor. Observing `monitor-owner` in `WAITING` still shows it holding the monitor that `monitor-contender` needs. This is why you cannot infer "waiting, therefore holding no resources".

## 4. Reading a Thread: State, Stack, and Lock-Holding Relationships

### 4.1. Fields to Combine Together

| Information | How to use |
| --- | --- |
| `threadId`, `threadName` | Identify the thread in the current run. |
| `threadState` | Starting point for classification. |
| `stackTrace` | Find the waiting operation and the application code path leading to it. |
| `lockInfo`, `lockName` | The lock or object the thread is waiting on, if any. |
| `lockOwnerId`, `lockOwnerName` | Trace to the lock-holding thread when information is available. |
| `lockedMonitors` | Monitors currently held by the thread. |
| `lockedSynchronizers` | Ownable synchronizers currently held by the thread, such as a `ReentrantLock` lock. |

This information is for observation, not for thread coordination logic. An owner might not be identifiable; `lockOwnerId = -1` or an absent owner name does not prove the system has no resource waiting. [ThreadInfo in Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html).

Read the stack from the top frame to see the execution point, then trace down to application frames to see why it arrived there. For example, seeing only `Unsafe.park` does not tell whether it is waiting on a lock, a queue, or a latch; you must inspect the calling frames.

### 4.2. Example Tracing from Waiter to Holder

The JSON below is a **simplified model for reading relationships**, not a full response. IDs and lock identifiers are chosen for illustration; other fields are omitted.

```json
{
  "threads": [
    {
      "threadId": 31,
      "threadName": "monitor-owner",
      "threadState": "WAITING",
      "stackTrace": [
        {
          "className": "java.util.concurrent.CountDownLatch",
          "methodName": "await"
        }
      ],
      "lockedMonitors": [
        {
          "className": "java.lang.Object",
          "identityHashCode": 305441741
        }
      ]
    },
    {
      "threadId": 32,
      "threadName": "monitor-contender",
      "threadState": "BLOCKED",
      "lockOwnerId": 31,
      "lockOwnerName": "monitor-owner",
      "lockInfo": {
        "className": "java.lang.Object",
        "identityHashCode": 305441741
      }
    }
  ]
}
```

How to read it:

1. `monitor-contender` is waiting to enter a monitor, with `lockOwnerId = 31`.
2. Find thread `31` in the same sample: it is `monitor-owner`.
3. Match the awaited lock against the list of monitors held by the owner.
4. The owner is waiting in `CountDownLatch.await`, so find the code or event that should open the latch.
5. There is no evidence of a wait cycle yet. Here we only see a single dependency edge.

You can write the relationship in text:

```text
monitor-contender
    -> waiting for monitor M
    -> monitor-owner holds M
    -> monitor-owner waiting for latch to be released
```

Thread names can duplicate; prefer IDs within the same JVM and same snapshot. Lock identifiers in JSON and addresses displayed by text tools are not memory size measurements. Do not compare them as global identifiers across JVMs.

### 4.3. Reading Wait Counts and Times Properly

`blockedCount` relates to counts of waiting to enter/re-enter a monitor; `blockedTime` is the corresponding accumulated time when contention monitoring is enabled. `waitedTime` is also a cumulative figure, not the age of the current wait. A value of `-1` in timing fields can indicate monitoring is disabled, not "minus one millisecond" or "never waited". Re-enabling monitoring may reset timing statistics. [ThreadInfo statistics](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html#getBlockedTime()).

Do not read `blockedCount = 500` as 500 threads currently blocked on one resource. Do not use `blockedTime` alone to measure queueing time for every lock type; waiting on `ReentrantLock` is not equivalent to the monitor `BLOCKED` state.

## 5. Recognizing Common Patterns in Applications

| Observed pattern | Initial hypothesis | Additional evidence needed |
| --- | --- | --- |
| Many `BLOCKED` threads pointing to one owner | Bottleneck on a shared monitor | What the owner is doing, lock scope, whether multiple samples repeat. |
| `WAITING` via `ReentrantLock.lock` | Explicit lock contention | Lock-holding thread and `lockedSynchronizers`. |
| Worker waiting on `BlockingQueue.take` when idle | Idle thread | Queue depth, incoming load, whether tasks are being processed. |
| Many requests waiting to borrow a connection | Resource pool may be exhausted | Active/waiting connections, slow queries, timeouts, threads holding connections. |
| Many stacks stopped in socket reads | Waiting on an external service or I/O | Dependency latency, network timeouts, concurrent traces and logs. |
| Thread repeatedly in a computation block with high CPU | Heavy computation or abnormal loop | Per-thread CPU and execution profile. |

These are **diagnostic hypotheses**, not automatic conclusions from method names. For instance, an idle worker in `take()` can be normal, whereas every worker waiting for results of other tasks queued in the very same saturated pool is a sign worth investigating.

### 5.1. How Contention, Deadlock, and Pool Exhaustion Differ

- **Lock contention:** multiple threads need the same lock; the owner can still finish and release the lock.
- **Deadlock:** a wait cycle exists that the parties cannot break on their own via current execution flow.
- **Pool exhaustion or starvation:** tasks cannot acquire the needed resource/worker; can happen even without any monitor lock cycle.

Two-lock wait-cycle example:

```text
Thread A holds L1, waiting for L2 held by B
Thread B holds L2, waiting for L1 held by A

A -> L2 -> B -> L1 -> A
```

Do not conclude deadlock just because multiple threads are `BLOCKED`. If the owner later releases the lock and tasks finish, it may be prolonged contention. Conversely, a wait cycle involving `ReentrantLock` can consist of `WAITING` threads.

For platform threads, `ThreadMXBean.findDeadlockedThreads()` supports finding cycles across monitors and ownable synchronizers; `findMonitorDeadlockedThreads()` checks monitors only. A `null` result does not rule out tasks waiting on I/O, business logic, or missing workers. These management APIs do not support observing virtual threads on JDK 21. [ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html).

Do not assume Actuator's text output will always include a line like `Found one Java-level deadlock` as some JVM diagnostic tools do. Waiting relationships and specific tool data are the evidence to read.

## 6. Runnable Java Experiment: Same Waiting, Different Causes

### 6.1. Purpose and How to Run

The program creates six **platform threads**:

- One thread holding a monitor while awaiting a latch; another thread waiting for that monitor.
- One thread waiting to take an item from an empty queue.
- One thread holding a `ReentrantLock` while awaiting a latch; another thread waiting for that lock.
- One thread sleeping with a timeout.

Latches confirm the owner acquired the lock before starting the contender. The program checks states with a five-second deadline instead of guessing that a short sleep suffices. These mechanisms are solely to build an observable experiment; do not use `getState()` polling for business coordination.

Save the entire code to `ThreadDumpLab.java`. Requires a JDK with the `java.management` module; the example was compiled with `--release 17` and verified on Java 17 and Java 21.

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class ThreadDumpLab {
    @FunctionalInterface
    interface Work {
        void run() throws InterruptedException;
    }

    private static Thread thread(String name, Work work) {
        return new Thread(() -> {
            try {
                work.run();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, name);
    }

    private static void awaitState(Thread thread, Thread.State expected)
            throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (thread.getState() != expected) {
            if (!thread.isAlive() || System.nanoTime() >= deadline) {
                throw new IllegalStateException(
                        thread.getName() + ": " + thread.getState());
            }
            Thread.sleep(10);
        }
    }

    private static void awaitReady(CountDownLatch ready)
            throws InterruptedException {
        if (!ready.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Owner did not become ready");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Object monitor = new Object();
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch monitorReady = new CountDownLatch(1);
        CountDownLatch lockReady = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        LinkedBlockingQueue<String> queue = new LinkedBlockingQueue<>();

        Thread monitorOwner = thread("monitor-owner", () -> {
            synchronized (monitor) {
                monitorReady.countDown();
                release.await();
            }
        });
        Thread monitorContender = thread("monitor-contender", () -> {
            synchronized (monitor) {
                // Can only enter after monitor-owner releases the monitor.
            }
        });
        Thread queueConsumer = thread("queue-consumer", () -> queue.take());
        Thread lockOwner = thread("lock-owner", () -> {
            lock.lock();
            try {
                lockReady.countDown();
                release.await();
            } finally {
                lock.unlock();
            }
        });
        Thread lockContender = thread("lock-contender", () -> {
            lock.lock();
            try {
                // Can only enter after lock-owner calls unlock().
            } finally {
                lock.unlock();
            }
        });
        Thread sleeper = thread("sleeper", () -> Thread.sleep(300_000));

        List<Thread> threads = List.of(monitorOwner, monitorContender,
                queueConsumer, lockOwner, lockContender, sleeper);
        try {
            monitorOwner.start();
            awaitReady(monitorReady);
            monitorContender.start();
            queueConsumer.start();
            lockOwner.start();
            awaitReady(lockReady);
            lockContender.start();
            sleeper.start();

            awaitState(monitorOwner, Thread.State.WAITING);
            awaitState(monitorContender, Thread.State.BLOCKED);
            awaitState(queueConsumer, Thread.State.WAITING);
            awaitState(lockOwner, Thread.State.WAITING);
            awaitState(lockContender, Thread.State.WAITING);
            awaitState(sleeper, Thread.State.TIMED_WAITING);

            ThreadMXBean bean = ManagementFactory.getThreadMXBean();
            long[] ids = threads.stream().mapToLong(Thread::getId).toArray();
            ThreadInfo[] infos = bean.getThreadInfo(ids, true, true);
            for (ThreadInfo info : infos) {
                if (info == null) {
                    throw new IllegalStateException("Thread disappeared");
                }
                String owner = info.getLockOwnerName();
                System.out.println(info.getThreadName() + " | "
                        + info.getThreadState() + " | owner="
                        + (owner == null ? "-" : owner));
            }
            if (args.length > 0 && args[0].equals("--hold")) {
                Thread.sleep(30_000);
            }
        } finally {
            release.countDown();
            queue.offer("stop");
            sleeper.interrupt();
            for (Thread thread : threads) {
                thread.join(5_000);
                if (thread.isAlive()) {
                    throw new IllegalStateException(
                            "Thread did not finish: " + thread.getName());
                }
            }
        }
    }
}
```

Compile and run in the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 ThreadDumpLab.java
java ThreadDumpLab
```

### 6.2. Stdout of the Default Run

On verified HotSpot JDKs 17/21, the program prints these exact six lines, in the defined list order, and then cleanly releases the threads:

```text
monitor-owner | WAITING | owner=-
monitor-contender | BLOCKED | owner=monitor-owner
queue-consumer | WAITING | owner=-
lock-owner | WAITING | owner=-
lock-contender | WAITING | owner=lock-owner
sleeper | TIMED_WAITING | owner=-
```

The `-` simply means `getLockOwnerName()` does not return an owner name for the object the thread is waiting on. It does not mean that thread holds no other locks.

Observations to be able to explain:

1. `monitor-owner` awaits the latch while still holding the enclosing monitor. `monitor-contender` is therefore in `BLOCKED` and points directly to the owner.
2. `queue-consumer` is in `WAITING` because the queue is empty. In the experiment, there is no work yet, so this is intentional waiting.
3. `lock-owner` awaits the same latch while still holding the `ReentrantLock`. `lock-contender` is in `WAITING` and has `lock-owner` as its owner.
4. `sleeper` is in `TIMED_WAITING` due to a timed `sleep`.
5. When `finally` opens the latch, both owners proceed and release their locks; both contenders can finish. The queue receives the stop element and the sleeping thread is interrupted. There is no deadlock in this program.

The `lock()` → `try` → `finally { unlock(); }` pattern guarantees releasing `ReentrantLock` when leaving the protected region. A fair lock policy also does not substitute for shortening slow operations inside the locked region. [ReentrantLock contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html).

### 6.3. Taking a Dump from the Program Using jcmd

To get an observation window, run:

```shell
java ThreadDumpLab --hold
```

The program still prints the six lines, then holds the experiment for about 30 seconds before cleaning up. Open a second terminal during that window:

```shell
jcmd -l
```

Find the process with main class `ThreadDumpLab`. Then, in PowerShell, replace `12345` with the actual PID just found:

```powershell
$javaProcessId = 12345
jcmd $javaProcessId Thread.print -l > lab-threads.txt
```

Use a JDK matching the target JVM, on the same machine, with appropriate user permissions. `Thread.print -l` adds `java.util.concurrent` lock information; command overhead depends on thread count. `jcmd -l` may not list JVMs inside containers in a separate process namespace. [JDK 21 jcmd manual](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).

In the actual experiment dump, find `monitor-contender` and match the object on the `waiting to lock` line against the `locked` line of `monitor-owner`. For `lock-contender`, find the `ReentrantLock$NonfairSync` object and match it against the `Locked ownable synchronizers` section of `lock-owner`.

The markers below are **abbreviated excerpts with addresses replaced by labels**, solely to show where to look; they are not full stdout or the Actuator HTTP format:

```text
"monitor-contender"
   java.lang.Thread.State: BLOCKED (on object monitor)
   - waiting to lock <M> (a java.lang.Object)

"monitor-owner"
   java.lang.Thread.State: WAITING (parking)
   at java.util.concurrent.CountDownLatch.await(...)
   - locked <M> (a java.lang.Object)

"lock-contender"
   java.lang.Thread.State: WAITING (parking)
   - parking to wait for <R> (a ReentrantLock$NonfairSync)
   at java.util.concurrent.locks.ReentrantLock.lock(...)

"lock-owner"
   java.lang.Thread.State: WAITING (parking)
   at java.util.concurrent.CountDownLatch.await(...)
   Locked ownable synchronizers:
   - <R> (a ReentrantLock$NonfairSync)
```

Addresses, thread IDs, internal frame names, and line numbers depend on the run/JDK. What must be preserved during analysis is the relationship between waiter and holder, not the numeric values of a single example.

This example runs standalone to study JVM mechanics. There is no need to add a fake business endpoint just to generate lesson data. In a Spring Boot application, Actuator collects data from the running app's JVM; reading the relationships relies on the exact same concepts.

## 7. Workflow for Investigating a Hung Request

1. **Narrow down the exact timeframe and instance.** Record affected APIs, latency, load, CPU, and dependent resources. A dump outside the error window may not contain the threads you need.
2. **Collect a set of samples.** Keep originals and timestamps; verify HTTP status/exit code to avoid parsing an error response file.
3. **Select the relevant thread group.** Start from pool names, application frames, or wait points; thread names are only hints, not request IDs.
4. **Trace dependencies.** For locks, follow the owner; for queues/latches/futures, find the task or event that must advance it.
5. **Compare samples.** See whether the same threads and stack groups repeat, whether owners change, and whether work completes. Being at the same spot in three samples is a clue worth investigating, not absolute proof of zero progress between samples.
6. **Cross-check other evidence sources.** Monitor contention requires inspecting the locked block; connection waiting requires pool/DB metrics; suspected heavy computation requires CPU/profiler; suspected external service requires traces and timeouts.
7. **Fix the underlying mechanism and re-verify.** Compare latency and completion under equivalent load, not just the count of `WAITING` threads.

Example of a testable hypothesis:

```text
Observation:
Multiple request threads wait on the same monitor.
The owner repeatedly pauses inside an outbound HTTP call.

Hypothesis:
The slow HTTP call is extending the monitor hold time,
forcing other requests to queue up.

Verification:
Inspect the synchronized block, correlate call traces/timeouts,
and re-measure under load after redesigning the state-protection scope.
```

Moving I/O out of a locked region is only appropriate when shared-data correctness is still preserved. Do not delete `synchronized` or change synchronization constructs merely to make `BLOCKED` lines disappear.

If all workers in a pool are waiting on tasks queued into that exact same pool, examine the task dependency structure before simply increasing pool size. Increasing thread count or connection count can shift pressure onto CPU, memory, or the database without resolving the cause.

## 8. Limitations with Virtual Threads on JDK 21

On JDK 21, `ThreadMXBean` manages platform threads. Actuator 3.3 relies on this thread management info, so do not treat the HTTP dump as a complete list of every virtual thread in the application.

When you need to observe virtual threads, use the dump capability built for them. The following example is a PowerShell command for a JDK 21 process; `12345` must be replaced with the actual PID:

```powershell
$javaProcessId = 12345
jcmd $javaProcessId Thread.dump_to_file -format=json "C:\diagnostics\threads-virtual.json"
```

The destination directory must exist and be writable by the target JVM. The file is created inside the target JVM's environment; on Unix/container hosts, use an appropriate absolute path there.

The `Thread.dump_to_file` dump format can list both platform threads and virtual threads, yet it does not carry all the lock/address details of a traditional dump. Therefore, do not apply the monitor-matching procedure from earlier verbatim to every format. When additional evidence on virtual thread execution is needed, pair with JFR matching the JDK version. [Observing virtual threads in Java 21](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html).

Clearly distinguish "does not appear in this dump type" from "does not exist". Nor should you infer that thousands of waiting virtual threads equals thousands of OS threads being tied up.

## 9. Common Errors During Collection and Interpretation

| Symptom or reasoning error | How to handle |
| --- | --- |
| HTTP `404` | Verify right instance, port/base path, endpoint enabled and exposed; check `exclude`. |
| HTTP `401` or `403` | Check authentication/authorization and proxy layer; do not open all endpoints to bypass errors. |
| Connection refused or timeout | Check process, bind address, network/container; if HTTP cannot serve, consider local authorized jcmd. |
| `.json` file contains HTML or error message | Check HTTP status, exit code, and `threads` structure before analyzing. |
| Seeing `WAITING` and concluding a hang | Read the waiting operation, wake-up condition, and actual load. |
| Seeing `RUNNABLE` and concluding high CPU | Cross-check CPU over time and execution profile. |
| Counting only `BLOCKED` to measure all contention | Also check `ReentrantLock`, condition waits, and resource pools. |
| Seeing an owner in `WAITING` and ignoring it | Check the locks it holds and the condition it is waiting on. |
| One sample resembling the previous one and concluding deadlock | Look for a wait cycle and verify progress; it may be valid repeated work. |

Taking a dump is also a unit of work. When an application is overloaded, the HTTP endpoint can be slow, require authentication, or fail to respond; no HTTP response does not automatically prove deadlock. If using jcmd, attach permissions and process visibility in the deployment environment must be appropriate.

A single request can hop across multiple threads when asynchronous processing is used. In that case, logs with correlation/trace IDs are needed to stitch stages together; do not attribute an entire request to one thread name merely because that name appeared in one sample.

## 10. Evidence-Based Self-Check

**Scenario 1:** `queue-consumer` is `WAITING` and the queue is empty, with no incoming tasks. Does anything need fixing?

No sign of error yet. The experiment shows this can be an idle worker. If tasks are waiting yet unprocessed, inspect the path feeding work into the queue and the actual worker pool.

**Scenario 2:** `monitor-contender` is `BLOCKED`, while the owner is `WAITING`. Can the owner be the cause of queueing?

Yes. In the example, the owner awaits a latch while holding the monitor. You must find what opens the latch, rather than ignoring the owner just because it is also waiting.

**Scenario 3:** Two threads are both `WAITING` in `ReentrantLock.lock` and each holds the lock the other needs. Can this be a deadlock?

Yes. The decisive evidence is the wait cycle between the two locks, not the presence of the `BLOCKED` constant.

**Scenario 4:** A `RUNNABLE` thread appears in the same method across three samples. Does that prove an infinite loop?

No. You must correlate CPU, source code, execution duration, and signs of work completion. Sampling can catch the same spot during normal repeated execution.

**Practice task:** run `ThreadDumpLab --hold`, point out the two "waiter → lock holder" edges yourself, one case of waiting for work, and one case of timed waiting. After the program finishes cleanly, explain why the snapshot contains both `BLOCKED` and `WAITING` without a deadlock.
