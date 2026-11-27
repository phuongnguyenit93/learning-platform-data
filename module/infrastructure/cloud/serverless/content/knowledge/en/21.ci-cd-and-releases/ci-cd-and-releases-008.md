# Rolling Back Code, Configuration, and Stateful Resources

Rollback means returning a failing system to a verified operational state. For Java serverless, this is more than redeploying an old JAR. A release can include function code, runtime configuration, environment variables, IAM policies, triggers, database schemas, queues, checkpoints, object storage, and data mutations already performed by the function.

Therefore, rollback must distinguish three categories: **versionable code and configuration**, **infrastructure reproducible via IaC**, and **data/business state requiring preservation or controlled recovery**. Switching an alias back to an old function version can restore code quickly, yet it does not automatically reverse a column-dropping migration, an already-processed message, or a payment sent to an external system.

Within **CLOUD_SERVERLESS**, this lesson focuses on developing and deploying Java functions triggered by HTTP, messages, or events while handling triggers, state, access permissions, retries, idempotency, cold starts, scaling, and cost. It builds a framework for planning rollbacks across code, configuration, and stateful resources—from release packaging through post-incident recovery and verification.

## 1. Rollback Restores Behavior, Not Just Files

A serverless release typically changes several components at once:

| Component | Example Change | Question When Rolling Back |
|---|---|---|
| Code artifact | New JAR, ZIP, or container image | Is there an immutable, verified old artifact? |
| Function configuration | Runtime, memory, timeout, concurrency | Is the old configuration compatible with current code and triggers? |
| Environment/configuration | Feature flags, endpoints, schema mode | Is there a secret-free config snapshot to restore? |
| Identity and permissions | Execution role, service account, resource policy | Does old code still have sufficient permissions without over-privilege? |
| Triggers/integrations | API routes, queue mappings, event filters | Can traffic be shifted or events paused safely? |
| Database/schema | Added columns, indexes, tables, or type changes | Can old code run against the new schema? |
| Persistent data | Objects, records, checkpoints, workflow state | Must we retain, replay, restore, or run a compensating migration? |
| External side effects | Emails, payments, webhooks, device commands | Is a compensating action needed rather than erasing history? |

The goal of rollback is restoring service behavior and preserving data correctness. Not every change can be reversed in place. Some changes require a forward fix or compensating action.

## 2. Distinguishing Rollback, Roll-Forward, and Compensation

Three common recovery approaches:

- **Rollback:** switch code, config, or traffic back to a previously known-good version.
- **Roll-forward:** release a new fix to resolve the issue in the current state, often needed when schemas/data have moved forward and are incompatible with old code.
- **Compensation:** execute a compensating business operation to offset already-occurred side effects—such as refunding a charge or canceling an order—rather than pretending the prior action never happened.

| Scenario | Typically Appropriate Approach |
|---|---|
| New function fails due to code bug, schema still compatible | Roll back alias/revision to old artifact |
| New environment variable is wrong | Restore previous config version and verify secret references |
| Migration only added nullable columns | Roll back code; leave expanded schema intact until safe |
| Migration deleted/transformed data irreversibly | Controlled restore or roll-forward |
| Message already triggered email/payment charge | Business idempotency and compensation |
| Event checkpoint advanced past failed events | Controlled replay from an appropriate offset/checkpoint |
| New IAM policy blocks invocations | Restore known-good least-privilege policy and verify principal/source |

Do not choose rollback merely because it is the fastest operation. First identify whether the failure lies in code, config, infrastructure, or data; then pick a recovery path that avoids losing further valid state.

## 3. Packaging Redeployable Releases

For reliable rollbacks, every release must have an immutable artifact. Never rebuild an old source tag and assume the JAR or image will be byte-identical to the previous build.

A release record should store:

- Release ID and build/deploy timestamps.
- Git commit, repository, branch/tag, and approver.
- JAR/ZIP URI or container image digest.
- SHA-256 digest of the artifact.
- Java runtime, framework, and dependency lock/versions.
- Build provenance, signatures, and SBOM if applied by the pipeline.
- Corresponding function version, Cloud Run revision, or deployment slot.
- Config revision/manifest and secret version references, without recording secret values.
- IaC commit/plan and database migration version.
- Triggers, alias/traffic mappings, and critical feature flags.

