# Canary Release with Partial Traffic Before Wide Rollout

A Java application may compile successfully on a new JDK, pass unit and integration tests, and even run well in staging, yet still fail when encountering real production data, traffic cadence, lifetimes, and request diversity. One way to reduce risk is a **canary release to a controlled portion of traffic**, observing the results, and expanding the scope only when there is sufficient evidence.

In **Java Advance Compatibility Migration**, canary releases are especially useful because JDK upgrade failures can manifest in many forms:

- A rarely used endpoint loads a library that is no longer compatible with the class-file version or API.
- A framework uses reflection into JDK internals and only fails in a specific workflow.
- The new JDK changes defaults for charset, TLS, locale, or timezone, causing payloads to differ from before.
- A Java agent, JNI library, or bytecode instrumentation throws errors on the new runtime.
- The JIT needs warm-up time, causing new pods to have high latency when they first start receiving traffic.
- GC, heap, CPU quota, or container image configuration alters p99 latency and operational cost.
- The application keeps running but writes data in a format the old version cannot read, making rollback dangerous.

Canary does not replace pre-release testing. It is a **verification gate after a release already qualifies for production**, with a bounded blast radius and the ability to stop or revert to the stable version.

This lesson guides designing a canary for JDK migration, from baselines, cohort/traffic selection, data compatibility, routing configuration, metrics, and guardrails to result analysis, rollout, rollback, and operational handover. The YAML examples, commands, and metrics are illustrative samples to adapt to your real system; do not apply them directly to production.

## 1. What Is a Canary Release?

### 1.1. Concept

A **canary release** is a method of deploying a new application version to a small subset of the real environment or users before shifting all traffic. During the trial period, the stable version and the new version coexist.

General example:

```text
                      Production traffic
                              |
                              v
                       Ingress / Gateway
                              |
                  +-----------+------------+
                  |                        |
               Stable                   Canary
            Current JDK               Target JDK
            App release A             App release A/B
                  |                        |
                  +-----------+------------+
                              |
                    Shared dependencies
                     DB / queue / cache
```

The goal is not merely "having a pod running the new JDK", but **having a set of requests actually processed by the new version, with the ability to measure and reverse the traffic**.

### 1.2. "A Portion of Traffic" Must Be Clearly Defined

There are at least three very different interpretations:

1. **Percentage of requests:** the gateway routes a percentage of requests to the canary.
2. **Percentage of users/tenants/sessions:** a fixed cohort is assigned to the canary.
3. **Percentage of instances/pods:** a number of replicas run the new version.

They are **not equivalent**.

If there is 1 new pod out of 10 pods, you cannot assume the canary receives exactly 10% of requests. Load balancers, connection reuse, sticky sessions, pod readiness, and autoscaling can all skew the distribution. You must measure the actual request share by version.

### 1.3. The Question a Canary Must Answer

For a Java migration, the goal could be:

> "Does the application running on JDK 21 maintain business contracts, error/latency SLOs, and resource costs under production traffic compared to the JDK 17 version?"

The answer must be tied to:

- Specific artifact and runtime versions.
- Scope of traffic/cohort tested.
- Observation duration.
- Which code paths were exercised.
- Predefined pass/fail criteria.
- Uncovered risks.

A passing canary is not proof that every workflow or every future point in time is safe.

## 2. Distinguishing Canary, Rolling, Blue-Green, Feature Flags, and Shadow Traffic

| Technique | How It Works | Strengths | Limitations |
|---|---|---|---|
| **Canary** | Distributes a portion of traffic to the new version | Observes production behavior with a small blast radius | Requires good routing, telemetry, and rollback |
| **Rolling update** | Replaces old instances with new instances gradually | Easy to use with an orchestrator | Number of new pods does not necessarily yield a controllable traffic share |
| **Blue-green** | Two complete environments; switches traffic from blue to green | Fast traffic cutover/rollback if state is compatible | Often requires double resources and a large cutover operation |
| **Feature flag** | Enables/disables a feature for a cohort | Decouples business features from deployment | Cannot swap the JVM of a running process |
| **Shadow/mirroring** | Duplicates a portion of requests to the new version without using shadow responses | Can observe before serving users | Side effects, personal data, and I/O are very dangerous without isolation |
| **A/B experiment** | Splits groups to measure product effectiveness | Compares business outcomes | Does not replace compatibility/safety gates |

A release can combine techniques. For example:

- 5% session canary to evaluate the new JDK.
- Feature flags keeping new business features off to isolate the runtime change.
- Rolling update inside the canary pod group.
- Blue-green for large infrastructure transitions.

Do not call a default rolling update an "analyzed canary" if it lacks traffic controls, observability, and decision gates.

## 3. Why Is Canary Especially Important When Upgrading the JDK?

### 3.1. Correctness and Passing Startup Are Not Enough

A binary can load classes and report healthy, yet only fail when:

- Establishing a TLS connection to a partner using an older algorithm/certificate.
- Serializing XML with a dynamically loaded JAXB or JAX-WS provider.
- Invoking a rarely used JDBC driver or native compression library.
- Processing customer files with a non-UTF-8 charset.
- A plugin has a higher class major version than the JVM runtime.
- A Java agent instruments a class only loaded during a specific transaction.

A canary helps catch errors dependent on real traffic that staging did not sufficiently simulate, but you must **intentionally select the activation scope**. If 1% of requests mostly hit the health endpoint, the result has little value.

### 3.2. Performance Depends on Runtime and Traffic Mix

A JDK upgrade can affect:

- HotSpot JIT, tiered compilation, deoptimization, and code cache.
- GC implementation/defaults and heap ergonomics.
- Thread scheduling, CPU quota, and container awareness.
- Reflection/proxy/code generation.
- Memory allocation and native memory.
- HTTP/TLS/charset/timezone behavior.
- Java agents, profilers, and monitoring instrumentation.

At 1% traffic, the canary may **not receive enough load to warm up the same hot paths** as stable, so latency may appear higher without representing the steady-state of the new version at 100%. Conversely, an under-loaded canary may fail to expose contention or memory leaks that appear under higher traffic.

### 3.3. Canary Is a Blast Radius Management Tool

When a bug occurs only in the new version, disabling routing to the canary reduces the number of requests that continue to be affected. However, not all side effects can be rolled back immediately:

- Committed database writes.
- Published queue messages.
- Sent emails/payments.
- Caches written in a new schema.
- Long-lived sessions and WebSocket connections.
- Scheduled jobs executed on the canary.
- Irreversible data migrations.

Therefore, **traffic rollback is one part of rollback, not the entire rollback**.

## 4. Prerequisites Before Running a Canary

You should not push a build that has not passed basic testing into production just to "let the canary catch bugs".

### 4.1. Mandatory Preflight

Before routing a single real request:

1. Build artifact has clear provenance, checksum/image digest.
2. Verify JDK vendor, major/update/build, and actual runtime process.
3. Check compatibility matrix for frameworks, dependencies, application servers, agents, and JNI.
4. Compile/run unit, integration, contract, and migration tests on the target JDK.
5. Smoke test the final artifact, not just source-set classes.
6. Check startup flags, JPMS, reflective access, and class loading.
7. Check TLS/certificates, data encoding, file I/O, and serialization.
8. Check readiness/liveness/startup probes.
9. Have observability separating stable/canary.
10. Have an owner, on-call support, and an executable stop/rollback procedure.
11. Have an agreed baseline and decision thresholds.
12. Verify database/shared-state compatibility when both versions coexist.

### 4.2. Isolate Changes to Infer Root Cause

A useful approach:

```text
Stable:
  App binary: A
  JDK: 17
  Framework: F
  Config: C

Canary runtime-first:
  App binary: A
  JDK: 21
  Framework: F
  Config: C
```

Keep all other variables identical where feasible. If the base image changes or the Java 21 runtime forces a framework upgrade, record this as a **JDK + environment/framework migration**.

