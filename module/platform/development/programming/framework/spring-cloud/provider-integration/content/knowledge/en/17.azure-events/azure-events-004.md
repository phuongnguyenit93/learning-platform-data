# Checkpoints, Partition Ownership, and Consumer Recovery

Azure Event Hubs stores events per partition for a configured retention window. Consumers read the stream by position and must record progress to resume after a process restart, container replacement, or partition handoff to another instance. **Checkpoints** store the processed reading position; **partition ownership** identifies which processor instance is responsible for a partition within a consumer group; **recovery** is the process of resuming after failures without dropping events and while controlling re-reads.

In the **Azure Events** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, this lesson covers operating Spring Boot consumers with EventProcessorClient, Azure Blob checkpoint store, and Microsoft Entra ID. Learners will design timely checkpointing, understand ownership and rebalancing, recover from crashes or network outages, handle duplicates and poison events, account for retention, secure access, and build runbooks for production systems.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the relationships among partitions, consumer groups, ownership records, offsets, sequence numbers, and checkpoints.
- Distinguish between **received events**, **processed events**, **saved checkpoints**, and **archived events**.
- Describe how EventProcessorClient coordinates ownership and balances partitions across multiple instances.
- Choose an appropriate checkpoint store, initial position, checkpoint frequency, and replay policy.
- Analyze failure windows: crashing before commit, after commit but before checkpoint, checkpoint failures, and ownership loss.
- Design idempotent consumers, inbox/deduplication, quarantine, and poison event handling.
- Configure EventProcessorClient in Spring Boot with Managed Identity and Azure RBAC.
- Operate graceful shutdown, scale-out/in, recovery, and testing in isolated environments.
- Build dashboards/runbooks based on consumer lag, checkpoint age, ownership, and retention.

## 2. Concepts and State Boundaries

### 2.1. Partitions, Consumer Groups, and Processor Instances

An Event Hub is divided into **partitions**; each partition is its own ordered event log. A **consumer group** establishes an independent logical reading cursor for a workload. Within the same consumer group, multiple processor instances coordinate to divide partitions. Each instance may own one or more partitions depending on partition count and balance state.

For example, an event hub with 8 partitions:
- One instance can own all 8.
- Two instances can split roughly 4 + 4.
- Four instances can split roughly 2 per instance.
- Ten instances do not create ten independent reading streams when there are only 8 partitions; some instances may own no partitions.

Different consumer groups have separate progress and ownership. Analytics and fraud detection can read the same event hub without sharing checkpoints. Conversely, replicas of the same logical application must use **the same consumer group and the same checkpoint store** to coordinate.

### 2.2. Offsets, Sequence Numbers, and Checkpoints

- **Offset** is the event's position in a partition's log, usually represented by the SDK as a string.
- **Sequence number** is the monotonically increasing number of an event within a partition.
- **Checkpoint** is the durable progress record saved by a consumer to resume reading later.
- **Enqueued time** is when Event Hubs ingested the event, useful for measuring event age and ingestion latency.
- **Ownership record** is the coordination state indicating which processor instance currently holds the right to process a partition within a consumer group.

Offsets and sequence numbers are scoped per partition, not across the entire event hub. A checkpoint does not mean an event was processed exactly once; it only records the position from which the application decided it can resume.

### 2.3. Four States to Distinguish

| State | Meaning | Where Observed |
|---|---|---|
| Received | Processor received the event from Event Hubs | Callback and event metadata |
| Processed | Business side effects completed or event was durably quarantined | Database, inbox, quarantine store |
| Checkpointed | Reading position was saved to the checkpoint store | Blob checkpoint metadata |
| Archived | Event was written to long-term storage if required by architecture | Blob/ADLS or data lake |

Do not infer **processed** from **received**, or **archived** from **checkpointed**. The checkpoint store does not contain full event bodies and does not replace Event Hubs Capture.

## 3. Why Are Checkpoints Needed?

Consumers can stop due to deployments, crashes, network drops, quota exhaustion, credential errors, node eviction, or rebalancing. On restart, the processor needs to know where to resume reading.

Without saved checkpoints, the application may have to start from the initial position, causing heavy re-reads or skipped history if an unsuitable position is chosen. If checkpoints are saved at the wrong time, consumers can skip unprocessed events. Checkpointing is therefore part of the **correctness contract** between the stream and the application.

~~~mermaid
flowchart LR
    EH["Event Hubs partition"] --> R["Read event at offset N"]
    R --> H["Business handler"]
    H --> DB["Commit side effect"]
    DB --> CP["Persist checkpoint N"]
    CP --> NEXT["Continue with next events"]
    CP -. "Failure before save" .-> REPLAY["Resume from older checkpoint"]
    REPLAY --> H
