# Defining Deployment Stop Conditions and Rollback Triggers

In **Java Advance Compatibility Migration**, bringing a new Java/JDK/framework version into production must not end at a "green build, successful deploy" state. An application may start up fine yet fail only when processing a rare event, calling a library with `AbstractMethodError`, performing a TLS handshake with a partner, running an end-of-day batch, or writing data using a new Hibernate version. Without defining beforehand **when to stop the rollout** and **how to trigger a rollback**, a small issue in the canary can escalate into a system-wide incident.

This lesson in the **Release and Operations** chapter presents how to establish **go/no-go**, **hard stop**, **soft stop**, **rollback triggers**, measuring SLOs and business invariants, organizing canary/rolling/blue-green deployments, and building runbooks. The focus is not only on reverting to the old artifact, but also on **protecting data, limiting impact, and verifying recoverability**.

**Principle:** all thresholds, conditions, and decision-making authority must be agreed upon **before** expanding traffic. The numbers in the examples illustrate methodology, not production thresholds that can be copied verbatim.

## 1. No-go, Pause, Containment, Rollback, and Roll-forward

| Decision | Goal | Example |
|---|---|---|
| **No-go** | Do not allow release to start | Missing rollback image, wrong JDK, required tests not passing |
| **Pause rollout** | Stop expanding impact to investigate | Hold canary at 5%, do not advance to 25% |
| **Containment** | Stop or restrict harmful behavior | Disable feature, isolate write path, stop consumer |
| **Rollback** | Return to a known safe operational state | Shift traffic back to stable, run old image/config |
| **Roll-forward** | Fix the incident with a follow-up release when rollback is unsafe | Hotfix, compatibility adapter, data repair |

**Pause does not mean rollback:** already-deployed canary pods may still be running and receiving traffic. **Binary rollback does not mean data rollback:** records, events, and payments already processed do not vanish automatically when changing the image.

### 1.1. Example

An application upgrading from Java 11/Spring Boot 2 to Java 17/Spring Boot 3:

1. Before deploy, verify runtime, dependency versions, and rollback plan: **go/no-go**.
2. When 5% canary shows rising 5xx: **pause**.
3. If duplicate payment charges are detected: immediate **containment**.
4. When data remains compatible with stable: **rollback traffic/image**.
5. When stable cannot understand new data: do not roll back blindly, **contain and evaluate roll-forward/repair**.

## 2. Why Set Stop Conditions Before Release?

During an incident, teams easily argue "wait longer for enough samples", "this is just warm-up", or "increase canary to observe more". Without clear boundaries, increasing traffic can expand the **blast radius**.

Pre-agreed stop conditions help:

- Limit affected users, transactions, and data.
- Avoid emotional decisions made to protect a release.
- Distinguish candidate regressions from incidents also affecting stable.
- Define who is authorized to pause, roll back, or isolate a flow.
- Prevent CI/CD from auto-advancing when metrics are missing.
- Create audit evidence and post-incident review material.
- Tie recovery plans to RTO/RPO.
- Ensure stable artifacts and capacity are prepared.
- Help all teams clearly understand **unacceptable** signals.

A policy of "roll back when the application is unstable" is insufficient. You must specify **metric, scope, observation window, threshold, sample, action, owner, and evidence**.

## 3. Key Terminology

| Concept | Meaning |
|---|---|
| Stable/control | Version currently serving or the control group |
| Candidate/canary | New version receiving a portion of workload |
| Rollout step | Each increment of traffic, replicas, tenants, or regions |
| Blast radius | Scale of potential impact |
| SLI | Measurable service quality indicator, e.g., request success |
| SLO | Service quality target over a measurement window |
| Error budget | Allowable error allowance under the SLO |
| Hard stop | Condition requiring immediate risk-mitigating action |
| Soft stop | Condition to pause and verify |
| Rollback trigger | Formal rule that initiates rollback |
| RTO | Target time to restore service |
| RPO | Target acceptable level of data loss |
| Inconclusive | Insufficient evidence to allow proceeding |
| Observability gap | Missing or unreliable metrics/logs/traces |

RTO and RPO are two distinct targets. Shifting traffic back to the old version in 5 minutes does not prove RPO was met if the faulty version wrote corrupted data.

## 4. Go/No-Go Gate Before Deployment

A preflight gate should be checked **before impacting production**:

| Gate | What to verify | Failure |
|---|---|---|
| Artifact provenance | Commit, build ID, image/JAR/WAR digest match approved build | No-go |
| Java runtime | Compiler, test, and container JVM match baseline | No-go |
| Dependencies | Frameworks, agents, libraries/bytecode tooling compatible | No-go |
| Required tests | Unit/integration/contract/security checks pass | No-go |
| Database | Schema and data compatible within rollback window | No-go |
| Messaging | Event formats and consumers/producers can co-exist | No-go |
| Observability | Metrics have version labels, logs/traces, alerts working | No-go |
| Stable capacity | Old version can take traffic back | No-go |
| Rollback | Artifact/config/permissions/runbook ready | No-go |
| Ownership | Release owner, on-call, and escalation contacts clear | No-go |
| Security | No blockers on auth, TLS, secrets, data access | No-go |
| Change window | Incident/maintenance and error-budget policy permit | No-go per policy |

