# Handling Retries After Handler Failure

## 1. The Problem: The Message Is Marked, Then the Handler Throws an Exception

A service receives a `PaymentEvent` from a broker and uses an **Idempotent Receiver** to avoid recording the same payment twice. Initial flow:

~~~text
Broker message EV-901
  → Idempotent Receiver: check eventId
  → Record marker "EV-901 seen"
  → PaymentHandler: write to ledger
  → Publish result
  → ACK message
~~~

Suppose the handler throws an exception **after the marker was saved** but **before the business logic commits**:

~~~text
T1  Broker sends EV-901 for the first time.
T2  Dedupe check: EV-901 absent → mark "seen".
T3  Handler calls database → fails, business transaction rolls back.
T4  RetryAdvice or broker resends EV-901.
T5  Dedupe check: EV-901 present → treated as duplicate.
T6  Handler may not be called again: work is lost despite never completing.
~~~

This is the **poisoned idempotency marker** bug: a “seen” marker is confused with “successfully processed”. Conversely, if the handler **already committed but the process crashes before ACK**, the broker will also redeliver; without protection, the side effect runs a second time.

~~~mermaid
flowchart TD
    IN["Message arrives / retry"] --> CHECK{"Key exists?"}
    CHECK -->|"No"| MARK["Write SEEN marker"]
    MARK --> WORK["Handler"]
    WORK -->|"Error before commit"| FAIL["Exception / retry"]
    FAIL --> CHECK
    CHECK -->|"Yes"| DROP["Duplicate: may be skipped"]
    DROP --> LOST["Risk of lost processing"]
    WORK -->|"Commit"| DONE["Business completed"]
~~~

**Critical question:** Does the marker represent **message receipt**, **temporary processing ownership**, or **committed business work**? Without defining these semantics accurately, simply increasing retry counts can still break the system.

This article belongs to the **Idempotent receiver** chapter of the **SPRING_INTEGRATION_PATTERN** module, within the path for implementing Enterprise Integration Patterns with Spring Integration: Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, along with testing and observing processing branches.

After this lesson, you will be able to distinguish failure windows; explain the interaction between `IdempotentReceiverInterceptor` and `RequestHandlerRetryAdvice`; use transactions/inbox/outbox or leases/fencing when needed; and test retries after handler failures, broker redeliveries, and external side effects.

## 2. Idempotent Receiver, Deduplication, and Retries Are Not Synonyms

**Idempotent Receiver** is the goal: receiving **the same logical operation** multiple times produces no unintended duplicate business effect. It does not require the handler to be invoked strictly once.

\[
\operatorname{effect}(\operatorname{handle}(m),\operatorname{handle}(m))
=\operatorname{effect}(\operatorname{handle}(m))
\]

| Concept | Responsible For | Does Not Guarantee by Itself |
|---|---|---|
| Idempotent Receiver | Re-receiving messages without causing incorrect side effects | Does not automatically make a broker exactly-once |
| Dedupe selector | Determining whether a key was previously recorded | Does not prove the previous attempt succeeded |
| Retry | Retrying on recoverable errors | Does not know whether a remote side effect already occurred |
| Transaction | Atomic commit/rollback within the transaction manager's scope | Does not roll back HTTP calls or another broker |
| Inbox/processed record | Storing durable received/processed state | Requires exact state semantics and uniqueness |
| Outbox | Storing durable publish intent alongside business commit | Publisher may still emit duplicates |
| Broker ACK | Acknowledgment per transport semantics | Not equivalent to a business commit |

**Detecting a duplicate is only one step.** Deciding whether to **block, return an old result, wait, retry, or quarantine** depends on the actual state of the previous operation.

## 3. Four Failure Windows

~~~text
Receive → Claim/Dedupe → Business handler → Commit → ACK
~~~

| Where Does the Failure Occur? | Business Side Effect | Behavior When Message Returns |
|---|---|---|
| Before claim | Has not occurred | Processed again |
| After claim but before business commit | Has not occurred or uncertain | Valid retry must not be blocked by a “seen” marker |
| After commit but before ACK | Already occurred | Second side effect must be prevented |
| During external API call with lost response | **Unknown** whether remote committed | Reconcile or use the same remote idempotency key |

**An exception does not prove all side effects rolled back.** An HTTP server may commit a payment even though the client timed out; a message producer may succeed even without receiving the broker ACK.

The ordering among marker recording, business transaction, publishing, and acknowledgment determines the safety of the entire flow.

## 4. Choosing Idempotency Keys by Logical Operation

Never use `MessageHeaders.ID` as a long-term business key if a broker/Transformer can recreate the Spring Message with a new ID. Nor should you use `attemptId` or the current timestamp to identify the same logical work.

Example:

~~~text
key = (tenantId, paymentId, operation, revision)
~~~

Or use a unique `eventId` that stays stable across retries **if the contract guarantees one event represents one operation**.

| Field | Role |
|---|---|
| `tenantId` | Separates tenants and permissions |
| `eventId` | Durable event identifier from producer |
| `paymentId` | Business entity |
| `operation` | CAPTURE, REFUND, CANCEL have distinct side effects |
| `revision` | New valid processing pass if needed |
| `attemptId` | Observing attempts; not part of the logical key |
| `MessageHeaders.ID` | Message instance ID, not business identity |

For instance, two operations `CAPTURE` and `REFUND` on the same payment **must not be conflated** simply because they share `paymentId`.

A key is an **identifier, not authorization**. The tenant must be verified from a trusted identity at ingress, not solely from a client-supplied header.

## 5. “Seen” Differs from “Succeeded”

A simple Boolean:

~~~text
processedEvents.contains("EV-901") == true
~~~

does not specify whether the operation is currently:

- being processed by a worker;
- failed prior to commit;
- committed to the ledger;
- waiting on a remote call with an unknown outcome;
- or already published as a result.

A clearer state model:

| State | Meaning | Retry with Same Key |
|---|---|---|
| `NEW` | No record yet | Claim and process |
| `PROCESSING` | A worker holds the lease | Defer/wait; do not run in parallel |
| `SUCCEEDED` | Business outcome committed | Do not repeat side effect; return old result if needed |
| `FAILED_RETRYABLE` | Incomplete, can be retried | Bounded retry |
| `FAILED_PERMANENT` | Must not be automatically reprocessed | Reject/quarantine or return failure |
| `UNKNOWN_OUTCOME` | External side effect may have occurred | Reconcile before blind retry |

When the **marker and side effect share one database transaction**, you can simply persist the **completed record** on commit. With remote services and multi-node workers, a state machine is usually necessary.

## 6. Decision Diagram When Receiving a Duplicate

~~~mermaid
flowchart TD
    IN["Receive message"] --> V{"Validate key, tenant, payload"}
    V -->|"Invalid"| Q["Reject / quarantine"]
    V -->|"Valid"| S{"Operation state?"}
    S -->|"NEW / retryable"| C["Atomic claim"]
    S -->|"PROCESSING with active lease"| WAIT["Defer; avoid concurrency"]
    S -->|"SUCCEEDED"| ACK["ACK / return cached outcome"]
    S -->|"FAILED_PERMANENT"| TERM["Terminal failure"]
    S -->|"UNKNOWN_OUTCOME"| REC["Reconciliation"]
    C --> H["Handler"]
    H -->|"Commit succeeds"| DONE["SUCCEEDED"]
    H -->|"Transient failure"| RETRY["Rollback / retryable state"]
    H -->|"Unknown remote result"| REC
    DONE --> ACK
    RETRY --> C
~~~

A `SUCCEEDED` duplicate and a `PROCESSING` duplicate **must not behave identically**. The former can safely ACK; the latter needs waiting/deferring or lease/recovery logic, and must never return a false success.

## 7. Preferred Option When Possible: A Single Database Transaction

If the **marker, business mutation, and outbox record** all use **the same database and transaction manager**, process as follows:

~~~text
BEGIN TRANSACTION
  INSERT idempotency key if absent
  IF duplicate:
      verify payload fingerprint
      do not execute side effect
  ELSE:
      update ledger / domain tables
      write outbox event
COMMIT TRANSACTION
~~~

When the handler throws an exception **before commit**, **both the marker and the business mutation** roll back. Subsequent retries can claim it again. When business work commits **before ACK**, the committed marker detects redeliveries.

**Condition:** all operations must genuinely participate in the same transaction. `@Transactional` on a JDBC handler **does not roll back an independent Redis marker** or a remote HTTP POST.

## 8. Illustrative SQL: Inbox, Ledger, and Outbox

PostgreSQL example:

~~~sql
CREATE TABLE processed_event (
    tenant_id VARCHAR(48) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    operation VARCHAR(40) NOT NULL,
    payload_fingerprint VARCHAR(128) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, event_id, operation)
);

CREATE TABLE payment_ledger (
    ledger_entry_id UUID PRIMARY KEY,
    tenant_id VARCHAR(48) NOT NULL,
    payment_id VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    amount_minor BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, payment_id, event_id)
);

CREATE TABLE outbox_event (
    outbox_id UUID PRIMARY KEY,
    tenant_id VARCHAR(48) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    payload_json JSONB NOT NULL,
    published_at TIMESTAMPTZ
);
~~~

This schema is purely illustrative; production must specify currency, debit/credit semantics, refund keys, permissions, and retention per domain. Uniqueness on `processed_event` prevents claiming the same event twice; uniqueness on `payment_ledger` acts as a guardrail for the business side effect. The outbox preserves **publish intent** across process crashes.

## 9. Transactional Java Handler with Marker in the Same Database

Java 17+ model:

~~~java
record PaymentEvent(
    String tenantId,
    String eventId,
    String paymentId,
    String operation,
    long amountMinor,
    String payloadFingerprint
) {}

enum ReceiveOutcome { PROCESSED, DUPLICATE }
~~~

Service:

~~~java
@Service
class PaymentReceiver {
    private final ProcessedEventRepository inbox;
    private final PaymentLedgerRepository ledger;
    private final OutboxRepository outbox;

    PaymentReceiver(ProcessedEventRepository inbox,
                    PaymentLedgerRepository ledger,
                    OutboxRepository outbox) {
        this.inbox = inbox;
        this.ledger = ledger;
        this.outbox = outbox;
    }

    @Transactional
    public ReceiveOutcome process(PaymentEvent event) {
        validateAndAuthorize(event);

        // INSERT ... ON CONFLICT DO NOTHING in the same transaction.
        boolean inserted = inbox.insertIfAbsent(
            event.tenantId(), event.eventId(),
            event.operation(), event.payloadFingerprint());

        if (!inserted) {
            inbox.assertSameFingerprint(
                event.tenantId(), event.eventId(),
                event.operation(), event.payloadFingerprint());
            return ReceiveOutcome.DUPLICATE;
        }

        ledger.applyEventOnce(event);
        outbox.recordPaymentProcessed(event);
        return ReceiveOutcome.PROCESSED;
    }

    private void validateAndAuthorize(PaymentEvent event) {
        // Implement schema/domain validation + tenant authorization.
    }
}
~~~

The repositories here are **application-implemented abstractions**, not default Spring Integration types. `insertIfAbsent` relies on a database unique key, such as `INSERT ... ON CONFLICT DO NOTHING` in PostgreSQL. Ensure the repositories **actually share the same transaction manager**.

