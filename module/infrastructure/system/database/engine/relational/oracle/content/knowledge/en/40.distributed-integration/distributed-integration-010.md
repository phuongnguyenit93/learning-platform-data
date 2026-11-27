# Outbox, Idempotency, and Event-Based Data Synchronization

In distributed systems, a business operation often needs to update data in Oracle Database while notifying another system of that change. For instance, when an order is confirmed, the Order service must update order status and emit an event so the Inventory service reserves stock, the Billing service creates an invoice receivable, or analytics updates its store.

If the application performs two independent operations—committing to the database and then sending a message to a broker—a window arises where one operation succeeds while the other fails. The database may commit while the message is never sent; or the message is sent while the database transaction rolls back. This is the dual-write problem.

**Transactional Outbox** solves dual writes by writing the business change and an event record in the same database transaction. A relay process reads committed outbox rows and forwards events to the message broker or target system. Because the relay may resend upon failure, consumers must process events **idempotently**: receiving the same event multiple times produces only a single business effect.

These three ideas fit tightly together:

- **Outbox:** ensures business changes and the intent to emit an event commit or roll back together.
- **Idempotency:** ensures repeated processing does not multiply effects.
- **Event-based synchronization:** uses committed business events to update other systems asynchronously.

Outbox does not inherently guarantee a message is sent only once, does not replace distributed transactions for every workflow, and does not make systems instantaneously consistent. It establishes a reliable foundation for at-least-once delivery, upon which idempotency, ordering, retries, and reconciliation achieve consistent results.

## 1. The Dual-Write Problem in Distributed Systems

Suppose the Order service saves an order in Oracle and sends an `OrderCreated` event to Kafka or another message broker.

A naive flow is often written as:

~~~text
1. INSERT order into Oracle
2. COMMIT
3. Send OrderCreated to broker
~~~

If the database commits successfully yet the application process terminates before step 3, the order exists while no downstream system receives the event. Inventory may fail to reserve stock, Billing never creates a receivable, and search never indexes the order.

If you swap the order:

~~~text
1. Send OrderCreated to broker
2. INSERT order into Oracle
3. COMMIT
~~~

The message can be processed by consumers while the database transaction is still uncommitted or ultimately rolls back. Target systems believe an order exists even though the source database lacks it.

A local Oracle transaction only governs changes within that database transaction. It does not automatically atomically commit alongside an external message broker unless the system uses a supported and properly configured distributed transaction mechanism.

### 1.1 Failure Windows of Dual Writes

| When Failure Occurs | Possible Remaining State |
|---|---|
| Before database commit | No business change; message not sent if sent after commit |
| After commit, before sending message | Data saved, but no event emitted |
| Mid-send, unknown whether broker received it | Application cannot tell whether to resend |
| Broker receives message, app loses connection before ACK | May resend and create duplicates |
| Send message first, database rolls back | Consumer receives event for a nonexistent change |

In particular, a publish timeout does not prove the broker never received the message. The broker may have persisted the message and sent an ACK that was lost in transit. Retries are necessary to avoid losing events, yet retries can create duplicates.

### 1.2 Why Not Just Use try/catch?

Error-handling code can retry on exceptions, but cannot solve every scenario:

- The process may be killed right after commit.
- The server may lose power.
- Network timeouts leave publish outcomes ambiguous.
- The broker may be temporarily unavailable for an extended period.
- Deployments or restarts wipe in-memory retry state.
- Multiple application instances may run concurrently and require coordination.

To recover after a process disappears, the intent to emit an event must be persisted durably alongside the business transaction. The outbox provides that durable persistence point.

## 2. What Is the Transactional Outbox?

A Transactional Outbox is a table or structure storing messages to be published. The application writes business data and inserts an event into the outbox within the same Oracle transaction.

Basic flow:

~~~text
Client
  |
  v
Order Service
  |
  | BEGIN TRANSACTION
  | UPDATE/INSERT business tables
  | INSERT event into OUTBOX
  | COMMIT
  v
Oracle Database
  |                    |
  | business data      | committed outbox event
  |                    |
  +--------------------+
             |
             v
       Outbox Relay
             |
             v
       Message Broker
             |
       +-----+------+
       |            |
       v            v
   Inventory      Billing
    Consumer      Consumer
       |            |
       v            v
   Local DB       Local DB
~~~

If the transaction rolls back, both business data and the outbox event roll back. If commit succeeds, both persist together. The relay may stop or the broker may be temporarily unavailable; the event remains in the outbox to be sent later.

### 2.1 Guarantees Provided by Outbox

Outbox solves atomicity on the database side:

- When the business update succeeds, the event record is saved in the same transaction.
- When the business update rolls back, the event record does not exist either.
- The relay can resume after restarts because events are stored durably.
- Unsent, in-progress, sent, or failing events can be tracked.

Outbox does not guarantee:

- That the broker receives only a single message.
- That consumers run only once.
- That target systems update synchronously with the source database.
- That messages are processed in order across multiple relay workers.
- That old events are retained forever.
- That a failing consumer fixes itself without operations.

### 2.2 Outbox and Database Transactions

The single most important requirement is that business data and the outbox record be written in **the same transaction within the same database transaction boundary**.

Incorrect example:

~~~text
Transaction A:
  UPDATE orders
  COMMIT

Transaction B:
  INSERT outbox_event
  COMMIT
~~~

If the process crashes between the two transactions, the dual-write gap remains.

Correct example:

~~~text
Transaction:
  UPDATE orders
  INSERT outbox_event
  COMMIT
~~~

Never use an autonomous transaction for outbox inserts when the goal is atomicity with business updates. An autonomous transaction commits independently; it can record an event even when the business transaction rolls back.

## 3. Designing an Outbox Table in Oracle

An outbox table needs enough fields to identify the event, identify the aggregate, describe the event type, hold the payload, and track publishing state.

Example DDL:

~~~sql
CREATE TABLE app_outbox (
    event_id          RAW(16) DEFAULT SYS_GUID() NOT NULL,
    aggregate_type    VARCHAR2(100) NOT NULL,
    aggregate_id      VARCHAR2(200) NOT NULL,
    aggregate_version NUMBER(19),
    event_type        VARCHAR2(200) NOT NULL,
    schema_version    NUMBER(10) DEFAULT 1 NOT NULL,
    occurred_at       TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    payload           CLOB NOT NULL,
    status            VARCHAR2(20) DEFAULT 'NEW' NOT NULL,
    attempt_count     NUMBER(10) DEFAULT 0 NOT NULL,
    next_attempt_at   TIMESTAMP WITH TIME ZONE,
    lease_owner       VARCHAR2(128),
    lease_until       TIMESTAMP WITH TIME ZONE,
    published_at      TIMESTAMP WITH TIME ZONE,
    last_error        VARCHAR2(2000),
    CONSTRAINT app_outbox_pk PRIMARY KEY (event_id),
    CONSTRAINT app_outbox_status_ck
      CHECK (status IN ('NEW', 'IN_PROGRESS', 'PUBLISHED', 'DEAD'))
);
~~~

