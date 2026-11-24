# Add business metrics with bounded tags

## 1. What problem does this lab solve?

Infrastructure metrics show how CPU, memory, or HTTP requests are behaving. Business metrics answer questions closer to what the system actually does:

- How many orders were created successfully?
- How many checkouts were rejected or failed with an error?
- How does checkout duration differ across channels?
- How many inputs fall outside the channels the system has standardized?

In Micrometer, a **tag** is a key–value pair attached to a meter, such as `channel=web` or `outcome=success`. When exported to Prometheus, they become labels.

Tags are useful for slicing data, but each value combination can create additional time series. If you put `orderId`, `userId`, or arbitrary strings from requests into tags, the number of combinations can grow with business data without any reasonable bound.

The goal of this lab is to create meaningful metrics while controlling **tag value cardinality** from design time and at the ingestion boundary.

The example uses Spring Boot 3.3.x, Java 17+, and the Micrometer version managed by Spring Boot. The test app runs locally only, uses the Servlet stack, and exports Prometheus via Actuator.

## 2. Lock down semantics before writing code

The lab simulates a checkout operation:

- `success`: order creation is considered successful.
- `rejected`: business logic intentionally rejects it.
- `error`: an exception is thrown during processing.

We design two meters:

| Micrometer Name | Type | Meaning | Tags |
| --- | --- | --- | --- |
| `business.orders.created` | Counter | Number of orders created successfully at the example's recording point | channel |
| `business.checkout.duration` | Timer | Duration and count of completed checkout processing, including rejections/errors | channel, outcome |

The counter counts only successful order creations. The timer measures both duration and recording count, so there is no need to create another total-checkout counter just to duplicate the timer's count.

This simulation writes to no database and performs no real payment. When applying to a transactional system, re-select the success recording point so it aligns with business commit.

### 2.1. Allowed value set

| Tag | Fixed values | Handling out-of-set inputs |
| --- | --- | --- |
| channel | web, mobile, batch, other | Normalize to other |
| outcome | success, rejected, error | Derived from processing flow, not taken raw from client |

Keep tag names consistent across every meter in the same family. Do not use `channel` in one place and `source` in another for the same metric name; nor register the same timer family with different sets of tag keys.

Case and surrounding whitespace for channel are normalized. `WEB`, `web`, and ` web ` all map to `web`. Blank, missing, or unrecognized values all map to `other`.

Outcome is the result observed by the service. In the lab, the client picks a scenario to trigger each branch; in a real system, clients must not self-declare outcome and skew metrics.

### 2.2. Bound the number of meters created

By pre-registering every combination:

```text
Counter: 4 channels                        =  4 meters
Timer:   4 channels × 3 outcomes           = 12 meters
Total business meters for this recorder    = 16 meters
```

This is the number of meter IDs in a registry, not the total number of Prometheus time series. A timer can export multiple series such as count, sum, buckets, or other entries depending on configuration/exporter.

In a running Spring Boot application, the registry also contains JVM, HTTP, and other meters. Therefore do not expect the entire application registry total to equal 16; that number applies only to the designed business meter set.

## 3. Prepare dependencies and configuration

Use a Spring Boot project with a Gradle wrapper, Boot plugin, and appropriate dependency management. Configuration snippet to add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    archiveFileName = 'bounded-business-metrics.jar'
}
```

This is not a complete build file. In a repository with build orchestration, use the repository's mechanism to avoid duplicate configuration.

Local lab file `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

This minimal lab adds no Spring Security or proxy. When running in an environment that has them, use appropriate access permissions; do not strip security from a real application to follow a lab example.

Do not expose all of Actuator just to read a Prometheus scrape output. Other endpoints are unnecessary for this practice goal.

## 4. Create a recorder with a fixed tag set

### 4.1. Startup class

File `src/main/java/demo/businessmetrics/BusinessMetricsApplication.java`:

```java
package demo.businessmetrics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BusinessMetricsApplication {
    public static void main(String[] args) {
        SpringApplication.run(BusinessMetricsApplication.class, args);
    }
}
```

### 4.2. Normalize channel and register meters once

