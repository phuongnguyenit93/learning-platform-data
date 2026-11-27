# Adapter Configuration Checklist Before Production Deployment in Spring Integration

> **Chapter:** Production  
> **Lesson:** Pre-deployment adapter configuration checklist  
> **Module:** Spring Integration Adapters  
> **Scope:** Inbound/outbound adapters, gateways, pollers, MessageChannel, and connections for File, SFTP, HTTP, JMS, AMQP, Kafka, and databases.

## 1. Objectives and Expected Outcomes

After this lesson, you will be able to:

1. Distinguish the roles and operational behavior of inbound adapters, outbound adapters, gateways, pollers, and MessageChannel.
2. Review minimum configurations for message contracts, timeouts, retries, idempotency, acknowledgements, transactions, dead-lettering, and backpressure.
3. Build dedicated checklists for File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC adapters.
4. Verify TLS, authentication, secrets, access permissions, resource limits, startup/shutdown, and multi-replica deployments.
5. Demonstrate safe handling across failure windows: processing succeeded before ack, timeout after side effect, partial file upload, or pod crash mid-transaction.
6. Build an evidence-backed test plan, dashboard, runbook, go/no-go criteria, and rollback plan.

**Cross-cutting scenario:** A Spring Boot service receives order files via SFTP, normalizes them into messages, writes to a database, and publishes Kafka events. Other flows call partner APIs over HTTP, read JMS/AMQP queues, or poll JDBC. It works locally, but production has multiple pods, unstable networks, and slow downstreams. The checklist must ensure no data loss, no duplicate business processing, and full investigability and recoverability.

**Version scope:** This lesson presents broadly applicable principles. Class names, methods, Spring Integration DSL properties, and broker/client capabilities may vary across Spring Integration, Spring Boot, and target system versions. Illustrative examples must be verified against the **actual project version** before going to production.

## 2. Pre-Deployment Go/No-Go Gates

Each item requires an **owner, test evidence, and PASS/FAIL status or an approved exception**.

| Gate | Review Question | Evidence |
|---|---|---|
| **G1 — Contract** | Are payload/header/schema/data limits clear? | Schema, examples, and contract tests |
| **G2 — Delivery** | When is a message considered successfully received/processed/acked? | Commit/ack diagram and crash tests |
| **G3 — Idempotency** | Do retries and replays cause repeated side effects? | Business key, unique constraint, tests |
| **G4 — Timeout** | Are connect, read, gateway reply, session, and poll timeouts bounded? | Configuration and timeout drills |
| **G5 — Retry** | Are retry owner, backoff, max attempts, and error classification defined? | Retry plan, rate limit/network tests |
| **G6 — Error path** | Where do failed messages go, who can replay them, and when to alert? | Error flow, DLQ/quarantine, runbook |
| **G7 — Transaction** | Are DB/broker/file/API boundaries defined? | Transaction diagram and failure matrix |
| **G8 — Capacity** | Are queues, threads, pollers, and connection pools bounded? | Load tests, sizing, backlog policy |
| **G9 — Security** | Are TLS, host keys, secrets, ACLs, and PII protected? | Security signoff, rotation tests |
| **G10 — Observability** | Are logs/correlation, metrics, dashboards, and alerts in place? | Dashboards and alert drills |
| **G11 — Lifecycle** | Do rolling deploys/restarts/shutdowns preserve messages? | Graceful shutdown and crash tests |
| **G12 — Operations** | Are owner, canary, pause/resume, rollback, and runbooks ready? | Operational signoff and go/no-go record |

Three questions must be answerable before production: **(a) where are messages durably held; (b) who is responsible for retrying on failure; (c) upon retry, what prevents business effects from being duplicated?**

Deployment must not proceed if core risks such as uncontrolled data loss, insecure credentials, or undefined ack/commit boundaries still exist.

## 3. Identifying the Right Endpoint Type and MessageChannel

Spring Integration connects **Messages** (payload + headers), **MessageChannels**, and endpoints into integration flows.

| Component | Role | Operational Checklist |
|---|---|---|
| **Inbound channel adapter** | Converts external events/resources into messages; one-way contract with no reply | Source, checkpoint, poller/listener, filter, retry |
| **Outbound channel adapter** | Sends messages to an external system, typically one-way | Timeout, result confirmation, idempotency, side effects |
| **Inbound gateway** | Receives a request and returns a reply via IntegrationFlow | Reply timeout, status/error mapping, request limits |
| **Outbound gateway** | Calls an external endpoint and waits for a reply | Correlation, timeout, retry, duplicate requests |
| **Poller** | Reads a source on a schedule, optionally in batches | Scheduling, max messages, transaction, pause |
| **Transformer** | Transforms the message contract | Schema, charset, type, header propagation |
| **Filter/Router** | Filters/selects processing branches | Rules, fallback, discarded messages, audit |
| **Service activator/handler** | Executes business logic and side effects | Idempotency, transaction, error boundary |
| **Error flow** | Receives and handles errors per configured mechanism | ErrorMessage, retry, quarantine, alert |

### 3.1. Channels and Processing Boundaries

| Channel | Characteristics | Risks to Test |
|---|---|---|
| `DirectChannel` | Invokes handler synchronously on the sender thread | Slow handlers block the source thread; exceptions can propagate back to the caller |
| `ExecutorChannel` | Dispatches processing via TaskExecutor | Transaction context does not automatically cross threads; queue/thread saturation, ordering |
| `QueueChannel` | Buffers messages for a poller/consumer to fetch | In-memory queues are not durable across restarts by default; capacity/MessageStore |
| `PublishSubscribeChannel` | Sends to multiple subscribers | Behavior when one branch fails, duplicate/missed branch delivery risks |
| `PriorityChannel` | Prioritizes according to a defined comparator/value | Starvation, execution order differing from input order |

**Do not confuse asynchronous with durable.** An in-memory `ExecutorChannel` or `QueueChannel` can decouple processing speeds, but it does not by default guarantee messages survive a process crash. If durability is needed, design a persistent `MessageStore` or appropriate broker/transaction and verify it with tests.

### 3.2. Flow Review Diagram

~~~mermaid
flowchart LR
    EXT["File / SFTP / HTTP / JMS / AMQP / Kafka / JDBC"] --> IN["Inbound endpoint"]
    IN --> CH["MessageChannel"]
    CH --> VALID["Validate / normalize"]
    VALID --> DEDUPE["Idempotency check"]
    DEDUPE --> BIZ["Business transaction"]
    BIZ --> OUT["Outbound adapter / gateway"]
    OUT --> DEST["Target system"]
    VALID -. "Payload invalid" .-> Q["Quarantine / DLQ"]
    BIZ -. "Temporary error" .-> RETRY["Bounded retry + backoff"]
    RETRY -. "Exhausted" .-> Q
    Q --> OPS["Alert / replay runbook"]
    IN --> OBS["Metrics / tracing"]
    DEST --> OBS
~~~

This diagram illustrates **logical** responsibilities; it does not imply that file, HTTP, DB, and broker all participate in a single ACID transaction. The review must pinpoint the exact moments of "received", "durably stored", "processed", "sent", and "acknowledged by target".

## 4. Message Contract and Idempotency

### 4.1. Contract Checklist

