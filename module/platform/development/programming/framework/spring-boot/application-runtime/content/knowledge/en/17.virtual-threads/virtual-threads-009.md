# Verifying Shutdown, Resource Cleanup, and External System Limits When Using Virtual Threads

**Topic:** Spring Boot Application Runtime → **Virtual Threads**. This lesson explains how to verify that an application using **virtual threads** can genuinely stop, interrupt work, release held resources, and avoid exceeding limits of external databases/APIs/brokers. The focus is not “how many threads can be created”, but **lifecycle, bounded admission, concurrency limits, timeouts, interruption, cleanup, job outcomes, and recoverability**.

**Lab version:** **Java 21+** (virtual threads have been an official feature since Java 21), **Spring Boot 3.5.x**, Spring Web, Maven. Spring Boot 3.5 recommends Java 24+ for a better virtual threads experience; the example below still compiles on **JDK 21**. Do not use Java 17 for code containing `Executors.newVirtualThreadPerTaskExecutor()` or `Thread.isVirtual()`. For applications on JDK 24+, details around `synchronized` pinning differ from JDK 21; always tie performance claims to the exact running JDK version.

## 1. Learning objectives

By the end of this lesson, you should be able to:

1. Explain that a virtual thread is **one lightweight Java thread per task**, not an automatically sized thread pool safe for every resource.
2. Distinguish **live virtual thread count**, **accepted job count**, **requests currently using external resources**, and **actual client pool connections**.
3. Enable virtual threads in Spring Boot 3.5 via `spring.threads.virtual.enabled=true` and explain why `spring.main.keep-alive=true` should be considered.
4. Create an `ExecutorService` using virtual-thread-per-task and manage its lifecycle alongside the Spring context.
5. Use **two `Semaphore`s for distinct purposes**: a cap on accepted jobs and a cap on concurrent external I/O.
6. Reproduce the scenario of **5 jobs accepted, 6th job rejected**, while concurrent external operations never exceed **2**.
7. Prove `InterruptedException` is handled properly: restore the interrupt flag, record state, and `release()` in `finally`.
8. Distinguish graceful shutdown `shutdown()`, cooperative forced shutdown `shutdownNow()`, `awaitTermination(...)` timeouts, and SIGKILL.
9. Identify resources that must be closed separately (JDBC/HTTP clients, responses, streams, broker consumers), without confusing virtual thread termination with closing every connection.
10. Design deadlines, retries, idempotency, and durable job queues when business rules forbid losing jobs across restarts.
11. Gather runtime evidence via job status, permit counts, shutdown logs, and thread dumps/JFR.
12. Distinguish an application **accepting** a job from **job completion**, and readiness from capacity to accept new work.

**Core principle:** Virtual threads help scale blocking tasks without holding one platform thread per task. They **do not** automatically expand database connection pools, API quotas, memory, or CPU. Therefore you must bound **work/resources**, and verify **cleanup on every exit path**.

## 2. Why do virtual threads still need limits?

### 2.1. One virtual thread per task

Java 21 provides:

~~~java
ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor();
~~~

Each submitted task creates a new virtual thread. This executor **does not bound** the number of virtual threads like a fixed thread pool. This is a JDK API usable inside Spring Boot, yet **Spring does not automatically own the lifecycle of an ExecutorService field you create**; the code managing it must stop/close it on context shutdown.

Java docs recommend **not pooling virtual threads** as a scarce resource. Use a `Semaphore` to limit concurrent access to a resource, or admission control to cap total pending work. A `Semaphore` does not turn virtual threads into a platform thread pool: virtual threads waiting for a permit can suspend/unmount from their carrier thread while blocking.

### 2.2. Independent limits

Suppose an application can create tens of thousands of virtual threads while a partner API only permits **2 concurrent calls**:

| Resource | Example cap | Consequence if ignored |
|---|---:|---|
| Virtual threads | Can be very large, depending on heap/runtime | Many objects/thread-locals/job states and overhead |
| Accepted jobs in process | 5 | RAM backlog grows unboundedly if uncapped |
| External API in-flight | 2 | Rate-limited/throttled, upstream overloaded |
| JDBC connections | e.g. 10 per instance | Long connection waits, timeouts, and contention |
| CPU cores | Machine-dependent | Virtual threads do not make CPU work run faster |
| Memory per job | Payload-dependent | OOM despite “lightweight” threads |
| Deadline/job | e.g. 30 seconds to acquire permit | Tasks hang long, hard to shut down gracefully |
| Replica count | e.g. 4 | Per-instance caps multiply across the cluster |

**Two measurements must not be conflated:** `Thread.currentThread().isVirtual() == true` only confirms the job runs on a virtual thread; it does not prove external I/O has bounded concurrency. Conversely, a `Semaphore(2)` limits concurrent calls within **one JVM/process**; with 4 replicas, total capacity can reach 8 calls if all are loaded, rather than a system-wide quota.

### 2.3. User cap, downstream cap, and backlog cap

A layered design can look like:

~~~text
HTTP client
    |
    | POST /lab/jobs
    v
Admission gate (Semaphore: 5)
    |    -> Full: HTTP 429, no new virtual thread created
    v
Executor: newVirtualThreadPerTaskExecutor()
    |
    +-- Virtual Thread A --    +-- Virtual Thread B ---+--> External slots (Semaphore: 2)
    +-- Virtual Thread C --/         |
    +-- Virtual Thread D ---- wait   +--> Mock external operation
    +-- Virtual Thread E ---- wait
                                   |
                             finally: release permit
                 |
                 +--> Job state: DONE / FAILED / INTERRUPTED
    |
    +--> finally: release admission permit
~~~

The limit of **5** is the number of unfinished jobs holding an admission permit; the limit of **2** is the number of jobs simultaneously inside the simulated external operation. The remaining three jobs can wait on the external permit. The lab uses a non-waiting semaphore at the HTTP boundary (`tryAcquire()`) and a timed-wait semaphore in the worker (`tryAcquire(timeout)`).

These are two distinct policies: **do not make HTTP requests wait indefinitely just to submit a job**, and **do not allow more than two jobs to use the external service concurrently**.

## 3. How does Spring Boot 3.5 support virtual threads?

### 3.1. Enable via configuration

In application properties:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

`spring.threads.virtual.enabled=true` requires Java **21+**. When Boot auto-configures `AsyncTaskExecutor` without a custom `Executor` overriding it, Boot can use `SimpleAsyncTaskExecutor` running virtual threads. When Boot auto-configures a scheduler, virtual threads can be used via `SimpleAsyncTaskScheduler`.

**Do not misunderstand:** pool properties such as `spring.task.execution.pool.max-size`, `queue-capacity`, or `spring.task.scheduling.pool.size` **do not cap virtual threads in the corresponding virtual-thread mode**. Spring Boot documentation states pool properties no longer take effect on executors/schedulers using virtual threads. External request caps must live at meaningful admission/semaphore/connection-pool layers.

