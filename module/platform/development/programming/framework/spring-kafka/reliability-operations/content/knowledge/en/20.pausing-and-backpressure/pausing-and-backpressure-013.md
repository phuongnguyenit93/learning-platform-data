# Safe Resume After an Incident

In a Spring Kafka system, **pause** temporarily stops taking in additional records while the application or a dependency experiences an incident. Once the root cause of the incident is resolved, **resume** allows the container or individual partitions to continue consuming data. However, resuming is not merely calling an API to "run again": backlog may have accumulated, older records may be nearing retention expiry, downstream may have just recovered without yet tolerating peak load, and some events may have already produced side effects before failures surfaced.

**Safe resume after an incident** is a controlled recovery process: verify readiness conditions, understand actual pause states, restore consumption in measured load increments, monitor impact, and have a plan to pause again if system health degrades. The goal is not driving consumer lag to 0 as fast as possible at all costs, but **bringing data back into the processing pipeline without causing a second incident, skipping records, or generating uncontrolled duplicate business effects**.

This lesson belongs to the **Pause and Backpressure** chapter of Spring Kafka Reliability Operations. Examples use Spring Kafka listener containers, consumer groups, topic-partitions, and Kubernetes environments; core rules also apply to VM or bare-metal deployments.

## 1. Typical scenario

Suppose the `payment-worker` service reads the `payment-requests` topic, partitions 0–5. When the payment gateway begins returning timeouts, the application proactively pauses consumption to avoid sending more requests to an overloaded dependency.

```text
T0 — Normal

payment-requests (6 partitions)
       |
       v
payment-worker consumers
       |
       v
Payment gateway — healthy

T1 — Incident

Payment gateway timeouts rise
       |
       v
Pause listener / selected partitions
       |
       v
Kafka continues retaining new records
       |
       v
Consumer lag accumulates

T2 — Dependency fixed

Do not resume all immediately
       |
       v
Verify readiness + offsets + in-flight state
       |
       v
Resume in partition batches
       |
       v
Monitor retries, gateway latency, lag, DLT
       |
       v
Expand to normal load
```

If all six partitions resume simultaneously right as the gateway recovers, the service can trigger a surge of requests that makes the gateway time out again. Waiting too long risks letting older records pass retention. Therefore, recovery plans must balance **catch-up speed**, **dependency health**, **processing order**, and **the ability to pause again if a step fails**.

## 2. Understanding pause/resume accurately in Spring Kafka

Spring Kafka supports pause/resume at the container and partition levels via `MessageListenerContainer`.

```java
// Pause/resume the entire container using the Spring Kafka API.
container.pause();
container.resume();

// Pause/reopen a specific topic-partition.
TopicPartition tp = new TopicPartition("payment-requests", 2);
container.pausePartition(tp);
container.resumePartition(tp);
```

| Action | Primary effect | Does not automatically perform |
|---|---|---|
| `pause()` | Requests the container to stop consuming more from managed partitions. | Does not stop JVM, does not commit offsets, does not cancel running work. |
| `resume()` | Clears the container-level pause request, letting the container resume polling records. | Does not fix dependencies, does not alter offsets, does not solve poison records. |
| `pausePartition(tp)` | Requests pausing a single partition. | Does not revoke assignments, does not move the partition to another member. |
| `resumePartition(tp)` | Clears the pause request for one partition. | Does not resume other partitions or an active container-wide pause command. |
| `stop()` | Stops the container lifecycle per configured policy. | Not equivalent to pause; may cause the consumer to leave the group. |

**Resume is asynchronous in terms of taking effect.** The container normally applies the change at an appropriate `poll()` boundary; the Java method returning does not guarantee records are already being fetched again at that instant.

Two distinct states must be tracked:

```java
boolean requested = container.isPauseRequested();
boolean applied = container.isContainerPaused();

TopicPartition tp = new TopicPartition("payment-requests", 2);
boolean partitionRequested =
        container.isPartitionPauseRequested(tp);
boolean partitionPaused =
        container.isPartitionPaused(tp);
```

