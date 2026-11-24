# Handling Metric Name or Tag Differences Between the Metrics Endpoint and Exporters

## 1. Why Does the Same Measurement Have Multiple Names?

You see `http.server.requests` in `/actuator/metrics`, yet querying that exact name in Prometheus returns no data. Or the metrics endpoint shows tag `order.type`, while exported data uses label `order_type`. This can be normal conversion rather than the application losing measurements.

**Micrometer meter names and monitoring-system time series names belong to two different representation layers.** When diagnosing, identify the name and labels at each hop instead of copying a name observed in one tool directly into another.

Concepts to distinguish:

| Concept | Role |
| --- | --- |
| Meter | Measurement instrument such as Counter, Timer, or Gauge |
| Meter name | Name used when registering with Micrometer, usually lowercase dot-separated |
| Tag | Key–value pair describing a dimension, e.g. `result=success` |
| MeterRegistry | Where meters are registered, recorded, and exposed to a measurement backend |
| Exporter/exporting registry | Component converting meters into the format accepted by the monitoring system |
| Label in Prometheus | Key–value pair attached to a time series |
| Time series | One metric name plus a specific set of label values, containing timestamped samples |

Micrometer provides naming conventions per monitoring system. Conventions can normalize meter names and tag keys to fit the target backend. See [Micrometer Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html).

A single meter can also produce multiple time series: a Timer is not merely "one duration number," but can expose count, total time, and other statistics. Therefore, there is no universal rule that every name in the metrics endpoint appears verbatim once in every exporter.

## 2. Map the Exact Path Before Comparing

You can organize verification into three observation points:

```text
Instrumentation code → registry and filters
                ├── metrics endpoint: meter name, measurements, tags
                └── exporting registry: backend-specific name/labels/unit
                           ↓
                  exported data from application
                           ↓
                 collector, relabeling, storage
                           ↓
                    query/dashboard
```

This diagram is a diagnostic model. In an application with a composite registry and multiple child registries, filters or configurations can differ. The metrics endpoint is not necessarily a textual mirror of a specific exporter's output.

Three comparisons answer three different questions:

1. **Does the app have the expected meter?** Check the registered name, meter type, tags, and data in the registry used by the endpoint.
2. **What does the app actually export?** Check the export endpoint response or output emitted by that exact exporter.
3. **What did the monitoring system store?** Check the name, labels, and sample data after collection/transformation.

If the app already exports properly yet queries find nothing, inspect from the collector onward. If it is absent from exported output, there is no reason to rewrite PromQL with dozens of guessed names yet.

## 3. Normal Differences to Recognize

### 3.1. Meter Names, Units, and Statistic Suffixes

Common examples when using Micrometer with Prometheus:

| Name/type in app | Common series shape in Prometheus | Meaning to read |
| --- | --- | --- |
| Counter `shop.checkout.completed` | `shop_checkout_completed_total` | Cumulative counter |
| Timer `shop.checkout.duration` | `shop_checkout_duration_seconds_count` | Number of recorded timings |
| Same Timer | `shop_checkout_duration_seconds_sum` | Total time, in seconds |
| Same Timer, when corresponding stat is enabled | `shop_checkout_duration_seconds_max` | Maximum duration stat per the meter's windowing mechanism |
| Same Timer, when exporting classic histogram | `shop_checkout_duration_seconds_bucket` | Latency distribution buckets |
| Gauge `queue.depth` with no extra unit | `queue_depth` | Current value |
| Meter with byte unit | Exported name may have `_bytes` suffix | Unit is part of what to compare |

The table lists examples for the corresponding Prometheus configuration and conventions, not a universal renaming algorithm across all exporters, meter types, or versions. Original names may already contain partial suffixes too.

With Micrometer 1.13, Prometheus registry name normalization and the client appending counter suffixes are separate steps. Do not invent a rule like "append `_total` to every name in code." You can cross-check [PrometheusNamingConvention in Micrometer 1.13.0](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/implementations/micrometer-registry-prometheus/src/main/java/io/micrometer/prometheusmetrics/PrometheusNamingConvention.java) when verifying a specific version.

Check units before concluding numbers are wrong. `250 ms` and `0.25 s` are the same duration. Do not multiply by 1,000 in a query if the dashboard already converts the display unit once.

