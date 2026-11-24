# Handling Exceptions and Degraded Status in Health Checks

## 1. What Does a Check Exception Indicate?

When a health check encounters an error, you must distinguish **the checked component being unusable** from **not being able to complete the check itself**. A refused connection, an exceeded timeout, a misconfiguration, and an interrupted thread are not the same event. Turning all of them into `UP` hides failures; turning all of them into "the entire application is dead" can unnecessarily sacrifice remaining serving capacity.

For example, a store uses an external product recommendation service. When that service fails, the store can still display a pre-prepared popular items list. Personalized recommendations are degraded, yet the storefront still operates. Conversely, if both the primary service and the fallback data are unusable, we no longer have evidence that the feature can still serve.

This lesson uses **Java 21 and Spring Boot 3.3.0** to build the following policy:

- `UP`: the primary-path check succeeds.
- `DEGRADED`: the primary path encounters a handleable failure, yet the fallback path is genuinely ready according to the application's contract.
- `DOWN`: neither path meets requirements, or the check encounters an error under which safe serving cannot be concluded.

`DEGRADED` is a custom status in the example, **not a built-in status that Actuator understands automatically**. Both its aggregation order and its HTTP status code must be configured.

## 2. Three Decision Layers to Keep Separate

```text
Check result or exception
    → Health of a component
    → aggregate status of the health endpoint or group
    → published HTTP status code
```

| Decision layer | Question to answer |
| --- | --- |
| Indicator | What does this failure mean for the component's ability to serve? |
| `StatusAggregator` | When multiple components have different statuses, which status represents the aggregate result? |
| `HttpCodeStatusMapper` | Which HTTP status code represents the final status? |

An indicator may return `DEGRADED` properly, yet the aggregate endpoint still returns `UP` if the aggregator does not know the new status. Conversely, JSON may contain the right status, yet a tool that only inspects HTTP codes may miss the degradation signal if the policy returns `200`.

Details such as `reason=DEPENDENCY_TIMEOUT` aid diagnostics; the `reason` string itself does not participate in severity ordering. It is the `status` field that feeds into the aggregation mechanism.

## 3. Default Exception Handling and Its Limits

### Implementing `HealthIndicator` Directly

If implementing `HealthIndicator.health()` directly, the application must decide how to handle errors itself. The interface does not automatically wrap the call in a `try/catch` to convert every exception into `DOWN`. You should not rely on an outer HTTP layer to turn an escaped exception into a structured health response.

### Extending `AbstractHealthIndicator`

`AbstractHealthIndicator` creates a `Health.Builder` for each invocation, runs `doHealthCheck(...)`, catches any escaping `Exception`, and produces `DOWN` via `builder.down(ex)`. It also logs a warning when the result retains an exception. This mechanism fits when an escaping exception genuinely ought to be interpreted as `DOWN`. See [Spring Boot 3.3.0 AbstractHealthIndicator source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/AbstractHealthIndicator.java).

The superclass does not decide for the application whether a fallback path is adequate. Nor does it:

- set a timeout or interrupt a hanging call automatically;
- restore the thread's interrupt flag when catching `InterruptedException`;
- understand a new status like `DEGRADED` automatically;
- guarantee that the exception message is safe to expose.

`Exception` and `Error` are different. Do not use `catch (Throwable)` merely to always produce a health JSON payload: severe errors such as `OutOfMemoryError` should not be turned into a normal check that was handled cleanly.

In the example below, we implement `HealthIndicator` directly to classify errors, preserve the interrupt flag, and return only curated reason codes.

## 4. Defining Degraded Status Based on Serving Capability

A degraded status requires clear evidence. "An exception was caught" is not evidence that the application can still serve.

| Scenario | Example's status | Rationale |
| --- | --- | --- |
| Primary path check succeeds | `UP` | Fallback path is not needed yet. |
| I/O error or timeout on primary path; fallback ready | `DEGRADED` | Still able to serve under an accepted fallback mechanism. |
| I/O error or timeout; fallback not ready | `DOWN` | No verified serving path remains. |
| Invalid check configuration | `DOWN` | Configuration must be fixed; do not treat as an ordinary transient connection glitch. |
| Fallback check itself throws an error | `DOWN` | Cannot confirm that fallback is still operational. |
| Thread interrupted | `DOWN` | Check was interrupted; preserve the interrupt signal for outer code. |
| Exception outside recognized types | `DOWN` | Insufficient basis to declare the component is serving. |

