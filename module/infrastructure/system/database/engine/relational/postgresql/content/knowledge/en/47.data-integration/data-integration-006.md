# Transactions, Network Failures, and Atomicity Boundaries with External Sources in PostgreSQL

PostgreSQL provides transactions with ACID properties for changes managed within the same database transaction. When a transaction commits successfully, PostgreSQL guarantees that the changes belonging to that transaction are applied according to its durability settings. If a transaction rolls back, the changes within that transaction do not become committed state.

This boundary has limits. A PostgreSQL transaction does not automatically encompass a sent email, an HTTP request to a payment provider, a file uploaded to object storage, a message published to a broker, or changes in an independent database. If an application updates the database and then calls an external service, a network failure can occur between the two operations. The database might roll back while the external service has already performed its side effect, or the database might commit while the client never receives the response.

Therefore, data integration must explicitly design for uncertain states. Key techniques include idempotency keys, classified retries, transactional outbox, inbox/deduplication, sagas with compensation, and two-phase commit when every participant truly supports that protocol. Each approach solves a different class of problem; no single BEGIN/COMMIT command automatically extends ACID across every system.

This lesson focuses on how PostgreSQL handles transactions and connection failures, why COMMIT can produce an ambiguous outcome for the client, how to build fault-tolerant workflows, and how to verify consistency when coordinating with external sources.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Identify the atomicity boundary of a PostgreSQL transaction.
2. Distinguish a transaction rollback from a completed external side effect.
3. Analyze the points where a network connection can drop before, during, and after COMMIT.
4. Explain ambiguous commit outcomes and how to verify state.
5. Classify retryable errors versus errors requiring business handling.
6. Design idempotency keys so clients can retry safely.
7. Distinguish at-most-once, at-least-once, and effectively-once processing.
8. Implement the transactional outbox and inbox/deduplication patterns.
9. Design sagas, compensation, and forward recovery.
10. Understand PREPARE TRANSACTION, COMMIT PREPARED, and the limitations of two-phase commit.
11. Evaluate postgres_fdw, dblink, message brokers, and external APIs.
12. Avoid holding database transactions open while waiting on long network calls.
13. Manage timeouts, retries, backoff, circuit breakers, and connection pools.
14. Monitor in-flight operations, outbox backlogs, and reconciliation.
15. Work through 80 practical exercises on integration reliability.

## 2. PostgreSQL's ACID Boundary

ACID describes the properties of a transaction within the resource manager executing that transaction.

- Atomicity: changes belonging to the transaction are committed together or rolled back together.
- Consistency: database-enforced constraints and rules must remain valid after the transaction.
- Isolation: concurrent transactions observe and affect each other according to the isolation level.
- Durability: after a successful commit, data is preserved according to the durability configuration and failure model.

### 2.1. A Database Transaction

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 20;

COMMIT;
~~~

If the transaction commits successfully, both updates are recorded together. If one statement fails and the transaction rolls back, neither update is committed.

### 2.2. Atomicity Does Not Automatically Extend Over HTTP

~~~text
PostgreSQL transaction
    BEGIN
      UPDATE orders
      INSERT payment_request
    COMMIT

External system
    HTTP POST /charge
~~~

The database and the HTTP service are two separate resource managers. PostgreSQL cannot roll back an HTTP request that a payment provider has already processed.

### 2.3. External Resources Have Independent Lifecycles

An external service may:
- Accept a request and process it asynchronously.
- Execute the side effect and lose the connection before returning a response.
- Return a timeout while the operation continues running on the server.
- Process the same request multiple times if the client retries.
- Exhibit eventual consistency.
- Expose an API to query operation status or idempotency key state.

Applications must understand the external service's contract instead of assuming request-response is an atomic operation.

### 2.4. A Transaction Is Not a Distributed Transaction by Default

BEGIN/COMMIT only governs the transaction on the participating connection and database. If an application opens another connection to a different database or makes an HTTP call, those resources do not automatically join the same transaction.

## 3. Network Failure Scenarios Around a Transaction

When a connection drops, the outcome depends on when the failure occurs.

| Disconnect Timing | What the Client Knows | Recommended Handling |
| --- | --- | --- |
| Before the server receives the request | The request may not have run | Retry if the operation is designed safely |
| While a statement is executing | Unknown how far the statement progressed | Verify connection/backend and transaction state |
| Before sending COMMIT | The transaction will usually roll back when the session ends, though session/server state must be verified | Do not infer strictly from a client-side timeout |
| After the server commits but before sending the response | The transaction may have committed | Handle ambiguous outcome |
| After the client receives commit success | The client knows the server confirmed commit | Continue the workflow based on persisted state |

### 3.1. Request Never Reaches the Server

If the TCP connection fails before the request reaches PostgreSQL, the server never executes the statement. However, clients can rarely distinguish this case from a request that reached the server whose response was lost.

### 3.2. Statement In Progress

If the client loses connectivity, the backend may detect the socket failure and abort the transaction. However, detection is not always instantaneous; the query may continue running briefly or the server may not immediately notice the disconnect.

### 3.3. Disconnect Before COMMIT

If the transaction has not been committed and the session terminates, PostgreSQL rolls back the uncommitted transaction. Still, the client must not treat an application-tier timeout as absolute proof that the backend has finished.

### 3.4. Disconnect During COMMIT

This is the hardest case. The server may have written the commit record and completed the commit, yet the response was lost on the way back to the client. The client sees only a connection error and does not know whether the transaction committed.

### 3.5. Disconnect After the COMMIT Response

If the client has received a success response for COMMIT, PostgreSQL has confirmed the commit under the configured durability policy. Subsequent external steps can still fail independently.

## 4. Ambiguous Commit Outcome

Suppose an application sends:

~~~sql
BEGIN;
INSERT INTO orders(order_id, status) VALUES (9001, 'created');
COMMIT;
~~~

PostgreSQL commits successfully, but the network connection resets before the client receives the response. The client gets a connection error. If the client re-runs the INSERT, it might create a duplicate or hit a unique violation.

### 4.1. Why Can't the Client Deduce the Outcome?

A TCP connection only indicates whether communication between two endpoints was interrupted. It does not provide a business-level answer to "did the transaction commit?" when the acknowledgment is lost.

### 4.2. Do Not Blindly Retry the Entire Operation

If the transaction already committed, retrying can:
- Create a duplicate row.
- Charge or deduct money twice.
- Submit two orders.
- Publish two messages.
- Execute an external side effect a second time.

### 4.3. Design for Status Lookup

Every business operation should have a stable identifier or idempotency key. After an unknown outcome error, the client can query the operation's status by key rather than issuing a fresh command.

### 4.4. Commit Acknowledgment and Durability

Commit outcomes are confirmed according to the configured durability settings, such as synchronous_commit and synchronous replication policy. If an application changes durability settings, evaluate the RPO and failure model separately. A commit success response does not mean an external service has finished processing.

## 5. Error Classification and Retries

Not every error should be retried.

### 5.1. Serialization Failure

SQLSTATE 40001 indicates a serialization failure. With serializable transactions, applications typically must retry the entire transaction from the beginning when this error occurs.

### 5.2. Deadlock Detected

SQLSTATE 40P01 indicates deadlock detected. PostgreSQL aborts one transaction as the victim. The application may retry the entire transaction if the operation is safe and retry budget remains.

### 5.3. Unique Violation

SQLSTATE 23505 typically indicates a unique constraint violation. Do not automatically retry the same transaction; determine whether it is a duplicate request/idempotency collision or a business conflict.

### 5.4. Connection Exception

SQLSTATE class 08 indicates a connection exception. When an error happens around COMMIT, the transaction outcome may be unknown to the client. Use an operation identifier to look up the state.

### 5.5. Query Cancellation and Timeout

SQLSTATE 57014 generally relates to query cancellation. Distinguish a query canceled prior to commit from a connection loss after commit was sent. A client-side timeout might only stop waiting on the client, depending on the driver and cancellation mechanism.

