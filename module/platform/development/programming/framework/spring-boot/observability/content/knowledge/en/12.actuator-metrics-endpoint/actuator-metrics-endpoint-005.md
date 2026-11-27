# Querying by Tag with the Spring Boot Actuator Metrics Endpoint

> **Chapter:** Actuator metrics endpoint  
> **Lesson:** Querying by tag  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production.

## 1. Real-World Problem: One Metric, Many Data Slices

A Spring Boot service exposes an order-creation API. On the dashboard, you see API calls rising and some requests returning errors. However, you need to know **whether errors occur mainly on the web or mobile channel**, or whether the `POST` method on `/api/orders` is truly affected.

Micrometer stores measurements (*meters*) under a name and **tag key–value** pairs. For example:

~~~text
orders.create.attempts{channel="web",    outcome="success"} → count = 120
orders.create.attempts{channel="web",    outcome="error"}   → count =   5
orders.create.attempts{channel="mobile", outcome="success"} → count =  80
orders.create.attempts{channel="mobile", outcome="error"}   → count =  10
~~~

Here `orders.create.attempts` is **one metric name** with four tag combinations. Querying by tag lets you select only the desired combinations.

With Spring Boot Actuator, a direct way to inspect this is:

~~~http
GET /actuator/metrics/orders.create.attempts?tag=channel:web
~~~

This query selects data with `channel=web`. To retrieve only web errors:

~~~http
GET /actuator/metrics/orders.create.attempts?tag=channel:web&tag=outcome:error
~~~

This is **tag-filtering syntax at the Actuator endpoint**, not PromQL. It is very useful for verifying whether labeling is right or wrong, checking a deployment, quickly investigating an incident, or supporting instrumentation testing.

**Expected outcomes:** master the `tag=key:value` syntax, how to combine multiple tags, understand the meaning of `measurements`/`availableTags`, distinguish metric names from Prometheus series names, and know when to switch to time-series queries instead of the Actuator endpoint.

## 2. What Capabilities Does the `/actuator/metrics` Endpoint Have?

Spring Boot Actuator provides the `metrics` endpoint to discover and inspect meters registered in the `MeterRegistry` used by the application.

| Path | Purpose | Example |
| --- | --- | --- |
| `GET /actuator/metrics` | List existing metric names | `jvm.memory.used`, `http.server.requests` |
| `GET /actuator/metrics/{metricName}` | View measurements and tags of a metric by Micrometer name | `/actuator/metrics/jvm.memory.used` |
| `GET /actuator/metrics/{metricName}?tag=k:v` | Include only meters with matching tag pair | `?tag=area:heap` |
| `GET /actuator/metrics/{metricName}?tag=a:x&tag=b:y` | Filter by multiple tag pairs | `?tag=method:POST&tag=status:500` |
| `GET /actuator/prometheus` | Export data in Prometheus format, **not** `/metrics` tag-query API | Series `*_total`, `*_seconds_count` |

`{metricName}` must be the **meter name in Micrometer**, typically dotted, such as `http.server.requests`. Metric names in Prometheus usually change per naming conventions, converting dots to underscores and adding units or suffixes. Do not look up `http_server_requests_seconds_count` as the Actuator path if the meter in the application is named `http.server.requests`.

In a default Spring Boot application, the paths above use the `/actuator` prefix when web endpoints are exposed; prefix, port, and base path can be changed by management configuration. In production environments, use the correct management URL for the application and restrict access.

## 3. Configuring Spring Boot for Practice

Examples target Spring Boot 3.x and can be adapted to your project version. With Maven and the Spring Boot parent/BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

`spring-boot-starter-actuator` enables metrics integration and management endpoints. `micrometer-registry-prometheus` is only needed when you want to export data in Prometheus format; it is **not required** to call `/actuator/metrics` in an application that already has an appropriate `MeterRegistry`.

Minimal `application.yml` configuration for a learning environment:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-service
~~~