If your Oracle release supports JSON constraints on `CLOB`, you can add:

~~~sql
ALTER TABLE app_outbox
  ADD CONSTRAINT app_outbox_payload_json_ck
  CHECK (payload IS JSON);
~~~

Check your Oracle version and supported JSON data types. Newer Oracle releases feature a native `JSON` data type; the example above uses `CLOB` for broader compatibility.

### 3.1 Column Meanings

| Column | Purpose |
|---|---|
| `EVENT_ID` | Unique event identifier, used as the idempotency key |
| `AGGREGATE_TYPE` | Entity type emitting the event, e.g., `ORDER` |
| `AGGREGATE_ID` | ID of the order or business entity |
| `AGGREGATE_VERSION` | Monotonic version of the aggregate to detect ordering/gaps |
| `EVENT_TYPE` | Event name, e.g., `OrderConfirmed` |
| `SCHEMA_VERSION` | Payload structure version |
| `OCCURRED_AT` | Business timestamp when the event occurred |
| `PAYLOAD` | Serialized event data |
| `STATUS` | Relay processing status |
| `ATTEMPT_COUNT` | Number of publish attempts made by the relay |
| `NEXT_ATTEMPT_AT` | Earliest timestamp eligible for retry |
| `LEASE_OWNER` | Worker currently holding processing ownership |
| `LEASE_UNTIL` | Lease expiration so another worker can reclaim if a worker dies |
| `PUBLISHED_AT` | Timestamp when the relay recorded successful publish |
| `LAST_ERROR` | Most recent error details, truncated/redacted of sensitive data |

You can add tenant ID, correlation ID, causation ID, trace ID, partition key, priority, or event source as needed. Avoid stuffing every application field into the payload if consumers do not need it.

### 3.2 Choosing an Event ID Type

The event ID must remain stable across all retries. Options include:

- `RAW(16)` with `SYS_GUID()`.
- UUID generated by the application before the transaction.
- A unique business identifier combined with version if clear rules exist.

Never generate a new event ID on each relay retry. If the ID changes per attempt, consumers cannot recognize duplicates of the same event.

Oracle sequences can generate numeric IDs, yet sequences do not guarantee transaction commit order. Event IDs are for identification; do not automatically treat them as timestamps or business ordering.

### 3.3 Indexes for the Relay

Indexes must support polling unsent events and looking up events by aggregate:

~~~sql
CREATE INDEX app_outbox_poll_ix
    ON app_outbox (status, next_attempt_at, occurred_at);

CREATE INDEX app_outbox_aggregate_ix
    ON app_outbox (aggregate_type, aggregate_id, aggregate_version);
~~~

Actual indexes should reflect the relay's predicates, status update frequency, and data volume. Too many indexes raise insert/update costs and storage footprint. If the table accumulates large event volumes, consider time-based partitioning, retention, and archive/purge strategies.

Do not create indexes blindly: `NEW`/`IN_PROGRESS`/`PUBLISHED` statuses have low cardinality; an index may not help if queries are not selective. Check execution plans and measure real workloads.

## 4. Writing Business Data and Events in the Same Transaction

Suppose an order is confirmed. The application updates `ORDERS` and inserts an `OrderConfirmed` event.

Illustrative SQL:

~~~sql
UPDATE orders
   SET status = 'CONFIRMED',
       version_no = version_no + 1,
       updated_at = SYSTIMESTAMP
 WHERE order_id = :order_id
   AND status = 'PENDING'
RETURNING version_no INTO :new_version;
~~~

Then in the same transaction:

~~~sql
INSERT INTO app_outbox (
    event_id,
    aggregate_type,
    aggregate_id,
    aggregate_version,
    event_type,
    schema_version,
    occurred_at,
    payload,
    status
)
VALUES (
    SYS_GUID(),
    'ORDER',
    :order_id,
    :new_version,
    'OrderConfirmed',
    1,
    SYSTIMESTAMP,
    :payload_json,
    'NEW'
);
~~~

Finally, commit once:

~~~sql
COMMIT;
~~~

In real applications, transaction boundaries are typically managed by the framework or connection. Both `UPDATE` and `INSERT` must share the same connection and transaction. If the `UPDATE` modifies zero rows, handle the concurrency conflict or invalid order state instead of still emitting `OrderConfirmed`.

### 4.1 Complete PL/SQL Example

~~~sql
DECLARE
    l_version orders.version_no%TYPE;
