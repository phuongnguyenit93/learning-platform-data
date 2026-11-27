# Planning Cutover, Rollback, and Legacy Infrastructure Decommissioning

Migrating an application to serverless does not end when the new function deploys successfully. The legacy and new systems may coexist for a period; data may be written in two places; events may arrive late or be redelivered; DNS, queues, schedulers, and clients may still call old endpoints. If traffic shifts without controlling these factors, an organization can create duplicate orders, lose events, corrupt state, or lose the ability to revert to the prior version.

**Cutover** is the moment or phase when part or all of a workload transitions from the legacy system to the serverless system. **Rollback** is the procedure to return traffic or processing to a prior safe state when operational or business criteria are not met. **Decommission** is the controlled teardown of legacy infrastructure after confirming zero remaining dependencies and satisfying retention, audit, and recovery requirements.

This lesson explains how to plan migrations in waves, prepare data and events, choose a traffic cutover strategy, set rollback triggers, validate post-cutover correctness, and decommission the legacy system. Examples focus on Java FaaS triggered by HTTP, queues, streams, schedulers, or event buses.

## 1. Migration Goals and Principles

### 1.1. A Successful Migration Is Measured by Outcomes

A migration is considered successful only when the new workload meets business and operational requirements in production. Typical criteria include:

- Functionality and API/event contracts uphold committed behavior;
- Data is complete, consistent, and reconcilable;
- Latency, availability, throughput, and freshness meet SLOs;
- Retries, duplicate deliveries, and partial failures are handled safely;
- IAM, networking, encryption, retention, and auditing comply with policy;
- Cost per successful transaction stays within acceptable bounds;
- Operations teams have dashboards, runbooks, permissions, and escalation paths;
- A rollback/forward-recovery plan has been rehearsed;
- Legacy infrastructure is decommissioned only after dependencies and retention needs expire.

The number of deployed functions or percentage of shifted traffic alone is not proof of success.

### 1.2. Do Not Migrate Everything at Once Unless Necessary

Split the migration into waves by bounded context, API, tenant, event type, or workload group. Each wave has its own owner, dependencies, data boundaries, success criteria, and rollback plan.

Small waves limit blast radius and let you learn from real traffic. However, slicing too finely can prolong coexistence, dual operations, and parallel-run costs. Balance cutover risk against the cost of maintaining two systems.

### 1.3. Maintain One Source of Truth per Data Type

During transition, data copies may exist in both legacy and serverless stores. Yet for every aggregate/table/entity, you must know which system is the authoritative writer at any given moment.

Two systems independently accepting writes without explicit conflict resolution risk split-brain. If dual-write is needed, use outbox/CDC and ownership/version rules; never treat two separate writes as atomic.

### 1.4. Rollback Must Be Designed Before Cutover

You cannot simply write "if it breaks, point traffic back to legacy." Rollback may be unsafe if the new system has written data under a new schema, emitted new events, or executed irreversible side effects.

Before cutover, answer:

- How long after shifting traffic can we still roll back?
- Can new writes be brought back to the legacy system?
- Has new data been reverse-synced?
- Can the old schema read newly written data?
- Which events were published and who consumed them?
- Which operations require compensation/reconciliation?
- Who holds authority to trigger rollback, and within what timebox?

## 2. Surveying Workloads and Choosing a Migration Strategy

### 2.1. Build an Inventory

Before designing cutover, list:

- Services, APIs, batch jobs, crons/schedulers, and consumers;
- Inbound/outbound dependencies;
- Databases, schemas, object storage, caches, and search indexes;
- Queues/topics/streams, partition keys, retention, and consumer groups;
- Secrets, certificates, IAM principals, and network paths;
- Traffic volume, peaks/bursts, payload sizes, and latency distributions;
- Stateful sessions, local filesystems, connection pools, and background threads;
- Data classification, residency, retention, and recovery requirements;
- Service owners, on-call rotations, SLOs, and cost centers.

For Java applications, flag assumptions incompatible with FaaS: long-lived processes, in-memory state, persistent local files, singleton schedulers, background threads, large connection pools, long transactions, or instance-bound sessions.

### 2.2. Pre-Migration Baseline

Measure at least one representative business cycle, including peak and off-peak windows if applicable:

- Request/event rates and concurrency;
- p50/p95/p99 latency;
- Success/error/timeout rates;
- Queue lag and oldest message age;
- Database CPU/IO/lock waits/connection counts;
- Retry, duplicate, and DLQ rates;
- Data volume and growth rate;
- Cost per request and cost per successful transaction;
- Operational toil and incident frequency.

The baseline is your post-cutover benchmark. Do not compare raw total bills alone because traffic and business mix can change.

### 2.3. Choosing a Transition Approach

| Strategy | Approach | When Appropriate | Primary Risks |
| --- | --- | --- | --- |
| Rehost/replatform | Shift runtime/deployment with minimal logic changes | Relatively stateless app, compatible dependencies | Preserves legacy coupling and cost structure |
| Refactor into functions | Extract handlers by HTTP/event/workflow | Clear bounded contexts and contracts | Changes runtime behavior and transaction boundaries |
| Strangler | Migrate capabilities one by one via gateway/router | Large systems requiring coexistence | Complex routing and data ownership |
| Big-bang | Cut over everything in one window | Small workloads where downtime is acceptable | Large blast radius and heavy rollback |
| Blue-green | Two complete stacks; switch traffic between them | Equivalent environments can be maintained | Data compatibility and double-running costs |
| Canary | Shift a small share and ramp gradually | Traffic can be split with strong telemetry | Must control cohort state/data |
| Queue drain then switch | Pause/throttle producers, drain backlog, then swap consumers | Workloads needing ordering or avoiding dual consumers | May require downtime and backlog builds while draining |
| Read/write split | Migrate reads first, then transfer write ownership | Queries can be separated from transactions | Different read/write semantics and stale-data risk |