- [ ] Payload format is defined: JSON/XML/CSV/binary/file reference/POJO and encoding.
- [ ] Schema/version, required fields, null/absent/empty semantics, and size limits are specified.
- [ ] Business key, correlation ID, trace context, source, tenant, and timestamp are defined.
- [ ] A **stable idempotency key across retries/replays** is chosen; do not rely by default on newly generated `MessageHeaders.ID`.
- [ ] Validation runs before producing any business side effects.
- [ ] Header propagation across HTTP/JMS/AMQP/Kafka/file is explicitly designed; do not assume every transport preserves headers intact.
- [ ] Contracts cover ordering, timestamps, versioning, and late-arriving events.
- [ ] Policies define which sensitive data may be logged or transmitted.
- [ ] Producer and consumer run contract tests whenever schemas change.

Example of an **application** envelope, not a default Spring Integration schema:

~~~json
{
  "schemaVersion": "1.0",
  "eventId": "evt-order-98765-v3",
  "eventType": "OrderSubmitted",
  "source": "partner-sftp",
  "occurredAt": "2026-11-23T08:00:00Z",
  "tenantId": "tenant-a",
  "correlationId": "corr-101",
  "payload": {
    "orderId": "ORD-98765",
    "revision": 3,
    "amount": 500000,
    "currency": "VND"
  }
}
~~~

A deduplication key can be `(source, eventId)` or `(tenant, orderId, revision)` **if the business contract guarantees uniqueness**. File names or correlation IDs do not inherently satisfy that requirement.

### 4.2. Delivery Semantics

| Guarantee Level | Meaning | Mitigation / Mechanism |
|---|---|---|
| **At-most-once** | No redelivery attempt in the processing path; messages may be lost on failure | Use only when business accepts potential loss |
| **At-least-once** | Messages may be redelivered if not acknowledged | Idempotent consumer, bounded retries |
| **Business effectively-once** | Business impact is not duplicated even when messages are redelivered | Unique key, transaction, processed-events table |
| **Scoped exactly-once** | Supported by certain platforms with transactions and specific semantics | State exact scope; do not extrapolate across HTTP/DB/file |

**Mandatory failure window to test:** The consumer writes to the DB successfully, then crashes before committing the Kafka offset or acknowledging JMS/AMQP. The source redelivers; without DB-level idempotency, an order could be created twice.

### 4.3. Idempotent Processing Pattern

~~~text
handle(message):
    validateContract(message)
    key = stableBusinessKey(message)

    begin db transaction
        if key already processed:
            commit
            return ALREADY_DONE
        applyBusinessChange(key)
        recordProcessedKeyWithUniqueConstraint(key)
        appendOutboxEvent(key, outputEvent)
    commit db transaction

    # Outbox publisher sends the event per retry policy.
    # Ack/checkpoint the source according to the defined contract.
~~~

This pseudocode omits transaction isolation and race condition details. In production, a **unique constraint** or proper locking is required—not just a SELECT before INSERT. If the DB commits but Kafka publishing fails, a transactional outbox records the obligation to publish later. A local database transaction does not automatically span HTTP, SFTP, and brokers.

### 4.4. Transaction/Ack Checklist

- [ ] Identify who acks/commits and when.
- [ ] Handle crashes **before side effect**, **after side effect but before ack**, and **after ack**.
- [ ] Never ack before business completion criteria are met.
- [ ] Outbound side effects have idempotency or reconciliation/compensation mechanisms.
- [ ] Per-target outcomes are tracked when one message fans out to multiple external systems.
- [ ] Test retries, replays, and concurrent duplicates across multiple consumers.
- [ ] Do not claim "end-to-end exactly-once" unless the entire scope is proven.

## 5. Poller, Scheduler, and Resource Limits

### 5.1. Poller Checklist

- [ ] Choose fixed delay, fixed rate, or cron based on data cadence and source capacity.
- [ ] Set a per-poll message limit such as `maxMessagesPerPoll` when supported by the endpoint.
- [ ] Ensure pollers do not busy-loop when the source is empty or experiencing network errors.
- [ ] Control concurrency, scheduler pool size, scan duration, and total inflight count.
- [ ] With multiple replicas, implement source partitioning, distributed claim/lock, or an equivalent mechanism.
- [ ] Verify transaction boundaries during polling and downstream processing.
- [ ] Provide exception handling, retry, alerting, and pause/resume capability.
- [ ] Persist checkpoint/metadata state across restarts if required by the flow.
- [ ] Test network timeouts, unresponsive sources, large batches, and poison inputs.
- [ ] Configure graceful shutdown to stop fetching new items while safely handling inflight work.

**Fixed delay** and **fixed rate** differ in scheduling semantics; verify against your application's scheduler and version. Do not use overly aggressive polling to mask throughput issues: when downstream slows down, batches pile up and increase resource pressure.

### 5.2. File Ingress Java DSL Example

~~~java
@Configuration
class FileIngressConfig {

    @Bean
    MessageChannel incomingFiles() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow fileIngressFlow() {
        return IntegrationFlow
                .from(
                    Files.inboundAdapter(new File("/srv/orders/ready"))
                         .patternFilter("*.ready"),
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofSeconds(5))
                               .maxMessagesPerPoll(10)
                    )
                )
                .channel("incomingFiles")
                .get();
    }
}
~~~

This example demonstrates the **inbound adapter → poller → MessageChannel** relationship; it is not production-ready on its own. You must add imports and verify APIs for your version, add a persistent filter/claim, verify completed file uploads, add handlers, retries, error flows, archiving, metrics, and multi-replica coordination. `DirectChannel` is not a durable queue.

### 5.3. Channel and Executor Checklist

| Question | Review Criterion |
|---|---|
| Is the handler CPU-bound or I/O-bound? | Size concurrency according to load and connection pools |
| Is there a new thread boundary? | Do not assume transactions from DirectChannel propagate across ExecutorChannel |
| Does the queue have bounded capacity? | Prevent memory exhaustion when downstream is slow |
| Is the queue in-memory or persistent? | Test restart and recovery according to the MessageStore type |
| What happens when the queue is full? | Controlled backpressure, pause, or rejection |
| Are there ordering requirements? | Prevent async concurrency from breaking business order |
| Who retries when the handler fails? | Document synchronous exceptions vs asynchronous error flows |
| Is there a wait time limit? | Prevent threads from blocking indefinitely |

## 6. Retry, Error Flow, and DLQ/Quarantine

### 6.1. Error Classification

| Category | Examples | Response Strategy |
|---|---|---|
| **Transient** | Network timeout, connection reset, 503, broker reconnect | Bounded retry with backoff and jitter |
| **Overload** | HTTP 429, DB pool exhaustion, broker throttling | Throttle rate, honor Retry-After policies where applicable |
| **Permanent** | Schema mismatch, invalid business rules | Quarantine/DLT; do not retry indefinitely |
| **Authentication/security** | 401/403, invalid certificate, wrong SFTP host key | Alert and fix config/permissions; do not bypass |
| **Duplicate** | Event already processed with the same business key | Idempotent no-op or conflict handling |
| **Poison message** | Record causing repeated exceptions | Bounded retry, dead-lettering, and replay runbook |

**Avoid cascading retries.** If the HTTP client, retry advice, and broker each retry multiple times, total side effects can far exceed expectations. Designate a **primary retry owner** and calculate the maximum total invocation count.

### 6.2. Spring Integration Error Mechanism

Spring Integration supports `ErrorMessage`, error channels, and endpoint-specific handlers/advices, but **does not guarantee all exceptions automatically route to the same errorChannel**:

