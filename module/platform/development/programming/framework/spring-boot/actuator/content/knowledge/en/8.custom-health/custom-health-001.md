# Building a HealthIndicator for an Application-Specific Component

## 1. When Connections Are Healthy but Functionality Is Still Unusable

Suppose a shipping fee calculation application loads a pricing rule table into memory. The database is still reachable, Redis still responds, and the process is still serving HTTP, yet the rule table has not been loaded or has become too stale. In that situation, built-in infrastructure checks cannot answer the question: **does the fee calculation component have data that meets the conditions to operate?**

A custom health check (`HealthIndicator`) expresses that condition in application code. It reads evidence from a specific component, evaluates it against defined criteria, and returns a `Health` object containing the status along with the necessary details.

Do not create an indicator just to increase the number of components in the JSON output. Create one when there is an important operational condition that existing indicators cannot observe, such as reference data being loaded, a processing engine being initialized, or a dedicated connection being ready.

In this lesson, we build the `rateCatalog` indicator for the pricing rule table. The example uses **Java 21 and Spring Boot 3.3.0**, including a standalone check and registration into Actuator. The policy on "how stale data may be at most" is a decision made by this example, not a default prescribed by Spring Boot.

## 2. Defining the Contract Before Writing Code

A useful indicator must have clear answers to four questions:

1. **Which component is checked?** The rule table residing in the memory of this process itself.
2. **What evidence is read?** A snapshot containing the rule count and the timestamp of the most recent successful refresh.
3. **When does it pass?** Data exists, there is at least one rule, the refresh timestamp is not in the future, and the data age does not exceed the threshold.
4. **What does the result not prove?** It does not prove that every pricing formula is correct, every order can be calculated, or the external data source is currently reachable.

The example chooses a five-minute threshold and the following evaluation order:

| Condition | Status | Reason code |
| --- | --- | --- |
| No snapshot yet | `OUT_OF_SERVICE` | `NOT_LOADED` |
| Snapshot has zero rules | `DOWN` | `EMPTY_CATALOG` |
| Refresh timestamp is in the future | `DOWN` | `CLOCK_SKEW` |
| Data age is greater than five minutes | `DOWN` | `STALE_CATALOG` |
| Data is sufficient and age is at most five minutes | `UP` | `READY` |

Here, `OUT_OF_SERVICE` expresses that the component is not yet eligible to serve; `DOWN` expresses that a snapshot exists but fails the criteria. The development team may choose a different policy if business requirements differ, but it must be interpreted consistently and be testable.

The threshold includes the boundary point: **at exactly five minutes it is still `UP`; only past five minutes does it become `DOWN`**. A small detail like `>` versus `>=` changes actual behavior, so it must be stated upfront rather than decided arbitrarily in code.

## 3. The HealthIndicator Contract and Support Class

`HealthIndicator` is an interface in the `org.springframework.boot.actuate.health` package. Its central method is:

```java
Health health();
```

This is a method signature, not a standalone Java program. An implementation must return `Health`, not a raw `"UP"` string, not `null`, and not a `ResponseEntity`.

Two common implementation approaches are:

| Approach | What the application must do itself |
| --- | --- |
| `implements HealthIndicator` | Implement `health()`, construct `Health`, and handle errors appropriately. |
| `extends AbstractHealthIndicator` | Implement `doHealthCheck(Health.Builder)`; the superclass creates the builder, invokes the check, and converts any escaping `Exception` into `DOWN`. |

This lesson uses the second approach. `AbstractHealthIndicator` catches `Exception`, not every `Throwable`; nor does it set a timeout on the code inside. Do not rely on the superclass to handle an infinitely hanging network call. You can inspect the exact mechanism in [Spring Boot 3.3.0 AbstractHealthIndicator source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/AbstractHealthIndicator.java).

A health call must produce a result for the current observation. Do not keep a shared `Health.Builder` across multiple requests; the builder for each invocation must be independent to avoid mixing statuses and details across threads.

## 4. Creating a Compilable and Runnable Example