A few notes:

- Exposing `metrics` only enables access to the endpoint; it **does not create business metrics automatically** if code has not executed the instrumented path.
- If the Prometheus registry is absent, the `prometheus` endpoint may not exist even if listed in exposure.
- The `management.metrics.tags.application` property adds a common tag to meters via proper configuration; actual tag names should be verified.
- In production, protect management endpoints with network policies, authentication/authorization, or a separate management port. Tag lists can expose internal structure, application state, and deployment information.
- Examples in this lesson use `localhost:8080`. If `management.server.port` or `management.endpoints.web.base-path` is configured, adjust the URL accordingly.

To view the list of meter names:

~~~bash
curl -s http://localhost:8080/actuator/metrics
~~~

Only after the desired name appears in the result should you proceed to query its tags.

## 4. Creating a Tagged Metric for Experimentation

To keep practice independent of HTTP instrumentation or JVM pool names, let's create a business Counter `orders.create.attempts`. Each order-creation execution records one result into either `outcome=success` or `outcome=error`, distinguished by `channel`.

~~~java
package example.orders;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderCreationService {
    private final MeterRegistry registry;

    public OrderCreationService(MeterRegistry registry) {
        this.registry = registry;
    }

    public void create(String incomingChannel, Runnable work) {
        String channel = normalizeChannel(incomingChannel);
        String outcome = "success";

        try {
            work.run();
        } catch (RuntimeException | Error ex) {
            outcome = "error";
            throw ex;
        } finally {
            registry.counter(
                "orders.create.attempts",
                "channel", channel,
                "outcome", outcome
            ).increment();
        }
    }

    private static String normalizeChannel(String incoming) {
        if ("web".equals(incoming)) return "web";
        if ("mobile".equals(incoming)) return "mobile";
        if ("partner".equals(incoming)) return "partner";
        return "other";
    }
}
~~~

**Explanation:**

1. `MeterRegistry` is injected by Spring Boot, so data goes into the configured registry. Do not create a separate registry directly inside the service.
2. `channel` is normalized into four bounded values (`web`, `mobile`, `partner`, `other`), preventing cardinality explosion.
3. `outcome` is determined after the result of `work.run()` is known. `finally` records exactly once per synchronous call, even when an exception occurs.
4. Both success and error branches share the same **metric name** but differ in tag combinations.
5. The example measures **attempts**, not successfully created orders. A retry counts as another attempt; clarify semantics before building SLOs.
6. If the application already has a Counter or Observation recording the same attempt count in this exact place, do not add a second measurement with the same function.

Example calls in a test or another service:

~~~java
orderCreationService.create("web", () -> repository.saveNewOrder());

orderCreationService.create("mobile", () -> {
    throw new IllegalStateException("Demo failure");
});
~~~

`repository` is a hypothetical business component; in tests/controllers, errors must be caught at the appropriate layer when continuing the scenario. In real products, avoid recording exception messages containing sensitive data as tags.

### Generating Predictable Test Data

Suppose a test environment has no background traffic, no retries, and you call:

| Channel | Success | Error | Total Attempts |
| --- | ---: | ---: | ---: |
| `web` | 12 | 3 | 15 |
| `mobile` | 8 | 2 | 10 |
| `partner` | 5 | 0 | 5 |
| **Total** | **25** | **5** | **30** |

In a fresh process with these exact calls, `orders.create.attempts` records **COUNT = 30**. Use tag queries to verify slices rather than inferring from the total alone.

## 5. `tag=key:value` Syntax: Reading a Single Condition

Basic syntax:

~~~text
GET /actuator/metrics/{metricName}?tag={tagKey}:{tagValue}
~~~

Example:

~~~bash
curl -s "http://localhost:8080/actuator/metrics/orders.create.attempts?tag=channel:web"
~~~

This means **select meters of that name whose `channel` tag has the exact value `web`**. It is not substring matching or regex. If an actual tag set has `channel=mobile-app`, filtering `channel=mobile` will not include it.