File `src/main/java/demo/businessmetrics/CheckoutMetrics.java`:

```java
package demo.businessmetrics;

import java.util.EnumMap;
import java.util.Locale;
import java.util.Map;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class CheckoutMetrics {

    public enum Channel {
        WEB("web"),
        MOBILE("mobile"),
        BATCH("batch"),
        OTHER("other");

        private final String tag;

        Channel(String tag) {
            this.tag = tag;
        }

        public String tag() {
            return tag;
        }

        public static Channel fromRaw(String raw) {
            if (raw == null) {
                return OTHER;
            }

            return switch (raw.trim().toLowerCase(Locale.ROOT)) {
                case "web" -> WEB;
                case "mobile" -> MOBILE;
                case "batch" -> BATCH;
                default -> OTHER;
            };
        }
    }

    public enum Outcome {
        SUCCESS("success"),
        REJECTED("rejected"),
        ERROR("error");

        private final String tag;

        Outcome(String tag) {
            this.tag = tag;
        }

        public String tag() {
            return tag;
        }
    }

    private final MeterRegistry registry;

    private final Map<Channel, Counter> created =
            new EnumMap<>(Channel.class);

    private final Map<Channel, Map<Outcome, Timer>> durations =
            new EnumMap<>(Channel.class);

    public CheckoutMetrics(MeterRegistry registry) {
        this.registry = registry;

        for (Channel channel : Channel.values()) {
            created.put(channel,
                    Counter.builder("business.orders.created")
                            .description("Successfully created orders")
                            .tag("channel", channel.tag())
                            .register(registry));

            Map<Outcome, Timer> byOutcome = new EnumMap<>(Outcome.class);

            for (Outcome outcome : Outcome.values()) {
                Timer timer = Timer.builder("business.checkout.duration")
                        .description("Completed checkout processing duration")
                        .tags("channel", channel.tag(),
                                "outcome", outcome.tag())
                        .register(registry);

                byOutcome.put(outcome, timer);
            }

            durations.put(channel, byOutcome);
        }
    }

    public Timer.Sample start() {
        return Timer.start(registry);
    }

    public void orderCreated(Channel channel) {
        created.get(channel).increment();
    }

    public void stop(
            Timer.Sample sample,
            Channel channel,
            Outcome outcome) {
        sample.stop(durations.get(channel).get(outcome));
    }
}
```

The maps are built in the constructor and then used only for lookup. Micrometer counters and timers support concurrent recording operations; we do not insert entries into maps on each request.

Three design decisions are present here:

1. Enums keep the emitted value set finite.
2. Raw strings are normalized before selecting a meter.
3. All meters are registered once, without creating an unbounded cache keyed by raw input strings.

Do not replace the enum map with `ConcurrentHashMap<String, Timer>` keyed by raw channel. A thread-safe map can still grow memory without bound.

Pre-registering 16 meters is a small, intentional choice in this lab. If the valid combination space is huge, pre-registration itself can consume resources; reduce dimensionality instead of merely switching from dynamic registration to full pre-registration.

## 5. Record once per business branch

File `src/main/java/demo/businessmetrics/CheckoutService.java`:

```java
package demo.businessmetrics;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    public enum Scenario {
        SUCCESS,
        REJECTED,
        ERROR
    }

    private final CheckoutMetrics metrics;

    public CheckoutService(CheckoutMetrics metrics) {
        this.metrics = metrics;
    }

    public boolean checkout(String rawChannel, Scenario scenario) {
        CheckoutMetrics.Channel channel =
                CheckoutMetrics.Channel.fromRaw(rawChannel);

        var sample = metrics.start();
        CheckoutMetrics.Outcome outcome = CheckoutMetrics.Outcome.ERROR;

        try {
            if (scenario == Scenario.REJECTED) {
                outcome = CheckoutMetrics.Outcome.REJECTED;
                return false;
            }

            if (scenario == Scenario.ERROR) {
                throw new IllegalStateException("simulated checkout failure");
            }

            metrics.orderCreated(channel);
            outcome = CheckoutMetrics.Outcome.SUCCESS;
            return true;
        } finally {
            metrics.stop(sample, channel, outcome);
        }
    }
}
```

