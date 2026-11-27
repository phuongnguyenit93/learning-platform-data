# Rolling Updates, Traffic Splitting, and Version Rollback

Containerized applications are typically updated by publishing a new image and gradually replacing running containers. Replacing all instances at once can leave the service unavailable while new containers start; routing a new version to all users without validation lets a single application bug affect the entire system. Therefore, container platforms need to coordinate three mechanisms: **rolling update** to replace workloads step-by-step, **traffic splitting** to control the share of requests sent to each version, and **rollback** to return to a stable version when a rollout misses requirements.

These three mechanisms address different facets of a release. Rolling updates govern replica lifecycles; traffic splitting governs requests reaching each version; rollbacks govern how the application and configuration are restored when faults are detected. They must build on immutable images, readiness, SLI/SLO observability, and data compatibility. This lesson explains how to design and operate a controlled container release workflow in compute environments.

## 1. Goals of a Safe Update

A sound deployment should achieve the following goals:

- Maintain enough healthy replicas throughout version replacement.
- Send traffic only to containers ready to process requests.
- Limit the blast radius of a new version.
- Detect faults via metrics, logs, traces, and health checks.
- Have clear rollout stop criteria and a defined rollback procedure.
- Ensure old and new versions can coexist during the transition window.
- Avoid corrupting data or in-flight transactions.
- Identify the exact image, config, and release running on every replica.

Zero downtime cannot be guaranteed merely by picking rolling updates. The application must support graceful shutdown, accurate readiness, compatible sessions, and backward-compatible dependencies. If every replica fails simultaneously due to a database migration or shared configuration, a rolling update can still cause an outage.

## 2. Shared Terminology

| Concept | Meaning |
|---|---|
| Release | An application release along with its image, configuration, and associated metadata |
| Image tag | A reference name for an image, e.g., `checkout:2.4.1` |
| Image digest | An immutable content-based image identifier, e.g., `sha256:...` |
| Replica | A running copy of a workload, typically a container or Pod |
| ReplicaSet | Kubernetes controller maintaining a Pod count from a Pod template |
| Deployment | Kubernetes resource managing rollouts and ReplicaSets for stateless apps |
| Readiness | Signal indicating an instance can receive traffic |
| Rollout | Process of transitioning a workload from the current version to a new version |
| Canary | Releasing a new version to a small slice of traffic before expanding |
| Blue-green | Maintaining two environment/version groups and switching traffic from old to new |
| Rollback | Reverting to a known stable release |
| Roll forward | Shipping a subsequent fix release to resolve a fault |

Record the release ID, image digest, source revision, deploy timestamp, and initiating user or automation. Mutable tags like `latest` can change over time; using digests or immutable version tags pinpoints the exact deployed artifact.

## 3. How Rolling Updates Work

A rolling update replaces old replicas in batches. The orchestrator creates a batch of new replicas, waits for them to become ready, and scales down old replicas. This repeats until the entire workload runs the new version.

~~~mermaid
flowchart TD
    A[4 replicas on version v1] --> B[Create 1 v2 replica]
    B --> C[Wait for v2 readiness]
    C --> D[Terminate 1 v1 replica]
    D --> E[Create next v2 replica]
    E --> F[Wait for readiness then remove v1]
    F --> G[Complete: 4 replicas on v2]
~~~

During the transition window, old and new versions coexist. This preserves capacity, but requires both versions to stay compatible with the same database, message schemas, caches, and API contracts.

### 3.1. MaxSurge and MaxUnavailable

In a Kubernetes Deployment, `maxSurge` caps how many Pods can be created above the desired replica count during a rolling update; `maxUnavailable` caps how many Pods can be unavailable during the update.

For example, a Deployment with 4 replicas:

- `maxSurge: 1` allows creating at most 1 Pod beyond the desired replica count.
- `maxUnavailable: 1` allows at most 1 Pod to be unavailable per the Deployment's rollout accounting.
- Configuring `maxSurge: 1`, `maxUnavailable: 0` prioritizes keeping full available capacity, though it requires spare cluster capacity to schedule the new Pod.

Kubernetes typically defaults both values to 25% if unspecified, but declare them explicitly based on capacity and SLOs. Percentages follow Kubernetes rounding rules; for workloads with few replicas, the resulting Pod counts can be unintuitive.

