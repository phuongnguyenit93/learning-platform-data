# Canary Rollout on a Portion of Traffic and Quality Monitoring

Bringing a Java application using CRaC into production should not start by shifting all traffic to newly restored processes. Even if checkpoint and restore have succeeded in a test environment, production also has real load, user data, shared backends, long-lived sessions, changing caches, and concurrent scale-out bursts. The safe deployment approach is to bring a group of restored instances in to serve a portion of traffic, keep a normal cold-start group as a control, monitor quality over a sufficiently long period, and only then increase the percentage.

This is a form of canary rollout. The canary group uses the checkpoint image and restore process; the control group continues cold starting with the current deployment method. Both groups serve the same application version and the same API contract so they can be compared. If the canary performs well and does not degrade the SLO, the traffic percentage can be increased gradually. If quality drops, the orchestrator shifts traffic back to the control group and stops expanding.

Canary does not only measure restore time. You need to monitor time-to-readiness, first-request latency, request errors, p95/p99, dependency recovery, memory/CPU, cache freshness, and business metrics. The goal is to prove that the newly restored process serves correctly and stably under real load, while having a clear path back.

## 1. Canary model for CRaC

In a simple model, there are two cohorts:

- **Control:** instances created from the normal image/container that start the JVM from scratch.
- **Canary:** instances created by restoring from a prepared checkpoint image.

Both groups should use the same application release, business configuration, dependencies, and resource limits. The main difference to measure is how the process is brought to a serving state. If the canary group uses a newer JDK, different CPU, different heap, or a different backend, the results will no longer reflect the impact of CRaC alone.

~~~mermaid
flowchart TD
    U[Client traffic] --> G[Ingress / gateway / service mesh]
    G -->|Control weight| C[Cold-start Deployment]
    G -->|Canary weight| R[CRaC restore Deployment]
    C --> DB[(Shared dependencies)]
    R --> DB
    C --> M[Metrics and traces]
    R --> M
    M --> D[Dashboard and rollout gates]
    D -->|Healthy: increase weight| G
    D -->|Unhealthy: rollback| G
~~~

Traffic is split at the ingress, gateway, or service mesh. The specific splitting mechanism depends on the platform; what matters is identifying which request belongs to which cohort and being able to change the ratio without modifying business logic.

### 1.1. Distinguishing canary rollout and benchmark

Benchmarks usually fix the workload and environment to compare performance. A canary rollout puts a small group into production to test behavior with real traffic, data, and dependencies. The two activities complement each other:

- Benchmarks help determine how much faster restore is than cold start and identify technical limits.
- Canary helps confirm real-world quality, including rare errors, stale caches, reconnects, sessions, and backend load.

Do not use canary as the first test for a checkpoint image that has never been successfully restored. Before that, there must be real image testing in a compatible environment, smoke tests, and a rehearsed rollback procedure.

## 2. Prerequisites before putting a canary into production

Before splitting traffic, prepare the following components:

1. **Identifiable checkpoint image:** know which application release, JDK, OS, CPU profile, native libraries, and configuration the image was created from.
2. **Repeatable restore process:** able to create additional instances from the image, check callbacks, and identify failure states.
3. **True readiness:** an instance only receives traffic after mandatory Resources have recovered and required dependencies have been verified.
4. **Control cohort:** still able to create cold-start instances from the same application release for comparison.
5. **Adjustable traffic routing:** change weights or disable the canary without needing client changes.
6. **Observability:** metrics, logs, and traces labeled with cohort, release, checkpoint ID, and instance ID.
7. **Spare capacity:** enough resources for the control cohort to continue serving if the canary is pulled from traffic.
8. **Tested rollback:** know how to shift traffic back to control and handle running canary instances.

If any of these conditions are missing, the rollout will make it hard to distinguish CRaC issues from application or infrastructure issues.

### 2.1. Using the same application release

Canary and control should run the same application artifact, business configuration, and compatible schema. If the canary runs new code while also using CRaC, and control runs the old version, an error could come from code changes rather than restore.

