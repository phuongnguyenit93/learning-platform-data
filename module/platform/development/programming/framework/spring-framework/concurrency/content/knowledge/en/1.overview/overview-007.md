# End-to-End Example: Report Processing and Periodic Data Updates

## 1. Problem Statement and Goals

Suppose a Spring service receives requests to generate revenue/summary reports over HTTP. Aggregation may take several seconds or minutes; at the same time, the application must update background metrics periodically. If the report is processed directly on the HTTP thread, the user has to hold the connection open for a long time and request-serving threads can be exhausted. If a new thread is spawned manually for every request, thread count and memory usage can easily grow out of control.

We separate two types of work:

1. **On-demand reports:** `POST /reports` creates a job ID and returns `202 Accepted` early; a bounded `TaskExecutor` processes it in the background. `GET /reports/{id}` returns status `PENDING`, `RUNNING`, `DONE`, or `FAILED`.
2. **Periodic data updates:** `TaskScheduler` triggers a `@Scheduled` method, updating the metrics table every 30 seconds after the previous run finishes. The `GET /metrics` API allows observing the current value.

In this demo, the data is a counter in H2 and the report reads the counter then simulates a slow aggregation step. This is a minimal model to show the execution flow and when data is read; in real applications, the SQL can be replaced by aggregation queries, CSV/PDF export, reading external sources, or saving results to object storage.

~~~mermaid
flowchart LR
    U[Client] -->|POST /reports| C[ReportController]
    C -->|save PENDING| R[ReportStore]
    C -->|call another bean| E[reportExecutor]
    E --> W[ReportWorker]
    W -->|read metrics| DB[(H2 metrics)]
    W -->|RUNNING / DONE / FAILED| R
    U -->|GET /reports/id| C
    S[taskScheduler] -->|every 30s after completion| J[MetricJob]
    J -->|UPDATE atomic| DB
    U -->|GET /metrics| DB
~~~

**Two distinct concepts:** `TaskExecutor` decides *where and with how many threads* a task runs; `TaskScheduler` decides *when* a task is triggered. `@Async` typically dispatches work to an executor; `@Scheduled` registers a schedule with a scheduler. Neither mechanism by itself guarantees durable job persistence when the process shuts down.

## 2. Building a Runnable Application (Java 17, Spring Boot 3.3.5)

Use Spring Boot to bootstrap the application, web server, and H2 connection; the annotations and executor/scheduler demonstrated are **Spring Framework** features. Structure:

~~~text
spring-concurrency-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/demo/
    │   ├── DemoApplication.java
    │   ├── ReportStatus.java
    │   ├── ReportStore.java
    │   ├── ReportWorker.java
    │   ├── ReportController.java
    │   ├── MetricJob.java
    │   └── MetricsController.java
    └── resources/
        ├── schema.sql
        └── data.sql
~~~

### 2.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>spring-concurrency-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 2.2. Enabling Scheduling/Async and Configuring Two Pools