**Spring proxy:** `@Transactional` takes effect when invoked through a Spring-managed bean; calling `this.process(event)` directly may bypass the proxy. Never catch an exception and return success when domain logic fails, as that can commit a false marker. If business rules require catching, explicitly define the rollback policy.

## 10. Wiring the Handler into Spring Integration Java DSL

~~~java
@Configuration
@EnableIntegration
class PaymentFlow {

    @Bean
    IntegrationFlow paymentFlow(PaymentReceiver receiver) {
        return IntegrationFlow.from("payments.in")
            .handle(PaymentEvent.class,
                (event, headers) -> receiver.process(event))
            .channel("payments.outcomes")
            .get();
    }
}
~~~

This is an example flow with imports omitted. `PaymentReceiver` is a Spring bean with a transaction proxy; `payments.outcomes` needs a real consumer or test channel.

**It is not mandatory to attach `IdempotentReceiverInterceptor` when the handler already has a transactional inbox.** Adding an interceptor that records Redis “seen” **before** the receiver can block retries while the SQL transaction has not yet completed.

## 11. Sequence Diagram: Rollback Before Commit

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant H as Handler
    participant DB as Database
    B->>H: EV-901 attempt 1
    H->>DB: BEGIN + insert marker
    H->>DB: Update ledger
    Note over H: Transient exception
    H->>DB: ROLLBACK marker + ledger + outbox
    B->>H: EV-901 redelivery
    H->>DB: BEGIN + insert marker
    H->>DB: Update ledger + outbox
    H->>DB: COMMIT
    H-->>B: ACK per policy
~~~

The marker does not exist after rollback, so the retry can execute again. For this behavior to hold, rollback must cover both **marker** and **mutation**, not just one of them.

## 12. Sequence Diagram: Commit Before ACK

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant H as Handler
    participant DB as Database
    B->>H: EV-902 attempt 1
    H->>DB: INSERT marker + ledger + outbox
    H->>DB: COMMIT
    Note over H: Crash before broker ACK
    B->>H: EV-902 redelivery
    H->>DB: INSERT ... ON CONFLICT DO NOTHING
    DB-->>H: Duplicate + matching fingerprint
    H-->>B: ACK, do not write ledger again
~~~

This handles **at-least-once delivery** with **effectively-once business effects within the database boundary**. Do not call this global exactly-once unless external services have matching idempotency.

## 13. Same Key with Different Payload Must Be Treated as a Conflict

~~~text
Attempt 1: EV-901, amount=10000, fingerprint=F1
Attempt 2: EV-901, amount=99000, fingerprint=F2
~~~

If `eventId` matches yet the content differs, it may indicate a producer bug, a replay of a different revision, or tampered data. Never treat it as a successful duplicate.

Procedure:

1. Read the fingerprint/schema version stored with the key.
2. Compare with the current **canonical payload** fingerprint.
3. Match → return `DUPLICATE`/cached outcome.
4. Mismatch → `IDEMPOTENCY_KEY_CONFLICT`, reject/quarantine and audit.

Never use Java's `Object.hashCode()` as a durable payload fingerprint across restarts/processes. For cryptographic hashes, canonicalize field ordering, numeric formatting, and schema version; avoid logging raw sensitive data.

## 14. IdempotentReceiverInterceptor: Detecting Duplicates Before the Handler

Spring Integration provides `IdempotentReceiverInterceptor`, a request-handler advice backed by a `MessageSelector`, often paired with `MetadataStoreSelector` and `ConcurrentMetadataStore` to detect previously seen keys.

Illustrative configuration approach:

~~~java
@Bean
IdempotentReceiverInterceptor idempotentAdvice(
        ConcurrentMetadataStore store) {
    MetadataStoreSelector selector = new MetadataStoreSelector(
        message -> {
            PaymentEvent event =
                (PaymentEvent) message.getPayload();
            return event.tenantId() + ":" + event.eventId()
                + ":" + event.operation();
        },
        store);
    return new IdempotentReceiverInterceptor(selector);
}
~~~

This example illustrates the API; verify constructor and strategy signatures against your actual Spring Integration version. Keys require unambiguous delimiters/validation per domain contract, not raw concatenation of arbitrary client strings.

**Danger point:** an **accept-once** style selector may store the key **the moment the message is accepted**, **before the handler finishes**. If the metadata store is independent of the business transaction, the marker persists after a handler exception and retries may be flagged as duplicates.

Duplicate behavior depends on interceptor configuration: it may mark a duplicate header, route to a discard channel, or throw an error per options. **Never assume duplicates are always dropped or the handler never runs.** Test duplicate state, handler invocations, replies, and ACKs directly.

## 15. Redis Metadata Store + PostgreSQL Transaction: Classic Failure Window

~~~text
Redis: putIfAbsent("EV-901", "seen") → success
PostgreSQL: BEGIN + update ledger → exception → ROLLBACK
Retry EV-901:
Redis: putIfAbsent("EV-901", "seen") → exists
→ message may not be reprocessed by handler
~~~

A PostgreSQL rollback **does not automatically delete** the Redis key. TTL only causes the key to vanish after some time, without proving the handler succeeded.

**Never unconditionally delete the marker with `DEL key` after an exception**: another worker may have already reclaimed the key or a remote side effect may have committed. If a claim must be released, use leases/versions and compare-and-set keyed by owner token, or place the marker in an appropriate transaction.

Remedies:

- Put the marker and business side effect in **the same DB transaction**.
- Or use an **inbox with states, leases, and fencing**.
- When external APIs are involved, use **remote idempotency keys and reconciliation**.

## 16. Retry Advice Outside or Inside Idempotent Advice?