Cases to distinguish:

| Query | Data Selected |
| --- | --- |
| No tag parameter | All tag combinations of the metric present in the registry |
| `?tag=channel:web` | Only combinations with `channel=web` |
| `?tag=outcome:error` | All channels with `outcome=error` |
| `?tag=channel:mobile` | Combinations with `channel=mobile` |
| `?tag=channel:WEB` | Only `WEB` if it actually exists; does not match `web` by default |

To return a different metric, change the **meter name in the path**, not via `tag`. Tag queries only select meters carrying the corresponding key/value.

### Important Note About the Colon

The `tag` parameter has the format `key:value`. The key precedes the first colon, and the value follows it. When a value has special characters or URL characters, ensure the request is properly URL-encoded so `&` is not interpreted as a query parameter separator.

Prefer `curl -G --data-urlencode` in examples containing spaces, slashes, braces, or URL-significant characters.

## 6. Combining Multiple Tags: AND Logic

Actuator allows **repeating the `tag` parameter** to filter by multiple key–value pairs.

~~~http
GET /actuator/metrics/orders.create.attempts?tag=channel:web&tag=outcome:error
~~~

Interpretation: **`channel=web` AND `outcome=error`**. From the practice dataset in Section 4, we expect COUNT = 3.

~~~bash
curl -s "http://localhost:8080/actuator/metrics/orders.create.attempts?tag=channel:web&tag=outcome:error"
~~~

With safer curl encoding:

~~~bash
curl -sG "http://localhost:8080/actuator/metrics/orders.create.attempts" \
  --data-urlencode "tag=channel:web" \
  --data-urlencode "tag=outcome:error"
~~~

The same pattern applies to HTTP server metrics if those tags actually exist:

~~~bash
curl -sG "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=method:POST" \
  --data-urlencode "tag=status:500"
~~~

Common misconceptions:

- Two `tag` parameters **do not mean OR**. `tag=channel:web&tag=outcome:error` does not mean "web or error".
- Writing `tag=channel:web,outcome:error` is not multi-tag syntax for the endpoint; it is a single parameter and may be interpreted as a value containing a comma.
- Two mutually exclusive values for the same key, such as `tag=channel:web&tag=channel:mobile`, are not an OR. No normal meter carries two different values simultaneously for the same tag key.
- If you want **OR**, **regex**, **group by**, or time-based analysis, use a backend query API such as PromQL. With Actuator, you can query each slice separately and process results in your test or tool.

**Rule:** a fixed tag set identifies a group of measurements; repeating `tag=key:value` intersects the filter conditions.

## 7. URL Encoding: Querying Tags with Spaces, Slashes, and Route Templates

HTTP server metrics typically have a `uri` tag representing a **route template** (depending on configuration and framework), such as `/api/orders/{id}`. Querying as a raw URL can easily run into issues with special characters, shells, or clients.

Use:

~~~bash
curl -sG "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=method:GET" \
  --data-urlencode "tag=uri:/api/orders/{id}"
~~~

This preserves the value `/api/orders/{id}` while encoding it properly when sending the request. In PowerShell, `curl` may be an alias for another cmdlet; use `curl.exe` with the same arguments when standard curl behavior is needed.

If you want to inspect the JVM memory pool named `G1 Old Gen`:

~~~bash
curl -sG "http://localhost:8080/actuator/metrics/jvm.memory.used" \
  --data-urlencode "tag=area:heap" \
  --data-urlencode "tag=id:G1 Old Gen"
~~~

Whether this query matches depends on the **actual `id` list**. On JVMs using ZGC, Shenandoah, Parallel GC, or other versions, pool names might not include `G1 Old Gen`. Always inspect `availableTags` first.

### Values That Should Not Be Used as Tags

Do not put high-variance values such as `orderId`, `userId`, `requestId`, tokens, full query strings, or URLs containing concrete IDs into metric tags. Tag querying does not turn high-cardinality data into a sound design: those values can create thousands or millions of time series.

