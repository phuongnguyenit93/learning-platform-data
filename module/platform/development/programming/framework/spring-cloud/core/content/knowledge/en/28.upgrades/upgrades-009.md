# Canary Rollout and Preparing to Roll Back to the Previous Version

> **Chapter:** Upgrades  
> **Module:** SPRING_CLOUD_CORE

A Spring Boot or Spring Cloud upgrade is only considered safe when the new application version can run alongside the old version during the transition period, the system can detect faults early, and the operations team has a tested rollback path. A passing build or a new Pod turning Ready is not enough to declare an upgrade successful.

In a distributed system, a single upgrade can simultaneously change Spring Boot, the Spring Cloud release train, the discovery client, LoadBalancer, configuration loading, actuator endpoints, bean lifecycles, and service-to-service communication behavior. Old and new replicas typically coexist for some period. They may share databases, message brokers, registries, and caches. Therefore, migrations must be designed so both versions operate safely together before retiring the old version.

This lesson builds a canary rollout, signal evaluation, expansion, and rollback procedure for the **SPRING_CLOUD_CORE** module. Key areas include cross-version compatibility, artifact and configuration management, health/readiness, graceful shutdown, traffic routing, database/message contracts, halt criteria, and recovery steps. Examples use Kubernetes Deployments, though the principles apply to other deployment platforms.

## 1. Goals of Canary Rollout and Rollback

Canary rollout introduces the new version to a small scope first. Operations observes real behavior with live or selected traffic, compares against the stable baseline, and expands only with sufficient evidence.

Rollback restores the service to a known-stable application version when the new release breaches error thresholds or fails operational targets. Rollback works only if data, configuration, APIs, events, and dependencies remain compatible with the old version.

A solid upgrade procedure must answer these questions in advance:

- Which Spring Boot and Spring Cloud versions are supported together?
- Can the new version run concurrently with the old version?
- Are database schemas and message schemas backward-compatible?
- How is traffic routed to the canary?
- What conditions permit expanding the rollout?
- What conditions force a halt or rollback?
- Are the previous version's image, configuration, and secrets still available for recovery?
- Who has authority to decide a rollback and who executes it?
- After rolling back, how do we verify traffic and data have stabilized?

Do not wait until a rollout fails to hunt down the old image, old config, or recovery commands. Those artifacts must be prepared before starting.

## 2. Distinguishing Rolling Update, Canary, and Blue-Green

These three strategies differ in how they shift traffic and the level of control they provide.

| Strategy | How it works | When suitable | Key considerations |
| --- | --- | --- | --- |
| Rolling update | Replaces old Pods with new Pods in batches | Frequent releases where versions can run together | During rollout, both versions serve traffic simultaneously |
| Canary | Introduces a small group of the new version to take a slice of traffic, then increases gradually | Risky changes needing comparison against a control group | Requires traffic splitting or weighted routing |
| Blue-green | Maintains two environments; shifts traffic from the old environment to the new one | Needs fast cutover while keeping the old environment for rollback | Resource-intensive and requires managing shared data/config |

### 2.1. A Rolling Update Is Not Automatically a Canary

Kubernetes Deployments default to the `RollingUpdate` strategy. `maxSurge` and `maxUnavailable` control how many extra Pods can be created and how many Pods can be unavailable during replacement.

Rolling updates replace Pods incrementally, yet a standard Kubernetes Service does not automatically split traffic by percentage between two versions. Once both old and new Pods are Ready, both can receive requests through the Service's endpoint selection.

If you need a canary with an explicit traffic percentage, use one of these approaches:

- Create a separate Deployment for the canary and route a fraction of traffic via an Ingress or API gateway.
- Use a service mesh supporting weighted routing.
- Use a progressive delivery platform capable of controlling traffic and evaluating metrics.
- Select canary traffic by header, cookie, tenant, or user group if the architecture supports it.

Do not describe `maxSurge: 1` as "only 1% of traffic goes to the new version." That is a limit on Pod count during rollout, not a traffic weight.

### 2.2. Choosing a Strategy Based on Risk Level

A patch dependency update with no contract changes can use a rolling update with small batches. Upgrading a Spring Cloud release train, changing a discovery provider, or migrating to Config Data should start with an isolated canary for closer observation. Major changes affecting both routing and data may require blue-green or a multi-step migration.

