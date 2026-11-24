# Scrape Intervals and Measurement Execution Time in the Application

Prometheus scrapes metrics every 15 seconds. During that interval, one HTTP request may finish in 80 ms, while another request may start before a scrape and finish after the scrape. To read charts accurately, separate the time the application measures a piece of work, the cadence at which Prometheus samples, and the duration of that sampling operation itself.

| Quantity | What it measures | What determines it |
| --- | --- | --- |
| Observation duration | Interval from the start to the end of the measured work. | Where the instrumentation code is placed. For example, `Timer.Sample` captures the start time from the registry's clock and records the duration when `stop(timer)` is called. |
| Scrape interval (`scrape_interval`) | Scheduled interval between Prometheus scrapes of a target. | Prometheus server configuration, globally by default or per job. |
| Scrape duration (`scrape_duration_seconds`) | How long scraping the target took. | Measured by Prometheus itself. `scrape_timeout` sets the wait limit for this operation. |
| Query range window, e.g. `[1m]` | Stored data range used by a PromQL function at each evaluation timestamp. | The query expression. |

With Spring MVC auto-configured by Spring Boot, server-side HTTP measurements typically carry the Micrometer name `http.server.requests`. The application's `Timer` updates its count and total duration when an observation completes. When Prometheus calls `/actuator/prometheus`, it reads the statistics currently exported by the registry. Increasing the scrape frequency helps the monitoring system see updates sooner when scrapes succeed. The duration of each observation is still determined by the measured unit of work.

## Tracing a request across a scrape boundary

Assume the same instance and the same label set, with the counter intact and no restarts. Prometheus samples at seconds 0, 15, and 30. The application records the following three requests.

| Request | Start | End | Recorded duration |
| --- | ---: | ---: | ---: |
| A | 2.00 s | 2.12 s | 120 ms |
| B | 6.00 s | 6.08 s | 80 ms |
| C | 14.00 s | 17.00 s | 3 s |

| Scrape time | Cumulative count | Cumulative total duration | What Prometheus reads |
| --- | ---: | ---: | --- |
| 0 s | 0 | 0.000 s | No observations yet. |
| 15 s | 2 | 0.200 s | A and B have been added. C is still running, so it has not contributed to the `Timer` statistics for completed work. |
| 30 s | 3 | 3.200 s | One more 3-second observation, recorded when C completed at second 17. |

Between the reads at second 0 and second 15, the total duration increased by 0.200 seconds across two observations. The average latency of those two requests is 0.100 seconds. The 15-second mark is the sampling time. From the two cumulative values, Prometheus knows how much the count and total duration increased, but cannot deduce individually whether each request took 120 ms or 80 ms. Histograms, if enabled, provide observation counts within value ranges, while individual request timestamps require detailed data sources such as per-request traces.

### When a fluctuation happens between two scrapes

- **Cumulative counters and total durations** retain increases from recorded requests. Both A and B still appear in aggregate metrics even though each started and ended between two scrapes. If the process restarts between two scrapes, updates not yet scraped can be lost.
- **Gauges reading current state** report the value at the time of sampling. If a queue spikes to 100 items at second 7 and returns to 0 at second 9, scrapes at second 0 and 15 may both observe 0.
- **In-flight work** needs an appropriate measurement if you want to observe it before completion. Micrometer provides `LongTaskTimer` for the number of active tasks and how long they have been running. It answers a different question from `Timer`, which counts completed work.

## Verifying with Micrometer and a mock clock

The following program simulates the three read timestamps in the table using `SimpleMeterRegistry` in its default cumulative mode. The mock clock advances immediately on command, so the example runs quickly while still measuring duration accurately against the registry's clock. The `sampleAt` function reads in-memory statistics to simulate a scrape.

Save the file as `ScrapeVsTimer.java`. The example uses Java 17+ and `io.micrometer:micrometer-core:1.13.0` with its runtime dependencies.