### 5.6. Retry Matrix

| Error | Typical Appropriate Action |
| --- | --- |
| 40001 serialization failure | Retry the entire transaction with backoff |
| 40P01 deadlock | Retry the entire transaction with a bounded limit |
| 23505 unique violation | Handle duplicate/conflict per business rules |
| 08xxx connection exception | Verify outcome; use idempotency/reconciliation |
| 57014 query canceled | Determine cancellation point and transaction state |
| 22xxx data exception | Fix input; do not retry verbatim |
| 28xxx authentication failure | Fix credentials/permissions |
| 53xxx insufficient resources | Shed load/wait for capacity; bounded retry if appropriate |

### 5.7. Retries Must Be Bounded

Use bounded retries, exponential backoff, jitter, a deadline, and a maximum elapsed time. Unbounded retries can trigger a retry storm and overload an already degraded service.

## 6. Exponential Backoff and Jitter

A retry policy typically increases the wait interval between attempts.

~~~text
attempt 1: wait about 100 ms
attempt 2: wait about 200 ms
attempt 3: wait about 400 ms
attempt 4: wait about 800 ms
...
cap delay and add random jitter
~~~

### 6.1. Exponential Backoff

Delay grows with the retry attempt count, usually with an upper cap. The goal is to relieve pressure on a failing dependency.

### 6.2. Jitter

Adding a random component prevents multiple clients from retrying at the exact same instant after an outage.

### 6.3. Deadline

Total retry time must fit within the request deadline or background job SLA. Once the deadline expires, persist the operation state for later handling instead of retrying indefinitely.

### 6.4. Retry Budget

Cap the ratio of retries to total requests. If the ratio crosses a threshold, trip a circuit breaker or shed traffic to prevent amplifying failures.

### 6.5. Retry Only Safe Operations

Retrying a GET is generally lower risk than retrying a payment POST, though true semantics depend on the API. Read the contract and use idempotency keys for side effects.

## 7. What Is Idempotency?

An idempotent operation can be executed multiple times with the same identity without producing additional business effects beyond the intended outcome.

For example, "set order status to shipped" can be idempotent if properly defined. "Deduct 100 more from balance" is not idempotent if each call applies another deduction.

### 7.1. Idempotency Key

The client generates a stable key for a business request and resends the same key on retries. The server stores the key alongside the request identity, status, and result.

### 7.2. Key Scope

The key must be unique within a defined scope, such as tenant + operation type + key. Never share one key across unrelated requests.

### 7.3. Request Fingerprint

Store a hash or canonical representation of the request. If the same idempotency key is sent with a different payload, return a conflict instead of mistakenly reusing an old result.

### 7.4. Retention

Retain idempotency records for at least as long as the client/provider can retry and as long as the business operation requires lookup. Deleting records too early can allow an old request to execute again.

### 7.5. Idempotency Does Not Automatically Create Exactly-Once

Idempotency prevents duplicate attempts from causing duplicate business effects within the protected scope. It does not guarantee that a message is delivered only once or that all external systems commit atomically together.

## 8. Idempotency Table in PostgreSQL

A straightforward table:

~~~sql
CREATE TABLE app.idempotency_requests (
    tenant_id bigint NOT NULL,
    idempotency_key text NOT NULL,
    request_hash bytea NOT NULL,
    operation_type text NOT NULL,
    status text NOT NULL
        CHECK (status IN ('processing', 'completed', 'failed')),
    response_body jsonb,
    resource_id bigint,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, idempotency_key)
);
~~~

### 8.1. Recording the Request

Within the transaction handling the request, attempt to insert the key:

~~~sql
INSERT INTO app.idempotency_requests (
    tenant_id,
    idempotency_key,
    request_hash,
    operation_type,
    status
)
VALUES ($1, $2, $3, $4, 'processing')
ON CONFLICT DO NOTHING;
~~~

If the insert creates a row, the current transaction owns processing for that key. If it inserts nothing because the key already exists, read the existing record and compare request_hash.

### 8.2. Validating the Payload

If the hash differs, return a conflict because the client is reusing the key for a different request. If the hash matches and status is completed, return the stored response.

### 8.3. Concurrent Duplicate Requests

The unique constraint on (tenant_id, idempotency_key) coordinates competing inserts. One insert may wait for the other transaction to commit or roll back. Afterward, the losing request reads the committed status.

### 8.4. Updating the Result Alongside Business Changes

For purely local PostgreSQL operations, write the business row, idempotency result, and response inside the same transaction. If the transaction rolls back, both the key claim and the business changes roll back together.

### 8.5. Do Not Leave Processing Records Orphaned Indefinitely

If the operation involves an external side effect, do not hold a database transaction open across the network call. Use an operation state machine or outbox to process asynchronously with timeouts and reconciliation.

## 9. Idempotent Handling Pattern for Local Operations

Example creating an order and saving the response in a single transaction:

~~~sql
BEGIN;

INSERT INTO app.idempotency_requests (
    tenant_id,
    idempotency_key,
    request_hash,
    operation_type,
    status
)
VALUES (42, 'req-7f31', decode('aabbcc', 'hex'), 'create_order', 'processing')
ON CONFLICT DO NOTHING;

-- Application checks whether this transaction inserted the row.
-- If not, it reads the existing row and returns the stored result
-- when the request hash matches and status is completed.

INSERT INTO app.orders (
    tenant_id,
    order_reference,
    status
)
VALUES (42, 'ORD-9001', 'created')
RETURNING order_id;

UPDATE app.idempotency_requests
SET status = 'completed',
    resource_id = 9001,
    response_body = '{"order_id":9001,"status":"created"}'::jsonb,
    updated_at = now()
WHERE tenant_id = 42
  AND idempotency_key = 'req-7f31';

COMMIT;
~~~

This illustrates the flow, not a copy-paste script for every schema. The application must accurately check whether this transaction inserted the key or is reading a prior request's outcome; never execute the order INSERT if the key was already handled.

### 9.1. Avoid the Select-Then-Insert Race

A pattern that runs SELECT on the key first and INSERT afterward suffers from a race condition: two requests can both see the key as missing. Use a unique constraint and INSERT ... ON CONFLICT as the arbiter.

### 9.2. Store a Stable Response

If the API must return the exact same response on retries, store the resource identifier, status, and response fields needed to reconstruct the response. Avoid storing secrets or unnecessary sensitive data.

### 9.3. Key Expiration

Expiration should align with the business and retry window. Deleting a record while the operation can still be retried breaks the idempotency guarantee.

## 10. Why Calling HTTP Inside a Transaction Is Usually Bad

Example:

~~~sql
BEGIN;
UPDATE app.orders SET status = 'paying' WHERE order_id = 9001;
-- Application calls payment provider and waits several seconds.
COMMIT;
~~~

The transaction holds locks and a snapshot while waiting on the network. If the provider times out, the database transaction can remain open for a long time, causing contention and connection pool exhaustion.

### 10.1. Lock Duration

A long transaction holds row or table locks, blocks vacuum cleanup, stretches the snapshot horizon, and increases dead tuples.

### 10.2. Unpredictable Network Latency

External APIs can take a few milliseconds or tens of seconds. Database transactions should remain short and bounded.

### 10.3. Rollback Does Not Undo HTTP

If the payment provider already charged the card and the client timed out, rolling back the database does not issue a refund. You need provider idempotency keys, status lookups, or a compensation/refund workflow.

### 10.4. Availability Coupling

If a database transaction waits on a provider reply before committing, the database workflow's availability becomes directly coupled to the provider's latency and availability.

### 10.5. When Is a Synchronous Call Still Appropriate?

Some use cases require a synchronous response. If you do this, keep transactions as short as possible, understand timeout semantics, use provider idempotency keys, and persist enough state to reconcile. Avoid holding row locks across a long network call.

## 11. Transactional Outbox Pattern