## 3. Verifying Compatibility Before Building Artifacts

Spring Cloud is released in release trains. Each train supports a specific range of Spring Boot versions. Do not upgrade Boot and Cloud by randomly picking the two latest versions and combining them in one build.

### 3.1. Using the BOM and Compatibility Verifier

Manage Spring Cloud modules using the Spring Cloud BOM matching the release train:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

`spring-cloud.version` should be chosen from the official compatibility matrix for Spring Cloud and the Spring Boot version your project uses. Do not override individual versions of Spring Cloud Commons, Config, LoadBalancer, or Netflix integrations when the BOM manages them.

Spring Cloud includes a Compatibility Verifier to check whether the Spring Boot version on the classpath falls within the range accepted by the release train. You can enable the verifier explicitly in test environments:

~~~yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
~~~

The verifier helps catch certain incompatible version pairs right at startup. It does not replace compile tests, integration tests, contract tests, or load tests; an application can pass the verifier and still fail due to APIs, configuration, or specific runtime behavior.

In current Spring Cloud Commons configuration, the verifier is not enabled by default. It focuses on checking the Spring Boot version supported by the release train; do not treat it as a check of the entire dependency graph or full API compatibility across services.

Do not disable the verifier just to make the application start when compatibility warnings appear. Resolve versions using a supported BOM/release train and only override the compatibility list when there is a verified justification.

### 3.2. Building a Version Matrix

Before rollout, record at minimum:

| Component | Current version | Canary version | Evidence |
| --- | --- | --- | --- |
| Java runtime | Running version | Target version | Build and runtime tests |
| Spring Boot | Current release | Target release | Spring Cloud matrix |
| Spring Cloud release train | Current BOM | Target BOM | Release notes and compatibility verifier |
| Spring Cloud Config | Current module | Target module | Config import/profile tests |
| Discovery provider | Current client | Target client | Registry integration tests |
| LoadBalancer | Current module | Target module | Instance selection and cache tests |
| Database driver | Current driver | Target driver | Connection, transaction, and migration tests |
| Message client | Current client | Target client | Producer/consumer contract tests |

Record actual versions from the built artifact, not just the version strings in dependency management files. Transitive dependencies can make the runtime classpath differ from expectations.

### 3.3. Notes on Multi-Step Upgrades

If the version gap is large, break it into supported steps. For example, upgrade Java or Spring Boot first, stabilize, and then upgrade the Spring Cloud release train if the matrix requires it. However, not every intermediate pair is valid; each step must have its own compatible BOM.

Do not skip release notes between intermediate versions. Check changes to deprecated/removed properties, relocated packages/classes, auto-configuration, Config Data, refresh behavior, discovery, and security defaults.

## 4. Preparing Recoverable Artifacts and Configuration

A fast rollback requires knowing the exact artifact running and the exact configuration used to start it.

### 4.1. Using Immutable Images

Build a new image and tag it by version or commit:

~~~text
registry.example.com/platform/order-service:2.8.0
registry.example.com/platform/order-service:2.8.1
~~~

Even better, record the image digest of each release. Tags can be repointed to another image if the registry allows overwrites; a digest uniquely identifies the exact image contents.

A release record should contain:

- Git commit SHA.
- Image digest.
- Java version.
- Spring Boot version.
- Spring Cloud BOM/release train.
- Build ID and build timestamp.
- Config version/label.
- Applied database migrations.
- Key feature flags or toggles.
- Deployment approver and rollback plan.

Do not rebuild "the old version" during an incident if the published image still exists. Use the exact tested artifact to avoid producing a binary different from the one that ran stably.

### 4.2. Versioning Configuration

Configuration is also part of the release. If the canary uses Config Server, record the config repository label/commit or the revision of the ConfigMap/Secret. Avoid mutating shared configuration contents without a version record.

Example of a release-immutable ConfigMap name:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-service-config-r2026-11-18
immutable: true
data:
  application.yml: |
    spring:
      application:
        name: order-service
~~~

Each version's Deployment references a specific ConfigMap. Upon rollback, old Pods can keep using the exact configuration tested alongside them.

Do not put passwords or tokens into a ConfigMap. Use a Secret or secret manager, restrict read permissions, and record the secret version/reference. For credential rotation, maintain an overlap period so both old and new versions work during rollout if the provider supports it.