```java
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public class ScrapeVsTimer {
    public static void main(String[] args) {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry = new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            Timer timer = registry.timer("demo.requests");
            sampleAt(0, timer);

            clock.add(Duration.ofSeconds(2));
            recordRequest(registry, timer, clock, 120);
            clock.add(Duration.ofMillis(3_880));
            recordRequest(registry, timer, clock, 80);

            clock.add(Duration.ofMillis(7_920));
            Timer.Sample inFlight = Timer.start(registry); // t = 14 s
            clock.add(Duration.ofSeconds(1));
            sampleAt(15, timer);

            clock.add(Duration.ofSeconds(2));
            inFlight.stop(timer); // t = 17 s
            clock.add(Duration.ofSeconds(13));
            sampleAt(30, timer);
        } finally {
            registry.close();
        }
    }

    private static void recordRequest(
            SimpleMeterRegistry registry, Timer timer, MockClock clock, long durationMillis) {
        Timer.Sample sample = Timer.start(registry);
        clock.add(Duration.ofMillis(durationMillis));
        sample.stop(timer);
    }

    private static void sampleAt(int seconds, Timer timer) {
        System.out.printf(Locale.ROOT, "t=%ds count=%d total=%.3fs%n",
                seconds, timer.count(), timer.totalTime(TimeUnit.SECONDS));
    }
}
```

On Bash, set `MICROMETER_CP` to the classpath containing the runtime JARs resolved by Maven or Gradle for the dependency above.

```bash
javac --release 17 -cp "$MICROMETER_CP" ScrapeVsTimer.java
java -cp ".:$MICROMETER_CP" ScrapeVsTimer
```

Output with Micrometer 1.13.0.

```text
t=0s count=0 total=0.000s
t=15s count=2 total=0.200s
t=30s count=3 total=3.200s
```

## Scheduling scrapes and reading results in Prometheus

Suppose the application already exposes `/actuator/prometheus` on port 8080 and Prometheus runs directly on the same host. In `prometheus.yml`, a job can be configured as follows.

```yaml
scrape_configs:
  - job_name: spring-app
    scrape_interval: 15s
    scrape_timeout: 5s
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ['localhost:8080']
```

Here Prometheus schedules scrapes every 15 seconds and caps each scrape wait at 5 seconds. This limit applies to the metrics scrape operation. A business request can still run longer than 5 seconds and be recorded upon completion. When distinguishing slow application processing from a slow scrape target response, inspect application HTTP latency alongside `up{job="spring-app"}` and `scrape_duration_seconds{job="spring-app"}`.

With the typical series names exported by Micrometer Prometheus for `http.server.requests`, the following query estimates the average duration in seconds across the entire job over a one-minute window.

```promql
sum(rate(http_server_requests_seconds_sum{job="spring-app"}[1m]))
/
sum(rate(http_server_requests_seconds_count{job="spring-app"}[1m]))
```

The numerator estimates cumulative processing seconds added per second. The denominator estimates completed requests per second. Compute `rate()` on each series before aggregating to handle counter resets when an instance restarts. When there are no observations in the window, the denominator is 0 if the series still has data, and division does not produce a meaningful average latency. When scrape samples are missing, the query may yield no result. Choose a window large enough to contain multiple successful scrapes for the actual scrape interval.

## References

- [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Micrometer 1.13 — Timers](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html)
- [Micrometer 1.13 — Gauges](https://docs.micrometer.io/micrometer/reference/1.13/concepts/gauges.html)
- [Micrometer 1.13 — Long Task Timers](https://docs.micrometer.io/micrometer/reference/1.13/concepts/long-task-timers.html)
- [Prometheus — Scrape Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#scrape_config)
- [Prometheus — Jobs, instances, and scrape metrics](https://prometheus.io/docs/concepts/jobs_instances/)
- [Prometheus — rate function](https://prometheus.io/docs/prometheus/latest/querying/functions/#rate)
