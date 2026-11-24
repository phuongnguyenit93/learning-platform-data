# Distinguishing Service Level Indicators (SLI), Service Level Objectives (SLO), and Alert Thresholds

> Scope: designing measurements and alerts when operating Spring Boot Actuator 3.3.x applications. The percentages, time windows, and event classification policies in this article are concrete examples; re-select them based on user experience and actual service data.

## 1. From a Measurement to an Operational Decision

Suppose a monitoring screen shows that 99.97% of requests over 30 days encountered no server-side errors. That number describes a measured outcome. To conclude whether the service meets requirements, you need an objective. To know whether to page the on-call engineer immediately, you also need alert conditions and corresponding actions.

Three concepts address three different questions:

| Concept | Primary question | Example |
| --- | --- | --- |
| Service Level Indicator (SLI) | What are we measuring service quality with, and what is the current result? | Proportion of eligible requests not returning HTTP 5xx |
| Service Level Objective (SLO) | What result is considered passing, over what scope and time period? | At least 99.9% of those requests pass in a 30-day rolling window |
| Alert thresholds and rules | When does the system need to ask an operator to take action? | Error rate exceeds a threshold over both long and short windows, sustained for the required duration |

An SLI is a carefully defined measurement; an SLO sets the target for that measurement. A single standalone percentage does not fully describe both. [Google SRE definitions of SLI and SLO](https://sre.google/sre-book/service-level-objectives/).

CPU exceeding 80% for 10 minutes is an operational condition that may be useful. It does not by itself become an SLO for user experience. Conversely, a service with low CPU can still return errors for every request due to misconfiguration.

## 2. Defining an SLI: Know What You Are Counting

For an event-ratio SLI:

```text
SLI(W) = count of good events in W / total count of eligible events in W
```

W is the observation window. Before writing queries, lock down:

1. **Target journey:** which user journey or operation?
2. **Eligible events:** which types of requests belong in the denominator?
3. **Good events:** what conditions must be met to enter the numerator?
4. **Measurement point:** at the browser, ingress gateway, or inside the application?
5. **Window and aggregation:** 5 minutes for investigation, or 30 days for objective evaluation?
6. **Missing-data state:** how to handle having no requests yet or losing observability?

Defining by good events / total events ties the measurement to service quality while clarifying what failed. [How to build SLIs in the SRE Workbook](https://sre.google/workbook/implementing-slos/).

### Two SLIs That Can Be Used for the Same API

The illustrative example throughout this article picks GET on route /api/orders/{id} of orders-api in production. This is a route template, not individual order IDs as labels.

| SLI | Eligible events | Good events |
| --- | --- | --- |
| Availability by HTTP status | GET requests recorded by the application for the chosen route | Response is not HTTP 5xx |
| Fast enough success | Same request set as above | Response is not HTTP 5xx and processing time is at most 300 ms |

In this illustrative policy, 4xx is not treated as a server-side availability failure. That does not mean every 4xx can be ignored: if 429 indicates the system cannot serve users, adjust the good-event definition accordingly. HTTP status codes may also not reflect business errors returned in the response body.

The health or prometheus endpoints are not part of this order-reading journey. Including them in the denominator can make the ratio look better without improving user experience.

### Limits of Measuring Inside the Application

Server-side Actuator metrics only observe what passed through their recording point. DNS failures, connection failures, or requests blocked before the application may not appear in the application's HTTP counters. Explicitly state that this is a server-side measurement and add measurement points at the gateway or external checks if the objective requires end-to-end experience.

Therefore, /actuator/health returning success does not prove users can complete a business operation.

## 3. Defining an SLO: Objective, Window, and Scope

A reference SLO can be written as follows:

```text
Service: orders-api
Environment: production
Operation: GET /api/orders/{id}
SLI: proportion of eligible requests not returning HTTP 5xx
Target: >= 99.9%
Evaluation window: 30-day rolling
Measurement point: application-side HTTP meters
```

This is a policy description, not Spring Boot configuration. Real operations also need an owner, data source, agreed exceptions, and how to act when the objective is missed. [Example SLO document](https://sre.google/workbook/slo-document/).

A 30-day rolling window and a calendar month are two different choices. With a rolling window, old data continuously ages out of the evaluation scope. Do not switch back and forth between the two calculation methods while keeping the same wording on dashboards.

For the fast-enough SLI, another SLO might be at least 99% of requests having both no server errors and processing time at most 300 ms in the same window. Then:

- **300 ms** is the boundary classifying whether each event is good.
- **99%** is the target ratio of the event set.
- **30 days** is the objective evaluation window.

The three values have different roles. Writing only 300 ms is not enough to define an SLO.

## 4. Error Budget: Turning the Objective into Allowed Failure

For a ratio-based SLO with target S less than 1:

```text
Allowed bad event ratio = 1 - S
Bad event budget = (1 - S) * total eligible events
Remaining budget = bad event budget - actual bad events
```

Example for the same 30-day window with sufficient data:

| Quantity | Value |
| --- | --- |
| Total eligible requests | 2,000,000 |
| SLO | 99.9% |
| Allowed bad requests by ratio | 2,000 |
| Observed bad requests | 600 |
| Observed SLI | 99.97% |
| Budget used | 30% |
| Remaining budget | 1,400 bad requests, or 70% |

This is an evaluation over the known total requests of the window. If traffic changes, the total denominator and event-based budget also change. Do not treat 2,000 as a fixed quota for all periods or all traffic levels.

In particular, **a request-ratio SLO does not automatically convert into minutes of allowed downtime**. Time-based conversion only fits time-based measurements or explicitly stated traffic assumptions. One peak minute can affect more requests than one low-traffic hour.

If remaining budget goes negative, preserve the over-budget information for evaluation; do not clamp negative numbers to 0 and hide the severity of the violation.

## 5. Alert Thresholds: Choosing When Action Is Needed

An alert needs to specify the expression, measurement window, threshold, duration, severity, and expected action. In Prometheus, `for` requires the condition to remain true across evaluations during that period before the alert transitions to firing. [Prometheus alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/).

Example:

```text
Measured condition: error rate over the last 5 minutes
Threshold: > 1%
Sustained duration: 2 minutes
Expected action: ask the on-call engineer to investigate
```

This is an illustrative alert rule, not a 99% SLO. The 5-minute window is for computing the ratio; the 2-minute sustained duration is for deciding the alert state. The two durations do not replace each other.

Two scenarios show why they must not be confused:

| Scenario | Full-window SLO | Current alert |
| --- | --- | --- |
| Early period served well, errors currently spiking fast | May still be passing | May need an early alert to protect budget |
| Just recovered from a major incident | May still be failing | Alert for ongoing errors may have already resolved |

Waiting until the entire 30-day SLO has already failed before paging can be too late. Yet paging just because a single sample slightly exceeded a number can create noise.

### Error Budget Burn Rate

Burn rate compares the recent bad-event ratio with the allowed ratio:

```text
Burn rate(W) = bad event ratio in W / (1 - SLO)
```

With a 99.9% SLO, the allowed bad ratio is 0.1% = 0.001. If the recent bad ratio is 1% = 0.01, the burn rate equals 10. If it is 2%, the burn rate equals 20.

Burn rate describes the current rate as a multiplier; it is not the percentage of budget already used. A burn rate of 10 does not mean 10% of the budget has been spent.

Under an assumption of relatively steady traffic, the fraction of budget consumed over interval w of period T can be estimated as burn rate times w/T. For example, T = 30 days = 720 hours, a burn rate of 14.4 over 1 hour corresponds to roughly 2% of the budget under that assumption. When traffic fluctuates strongly, check actual event counts; do not treat this time-based estimate as an identity for all data.

One way to choose conditions is to combine a long window to assess impact and a short window to verify errors are still occurring. Levels such as 14.4 at 1 hour / 5 minutes are reference points requiring calibration, not Spring Boot constants. [Alerting on error budgets](https://sre.google/workbook/alerting-on-slos/).

## 6. Actuator Supplies Data; Bucket Configuration Does Not Create Objectives

In a typical Spring MVC application, the HTTP meter has the Micrometer name http.server.requests. When exported to Prometheus, series such as http_server_requests_seconds_count and corresponding histogram buckets can be used.

For an application that already has Actuator and the Prometheus registry, illustrative configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  metrics:
    tags:
      service: orders-api
      environment: production
    distribution:
      slo:
        http.server.requests: 300ms
```

This is configuration merged into an application, not a complete project. Required dependencies include spring-boot-starter-actuator and io.micrometer:micrometer-registry-prometheus, along with the web stack the application actually uses.

The name management.metrics.distribution.slo is easily misunderstood. It configures cumulative histograms with chosen boundaries. In the example, 300 ms is a bucket boundary; the configuration does not declare a 99% objective, 30-day window, or alert recipients. [Spring Boot 3.3 distribution.slo property](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing.per-meter-properties).

With classic Prometheus histograms for a Timer, the time unit is seconds; 300 ms corresponds to bucket le="0.3". That cumulative bucket counts occurrences with duration at most the boundary. Check actual exported data and ensure every running instance participating in the calculation has this bucket. [Histograms and SLO boundaries in Micrometer](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html).

Do not average p95 values across multiple instances to infer service-wide p95. If the objective is the proportion of requests at most 300 ms, counting the exact bucket over total events usually expresses the contract more directly than an approximate percentile. [Histograms and calculating ratios by bucket](https://prometheus.io/docs/practices/histograms/).

## 7. A Prometheus Rule Example with Numerator, Denominator, and Alert

The example continues with the HTTP availability policy: every GET request for the chosen route belongs in the denominator; only HTTP 5xx belongs in bad events. Assume data from instances is collected completely, service/environment labels exist, and retention is sufficient for evaluation purposes.

The illustrative rules file below computes ratios at 5 minutes and 1 hour, then sets a fast-burn alert. It is loaded by Prometheus, not automatically read by Spring Boot from application.yml:

```yaml
groups:
  - name: orders-slo
    interval: 30s
    rules:
      - record: orders:requests:rate5m
        expr: |
          sum by (service, environment) (
            rate(http_server_requests_seconds_count{
              service="orders-api", environment="production",
              method="GET", uri="/api/orders/{id}"
            }[5m])
          )
      - record: orders:errors:rate5m
        expr: |
          sum by (service, environment) (
            rate(http_server_requests_seconds_count{
              service="orders-api", environment="production",
              method="GET", uri="/api/orders/{id}", status=~"5.."
            }[5m])
          )
          or on (service, environment)
          (0 * orders:requests:rate5m)
      - record: orders:errors:ratio5m
        expr: orders:errors:rate5m / orders:requests:rate5m
      - record: orders:requests:rate1h
        expr: |
          sum by (service, environment) (
            rate(http_server_requests_seconds_count{
              service="orders-api", environment="production",
              method="GET", uri="/api/orders/{id}"
            }[1h])
          )
      - record: orders:errors:rate1h
        expr: |
          sum by (service, environment) (
            rate(http_server_requests_seconds_count{
              service="orders-api", environment="production",
              method="GET", uri="/api/orders/{id}", status=~"5.."
            }[1h])
          )
          or on (service, environment)
          (0 * orders:requests:rate1h)
      - record: orders:errors:ratio1h
        expr: orders:errors:rate1h / orders:requests:rate1h
      - alert: OrdersAvailabilityFastBurn
        expr: |
          (orders:errors:ratio1h > 14.4 * 0.001)
          and on (service, environment)
          (orders:errors:ratio5m > 14.4 * 0.001)
          and on (service, environment)
          (orders:requests:rate5m > 0)
        for: 2m
        labels:
          severity: page
        annotations:
          summary: 'orders-api error budget is burning fast'
          description: 'Error rate exceeded 1.44% over both 1-hour and 5-minute windows.'
```

Explanation of choices:

- Compute rate on each counter first before summing across instances, so counter resets on restarts are handled on the right series.
- Sum numerators and denominators by the same service/environment, rather than averaging instance ratios.
- When no 5xx series exists yet while a valid denominator exists, the 0 times denominator branch represents zero errors under the stated data model.
- If the denominator is 0, division yields no valid ratio; do not automatically turn that case into 100% good.
- If the denominator is also missing, the fallback branch does not fabricate a healthy service. However, partial data loss still needs separate checking.

The meaning of rate and or/on matching is defined in PromQL. The fallback branch is only valid once metric export behavior is confirmed; it does not prove every real error was observed. [rate function](https://prometheus.io/docs/prometheus/latest/querying/functions/#rate), [Set and vector matching operators](https://prometheus.io/docs/prometheus/latest/querying/operators/#logical-set-binary-operators).

The threshold 14.4 times 0.001 equals 0.0144, i.e., a 1.44% error rate. The rule requires both the 1-hour and 5-minute ratios to exceed that level. for: 2m adds wait time in this example; assess the detection delay introduced by that choice.

severity: page is a label used by the notification routing system. Setting this label alone does not automatically place a call or send a notification; corresponding alert routing configuration is required.

This is only a fast-burn rule to illustrate the boundary between measurement, objective, and alert. It does not detect every slow degradation, data loss, or failure outside the application. These 5-minute/1-hour queries are also **not a compliance calculation for the full 30-day SLO**.

### Measuring Fast Enough Success Ratio

Based on the same denominator, an illustrative 5-minute query could be:

```promql
(
  sum by (service, environment) (
    rate(http_server_requests_seconds_bucket{
      service="orders-api", environment="production",
      method="GET", uri="/api/orders/{id}",
      status!~"5..", le="0.3"
    }[5m])
  )
  or on (service, environment)
  (0 * orders:requests:rate5m)
)
/ orders:requests:rate5m
```

The numerator requires both no 5xx error and at most 300 ms. A very fast 503 response still does not count as good in this SLI. The query depends on the denominator recording rule declared above and the right bucket on every instance; inspect data before interpreting results.

If this SLI's objective is 99%, use a 1% budget for it. Do not mistakenly use the 0.1% budget of the 99.9% availability SLO.

## 8. Aggregation and Missing Data Can Lead to Wrong Conclusions

### Sum Events Before Dividing

Suppose one group has 10 requests, all 10 good: SLI is 100%. Another group has 990 requests, 891 good: SLI is 90%. A simple average of the two ratios gives 95%, whereas the whole set has 901/1,000 good requests, or 90.1%.

The same principle applies when aggregating across instances or time intervals with different traffic levels. To evaluate an event-based SLO for the entire window, you need the ratio of total good events to total eligible events. Do not replace it with an average of 5-minute SLIs unless the objective explicitly defines such time weighting.

### Distinguishing Three States

| State | What can be concluded? |
| --- | --- |
| Sufficient data, positive denominator, no bad events recorded | Good ratio can be computed for the defined scope |
| Data exists but no requests in the window | No request-based ratio to evaluate; a zero-traffic policy is needed |
| Missing data or unable to scrape | Insufficient evidence to conclude the service is passing |

A minimum traffic threshold can reduce noisy alerts yet also ignore user impact during low traffic. If used, explicitly state the trade-off and provide supplementary observation, such as external journey checks. Do not patch missing data by setting all nonexistent ratios to 0% error.

## 9. Java Program Verifying the Calculation

The SloBudgetDemo.java file below uses known hypothetical event counts to check the formulas. It does not read Actuator or run an alerting system; its output must not be used as evidence that a real application meets its SLO.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Optional;

public class SloBudgetDemo {
    static Optional<BigDecimal> goodFraction(long total, long bad) {
        if (total < 0 || bad < 0 || bad > total) {
            throw new IllegalArgumentException("Invalid event counts");
        }
        if (total == 0) {
            return Optional.empty();
        }
        return Optional.of(
            BigDecimal.valueOf(total - bad).divide(
                BigDecimal.valueOf(total), 9, RoundingMode.HALF_UP
            )
        );
    }

    public static void main(String[] args) {
        long total = 2_000_000L;
        long bad = 600L;
        BigDecimal objective = new BigDecimal("0.999");
        BigDecimal allowedFraction = BigDecimal.ONE.subtract(objective);

        BigDecimal observed = goodFraction(total, bad).orElseThrow();
        BigDecimal allowedEvents = allowedFraction.multiply(
            BigDecimal.valueOf(total)
        );
        BigDecimal remainingEvents = allowedEvents.subtract(
            BigDecimal.valueOf(bad)
        );
        BigDecimal usedPercent = BigDecimal.valueOf(bad)
            .divide(allowedEvents, 6, RoundingMode.HALF_UP)
            .multiply(new BigDecimal("100"));

        BigDecimal recentBadFraction = new BigDecimal("0.01");
        BigDecimal recentBurnRate = recentBadFraction.divide(
            allowedFraction, 2, RoundingMode.HALF_UP
        );

        System.out.println("SLI=" + observed
            .multiply(new BigDecimal("100"))
            .setScale(3, RoundingMode.HALF_UP).toPlainString() + "%");
        System.out.println("allowedBadEvents="
            + allowedEvents.stripTrailingZeros().toPlainString());
        System.out.println("remainingBadEvents="
            + remainingEvents.stripTrailingZeros().toPlainString());
        System.out.println("budgetUsed="
            + usedPercent.setScale(1, RoundingMode.HALF_UP)
                .toPlainString() + "%");
        System.out.println("sloMet=" + (observed.compareTo(objective) >= 0));
        System.out.println("recentBurnRate=" + recentBurnRate.toPlainString());
        System.out.println("zeroTraffic="
            + (goodFraction(0, 0).isEmpty() ? "NO_DATA" : "MEASURED"));
    }
}
```

Compile and run with JDK 21 or later:

```powershell
javac --release 21 -encoding UTF-8 SloBudgetDemo.java
java SloBudgetDemo
```

Stdout:

```text
SLI=99.970%
allowedBadEvents=2000
remainingBadEvents=1400
budgetUsed=30.0%
sloMet=true
recentBurnRate=10.00
zeroTraffic=NO_DATA
```

sloMet=true evaluates the full-window data having an SLI of 99.970%, higher than the 99.9% objective. recentBurnRate=10.00 evaluates a recent 1% error rate; this is a different quantity, not a contradiction with the full window still passing. A level of 10 also has not exceeded the 14.4 threshold of the illustrated fast-burn rule.

zeroTraffic=NO_DATA preserves the distinction between having no requests and achieving 100%. BigDecimal helps the example's decimal calculations avoid representation errors at values like 0.999. When building real tools, also define rounding rules, late-arriving data, and objective bounds; burn rate per the formula above requires a budget greater than 0.

## 10. Checking the Design Before Use

| Question to check | Expected evidence |
| --- | --- |
| Does the SLI accurately reflect user needs? | Definition of target journey, good/bad events, and measurement point |
| Is the SLO complete? | Target ratio, window, scope, and owner |
| Do alerts lead to concrete actions? | Clear condition, severity, and investigation direction |
| Does Actuator have the right data? | Counters, route labels, and buckets verified on each running instance |
| How is zero traffic handled? | Separate state and policy, not automatically claiming healthy |
| Is data loss detected? | Scrape checks and supplementary observation |
| Does multi-instance deployment compute accurately? | Weighted event sums, not averaging percentiles or ratios arbitrarily |

Test at least these cases: all good, all bad, sudden error spike, post-incident recovery, very low traffic, lost metrics, missing bucket on one instance, and counter restart. A valid YAML file alone does not prove alerts respond properly to those scenarios.

## 11. Self-Practice

1. An objective states 99% of requests take at most 300 ms over 30 days. Point out which part describes good events, which is the target ratio, and which is the window.
2. With 2,000,000 requests and a 99.9% SLO, change the bad request count in the program to 2,500. Explain the SLI, remaining budget, and objective-met status.
3. If an incident has ended but the 30-day SLI remains below the objective, why might the ongoing-error alert resolve while the SLO evaluation still fails?
4. Change the policy so HTTP 429 is also a bad event. Identify which numerators, descriptions, and queries need to be updated consistently.
5. Why is declaring management.metrics.distribution.slo.http.server.requests=300ms not enough to have a 99% SLO and an alert protecting it?

You have properly distinguished the three concepts when you can point out what the data is saying, what the objective requires, and which rule decides when action is needed, without using one number to stand in for all three.