For example, `uri=/api/orders/{id}` is a bounded route template, unlike `uri=/api/orders/123456` generated anew for every order. When you need to investigate a specific request, use logs/traces with trace IDs or controlled span attributes instead of adding request IDs as metric labels.

## 8. Reading the JSON: `measurements` and `availableTags`

When querying a metric, Actuator typically returns JSON containing `name`, `description`, `baseUnit`, `measurements`, and `availableTags`. Illustrative example for the Counter after filtering `channel=web`:

~~~json
{
  "name": "orders.create.attempts",
  "description": null,
  "baseUnit": null,
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 15.0
    }
  ],
  "availableTags": [
    {
      "tag": "outcome",
      "values": ["success", "error"]
    }
  ]
}
~~~

This illustrative example matches the Section 4 data: 12 successes and 3 errors on web, total COUNT = 15. Actual output may include other tags such as `application` or different ordering, depending on Spring Boot/Micrometer configuration.

Field explanations:

| JSON Field | Meaning |
| --- | --- |
| `name` | Metric name looked up by Micrometer name |
| `description` | Metric description if available; may be `null` |
| `baseUnit` | Base unit if defined by the meter; may be `null` |
| `measurements` | Statistics provided by the meter and aggregated values across matching meters |
| `availableTags` | Remaining tags/values usable to narrow further within matching meters, depending on data and already-filtered tags |

### Statistics Depend on Meter Type

| Meter Type | Common Statistics | Do Not Misinterpret |
| --- | --- | --- |
| Counter | `COUNT` | Cumulative count since meter creation, not "requests/second" |
| Gauge | `VALUE` | Value at read time; can rise or fall |
| Timer | `COUNT`, `TOTAL_TIME`, `MAX` | Count of recorded samples; total duration and max are not p95 |
| DistributionSummary | `COUNT`, `TOTAL`, `MAX` (meter/version dependent) | Total sample amount differs from Timer duration |
| LongTaskTimer | Active task count and running duration, under corresponding statistics | Not completed job count and p95 latency |

When querying a meter name that matches multiple tag combinations, the endpoint may **aggregate measurements across that set of meters**. Thus COUNT after filtering `channel=web` equals the sum of counts for `outcome=success` and `outcome=error`. Other statistics such as MAX have their own semantics; do not assume every value is a simple sum.

### Practice Reading `availableTags`

For a metric with `channel` and `outcome`:

1. Call without filters to see all available tag keys and values.
2. Add `tag=channel:web`; the result narrows to meters belonging to web.
3. Inspect `availableTags` to see which `outcome` values remain in that subset.
4. Add `tag=outcome:error` to narrow the result further.
5. Compare measurements with test scenario outcomes.

`availableTags` is a discovery tool, **not a raw data table of individual requests**. It does not provide a list of all tag combinations with separate measurements; when individual slices are needed, query with more conditions or use a time-series backend.

## 9. Detailed Example: Filtering HTTP Server Metrics by `method`, `uri`, and `status`

In a Spring MVC/WebFlux application with proper instrumentation, the `http.server.requests` metric may be present. Common tags depending on framework/version include `method`, `uri`, `status`, `outcome`, and `exception`. Do not assume every tag is guaranteed to exist across every version or endpoint.

### 9.1. Discovering Names and Tags

~~~bash
curl -s http://localhost:8080/actuator/metrics

curl -s http://localhost:8080/actuator/metrics/http.server.requests
~~~

If this metric is available, the output shows `availableTags`, such as `method=GET/POST`, `status=200/404/500`, and `uri` containing observed route templates. Actual route/tag names may differ, especially when no requests have run yet or a route is not recognized by the framework.

### 9.2. Filtering `POST /api/orders`

~~~bash
curl -sG "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=method:POST" \
  --data-urlencode "tag=uri:/api/orders"
