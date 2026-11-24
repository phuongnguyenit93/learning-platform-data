# Limits of Virtual Threads with CPU, Database Connections, and Pinning Tasks

**Scope:** Java 21+ (virtual threads were standardized in JDK 21 by JEP 444), Spring Boot on the JVM, focusing on Spring MVC/Servlet and JDBC workloads. Distinguish **JDK 21–23** from **JDK 24+**, because JDK 24 introduced a major change to pinning inside `synchronized` code. Standalone Java examples require JDK 21+; illustrative Spring Boot settings target Spring Boot 3.5.x.

**Most important takeaway:** Virtual threads allow an application to hold many **I/O-waiting tasks** using fewer platform threads. They do not make CPUs compute faster, do not automatically increase database connection counts, do not shorten transactions, and do not guarantee that every kind of blocking releases the carrier thread.

## 1. Mechanism: how do virtual threads run on carrier threads?

A **platform thread** usually maps closely to an OS thread. A **virtual thread** is still a `java.lang.Thread`, yet the JVM schedules huge numbers of virtual threads onto a smaller pool of platform threads called **carrier threads**.

- When a virtual thread is **executing Java code on CPU**, it must be **mounted** on a carrier. One carrier cannot execute two compute streams on a single core at the exact same instant.
- When a virtual thread runs many **compatible blocking I/O operations** such as socket waits, JDBC I/O, or `Thread.sleep`, the JVM can **unmount** the virtual thread and return the carrier to the scheduler to run other work. When results arrive, the virtual thread is scheduled back.
- An already-created task can still be **waiting for a carrier**, **waiting for a connection**, **waiting for a lock**, **waiting for I/O**, or **waiting on another system**. A huge virtual-thread count does not mean huge concurrency across every resource.
- When a virtual thread is **pinned** while blocking, it cannot unmount normally, holding the carrier throughout the wait. Frequent, long-lasting pinning can degrade throughput.

~~~text
HTTP requests (many)
   │
   ├── Virtual thread A ── CPU computation ───────► carrier #1 busy
   ├── Virtual thread B ── waiting on socket ─────► unmounted; carrier reused
   ├── Virtual thread C ── waiting on DB conn ────► virtual thread exists, DB pool still bounded
   └── Virtual thread D ── blocked while pinned ──► carrier may be held
                                        │
                                        ▼
                           CPU / DB / external services
                           remain finite resources
~~~

The standard pattern is **one virtual thread per task** with readable synchronous code: `Executors.newVirtualThreadPerTaskExecutor()`. Never build a fixed-size thread pool to reuse virtual threads; to cap concurrency hitting a resource, use **connection pools, semaphores, bulkheads, or controlled queues**.

### Throughput, latency, and concurrency are not the same

- **Latency:** how long a single request takes from start to finish. Virtual threads usually **do not shorten** how long a SQL query runs inside a DB or how long a CPU algorithm takes.
- **Throughput:** completed requests per unit of time. If platform threads previously sat blocked waiting on I/O, virtual threads **can** improve throughput by letting more requests make progress concurrently.
- **Concurrency:** tasks currently active/waiting in the system. Concurrency rising past DB, CPU, or external-service capacity turns into long queues and timeouts.

An approximate reading from **Little's Law** in steady state is `L = λ × W`, where `L` is requests in the system, `λ` is throughput, and `W` is time spent in the system. If throughput stops rising while wait time grows, higher concurrency only reflects **backlog**, not better performance.

## 2. First limit: CPU-bound work

### Why doesn't adding virtual threads create more CPU power?

Heavy computation—encryption, compression, image processing, parsing huge payloads, numerical algorithms, or tight hot loops—needs **real CPU time**. A virtual thread actively computing keeps its carrier busy the whole time. The scheduler can context-switch tasks, yet it cannot invent extra CPU cores.

Suppose a machine has 4 effective CPU cores and 1,000 requests, each requiring exactly **50 ms of CPU** (zero I/O wait). Total demand is `1,000 × 50 ms = 50 s CPU`. The ideal lower bound for the whole batch is `50/4 = 12.5 s`, excluding overhead, GC, contention, and other costs. Spawning 1,000 virtual threads **cannot** turn that batch into 50 ms.