BEGIN
    UPDATE orders
       SET status = 'CONFIRMED',
           version_no = version_no + 1,
           updated_at = SYSTIMESTAMP
     WHERE order_id = :p_order_id
       AND status = 'PENDING'
    RETURNING version_no INTO l_version;

    IF SQL%ROWCOUNT = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Order is not pending or does not exist'
        );
    END IF;

    INSERT INTO app_outbox (
        event_id,
        aggregate_type,
        aggregate_id,
        aggregate_version,
        event_type,
        schema_version,
        occurred_at,
        payload,
        status
    )
    VALUES (
        SYS_GUID(),
        'ORDER',
        TO_CHAR(:p_order_id),
        l_version,
        'OrderConfirmed',
        1,
        SYSTIMESTAMP,
        :p_payload,
        'NEW'
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

The example illustrates transaction boundaries. In application code, let the transaction management layer handle commit/rollback if the transaction spans additional steps. Never commit inside a shared helper procedure when the caller controls a larger transaction.

### 4.2 What Should the Payload Contain?

An event envelope typically includes:

~~~json
{
  "eventId": "9d4d0d3e-...",
  "eventType": "OrderConfirmed",
  "schemaVersion": 1,
  "aggregateType": "ORDER",
  "aggregateId": "ORD-10025",
  "aggregateVersion": 7,
  "occurredAt": "2026-11-14T09:30:00Z",
  "source": "order-service",
  "correlationId": "req-8f21",
  "causationId": "cmd-39a2",
  "data": {
    "orderId": "ORD-10025",
    "customerId": "CUS-82",
    "currency": "VND",
    "totalAmount": 1250000
  }
}
~~~

This JSON is illustrative. The payload should carry enough information for consumers to understand the event without querying back to the source database in every case.

### 4.3 Snapshot Events vs. Reference Events

There are two common payload styles:

- **Snapshot event:** carries all values needed at the moment the event occurred.
- **Reference event:** carries only IDs and expects consumers to read current state from the source API/database.

Snapshots let consumers process historical events accurately even after source data changes further. References shrink payload sizes and avoid duplicating data, yet consumers may read a newer state than the event being processed.

For example, `OrderConfirmed` at version 7 must deliver the confirmed `totalAmount`. If the consumer queries `ORDERS` later, the order may already have been cancelled or edited in version 8. The consumer would observe current data rather than version 7's event state.

Choose snapshot or reference based on business needs, privacy, size, and coupling. Never include sensitive data in events if consumers do not require it.

## 5. Outbox Relay: Shipping Committed Events Outward

The relay is the process reading the outbox and publishing events to the broker. A relay can operate via:

- **Polling publisher:** periodically queries unsent rows.
- **Transaction log tailing / CDC:** reads committed changes from redo logs or change streams and emits events.
- **Database queue:** uses Oracle AQ/Transactional Event Queues or integrated queuing where appropriate.

Regardless of approach, the relay must only publish committed events. It must also handle crashes, retries, duplicates, and concurrent workers.

### 5.1 Polling Publisher

A polling relay periodically checks for events in `NEW` state whose retry time has arrived. This is easy to implement, has minimal CDC infrastructure dependencies, and operates directly on Oracle tables.

General flow:

1. Select a batch of unprocessed events.
2. Claim events using leases or row locks.
3. Commit the claim state.
4. Publish to the broker outside the database transaction.
5. Upon broker acknowledgment, update the event to `PUBLISHED`.
6. Upon publish failure, increment `attempt_count` and schedule retry.
7. If failures exceed policy limits, move the event to `DEAD` for investigation.

Never hold row locks while awaiting a network broker. Network calls can stall, causing lock contention and long-open database transactions. Typically, claim events in a short transaction, commit the lease, and publish outside the transaction.

### 5.2 Claiming Events Across Multiple Workers

When multiple relay workers poll concurrently, prevent two workers from processing the same event simultaneously. Oracle supports `FOR UPDATE SKIP LOCKED` for queue-like workloads.

Illustrative claiming cursor:

~~~sql
DECLARE
    CURSOR c_events IS
        SELECT event_id
          FROM app_outbox
         WHERE status = 'NEW'
            OR (status = 'IN_PROGRESS'
                AND lease_until < SYSTIMESTAMP)
         ORDER BY occurred_at, event_id
         FOR UPDATE SKIP LOCKED;

    l_event_id RAW(16);
    l_count    PLS_INTEGER := 0;
BEGIN
    OPEN c_events;

    LOOP
        FETCH c_events INTO l_event_id;
        EXIT WHEN c_events%NOTFOUND OR l_count >= 100;

        UPDATE app_outbox
           SET status = 'IN_PROGRESS',
               lease_owner = 'relay-01',
               lease_until = SYSTIMESTAMP
                             + INTERVAL '60' SECOND,
               attempt_count = attempt_count + 1
         WHERE CURRENT OF c_events;

        l_count := l_count + 1;
    END LOOP;

    CLOSE c_events;
    COMMIT;
END;
/
~~~

This is an illustrative skeleton to adapt to your Oracle version, cursor logic, batch cap, and retry conditions. In real deployments, predicates must include `NEXT_ATTEMPT_AT IS NULL OR NEXT_ATTEMPT_AT <= SYSTIMESTAMP`, ensuring statuses and leases stay consistent.

`SKIP LOCKED` lets a worker skip rows locked by another worker. It improves concurrency, but does not itself preserve per-aggregate ordering or replace lease expiration.

### 5.3 Lease Owner and Lease Expiry

Leases let another worker take over an event if the current worker is killed after claiming.

Example:

- Worker A claims event E1 with a lease until 10:01.
- Worker A terminates before publishing.
- The lease expires.
- Worker B claims E1 and retries sending.

Leases must be long enough for batch size and publish latency, yet not so long that events remain stuck long after a crash. Workers should renew leases during long runs or use per-event leases.

Include a lease token or claim generation to prevent an old worker from overwriting status after its lease expired and a new worker claimed the event. Upon completion, the `UPDATE` must verify `event_id`, `lease_owner`/token, and current status.

### 5.4 Publish First, Then Mark PUBLISHED

Once the broker confirms publish, the relay updates:

~~~sql
UPDATE app_outbox
   SET status = 'PUBLISHED',
       published_at = SYSTIMESTAMP,
       lease_owner = NULL,
       lease_until = NULL,
       last_error = NULL
 WHERE event_id = :event_id
   AND status = 'IN_PROGRESS'
   AND lease_owner = :worker_id;

COMMIT;
~~~

If the broker received the event but the relay crashes before `UPDATE`/`COMMIT`, the event stays `IN_PROGRESS` or its lease expires. Another worker resends the event. This is an intentional duplicate to prevent losing events.

Marking `PUBLISHED` before publishing means the process could crash after updating but before publishing, losing the event. Thus, the standard order is publish first, mark published second; consumers must be idempotent.

### 5.5 Retries and Backoff

On transient publish failures, do not retry continuously without pausing. Use bounded exponential backoff with jitter so workers do not stampede the broker simultaneously upon recovery.

Illustrative schedule:

| Attempt | Base Delay |
|---:|---:|
| 1 | 1 second |
| 2 | 2 seconds |
| 3 | 4 seconds |
| 4 | 8 seconds |
| 5 | 16 seconds |
| Thereafter | Capped at policy maximum |

Formula:

\[
delay = \min(maxDelay,\ baseDelay \times 2^{attempt})
\]

Adding random jitter spreads out load. Distinguish transient errors—timeouts, broker unavailable, throttling—from permanent errors like invalid payloads or incompatible schemas.

### 5.6 Dead-Letter State

After exceeding retry limits or max wait duration, an event can move to `DEAD`. `DEAD` does not mean forgotten. It requires:

- Alerting the operations team.
- Storing `last_error` scrubbed of sensitive data.
- A dashboard and investigation runbook.
- Replay support after fixing root cause.
- Never silently deleting or mutating the original payload.

When replaying, preserve the same `event_id` if re-sending the exact same event. If creating a new business event after fixing data, use a new `event_id` and link causation/correlation accordingly.

## 6. CDC and Transaction Log Tailing

Instead of polling the outbox, a relay can read committed changes from redo logs or change data capture (CDC). A connector watches `INSERT`s into the outbox table and forwards records to the broker.

In Oracle, options depend on version, edition, licensing, and infrastructure and may include:

- Oracle GoldenGate.
- LogMiner-based CDC or redo-reading connectors.
- Oracle XStream in environments with appropriate privileges and configuration.
- Third-party CDC tools supporting Oracle.
- Oracle Advanced Queuing or Transactional Event Queues for in-database queuing architectures.

Check licensing and support terms for each product. Never assume a CDC feature is included in every edition or permitted without appropriate licenses.

### 6.1 CDC from the Outbox Table

~~~text
Oracle transaction
   |
   +-- UPDATE business table
   |
   +-- INSERT outbox row
   |
  COMMIT
   |
   v
Redo / transaction log
   |
   v
CDC connector
   |
   v
Broker topic
   |
   v
Consumers
~~~

CDC reads only committed changes from logs. This avoids repeatedly polling for `NEW` rows. The connector persists offsets/SCNs to resume reading after restarts.

### 6.2 Polling vs. CDC

| Criterion | Polling Relay | CDC / Log Tailing |
|---|---|---|
| Latency | Depends on polling interval and batch | Can be lower, near real-time |
| Complexity | Easy to understand, self-contained | Requires connector, log retention, and CDC operations |
| Database load | Queries and updates outbox status | Reads redo/logs and maintains offsets |
| Retries | Relay application manages directly | Connector/broker manages its own retries |
| Ordering | Must design in worker | Can rely on partition/log order, still needs key/version |
| Observability | Outbox status table easy to query | Must monitor connector lag and offsets |
| Best fit | Moderate traffic, simple deployment | High traffic or low-latency requirements |

CDC from an outbox can still emit duplicates when a connector restarts or rewinds offsets. Consumer idempotency remains mandatory.

### 6.3 Why Still Use an Outbox If You Have CDC?

Direct CDC on business tables generates events from row changes, yet row changes do not always convey business intent. An `UPDATE` might come from a bug fix, migration, batch job, or trigger. Consumers have to infer events from data structures.

An outbox lets the application emit explicit business events such as `OrderConfirmed`, `PaymentCaptured`, or `CustomerAddressChanged`. CDC simply serves as the transport for events already written to the outbox.

## 7. What Is Idempotency?

An operation is idempotent if executing it once or multiple times with the same input identifier produces the exact same business outcome.

Examples:

- Setting order status to `CONFIRMED` can be idempotent if updated conditionally without generating repeated side effects.
- Adding 100,000 VND to a balance is not idempotent if the same request runs twice.
- Creating a new payment is not idempotent if every retry creates a separate payment.

In messaging systems, duplicates arise from broker redeliveries, consumer restarts, lost ACKs, or relay resends. Idempotency lets consumers handle redeliveries safely.

### 7.1 At-Least-Once and Duplicates

Outbox relays commonly follow at-least-once semantics:

- The relay keeps retrying until the broker accepts the message or the event enters an error state.
- An event may be sent multiple times if confirmation of an earlier attempt was unclear.
- Consumers may re-receive already-processed events.

At-least-once prioritizes never losing events. In exchange, applications must tolerate duplicates and handle them deterministically.

### 7.2 End-to-End Exactly-Once Is Hard to Expect

A broker may support producer idempotence or broker-scoped transactions. That alone does not merge an Oracle transaction, broker publish, consumer database update, and external API call into one atomic transaction.

For instance, a consumer updates its database and crashes before ACKing the broker. The broker redelivers the message. If the consumer is not idempotent, the business update runs twice.

Therefore, practical designs pair at-least-once delivery with idempotent consumers. Narrow exactly-once semantics may exist within specific technology boundaries, yet document those exact boundaries rather than claiming system-wide exactly-once.

## 8. Inbox Pattern and Deduplication Tables

A standard way to ensure a consumer applies an event at most once to its local database is recording the event ID in an inbox/processed-messages table in the same transaction as the business update.

Example DDL:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR2(100) NOT NULL,
    event_id      RAW(16) NOT NULL,
    received_at   TIMESTAMP WITH TIME ZONE
                  DEFAULT SYSTIMESTAMP NOT NULL,
    processed_at  TIMESTAMP WITH TIME ZONE,
    CONSTRAINT consumer_inbox_pk
      PRIMARY KEY (consumer_name, event_id)
);
~~~