If the canary simultaneously uses app release B, new dependencies, and new feature flags, when p99 increases it will be hard to distinguish the cause. That does not make the experiment worthless, but you cannot conclude solely that "JDK 21 caused the slowdown" from such a test.

### 4.3. When a Safe Canary Cannot Be Performed

Some migrations must first be handled via staging/isolated deployment or architectural expansion:

- Database schema migration incompatible with the old version.
- Shared cache/session format that is not backward/forward compatible.
- No way to route traffic or isolate side effects.
- Batch/queue tasks with only one active leader and no ownership handover mechanism.
- Native library or server upgrade with cluster-wide impact that cannot run side by side.
- Product lacks sufficient metrics/rollback to detect and limit errors.
- Legal policy does not allow using a customer group for uncontrolled trials.

Canary is a method, not an excuse to bypass data or operational safeguards.

## 5. Capturing the Stable Version Baseline

### 5.1. The Baseline Has Two Parts

**Artifact/environment baseline:**

- Git revision and application release.
- JAR/WAR/EAR checksum or container image digest.
- JDK vendor/version/build.
- Framework/server versions.
- Runtime dependency graph and agent/native library versions.
- JVM flags, GC, heap, env, and system properties.
- OS, architecture, CPU/memory limits, container runtime.
- External service versions and database schema.

**Operational baseline:**

- Traffic volume by route, tenant, and request type.
- Error rate, timeout, and retry counts.
- p50/p95/p99 latency, queueing, and throughput.
- CPU per request, throttling, allocation, GC, RSS.
- Startup/readiness, warm-up, and autoscaling.
- Business success metrics and data correctness indicators.
- Pre-existing errors prior to the migration.

A green canary chart is not enough if the actual baseline also had errors, traffic composition differed, or metrics were mislabeled.

### 5.2. Measure Concurrently When Possible

Comparing canary against stable **at the same time** helps reduce the impact of traffic seasonality, backend incidents, and load changes. However, cohort differences must still be considered:

- Does the canary have more new users or more large customers?
- Does the canary have the same request sizes or endpoints as stable?
- Does the canary receive traffic from a slower network region?
- Does a zone/node hosting the canary experience more CPU throttling than stable?

A good comparison should try to balance cohorts or normalize by traffic mix, rather than looking at a single aggregate latency.

## 6. Designing Purpose-Fit Traffic Splitting

### 6.1. Weighted Request Routing

The gateway/service mesh can route by weight:

```text
Stable 95%
Canary  5%
```

This is the **desired distribution weight**, not a guarantee of exactly 5% of requests in every short interval. The actual outcome depends on the routing implementation, connection reuse, retries, readiness, and real traffic distribution.

Measure:

```text
actual_canary_share =
  requests_handled_by_canary /
  requests_handled_by_all_versions
```

With request streams, WebSockets, or long-lived connections, "% requests" and "% connections/users" can differ substantially.

### 6.2. Cohort Routing by User/Tenant

When sessions or business workflows span multiple requests, stable routing by user/tenant hash can be beneficial:

```text
hash(tenant_id) -> cohort
  cohort stable  -> old JDK
  cohort canary  -> new JDK
```

Pros:

- A single user is not switched between versions on every request.
- Easier to compare business outcomes at the cohort level.
- Can route a workflow consistently.
- Can exclude highly sensitive customer groups initially.

Cons:

- A small cohort may not be representative.
- A large tenant may account for most of the load despite few tenants.
- Fixed user assignment does not help test all countries/features.
- Sticky routing complicates rollback if the new version's session/state is incompatible.

You must clearly declare the splitting unit: request, session, user, tenant, or connection.

### 6.3. Route or Endpoint Targeting

Some teams initially enable the canary only for lower-risk routes. For example:

```text
GET /catalog/*       canary eligible
GET /orders/*        canary eligible
POST /payments       stable-only initially
POST /refunds        stable-only initially
```

This is a risk-reduction strategy, but coverage remains incomplete. You must plan to test critical paths before full rollout, in a sandbox environment or with an authorized cohort.

Do not conclude that the payment system is safe just because the canary handled a read-only endpoint well.

### 6.4. Routing by Region or Zone

Deploying a canary in a single geographic region/availability zone can reduce the blast radius, but introduces variables:

- Different regional traffic.
- Different database replicas/latencies.
- Different TLS/certificate/network policies.
- Different CPU/OS nodes or hardware generations.
- Uneven tenant and data distribution.

If the goal is to isolate JDK impact, you need a stable baseline in the **same region/zone or equivalent infrastructure**.

### 6.5. Retries Can Distort Actual Ratios

A gateway may retry a failed request against the other version. If a request fails on the canary and then succeeds on stable, the final client-side metric may mask the initial failure.

Track:

- Initial routing decision.
- Backend attempts by version.
- Retry count and reasons.
- Final response received by the client.
- Duplicate side effects.

Do not evaluate a canary solely by the overall success rate when a retry policy masks errors on the new version.

## 7. Do Not Confuse Pod Count with Traffic Percentage

### 7.1. Kubernetes Deployment Rolling Update

A Kubernetes Deployment might use:

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0
```

This configuration describes **phased pod replacement**, not creating an observable 5% canary traffic split that can be held steady over time.

If a single shared Service points to both old and new pods, traffic distribution is affected by the endpoint set, connection pooling, and routing implementation. Especially with long-lived connections, the number of handled requests can diverge sharply from the replica ratio.

### 7.2. Canary Usually Needs Two Workloads and Routing Control

An illustrative model:

```text
Deployment: order-stable   image: order:jdk17
Service:    order-stable

Deployment: order-canary   image: order:jdk21
Service:    order-canary

Gateway / service mesh:
  backend order-stable -> weight 95
  backend order-canary -> weight 5
```

Separating workloads helps keep both versions active concurrently, adjust weights, and scale the canary independently. However, the final design depends on the platform/rollout controller; do not copy this architecture if your environment already provides another supported canary mechanism.

### 7.3. Readiness Affects Effective Traffic

Canary pods may be created yet not become ready due to:

- Faulty JDK startup flags.
- Framework class initialization failure.
- Missing config/secrets.
- Java agent failure.
- Native library load failure.
- Health probe timeout too short.

If pods are not ready, requests will not reach the canary; a system looking only at overall 200 responses could "pass" even though **zero canary requests occurred**. There must be a gate verifying the number of ready pods and the actual requests passing through the canary.

## 8. Weighted Routing Example Using Kubernetes Gateway API

A platform supporting **Gateway API HTTPRoute weighted backends** can declare an illustrative configuration:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: order-routing
spec:
  parentRefs:
    - name: order-gateway
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /orders
      backendRefs:
        - name: order-stable
          port: 8080
          weight: 95
        - name: order-canary
          port: 8080
          weight: 5
```

**Prerequisites:**

- Namespace, gateway, listeners, Services, and backend ports must exist.
- The gateway implementation must support weighted backends.
- The route must be accepted by the controller and attached to the right listener/hostname.
- Authentication, TLS, and policy attachments must be consistent.
- Other routes must not accidentally bypass the canary split.
- Metrics/labels distinguishing stable and canary must exist after routing.

This example is a reference configuration, **not a file to apply directly to production**. After applying it in an authorized environment, you must verify the route status and actual request distribution.

### 8.1. Increasing Weight Does Not Mean Increasing Capacity Proportionally

If the canary has one replica and stable has multiple replicas, shifting from 5% to 25% traffic can overload the canary before users benefit from the new version. Inspect:

- Request rate/CPU per pod.
- Concurrency limit.
- HPA behavior.
- Queue length.
- Memory/heap and GC.
- Network/DB connection pool size.
- Pod readiness and warm-up.
- Traffic hotspots/tenant skew.

Traffic weight and replica count must be designed together, yet not equated.

### 8.2. If There Is No Weighted-Routing Controller

You can use:

- A service mesh with traffic splitting.
- An API gateway/ingress controller supporting canary.
- An application load balancer with weighted target groups.
- Cohort routing at a reverse proxy.
- Blue-green with group-by-group tenant/service migration.