This is a **standalone Maven project**. Create the files with the exact names and paths below. The model, indicator, and verification program do not require running a web server; the additional Spring Boot application in section 6 will expose the same indicator through Actuator.

### 4.1. Declaring Dependencies

File `pom.xml`:

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
    <artifactId>custom-health-demo</artifactId>
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

### 4.2. The Observed Component

File `src/main/java/learning/customhealth/RateCatalog.java`:

```java
package learning.customhealth;

import java.time.Instant;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class RateCatalog {

    public record Snapshot(int ruleCount, Instant lastSuccessfulRefresh) {
        public Snapshot {
            if (ruleCount < 0) {
                throw new IllegalArgumentException("ruleCount must not be negative");
            }
            Objects.requireNonNull(lastSuccessfulRefresh, "lastSuccessfulRefresh");
        }
    }

    private final AtomicReference<Snapshot> current = new AtomicReference<>();

    public Snapshot snapshot() {
        return current.get();
    }

    public void publish(int ruleCount, Instant lastSuccessfulRefresh) {
        current.set(new Snapshot(ruleCount, lastSuccessfulRefresh));
    }
}
```

`Snapshot` is an immutable snapshot: the rule count and refresh timestamp travel together. `AtomicReference` allows the data-loading thread to publish a complete snapshot, while the health thread reads a single consistent reference. The indicator reads `snapshot()` exactly once per check, avoiding mixing the count from an old version with the timestamp from a new one.

In a real application, `publish(...)` is only called after the loader has fetched and successfully validated a rule set. This simplified example only stores enough metadata to study the health mechanism; it does not implement the shipping fee rule engine or an external data loader.

If a load fails, `lastSuccessfulRefresh` must not be updated as if it had succeeded. Doing so would cause health to keep reporting fresh data even though the actual rule table was not refreshed.

### 4.3. Custom Indicator

File `src/main/java/learning/customhealth/RateCatalogHealthIndicator.java`:

```java
package learning.customhealth;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

import org.springframework.boot.actuate.health.AbstractHealthIndicator;
import org.springframework.boot.actuate.health.Health;

public final class RateCatalogHealthIndicator extends AbstractHealthIndicator {

    private final RateCatalog catalog;
    private final Clock clock;
    private final Duration maxAge;

    public RateCatalogHealthIndicator(RateCatalog catalog, Clock clock, Duration maxAge) {
        this.catalog = Objects.requireNonNull(catalog, "catalog");
        this.clock = Objects.requireNonNull(clock, "clock");
        this.maxAge = Objects.requireNonNull(maxAge, "maxAge");
        if (maxAge.isZero() || maxAge.isNegative()) {
            throw new IllegalArgumentException("maxAge must be positive");
        }
    }

    @Override
    protected void doHealthCheck(Health.Builder builder) {
        RateCatalog.Snapshot snapshot = catalog.snapshot();
        builder.withDetail("maxAgeSeconds", maxAge.toSeconds());

        if (snapshot == null) {
            builder.outOfService().withDetail("reason", "NOT_LOADED");
            return;
        }

        builder.withDetail("ruleCount", snapshot.ruleCount());
        if (snapshot.ruleCount() == 0) {
            builder.down().withDetail("reason", "EMPTY_CATALOG");
            return;
        }

        Duration age = Duration.between(snapshot.lastSuccessfulRefresh(), Instant.now(clock));
        builder.withDetail("ageSeconds", age.toSeconds());
        if (age.isNegative()) {
            builder.down().withDetail("reason", "CLOCK_SKEW");
            return;
        }
        if (age.compareTo(maxAge) > 0) {
            builder.down().withDetail("reason", "STALE_CATALOG");
            return;
        }

        builder.up().withDetail("reason", "READY");
    }
}
```

Notable design choices:

- **Receive the component via constructor:** the indicator observes the exact `RateCatalog` provided by the application, rather than creating another empty catalog on its own.
- **Receive `Clock`:** tests can control time without actually waiting five minutes or using `Thread.sleep()`.
- **Validate configuration on construction:** an invalid threshold is a configuration error that should surface early, not a random health call returning `DOWN`.
- **Compare `Duration`:** the staleness decision preserves full time precision; `ageSeconds` is merely a diagnostic detail rounded down to whole seconds.
- **Read-only:** `doHealthCheck` does not call `publish`, does not reload data, and does not adjust the clock.

Details such as `reason`, `ruleCount`, and `ageSeconds` are a contract defined by this application. Actuator does not understand that `STALE_CATALOG` matters more than `EMPTY_CATALOG`; the status chosen by the indicator's code is what gets used for health aggregation.

## 5. Checking Branches Using Fixed Time

File `src/main/java/learning/customhealth/RateCatalogHealthIndicatorDemo.java`:

```java
package learning.customhealth;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.Status;

public class RateCatalogHealthIndicatorDemo {

    private static final Instant NOW = Instant.parse("2026-01-01T00:10:00Z");
    private static final Clock CLOCK = Clock.fixed(NOW, ZoneOffset.UTC);
    private static final Duration MAX_AGE = Duration.ofMinutes(5);

    public static void main(String[] args) {
        check("notLoaded", null, Status.OUT_OF_SERVICE, "NOT_LOADED");
        check("empty", new RateCatalog.Snapshot(0, NOW), Status.DOWN, "EMPTY_CATALOG");
        check("fresh", new RateCatalog.Snapshot(12, NOW.minusSeconds(30)), Status.UP, "READY");
        check("boundary", new RateCatalog.Snapshot(12, NOW.minusSeconds(300)), Status.UP, "READY");
        check("pastBoundary", new RateCatalog.Snapshot(12, NOW.minusSeconds(300).minusNanos(1)),
                Status.DOWN, "STALE_CATALOG");
        check("stale", new RateCatalog.Snapshot(12, NOW.minusSeconds(301)), Status.DOWN, "STALE_CATALOG");
        check("future", new RateCatalog.Snapshot(12, NOW.plusSeconds(1)), Status.DOWN, "CLOCK_SKEW");
    }

    private static void check(String name, RateCatalog.Snapshot input, Status expected, String reason) {
        RateCatalog catalog = new RateCatalog();
        if (input != null) {
            catalog.publish(input.ruleCount(), input.lastSuccessfulRefresh());
        }
        RateCatalog.Snapshot before = catalog.snapshot();
        RateCatalogHealthIndicator indicator = new RateCatalogHealthIndicator(catalog, CLOCK, MAX_AGE);
        Health result = indicator.health();

        if (!expected.equals(result.getStatus()) || !reason.equals(result.getDetails().get("reason"))) {
            throw new AssertionError("Unexpected result for " + name + ": " + result);
        }
        if (catalog.snapshot() != before) {
            throw new AssertionError("Health check changed the catalog");
        }
        System.out.println(name + "=" + result.getStatus().getCode() + " (" + reason + ")");
    }
}
```

In the directory containing `pom.xml`, verify that `mvn -version` is using JDK 21 and run:

```shell
mvn compile dependency:build-classpath "-Dmdep.outputFile=target/classpath.txt"
```

On PowerShell, run next:

```powershell
$dependencyClasspath = (Get-Content -Raw -LiteralPath 'target/classpath.txt').Trim()
java -cp "target/classes;$dependencyClasspath" learning.customhealth.RateCatalogHealthIndicatorDemo
```

On Linux/macOS, the equivalent run command is:

```shell
java -cp "target/classes:$(cat target/classpath.txt)" learning.customhealth.RateCatalogHealthIndicatorDemo
```

This code uses Spring Boot libraries, so a standalone `javac RateCatalogHealthIndicator.java` will lack the classpath. Maven has already performed the Java compilation and dependency resolution; the `java` command above only runs the compiled check program.

Stdout of the check program is:

```text
notLoaded=OUT_OF_SERVICE (NOT_LOADED)
empty=DOWN (EMPTY_CATALOG)
fresh=UP (READY)
boundary=UP (READY)
pastBoundary=DOWN (STALE_CATALOG)
stale=DOWN (STALE_CATALOG)
future=DOWN (CLOCK_SKEW)
```

