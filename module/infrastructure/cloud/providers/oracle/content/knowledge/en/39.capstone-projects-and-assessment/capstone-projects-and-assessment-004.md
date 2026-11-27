# Message Processing Project with Streaming, Queue, and Java Workers

## 1. Objectives and Deliverables

In the **Capstone Projects and Assessment** chapter of the **CLOUD_PROVIDERS_ORACLE** module, this project combines Oracle Cloud Infrastructure (OCI) Streaming, Queue, Compute, IAM, VCN, and an Oracle Database into an asynchronous order-processing pipeline. Learners must prove the system still produces correct results when messages are redelivered, processes stop mid-flight, or the database becomes temporarily unreachable.

The final deliverables include a Java event producer, a Java dispatcher forwarding events from Streaming to Queue, competing Java workers consuming tasks, and a database storing results. The infrastructure must include role-based authorization, monitoring, recovery procedures, reproducible deployment, and cost-control measures.

After completing this project, learners will be able to:

- Explain when a replayable event log is required versus when a work queue is required.
- Pinpoint the exact success-acknowledgment boundaries across producer, dispatcher, and worker.
- Implement idempotent processing using unique keys and database transactions.
- Measure latency, backlog, throughput, and fault-recovery behavior.
- Protect data flows with IAM, network connectivity, and proper credential management.
- Present acceptance evidence, architectural trade-offs, and limitations of test results.

The configurations and performance targets below are **lab choices**, not OCI service limits, SLA commitments, or pricing guarantees.

## 2. Business Problem and Scope

A sales system emits an event when an order is accepted. Each valid event must create exactly one fulfillment preparation request in the business table.

Standard flow:

1. The producer creates an `OrderAccepted` event with a stable `eventId`.
2. The producer sends the event to the `orders-events` stream.
3. The dispatcher reads the stream using consumer group `fulfillment-dispatch-v1`.
4. The dispatcher forwards the raw envelope to the `fulfillment-tasks` queue.
5. A worker reads the task, validates the data, and writes to the database.
6. The worker deletes the message from Queue only after the business transaction commits.

The business outcome of this project is a `READY_FOR_FULFILLMENT` record. The project does not call shipping carriers, charge payments, or send real emails. External side effects outside the database require their own idempotency protocols if added.

Three invariants to protect:

| Invariant | Testable Statement |
| --- | --- |
| Never drop an acknowledged event | Every event confirmed as accepted by the service to the producer must reach a business outcome or a reconcilable error state, within the designed retention window and recovery conditions |
| At most one business effect per event | The `(eventId, effectName)` pair is recorded only once, even when transport messages appear multiple times |
| Never acknowledge before durable handoff | The dispatcher never advances its checkpoint before handoff completes; the worker never deletes a message before data commits |

The phrase "exactly once" in the second invariant describes only the effect protected inside the database transaction. The system still tolerates duplicate publishing or duplicate delivery. There is no default distributed transaction spanning Streaming, Queue, and Oracle Database.

## 3. Reference Architecture

~~~mermaid
flowchart LR
    P["Java producer"] -->|"OrderAccepted"| S["OCI Streaming: orders-events"]
    S -->|"Consumer group"| D["Java dispatcher"]
    D -->|"Forward envelope"| Q["OCI Queue: fulfillment-tasks"]
    Q --> W1["Java worker A"]
    Q --> W2["Java worker B"]
    W1 -->|"JDBC transaction"| DB[("Oracle Database / Autonomous Database")]
    W2 -->|"JDBC transaction"| DB
    Q -->|"Exceeds delivery threshold"| DLQ["Dead letter queue"]
    D -->|"Unforwardable data"| QUAR["Durable quarantine store"]
    S -. "Dedicated replay consumer group" .-> R["Replay tool"]
    R -. "Preserve eventId" .-> Q
    D -. "Logs, metrics" .-> O["OCI Logging / Monitoring"]
    W1 -. "Logs, metrics" .-> O
    W2 -. "Logs, metrics" .-> O
~~~

In the baseline setup, dispatcher and workers run on Compute instances in a private subnet. The producer may run on a separately authorized load-generation host. The Oracle Database uses a private endpoint if the lab environment supports that configuration.

The quarantine store handles cases where the dispatcher cannot enqueue a record, such as an envelope exceeding application limits. A database quarantine table keyed by `(stream_id, partition_id, source_offset)` can be used. If not implementing this store, the dispatcher must halt checkpoint progression and raise an alert; never skip a record and move on.

The dispatcher's quarantine store differs from Queue's DLQ. An event that has never entered Queue cannot be protected by Queue's DLQ.

### Why Use Both Streaming and Queue?

Streaming retains a log so multiple independent groups can consume it and data can be replayed within the retention period. Queue acts as a work buffer, letting workers share load and handle per-task redelivery. Not every application needs both; this project uses both to practice the differences and handoff boundaries.

A Queue-only option fits better when event history for replay is unnecessary. A Streaming-only option may fit when the consumer group handles work distribution and retries itself. In the report, learners must explain the benefits of the added component against the extra cost and operational overhead.

## 4. Understanding Semantics Before Writing Code

| Aspect | Streaming in This Project | Queue in This Project |
| --- | --- | --- |
| Data model | Partitioned log, read via cursor | Task queue, received with a receipt |
| Progress | Committed consumer group position | Message deletion after processing |
| Re-reading | Re-readable within the retention window | Deleted messages can no longer be replayed from the queue |
| Parallelism | Partitions split among group members | Competing workers consume tasks in the chosen baseline setup |
| Ordering | Guaranteed within a partition | Business design must not rely on receive or completion order |
| Application failure | Uncommitted range can be re-read | Redeliverable once visibility timeout expires |
| Poison data | Requires an application strategy | Supports DLQ per delivery configuration |