`isPauseRequested()` reflects container-wide pause requests; `isContainerPaused()` reflects the container's applied state per Spring Kafka's API. For partitions, the `isPartitionPauseRequested` and `isPartitionPaused` pair distinguishes intent from actual state.

During incident handling, report accurately:

- **Resume requested:** a request to reopen consumption was sent.
- **Resume applied:** the container is no longer in the paused state for the target scope.
- **Consumption healthy:** records are actually processing and offsets are advancing with an acceptable error rate.

These three states **are not equivalent**. Never announce "the system has recovered" merely because a `resume()` call returned normally.

## 3. What pause does not guarantee

A Kafka consumer still owns its partitions while paused. Group membership is normally preserved because the container keeps calling `poll()`, rather than leaving the thread idle indefinitely. While paused:

1. Producers can continue writing new records to Kafka.
2. Consumer lag on paused partitions can grow.
3. Records already fetched from the prior poll may still be processing.
4. Already-started transactions or retries may still be finishing or aborting.
5. Offsets do not commit automatically just from pause/resume.
6. The consumer group can still rebalance on instance restarts, poll timeouts, or membership changes.

Upon resume, the consumer continues from its **actual read position and committed offsets**, rather than rewinding to when the incident began. Some processed-but-uncommitted records may be redelivered after a crash; the application must tolerate at-least-once delivery and business idempotency.

Example:

```text
Before incident:
  committed offset = 100
  log end offset   = 120

During incident:
  pause applied
  producer sends 80 more records

After incident:
  committed offset = 100  (assuming no additional commits)
  log end offset   = 200
  lag              = 100

resume() -> consumer can fetch unprocessed records
            from the valid position per consumer state
```

Never call `seek()` to the log end offset to "drop the backlog" if the business requires processing queued records. Seeking and offset resets risk data loss and require explicit decisions.

## 4. Prerequisites before resuming

An incident marked "resolved" in a ticketing system **is not enough**. Establish **readiness gates** independent of the technical control step:

| Condition group | Questions to answer | Expected evidence |
|---|---|---|
| Root cause | Was the incident cause fixed, or did errors merely dip temporarily? | Deploy/config fix, test results, dependency health. |
| Dependency capacity | Can downstream absorb rising traffic gradually? | Error rate, p95/p99 latency, pool saturation, quotas. |
| Consumer health | Are containers, pods, consumer group, and assignments stable? | Pods ready, no crash loops, lag/assignments observed. |
| Offsets & retention | Is the backlog still inside Kafka, or at risk of retention expiry? | Committed offsets, log start/end offsets, record age. |
| In-flight work | Are transactions, callbacks, or jobs fetched before pause still running? | In-flight counters, transaction states, worker queue depth. |
| Data correctness | Are there poison records, schema mismatches, or data needing fixes before replay? | Sample inspection and DLT review results. |
| Idempotency | Could redelivered records cause duplicate side effects? | Unique constraints, event IDs, inbox, API idempotency keys. |
| Rollback | Can we pause again quickly if metrics degrade? | Clear owner, operational permissions, verified API/feature flags. |

Not every system shares identical metrics or thresholds. Financial transactions may strictly mandate idempotency and reconciliation, whereas non-critical telemetry may prioritize throughput recovery. Derive thresholds from SLOs, dependency capacity, and data retention requirements.

## 5. Restore the dependency first, then reopen Kafka

If the pause reason was an exhausted database connection pool or HTTP gateway timeouts, first verify **the target service can handle real load**. A health check returning HTTP 200 proves only that the endpoint responds, not that the service can drain a backlog.

Combine:

- Readiness/liveness confirming service-to-dependency connectivity.
- A canary request or low-traffic test transaction completing cleanly.
- Error rates and latencies remaining steady over an observation window.
- Connection pools, thread pools, queue depth, and rate limits/quotas holding headroom.
- No incomplete deployment or mismatched config still rolling across instances.
- DLT/retries from the prior incident triaged, avoiding reckless replay alongside the main backlog.

An effective operational practice is **keeping rate limiters/circuit breakers at downstream callsites** even after resuming. Pause only controls the influx of new records to the listener; it cannot precisely bound HTTP calls or SQL queries per second if listeners process multiple records concurrently.