`spring.main.keep-alive=true` is useful because **virtual threads are daemon threads**. If an application only has daemon threads left (for instance an `@Scheduled`-heavy workload), the JVM can exit even while work remains; keep-alive prevents unexpected process termination. This is neither a shutdown strategy nor durable job persistence: on valid context stop or SIGKILL, resources and data still need handling.

### 3.2. Code-created executors vs Boot auto-configured executors

Two common patterns:

| Approach | Example | Who owns the lifecycle? | Limits still needed |
|---|---|---|---|
| Boot-managed task executor | `@Async` using Boot auto-configured executor | Spring/Boot depending on executor type | Admission/timeouts/connection quotas |
| Custom Java executor in an `@Service` | `Executors.newVirtualThreadPerTaskExecutor()` | The bean owning the field must close it | Admission and external permits |
| Custom Spring `SimpleAsyncTaskExecutor` | `setVirtualThreads(true)` | Depends on registration/closing; not a reuse pool | `setConcurrencyLimit` or another gate per semantics |
| JDBC connection pool | HikariCP or equivalent | DataSource/pool bean | `maximumPoolSize`, connection timeouts |
| Broker listener container | Corresponding Spring integration | Listener container/lifecycle | Consumer concurrency, in-flight, acks, retries |

`SimpleAsyncTaskExecutor` **does not reuse threads**. Some versions of Spring Framework 6.2 support `setConcurrencyLimit(...)` and an option to reject at the cap; limiting can **block the submitter** by default. Check the exact Javadoc for your version; do not treat `setConcurrencyLimit` as equivalent to a bounded job queue with durable storage.

In this lab, we **intentionally own an `ExecutorService` field** to observe shutdown clearly. It is independent of any `@Async` executor Spring Boot may create.

## 4. Interruption, cancellation, and closing resources: three different things

### 4.1. An interrupted thread does not guarantee the operation stopped

`shutdownNow()` makes a **best-effort attempt** to stop running tasks, typically via `Thread.interrupt()`. A task blocked in `Thread.sleep(...)`, `CountDownLatch.await(...)`, or `Semaphore.tryAcquire(timeout)` can respond with `InterruptedException`. However, if an external client ignores interruption, native I/O or a stuck API call might not stop immediately.

Proper handling:

~~~java
try {
    performInterruptibleWork();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    recordCancelledOrInterrupted();
} finally {
    releaseOwnedResources();
}
~~~

This is an **illustrative snippet**, not a standalone Java file. Always distinguish:

- **interrupt request**: cooperative signal asking to stop;
- **job actually stopped**: task exited the critical section and released permits;
- **executor terminated**: no tasks remain running;
- **external operation rolled back**: requires explicit DB/API contracts, not inferred from an interrupt.

### 4.2. Never release a permit by mistake

Safe acquire/release pattern:

~~~java
boolean acquired = false;
try {
    acquired = semaphore.tryAcquire(20, TimeUnit.SECONDS);
    if (!acquired) {
        throw new TimeoutException("external permit timeout");
    }
    performExternalCallWithTimeout();
} finally {
    if (acquired) {
        semaphore.release();
    }
}
~~~

If `tryAcquire(...)` fails yet code still calls `release()`, permits inflate past the original cap. If `release` is skipped on exception, permits leak and later jobs may wait forever. In the complete lab we express exceptions and interrupt handling more fully; the snippet above illustrates ownership alone.

### 4.3. Closing connections differs from closing virtual threads

- JDBC: obtain a `Connection` from the pool and use `try-with-resources` to **return the connection to the pool**; the physical connection may be kept for reuse.
- HTTP client: configure connect/request/read timeouts appropriately; close `InputStream`/`Response` if the API requires; pooled HTTP clients close at bean lifecycle.
- Files/Sockets: close `Closeable` in `try-with-resources`, avoiding leaking file descriptors across uncontrolled work flows.
- Message brokers: pause receiving new messages, complete ack/nack per policy, close sessions/consumers.
- Semaphore: release permits in `finally`, never relying on GC to recover leaked permits.
- Virtual thread: finishing `run()` does not roll back an already-dispatched external side effect.

Do not “fix” resource leaks by spawning more virtual threads. More tasks only make resource-pool/FD failures hit sooner and harder to diagnose.

## 5. Complete practice project: external limits and cooperative shutdown

### 5.1. Initialize the Maven project

Create a project via Spring Initializr:

- **Java 21** (24+ works if supported by the environment), **Spring Boot 3.5.x**.
- Build: **Maven**, Packaging: **Jar**.
- Group `com.example`; Artifact `virtual-shutdown-lab`.
- Package `com.example.virtualshutdown`.
- Dependency: **Spring Web**.
- Keep the generated `pom.xml` and Maven Wrapper without mixing dependency versions manually.

Structure:

~~~text
virtual-shutdown-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/virtualshutdown/
    VirtualShutdownLabApplication.java
    VirtualJobService.java
    VirtualJobController.java
  src/main/resources/application.properties
~~~

The three Java files below **are complete code within the Maven project above**. They require Spring Web and Jakarta annotations included in runtime dependencies; do not compile/run with `javac` against a JDK-only classpath.

### 5.2. Main class

File `src/main/java/com/example/virtualshutdown/VirtualShutdownLabApplication.java`:

~~~java
package com.example.virtualshutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class VirtualShutdownLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(VirtualShutdownLabApplication.class, args);
    }
}
~~~

Main does not manually open `new Thread()` or hold an unclosed local ExecutorService. Worker lifecycle belongs to the Spring-managed `VirtualJobService` in the next step.

### 5.3. VirtualJobService: two limits + error handling + shutdown

File `src/main/java/com/example/virtualshutdown/VirtualJobService.java`:

~~~java
package com.example.virtualshutdown;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Service;

@Service
public class VirtualJobService {

    // Each task gets one virtual thread; executor has NO size limit.
    private final ExecutorService executor =
            Executors.newVirtualThreadPerTaskExecutor();

    // At most 5 jobs accepted/not yet finished in the JVM.
    private final Semaphore admitted = new Semaphore(5, true);

    // Only 2 jobs may enter the simulated external I/O section.
    private final Semaphore externalSlots = new Semaphore(2, true);

    private final CountDownLatch demoRelease = new CountDownLatch(1);
    private final ConcurrentMap<String, JobView> jobs =
            new ConcurrentHashMap<>();

    private final AtomicBoolean stopping = new AtomicBoolean();
    private final AtomicInteger accepted = new AtomicInteger();
    private final AtomicInteger rejected = new AtomicInteger();
    private final AtomicInteger done = new AtomicInteger();
    private final AtomicInteger failed = new AtomicInteger();
    private final AtomicInteger interrupted = new AtomicInteger();
    private final AtomicInteger externalActive = new AtomicInteger();
    private final AtomicInteger externalPeak = new AtomicInteger();