### 4.3. Do Not Change Remote Configuration Mid-Rollout Without Control

If Spring Cloud Config Server serves configuration, a new commit can affect all running replicas or subsequent refreshes. Separate configuration changes from image changes whenever possible, and record which config label each canary uses.

A rollback plan must restore all of:

- Image/application version.
- Config Server label or ConfigMap revision.
- Secret references if credentials changed.
- Feature flags.
- Routing rules and service selectors.
- Related deployment/environment changes.

## 5. Verifying Compatibility When Old and New Versions Coexist

During a rolling update or canary, both versions can receive requests and read/write shared resources simultaneously. This must be tested beforehand.

### 5.1. Database Schema: Expand Then Contract

Do not deploy a schema change that breaks the old version at the same time as the new application version.

Use the expand-contract workflow:

1. **Expand:** add new columns, tables, or indexes in a way that keeps the old version working.
2. **Deploy compatible code:** the new version can read both old and new schemas or write compatibly.
3. **Migrate data:** backfill data in rate-limited batches.
4. **Switch usage:** transition code to the new field/structure.
5. **Observe:** confirm no old readers/writers still depend on the old schema.
6. **Contract:** drop the old column or constraint in a later release once rolling back to old code is no longer a goal.

Example renaming column `customer_name` to `display_name`:

| Phase | Schema | Old code | New code |
| --- | --- | --- | --- |
| Before migration | Only `customer_name` exists | Reads/writes old column | Not deployed yet |
| Expand | Both columns exist | Keeps using old column | Can read/write both |
| Transition | Both columns kept in sync | Still operates | Reads/writes new column or dual-writes |
| After retiring old code | Both columns still exist | No old instances remain | Uses new column only |
| Contract | Old column dropped | Rollback to old code no longer needed | Uses new column only |

Do not drop the old column as soon as the first canary succeeds. If the application must roll back, old code still needs the schema it understands.

If using dual-writes, both writes must be kept consistent within the same transaction when the same database supports it; if synchronization spans multiple systems, use mechanisms such as transactional outbox, idempotent retries, and reconciliation. Never succeed writing the new column and ignore a failure writing the old column—or vice versa—because both versions could read different values during rollout.

### 5.2. Data Migrations May Be Irreversible

Rolling back a Deployment does not automatically roll back written data. A migration can reformat, backfill, or delete data that old code does not understand.

Before migrating:

- Identify which migrations are additive-only and which transform/delete data.
- Prefer migrations that can run while both versions are active.
- Back up and verify restore/PITR capability before any destructive operation.
- Run the migration on representative data and measure duration/locks.
- Do not run destructive migrations automatically alongside a canary without a data recovery plan.

Do not assume running a down-migration script works during rollback. Some data transformations cannot be reversed safely; database restoration is a separate procedure and can lose transactions committed after the backup point.

### 5.3. API and Message Contracts

If the new service alters APIs or event schemas, old consumers and producers may still be running. Prefer additive changes:

- Add optional fields instead of changing existing field types.
- Do not change the meaning of existing fields in the same release.
- Keep old endpoints while consumers transition.
- Consumers ignore unknown fields when the contract permits.
- New producers do not emit events that old consumers cannot parse.
- Use schema versioning and test backward/forward compatibility for messages.

For event-driven systems, test both new producer with old consumer and old producer with new consumer. If the two directions are incompatible, deploy adapters, versioned topics, or multi-step changes.

### 5.4. Discovery, Registry, and LoadBalancer

During an upgrade, old and new instances may register under the same service ID. Ensure:

- Both versions register metadata understood by clients.
- Registration health/status is interpreted consistently by the provider.
- Old clients do not pick new instances if protocols/configs are incompatible.
- New clients can still call old instances during the transition period.
- Discovery/LoadBalancer caches do not retain failing instances for too long.
- Service IDs or port metadata are not changed in ways that prevent old clients from finding the service.

If changing discovery providers or metadata schemas, deploy a compatibility layer or separate service IDs by version during the transition.

## 6. Designing an Observable Canary

A canary is only useful if you can distinguish the new version's signals from the stable group.

### 6.1. Adding Version Labels

Attach release labels to Pods, metrics, and logs:

~~~yaml
metadata:
  labels:
    app: order-service
    app.kubernetes.io/name: order-service
    app.kubernetes.io/version: "2.8.1"
    release-track: canary
~~~

Include version/commit in application info or structured logs as non-sensitive metadata. Metric labels must bound cardinality; do not put request IDs, user IDs, or unbounded random values into tags.

### 6.2. Isolating Canary Traffic

Example using two Deployments:

- `order-service-stable`: the primary serving version.
- `order-service-canary`: the new version starting with one replica.

Create a separate Service for the canary and configure the Ingress/service mesh/API gateway to send a small percentage of traffic to that Service. If the platform does not support weighted routing, select request subsets via headers/tenants or use a suitable progressive delivery mechanism.

Do not infer traffic share solely from Pod count. A single canary replica can receive a higher share of requests than expected if requests are unevenly distributed or routing is misconfigured.

### 6.3. Selecting Safe Canary Traffic

Start with lower-risk traffic that still represents real behavior:

- Read requests before write requests when possible.
- Internal tenant groups or test users.
- A small percentage of requests without irreversible transactions.
- Avoid large batch jobs during the initial stage.
- Keep the same authentication, networking, and downstream conditions as production.

If testing write paths is necessary, use reconcilable transactions or isolated test data. Never let a canary accidentally send duplicate emails, payments, or customer-facing events without safeguards.

## 7. Configuring Rollout and Readiness on Kubernetes

A basic rolling-update Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 6
  revisionHistoryLimit: 10
  minReadySeconds: 20
  progressDeadlineSeconds: 600
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: registry.example.com/platform/order-service:2.8.1
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

`maxUnavailable: 0` maintains the desired Ready Pod count during rollout, provided the cluster has capacity for surge Pods. `maxSurge: 1` bounds extra Pods. Values must fit quotas, capacity, connection limits, and cluster cost.

`minReadySeconds` requires a Pod to stay Ready for a minimum interval before being considered available. `progressDeadlineSeconds` helps detect stalled rollouts. The readiness probe must reflect ability to serve traffic; the liveness probe should not depend on databases or external services that can fail temporarily.

For applications with long or variable startup times after a framework upgrade, use a startup probe so Kubernetes waits for startup before applying liveness/readiness:

~~~yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 30
~~~

This example allows roughly up to five minutes for the startup probe to succeed. Set thresholds based on actual startup time; an overly generous startup probe delays detecting a hung startup.

### 7.1. Spring Boot Readiness and Liveness

Spring Boot Actuator can expose:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

In Kubernetes environments, these health groups reflect `ApplicationAvailability`. By default, Spring Boot does not automatically include every health indicator in readiness. Only include an external dependency in readiness when the application truly cannot serve traffic if that dependency fails.

Probe endpoints must be exposed and reachable on the port kubelet queries. If Actuator uses a separate management port, consider enabling probe paths on the main server port to avoid situations where the management context looks healthy while the main web server cannot accept requests.

Do not mechanically add the database or registry to liveness. If a shared dependency experiences an outage, all Pods could restart simultaneously and worsen the incident.

### 7.2. Graceful Shutdown

When an old Pod is replaced, in-flight requests must be allowed to complete during shutdown:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Kubernetes needs `terminationGracePeriodSeconds` to be greater than or equal to the time the application needs to stop plus any preStop/infrastructure drain interval. Align readiness, service registry deregistration, load balancer propagation, and graceful shutdown so an instance stops receiving new requests while shutting down.

Do not set the graceful shutdown timeout shorter than the longest allowed request duration in the system. Conversely, an excessively long timeout slows rollouts and ties up resources.

## 8. Defining the Baseline and Go/No-Go Criteria

Before the canary, capture a baseline from the stable version over a comparable time window and similar load conditions.

### 8.1. Signals to Monitor

| Category | Signals |
| --- | --- |
| Availability | Request success rate, HTTP 5xx, timeouts, readiness failures |
| Latency | p50, p95, p99 per endpoint and dependency |
| Saturation | CPU, memory, GC pauses, thread pools, connection pools |
| Startup | Startup duration, bean creation errors, restart counts |
| Discovery | Registry errors, instance refresh latency, empty instance lookup counts |
| LoadBalancer | Instance selection errors, failed/discarded requests, per-instance request distribution |
| Config | Config Server fetch errors, binding failures, actual config version |
| Database | Connection count, lock waits, query latency, deadlocks |
| Messaging | Consumer lag, retries, dead-letter queues, serialization errors |
| Business | Transaction success rate, corrupt data, duplicate or skipped jobs |

