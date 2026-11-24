# 18.6. Correlating In-Flight Requests, Pools, Queues, and Dependency Resources

## Objectives

A Java service experiencing rising **p95/p99 latency** often exhibits many unfinished requests, busy thread pools, long queues, or waits on underlying resources (databases, HTTP/gRPC, Redis, message brokers) at the same time. Yet those metrics describe **different stages of the same pipeline**. Locating the bottleneck requires correlating them **over the same time window, the same request scope, and in layer order**, rather than looking at any single metric in isolation.

This lesson focuses on **I/O and latency** in Java 17+: from request ingress, through workers/executors and queues, to connection pools and dependent services, and finally returning a response, timing out, or failing. The goal is to know **where requests are sitting, what they are waiting on, why "in-flight" count is rising, and when to apply backpressure instead of enlarging pools**.

### Key takeaways

- Distinguish **in-flight requests**, **active workers**, **executor queues**, **pending connection acquisitions**, **leased/idle connections**, **downstream in-flight calls**, and **dependency saturation**.
- Read **instantaneous gauges** and **cumulative counters/histograms** accurately; recognize that a single request can appear in multiple layers and must not be summed as separate requests.
- Use **Little's Law** to check the relationship between throughput, concurrency in flight, and latency under appropriate conditions.
- Diagnose bottleneck patterns: server executors, DB connection pools, DB queries/locks, downstream HTTP, pre-gateway queues, retry/fan-out, and CPU/GC pressure.
- Design instrumentation sufficient to separate **queue wait time**, **connection wait time**, **I/O time**, and **actual processing time**, with a standalone runnable Java 17+ example.

## 1. Diagram: where does a request travel?

A typical synchronous Java pipeline:

```text
Client
  |
  v
Load balancer / gateway   [accepted, queued, rejected, timed out]
  |
  v
HTTP server / ingress     [requests in-flight, request duration]
  |
  +--> dispatch / executor pool
  |       |
  |       +--> worker active?
  |       +--> executor queue waiting?
  |
  +--> business logic
          |
          +--> DB/HTTP/Redis client pool
          |       |
          |       +--> leased / active connections
          |       +--> idle connections
          |       +--> pending acquisition / acquire timeout
          |
          +--> downstream service
                  |
                  +--> in-flight calls / concurrency limit
                  +--> queue / CPU / DB / locks / errors / latency
  |
  v
Response success / error / cancellation / timeout
```

Not every architecture follows this exact path:

- **Blocking servlet:** one request typically holds one worker while executing or waiting on synchronous I/O; however, an async servlet can release the worker before the request finishes.
- **Reactive/event-loop:** thousands of requests can be in-flight with only a handful of event-loop threads; **in-flight ≠ active threads**.
- **Fan-out:** one request calls 3 downstreams concurrently or retries multiple times, so **3 downstream calls do not equal 3 inbound requests**.
- **Streaming/long polling:** a request can stay open for a long time while using little CPU/worker capacity, depending on the framework.
- **Shared pools:** schedulers/background jobs may share an executor or connection pool with requests; never attribute all queuing and CPU solely to HTTP requests.

The first step is to **map out the exact flow and measurement boundaries** of the system under investigation, including gateways/proxies and dependencies. A metric named "active" is meaningful only once you know whether it counts requests, threads, connections, or queries.

## 2. Comparison table of key metrics

| Metric | Measurement layer and actual definition | Question it answers | Do NOT infer |
| --- | --- | --- | --- |
| **Inbound in-flight requests** | Requests accepted by the service that have not yet finished at measurement time | How many requests have not returned a response yet? | How many threads are burning CPU or how many DB connections are used |
| **Request arrival rate** | New requests/second, computed from counter deltas over time | How fast is load arriving? | How fast the system actually completes work successfully |
| **Completion/throughput rate** | Finished requests/second (broken down by success/error/timeout) | How fast is the system draining work? | Does not by itself prove requests meet SLA |
| **Executor active workers** | Workers running tasks; `ThreadPoolExecutor.getActiveCount()` is an **estimate** | How many tasks are holding workers? | That those workers are using CPU; they may be blocked on DB |
| **Executor queued tasks** | Tasks placed into the work queue that have not started running | How large is the backlog ahead of workers? | That every queued task is an inbound HTTP request |
| **Executor pool size/max** | Current workers and configured ceiling | Is there room to spawn more workers? | That growing the pool means downstream capacity exists |
| **Connection leased/active** | Connections checked out to callers per client pool semantics | How many pool connections remain available? | That every active connection is actively running SQL or transferring data |
| **Connection idle** | Open connections not currently checked out to callers | Does the pool have immediate spare capacity? | That downstream is fast, or that no requests are waiting |
| **Pending acquisition** | Callers waiting to borrow a connection/permit from the pool | Is there contention before calling DB/remote? | That downstream SQL/HTTP processing time itself is long |
| **Downstream in-flight calls** | Ongoing RPC/SQL/HTTP calls to a dependency | How much concurrency is hitting the dependency? | That it equals inbound requests (due to retries/fan-out) |
| **Queue/pool wait duration** | Wait time distribution per stage | Which stage drives p95/p99 up? | That stage percentiles can be summed to get end-to-end p99 |
| **Request end-to-end duration** | From ingress boundary to recorded response/error/cancellation | How long did users wait at this service boundary? | Automatic per-stage breakdown without spans |

