# Canarying New Thresholds on a Subset of Replicas

When changing circuit breaker thresholds in a Spring Cloud system, do not apply the new configuration to all replicas at once before knowing how it behaves under real load. You can roll out the configuration to a separate group of replicas, route a controlled portion of traffic to that group, and compare its behavior against the group running the stable configuration.

This approach is commonly called a canary rollout. With Resilience4j, each process normally maintains its own local circuit breaker instances and sliding windows. Therefore, a canary replica group can run the new thresholds while the stable group continues using the old thresholds. Operations teams observe error rates, slow calls, circuit-open counts, fallbacks, and latency before deciding whether to expand the rollout or roll back.

## Why Canary Circuit Breaker Thresholds?

Thresholds such as `failureRateThreshold`, `slowCallDurationThreshold`, `slowCallRateThreshold`, and `minimumNumberOfCalls` directly govern when a circuit breaker transitions from CLOSED to OPEN. Threshold changes can improve protection, yet they can also cause the circuit to open too early or too late.

For example, lowering `slowCallDurationThreshold` from 2 seconds to 800 ms classifies more calls as slow. If the service normally responds in around 900 ms during peak hours, the new configuration may push up the slow-call rate and open the circuit frequently. Conversely, raising `failureRateThreshold` too high can cause the application to keep sending many calls to a failing dependency.

Canary testing helps answer these questions:

- Does the new configuration detect degradation earlier?
- Does the circuit open too often under normal load conditions?
- Do fallback and fail-fast rejection rates rise unexpectedly?
- Do users experience more errors or degraded data?
- Does the new configuration behave stably as traffic increases and as the dependency recovers?

Threshold changes must be evaluated alongside business behavior. A circuit breaker that opens more often may relieve pressure on a dependency, yet it may also send more requests to fallbacks. The goal is to find the right balance between system protection and service availability.

## Separating Canary and Stable Groups

To make comparisons meaningful, clearly distinguish replicas running the old configuration from replicas running the new configuration. You can deploy two Deployment groups:

- **Stable:** continues running the verified version and configuration.
- **Canary:** runs the same application or a compatible version, but loads the new circuit breaker threshold set.

Each group should have a clear label or identifying attribute, such as `track=stable` and `track=canary`. The circuit breaker name can be identical across both groups, such as `inventory-read`, because each process has its own registry and state. However, metrics must carry a deployment or release-track label to distinguish stable figures from canary figures.

~~~mermaid
flowchart TD
    A[Gateway or traffic router] -->|Majority of traffic| B[Stable group]
    A -->|Small percentage| C[Canary group]
    B --> D[Old circuit breaker configuration]
    C --> E[New circuit breaker configuration]
    D --> F[Stable metrics and logs]
    E --> G[Canary metrics and logs]
    F --> H[Compare over the same time window]
    G --> H
    H --> I{Meets release criteria?}
    I -->|Yes| J[Gradually increase canary percentage]
    I -->|No| K[Roll back canary group]
~~~

Do not merely edit a ConfigMap shared by both stable and canary, because both groups may pick up the new configuration simultaneously and eliminate your comparison baseline. Provide separate configurations per Deployment, profile, or distinctively labeled configuration source.

## Managing Configuration by Profile

Spring Boot can load profile-specific configuration. For instance, the stable group's default configuration remains in `application.yml`, while the canary group additionally loads `application-canary.yml`.

Illustrative stable configuration:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 40
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 5
~~~

Illustrative canary configuration changing the slow-call duration and rate thresholds:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 40
        failureRateThreshold: 50
        slowCallDurationThreshold: 1200ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 5
~~~

In this example, the canary is more sensitive to slow calls: the slow-call duration threshold drops from 2 seconds to 1.2 seconds and the allowed slow-call rate drops from 60% to 50%. These values only illustrate how to separate configuration; choose thresholds based on SLOs, baseline latency, and real traffic.

The canary profile can be enabled via an environment variable in the Deployment:

~~~yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    value: canary
~~~

If stable does not enable the canary profile, it continues loading the default configuration. In real environments, separate ConfigMaps per Deployment or Spring Cloud Config with separate labels/profiles can be used. What matters is verifying that each group actually loads its intended set of values.

Do not assume editing a ConfigMap file automatically updates running circuit breaker instances. An updated mounted file does not mean Spring Boot and Resilience4j have recreated or updated the instances. If your version and application's refresh mechanism does not guarantee updating circuit breaker configuration, perform a rollout so new processes load the new configuration. After the rollout, verify effective configuration via a protected endpoint or configuration logs, without exposing sensitive data.

## Keeping Comparison Conditions Fair

A canary is only valid when stable and canary groups receive equivalent workloads. If canary receives only cached read requests while stable receives write operations as well, error rates and latencies cannot be compared directly.

Before shifting traffic, verify:

- The same endpoints and business operations are sent to both groups.
- Request proportions, payload sizes, and tenant distributions are comparable.
- Both run the same application version or differ only in the configuration under test.
- Dependencies, HTTP client timeouts, retries, and bulkheads are identical, unless intentionally part of the test.
- Metric collection and observation intervals are identical.