| Workload | What virtual threads improve | Limits that remain |
| --- | --- | --- |
| Heavy HTTP/JDBC/network waiting | Avoid holding OS threads while waiting; can raise waiting request count | Bandwidth, network latency, DB speed, and connection limits |
| Heavy parsing, compression, hashing, encryption | Convenient synchronous code; relatively cheap thread creation | Core count, container CPU quota, GC, and RAM |
| Mixed CPU + I/O | Reuses carrier idle time during I/O waits | CPU phase still bounds throughput when CPU saturates |
| Very large concurrent batches | Simpler task creation than one platform thread per task | Queue sizes, heap, file descriptors, per-task memory, and downstream |

**Signs of a CPU bottleneck:** CPU near actual quota, raising concurrency fails to boost throughput, p95/p99 latency worsens, high GC/CPU time. On Kubernetes, check both **CPU throttling** and `cpu limits`; `availableProcessors()` only helps read the JVM environment and never replaces profiling.

**Proper handling:** optimize algorithms and queries; trim CPU work from request paths; bound expensive computations against core/quota budgets; offload heavy batches to dedicated jobs/workers if needed; benchmark throughput under identical config and load. Never use `Thread.sleep` to simulate CPU work—sleeping is **waiting**, with completely different behavior.

### Is scheduler parallelism a CPU performance knob?

The JVM uses a scheduler to mount virtual threads onto carriers; default parallelism normally matches available processors. Specialized JVM properties such as `jdk.virtualThreadScheduler.parallelism` exist for tuning the scheduler during targeted measurements. **Raising parallelism does not create more CPUs** and is not a default fix for CPU-bound apps. It can increase contention and context switching. Change it only after identifying the bottleneck and benchmarking real load.

## 3. Second limit: connection pools and database capacity

### More virtual threads do not mean more JDBC connections

A JDBC connection involves DB server resources, sockets, session state, and transactions. In Spring Boot with JDBC/JPA, a **DataSource connection pool**—commonly HikariCP—is used. The pool allows **at most a configured number of connections**, regardless of how many virtual threads the server spawns.

Suppose 500 concurrent HTTP requests each use JDBC, and HikariCP allows 10 connections:
1. At most **10 pool connections** can be checked out simultaneously (assuming one connection per request).
2. Remaining requests must **wait** for a connection; their virtual threads stay alive without creating extra DB connections.
3. Only when a request closes/returns its connection to the pool can another request proceed.
4. Waiting past `connectionTimeout` causes HikariCP to throw an acquisition exception; depending on app handling, the request may fail with 5xx or a mapped error code.

**Illustrative math:** holding a connection for 100 ms on average with a 10-connection pool gives a very rough ceiling of `10/0.1 = 100 connection uses/second` **if** connections are utilized continuously and hold times remain 100 ms. That is not an exact QPS forecast: DB queries slow down as concurrency rises, transactions run multiple queries, and locks or other bottlenecks appear. A single request may also check out connections multiple times.

~~~text
          Spring MVC / virtual threads
              500 active requests
                       │
                       ▼
                HikariCP pool
                maximumPoolSize=10
                    │    │
                 10 connections ─────► Database
                    │                    CPU, I/O, locks,
             Remaining requests          limits, query plans
             wait for connection
             (cannot auto-create
              490 connections)
~~~

The connection pool **is itself a limiter** on JDBC connections. You do not need to put an extra `Semaphore(10)` right in front of `getConnection()` just to duplicate the pool's limit of 10; a separate semaphore makes sense only to enforce a **different business limit** (such as capping concurrency for one especially expensive query or across multiple systems sharing a DB).

### Illustrative Spring Boot/HikariCP configuration

When an application has a JDBC datasource and uses HikariCP, you can configure `src/main/resources/application.properties`:

~~~properties
# Option for Spring Boot 3.2+ running on Java 21+
spring.threads.virtual.enabled=true

# Useful if the application relies on virtual daemon threads / scheduled tasks
spring.main.keep-alive=true

# Example configuration; adjust to actual load and DB limits
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.connection-timeout=2000
~~~

- `maximum-pool-size=10`: caps one Hikari pool at 10 connections for one instance; 10 here is an **example value**, not a universal standard.
- `connection-timeout=2000`: waits at most **2,000 ms** to borrow a connection before failing. This is **not** a timeout for the entire SQL query or HTTP request.
- These properties take effect when an actual JDBC datasource/Hikari pool exists; enabling virtual threads alone does not create databases or extra connections.
- Deploying **3 replicas** each with pool max 10 lets this service group use up to **30 connections** concurrently; remember to reserve budget for other apps, admin tools, migrations, and DB limits.
- Release-specific HikariCP defaults can vary with configuration; always inspect effective configuration and Actuator/JMX when tuning.

