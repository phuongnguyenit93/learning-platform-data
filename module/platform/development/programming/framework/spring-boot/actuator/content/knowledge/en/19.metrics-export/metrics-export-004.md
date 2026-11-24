## Configuring Metrics Export via OTLP

When a Collector is the central ingestion point for telemetry, a Spring Boot application can use Micrometer's OTLP registry to send metrics periodically. Business code continues recording to `MeterRegistry`. The exporter reads measurements from the registry, packages them, and sends them to the receiver. When verifying the configuration, confirm both that the application recorded the measurements and that the Collector received those exact measurements.

### Choosing the Right Exporter and Endpoint

With Spring Boot 3.3 and Micrometer 1.13, add `spring-boot-starter-actuator` and `io.micrometer:micrometer-registry-otlp`. Use Spring Boot's BOM to manage compatible versions. When auto-configuration is active, Spring Boot creates an OTLP registry and applies properties under `management.otlp.metrics.export`. The metrics exporter in this example sends `POST` requests over **OTLP/HTTP**. The common port is `4318`, and `/v1/metrics` is the default metrics ingestion path. If the Collector only exposes an OTLP/gRPC port, you must enable an HTTP receiver to use this configuration. The trace export path and trace sending configuration belong to a separate flow.

Save the following configuration in `src/main/resources/application.yml` when the application and Collector run directly on the same machine.

```yaml
management:
  otlp:
    metrics:
      export:
        enabled: true
        url: http://127.0.0.1:4318/v1/metrics
        step: 15s
        aggregation-temporality: cumulative
        resource-attributes:
          "[service.name]": checkout-otlp-demo
```

| Property | Role |
| --- | --- |
| `enabled` | Enables the OTLP exporter when the corresponding library is on the classpath. Set `false` to disable only the OTLP flow in an environment. |
| `url` | Full address of the metrics ingestion endpoint, including scheme, host, port if needed, and path. |
| `step` | Interval between export cycles. The default in Spring Boot 3.3.0 is one minute. The example uses 15 seconds for faster observation. |
| `aggregation-temporality` | Chooses how cumulative quantities such as Counter and Histogram are represented across export intervals. |
| `resource-attributes` | Shared source-identifying metadata for exported data, such as `service.name`. The `channel` tag in the example is an attribute of the specific data point. |
| `headers` | Additional headers required by the receiver's contract, such as authentication credentials. |

With `cumulative`, a Counter within the same process lifecycle may export `3` and then `5` after incrementing by two. With `delta`, two separate intervals may carry increments of `3` and then `2` respectively. These numbers assume each increment occurs in a separate interval. Choose the temporality supported by your receiver and query engine. When the process restarts, the counter may start over from the beginning. When an export cycle is lost, recovery capability depends on the exporter, buffering, and temporality mode.

### Running a Test Collector

Save `otelcol.yaml` outside the application. Use a Collector distribution that includes the `otlp` receiver and `debug` exporter.

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: "127.0.0.1:4318"
exporters:
  debug:
    verbosity: detailed
service:
  pipelines:
    metrics:
      receivers: [otlp]
      exporters: [debug]
```

```bash
otelcol validate --config=otelcol.yaml
otelcol --config=otelcol.yaml
```

In this configuration, the receiver listens on loopback and the metrics pipeline outputs received data to detailed logs. `debug` lets you inspect data at the Collector. To query metrics later, use an exporter that writes data to a metrics storage backend. If running in separate containers, configure the receiver to listen on an appropriate network interface and set `url` to a DNS name reachable by the application. The application's loopback does not point to the Collector container.

### Sending an Easily Recognizable Counter

The following Java example runs with JDK 17 and Gradle 8.x. Set `rootProject.name = 'otlp-export-demo'` in `settings.gradle`, then use the following `build.gradle`. The Jackson library on the classpath supports Actuator auto-configuration for the command-line application in the example.

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-otlp'
    runtimeOnly 'com.fasterxml.jackson.core:jackson-databind'
}
```

