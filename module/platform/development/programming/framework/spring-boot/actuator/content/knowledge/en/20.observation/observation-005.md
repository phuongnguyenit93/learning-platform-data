# Distinguishing Low-Cardinality and High-Cardinality Key-Values

## 1. One Operation Needs Two Levels of Information

Suppose an application processes orders. Operators want to know:

- How do the WEB and MOBILE channels differ in processing count, latency, and error rate?
- Which steps did the specific order `demo-102` go through?

The first question requires **grouping executions** into a small set of stable groups. The second question requires **details of a single execution**. If both levels of information are put into metric tags in the same way, the number of groups can grow with the number of orders.

Micrometer Observation distinguishes two groups of key-values to express this intent:

| Group | Design meaning | Example |
| --- | --- | --- |
| Low cardinality | A small, bounded, and controlled value set, suitable for grouping metrics | `channel=WEB`, `result=SUCCESS` |
| High cardinality | Diverse values or values that can keep growing with real data, serving investigative detail | `order.id=demo-102`, per-request ID |

A **key-value** is a name-and-value pair, such as key `channel` and value `WEB`. In metrics terminology, these pairs are often called tags or labels. "Low" and "high" refer to **the number of distinct values that can appear**, not string length.

In Spring Boot 3.3's standard Observation integration, low-cardinality key-values are used for both metrics and traces; high-cardinality key-values only flow to traces in this mechanism. Creating and exporting traces still requires an appropriately configured tracing system. See [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

## 2. Understand Cardinality Before Choosing the API

### 2.1. Counting Distinct Values

With a sequence of values for `channel`:

```text
WEB, WEB, MOBILE, WEB, MOBILE
```

there are five occurrences, yet only **two distinct values**. The observed cardinality in this data is 2.

With `order.id`:

```text
demo-101, demo-102, demo-103, demo-104, demo-105
```

there are five distinct values. As the number of orders grows, the value set can keep growing; there is no small, stable list the application commits to keeping.

A long UUID string is not the only cause of high cardinality. Short codes like `A1`, `A2`, `A3`... can still produce very many values. Conversely, the string `PAYMENT_AUTHORIZATION_REJECTED` is fairly long yet may belong to a small set of predefined outcome codes.

### 2.2. A Small Snapshot Is Not Enough to Conclude

Having only three users today does not make `user.id` a good low-cardinality tag. You must evaluate the **potential value domain and rate of new value generation** over the application's lifetime.

Likewise, saying "there are only finitely many values" is not enough. A catalog with millions of products is still far too large for many metric-grouping goals, even though that catalog is mathematically finite.

There is no single threshold like "under 100 is always low" that holds true for every system. The decision also depends on:

- Number of combinations with other tags.
- Number of metrics carrying that same tag set.
- Number of instances and how the storage system distinguishes instances.
- Histogram configuration, retention period, and query cost.
- The actual operational question that needs answering.

### 2.3. The API Is a Declaration by the Code Author

`lowCardinalityKeyValue` does not inspect the contents and verify on its own that the value has low cardinality. If you pass an order ID into it, the library may still use that ID as a metric grouping dimension.

`highCardinalityKeyValue` is also neither a detector nor a data-encryption mechanism. It declares how metadata should be classified for matching handlers. The instrumentation author is responsible for choosing the right group.