Example secret-free release manifest:

```json
{
  "releaseId": "orders-2026.11.17.3",
  "sourceCommit": "8f4c2b1d...",
  "artifact": {
    "uri": "registry.example.com/orders@sha256:abc123...",
    "sha256": "abc123..."
  },
  "runtime": "java21",
  "configRevision": "orders-prod-config-42",
  "migrationVersion": "V018",
  "deployment": {
    "platform": "cloud-run",
    "revision": "orders-00042-xyz"
  }
}
```

Digest and revision values here are illustrative. In a real release system, store full values and verify artifacts prior to deployment. Never put passwords, access keys, private keys, or secret values into manifests.

## 4. Use Immutable Artifacts and Promote the Exact Same Build

A pipeline should build once and promote that exact artifact across dev, staging, and production. Environment differences are passed via config/secrets/identities without modifying JAR or image contents after signing.

For containers, deploy by digest rather than mutable tags. For JAR/ZIPs, store artifacts by version and digest in a registry or object storage with retention. Protect write/delete permissions and retain artifacts long enough for rollbacks, audits, and incident investigations.

Old artifacts must remain downloadable when:

- A new canary fails after partial traffic shifting.
- An IAM or config error is discovered late.
- Staging needs to be reproduced for investigation.
- A function version must be restored after several releases.

If registry retention policies purge artifacts too aggressively, rollback operations can fail even though old function version or revision metadata still exists.

## 5. Versioned Deployments and Traffic Shifting

Serverless platforms usually provide ways to maintain multiple versions or revisions side by side. This forms the foundation for fast rollbacks.

| Platform | How Versions Are Kept | How Traffic Shifts / Rolls Back |
|---|---|---|
| AWS Lambda | Published versions and aliases | Point production alias back to known-good version |
| Google Cloud Run | Immutable revisions | Shift traffic back to previous revision |
| Azure Functions | Deployment slots on supported plans | Swap slots back or redeploy previous artifact |
| Other container/FaaS platforms | Platform-specific versions/revisions/deployments | Switch route or redeploy verified digest |

Traffic shifting lets you test a new release on a subset of requests before cutting over completely. You can use canary, linear rollout, or blue/green depending on platform capabilities. Verify plan and function-type support; not every platform or hosting plan offers identical deployment slots or traffic splitting.

## 6. Rolling Back AWS Lambda with Published Versions and Aliases

A Lambda published version is an immutable snapshot of code and versioned settings at publish time. An alias is an updatable pointer to a published version. Production integrations should invoke an alias rather than `$LATEST` directly if rapid version switching is required.

For example, alias `prod` currently points to version `42`. If version `43` fails, point the alias back to version `42`:

```bash
aws lambda update-alias \
  --function-name orders-handler \
  --name prod \
  --function-version 42
```

Verify the alias after updating:

```bash
aws lambda get-alias \
  --function-name orders-handler \
  --name prod
```

Triggers/API integrations must reference the corresponding alias ARN so traffic actually routes through the alias. If a trigger invokes an unqualified function ARN or `$LATEST`, updating the alias may not affect that invocation path.

Lambda aliases also support routing a fraction of traffic to another version in certain setups. When canarying, define alarms and automatic halt/revert criteria. Updating an alias does not automatically reverse database migrations, processed messages, or external side effects.

## 7. Rolling Back Cloud Run via Revisions

Every Cloud Run service deployment creates a new revision. The revision retains the configuration and image from that deployment. If the new revision fails, route traffic back to an older revision.

Example:

```bash
gcloud run services update-traffic orders-service \
  --region=asia-southeast1 \
  --to-revisions=orders-service-00041-abc=100
```

Substitute the revision name with a known-good revision in the service. Inspect traffic mappings after updating and confirm the older revision remains ready to serve.

A Cloud Run revision rollback only shifts traffic. If new settings live in Secret Manager, database schemas, or external resources outside the revision, handle them separately. Furthermore, if the old revision references a Secret Manager version that was disabled/deleted or a service account whose permissions were revoked, shifting traffic back to the old revision can still fail.

