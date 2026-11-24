# Failing When DLT Publish Fails

A Dead Letter Topic (DLT) is the recovery destination for records a consumer cannot process successfully under its retry policy. In Spring Kafka, a listener failure can be handed to **DeadLetterPublishingRecoverer** to publish the record to the DLT. However, DLT publishing itself is a Kafka producer operation and **can fail** due to broker issues, authorization, serialization, topic configuration, record size, or timeouts.

If the application treats a record as recovered when it was never actually written to the DLT, the source offset may be committed and the data will no longer traverse the normal processing path. This is a severe **silent loss** risk: the consumer group looks like it is making progress, yet the business logic never ran and the failed record is nowhere to be investigated.

A reliable design must distinguish three states:

1. **Listener business processing failed.**
2. **Recoverer attempted to publish to the DLT**, though the outcome may be unknown or failed.
3. **Recovery is confirmed succeeded** per the chosen publish mechanism and acknowledgement policy; only then may the source offset advance per delivery semantics.

Never equate invoking the DLT send call with the broker having accepted the record. This lesson focuses on how to **fail recovery explicitly when DLT publishing fails**, how the consumer re-handles the record, duplicate windows, and operational runbooks.

## 1. Where does the DLT sit in the error-handling workflow?

For a typical record listener, the workflow is:

~~~text
orders.events
      |
      v
@KafkaListener processes record
      |
      +--- Succeeded -------------------> Offset advances per AckMode
      |
      +--- Failed
               |
               v
        DefaultErrorHandler
               |
          Retry/backoff
               |
       +-------+-------+
       |               |
   Retry succeeded  Retries exhausted / non-retryable
       |               |
       v               v
   Continue       DeadLetterPublishingRecoverer
                       |
                       v
                  Publish to DLT
                       |
                +------+------+
                |             |
            Succeeded       Failed
                |             |
                v             v
         Recovery complete  Recovery must be
         per policy         treated as failed
~~~

The error handler controls retrying the input record; the recoverer decides which records need moving to the DLT and calls the producer to publish. Because the producer sends asynchronously, the recoverer needs a policy for observing send results to determine whether recovery completed.

With Spring Kafka, two related models exist:

- **Blocking retry:** typically uses DefaultErrorHandler with DeadLetterPublishingRecoverer.
- **Non-blocking retry:** uses retry-topic infrastructure, such as `@RetryableTopic`, where records pass through retry topics before reaching the DLT.

Both models have different components and commit points, yet both must handle failures when publishing to a recovery topic.

## 2. What does "DLT publish failed" cover?

A publish operation can fail immediately while preparing the record or after the request has been dispatched to the broker.

### 2.1. Synchronous errors before sending

Examples:

- The serializer cannot convert the key/value to bytes.
- The DLT record is built with an invalid topic or partition.
- The producer is closed or in a fatal state.
- The client lacks required producer configuration.
- The record or headers fail during conversion.

An exception may be thrown immediately while building the request or calling `send()`. There is no success future to wait on when the operation cannot even start.

### 2.2. Asynchronous errors after sending

Examples:

- Broker leader changes or connection drops.
- The producer does not receive acknowledgement.
- The DLT topic does not exist yet and metadata is unavailable.
- Authorization is denied.
- Replication/ISR does not meet producer requirements.
- The record hits delivery timeout.

The producer can return a future and report the failure later. If the recoverer does not inspect the future, `send()` returning only means the send was accepted for client processing, **not** that the broker durably persisted the record.

### 2.3. Ambiguous outcome after timeout

A timeout does not always prove the DLT record was not written. Sometimes the broker appended the record but the acknowledgement did not arrive in time. If the recoverer fails and the source record is redelivered, the record may be published to the DLT a second time.

Therefore, the policy "do not commit the source offset when DLT publish is unconfirmed" prevents skipping records, yet **does not by itself guarantee the DLT holds only one copy**. The system needs stable event IDs and deduplication in the DLT consumer or replay workflow.

## 3. Risks when the recoverer does not confirm send results

A dangerous behavior can happen:

~~~text
Listener fails processing
        |
        v