A Timer provides at least count and total time; the exported unit depends on the backend. Statistics such as max, percentiles, and histograms also depend on capability and configuration. See [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

### 3.2. Tag Keys and Tag Values Are Not the Same Thing

Example:

```text
In the meter:
    order.type = web-v2
    result     = success

In Prometheus data under the convention in question:
    order_type = web-v2
    result     = success
```

The key `order.type` is normalized to `order_type`; do not assume the value `web-v2` also turns into `web_v2`. A filter or pipeline may intentionally transform values, yet there must be evidence of that transformation.

Do not reverse-engineer a label name into the original tag name merely by replacing every underscore with a dot. Two different original names can normalize to the same form; and a key like `response_code` may already contain an underscore.

Label order in text output does not create a different series type. Two samples with the same name and the same set of key–value pairs identify the same series regardless of label print order.

### 3.3. Labels Generated by Statistics

Classic histograms include an `le` label representing the bucket upper bound. Percentiles exported in the matching format can carry `quantile`. These are not necessarily business tags passed via `tags(...)` when registering the meter.

Therefore, seeing an extra `le` on a `_bucket` series is not enough to conclude tags were added incorrectly. First identify whether you are reading a count, sum, bucket, or quantile.

## 4. Procedure for Inspecting a Specific Metric

### Step 1 — Pin Target and Time Window

Record the application name, instance, version, exporter type, and time window. Avoid querying the metrics endpoint on instance A and comparing it with exporter output from instance B behind a load balancer.

Ensure the meter-creating activity has occurred. A meter registered only on the first request may not exist immediately after startup. A freshly restarted instance also will not have the same cumulative values as an instance running for days.

### Step 2 — Find the Original Name at the Metrics Endpoint

With an app whose management path is configured and protected, suppose the management URL is `http://127.0.0.1:9091`. Using Bash:

```bash
curl -fsS http://127.0.0.1:9091/actuator/metrics
curl -fsS http://127.0.0.1:9091/actuator/metrics/shop.checkout.completed
```

The name used to select at the metrics endpoint is the application's meter name, not the Prometheus-normalized name. See [Spring Boot 3.3 Metrics Endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

The JSON example below illustrates only the fields being compared, not the entire response:

```json
{
  "name": "shop.checkout.completed",
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 3.0
    }
  ]
}
```

Calling `/actuator/metrics/shop_checkout_completed_total` is not an equivalent substitute for the original name in the example.

URLs in this lesson are lab assumptions. If your system changes port, context path, or base path, use the real URL; use allowed authentication rather than opening endpoints publicly.

### Step 3 — Narrow Down by Meter Tags

Read `availableTags` if provided by the response, then use the exact keys and values observed. Example:

```bash
curl -fsS --get \
  --data-urlencode 'tag=order.type:web-v2' \
  --data-urlencode 'tag=result:success' \
  http://127.0.0.1:9091/actuator/metrics/shop.checkout.completed
```

`--data-urlencode` passes query parameters safely. Do not change `order.type` to `order_type` in this command just because the exporter uses that form.

When unfiltered, the endpoint can aggregate measurements across multiple meters with the same name and different tag combinations. Thus, comparing an unfiltered `COUNT` at the endpoint with a Prometheus series filtered solely to `result="success"` can naturally differ.

### Step 4 — Inspect the Actual Exported Output

With the Prometheus registry and endpoint available:

```bash
curl -fsS http://127.0.0.1:9091/actuator/prometheus
```

Find the group related to `shop_checkout_completed` and `shop_checkout_duration`. An illustrative excerpt might be:

```text
shop_checkout_completed_total{order_type="web-v2",result="success"} 3.0
shop_checkout_duration_seconds_count{order_type="web-v2",result="success"} 1
shop_checkout_duration_seconds_sum{order_type="web-v2",result="success"} 0.25
```

These lines illustrate names and labels, without guaranteeing exact line order, number formatting, or metadata across all client versions. The Counter incremented three times, while the Timer in the example recorded once; the two counts need not match because code measured two separate things.

Record the series name, labels, unit, statistic type, and collection timestamp. Do not screenshot only one `HELP` or `TYPE` line: family names in metadata and counter sample names may be presented differently depending on format.

### Step 5 — Check in the Monitoring System

Suppose you have verified the target has labels `job="checkout-api"` and `instance="10.0.0.7:9091"`. Query the actual exported name:

```promql
shop_checkout_completed_total{
  job="checkout-api",
  instance="10.0.0.7:9091",
  order_type="web-v2",
  result="success"
}
```

Job and instance names here are examples and must be replaced with real target labels. If the query returns no data, check target config, last scrape, timestamp, and transformation steps before adding more filters.

Distinguish instant queries from rate queries. A series may show in an instant query yet `rate(...[5m])` returns nothing when there are not enough samples inside the window.

### Step 6 — Conclude Where the Difference Appears

- Name differs between meter and exported output: check naming convention, unit, meter type, and registry filters.
- Tag differs right in the exported output: check meter registration, common tags, and filters.
- Exported output is right yet stored monitoring data differs: check collector, relabeling, pipeline, and query.
- Only dashboard differs: check recording rules, aggregations, dashboard variables, and display field names.

The goal is to locate the **first point** where data diverges from expectations, not to alter every layer simultaneously until a chart shows numbers.

## 5. Compare Semantics Too, Not Just Names

### 5.1. One Meter Does Not Necessarily Map to One Series

To query a Timer's event count, use the matching `_count` series. To query total time, use `_sum`. To query average latency over a window, take the ratio of rate of total time to rate of event count.

Example with verified time series:

```promql
sum(rate(shop_checkout_duration_seconds_sum{
  job="checkout-api", result="success"
}[5m]))
/
sum(rate(shop_checkout_duration_seconds_count{
  job="checkout-api", result="success"
}[5m]))
```

The result is in seconds. Fresh enough data and a meaningful denominator are required; when there are no events, do not treat a missing or undefined result as zero latency.

`_max` is not p95. Nor should you apply `rate` to a gauge just because its name looks like a counter. Verify data type and exporter representation before picking an expression.

### 5.2. Do Not Compare a Snapshot Against a Rate or Different Window

`COUNT=300` on one instance does not contradict a service-wide `2 request/s` chart. One is a cumulative count at sample time; the other is a rate over a window potentially aggregated across multiple instances.

Before saying "the tags are wrong so numbers don't match," confirm:

- Same instance or aggregated across multiple instances?
- Same route, outcome, and event-type filters?
- Cumulative value, rate, or increase over a window?
- Same unit?
- Any restarts, slow scrapes, or data gaps?
- Comparing count against count, or count against bucket counts?

A histogram has multiple buckets, so exported line count is not recording count. Classic buckets are cumulative; do not sum all buckets to find total requests.

## 6. When Differences Originate from Registries and Filters

An application may use a composite registry and multiple child registries. Check which registry code writes to, which registry the endpoint uses, and which registry actually exports data.

Situations worth checking:

| Situation | Why it creates differences |
| --- | --- |
| Code creates its own separate registry | Meters may sit outside the registry used by the endpoint/exporter |
| Filter applies only to one child registry | Meter names, tags, or presence may differ between export paths |
| Filter denies a group of meters | Code still calls the meter, yet the export path lacks expected data |
| Filter renames or drops a tag | Resulting name/dimension differs from initial expectations |
| Common tags configured differently | One export path includes app/region labels absent in another |
| Configuration applied too late | Previously registered meters do not retroactively transform as expected |

`MeterFilter` can deny meters, transform IDs, or configure statistics. Filter ordering matters. See [Micrometer Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html).

Example configuration snippet inside an app that already has a registry:

```java
import io.micrometer.core.instrument.config.MeterFilter;

registry.config().meterFilter(
        MeterFilter.renameTag("shop.", "order.type", "channel"));
```

This is a configuration snippet, not a standalone program. It must be applied before the relevant meters are registered; scope of effect also depends on which registry receives the filter. Then `channel` may be the tag key to look for on that measurement path, rather than a dot-to-underscore conversion.

Similarly, common tag config in Spring Boot may look like:

```yaml
management:
  metrics:
    tags:
      application: checkout-api
```

Do not assume application name automatically becomes an `application` label everywhere unless corresponding configuration or components are present.

When a label is missing, check where it should be created. Editing PromQL cannot conjure a dimension that was never recorded.

## 7. When Labels Change After Leaving the Application

### 7.1. Target Labels Differ from Application-Registered Tags

Prometheus commonly attaches `job` and `instance` when scraping a target. Consequently, stored data can include these two labels even though they do not appear in the metrics endpoint JSON or the app's own exported text. See [Prometheus Jobs and instances](https://prometheus.io/docs/concepts/jobs_instances/).

Some environment labels can also be added by target config or service discovery. When seeing extra `cluster`, `namespace`, or `region` labels, identify the actual source; do not assume all labels originate from Micrometer.

If the app also exports `job` or `instance`, conflict handling depends on `honor_labels`. Under the corresponding behavior when `honor_labels=false`, conflicting labels from scraped data can be renamed to `exported_job` or `exported_instance`, and then the target's label is attached.

This is a testable explanation for "why did my label get renamed in Prometheus while the endpoint still prints the old name?". Do not flip `honor_labels` just to make a prefix vanish before understanding target-identification consequences.

### 7.2. Relabeling and Collectors Can Alter or Drop Data

Example configuration snippet in a Prometheus scrape job:

```yaml
metric_relabel_configs:
  - source_labels: [__name__, order_type]
    regex: 'shop_checkout_completed_total;(.*)'
    target_label: channel
    replacement: '$1'
    action: replace
```

For matching series, this illustrative config copies `order_type`'s value into label `channel` before storage. It **does not delete** `order_type` automatically. If stored data retains only `channel`, check for an additional labeldrop step or another transformation.

`metric_relabel_configs` operates on samples prior to ingestion. Config can also drop series, so "present in exported output yet absent from storage" is not necessarily a metric-name mismatch. See [Prometheus configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/).

Do not confuse target relabeling with metric relabeling. They act at different stages. When intermediate collectors, OpenTelemetry Collector, or remote write pipelines exist, continue checking processor/relabel steps in that exact pipeline.

Document the change with two-sided evidence:

```text
Before collection:
    shop_checkout_completed_total
    order_type=web-v2

After the configured pipeline:
    shop_checkout_completed_total
    order_type=web-v2
    channel=web-v2

Explanation:
    There is a label-copying step, with no evidence the original label was deleted.
```

### 7.3. Dashboards May Not Query the Raw Series

A recording rule can create a new name for an aggregation. A `sum by (...)` query also drops dimensions not preserved in the output. A legend title on a dashboard might simply be a display string written by the author.

Therefore, open the actual query expression:

- Is it querying the raw series or a recording-rule-generated name?
- Is an aggregation stripping `instance` or business tags?
- Are dashboard variables injecting filters that mismatch actual values?
- Are the selected datasource and time range right?

A label not appearing in an aggregated result does not prove the exporter never emitted that label.

## 8. Exporter Version and Format Are Part of the Record

Record at least the versions of Spring Boot, Micrometer, registry modules, and backend client. Do not write only "using Prometheus."

Micrometer has a Prometheus integration using the newer client and a `prometheus-simpleclient` path using the older client. They do not guarantee identical formatting details or naming rules. When upgrading versions, read corresponding release changes and check actual exported output, especially regarding suffixes or name validation rules.

Prometheus text format and OpenMetrics also differ in metadata, counter representation, or extra fields. Do not treat an output excerpt from another version as an absolute canonical string for full-text equality checks.

The `_seconds_count`, `_seconds_sum`, and `_bucket` examples in this lesson refer to the corresponding Prometheus representation. With other exporters:

- Names may follow a different convention.
- Tags may map to different attributes or dimensions.
- Units and statistical representations may differ.
- Some metadata may live on resource/metadata records rather than as labels on every data point.

The sustainable practice is keeping business names in code according to Micrometer conventions while maintaining verified mappings per export path. Do not rename every meter in code to Prometheus names just because one dashboard queries the wrong name.

## 9. Design Mistakes That Make Reconciliation Harder

### 9.1. Same Name with Inconsistent Tag Keys

Example to avoid in a design targeting Prometheus:

```java
registry.counter("shop.checkout.completed", "channel", "web").increment();
registry.counter("shop.checkout.completed", "result", "success").increment();
```

Both registrations use the same name yet different tag key sets. The registry/client may warn or behave unexpectedly; read meter registration logs and constraints of the version in use.

A more consistent design uses the same key set with clear meaningful values for each case:

```java
registry.counter("shop.checkout.completed",
        "channel", "web", "result", "success").increment();
registry.counter("shop.checkout.completed",
        "channel", "batch", "result", "failure").increment();
```

These are code snippets inside an app that already has a registry. Do not use dummy values just to pad tags if doing so distorts measurement meaning; define the metric's label contract upfront. See [Micrometer Prometheus on tag consistency and export formats](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html).

### 9.2. Different Names Normalizing to the Same Form

`shop.checkout` and `shop_checkout` can become indistinguishable after normalization. Likewise, two tag keys normalized to the same name can collide.

In that case, inspect warning logs, registered meter lists, and actual output. Do not just add another character replacement in PromQL. Fix the naming design or mapping rules so multiple concepts do not occupy one identifier.

Also consider meter types: registering the same identifier as both a Counter and a Timer will not yield two independent measurements as desired. Name, type, and labels must have an unambiguous relationship.

### 9.3. Uncontrolled Growth in Label Combinations

Every combination of label values can create a new series. Do not add order IDs, trace IDs, emails, or URLs with variable IDs just for "easy tag search."

For HTTP routes, prefer route templates like `/orders/{id}` per the app's instrumentation convention instead of paths containing each specific order ID. Per-request specifics usually belong in logs or traces with appropriate data policies.

If a faulty tag needs fixing, weigh both cardinality reduction and the risk of collapsing distinct series into one identifier. Dropping a tag can lose the ability to distinguish sources; for already exported data, unplanned label removal can create collisions.

### 9.4. Renaming in Production Without Updating Consumers

A name or tag change affects dashboards, recording rules, alerts, and reports. Before changing:

1. Identify which contract is wrong: name in code, exporter mapping, collection rule, or query.
2. List consumers that need updating.
3. Test on representative data; check units and statistic types.
4. Roll out with a plan allowing before–after comparison.
5. If keeping a compatibility window, define its scope and end date.

Do not keep two counters with the same meaning indefinitely and sum both in queries, as that can double-count the same activity.

## 10. Java 17+ Example: Distinguishing Original Names from Naming Conventions

The following program runs standalone with Micrometer Core 1.13.0. It uses `SimpleMeterRegistry` and calls the snake case convention directly to observe names. It does not boot Spring Boot, open HTTP ports, or simulate the full Prometheus exporter.

### 10.1. Preparing Dependencies

Create a new directory with:

```text
meter-naming-demo/
├── pom.xml
└── src/main/java/MeterNamingDemo.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>meter-naming-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

In a Spring Boot app, you normally let Boot's BOM manage matching dependency versions. This standalone POM pins versions to reproduce a minimal program.

### 10.2. Full Program

Contents of `src/main/java/MeterNamingDemo.java`:

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.config.NamingConvention;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class MeterNamingDemo {
    public static void main(String[] args) {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            Counter completed = Counter.builder("shop.checkout.completed")
                    .tags("order.type", "web-v2", "result", "success")
                    .register(registry);
            completed.increment(3);

            Timer duration = Timer.builder("shop.checkout.duration")
                    .tags("order.type", "web-v2", "result", "success")
                    .register(registry);
            duration.record(Duration.ofMillis(250));

            System.out.println("counter.name=" + completed.getId().getName());
            System.out.println("counter.count=" + (long) completed.count());
            System.out.println("tag.order.type=" + completed.getId().getTag("order.type"));
            System.out.println("snake.name=" + NamingConvention.snakeCase.name(
                    completed.getId().getName(), Meter.Type.COUNTER));
            System.out.println("snake.tag=" + NamingConvention.snakeCase.tagKey("order.type"));
            System.out.println("timer.count=" + duration.count());
            System.out.println("timer.total.seconds=" + duration.totalTime(TimeUnit.SECONDS));
        } finally {
            registry.close();
        }
    }
}
```

### 10.3. Compiling, Running, and Comparing Stdout

From the directory containing the POM, using Bash:

```bash
mvn -q compile dependency:copy-dependencies
java -cp "target/classes:target/dependency/*" MeterNamingDemo
```

Maven downloads dependencies as needed and compiles with release 17. If you want to invoke the compiler directly after Maven has created directories and downloaded dependencies:

```bash
javac --release 17 -encoding UTF-8 -cp "target/dependency/*" -d target/classes src/main/java/MeterNamingDemo.java
```

On Windows, the classpath separator in the run command uses a semicolon:

```powershell
java -cp "target/classes;target/dependency/*" MeterNamingDemo
```

Program stdout:

```text
counter.name=shop.checkout.completed
counter.count=3
tag.order.type=web-v2
snake.name=shop_checkout_completed
snake.tag=order_type
timer.count=1
timer.total.seconds=0.25
```

Explanation:

- `getId().getName()` still returns the name registered in the active registry.
- The original tag key is still `order.type`; its value is still `web-v2`.
- Calling the snake case convention produces a different representation of the name and tag key without mutating the meter object being read.
- `snake.name` does not yet have `_total`: character normalization does not cover the entirety of how an exporter/client formats a counter.
- The Timer recorded one 250 ms duration, so requesting total time in seconds yields `0.25`.

The program verifies the distinction between original names, naming conventions, and units. To verify the series names of a production exporter, you still need to read exported output from the exact registry and version in use.

## 11. Document the Mapping So You Do Not Guess Next Time

A brief profile for the example metric could be:

| Field to record | Illustrative value |
| --- | --- |
| Business meaning | Completed checkouts by order type and outcome |
| Micrometer name | `shop.checkout.completed` |
| Meter type | Counter |
| App tag keys | `order.type`, `result` |
| Verified Prometheus name | `shop_checkout_completed_total` |
| Exported label keys | `order_type`, `result` |
| Values being checked | `web-v2`, `success` |
| Target-provided labels | `job`, `instance` per scrape config |
| Post-collection transforms | Yes or no; note exact rule if present |
| Evidence scope | Instance, version, timestamp, and data format |

Do not treat the illustrative table as a contract for an unverified system. When creating a real profile, fill it from observed evidence at each point.

Before editing, you should be able to answer: "Am I fixing the meter name, exporter mapping, collection rule, or query?". After editing, compare on the same instance and same label combination; verify related alerts still reflect the intended semantics.

## 12. Self-Practice Diagnostics

### Scenario 1: Using the Exported Name at the Metrics Endpoint

The application has meter `shop.checkout.completed`. Prometheus has series `shop_checkout_completed_total`. You call:

```text
/actuator/metrics/shop_checkout_completed_total
```

and cannot find the expected meter.

**Reference:** use the meter name observed in the registry, namely `shop.checkout.completed`, when querying the metrics endpoint. Use the exported series name when querying Prometheus. There is no need to rename the meter in code just so both URLs use the exact same character string.

### Scenario 2: Tag Value Mistakenly Altered

Exported output has:

```text
shop_checkout_completed_total{order_type="web-v2",result="success"} 3.0
```

A query using `order_type="web_v2"` returns no data.

**Reference:** in the example, the key was normalized while the value remained `web-v2`. Fix the filter condition to the actual value. If a pipeline transforms values in another environment, verify that separately rather than applying character substitution speculatively.

### Scenario 3: Exported Output Is Right, Yet Stored Labels Gain a Prefix

The app itself exports label `job="business-worker"`, yet Prometheus stores `exported_job="business-worker"` alongside the target's `job` label.

**Reference:** check label-conflict handling and `honor_labels` configuration. This may be a change at the scrape step, not Micrometer renaming tags inside the app. Preserve two-sided evidence before adjusting policy.

### Scenario 4: Total Time Off by 1,000x

One recorded sample is 250 ms. Timer data exported in seconds has total time 0.25; the dashboard displays 0.25 ms.

**Reference:** check the series unit and display unit. A value of 0.25 seconds equals 250 milliseconds. Change formatting or unit conversion at one identified point only; do not multiply/divide across multiple layers and accidentally introduce a new discrepancy.

A diagnostic result meets expectations when it pinpoints the original name, exported name, label keys/values, unit, and exact transformation hop. Formatting differences are only the initial clue; what must be preserved is the measurement's meaning and the ability to query the right data.