- With `DirectChannel`, exceptions can propagate back to the sender and drive rollback/ack at the source.
- With `ExecutorChannel`, pollers, or async listeners, identify the exact error flow and error handler in use.
- An error handler that only logs and swallows exceptions can cause upstream to treat the operation as successful, depending on the execution path.
- `errorChannel` does not automatically provide a DLQ, automatic retries, or message persistence.
- Specify clearly when an exception is rethrown for source redelivery versus recovered after durable persistence to quarantine.

### 6.3. DLQ/Quarantine Checklist

- [ ] Failed messages are stored with appropriate retention and ACLs.
- [ ] Record business key, source, failed handler, reason, attempts, timestamp, and correlation ID.
- [ ] Separate data errors from infrastructure errors to prevent misguided replays.
- [ ] Never store Authorization headers, passwords, raw tokens, or unnecessary PII.
- [ ] Track metrics for size, age, arrival rate, alerts, and ownership.
- [ ] Maintain a small-batch replay runbook that checks idempotency and ordering.
- [ ] Define deletion/retention procedures and audit logs for operational actions.
- [ ] Verify poison messages cannot trigger a retry storm.

## 7. Security and Shared Configuration Management

### 7.1. Security Checklist

- [ ] Never hard-code secrets/tokens/private keys in source code, committed config files, or container images.
- [ ] Use a secret manager or secure mount; restrict file read permissions to the required service identity.
- [ ] Define owner, rotation, expiry, and revocation workflows for every credential.
- [ ] Validate TLS certificates/hostnames/chains; never disable verification because production setup is difficult.
- [ ] For SFTP, verify server host keys against trusted known-hosts or an approved mechanism.
- [ ] Grant each adapter least-privilege access to specific paths, queues, exchanges, topics, databases, or APIs.
- [ ] Enforce appropriate network ingress/egress controls and rate limits.
- [ ] Never log full payloads containing PII, passwords, cookies, Authorization headers, or private keys.
- [ ] Externalize configuration per environment and validate required properties before startup.
- [ ] Test credential rotation and expired/mismatched certificates.

### 7.2. Example Application-Defined Properties

~~~yaml
app:
  integration:
    ingress:
      enabled: true
      fixed-delay: 5s
      max-messages-per-poll: 10
      max-inflight: 50
    retry:
      max-attempts: 4
      initial-backoff: 1s
      max-backoff: 15s
    timeout:
      connect: 5s
      read: 20s
      request: 30s
    quarantine:
      enabled: true
      retention: 7d
    sftp:
      host: SFTP_HOST_FROM_ENV_OR_SECRET
      username: SFTP_USER_FROM_ENV_OR_SECRET
      private-key-path: /etc/app/ssh/id_ed25519
      known-hosts: /etc/app/ssh/known_hosts
~~~

**Important:** This is an **illustrative application property structure**, not a list of properties automatically recognized by Spring Integration/Spring Boot. You need a binding/validation class that wires these fields to actual adapters/clients. These numbers are also not universal SLOs for every system.

## 8. File Adapter: Pre-Production Checklist

### 8.1. File Inbound

- [ ] Directories have clear ownership, permissions, mounts, disk capacity, inode limits, and retention.
- [ ] Producers write a temporary file then rename/place a marker only upon completion; consumers never read partially written files.
- [ ] File patterns, charset, max file size, row count, and schema are validated.
- [ ] Deduplication is in place; **an in-memory filter alone is insufficient** when state must survive restarts or multiple replicas.
- [ ] A persistent metadata store or distributed claim/lock is configured per design.
- [ ] A business idempotency key ensures reprocessing a file after a crash does not duplicate effects.
- [ ] Lifecycle states (ready/processing/done/failed or equivalent) are tracked.
- [ ] Files are archived/deleted only after processing obligations and recovery guarantees are met.
- [ ] Invalid/failed files are quarantined with a replay runbook.
- [ ] Tested against slow producers, oversized files, duplicate filenames, modified files with the same name, and pod restarts.
- [ ] If using shared volumes, rename/lock semantics are tested on the actual filesystem.

### 8.2. File Outbound

- [ ] Target filename, path, write permissions, and existing-file behavior are defined.
- [ ] Use temporary filename + rename when downstream consumers must only read complete files.
- [ ] Include checksums/record counts or manifests if required by the business contract.
- [ ] Retries must not write two file versions that duplicate business effects.
- [ ] Verify behavior on disk full, permission denied, I/O errors, and cleanup.
- [ ] Distinguish between "file written" and "source message acknowledged".

**Failure drill:** File write succeeds, but the app crashes before DB commit/ack. After restart, there must be a way to determine whether the file needs rewriting—do not assume a shared transaction protects both.

## 9. SFTP Adapter: Pre-Production Checklist

### 9.1. SFTP Inbound

- [ ] Remote host/port/user/path, local cache/path, and owners are externalized.
- [ ] Host keys are verified; known-hosts has an update/rotation procedure.
- [ ] Private keys/credentials are managed via a secret store, never logged or baked into images.
- [ ] Connect/session/read timeouts and bounded reconnect/backoff are configured.
- [ ] Session factory/cache/pool is sized for concurrent transfers.
- [ ] Remote and local file filters are configured; use persistent metadata when deduplication must survive restarts.
- [ ] A protocol confirms upload completion (temporary extension → rename, marker file, or manifest).
- [ ] When multiple replicas poll concurrently, implement distributed claims, locks, or source partitioning.
- [ ] Rules exist for files with the same name but changed content: version/hash/business ID.
- [ ] Remote archive/failed/done folders and retention are defined; never delete from source prematurely.
- [ ] When download succeeds but business processing fails, files still have a replay/recovery path.
- [ ] Tested mid-transfer disconnects, wrong host keys, remote disk full, and expired credentials.
- [ ] Track metrics for oldest pending file, failure count, and local cache age.

**Note:** A persistent accept-once filter may mark a file as **observed/downloaded** before the business transaction finishes. Do not treat filter state as a business receipt; maintain processing records and crash-recovery retries.

### 9.2. SFTP Outbound

- [ ] Target directory, temporary name, rename, and length/checksum verification are configured as needed.
- [ ] Behavior when the remote file already exists is defined.
- [ ] Retrying after an upload timeout risks duplicate delivery; use versioned names/idempotency/manifests.
- [ ] Limit concurrent sessions, bandwidth, and reconnects.
- [ ] Test permission denied, insufficient disk, rename failure, and response timeout.
- [ ] Do not delete local files before completing the handoff contract.
- [ ] Atomic rename and server filesystem semantics are tested against the real SFTP server.

## 10. Foundation Section Exit Gate

Before moving to broker/API/database adapters, reviewers must confirm:

- [ ] A message flow diagram and **commit/ack boundaries** exist.
- [ ] Idempotency keys and duplicate/crash tests are in place.
- [ ] Pollers/channels/executors have bounded concurrency and buffers.
- [ ] Retry/backoff does not multiply unboundedly across layers.
- [ ] Error flows route failed messages to recovery with a clear owner.
- [ ] Connection security and secrets meet production standards.
- [ ] Partially uploaded File/SFTP artifacts are never processed.
- [ ] Metrics, logs/correlation, and pause/resume controls are in place.

**If any answer is ambiguous, do not assume Spring Integration handles it automatically.** Document the decision and test evidence before go-live.

## 11. HTTP Adapter: Inbound and Outbound Gateway

### 11.1. HTTP Inbound Gateway

HTTP inbound typically follows a **request/reply** contract; beyond business logic, you must manage request threads, response timeouts, and API responses.