    public Submission submit(String kind) {
        if (stopping.get()) {
            return new Submission(null, "SHUTTING_DOWN");
        }

        // Fast-fail at the HTTP boundary: DO NOT spawn unbounded threads.
        if (!admitted.tryAcquire()) {
            rejected.incrementAndGet();
            return new Submission(null, "REJECTED");
        }

        // Re-check to reduce race with shutdown.
        if (stopping.get()) {
            admitted.release();
            return new Submission(null, "SHUTTING_DOWN");
        }

        String id = UUID.randomUUID().toString();
        jobs.put(id, new JobView(id, kind, "ACCEPTED",
                null, "accepted in memory"));

        try {
            executor.execute(() -> runJob(id, kind));
            accepted.incrementAndGet();
            System.out.println("LAB_SUBMITTED id=" + id);
            return new Submission(id, "ACCEPTED");
        } catch (RejectedExecutionException ex) {
            admitted.release();
            jobs.put(id, new JobView(id, kind, "REJECTED",
                    null, "executor is shutting down"));
            return new Submission(id, "SHUTTING_DOWN");
        }
    }

    private void runJob(String id, String kind) {
        boolean slotHeld = false;
        String thread = Thread.currentThread().toString();

        try {
            jobs.put(id, new JobView(id, kind, "WAITING_SLOT",
                    Thread.currentThread().isVirtual(),
                    "waiting for external permit"));

            // Wait for permit with deadline; blocking a virtual thread is valid.
            if (!externalSlots.tryAcquire(30, TimeUnit.SECONDS)) {
                throw new TimeoutException(
                        "LAB_EXTERNAL_PERMIT_TIMEOUT");
            }

            slotHeld = true;
            int activeNow = externalActive.incrementAndGet();
            externalPeak.accumulateAndGet(activeNow, Math::max);

            jobs.put(id, new JobView(id, kind, "RUNNING",
                    Thread.currentThread().isVirtual(), thread));
            System.out.println("LAB_EXTERNAL_BEGIN id=" + id
                    + " active=" + activeNow
                    + " virtual=" + Thread.currentThread().isVirtual());

            switch (kind) {
                case "block" -> {
                    if (!demoRelease.await(90, TimeUnit.SECONDS)) {
                        throw new TimeoutException(
                                "LAB_EXTERNAL_TIMEOUT");
                    }
                }
                case "fail" -> throw new IllegalStateException(
                        "LAB_INTENTIONAL_FAILURE");
                default -> Thread.sleep(250);
            }

            done.incrementAndGet();
            jobs.put(id, new JobView(id, kind, "DONE",
                    true, "completed"));
            System.out.println("LAB_DONE id=" + id);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            interrupted.incrementAndGet();
            jobs.put(id, new JobView(id, kind, "INTERRUPTED",
                    Thread.currentThread().isVirtual(),
                    "interrupted during shutdown or cancellation"));
            System.out.println("LAB_INTERRUPTED id=" + id);
        } catch (Exception ex) {
            failed.incrementAndGet();
            jobs.put(id, new JobView(id, kind, "FAILED",
                    Thread.currentThread().isVirtual(),
                    ex.getMessage()));
            System.out.println("LAB_FAILED id=" + id
                    + " cause=" + ex.getMessage());
        } finally {
            if (slotHeld) {
                int now = externalActive.decrementAndGet();
                externalSlots.release();
                System.out.println("LAB_EXTERNAL_RELEASE id=" + id
                        + " active=" + now);
            }
            admitted.release();
            System.out.println("LAB_ADMISSION_RELEASE id=" + id);
        }
    }

    public void releaseBlockedTasks() {
        demoRelease.countDown();
    }

    public JobView job(String id) {
        return jobs.get(id);
    }

    public Stats stats() {
        return new Stats(
                accepted.get(),
                rejected.get(),
                done.get(),
                failed.get(),
                interrupted.get(),
                5 - admitted.availablePermits(),
                admitted.availablePermits(),
                externalActive.get(),
                externalPeak.get(),
                externalSlots.availablePermits(),
                stopping.get());
    }

    @PreDestroy
    public void shutdown() {
        stopping.set(true);
        System.out.println("LAB_SHUTDOWN_BEGIN inFlight="
                + (5 - admitted.availablePermits()));

        // Step 1: stop accepting new tasks, wait for running tasks.
        executor.shutdown();

        try {
            if (!executor.awaitTermination(3, TimeUnit.SECONDS)) {
                // Step 2: if not yet terminated, request interruption.
                System.out.println("LAB_SHUTDOWN_INTERRUPT");
                executor.shutdownNow();

                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    System.out.println(
                            "LAB_SHUTDOWN_TIMEOUT cleanup incomplete");
                }
            }
        } catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
            System.out.println("LAB_SHUTDOWN_WAIT_INTERRUPTED");
        }

        System.out.println("LAB_SHUTDOWN_END terminated="
                + executor.isTerminated()
                + " externalActive=" + externalActive.get()
                + " admittedInFlight="
                + (5 - admitted.availablePermits()));
    }

    public record Submission(String id, String state) {
    }

    public record JobView(
            String id, String kind, String state,
            Boolean virtualThread, String detail) {
    }

    public record Stats(
            int accepted, int rejected, int done, int failed,
            int interrupted, int admittedInFlight,
            int admissionAvailable, int externalActive,
            int externalPeak, int externalAvailable,
            boolean stopping) {
    }
}
~~~

**Correctness analysis of the code:**

1. `newVirtualThreadPerTaskExecutor()` spawns **one virtual thread per task**. The cap of **5** is enforced by `admitted.tryAcquire()` prior to calling `execute`, not by the executor limiting threads.
2. `Semaphore(5, true)` is the **admission guard**: each unfinished job holds one permit; the sixth job is rejected while all five permits are held. It prevents spawning excessive virtual threads just to wait on external resources.
3. `Semaphore(2, true)` is the **downstream concurrency guard**: at most two jobs enter the critical section concurrently. Others wait via `tryAcquire(30, TimeUnit.SECONDS)` inside their virtual threads.
4. `Boolean virtualThread` in `JobView` starts as `null` before the job runs and becomes `true` when code measures `Thread.currentThread().isVirtual()`. This is a direct measurement, not inferred from properties or thread names.
5. `RUNNING` is recorded **only after acquiring the external permit**; `WAITING_SLOT` indicates the task has a virtual thread yet has not accessed the resource. `DONE`, `FAILED`, and `INTERRUPTED` are terminal states in the example.
6. `slotHeld` ensures external permits are released only when acquired successfully. `finally` releases **both external and admission permits** when the job ends, whether by success, error, interrupt, or timeout.
7. `Thread.currentThread().interrupt()` preserves the interrupt status when catching `InterruptedException`. Code does not attempt to continue external calls after receiving an interrupt.
8. `@PreDestroy` is invoked by Spring when destroying the bean during normal context close. It stops accepting work, calls `shutdown()`, waits up to 3 seconds, then calls `shutdownNow()` and waits up to 5 more seconds. This is a **lab deadline**, not a guarantee every external operation halts within 8 seconds.
9. `executor.isTerminated()` is logged after waiting. **Only when isTerminated=true, externalActive=0, admittedInFlight=0** have managed tasks left the critical section in the demo. If any differ, incomplete cleanup must be reported.
10. `ConcurrentHashMap jobs` has no TTL/retention to keep the lesson simple. In production, bound memory and use a durable job store if jobs must not be lost when the JVM dies.
11. `accepted` increments after `execute(...)`. A very fast task can finish before the caller increments the counter, so snapshots across multiple `AtomicInteger`s are **not a single transaction**; compare final counts once the system is quiescent.
12. `demoRelease` is a one-shot latch. Once opened, it does not reset automatically; restart the application to run the saturation test again in a fresh state.