`src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean("reportExecutor")
    ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("report-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }

    @Bean
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("schedule-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(20);
        return scheduler;
    }
}
~~~

`reportExecutor` has 2 core threads, a maximum of 4 threads, and a queue of up to 20 tasks; when full, it can reject new requests. With standard `ThreadPoolExecutor` configuration, threads beyond the core count are only created once the queue is full, so `maxPoolSize` does not mean 4 threads are always running. `taskScheduler` is a separate pool for periodic tasks, preventing report generation from occupying scheduling threads. The bean name `taskScheduler` allows the `@Scheduled` mechanism to discover this scheduler.

### 2.3. Initializing Data

`src/main/resources/schema.sql`:

~~~sql
CREATE TABLE metrics (
    id INTEGER PRIMARY KEY,
    total BIGINT NOT NULL
);
~~~

`src/main/resources/data.sql`:

~~~sql
INSERT INTO metrics (id, total) VALUES (1, 0);
~~~

Spring Boot automatically executes these SQL initialization scripts when using embedded H2 with default settings. On each fresh startup with in-memory H2, the demo data can reset from 0. The `total = total + 1` update is performed directly in SQL, avoiding read-then-write patterns that easily lose updates under multiple threads.

### 2.4. Report Status Store

`src/main/java/com/example/demo/ReportStatus.java`:

~~~java
package com.example.demo;

import java.util.UUID;

public record ReportStatus(UUID id, String status, Long total, String error) {
}
~~~

`src/main/java/com/example/demo/ReportStore.java`:

~~~java
package com.example.demo;

import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Service;

@Service
public class ReportStore {
    private final ConcurrentMap<UUID, ReportStatus> jobs = new ConcurrentHashMap<>();

    public void pending(UUID id) {
        jobs.put(id, new ReportStatus(id, "PENDING", null, null));
    }

    public void running(UUID id) {
        jobs.put(id, new ReportStatus(id, "RUNNING", null, null));
    }

    public void done(UUID id, long total) {
        jobs.put(id, new ReportStatus(id, "DONE", total, null));
    }

    public void failed(UUID id, String error) {
        jobs.put(id, new ReportStatus(id, "FAILED", null, error));
    }

    public ReportStatus find(UUID id) {
        return jobs.get(id);
    }
}
~~~

`ConcurrentHashMap` allows HTTP threads and worker threads to access it concurrently; each `ReportStatus` is an immutable record, so updates replace the entire value atomically. This is only in-RAM state: a restart loses jobs and statuses; a real system should persist them in a `report_jobs` table or durable store with retention/cleanup policies.

### 2.5. Asynchronous Worker

`src/main/java/com/example/demo/ReportWorker.java`:

~~~java
package com.example.demo;

import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportWorker {
    private final JdbcTemplate jdbc;
    private final ReportStore store;

    public ReportWorker(JdbcTemplate jdbc, ReportStore store) {
        this.jdbc = jdbc;
        this.store = store;
    }

    @Async("reportExecutor")
    public void generate(UUID id) {
        store.running(id);
        try {
            Long total = jdbc.queryForObject(
                    "SELECT total FROM metrics WHERE id = 1", Long.class);
            if (total == null) {
                throw new IllegalStateException("Data not found");
            }

            // Simulates a time-consuming aggregation/file-generation step.
            Thread.sleep(1500);
            store.done(id, total);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            store.failed(id, "Job interrupted during application shutdown");
        } catch (Exception ex) {
            store.failed(id, "Unable to generate report");
        }
    }
}
~~~

`@Async("reportExecutor")` only takes effect when the method is called through a Spring proxy—in this example, **ReportController calling a different bean, ReportWorker**. If called via `this.generate(id)` from a method in the same class, the internal call bypasses the proxy and usually runs synchronously. Do not pass `HttpServletRequest`, `EntityManager`, or closing request resources to the background thread; pass the required ID/input data and open resources inside the worker. `Thread.sleep` is only a simulation, not a report-processing technique.

If you want to obtain the result via a Java API (instead of polling status over HTTP), the `@Async` method can return `CompletableFuture<T>`. Do not call `join()` or `get()` immediately on the HTTP thread if the goal is to return a fast response.

### 2.6. HTTP API Returning the Job ID

`src/main/java/com/example/demo/ReportController.java`:

~~~java
package com.example.demo;

import java.net.URI;
import java.util.UUID;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/reports")
public class ReportController {
    private final ReportStore store;
    private final ReportWorker worker;

    public ReportController(ReportStore store, ReportWorker worker) {
        this.store = store;
        this.worker = worker;
    }

    @PostMapping
    public ResponseEntity<ReportStatus> submit() {
        UUID id = UUID.randomUUID();
        store.pending(id);
        try {
            worker.generate(id);
        } catch (TaskRejectedException ex) {
            store.failed(id, "Queue is full, please retry");
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(store.find(id));
        }
        return ResponseEntity.accepted()
                .location(URI.create("/reports/" + id))
                .body(store.find(id));
    }

    @GetMapping("/{id}")
    public ResponseEntity<ReportStatus> status(@PathVariable UUID id) {
        ReportStatus result = store.find(id);
        return result == null
                ? ResponseEntity.notFound().build()
                : ResponseEntity.ok(result);
    }
}
~~~

`202 Accepted` confirms the request was accepted for processing, without guaranteeing the report will succeed. The `Location` header points to the status resource. At the time of the response, `status` may already be `PENDING` or `RUNNING`, or even `DONE` if the work finished very quickly: do not write tests assuming an exact instantaneous state. If the executor rejects the task because it is full, the API returns `503 Service Unavailable`.

### 2.7. Periodic Updates and Metrics Lookup API

`src/main/java/com/example/demo/MetricJob.java`:

~~~java
package com.example.demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MetricJob {
    private final JdbcTemplate jdbc;

    public MetricJob(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Scheduled(initialDelay = 5_000, fixedDelay = 30_000)
    public void refresh() {
        int rows = jdbc.update(
                "UPDATE metrics SET total = total + 1 WHERE id = 1");
        if (rows != 1) {
            throw new IllegalStateException("Missing metrics row id=1");
        }
    }
}
~~~

`src/main/java/com/example/demo/MetricsController.java`:

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MetricsController {
    private final JdbcTemplate jdbc;

    public MetricsController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @GetMapping("/metrics")
    public Map<String, Long> current() {
        Long total = jdbc.queryForObject(
                "SELECT total FROM metrics WHERE id = 1", Long.class);
        return Map.of("total", total);
    }
}
~~~

About 5 seconds after the application starts, `MetricJob` runs for the first time. With `fixedDelay = 30_000`, the next run starts at least 30 seconds *after the previous one finishes* (which may be delayed if the system is busy). The counter increments by 1 on each successful run; if a report reads before an update, it may reflect the older value. That is a snapshot at read time, not a synchronization bug.

## 3. Running the Processing Flow

Requires JDK 17+ and Maven. In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -s http://localhost:8080/metrics
curl -i -X POST http://localhost:8080/reports
# Extract id from the POST response JSON, then replace ACTUAL_UUID with that value:
curl -s http://localhost:8080/reports/ACTUAL_UUID
~~~

For example, `GET /metrics` initially returns `{"total":0}`. After the first update, this becomes 1, then keeps increasing as runs succeed. `POST /reports` returns HTTP 202 and JSON like:

~~~json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PENDING",
  "total": null,
  "error": null
}
~~~

The UUID above is **illustrative only**; the initial status may differ due to concurrent execution. Use the actual UUID returned by POST when calling GET. Around 1.5 seconds after the worker starts, the response looks like:

~~~json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "DONE",
  "total": 1,
  "error": null
}
~~~

The value of `total` depends on when the worker reads the table, and is not fixed at 1. To observe queue limits, send multiple concurrent POST requests; when the executor saturates, some requests may receive 503. When the application stops/restarts, in-memory H2 and `ReportStore` lose the demo data.

## 4. Why Does This Design Not Block HTTP?

- **Request thread:** creates the UUID and `PENDING` status, submits the task to the pool, and returns 202 quickly; does not wait for `Thread.sleep`.
- **Report thread:** marks `RUNNING`, reads the DB, performs the slow step, and saves `DONE`/`FAILED`; the number of concurrently active tasks is bounded by the pool.
- **Scheduler thread:** independent of the report pool; runs a small update operation, then schedules the next run.
- **Shared state:** `ConcurrentHashMap` is safe for individual `put/get` operations; if multi-step conditional state transitions are needed (such as `PENDING -> RUNNING` once), use `compute`/CAS or conditional state updates in the DB.

Even though the two pools separate threads, they still share real resources such as the connection pool, CPU, RAM, and DB. If 50 reports all run heavy queries, scheduled tasks can still slow down because the DB is overloaded. Therefore, you must measure durations, limit DB access, and implement backpressure.

### Comparing Scheduling Mechanisms

| Option | Meaning | Best Fit |
| --- | --- | --- |
| `@Scheduled(fixedDelay = 30000)` | Waits 30 seconds after the previous run *finishes* | Data synchronization/polling that does not require a fixed start cadence |
| `@Scheduled(fixedRate = 30000)` | Targets start times at a 30-second period | Lightweight jobs needing a steady cadence; slow runs can cause delays |
| `@Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")` | Runs on a calendar schedule, e.g., 02:00 daily in a specified time zone | End-of-day reports, book closing |