This is **the policy for the recommendation component in this lesson**. Do not apply it mechanically to mandatory functions such as payment confirmation. For a function without a valid fallback path, a primary-path failure may have to result directly in `DOWN`.

In a real system, the "fallback ready" signal must reflect the actual fallback data or mechanism in use: data is present, not expired, validated, and satisfies the committed portion of functionality. A configuration flag set to `true` does not prove all of those things.

## 5. Complete Example: Classifying Exceptions and Returning Health Safely

Create a standalone Maven project. File `pom.xml`:

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
    <artifactId>health-failure-demo</artifactId>
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

### 5.1. Indicator

File `src/main/java/learning/healthfailure/RecommendationHealthIndicator.java`:

```java
package learning.healthfailure;

import java.io.IOException;
import java.net.SocketTimeoutException;
import java.net.http.HttpTimeoutException;
import java.util.Objects;
import java.util.concurrent.TimeoutException;
import java.util.function.BooleanSupplier;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.actuate.health.Status;

public final class RecommendationHealthIndicator implements HealthIndicator {

    public static final Status DEGRADED = new Status("DEGRADED");

    @FunctionalInterface
    public interface Probe {
        void verify() throws Exception;
    }

    public static final class ProbeMisconfiguredException extends Exception {
        public ProbeMisconfiguredException(String message) {
            super(message);
        }
    }

    private final Probe primary;
    private final BooleanSupplier fallbackReady;

    public RecommendationHealthIndicator(Probe primary, BooleanSupplier fallbackReady) {
        this.primary = Objects.requireNonNull(primary, "primary");
        this.fallbackReady = Objects.requireNonNull(fallbackReady, "fallbackReady");
    }

    @Override
    public Health health() {
        try {
            primary.verify();
            return result(Status.UP, "PRIMARY_READY", "NOT_NEEDED");
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return result(Status.DOWN, "CHECK_INTERRUPTED", "NOT_CHECKED");
        }
        catch (ProbeMisconfiguredException ex) {
            return result(Status.DOWN, "PROBE_MISCONFIGURED", "NOT_CHECKED");
        }
        catch (HttpTimeoutException | SocketTimeoutException | TimeoutException ex) {
            return afterPrimaryFailure("DEPENDENCY_TIMEOUT");
        }
        catch (IOException ex) {
            return afterPrimaryFailure("DEPENDENCY_IO_FAILURE");
        }
        catch (Exception ex) {
            return result(Status.DOWN, "UNEXPECTED_CHECK_FAILURE", "NOT_CHECKED");
        }
    }

    private Health afterPrimaryFailure(String reason) {
        try {
            return fallbackReady.getAsBoolean()
                    ? result(DEGRADED, reason, "READY")
                    : result(Status.DOWN, reason, "NOT_READY");
        }
        catch (RuntimeException ex) {
            return result(Status.DOWN, "FALLBACK_CHECK_FAILED", "UNKNOWN");
        }
    }

    private static Health result(Status status, String reason, String fallback) {
        return Health.status(status)
                .withDetail("reason", reason)
                .withDetail("fallback", fallback)
                .build();
    }
}
```

### 5.2. Why Are the Branches Written This Way?

**Catch timeout before IOException.** `HttpTimeoutException` and `SocketTimeoutException` belong to the `IOException` hierarchy, whereas `java.util.concurrent.TimeoutException` is a separate checked exception. If `IOException` were caught first, specific timeout classification would no longer work as designed; Java also forbids placing a catch branch for a subclass after a branch that already catches its superclass. Compare [HttpTimeoutException](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpTimeoutException.html) and [TimeoutException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/TimeoutException.html).

**Restore the interrupt flag.** After catching `InterruptedException` and not rethrowing it, the example calls `Thread.currentThread().interrupt()` to preserve the signal for the calling layer. It does not retry, does not perform additional fallback checks, and does not treat interruption as proof that the external resource is broken. See [InterruptedException contract in Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InterruptedException.html).

**Misconfiguration has its own branch.** `ProbeMisconfiguredException` is a contract defined by the example. A real adapter can throw it when determining that the check's configuration is invalid. Do not assume all HTTP `4xx` responses or all library exceptions belong to the same category; understand the protocol and client before mapping them.