The `pastBoundary` case intentionally exceeds the limit by just one nanosecond. It proves that the logic does not round data age down to seconds before deciding the status. In that case, `ageSeconds` can still be `300` even though the status is already `DOWN`; that detail has lower resolution than the comparison. If the system needs near-boundary diagnostics, a duration detail with appropriate precision can be added.

The program also verifies that calling health does not replace the catalog snapshot. This is evidence of read-only behavior in the example, not a test covering every concurrency scenario of a real application.

## 6. Registering the Same Indicator in Spring Boot Actuator

Merely instantiating an object with `new` in the check program does not make Actuator aware of it. That object must be registered as a bean in the Spring context.

### 6.1. Creating the Application and Beans

File `src/main/java/learning/customhealth/CustomHealthApplication.java`:

```java
package learning.customhealth;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CustomHealthApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomHealthApplication.class, args);
    }

    @Bean
    RateCatalog rateCatalog() {
        return new RateCatalog();
    }

    @Bean
    Clock healthClock() {
        return Clock.systemUTC();
    }

    @Bean
    @ConditionalOnProperty(prefix = "app.health.rate-catalog", name = "enabled",
            havingValue = "true", matchIfMissing = true)
    RateCatalogHealthIndicator rateCatalogHealthIndicator(
            RateCatalog catalog,
            Clock clock,
            @Value("${app.health.rate-catalog.max-age-seconds:300}") long maxAgeSeconds) {
        return new RateCatalogHealthIndicator(catalog, clock, Duration.ofSeconds(maxAgeSeconds));
    }

    @Bean
    @ConditionalOnProperty(prefix = "demo.catalog", name = "load",
            havingValue = "true", matchIfMissing = true)
    ApplicationRunner loadDemoCatalog(
            RateCatalog catalog,
            Clock clock,
            @Value("${demo.catalog.rule-count:12}") int ruleCount,
            @Value("${demo.catalog.age-seconds:30}") long ageSeconds) {
        return args -> catalog.publish(ruleCount, Instant.now(clock).minusSeconds(ageSeconds));
    }
}
```

Keeping the classes in the same package makes the example easy to run; the indicator is registered via `@Bean`, so `@Component` is not added directly to the `RateCatalogHealthIndicator` class. Using both approaches could create two unintended beans. In a larger project, bean configuration can be placed separately, while still maintaining a single clear registration mechanism.

`loadDemoCatalog` is only a simulated data loader for testing statuses, not a real data-loading task. It runs when the application starts; the indicator does not call back into the loader. Properties starting with `demo.catalog` serve only this experiment.

### 6.2. Bean Name Becomes Component Name

The bean name from the method is `rateCatalogHealthIndicator`. Actuator strips the `HealthIndicator` suffix, so the component name is `rateCatalog`, with the default path:

```text
/actuator/health/rateCatalog
```

The bean name is the determining piece of information in this case, not the constructor parameter name or the catalog name in the business domain. Renaming the bean can change the path and any configurations referencing it; treat it as an operational contract change. See [custom indicator naming and registration rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators).

### 6.3. Observation Configuration for Local Learning

File `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health
management.endpoint.health.show-components=always
management.endpoint.health.show-details=always
app.health.rate-catalog.max-age-seconds=300
```

This full visibility configuration is for observation on loopback. When moving to an operational environment, choose access permissions and a visibility policy appropriate for the actual detail contents. Enabling `show-details` does not replace application authentication or authorization.

