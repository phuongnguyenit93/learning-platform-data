# Understanding Blue-Green Deployment and Traffic Cutover Timing

Blue-green deployment is a deployment strategy that maintains two parallel environments: **blue**, which is currently serving users, and **green**, which holds the new version being prepared. Once green has been deployed, verified, and meets release criteria, the system switches traffic from blue to green. If the new version encounters issues, the team can switch traffic back to blue quickly, provided data and dependencies remain compatible.

The decisive part of blue-green is not merely having two versions running simultaneously. What matters is **choosing the right moment for traffic cutover**: green must be sufficiently ready, checks must be meaningful, data risks must be controlled, and the team must know what conditions will trigger a rollback.

This is part of the **DEVOPS_CI_CD_FUNDAMENTALS** capability: building CI/CD discipline from Git events, pipelines as code, automated build and testing through artifact management, environments, quality gates, traceable releases, post-deployment verification, and rollback capability.

## 1. What is blue-green deployment?

Blue and green are two environment versions capable of running the application independently. Color names are merely a convention; they can also be called stable/candidate, current/next, or v1/v2.

- **Blue:** the current version actively receiving production traffic.
- **Green:** the new version already deployed but not yet receiving primary production traffic.
- **Traffic router:** the component deciding whether requests go to blue or green, such as a load balancer, ingress, reverse proxy, service mesh, or DNS.

General flow:

~~~mermaid
flowchart TD
    U["Users"] --> R["Load balancer / traffic router"]
    R --> B["Blue: current version"]
    R -. "After cutover" .-> G["Green: new version"]
    B --> DB[("Shared database")]
    G --> DB
    G --> V["Readiness, smoke tests, and verification"]
    V --> D{"Ready to switch traffic?"}
    D -- "Not yet" --> G
    D -- "Passed" --> R
~~~

Before cutover, blue continues serving users while green is provisioned and verified. After cutover, green receives new requests. Blue is typically kept around for a period to enable fast rollback, and only afterward is decommissioned or reused for the next deployment.

Blue-green can use two VM clusters, two container groups, two Kubernetes Deployments, two App Service slots, or two target groups behind a load balancer. Specific implementation details vary by platform, but the principles of readiness, routing, data, and rollback remain the same.

## 2. What problem does blue-green solve?

Deploying directly onto the live serving environment can create a window where users encounter an unstable version, old and new instances handle requests inconsistently, or rollback requires re-modifying individual machines.

Blue-green helps:

- Prepare and verify the new version before users officially receive traffic on it.
- Switch traffic through a single centralized control point.
- Reduce outage duration when cutover is well-designed.
- Keep the old version ready for fast rollback.
- Test the new version in a production-like environment before switching.
- Decouple binary deployment from the moment users start receiving that version.

Blue-green does not automatically guarantee zero downtime. Open connections, sessions, caches, database schemas, background workers, and supporting systems can complicate the transition. If the two versions are incompatible with shared data, switching traffic or rolling back can still cause failures even when routing works properly.

## 3. Comparing blue-green with rolling and canary

All three strategies reduce release risk, but they control traffic differently:

| Strategy | How versions are replaced | How traffic shifts | Key strengths | Main limitations |
| --- | --- | --- | --- | --- |
| Blue-green | Provision a full new environment alongside the current one | Shift a large share or all traffic at the router | Fast cutover and rollback if the system is compatible | Requires capacity for two environments and control over shared data |
| Rolling | Replace old instances in batches with new instances | Traffic gradually passes through both old and new instances during rollout | No need to maintain two full environments | Two versions serve concurrently for a period; rollback may take longer |
| Canary | Deploy the new version to a small subset | Increase the traffic share to the new version in steps | Measures behavior on live traffic with a small blast radius | Requires strong routing/metrics and can extend the period where two versions coexist |

Blue-green can be combined with canary: green is fully provisioned, and then the router sends a small percentage of traffic to green before switching completely. When people say blue-green, it does not necessarily mean shifting 100% of traffic in one operation; that depends on router capabilities and release policy.

