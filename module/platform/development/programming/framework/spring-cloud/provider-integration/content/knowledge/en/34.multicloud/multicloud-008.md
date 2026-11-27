# Assessing Migration Costs, Consistency, and Transition Planning

Moving a Spring Boot workload to another cloud provider is an architectural and operational decision, as well as a financial one. A service with a lower storage unit price can still increase total cost if it introduces egress, request fees, replication, private connectivity, operating two platforms, or migration effort. Likewise, a target offering high throughput with a different consistency model than the source can alter business behavior.

Therefore, before choosing AWS, Azure, or Google Cloud as a target, three questions must be answered: what is the total cost of ownership over the forecast horizon; what consistency level must the system guarantee for each data type; and which transition strategy meets downtime, RPO, RTO, and business risk limits. Spring Cloud libraries help applications integrate with each provider's managed services, but they do not solve the economics or make service semantics equivalent on their own.

## Objectives

After this lesson, you will be able to:

- Build a total cost of ownership (TCO) model covering the current workload, target workload, and transition period.
- Estimate costs for data transfer, parallel runs, change synchronization, testing, and rollback.
- Distinguish consistency levels and specify the level required by business logic.
- Evaluate the impact of replication lag, retries, message ordering, and dual-writes.
- Select a transition strategy based on volume, downtime, risk, and rollback capability.
- Establish measurable go/no-go criteria before cutover.

## 1. Scoping the economic analysis properly

Do not compare the isolated price of a VM, one GB of storage, or one million requests. Compare the cost of delivering the same business capability at the same service level. If the target workload needs extra replicas, caches, gateways, private endpoints, or observability tooling to meet an equivalent SLO, those items must appear in the model.

Pick an evaluation horizon, typically 12, 24, or 36 months depending on budget and contract cycles. Use identical assumptions for load, growth, availability, retention, backups, deployment regions, and staffing across source and target. Separate three cost categories:

| Category | Typical components | When incurred |
|---|---|---|
| One-time costs | Compatibility analysis, design, adapter development, migration tooling, initial data transfer, testing, training | Before and during migration |
| Transition costs | Running two environments in parallel, replication, egress, reconciliation, test environments, after-hours support | During the transition and rollback windows |
| Steady-state recurring costs | Compute, storage, databases, requests, networking, backups, observability, support, operational staffing | After cutover |

TCO over the evaluation horizon can be expressed as:

\[
TCO = C_{one\text{-}time} + C_{transition} + \sum_{m=1}^{N} C_{steady,m}
\]

Where (N) is the number of forecast months. When comparing against staying on the source, include source costs over the same period plus any savings or avoided expenses. Do not double-count source costs: the portion of the source still running during transition belongs in `C_transition`, while post-decommission source costs do not belong in target steady state.

Alongside monetary figures, record decision-support metrics such as payback period, cost per transaction, cost per GB of active data, monthly operational effort, and the value of reducing vendor dependence. Factors hard to quantify in currency should be captured separately as benefits or risks rather than forced into an arbitrary number.

## 2. Estimating cost components

### 2.1. Compute and application runtime

For Spring Boot, account for instance or pod counts, machine types, CPU/memory requests and limits, autoscaling, uptime, standby capacity, and control plane charges if applicable. A 24/7 workload has a different cost profile than a batch job running a few hours daily. Compare at identical load and identical SLOs; if the target provider has different per-core performance, benchmark to adjust instance counts instead of blindly copying source sizing.

Include Kubernetes or container platform charges, load balancers, NAT gateways, IP addresses, service meshes, and required supporting services. Never assume cheaper raw compute means a cheaper overall platform.

### 2.2. Storage and databases

For object storage, total cost can include average capacity by storage tier, PUT/GET/LIST request counts, archive-tier retrieval fees, versioning, lifecycle transitions, replication, inventory reports, encryption, and egress. Infrequently accessed data can be cheap to store yet expensive to restore or transfer out. Forecast by access-frequency distribution rather than applying a single storage class to all objects.

For managed databases, include compute, storage, provisioned IOPS or throughput, backups, read replicas, high availability, licenses, proxies, connections, and data transfer. If switching between engines, add schema conversion, query rewrites, compatibility testing, and index re-tuning costs. A target database with a lower unit price that requires more read replicas or larger compute to meet latency targets may cost more to operate.

