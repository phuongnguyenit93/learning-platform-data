## Connecting Grafana Dashboards and Verifying Data Before Creating Alerts

An empty panel can happen because Prometheus fails to scrape data, the application has not emitted the meter yet, a filter selects the wrong label, or the rate window has too few samples. Before using a panel as the basis for an alert, identify which layer provides the value, verify the value when the service runs normally, and observe the value changing during a controlled test failure.

### 1. Verify the data path

The Spring Boot application exposes data via Actuator. Prometheus periodically reads the endpoint, stores time series, and evaluates PromQL. Grafana sends queries to Prometheus to render dashboards and, for Grafana-managed rules, evaluates alert conditions.

In a Spring Boot 3.3 web application with `spring-boot-starter-actuator` and `io.micrometer:micrometer-registry-prometheus`, you can expose the endpoints using the `application.yml` below. The example uses the default Actuator path.

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

The example `prometheus.yml` for a test environment has a service named `checkout`, port `8080`, on the same network as Prometheus. `targets` contains an address reachable by **Prometheus**.

```yaml
scrape_configs:
  - job_name: checkout
    metrics_path: /actuator/prometheus
    scrape_interval: 15s
    static_configs:
      - targets: ["checkout:8080"]
```

Check in the following order.

1. **Actuator.** From the Prometheus network, read `http://checkout:8080/actuator/prometheus`. After sending requests to the application, look for the `http_server_requests_seconds_count` line or the actual name exported by the application. Read `status` and `uri` right on that line. If the metric is not present yet, confirm the application has handled requests and the Prometheus registry is active.
2. **Prometheus.** On the Prometheus **Targets** page or via `/api/v1/targets`, verify the scrape URL, last scrape time, and last error. Run `up{job="checkout"}`. `1` means the latest scrape succeeded, `0` means it failed. No `up` series may be due to a wrong `job`, a target not yet discovered, or a target that disappeared. Compare the number of returned targets against the expected list of instances. One succeeding target does not confirm all instances have data.
3. **Grafana.** Go to **Connections → Add new connection**, select **Prometheus**, then **Add new data source**. Set a name such as `Prometheus checkout` and enter the URL of the **Prometheus server**, such as `http://prometheus:9090` if both services are on the same Docker Compose network. Inside the Grafana container, `localhost` points to that container itself. Set the data source's **Scrape interval** to match `15s` in the example, then click **Save & test**. Next go to **Explore**, select that data source, and run `up{job="checkout"}` again. A successful connection confirms Grafana can reach Prometheus. Querying `up` shows the scrape status of the specific targets.

If you need to cross-check directly against the API, run the following command from a place that can reach the Prometheus port published on the local machine. `status="success"` confirms the query was processed. Also read `data.result` to see which series were returned and inspect each series' `instance` label.

```bash
curl -fsS -G 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=up{job="checkout"}'
```

### 2. Build panels and verify raw numbers

In Explore, start with `http_server_requests_seconds_count{job="checkout"}` to inspect the labels and cumulative values of each series. For a stably existing series, `count_over_time(http_server_requests_seconds_count{job="checkout"}[5m])` shows the actual number of samples in the window. With a 15-second scrape interval, a consistently scraped series has around 20 samples in 5 minutes. `rate` requires at least two samples per series. A low sample count on a newly appearing `5xx` series can temporarily prevent calculating the error rate.

Create a dashboard with three panels using the same data source. The **Scrape by instance** panel uses `up{job="checkout"}`, displayed by `instance` to spot missing or failing targets. The two business panels can use **Time series** and **Range** query type. When matching against an alert, keep the `[5m]` window fixed so both places compute the same metric.

**Requests per second**

```promql
sum by (job) (
  rate(http_server_requests_seconds_count{job="checkout"}[5m])
)
```

**Percentage of requests returning HTTP 5xx**

```promql
100 *
sum by (job) (
  rate(http_server_requests_seconds_count{job="checkout",status=~"5[0-9][0-9]"}[5m])
)
/
(
  sum by (job) (
    rate(http_server_requests_seconds_count{job="checkout"}[5m])
  ) > 0
)
```