~~~

The Timer result can contain `COUNT`, `TOTAL_TIME`, and `MAX`. To filter further by status 500:

~~~bash
curl -sG "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=method:POST" \
  --data-urlencode "tag=uri:/api/orders" \
  --data-urlencode "tag=status:500"
~~~

This queries "POST and this route and status 500", not "all 5xx errors". With distinct statuses 500, 502, 503..., a `status:500` condition only matches the exact value `500`.

If an `outcome=SERVER_ERROR` tag exists under the active convention, querying by `outcome` may suit a 5xx group. **Do not guess enum/tag values**; inspect `availableTags` and verify with controlled traffic.

### 9.3. Status Errors Are Not Only in HTTP

A business observation may record `outcome=error` while the HTTP response is still 200 because the application caught the error and returned a fallback result. Conversely, HTTP 500 does not always mean a business transaction lost data. Tags `status`, `outcome`, and `exception` have distinct semantics; SLI/SLO analysis must define "error" for each layer.

## 10. Second Example: Filtering JVM Memory Metrics by `area` and `id`

The `jvm.memory.used` metric is usually a Gauge with tags `area` and `id`. The goal is to identify which pool uses many bytes rather than only looking at the JVM-wide total.

~~~bash
# View registered pools and values of area/id.
curl -s "http://localhost:8080/actuator/metrics/jvm.memory.used"

# Retrieve only heap pools.
curl -s "http://localhost:8080/actuator/metrics/jvm.memory.used?tag=area:heap"

# Retrieve a specific pool when its name is known.
curl -sG "http://localhost:8080/actuator/metrics/jvm.memory.used" \
  --data-urlencode "tag=area:heap" \
  --data-urlencode "tag=id:G1 Old Gen"
~~~

Without specifying `id`, the `VALUE` measurement may reflect an aggregated result across matching pools. Filtering by a specific pool name narrows data to meters with that tag. However, do not treat that "used" measurement as total container memory or RSS.

**Limitations:** `jvm.memory.used` measures JVM memory across pools; direct buffers, thread stacks, and native memory have separate measurement paths or are not fully reflected. When suspecting container OOMKill, examine process/container metrics and logs as well.

## 11. Comparing Actuator Tag Queries with Prometheus/PromQL

Both approaches can select a subset of metrics by labels, but they answer **different kinds of questions**.

| Aspect | Actuator `/actuator/metrics` | Prometheus + PromQL |
| --- | --- | --- |
| Data source | Registry of **the single instance/process** called | Samples scraped from one or more targets over time |
| Query type | Metric name + `tag=key:value` pairs | Series selector expressions, arithmetic, aggregations, label matchers |
| Label filtering | Primarily exact value matching | `=`, `!=`, regex `=~`, `!~` |
| Combining multiple conditions | Repeated `tag` with AND semantics | Combine matchers, aggregations, PromQL logic |
| Time-based queries | Not a time-window query mechanism | Range vectors and functions `rate()`, `increase()`, `histogram_quantile()`... |
| Group by | No general group-by syntax | `sum by (...)`, `max by (...)`... |
| Primary purpose | Discovery, debugging, verifying instrumentation | Historical dashboards, SLI/SLO, alerting, trend analysis |

For the `orders.create.attempts` Counter, the Actuator query:

~~~http
GET /actuator/metrics/orders.create.attempts?tag=channel:web&tag=outcome:error
~~~

returns the measurement in the current instance registry. It **does not return errors per second over 5 minutes**.

In Prometheus, this Counter might be exported as `orders_create_attempts_total` (verify against the actual exporter). Query for web error rate:

~~~promql
sum(
  rate(orders_create_attempts_total{
    channel="web",outcome="error"
  }[5m])
)
~~~

Computing the error ratio on web:

~~~promql
sum(
  rate(orders_create_attempts_total{
    channel="web",outcome="error"
  }[5m])
)
/
sum(
  rate(orders_create_attempts_total{
    channel="web"
  }[5m])
)
~~~