**Gauges** (`in-flight`, `active`, `queued`, `pending`) are point-in-time snapshots. **Counters** (`accepted_total`, `completed_total`, `rejected_total`, `timeout_total`) are cumulative totals; to get rates, take **deltas over a window** and handle process restarts. **Histograms** for latency show distributions and tails; verify whether the metric includes all outcomes (success, error, timeout, rejection).

**Do not add blindly:** a single request can simultaneously contribute `in-flight=1`, `active worker=1`, and `connection pending=1`. Summing those gives 3 even though there is only **one inbound request**. Conversely, a request waiting in the executor queue does not show up in active workers yet, while still counting as in-flight if the HTTP layer already accepted it.

## 3. Aligning metrics by timestamps and denominators

Never compare values from different time windows or instances: request rate at 10:00:00 and queue depth at 10:05:00 can reflect different traffic; per-pod metrics do not automatically match cluster-wide metrics.

### 3.1. Choosing a minimal metric set

Over an example **30-second** window per instance/pod:

1. **Ingress:** accepted rate, completed rate, success/error/timeout/reject rates, current in-flight, request duration p50/p95/p99.
2. **Application executor:** pool size, active workers, max, queue size/capacity, rejected count, task queue wait histogram, and task execution duration.
3. **Dependency client pool:** active/leased, idle, max, pending waiters, acquisition duration/timeouts, connection hold duration.
4. **Remote dependency:** RPC/SQL in-flight, p95/p99 latency, errors/timeouts, server queues/DB locks/CPU/disk/connection limits where telemetry exists.
5. **Host/runtime:** CPU throttling, JVM CPU/GC, heap, thread count, I/O/network; avoid mistaking CPU waits for DB waits.
6. **Traces/logs:** trace ID, attempt/retry count, cancellation/deadlines, timestamps at each stage.

Label sensibly by service, instance, endpoint/route, dependency, and **pool name**. Avoid high-cardinality tags like request ID, user ID, or raw URLs; correlation IDs belong in traces/logs, not metric labels.

### 3.2. Little's Law: in-flight requests, throughput, and latency

In a **steady-state system**, with consistent measurement boundaries over a long enough window:

```text
L = λ × W

L = average number of work items inside the measured boundary
λ = average arrival/completion rate (work items per second, in steady state)
W = average time each item spends inside that boundary (seconds)
```

**Hypothetical** example: an endpoint steadily processes **100 requests/s** with an average service residence time of **0.25 s**:

```text
L = 100 requests/s × 0.25 s = 25 requests in-flight (average)
```

If measured average in-flight is **120** instead of **25** for the same boundary, before declaring a bug check: did latency rise? Do both numbers cover the same window and request cohort? Are long polling/cancellations/streaming included? Is a burst or growing backlog keeping the system **out of steady state**?

The same applies to a **queue** alone when defined consistently: average queued tasks equals task throughput × average queue wait under steady state. **Never plug p99 into `L = λW`**, because `W` must be the **mean** residence time; multiplying average rate by p99 does not give expected in-flight count.

### 3.3. Backlog and inflow/outflow imbalance

For a simple queue with no drops/retries/cancellations and consistent item counting:

```text
Δbacklog ≈ arrivals - departures

If λ_in > μ_out persists: queue grows until full/rejected/timed out.
```

**Hypothetical** example: over 10 seconds **1,200 tasks arrive** and **900 tasks are dequeued by workers**: the backlog ahead of workers grows by about **300 tasks** assuming no drops/cancellations/rejections. However, if backlog capacity is capped at **100**, excess tasks may be rejected, block the producer, or run on the caller depending on the rejection policy. Thus **a queue sitting flat at 100 does not mean the system is healthy**: it may be pinned at the cap and actively rejecting.

To translate into service throughput, distinguish **task dequeue** from **request completion**. One request may spawn multiple tasks, and task completion does not guarantee the response was sent.

## 4. Request layer: when does in-flight rise?

**In-flight requests** are defined from a start boundary (e.g., handler receives request) to an end boundary (response completes or is cancelled). Keep counting consistent:

- Increment the gauge **once** at the chosen valid request acceptance boundary.
- Decrement the gauge **once** on every exit path: success, error, timeout, cancellation, closed connection; use `try/finally` for synchronous handlers and completion callbacks for async.
- For async/streaming, **do not decrement when the handler method returns** if the response has not finished yet.
- If a gateway accepts 10,000 requests while the service only admits 6,000, the service's `in-flight` misses the 4,000 requests waiting or rejected **upstream of the service**.
- If `active requests` is measured only in an HTTP framework filter, know whether requests queued ahead of the executor (before entering the filter) are counted.

To detect queuing upstream of the service, check **gateway pending/connection backlog**, service accepted rate, upstream rates, and client timeouts. Low server in-flight paired with high client latency does not clear the service: requests may not even be reaching handlers yet.

### High in-flight can represent four very different phenomena

1. **Legitimate heavy traffic:** throughput and concurrency rise proportionally, latency stays steady, few timeouts; possibly valid load.
2. **Server worker queue:** requests accepted but waiting for workers; `executor.queued` and queue wait increase.
3. **Blocked I/O:** workers or async requests stay in-flight waiting on connections, DB locks, or remote sockets; CPU may be low.
4. **Long-lived requests:** streaming/SSE/long polling keep connections open safely; segment metrics by route and traffic class.

Looking at `in-flight=500` alone cannot tell these four scenarios apart.

## 5. Worker/executor layer: busy pools and accumulating queues

For a `java.util.concurrent.ThreadPoolExecutor` wired to request processing, available APIs include:

| API | Meaning |
| --- | --- |
| `getPoolSize()` | Current number of worker threads |
| `getCorePoolSize()` / `getMaximumPoolSize()` | Configured core/max limits |
| `getActiveCount()` | **Approximate** count of workers executing tasks; not CPU usage |
| `getQueue().size()` | Number of tasks waiting in the executor work queue at query time |
| `getQueue().remainingCapacity()` | Remaining queue capacity if supported by the queue |
| `getCompletedTaskCount()` | **Approximate** total completed tasks |
| `getTaskCount()` | **Approximate** total scheduled tasks |

**Mind the queue policy:**

- With a **bounded `ArrayBlockingQueue`** and finite max workers, a full pool/queue can **reject tasks** per `RejectedExecutionHandler`. Maintain a dedicated rejection metric and map rejections to HTTP errors/backpressure.
- With an **unbounded `LinkedBlockingQueue`** (e.g., `Executors.newFixedThreadPool`), tasks can pile up indefinitely, inflating latency and memory without early rejection. When the queue always accepts tasks, setting `maximumPoolSize` above core has **no effect** under that queuing rule.
- With `SynchronousQueue`, no backlog sits in a traditional queue; if direct handoff fails, the pool must spawn a new worker or reject.
- `CallerRunsPolicy` executes tasks on the **submitting thread**, pushing pressure back onto callers; the executor's `active worker` count will not reflect tasks running on caller threads.
- If the app uses **ForkJoinPool, virtual threads (newer JDKs), event loops**, or custom framework dispatchers, do not map `ThreadPoolExecutor` metrics 1-to-1. Check how that framework exposes queuing and concurrency.

**Active worker means "occupying a slot," not "burning CPU."** A worker can be waiting on `DataSource.getConnection()`, `Socket.read()`, `Future.get()`, `LockSupport.park()`, or a downstream RPC. Increasing workers while existing workers block on the DB pool often shifts the bottleneck straight down to the DB and grows connection wait queues.

### Signs of executor saturation

```text
active ~= max
queued rising
task_queue_wait p95/p99 rising
accepted_rate > task_start_rate across multiple windows
rejected_total rising when queue is full
```

These point to a **backlog ahead of workers**. Next, determine **why workers stay busy so long**: CPU-bound work, blocked I/O, lock contention, GC, slow downstream, or traffic mix. Never raise worker counts before checking stacks and dependency metrics.

## 6. Connection pool layer: active/idle/pending differ

Suppose a request needs a DB connection from a connection pool:

```text
worker processing request
    |
    +-- acquire(connection)
    |       |
    |       +-- idle available   -> return connection immediately
    |       +-- can open new     -> connect/authenticate (can be slow)
    |       +-- max reached      -> wait in pending/acquire queue
    |
    +-- connection acquired      -> send query/transaction
    |       |
    |       +-- DB executing / waiting on locks/disk/CPU
    |
    +-- release connection       -> return to pool
```

Common metrics exposed by pools (HikariCP, JDBC pools, HTTP client pools, Redis pools, etc.—**exact names vary by framework/version**):

- **max/size:** configured max pool size or currently open connections; the two are not always equal.
- **active/leased:** connections checked out to callers. A caller might **not be running any query** yet still hold a connection in a long transaction or due to a leak.
- **idle:** connections open and ready to borrow immediately at snapshot time.
- **pending/waiting:** callers waiting to borrow a connection. Can exceed worker count with async callers or non-blocking APIs; counted differently across pools.
- **acquire wait duration:** time waiting to obtain a connection, including slot wait and connection setup depending on instrumentation.
- **usage/hold duration:** how long the caller holds the connection after borrowing; not purely SQL execution time.
- **acquire timeout / errors:** failures to borrow before deadline; typically cascade into request failures.