**Intentional demo limitation:** there is no real network I/O and no transactions. Thus we verify **concurrency/cleanup semantics**, yet cannot conclude from this alone that a real JDBC connection, HTTP response stream, or broker consumer was closed. Those require dedicated checks in later sections.

### 5.4. REST controller to submit jobs and read results

File `src/main/java/com/example/virtualshutdown/VirtualJobController.java`:

~~~java
package com.example.virtualshutdown;

import java.util.Map;
import java.util.Set;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class VirtualJobController {

    private static final Set<String> KINDS =
            Set.of("quick", "block", "fail");

    private final VirtualJobService jobs;

    public VirtualJobController(VirtualJobService jobs) {
        this.jobs = jobs;
    }

    @PostMapping("/lab/jobs")
    public ResponseEntity<?> submit(
            @RequestParam(defaultValue = "quick") String kind) {

        if (!KINDS.contains(kind)) {
            return ResponseEntity.badRequest().body(
                    Map.of("error", "kind must be quick, block or fail"));
        }

        VirtualJobService.Submission result = jobs.submit(kind);

        return switch (result.state()) {
            case "ACCEPTED" ->
                    ResponseEntity.status(HttpStatus.ACCEPTED)
                            .body(result);
            case "REJECTED" ->
                    ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                            .body(result);
            default ->
                    ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                            .body(result);
        };
    }

    @GetMapping("/lab/jobs/{id}")
    public ResponseEntity<?> status(@PathVariable String id) {
        VirtualJobService.JobView job = jobs.job(id);

        if (job == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(Map.of("error", "job id not found"));
        }
        return ResponseEntity.ok(job);
    }

    @GetMapping("/lab/stats")
    public VirtualJobService.Stats stats() {
        return jobs.stats();
    }

    @PostMapping("/lab/release")
    public Map<String, Boolean> release() {
        jobs.releaseBlockedTasks();
        return Map.of("released", true);
    }
}
~~~

**HTTP contract:**

- `POST /lab/jobs?kind=quick`: 202 if admitted into RAM; job transitions to `DONE` shortly after.
- `POST /lab/jobs?kind=block`: 202 if admitted; holds external permit while waiting on latch; used to verify limits.
- `POST /lab/jobs?kind=fail`: may return **202 on submit** yet later become `FAILED` when the virtual thread runs; do not mistake 202 for business success.
- If admission is full: **429** with `state="REJECTED"`.
- If shutting down: **503** with `state="SHUTTING_DOWN"` if the HTTP connector still accepts the request.
- `GET /lab/jobs/{id}` reads status; returns `404` when ID does not exist.
- `GET /lab/stats` exposes counters, active external, peak, and permits.
- `POST /lab/release` releases the lab latch; not a business API.

**Safety:** The controller is localhost-only with no authentication. **Never expose endpoints that create block/fail jobs or release latches in production**. Production needs authentication, per-tenant quotas, request validation, rate limits, and body size limits. The lab stores state in RAM, with no post-restart recovery guarantee.

### 5.5. Spring Boot configuration

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=virtual-shutdown-lab
server.address=127.0.0.1
server.port=8080

# Enable Spring Boot virtual-thread integrations on Java 21+
spring.threads.virtual.enabled=true
spring.main.keep-alive=true

# Make context stop behavior explicit for the lab
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

In the lab, **the custom executor in `VirtualJobService` already creates virtual threads via JDK APIs even when `spring.threads.virtual.enabled` is not enabled**. This property also lets us observe how Spring Boot configures virtual threads at supported integration points; do not mistake it for a cap on the service's own executor.

`server.address=127.0.0.1` is suitable only for local testing. In containers/Kubernetes, bind an interface reachable by kubelet/ingress; do not copy a loopback address into a Pod and forget to check networking.

## 6. Run the lab and confirm real virtual threads

### 6.1. Maven Wrapper and JDK

On Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd spring-boot:run
~~~

`java -version` must show **JDK 21+**. If the terminal has `JAVA_HOME` or PATH pointing to Java 17, the application will not run with these APIs. Do not compile targeting Java 17 and expect `newVirtualThreadPerTaskExecutor()` to exist on a lower runtime.

Keep the Maven terminal running the app. In another terminal:

~~~bash
curl -i -X POST "http://127.0.0.1:8080/lab/jobs?kind=quick"
curl -i "http://127.0.0.1:8080/lab/stats"
~~~

Submission returns HTTP **202** and JSON containing a UUID with `state="ACCEPTED"`. Program-generated IDs are random, with no fixed stdout value to hardcode.

After copying the ID from the response, on Linux/macOS shells:

~~~bash
read -r JOB_ID
# Paste the received ID, press Enter
curl -i "http://127.0.0.1:8080/lab/jobs/$JOB_ID"
~~~

On PowerShell:

~~~powershell
$jobId = Read-Host "Paste job ID from 202 response"
curl.exe -i "http://127.0.0.1:8080/lab/jobs/$jobId"
~~~

Once the worker finishes, the job has `state="DONE"` and `virtualThread=true`, or while still executing has `WAITING_SLOT`/`RUNNING` also with `virtualThread=true`. Logs look like:

~~~text
LAB_SUBMITTED id=<dynamic-id>
LAB_EXTERNAL_BEGIN id=<dynamic-id> active=1 virtual=true
LAB_DONE id=<dynamic-id>
LAB_EXTERNAL_RELEASE id=<dynamic-id> active=0
LAB_ADMISSION_RELEASE id=<dynamic-id>
~~~

The IDs are **variables in the log pattern**, not literal strings always printed verbatim. `LAB_EXTERNAL_BEGIN` may appear before `LAB_SUBMITTED` because the request thread and virtual thread run concurrently. `virtual=true` is a more reliable milestone to verify than strict log ordering.

**Never record “job success” solely from HTTP 202.** `202 Accepted` only indicates admission and `execute()` accepted the task into the JVM; the job can fail or be interrupted afterward.

## 7. Experiment 1 — Proving external limits, not virtual thread limits

Start **a fresh JVM** so the latch is not yet released. Within under **30 seconds** (permit wait deadline) and before **90 seconds** (external gate hold deadline), send six `block` requests rapidly.

On Linux/macOS:

~~~bash
for i in 1 2 3 4 5 6; do
  curl -s -i -X POST "http://127.0.0.1:8080/lab/jobs?kind=block"
done
curl -s "http://127.0.0.1:8080/lab/stats"
~~~

On Windows PowerShell:

~~~powershell
1..6 | ForEach-Object {
    curl.exe -s -i -X POST "http://127.0.0.1:8080/lab/jobs?kind=block"
}
curl.exe -s "http://127.0.0.1:8080/lab/stats"
~~~