The composite primary key `(consumer_name, event_id)` allows the same event to be processed by independent consumers while preventing any single consumer from recording the same event twice.

### 8.1 Processing Messages in One Transaction

Consumer flow:

1. Receive message.
2. Begin database transaction.
3. Insert event ID into inbox.
4. If insert succeeds, apply business effects.
5. Mark inbox processed.
6. Commit.
7. ACK the message to the broker only after commit.

Illustrative PL/SQL example:

~~~sql
DECLARE
    l_duplicate EXCEPTION;
    PRAGMA EXCEPTION_INIT(l_duplicate, -1);
BEGIN
    INSERT INTO consumer_inbox (
        consumer_name,
        event_id,
        received_at
    )
    VALUES (
        'inventory-service',
        :event_id,
        SYSTIMESTAMP
    );

    UPDATE inventory
       SET reserved_quantity = reserved_quantity + :quantity,
           version_no = version_no + 1
     WHERE product_id = :product_id;

    UPDATE consumer_inbox
       SET processed_at = SYSTIMESTAMP
     WHERE consumer_name = 'inventory-service'
       AND event_id = :event_id;

    COMMIT;
EXCEPTION
    WHEN l_duplicate THEN
        ROLLBACK;
        -- Event was recorded previously.
        -- Consumer can ACK the duplicate per policy.
        NULL;
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

The example assumes inventory updates are valid and validated separately. In production code, do not swallow every unique-constraint error if another constraint could fail; identify the exact inbox constraint or perform insert/dedup via a controlled API.

ACK the broker only after the database commit succeeds. If you ACK before commit and the process dies, the broker may never redeliver the message while the business transaction rolled back.

### 8.2 Why Must Inbox Insert and Business Update Share a Transaction?

Suppose the consumer commits the inbox first and updates inventory afterward. If the process crashes in between, redelivery sees the event ID already exists and skips it; inventory is never updated. That loses the effect.

Conversely, if inventory updates and commits first and inbox writes in a separate transaction, a crash in between causes the message to be reprocessed and increment quantity a second time.

Sharing one transaction ensures both happen atomically: either both inbox and business effects commit, or both roll back.

### 8.3 Handling Duplicates Under Concurrency

Two consumer instances might receive the same event nearly simultaneously. Both attempt to insert the same primary key:

- One transaction inserts successfully and holds the lock.
- The other waits for the outcome.
- If the first commits, the second receives a duplicate key error.
- If the first rolls back, the second can insert and proceed.

Oracle's unique constraint is the final guard against two workers processing the same event. Checking with `SELECT` before `INSERT` is insufficient because both workers can observe absence and proceed concurrently.

### 8.4 Inbox Retention