Two conceptual orderings:

~~~text
A. RetryAdvice( IdempotentAdvice( Handler ) )

B. IdempotentAdvice( RetryAdvice( Handler ) )
~~~

**A:** every attempt initiated by `RetryAdvice` passes through `IdempotentAdvice`. If the first attempt already recorded “seen”, the second attempt may hit a duplicate before the handler.

**B:** `IdempotentAdvice` runs once before the internal retry loop. Handler retries can proceed, yet **once attempts are exhausted**, the marker may remain and **outer broker redeliveries** will hit a duplicate.

**Reordering advice does not fix the root issue** if a marker is persisted before business commit without rollback or state transitions. Test invocation order, exception/recovery behavior, and the real state backend rather than just reading bean names.

## 17. RequestHandlerRetryAdvice: Bounded Retries, Not Infinite

Spring Integration provides `RequestHandlerRetryAdvice` to attach retries to a handler. `RetryTemplate` example:

~~~java
@Bean
RequestHandlerRetryAdvice handlerRetryAdvice() {
    RetryTemplate template = new RetryTemplate();
    template.setRetryPolicy(new SimpleRetryPolicy(3));

    FixedBackOffPolicy backoff = new FixedBackOffPolicy();
    backoff.setBackOffPeriod(200);
    template.setBackOffPolicy(backoff);

    RequestHandlerRetryAdvice advice =
        new RequestHandlerRetryAdvice();
    advice.setRetryTemplate(template);
    return advice;
}
~~~

`SimpleRetryPolicy(3)` here targets **three total attempts**, not three additional retries. This code explains the mechanism; production must classify exceptions, set deadlines, recovery callbacks, jitter/backoff, and position the advice properly in the flow.

**RetryAdvice only catches exceptions within the advice's boundary.** If the handler hands off the task to an `ExecutorChannel`/broker and returns, subsequent exceptions belong to another error boundary; advice around a publisher will not retry consumer errors.

## 18. Which Errors Should Retry vs. Yield a Terminal Outcome?

| Error | Sensible Policy |
|---|---|
| DB deadlock, transient connection loss | Bounded retry, new transaction |
| HTTP 503/429 with retry contract | Backoff and quota, respecting deadline |
| HTTP timeout, remote outcome uncertain | Reconcile or retry with the same remote key |
| Invalid schema/payment amount | Reject/quarantine, do not retry forever |
| Unauthorized tenant | Security failure, do not retry like a network error |
| Same idempotency key with different payload | Conflict, stop processing |
| Duplicate already SUCCEEDED | Do not repeat side effect, ACK/cached reply |
| PROCESSING with active lease | Controlled defer/requeue |
| Permanent business rejection | Persist terminal failure and return outcome |

Retrying permanent errors endlessly can trigger **retry storms** and keep the inbox stuck indefinitely. Distinguish **structured failure outcomes** from exceptions that lose replies.

## 19. External HTTP Calls: Database Transactions Do Not Cover External Side Effects

A handler executes:

~~~text
BEGIN local DB transaction
  INSERT inbox marker
  POST /payments/capture to provider
  UPDATE payment state
COMMIT local DB
~~~

If the remote provider **already captured** but the connection drops before the client receives the response, the local transaction may roll back while money **was already captured**. Retrying with a new remote operation ID could capture a second time.

**A JDBC rollback does not roll back a committed HTTP request**. When side effects sit outside the local transaction:

1. Record a **durable operation intent** with the logical idempotency key.
2. Reuse **the same remote idempotency key** across retries when supported by the provider.
3. If the response is lost, query remote status by operation ID/key.
4. Only mark `SUCCEEDED` after the outcome is verified.
5. If the outcome is uncertain and the remote lacks idempotency/query APIs, **do not blindly retry POST**; route to reconciliation/manual review.
6. Use compensation/corrections when permitted by the domain, never assuming every external side effect is reversible.

An HTTP client timeout only means **the client did not receive a response**, not that the remote server did nothing.

## 20. State Machine When One Atomic Transaction Is Not Possible

A durable inbox record can hold:

~~~text
logical_key
tenant_id
payload_fingerprint
state: NEW | PROCESSING | SUCCEEDED | FAILED_RETRYABLE
     | FAILED_PERMANENT | UNKNOWN_OUTCOME
attempt_count
lease_owner
lease_until
fencing_version
remote_operation_id
result_reference
updated_at
~~~

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> PROCESSING: claim + lease
    PROCESSING --> SUCCEEDED: verified commit
    PROCESSING --> FAILED_RETRYABLE: safe transient failure
    PROCESSING --> UNKNOWN_OUTCOME: remote result unknown
    PROCESSING --> FAILED_PERMANENT: nonretryable error
    FAILED_RETRYABLE --> PROCESSING: bounded retry
    UNKNOWN_OUTCOME --> PROCESSING: reconciled, safe retry
    SUCCEEDED --> [*]
    FAILED_PERMANENT --> [*]
~~~

Every critical transition must be atomic or conditional. A `PROCESSING` claim does not mean completion. When that state exists with an unexpired lease, duplicates must **wait/defer**, never running in parallel and never ACKing as a success without durable responsibility.

## 21. Leases and Fencing: When a Worker Dies or Runs Too Long

Two workers may receive the same message:

~~~text
W1: claim EV-901 token=8 → PROCESSING
W2: sees PROCESSING token=8 → defer

W1 pauses for a long time, lease expires.
W2: reclaims token=9 → processes.
W1 wakes up: tries to mark SUCCEEDED with token=8.
Store must reject W1.
~~~

A conditional update:

~~~sql
UPDATE inbox_operation
SET state = 'SUCCEEDED',
    updated_at = NOW()
