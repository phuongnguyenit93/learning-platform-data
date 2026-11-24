# Designing External Dependency Checks with Timeouts and Bounded Cost

## 1. A Health Check Also Consumes Resources

When a `HealthIndicator` calls a database, Redis, or an HTTP service, it becomes real work: it requires processing threads, connections, wait time, and resources on the checked system.

If an external dependency is slow, an unbounded check can tie up many threads of the application itself. If multiple monitors call simultaneously, checks can also pile load onto a service already experiencing an incident.

Therefore, the design must answer all of the following simultaneously:

- **What capability is being checked?** Being able to connect does not guarantee the required business operation can succeed.
- **How much time may it spend?** Including wait layers before and during request dispatch.
- **How many resources may it consume?** Call count, in-flight tasks, queues, connections, and payload size.
- **Until when is a result still fresh?** An old `UP` sample cannot be kept indefinitely.
- **When a check hangs, what keeps growing?** A good design must have a concrete answer.

This lesson uses **Spring Boot 3.3.0 and JDK 21** for Java examples. The timing numbers are illustrative configurations; actual budgets must be based on operational requirements and measurements of your application.

### 1.1. From "Ping an API" to a Check Contract

A contract can be described as follows:

```text
Dependency: catalog
Capability to verify: the service's readiness endpoint responds with HTTP 204
Single check: one HEAD request issued by application code
No retry loop at the check layer
Frequency: wait 2 seconds after the previous check finishes
Single-evaluation budget: 500 ms
Maximum age of a completed sample: 6 seconds
Concurrent in-flight checks at the application layer: at most 1 for this indicator
```

This contract only confirms the signal committed by that endpoint. It does not prove every catalog transaction succeeds. If read permission, write permission, or a mandatory dataset is a condition for serving, decide which lightweight check genuinely represents that condition.

Checks should avoid side effects: do not create orders, send emails, execute payments, or mutate business data just to determine health.

## 2. Separate the Types of Time Limits

### 2.1. Connect Timeout Does Not Cover the Entire Operation

A call can pass through many steps:

```text
Wait for resource/connection
    -> name resolution
    -> establish connection and security
    -> send request
    -> wait for response
    -> process body
    -> return connection and clean up resources
```

Each step may have its own wait mechanism. Read the client's contract to know which steps each timeout covers, whether it applies when reusing connections, and whether it includes reading the body.

With the JDK's `HttpClient`, `connectTimeout` applies when establishing a new connection; when reusing an existing connection, this limit has no effect on that step. [JDK 21 HttpClient.Builder API](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.Builder.html#connectTimeout(java.time.Duration))

Do not take a setting like `connectTimeout=150ms` and conclude the entire check will always finish within `150ms`.

### 2.2. Distinguish Per-Step Timeouts from an Overall Deadline

A **timeout** can be set for a single step. A **deadline** represents the point at which the overall work is no longer allowed to keep waiting under the caller's contract.

For instance, if the monitor only waits `1 second`, a synchronous design may allocate part of the budget to the external check and reserve the remainder for other contributors, aggregation, response serialization, and network transmission.

If three dependencies are checked sequentially, total time can add up. If checked in parallel, wait time may drop while concurrent connections and work increase. Bound both dimensions rather than optimizing only a single metric.

Timing dimensions that typically need verification:

| Dimension | Question to answer |
| --- | --- |
| Waiting for a connection from the pool | How long can it be held up before actually sending the request? |
| Connect/TLS | If a new connection fails or does not respond, how long does it wait? |
| Request/response wait | Under what condition does the client stop waiting? |
| Body read | Are total duration, size, and receive rate bounded? |
| Retries and backoff waits | Do all attempts share one budget or does each restart from zero? |
| Execution queue | Does time waiting for a thread count toward the measured duration? |

An idle-read timeout based on gaps without incoming bytes can still allow a slow trickle stream to drag on. Therefore, also verify an overall bound on the operation when reading response content.

### 2.3. Actuator's Warning Threshold Is Not a Timeout Enforcer

Spring Boot provides the property:

```properties
management.endpoint.health.logging.slow-indicator-threshold=1s
```

