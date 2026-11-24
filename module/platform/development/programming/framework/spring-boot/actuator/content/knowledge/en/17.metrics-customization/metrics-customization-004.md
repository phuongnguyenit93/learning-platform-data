# Limiting Tag Cardinality and Handling High-Cardinality URIs

## 1. Why Can a URI Label Overload a Monitoring System?

Suppose an application has an order detail route:

```text
/orders/{id}
```

If the path with the order ID substituted is used as a label value, each resource can create a separate measurement group:

```text
uri=/orders/101
uri=/orders/102
uri=/orders/103
...
```

Meanwhile, the operational question is usually "is the order detail route slow?", not "does every order ID need its own duration chart?". The same type of operation has been split into too many groups.

The **cardinality** of the `uri` label is the number of distinct URI values used. High cardinality can increase the number of meters in the Java process, the number of time series in the receiving system, memory usage, storage cost, and query difficulty.

Distinguish carefully:

- Request count is how many times an operation occurs.
- `uri` value count is how many distinct path groups exist.
- Meter count depends on the name plus the entire set of labels.
- Exported series count also depends on the meter type and statistics, such as histograms.

One million requests with the same `uri=/orders/{id}` value do not automatically create one million meters. However, one million distinct URIs put into a label can cause problems even if each URI is called only once.

The solution has two parts: **produce controlled-cardinality labels at the source**, and then **set limits to protect when data exceeds expectations**. Setting a limit alone while keeping raw URIs can cause gaps in monitoring data.

## 2. Setting a Label Budget Based on Measurement Semantics

### 2.1. Value Limit Differs from Key Count

A meter with three label keys `method`, `status`, and `uri` can still produce many combinations:

```text
4 methods × 6 statuses × 50 URIs = up to 1,200 combinations
```

This is an estimate when all combinations occur; actual data may be smaller. Across multiple instances, per-instance series also contribute to the system-wide total.

Therefore, capping `uri` at 50 values does not mean the entire system has only 50 meters or 50 series. Other labels can still multiply, and each timer can export multiple statistics.

Also do not confuse cardinality with string length. Truncating every URI to 100 characters does not guarantee the number of distinct URIs will stay small. Hashing URIs into short codes also usually preserves cardinality if each input still gets its own code.

### 2.2. Labels Must Serve Grouping, Not Per-Event Lookup

Dimensions with well-defined value sets are usually more suitable:

| Need | Usable Label | Data That Should Not Go Raw Into Metrics |
| --- | --- | --- |
| Compare HTTP routes | Route template such as `/orders/{id}` | Order ID substituted into the path |
| Compare processing outcomes | Agreed success/failure categories | Full error message text |
| Compare providers | Finite set of providers | Free-form input string |
| Compare user groups | Defined service tier | User ID or email |
| Inspect search behavior | Search operation category | Full user search query |

When you need to look up a specific transaction or request, use an appropriate mechanism such as logs or traces according to the application's data policy. Do not turn aggregated metrics into an index of every event.