Explanation of the order:

- Channel has already been mapped into the allowed set before picking a meter.
- `Timer.Sample` starts when the service begins handling the call.
- Outcome defaults to error so an exception on the processing path is never recorded as success.
- The counter increments only on the successful order-creation branch.
- The `finally` block records the timer on return or when an exception exits the try block.
- Every call under the lab's valid scenarios stops the sample exactly once.

The service timer is not end-to-end HTTP duration. It excludes full security filtering time, parameter binding, and response serialization. If both durations are needed, use distinct names/semantics to avoid misleading comparisons.

An HTTP parameter that fails conversion to Scenario may yield a 400 from the framework before entering the service. That request is not counted by this business timer. That is a measurement boundary, not automatically missing data.

### Reliability of counts

In-memory metrics are not a transaction ledger. Sudden process termination can lose unscraped data. Retries can create extra executions; incrementing before transaction commit can count a transaction that later rolls back.

In production, clearly define whether you are counting attempts, service outcomes, or committed events. If exact accounting or exactly-once business event counts are needed, use a durable data source rather than an in-memory counter.

## 6. Create an API to trigger the branches

File `src/main/java/demo/businessmetrics/CheckoutController.java`:

```java
package demo.businessmetrics;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CheckoutController {
    private final CheckoutService service;

    public CheckoutController(CheckoutService service) {
        this.service = service;
    }

    @PostMapping("/lab/checkout")
    public ResponseEntity<String> checkout(
            @RequestParam(name = "channel", defaultValue = "") String channel,
            @RequestParam(name = "scenario", defaultValue = "SUCCESS")
            CheckoutService.Scenario scenario) {
        try {
            boolean created = service.checkout(channel, scenario);

            if (created) {
                return ResponseEntity.status(HttpStatus.CREATED)
                        .body("created");
            }

            return ResponseEntity.status(422).body("rejected");
        } catch (IllegalStateException exception) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body("failed");
        }
    }
}
```

This API uses POST because it triggers a simulated business operation. The scenario parameter is only a lab tool to reproduce outcomes; it is not a design allowing clients to dictate business outcomes in a real system.

In the example, the HTTP enum uses `SUCCESS`, `REJECTED`, `ERROR`. The emitted outcome tag is lowercase and chosen inside the service. Those two value sets have distinct roles.

Catching `IllegalStateException` in the controller handles the specific simulated error. Do not treat this as a general exception-handling policy for a production application.

## 7. Add guards at MeterRegistry

Enum normalization is the primary mechanism. Add `MeterFilter` to block another instrumentation path from accidentally registering extra tag values.

File `src/main/java/demo/businessmetrics/MetricGuardConfiguration.java`:

```java
package demo.businessmetrics;

import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricGuardConfiguration {

    @Bean
    MeterFilter businessChannelGuard() {
        return MeterFilter.maximumAllowableTags(
                "business.",
                "channel",
                4,
                MeterFilter.deny());
    }

    @Bean
    MeterFilter checkoutOutcomeGuard() {
        return MeterFilter.maximumAllowableTags(
                "business.checkout.duration",
                "outcome",
                3,
                MeterFilter.deny());
    }
}
```

Spring Boot applies MeterFilter beans to the Boot-managed registry. A registry instantiated manually via `new SimpleMeterRegistry()` elsewhere does not receive these beans automatically; when testing directly, attach the filters to the test registry.

Meaning and limits:

- Name prefixes are matched against Micrometer meter names, not Prometheus underscore-converted names.
- The channel guard applies to meters starting with `business.`.
- The cap is the number of distinct tag values the filter tracks within that scope.
- Exceeding the cap denies meter registration per the supplied fallback filter; it does not rewrite values to other.
- This is not an exact allowlist. If four bad values are registered first, merely setting max=4 does not turn them into web/mobile/batch/other.
- The filter does not evict existing meters or drop old values to admit new ones.
- A denied meter can result in measurements with no exported data; do not treat the absence of a Java exception as proof the measurement was saved.

Therefore, do not use the filter as a “take the first four channels seen” algorithm. The allowed set must live in design and be normalized before registration.