- [ ] Path, HTTP method, content type, request/response schemas, and API version are clearly defined.
- [ ] Proper authentication/authorization, TLS, and network access policies are enforced.
- [ ] Request sizes/headers are bounded; JSON/XML is validated against malformed/anomalous payloads.
- [ ] Rate limits, concurrency, and timeouts are aligned across reverse proxies/load balancers.
- [ ] For long-running operations, use an async acceptance/status pattern rather than blocking synchronously indefinitely.
- [ ] Map validation, authentication, conflict, timeout, throttling, and internal errors to contract responses.
- [ ] If clients retry POSTs, require an idempotency key or check for already-processed requests.
- [ ] Correlation IDs and traces propagate through the inbound flow without logging bearer tokens/cookies.
- [ ] Test client disconnects, timeouts, duplicate requests, oversized payloads, and invalid requests.
- [ ] Never return success before business side effects satisfy contract conditions.

### 11.2. HTTP Outbound Gateway

- [ ] Configure connect timeout, response/read timeout, and overall request timeout.
- [ ] Connection pool and per-host/route connection limits match partner capacity.
- [ ] Verify TLS certificates/hostnames, proxies, mTLS, or OAuth credentials if used.
- [ ] Classify 400/401/403/404/409/429/5xx, timeouts, and network resets.
- [ ] Use bounded retries with backoff/jitter, honoring partner rate-limit signals when present.
- [ ] **Never blindly retry non-idempotent POST/PUT** calls when side-effect state is unknown.
- [ ] Use partner-side idempotency keys, status lookup APIs, or reconciliation workflows.
- [ ] Limit response sizes, validate content types/schemas, and avoid parsing untrusted data blindly.
- [ ] Implement error mapping, dashboards, alerts, and trace/correlation IDs.
- [ ] Test 429, 503, invalid response schemas, and timeouts occurring after the receiver completed processing.

**Typical scenario:** An HTTP POST creating a payment succeeds on the server, but the response to the client is lost. Retrying without an idempotency key can create a second payment. This is a **side-effect ambiguity** issue, not just a timeout error.

## 12. JMS Adapter: Acknowledgement and Redelivery

JMS provides messaging abstractions, while specifics of transactions, DLQs, prefetch/concurrency, and failover depend on the broker/JMS provider and listener container.

- [ ] Destination queue/topic names, owners, and subscription modes (durable/shared where appropriate) are clear.
- [ ] Connection factory, credentials, TLS, pooling, reconnect, and timeouts are configured.
- [ ] Acknowledge mode / transacted session / transaction manager are deliberately chosen.
- [ ] A diagram defines when the broker considers a message processed.
- [ ] On handler exceptions, know whether messages are redelivered, sent to DLQ, or marked complete.
- [ ] Redelivery limits, backoff, and poison message handling are configured.
- [ ] Consumer concurrency, prefetch/consumer window, and ordering are load-tested.
- [ ] Message converters, payload serialization, and JMS property/header mappings are tested.
- [ ] For request/reply gateways, correlation ID, reply destination, and reply timeout are configured.
- [ ] Handlers are idempotent when messages are redelivered after a DB commit.
- [ ] Metrics cover queue depth, oldest message age, redelivery rate, DLQ count, and active consumers.
- [ ] Tested broker restarts, listener crashes before/after transactions, and expired credentials.
- [ ] A DLQ replay runbook exists with service account access controls and auditing.

**Note:** A local JMS transaction usually **does not automatically span** databases, HTTP, or other systems. Use XA/distributed transactions only when architecture, infrastructure, and testing truly support them; for typical flows, prefer idempotency combined with explicit failure-window handling.

### 12.1. Mandatory JMS Drill

1. Consumer reads a message.
2. Business handler commits the database transaction successfully.
3. Process is killed **before the message is acknowledged**.
4. Listener restarts.
5. Message is redelivered per broker semantics.
6. System does not create a second business record thanks to a stable key and unique constraint.

If you cannot explain the outcome in steps 5–6, the flow is not yet verified safe.

## 13. AMQP Adapter: Publisher Confirms, Ack, and DLQ

For Spring AMQP/RabbitMQ, you must understand exchanges, queues, routing, publisher confirms, acknowledgements, and dead-lettering.

- [ ] Exchanges, queues, and bindings/routing keys are governed and match environment topology.
- [ ] Queue durability and message persistence/durability match requirements; do not conflate the two settings.
- [ ] Auto/manual ack matches listener container settings and failure policy.
- [ ] With manual ack, ack only occurs after defined processing criteria are satisfied.
- [ ] Consumer concurrency and prefetch are bounded to prevent excessive unacked messages.
- [ ] DLX/DLQ or error routing, retention, and replay procedures are in place.
- [ ] Avoid endlessly requeuing poison messages, which causes redelivery storms.
- [ ] Producers handle publisher confirms/returns or unroutable messages when delivery confirmation is required.
- [ ] Idempotency covers broker redeliveries or producer retries when confirms are missed.
- [ ] Connections, heartbeats, TLS, authentication, and recovery are verified.
- [ ] Dashboards track ready queue depth, unacked count, publish/ack rates, consumer count, and DLQ.
- [ ] Tested broker failover, invalid routing keys, and consumer crashes after DB commit but before ack.

**Manual ack is not exactly-once.** Acking too early risks losing side effects on handler failure. If the DB commits but the ack fails, the broker can redeliver. The design must account for both windows.

### 13.1. Publisher Confirm and Handling Ambiguous Outcomes

If a producer sends a message and disconnects before receiving a confirm, you cannot assume the broker did not store the message. Retrying may produce duplicates; downstream consumers need idempotency. Confirm/return/routing tests help detect messages not accepted by the broker or queue as expected, but do not replace contracts and reconciliation.

## 14. Kafka Adapter: Offsets, Partitions, and Error Record Handling

- [ ] Topics, partition counts, retention, cleanup policies, and ACLs are approved.
- [ ] Kafka bootstrap servers, TLS/SASL/credentials are configured per environment.
- [ ] Producer key/partition routing aligns with business-key ordering requirements.
- [ ] Serializers/deserializers, schema versions, and compatibility are tested.
- [ ] Producer retries, acks, and idempotent producer settings match required guarantees.
- [ ] Consumer `group.id` has an owner; impacts of changing groups or redeploying are understood.
- [ ] `auto.offset.reset` is an explicit decision for groups without offsets, never left to chance.
- [ ] Ack/offset commits happen at the contractually defined point.
- [ ] Error handlers, retry/backoff, DLT/recovery, and poison record policies are configured.
- [ ] Consumer concurrency aligns with partition count; do not expect global topic ordering.
- [ ] `max.poll.interval.ms`, processing duration, batch size, and rebalance behavior are verified.
- [ ] Tested consumer crashes after DB commit but before offset commit.
- [ ] Idempotent consumers and unique business keys protect DB updates.
- [ ] If using Kafka transactions/exactly-once, scope is documented; **it does not extend to external HTTP calls or databases**.
- [ ] Monitor consumer lag, rebalances, retry rates, DLT size, and commit errors.

### 14.1. Ordering and Poison Records

Kafka preserves ordering **per partition**; across multiple partitions, there is no global order. If the partition key is based on `orderId`, revisions of the same order should share the same partitioning rule if ordering is required.

Sending a failed record to a DLT and continuing with the next record can violate business constraints like "revision 3 must be processed after revision 2". Define a policy—**block partition, quarantine the chain, replay, or approved skip**—before production.

