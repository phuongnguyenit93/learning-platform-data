# Deployment Rollback

Deployment rollback is the operation of returning a running service to an application version or configuration known to be stable after a deployment causes failures. In a Spring Kafka system, rollback must be treated as part of incident response because a new version may already have executed code, consumed or emitted events, updated databases, and triggered side effects on other systems.

Restoring an old image does not automatically undo what the new version already did. Published Kafka records remain in the topic; committed consumer offsets stay where they are; database rows already written and emails or payment requests already sent continue to exist. Therefore, before rolling back, you must determine whether the old version can read the system's current state and how already-executed side effects should be handled.

## 1. Distinguish Application, Configuration, and Data Rollbacks

During a deployment, multiple components can change together. Identify precisely which components need restoring:

| Component | What rollback means | What is not automatically undone |
|---|---|---|
| Application artifact | Return the Deployment or service to an image/build known to be stable. | Already published records, committed offsets, and written data. |
| Application configuration | Restore previous ConfigMaps, Secret references, environment variables, or runtime configuration. | Changes already triggered by the new config in databases or Kafka. |
| Database schema | Run a reverse migration if that migration was designed and tested to be reversible. | Data already deleted, transformed, or written in the new format. |
| Kafka topic/configuration | Restore topic settings or routing flows if those changes are reversible. | Records already written; increased partition counts cannot be reduced by normal operations. |
| Business data | Run a data-repair workflow or emit compensating events. | External side effects such as deliveries, sent emails, or completed payments. |

Never call deploying an old image a "full system rollback" if databases, Kafka, and downstream services have already accepted changes from the new version. In the incident report, clearly record which components were rolled back and which require reconciliation or compensation.

## 2. When Should You Roll Back?

Rollback is appropriate when there is sufficient evidence that the newly deployed version is the primary cause, a prior version operated stably, and the old version is compatible with current data and schemas.

Common signals to examine:

- Listener error rates surge immediately after deployment, such as deserialization exceptions, business processing failures, or database write errors.
- Producers fail to send records, publish acknowledgment errors rise, or Kafka transactions repeatedly abort.
- Consumer lag rises rapidly, throughput drops sharply, or partitions rebalance continuously after changing concurrency or listener settings.
- Record retries or dead-letter topic (DLT) volume spike abnormally.
- Downstream APIs, database connection pools, or JVM resources overload after deployment.
- Smoke tests or canary checks detect incorrect business outcomes.

Do not roll back solely on a single isolated alert. Compare when errors began against deployment timestamps, inspect dependencies and infrastructure, confirm the impact scope, and verify whether the fault also existed in the previous version.

### Rollback or Forward Fix?

| Situation | Usually appropriate direction |
|---|---|
| New code bug; prior version is compatible with current schemas and data | Roll back to the prior version, then investigate root cause. |
| New config caused failures and prior config remains valid | Restore the configuration known to be stable. |
| New version already wrote payloads the old version cannot deserialize | Consider a forward fix or data transformation first; direct rollback may make old consumers fail continuously. |
| Migration deleted or restructured data in ways the old version cannot understand | Prefer a forward fix or controlled recovery migration. |
| Bad events were already published to Kafka or external side effects completed | Roll back the app if needed, and separately run compensation or reconciliation. |
| Incident lies in brokers, network, or databases independent of the deployment | Fix the dependency; rolling back the app may not address the root cause. |

If compatibility of the old version is not yet proven, keep the system under control, halt rollouts or jobs generating more bad data, and choose a forward fix or containment measure. Do not let a rollback trigger a new error loop.

## 3. Mandatory Checks Before Rolling Back Spring Kafka

### Producer and Consumer Compatibility

In an event-driven system, producers and consumers may be deployed at different times. The old version must be able to read records already written by the new version. Check both directions:

- Can the old consumer read payloads produced by the new producer?
- Can the new consumer or new producer read/write compatibly with older records and schemas?
- Did enums, required fields, data types, headers, Kafka keys, or serializers change?
- Which compatibility policy does Schema Registry enforce, and did the new schema pass that policy?
- Can the old version handle headers or metadata added by the new version?