Capping individual tags also does not cap total meters if metric names or other tags grow freely. Do not build names like `business.orders.customer.12345` to bypass tag limits; the cardinality problem simply moves into the metric name.

## 8. Test tag bounds and outcome branches

The tests below use a standalone `SimpleMeterRegistry` without starting a web server. Because this registry contains only the example's meters, we can assert the exact total of 16.

File `src/test/java/demo/businessmetrics/CheckoutMetricsTest.java`:

```java
package demo.businessmetrics;

import java.time.Duration;
import java.util.Set;
import java.util.stream.Collectors;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CheckoutMetricsTest {

    private static SimpleMeterRegistry registryWithGuards() {
        var registry = new SimpleMeterRegistry();
        var guards = new MetricGuardConfiguration();

        registry.config()
                .meterFilter(guards.businessChannelGuard())
                .meterFilter(guards.checkoutOutcomeGuard());

        return registry;
    }

    @Test
    void rawChannelsDoNotCreateUnboundedMeters() {
        try (var registry = registryWithGuards()) {
            var metrics = new CheckoutMetrics(registry);
            var service = new CheckoutService(metrics);

            service.checkout(" WEB ", CheckoutService.Scenario.SUCCESS);
            service.checkout("Web", CheckoutService.Scenario.SUCCESS);
            service.checkout(null, CheckoutService.Scenario.SUCCESS);

            for (int index = 0; index < 1_000; index++) {
                service.checkout("partner-" + index,
                        CheckoutService.Scenario.SUCCESS);
            }

            assertEquals(16, registry.getMeters().size());

            assertEquals(2.0, registry.get("business.orders.created")
                    .tag("channel", "web").counter().count(), 0.0);

            assertEquals(1_001.0, registry.get("business.orders.created")
                    .tag("channel", "other").counter().count(), 0.0);

            assertEquals(1_001L,
                    registry.get("business.checkout.duration")
                            .tags("channel", "other",
                                    "outcome", "success")
                            .timer().count());

            Set<String> channels = registry.getMeters().stream()
                    .map(meter -> meter.getId().getTag("channel"))
                    .collect(Collectors.toSet());

            assertEquals(Set.of("web", "mobile", "batch", "other"),
                    channels);
        }
    }

    @Test
    void rejectedAndErrorAreTimedWithoutCreatedOrders() {
        try (var registry = registryWithGuards()) {
            var metrics = new CheckoutMetrics(registry);
            var service = new CheckoutService(metrics);

            assertFalse(service.checkout("mobile",
                    CheckoutService.Scenario.REJECTED));

            assertThrows(IllegalStateException.class,
                    () -> service.checkout("batch",
                            CheckoutService.Scenario.ERROR));

            assertEquals(1L,
                    registry.get("business.checkout.duration")
                            .tags("channel", "mobile",
                                    "outcome", "rejected")
                            .timer().count());

            assertEquals(1L,
                    registry.get("business.checkout.duration")
                            .tags("channel", "batch",
                                    "outcome", "error")
                            .timer().count());

            assertEquals(0.0, registry.get("business.orders.created")
                    .tag("channel", "mobile").counter().count(), 0.0);

            assertEquals(0.0, registry.get("business.orders.created")
                    .tag("channel", "batch").counter().count(), 0.0);
        }
    }

    @Test
    void guardsDenyAdditionalTagValues() {
        try (var registry = registryWithGuards()) {
            new CheckoutMetrics(registry);

            registry.counter("business.orders.created",
                    "channel", "unexpected-channel").increment();

            registry.timer("business.checkout.duration",
                    "channel", "web",
                    "outcome", "unexpected-outcome")
                    .record(Duration.ofMillis(1));

            assertNull(registry.find("business.orders.created")
                    .tag("channel", "unexpected-channel").counter());

            assertNull(registry.find("business.checkout.duration")
                    .tags("channel", "web",
                            "outcome", "unexpected-outcome")
                    .timer());

            assertEquals(16, registry.getMeters().size());
        }
    }
}
```

Run:

```bash
./gradlew test
```

On Windows use `gradlew.bat test`. For multi-project builds, select the task path of the appropriate module.