### 14.2. Kafka Drill

~~~text
Kafka record -> consumer -> DB transaction commit
                              |
                              +-- process killed
                                  before offset commit
                              |
restart -> record is redelivered
        -> idempotency key identifies ALREADY_PROCESSED
        -> offset is committed per policy
~~~

If `group.id` changes or offsets are reset, the number of replayed records can be large; the runbook must verify **how far business side effects have already been committed** before seeking/replaying.

## 15. JDBC Adapter: Polling and Database Operations

### 15.1. JDBC Inbound Polling

- [ ] SELECT/filters fetch only eligible rows, with batch limits and `ORDER BY` where needed.
- [ ] Appropriate indexes exist, and execution plans are tested on production-like data.
- [ ] Row claim/lock/marking prevents two instances from processing the same record unintentionally.
- [ ] Row states can use NEW/PROCESSING/DONE/FAILED or an equivalent model.
- [ ] If PROCESSING uses a lease, include expiry and recovery jobs for rows stuck after crashes.
- [ ] Transaction isolation and lock semantics fit the specific database engine.
- [ ] Do not hold DB locks/transactions open across slow remote HTTP calls without explicit design justification.
- [ ] ID/timestamp watermarks handle late updates and concurrency safely.
- [ ] Query timeouts, connection pools, transaction limits, and deadlock retry/protection are configured.
- [ ] Tested two-poller concurrent claims, malformed rows, and pod restarts mid-transaction.
- [ ] Metrics track pending row age, in-progress lease age, query latency, and pool saturation.

**Pseudo-SQL** example illustrating the claim pattern; syntax must be adapted to your database:

~~~sql
BEGIN TRANSACTION;

SELECT id
FROM integration_inbox
WHERE status = 'NEW'
ORDER BY created_at, id
FOR UPDATE SKIP LOCKED;

-- Limit row count according to the specific SQL dialect.
-- UPDATE only claimed IDs to PROCESSING.
-- Optionally record lease_owner and lease_until.

COMMIT;
~~~

`SKIP LOCKED` and pagination syntax vary across databases. Use only after verifying isolation, deadlock behavior, and transactions on the real database. Even after claiming a row, **business effect** idempotency is still required because a worker can crash after commit.

### 15.2. JDBC Outbound/Gateway

- [ ] SQL uses bind parameters; never concatenate user data into queries.
- [ ] Transaction boundaries, isolation, timeouts, and autocommit policies are defined.
- [ ] Unique constraints/upserts/locking prevent duplicate side effects.
- [ ] Limit result rows, fetch size, cursor lifetime, and memory usage.
- [ ] Connection pool max size, borrow timeout, and max lifetime align with DB capacity.
- [ ] Distinguish constraint/validation errors from transient deadlocks/timeouts.
- [ ] Tested DB failover, pool exhaustion, commit conflicts, rollbacks, and partial failures.
- [ ] Never log credentials or sensitive data inside SQL parameters.

### 15.3. Writing to DB and Publishing Broker Messages

When a handler commits to a DB and then publishes to Kafka/JMS/AMQP, the two side effects typically **do not share a single ACID transaction**. A transactional outbox records both the business row and the "obligation to publish" within one DB transaction; a separate publisher retries sending outbox entries. Downstream consumers still need idempotency because duplicates can occur.

## 16. Connection Lifecycle, Deployment, and Multiple Replicas

### 16.1. Startup/Readiness

- [ ] Required configuration is validated early; missing critical secrets/endpoints fail clearly.
- [ ] Distinguish process **liveness** from **readiness** to accept traffic/work.
- [ ] Temporary dependency outages trigger reconnect/backoff; avoid unnecessary infinite restart loops.
- [ ] Gate endpoints if schemas or remote resources are not ready yet.
- [ ] Health checks must never trigger business side effects.
- [ ] Pollers/listeners can be paused/resumed via an authorized procedure.
- [ ] Credential/certificate rotation has been tested on running processes.

### 16.2. Graceful Shutdown and Rolling Deployment

- [ ] On shutdown, endpoints stop accepting new messages as designed.
- [ ] Inflight work completes within the grace period or safely recovers/redelivers.
- [ ] Sources are never acknowledged before business state meets completion criteria.
- [ ] Tested SIGTERM/kill during HTTP calls, SFTP transfers, DB transactions, and broker deliveries.
- [ ] Rolling deployments across two versions maintain schema/message compatibility.
- [ ] Multiple pods cannot concurrently claim the same file/row unless duplicate handling is protected.
- [ ] Rollback plans preserve offsets, metadata, outbox records, and external effect state.

### 16.3. Sizing and Backpressure

Quantify arrival rate, processing throughput, p95/p99 latency, max inflight, queue size, thread pools, connection pools, and target limits. For example, if upstream sends 120 records/s while downstream sustains 80 records/s, backlog grows by roughly 40 records/s at steady rate; adding threads without increasing DB/API capacity does not fix the bottleneck.

Choose **poller pause, bounded queues, broker backpressure, concurrency limits, or fail-fast** under overload according to each endpoint's semantics. Never let in-memory buffers grow unboundedly until OOM.

## 17. Observability: Metrics, Logs, Tracing, and Alerts

### 17.1. Structured Logging

| Field | Purpose |
|---|---|
| Business ID / eventId / idempotency key | Identify records across retries |
| correlationId / traceId | Link ingress, handlers, and outbound calls |
| Adapter, channel, endpoint ID | Pinpoint which step failed |
| Target endpoint / protocol | Identify which dependency is impacted |
| Schema/mapping version | Explain parsing/transformation behavior |
| Attempt, retry delay, error category | Classify errors and detect retry storms |
| Commit/ack/offset/checkpoint state | Investigate loss/duplication windows |
| Processing duration, payload size | Spot bottlenecks |
| Outcome: success/retry/quarantine/reject | Measurable execution results |

Never log raw Authorization headers, cookies, credentials, private keys, or payloads containing unnecessary PII. For large files, log allowed file IDs/checksums/metadata instead of full contents.

### 17.2. Dashboards and Alerts

| Metric | Alert Signal |
|---|---|
| Ingress/egress rate | Abnormal drops or spikes |
| End-to-end processing latency | Exceeding p95/p99 SLO |
| Handler/adapter error rate | Spike in same error type or security errors |
| Retry volume and attempts | Retry storms, unstable partners |
| DLQ/quarantine size and oldest age | Aging failures awaiting handling |
| Kafka consumer lag / JMS-AMQP queue depth | Backlog not draining |
| Oldest SFTP/file pending age | Stuck files or partner stopped sending |
| JDBC PROCESSING lease age | Claimed rows not completing |
| Thread/queue depth, executor rejections | Channel congestion |
| Connection pool utilization, timeouts | Pool exhaustion or slow dependency |
| Duplicate detected rate | Frequent producer retries, business key conflicts |
| Business completion rate | Technical success paired with business failure |

Spring Integration provides management/metrics/observation capabilities depending on version and setup. If using Micrometer, Spring Boot Actuator, or a tracing stack, **verify that metrics/traces actually appear** with valid tags and alerts—do not merely add dependencies.

### 17.3. Cross-Transport Correlation

HTTP typically carries tracing headers, whereas file/SFTP/JDBC polling needs to generate or extract business IDs per contract. When bridging to Kafka/JMS/AMQP, configure and test header mappings in converters. Do not assume Spring Integration `MessageHeaders` pass intact across every protocol.