Do not just tick checkboxes by gut feeling: each item needs a supporting link or log evidence. If a deployment already includes a destructive migration that breaks stable, resolve that **before** starting the canary.

## 5. Hard Stop: Conditions That Cannot Wait for Statistics

**Hard stops** protect core business and safety invariants:

- Recording wrong amounts, balances, or duplicate charges.
- Evidence of unauthorized access or cross-tenant data exposure.
- Loss, miswriting, or corruption of data.
- Exposure of secrets, tokens, or personal information.
- Publishing messages that put downstream systems into invalid states.
- An unapproved artifact being deployed.
- The new version rendering shared infrastructure unavailable.
- Proven severe failures in a critical transaction flow.
- A change making the rollback path unsafe while the release continues increasing risk.

Once sufficient confirming evidence exists, you must **stop expanding impact and execute containment per runbook**; simultaneously evaluate rollback and initiate incident response. Do not wait for 500 requests or 2 sampling windows if a duplicate payment has been verified.

### 5.1. Do Not Treat Every Alert as a Verified Error

A detector can have false positives. The runbook must describe verification evidence and fast on-call triage; however, the verification process must not allow a severe data/security incident to drag on indefinitely.

## 6. Soft Stop: Pausing to Investigate

Some signals require pausing before ramping traffic:

- 5xx ratio rises without enough data yet.
- p95/p99 latency exceeds baseline.
- Sustained rise in CPU/GC/heap.
- Unstable readiness or startup.
- Rising queue lag, retry rate, or DLQ.
- Both stable and candidate are impacted by a shared dependency.
- Dashboard missing data or broken release labels.
- APM agent not reporting or trace propagation broken.

**Pause** means holding the blast radius within an acceptable boundary. The team then identifies the cause and impact and decides to **resume, roll back, or continue containment** within a timebox.

A soft stop without an investigation timebox easily turns into a canary "hanging" for hours with no one taking responsibility.

## 7. Designing Measurable Conditions

A good condition needs:

~~~text
Signal:       HTTP 5xx error ratio
Scope:        orders-api candidate, checkout route
Window:       rolling 5 minutes
Min sample:   500 valid requests
Threshold:    > 1% AND > 3 times comparable stable ratio
Decision:     PAUSE increasing traffic
Owner:        release on-call
Investigation: logs, traces, dependency, business impact
Rollback:     if candidate-caused or regression persists
Evidence:     release-labeled dashboard + incident record
~~~

The thresholds **500, 1%, 3x, 5 minutes** are examples only.

### 7.1. Minimum Sample Is Part of the Condition

One failed request out of ten requests is 10%, yet has little statistical evidence. For low-traffic services, longer windows or synthetic tests are needed. However, sample size **must never disable a hard stop**.

### 7.2. The Window Must Match the Workload

A batch job running every 60 minutes cannot be validated by just 5 minutes of HTTP monitoring. Event-based gates can be used: "first job on candidate succeeds", "sufficient critical event types processed", or "reconciliation accurate".

## 8. Illustrative Error Ratio Calculation

Suppose over 5 minutes:

| Group | Requests | 5xx | 5xx ratio |
|---|---:|---:|---:|
| Stable | 20,000 | 40 | 0.2% |
| Candidate | 1,000 | 20 | 2.0% |

Formula:

\[
\text{Error Ratio}=\frac{\text{Number of failed requests}}{\text{Total valid requests}}
\]

The candidate has a 2.0% error rate, **10 times higher than stable**. Under the agreed policy, this is a strong pause signal.

Nevertheless, verify:

- Is the traffic mix across routes/tenants/regions comparable?
- Do the errors share the same root cause?
- Are monitoring probes skewing the denominator?
- Are the errors at the application, ingress, or dependency layer?
- Are there enough samples and metric freshness?
- Did the 5xx errors truly appear only after rollout?

If stable had 0 errors in a small window, calculating "candidate is N times higher" is unreliable. Combine absolute thresholds, sample volume, and practical assessment.

## 9. SLO, Error Budget, and Burn Rate

For example, a **99.9%** availability SLO over 30 days allows roughly **0.1%** unsuccessful events under the same SLI.

If the candidate has 2% errors, the error budget burn rate relative to the allowed rate is approximately:

\[
\text{Burn Rate}=\frac{2\%}{0.1\%}=20
\]

This is a simplified interpretation; real systems often use **multi-window burn-rate alerts** to balance detection speed and noise.

A release gate can enforce policies:

- Do not release high-risk changes when the error budget is exhausted.
- Prioritize reliability fixes over shipping more features.
- Allow emergency fixes under a separate approval process.
- Halt rollout when the candidate burns budget faster than allowed.

An average SLO does not replace **critical business invariants**. A checkout API failing for a small group can be severe even if the overall service still meets its aggregate target.

## 10. Latency, GC, and Java Performance

Upgrading the JDK can alter JIT, GC, class loading, TLS, and thread scheduling. An illustrative condition:

~~~text
PAUSE if:
  p95 checkout latency > 500 ms
  AND p95 > 1.5x stable p95
  across two consecutive 5-minute windows
  with sufficiently representative request count and traffic mix.
~~~

Do not copy 500 ms verbatim to every service.