Changing multiple policies simultaneously makes it hard to identify causes when outcomes diverge. During a circuit breaker threshold canary, change only a tightly related group of parameters and record the exact old/new values.

## Choosing Traffic Percentage and Canary Group Size

You can start with one canary replica or a small traffic share, then scale up as metrics stabilize. The specific ratio depends on traffic volume, risk level, and traffic isolation capabilities.

A circuit breaker process typically maintains its own sliding window. If a single canary replica receives only a few requests per minute, it may fail to reach `minimumNumberOfCalls` during the observation window. In that case, the circuit breaker will not have enough samples to evaluate failure rate or slow-call rate. A multi-replica aggregate dashboard showing enough samples does not mean any single replica's local sliding window has enough samples.

Roughly estimate the sample count each canary receives:

`Samples during observation window ≈ requests per second × canary traffic share × observation seconds`

For example, if a service receives 100 requests/second and canary receives 5% of traffic for 60 seconds, total requests entering the canary group are about 300. If three canary replicas share load fairly evenly, each replica receives around 100 requests in that minute. With `minimumNumberOfCalls=40`, each replica is likely to have enough samples to begin evaluation. This is only an estimate; check actual distribution and the number of calls genuinely passing through the circuit breaker.

If traffic is low, extend the observation window or use a smaller canary group to increase samples per instance. Do not lower `minimumNumberOfCalls` solely to make the canary trip faster without evaluating the impact on statistical reliability.

## Routing Traffic to the Canary

Use a routing mechanism capable of separating stable and canary groups, such as a Gateway, ingress controller, service mesh, or rollout controller supporting weighted traffic. A standard Kubernetes Service selects endpoints by selector; it does not automatically split traffic 95/5 between two Deployments simply because both share the same app label.

One implementation pattern is creating two separate Services:

- `inventory-api-stable` selects pods with `track: stable`.
- `inventory-api-canary` selects pods with `track: canary`.

Then the Gateway or service mesh routes a small percentage of requests to the canary Service. Ensure session affinity or tenant routing does not send the canary a set of requests markedly different from stable. If sticky routing is used, monitor actual traffic distribution rather than trusting configured weights alone.

Illustrative Deployment label structure:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-api-canary
spec:
  replicas: 2
  selector:
    matchLabels:
      app: inventory-api
      track: canary
  template:
    metadata:
      labels:
        app: inventory-api
        track: canary
    spec:
      containers:
        - name: inventory-api
          image: example/inventory-api:1.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: canary
~~~

This illustrates the Deployment portion; you must declare the corresponding Services and weighted routing configuration in your deployment platform. Do not place canary pods in an undifferentiated backend pool alongside stable if your goal is explicit traffic-split control.

## Monitoring Circuit Breakers Separately by Group

Attach deployment labels to metrics or logs to separate stable and canary. Key metrics include:

- Failure rate and failed call count.
- Slow-call rate and slow call count.
- p50, p95, and p99 latencies.
- CLOSED → OPEN and OPEN → HALF_OPEN transition counts.
- Calls rejected because the circuit is OPEN.
- Fallback counts and fallback outcome types.
- HTTP 5xx, timeout, and connection error rates.
- Business-level request success rate.

Illustrative metric dimensions:

| Label | Illustrative Value | Purpose |
|---|---|---|
| `deployment_track` | stable / canary | Compare release groups. |
| `service` | inventory-api | Identify the service. |
| `circuit_breaker` | inventory-read | Identify the protected flow. |
| `config_revision` | cb-threshold-2026-11 | Tie results to a configuration version. |
| `outcome` | success / failure / slow / rejected | Classify outcomes. |

Labels must have bounded value domains. Do not add SKU, user ID, order ID, or request ID to metrics. Record those identifiers in traces or logs according to the application's data policy.

Compare rates and percentiles rather than raw counts alone. If canary receives 5% of traffic, its absolute error count may be lower than stable's even when its error rate is higher. Compare across the same endpoint, the same time range, and the same request group.

## Setting Promotion and Rollback Criteria Before Starting

Before shifting traffic, record stable's baseline and define the conditions for increasing traffic or rolling back. Do not wait for an incident to decide acceptance thresholds.

Illustrative criteria:

| Metric | Illustrative Promotion Condition | Rollback Signal |
|---|---|---|
| Business error rate | No significant increase compared to stable. | Exceeds allowable margin or impacts core transactions. |
| p95/p99 latency | Within SLO and does not degrade significantly. | Sustained latency spike or rising request timeouts. |
| Fallback rate | Rises within expected bounds of the change. | Fallback spikes sharply or returns excessive degraded data. |
| Circuit breaker open rate | Matches actual error/slow-call signals. | Circuit opens repeatedly under normal load. |
| Dependency load | Stays within dependency capacity. | Load or connection pools climb to dangerous levels. |
| Sample count | Reaches `minimumNumberOfCalls` across canary replicas. | Insufficient samples to conclude; extend observation or adjust plan. |

Criteria must be quantified according to SLOs and business behavior. No single promotion percentage suits every system. If canary lacks samples or traffic is unrepresentative, treat the outcome as inconclusive rather than passing by default.