### 2.3. Messaging and integration

For queues, topics, and event buses, count operations, message sizes, subscription counts, retention, retries, dead-lettering, provisioned throughput, connections, and cross-region delivery. During parallel runs, a single event may be published to both source and target or forwarded via a bridge; this increases operation counts and can incur extra egress.

Estimate using both normal traffic and failure traffic. If target consumers slow down, retries and backlogs can sharply multiply message deliveries. Include retry rates, retention durations, and DLQ rates in load scenarios instead of modeling only normal-day happy-path messages.

### 2.4. Networking and data transfer

Networking is often the most overlooked item in cloud comparisons. Classify data flows by direction and destination: internet egress, cross-region transfer, cross-zone transfer, hybrid links, NAT traffic, private endpoints, and inter-service traffic. Pricing and billing rules depend on provider, region, link type, and contract; always pull figures from current pricing sheets or calculators at budgeting time.

For an initial bulk transfer, a baseline estimation formula is:

\[
C_{transfer} = V_{GB} \times P_{GB} + C_{request} + C_{temporary}
\]

Where (V_{GB}) is the volume of data actually traversing the link, (P_{GB}) is the unit rate for that transfer path, `C_request` is operation fees if applicable, and `C_temporary` is staging or temporary copy storage. If multiple passes are required, sum each pass and account for ongoing deltas. When compressing or filtering data, use post-transform volume; never assume all data is compressible.

Theoretical transfer time can be estimated as:

\[
T_{transfer} \approx \frac{V_{bytes}}{B_{effective}}
\]

`B_effective` is effective throughput after accounting for network limits, concurrency, encryption, service throttling, and retry overhead. Theoretical numbers are only for initial planning; benchmark with a representative data sample before committing to a downtime window.

For example, transferring 12 TB at an average useful throughput of 200 MB/s takes roughly 16.7 hours by decimal division, before adding verification, retries, metadata, API rate limits, and changes generated during transfer. If the allowed downtime window is only two hours, you cannot wait until stopping the system to begin copying. You must pre-seed data, sync deltas, and freeze writes only in the final phase.

### 2.5. Security, observability, and support

Include costs for secret managers, KMS/Key Vault/Cloud KMS, audit logs, security posture tools, vulnerability scanning, log ingestion, metrics, traces, alerts, and observability retention. Enabling verbose auditing or longer log retention raises bills, yet shortens investigation time and supports compliance audits.

Include provider support plans, specialist migration services, and time from platform, security, data, development, and operations teams. Internal engineering time is not free merely because it does not appear on a cloud invoice. Estimate person-days by role, opportunity cost, and cutover support coverage.

## 3. Building a TCO spreadsheet and sensitivity analysis

A spreadsheet can be organized by service and environment. Each line item should capture unit of measure, usage quantity, unit price, pricing source, assumptions, and confirming owner. Never enter a single lump-sum figure without preserving components so the model adjusts when load changes.

| Component | Current source | Post-migration target | Parallel run phase | Estimation basis |
|---|---|---|---|---|
| Spring Boot compute | Instance/pod hours | Instance/pod hours | Both environments | Load and SLO |
| Object storage | GB-month and requests | GB-month and requests | Copies in both | Volume, tier, access pattern |
| Databases | Compute, GB, IOPS, backups | Compute, GB, IOPS, backups | Source + target + CDC | Query profile, HA, retention |
| Messaging | Operations, throughput, retention | Operations, throughput, retention | Bridge/dual publish | Message rate, size, retries |
| Networking | Egress, NAT, private links | Egress, NAT, private links | Replication and sync | Bytes per path |
| Security/observability | KMS, secrets, logs, traces | KMS, secrets, logs, traces | Dual-side auditing | Retention and monitoring level |
| Staffing and support | Current ops | Target ops | Migration/cutover | Person-days and support tier |

Build at least three scenarios:

- **Baseline:** expected load and growth, planned transition duration, typical retry rates.
- **Downside:** faster data growth, slower transfer, high CDC lag, extended dual-run, elevated retries, or a rollback.
- **Upside:** effective compression/filtering, shorter transition window, more efficient target resource utilization, and early source decommission.