**Errors while checking fallback must also be handled.** An exception thrown inside a `catch` block does not automatically transfer to sibling `catch` blocks of the same `try`. Therefore, `afterPrimaryFailure` handles errors from `BooleanSupplier` separately instead of letting a fallback error escape `health()`.

**Do not expose exception messages.** The branches only produce `reason` and `fallback` from curated value sets. They do not call `withDetail("error", ex.getMessage())`, and do not attach tokens, internal URLs, or exception objects to the result. The example code does not implement a logging system; a real application still needs internal diagnostics with access control and rate limiting.

**No retries inside the indicator.** One health call probes the primary path once and reads the fallback signal only when needed. Recovery mechanisms, data reloading, or invoking actual business fallback logic belong to the component owning the feature, not inside this observation check.

## 6. Running Checks Without Network Services

File `src/main/java/learning/healthfailure/HealthFailureDemo.java`:

```java
package learning.healthfailure;

import java.io.IOException;
import java.net.http.HttpTimeoutException;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BooleanSupplier;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.SimpleHttpCodeStatusMapper;
import org.springframework.boot.actuate.health.SimpleStatusAggregator;
import org.springframework.boot.actuate.health.Status;

import learning.healthfailure.RecommendationHealthIndicator.Probe;
import learning.healthfailure.RecommendationHealthIndicator.ProbeMisconfiguredException;

public class HealthFailureDemo {

    public static void main(String[] args) {
        check("primary", () -> {}, () -> true, Status.UP, "PRIMARY_READY");
        check("ioWithFallback", () -> { throw new IOException("internal IO diagnostic"); },
                () -> true, RecommendationHealthIndicator.DEGRADED, "DEPENDENCY_IO_FAILURE");
        check("timeoutWithFallback", () -> { throw new TimeoutException("internal timeout"); },
                () -> true, RecommendationHealthIndicator.DEGRADED, "DEPENDENCY_TIMEOUT");
        check("httpTimeoutWithFallback", () -> { throw new HttpTimeoutException("internal timeout"); },
                () -> true, RecommendationHealthIndicator.DEGRADED, "DEPENDENCY_TIMEOUT");
        check("noFallback", () -> { throw new IOException("internal IO diagnostic"); },
                () -> false, Status.DOWN, "DEPENDENCY_IO_FAILURE");
        check("misconfigured", () -> { throw new ProbeMisconfiguredException("internal config"); },
                () -> true, Status.DOWN, "PROBE_MISCONFIGURED");
        check("unexpected", () -> { throw new IllegalStateException("internal bug"); },
                () -> true, Status.DOWN, "UNEXPECTED_CHECK_FAILURE");
        check("fallbackFailure", () -> { throw new IOException("internal IO diagnostic"); },
                () -> { throw new IllegalStateException("internal fallback bug"); },
                Status.DOWN, "FALLBACK_CHECK_FAILED");

        try {
            check("interrupted", () -> { throw new InterruptedException("test interruption"); },
                    () -> true, Status.DOWN, "CHECK_INTERRUPTED");
            if (!Thread.currentThread().isInterrupted()) {
                throw new AssertionError("Interrupt flag was lost");
            }
            System.out.println("interruptFlag=true");
        }
        finally {
            Thread.interrupted();
        }

        Set<Status> statuses = Set.of(Status.UP, RecommendationHealthIndicator.DEGRADED);
        Status defaultAggregate = new SimpleStatusAggregator().getAggregateStatus(statuses);
        Status configuredAggregate = new SimpleStatusAggregator(
                "DOWN", "OUT_OF_SERVICE", "DEGRADED", "UP", "UNKNOWN").getAggregateStatus(statuses);
        if (!Status.UP.equals(defaultAggregate)
                || !RecommendationHealthIndicator.DEGRADED.equals(configuredAggregate)) {
            throw new AssertionError("Unexpected aggregation");
        }

        var mapper = new SimpleHttpCodeStatusMapper(Map.of(
                "DOWN", 503, "OUT_OF_SERVICE", 503, "DEGRADED", 200));
        int code = mapper.getStatusCode(configuredAggregate);
        if (code != 200 || mapper.getStatusCode(Status.DOWN) != 503) {
            throw new AssertionError("Unexpected HTTP mapping");
        }
        System.out.println("defaultAggregate=" + defaultAggregate.getCode());
        System.out.println("configuredAggregate=" + configuredAggregate.getCode());
        System.out.println("configuredHttp=" + code);
    }

    private static void check(String name, Probe primary, BooleanSupplier fallback,
            Status expected, String expectedReason) {
        AtomicInteger calls = new AtomicInteger();
        Probe counted = () -> {
            calls.incrementAndGet();
            primary.verify();
        };
        Health result = new RecommendationHealthIndicator(counted, fallback).health();
        if (!expected.equals(result.getStatus())
                || !expectedReason.equals(result.getDetails().get("reason"))
                || calls.get() != 1
                || result.getDetails().containsKey("error")) {
            throw new AssertionError("Unexpected result for " + name + ": " + result);
        }
        System.out.println(name + "=" + result.getStatus().getCode() + " (" + expectedReason + ")");
    }
}
```