### 10.1. Warm-Up Does Not Waive Hard Stops

A new canary may go through JIT warm-up, cache cold-start, or unpopulated connection pools. A warm-up window can be allowed, but never used as an excuse to ignore data loss, authorization bypass, or severe 5xx errors.

### 10.2. Percentile Aggregation

Do not calculate service-wide p95 by averaging pod p95 values. Use proper histograms/aggregations supported by your measurement tool.

### 10.3. Saturation Metrics

Monitor CPU, throttling, heap, GC pauses, thread pools, HTTP/DB pools, native memory, file descriptors, OOM, queue age, and timeouts. Even a small canary can break the whole service if it exhausts a shared connection pool.

## 11. Signals Specific to Java/JDK Migration

| Error type | Examples |
|---|---|
| Bytecode target | `UnsupportedClassVersionError` |
| ABI linkage | `NoSuchMethodError`, `AbstractMethodError`, `IncompatibleClassChangeError` |
| JPMS/reflection | `InaccessibleObjectException`, `IllegalAccessError` |
| Missing runtime API | `ClassNotFoundException`, `NoClassDefFoundError` |
| Javax/Jakarta mismatch | Incompatible Servlet/Validation/JPA APIs |
| Crypto/TLS | `SSLHandshakeException` |
| Serialization | JSON/XML/event deserialization errors |
| Bytecode agents | ASM/Byte Buddy not supporting class major version |
| ORM/JDBC | Hibernate converter, SQL, transaction errors |
| JNI/native | `UnsatisfiedLinkError` |
| Runtime performance | GC pause, latency, heap/native memory regressions |

An error may surface only when a request executes the exact method or event path. Therefore, **a green startup does not mean runtime compatibility**.

If a new canary fails on a critical route, do not wait for the whole-service 5xx ratio to cross the threshold before pausing.

## 12. Business Invariants: The Power of the Right Signal

Business invariants should be separated from HTTP metrics:

- Never charge twice for the same idempotency key.
- Never deduct stock twice.
- Never generate an invoice with an incorrect total.
- Never let a user read another tenant's data.
- Never lose a confirmed transaction.
- Never write a state that old consumers cannot read outside the rollout contract.
- Never corrupt balances or ledgers.
- Never send user data to the wrong destination.

A Hibernate converter bug can still return HTTP 200 while writing the wrong order status. Only **business reconciliation** catches it; therefore, monitoring must measure correctness, not only availability.

### 12.1. Synthetic Transactions

Isolated test transactions can be created: login, dummy order creation, validation checks, outbound TLS, message serialization, ORM data queries. Do not use real payments or customer data without an approved isolation/cleanup plan.

## 13. Observability Is a Release Gate

To make rollout decisions, you need:

1. Version/build/digest labels in telemetry.
2. Release markers and timestamps.
3. Logs with trace/correlation IDs.
4. Error/latency/saturation by candidate and stable.
5. Critical route and business metrics.
6. Queue/batch/job metrics if the application uses them.
7. Traces across dependencies.
8. Working alert channels.
9. Known metric ingestion latency.
10. Owners of dashboards/queries.

### 13.1. Missing Metrics Do Not Mean Pass

If metrics disappear, labels change after a Micrometer upgrade, or an APM agent breaks on the new JDK, the system is in an **inconclusive** state. Normally you should pause until observability is restored, rather than assuming the app is healthy.

### 13.2. Do Not Use Aggregate Metrics to Hide Canary Errors

If the candidate receives only 5% of requests, its errors can be drowned out in the service-level average. Always compare by release label and traffic mix.

## 14. Canary and Stable Must Be Compared Comparably

~~~text
                  Incoming traffic
                         |
                 +-------+-------+
                 |               |
                 v               v
            Stable N       Candidate N+1
             control          canary
                 |               |
                 +-------+-------+
                         |
                  Compare SLIs
                         |
             Continue / Pause / Rollback
~~~

When comparing, check:

- Same time window.
- Request route/method and tenant profile.
- Region/device/client mix.
- Request sizes and workloads.
- Cache/JIT warm-up differences.
- External dependencies.
- Uncovered background jobs.
- Minimum sample and instrumentation quality.

**A 1% canary does not mean 1% risk:** one pod can monopolize a shared DB connection pool or create migration side effects affecting all traffic.

## 15. Progressive Rollout With Step Gates

Example diagram:

~~~text
Preflight
   |
   v
1% traffic --> observe --> decision
   |
   v
5% traffic --> observe --> decision
   |
   v
25% traffic --> observe --> decision
   |
   v
100% traffic --> extended observation
~~~

Percentages are illustrative only. For low-traffic systems, internal cohorts, region-first rollout, or synthetic coverage can be used.

Before advancing a step:

- Do metrics have enough data?
- Have critical workflows been exercised?
- Are error/latency/GC stable?
- Are data/security invariants protected?
- Is the rollback path still safe?
- Is stable capacity still sufficient?
- Has the owner approved per policy?

**Reaching 100% rollout still requires continued monitoring.** End-of-day batches or rare flows may only run after deployment completes.

## 16. Blue-Green Deployment and Traffic Switch

~~~text
                   Traffic router
                         |
                 +-------+-------+
                 |               |
                 v               v
           Blue stable      Green candidate
~~~