Do not write a script that manually mutates endpoint labels in production just to simulate a canary when safe rollback mechanisms are lacking.

## 9. Choosing a Phased Traffic Ramp Plan

### 9.1. Sample Progression

An illustrative sequence:

```text
0% (deploy, no traffic)
      |
      v
1%  -> 5% -> 10% -> 25% -> 50% -> 100%
       |      |      |      |
    Gate A  Gate B Gate C Gate D
```

No single fixed percentage or duration fits every system. For a low-traffic service, 1% may yield too few samples; for a service with millions of requests, 1% may already be a large blast radius.

You can start with an internal cohort or restricted region instead of a fixed request percentage. The progression should be based on **risk budget, traffic volume, and confidence level**, not a generic "5% rule".

### 9.2. Each Stage Requires Three Conditions

1. **Minimum exposure:** enough meaningful requests/transactions have been processed by the canary.
2. **Minimum observation:** enough time has elapsed to observe startup, warm-up, GC, scheduled jobs, or slow-developing errors.
3. **Guardrails met:** errors, latency, resources, and business metrics are within defined thresholds, with no major incidents.

If samples are insufficient or there is a telemetry gap, the conclusion is **INCONCLUSIVE**, not PASS.

### 9.3. Early Stages May Take Longer Than Expected

A 1% canary in a low-traffic system might not receive rare workflows for days. In this case, you need:

- Additional synthetic smoke/contract test sequences.
- A cohort chosen to include the workflows requiring verification.
- A longer observation window.
- Increasing traffic to a level that yields sufficient samples, with clear guardrails.
- Or verifying in an isolated environment before expanding.

Do not increase traffic merely to reach sample size without appropriate rollback capability or monitoring.

### 9.4. Avoid Advancing Before Metrics Are Fully Aggregated

Metrics systems can have scrape intervals and delays, delayed log ingestion, or differing tracing sampling. If you just increased weight from 5% to 25%, do not immediately jump to 50% before the 25% window has sufficient data.

Record explicit timestamps for each stage, distinguishing the startup/ramp interval from the stable window.

## 10. SLOs, SLIs, and Guardrails for a Java Canary

### 10.1. Choose User-Meaningful Metrics

Some important SLIs:

| Category | SLI | Question |
|---|---|---|
| Availability | Successful request/transaction ratio | Are users completing their tasks? |
| Latency | p50/p95/p99 or ratio of requests below threshold | Does the new version worsen tail latency? |
| Correctness | Data/response contract mismatch | Are correct results returned? |
| Error quality | 5xx, timeouts, exceptions, retries | Are new errors hidden by retries? |
| Resource | CPU/req, RSS, GC, native memory | Do operational costs increase? |
| Startup | Time to readiness, cold p99 | Can new pods safely take load? |
| Business | Payment success, completed orders | Do business outcomes change? |
| Async | Queue lag, consumer errors, DLQ | Is background processing affected? |
| Security | TLS/auth failures, policy violations | Do JDK security defaults break integrations? |

Do not track only CPU or only request error rate. A release with lower CPU that writes corrupt data must still **fail**.

### 10.2. Baseline-Relative and Absolute Guardrails

Two types of conditions should be combined:

- **Absolute threshold:** the canary must remain within the product SLO.
- **Relative threshold:** the canary must not be worse than stable by more than the agreed budget when comparing the same traffic type.

Illustrative example:

```text
Absolute:
  availability >= SLO target
  p99 latency <= business limit

Relative:
  canary 5xx rate not materially worse than stable
  canary p95/p99 within agreed regression budget
  CPU/transaction and memory within capacity budget

Critical:
  no data corruption, irreversible writes,
  unauthorized access, or severe crash
```

Do not set an assumed threshold as a universal standard. Select specific numbers from the existing baseline, risk appetite, and SLOs.

### 10.3. Define the Right Denominator

Availability metric example:

```text
success_ratio =
  successful_business_transactions /
  eligible_business_transactions
```

Depending on the product, HTTP 2xx is not necessarily success (for example, HTTP 200 yet the transaction was rejected due to a backend error). Conversely, 4xx from invalid client requests is not necessarily an application error; however, an abnormal spike in the canary may reflect changed validation behavior.

You must define which requests count toward the error budget before measuring.

## 11. Canary Comparison Is Not Just Comparing Two Chart Lines

### 11.1. Metrics Must Share the Same Unit of Analysis

If stable receives many bulk/report requests while canary receives mostly lightweight GETs, lower average latency on the canary does not prove the new runtime is faster.

You can group by:

- Endpoint/route.
- HTTP method.
- Tenant size or cohort class.
- Request payload size buckets.
- Region/zone.
- HTTP status/error category.
- Cold/warm pod state.
- JVM/agent version.

However, overly granular grouping can cause metric cardinality explosion. Do not attach raw user IDs, emails, or request IDs to high-cardinality labels or expose sensitive data.

### 11.2. Sample Size and Confidence

p99 is sensitive when request counts are small. If the canary receives only a few dozen requests in a window, percentiles can fluctuate wildly or be meaningless.

When comparing:

1. Record the sample count for each version.
2. Define an appropriate confidence/statistical method.
3. Avoid calling "PASS" when data is insufficient.
4. Do not cherry-pick the best-looking time window.
5. Distinguish sample-based p99 from histogram-based estimation.
6. Account for delayed metrics and high-cardinality sampling.

You can use sequential testing or specialized canary analysis mechanisms, but false positives/false negatives must be managed. There is no single p-value threshold or observation duration suitable for all request rates.

### 11.3. Compare Against a Concurrent Stable Baseline

An application has hourly traffic fluctuations: comparing a canary at 02:00 with stable from 14:00 the previous day is usually unfair.

If both versions receive traffic concurrently, the comparison is more valid, though cohort skew and resource placement must still be controlled.

### 11.4. Do Not Mask Errors with Retries

If the canary throws a 500 and the gateway retries to stable and returns 200, end-user metrics may look normal while the canary is failing. Also track:

- First-attempt error rate.
- Retry attempts by backend version.
- Final client-visible outcome.
- Duplicate writes/idempotency.
- Extra latency due to retries.

A canary that triggers excessive retries should not be expanded just because the final success rate looks acceptable.

## 12. Tagging Version and JDK in Telemetry

### 12.1. Every Request Must Know Which Version Handled It

One design approach:

```text
service=order-api
release_track=stable | canary
app_version=4.8.1
image_digest=sha256:...
java_runtime=17 | 21
region=...
route=/orders/{id}
```

Version information should flow into metrics, traces, and logs in your observability system's standard format. Do not use raw path values containing user IDs as metric labels.

### 12.2. Avoid Labels Causing Excessive Cardinality

Labels that are generally controllable:

- `service`, `deployment_track`.
- `jdk_major`.
- `region`, `cluster`, `route_template`.
- `response_code_class`.
- `build_revision` if the number of active versions is bounded.

Do not use raw user/tenant IDs across all request counters. If analyzing a specific tenant is needed, use traces/logs under appropriate data policies instead of unbounded Prometheus labels.

### 12.3. Log and Trace Correlation

When an error occurs in the canary, you must answer:

- Which version was the request routed to?
- Which JDK was the JVM process running?
- At which step did the exception occur?
- Did a retry fall back to stable?
- Which downstream failed?
- Were any side effects committed?
- Does the error correlate with class loading, GC, TLS, or an agent?

Trace/log IDs help correlate sources, though not all information should be logged publicly.

## 13. Example Metrics Queries (Illustrative PromQL)

Suppose the application exposes a counter:

```text
http_server_requests_total{
  service="order-api",
  release_track="stable|canary",
  status_code="200|500|..."
}
```

Metric names and labels are **hypothetical** and must be replaced with your actual instrumentation.

### 13.1. Request Rate by Version

```promql
sum by (release_track) (
  rate(http_server_requests_total{service="order-api"}[5m])
)
```