These tests prove three distinct things:

| Test | What is verified |
| --- | --- |
| 1,000 unknown raw inputs | Does not increase meter count, still records all into other |
| Rejected/error branches | Timer still records once on rejected return or exception; success counter does not increment |
| Registering tags above cap | Filter blocks new meters carrying values beyond the registered cap |

The first test does not merely confirm meter count stays flat. It also confirms event counts are added to other, avoiding the trap of “capping succeeds” by dropping all measurements.

Do not assert processing duration against a fixed number. Execution duration depends on hardware and scheduling; what matters in the example is timer count and the exact tag set.

The required result is all three tests passing. Specific console/report formatting depends on Gradle and logging configuration, so do not treat a predicted Gradle log line as fixed stdout.

## 9. Run the API and inspect Prometheus output

### 9.1. Start a fresh process

```bash
./gradlew bootJar
java -jar build/libs/bounded-business-metrics.jar
```

On Windows, use `gradlew.bat bootJar`.

The application Java files require Spring Boot/Micrometer dependencies. The `java -jar` command runs the packaged executable JAR; do not run individual application classes with `javac` without setting the classpath.

Keep the process running and open another terminal. On Windows, use `curl.exe` if `curl` is shadowed by a PowerShell alias.

### 9.2. Send four intentional requests

On a freshly started process with no other checkout requests yet:

```bash
curl -i -X POST "http://127.0.0.1:8080/lab/checkout?channel=web&scenario=SUCCESS"
curl -i -X POST "http://127.0.0.1:8080/lab/checkout?channel=mobile&scenario=REJECTED"
curl -i -X POST "http://127.0.0.1:8080/lab/checkout?channel=batch&scenario=ERROR"
curl -i -X POST "http://127.0.0.1:8080/lab/checkout?channel=partner-42&scenario=SUCCESS"
```

Expectations:

| Request | HTTP status | Body |
| --- | --- | --- |
| web / SUCCESS | 201 | created |
| mobile / REJECTED | 422 | rejected |
| batch / ERROR | 500 | failed |
| partner-42 / SUCCESS | 201 | created |

Do not pass `--fail` in these commands so you can still read the status and body of the 422/500 branches. curl does not treat HTTP error statuses as connection failures on its own.

The bodies above are returned by the controller without trailing newlines added by code. Headers may contain dynamic data; do not treat the entire HTTP response as fixed stdout.

### 9.3. Check logical values after four requests

| Meter | Tags | Expected value |
| --- | --- | --- |
| business.orders.created | channel=web | count=1 |
| business.orders.created | channel=other | count=1 |
| business.orders.created | channel=mobile | count=0 |
| business.orders.created | channel=batch | count=0 |
| business.checkout.duration | channel=web, outcome=success | count=1 |
| business.checkout.duration | channel=mobile, outcome=rejected | count=1 |
| business.checkout.duration | channel=batch, outcome=error | count=1 |
| business.checkout.duration | channel=other, outcome=success | count=1 |

All remaining timers have count=0. Total observations recorded by the timer is 4; total successful orders is 2.

The failed attempt is measured under outcome=error rather than creating a tag containing an exception message. Channel `partner-42` is not exported verbatim; it is folded into other.

Read the exposition output:

```bash
curl -i http://127.0.0.1:8080/actuator/prometheus
```

Look for the corresponding exported names:

```text
business_orders_created_total
business_checkout_duration_seconds_count
business_checkout_duration_seconds_sum
```

Exported metric names differ from Micrometer names. Timers are exported in the exporter's base unit; the names above express seconds. Number formatting, line ordering, and additional labels may vary by exporter/configuration.

Do not predict a fixed value for duration sum. The simulated requests do not intentionally sleep, and execution duration depends on the environment.

Also verify that no `partner-42` tag value, order ID, or raw error string appears in this metric family. Calling the scrape endpoint does not increment the order-creation counter, because it does not invoke the checkout handler.

### 9.4. Check normalization and measurement boundaries

Try a channel with uppercase letters and whitespace:

```bash
curl -i -X POST --data-urlencode "channel= WEB " --data-urlencode "scenario=SUCCESS" http://127.0.0.1:8080/lab/checkout
```