The result is a ratio from 0 to 1 when the denominator is positive. During periods with no traffic, the denominator may be 0 or have no data. Dashboards/alerts must handle that case.

**Do not use Actuator to compute rates by calling it twice and subtracting values ad hoc in production** without managing timing, restarts, targets, resets, and grouping. For continuous monitoring, use a time-series backend with proper sampling and counter-handling functions.

## 12. Different Instances Can Return Different Results

In a system with 5 Spring Boot pods, each pod holds its own `MeterRegistry`. If you access `/actuator/metrics` through a load balancer, two calls may hit **two different pods**.

For example:

~~~text
Pod A: orders.create.attempts{channel="web",outcome="error"} = 3
Pod B: orders.create.attempts{channel="web",outcome="error"} = 1
Pod C: orders.create.attempts{channel="web",outcome="error"} = 5
~~~

A curl command to the endpoint via a load balancer does not reflect the cluster-wide total = 9; it only reflects the numbers of whichever target received the request. If two requests hit A then B, you may see COUNT drop 3 → 1 even though no Counter reset occurred.

What to do:

1. When debugging locally, target **the exact instance** by accessing the management endpoint directly in an authorized environment.
2. When using Kubernetes, keep the pod/target consistent when doing before-and-after comparisons in a test.
3. To see the cluster-wide total, let Prometheus scrape each instance and use `sum(...)` appropriately.
4. Remember Counters can reset when an application restarts or a meter is recreated; per-pod cumulative counts are not permanent transaction totals.
5. Keep labels distinguishing service, environment, and instance, but avoid attaching a unique **per-request** ID to metrics.

This is a key distinction between "querying by tag on a single JVM" and "cluster-wide time-series querying".

## 13. Cardinality, Security, and Endpoint Access Control

Tags used for metrics should have bounded value sets: `method`, `status`, `uri` as a **route template**, normalized `outcome`, and normalized `channel`. Adding `userId`, email, dynamic IP, request ID, or order ID can cause the number of label combinations to grow very quickly.

Suppose a metric has 4 channels, 3 outcomes, and 8 instances. The maximum number of combinations for each series type is:

~~~text
4 × 3 × 8 = 96 tag combinations
~~~

If you add a nearly unique `requestId` across 100,000 calls, the number of series can grow with the number of calls; memory, scraping, and query costs all increase. With histograms, bucket counts multiply that cost further.

**Querying by tag is not an excuse to put IDs into metrics.** When you need to find a specific request:

- Use low-cardinality metrics to identify the affected time window, route, outcome, and instance.
- Use logs with `traceId/spanId` when correlation is configured.
- Use distributed tracing to inspect spans across services; some spans may carry high-cardinality attributes per data policy.
- Check context propagation, sampler, and exporter if traces do not appear. An Actuator query returning a metric **does not prove** traces were exported.

### Protecting Actuator

Even without exposing user data, `availableTags` can reveal API routes, deployment state, and system information. In production:

- Expose only required endpoints.
- Restrict access via private networks, proxies, authentication/authorization, and proper Spring Security configuration.
- Avoid putting sensitive information into metric names, tag keys, or tag values in the first place.
- Check the management port/base path and do not assume management endpoints are protected the same way as business APIs.
- Do not build a public endpoint accepting arbitrary tag names/values and forwarding them as queries without a clear need.

