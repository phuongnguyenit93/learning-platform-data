# Detecting Slow Checks and Avoiding Data-Mutating Operations

## 1. Observation Also Consumes Resources

A health check does not sit outside the system being observed. It still uses CPU, threads, connections, memory, and resources of dependent services. If a slow check is called frequently, monitoring itself can add load right when the system is struggling.

Another mistake is even harder to spot: a check that seems merely to "test whether it works" consumes a message from a queue, updates a processing timestamp, or creates a business record. The result may be `UP`, yet reading health mutated the system.

This lesson uses **Java 21 and Spring Boot 3.3.0** for two paired goals:

- identify which check is slow, measure the right scope, and understand Actuator's warning;
- design read-only checks with bounded cost that do not mutate business data.

The example is an in-memory work queue. Health reads the queue length; it does not dequeue jobs to process. A small model lets us verify before/after state without connecting to an external system.

## 2. Slow, Timed Out, and DOWN Are Three Different Conclusions

| Signal | What does it tell you? | What must not be inferred automatically |
| --- | --- | --- |
| Check takes a long time | One observation spent noticeable time. | The component must definitely be `DOWN`. |
| Operation timed out | No result arrived within the deadline set for that operation. | All underlying work has been completely canceled. |
| Indicator returns `DOWN` | Failed the health policy applied by the indicator. | The cause is necessarily slowness. |
| HTTP health is slow | Total time to receive a response is high. | One single indicator is the sole cause. |

A check can return `UP` after 150 ms while triggering a warning because the warning threshold is 50 ms. The two signals do not contradict each other: `UP` describes pass/fail criteria, while the warning describes time cost.

Conversely, a check can return `DOWN` very quickly because it detected a misconfiguration. Do not use response speed as a substitute for the status and evidence inside.

## 3. Detecting Slow Checks with Actuator

### 3.1. Warning Threshold

In Spring Boot 3.3, Actuator has a slow-indicator warning threshold, defaulting to **10 seconds**. It can be adjusted via:

```properties
management.endpoint.health.logging.slow-indicator-threshold=200ms
```

The value above is an example for observation in a learning environment, not a recommended threshold for every system. Real thresholds must match your time budget, call frequency, and characteristics of the checked resource. See [Spring Boot 3.3 rules on slow indicators](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators).

Keep the log level allowing `WARN` where Actuator logs warnings. If your logging setup only accepts `ERROR`, lowering the threshold will not make warnings appear.

### 3.2. Warnings Are Not Cancellation Mechanisms

On Spring Boot 3.3.0's synchronous check path, `HealthEndpointSupport` records the start time, invokes the contributor, and checks the duration in `finally`. When duration exceeds the threshold and the logger allows `WARN`, it logs a warning naming the contributor and elapsed time. This mechanism does not automatically change the result to `DOWN`, create a client timeout, or launch a background process to stop the operation. You can cross-check [HealthEndpointSupport](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java).

Therefore, on this synchronous path, if the call has not returned yet, do not expect that warning to appear the instant the clock crosses the threshold. Timeouts are needed at the I/O-executing layer to prevent indefinite waiting.

Calling `indicator.health()` directly inside a unit test also bypasses the endpoint layer responsible for logging this warning. To verify Actuator's warning, call through the endpoint or the corresponding support path.

### 3.3. Measure Both the Full Request and Individual Checks

A request's duration can also include routing, authentication, waiting for workers/connections, multiple checks, and response rendering. A synchronous request with five sequential checks taking roughly 300 ms each can spend around 1.5 seconds on checks alone even though none crosses a 500 ms threshold.

Thus, observe both HTTP latency and individual check latency. For reactive flows, measure until the publisher's terminal signal rather than measuring only the time to create a `Mono`. Do not infer asynchronous measurement scope from a synchronous experiment or from the method returning very quickly.

## 4. What Does "Not Mutating Data" Mean?

In this lesson, the goal is avoiding business side effects: not dispatching jobs, not consuming/acknowledging messages, not altering orders, not refreshing data expiration, and not triggering business workflows.