~~~

A proper checkpoint store helps the processor recover its reading position; it does not automatically recover database transactions, guarantee handler idempotency, or extend Event Hubs retention.

## 4. Blob Checkpoint Store and Partition Ownership

### 4.1. What Does the Blob Checkpoint Store Store?

The Azure SDK provides the **azure-messaging-eventhubs-checkpointstore-blob** package with BlobCheckpointStore. The store uses Blob Storage to keep ownership and checkpoint metadata per partition/consumer group/event hub following SDK conventions.

Two primary groups of information:
- **Ownership:** processor owner ID, partition ID, update/expiry timestamps, and coordination metadata.
- **Checkpoint:** offset/sequence number persisted by the consumer for the partition.

Applications should not manually edit or delete these metadata blobs while processors are running. Their format and naming are library implementation details; use the SDK checkpoint store to manage them rather than creating parallel custom leases/records.

### 4.2. How Is Ownership Coordinated?

Conceptually, each processor instance has an owner ID. Instances read the list of ownership records in the checkpoint store, identify unowned partitions or expired ownerships, and attempt to claim ownership using the store's conditional update mechanism. An instance owning a partition periodically updates its ownership record to indicate it is still active.

When a new instance joins or an existing instance stops renewing ownership:
1. Processor instances detect ownership state changes during load-balancing cycles.
2. An instance can claim unowned or expired partitions.
3. The old instance may close processing for transferred partitions.
4. The new instance starts reading from the saved checkpoint or initial position if no checkpoint exists.
5. Uncheckpointed events may be re-read.

Claiming ownership relies on conditional updates in the checkpoint store and the SDK's load-balancing algorithm. Never assume a network-isolated process loses ownership instantaneously; ownership expiry and balancing intervals introduce a detection delay.

### 4.3. Ownership Is Not a Business Lock

Ownership helps processor instances coordinate reading partitions within the same consumer group. It is not a distributed lock protecting database rows, does not guard external HTTP API side effects, and does not guarantee an event runs only once.

During network partitions, an old instance may not yet know it lost ownership while another instance begins claiming the partition after expiry. Applications must still tolerate duplicates/replays and enforce idempotency at the business layer. Never use ownership records as the sole mechanism to prevent double payments or duplicate database updates.

### 4.4. One Checkpoint Store for Multiple Instances of the Same Workload

Instances in the same consumer group must see the same checkpoint store to coordinate ownership and progress. Different consumer groups can have separate checkpoints; they can share a storage account/container if SDK configuration and permissions allow, though separate scopes/containers per workload or environment should be designed when operational and security isolation is needed.

Do not arbitrarily share checkpoint namespaces/containers across:
- Dev and production.
- Two different event hubs that happen to use the same consumer group name.
- Two logical applications with different processing goals.
- A temporary test run and a production processor.

The checkpoint store should outlive individual processes/pods; never create a new random container on each deploy, or new processors will not find old checkpoints.

## 5. Partition Ownership Lifecycle in EventProcessorClient

### 5.1. When the Processor Starts

An EventProcessorClient typically performs:
1. Creates or uses an Event Hubs client with the configured namespace, hub, and consumer group.
2. Reads partition info and ownership/checkpoint records from the store.
3. Participates in load balancing with other instances in the same group.
4. Claims ownership of assigned partitions.
5. Determines starting position: saved checkpoint or initial position.
6. Invokes event-processing and error-handling callbacks as the processor operates.

Applications do not need to write partition assignment algorithms when using EventProcessorClient. However, you must configure matching consumer group, checkpoint store, credentials, and resource IDs across replicas of the same workload.

### 5.2. Steady-State Operation

The processor periodically renews ownership and checks balance. Events are received from partitions currently owned by the instance. Applications can checkpoint per event, per batch, or on a time interval based on their replay budget.

When a partition is handed off, the processor closes handling for that partition per SDK lifecycle and another instance can take over. Partition close/initialization callbacks, if used, help manage per-partition resources; do not keep unique business state solely in instance memory because partitions can migrate to other instances.

### 5.3. Scaling Out

When adding replicas:
- The new instance registers an owner ID.
- Existing processors and the new instance observe ownership records.
- Load balancing can migrate some partitions to distribute load.
- The new instance starts from the saved checkpoint.
- During handoff, there may be a brief throughput dip and some replay.

