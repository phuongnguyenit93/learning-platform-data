# Querying Metrics by Name and Tag Without Misreading Aggregated Results

A single reading of `COUNT=15` does not say a specific group processed 15 times. That number may have merged multiple channels, multiple outcomes, or multiple targets sharing one metric name. To understand the result, you must know **which meters were selected and how their measurements were merged**.

In Spring Boot Actuator, the `metrics` endpoint helps inspect available names, values, and tags. This lesson walks from selecting a name and filtering tags to interpreting each statistic, then verifies behavior with a program using Spring Boot 3.3.0 and Micrometer 1.13.0. Code targets Java 17 and runs on JDK 21.

## 1. Mental model for reading a query

A query can be understood in three steps:

```text
Logical name
    -> select meters with matching name
    -> filter by tag key-value pairs
    -> merge statistics of remaining matching meters
    -> return measurements and remaining filterable tags
```

Consider a counter family `store.orders` counting recorded order-processing outcomes:

| Name | channel | result | COUNT |
| --- | --- | --- | --- |
| `store.orders` | `web` | `success` | 8 |
| `store.orders` | `web` | `failure` | 2 |
| `store.orders` | `api` | `success` | 5 |

These are three meters for three tag combinations, even though they share one logical name. The dataset does not yet contain `channel=api, result=failure`.

From that table:

- Select only name `store.orders`: merges all three groups, yielding 15.
- Add `channel=web`: merges the two web groups, yielding 10.
- Add `result=success` as well: leaves only the web success group, yielding 8.

The number 15 is not a list of 15 order objects and does not by itself prove 15 unique orders exist. Counting semantics depend on the chosen recording rule. If every retry is counted, the number reflects those recordings.

## 2. Choosing the right logical name

### 2.1. The name list is not a list of every tag combination

In a web application with the endpoint accessible, start with:

```http
GET /actuator/metrics
```

The `names` list tells you the currently known metric names. The name `store.orders` only needs to appear once even though the registry holds the three tag groups in the table above.

To inspect details of a metric family:

```http
GET /actuator/metrics/store.orders
```