The transactional outbox solves the problem of updating the database and recording an event to send externally within the same local transaction.

### 11.1. Core Idea

Within one transaction:
1. Update the business data.
2. Insert the event into the outbox.
3. Commit both together.

A separate worker reads the outbox and publishes the event to a broker or external service.

~~~text
Application
    |
    v
PostgreSQL transaction
    |-- update business row
    |-- insert outbox event
    |
    v
COMMIT
    |
    v
Outbox relay
    |
    v
Message broker / external API
~~~

### 11.2. Why Is This Pattern Useful?

If the transaction rolls back, the event does not exist. If the transaction commits, the event is durably persisted in the database and the relay can deliver it once the network recovers.

### 11.3. Outbox Does Not Make the Broker Commit with the Database

Database commit and broker publish remain two separate steps. The relay can publish successfully and then crash before marking the event published. Therefore, duplicate delivery can still happen.

### 11.4. Delivery Semantics

An outbox relay is typically designed for at-least-once delivery: events may be resent until acknowledged. Consumers must be idempotent.

### 11.5. Outbox Is Durable Intent

The outbox records that the database committed a business change and that the system needs to perform an external action. It does not assert that the external action has already succeeded.

## 12. Designing the Outbox Table

~~~sql
CREATE TABLE app.outbox_events (
    event_id uuid PRIMARY KEY,
    aggregate_type text NOT NULL,
    aggregate_id text NOT NULL,
    aggregate_version bigint,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    available_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    attempts integer NOT NULL DEFAULT 0,
    last_error text
);

CREATE INDEX outbox_pending_idx
    ON app.outbox_events (available_at, occurred_at)
    WHERE published_at IS NULL;
~~~

### 12.1. event_id

A stable ID used for deduplication at the consumer. UUIDs are often convenient for event identity.

### 12.2. aggregate identity

aggregate_type/aggregate_id group events by business entity, such as order. aggregate_version can help detect ordering issues or gaps.

### 12.3. payload

Store enough information for consumers. Avoid secrets, payment credentials, or unnecessary fields. Consider payload versioning.

### 12.4. published_at

NULL indicates the event has not yet been confirmed published under the relay policy. This timestamp is set once the broker or API confirms receipt.

### 12.5. Pending Index

A partial index keeps lookups for unpublished events efficient. As the table grows, establish a retention, partitioning, or archiving policy so the outbox does not grow without bound.

## 13. Writing Business Changes and Outbox in the Same Transaction

~~~sql
BEGIN;

UPDATE app.orders
SET status = 'confirmed',
    version = version + 1
WHERE order_id = 9001
RETURNING order_id, version;

INSERT INTO app.outbox_events (
    event_id,
    aggregate_type,
    aggregate_id,
    aggregate_version,
    event_type,
    payload
)
VALUES (
    gen_random_uuid(),
    'order',
    '9001',
    4,
    'order.confirmed',
    '{"order_id":9001,"status":"confirmed","version":4}'::jsonb
);

COMMIT;
~~~

The application should read the actual order_id/version returned by UPDATE ... RETURNING to build the payload instead of hard-coding values as shown in the example. This can be done using a CTE or application transaction logic.

### 13.1. Atomic Local Write

If the outbox INSERT fails, the order UPDATE also rolls back. If the commit succeeds, both the business state and the event intent exist.

### 13.2. Never Publish Before COMMIT

If you publish before the database commits, consumers could receive an event for a business transaction that later rolls back. The outbox prevents this ordering bug by relaying only committed rows.

### 13.3. Payload Contract

The event schema should include event type/version, event ID, aggregate ID, occurred_at, and required payload fields. Consumers must handle payload evolution.

## 14. Outbox Relay with SKIP LOCKED

Multiple workers can claim unpublished events using SELECT ... FOR UPDATE SKIP LOCKED.

~~~sql
WITH batch AS (
    SELECT event_id
    FROM app.outbox_events
    WHERE published_at IS NULL
      AND available_at <= now()
    ORDER BY occurred_at, event_id
    FOR UPDATE SKIP LOCKED
    LIMIT 100
)
SELECT e.*
FROM app.outbox_events AS e
JOIN batch AS b USING (event_id);
~~~

### 14.1. Short Claim Transaction

You can claim a batch in a brief transaction and assign a lease/worker identity. Commit the claim before calling the broker so row locks are not held across the network call.

### 14.2. Lease Model

A production schema may include locked_by, locked_until, or claim_token. A worker only processes rows whose lease still belongs to it.

### 14.3. Publish Outside the Transaction

After claiming, the worker sends the event to the broker. Once the broker acknowledges, the worker updates published_at in a new transaction.

### 14.4. Crash After Publish

If the broker receives the event and the worker crashes before updating published_at, the lease expires and the event is resent. This is intentional duplication in an at-least-once design.

### 14.5. Do Not Hold Database Locks During Network Calls

Claim rows, commit, publish, then record the outcome. Never hold a transaction open while waiting on a broker unless using a specialized, benchmarked design.

## 15. Inbox Pattern and Consumer Deduplication

A consumer may receive the same event multiple times. An inbox table stores processed event IDs alongside the business update within a single local transaction.

