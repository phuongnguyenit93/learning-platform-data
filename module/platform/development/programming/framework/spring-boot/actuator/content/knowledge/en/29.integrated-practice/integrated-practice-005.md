# Collect metrics with Prometheus and build a Grafana dashboard

This lab creates a Spring Boot application that exports metrics via Actuator, configures Prometheus to scrape it periodically, and provisions a ready-to-run Grafana dashboard from configuration files. Learners will generate successful and failed traffic to read three HTTP signals: throughput, error rate, and latency; then correlate them with JVM metrics and business counters.

The example uses Spring Boot 3.3.5, Java 17+ source code, a Java 21 JVM container, Prometheus 2.54.1, and Grafana 11.2.2. These are concrete illustrative versions, not production version recommendations. Host-side commands in this lab use PowerShell 7, Maven, and Docker Compose with Linux containers.

## 1. Understand the data flow

```text
Test request
    -> Spring MVC handles /demo/orders
        -> Micrometer records HTTP Timer and custom Counter
            -> Actuator /actuator/prometheus exposes data
                <- Prometheus actively scrapes every 5 seconds
                    -> stores time series
                        <- Grafana sends PromQL queries
                            -> renders dashboard
```

| Component | Responsibility |
| --- | --- |
| Micrometer | Provides meter model, records measurements and labels in the app |
| Prometheus Registry | Converts meters into Prometheus names and exposition format |
| Actuator | Exposes the HTTP endpoint to read exported data |
| Prometheus | Scrapes periodically, attaches target labels, stores time series, and executes PromQL |
| Grafana | Sends queries to Prometheus and visualizes results |

In this flow, the application does not push data directly to Grafana. Nor does Grafana use the Actuator endpoint as a Prometheus datasource.

Three meter types will be observed:

- **Counter, cumulative counter:** e.g., number of completed tasks. Its value within a process only increases; it may reset when the application restarts.
- **Gauge, instantaneous measurement:** e.g., heap bytes currently in use.
- **Timer, duration measurement:** records count and total time; when histograms are enabled, it also exports buckets for quantile estimation.

A time series is identified by the metric name together with the full label set. Changing a label value can create additional series, not merely change a display attribute.

## 2. Create a verifiable application

### 2.1. Project structure

```text
metrics-lab/
├── pom.xml
├── Dockerfile
├── compose.yml
├── src/main/
│   ├── java/demo/metrics/
│   │   ├── MetricsLabApplication.java
│   │   └── OrderController.java
│   └── resources/application.yml
└── observability/
    ├── prometheus.yml
    └── grafana/
        ├── dashboards/
        │   └── spring-boot.json
        └── provisioning/
            ├── datasources/
            │   └── prometheus.yml
            └── dashboards/
                └── lab.yml
```

Create the files in the exact locations. This is a standalone demo project; there is no need to modify the build configuration of an existing repository.

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>metrics-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
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

The `micrometer-registry-prometheus` dependency must be on the classpath for Boot to configure the corresponding registry. Adding Actuator alone is not enough to have a working Prometheus endpoint by default.

`src/main/java/demo/metrics/MetricsLabApplication.java`:

```java
package demo.metrics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MetricsLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(MetricsLabApplication.class, args);
    }
}
```

### 2.2. Traffic-generating endpoint and custom Counter

`src/main/java/demo/metrics/OrderController.java`:

```java
package demo.metrics;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class OrderController {
    private final Counter successes;
    private final Counter failures;

    public OrderController(MeterRegistry registry) {
        this.successes = Counter.builder("lab.orders.completed")
                .description("Completed demo order attempts")
                .tag("outcome", "success")
                .register(registry);
        this.failures = Counter.builder("lab.orders.completed")
                .description("Completed demo order attempts")
                .tag("outcome", "failure")
                .register(registry);
    }

    @PostMapping("/demo/orders")
    public ResponseEntity<Map<String, String>> order(
            @RequestParam(name = "outcome", defaultValue = "success") String outcome) {
        Counter counter;
        long delayMs;
        switch (outcome) {
            case "success" -> {
                counter = successes;
                delayMs = 40;
            }
            case "failure" -> {
                counter = failures;
                delayMs = 120;
            }
            default -> throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "outcome must be success or failure");
        }

        try {
            Thread.sleep(delayMs);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE, "demo work interrupted");
        }

        counter.increment();
        HttpStatus status = outcome.equals("success")
                ? HttpStatus.OK : HttpStatus.SERVICE_UNAVAILABLE;
        return ResponseEntity.status(status).body(Map.of("outcome", outcome));
    }
}
```