**Never increase `maximum-pool-size` merely because virtual-thread count grew.** Databases still have finite CPU, IOPS, buffer caches, locks, `max_connections`, transaction throughput, and network bandwidth. Oversized pools increase DB contention and worsen p99 latency. Size pools by measuring active/pending/idle counts, connection wait time, query latency, DB throughput, DB CPU, lock waits, and total connections across all replicas.

### Holding connections/transactions longer causes faster congestion

If a `@Transactional` method queries the DB and then calls a slow external API while the connection stays leased, the connection stays occupied for the entire API wait—even if the virtual thread unmounts cleanly.

~~~java
// Snippet illustrating an anti-pattern; not a standalone runnable program.
@Transactional
public Receipt createReceipt(Request request) {
    Order order = orderRepository.save(new Order(request.id()));
    ShippingQuote quote = shippingClient.fetchQuote(request.address()); // HTTP call may be slow
    order.setShippingFee(quote.fee());
    return receiptRepository.save(new Receipt(order));
}
~~~

Depending on transaction configuration and checkout timing, the snippet above **can** hold a DB connection while waiting on HTTP. When consistency rules permit, move external I/O outside DB transactions, set clear timeouts, and design error handling/compensation. Do not arbitrarily relocate I/O if strict transactional atomicity is required.

Also keep in mind:
- Close `Connection`, `ResultSet`, and `PreparedStatement` properly (or use `JdbcTemplate`/JPA with proper resource management); **connection leaks** exhaust pools.
- Optimize SQL, indexes, query counts, and N+1 issues; never treat virtual threads as a fix for slow queries.
- Bound batches/pagination and configure separate timeouts for queries, statements, transactions, HTTP requests, and connection acquisition.
- Apply backpressure/admission control before queues grow without bound; configure bounded retries with jitter to avoid retry storms when the DB is overloaded.
- JDBC drivers and other libraries may contain native, synchronized, or poorly compatible blocking paths; test with a profiler/JFR on your **actual JDK and driver**.

## 4. Third limit: pinning — when a virtual thread holds its carrier

### What is pinning, and when does it actually hurt?

**Pinning** happens when a virtual thread **cannot unmount from its carrier** during a wait. When a virtual thread blocks while holding its carrier, that carrier cannot run other virtual threads, shrinking the pool of usable carriers.

Distinguish clearly:
- **No pinning:** the virtual thread performs compatible I/O and unmounts while waiting; the carrier is free for other work.
- **Pinning:** while blocked, the carrier remains held. If frequent and long enough, throughput can drop or scheduler starvation can occur.
- **Lock contention:** threads waiting on a mutex/monitor. Locks remain a logical serialization constraint even without pinning; swapping lock types does not make a serial critical section concurrent.
- **Running CPU:** a virtual thread using a carrier for computation is normal; that is **not called pinning** just because the carrier is busy.

### Distinguish accurately between JDK 21–23 and JDK 24+

| JDK version | `synchronized` containing blocking calls | Native/FFM and special runtime cases | Recommended approach |
| --- | --- | --- | --- |
| **21–23** | Blocking inside a `synchronized` method/block **can pin** the carrier | Can still pin | Locate long, frequent blocking spots; shrink lock scopes or use `ReentrantLock` where justified |
| **24+** | **JEP 491** fixes typical monitor/`synchronized` pinning: virtual threads can unmount when blocking inside `synchronized` | Pinning can still occur with native/FFM frames and certain VM/runtime paths; measure | Do not blindly replace every `synchronized`; keep checking JFR and lock contention |

**Do not memorize “every `synchronized` causes pinning” as a permanent Java rule.** That is specifically outdated on JDK 24+. Conversely, do not claim “JDK 24 has zero pinning”: applications or dependencies can still hit native methods, foreign functions, or JVM paths that prevent unmounting.

Example **on JDK 21–23** carrying monitor-pinning risk:

~~~java
// Illustrative snippet; serialization still occurs when multiple tasks share the monitor.
private final Object monitor = new Object();

public void doSomething() throws InterruptedException {
    synchronized (monitor) {
        Thread.sleep(300); // JDK 21–23: may pin the carrier while sleeping
    }
}
~~~