A migration can combine strangler at the capability level with canary at the traffic level.

### 2.4. Identifying Unsuitable Conditions

FaaS is not automatically right for every workload. Re-evaluate if the application relies on:

- Continuously running processes or background daemons;
- Long-lived connections unsupported by the platform;
- Local filesystems required to retain state;
- Ultra-tight latency budgets where cold starts cannot be controlled;
- High sustained steady load where always-on containers/services are more economical;
- Long transactions or stateful sessions spanning multiple requests;
- Libraries/native runtimes incompatible with the function environment.

You can keep some workloads on containers/VMs and move only suitable parts to FaaS. The goal is sensible operational boundaries, not forcing everything into functions at any cost.

## 3. Designing Migration Waves and Dependency Graphs

### 3.1. Slicing by Business Capability

For example, an e-commerce system might be sliced into:

1. Notification and email event handlers.
2. Catalog read API.
3. Order intake HTTP API.
4. Inventory reservation consumer.
5. Payment workflow.
6. Reporting/export batch jobs.

The order does not have to match this exact sequence. Prioritize capabilities with clear boundaries, minimal shared writes, and independent measurability. Payment/inventory flows usually demand stricter correctness controls and thorough rehearsal.

### 3.2. Building a Dependency Graph

Map services, data stores, event sources, identities, and external APIs as nodes, showing read/write directions. Annotate every edge with:

- Protocol and contract;
- Producer/consumer owners;
- Timeout/retry semantics;
- Authentication/authorization;
- Schema/version;
- Data classification;
- Behavior on dependency failure.

A dependency graph reveals when a new function still depends on the legacy database, legacy scheduler, or an unmigrated service.

### 3.3. Wave Plan

Each wave should maintain a record:

| Attribute | Contents |
| --- | --- |
| Scope | APIs/events/tenants/workloads being migrated |
| Owner | Accountable team and technical lead |
| Dependencies | Data, queues, APIs, IAM, networking |
| Migration method | Canary, blue-green, strangler, batch |
| Data plan | Snapshot, CDC, freeze, reconciliation |
| Cutover window | Timing, duration, and traffic profile |
| Success criteria | SLOs, business correctness, cost |
| Rollback triggers | Concrete thresholds and evaluation windows |
| Rollback steps | Who does what, and in what order |
| Hypercare | On-call staff, duration, and dashboards |
| Decommission gate | Conditions to tear down legacy resources |

### 3.4. Dependency Sequencing

Migrate capabilities according to the dependency graph. For instance, if a new consumer expects event schema v2, the legacy producer must emit a compatible schema or the consumer must handle both v1/v2 beforehand. Never cut over a producer before all necessary consumers understand the new contract.

## 4. Preparing the Java Serverless Architecture

### 4.1. Separating Business Logic from Adapters

Keep business logic in the service/domain layer and place HTTP, queue, stream, or scheduler handlers in adapters. This lets the same logic run through both legacy entry points and FaaS adapters during coexistence.

```text
HTTP API / Legacy Controller ----+
                                 |
Queue / Stream Function ----------+--> Application Service --> Ports
                                 |                         |
Scheduler Function --------------+                         +--> Repository
                                                           +--> Event Publisher
                                                           +--> External Client
```

Adapters handle payload parsing, auth context, retry/ack semantics, and response mapping. Domain services should not depend directly on cloud-provider-specific event objects.

### 4.2. Contract Compatibility

Maintain API/event compatibility during the transition:

- Support new optional fields;
- Do not change meanings of existing fields;
- Version events explicitly;
- Consumers handle both old and new schemas within the migration window;
- Do not emit v2 events before required consumers are ready;
- Preserve error semantics and idempotency behavior.

### 4.3. Externalizing Configuration from Artifacts

Endpoints, table/queue names, feature flags, timeouts, and concurrency limits should be configured per environment. Java artifacts should remain immutable across dev/staging/production; record config revisions in release logs.

Reference secrets from a secret manager rather than embedding them in JARs/containers or version-controlled config files. At cutover, confirm the new runtime identity reads the right secrets and network routes.

### 4.4. Stateless Handlers and Durable State

Do not move state from singletons/static fields into functions assuming warm environments will keep it. Sessions, idempotency records, workflow state, and checkpoints belong in durable services. Local caches are purely disposable optimizations.

### 4.5. Java Example: Routing by Migration Cohort

Example application-level router choosing legacy or serverless by tenant cohort. Decisions must stay stable for a tenant within a wave and be logged for troubleshooting:

```java
public enum ProcessingTarget {
    LEGACY,
    SERVERLESS
}

public interface MigrationCohortPolicy {
    ProcessingTarget targetFor(String tenantId);
}

public final class OrderFacade {
    private final MigrationCohortPolicy policy;
    private final OrderProcessor legacy;
    private final OrderProcessor serverless;

    public OrderFacade(
            MigrationCohortPolicy policy,
            OrderProcessor legacy,
            OrderProcessor serverless) {
        this.policy = policy;
        this.legacy = legacy;
        this.serverless = serverless;
    }

    public OrderResult submit(String tenantId, OrderCommand command) {
        return switch (policy.targetFor(tenantId)) {
            case LEGACY -> legacy.submit(tenantId, command);
            case SERVERLESS -> serverless.submit(tenantId, command);
        };
    }
}
```

This is an illustrative router. Policies should come from an audited feature/config service with safe fallbacks and never change randomly between retries. If a business transaction starts on legacy, subsequent steps must honor that transaction's owner/route so part does not run on legacy while another unexpectedly hits serverless.

## 5. Data Migration: Snapshot, CDC, and Final Sync

### 5.1. Choosing a Data Strategy

