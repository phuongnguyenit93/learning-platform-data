# Application Hang: Thread Dumps, Deadlocks, and Dependency Timeouts

A compute application can remain running yet stop processing requests: users see spinning loaders indefinitely, APIs stop responding, queue backlogs climb, or health checks fail. This state is commonly called an *application hang*. The cause may sit inside the process—such as a deadlock, thread pool exhaustion, lock contention, or a CPU-spinning loop—or in a dependency such as a database, HTTP service, DNS, storage, or message broker.

Accurate diagnosis combines three perspectives: **thread dumps** show what threads are executing or waiting on; **deadlock analysis** uncovers cyclic resource waits that cannot self-resolve; and **dependency timeout analysis** pinpoints which stage of an external call the application is waiting on. This lesson focuses on collecting evidence, reading symptoms, and safely restoring service on compute workloads.

## 1. Recognizing an application hang

An application hang does not necessarily mean the process has died. The process can stay alive with its port open and low CPU while requests fail to complete. Common symptoms include:

- New requests consistently time out or suffer sharp latency spikes.
- Health checks fail to receive a response within their deadline.
- In-flight requests rise while throughput falls.
- Queue backlog or oldest message age climbs.
- Thread pools, connection pools, or semaphores hit their limits.
- CPU nears 100% due to tight loops, lock spinning, or continuous retries.
- CPU drops abnormally low because most threads are waiting on locks, I/O, or dependencies.
- The service recovers only after a restart, yet the incident recurs as load increases.

Distinguish hangs from other failure states:

| State | Indicators | Investigation direction |
|---|---|---|
| Process crash | PID disappears or non-zero exit code | Crash logs, core dumps, OOM killer, service manager |
| Application hang | Process stays alive yet work makes no progress | Thread dumps, locks, pools, dependencies |
| Overload | Throughput continues while latency and queues grow with load | CPU, memory, thread/connection pools, capacity |
| Dependency outage | Many requests stall on the same external service | Timeouts, DNS, network, service health |
| Deadlock | A group of threads waits on each other in a cycle | Thread dumps and lock ownership |
| Resource starvation | Finite resources are completely held | Thread pool, DB connections, file descriptors, semaphores |

A single metric alone is insufficient. Low CPU can signal waiting threads, or it can simply mean the application receives no traffic. High CPU can reflect valid processing, or it can indicate a retry storm or infinite loop.

## 2. What are threads and thread dumps?

A thread is an execution unit inside a process. Java applications typically maintain many threads for request handling, background jobs, schedulers, garbage collection, and runtime tasks. Each thread has its own stack showing the chain of executing methods or the exact point where it is waiting.

A **thread dump** is a snapshot of all threads at a point in time, typically containing:

- Thread name and ID.
- Thread state such as RUNNABLE, BLOCKED, WAITING, or TIMED_WAITING.
- Thread stack trace.
- Locks or monitors the thread holds or waits for.
- Synchronizer details, depending on the tool and runtime.
- Deadlocks detected by the JVM, if any.

A thread dump captures evidence at a single instant. One dump alone may not distinguish a normal brief wait from a long-term stall. Capture multiple dumps a few seconds apart to observe whether thread states progress.

## 3. Thread states in Java

Common Java thread states:

| State | Meaning | Signals to watch |
|---|---|---|
| RUNNABLE | Thread is running in the JVM or waiting for an OS-level resource | Identical stacks repeating across dumps can indicate a loop or stuck native call |
| BLOCKED | Thread is waiting to acquire an intrinsic monitor to enter a synchronized block | Multiple threads waiting on the same lock indicate lock contention |
| WAITING | Thread is waiting indefinitely for another thread or wake-up signal | `Object.wait`, `Thread.join`, `LockSupport.park` |
| TIMED_WAITING | Thread is waiting with a time bound | `sleep`, timed wait, timed park, or timed join |
| NEW | Thread was created but not yet started | May be normal at certain moments |
| TERMINATED | Thread has finished | No longer participates in processing |