Choose a strategy based on architecture, observability, resource cost, risk level, and recovery requirements. If the system cannot run two versions concurrently due to licensing, data, or resource limits, blue-green may not fit.

## 4. Prerequisites before creating green

Blue-green must be designed across both the pipeline and application architecture, not merely tacked on as a route swap at the end.

### 4.1. Artifacts must be immutable and traceable

Build the artifact once from a specific commit, run tests and quality gates, and then deploy that exact artifact to green. Do not rebuild a different version during production deployment just to change configuration.

Record:

- Source repository and commit SHA.
- Artifact version and digest.
- Build run ID and build provenance if available.
- Deployment configuration and manifest version.
- Image digest or package checksum.
- Test, scan, and quality gate results.

Once green is verified and traffic shifts, blue-green must know exactly which version is running on each color. On rollback, the team needs to know which artifact blue points to and whether that artifact still exists in the registry.

### 4.2. Blue and green environments must match on critical dimensions

Both environments need equivalent configuration for:

- Runtime, operating system, CPU architecture, and compute resources.
- Network policies, DNS, firewalls, and outbound access.
- Secrets, certificates, and service permissions.
- Feature flags and application configuration.
- Connections to databases, caches, message brokers, and object storage.
- Observability: logs, metrics, tracing, and alerts.

Every config value does not have to be identical, but differences must be declared and justified. If green uses different database settings or permissions from blue, smoke tests must verify the exact configuration that will be used after cutover.

### 4.3. Resources and capacity

During preparation, blue and green coexist, so CPU, memory, connection pools, nodes, and quotas may nearly double for the duplicated components. Also account for auxiliary resources such as database connections, broker consumers, cache namespaces, and licenses.

If green scales up fully before cutover while the database lacks enough connections, the preparation phase itself can slow down blue. Check limits and set appropriate quotas before running both environments concurrently.

## 5. States in a blue-green release

A release can be modeled with explicit states:

| State | Blue | Green | Traffic |
| --- | --- | --- | --- |
| Stable | Serving | Not created or stopped | 100% to blue |
| Provisioning | Serving | Creating | 100% to blue |
| Validating | Serving | Running, under test | Production stays on blue; isolated tests hit green |
| Ready | Serving | Passed checks | Not cut over yet or receiving canary traffic |
| Switching | Serving | Qualified | Router shifting per plan |
| Green active | Retained for rollback | Serving | New traffic goes to green |
| Rollback | Re-activated | Isolated or under investigation | New traffic returns to blue |
| Retired | Removed or reused | Becomes the old version next time | Only one environment active |

Do not treat container `Running` status as `Ready`. Define explicit state transition criteria and persist results so operators know which step the pipeline is in.

## 6. Deploying green before switching traffic

A green deployment sequence typically includes:

1. Identify the artifact digest and release configuration.
2. Verify quality gates, provenance, signatures, and scans per policy.
3. Provision green resources from reviewed manifests or infrastructure-as-code.
4. Provide environment-appropriate secrets, network rules, and access permissions.
5. Run compatible migrations if needed.
6. Start application instances and wait for readiness.
7. Run smoke tests directly against green via internal endpoints.
8. Verify logs, metrics, tracing, and dependencies.
9. Evaluate capacity and cutover criteria.

During this phase, blue still receives production traffic. Do not let green automatically send emails, process payments, emit events, or run scheduled jobs alongside blue simply because green has started. Tasks with side effects need leader election, feature flags, or workers disabled on the inactive environment.

### 6.1. Readiness, liveness, and smoke tests

These three checks serve distinct purposes:

- **Liveness:** the process is still running and not deadlocked to the point of needing a restart.
- **Readiness:** the instance can accept production requests; mandatory dependencies are ready.
- **Smoke test:** a small set of operations verifying that critical workflows actually function.

A health endpoint returning HTTP 200 alone may be insufficient. Green could report health success yet fail to write to the database, fetch secrets, connect to the broker, or load required models/configs.

Smoke tests should verify meaningful behavior, for example:

- Read endpoints return the expected structure.
- A test write in a test data region persists and reads back cleanly.
- The application authenticates with dependencies.
- A critical flow completes within the allowed latency.
- No severe errors appear in startup logs.

Avoid smoke tests that generate real transactions, send real emails, or emit events with irreversible side effects. Use test accounts, isolated test data, or dry-run modes when available.

## 7. When should traffic be switched?

Do not switch traffic merely because the deployment job finished or containers are Running. Green should only be considered eligible when all predefined criteria pass.

A cutover decision should check:

### 7.1. Green is technically ready

- All required instances are Ready.
- Configuration and secrets are loaded properly.
- Database migrations and dependency initialization have completed.
- Smoke tests on green pass.
- No startup errors or crash loops.
- Logs and metrics are flowing into observability systems.

### 7.2. Change risk has been evaluated

- Artifact digest matches the tested and approved build.
- Quality gates, vulnerability policies, and provenance pass requirements.
- Database schema is compatible with both blue and green during the transition.
- Feature flags and side effects are controlled.
- A rollback plan has been tested or appropriately rehearsed.

### 7.3. Post-cutover observability is ready

Before switching, dashboards and alerts must be ready to monitor:

- Request success and error rates per version.
- p50/p95/p99 latency.
- Timeout and connection error rates.
- CPU, memory, threads, connection pools, and saturation.
- Database query latency, locks, and connection counts.
- Queue lag, consumer errors, and retries.
- Business metrics such as orders created, successful payments, or completed transactions.

In particular, there must be a way to distinguish traffic going to blue vs. green. If metrics are only aggregated system-wide, errors on green can be masked by the volume of requests blue continues handling well.

### 7.4. Predefine decision thresholds

Set thresholds before cutover based on SLOs, baselines, and service criticality. For example, the team may specify:

- Error rate does not exceed the approved threshold during the observation window.
- Latency stays within SLO limits or adjusted baselines.
- Zero critical business errors occur.
- No crash loops or sustained saturation.
- Queue lag and database connections stay within bounds.

Do not use one uniform number across every system. A payment API, a content page, and a batch worker have different load characteristics. Thresholds must reflect the risk level the organization accepts.

**The right time for cutover** is when green has passed technical and business checks, data is compatible, the router can switch in a controlled way, and operators have enough signals to detect failures and decide on rollback.

### 7.5. Choosing an operational window

Once green meets technical criteria, pick the cutover time based on load schedules and operational support coverage:

- Prefer windows with sufficient on-call staff to monitor and make decisions.
- Avoid overlapping with large batch jobs, financial close, billing cycles, or anomalous traffic events if those increase risk.
- Confirm supporting systems and dependent teams are in a stable state.
- Notify on-call responders and dependent teams of the cutover time, halt criteria, and rollback authority.
- Leave adequate time for the post-cutover observation window before starting another major change.

Choosing low-traffic hours can reduce the number of affected users if a rollback is needed, but it does not replace readiness, smoke tests, capacity checks, or monitoring. For continuously operating services, cutover can occur at any time if the system is ready and operators can respond.

## 8. How to switch traffic

The traffic router is the central control point of blue-green. Common mechanisms:

| Mechanism | How traffic shifts | Notes |
| --- | --- | --- |
| Load balancer target group | Swap target groups or change weights from blue to green | Can support connection draining and health checks |
| Kubernetes Service selector | Change label selector so the Service targets green pods | Requires readiness probes and awareness of endpoint update delay |
| Ingress/reverse proxy | Update upstream or backend service | May require reload and propagation time |
| Service mesh | Update routing rules / virtual service | Can support weights and canary before full cutover |
| DNS | Change record from blue to green | DNS caching and TTL make cutover non-instantaneous |
| Platform slot | Swap slots or switch backend via platform mechanism | Depends on session behavior, storage, and slot configuration |

With a load balancer or service mesh, you can start with a small percentage of traffic to green and increase gradually. With DNS, do not assume updating a record moves every client immediately; resolvers and clients can cache addresses longer than the TTL.

### 8.1. Kubernetes Service selector example