## 6. Inspecting consumer groups and partition ownership

Before resuming, verify which consumer owns which partitions. For a multi-partition Kafka topic, assignments may have shifted during the incident due to pod restarts or rolling updates.

Example inspection commands:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group payment-worker

kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group payment-worker \
  --members --verbose
```

These commands inspect group members, partition assignments, committed offsets, log-end offsets, and lag depending on your Kafka CLI version. However, **standard Kafka CLI does not know whether a Spring container paused a partition**. Pause state must be read from Spring Kafka container APIs, application events, or application-exposed metrics.

In Kubernetes:

```bash
kubectl get pods -l app=payment-worker -o wide
kubectl logs -l app=payment-worker --since=15m --prefix=true
```

Inspect logs for assignments, rebalances, pause/resume, consumer errors, transaction aborts, producer fencing, and dependency errors. If a partition moved to a new pod, calling resume on the **old pod** will not change actual consumption.

With `@KafkaListener(concurrency = "4")`, Spring Kafka can create multiple child containers inside one JVM. Do not assume "partition N always belongs to child N"; partition ownership depends on the assignor, member count, and rebalances.

## 7. Checking lag, offsets, and retention limits

Lag helps estimate catch-up work after resume, though it does not fully reflect per-record processing difficulty.

```text
Topic payment-requests, partition 2:

committed offset = 2500
log end offset   = 12500
lag              = 10000 records
```

If producers continue writing 200 records/second and the post-resume consumer processes 500 records/second on that partition, the theoretical backlog drain rate is:

```text
Net catch-up = 500 - 200 = 300 records/second
Backlog      = 10,000 records
Estimated time ≈ 10,000 / 300 ≈ 33.3 seconds
```

This is an **illustrative** calculation, not a real SLA: records vary in cost, retries add load, and throughput fluctuates. If processing speed equals or falls below producer rate, lag will not shrink even after the consumer resumes.

Pay close attention to **log start offset** and retention policies. If a partition stayed paused longer than retention or underwent log compaction, older records may no longer exist. Never treat `auto.offset.reset=earliest` as a way to recover deleted data: `earliest` picks the earliest offset **still retained**, not records purged past retention.

Before resuming, confirm committed offsets remain valid. If offsets are already gone from the log, the incident becomes a **source-data recovery problem** or a business decision to accept data loss—not a simple resume operation.

## 8. A resume control service using Spring Kafka

Assign a fixed `id` to the listener to access its container via `KafkaListenerEndpointRegistry`:

```java
@Component
public class PaymentRequestListener {

    @KafkaListener(
        id = "payment-requests-listener",
        topics = "payment-requests",
        groupId = "payment-worker",
        concurrency = "3"
    )
    public void onRecord(ConsumerRecord<String, String> record) {
        paymentService.process(record.key(), record.value());
    }
}
```

State management service:

```java
@Service
public class PaymentListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public PaymentListenerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void requestResumeAll() {
        container().resume();
    }

    public void requestResumePartition(int partition) {
        TopicPartition tp =
                new TopicPartition("payment-requests", partition);
        container().resumePartition(tp);
    }

    public boolean isResumeApplied(int partition) {
        TopicPartition tp =
                new TopicPartition("payment-requests", partition);
        MessageListenerContainer c = container();

        return !c.isPartitionPauseRequested(tp)
                && !c.isPartitionPaused(tp)
                && !c.isPauseRequested();
    }

    public void requestPausePartition(int partition) {
        TopicPartition tp =
                new TopicPartition("payment-requests", partition);
        container().pausePartition(tp);
    }

    private MessageListenerContainer container() {
        MessageListenerContainer c =
                registry.getListenerContainer("payment-requests-listener");
        if (c == null) {
            throw new IllegalStateException("Listener not registered");
        }
        return c;
    }
}
```

Required imports:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
```

**Important limitation of this example:** `isResumeApplied` reads only local container pause flags; it **does not prove the partition is assigned, the container is running, or offsets are actually advancing**. In multi-pod systems, check the right owner and pair with consumption metrics. If a container-wide pause request remains or the container stopped, calling `resumePartition` alone may not deliver records.