Run the application:

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.customhealth.CustomHealthApplication"
```

Specifying the main class distinguishes it from the check program in section 5. After the simulated loader finishes, open another terminal:

```shell
curl -i http://127.0.0.1:8080/actuator/health/rateCatalog
curl -i http://127.0.0.1:8080/actuator/health
```

On Windows PowerShell, use `curl.exe` if `curl` is a PowerShell alias. On Windows you can also invoke `mvn.cmd` instead of `mvn`.

With the defaults, if called within five minutes of the simulated refresh timestamp, the `rateCatalog` branch has status `UP`, reason `READY`, and `ruleCount=12`. The JSON body has the following structure; data age is a number that changes depending on when it is called:

```json
{
  "status": "UP",
  "details": {
    "maxAgeSeconds": 300,
    "ruleCount": 12,
    "ageSeconds": 31,
    "reason": "READY"
  }
}
```

`31` is only an illustrative number, not fixed stdout. Because the example only loads once, after the data expires, the status transitions to `DOWN` without needing a restart. This shows that health depends on current evidence; a single `UP` does not remain valid forever.

On the aggregate endpoint, the indicator's result appears under `components.rateCatalog`. Other components also participate in aggregation, so `rateCatalog=UP` does not guarantee that the overall status is `UP`.

## 7. Creating Controlled Failure Scenarios

Stop the running application session before each retry. The following commands run from the project directory and keep the default 300-second threshold.

### Data Not Loaded Yet

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.customhealth.CustomHealthApplication" "-Dspring-boot.run.arguments=--demo.catalog.load=false"
```

The application can still start, but `rateCatalog` returns `OUT_OF_SERVICE` with `reason=NOT_LOADED` because no snapshot has been published.

### Data Already Stale Upon Load

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.customhealth.CustomHealthApplication" "-Dspring-boot.run.arguments=--demo.catalog.age-seconds=301"
```

The branch returns `DOWN` with `reason=STALE_CATALOG`. There is no need to wait a full five minutes to test this case.

### Empty Rule Table

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.customhealth.CustomHealthApplication" "-Dspring-boot.run.arguments=--demo.catalog.rule-count=0"
```

The branch returns `DOWN` with `reason=EMPTY_CATALOG` even though the catalog object still exists. Having a bean does not mean the data inside the bean meets requirements.

With the default HTTP mapping of the health endpoint, `DOWN` and `OUT_OF_SERVICE` map to HTTP `503`; `UP` maps to `200`. This `503` is the result of the health publishing machinery, not because `doHealthCheck` threw an HTTP exception. When an application customizes status mapping or aggregation, you must read the active policy.

The example does not create a new status such as `STALE`. The reason code `STALE_CATALOG` only supplements diagnostics alongside the `DOWN` status. If you define a new status yourself, you must also define aggregation order and HTTP mapping; do not assume every new string is automatically treated as a failure.

## 8. Enabling/Disabling an Application-Owned Indicator

Do not assume that simply setting `management.health.rateCatalog.enabled=false` will remove any custom bean of the corresponding name. Enable/disable properties only take effect when the configuration creating the bean actually uses them as a condition.

In the example, we deliberately declare `@ConditionalOnProperty` with a custom key:

```properties
app.health.rate-catalog.enabled=false
```

When starting with this value, the `rateCatalogHealthIndicator` bean is not created. The catalog and simulated loader remain separate components; disabling observation does not fix the data and does not make the business component work again.

`havingValue="true"` requires the value to be `true`; `matchIfMissing=true` allows creating the indicator when the key is omitted. This is the direct meaning of the annotation, not an automatic property-name recognition mechanism. You can cross-check the [ConditionalOnProperty contract](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.java).

Similarly, `management.health.defaults.enabled=false` does not automatically remove this bean: the condition we wrote only reads `app.health.rate-catalog.enabled`. If you want the global default switch to affect a custom indicator, that condition must be explicitly designed and tested.

Distinguish three actions:

- **Disable the bean:** that bean's check no longer exists in the health tree.
- **Hide details:** the check can still run and affect the status, but the caller does not receive details.
- **Change criteria:** the check still exists, but the `UP`/`DOWN` conditions change; this is a policy change with operational impact.

## 9. Designing Checks So Observation Does Not Cause Additional Incidents

### Read-Only and Non-Mutating

Do not reload the entire rule table, write business records, send emails, or create real transactions inside `health()`. A monitoring system may call it very frequently and from many places. If every call mutates the system, monitoring frequency becomes part of business behavior.