**Typical pool bottleneck pattern:** `active ~= max`, `idle=0`, `pending>0`, `acquire_p95` rising, worker stacks clustered at acquire. This indicates a bottleneck in **connection availability**. To find the root cause, inspect whether connections are held by slow queries/locks, long transactions, connection leaks, or an undersized max pool relative to legitimate load.

**Do not infer backward** that DB CPU is high just because `pool active=max`. A DB can have low CPU while connections are held by locks, slow I/O, network waits, or idle transactions. Cross-check DB active sessions, wait events, locks, query latency, and connection counts on both sides.

### An approximate capacity sanity check

Suppose **8 connections** are kept busy continuously, each checkout held for **80 ms** on average:

```text
Ideal ceiling ~= 8 connections / 0.080 s = 100 checkouts/s
```

This formula uses **average connection hold time**, not end-to-end request latency; it is an intuitive upper bound under sustained load and ideal conditions, **not a throughput guarantee**. If a request performs multiple DB calls or retries, checkout rate differs from requests/s. If the DB itself handles only 60 queries/s, enlarging the pool to 16 will not make the DB handle 200 queries/s; it can worsen contention.

## 7. Dependency layer: beyond connection counts

Your application's pool can look healthy while downstream is still slow due to:

- **DB:** lock waits, long transactions, slow queries/missing indexes, connection setup, CPU/disk I/O, replication, checkpoints, connection/session limits.
- **HTTP/gRPC dependency:** server queues, connection setup, DNS, TLS, TCP retransmits, network latency, upstream rate limits; HTTP/2 multiplexing carries many concurrent streams over one connection so "connection count" ≠ "request count."
- **Redis/cache:** fast pool acquire yet slow commands, blocking operations, network latency, or saturation on the dependency's single-threaded event loop.
- **Message broker:** producer batching/queues/acks, in-flight requests, retries, and broker partitions/replication; publish latency is distinct from consumer processing.
- **Threads/CPU/GC inside your own app:** outbound calls can look slow when workers lack CPU to send/read responses or callbacks are delayed by scheduling; never blame downstream blindly for every wait.

Observe **the same dependency on both client and server sides**: outbound request counts, client latency/errors/timeouts; server in-flight, queues, CPU/locks/query metrics. A dependency may respond slowly due to real server work, or the client may spend time **before sending** waiting on pools, circuit breakers, or rate limiters.

### Retries and fan-out skew counts

Suppose one inbound request calls 3 HTTP endpoints in parallel and retries one endpoint twice:

- **Inbound requests = 1**.
- **Outbound attempts can reach 5** (3 initial + 2 retries), not necessarily all concurrent.
- **Downstream in-flight** at an instant can exceed inbound in-flight, though not equal total attempts.
- If retries fire right when a dependency slows down, rising attempts can **amplify load** (retry storm) and prolong in-flight/queues.

Tag `dependency`, `operation`, `attempt`, `timeout`, and `retry_reason` in traces/logs; keep metric labels to bounded-cardinality dimensions. Use **retry budgets, exponential backoff with jitter, and overall deadlines**, avoiding unbounded retries at every layer.

## 8. Setting timeouts, queue capacities, and backpressure end-to-end

Three design mistakes that easily cause latency explosions:

1. **Unbounded acceptance:** requests queue for seconds after the client deadline has already expired; workers waste effort on work that no longer has value.
2. **No end-to-end timeout budget:** 200 ms waiting for a worker + 500 ms waiting for a DB connection + 3 s query + another 3 s retry = huge p99, even though each individual timeout looks "reasonable."
3. **Enlarging every pool at once:** more workers create more callers waiting on connections; more connections overload the DB; larger queues merely disguise failures as long waits.

### Good practices

- **Bounded queues and admission control:** protect CPU/RAM and make overload fail clearly; define rejection behavior (HTTP 429/503, `Retry-After` per policy) instead of hanging indefinitely.
- **Propagate deadlines across layers:** if a request has a 1.5 s total budget, executor wait, connection acquisition, queries, and retries must share that budget rather than resetting 1.5 s at each layer.
- **Queue wait timeout/cancellation:** when a client cancels, ensure unstarted tasks and futures/outbound calls are cancelled appropriately; release resources in `finally`/callbacks and do not assume cancel automatically aborts a downstream DB query.
- **Size pools to the weakest resource:** add server workers only when CPU/I/O and downstreams have headroom; tune connection pools alongside DB/server limits.
- **Bulkheads/circuit breakers/rate limits:** isolate slow dependencies; prevent one API from filling shared executors/connection pools and taking down the whole service.
- **Isolate request classes:** streaming vs. short requests, reads vs. writes, and heavy batch vs. interactive traffic often need separate pools/budgets/queues.
- **Monitor successes, errors, and rejections together:** success throughput must not hide rising timeouts/rejections; watch both saturation and user-facing SLAs.