| Approach | Description | Best Suited For | Notes |
| --- | --- | --- | --- |
| Offline copy | Stop writes, export/import, then open the new system | Small datasets, downtime acceptable | Simple, but requires an explicit stop window |
| Snapshot + CDC | Copy snapshot, then stream subsequent changes via CDC | Large datasets, minimal downtime | Must manage ordering, lag, and checkpoints |
| Continuous replication | Sync data throughout coexistence | Flexible cutover timing | Define one direction/owner; avoid unplanned multi-master |
| Logical export/import | Transfer via intermediate files/formats | Different DB engines/schemas | Validate encoding, types, and constraints |
| Event replay | Rebuild read models from event logs | Complete event history and safe replay | Depends on retention, ordering, and idempotency |

### 5.2. Snapshot + CDC

A typical sequence:

1. Capture a consistent snapshot at time T0.
2. Import the snapshot into the target database.
3. Start/resume CDC from the log position matching T0.
4. Apply changes in required order while maintaining checkpoints.
5. Monitor replication lag and apply errors.
6. At cutover, block new source writes or transfer write ownership per plan.
7. Drain in-flight transactions and wait for CDC to reach the final watermark.
8. Run checksums/counts/reconciliation.
9. Open the write path on the target.

Understand your CDC tool's semantics: snapshot boundaries, transaction ordering, deletes/tombstones, schema changes, and retries. Never assume "lag equals 0" automatically proves all business data is valid.

### 5.3. Avoid Arbitrary Dual-Writes

A Java pattern writing to the legacy DB then the target DB via two independent calls has clear failure modes:

- Legacy commits, target fails;
- Target commits, legacy fails;
- Response timeouts cause callers to retry and write twice;
- One DB receives a newer update first, scrambling update order.

When dual-write is necessary, use CDC/outbox or a replication mechanism with well-defined semantics. If writing to two places is unavoidable, persist operation IDs, versions, and sync status, paired with reconciliation and repair processes. Never assume two databases commit atomically.

### 5.4. One Authoritative Writer

In each stage, specify which system owns canonical writes:

| Stage | Source | Target | Rules |
| --- | --- | --- | --- |
| Initial copy | Primary writer | Read/replica | Snapshot + CDC source → target |
| Canary read | Primary writer | Read-only/candidate | Compare outputs; block target from emitting side effects |
| Canary write | Per cohort | Writer for migrated cohorts | One owner per aggregate/tenant |
| Full cutover | Read-only/retired writer | Primary writer | Fence source writes and verify target |
| Rollback window | Per rollback design | Per rollback design | Reverse sync or forward recovery prepared |

If splitting ownership by tenant, routing and data partitioning must guarantee a tenant never has two systems acting as writer simultaneously.

### 5.5. Schema Expand-Migrate-Contract

When evolving schemas:

1. **Expand:** add backward-compatible fields/tables/indexes.
2. **Migrate:** deploy compatible readers/writers and backfill data.
3. **Validate:** verify old/new data and consumer compatibility.
4. **Contract:** drop old fields/formats only after all old readers/writers stop and the rollback window ends.

Do not drop columns or alter semantics right before cutover if rollback requires old binaries to read target data. Maintain compatibility long enough for both release rollbacks and delayed events.

### 5.6. Data Verification

Verify across multiple layers:

- Row/document counts by partition/tenant/time window;
- Checksums/hashes over canonicalized data;
- Aggregate totals such as balances, inventory, and order counts;
- Null/missing fields and enum values;
- Foreign-key/reference consistency;
- Duplicate business keys;
- Timestamps/timezones and numeric precision;
- Sequence/version gaps;
- Event/outbox/inbox reconciliation.

Matching counts do not guarantee matching contents. Full-table checksums can be expensive; verify by partition, sampling, and critical business invariants.

## 6. Event Migration and Consumer Cutover

### 6.1. Prevent Two Consumers from Creating Duplicate Side Effects

If a legacy consumer and a new function both read the same queue/topic, each message could be processed twice. This is safe only if consumers share idempotency and semantics permit it. Typically you need one of:

- Separate consumer groups/queue ownership with subscription switching;
- Pause the legacy consumer before starting the new consumer;
- Route by partition/key or tenant cohort;
- Mirror events to a shadow environment without executing side effects;
- Deduplicate via a shared event ID/business operation ID.

### 6.2. Queue Cutover

Before cutover:

- Identify in-flight messages and visibility/lease timeouts;
- Stop producers or route new messages to the target;
- Wait for legacy consumers to finish or persist checkpoint state;
- Check queue depth/oldest message age;
- Start the new consumer with concurrency caps;
- Monitor duplicates, DLQs, and business completion.

If backlog remains in the old queue, deciding whether to finish draining on legacy, drain to a new queue, or switch the queue outright depends on ordering and schemas. Never copy messages ad hoc while legacy consumers are still actively reading.

### 6.3. Stream Cutover

For Kafka/Kinesis or similar streams, specify:

- Partition/shard assignments;
- Committed offsets/checkpoints;
- Consumer group identities;
- Retention windows;
- Ordering scope;
- Replay behavior;
- Schema compatibility.

The new consumer can start from an old offset, latest offset, or timestamp. Picking the wrong start point causes dropped or reprocessed records. Persist checkpoints and event IDs; idempotency guards against duplicates, not picking the wrong offset.

### 6.4. Scheduled Job Migration

An old cron job and a new scheduler could fire within the same minute. Enforce one scheduler owner at a time, fenced locks/leases, or job idempotency keys per logical schedule window. Verify timezones, daylight saving behavior, missed invocations, and catch-up policies.

### 6.5. Event Schemas and Delayed Delivery

Events emitted before cutover may arrive after cutover. New consumers must parse old schemas throughout the retention/replay window or use a translator. Never delete old schemas immediately after deploying new producers.