Avoid setting a high `maxSurge` if the cluster lacks CPU/RAM or quota to schedule extra Pods. Conversely, setting `maxUnavailable` too high can shrink serving capacity during a rollout.

## 4. Readiness, Liveness, and Startup Probes

Rolling updates are safe only if the orchestrator knows when a new container can take traffic.

- **Startup probe:** gives the application time to boot; liveness and readiness are not evaluated normally until the startup probe passes.
- **Readiness probe:** determines whether a Pod is eligible to receive requests.
- **Liveness probe:** determines whether a container must be restarted because it is no longer functioning properly.

Readiness should not check only whether the process is alive or a port is open. If the app has not finished loading config, connecting to critical dependencies, or warming up, it may return errors even with an open port.

Liveness should not depend on a flaky external service. If a database blips and liveness fails across all Pods, Kubernetes may mass-restart containers even though restarting cannot fix a dependency outage.

Example probe configuration in a Pod template:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-api
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  minReadySeconds: 10
  progressDeadlineSeconds: 600
  revisionHistoryLimit: 5
  selector:
    matchLabels:
      app: checkout-api
  template:
    metadata:
      labels:
        app: checkout-api
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: api
          image: registry.example.com/checkout-api@sha256:REPLACE_WITH_DIGEST
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /health/startup
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 10
            failureThreshold: 3
~~~

This is an illustrative template. Replace the registry, digest, endpoints, and thresholds for your application. Overly aggressive probes can trigger restart loops or flap Pods out of Service endpoints; overly lenient probes can route requests to unhealthy Pods.

## 5. Graceful Shutdown and Traffic Draining

When a Pod is replaced, the old container needs time to finish in-flight requests. If the process is killed immediately, clients can see connection resets, partially processed requests, or workers dropping messages.

A typical shutdown flow includes:

1. Mark the instance unready.
2. Wait for the endpoint controller, proxy, or load balancer to update backends.
3. Stop accepting new requests/jobs.
4. Complete in-flight requests within the allowed time window.
5. Stop consumers from pulling new messages; finish or safely requeue active jobs.
6. Flush logs, close connections, and release resources.
7. Exit before the termination grace period expires.

In Kubernetes, `terminationGracePeriodSeconds` sets the time limit for terminating a Pod. Any `preStop` hook runs inside that grace period; hook duration is not added on top of the limit. After the deadline, the container can be forcibly killed.

Verify that the application actually handles `SIGTERM`. Simply extending the grace period will not fix a process that ignores graceful shutdown or requests without timeouts.

## 6. Rolling Out a Deployment on Kubernetes

Commonly used commands:

~~~bash
# Apply the new manifest
kubectl apply -f deployment.yaml

# Watch rollout progress
kubectl rollout status deployment/checkout-api

# View revision history
kubectl rollout history deployment/checkout-api

# Inspect details of a specific revision
kubectl rollout history deployment/checkout-api --revision=3

# List Pods by label
kubectl get pods -l app=checkout-api -o wide

# Inspect events and why a Pod is not ready
kubectl describe deployment checkout-api
kubectl describe pod POD_NAME
~~~

`kubectl rollout status` reports rollout progress from the Deployment's perspective. Completion does not replace checking business logic, latency, error rates, or data. Keep observing after every replica has moved to the new version.

### 6.1. MinReadySeconds and Progress Deadline

`minReadySeconds` requires a Pod to stay continuously Ready for a set duration before the Deployment counts it as available. This reduces the risk of treating a Pod that only passed readiness momentarily as stable.

`progressDeadlineSeconds` limits how long a Deployment may make no progress. Once exceeded, the Deployment can report `ProgressDeadlineExceeded`; the controller does not automatically roll back solely because this condition triggers. Release pipelines must detect this state and trigger halt/rollback decisions per policy.

### 6.2. What Role Does PodDisruptionBudget Play?

A `PodDisruptionBudget` (PDB) limits how many Pods can be disrupted during voluntary disruptions routed through the eviction API, such as draining a node. PDBs are useful for node maintenance and certain orchestration actions, but they do not replace `maxSurge`, `maxUnavailable`, readiness, or Deployment rollout capacity planning. Do not assume a PDB automatically protects every rollout performed by the Deployment controller.