Backpressure makes a system **fail fast in a controlled way** when capacity is exhausted, which is usually better than accepting unboundedly and triggering cascading timeouts. Still, response codes and retry rules depend on the API contract; never treat every 503 as safe to retry immediately.

## 9. Java 17: simulating four requests across two waiting layers

This example **runs standalone** on JDK 17+ with no DB or network required. Its goal is to observe **three distinct states**:

- Two executor workers actively running tasks.
- Two requests sitting in the executor queue without a worker yet.
- One worker holding the "connection" while the second worker waits for a permit from the dependency pool.

`Semaphore` merely **simulates a connection limit**; it is not a real JDBC connection pool. Readings from `getActiveCount()` and `getQueueLength()` are **approximate** while state is changing.

Create **`RequestPoolSnapshot.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class RequestPoolSnapshot {
    private static final ThreadPoolExecutor WORKERS =
            new ThreadPoolExecutor(
                    2, 2, 0L, TimeUnit.MILLISECONDS,
                    new ArrayBlockingQueue<>(2),
                    new ThreadPoolExecutor.AbortPolicy());

    // Simulate a pool with exactly 1 connection/permit.
    private static final Semaphore DEPENDENCY = new Semaphore(1, true);
    private static final CountDownLatch RELEASE = new CountDownLatch(1);
    private static final CountDownLatch FIRST_LEASED = new CountDownLatch(1);
    private static final CountDownLatch SECOND_STARTED = new CountDownLatch(1);
    private static final AtomicInteger IN_FLIGHT = new AtomicInteger();

    private static void accept(boolean first, boolean second) {
        IN_FLIGHT.incrementAndGet();
        try {
            WORKERS.execute(() -> {
                boolean leased = false;
                try {
                    if (second) {
                        SECOND_STARTED.countDown();
                    }
                    DEPENDENCY.acquire();
                    leased = true;
                    if (first) {
                        FIRST_LEASED.countDown();
                    }
                    RELEASE.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    if (leased) {
                        DEPENDENCY.release();
                    }
                    IN_FLIGHT.decrementAndGet();
                }
            });
        } catch (RejectedExecutionException e) {
            // Rejected, so no longer part of the admitted in-flight set.
            IN_FLIGHT.decrementAndGet();
            throw e;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try {
            accept(true, false);
            if (!FIRST_LEASED.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First task did not start");
            }

            accept(false, true);
            if (!SECOND_STARTED.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Second task did not start");
            }

            // Two workers are busy. The next two tasks enter the queue.
            accept(false, false);
            accept(false, false);

            // Best-effort wait so the second worker queues on the Semaphore.
            for (int i = 0; i < 100 && !DEPENDENCY.hasQueuedThreads(); i++) {
                Thread.sleep(10);
            }

            System.out.println("inFlight=" + IN_FLIGHT.get());
            System.out.println("workersActiveApprox=" + WORKERS.getActiveCount());
            System.out.println("executorQueued=" + WORKERS.getQueue().size());
            System.out.println("dependencyLeased=" + (1 - DEPENDENCY.availablePermits()));
            System.out.println("dependencyPendingApprox=" + DEPENDENCY.getQueueLength());
        } finally {
            RELEASE.countDown();
            WORKERS.shutdown();
            if (!WORKERS.awaitTermination(5, TimeUnit.SECONDS)) {
                WORKERS.shutdownNow();
            }
        }
    }
}
```

Compile and run:

```bash
javac --release 17 RequestPoolSnapshot.java
java RequestPoolSnapshot
```

Under normal execution, **`inFlight=4`**, **`executorQueued=2`**, and **`dependencyLeased=1`** are designed to be deterministic at the observation point. **Typical** output:

```text
inFlight=4
workersActiveApprox=2
executorQueued=2
dependencyLeased=1
dependencyPendingApprox=1
```

`getActiveCount()` and `getQueueLength()` are observational/approximate APIs; under unusual scheduler conditions or interrupted execution, the `Approx` lines can vary. If the JVM lacks resources to start threads within 5 seconds, the program fails fast instead of pretending the snapshot is valid.

**Why the metrics do not add up to eight requests:**

- `inFlight=4` covers all 4 admitted tasks: 2 running, 2 queued in the executor. It is the program's own counter.
- `workersActiveApprox=2` means 2 workers occupy slots: one holds the permit and waits on `RELEASE`, while the second waits to acquire the permit. **Neither is burning CPU.**
- `executorQueued=2` are **two other requests** that have not been picked up by a worker yet—not the threads waiting on the semaphore.
- `dependencyLeased=1` represents **one resource** checked out, and `dependencyPendingApprox=1` represents the second worker waiting to acquire it. Those two numbers do not count extra inbound requests.
- Looking only at `workerActive=2` might tempt someone to think "the server pool is busy, add threads"; yet **what holds the workers** here is the dependency permit and simulated wait.