~~~sql
CREATE TABLE app.inbox_events (
    consumer_name text NOT NULL,
    event_id uuid NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

### 15.1. Consumer Transaction

~~~sql
BEGIN;

INSERT INTO app.inbox_events (consumer_name, event_id)
VALUES ('billing-projection', '11111111-1111-4111-8111-111111111111')
ON CONFLICT DO NOTHING;

-- Application checks whether this INSERT created a row.
-- Only a newly claimed event may apply the business update.

UPDATE app.customer_balances
SET order_count = order_count + 1
WHERE customer_id = 42;

UPDATE app.inbox_events
SET processed_at = now()
WHERE consumer_name = 'billing-projection'
  AND event_id = '11111111-1111-4111-8111-111111111111';

COMMIT;
~~~

This illustrates the flow. The consumer executes the UPDATE only when it actually inserts the inbox key. If the key already exists, skip the duplicate event and do not reapply the business update.

### 15.2. Atomic Deduplication

The inbox insert and consumer business update run in the same transaction. If the transaction rolls back, the inbox claim rolls back too, allowing the event to be retried.

### 15.3. Consumer Side Effects Outside the Database

If the consumer also sends an email or calls another API, the inbox transaction does not cover that external side effect. The consumer may need its own outbox or an idempotency key for the downstream dependency.

### 15.4. Inbox Retention

Keep event IDs long enough to cover broker redeliveries, replays, and disaster recovery. Purging inbox records too soon can allow replays to produce duplicate business effects.

## 16. At-Most-Once, At-Least-Once, and Effectively-Once

### 16.1. At-Most-Once

An event is processed at most once, but it can be lost if the consumer crashes after receiving it and before processing/acknowledging per the protocol.

### 16.2. At-Least-Once

An event is retried until acknowledged or policy terminates. Duplicate delivery can occur.

### 16.3. Exactly-Once Claims

"Exactly once" must have a clearly defined scope. A broker may provide its own semantics within a bounded scope, but that does not create an atomic commit across the broker, PostgreSQL, and a payment API.

### 16.4. Effectively-Once Business Effect

A system can achieve business outcomes equivalent to single-time processing using:
- Stable event/operation IDs.
- Unique constraints.
- Inbox/deduplication.
- Idempotent handlers.
- Atomic local state transitions.
- Reconciliation for ambiguous states.

This is a property of a well-designed workflow, not a promise that the network never duplicates messages.

## 17. Saga Pattern

A saga breaks a long business workflow into multiple local transactions, each committing independently. If a later step fails, the system executes compensating actions or transitions the workflow to a state requiring resolution.

Order/payment/shipping example:

~~~text
Create order
    |
    v
Reserve inventory
    |
    v
Authorize payment
    |
    v
Arrange shipment
    |
    v
Complete order

If a later step fails:
    release inventory
    void/refund payment when appropriate
    mark order for compensation/review
~~~

### 17.1. Local Transactions

Each service or database commits its own state. Never hold one database transaction open across the entire saga.

### 17.2. Compensation

Compensation is a business action that offsets a prior step. It is not necessarily a perfect inverse. For example, a sent email cannot be "unsent"; a captured payment may require a refund rather than deleting a transaction.

### 17.3. Saga State Machine

Persist workflow states such as pending, inventory_reserved, payment_authorized, shipment_requested, completed, compensating, failed, or manual_review.

### 17.4. Idempotent Steps

Each saga step has a stable step ID/idempotency key. Retrying a step must not reserve inventory or charge a payment a second time.

### 17.5. Timeouts and Compensation

A timeout does not prove that an external step failed. Before compensating, query the provider's status or retry with the same idempotency key to determine the outcome.

### 17.6. Orchestration vs. Choreography

- Orchestration: a coordinator persists state and drives each step.
- Choreography: services react to events and emit subsequent events.

Orchestration makes centralized state easier to observe; choreography avoids a central coordinator but can make flows harder to trace.

## 18. Storing Saga State in PostgreSQL

~~~sql
CREATE TABLE app.sagas (
    saga_id uuid PRIMARY KEY,
    saga_type text NOT NULL,
    aggregate_id text NOT NULL,
    state text NOT NULL,
    current_step text,
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    last_error text
);

CREATE TABLE app.saga_steps (
    saga_id uuid NOT NULL REFERENCES app.sagas(saga_id),
    step_name text NOT NULL,
    status text NOT NULL,
    idempotency_key text NOT NULL,
    request_payload jsonb,
    result_payload jsonb,
    attempts integer NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (saga_id, step_name),
    UNIQUE (idempotency_key)
);
~~~

### 18.1. Optimistic Concurrency

Use a version column to prevent two workers from updating saga state concurrently:

~~~sql
UPDATE app.sagas
SET state = 'payment_authorized',
    version = version + 1,
    updated_at = now()
WHERE saga_id = $1
  AND version = $2;
~~~

If the affected row count is zero, the worker should re-read the latest state and decide whether to retry or reconcile.

### 18.2. Persist Before Calling Externally

Record the step intent and idempotency key before invoking an external API. If the process crashes, another worker can resume from durable state.

### 18.3. Persist the Outcome After Calling

Upon receiving a response, store the provider operation ID/result and transition state in a transaction. If the response is lost, query the provider using the idempotency key or operation ID.

### 18.4. Compensation State

Store compensation states separately so you know which steps were compensated, which are retrying, and which require manual review.

## 19. Two-Phase Commit (2PC)

Two-phase commit is a protocol that coordinates multiple resource managers to reach a unified commit/abort decision through a coordinator.

Two phases:
1. Prepare: each participant records its readiness to commit and enters the prepared state.
2. Commit/abort: the coordinator broadcasts the final decision to all participants.

~~~text
Coordinator
   |
   +---- PREPARE ----> Participant A
   |                       |
   |                       +-- prepared
   |
   +---- PREPARE ----> Participant B
                           |
                           +-- prepared

If all prepared:
   COMMIT PREPARED on A and B
Else:
   ROLLBACK PREPARED on participants
~~~

### 19.1. 2PC Differs from Outbox/Saga

2PC attempts to achieve an atomic commit among participants supporting the protocol. Outbox/saga rely on durable local transactions and asynchronous delivery/compensation. They do not offer the same semantics.

### 19.2. The Coordinator Needs a Durable Decision Log

If the coordinator crashes after prepare, it must recover its decision from a durable log and finish committing or aborting. Otherwise, participants can remain stuck in-doubt.

### 19.3. Prepared Participants Hold Locks

A prepared transaction can retain locks and transaction resources even after the client session disconnects. If forgotten, it causes blocking and affects vacuum/transaction horizons.

### 19.4. 2PC Does Not Make an HTTP API Participate

An HTTP payment provider typically does not understand PREPARE/COMMIT PREPARED. You cannot turn an HTTP request into an XA participant simply by placing it between two SQL commands.

### 19.5. Operational Cost

2PC requires a reliable transaction manager/coordinator, recovery procedures, prepared-transaction monitoring, and handling for network partitions. Choose it only when every participant supports it and atomicity requirements justify the cost.

## 20. PostgreSQL Prepared Transactions

PostgreSQL supports prepared transactions via SQL commands when max_prepared_transactions is configured greater than zero.

### 20.1. Configuration

~~~sql
SHOW max_prepared_transactions;
~~~

The default is typically 0, meaning prepared transactions are disabled. Changing this setting requires proper server configuration and may require a restart depending on version and deployment.

### 20.2. Prepare

~~~sql
BEGIN;

UPDATE app.accounts
SET balance = balance - 100
WHERE account_id = 10;

PREPARE TRANSACTION 'transfer-2026-0001';
~~~

PREPARE TRANSACTION ends the current transaction and leaves it in the prepared state. The global transaction identifier must be unique within the database per PostgreSQL rules.

### 20.3. Commit Prepared

~~~sql
COMMIT PREPARED 'transfer-2026-0001';
~~~

### 20.4. Rollback Prepared

~~~sql
ROLLBACK PREPARED 'transfer-2026-0001';
~~~

COMMIT PREPARED and ROLLBACK PREPARED must be executed outside a transaction block and according to the coordinator's decision.

### 20.5. Inspecting Prepared Transactions

~~~sql
SELECT
    transaction,
    gid,
    prepared,
    owner,
    database
FROM pg_prepared_xacts
ORDER BY prepared;
~~~

### 20.6. Do Not Use PREPARE TRANSACTION as Arbitrary Pause/Resume

Prepared transactions are not a mechanism for pausing a transaction across an application disconnect and resuming later. They are designed for a transaction manager with an explicit protocol and recovery procedure.

### 20.7. Do Not Arbitrarily Commit/Rollback a GID

DBAs should never decide COMMIT PREPARED or ROLLBACK PREPARED based solely on transaction age. Always consult the coordinator's durable decision log or a runbook designed for distributed transactions.

## 21. Limitations of 2PC

### 21.1. Blocking When the Coordinator Is Unavailable

If a participant has prepared but has not received the final decision, it can hold locks while the coordinator is unreachable. This is the classic blocking property of 2PC.

### 21.2. Participant Support

All participants must support compatible protocols and semantics. An ordinary database driver or API does not automatically provide distributed transaction coordination.

### 21.3. Operational Recovery

You must know:
- Which coordinator owns the GID.
- Where the decision log lives.
- Who is authorized to resolve an in-doubt transaction.
- Timeout and escalation policies.
- How to recover when a participant is unreachable.
- How to avoid resolving contrary to a recorded decision.

### 21.4. Does Not Replace Backups

2PC coordinates commit decisions; it does not replace backups, PITR, disaster recovery, or business reconciliation.

### 21.5. When Should It Be Considered?

When multiple transactional resource managers support 2PC, true atomic commit is required, coordinator and operational complexity are acceptable, and tested recovery procedures exist.

## 22. postgres_fdw and Remote Database Transactions

postgres_fdw allows querying foreign tables on a remote PostgreSQL server. It can coordinate the remote transaction lifecycle with the local transaction within the limits supported by its implementation.

### 22.1. Foreign Server Example

~~~sql
CREATE EXTENSION postgres_fdw;

CREATE SERVER remote_db
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (host 'db.example.internal', dbname 'sales', port '5432');

CREATE USER MAPPING FOR app_user
SERVER remote_db
OPTIONS (user 'remote_reader', password 'managed-secret');

IMPORT FOREIGN SCHEMA public
LIMIT TO (customers)
FROM SERVER remote_db
INTO remote_sales;
~~~

This example illustrates structure only. Credentials must be managed via secret policy; never hard-code passwords in migrations or repositories.

### 22.2. Remote Transactions

When a local transaction accesses a foreign server, postgres_fdw can open a remote transaction and manage it alongside the local transaction. It also handles savepoints/subtransactions as supported.

### 22.3. Do Not Assume Global 2PC

Do not treat a transaction accessing multiple foreign servers and local tables as an unconditionally atomic distributed transaction across all failure modes. postgres_fdw is not a general-purpose coordinator providing 2PC across arbitrary remote participants. Consult the documentation for your version and check the failure semantics of your topology.

### 22.4. Network Failures

If the remote connection drops during commit processing, local and remote outcomes may require reconciliation depending on failure timing and implementation. Never blindly retry a business operation simply because the client received an error.

### 22.5. Query Pushdown

Some filters and joins can be pushed down to the remote server. Pushdown reduces data transfer, but it does not increase atomicity guarantees.

### 22.6. Credential and Role Mapping

USER MAPPING governs the remote identity. Check least privilege, password rotation, and visibility. Do not grant an application role broader remote privileges than required.

## 23. dblink and External SQL Connections

dblink opens connections to another PostgreSQL server and sends SQL. It is a useful integration utility in some workloads, but it does not automatically provide a distributed transaction coordinator.

### 23.1. Remote Calls

dblink can execute queries on a remote connection. The remote transaction has its own lifecycle depending on the connection and commands sent.

### 23.2. Local Rollback Does Not Guarantee Remote Rollback

If a remote statement has already committed or the remote transaction has ended, rolling back the local transaction will not automatically undo the remote change.

### 23.3. Connection Management

Manage the remote connection lifecycle, error handling, credentials, timeouts, and cleanup. Avoid leaving orphaned remote connections behind.

### 23.4. Do Not Mask Failures with Asynchronous Calls

If using dblink_send_query/dblink_get_result, manage result states and connections carefully. Async execution does not make a remote action atomic with the local database.

## 24. External APIs: Payment, Email, and Object Storage

Each external resource has distinct semantics.

### 24.1. Payment Providers

Use provider idempotency keys, store provider operation IDs, track authorization/capture/refund states, and reconcile. Never assume a timeout means the payment did not occur.

### 24.2. Email Services

A sent email generally cannot be rolled back. Use an outbox to send after commit, store message IDs/statuses, and handle retries/deduplication per API support. Never send emails before the business transaction commits.

### 24.3. Object Storage

Uploading an object and writing database metadata are two separate operations. You can upload to a temporary key, then commit metadata/state and promote/finalize in the workflow; or persist a pending state and garbage-collect orphaned objects.

### 24.4. Search Indexes

Database commits and search indexing are usually eventually consistent. Use an outbox/change stream and an idempotent consumer; expose indexing status if needed.

### 24.5. Webhooks

Webhook delivery is typically at-least-once. Use stable event IDs, signature verification, retry schedules, endpoint timeouts, and receiver deduplication.

## 25. Transactional Outbox for API Integration

An application can create an order and request payment in the same database transaction by writing a payment command to an outbox.

~~~sql
CREATE TABLE app.payment_commands (
    command_id uuid PRIMARY KEY,
    order_id bigint NOT NULL REFERENCES app.orders(order_id),
    idempotency_key text NOT NULL UNIQUE,
    amount numeric(14,2) NOT NULL CHECK (amount > 0),
    currency char(3) NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'processing', 'succeeded', 'failed', 'unknown')),
    provider_reference text,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
