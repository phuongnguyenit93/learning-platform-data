# Discovering Available Metrics with the Metrics Endpoint

## 1. Start with the question "which metrics does this application currently have?"

When you want to inspect JVM memory, HTTP traffic, or a business counter, do not guess metric names from a dashboard or another application. Spring Boot Actuator provides the `metrics` endpoint to discover the metric names currently known to the registries the endpoint uses.

The basic workflow has three steps: **fetch the list of names → pick an actual name → read its details and narrow by tags when needed**. Afterward, you can trigger a test operation to observe registration or value changes.

```text
GET /actuator/metrics
        |
        v
names: currently available metric names
        |
        v
GET /actuator/metrics/{metric-name}
        |
        v
description, unit, measurements, filterable tags
```

This endpoint serves application-side diagnostics. Seeing a name in the list does not prove the metric was successfully exported to a monitoring system, has historical data, or that the overall system is healthy.

This lesson uses Spring Boot **3.3.0**, Micrometer **1.13** line, and Java 17+ to verify examples. Configuration and data in a real application must be verified directly; do not treat a fixed name list as a standard across every project.

## 2. Preparing HTTP access to the endpoint

### 2.1. Distinguishing dependencies, endpoint enablement, and HTTP exposure

For a Spring MVC application, common dependencies for the experiment are `spring-boot-starter-web` and `spring-boot-starter-actuator`. Actuator integrates Boot's metrics infrastructure; the `metrics` endpoint also requires a registry in the application context.

Distinguish three layers of conditions:

| Condition layer | What to check |
| --- | --- |
| Metrics infrastructure | Are Micrometer and an appropriate `MeterRegistry` configured? |
| Endpoint enabled | Does `management.endpoint.metrics.enabled` allow the endpoint to exist under active configuration? |
| Endpoint exposed over HTTP | Does `management.endpoints.web.exposure.include`/`exclude` allow access over the web? |