Test contract:

| Request | HTTP code | Custom counter | Simulated wait time |
| --- | --- | --- | --- |
| `POST /demo/orders?outcome=success` | 200 | `outcome=success` increments by 1 | 40 ms |
| `POST /demo/orders?outcome=failure` | 503 | `outcome=failure` increments by 1 | 120 ms |
| Any other outcome value | 400 | No new label series created/incremented | No simulated work performed |

`Thread.sleep` only introduces latency to practice reading dashboards. It is not a full simulation of CPU load, database work, or production performance. Measured HTTP latency also includes other processing overhead, so it need not equal 40 or 120 ms exactly.

Both counters are registered once in the constructor with two finite label values. Do not pass an arbitrary request parameter directly into `tag("outcome", ...)`; otherwise callers could grow series count continuously.

This counter measures simulated attempts that reached completion, including intentional success and failure results. The HTTP Timer automatically measures HTTP requests. Their scopes do not match 1-to-1: a 400 request still belongs to HTTP metrics, but not to this completion counter.

### 2.3. Enable endpoints and histograms

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080
spring:
  application:
    name: metrics-lab
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  metrics:
    tags:
      application: ${spring.application.name}
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests: 50ms,100ms,250ms,500ms,1s,2s
```

Meaning of the choices:

- Expose only `health` and `prometheus` in this lab.
- The common tag `application=metrics-lab` is applied to application meters.
- Enable histograms for `http.server.requests` to produce bucket data for p95.
- SLO thresholds add bucket boundaries at 50 ms, 100 ms, 250 ms, 500 ms, 1 second, and 2 seconds.

Names in Boot/Micrometer configuration differ from names exported to Prometheus:

| Meter name in application | Example exported name |
| --- | --- |
| `lab.orders.completed` | `lab_orders_completed_total` |
| `http.server.requests` | `http_server_requests_seconds_count`, `_sum`, `_bucket` |
| `jvm.memory.used` | `jvm_memory_used_bytes` |

Timers export durations in seconds for the metrics above. A value of 0.12 corresponds to roughly 120 ms; do not read it as 0.12 ms.

Histograms increase series count because each label combination gains many buckets. Enable them only where needed and keep URI, status, and label counts under control.

## 3. Run all three services in the same Compose network

### 3.1. Package the application

`Dockerfile`:

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/metrics-lab-1.0.0.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

The Dockerfile takes the JAR built with Maven on the host. Therefore you must run `mvn clean package` before `docker compose up --build`. It does not compile source code inside the image.

### 3.2. Prometheus configuration

`observability/prometheus.yml`:

```yaml
global:
  scrape_interval: 5s
  evaluation_interval: 5s

scrape_configs:
  - job_name: spring-boot-lab
    scrape_interval: 5s
    scrape_timeout: 3s
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - app:8080
```

Prometheus reaches the application at `app:8080` via Compose internal DNS. Inside the Prometheus container, `localhost:8080` points to the Prometheus container itself, not the application.

`job` and `instance` are important labels added during scraping. With this configuration, job is `spring-boot-lab` and the target is `app:8080`.

Scrape timeout is 3 seconds, shorter than the 5-second scrape interval. If the endpoint becomes slower than that budget, investigate the endpoint, load, and connectivity; do not blindly raise all timeouts.

### 3.3. Provision the datasource and dashboard provider

`observability/grafana/provisioning/datasources/prometheus.yml`:

```yaml
apiVersion: 1
datasources:
  - name: Prometheus Lab
    uid: prometheus-lab
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
    jsonData:
      httpMethod: POST
      timeInterval: 5s