### 13.2. 5xx Rate by Version

```promql
sum by (release_track) (
  rate(
    http_server_requests_total{
      service="order-api",
      status_code=~"5.."
    }[5m]
  )
)
/
clamp_min(
  sum by (release_track) (
    rate(http_server_requests_total{service="order-api"}[5m])
  ),
  0.000001
)
```

This is the 5xx rate and does not automatically include gateway timeouts, application-level failures, or retries. Separate metrics are needed for those cases.

### 13.3. p95/p99 When a Histogram Is Available

Suppose the exporter provides `http_server_request_duration_seconds_bucket`:

```promql
histogram_quantile(
  0.99,
  sum by (le, release_track) (
    rate(
      http_server_request_duration_seconds_bucket{
        service="order-api"
      }[5m]
    )
  )
)
```

Histogram quantile is an **estimate** based on bucket boundaries and metric conventions; it is not the same as computing p99 directly from raw request samples. If the service uses native histograms or a different metric schema, the query must be adjusted accordingly.

### 13.4. Do Not Let "No Traffic" Become a Pass

If the canary has no traffic, the request error rate may not appear or may have a near-zero denominator. You should not default to 0% error and declare a pass. The gate requires minimum traffic/exposure and verification of the per-version distribution.

## 14. JVM-Specific Metrics for a JDK Canary

### 14.1. Startup and Readiness

- Process start timestamp.
- JVM initialization/ready time.
- Application readiness transition.
- Startup errors and restart count.
- Pod scheduling/image pull time if analyzing end-to-end.
- Time from ready to SLO-compliant throughput.

Readiness does not mean the JIT has warmed up; a pod can become ready before hot methods are compiled or connection pools are fully initialized.

### 14.2. JIT and Code Cache

You can observe:

- CPU consumed by compiler threads during diagnostics.
- Compilation activity or queues via JFR/jcmd when appropriate.
- Code cache usage/warnings.
- Warm-up latency and throughput trend.
- Deoptimization/recompilation if investigating a hypothesis.

There is no need to enable verbose compilation logs for every canary pod in production. Prioritize telemetry with acceptable overhead; enable scoped diagnostics only when investigating an issue.

### 14.3. GC and Allocation

Track:

- GC pause time and frequency.
- Heap occupancy before/after GC.
- Allocation rate.
- Old-generation/full collections if the collector has corresponding concepts.
- Native memory/RSS.
- CPU usage and throttling.

When upgrading the JDK, the default GC or ergonomics may differ between releases/configurations. Comparisons must explicitly record flags and heap/CPU limits. A p99 spike coinciding with GC does not by itself prove a JIT regression.

### 14.4. Classloading and Reflection

The canary needs metrics/logs for:

- `ClassNotFoundException` and `NoClassDefFoundError`.
- `UnsupportedClassVersionError`.
- `InaccessibleObjectException`.
- `NoSuchMethodError`/`IllegalAccessError`.
- ServiceLoader/provider lookup failures.
- Agent/instrumentation errors.

Some errors only occur when a rare route or plugin is triggered; ensure appropriate execution within canary coverage.

### 14.5. JDK Security and I/O

Monitor anomalies in:

- TLS handshakes and certificate verification.
- HTTP client connection failures.
- DNS resolution.
- Filesystem encoding/locale.
- Cryptographic provider.
- Native library loading.
- Database driver validation.

Do not look only at server 5xxs if outbound client errors are swallowed by the application and turned into empty data or infinite retries.

## 15. Warm-Up and Cold Pods: A Distinct Challenge

### 15.1. A Small Canary Can Stay Permanently "Under-Warmed"

A canary receiving very few requests may have less opportunity to warm up hot paths compared to stable. This can lead to:

- More interpreted/C1 execution during the measurement window.
- Cold caches and class initialization.
- Delayed connection pool growth.
- Lower steady throughput due to insufficient load.
- Higher per-request latency than the baseline even though full traffic behavior may differ.

If you want to compare steady-state performance, measure after the canary is sufficiently warmed up **based on metrics and workload**, not merely after a fixed number of minutes.

### 15.2. Warm-Up Is Not Sending a Single GET /health

A health endpoint typically does not exercise:

- Business serializers/validators.
- JPA/SQL queries.
- TLS client handshakes.
- Native compression/calls.
- Complex DTO mapping.
- Error paths.
- Large payload handling.

If using synthetic warm-up traffic, simulate critical paths and ensure it causes no production side effects. Synthetic traffic must be labeled so it does not skew user SLO metrics.

### 15.3. Measure Cold and Warm Phases Separately

You can split into phases:

```text
Deploy canary pods
       |
       v
Readiness / startup metrics
       |
       v
Initial routed traffic
       |
       v
Warm-up observation
       |
       v
Steady observation
       |
       v
Traffic increase / phase shift
```

If you simply drop the cold window from reports, the team will miss autoscaling risks. If you measure only the cold window, the team may unfairly judge long-running throughput.

### 15.4. Canary Autoscaling Can Continuously Spawn Cold Pods

When increasing weight, the HPA may scale up additional pods. Each new pod has its own JIT/caches, triggering another warm-up cycle. Therefore, the post-traffic-increase gate must account for:

- New pod count.
- Pod age.
- Warm vs. cold pod share.
- JDK startup behavior.
- CPU/memory headroom.
- HPA stabilization and target utilization.

Do not evaluate only the deployment's global average.

## 16. Database and Shared-State Compatibility When Two Versions Run Simultaneously

### 16.1. Canary Often Shares State with Stable

Both versions may simultaneously read/write:

- The same relational database.
- Redis/cache keys.
- Kafka topics/consumer groups.
- Shared object storage.
- Session store.
- Message payloads and schema registry.
- Feature flags and configuration service.

If the canary writes a new format that stable cannot understand, **stopping routing to the canary does not undo the already-written data**.

### 16.2. Expand-Contract Migration

For schema changes, a common strategy:

1. **Expand:** add schemas/fields in a way that keeps the old version working.
2. **Dual-compatible:** both stable/canary understand the required data.
3. **Migrate:** backfill/transform according to a verified plan.
4. **Switch:** ramp traffic after the contract passes.
5. **Contract:** remove old structures only when no old consumers remain and rollback policy allows.

For example, adding a nullable column can be less risky than immediately altering types or dropping columns, though details depend on the database, ORM, and contract.

### 16.3. Serialization Changes Even When Business Code Barely Changes

Upgrading the JDK or framework can affect:

- Default charset and encoding when unspecified.
- Java serialization if class/metadata changed.
- Jackson/JSON date format when dependencies changed.
- XML/JAXB binding and namespaces.
- Locale/timezone data.
- Cache value types or binary format.
- JDK provider selection in cryptography.

You must test **forward/backward compatibility** when two versions consume the same data. If rollback requires the old version to read data written by the new version, make that a release gate.

### 16.4. ID Generation, Sequences, and Ordering

When both versions write to the database concurrently, ensure they do not generate duplicate IDs or conflicting ordering. If you change service logic, ORM, or transaction strategy alongside the JDK, the risk is much higher.

Canary is only a traffic-distribution method; it does not by itself solve concurrency, schema migration, or idempotency.

## 17. Queue Consumers and Background Jobs Bypass the HTTP Gateway

### 17.1. An Easily Overlooked Point

5% canary HTTP routing does **not** mean canary queue consumers or scheduled tasks handle only 5% of the work. If both stable and canary join the same consumer group, message distribution depends on broker partition assignment and concurrency, not HTTPRoute weights.

What can happen:

- Canary receives a partition with extremely heavy traffic.
- Canary processes more sensitive messages than stable.
- A cron job runs on both versions and sends duplicate notifications.
- A misconfigured leader-election lock creates two active schedulers.
- A new message schema breaks stable consumers.

### 17.2. Design Canary Separately for Asynchronous Work

Options, depending on the system:

- Select an explicit set of partitions/queues.
- Use producer cohort routing by key with a compatible contract.
- Run canary consumers in a dedicated group/test topic when isolation is needed.
- Keep schedulers disabled on the canary initially.
- Use safe leader election and test failover.
- Reduce concurrency in a controlled manner and monitor lag/DLQ.
- Run synthetic events that can be replayed/rolled back.

Do not casually add another consumer group to a production topic if doing so causes every message to be processed twice; understand the broker semantics.

### 17.3. Metrics Needed for an Async Canary

- Processed/successful events by version.
- Failed/retried events.
- Consumer lag and rebalance count.
- Dead-letter count.
- Processing latency by event type.
- Duplicate side effects/idempotency violations.
- Checkpoint/offset correctness.
- Graceful shutdown and in-flight message handling.

Do not sign off on a 100% rollout based solely on HTTP metrics when the application also processes queues or cron jobs.

## 18. Sticky Sessions, WebSockets, and Long-Lived Connections

### 18.1. Request-Level Splitting Can Break Session Behavior

If a user's first request hits the canary and the next hits stable while session formats differ, you may encounter:

- Authentication/session invalidation.
- Incompatible cache state.
- Different CSRF token or cookie behavior.
- Inconsistent feature state.
- Duplicate workflows or lost updates.

Session/user-based routing may suit stateful workloads better than request splitting, though it complicates cohorts and rollbacks.

### 18.2. WebSocket/gRPC Streaming

A connection lasting hours may stay pinned to one backend even after traffic weights change. Setting canary weight to 0 does not automatically drop existing connections; rollback requires policies for:

- Drain.
- Graceful shutdown.
- Connection lifetime cap.
- Reconnection behavior.
- Streaming state checkpointing.
- Ensuring no messages are lost when switching versions.

A canary with few connections where each connection carries many messages must not be evaluated by connection count alone.

### 18.3. Session Compatibility Is a Release Requirement

If both JDK versions still run the same app artifact, session compatibility may change less than when upgrading the framework simultaneously. Yet testing is still necessary because serialization, security providers, or the container/session store may differ.

Do not assume canary rollback is safe if users have received new state unreadable by stable.

## 19. Canary Analysis of Data Errors Undetected by HTTP Status

### 19.1. "200 OK" Is Not Always Business-Correct

A new version may return HTTP 200 yet:

- Monetary amounts are rounded incorrectly.
- Date/time formats have shifted timezones.
- Vietnamese text has corrupted encoding.
- JSON properties disappear.
- XML namespaces are wrong.
- Records are written twice.
- Authorization permits an invalid action.
- Cache keys changed, leaking data to the wrong tenant.

Canary needs domain-specific correctness checks, not just exception tracking.

### 19.2. Compare Outputs Against Contracts

If the system has read-only or pure computation paths, you can compare stable/canary responses against test fixtures. You must specify which fields are allowed to differ: timestamps, random IDs, ordering of unordered collections, headers, or tracing info.

A safer approach for operations with side effects is testing via staging/test accounts or workflows with clear domain rollback, rather than submitting the same payment transaction twice to "compare results".

### 19.3. Use Shadow Traffic Only with Isolation

If duplicating requests to evaluate the new version:

- Shadow requests must not write to the production DB again.
- Do not send real emails/SMS/payments/notifications.
- Do not expose personal data outside authorized boundaries.
- Downstream calls require sandboxes/mocks or read-only policies.
- Do not return shadow responses to users.
- Do not distort auditing, rate limits, or anti-fraud systems.

If these conditions cannot be guaranteed, **do not use mirroring for operations with side effects**.

## 20. Health Checks and Rollback Readiness

### 20.1. Startup, Readiness, and Liveness Have Different Meanings

- **Startup probe:** gives the application time to start without being killed prematurely by liveness, when supported by the environment.
- **Readiness probe:** signals that the backend can accept traffic according to contract.
- **Liveness probe:** detects a process condition requiring restart per policy.

If liveness is too strict during JIT/class initialization or GC startup, the canary may restart continuously. If readiness is too lenient, real requests arrive before the service is ready to process them.

### 20.2. Do Not Turn Readiness into a Full JIT Benchmark

Readiness should not wait for every method to be C2-compiled or run every business transaction. That can destabilize rollouts or trigger side effects.

Instead:

- Readiness ensures minimum components to receive traffic.
- Traffic ramp controls initial load.
- Warm-up observation evaluates cold performance.
- SLO guardrails monitor real user experience.

### 20.3. An Unhealthy Canary Pod Cannot Pass

The gate must inspect pod readiness/restarts and request counts, not just the stable aggregate. If the canary crashes and traffic automatically falls back to stable, the overall success rate can still look good; that is a **canary failure**.

## 21. Difference Between Traffic Rollback and Deployment Rollback

### 21.1. Traffic Rollback

Set canary weight to 0 or remove the cohort from routing:

```text
Before:
  stable 90%
  canary 10%

After abort:
  stable 100%
  canary 0%
```

This is a critical step to stop new requests, though some existing connections/streams/in-flight requests may continue. Gateways/controllers have propagation delays, so you must verify that the **actual request rate to the canary has dropped**.

### 21.2. Deployment Rollback

Once routing has stabilized:

- Drain canary connections.
- Stop background consumers/schedulers.
- Ensure in-flight transactions complete or are safely retried.
- Scale down or revert workload.
- Preserve logs/JFR/crash dumps before deleting pods if policy permits.
- Verify stable still has sufficient capacity.
- Log the incident and close or hold the release in a blocked state.

Do not hastily delete all canary logs after a rollback; that destroys root-cause evidence.

### 21.3. Data Rollback

If the canary wrote incompatible data, rollback may require:

- Stopping writers.
- Running pre-designed compensating transactions.
- Restoring from backup if approved and within RPO.
- A data repair/migration plan.
- Safely requeuing/replaying events.
- Isolating the affected tenant/cohort.

This can be high-risk work. That is why data compatibility must be verified before the canary and changes designed using **expand-contract** whenever possible.

### 21.4. Rollback Must Be Rehearsed

An untested runbook is not enough. Before expanding traffic, verify in staging or a controlled environment:

- Actual rollback commands/APIs.
- Auth/permissions.
- Propagation/detection time.
- How to drain workloads.
- Database/session compatibility.
- On-call notifications.
- How to return to stable success metrics.

Avoid relying on complex manual procedures known by only one person.

## 22. Emergency Stop (Abort) Rules Before Starting

### 22.1. Triggers That May Require Immediate Abort

Illustrative examples:

- Any evidence of corruption or data leakage.
- Security/authz bypass.
- Incorrect critical payment/billing side effect.
- Canary crash loop or lack of ready endpoints.
- Severe error increase compared to stable.
- p99 exceeding SLO past the agreed threshold.
- Dangerous queue lag/DLQ growth.
- Native JVM crash/agent incompatibility.
- Resource usage threatening shared downstream systems.
- Loss of canary observability or broken rollback controls.

Critical conditions may require an immediate abort without waiting for a large sample.

### 22.2. Distinguishing STOP, HOLD, and PROMOTE

| Decision | Situation | Action |
|---|---|---|
| **STOP / ABORT** | Critical guardrail violated | Stop traffic increase, roll back routing, and handle side effects |
| **HOLD** | Sparse data, metric delay, or uncertainty | Keep at a low level and gather additional observations if safe |
| **PROMOTE** | Sufficient exposure, tests, and guardrails met | Increase traffic according to the approved stage |
| **PAUSE FOR INVESTIGATION** | A metric drifted without a clear source | Do not increase load; isolate using logs/traces |
| **COMPLETE** | Full rollout and post-deploy verification achieved | Finalize release evidence and close the canary |

Do not equate "no errors detected" with "proven pass" when telemetry or coverage is lacking.

### 22.3. Guardrails Should Not Wait for the Release Manager to Be Online

Some organizations use automation to halt rollout progression when metrics breach thresholds. However, you need:

- Reviewed rules.
- Trustworthy metrics data.
- Scoped rollback permissions and auditing.
- No automatic execution of dangerous data rollbacks.
- Manual override and escalation policy.
- No masking of errors via infinite automatic rollout retries.

Automation is a supporting layer, not a replacement for operational responsibility.

## 23. Example Rollout Plan with Clear Gates

An illustrative runbook:

| Stage | Traffic | Requirements Before Advancing |
|---|---|---|
| **P0 — Deploy** | 0% external | Image/JDK/health/observability and rollback ready |
| **P1 — Internal** | Internal cohort | Synthetic critical paths, no critical exceptions |
| **P2 — Small** | 1–5% | Minimum exposure, error/latency guardrails, warm-up |
| **P3 — Medium** | 10–25% | Business flows, GC/CPU/memory, async jobs with sufficient data |
| **P4 — Large** | 50% | Soak, capacity, state compatibility, incident-free window |
| **P5 — Full** | 100% | SLOs and correctness continue to hold |
| **P6 — Observe** | 100% + monitoring | Verify tail effects, retain rollback window per policy |

These percentages are examples for discussion, not safe defaults. For low-volume jobs, a well-defined cohort can be more valuable than a percentage. For systems with financial or healthcare responsibilities, guardrails and validation need to be stricter.

### 23.1. Duration of Each Gate

There is no universal "5 minutes per stage is enough". It must depend on:

- Traffic volume.
- Latency SLO/window.
- When scheduled jobs run.
- JIT/cold startup.
- Database/queue behavior.
- Rare yet critical flows.
- Time required for leaks/resource regressions to surface.

If a service runs a nightly batch job, a canary active only at midday has not verified that batch path.

### 23.2. Expanding by Region or Tenant

When deploying across multiple regions, you can choose:

```text
Region A -> small cohort -> larger cohort -> full
Region B -> small cohort -> larger cohort -> full
Region C -> small cohort -> larger cohort -> full
```

Explicitly note that completing Region A does not by itself prove Region B is identical in CA trust, native libs, locale, availability zones, or networking.

## 24. Release Artifacts and JDK Provenance

### 24.1. What Must Be Versioned

Canary and stable require metadata:

```yaml
release:
  application_version: "4.8.1"
  commit: "<git-sha>"
  artifact_sha256: "<artifact-checksum>"
  container_image_digest: "<image-digest>"
  java:
    vendor: "<vendor>"
    version: "<major-update-build>"
  framework_version: "<version>"
  runtime_dependencies_manifest: "<reference>"
  gc: "<collector>"
  jvm_flags_reference: "<config-reference>"
  deployment_track: "canary"
```

Do not store secrets in the release manifest. Placeholder fields must be populated from the real pipeline.

### 24.2. A Container Image Tag Is Not Enough

A tag like `app:jdk21` can be overwritten. To conclude the canary ran the exact binary, you must store an immutable digest or equivalent provenance.

If using the same application JAR in two images with different JDKs, you can verify the application JAR SHA-256 is identical while recording the runtime layer difference.

### 24.3. The Actual Java Runtime Must Be Observed

Some containers have multiple JVM installations or launcher scripts that override `JAVA_HOME`. Simply seeing the CI build use Java 21 does not prove the production canary pod is running Java 21.

Obtain runtime metadata from process/startup logs or authenticated application telemetry; avoid exposing sensitive system properties on public endpoints.

## 25. CI/CD Pipeline for Canary Migration

A general pipeline:

```text
Commit / approved release
            |
            v
Build + unit/integration tests
            |
            v
JDK compatibility + artifact verification
            |
            v
Image signing / provenance / security policy
            |
            v
Staging contract + performance smoke
            |
            v
Deploy canary workloads (0% external)
            |
            v
Preflight health + telemetry + rollback test
            |
            v
Controlled traffic stage
            |
            v
Automated + human review (if policy)
            |
         +--+--+
         |     |
       FAIL   PASS
         |     |
         v     v
       ABORT  PROMOTE
         |     |
         v     v
     Incident   Next stage / full rollout
```

The pipeline must freeze the artifact between steps. If the "deploy canary" job rebuilds source with newer dependency versions, evidence from staging may no longer apply.

### 25.1. Do Not Allow the Pipeline to Bypass Security/Quality Gates

Canary is a **subsequent step** after testing and artifact controls, not a reason to skip:

- Unit/integration tests.
- Dependency vulnerability checks.
- Artifact provenance.
- Secret scanning.
- API schema compatibility.
- Database migration review.
- Required approvals.

### 25.2. Variables That Must Be Synchronized

- JDK build/runtime vendor.
- Container image/OS.
- JVM flags.
- Framework/server dependencies.
- Feature flags.
- Schema version.
- Traffic routing policies.
- Monitoring labels.
- Synthetic traffic exclusions.

If canary and stable use differently configured backends, the report must state this explicitly.

## 26. Notable JVM Issues During a Canary

### 26.1. JEP 403 and Reflection

When upgrading to JDKs with stricter strong encapsulation, older frameworks or agents may encounter `InaccessibleObjectException` on rare code paths. The canary needs to log exception types and exercise sufficient reflection-heavy workflows.

`--add-opens` can be a scoped workaround if approved, but should not be enabled en masse just to keep the canary green. Record the owner and library upgrade plan.

### 26.2. JEP 320 and Removed Java EE APIs

Upgrading from JDK 8 to JDK 11+ can remove JAXB/JAX-WS/Activation modules previously bundled in the JDK. A REST endpoint may pass while XML export fails because `javax.xml.bind.JAXBContext` is only dynamically loaded.

Before the canary, test XML/SOAP workflows, or supply the appropriate runtime dependencies in the verified artifact. If the canary passes because no XML requests arrived, the result still does not cover this risk.

### 26.3. JEP 400 and Default Charset

When moving to JDK 18+, the UTF-8 default charset can alter behavior compared to legacy environments for APIs relying on the default charset. A canary handling legacy files must test byte-level data and inspect accented characters, especially in import/export flows.

Do not compare only HTTP status when output files suffer encoding corruption.

### 26.4. Bytecode Level and Runtime Graph

If a dependency class was compiled for Java 21 while the canary runtime is still Java 17, `UnsupportedClassVersionError` can occur on the code path loading that class. If the goal is to upgrade the runtime to Java 21, verify the actual image contains Java 21 and the classpath does not mix incompatible JARs.

An application compiled with target 17 can still run on a JDK 21 runtime; there is no requirement to bump the bytecode target to 21 in the same batch.

### 26.5. Java Agents and Native Code

A Java agent or JNI library running fine on the baseline JDK is not guaranteed to support the target JDK. The canary must verify agent startup, bytecode instrumentation, native library version, architecture, and resource cleanup.

A native crash can terminate the entire JVM; a route rollback will not undo transactions that already produced side effects before the crash.

### 26.6. Virtual Threads and Concurrency

If a JDK 17 → 21 migration simultaneously switches executors to virtual threads, that is a separate concurrency architecture change. It can increase concurrent requests and cause downstream saturation, even when the JDK runtime improves throughput.

Test the JDK upgrade without changing the thread model before evaluating virtual threads' impact, if the product allows. If combining them is unavoidable, clearly record that the canary measures a **full-stack change**, not just the JDK delta.

## 27. Isolating Results When Stable/Canary Share Downstream Dependencies

### 27.1. The Database Can Be a Shared Bottleneck

If the canary consumes extra connection pool capacity or sends different queries, it can affect stable. In that case, stable is no longer a completely independent control group.

Monitor:

- DB active/idle connections.
- Query latency and lock waits.
- Transaction aborts/deadlocks.
- Slow queries.
- Saturation of shared connection pool/DB.
- Cache hit rate and eviction.
- Partner-side rate limits.

If both stable and canary degrade together, do not automatically assume the canary is innocent; it may be causing shared-backend overload.

### 27.2. Fair Resource Cost Comparison

A canary receiving less load may have higher CPU/request due to startup, fixed overhead, or unwarmed JIT; under heavier load, different bottlenecks may emerge.