## 14. Common Errors When Querying by Tag

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `GET /actuator/metrics` returns 404 | Missing Actuator, endpoint not exposed, different base path/port, or security/routing | Check dependencies, exposure, and management URL |
| `/actuator/metrics` works, business metric missing | Code path hasn't run, meter not registered, wrong registry, or blocked by `MeterFilter` | Trigger instrumentation, check the right `MeterRegistry` |
| Filtering `tag=channel:web` yields no data | Different tag key/value, wrong casing, or combination hasn't occurred | Read `availableTags` and actual tags |
| `tag=method:POST, status:500` does not match | Combined multiple conditions into one value | Repeat `tag=method:POST&tag=status:500` |
| Tags with spaces/braces fail to match | Incorrect URL encoding or shell mangling special characters | Use `curl -G --data-urlencode` |
| Querying `http_server_requests_seconds_count` in `/actuator/metrics` fails | Confusing Prometheus series name with Micrometer meter name | Use `http.server.requests` if that is the actual meter name |
| Same query returns fluctuating counts | Load balancer picks different pods, restart/reset, or active tasks altering a Gauge | Pin the instance and check meter type |
| Selected `status:500` but wanted all 5xx | Exact match is not a status group | Check `outcome` tag or use PromQL |
| `/actuator/metrics` has data but Prometheus lacks it | Prometheus registry, endpoint, scrape config/target, or auth failure | Check each stage of the export pipeline |
| `availableTags` has too many values | Instrumentation includes unbounded IDs or high-cardinality tags | Normalize routes/tags, remove unbounded labels |
| COUNT increases while p95 is unchanged or missing | Counter has no duration; Timer lacks suitable histogram | Use Timer + histogram/PromQL for percentiles |
| Metric appears but corresponding trace is missing | Tracing disabled or sampling/exporter/propagation differs from metrics path | Inspect tracing pipeline separately |

**HTTP status when a filter does not match:** depending on version and case, the query may find no matching meter or return unexpected results. Inspect the actual response body/status; do not rely solely on the endpoint existing to conclude the tag filter worked. When debugging, start with an unfiltered query and add conditions one by one.

## 15. Incident Investigation Workflow: Step-by-Step Tag Queries

Scenario: an API group in `order-service` starts returning errors after a deployment.

**Step 1 — check which meters exist.**

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/http.server.requests
~~~

Note tag names from `availableTags`, especially `uri`, `method`, `status`, `outcome`. Do not assume tags appear automatically before traffic arrives.

**Step 2 — isolate route and method.**

~~~bash
curl -sG "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=uri:/api/orders" \
  --data-urlencode "tag=method:POST"
~~~

Confirm COUNT and TOTAL_TIME reflect requests actually completed for this route and method.

**Step 3 — narrow down to errors.**

~~~bash
curl -sG "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=uri:/api/orders" \
  --data-urlencode "tag=method:POST" \
  --data-urlencode "tag=status:500"
~~~

If the status is not 500, pick the actual tag/value from `availableTags`. To group 5xx errors, switch to PromQL or a standard `outcome` tag if appropriate.

**Step 4 — compare with the business metric.** Query `orders.create.attempts` by `channel` and `outcome` to determine whether errors originate from order creation or from the HTTP/server layer.

**Step 5 — check history and cluster-wide impact.** Use the time-series backend to inspect per-minute error rate, before/after deployment changes, p95 latency, and impact across instances. Actuator is a snapshot of one process, not a replacement for dashboards.

**Step 6 — correlate logs/traces.** Based on timestamp and service, search logs by trace ID or related spans. Check propagation and sampling when investigating cross-service requests.

**Step 7 — verify after remediation.** Repeat testing with deterministic traffic, confirm new tags do not increase cardinality, then monitor error rate/latency in Prometheus.

### Distinguishing "No Data" from "No Errors"

A metric or tag combination that has never been recorded may not exist in the registry at all, rather than having COUNT = 0. Never assume an empty query means the system is error-free: the name may be wrong, the tag may be wrong, you may be querying the wrong instance, or the exporter may not be ready.

## 16. Practice Test with Expected Answers

Suppose in a fresh process, only the calls in the table occurred:

| Combination | COUNT |
| --- | ---: |
| `channel=web, outcome=success` | 12 |
| `channel=web, outcome=error` | 3 |
| `channel=mobile, outcome=success` | 8 |
| `channel=mobile, outcome=error` | 2 |
| `channel=partner, outcome=success` | 5 |

