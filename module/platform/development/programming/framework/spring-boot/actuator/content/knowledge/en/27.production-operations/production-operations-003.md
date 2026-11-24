# Building Dashboards for Traffic, Errors, Latency, and Resource Usage

## 1. Dashboards Must Support Operational Decisions

A dashboard is a set of charts organized to answer a group of questions. For an HTTP service running on Spring Boot, the on-call engineer needs to know:

- How many requests is the application receiving?
- How many requests are failing, and in which category?
- How long are users waiting?
- Which application instance is running out of resources or showing signs of overload?

These four signal groups must be read together. A traffic drop may result from lower demand, or from an instance stopping accepting requests. Low CPU does not rule out the application waiting on a database. Low average latency also does not prove the slowest requests still meet targets.

A useful dashboard has two layers:

1. **Service layer:** total traffic, error rate, and latency distribution for the monitored business scope.
2. **Per-instance layer:** CPU, memory, threads, and bounded resources to pinpoint where anomalies originate.

This article uses Spring Boot **3.3.x**, Micrometer, Prometheus, and Grafana. The hands-on example uses a Servlet application on a local machine. Production configuration should keep the same measurement semantics while adapting addresses, access permissions, and target discovery mechanisms accordingly.

## 2. Understanding the Metrics Path

```text
HTTP requests / JVM activity
          ↓
Micrometer records measurements inside the application
          ↓
Actuator /actuator/prometheus exposes metrics
          ↓  Prometheus scrapes periodically
Prometheus stores time series
          ↓  Grafana sends PromQL queries
Dashboard renders results over time and labels
```

The Prometheus endpoint exposes metrics in a format readable by the collection system. [Spring Boot 3.3 Prometheus REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/prometheus.html)

Grafana sends queries to a data source to render charts; in this model that source is Prometheus. [Querying data in Grafana](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/query-transform-data/)

Do not read the current value from an endpoint and treat it as long-term history. History must be stored by the metrics system. Nor should you expose `env`, `beans`, or dumps just to build a dashboard for the four signal groups above.

### Three Metric Types to Recognize

| Type | Meaning | How it is used in this article |
| --- | --- | --- |
| Cumulative counter | Counts events; can reset to a low value when the process restarts | Compute request and error rates from increases over time |
| Instantaneous value (gauge) | Can go up or down | Plot CPU, memory, active connections |
| Histogram | Records observation distribution into buckets | Compute p95/p99 from latency buckets |