WHERE logical_key = :key
  AND state = 'PROCESSING'
  AND fencing_version = :expected_token;
~~~

If affected rows is 0, the worker lost completion rights. Never update state by `logical_key` alone without checking owner/version.

**Local fencing does not stop remote side effects**: the old worker could still send an HTTP request after its lease expired. External systems also need the same idempotency key or version/fencing checks to prevent double side effects.

Lease TTL **is not a command killing the worker**. Measure lock age, renewals, reclaims, and handle errors when two workers run simultaneously.

## 22. Handling `UNKNOWN_OUTCOME` After Timeouts

~~~text
POST /capture key=CAPTURE-901
  → Provider committed.
  → Network dropped before HTTP response.
  → Client threw timeout.
~~~

Do not immediately transition to `FAILED_RETRYABLE` and issue a new capture request under a new key. A dedicated `UNKNOWN_OUTCOME` state lets the workflow **reconcile**.

| Provider Supports | How to Handle |
|---|---|
| Idempotency key with stable contract | Retry with **the same key** within the provider's committed window |
| Operation/status query API | Query status, persist local outcome after verification |
| Webhook event with operation ID | Wait for matching correlated callback with a deadline/reconciliation |
| Neither idempotency nor query API | Escalate/manual review; avoid retrying dangerous side effects |

Preserve the payload fingerprint: same key with a different amount/currency must never be treated as a harmless retry.

## 23. Transactional Outbox: Never Losing Results on Pre-Publish Crash

Another failure mode:

~~~text
Ledger COMMIT succeeds.
Process crashes before publishing PaymentProcessed.
Broker redelivery is deduplicated because event is already SUCCEEDED.
Downstream never receives the result event.
~~~

**Transactional Outbox** persists the publish intent in the same transaction as the ledger and inbox:

~~~mermaid
flowchart LR
    I["Incoming event"] --> TX["Database transaction"]
    TX --> P["processed_event"]
    TX --> L["payment_ledger"]
    TX --> O["outbox_event"]
    O --> PUB["Outbox publisher"]
    PUB --> BROKER["Broker"]
    BROKER --> C["Idempotent downstream consumer"]
~~~

The outbox publisher reads unpublished records, sends them, and marks them published. If the publisher crashes **after sending but before marking published**, the same outbox event may be resent. Downstream receivers still need deduplication by durable event ID.

Outbox does not provide global exactly-once; it ensures **publish intent is not lost** after a local business commit. If ordering per payment is needed, add an aggregate version/sequence and key-based partitioning policy.

## 24. ACK, Requeue, and DLQ Must Align with Durable State

Kafka/AMQP/JMS adapters have different ACK modes and error handlers; no single `ack()` line fits all of them.

| Outcome | Typical Action to Consider |
|---|---|
| `PROCESSED` + transaction committed | ACK |
| `DUPLICATE_SUCCEEDED` + matching fingerprint | ACK or return cached response |
| Transient failure before commit | Bounded retry, nack/requeue with backoff |
| `PROCESSING` held by another worker | Bounded defer; avoid hot retry loops |
| Permanent validation/authorization error | Quarantine/DLQ, ACK per contract |
| `UNKNOWN_OUTCOME` | Persist durable reconciliation intent; ACK only once responsibility is durably transferred |

**Never unconditionally ACK when a handler throws an exception** if that leaves the message with no recovery source. Equally, never infinitely requeue messages with bad data or permanent conflicts.

If the workflow hands off to a durable coordinator, ACKing once durable intent is recorded can be valid even before the side effect finishes; clearly define this as **async accepted**, not `SUCCEEDED`.

## 25. Error Channel and Asynchronous Boundaries

A handler called from a `DirectChannel` can throw exceptions back to the caller. With an `ExecutorChannel`, poller, or broker listener, exceptions may occur **after upstream `send()` has already returned**:

~~~mermaid
flowchart TD
    IN["Input"] --> B{"Execution boundary"}
    B -->|"Synchronous"| H1["Handler on caller thread"]
    B -->|"Asynchronous"| H2["Handler on worker thread"]
    H1 -->|"Exception"| E1["Caller / Retry advice"]
    H2 -->|"Exception"| E2["Error channel / container recoverer"]
    H1 -->|"Commit"| OK1["Reply / ACK policy"]
    H2 -->|"Commit"| OK2["Async terminal state / ACK"]
~~~

To handle errors properly:

1. Verify `RetryAdvice` **wraps the exact handler throwing the exception**.
2. Check whether the error handler/container receives `failedMessage` and the business idempotency key.
3. Ensure failures update/roll back the inbox per allowed state transitions.
4. Distinguish failure outcomes sent to a Gateway/Aggregator from infrastructure errors triggering retries.
5. Ensure ACK/DLQ never accidentally drops work still in `PROCESSING`.

**An error channel does not automatically clear a SEEN marker or finalize an inbox record.** An explicit responsible component and transaction/recovery policy are required.

## 26. Retries Exhausted: Never Return a False Success to Stop the Loop

~~~text
EV-901:
  Attempt 1 → DB timeout
  Attempt 2 → DB timeout
  Attempt 3 → DB timeout
  → RETRY_EXHAUSTED
~~~

Once attempts are exhausted:

- Record a structured error and transition truthfully to `FAILED_RETRYABLE`/`UNKNOWN_OUTCOME`.
- Release the claim or let the lease expire **conditionally**, never deleting markers irresponsibly.
- Route the message to a DLQ/longer-delay retry queue if permitted by contract.
- Assign an owner, deadline, and safe replay procedure.
- If a Gateway requires a reply, return an infrastructure failure/pending status rather than `SUCCESS`.