Never purge inbox records too early while the broker might still redeliver or events might be replayed. Retention must exceed the maximum window during which duplicates can appear per broker and operational policies.

If pruning old records, know how far back replays can reach. Store deduplication keys in business tables or a long-term idempotency store if business requirements demand it.

## 9. Idempotency Keys for APIs and Commands

Idempotency does not apply only to event consumers. APIs can receive retried requests due to client timeouts or gateway retries.

For example, a client sends `POST /payments` with an `Idempotency-Key` header. The server stores the key, request hash, and processing result.

Illustrative table:

~~~sql
CREATE TABLE api_idempotency (
    client_scope  VARCHAR2(100) NOT NULL,
    idempotency_key VARCHAR2(200) NOT NULL,
    request_hash  RAW(32) NOT NULL,
    response_code NUMBER(3),
    response_body CLOB,
    status        VARCHAR2(20) NOT NULL,
    created_at    TIMESTAMP WITH TIME ZONE
                  DEFAULT SYSTIMESTAMP NOT NULL,
    completed_at  TIMESTAMP WITH TIME ZONE,
    CONSTRAINT api_idempotency_pk
      PRIMARY KEY (client_scope, idempotency_key)
);
~~~

When receiving a request:

- If the key does not exist, create the record and execute business logic.
- If the key already completed with the same request hash, return the stored response.
- If the key exists with a different request hash, return an error because the client reused a key for different content.
- If the key is still in progress, apply wait policy, return processing status, or ask client to retry later.

Idempotency keys need a scope such as client/account/tenant to avoid collisions across users. Never generate a fresh key on the server for each retry.

### 9.1 Idempotency Keys Do Not Replace Validation

If the same key arrives with a different payload, the server must detect and reject it. Storing only the key without a request hash or equivalent check lets a client accidentally reuse a key for a different operation and receive stale results.

Define key expiration as well. If keys are purged after one day yet a client retries after two days, the operation may execute again. TTL must align with API contracts and system retry windows.

### 9.2 Idempotent Updates via State Conditions

Some business commands can be made idempotent using state and version checks:

~~~sql
UPDATE orders
   SET status = 'CONFIRMED',
       version_no = version_no + 1
 WHERE order_id = :order_id
   AND status = 'PENDING';
~~~

If retried, a row already `CONFIRMED` is not updated again. However, distinguish "already completed earlier" from "does not exist" or "invalid state." The application should re-read current state and return the appropriate outcome.

For incrementing/decrementing quantities or balances, state conditions alone may not suffice. Use unique operation IDs, ledger entries with unique keys, or business transaction logs to prevent duplicates.

## 10. Event Ordering and Aggregate Versions

Event-based synchronization often requires ordering within a single aggregate. For example, `OrderCreated` must process before `OrderConfirmed`; `OrderConfirmed` before `OrderShipped`.

Global system-wide ordering is rarely required. Global ordering reduces throughput and creates bottlenecks. Usually, ordering per aggregate ID suffices.

### 10.1 Timestamps Are Not Absolute Order

`OCCURRED_AT` is useful for observation and approximate sorting, yet timestamps do not always reflect commit order:

- Two sessions can capture timestamps at different moments and commit in reverse order.
- Clocks across machines can drift.
- Timestamps have finite precision.
- Events can be relayed minutes later.
- Sequences fetched before commit do not guarantee commit order.

To detect business order reliably, use an `AGGREGATE_VERSION` incremented within the same transaction updating the aggregate.

### 10.2 Aggregate Version

On every aggregate change, increment the version:

~~~sql
UPDATE orders
   SET status = :new_status,
       version_no = version_no + 1
 WHERE order_id = :order_id
   AND version_no = :expected_version
RETURNING version_no INTO :new_version;
~~~

The event is recorded with the exact same `new_version` in the transaction. Optimistic concurrency via `expected_version` detects competing commands.

Consumers store `last_processed_version` per aggregate. When receiving a version:

- If version equals `last + 1`, process it.
- If version is less than or equal to `last`, it is likely a duplicate or stale event.
- If version exceeds `last + 1`, an event may be missing; buffer or request replay/reconciliation.

Gap handling depends on business logic. Some consumers can apply the latest snapshot; others need every event because each event triggers a distinct effect.

### 10.3 Ordering at the Relay

Multiple relay workers can publish version 8 before version 7 if they claim and send in parallel. If per-aggregate ordering is mandatory, you can:

- Partition events by aggregate ID with only one worker per partition.
- Avoid claiming a new event for an aggregate while an earlier event remains unpublished.
- Use aggregate ID as the broker partition key to preserve intra-partition ordering.
- Use aggregate version so consumers detect out-of-order deliveries and gaps.

Using `ORDER BY occurred_at` in a polling query alone does not preserve order when multiple workers or varying publish latencies exist.

### 10.4 Ordering at the Broker

Some brokers preserve order within a partition or queue, but not across an entire topic with multiple partitions. Use aggregate ID as the message key if the broker supports key-based partitioning.

If events for the same aggregate land in different partitions, consumers may receive them out of order. Keep partition keys and routing strategies stable over time; changing partition counts can affect key mapping depending on the broker.

## 11. Event Contracts and Schema Evolution

Events are contracts between producers and consumers. When a producer changes payloads, older consumers may not deploy simultaneously. Design schemas to evolve safely.

An event envelope should specify:

- `eventId`.
- `eventType`.
- `schemaVersion`.
- `aggregateType` and `aggregateId`.
- `aggregateVersion` if ordering is required.
- `occurredAt`.
- `source`.
- `correlationId` and `causationId`.
- `data` payload.

### 11.1 Backward-Compatible Changes

Changes are generally safer when:

- Adding optional fields with clear defaults.
- Consumers ignore unknown fields.
- Not changing the meaning of existing fields.
- Not changing implicit units or timezones.
- Not making breaking data type changes.
- Keeping `eventType` stable and introducing a new event type when business semantics change substantially.

Removing fields, renaming fields, changing types, altering enums, or shifting semantics can break consumers. Use a schema registry or contract tests when an ecosystem has many producers/consumers.

### 11.2 Payload Versioning

You can include `schemaVersion` in the envelope. Consumers can support multiple versions, or producers can emit a new event type.

Do not use versioning to justify arbitrary breaking changes. Versioning is only effective with clear migration rules, compatibility guarantees, and support windows for older versions.

### 11.3 Immutable Events

An event describes a fact that happened in the past: `OrderConfirmed`, `PaymentCaptured`, `InventoryReserved`. Never mutate the payload of an already-emitted event to reflect later state.

If a correction is needed, emit a new event such as `OrderCorrectionApplied` or `PaymentRefunded`. Event history must preserve historical accuracy and auditability.

