# Integrating Registries for Datadog, InfluxDB, or StatsD as Needed

A Spring Boot application can send the same measurement to different systems while still using the Micrometer API to record it. What changes per environment is the **registry**, the ingestion address, and the authentication mechanism. For Datadog, first distinguish between two delivery paths. The application can call the Datadog API directly or send StatsD packets to an Agent for the Agent to forward.

| Application Destination | Micrometer Dependency | Export Mechanism |
| --- | --- | --- |
| Datadog Metrics API | `micrometer-registry-datadog` | Periodically sends over HTTPS to the Datadog site. |
| InfluxDB | `micrometer-registry-influx` | Periodically sends data points to InfluxDB's write API. |
| StatsD daemon or DogStatsD Agent | `micrometer-registry-statsd` | Sends metric lines using the protocol flavor supported by the receiver. The example uses UDP. |

## Preparing Spring Boot 3.3

Use `spring-boot-starter-actuator`. Add the `runtimeOnly` line for the chosen option to the `dependencies` block and let Spring Boot's dependency management select the Micrometer version. If a single build needs to carry multiple registries for different environments, use profiles to select the active registry.

With the profile-based approach in this article, put the shared baseline in `application.properties`:

~~~properties
management.defaults.metrics.export.enabled=false
management.metrics.tags.application=export-demo
~~~

The first flag disables Spring Boot auto-configured exporters by default. Each profile below enables a single exporter using `enabled=true`. The `application` tag helps filter the application's data at the destination. Activate an appropriate profile, such as setting `SPRING_PROFILES_ACTIVE=metrics-influx` in the runtime environment when choosing InfluxDB.

## 1. Datadog via API

Dependency:

~~~groovy
runtimeOnly 'io.micrometer:micrometer-registry-datadog'
~~~

In `application-metrics-datadog.properties`:

~~~properties
management.datadog.metrics.export.enabled=true
management.datadog.metrics.export.api-key=${DATADOG_API_KEY}
management.datadog.metrics.export.step=30s
~~~

Supply `DATADOG_API_KEY` to the process from a secret store. The API key is used to submit metrics. The Application key is optional for exporting additional meter metadata. Spring Boot defaults to Datadog US. If your account uses a different site or the application must route through an internal proxy, configure `management.datadog.metrics.export.uri` to match your environment's address.

The application needs outbound HTTPS connectivity to the chosen endpoint. After starting, wait for an export interval and look for measurements in your account's site, filtering by the time range and tag `application:export-demo`. If authentication errors occur, verify whether the API key belongs to the right site and environment.

## 2. InfluxDB via Write API

Dependency:

~~~groovy
runtimeOnly 'io.micrometer:micrometer-registry-influx'
~~~

In `application-metrics-influx.properties`, example for **InfluxDB v2**:

~~~properties
management.influx.metrics.export.enabled=true
management.influx.metrics.export.api-version=v2
management.influx.metrics.export.uri=https://influx.example.com:8086
management.influx.metrics.export.org=platform
management.influx.metrics.export.bucket=app-metrics
management.influx.metrics.export.token=${INFLUX_METRICS_TOKEN}
management.influx.metrics.export.step=30s
~~~

Replace the URI, org, and bucket with your deployment values. The bucket must exist and the token must have write permission for that bucket. `uri` is the base server address in the example. The registry appends the write API path according to the chosen version. Check data in the right org, bucket, and time range after the export interval.

For **InfluxDB v1**, use `api-version=v1`, select the database with `management.influx.metrics.export.db`, and supply `user-name` and `password` if the server enables authentication. The `org`, `bucket`, and `token` properties in the example belong to v2 configuration. If the v1 database is pre-provisioned by infrastructure, you can set `management.influx.metrics.export.auto-create-db=false`.

## 3. StatsD or DogStatsD via Agent

Dependency:

~~~groovy
runtimeOnly 'io.micrometer:micrometer-registry-statsd'
~~~

In `application-metrics-statsd.properties`, example for an Agent supporting **DogStatsD** over UDP:

~~~properties
management.statsd.metrics.export.enabled=true
management.statsd.metrics.export.host=statsd-agent
management.statsd.metrics.export.port=8125
management.statsd.metrics.export.protocol=udp
management.statsd.metrics.export.flavor=datadog
~~~

`host` and `port` specify where the Agent receives packets from the application. `protocol` is the transport, while `flavor` determines how metric lines and tags are formatted. The example uses `datadog` because the receiver understands DogStatsD. For a daemon compatible with Etsy's original StatsD protocol, choose `flavor=etsy` and check receiver capabilities, especially tag support.

The name `statsd-agent` must resolve from the application process. Inside a container, `localhost` points to that container itself. When the Agent is elsewhere, use an address reachable by the application and configure the Agent to listen on an appropriate interface. With the DogStatsD path, credentials for forwarding data from the Agent to Datadog belong to the Agent's configuration.

UDP has no per-packet acknowledgment. When data is missing, check the Agent's packet-receive counters or logs, the UDP port, and forwarding configuration. If the same meter is sent to the same store via both the Datadog API and DogStatsD, check for duplicate data before summing the results.

## Verifying with an Easily Identifiable Measurement

In a test application that already has Spring Boot Actuator, add `ExportProbe.java` to a Spring-scanned package. The example uses a fixed gauge to observe data across multiple export cycles. The `probeValue` field holds a reference to the value that the gauge reads.

~~~java
package example;

import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class ExportProbe {
    private final AtomicInteger probeValue = new AtomicInteger(7);

    public ExportProbe(MeterRegistry registry) {
        Gauge.builder("demo.export.probe", probeValue, AtomicInteger::get)
                .register(registry);
    }
}
~~~

1. Run the application with the chosen profile. In a controlled test environment, if the `metrics` endpoint is exposed, call `GET /actuator/metrics/demo.export.probe` and verify that the `VALUE` measurement equals 7. This proves the application registered the meter.
2. Check the destination. For Datadog or InfluxDB, observe after at least one export interval. For StatsD, check that the Agent receives and forwards or aggregates the gauge line. Use the application tag on destinations that support tags and check naming conventions when searching for the measurement.
3. If you see 7 in Actuator but not at the destination, isolate the export stage by profile, network, credentials, and receiver errors. If data appears from multiple pipelines, check active profiles and exporters.

### References

- [Spring Boot 3.3 – Datadog, Influx, and StatsD Registries](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Spring Boot 3.3 – Registry Configuration Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)
- [Micrometer 1.13 – StatsD Protocol and Format Flavors](https://docs.micrometer.io/micrometer/reference/1.13/implementations/statsD.html)