Never catch an exception and return a success result merely to get the message ACKed. Doing so can commit the marker while business work never finished.

## 27. Splitter and Aggregator: One Failing Child Can Stall a Group Forever

~~~text
Batch B-101 → Splitter → L1, L2, L3
L1 → SUCCESS
L2 → handler throws → retry / idempotent check
L3 → SUCCESS
               ↓
            Aggregator
~~~

If an Idempotent Receiver marks L2 before processing and then blocks retries, the Aggregator sees only two outcomes. The system must separate:

- **Parent correlation** such as `batchId`/`processingGroupId`.
- **Member ID** such as `lineId`.
- **Idempotency operation key** such as `(tenant,batch,revision,lineId,operation)`.
- **Attempt ID** solely for tracing.

Never share a single idempotency key across all children of a batch, or the second child will be treated as a duplicate of the first.

When a member exhausts retries, it can emit a `LineOutcome(success=false, reasonCode=...)` carrying **the same correlation/member ID**, allowing the Aggregator to conclude `PARTIAL/FAILED`. However, if the member is still retryable, policies must prevent a stale terminal failure and a late success from producing two conflicting outcomes in the group.

**Releasing on `group.size()==N` is not enough** if duplicate L1 is counted twice; distinct member IDs and a group manifest are required.

## 28. Gateway Timeout Does Not Cancel an In-Flight Operation

~~~text
Gateway.submitPayment()
  → handler is processing
  → caller times out after 2 seconds
  → handler may commit at second 3
~~~

If the caller sees a timeout and generates a **new eventId** for the same operation, the receiver may treat it as a new operation and execute twice. For the same logical request, callers must reuse **the same idempotency key**.

Appropriate request–reply states:

- `SUCCEEDED` → return the cached result.
- `PROCESSING` → return PENDING/202 or expose a status endpoint per contract.
- `UNKNOWN_OUTCOME` → reconcile; never report definite failure.
- `FAILED_PERMANENT` → return a clear business failure.

`replyChannel` is the return address of a single invocation, **not a business idempotency ID**. It can change across retries or not be serializable across a broker.

## 29. Router, Transformer, Content Enricher, and Retries

| Endpoint | Risk | Required Design |
|---|---|---|
| Router | Policy change sends replay to another branch | Pin route/policy version when deterministic replay is needed |
| Filter | Drops a child and leaves Aggregator missing an outcome | Emit correlated rejection/failure message |
| Transformer | Creates new Message, drops `eventId` | Preserve stable business key in payload/headers |
| Content Enricher | Repeated lookup requests or misattached replies | Child request ID + parent correlation |
| Splitter | Replay re-emits N children | Separate idempotency key per child |
| Aggregator | Duplicates inflate count or trigger double release | Manifest, unique members, completed-group policy |
| Gateway | Timeout followed by caller retry with new key | Stable client request ID |

**Do not rely on `MessageHeaders.ID`** when a Transformer builds a new Spring Message or a broker redelivers. Across transports, use a contract-defined business identity with tenant scope and schema version.

## 30. Metadata Store Disconnected: Failing Open Can Duplicate Side Effects

When `ConcurrentMetadataStore` cannot be read or written, the dangerous pattern is:

~~~java
try {
    dedupeStore.claim(key);
} catch (StoreUnavailableException failure) {
    handler.process(event); // Skips duplicate check!
}
~~~

If multiple consumers receive the same message, they can run in parallel and double-charge.

Safe policy:

- **Fail closed/defer** until the store recovers, with backoff/deadlines.
- Route to a durable quota-bounded queue for later retry.
- Or let a thoroughly verified domain database uniqueness constraint enforce idempotency.

Never replace a distributed idempotency store with per-node in-memory maps when multiple nodes receive redeliveries without protection at the side-effect destination.

## 31. TTL and Retention of Idempotency Keys

`SUCCEEDED` keys should be retained based on:

1. Broker redelivery/replay window.
2. How long producers may retry the same request ID.
3. Remote provider idempotency key retention.
4. Audit and business requirements.

Too short a TTL: old duplicates arrive post-expiry and get reprocessed. Infinite TTL: the store bloats and reused keys could block valid new operations.

Different states need different retention: `PROCESSING` uses **leases + recovery**, `UNKNOWN_OUTCOME` requires **reconciliation**, `SUCCEEDED` keeps a tombstone through the anti-replay window, and `FAILED_PERMANENT` may require longer auditing.

**Never treat TTL as proof that “the handler stopped running”.** A paused worker can resume after its lease expires; fencing and remote idempotency resolve contention.

## 32. Testing Rollback After Handler Failure

An integration test with a real database:

~~~java
@Test
void exceptionBeforeCommitDoesNotPoisonRetry() {
    PaymentEvent event = sampleEvent("EV-901");
    ledger.failNextUpdate();

    assertThrows(TransientDataAccessException.class,
        () -> receiver.process(event));

    assertFalse(inbox.existsCommitted(
        event.tenantId(), event.eventId(), event.operation()));
    assertEquals(0, ledger.countFor(event.eventId()));

    assertEquals(ReceiveOutcome.PROCESSED,
        receiver.process(event));
    assertEquals(1, ledger.countFor(event.eventId()));
    assertEquals(1, outbox.countFor(event.eventId()));

    assertEquals(ReceiveOutcome.DUPLICATE,
        receiver.process(event));
    assertEquals(1, ledger.countFor(event.eventId()));
}
~~~

`sampleEvent`, `failNextUpdate`, and repository test methods are **application-defined test fixtures**. Use a real test DB/transaction manager or Testcontainers to test rollback; Java mocks cannot prove the marker and ledger share a transaction.