The experiment also highlights measurement limits: `getQueue().size()` counts tasks waiting **in this executor**, not gateway queues, DB pending counts, message brokers, or async requests outside the executor. When replacing the mock semaphore with real HikariCP/HTTP clients, use each pool's native metrics.

## 10. Measuring per stage in a real application

To avoid lumped metrics, instrument at clear boundaries:

```text
t0 ingress_received
t1 task_enqueued
t2 task_dequeued / execution_started
t3 dependency_acquire_started
t4 dependency_acquired
t5 outbound_call_started
t6 outbound_call_completed
t7 dependency_released
t8 response_completed
```

Useful quantities for a linear synchronous request:

| Measurement | Interval | Meaning |
| --- | --- | --- |
| Admission/dispatch delay | `t1 - t0` | Before enqueue/dispatch |
| Executor queue wait | `t2 - t1` | Waiting for a worker |
| Dependency acquisition wait | `t4 - t3` | Waiting for connection/permit or pool connect |
| Downstream call duration | `t6 - t5` | Call duration seen by HTTP/JDBC client |
| Connection hold duration | `t7 - t4` | Leased time, including other work if caller holds it |
| End-to-end service duration | `t8 - t0` | Total latency within the service scope |

**Notes:**

- These intervals **do not sum cleanly in every architecture**: extra logic, async overlap, parallel dependencies, or retries may sit between them.
- Use **`System.nanoTime()`** for elapsed durations within the same JVM, never `System.currentTimeMillis()`, since wall clocks can jump.
- **Per-stage histograms** combined with distributed tracing are how you tell whether p99 comes from queuing, acquisition, or downstream. **Never add stage p99s** to "compute total p99"; percentiles are not linear.
- For async flows, declare boundaries clearly and close metrics when **the response actually finishes or cancels**, not merely when the handler thread returns.
- If a request times out before a worker dequeues it, provide proper removal/cancellation and timeout metrics; do not let stale work execute indefinitely.
- With N attempts, record attempt index and total budget; do not collapse retries into "one slow query."

### Inspecting stacks and JFR to see what workers are waiting on

On HotSpot JDK 17, illustrative PID `12345`:

```bash
jcmd 12345 Thread.print -l
jcmd 12345 JFR.start name=io-diag settings=profile duration=60s filename=io-diag.jfr
```

After the recording finishes:

```bash
jfr summary io-diag.jfr
jfr print --events "jdk.SocketRead,jdk.SocketWrite,jdk.ThreadPark" io-diag.jfr
```

- Thread dumps locate worker stacks in `DataSource.getConnection()`, JDBC drivers, `Socket.read()`, `CompletableFuture.join()`, or lock waits; **one snapshot cannot prove prolonged waiting**.
- JFR captures socket I/O, thread parks, and synchronization depending on which events were **enabled and emitted** in the recording. `jfr summary` confirms the file actually contains events before analyzing.
- Low CPU paired with many `WAITING`/`TIMED_WAITING` threads may indicate I/O or condition waits rather than a CPU bug. Conversely, `RUNNABLE` does not guarantee a thread is on CPU because of native I/O.
- When downstream DB is suspected, collect **DB-side query/lock/session metrics** and traces, since Java thread dumps cannot explain why the SQL server is slow.
- Run `jcmd ... JFR.start` and event settings respecting operational permissions, file size, and overhead; avoid leaving heavy capture settings on uncontrolled in production.

## 11. Bottleneck inference matrix

| Signals occurring **together** | Priority hypothesis | Next verification and actions |
| --- | --- | --- |
| In-flight ↑, executor queue ↑, active≈max, dependency pending low | Bottleneck ahead of workers or slow worker execution | Thread dumps, CPU/GC, queue wait histogram; inspect per-task work, pool/CPU quota |
| In-flight ↑, active≈max, DB pool active=max, idle=0, pending ↑ | Workers held while waiting for connections | Connection-acquire p95, transaction duration, JDBC stacks, DB wait events; do not add workers yet |
| DB pool active=max, pending=0, DB latency ↑ | Connections held long or DB slow, not necessarily pool admission bottleneck | Query plans, DB locks/CPU/I/O, connection hold duration |
| Short executor queue, HTTP in-flight ↑, async dependency waits ↑ | Async I/O or slow remote dependency | Client spans, remote p95/p99, retry counts; do not use active threads as proxy for in-flight |
| Gateway pending ↑, app request rate low | Queuing/admission upstream of the app | Gateway accept/backlog, load balancing, network, app capacity, pod readiness |
| Pending connections ↑, acquire timeouts ↑ yet low DB CPU | Transactions holding connections, locks, or network, not necessarily DB CPU | DB locks/sessions/idle-in-transaction, client connection usage |
| Outbound attempts grow faster than inbound rate | Retry/fan-out amplification | Retry counts, attempt spans, deadlines/budgets, circuit breakers |
| App request rate rises, throughput flat, queue=max, rejects ↑ | Service overloaded / bounded queue full | Admission policy, rate limits, true capacity, 429/503 |
| p99 ↑, CPU throttled ↑, GC/threads waiting on scheduling | Container CPU quota pressure | cgroup CPU stats, CPU limits, thread states, GC pauses |
| p99 ↑, in-flight ↑ yet throughput remains steady | Latency or long-lived requests rose; possible traffic-mix shift | Breakdown by endpoint, streaming class, stage latency, and in-flight count |