DeadLetterPublishingRecoverer calls KafkaTemplate.send()
        |
        v
send() returns incomplete future
        |
        v
Recoverer returns normally
        |
        v
Container treats record as recovered
        |
        v
Source offset is committed per policy
        |
        v
Producer future later reports DLT publish failure
~~~

In that case the DLT is missing the record while the consumer group's committed offset has moved ahead. Restarting the consumer will not automatically re-read the source record because the group resumes from the committed offset.

In Spring Kafka versions that support it, **DeadLetterPublishingRecoverer.setFailIfSendResultIsError(true)** lets the recoverer throw an exception when the publish result reports an error. Verify the actual configuration and API of your running version; never rely on defaults without checking.

Principles:

- Recovery is considered successful only after meeting the confirmation condition chosen by the business.
- If DLT publishing fails, the exception must propagate back into error/recovery handling rather than just being logged.
- Source offsets should not be proactively committed as "recovered" when the failed record has not been persisted as required.
- When publish outcome is uncertain, prefer safe replayability and tolerate controlled duplicates over silent data loss.

## 4. Configuring failure when DLT send fails

Example Spring Kafka configuration for a non-transactional listener:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DeadLetterPublishingRecoverer deadLetterRecoverer(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(dltKafkaTemplate);

    // Recovery must not be considered successful if the producer reports an error.
    recoverer.setFailIfSendResultIsError(true);

    // Bound how long the recoverer waits for the send result.
    recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(15));

    return recoverer;
}

@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer deadLetterRecoverer) {

    DefaultErrorHandler handler = new DefaultErrorHandler(
        deadLetterRecoverer,
        new FixedBackOff(1_000L, 3L)
    );

    // After a recovery failure, the backoff sequence can be restarted.
    handler.setResetStateOnRecoveryFailure(true);

    return handler;
}
~~~

This example reflects three decisions:

1. The listener has a bounded retry budget to process the record before recovery.
2. The recoverer checks DLT publish results and throws if sending fails under the configured confirmation mechanism.
3. When recovery fails, the error handler can restart the backoff sequence for the next processing cycle.

Verify setter names and timeout types against your Spring Kafka version's Javadoc. Specifically, the send-result wait time must align with the producer's configured timeouts. Never set an infinite wait timeout just to avoid exceptions.

### 4.1. What does the confirmation mechanism actually guarantee?

When the send future completes successfully, the producer received an acknowledgement per its `acks` setting. If the producer uses **acks=all**, brokers confirm according to ISR replicas and `min.insync.replicas`; it does not mean every existing replica has acknowledged.

If high durability is required for recovery, review:

- Producer `acks=all`.
- Appropriate idempotent producer settings.
- Sufficient DLT topic replication factor.
- `min.insync.replicas` aligned with replication factor.
- Managed retention and access permissions.
- Alerts whenever send results go unconfirmed.

You cannot achieve durability merely by awaiting the future if the DLT topic has an inadequate replication factor or the producer uses weak acknowledgements.

## 5. Choosing a timeout when waiting for DLT publish

The recoverer can wait for the `KafkaTemplate.send()` result. The wait time needs to be long enough for the producer to retry retriable errors and receive a response, without blocking the consumer thread for too long.

Related time bounds:

| Parameter | Role |
|---|---|
| delivery.timeout.ms | Upper bound on total time the producer spends delivering a record |
| request.timeout.ms | Wait time for each individual broker request response |
| linger.ms | Batching wait interval before sending if configured |
| Recoverer wait-for-send-result timeout | Time the recoverer waits on the DLT send future |
| max.poll.interval.ms | Limit on consumer poll progress |
| Error handler BackOff | Wait interval before the next processing/recovery attempt |

If the recoverer only waits 2 seconds while producer delivery timeout is 120 seconds, the recoverer can time out while the request is still in flight. The DLT record may appear later, and another retry could publish an extra copy.

If the recoverer waits 120 seconds on the consumer thread, repeated waits can stretch the processing loop and affect poll cadence. Design from SLOs, measure actual latency, budget retries, and use finite producer timeouts.