```

The datasource uses `http://prometheus:9090` because queries are sent by the Grafana server from inside the Compose network. The URL in the learner's browser is a different location.

`timeInterval: 5s` declares the scrape interval for the datasource, helping Grafana compute `$__rate_interval` matching the lab's scrape interval.

`observability/grafana/provisioning/dashboards/lab.yml`:

```yaml
apiVersion: 1
providers:
  - name: spring-boot-lab
    orgId: 1
    folder: Spring Boot Lab
    type: file
    updateIntervalSeconds: 10
    allowUiUpdates: false
    options:
      path: /var/lib/grafana/dashboards
```

The provider reads dashboard JSON files from the mounted directory. In this lab, the JSON file is the source of truth; edit it to modify the dashboard. Do not expect UI edits to overwrite provisioning configuration.

### 3.4. Compose file

`compose.yml`:

```yaml
services:
  app:
    build: .
    environment:
      JAVA_TOOL_OPTIONS: "-Xms128m -Xmx256m"
    ports:
      - "127.0.0.1:8080:8080"

  prometheus:
    image: prom/prometheus:v2.54.1
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.path=/prometheus"
      - "--storage.tsdb.retention.time=2d"
    volumes:
      - ./observability/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus-data:/prometheus
    ports:
      - "127.0.0.1:9090:9090"
    depends_on:
      - app

  grafana:
    image: grafana/grafana:11.2.2
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:?Set GRAFANA_ADMIN_PASSWORD}
      GF_USERS_ALLOW_SIGN_UP: "false"
    volumes:
      - ./observability/grafana/provisioning:/etc/grafana/provisioning:ro
      - ./observability/grafana/dashboards:/var/lib/grafana/dashboards:ro
      - grafana-data:/var/lib/grafana
    ports:
      - "127.0.0.1:3000:3000"
    depends_on:
      - prometheus

volumes:
  prometheus-data:
  grafana-data:
```

Ports published on host loopback for the lab:

| Address opened from host | Purpose |
| --- | --- |
| `http://localhost:8080` | Application and Actuator endpoints |
| `http://localhost:9090` | Prometheus UI/query API |
| `http://localhost:3000` | Grafana |

`depends_on` orders startup, not readiness. Prometheus may briefly report the target DOWN while Boot starts up, then automatically recover on subsequent scrapes.

Two named volumes preserve Prometheus and Grafana data across container recreations. Prometheus is set to a 2-day retention window for the lab; this is not a production retention policy.

The Grafana password environment variable must be set before Compose interpolates the configuration. The initial password applies only when initializing the account in Grafana storage; changing the environment variable later does not automatically reset an account password already stored in the volume.

## 4. Complete Grafana dashboard

Save all of the following JSON to `observability/grafana/dashboards/spring-boot.json`. The datasource UID `prometheus-lab` must match the datasource file created earlier.

The dashboard includes an application selector variable, three HTTP panels, JVM heap memory, simulated work completion rate, per-instance CPU, and scrape status.