**Never pick a hypothesis just because one row "matches."** Establish temporal ordering and find the first stage where queuing/waiting started before inferring deeper causes.

## 12. Illustrative scenario: the DB pool is the bottleneck, not the thread pool

**Hypothetical** metrics for a Java service during a p99 spike:

| Metric | Before spike | During spike |
| --- | ---: | ---: |
| Inbound completed/s | 80 | 78 |
| In-flight requests | 24 | 150 |
| Request p99 | 280 ms | 2.4 s |
| Server active workers / max | 18 / 64 | 63 / 64 |
| Executor queued tasks | 0 | 70 |
| DB pool active / max | 7 / 12 | 12 / 12 |
| DB pool idle | 5 | 0 |
| DB pool pending | 0 | 45 |
| DB connection-acquire p95 | 5 ms | 850 ms |
| DB server query p95 | 25 ms | 240 ms |

### Layer-by-layer reasoning

1. **Ingress:** completed rate barely changed while in-flight jumped → requests are spending much longer inside the service; bottleneck location not yet proven.
2. **Executor:** workers are near max and the queue has a backlog. Tasks lack free workers, yet this alone does not prove adding workers helps.
3. **DB connection pool:** active=max, idle=0, pending=45, acquire wait p95=850 ms → many workers are blocked trying to borrow a DB connection. This is a **directly observed** bottleneck.
4. **DB query:** p95 also rose from 25 ms to 240 ms, so longer-held connections can starve the pool. Investigate **slow queries/locks/DB load/transaction holds**, or traffic mix shifting to heavier queries.
5. **Priority path:** trace slow requests, inspect the DB server, timeouts/retries, and connection hold time; shorten queries/transactions if possible. **Do not raise server worker max from 64 to 256 right away**, as that will simply pile more callers into DB pending.
6. **After tuning:** compare at the same load and sampling window: DB acquire p95, pending, executor queue, success throughput, request p95/p99, timeouts/rejects, and DB server metrics.

**Do not assume p99=2.4 s can be computed by adding 850 ms acquisition p95 + 240 ms query p95.** Those are percentiles from different scopes/distributions; trace **the same requests** end-to-end to explain tail latency.

## 13. A 10-minute investigation workflow when p99 spikes

1. **Isolate the exact service/endpoint/pod and time window.** Inspect load balancer, request attempts, throughput, errors/timeouts/rejections, and p50/p95/p99. Determine whether clients timed out before or after the service began processing.
2. **Verify the definition of in-flight:** at which ingress is it counted? Does it include async/streaming, cancellations, or pre-handler queues? Avoid relying on an undefined metric.
3. **Measure the executor:** active/max, queue size/capacity, rejected count, queue-wait duration; separate a "capped queue that stopped growing" from a truly empty queue.
4. **Measure dependency pools:** active/max, idle, pending, acquisition wait/timeouts; keep separate pools distinct by name instead of lumping into generic "DB connections."
5. **Inspect dependent resources:** queries/locks/remote latency, server queues, CPU, disk, pool/session limits; link the exact dependency via traces.
6. **Capture appropriate thread samples and JFR:** see whether workers are burning CPU, waiting on pools, or waiting on sockets; avoid concluding from thread state alone.
7. **Run a quick sanity check:** throughput × **mean** latency ≈ mean in-flight (in steady state); inspect queue arrivals/departures and backlog over the same window.
8. **Check CPU quotas/GC, retry amplification, and lock contention.** A slow dependency cascade can originate from CPU throttling or GC inside the service itself.
9. **Choose low-risk interventions:** limit request inflow, cancel stale work, align per-stage timeouts, isolate slow dependencies; fix slow queries/leaks; tune pool sizes only after checking end-to-end capacity.
10. **Re-measure before and after:** identical workload and route/dependency; inspect tail latency, success throughput, queues/pending, errors, resource utilization, and cost.

Every statement in a report should cite **a metric/trace at a specific timestamp**, its measurement boundary, and tested hypotheses. Never re-tune pools based on a single snapshot or unaligned charts.