Set the first panel's unit to requests/second. The second panel receives values on a **0–100** scale because PromQL already multiplies by 100. The `> 0` filter drops a zero denominator and keeps positive rates intact. If there is no 5xx series yet or that series has too few samples to compute `rate`, the percentage query may return empty even when requests exist. Inspect the numerator and denominator separately before deciding which cases should be represented as 0%.

If you change the scope to a route or method, use the same filters in both numerator and denominator. To compare a panel against Explore or the Prometheus UI, choose the same data source, the same evaluation time, the same query with variables substituted, and the same time step when comparing the full curve. Open **Inspect → Query** to check the actual request and **Inspect → Data** to read values. Check transformations and display options if numbers on the graph differ from the raw query results. For exploratory panels that need to adjust automatically when zooming, you can use `$__rate_interval` in Grafana. This interval depends on the panel's resolution and the scrape interval configured in the data source or the query's `Min step`. View the substituted value in Query Inspector when cross-checking. When moving to an alert query, use a fixed window such as `[5m]`.

### 3. Test data states

In a test environment, generate steady traffic and observe enough scrapes. Then generate a controlled burst of traffic with 5xx responses, verify the HTTP codes on the caller side, and wait for Prometheus to scrape at least two samples for the error series. Correlate the load generation time with the dashboard. When you need to measure the normal state after the fault test, maintain successful traffic long enough for the error period to age out of the `[5m]` window.

The following table uses illustrative numbers to verify units and how to read the queries. Actual measured rates can vary slightly depending on scrape timing and `rate` extrapolation.

| Test state | Result to verify |
| --- | --- |
| Traffic present, error series has enough samples, and error counter is flat | Total rate is positive, error rate is 0, and percentage is 0%. |
| Test errors present | If total is 12 requests/second and errors are 0.6 requests/second, the panel displays 5%. Check the `status` label and `job` scope if the result differs from expectations. |
| Stop sending requests and wait out the window | If counters are still exported, total rate returns to 0. The ratio query above returns empty because the denominator is 0. |
| One instance stops being scraped | The target's `up` may drop to 0 or the series may disappear if the target is removed. The two business panels may still show numbers from the remaining instances. Separately verify the number of instances with data. |
| Grafana query fails | Check the error message, access permissions, URL, and status of Prometheus. A query error differs from a query that succeeds but returns no data. |

For the 0% case, you need enough measurements to confirm no errors occurred, or a conditional 0-filling convention based on traffic and data completeness. Turning every panel gap into 0 masks the distinction between scrape failures, missing samples, and zero traffic.

### 4. Preview alert conditions

Move a verified query into an alert rule only when you clearly know its value, unit, label scope, and behavior on missing data. For Grafana-managed alerts, select the same data source and test an **Instant** query so each label set returns a single value at evaluation time. If using **Range**, choose an appropriate **Reduce** expression before comparing against a threshold, such as **Last** to get the final value of each series. **Last** and **Mean** answer two different questions. Keep deterministic filters like `job="checkout"` and use `[5m]` instead of dashboard-dependent variables like `$job` or `$__rate_interval`.

In the rule editor, use **Preview** to inspect the series and values entering the condition. With a test threshold greater than 4 on a 0–100 scale, a value of 5 must exceed the threshold and 0 must stay below it. Choose operational thresholds based on traffic, normal error rate, and service requirements. If you need to ignore fluctuations when there are only a few requests, define a minimum traffic threshold over the same window. Preview is also the time to verify that remaining labels are sufficient to identify the failing service or route.

The PromQL window determines which data is used at each evaluation. **Evaluation interval** determines how often Grafana checks. **Pending period** determines how long the condition must hold before firing an alert. Preview shows the condition result on a trial evaluation. For Grafana-managed rules, decide separately how to handle **No Data** and **Error**. If one series disappears while other series still have data, the rule can still return a result. Use scrape signals like `up` and expected instance count to detect partial data loss.

### References

- [Spring Boot 3.3 Actuator — collecting metrics with Prometheus](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Prometheus — Query API and checking targets](https://prometheus.io/docs/prometheus/latest/querying/api/)
- [Grafana — connecting a Prometheus data source](https://grafana.com/docs/grafana/latest/datasources/prometheus/configure/)
- [Grafana — inspecting panel queries and data](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/panel-inspector/)
- [Grafana — alert queries and conditions](https://grafana.com/docs/grafana/latest/alerting/fundamentals/alert-rules/queries-conditions/)