## 12. Event-Based Synchronization Across Multiple Systems

When a consumer receives an event, it updates its local read model or database. This is a common pattern for synchronizing data without letting services query each other's databases directly.

~~~text
                 Oracle Order DB
                       |
                 Transactional
                    Outbox
                       |
                  Outbox relay
                       |
                 Event broker
             /         |         \
            /          |          \
           v           v           v
    Inventory DB   Billing DB   Search Index
       Consumer      Consumer     Consumer
~~~

Each consumer owns its local data. The Order service does not need to know Inventory's or Search Index's schema. It simply publishes the agreed event contract.

### 12.1 Event Notification vs. Event-Carried State Transfer

Two common payload styles:

- **Event notification:** signals that a change occurred; the consumer calls an API to fetch details.
- **Event-carried state transfer:** carries enough data for the consumer to update its local model without calling back to the producer.

Event notifications shrink payload size but increase runtime coupling and risk reading state newer than the event. Event-carried state transfer reduces synchronous dependencies but requires managing schemas, security, and replicated data.

### 12.2 Eventual Consistency

After the Order service commits, an event takes time to flow through relay, broker, and consumers. During that window, Inventory or Search may not yet reflect the change.

This is eventual consistency. Applications must surface intermediate states when users read immediately after writing—such as "processing," "syncing," or using read-your-writes against the primary source.

Never assume all services update simultaneously. Define propagation SLAs—e.g., 95% of events within 2 seconds, 99.9% within 30 seconds—backed by real measurements.

### 12.3 Reconciliation

Event processing can experience prolonged failures or consumer bugs. Establish reconciliation mechanisms between the source of truth and projections:

- Compare counts or checksums by partition/time range.
- Re-read aggregate versions.
- Replay events from offsets or archives.
- Rebuild read models from snapshots and event history.
- Emit correction events when drift is detected.
- Record reconciliation results and completion timestamps.

Eventual consistency does not mean accepting permanent drift. Reconciliation detects and repairs discrepancies that do not self-heal.

## 13. Sagas and Outbox in Multi-Service Workflows

A business process can span multiple services and databases. A single local Oracle transaction cannot commit all of them.

Order placement example:

1. Order service creates the order.
2. Inventory service reserves stock.
3. Payment service captures funds.
4. Shipping service creates the shipment.

If payment fails after inventory was reserved, the system must release the stock. This distributed workflow is commonly modeled as a Saga.

~~~text
OrderCreated
    |
    v
ReserveInventory
    |
    +---- InventoryReserved ----> AuthorizePayment
    |                                  |
    |                                  +---- PaymentAuthorized
    |                                  |           |
    |                                  |           v
    |                                  |       CreateShipment
    |                                  |
    |                                  +---- PaymentRejected
    |                                              |
    v                                              v
OrderCancelled <---- ReleaseInventory <---- Compensation
~~~

Each service executes a local transaction and emits events/commands via its outbox. When a downstream step fails, the saga triggers compensating actions.

### 13.1 Forward Recovery and Compensation

When a step hits a transient failure, it can retry that step. When a failure is unrecoverable or business rules dictate cancellation, the saga executes compensation.

Compensation is not a technical database rollback. It is a new business operation designed to reverse earlier effects—for example, not deleting reservation history, but emitting `InventoryReservationReleased`.

### 13.2 Idempotent Compensation

Compensating actions can also be delivered multiple times. Give each action an idempotency key, such as `sagaId + stepName + actionVersion`. If `ReleaseInventory` arrives twice, the consumer must not adjust stock twice.

### 13.3 An Outbox in Every Service

Each service owns its own database and its own outbox. Never write directly to another service's database. A saga coordinator or choreography receives events, persists saga state, and emits subsequent commands via its own outbox.

## 14. Oracle Advanced Queuing and Transactional Event Queues

Oracle provides database-integrated queuing technologies such as Advanced Queuing (AQ) and Transactional Event Queues (TxEventQ, naming/availability depends on release). These fit well when you want messages managed inside the Oracle ecosystem.

AQ supports transactional enqueue/dequeue within database transactions. This can eliminate certain dual-write boundaries when applications and consumers properly use the built-in queue.

However, distinguish between:

- Outbox is a design pattern built on tables and a relay.
- AQ/TxEventQ is messaging infrastructure provided by Oracle.
- CDC is a mechanism reading changes from transaction logs.
- Kafka/RabbitMQ or other brokers are messaging systems external to the database.

Choose based on throughput, latency, retention, routing, operational skills, integration ecosystem, and licensing. Avoid adding an outbox table if a transactional queue already fits well and Oracle coupling is acceptable; conversely, do not force every consumer onto Oracle queues if the architecture requires a central broker.

## 15. Should Triggers Automatically Write to the Outbox?

Triggers can write to an outbox upon table modifications, but require caution.

Advantages:

- Captures changes even when multiple applications modify a table.
- Places audit/event logic close to the database.
- Business code cannot forget to insert the event if triggers cover the right operations.

Risks:

- Triggers hide side effects from application code.
- Easy to emit events for technical fixes, migrations, or batches lacking business meaning.
- Hard to construct context-rich payloads.
- Triggers add DML overhead and can introduce unexpected errors.
- Complex triggers risk recursion or trigger-ordering dependencies.
- Schema changes can break triggers.

If using triggers, keep them small, define clear event semantics, and never call brokers/networks inside a trigger. Triggers must insert into the outbox within the same transaction, never an autonomous transaction. For business events like `OrderConfirmed`, the application/service layer usually has clearer context to decide when to emit events.

## 16. Event Security and Privacy

Events may persist longer than source rows or reach many downstream systems. Treat payloads as replicated data with dedicated protection policies.

Principles:

- Include only fields consumers genuinely require.
- Never include passwords, tokens, secrets, or authentication credentials.
- Encrypt data in transit and in broker storage per policy.
- Restrict read permissions on topics/queues.
- Consider masking data in logs and dead-letter records.
- Define retention and replay permissions.
- Establish procedures to delete/anonymize personal data per legal regulations.
- Protect correlation IDs and metadata that could identify users.

If an event carries personal data, deleting a row in the source database does not automatically purge copies in brokers, data lakes, search indexes, and consumer databases. Establish data lifecycle policies and correction/deletion event mechanisms.

### 16.1 Do Not Arbitrarily Log Full Payloads

When publishing fails, avoid dumping entire payloads into application logs if they contain sensitive information. Log event ID, type, controlled aggregate ID, and error code—enough to investigate safely.

### 16.2 Privileges on the Outbox Table

Separate permissions:

- Business service gets `INSERT` on outbox.
- Relay gets `SELECT`/`UPDATE` on required status columns.
- Auditors get scoped metadata read access.
- Do not grant broad `DELETE` to the relay.
- Purge jobs get dedicated privileges and explicit retention rules.

If the relay only updates status, it does not need privileges to alter payloads. Use views or packages to restrict operations.

## 17. Managing Outbox Size and Retention

Outboxes can grow rapidly if every business transaction emits multiple events. Define the record lifecycle:

- `NEW`: awaiting publish.
- `IN_PROGRESS`: leased by a relay.
- `PUBLISHED`: acknowledged by broker.
- `DEAD`: exceeded retry policy or permanent failure.

`PUBLISHED` records do not need to live forever in the hot table. They can be archived and purged per retention. However, if the outbox serves as an audit/event history, retention may be longer and warrant dedicated archival storage.

### 17.1 Safe Purging

Never delete `IN_PROGRESS` or `NEW` events. Purge only `PUBLISHED` events old enough under policy and `DEAD` events after investigation/reconciliation.

Illustrative purge predicate:

~~~sql
DELETE FROM app_outbox
 WHERE status = 'PUBLISHED'
   AND published_at < SYSTIMESTAMP - INTERVAL '30' DAY;
~~~

30 days is illustrative only. Production requires batched deletes to avoid huge transactions, undo/redo spikes, and prolonged locks.

### 17.2 Partitioning

For large tables, partitioning by creation time enables efficient purging and archiving. However, unique constraints and partition keys affect primary key design; Oracle has specific rules for local/global indexes. Design partitioning alongside event identification and query patterns.

### 17.3 Retention Must Match the Replay Window

If a broker can replay 90 days of events yet the inbox keeps only 7 days, consumers may reprocess old events after dedup records are purged. Inbox, outbox, broker, and event archive retentions must be designed cohesively.

## 18. Observing and Operating Event Pipelines

An event pipeline must be monitored from the source transaction to the final consumer.

### 18.1 Outbox Metrics

- Count of `NEW` events.
- Age of oldest `NEW` event.
- Count of `IN_PROGRESS` events and expired leases.
- `PUBLISHED` events per minute.
- Count of `DEAD` events.
- Average and maximum `attempt_count`.
- Latency from `occurred_at` to `published_at`.
- Table size and growth rate.
- Publish error rate.

A critical metric is **outbox age**: the age of the oldest event still waiting to publish. Low queue depth with a single stuck event can still signal a business outage.

### 18.2 Broker and Consumer Metrics

- Producer publish latency and error rate.
- Broker queue/topic lag.
- Consumer lag/offset.
- Redelivery counts.
- Duplicate deduplication counts.
- Processing latency.
- Retry counts and dead-letter counts.
- Version gaps/out-of-order counts.
- Event success rate by event type.

### 18.3 Correlation and Tracing

Propagate `correlationId` end to end:

~~~text
HTTP request
  -> Order transaction
  -> Outbox event
  -> Broker message
  -> Inventory consumer
  -> Inventory database
~~~

Preserve `eventId`, `correlationId`, `causationId`, `aggregateId`, and trace context. This lets you trace a business workflow across multiple services without logging full payloads.

### 18.4 Meaningful Alerts

Alerts should reflect business impact, not just raw technical counters:

- `OrderConfirmed` events delayed beyond SLA.
- Outbox backlog growing continuously.
- Inventory consumer failing to process events.
- `DEAD` events rising.
- Version gaps appearing.
- Abnormally high deduplication rates.
- Relay leases expiring repeatedly.
- Database outbox segment or FRA/storage nearing capacity.

## 19. Testing Failure Scenarios

Outbox and idempotency are only trustworthy once tested against real crash points.

| Scenario | Expected Outcome |
|---|---|
| Business transaction rolls back | Neither business update nor outbox event persists |
| Commit succeeds, relay stops | Event remains in outbox and is sent after restart |
| Broker receives event, ACK lost | Relay may send duplicate; consumer applies only one effect |
| Relay dies after publish, before marking `PUBLISHED` | Event is resent after lease expiry; consumer deduplicates |
| Consumer dies before commit | Inbox and business update roll back; broker redelivers |
| Consumer commits, ACK lost | Message redelivered; inbox detects duplicate |
| Two consumers receive same event concurrently | Unique key lets only one transaction process |
| Events arrive out of order | Version check detects out-of-order/gap |
| Extended broker outage | Retries/backoff, backlog grows, and alerts fire |
| Invalid payload | Event enters `DEAD`/quarantine, no infinite retries |
| Purge runs while relay processes | Purges only eligible statuses, spares active leases |

### 19.1 Testing Relay Crash Windows

Specifically test two windows:

1. Broker received the event; relay has not yet marked `PUBLISHED`.
2. Relay marked `PUBLISHED`; broker never received the event.

A sound design accepts duplicates in the first window. The second window must be eliminated by publishing first and marking published second.

### 19.2 Testing Consumer ACKs

Consumers must ACK only after the local transaction commits. Test killing the process right after commit and before ACK. The message will be redelivered; the inbox must catch the duplicate.

### 19.3 Testing Replays

Replays happen when:

- A consumer is rebuilt.
- Broker offsets are reset.
- Dead-letter events are replayed.
- CDC connectors reread from an older checkpoint.
- Event archives rebuild projections.

Replays must keep the same event ID for deduplication. If intentionally re-executing a new business operation, create a new command/event with a new idempotency key and record causation links.

## 20. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Commit business first, insert outbox later | Data exists without event | Write in the same transaction |
| Send to broker inside trigger | DB transaction depends on network and broker | Write only to outbox in transaction |
| Use autonomous transaction for outbox | Event can persist even when business rolls back | Use the same transaction |
| Mark `PUBLISHED` before publishing | Events can be lost | Publish first, then mark |
| No stable event ID | Cannot deduplicate duplicates | Use an event ID invariant across retries |
| Consumer ACKs before commit | Business effects can be lost | Commit, then ACK |
| Separate inbox commit | Inbox exists while business update rolls back | Same transaction |
| Checking duplicates with `SELECT` only | Race condition between workers | Unique constraint |
| Infinite retries without backoff | Load and log storms | Exponential backoff, jitter, DLQ |
| Multiple workers without ordering control | Events for same aggregate arrive out of order | Partition/serialize by aggregate and version |
| Using timestamps as versions | Does not guarantee commit order | Aggregate version |
| ID-only payload while consumer reads current row | Consumer sees state newer than event | Snapshot or versioned API |
| Purging outbox too early | Cannot replay/reconcile | Align retention with replay window |
| No reconciliation | Silent long-term drift | Periodic reconciliation |
| Logging sensitive payloads | Data leaks | Minimal metadata logging and masking |