This request must increment the existing `channel=web` series, without creating `channel=WEB` or a channel with spaces.

Try omitting channel:

```bash
curl -i -X POST "http://127.0.0.1:8080/lab/checkout?scenario=SUCCESS"
```

The empty default value maps to other.

If an invalid scenario is passed:

```bash
curl -i -X POST "http://127.0.0.1:8080/lab/checkout?channel=web&scenario=UNKNOWN"
```

The framework returns a parameter conversion error, typically 400 in this minimal lab configuration, before entering the service. The business timer does not increment for that request. Automatic HTTP metrics may still record the request; that is a different measurement.

After these extra requests, numbers no longer match the table for just the initial four requests. Record actual call counts or restart the process before repeating a scenario requiring exact counts.

## 10. Query with accurate semantics and units

The following examples assume Prometheus is already scraping the application. Job/instance names and infrastructure labels must match your system.

### 10.1. Successful order creation rate by channel

```promql
sum by (channel) (
  rate(business_orders_created_total[5m])
)
```

The result is successful events per second. This is not total checkout attempts, because the counter does not increment on rejected or error.

Apply `rate()` per series before summing to handle counter resets per instance. Do not sum counters across multiple instances first and assume the result behaves like a single non-resetting counter.

### 10.2. Checkout count by channel and outcome

```promql
sum by (channel, outcome) (
  rate(business_checkout_duration_seconds_count[5m])
)
```

Timer count includes outcomes recorded by the service. It excludes requests rejected before the service or incomplete operations.

### 10.3. Average duration by channel

```promql
sum by (channel) (
  rate(business_checkout_duration_seconds_sum[5m])
)
/
sum by (channel) (
  rate(business_checkout_duration_seconds_count[5m])
)
```

The result is in seconds. To display milliseconds, multiply by 1000 at the query/display layer.

When there is no traffic, the denominator can be 0 and the result may be NaN. Do not automatically interpret this as “processing time is 0” or “the exporter is broken.”

### 10.4. Error rate among processed checkouts

```promql
sum(
  rate(business_checkout_duration_seconds_count{outcome="error"}[5m])
)
/
sum(
  rate(business_checkout_duration_seconds_count[5m])
)
```

If the business also treats rejected as an outcome requiring separate tracking, build a separate ratio for rejected. Do not silently merge business rejections with technical errors if operational definitions distinguish them.

### 10.5. Unrecognized channel ratio

```promql
sum(
  rate(business_checkout_duration_seconds_count{channel="other"}[5m])
)
/
sum(
  rate(business_checkout_duration_seconds_count[5m])
)
```

Other keeps cardinality bounded with a trade-off: losing distinction among unknown values. A rising other ratio is a reason to inspect input data and taxonomy, not a reason to automatically emit every unknown string as a tag.

The `5m` windows are only examples. `rate()` needs enough samples relative to the scrape interval; one request just run and one scrape are not enough for rate queries to stabilize.

### 10.6. Percentiles require appropriate distribution data

Timer count and sum are not enough to reconstruct p95. With classic histograms appropriately enabled, you can use:

```promql
histogram_quantile(
  0.95,
  sum by (le, channel) (
    rate(business_checkout_duration_seconds_bucket[5m])
  )
)
```

The baseline lab configuration does not enable histograms for this timer, so do not expect bucket queries to return data automatically. Decide separately on histograms, value ranges, buckets, and series budget before enabling them.

Do not average per-instance p95 values to treat as system-wide p95. You cannot turn an average duration into a percentile merely by renaming the chart.

## 11. Calculate cardinality budget when scaling

Adding a tag dimension with N independent values can multiply combinations by N. For example, adding `payment_method` with 5 values to a 12-combination timer can expand it to 60 combinations.

This is the maximum per allowed values and valid combinations; not every data model actually materializes the full Cartesian product. Specifically, pre-registration in this lab creates all designed combinations.

The budget must account for:

- Number of tag sets per metric family.
- Number of series generated per meter/exporter type.
- Number of scraped targets/replicas.
- Added infrastructure labels or common tags.
- Number of distinct label sets accumulated over the retention window.