## 7. Traffic Splitting Across Versions

Rolling updates replace replicas via controller progression. Traffic splitting actively controls what proportion of requests goes to different versions. The two approaches can be combined, though they are not synonymous.

For example, the stable version receives 95% of requests and the canary version receives 5%. If the canary meets SLOs, its share can be raised gradually.

~~~mermaid
flowchart LR
    C[Client traffic] --> R[Ingress / Gateway / Service Mesh]
    R -->|95%| S[Stable v1]
    R -->|5%| K[Canary v2]
    S --> M[Metrics and traces]
    K --> M
    M --> D{SLOs met?}
    D -->|Yes| P[Increase canary weight]
    D -->|No| X[Stop canary and roll back]
~~~

Ways to implement traffic splitting:

- Gateways or ingresses supporting weighted routing.
- Service meshes with subset/version-based traffic policies.
- Global traffic managers when versions span clusters or regions.
- Feature flags enabling new behavior for selected user cohorts.
- Header/cookie routing for controlled testing.

Weight support and splitting precision depend on the controller, proxy, and platform. Some setups split per connection rather than per request; keep-alive or HTTP/2 multiplexing can make observed request ratios diverge from connection weights.

### 7.1. Stepwise Canary Release

An illustrative progression plan:

| Stage | Canary Share | Promotion Criteria |
|---|---:|---|
| Start | 1% | Smoke tests and health checks pass |
| Step 2 | 5% | Error rate and latency stay within thresholds |
| Step 3 | 10% | No abnormal business or dependency errors |
| Step 4 | 25% | p95/p99, throughput, and resource utilization healthy |
| Step 5 | 50% | No meaningful regressions |
| Complete | 100% | SLOs met over the defined observation window |

Percentages and durations are examples only. With low request volume, 1% may yield too few samples to draw conclusions. Ensure enough requests, enough observation time, and coverage across key user/workload segments.

### 7.2. Choosing User Cohorts for a Canary

Canaries can target:

- A random percentage of requests.
- A set of internal users or accounts.
- Headers or cookies sent by test clients.
- Specific regions, tenants, or workload types.
- A batch of replayable background jobs.

Never put the most sensitive user group into the initial canary. For data writes or payments, require idempotency, auditing, and blast-radius caps. A canary is not the place to test changes that could cause data loss.

### 7.3. Sticky Routing and Sessions

If the same user bounces back and forth between two versions, local sessions or caches may be incompatible. Sticky routing keeps a user pinned to one version during the experiment, though it can skew traffic distribution.

Stateless applications or compatible shared session stores make traffic shifting safer. When sticky routing is required, define fallback behavior if a backend fails, cookies expire, or the version is rolled back.

## 8. Blue-Green Deployment

Blue-green maintains two environment groups:

- **Blue:** the version currently serving production traffic.
- **Green:** the new version, deployed and tested.

Once Green passes readiness and smoke tests, the load balancer or service router switches traffic from Blue to Green. If errors emerge, traffic can be switched back to Blue while Blue remains available.

~~~mermaid
flowchart TD
    U[Users] --> L[Load balancer]
    L -->|Before cutover| B[Blue: version v1]
    L -.->|After cutover| G[Green: version v2]
    G --> H[Health and smoke tests]
    H --> D{Meets criteria?}
    D -->|Yes| C[Switch all traffic to Green]
    D -->|No| R[Keep or revert to Blue]
~~~

Advantages:

- Allows testing the new version before it takes live production traffic.
- Fast traffic cutover when endpoints and data are compatible.
- Easy fallback to the old group during the rollback window.

Trade-offs:

- Requires capacity for both groups to coexist.
- Databases and queues may be accessed concurrently by both versions.
- Sessions, caches, and side effects must remain compatible.
- Blue cannot be torn down too early while rollback might still be needed.

Blue-green can use two Deployments/Services in Kubernetes, two node pools, two clusters, or two isolated environments. Blue and Green are logical labels; exact implementation varies by platform.

## 9. Comparing Rolling, Canary, and Blue-Green