This is a complete runnable program. The lambdas intentionally throw exceptions to verify the policy; they do not perform I/O and do not simulate actual wait times. Hence, the test does not depend on whether an external server is running.

In the directory containing `pom.xml`, confirm Maven uses JDK 21, then compile and build the classpath:

```shell
mvn -version
mvn compile dependency:build-classpath "-Dmdep.outputFile=target/classpath.txt"
```

Run on PowerShell:

```powershell
$dependencyClasspath = (Get-Content -Raw -LiteralPath 'target/classpath.txt').Trim()
java -cp "target/classes;$dependencyClasspath" learning.healthfailure.HealthFailureDemo
```

Or run on Linux/macOS:

```shell
java -cp "target/classes:$(cat target/classpath.txt)" learning.healthfailure.HealthFailureDemo
```

Maven compiled the Java files along with dependencies. Do not run `javac RecommendationHealthIndicator.java` standalone without providing the Actuator classpath.

The exact stdout of the program is:

```text
primary=UP (PRIMARY_READY)
ioWithFallback=DEGRADED (DEPENDENCY_IO_FAILURE)
timeoutWithFallback=DEGRADED (DEPENDENCY_TIMEOUT)
httpTimeoutWithFallback=DEGRADED (DEPENDENCY_TIMEOUT)
noFallback=DOWN (DEPENDENCY_IO_FAILURE)
misconfigured=DOWN (PROBE_MISCONFIGURED)
unexpected=DOWN (UNEXPECTED_CHECK_FAILURE)
fallbackFailure=DOWN (FALLBACK_CHECK_FAILED)
interrupted=DOWN (CHECK_INTERRUPTED)
interruptFlag=true
defaultAggregate=UP
configuredAggregate=DEGRADED
configuredHttp=200
```

`Thread.interrupted()` inside `finally` only clears the signal of **the main thread owned by the check program**, after verifying that the flag was preserved. It is not an instruction for indicator code to clear the interrupt flag of a request-serving thread. Inside the indicator, the flag is still restored with `interrupt()`.

## 7. Why Can `DEGRADED` Disappear from the Aggregate Result?

The default `SimpleStatusAggregator` only ranks its well-known statuses. Given the set `{UP, DEGRADED}` when `DEGRADED` is not yet in the ordering, the default result can be `UP`; if no status is recognized, the result is `UNKNOWN`. One cannot infer that a new status automatically sits between `UP` and `DOWN` merely from the English meaning of that name. See [SimpleStatusAggregator source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.java).

To use the policy in this lesson, configure the ordering from most severe to least severe:

```properties
management.endpoint.health.status.order=down,out-of-service,degraded,up,unknown
```

Then:

| Component statuses | Aggregate result under the order above |
| --- | --- |
| `UP`, `DEGRADED` | `DEGRADED` |
| `DOWN`, `DEGRADED` | `DOWN` |
| `OUT_OF_SERVICE`, `DEGRADED` | `OUT_OF_SERVICE` |

This is not majority voting. Ten `UP` indicators do not override a single `DOWN` indicator when `DOWN` comes earlier in the order.

Do not add a custom status in one module and forget the consumers reading that status: monitoring tools, health groups, probes, and dashboards may hold different assumptions. A health group with its own policy must also be tested separately rather than inferred by default from the aggregate endpoint.

## 8. HTTP Mapping Must Reflect the Real Operational Decision