Suppose two Deployments create pods sharing the label app=orders-api, but differing in the track label:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api-blue
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
      track: blue
  template:
    metadata:
      labels:
        app: orders-api
        track: blue
    spec:
      containers:
        - name: api
          image: registry.example.com/orders-api@sha256:BLUE_IMAGE_DIGEST
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            periodSeconds: 5
            failureThreshold: 3
~~~

The green Deployment has the same structure but is named orders-api-green, with label track green and the new version's image digest. The Service initially selects blue:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: orders-api
spec:
  selector:
    app: orders-api
    track: blue
  ports:
    - name: http
      port: 80
      targetPort: 8080
~~~

Once green passes readiness and smoke tests, you can switch the selector:

~~~bash
kubectl patch service orders-api \
  --type merge \
  -p '{"spec":{"selector":{"app":"orders-api","track":"green"}}}'
~~~

The Service updates EndpointSlices to select the matching green pods. Endpoint updates and existing connections have latency; do not treat a successful patch return as proof that all traffic has shifted. Observe live requests and verify routing via metrics/logs.

`BLUE_IMAGE_DIGEST` and `GREEN_IMAGE_DIGEST` are placeholders; in real manifests, replace them with valid digests. This example only illustrates the selector mechanism and omits namespaces, resource quotas, network policies, autoscaling, or full production configuration.

To roll back, change the selector back to track blue after confirming blue is still Ready and compatible with the current data state.

## 9. Connection draining, sessions, and in-flight traffic

When the router sends new requests to green, in-flight requests on blue may not have finished yet. Define how to handle them:

- **Connection draining:** stop sending new connections to blue while allowing current requests to finish within a grace period.
- **Graceful shutdown:** the application stops accepting new requests, completes active work, and exits.
- **Timeouts:** cap long-running requests to prevent blue from being held indefinitely.
- **WebSockets/streaming:** may require keeping connections on blue or instructing clients to reconnect.
- **Sticky sessions:** instance-bound sessions can keep users routed back to blue after cutover.

If sessions live in instance memory, users can lose login state when switching environments. Use a shared session store or stateless tokens where appropriate. If both versions use different session formats, ensure they remain compatible during transition and rollback.

For workers and consumers, switching HTTP traffic does not automatically transfer message processing ownership. If both blue and green consume from the same queue, duplicate processing, contention, or double side effects can occur. Design idempotency, consumer groups, leader election, or a timed shutdown for blue workers.

## 10. Shared databases and data are the biggest risk

Blue and green usually connect to the same database. That keeps data consistent across both environments, but it also means both versions may read/write the same schema during deployment and rollback.

Do not deploy destructive migrations before cutover if blue still needs the old schema. A common pattern is **expand-contract**:

1. **Expand:** add new columns, tables, indexes, or APIs in a way still compatible with the old version.
2. **Deploy compatible version:** deploy green capable of working with both new and old schemas during the transition.
3. **Cutover:** switch traffic to green after verification.
4. **Observe:** keep blue during the rollback window, ensuring blue can still run against the current schema.
5. **Contract:** drop old columns, tables, or compatibility paths only after the old version is no longer needed and rollback no longer depends on them.

For example, if green needs a new customer_status column, the migration can add it as nullable first. Green writes both old and new fields during the transition if needed. After blue is removed and data is backfilled/verified, the team considers dropping the old column in a later release.

Some data changes cannot be rolled back by switching traffic. If green writes data in a format blue cannot read, reverting to blue can cause errors or data loss. Verify read/write compatibility before cutover and prepare a separate data recovery plan for irreversible migrations.

## 11. Caches, messages, and side effects

Coexisting environments can share or isolate caches, brokers, and external systems. Each choice has consequences:

- Shared caches let blue and green see the same data, but key formats must be compatible.
- Separate caches provide isolation, but green may start with cold caches and cause a load spike on the database.
- Shared queues require consumer controls to avoid unintended parallel processing.
- Separate topics or queues aid green testing, but test events must not leak into real systems.
- Emails, payments, webhooks, and notifications require idempotency or must be disabled during validation.
- Scheduled jobs should run on only one active version if the task is not designed for concurrent execution.