Save the Java file at `src/main/java/demo/otlp/OtlpExportDemo.java`.

```java
package demo.otlp;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;

@SpringBootApplication
public class OtlpExportDemo {
    public static void main(String[] args) throws InterruptedException {
        try (var context = new SpringApplicationBuilder(OtlpExportDemo.class)
                .web(WebApplicationType.NONE)
                .run(args)) {
            var registry = context.getBean(MeterRegistry.class);
            var counter = registry.counter("demo.checkout.completed", "channel", "web");
            long pauseMillis = 1000L * context.getEnvironment()
                    .getProperty("demo.pause-seconds", Long.class, 20L);

            counter.increment(3);
            System.out.println("recorded=" + counter.count());
            Thread.sleep(pauseMillis);

            counter.increment(2);
            System.out.println("recorded=" + counter.count());
            Thread.sleep(pauseMillis);
        }
    }
}
```

While the Collector is running, start the application in another terminal window.

```bash
gradle bootRun
```

In addition to Spring Boot startup logs, the program prints the following two lines about 20 seconds apart.

```text
recorded=3.0
recorded=5.0
```

Those lines confirm the application recorded the measurements into the registry. In the Collector logs, look for metric `demo.checkout.completed`, data point attribute `channel=web`, and resource attribute `service.name=checkout-otlp-demo`. With `cumulative` configured, expect a point with value 3 in one interval and 5 in a later interval after the second increment occurred. Compare receipt timestamps and values rather than counting exactly two log lines. The exporter may send before the first increment or while the value remains unchanged, depending on startup timing. The application waits after each increment so it has a chance to export on the 15-second cadence.

### Changing the Destination per Environment

If the deployment target requires a Bearer token over HTTPS, you can place overrides in `application-production.yml` and activate the `production` profile. Provide the full URL and token in the deployment environment configuration.

```yaml
management:
  otlp:
    metrics:
      export:
        url: ${OTLP_METRICS_URL}
        headers:
          "[Authorization]": "Bearer ${OTLP_TOKEN}"
```

Bracket syntax preserves the configuration map key verbatim, such as `service.name` and `Authorization`. If the exported service name differs from expectations, also check the `OTEL_SERVICE_NAME` variable because Micrometer 1.13 can use this variable to override `service.name`. If the receiver specifies a different header name or authentication scheme, follow the receiver's exact contract. When configuring shorter intervals, check meter counts, export volume, and receiver latency. `batch-size` limits the number of meters per registry payload. `connect-timeout` and `read-timeout` adjust timeouts for connecting and reading responses.

### Isolating Missing Data

| Symptom | Checkpoints |
| --- | --- |
| Counter incremented, Collector received nothing | Check that the OTLP library is on the runtime classpath, the active Spring profile, `enabled`, and elapsed time relative to `step`. |
| Connection refused or timed out | Check listening address, DNS, and network reachability from the application process. |
| Received HTTP 404 | Check whether the URL has the right metrics ingestion path, typically `/v1/metrics`, and whether any proxy forwards the path properly. |
| Received HTTP 401 or 403 | Check authentication method, headers, and permissions at the destination. |
| Collector received data, but storage backend lacks it | Check the `metrics` pipeline, downstream errors or rejected points, source name, and query time range. |

In OTLP/HTTP, an HTTP 200 response can still indicate partial acceptance. When diagnosing, compare accepted or rejected point counts at the Collector for the specific metric. Separate confirming HTTP success from confirming that data reached the storage backend.

### References

- [Spring Boot 3.3 Actuator — OTLP Metrics Auto-Configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Micrometer 1.13 — OTLP Registry Configuration](https://docs.micrometer.io/micrometer/reference/1.13/implementations/otlp)
- [OpenTelemetry Collector — Receiver, Exporter, and Pipeline](https://opentelemetry.io/docs/collector/configuration/)
- [OpenTelemetry — OTLP/HTTP Specification](https://opentelemetry.io/docs/specs/otlp/#otlphttp)