| Criterion | Rolling update | Canary | Blue-green |
|---|---|---|---|
| How versions swap | Gradually replaces replicas | Opens a small traffic slice to new version, then ramps up | Prepares new group, then switches traffic |
| Traffic control | Usually driven by readiness and rollout strategy | Explicit weights or user cohorts | Switches traffic between two groups |
| Temporary capacity | Needs surge capacity per config | Runs stable and canary side-by-side | Can require nearly double capacity |
| Fault detection | Via rollout status and telemetry | Via stable vs. canary comparison | Via pre- and post-cutover testing |
| Rollback speed | Depends on rollout and revision speed | Halt canary, drop weight to 0 | Switch traffic back to Blue |
| Best suited for | Compatible changes, frequent releases | Changes needing validation under live traffic | Releases needing fast cutover or isolated pre-cutover testing |

No single strategy fits every case. Rolling updates are simpler and more capacity-efficient in many scenarios. Canary fits when measuring impact under live traffic matters. Blue-green fits when testing a new stack in isolation is required and spare capacity is available for both groups.

## 10. Measurement and Automated Rollout Stop Criteria

Never judge a rollout solely by Pod Ready status. Monitor metrics across both stable and canary versions:

- Request rate and successful throughput.
- Error rate broken down by status code and business error type.
- p50/p95/p99 latency.
- CPU, memory, throttling, and restart counts.
- Queue depth, message age, and retries.
- DB connection pools, query latency, and lock waits.
- Dependency timeouts and circuit breaker open counts.
- Node, network, and storage saturation.
- Business metrics such as completed transactions, successful orders, or payment success rate.

A canary policy might require:

- Error rate does not exceed baseline beyond the allowed margin.
- p95/p99 latency does not rise past defined bounds.
- Zero correctness or data integrity failures.
- No OOMs or restart loops.
- No abnormal spikes in retries, queue age, or dependency saturation.
- Sufficient request count and minimum observation duration.

Compare canary against stable concurrently to minimize the impact of load fluctuations. Comparing against an old historical baseline can mislead if demand or dependencies have shifted.

### 10.1. Separating Version Faults from System-Wide Faults

If both stable and canary show rising latency, the culprit may be the database, network, or overall traffic. If errors rise only on canary, a regression in the new version is much more likely. Use version/release labels in metrics and traces to segment the two cohorts.

Avoid using user IDs or high-cardinality values as metric labels if your telemetry stack cannot handle them; that inflates cost and ingestion load. Keep high-detail identifiers in controlled logs and traces instead.

## 11. Schema and Contract Compatibility While Two Versions Coexist

During a rolling update or canary, v1 and v2 may access the same database or queue concurrently. Breaking schema changes can break the old version the moment the new version begins rolling out.

A safe workflow commonly uses the **expand and contract** pattern:

1. **Expand:** add new columns/tables/fields in a backward-compatible manner.
2. **Deploy compatible code:** the new version can read old data and write new data per defined rules.
3. **Migrate data:** backfill or transform records in controlled batches.
4. **Switch usage:** gradually move code over to the new fields/schema.
5. **Contract:** remove old fields or structures only after all old versions have stopped using them and the rollback window has closed.

For message queues, version events/schemas or design consumers to accept both old and new formats. For APIs, avoid breaking contracts for clients still running older versions.

Application rollback does not automatically roll back database migrations. If the new schema already accepted incompatible data, reverting to the old image may leave the old app unable to read those rows. Design and test dedicated migration rollbacks or forward-fixes separately.

## 12. Managing Configs, Secrets, and Artifacts

A release is more than just a container image. It also includes:

- ConfigMaps or application configurations.
- Secrets and identity bindings.
- Environment variables.
- Service accounts and permissions.
- Network policies and service routing.
- Database migration versions.
- Feature flags.
- Resource requests/limits and autoscaling policies.

Version configurations alongside releases or manage config changes through an auditable workflow. Never edit an active ConfigMap in place without tracking it; Pods may fail to pick up changes or replicas may read different configs at different times.

Use image digests to ensure every replica runs the exact same artifact. Avoid mutable tags like `latest` in production releases unless pinned by digest. Retain old images in the registry long enough for rollbacks while complying with vulnerability scanning policies.

## 13. Rolling Back on Kubernetes

If a rollout introduces a regression, inspect history and revert to a prior revision:

~~~bash
# View revision history
kubectl rollout history deployment/checkout-api

# Check rollout status
kubectl rollout status deployment/checkout-api

# Revert to the previous revision
kubectl rollout undo deployment/checkout-api