A seemingly minor JSON change can break compatibility if it renames a field, changes a type, turns an optional field into required, or emits an enum value unrecognized by older consumers. For Avro, Protobuf, or JSON Schema, verify format compatibility rules and the active registry configuration.

### Database Migrations and Data

The old version must run cleanly against the current database schema. The expand-contract pattern reduces risk:

1. **Expand:** add columns, tables, or indexes so the old version still works.
2. Deploy new code that reads/writes the new structure while maintaining required compatibility.
3. Backfill data and confirm the new application no longer depends on the old structure.
4. **Contract:** remove old columns or structures in a separate change only after no old version needs them.

If the new deployment already ran a destructive migration—such as dropping a column or making an incompatible type change—the old image may fail to start or write corrupt data. Never run down-migrations mechanically in production. Evaluate backups, recoverability, volume of newly written data, and migration impact before deciding.

### Consumer Groups, Offsets, and Topics

Rolling back an application does not return its consumer group to earlier offsets. Committed offsets stay in Kafka, and old consumers resume from where the group last committed. This is usually desired because it avoids reprocessing all prior data.

Do not reset offsets as a default rollback step. Resetting can reprocess events, create duplicate side effects, or corrupt state if listeners are not idempotent. Replay or reset offsets only with a dedicated plan, clear scope, and duplicate-prevention controls.

Check changes involving:

- New topics, retry topic names, or DLTs created by the new version.
- Partition counts, replication factors, retention, cleanup policies, and ACLs.
- Kafka keys or producer partitioning strategies.
- Consumer group IDs, subscription patterns, concurrency, and partition assignment behavior.
- Committed offsets, end offsets, lag, and records sitting in retry topics or DLTs.

Topic changes typically persist independently of application lifecycles. For example, an increased partition count cannot be undone by shrinking partition count through normal operations. The old version must operate safely with the existing topic state.

### Transactions and Producer Identity

If using Spring Kafka transactions or exactly-once semantics for consume-process-produce flows, verify transaction configs remain valid after rolling back. Specifically, concurrently running instances must have transaction ID prefixes configured to prevent duplicate identities and unexpected producer fencing. When blue-green or rolling deployments run two revisions concurrently, check how each revision generates transaction IDs.

Kafka transactions do not revert previously committed transactions. Consumers using `read_committed` isolation will still read records from transactions committed by the new version. If those records are incompatible with old code, payload handling or a forward fix is required.

## 4. Record Pre-Action State

Before changing versions, capture enough information to compare and continue investigating:

| Category | Information to record |
|---|---|
| Deployment | Service/Deployment name, namespace, current image digest or build ID, running revision, and replica count. |
| Configuration | Config version, feature flags, secret/config references, and relevant Spring Kafka values. Never put secret values into incident logs. |
| Kafka | Cluster, topic, partitions, consumer group, committed offsets, end offsets, lag, and record counts in retry/DLT. |
| Database | Migration version, backup status, timestamps of newly written data, and relevant schema changes. |
| Impact | Request/event IDs, correlation IDs, error window, counts of succeeded/failed transactions, and affected downstream services. |
| Observability | Dashboards, logs, traces, alerts, and deployment/incident start timestamps. |

Record the exact image digest or build ID rather than just a tag like `latest`. Tags can be repointed to a different artifact later; digests uniquely identify the exact image to restore.

## 5. Deployment Rollback Procedure

### Step 1: Declare Incident and Halt Rollout

Appoint an incident coordinator and a rollback operator. Halt active pipelines or rollouts so no new revision keeps mutating state. Communicate the impact scope in the operations channel per organizational process.

Identify which service is the fault source: producer, consumer, synchronous API, or an auxiliary worker. If multiple services were deployed together, roll back in the defined dependency order rather than rolling back everything blindly.

### Step 2: Select a Stable Revision

Check deployment history and verify the prior revision was genuinely stable. Verify the image digest, build ID, configuration, and migrations expected by that revision. If multiple revisions exist, pick one validated by production or canary metrics.