These are **three alternative choices** for the same job's schedule—do not place all three annotations on the demo method. `fixedRate` does not automatically guarantee parallel execution of runs of the same job; the schedule and pool also affect behavior. If a scheduled run dispatches work to an executor, background executions can overlap, so duplicate/overlap control is needed.

## 5. Turning the Demo Into a Production Design

### 5.1. Durable Storage and Idempotency

For reports taking minutes, persist each job in the DB with fields such as `id`, `request_key`, `state`, `created_at`, `attempts`, `result_location`, and `error_code`. When a client retries due to a timeout, use an idempotency key or unique constraint to avoid generating two identical reports. Workers should perform conditional updates—for instance, only one worker may transition `PENDING` to `RUNNING`; store report files in shared storage rather than one instance's RAM.

Periodic tasks should store a watermark such as `last_processed_at` or `source_version`. Each run reads only new data and `UPSERT`s by business key; on retry, results are not mistakenly double-counted. The counter-increment SQL in the demo is **not idempotent**: calling it twice increments twice, so do not use this pattern as-is for real financial data.

### 5.2. Multiple Instances and Transactions

`@Scheduled` is registered **within each application context**. If 3 pods run, each pod can run its own job: a shared table risks being updated 3 times. To ensure a logical run executes once across the whole cluster, use a distributed lock/DB lock, an external scheduler, or a queue system with job-claiming semantics; design for retries because failures can happen between doing the work and recording completion.