Production systems should separate two endpoints/operations: **setting desired state** (request) and **verifying applied state** (observation), rather than synchronously returning "resumed successfully" right after calling the method.

## 9. Multi-pod recovery: desired state as the source of truth

In multi-replica deployments, `KafkaListenerEndpointRegistry` sees only containers inside the **current JVM**. A `resume()` command on pod A does not resume pod B, and partitions can shift owners during rebalances.

For system-wide incident pauses, store **desired state** in an accessible control plane or database:

```text
Control plane
  incident_id = INC-4821
  generation  = 12
  desired_paused_partitions = {payment-requests-2, payment-requests-4}
                 |
                 v
         Reconciler on each pod
                 |
       +---------+---------+
       |                   |
       v                   v
     Pod A               Pod B
  current assignment  current assignment
       |                   |
       v                   v
  Apply pause/resume per actual owner
```

When an operator reopens `payment-requests-2`, the control plane updates desired state and increments generation. Instances observe the new generation, check their assignments, and apply pause/resume accordingly. If a partition moves to a new pod, the new owner must also reconcile.

This design avoids two risks:

- **Losing pauses on restart:** newly started pods do not remember pauses stored only in an old pod's RAM.
- **Resuming the wrong owner:** commands hitting an instance that no longer owns that partition.

Ensure permissions to mutate desired state are restricted, maintain an audit trail (actor, incident ID, timestamp, reason), and prevent an **old resume** command from overwriting a **new pause** from another incident. Use generations/versions, compare-and-set, or leases to prevent races.

If the requirement is "process zero additional records before pause policy is confirmed," you may also need a business gate inside the listener and startup/assignment guards. Relying solely on a reconciler eventually calling the pause API after assignment occurs cannot strictly prevent every record from slipping through.

## 10. Resuming in batches to avoid thundering herds

When backlog is huge, resuming every partition at once can trigger a **traffic spike** exceeding dependency capacity. The safer path is phased reopening:

```text
Phase A: one partition / one canary instance
                    |
                    v
      Measure error rate, latency, throughput
                    |
             Readiness gate met?
               /          \
              No           Yes
              |             |
              v             v
           Re-pause    Phase B: add partitions
                              |
                              v
                       Monitor and ramp up
                              |
                              v
                      Open all once stable
```

For example, a runbook might open one partition during canary, then two more partitions after an observation window, and finally open the rest. **Partition counts and observation windows are operational parameters** with no single default formula for every workload.

At the dependency layer, also tune:

- Maximum concurrent HTTP/DB calls or semaphores.
- Per-tenant/partner rate limits when partitions mix multiple keys.
- Consumer concurrency and `max.poll.records` if batch processing size truly needs adjustment.
- Timeouts and retry/backoff to avoid amplifying load on a freshly recovered dependency.
- Circuit breakers and bulkheads so one failure class does not stall the whole system.

Pause/resume does not provide fine-grained rate limiting by itself. A single partition can hold millions of records, and a fast listener can still fire heavy traffic the moment it resumes. Enforce explicit limits at the dependency callsite.

## 11. Stop conditions and automatic re-pausing

Before resuming, define **stop conditions** and who is authorized to re-trigger pause. Example:

| Signal | Condition to monitor | Action when threshold breached |
|---|---|---|
| Dependency error rate | Sustained climb past configured tolerance. | Pause the newly opened batch, keep other partitions halted. |
| p95/p99 latency | Sharp spike once backlog begins draining. | Throttle downstream calls or pause partitions back down. |
| Connection pool/queue depth | Approaching saturation. | Cap concurrency, stop ramping load. |
| Listener retries/exceptions | Abnormal surge in record failures. | Inspect data, classifiers, and DLT; halt further expansion. |
| DLT ingress | Many records routed to DLT. | Verify correctness, consider halting resume. |
| Transaction abort/commit errors | Transactional listener failing commits consistently. | Pause, investigate coordinator/fencing/timeouts. |
| Consumer lag | Not dropping after an adequate observation window. | Inspect real throughput and dependency; avoid blind scaling. |