When you need to test both a new release and CRaC, split them into two separately measurable changes:

- First deploy the new release using cold start and verify quality.
- Then create a checkpoint from that exact release and canary the CRaC startup method.

If testing both simultaneously is unavoidable, you need a separate cohort matrix to distinguish the release variable from the restore variable.

### 2.2. Identifying the checkpoint image and expiration

A checkpoint image should be treated as an artifact tied to a runtime profile. Metadata should record at least:

- Application version or commit/build ID.
- JDK vendor, version, build, and JVM flags.
- OS/kernel and checkpoint engine/CRIU version matching the image creation environment.
- CPU architecture and feature baseline.
- Native libraries, Java agents, and profiler versions.
- Critical configuration, schema version, and dependency types.
- Image creation timestamp and warm-up duration.
- Resource callback procedure version.

Do not use an old image after the application, JDK, native dependencies, or CPU profile changes without verifying compatibility. Set an image expiration policy; an image that is too old may contain caches, credentials, or runtime state that are no longer valid.

## 3. Choosing traffic cohorts and how to split traffic

Traffic splitting can be done by random percentage, consistent hashing by user/tenant, or rules by request type. Choose the splitting method based on the characteristics of the application.

### 3.1. Percentage split at the gateway

This is a simple approach when requests are independent and do not require session affinity. For example, 95% of traffic goes to control and 5% to canary. The gateway/service mesh decides the destination by weight.

Advantages:

- Can increase/decrease the ratio without modifying clients.
- Can quickly pull the canary from traffic when errors are detected.
- Easy to observe the actual request ratio between the two cohorts.

Limitations:

- A user may hit both cohorts across consecutive requests if routing is not sticky.
- Sessions stored in an instance's memory may not exist in the other cohort.
- Requests belonging to the same business flow may be split across the two groups.

### 3.2. Consistent hashing by user or tenant

For applications with sessions or multi-step workflows, you can hash by user ID, tenant ID, or a stable key so the same group of users always lands on the same cohort during the experiment.

For example, 5% of tenants are routed to canary and the rest to control. This reduces the chance of a session switching instances mid-flight. However, ensure that:

- The key used for hashing is stable and does not expose sensitive data in logs.
- Tenant distribution is balanced enough; one large tenant should not give the canary abnormal load.
- The user group can be shifted back to control on rollback.
- Session state and written data remain compatible between the two cohorts.

Do not use consistent hashing if it forces a critical customer group to bear the entire canary risk without load limits.

### 3.3. Choosing appropriate traffic types

In the initial phase, you can choose read requests, requests without side effects, or a low-risk subset of endpoints. Once quality is stable, expand to more complex flows.

| Traffic type | Approach |
|---|---|
| Read-only request | Usually suitable to start with, but still must check cache freshness and consistency. |
| Data-writing request | Only include once schema, idempotency, retry, and rollback are clear. |
| Multi-step workflow | Use sticky routing or ensure shared session/state. |
| WebSocket/SSE/streaming | Check reconnect/resume and connection lifetime; do not rely solely on request weight. |
| Background consumer | Do not deliver the same messages to two consumer groups just to create a traffic split; require clear partition/ownership. |
| Scheduled job | Only one cohort should hold the right to run write jobs at a time, unless the job is designed to be idempotent and has leader election. |

### 3.4. Avoiding duplicate work when splitting messages

HTTP traffic can be routed per request, but message consumers and scheduled jobs have different semantics. If control and canary both subscribe to a topic using two separate consumer groups, both can process the same message and cause duplicate side effects.

For background workers, choose one of the following:

- Have only control process messages during the initial HTTP canary phase.
- Use partition assignment to divide messages exclusively.
- Use a single consumer group and a clearly designed handoff mechanism.
- Use idempotency keys and deduplication storage if the business logic allows.
- Disable scheduled jobs on canary until ownership is transferred.