A rough estimate when recovery repeatedly times out:

~~~text
Time before next poll
    ≈ listener time + listener backoff
      + recovery attempts × DLT wait timeout
      + overhead
~~~

No single timeout fits every application. If the DLT is a mandatory data-safety path, it is usually better to fail and preserve redelivery when publishing cannot be confirmed rather than shrinking timeouts and pretending sends succeeded.

## 6. Common causes of DLT publish failure

| Cause | Symptoms | Where to investigate |
|---|---|---|
| DLT topic does not exist | Metadata timeout, unknown topic/partition | Check topic provisioning and auto-create permissions |
| Wrong DLT name or partition | Invalid topic/partition, mismatched metadata | Check destination resolver and partition count |
| Missing write permission | TopicAuthorizationException or authorization error | Check principal, ACLs, credentials |
| Serializer cannot handle value | SerializationException | Check DLT KafkaTemplate serializer and payload type |
| Record too large | RecordTooLargeException or size-limit error | Check serialized bytes, headers, max.request.size, and broker/topic limits |
| Unstable broker/leader/ISR | NotEnoughReplicas, timeout, leader error | Check ISR, leader, replication, and broker health |
| Producer buffer full | Block timeout, queue backlog | Check throughput, buffer memory, and broker latency |
| Producer closed or fatal error | IllegalStateException or producer fatal exception | Recover producer; check transaction/fencing if used |
| Network/DNS/TLS | Disconnect, authentication/handshake error | Check endpoints, certificates, and connectivity |

Do not treat every timeout as a transient network glitch. A missing topic or wrong endpoint can keep timing out until configuration is fixed. The root cause dictates whether retrying makes sense.

## 7. Missing DLT topic or wrong partition

With the default DeadLetterPublishingRecoverer, the destination is usually derived from the source topic while preserving the corresponding partition. For example, a record from topic `orders` partition 7 may be sent to `orders.DLT` partition 7.

If the DLT topic only has 3 partitions, destination partition 7 is invalid. Publishing can fail, or the framework may validate partitions and apply version- and configuration-dependent handling. Verify your destination resolver and the recoverer's partition validation behavior.

Illustrative routing:

~~~java
DeadLetterPublishingRecoverer recoverer =
    new DeadLetterPublishingRecoverer(
        dltKafkaTemplate,
        (record, exception) ->
            new TopicPartition(record.topic() + ".DLT", -1)
    );
~~~

Using a negative partition in the destination resolver lets the producer choose a partition instead of forcing the same source partition, per the recoverer's contract. This avoids requiring the DLT topic to have the same partition count, though **it does not preserve ordering or source-to-DLT partition mapping**.

If you need to keep the source partition for easier investigation, provision the DLT with enough partitions and store original topic/partition/offset in headers. In production, create topics via IaC with explicit replication, retention, and ACLs; do not rely on unintended auto-create.

## 8. Serializer incompatible with failed records

A particularly common error happens when an input record fails deserialization. With **ErrorHandlingDeserializer**, the framework can place the deserialization failure into headers and let the recoverer send the original `byte[]` value to the DLT.

However, the `KafkaTemplate` used for the DLT might be configured with a JSON serializer that only accepts deserialized objects, not `byte[]`. In that case:

~~~text
Source record contains invalid bytes
         |
         v
ErrorHandlingDeserializer records error
         |
         v
DeadLetterPublishingRecoverer attempts to send raw bytes
         |
         v
DLT KafkaTemplate uses a serializer that does not support bytes
         |
         v
SerializationException: DLT publish failed
~~~

The fix is configuring the DLT serializer to support the value types being sent, such as using **DelegatingByTypeSerializer** to pick `ByteArraySerializer` for `byte[]` and a JSON serializer for normal objects.

Conceptual configuration:

~~~java
Map<Class<?>, Serializer<?>> serializers = new LinkedHashMap<>();
serializers.put(byte[].class, new ByteArraySerializer());
serializers.put(OrderEvent.class, new JsonSerializer<OrderEvent>());