This is a threshold for **logging warnings about slow indicators**. It does not interrupt a socket, cancel a SQL statement, or force `health()` to return after one second. The 3.3 documentation describes the `10 second` default threshold and how to change the logging threshold. [Slow health indicators](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators)

Timeouts must be designed into the client and execution model of the check, independently of this observation threshold.

### 2.4. Stopping Waiting Differs from Stopping the Work

Setting a wait timeout when calling `Future.get` does not guarantee that the background work has stopped. Likewise, a future completing with a timeout error does not prove the underlying connection has been released.

Cancellation still depends on the client. With the JDK's `HttpClient`, when an operation is interrupted, the client attempts to cancel the HTTP exchange without guaranteeing when cancellation takes effect; the server may still have received the request and resources may be reclaimed asynchronously. [HttpClient cancellation contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html#send(java.net.http.HttpRequest,java.net.http.HttpResponse.BodyHandler))

A common design mistake is spawning a new task every time a wait expires while old tasks remain alive. When a dependency hangs, cost grows with the number of checks.

## 3. Bound Cost, Not Just Single-Call Latency

### 3.1. Estimating Total Load from Monitoring

Suppose:

- `N` application processes.
- `M` independent monitoring sources.
- Each source polls once every `P` seconds.
- Each health call triggers one check against the same dependency.

Approximate call rate at the application layer:

```text
R = N × M / P
```

With `200` processes, `3` monitoring sources, and a `5-second` interval:

```text
R = 200 × 3 / 5 = 120 checks/second
```

If each check retries up to three times on its own, a failure scenario can generate up to `360` attempts per second at that layer, before counting internal client or proxy retries.

Adjust this formula if there are additional direct queries to individual components or multiple checks inside one contributor. Do not look only at the refresh rate of a single dashboard.

### 3.2. Keep Checks Small and Meaningful

| Dependency | A lightweight check direction | What to avoid |
| --- | --- | --- |
| HTTP | Check endpoint with a clear contract, small response | Loading large pages or calling multi-step business flows |
| JDBC | Connection validity check or small targeted operation | Scanning large tables, locking data, heavy statistical queries |
| Redis | Lightweight command confirming the required capability | Reading the entire keyspace or large values |
| Rate-limited external service | Agreed-upon frequency | Letting every monitoring screen open consume a fresh call |

`HEAD` is useful when the endpoint supports it and has an appropriate contract: the client side does not need to download a body. However, the server may still perform work to handle `HEAD`. Do not infer "no body" means "zero server cost."

Do not automatically escalate from a failed lightweight check to a heavier check unless that escalation fits within the designed budget.

### 3.3. Three Execution Options

| Approach | Benefit | Cost paid |
| --- | --- | --- |
| Call directly in `health()` | Observes at request time | Health response path depends on external latency; call count scales with callers |
| Use cache, refresh on demand | Reduces calls when callers are few | Must control concurrent refreshes, waiting callers, and sample age |
| Periodic sampling on a dedicated thread | Decouples health read path from I/O; many readers share one sample | Still calls periodically even if nobody reads; results lag and need staleness policy |

No single option fits every application. For a cheap check, a client with reliable bounds, and few callers, synchronous execution may suffice. When there are many readers or a client that can get stuck, a sampling model controls impact more cleanly.

The next section implements the third option to make its boundaries explicit.

## 4. Sampling Model with a Periodic Task

```text
Dedicated sampling thread
    -> execute one check
    -> overwrite latest sample
    -> wait an interval after that run finishes
    -> execute next run

Every health() call
    -> read latest sample
    -> check sample age
    -> return Health
```

### 4.1. What the Model Guarantees Within the Sampler Scope

- `health()` makes no network calls, awaits no futures, and submits no additional tasks.
- Only one periodic task is registered per instance.
- The next run waits until the previous run finishes before counting the delay.
- A new sample overwrites the old sample; no history accumulates in memory.
- If no sample exists yet or the sample has expired, return `DOWN` per the example's policy.
- If a check gets stuck, this layer does not spawn replacement threads or queue another check for each health read.