## 7. Shadow Traffic and Pre-Cutover Validation

### 7.1. Shadow Mode

Shadow traffic sends copies of requests/events to the new system to compare outcomes without allowing production side effects. For example, the new function runs validation and computes a response; results are logged/compared without charging payments or sending emails.

Shadow testing reveals behavioral diffs, latency profiles, and compatibility bugs. Protect shadow data and prevent shadow load from exceeding target capacity.

### 7.2. Comparing Results

Compare meaningful attributes:

- Status/decision codes;
- Normalized response fields;
- Business invariants;
- Generated event types/payloads;
- Calculated totals/rounding;
- Validation errors;
- Latency and dependency usage.

Strip timestamps, random IDs, or non-deterministic fields before comparing. Do not compare only byte-for-byte if field ordering or metadata differs while semantics match.

### 7.3. Prevent Shadow Traffic from Causing Side Effects

Provision dedicated shadow identities/resources and deny write/send/charge permissions where possible. Where read-only cannot be guaranteed, use mocks/sandboxes for side-effecting dependencies. Attach `shadow=true` to telemetry, but never rely solely on a spoofable caller header to protect production data.

### 7.4. Exit Criteria for Shadow

- Zero unexplained critical correctness diffs;
- Compatible schemas and auth contexts;
- p95/p99 latency and concurrency within budget;
- Zero unintended write/email/payment side effects;
- Headroom in dependency quotas and costs;
- Every error class has an owner and remediation plan.

## 8. Traffic Cutover Strategies

### 8.1. Big-Bang Cutover

Shift 100% of traffic during a maintenance window. Typical sequence: freeze changes, drain in-flight work, run final data sync, switch routing, run smoke tests, and monitor.

The advantage is clean post-switch ownership boundaries. The drawback is a wide blast radius requiring fast rollback. Use only when workloads, downtime budgets, and recovery plans allow.

### 8.2. Blue-Green

Prepare both blue (legacy) and green (serverless) stacks. The router switches traffic to green; blue remains warm through the rollback window.

Blue-green simplifies traffic switching yet does not automatically solve database compatibility. If green writes a schema blue cannot read, routing rollback can corrupt or break reads. Pair with expand-migrate-contract and explicit write ownership.

### 8.3. Percentage Canary

Shift traffic incrementally: 1%, 5%, 10%, 25%, 50%, then 100% is one example. Actual steps depend on volume and risk. Hold each stage long enough to collect representative samples across business cycles.

Canaries can be sliced by:

- Weighted routing at gateways/load balancers;
- Function alias/version routing;
- Tenant cohorts;
- Account/customer segments;
- API routes or operation types;
- Event partitions/groups.

Never randomize cohorts per retry if a single business transaction could span both systems. Use sticky routing by transaction/tenant and log route decisions.

### 8.4. Strangler Routing

A gateway/router directs migrated capabilities to new functions while sending the rest to legacy. Gradually, legacy retains only unmigrated capabilities.

The router must enforce auth, timeouts, headers, correlation IDs, rate limits, and error mapping consistently. Avoid creating accidental call loops like legacy → gateway → function → legacy.

### 8.5. DNS Cutover

DNS is cached by clients, resolvers, and proxies. Lowering TTL ahead of migration shortens propagation, yet does not guarantee all clients switch immediately. For HTTP APIs, gateway/edge routing is usually easier to control than DNS alone.

If using DNS:

- Verify actual TTLs and client caching behavior;
- Keep the old endpoint live throughout the rollback window;
- Do not revoke old certificates/network routes prematurely;
- Monitor residual traffic still hitting the old endpoint;
- Prepare for client pinning or long-lived caches.

### 8.6. Feature Flags and Kill Switches

Feature flags enable toggling capabilities or tenants via configuration. They require:

- Owners and approvals;
- Change audit logs;
- Safe default/fallback behaviors;
- Known cache/propagation behavior;
- Tested kill switches;
- Expiry dates to remove flags post-migration.

Flags must not live forever. Stale flags obscure routing logic and increase split-traffic risk.

## 9. Detailed Cutover Procedure

### 9.1. Before Cutover Day

**T-14 to T-7 days** (illustrative; adjust per project):

- Complete dependency inventory and ownership;
- Run load, soak, and chaos/failure tests within safe boundaries;
- Complete snapshot/CDC and schema compatibility checks;
- Rehearse rollback in an equivalent environment;
- Verify production IAM, networking, secrets, and quotas;
- Verify dashboards, alerts, and runbooks;
- Lock SLOs, business validations, and rollback thresholds;
- Notify stakeholders/support and external providers if needed.

**T-1 day:**

- Freeze unrelated changes;
- Verify artifact digests/config revisions;
- Verify backups/snapshots and restore points;
- Check replication lag, queue backlogs, and scheduler ownership;
- Confirm on-call staff, decision makers, and escalation channels;
- Check clock synchronization and timestamps across systems.

### 9.2. During the Cutover Window

1. Open the incident/change bridge and confirm the decision maker.
2. Check health of both legacy and target before making changes.
3. Pause or throttle writes/producers per plan.
4. Drain in-flight requests/messages and record checkpoints.
5. Wait for CDC/replication to reach the designated watermark.
6. Run final reconciliation/consistency checks.
7. Switch routing or consumer ownership.
8. Open traffic for the approved cohort/percentage.
9. Run technical smoke tests and business transaction tests.
10. Observe errors, latency, queue age, data correctness, and cost.
11. Ramp traffic across gates; halt immediately if any rollback trigger trips.
12. Log timestamps and decisions for every step in the change record.

### 9.3. Post-Cutover

- Keep legacy read-only or on standby per rollback design;
- Monitor residual traffic still reaching legacy;
- Reconcile data and events by cohort;
- Check retries/DLQs and duplicate side effects;
- Monitor SLOs and cost per successful transaction;
- Update service catalogs and on-call ownership;
- Maintain hypercare for the agreed period.

