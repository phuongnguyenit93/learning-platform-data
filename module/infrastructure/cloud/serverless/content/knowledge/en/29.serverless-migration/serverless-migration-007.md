# Parallel Runs, Shadow Traffic, and Result Evaluation

Migrating an application to serverless changes how it runs, scales, stores state, and handles failures. Switching all traffic at once can cause architectural flaws, data discrepancies, or capacity shortfalls to surface only after real users are impacted. Parallel runs and shadow traffic validate the new system against real-world workloads before transferring serving authority.

A **parallel run** is a phase where both the legacy system and the new system operate concurrently for a period so the team can compare behavior, data, and operations. **Shadow traffic** sends copies of requests or events to the new system to observe outputs while the legacy system still produces the response or business decision returned to users. Shadow traffic is not automatically safe: if copied requests trigger payments, send emails, or write to production data, you can execute side effects twice.

This lesson explains how to organize a phased migration, design a safe mirroring flow for Java serverless, compare outcomes meaningfully, set cutover gates, and prepare rollback. The ultimate goal is proving the new system meets business behavior, latency, reliability, security, and cost targets before taking full traffic.

## 1. Why Run in Parallel?

Legacy systems often contain undocumented behaviors: validation quirks, rounding rules, update ordering, retries, timeouts, default values, timezone handling, legacy data edge cases, and secondary integrations. Unit tests may not reflect real production workloads.

Running in parallel helps surface:

- Responses or business decisions that differ from the legacy system.
- Missing, extra, malformed, or wrong-state data.
- Java runtime latency or memory profiles that differ from expectations.
- Triggers, queues, retries, or concurrency failing under real traffic.
- Misconfigured permissions, network routes, secrets, or dependencies.
- Higher cost per transaction than the current model.
- Rare edge cases that only appear in production traffic.

A successful deployment only proves the artifact can be deployed. It does not prove business equivalence or readiness to replace the legacy system.

## 2. Distinguishing Parallel Runs, Shadow Traffic, Canary, and Dual-Write

These terms are often used interchangeably, yet they behave differently:

| Execution Mode | Requests Sent to New System? | Who Responds to User? | Writes Data? |
|---|---|---|---|
| Offline replay | Stored or synthesized data replayed to the new system | No direct user request | Writes only to a test/replay environment |
| Shadow traffic | Copies of requests sent to the new system | Legacy system | Candidate should be read-only or write to an isolated store |
| Parallel run | Both systems process the same business flow during reconciliation | Configured rule, usually legacy first | May write to two separate datastores or one authoritative store |
| Canary | A percentage of real requests served by the new system | Whichever system was selected per request | The serving system holds write authority |
| Dual-write | One write operation sent to both systems | Design-dependent | Yes; requires explicit consistency and recovery |
| Blue/green cutover | Traffic switches from blue environment to the new environment | Active environment | One designated writer |

Shadow traffic generally does not replace the primary response. Canary does: requests route to the candidate, and the candidate returns the result to the user. A load balancer sending 10% of traffic to a new target is canary or weighted routing, not shadow mirroring.

Dual-write is a separate data concern. If an application writes to two databases within one request, one write can succeed while the other fails. Without distributed transactions or reconciliation, the two systems diverge.

## 3. Phased Migration Model

A safe roadmap gradually increases confidence and traffic scope:

~~~mermaid
flowchart TD
    A["Inventory legacy behavior"] --> B["Replay historical data"]
    B --> C["Shadow traffic to candidate"]
    C --> D["Compare responses and data"]
    D --> E{"Criteria met?"}
    E -->|"Not yet"| F["Fix discrepancies and re-run"]
    F --> C
    E -->|"Yes"| G["Canary: fraction of real requests"]
    G --> H["Monitor SLOs and business metrics"]
    H --> I{"Scale-up thresholds met?"}
    I -->|"No"| J["Roll back traffic to legacy"]
    I -->|"Yes"| K["Increase canary percentage"]
    K --> L["Full cutover"]
    L --> M["Hold rollback window and reconcile"]
~~~

Stages can include:

1. **Baseline:** measure the legacy system and capture required behaviors.
2. **Offline replay:** replay sanitized requests/events into the candidate.
3. **Shadow:** mirror a portion of production traffic without creating production side effects.
4. **Comparison:** compare responses, data, latency, errors, and cost.
5. **Canary:** let the candidate serve a fraction of live requests.
6. **Progressive cutover:** step up traffic against agreed gates.
7. **Stabilization:** keep the legacy system ready for rollback for a defined window.
8. **Decommission:** shut down the legacy system only after the rollback window closes, data is reconciled, and dependencies have moved.

Never jump straight from shadow to 100% traffic. Shadow evaluates request processing; canary validates the candidate as the user-serving system.

## 4. Define Business Scope Before Mirroring

Not every endpoint or event belongs in the same experiment. Classify by operation type:

| Operation Type | Examples | Safe Testing Approach |
|---|---|---|
| Read-only | Profile lookup, catalog lookup | Mirror requests and compare responses |
| Deterministic calculation | Tax, shipping fees, points calculation | Mirror and compare normalized outputs |
| Command with side effects | Order creation, stock reservation, status updates | Run against an isolated datastore or fake dependencies |
| External side effect | Payment capture, sending email/SMS, issuing invoices | Mock/sandbox or block completely during shadow |
| Event consumer | SQS/Kafka/EventBridge handler | Replay to a separate queue with an isolated idempotency namespace |
| Scheduled job | Reconciliation, batch settlement | Run against a data snapshot or in dry-run mode |

A POST request is not necessarily impossible to shadow, but the candidate must never execute production side effects a second time. If side effects cannot be isolated yet, run only validation/calculation or use copied data.

## 5. Shadow Traffic Architecture

Traffic can be mirrored at the gateway/proxy or inside the application. Pick the placement based on security requirements, fidelity of request preservation, and reliability of copy delivery.

~~~mermaid
flowchart LR
    C["Client"] --> G["Gateway / Router"]
    G --> L["Legacy application"]
    L --> R["Response to client"]
    G -. "Mirror copy" .-> Q["Shadow queue"]
    Q --> S["Java serverless candidate"]
    S --> X["Isolated dependencies"]
    L --> O["Comparison store"]
    S --> O
    O --> A["Diff and metrics"]
~~~

In this model:

- The legacy system keeps returning the primary response.
- The gateway or a mirroring component sends a copy to a shadow queue.
- The candidate processes the copy in an isolated environment.
- The candidate writes comparison outputs to a comparison store.
- A worker analyzes diffs and emits metrics.
- The shadow path is forbidden from sending payments, emails, or commands to production dependencies.

Mirroring should be asynchronous and resource-bounded. If mirroring slows down primary requests or exhausts connection pools, the experiment itself degrades the live serving system.

## 6. Choosing Where to Duplicate Requests

Three common approaches:

**Gateway/proxy mirroring:** a proxy or service mesh receives a request and sends a copy to the candidate. The advantage is minimal changes to legacy code. Verify the proxy truly supports mirroring, preserves required headers, caps payloads, and does not wait for the candidate response.

**Application-level mirroring:** the legacy app creates a shadow envelope after handling the primary request. This allows selecting fields, attaching correlation IDs, and stripping sensitive data. However, avoid adding latency and handle copy-send failures gracefully.

**Event/log replay:** record requests or domain events to a controlled stream/log, then replay them to the candidate. This simplifies retries and analysis, though you must store enough context to reconstruct requests and protect sensitive data.

Not every gateway supports request duplication. Some canary features only split requests across two deployments rather than sending duplicate copies. Verify tool semantics before calling it shadow traffic.

## 7. Designing the Shadow Envelope

Avoid forwarding raw HTTP requests when the candidate needs only part of the data. Create an envelope with an explicit schema version and metadata:

~~~json
{
  "schemaVersion": 1,
  "experimentId": "migration-orders-2026-11",
  "correlationId": "req-7f2d",
  "sourceSystem": "legacy-orders",
  "targetSystem": "serverless-orders",
  "capturedAt": "2026-11-17T10:15:30Z",
  "operation": "CalculateOrder",
  "tenantKey": "tenant-42",
  "idempotencyKey": "order-command-987",
  "payload": {
    "currency": "VND",
    "items": [
      {
        "sku": "SKU-100",
        "quantity": 2
      }
    ]
  }
}
~~~

The envelope should include:

- Experiment ID to distinguish runs.
- Correlation ID to link logs across legacy, queue, and candidate.
- Schema version for controlled structural changes.
- Source/target system and operation.
- Capture timestamp and necessary cohort details.
- Stable idempotency key.
- Payload stripped or masked of unnecessary data.