~~~

Inside the order-creation transaction:

~~~sql
BEGIN;

INSERT INTO app.orders (order_id, status)
VALUES (9001, 'pending_payment');

INSERT INTO app.payment_commands (
    command_id,
    order_id,
    idempotency_key,
    amount,
    currency,
    status
)
VALUES (
    gen_random_uuid(),
    9001,
    'order-9001-payment-v1',
    125.00,
    'USD',
    'pending'
);

COMMIT;
~~~

A worker reads the committed command, calls the provider using the same idempotency key, and stores the outcome in a new transaction.

### 25.1. Provider Idempotency

If the worker times out and does not know whether the provider charged the card, retry with the same provider idempotency key or query operation status. Never generate a new key for the same business intent.

### 25.2. Unknown State

If the provider does not support lookup or idempotency, the state may require manual reconciliation. Never mark it failed automatically just because of a timeout.

### 25.3. Separate Authorization and Capture

Payment workflows often involve multiple steps. Store separate states for authorization, capture, void, and refund. Compensation must follow provider semantics.

## 26. Reconciliation

Reconciliation compares local state against an external system to resolve unknown outcomes or missed events.

### 26.1. When Is Reconciliation Needed?

- Client lost connection around COMMIT.
- Provider timed out after receiving a request.
- Outbox relay published and then crashed.
- Consumer executed a side effect and lost acknowledgment.
- Saga step remained in processing too long.
- External webhook arrived late or duplicated.
- Operator recovered a coordinator after an outage.

### 26.2. Reconciliation Keys

Use order IDs, provider operation IDs, idempotency keys, event IDs, or stable business references. Avoid fuzzy matching whenever explicit identities can be persisted.

### 26.3. Reconciliation Outcomes

- Both external and local succeeded: mark completed.
- External has not processed yet: retry with the same key.
- External succeeded, local not recorded: update local state based on provider evidence.
- External definitely failed: mark failed or initiate compensation.
- Cannot determine: keep unknown/manual_review; never guess.

### 26.4. Audit Trail

Persist request IDs, provider references, timestamps, attempt counts, response codes, and state transitions. Do not store payment secrets or sensitive credentials.

### 26.5. Reconciliation Is Not Blind Data Repair

Every correction must rely on authoritative evidence and be audited. An automated job should never issue refunds or recreate orders based solely on a timeout message.

## 27. Connection Pools and Transaction Boundaries

Connection pooling enables connection reuse, but applications must respect transaction and session state.

### 27.1. Connection Loss

If a connection drops mid-transaction, the backend can roll back once it detects the disconnect. The application must discard the broken connection rather than returning it to the pool as healthy.

### 27.2. Pool Reset

Poolers must reset session state according to their mode. SET variables, temporary tables, prepared statements, advisory locks, and session-level state may not behave as applications expect under transaction pooling.

### 27.3. PgBouncer Transaction Pooling

In transaction pooling, a client is assigned a server connection only for the duration of a transaction. After COMMIT/ROLLBACK, the connection may be assigned to another client. Never rely on session affinity outside a transaction.

### 27.4. External Calls

Do not hold a pooled connection or transaction open while waiting on an API response unless strictly necessary. Doing so shrinks pool capacity and causes queueing.

### 27.5. Broken Connections

After a network exception, verify driver and pool semantics. Mark the connection unusable if needed and open a fresh one. Never resend COMMIT/ROLLBACK over a compromised connection.

## 28. Savepoints Do Not Solve External Atomicity

SAVEPOINT allows rolling back part of the work inside the same PostgreSQL transaction.

~~~sql
BEGIN;

INSERT INTO app.orders(order_id, status)
VALUES (9002, 'created');

SAVEPOINT before_optional_step;

UPDATE app.orders
SET status = 'validated'
WHERE order_id = 9002;

ROLLBACK TO SAVEPOINT before_optional_step;

COMMIT;
~~~

### 28.1. Scope

SAVEPOINT only governs changes within the same transaction. It does not undo emails, payments, broker publishes, or committed remote side effects.

### 28.2. Subtransactions

Savepoints can help recover from partial errors inside a database transaction. Do not use them as a substitute for sagas or 2PC.

### 28.3. External Operation Results

If an external call occurred between SAVEPOINT and ROLLBACK TO SAVEPOINT, the external system has no knowledge of the database savepoint rollback. The application must handle compensation or reconciliation.

## 29. Isolation Levels and External Workflows

Isolation levels govern concurrency between transactions inside PostgreSQL; they do not extend atomicity to external systems.

### 29.1. Read Committed