Do not expect scale-out to increase throughput linearly right away. Partition count caps how many processors can concurrently own partitions in the same group. If the bottleneck is the database, Blob checkpoint store, or handler logic, adding pods can increase downstream load without increasing useful throughput.

### 5.4. Scaling In or Stopping an Instance

When an instance stops cleanly:
- Invoke stop according to the SDK lifecycle.
- Let the processor relinquish ownership and close partition resources.
- Finish in-flight callbacks within the allotted shutdown grace period if possible.
- Never checkpoint uncommitted events.
- Remaining instances claim partitions once ownership is released or expires.

If a process is killed abruptly, ownership may linger until expiry. Other instances may not take over immediately. Container termination grace periods must be long enough for shutdown, yet not so long that deployments hang.

## 6. Initial Position and Resume

### 6.1. When No Checkpoint Exists Yet

When a consumer group/partition has no checkpoint yet, the processor needs an initial position. Common options:
- **Earliest:** read from the earliest event still in retention.
- **Latest:** start from new events written after startup.
- **Enqueued time:** start from a chosen timestamp.
- **Offset/sequence number:** start from a specific position if still available.

Choose the initial position based on workload goals:
- Projections needing to rebuild state may require earliest within retention or an archive.
- Consumers only interested in new events from deployment onward may choose latest.
- Backfills may choose a specific timestamp or offset in a dedicated consumer group.

Do not leave production initial position to implicit defaults without documenting it explicitly in configuration and runbooks.

### 6.2. When a Checkpoint Already Exists

When a valid checkpoint exists for a partition, the processor resumes from that checkpoint. Initial position is not a reset switch applied on every restart. If you need to replay:
- Create a new consumer group with the desired initial position.
- Use a dedicated rate-limited replay consumer/processor.
- Use an archive/Capture if the target data has aged out of retention.
- Reset checkpoints only under a supported procedure with backups/reconciliation and when processors are not competing for ownership.

Do not delete checkpoint blobs to "fix an issue" while production processors are still running. Doing so can trigger massive re-reads, duplicates, or ownership churn.

### 6.3. Retention and Stale Checkpoints

Checkpoints store positions, but Event Hubs retains events only for the configured retention period. If a consumer stops longer than retention, events at the old offset may have been purged. A checkpoint cannot bring back expired events.

When you discover a checkpoint is outside available data:
- Determine current retention and when the consumer stopped.
- Check whether an archive/Capture or another source exists to backfill.
- Deliberately choose an initial position for the remaining data.
- Record the potential data gap and notify business owners.
- Never silently switch to latest if business requirements mandate complete history.

## 7. Checkpointing at the Right Time: Commit First, Checkpoint After

### 7.1. Failure Windows

Suppose a consumer receives event E, updates the database, and then checkpoints:
- **Checkpoint before database commit:** if the process crashes between steps, the checkpoint advanced while the side effect is not durable; the event may be skipped.
- **Database commit before checkpoint:** if the process crashes between steps, the event may be re-read; idempotency is needed to avoid repeating side effects.
- **Database commit and dedup in the same transaction before checkpoint:** the event is re-read, and the consumer recognizes it was already processed.
- **Durable quarantine before checkpoint:** unprocessable malformed events can be isolated and skipped under an explicit policy.

~~~mermaid
sequenceDiagram
    participant EH as Event Hubs
    participant C as Consumer
    participant DB as Database
    participant B as Blob checkpoint store
    EH->>C: Event E at offset N
    C->>DB: Commit business effect + inbox(E)
    DB-->>C: Commit OK
    C->>B: Save checkpoint N
    B-->>C: Checkpoint saved
    Note over C,B: If checkpointing fails, E may replay
~~~

There is no default atomic transaction spanning the business database and the Blob checkpoint store. Therefore, duplicates occurring after commit but before checkpoint are normal scenarios to design for, not impossible edge cases.

### 7.2. Checkpoint per Event or per Batch?

| Strategy | Advantage | Risk |
|---|---|---|
| Every event | Small replay window | Many Blob/checkpoint operations, may lower throughput |
| Every N events | Fewer checkpoint writes | May replay many already-processed events |
| Time-based interval | Easy to bound replay duration | Replayed event count varies with throughput |
| After a DB batch commit | Aligns progress with durable batches | Must know exactly which batch committed and ensure no earlier event is still pending |

Choose based on throughput, processing time, checkpoint store cost, processing RPO, and idempotency capabilities. When checkpointing by batch, only checkpoint up to the last event of a **contiguous completed sequence**. Never checkpoint past an earlier event that is still processing.

### 7.3. Do Not Let Parallel Processing Advance Checkpoints Past Failed Events