### 17.4. Telemetry Operations Checklist

- [ ] Concrete SLOs exist for processing latency and acceptable loss/duplication bounds.
- [ ] Alerts specify severity, owner/on-call, and runbook URL.
- [ ] Alert delivery has been tested for rising DLQ, lag, timeouts, or auth failures.
- [ ] Dashboards distinguish **no new incoming data** from **messages stuck in-flight**.
- [ ] Hourly/daily baselines and operational windows exist to avoid arbitrary thresholds.
- [ ] Correlation links source files/records to side effects and targets.

## 18. Mandatory Pre-Go-Live Test Matrix

**Do not test only the happy path.** For integration systems, the most critical tests cover moments where a process crashes **after a side effect but before acknowledging or writing a checkpoint**.

### 18.1. Test Layers

1. **Unit tests:** contracts, transforms, routers, validation, error classification, and idempotency rules.
2. **Integration tests:** adapters connected to test brokers/databases/SFTP/HTTP stubs behaving like production.
3. **Contract tests:** schemas, message headers, version compatibility, and malformed data.
4. **Load/soak tests:** throughput, concurrency, queues/buffers, connection pools, memory, and backlogs.
5. **Failure injection:** network resets, timeouts, restarts, rebalances, poison records, partial transfers.
6. **Security tests:** expired credentials, invalid TLS/host keys, unauthorized APIs, oversized payloads.
7. **Operations drills:** pause/resume, DLQ replay, failback, secret rotation, graceful shutdown.

### 18.2. Traceable Test Suite

| ID | Scenario | Pass Criteria |
|---|---|---|
| **T01** | Valid message flows from inbound through handler to outbound | Correct business output, correlation, and audit |
| **T02** | Message with invalid schema version | Quarantined/rejected per contract, no side effects |
| **T03** | Payload missing required field or wrong charset | Clear error raised and no corrupt data created |
| **T04** | Same eventId sent twice | No duplicate business side effects |
| **T05** | App crashes after DB commit, before ack | Safe redelivery, no duplicate inserts |
| **T06** | App crashes after outbound success but before saving state | Idempotency/reconciliation prevents duplicate outbound effects |
| **T07** | File partially uploaded | Not processed before ready marker/rename |
| **T08** | File re-polled after restart | No data loss and no duplicate orders |
| **T09** | Two replicas poll the same directory | No unauthorized double-processing |
| **T10** | Same filename with modified content | Handled per contract version/hash/business key |
| **T11** | Local disk/inode full | Error/alert raised, not marked DONE |
| **T12** | Wrong SFTP host key | Connection rejected and alerted, verification never bypassed |
| **T13** | SFTP network drop mid-download/upload | Proper retry/recovery, transfer not treated as successful |
| **T14** | SFTP credential expired | No infinite tight-loop retry, routed to owner |
| **T15** | HTTP inbound duplicate POST | Idempotency key preserves a single business effect |
| **T16** | HTTP inbound oversized payload | Safely rejected without memory exhaustion |
| **T17** | HTTP outbound returns 429/503 | Proper backoff and bounded attempts |
| **T18** | HTTP POST succeeds at partner but response times out | Reconciliation/idempotency prevents duplicates |
| **T19** | HTTP auth 401/403 | Alert/config action, no tight-loop retry |
| **T20** | JMS listener crashes before/after commit/ack | Correct redelivery and idempotency |
| **T21** | JMS poison message | Bounded retry, DLQ with replay |
| **T22** | JMS broker restart/failover | Consumer recovers without corrupting state |
| **T23** | AMQP manual ack lost after DB commit | Message redelivered without duplicating side effects |
| **T24** | AMQP unroutable/wrong routing | Detected via publisher confirm/return policy |
| **T25** | AMQP repeated poison message requeue | DLX/DLQ or storm-prevention mechanism triggers |
| **T26** | AMQP prefetch too high for downstream | Backpressure/queue metrics expose risk |
| **T27** | Kafka record committed to DB before offset commit | Idempotent redelivery |
| **T28** | Kafka consumer rebalance/scaling | No lost records; partition ordering preserved |
| **T29** | Kafka poison record blocking partition | DLT/quarantine follows ordering policy |
| **T30** | Kafka consumer lag spikes after outage | Alert triggers and backlog drain plan works |
| **T31** | Kafka group.id change / offset reset | Controlled replay without duplicate side effects |
| **T32** | Two JDBC pollers claim the same row | Only one writer claims per DB lock/lease design |
| **T33** | Crash while JDBC row is PROCESSING | Lease expiry/recovery returns row to processable state |
| **T34** | DB deadlock, timeout, and pool exhaustion | Bounded retry, metrics/alerts, no data loss |
| **T35** | DB commit succeeds, Kafka publish fails | Outbox records obligation and publisher recovers |
| **T36** | In-memory QueueChannel loses process | Durable boundary/recovery exists per contract |
| **T37** | ExecutorChannel queue full | Clear backpressure/rejection, no OOM |
| **T38** | Thread switch while transaction is open | Transaction is not assumed to cross into executor |
| **T39** | Concurrent retries in HTTP client + advice + broker | Total attempts stay within budget |
| **T40** | Error flow only logs and returns | Tests expose risk of lost effects / false acks |
| **T41** | DLQ replay after bug fix | No duplicate business side effects |
| **T42** | Expired TLS certificate / hostname mismatch | Fails closed and alerts properly |
| **T43** | Secret rotated while app is running | Connections recover per runbook |
| **T44** | Rolling deploy across two versions | Message/schema compatibility, no double-claim |
| **T45** | Graceful shutdown with inflight messages | Completes or redelivers/recovers without loss |
| **T46** | Network partition to remote dependency | Bounded retry/backoff and capacity |
| **T47** | Load exceeds downstream capacity | Backlog throttled/contained, resources do not collapse |
| **T48** | Correlation across SFTP → DB → Kafka | Traces/logs correlate end-to-end without leaking PII |
| **T49** | Replayed events arrive out of order | Business version/ordering policy handles correctly |
| **T50** | Rollback after partial side effects | Reconciled/compensated without duplicates or loss |
| **T51** | Unexpectedly empty source snapshot/batch | Not misinterpreted as a mass-deletion command |
| **T52** | Deleting DLQ records without ops privileges | Blocked by ACLs, audit, and retention |
| **T53** | Listener runs 24 hours with intermittent errors | No memory/thread/session/connection leaks |
| **T54** | Startup while broker/SFTP/DB temporarily unavailable | Readiness and reconnect follow policy |
| **T55** | Poison message mixed with valid messages | Does not permanently stall entire system beyond policy |

**How to store evidence:** each test requires expected/actual results, environment, adapter/endpoint ID, config/version, simulated message/business ID, timestamp, correlation ID, logs/metrics, tester name, and related issue. In particular, tests T05, T18, T23, T27, T35, and T50 cannot be substituted with "tested one happy-path message".

## 19. Canary Deployment, Operations, and Rollback Plan

### 19.1. Before Deployment Day

- [ ] Finalize topology diagram, endpoint owners, network paths, and access controls.
- [ ] Verify production configs/secrets with appropriate management tooling.
- [ ] Schema/database migrations are compatible with the previous app version during rolling updates.
- [ ] Run contract, load, security, and failure-window tests.
- [ ] Verify dashboards/alerts and on-call runbooks are operational.
- [ ] Rehearse endpoint stop/start, DLQ replay, restarts, and rollbacks.
- [ ] Prepare a backlog-handling plan and initial message/file rate limits.
- [ ] Confirm go/no-go approvers, timeline, and communication channels.