Do not pick a revision solely by most recent sequence number. An intermediate revision may contain the same bug or be incompatible with current schemas.

### Step 3: Verify Compatibility Preconditions

Before restoring, confirm the old consumer can read existing records, the old producer will not omit data required by newer downstream services, and the database schema has no changes breaking old code. Inspect retry topics, DLTs, and pending records as well.

If preconditions are not met, choose a forward fix, configuration fix, or controlled data transformation before swapping artifacts.

### Step 4: Execute Rollback Through the Proper Control Plane

Use the same control plane that manages deployments. If using GitOps, update desired state by reverting the configuration commit and letting the controller reconcile. Never edit the cluster directly while GitOps keeps overwriting state.

For a directly managed Kubernetes Deployment, inspect history and status with:

~~~bash
kubectl rollout history deployment/orders-consumer -n production
kubectl rollout status deployment/orders-consumer -n production
~~~

After identifying the target revision, e.g. revision 12:

~~~bash
kubectl rollout undo deployment/orders-consumer -n production --to-revision=12
kubectl rollout status deployment/orders-consumer -n production
~~~

This is an example for a Kubernetes Deployment; substitute your environment's namespace, resource, and revision. If the Deployment is managed via Helm or GitOps, use that tool as the primary source of changes.

For a Helm release, inspect history and status with:

~~~bash
helm history orders -n production
helm status orders -n production
~~~

After confirming the chart revision to restore, run `helm rollback` to the chosen revision and monitor release status. Do not run manual Helm rollbacks if your environment's GitOps process requires reverting commits in the repository.

### Step 5: Restore Configurations Accompanying the Artifact

An old artifact may require old configs, yet never blindly restore entire Secrets or ConfigMaps. Diff every change, identify which setting caused failures, and verify old values remain valid with current brokers, databases, schema registries, and downstream services.

Spring Kafka settings to review include:

- Bootstrap servers, security protocol, SASL/SSL, and truststore/keystore references.
- Consumer group ID, topic subscriptions, concurrency, poll/batch behavior, and acknowledgment mode.
- Deserializers, trusted packages, error handlers, retry backoff, retry topics, and DLT routing.
- Producer serializers, `acks`, retries, idempotence, transaction ID prefix, and timeouts.
- Timeouts, connection pools, listener auto-startup, and relevant feature flags.

Restore configurations selectively if only one setting caused the issue. Avoid reintroducing expired credentials or decommissioned endpoints into production.

### Step 6: Wait for Rollout Completion and Inspect Runtime

Confirm all target replicas run the intended image digest and are ready for traffic. Check pod restarts, readiness/liveness probes, startup failures, Kafka client initialization logs, and dependency connection errors.

For consumers, verify group membership is stable, partitions are assigned, listeners are actively running, and lag begins dropping at expected speed. For producers, confirm broker connections, metadata refreshes, and send acknowledgments work. Do not treat a Deployment reporting Available as sufficient proof that the Kafka flow is healthy.

### Step 7: Smoke Test and Monitor

Run a safe smoke test with a representative event or an approved test transaction. Confirm the record is published, consumed, target data is accurate, and no duplicate side effects occur.

Monitor dashboards and logs long enough to cover normal processing cycles. Compare against the pre-incident baseline and confirm metrics return within acceptable bounds before closing the incident.

## 6. Deployment Strategy Considerations

### Rolling Deployment

Rolling deployments replace replicas in batches. During transition, old and new pods may join the same consumer group concurrently. Kafka distributes partitions across consumers and rebalances may occur.

During rollback, check:

- New pods stopped accepting work and completed or safely handled in-flight work.
- Old pods started with the expected consumer group and subscriptions.
- Two versions are not executing an external action simultaneously without idempotency.
- Shutdown grace period is sufficient for listeners to stop cleanly; do not commit offsets for unfinished work.

When old and new versions join the same group, Kafka treats them as consumers in one group; records split by partition. This is not record-level canarying and does not guarantee every canary record is handled by the new version.

### Blue-Green Deployment

Blue-green maintains two environments to switch traffic between old and new versions. For HTTP, traffic shifts via services or ingress. For Kafka consumers, switching requires deliberate planning because the two environments might join the same group, use different groups, or write to a shared database.