When comparing:

- Use the same hardware/container budget if possible.
- Inspect per-pod CPU and request rate.
- Separate cold/warm pods.
- Compare p95/p99 by request mix.
- Check autoscaling and downstream capacity.

Do not alter CPU limits only for the canary if the goal is to isolate the JDK runtime, unless documented as a configuration change requiring verification.

### 27.3. Checking for Cascade Failures

A failing canary can increase retries, overloading the database/queue or the stable version. Limit retry budgets, concurrency, and circuit-breaker behavior so the blast radius is genuinely contained.

A canary is not safe if 1% of user traffic can cause 100% downstream saturation via a retry storm.

## 28. How to Handle Degraded Metrics When Root Cause Is Unclear

### 28.1. Do Not Rush to Fix by Increasing Heap

If canary p99 is high:

1. Check sample count, traffic mix, and version labels.
2. Check cold/warm pod age.
3. Check CPU quota/throttling.
4. Check GC pauses, allocation, and RSS.
5. Check JIT/warm-up if there are signs.
6. Check downstream latency/retries.
7. Check Java agents/observability overhead.
8. Inspect application logs/traces of slow requests.
9. Compare against stable at the same point in time.
10. Decide on HOLD, ABORT, or testing configuration in staging.

Increasing heap or changing GC while evaluating a JDK can obscure the root cause. If a mitigation must be tested, save it as a new canary version/config with a clear baseline.

### 28.2. Canary Error Spike Immediately Upon Traffic Shift

Some possibilities:

- Readiness does not guarantee the application is actually ready.
- TLS/DB pool not yet initialized.
- Classloading/lazy initialization.
- Faulty JDK flags or agent.
- Insufficient memory/CPU resources.
- Routing/gateway misconfiguration.
- Canary cohort data has different characteristics from stable.

Before labeling it a "JDK regression", verify metrics and logs. However, when a critical guardrail is violated, **stop/roll back first and investigate afterward**—do not keep real traffic flowing just to gather more logs.

### 28.3. Failures Appearing Only After Many Hours

May be related to:

- Native memory leaks.
- File descriptor/connection leaks.
- GC/memory pressure.
- Background jobs.
- TLS certificate rotation.
- Stale classloader/plugin behavior.
- Queue replay.
- Cache eviction/TTL.
- Scheduled job code paths.

Therefore, each stage needs an observation window matched to the workload type, not just a few smoke requests.

## 29. Canary Incident Handling Procedure

### Step 1 — Trigger Abort per Guardrail

Stop increasing traffic and revert routing to stable per runbook if critical thresholds are breached.

### Step 2 — Verify Effectiveness

Check backend request rate: is the canary still receiving new requests? Do long-lived sessions/streams need draining?

### Step 3 — Protect Downstream Services and Data

Stop/protect queue consumers, schedulers, writes, or external side effects if needed, per the approved plan.

### Step 4 — Preserve Evidence

Save the image digest, JDK version, logs, traces, metrics windows, crash reports, and pod events per policy. Prevent GC/rollout from wiping out evidence.

### Step 5 — Classify the Failure

- JDK API removal.
- Reflection/JPMS.
- Bytecode/dependency mismatch.
- Native/agent.
- TLS/charset/timezone.
- JIT/GC/resource/performance.
- Routing/readiness.
- Data/session/queue compatibility.
- External backend/shared resource.

### Step 6 — Decide Next Steps: Continue Rollback, Fix-Forward, or Pause

If it was only a routing config issue and the fix is verified, a new canary can be started. If there is data corruption or security impact, follow the full incident process rather than automatically retrying the release.

### Step 7 — Close the Incident and Add New Guardrails

Record the root cause, affected traffic/time window, request/tenant scope, blast radius, data repair, and regression tests to add.

## 30. End-to-End Example: JDK 17 → JDK 21 Canary for a REST Service

Suppose a service:

```text
Service: order-api
Current runtime: JDK 17
Target runtime: JDK 21
App JAR: same release revision, same SHA-256
Framework: version verified to support JDK 21
Deployment: Kubernetes, two workloads
Traffic: REST requests + queue consumers
Shared backend: PostgreSQL + Redis
SLO: agreed p99 / error budget
```

### 30.1. Pre-Rollout

The team:

1. Runs the artifact on JDK 21 in staging.
2. Tests business flows, TLS, JDBC, serialization, and security.
3. Verifies the container JDK 21 process/version.
4. Locks in stable/canary routing and telemetry labels.
5. Verifies bidirectional database compatibility.
6. Decides to keep queue consumers disabled on the initial canary.
7. Rehearses rollback from a small cohort.
8. Defines error/latency/business guardrails.

### 30.2. P0/P1 Stage

Deploy canary with 0% external traffic, measure startup, probes, and image/JDK provenance. Run an internal test cohort to trigger critical business paths and verify logs/traces carry the proper labels.

If an `InaccessibleObjectException` occurs in the serializer when creating a specific DTO, stop immediately and fix the library; there is no reason to open 5% user traffic yet.

### 30.3. Small Traffic Stage

Shift a small cohort, verify actual request distribution, and measure cold/warm separately.

Suppose the canary shows high p99 in the first few minutes but falls within threshold after warm-up, while stable remains steady throughout. The team should not declare pass based solely on steady-state numbers; they must check autoscaling/cold-pod SLOs. They can hold traffic, adjust the ramp, or add capacity per procedure after identifying the cause.

### 30.4. Medium Stage

Increase traffic once samples are sufficient and guardrails pass. Check:

- Per-route errors/latency.
- CPU/request, GC, JIT warm-up.
- DB pool/Redis impact.
- Pod restarts/readiness.
- Session affinity.
- Security/TLS and charset.
- Business outcome metrics.

If enabling canary queue consumers, have a separate routing/partitioning plan—do not use HTTP traffic weight as a proxy.

### 30.5. Full and Observation Stage

When traffic reaches 100%:

- Do not immediately delete stable rollback capacity if policy requires an observation window.
- Re-measure SLOs under full-load behavior, since 50% may not have exposed capacity bottlenecks.
- Monitor at least one full operational cycle to observe relevant scheduled jobs.
- Verify newly written data can be read by the rollback version if policy requires.
- Finalize evidence and owners for remaining workarounds.

The valid conclusion is: **this specific release on JDK 21 met guardrails under the observed traffic and environment**, not that every Java 17 application is safe on Java 21.

## 31. Second Example: JDK 8 → JDK 21 and Rare Code Paths

A legacy application uses JAXB from JDK 8, but XML export accounts for only a small fraction of requests. The project runs the app on JDK 21, and health and JSON endpoints pass. A 1% canary receives only JSON traffic and therefore misses the missing JAXB API/runtime.

After full rollout, the first user calls XML export and hits:

```text
java.lang.NoClassDefFoundError:
  javax/xml/bind/JAXBContext
```

Lessons here:

1. Do not use a small traffic share as proof of full coverage.
2. Rare but critical features must have synthetic/contract tests before the canary.
3. Before upgrading JDK 8 to 11+, check for JAXB/JAX-WS/Activation modules removed from the JDK.
4. Add the right generation of API/runtime providers when needed, producing a newly verified artifact.
5. Clearly record that adding runtime dependencies produces a different deployment bundle; do not keep calling it an unchanged binary.
6. Create a regression test exercising XML export on the target JDK.

A canary only catches bugs when tests or traffic actually trigger the failing path.

## 32. When Should You Not Expand Traffic?

A sample set of **NO-GO** criteria:

- Unknown exact binary/JDK running in the canary.
- Unable to measure canary request rate or error rate separately.
- Stable/canary do not share a compatible data contract; rollback could corrupt state.
- Canary pods are not ready, in a restart loop, or receiving no real traffic.
- No procedure to stop queue consumers/schedulers.
- Critical failure in security, data integrity, or payments.
- Framework/vendor target JDK support missing under mandatory policy.
- Guardrails not met or metrics untrustworthy.
- Insufficient sample size/code path coverage for the next load increase.
- No owner on call for rollback during the rollout window.
- Downstream services are near saturation and the canary could trigger a retry storm.
- Artifact changed unexpectedly so baseline results are no longer comparable.