**Expected state before jobs time out or get released:**

- **First 5 requests** → HTTP **202**, each with its own UUID and `state=ACCEPTED`.
- **Sixth request** → HTTP **429**, `state=REJECTED`; the service does not spawn a virtual thread for this task.
- `admittedInFlight=5`, `admissionAvailable=0`.
- `externalActive=2`, `externalAvailable=0`.
- `externalPeak=2`; never exceeds 2 in a standard lab run.
- There are **2 jobs** in `RUNNING` holding external permits.
- There are **3 jobs** in `WAITING_SLOT` with virtual threads waiting for a permit.
- `accepted=5` and `rejected=1` (if these are the only six submissions).
- No `DONE` jobs yet for the block batch.

Comparison table:

| Metric | Max/expected value | Bounded by |
|---|---:|---|
| Accepted jobs not yet finished | 5 | `Semaphore admitted(5)` |
| Jobs using mock external resource | 2 | `Semaphore externalSlots(2)` |
| Virtual threads waiting on external permit | 3 in this batch | Remaining admission, not a virtual thread pool |
| Is the 6th job accepted? | No | Fast-fail at admission |
| HTTP response when saturated | 429 | Controller mapping for `REJECTED` |

This proves **external concurrency** limits still hold even when many virtual threads can be created. The lab's semaphore must not be mistaken for a cluster-wide quota; running N replicas raises the combined ceiling up to `2 × N` unless downstream coordination/rate limiting exists.

### 7.1. Release and confirm zero permit leaks

While all block requests are holding/waiting for permits:

~~~bash
curl -i -X POST "http://127.0.0.1:8080/lab/release"
curl -i "http://127.0.0.1:8080/lab/stats"
~~~

Poll stats a few times until all five accepted jobs finish. With no timeouts/interrupts and no other submissions:

~~~json
{
  "accepted": 5,
  "rejected": 1,
  "done": 5,
  "failed": 0,
  "interrupted": 0,
  "admittedInFlight": 0,
  "admissionAvailable": 5,
  "externalActive": 0,
  "externalPeak": 2,
  "externalAvailable": 2,
  "stopping": false
}
~~~

This is the **expected JSON once the system is quiescent**, not necessarily the result of the GET immediately after POST release because workers run asynchronously. JSON property order may vary. Permit values returning to **5** and **2** prove no semaphore leak in this model; they **do not yet prove** a real JDBC connection or HTTP response stream was closed.

Do not retry saturation in **the same JVM after release** expecting block jobs to wait, because `CountDownLatch` does not reset. Restart the app to test again with a fresh latch.

## 8. Experiment 2 — Task failure and cleanup in finally

When no block jobs remain or after restarting, call:

~~~bash
curl -i -X POST "http://127.0.0.1:8080/lab/jobs?kind=fail"
curl -i "http://127.0.0.1:8080/lab/stats"
~~~

HTTP submit may return **202** before the virtual thread throws an error. In logs:

~~~text
LAB_EXTERNAL_BEGIN id=<dynamic-id> active=1 virtual=true
LAB_FAILED id=<dynamic-id> cause=LAB_INTENTIONAL_FAILURE
LAB_EXTERNAL_RELEASE id=<dynamic-id> active=0
LAB_ADMISSION_RELEASE id=<dynamic-id>
~~~

When the job becomes `FAILED`, `failed` increments by one, yet `admittedInFlight=0` and `externalAvailable=2` return after `finally`. This proves that **business exceptions** do not leak permits.

If `externalSlots.tryAcquire(...)` **expires after 30 seconds** before acquiring a slot, the task becomes `FAILED` with `LAB_EXTERNAL_PERMIT_TIMEOUT`, and only the **admission** permit is released. Because `slotHeld=false`, code does **not** release an external permit it never held. Distinguish this timeout from an API network timeout occurring **after acquiring the permit**.

If the worker is interrupted while waiting for the external permit, the `InterruptedException` branch runs and the admission permit is released; external permits are not erroneously inflated.

## 9. Experiment 3 — Shutdown while virtual threads are waiting

### 9.1. Testing workflow without corrupting data

1. Restart the application so the latch is unreleased.
2. Submit **5 requests** of `kind=block`.
3. Confirm `admittedInFlight=5`, `externalActive=2`, `externalPeak=2`.
4. **Do not call `/lab/release`**.
5. Stop the process via Ctrl+C in the Maven terminal or a valid SIGTERM when running the JAR (do not use SIGKILL).
6. Observe logs from `VirtualJobService.shutdown()`, worker interrupts, and permit releases.

**Representative** log example:

~~~text
LAB_SHUTDOWN_BEGIN inFlight=5
LAB_SHUTDOWN_INTERRUPT
LAB_INTERRUPTED id=<dynamic-id>
LAB_EXTERNAL_RELEASE id=<dynamic-id> active=...
LAB_ADMISSION_RELEASE id=<dynamic-id>
LAB_SHUTDOWN_END terminated=true externalActive=0 admittedInFlight=0
~~~

Because there are five tasks, interrupt/release markers appear multiple times and ordering among virtual threads **is not fixed**. Web server graceful shutdown markers may appear before `LAB_SHUTDOWN_BEGIN`. The lab's default path is: `shutdown()` stops accepting new tasks; because the 5 blocked jobs do not finish within 3 seconds, code calls `shutdownNow()` to request interruption; because `CountDownLatch.await` and `Semaphore.tryAcquire` respond to interrupts, workers exit and `finally` releases permits.

**PASS criteria for this test:**

- `LAB_SHUTDOWN_BEGIN` followed later by `LAB_SHUTDOWN_END` appear.
- `terminated=true` given cooperative workers and no stuck external I/O.
- `externalActive=0`; `admittedInFlight=0` at the end in a standard lab run.
- `LAB_INTERRUPTED` markers appear with corresponding IDs.
- Each job that held an external slot has `LAB_EXTERNAL_RELEASE`; each accepted job has `LAB_ADMISSION_RELEASE` if the task actually started.
- No `LAB_SHUTDOWN_TIMEOUT cleanup incomplete` message appears in the normal cooperative path.

**Do not assert absolutes:** Individual marker ordering or exact 3+5 second timings are not contracts; scheduler, OS, framework, and cleanup work can vary them. If a task is in the list returned by `shutdownNow()` having never started, it may never run `finally`; the JDK API does not promise pending tasks will be started solely for cleanup. Production therefore needs durable job state and handling for dropped/unstarted tasks.

### 9.2. HTTP server shutdown and background jobs are two phases

Spring Boot 3.5 supports graceful shutdown for embedded web servers. `server.shutdown=graceful` directs the web server to stop accepting new requests per policy and let in-flight requests finish within the allowed time. `spring.lifecycle.timeout-per-shutdown-phase` is the per-lifecycle-phase budget. The demo service's `@PreDestroy` is a bean-destruction hook, not a full replacement for `SmartLifecycle` and phase orchestration when broker consumers exist.