Each statement gets its own snapshot under Read Committed semantics. A workflow that reads state and calls an external API must protect state transitions from concurrent changes.

### 29.2. Repeatable Read

Keeps a stable snapshot throughout the transaction, but can cause serialization-like errors when concurrent updates occur. Long transactions spanning network calls keep old snapshots alive too long.

### 29.3. Serializable

PostgreSQL may abort a transaction to enforce serializable behavior. The application must retry the entire transaction upon receiving a serialization failure. External side effects should not run before knowing the local transaction committed.

### 29.4. Optimistic State Transitions

Use a version/status predicate:

~~~sql
UPDATE app.orders
SET status = 'processing',
    version = version + 1
WHERE order_id = $1
  AND status = 'pending'
  AND version = $2;
~~~

Check the affected row count. Only one worker can transition state from the version it read if the predicate matches.

### 29.5. Row Locks

SELECT ... FOR UPDATE can protect a local state transition. Holding the lock during a long API call causes contention; usually it is better to claim intent briefly and call externally outside the transaction.

## 30. Timeouts Across Layers

An integration workflow involves multiple distinct timeouts.

| Timeout | Scope | Meaning |
| --- | --- | --- |
| connect_timeout | Client connecting to PostgreSQL | Limits connection establishment time |
| statement_timeout | PostgreSQL statement | Cancels a statement when duration is exceeded |
| lock_timeout | Waiting for lock acquisition | Aborts if waiting for a lock too long |
| idle_in_transaction_session_timeout | Session idle in transaction | Closes sessions sitting idle too long |
| TCP/network timeout | Transport | Limits network wait time |
| HTTP client timeout | External API request | Client stops waiting for a response |
| Provider operation timeout | External system | Provider-specific contract |
| Workflow deadline | Entire business process | Overall time limit |

### 30.1. Timeouts Are Not Cancellation Guarantees

A client timeout only means the client stops waiting. The external server may keep processing. The PostgreSQL backend might also not receive cancellation immediately.

### 30.2. Layered Deadlines

Set timeouts so the overall workflow deadline exceeds the required steps while each dependency has its own bound. Leave headroom for cleanup and reconciliation.

### 30.3. Timeouts and Retries

If a timeout occurs after a request was sent, the outcome may be unknown. Retry with the same idempotency key or query status.

## 31. Circuit Breakers and Bulkheads

### 31.1. Circuit Breaker

When a dependency exhibits a high error rate, a circuit breaker pauses new requests to avoid overloading it. After a cooldown period, it sends probe requests before reopening fully.

### 31.2. Bulkhead

Isolate concurrency pools/queues per dependency so one slow external service does not exhaust all worker threads or connections.

### 31.3. Queue Buffering

An outbox/queue decouples database commit latency from external API latency. Queues require backpressure and capacity bounds.

### 31.4. Never Drop Intent When the Circuit Opens

If the business change already committed, the command/event must remain durably stored (e.g., in the outbox). A circuit breaker only delays delivery; it does not discard intent.

## 32. Ordering and Concurrent Delivery

Events for the same aggregate may require ordering.

### 32.1. Aggregate Version

Increment the version inside the business transaction and store it with the outbox event. Consumers can detect out-of-order events or missing versions.

### 32.2. Partitioning

Keying broker partitions by aggregate ID can preserve ordering within a partition per broker semantics. Global ordering across the entire system is rarely guaranteed.

### 32.3. Outbox Ordering

ORDER BY occurred_at does not automatically guarantee workers publish in exact order if multiple workers claim different batches. If strict ordering matters, serialize by aggregate or use sequence/version checks.

### 32.4. Consumer Version Guards

A consumer can apply only the next expected version, hold early/late events in an inbox, or retry once gaps resolve. Design according to domain requirements.

### 32.5. Clock Ordering

Never rely on timestamps from multiple hosts as an absolute order. Use aggregate versions or database-generated sequences when causal ordering is required.

## 33. Transactional Inbox for Incoming Webhooks

External providers delivering webhooks may retry the same event multiple times. Verify signatures and deduplicate by event ID.

~~~sql
CREATE TABLE app.provider_webhook_inbox (
    provider_name text NOT NULL,
    provider_event_id text NOT NULL,
    payload jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    PRIMARY KEY (provider_name, provider_event_id)
);
~~~

### 33.1. Receive Flow

1. Verify the webhook signature.
2. Parse and validate the event.
3. Insert an inbox row with the unique provider event ID.
4. If duplicate, return an appropriate acknowledgment.
5. Worker processes the event in a transaction.
6. Update business state and processed_at in the same transaction.
7. Retry on transient errors.

### 33.2. Acknowledgment Timing

Only return success to the provider after the event has been durably persisted or processed per contract. Returning success before persistence risks losing the event on a process crash.

### 33.3. Out-of-Order Webhooks

Webhooks can arrive out of order. Check provider event version/timestamp/status transitions and query authoritative provider state when needed.

### 33.4. Signature Replay

Signature verification alone does not stop replays. Combine event ID deduplication, timestamp tolerance windows, and provider security guidelines.

## 34. External File and Object Storage Workflows

Databases and object storage do not share transactions.

### 34.1. Upload First, Metadata Second

If the upload succeeds but the DB insert fails, the object becomes an orphan. Use a temporary key and a garbage collector with a retention window.

### 34.2. Metadata First, Upload Second

If the DB commits metadata first and the upload fails, the row references a nonexistent object. Store a pending_upload state and expose the object only once ready.

### 34.3. Stateful Workflow

~~~text
pending_upload
      |
      v
uploading
      |
      +---- success ----> available
      |
      +---- failure ----> retry / failed
      |
      +---- unknown ----> reconcile provider object
~~~

### 34.4. Cleanup

Delete orphaned objects only after verifying age, ownership, and operation state. Never delete an object simply because a single database query temporarily missed a row.

## 35. External Payment Workflows

Payments require an explicit state machine because timeouts and duplicate charges have direct business impact.

### 35.1. States

Examples:
- pending.
- authorization_requested.
- authorized.
- capture_requested.
- captured.
- failed.
- void_requested.
- voided.
- refund_requested.
- refunded.
- unknown.
- manual_review.

### 35.2. Idempotency per Operation

Authorization, capture, and refund may each need distinct yet stable idempotency keys per intent. Never reuse an authorization key for a separate refund.

### 35.3. Provider References

Store provider payment/operation IDs and response metadata needed to query status.

### 35.4. Timeouts

If a capture request times out, local state becomes unknown until provider status is verified. Retry with the same key per the provider's contract.

### 35.5. Compensation

If an order cannot be fulfilled after authorization, you can void the authorization. If already captured, you can refund. This is business compensation, not database rollback.

## 36. Foreign Systems and Data Consistency Models

### 36.1. Strong Consistency Within One Database

A PostgreSQL transaction provides atomicity and consistency within its transaction boundary.

### 36.2. Eventual Consistency

Outbox/consumer pipelines update downstream projections after commit. For some window, the primary database and search indexes/caches/reporting stores can diverge.

### 36.3. Read-Your-Writes

If clients must see their own writes immediately, read from the primary/local authoritative store or await event/consumer acknowledgment per contract.

### 36.4. Monotonic State Transitions

Define state machines that disallow backward transitions outside designated compensations. Enforce them using conditional UPDATEs and version guards.

### 36.5. Reconciliation Windows

Define how long an operation can stay pending/unknown before triggering alerts or manual review. Never automatically mark operations failed just due to a brief delay.

## 37. Distributed Transactions Across Multiple Databases

An application may update two independent PostgreSQL databases.

### 37.1. Two Local Commits

If database A commits and database B loses connectivity before committing, the two databases diverge. A local transaction on A cannot be rolled back by sending a ROLLBACK to B after A has committed.

### 37.2. Coordinator

If both participants support 2PC, a transaction manager can coordinate prepare/commit. Otherwise, use saga/outbox and reconciliation.