Never put access tokens, cookies, passwords, payment card data, or secrets in shadow envelopes. If user/tenant identifiers are needed, prefer pseudonymous IDs or tokenization. Keep only fields needed for business evaluation.

## 8. Never Trigger Production Side Effects in Shadow Mode

This is the single most important safety rule. The candidate may execute production-like code, but dependencies must be configured to produce zero real-world actions.

Controls:

- Dedicated database/schema holding a sanitized data copy.
- Payment sandbox or fake payment adapter.
- Blocked outbound email/SMS replaced by a sink recording message contents.
- Dedicated object storage prefix for the experiment.
- Dedicated queue/topic; never publish to production event buses.
- IAM role scoped exclusively to shadow resources.
- Network egress blocked toward side-effect endpoints.
- Tag every request with an experiment ID.
- Set TTL on test data and clean up after completion.

An application flag like `SHADOW_MODE=true` helps, yet is insufficient if one code branch forgets to check it. Combine application guards with IAM, network policies, sandbox credentials, and resource isolation.

For payments, use only a sandbox or fake adapter. Never submit real authorizations/captures just to compare the candidate against legacy. For email/SMS, write to a sink and compare masked templates/recipients instead of messaging real customers.

## 9. Ensuring Shadow Traffic Does Not Impact the Primary System

Shadow traffic adds load. Mirroring 100% of traffic doubles request volume hitting the candidate and shared dependencies.

Safeguards:

- Start with a low sampling rate.
- Use a dedicated queue with retention and a DLQ.
- Cap maximum concurrency on the candidate.
- Bound batch sizes and replay throughput.
- Use short timeouts on the mirror publisher.
- Apply backpressure when shadow queue backlog grows.
- Drop shadow copies under overload instead of blocking primary requests.
- Put a circuit breaker around the mirror publisher.
- Isolate compute, database, and network quotas where possible.
- Monitor impact on legacy latency and error rates.

If mirror enqueuing sits on the critical path, a slow queue stretches primary request latency. Use an outbox or infrastructure-level async fan-out; if synchronous publishing is unavoidable, use a short timeout and treat shadow publishing as best-effort. Emit metrics for dropped copies so you do not mistakenly believe all requests were compared.

Never use fire-and-forget background threads in AWS Lambda to send shadow traffic after the handler returns. The runtime may freeze or reuse the execution environment, giving no guarantee background work finishes. Use durable queues, outboxes, or controlled proxy mirroring.

## 10. Purposeful Traffic Sampling

Sampling bounds costs and blast radius. You do not need to mirror every request.

Sample by:

- Random percentage, e.g., 1% or 5%.
- Specific tenants or internal customer groups.
- Specific routes or operation types.
- Payload sizes.
- Regions or source channels.
- Requests carrying specific features/versions.
- Known edge cases such as currencies, timezones, or order statuses.

Avoid sampling bias. If you sample only small, simple requests, the candidate may look healthy while failing on large payloads or rare flows. Combine random sampling with targeted cohorts to cover both typical traffic and edge cases.

Record eligible request count, sampled count, successfully mirrored count, and candidate-completed count. Without a denominator, you cannot judge whether the diff rate is representative.

## 11. Java: Separating Business Logic from Adapters and Side Effects

Java applications should separate calculation/business rules from HTTP, queue, database, and external service adapters. This lets the candidate run on identical inputs using fake adapters or isolated datastores.

A simple structure:

~~~java
public interface OrderCalculator {
    OrderQuote calculate(OrderCommand command);
}

public final class LegacyOrderCalculator implements OrderCalculator {
    @Override
    public OrderQuote calculate(OrderCommand command) {
        // Current logic of the legacy system.
        return legacyRules.calculate(command);
    }
}

public final class ServerlessOrderCalculator implements OrderCalculator {
    @Override
    public OrderQuote calculate(OrderCommand command) {
        // Logic of the candidate Java function.
        return newRules.calculate(command);
    }
}
~~~

Both implementations accept the same normalized command. Adapters translate HTTP/event payloads into domain commands. Domain logic should not read environment variables directly or call payment providers during calculation.

During shadowing, invoke the candidate implementation with isolated dependency adapters. During canary, the router picks one implementation as the primary system for that request.