If green needs cache warm-up, run it before cutover and monitor load on dependencies. Do not run warm-up using operations with business side effects. If events must be sent, use test events or a sandboxed environment.

## 12. Post-cutover monitoring and deciding to keep or roll back

After switching traffic, the job is not finished. This is the phase to validate green under real traffic.

Monitor at least:

- Request success and error rates, broken down by version.
- Latency and timeouts.
- Application error logs, exceptions, and crashes.
- CPU, memory, thread, and connection pool saturation.
- Database latency, locks, and connection counts.
- Queue lag, retries, and dead-letters.
- Business metrics: successful transactions, orders created, completed payments.
- Alerts from dependencies and infrastructure.

The observation window should match load patterns. A continuously trafficked API may show early signals within minutes; an hourly batch or time-specific business workflow requires a longer window to gather sufficient evidence.

### 12.1. Conditions to keep green

Keep green as the active version when:

- Error rate and latency stay within defined thresholds.
- No critical business errors occur.
- Dependencies and databases operate stably.
- No abnormal increases in retries, queue lag, or resource saturation appear.
- Critical workflows have received enough traffic to verify.
- No new release-related alerts fire.

### 12.2. Rollback conditions

Revert to blue when predefined conditions occur, such as:

- Error rate breaches threshold during the observation window.
- Latency rises past SLO and impacts users.
- Critical transactions fail or data is corrupted.
- Green crash-loops, loses readiness, or cannot reach dependencies.
- Queue lag or retries grow enough to threaten SLA.
- Security anomalies or unintended behavior appear.

Do not wait for the observation window to expire if a severe incident is detected. Conversely, do not roll back over a single noisy alert without checking actual impact and predefined thresholds. Operators must distinguish real signals from monitoring glitches.

## 13. How to execute a blue-green rollback

If blue is still running and data remains compatible, rollback can be as simple as pointing the router back to blue:

1. Confirm blue is still Ready and has sufficient capacity.
2. Stop or reduce traffic to green.
3. Route new requests back to blue.
4. Drain in-flight connections on green if possible.
5. Verify traffic and business metrics stabilize on blue.
6. Isolate green for investigation; do not delete logs or artifacts.
7. Record release ID, digest, timestamp, and rollback reason.

Traffic rollback does not automatically undo database migrations, emitted messages, sent emails, or completed transactions. Identify which side effects occurred and handle them separately.

Keep blue during the defined rollback observation window. Deleting blue too soon forfeits fast rollback; keeping it too long increases costs and leaves behind a stale environment easily forgotten. Decommission timing for blue should be based on rollback risk, data state, and artifact retention policies.

### 13.1. Rollback is not always safe

You cannot roll back by routing alone if:

- Green altered the schema in a way blue cannot read.
- Green wrote data in an incompatible new format.
- A message was processed under new logic and cannot safely repeat.
- Blue lacks capacity because it was scaled down.
- Blue's secrets, certificates, or endpoints were revoked.
- External side effects already executed and cannot be undone.

Therefore, rollback must be designed alongside migrations, workers, sessions, caches, and external integrations. If data has moved into a non-reversible state, the path forward may be a forward-fix or deploying a follow-up patch rather than reverting to the old binary.

## 14. Common mistakes when using blue-green

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Switching traffic as soon as containers are Running | Green is not business-ready yet | Use readiness, smoke tests, and dependency checks |
| Blue and green have incompatible schemas | Rollback breaks the old application | Use expand-contract and compatibility testing |
| Both environments run workers concurrently | Duplicate message/job processing | Control active workers, idempotency, and leader election |
| Skipping connection draining | Long requests get dropped or hang | Connection draining and graceful shutdown |
| Storing sessions in memory | Users lose sessions after cutover | Shared session store or stateless tokens |
| Looking only at aggregate metrics | Green errors hidden by blue traffic | Split metrics by version/color |
| Using DNS and assuming instant switchover | Clients still call blue due to DNS cache | Account for TTL and resolvers; prefer routers with clean cutover |
| Ignoring two-environment capacity needs | Resource exhaustion or database overload | Load test and size quotas/connections before release |
| Deleting blue right after cutover | Rollback becomes slow or impossible | Retain blue during the observation window |
| Treating traffic switch as complete rollback | Side effects and new data still persist | Plan for data, messages, and external side effects |
| Building separate artifacts per color | Blue/green may run unexpected binaries | Promote the exact verified artifact digest |