## 14. Common misconceptions

1. **"500 in-flight means 500 worker threads are running."** False for async, queued requests, and long-lived connections.
2. **"Active workers near max means CPU is near 100%."** False: workers can be blocked on connection pools or I/O.
3. **"Executor queue is growing so increase max threads."** Not necessarily; if workers are waiting on a DB pool, adding workers usually pushes contention downstream.
4. **"DB pool active=max proves the DB is executing max queries."** False: leased connections can be held by transactions/logic not currently issuing queries.
5. **"No pending connections means the DB is not slow."** False: already-leased connections can be stalled on SQL, locks, or network for a long time.
6. **"Pool has 20 connections so at most 20 inbound requests."** False for requests not hitting the DB, async multiplexing, and multiple checkouts per request; scopes differ.
7. **"Stage A p99 + stage B p99 = request p99."** False; percentiles do not add linearly and stages can overlap.
8. **"Little's Law uses p99 latency."** False: it uses **averages** under valid steady-state assumptions.
9. **"Queue stays flat at max without rising, so the system is stable."** False: it may be continuously rejecting, cancelling, or timing out.
10. **"Just making the queue huge will absorb all spikes."** It may simply trade explicit rejections for timeout failures and higher RAM usage.
11. **"A client timeout immediately cancels the DB query."** Not guaranteed; explicit cancellation propagation is required.
12. **"One request equals one downstream call."** False with fan-out, retries, streaming, and background work.
13. **"Throughput includes only 2xx responses."** Only if the metric explicitly defines it that way; when measuring departure rate, include all relevant outcomes.
14. **"HTTP request latency has nothing to do with the gateway."** When queuing happens upstream of the service, service metrics can miss time users already spent waiting.
15. **"The Semaphore demo is real HikariCP."** No: the demo merely illustrates two separate queues, without real SQL, sockets, or connection lifetimes.
16. **"One thread dump is enough."** Insufficient: snapshots must align with queue/pool/duration timelines to avoid mistaking a brief wait for a chronic bottleneck.

## 15. Self-check questions

**Question 1.** A service has 200 in-flight requests, executor active=16, queued=20. Can you conclude 164 requests were lost?  
**Answer:** No. Remaining requests may be executing asynchronously, waiting on dependencies, streaming, or sitting at stages outside that executor. Check each metric's definition and traces.

**Question 2.** DB pool max=10, active=10, idle=0, pending=35, acquisition p95 rising. Will adding server workers fix the root bottleneck?  
**Answer:** Not guaranteed, and it usually increases pending further. Investigate connection hold time, DB queries/locks, transactions, and end-to-end sizing first.

**Question 3.** Steady throughput is 120 req/s and mean latency is 0.5 s. What average in-flight count does Little's Law predict?  
**Answer:** `L = 120 × 0.5 = 60`, assuming consistent boundaries and steady state. Do not replace mean latency with p99.

**Question 4.** Workers active=max while CPU is low, and thread dumps show many workers waiting in `DataSource.getConnection()`. What does this suggest?  
**Answer:** Workers are holding thread slots while waiting for connections. Measure pending/acquire p95, active/max, and DB-side metrics to find the real cause.

**Question 5.** Queue size stays flat at 100/100 while `rejected_total` climbs steeply. Is the bottleneck gone?  
**Answer:** No. The queue is full and new tasks are being rejected; inspect rejection rate, deadlines, throughput, and capacity.

**Question 6.** One HTTP request calls 3 services and retries one of them twice. Is inbound=5?  
**Answer:** No. Inbound=1; outbound attempts can reach 5. Keep attempt metrics separate from request metrics.

**Question 7.** Request p99=2 s, acquisition p99=800 ms, query p99=900 ms. Can you conclude the "other" portion is always 300 ms?  
**Answer:** No. Percentiles from different distributions do not add or subtract linearly; inspect traces of the same requests.

**Question 8.** Increasing the DB pool from 8 to 32 when DB server CPU is already 100% causes query latency to rise. Will throughput necessarily increase?  
**Answer:** No. Higher concurrency can raise DB contention/queuing and worsen tail latency; measure real capacity.

## References

- [Java SE 17 — `ThreadPoolExecutor`: pool size, active count, queue, rejection policies](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 17 — `Semaphore`: available permits and queue-length estimates](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Java SE 17 — `CountDownLatch`: coordinating concurrent experiments](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Oracle JDK 17 — `jcmd`: `Thread.print` and `JFR.start`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Oracle JDK 17 — `jfr`: `summary` and `print`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html)
- [Little (1961), "A Proof for the Queuing Formula: L = λW"](https://doi.org/10.1287/opre.9.3.383)
- [Micrometer — Meter Types: Gauge, Counter, Timer](https://docs.micrometer.io/micrometer/reference/concepts.html)