# Revert to a specific revision
kubectl rollout undo deployment/checkout-api --to-revision=3

# Verify version and Pod status
kubectl get deployment checkout-api -o wide
kubectl get rs -l app=checkout-api
kubectl get pods -l app=checkout-api -o wide
~~~

`kubectl rollout undo` reverts the Deployment's Pod template to a prior revision in retained history. It does not restore databases, messages, external secrets, object storage data, or already-executed side effects. If revision history was pruned or releases are GitOps-managed, execute rollbacks through the authoritative declarative source.

### 13.1. Rollbacks in GitOps

When Git is the source of truth, manual changes via `kubectl rollout undo` may be overwritten when the GitOps controller reconciles back to the repository state. In that setup, perform rollbacks by reverting the commit or selecting a stable manifest/image digest in Git and letting the controller sync.

Establish a single control authority for rollouts. Avoid having CI/CD, GitOps, and ad-hoc manual commands modify the same Deployment without clear ownership rules.

## 14. Controlled Rollback Procedure

When deciding to roll back:

1. Halt any further traffic ramp-up to the new version.
2. If using canary, set canary weight to 0 or route traffic back to stable.
3. If using rolling update, pause/stop the rollout via the release controller and restore the stable Pod template.
4. Confirm old replicas have sufficient capacity and pass readiness.
5. Verify schema/database compatibility before shifting 100% of traffic back.
6. Monitor in-flight requests, queues, and transactions.
7. Confirm error rates, latency, and business metrics return to baseline.
8. Preserve logs, traces, image digests, and release metadata for investigation.
9. Document root cause, blast radius, and remediation steps.
10. Re-release only after implementing a fix and passing required tests.

If the new version ran a breaking migration or caused irreversible side effects, a naive rollback can make things worse. In such cases, you may need to roll forward with a compatible fix or execute a dedicated data recovery runbook.

## 15. Handling Open Traffic and Long-Lived Connections

Load balancers typically pick a backend when establishing a connection or per request depending on service type. During version swaps:

- HTTP keep-alive can pin connections to old backends.
- HTTP/2 can multiplex many requests over one connection.
- WebSockets and gRPC streams can outlive the rollout window.
- TCP sessions do not automatically migrate to new containers when an old backend exits.

Applications need drain deadlines, connection-close notifications, and client reconnect/resume support where appropriate. Streaming or WebSockets may require longer overlap periods than short-lived HTTP requests. Size `terminationGracePeriodSeconds` to match real application behavior and gateway timeouts.

For queue workers, acknowledge messages only after results are durably persisted. If stopped mid-job, checkpoint or requeue per broker semantics and design idempotency for safe reprocessing.

## 16. Rollouts for Stateful Workloads

Deployment rolling updates are better suited to stateless applications. For StatefulSets, databases, brokers, or volume-attached workloads:

- Define update ordering and quorum requirements.
- Check leader/primary and replica health.
- Verify protocol and on-disk format version compatibility.
- Verify backups and restores before risky changes.
- Monitor replication lag and failover readiness.
- Avoid updating too many quorum members simultaneously.
- Verify volume attachments, filesystems, and storage classes.
- Maintain a vendor-supported downgrade path; some software does not support downgrading on-disk data formats.

Do not apply a generic rolling update manifest to every container type. Databases and distributed systems require product-specific upgrade runbooks.

## 17. Example Release Pipeline with Canary and Rollback

A reference pipeline:

~~~mermaid
flowchart TD
    A[Build image] --> B[Scan and test image]
    B --> C[Push image, record digest]
    C --> D[Deploy canary]
    D --> E[Readiness and smoke tests]
    E --> F[Shift 5% traffic]
    F --> G[Evaluate SLI/SLO]
    G --> H{Within thresholds?}
    H -- No --> I[Set weight to 0 and roll back]
    H -- Yes --> J[Step traffic upward]
    J --> K{At 100% and stable?}
    K -- No --> I
    K -- Yes --> L[Promote release]
    L --> M[Retain old revision for rollback window]
~~~

Record metadata at every step: commit SHA, image digest, config version, database migration ID, canary weight, start/end timestamps, and evaluation results. This makes decisions reproducible and identifies the exact active release.

### 17.1. Example Release Policy

