# Non-rollbackable side effects

In a Spring Kafka system, a message can cause the application to perform multiple actions: updating an order in the database, charging via a payment gateway, sending an email, creating a shipment, or calling another service's API. Database changes can usually roll back when a transaction fails. However, an action that already happened outside the transaction does not automatically vanish just because the application rolls back.

This is the core problem of **non-rollbackable side effects**. When processing a message, the system must account for cases where the external action succeeded yet the application did not persist the outcome in time. Kafka may redeliver the message, the listener may run again, and a retry may trigger the action a second time. For operations like sending email, issuing tickets, creating accounts, or charging money, that repetition can cause real-world consequences.

The design goal is not to assume everything will run only once. The goal is to ensure each business operation has a stable identity, track the action's state, handle message redelivery safely, and provide reconciliation when outcomes are unclear.

## 1. What is a non-rollbackable side effect?

A side effect is a change produced by a program beyond a function's return value. Some side effects can be reversed by a transaction or a compensating action. Others, once executed, cannot be fully undone.

| Action | Directly rollbackable? | Risk when repeated |
|---|---|---|
| Updating a record in the same DB transaction | Yes, before commit | Usually protected by DB within the transaction |
| Sending an email to a customer | No | Customer may receive multiple emails |
| Sending SMS or push notification | Not guaranteed | Sent messages may not be recallable |
| Charging via a payment provider | Not in the DB rollback sense | Customer may be charged twice |
| Creating a shipment with a carrier | Usually no | Multiple tracking numbers or pickups may be created |
| Granting permissions or creating an account in an external system | Depends on API | Duplicate resources or wrong permissions |
| Writing an event to Kafka | Cannot erase already-read history in general | Consumers may process the event before a compensating event |

Some APIs offer cancel, refund, or revoke operations. Those operations are usually **new actions** with their own rules and outcomes. They do not make it as if the original action never happened. For example, a refund is a new financial transaction; it is not a rollback of the prior charge.

## 2. Why do retries create risk?

Suppose a consumer receives an `OrderApproved` event and calls an API to charge payment. The sequence might unfold as:

1. Kafka delivers the event to the consumer.
2. Consumer calls the payment provider.
3. Provider successfully charges the card.
4. The connection times out or the consumer process stops before recording the result.
5. The offset is not committed, or a retry mechanism replays the event.
6. The consumer receives the event again and calls the charge API a second time.

From the application's perspective, the first call may look like a mere timeout. Yet a timeout only indicates the application did not receive a response within the wait window; it **does not prove** the provider failed to execute the action.

This is an *unknown outcome* scenario. If the application treats every timeout as a confirmed failure and sends a brand-new request, it can create a duplicate side effect. If the application never resends, it can drop a business operation that the provider genuinely never ran.

Therefore, distinguish three cases:

- **Confirmed success:** received a success response and persisted that result.
- **Confirmed failure:** provider returned a response indicating the action did not execute, such as a declined transaction.
- **Unknown:** timeout, disconnect, process crash, or error occurred between sending the request and persisting the result. This state requires reconciliation or controlled retry.

Do not lump the third case into normal failure handling.

## 3. Guarantee boundaries of Kafka transactions

Kafka supports producer transactions and exactly-once semantics for certain flows residing inside Kafka. For instance, a consumer can read records, produce new records, and commit offsets within the same Kafka transaction. Consumers reading with `isolation.level=read_committed` will not see records from aborted transactions.

This scope is very useful for **Kafka-to-Kafka** flows. However, a Kafka transaction does not automatically wrap an HTTP request, email, SMS, or relational database transaction. If a listener calls a payment provider and the Kafka transaction aborts, the provider receives no rollback signal from Kafka.

Similarly, committing a DB transaction and committing a Kafka offset are two operations on two separate systems unless the application implements an appropriate distributed coordination mechanism. The DB may commit while the offset does not. Kafka redelivers the event and the listener runs again. Hence, the consumer still needs safe duplicate handling.

Clarify the guarantee actually needed:

| Guarantee | Meaning | Solves external side effects? |
|---|---|---|
| At-most-once | A message may be skipped, not actively reprocessed after acknowledgment | No; actions may be lost |
| At-least-once | Messages are redelivered until acknowledged per config | No; actions may run multiple times |
| Exactly-once within Kafka | Reads, writes, and offsets inside a Kafka transaction are coordinated | Does not automatically extend to HTTP, email, or external DBs |
| Effectively-once at business layer | Multiple deliveries or retries still yield a single business outcome | Achievable with proper idempotency, state tracking, and reconciliation |