Blue-green enables fast traffic switching, but is only safe when:

- Green is ready and warmed up.
- Blue still retains capacity.
- Database/event schemas are compatible.
- Session/cookie/redirect behavior is correct.
- No duplicate schedulers/consumers run causing side effects.
- The traffic router has a path back to blue.
- Monitoring confirms the correct pool and version.

Switching traffic from green back to blue **does not delete records already written by green**. If blue cannot understand the new records, rolling back traffic can worsen errors.

## 17. Rolling Deployment and Concurrent Versions

During a rolling update, both may run at the same time:

~~~text
Load balancer
  |            |
  v            v
Old pods     New pods
Version N    Version N+1
~~~

Check:

- Old/new apps can read/write the same DB schema.
- Session serialization compatibility.
- API clients may hit both versions.
- Producers/consumers understand each other's messages.
- Cache values and key formats are compatible.
- Feature flags are synchronized.
- Schedulers have proper locks/leader election.
- Config/runtime do not conflict.

A feature running for just 10 minutes that writes state unreadable by the old version is enough to break the rollback window.

## 18. Feature Flags and Kill Switches

A feature flag can isolate a risky code path:

~~~text
Request
   |
   v
Feature flag
   |
   +--> Old implementation
   |
   +--> New implementation
~~~

When properly designed, turning off a flag can stop harm faster than rolling back an image. However, ensure:

- The old branch still works.
- The flag propagates in time.
- Data written by the new branch is compatible with the old branch.
- Batch/consumer processes also check the flag if needed.
- Metrics distinguish states.
- The flag fallback has been tested.

**Disabling a flag is only containment if the root cause remains in the artifact.** You still must remediate and decide whether to perform a full rollback.

## 19. Rollback Layers to Separate

| Layer | Action | Not automatically restored |
|---|---|---|
| Traffic | Router shifts back to stable | DB and external side effects |
| Binary | Run known-good image/JAR/WAR | Config/data schemas |
| Config | Revert env vars/flags/feature settings | Already committed writes |
| Queue | Stop candidate consumers | Already acked/published events |
| DB | Controlled restore/PITR/repair | Valid transactions after snapshot unless reconciled |
| Roll-forward | Hotfix/compatibility adapter | Previously corrupted data |

A full system rollback usually requires coordinating multiple layers. **Do not declare recovery merely because the orchestrator reports the previous revision is Available.**

## 20. Preparing Java Runtime and Framework Rollback

A stable version may include:

- Old JDK vendor/version and base OS image.
- Different Spring Boot/Framework/Hibernate libraries.
- Different JVM flags.
- Different Java agent/APM.
- Different TLS provider/truststore.
- Different serialization and data access mappings.
- Specific container config and secret references.

Save the **stable image digest**, not just a mutable tag. Along with the artifact, keep the configuration, dependency set, and JDK runtime verification instructions.

### 20.1. Do Not Randomly Downgrade Individual JARs

Do not "roll back" by swapping just a single Spring Framework JAR or Hibernate JAR inside the candidate. Revert to a verified, operable combination of dependencies.

### 20.2. Stable Needs Enough Capacity

If blue/stable was scaled down to too few replicas, rolling back traffic can overload it. Prepare capacity or time-to-scale-up aligned with RTO.

## 21. Database and the Expand-and-Contract Process

This is often the biggest risk for rollback.

Example:

~~~text
Version N understands statuses: NEW, PAID
Version N+1 adds: PARTIALLY_REFUNDED
Rollback to N:
  old parser does not understand the new value
~~~

Even when the database schema does not change, **data values** can render old code incompatible.

A risk-reducing process:

1. **Expand:** add compatible fields/tables/indexes without removing old structures.
2. **Compatibility:** old/new versions can simultaneously read/write.
3. **Switch:** gradually enable new behavior along with the rollout.
4. **Contract:** remove old parts only after the rollback window has truly closed.

Do not assume dual-write should always be used; it introduces its own consistency risks.

### 21.1. DDL Rollback Is Not Data Rollback

A down migration can drop a field containing newly written data. Before any destructive operation, review:

- Backup/PITR availability.
- RPO and valid writes after snapshot.
- Number of affected records.
- Consumers or reports depending on the schema.
- Authorized approvers.
- Reconciliation plan.

### 21.2. Restores Must Be Rehearsed

Having backups is not enough. Know how long a restore takes, what data is lost, how integrity is verified, and who owns the decision.

## 22. Messaging, Idempotency, and Consumer Rollback

In an event-driven system:

~~~text
New producer --> Broker --> Old consumer
    new schema              incompatible parser
~~~

Rolling back the producer does not delete already-published events. Rolling back a consumer does not automatically undo payments, emails, or side effects.

Stop conditions to monitor:

- Consumer lag and oldest message age.
- Deserialization failures.
- DLQ growth.
- Retry storms.
- Duplicate processing.
- Offset commit state.
- Schema compatibility.
- Cross-version producer/consumer tests.

**Do not blindly reset offsets/replay all messages** if idempotency has not been verified. When data is already wrong, a reconciliation plan is required.

## 23. Security Hard Stop

Signals requiring immediate escalation:

- Authorization bypass.
- Cross-tenant data access.
- TLS validation disabled.
- Tokens/secrets appearing in logs.
- Management endpoints publicly exposed.
- Wrong audience/issuer acceptance in JWT.
- Sensitive data sent to the wrong destination.

Stop increasing exposure, contain, and escalate to the security incident process. Do not wait for p95 or 5xx. Never use a trust-all TLS workaround to make a deployment appear to work.

## 24. Auto-Pause, Auto-Rollback, or Manual Approval?

| Option | Pros | Risks |
|---|---|---|
| Auto-pause | Quickly limits blast radius | Existing canary may still keep running |
| Auto-rollback | Fast reaction when traffic-based rollback is safe | False positives, metric outages, data mismatch |
| Human-approved | Has business/data context | Slow if ownership is unclear |
| Hybrid | Auto-pause, rollback per policy/approval | Needs clear escalation and audit trail |

Auto-rollback should only apply when:

1. Telemetry is trustworthy and labeled by version.
2. Sample/window and fail/inconclusive semantics are clear.
3. Stable artifact/capacity are ready.
4. DB/schema/event formats are backward-compatible.
5. Actions are rehearsed and idempotent.
6. Audit logs and owners exist.
7. It does not trigger unapproved destructive data recovery.

For data corruption, teams typically require immediate containment and involvement of DB/incident owners for recovery decisions.

## 25. Rollout Decision Tree

~~~text
Preflight passed?
    |
    +-- NO --> NO-GO
    |
    +-- YES --> Candidate receives traffic
                      |
                      v
              Hard stop verified?
                |           |
               YES          NO
                |            |
         CONTAIN+INCIDENT    v
                       Telemetry valid?
                         |         |
                        NO        YES
                         |         |
                       PAUSE       v
                            SLIs & invariants OK?
                              |         |
                             YES        NO
                              |          |
                           Advance      PAUSE
                             step         |
                                          v
                                 Rollback safe?
                                  |       |
                                 YES      NO
                                  |       |
                               ROLLBACK  CONTAIN +
                                         ESCALATE/
                                         ROLL-FORWARD
~~~

This is a reasoning diagram, not a directly executable machine workflow. A hard stop can be verified at any stage and must take top immediate priority.

## 26. Illustrative Guardrails Table

| Signal | Example threshold | Decision |
|---|---|---|
| Verified duplicate payment | One case | Hard stop + reconciliation |
| Authorization bypass | One verified case | Hard stop + security incident |
| 5xx ratio | >1%/5 min, >=500 requests, >3x stable | Pause, roll back if release-caused |
| p95 checkout | >500 ms and >1.5x stable over two windows | Pause |
| Canary crashloop | Repeated NotReady and retries | Pause/rollback |
| LinkageError critical path | Verified on candidate | Pause/rollback |
| Consumer DLQ growth | Sustained above baseline | Pause/contain |
| Data inconsistency | Verified invariant violation | Hard stop |
| Monitoring unavailable | Required SLIs missing | Pause |
| Stable capacity missing | Cannot accept traffic back | No-go |
| Unsafe rollback | Old version incompatible with state | No-go or containment |

Values are **illustrative only**. For low-traffic services or high correctness requirements, dedicated policies are needed.

## 27. Illustrative Policy-as-Code

~~~yaml
# Pseudocode, NOT an actual Kubernetes/Argo/Flagger configuration.
releaseGuardrails:
  service: orders-api
  stable: known-good
  candidate: java17-boot3
  preflight:
    approvedArtifact: true
    stableCapacityRequired: true
    rollbackImageRequired: true
    observabilityRequired: true
    databaseCompatibilityRequired: true
  rollout:
    stepsPercent: [1, 5, 25, 100]
    insufficientData: PAUSE
  metrics:
    - name: canary5xx
      windowMinutes: 5
      minRequests: 500
      pauseIfRatioAbove: 0.01
      pauseIfTimesStableAbove: 3
    - name: checkoutP95
      windowMinutes: 5
      minRequests: 300
      pauseIfLatencyMsAbove: 500
      pauseIfTimesStableAbove: 1.5
  hardStop:
    - verifiedDataCorruption
    - verifiedAuthorizationBypass
    - verifiedDuplicateTransaction
  decisions:
    pauseOwner: release-oncall
    rollbackRequires: safeAndVerifiedPlan
    dataRestoreRequires: databaseOwnerApproval
~~~

Keys only represent a **policy model**; to run in practice, translate to the actual schema/tool version and test controller behavior.

Policy changes require review. Do not silently loosen thresholds to turn dashboards "green" under release pressure.

## 28. Kubernetes Deployment: Pause and Undo

Example commands for an authorized runbook:

~~~bash
kubectl rollout status deployment/orders-api -n production
kubectl describe deployment orders-api -n production
~~~

Pause the update:

~~~bash
kubectl rollout pause deployment/orders-api -n production
~~~

View revisions and undo when appropriate:

~~~bash
kubectl rollout history deployment/orders-api -n production
kubectl rollout undo deployment/orders-api -n production
kubectl rollout status deployment/orders-api -n production
~~~

Resume once re-evaluated:

~~~bash
kubectl rollout resume deployment/orders-api -n production
~~~

**Limitations:**