| Condition | Action |
|---|---|
| Image scan or mandatory tests fail | Do not deploy |
| Canary fails readiness/smoke tests | Halt rollout |
| Error rate exceeds threshold consecutively | Shift traffic back to stable |
| p99 breaches threshold during observation window | Pause weight increase, investigate |
| Data integrity failure detected | Roll back / trigger incident response immediately per runbook |
| SLOs remain healthy across steps | Increase weight |
| 100% traffic and sufficient observation time | Mark release complete |

Thresholds must align with service SLOs and baselines. Avoid triggering automated rollbacks on a brief spike or single failed probe; require observation windows, minimum sample counts, and multiple independent signals.

## 18. Common Mistakes During Container Updates

**Readiness passes too early.** Traffic hits Pods before the app is ready. Verify critical dependencies and startup state.

**Using mutable tags.** Replicas may pull different images at different times. Pin digests for every release.

**maxSurge exceeds cluster capacity.** New Pods stay Pending and stall the rollout. Check quotas, node capacity, affinity rules, and the cluster autoscaler.

**maxUnavailable too high.** Serving capacity drops below safe levels. Calculate against replica count, peak load, and failure scenarios.

**Liveness depends on the database.** Database hiccups cause all Pods to restart continuously. Separate liveness from readiness and dependency health.

**Failing to drain long-lived connections.** Requests or streams drop mid-flight. Use graceful shutdown, deadlines, and client reconnect logic.

**Too few canary samples.** A tiny traffic slice for a short window misses rare bugs. Increase duration or sample volume based on real traffic.

**Comparing canary and stable across different time windows.** Load shifts or dependency jitter skew conclusions. Compare side-by-side and normalize workloads.

**Rolling back the image while forgetting the schema.** The old version cannot parse new data. Use expand-and-contract and test rollbacks.

**GitOps overwrites manual rollbacks.** The controller restores the broken config. Perform rollbacks through the authoritative declarative source.

**Deleting old ReplicaSets/images too soon.** Loses fast rollback capability. Retain revisions and artifacts throughout the rollback window.

## 19. Pre-, Mid-, and Post-Rollout Checklist

### Pre-Rollout

- [ ] Image tested, scanned, and pinned by digest.
- [ ] Release records commit SHA, config version, and clear owner.
- [ ] Readiness, liveness, and startup probes tested.
- [ ] `maxSurge`, `maxUnavailable`, capacity, and quotas calculated.
- [ ] Old and new versions are API-, database-, and message-schema-compatible.
- [ ] Expand-and-contract migration plan prepared.
- [ ] Graceful shutdown, draining, and termination grace period properly sized.
- [ ] Baseline metrics, logs, traces, and SLOs available for comparison.
- [ ] Prior revision/image and rollback runbook ready.

### During Rollout

- [ ] Monitor rollout status and Pod events.
- [ ] Route traffic only to Ready replicas.
- [ ] Watch error rates, p95/p99, throughput, and resource saturation.
- [ ] Ramp canary weights incrementally with adequate sample sizes.
- [ ] Watch database, queue, and dependency metrics.
- [ ] Halt traffic increases if thresholds breach.
- [ ] Do not delete old versions before the rollback window closes.

### Post-Rollout

- [ ] 100% traffic on new version with adequate observation time.
- [ ] Business metrics and data integrity verified.
- [ ] No abnormal backlogs or retries.
- [ ] Release metadata and outcomes recorded.
- [ ] Rollback artifacts and revisions retained per policy.
- [ ] Post-release review conducted if a regression or rollback occurred.

## 20. Conclusion

Rolling updates swap replicas step-by-step to preserve capacity; traffic splitting controls request ratios between stable and new versions; rollbacks return the service to a stable release when a rollout falls short. Coordinating these three mechanisms requires pinning images by digest, configuring readiness/startup probes accurately, sizing `maxSurge` and `maxUnavailable`, draining connections, monitoring SLOs, and keeping data compatible between old and new versions.

Choose rolling updates for compatible changes and straightforward workflows; use canary releases when live-traffic validation is needed; use blue-green when isolated testing of a new stack is required and spare capacity is available. A rollback must cover routing, application artifacts, configurations, and data plans. A release is complete only when the new version serves reliably, business logic behaves correctly, and every artifact is fully traceable.