Run sensitivity analysis on high-impact variables: data volume, egress, parallel-run duration, replica count, growth rate, cache hit ratio, operation counts, and retention. For example, if each week of delayed source shutdown adds another week of compute, database, backup, and support charges, that cost must show up in the model. Identify which variables move TCO the most so you can benchmark those first.

If applying discounted cash flows, discount cash outlays using timing and discount rates provided by finance. For typical engineering decisions, a monthly cost breakdown across scenarios is often sufficient; avoid false precision when unit rates, usage, or migration timelines remain unverified.

## 4. Choosing the consistency level suited to the business

Consistency describes how clients observe data after an update. No single consistency level is optimal for all data. Account balances, order states, and authorization policies typically require stronger guarantees than caches, analytics metrics, or feeds that tolerate delayed updates.

Common consistency models:

| Model | Core behavior | Suitable use case examples |
|---|---|---|
| Strong/linearizable consistency | After a write succeeds, subsequent reads observe the new value under a valid global order | State requiring immediate decisions, such as quotas or unique allocation |
| Read-your-writes | A client reads changes that the same client just wrote | Profile page immediately after a user updates details |
| Monotonic reads | A client never sees an older version of data after seeing a newer one | Session state or multi-step workflows |
| Causal consistency | Causally related operations are observed in order | Creating a record then emitting a related event |
| Eventual consistency | If updates stop and the system stays healthy, replicas eventually converge | Caches, search indexes, analytics, or secondary read views |

These terms describe system properties at different scopes; exact names and guarantees of managed services vary. Always read target database, storage, or broker documentation and test under failure, failover, and multi-region conditions. Never assume two services share identical consistency simply because both offer `GET` and `PUT` APIs.

### 4.1. Defining requirements by business flow

For every read/write flow, specify:

- Who is the authoritative writer and how many concurrent writers exist?
- After a write, which clients need to see new data and within what timeframe?
- Are stale reads acceptable? If so, how stale at maximum?
- Are ordering guarantees needed across events or multiple records?
- If two writers update the same key, what is the conflict resolution rule?
- During a provider or network partition, does the business prefer availability or rejecting writes to preserve consistency?

Translate answers into measurable criteria. For example: after an order-status update API returns success, the status query API must reflect the new version within two seconds in the same region; consumers must process events in order per `orderId`; analytics replicas may lag by at most five minutes. These thresholds are illustrative and must be confirmed by business owners.

### 4.2. Consistency in databases and replication

Primary/replica databases typically exhibit replication lag. Reading from replicas can save cost or offload the primary, yet immediately after a write it can return stale data. When business logic requires read-your-writes, read from the primary for a bounded window, use session consistency if the service supports it, or wait until the replica reaches the recorded watermark.

In CDC-based migrations, distinguish when a record commits on the source from when that change applies on the target. Track the log sequence number (LSN), binlog position, or checkpoint corresponding to your engine and tooling. At cutover, you must know the exact position applied at the target; seeing a replication process running does not prove data has caught up.

Schema migrations also affect consistency. Use an expand-and-contract strategy when old and new versions must coexist: add compatible columns or structures, deploy code capable of staged reads/writes, backfill data, switch reads, and remove legacy structures only after a safety window. Avoid breaking schema changes while source and target run side by side.

### 4.3. Consistency in events and messaging

Most distributed messaging systems provide at-least-once delivery or may redeliver under certain conditions. Consequently, consumers must be idempotent. Do not treat an "exactly-once" setting on one service as an end-to-end business transaction guarantee spanning databases, brokers, and external APIs.

Assign unique event IDs, persist processing markers inside the business transaction where possible, and use the Transactional Outbox pattern to prevent committing to the database without publishing the message. Consumers can use an Inbox or processed-events table to ignore already-applied events. If ordering is required, specify a partition key or session keyed by an aggregate such as `orderId`; do not rely on global ordering unless the broker explicitly guarantees it.

When migrating brokers, a message already processed on the source might be replayed onto the target. Maintain a deduplication policy spanning the entire transition, lasting longer than retry and replay windows. Reconciling received message counts does not replace reconciling business outcomes.

## 5. Transition strategies and trade-offs

No single migration strategy fits every workload. Select an approach based on data size, compatibility, maximum downtime, tolerance for parallel runs, and rollback feasibility.