Do not assume reducing HTTP traffic weight is enough to isolate all side effects of the canary.

## 4. Deploying two cohorts in Kubernetes

One deployment pattern is to create two Deployments from the same application image:

- **orders-control:** runs the normal Java startup command.
- **orders-crac:** restores from the prepared checkpoint image.

Both Deployments can share dependent Services and the same application release. They have different cohort labels so metrics and logs distinguish them.

Condensed Deployment example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-control
spec:
  replicas: 9
  selector:
    matchLabels:
      app: orders
      cohort: control
  template:
    metadata:
      labels:
        app: orders
        cohort: control
        release: "2026.11.13"
    spec:
      containers:
        - name: app
          image: example/orders:2026.11.13
          command: ["java", "-jar", "/app/orders.jar"]
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /ready
              port: http
            periodSeconds: 5
            failureThreshold: 3
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-crac
spec:
  replicas: 1
  selector:
    matchLabels:
      app: orders
      cohort: crac
  template:
    metadata:
      labels:
        app: orders
        cohort: crac
        release: "2026.11.13"
    spec:
      containers:
        - name: app
          image: example/orders-crac:2026.11.13
          command: ["/opt/crac/restore-entrypoint"]
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /ready
              port: http
            periodSeconds: 5
            failureThreshold: 3
~~~

**restore-entrypoint** is only a placeholder for the platform's restore mechanism, not a standard CRaC command. In practice, checkpoint/restore may be performed by the container runtime, CRIU integration, or a dedicated controller. Do not replace the container command with a hypothetical script if the runtime requires starting/restoring differently.

### 4.1. Separating Services by cohort

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: orders-control
spec:
  selector:
    app: orders
    cohort: control
  ports:
    - name: http
      port: 80
      targetPort: http
---
apiVersion: v1
kind: Service
metadata:
  name: orders-crac
spec:
  selector:
    app: orders
    cohort: crac
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

Separate Services let the gateway route clearly by cohort. The readiness probe must reflect true serving capability; a Pod that is not ready will not be included in normal Service endpoint routing.

### 4.2. Example of splitting traffic with Istio

If the cluster uses Istio, a VirtualService can split weights between the two Services:

~~~yaml
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata:
  name: orders
spec:
  hosts:
    - orders.example.internal
  http:
    - route:
        - destination:
            host: orders-control
            port:
              number: 80
          weight: 95
        - destination:
            host: orders-crac
            port:
              number: 80
          weight: 5
~~~

This is an example Istio configuration; the cluster needs an appropriate Istio Gateway/route and both Services must exist. Weight is a target routing ratio, not guaranteed to be exact in every small window due to low request counts or how the proxy distributes traffic. Verify the actual ratio from server-side metrics.

If using NGINX Ingress, Gateway API, Argo Rollouts, or another platform, use the corresponding traffic splitting mechanism. There is no need to modify the application to run a canary if the routing layer already supports it.

## 5. Readiness and liveness after restore

A newly restored Pod may already have a process running but still not be ready to receive traffic. Readiness must reflect the application's recovery state.

### 5.1. Readiness by mandatory capabilities

The readiness endpoint should check mandatory dependencies needed to serve primary requests, for example:

- Resource callbacks have completed.
- The database pool can issue a connection and a test query succeeds.
- Mandatory caches have valid data or a fallback.
- HTTP clients/service discovery are working.
- Message consumers or workers are only started when needed.
- Recovery gates are open for routed capabilities.

Not every optional dependency needs to be ready to enable the entire application. You can express readiness per capability or disable routes to degraded features. However, if the readiness endpoint just returns 200 whenever the JVM is alive, the gateway may send traffic too early.

### 5.2. Distinguishing readiness and liveness

- **Liveness** answers whether the process is still alive and can continue. Liveness should not fail just because the database temporarily loses connection, if the application can recover.
- **Readiness** answers whether the instance can receive traffic yet. During RESTORING, readiness should be false.
- **Startup probe** can protect applications with long startup/recovery, preventing the liveness probe from firing too early and causing false restarts.