DelegatingByTypeSerializer valueSerializer =
    new DelegatingByTypeSerializer(serializers, true);
~~~

This example only illustrates choosing serializers by Java type. Adapt it for your actual payload classes, key serializer, serializer ordering, trusted packages settings, and Spring Kafka version API.

Do not simply re-serialize all failed values as JSON if doing so loses the original bytes needed for debugging. For deserialization failures, original bytes and metadata are key evidence for analyzing schema or payload corruption.

## 9. Authorization, authentication, and configuration errors

DLT publishing is a **produce operation to a different topic**. A principal authorized to consume the source topic is not guaranteed to have write permission on the DLT topic.

A deployment may read `orders.events` normally yet fail writing `orders.events.DLT` because:

- ACLs only grant READ on the source topic.
- The DLT topic was provisioned on a different cluster or namespace.
- The DLT KafkaTemplate uses a different principal.
- Credentials/TLS certificates changed.
- The DLT topic has its own policy.

These errors usually cannot be resolved by retrying with the same credentials. Fix ACLs, credentials, or routing and re-verify.

Include DLT write-permission checks in pre-rollout verification. If the DLT is a critical recovery path, discovering a missing ACL only when the first poison record arrives is too late.

## 10. What does DefaultErrorHandler do when recovery fails?

With blocking retries and DefaultErrorHandler, after the listener exhausts retries or hits a non-retryable exception, the handler calls the recoverer. If the recoverer throws an exception, **recovery has not succeeded**.

In Spring Kafka versions that support it, DefaultErrorHandler has a mechanism to reset backoff state when recovery fails. The record can then be redelivered and retry/recovery can continue, rather than being treated as handled simply because the recoverer was invoked.

Example:

~~~text
Record X at offset 53
      |
      v
Listener business failure
      |
      v
Listener retries exhausted per policy
      |
      v
Recoverer publishes to DLT
      |
      v
DLT send fails -> recoverer throws exception
      |
      v
DefaultErrorHandler does not mark recovery succeeded
      |
      v
Record X remains unrecovered work
      |
      v
Backoff / redelivery / recovery retried per config
~~~

Things to verify in your specific version:

- Does the recoverer actually throw an exception when DLT send fails?
- Does the error handler's state reset on recovery failure?
- How are AckMode, manual ack, and `commitRecovered` configured?
- Is the record sought/re-submitted for reprocessing?
- Can the container stop due to an unhandled exception?

Do not assume any arbitrary DefaultErrorHandler configuration behaves properly if listener code catches exceptions itself or manually acknowledges records before recovery completes.

## 11. Offset commits: retain records when the DLT fails to save

In an at-least-once model, a crucial goal is **not losing the chance to reprocess the source record** when DLT publishing fails.

Distinguish these states:

| State | What the application knows | Appropriate offset action |
|---|---|---|
| Listener succeeded | Business logic completed | Commit per AckMode |
| Listener failed, DLT publish confirmed | Record stored in recovery stream | May commit per recovery policy |
| Listener failed, DLT publish rejected | Recovery failed | Do not mark record as recovered |
| Listener failed, DLT send timed out / uncertain | DLT may or may not have written it | Preserve replayability, tolerate DLT duplicates |
| DLT succeeded yet source offset commit failed | DLT has record, group has not saved progress | Source record may be re-read and DLT may get duplicates |

With **AckMode.MANUAL_IMMEDIATE**, some DefaultErrorHandler configurations can use `commitRecovered` to commit offsets of recovered records. Enable that only when matching AckMode and when certain the recoverer returns normally under the desired confirmation conditions.

With other AckModes, the container manages commits per its own rules. Do not apply a blanket claim that "once the recoverer finishes, the offset commits immediately" to every configuration.

Never write logic like:

~~~java
try {
    publishToDlt(record);
}
catch (Exception ex) {
    log.error("DLT failed", ex);
}
acknowledgment.acknowledge(); // dangerous if DLT has not stored the record
~~~

If the recoverer fails, propagate the error back to the appropriate error-handling flow or hold the record in another durable recovery mechanism. Logging and then acknowledging erases the fact that business logic never ran and the DLT never recorded it.