The example chooses **HTTP 200 for DEGRADED** because the fallback path still satisfies an acceptable portion of functionality. A monitoring tool that wants to alert on degradation must read the JSON or have a separate signal; checking only "did HTTP succeed" will not detect reduced functional quality.

```properties
management.endpoint.health.status.http-mapping.down=503
management.endpoint.health.status.http-mapping.out-of-service=503
management.endpoint.health.status.http-mapping.degraded=200
```

Keep both the `down` and `out-of-service` lines. In Spring Boot 3.3, when configuring custom mappings, the default mappings for those two statuses are not automatically preserved. Adding only `degraded=200` can cause the remaining failure statuses to fall back to the default `200` code if they are not re-declared. Cross-check [health endpoint status mapping rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators).

If an endpoint's requirement is "when degraded, stop receiving additional traffic," you can choose `degraded=503` for the endpoint or group designed for that purpose. This decision should not be applied indiscriminately to every check: taking a host out of traffic should aid system recovery, not trigger a cascading outage because an optional service temporarily failed.

`UNKNOWN` is not by default an HTTP failure either. Under default mappings, it does not automatically become `503`. If lack of evidence must stop the system from accepting work, express that with explicit status and HTTP policies.

## 9. Observing the Same Policy in a Spring Boot Application

File `src/main/java/learning/healthfailure/HealthFailureApplication.java`:

```java
package learning.healthfailure;

import java.io.IOException;
import java.util.concurrent.TimeoutException;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import learning.healthfailure.RecommendationHealthIndicator.Probe;
import learning.healthfailure.RecommendationHealthIndicator.ProbeMisconfiguredException;

@SpringBootApplication
public class HealthFailureApplication {

    public static void main(String[] args) {
        SpringApplication.run(HealthFailureApplication.class, args);
    }

    @Bean
    RecommendationHealthIndicator recommendationHealthIndicator(
            @Value("${demo.primary:io}") String mode,
            @Value("${demo.fallback-ready:true}") boolean fallbackReady) {
        Probe probe = switch (mode) {
            case "up" -> () -> {};
            case "io" -> () -> { throw new IOException("simulated IO failure"); };
            case "timeout" -> () -> { throw new TimeoutException("simulated timeout"); };
            case "misconfigured" -> () -> {
                throw new ProbeMisconfiguredException("simulated invalid probe configuration");
            };
            default -> throw new IllegalArgumentException("Unsupported demo mode");
        };
        return new RecommendationHealthIndicator(probe, () -> fallbackReady);
    }
}
```

File `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health
management.endpoint.health.show-components=always
management.endpoint.health.show-details=always
management.endpoint.health.status.order=down,out-of-service,degraded,up,unknown
management.endpoint.health.status.http-mapping.down=503
management.endpoint.health.status.http-mapping.out-of-service=503
management.endpoint.health.status.http-mapping.degraded=200
```

The `demo.*` values only create learning scenarios; they do not implement a real recommendation service or fallback mechanism. When integrating for real, replace the simulated signal sources with properly scoped checks and fallback evidence. An indicator does not create fallback capability simply because it can return `DEGRADED`.

The bean name is `recommendationHealthIndicator`, so the default contributor name is `recommendation`. Run:

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.healthfailure.HealthFailureApplication"
```

In another terminal:

```shell
curl -i http://127.0.0.1:8080/actuator/health/recommendation
curl -i http://127.0.0.1:8080/actuator/health
```

On Windows, you can use `mvn.cmd` and `curl.exe`. With the default scenario `demo.primary=io` and fallback ready, the recommendation branch returns HTTP `200` with body:

```json
{
  "status": "DEGRADED",
  "details": {
    "reason": "DEPENDENCY_IO_FAILURE",
    "fallback": "READY"
  }
}
```

JSON key ordering and whitespace do not matter. On the aggregate endpoint, other components still participate; if another component is `DOWN`, the aggregate status under this configuration will be `DOWN`.

Stop the application, then test without fallback:

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.healthfailure.HealthFailureApplication" "-Dspring-boot.run.arguments=--demo.fallback-ready=false"
```

The recommendation branch switches to `DOWN`, `fallback=NOT_READY`, and HTTP `503`. Replace the argument with `--demo.primary=up` to observe `UP`, or `--demo.primary=timeout` to observe `reason=DEPENDENCY_TIMEOUT` when fallback is still available.