## 12. Java: Publishing Shadow Envelopes to a Queue

An illustrative example of application-level mirroring:

~~~java
public final class OrderController {
    private final LegacyOrderService legacy;
    private final ShadowPublisher shadowPublisher;

    public OrderController(
            LegacyOrderService legacy,
            ShadowPublisher shadowPublisher) {
        this.legacy = legacy;
        this.shadowPublisher = shadowPublisher;
    }

    public OrderResponse create(OrderRequest request) {
        OrderResponse primary = legacy.create(request);

        ShadowEnvelope envelope =
                ShadowEnvelope.from(request, primary.getRequestId());

        try {
            shadowPublisher.publishWithShortTimeout(envelope);
        } catch (RuntimeException error) {
            // Do not break the primary response simply because mirroring failed.
            Metrics.increment("shadow.publish.failure");
        }

        return primary;
    }
}
~~~

This only illustrates the flow; synchronous publishing still adds latency. In production, consider an outbox or gateway/proxy fan-out. If business requirements demand guaranteed capture of shadow events, use a transactional outbox rather than swallowing publish errors. The shadow path can be best-effort when the goal is comparison and it must never affect primary requests.

Do not embed the primary response in the envelope if it contains PII or secrets. Include only fields needed for diffing and redact before publishing.

## 13. Java: Processing Shadow Events Idempotently

Shadow consumers may receive the same envelope again due to queue retries. Use experiment ID combined with correlation ID as the processing key, but never share an idempotency key with production business flows if doing so could block real traffic.

~~~java
public final class ShadowOrderHandler
        implements RequestHandler<ShadowEnvelope, ShadowResult> {

    private final ShadowStore store = ShadowStore.create();
    private final OrderCalculator candidate =
            ServerlessOrderCalculator.create();

    @Override
    public ShadowResult handleRequest(
            ShadowEnvelope envelope,
            Context context) {

        String key = envelope.experimentId()
                + ":" + envelope.correlationId();

        ShadowResult existing = store.findCompleted(key);
        if (existing != null) {
            return existing;
        }

        OrderCommand command =
                OrderCommand.from(envelope.payload());

        OrderQuote quote = candidate.calculate(command);

        ShadowResult result =
                ShadowResult.completed(key, quote);

        store.saveIfAbsent(result);
        return result;
    }
}
~~~

This is pseudocode; the store needs atomic conditional writes or transactions. If two concurrent invocations receive the same envelope, only one result is recorded as canonical. The candidate must not invoke command handlers that create real orders.

If the same input is replayed in another experiment, use a new experiment ID to store new results while keeping the original correlation ID to compare across runs.

## 14. Normalizing Results Before Comparison

Byte-for-byte JSON comparison produces frequent false positives. Two systems can return identical business outcomes while differing in field order, timestamps, generated IDs, or numeric formatting.

Normalize before diffing:

- Sort collections when order is not semantically meaningful.
- Normalize timezones to UTC.
- Normalize currency and decimal scale.
- Strip or mask independently generated request IDs.
- Compare timestamps within a defined tolerance if business rules allow.
- Normalize nulls, missing fields, and defaults per contract.
- Normalize text encoding and casing when semantics are case-insensitive.
- Keep meaningful fields untouched, such as status, amounts, taxes, inventory, and permission decisions.

Never strip fields just to make diffs pass. Every normalization rule must be justified and reviewed. If a timestamp is business data, do not ignore it merely because the two systems generated slightly different timestamps.

## 15. Classifying Diffs by Severity

Not all discrepancies carry the same risk.

| Severity | Examples | Action |
|---|---|---|
| Critical | Wrong monetary amount, wrong access control, duplicate payment, lost order | Block cutover; investigate immediately |
| High | Wrong business status, missing record, wrong inventory | Block traffic expansion |
| Medium | Field mismatch not affecting core decision yet breaking contract | Fix or get formal exception approval |
| Low | Confirmed benign timestamp, ordering, or formatting differences | Document normalization rule |
| Expected | Fields intentionally designed differently between versions | Document mapping and verify consumer compatibility |

Assign severity by domain. In payments, a 1-unit currency difference can be critical. In recommendation lists, item ordering might be medium or low depending on contracts.