## 10. Readiness Gates and Success Criteria

### 10.1. Technical Readiness

- Artifacts signed/scanned with recorded digests;
- Java runtime/dependencies verified compatible;
- Least-privilege IAM and network paths tested;
- Timeouts, memory, concurrency, retries, and DLQs properly configured;
- API/event contracts compatible;
- Dashboards, logs, traces, and alerts active;
- Quotas/capacity sufficient for peaks and retries;
- Backup/restore and rollback rehearsed.

### 10.2. Data Readiness

- Snapshot/CDC checkpoints clear;
- Replication lag within thresholds;
- Bidirectional schema compatibility maintained for the rollback window;
- Row counts/checksums/invariants verified;
- Writer ownership unambiguous;
- Event IDs, versions, and idempotency preserved;
- Sensitive data protected per policy.

### 10.3. Operational Readiness

- Service owners, on-call, and escalation paths confirmed;
- Runbooks dry-run by operators;
- Decision makers and rollback authority ready;
- Change records/approvals complete;
- Cloud/vendor support paths known;
- Hypercare schedule staffed.

### 10.4. Business Readiness

- Business owners sign off on acceptance criteria;
- Business counts/financial totals reconciled;
- Customer communications/support scripts ready;
- Downtime/degraded-mode expectations approved;
- Compliance/data-residency sign-offs complete if required.

### 10.5. Success Criteria Must Be Quantitative

Example for an order API:

| Metric | Illustrative Gate |
| --- | --- |
| HTTP success rate | Not more than 0.2 percentage points below baseline over 30 minutes |
| p95 latency | Within published SLO |
| Duplicate orders | 0 duplicate business orders within reconciliation window |
| Payment/inventory invariants | Zero unexplained discrepancies |
| Queue age | Within freshness SLO |
| DLQ rate | Does not exceed approved threshold |
| Cost per completed order | Within agreed guardrail after normalizing traffic |

These thresholds are examples. Base thresholds on service baselines, SLOs, and risk appetite. Choose observation windows long enough to avoid reacting to brief spikes.

## 11. Rollback: Decisions, Conditions, and Sequence

### 11.1. Rollback Triggers

Triggers should combine technical and business signals:

- Sustained error/timeout rates above thresholds;
- p95/p99 latency breaching SLOs;
- Uncontrolled growth in consumer lag/oldest message age;
- Database throttling/connection saturation;
- Failures in data checksums, balances, inventory, or order reconciliation;
- Duplicate/missing events exceeding thresholds;
- Security/IAM/data exposure incidents;
- Cost spikes from retry/event loops;
- Target unable to stay within capacity/quotas.

Critical triggers such as corrupted data or data exposure require an immediate stop without waiting out an observation window.

### 11.2. Rollback Decision Record

Document:

- Trigger and supporting metrics/evidence;
- Impact start time;
- Scope/cohort/region;
- Decision maker;
- Choice of rollback vs. forward-fix;
- Data writes/events already committed;
- Action sequence and owners;
- Recovery verification criteria.

### 11.3. Rolling Back Routing Does Not Roll Back Data

Routing traffic back to legacy only changes future request paths. If the target wrote new data, legacy might not see or understand it. Before rolling back, determine:

- Whether the target accepted any writes;
- Whether CDC/reverse replication copied writes back to legacy;
- Whether source can safely reclaim write authority or target must remain source of truth;
- Whether schemas remain compatible;
- Whether emitted events can be processed by legacy consumers;
- Whether external side effects have already occurred.

Without safe reverse sync, you may need to keep target as the writer and forward-fix, or pause writes and reconcile before switching. Never flip-flop writers arbitrarily.

### 11.4. Controlled Rollback Procedure

1. Activate incident/change procedures and confirm the decision maker.
2. Halt canary/traffic ramping; block new writes if needed.
3. Capture target/source checkpoints, CDC positions, queue offsets, and transaction IDs.
4. Determine which system holds authoritative data.
5. Select reverse sync, restore, compensation, or forward-fix.
6. Switch routing/consumers back safely per the data-compatible plan.
7. Verify legacy can read current state and events/schemas.
8. Run reconciliation and duplicate/missing event checks.
9. Reopen traffic within limits and monitor SLOs.
10. Keep target/legacy intact for investigation until formal sign-off.

### 11.5. Rollback, Roll-Forward, and Compensation

| Approach | Description | When Appropriate |
| --- | --- | --- |
| Code/routing rollback | Revert to prior artifact/route | Data and contracts remain compatible |
| Roll-forward fix | Patch the issue on target and proceed | Data has mutated, rollback is unsafe, or patching is faster |
| Compensation | Issue compensating business actions | Side effects committed and reversible via business rules |
| Restore/replay | Restore snapshot or replay events | Data lost/corrupted with a clean recovery point and replay plan |
| Stop-the-write | Pause writes to protect consistency | Risk of split-brain or data corruption |

Rollback is not always the best option. The decision depends on data state, compatibility, business impact, and recovery time.

### 11.6. Platform-Specific Rollback Actions

| Platform | How to Restore Stable Workload | What to Verify |
|---|---|---|
| AWS Lambda | Point alias back to prior version or let CodeDeploy roll back deployment | Alias target, event source mappings, resource permissions, and Provisioned Concurrency |
| API Gateway | Restore prior integration/route or stage deployment | Active stage, authorizers, caching, and integration timeouts |
| Azure Functions | Swap slots back or deploy stable artifact | Slot-specific settings, hostnames, trigger listeners, and app settings |
| Azure API Management | Restore stable backend/policy/revision | Backend target, policies, subscriptions, and health |
| Queue consumer | Stop new consumer, start legacy consumer per runbook | In-flight messages, checkpoints, duplicates, and DLQ |
| DNS | Restore prior records if using DNS cutover | Resolver/client caches, TTLs, and connection reuse |