In systems with external side effects, the practical approach is usually **at-least-once delivery combined with idempotent processing**. Kafka can redeliver; the application ensures reprocessing does not produce a second business outcome.

## 4. Start with a stable business identity

Each side effect needs an idempotency key representing **one specific business action**. The key must remain identical when the same business action is retried, even if the message is replayed or routed through a retry topic.

For example, if an order may only be charged once per payment attempt, the key might be:

```text
order:ORD-8421:charge:payment-attempt-1
```

If business rules allow a customer to retry payment after a prior decline, each valid attempt must have its own identifier, such as `payment-attempt-2`. Never reuse one shared key across distinct attempts, or a new payment attempt could be mistaken for the old one.

Common choices:

- Stable `eventId` generated by the producer: suitable when one event maps to one side effect.
- Business ID plus action type: e.g., `orderId + effectType`, suitable when one event triggers multiple distinct action types.
- Business execution attempt ID: suitable when the same order has multiple valid payments, shipments, or refunds.

Do not use Kafka offsets as idempotency keys for side effects. An offset is meaningful only within a specific partition; the same event when replayed, copied, or routed through a retry topic can have a different offset. Idempotency keys must be business-driven, independent of a record's current position in Kafka.

If the provider supports idempotency keys, send the same key on every attempt of the same action. Providers usually store outcomes by key and return the prior result on equivalent retries. Read the API contract carefully: key retention duration, uniqueness scope, handling of mismatched payloads, and retryable error types vary across providers.

A crucial rule is **the same key must always represent the same request content**. Store a payload hash as well. If a new request reuses an old key with a changed amount, currency, or recipient, the system must detect a conflict instead of silently treating it as a valid retry.

## 5. Record intent before calling the external system

Do not place a non-rollbackable HTTP call inside a long DB transaction and expect a DB rollback to undo the HTTP call. Instead, record that the system intends to execute the action, commit that intent, and let a worker perform the side effect in a separate step.

A side-effect tracking table can store:

| Field | Purpose |
|---|---|
| `effect_key` | Stable idempotency key with a unique constraint |
| `event_id` | Link to the source event |
| `effect_type` | Action type, e.g., `CHARGE_PAYMENT` |
| `request_hash` | Detects same key with differing payload |
| `request_payload` | Content to resend or reference data to reconstruct the request |
| `status` | Current status of the action |
| `provider_reference` | Transaction or resource ID returned by provider |
| `response_payload` | Result persisted for processing or reconciliation |
| `attempt_count` | Number of attempts executed |
| `next_attempt_at` | Earliest timestamp allowed for the next attempt |
| `lease_until` | Expiration time of the worker's processing claim |
| `last_error` | Most recent error for investigation |

Condensed PostgreSQL schema example:

```sql
CREATE TABLE external_effect (
    effect_key         varchar(200) PRIMARY KEY,
    event_id           varchar(100) NOT NULL,
    effect_type        varchar(80) NOT NULL,
    request_hash       varchar(128) NOT NULL,
    request_payload   jsonb NOT NULL,
    status             varchar(24) NOT NULL,
    provider_reference varchar(200),
    response_payload   jsonb,
    attempt_count      integer NOT NULL DEFAULT 0,
    next_attempt_at    timestamptz,
    lease_until        timestamptz,
    last_error         text,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_external_effect_pending
    ON external_effect (next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'RETRYABLE');
```

`effect_key` is a unique key preventing two threads from creating two records for the same action. In multi-provider systems, include the provider name in the key or add a unique constraint on `(provider, effect_key)`, depending on the provider's uniqueness scope.

### 5.1. Saving inbox and side-effect intent in the same DB transaction

When the listener receives an event, it can do two things inside one DB transaction:

1. Record `eventId` in the inbox table to detect already-processed events.
2. Create an `external_effect` record in `PENDING` status if that action does not exist yet.

Example inbox table:

```sql
CREATE TABLE consumer_inbox (
    consumer_name varchar(100) NOT NULL,
    event_id      varchar(100) NOT NULL,
    processed_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
```

The listener can invoke a Spring service managed by a DB transaction:

```java
@Service
public class OrderApprovedHandler {
    private final JdbcTemplate jdbc;

    public OrderApprovedHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void recordIntent(OrderApproved event) {
        int inserted = jdbc.update("""
            INSERT INTO consumer_inbox (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """, "billing", event.eventId());

        if (inserted == 0) {
            // This event was previously recorded by the consumer.
            return;
        }

        String effectKey = "order:" + event.orderId()
            + ":charge:" + event.paymentAttemptId();

        jdbc.update("""
            INSERT INTO external_effect (
                effect_key, event_id, effect_type, request_hash,
                request_payload, status
            ) VALUES (?, ?, 'CHARGE_PAYMENT', ?, CAST(? AS jsonb), 'PENDING')
            ON CONFLICT (effect_key) DO NOTHING
            """,
            effectKey,
            event.eventId(),
            event.paymentRequestHash(),
            event.paymentRequestJson());
    }
}
```

The listener merely records intent in the DB:

```java
@KafkaListener(topics = "order-approved", groupId = "billing")
public void onOrderApproved(OrderApproved event) {
    orderApprovedHandler.recordIntent(event);
}
```

When `recordIntent` returns, Spring's transaction proxy completes the DB transaction before the service call returns to the listener. Only then does the listener return to the container so the container handles offset acknowledgment per configuration. If the DB transaction fails, the listener throws and the message can be reprocessed. If the DB committed yet the offset did not and the event redelivers, the inbox key prevents creating the intent a second time.

Key condition: writing the inbox and creating the side-effect intent must be in **the same DB transaction**. If the inbox write commits first and creating the intent fails, redelivery could be treated as a duplicate and the action would be lost. If the intent commits first without the inbox, redelivery might still stay safe thanks to the unique constraint on `effect_key`, but data state becomes harder to reason about.

The example above illustrates the core mechanics. In production code, inspect the insert result and payload when `effect_key` already exists. If the key exists with a different `request_hash`, record a business conflict error and handle it explicitly; never ignore that discrepancy.

## 6. Executing side effects with a stateful worker

A separate worker reads `PENDING` or `RETRYABLE` records, holds a processing lease, calls the provider, and persists the result. Claiming records must be safe under concurrent workers. In PostgreSQL, a common implementation is a short transaction using `SELECT ... FOR UPDATE SKIP LOCKED`, updating to `IN_PROGRESS` with `lease_until`, and committing before making network calls.

The sequence should be:

1. Claim a record and set a lease in a short DB transaction.
2. Commit the claim transaction so other workers do not pick up the same work.
3. Call the provider outside the DB transaction, sending `effect_key` as the idempotency key.
4. On success, save `SUCCEEDED`, reference code, and response.
5. If the provider confirms the action did not execute and the error is retryable, save `RETRYABLE` with `next_attempt_at`.
6. If the provider definitively declines, save `FAILED_FINAL`.
7. If a timeout or disconnect leaves the outcome unclear, save `UNKNOWN` and transition to reconciliation.

Never hold row locks or an open DB transaction while waiting on an HTTP response. An external request can take seconds or hang until timeout; holding a transaction throughout increases lock duration, connection contention, and DB bottleneck risk.

Conceptual processing flow:

```java
public void dispatch(ExternalEffect effect) {
    try {
        ChargeResult result = paymentClient.charge(
            effect.requestPayload(),
            effect.effectKey() // same key for all attempts of this action
        );

        effectRepository.markSucceeded(
            effect.effectKey(), result.providerReference(), result.toJson());
    } catch (DefinitivePaymentDecline ex) {
        effectRepository.markFailedFinal(effect.effectKey(), ex.getMessage());
    } catch (TimeoutException | ConnectionException ex) {
        effectRepository.markUnknown(effect.effectKey(), ex.getMessage());
    }
}
```

This example illustrates processing boundaries; exception classification must follow the specific payment client's contract. Not every `4xx` is a terminal failure, and not every `5xx` proves the provider did not execute the action. Know whether the provider may have processed the request before returning an error.

### 6.1. A useful state machine

States should reflect what the system actually knows:

| State | Meaning | Next action |
|---|---|---|
| `PENDING` | Intent persisted, no worker executing yet | Claim to process |
| `IN_PROGRESS` | A worker holds a lease and is executing the action | Wait for result or lease expiry |
| `SUCCEEDED` | Provider confirmed success and result is persisted | Do not re-execute; read result only |
| `RETRYABLE` | Confirmed safe to retry later | Retry on schedule with same idempotency key |
| `UNKNOWN` | Provider may have executed, yet application does not know result | Reconcile before deciding |
| `FAILED_FINAL` | Provider confirmed action cannot or should not be retried | Escalate to business or operations handling |
| `RECONCILING` | Querying provider or reconciling data | Update to succeeded, failed, or continue waiting |

A worker may die after the provider succeeded yet before updating `SUCCEEDED`. When the lease expires, the old record should not automatically revert to `PENDING` and dispatch a new request with a new key. Route it to unknown-state handling. If the provider properly supports idempotency keys, the worker can resend the same request with the same key; if the provider supports querying by reference or business key, query the result first.

Leases help recover abandoned work, yet a lease does not automatically guarantee two workers will never call the provider simultaneously. An old worker may stall longer than the lease and resume while a new worker already claimed the record. Combine leases with fencing/versioning when you need to prevent stale workers from overwriting newer state, and with provider-side idempotency keys to protect external side effects.

## 7. Inbox, Outbox, and Effect Ledger solve different parts

Three design patterns often travel together with distinct responsibilities:

| Pattern | Solves | Does not automatically solve |
|---|---|---|
| Transactional Outbox | DB commits yet Kafka event to publish may be lost or out of sync with state | Consumer duplicates and external non-Kafka side effects |
| Inbox / Idempotent Consumer | An event may be delivered multiple times yet DB changes apply only once | Whether an external API already executed |
| Effect Ledger | Tracks each side effect, idempotency key, outcome, and unknown states | Cannot force a non-idempotent provider to become exactly-once |

### 7.1. Transactional Outbox

When a business operation updates the DB and must emit a Kafka event, write the business change and an outbox row in the same DB transaction. A publisher reads the outbox and sends the event to Kafka. After publishing succeeds, the publisher marks the outbox row sent.

The publisher may die after Kafka received the event yet before the DB marks `published`. On restart, the publisher sends the event again. Hence, outbox events need stable IDs and consumers must remain idempotent.

Outbox ensures event-publishing intent is durably stored alongside DB changes. It does not turn a payment API or email into part of a Kafka transaction.

### 7.2. Inbox / Idempotent Consumer

The consumer records `consumerName + eventId` with a unique constraint in the same transaction as the DB changes caused by the event. If the insert produces no new row, the event was already processed and the consumer can finish safely.

The unique constraint is critical protection when multiple instances process concurrently or two deliveries arrive nearly simultaneously. Checking duplicates via `SELECT` then `INSERT` without a constraint invites a race condition: two instances both see no record and both execute business logic.

### 7.3. Effect Ledger

The inbox only proves the consumer recorded the event. It is insufficient to answer "did the provider charge the card?". The effect ledger tracks each external action and its outcome separately. One event can produce multiple effect records, such as creating a shipment and sending a notification, each with its own key and state.

Combining these three patterns cleanly separates: whether business data committed, whether the event was emitted, whether the consumer recorded the event, and what outcome the external side effect reached.

## 8. Retries must depend on error type and side-effect state

Retry is a recovery mechanism, not proof that the prior call never happened. Before retrying, identify which category the error belongs to:

| Scenario category | Example | Appropriate handling |
|---|---|---|
| Definitely never sent request | Validation failed before opening connection | Fix data or mark terminal error |
| Provider explicitly declined, no side effect created | Insufficient funds and API contract confirms no transaction | May retry if conditions change, per business rules |
| Transient error yet provider confirms request was not processed | Rate limit with explicit retry contract | Back off and retry with same key |
| Timeout after sending request | No response received | Mark `UNKNOWN`, query, or retry with idempotency key |
| Provider succeeded yet DB write failed | Process stopped after receiving response | Reconcile or call again with same key to retrieve prior result |
| Invalid payload or business rule violation | Invalid amount, recipient, or status | Do not retry blindly; route to error handling |

Apply exponential backoff, jitter, and attempt limits to avoid spiking traffic onto the provider. Respect `Retry-After` if returned by the API and allowed by contract. Persist the next-attempt timestamp instead of sleeping threads while waiting.