```json
{
  "uid": "spring-boot-metrics-lab",
  "title": "Spring Boot Metrics Lab",
  "schemaVersion": 39,
  "version": 1,
  "editable": false,
  "refresh": "5s",
  "time": {
    "from": "now-15m",
    "to": "now"
  },
  "timezone": "browser",
  "tags": [
    "spring-boot",
    "prometheus",
    "lab"
  ],
  "templating": {
    "list": [
      {
        "name": "application",
        "label": "Application",
        "type": "query",
        "datasource": {
          "type": "prometheus",
          "uid": "prometheus-lab"
        },
        "definition": "label_values(jvm_memory_used_bytes{job=\"spring-boot-lab\"}, application)",
        "query": {
          "query": "label_values(jvm_memory_used_bytes{job=\"spring-boot-lab\"}, application)",
          "refId": "PrometheusVariableQueryEditor-VariableQuery"
        },
        "refresh": 1,
        "sort": 1,
        "multi": false,
        "includeAll": false,
        "current": {
          "text": "metrics-lab",
          "value": "metrics-lab"
        },
        "options": []
      }
    ]
  },
  "panels": [
    {
      "id": 1,
      "title": "HTTP orders / sec",
      "type": "timeseries",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus-lab"
      },
      "gridPos": {
        "x": 0,
        "y": 0,
        "w": 8,
        "h": 8
      },
      "fieldConfig": {
        "defaults": {
          "unit": "reqps",
          "min": 0
        },
        "overrides": []
      },
      "options": {
        "legend": {
          "displayMode": "list",
          "placement": "bottom"
        }
      },
      "targets": [
        {
          "refId": "A",
          "expr": "sum(rate(http_server_requests_seconds_count{job=\"spring-boot-lab\",application=~\"${application:regex}\",uri=\"/demo/orders\",method=\"POST\"}[$__rate_interval]))",
          "legendFormat": "HTTP orders / sec",
          "range": true,
          "editorMode": "code",
          "instant": false
        }
      ]
    },
    {
      "id": 2,
      "title": "HTTP 5xx rate",
      "type": "stat",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus-lab"
      },
      "gridPos": {
        "x": 8,
        "y": 0,
        "w": 8,
        "h": 8
      },
      "fieldConfig": {
        "defaults": {
          "unit": "percentunit",
          "min": 0
        },
        "overrides": []
      },
      "options": {
        "colorMode": "value",
        "graphMode": "none",
        "reduceOptions": {
          "calcs": [
            "lastNotNull"
          ],
          "fields": "",
          "values": false
        }
      },
      "targets": [
        {
          "refId": "A",
          "expr": "(sum(rate(http_server_requests_seconds_count{job=\"spring-boot-lab\",application=~\"${application:regex}\",uri=\"/demo/orders\",method=\"POST\",status=~\"5..\"}[$__rate_interval])) or vector(0)) / sum(rate(http_server_requests_seconds_count{job=\"spring-boot-lab\",application=~\"${application:regex}\",uri=\"/demo/orders\",method=\"POST\"}[$__rate_interval]))",
          "legendFormat": "HTTP 5xx rate",
          "range": false,
          "editorMode": "code",
          "instant": true
        }
      ]
    },
    {
      "id": 3,
      "title": "HTTP p95 latency",
      "type": "timeseries",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus-lab"
      },
      "gridPos": {
        "x": 16,
        "y": 0,
        "w": 8,
        "h": 8
      },
      "fieldConfig": {
        "defaults": {
          "unit": "s",
          "min": 0
        },
        "overrides": []
      },
      "options": {
        "legend": {
          "displayMode": "list",
          "placement": "bottom"
        }
      },
      "targets": [
        {
          "refId": "A",
          "expr": "histogram_quantile(0.95, sum by (le) (rate(http_server_requests_seconds_bucket{job=\"spring-boot-lab\",application=~\"${application:regex}\",uri=\"/demo/orders\",method=\"POST\"}[$__rate_interval])))",
          "legendFormat": "HTTP p95 latency",
          "range": true,
          "editorMode": "code",
          "instant": false
        }
      ]
    },
    {
      "id": 4,
      "title": "JVM heap memory across instances",
      "type": "timeseries",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus-lab"
      },
      "gridPos": {
        "x": 0,
        "y": 8,
        "w": 12,
        "h": 8
      },
      "fieldConfig": {
        "defaults": {
          "unit": "bytes",
          "min": 0
        },
        "overrides": []
      },
      "options": {
        "legend": {
          "displayMode": "list",
          "placement": "bottom"
        }
      },
      "targets": [
        {
          "refId": "A",
          "expr": "sum(jvm_memory_used_bytes{job=\"spring-boot-lab\",application=~\"${application:regex}\",area=\"heap\"})",
          "legendFormat": "JVM heap memory across instances",
          "range": true,
          "editorMode": "code",
          "instant": false
        }
      ]
    },
    {
      "id": 5,
      "title": "Simulated orders completed / sec",
      "type": "timeseries",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus-lab"
      },
      "gridPos": {
        "x": 12,
        "y": 8,
        "w": 12,
        "h": 8
      },
      "fieldConfig": {
        "defaults": {
          "unit": "ops",
          "min": 0
        },
        "overrides": []
      },
      "options": {
        "legend": {
          "displayMode": "list",
          "placement": "bottom"
        }
      },
      "targets": [
        {
          "refId": "A",
          "expr": "sum by (outcome) (rate(lab_orders_completed_total{job=\"spring-boot-lab\",application=~\"${application:regex}\"}[$__rate_interval]))",
          "legendFormat": "{{outcome}}",
          "range": true,
          "editorMode": "code",
          "instant": false
        }
      ]
    },
    {
      "id": 6,
      "title": "Process CPU by instance",
      "type": "timeseries",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus-lab"
      },
      "gridPos": {
        "x": 0,
        "y": 16,
        "w": 12,
        "h": 8
      },
      "fieldConfig": {
        "defaults": {
          "unit": "percentunit",
          "min": 0
        },
        "overrides": []
      },
      "options": {
        "legend": {
          "displayMode": "list",
          "placement": "bottom"
        }
      },
      "targets": [
        {
          "refId": "A",
          "expr": "process_cpu_usage{job=\"spring-boot-lab\",application=~\"${application:regex}\"}",
          "legendFormat": "{{instance}}",
          "range": true,
          "editorMode": "code",
          "instant": false
        }
      ]
    },
    {
      "id": 7,
      "title": "Prometheus scrape status",
      "type": "stat",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus-lab"
      },
      "gridPos": {
        "x": 12,
        "y": 16,
        "w": 12,
        "h": 8
      },
      "fieldConfig": {
        "defaults": {
          "unit": "none",
          "min": 0,
          "decimals": 0,
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "red",
                "value": null
              },
              {
                "color": "green",
                "value": 1
              }
            ]
          }
        },
        "overrides": []
      },
      "options": {
        "colorMode": "value",
        "graphMode": "none",
        "reduceOptions": {
          "calcs": [
            "lastNotNull"
          ],
          "fields": "",
          "values": false
        }
      },
      "targets": [
        {
          "refId": "A",
          "expr": "up{job=\"spring-boot-lab\"}",
          "legendFormat": "{{instance}}",
          "range": false,
          "editorMode": "code",
          "instant": true
        }
      ]
    }
  ]
}
```