The example displays full details on loopback for learning. In operational environments, access permissions and the `show-details` policy must be appropriate; custom health fields should not contain secrets in the first place.

## 10. Timeouts, Interruptions, and Slow Checks Are Three Different Things

**Timeout** means an operation has a deadline and did not finish within the allowed time. Catching `TimeoutException` only handles a timeout signal that has already occurred; the `catch` block itself does not establish a timeout for `primary.verify()`.

**Thread interruption** is a cooperative signal asking a blocking or active operation to stop according to contract. Once `InterruptedException` is caught, do not retry immediately, do not clear the flag and report `UP`, and do not assume the external network is broken.

**Slow check** is an observation about duration. The `management.endpoint.health.logging.slow-indicator-threshold` property adjusts Actuator's warning log threshold; it does not automatically cancel the call or transition it to another status.

When writing an adapter with real I/O, define the client timeout, connection timeout, operation timeout, and total cost of the check. Do not assume a timeout at a wrapper layer can automatically stop the underlying work.

For example, `Future.get(timeout)` may throw `TimeoutException`, yet the awaited task may continue running. Even when calling `cancel(true)`, stopping still depends on whether the task and client honor interrupts. Creating a new executor per health call and abandoning background tasks causes monitoring to add load and leak resources.

If an adapter wraps errors in `CompletionException` or `ExecutionException`, unwrap them in a controlled manner and classify the root cause per the adapter's contract. A catch block for `IOException` will not automatically catch an `IOException` sitting inside another wrapper. With reactive chains, error signals must be handled inside the chain, such as with `onErrorResume`, rather than only placing a `try/catch` around publisher creation.

## 11. Keep Results Useful Without Hiding Causes

Published results and internal diagnostic data serve different purposes:

| Where used | Appropriate information |
| --- | --- |
| Published health | Status, stable reason code, fallback state, and non-sensitive metrics. |
| Access-controlled internal logs | Error type, timestamp, component, correlation ID, and cause needed for investigation. |
| Metrics | Failure rate, check duration, degradation count, and recovery time. |

Avoid two extremes: returning full stack traces on the endpoint or swallowing all errors so operators only see `DOWN` with no way to investigate. In a real system, supplement with appropriate internal diagnostics while avoiding logging the same stack trace on every poll and avoiding turning expected failures into an unbounded log stream.

Do not use `Health.down(ex)` without reviewing what exception content might enter `details` and other display channels. Also do not assume `/env`'s value masking automatically processes every string you place into custom health.

After a transient failure, the next check can return to `UP` if the primary path succeeds. Do not keep a permanent "has failed once" flag and forget to design a clearing condition. If anti-flapping behavior is needed, use a policy with explicit state, thresholds, and time windows; `HealthIndicator` does not automatically supply those conditions simply because polling runs repeatedly.

## 12. Verify the Policy Instead of Only Testing the Happy Path

Before using in production, gather evidence for each layer:

- **Classification:** timeouts, I/O errors, misconfiguration, unexpected errors, and fallback-path errors enter the expected branches.
- **Thread interruption:** the interrupt flag is preserved; no retries or extra I/O occur after interruption.
- **Side effects:** the probe only observes; it does not send real transactions, refresh data, or create unmanaged resources.
- **Data confidentiality:** details contain no exception messages, tokens, or user data; internal logs remain sufficient for investigation.
- **Aggregation:** `UP + DEGRADED` yields `DEGRADED`; `DOWN + DEGRADED` still yields `DOWN` per the chosen order.
- **HTTP:** verify `DOWN=503`, `OUT_OF_SERVICE=503`, and `DEGRADED` matching policy after adding custom mappings.
- **Recovery:** the same component can transition from failure back to `UP` when evidence changes; stale status is not retained erroneously.
- **Real cost:** measure duration and cancellation behavior with a real I/O client; the exception-throwing lambdas in this lesson do not prove this yet.

If JSON contains `DEGRADED` yet the monitoring tool still reports healthy, check which field the tool reads and whether HTTP `200` was chosen. If the individual branch is `DEGRADED` yet the aggregate endpoint is `UP`, check the status order. If requests hang despite having a timeout catch block, verify that the underlying operation actually has a timeout configured.

Proper exception handling in health is not just preventing an exception from escaping. It must turn evidence into meaningful status, preserve interrupt signals, describe degradation honestly, and make both aggregate results and HTTP reflect the chosen policy.