Within a partition, Event Hubs delivers events in order. However, if a callback submits events to an executor for async processing, a later event can finish before an earlier one. Checkpointing on the later event can cause the unfinished earlier event to be skipped after a restart.

Options:
- Process sequentially per partition.
- Parallelize by aggregate key while maintaining per-key order and a contiguous completion watermark.
- Persist processing status durably to support continuation/reconciliation.
- Only update checkpoints up to the last offset/sequence where all preceding events have completed or been quarantined.
- Limit in-flight events to prevent unbounded internal queues.

## 8. Idempotency and Inbox to Prevent Duplicate Processing

Event Hubs consumers must typically tolerate at-least-once processing due to replays, rebalancing, and checkpoint failures. Use a stable business event ID, not only the offset.

PostgreSQL example:

~~~sql
CREATE TABLE processed_event (
    consumer_name varchar(100) NOT NULL,
    event_id varchar(200) NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Within the same transaction:
1. Insert the event ID into the `processed_event` table.
2. On unique conflict, the event was already processed; skip side effects.
3. If the insert succeeds, update projections/business state.
4. Commit.
5. Only after the handler returns successfully should the checkpoint be updated.

Illustrative SQL statement:

~~~sql
INSERT INTO processed_event (consumer_name, event_id)
VALUES ('order-projection', :event_id)
ON CONFLICT DO NOTHING;
~~~

If zero rows are inserted, the event was already recorded. Ensure the dedup insert and business side effects execute in the **same transaction**; separating them into two transactions allows a crash after recording dedup but before the side effect, causing lost processing on replay.

Besides the event ID, you can store a payload hash or schema version to detect cases where the same ID arrives with a different payload. Dedup table retention must exceed the window during which events can be replayed or resent.

## 9. Recovering from Different Failure Types

### 9.1. Process/Container Crash

1. The orchestrator detects the instance is unhealthy.
2. The old instance's ownership record stops updating.
3. After ownership expires and load balancing runs, a remaining instance can claim the partition.
4. The new instance reads the latest checkpoint.
5. Events after the checkpoint are re-read.
6. Dedup/inbox prevents repeating already-committed side effects.

Track ownership expiry duration and load-balancing intervals to estimate recovery time. Do not treat one interval setting as an SLA; actual recovery time also depends on networking, Blob, Event Hubs, and instance state.

### 9.2. Losing Connection to the Blob Checkpoint Store

A processor can stay connected to Event Hubs yet fail to read/write ownership or checkpoints. In that case:
- Verify Blob DNS, firewall, private endpoints, and TLS.
- Verify the runtime principal and Storage Blob Data Contributor role.
- Check container URL/account and Region.
- Inspect checkpoint/ownership errors in processor logs.
- Do not create containers or switch storage accounts using runtime permissions if IaC owns the resource.
- Once connectivity recovers, inspect actual checkpoints and replay behavior.

Do not assume a checkpoint update succeeded merely because the handler threw no exception. If a Blob request times out, the save result may be indeterminate; on restart, read the actual checkpoint from the store and expect duplicates.

### 9.3. Losing Connection to Event Hubs

When the namespace or network path has an outage:
- Processors may stop receiving events or emit connection errors.
- Ownership heartbeats may fail to renew depending on store dependencies and SDK behavior.
- Producers may still succeed if the producer path is independent.
- When connectivity recovers, processors resume from checkpoints, potentially replaying events.

Distinguish Event Hubs errors, DNS/private endpoint errors, Entra token errors, RBAC errors, and Blob checkpoint errors. A 403 error is not a quota issue; a timeout does not prove events were lost.

### 9.4. Old Instance Returns After Ownership Migrated

An old instance can regain network connectivity after another instance already claimed the partition. The SDK uses ownership coordination to manage reading rights; however, never design side effects assuming zero overlap or zero duplicates in every failure mode.

Handlers must remain idempotent. For non-repeatable actions like payments, sending emails, or calling partner APIs, use idempotency keys at the target system or a durable stateful outbox/workflow.

### 9.5. Deleted or Corrupted Checkpoints

Before making changes:
- Stop processor instances for the affected consumer group per procedure.
- Verify the correct event hub, consumer group, partition, and checkpoint store.
- Check Blob backups/soft delete/versioning if configured.
- Determine the initial position and range of data to re-read.
- Assess side-effect impact and replay rate.
- Execute the approved change, then start a canary instance and observe before scaling.

Do not wipe an entire checkpoint container to fix a single partition without understanding metadata layout and impact on other consumer groups.

## 10. Poison Events, Quarantine, and Replay

Event Hubs is a stream log, not a queue with a built-in DLQ like Service Bus. An invalid-schema event or one causing business errors can cause consumers to fail repeatedly if checkpoints never advance. Define explicit policies:

- **Transient failure:** bounded retries inside the handler or pause partition processing; do not checkpoint past unprocessed events.
- **Permanent/schema failure:** durably write the event and required metadata to a quarantine store/queue; only checkpoint after quarantine succeeds and policy allows.
- **Unknown outcome:** check inbox/idempotency records or reconcile with the target system before retrying side effects.
- **Manual intervention:** stop/throttle the processor per runbook when automated decisions are unsafe.

Quarantine records should include event ID, partition ID, offset, sequence number, enqueued time, schema version, error category, and correlation ID. Avoid storing raw payloads unnecessarily; if needed, encrypt them and enforce strict access controls.

Replay requires dedicated tooling:
- Choose a new consumer group or explicit offset/time range.
- Throttle replay speed so the database is not overloaded.
- Tag a replay run ID and track succeeded/failed event counts.
- Preserve the original event ID so consumers deduplicate.
- Never republish an event with a brand-new ID if the goal is to reprocess the same intent without linking back to the original event.
- Plan how to pause and resume the replay.

## 11. Configuring EventProcessorClient in Spring Boot

### 11.1. Dependencies and Configuration Properties

Example requires compatible Azure SDK libraries:
- azure-messaging-eventhubs
- azure-messaging-eventhubs-checkpointstore-blob
- azure-storage-blob
- azure-identity

Use a BOM matching your Spring Boot and Spring Cloud Azure versions. Do not mix incompatible SDK versions.

Example custom properties:

~~~yaml
app:
  event-hubs:
    namespace: orders-prod.servicebus.windows.net
    event-hub-name: order-events
    consumer-group: order-projection
    checkpoint-container-url: https://ordersprodstore.blob.core.windows.net/eventhub-checkpoints
    initial-position: earliest
~~~

The `app.*` keys are custom application properties in this example, not shared auto-configuration properties across all Spring Cloud Azure versions. Production must obtain endpoints and resource IDs from trusted deployment manifests; never hardcode credentials.

### 11.2. Creating Credentials and Checkpoint Client

~~~java
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobContainerAsyncClient;
import com.azure.storage.blob.BlobContainerClientBuilder;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@ConfigurationProperties(prefix = "app.event-hubs")
record EventHubProperties(
        String namespace,
        String eventHubName,
        String consumerGroup,
        String checkpointContainerUrl,
        String initialPosition) {}

@Configuration
@EnableConfigurationProperties(EventHubProperties.class)
class EventHubStorageConfiguration {

    @Bean
    DefaultAzureCredential defaultAzureCredential() {
        return new DefaultAzureCredentialBuilder().build();
    }

    @Bean
    BlobContainerAsyncClient checkpointContainer(
            EventHubProperties properties,
            DefaultAzureCredential credential) {
        return new BlobContainerClientBuilder()
                .endpoint(properties.checkpointContainerUrl())
                .credential(credential)
                .buildAsyncClient();
    }
}
~~~

DefaultAzureCredential selects an appropriate credential according to the environment and provider chain order of the SDK version. Local developer credentials may differ from Managed Identity or Workload Identity when running on Azure. Verify the actual principal and role assignments on the storage account/container.

### 11.3. Creating the Processor and Updating Checkpoints

~~~java
import com.azure.messaging.eventhubs.EventProcessorClient;
import com.azure.messaging.eventhubs.EventProcessorClientBuilder;
import com.azure.messaging.eventhubs.checkpointstore.blob.BlobCheckpointStore;
import com.azure.storage.blob.BlobContainerAsyncClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class EventProcessorConfiguration {

    @Bean(destroyMethod = "stop")
    EventProcessorClient eventProcessorClient(
            EventHubProperties properties,
            DefaultAzureCredential credential,
            BlobContainerAsyncClient checkpointContainer,
            OrderEventHandler handler) {

        return new EventProcessorClientBuilder()
                .consumerGroup(properties.consumerGroup())
                .credential(
                        properties.namespace(),
                        properties.eventHubName(),
                        credential)
                .checkpointStore(new BlobCheckpointStore(checkpointContainer))
                .processEvent(context -> {
                    // The handler must commit side effects or durably quarantine.
                    handler.handle(context.getEventData());

                    // Only update the checkpoint after the handler returns successfully.
                    context.updateCheckpoint();
                })
                .processError(error -> {
                    // Use structured logger/metrics in production.
                    // Do not log tokens or sensitive raw payloads.
                    System.err.println(
                            "Event processor error: " + error.getThrowable());
                })
                .buildEventProcessorClient();
    }
}
~~~

This is a skeleton based on the Azure SDK for Java API; verify method signatures against your actual dependency versions. The processor bean is reused throughout the application lifecycle. Never create a new processor per request or per event.

### 11.4. Starting and Stopping with Lifecycle

~~~java
import com.azure.messaging.eventhubs.EventProcessorClient;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
class EventProcessorLifecycle implements ApplicationRunner {
    private final EventProcessorClient processor;

    EventProcessorLifecycle(EventProcessorClient processor) {
        this.processor = processor;
    }

    @Override
    public void run(ApplicationArguments args) {
        processor.start();
    }
}
~~~

The processor bean specifies `destroyMethod = "stop"` so Spring stops the client when the context closes. In production:
- Configure a termination grace period sufficient for shutdown.
- Stop accepting new work when the instance is preparing to shut down.
- Track running callbacks and database transactions.
- Never checkpoint events that are half-processed.
- Ensure Blob/DB clients are not closed before the processor.
- After an unclean shutdown, expect replays from the last checkpoint and deduplicate.

If using a Spring lifecycle interface instead of ApplicationRunner, ensure start/stop are not invoked multiple times and dependency ordering is explicitly managed.

### 11.5. Initial Position Applies Only When No Checkpoint Exists

Initial position settings must be mapped to the EventProcessorClient API for your SDK version and apply per partition. Once a checkpoint exists, the processor normally resumes from the checkpoint. Do not treat changing initial position as a way to reset saved progress.

If replay is required, prefer a separate consumer group and a rate-limited runbook. Avoid deleting production checkpoints while processors are active.

## 12. Processing Events Safely Before Checkpointing

A handler should:
1. Validate event ID, event type, and schema version.
2. Open a database transaction.
3. Insert the event ID into an inbox/processed-event table with a unique constraint.
4. If the event was already processed, exit the handler cleanly without repeating side effects.
5. If the event is new, update business data.
6. Commit the transaction.
7. Only then does the callback update the checkpoint.

PostgreSQL example:

~~~sql
CREATE TABLE processed_event (
    consumer_name varchar(100) NOT NULL,
    event_id varchar(200) NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Insert statement:

~~~sql
INSERT INTO processed_event (consumer_name, event_id)
VALUES ('order-projection', :event_id)
ON CONFLICT DO NOTHING;
~~~

If the insert creates no new row, the event was processed previously. The deduplication table and business changes must participate in the same transaction. If an event ID is reused with a different payload, record a conflict instead of silently treating it as a valid duplicate.

Checkpointing is not inside the database transaction. Consequently, a successful DB commit followed by a failed Blob checkpoint update causes a replay; the inbox guarantees side effects do not repeat. Conversely, never checkpoint before committing.

## 13. Scaling, Rebalancing, and Resilience

### 13.1. Partition Count Limits Parallelism

Within a consumer group, one partition is owned by at most one processor instance at a time under standard coordination. If an event hub has 6 partitions, scaling to 20 pods does not create 20 useful partition workers. Excess pods may own no partitions.

Before scaling:
- Inspect partition count and load distribution.
- Measure event processing duration, CPU, DB latency, and checkpoint latency.
- Check for hot partitions caused by skewed partition keys.
- Avoid frequent restarts/scaling that cause repeated ownership rebalancing.
- Consider increasing partitions only when supported by the tier and after evaluating ordering/key mapping.

### 13.2. Rebalancing Can Trigger Replays

When ownership moves from instance A to B, B starts from the latest checkpoint. Events processed by A but not yet checkpointed can be re-read by B. This is an expected replay window. Too-infrequent checkpoints enlarge the replay window; too-frequent checkpoints raise Blob overhead.

### 13.3. A Single Slow Partition

A partition can lag due to:
- Hot partitions.
- Large events or slow handlers.
- DB connection pool exhaustion.
- Synchronous external API calls.
- Slow Blob checkpoint store.
- Parallel callback execution breaking ordering assumptions.

Adding instances does not split one partition across multiple owners in the same consumer group. Optimizing handlers, improving key distribution, or separating workloads addresses the root cause.

## 14. Monitoring and Consumer Health Metrics

Do not monitor only whether the processor is running. A processor can be up yet fail to advance checkpoints or fall steadily behind.

| Metric | Meaning | Signs Requiring Investigation |
|---|---|---|
| Active processor instances | Number of participating instances | Unexpected drop or constant churn |
| Partition ownership count | Partitions owned per instance | An instance owns zero partitions or prolonged imbalance |
| Ownership changes/rebalances | Partition handoff frequency | Continuous rebalancing, unclean shutdowns |
| Last checkpoint time | Timestamp of latest checkpoint | Stagnant for an abnormal period |
| Checkpoint age | Age of checkpoint per partition | Growing replay window and rising lag risk |
| Consumer lag | Gap between read position and stream tail | Consumer not keeping pace with ingestion |
| Event processing duration | Callback execution time | Slow handler or downstream bottleneck |
| Checkpoint failures | Errors saving progress | Blob permissions/network/timeout issues |
| Duplicates suppressed | Replayed events deduplicated | Sudden spike after deploy/rebalance |
| Quarantine count | Events failing normal processing | Schema drift or buggy producer |
| Oldest unprocessed event age | Age of oldest incomplete event | Business SLAs may be breached |

Consumer lag can be estimated from sequence/offset or enqueued time of the newest event versus consumer progress. Event Hubs metrics do not always expose granular per-application consumer lag; emit application metrics from processors and checkpoint stores. Never subtract offsets across two different partitions as a naive global lag figure.

### 14.1. Alerts Should Link to Runbooks

Examples:
- Checkpoint age exceeds SLO threshold.
- Consumer lag continuously climbing.
- Processor instance stopped or owns zero partitions.
- Blob checkpoint writes returning 403/timeouts.
- Frequent ownership churn.
- Rapid rise in quarantined events.
- Unusual spike in p95/p99 event processing duration.
- Events nearing retention expiration before consumer processing.

Every alert needs an owner, severity, dashboard, request/partition context, and identity/network verification steps. Do not apply one fixed numeric threshold to every event hub; baselines depend on throughput, retention, and business requirements.

## 15. Consumer Recovery Runbooks

### 15.1. Consumer Completely Stopped

1. Verify deployment status, pods/processes, health checks, and shutdown reason.
2. Check namespace, event hub, consumer group, and checkpoint container in configuration.
3. Verify the runtime principal and Event Hubs Data Receiver role.
4. Verify Blob Data Contributor, DNS, firewall, and private endpoints.
5. Inspect ownership records and checkpoint age; do not delete metadata.
6. Start a canary instance, confirm ownership acquisition and resumption from checkpoint.
7. Monitor lag, duplicates, DB, and checkpoints before scaling out fully.

### 15.2. Consumer Running, Yet Checkpoints Do Not Advance

1. Check whether the handler blocks, retries infinitely, or hits transaction timeouts.
2. Check Blob write errors, RBAC, tokens, and networking.
3. Verify the callback calls `updateCheckpoint` after successful processing.
4. Confirm no exceptions are swallowed and checkpoints are not called before commit.
5. Check whether batch/async processing advances checkpoints past unfinished events.
6. Modify checkpoints only under an approved recovery procedure.

### 15.3. Large Lag Approaching Retention Limit

1. Measure ingestion rate versus processing rate.
2. Check which partitions are hot or unowned.
3. Inspect downstream DB, thread pools, Blob checkpoints, and network.
4. Throttle producer rates if possible and increase consumer capacity within partition limits.
5. If replay/backfill is needed, use archive/Capture or retained data sources.
6. Record any data window lost past retention and handle per business requirements.

### 15.4. Events Reprocessed After Deployment

1. Compare deploy time, shutdown time, and latest checkpoint timestamp.
2. Check ownership rebalancing and checkpoint store health.
3. Measure duplicate suppression in the inbox table.
4. Verify external non-DB side effects use idempotency keys.
5. Never reset checkpoints to eliminate duplicates; fix the root cause and reconcile business state.

## 16. Testing Recovery in an Isolated Environment

Use dedicated test event hubs, consumer groups, and Blob checkpoint containers. Never reset production checkpoints, delete ownership blobs, or inject network failures against real resources just to test.

| Scenario | How to Test | Expected Result |
|---|---|---|
| Normal restart | Cleanly stop/start processor | Resumes from checkpoint |
| Crash after DB commit before checkpoint | Kill test process at fault point | Events replay, but dedup prevents duplicate side effects |
| Crash before DB commit | Kill before commit | Events are re-read and processed |
| Blob checkpoint 403 | Use test identity lacking Blob data role | Checkpoint failure observed; no false progress reported |
| Blob network unavailable | Block endpoint in test environment | Processor reports errors; recovers once network returns |
| Instance scale-out | Increase instances in same consumer group | Ownership redistributes |
| Instance scale-in | Stop one processor | Partitions are claimed by another instance after coordination |
| Ownership expiry | Simulate an instance failing to renew ownership | Remaining instance takes over after expiry |
| Duplicate event | Re-send same event ID | Single business side effect |
| Poison event | Send invalid-schema payload | Quarantined or halted per policy; never silently skipped |
| Checkpoint older than retention | Use suitable test hub/retention | Alerting and explicit initial position/archive handling |
| Replay via new consumer group | Read from earliest in test | Controlled, idempotent replay |
| Out-of-order events | Send aggregate versions out of order | Consumer detects gap/stale event |
| Graceful shutdown | SIGTERM mid-processing | Clean stop or safe replay |
| Cross-environment access | Dev identity accesses prod checkpoint/event hub | Denied by RBAC/network |

Tests should collect event ID, partition ID, offset, sequence number, checkpoint timestamp, sanitized owner ID, and correlation ID for analysis. Never log tokens or sensitive raw payloads.

## 17. Common Design Mistakes

| Mistake | Consequence | Prevention |
|---|---|---|
| Checkpoint before DB commit | Lost side effects after crash | Commit first, checkpoint after |
| Sharing checkpoints across different logical workloads | Conflicting progress/ownership | Separate consumer groups and store conventions |
| Creating a new checkpoint container per deploy | Inability to resume from old checkpoints | Stable resources managed by IaC |
| Separate consumer group per pod | Each pod reads the entire stream, multiplying load | Same workload shares one group |
| Swallowing exceptions then checkpointing | Failed events skipped | Durable quarantine or controlled halt |
| Believing ownership prevents duplicates | Repeated side effects on crash/rebalance | Database inbox/idempotency |
| Checkpointing too frequently | Higher I/O and cost, lower throughput | Measure and choose batch/interval |
| Checkpointing too infrequently | Large replay window | Set replay budget and deduplicate |
| Async processing advancing checkpoints past pending events | Pending events skipped | Sequential processing or contiguous completion watermark |
| Arbitrarily resetting production checkpoints | Massive replay and duplicates | Runbook, approval, canary, and reconciliation |
| Using initial position as a restart reset | Reading wrong offset or dropping data | Apply initial position only when no checkpoint exists |
| Requiring long-term replay without archiving | Data past retention is unrecoverable | Capture/ADLS archive with dedicated retention |

## 18. Pre-Production Checklist

- **Identity:** Processor has Event Hubs Data Receiver; checkpoint store has Storage Blob Data Contributor at the right scope.
- **Resources:** Stable namespace, hub, consumer group, and Blob container isolated per environment/workload.
- **Ownership:** Replicas share the same group and checkpoint store; load balancing and rebalancing observed.
- **Initial position:** Explicitly configured; behavior when no checkpoint exists is understood.
- **Checkpointing:** Only after durable side effects; frequency derived from replay budget.
- **Idempotency:** Stable event ID, unique constraint/inbox, and external non-DB side effects protected against duplicates.
- **Ordering:** Never checkpoint past unfinished events; aggregate version checked when needed.
- **Retention:** Consumer can keep up; archive/Capture meets long-term replay requirements.
- **Lifecycle:** Started/stopped via Spring lifecycle; termination grace period and graceful shutdown tested.
- **Failure handling:** Bounded retries, quarantine, runbooks for Blob/Event Hubs/network/identity failures.
- **Observability:** Ownership, checkpoint age, consumer lag, processing duration, duplicates, and quarantine have metrics/alerts.
- **Recovery:** Tested crash before/after commit, checkpoint failure, scaling, replay, and retention expiry.
- **Security:** No static credentials in source; logs stripped of secrets and sensitive payloads.
- **Cost:** Monitoring Event Hubs tier/throughput, Blob checkpoint operations, retention, Capture, networking, and monitoring.

## 19. Summary

**Checkpoints** store the processed reading position; **partition ownership** coordinates processor instances within the same consumer group; **recovery** resumes from checkpoints after crashes, rebalancing, or network disconnects. These three mechanisms work together, yet they do not create an exactly-once transaction spanning Event Hubs, Blob Storage, and the business database.

When operating Spring Boot with EventProcessorClient, use a durable checkpoint store, share one consumer group across replicas of the same workload, commit side effects before checkpointing, deduplicate by event ID, and bound replays within retention. Combining Managed Identity, least-privilege RBAC, graceful shutdown, per-partition metrics, and recovery runbooks ensures your consumer continues operating predictably when instances, networks, or services fail.