When Ctrl+C/SIGTERM arrives, **the HTTP server may close or become unreachable before the job service finishes cleanup**. Do not rely on GET `/lab/stats` during shutdown; use logs, pre-shutdown metrics, and external state. In real production systems, you need a policy to stop accepting jobs early (readiness/admission gate), then drain/cancel and persist durable state.

### 9.3. Differences between shutdown, shutdownNow, close, and SIGKILL

| Mechanism | Effect | Guarantees tasks exit immediately? |
|---|---|---|
| `executor.shutdown()` | Stops accepting new tasks; lets submitted tasks continue | No |
| `executor.awaitTermination(timeout)` | Waits until executor stops or timeout expires | Does not cancel automatically |
| `executor.shutdownNow()` | Requests stop and returns unstarted tasks; usually interrupts running tasks | No, best effort |
| `ExecutorService.close()` on Java 21 | Requests orderly shutdown and **waits until all tasks finish**; has API-specific behavior if interrupted | Can wait long if tasks do not stop |
| `@PreDestroy` | Spring bean destruction hook during valid context close | Not guaranteed to run if process is killed |
| JVM SIGTERM/Ctrl+C | Can trigger shutdown hooks and context close | Depends on deadlines, application, and OS |
| SIGKILL / `kill -9` | Forcefully terminates process | No reliable Java callbacks/cleanup |

Therefore, if tasks can block indefinitely, calling `executor.close()` inside `@PreDestroy` without a timeout can hang shutdown. The lab uses two phases with `awaitTermination` and `shutdownNow`, yet cannot **force** uncooperative native I/O to stop within a bounded time.

## 10. External resource cleanup: what to inspect?

### 10.1. JDBC/DataSource

In Spring Boot, JDBC connections typically come from a connection pool like HikariCP. Virtual threads do not give the pool more connections. When 1,000 virtual threads simultaneously request connections from a pool of 10, most must wait for a connection or time out; latency increases and can slow down the entire system.

Proper code pattern for a manual JDBC operation:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "SELECT 1")) {
    try (ResultSet rows = statement.executeQuery()) {
        if (rows.next()) {
            return rows.getInt(1);
        }
    }
}
~~~

This is a **method-body snippet**, requiring `DataSource`/imports and a method with a matching return type; **do not** drop it directly into a Web-only project lacking JDBC dependencies. With Spring `JdbcTemplate` or `@Transactional`, the framework can manage acquisition/release per contract; do not manually close a connection belonging to a framework-managed transaction outside your scope.

Check: Hikari active/idle/pending, connection acquisition timeout, transaction duration, selective leak detection, and connections returning to the pool on exception/cancellation. If the JDBC pool already is your desired concurrency cap, adding a semaphore with **the exact same cap** can be redundant; Oracle also notes connection pools act as limiters themselves. Add extra permits when a **different business cap** is needed (e.g., partner only accepts 2 QPS/concurrent calls) or to reject early before exhausting connections.

### 10.2. HTTP client calling upstream

A production HTTP call needs:

- Appropriate connection and request/response deadlines.
- Concurrent call / total in-flight caps and rate limits matching upstream policy.
- Closing response body streams when required by the API.
- Closing/stopping reusable HTTP clients at the proper lifecycle, without creating a new client per job if it manages a connection pool.
- Distinguishing timeouts, cancellation, 429/503 responses, DNS/network failures, and permanent errors.
- Using idempotency keys if the operation has external side effects and retries.

JDK 21 snippet using `HttpClient` (client can be reused):

~~~java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.invalid/resource"))
        .timeout(Duration.ofSeconds(3))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
~~~

This is purely an **illustrative code snippet**; `example.invalid` is a documentation-only host, **never to be called as a real service**, and requires defining `HttpClient client`, imports, error handling, a valid URI, and timeouts. Calling `client.send` from a virtual thread is suitable for blocking I/O; `send` can throw `InterruptedException`, requiring cancellation handling. Do not assume a 200 response or an interrupt proves all downstream resources rolled back.

### 10.3. Broker consumers

With Kafka, RabbitMQ, or JMS, “stopping a virtual thread” does not automatically ack/nack messages. Manage:

1. Pausing receipt of new messages.
2. Waiting for/recording in-flight processing within deadline.
3. Acking or performing valid protocol redelivery.
4. Closing consumers/sessions/connections per library contract.
5. Recording durable state/idempotency when tasks have external side effects.

If the framework's listener container already has `SmartLifecycle` and shutdown phases, prefer configuring its lifecycle rather than writing two places both owning start/stop.

### 10.4. File descriptors, streams, and ThreadLocal

Every virtual thread is a Java Thread object so code can still use `ThreadLocal`. However, virtual-thread-per-task **is not pooled/reused to amortize caches** like a few platform threads. Holding large payloads, credentials, or per-request objects in ThreadLocals across tens of thousands of jobs can bloat memory. When using MDC/SecurityContext/transaction context, establish propagation and cleanup explicitly; switching threads does not guarantee old context carries over automatically.

A thread terminating does not mean every file descriptor or pooled connection was freed if references remain held. For `AutoCloseable` instances truly owned by a task, use `try-with-resources`/`finally`. For shared clients, put close hooks on the owner bean rather than letting one job close a client shared by others.

## 11. CPU, memory, and virtual thread pinning

### 11.1. I/O-bound is not CPU-bound

Virtual threads help when many tasks frequently wait on I/O. They **do not make CPU computations run faster** or increase CPU cores. If work is CPU-bound, adding more virtual threads can just create contention; use work limiters based on CPU cores/measurement or an appropriate architecture.

### 11.2. Pinned virtual threads: distinguish JDK versions

With **JDK 21**, a virtual thread can **be pinned to its carrier** when blocking inside `synchronized` or native/foreign calls. A pinned virtual thread holds its platform carrier thread and lowers scalability if pinning is prolonged/frequent. JDK **24+** significantly changes synchronized pinning (per JEP 491); do not apply JDK 21 descriptions verbatim to all newer Java releases.

Do not fix every `synchronized` unconditionally. Find critical sections **holding monitors during long blocking I/O**; consider moving blocking I/O outside synchronized or using `ReentrantLock` where needed. For native/third-party drivers, verify stacks and library compatibility.

Diagnostic tool on JDK 21:

~~~bash
jcmd PID Thread.dump_to_file -format=json virtual-threads.json
~~~

Replace `PID` with the running JVM's PID. You can enable Java Flight Recorder and look for `jdk.VirtualThreadPinned` events when pinning actually occurs. Do not infer “no event seen” always means zero pinning: events, thresholds, and JFR settings affect observation. Java 24+ introduces changes, so pinning and event guidance must match the active JDK.

### 11.3. Memory pressure becomes the remaining limit

A virtual thread is lighter than a platform thread, yet not **free**. Each task carries stack/data structures, futures, payloads, HTTP context, job results, TLS/trace context, and may hold references to external resources. If admission is unbounded, 100,000 virtual threads waiting on a semaphore form a huge backlog, risking heap exhaustion or unbounded response latency.