## 12. DLT written yet source uncommitted: valid duplicates

Even when the recoverer checks send results and the broker confirms the DLT publish, the source consumer's offset commit can still fail.

~~~text
DLT publish: succeeded
        |
        v
Record exists in orders.DLT
        |
        v
Application crashes before committing orders offset
        |
        v
Another consumer re-reads source record
        |
        v
Publishes to DLT again
~~~

In a non-transactional model, there is no automatic atomicity between DLT publishing and source offset commits. That is why **DLTs must tolerate duplicates**.

To prevent duplicate business impacts:

- Keep original topic, partition, and offset in DLT headers.
- Keep a stable event ID/business key.
- DLT consumers or replay workflows use an idempotency key.
- Never treat the DLT's new offset as a business identifier.
- During replay, track which records have already been processed or admitted to the workflow.

A technical identity key can combine original topic + original partition + original offset. If a business action can be published multiple times as distinct source records, a business-level event ID is still required to deduplicate across those publishes.

## 13. When the producer times out yet the DLT was already written

A producer timeout can produce an ambiguous result:

1. Recoverer sends the DLT publish request.
2. Broker writes the record.
3. Network drops the acknowledgement.
4. Future reports error or recoverer times out waiting.
5. Error handler retries recovering the source record.
6. DLT receives a duplicate copy.

You cannot completely eliminate this case by increasing wait timeouts or enabling idempotence. Idempotent producers protect internal protocol retries within a producer session; a fresh `send()` call from the recoverer upon redelivery can be treated as a new record.

For systems requiring business-level exactly-once processing, design idempotency when reading/replaying the DLT or use appropriately scoped transactions. Do not rely on "DLT send is only called once" as an invariant.

## 14. DLT failures and retry storms

If DLT brokers go down, each failed record may keep cycling:

~~~text
Listener fails -> Retries exhausted
          |
          v
DLT publish fails
          |
          v
Recovery retry
          |
          v
DLT publish retried
          |
          v
Continues failing ...
~~~

When many consumers hit this simultaneously, a retry storm can erupt: producers send high volumes of failing, timing-out, retrying requests at once, keeping brokers or the network overloaded.

Safeguards:

- Bounded, sufficiently long backoff during prolonged recovery failures.
- Classify recoverable vs. unrecoverable DLT errors.
- Limit concurrency and in-flight broker requests.
- Alert immediately when DLT publish failures spike.
- Track producer retry rate and delivery timeouts.
- Have a controlled process to pause/stop consumers if failed records cannot be stored.
- Fix topics, ACLs, clusters, and serializers before letting the system drain backlogs.

Never make all recovery retries infinite automatically. If the DLT topic is misconfigured, retries cannot fix the root cause.

## 15. Blocking retry vs. non-blocking retry when DLT fails

With **blocking retry**, DefaultErrorHandler and DeadLetterPublishingRecoverer coordinate redelivery when recovery fails.

With **non-blocking retry**, retry-topic infrastructure publishes records through retry topics and eventually to the DLT. If publishing at any topic hop or to the DLT fails, ensure the source record for that hop is not treated as recovered before the publish outcome is confirmed per configuration.

Differences:

| Aspect | Blocking retry | Non-blocking retry |
|---|---|---|
| Recovery flow | Error handler handles source record | Retry-topic routing across multiple topics |
| Data handoff boundary | When recoverer publishes to DLT | Each publish to retry topic / DLT |
| Ordering | Easier to control within source partition | Can change |
| Consumers/offsets | Mainly source container | Each retry topic has its own consumer and offsets |
| Publish failure | Recovery incomplete if send confirmation fails | Hop incomplete if publish fails |
| Observability | Record retries, DLT send, source offset | Must monitor all retry stages and DLT |

Do not carry an assumption straight from DefaultErrorHandler over to `@RetryableTopic` without checking your version and actual recoverer bean. Retry-topic infrastructure can create its own recoverer, listener containers, and error handlers.

## 16. Distinguishing DLT publish failure from DLT listener failure

Two incidents are easily confused:

1. **DLT publish failure:** the producer cannot write the record to the DLT topic.
2. **DLT listener/handler failure:** the record is already in the DLT, yet the listener consuming or processing the DLT throws an exception.

Example:

~~~text
Source listener fails
      |
      v
DLT publish fails               <-- DLT publish failure

Source listener fails
      |
      v
DLT publish succeeded
      |
      v
@DltHandler processing DLT fails <-- DLT processing failure
~~~

In the retry-topic pattern, the **DltStrategy** enum offers options like `FAIL_ON_ERROR`, `ALWAYS_RETRY_ON_ERROR`, or `NO_DLT` depending on version. These strategies govern **behavior when processing records in the DLT** or whether a DLT is created; **do not confuse** `DltStrategy.FAIL_ON_ERROR` with configuring DeadLetterPublishingRecoverer to fail when the **producer sending to the DLT** fails.

If the goal is verifying producer sends to the DLT, check the recoverer's send-result verification config. If the goal is whether a failing DLT handler should stop or retry, check `DltStrategy` and the DLT listener's error handler.

These are two separate failure boundaries and require distinct metrics and alerts.

## 17. Transactional listeners need dedicated recovery handling

With listener containers using Kafka transactions, Kafka outputs and input offsets can participate in the same transaction. When a listener exception triggers a rollback, **DefaultAfterRollbackProcessor** typically handles retry/recovery rather than relying solely on a non-transactional DefaultErrorHandler.

Some Spring Kafka configurations support publishing recovered records in a new transaction and sending source offsets into that transaction per policy. When doing so, verify:

- Does the recoverer publish to the DLT within the established transaction?
- Is the original offset committed with the recovery transaction?
- Does the producer transaction commit succeed?
- If the transaction aborts, is the record redelivered properly?
- Are there producer fencing, timeout, or transaction coordinator errors?

**Do not assume a DLT publish and source offset commit are atomic merely because a Java method has `@Transactional`.** Kafka transactions must be configured at the proper producer/container boundary, and your Spring Kafka version dictates the exact APIs.

Kafka transactions also do not automatically cover database changes or HTTP side effects. If an external action succeeded yet the recovery transaction failed, the record can still be reprocessed. Idempotency remains mandatory.

## 18. Designing a fallback when the DLT is unavailable

The DLT is the primary recovery channel, yet it can still lose write availability. Decide what to do when the DLT is unavailable longer than an acceptable threshold.

Options:

| Policy | Advantages | Trade-offs |
|---|---|---|
| Hold source record unrecovered and retry with backoff | Does not intentionally drop records | Lag grows, partition can stall |
| Controlled consumer pause/stop | Curbs retry storms, preserves source position | Slows whole or partial consumption stream |
| Purpose-built durable fallback storage | Can store records for later handling when Kafka DLT fails | Adds system, permissions, transactions, and reconciliation |
| Fallback DLT on another cluster | Isolates failure domain | Adds security, routing, consistency, and monitoring complexity |
| Alert incident and manual intervention | Clear ownership and control over critical data | Less automation |

If using fallback storage, mark recovery complete only after writing with the required durability. Never call a fallback API, swallow exceptions, and commit offsets. You need event IDs, checksums, or source identifiers to reconcile copies that may appear in multiple places.

The right option depends on data criticality, Kafka retention, processing SLAs, and the operations team's recovery capacity.

## 19. How should the DLT producer be configured?

The `KafkaTemplate` used for the DLT is a producer. It can share a `ProducerFactory` or use a dedicated factory; if dedicated, verify all security, serializer, and reliability properties.

Spring Boot example:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
        max.in.flight.requests.per.connection: 5
~~~

This is an illustrative configuration. When the DLT `KafkaTemplate` has its own producer factory, ensure these properties are applied to the **DLT's actual producer factory**, not just the default producer.

Notes:

- `acks=all` does not replace replication factor and `min.insync.replicas`.
- Idempotence supports producer protocol retries; it does not deduplicate new business publishes.
- `delivery.timeout.ms` must align with how long the recoverer can wait and your SLOs.
- Producer buffer and batch settings can affect latency.
- Serializers must be compatible with both normal records and failed payloads routed to the DLT.
- DLTs can contain sensitive data; enforce proper access and retention policies.