When readiness is false, ensure the gateway does not route new requests to that Pod. If the system uses a sidecar or custom proxy, verify its actual behavior.

### 5.3. Do not open readiness too early

A common mistake is an `afterRestore` callback creating the client object successfully and immediately marking ready, even though the connection to the server has not been verified. Distinguish "client object created" from "dependency can serve requests." You can run a lightweight health check with a timeout before opening the gate.

Do not run health checks that cause side effects. Database checks should use a safe read query; broker checks should verify connectivity/metadata without producing business messages.

## 6. Monitoring quality: SLIs, SLOs, and CRaC metrics

Canary needs a dashboard that can compare both cohorts over the same time window and workload. Metrics should be organized into four groups.

### 6.1. Request quality

- Request rate by cohort.
- Error rate by status class and exception type.
- Timeout, connection reset, and retry rate.
- Latency p50, p95, p99.
- First-request latency after readiness turns on.
- Request success rate by endpoint/capability.

### 6.2. Restore quality

- Restore success/failure count.
- Restore engine duration if provided by the platform.
- Duration of each `afterRestore` callback.
- Restore-to-ready duration.
- Checkpoint image age and image version.
- Rate of instances having to fall back to cold start.
- Native library, file descriptor, socket, or CPU/runtime compatibility errors.

### 6.3. Resources and dependencies

- CPU usage, throttling, and load.
- Heap used/committed, GC pause, and allocation rate.
- RSS, native memory, and container memory peak.
- Thread count, executor queue depth, and scheduler lag.
- Connection pool active/idle/pending and connection creation rate.
- Database latency, saturation, connection count.
- Cache hit/miss, refresh duration, and stale entry count.
- Broker lag, consumer rebalance, and processing delay.

### 6.4. Business quality

- Transaction completion rate.
- Duplicate or idempotency conflict rate.
- Number of duplicate or dropped messages.
- Post-write data verification results.
- Interrupted workflow rate.
- Product-specific metrics such as payment, ordering, or authentication.

A canary with a good HTTP 200 rate that produces duplicate messages or returns stale cache data is still a failing canary.

## 7. Labeling cohorts in metrics, logs, and traces

Every important metric should have labels to distinguish `control` and `crac`. Useful labels typically include:

- **cohort:** `control` or `crac`.
- **release:** application release/build ID.
- **checkpoint_id:** image identifier or version, if cardinality is controlled.
- **restore_attempt:** ID of the restore attempt or instance.
- **instance:** pod/instance ID.
- **region/zone:** deployment region if comparison is needed.

Do not add user ID, session ID, or unbounded-cardinality checkpoint IDs to every metric label. Use traces/logs to store detailed identifiers; metrics should use a controlled label set.

Structured log example:

~~~json
{
  "event": "application.ready",
  "cohort": "crac",
  "release": "2026.11.13",
  "checkpointId": "orders-2026-11-13-a17",
  "instance": "orders-crac-7d8c9",
  "restoreToReadyMs": 1240
}
~~~

This is illustrative data. Do not log credentials, request bodies, or personal data in canary logs.

## 8. Example Prometheus queries to compare cohorts

The metric names below are examples for application instrumentation. Replace them with your system's actual metric names.

### 8.1. Error ratio by cohort

~~~promql
sum by (cohort) (
  rate(http_server_requests_total{status=~"5.."}[5m])
)
/
sum by (cohort) (
  rate(http_server_requests_total[5m])
)
~~~

If the canary has a higher error ratio than control, analyze by endpoint, status code, and exception before deciding to rollback. With very low traffic, a single error can make the ratio swing sharply; combine absolute request counts with observation duration.

### 8.2. p95 latency by cohort

~~~promql
histogram_quantile(
  0.95,
  sum by (le, cohort) (
    rate(http_server_request_duration_seconds_bucket[5m])
  )
)
~~~