`scheduleWithFixedDelay` measures the delay from when one execution completes to when the next begins. An exception escaping the periodic task can stop subsequent runs; the sample code handles normal check exceptions inside the task. [JDK 21 ScheduledExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html#scheduleWithFixedDelay(java.lang.Runnable,long,long,java.util.concurrent.TimeUnit))

The executor pool in the code is kept private with a single periodic task. It is not an open work queue for every caller.

### 4.2. Limits on Frequency and Freshness

With a delay `D` after each run and actual execution duration `T`, one process performs approximately:

```text
1 / (D + T) checks/second
```

This rate does not increase just because more health readers appear. This is the number of `Probe.check()` calls at the application layer, not a claim about all internal network exchanges by the client.

In return, the read status reflects a completed sample. If the latest sample is within the age limit, the example may keep returning `UP` during that window even while a new check is slow. Past the age limit, the stale sample is no longer treated as current health evidence.

### 4.3. Evaluation Budget Does Not Force-Stop Threads

**In the code below, `budget` is used to reject results that finish too late. It is not a timer that interrupts a hanging `Probe.check()`.**

If a check returns `true` after exceeding the budget, the sample is recorded as `DOWN/PROBE_BUDGET_EXCEEDED`. If it never returns, the health read path continues relying on the old sample and eventually reports an expired sample.

Real I/O limits must still be configured in the client. Isolating the health read path does not replace proper client configuration.

## 5. Complete Java Example Without External Dependencies

The example uses a simulated probe so results are repeatable, including a scenario that ignores interrupt requests. It does not send requests to a real service.

### 5.1. Files and Dependencies

```text
bounded-health-demo/
├── pom.xml
└── src/main/java/example/health/BoundedProbeDemo.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <groupId>example</groupId>
    <artifactId>bounded-health-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
</project>
```

`src/main/java/example/health/BoundedProbeDemo.java`:

```java
package example.health;

import java.io.IOException;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.LongSupplier;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.actuate.health.Status;

public class BoundedProbeDemo {
    @FunctionalInterface
    public interface Probe {
        boolean check() throws Exception;
    }

    public static final class SampledIndicator
            implements HealthIndicator, AutoCloseable {
        private record Sample(Health health, long completedAtNanos) {}

        private final String dependency;
        private final Probe probe;
        private final LongSupplier nanoTime;
        private final long delayNanos;
        private final long budgetNanos;
        private final long maxAgeNanos;
        private final AtomicReference<Sample> latest = new AtomicReference<>();
        private final AtomicBoolean closed = new AtomicBoolean();
        private final ScheduledThreadPoolExecutor scheduler;
        private boolean started;
        private ScheduledFuture<?> scheduled;

        public SampledIndicator(String dependency, Probe probe, Duration delay,
                Duration budget, Duration maxAge) {
            this(dependency, probe, delay, budget, maxAge, System::nanoTime);
        }

        private SampledIndicator(String dependency, Probe probe, Duration delay,
                Duration budget, Duration maxAge, LongSupplier nanoTime) {
            this.dependency = Objects.requireNonNull(dependency);
            this.probe = Objects.requireNonNull(probe);
            this.nanoTime = Objects.requireNonNull(nanoTime);
            this.delayNanos = positiveNanos(delay);
            this.budgetNanos = positiveNanos(budget);
            this.maxAgeNanos = positiveNanos(maxAge);
            if (maxAgeNanos <= Math.addExact(delayNanos, budgetNanos)) {
                throw new IllegalArgumentException("maxAge must exceed delay + budget");
            }
            this.scheduler = new ScheduledThreadPoolExecutor(1, task -> {
                Thread thread = new Thread(task, "health-sample-" + dependency);
                thread.setDaemon(true);
                return thread;
            });
            scheduler.setRemoveOnCancelPolicy(true);
        }

        private static long positiveNanos(Duration value) {
            long nanos = Objects.requireNonNull(value).toNanos();
            if (nanos <= 0) {
                throw new IllegalArgumentException("duration must be positive");
            }
            return nanos;
        }

        public synchronized void start() {
            if (closed.get()) {
                throw new IllegalStateException("indicator is closed");
            }
            if (!started) {
                scheduled = scheduler.scheduleWithFixedDelay(
                        this::refresh, 0, delayNanos, TimeUnit.NANOSECONDS);
                started = true;
            }
        }

        private Health result(Status status, String reason) {
            return Health.status(status)
                    .withDetail("dependency", dependency)
                    .withDetail("reason", reason).build();
        }

        private void refresh() {
            long began = nanoTime.getAsLong();
            Health value;
            try {
                value = probe.check()
                        ? result(Status.UP, "OK")
                        : result(Status.DOWN, "DEPENDENCY_REJECTED");
            }
            catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                value = result(Status.DOWN, "INTERRUPTED");
            }
            catch (Exception ex) {
                value = result(Status.DOWN, "PROBE_FAILED");
            }

            long completed = nanoTime.getAsLong();
            if (completed - began > budgetNanos) {
                value = result(Status.DOWN, "PROBE_BUDGET_EXCEEDED");
            }
            if (!closed.get()) {
                latest.set(new Sample(value, completed));
            }
        }

        @Override
        public Health health() {
            if (closed.get()) {
                return result(Status.DOWN, "STOPPED");
            }
            Sample sample = latest.get();
            if (sample == null) {
                return result(Status.DOWN, "NO_SAMPLE");
            }
            long age = Math.max(0, nanoTime.getAsLong() - sample.completedAtNanos());
            if (age > maxAgeNanos) {
                return Health.down()
                        .withDetail("dependency", dependency)
                        .withDetail("reason", "STALE_SAMPLE")
                        .withDetail("lastStatus", sample.health().getStatus().getCode())
                        .withDetail("sampleAgeMs",
                                TimeUnit.NANOSECONDS.toMillis(age)).build();
            }
            return Health.status(sample.health().getStatus())
                    .withDetails(sample.health().getDetails())
                    .withDetail("sampleAgeMs",
                            TimeUnit.NANOSECONDS.toMillis(age)).build();
        }

        @Override
        public synchronized void close() {
            if (closed.compareAndSet(false, true)) {
                if (scheduled != null) {
                    scheduled.cancel(true);
                }
                scheduler.shutdownNow();
            }
        }
    }

    private enum Mode { OK, REJECTED, ERROR, LATE }

    private static void print(String label, Health health) {
        System.out.println(label + "=" + health.getStatus().getCode()
                + "/" + health.getDetails().get("reason"));
    }

    public static void main(String[] args) throws Exception {
        AtomicLong clock = new AtomicLong();
        AtomicInteger calls = new AtomicInteger();
        AtomicReference<Mode> mode = new AtomicReference<>(Mode.OK);
        Probe probe = () -> {
            calls.incrementAndGet();
            return switch (mode.get()) {
                case OK -> true;
                case REJECTED -> false;
                case ERROR -> throw new IOException("simulated I/O error");
                case LATE -> {
                    clock.addAndGet(Duration.ofMillis(300).toNanos());
                    yield true;
                }
            };
        };

        SampledIndicator indicator = new SampledIndicator(
                "catalog", probe, Duration.ofSeconds(1),
                Duration.ofMillis(200), Duration.ofSeconds(3), clock::get);
        try {
            print("initial", indicator.health());
            indicator.refresh();
            print("fresh", indicator.health());
            for (int index = 0; index < 10_000; index++) {
                indicator.health();
            }
            System.out.println("probe-calls-after-10000-reads=" + calls.get());
            clock.addAndGet(Duration.ofSeconds(4).toNanos());
            print("expired", indicator.health());
            mode.set(Mode.REJECTED);
            indicator.refresh();
            print("rejected", indicator.health());
            mode.set(Mode.ERROR);
            indicator.refresh();
            print("exception", indicator.health());
            mode.set(Mode.LATE);
            indicator.refresh();
            print("late", indicator.health());
            mode.set(Mode.OK);
            indicator.refresh();
            print("recovered", indicator.health());
        }
        finally {
            indicator.close();
        }
        print("closed", indicator.health());

        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicInteger attempts = new AtomicInteger();
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximumActive = new AtomicInteger();
        Probe blockedProbe = () -> {
            attempts.incrementAndGet();
            int current = active.incrementAndGet();
            maximumActive.accumulateAndGet(current, Math::max);
            entered.countDown();
            try {
                boolean released = false;
                while (!released) {
                    try {
                        release.await();
                        released = true;
                    }
                    catch (InterruptedException ignored) {
                        // Deliberately simulate a client that ignores cancellation.
                    }
                }
                return true;
            }
            finally {
                active.decrementAndGet();
                exited.countDown();
            }
        };

        SampledIndicator blocked = new SampledIndicator(
                "catalog", blockedProbe, Duration.ofMillis(10),
                Duration.ofMillis(200), Duration.ofSeconds(3));
        try {
            blocked.start();
            if (!entered.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker did not enter probe");
            }
            blocked.start();
            for (int index = 0; index < 10_000; index++) {
                blocked.health();
            }
            print("while-blocked", blocked.health());
            System.out.println("blocked-attempts=" + attempts.get());
            System.out.println("max-concurrent-probes=" + maximumActive.get());
            blocked.close();
            print("closed-while-blocked", blocked.health());
        }
        finally {
            blocked.close();
            release.countDown();
            if (!exited.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("demo worker did not exit");
            }
        }
    }
}
```

### 5.2. Compiling and Running

In the directory containing `pom.xml`, with Maven and JDK 21, run in PowerShell:

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
$boundedProbeClasspath = (Get-Content -Raw -LiteralPath classpath.txt).Trim()
javac --release 21 -encoding UTF-8 -cp $boundedProbeClasspath -d out src/main/java/example/health/BoundedProbeDemo.java
java -cp "$boundedProbeClasspath;out" example.health.BoundedProbeDemo
```

On Linux/macOS, use `:` as the classpath separator and the corresponding shell syntax.

Stdout lines from the program:

```text
initial=DOWN/NO_SAMPLE
fresh=UP/OK
probe-calls-after-10000-reads=1
expired=DOWN/STALE_SAMPLE
rejected=DOWN/DEPENDENCY_REJECTED
exception=DOWN/PROBE_FAILED
late=DOWN/PROBE_BUDGET_EXCEEDED
recovered=UP/OK
closed=DOWN/STOPPED
while-blocked=DOWN/NO_SAMPLE
blocked-attempts=1
max-concurrent-probes=1
closed-while-blocked=DOWN/STOPPED
```

Environment or library logs, if any, do not belong to the output lines above.

### 5.3. Verified Scenarios

| Output | What was verified |
| --- | --- |
| `initial=DOWN/NO_SAMPLE` | Missing sample is not implicitly treated as healthy |
| `fresh=UP/OK` | Fresh successful sample is used |
| `probe-calls-after-10000-reads=1` | Repeated health reads do not re-invoke the dependency |
| `expired=DOWN/STALE_SAMPLE` | Old successful sample is not kept green indefinitely |
| `rejected=DOWN/DEPENDENCY_REJECTED` | Dependency returned a result failing the contract |
| `exception=DOWN/PROBE_FAILED` | Ordinary exception is converted into a health result |
| `late=DOWN/PROBE_BUDGET_EXCEEDED` | Success returned too late is not accepted as `UP` |
| `recovered=UP/OK` | New successful sample can replace a failure result |
| `blocked-attempts=1` | Readers do not trigger extra attempts while a check is stuck |
| `max-concurrent-probes=1` | Only one check runs at a time in the sampler |
| `closed-while-blocked=DOWN/STOPPED` | Stopping the indicator does not wait for the simulated client to honor interrupt |

Sample age and late-result checks use a simulated clock rather than sleeping and measuring jitter-prone milliseconds. In real runs, the public constructor uses `System.nanoTime` to measure elapsed intervals.

The `refresh()` method is an internal detail. `main` calls it directly during policy checks because it sits inside the outer enclosing class; normal usage calls `start()` once and lets the periodic schedule execute.

### 5.4. Reading the Code's Boundaries Accurately

`maxAge` is validated to exceed `delay + budget` to prevent an obviously misconfigured setup that leaves insufficient time between samples under the expected budget. In production, headroom is also needed for scheduling jitter, client overhead, and system load.

Samples are aged from when the check finishes. Results exceeding the budget are recorded as failures; a fresh timestamp does not turn a slow check into a success.

`close()` cancels the schedule and requests thread interruption, without waiting indefinitely via `awaitTermination`. A daemon thread keeps it from keeping the JVM alive when the process exits; daemon status does not mean external sockets or work have been canceled.

In the blocked test, the simulated client deliberately ignores interrupts. The program releases it only during test cleanup. Do not put that interrupt-ignoring behavior into production clients.

## 6. Attaching a Timeout-Configured HTTP Client to a Spring Boot Application

After having the `SampledIndicator` type in section 5, the following configuration illustrates how to register it with a real HTTP check in an application that already includes Actuator.

Save `CatalogHealthConfiguration.java` in package `example.health`:

```java
package example.health;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import example.health.BoundedProbeDemo.SampledIndicator;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogHealthConfiguration {
    @Bean(name = "catalogProbeClient", destroyMethod = "shutdownNow")
    public HttpClient catalogProbeClient() {
        return HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(150))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Bean(destroyMethod = "close")
    public SampledIndicator catalogHealthIndicator(
            @Qualifier("catalogProbeClient") HttpClient client,
            @Value("${demo.health.catalog.url}") URI target) {
        HttpRequest request = HttpRequest.newBuilder(target)
                .timeout(Duration.ofMillis(400))
                .method("HEAD", HttpRequest.BodyPublishers.noBody())
                .build();
        SampledIndicator indicator = new SampledIndicator(
                "catalog",
                () -> client.send(request,
                        HttpResponse.BodyHandlers.discarding()).statusCode() == 204,
                Duration.ofSeconds(2), Duration.ofMillis(500),
                Duration.ofSeconds(6));
        indicator.start();
        return indicator;
    }
}
```

In the sample code, the type is imported from the outer enclosing class for immediate use with the file in section 5. When structuring application code, you can extract `Probe` and `SampledIndicator` into separate classes and adjust imports accordingly.

Configure the target address:

```properties
demo.health.catalog.url=${CATALOG_HEALTH_URL}
```

The `CATALOG_HEALTH_URL` environment variable must point to an endpoint managed in application configuration and permitted to be called. Do not take the check URL from a health caller's parameters.

### 6.1. Contract of the HTTP Request

The example expects the endpoint to:

- Support `HEAD`.
- Return `204` when the checked condition is met.
- Perform no heavy work or side effects per call.

`200`, `301`, `401`, `405`, `429`, or `503` all fail to match the example's `204` contract. That does not mean every service must use `204`; adjust the policy to match the real contract.

`followRedirects(NEVER)` prevents automatically following redirect chains. The code has no retry loop at the check layer. Still verify internal retry behavior of the client, proxies, and infrastructure if network exchange counts must be bounded.

`BodyHandlers.discarding()` avoids accumulating response content into a large string. It is not a byte-limit enforcer for an arbitrary `GET` request. In this sample, `HEAD` is part of the contract so no body needs to be received; if switching to `GET`, redesign read limits and response size limits.

### 6.2. Timing Values Serve Different Roles

| Value in Java configuration | Role |
| --- | --- |
| `150ms` on `connectTimeout` | New-connection establishment limit per client contract |
| `400ms` on request `timeout` | Request timeout per JDK API |
| `500ms` on `SampledIndicator` | Results finishing past this threshold are marked over-budget |
| `2s` delay | Wait interval after one check finishes |
| `6s` maxAge | Maximum age of a sample still considered usable |

`HttpRequest.Builder.timeout` sets the request timeout and throws `HttpTimeoutException` when no response arrives within the limit per the API contract. Omitting a timeout amounts to leaving that layer unbounded. [HttpRequest.Builder.timeout](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html#timeout(java.time.Duration))

Do not sum `150 + 400` or take the largest number and treat it as absolute proof of total elapsed time: timer scopes can overlap, and other processing steps must be verified on the real client/JDK.

The `500ms` budget does not interrupt a hanging network call. It only rejects acknowledging late results; the health read path is protected by separating I/O from `health()` and checking sample age.

### 6.3. Reusing the Client and Stopping Intentionally

The client is a bean shared for the indicator rather than recreated per health read. Reusing the client enables reusing connection resources.

The configuration explicitly specifies `destroyMethod="shutdownNow"` for the JDK 21 `HttpClient`. This method requests a best-effort stop of the client; it does not guarantee all in-flight operations have ended. `HttpClient.close()` has a contract to wait for operations to complete, so it cannot be assumed to always return immediately during cleanup. [JDK 21 HttpClient lifecycle](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html#shutdownNow())

The periodic thread and the client are two separate resource layers. Bounding a check at the application layer does not automatically prove all internal threads, connections, or buffers of the library share the same bounds; inspect and configure those resources separately.

## 7. Decisions to Add for Real-World Use

### 7.1. Sample Age, Initial Policy, and Recovery Status

The example chooses `DOWN` for missing sample, stale sample, and stopped state. This choice suits a signal requiring fresh evidence before being considered ready.

Do not change it to `UNKNOWN` just to make HTTP status codes look nicer: under default mappings, `UNKNOWN` can still receive HTTP `200`. If choosing another status, define both aggregation behavior and the HTTP code the monitoring system will use.

Nor should you return an expired `UP` sample with merely `stale=true` added in details. Many health consumers only inspect status or HTTP code and do not read detail flags.

If the application has a fallback serving mechanism when a dependency fails, a different status or monitoring group may be warranted. Decisions must rest on actual serving capability, not merely on whether the client connected.

### 7.2. Liveness and Readiness Have Different Goals

An external dependency failure does not necessarily prove the application process needs to be restarted. Putting every external service into liveness can cause repeated restarts while a shared outage remains unresolved.

Readiness may need to consider dependencies genuinely required to accept traffic, yet including or excluding one from the group must be decided according to the application's serving contract and fallback capability. [Guide to checking external state with Kubernetes probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.external-state)

The indicator in this lesson only provides a signal; group selection is not inferred automatically from the name `catalog`.

### 7.3. JDBC Needs Multiple Independent Bounds

For a database, consider at least:

- Time to acquire a connection from the pool.
- Time to validate the connection or execute the check query.
- Network wait timeout at the driver level.
- Closing/returning resources and impact on business work.

`Connection.isValid(timeout)` verifies connection validity via the driver's mechanism. It does not cover acquiring a connection from the pool beforehand.

`setNetworkTimeout` and query timeouts are separate mechanisms with separate effects on the connection upon expiration. A driver may perform multiple round-trips inside a single API call; verify the actual timeout scope. [JDK 21 JDBC Connection API](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html#isValid(int))

Avoid holding health connections long enough to starve business traffic. Creating a dedicated connection pool also carries cost; do so only when the design accounts for additional connections and database-side access limits.

### 7.4. Controlling Retries, Queues, and Indicator Count

Health is naturally polled repeatedly. Retrying multiple times inside every single check can amplify load right when a dependency is failing.

For example, three attempts, each waiting `400ms`, with two `100ms` backoff intervals:

```text
3 × 400ms + 2 × 100ms = 1400ms
```

The figure already exceeds `1 second` even though each individual timeout looked small. If retries are needed, all attempts must fit within the allocated budget with explicit limits on attempt count, backoff, and resources.

The sample code creates one periodic thread per indicator. If hundreds of indicators like this are created, total thread count grows too. When a shared scheduler is needed, redesign concurrency limits and slow-dependency isolation; do not simply switch to a single unbounded shared queue.

Virtual threads can reduce the cost of certain blocking waits, yet they do not automatically bound connection counts, remote request rates, or service-side resources.

### 7.5. Staggering Sampling Schedules Across Processes

The sample code starts immediately so tests are easy to reproduce. When many processes start together, they may check the same target at nearly identical times.

Finite random jitter can be added to the start time or check schedule while maintaining frequency and freshness bounds. Factor the initial pre-sample window and that jitter range into `maxAge`.

Periodic sampling can generate more calls than an on-demand model if almost nobody reads health. Pick the interval from load budgets and fault-detection requirements rather than assuming "the more frequent, the better" by default.

### 7.6. Detail Data and Observability

The sample code returns only the logical dependency name, reason code, and sample age. It does not put exception messages, HTTP bodies, URLs with sensitive parameters, or stack traces into health.

In operations, observe separately:

| Metric | What it can detect |
| --- | --- |
| Check execution duration | Client starting to slow down before samples expire |
| Latest sample age and last success timestamp | Schedule stopped running or check got stuck |
| Started/completed check counts | Work not finishing as expected |
| Error/over-budget result counts | Connection failures, response contract mismatches, or overly tight limits |
| Client and connection resources | Cost beneath the indicator layer |
| Call rate per logical dependency | Whether cluster-wide load exceeds budget |

`health()` in this design runs fast even when background I/O hangs. Thus Actuator's slow-indicator log does not replace measuring execution time and sample age on the sampling thread.

Keep metric labels within a bounded set of values. Do not use arbitrary URLs, continuously changing error messages, or user IDs as labels. Nor should you log a fresh stack trace on every repeat read of the same failure sample.

## 8. Boundaries to Read Accurately

The design protects **this indicator's read path** from waiting on the network. It does not guarantee all of `/actuator/health` returns quickly if other contributors still perform unbounded I/O.

Nor is it an absolute real-time guarantee: OS scheduling, garbage collection, and process resources still affect latency. The verifiable benefit is that the read path does not depend on whether the remote client returns.

If a client cannot exit I/O, the code does not spawn a new thread to replace the old one on every timeout. It retains one stuck task and lets the signal expire. This is an intentional bound on growth alongside surfacing the incident.

When a non-cooperative piece of work must be reliably reclaimed, handle it in the client/driver or an isolation boundary capable of terminating that work. Requesting thread interruption, marking it daemon, or attaching another future does not create that guarantee.

## 9. Verifying Before Putting a Check Into Production

Key test scenarios should include:

| Scenario | Evidence required |
| --- | --- |
| Fast dependency success | Correct status and one check has known cost |
| Non-contract status code | Not misidentified as healthy |
| Immediate connection refusal | Not confused with silent unresponsiveness |
| Slow or unresponsive target | Health read path still behaves per the chosen model |
| Name resolution, TLS, connection wait | Actual timeouts cover the necessary steps |
| Large or trickling response | Does not load/buffer unbounded data |
| Many concurrent callers | Task and connection counts do not grow with every read |
| Sample past maximum age | Stale `UP` is no longer used as current status |
| Dependency recovery | A fresh sample replaces the failure status |
| Application shutdown while I/O stuck | Cleanup obeys actual bounds and cancellation contract |
| Multiple processes | Cluster-wide rate and post-startup load spike stay within budget |

The program in section 5 verifies the sampling policy and task bounds using a simulated dependency. It is not proof that a real HTTP/JDBC client passes every network scenario in the table; test further with your actual client, driver, and deployment environment.

## 10. Self-Check Practice

1. Write a contract for a real dependency: capability to check, minimal operation, expected code/result, per-layer timeouts, frequency, maximum sample age, and concurrency limit.
2. Compute total call rate with `50` processes, `4` monitoring sources, and a `10-second` interval. Then compare against per-process sampling with a `5-second` delay, excluding execution time.
3. In the sample program, advance the simulated clock past `maxAge` without producing a new sample. Explain why an old successful result is not kept returning `UP`.
4. Have the check return `true` after exceeding `budget`. Distinguish the `PROBE_BUDGET_EXCEEDED` result from actually stopping I/O on time.
5. Call `health()` multiple times while the check is blocked. Inspect dependency call counts, not only a single caller's latency.
6. Pick an HTTP endpoint that only supports `GET`. Design response read limits and payload size limits before replacing `HEAD` in the sample.

A bounded check must clearly show **what is being measured, how long it may wait, how much concurrent work exists, and until when health evidence remains fresh**. Those four answers let monitoring observe an incident without amplifying it further.