The [Micrometer Observation 1.13](https://docs.micrometer.io/micrometer/reference/1.13/observation/introduction.html) documentation uses an HTTP path containing an entity ID versus a templated route to illustrate the difference between a data-driven domain and a bounded domain.

## 3. Why Does This Decision Directly Affect Metrics?

### 3.1. Each Tag Combination Creates a Distinct Measurement Identity

Consider the metric `order.lookup`. With the `channel` tag, two combinations can be:

```text
order.lookup{channel=WEB}
order.lookup{channel=MOBILE}
```

Two WEB calls can contribute together into one WEB timer. Adding `order.id` as a tag turns the identities into:

```text
order.lookup{channel=WEB, order.id=demo-101}
order.lookup{channel=WEB, order.id=demo-102}
order.lookup{channel=MOBILE, order.id=demo-103}
```

This notation illustrates identity, not a mandatory export format for every backend. For metrics, the name and tag set define separate measurement groups. If the ID changes continually, the application and storage system must manage many tiny groups instead of a few useful aggregated groups.

The impact can appear in multiple places: registry memory, export payload size, number of stored series, query indexes, and dashboard complexity. Aggregating in queries later does not eliminate the cost of creating and storing the detailed series beforehand.

Prometheus also notes that each distinct label combination creates a separate time series, and warns against dimensions like user ID or email. See [Metric and label naming](https://prometheus.io/docs/practices/naming/).

### 3.2. Dimensions Combine Multiplicatively, Not Additively

Suppose a metric has:

| Tag | Maximum designed values |
| --- | ---: |
| `channel` | 4 |
| `result` | 3 |
| `region` | 5 |

The theoretical maximum number of combinations is:

```text
4 × 3 × 5 = 60
```

Actual combinations may be fewer if some combinations never occur. This is an upper bound based on known value-domain assumptions, not a claim that the application always creates exactly 60 meters.

If you add a tag with 100,000 values and all corresponding combinations occur, the theoretical bound becomes:

```text
60 × 100,000 = 6,000,000
```

With a globally unique `order.id`, each ID does not necessarily appear with every combination of the other three tags. In that case, the product formula can overstate actual combinations. Even so, it shows why you must examine correlations and **count actual combinations**, while still assessing the risk of unbounded growth.

A tag that seems small in isolation can still be costly when combined with several other small tags.

### 3.3. Meters and Exported Series Are Not Always Equal in Count

A single timer can export multiple statistics. With classic Prometheus-style histograms, in addition to buckets there are sum and count; thus one tag combination can correspond to multiple exported series.

In a hypothetical example with 12 finite buckets, one `+Inf` bucket, one sum series, and one count series: that statistics group alone produces 15 series per tag combination. With 60 combinations that is 900 series; if the backend distinguishes 20 instances sharing those combinations, the illustrative figure becomes 18,000.

This example counts only the listed components, excluding extra statistics; do not apply the factor of 15 directly to native histograms or every OTLP export mode. The takeaway is that **grouping cost can be multiplied by how statistics are represented**. See [Micrometer 1.13 Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html).

## 4. Where Do the Two Key-Value Groups Go in Observation?

### 4.1. Context Holds Metadata; Handlers Decide How to Use It

An observation has an `Observation.Context`. Handlers react to lifecycle events such as start, error, stop, or other events.

You can picture the usual consumption flow:

```text
Observation.Context
├── Low-cardinality key-values
│   ├── metrics handler -> meter tags
│   └── tracing handler -> span attributes
└── High-cardinality key-values
    └── tracing handler -> span details
```

`ObservationRegistry` manages handlers and observation configuration; `MeterRegistry` manages meters. Without an appropriate tracing handler and exporter, adding high-cardinality metadata is not enough to produce a trace in an external system.

A custom handler can still read metadata and use it in its own way. Therefore, the classification rule is not a security boundary that strictly prevents all custom code from turning high-cardinality values into metrics. The example in this lesson verifies the behavior of `DefaultMeterObservationHandler`, the standard metrics component in use.

The context and handler mechanism is explained in [Observation Components 1.13](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

### 4.2. Placing in the Right Group Does Not Mean Data Is Protected

`highCardinalityKeyValue("token", token)` can still send a secret into the tracing system. It is not a way to hide tokens from observability systems.

Two questions must be separated:

1. Is this data permitted to be collected and useful for investigation?
2. If collected, is it suitable as a metric grouping dimension?

Tokens, passwords, session cookies, and full payment details do not become acceptable merely because they are placed in high-cardinality. Investigative correlation IDs must also be chosen according to the application's data policy.

Conversely, a low-cardinality value can still be sensitive. Having few distinct values does not determine who is allowed to view the data.

### 4.3. It Does Not Automatically Create Context Propagation

Adding `order.id` to high-cardinality metadata does not automatically put it into the headers of every request sent to another service. Observation metadata, span attributes, and baggage/context propagation are related but distinct mechanisms.

Nor do you need to add Trace ID as a metric tag to "link" the two systems. If using navigation links such as exemplars, check the corresponding support; do not turn every Trace ID into a new metric dimension.

## 5. Choosing Groups for Common Data

| Proposed metadata | Initial assessment | Suitable design approach |
| --- | --- | --- |
| `channel` from WEB/MOBILE/BATCH enum | Small, controllable domain | Can use low-cardinality |
| `result` from a fixed set of outcome codes | Small domain if truly bounded | Use low-cardinality when grouping is needed |
| Route `/orders/{orderId}` | Route set defined by the application | Usually suitable for low-cardinality |
| Concrete path `/orders/demo-102` | Grows with order IDs | Do not use raw value as a metric tag |
| `order.id` or `request.id` | Many values, continually generated | Trace detail if needed and permitted |
| `exception.message` | May contain IDs, inputs, and varying text | Prefer stable error code/type for grouping |
| `tenant.id` | Depends on scale and tenant growth rate | Do not assume low just because there are few tenants now |
| `product.id` | Catalog can be very large | Consider controlled product groups or trace details |
| Full URL with query string | May contain many values and secrets | Use normalized route/target; collect only needed details |
| Exact timestamp or random UUID | Continuously new values | Do not use as a normal metric dimension |

This is an initial assessment; the final decision must tie to operational questions and cardinality budgets. A tag with a small domain that helps no query still does not need to be collected.

For example, instead of grouping processing time by individual order, choose `channel` and `result` for metrics; per-order correlation IDs serve trace investigation only. Not every piece of information has to appear in both types of telemetry.

## 6. Java Example: Directly Measuring the Effect of Classification

The following example runs standalone with JDK 21 and Micrometer 1.13.15. No Spring MVC, HTTP server, Collector, or monitoring account is needed. The goal is to observe directly in memory:

- Does high-cardinality metadata remain in the context?
- Does that metadata become a tag on the standard timer?
- How does the timer count change when metadata is mistakenly placed in the low group?

This is a simulated program: the observed work simply adds a dummy order ID to a list. It performs no real order lookup and exports no traces externally.

### 6.1. Preparing Two Files

Structure:

```text
cardinality-demo/
├── pom.xml
└── src/main/java/CardinalityDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>cardinality-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>21</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.15</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>CardinalityDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

The `micrometer-core` dependency at this version brings in the Observation/Common components needed for the example. For a real Boot application, prefer the Boot-managed version set instead of overriding library versions just to copy the example.

`src/main/java/CardinalityDemo.java`:

```java
import io.micrometer.common.KeyValue;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public class CardinalityDemo {
    record Input(String channel, String orderId) {}

    private static final List<Input> INPUTS = List.of(
            new Input("WEB", "demo-101"),
            new Input("WEB", "demo-102"),
            new Input("MOBILE", "demo-103")
    );

    public static void main(String[] args) {
        run("correct", false);
        run("wrong-low", true);
    }

    private static void run(String mode, boolean orderIdAsLow) {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        try {
            ObservationRegistry observations = ObservationRegistry.create();
            List<String> completed = new ArrayList<>();
            List<String> highValues = new ArrayList<>();

            observations.observationConfig()
                    .observationHandler(new DefaultMeterObservationHandler(meters))
                    .observationHandler(new ObservationHandler<Observation.Context>() {
                        @Override
                        public boolean supportsContext(Observation.Context context) {
                            return true;
                        }

                        @Override
                        public void onStop(Observation.Context context) {
                            String value = "absent";
                            for (KeyValue keyValue : context.getHighCardinalityKeyValues()) {
                                if ("order.id".equals(keyValue.getKey())) {
                                    value = keyValue.getValue();
                                }
                            }
                            highValues.add(value);
                        }
                    });

            for (Input input : INPUTS) {
                Observation observation = Observation.createNotStarted(
                                "order.lookup", observations)
                        .lowCardinalityKeyValue("channel", input.channel());

                if (orderIdAsLow) {
                    observation.lowCardinalityKeyValue("order.id", input.orderId());
                }
                else {
                    observation.highCardinalityKeyValue("order.id", input.orderId());
                }

                observation.observe(() -> {
                    completed.add(input.orderId());
                });
            }

            var timers = meters.find("order.lookup").timers();
            Map<String, Long> counts = new TreeMap<>();
            boolean orderIdOnTimer = false;

            for (Timer timer : timers) {
                counts.merge(timer.getId().getTag("channel"), timer.count(), Long::sum);
                orderIdOnTimer |= timer.getId().getTag("order.id") != null;
            }

            System.out.println("mode=" + mode);
            System.out.println("completed=" + completed.size());
            System.out.println("timer-series=" + timers.size());
            System.out.println("counts-by-channel=" + counts);
            System.out.println("order-id-on-timer=" + orderIdOnTimer);
            System.out.println("high-values=" + highValues);

            int expectedTimers = orderIdAsLow ? 3 : 2;
            if (completed.size() != 3 || timers.size() != expectedTimers
                    || !counts.equals(Map.of("WEB", 2L, "MOBILE", 1L))
                    || orderIdOnTimer != orderIdAsLow) {
                throw new IllegalStateException("Unexpected observation result");
            }
        }
        finally {
            meters.close();
        }
    }
}
```

The three inputs have only two `channel` values yet three distinct `order.id` values. Each mode creates a fresh registry so results from the previous run do not bleed into the next.

In `correct`:

```java
observation.lowCardinalityKeyValue("channel", input.channel());
observation.highCardinalityKeyValue("order.id", input.orderId());
```

In `wrong-low`, the program deliberately places `order.id` in the low-cardinality group. This is a control experiment using three in-memory dummy records, not a design pattern to apply.

The custom handler simply reads high-cardinality key-values when the observation stops and records the string for printing results. It is **not a tracing handler**. This separation allows inspecting metadata without confusing having context with having exported a span.

### 6.2. Compiling and Running

In the directory containing `pom.xml`, run Maven with JDK 21:

```shell
mvn -q compile exec:java
```

If dependencies are not yet cached, Maven needs repository network access. This is not a standard-library-only Java file, so running `javac CardinalityDemo.java` without a classpath is insufficient; Maven handles dependencies and the classpath in the command above.

Program stdout:

```text
mode=correct
completed=3
timer-series=2
counts-by-channel={MOBILE=1, WEB=2}
order-id-on-timer=false
high-values=[demo-101, demo-102, demo-103]
mode=wrong-low
completed=3
timer-series=3
counts-by-channel={MOBILE=1, WEB=2}
order-id-on-timer=true
high-values=[absent, absent, absent]
```

`TreeMap` keeps display order as MOBILE then WEB so the output does not depend on registry iteration order. Actual measured durations are not printed because they depend on the execution environment.

### 6.3. Reading the Results by Evidence

| Result | What is proven |
| --- | --- |
| `completed=3` in both modes | The work still ran three times; metadata classification did not alter the simulated call count |
| `timer-series=2` in `correct` mode | The two WEB calls shared one timer; MOBILE used a different timer |
| `order-id-on-timer=false` | The standard metrics handler does not put high-cardinality `order.id` into timer tags |
| `high-values=[demo-101, ...]` | Metadata remains in the context for matching handlers to use |
| `timer-series=3` in `wrong-low` mode | The `order.id` tag split the three calls into three distinct timer identities |
| `high-values=[absent, ...]` in `wrong-low` mode | The value was placed in the low set, not in the high set read by the custom handler |

`timer-series` in the program is **the number of `Timer`s named `order.lookup` in the registry**. It is not the total number of time series any given backend would store after exporting histograms or adding other metadata.

In the wrong mode, `counts-by-channel` still outputs WEB=2 and MOBILE=1 because the program sums counts across timers sharing the same channel. That sum does not prove the tag design is still efficient: three separate timers already had to be created and traversed. As the number of IDs grows, "aggregating back at query time" still pays the cost of the detailed series.

Three IDs in the example do not cause a memory incident on their own; they merely make the difference in measurement identity visible. The operational risk lies in applying the same rule to a volume of IDs growing with real data.

### 6.4. What the Example Does Not Prove

The example creates no spans, does not test sampling, and does not test exporters. To confirm high-cardinality data appears on spans in a Boot application, you must add an appropriate tracing setup and inspect actual spans.

The example also does not measure storage costs or production query latency. It verifies Micrometer's grouping mechanism; evaluating a cardinality budget requires data and configuration from the real deployment environment.

## 7. Designing Metadata That Is Truly Bounded

### 7.1. Start from the Question, Then Choose Tags

A design process can follow this order:

1. Write down the question to answer: "Which channel has a high error rate?"
2. Choose a stable observation name and necessary dimensions: `channel`, `result`.
3. Define the valid value set and the source generating each value.
4. Estimate combinations together with existing framework or global tags.
5. Decide which details are needed only for traces, and which should not be collected.
6. Verify behavior with data containing many distinct values.

Do not add a tag just because a value is available in the request. An ID that is very convenient to look at in a log does not mean it is an appropriate dimension to split metrics across the whole system.

### 7.2. Normalize Values at Metadata Creation Time

If reading `channel` directly from a request, callers may send `web`, `WEB`, `Web`, whitespace, or a completely different string. Even if the author thinks there are only three channels, input data can expand the value domain.

A Java method can normalize **metadata used for observation**:

```java
private static String normalizeChannel(String raw) {
    if (raw == null) {
        return "UNKNOWN";
    }

    String value = raw.trim().toUpperCase(java.util.Locale.ROOT);
    return switch (value) {
        case "WEB", "MOBILE", "BATCH" -> value;
        default -> "UNKNOWN";
    };
}
```

This is a method placed inside a class, not a standalone Java file. Use its return value for the low-cardinality `channel`. The output domain is constrained to WEB, MOBILE, BATCH, and UNKNOWN.

Collapsing unknown values into UNKNOWN loses the ability to distinguish individual unknown strings in metrics; that is a trade-off to understand. Validation and rejection of business input must still follow the application's rules. Normalizing an observation tag does not mean accepting invalid business input.

Keep the same set of keys for a metric family, rather than having `channel` sometimes and switching to a different key name depending on the request. If an undetermined value must be represented, pick a controlled sentinel value and use it consistently.

### 7.3. Use Semantically Meaningful Grouping Information

Several changes are often helpful:

| Detailed data | Grouping dimension to consider | Information lost when grouping |
| --- | --- | --- |
| Order ID | Channel or managed order category | Does not distinguish individual orders |
| Exact timestamp | Do not add as a tag; let the data's timestamp represent time | Does not treat each instant as a group |
| Exact monetary amount | Range buckets defined per need | Does not keep exact currency amount in tag dimension |
| Full error message | Stable error code/category | Does not retain prose or dynamic data in metric dimensions |
| URL with IDs and query | Templated route or operation name | Does not keep each concrete URL |

Do not group arbitrarily just to reduce series count. Each group should be meaningful when querying or alerting; if you cannot explain what a group means, you probably should not add that dimension.

### 7.4. Size-Reduction Tricks That Do Not Reduce Cardinality

- **Hashing IDs:** if distinct IDs still produce distinct hashes, the number of values stays nearly the same.
- **Truncating strings shorter:** reducing length does not guarantee reducing the number of distinct values enough.
- **Moving the ID from a tag to the metric name:** still creates huge numbers of metric identities while making metric structure hard to manage.
- **Renaming the key:** changing `customer.id` to `customer` does not change the value domain.
- **Only reducing export frequency:** affects transmission frequency, without altering the set of meter identities already created.
- **Only reducing trace sampling:** does not cause fewer metric tags to be generated in the standard measurement mechanism.

Bucketing IDs into a fixed number of buckets can bound the number of groups, yet it is an aggregation that loses individual ID identification and may lack business meaning. Nor is it inherently a data-protection measure. Do not treat it as a universal substitute for proper tag design.

## 8. Protective Limits Are a Supporting Layer

Micrometer provides `MeterFilter` to control meter registration and transform meter identities. Configuration example given a `MeterRegistry` variable `meters`:

```java
meters.config().meterFilter(
        io.micrometer.core.instrument.config.MeterFilter.maximumAllowableTags(
                "order.",
                "channel",
                4,
                io.micrometer.core.instrument.config.MeterFilter.deny()
        )
);
```

The example chooses 4 because the metadata schema above defined three channels plus UNKNOWN; that number is not a recommended limit for all applications. The filter targets names starting with `order.` and the `channel` tag. It must be configured before the relevant meters are registered.

When the limit is reached and the `deny` policy rejects a new meter, the registry returns a meter that records no actual data (NOOP). This:

- Does not automatically convert excess values to UNKNOWN.
- Does not guarantee total measurement counts remain complete.
- Does not automatically fix instrumentation sites generating bad tags.
- Should not be viewed as a global storage quota across all processes and backends.

Therefore, you must check the impact on data, rather than treating the absence of an application exception as proof that the limit does not drop measurements.

Other tools such as `ignoreTags` or `replaceTagValues` can drop/collapse dimensions when mitigating an issue. They alter the identity and grouping semantics of metrics, so queries, dashboards, and historical data must be checked. Installing a filter after an incident does not mean historical data or prior costs have been erased.

See [Micrometer 1.13 Meter Filters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html). A protective layer is helpful alongside a clear metadata schema; it does not replace the responsibility to bound value domains at the source.

## 9. Verifying in a Real Spring Boot Application

### 9.1. Reading the Right Layer of Evidence

If the application exposes the `metrics` diagnostic endpoint with proper authorization, inspect the meter you want to observe by name. In an application instrumented with the `order.lookup` observation, the corresponding diagnostic path is usually:

```text
/actuator/metrics/order.lookup
```

The actual path also depends on the configured port and base path. There is no need to expose extra endpoints in production just to test this lesson.

Inspecting available tags can help spot unwanted tags. However:

- A response listing tag values does not necessarily show every combination of them.
- The diagnostic endpoint reflects the application/registry under inspection, not the entire backend history.
- High-cardinality key-values not appearing in standard metric tags may be the intended behavior.
- To check them on traces, you must inspect actual spans and tracing, sampling, filtering, and export conditions.

How to use the meter diagnostic endpoint is described in [Boot 3.3 Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 9.2. Distinguishing Common Symptoms

| Symptom | Direction to check |
| --- | --- |
| Meter count grows nearly with order count | Look for IDs, timestamps, or free-form strings in low-cardinality tags and meter names |
| Same channel appears in multiple variants | Check case normalization, whitespace, and value sources |
| Only two keys yet very many series | Count value domains and combinations, not just the number of keys |
| High-cardinality metadata missing in `metrics` | Check the handler contract; this absence may be intended |
| Metadata is in context yet missing in trace system | Check tracing handler, sampling, exporter, and data filters |
| Counts drop after adding a limit | Check for denied meters and discarded measurements |
| Query aggregation looks right yet cost stays high | Check how many series are created/stored before aggregation |
| Each instance has few values yet backend has many series | Check total instances, retention, and backend-added dimensions |

When investigating suspected cardinality issues, record the metric name, keys, value domains, rate of new values, and observed combination count. Do not include tokens or raw user data in diagnostic reports.

## 10. Practice and Self-Explanation

**Exercise 1: Add `new Input("WEB", "demo-104")` to the program.**

In correct mode, the count of `order.lookup` timers remains 2 and the total WEB count becomes 3. In wrong mode, the timer count becomes 4 because there is a new tag combination. Both modes still execute the simulated work four times. When changing the dataset, update the validation checks at the end of the program accordingly.

**Exercise 2: Replace the last input with a duplicate of `WEB/demo-101`.**

In wrong mode, repeating the exact same tag set does not create a new timer identity; the existing timer's count increments. This separates "event count" from "distinct value-combination count."

**Exercise 3: Choose how to store `customer.id`, `customer.tier`, and `result`.**

`customer.id` usually grows with customers, so do not use it as a metric dimension by default. `customer.tier` can fit if drawn from a small, managed tier set. `result` can fit if it is a stable outcome code rather than a full error message. Only collect detailed IDs in traces when needed and permitted.

**Exercise 4: A new system has 10 tenants. Can `tenant.id` be used as low-cardinality?**

Not enough information. You need to know how high the tenant count can grow, combinations with other dimensions, per-tenant monitoring needs, and storage budget. The current count is only a snapshot; the decision must rest on value-domain commitments and projected cost.

**Exercise 5: Does a value placed into high-cardinality automatically appear on every trace?**

No. It must belong to an appropriate observation/span, be consumed by a handler, and pass recording, sampling, filtering, and export conditions. Metadata classification is not a guarantee that every piece of data is persisted.

When adding a new key-value, be able to explain **where the value comes from, how many groups it can create, which question those groups serve, and whether it needs to appear in metrics or only in trace details**.