You can use `0.99` to view p99 if the histogram has enough buckets and a large enough sample count. Compare the same endpoint or the same request group; mixing endpoints with different latencies can lead to wrong conclusions.

### 8.3. Restore-to-ready duration

~~~promql
histogram_quantile(
  0.95,
  sum by (le, cohort) (
    rate(application_restore_to_ready_seconds_bucket[15m])
  )
)
~~~

This metric is typically only present in the CRaC cohort. You can track p50/p95 by release or image profile, but there is no need to attach high-cardinality image IDs to every series if the system has many images.

### 8.4. Restore failure rate

~~~promql
sum by (cohort) (
  rate(application_restore_failures_total[15m])
)
~~~

This is the failure rate over time, not the failure ratio out of total restore attempts. To get the failure ratio, add a counter for total restore attempts and divide the two metrics over the same labels/window.

### 8.5. CPU and memory

Track CPU usage, CPU throttling, container memory working set, JVM heap, and GC by cohort. If the canary uses fewer replicas than control, normalize by request rate or request count to avoid drawing conclusions from absolute total CPU.

## 9. Setting rollout gates before increasing traffic

Do not increase traffic just because the canary has been running for a certain amount of time. There must be clear conditions on quality and sample size.

A gate typically includes:

- Error rate does not exceed the absolute threshold and is not worse than control beyond the allowed budget.
- p95/p99 does not exceed the SLO or regression budget.
- No critical restore/callback errors.
- Restore-to-ready is within operational targets.
- No OOM, restart loops, or abnormal CPU throttling.
- Dependency saturation does not increase unexpectedly.
- Business metrics show no duplicates, loss, or inconsistency.
- Sufficient requests and observation time have accumulated to conclude.

Example gate table; values must be set according to actual SLOs, not generic thresholds:

| Metric | Condition to increase traffic | Condition to stop/rollback |
|---|---|---|
| HTTP 5xx ratio | Not higher than control beyond the regression budget. | Exceeds error budget or rises continuously across windows. |
| p95/p99 latency | Within SLO and no significant regression. | Exceeds SLO or tail latency rises persistently. |
| Restore success | All attempts in the phase meet the set target. | Restore/callback failures exceed threshold or critical error occurs. |
| Time-to-ready | Within startup/scale-out target. | Past deadline or trends upward with image age. |
| Memory/CPU | Has headroom and does not grow abnormally. | OOM, eviction, throttling, or saturation. |
| Business correctness | No increase in duplicates/loss or data discrepancies. | Any critical correctness error. |

For correctness errors such as duplicate writes, data loss, or wrong access permissions, do not wait for the soak time to finish before rolling back.

## 10. Increasing traffic in steps

An illustrative progression:

| Phase | Traffic to CRaC cohort | Goal |
|---|---:|---|
| Baseline | 0% | Collect control metrics and verify the dashboard. |
| Canary 1 | 1% | Verify routing, readiness, and basic errors. |
| Canary 2 | 5% | Observe first-request, callbacks, and dependencies under light load. |
| Canary 3 | 10% | Check latency/errors and backend load. |
| Canary 4 | 25% | Confirm behavior at substantial load and diverse request types. |
| Canary 5 | 50% | Balanced comparison of both cohorts under identical conditions. |
| Rollout | 100% | Only after all gates and soak times pass. |

This is an example, not a mandatory schedule. For low-traffic systems, 1% may only generate a few requests and not provide enough evidence. In that case, you can use a higher percentage for an internal tenant group or extend the observation period. For high-load systems, start smaller to limit the blast radius.

### 10.1. Soak time and sample size

Each step needs enough time to observe:

- Requests during peak and off-peak hours if load varies over time.
- Cache refresh and TTL cycles.
- Long-interval scheduled tasks.
- Token refresh, connection rotation, or certificate reload.
- Worker/consumer rebalances.
- Business flows that do not occur continuously.