**Careful:** if the test method itself is annotated with `@Transactional`, calls may run inside the same test transaction and hide real commit/rollback boundaries. Separate transaction boundaries as in production.

## 33. Testing Crash After Commit but Before Broker ACK

Scenario:

~~~text
Attempt #1:
  processed_event + ledger + outbox COMMIT
  simulate crash before ACK

Attempt #2:
  redelivery with same eventId, different Spring Message ID
  receiver returns DUPLICATE
  ledger count unchanged
~~~

Verify:

- Inbox marker and ledger still exist after restart.
- Same key + same fingerprint is a safe duplicate.
- Same key + different fingerprint is a conflict.
- Outbox record exists for the publisher to resume sending.
- Broker ack/redelivery does not trigger a second business mutation.

Merely calling the receiver twice does not prove ACK behavior. To test a real adapter, use a broker/container and inject crashes at the appropriate boundary.

## 34. Testing Concurrency and Lease/Fencing

To expose race conditions, use a `CountDownLatch` or barrier across two workers:

~~~text
W1: INSERT EV-901 → pending
W2: INSERT EV-901 → conflict / wait
W1: UPDATE ledger + COMMIT
W2: detects completed duplicate

Expected:
  inbox committed rows = 1
  ledger entries       = 1
  outbox intents       = 1
~~~

Another test for the state machine:

~~~text
W1 claims token 8 → lease expires
W2 reclaims token 9 → COMMIT
W1 tries mark SUCCEEDED(token 8) → affected rows = 0
~~~

Test with real transactions/unique constraints. Running twice sequentially does not expose races. For remote side effects, add a test using the same idempotency key when both workers call the provider.

## 35. Testing Remote Timeouts and Unknown Outcomes

Fake provider:

~~~text
POST /capture idempotencyKey=K
  → provider commits capture
  → client receives no response
  → timeout

Retry POST /capture idempotencyKey=K
  → provider returns old result
  → total captures = 1
~~~

Expectations:

1. Never generate a new `K` when retrying the same logical operation.
2. `UNKNOWN_OUTCOME` is reconciled and transitioned to a terminal state.
3. No double charges, even when the first response is lost.
4. Conflicting payloads with the same `K` are rejected.
5. If the provider lacks idempotency support, never auto-retry dangerous capture commands without a verification protocol.

## 36. End-to-End Test Matrix

| Test Case | Fault Injection | What It Proves |
|---|---|---|
| Happy path | No error | One marker, one side effect, one outbox intent |
| Pre-claim failure | Store write fails | No lost messages |
| After marker/before commit | Ledger throws exception | Marker rolls back or enters retryable state |
| After commit/before ACK | Crash | Redelivery does not double-mutate |
| Same key/different content | Different fingerprint | Conflict/quarantine |
| Retries exhausted | All attempts fail | No false success or stuck marker |
| Independent Redis marker | DB rollback | Detects and avoids poisoned markers |
| Concurrent duplicates | Two workers | Unique owner/commit |
| Lease expiry | Old worker wakes up | Fencing rejects stale completion |
| Remote timeout | Provider already committed | Reconciles with same remote key |
| Broker redelivery | New Spring Message ID | Business key remains stable |
| Splitter child retry | One line fails | Does not block other members |
| Aggregator release | Duplicate result | Does not count duplicate as a new member |
| Gateway timeout | Caller retries with same key | Does not create a new operation |
| Async error | Worker throws exception | Error path preserves correlation |
| Store unavailable | Dedupe backend down | Does not dangerously fail open |
| Restart | App killed | Recovers from durable state |
| Late reply | Reply after completed | No double publish |
| TTL expiry | Replay outside window | Explicit retention/replay contract |

**Specifically:** with `IdempotentReceiverInterceptor`, test duplicate headers, discard/exception/reply behavior, advice ordering, and metadata commit timing directly. Never infer semantics from the interceptor's name.

## 37. Observability: Detecting “Retries Ran While the Handler Didn't”

| Suggested Metric | Purpose |
|---|---|
| `receiver.message.received.count` | Incoming messages and attempts |
| `receiver.idempotency.claim.count` | New claims |
| `receiver.idempotency.duplicate.count` | Duplicates |
| `receiver.idempotency.conflict.count` | Same key, different payload |
| `receiver.inbox.processing.count` | In-flight operations |
| `receiver.handler.failure.count` | Business handler failures |
| `receiver.retry.attempts.count` | Retry amplification |
| `receiver.retry.exhausted.count` | Unrecovered operations |
| `receiver.unknown.outcome.count` | Uncertain external side effects |
| `receiver.lease.expired.count` | Expired leases |
| `receiver.fencing.rejected.count` | Stale worker state updates |
| `receiver.business.committed.count` | Actual business commits |
| `receiver.outbox.pending.count` | Unpublished intents |
| `receiver.ack.failure.count` | Transport redelivery risk |
| `receiver.inbox.state.age` | Operations stuck in a state |

These are **recommended metrics**, not default Spring Integration meters. Tags should have low cardinality such as `flow`, `operation`, `outcome`, and `reasonCode`; never use `eventId`/`paymentId`/`idempotencyKey` as dynamic metric tags.

Controlled structured logs/tracing:

~~~text
eventId=EV-901
operation=CAPTURE
attempt=2
inboxState=FAILED_RETRYABLE
handlerPhase=BEFORE_COMMIT
transactionOutcome=ROLLED_BACK
brokerRedelivery=true
reasonCode=DB_DEADLOCK
~~~

Goal: answer **whether the marker committed, whether the side effect committed, who holds the lease, and what decided ACK/retry**. Never log raw payment data, credentials, or secret idempotency tokens.

## 38. Runbook When a Message Is Treated as Duplicate Before Completion