The example reads a published snapshot and therefore does not refresh data. Thus, it answers **whether the current data is usable according to age and count criteria**, rather than **whether the loading source is currently reachable**. If both pieces of evidence are needed, define separate check boundaries instead of letting one signal stand in for a different question.

### Bounded Time and Cost

If a real indicator requires I/O, timeouts must be configured in the client or corresponding I/O operation and total cost must be bounded. `AbstractHealthIndicator` only handles exceptions after they occur; it does not automatically interrupt a hanging operation.

Do not create a new thread or a new pool for each health call. Wrapping a call with `Future.get(timeout)` also does not prove that the underlying I/O was canceled when the timeout expired. You must understand the cancellation and timeout mechanisms of the specific client in use.

`management.endpoint.health.logging.slow-indicator-threshold` adjusts the slow-indicator warning threshold, not a deadline to automatically cancel it. With WebFlux and genuinely reactive clients, the appropriate contract is `ReactiveHealthIndicator`; do not call `.block()` on an event loop thread just to fit into a synchronous indicator.

### Do Not Expose Sensitive Information

Only add details needed for operational action: a stable reason code, data age, item count, or non-sensitive component name. Do not put tokens, passwords, full connection strings, or customer data into `withDetail`.

The superclass converts an escaping exception into `DOWN` along with error information; the exception message may contain sensitive content. For foreseeable errors, map to a safe reason code and log internally according to the application's policy. `show-details=never` reduces data returned through the endpoint, but does not turn putting secrets into a `Health` object into a good design.

### Do Not Mechanically Tie Health Conclusions to Orchestration Actions

Registering `rateCatalog` in the aggregate health tree does not automatically add it to every liveness/readiness group. Whether the orchestrator uses that signal to accept traffic or restart the process is a separate configuration decision.

A failing external data source does not by default mean the JVM needs to be restarted. Before using an indicator in a probe, determine whether the component can self-recover, whether it can continue serving using stale data, and which orchestration action actually aids recovery.

## 10. Verification and Common Pitfalls

Beyond the seven scenarios of the check program, when integrating into a real application, confirm:

| What to verify | Useful evidence |
| --- | --- |
| Correct status rules | Test no data, empty data, fresh data, exact threshold, just past threshold, and future timestamp. |
| No side effects | Snapshot and business data remain unchanged after calling health multiple times. |
| Correct registration | Bean is present, contributor name is `rateCatalog`, and there is only one bean as designed. |
| Correct toggle | Change `app.health.rate-catalog.enabled`, restart context, and verify bean presence/absence. |
| Correct published response | Verify path, HTTP status, JSON, and visibility policy via HTTP in a runnable environment. |
| Correct operational limits | Measure latency, I/O call count, and behavior on client timeout if the indicator performs I/O. |

**Class exists but does not appear in Actuator:** check whether the class has become a bean, whether the configuration is loaded, and whether property conditions match. A unit test calling `new RateCatalogHealthIndicator(...)` successfully does not prove Spring has registered it.

**Bean exists but reads the wrong catalog:** check whether the indicator receives the exact bean being updated by the business thread. Creating `new RateCatalog()` inside `doHealthCheck` will always observe a new unloaded object, not the real application state.

**Always returns `UP`:** check whether the refresh timestamp is being reset on every health call, whether errors are being swallowed in a `catch` block and reported healthy, or whether the empty-data criterion was missed.

**Same data but tests pass intermittently:** check whether the code depends on the real clock or compares boundary conditions incorrectly. Use `Clock.fixed` to turn time conditions into explicit test data.

**Returns `DOWN` when `ruleCount` is negative or `maxAge` is zero:** in this design, that is not the expected outcome. The constructor rejects invalid data or configuration, which can fail startup initialization. Distinguish setup errors from health status observed after the application is running.

A complete indicator must connect **operational condition → readable evidence → status → safe details → registered bean → verifiable result**. For `rateCatalog`, this chain is realized through a consistent snapshot, explicit data-age criteria, a read-only check, and fixed-time test scenarios.