Do not use a 5-minute window to draw conclusions about errors that only occur hourly or daily. Soak time should be based on the system's operational cycles and the risks being tested.

### 10.2. Do not increase traffic when the canary lacks load

If the canary receives too few requests, percentiles and error ratios are unreliable. You can supplement with synthetic probes or replay anonymized workloads to verify functionality, but do not mix synthetic results with production metrics without separate labels.

## 11. Monitoring post-restore quality by phase

Divide the dashboard into three windows: immediately after restore, during the soak phase, and steady state.

### 11.1. Immediately after restore

Monitor:

- Restore success/failure and duration.
- `afterRestore` callback duration by Resource.
- Time to readiness.
- Connection creation, TLS handshake, and authentication failures.
- Cache validation/refresh and number of evicted entries.
- First-request latency and errors.
- CPU/memory peak during recovery.

This is the phase most likely to expose stale sockets, expired credentials, stale caches, or readiness opening too early.

### 11.2. Soak phase

Monitor longer cycles:

- Memory leaks or steadily growing RSS.
- Duplicate scheduler/task execution.
- Retry storms and circuit breakers opening continuously.
- Connection pool leaks or growing pending queues.
- Cache stampedes and abnormal refreshes.
- Message lag or duplicate processing.
- Log/telemetry exporters failing to reconnect.

### 11.3. Steady state

Once the canary is stable, compare p50/p95/p99, throughput, CPU/request, allocation, GC, error ratio, and business metrics against control. If restore gives fast startup but steady-state latency or resource usage is worse, identify the root cause before rolling out broadly.

## 12. Rollback and fallback

Rollback must be prepared before enabling canary traffic. The primary goal is to stop sending new requests to the restored group and ensure the control group has enough capacity.

Basic procedure:

1. Set the canary traffic weight to 0% at the gateway/service mesh.
2. Confirm new requests only go to control.
3. Keep readiness and liveness accurate; do not mass-restart unless necessary.
4. Stop creating new instances from the suspect checkpoint image.
5. Collect logs, traces, metrics, and image metadata for investigation.
6. If needed, drain serving canary instances and terminate them safely.
7. Shift scale/capacity back to the cold-start group to meet traffic.
8. Only re-enable canary after a tested image or fix is ready.

### 12.1. Fallback to cold start

Some platforms can automatically attempt restore and fall back to cold start if restore fails. If using this mechanism, record separate metrics:

- Restore attempts.
- Restore failure reasons.
- Cold-start fallback count.
- Time-to-ready after fallback.

Without separating metrics, the dashboard may show instances eventually becoming ready and hide the restore failure rate. Fallback can also increase CPU load and extend startup, so spare capacity is needed.

### 12.2. Code rollback and shared data

Both cohorts usually share databases and backends. If the canary has written data, shifting traffic back to control does not automatically undo those changes. Therefore:

- Schema migrations must be backward-compatible during the rollout.
- API and event formats must be compatible between both cohorts.
- Write operations need idempotency and auditing.
- Do not let the canary run background jobs that can cause side effects outside traffic routing.
- Have a plan for handling in-flight messages or workflows.

Traffic rollback is a routing operation, not a business data rollback.

## 13. Incident analysis by cohort

When the canary performs worse than control, classify by symptom:

| Symptom | Causes to check |
|---|---|
| Restore-to-ready increases | Slow image distribution, slow callbacks, dependency reconnects, or overly heavy readiness checks. |
| High first-request latency | Lazy initialization, cache misses, unwarmed pools, or un-JITted code paths. |
| 5xx spike right after restore | Stale connections, credentials/TLS, Resource callbacks, or readiness opening too early. |
| p99 increases while p50 is normal | Certain dependency timeouts, pool queueing, GC pauses, or tail requests. |
| CPU increases in canary | Recovery/warm-up re-running, retry storms, compilation, or container throttling. |
| Higher RSS than control | Retained heap state, native memory, thread count, or memory mapping. |
| Duplicate jobs/messages | Consumers or schedulers running concurrently in both cohorts. |
| Cache returns stale data | Cache freshness/version not checked after restore. |
| Restore failure but Pod is still ready | Fallback hiding the error or readiness not reflecting the restore outcome. |
| Errors only on one node | CPU/kernel/CRIU/runtime/storage profile differs from other nodes. |

