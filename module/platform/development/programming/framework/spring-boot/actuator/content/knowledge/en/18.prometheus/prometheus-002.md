# JSON from the Metrics Endpoint and Prometheus Scrape Exposition Format

In Spring Boot Actuator, `/actuator/metrics` helps operators discover meters and check current values. `/actuator/prometheus` serves a different job. The Prometheus server calls this endpoint periodically to scrape samples in a protocol it understands. Both can reflect the same Micrometer measurement, but naming, filtering, and data representation differ.

| Comparison Point | `/actuator/metrics` | `/actuator/prometheus` |
| --- | --- | --- |
| Purpose | Diagnostics on a single application instance. | Provides data for periodic scraping by a Prometheus server. |
| Typical response in Spring Boot 3.3 | JSON, typically with `Content-Type: application/vnd.spring-boot.actuator.v3+json`. | Prometheus text format `text/plain;version=0.0.4` by default. Can return OpenMetrics 1.0 when negotiated via `Accept`. |
| Names | Micrometer meter names, e.g., `jvm.memory.used`. | Time series names after the registry applies export naming conventions, e.g., `jvm_memory_used_bytes`. |
| Structure | List of names or details of a single meter name, including statistics, base unit, and remaining filterable tags. | Sample lines containing metric name, labels, and value. Multiple label sets of a metric family appear separately. |
| Time | Value at the time of the call, as currently recorded by the meter. | Each response provides samples for a single scrape. Prometheus builds history by storing samples across multiple scrapes. |

## Reading JSON to inspect the application

`GET /actuator/metrics` returns an object with a `names` array. To view details, append the Micrometer name to the path. The `tag` parameter takes a `key:value` pair. Repeat the parameter to filter by multiple tags.

```bash
curl -i 'http://localhost:8080/actuator/metrics'
curl -i --get 'http://localhost:8080/actuator/metrics/jvm.memory.used' --data-urlencode 'tag=area:nonheap' --data-urlencode 'tag=id:Metaspace'
```

Below is an illustrative JSON body when selecting the Metaspace area. Actual memory values depend on the JVM and the time of the call.

```json
{
  "name": "jvm.memory.used",
  "description": "The amount of used memory",
  "baseUnit": "bytes",
  "measurements": [
    {
      "statistic": "VALUE",
      "value": 67108864
    }
  ],
  "availableTags": []
}
```

`measurements` indicates the statistic and corresponding value. Here `VALUE` is the current value of the gauge. `baseUnit` indicates the measurement is in bytes. `availableTags` lists the remaining tags that can be used to narrow the results. The array is empty in the example because both tags of the meter have already been selected.

If filtering only by `area:nonheap`, multiple memory areas may match together. For this memory gauge, the endpoint sums the matching `VALUE` entries. When two areas have 67,108,864 and 8,388,608 bytes respectively, the JSON for the `area:nonheap` filter returns a total value of 75,497,472 bytes. Filter further by `id` to compare a single memory area with a single Prometheus time series.

## Reading the scrape response

```bash
curl -i 'http://localhost:8080/actuator/prometheus'
```

In the Prometheus 0.0.4 text format response, an illustrative excerpt for the same two memory areas looks like the following.

```text
# HELP jvm_memory_used_bytes The amount of used memory
# TYPE jvm_memory_used_bytes gauge
jvm_memory_used_bytes{area="nonheap",id="Metaspace"} 67108864
jvm_memory_used_bytes{area="nonheap",id="Compressed Class Space"} 8388608
```

`# HELP` describes the metric family and `# TYPE` specifies the type. Each data line represents a sample with a name, a label set, and a numeric value. The specification allows an optional timestamp. In this excerpt there is no timestamp attached to the sample, so the server uses the scrape timestamp to store the sample. The metric name combined with the full label set identifies a time series. When storing, Prometheus typically adds target labels such as `job` and `instance`.

The renaming rules also depend on the meter type and unit. For the `Timer` `http.server.requests`, for example, the Prometheus registry may export `http_server_requests_seconds_count` for the measurement count and `http_server_requests_seconds_sum` for the total time in seconds. `_bucket` series appear when a corresponding histogram is configured. Therefore, take the actual series names from the scrape response when writing queries.

To view the OpenMetrics variant in Spring Boot 3.3, request the corresponding content type.

```bash
curl -i -H 'Accept: application/openmetrics-text; version=1.0.0' 'http://localhost:8080/actuator/prometheus'
```

Check the response `Content-Type`. OpenMetrics 1.0 uses `application/openmetrics-text` and marks the end of the body with `# EOF`. When Prometheus scrapes automatically, the server sends `Accept` according to the configured scrape protocols. Both variants serve sample scraping and have their own formatting rules.

## Connecting Spring Boot to Prometheus

In a Spring Boot web application using auto-configuration, add `spring-boot-starter-actuator` and `io.micrometer:micrometer-registry-prometheus`. The following example exposes both endpoints to observe them in the same run.

```properties
management.endpoints.web.exposure.include=health,metrics,prometheus
```

With the application on port 8080 and Prometheus running directly on the same machine, add the job to `prometheus.yml`.

```yaml
scrape_configs:
  - job_name: spring-app
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ['localhost:8080']
```

If the Prometheus server runs in a container or on another machine, use an application address reachable by that server. If the application uses a separate management port or management path, adjust `targets` and `metrics_path` to match the actual URL.

After the job scrapes successfully, query the stored series with PromQL.

```promql
jvm_memory_used_bytes{job="spring-app", area="nonheap", id="Metaspace"}
```

Prometheus also has a query API that returns JSON, such as `/api/v1/query` on the **Prometheus server**. That JSON contains the query results of the scraped data. JSON from `/actuator/metrics` on the **Spring Boot application** contains diagnostic data at the time of the call.

## Diagnosing discrepancies between the two sides

- **`/actuator/metrics` returns HTTP 200 but the job reports a scrape error.** Check `metrics_path` and the target's `Content-Type`. Actuator JSON can be a valid application response, yet not the input format expected by the scraper.
- **`/actuator/prometheus` returns 404.** Check the registry dependency, HTTP endpoint exposure configuration, management port, and actual path. For 401 or 403, check the scrape target's permissions.
- **Same base name but mismatched values.** Compare using the same unit, the same tag/label set, and the same application instance. JSON may have aggregated multiple memory areas, whereas the PromQL query selects a single area. Two HTTP requests may also observe the JVM at different points in time.
- **The scrape response has the sample, but the query does not show it yet.** Check the scrape target status, actual series name, and labels on the server. The application response at call time and the latest sample stored by Prometheus may belong to two different points in time.

## References

- [Spring Boot 3.3 — Actuator Metrics API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html)
- [Spring Boot 3.3 — Actuator Prometheus API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/prometheus.html)
- [Spring Boot 3.3 — Micrometer and Prometheus Configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Prometheus — Exposition Formats](https://prometheus.io/docs/instrumenting/exposition_formats/)
- [Prometheus — Scrape Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#scrape_config)
- [Prometheus — HTTP Query API](https://prometheus.io/docs/prometheus/latest/querying/api/)