## 8. Rolling Back Azure Functions via Deployment Slots or Old Artifacts

For Azure Functions on hosting plans supporting deployment slots, you can deploy the new version to a staging slot, verify it, and swap with production. If errors appear after swapping, swap back if slot state and configurations remain compatible.

Certain application settings can be marked slot-specific (deployment slot settings). Identify which settings stay with the slot and which move with swapped content. If connection strings, storage accounts, or secret references swap unexpectedly, the function may access the wrong environment.

Deployment slots are not available on every plan or Functions configuration. When slots are unavailable, retain the old artifact version and redeploy the exact published package. Whether using slots or redeploying, re-verify triggers, managed identities, host storage, app settings, and permissions after rolling back.

## 9. Managing Configuration as Part of the Release

Old code may fail to run if current configuration has changed. A release manifest should reference config revisions or versions of critical values.

Configuration groups typically requiring management:

- Feature flags and business rule toggles.
- Endpoints for databases, queues, APIs, or object storage.
- Timeouts, retry counts, batch sizes, concurrency, and memory.
- Event filters, queue/topic/subscription names, and consumer groups.
- Log levels, tracing sampling, and metric dimensions.
- Secret references/versions, certificates, and encryption key references.

Store non-secret configurations in version-controlled source control or config stores. For secrets, record only references and version IDs in release records; never copy secret values into Git, artifacts, logs, or manifests.

When rolling back configuration:

1. Identify which settings changed alongside the release.
2. Verify old code is compatible with old values and current resources.
3. Restore the known-good config revision or update the specific settings needed.
4. Preserve emergency security changes such as revoked credentials; never restore a suspected compromised secret just to make old code run.
5. Verify the function received the restored config and no instances unexpectedly retain stale values.

## 10. Secret Rollbacks and Credential Rotation

Secrets have their own lifecycle. If a secret was rotated due to expiration or compromise, never roll back to the old secret simply because the previous release used it.

Safer approach:

- Both new and old code read secrets via stable references.
- Secret manager retains the current version and can retain the prior version during transitions.
- When rotating, update server-side credentials first or support a brief dual-credential overlap window.
- After all consumers use the new credential, revoke the old credential.

If an old release hardcoded or only understands the old credential, update code or a config adapter to support rotation before revoking. Restoring a compromised credential is dangerous and can reopen access to attackers.

## 11. Database Migrations Must Be Backward-Compatible

Databases are usually the hardest component to roll back because new code may have written data under a new schema. A destructive migration—dropping columns, changing data types, or altering field meanings—can render old code unable to run.

A common strategy is **expand–migrate–contract**:

1. **Expand:** add new columns/tables/indexes without breaking old code, typically allowing nulls or safe defaults.
2. **Migrate:** deploy code able to read both old and new schemas; backfill data in batches; optionally dual-write during transition if design guarantees consistency.
3. **Switch:** move all consumers to the new field/schema and observe.
4. **Contract:** only in a later release, once no old code or consumers remain, drop old fields/tables.

Example adding a new column:

```sql
ALTER TABLE orders
ADD COLUMN fulfillment_status_v2 VARCHAR(32);
```

New code can write both `fulfillment_status` and `fulfillment_status_v2` during transition. Old code continues reading the old column. After backfilling and moving all consumers to the new field, stop writing the old field; dropping the old column should be a separate migration after the rollback window ends.

Never combine expand and contract in the same release if fast code rollback is required. Rolling back binaries is only safe while the schema remains compatible with that binary.

## 12. When Is a Database Restore Needed Instead of Code Rollback?

A database restore recovers data from snapshots or point-in-time recovery (PITR). Use it only when data is corrupted, accidentally deleted, or ruined by a migration beyond repair via compensating migrations.

Restores carry risks:

- Valid data written after the snapshot/PITR timestamp may be lost.
- Restored database endpoints/hostnames may differ; functions need config updates.
- Secrets, security groups, network routes, and IAM database authentication must be verified.
- Database restores take time and interrupt processing.
- Queues/events acknowledged after the restore point will not automatically reappear in the database.