| Strategy | How it works | Advantages | Costs/risks |
|---|---|---|---|
| Big-bang/offline | Freeze writes, copy data, verify, then start at target | Simple workflow; avoids prolonged parallel sync | High downtime; window depends on transfer and check speed |
| Online migration with CDC | Initial bulk load, continuous change sync, brief write freeze at the end | Minimizes downtime; provides checkpoints for reconciliation | Replication and operational costs; must handle schemas and lag |
| Blue-green | Stand up full target environment, verify, then switch traffic | Fast traffic cutover and staged control | Cost of two environments; post-switch writes require a separate plan |
| Canary | Shift a fraction of traffic or a subset of tenants first | Limits blast radius; observes real behavior | Requires consistent routing; shared data can complicate isolation |
| Strangler/phased | Migrate capability by capability or service along business boundaries | Breaks up risk; prioritizes high-value areas | Long duration; multiple providers and routing layers coexist |
| Shadow read | Mirror read queries to target for comparison without returning target responses to users | Tests compatibility under real load | Increases read cost and load; must prevent side effects and unnecessary sensitive data exposure |

Blue-green describes maintaining two environment versions, whereas canary describes traffic distribution. They can be combined. CDC is a data synchronization technique rather than a standalone traffic strategy; it is commonly paired with blue-green or phased migrations.

### 5.1. When to choose each approach

Big-bang can make sense for small applications with modest data, acceptable downtime windows, and tested backups. Online migration suits large datasets or tight downtime budgets, provided tooling supports the exact engines and topology, and operations understands checkpoints and reconciliation.

Phased migration fits systems with clear business boundaries, such as moving document storage first and messaging later. Keep API contracts and ownership rules explicit on both sides. If one business transaction writes across multiple capabilities spanning two providers, latency and partial failures add complexity.

Shadow reads help compare read responses, provided they never trigger side effects such as creating objects, sending emails, charging accounts, or publishing messages. For sensitive data, replicate only the minimum needed for verification and obey access and retention policies.

## 6. Managing consistency during parallel runs

The dual-run phase is typically the most expensive and hardest to control. Clarify whether "dual-run" means running two application deployments, reading from two places, or writing to two places. These three cases carry vastly different risks.

- **Two application deployments running, one writer:** can be safe if only one environment is permitted to handle writes or writer authority is strictly enforced.
- **Shadow reads from two places:** used for comparison; the target must trigger no side effects. Comparisons must normalize ordering, timestamps, default fields, and acceptable tolerances.
- **Dual-writes to two places:** easily produce states where one side succeeds and the other fails. Use only with conflict resolution, idempotency, retries, reconciliation, and clear rules for authoritative state.

A safer pattern for many systems is single-writer: at any moment, only one provider accepts authoritative writes. Use fencing tokens or monotonically increasing epochs to stop old instances from continuing to write after writer ownership moves. Changing an environment variable or DNS alone is insufficient as a write fence because existing processes may still hold open connections and credentials.

When synchronizing changes, record watermarks/checkpoints. Every record or event needs identity and version metadata to determine which changes have already been applied. When two versions update the same entity, use optimistic locking/versions or deterministic business rules; never blindly pick the newer timestamp if clocks are unsynchronized or wall-clock order does not reflect causality.

## 7. Gate-controlled transition plan

An execution plan should specify owners, timing, commands/automation, observability signals, and exit criteria for every step. Below is a reference sequence for an online migration.

### Phase A – Discovery and baseline

1. Inventory services, data, dependencies, credentials, endpoints, and network flows.
2. Measure baselines: request rate, latency, error rate, database load, message lag, monthly spend, and data growth.
3. Confirm consistency requirements, RPO/RTO, SLOs, retention, and downtime windows with business owners.
4. Check compatibility of database engines, SDKs, Spring Boot, Spring Cloud, and runtimes.
5. Build a three-scenario TCO model and approve migration/dual-run budgets.

### Phase B – Target build and verification

1. Provision target resources, networks, private endpoints, roles, secrets, keys, and backups.
2. Configure Spring Boot adapters/providers via profiles or deployment settings.
3. Test connectivity, permissions, TLS, quotas, and latency from the actual runtime.
4. Run contract tests for storage, databases, and messaging; test timeouts, throttling, and expired credentials.
5. Trial-transfer a representative dataset, measuring throughput, cost, and reconciliation.

### Phase C – Sync and rehearsal