In Spring Kafka, retry topics, retry interceptors, or dead-letter topics help manage message redelivery. However, they do not replace idempotency. A re-invoked listener can still call the API again. When sending an event to a DLT, preserve `eventId`, `effectKey`, and correlation metadata so investigation, reconciliation, and replay stay safe.

Do not automatically replay a DLT for a side effect in `UNKNOWN` state without knowing whether the provider already executed the action. Inspect the effect ledger and provider first before deciding.

## 9. When the provider does not support idempotency

This is the hardest case. Suppose the application sends a create-shipment command. The connection times out after sending. The API accepts no idempotency key and offers no lookup endpoint by the application's request code. The application cannot know for sure whether the shipment was created.

In that situation, no retry strategy can simultaneously eliminate both risks:

- Resending may create a second shipment.
- Not resending may leave the shipment never created.

Shrink the uncertainty window with these measures:

1. **Use an application-generated reference:** send a `merchantReference` or business key if the API supports one, then query by that code.
2. **Query before resending:** if the provider has a search API by order, recipient, or reference code, check the result first.
3. **Store requests and correlation IDs:** retain payload, timestamps, correlation codes, and raw responses to aid reconciliation.
4. **Build a reconciliation queue:** `UNKNOWN` records must be checked periodically or routed to operations staff.
5. **Cap automatic retries:** never loop infinitely on an action capable of causing irreversible consequences.
6. **Design compensating actions:** if business rules allow, prepare a dedicated cancel, refund, or revoke flow, while noting that compensation itself can fail.

If a provider lacks idempotency, lookup keys, and reconciliation mechanisms, the system must explicitly document that guarantee limitation in its design. Never claim exactly-once for such a side effect.

## 10. Compensation is a new action, not a rollback

In a multi-step workflow, an earlier step may complete while a later step fails. For example:

1. Payment succeeds.
2. Shipment creation fails.
3. Business rules decide to refund.

A refund is a compensating step in a Saga. It has its own ID, state, retry policy, and failure modes. Never delete the payment record as if the transaction never happened. Keep the history of both the charge and the refund for auditing and reconciliation.

A Saga typically maps business steps and corresponding compensating actions:

```text
Order confirmed
        |
        v
Charge payment -----------------> Charge succeeded
        |                              |
        | failed                       v
        |                        Create shipment
        |                              |
        |                              | failed
        |                              v
        |                        Request refund
        |                              |
        v                              v
  Await error handling           Track refund
```

A Saga does not create a single ACID transaction across multiple services. It orchestrates a chain of local transactions and compensating actions. Because each step can fail or be redelivered, every step and every compensation requires idempotency.

Not every side effect has a clean compensation. A read email cannot be "un-read" from the recipient's memory. An SMS may already have reached the handset. For such actions, good design focuses on minimizing duplicate sends, keeping history, issuing follow-up corrections when needed, and having clear support procedures.

## 11. Implementation notes for Spring Kafka

### 11.1. Let the DB commit before the listener completes

If the listener writes inbox and effect intent using a DB transaction, ensure the DB transaction completes successfully before the listener returns normally. When the container acknowledges offsets only after listener success, DB commit followed by offset commit failure can still cause redelivery; the inbox and unique constraint make redelivery safe.

Never ack a message before required data has committed. If you ack first and the DB rolls back, Kafka may not redeliver the event and the business intent will be lost.

### 11.2. Do not confuse Kafka transactions with DB transactions

`KafkaTransactionManager` manages Kafka transactions. `JpaTransactionManager` or `DataSourceTransactionManager` manages the corresponding DB transaction. Having both managers in the application does not automatically make HTTP requests, DB, and Kafka commit or roll back together as one distributed transaction.

If using Kafka transactions for consume-transform-produce flows, keep non-Kafka side effects in a separate stateful workflow. For DB-to-Kafka flows, consider Transactional Outbox to persist DB changes and event emission intent in the same DB transaction.

### 11.3. Retry topics and DLTs must preserve business identity

When an event moves through retry topics or a DLT, headers and metadata can change. Keep `eventId` in the payload or a controlled metadata field, and keep `effectKey` unchanged across all attempts. Never generate a new key simply because the message moved to another topic.

### 11.4. Concurrency must be protected in the DB

Kafka consumer groups distribute partitions among consumers, but are not an exclusive lock for every side effect. Rebalances, retry topics, multi-threaded processing, or manual replays can cause the same business action to appear in multiple places. Use unique constraints, transactions, and controlled claims to protect data.