This does not mean a check leaves zero operational footprint. It may still emit logs, increment monitoring counters, open connections, or consume service quota. Those costs must also be accounted for.

| Resource | Potentially suitable observation | Operations that easily mutate the system |
| --- | --- | --- |
| Queue | Read metadata/depth via appropriate admin API or an existing snapshot. | Consuming messages, acking, sending test messages into a business queue. |
| Database | Connection check or reviewed small read query. | Insert/update/delete, calling procedures that mutate data. |
| Cache | Read metadata or a probe key per a designed contract. | Overwriting real data, extending TTL, deleting keys to test permissions. |
| HTTP service | Call a read-only check API with confirmed semantics. | Calling URLs with reset behavior, resource creation, or business execution. |
| Filesystem | Read required metadata or state published by the owning component. | Creating/deleting files in a business directory on every health call. |

Method names or HTTP verbs alone are not enough to guarantee read-only behavior. A `GET` URL can still be implemented poorly; a `SELECT` statement can invoke a function with side effects. Inspect the actual behavior of the API, query, and associated resources.

An active test that writes data can be useful in dedicated synthetic testing with isolated resources and explicit cleanup procedures. Do not place it into frequently polled health checks just because it feels like the fastest way to prove "writes work."

## 5. Complete Example: Read-Only Queue Health

This is a standalone Maven project. File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>learning</groupId>
    <artifactId>slow-probe-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

### 5.1. Separating Status Reads from Taking Work

File `src/main/java/learning/slowprobe/WorkQueue.java`:

```java
package learning.slowprobe;

import java.util.ArrayDeque;
import java.util.Collection;
import java.util.Deque;
import java.util.Objects;

public final class WorkQueue {

    public record Snapshot(int pending, long deliveries) {
        public Snapshot {
            if (pending < 0 || deliveries < 0) {
                throw new IllegalArgumentException("Queue counters must not be negative");
            }
        }
    }

    private final Deque<String> jobs;
    private long deliveries;

    public WorkQueue(Collection<String> initialJobs) {
        this.jobs = new ArrayDeque<>(Objects.requireNonNull(initialJobs, "initialJobs"));
    }

    public synchronized Snapshot inspect() {
        return new Snapshot(jobs.size(), deliveries);
    }

    public synchronized String deliverNext() {
        String job = jobs.pollFirst();
        if (job != null) {
            deliveries++;
        }
        return job;
    }
}
```

`inspect()` only takes a snapshot of counters; `deliverNext()` takes a job out of the queue and increments deliveries. The two methods serve two different purposes. Health must use `inspect()`, not "try taking one job and figure it out later."

`synchronized` keeps the snapshot consistent in this small model. In a real system, examine lock hold times and the broker's metadata read path; do not assume a network admin call costs the same as `jobs.size()` in memory.

### 5.2. Indicator Accepting a Read Hook

File `src/main/java/learning/slowprobe/QueueHealthIndicator.java`:

```java
package learning.slowprobe;

import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;

public final class QueueHealthIndicator implements HealthIndicator {

    private final Callable<WorkQueue.Snapshot> reader;
    private final int maxPending;

    public QueueHealthIndicator(Callable<WorkQueue.Snapshot> reader, int maxPending) {
        this.reader = Objects.requireNonNull(reader, "reader");
        if (maxPending < 0) {
            throw new IllegalArgumentException("maxPending must not be negative");
        }
        this.maxPending = maxPending;
    }

    @Override
    public Health health() {
        long started = System.nanoTime();
        Health.Builder builder = Health.unknown().withDetail("maxPending", maxPending);
        try {
            WorkQueue.Snapshot snapshot = reader.call();
            if (snapshot == null) {
                builder.down().withDetail("reason", "NO_SNAPSHOT");
            }
            else {
                builder.withDetail("pending", snapshot.pending());
                if (snapshot.pending() > maxPending) {
                    builder.down().withDetail("reason", "BACKLOG_LIMIT");
                }
                else {
                    builder.up().withDetail("reason", "WITHIN_LIMIT");
                }
            }
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            builder.down().withDetail("reason", "INTERRUPTED");
        }
        catch (Exception ex) {
            builder.down().withDetail("reason", "READ_FAILED");
        }
        long durationMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started);
        return builder.withDetail("durationMs", durationMs).build();
    }
}
```