Compare the canary against stable by rate and matching traffic types. A canary group with low volume can have a small absolute error count yet a very high error rate.

### 8.2. Define Thresholds Before Deployment

Do not pick thresholds after looking at the charts. Specify clearly:

- Maximum allowed error rate.
- Maximum p95/p99 increase relative to baseline.
- Permitted restart or readiness failure count.
- Maximum CPU/memory/connection thresholds.
- Maximum queue lag and event processing time.
- Unacceptable business errors.
- Minimum observation window per step.

Illustrative example, not universal SLOs:

| Condition | Decision |
| --- | --- |
| 5xx rises by more than 1 percentage point over stable for 5 minutes | Halt expansion and investigate |
| p95 increases by more than 20% under comparable traffic | Hold canary, profile performance |
| Repeated readiness failures or Pod crash loops | Halt rollout |
| Database connections exceed operational limit | Halt expansion |
| Data mismatch or duplicate transactions | Halt immediately, handle data incident |
| Canary stays stable across a representative traffic cycle with no SLO violations | Eligible to increase share |

Actual thresholds must be based on the service's SLOs, baseline, and capacity. For data corruption, security issues, or financial transaction bugs, do not wait out the observation window before halting.

### 8.3. Observe Long Enough

A few minutes is not enough if the service runs hourly batch jobs, experiences time-of-day traffic shifts, or has slow event consumers. The canary must traverse critical flows and necessary business cycles before expanding.

If waiting through a full cycle is impractical, supplement with replay tests, synthetic transactions, or staging tests using representative data/traffic and document what remains unverified.

## 9. Step-by-Step Canary Rollout Procedure

A runbook applicable to a Spring Cloud release train upgrade:

1. **Freeze unrelated changes:** avoid changing code, schemas, config, and routing outside the release scope simultaneously.
2. **Capture baseline:** snapshot metrics, logs, config versions, dependency versions, and registry state.
3. **Run preflight checks:** BOM/compatibility, startup tests, integration tests, contract tests, and database migrations.
4. **Deploy canary:** launch one replica or a small group using the new image digest.
5. **Verify startup:** check logs, readiness, liveness, Config Server, and discovery.
6. **Run smoke tests:** invoke key APIs, confirming authentication, routing, persistence, and messaging.
7. **Send small traffic slice:** use prepared routing rules; do not infer percentages from replica counts.
8. **Compare with stable:** watch error rates, latency, saturation, and business metrics.
9. **Verify cross-version compatibility:** confirm old clients call the new server and new clients call the old server if both directions can occur.
10. **Ramp traffic in steps:** increase only when every threshold passes.
11. **Expand replicas:** proceed in batches while keeping rollback artifacts/configs ready.
12. **Complete rollout:** verify all instances run the new version, the registry is clean, and no old consumers remain unprocessed.
13. **Hold a stabilization period:** do not run destructive contract migrations or delete old code in the same rollout.
14. **Close the release:** archive metrics, config revisions, image digests, decisions, and resolved incidents.

If any step fails, stop expanding. Do not increase traffic merely because Pods report Ready.

## 10. Example Rollout Control Commands

Check status:

~~~bash
kubectl rollout status deployment/order-service
kubectl get pods -l app=order-service -o wide
kubectl describe deployment/order-service
~~~

View history:

~~~bash
kubectl rollout history deployment/order-service
~~~

Pause a rolling update to inspect:

~~~bash
kubectl rollout pause deployment/order-service
~~~

Resume once verified:

~~~bash
kubectl rollout resume deployment/order-service
~~~

If using a separate canary Deployment, control traffic via the gateway/service mesh. The rollout commands above control only the Deployment; they do not automatically adjust Ingress or service mesh traffic weights.

## 11. Deciding to Roll Back

Roll back when the new version breaches halt criteria or there is clear evidence it degrades reliability. Do not wait for failures to spread just to gather more data.

### 11.1. Signals Requiring Immediate Rollback