For counters, Prometheus `rate()` computes the per-second average rate of increase and handles counter resets. When aggregating across multiple instances, compute rate per series first, then sum. [Prometheus rate function](https://prometheus.io/docs/prometheus/latest/querying/functions/#rate)

## 3. Preparing a Lab Application with Real Metrics

Use a **separate Spring Boot 3.3.x Servlet project**, JDK 21, and an existing Gradle Wrapper. The snippets below are added to that project; they are not instructions to modify a serving production application.

### 3.1. Dependencies and Application Configuration

Add dependencies in `build.gradle` of a project already using the Spring Boot plugin and dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Create `src/main/resources/application.yml` in the lab project:

```yaml
spring:
  application:
    name: orders-lab

server:
  address: 127.0.0.1
  port: 8080

management:
  server:
    address: 127.0.0.1
    port: 9001
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: [health, prometheus]
  endpoint:
    health:
      enabled: true
    prometheus:
      enabled: true
  metrics:
    tags:
      application: orders-lab
    distribution:
      percentiles-histogram:
        "http.server.requests": true
      slo:
        "http.server.requests": 100ms,300ms,1s
```

Spring Boot records HTTP metrics under the name `http.server.requests`; the distribution configuration enables histogram export and adds the latency thresholds to observe. [HTTP metrics and per-meter configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)

Histograms support aggregating buckets across instances before estimating percentiles. Pre-calculated percentiles at each process do not have this aggregation property. [Micrometer histograms and percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)

The 100 ms, 300 ms, and 1 s thresholds are choices for the lab exercise. Place buckets at the time ranges you actually need to distinguish; do not grow the bucket count indefinitely.

The configuration uses loopback because Prometheus will run directly on the same machine. For another container or host, the address must be reachable from where the collector runs. Production needs network source restrictions and proper authentication; do not expose the management port directly to the Internet.

### 3.2. Creating Three Paths with Verifiable Behavior

Place the file `src/main/java/lab/dashboard/DashboardLabApplication.java` in the lab project. Keep only one appropriate main startup class in that project:

```java
package lab.dashboard;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DashboardLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(DashboardLabApplication.class, args);
    }
}

@RestController
@RequestMapping("/demo")
class DemoController {
    @GetMapping("/ok")
    public String ok() {
        return "ok";
    }

    @GetMapping("/fail")
    public ResponseEntity<String> fail() {
        return ResponseEntity.status(500).body("failed");
    }

    @GetMapping("/slow")
    public String slow() throws InterruptedException {
        Thread.sleep(250);
        return "slow";
    }
}
```

This code runs inside Spring Boot with the dependencies above; do not compile it standalone with `javac` when the classpath is missing.

Start on Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

On Linux/macOS use `./gradlew bootRun`. If the lab project has Spring Security, configure permissions for the paths used in the article; this example assumes no security library has been added yet.

Verify using `curl.exe` on Windows:

```powershell
curl.exe -i http://127.0.0.1:8080/demo/ok
curl.exe -i http://127.0.0.1:8080/demo/fail
curl.exe -i http://127.0.0.1:8080/demo/slow
curl.exe http://127.0.0.1:9001/actuator/prometheus
```

The three business responses have bodies `ok`, `failed`, and `slow` respectively; status codes are 200, 500, and 200 respectively. Calling slow waits at least the sleep duration in the controller plus processing overhead. Do not treat observed latency as an exact 250 ms.

## 4. Configuring Prometheus and Confirming Time Series

This example assumes Prometheus and Grafana are installed and running directly on the lab machine. Create `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  scrape_timeout: 5s

scrape_configs:
  - job_name: orders-lab
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["127.0.0.1:9001"]
        labels:
          environment: lab
```

Start Prometheus with that file, for example on Windows:

```powershell
.\prometheus.exe --config.file=prometheus.yml
```

Targets and paths are declared in the scrape configuration. [Prometheus configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)

If Prometheus runs inside a container, `127.0.0.1` refers to that container itself; replace it with an application address reachable from the container. Likewise, the Grafana data source URL must be reachable from the Grafana server.

### 4.1. Locking Down the Label Set Before Writing Dashboards

In this article:

| Label | Source | Meaning |
| --- | --- | --- |
| `job="orders-lab"` | Scrape configuration | Target group of the lab application |
| `instance` | Attached by Prometheus on scrape | Specific target, e.g. `127.0.0.1:9001` |
| `environment="lab"` | Target label in scrape configuration | Environment |
| `application="orders-lab"` | Common tag in the application | Application name on meters exported by the application |
| `method`, `uri`, `status` | HTTP metrics | Request classification |

Placing environment on the **target** gives both application metrics and `up` that label. Common tags inside application data do not automatically become labels on `up`.

Prometheus automatically generates `up`: 1 when scrape succeeds, 0 when scrape fails. [Job, instance, and auto-generated series](https://prometheus.io/docs/concepts/jobs_instances/)

Check in the Prometheus query UI:

```promql
up{job="orders-lab", environment="lab"}
```

After calling the lab APIs, check:

```promql
http_server_requests_seconds_count{job="orders-lab", environment="lab"}
```

```promql
http_server_requests_seconds_bucket{job="orders-lab", environment="lab"}
```

Data and proper labels must be present before building charts. HTTP meters may appear only after requests arrive. If buckets are missing, check the histogram configuration and restart the application.

The Prometheus names in this article use the common export format of HTTP timers. Always cross-check against actual endpoint data, especially when upgrading Micrometer or changing naming conventions.

### 4.2. Keeping Label Combinations Within a Manageable Range

Use templated URI labels, such as `/orders/{id}`, rather than individual paths containing order IDs. Do not add user IDs, request IDs, emails, or tokens as metric labels.

Each label combination creates a time series. Buckets further multiply the number of histogram series. [Prometheus naming and label conventions](https://prometheus.io/docs/practices/naming/)

You can store a request's ID in logs/traces for individual investigation. Dashboards need grouping stable enough for comparison over time.

## 5. Traffic, Error, and Latency Panels

The queries below use a **5-minute** window and run directly in Prometheus. In Grafana, you can consistently replace `[5m]` with `[$__rate_interval]`; the data source's scrape interval must match the 15-second value in this article. [Grafana rate interval variable](https://grafana.com/docs/grafana/latest/datasources/prometheus/template-variables/#use-__rate_interval)

All HTTP panels exclude management and probe URIs with the filter:

```text
uri!~"/actuator.*|/livez|/readyz"
```

This filter assumes default management/probe paths. If the application changes paths, update all queries consistently. For systems with multiple API types, clearly define the business scope to measure rather than lumping everything together.

### 5.1. Total Traffic: Requests per Second

```promql
sum(
  rate(http_server_requests_seconds_count{
    job="orders-lab",
    environment="lab",
    uri!~"/actuator.*|/livez|/readyz"
  }[5m])
)
```

Set the panel type to Time series, unit `req/s`. A value of 20 means an average rate of 20 completed requests per second over the window under consideration.

Do not plot the raw counter and label it "RPS". A raw counter grows monotonically over time; it answers a different question.

To see load distribution across instances, keep the instance label:

```promql
sum by (instance) (
  rate(http_server_requests_seconds_count{
    job="orders-lab",
    environment="lab",
    uri!~"/actuator.*|/livez|/readyz"
  }[5m])
)
```

Both charts are necessary: service total indicates demand; per-instance helps spot uneven load or an instance not receiving requests.

### 5.2. Errors per Second and Error Rate

Here, server errors are defined as **HTTP 5xx**. State this definition clearly in the panel description. 4xx responses and business errors returning HTTP 200 need separate panels or meters according to the system's contract.

5xx error rate (errors per second):

```promql
sum(
  rate(http_server_requests_seconds_count{
    job="orders-lab",
    environment="lab",
    uri!~"/actuator.*|/livez|/readyz",
    status=~"5.."
  }[5m])
)
```

5xx error percentage, unit percent:

```promql
100 *
(
  sum(
    rate(http_server_requests_seconds_count{
      job="orders-lab",
      environment="lab",
      uri!~"/actuator.*|/livez|/readyz",
      status=~"5.."
    }[5m])
  )
  or
  (
    0 * sum(
      rate(http_server_requests_seconds_count{
        job="orders-lab",
        environment="lab",
        uri!~"/actuator.*|/livez|/readyz"
      }[5m])
    )
  )
)
/
(
  sum(
    rate(http_server_requests_seconds_count{
      job="orders-lab",
      environment="lab",
      uri!~"/actuator.*|/livez|/readyz"
    }[5m])
  ) > 0
)
```

Explanation of each part:

- The numerator is the error rate for the same request scope.
- The `or (0 * ...)` branch supplies 0 when request metrics exist but no 5xx series exists yet.
- The denominator uses the filtering comparison `> 0`, **not `bool`**, to keep positive rate values as the denominator.
- When there are no requests in the window, there is no meaningful ratio to display. The panel should show no ratio data, alongside an RPS panel and scrape status to explain why.

Vector arithmetic, set operators, and filtering comparisons have different semantics in PromQL. [Prometheus operators](https://prometheus.io/docs/prometheus/latest/querying/operators/)

Do not replace the denominator with `clamp_min(..., 1)` just to eliminate division-by-zero errors. At traffic of 0.1 req/s, replacing the denominator with 1 distorts the error rate by tenfold.

Also do not take the unweighted arithmetic mean of instance error percentages. For example, in the same time range:

| Instance | Total requests | Errors | Rate |
| --- | ---: | ---: | ---: |
| A | 100 | 1 | 1% |
| B | 1 | 1 | 100% |
| Whole service | 101 | 2 | About 1.98% |

Averaging 1% and 100% into 50.5% does not reflect the error rate of 101 requests.

### 5.3. Weighted Average Latency

```promql
sum(
  rate(http_server_requests_seconds_sum{
    job="orders-lab",
    environment="lab",
    uri!~"/actuator.*|/livez|/readyz"
  }[5m])
)
/
(
  sum(
    rate(http_server_requests_seconds_count{
      job="orders-lab",
      environment="lab",
      uri!~"/actuator.*|/livez|/readyz"
    }[5m])
  ) > 0
)
```

The result has units of **seconds**: total processing time divided by total request count. Grafana can display seconds with appropriate formatting, or multiply by 1000 and select milliseconds. Do not multiply by 1000 and still label the unit as seconds.

For example, 100 requests taking 10 ms each and one request taking 1000 ms: the overall average is `2000 / 101 ≈ 19.802 ms`, not 505 ms.

### 5.4. p95 and p99: Observing the Latency Tail

p95 is an estimate of the threshold that roughly 95% of observations do not exceed within the chosen window and scope. It is not 95% of the maximum value.

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      job="orders-lab",
      environment="lab",
      uri!~"/actuator.*|/livez|/readyz"
    }[5m])
  )
)
```

With classic histograms, the `le` label defines the upper bound of the bucket. Keep `le` when summing buckets, then compute the quantile; replace 0.95 with 0.99 for p99. [Histograms in Prometheus](https://prometheus.io/docs/practices/histograms/)

Do not average p95 values across instances. Aggregate the distribution first, compute the percentile afterward. Instances must use the same bucket definitions and boundaries for consistent comparison/aggregation.

To find slow APIs, also retain method and URI template:

```promql
histogram_quantile(
  0.95,
  sum by (le, method, uri) (
    rate(http_server_requests_seconds_bucket{
      job="orders-lab",
      environment="lab",
      uri!~"/actuator.*|/livez|/readyz"
    }[5m])
  )
)
```

Set the legend to include method and uri. Avoid plotting thousands of lines on a single panel; filter API groups or use a table to select routes to investigate.

Percentiles depend on observation count and bucket resolution. When requests are very sparse, do not treat p99 as a firm conclusion. Inspect request count in the window and latency per API simultaneously.

### 5.5. Measuring the Proportion Meeting a Time Threshold When Needed

If the `le="0.3"` bucket is exported, the percentage of requests completing in up to roughly 300 ms is:

```promql
100 *
sum(
  rate(http_server_requests_seconds_bucket{
    job="orders-lab",
    environment="lab",
    uri!~"/actuator.*|/livez|/readyz",
    le="0.3"
  }[5m])
)
/
(
  sum(
    rate(http_server_requests_seconds_count{
      job="orders-lab",
      environment="lab",
      uri!~"/actuator.*|/livez|/readyz"
    }[5m])
  ) > 0
)
```

Before using it, check the actual `le` label values from the endpoint to match the exact export format. This panel only measures duration and can still count very fast 500 responses. If the goal requires "successful and fast enough", redefine the good-request set and denominator according to that SLO.

## 6. Resource Panels: Prefer Viewing Per Instance

Resource panels help guide investigation; they do not by themselves prove root cause. Micrometer provides binders for JVM memory, GC, CPU, and threads. [Micrometer JVM metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html)

### 6.1. Process CPU

```promql
100 * process_cpu_usage{
  job="orders-lab",
  environment="lab"
}
```

Choose unit percent 0–100, legend by instance. Do not sum CPU percentages of instances into a "service-wide percentage".

This is the CPU ratio reported by the JVM/OS for that measurement. It does not automatically equal the percentage of a container's CPU quota. If container throttling or limits need to be evaluated, add infrastructure metrics specific to the platform.

Low CPU while p95 is high may suggest waiting on I/O, connections, or locks. High CPU alongside rising traffic may suggest increased compute demand. Both require further evidence.

### 6.2. Heap Used

```promql
sum by (instance) (
  jvm_memory_used_bytes{
    job="orders-lab",
    environment="lab",
    area="heap"
  }
)
```

Choose unit bytes. When selecting only one environment/job, each line shows the total heap used by one instance.

If you want a percentage per **memory pool that has a valid maximum**:

```promql
100 *
jvm_memory_used_bytes{
  job="orders-lab",
  environment="lab",
  area="heap"
}
/
(
  jvm_memory_max_bytes{
    job="orders-lab",
    environment="lab",
    area="heap"
  } > 0
)
```

Keep instance and pool id in the legend. Pools without a positive maximum will not appear in the ratio; do not turn them into 0%. Do not label this chart "container memory percentage".

Micrometer records pools and corresponding labels from the JVM. [JvmMemoryMetrics 1.13 source](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/binder/jvm/JvmMemoryMetrics.java)

Observe trends across multiple GC cycles. A single segment where heap rises then drops is not enough to conclude a memory leak. Process memory also includes off-heap areas; when needed, cross-check process/container metrics rather than treating heap as all memory.

### 6.3. Threads and GC Time

Number of live JVM threads:

```promql
jvm_threads_live_threads{
  job="orders-lab",
  environment="lab"
}
```

Cumulative GC pause time rate:

```promql
sum by (instance) (
  rate(jvm_gc_pause_seconds_sum{
    job="orders-lab",
    environment="lab"
  }[5m])
)
```

The GC panel has units of pause seconds per observed second. Inspect alongside heap and latency; do not infer root cause from a single spike. Some meters depend on the JVM, collector, or activity that occurred; confirm names/labels before use.

Rising threads does not necessarily mean blocked threads. If queues or saturation levels need to be evaluated, add metrics for the executor/thread pool actually doing the work.

### 6.4. Database Connections, When the Application Has a Pool

Example using JDBC meters already present in the endpoint:

```promql
100 *
jdbc_connections_active{
  job="orders-lab",
  environment="lab"
}
/
(
  jdbc_connections_max{
    job="orders-lab",
    environment="lab"
  } > 0
)
```

Keep instance and pool/data source name labels. Spring Boot provides active, idle, and limit metrics for supported DataSources. [DataSource metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.jdbc)

The lab application has not added a database yet, so this panel may have no data. Do not add a dummy database just so every panel has a curve. In production, a high active/max ratio is a clue; check connection acquisition wait time, waiting requests, and database load before expanding the pool.

## 7. Building the Grafana Layout from Verified Queries

Add a Prometheus data source and set a URL reachable by the Grafana server, such as `http://127.0.0.1:9090` when both run directly on the same machine. Test the connection before creating panels.