`RUNNABLE` does not guarantee a thread is actively burning CPU. The JVM uses this state both for executing threads and certain threads waiting on native/OS resources. Correlate stack traces, per-thread CPU, and multiple dumps.

`WAITING` threads are not errors by default. Idle worker threads waiting on an empty queue, schedulers awaiting their next tick, or threads awaiting signals can all be normal. What matters is which threads hold needed resources and whether requests make progress.

## 4. Collecting thread dumps on the JVM

Before restarting a hung JVM, collect thread dumps if conditions allow. This preserves evidence that a restart will wipe from memory.

### 4.1. Using jcmd

Find the JVM PID and print a thread dump:

~~~bash
jcmd -l
jcmd <pid> Thread.print -l > thread-dump-1.txt
~~~

Depending on the JDK and user permissions, attach commands must run under the same user or with sufficient privileges for the target process. Use `jcmd` help to check options supported by your JVM version.

### 4.2. Using jstack

~~~bash
jstack -l <pid> > thread-dump-1.txt
~~~

Depending on JDK version and JVM state, `jstack` may fail to attach. Avoid hammering an overloaded host with repeated heavy attach commands; collect deliberately and save output where disk space is sufficient.

### 4.3. Using SIGQUIT on Linux

For HotSpot JVMs on Linux, you can send `SIGQUIT`:

~~~bash
kill -3 <pid>
~~~

Typically the JVM prints the thread dump to the process's standard error, which is usually captured by the service manager or container runtime logs. `SIGQUIT` in this case tells the JVM to emit a dump rather than terminating it. Output location depends on how the service was launched and how stdout/stderr are redirected.

### 4.4. Capturing multiple dumps for comparison

A common practice is capturing three dumps 5–10 seconds apart, if the system tolerates it:

~~~bash
jcmd <pid> Thread.print -l > thread-dump-1.txt
sleep 5
jcmd <pid> Thread.print -l > thread-dump-2.txt
sleep 5
jcmd <pid> Thread.print -l > thread-dump-3.txt
~~~

This interval is illustrative only. For long-running requests, a different spacing may be needed. The goal is to observe whether threads advance in stack frames, locks, and states or remain frozen.

Protect thread dumps as sensitive operational data: stack frames can expose usernames, internal URLs, SQL queries, file paths, or application values inadvertently placed in thread names or arguments. Restrict read access, never attach dumps publicly, and enforce retention policies.

## 5. Reading a thread dump systematically

When opening a dump, do not read sequentially from top to bottom. Target high-signal markers first:

1. Locate any JVM-reported deadlock section.
2. Count threads by state and group by name/pool.
3. Look for large clusters of threads with identical stack traces.
4. Locate `BLOCKED` threads and the locks they are waiting for.
5. Identify which thread holds each awaited lock.
6. Look for stacks involving network, database, file I/O, or pool acquisition.
7. Compare the same threads across multiple dumps to see if stacks advance.
8. Correlate with per-thread CPU, request latency, pool metrics, and application logs.

Thread dumps can be huge. Search by `BLOCKED`, `deadlock`, pool names, package names, or suspected classes. Always preserve exact thread names and IDs when comparing across dumps.

### 5.1. Example of a thread waiting on a lock

Illustrative dump excerpt:

~~~text
"api-worker-17" #82 prio=5 os_prio=0 tid=0x... nid=0x... BLOCKED
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.OrderService.updateInventory(OrderService.java:142)
        - waiting to lock <0x00000006c1234560>
        - locked <0x00000006c1234500>
        at com.example.OrderService.process(OrderService.java:91)
~~~

Thread `api-worker-17` is waiting to acquire monitor ending in `4560` while holding monitor ending in `4500`. Find which other thread holds the monitor it wants. If many workers wait on the same monitor, requests can queue up even when CPU stays low.

### 5.2. Example of a thread waiting on a dependency