- Transactions are lost, duplicated, or written with corrupt data.
- Security vulnerabilities or broken access permissions.
- Canary raises 5xx/timeouts beyond defined thresholds.
- Unrecoverable startup errors or crash loops within the allowed window.
- Discovery/LoadBalancer fails to route to critical services.
- Message consumers fail to parse events or cause a surge in dead-letter queues.
- Connection pools or thread pools are exhausted.
- New configuration prevents the service from fulfilling business logic.
- Data integrity cannot be verified after changes.

A severe business bug may require stopping canary traffic even when health endpoints still report `UP`.

### 11.2. Distinguishing Rollback from Roll-Forward

Some bugs can be resolved via configuration or a feature flag without changing the image. In those cases, a roll-forward may be faster and less risky.

Application rollback fits when the new binary is the culprit and the old version remains compatible with current data/config. If the schema changed in a way old code cannot read, rolling back the image can worsen the incident.

Before deciding, pinpoint the faulty layer:

- Image/application code.
- Config Server/ConfigMap/Secret.
- Database schema/data.
- Service contract or message schema.
- Routing/discovery/registry.
- Infrastructure or external dependencies.

Pick the matching recovery action; do not run `kubectl rollout undo` expecting it to revert the database, Config Server, or traffic routing.

## 12. Kubernetes Rollback Runbook

When deciding to roll back:

1. Stop ramping traffic and pause the rollout if needed.
2. Shift traffic off the canary or scale the canary to 0 if using separate Deployments.
3. Record the release, config revision, metrics, logs, and failure timestamp.
4. Confirm the database schema remains compatible with the previous version.
5. Restore the known-stable image digest or Deployment revision.
6. Restore config/secret references and feature flags if they changed.
7. Wait for the rollback rollout to complete.
8. Verify readiness and run smoke tests.
9. Check registry, LoadBalancer, queues, and connection pools.
10. Monitor error rates and business metrics after rollback.
11. Reconcile data/transactions created during the canary window.
12. Document root cause and block contract migration steps until safe.

Example viewing history and rolling back to the previous revision:

~~~bash
kubectl rollout history deployment/order-service
kubectl rollout undo deployment/order-service
kubectl rollout status deployment/order-service
~~~

Roll back to a specific revision:

~~~bash
kubectl rollout undo deployment/order-service --to-revision=12
kubectl rollout status deployment/order-service
~~~

Revision numbers in examples are illustrative. Before running, verify which revision holds the exact image/config template to restore. Deployment history retains only `revisionHistoryLimit` ReplicaSets; if set to 0, no prior revisions remain to roll back this way.

### 12.1. Rolling Back Canary Traffic

If the canary uses a separate Deployment:

- Set the weighted route to 0% for the canary.
- Confirm new requests no longer reach the canary.
- Allow in-flight requests to finish or drain per policy.
- Scale the canary to 0 or retain it for investigation per incident policy.
- Preserve logs/metrics and image digests for analysis.

If using blue-green, switch the route/service selector back to the known-stable blue environment. Check gateway DNS/caches/connection pooling to confirm traffic has genuinely returned.

### 12.2. Restoring Configuration

If Config Server published a new label, restore the label/reference compatible with the old version. If using versioned ConfigMaps, point the Deployment back to the old ConfigMap name. If secrets rotated, ensure old credentials remain valid or issue compatible credentials before rolling back.

Do not delete old secrets immediately after issuing new secrets. An overlap window lets both versions keep operating during transitions.

### 12.3. Post-Rollback Verification

Rollback is complete only when:

- All serving Pods run the right image.
- Readiness is stable and restart counts are not climbing abnormally.
- Routing no longer sends requests to the faulty canary.
- The registry has no invalid old/new instance statuses.
- Error rates and latency return to baseline.
- Consumer lag and dead-letter queues are under control.
- Database connections and pools are stable.
- Transactions from the rollout window are reconciled.
- Config versions and secret references match the restored release.

## 13. Preparing Rollback for Databases and Messages

### 13.1. Do Not Automatically Run Down Migrations on Application Rollback

If a migration only added columns or indexes that old code ignores, you can usually keep the expanded schema while rolling back code. Dropping newly added structures immediately can lose data or break new code still running on another replica.

If a migration deleted or altered the meaning of data, a dedicated recovery plan is needed. Restoring from a backup or point-in-time recovery may be required, though that can discard transactions committed after the restore point. Assess data impact before acting.

