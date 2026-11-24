# Designing Business Metrics with Clear Names, Units, and Scoped Tags

## 1. Start from the Business Question

Actuator can tell you whether the application is still running, whether CPU is busy, or whether an API responds slowly. That data does not yet answer questions such as:

- How many order creation attempts ended with a system error?
- How long does handling an order creation attempt usually take?
- How many new orders were actually saved successfully?
- How does the number of items per order differ between web and mobile applications?

A **business metric** is a measurement of an event or state that is meaningful to product operations. It is interpreted using specific business rules, rather than merely describing technical resources.

For example, `http.server.requests` measures HTTP requests; it does not inherently know whether a request created a new order, returned an existing order due to deduplication, or merely placed work into a queue.

In Micrometer, a **meter** is the object that collects measurements; a **MeterRegistry** manages meters. A **tag** is a key–value pair used to group data. A time series in a monitoring system is bound to a specific combination of labels; a single meter can produce multiple series, such as the sample count and total time of a timer. See [Micrometer — Meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html).

We proceed in order:

```text
Question to answer
        ↓
Event/state and measurement boundary
        ↓
Meter type, unit, and name
        ↓
Tags with a finite value set
        ↓
Recording point in the application
        ↓
Querying, verification, and operations
```

If you have not agreed on “what a success means,” clarify the definition before adding a `Counter`.

## 2. Write a Measurement Contract

A **measurement contract** records the shared meaning understood by the code author, the dashboard reader, and the alert author. A contract does not have to be a tool-specific format; a short table in the project documentation is already useful.

| Component | What to clarify |
| --- | --- |
| Question | What decision will be based on this measurement? |
| Subject | Calls, attempts, orders, items, or balances? |
| Start/end points | Measured from when to when? Recorded at which step? |
| Scope | One instance, one service, one tenant, or the entire system? |
| Meter type | Counting events, measuring duration, observing state, or value distribution? |
| Unit | Requests, seconds, bytes, items, or a specific currency unit? |
| Name and description | Is there enough context when viewing the name alone? |
| Tags | Which keys are always present? What are the valid values and limits? |
| Retry/deduplication | Count attempts or unique outcomes? |
| Querying approach | Rate, ratio, sum, or percentile over what time window? |
| Owner | Which team maintains the definition and handles changes? |

The running example throughout this lesson is the order creation flow at the checkout step. We define:

1. **A checkout submission attempt** begins when the application service receives the call and ends when that attempt has an outcome. Outcomes belong to `success`, `business_rejected`, or `system_error` in the illustrative model.
2. **A newly committed order** is counted only after the transaction creating the new order has been confirmed as committed.
3. **Order item count** is the total product quantity, not the number of line items. An order with two lines of quantities 2 and 3 is recorded as 5.
4. The intake channel is normalized to `web`, `mobile`, or `other`.

A real system might also need a `replayed` outcome for deduplicated requests. In that case, the definition and instrumentation code must be extended together: returning an existing order must not increment the new-order count.

### 2.1. Separate Business Events from Technical Execution Counts

A single order can generate:

```text
1 purchase intent
→ 2 HTTP submissions due to user retries
→ 3 payment service calls due to internal retries
→ 1 newly committed order
```

All of these numbers can be accurate because they measure different subjects. The mistake is naming all four as “order count.”

- To know processing load: measure calls or attempts.
- To know final effectiveness: measure confirmed business outcomes.
- To know whether calling a partner is healthy: measure each partner call.
- To count unique customers/orders accurately: use an appropriate data source and reconciliation mechanism; do not infer it by summing all calls.

The number of attempts finishing within a time window does not necessarily equal the number of attempts starting in that same window because work may still be in flight. Reconciliation relationships must account for window boundaries and incomplete state.

### 2.2. Metrics Do Not Replace a Business Ledger

Recording a meter and committing to a DB are two separate operations. Incrementing a counter before commit can count rolled-back transactions. Incrementing after commit can still miss events if the process stops between the commit and the recording call.

Therefore, these metrics serve operational observability, trend detection, and alerting. Official revenue reporting, payment reconciliation, or exact order counts must rely on durable data with deduplication rules. Publishing events via an outbox can support a more reliable design, but it does not automatically turn every counter increment into an exact unique-counting mechanism.

## 3. Choose the Right Meter for the Quantity