Key details to understand from the configuration:

- The `application` variable pulls label values from this job's JVM metrics; business requests are not required beforehand to select the application.
- HTTP queries filter specifically on `POST /demo/orders`, so health requests and scrape requests do not skew the business chart under study.
- The error-rate panel and `up` panel use instant queries to read the current point-in-time result.
- Time-series panels use range queries.
- Error rate/CPU use percent-unit from 0–1 inputs; p95 uses seconds; heap uses bytes.
- The Prometheus-generated `up` metric carries target labels such as `job` and `instance`, and does not inherit Micrometer's common tag `application`. The up panel filters by the lab's job, which contains only this demo application.
- Heap memory in the panel is summed across selected instances; CPU is kept as separate lines per instance.

If extending the same job to multiple applications, add appropriate target labels and update the `up` filter. Do not assume changing the application variable automatically filters every Prometheus-generated metric.

### 4.1. Throughput: Counter vs. rate

Query usable directly in the Prometheus UI:

```promql
sum(
  rate(http_server_requests_seconds_count{
    job="spring-boot-lab",
    application="metrics-lab",
    uri="/demo/orders",
    method="POST"
  }[1m])
)
```

`_count` is the cumulative request count of the Timer. `rate(...[1m])` calculates the per-second average rate over a 1-minute window; `sum` aggregates matching series.

Compute rate per series before summing so per-instance counter resets are handled properly. Do not use raw cumulative counter values directly as requests/second.

In the dashboard JSON, the window is replaced by `$__rate_interval`. That is a Grafana variable, not syntax Prometheus understands natively. When testing in the Prometheus UI, use a concrete window like `[1m]` and concrete labels as shown above.

Rate windows need enough samples. With 5-second scrapes, a 5-second window easily lacks sufficient points. Increasing dashboard refresh speed does not make Prometheus scrape more frequently.

### 4.2. HTTP 5xx error rate