With classic histograms, if each combination exports B buckets, where B already includes the +Inf bucket, then buckets plus count and sum produce B+2 series per combination. Some exporters add other series too; do not treat B+2 as a universal complete formula across all configurations.

Do not apply this exact bucket formula blindly to native histogram or summary implementations. You must know the actual data type chosen.

Tags to avoid in aggregated business metrics:

| Value | Why unsuitable? | Better place when investigating |
| --- | --- | --- |
| orderId, requestId, traceId | Nearly grows per event | Logs or traces with proper access/retention policy |
| userId, email | High cardinality and may contain personal data | Controlled investigation stores |
| Full URL or query string | Contains continuously changing IDs/parameters | Route templates or properly sanitized logs |
| Exception message | Unstable, may contain input data | Structured logs; error tags use only a finite taxonomy |
| Free-form partner name | Value set can expand unexpectedly | Approved finite catalog or other |

Hashing userId/email does not reduce the number of distinct values. Nor is it by itself sufficient anonymization for every purpose; do not use hashing as a cardinality fix.

Limiting tag character length does not equal limiting value count. One million short strings are still one million distinct values.

If the system uses common tags such as region/service, verify they also have controlled value sets and do not collide with business tag names. The example's filters protect only the configured dimensions; they do not govern every other dimension across the system.

## 12. Common implementation pitfalls

### Attaching raw tags hoping the exporter caps them

Micrometer/Prometheus cannot guess that a string is an “ID that should not be used.” Normalization must happen before meter registration. Additional registry limits cannot replace semantic design.

### Registering the same name with different tag key sets

A metric family having `channel` in one place and `channel+userId` in another can cause conflicts or an inconsistent data model. Keep schemas stable and check registry registration warnings.

### Confusing denied meters with events folded into other

A deny filter blocks new meters; it does not reroute events to another meter. To keep total event counts under the other group, normalization must occur in the recorder, as the tests verified.

### Recording the timer twice or missing exception branches

Stopping in both catch and finally can record one execution multiple times. Stopping only on the success path drops errors and biases average duration.

### Counting success before actual success

In the simulation, the success point is trivial. In a real service, align with transactions, async work, retries, and post-commit callbacks. Do not place increment merely because “the request was received.”

### Creating dynamic metric names to avoid tags

Names like `business.checkout.partner_123` still create a data-driven set of meters. Budgets must govern both metric names and tags.

### Checking only meter count, not event totals

A filter denying everything keeps meter count from growing while losing all observability data. Tests must verify accurate counts across valid groups.

### Folding into other without watching the other ratio

An overly large other bucket can hide input drift or mapping bugs. Watch the ratio and investigate with suitable logs/traces; add values to the catalog only when there is clear business need and budget.

### Treating tag bounds as HTTP input validation

Cardinality normalization does not replace validation of request length, format, or business rules. A huge raw string can still consume CPU/memory during parsing and normalization, even if the final tag is just other.

## 13. Completion criteria

The lab meets requirements when there is complete evidence for:

1. Both metric families are clearly defined: counter counts successes, timer counts and measures all outcomes handled in the service.
2. Channel emits only web/mobile/batch/other; outcome emits only success/rejected/error.
3. Uppercase, whitespace, and unknown inputs are normalized properly.
4. Test with 1,000 raw values creates no extra meters and adds all events to other.
5. Rejected/error branches are recorded once by the timer without incrementing the success counter.
6. Filters block extra registrations exceeding the designed budget.
7. The four live lab requests produce exact counts matching the table; durations are not compared against an assumed value.
8. Exposition output contains no IDs, exception messages, or raw unlisted channels.
9. Queries use the right exported names, units, and windows with sufficient samples.
10. When adding tag dimensions/histograms/replicas, the budget is recalculated and per-layer bounds remain clear.

After testing, stop the local process. When transferring this pattern to a real application, remove the simulation's scenario selector and wire instrumentation to real business outcomes.

A finite tag set is a data contract: it keeps metrics aggregatable, comparable, and operable over the long term. The recorder, registry guards, and count tests must all protect that contract together.