### 37.3. Dual Writes

Writing directly to database A and then database B is the classic dual-write problem. A crash between the two writes creates divergence.

### 37.4. Replication and CDC

CDC can stream changes from one database downstream. It provides asynchronous propagation, not a synchronous global atomic commit.

### 37.5. Source of Truth

Designate a single authoritative system for each piece of data. Avoid treating two databases as simultaneous owners of the same field without conflict resolution.

## 38. Distributed Locks Do Not Replace Transaction Coordination

Advisory locks or external distributed locks help a worker claim work. They do not guarantee atomic commits between a database and an external service.

### 38.1. Lock Leases

A distributed lock can expire while a worker is still running. The old worker could continue applying side effects after a new worker acquires the lock.

### 38.2. Fencing Tokens

Use monotonically increasing fencing tokens if downstream resources can reject writes from stale lock holders.

### 38.3. Idempotency Is Still Required

Locks reduce concurrency but do not solve lost responses, retries, duplicate messages, or crashes after side effects.

## 39. Observability for Transactions and Integrations

Monitor both PostgreSQL and external workflows.

### 39.1. Database Metrics

- Active/idle-in-transaction sessions.
- Long-running transactions.
- Lock waits and deadlocks.
- Transaction commits/rollbacks.
- Connection failures.
- WAL/replication lag.
- Prepared transactions.
- Outbox/inbox table sizes.

### 39.2. Workflow Metrics

- Operations pending/processing/unknown.
- Retry attempts and retry age.
- Oldest unpublished outbox age.
- Publish failure rate.
- Consumer lag.
- Inbox duplicate count.
- Saga duration/compensation count.
- Provider timeout/error rates.
- Reconciliation backlog.

### 39.3. Correlation Identifiers

Propagate request_id, idempotency_key, saga_id, event_id, aggregate_id, and provider_reference across logs and traces. Never log secrets or full payment details.

### 39.4. Prepared Transaction Monitoring

~~~sql
SELECT
    gid,
    prepared,
    owner,
    database,
    now() - prepared AS prepared_age
FROM pg_prepared_xacts
ORDER BY prepared;
~~~

Alert on prepared transactions lasting longer than the expected protocol window. Resolution must follow the coordinator decision log.

### 39.5. Long Transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 300) AS query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Identify idle-in-transaction sessions and transactions holding locks or snapshots too long.

## 40. Failure Injection and Testing

Reliability must be tested in controlled environments.

### 40.1. Disconnect Before COMMIT

Drop the connection before sending COMMIT and verify the transaction rolls back when the session closes.

### 40.2. Lost Response After COMMIT

Use a proxy or test harness to drop the response after the server receives COMMIT. Verify the client can look up operation status using its idempotency key.

### 40.3. Worker Crash After Publish

Simulate the broker receiving an event while the worker crashes before marking the outbox row published. Consumers must handle the duplicate safely.

### 40.4. Consumer Crash Before Commit

Verify that the inbox claim and business update roll back together so the event can be retried.

### 40.5. Provider Timeout

Simulate the provider processing a request while the response times out. The worker must reuse the same idempotency key or query status.

### 40.6. Coordinator Crash

If using 2PC, rehearse a coordinator crash after prepare and verify recovery via the decision log before resolving prepared transactions.

### 40.7. Clock Skew and Delayed Messages

Test late, out-of-order webhooks/events and skewed clocks. Rely on versions and identities rather than timestamps alone.

## 41. Security for External Integrations

- Use TLS and verify certificates for database and API connections.
- Store secrets in a secret manager.
- Enforce least privilege for remote roles and application roles.
- Never write credentials or payment tokens into outbox payloads.
- Verify webhook signatures and protect against replays.
- Validate payload schemas and versions.
- Enforce request size limits and rate limits.
- Redact PII in logs and traces.
- Rotate provider credentials on a schedule.
- Audit manual compensation and refund actions.

## 42. Common Anti-Patterns

| Anti-Pattern | Consequence | Correct Approach |
| --- | --- | --- |
| Calling a payment API inside a long transaction | Holds locks/connections and still is not atomic | Outbox + provider idempotency |
| Assuming DB rollback undoes an email | Sent email still exists | Send after commit via outbox |
| Retrying blindly after connection error around COMMIT | Can duplicate the business operation | Query state by idempotency key |
| Generating a new key on every retry | Provider cannot deduplicate | Keep key stable for the same intent |
| SELECT then INSERT idempotency key | Race condition across concurrent requests | Unique constraint + ON CONFLICT |
| Publishing event before DB commit | Consumers see events from rolled-back transactions | Transactional outbox |
| Marking published before broker acknowledgment | Events can be lost | Publish then record acknowledgment |
| Assuming broker exactly-once covers the DB | Cross-system side effects still duplicate | Inbox/idempotent consumer |
| Consumer ack before persisting | Crash can lose the event | Persist inbox before acknowledgment |
| Inbox and business update in separate transactions | Duplicates or lost consistency | Commit in the same transaction |
| Holding DB transaction open during API calls | Locks/snapshots/connections held too long | Commit intent, call outside transaction |
| Treating timeout as operation failed | Provider may have processed it | Unknown state and reconciliation |
| Assuming saga compensation is a perfect rollback | Side effects cannot always be undone | Explicit business compensation |
| Using 2PC with an unsupported HTTP service | No prepare protocol exists | Outbox/saga |
| Leaving prepared transactions orphaned | Locks and xid resources persist long-term | Coordinator recovery/monitoring |
| Committing prepared transactions by age alone | Can contradict the decision log | Resolve via coordinator |
| Treating FDW as global atomic commit | Remote/local failures can diverge | Evaluate semantics, outbox/saga |
| Unbounded retries | Retry storm | Backoff, jitter, deadline, budget |
| Ordering events by timestamp alone | Clock skew/out-of-order delivery | Aggregate version/sequence |
| Not reconciling unknown states | Divergence persists indefinitely | Durable reconciliation workflow |

## 43. PostgreSQL Hands-On Exercises

Perform these in a lab or staging environment using test services. Never trigger real payments, emails, or external production mutations solely for testing.