If blue and green share one consumer group, they split partitions and can trigger rebalances during version switches. If they use separate group IDs, each environment reads independently and can apply the same event twice to a shared target. Use separate groups only when outputs are isolated or adequate deduplication/idempotency exists.

When switching back to blue, confirm green has stopped or been isolated, group membership is stable, and blue can handle records published or consumed by green while active.

### Canary Deployment

Canaries should bound blast radius by traffic, tenant, key, or selected functionality. For Kafka, partitioning and routing must be explicitly designed: producers may route a slice of traffic through a new version, while consumers may use a dedicated group or separate routing strategy.

Never let two independent consumer groups write to a shared sink without deduplication. Likewise, do not assume adding one canary replica in the same group routes a fixed percentage of records to it; partition assignment governs distribution.

When a canary fails, stop routing new traffic to the canary version, record events emitted or processed by the canary, and shift remaining traffic back to the stable version. Already-emitted events must still be handled compatibly or compensated.

## 7. Handling Affected Data and Events

Rolling back code does not delete published Kafka records or undo database commits. Once the system stabilizes, classify affected data:

1. **Valid and compatible events:** let the stable consumer process them through normal flows.
2. **Valid events incompatible with the old version:** consider a forward fix on the consumer, audited payload transformation, or routing through a compatible consumer.
3. **Faulty but repairable events:** preserve originals, generate corrected records with documented reasons, and republish via controlled replay.
4. **Side effects already executed:** apply business compensation or reconciliation workflows, such as emitting adjustment events, refunds, or updating delivery statuses separately.
5. **Duplicate events from reprocessing:** rely on event IDs and idempotency keys to prevent duplicate application; reconcile cases that already produced side effects before concluding.

Never delete topics or reset offsets to "clean up" deployment fallout. Those actions can destroy evidence, lose data needing processing, or trigger additional side effects. If replay is needed, create a separate plan with explicit topics/partitions/offsets, stable event IDs, idempotent consumers, and stop conditions.

With a transactional outbox, determine the state of outbox rows and published records. With a consumer inbox, confirm processing markers persist within the same business transaction. Never delete inbox rows merely to let the old version reprocess events.

## 8. Post-Rollback Monitoring

Monitor infrastructure health, Kafka streams, and business outcomes together:

| Metric group | What to watch |
|---|---|
| Deployment | Image digest/revision, ready replicas, restart counts, rollout status, and readiness failures. |
| Consumer | Consumer group membership, rebalance rate, committed offsets, end offsets, per-partition lag, and throughput. |
| Listener errors | Exceptions by type, deserialization failures, retry counts, DLT publish rate, and processing duration. |
| Producer | Send failures, request latency, retries, timeouts, broker disconnects, and transaction aborts/fencing. |
| Database | Connection pool, transaction rollbacks, deadlocks, lock waits, write latency, and migration/schema errors. |
| Downstream | API errors, timeouts, rate limits, duplicate requests, and side-effect states. |
| Business | Successful transactions, aggregate states, financial totals/quantities, missed or double-applied events. |

Signals requiring immediate investigation after rollback include consumer lag continuing to climb, DLT still rising, producer errors not dropping, continuous group rebalancing, or business errors persisting on the old version. When those occur, the hypothesis that "the new deploy was the sole cause" may be wrong, or a dependent change remains un-reverted.

Set explicit incident closure criteria, such as error rate returning to baseline, lag stabilizing or draining, no unexpected rollouts, critical transactions reconciled, and failing records assigned an owner. Observation duration should match system traffic and processing cycles.

## 9. Testing Rollback Readiness Before Production

Rollback must be rehearsed before it becomes an emergency action. In staging or an equivalent environment, test at least these scenarios:

| Scenario | Expected outcome |
|---|---|
| New version causes listener to throw exceptions | Rollout halts and app reverts to stable revision; old listener resumes cleanly. |
| New version publishes payloads with new fields | Old consumer still reads cleanly or designed forward-fix path activates. |
| Expand migration already ran | Old version continues running against the expanded schema. |
| Destructive migration already ran | Runbook blocks direct rollback and prescribes recovery/forward-fix path. |
| Consumer group rebalances during rollout | Partitions reassign without losing records or creating duplicate side effects. |
| Pod stops mid-record processing | Record can be redelivered and idempotency protects business mutations. |
| Producer transaction open when pod stops | Uncommitted transaction aborts/fences per Kafka mechanics; committed records persist. |
| DLT or retry topic holds records from new version | Restored version can read them or records are held for separate processing. |
| Blue-green running simultaneously | Group IDs, routing, and target sinks prevent unintended duplicate processing. |
| Rollback finished while downstream still fails | Closure criteria prevent closing the incident based solely on Deployment status. |

Rehearse the full path: detection, halting rollout, capturing evidence, verifying compatibility, rolling back, smoke testing, monitoring, and data reconciliation. Record execution times and error-prone manual steps to refine the runbook.

## 10. Preventing Difficult Rollbacks

Several practices shorten recovery time:

- Use immutable images, record digests/build IDs, and retain artifacts of stably running revisions.
- Keep deployment history, chart versions, Git commits, and matching configs traceable.
- Roll out database changes via expand-contract; avoid bundling breaking migrations with code releases.
- Design event schemas for backward and forward compatibility; enforce compatibility checks in CI before publishing schemas.
- Keep event IDs stable and use inbox/outbox or idempotency keys for critical side effects.
- Keep consumer group IDs stable across revisions for the same processing flow; change group IDs only with an explicit backfill or consumer migration plan.
- Decouple feature flags from artifacts to disable new behavior quickly, while governing change permissions and recording history.
- Configure proper health checks for listeners and dependencies; separate readiness from liveness to avoid restart loops during transient dependency outages.
- Monitor lag, retries, DLT, producer errors, and business metrics immediately after every deploy.
- Practice rollbacks periodically, including cases where new data was already written and old code must read it.

Feature flags can serve as faster containment than a rollback when only one new feature misfires. However, toggling a flag does not fix already-written data and does not replace compatibility checks.

## 11. Incident Execution Checklist

### Before Rollback

- [ ] Confirmed error onset correlates with the deployment.
- [ ] Halted rollout and designated coordinator and operator.
- [ ] Recorded image digest/build ID, revision, config version, and timestamps.
- [ ] Captured consumer group state, offsets, lag, retry topics, and DLT state.
- [ ] Checked producer/consumer schema compatibility with existing records.
- [ ] Confirmed old version is compatible with current database schema and data.
- [ ] Identified already-executed side effects and compensation/reconciliation plan if needed.
- [ ] Selected the right control plane and target revision for rollback.

### During Rollback

- [ ] Modified deployment/configuration only via the designated control plane.
- [ ] Confirmed new replicas stopped in a controlled manner.
- [ ] Confirmed all target replicas run the intended artifact and configuration.
- [ ] Verified Kafka connections, listeners, producers, and dependencies.
- [ ] Confirmed consumer group stability and no unplanned offset resets.
- [ ] Executed a safe smoke test.

### After Rollback

- [ ] Error rate, lag, retries, DLT, and producer failures returned to acceptable bounds.
- [ ] Confirmed no restart loops or abnormal rebalancing.
- [ ] Reconciled critical business data and side effects.
- [ ] Assigned ownership for failing records or data needing compensation.
- [ ] Recorded timeline, restored revision, decisions, and operational evidence.
- [ ] Filed follow-ups to fix root cause and improve deployment processes.

## 12. Rollback Completion Criteria

Deployment rollback is complete only when the stable revision runs across the entire intended scope, producers and consumers operate normally, technical metrics return within acceptable bounds, and critical business transactions are reconciled. Events or side effects created while the faulty version ran must each reach an explicit resolution: processed, queued for replay, compensated, or accepted under a documented decision.

A healthy Deployment proves only that the application started. It does not prove Kafka and database data are correct. Close the incident only after confirming both runtime health and business outcomes, while preserving evidence so future rollbacks execute quickly and safely.