Do not rely on a single aggregate diff rate. A tiny rate concentrated on high-value transactions is far more dangerous than widespread formatting diffs.

## 16. Comparing Data and Business Invariants

Beyond response diffs, check business invariants:

- Total new orders created per day.
- Total monetary amounts by currency.
- Counts of authorized/captured/refunded payments.
- Counts of inventory reservations and releases.
- Final workflow states.
- Counts of received, processed, retried, and DLQ events.
- Foreign-key or cross-aggregate references.
- Zero duplicate business keys where uniqueness is required.

Compare within the same cohort and time window. Eventually consistent data may not sync immediately; define an explicit reconciliation window and distinguish normal lag from lost records.

When data contains PII, diff using pseudonymous identifiers or securely managed salted hashes. Never expose personal data on diff dashboards or logs.

## 17. Handling Data When Legacy and New Systems Have Different Schemas

During migration, legacy and new schemas may differ. Define explicit mappings for:

- Field renames.
- Field splits or merges.
- Type conversions.
- Default values.
- Enum mappings.
- Precision and rounding.
- Timezone and timestamp semantics.
- Soft deletes and tombstones.
- Versioning and backward compatibility.

Use expand-and-contract whenever possible:

1. Add new fields or schemas in a backward-compatible way.
2. Deploy code capable of reading both old and new shapes.
3. Backfill historical data.
4. Begin writing or mirroring data per the chosen strategy.
5. Switch readers to the new schema.
6. Monitor and reconcile.
7. Remove old fields only after no consumers use them.

Never deploy breaking schema changes before all relevant producers and consumers are ready.

## 18. Dual-Write and Consistency

Dual-writes may appear necessary when both legacy and new systems must receive updates during transition. Yet if the application writes database A successfully and database B fails, state diverges.

Common strategies:

**Transactional outbox:** write business changes and an outbox event in the same source database transaction. A publisher reads the outbox and dispatches events to the target system. This prevents committing database state while losing events.

**Change Data Capture (CDC):** read the source database transaction log to replicate changes to the target. Monitor replication lag, schema changes, and checkpoints.

**Single writer:** only one system holds write authority at any time. The other system receives data via replication or events. This minimizes conflicts and simplifies rollback.

**Reconciliation:** periodically compare source and target, detecting and repairing discrepancies by business key.

Never run two independent writers against the same aggregate without conflict resolution. Simple retries cannot resolve cases where one side committed and the other did not.

## 19. Keeping a Single Source of Truth in Each Stage

In every migration stage, explicitly designate which system is authoritative.

| Stage | Source of Truth | What Candidate Is Allowed to Do |
|---|---|---|
| Offline replay | Legacy production data | Read snapshot and write to test datastore |
| Shadow | Legacy | Process copies, write comparison outputs |
| Canary read path | Legacy or target per defined domain | Candidate serves a read cohort |
| Canary write path | One designated writer | Only that writer commits business writes |
| Cutover | Target | Legacy read-only or receiving CDC for rollback |
| Decommission | Target | Legacy shut down after retention/rollback window |

When transferring write authority, enforce a fencing step so the legacy system stops writing past the cutover timestamp. Use routing gates, feature flags, database permissions, or lease/epoch tokens. Changing DNS alone is not enough to prevent in-flight legacy requests from continuing to write.

## 20. Designing Feature Flags and Routing

The router should choose which system handles a request based on flags or stable cohorts. Hash tenant/user/business keys so a customer does not bounce back and forth between legacy and target on consecutive requests.

Logic example:

~~~java
public OrderResponse route(
        OrderRequest request,
        RoutingConfig config) {

    if (config.isTargetEnabledFor(request.tenantId())) {
        return serverlessOrderService.create(request);
    }

    return legacyOrderService.create(request);
}
~~~

Shadow mode should be independent of primary routing:

- Primary target: system returning responses to users.
- Shadow target: system receiving copies for comparison.
- Write authority: sole system permitted to commit side effects.
- Cohort: group of requests selected to hit the candidate.

Do not use a single boolean like `NEW_SYSTEM=true` to control routing, shadowing, data writers, and external side effects simultaneously. Separating flags makes rollback precise and prevents accidentally enabling write authority.

## 21. Evaluating Latency and Throughput

When comparing legacy against serverless, measure the same request types under comparable load:

- p50, p95, p99, and p99.9 latency.
- Throughput in requests/sec or events/sec.
- Error rates broken down by status and exception type.
- Queue age and processing delay.
- Cold start / Init Duration where applicable.
- Throttles and concurrency.
- Dependency latency.
- Timeouts and retry rates.

A shadow candidate does not return responses to users, so its latency is not end-to-end user-perceived latency. Measure candidate processing latency separately from overhead added by the mirror publisher. In canary, measure true end-to-end latency of requests served by the candidate.

Do not compare legacy p99 during peak hour against candidate p99 during quiet hours. Use matching cohorts, time windows, or replay datasets so comparisons stay valid.

## 22. Evaluating Reliability and Operations

A candidate with low latency that retries constantly or fills a DLQ cannot be considered better.

Monitor:

| Category | Metrics |
|---|---|
| Invocation | Invocations, Errors, Throttles, Duration |
| Queue | Visible messages, in-flight, age of oldest message |
| Retry | Retry count, redrive count, DLQ messages |
| Runtime | Init duration, memory usage, timeouts, out-of-memory |
| Dependency | Connection failures, 429/5xx, timeouts, pool saturation |
| Data | Missing, duplicate, stale reads, reconciliation mismatches |
| Operations | Deployment failures, rollback time, alert count |
| Security | Access denied, secret access, unexpected egress |

Use the same trace/correlation ID to link legacy requests, shadow events, candidate invocations, and comparison records. Avoid placing customer IDs directly in metric dimensions due to high cardinality and data exposure risks.

## 23. Evaluating Cost on the Same Business Unit

Cost must cover the entire pipeline, not just Lambda duration:

- Legacy compute and licenses still maintained.
- Lambda requests and GB-seconds.
- API Gateway, queues, streams, and event pollers.
- Logs, metrics, traces, and retention.
- Databases, caches, NAT, storage, and data transfer.
- Provisioned Concurrency or minimum instances.
- Extra requests and compute from shadow traffic.
- Dual-write, CDC, reconciliation, and replay.
- Operational overhead while both systems coexist.

A useful metric:

~~~text
Cost per successful business operation =
Total migration-period cost / Successful business operations
~~~

Separate temporary migration costs from steady-state costs. Shadow traffic intentionally raises costs during validation to reduce cutover risk. Bound the duration and mirror percentage so experiments do not run indefinitely.

## 24. Designing Experiments and Acceptance Gates

Before running, document:

1. Business objective.
2. Selected endpoints/events.
3. Cohort and sampling rate.
4. Source of truth.
5. Candidate side-effect policy.
6. Dataset or payloads used.
7. Metrics and comparison rules.
8. Error budgets and stop conditions.
9. Duration and accountable owners.
10. Criteria to ramp traffic, roll back, and conclude.

Example acceptance gate:

| Criterion | Illustrative Threshold |
|---|---|
| Critical business diffs | 0 |
| Duplicate side effects | 0 |
| Missing business records | 0 in reconciled cohort |
| p95 latency | Within agreed SLO |
| p99 latency | Within allowable increase over baseline |
| Error rate | Within error budget |
| Queue age | Below processing SLA |
| DLQ | Zero unclassified failures |
| Data reconciliation | Zero remaining critical mismatches |
| Cost per success | Within target budget |

Thresholds must be approved by business and operations owners. Do not treat illustrative numbers as a universal policy for every workload.

## 25. Allowing Sufficient Duration and Sample Size

A few dozen requests are not enough to conclude the new system is stable. Ensure coverage across:

- Peak and off-peak traffic.
- Small, medium, and large payloads.
- Different tenant types or customer tiers.
- Error paths and retry paths.
- Late, duplicate, and out-of-order events where applicable.
- Currencies, locales, and timezones.
- Expected production batch sizes and concurrency.

For rare errors, you need enough samples to observe them. Seeing zero errors in a tiny sample does not prove a zero error probability. Combine sanitized real traffic, synthetic edge cases, and controlled replay.

Run experiments long enough to cover business cycles such as end-of-day runs, batch settlements, reporting, or quota resets. Seasonal workloads may require longer canary windows or dedicated load tests.

## 26. Canary Cutover After Shadow

Once shadow passes acceptance gates, begin canary. Canary means a fraction of real requests is served by the candidate, which is responsible for returning responses and committing business state.

An illustrative traffic ramp:

~~~text
Stage 0: 0% target, 100% legacy
Stage 1: 1% target, 99% legacy
Stage 2: 5% target, 95% legacy
Stage 3: 10% target, 90% legacy
Stage 4: 25% target, 75% legacy
Stage 5: 50% target, 50% legacy
Stage 6: 100% target
~~~

This is an illustrative schedule. Hold each stage long enough to observe latency, errors, and business outcomes. For write paths, cohorts must remain stable with an explicit source of truth. Avoid routing a user to legacy on one request and to target on the next if the two systems do not share compatible state.

If the candidate encounters errors, halt traffic ramping and return the cohort to legacy per the runbook. Do not auto-rollback on a noisy metric over a tiny window; use agreed thresholds, durations, and business severity rules.

## 27. Rollback and Backward Compatibility

Traffic rollback is only easy if data and contracts remain compatible with the legacy system.

Before cutover, verify:

- Legacy can still read data written by the target.
- The new schema is backward compatible or has reverse mappings.
- Emitted events do not break legacy consumers.
- Queues/checkpoints can resume from a safe position.
- The target does not trigger side effects unknown to legacy.
- Secrets, IAM, and networking for legacy remain intact throughout the rollback window.
- Writers can be fenced and write authority returned to one place.

If the target writes an incompatible new schema, routing traffic back to legacy can break the application even when code deployment rollback succeeds. This is why expand-and-contract and single-writer discipline matter.

Do not delete legacy databases, queues, or IAM roles immediately after cutover. Wait until the rollback window ends and reconciliation completes before decommissioning.

## 28. When Is Shadow Traffic Unsuitable?

Shadow traffic may be unsuitable or require special design when:

- Requests contain sensitive data that cannot legally be copied.
- Operations produce side effects that cannot be sandboxed or isolated.
- The candidate cannot process the same schemas/payloads as legacy.
- Requests are real-time and mirroring adds unacceptable load.
- The system has tight rate limits or high per-request costs.
- Data mutates constantly so comparison outputs diverge from the original snapshot.
- The candidate depends on state created by prior requests.
- Requests carry nonces, one-time tokens, or non-replayable operations.

In these cases, use synthetic tests, sanitized offline replay, contract tests, deterministic simulation, or shadow only a read-only calculation slice.

## 29. Common Pitfalls in Parallel Runs

| Pitfall | Consequence | Fix |
|---|---|---|
| Running shadow while still sending real emails/payments | Side effects execute twice | Fake adapters, sandboxes, and egress policies |
| Mirroring 100% from day one | Sudden load and cost spikes | Sampling and gradual ramp |
| Raw JSON comparison | False positives from timestamps/IDs/ordering | Reviewed canonicalization |
| Ignoring differing fields | Masks business bugs | Domain-driven severity and invariants |
| Sharing a single idempotency store | Shadow blocks primary production flows | Dedicated namespace per experiment |
| Fire-and-forget background threads in Lambda | Copies may never be sent | Queues/outbox/proxy mirroring |
| Dual-write without reconciliation | Two datastores drift apart | Single writer, outbox/CDC, and repair |
| Constantly shifting canary cohorts | Inconsistent comparisons | Stable cohort hashing |
| Measuring only candidate latency in shadow | Confused with real user latency | Measure shadow processing and canary E2E separately |
| Rolling back after breaking schema changes | Legacy cannot read new data | Expand-and-contract and backward compatibility |
| No rollback window | No path back | Retain legacy, data, and routing for a set window |

## 30. Runbook for Shadow Experiments

A minimal runbook should cover:

**Before running**

- Define owner, experiment ID, and schedule.
- Confirm source of truth and side-effect policies.
- Verify candidate roles, network egress, and datastores.
- Choose sampling rate and maximum concurrency.
- Enable dashboards, alarms, and log correlation.
- Verify queue retention, DLQ, and mirror kill switch.

**During the run**

- Monitor legacy latency/error rates.
- Monitor mirror publish successes/drops.
- Monitor candidate invocations, errors, and queue age.
- Inspect diffs by severity.
- Verify side-effect and data isolation.
- Abort experiment if stop conditions trigger.

**After the run**

- Stop mirroring and drain queues per policy.
- Reconcile eligible, mirrored, processed, and compared counts.
- Summarize diffs and business invariants.
- Record costs and latency.
- Delete or archive test data per retention policy.
- Decide to fix, rerun, canary, or cancel migration.