That is why the lab uses **Semaphore(5)** before creating threads, rather than relying only on `Semaphore(2)` downstream. In production, size admission capacity based on SLOs, estimated memory per task, queue delay, retry policies, and recoverability.

## 12. Graceful shutdown, readiness, and container deadlines

Spring Boot 3.5 provides graceful shutdown with supported embedded web servers; the web server attempts to stop accepting new requests and finish in-flight requests within budget. However, there are **two separate axes**:

- **HTTP request lifecycle:** ingress/readiness, client connections, request handlers, web connector.
- **Background jobs lifecycle:** admission, pending jobs, resource semaphores, external I/O, executor, job persistence.

If you only enable `server.shutdown=graceful` while leaving a service-created `ExecutorService` unclosed, there is no guarantee background jobs are drained/cancelled. If you only call `executor.shutdownNow()` while the web server still accepts new jobs, you can cause uncontrolled rejections/losses.

**Recommended design sequence:**

1. Publish `REFUSING_TRAFFIC` readiness or disable admission for **new jobs** before/alongside the drain phase per policy.
2. Stop intake from HTTP/brokers/schedulers; avoid spawning new tasks.
3. Let in-flight jobs finish within deadline; record durable state/outcomes.
4. Cancel/interrupt remaining tasks if needed; require them to release permits/streams/connections in `finally`.
5. Close reusable clients and consumers/containers after user jobs stop using them.
6. Verify executor terminated, active external=0, permits returned, and error/cancellation metrics.
7. Ensure total phase deadlines fit within `terminationGracePeriodSeconds`, autoscaling/restarts, and platform-level timeouts.

**Caution:** readiness is only an infrastructure routing signal; publishing `REFUSING_TRAFFIC` **does not automatically block all direct HTTP requests** if the app has no gate or the web server has not started shutdown. An admission check right at the API is needed to stop accepting new jobs while stopping.

### 12.1. Graceful shutdown cannot be proven with SIGKILL

SIGKILL or OS crashes do not guarantee `@PreDestroy`, `SmartLifecycle.stop(...)`, or task `finally` blocks run. Therefore, if the requirement is “when HTTP returns 202, the job is guaranteed not to be lost”, persist the job durably before responding, using queues/brokers/DBs with ack/recovery and idempotency. The lab's 202 only means “accepted into JVM RAM”, **not** a durability promise.

### 12.2. Do not confuse different timeouts

| Timeout | Scope | When expired |
|---|---|---|
| Non-blocking admission `tryAcquire()` | HTTP submit | Reject immediately |
| External permit `tryAcquire(30s)` | Waiting for resource slot | Job `FAILED` if not acquired |
| Demo external latch `await(90s)` | Simulated I/O | Job `FAILED` if unreleased |
| HTTP client request timeout | Request to upstream | Library-dependent, usually throws exception |
| `awaitTermination(3s+5s)` | Waiting for executor stop | Escalate/log timeout |
| Spring shutdown phase timeout | Context's `LifecycleProcessor` | Proceeds/times out per framework |
| Kubernetes termination grace period | Entire process/Pod | Can forcefully terminate |
| Business operation deadline | Entire task | Typically needs cancel and idempotency |

A job making three 30-second HTTP calls does not automatically guarantee a 30-second total deadline. Compute an end-to-end budget with cancellation propagation and per-step timeouts. If retries are unbounded, deadlines can still be exceeded even when each individual call has a timeout.

## 13. Observability and evidence sufficient to declare PASS

### 13.1. Numbers to monitor

| Metric | Meaning | Warning sign |
|---|---|---|
| `admittedInFlight` | Accepted jobs not yet finished/cleaned up | Pinned at cap 5 continuously |
| `admissionAvailable` | Capacity left to accept jobs | 0 for prolonged periods |
| `externalActive` | Jobs currently holding external permits | Exceeding 2 is an invariant bug |
| `externalPeak` | Highest active value observed | **Must never exceed 2** |
| `externalAvailable` | Remaining external permits | Must return to 2 when idle |
| `accepted/rejected` | Submission successes/rejections | Rejection spikes need throttling/upstream signals |
| `done/failed/interrupted` | Worker outcomes | Job fails yet HTTP 202 submit can still be valid |
| Executor terminated | No tasks still running after shutdown | false after deadline requires investigation |
| Resource pool metrics | JDBC/HTTP/broker active/pending | Leaks, backlogs, pool exhaustion |
| Process memory, GC | Memory of jobs/threads/payloads | Rising even when CPU is low |

A snapshot of `externalActive=0` does not prove jobs completed business side effects or committed transactions. A snapshot of `externalAvailable=2` only proves **internal semaphores** were returned. Measure **physical resources** and business state to assert end-to-end correctness.

### 13.2. Minimal invariants

In a steady lab JVM before shutdown:

~~~text
0 <= admittedInFlight <= 5
0 <= externalActive <= 2
0 <= externalPeak <= 2
admissionAvailable + admittedInFlight == 5
externalAvailable + externalActive == 2   (latest snapshot, races possible between reads)
~~~

Because `Semaphore.availablePermits()` and `AtomicInteger.get()` are read at slightly different instants, a `GET /lab/stats` right during release/acquire may show numbers not adding up instantaneously. Assert exact invariants only in quiescent states or via truly synchronized/atomic snapshot instrumentation.

### 13.3. Log markers

- `LAB_EXTERNAL_BEGIN`: task acquired a permit and is using the simulated external resource.
- `virtual=true`: code executed on a virtual thread.
- `LAB_EXTERNAL_RELEASE`: task passed through external critical-section cleanup.
- `LAB_ADMISSION_RELEASE`: job returned its admission permit.
- `LAB_FAILED`: exception inside task, not just submission error.
- `LAB_INTERRUPTED`: task responded to interruption.
- `LAB_SHUTDOWN_BEGIN` / `LAB_SHUTDOWN_END`: owner service lifecycle.
- `terminated=true` and `externalActive=0`: evidence of proper demo termination when combined with job states/counters.

In production, include request ID, job ID, trace ID, deadline, attempt count, and error category; avoid logging secrets, full request payloads, or sensitive business identifiers.

## 14. Failure scenarios and how to analyze them