## Progressive Rollout Workflow

A controlled rollout sequence can include:

1. **Capture baseline:** save current configuration, stable metrics, and dependency health before making changes.
2. **Prepare canary:** create a separate replica group and load the profile or ConfigMap containing new thresholds.
3. **Verify configuration:** inspect instance names, threshold values, timeouts, and config revision on each canary pod.
4. **Smoke test:** send a controlled set of requests to confirm canary works and metrics carry the expected labels.
5. **Shift small traffic:** route a low percentage to canary while stable serves the remainder.
6. **Observe sufficient samples:** wait for each canary instance to accumulate minimum calls and observe under representative load.
7. **Evaluate:** compare failure rate, slow-call rate, latency, fallbacks, circuit state, and business metrics.
8. **Ramp up:** if criteria are met, step up traffic percentages, e.g., 5%, 10%, 25%, 50%, then 100%.
9. **Finalize:** once all traffic uses the new configuration stably, update stable configuration to the same verified values.
10. **Clean up canary:** remove canary configuration and resources when no longer needed, while retaining change history and metrics.

The traffic steps above are illustrative only. Smaller steps can be used for critical services or high volume. Re-observe after each increase because behavior at 5% traffic may differ when 50% of traffic uses the new configuration.

## Rolling Back When the Canary Fails

A rollback must quickly restore stable traffic paths and configuration:

- Stop routing additional traffic to the canary.
- Set canary traffic share to 0% or shift requests back to stable.
- Preserve logs, metrics, and configuration revisions for investigation.
- If necessary, scale down or remove the canary group from the Service.
- Verify stable continues receiving traffic and metrics return to baseline.
- Do not delete evidence of circuit breaker states, fallbacks, and errors that occurred.

If the change lived only in canary configuration, rolling back usually means shifting traffic to stable and stopping the canary group. If the new configuration was already applied across all replicas, redeploy the old configuration through a controlled rollout. Do not merely edit configuration files without verifying running processes reloaded the old values.

Also note that circuit breaker state is not necessarily preserved across pod restarts. New replicas may start in CLOSED state with an empty sliding window. After rollback, watch the warm-up phase carefully to avoid mistaking insufficient samples for full dependency recovery.

## Pitfalls to Avoid

| Risk | Consequence | Mitigation |
|---|---|---|
| Stable and canary share a ConfigMap that mutates both | Loses the control group and obscures which config is running. | Separate config by Deployment/profile or revision. |
| Canary receives unrepresentative traffic | Metrics cannot be compared fairly. | Keep request types consistent and inspect traffic distribution. |
| Each canary replica lacks samples | Circuit breaker cannot evaluate thresholds. | Estimate per-instance sample rate and extend observation time. |
| Comparing absolute error counts only | Higher-traffic group shows more errors despite a lower rate. | Compare rates and percentiles on identical workloads. |
| Changing multiple policies at once | Hard to attribute which change caused the outcome. | Keep changes narrowly scoped and track revisions. |
| Assuming configuration auto-refreshes | Pods still run old values despite ConfigMap edits. | Verify refresh mechanism or roll out new pods. |
| Monitoring only OPEN state | Misses rising latency and fallbacks before the circuit opens. | Monitor failure rate, slow-call rate, latency, and business outcomes. |
| Canary restarts repeatedly | Sliding window resets, sample counts fluctuate. | Monitor restarts and readiness; halt rollout on anomalies. |

## Post-Release Verification

After completing the rollout, verify:

- All replicas are running the expected configuration revision.
- Circuit breaker names match Resilience4j configuration.
- Each group has metrics distinguishing stable/canary during the comparison phase.
- Traffic no longer enters the old canary group if rolled back or once the experiment concludes.
- No unexpected spikes in fallbacks or fail-fast rejections occur after promotion.
- Replicas have enough samples and circuit breaker states are stable after warm-up.
- Dashboards, alerts, and runbooks reference the newly released revision.

Do not inspect configuration in the repository alone. Verify effective values in running processes via controlled startup logs, protected internal endpoints, or deployment metadata. When multiple configuration sources exist, know which source Spring Boot loaded the final effective value from.

## Operational Checklist

1. Save the baseline and current configuration revision.
2. Separate stable and canary groups via Deployment, profile, or independent configuration.
3. Choose a small traffic share large enough for each circuit breaker to collect required samples.
4. Keep canary workload comparable to stable.
5. Verify the new thresholds are actually loaded on every replica.
6. Monitor failure rate, slow-call rate, latency, fallbacks, open transitions, and business errors.
7. Increase traffic only after gathering enough samples and meeting predefined promotion criteria.
8. Roll back immediately if defined risk conditions are triggered.
9. After promotion, update stable with the same revision and re-verify all replicas.
10. Record experiment results so future adjustments have a reliable baseline.

Canarying new thresholds on a subset of replicas validates circuit breaker impact under real traffic within a controlled blast radius. By isolating configuration and traffic, accounting for per-replica local sliding windows, comparing by rates, and setting promotion/rollback criteria upfront, operations teams can tune protection while minimizing the risk of widespread service disruption.