## 21. Comparing Outbox with Alternatives

| Solution | Advantages | Limitations |
|---|---|---|
| Transactional Outbox | Easy to understand, atomic with local DB, clear business events | Needs relay, retries, cleanup, and idempotency |
| Distributed transaction / 2PC | Coordinates commits across supported resources | High coupling, operational complexity, not every broker participates |
| Oracle AQ/TxEventQ | Database-integrated messaging, transaction-aware | Coupling to Oracle and release/licensing conditions |
| Direct CDC from business tables | Near real-time, reads logs instead of polling | Row changes do not always reflect business intent |
| CDC from outbox | Clear event semantics, no status polling | Requires CDC connector and log retention |
| Periodic batch sync | Simple for low-churn data | High latency, hard to handle incrementals and deletes |
| Synchronous API calls between services | Immediate result when successful | Runtime coupling, timeouts, and cascading failures |

No single choice fits every system. Outbox fits best when you must reliably emit business events from local transactions and accept eventual consistency.

## 22. End-to-End Example: Order and Inventory

Suppose the Order service owns `ORDERS` in Oracle, and the Inventory service owns `INVENTORY` in a separate database.

When confirming an order:

1. Order service verifies the order is `PENDING`.
2. Updates status to `CONFIRMED` and increments version.
3. Inserts `OrderConfirmed` into `APP_OUTBOX`.
4. Commits.
5. Relay publishes the event.
6. Inventory consumer receives the event.
7. Consumer inserts event ID into `INBOX`.
8. Consumer increments reserved quantity and records version.
9. Consumer commits.
10. Consumer ACKs the broker.

If the consumer receives the event again, the inbox insert hits a duplicate key error and business effects do not rerun.

### 22.1 Consumer Version-Tracking Table

You can store applied versions:

~~~sql
CREATE TABLE inventory_order_state (
    order_id           VARCHAR2(200) PRIMARY KEY,
    last_event_version NUMBER(19) NOT NULL,
    status             VARCHAR2(30) NOT NULL,
    updated_at         TIMESTAMP WITH TIME ZONE
                       DEFAULT SYSTIMESTAMP NOT NULL
);
~~~

The consumer checks the version before applying the event. If a version jumps ahead, buffer the event and handle the gap per policy. If an event is older than the applied version, mark it duplicate/stale without reapplying effects.

### 22.2 Consumers Need Clear Transaction Logic

Inbox and inventory updates must share a transaction. If an external service call is also required, never make an HTTP call inside a long database transaction. Write a new outbox event inside the consumer's transaction and use a separate relay to dispatch the downstream request.

That is how each service preserves local atomicity without creating distributed transactions spanning across the network.

## 23. Implementation Roadmap in Oracle

A controlled rollout path:

1. Identify business events and sources of truth.
2. Design event envelopes, event IDs, aggregate IDs/versions, and schema versions.
3. Create the outbox table, constraints, and required indexes.
4. Update business transactions to insert into the outbox in the same commit.
5. Build a polling relay or configure CDC.
6. Design retries, leases, dead-letter handling, and replay.
7. Create inbox/deduplication at consumers.
8. Ensure inbox and business effects share a transaction.
9. Design per-aggregate partitioning/ordering if needed.
10. Define schema evolution and compatibility rules.
11. Configure retention, purging, and archiving.
12. Add metrics, tracing, alerts, and reconciliation.
13. Test crash windows, duplicates, ordering, and replays.
14. Roll out consumer by consumer and monitor propagation lag.

### 23.1 Separation of Responsibilities

- Business service decides which events carry business meaning.
- Oracle transaction persists business state and outbox atomically.
- Relay only transports events without altering business content.
- Broker stores and delivers messages per its delivery semantics.
- Consumer validates events, deduplicates, and updates local state.
- Reconciliation detects drift between source and projections.
- Operations manages backlogs, retries, retention, and incidents.

Separating responsibilities keeps business logic out of relays and prevents consumers from accessing producers' internal tables directly.

## 24. Design and Operations Checklist

### Producer and Outbox

- [ ] Business update and outbox insert share the same transaction.
- [ ] No autonomous transactions used for events requiring atomicity.
- [ ] Event ID remains stable across all retries.
- [ ] Payload includes event type and schema version.
- [ ] Aggregate ID/version included if ordering is required.
- [ ] Payload contains no unnecessary data or secrets.
- [ ] Indexes and partitions designed for workload.
- [ ] Outbox retention matches replay window.

### Relay

- [ ] Emits only committed events.
- [ ] Safe claiming mechanism across multiple workers.
- [ ] Lease expiry and recovery for stalled events.
- [ ] Never holds row locks during network calls.
- [ ] Publish first, mark `PUBLISHED` second.
- [ ] Retries use backoff and jitter.
- [ ] Dead-letter/quarantine and replay procedures exist.
- [ ] Monitors outbox age and backlog.
- [ ] Enforces per-aggregate ordering if required by business logic.

### Consumer

- [ ] Stable idempotency key.
- [ ] Inbox and business effects share the same transaction.
- [ ] Broker ACK occurs after commit.
- [ ] Unique constraint prevents race conditions.
- [ ] Detects stale events, duplicates, and version gaps.
- [ ] External side effects have dedicated idempotency or a downstream outbox.
- [ ] Inbox retention exceeds replay window.

### System-Wide

- [ ] Event contracts remain compatible during staggered producer/consumer deploys.
- [ ] Correlation/causation IDs and tracing implemented.
- [ ] Metrics exist for producer, broker, and consumer.
- [ ] Reconciliation and projection-rebuild procedures exist.
- [ ] Sensitive data handling and retention procedures defined.
- [ ] Tested crash after publish, before marking published.
- [ ] Tested crash after consumer commit, before ACK.
- [ ] Tested duplicates, out-of-order events, broker outages, and replays.

## 25. Conclusion

Transactional Outbox solves dual writes by persisting business updates and event records in the same Oracle transaction. A relay reads committed events and publishes them to a broker via polling or CDC. Because publishing can repeat on timeouts or crashes, systems should design for at-least-once delivery and use idempotency to prevent duplicated business effects.

The Inbox pattern, unique constraints, and local transactions enable consumers to handle duplicates safely. Aggregate versions, partition keys, and gap detection support ordering. Retries/backoff, dead-letter queues, retention, reconciliation, schema evolution, and observability keep pipelines operable under real failure conditions.

Outbox does not create instantaneous consistency or end-to-end exactly-once semantics. It establishes a durable boundary between the source transaction and event emission. When each service owns its local transactions, emits stably identified events, and processes messages idempotently, data synchronizes reliably across systems without requiring distributed transactions spanning every service.