The indicator takes a read hook instead of needing direct access to the queue's entire API. This makes responsibilities clear and easy to test; it is not a security barrier preventing malicious lambdas. You must still verify the supplied implementation is genuinely read-only.

`System.nanoTime()` is used to measure elapsed duration; do not use wall-clock differences as a performance stopwatch. `durationMs` is the time inside the indicator, excluding the full HTTP request or steps outside it. Putting that measurement into details also does not automatically create a historical metric.

`maxPending` is the example's backlog policy. Exactly at the threshold still passes; exceeding the threshold yields `DOWN`. Being slow does not automatically make the indicator `DOWN`: if reading succeeds and backlog meets criteria, it still returns `UP`. If latency limits are required as a health criterion, add that policy explicitly.

### 5.3. Verifying Repeated Calls Do Not Consume Jobs

File `src/main/java/learning/slowprobe/QueueReadOnlyDemo.java`:

```java
package learning.slowprobe;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.actuate.health.Status;

public class QueueReadOnlyDemo {

    public static void main(String[] args) {
        WorkQueue queue = new WorkQueue(List.of("job-1", "job-2"));
        WorkQueue.Snapshot before = queue.inspect();
        AtomicInteger observations = new AtomicInteger();
        var indicator = new QueueHealthIndicator(() -> {
            observations.incrementAndGet();
            return queue.inspect();
        }, 100);

        for (int i = 0; i < 3; i++) {
            if (!Status.UP.equals(indicator.health().getStatus())) {
                throw new AssertionError("Unexpected health status");
            }
        }
        WorkQueue.Snapshot after = queue.inspect();
        if (!before.equals(after) || observations.get() != 3) {
            throw new AssertionError("Observation changed business state or was skipped");
        }

        System.out.println("status=UP");
        System.out.println("pendingBefore=" + before.pending());
        System.out.println("pendingAfter=" + after.pending());
        System.out.println("deliveriesBefore=" + before.deliveries());
        System.out.println("deliveriesAfter=" + after.deliveries());
        System.out.println("observations=" + observations.get());
        System.out.println("businessStateUnchanged=" + before.equals(after));
    }
}
```

In the project directory, verify Maven uses JDK 21 and compile:

```shell
mvn -version
mvn compile dependency:build-classpath "-Dmdep.outputFile=target/classpath.txt"
```

Run on PowerShell:

```powershell
$dependencyClasspath = (Get-Content -Raw -LiteralPath 'target/classpath.txt').Trim()
java -cp "target/classes;$dependencyClasspath" learning.slowprobe.QueueReadOnlyDemo
```

Or run on Linux/macOS:

```shell
java -cp "target/classes:$(cat target/classpath.txt)" learning.slowprobe.QueueReadOnlyDemo
```

Maven compiled the Java sources with the required classpath. Do not run `javac QueueHealthIndicator.java` standalone without adding Actuator libraries to the classpath.

Exact stdout:

```text
status=UP
pendingBefore=2
pendingAfter=2
deliveriesBefore=0
deliveriesAfter=0
observations=3
businessStateUnchanged=true
```

`observations` increasing is an instrumentation trace intentionally created in the test; the job count and delivery count remain unchanged. The check does not merely compare statuses: it proves all three reads occurred without altering the model's business state.

## 6. Creating a Controlled Slow Read to Observe Warnings

File `src/main/java/learning/slowprobe/SlowProbeApplication.java`:

```java
package learning.slowprobe;

import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SlowProbeApplication {

    public static void main(String[] args) {
        SpringApplication.run(SlowProbeApplication.class, args);
    }

    @Bean
    WorkQueue workQueue() {
        return new WorkQueue(List.of("job-1", "job-2"));
    }

    @Bean
    QueueHealthIndicator workQueueHealthIndicator(
            WorkQueue queue,
            @Value("${demo.delay-ms:150}") long delayMs,
            @Value("${demo.max-pending:100}") int maxPending) {
        if (delayMs < 0) {
            throw new IllegalArgumentException("delayMs must not be negative");
        }
        return new QueueHealthIndicator(() -> {
            Thread.sleep(delayMs);
            return queue.inspect();
        }, maxPending);
    }
}
```

`Thread.sleep` only simulates latency, not an operation that belongs in a real health check. All reads still use `inspect()`. Latency and backlog are two independent variables for testing policies.

File `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health
management.endpoint.health.show-components=always
management.endpoint.health.show-details=always
management.endpoint.health.logging.slow-indicator-threshold=50ms
logging.level.org.springframework.boot.actuate.health.HealthEndpointSupport=WARN
```

The bean name `workQueueHealthIndicator` creates the contributor `workQueue`. Start:

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.slowprobe.SlowProbeApplication"
```

In another terminal, call:

```shell
curl -i http://127.0.0.1:8080/actuator/health/workQueue
```

On Windows, you can use `mvn.cmd` and `curl.exe`. With a backlog of 2 and limit of 100, the branch returns `UP` and HTTP `200`. Details look like:

```json
{
  "status": "UP",
  "details": {
    "maxPending": 100,
    "pending": 2,
    "reason": "WITHIN_LIMIT",
    "durationMs": 151
  }
}
```

`151` is an illustrative number, not a fixed value, and can be higher when the system is busy. At the same time, Actuator's log contains a warning naming the `workQueue` contributor and its response time. This version's message includes the identifying text `Health contributor` and `took ... to respond`; class name, duration, timestamp, and formatting depend on the run/logging configuration.

The takeaway to observe is: **the 50 ms threshold does not cut off the call at 50 ms**. The ~150 ms simulated read still finishes and returns `UP`, and then the warning indicates it was slower than the threshold.

Stop the application and test a backlog exceeding the limit:

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.slowprobe.SlowProbeApplication" "-Dspring-boot.run.arguments=--demo.max-pending=1"
```

Now the contributor returns `DOWN/BACKLOG_LIMIT`, HTTP `503` per default mapping, yet does not dequeue jobs to try reducing the backlog. Read-only behavior must hold even when the result is unhealthy.

The configuration exposing full details serves observation on loopback. In production, use appropriate access policies and avoid putting job payloads or sensitive data into health results.

## 7. Ways of "Testing to Be Sure" That Easily Mutate the System

### Taking a Message and Putting It Back

Receiving and re-sending or acking/nacking a message is not equivalent to never having received it. It can alter ordering, delivery counts, visibility timeouts, dead-letter policies, or broker processing traces. In the model above, `deliverNext()` altered both the job count and the delivery count.

Do not invoke real processing APIs to verify observability. Read metadata, connection status, or a snapshot published by the owning component, depending on the question you need answered.

### Writing a Record and Rolling Back or Deleting Immediately

Rollback is not proof of zero cost or side effects. The operation may have held locks, consumed sequences, triggered external logic, or emitted a non-transactional event. Insert-then-delete also has a real window of existence and can leave traces in other systems.

If an end-to-end write flow must be proven, design separate synthetic tests with isolated data and permissions; do not repeat it on business tables on every health poll.

### Refreshing Data Immediately When Seeing It Stale

Health calling `refresh()`, updating `lastSeen`, extending TTL, or populating a cache entry on miss causes observation to alter the evidence. The more frequently monitoring polls, the more artificially fresh data can appear or the more extra loads are triggered.

The component owning the data should refresh on its own lifecycle. Health reads the snapshot, last successful timestamp, and defined expiration criteria.

### Assuming a `readOnly` Annotation Is an Absolute Barrier