1. Run the initial data load and enable CDC or incremental sync.
2. Monitor lag, checkpoints, retries, DLQs, checksums, and egress spend.
3. Execute shadow reads or controlled canaries.
4. Rehearse cutover and rollback with test data/traffic; measure actual durations.
5. Lock down runbooks, on-call staffing, communication channels, and change-window permissions.

### Phase D – Cutover

1. Confirm go/no-go against approved criteria.
2. Announce the change window and enable safeguards, such as restricting admin changes or pausing batch jobs.
3. Stop producers or freeze writes on the source; finish in-flight transactions and drain consumers per plan.
4. Record the final source watermark; wait for the target to apply up to the watermark and confirm lag is within bounds.
5. Run data reconciliation and verify business invariants.
6. Transfer writer fencing token/ownership to the target, then shift traffic via gateway, feature flags, or DNS.
7. Enable canary traffic, monitor signals, and ramp up once criteria pass.

### Phase E – Stabilization and closeout

1. Monitor errors, latency, throughput, lag, retries, DLQs, quotas, security, and costs over the stabilization window.
2. Verify backups and test restoring on the target.
3. Resolve any residual discrepancies via audited reconciliation.
4. Stop replication and decommission source resources after the rollback window closes and data owners approve.
5. Update runbooks, architecture diagrams, dashboards, budgets, and operational ownership.

## 8. Go/no-go criteria and rollback

Never decide cutover solely because the target application starts cleanly. Require quantitative gates and designated owners empowered to halt the change.

| Category | Example go criteria | No-go conditions |
|---|---|---|
| Data | Checksums and counts within threshold; any variances explained | Missing or corrupt critical records unresolved |
| Replication | Lag below threshold and target applied final watermark | Checkpoints behind or unexplained CDC errors |
| Consistency | Business invariants and read-after-write tests pass | Stale reads possible beyond business tolerance |
| Security | Workloads use right principals, least privilege, valid secrets and TLS | Uncontrolled static credentials or overly broad permissions remain |
| Performance | p95/p99, throughput, and error rates within SLO | Target throttling or latency breaches approved thresholds |
| Recovery | Backup restore and rollback drills meet target duration | Post-cutover writes cannot be preserved |
| Cost | Dual-run and steady-state projections within budget | Egress, replicas, or support exceed unapproved limits |

Rollback must account for data written after cutover. If no writes occurred on the target, traffic can revert to the source once source consistency is confirmed. If the target accepted writes, you must reverse-sync, replay logs/outbox, or reconcile before allowing the source to accept writes again. When those changes cannot be preserved safely, rolling forward—fixing issues on the target and keeping writer authority there—may be safer than reverting blindly.

Set an explicit deadline for the rollback window and define exit conditions. The longer dual-run continues, the higher the dual-platform spend, access complexity, and data divergence risk. Conversely, shutting down the source too early eliminates recovery options. Base the window on risk and stability evidence, not guesswork.

## 9. Example: assessing an order service migration to a target cloud

Suppose a Spring Boot order-processing system uses managed PostgreSQL, object storage, and a message broker. The database holds 2 TB, document storage holds 12 TB, and peak traffic is 1,500 requests/second. The system permits at most 15 minutes of downtime, requires near-zero RPO for confirmed orders, and tolerates up to five minutes of lag on analytics metrics.

**Consistency assessment.** Order and payment tables require a single authoritative writer, ACID transactions, and duplicate-prevention controls. Consumers must be idempotent by event ID and preserve ordering per `orderId` where workflows require it. Search indexes and reports can use eventual consistency within the five-minute lag budget. Do not force secondary data onto strong consistency if business logic does not need it.

**Strategy assessment.** Pre-copy the 12 TB of objects using dedicated transfer tooling, then sync deltas. Use initial load plus CDC for the database if engine and topology support it. Migrate the broker via a bridge or event replay carrying event IDs; before cutover, drain backlogs or confirm replay procedures. Pair blue-green for runtime with canary for traffic while keeping a single writer.

**Cost assessment.** TCO covers source and target compute and databases during parallel runs, object storage in both clouds, initial 12 TB plus delta transfer, CDC, message bridge, egress, backups, KMS, observability, support, and cutover staffing. The model should include downside scenarios such as a one-week extended rollback window and re-transferring a portion of data. Unit prices must reflect actual regions and contracts; this example assumes no specific cloud pricing.