In Boot 3.3, by default only `health` is exposed over HTTP. Thus, seeing `/actuator/health` work does not mean `/actuator/metrics` is accessible yet. `exclude` also takes precedence over `include` when they conflict. [Boot 3.3 endpoint enablement and exposure rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Illustrative configuration:

```yaml
management:
  endpoint:
    metrics:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,metrics
```

You do not need to expose all of Actuator just to read metrics. If security configuration is present, read authorization is still governed by that configuration; exposing an endpoint over HTTP does not automatically grant access to everyone.

Regarding implementation, `MetricsEndpoint` auto-configuration checks endpoint availability conditions and a `MeterRegistry` bean. Adding a string to `include` does not automatically create business metrics the application has not registered. [MetricsEndpointAutoConfiguration 3.3.0](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/MetricsEndpointAutoConfiguration.java).

### 2.2. Confirm the exact URL before analyzing data

Commands in this lesson use the default URL `http://127.0.0.1:8080/actuator/metrics`. If the application changes the management port, base path, context path, or sits behind a reverse proxy, use the actual corresponding URL.

For example, when changing only `management.endpoints.web.base-path` to `/manage` while keeping the same default port/context, the path becomes `/manage/metrics`. Do not explain away every 404 as "no metrics yet" before confirming you called the right endpoint.

## 3. Fetching the name list with GET /actuator/metrics

```bash
curl -i http://127.0.0.1:8080/actuator/metrics
```

When the endpoint is reachable, expect HTTP 200 and JSON containing a `names` field. The following example only illustrates the structure with a few common names, not a mandatory list or the full response of every application:

```json
{
  "names": [
    "jvm.memory.used",
    "jvm.threads.live",
    "process.uptime"
  ]
}
```

`names` is an array of names currently known to the endpoint. It does not contain all measurement values, does not describe every tag set, and is not a list of the application's HTTP APIs. To view those details, select an exact name and inspect its details. [Metrics endpoint HTTP contract](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

### 3.1. Name count differs from meter count

The same name `demo.work.completed` can have meters for `channel=web` and `channel=mobile`. The list still contains only a single string `demo.work.completed`; there is no separate entry per tag set.

In Boot 3.3.0, the listing implementation collects names into a set and traverses child registries if the registry is composite. Thus, counting the length of `names` counts distinct names at this endpoint layer, not meter IDs, tag combinations, heap usage, or time-series counts in a monitoring system. [listNames/collectNames 3.3.0 source](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/metrics/MetricsEndpoint.java).

This version's implementation uses a structure that sorts names, yet consuming tools should look up by name string rather than element position. Do not assume the third element is always the "memory metric" across runs.

### 3.2. The list is not a static catalog

Meters created by binders can appear right at startup. A meter registered inside a business branch only appears once that registration code has executed. A missing metric name is not always a bug; check when and under what condition it is created.

Conversely, a pre-registered counter that has not yet been incremented may already appear by name with a count of 0. **A meter not existing** differs from **a meter existing with a current value of 0**.

Configuration, libraries on the classpath, application type, runtime, and executed operations can all cause the list to vary. An application not using JDBC does not necessarily have connection-pool metrics, just as an HTTP meter may not yet have samples before an appropriate observation flow completes.

Calling HTTP endpoints themselves can also create or update HTTP metrics after the request finishes. Therefore, do not require the total application name count to stay immutable between two discovery calls.

## 4. Finding the name groups of interest

You can start from an operational question and look for matching prefixes/names in the actual output:

| Question | Name groups you might see | Notes |
| --- | --- | --- |
| How are JVM memory and threads being used? | `jvm.memory.*`, `jvm.threads.*` | Tags and units can distinguish memory areas/thread states |
| How long has the process been running? | `process.uptime` | A single process metric is not automatically cluster-wide data |
| Is HTTP being observed? | `http.server.requests` | You may need to send a request and wait for it to finish |
| Has experimental business work been recorded? | `demo.work.completed` in the example | The name only appears after the first registration per example code |

These are search hints, not a way to determine meter type solely from a prefix. Pick a real name from `names`, read its description and unit, and only then interpret it.

### 4.1. Filtering results on the client tool side

If `jq` is available, you can print one name per line or filter the JVM group:

```bash
curl -s http://127.0.0.1:8080/actuator/metrics | jq -r '.names[]'
curl -s http://127.0.0.1:8080/actuator/metrics | jq -r '.names[] | select(startswith("jvm."))'
```

With PowerShell, no `jq` installation is needed:

```powershell
$metricNames = (Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/metrics').names
$metricNames | Where-Object { $_ -like 'jvm.*' }
```

These filters run in the JSON client tool. Do not invent query parameters like `prefix=jvm` or `page=1` and assume the endpoint filtered/paginated names; the listing API does not declare such parameters.

In PowerShell where `curl` is an alias, use `curl.exe` if you want to run the exact curl syntax in this lesson. When errors occur, use `-i` to see HTTP status; looking only at an empty body can hide important clues.

## 5. Opening details of an available metric name

For example, if the list actually contains `jvm.memory.used`:

```bash
curl -i http://127.0.0.1:8080/actuator/metrics/jvm.memory.used
```

Details can include these fields:

| Field | How to use |
| --- | --- |
| `name` | Confirm the exact selected name |
| `description` | Understand the meaning when the meter provides a description |
| `baseUnit` | Know the unit if provided by the meter |
| `measurements` | Read `statistic`/`value` pairs |
| `availableTags` | View dimensions/values still available for narrowing |

Do not force every meter to have the same fields or statistics. Counters typically have COUNT; gauges typically have VALUE; timers can have COUNT, TOTAL_TIME, MAX. The goal of discovery is to find the right instrument and scope, not infer rate or latency from a name alone.

### 5.1. Use Micrometer names, not names exported under another convention

The name in the endpoint must match the name used in the registry/source code. If a monitoring system turns dots into underscores or adds statistic suffixes, do not copy that exported name verbatim into the URL and conclude the metric is missing.

For example, when the list shows `jvm.memory.used`, use `/actuator/metrics/jvm.memory.used`. Read the actual list first instead of guessing a variant like `jvm_memory_used`. [Naming rules at Boot 3.3 metrics endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.endpoint).

### 5.2. Narrowing by tags after reading availableTags

In the business example below, details show a `channel` tag with two values `web` and `mobile`. You can select just the web channel:

```bash
curl -s -G http://127.0.0.1:8080/actuator/metrics/demo.work.completed --data-urlencode "tag=channel:web"
```

The parameter uses the form `tag=key:value`. For multiple dimensions, repeat the `tag` parameter to apply them together. Use `--data-urlencode` to avoid manually escaping spaces or special characters in values.

Not filtering tags can return merged measurements across multiple matching meters sharing the same name. A total COUNT of 3 does not prove only one counter exists in the registry. Once a dimension is filtered, it may no longer appear in the response's `availableTags` because the endpoint only lists remaining dimensions you can still narrow down.

If the name exists yet no meter matches all selected tags, reading details can return 404. If the tag parameter lacks the separator, such as `tag=channel`, the invalid request can return 400. That is a data-selection error, distinct from the endpoint not being exposed over HTTP.

## 6. Complete experiment: a name appearing after a test operation

The experiment creates a small Boot Spring MVC application. The `/work` endpoint records a counter only when called; the counter is not pre-registered in the constructor. This makes before-and-after states clearly observable.

The application binds only to `127.0.0.1` and exposes only `health,metrics` over HTTP for local machine use. The sample project does not add Spring Security. If applying to an application with security enabled, use that application's appropriate administrative read permissions.

Create a project with a Boot 3.3-compatible Gradle wrapper and JDK 17 available. These APIs can also run on JDK 21 with matching project configuration.

```text
metrics-discovery-demo/
  build.gradle
  settings.gradle
  gradlew / gradlew.bat and gradle/wrapper/
  src/main/java/example/discovery/MetricsDiscoveryApplication.java
  src/main/resources/application.yml
```

`settings.gradle`:

```groovy
rootProject.name = 'metrics-discovery-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Versions in the example are pinned to reproduce the verified APIs, not as a deployment patch recommendation. For existing Boot projects, use Boot's dependency management to keep compatible Micrometer versions.

`src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoint:
    metrics:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,metrics
  metrics:
    use-global-registry: false
```

`use-global-registry: false` isolates the experiment from attaching the registry to Micrometer's shared static state; it does not disable the Spring-injected `MeterRegistry` and does not disable the metrics endpoint.

`src/main/java/example/discovery/MetricsDiscoveryApplication.java`:

```java
package example.discovery;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@RestController
public class MetricsDiscoveryApplication {
    private final MeterRegistry registry;

    public MetricsDiscoveryApplication(MeterRegistry registry) {
        this.registry = registry;
    }

    public static void main(String[] args) {
        SpringApplication.run(MetricsDiscoveryApplication.class, args);
    }

    @GetMapping("/work")
    public String work(
            @RequestParam(name = "channel", defaultValue = "web") String channel) {
        if (!"web".equals(channel) && !"mobile".equals(channel)) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "channel must be web or mobile");
        }

        Counter.builder("demo.work.completed")
            .description("Completed demo work")
            .baseUnit("operations")
            .tag("channel", channel)
            .register(registry)
            .increment();

        return "recorded:" + channel;
    }
}
```

Only two channel labels are valid: `web` and `mobile`. Code does not take an arbitrary user string as a tag, keeping the experiment's categorization set bounded. Calling `/work` merely simulates a work-completion point and returns a recorded acknowledgment rather than running a real business workflow.

Start from the project directory:

```bash
./gradlew bootRun
```

On Windows PowerShell use `.\gradlew.bat bootRun`. This program requires Spring/Micrometer dependencies; do not run with a standalone `javac MetricsDiscoveryApplication.java` missing a classpath. Startup log lines vary by environment, whereas the HTTP response bodies for the valid requests below are deterministic.

### 6.1. Before calling /work

Start a fresh application instance and fetch the list:

```bash
curl -i http://127.0.0.1:8080/actuator/metrics
```

Expect HTTP 200 with `names`, yet `demo.work.completed` is absent because the counter registration code has not executed yet. You can quickly check with PowerShell:

```powershell
$before = (Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/metrics').names
$before -contains 'demo.work.completed'
```

The expression evaluates to `False`. Read details directly before the counter exists:

```bash
curl -i http://127.0.0.1:8080/actuator/metrics/demo.work.completed
```

Expect HTTP 404 under the sample configuration. This does not contradict `/actuator/metrics` returning 200: the endpoint exists, yet the chosen metric name has no matching registered data yet.

### 6.2. Generating exactly three recordings

Use another terminal while the application keeps running:

```bash
curl -i "http://127.0.0.1:8080/work?channel=web"
curl -i "http://127.0.0.1:8080/work?channel=web"
curl -i "http://127.0.0.1:8080/work?channel=mobile"
```

All three valid requests return HTTP 200. The bodies are `recorded:web`, `recorded:web`, and `recorded:mobile` respectively. Each call increments exactly one counter matching the selected channel.

Subsequent count results assume starting from a fresh process with only those three `/work` calls. Calling `/work` again increases totals; reading metrics does not itself invoke the `/work` handler.

### 6.3. Re-reading the list

```powershell
$after = (Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/metrics').names
$after -contains 'demo.work.completed'
@($after | Where-Object { $_ -eq 'demo.work.completed' }).Count
```

The two results are `True` and `1` respectively. The custom name appears only once even though two distinct meters exist by channel tag. Do not assert that the entire array length increased by exactly 1, because making HTTP calls can cause other HTTP-observing meters to appear.

### 6.4. Opening details and selecting a channel

```bash
curl -s http://127.0.0.1:8080/actuator/metrics/demo.work.completed
```

Response corresponding to the three recordings:

```json
{
  "name": "demo.work.completed",
  "description": "Completed demo work",
  "baseUnit": "operations",
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 3
    }
  ],
  "availableTags": [
    {
      "tag": "channel",
      "values": [
        "mobile",
        "web"
      ]
    }
  ]
}
```

Element ordering inside arrays is not something you should rely on to identify a channel; read the name string. COUNT equals 3 is the sum across matching meters with that name at read time, not the count of names in `names` and not automatically 3 calls/second.

Filter specifically for the web channel:

```bash
curl -s -G http://127.0.0.1:8080/actuator/metrics/demo.work.completed --data-urlencode "tag=channel:web"
```

Result:

```json
{
  "name": "demo.work.completed",
  "description": "Completed demo work",
  "baseUnit": "operations",
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 2
    }
  ],
  "availableTags": []
}
```

A COUNT value of 2 confirms the filter. `availableTags` is empty here because the example has only the channel dimension and that dimension has already been selected. It does not mean the counter lost its tag in the registry.

### 6.5. Comparing not-found and invalid-request cases

| Request in sample app | Expected HTTP | Meaning |
| --- | --- | --- |
| `GET /actuator/metrics` | 200 | Name list can be read |
| Details of `demo.work.completed` before first `/work` call | 404 | Name not yet registered |
| `GET /work?channel=web` or `mobile` | 200 | One more occurrence recorded |
| Details after three recordings | 200 | Description, unit, measurements, and tags present |
| Details with `tag=channel:web` | 200 | Web channel meter selected |
| Details with `tag=channel:unknown` | 404 | No meter matches filter |
| Details with `tag=channel` | 400 | Invalid tag format |
| `GET /work?channel=unknown` | 400 | Sample code rejects label outside allowed set |

These statuses are verified under the sample configuration. With Spring Security, proxies, custom paths, or custom error handlers, analyze the actual response-producing layer instead of expecting every system to return the exact same error shape.

## 7. When an expected metric is missing

### 7.1. Separate endpoint access errors from name-lookup errors

First verify whether `GET /actuator/metrics` returns HTTP 200 with `names`. If not, check port/path, dependencies, endpoint enablement config, web exposure, `exclude`, and access permissions. Do not evaluate metric names yet.

If the list is readable, verify the exact Micrometer name and search in the current array. Do not use a name transformed by exporter conventions, and do not look for a name from another project and treat its absence as an Actuator bug.

### 7.2. Check registration lifecycle and registry source

For custom meters, did the registration code actually run? Is a filter denying it? Does the recording component use the Spring-managed `MeterRegistry`, or did it instantiate `new SimpleMeterRegistry()` elsewhere?

Registering into an isolated registry does not automatically make the application's endpoint see it. The example's dependency-injection pattern ensures both recording and the application's metrics infrastructure share the managed registry.

For metrics from libraries or binders, the corresponding component and configuration conditions must be met. A name appearing only after a specific operation or resource creation can be normal behavior.

### 7.3. Distinguish easily confused properties

| Property | What it controls |
| --- | --- |
| `management.endpoint.metrics.enabled` | Enabling the metrics endpoint |
| `management.endpoints.web.exposure.include`/`exclude` | Which endpoints are exposed over HTTP |
| `management.metrics.enable.<prefix>` | Accepting/denying meters by name prefix via metrics config |
| `management.metrics.use-global-registry` | Attaching configured registries to the static global registry |

For example, `management.metrics.enable.demo=false` can filter out meters starting with `demo`, even while `/actuator/metrics` still works and JVM names remain listed. Do not try fixing it by exposing more endpoints when the root cause is that the meter was denied by a filter. [Boot 3.3 per-meter properties](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing.per-meter-properties).

### 7.4. Check the right process and timestamp

Restarting the application loses custom meters that are only registered by operations not yet re-executed. With multiple instances, a `/work` call may hit instance A while the next metrics read hits instance B. A differing list in that case does not prove a metric "vanished."

Early-registered meters can exist with value 0 right after startup; late-registered meters require the triggering operation. Always state reproduction steps and process boundaries when comparing results.

## 8. Conclusions the name list does not provide

- You cannot tell whether the system is healthy or failing merely from seeing `http.server.requests`.
- You cannot tell total meter/tag counts or memory usage from the length of the `names` array.
- You cannot tell requests per second or multi-hour trends from a single snapshot of current names/values.
- You cannot confirm data is reaching Prometheus/OTLP or another backend just because the endpoint is readable.
- You do not automatically gather data from every instance, arbitrary registry, or library not wired into the metrics infrastructure.

`metrics` is an entry point for discovering and verifying instrumentation. For charts, historical queries, and alerts, you need a monitoring system and proper export configuration. The `prometheus` endpoint, if configured, has a different role/format; the two endpoints are not interchangeable simply by swapping URL names.

Do not loop continuously querying details of every name as a substitute for production metrics collection. Diagnostic tools should select names relevant to the question under investigation and cross-check against real operational observability sources.

## 9. Repeatable discovery procedure

1. **Confirm the right application, instance, port, and base path.** Record HTTP status before reading data.
2. **Fetch `/metrics` and store the name list in your client tool.** Search names by question, not by element index.
3. **Open details of a real name.** Read description, unit, statistics, and available tags.
4. **Trigger a clearly bounded test operation.** Know which code registers/records the meter and the expected call count.
5. **Re-read the name list and details.** Distinguish a newly appearing name from a value change on an existing meter.
6. **Filter tags if the name represents multiple groups.** Confirm each group before interpreting the total.
7. **State conclusions within exact scope.** Specify which instance/timestamp the data covers and what remains unverified.

For this lesson's experiment, completion evidence is: the list is readable; the custom name is absent before the operation and present afterward; the name is not duplicated across two channels; total and filtered details match the three requests sent. You do not need to rely on a fixed total count of JVM names.

## 10. Self-check

1. `/actuator/health` returns 200 while `/actuator/metrics` returns 404. List the configuration layers to check before editing counter registration code.
2. The list contains 50 names. Why can you not conclude the registry holds only 50 meters or the monitoring system has only 50 series?
3. How does pre-registering a counter with value 0 differ from registering the counter only on the first business call?
4. Run the experiment from a fresh process: call web twice and mobile once; predict the name's appearance, total COUNT, and COUNT when filtering for web.
5. Why does `availableTags=[]` after filtering channel not prove the channel tag was deleted?
6. A name appears in the list yet details with a tag set return 404. Distinguish that case from a 404 on the listing endpoint itself.
7. A name was found using underscore style on a dashboard yet is missing when placed in the metrics URL. Where will you get the right name from, and what will you check next?

Discovering the metrics endpoint properly means finding **existing names, accurately scoped details, and before-and-after evidence of instrumentation**, before moving to deeper analysis or monitoring system configuration.