- `rollout pause` stops Deployment progression; it does not automatically shift traffic back to stable.
- `rollout undo` depends on revision history still being available, the old image being pullable, and compatible configuration.
- If a Deployment is currently paused, execute the pause/resume/undo sequence appropriate for the tested system.
- The undo command does not revert databases, queue messages, side effects, or external configs.
- `rollout status` reports Deployment status; it does not prove customer-facing SLO/correctness.

Canary weighted traffic may require ingress, service mesh, or a progressive delivery controller; do not assume Deployment provides that routing policy by default.

## 29. Health Probes Do Not Replace Business Guardrails

- **Startup probe** checks startup state.
- **Readiness probe** indicates a pod is ready to receive traffic per corresponding routing semantics.
- **Liveness probe** helps detect containers needing restart.

These probes do not prove:

- No duplicate payments exist.
- Hibernate mappings are correct.
- JWT authorization is not bypassed.
- Message serialization remains compatible.
- p99 meets SLO.
- External API integrations work.

Overly strict liveness settings can cause a new JDK to restart repeatedly during GC pauses/JIT warm-up. Configure probes appropriate to the lifecycle while running user-facing metrics and invariants.

## 30. Illustrative Metrics Query

A PromQL-like query for candidate 5xx ratio, assuming corresponding metrics/labels exist:

~~~promql
sum(rate(http_server_requests_seconds_count{
  service="orders-api",
  version="candidate",
  status=~"5.."
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  service="orders-api",
  version="candidate"
}[5m]))
~~~

This is an **example only**. Spring/Micrometer/OTel metric names and labels may differ. You must:

- Check the denominator.
- Filter out health probe noise if appropriate.
- Distinguish candidate/control.
- Handle zero requests.
- Check sample count and metric freshness.
- Have independent business checks.

Do not trust a single query if serialization/data correctness changes do not appear as 5xx responses.

## 31. Executable Rollback Runbook

A practical runbook should contain:

~~~text
Release:
  service, candidate digest, stable digest,
  cluster, namespace, owners, change window.

Trigger:
  exact metric/invariant, scope, window,
  threshold and incident severity.

Pre-checks:
  stable available and enough capacity;
  database/event backward compatibility;
  config/secrets and JVM runtime compatible.

Contain:
  pause increasing traffic;
  disable risky feature/consumer if authorized;
  open incident if required.

Rollback:
  change routing or deploy stable artifact;
  restore compatible configuration;
  confirm no unintended candidate traffic.

Validate:
  deployed digest, 5xx, latency, GC,
  critical business transaction, security,
  DB reads/writes, queues and observability.

Close:
  incident timeline, RTO/RPO, impact,
  ownership, prevention and re-release gate.
~~~

These lines must be translated into actual **commands, dashboard URLs, and contact points** for the real application. Do not wait until an incident happens to look up the stable image or who has permission to roll back.

## 32. Roles and Decision Authority

| Role | Responsibilities |
|---|---|
| Release owner | Coordinates rollout steps and decisions per policy |
| On-call/SRE | Monitors alerts, executes pause, routing/rollback per authority |
| Application owner | Diagnoses JVM/framework/API and business logic |
| Database owner | Assesses state/schema, backups, repair/reconciliation |
| Security owner | Handles auth/TLS/privacy incidents |
| Incident commander | Coordinates severe or multi-system incidents |
| Communications owner | Communicates status and impact |
| Approver | Approves risky operations per policy |

One person may hold multiple roles, but ownership must never be left unassigned.

Clearly specify which actions on-call may execute immediately to **stop damage**, and which actions—such as destructive DB restores—require approval. Do not create processes that leave operators waiting indefinitely while data is being corrupted.

## 33. Timebox and Resume Decision

An illustrative plan:

~~~text
T0: candidate receives canary traffic
T+5m: check telemetry freshness and sample
T+10m: pause if soft-stop guardrail breached
T+15m: assign cause and severity
T+20m: decide safe rollback or controlled continuation
~~~

These timestamps are not production defaults. Hard stops require immediate action; hourly batch jobs must have event-based observation.

Resume may only occur when:

1. Alerts have been explained, not merely disappeared.
2. Metrics are fresh and have sufficient data.
3. Candidate has passed critical tests.
4. Data/security invariants remain intact.
5. Stable/rollback options remain ready.
6. Owner approves per release policy.

If sufficient evidence is lacking after the timebox, **do not expand the blast radius**.

## 34. When Rollback Is Unsafe

Some scenarios:

- DB already dropped a field that stable still uses.
- Old binary cannot parse new data values.
- Broker holds new-schema events that old consumers do not understand.
- Side effects already occurred (charges/emails).
- Stable image has a critical security vulnerability.
- Backups cannot restore within RPO.
- External API contract changed one-way.

In such cases:

1. Stop the rollout.
2. Contain the harmful flow.
3. Preserve logs/transactions and determine scope.
4. Engage DB/data/security ownership.
5. Compare rollback vs roll-forward/compatibility adapter.
6. Execute controlled repair/reconciliation.
7. Verify correctness before reopening traffic.
8. Record the decision and evidence.

**An unsafe rollback does not mean continuing the release.** You may have to switch features to read-only or pause consumers.

## 35. Scenario: Linkage Error Appearing Only in Canary

A candidate upgrades Java 17 and its framework. When calling checkout:

~~~text
java.lang.AbstractMethodError:
Receiver class com.vendor.LegacyCheckoutAdapter ...
~~~

Procedure:

1. Candidate metrics record 5xx on checkout; stable in the same window has no errors.
2. Pause canary immediately.
3. Assess critical business impact.
4. If state is compatible and guardrails require it, roll back traffic.
5. Check already-executed payments to avoid retries/duplicates.
6. Verify checkout recovers on stable.
7. Investigate SPI version, adapter binary, classpath, class loader.
8. Upgrade adapter/test the failing path before re-rolling out.

Do not wait for the whole-service error ratio to spike if a critical path already has a verified failure.

## 36. Scenario: ORM Writing Wrong Data With HTTP 200

Candidate upgrades Hibernate along with the JDK. A custom enum converter changes mapping. The controller returns HTTP 200, yet reconciliation detects incorrect order values.

Actions:

- Hard stop per correctness invariant.
- Pause affected writes.
- Identify corrupted records.
- Assess whether the old binary can read the new state.
- Roll back code/traffic only when safe.
- Repair/reconcile data under DB/business owner responsibility.
- Test correctness before reopening.
- Document user impact and incident report.

This is why monitoring must include business invariants, not just availability.

## 37. Scenario: TLS Handshake Failure After JDK Upgrade

Candidate fails to call the payment partner:

~~~text
javax.net.ssl.SSLHandshakeException
~~~

May be caused by truststore, certificate chain, TLS protocol/provider, or mTLS configuration.

Procedure:

1. Pause.
2. Inspect outbound error metrics/traces.
3. Do not disable TLS validation or use trust-all.
4. Roll back runtime/traffic if impacted and state is compatible.
5. Fix certificate/truststore per policy.
6. Test outbound TLS in a comparable staging environment.
7. Re-canary with guardrails.

## 38. Scenario: Both Stable and Candidate Spike in 502/504

Suppose right after starting the canary, both pools show rising errors. Do not automatically conclude the candidate caused it or is completely unrelated.

Check:

- Database/shared connection pool saturation.
- Ingress/proxy/network outage.
- Whether the candidate makes unusual queries/connections.
- Traffic spikes and load balancer behavior.
- Error distribution by version and route.
- Dependency logs and deployment events.

Keep the rollout paused until the shared incident is resolved, root cause is sufficiently clear, and guardrails can be re-evaluated.

## 39. Rehearsing Rollback Before Needing Rollback

A rehearsal can:

1. Deploy the candidate into staging/an appropriate environment.
2. Run synthetic workflows.
3. Pause and shift traffic back to stable.
4. Verify old runtime/image/config.
5. Check DB schema/data compatibility.
6. Check queues, caches, sessions, and scheduled jobs.
7. Measure execution and recovery time.
8. Verify RBAC and escalation.
9. Confirm metrics/traces/alerts reflect the version switch.
10. Save runbook updates and remaining manual steps.

Do not arbitrarily use real customer data or real transactions for rehearsal. Rehearsals must evaluate **state compatibility**, not merely whether a command returns exit code 0.

## 40. RTO/RPO and Incident Timeline

Illustrative example:

~~~text
14:00 candidate incident detected
14:02 rollout paused
14:06 traffic returned to stable
14:09 HTTP SLIs restored
14:25 data reconciliation completed
~~~

A service may recover HTTP SLIs before all data is confirmed accurate. Do not declare an incident resolved at 14:09 if business correctness has not yet been restored.

Measure:

- Time to detect.
- Time to decide.
- Time to contain.
- Time to restore traffic.
- Time to reconcile state.
- Total customer impact.
- Actual RTO/RPO vs targets.

## 41. Decision Report Template

~~~yaml
# Illustrative template; not an actual incident that occurred.
releaseDecision:
  service: orders-api
  candidate: jdk17-boot3-build
  stable: known-good
  rolloutStepPercent: 5

  trigger:
    type: error-regression
    windowMinutes: 5
    minimumRequests: 500
    observedCandidateRatio: "record-value"
    observedStableRatio: "record-value"

  decision:
    action: PAUSE
    timestamp: "record-time"
    owner: release-oncall
    approvedBy: incident-policy

  safety:
    stableArtifactAvailable: false
    stableCapacityValidated: false
    databaseBackwardCompatible: false
    eventSchemaCompatible: false
    rollbackRehearsed: false

  evidence:
    dashboard: "record-link"
    logs: "record-link"
    traces: "record-link"
    incident: "record-link"

  outcome:
    stableTrafficRestored: false
    criticalFlowsVerified: false
    dataIntegrityVerified: false
    followUpOwner: application-team
~~~

The `false` and `record-value` values are placeholders, not PASS evidence. An actual decision must include the specific version/digest, approver, metrics/traces, and timestamp.

## 42. Go/No-Go Checklist