### 19.2. Canary Deployment

1. Deploy a single replica/canary with planned endpoints and credentials.
2. Enable health/metrics/logging and verify connections under real permissions.
3. Run smoke tests using synthetic data through controlled production paths.
4. Throttle poller rates/concurrency for easier observation.
5. Measure end-to-end business completion, duplicate rate, processing latency, and backlog.
6. Once approved thresholds are met, gradually increase traffic/replicas/batch sizes.
7. Monitor during the stabilization window and close the change only upon owner confirmation.

**Do not assume a canary receives only a fraction of traffic if consumer groups, queues, or pollers lack routing isolation.** Understand how Kafka partition assignment, competing JMS/AMQP consumers, and distributed claims for file/SFTP/JDBC actually behave.

### 19.3. When to HOLD or Rollback?

- Uncontrolled message loss or duplicate side effects are detected.
- App corrupts data or sends sensitive data to the wrong destination.
- DLQ/backlog grows beyond what can drain within approved SLOs.
- TLS/auth errors, credential leaks, or bypassed security validations occur.
- Multiple replicas process the same item outside design limits.
- Continuous consumer retries overload DB/API/brokers.
- Commit/ack state cannot be determined after an incident.
- Error flows swallow messages or produce false success results.

**Rolling back the application version does not undo external side effects.** Written files, published messages, DB commits, executed partner API calls, and committed offsets must be reconciled separately.

### 19.4. Rollback Runbook

1. Pause faulty ingress/writers; capture metrics, logs, offsets, metadata, and backlog state.
2. Identify business effects that were committed, emitted, or remain unacknowledged.
3. Verify schema/consumer-group/checkpoint compatibility with the previous version.
4. Redeploy the verified version or disable the new feature per plan.
5. Replay in a controlled manner using idempotency keys and preserving business ordering where needed.
6. Reconcile target systems (DB, files, brokers, partner APIs) to avoid loss or duplication.
7. Resume ingress only when state is consistent and approved by the owner.
8. Write a postmortem covering root cause, test updates, and preventive policies.

Never execute "clear queue", "delete inbox", "reset offset to earliest", or "rename and resend everything" before determining actual side effects.

## 20. Post-Go-Live Operations Runbook

### 20.1. No New Data Observed

1. **Does the source have data?** Are ready files on File/SFTP, messages on broker, NEW rows in DB, or HTTP requests arriving?
2. **Is the endpoint running?** Is the poller/listener/gateway disabled, paused, stopped, or failing startup?
3. **Is a channel congested?** Check executor queue depth, active threads, rejections, and pool exhaustion.
4. **Is a dependency failing?** Check credentials, TLS, DNS, network, quotas, response latency, and broker/DB health.
5. **Where did the message go?** Check retry scheduler, error flow, DLQ, quarantine, and pending outbox.
6. **Did business logic commit?** Check DB/business records, ack/offsets, and file markers/metadata.
7. **Choose an action:** Retry, re-drive, fix input, throttle load, pause source, or rollback.
8. **Log the incident:** Owner, timestamps, blast radius, business IDs, and open questions.

### 20.2. DLQ/Quarantine Replay

- Verify the root cause is resolved.
- Inspect error records to determine whether partial side effects occurred.
- Obtain approval for replays involving sensitive data or high-risk business logic.
- Run bounded batches while monitoring idempotency and ordering.
- Reconcile business outcomes between source and target after replay.
- Delete or reclassify DLQ records only per retention, permission, and audit policies.

### 20.3. Pause/Resume Endpoint

The runbook must specify **endpoint ID**, owner, how to pause inbound pollers/listeners or throttle outbound traffic, inflight wait time, resume conditions, and backlog checks. Pausing does not necessarily cancel active HTTP calls or broker transactions; behavior for each endpoint type must be tested in advance.

### 20.4. Credential Rotation

1. Prepare new secrets/certificates/keys per security procedures.
2. Verify both sides support a transition overlap window if needed.
3. Apply rotation in a limited scope and verify reconnects and readiness.
4. Monitor auth/TLS/host-key errors and traffic.
5. Revoke old credentials after confirming no dependencies remain.
6. Record audit details: owner, timestamp, outcome, and recovery plan.

## 21. Case Study: SFTP → JDBC → Kafka

A system receives partner order CSVs via SFTP. Files are parsed and validated; each order is written to a DB and emits an `OrderAccepted` event to Kafka. The project deploys three replicas for high availability.

### 21.1. Flawed Initial Design

- Poller runs every second with no batch limit.
- Multiple pods scan the same remote directory using only an in-memory accept-once filter.
- Partner uploads `.csv` files directly before data is complete.
- No business idempotency key; retrying a file can create duplicate orders.
- Handler commits the DB then publishes directly to Kafka without an outbox.
- `errorChannel` only logs exceptions, with no quarantine/replay.
- No metrics for file age or Kafka publish failures.

This design may appear to work locally with one instance, but is unsafe for production.

### 21.2. Improved Design

**SFTP Producer:** Upload with a temporary name, only rename to the ready extension or create a marker upon completion; provide business keys and checksums/manifests if required by contract.

**Ingress:** Verify SFTP host keys, use a secret store and timeouts; partition/claim sources across replicas; use appropriate persistent metadata/filters; configure pollers with bounded batch sizes and concurrency.

**Business contract:** Each order has a stable ID and revision, schema version, row count, and file size limits. Validation executes before side effects; sensitive data is omitted from logs.

**JDBC transaction:** Enforce unique business keys and a processed-events table; write the order and outbox event in a single transaction. Retries after crashes do not create new orders.

**Kafka publisher:** A worker publishes outbox records with retry/backoff, tracks attempt status, and monitors pending age and publish failures. Downstream consumers remain idempotent since events can be redelivered.

**Error handling:** Schema-invalid files go to quarantine; infrastructure errors use bounded retries; source files are not deleted prematurely; a replay runbook and owner exist.

**Observability:** Trace from remote file ID → order ID → DB transaction/outbox → Kafka event; dashboards show oldest pending file, duplicate no-op count, and outbox lag.

### 21.3. Three Decisive Failure Drills

**Drill A — DB commits, pod dies before Kafka publish.** The outbox holds the pending event. A worker resumes publishing after restart; no duplicate order is created.

**Drill B — Two replicas inspect the same file.** Distributed claims/filters reduce contention; the DB unique key protects business integrity even if input is reprocessed.

**Drill C — Partner loses network mid-upload.** Unready files are never parsed; processing begins only after completion. Failed files remain investigable and re-drivable.

### 21.4. Acceptance Criteria

- No lost orders across defined failure drills.
- Replays create no duplicate side effects.
- Full traceability and reconciliation from SFTP to Kafka.
- Failed files do not vanish; they enter quarantine with a runbook.
- Backlog and latency meet approved SLOs.
- Scaling or restarting replicas causes no out-of-contract duplicates.
- Tested pause/resume, credential rotation, and rollback runbooks exist.

**Lesson:** No single inbound adapter, poller, Kafka producer, or transaction manager can substitute for end-to-end flow design.

## 22. Reusable Review Form Template

~~~yaml
flow: supplier-orders-sftp-to-kafka
owners:
  business: order-operations
  technical: integration-platform
  onCall: platform-operations
ingress:
  type: sftp-inbound
  remoteReadyProtocol: temp-then-rename
  pollInterval: 5s
  maxBatch: 10