```promql
(
  sum(
    rate(http_server_requests_seconds_count{
      job="spring-boot-lab",
      application="metrics-lab",
      uri="/demo/orders",
      method="POST",
      status=~"5.."
    }[1m])
  )
  or vector(0)
)
/
sum(
  rate(http_server_requests_seconds_count{
    job="spring-boot-lab",
    application="metrics-lab",
    uri="/demo/orders",
    method="POST"
  }[1m])
)
```

The numerator is the 5xx request rate; the denominator is the rate of all requests matching the same route and method. A result of 0.2 is a 20% rate, not 0.2%.

`or vector(0)` in the numerator turns a missing 5xx series into a numerator of 0 when the denominator has traffic. It does not turn completely missing data into a healthy system. If there are no requests in the window, the denominator can be 0; the ratio is then undefined and may display No data/NaN.

Do not substitute 0 for every missing datum. When gaps appear, check the up panel and underlying raw series first.

This is the HTTP 5xx error rate. It is not automatically the business failure rate of every system, because some applications represent business failures with other HTTP codes.

### 4.3. p95 latency from histograms

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      job="spring-boot-lab",
      application="metrics-lab",
      uri="/demo/orders",
      method="POST"
    }[1m])
  )
)
```

Classic histogram buckets carry the `le` label, representing the upper bound and cumulative count up to that bound. Preserve `le` when aggregating across instances so `histogram_quantile` still sees the bucket distribution.

p95 is an estimate from the histogram: roughly 95% of observations had durations no greater than that estimated quantile. It does not mean every request took exactly p95, nor is it the maximum value.

Do not average per-instance p95 values to infer a shared p95. To aggregate, sum appropriate buckets first and then compute the quantile. Accuracy also depends on bucket boundaries and data within the window.

SLO boundaries in the histogram config only add measurement buckets. They do not create SLO commitments, check target attainment rates, or send alerts.

### 4.4. Correlate business metrics and resources

The simulated-orders panel computes the rate of `lab_orders_completed_total` grouped by `outcome`. After generating traffic, there will be success and failure lines. Label series are bounded to the two values registered in code.

Heap is an instantaneous measurement, so do not apply `rate` to it as with counters. CPU in the panel is process utilization provided by the meter; percent formatting on the dashboard does not convert it into number of CPU cores consumed.

CPU measurements can depend on JVM/OS support. If only the CPU panel lacks data, check whether the metric is being exported before concluding the whole scraping pipeline is broken.

## 5. Start up and verify stage by stage

### 5.1. Build and run

Once all files are created, in the directory containing `pom.xml`:

```powershell
mvn clean package
```

In PowerShell 7, enter the initial Grafana password without echoing characters:

```powershell
$env:GRAFANA_ADMIN_PASSWORD = Read-Host -MaskInput "Grafana password for practice lab"
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

The first run requires network access for Maven to download dependencies and Docker to pull base images/images. The Docker daemon must be running in Linux containers mode.

Compose binds exposed ports only to 127.0.0.1 for local study on the current machine. Do not reuse this configuration verbatim as a production security/deployment design.

### 5.2. Stage 1: the application actually exports metrics

```powershell
curl.exe -i http://localhost:8080/actuator/health
curl.exe -i http://localhost:8080/actuator/prometheus
```

The Prometheus endpoint must return metrics text with HTTP 200, not a login page or JSON from `/actuator/metrics`. HELP/TYPE lines and sample values show the exposition format; full contents change with time and JVM state.

Send two requests so the HTTP series for the business route appear:

```powershell
curl.exe -i -X POST "http://localhost:8080/demo/orders?outcome=success"
curl.exe -i -X POST "http://localhost:8080/demo/orders?outcome=failure"
```

The first request returns HTTP 200 with JSON:

```json
{"outcome":"success"}
```

The second request returns intentional HTTP 503 with JSON:

```json
{"outcome":"failure"}
```

Re-read the metrics endpoint and look for the names:

```text
lab_orders_completed_total
http_server_requests_seconds_count
http_server_requests_seconds_sum
http_server_requests_seconds_bucket
jvm_memory_used_bytes
```

Do not try to match the entire response as a fixed stdout string: JVM values, timestamps, and scrape counts change continuously. Verify metric names, labels, and relationships between measurements.