On JDK 24+, **synchronized pinning** is resolved, yet only one thread can still hold the monitor at a time; if many tasks contend on the same monitor, execution remains **serialized**.

An alternative when monitor pinning truly needs removal on JDK 21–23 is `ReentrantLock`:

~~~java
// Illustrative snippet, not a way to make the same critical section run in parallel.
private final java.util.concurrent.locks.ReentrantLock lock =
        new java.util.concurrent.locks.ReentrantLock();

public void doSomething() throws InterruptedException {
    lock.lock();
    try {
        Thread.sleep(300);
    } finally {
        lock.unlock();
    }
}
~~~

`ReentrantLock` lets the virtual thread park without **monitor pinning** on JDK 21–23. Even so, the example **holds the lock for 300 ms**, forcing tasks sharing the lock to queue behind each other. A better optimization—**only when invariants allow**—is shortening lock hold time and keeping long I/O out of locked regions. Do not bulk-replace every brief `synchronized`, as that adds complexity without speeding anything up.

### Situations to test in practice

- Legacy libraries performing I/O inside `synchronized` blocks on **JDK 21–23**.
- JDBC drivers, native libraries, JNI/FFM, or runtime paths holding native frames while blocking, including on JDK 24+.
- Monitor/lock contention or class initialization; not every slowdown is `VirtualThreadPinned`, so cross-check JFR and thread dumps.
- Calling incompatible blocking APIs or blocking calls not cleanly unmounted on your JDK/library/platform.

Pinning **does not corrupt program results** by itself; its impact is on scalability and latency. A rare long event is not necessarily a bottleneck, whereas dozens per second on hot request paths warrant investigation.

## 5. Using virtual threads properly in Spring Boot

In Spring Boot 3.2+ with Java 21+, enable:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

In supported Spring Boot Servlet web configurations, virtual threads can handle requests with embedded Tomcat/Jetty and Spring task-execution integrations. Spring Boot can also auto-configure a virtual-thread `SimpleAsyncTaskExecutor`; `@Async` and scheduling depend on the active executor/scheduler configuration. **If you register custom executors or customize containers**, verify requests/tasks actually run on virtual threads. Never assume every application thread turns virtual automatically.

To check an endpoint **only in test environments**, you can add:

~~~java
// Illustrative controller snippet (Spring MVC); imports/application omitted.
@RestController
class ThreadInfoController {
    @GetMapping("/thread-info")
    public String threadInfo() {
        return "virtual=" + Thread.currentThread().isVirtual();
    }
}
~~~

With virtual-thread configuration and a compatible servlet container, responses are expected to show `virtual=true` for requests on virtual threads. If `virtual=false`, inspect the Java version, web server setup, custom executors, and stack/framework. Do not expose operational probe endpoints as public APIs.

**Notes:**
- With virtual threads enabled, **platform thread-pool size** properties such as certain `spring.task.execution.pool.*` and `server.tomcat.threads.*` settings may no longer apply to executors switched to virtual threads. **Do not** confuse them with JDBC pool limits: `spring.datasource.hikari.maximum-pool-size` **still applies**.
- Virtual threads are **daemon threads**. Spring Boot supports `spring.main.keep-alive=true` so the process does not exit when no non-daemon threads remain—vital for apps relying solely on scheduled/background tasks.
- In Spring WebFlux/reactive pipelines, virtual threads **do not replace the entire event-loop model**; determine the executor for specific blocking steps. This article focuses on synchronous servlet requests.
- `@Transactional`, security context, and MDC logging usually rely on **thread context**. Within a single synchronous execution path on one thread, they follow library contracts. When offloading to `@Async`/another executor, context **does not propagate automatically**; use the framework's proper propagation mechanism.
- Virtual threads do not prevent overload; higher concurrency makes protecting DB pools, remote calls, rate limits, heap, queues, and shutdown cancellation even more important.

## 6. Standalone Java 21 example: many virtual threads, only two “DB connections”

The following example simulates a **2-slot** pool using `Semaphore`. This is **not real DB/JDBC**; the goal is proving that even with 12 virtual threads, tasks concurrently inside the resource-limited section are capped at 2. In production, **HikariCP itself enforces the connection limit**, so you normally do not wrap it in a redundant semaphore.