~~~text
"http-client-worker-4" #63 prio=5 os_prio=0 tid=0x... nid=0x... WAITING
   java.lang.Thread.State: TIMED_WAITING
        at java.util.concurrent.CompletableFuture.get(...)
        at com.example.InventoryClient.fetch(InventoryClient.java:88)
        at com.example.OrderService.process(OrderService.java:120)
~~~

This stack shows the thread waiting on a future result. That alone does not prove a deadlock. Check what completes the future, whether dependency calls have timeouts, whether connection pools are exhausted, and whether callback threads remain available.

## 6. What is a deadlock?

A deadlock occurs when two or more threads each hold a resource another thread needs, forming a wait cycle that cannot break on its own. Example:

- Thread A holds lock L1 and waits for lock L2.
- Thread B holds lock L2 and waits for lock L1.
- A cannot proceed to release L1 because it is waiting for L2.
- B cannot proceed to release L2 because it is waiting for L1.

~~~mermaid
flowchart LR
    A[Thread A holds Lock L1] -->|waits for| L2[Lock L2]
    L2 --> B[Thread B holds Lock L2]
    B -->|waits for| L1[Lock L1]
    L1 --> A
~~~

Within this cycle, neither thread makes progress. Requests relying on those threads hang or time out.

### 6.1. Java deadlock example

The following snippet illustrates two threads acquiring two locks in opposite order:

~~~java
public class DeadlockExample {
    private static final Object LOCK_A = new Object();
    private static final Object LOCK_B = new Object();

    public static void main(String[] args) {
        Thread first = new Thread(() -> {
            synchronized (LOCK_A) {
                pause();
                synchronized (LOCK_B) {
                    System.out.println("first completed");
                }
            }
        }, "first-thread");

        Thread second = new Thread(() -> {
            synchronized (LOCK_B) {
                pause();
                synchronized (LOCK_A) {
                    System.out.println("second completed");
                }
            }
        }, "second-thread");

        first.start();
        second.start();
    }