### 5.3. Stage 2: Prometheus scrapes successfully

Open [Prometheus](http://localhost:9090), go to the Targets page, and locate job `spring-boot-lab`. The target should transition to UP after the application starts and one scrape succeeds.

In the query page, run:

```promql
up{job="spring-boot-lab"}
```

A value of 1 means the most recent scrape of that target succeeded; 0 means the scrape failed. It does not guarantee all application business logic is healthy.

Next check raw business data:

```promql
lab_orders_completed_total{job="spring-boot-lab",application="metrics-lab"}
```

If the application endpoint has data but Prometheus queries do not yet, inspect the target and wait for a scrape cycle; do not jump straight to editing the dashboard.

You can validate the config file inside the container with:

```powershell
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
```

### 5.4. Stage 3: Grafana reads the right Prometheus

Open [Grafana](http://localhost:3000), sign in with user `admin` and the password entered earlier. Find the `Spring Boot Lab` folder and open the `Spring Boot Metrics Lab` dashboard.

Select application `metrics-lab`, time range Last 15 minutes, and observe the panels. The datasource is already provisioned with a fixed UID; there is no need to enter the Prometheus URL again through the UI.

If you modify datasource provisioning, restart Grafana to apply the corresponding configuration. The dashboard provider in this example polls JSON file changes periodically; still keep JSON valid and wait for it to reload.

## 6. Generate traffic to read the dashboard

Run the following loop in PowerShell. Every fifth request is a failure. The script is sequential, so sleep time, processing latency, and network overhead jointly determine the actual rate.

```powershell
for ($requestIndex = 1; $requestIndex -le 300; $requestIndex++) {
    $outcome = if ($requestIndex % 5 -eq 0) { "failure" } else { "success" }
    $httpCode = & curl.exe --silent --show-error -o NUL -w "%{http_code}" -X POST "http://localhost:8080/demo/orders?outcome=$outcome"

    if ($httpCode -ne "200" -and $httpCode -ne "503") {
        Write-Warning "Unexpected HTTP status code: $httpCode"
    }
    Start-Sleep -Milliseconds 100
}
```

503 is an intentionally generated outcome here, so the loop does not treat that code alone as an unexpected execution error. These commands use Windows `NUL` to discard the response body.

Observe after accumulating enough samples, typically needing about 30–60 seconds in this lab:

| Panel | Observation to explain |
| --- | --- |
| HTTP orders / sec | Shows rate; not the monotonically growing counter since startup |
| HTTP 5xx rate | Approaches the failure request ratio in the window; need not equal exactly 20% at every instant |
| HTTP p95 latency | Reflects the slow tail of requests; not the average of 40 ms and 120 ms |
| Simulated orders completed / sec | Shows two lines, success/failure, bounded as defined in code |
| JVM heap | Can rise and fall with allocation and GC, need not increase monotonically |
| CPU by instance | Shows process CPU usage, not sleep wait time |
| Scrape status | 1 when Prometheus successfully scrapes the target |

When load stops, rates drop toward 0 after earlier requests leave the calculation window. Error rate and p95 may lose meaningful values when there are no observations. Always read them alongside the time range and scrape status.

To test the difference between HTTP metrics and the business counter, send a request with `outcome=unknown`. It returns 400 and is counted by the HTTP Timer, without creating an `outcome=unknown` series on the completion counter.

## 7. Inject failures to practice diagnostics

### 7.1. Stop the application while keeping observability up

```powershell
docker compose stop app
```

After the next scrape, the application target fails and `up` must reflect that. Historical data remains in Prometheus. A dashboard still displaying historical lines does not mean the application is still emitting fresh metrics.

Restart it:

```powershell
docker compose start app
```

Counters in the new application process start fresh. `rate` queries are designed to handle counter resets in a series, though results immediately after restart still depend on sample count and window. Do not subtract two arbitrary counter values and treat a negative difference as negative requests.

If a target is removed from configuration instead of merely stopping responses, distinguish “target series no longer exists” from `up=0`. Do not rely on a simple up panel as your entire missing-target detection strategy.

### 7.2. Stage-by-stage troubleshooting table

| Symptom | Check first |
| --- | --- |
| `/actuator/prometheus` returns 404 | Registry dependency, exposure, base/context path, and auto-configuration conditions |
| Endpoint returns 401/403 or login HTML | Security policy applied to the scrape path |
| Target DOWN with connection error | Is app running; does target use `app:8080` on the right Compose network |
| Target DOWN with timeout | Endpoint latency, app load, and scrape timeout |
| Target UP but missing `http_server_requests_seconds_count` for route | Was that endpoint actually called; are URI/method labels exact |
| Has `_count`, `_sum` but missing `_bucket` | Was histogram enabled for the exact meter name and app restarted |
| Prometheus has data but Grafana shows No data | Datasource UID/URL, application variable, query labels, and time range |
| Rate query has few points or is empty | Sample count, scrape interval, and rate window |
| Error rate differs greatly from expected | Do numerator/denominator share route, method, app, and window; are 4xx involved |
| p95 meaningless with few requests | Observation count and buckets; do not infer precision from a single number |
| Dashboard JSON does not appear | Right file/folder mount, valid JSON, provider, and Grafana logs |

Log inspection commands:

```powershell
docker compose logs --tail 100 app
docker compose logs --tail 100 prometheus
docker compose logs --tail 100 grafana
```

Diagnosing in order application → Prometheus → Grafana prevents editing queries when source data was never collected.

## 8. Boundaries to preserve when scaling

### 8.1. Labels and series count

Keep labels in a controlled value set. Never use order ID, user ID, email, trace ID, raw URLs with parameters, or exception messages as metric labels.

HTTP `uri` labels should represent route templates such as `/orders/{id}` rather than a different path value per order. Histograms also multiply series count by bucket count; do not turn on histograms for every meter indiscriminately.

Logs and traces fit tracking a specific request. Metrics fit aggregating trends and rates over bounded label sets.

### 8.2. Security and operational cost

Metrics endpoints can reveal service names, routes, resources, and internal labels. In real deployments, choose network and authentication policies for the Prometheus → application path; if the endpoint requires auth, Prometheus must be configured to scrape per that contract.

Never place credentials in labels, dashboard JSON, or query URLs. Bound data volume, retention, storage volume size, and query cost to actual needs.

This dashboard does not create alerts yet. SLO thresholds, alerts, notification routing, and incident response are separate design decisions. Do not treat a dashboard full of charts as a complete production monitoring system.

### 8.3. Reproducibility and verification scope

Provisioning files rebuild the datasource and dashboard. They do not guarantee two runs produce identical numbers: JVM behavior, host load, scrape timing, and history differ.

Testing code with mock HTTP can confirm counters, HTTP Timers, labels, and histograms are exported properly. It does not replace verifying Prometheus actually scrapes the container or confirming the dashboard renders in Grafana. Go through all three stages in section 5 when running in a real environment.

Stop the lab:

```powershell
docker compose down
Remove-Item Env:GRAFANA_ADMIN_PASSWORD
```

`docker compose down` here does not delete the named volumes. When restarting with the old Grafana volume, use the account/password stored in that data.

## 9. Acceptance criteria

1. The Prometheus registry is created and `/actuator/prometheus` returns metrics data.
2. Successful/failed HTTP requests increment the right custom counters without creating labels from arbitrary inputs.
3. HTTP Timer has count/sum and histogram buckets as configured.
4. Prometheus target is UP and application metrics are readable with PromQL.
5. Grafana datasource points to the internal Prometheus network address and the dashboard loads from JSON.
6. Throughput queries use counter rates; error-rate queries use matching numerator/denominator scope; p95 is computed from buckets.
7. Time, ratio, and memory units are correct; missing data is distinguished from 0.
8. Starting load, stopping load, and restarting the app are all explainable from metric behavior and query windows.
9. Labels are bounded, scrape paths have proper access policies, and historical data is explicitly managed.

Whenever reading a panel, always verify what it measures, which series it selects, what window it aggregates over, and what unit it uses. Those questions connect measurements in code to genuinely useful operational insight on a dashboard.