- [ ] Candidate commit, digest, and JDK/runtime version identified.
- [ ] Compiler/test/production JVM meet baseline.
- [ ] Frameworks, dependencies, agents, and bytecode tooling verified.
- [ ] Required unit/integration/contract/security tests pass.
- [ ] Stable artifact and capacity are ready.
- [ ] Database/schema backward compatibility reviewed.
- [ ] Producer/consumer event schema compatibility reviewed.
- [ ] Auth/TLS/privacy hard stops defined.
- [ ] Critical business transactions are monitored.
- [ ] Canary/control telemetry has reliable labels.
- [ ] Thresholds/window/min sample and inconclusive policy are clear.
- [ ] Runbook, owners, permissions, and escalation are ready.
- [ ] Rollback rehearsal or equivalent evidence exists.
- [ ] Change window and error budget policy permit release.

## 43. In-Rollout Checklist

- [ ] Markers recorded for every traffic increase.
- [ ] Confirmed candidate receives expected traffic.
- [ ] Checked startup/readiness and JVM/linkage errors.
- [ ] Checked error ratio, p95/p99, GC, saturation.
- [ ] Compared over the same window against stable/control.
- [ ] Checked critical routes and business invariants.
- [ ] Checked queue lag, DLQ, and scheduled jobs.
- [ ] Verified telemetry freshness.
- [ ] Do not advance when data is inconclusive.
- [ ] Pause or contain when a guardrail triggers.
- [ ] Clearly recorded decision-maker and evidence.
- [ ] Resume only when agreed conditions are met again.

## 44. Post-Rollback Checklist

- [ ] Candidate no longer receives unintended traffic.
- [ ] Stable artifact and JVM/runtime verified.
- [ ] Configuration and secret references compatible.
- [ ] Error ratio, latency, and saturation acceptable.
- [ ] Critical business transactions operational.
- [ ] Data integrity and reconciliation completed or clear plan in place.
- [ ] Queue offsets, retries, DLQ, and external side effects under control.
- [ ] Login, sessions, caches, and security operational.
- [ ] Traces, metrics, and alerts recovered.
- [ ] RTO/RPO and customer impact recorded.
- [ ] Incident has an owner and action items.
- [ ] Faulty candidate blocked from automatic redeploy.
- [ ] Re-release only after root-cause fix/regression tests.

**Rollback is complete when the service and data are in a verified state**, not merely when the tool reports Deployment Available.

## 45. Common Mistakes

### 45.1. Vague Thresholds

"Roll back if CPU is high" lacks baseline, scope, window, and user impact. Measurable conditions are required.

### 45.2. Looking Only at 5xx

HTTP 200 can still hide data corruption, duplicate payments, or authorization bypass.

### 45.3. Waiting for Samples on a Hard Stop

Never force a verified severe data discrepancy to wait for 500 requests.

### 45.4. Treating Missing Metrics as Pass

Missing telemetry is usually an inconclusive state that must pause or be handled per policy.

### 45.5. Confusing Pause With Rollback

Already-deployed canary pods can keep running; real traffic and lifecycle controls are needed.

### 45.6. Treating Rollback as Only an Image

Schemas, data, queues, and external side effects do not revert automatically.

### 45.7. Auto-Rolling Back on Every Alert

False positives or data incompatibility can make things worse. Only automate when rollback is safe and tested.

### 45.8. No Owner

A valid alert when nobody has authority to act means the release process is not ready.

### 45.9. No Rehearsal

An untested runbook may lack RBAC, images, stable capacity, or the right JVM flags.

### 45.10. Resuming Because the Alert Disappeared

An alert may disappear because canary traffic dropped or the metric pipeline broke. Always verify the cause.

### 45.11. Forcing Roll-Forward Just to Avoid Rollback

Decisions should rest on state compatibility, risk, and recovery, not emotion.

### 45.12. Not Measuring Post-Rollback

A successful undo command does not guarantee checkout, events, and data correctness have recovered.

## 46. Concluding Principles

- **No-go, pause, containment, rollback, and roll-forward** are five distinct types of decisions.
- **Guardrails must be finalized before deploy** and include metric, scope, window, sample, threshold, action, and owner.
- **Hard stops prioritize data/security/business invariants**, without waiting for full statistics once a violation is verified.
- **Soft stops** use canary/control comparison metrics, observation windows, and minimum volume to curb noise.
- **Missing telemetry is not success**, and aggregate metrics can hide candidate regressions.
- **SLO/error budget help evaluate reliability**, but do not replace correctness checks.
- **Java migrations have specific failure modes** such as linkage, reflection, TLS, Jakarta, bytecode agents, GC, and ORM behavior.
- **Canary/blue-green/rolling deployments** all require checking actual traffic, state, and shared resources.
- **Artifact rollback does not automatically restore databases, messages, or side effects**.
- **Expand-and-contract and backward compatibility** keep the stable version working during the rollback window.
- **Automated rollback is only suitable when the action is safe, telemetry is reliable, and it has been rehearsed**.
- **Runbooks must include owners, artifact digests, RBAC, commands, dashboards, and post-recovery tests**.
- **If rollback is unsafe, contain and escalate**, never continue rolling out by default.
- **Assess recovery via SLIs, business invariants, and data integrity**, not just orchestrator status.

In **Java Advance Compatibility Migration**, stop conditions and rollback triggers are not a minor part of the deployment checklist. They are safety guardrails that tell the release team **when not to start, when to cap risk, when returning to stable is viable, and when state must be handled under a separate plan**. When those decisions rest on clear signals, evidence, and ownership, Java/JDK/framework upgrades can proceed in controlled steps with reliable recoverability.