For Counter `orders.create.attempts`, try predicting the results:

| Query | Expected COUNT |
| --- | ---: |
| No filter | 30 |
| `tag=channel:web` | 15 |
| `tag=outcome:success` | 25 |
| `tag=outcome:error` | 5 |
| `tag=channel:web&tag=outcome:error` | 3 |
| `tag=channel:mobile&tag=outcome:success` | 8 |
| `tag=channel:partner` | 5 |

These numbers hold only for the hypothetical workload, assuming no background traffic or retries and the Counter starting from 0. If common tags such as `application` are configured, measurements remain valid while `availableTags` includes additional keys.

### Task A — Write HTTP Requests

1. Write a curl command to list all metric names.
2. Write a curl command to fetch `orders.create.attempts` without filters.
3. Write a curl command to filter `channel=mobile` and `outcome=error`.
4. Write a curl command to filter `jvm.memory.used` by `area=heap` and a pool name containing spaces.
5. Explain how to properly URL-encode `uri=/api/orders/{id}`.

### Task B — Read JSON and Answer

From the response of `/actuator/metrics/orders.create.attempts?tag=channel:web`, identify what `measurements` describes and what `availableTags` is used for. If `outcome=success,error` appears, explain why the total COUNT is not automatically split into two rows.

### Task C — Build Historical Queries

Write PromQL to compute errors/second for `channel=web` over 5 minutes and the error ratio across all attempts on that channel. Verify the exported Counter name in Prometheus first before writing the expression.

### Task D — Test Environment Changes

Run the application with two instances and hit an endpoint through a load balancer. Explain why COUNT can differ from call to call. Then use Prometheus to properly aggregate COUNT/`rate()` across instances.

### Self-Check Questions

1. What is the tag-query syntax in Actuator?
2. When using two `tag` parameters, do they combine with AND or OR?
3. Does `tag=status:500` select all 5xx statuses?
4. Why are `http.server.requests` and `http_server_requests_seconds_count` two naming styles at two different layers?
5. Does `availableTags` return per-request data?
6. Why does `COUNT=100` in Actuator not mean 100 requests/second?
7. Why should `requestId` not be added as a metric tag just to query a specific request?
8. Why can querying through a load balancer return different values for the same metric?
9. When a query returns empty, which hypotheses must be checked before concluding "no errors"?
10. Can the `/actuator/metrics` endpoint replace PromQL for a 7-day dashboard?

**Completion criteria:** can operate the `/actuator/metrics` endpoint, filter one or more tags with proper syntax, URL-encode values, read `measurements`/`availableTags`, distinguish Counter/Gauge/Timer, identify exact Micrometer names, use PromQL when time-based or cluster-wide aggregation is needed, and protect tag cardinality.

## 17. Key Takeaways

- The core syntax is **`/actuator/metrics/{metricName}?tag=key:value`**. Multiple conditions use **repeated `tag` parameters**, meaning **AND**.
- Start with `/actuator/metrics` and an **unfiltered** query to discover meters and `availableTags` before filtering.
- `measurements` returns statistics for the selected meters; COUNT, VALUE, TOTAL_TIME, and MAX have different meanings. Do not interpret snapshots as rates or percentiles.
- Micrometer names may differ from Prometheus series names; `/actuator/metrics` does not use PromQL syntax.
- Actuator tag queries serve **discovery and single-instance debugging**. For multi-minute/multi-day trends, regex, group by, cluster-wide aggregation, and alerts, use a time-series backend like Prometheus.
- Attach only **low-cardinality** labels to metrics; never use user/request/order IDs as tags. Use logs and traces to investigate a specific request.
- Protect management endpoints, verify port/base path/auth, and distinguish instrumentation errors from scrape/exporter/sampling/propagation errors.

## References

- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot Reference — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer Reference — MeterRegistry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer Reference — Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html)
- [Prometheus — Querying Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)