1. **Local atomicity:** create a transaction updating two tables and roll it back.
2. **Commit:** commit a transaction and verify the state from another connection.
3. **Disconnect:** drop the connection before COMMIT and observe the rollback.
4. **Ambiguous commit:** simulate a lost response after COMMIT.
5. **SQLSTATE:** classify 40001, 40P01, 23505, and class 08 errors.
6. **Serialization retry:** run concurrent serializable transactions and retry the full transaction.
7. **Deadlock retry:** trigger a controlled deadlock and handle 40P01.
8. **Client timeout:** distinguish a client timeout from server cancellation.
9. **Idempotency schema:** create an idempotency_requests table with a unique key.
10. **Request hash:** use a hash to detect the same key with a different payload.
11. **Concurrent requests:** send two requests with the same idempotency key.
12. **Duplicate response:** return the stored response for repeated requests.
13. **Key expiry:** design retention aligned with the retry window.
14. **Local transaction:** write the business row and idempotency result in one transaction.
15. **Unique conflict:** distinguish duplicate requests from business unique violations.
16. **Backoff:** implement capped exponential backoff.
17. **Jitter:** add random jitter to retry workers.
18. **Deadline:** bound total retry duration.
19. **Retry budget:** track a retries-per-request metric.
20. **Outbox schema:** create outbox_events with event_id.
21. **Atomic outbox:** update an order and insert an event in the same transaction.
22. **Rollback test:** force the outbox insert to fail and verify the business update rolls back.
23. **Relay:** build a worker polling unpublished events.
24. **SKIP LOCKED:** run two competing relay workers.
25. **Lease:** add locked_by/locked_until for outbox claims.
26. **Publish crash:** simulate crashing after publish and before updating published_at.
27. **Duplicate delivery:** verify the consumer safely tolerates duplicates.
28. **Inbox schema:** create inbox_events with a unique consumer/event key.
29. **Inbox atomicity:** commit the inbox claim and business update in the same transaction.
30. **Consumer rollback:** force the business update to fail and verify the inbox claim rolls back.
31. **Retention:** define an outbox/inbox retention policy.
32. **Ordering:** add aggregate_version to events.
33. **Out-of-order:** simulate events arriving out of order.
34. **Saga schema:** create sagas and saga_steps tables.
35. **Saga state:** implement conditional state transitions.
36. **Optimistic locking:** use a version column to prevent concurrent updates.
37. **Compensation:** simulate reserving inventory and then releasing it.
38. **Payment timeout:** simulate the provider processing a charge while the response times out.
39. **Provider key:** retry payment with the same idempotency key.
40. **Unknown state:** store an unknown operation and reconcile it.
41. **Orchestration:** implement a simple saga coordinator.
42. **Choreography:** design an event-driven workflow and analyze its observability.
43. **2PC setting:** inspect max_prepared_transactions.
44. **Prepared transaction:** test PREPARE TRANSACTION in the lab.
45. **Commit prepared:** finalize with COMMIT PREPARED.
46. **Rollback prepared:** abort with ROLLBACK PREPARED.
47. **Catalog:** query pg_prepared_xacts.
48. **In-doubt:** simulate a coordinator crash after prepare and inspect the recovery log.
49. **Lock retention:** observe locks held by a prepared transaction.
50. **Cleanup policy:** write a runbook to resolve prepared transactions via the coordinator.
51. **FDW:** install postgres_fdw and query a remote table.
52. **FDW transaction:** test local/remote updates inside a single lab transaction.
53. **FDW failure:** simulate network loss and analyze commit outcomes.
54. **dblink:** execute a remote query and manage the connection lifecycle.
55. **Dual database:** simulate DB A committing while DB B fails.
56. **Outbox vs. 2PC:** choose a pattern between two PostgreSQL services.
57. **Webhook inbox:** store provider event IDs and deduplicate.
58. **Webhook signature:** verify signatures before persisting.
59. **Replay:** replay a webhook and verify business effects do not repeat.
60. **Object storage:** design pending_upload/available states.
61. **Orphan cleanup:** build a garbage collector for uploaded objects without metadata.
62. **Email:** emit an outbox event for email after order commit.
63. **Search projection:** update a search index using an asynchronous consumer.
64. **PgBouncer:** test behavior under transaction pooling.
65. **Session state:** test SET/temp tables/session advisory locks through transaction pooling.
66. **Connection pool:** discard broken connections after network exceptions.
67. **Timeout layers:** configure connect/statement/lock/HTTP/workflow deadlines.
68. **Circuit breaker:** simulate a provider outage and trip the circuit.
69. **Bulkhead:** isolate worker pools per external dependency.
70. **Backpressure:** throttle outbox relay concurrency when a provider slows down.
71. **Monitoring:** build dashboards for outbox age and retry rate.
72. **Reconciliation:** create a report of operations stuck in unknown too long.
73. **Correlation:** propagate request_id/event_id/saga_id across logs.
74. **Prepared alert:** alert on prepared transactions exceeding policy age.
75. **Long transaction:** identify idle-in-transaction sessions.
76. **Failure injection:** drop connections at points around COMMIT.
77. **Worker crash:** crash the relay after publish and verify duplicate handling.
78. **Restore:** restore a database with pending outbox rows and resume relaying.
79. **DR rehearsal:** restore the database and reconcile external provider states.
80. **End-to-end design:** build an order/payment/shipping workflow with PostgreSQL transactions, idempotency keys, transactional outbox, inbox deduplication, saga compensation, reconciliation, monitoring, and tested failure recovery.

## 44. Integration Design Checklist

### Transaction Boundary

- [ ] Clearly define what data belongs within a single PostgreSQL transaction.
- [ ] Verify whether external APIs/brokers/storage have their own transaction protocols.
- [ ] Never assume local rollback undoes external side effects.
- [ ] Avoid holding transactions open across long network calls.
- [ ] Handle ambiguous outcomes around COMMIT.

### Idempotency and Retries

- [ ] Every business intent has a stable idempotency key.
- [ ] Keys are unique within an appropriate scope.
- [ ] Request hashes detect payload mismatches.
- [ ] Retries have bounded attempts, backoff, jitter, and deadlines.
- [ ] Connection errors around COMMIT are reconciled.
- [ ] Provider API support for idempotency/status lookup is verified.

### Outbox/Inbox

- [ ] Business state and outbox event commit in the same transaction.
- [ ] Relay publishes only committed events.
- [ ] Relay survives crashes after publishing.
- [ ] Consumers deduplicate using a unique inbox key.
- [ ] Inbox claim and business update commit in the same transaction.
- [ ] Ordering/versioning and retention are defined.
- [ ] Outbox backlog has alerts and backpressure.

### Saga/2PC

- [ ] Saga steps and compensations are defined.
- [ ] Unknown states are never automatically marked failed.
- [ ] 2PC is used only when every participant supports it.
- [ ] Coordinator maintains a durable decision log.
- [ ] Prepared transactions are monitored and recovered per policy.
- [ ] No in-doubt GID is left without an owner.

### Operations

- [ ] Connection pools discard broken connections.
- [ ] Layer-by-layer timeouts are configured.
- [ ] Circuit breakers/bulkheads are in place.
- [ ] Correlation IDs flow through all logs.
- [ ] Reconciliation has a schedule and owner.
- [ ] Failure injection/restore drills are performed.
- [ ] Secrets/PII are protected in outboxes and logs.

## 45. Summary

A PostgreSQL transaction provides atomicity for changes inside that database transaction. An external API, broker, object store, or independent database has its own resource manager and failure modes. Network failures can leave the client unsure whether COMMIT succeeded, or leave an external system with completed side effects despite a lost response.

~~~text
LOCAL BUSINESS CHANGE
       |
       v
POSTGRESQL TRANSACTION
  update business state
  insert outbox command/event
       |
       v
COMMIT
       |
       v
RELAY / WORKER
       |
       v
EXTERNAL SYSTEM
       |
       +---- acknowledged ----> record result
       |
       +---- timeout/lost reply -> unknown
                                      |
                                      v
                              idempotent retry
                              or reconciliation
~~~

Key principles to remember:

- **ACID has a boundary.** A PostgreSQL transaction does not automatically cover HTTP, email, message brokers, object storage, or an independent database.
- **Disconnects around COMMIT create ambiguous outcomes.** Clients cannot infer a transaction rollback from a connection error alone.
- **Never retry side effects blindly.** Use stable operation IDs and idempotency keys to identify the same business intent.
- **Retry by error class.** Serialization/deadlock errors may call for full transaction retries; connection loss around commit requires state verification.
- **Outbox records durable intent alongside business state.** The relay publishes after commit and consumers must tolerate duplicate deliveries.
- **Inbox deduplicates inside a local transaction.** Claiming the event and applying the business update must commit together.
- **Sagas split workflows into local transactions.** Compensation is a business action, not a physical rollback of an already-executed side effect.
- **2PC requires support from all participants and a coordinator.** Prepared transactions can hold locks; a durable decision log and recovery procedure are mandatory.
- **FDW/dblink do not automatically create global atomicity.** Understand the semantics and failure behavior of each remote integration.
- **Timeouts do not mean an operation failed.** Use unknown states, provider status lookups, and reconciliation.
- **Keep database transactions short.** Never hold locks, snapshots, or pooled connections while waiting on long external network calls.
- **Test failure points.** Simulate lost commit responses, duplicate publishes, worker crashes, and provider timeouts before production rollout.

Reliable integration does not rely on assuming the network always replies on time. It persists durable intent, identifies retries, tolerates duplicate deliveries, tracks uncertain states, and enforces reconciliation procedures to converge systems back to a consistent business state.