`@Transactional(readOnly = true)` is a hint to the transaction manager and corresponding optimizations; it is not a universal guarantee that every underlying layer will refuse writes. Nor does it stop an HTTP call, email send, or queue operation outside that transaction. See [Transactional's readOnly contract](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/transaction/annotation/Transactional.html#readOnly()).

To reduce accidental write risk, combine narrow read APIs, reviewed queries, appropriate resource permissions, and before/after state tests. Also, do not use a completely different admin account and treat that account's successful connection as proof the application's account still works.

## 8. Read-Only Can Still Be Very Expensive

A `SELECT COUNT(*)` over a large dataset, listing an entire bucket, or fetching every message to count can be read-only yet unsuitable for frequent health checks. Keep observations small and well-scoped instead of rebuilding business reports on every check.

Common causes of slow checks include:

- waiting to borrow a connection from a pool before starting the command;
- DNS, TLS handshakes, or re-authentication occurring too frequently;
- client timeouts set too high or missing;
- retrying multiple times within a single health call;
- lock contention inside the application or dependent service;
- unbounded read queries, large scans, or unnecessary payload deserialization.

Budgets must include resource wait times and retry counts, not only execution time of the final command. Lowering the warning threshold does not replace setting timeouts, bounding concurrency, and reducing read cost.

Do not create a new executor or client per request just to impose an outer timeout. When the wait expires, the underlying task may keep running, holding connections and accumulating load. Understand the real client's cancellation mechanism and manage shared resource lifecycles.

### Account for the Frequency of the Entire Monitoring System

For example, with 100 instances, each polled by two systems every 10 seconds, average observation load is roughly `100 × 2 / 10 = 20` requests/second. If one probe holds resources for roughly two seconds, concurrent waiting/active work can amount to roughly 40 probes in steady state before accounting for additional limits and queues.

This is an estimate showing how costs multiply, not a promise about exact thread counts. Bounded pools can turn that load into queuing latency. Synchronized bursts of requests create peaks even higher than the average.

## 9. Measure Enough to Find the Root Cause

Individual warnings help spot slow contributors, yet do not replace a latency distribution history. When long-term tracking is needed, you can use a Micrometer `Timer` around the check with a stable component name and a small tag set.

Illustrative snippet where `MeterRegistry registry` and `HealthIndicator indicator` are available:

```java
Timer timer = registry.timer("app.health.probe", "component", "workQueue");
return timer.record(indicator::health);
```

This snippet requires importing `io.micrometer.core.instrument.Timer` and is not a standalone program. The name `app.health.probe` is defined by the application; it is not a default Actuator metric automatically created for every indicator.

This wrapper measures the entire synchronous call passed into it, whereas `durationMs` in the example measures from inside the indicator. Do not attach customer IDs, job payloads, dynamic URLs, or exception messages as tags: they explode time-series cardinality and may contain sensitive data.

Compare probe duration against connection acquisition time, worker busyness, dependency latency, and HTTP latency. Raising thresholds or silencing loggers only hides the observation signal; it does not prove the root cause was addressed.

## 10. Verification Procedure Before Production Use

1. **Define the health question.** Checking connectivity, data freshness, or backlog are different questions; pick the smallest read that answers the required question.
2. **Trace the call path.** Follow from indicator through service, repository/client to the real API or statement. Do not stop at a method named `check()` or an annotation.
3. **Snapshot state before/after.** For queues, inspect depth, order, and delivery counts if present; for databases, inspect data and related side effects. In isolated tests, prevent other actors from changing data so causes can be attributed accurately.
4. **Call repeatedly and concurrently.** Ensure no jobs are dequeued, no data is written, and no state is refreshed merely due to observation. Watch both I/O call counts and connection counts.
5. **Introduce controlled latency.** Confirm warnings identify the right contributor, statuses still follow policy, and real timeouts fire at the required layer.
6. **Exercise failure paths.** Test exceptions, thread interruption, excessive backlog, and missing observation data; read-only behavior must hold on failure paths as well.
7. **Test the published path.** Call through Actuator when verifying Actuator warnings; test visibility permissions and HTTP status separately from direct indicator calls.

An `UP` result is not enough to judge a good health check. You must also prove it observes the right resource, completes at acceptable cost, detects slowness, and leaves business data untouched after every invocation.