## 15. Example blue-green release for an order service

Suppose orders-api version 1.8.0 is running on blue. The team wants to release 1.9.0 adding a new order status.

**Pre-release**

- Build 1.9.0 from a reviewed commit, run unit/integration tests, and pass quality gates.
- Record artifact digest and provenance.
- Verify migrations only add new columns and do not remove fields 1.8.0 requires.
- Define smoke tests and error rate/latency thresholds.
- Confirm blue has enough capacity to keep serving while green is provisioned.

**Preparing green**

- Create the green Deployment using the exact 1.9.0 image digest.
- Provision secrets and network policies.
- Run the expand migration and wait for completion.
- Wait for all green pods to become Ready.
- Call health endpoints and run create/read order smoke tests using a test account.
- Verify logs, database latency, queues, and caches.
- Keep side-effect workers active on blue only until cutover.

**Cutover**

- Have the router direct a small percentage of requests to green if supported by the platform.
- Monitor error rate, latency, and business metrics isolated for green.
- If thresholds pass within the observation window, increase traffic share to green.
- Once all new traffic reaches green and the system is stable, mark green as active.
- Drain blue connections and keep blue ready for rollback.

**Post-release**

- Monitor transactions, queues, and databases for an appropriate duration.
- If green hits critical failures, switch traffic back to blue after verifying schema compatibility.
- If stable, wait out the rollback window before retiring blue.
- Only in a subsequent release, when no old version needs the old fields, execute the contract migration.

This example shows that cutover timing depends on application readiness as well as data, workers, and observability. It cannot rely solely on the result of a deploy command.

## 16. Pre-, during-, and post-cutover checklist

**Before creating green**

- [ ] Artifact is built, tested, scanned, and identified by digest.
- [ ] Provenance and release records exist per policy.
- [ ] Blue/green have appropriate configuration, networking, secrets, and permissions.
- [ ] Capacity, quotas, and database connections are sized for two environments.
- [ ] Migrations are compatible with both old and new versions.
- [ ] Workers, schedulers, and side effects have control mechanisms.
- [ ] Dashboards, alerts, and cutover/rollback criteria are ready.

**Before switching traffic**

- [ ] Green has sufficient replicas and all instances are Ready.
- [ ] Smoke tests on green pass.
- [ ] Dependencies, database, cache, and broker are healthy.
- [ ] Artifact digest matches the approved build.
- [ ] No critical errors appear in logs.
- [ ] Blue remains healthy and able to take traffic back.
- [ ] Router has an appropriate switching plan and connection draining.
- [ ] Operators know who decides cutover and who triggers rollback.

**After switching traffic**

- [ ] New requests actually reach green per metrics/logs.
- [ ] Error rate, latency, and business metrics are within thresholds.
- [ ] Database, queues, caches, and dependencies are stable.
- [ ] Blue is retained for the defined rollback window.
- [ ] Release/deployment records accurately log digest, timestamp, and outcome.
- [ ] Blue is retired only once rollback is no longer needed and data is compatible.
- [ ] Contract migrations run separately under controlled conditions.

## Conclusion

Blue-green deployment separates preparing the new version from the moment users start receiving it. Blue continues serving while green is deployed and verified; traffic switches only when green is Ready, smoke tests pass, dependencies and data are compatible, capacity is sufficient, and observability is ready.

After cutover, monitor versioned metrics and manage connection draining, sessions, workers, and side effects. Retaining blue during the rollback window enables fast recovery, though only safely when schemas and data remain compatible. When these conditions are thoroughly designed, blue-green gives CI/CD controlled, traceable releases with faster recovery when a new version runs into trouble.