| Question | Appropriate meter | Value recorded |
| --- | --- | --- |
| How many new orders committed? | `Counter` | Increments by one for each valid event |
| How long does a checkout submission take? | `Timer` | Duration of a completed attempt |
| How many items does each order have? | `DistributionSummary` | Item count of each new order |
| How many attempts are currently in flight? | `Gauge` | In-flight count at sampling time |
| How long have long-running jobs been running? | `LongTaskTimer`, when needed | Currently active jobs |

`Counter` is for monotonically increasing cumulative quantities. When an order is canceled, do not decrement the “orders ever created” counter; you can record a separate “order canceled” event. If you want to observe the number of currently open orders, that is a current state that can increase or decrease, suited for a gauge backed by an appropriate data source.

`Timer` already tracks the count of measured events. Do not add a counter solely to count the exact same attempts that the timer already records. However, a “newly committed orders” counter is still meaningful on its own because it is a different event from “completed checkout submission.” Similarly, a summary has a sample count and a total value; the sample count of the items summary is the number of orders measured, while the total is the total item quantity.

See [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html) and [Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html).

A gauge reflects only what is observed at sampling time. If the in-flight count rises and falls between two scrapes, the chart can miss the spike. When creating a gauge on a state object, the application must keep that object alive and update it properly; registering an immutable value does not produce a self-updating measurement.

Refer to [Micrometer — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html).

In the following examples, we implement the timer, counter, and summary. A gauge is a separate option when the application needs to track work currently in progress.

## 4. Name by Meaning, Keep Units Consistent

### 4.1. One Name Describes One Quantity

In Micrometer code, use lowercase with dot-separated segments. Names should carry domain context, subject, and event/quantity:

| Name | Interpretation |
| --- | --- |
| `checkout.submissions` | Timer for completed checkout submissions |
| `checkout.orders.committed` | Counter for newly committed orders |
| `checkout.order.items` | Summary for item count of each new order |
| `checkout.inflight` | Gauge for in-flight attempts, if implemented |

There is no single mandatory keyword across every organization; what matters is that names and descriptions match the contract consistently.

Names like `count`, `success`, `business.metric`, or `process.time` lack subject and scope. Method-bound names such as `OrderService.save.call` can be brittle during refactoring and do not clearly express the business event.

Do not create separate names per channel like `checkout.web.submissions` and `checkout.mobile.submissions` if they share the same meaning. Keep one name `checkout.submissions` and use a `channel` tag. Conversely, do not merge “checkout submission” and “payment gateway call” under the same name just because both are calls.

A meter description helps clarify the recording point, but it cannot rescue a name that mixes incompatible quantities. Refer to [Micrometer — Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html).

### 4.2. Units Are Part of the Contract

| Quantity | How to handle |
| --- | --- |
| Duration | Use `Timer`, recording with `Duration` or a value paired with `TimeUnit` |
| Data size | Standardize on bytes; you can declare `baseUnit("bytes")` |
| Item count | Specify clearly whether it is total quantity or line count; use `baseUnit("items")` for summary |
| Ratio | Choose 0–1, do not mix with 0–100 |
| Money | Specify the currency and smallest or major unit; do not sum different currencies |

Declaring `baseUnit` for a general measurement does not mean Micrometer automatically knows how to convert 1,000 milliseconds into one second. For durations, `Timer` is unit-aware via its API; for size or money, normalizing the input number remains the application's responsibility.

For example, `record(120, TimeUnit.MILLISECONDS)` and `record(Duration.ofMillis(120))` both express 120 ms. Do not use a summary to record `120` and merely set `baseUnit("seconds")` expecting the system to convert it automatically.