message:
  schemaVersion: "1.0"
  idempotencyKey: source-orderId-revision
  maxPayloadSize: REVIEWED_LIMIT
channels:
  processing: bounded-workers
  durableCheckpoint: database-inbox
delivery:
  expectedSemantics: at-least-once
  businessIdempotency: unique-constraint
  publishRecovery: transactional-outbox
failure:
  transient: bounded-backoff
  permanent: quarantine
  replayRunbook: documented-and-tested
security:
  sftpHostKeyVerification: required
  secretsManaged: true
observability:
  correlationId: required
  queueAndLagAlerts: tested
readiness:
  crashDrillsPassed: true
  gracefulShutdownTested: true
  rollbackTested: true
approval:
  businessOwner: PENDING
  security: PENDING
  operations: PENDING
~~~

**This is an illustrative review form**, not YAML understood by Spring Integration. Do not mark GO while any approval remains PENDING or technical evidence is missing.

### 22.1. Decision Matrix

| Status | Criteria |
|---|---|
| **GO** | All mandatory gates pass; tests and rollback have evidence |
| **GO WITH EXCEPTION** | Exceptions have approved owner/expiry, scope, and risk mitigations |
| **HOLD / RETEST** | Missing load/failure drills, unverified source/contract, or pending owner approval |
| **NO-GO** | Uncontrolled loss/duplicate side effects, security flaws, unknown ack/commit, no recovery path |

Never use exceptions to justify bypassing TLS/host-key verification, exposing secrets publicly, or accepting data loss forbidden by the business.

## 23. Anti-Patterns to Avoid

**"Enabling retry guarantees no message loss."** Retries do not fix premature acks, missing persistence, or ambiguous side effects. Failure-window tests are mandatory.

**"Kafka/JMS/AMQP guarantees exactly-once so the DB doesn't need idempotency."** Broker semantics do not automatically cover external DBs or HTTP calls. Business keys and transactions/reconciliation are required.

**"QueueChannel means durable queue."** In-memory queues lose messages on restart; durability depends on a MessageStore or broker.

**"Every exception automatically goes through errorChannel."** Error paths depend on sync vs async endpoints and error handlers. Propagation and ack behavior must be verified.

**"SFTP download complete means business processing complete."** Ingestion/metadata filtering, DB commit, and archiving are distinct states.

**"HTTP timeout means the receiver didn't execute the request."** The request may have succeeded while the response was lost. Idempotency keys or status lookups are required.

**"Kafka preserves ordering across the entire topic."** Ordering only holds within a partition; key selection and concurrency affect ordering.

**"Adding pods always increases throughput."** It can increase file/row contention, saturate remote APIs/DBs, and trigger retry storms.

**"DB commit and broker publish share one transaction."** Understand transaction boundaries, outbox patterns, or compensating designs.

**"Logging full payloads makes debugging fastest."** It leaks PII/secrets; use metadata and business correlation instead.

**"Rolling back the image undoes all changes."** External side effects, offsets, uploaded files, API calls, and DB commits persist.

**"Having Actuator means monitoring is sufficient."** You need flow-specific business metrics, alerts, correlation, and verified failure detection.

## 24. Self-Check Questions

1. How do an inbound adapter and an inbound gateway differ in terms of request/reply?
2. Why should a newly generated `MessageHeaders.ID` not automatically serve as a business idempotency key?
3. How does switching from `DirectChannel` to `ExecutorChannel` affect transactions and ordering?
4. How does an in-memory `QueueChannel` differ from a durable broker queue?
5. When a Kafka offset is uncommitted after a DB commit, what happens upon restart?
6. Why do JMS/AMQP redeliveries require an idempotent consumer?
7. If an HTTP POST times out, why can't you assume the partner did not process it?
8. When an SFTP file is mid-upload, what convention tells the consumer it is ready?
9. Does a persistent accept-once filter prove business processing succeeded?
10. If two JDBC pollers SELECT the same NEW row, what prevents double claiming?
11. Why is a unique constraint needed instead of just a SELECT checking if the key exists?
12. Which failure window does the transactional outbox solve?
13. What is the risk of retrying across three layers, and who should own the retry policy?
14. What must be verified before running a DLQ replay test?
15. When Kafka routes a poison record to a DLT, how can this affect ordering?
16. In AMQP, which two distinct parts do publisher confirms and consumer acks solve?
17. Why shouldn't a database transaction remain open while calling a slow API?
18. Which metrics distinguish "no messages at source" from "messages stuck in flow"?
19. During rolling deployments, what must be tested regarding schemas, checkpoints, and inflight work?
20. In an SFTP → DB → Kafka flow, if DB commits but Kafka publish fails, how should it recover?

**Hint:** Separate the milestones *receive → durably persist → execute side effect → acknowledge/commit source → verify target*. For each milestone, ask: "if the process dies right after this step, where must retry happen and what risks remain?"

## 25. Glossary and References

| Term | Meaning |
|---|---|
| **Inbound/outbound adapter** | One-way endpoint receiving/sending data between a flow and an external system |
| **Inbound/outbound gateway** | Request/reply endpoint inside an IntegrationFlow |
| **MessageChannel** | Channel passing messages between endpoints |
| **Poller** | Scheduled task reading from a source |
| **At-least-once** | Messages may be redelivered when not yet acknowledged |
| **Idempotency** | Repeating requests without causing unintended duplicate business effects |
| **Ack/offset/checkpoint** | Acknowledgement or processed-position marker at the source |
| **Transactional outbox** | Recording the obligation to publish a message inside the business DB transaction |
| **DLQ/DLT/quarantine** | Storage for failed messages/records for investigation and replay |
| **Retry/backoff** | Retrying with bounded attempts and controlled wait intervals |
| **Backpressure** | Throttling input based on downstream processing capacity |
| **Persistent metadata store** | Storage preserving filter/checkpoint state across restarts |
| **Consumer lag / backlog** | Volume of waiting data or consumer delay behind head |
| **Graceful shutdown** | Stopping new intake and draining inflight work safely |
| **Go/no-go** | Deployment decision based on evidence and risk level |

Resources to cross-check **against your project version**:

- **Spring Integration Reference Guide:** Message Channels, Polling Consumer, Endpoint Lifecycle, Error Handling, and Message Store.
- **Spring Integration File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC adapters:** Java DSL, inbound/outbound/gateways, adapter-specific limits and mechanisms.
- **Spring Framework / Spring Boot Reference:** Transaction Management, TaskExecutor/TaskScheduler, configuration binding, Actuator, and Micrometer.
- **Spring for Apache Kafka Reference:** Listener container, acknowledgement, retry, DLT, transactions, and consumer groups.
- **Spring AMQP Reference and RabbitMQ documentation:** Ack, prefetch, publisher confirms/returns, dead lettering.
- **Jakarta Messaging (JMS) specification and broker vendor documentation:** Transactions, acknowledge, redelivery, durable subscriptions, DLQ.
- **Official documentation for your SFTP server, partner HTTP APIs, JDBC driver, and database:** Host keys, timeouts, API idempotency, SQL locking, connection pooling, and failure recovery.

**Final criterion:** A production-ready adapter does more than **connect to an external system**. It must have a clear message contract, explainable delivery and transaction/ack semantics, idempotency, error recovery, security, load limits, observability, runbooks, and corresponding failure tests. Only when **evidence meets requirements and owners approve** should the flow move into live operations.
