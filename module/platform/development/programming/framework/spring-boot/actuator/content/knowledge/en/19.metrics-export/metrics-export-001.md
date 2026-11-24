## Distinguishing Pull-Based from Push-Based Data Collection

An application can record the same measurement in memory yet expose that measurement externally in two ways. With the pull mechanism, the collector actively comes to read it. With the push mechanism, the exporter on the source side actively sends it to the receiver. Identify **who initiates the connection at each hop**. Both mechanisms transfer metric values from where measurements are produced to where they are collected.

### Who Connects and Who Controls the Cadence?

| Point to Identify | Direct Pull with Prometheus | Push with Micrometer's OTLP Exporter |
| --- | --- | --- |
| Connection initiator | Prometheus sends a `GET` request to the application's endpoint. | The application sends a `POST` with metrics data to the OTLP/HTTP receiver. |
| Schedule controller | Prometheus sets `scrape_interval` for the scrape job. | The application sets `management.otlp.metrics.export.step` for the export cadence. |
| Reachable address required | From Prometheus to each target, such as the application's management port. | From the application to the Collector or an OTLP-capable receiver. |
| Signals when an issue occurs | Target status, last scrape error, and the `up` metric. | Exporter send errors, receiver-side ingestion counts, and the timestamp of the latest data point received from the source. |

**Pull.** Micrometer's registry holds the measurements inside the application. Upon receiving `GET /actuator/prometheus`, Actuator returns the measurements in Prometheus scrape format. Prometheus stores samples according to its own schedule. A manual `curl` call verifies that the endpoint has data, while the **Targets** page and `up` indicate whether Prometheus can actually reach and read the endpoint over its network path. `up=1` indicates a successful scrape; whether the service satisfies business logic must be measured separately.

**Push.** Application code continues recording measurements into Micrometer. The OTLP exporter batches and sends data points according to the configured step. The `/v1/metrics` destination is the OTLP/HTTP receiver endpoint, commonly using port `4318`. With a Collector, the receiver ingests the payload and routes it through the metrics pipeline to one or more exporters. Successfully reaching the Collector only verifies the first hop. To confirm that the storage backend has the data, you must also check the hop from the Collector to the final destination.

A `Counter.increment()` call records an occurrence in the registry. It does not correspond to a single HTTP export request. The delay before a measurement becomes visible depends on the scrape interval or export step, along with downstream processing steps.

### Comparing Both on the Same Spring Boot 3.3 Application

This example is for a test environment where the application, Prometheus, and OpenTelemetry Collector run directly on the same machine. The web application listens on port `8080` and includes `spring-boot-starter-actuator`. Add both registries below to observe both flows from the same measurement source. With Gradle using Spring Boot's BOM, add the following two dependencies.

```groovy
runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
runtimeOnly 'io.micrometer:micrometer-registry-otlp'
```

The `application.yml` configuration exposes the pull endpoint and sets the push destination. Both cadences are set to 15 seconds in the example for easy observation. They are managed by two separate processes and are not necessarily synchronized.

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  otlp:
    metrics:
      export:
        url: http://127.0.0.1:4318/v1/metrics
        step: 15s
        resource-attributes:
          "[service.name]": checkout
```

The `prometheus.yml` configuration specifies where Prometheus pulls data from.

```yaml
scrape_configs:
  - job_name: checkout
    metrics_path: /actuator/prometheus
    scrape_interval: 15s
    static_configs:
      - targets: ["127.0.0.1:8080"]
```

The `otelcol.yaml` configuration tells the Collector to accept OTLP/HTTP and log metric details for easy inspection. The `debug` exporter in the example is for observing incoming data, whereas a production pipeline needs an exporter to a suitable storage backend.

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

Start the Collector with `otelcol --config=otelcol.yaml` and Prometheus with `prometheus --config.file=prometheus.yml` in two terminal windows, then start the application. The Collector command name may vary by distribution, such as `otelcol-contrib`. If you move the processes into separate containers, use addresses that the connecting process can resolve and reach. `127.0.0.1` inside each container refers to that container itself.

**Verify the pull path.** Read the application endpoint, then check whether Prometheus fetched the data on schedule.

```bash
curl -fsS 'http://127.0.0.1:8080/actuator/prometheus'
curl -fsS -G 'http://127.0.0.1:9090/api/v1/query' \
  --data-urlencode 'query=up{job="checkout"}'
```

Once the application is up and Prometheus scrapes successfully, the expected result is `up{job="checkout",instance="127.0.0.1:8080"} = 1`. You can look for the `jvm_memory_used_bytes` family in the scrape output. Memory values depend on the process.

**Verify the push path.** Wait for the Collector to receive data after one or a few 15-second export intervals. In the `debug` logs, look for the resource attribute `service.name=checkout` and the JVM metric data points. If no data appears, check the application logs, the OTLP/HTTP port, the `/v1/metrics` path, and whether the receiver is wired into `service.pipelines.metrics`. Calling `GET` on `/v1/metrics` does not test OTLP push, because the receiver expects a `POST` with an OTLP payload.

In the test environment, stop Prometheus temporarily while keeping the application and Collector running. The Collector can still receive and log new export intervals. Restart Prometheus, then stop the Collector temporarily. After a successful scrape, Prometheus still reports `up=1` even though the OTLP exporter may log connection errors. These two experiments clarify which party each flow depends on.

### Choosing a Mechanism by Environment and Process Lifecycle

For long-running services with scrape addresses reachable by Prometheus and needing per-instance monitoring, pull lets you manage scrape schedules centrally and use `up` to check targets. If services only allow outbound connections and an OTLP-capable Collector is already in place, push fits that network direction. With either approach, define which sources are expected and the maximum acceptable staleness window before data is considered outdated.

If a scrape is missed, the sample at that point in time is missing. The next scrape may see an increased counter value if the process has not reset the counter. If an OTLP send fails, retry capability depends on the exporter, buffering, and configuration. When a source runs shorter than a scrape or export cycle, verify whether it has a chance to be scraped or flushed successfully before exiting. Enabling a periodic exporter alone does not guarantee that data reaches the destination.

Two common multi-hop examples:

- **Pushgateway.** A job pushes measurements to Pushgateway. Prometheus then scrapes from Pushgateway. This is commonly used to record service-level outcomes of short-lived batch jobs. Measurements in the gateway can persist after the job finishes, so stale metric groups should be deleted according to the job lifecycle. `up` on the scrape hop reflects reachability of the gateway. In Spring Boot 3.3, Pushgateway auto-configuration is tied to the legacy `micrometer-registry-prometheus-simpleclient` registry, whereas the example above uses `micrometer-registry-prometheus`.
- **Prometheus remote write.** Prometheus can scrape samples from an application and then push the collected samples to remote storage. `remote_write` belongs to the outbound hop from Prometheus. The hop from the application into Prometheus still uses a pull schedule when configured as a scrape job.

If you enable multiple registries simultaneously for the same source, verify where each flow goes. When two flows land in the same storage backend, determine how to distinguish or deduplicate them before summing their values.

### References

- [Spring Boot 3.3 Actuator — Exporting Metrics with OTLP and Prometheus](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Micrometer 1.13 — OTLP Endpoint, Step, and Configuration](https://docs.micrometer.io/micrometer/reference/1.13/implementations/otlp)
- [OpenTelemetry — Collector Receiver, Exporter, and Pipeline Configuration](https://opentelemetry.io/docs/collector/configuration/)
- [Prometheus — When to Use Pushgateway](https://prometheus.io/docs/practices/pushing/)
- [Prometheus — Remote Write Protocol](https://prometheus.io/docs/specs/prw/remote_write_spec/)