    private static void pause() {
        try {
            Thread.sleep(100);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
~~~

If `first-thread` acquires `LOCK_A` before `second-thread` acquires `LOCK_B`, and each then awaits the other lock, deadlock occurs. `Thread.sleep` in the example merely increases reproducibility; the root cause is inconsistent lock acquisition ordering.

### 6.2. Identifying deadlocks in thread dumps

The JVM can detect certain monitor/synchronizer cycles and print a section such as `Found one Java-level deadlock`. When you see this notice:

- Identify all participating threads.
- Record the locks each thread holds and waits for.
- Locate the matching code via stack traces.
- Determine lock acquisition ordering across different code paths.
- Check whether locks are held while performing network, database, or callback calls.

Absence of a deadlock section in a dump does not prove the application is not hung. Thread pool starvation, dependency timeouts, lock contention, or deadlocks inside native libraries may not be caught by Java-level deadlock detection.

## 7. Bottlenecks easily mistaken for deadlocks

### 7.1. Lock contention

Multiple threads compete for the same lock while one thread can still acquire it and make progress. This is contention, not necessarily deadlock. Indicators include many threads `BLOCKED` on the same monitor while one thread holds it.

Remediation options include shortening critical sections, reducing shared mutable state, lock striping/sharding, or using appropriate concurrent data structures. Avoid merely adding more threads, as that can increase lock wait queues.

### 7.2. Thread pool starvation

Thread pool starvation happens when all workers in a pool are occupied by tasks waiting on sub-tasks submitted to the very same bounded pool. For example, a task in the pool synchronously calls `Future.get()` on a child task submitted to the same fixed pool; if every worker does this, no worker remains to run the child tasks.

Common symptoms:

- Active pool count hits its maximum.
- Task queue grows while throughput stalls.
- Many threads wait simultaneously on `Future.get`, `join`, or semaphores.
- No clear monitor lock cycle exists.

Remediation: avoid blocking synchronously on child tasks in the same pool, isolate pools by workload type, use asynchronous composition, or bound nesting depth. Separate pools also require sizing and backpressure; creating too many pools can exhaust resources.

### 7.3. Connection pool exhaustion

If an application cannot acquire a connection from its DB/HTTP pool, requests stall before ever sending the query or request. Causes include an undersized pool, connection leaks, slow queries, or dependencies failing to return connections.

Check active/idle/pending connections, acquisition wait times, long-held connections, and timeout logs. Raising pool size while the database is already overloaded can worsen the incident.

### 7.4. Queue or semaphore bottlenecks

Workers may wait on semaphores, bounded queues, or rate limiters. If producers enqueue faster than consumers drain, queues grow continuously. If consumers hold permits too long or fail to release them on exceptions, other threads can wait indefinitely.

Check queue depth, enqueue/dequeue rates, permit usage, permit hold duration, and exception handling paths.

## 8. Analyzing dependency wait times

A single request can wait across multiple stages before receiving a result. Setting only an outer global timeout may be insufficient if an inner operation lacks a timeout or ignores cancellation.

For an HTTP client, stages may include:

1. DNS resolution.
2. Waiting to acquire a connection from the pool.
3. TCP connect.
4. TLS handshake.
5. Sending the request.
6. Waiting for response/read.
7. Reading the body and processing results.

For a database, stages include waiting for a connection, executing the query, waiting on locks, transferring results, and committing transactions. For queues, stages include waiting for messages, holding lease/visibility timeouts, processing, and acknowledging.

### 8.1. Timeouts to distinguish

| Timeout | What does it bound? | Example failure if unconfigured |
|---|---|---|
| DNS timeout | Name resolution duration | Requests hang when resolver stops responding |
| Connection pool acquire timeout | Time waiting for an idle connection | Requests pile up when pool is exhausted |
| Connect timeout | TCP establishment duration | Long waits when endpoint is unreachable |
| TLS handshake timeout | TLS negotiation duration | Stalls when proxy or peer fails to finish handshake |
| Read/response timeout | Time waiting for response data | Threads stay pinned when server or network stalls |
| Write timeout | Time spent sending data | Uploads or socket writes hang |
| Query/statement timeout | DB statement execution duration | Long-running queries or lock waits |
| Request/call deadline | Total budget for one business operation | Cumulative steps exceed client tolerance |
| Transaction timeout | Maximum transaction lifetime | Transactions hold locks/connections too long |

Exact names and semantics depend on the library. A read timeout may bound the gap between two reads rather than the total duration of the entire response. Read client documentation and test actual timeout behavior.

### 8.2. Overall deadline budgeting

Suppose an API has a 2-second deadline. If each dependency is independently allowed a 2-second wait, a request calling three services sequentially can stretch over several seconds. Propagate the remaining deadline across layers and budget time per step.

Illustrative example:

| Stage | Example budget |
|---|---:|
| Authentication and input handling | 150 ms |
| Pool wait and call to service A | 500 ms |
| Database query | 700 ms |
| Response completion and buffer | 300 ms |
| Total | 1,650 ms |

The remainder of the deadline absorbs variance and overhead. This is illustrative only; timeouts should reflect SLOs, actual latency distributions, and dependency resilience. Never let summed independent timeouts exceed the request's overall deadline.

### 8.3. Retries can worsen an outage

Retries help with transient glitches, yet unbounded or synchronized retries can trigger a retry storm. When a dependency is already overloaded, many clients retrying together amplify load and prolong the outage.

Principles:

- Retry only errors classified as transient.
- Use exponential backoff and jitter.
- Enforce limits on retry count and total retry budget.
- Retry only idempotent operations or requests with idempotency keys.
- Respect remaining deadlines; do not start retries with no useful time left.
- Avoid retrying simultaneously at every layer if doing so multiplies request volume.
- Record retry counts and reasons to detect retry storms early.

## 9. Circuit breakers, bulkheads, and backpressure

Timeouts bound wait duration; complementary resilience patterns prevent one failing dependency from taking down the entire application.

### 9.1. Circuit breaker

Common circuit breaker states:

- **Closed:** lets requests pass while monitoring failure rates.
- **Open:** temporarily short-circuits calls to the dependency when failure thresholds trip.
- **Half-open:** allows limited probe requests to check whether the dependency has recovered.

Circuit breakers need tuned thresholds, sampling windows, open durations, and half-open policies. Too sensitive, and healthy dependencies get blocked; too loose, and cascading failures spread unchecked.

### 9.2. Bulkhead

Bulkheads isolate resources by dependency or workload type. For example, an API calling both a payments service and a recommendations service uses two separate pools. When recommendations slow down, they cannot consume all workers reserved for payments.

Bulkheads apply to thread pools, connection pools, semaphores, queues, or concurrency caps. Isolation must pair with quotas and capacity planning.

### 9.3. Backpressure

Backpressure throttles incoming work when downstream stages cannot keep up. Rather than accepting unbounded work and letting queues and memory explode, the system slows producers, rejects early with an appropriate status code, or buffers in a bounded durable queue.

Monitor queue depth, queue age, rejection rates, and consumer throughput to pinpoint bottlenecks.

## 10. OS tools for corroborating evidence

Thread dumps reveal internal JVM state, yet OS telemetry is needed to see how the process uses CPU, memory, disk, and network.

### Linux

~~~bash
# Process overview and per-thread CPU/memory
top -H -p <pid>

# List threads of a process
ps -L -p <pid> -o pid,tid,psr,stat,pcpu,comm

# CPU and I/O over time
pidstat -p <pid> -t 1
iostat -xz 1

# Memory and paging
vmstat 1

# Sockets and connection states
ss -tanp

# File descriptor limits
cat /proc/<pid>/limits
ls /proc/<pid>/fd | wc -l
~~~

`top -H` and `ps -L` identify which threads consume CPU. `pidstat` tracks thread/process activity over intervals. `iostat` exposes storage latency; `ss` inspects TCP connections and socket states. Ensure tools are installed and run with sufficient privileges to inspect the process.

### Windows

Use Task Manager, Resource Monitor, Performance Monitor, and Process Explorer to inspect per-thread CPU, handles, wait chains, and I/O. Event Viewer correlates service failures and OS errors. For JVM workloads on Windows, still capture thread dumps using the matching JDK tools.

Never diagnose a deadlock solely from low CPU or high thread counts. Combine OS metrics with thread dumps and dependency telemetry.

## 11. Workflow for investigating a hung application

A sound workflow preserves evidence before altering process state.

### Step 1: Define scope and impact

- Does the incident affect one instance or the entire service?
- All requests or only one endpoint/job?
- When did it start, and does it align with a deployment, scaling event, restart, or config change?
- How did error rate, latency, throughput, and queue backlog change?
- Are healthy backends available to absorb shifted traffic?

### Step 2: Check dependencies and resource pools

- Does the DB connection pool show pending requests or active connections at max?
- Does the HTTP client pool hold leased connections for abnormally long durations?
- Are DNS, connect, TLS, or response latencies abnormal?
- Did queue depth, message age, or consumer counts shift?
- Are any semaphores, rate limiters, or bounded queues full?

### Step 3: Capture multiple thread dumps

- Record PID, timestamps, host/instance ID, and application version.
- Capture 2–3 thread dumps spaced at an appropriate interval.
- Store files with restricted permissions.
- Do not restart immediately if evidence can be captured safely.
- If attach fails, record the error and switch to another supported method.

### Step 4: Group threads

- Search for deadlock reports.
- Count `RUNNABLE`, `BLOCKED`, `WAITING`, and `TIMED_WAITING`.
- Group identical stacks by pool and call site.
- Identify threads holding locks, waiting on locks, or waiting on futures.
- Cross-check which threads consume high CPU in OS metrics.

### Step 5: Correlate with logs and traces

Use request IDs, trace IDs, thread names, timestamps, and instance IDs to find stalled requests. Check logs to see whether requests are stuck on DB, HTTP clients, queues, DNS, or locks. Traces reveal which spans consume the bulk of elapsed time.

### Step 6: Choose impact mitigation

Depending on the cause, drain traffic away from the instance, temporarily lower concurrency, pause new job intake, scale capacity, relieve dependency load, or perform a drained restart. Never blindly enlarge thread pools, connection pools, or timeouts; doing so can shift pressure onto another resource.

### Step 7: Verify after remediation

Monitor latency, error rates, throughput, active threads, pool wait times, queue age, and dependency health. Confirm new requests complete and backlogs shrink. Preserve before/after evidence for root cause analysis.

## 12. Investigation example: API hangs from an exhausted DB connection pool

Suppose a Java API begins timing out after traffic rises. CPU sits around 25%, HTTP worker threads near their limit, and the DB connection pool reports `active=max` with rising pending waiters.

Thread dumps show many workers at a similar stack:

~~~text
"http-nio-8080-exec-31" #91
   java.lang.Thread.State: TIMED_WAITING
        at java.util.concurrent.locks.AbstractQueuedSynchronizer...
        at com.zaxxer.hikari.pool.HikariPool.getConnection(...)
        at com.example.OrderRepository.load(OrderRepository.java:74)
        at com.example.OrderService.getOrder(OrderService.java:52)
~~~

This shows workers waiting for a connection from the pool. It is not enough by itself to prove a pool leak. Verify:

1. Are active connections held by long transactions or slow queries?
2. Is any code path failing to close connections/result sets on exceptions?
3. Is the database experiencing lock waits, high CPU, or near-max connection counts?
4. Is a connection acquisition timeout configured?
5. Do thread dumps show other threads holding connections while waiting on HTTP calls or locks?
6. Do pool metrics show connections being returned after requests finish?

Fixes may involve patching connection leaks, optimizing queries, shortening transactions, or capping concurrency. Enlarge pool size only if the database has spare capacity and overall connection limits permit. If the database is already overloaded, adding connections can worsen latency.

## 13. Investigation example: deadlock from lock ordering

Suppose an API experiences sudden latency spikes, requests fail to complete, and CPU stays nearly idle. Three thread dumps show two threads frozen in identical states:

- `inventory-worker-1` holds the `Inventory` lock and waits for the `Order` lock.
- `order-worker-2` holds the `Order` lock and waits for the `Inventory` lock.

Once JVM dumps confirm a deadlock cycle, waiting longer rarely resolves the stuck threads. Preserve the thread dumps, pinpoint the code paths, and mitigate impact by shifting traffic or restarting the instance per safe runbooks if no runtime recovery exists.

Long-term fixes:

- Enforce a consistent lock acquisition order across all code paths.
- Never perform network/database calls while holding internal locks.
- Keep critical sections short.
- Avoid invoking callbacks or untrusted code inside `synchronized` blocks.
- Use timeouts/`tryLock` where business logic permits and handle lock-acquisition failures.
- Write concurrency tests and monitor lock contention under representative load.

## 14. Preventing application hangs

Application design should bound waits and resources from the start:

- Set explicit timeouts for DNS, pool acquisition, connect, TLS, read/write, queries, and requests.
- Propagate remaining deadlines across services instead of setting unbounded independent timeouts.
- Use retries with backoff, jitter, and attempt limits; avoid retrying non-idempotent calls.
- Isolate thread pools and connection pools by dependency/workload type when needed.
- Bound queues, concurrency, and in-flight requests.
- Avoid synchronously blocking on child tasks submitted to the same bounded thread pool.
- Never hold locks while calling external dependencies.
- Design jobs with idempotency, checkpoints, and cancellation.
- Configure graceful shutdown to drain requests and workers before restarts.
- Monitor pool utilization, wait times, active threads, blocked threads, and queue age.
- Run load tests to locate concurrency limits and saturation points before production.

### 14.1. Configuring timeouts from SLOs

Timeouts should reflect SLOs and dependency latency percentiles rather than arbitrary guesses. For example, if an API SLO is 1 second, a dependency cannot have a 10-second read timeout without cancellation or an overall deadline. Budget time per step while reserving room for serialization, network transit, and response assembly.

Overly short timeouts cause false failures during minor normal traffic bumps; overly long timeouts keep threads and connections pinned. Measure p50, p95, p99, timeout rates, and retry rates before tuning.

### 14.2. Observing threads and pools

Useful metrics for JVM services:

- Thread counts by state and pool name.
- Executor active/idle threads and queue size.
- Rejected task counts.
- Lock contention or monitor blocked time where supported.
- DB/HTTP pool active, idle, pending, and acquisition latency.
- In-flight requests, latency, and timeouts per dependency.
- GC pauses, heap occupancy, and allocation rates.
- Per-process/per-thread CPU and OS load average.

If thread counts climb steadily, check for thread leaks or unbounded pools. If thread counts stay flat while active workers max out and queues grow, suspect saturation. If many threads wait on the same lock, analyze lock ownership.

## 15. Security when collecting and handling evidence

Thread dumps, heap dumps, core dumps, and logs can contain sensitive data. Before collecting or sharing:

- Store files in directories readable only by incident responders.
- Never attach dumps to public tickets or repositories.
- Do not send raw files externally without checking data-handling policies.
- Enforce retention windows and delete copies once no longer needed.
- Record timestamp, PID, instance ID, JVM version, and collector identity.
- Avoid running heavy profilers or dumps when the system is severely resource-starved.
- Heap dumps can be huge and contain sensitive objects; capture only with a specific memory hypothesis and ample disk space.

When an urgent restart is needed to restore service, balance evidence preservation against user impact. Whenever feasible, quickly grab minimal thread dumps and metrics right before restarting.

## 16. Application hang troubleshooting checklist

- [ ] Defined scope, start time, and affected workloads.
- [ ] Correlated deployments/changes, logs, metrics, and traces.
- [ ] Checked CPU, memory, disk I/O, network, and process/thread counts.
- [ ] Checked thread pools, DB/HTTP connection pools, queues, and semaphores.
- [ ] Collected multiple thread dumps with clear timestamps and PIDs.
- [ ] Checked for deadlock reports, `BLOCKED` threads, and lock owners.
- [ ] Identified thread groups with identical stacks or waiting on futures/dependencies.
- [ ] Verified DNS, pool acquire, connect, TLS, read/write, and query timeouts.
- [ ] Verified retries, backoff, deadlines, and cancellation.
- [ ] Checked worker idempotency/checkpoints if jobs were interrupted.
- [ ] Selected proper impact mitigation without blindly enlarging pools.
- [ ] Verified latency, error rate, throughput, and backlog after remediation.
- [ ] Secured and stored thread dumps/logs according to policy.
- [ ] Documented root cause, corrective actions, and prevention steps.

## 17. Conclusion

Application hangs can stem from deadlocks, lock contention, thread pool starvation, connection pool exhaustion, or slow dependencies. Thread dumps reveal where threads are running or waiting; consecutive dumps separate transient pauses from stalled states. Deadlocks must be confirmed via lock cycles and code paths; threads waiting on dependencies must be correlated with timeouts, pool metrics, logs, and traces.

To troubleshoot effectively, capture evidence prior to restarts whenever possible, inspect both the JVM and the OS, pinpoint the exact resource being held, and enforce deadlines across every dependency. Combining consistent lock ordering, pool isolation, bounded queues, capped retries, backpressure, and graceful shutdown prevents cascading hangs and supports controlled recovery on compute workloads.