Typically, restore to a new instance/database, verify data, and then switch traffic or endpoints per runbook. For partial corruption, consider exporting/reconciling records instead of replacing the entire database. Test restores regularly; an untested snapshot is not sufficient proof of recoverability.

## 13. Rolling Back Object Storage Data

Object storage may support versioning or retention. With S3 versioning, an overwrite creates a new object version; previous versions remain readable if version IDs exist and permissions allow.

Things to watch:

- Deleting an object in a versioned bucket may insert a delete marker instead of removing all versions.
- Lifecycle policies may expire older versions after retention windows.
- Object Lock/retention/legal holds can block deleting or modifying objects.
- KMS keys must still exist and permit decrypting older versions.
- Event notifications may fire new events when restoring/copying objects; avoid unintentionally re-triggering pipelines.

If a function generated corrupted output files, write corrected files or copy the right previous version back to the target key. Before restoring, check which consumers read that key and whether related metadata/indexes/caches need updates.

## 14. Rolling Back Queues, Messages, and Event Streams

Already-processed messages cannot automatically "unprocess" merely by deploying old code. Distinguish pending messages, in-flight messages, acknowledged/completed messages, and events replayable from retention.

| Source | States to Inspect | Recovery Approach |
|---|---|---|
| SQS/queue | Visible, in-flight, DLQ, retention | Stop consumer, preserve messages, redrive DLQ or controlled replay |
| Service Bus | Active, locked, deferred, dead-letter | Stop consumer, check lock/delivery counts, replay DLQ per procedure |
| Pub/Sub | Unacked messages, ack deadline, subscription retention | Adjust consumer, seek/replay per subscription and retention capabilities |
| Event Hubs/Kafka-like streams | Offsets/checkpoints, partitions, retention | Use appropriate consumer group/replay offset; expect event re-execution |
| S3 events | Object versions and notifications | Replay events or run reconciliation against object listings |

Before pausing consumers, verify whether backlog growth is safe. If a faulty release corrupted data while still acknowledging messages, identify affected messages and retain event IDs/idempotency keys for selective replay.

When resetting checkpoints or redriving DLQs, events may be processed again. Consumers must be idempotent; otherwise, replay can create duplicate orders, emails, or payment charges.

## 15. External Side Effects Requiring Compensation

A function may call payment gateways, send emails, open tickets, or dispatch webhooks. These actions happened outside the system and cannot be undone by restoring a database snapshot.

Examples:

- If a payment was captured, call refund/void APIs per business rules.
- If an email was sent, it cannot be unsent; send a follow-up correction if necessary.
- If a webhook was sent to a partner, use idempotency keys and reconciliation APIs to verify state.
- If an order was sent to fulfillment, issue a cancellation/return workflow.

This is saga compensation, not physical rollback. Store business events, external request IDs, idempotency keys, and outcomes for investigation. Never delete audit trails to make state look as though nothing happened.

## 16. Idempotency Makes Rollbacks and Replays Safe

Rollbacks often involve retries, redrives, or replays. If an event can be processed multiple times, side effects must be idempotent.

A simple pattern:

```java
public void handle(OrderSubmitted event) {
    String key = "order-submitted:" + event.eventId();

    idempotencyStore.executeOnce(key, () -> {
        orderService.submit(event.orderId());
        return null;
    });
}
```

`executeOnce` is an illustrative port. Real implementations must store keys in a database/shared store using conditional writes or transactions. Never use a `static Set` inside a function instance, because instances restart, scale out, and run concurrently.

For external APIs, propagate idempotency keys to providers when supported. If an invocation writes to the database and times out before acknowledging the message, retries must recognize the work already completed. The outbox pattern helps commit business state and outgoing events in one transaction, then relay events with safe retries.

## 17. Rolling Back Infrastructure as Code

IaC manages functions, IAM, triggers, queues, buckets, databases, and networks. An `apply` or stack update can create, modify, replace, or delete resources.

Before rolling back infrastructure:

1. Record the deployed IaC commit and plan/change set.
2. Identify which resources changed in-place versus replaced or deleted.
3. Check `DeletionPolicy`, `UpdateReplacePolicy`, `prevent_destroy`, snapshots, and retention.
4. Check cross-stack/module dependencies and resources shared with other apps.
5. Restore prior IaC configurations or generate a new reviewed change set/plan.
6. Verify drift and actual resource state before applying.