### 13.2. Message Queues May Retain Events from the New Version

Old consumers may read messages emitted by new producers after a rollback. Therefore:

- Keep event schemas compatible during the transition window.
- Do not delete old fields as soon as the new producer starts running.
- If a new event version is incompatible, route to a separate topic/version or use an adapter.
- Monitor dead-letter queues and retries.
- Do not purge queues to "clear" errors without assessing data impact.
- Verify idempotency when replaying messages after rollback.

### 13.3. API Consumers/Producers

If the new service published a new API contract, rolling back the producer can leave new consumers calling an endpoint that no longer exists. Keep old endpoints until consumers have fully migrated or use a gateway adapter handling both contracts.

A helpful rule: deploy additive changes first, migrate consumers next, and remove old contracts in a separate release once no callers remain.

## 14. Automating Canary and Rollback Criteria

A progressive delivery pipeline can evaluate metrics before increasing traffic. Rules must be explicit and auditable:

~~~yaml
# Illustrative pseudocode, not the schema of a specific controller
canary:
  initialWeight: 5
  steps:
    - weight: 5
      duration: 10m
    - weight: 15
      duration: 15m
    - weight: 30
      duration: 20m
    - weight: 50
      duration: 30m
  analysis:
    metrics:
      - name: http_5xx_rate
        max: 0.01
      - name: p95_latency_ratio
        max: 1.20
      - name: readiness_failures
        max: 0
  onFailure: pause-and-rollback
~~~

The numbers merely illustrate how to express policy. Actual schemas depend on Argo Rollouts, Flagger, or your progressive delivery platform. Do not copy pseudocode into a Kubernetes Deployment manifest.

A solid pipeline should:

- Capture baselines for stable and canary over the same time window.
- Compare error rates, not just absolute error counts.
- Include dedicated thresholds for business errors and data integrity.
- Automatically halt when metrics lack sufficient data.
- Record decisions and approvers.
- Never automatically roll back databases or data when rolling back the application.
- Allow operators to pause when signals appear outside dashboards.

Do not automatically raise traffic if telemetry is missing or the canary has not received enough representative requests. "No error data" is different from "proven error-free."

## 15. Rehearsing Rollback Before Production

Rollback must be rehearsed in staging or an environment with production-like topology.

A rehearsal should verify:

1. The old image digest and Deployment revision can be located accurately.
2. Old Config/Secret versions still exist and remain readable.
3. Traffic can shift off the canary within the target time.
4. `kubectl rollout undo` or the GitOps workflow restores the exact previous Pod template.
5. Readiness and graceful shutdown work.
6. The current database schema remains compatible with old code.
7. Old consumers can still process messages in the queue.
8. The discovery registry removes faulty new instances and retains stable instances.
9. Metrics/logs show when rollback started, paused, and finished.
10. On-call staff know who decides, who executes, and how to communicate internally.

Measure the time from rollback decision until traffic stabilizes. Compare it against the service's RTO target. If rollback takes longer than business error tolerance, improve automation or the deployment strategy.

## 16. Pre-, During-, and Post-Canary Checklists

### Pre-Deployment

- [ ] Spring Boot and Spring Cloud BOM are within the compatibility matrix.
- [ ] Compatibility verifier and startup tests have run.
- [ ] Image digest, commit, and dependency versions are recorded.
- [ ] Config/Secret versions for stable and canary are saved.
- [ ] API, database, and message contracts are compatible across both versions.
- [ ] Expand migration is complete and does not break old code.
- [ ] Baseline metrics and stop/go thresholds exist.
- [ ] Canary routing rules and a path to restore traffic to stable exist.
- [ ] Readiness/liveness and graceful shutdown have been tested.
- [ ] Rollback commands and accountable owners are defined.
- [ ] Rollback has been rehearsed in an appropriate environment.

### During Deployment

- [ ] Canary receives only the intended traffic share.
- [ ] Startup, readiness, discovery, and config loading are stable.
- [ ] Error rate and latency are compared against stable.
- [ ] Database, broker, and connection pools stay within limits.
- [ ] No data corruption or message incompatibility occurs.
- [ ] Every traffic increment has an explicit decision.
- [ ] Rollout can be paused immediately if metrics look abnormal.

### Post-Deployment