**Go/no-go.** Transfer writer authority only once CDC applies through the final watermark, order and payment checks show zero discrepancies, target consumers produce no duplicate side effects, latency meets SLOs, and post-cutover write preservation has been rehearsed. If replication lag breaches thresholds or rollback tests fail to preserve new transactions, postpone cutover.

This example illustrates how consistency requirements vary by data type, strategies can combine CDC with blue-green/canary, and migration costs must cover the entire overlap period where two environments coexist.

## 10. Integrating decisions into the Spring Boot application

Put provider selection and migration modes under controlled configuration. Example:

```yaml
app:
  migration:
    mode: ${MIGRATION_MODE:source}
    write-owner: ${WRITE_OWNER:source}
    epoch: ${WRITE_EPOCH:1}
  consistency:
    order-read-after-write: primary
    analytics-max-lag: 5m
```

This is illustrative application configuration. Protect `write-owner` and `epoch` with an authoritative coordination mechanism; never let individual instances decide independently. Feature flags or a control plane can switch modes, provided all instances observe consistent state and old writers are fenced.

Business ports isolate provider clients:

```java
public interface OrderRepository {
    Order findById(OrderId id);
    Order save(Order order);
}

public interface EventPublisher {
    void publish(OrderEvent event);
}
```

Database and messaging adapters connect to their corresponding managed services. Business services enforce invariants such as order-state validation and duplicate-update guards. Use a Transactional Outbox when order mutations and events must commit together; a dedicated publisher relays outbox rows to the broker and marks checkpoints only after acknowledgement.

Do not build abstractions assuming every provider supports identical transactions or identical consistency. Express required business capabilities explicitly, run contract tests on every adapter, and run integration tests against real services or compatible environments. Test failovers, timeouts, retries, stale reads, duplicate deliveries, and revoked permissions thoroughly.

## 11. Common assessment mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Comparing only unit prices for compute or storage | Misses networking, backups, requests, and staffing | Compare TCO at identical load and SLOs |
| Ignoring dual-run duration | Budget omits dual-environment expenses | Model transition scenarios and rollback deadlines |
| Using ETag or object counts as sole proof | May miss corrupted contents or wrong metadata | Use proper checksums and reconcile business attributes |
| Assuming replicas immediately reflect recent writes | Requests can return stale data | Specify read-your-writes and primary/replica routing policies |
| Dual-writing without idempotency | Creates duplicate transactions or side effects | Single-writer, outbox/inbox, and reconciliation |
| Treating a DNS switch as a complete rollback | Old writers or pooled connections keep mutating state | Fence writers, manage connections, and sync new writes |
| Rehearsing only the happy path | Unprepared when CDC, DNS, or provider APIs fail | Rehearse rollback, retries, failover, and data recovery |
| Using outdated cloud pricing in budgets | Inaccurate estimates for target region/contract | Record price sources and dates; refresh before sign-off |

## 12. Checklist before approving a migration

- [ ] TCO compares source, target, and parallel-run phases over the same time horizon.
- [ ] Unit prices cite sources, dates, regions, units, and usage assumptions.
- [ ] Egress, replication, requests, backups, security, observability, support, and staffing are included.
- [ ] Baseline, downside, and upside scenarios exist; top sensitivity drivers identified.
- [ ] Every data flow specifies consistency, ordering, RPO/RTO, and lag tolerance.
- [ ] Single authoritative writer and fencing mechanism exist for ownership transfer.
- [ ] CDC or sync tooling includes checkpoints, lag monitoring, and reconciliation.
- [ ] Consumers are idempotent; events carry IDs; dead-lettering and replay are controlled.
- [ ] Migration strategy fits downtime, volume, and compatibility constraints.
- [ ] Cutover defines quantitative go/no-go gates, owners, and monitoring windows.
- [ ] Rollback preserves post-cutover writes, or a clear roll-forward decision exists.
- [ ] Backup restores, runbooks, and communication plans have been rehearsed.
- [ ] Dual-run end date and source decommission criteria are defined.

A sound migration decision must prove all three dimensions: lifecycle cost stays within budget, data maintains the consistency required by the business, and the transition can halt or recover whenever criteria fail. When assumptions are measured, documented, and verified, teams can choose target providers and migration timing based on evidence rather than unit pricing or assumptions about a new platform.