Exact steps depend on deployment tooling and environment configuration. Rehearse in staging to verify operators have permissions and know exact aliases, slots, routes, or consumers to adjust.

#### AWS Lambda: Aliases and CodeDeploy

A Lambda version is an immutable snapshot of code and select configuration. An alias like `live` provides a stable ARN for callers while the underlying version shifts. CodeDeploy supports canary/linear traffic shifting and can halt or roll back when alarms or hooks fail.

Abbreviated AWS SAM example:

```yaml
Resources:
  CatalogFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: com.example.catalog.CatalogHandler::handleRequest
      CodeUri: target/catalog-function.zip
      AutoPublishAlias: live
      DeploymentPreference:
        Type: Canary10Percent5Minutes
        Alarms:
          - !Ref CatalogFunctionErrorsAlarm
```

This is an illustrative snippet; the stack must still define alarms, IAM, API integrations, and remaining properties. Callers should invoke the alias rather than pinning a version directly when fast switching is required. Verify which function/alias event source mappings target and ensure resource-based policies still allow triggers to invoke the destination. Rolling back an alias never reverses database writes, messages, or side effects that already occurred.

#### Azure Functions: Deployment Slots and Swap

On hosting plans supporting deployment slots, deploy the candidate to a staging slot, warm it up, and run smoke tests before swapping with production. If issues appear after swapping, swap back or deploy a stable artifact per runbook.

1. Deploy artifact to the staging slot.
2. Apply staging configuration and mark slot-specific (sticky) settings properly.
3. Warm up the runtime and verify the staging hostname.
4. Confirm trigger listeners do not accidentally consume from the production queue.
5. Run smoke tests and inspect Application Insights.
6. Swap staging with production, then verify hostnames, auth, and function execution.
7. If checks fail, swap back or redeploy the stable artifact.

With Queue, Service Bus, or Timer triggers, the staging slot can start active listeners. If both staging and production connect to the same live queue, two listeners can compete for messages or process concurrently. Use test queues, appropriate listener settings, or explicit consumer switching procedures. Verify hosting plan/OS slot support before relying on swaps as a rollback mechanism.

## 12. Data Reconciliation After Cutover or Rollback

### 12.1. Reconciling Business Invariants

Do not compare row counts alone. For orders/payments/inventory, reconcile:

- Order counts by status/tenant/time window;
- Amount/currency totals against ledgers;
- Reserved/available inventory;
- Captured/refunded/unknown payments;
- Events produced/consumed/failed;
- Pending and duplicate outbox/inbox entries;
- Aggregate versions and sequence gaps.

### 12.2. Handling Unknown Outcomes

If a request times out while the payment provider might have captured funds, do not immediately submit another charge. Query the provider using the idempotency key/operation ID, reconcile the ledger, and act only after the status is clear.

### 12.3. Reconciliation Report

A report should include:

| Field | Meaning |
| --- | --- |
| Scope | Cohort, tenant, partition, and time range |
| Source/target watermark | Synchronized data boundary |
| Count delta | Difference in record counts |
| Amount/aggregate delta | Difference in business totals |
| Missing/duplicate IDs | Missing or duplicated events/transactions |
| Version/sequence gaps | Ordering gaps |
| Exceptions | Discrepancies requiring investigation |
| Decision | Accept, repair, replay, or stop |
| Owner/evidence | Sign-off owner and supporting artifacts |

### 12.4. Repairs Must Be Idempotent and Audited

Repair scripts/jobs should support dry-run, bounded scope, operation IDs, audit logs, and resumability. Never run bulk updates without checkpoints. For financial or sensitive data, obtain policy-required approvals and perform independent post-repair reconciliation.

## 13. Hypercare and Post-Cutover Monitoring

### 13.1. Hypercare

Hypercare is the period of heightened support immediately following cutover. Define:

- Start and end times;
- Primary/secondary on-call staff;
- Business owners and platform contacts;
- Dashboards/war-room channels;
- Stakeholder update cadence;
- Exit criteria for hypercare;
- Owners for remaining issues.

### 13.2. Cutover Dashboard

Monitor legacy and target side by side:

- Traffic split by route/cohort;
- Success/error/timeout rates;
- p50/p95/p99 latency;
- Invocations/concurrency/throttles/cold starts;
- Queue lag, oldest message age, and DLQs;
- Database CPU/IO/connections/locks/replication lag;
- Data discrepancies and business completion;
- Retry amplification and duplicate rates;
- Cost per successful transaction.

Separate shadow traffic from production traffic so you do not misread success rates or cost.

### 13.3. Hypercare Exit Criteria

- Stable SLOs across a representative business cycle;
- Zero unresolved critical discrepancies;
- Backlogs/DLQs at normal levels;
- Alert noise and runbooks tuned;
- Support/on-call teams formally owning operations;
- Rollback window closed or extended with an owner;
- Decommission gates reviewed.

## 14. Legacy Infrastructure Decommissioning

### 14.1. Do Not Delete Legacy Immediately Upon Reaching 100% New Traffic

Legacy may still be used by:

- Old clients or DNS caches;
- Unmigrated scheduled jobs/crons;
- Webhook subscriptions;
- Queue consumers or DLQ replays;
- Reporting/export jobs;
- Admin scripts and support tools;
- Backup/restore or audit processes;
- Downstream systems calling legacy private endpoints.

Verify zero real traffic and dependencies rather than trusting architecture diagrams alone.

#### Quarantine Before Deletion

Before deleting resources, pause or isolate legacy for an observation period:

1. Disable old listeners, schedulers, or jobs per plan.
2. Block new ingress to legacy endpoints while keeping access logs/metrics to catch straggling callers.
3. Observe across at least one full cycle of critical batch/scheduled clients.
4. If legitimate callers appear, restore access or migrate those callers before continuing.

Match the quarantine period to traffic patterns. Confirming a monthly job is unused takes more than a few days of zero requests.

### 14.2. Decommission Gates

Begin decommissioning only when:

- Legacy traffic is zero or every remaining hit is accounted for;
- All writers/consumers/schedulers have migrated;
- Target meets SLOs and business acceptance during hypercare;
- Data reconciliation is complete;
- Rollback window has closed with sign-off;
- Backups/exports/retention/legal holds are addressed;
- Owners approve deleting resources and data;
- A complete inventory of related resources, dependencies, and credentials exists.

### 14.3. Decommissioning Sequence

1. Mark legacy read-only or disable entry points per plan.
2. Monitor access logs/metrics for remaining callers.
3. Disable legacy schedulers, event subscriptions, webhooks, and consumers.
4. Drain queues or archive per retention policy.
5. Export/back up data to retain and verify readability.
6. Revoke unused IAM roles, access keys, secrets, certificates, and cross-account trusts.
7. Remove legacy DNS records, routes, load balancers, NAT rules, firewalls, and network paths after verification.
8. Delete compute/database/storage resources per approvals and deletion protection policies.
9. Confirm logs/audits/billing evidence are retained per policy.
10. Update service catalogs, CMDBs, diagrams, cost allocations, and runbooks.
11. Monitor bills and alerts to catch orphaned resources.

Never delete backups or data solely because compute stopped. Retention, legal holds, data residency, and audit policies may mandate keeping data longer.

### 14.4. Decommissioning by Layer

| Layer | Action | Checks Before Removal |
| --- | --- | --- |
| Compute | Stop/scale to zero/delete VMs/containers/services | Zero traffic, processes, or scheduled tasks |
| Network | Remove routes, security groups, NAT, endpoints, load balancers | Zero dependent consumers/clients |
| Identity | Revoke roles/keys/trusts/policies | Zero workloads using the principal |
| Data | Archive/delete databases, files, caches | Retention, legal holds, backups, and reconciliation |
| Messaging | Disable subscriptions/consumers, archive queues/topics | Offsets, backlog, DLQ, and replays handled |
| DNS/certificates | Remove records/certs/bindings | TTL/client caches and old endpoints no longer needed |
| Observability | Retire old agents/metric/log pipelines | Audit/retention evidence saved |
| Billing | Remove unused capacity/licenses/commitments | Does not impact other shared workloads |

### 14.5. Decommissioning Evidence

Archive evidence:

- Approvals and change records;
- List of deleted vs. retained resources;
- Traffic/access verification;
- Backup/retention references;
- IAM revocation confirmation;
- Data deletion confirmation if applicable;
- Before/after cost comparison;
- Owner sign-off and completion date.

### 14.6. IaC and Protection Against Accidental Deletion

When resources are managed via IaC, removing resource blocks from code can destroy them on the next `apply`. Before editing:

- Confirm workspace/state matches the right environment and account/subscription;
- Check dependencies and shared resources;
- Inspect the plan to see every resource marked destroy/replace;
- Keep deletion protection or `prevent_destroy` on critical data resources during migration;
- Use retain policies or take snapshots before deletion if data must be kept;
- Never run `terraform destroy` on an entire workspace just to retire one endpoint.

Example Terraform lifecycle guard for a database:

```hcl
resource "aws_db_instance" "legacy" {
  identifier        = "legacy-orders"
  allocated_storage = 100
  engine            = "postgres"
  instance_class    = "db.t4g.medium"

  deletion_protection = true

  lifecycle {
    prevent_destroy = true
  }
}
```

This is an illustrative snippet, not a complete production database configuration. `prevent_destroy` causes Terraform to reject plans that would destroy the resource while the block and lifecycle guard remain in configuration; deletion protection adds a cloud-service-level safeguard. When ready to retire, peer-review removal of the guard, take required snapshots/retention backups, and inspect the plan before applying. Never remove guards merely to make a pipeline green.

## 15. Java Migration Example: Idempotency and Route Stability

### 15.1. Preserving Operation IDs Across Both Systems

When a caller submits an order, generate/accept a stable business operation ID. Both legacy and serverless adapters must interpret the same key with the same semantics. Never generate a new key whenever the router switches targets.

```java
public record OrderCommand(
        String operationId,
        String orderId,
        String tenantId,
        long amountMinor) {
}

public interface OrderProcessor {
    OrderResult submit(String tenantId, OrderCommand command);
}

public interface IdempotencyStore {
    // Atomically claims an operation key or returns its prior result.
    IdempotencyDecision begin(String scope, String operationId);
}
```

`IdempotencyStore` must be shared across both processing paths or backed by unified deduplication. If legacy and serverless maintain separate idempotency stores, the same operation can execute once in each system.

### 15.2. Route Decisions Must Be Sticky

If tenant A moves to serverless, retries of transaction A must keep hitting the matching target, or the target must recognize an operation already started on legacy. Never pick targets randomly per request. Store cohort assignments and transaction owners in durable configuration/state.

### 15.3. Do Not Dual-Write Business Side Effects in Shadow Mode

Shadow invocations only compute/compare outputs. They must never charge payments, reserve stock, send emails, or emit production events. Separate permissions and use sandbox endpoints to bound side effects.

## 16. Sample Cutover Runbook

### Pre-Cutover

- [ ] Change record and stakeholder communications approved.
- [ ] Primary/secondary on-call and decision makers confirmed.
- [ ] Target health, quotas, IAM, networking, and secrets verified.
- [ ] Snapshot/CDC checkpoints and replication lag within thresholds.
- [ ] Queue/stream/scheduler ownership clear.
- [ ] Legacy/target schema compatibility verified.
- [ ] Dashboards/alerts and business reconciliation ready.
- [ ] Rollback/forward recovery rehearsed.
- [ ] Backup/restore points and data retention verified.