Create a new dashboard, add panels, select the data source, and enter PromQL in the query editor. Save the dashboard after naming and verifying results. [Create a Grafana dashboard](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/create-dashboard/), [PromQL query editor](https://grafana.com/docs/grafana/latest/datasources/prometheus/query-editor/)

Suggested layout:

| Row | Panel | Representation |
| --- | --- | --- |
| 1 | Scrape status per instance | Stat or State timeline; 1 and 0 have clear meanings |
| 1 | Total RPS, 5xx rate, p95 | Overview values with trends |
| 2 | RPS per instance, 5xx per second | Time series to compare load and errors |
| 2 | Average, p95, p99 | Same unit and same request scope |
| 3 | Latency by method/uri | Table or chart with API filters |
| 4 | CPU, heap, threads, GC per instance | Do not let cluster-wide averages hide an anomalous instance |
| 5 | Pool/queue/container | Add only when corresponding data and operational questions exist |

Document in each panel's description:

- Which service, environment, and paths are counted.
- Calculation window and unit.
- What condition counts as an error.
- How to interpret zero or no-data values.
- Links to detailed charts or appropriate investigation procedures.

Set an initial time range of 30 minutes with 15–30 second auto-refresh for the lab exercise. Changing the time range does not turn a wrong measurement into a right one; re-check rate calculation and resolution when viewing many hours or days.

### Reusable Filters

Once the static version works, create single-select job and environment variables; instance can allow multi-select. Variable queries pull label values from `up`, since scope labels were placed on targets.

When applying to panels, replace fixed selectors with:

```text
job="$job", environment="$environment", instance=~"$instance"
```

With multi-select or All, instance uses `=~`. Also verify every panel applies the same filters. [Prometheus template variables in Grafana](https://grafana.com/docs/grafana/latest/datasources/prometheus/template-variables/)

Selecting one instance must make service panels reflect that specific instance. If the RPS panel still sums the whole cluster while CPU filters one instance, viewers may combine two signals with different scopes.

### Scrape Status Is Not Business Status

```promql
up{job="orders-lab", environment="lab"}
```

`up=1` proves scraping succeeded, not that business APIs succeeded. An application can export metrics normally while an API returns 500.

Conversely, `up=0` can result from a stopped application, wrong permissions, network issues, or a failing endpoint. If a target is dropped from discovery configuration, the `up` series may even disappear; cross-check expected target counts against deployment sources.

Do not configure all missing values as 0 and color them green. When scraping has just failed, windowed rate queries can still return values from previous samples. Read the scrape status panel alongside historical charts.

## 8. Verifying Dashboards with Intentional Scenarios

### 8.1. Generating a Predictable Mix of Requests

Save the snippet below as `traffic.py` on the lab machine with Python 3. It only calls the lab APIs on loopback:

```python
import time
import urllib.error
import urllib.request

base_url = "http://127.0.0.1:8080"
counts = {200: 0, 500: 0}

for index in range(1000):
    if index % 10 == 0:
        path = "/demo/fail"
    elif index % 5 == 0:
        path = "/demo/slow"
    else:
        path = "/demo/ok"

    try:
        with urllib.request.urlopen(base_url + path, timeout=3) as response:
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()

    if status not in counts:
        raise RuntimeError(f"Unexpected HTTP status: {status}")

    counts[status] += 1
    time.sleep(0.05)

print(
    f"sent={sum(counts.values())} "
    f"ok={counts[200]} server_errors={counts[500]}"
)
```

Run:

```text
python traffic.py
```

If the application matches the example and all 1000 calls receive expected responses, stdout is:

```text
sent=1000 ok=900 server_errors=100
```

This includes 100 slow calls among the 900 HTTP 200 responses. Connection errors or timeouts are not hidden; the script stops for the learner to investigate.

The script's count results are exact for the loop. RPS and ratios on the dashboard are computed over scrape windows and can be affected by startup, the selected time range, and prior manual calls. When steady state needs to be observed, run the test loop long enough.

### 8.2. Acceptance Tests

| Scenario | Signals to check |
| --- | --- |
| Call only `/demo/ok` | RPS rises, no 5xx errors; a 5xx series does not necessarily exist yet |
| Mixed calls via script | 5xx errors and slow request group appear; source counts roughly match trends |
| Increase slow share | p95/p99 reflect the slow portion under the new distribution, without requiring exactly 250 ms |
| Stop sending requests while keeping the app running | Rate gradually drops to 0 as traffic leaves the window; scraping still succeeds |
| Stop the application | Scraping fails; dashboard does not interpret it as healthy and error-free |
| Restart the application | Counter resets; rate panel does not turn resets into negative traffic |
| Add an instance | Total RPS sums properly, CPU/heap still show each instance |
| Change environment filter | All panels switch scope together, without mixing lab and production |

If Prometheus scrapes before the script starts running, metrics are cleaner for comparing counter increases. `increase()` may interpolate, so it does not guarantee an integer result matching the exact counter in the script.

### 8.3. Mistakes to Catch Before Real Use

- Using cumulative count as the request rate.
- Computing rate after summing counters from multiple processes.
- Averaging error rates or percentiles across instances.
- Omitting the le label in classic histogram aggregation.
- Counting probes/scrapes into business traffic without stating so.
- Confusing seconds with milliseconds, or 0–1 ratios with 0–100 percentages.
- Using heap as a proxy for total container memory.
- Displaying missing series as 0 or connecting lines across data gaps.
- Picking color thresholds just because they look reasonable, without tying them to service objectives.
- Inferring causality solely because two charts rise at the same time.

## 9. Bringing Dashboards into Operational Processes

Before production use, document the dashboard owner, observation goals, data source, standard label set, and how queries are changed. Store dashboard configurations under the team's change management process so they can be reviewed and restored.

Dashboards and alerts have different roles. Dashboards support exploration; alerts need conditions, duration thresholds, missing-data handling, and specific recipients. A color threshold on a panel does not by itself constitute a response mechanism.

When anomalies occur, start from impact: traffic, failure rate, and latency. Then identify the involved API/instance, cross-check resources and deployment timestamps, and use logs/traces to test hypotheses.

A dashboard meets its goal when operators can determine the blast radius, distinguish service incidents from metrics collection incidents, and select the next investigation step using measurements with clear semantics.