A timer may be exported in different base units depending on the registry; Prometheus typically uses seconds. See [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

If measuring payment amounts and refund amounts, separate positive event streams for payments and refunds. Do not decrement a payment counter to represent a refund. Metrics use floating-point numbers and do not replace exact financial arithmetic in business systems.

### 4.3. Code Names and Exported Names May Differ

Micrometer translates names according to the conventions of the receiving backend. The name `checkout.submissions` is used when querying `MeterRegistry` and the metrics endpoint; with Prometheus, a timer typically produces series such as `checkout_submissions_seconds_count` and `checkout_submissions_seconds_sum` in the Micrometer 1.13 line.

When naming in code, do not manually append `_total`, `_count`, or `_seconds` in a way that duplicates suffixes generated by the exporter. The final exported name also depends on the meter type, unit, and registry configuration; inspect the actual endpoint before writing dashboards.

Backend naming rules do not fully match code naming rules. [Prometheus — Metric and label naming](https://prometheus.io/docs/practices/naming/) explains why exported names should express units and why unbounded-domain labels must be avoided.

## 5. Tags Answer Grouping Questions, Not Individual Transaction Identification

For `checkout.submissions`, the two tags are:

| Key | Value domain | Purpose |
| --- | --- | --- |
| `channel` | `web`, `mobile`, `other` | Compare intake channels |
| `outcome` | `success`, `business_rejected`, `system_error` | Separate processing outcomes |

Keys and values must be normalized. `WEB`, `Web`, and `web ` must not accidentally become three groups if all mean “web.” Data outside the allowed set is mapped to `other`; unknown values should be investigated in logs or in a separate bounded measurement.

Keep the key set consistent **within the same meter family**: every `checkout.submissions` timer has both `channel` and `outcome`, even for groups with no data yet. The `checkout.orders.committed` counter may only need `channel` because it is a different meter family.

Values such as `orderId`, `requestId`, `traceId`, email addresses, exception messages, or URLs with arbitrary parameters are unsuitable as tags for individual transactions. Put them in logs/tracing when detailed lookup is needed. Hashing IDs only changes the representation; each distinct ID still produces a distinct tag value.

Each meter is identified by its name and tag set. Changing a tag value when recording does not “update the label of an existing meter,” but rather looks up or creates a different meter. Therefore:

```text
channel=web, outcome=success
channel=web, outcome=system_error
```

are two meters of the same family, serving two different outcome groups.

### 5.1. Budget Tag Combinations Before Implementation

With three channels and three outcomes, the timer has at most:

```text
3 channels × 3 outcomes = 9 meter combinations per instance
```

If two payment methods are added:

```text
3 × 3 × 2 = 18 combinations
```

Assuming 20 instances, timer count and sum alone can already produce around `18 × 20 × 2 = 720` series in the backend; max, buckets, additional labels, and instance churn will change the actual count further.

This is an estimate based on potential combinations, not an exact formula for every registry. Histograms typically multiply the cost further because each bucket also generates data. A tag with few values on its own can still cause many combinations when combined across multiple dimensions.

Before adding a tag, answer:

1. Is there a specific query or decision that requires this dimension?
2. Can the value domain be enumerated and bounded?
3. Do you truly need to group every meter by this dimension?
4. Does aggregating without that dimension still make sense?
5. Is the cost across all instances and retention period acceptable?

Do not add `tenant` to every metric out of habit. A few tenants today can become tens of thousands of tenants later; when detailed per-customer analysis is needed, a business analytics system may be more appropriate.

### 5.2. Distinguish Business Tags from Environment Tags

`channel` and `outcome` describe the event. `application`, `environment`, or `region` describe where the application runs.

In Spring Boot, common tags can be configured, for example:

```yaml
management:
  metrics:
    tags:
      application: checkout-service
      environment: local
```

These are tags with fixed values per deployment. Do not put per-request changing data into registry common tags.

The backend may already add labels such as `job` and `instance` during scraping. Check existing conventions to avoid name collisions or label shadowing. Adding common tags must happen before meters are registered; in Boot, use configuration or a `MeterRegistryCustomizer` instead of mutating the registry late from a request handler.

## 6. Standalone Java 17 Example with Micrometer

The example records four known outcomes using simulated durations so stdout is deterministic. It verifies meter structure, names, units, and tags; it does not benchmark machine speed and does not perform DB transactions.

In this illustrative model, `success` means creating a newly committed order. It does not simulate deduplicated requests, post-commit timeouts, or errors occurring while sending a response to the customer. In an application with those cases, the commit event and the attempt outcome must be recorded at their respective points rather than inferred from a single outcome variable.

Create a standalone Gradle project with the following three files.

`settings.gradle`:

```groovy
rootProject.name = 'business-metrics-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'io.micrometer:micrometer-core:1.13.0'
}

application {
    mainClass = 'BusinessMetricsDemo'
}
```

Version `1.13.0` keeps the standalone example reproducible on the Micrometer line used alongside Spring Boot 3.3. For a Boot application, prefer the version managed by the application's BOM instead of copying this version to override it.

File `src/main/java/BusinessMetricsDemo.java`:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Duration;
import java.util.EnumMap;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

public class BusinessMetricsDemo {
    public enum Channel {
        WEB, MOBILE, OTHER;

        public String tag() {
            return name().toLowerCase(Locale.ROOT);
        }

        public static Channel from(String raw) {
            String value = raw == null ? "" : raw.trim().toLowerCase(Locale.ROOT);
            return switch (value) {
                case "web" -> WEB;
                case "mobile" -> MOBILE;
                default -> OTHER;
            };
        }
    }

    public enum Outcome {
        SUCCESS, BUSINESS_REJECTED, SYSTEM_ERROR;

        public String tag() {
            return name().toLowerCase(Locale.ROOT);
        }
    }

    public static final class CheckoutMetrics {
        private final EnumMap<Channel, EnumMap<Outcome, Timer>> submissions =
                new EnumMap<>(Channel.class);
        private final EnumMap<Channel, Counter> committed =
                new EnumMap<>(Channel.class);
        private final EnumMap<Channel, DistributionSummary> orderItems =
                new EnumMap<>(Channel.class);

        public CheckoutMetrics(MeterRegistry registry) {
            for (Channel channel : Channel.values()) {
                EnumMap<Outcome, Timer> byOutcome = new EnumMap<>(Outcome.class);
                for (Outcome outcome : Outcome.values()) {
                    byOutcome.put(outcome, Timer.builder("checkout.submissions")
                            .description("Completed checkout submission latency")
                            .tags("channel", channel.tag(), "outcome", outcome.tag())
                            .register(registry));
                }
                submissions.put(channel, byOutcome);
                committed.put(channel, Counter.builder("checkout.orders.committed")
                        .description("New orders whose creation transaction committed")
                        .tag("channel", channel.tag())
                        .register(registry));
                orderItems.put(channel, DistributionSummary.builder("checkout.order.items")
                        .description("Item units in each newly committed order")
                        .baseUnit("items")
                        .tag("channel", channel.tag())
                        .register(registry));
            }
        }

        public void recordResult(
                Channel channel, Outcome outcome, Duration duration, int items) {
            Objects.requireNonNull(channel);
            Objects.requireNonNull(outcome);
            Objects.requireNonNull(duration);
            if (duration.isNegative()
                    || (outcome == Outcome.SUCCESS && items <= 0)
                    || (outcome != Outcome.SUCCESS && items != 0)) {
                throw new IllegalArgumentException("Invalid completed result");
            }

            submissions.get(channel).get(outcome).record(duration);
            if (outcome == Outcome.SUCCESS) {
                committed.get(channel).increment();
                orderItems.get(channel).record(items);
            }
        }
    }

    public static void main(String[] args) {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            CheckoutMetrics metrics = new CheckoutMetrics(registry);
            metrics.recordResult(
                    Channel.from("WEB"), Outcome.SUCCESS, Duration.ofMillis(120), 2);
            metrics.recordResult(
                    Channel.from("web"), Outcome.BUSINESS_REJECTED, Duration.ofMillis(40), 0);
            metrics.recordResult(
                    Channel.from("mobile"), Outcome.SYSTEM_ERROR, Duration.ofMillis(80), 0);
            metrics.recordResult(
                    Channel.from("web"), Outcome.SUCCESS, Duration.ofMillis(160), 5);

            long completed = registry.find("checkout.submissions").timers()
                    .stream().mapToLong(Timer::count).sum();
            Timer webSuccess = registry.get("checkout.submissions")
                    .tags("channel", "web", "outcome", "success").timer();
            DistributionSummary webItems = registry.get("checkout.order.items")
                    .tag("channel", "web").summary();

            System.out.println("completed=" + completed);
            System.out.println("web.success.count=" + webSuccess.count());
            System.out.println("web.success.totalMs="
                    + Math.round(webSuccess.totalTime(TimeUnit.MILLISECONDS)));
            System.out.println("web.business_rejected.count="
                    + registry.get("checkout.submissions")
                    .tags("channel", "web", "outcome", "business_rejected").timer().count());
            System.out.println("mobile.system_error.count="
                    + registry.get("checkout.submissions")
                    .tags("channel", "mobile", "outcome", "system_error").timer().count());
            System.out.println("web.orders.committed="
                    + Math.round(registry.get("checkout.orders.committed")
                    .tag("channel", "web").counter().count()));
            System.out.println("web.order.items.total=" + Math.round(webItems.totalAmount()));
            System.out.printf(Locale.ROOT, "web.order.items.mean=%.1f%n", webItems.mean());
            System.out.println("meter.ids=" + registry.getMeters().size());
        } finally {
            registry.close();
        }
    }
}
```

Run with Gradle 8.x and JDK 17 installed:

```bash
gradle -q run
```

If the project has a Gradle Wrapper, replace `gradle` with `./gradlew` on Linux/macOS or `.\gradlew.bat` on Windows. The first run requires downloading dependencies from Maven Central.

Stdout:

```text
completed=4
web.success.count=2
web.success.totalMs=280
web.business_rejected.count=1
mobile.system_error.count=1
web.orders.committed=2
web.order.items.total=7
web.order.items.mean=3.5
meter.ids=15
```

### 6.1. Verify the Values Yourself

- Four processing attempts completed, so the total count across the timers is 4.
- Two successful web attempts took 120 ms and 160 ms: count is 2, total time is 280 ms.
- One web business-rejected attempt and one mobile system-error attempt are recorded in two separate groups.
- Only the two successful outcomes in this model create new orders: the web channel counter is 2.
- The two new orders have 2 and 5 items respectively: the summary has a total of 7 and a mean of 3.5.
- There are 9 timers, 3 counters, and 3 summaries, totaling 15 meter IDs; this is not the number of Prometheus series that will be exported.
- `Channel.from` produces only the three known tag values. Unknown inputs do not create a separate meter per input string.

The meters are pre-registered over finite enum sets, so groups with no events yet also appear in the registry with an initial count of 0. This approach suits a small number of combinations; do not pre-register millions of combinations just to avoid missing values.

The `recordResult` method assumes each outcome is passed to it exactly once. Calling it again with the same outcome still increments the metrics; the snippet has no mechanism to recognize an already-recorded transaction.

### 6.2. Why Use Both a Timer and a Counter Here?

The timer answers “how many processing attempts completed and how long did they take.” The counter answers “how many new orders committed.” When retries, deduplication, or multi-step processing exist, the two quantities can differ.

Do not add the timer's count to the counter to find a “business total.” They are not two disjoint parts of a single sum. If you need a counter solely to duplicate the timer's count, reconsider whether it is necessary.

## 7. Bring the Design into a Spring Boot Application

In a Boot application with Actuator, use the Spring-managed `MeterRegistry`. You can extract the `CheckoutMetrics` class and enums from the example into files in an application package, then register the metrics object as a bean.

The configuration snippet below illustrates using the nested class directly if it is placed in the same package as the configuration:

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CheckoutMetricsConfiguration {
    @Bean
    public BusinessMetricsDemo.CheckoutMetrics checkoutMetrics(
            MeterRegistry registry) {
        return new BusinessMetricsDemo.CheckoutMetrics(registry);
    }
}
```

The snippet above is configuration inside a Boot application that already has the corresponding `BusinessMetricsDemo` class; it is not a standalone `main` program. In a real project, you can name and split classes according to your project's package structure.

Do not create `new SimpleMeterRegistry()` inside a production service and expect Actuator to automatically see that private registry. `SimpleMeterRegistry` in the example is only for simple in-memory experiments.

Also do not rely on static methods on `Metrics` in place of the injected registry when you need to ensure Spring's configuration, filters, and exporters are applied. See [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 7.1. Choose the Right Recording Point in the Business Flow

A realistic sequence might be:

```text
Receive call
  → start timing sample
  → validate business conditions
  → execute transaction
  → commit confirmed
  → record new order event and item count
  → finish processing attempt, record timer by outcome
```

Do not increment the new-order counter immediately after `repository.save(...)` if the transaction can still roll back. With declarative `@Transactional` transactions, returning from the method body does not always mean the commit has finished at the moment code inside that method is running. The recording point must align with the transaction boundary, such as after the proxied call completes if that is the outermost transaction boundary, or in a properly designed post-commit callback. If the method participates in an outer transaction, wait for that outer transaction to commit. See [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html).

If the commit succeeds but responding to the client fails, “newly committed order” and “how the call ended” must be expressed independently. That is why the combined `recordResult` method is only a simplified model for experimentation.

The duration of a synchronous attempt is typically measured with `Timer.Sample` and stopped once the outcome is known. With `CompletableFuture` or reactive flows, attach the stop point to the true completion signal rather than stopping the timer immediately upon returning the asynchronous object. Details for errors, cancellation, and retries must follow the measurement contract.

### 7.2. Protect the Tag Budget with MeterFilter

Prefer bounding data right at the recording point as in `Channel.from`. You can add a registry protection layer:

```java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsBudgetConfiguration {
    @Bean
    public MeterFilter checkoutChannelLimit() {
        return MeterFilter.maximumAllowableTags(
                "checkout.", "channel", 3, MeterFilter.deny());
    }
}
```

This filter applies to meters whose names start with `checkout.` and caps the number of `channel` values it accepts. It does not determine on behalf of business logic that the three values must be `web`, `mobile`, `other`; value mapping is still required.

When registration is denied, Micrometer may return a no-op (NOOP) meter. Thus the filter protects resources but can cause lost measurements if data exceeds the contract. Do not treat this as a mechanism to bucket all excess values into `other`, nor expect it to automatically remove meters that were already registered earlier.

Filter order matters; an early accepting filter can affect subsequent checks. See [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html). In Boot, `MeterFilter` beans are applied to the Spring-managed registry.

## 8. Inspect Measurements via Actuator Before Creating Dashboards

If the application already has the web starter, Actuator starter, and Prometheus registry, a local experiment configuration might be:

```yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    tags:
      application: checkout-service
      environment: local
```

This is configuration for a Boot application, not for the standalone `SimpleMeterRegistry` program. Merge it with your existing configuration and avoid creating duplicate `management` keys. Actual access permissions still depend on application security and deployment network settings.

Call the following endpoints after the application has recorded events:

```bash
curl "http://127.0.0.1:8081/actuator/metrics/checkout.submissions"
curl "http://127.0.0.1:8081/actuator/metrics/checkout.submissions?tag=channel:web&tag=outcome:success"
curl "http://127.0.0.1:8081/actuator/metrics/checkout.orders.committed?tag=channel:web"
curl "http://127.0.0.1:8081/actuator/metrics/checkout.order.items?tag=channel:web"
curl "http://127.0.0.1:8081/actuator/prometheus"
```

On PowerShell, you can use `curl.exe` if `curl` is an alias for another command.

Check:

- Do the names and tag sets match the contract?
- Does the timer have appropriate `COUNT` and `TOTAL_TIME`? Read `baseUnit` instead of assuming total time is always in ms.
- The summary's count is the number of recorded orders; `TOTAL` is the item count in the declared unit.
- Does the tag filter actually select the intended group?
- Is a group with no events a meter with count 0, or does it not exist at all?
- Does the Prometheus exported name have the unit/suffix expected by your planned queries?

When omitting tag filters, the metrics endpoint may sum the measurements of multiple matching meters. That aggregation is only useful if the groups share the same quantity and unit. Do not use an aggregated result to claim every channel is healthy.

## 9. Design Queries Alongside the Measurement

The queries below illustrate typical Micrometer 1.13 exported names for Prometheus. Use them only after verifying against the actual endpoint.

### 9.1. New Order Creation Rate

```promql
sum by (channel) (
  rate(checkout_orders_committed_total{
    application="checkout-service"
  }[5m])
)
```

The result is the number of newly committed orders per second over the calculation window, not the all-time total order count.

A counter grows cumulatively over the process lifetime; instance restarts can reset the count back to start. Use functions designed for counters and preserve per-series reset handling before aggregating. Refer to [Prometheus — Query functions](https://prometheus.io/docs/prometheus/2.55/querying/functions/).

### 9.2. System Error Rate Among Completed Attempts

```promql
sum by (channel) (
  rate(checkout_submissions_seconds_count{
    application="checkout-service",
    outcome="system_error"
  }[5m])
)
/
sum by (channel) (
  rate(checkout_submissions_seconds_count{
    application="checkout-service"
  }[5m])
)
```

The denominator here is **all completed attempts**, including business rejections. If you want the error rate only among business-eligible attempts, the denominator must change and the dashboard title must express that accurately.

When the denominator is 0 or a series is missing, an undefined/no-data result does not mean a 0% error rate. Configure how this case is handled proactively.

### 9.3. Average Duration of Successful Attempts

```promql
sum by (channel) (
  rate(checkout_submissions_seconds_sum{
    application="checkout-service",
    outcome="success"
  }[5m])
)
/
sum by (channel) (
  rate(checkout_submissions_seconds_count{
    application="checkout-service",
    outcome="success"
  }[5m])
)
```

The result unit is seconds for the series above. This is a weighted average by attempt count. Do not take a simple average of each instance's average duration when their traffic volumes differ.

An average does not describe the tail of the distribution. If you need multi-instance aggregated p95/p99, design histograms and bucket budgets from the start; do not sum or average percentiles computed separately on each instance.

### 9.4. A Ratio Is Only Meaningful When Numerator and Denominator Are Compatible

“New orders / HTTP submissions” can change due to retries or deduplication, even when the system has no errors. “Successful payments / partner calls” measures per-attempt effectiveness; “successfully paid orders / orders requiring payment” measures the final outcome. The two ratios serve two different purposes.

Numerator and denominator must share the same service scope, window, filter conditions, and subject definition. If the data comes from different stages, you must also account for latency between those stages.

## 10. Keep Definitions Stable as the System Evolves

A metric is a contract interface between code and operators. Changing its meaning while keeping the same name can make dashboards look continuous even though data from the two periods is no longer comparable.

For example, `checkout.orders.committed` initially counts new orders; later it is changed to count every order return, including deduplicated replays. A rising chart might not reflect real sales or traffic growth, but merely a definition change.

When making changes:

1. Determine whether the subject, unit, recording point, or outcome set changes.
2. If the meaning is no longer compatible, choose a new name/contract and update queries.
3. When running both in parallel for reconciliation, set a clear migration deadline.
4. While multiple versions run simultaneously, avoid mixing the two definitions or double-counting two names for the same goal.
5. Retire the old meter and old queries on schedule after verification.

Changing the unit from VND to thousands of VND without updating the contract is a serious error even if the Java data type does not change. Similarly, changing `channel=mobile` to `channel=app` creates a new data group; do not assume it is merely renaming a display label on the dashboard.

With the same name and tags, the registry typically reuses the already-registered meter. Do not rely on re-registering with a different description, meter type, or unit to change a definition safely. Catch conflicts during configuration checks and data verification.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Naming a metric `success` | Unclear which operation succeeded | Add business domain, event, and description |
| Incrementing “orders created” before commit | Counts rolled-back transactions | Record at the appropriate commit boundary |
| Counting retries as multiple new orders | Wrong subject measured | Separate attempts from unique outcomes |
| Timer and counter both counting the exact same event | Redundant data, prone to recording-point drift | Use the timer's count when it fits the goal |
| Mixing ms and seconds | Values off by orders of magnitude | Use unit-aware APIs and verify exported values |
| Using `orderId` or email as a tag | Unbounded combination growth | Keep detailed identifiers in logs/tracing |
| Hashing an ID and still using it as a tag | Does not reduce the number of distinct values | Map to meaningful finite groups |
| Not normalizing input values | One channel splits into multiple groups | Define an allowed value set and a fallback value |
| Creating a private registry in a service | Actuator/exporters miss the expected metrics | Use the Spring-managed registry |
| Using a counter for open order count | Cannot properly represent increases and decreases | Use a gauge backed by appropriate state |
| Treating a counter total as an exact financial figure | Ignores resets, dropped samples, and duplicate events | Reconcile against durable business data |
| Checking only that code runs without errors | Measurement meaning can still be wrong | Use clear input fixtures and expected outputs |

## 12. Design and Verification Exercises

1. Write a contract for the question “how many payment attempts were declined.” Distinguish partner declines, invalid business conditions, and connection errors.
2. Given a transaction with three partner call attempts but only one final payment outcome, list the meters to increment and their increments; do not use a single counter for both concepts.
3. In the Java example, add a `BUSINESS_REJECTED` outcome on the mobile channel with a duration of 60 ms. Before running, predict the total attempts, new orders, total items, and number of meter IDs.
4. Pass the channel `"new-user-channel-123"` through `Channel.from`. Explain why the number of meter IDs remains bounded and which group receives the data.
5. Calculate the budget for four channels, five outcomes, three payment method types, and 30 instances. State clearly the difference between meter combination count and series count when histograms are enabled.
6. Design a refund amount metric: specify the currency, unit, sign of the value, and why different currencies must not be summed together.
7. Propose how to migrate a metric currently counting “order creation calls” to a metric counting “newly committed orders,” including names, transition phase, and queries that need updating.

A design is satisfactory when someone else can read the name, unit, tags, and description and know **exactly what is being measured, where it is recorded, which groups can be aggregated, and what limitations apply**.