Never blindly run `terraform apply` on an old commit. Current state may have changed, resources may have been replaced, or new data created post-release. Generate a fresh plan from current state and review every destroy/replace operation.

CloudFormation rollbacks can revert certain resource changes to a prior template, yet cannot undo external side effects like sent messages, API calls, or database migrations outside stack control.

## 18. IAM, Triggers, and Networking During Rollback

An older function version might rely on an IAM policy or endpoint that was subsequently altered. When rolling back code, verify:

- Execution roles/service accounts remain attached with least-privilege permissions.
- Resource-based policies still permit API Gateway, queues, event buses, or storage to invoke the function.
- Secret/KMS key versions remain accessible.
- Security groups, VPC connectors, private endpoints, and DNS remain accurate.
- Event filters, batch sizes, timeouts, and concurrency suit the old code.
- API schemas and event schemas emitted by producers remain compatible with old consumers.

Never roll back an IAM policy to an overly broad configuration just to restore service quickly. If a new permission accidentally blocks the function, fix the exact statement/condition and test both allow and deny paths.

## 19. Canary, Blue/Green, and Automated Rollback Criteria

Instead of shifting 100% of traffic immediately, roll out incrementally:

1. Deploy the new release without receiving production traffic.
2. Smoke test via test routes or synthetic events.
3. Shift a small percentage of traffic to the new release.
4. Monitor error rates, latency, throttling, business metrics, and downstream health.
5. Increase traffic in steps if thresholds pass.
6. If thresholds breach, stop rollout and shift traffic back to the old revision/version.

Signals that can trigger rollback:

- HTTP 5xx or function error rate climbs above baseline.
- p95/p99 latency breaches SLO over an observation window.
- Queue backlogs, consumer lag, or DLQs spike rapidly.
- Database connection pools exhaust or query latency spikes.
- Business failure rates rise—for example, payment declines due to bugs or stuck order states.
- Security metrics reveal abnormal access-denied spikes or unauthorized requests.

Do not rely solely on CPU or invocation success. A function can return HTTP 200 while persisting corrupted data. Include business metrics and post-deploy consistency checks.

## 20. Ordered Rollback Runbook

During a production incident, a clear runbook reduces ad-hoc decisions.

### Phase A — Assess and Contain Impact

1. Record release ID, function version/revision, error onset time, and blast radius.
2. Determine whether the fault lies in code, config, IAM, triggers, dependencies, or data.
3. If the function is actively writing corrupted data, pause triggers/traffic in a controlled manner.
4. Preserve pending queues/events; never purge messages or advance checkpoints just to clear dashboards.
5. Preserve logs, traces, request IDs, event IDs, and release manifests.

### Phase B — Select Recovery Path

1. Verify the old artifact and its signature/digest.
2. Confirm current schemas are compatible with old code.
3. Verify configs/secrets/permissions needed by old code.
4. Decide among code rollback, config rollback, roll-forward migration, or compensation.
5. If data restore is required, estimate the data-loss window and choose an approved recovery point.

### Phase C — Execute

1. Switch aliases/traffic/slots back to the known-good release or redeploy the verified artifact.
2. Restore the matching config revision.
3. Modify IAM/triggers/networking only where faulty and review permissions.
4. Execute compensating migrations or business compensations if needed.
5. Re-enable consumers/triggers incrementally after smoke tests.

### Phase D — Verify and Close Incident

1. Send representative test HTTP requests and events matching real flows.
2. Verify invocations, logs, traces, responses, and side effects.
3. Monitor queue backlogs, retries, DLQs, databases, and business metrics.
4. Reconcile events processed during the incident window.
5. Record restored release ID/digest, compensations executed, and data requiring reconciliation.
6. Schedule follow-up to fix root causes and update runbooks.

## 21. Example: Rolling Back a Java Order Processor

Suppose release `orders-v43` introduces a `fulfillmentStatusV2` field, but new code writes invalid values causing downstream consumers to reject orders. Release `orders-v42` still reads the old schema and the new column was added as nullable.