Prometheus also recommends careful consideration for labels with many values because each combination creates additional time series. [Instrumentation guidelines — Do not overuse labels](https://prometheus.io/docs/practices/instrumentation/#do-not-overuse-labels).

### 2.3. Reserve Room for the Fallback Group

If a label policy allows three values `primary`, `backup`, and `other`, the budget must include `other`. If room is left only for common values, the fallback group can be denied at the exact moment it is needed most.

A budget should derive from valid routes, status groups, and business values, with headroom for expected changes. Do not keep raising thresholds just to chase every new ID.

## 3. Fixing URIs at the Source Using Route Templates

### 3.1. Server Side: Use the Matched Route

In Spring MVC, a declaration like this expresses a route template:

```java
@GetMapping("/orders/{id}")
```

This is the annotation portion of an existing handler, not a standalone program. The real order ID is used for business processing; the metric label should describe the route template.

Spring's HTTP observability integrations use matched route information when available. If you see metrics carrying thousands of values like `/orders/101`, check:

- Whether manual instrumentation code uses `request.getRequestURI()` as a label.
- Whether a custom observation convention overrides the route template with the actual path.
- Whether a gateway, router, or external integration strips route template information.
- Whether unmatched requests have arbitrary raw paths attached directly as labels.

For unmatched requests, a finite fallback group is needed. Values such as `NOT_FOUND` or `UNKNOWN` may appear depending on integration, status, and version; do not assume every failed request must carry one specific fixed label.

The essential invariant is not creating a new group for every 404 path sent by callers. [Spring Framework's Observability Support documentation](https://docs.spring.io/spring-framework/reference/integration/observability.html) describes `uri` at the HTTP observation level and high-cardinality information.

### 3.2. HTTP Client Side: Pass Template and Variables Separately

With an instrumented `RestClient`, compare these two styles:

```java
// Path has already been concatenated into a concrete string.
client.get()
        .uri("/orders/" + orderId)
        .retrieve()
        .toBodilessEntity();

// URI template and variable value are passed separately.
client.get()
        .uri("/orders/{id}", orderId)
        .retrieve()
        .toBodilessEntity();
```

This illustrates usage with an existing `client` and `orderId`. The second style preserves the template before variable substitution for integrations that support it.

Use the builder configured by Spring Boot for the corresponding client to receive the application's observability integration. Do not assume every manually instantiated client already emits metrics.

Pre-built absolute URIs, string-concatenated paths, UUIDs, slugs, pagination tokens, or directly embedded query values can lose the template or expand the value set if passed raw into labels. Inspect the actual `uri` label, because some APIs fall back to a placeholder when no template is available instead of exporting the real path.

Do not simply strip all digits using a generic regex. That approach can still miss UUIDs/slugs, or wrongly merge routes with different meanings such as an API version segment. Information from the router or the template passed at the call site is more reliable than guessing from path strings.

### 3.3. For Custom Metrics, Normalize Before Registering the Meter

If the application records a `Timer` or `Counter` directly, determine the label value before calling builder/register. Use a finite lookup table or structured business metadata.

For example, every request classified by the router as "view single order" uses `/orders/{id}`. Unmatched paths use an agreed group. Do not maintain an unbounded map from every raw URI to a normalized URI solely for metrics.

Normalization is a decision about data semantics: once grouped, the metric no longer distinguishes individual IDs. That is intentional for aggregated observability, not a replacement for detailed storage.

## 4. How Does a Tag-Limiting MeterFilter Work?

Micrometer provides the API:

```java
MeterFilter.maximumAllowableTags(
        "http.server.requests",
        "uri",
        100,
        MeterFilter.deny());
```

This is an example filter configuration with four components:

| Parameter | Meaning |
| --- | --- |
| `"http.server.requests"` | Meter name prefix to which it applies |
| `"uri"` | Label key to cap |
| `100` | Number of distinct values allowed per the filter's mechanism |
| `MeterFilter.deny()` | Reject meter registration when a new value exceeds the threshold |

The first argument is a **prefix**, not a regular expression or a URI filter. If multiple meter names match the prefix, the shared scope of this filter must be accounted for.

Key points to understand:

- The limit is on the number of label values, not requests per second.
- Meters using already-accepted values can continue recording many more times.
- New URI values exceeding the threshold are not automatically converted into `other` by `deny()`.
- Denying a meter does not reject HTTP requests or cancel business logic.
- On `DENY`, the registry returns a non-recording instrument (NOOP); recording calls can still run without adding that sample to collected data.
- This filter does not promise random sampling, keeping the top N important routes, or applying an N-minute sliding window.

Therefore, this is a safeguard, not the sole solution for fixing high-cardinality URIs. [Micrometer's Meter Filters documentation](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html) describes the limiting API and behavior of denied meters.

If initial raw URIs exhaust the budget, a valid route arriving later may have no measurements. The remaining data is not necessarily representative of total traffic and should not be treated as a random statistical sample.

## 5. Java Experiment: Raw Limit vs. Normalization Produce Different Results

The example uses Java 21 and Micrometer 1.13.0. It simulates eight metric recordings without starting an HTTP server. The name `demo.http.requests` is chosen separately to distinguish it from Spring Boot's auto-configured HTTP metric.

Three scenarios run on three fresh registries:

1. `RAW`: uses raw URIs with no limit.
2. `LIMIT_ONLY`: uses raw URIs, allowing only two `uri` values.
3. `TEMPLATE_AND_LIMIT`: normalizes at the source, then applies the same limit of two values.

### 5.1. Dependency

Create `pom.xml` in a standalone practice directory:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>uri-tag-budget-lab</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
</project>
```

The version is pinned to reproduce the experiment. In a Spring Boot application, use the Micrometer version managed by Spring Boot.

### 5.2. Complete Program

Save at `src/main/java/demo/UriTagBudgetDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.time.Duration;
import java.util.Collection;
import java.util.List;
import java.util.stream.Collectors;

public class UriTagBudgetDemo {
    private static final String METRIC = "demo.http.requests";
    private static final List<String> PATHS = List.of(
            "/orders/101", "/orders/102", "/orders/103",
            "/orders/104", "/orders/105",
            "/missing/a", "/missing/b", "/orders/101");

    public static void main(String[] args) {
        run("RAW", false, 0);
        run("LIMIT_ONLY", false, 2);
        run("TEMPLATE_AND_LIMIT", true, 2);
    }

    private static void run(String label, boolean useTemplate, int limit) {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            if (limit > 0) {
                registry.config().meterFilter(MeterFilter.maximumAllowableTags(
                        METRIC, "uri", limit, MeterFilter.deny()));
            }

            for (String path : PATHS) {
                boolean matched = path.matches("/orders/[0-9]+");
                String uri = useTemplate
                        ? (matched ? "/orders/{id}" : "NOT_FOUND")
                        : path;
                String status = matched ? "200" : "404";
                Timer.builder(METRIC)
                        .tags("method", "GET", "status", status, "uri", uri)
                        .register(registry)
                        .record(Duration.ofMillis(1));
            }

            Collection<Timer> timers = registry.find(METRIC).timers();
            long recorded = timers.stream().mapToLong(Timer::count).sum();
            String uris = timers.stream()
                    .map(timer -> timer.getId().getTag("uri"))
                    .distinct().sorted()
                    .collect(Collectors.joining(", ", "[", "]"));

            System.out.printf("%s attempts=%d meters=%d recorded=%d%n",
                    label, PATHS.size(), timers.size(), recorded);
            System.out.println(label + " uris=" + uris);
        } finally {
            registry.close();
        }
    }
}
```

The `/orders/[0-9]+` rule is a tiny router simulation intended solely for the experiment's input set. It is not an algorithm for normalizing every URI in a real application. In real systems, prefer matched route information or a known template at the call site.

Unmatched paths in the simulation are assigned status 404 and the `NOT_FOUND` group when normalized. No real request is blocked by the filter in this program.

### 5.3. Compile and Run

From the directory containing `pom.xml`, use Maven to download dependencies and JDK 21 to compile. The first download requires access to the Maven repository.

On PowerShell/Windows:

```powershell
mvn -q dependency:copy-dependencies -DoutputDirectory=target/dependency
javac --release 21 -cp "target/dependency/*" -d target/classes src/main/java/demo/UriTagBudgetDemo.java
java -cp "target/classes;target/dependency/*" demo.UriTagBudgetDemo
```

On Linux/macOS, use the same first two commands and replace the run command with:

```bash
java -cp "target/classes:target/dependency/*" demo.UriTagBudgetDemo
```

Exact stdout:

```text
RAW attempts=8 meters=7 recorded=8
RAW uris=[/missing/a, /missing/b, /orders/101, /orders/102, /orders/103, /orders/104, /orders/105]
LIMIT_ONLY attempts=8 meters=2 recorded=3
LIMIT_ONLY uris=[/orders/101, /orders/102]
TEMPLATE_AND_LIMIT attempts=8 meters=2 recorded=8
TEMPLATE_AND_LIMIT uris=[/orders/{id}, NOT_FOUND]
```

### 5.4. Explaining the Results

In `RAW`, seven distinct paths create seven timers. `/orders/101` is recorded twice so the total count is eight, even though the meter count is seven.

In `LIMIT_ONLY`, `/orders/101` and `/orders/102` are accepted first. Subsequent new URIs are denied. The final attempt reuses `/orders/101`, so it is still recorded; total count drops to three.

In `TEMPLATE_AND_LIMIT`, five different order IDs all become `/orders/{id}`, while the two unmatched paths both become `NOT_FOUND`. Only two URI values exist, yet all eight recordings are preserved.

| Scenario | Meter Count | Total Recorded | Key Takeaway |
| --- | --- | --- | --- |
| Raw URI | 7 | 8 | Preserves data, but group count grows with input |
| Limit only | 2 | 3 | Protects group count by losing samples above the cap |
| Normalize then limit | 2 | 8 | Small group set still captures all attempts in the experiment |

Do not interpret `recorded=3` as the application only processing three attempts. All eight attempts passed through the loop; five no longer contributed to retained measurements.

## 6. Safeguard Configuration in Spring Boot

### 6.1. HTTP Server and Client URI Limits

Spring Boot 3.3 provides two properties:

```properties
management.metrics.web.server.max-uri-tags=100
management.metrics.web.client.max-uri-tags=100
```

The value 100 here is the documented default for this version branch, not an optimal budget recommendation for every application. New URIs exceeding the threshold are rejected by the filter for metrics belonging to the corresponding integration.

Verify the exact version, metric names, and active integrations when changing configuration. These two HTTP properties do not automatically cap every label on every business metric. [Spring Boot 3.3 Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html) lists the properties, defaults, and denial behavior.

If there are more valid routes than the budget, redesign the budget or measurement scope. If there is only one route yet thousands of URIs contain IDs, fix label generation first. The two situations should not be treated identically by bumping the number.

### 6.2. Limiting a Custom Business Label

For application metrics, you can register a `MeterFilter` as a bean. The example below assumes the `provider` label contract consists solely of `primary`, `backup`, and `other`:

```java
@Bean
MeterFilter checkoutProviderBudget() {
    return MeterFilter.maximumAllowableTags(
            "checkout.", "provider", 3, MeterFilter.deny());
}
```

This is a method placed inside an application `@Configuration` class, importing `org.springframework.context.annotation.Bean` and `io.micrometer.core.instrument.config.MeterFilter`. It is not a standalone Java program.

The label producer must map cleanly into those three groups. If free-form provider strings are still emitted into the label, the first three arbitrary values encountered can exhaust the budget; the filter does not enforce the business contract for you.

Configure filters during initialization, before registering related meters. Do not attach filters repeatedly per request or create a new registry in a service to bypass limits.

### 6.3. Do Not Overlook Filter Order and Scope

A filter can alter identity, accept, or deny a meter. A filter that accepts an entire group can prevent subsequent accept/deny checks from applying as intended. Inspect the filter chain rather than concluding you are protected merely because a limit bean is present.

If using a label-mapping filter as a transitional measure, the logic must stay consistent with meter identity and not depend arbitrarily on the current request. Prefer producing structured labels at the source so the policy is easy to verify and less reliant on internal mapping rules.

## 7. Approaches That Do Not Fix the Root Cause

### 7.1. Renaming Metrics or Changing Case Style

Converting dots to underscores, changing `uri` to `path`, or inventing another metric name does not reduce the number of URI values. If data still contains every ID, the problem merely moves under a new name.

### 7.2. Hashing or Truncating URIs

Hashing changes representation; it does not reduce the number of distinct values. Truncation can cause unintended collisions while still leaving a huge number of groups. Normalize according to routes or meaningful business categories.

### 7.3. Immediately Deleting the Entire URI Label

Dropping the label can cut series count, but it also removes the ability to distinguish endpoints. That may be a deliberate choice for an aggregate measurement, not the default option for every HTTP metric.

Normally you should preserve finite route templates before considering dropping this classification dimension altogether.

### 7.4. Using Dashboard Regexes to Merge After Collection

Grouping URIs in queries makes charts readable, but it does not stop the application from creating many meters or the monitoring system from storing many series.

Similarly, dropping labels at the collection tier can reduce downstream storage, but it does not fix the volume of meters already created inside the JVM. Know which layer a measure actually protects.

### 7.5. Raising Thresholds or Restarting to Silence Alerts Temporarily

Raising thresholds is only appropriate when the valid value set has been evaluated. If values grow per resource ID, a higher threshold can still fill up quickly.

Restarting does not turn raw URIs into route templates. Changing a filter also does not automatically rewrite all existing meters or erase history stored in the monitoring system. You need a verified config/code change and follow-up monitoring of new data.

## 8. Verifying After the Fix: Fewer Groups While Keeping Complete Measurements

Do not check only whether "meter count went down". A deny filter also lowers meter count, yet can simultaneously drop part of the traffic as the experiment demonstrated.

A useful verification pass includes:

1. Pick one instance and a controllable set of inputs.
2. Send many different IDs to the same valid route.
3. Send unmatched requests across several different paths.
4. Inspect the `uri` values appearing in the metric.
5. Compare the increase in total count against completed requests within the measured scope.
6. Check other labels such as method, status, and business labels to ensure none are growing unexpectedly.

If the `metrics` endpoint is exposed, you can query:

```bash
curl "http://127.0.0.1:8080/actuator/metrics/http.server.requests"
curl --get "http://127.0.0.1:8080/actuator/metrics/http.server.requests" --data-urlencode "tag=uri:/orders/{id}"
```

These commands are for a running Spring Boot application, not the standalone Java program in section 5. On PowerShell you can use `curl.exe`. Use the exact port, management path, and label values actually served by your application.

In the detail response, check available tag values and statistics. Compare before/after counts rather than comparing cumulative values directly against new requests. When summing multiple groups, keep the scope consistent and avoid mixing Actuator inspection requests into the business traffic under test.

These goals should hold simultaneously:

| Check Item | Expected Outcome |
| --- | --- |
| Same route, many resource IDs | Same route template value |
| Many unmatched paths | Finite fallback group set |
| Valid traffic within budget | Total measurement count remains complete |
| New values exceeding budget | Denial behavior is detected and understood |
| Remaining labels | No other unbounded growth dimension |

Once a limit triggers, do not compute application-wide error rates or traffic solely from retained metrics and treat them as complete data. Cross-check another source and identify the missing scope.

## 9. Monitoring So Limits Do Not Become Blind Spots

Operations must know when measurements are being denied. You can use the integration's built-in alerts or a violation tracking mechanism with a finite label set.

If writing custom notifications when a threshold is exceeded, do not create a new metric labeled with the rejected URI itself; that recreates the problem under a different name. Logging every over-limit request can also be too noisy, so rate and aggregation levels must be controlled.

Evaluate group count over time alongside request volume and application route changes. A deployment adding legitimate routes differs from random request traffic generating thousands of new paths.

With Observation, distinguish low-cardinality data used for metrics from high-cardinality detail data. Moving IDs to an appropriate detail field does not mean that data has zero cost; it simply avoids using IDs as metric aggregation dimensions.

A policy can specify:

- Which labels are permitted and their expected value sets.
- Whether URI templates come from the router or client call-site templates.
- The fallback group when a route cannot be determined.
- Protective limits per metric or metric group.
- How denied samples are detected and how completeness is verified.

## 10. Check Your Understanding

1. One million requests all use `uri=/orders/{id}`. What is the cardinality of the URI label alone?
2. Why did capping raw URIs at two in the experiment retain only three out of eight measurements?
3. Does `MeterFilter.deny()` automatically put remaining URIs into `other`?
4. Does capping URI at 100 guarantee the entire registry has at most 100 meters?
5. Does normalizing in a dashboard prevent JVM memory from being used to hold meters per raw URI?

Answer key: one value; the first two URIs were accepted and the last attempt reused an existing URI; it does not merge automatically; no, because other metric names and label dimensions remain; no, because queries run after meter creation and metric collection.

The complete solution is to keep labels describing meaningful operation groups, normalize before creating measurements, add protective thresholds, and verify that metrics still accurately represent the scope you intend to observe.