| Symptom | Possible cause | Right check |
|---|---|---|
| `spring.threads.virtual.enabled` set yet job not virtual | Code submits to platform executor or different call path | Print `Thread.isVirtual()` inside actual task |
| Virtual threads rise while DB timeouts rise | Connection pool/upstream still capped | Hikari active/pending, query duration, call count |
| `externalPeak` exceeds cap | Wrong release, multiple semaphore instances, bypassed guard | Check bean scope and paired acquire/release |
| After job fails, `externalAvailable` stays short | Missing `finally` or wrong release path | Inject failure and inspect release logs |
| Permits grow above cap | Releasing when acquire failed | Use `slotHeld` boolean, release only when truly held |
| Shutdown hangs | I/O lacks timeout/interrupt, `close()` waits forever | Thread dumps, deadlines, shutdownNow/awaitTermination |
| JVM exits when only scheduler virtual threads remain | Daemon semantics | Check `spring.main.keep-alive=true` |
| Pool max-size set yet concurrency remains high | Virtual threads do not use those pool settings | Add admission/downstream gates |
| Job status stuck RUNNING after crash | In-RAM registry only, not durable | Persistent job store/leases/heartbeats |
| Calling `ExecutorService.close()` slows shutdown | `close()` waits for tasks to finish | Bounded shutdown strategy, timeouts |
| Task interrupted yet external request keeps running | Client lacks fast cancellation support | Request timeouts, explicit close/cancel, library docs |
| A bean creates its own executor and never closes it | Missing owner lifecycle | Appropriate `@PreDestroy` or `SmartLifecycle` |
| Multiple replicas exceed cluster-wide API quota | Semaphore is local-only | Distributed rate limits/coordination |
| Adding a Semaphore next to JDBC pool raises latency | Redundant cap or wrong layer chosen | Measure DB pool, decide where gate belongs |
| CPU hits 100%, throughput stops rising | CPU-bound work | Core count, CPU profile; virtual threads do not add compute |
| Prolonged pinned virtual threads on JDK 21 | Blocking inside synchronized/native | JFR pinned events, thread dumps, JDK upgrade |
| HTTP 202 yet jobs lost on restart | Admission is RAM-only | Durable queue and ack/idempotency |
| New requests still arrive when publishing refusing | Readiness is a signal, no app gate yet | Check routing and `stopping` state at submit |
| `executor.isTerminated=false` after deadline | Task uncooperative or unstarted pending | Failure logs, thread dump, external resource cleanup |

## 15. Graded extension exercises

### Exercise A — Proof of 2 external calls and 5 admitted jobs

Run six `kind=block` requests from a fresh JVM. Confirm 5 HTTP 202, 1 HTTP 429, `externalActive=2`, `admittedInFlight=5`, `externalPeak<=2`. Explain why there is **not** a virtual-thread pool of size 2.

### Exercise B — Verify release on the happy path

Call `POST /lab/release`, wait for accepted jobs to finish, and verify `done=5`, `admissionAvailable=5`, `externalAvailable=2`. Explain why you must wait for a quiescent state before comparing snapshots.

### Exercise C — Verify cleanup on exception

Run `kind=fail`. Observe `FAILED` after the HTTP 202 response, `LAB_EXTERNAL_RELEASE`, and `LAB_ADMISSION_RELEASE`. Point out how `finally` ensures release despite exceptions.

### Exercise D — Verify stopping while blocked

Run 5 block jobs without releasing, then use Ctrl+C/SIGTERM. Record `LAB_SHUTDOWN_INTERRUPT`, interrupted/release markers, and `LAB_SHUTDOWN_END`; explain why `shutdownNow()` is only best-effort if tasks are uncooperative.

### Exercise E — Test missing cleanup in a copy

In a lab copy, intentionally remove `externalSlots.release()` from `finally`. Submit a `fail` job, then more jobs; compare permit counts and timeout waits. Restore the code immediately. **Only do this with simulated resources**, never inducing leaks in production or external services.

### Exercise F — Replace mock external with controlled real HTTP

Use a local mock server or test container, not a production service. Cap at 2 concurrent requests, set finite timeouts, log request start/end; verify the ceiling is never exceeded under load, and cleanup/response closing executes on timeout/interrupt.

### Exercise G — Replace mock external with a JDBC pool

Use a test database and Hikari metrics. Spawn 10+ virtual threads with a 2-connection pool; measure active/pending/acquire times and confirm connections return after exceptions. Evaluate whether an extra semaphore is needed or if the pool already bounds reasonably.

### Exercise H — Test real crashes and durability

Compare graceful SIGTERM with SIGKILL after HTTP 202 in the lab. Confirm that after SIGKILL you cannot rely on `@PreDestroy` or an in-RAM job registry for recovery. Propose a durable table/queue + retry/idempotency and test redelivery after restart.

## 16. Acceptance checklist

- [ ] Runs on Java 21+ and compiles the Spring Boot 3.5.x project.
- [ ] Understands `spring.threads.virtual.enabled=true` and `spring.main.keep-alive=true` have distinct roles.
- [ ] Observed `Thread.currentThread().isVirtual()==true` inside workers.
- [ ] Explains why virtual threads do not give databases/APIs infinite capacity.
- [ ] Reproduced 5 accepted + 1 rejected with admission limit 5.
- [ ] Observed externalActive/Peak at most 2 with external semaphore 2.
- [ ] Observed remaining jobs in `WAITING_SLOT` instead of slipping into the external critical section.
- [ ] Proved both success and failure execute `finally` to release permits.
- [ ] Caught and handled `InterruptedException`, restoring the interrupt flag.
- [ ] Verified graceful shutdown and interrupt escalation have bounded waits.
- [ ] Read `executor.isTerminated()` and permit counts after stop to draw lab-scoped conclusions.
- [ ] Stated limitations of SIGKILL and uninterruptible external I/O.
- [ ] Knows how to close JDBC connections, HTTP bodies, and broker consumers per proper owner.
- [ ] Knows Boot pool properties do not replace external concurrency limits.
- [ ] Distinguished readiness routing, admission, and executor shutdown.
- [ ] Proposed a durable job queue/idempotency if 202 must guarantee no lost work.
- [ ] Distinguished JDK 21 pinning from JDK 24+ improvements.
- [ ] Captured logs/metrics for accepted, rejected, externalPeak, failed, and interrupted.

## 17. Official documentation

1. **Oracle JDK 21 — Virtual Threads**: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html — lifecycle, carriers, semaphores, interrupts, pinning, and observation.
2. **Java SE 21 — Executors**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html — `newVirtualThreadPerTaskExecutor()`.
3. **Java SE 21 — ExecutorService**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html — `shutdown`, `shutdownNow`, `awaitTermination`, and `close`.
4. **Spring Boot 3.5 — SpringApplication, Virtual Threads**: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html — enablement, daemon behavior, and keep-alive.
5. **Spring Boot 3.5 — Task Execution and Scheduling**: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html — Boot auto-configured executors/schedulers with virtual threads.
6. **Spring Boot 3.5 — Graceful Shutdown**: https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html — HTTP connectors and lifecycle phase timeouts.
7. **Spring Framework 6.2 — SimpleAsyncTaskExecutor**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/SimpleAsyncTaskExecutor.html — virtual threads option and concurrency limiting.
8. **Java SE 21 — Semaphore**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html — acquire/release, fairness, and interruptibility.

**Conclusion:** Virtual threads make **one Java thread per blocking job** practical; they do not replace resource limits. A proper system must **reject or queue work with bounds before spawning endless threads**, **cap operations occupying external resources**, **set deadlines**, **release in `finally`**, and **stop intake + drain/cancel on shutdown**. In the lab, reliable milestones are `externalPeak<=2`, permits returning to initial counts, and `terminated=true` on cooperative stop. In production, add real verification with JDBC/HTTP/brokers and durable job persistence before promising zero lost work.