Compare logs and metrics by cohort, release, `checkpoint_id`, node, and instance. If errors only appear on a group of nodes, check the runtime fingerprint before modifying application code.

## 14. Example rollout decision runbook

A simple runbook can use the following decisions:

| Situation | Action |
|---|---|
| Restore succeeds, readiness met, SLO stable, sufficient samples | Continue soaking, then increase weight by one step. |
| Restore is slow but request quality is good | Keep weight unchanged, investigate callbacks/image distribution before increasing. |
| Restore failure but cold-start fallback succeeds | Keep traffic low or 0%; analyze failure rate and fallback capacity. |
| 5xx or p99 exceeds threshold across multiple windows | Set canary weight to 0%, preserve artifacts, and investigate. |
| Correctness or security error | Rollback immediately without waiting for the soak window to end. |
| Backend dependency saturated due to concurrent restores | Reduce restore concurrency, lower canary weight, and adjust reconnect backoff. |
| Only one CPU/node profile fails | Stop scheduling canary on that profile and check compatibility. |
| Insufficient metrics or dashboard missing cohort labels | Do not increase traffic until observability is fixed. |

Every action needs an owner, timestamp, reason, and related checkpoint/image ID for post-incident auditing.

## 15. Protecting the control cohort and backends during canary

Canary can increase overall load instead of just shifting a portion of traffic, especially when restores trigger concurrent reconnects.

Control the following:

- Number of concurrently restoring instances.
- New connections per second to databases/brokers.
- Warm-up or cache refresh concurrency.
- Retry backoff and jitter.
- CPU/memory headroom on nodes.
- Image distribution throughput.
- Control capacity if the canary is pulled from traffic.

Do not increase canary replica count and traffic weight at the same time if the impact of each change is not yet known. You can first keep the replica count stable and only change routing weight, then test scale-out afterward.

## 16. Reporting canary results

After each phase, save a short, comparable report:

- Release and checkpoint image ID.
- Start/end timestamps, cluster/region, and node profile.
- Traffic weight and actual request count per cohort.
- Restore success/failure and fallback count.
- Restore-to-ready, first-request p50/p95/p99.
- Request error ratio and throughput.
- CPU, memory, GC, connection pool, and backend saturation.
- Business correctness metrics.
- SLO impact and error budget consumed.
- Decision: hold, increase weight, stop, or rollback.
- Open issues and owners.

Do not report only the percentage of shifted traffic. Include request counts, instance counts, and observation duration so readers understand the confidence level of the conclusion.

## 17. Common canary deployment mistakes

**Shifting 100% of traffic right after one successful restore.** A single success does not test real load, cache TTLs, token refreshes, or periodic jobs. Increase in steps with soak time.

**Canary and control running different releases.** When errors occur, it is impossible to separate CRaC's impact from code changes. Keep the release identical during this experiment.

**Not labeling cohorts in metrics.** Dashboards blend both groups and hide regressions. Add cohort/release/image labels with controlled cardinality.

**Only monitoring restore engine duration.** Users care about when the instance serves traffic. Measure restore-to-ready and first-request latency.

**Readiness only checking if the process is alive.** The gateway routes requests before databases/caches/clients are ready. Use readiness based on mandatory dependencies.

**Splitting message consumers like HTTP requests.** Two consumer groups can process the same message. Manage partition ownership or enable only one cohort.

**Rolling back traffic but forgetting background jobs.** Scheduled jobs or consumers in the canary can still write data. Stop or transfer ownership of background workers separately.

**Cold-start fallback hiding restore failures.** Track restore failures and fallback counts separately, not just Pod readiness.