Streaming is an append-only log and is replayable within retention. Per-partition ordering does not mean global stream ordering; events passing through Queue and multiple workers also do not preserve business completion order by default. See [Streaming Overview](https://docs.oracle.com/en-us/iaas/Content/Streaming/Concepts/streamingoverview.htm).

Consumer groups distribute partitions across dispatchers. Each instance needs a unique name; adding instances beyond the partition count adds no extra parallelism for that group. With `commitOnGet=true`, the next fetch commits the previous fetch's progress; the dispatcher must therefore finish handing off a batch before issuing the next fetch. See [Using Consumer Groups](https://docs.oracle.com/en-us/iaas/Content/Streaming/Tasks/using_consumer_groups.htm).

Queue returns a receipt so workers can update visibility or delete a message. A receipt belongs to a single delivery and does not replace `eventId`. Workers must use the receipt of the delivery currently being processed. Choosing an appropriate visibility timeout and long polling prevents premature redelivery or tight polling loops on an empty queue. See [Consuming Messages from a Queue](https://docs.oracle.com/en-us/iaas/Content/queue/consume-messages.htm).

A log line stating "message received" does not prove business success. An HTTP success status from a batch API also does not replace checking per-entry results when the API reports individual message outcomes.

## 5. Event Contract and Identifier Rules

### 5.1. Proposed Envelope

~~~json
{
  "eventId": "evt-lab-000001",
  "eventType": "OrderAccepted",
  "schemaVersion": 1,
  "occurredAt": "2026-11-01T03:15:00Z",
  "correlationId": "corr-lab-001",
  "orderId": "ORD-LAB-000001",
  "payload": {
    "customerId": "CUS-LAB-001",
    "amountMinor": 159000,
    "currency": "VND"
  }
}
~~~

`amountMinor` is an integer in the smallest currency unit defined by the application for each currency. For VND in this lab, the value above represents 159,000 VND. Avoid using `double` for monetary amounts.

Mandatory rules:

- The producer generates `eventId` once before the first publish; all retries reuse the exact ID and payload.
- `orderId` is used as the partition key when publishing to Streaming to group related events. This alone does not guarantee end-to-end ordering across the system.
- `schemaVersion` selects the parser; never infer the version from whichever fields happen to appear.
- Workers accept only `eventType=OrderAccepted`, supported versions, non-empty IDs, positive amounts, and currencies in the application's allowlist.
- ID length limits, UTF-8 byte sizes, and required fields must be validated before writing to the database.
- Payloads must not contain passwords, access keys, or personal data unnecessary for the task.

### 5.2. Distinguishing Identifier Types

| Value | Role | Used as Business Idempotency Key? |
| --- | --- | --- |
| `eventId` | Producer-managed event identity | Yes, paired with effect name |
| `orderId` | Business entity identity | May serve as an additional business constraint |
| Stream partition and offset | Transport position in the stream | Used for source tracing, not a replacement for event ID |
| Queue message ID | Copy identity inside Queue | No, republishing can create a new copy |
| Queue receipt | Lease handle for the current delivery | No |
| `correlationId` | Links logs across a processing flow | Not necessarily unique |

The dispatcher preserves raw UTF-8 JSON strings in the baseline version. This allows computing SHA-256 over the exact event string to detect an `eventId` reused with different content.

If any component parses and re-serializes JSON, property order or numeric formatting may change. In that case, agree on a canonicalization rule before hashing; never treat two byte-different JSON payloads as equal merely because they share an ID. Hashing detects content conflicts; it does not authenticate the sender's identity.

Name the effect `create-fulfillment:v1`. A bug-fix release producing the same business effect must keep this name during replays. Renaming the effect merely to bypass deduplication can trigger a second side effect.

## 6. Resource Preparation and Lab Configuration

### 6.1. Required Knowledge and Permissions

Learners need familiarity with Java, JDBC, HTTP, JSON, database transactions, and basic OCI IAM. Prepare a tenancy, a dedicated lab compartment, adequate resource quotas, administrator-delegated deployment permissions, and administrative Compute access.

Choose a region offering all required services. Verify provisioning capacity before generating load. Do not assume every tenancy receives free resources or identical quotas.

### 6.2. Minimum Inventory

| Component | Lab Starting Configuration | Details to Record |
| --- | --- | --- |
| Compartment | One dedicated capstone compartment | OCID, owner, cleanup date |
| VCN | Private subnet for apps and outbound HTTPS path | CIDR, route tables, NSGs |
| Streaming | One stream pool, one stream, 3 partitions, 24-hour retention | Stream OCID, messages endpoint |
| Queue | One queue, 24-hour retention, 60s visibility, 20s long poll | Queue OCID, messages endpoint, delivery threshold |
| Dispatcher | Initially one instance, then two instances | Group name, distinct instance names |
| Worker | One then two Java processes | Thread count, JDBC pool size, batch limit |
| Oracle Database | One application schema | TLS connection method, application account |
| Observability | Centralized logs and dashboard | Measurement window, alarm rules, log retention |

Set the initial delivery threshold to 5 in lab configuration if supported by the service. When testing the DLQ, cross-check actual status against active settings; do not assume a fixed API call count always matches the moment a message moves to the DLQ.

Retention periods must exceed expected outage duration, catch-up time, and a safety margin. The 24-hour retention here is solely for a short lab session.

### 6.3. Application Configuration

~~~properties
OCI_REGION=<lab-region>
STREAM_ID=<stream-ocid>
STREAM_MESSAGES_ENDPOINT=<stream-messages-endpoint>
STREAM_GROUP=fulfillment-dispatch-v1
STREAM_INSTANCE=dispatcher-a
STREAM_BATCH_LIMIT=10

QUEUE_ID=<queue-ocid>
QUEUE_MESSAGES_ENDPOINT=<queue-messages-endpoint>
QUEUE_VISIBILITY_SECONDS=60
QUEUE_POLL_SECONDS=20
QUEUE_BATCH_LIMIT=1

WORKER_EFFECT=create-fulfillment:v1
WORKER_THREADS=1
DB_JDBC_URL=<jdbc-url-tls>
DB_USER=<app-account>
DB_SECRET_REFERENCE=<secret-reference>
~~~

Start with queue batch size 1 to observe each delivery lifecycle clearly. Increase batch size and threads only after correctness is proven. If fetching 10 messages and processing sequentially, visibility for the last messages is already ticking from the moment the batch was received.

Obtain endpoints from resource details rather than constructing hostnames manually from region names. Queue has separate control-plane and messages endpoints; clients producing, consuming, updating, or deleting messages must target the queue's messages endpoint. See [Queue Messages Endpoint](https://docs.oracle.com/en-us/iaas/Content/queue/messages.htm).

## 7. IAM, Credentials, and Networking

### 7.1. Separating Three Application Runtime Roles

Create separate dynamic groups for producer, dispatcher, and worker Compute instances when running on OCI. Membership can bind to instance OCIDs; never lump every instance in the tenancy into one broad role for convenience.

Data-plane policy examples, where placeholders must be replaced with lab resources:

~~~text
Allow dynamic-group LabOrderProducers to use stream-push in compartment OciMessagingLab where target.stream.id = '<stream_ocid>'

Allow dynamic-group LabDispatchers to use stream-pull in compartment OciMessagingLab where target.stream.id = '<stream_ocid>'

Allow dynamic-group LabDispatchers to use queue-push in compartment OciMessagingLab where target.queue.id = '<queue_ocid>'

Allow dynamic-group LabFulfillmentWorkers to use queue-pull in compartment OciMessagingLab where target.queue.id = '<queue_ocid>'
~~~

`stream-push` and `stream-pull` separate publishing from reading the stream. `queue-push` isolates sending, while `queue-pull` covers receiving and delivery operations. Never grant resource create/delete privileges to application processes merely because they send or receive messages. See [Streaming Policy Reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/streamingpolicyreference.htm) and [Queue Policy Reference](https://docs.oracle.com/en-us/iaas/Content/queue/policy-reference.htm).

The examples above do not grant permission to read resource metadata, fetch secrets, or emit logs/metrics. If the application calls `GetQueue`, reads secrets from Vault, or pushes telemetry via SDK, add exact permissions for those capabilities. Endpoints can be injected via deployment config so runtime processes do not need metadata discovery.

IAM for Queue does not replace `INSERT` or `SELECT` privileges in the Oracle schema. The application account may access only required tables; table-creation and infrastructure-admin accounts must remain separate.

On Compute, use instance principals to avoid copying API private keys onto VMs. When running the producer on a personal workstation, use a lab-scoped OCI profile with matching permissions. Database passwords, wallets, and API keys must never be packaged into JARs, images, or source control.

### 7.2. Connectivity Paths Must Be Proven

For public Streaming and Queue endpoints, private subnets require an authorized outbound path such as a NAT Gateway, plus proper DNS and HTTPS egress. If using a private endpoint for a service, configure routes, DNS, and NSGs specifically for that endpoint; do not assume all services share the same private connectivity model.

Workers need a TLS path to the database. NSGs must allow only application sources and the active listener port. Administrative access goes through Bastion or an organization-approved administrative path.

Test two failure classes separately:

- Broken network or DNS: cannot connect, timeouts, unresolvable host.
- Broken authentication or authorization: requests reach the service but are denied.

Record request IDs returned by the service. Never change policies to tenancy-wide permissions to mask an endpoint or route-table error.

## 8. Structuring the Java Application

Use Java 17 or later and Maven for the lab application. Separate three entry points for independent deployment and scaling:

~~~text
producer       -> generate data, publish, save reconciliation manifest
dispatcher     -> read Streaming, forward to Queue, manage progress
worker         -> receive from Queue, validate, run JDBC transaction, delete delivery
shared         -> envelope, validation, error codes, and telemetry
~~~

Use OCI Java SDK 3.x with a specific version chosen by the team and pinned in build configuration. Core dependencies include:

| Dependency | Purpose |
| --- | --- |
| `com.oracle.oci.sdk:oci-java-sdk-bom` | Align versions across OCI SDK modules |
| `com.oracle.oci.sdk:oci-java-sdk-streaming` | Streaming client |
| `com.oracle.oci.sdk:oci-java-sdk-queue` | Queue client |
| `com.oracle.oci.sdk:oci-java-sdk-common-httpclient-jersey3` | HTTP transport chosen for examples |
| Oracle JDBC driver compatible with JDK and database | Database transactions |
| Project-selected JSON and logging libraries | Envelope parsing, structured logging |

In SDK 3.x, declare an appropriate HTTP transport in addition to service modules. The BOM prevents version mismatches across modules. See [Getting Started with the Java SDK](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkgettingstarted.htm).

The Java snippets below are **integration excerpts**, not complete runnable applications. Learners must add bootstrapping, configuration, JSON parsing, persistence, logging, and process supervision. Method names like `publishAndVerify` or `applyAtomically` are application contracts, not built-in OCI APIs.

Example creating a Queue client on Compute:

~~~java
import com.oracle.bmc.ClientConfiguration;
import com.oracle.bmc.auth.InstancePrincipalsAuthenticationDetailsProvider;
import com.oracle.bmc.queue.QueueClient;

var provider = InstancePrincipalsAuthenticationDetailsProvider.builder().build();

var clientConfig = ClientConfiguration.builder()
        .connectionTimeoutMillis(5_000)
        .readTimeoutMillis(35_000)
        .build();

QueueClient queue = QueueClient.builder()
        .endpoint(queueMessagesEndpoint)
        .configuration(clientConfig)
        .build(provider);
~~~

`queueMessagesEndpoint` comes from the real queue's configuration. Reuse the client over the process lifetime and close it on shutdown. Read timeout must accommodate configured long polling plus network latency; revisit timeouts if changing the long-poll duration.

Avoid wildcard-importing `streaming.requests` and `queue.requests` together because both define names like `GetMessagesRequest`. The dispatcher example uses fully qualified names to make the target service explicit.

## 9. Building the Producer and Input Reconciliation Ledger

The producer generates a reproducible event set, such as 1,000 valid orders with a run-scoped ID prefix. Before publishing, save the `eventId` list and corresponding hashes in a run manifest. This is acceptance data, not disposable logs discarded when the process exits.

Workflow:

~~~text
generate eventId + orderId + envelope
write envelope to input manifest
send to Streaming, key = UTF-8(orderId), value = UTF-8(envelope)
inspect publish result
    per-entry success -> record CONFIRMED with partition/offset if available
    per-entry explicit failure -> classify error and retry appropriately
    timeout or lost response -> record UNKNOWN, retry with same eventId and payload
~~~

Streaming returns per-entry results for `PutMessages`, including errors if an append fails. Therefore, the producer must never mark an entire batch successful based solely on HTTP status. See [PutMessagesResultEntry](https://docs.oracle.com/en-us/iaas/tools/java/3.72.1/com/oracle/bmc/streaming/model/PutMessagesResultEntry.html).

Do not Base64-encode JSON bytes into a string and pass that string as bytes into the Java SDK without an application-level reason. Distinguish wire payload representation from SDK data types; a mismatched double-encode/decode contract causes workers to receive corrupted content. Oracle's CLI examples use Base64 for message values in JSON input files. See [Publishing Messages](https://docs.oracle.com/en-us/iaas/Content/Streaming/Tasks/publishingmessages.htm).

When testing duplicate delivery, republish exact existing envelopes. When testing identity conflicts, send an envelope with modified content while keeping the same `eventId`. These are two distinct scenarios and must yield two distinct observed outcomes.

The manifest should distinguish:

- `CONFIRMED`: the producer received explicit success confirmation.
- `UNKNOWN`: the service may have accepted the request, but the producer does not know the outcome.
- `REJECTED`: confirmed failure that must not be counted as valid input.

At the end of the test, every ID in `UNKNOWN` must be reconciled or retried under control; never delete `UNKNOWN` entries from reports to inflate success rates.

## 10. Building the Dispatcher: Handoff First, Checkpoint Later

### 10.1. Baseline Flow

Choose `commitOnGet=true` and process batches synchronously in the initial version. Do not prefetch the next batch while the current batch still holds messages unacknowledged by Queue.

~~~java
import com.oracle.bmc.streaming.StreamClient;
import com.oracle.bmc.streaming.model.CreateGroupCursorDetails;
import com.oracle.bmc.streaming.requests.CreateGroupCursorRequest;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;

static void dispatch(
        StreamClient stream,
        String streamId,
        String groupName,
        String instanceName,
        Consumer<byte[]> publishAndVerify,
        AtomicBoolean running) throws InterruptedException {

    var details = CreateGroupCursorDetails.builder()
            .groupName(groupName)
            .instanceName(instanceName)
            .type(CreateGroupCursorDetails.Type.TrimHorizon)
            .commitOnGet(true)
            .build();

    String cursor = stream.createGroupCursor(
            CreateGroupCursorRequest.builder()
                    .streamId(streamId)
                    .createGroupCursorDetails(details)
                    .build())
            .getCursor().getValue();

    while (running.get()) {
        var response = stream.getMessages(
                com.oracle.bmc.streaming.requests.GetMessagesRequest.builder()
                        .streamId(streamId)
                        .cursor(cursor)
                        .limit(10)
                        .build());

        for (var message : response.getItems()) {
            // Return only after Queue confirms durable acceptance.
            // Unresolved errors must throw; never swallow exceptions.
            publishAndVerify.accept(message.getValue());
        }

        cursor = response.getOpcNextCursor();

        if (response.getItems().isEmpty()) {
            Thread.sleep(500);
        }
    }
}
~~~

The cursor is created with a stable group name and a distinct instance name per process. The group cursor creation snippet uses exact Java SDK fields. See [CreateGroupCursor in Java](https://docs.oracle.com/en-us/iaas/tools/java-sdk-examples/latest/streaming/CreateGroupCursorExample.java.html).

The next `GetMessages` call is the point where the previous batch may be committed. Assigning the `cursor` variable in Java does not commit progress on the service. If the process stops after successful forwarding but before the next fetch, the batch may be re-read and re-sent to Queue; workers must tolerate this.

Contract for `publishAndVerify`:

1. Validate size and decode bytes as valid UTF-8 without auto-repairing corrupt data.
2. Send the raw envelope to Queue using `PutMessages` against the messages endpoint.
3. Inspect the complete API response; never equate sending the request with success.
4. For ambiguous timeouts, allow retries with the same content and ID, accepting possible duplicates.
5. For unhandled errors, throw an exception so the loop does not advance to the next batch.

Queue accepts string content; the Streaming Java SDK returns message bytes. Decoding rules must remain consistent. Source metadata such as stream ID, partition, and offset can be logged or placed in a pre-designed wrapper, without losing event identity.

### 10.2. Recovery and Partially Failed Batches

Suppose the dispatcher reads 10 messages and forwards the first 6 before a network error occurs. Until the remaining 4 messages have durable handoff, the dispatcher must not issue the next fetch and accidentally commit the whole batch.

The initial version may exit the loop on failure, wait in a supervisor with backoff, and recreate the group cursor using the **same group name**. Messages already forwarded but not yet checkpointed may reappear. Never generate random group names on restart, as that alters read scope and breaks reconciliation.

When retrying at length within the same process, manage heartbeats and cursor lifetimes per the API. The snippet above omits heartbeats; it suits small batches and short handoffs. When partition ownership becomes uncertain, discard stale state and rejoin the group. Never keep committing on the assumption that the instance still owns the partition.

With manual commits, create the cursor with `commitOnGet=false` and call `ConsumerCommit` only after successful handoff, adopting the new cursor returned by the API. This is an advanced pattern requiring heartbeat, rebalance, and commit-error handling; never mix it into an auto-commit loop without redesigning. See [Committing Offsets Manually](https://docs.oracle.com/en-us/iaas/Content/Streaming/Tasks/commit-consumer-group.htm).

### 10.3. Poison Records Before Queue

If a message cannot be forwarded to Queue due to a permanent data defect:

- Baseline option: halt checkpoint progression, alert, and require operator intervention before retention expires.
- Extended option: store raw source data and the failure reason in a durable quarantine store keyed by stream position; only after durable storage succeeds is the record considered handed off.

Never log and skip. Logs may truncate payloads, expire, or be sampled, so they are not a recovery store.

## 11. Idempotent Transaction Design in Oracle Database

### 11.1. Minimum Schema

~~~sql
CREATE TABLE event_receipts (
    event_id        VARCHAR2(64 CHAR) NOT NULL,
    effect_name     VARCHAR2(64 CHAR) NOT NULL,
    payload_sha256  CHAR(64 CHAR) NOT NULL,
    processed_at    TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_event_receipts PRIMARY KEY (event_id, effect_name)
);

CREATE TABLE fulfillment_jobs (
    order_id         VARCHAR2(64 CHAR) NOT NULL,
    source_event_id  VARCHAR2(64 CHAR) NOT NULL,
    amount_minor     NUMBER(18, 0) NOT NULL,
    currency         VARCHAR2(3 CHAR) NOT NULL,
    job_status       VARCHAR2(32 CHAR) NOT NULL,
    created_at       TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_fulfillment_jobs PRIMARY KEY (order_id),
    CONSTRAINT uq_fulfillment_source UNIQUE (source_event_id),
    CONSTRAINT ck_fulfillment_amount CHECK (amount_minor > 0),
    CONSTRAINT ck_fulfillment_status CHECK (
        job_status = 'READY_FOR_FULFILLMENT'
    )
);
~~~

The application validates that amounts fit both Java `long` and the chosen `NUMBER(18,0)` precision. Each lab order has one valid acceptance event. If the same `orderId` arrives in a new event with different meaning, that is a business conflict to triage—never silently treat it as a duplicate message.

`event_receipts` also acts as the deduplication inbox. Purge inbox history only after bounding the full window during which replays or redrives may occur, including data stored outside Queue. Purging the inbox prematurely and then replaying alters deduplication guarantees.

### 11.2. Mandatory Persistence Layer Algorithm

~~~text
parse + validate envelope
compute SHA-256 per agreed canonical data rules
open JDBC connection, autoCommit = false

attempt INSERT event_receipts(eventId, effectName, hash)
    if unique violation specifically on receipt INSERT:
        rollback
        read existing receipt
        if hash differs -> identity conflict error, do not acknowledge success
        if hash matches -> return ALREADY_APPLIED
        if unreadable -> return retryable error
    if other error -> rollback, propagate error

INSERT fulfillment_jobs(...)
commit
return APPLIED

if any write or commit step fails:
    rollback if still possible
    propagate error; do not request Queue message deletion
~~~

Both inserts must share the **same connection and same transaction**. Never commit the receipt first and create the fulfillment job afterward. The database unique constraint resolves races when two workers process the same event concurrently; a Java-side `SELECT` before `INSERT` is insufficient to replace this constraint.

Handle unique-constraint violations strictly in the context of the receipt insert. If inserting into `fulfillment_jobs` violates `order_id` or `source_event_id`, roll back and investigate the business conflict; never catch all unique errors and return success.

When a commit times out, the application may not know whether the transaction succeeded. The worker leaves the message for redelivery; the next attempt uses the inbox to distinguish already-applied from unapplied. Never assume "commit threw an exception, so nothing was written."

### 11.3. Why Not Use Local Memory?

A `ConcurrentHashMap` tracks IDs only within one process, loses state on restart, and does not coordinate across instances. A local marker file is likewise not atomic with database changes. Memory may act as a read cache, but final decisions must rely on shared transactional state.

If adding a `FulfillmentPrepared` event emission after commit, use a transactional outbox: write business data and the outbox row in the same transaction, then let a separate publisher forward the outbox to the messaging service. The outbox publisher may still emit duplicates; downstream consumers still require idempotency. Never call external services mid-transaction assuming a database rollback will undo the call.

## 12. Building the Queue-Consuming Java Worker

### 12.1. Receive, Persist, Then Delete

The snippet below processes one delivery at a time to make the ordering clear:

~~~java
import com.oracle.bmc.queue.QueueClient;
import com.oracle.bmc.queue.requests.DeleteMessageRequest;
import com.oracle.bmc.queue.requests.GetMessagesRequest;

interface EffectStore {
    // Return only after APPLIED commits or ALREADY_APPLIED is verified.
    // Invalid data, conflicts, and infrastructure errors must throw.
    void applyAtomically(String envelope) throws Exception;
}

static void pollOnce(
        QueueClient queue,
        String queueId,
        EffectStore store) throws Exception {

    var response = queue.getMessages(
            GetMessagesRequest.builder()
                    .queueId(queueId)
                    .limit(1)
                    .timeoutInSeconds(20)
                    .visibilityInSeconds(60)
                    .build());

    for (var message : response.getGetMessages().getMessages()) {
        store.applyAtomically(message.getContent());

        queue.deleteMessage(
                DeleteMessageRequest.builder()
                        .queueId(queueId)
                        .messageReceipt(message.getReceipt())
                        .build());
    }
}
~~~

Queue's `GetMessagesResponse` wraps a `GetMessages` model, whereas Streaming's response holds an `items` list; the two types are not interchangeable despite sharing an operation name. See [Queue GetMessagesResponse](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/queue/responses/GetMessagesResponse.html) and [Streaming GetMessagesResponse](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/streaming/responses/GetMessagesResponse.html).

The outer loop calls `pollOnce`, classifies exceptions, emits telemetry, and applies bounded backoff. An exception during processing must never enter a `finally` block that unconditionally deletes the message. If the database commits but `DeleteMessage` fails, log an "uncertain ack" state; subsequent redelivery must return `ALREADY_APPLIED` and retry deletion using the new receipt.

### 12.2. Visibility Timeout and Long-Running Tasks

Suppose normal processing takes under 2 seconds, while occasional queries take 35 seconds. A 60-second visibility timeout is a reasonable lab starting point, later tuned from real measurements.

Budgeting starts at message receipt and covers executor queuing, processing, commit, short retries, and deletion:

~~~text
visibility
    > pre-processing queue wait
    + processing time accounting for tail latency
    + commit and delete time
    + safety margin
~~~

If a task exceeds the budget, the worker extends visibility before expiry using `UpdateMessage` with the active receipt. Updating alters visibility only; it does not substitute for business commit and cannot extend a message indefinitely past retention. See [Updating Message Visibility](https://docs.oracle.com/en-us/iaas/Content/queue/update-messages.htm).

A 3-minute task needs a dedicated renewal mechanism; scheduling a timer on the same thread blocked on JDBC will not guarantee the timer fires. When lease ownership can no longer be confirmed, let the active attempt fail safely or complete under inbox protection; never rely on visibility as the sole business lock.

### 12.3. Shutdown and Resource Bounds

Upon receiving a shutdown signal:

1. Stop polling for new tasks.
2. Allow in-flight tasks to finish within a configured grace period.
3. Delete only deliveries that committed or were verified as valid duplicates.
4. Leave remaining deliveries to become eligible for redelivery.
5. Close executors, connection pools, and SDK clients.

Limit concurrent in-flight messages to match thread count, connection pool size, and visibility. An unbounded executor queue can cause messages to expire before processing even starts, despite low average CPU.

## 13. Retries, DLQ, and Controlled Replay

### 13.1. Classifying Errors Before Retrying

| Error Class | Examples | Handling |
| --- | --- | --- |
| Transient | Network timeouts, throttling, brief DB interruption | Bounded retries with backoff and jitter; preserve event identity |
| Configuration or permissions | Wrong endpoint, bad credentials, missing IAM | Alert, throttle or pause polling; fix config before resuming |
| Permanent data defect | Malformed JSON, unsupported version, invalid amount | Do not hot-retry; route to DLQ or quarantine per design |
| Business conflict | Same event ID with different hash, conflicting order acceptance | Quarantine, preserve evidence, never report success as duplicate |
| Ambiguous outcome | Lost response on publish, commit, or delete | Reconcile or allow redelivery; rely on idempotency for safety |

Backoff formula to use:

~~~text
wait cap = min(cap, base × 2^attempt)
actual wait = random value between 0 and wait cap
~~~

For example, the lab sets `base=200 ms`, `cap=5 s` for short in-app retries. This is illustrative. Sum SDK and application retry budgets together; three layers all retrying aggressively can exceed visibility and exhaust JDBC connections.

If the database goes down for several minutes, a circuit breaker should throttle processing and pause polling. Continuing to pull the same messages while a dependency is definitely down increments delivery counts and pushes valid tasks into the DLQ.

### 13.2. DLQ Lifecycle

Queue provides a DLQ for messages exceeding the configured delivery threshold. Messages in the DLQ are still subject to retention; entering the DLQ is not permanent archival. Polling messages for inspection can also affect delivery counts, so avoid ad-hoc Console polling during test measurements. See [Dead Letter Queues](https://docs.oracle.com/en-us/iaas/Content/queue/deadletterqueues.htm) and [Consuming Messages Considerations](https://docs.oracle.com/en-us/iaas/Content/queue/consume-messages-queue.htm).

Redrive runbook:

1. Identify root cause: data defect, code bug, or infrastructure failure.
2. Record identifiers, hashes, timestamps, and handling rationale; minimize copying sensitive payloads.
3. Fix the root cause and validate against a small sample.
4. Republish valid events to the target queue at a rate-limited pace.
5. Preserve `eventId` and payload when reprocessing the same event.
6. Delete the DLQ entry only after target publication is confirmed.
7. Reconcile outcomes and watch for re-entry into the DLQ.

Crashing between target publish and DLQ deletion can create duplicates. The inbox mechanism protects the business effect, mirroring the dispatcher crash window.

If business rules require modifying the contents of an invalid event, create a corrective event with a new ID referencing the original. Never silently edit the payload while keeping the same ID, as that breaks the envelope's immutability contract.

### 13.3. Replaying from Streaming

Replays use a separate consumer group, such as `fulfillment-replay-run-01`, or explicit reads by partition and saved offset. Define the time range, source data, target queue, and maximum rate upfront.

For an existing group, do not assume passing `TrimHorizon` or a timestamp to cursor creation automatically resets the group's committed position. Use a new group or supported offset-update operations after assessing impact on active consumers.

Replaying an already-succeeded event set should increase delivery and duplicate-detection counts without increasing fulfillment jobs. Replay cannot recover messages past retention without an independent backup store.

## 14. Implementation Milestones and Verification Checkpoints

### Milestone 1: Infrastructure Preparation

Create the compartment and apply tags for owner, environment, project, and cleanup date. Provision networking, outbound paths, NSGs, stream pool, stream, queue, database schema, and permission groups.

You can deploy via Terraform with the OCI provider, directly or through OCI Resource Manager. Save input variables and necessary outputs such as OCIDs, endpoints, and subnets; protect state files because state may contain sensitive data. Never commit plaintext passwords in variables alongside source code.

This milestone passes when resources exist, endpoints are accurately captured, and reproducible configuration exists. Console screenshots alone do not prove repeatable infrastructure.

### Milestone 2: Per-Component Connectivity and Permission Checks

Verify the producer can publish one message, the dispatcher can read from the stream and push to Queue, and the worker can poll and connect to the database—each using its own identity.

Then test unauthorized actions against lab resources: the producer cannot consume Queue; the worker cannot publish to the stream or delete resources. Record denials along with request IDs where returned.

If all roles share a single Compute instance and the same instance principal, running three processes does not make them three independent IAM identities. Proving runtime privilege separation requires deploying on separate instances or using appropriate distinct identity mechanisms.

### Milestone 3: Completing a Single-Event Flow

Execute in order:

1. Initialize the schema and load configuration.
2. Start one worker.
3. Start one dispatcher with a fixed group name.
4. Publish one valid envelope.
5. Verify one receipt and one fulfillment job exist.
6. Verify the message is deleted from Queue after success.

At this milestone, keep batch size at 1 and avoid concurrency. Record `eventId`, partition/offset, Queue message ID, and transaction result for end-to-end tracing.

### Milestone 4: Proving Idempotency and Recovery

Republish the old envelope; record counts must not grow. Stop the worker after commit but before delete, then restart; record counts still must not grow. Stop the dispatcher after Queue acceptance but before checkpoint; re-forwarded records still produce only one effect.

### Milestone 5: Scaling Load and Operations

Scale workers, run controlled fault injections, measure backlog, run redrive/replay, and document optimal settings within the chosen budget. Whenever changing batch sizes or concurrency, re-measure visibility and connection pools.

Learners must supply build commands, run commands for all three entry points, and deployment configurations matching their own application. Excerpts in this guide do not substitute for those reproducible deliverables.

## 15. Lab Acceptance Suite

### 15.1. Standard Test Dataset

Create a run with a dedicated ID prefix containing:

- 1,000 valid events, each for a distinct order.
- 100 duplicate publishes of existing valid envelopes, byte-for-byte identical.
- 10 business-invalid events with distinct IDs, such as `amountMinor=-1`.

Expected total publishes: 1,110; logical events: 1,010, of which 1,000 are valid and 10 are intentionally invalid. Retries from infrastructure faults may raise the actual transport count. Track every record via the manifest rather than treating API call counts as order counts.

Once the system stabilizes:

- Exactly 1,000 receipts exist for effect `create-fulfillment:v1` across the valid set.
- Exactly 1,000 fulfillment jobs match published IDs and data.
- The 10 invalid events produce no jobs and are accounted for in the DLQ or designed error store.
- Duplicates produce no extra results.
- Zero valid IDs remain unexplained in reconciliation.

If `UNKNOWN` entries remain in the manifest, input coverage is incomplete. Resolve them or explicitly record them as test limitations.

### 15.2. Fault-Injection Matrix

| Scenario | Lab Injection Method | Acceptance Signal |
| --- | --- | --- |
| Same event published twice | Reuse envelope | Jobs unchanged, duplicate counter increments |
| Dispatcher crashes after enqueue | Inject failpoint after successful publish and before next get | Redelivery may occur; zero duplicate jobs |
| Worker crashes before commit | Failpoint before commit, then terminate process | Incomplete transaction rolls back; message redelivered |
| Worker crashes after commit | Failpoint right after store returns, before delete | Next delivery detects already applied |
| Task exceeds visibility | Inject processing delay | Redelivery may occur; inbox protects data |
| Visibility renewal | Enable extender for long task | Unintended redeliveries drop; renewal logs recorded |
| Database outage | Time-bound connectivity block in lab | No delete before commit; processes on recovery or via redrive plan |
| Queue temporarily unreachable | Block dispatcher egress | Stream does not checkpoint past unhanded batch |
| Unsupported message version | Send unsupported version | No job created; error classified and routed |
| Same event ID, different content | Alter amount while keeping ID | Conflict detected, not treated as valid duplicate |
| Scale dispatcher up or down | Add/remove instance names in same group | Rebalance may occur, zero lost results |
| Replay processed data | Dedicated replay group, preserve event ID | Fulfillment jobs unchanged |

Failpoints should target a single test `eventId` and deactivate after firing once. Never inject faults by deleting shared resources or disabling broad tenancy permissions.

Stopping a process at an exact point yields stronger evidence than random kills claimed to cover a fault window. Capture pre-failpoint logs and post-recovery verification.

### 15.3. Set-Based and Content-Based Reconciliation

Let:

- `V` be the set of valid IDs confirmed or successfully reconciled at input.
- `D` be the set of IDs with matching-effect receipts in the database.
- `J` be the set of source IDs for fulfillment jobs in the run.

At completion:

~~~text
V \ D = empty
D \ V = empty
D = J
job contents match orderId, amountMinor, and currency in the manifest
~~~

Compare ID sets first, counts second. Both sides having 1,000 rows can still hide one missing ID and one extra ID.

Example queries scoped to the run prefix:

~~~sql
SELECT COUNT(*) AS receipt_count
FROM event_receipts
WHERE effect_name = 'create-fulfillment:v1'
  AND event_id LIKE 'evt-run01-%';

SELECT COUNT(*) AS job_count
FROM fulfillment_jobs
WHERE source_event_id LIKE 'evt-run01-%';

SELECT event_id
FROM event_receipts
WHERE effect_name = 'create-fulfillment:v1'
  AND event_id LIKE 'evt-run01-%'
MINUS
SELECT source_event_id
FROM fulfillment_jobs
WHERE source_event_id LIKE 'evt-run01-%';
~~~

Check the reverse set difference and cross-check the manifest in your acceptance script. The `MINUS` query above finds only receipts lacking jobs; it does not prove all producer-sent events were received.

## 16. System Observability and Performance Targets

### 16.1. Minimum Dashboard

The names below are **recommended application metrics**, not guaranteed built-in OCI metric names.

| Metric | Question to Answer |
| --- | --- |
| `producer_confirmed_total` | How many publishes have been confirmed? |
| `producer_unknown_total` | How many requests have unknown outcomes? |
| `dispatcher_forwarded_total` | How many handoffs has Queue confirmed? |
| `dispatcher_forward_error_total` | What categories do handoff errors fall into? |
| `worker_delivery_total` | How many deliveries were received, including duplicates? |
| `worker_applied_total` | How many new effects committed? |
| `worker_duplicate_total` | How many content-identical duplicates were verified? |
| `worker_conflict_total` | Are any same-ID, different-payload conflicts occurring? |
| `worker_ack_error_total` | Did any commits succeed while Queue deletion failed? |
| `worker_processing_seconds` | What are p50, p95, and p99 processing latencies? |
| `pipeline_end_to_end_seconds` | How long from event creation to persisted business effect? |
| `db_connection_wait_seconds` | Are threads stalling on the connection pool? |

Add visible/in-flight counts for the queue and DLQ from service APIs/metrics. Queue statistics are approximate while producers and consumers remain active; use the database and manifest for final reconciliation. See [Queue Statistics](https://docs.oracle.com/en-us/iaas/Content/queue/queue-statistics.htm).

For Streaming, track lag via service metrics or age of unprocessed records. Never treat offsets as exact message counters, and do not assume subtracting two offsets always equals the remaining record count.

Logs should include component, instance, event ID, correlation ID, source position if known, Queue message ID, delivery count if available, outcome, error code, and request ID. Never use unbounded event IDs as metric dimensions; use logs to trace individual IDs. Never log full receipts, secrets, wallets, or customer payloads.

### 16.2. Targets for the Standard Run

Reasonable initial targets:

- Error-free run: 1,000 valid events complete within 5 minutes.
- Warm system with zero backlog: p95 from event creation to commit under 5 seconds.
- Single worker stopped: system continues making progress and drains remaining work after recovery within the test window.
- Any data discrepancy during reconciliation fails acceptance.

These are learning benchmarks. Reports must record Compute shapes, worker count, partition count, message size, batch sizes, database limits, and test duration. Cross-host end-to-end latency timestamps require clock synchronization; measure intra-process durations with monotonic clocks.

### 16.3. Estimating Capacity and Backpressure

Let `lambda` be the arrival rate, `mu` be the average processing rate per worker, and `N` be the number of workers. For backlog to drain while input continues arriving:

~~~text
N × mu > lambda
approximate catch-up time = backlog / (N × mu - lambda)
~~~

For example, with 40 messages/second arriving and each worker handling 25 messages/second, two workers provide 50 messages/second capacity. A backlog of 3,000 messages takes roughly 300 seconds to drain under an ideal model. Database latency, retries, and contention can lengthen real recovery times.

Without spare capacity, raising retention only delays message expiration. You must throttle publishing, scale the actual bottleneck, or optimize processing.

Never scale workers indefinitely: once the database saturates, adding threads increases connection waits, timeouts, and redeliveries. Bounding prefetch and in-flight task counts establishes controlled backpressure.

## 17. Operations Runbook and Availability

### When Backlog Grows

1. Isolate the bottleneck to Streaming-to-Queue, Queue-to-worker, or the database.
2. Read arrival rate, completion rate, error counts, in-flight counts, and JDBC wait times.
3. Compare estimated catch-up time against remaining retention.
4. Throttle upstream load or scale the true bottleneck component.
5. Verify backlog actually shrinks after the change.

If Queue holds few messages while stream event age rises, adding workers usually will not fix a dispatcher lacking permissions or failing to reach Queue.

### When the DLQ Grows

Pause bulk redrive, inspect a controlled sample, classify errors, and identify the associated release. If valid messages entered the DLQ due to a database outage, restore the dependency first and redrive at a bounded rate. Never simply raise the delivery threshold to mask persistent failures.

### When an Instance Fails

Run two dispatchers on two Compute instances with the same group and distinct instance names. Run workers across separate instances as well; select fault domains or availability domains appropriate to your region and infrastructure design.

Two processes on one host test concurrency, not machine-loss survival. Managed messaging services also do not eliminate single points of failure in application code, database connectivity, secrets, or deployment procedures.

The database must be restored consistently across both the inbox table and the business table. Restoring one table to a different point in time than the other can yield an "already processed" state missing its business effect, or allow re-application.

### When Retention Expires or Source Copies Are Lost

Determine what remains in the stream, queue, DLQ, manifest, and independent backups. Report the recoverable scope, reconcile affected IDs, and apply business remediation workflows as needed. Never claim zero data loss merely because worker logs show no exceptions.

## 18. Automation, Releases, and Cost Control

Package producer, dispatcher, and worker with explicit artifact versions. Deployment workflows should include config checks, backward-compatible schema migrations, small-sample smoke checks, and post-release metric verification.

During upgrades, prioritize compatibility with all event versions currently in flight. Never drop support for an older schema while the stream, queue, or DLQ still holds events of that version. Application rollbacks must also remain compatible with the deployed database schema.

Track costs by component:

| Component | Factors to Measure and Bound |
| --- | --- |
| Streaming | Partitions, throughput, retention per applicable billing rules |
| Queue | Request counts, retries, empty polls, message size |
| Compute | Instance count, CPU/RAM shape, uptime, boot volumes |
| Database | Compute sizing, storage, backups, and connection count |
| Networking | Egress, NAT, and associated traffic per actual topology |
| Observability | Log volume, retention, and metric/dimension counts |

Use applicable region and tenancy rate cards when estimating; never treat illustrative figures as pricing commitments. Set lab budgets, usage alerts, and load-generator caps inside project tooling. A budget alert does not act as an automatic producer kill-switch unless automation enforces it.

Tear down resources in controlled order:

1. Stop the producer and record final manifest state.
2. Let the system drain or archive what must be retained.
3. Stop dispatchers, workers, and auto-restart mechanisms.
4. Save required evidence, then delete lab-dedicated resources per your recorded inventory.
5. Check remaining billable resources such as volumes, databases, backups, endpoints, or logs.
6. Revoke permissions and credentials created solely for the project.

Never delete the stream or queue before completing reconciliation and then rely on the database alone as sole proof of all inputs.

## 19. Handover Package and Grading Rubric

The learner's submission includes source code for all three components, pinned dependencies/versions, build and run instructions, reproducible infrastructure definitions, schema, sanitized sample configs, manifests, fault-test results, dashboards, and runbooks.

The report must answer three questions with evidence: what the system received, what effects it produced, and how each break point between two components recovers.

| Category | Max Points | Evidence |
| --- | ---: | --- |
| Contract and architecture | 15 | Service roles, IDs, ack boundaries, retention assumptions |
| Producer and dispatcher | 20 | Per-entry results, stable cursor/group, handoff before checkpoint |
| Worker and data correctness | 25 | Atomic inbox + business transaction, hash conflicts, delete after commit |
| Fault injection and recovery | 15 | Failpoints, replay/redrive, ID and content reconciliation |
| IAM and networking | 10 | Distinct roles, negative permission tests, restricted connectivity |
| Observability, deployment, and cost | 15 | Metrics, reproducible config, load results, runbook, resource teardown |
| **Total** | **100** | |

The project passes only when zero unexplained data discrepancies remain and recovery is proven across two critical windows: dispatcher crash after enqueue before checkpoint, and worker crash after commit before delete.

Blocking defects requiring remediation before acceptance, regardless of total score: deleting messages before commit; skipping bad messages and advancing checkpoints; treating all unique-constraint errors as valid duplicates; or claiming end-to-end exactly-once guarantees without scoping transaction boundaries.

## 20. Post-Baseline Extensions

Pick one extension while preserving the full data-correctness verification suite:

- Add an independent consumer group to build a reporting projection without altering the dispatcher group.
- Add a transactional outbox to emit downstream business results, then test crashing after publish before marking the outbox row.
- Support multi-event order lifecycles using sequence/version numbers and state-transition rules; test out-of-order arrivals.
- Archive source payloads for recovery beyond retention, with a catalog and safeguards against accidental replay.
- Autoscale workers from backlog depth while respecting database connection limits.
- Execute a database restore drill and verify inbox consistency with business tables.

Every extension must state its new invariant, observability signals, and failure scenarios. Capstone mastery is shown by being able to explain and reproduce fault-recovery outcomes, along with tracing a message from producer acceptance through durable persistence of its business effect.