### Execution

- [ ] Freeze unrelated changes.
- [ ] Pause or reroute producers per plan.
- [ ] Drain in-flight work and save checkpoints.
- [ ] Wait for final data sync/watermark.
- [ ] Run count/checksum/business invariant checks.
- [ ] Switch traffic for the approved cohort/percentage.
- [ ] Run smoke tests and business verification tests.
- [ ] Monitor SLOs, duplicates, DLQs, lag, and cost.
- [ ] Ramp traffic only after prior gates pass.
- [ ] Record decisions/timestamps/evidence.

### Rollback If Triggers Fire

- [ ] Stop traffic ramping and assess blast radius.
- [ ] Capture target/source watermarks, event offsets, and write history.
- [ ] Identify the authoritative data store.
- [ ] Choose reverse sync, compensation, forward-fix, or stop-the-write.
- [ ] Switch routes/consumers per data-compatible plan.
- [ ] Run reconciliation and verify business correctness.
- [ ] Notify stakeholders and update the incident record.

### Post-Cutover

- [ ] Hypercare complete and operational owners transitioned.
- [ ] Residual legacy traffic/dependencies verified zero.
- [ ] Rollback window closed with sign-off.
- [ ] Retention/backups/legal holds handled.
- [ ] Decommission approvals and resource inventory complete.
- [ ] Legacy IAM/network/DNS/compute/data cleanup complete.
- [ ] Billing and service catalogs updated.

## 17. Migration Anti-Patterns

### 17.1. Shifting Traffic Before Understanding Data Ownership

Traffic switches fast, yet if two systems both write to the same aggregate, rollback becomes painful. Lock down writer ownership and reconciliation first.

### 17.2. Dual-Write Without Outbox/CDC

Two independent writes do not form a distributed transaction. One side can succeed while the other fails. Use replication/outbox or a repair process keyed by versions and operation IDs.

### 17.3. Shadow Traffic with Production Write Permissions

Shadow requests could send real emails, charge payments, or emit real events. Use separate identities/resources, deny writes, or sandbox side effects.

### 17.4. Per-Request Randomized Canaries

A transaction could start on legacy and retry onto serverless. Use sticky cohort/operation routing and preserve transaction ownership.

### 17.5. Rolling Back Only via DNS/Alias

Data and events may already have changed. Check reverse sync, schema compatibility, and side effects before routing back to legacy.

### 17.6. Shutting Down Legacy Immediately After Cutover

Old clients, schedulers, delayed events, and backups may still depend on it. Keep a rollback window, read-only period, and verify actual access logs.

### 17.7. Deleting Backups Alongside Compute

Backups, retention, and audits have independent lifecycles. Check retention rules and legal holds before deleting data.

### 17.8. No Owner for Rollback Decisions

If anyone can propose rollback yet nobody holds authority to decide, incident bridges stall. Appoint decision makers, thresholds, and authority before cutover.

## 18. Production Migration Checklist

- [ ] Complete workload inventory, dependency graph, and owners.
- [ ] Baseline traffic, latency, errors, data, and cost recorded.
- [ ] Wave scope and migration strategy have business owners.
- [ ] Java business logic decoupled from cloud-specific adapters at appropriate boundaries.
- [ ] API/event contracts and schema versions compatible.
- [ ] Target configurations/secrets/IAM/networking verified.
- [ ] Data snapshot/CDC/checkpoints and final sync rehearsed.
- [ ] One authoritative writer per aggregate/tenant at each stage.
- [ ] Dual-writes use outbox/CDC/reconciliation rather than two uncoordinated calls.
- [ ] Idempotency keys and event IDs preserved across legacy/target/retries.
- [ ] Queue/stream offsets, scheduler ownership, and delayed events handled.
- [ ] Shadow mode causes zero production side effects.
- [ ] Canary/cohort routing stays sticky across retries.
- [ ] Cutover gates measure both technical SLOs and business correctness.
- [ ] Rollback triggers, decision makers, and timeboxes approved.
- [ ] Rollback plan covers data, events, schemas, and side effects.
- [ ] Forward-fix/compensation/replay paths defined.
- [ ] Hypercare owners and dashboards ready.
- [ ] Decommission gates verify zero traffic/dependencies with evidence.
- [ ] Backups, retention, legal holds, and audits preserved per policy.
- [ ] Old IAM, secrets, DNS, certificates, networking, and resources decommissioned cleanly.
- [ ] IaC plans affect only approved legacy resources; deletion protection/retain policies reviewed.
- [ ] Before/after cost and cost per successful transaction reconciled.
- [ ] Service catalog, runbooks, RACI, and support boundaries updated.

## Conclusion

Cutover changes workload routing and ownership; rollback restores a safe operational and data state; decommissioning tears down resources after confirming zero remaining dependencies. All three must be designed together from the beginning of a migration.

For Java serverless, migrate in waves, decouple business logic from adapters, maintain API/event compatibility, enforce one authoritative writer, and use snapshots/CDC/outboxes to govern data. Shadow and canary runs shrink blast radius, provided side effects are guarded and routing stays sticky across retries. Success gates must measure SLOs, business invariants, queue freshness, and cost per successful transaction.

Rollback is never just pointing traffic back to an old endpoint. You must know what data was written, which events fired, what schemas changed, and which side effects are irreversible. When rollback is unsafe, forward-fix, compensation, or stop-the-write may be better choices. Retire legacy only after hypercare, reconciliation, rollback window expiry, retention review, and decommission sign-off. Every step requires an owner, checkpoint, evidence, and runbook so migrations stay controllable in production.