When evidence is missing, **HOLD** for additional verification is a valid outcome. When a critical violation occurs, **ABORT** per runbook is safer than "waiting for enough samples".

## 33. Common Misconceptions

| Misconception | Reality |
|---|---|
| "One new pod out of 20 pods means 5% traffic" | Replica ratio does not guarantee request share |
| "RollingUpdate is automatically a safe canary" | Separate stages, routing, and analysis are needed |
| "No errors in 5 minutes means pass" | Samples may be insufficient or code paths untouched |
| "Health 200 means JDK compatibility is sufficient" | Health does not verify TLS/JAXB/JPA/native/rare flows |
| "Lower canary p99 than stable means the new JDK is faster" | Traffic mix, cold state, and hardware must be balanced |
| "Setting canary weight to 0 undoes everything" | DB/queue/session side effects still persist |
| "5% HTTP traffic means 5% queue work" | Queue assignment and schedulers are independent |
| "New JDK with same JAR means data cannot change" | Charset/timezone/security/defaults can differ |
| "A small canary cannot cause a major outage" | Retry storms or shared DB saturation can still spread |
| "p99 from very few requests is strong evidence" | Low-sample percentiles fluctuate wildly |
| "Gateway returned 200 so canary had no errors" | Retries to stable may mask backend failures |
| "Shadow POST is safe because the response is discarded" | Side effects can still occur without isolation |
| "Readiness=true means JIT is warmed up" | Readiness and steady performance are different |
| "One region passing means all regions pass" | Native libs/CAs/CPUs/traffic may differ |
| "Rollback only needs keeping the old app image" | There are also data, config, schema, agent, runtime, and sessions |
| "Just increase heap to fix p99 when JDK changes" | Isolate JIT/GC/CPU/downstream first |
| "Passing SLOs is enough; no need for business correctness" | Writing corrupt data is unacceptable |
| "Canary replaces integration tests" | Rare paths may not be triggered by traffic |
| "A release can promote without canary data" | Zero exposure is not a PASS |

## 34. Checklist Before, During, and After Canary

### Before Opening Traffic

- [ ] Confirmed runtime upgrade goal, scope, and variable isolation.
- [ ] Locked application artifact checksum/image digest.
- [ ] Verified JDK vendor/version/build in the actual running process.
- [ ] Checked framework, dependency, native library, and agent support matrix.
- [ ] Ran unit/integration/contract tests on the target JDK.
- [ ] Verified class-file version, JPMS/reflection, TLS, charset, and serialization.
- [ ] Verified appropriate health/startup/readiness/liveness probes.
- [ ] Configured stable/canary workloads and routing.
- [ ] Verified rollback permissions and rehearsed in an authorized environment.
- [ ] Defined SLIs/SLOs, stop/hold/promote criteria, and minimum exposure.
- [ ] Confirmed database/cache/session/queue compatibility.
- [ ] Addressed side effects, scheduled jobs, and consumer-group semantics.
- [ ] Prepared version labels and observability dashboards.
- [ ] Assigned rollout owner, on-call, and escalation contacts.
- [ ] Checked secrets, logging/privacy, and security policies.

### During Traffic Testing

- [ ] Verified actual canary request share, not just routing weight.
- [ ] Confirmed ready canary pods have traffic and capacity.
- [ ] Observed request mix/cohorts, retries, and backend attempts.
- [ ] Separated cold/warm canary metrics.
- [ ] Monitored errors, p95/p99, throughput, and business outcomes.
- [ ] Observed CPU, GC, memory, container throttling, and restarts.
- [ ] Checked TLS, native, agent, class loading, and reflection exceptions.
- [ ] Monitored queue lag/DLQ/schedulers if applicable.
- [ ] Checked shared backend load and retry amplification.
- [ ] Waited for sufficient samples, observation window, and metrics ingestion.
- [ ] Logged every weight/cohort change with timestamps.
- [ ] Halted traffic increases upon guardrail uncertainty.
- [ ] Aborted promptly if a critical incident occurred.

### After Promote or Abort

- [ ] Verified the full deployment is actually receiving expected traffic.
- [ ] Observed post-promotion SLOs and batch/soak behavior.
- [ ] Confirmed old/new state compatibility within the rollback window.
- [ ] Retained rollback artifact/runtime/image and runbook per policy.
- [ ] If aborted, stopped traffic, drained connections, and handled async jobs.
- [ ] Evaluated data repair/side effects if errors occurred.
- [ ] Saved logs, traces, metrics, and crash evidence appropriately.
- [ ] Documented incident/root cause and follow-up regression tests.
- [ ] Tracked remaining workarounds, owners, and technical debt.
- [ ] Updated support matrix and release documentation.

## 35. Handover Package for Release/Operations Teams

A canary run should produce the following package:

1. **Change scope:** JDK-only, JDK + container, or JDK + framework/dependency.
2. **Artifact provenance:** SHA-256 or immutable image digest, git revision, and BOM/lockfile.
3. **Runtime matrix:** JDK vendor/build, JVM flags, GC, agents, OS/architecture.
4. **Traffic plan:** routing/cohort strategy, per-stage percentages, endpoint eligibility.
5. **Coverage:** tested business flows/feature flags/async paths.
6. **Shared-state plan:** schema/session/queue compatibility and side-effect ownership.
7. **Baseline:** stable SLOs, traffic mix, and resource metrics.
8. **Canary telemetry:** version-labeled dashboards, logs/traces, real traffic share.
9. **Decision gates:** thresholds, minimum exposure, observation windows, owners.
10. **Stage evidence:** timestamps, sample counts, metrics, approval/decision.
11. **Operational incidents:** crashes, retries, data anomalies, and resolutions.
12. **Rollback proof:** route switch, connection drain, async pause, and data recovery.
13. **Post-rollout verification:** full-load SLOs, autoscaling, cold starts, and scheduled jobs.
14. **Residual risks:** uncovered code paths, framework support gaps, and workarounds.
15. **Next steps:** clean up stable resources per policy, upgrade toolchain/source/dependencies if needed.

### Short Decision Log Sample

```yaml
canary:
  service: "order-api"
  release_id: "<release>"
  stable:
    app_artifact: "<sha256>"
    jdk: "<vendor-17-build>"
  candidate:
    app_artifact: "<sha256>"
    jdk: "<vendor-21-build>"
  routing:
    method: "weighted-gateway"
    desired_weight_percent: 5
    measured_share_percent: "<observed>"
  analysis:
    window: "<start-end>"
    request_samples: "<count>"
    required_exposure_met: false
    functional_contracts: "PASS"
    error_guardrail: "PASS"
    latency_guardrail: "INCONCLUSIVE"
    data_compatibility: "PASS"
    async_workload_coverage: "PENDING"
  decision:
    status: "HOLD"
    reason: "Insufficient observation for async workflow"
    owner: "<release-owner>"
  rollback:
    route_procedure: "<runbook-reference>"
    artifact_reference: "<immutable-image-digest>"
```

The sample fields are not production metrics. If `required_exposure_met=false` or critical guardrails remain `INCONCLUSIVE/PENDING`, do not manually change `status` to `PROMOTE` just because the remaining checks show PASS.

**Conclusion:** A canary release reduces risk during a Java/JDK upgrade by limiting a portion of real traffic to the new version, measuring stable and canary separately, and expanding through evidence-backed decision gates. A good canary is not just a few pods on the new JDK: it requires **artifact provenance, controllable routing, sufficient code path coverage, cold/warm JVM observation, SLO and correctness guardrails, data compatibility while both versions coexist, async workload management, and genuinely prepared rollback**. Scale to 100% only when those criteria are met, and continue monitoring after full rollout because full load can reveal issues that a small canary cannot.