Thresholds must include **hysteresis** to avoid rapid pause/resume oscillation around a single value. For example, set a high-latency pause threshold and a lower resume threshold, requiring stability over a time window. Define these values from real SLOs rather than hard-coding identical numbers across all services.

The system can auto-pause again when degradation is clear, yet should cap automatic retry cycles, alert operators, and escalate to manual intervention if failures keep repeating.

## 12. Handling poison records and schema errors before reopening

Not every incident stems from dependency overload. If a record triggers `DeserializationException`, `ValidationException`, or a permanent business error, resuming can send the consumer straight back to the same record and fail repeatedly.

### Errors before entering the listener

Deserialization happens inside Kafka consumer `poll()`. If payloads fail wire format or schemas are missing, `@KafkaListener` may never be invoked. In Spring Kafka, `ErrorHandlingDeserializer` lets the container route deserialization errors into the error-handling branch instead of letting the consumer get stuck in `poll()`.

### Errors inside the listener

`DefaultErrorHandler` can retry per `BackOff` and hand the record to a recoverer once exhausted. With non-blocking retries, records may already have moved to retry topics or a DLT; resuming the main topic does not automatically resume the entire retry/DLT workflow.

Before resuming, decide:

1. Has the data been fixed or can updated code handle the old record?
2. How many times should transient errors retry before recovery?
3. Are permanent errors routed to the DLT with source metadata?
4. Does the DLT producer have appropriate serializers/ACLs/topics, including `byte[]` for deserialization failures?
5. Is there a controlled replay runbook to prevent poison-record loops?

**Never use resume as an infinite retry loop.** If a permanent bug remains unresolved, fix the contract, classify exceptions, or route records through a controlled recovery workflow.

## 13. Idempotency and side effects on record redelivery

A consumer may finish calling the payment gateway yet crash before committing its offset. Upon resume or restart, the same record can be redelivered and call the gateway again.

```text
Kafka record OrderPaymentRequested
             |
             v
Payment gateway returns SUCCESS
             |
             X process crashes before offset commit
             |
             v
Consumer re-reads record during recovery
             |
             v
Risk of double charge if not idempotent
```

The fix lies not in pause/resume, but in **idempotency**:

- Every event carries a stable ID across retries/replays.
- When calling external APIs, pass an idempotency key if supported by the partner.
- Record processing markers in the database with a unique constraint inside the same transaction as DB side effects.
- Resolve "API called but confirmation lost" states via reconciliation instead of blindly charging again.
- For transactional Kafka listeners, remember Kafka transactions do not span external payment providers or external databases.

When an incident involves non-repeatable side effects, readiness gates must include reconciliation results for in-flight records. If you cannot tell which records already paid, **do not fully resume yet**.

## 14. Application events and status logs

Spring Kafka provides application events for consumer or partition pause/resume. Depending on version, use `ConsumerPausedEvent`, `ConsumerResumedEvent`, or `ConsumerPartitionPausedEvent`, `ConsumerPartitionResumedEvent`.

Logging example:

```java
@Component
public class KafkaPauseResumeEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaPauseResumeEvents.class);

    @EventListener
    public void onResumed(ConsumerPartitionResumedEvent event) {
        log.info("Kafka partition resume applied: {}", event);
    }

    @EventListener
    public void onPaused(ConsumerPartitionPausedEvent event) {
        log.warn("Kafka partition pause applied: {}", event);
    }
}
```