**Increasing canary when backends are overloaded.** Reconnects or cache warm-ups can create traffic spikes. Limit concurrency and monitor dependency saturation.

**Not checking checkpoint age.** Old images may contain stale caches/credentials. Set TTLs and image recreation policies.

## 18. Checklist for canary rollout on a portion of traffic

- [ ] Control and canary run the same application release and business configuration.
- [ ] Checkpoint image has an ID, version, runtime fingerprint, and expiration policy.
- [ ] Real image restore has been tested before entering production.
- [ ] Sufficient control capacity exists to serve if the canary is rolled back.
- [ ] Traffic routing can increase/decrease weight quickly.
- [ ] Cohort is labeled in metrics, logs, and traces.
- [ ] Readiness is false while mandatory Resources have not recovered.
- [ ] Liveness does not falsely restart just because a dependency is temporarily unavailable.
- [ ] Sessions, sticky routing, and multi-step workflows are handled explicitly.
- [ ] Message consumers and scheduled jobs do not run concurrently across both cohorts.
- [ ] SLIs/SLOs and rollout gates exist for error rate, latency, restore success, and correctness.
- [ ] Sufficient sample size and soak time exist for long cycles.
- [ ] First-request, callback duration, restore-to-ready, and steady state are tracked separately.
- [ ] CPU, memory, GC, pools, caches, and backend saturation are monitored.
- [ ] Separate cold-start fallback metrics exist if that mechanism is used.
- [ ] Traffic rollback to 0% canary has been rehearsed.
- [ ] A plan exists to handle side effects and data written during the canary period.
- [ ] Weight is not increased when observability is missing or metrics are insufficient.
- [ ] Reports and checkpoint image IDs are saved for each rollout step.

## 19. Terms to remember

- **Canary rollout:** deploying a version/startup method to a small portion of traffic before expanding.
- **Control cohort:** the baseline group continuing to run the current method, in this article cold start.
- **Treatment cohort:** the experimental group, in this article processes restored from a checkpoint.
- **Traffic weight:** the percentage of traffic the gateway intends to send to each cohort.
- **Sticky routing:** keeping related requests from the same user/session/tenant routed to the same group.
- **SLI:** a metric measuring service quality such as availability, latency, or error rate.
- **SLO:** the quality target set for an SLI over a period of time.
- **Soak time:** the duration a canary percentage is held to observe errors and periodic behavior.
- **Blast radius:** the scope of users or workloads affected if the canary encounters an error.
- **Readiness:** the state in which an instance can receive traffic.
- **Fallback:** switching to a backup startup method, such as cold start when restore fails.
- **Checkpoint age:** the time elapsed from creating a checkpoint image to using it for restore.
- **Cohort label:** a label used to distinguish control and canary in telemetry.
- **Rollback:** stopping the rollout and shifting traffic back to the stable group.

Deploying CRaC on a portion of traffic is the way to validate restore under production conditions with a limited blast radius. Keep the control cohort as a baseline, route the canary with an adjustable ratio, open readiness only after recovery completes, and monitor both request quality and business correctness. Increase traffic in steps once sample size is sufficient and SLOs are stable; if there are critical correctness, restore, or dependency errors, pull the canary from traffic and return to the cold-start cohort while preserving evidence for investigation.

## References

- [CRaC — Checkpoint and restore](https://crac.org/use/checkpoint-and-restore/): the process of creating checkpoints and restoring in deployment environments.
- [CRaC — Best practices](https://crac.org/reference/best-practices/): managing Resources, dependencies, and application state around checkpoint/restore.
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): distinguishing probes and conditions for putting a Pod into service.
- [Istio — Traffic Shifting](https://istio.io/latest/docs/tasks/traffic-management/traffic-shifting/): splitting traffic by weight between versions/services.
- [Google SRE Workbook — Canarying Releases](https://sre.google/workbook/canarying-releases/): canary principles, quality metrics, and rollout decisions.