## 20. Observing DLT publish failures

Low consumer lag does not guarantee recovery is healthy. If the recoverer does not confirm send results and offsets were committed, DLT failures may no longer show up as source lag.

Signals to monitor:

| Signal | Purpose |
|---|---|
| DLT publish attempts | Volume of records attempted to be sent to DLT |
| DLT publish success | Volume confirmed sent successfully |
| DLT publish failure by exception | Detects authorization, serialization, timeout, metadata errors |
| DLT producer send latency | Detects slow brokers or producers |
| Recovery failure count | Identifies incomplete recoverer runs |
| Source partition lag | Whether source records are stalled by recovery failures |
| DLT incoming rate | Verifies records actually arrive at the DLT |
| DLT consumer lag | Tracks unhandled records sitting on the DLT |
| Oldest unrecovered record age | Detects records held past SLO |
| Rebalance rate | Whether long recovery waits affect polls/group stability |
| Kafka broker ISR/leader status | Identifies infrastructure root causes |

Not every metric shares identical names across Kafka/Spring Kafka versions. Use Micrometer observations, producer metrics, error handler logging, or recoverer instrumentation as appropriate.

Tag metrics by topic, stage, and exception group; avoid using event IDs as metric labels due to very high cardinality. Event IDs belong in logs or traces.

### 20.1. What should recovery logs contain?

A helpful log for on-call engineers usually includes:

- Consumer group, client ID.
- Original topic, partition, offset.
- DLT destination topic and partition.
- Event ID/correlation ID.
- Original listener exception.
- New producer/recoverer exception.
- Wait duration and DLT confirmation outcome.
- Retry attempt or recovery attempt if available.

Never log credentials, access tokens, or entire sensitive payloads. A DLT incident normally needs metadata to trace the path; there is no need to copy full personal data into logs.

## 21. Runbook when DLT publish fails

### Step 1: Identify the failure boundary

Confirm the error occurred while publishing to the DLT, not when the listener processed the source record or when a DLT consumer handled a stored record. Locate the exception from `DeadLetterPublishingRecoverer` or the Kafka producer send result.

### Step 2: Inspect the record and destination

- What are the original topic/partition/offset?
- Which topic/partition did the resolver choose as the DLT destination?
- Does the DLT topic exist with enough partitions?
- Does the producer principal have the required Describe/Write permissions?
- Can the serializer handle the failed record's key/value?

### Step 3: Check Kafka infrastructure

- Does the DLT partition have a leader?
- Does ISR satisfy `min.insync.replicas`?
- Are broker request latency and networking healthy?
- Is the producer hitting metadata timeouts or buffer exhaustion?
- Were there authentication/TLS errors or recent ACL changes?

### Step 4: Keep data safe

If DLT publishing has not been confirmed, do not mark the record recovered or commit offsets just to clear lag. Per policy, let the error handler retry recovery, pause the container, or trigger a durable fallback workflow.

On send timeout, record the outcome as **unknown** and prepare to handle DLT duplicates if the record is redelivered.

### Step 5: Remediate the root cause

Fix the topic, ACLs, serializers, payload size, or broker/ISR depending on the error. Avoid merely raising timeouts or retry counts when the root cause is permanent.

### Step 6: Verify end-to-end

After fixing, verify failed records are written to the DLT, source offsets advance properly, retry/recovery failures drop, and DLT consumers or downstream handlers can read the records. If duplicates occurred, verify by event ID and source metadata.

### Step 7: Close the incident

Document affected record counts, duration the DLT could not accept writes, unrecovered source offsets, records with uncertain outcomes, catch-up duration, and preventive actions.

## 22. Common design mistakes