Imports:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPartitionPausedEvent;
import org.springframework.kafka.event.ConsumerPartitionResumedEvent;
import org.springframework.stereotype.Component;
```

Application events confirm that state took effect on the container side. However, these events **do not prove the listener processed records successfully after resume**; correlate committed offsets, throughput, error rates, and business metrics.

A helpful structured log during incident coordination:

```text
incident_id=INC-4821
action=RESUME_PARTITION
topic=payment-requests
partition=2
consumer_group=payment-worker
instance=payment-worker-pod-3
control_generation=12
requested_state=ACTIVE
applied_state=ACTIVE
reason=payment-gateway-recovered
```

This is an illustrative log schema, not a default Spring Kafka format. Include timestamps, actor, and correlation IDs as appropriate, and never log payloads containing sensitive data.

## 15. Defining successful recovery with metrics

Evaluating recovery requires multiple perspectives:

| Signal | Meaning | Conclusion you must not draw alone |
|---|---|---|
| Container pause state | Resume request took effect where observed. | Does not prove records finished processing. |
| Assigned partitions | Consumer currently holds partition ownership. | Does not mean the partition is unpaused. |
| Committed offset | Group recorded progress. | Does not guarantee external side effects succeeded if listener lacks idempotency. |
| Lag per partition | Remaining offset backlog. | Does not tell whether individual events succeeded functionally. |
| Processing throughput | Record completion rate. | Does not reflect the rate of failed events going to DLT. |
| Retry/DLT rate | Failure and recovery levels. | Climbing DLT can mask trouble even while main-topic lag drops. |
| Dependency saturation | Risk of re-overloading. | Looking healthy for a few seconds may fail under full load. |
| Event age | Data delay and SLO/retention breach risk. | Low lag does not always mean fresh data. |

A "recovery complete" condition might require: all target partitions active on their true owners, committed offsets climbing steadily, lag shrinking toward target bounds, error/DLT rates not spiking abnormally, dependency headroom intact, and zero skipped data detected. Exact criteria and thresholds are application decisions.

## 16. Post-incident resume runbook

The following procedure assumes the incident has been identified and the prior pause was intentional.

### Phase A — Preparation

1. **Lock scope:** record incident ID, topic, group, paused partition list, and affected instances.
2. **Confirm root cause:** dependency/code/config fix is deployed with evidence in the target environment.
3. **Verify data safety:** committed offsets, log start/end, record age, retries/DLT, and suspected partially processed side effects.
4. **Verify resources:** stable pods, group assignments not rebalancing continuously, CPU/threads/connection pools have headroom.
5. **Set stop conditions:** error, latency, retry, and DLT thresholds plus how to pause again.
6. **Confirm control access:** operators or control plane can target the true partition owners with audit logging.

### Phase B — Canary resume

7. Pick **one partition or a small representative load slice** and update desired state to active.
8. Call `resumePartition(tp)` on the owning container, or let pod reconcilers apply desired state.
9. Wait for `isPartitionPauseRequested(tp) == false` and `isPartitionPaused(tp) == false` on the valid owner; if a container-wide pause remains, handle that pause request separately.
10. Monitor committed offsets, throughput, dependency error rates, latency, retries/DLT, and in-flight jobs over the defined observation window.
11. If thresholds breach, re-pause the canary and investigate; do not open remaining partitions.

### Phase C — Expansion and completion

12. Once canary stabilizes, reopen additional partitions in batches; between batches confirm dependency headroom and expected lag drain.
13. Re-verify desired/applied state after any rebalance or rolling deployment.
14. Once all target partitions have resumed, keep monitoring until backlog and event age return within business limits.
15. Reconcile events at risk of duplicate/partial side effects, process DLT entries, and update the incident timeline.
16. Mark the incident resolved only when **consumption + business logic + dependency** all satisfy defined recovery criteria.

Never reduce the runbook to a simplistic script like "resume all; sleep 30; done." As backlog size and business sensitivity vary, canary criteria and partition rollout order must adapt accordingly.

## 17. When should you pause again?

Right after resuming, signs may emerge that the dependency is about to collapse again or updated code still fails on older data. In that case:

```text
Resume batch N
       |
       v
Error rate / latency / DLT breaches stop condition
       |
       v
Pause batch N or affected partitions
       |
       v
Wait for pause applied; manage in-flight work
       |
       v
Investigate; lower rate limits/concurrency or fix data
       |
       v