A sound sequence:

1. Halt rollout and revert the alias/revision to `orders-v42`.
2. Keep the `fulfillmentStatusV2` column intact; do not drop columns mid-incident.
3. Pause or throttle consumers generating bad data if necessary.
4. Identify affected event IDs and order IDs from logs/traces.
5. Fix bad data via compensating migration or idempotent reconciliation jobs.
6. Replay quarantined messages after data has been repaired.
7. Build `orders-v44` with proper validation and mapping; test in staging before canarying.
8. Only drop old columns in a later release once all consumers have migrated and the rollback window has closed.

This example shows code rollback can be fast while schemas and data stay intact to avoid losing information or breaking old code.

## 22. Common Rollback Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Deployed old code but function still fails | Config, IAM, secrets, or networking changed | Compare release manifests and check external dependencies |
| Alias points to old version yet requests hit new version | Trigger/API invokes `$LATEST` or unqualified ARN | Check integration targets and alias ARNs |
| Old revision gets traffic but fails to start | Secret version, service account, or dependency was revoked | Restore safe dependencies; never restore compromised secrets |
| Old code fails against current database | Migration broke backward compatibility | Roll forward or run compensating migration; never blindly delete data |
| Messages processed twice after replay | Non-idempotent consumer | Use idempotency keys and reconciliation |
| Queue loses messages after rollback | Queue/retention purged or messages already acked | Check DLQs, archives, and replayable event sources |
| Database restore loses recent transactions | Chosen PITR point is too old | Restore in parallel and reconcile data past recovery point |
| Terraform rollback wants to delete database | Old IaC commit triggers destroy/replace | Review plans, protect resources, and snapshot before applying |
| Old secret works but is insecure | Rollback restored a leaked credential | Keep rotation active; update code/config for new credential |
| Rollback finished yet business metrics remain wrong | Side effects occurred before code reverted | Run compensation and data reconciliation |

## 23. Checklist for Rollback-Ready Releases

| Question | Required Evidence |
|---|---|
| Is the artifact immutable? | JAR/ZIP/image digest, signature, and provenance |
| Is the previous release retained? | Registry retention and read access to old artifacts |
| Do we know which version/revision is running? | Release manifest, alias/revision mapping |
| Is configuration versioned? | Config revision and secret version references |
| Are schemas backward-compatible? | Expand–migrate–contract and N/N-1 code tests |
| Is data recoverable? | Backups/PITR, object versioning, and restore tests |
| Are events replayable? | Retention, DLQs, checkpoints/offsets, and idempotency |
| Do external side effects have compensation? | Business workflows, provider request IDs, and audit records |
| Can IaC roll back safely? | Plans/change sets, dependency graphs, and deletion protection |
| Are rollback criteria defined? | SLOs, business metrics, alarms, and accountable owners |
| Has the runbook been rehearsed? | Rollback/restore drills in staging |
| Can recovery be verified? | Smoke tests, reconciliation, and backlog/error monitoring |

## 24. Rehearsing Rollbacks and Improving Recovery Time

Rollbacks must be practiced before an incident hits. In staging, run drills:

- Deploy a new release and intentionally inject HTTP errors to verify traffic shifts back to the old revision.
- Change a setting and restore the previous config revision.
- Apply a new schema and verify old code continues working.
- Inject poisoned messages, route to DLQ, and replay after fixing the consumer.
- Restore a database snapshot/PITR to a new environment and verify data.
- Create a new object version and restore the previous version.
- Test an IaC apply involving resource replacement in a test environment and verify resource retention.
- Simulate secret rotation and roll back code without re-enabling old credentials.

Measure time to detect, time to decide, time to shift traffic, and time to reconcile data. These metrics clarify which rollbacks can be automated, which need approval, and which resources must be prepared in advance.

A good rollback does more than send requests back to old code. It keeps code, configuration, permissions, triggers, and data mutually compatible. For Java serverless, keep artifacts immutable, deploy via versions/revisions, design backward-compatible schemas, store recoverable state, handle replays with idempotency, and use compensation for external side effects. When these safeguards are built into release design, rollback becomes a controlled operational procedure rather than a risky gamble during an incident.