The endpoint is a diagnostic tool for metrics registered in the application; it provides names, measurements, and tag filtering. [Spring Boot 3.3 metrics REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

### 2.2. Use names from code, do not guess from exported names

Actuator expects the logical name used to register the meter in Java, such as `store.orders` or `store.checkout.duration`. Names in an external monitoring system may have been normalized under that system's conventions.

Therefore, an underscore-separated name or suffix seen in an exporter's output is not automatically the name to place after `/actuator/metrics/`. When unsure, check the `names` list and the registration site in code. [Spring Boot 3.3 metrics guide](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 2.3. An absent name does not mean a value of 0

A meter may only be created when a business branch runs for the first time. A missing name can also result from a filter, wrong registry, wrong instance, or wrong logical name.

Distinguish:

- The meter exists and its measurement equals 0.
- The meter does not exist yet or no group matches the conditions.
- The endpoint or application is not reachable yet.

Those three cases must not all be collapsed into 0 and interpreted the same way.

## 3. Filtering by tags with explicit conditions

Tags are passed via the `tag` parameter in `key:value` form:

```http
GET /actuator/metrics/store.orders?tag=channel:web
GET /actuator/metrics/store.orders?tag=channel:web&tag=result:success
```

In the second query, a meter must match **both** `channel=web` **and** `result=success`. Tag pairs with different keys combine as an AND condition.

| Condition | Selected groups in dataset | COUNT |
| --- | --- | --- |
| No tags | Web success, web failure, API success | 15 |
| `channel=web` | Both web groups | 10 |
| `result=success` | Web success and API success | 13 |
| `channel=web`, `result=success` | Web success | 8 |
| `channel=api`, `result=failure` | No matching combination | No measurement for this selection |

### 3.1. Unselected filter dimensions must be understood as still merged

A query filtering only `channel=web` still includes both successes and failures. The number 10 is not the web success count.

Similarly, filtering `result=success` still spans multiple channels. The number 13 is not solely API or web successes. An omitted filter condition is typically an unsplit dimension inside the merged result.

This matters especially for tags like region, connection pool name, cache name, status, or HTTP route. One metric name can encompass many groups that need to be inspected separately.

### 3.2. Do not assume repeated parameters mean OR

Multiple `tag` parameters express key-value pairs to filter on. Do not assume repeating the same key with two values selects an OR operation like a monitoring system's query language.

If you need to combine two values of the same key, choose the right aggregation scope, query each group to check, or use a query engine that explicitly supports that selection. Keep one clear meaning per key within a single request.

### 3.3. Mind values and URL encoding

`channel=api` and `channel=API` do not match the same value in this dataset. Only use keys and values matching the meter's contract.

Tag values containing spaces or special characters must be URL-encoded. In a shell, `&` inside a URL must also stay part of the argument data rather than being interpreted as a shell operator.

Example using curl to encode values and keep the URL clean:

```shell
curl --get "http://localhost:8080/actuator/metrics/store.orders" --data-urlencode "tag=channel:web" --data-urlencode "tag=result:success"
```

On Windows, if `curl` points to another command instead of the curl binary, use `curl.exe` with the same arguments.

## 4. Reading the response and availableTags

A response contains these groups of information:

| Field | How to use | What not to infer |
| --- | --- | --- |
| `name` | Confirm the metric family being read | Do not assert only one meter exists across tags |
| `description` | Understand the declared meaning | Does not replace checking how writes and merges work |
| `baseUnit` | Read the measurement's unit | Do not turn every number into a rate or average |
| `measurements` | Read each statistic by `statistic` name | Do not sum statistics with different units |
| `availableTags` | Find dimensions and values usable for further filtering | Do not assert every value combination exists |

With the counter set from Section 1, querying by name produces content equivalent to the following JSON example; item order may vary:

```json
{
  "name": "store.orders",
  "description": "Recorded order outcomes",
  "baseUnit": "orders",
  "measurements": [
    { "statistic": "COUNT", "value": 15.0 }
  ],
  "availableTags": [
    { "tag": "channel", "values": ["api", "web"] },
    { "tag": "result", "values": ["failure", "success"] }
  ]
}
```

This is illustrative data constructed for the lesson. Field names and structure follow the Actuator REST API; the program in Section 7 produces the corresponding descriptors for direct verification.

### 4.1. availableTags is not a table of combinations

Seeing `channel` with `api`, `web` and `result` with `failure`, `success` is not enough to conclude all four combinations exist.

In the dataset under examination, failure only exists on web. Thus, selecting `api + failure` has no matching meter even though each individual value appears in `availableTags` on the broader query.

To check a combination, filter one dimension at a time and inspect the remaining options. After selecting `channel=api`, the `result` tag only leaves `success` in the sample data.

### 4.2. Selected conditions narrow further filtering options

In the implementation used in this example, `availableTags` is computed from the still-matching meters; keys already used for filtering are no longer listed as unselected dimensions.

After `channel=web`, the result can still be filtered by both values of `result`. After selecting both `channel=web` and `result=success`, no unselected dimensions remain in this simple counter set.

Consequently, a tag disappearing from the suggestion list after filtering does not necessarily mean data was lost. Distinguish already-applied filters from dimensions still available to pick next.

## 5. Merging measurements accurately by statistic type

Do not ask only "how many meters were merged"; also ask "by which mathematical operation was this statistic field merged?"

For the types verified in Spring Boot 3.3.0:

| Meter type and statistic | How the endpoint merges matching groups in the example | How to read |
| --- | --- | --- |
| Counter – `COUNT` | Sums count values | Total recorded amount across selected groups |
| Gauge – `VALUE` | Sums observed values | Meaningful only when states are additive for the same question |
| Timer – `COUNT` | Sums sample counts | Total number of recorded duration samples |
| Timer – `TOTAL_TIME` | Sums total durations | Total duration of recorded samples, in the response unit |
| Timer – `MAX` | Takes the largest value among the groups' max values | Not the sum of maxes and not automatically all-time history max |

**Version note:** a general description saying the endpoint "sums statistics" should not be applied mechanically to every `statistic`. The example running on Spring Boot 3.3.0 confirms `MAX` takes the maximum value. When verifying specific behavior, check the active implementation and version.

### 5.1. Summing gauges is useful only when addition makes sense

Suppose two independent gauges represent a web queue with 4 jobs and an API queue with 7 jobs. The sum 11 makes sense if you want to see pending jobs across both disjoint queues.

If two gauges observe the same shared queue, summing both values double-counts the same data. If gauges represent ratios or percentages, addition usually also requires examining meanings and denominators; do not treat every `VALUE` sum as a valid overall metric.

The endpoint performs merging based on data and statistics. It does not possess full business semantics to guarantee your chosen group selection yields a meaningful quantity.

### 5.2. Reading Timer by count, total duration, and unit

Timer dataset used in this lesson:

| channel | Recorded durations | COUNT | TOTAL_TIME | MAX before max window expires |
| --- | --- | --- | --- | --- |
| `web` | 100, 200, 300 ms | 3 | 0.6 seconds | 0.3 seconds |
| `api` | 900 ms | 1 | 0.9 seconds | 0.9 seconds |
| Merged groups | Four recordings | 4 | 1.5 seconds | 0.9 seconds |

The average duration across the four samples is:

```text
Total duration / total count = 1.5 seconds / 4 = 0.375 seconds = 375 ms
```

Do not take the arithmetic mean of the two group averages: web averages 200 ms and API averages 900 ms, yet `(200 + 900) / 2 = 550 ms` is not the average of the four samples. The two groups have different sample counts.

When `COUNT=0`, division cannot produce a meaningful average duration; do not replace the result with an arbitrary number and treat it as measured latency.

Timer provides at least sample count and total duration; the base unit depends on the registry. Basic implementations' max values are time-windowed and can expire when no new recordings arrive. [Timer in Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html).

Thus, max can drop to 0 while cumulative count still retains the example's four recordings. Do not conclude the old recordings never happened or that application latency has always been 0 across its lifetime.

### 5.3. Aggregated numbers cannot reconstruct every detail

`COUNT`, `TOTAL_TIME`, and `MAX` are not enough to reconstruct the full duration distribution. Do not infer p95, p99, or individual raw samples from those three numbers alone.

Similarly, a counter sum by name cannot recover tag splits once groups are collapsed. Re-filter the exact dimension you need to analyze, or use an appropriate storage and query source.

## 6. Preparing HTTP access in a web application

This section applies to a Spring Boot web application that already has Actuator and registered meters. You can expose the required endpoints for a learning environment, for example in `application.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
```

Exposure configuration enables serving the endpoints; it does not generate business data by itself and does not replace access-control configuration. Host, port, and base path can also differ from the examples' defaults.

Step-by-step reading sequence:

```shell
curl "http://localhost:8080/actuator/metrics"
curl "http://localhost:8080/actuator/metrics/store.orders"
curl "http://localhost:8080/actuator/metrics/store.orders?tag=channel:web"
curl "http://localhost:8080/actuator/metrics/store.orders?tag=channel:web&tag=result:success"
```

Against an application with live traffic, values can change between requests. Do not require an earlier total to equal the sum of groups read at later timestamps.

The standalone program below uses the same `MetricsEndpoint` class to verify selection and merging, without running a web server. To test with curl, put the meters into a running web application; running only the CLI program does not open port 8080.

## 7. Complete Java example and verifiable stdout

The program sets up three counter groups, two timer groups, and two gauges. Timer and gauge data are created independently to illustrate each type's merging; do not assume four timer runs represent all counter recordings.

### 7.1. Project files

Create a separate experiment directory:

```text
metric-query-demo/
├── pom.xml
└── MetricQueryDemo.java
```

`pom.xml`:

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

    <groupId>example</groupId>
    <artifactId>metric-query-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
</project>
```

The parent manages library versions per Spring Boot 3.3.0. The example calls the API directly, so no web application packaging plugin is needed to run the verification.

### 7.2. Source code

`MetricQueryDemo.java`:

```java
import java.time.Duration;
import java.util.List;
import java.util.Locale;
import java.util.TreeSet;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.Statistic;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.springframework.boot.actuate.metrics.MetricsEndpoint;

public class MetricQueryDemo {
    public static void main(String[] args) {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        AtomicInteger webQueue = new AtomicInteger(4);
        AtomicInteger apiQueue = new AtomicInteger(7);
        try {
            addOrders(registry, "web", "success", 8);
            addOrders(registry, "web", "failure", 2);
            addOrders(registry, "api", "success", 5);

            Timer web = registry.timer("store.checkout.duration", "channel", "web");
            web.record(Duration.ofMillis(100));
            web.record(Duration.ofMillis(200));
            web.record(Duration.ofMillis(300));
            Timer api = registry.timer("store.checkout.duration", "channel", "api");
            api.record(Duration.ofMillis(900));

            Gauge.builder("store.queue.depth", webQueue, AtomicInteger::get)
                    .tag("channel", "web").register(registry);
            Gauge.builder("store.queue.depth", apiQueue, AtomicInteger::get)
                    .tag("channel", "api").register(registry);

            MetricsEndpoint endpoint = new MetricsEndpoint(registry);
            System.out.println("knownCounterName="
                    + endpoint.listNames().getNames().contains("store.orders"));
            printCount("all", endpoint.metric("store.orders", null));
            printCount("web", endpoint.metric(
                    "store.orders", List.of("channel:web")));
            printCount("success", endpoint.metric(
                    "store.orders", List.of("result:success")));
            printCount("webSuccess", endpoint.metric(
                    "store.orders", List.of("channel:web", "result:success")));
            System.out.println("apiFailure="
                    + (endpoint.metric("store.orders",
                    List.of("channel:api", "result:failure")) == null
                    ? "NO_MATCH" : "MATCH"));

            var allOrders = endpoint.metric("store.orders", null);
            printTagValues(allOrders, "channel");
            printTagValues(allOrders, "result");

            var duration = endpoint.metric("store.checkout.duration", null);
            double count = measurement(duration, Statistic.COUNT);
            double total = measurement(duration, Statistic.TOTAL_TIME);
            double max = measurement(duration, Statistic.MAX);
            System.out.printf(Locale.ROOT,
                    "timerCount=%.0f totalSeconds=%.3f maxSeconds=%.3f meanMs=%.3f%n",
                    count, total, max, total / count * 1000);

            var queues = endpoint.metric("store.queue.depth", null);
            System.out.printf(Locale.ROOT, "queueValue=%.0f%n",
                    measurement(queues, Statistic.VALUE));
            System.out.println("queueSources="
                    + webQueue.get() + "+" + apiQueue.get());
        } finally {
            registry.close();
        }
    }

    private static void addOrders(SimpleMeterRegistry registry,
                                  String channel, String result, int amount) {
        Counter.builder("store.orders")
                .description("Recorded order outcomes")
                .baseUnit("orders")
                .tags("channel", channel, "result", result)
                .register(registry)
                .increment(amount);
    }

    static double measurement(
            MetricsEndpoint.MetricDescriptor descriptor, Statistic statistic) {
        return descriptor.getMeasurements().stream()
                .filter(sample -> sample.getStatistic() == statistic)
                .findFirst().orElseThrow().getValue();
    }

    private static void printCount(
            String label, MetricsEndpoint.MetricDescriptor descriptor) {
        System.out.printf(Locale.ROOT, "%s.count=%.0f%n",
                label, measurement(descriptor, Statistic.COUNT));
    }

    private static void printTagValues(
            MetricsEndpoint.MetricDescriptor descriptor, String tagName) {
        var tag = descriptor.getAvailableTags().stream()
                .filter(candidate -> candidate.getTag().equals(tagName))
                .findFirst().orElseThrow();
        System.out.println(tagName + "Values=" + new TreeSet<>(tag.getValues()));
    }
}
```

Key points to observe in the code:

1. `addOrders(...)` creates meters with the same name but different tag combinations, then increments by the corresponding amount.
2. `MetricsEndpoint` accepts the registry holding the data. Calling `metric(name, filters)` selects and merges measurements just as the HTTP endpoint handler does.
3. String lists `channel:web`, `result:success` are filter conditions for the direct API call; they correspond to `tag` parameters in HTTP queries.
4. `measurement(...)` selects by `Statistic`, not by element index inside the `measurements` array.
5. `apiFailure` tests the no-matching-combination case. The direct call returns `null`; the program distinguishes it from a descriptor with `COUNT=0`.
6. `TreeSet` only sorts tag values for deterministic stdout printing. It does not alter how the endpoint filters.
7. Both gauge state objects are kept alive until the end of observation. The registry is closed in `finally` per the standalone program's lifecycle.

### 7.3. Compile and run

Maven and JDK 17 or newer are required; the example uses Java 17 level and runs on JDK 21. Download runtime dependencies:

```shell
mvn -q dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=lib
```

PowerShell/Windows:

```powershell
New-Item -ItemType Directory -Path out -Force | Out-Null
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out MetricQueryDemo.java
java -cp "out;lib/*" MetricQueryDemo
```

Linux/macOS:

```shell
mkdir -p out
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out MetricQueryDemo.java
java -cp "out:lib/*" MetricQueryDemo
```

The classpath uses `;` on Windows and `:` on Linux/macOS. The first download needs Maven repository access if the machine does not yet cache dependencies.

Stdout:

```text
knownCounterName=true
all.count=15
web.count=10
success.count=13
webSuccess.count=8
apiFailure=NO_MATCH
channelValues=[api, web]
resultValues=[failure, success]
timerCount=4 totalSeconds=1.500 maxSeconds=0.900 meanMs=375.000
queueValue=11
queueSources=4+7
```

Timer output uses seconds for the example's registry, then converts to milliseconds when computing the average. `Locale.ROOT` keeps the decimal point consistent. Do not grab the number `1.500`, ignore the `totalSeconds` label, and mistake it for 1.5 ms.

## 8. Distinguishing Actuator queries from meter lookups in Java

The following single call does not sum every counter sharing that name:

```java
Counter one = registry.get("store.orders").counter();
```

This is a snippet for a registry that already contains data. When multiple tag groups exist, do not rely on a single-meter lookup to infer a total, and do not rely on which group happens to be picked.

To select the exact group:

```java
Counter webSuccess = registry.get("store.orders")
        .tags("channel", "web", "result", "success")
        .counter();
```

To explicitly sum counters within a scope:

```java
double webTotal = registry.find("store.orders")
        .tag("channel", "web")
        .counters()
        .stream()
        .mapToDouble(Counter::count)
        .sum();
```

Requires importing `io.micrometer.core.instrument.Counter` and having an appropriate `registry` variable. With the sample dataset, `webTotal` is `10.0`.

This is an aggregation performed by your code across matching meters. It differs from `counter()` returning one object and differs from `MetricsEndpoint` building a descriptor across statistics.

Pick the right tool for each goal:

| Goal | Approach |
| --- | --- |
| Inspect names and filterable dimensions | `MetricsEndpoint` or HTTP `metrics` endpoint |
| Retrieve one meter with exact known name and tags | Single lookup with full conditions |
| Sum a set of counters in Java | Fetch matching collection and sum by intended semantics |
| Query history, rates, and alerts across collections | Appropriate storage backend and monitoring tool |

## 9. Boundaries to maintain when interpreting results

### 9.1. Application and instance scope

An endpoint on one instance does not automatically represent the entire service cluster. When running multiple instances, identify which instance a request reached, especially when accessing through a load balancer.

One request hitting instance A and the next hitting B can return different numbers without any filtering bug. Aggregating cluster-wide requires a data source with instance identification and proper aggregation rules.

### 9.2. A snapshot does not become history or a rate

`COUNT=15` in the example's cumulative counter is the recorded amount, not "15 orders/second." Computing a rate requires timestamps and appropriate history, along with understanding how the registry exports metrics.

The `metrics` endpoint serves inspection; it does not replace a historical monitoring store. Polling it a few times for diagnostics does not turn this API into a time-series backend.

### 9.3. Units and schemas must be compatible

Before merging, groups sharing a name must still describe the same quantity and share a consistent unit contract. One group recording bytes and another recording KiB under the same name and metadata will not be auto-corrected by the endpoint into accurate data.

`description` and `baseUnit` in the response are descriptive metadata, not proof that every recording site obeyed the contract. Inspect registration and recording sites when numbers look off.

Tags present on a counter family also do not automatically exist on a timer family. In the example, the counter uses `result` while the timer only uses `channel`; do not use one name's tag list to assume queries on every other name.

### 9.4. Results can change during observation

Writes can occur concurrently with reads. A single descriptor or multiple consecutive requests do not automatically form an atomic read transaction across all business state.

When verifying exact values, use controlled inputs like the sample program. On a live running system, choose appropriate evidence and account for freshness, instance lifecycles, and statistical windows.

## 10. Diagnosing when results differ from expectations

| Symptom | What to check |
| --- | --- |
| Name exists, yet filtering a combination yields no data | Does that combination actually exist, or were only the individual values present in `availableTags`? |
| Counter by name is higher than the group of interest | Is an unfiltered tag still merging multiple groups? |
| Name copied from exporter is not found | Does the logical name in the registry differ from the normalized exported name? |
| `availableTags` shrinks after a filter | Which groups still match and which keys were already selected? |
| Gauge sum is confusing | Are the states disjoint and is addition semantically valid? |
| Timer mean misses expectation | Did you divide total time by total count, or average the group averages? |
| MAX does not equal the sum of group maxes | This statistic uses maximum-value selection in the verified implementation |
| MAX drops to 0 while COUNT remains | Did the max window expire while count stayed cumulative? |
| Two calls to the same URL return different numbers | Were new writes recorded, did the instance change, or did a statistical window shift? |
| Missing data yet UI displays 0 | Is a no-match result being collapsed into an actual zero measurement? |

A useful check order is: confirm instance and endpoint access, logical name, tag set, remaining matching scope, statistic type, unit, and time basis. Once each layer is clear, interpreting an aggregated number has solid grounding.

## 11. Practice

Change each part on a fresh run and predict the output:

1. Add `addOrders(registry, "api", "failure", 4)`. Total counter becomes 19; web remains 10; success remains 13; the API failure combination now has data. Re-check `availableTags` after filtering for API.
2. Keep only the `channel:web` filter in the `webSuccess` query. Result becomes 10 because both web outcomes remain; variable names do not add filter conditions.
3. Add a 400 ms timer sample for web. Timer total becomes 5 samples and 1.9 seconds; average is 380 ms, while current max remains 900 ms.
4. Change the query tag value from `api` to `API`. Compare the no-matching-group case against a counter whose actual value is 0.
5. Call `registry.get("store.orders").counter()` and compare with summing `counters()`. Explain why a single-object lookup is not an aggregation.
6. Filter the counter by one channel, read remaining tags, then filter further. Do not deduce all combinations from the value list of an unfiltered query.

When documenting results, state the full scope: "COUNT across all order outcomes," "COUNT for web," or "COUNT for web success." For timers, include both statistic and unit, such as "total duration 1.5 seconds across four samples" rather than citing a contextless number.