1. **Identify the logical key** from verified tenant/event/operation/revision.
2. **Inspect inbox/metadata:** is the actual state `SEEN`, `PROCESSING`, or `SUCCEEDED`?
3. **Cross-check the ledger:** did the side effect and outbox record commit?
4. **Check transactions:** was the marker inside the same transaction as the handler?
5. **Check the advice chain:** is `RetryAdvice` inside or outside `IdempotentAdvice`?
6. **Check the error path:** did the failure happen before commit, after commit, or at a remote API?
7. **Check ACK/DLQ:** was the message ACKed without durability or requeued endlessly?
8. **Check locks/leases:** does another worker hold the lease or did it expire?
9. **Reconcile the external outcome** if an API timed out with an unknown commit status.
10. **Recover conditionally:** retry when certain no effect occurred or with the same remote key; if already committed, complete/return cached reply.
11. **Check pending Aggregator groups** if this message was a child outcome.
12. **Add a regression test** reproducing that exact failure window.

**Never flush all Redis metadata keys and replay everything**. Other keys may be protecting already-committed operations; indiscriminate deletion risks duplicate charges or double events.

## 39. Lab Exercise: Three Ways to Handle Retries After Handler Failure

Build **PaymentEventReceiver** in three versions:

1. **Intentionally flawed:** use a `seen(eventId)` metadata store separate from the DB, inject an exception after marking; observe retries getting treated as duplicates.
2. **Transactional:** use `processed_event + payment_ledger + outbox_event` in one transaction; pre-commit errors roll back everything.
3. **External operation:** use inbox state/lease/fencing, remote idempotency keys, and reconciliation.

Then:

4. Attach `RequestHandlerRetryAdvice` with three attempts to the appropriate flow.
5. Test both advice orderings with `IdempotentReceiverInterceptor`; count selector and handler invocations.
6. Use PostgreSQL/Testcontainers to verify constraints and rollbacks.
7. Inject errors **after marker, before ledger**, **after ledger, before COMMIT**, and **after COMMIT, before ACK**.
8. Create two messages with the same key and different payloads to test conflict detection.
9. Send two copies of the same event concurrently using a latch/barrier.
10. Test lease timeouts and fencing out the stale worker.
11. Simulate the remote server committing while the response is lost.
12. Test broker redelivery when the Spring Message ID changes.
13. Connect Splitter/Aggregator and produce a failure outcome for one child.
14. Build dashboards for retries, duplicates, inbox state age, unknown remote outcomes, and outbox backlog.

**Completion criteria:** retries after pre-commit failures **are not wrongly blocked by markers**; redeliveries after commit **do not repeat side effects**; payload conflicts are detected; remote timeouts are reconciled; no claims hang forever; all ACK/DLQ states are traceable.

## 40. Common Misconceptions

**“Seeing the message means it was processed successfully.”** False. Claim and commit are different.

**“IdempotentReceiverInterceptor automatically rolls back markers when a handler fails.”** Never assume; it depends on the selector, metadata store, and transaction.

**“Just reordering RetryAdvice and IdempotentAdvice is enough.”** Not if the marker survives exhausted retries or broker redeliveries.

**“A Redis marker rolls back automatically with `@Transactional` on a JDBC handler.”** Not unless both systems participate in the same transaction.

**“Catching exceptions and returning success makes retries safe.”** It can commit the marker while skipping the work.

**“Duplicates must always throw an exception.”** No. A `SUCCEEDED` duplicate can ACK/return cached results; a `PROCESSING` duplicate should defer.

**“An HTTP timeout means the remote side did not commit.”** False; the outcome may be unknown.

**“Using a new UUID on every retry is safer.”** False if that UUID is the remote/business idempotency key.

**“A Gateway timeout automatically cancels the handler.”** Not automatically.

**“An inbox unique constraint guarantees exactly-once HTTP capture.”** No; remote calls need their own idempotency/reconciliation.

**“Outbox guarantees the broker never receives duplicates.”** False; the publisher can redeliver.

**“A broker ACK means payment succeeded.”** Not necessarily: an ACK may only confirm responsibility was durably persisted.

**“A short TTL is always economical and safe.”** False if redeliveries occur after the TTL expires.

**“One in-memory map per JVM suffices for a cluster.”** Not if multiple consumers can handle the same key.

**“Every exception should retry indefinitely.”** False; permanent, authorization, and key-conflict errors require terminal policies.

## 41. Key Takeaways

When a handler fails, **an Idempotent Receiver must never treat a “received” marker as proof of “completed”**. If a metadata key is written before the handler and survives rollback, retries can be blocked even though the work never succeeded. If business work already committed before ACK, redeliveries must be prevented from repeating side effects.

For operations within **one database**, prefer **atomic transactions** covering the marker, business mutation, and outbox. For external operations, use **inbox state machines, atomic claims, leases/fencing, remote idempotency keys, and reconciliation**. The ordering of `IdempotentReceiverInterceptor` and `RequestHandlerRetryAdvice` must be tested, yet **never substitutes for a proper commit protocol**.

Keep business keys stable across Router, Filter, Transformer, Splitter, Gateway, and brokers; separate group/member keys from attempt IDs; handle errors according to sync/async boundaries and ACK/retry policies. The goal is to **retry only unfinished work, recognize committed work, and neither lose nor duplicate tasks**.

### References

- Spring Integration Reference, **Idempotent Receiver**: https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html
- Spring Integration Reference, **Retry Advice**: https://docs.spring.io/spring-integration/reference/handler-advice/classes.html
- Spring Integration Reference, **Metadata Store**: https://docs.spring.io/spring-integration/reference/metadata-store.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Enterprise Integration Patterns, **Idempotent Receiver**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html