Create a single file `VirtualThreadLimitsDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public class VirtualThreadLimitsDemo {
    public static void main(String[] args) throws Exception {
        final int jobs = 12;
        final int slots = 2;

        Semaphore simulatedConnections = new Semaphore(slots, true);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();
        List<Future<?>> results = new ArrayList<>();

        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < jobs; i++) {
                results.add(executor.submit(() -> {
                    boolean acquired = false;
                    boolean counted = false;
                    try {
                        simulatedConnections.acquire();
                        acquired = true;
                        int current = active.incrementAndGet();
                        counted = true;
                        peak.accumulateAndGet(current, Math::max);

                        // Simulated I/O wait: holds slot without heavy CPU work.
                        Thread.sleep(40);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new RuntimeException(e);
                    } finally {
                        if (counted) {
                            active.decrementAndGet();
                        }
                        if (acquired) {
                            simulatedConnections.release();
                        }
                    }
                }));
            }

            // get() forces main to wait for results and surface task errors.
            for (Future<?> result : results) {
                result.get();
            }
        }

        System.out.println("jobs=" + jobs);
        System.out.println("simulatedConnectionLimit=" + slots);
        System.out.println("peakWithinLimit=" + (peak.get() <= slots));
        System.out.println("activeAfterCompletion=" + active.get());
    }
}
~~~

**Compile and run** with JDK 21 or newer from the file's directory:

~~~bash
javac VirtualThreadLimitsDemo.java
java VirtualThreadLimitsDemo
~~~

**Exact stdout when all tasks finish normally:**

~~~text
jobs=12
simulatedConnectionLimit=2
peakWithinLimit=true
activeAfterCompletion=0
~~~

Because `Semaphore` has only two permits, `peak` cannot exceed 2. Execution duration and the exact `peak` value (1 or 2 depending on timing) **must not be asserted as fixed constants**; only `peakWithinLimit=true` is the proven invariant. `Thread.sleep(40)` simulates **I/O waiting** rather than measuring CPU/DB; this program is not a JDBC benchmark.

In real apps, replace this model with `DataSource`/HikariCP and proper timeouts. Only consider a dedicated semaphore/bulkhead when you need to cap a **specific heavy operation** tighter than the general connection limit (e.g. allowing at most 3 heavy SQL reports concurrently).

## 7. Spring Boot + JDBC example: connection timeout and transactions

The snippet below is a **Spring MVC/`JdbcTemplate` integration fragment**, not a standalone program: it requires a Spring Boot project, `spring-boot-starter-web`, `spring-boot-starter-jdbc`, a JDBC driver, a datasource, and a real `products(id, name)` table.

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record ProductDto(long id, String name) {}

@Repository
class ProductRepository {
    private final JdbcTemplate jdbc;

    ProductRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    ProductDto find(long id) {
        return jdbc.queryForObject(
            "select id, name from products where id = ?",
            (rs, rowNum) -> new ProductDto(
                rs.getLong("id"), rs.getString("name")),
            id
        );
    }
}

@RestController
@RequestMapping("/api/products")
class ProductController {
    private final ProductRepository repository;

    ProductController(ProductRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    ProductDto get(@PathVariable long id) {
        return repository.find(id);
    }
}
~~~

**What to understand about execution flow:**

~~~text
HTTP request
    │
    ▼
Spring MVC controller on virtual thread (when enabled, supported stack)
    │
    ▼
JdbcTemplate needs a connection
    │
    ├── Pool has slot → check out connection → run query → return connection
    │
    └── Pool out of slots → wait ≤ connectionTimeout → acquire slot or fail
                                    │
                                    ▼
                     DB determines actual SQL speed
~~~

You do not write `new Thread(...)` in the controller to “benefit from virtual threads”: configure the container and executor properly, and request handlers already run inside virtual threads. Accessing the DB from a controller on a virtual thread **does not** make the database execute queries any faster.

With HikariCP/Actuator, track metrics corresponding to **active connections**, **idle**, **pending/waiting threads**, **connection acquisition timeouts**, and **connection usage duration**. Exact metric names depend on Spring Boot/Micrometer versions; check Actuator metadata for your stack.

## 8. Detecting pinning, CPU bottlenecks, and DB bottlenecks

### A. JDK Flight Recorder (JFR)

JFR records `jdk.VirtualThreadPinned` events whenever a virtual thread stays pinned past a threshold; Java documentation cites a default threshold of **20 ms**. Capture data **under problematic load**, since idle runs rarely reproduce contention.

You can launch an application JAR with recording enabled (replace `app.jar` with your actual JAR):

~~~bash
java -XX:StartFlightRecording=filename=virtual-threads.jfr,duration=60s,settings=profile -jar app.jar
~~~

Once the recording finishes:

~~~bash
jfr print --events jdk.VirtualThreadPinned virtual-threads.jfr
~~~

Having **zero events** does not guarantee the system has no issues: load may have been too light, events fell below threshold, JFR missed the window, or the real bottleneck is CPU/DB. On JDK 21–23, detailed pinning stack traces can be printed with an **option applicable only to older JDK releases**:

~~~bash
java -Djdk.tracePinnedThreads=full -jar app.jar
~~~

Starting in JDK 24, this diagnostics story changed with JEP 491; **do not rely on `jdk.tracePinnedThreads` to diagnose JDK 24+**. Prefer JFR, thread dumps, and profilers supporting your active JDK.

### B. Thread dumps for virtual threads

Get the JVM's PID and run:

~~~bash
jcmd <PID> Thread.dump_to_file -format=json thread-dump.json
~~~

This newer dump format lets you inspect virtual threads, stack groups waiting on JDBC/network/locks, and carrier relationships; traditional thread dumps do not all display virtual threads the same way. Combine with SQL slow-query logs, database metrics, CPU profilers, and request traces. Never draw conclusions solely from the number of threads in `WAITING`: virtual threads **are designed to wait cheaply**.

### C. Symptom-based diagnostic table

| Observed symptom | Hypothesis to test | Measurements/evidence | Appropriate action |
| --- | --- | --- | --- |
| App CPU ~100% of quota, throughput flat | CPU-bound or GC/throttling | CPU profiles, GC pauses, throttling, p95 | Optimize computation, limit CPU-heavy concurrency, scale CPU reasonably |
| Hikari active = max, pending high, timeouts | Connection pool/DB bottleneck | Active, pending, acquisition wait, SQL latency | Optimize SQL/transactions, set query timeouts, size pool based on DB |
| App CPU low, DB CPU/lock waits high | DB saturated or lock contention | DB wait events, slow queries, lock graphs | Fix queries/indexes, locks, transactions; do not blame the scheduler |
| Many `jdk.VirtualThreadPinned` events | Carriers held during blocking | JFR stack traces, JDK version | On JDK 21–23 inspect `synchronized`; on JDK 24+ inspect native/VM paths |
| No pinning yet latency is high | Waiting on DB pool, HTTP, rate limits, queues | Tracing and stage timings | Add admission control, timeouts, optimize downstream |
| Raising virtual concurrency spikes RAM | Many tasks, request bodies, `ThreadLocal`/caches, queues | Heap profiles, allocations, live tasks | Bound in-flight count and memory footprint; manage lifecycles |
| Adding virtual threads worsens p99 | Overload, contention, or DB/CPU limit | Load-test concurrency sweeps, p95/p99, error rate | Find peak useful capacity and enforce backpressure |

### D. Designing load tests for valid conclusions

Test with identical payloads, DB data, JVM heap/quotas, replica counts, drivers/JDKs, and warmed-up workloads. Ramp load in steps (concurrency or offered RPS) and record:
1. Completed **throughput**, error/timeout rates, and p50/p95/p99 request latency.
2. **App CPU** (and CPU throttling), GC, RAM, and runnable carriers/threads as needed.
3. **Hikari active/idle/pending**, acquisition wait, timeouts, and **DB CPU/query/lock waits**.
4. **JFR pinned events**, durations, stack traces, and frequencies.
5. Queue depths, in-flight requests, and outbound HTTP wait times.

Compare three baselines: Spring Boot default platform threads, virtual threads on JDK 21, and virtual threads on JDK 24+ (if your environment permits). Never draw conclusions from `Thread.sleep` alone; use workloads with realistic CPU/I/O ratios, queries, and transactions. The goal is finding the **point of highest useful throughput where latency and errors stay acceptable**.

## 9. Common misconceptions

**Misconception 1: “Virtual threads make every endpoint N times faster.”** False. They lower the thread cost of waiting on I/O; CPU-bound or DB-bottlenecked endpoints may see zero speedup.

**Misconception 2: “10,000 virtual threads open 10,000 JDBC connections.”** False. The connection pool and DB determine connection count; a pool of 10 still allows only 10 concurrent slots.

**Misconception 3: “Just crank Hikari pool size way up.”** Larger pools can overload the DB. Budget across all replicas and measure DB capacity.

**Misconception 4: “Any thread inside `synchronized` is definitely pinning.”** False. Pinning requires blocking and depends on JDK version. JDK 24+ resolves monitor-related pinning; brief `synchronized` blocks are not automatically harmful.

**Misconception 5: “Converting all `synchronized` to `ReentrantLock` makes the system more concurrent.”** False. Locks still guard critical sections and tasks still wait on one another; change only actual pinning or long-held lock hotspots.

**Misconception 6: “Low CPU means no bottleneck.”** Exhausted DB pools, DB lock waits, slow remote services, or carrier pinning can crush throughput while app CPU remains low.

**Misconception 7: “Zero `VirtualThreadPinned` events means virtual threads are perfect.”** False. JFR uses a threshold and only captures while recording; other bottlenecks still apply.

**Misconception 8: “Every `@Async`, scheduler, MVC, and WebFlux task runs on virtual threads automatically when enabled.”** Execution still depends on stack, auto-configuration, and custom executors. Verify `Thread.currentThread().isVirtual()` in the actual code path.

**Misconception 9: “With virtual threads, timeouts and backpressure aren't needed.”** On the contrary, high counts of waiting requests make timeouts, retry budgets, connection budgets, and admission control essential.

**Misconception 10: “Virtual thread count has no RAM impact.”** Each thread is lighter than a platform thread, yet still carries stack/objects/lifecycle state; a million tasks holding request bodies or buffers can consume massive heap.

## 10. Adoption checklist and self-check questions

Before enabling in production, answer: **Where is the application bottlenecking? Is the workload mostly I/O wait? Is the DB pool sized and monitored? Are we on JDK 21 or 24+? Are there unusual JNI/driver/lock paths? Are requests/errors/timeouts/queues bounded?** If you do not know, measure before optimizing.

Self-check:

1. A server has 8 cores and 2,000 HTTP requests, each doing 100 ms of continuous CPU computation. Will spawning 2,000 virtual threads finish all of them in 100 ms? Why or why not?
2. HikariCP `maximum-pool-size=8`, and 100 virtual threads concurrently request a JDBC connection. At most how many connections can be checked out from **this pool** at once? What do the remaining 92 requests do?
3. A SQL query holds a connection for 200 ms and the pool has 10 slots. Why doesn't “raising thread count” make queries run 10× faster?
4. JDK 21 has `Thread.sleep(250)` inside `synchronized` on a hot request path. Which tools find pinning? When upgrading to JDK 24, what changes, and what **does not** change?
5. `spring.threads.virtual.enabled=true` is set, yet an `@Async` task still runs on a platform thread. Which custom executors/configs should you check?
6. A request opens a transaction, queries the DB, makes a 2-second HTTP call, and then commits. Why don't virtual threads fix high Hikari pending counts?

**Suggested answers:** (1) No: 200 seconds of total CPU work are still needed, giving an ideal lower bound of ~25 seconds on 8 cores excluding overhead; (2) at most 8, while the rest wait for a slot or time out; (3) the pool and DB remain finite, and hold time did not shrink; (4) JFR `jdk.VirtualThreadPinned` and thread dumps; JDK 24 eliminates monitor pinning, yet lock serialization and native pinning cases remain; (5) custom executor beans, container setup, schedulers/stacks; (6) the transaction may hold a JDBC connection during the HTTP wait, so transaction boundaries must be tightened.

### Official documentation

- Oracle: [Virtual Threads — Java 21](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) — mechanics, diagnosing pinning, `Semaphore`, `ThreadLocal`.
- Oracle: [Virtual Threads — Java 24](https://docs.oracle.com/en/java/javase/24/core/virtual-threads.html) — behavior after `synchronized` changes, JFR/thread dumps.
- Oracle: [Significant Changes in JDK 24](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html) — JEP 491.
- Spring Boot 3.5: [SpringApplication — Virtual threads](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html) — enabling, JDK requirements, keep-alive, and pinning notes.
- Spring Boot 3.5: [Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html) — auto-configured executors/schedulers.
- HikariCP: [Configuration](https://github.com/brettwooldridge/HikariCP#gear-configuration-knobs-baby) — `maximumPoolSize`, `connectionTimeout`, and pool limits.