- [ ] All replicas run the expected image digest.
- [ ] No unexpected old instances remain.
- [ ] Registry and LoadBalancer reflect the new instance list.
- [ ] Config versions and secret references are uniform.
- [ ] Error rate, latency, and business metrics are stable.
- [ ] Database migration has not contracted too early.
- [ ] Message queues have no abnormal backlog.
- [ ] Release record and canary results are archived.
- [ ] Contract migration timing is scheduled separately.

## 17. Illustrative Scenario: Upgrading a Spring Cloud Release Train

Suppose `order-service` runs an older release train and needs to upgrade Spring Boot/Spring Cloud with a new BOM. The application uses Config Server, Eureka, LoadBalancer, PostgreSQL, and Kafka.

A viable plan could be:

1. Create an upgrade branch and update Spring Boot and the Spring Cloud BOM per the support matrix.
2. Run unit, auto-configuration, Config Data, Eureka, LoadBalancer, and Kafka integration tests.
3. Add new database columns via an expand migration while keeping old columns.
4. Ensure producers still emit events compatible with old consumers.
5. Build an immutable image and record its digest alongside the config label.
6. Create a separate canary Deployment with one replica.
7. Route 5% of read traffic to the canary; hold off on high-risk write paths initially.
8. Monitor startup, 5xx, p95/p99, registry, connection pools, and consumer lag.
9. Increase traffic incrementally as thresholds pass.
10. Once all replicas run the new version, keep monitoring for a full business cycle.
11. Keep old database columns and old event contracts throughout the rollback window.
12. Contract schemas/APIs only in a later release once no old code needs compatibility.

If the canary fails because LoadBalancer picks wrong instances, stop increasing traffic, shift traffic back to stable, preserve the image/logs/config revision, and inspect discovery caching and provider status. If the failure is schema-related, do not roll back the image before confirming old code can still read the current schema.

## 18. Common Mistakes and How to Avoid Them

1. **Treating rolling updates as canary traffic:** use weighted routing when a specific traffic percentage is needed.
2. **Upgrading Boot and Cloud without the BOM:** check the release train and compatibility verifier.
3. **Not saving the old image digest:** you cannot be sure you rolled back to the exact binary.
4. **Editing ConfigMaps/Secrets in place:** version configuration and keep revisions.
5. **Checking only Pod Ready:** monitor business metrics, latency, and downstream errors too.
6. **Making liveness depend on the database:** avoid restart storms when external dependencies fail.
7. **Leaving graceful shutdown disabled:** in-flight requests can be severed when Pods are replaced.
8. **Dropping database columns right after rollout:** old code may no longer be able to roll back.
9. **Making incompatible message schema changes:** old/new producers and consumers may fail to parse events.
10. **Rolling back only the image:** also restore config, routing, feature flags, and secret references if they changed.
11. **Running down migrations automatically:** can lose data or break the schema needed by the old version.
12. **Never testing rollback:** an unrehearsed procedure usually takes longer than expected.
13. **Increasing traffic when telemetry is missing:** missing data is not a safety signal.
14. **Contracting right after the canary:** keep the compatibility window open long enough for rollback and consumer lag.

## 19. Key Takeaways

Canary rollout catches issues before all traffic shifts to a new version; rollback restores service when a new version misses thresholds. Both are reliable only when old and new versions can coexist, old artifacts/configs remain intact, schemas/APIs/messages are compatible, and stop/go criteria are defined upfront.

For **SPRING_CLOUD_CORE**, use the right Spring Cloud BOM, check the compatibility verifier, deploy canaries with explicit routing, monitor readiness alongside business metrics, enable graceful shutdown, and apply expand-contract for databases. When rolling back, restore the image together with required config/routing, verify the registry, and reconcile data. Remove old schemas or contracts only after the rollback window closes and no old consumers remain.

## References

- [Spring Cloud Commons — Compatibility Verification](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Release Trains and Compatibility](https://spring.io/projects/spring-cloud#overview)
- [Spring Boot Actuator — Kubernetes Probes and Availability](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Kubernetes — Update a Deployment Without Downtime](https://kubernetes.io/docs/tasks/run-application/update-deployment-rolling/)
- [Kubernetes — Deployment Rollback](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Martin Fowler — Evolutionary Database Design](https://martinfowler.com/articles/evodb.html)