| Practice | Risk | Remediation |
|---|---|---|
| Calling `KafkaTemplate.send` and treating DLT as succeeded | Future may fail after recoverer returns | Enable appropriate send-result verification |
| Only logging DLT failure and acknowledging source | Silent loss if DLT never wrote | Propagate error back to recovery/error handler |
| Assuming timeout proves DLT was not written | Redelivery may create duplicates | Use event IDs and deduplicate on DLT/replay |
| Skipping DLT topic creation before deploy | Metadata timeouts, publish failures | Provision topics via IaC |
| DLT has fewer partitions than destination partition | Invalid destination or send failure | Provision enough partitions or use a suitable resolver |
| DLT serializer only supports valid objects | Raw bytes from deserialization errors cannot be sent | Use serializers supporting `byte[]` and real payloads |
| Consumer has Read ACL but producer lacks DLT Write ACL | Authorization error during recovery | Verify DLT producer permissions |
| Retrying recovery infinitely on permanent errors | Partition stalls and retry storm | Classify errors, alert, and intervene |
| Enabling `DltStrategy.FAIL_ON_ERROR` to fix DLT producer failures | Confuses DLT handler failure with publish failure | Configure recoverer send-result verification |
| Watching only main topic lag | Misses recovery failures or DLT backlogs | Monitor the entire pipeline |
| Believing idempotent producer prevents DLT duplicates | Redelivery creates a fresh publish | Deduplicate at the business layer |
| Confusing Java `@Transactional` with Kafka transactions | Lacks expected atomicity | Configure Kafka transactions / after-rollback processing properly |

## 23. Pre-production testing checklist

Include functional tests and controlled fault injection:

1. Listener fails and DLT publish succeeds: confirm recoverer completes and offsets follow policy.
2. DLT topic missing: recovery reports an error and source record is not skipped.
3. DLT producer lacks Write ACL: authorization error is observed and alerted.
4. DLT serializer does not support raw `byte[]`: error is clearly reported and not swallowed.
5. DLT broker has no leader or insufficient ISR: verify retries and timeout-exhaustion behavior.
6. DLT send written by broker yet ack lost: verify duplicate handling.
7. DLT publish succeeds yet source offset commit fails: record can redeliver and be handled idempotently.
8. Recoverer fails repeatedly: verify backoff, lag, rebalances, and pause capability.
9. DLT fails when record is too large: confirm payload remediation or fallback path.
10. DLT publish failure distinct from DLT handler failure: verify separate metrics and policies.
11. If using transactions: test recovery transactions, aborts, and offset commits.
12. If using retry topics: test publish failures at both retry-topic hops and final DLT publish.

Testing should not rely on shutting down production brokers or deleting DLT topics on shared clusters. Use isolated Kafka environments, dedicated test permissions/topics, or controlled fault injection.

## 24. Operational configuration checklist

Before putting `DeadLetterPublishingRecoverer` into production, verify:

- Does the recoverer check producer send results and throw when DLT publishing fails?
- Is the send-result wait timeout finite and aligned with producer delivery timeout?
- Does the DLT `KafkaTemplate` have the right serializers, security, and `acks`?
- Does the DLT topic exist with sufficient partitions, replication, ISR, and ACLs?
- Do AckMode and `commitRecovered` policies ensure records are not intentionally skipped when recovery fails?
- Can `DefaultErrorHandler` or `AfterRollbackProcessor` handle recovery failures?
- Can a record be redelivered when DLT fails without duplicating side effects?
- Do DLT records carry event IDs and source metadata for deduplication and investigation?
- Are alerts configured for DLT publish failures, recovery failures, and oldest unrecovered record age?
- Are runbooks ready for permanent errors like ACL/serializer issues and transient errors like broker/ISR outages?
- Is there a safe fallback or pause plan if the DLT cannot accept writes during a prolonged outage?
- Are DLT publish failures distinguished from DLT consumer processing failures?

**Core principle:** A DLT is a safety path for holding failed records, not an operation guaranteed to succeed. If DLT publishing fails, recovery must also be treated as failed under the chosen policy; never keep committing source offsets as though the record were safely stored. When you cannot tell for sure whether the DLT received the record, preserve replayability, tolerate controlled duplicates, and use idempotency to protect business state. That prioritizes data integrity over cosmetic consumer lag metrics.