### 11.5. Do not hold transactions open across slow API calls

Split claiming, calling the provider, and updating results into short-transaction steps. This reduces connection and lock hold times while making state clear if the process stops between steps.

### 11.6. Make business state observable

Logs and metrics should carry `eventId`, `effectKey`, side-effect type, provider reference, and attempt number. Avoid logging sensitive data such as card numbers or tokens. Useful metrics include counts of effects in `PENDING`, `IN_PROGRESS` past lease, `UNKNOWN`, `RETRYABLE`, `FAILED_FINAL`, processing duration, and reconciliation success rate.

An alert on the count or age of `UNKNOWN` records is often more valuable than simply alerting that a listener threw an exception. An exception shows code hit an error; `UNKNOWN` indicates an external action may have happened without system confirmation.

## 12. Design checklist for a side effect

Before introducing an external action into a consumer, answer these questions:

- What action counts as one single business execution?
- From what data is the idempotency key derived, and is it stable across retries, replays, and rebalances?
- Does the provider support idempotency keys? How long are keys retained and how strictly must payloads match?
- If a timeout occurs after sending a request, how does the system query the outcome?
- Where is side-effect intent durably stored, and what unique constraint protects it?
- Are the inbox record and effect intent committed in the same DB transaction?
- How do workers claim work to avoid concurrent execution across instances?
- If a worker dies after provider success before writing the DB, how does the system recover?
- Who or what component reconciles `UNKNOWN` states?
- Do retries have backoff, jitter, attempt limits, and error classification?
- Does the DLT preserve event ID, effect key, and data needed for investigation?
- If compensation is needed, does the compensating action have its own ID, state, and idempotency?
- Which metrics and alerts detect hung or indeterminate side effects?

## 13. Complete example: consumer creates a charge request

Suppose the Order service emits `OrderApproved` with `eventId`, `orderId`, `paymentAttemptId`, amount, and currency. The Billing service must ask the payment provider to charge.

**Step 1 — Consumer records the event.** The listener calls `recordIntent`. Within one DB transaction, the service inserts `(billing, eventId)` into the inbox and inserts an effect keyed `order:{orderId}:charge:{paymentAttemptId}` with status `PENDING`. If the event is redelivered, the inbox unique key blocks duplicate processing. If two different events represent the same charge attempt, unique `effect_key` still prevents creating two effects.

**Step 2 — Worker claims the effect.** A worker picks a `PENDING` effect, sets `IN_PROGRESS`, increments `attempt_count`, and sets `lease_until` in a short transaction. After commit, the worker calls the provider.

**Step 3 — Call the provider.** The worker sends the payload and `effect_key` as the idempotency key. If the prior call succeeded yet the response was lost, the retry with the same key must be handled per the provider's idempotency contract, typically returning the first attempt's outcome instead of creating a new charge.

**Step 4 — Persist the outcome.** Upon receiving success, the worker saves `SUCCEEDED` along with the provider reference. Subsequent event redeliveries create no new effects; dispatcher runs also skip already-succeeded effects.

**Step 5 — Reconcile when outcome is unclear.** On timeout, the worker saves `UNKNOWN`. A reconciliation job queries the provider by idempotency key or provider reference. If the transaction is found, it updates to `SUCCEEDED`; if the provider confirms no transaction exists, it can return the effect to `RETRYABLE` per policy; if still indeterminate, keep waiting or escalate to manual handling.

This flow does not prevent every network glitch or redelivery. It makes every redelivery safe to handle while preserving enough state to recover when the application does not know what the provider did.

## Conclusion

For non-rollbackable side effects, the critical boundary lies between internal transactions and actions already executed in external systems. Kafka can deliver messages multiple times; the DB can commit while offsets remain uncommitted; providers can succeed even when the application sees only a timeout.

A resilient design requires a business-aligned idempotency key, an inbox to recognize duplicate events, an effect ledger to track each action, stateful leased workers, error-classified retries, and reconciliation for indeterminate outcomes. If the workflow spans multiple services, compensation must be treated as a new business action with its own state and idempotency.

When a provider supports neither idempotency nor outcome lookup, acknowledge that guarantee limit openly and design appropriate reconciliation workflows. No Kafka transaction can automatically roll back a sent email or a charge already collected by a provider. Systems achieve reliability by explicitly managing what is known, what is unknown, and how to proceed safely.