`@Transactional` binds to the executing thread's context. An HTTP request's transaction **does not automatically propagate** to an `@Async` worker. If a transaction is needed, open it on a service method invoked by the worker on the background thread or use `TransactionTemplate`; avoid holding a transaction open throughout file generation or external API calls. In the JDBC demo, each UPDATE auto-commits on the default connection when no surrounding transaction is present.

### 5.3. Errors, Resources, and Application Shutdown

- `@Async void` returns no Future to the caller; the worker should catch/record business errors, update `FAILED`, and log with the job ID. If an exception escapes, configure `AsyncUncaughtExceptionHandler` for uncaught errors.
- `@Scheduled` jobs can fail on any run. Do not rely solely on logs: track failure counts, last success timestamp, overdue alerts, timeouts on external service calls, and retries with appropriate backoff.
- Bound `corePoolSize`, `maxPoolSize`, and `queueCapacity` according to load and the connection pool; return 429/503 when unable to accept more work. An in-memory queue is not a durable message queue.
- Monitor `active threads`, `queued tasks`, `rejected tasks`, completion duration, error rate, and `PENDING` to `RUNNING` queue delay. Include correlation/job IDs in logs; MDC and Spring Security context do not automatically carry across all threads, so intentional propagation is required.
- On shutdown, the pool can wait for running tasks within the configured limit; the 20-second limit in the demo does not guarantee long reports finish. For critical jobs, you need checkpointing and post-restart recovery mechanisms.

### 5.4. Common Pitfalls

| Symptom | Common Cause | How to Address |
| --- | --- | --- |
| `@Async` still blocks HTTP | Internal call `this.method()`; missing `@EnableAsync` | Call through another bean/proxy, check thread names |
| `@Scheduled` does not run | Missing `@EnableScheduling`; bean not Spring-managed | Register the bean, inspect logs and startup |
| Duplicate reports | Client retries or multiple workers/pods pick up the same work | Idempotency keys, conditional state transitions |
| Metrics double-counted | Multiple pods running the same schedule or non-idempotent retries | Cluster-wide lock, watermark, upsert |
| Report sees stale data | Reading snapshot before a new update | Record snapshot timestamp, define freshness SLAs |
| Request thread exhaustion / DB bottleneck | Unbounded pool and queue or heavy queries | Bounded pools, timeouts, backpressure, load testing |
| Jobs lost after restart | Status/queue stored in RAM | DB/job broker, resume/retry mechanisms |

## 6. Testing Checklist and Self-Check Questions

1. **HTTP flow:** POST returns 202 faster than the 1.5-second simulated step; verify `Location` and GET with the actual ID; final status is `DONE` or `FAILED`.
2. **Schedule:** GET `/metrics` before and after at least one scheduled run to verify the value increases; use a short `fixedDelay` interval in tests and verify the next start time is measured from when the previous run finished.
3. **Concurrent load:** send multiple POSTs, measure `report-*` thread count, queue length, and 503 responses under saturation; ensure the scheduler keeps operating.
4. **Failures:** temporarily make the DB query fail and verify the job transitions to `FAILED` with sufficient logs/metrics to investigate; test interruption/application shutdown.
5. **Multiple instances:** run two instances against the same test DB to observe that the schedule can run twice; then test the corresponding locking or deduplication mechanism.
6. **Consistency:** define whether a report reflects data as of start time, SELECT time, or completion time; do not promise the "latest" value unless business rules specify it.

**Self-answer:** (a) Why should `@Async` reside on a different bean from the caller? (b) When running 3 pods, how many `@Scheduled` triggers can fire per cycle? (c) Why must the queue be bounded? (d) Does the HTTP transaction follow into the async worker? (e) How do you retry a periodic update without double-counting?

Official documentation: [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html).