## 31. Runbook for Cutover and Rollback

**Cutover**

1. Confirm all acceptance gates pass.
2. Confirm target capacity, quotas, and downstream readiness.
3. Confirm writer authority and fencing mechanisms.
4. Confirm schema compatibility.
5. Select the initial canary cohort.
6. Shift routing at the approved percentage.
7. Monitor SLOs, data consistency, and business success.
8. Increase traffic across gates.
9. Move to 100% once all stages stabilize.
10. Keep legacy ready through the rollback window.

**Rollback**

1. Halt traffic ramping immediately.
2. Route the cohort back to legacy.
3. Fence the target writer if needed.
4. Check in-flight requests and messages.
5. Reconcile transactions committed at the target.
6. Replay incomplete events using original idempotency keys.
7. Verify schema and data compatibility.
8. Resume target traffic only after fixing the root cause and re-passing gates.

Rollback does not necessarily mean deleting target data. You usually need to retain target data for investigation and reconciliation.

## 32. Migration Evaluation Report

A report should include:

- Scope of endpoints/events and cohorts.
- Duration, sampling rate, and eligible request counts.
- Counts of mirrored, processed, compared, and dropped requests.
- Diff rates by severity.
- Business invariants and reconciliation results.
- p50/p95/p99 latency and throughput.
- Errors, retries, throttles, queue age, and DLQ counts.
- Cost per successful business operation.
- Security/privacy review.
- Acceptance gate outcomes.
- Decision: continue shadow, fix, canary, roll back, or decommission.
- Action items, owners, and deadlines.

A good report distinguishes observed data from assumptions. If samples are insufficient or a traffic segment was not covered, document the limitation rather than claiming full system equivalence.

## 33. Production Checklist

**Experiment Design**

1. Are baselines and acceptance gates defined?
2. Is the source of truth defined for each stage?
3. Are shadow and canary clearly distinguished?
4. Is sampling representative and covering edge cases?
5. Are correlation IDs and experiment IDs in place?

**Business and Data Protection**

6. Does the candidate avoid creating production side effects?
7. Do payment/email/SMS integrations use sandboxes or sinks?
8. Are datastores, queues, and IAM isolated?
9. Are payloads redacted and retention bounded?
10. Are idempotency keys kept stable during replay?
11. Does dual-write have outbox/CDC/reconciliation?
12. Is single-writer or fencing enforced at cutover?

**Evaluation**

13. Are responses canonicalized in a controlled manner?
14. Are critical business diffs zero per policy?
15. Are business invariants and data reconciled?
16. Are p50/p95/p99, errors, retries, and queue age measured?
17. Is cost per successful operation calculated?
18. Does the sample cover peaks and business cycles?

**Cutover and Rollback**

19. Is the canary cohort stable?
20. Does the target have sufficient quotas, concurrency, and downstream capacity?
21. Are schemas backward compatible?
22. Are cutover/rollback runbooks ready?
23. Does legacy remain ready throughout the rollback window?
24. Is reconciliation completed before decommissioning?

## References

- [AWS Prescriptive Guidance: Strangler fig pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/strangler-fig.html)
- [AWS Database Migration Service: Change data capture](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Task.CDC.html)
- [AWS Lambda: Using Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [Amazon API Gateway: Canary release deployment](https://docs.aws.amazon.com/apigateway/latest/developerguide/canary-release.html)
- [OpenTelemetry: Distributed traces](https://opentelemetry.io/docs/concepts/signals/traces/)
- [AWS Well-Architected: Operational excellence](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/welcome.html)

## Conclusion

Parallel runs and shadow traffic validate a serverless candidate against realistic workloads before transferring serving authority. Shadow keeps the legacy system as primary and sends copies to the candidate; canary shifts a portion of real requests to the new system. Dual-write is a separate consistency problem requiring single-writer discipline, outbox/CDC, or reconciliation.

For Java serverless, separate domain logic from adapters and side effects, use queues/outboxes instead of unguaranteed background threads, isolate databases and external services, keep idempotency keys stable, and normalize results before diffing. Evaluate correctness, data invariants, latency, reliability, and cost per successful operation. Increase traffic only when acceptance gates pass, schemas stay compatible, and rollback has been rehearsed.