Return to readiness gates before next resume attempt
```

Do not treat pausing again as a runbook failure: it is a pre-designed safety valve. Nor should you auto-resume right away on a tiny metric dip without hysteresis and a stability window.

If paused partition counts keep climbing, or each resume lasts only seconds, stop expanding, escalate the incident, and investigate root cause. Rapid toggling creates traffic bursts, retry storms, and makes tracking partial side effects difficult.

## 18. Common failures during resume

| Symptom | Possible cause | Remediation |
|---|---|---|
| Called `resume()` yet no new records appear | Container stopped, unassigned, per-partition pause still active, or topic has no backlog. | Check container lifecycle, assignments, requested/applied states, and offsets. |
| Resumed a partition yet lag does not drop | Slow consumer, dependency errors, poison record, or producer rate exceeds processing rate. | Inspect throughput, retries/DLT, dependency, and per-partition lag. |
| Only one pod resumes | Command hit a local registry rather than all owners. | Use deployment-wide desired state and reconcile by assignment. |
| Partition changed owner and starts running while needing pause | Desired pause stored only in old pod or rebalance race. | Persist state durably, reapply on assignment/startup with generation/versioning. |
| Duplicate processing appears after resume | Side effect succeeded before crash while offset did not commit. | Use event IDs, inbox/unique constraints, and API idempotency keys. |
| DLT spikes sharply right after resume | Old data still incompatible or business bug unfixed. | Halt expansion, inspect classifiers, schemas, and recoverer. |
| Consumer rebalances continuously | Long listener/blocking retries, poll interval, pod restarts, or networking. | Check `max.poll.interval.ms`, group logs, and processing durations. |
| Offset no longer valid | Old records expired past retention or removed by log cleanup. | Inspect log start, execute source recovery plan; never reset offsets arbitrarily. |
| Recently recovered gateway times out again | Thundering herd from resuming all partitions simultaneously. | Selective pausing, phased ramp-up, and concurrency/rate caps. |

## 19. Testing safe resume before production

Build integration tests with Kafka Testcontainers or embedded Kafka to simulate pause, resume, and record backlogs.

A baseline scenario:

1. Create a multi-partition topic, a test consumer group, and a fixed listener ID.
2. Send baseline records and verify partitions are assigned.
3. Pause one or more partitions using the container API.
4. Wait for the **applied** pause state rather than relying solely on a fixed `Thread.sleep`.
5. Publish more records to both paused and active partitions; verify active ones continue processing.
6. Simulate dependency recovery and resume one partition.
7. Confirm requested/applied states flip to active, backlogged records are consumed, and offsets advance.
8. Inject transient errors to verify retry/backoff, DLT, and stop conditions.
9. With multiple instances, trigger rebalances/restarts to verify desired state reapplies to the right owner.
10. Simulate side-effect completion followed by crash before commit to verify idempotency.

Tests must account for **in-flight records**: records polled before pause may still exist. Do not assert "zero listener invocations occur after calling pause" without waiting for applied pause state and prior work completion.

Never use production to simulate lost offsets, force fencing, or reset groups just to drill a runbook. Use isolated topics/groups and simulated dependencies.

## 20. Operational principles

- Resume is a **conditional procedure**, not a single API call.
- Verify dependency, consumer health, data, retention, idempotency, and rollback paths before reopening.
- Distinguish **resume requested**, **resume applied**, and **consumption healthy**.
- Use the Spring Kafka container API rather than manipulating `KafkaConsumer` directly from external threads.
- Never infer a partition resumed solely from Kafka assignments or lag.
- Across multiple pods, apply desired state on the **current owner** and reconcile after rebalances/restarts.
- Never reset offsets or seek to end to clear backlog without an approved business decision.
- Prefer **canary and phased ramp-up**, paired with rate limits, hysteresis, and stop conditions.
- Monitor committed offsets, lag, record age, dependency saturation, retries, DLT, and transaction errors together.
- Use event IDs/idempotency to handle records redelivered after crashes or resumes.
- Maintain audit logs of pause/resume reasons, incident IDs, actors, and applied states.
- Have a runbook to re-pause and recover data if retention limits were breached.

**Safe resume after an incident** is complete when consumption runs again **at the intended scope**, at a rate within downstream capacity, committed offsets and business outcomes advance validly, and no fresh wave of errors is triggered. Spring Kafka provides the pause/resume mechanics; true reliability depends on readiness gates, load control, end-to-end pipeline observability, and readiness to respond if recovery does not go as planned.
