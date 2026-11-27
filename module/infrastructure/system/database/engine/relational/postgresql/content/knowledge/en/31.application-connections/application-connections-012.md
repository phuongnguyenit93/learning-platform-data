# LISTEN, NOTIFY, and Limits of In-Database Notifications in PostgreSQL

In applications maintaining multiple connections to PostgreSQL, a process sometimes needs to know **data has just changed** in order to refresh a cache, wake up a worker, update a dashboard, or start processing new tasks. If the worker constantly runs `SELECT` to poll a table, the system can generate heavy query traffic even when there is no new work.

PostgreSQL provides an **asynchronous notifications** mechanism with three main elements:

- `LISTEN channel`: registers a **session** to listen for notifications on a named channel.
- `NOTIFY channel, 'payload'`: sends a notification to sessions listening on that channel.
- `pg_notify(channel, payload)`: equivalent function, convenient when the channel or payload is a dynamic expression or bound via JDBC.

Example with two sessions connected to the same database:

~~~sql
-- Session A: register listener.
LISTEN app_events;

-- Session B: send notification.
NOTIFY app_events, 'changed';
~~~

After the sending transaction executes **COMMIT**, eligible listeners receive a notification carrying the channel name, payload, and backend process ID of the sender.

**However, `LISTEN`/`NOTIFY` is not a durable message queue.** A disconnected listener can miss notifications. PostgreSQL does not store per-consumer offsets, does not offer replay for missed notifications, and does not know whether business processing succeeded.

This lesson, **“LISTEN, NOTIFY, and Limits of In-Database Notifications”**, belongs to the **Application Connections** chapter of the **Relational Database Engine — PostgreSQL** module. It covers syntax, transaction semantics, database/session scope, ordering and coalescing, payload and queue limits, security, Java/pgJDBC usage, outbox design, operations, and practice exercises.

> **Safety note:** table and trigger examples are strictly for a lab database. Never put secrets, PII, or critical transaction data in `NOTIFY` as the sole storage medium. Before changing production systems, check privileges, notification load, and transaction semantics first.

---

## 1. Why Not Poll Only?

A worker might continuously execute:

~~~sql
SELECT task_id, title
FROM tasks
WHERE status = 'pending'
ORDER BY task_id
LIMIT 10;
~~~

When no new tasks exist, repeated queries waste network round trips, planning/execution CPU, I/O, and connection activity.

Polling flow:

~~~text
Worker               Database
  |----- SELECT -------->|
  |<------ 0 rows -------|
  |----- SELECT -------->|
  |<------ 0 rows -------|
  |----- SELECT -------->|
  |<------ 1 row --------|
~~~

With `NOTIFY`, a write transaction can emit a signal:

~~~text
Application --INSERT task + NOTIFY--> PostgreSQL
                     |
                   COMMIT
                     |
                     v
                   Listener
                     |
                     v
               SELECT tasks
~~~

The worker queries primarily when signaled or on a backup reconciliation timer. This cuts detection latency while online, yet **does not eliminate polling altogether** when data must never be missed.

## 2. Distinguishing a Notification from a Business Event

A notification may carry only:

~~~text
channel = jobs_changed
payload = changed
~~~

A business event needing reliable processing might contain:

~~~json
{
  "event_id": 901,
  "event_type": "task_created",
  "task_id": 41,
  "version": 1
}
~~~

If an event lives only inside `NOTIFY`, a listener offline at emission time will never receive that event upon reconnecting.

A sound design typically looks like:

- Store tasks/events in a **durable table**.
- Use `NOTIFY` as a **wake-up hint**.
- On receiving the hint, query the table for rows to process.
- Implement retries, idempotency, and reconciliation.

### 2.1. When Is Standalone `NOTIFY` Enough?

For a **loss-tolerant signal**—such as hinting a UI refresh or invalidating a TTL-bounded cache—direct `NOTIFY` can suffice. Even then, without a TTL or periodic poll, a missed notification leaves the cache stale until another change occurs.

## 3. `LISTEN` Syntax

~~~sql
LISTEN channel_name;
~~~

Example:

~~~sql
LISTEN inventory_changed;
~~~

Subscriptions belong to the **current PostgreSQL session**.

One session corresponds to one connection/backend. When that session closes:

- The session's `LISTEN` registrations vanish.
- A new connection does not inherit prior `LISTEN`s.
- The application must re-issue `LISTEN` after reconnecting.

### 3.1. `LISTEN` Does Not Query Existing Data

`LISTEN inventory_changed` does not check how many rows exist in an inventory table and does not replay notifications sent before registration. It only subscribes to future matching notifications.

## 4. `NOTIFY` Syntax

~~~sql
NOTIFY channel_name;

NOTIFY channel_name, 'payload';
~~~

Example:

~~~sql
NOTIFY inventory_changed, 'item_updated';
~~~

`NOTIFY` syntax takes an SQL identifier for the channel and an optional literal payload string.

When building payloads dynamically, `pg_notify` is much more convenient.

### 4.1. `NOTIFY` Succeeds Even When Nobody Is Listening

A session can emit a notification with zero listeners attached. It does not become a durable event waiting for future subscribers.

### 4.2. `NOTIFY` Writes No Row to a Business Table

No table named `inventory_changed` is created automatically. A channel is purely a logical notification stream name shared across sessions.

## 5. `pg_notify` for Dynamic Data

~~~sql
SELECT pg_notify(
    'inventory_changed',
    json_build_object(
        'kind', 'item_updated',
        'item_id', 1001
    )::TEXT
);
~~~

`pg_notify(channel TEXT, payload TEXT)` can be called from SQL or PL/pgSQL.

Inside a PL/pgSQL function or procedure, when discarding the return value, use:

~~~sql
PERFORM pg_notify(
    'inventory_changed',
    'changed'
);
~~~

### 5.1. Why Send a Hint Instead of the Full Record?

Payloads stay tiny and predictable in bytes, never carry sensitive data, and force listeners to fetch records from authoritative tables governed by `GRANT` and RLS policies.

## 6. Channel Names and Case Sensitivity

Channel names in `LISTEN` and `NOTIFY` follow PostgreSQL identifier rules.

~~~sql
LISTEN AppEvents;
~~~

Unquoted identifiers are folded to lowercase. If you quote:

~~~sql
LISTEN "AppEvents";
~~~

the identifier becomes case-sensitive.

The channel argument in:

~~~sql
SELECT pg_notify('AppEvents', 'changed');
~~~

is a `text` string, not folded to lowercase by the SQL parser like an unquoted identifier. Never mix quoted and unquoted names accidentally.

**Good convention:** use lowercase `snake_case` names such as `orders_changed`.

### 6.1. Channel Identifiers Cannot Be Arbitrarily Long

Under standard PostgreSQL builds, identifiers default to a maximum of roughly **63 bytes**. Never encode JSON, tokens, or arbitrary paths into channel names.

## 7. `LISTEN`/`NOTIFY` Scope Is a Single Database

~~~text
PostgreSQL cluster
  |
  +-- database_a
  |     +-- Session A: LISTEN events
  |     +-- Session B: NOTIFY events
  |                  |
  |                  +--> A receives it
  |
  +-- database_b
        +-- Session C: LISTEN events
                     |
                     +--> Does NOT receive events from database_a
~~~

**Same cluster does not mean same database.** `LISTEN`/`NOTIFY` does not cross from database A to database B.

Nor is it an automatic pub/sub bus spanning multiple PostgreSQL clusters or operating independently across read replicas.

## 8. `LISTEN` Registration Takes Effect at `COMMIT`

If you run:

~~~sql
BEGIN;

LISTEN orders_changed;

COMMIT;
~~~

the `LISTEN` registration takes effect when the transaction commits per PostgreSQL semantics.

If you run:

~~~sql
BEGIN;

LISTEN orders_changed;

ROLLBACK;
~~~

the new registration is not applied.

### 8.1. Why Does This Matter?

If code opens a transaction, issues `LISTEN`, and never commits it, the listener may not actually be subscribed yet. Any notifications emitted in the meantime will not wait for it to commit.

`UNLISTEN` inside a transaction follows matching commit/rollback semantics.

## 9. Listener Session and Publisher Session

Open two terminal/`psql` connections to the same database.

**Session A:**

~~~sql
LISTEN demo_channel;
~~~

**Session B:**

~~~sql
NOTIFY demo_channel, 'hello';
~~~

Once B commits, Session A receives the notification. In `psql`, if it has not printed yet, run:

~~~sql
SELECT 1;
~~~

to drive protocol message polling and display queued notifications.

Each notification reports:

- Channel name.
- Payload.
- PID of the sending backend.

### 9.1. PID Is Not an Event ID

~~~sql
SELECT pg_backend_pid();
~~~

returns the backend process ID of the current session. PIDs help diagnostics and filtering self-notifications, but are not durable event keys; PIDs change across reconnects and are recycled by the OS.

## 10. `NOTIFY` Is Emitted Only Upon `COMMIT`

In Session B:

~~~sql
BEGIN;

NOTIFY demo_channel, 'not_yet_committed';

-- Before COMMIT, listeners have not received this notification yet.
~~~

Only upon:

~~~sql
COMMIT;
~~~

is the notification delivered to eligible listeners.

### 10.1. Why Is This a Good Property?

If code inserts a task and calls `NOTIFY` but later rolls back the transaction, workers are never woken up for a task that never existed in committed state.

### 10.2. Sending Succeeding Does Not Mean Processing Succeeded

The sender's `COMMIT` does not wait for listeners to finish business work, and PostgreSQL has no per-consumer ACK mechanism confirming processing.

## 11. `ROLLBACK` Cancels Uncommitted Notifications

~~~sql
BEGIN;

NOTIFY demo_channel, 'will_disappear';

ROLLBACK;
~~~

This notification is never delivered as a committed event.

`NOTIFY` calls inside triggers within the writing transaction follow identical semantics.

**Never try to use notifications as a side-channel to emit durable events when the business transaction rolls back.**

## 12. Listeners Inside Open Transactions Receive Notifications Late

A session subscribed via `LISTEN` that holds a long transaction open delays notification delivery to that client until its transaction ends.

Example Session A:

~~~sql
BEGIN;

SELECT pg_sleep(5);

COMMIT;
~~~

If Session B emits `NOTIFY` while A's transaction is open, A only observes the notification after A finishes its transaction.

### 12.1. Consequences

- Workers receive events late.
- Long transactions hold resources.
- Cleaning the shared notification queue can be hindered under certain conditions.
- The application appears “asleep” despite new data arriving.

That is why a listener should hold a **dedicated connection** and **never keep long transactions open** while waiting.

## 13. Startup Race Condition

An unsafe startup sequence:

~~~text
1. Worker SELECT pending jobs -> 0
2. API INSERT job, NOTIFY, COMMIT
3. Worker LISTEN channel, COMMIT
4. Worker waits forever
~~~

Step 2's notification fired before the worker registered. The job sits in the database, yet the worker is never woken up.

### 13.1. Safer Startup Sequence

~~~text
1. Open listener connection.
2. LISTEN channel.
3. Commit the LISTEN registration.
4. Query/reconcile the durable tasks table.
5. Wait for notifications.
6. Upon every notification, re-query the table.
7. Poll periodically to recover from missed signals.
~~~

A `NOTIFY` arriving between Steps 3 and 4 may correspond to a row already read in Step 4. Handle that via **idempotent processing** rather than assuming every `NOTIFY` maps strictly to an unseen event.

## 14. Identical Notifications in the Same Transaction Coalesce

If one transaction emits multiple notifications with the **exact same channel and payload**:

~~~sql
BEGIN;

SELECT pg_notify('demo_channel', 'same');
SELECT pg_notify('demo_channel', 'same');
SELECT pg_notify('demo_channel', 'same');

COMMIT;
~~~

PostgreSQL may deliver **a single** notification for that identical channel/payload pair.

### 14.1. Distinct Payloads

~~~sql
BEGIN;

SELECT pg_notify('demo_channel', 'a');
SELECT pg_notify('demo_channel', 'b');

COMMIT;
~~~

Distinct payloads are not coalesced under the identical channel/payload rule.

### 14.2. Separate Transactions

Two separate transactions both sending `'same'` do not coalesce with each other under the within-transaction deduplication rule.

### 14.3. Lesson

**Never infer row or event counts from how many notifications arrive.** One transaction can insert 1,000 rows and emit only one wake-up hint.

## 15. Notification Ordering

PostgreSQL preserves notification ordering consistent with emission order inside a transaction and commit order across transactions.

Still, distinguish carefully between:

- Order of `NOTIFY` calls.
- Order of `COMMIT`s.
- Order of generated sequence/identity IDs.
- Business ordering by timestamp or version.

They are not always identical.

### 15.1. Identity ID Order Is Not Commit Order

~~~text
Transaction T1 gets event_id=100, stays open
Transaction T2 gets event_id=101, COMMITs first
Worker sees 101
Transaction T1 COMMITs afterward
Only now does worker see 100
~~~

If a worker stores `last_id = 101` and only queries `event_id > 101`, event 100 gets skipped permanently. Never rely on a simple high-watermark sequence cursor when concurrent transactions can commit out of ID order without a gap-handling mechanism.

## 16. A Session Can Hear Its Own Notifications

If a session both `LISTEN`s and `NOTIFY`s on the same channel, it receives notifications sent by its own backend after commit.

In pgJDBC, each `PGNotification` carries the sender's PID; comparing it to the connection's `pg_backend_pid()` identifies self-notifications.

Even so, design idempotent processing rather than treating PIDs as durable business keys.

## 17. Payloads Are Bounded in Bytes

Under standard PostgreSQL configuration, a `NOTIFY` payload must be **shorter than roughly 8000 bytes**.

**Bytes are not characters.** Vietnamese text or emojis occupy more UTF-8 bytes than displayed characters or Java UTF-16 code units.

### 17.1. Measuring Bytes

~~~sql
SELECT
    octet_length('đã thay đổi'::TEXT) AS bytes,
    length('đã thay đổi'::TEXT) AS characters;
~~~

If a payload is oversized:

~~~sql
SELECT pg_notify(
    'orders_changed',
    repeat('x', 100000)
);
~~~

the call exceeds the standard limit and fails. You do not need to run this call just to verify it fails.

### 17.2. Best Practice: Send an ID or Hint

~~~sql
SELECT pg_notify(
    'orders_changed',
    '{"event_id":901}'::TEXT
);
~~~

Or:

~~~sql
SELECT pg_notify(
    'orders_changed',
    'changed'
);
~~~

The worker queries the corresponding event or task from its table.

## 18. Never Send Sensitive Payloads

Keep payloads free of:

- Passwords, tokens, API keys.
- Payment details or PII.
- Medical records or private user data.
- Entire JSON business records.
- Internal structures requiring tenant-scoped authorization.

With `LISTEN`/`NOTIFY`, channels have **no broker-style per-topic ACL** restricting subscriptions to specific users via channel `GRANT`s.

Therefore keep payloads compact, non-sensitive, and never treat them as proof of authorization.

## 19. There Is No `GRANT LISTEN ON CHANNEL`

PostgreSQL does not support channel-level SQL grants like:

~~~sql
-- Not valid syntax:
-- GRANT LISTEN ON CHANNEL orders_changed TO app_user;
~~~

Any role permitted to connect to the database can `LISTEN`/`NOTIFY` on valid channel names.

When distinct trust boundaries exist, enforce security via:

- Database `CONNECT` privileges.
- Roles, network credentials, and TLS.
- `GRANT` and RLS on source tables.
- Careful secret and connection isolation.
- Workers reading authoritative rows from the DB rather than trusting payloads.

**An obscure channel name is not security.**

## 20. The Notification Queue Is Finite

PostgreSQL maintains a shared notification queue for delivering notifications to database listeners.

This queue has finite capacity; PostgreSQL documentation notes a large capacity (typically around **8 GB** in standard builds), yet it is not infinite.

When the queue fills up:

- Systems should alert.
- Transactions executing `NOTIFY` can fail at `COMMIT`.
- Long-running listener transactions can prevent queue cleanup.

### 20.1. Observing Queue Usage

~~~sql
SELECT pg_notification_queue_usage();
~~~

The returned number is a **fraction of queue capacity currently used**, not the count of unprocessed business events.

Example:

~~~sql
SELECT
    pg_notification_queue_usage()
        AS queue_fraction;
~~~

A value approaching `1` signals heavy queue pressure needing investigation. You cannot infer pending task counts from this function.

## 21. Why Are Long Listener Transactions Dangerous?

If a listening session keeps an open transaction idle or busy for a long time, PostgreSQL must retain notification queue state to honor delivery semantics.

Questions to ask when queue usage climbs:

1. Is any listener stuck `idle in transaction`?
2. Is a long query/report running on a listener connection?
3. Are publishers emitting unique payloads per row?
4. Did bulk DML trigger massive per-row `NOTIFY`s?
5. Are network stalls slowing down listener reads?
6. Should notifications be throttled or collapsed into coarse hints?

Adding per-row `NOTIFY` triggers blindly can degrade DML and commit latency.

## 22. A Full Queue Can Break Business Transactions

Unlike fire-and-forget channels that silently drop messages under backpressure, `NOTIFY` ties into transaction commit and queue management.

Once the queue fills completely, transactions calling `NOTIFY` fail to commit. If an order-creation trigger fires `NOTIFY` inside the order transaction, notification queue saturation can block **committing orders**.

Monitoring queue usage and controlling notification volume is therefore an operational requirement, not just tuning.

## 23. Offline Listeners Receive No Replay

~~~text
10:00  Listener A online, LISTEN jobs_changed
10:01  DB sends event X, A receives it
10:02  A loses connection
10:03  DB sends event Y, A misses it
10:04  A reconnects and runs LISTEN
10:05  DB sends event Z, A receives it
~~~

Notification Y is never resent automatically on the new connection.

Whenever Y represents mandatory work, it must sit in **durable rows** that A finds upon reconnecting.

## 24. No Business ACK

When a listener receives:

~~~text
channel=jobs_changed
payload=changed
~~~

PostgreSQL has no idea whether the worker:

- Queried the pending table yet.
- Processed the item successfully.
- Finished calling downstream APIs.
- Committed its result.
- Crashed mid-way.

`LISTEN`/`NOTIFY` has no built-in per-event ACK API telling the server to redeliver that exact message to another consumer.

## 25. No Consumer Groups

If three sessions all `LISTEN` on the same channel:

~~~text
             NOTIFY jobs_changed
                      |
            +---------+---------+
            |         |         |
         Worker A  Worker B  Worker C
~~~

all three receive the hint. PostgreSQL **does not load-balance** “task 1 to A, task 2 to B” like a broker consumer group.

When only one worker may process each task, implement **atomic claiming**, row locks, leases, and idempotency.

## 26. Role of a Dedicated Listener Connection

A well-designed listener typically:

- Keeps a single persistent session open.
- Uses `autoCommit=true`.
- Never holds open long transactions while waiting.
- Issues `LISTEN` immediately upon connecting.
- Polls notifications via pgJDBC/protocol.
- Reconnects and re-issues `LISTEN` on failure.
- Periodically reconciles durable state.

Never reuse the listener session to run long reporting SQL or heavy business transactions.

## 27. Why Connection Pools Complicate `LISTEN`

Suppose:

~~~text
Worker borrows connection X from pool
Worker executes LISTEN jobs_changed
Worker returns X to pool
Another request gets X, opens a long transaction
Worker mistakenly believes it still owns the listener
~~~

`LISTEN` binds to **session X**, not to the application's listener Java object.

Solution: hold a **dedicated connection** outside the general request pool for listening, and never return it while active. Use a separate `DataSource` if helpful for clear lifecycle isolation.

## 28. Lab: Creating `tasks` and `outbox` Tables

Run in an **empty lab database**:

~~~sql
CREATE SCHEMA notify_lab;

CREATE TABLE notify_lab.tasks (
    task_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending', 'processing', 'done', 'failed'
        )),
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);

CREATE TABLE notify_lab.outbox (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id BIGINT NOT NULL
        REFERENCES notify_lab.tasks(task_id),
    event_type TEXT NOT NULL,
    event_data JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);

CREATE INDEX idx_outbox_unpublished
ON notify_lab.outbox(event_id)
WHERE published_at IS NULL;
~~~

Each table has a distinct role:

- `tasks`: source of truth for task state.
- `outbox`: source of truth for events awaiting relay/processing.
- `NOTIFY` is strictly a **hint**, not stored in table structures.

## 29. Procedure Creating Task and Event Atomically

~~~sql
CREATE PROCEDURE notify_lab.create_task(
    IN p_title TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_task_id BIGINT;
BEGIN
    IF p_title IS NULL
       OR btrim(p_title) = ''
    THEN
        RAISE EXCEPTION
            'Task title must not be empty';
    END IF;

    INSERT INTO notify_lab.tasks (title)
    VALUES (p_title)
    RETURNING task_id INTO v_task_id;

    INSERT INTO notify_lab.outbox (
        task_id,
        event_type,
        event_data
    )
    VALUES (
        v_task_id,
        'task_created',
        jsonb_build_object(
            'task_id', v_task_id,
            'kind', 'task_created'
        )
    );
END;
$$;
~~~

This procedure **does not commit internally**. Caller:

~~~sql
BEGIN;

CALL notify_lab.create_task('Import invoice A');

COMMIT;
~~~

If the transaction rolls back, both the task and outbox event roll back together.

### 29.1. Why Atomicity Matters

It eliminates split-brain states:

- Task committed while the event is missing.
- Event dispatched externally while the task ultimately rolled back.

A transactional outbox guarantees atomicity between business state and the event record inside the same PostgreSQL transaction.

## 30. Trigger Emitting a Hint When Outbox Gets New Rows

Create an `AFTER STATEMENT` trigger using a transition relation:

~~~sql
CREATE FUNCTION notify_lab.notify_outbox_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM inserted_rows
    ) THEN
        PERFORM pg_notify(
            'notify_lab_outbox',
            'changed'
        );
    END IF;

    RETURN NULL;
END;
$$;

CREATE TRIGGER outbox_notify_insert
AFTER INSERT ON notify_lab.outbox
REFERENCING NEW TABLE AS inserted_rows
FOR EACH STATEMENT
EXECUTE FUNCTION notify_lab.notify_outbox_change();
~~~

When a statement inserts outbox rows:

1. Transition table `inserted_rows` holds the rows inserted by that statement.
2. If non-empty, the trigger calls `pg_notify`.
3. `NOTIFY` participates in the active transaction.
4. Listeners see it only if the transaction commits.

### 30.1. Why Statement-Level Instead of Row-Level?

If a statement inserts 1,000 outbox rows, one wake-up hint is enough. Statement-level triggers avoid firing the trigger function once per row.

### 30.2. Why Payload `'changed'`?

Workers do not need event IDs from the notification. They only need to know **it is time to query the outbox**. That stays invariant regardless of coalescing or batch counts.

## 31. Two-Session Lab: Receiving the Hint After `COMMIT`

**Session A:**

~~~sql
LISTEN notify_lab_outbox;
~~~

**Session B:**

~~~sql
BEGIN;

CALL notify_lab.create_task('Import invoice A');

-- Session A has not received the hint from this transaction yet.
COMMIT;
~~~

After commit, Session A receives:

~~~text
channel = notify_lab_outbox
payload = changed
~~~

Session A then queries durable data:

~~~sql
SELECT
    event_id,
    task_id,
    event_type,
    event_data,
    published_at
FROM notify_lab.outbox
WHERE published_at IS NULL
ORDER BY event_id;
~~~

Those durable rows represent the real work to process.

## 32. Lab: `ROLLBACK` Produces No Committed Event

**Session B:**

~~~sql
BEGIN;

CALL notify_lab.create_task(
    'Task should not exist'
);

ROLLBACK;
~~~

Neither a committed task/outbox row nor a committed notification is emitted for this call.

### 32.1. Identity Counters Can Still Leave Gaps

Even when `INSERT` rolls back, allocated identity/sequence values do not rewind. Gaps in `event_id`/`task_id` are normal and do not mean an event was committed or processed.

## 33. Lab: Coalescing Identical Payloads

~~~sql
BEGIN;

CALL notify_lab.create_task('Task B');
CALL notify_lab.create_task('Task C');

COMMIT;
~~~

Each outbox insert invokes `pg_notify('notify_lab_outbox', 'changed')`. Because both calls share identical channel and payload inside the same transaction, the listener may receive only **one** notification.

Yet the outbox holds **two** new rows. The worker queries the table and processes both rather than counting notifications.

## 34. Never Use Max `event_id` as an Absolute Commit Cursor

A concurrency example:

~~~text
T1 INSERTs outbox event_id = 501, not yet COMMITted
T2 INSERTs outbox event_id = 502, COMMITs first
Worker processes 502, saves last_id = 502
T1 COMMITs and event 501 becomes visible
~~~

If the worker only queries:

~~~sql
SELECT *
FROM notify_lab.outbox
WHERE event_id > 502;
~~~

event 501 is skipped forever.

**Never infer commit order from sequence values.** A safer worker queries unprocessed items (`published_at IS NULL`) or uses a claim/checkpoint mechanism built for concurrent transaction ordering.

## 35. Worker Reading Durable Events

Simple query:

~~~sql
SELECT
    event_id,
    task_id,
    event_type,
    event_data
FROM notify_lab.outbox
WHERE published_at IS NULL
ORDER BY event_id
LIMIT 100;
~~~

This clearly illustrates the work source. However, with **multiple concurrent workers**, a plain unlocked `SELECT` lets two workers grab the same row.

Add proper coordination:

- Atomic claiming.
- `FOR UPDATE SKIP LOCKED`.
- Status, leases, and retries.
- Idempotency keys.
- Timeouts and crash recovery policies.

## 36. Claiming Work with `FOR UPDATE SKIP LOCKED`

Atomic claim of up to 10 tasks:

~~~sql
WITH picked AS (
    SELECT task_id
    FROM notify_lab.tasks
    WHERE status = 'pending'
    ORDER BY task_id
    FOR UPDATE SKIP LOCKED
    LIMIT 10
)
UPDATE notify_lab.tasks AS t
SET status = 'processing',
    updated_at = statement_timestamp()
FROM picked AS p
WHERE t.task_id = p.task_id
RETURNING
    t.task_id,
    t.title,
    t.status;
~~~

This allows multiple workers to claim disjoint rows cleanly under row locking.

### 36.1. `SKIP LOCKED` Does Not Guarantee Exactly-Once Execution

If a worker crashes right after claiming, tasks can get stranded in `processing`. Real systems add leases, expiry timeouts, requeuing, and idempotent processing.

### 36.2. Never Hold Locks Across Slow External HTTP Calls

Keep the claim transaction short, commit durable state, and handle external processing separately. Holding DB transactions open across network waits creates lock contention and connection starvation.

## 37. Transactional Outbox Alone Does Not Guarantee Exactly-Once Publication

Typical relay loop:

~~~text
1. Query unpublished outbox events
2. Publish event to external broker/HTTP endpoint
3. Mark published_at
~~~

If the worker crashes **after Step 2 and before Step 3**, the event gets published again on recovery.

Thus outboxes typically deliver **at-least-once semantics**, requiring downstream idempotency keyed by `event_id` or business key.

### 37.1. One `published_at` Cannot ACK Multiple Subscribers

If multiple independent consumers read the same event, each needs per-consumer state or broker offsets. A single shared timestamp does not verify every consumer succeeded.

## 38. How Does Java/pgJDBC Expose Notifications?

PostgreSQL JDBC driver interfaces:

- `org.postgresql.PGConnection`.
- `org.postgresql.PGNotification`.

Unwrap the standard JDBC connection:

~~~java
import org.postgresql.PGConnection;

PGConnection pg =
    connection.unwrap(PGConnection.class);
~~~

`PGConnection` exposes `getNotifications()` and, in modern driver versions, `getNotifications(timeoutMillis)`.

Standard `java.sql.Connection` has no built-in durable consumer/ACK API like a message broker.

## 39. Dedicated Java Listener

Example using a pgJDBC-backed `DataSource`:

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;

import javax.sql.DataSource;

import org.postgresql.PGConnection;
import org.postgresql.PGNotification;

public final class OutboxNotificationListener {

    private final DataSource listenerDataSource;

    public OutboxNotificationListener(
            DataSource listenerDataSource) {
        this.listenerDataSource = listenerDataSource;
    }

    public void runUntilInterrupted()
            throws SQLException {

        try (Connection connection =
                 listenerDataSource.getConnection()) {

            // Dedicate this connection exclusively to listening.
            connection.setAutoCommit(true);

            try (Statement statement =
                     connection.createStatement()) {
                statement.execute(
                    "LISTEN notify_lab_outbox"
                );
            }

            PGConnection pg =
                connection.unwrap(PGConnection.class);

            // Once LISTEN is active,
            // read durable tasks/events first.
            reconcileOutbox();

            while (!Thread.currentThread().isInterrupted()) {

                PGNotification[] notifications =
                    pg.getNotifications(5000);

                if (notifications != null) {
                    for (PGNotification n : notifications) {

                        if ("notify_lab_outbox".equals(
                                n.getName())) {
                            System.out.printf(
                                "channel=%s pid=%d payload=%s%n",
                                n.getName(),
                                n.getPID(),
                                n.getParameter()
                            );
                        }
                    }
                }

                // Fallback poll even when no notification arrives.
                reconcileOutbox();
            }
        }
    }

    private void reconcileOutbox() {
        // TODO: query durable outbox using working connections;
        // claim/lock jobs, process idempotently, persist status.
        // Do not pretend this example ensures exactly-once delivery.
    }
}
~~~

This code illustrates the listener lifecycle rather than a complete production worker. Wire `reconcileOutbox` to real transactional claiming and retry logic.

### 39.1. Why Pass a Timeout to `getNotifications`?

So the worker does not block indefinitely, stays responsive to shutdown interrupts, and runs periodic fallback reconciliation.

### 39.2. What If the Connection Fails?

Catch `SQLException` in an outer supervisor loop, close the connection, back off, open a fresh connection, re-issue `LISTEN`, and reconcile. Never assume a dropped session stayed subscribed.

### 39.3. Never Share One Connection Across Threads

Sharing a single JDBC connection simultaneously between the listener thread and worker queries causes protocol and transaction races. Use separate connections for listening and working transactions.

## 40. Sending Notifications from Java with `PreparedStatement`

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class NotifyPublisher {

    public void send(
            Connection connection,
            String channel,
            String payload) throws SQLException {

        try (PreparedStatement ps =
                 connection.prepareStatement(
                     "SELECT pg_notify(?, ?)"
                 )) {
            ps.setString(1, channel);
            ps.setString(2, payload);
            ps.execute();
        }
    }
}
~~~

Parameter binding prevents SQL injection from channel/payload strings. It **does not** validate business authorization.

### 40.1. Timing When `autoCommit=false`

If the connection is inside a transaction, `pg_notify` delivers only after `COMMIT`. Never open a side autocommit connection just to send the wake-up hint before the data transaction commits.

## 41. Java Services and Transaction Ownership

An application service flow:

~~~text
BEGIN
  INSERT task
  INSERT outbox
  Trigger pg_notify('notify_lab_outbox','changed')
COMMIT
      |
      v
Listener receives hint
      |
      v
Worker reads outbox
~~~

With Spring `@Transactional`, let the transaction manager commit. Because `notify_lab.create_task` does not commit internally, it participates cleanly inside a transactional service.

Never flip `autoCommit` or call `connection.commit()` directly on a connection managed by Spring or an ORM without explicit ownership.

## 42. Reconnect and Backoff Loop

A sound operational loop:

~~~text
while service is running:
    try:
        open dedicated DB connection
        set autocommit=true
        LISTEN channel
        reconcile durable rows
        while connected:
            getNotifications(timeout)
            reconcile durable rows
    catch connection error:
        close connection
        wait with bounded exponential backoff + jitter
        reconnect and re-LISTEN
~~~

Backoff with jitter prevents hundreds of app instances from stampeding PostgreSQL right after an outage.

**Always reconcile after reconnecting**, because notifications emitted while offline are never replayed.

## 43. `LISTEN` with Spring `@Transactional`

Write transaction:

~~~text
@Transactional createTask()
    |
    +--> INSERT tasks
    +--> INSERT outbox
    +--> trigger NOTIFY
    +--> COMMIT
            |
            v
          Listener
~~~

This works cleanly.

However, never mark a listener loop as `@Transactional` holding a transaction open for the entire wait:

~~~text
@Transactional listenForever()
  -> LISTEN
  -> wait for notifications
  -> transaction never COMMITs
~~~

That prevents `LISTEN` from activating properly and delays notification delivery. Listeners should manage dedicated non-transactional connections directly.

## 44. `LISTEN`/`NOTIFY` and Cache Invalidation

A common pattern:

~~~text
API instance A: UPDATE product.price + COMMIT
                   |
                   v
            NOTIFY products_changed
                   |
            +------+------+ 
            |             |
       Instance B     Instance C
            |             |
       Invalidate      Invalidate
         cache           cache
~~~

If Instance C is offline during `NOTIFY`, it misses the invalidation. Give caches TTLs or periodic refresh/reconciliation.

### 44.1. Eventual Consistency Must Be Accepted Explicitly

`LISTEN`/`NOTIFY` does not guarantee every node's local cache invalidates synchronously. Whenever strict consistency is mandatory, use a stronger consistency model or route reads to the authoritative source.

## 45. Should You Create One Channel per Task ID?

Do not create millions of per-ID channels:

~~~text
LISTEN task_1001
LISTEN task_1002
LISTEN task_1003
...
~~~

Channel names should represent **event categories**:

~~~text
LISTEN tasks_changed
LISTEN orders_changed
LISTEN cache_invalidated
~~~

and rely on durable tables or tiny IDs in payloads when pointing to specific entities.

## 46. Per-Row `NOTIFY` Inside a Trigger: An Anti-Pattern

Example:

~~~sql
CREATE FUNCTION notify_lab.notify_each_task()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM pg_notify(
        'tasks_changed',
        NEW.task_id::TEXT
    );

    RETURN NEW;
END;
$$;
~~~

Attached `AFTER INSERT FOR EACH ROW` during a one-million-row insert, this fires one million distinct payloads, ballooning queue usage and DML overhead.

If the goal is merely “new tasks arrived,” a **statement-level hint** trigger on the outbox is usually far better.

### 46.1. Coalescing Does Not Rescue Distinct Payloads

Whenever payloads differ, PostgreSQL does not coalesce them. Never count on coalescing to salvage high-volume per-row notifications.

## 47. Bulk Imports and Load Limits

Given:

~~~sql
INSERT INTO notify_lab.tasks(title)
SELECT
    'Task ' || g::TEXT
FROM generate_series(1, 100000) AS g;
~~~

one statement produces massive row volume.

Per-row triggers flood the notification queue; a single statement-level hint keeps notification traffic negligible while workers scan and claim durable rows in batches.

**Never run large bulk-insert tests on a shared production database.** Benchmark in bounded lab environments.

## 48. No Channel-Level Security

Another role can execute:

~~~sql
NOTIFY tasks_changed, 'run_admin_job';
~~~

as long as it holds normal database connection and SQL execution privileges.

Workers **must never trust a payload string as an authorized command**. Instead:

~~~text
NOTIFY changed
      |
      v
Query durable table
      |
      v
Validate authorization, status, version
      |
      v
Claim work atomically
      |
      v
Execute intended operation
~~~

Treat notifications strictly as hints, never as signed requests or privileged commands.

## 49. `NOTIFY` Does Not Replace Logical Replication / CDC

| Criterion | `LISTEN`/`NOTIFY` | Logical Decoding / CDC |
|---|---|---|
| Goal | Fast session-to-session signals | Stream committed changes from WAL |
| Replay after offline consumer | Not built-in | Supported via offsets/slots by design |
| Payload | Small text | Protocol/plugin change records |
| Per-consumer ACK | No | Framework-managed stream checkpoints |
| Operational complexity | Relatively low | Higher; manage WAL, slots, lag |
| Good for wake-up hints | Yes | Works, usually heavier |
| Good for long-term CDC | Insufficient alone | Appropriate when properly configured |

CDC also does not automatically guarantee end-to-end exactly-once semantics; idempotency and failover procedures remain necessary.

## 50. Comparison with Message Brokers

Brokers such as Kafka, RabbitMQ, or dedicated queue services offer capabilities absent from `LISTEN`/`NOTIFY`, depending on product and configuration:

- Durable messages.
- Per-consumer offsets and ACKs.
- Retries and dead-letter queues.
- Consumer groups.
- Backpressure and retention policies.
- Event replay.
- Cross-service and cross-region fan-out.

In exchange, you pay extra infrastructure, monitoring, and operational cost.

### 50.1. Choose by Requirements, Not Hype

If you only need to wake a worker to query PostgreSQL, `LISTEN`/`NOTIFY` + an outbox is often far simpler than operating a broker.

If you need millions of distributed events, independent replay, and consumer groups, a message broker or CDC pipeline makes sense.

## 51. Two-Phase Commit and `NOTIFY`

PostgreSQL enforces a restriction: a transaction that issued `NOTIFY` **cannot be prepared** with `PREPARE TRANSACTION` for two-phase commit. `LISTEN`/`UNLISTEN` also carry restrictions around prepared transactions.

If your application uses XA/2PC, never assume `NOTIFY` can be embedded into every prepared transaction. Verify requirements and place notifications outside incompatible boundaries.

## 52. Failover and Lifecycles

During a primary restart or failover:

- Existing sessions drop.
- `LISTEN` subscriptions do not transfer automatically to new connections.
- Notifications emitted while disconnected have no per-client backlog for replay.
- Committed outbox rows remain recoverable according to your replication and durability architecture.

Listeners recovering from failover must reconnect, re-issue `LISTEN`, and rescan durable work.

## 53. Read Replicas and Replication Lag

If a listener receives `NOTIFY` from the primary and immediately runs `SELECT` on a read replica, the replica may **not yet have applied the committed change** due to replication lag.

Verify carefully:

- Which database/primary is the listener connected to?
- Does the worker query the primary or a replica?
- Does the workflow require read-after-write consistency?
- Must it wait for replica catch-up via LSN/lag checks?
- What delay is acceptable?

Never treat `NOTIFY` as a synchronization barrier proving replicas caught up.

## 54. Metrics and Observability

Useful metrics:

- `pg_notification_queue_usage()`.
- Listener count and connection error rates.
- Notifications received/sec.
- Empty wake-ups (woken with 0 rows ready).
- Commit-to-worker processing latency.
- Unpublished outbox row count.
- Age of oldest unpublished event.
- Retry counts and duplicate handling counts.
- Job claim/completion rates.
- Lock waits and deadlocks.
- Reconnect frequency and recovery duration.

### 54.1. Inspecting `pg_stat_activity`

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

A listener session stuck `idle in transaction` demands immediate attention. Never expose raw query text or sensitive session info on unauthenticated dashboards.

## 55. Common Mistakes

### 55.1. Calling `LISTEN` After Querying Pending Rows

Creates a race window missing notifications emitted between `SELECT` and `LISTEN`.

### 55.2. Calling `LISTEN` Without Committing

The subscription may not take effect yet.

### 55.3. Holding a Long Listener Transaction

Delays notification delivery and stalls queue cleanup.

### 55.4. Returning a Listener Connection to the Pool

Session lifecycle no longer belongs to the listener.

### 55.5. Forgetting to Re-Subscribe After Reconnect

New sessions do not preserve old channel subscriptions.

### 55.6. Skipping Reconciliation After an Outage

Events committed during downtime go unnoticed.

### 55.7. Counting Notifications as Business Events

Coalescing invalidates 1-to-1 counting.

### 55.8. Assuming the Payload Limit Is 8,000 Unicode Characters

The limit is measured in bytes, not Java `String.length()`.

### 55.9. Putting Tokens or PII in Payloads

Channels are not authorization boundaries.

### 55.10. Trusting Payloads to Trigger Privileged Actions

Another role may emit `NOTIFY` on the same channel.

### 55.11. Having Every Listener Process the Same Task

`LISTEN`/`NOTIFY` lacks consumer groups; enforce atomic claiming and idempotency.

### 55.12. Relying on Sequence IDs for Commit Ordering

Concurrent transactions can commit out of ID allocation order.

### 55.13. Using `NOTIFY` as Durable Event Storage

Offline clients permanently lose notifications.

### 55.14. Failing to Monitor the Notification Queue

A full queue can break commits on `NOTIFY`-emitting transactions.

### 55.15. Testing Only in a Single Session

Integration tests must cover at least two sessions, commit/rollback, and reconnect recovery.

### 55.16. Emitting Unique Per-Row Notifications During Bulk Imports

Triggers notification storms.

### 55.17. Querying a Replica Immediately After `NOTIFY` Expecting Data

Exposes replication lag races.

### 55.18. Neglecting Shutdown Behavior

Listeners may hang connections and threads during app shutdown.

### 55.19. Omitting Backoff After Connection Errors

Synchronized reconnect storms overload recovering databases.

### 55.20. Confusing `pg_notification_queue_usage` with Pending Event Count

It reports queue fullness fraction, not business backlog size.

## 56. `LISTEN`/`NOTIFY` Implementation Checklist

**Semantics**

1. Is the notification strictly a hint, or are events never allowed to be lost?
2. When clients go offline, is there a durable table to rescan?
3. Does the domain require strict ordering?
4. Is duplicate processing tolerated?
5. Are idempotency/event IDs defined?

**SQL and Transactions**

6. Does `LISTEN` commit before initial reconciliation?
7. Does `NOTIFY` participate in the transaction requiring atomicity?
8. Are payloads tiny and free of sensitive data?
9. Do bulk writes avoid massive per-row notifications?
10. Are listeners free of long transactions?
11. Is queue usage monitored?
12. Are 2PC/XA incompatibilities checked if used?

**Application Connections**

13. Does the listener own a dedicated connection?
14. Does reconnect re-issue `LISTEN`?
15. Are backoff and jitter applied on DB failures?
16. Does startup/reconnect run reconciliation?
17. Is periodic fallback polling enabled?
18. Are null/empty notification arrays handled safely?
19. Is graceful shutdown implemented?
20. Was it tested against your exact pgJDBC version?

**Durability**

21. Are business events stored in an outbox table?
22. Do multiple workers use atomic claiming?
23. Do crashed workers recover via leases/retries?
24. Is duplicate delivery handled safely?
25. Are event backlog metrics and alerts in place?

## 57. Practice Exercises

### Exercise 1 — `LISTEN`

Write SQL to subscribe to channel `orders_changed`.

**Hint:** `LISTEN orders_changed;`.

### Exercise 2 — `NOTIFY`

Send payload `changed` on channel `orders_changed`.

**Hint:** `NOTIFY orders_changed, 'changed';`.

### Exercise 3 — `pg_notify`

Send a notification with channel and payload computed dynamically at runtime.

**Hint:** `SELECT pg_notify(channel_text, payload_text);`.

### Exercise 4 — Same Database

Does a session in database B receive `NOTIFY` emitted in database A of the same cluster?

**Hint:** no.

### Exercise 5 — Registration

When does a `LISTEN` executed inside a transaction take effect?

**Hint:** at `COMMIT`.

### Exercise 6 — Rollback

Is a `NOTIFY` inside a rolled-back transaction delivered?

**Hint:** no.

### Exercise 7 — Listener Transaction

How does a listener holding a long open transaction affect delivery?

**Hint:** notifications may be delayed.

### Exercise 8 — Startup Race

Why can running `SELECT` before `LISTEN` miss new tasks?

**Hint:** a `NOTIFY` can fire between the two steps.

### Exercise 9 — Startup Sequence

State the safer ordering of `LISTEN`, `COMMIT`, and reconciliation.

**Hint:** `LISTEN` (and commit), then reconcile.

### Exercise 10 — Coalescing

You send three identical channel/payload notifications in one transaction; are you guaranteed to receive three?

**Hint:** no, possibly only one.

### Exercise 11 — Different Payloads

Are distinct payloads on the same channel coalesced by the identical channel/payload rule?

**Hint:** not under the identical channel/payload rule.

### Exercise 12 — Two Transactions

Do two separate transactions sending identical payloads coalesce into one as inside a single transaction?

**Hint:** no.

### Exercise 13 — Business Event Count

Can you infer the number of inserted rows from notification count?

**Hint:** no.

### Exercise 14 — UTF-8 Bytes

Why do `length` and `octet_length` differ?

**Hint:** character count vs. byte length.

### Exercise 15 — Payload Limit

Should you send huge full JSON records inside `NOTIFY`?

**Hint:** no—byte limit and non-durable.

### Exercise 16 — Queue Usage

Write a query to inspect queue occupancy.

**Hint:** `pg_notification_queue_usage()`.

### Exercise 17 — Full Queue

How can a full queue impact commits?

**Hint:** transactions calling `NOTIFY` can fail to commit.

### Exercise 18 — Channels

Which function lists channels the current session is listening on?

**Hint:** `pg_listening_channels()`.

### Exercise 19 — `UNLISTEN`

How do you unsubscribe from all channels in the current session?

**Hint:** `UNLISTEN *;`.

### Exercise 20 — PID

Is the PID in `PGNotification` a durable event ID?

**Hint:** no.

### Exercise 21 — Offline

Do reconnecting workers receive notifications sent while they were offline?

**Hint:** no.

### Exercise 22 — Outbox

Why store the outbox insert inside the same transaction as the task?

**Hint:** atomicity.

### Exercise 23 — Hint

Why can a trigger simply emit payload `'changed'` instead of full `event_data`?

**Hint:** workers query the durable outbox table.

### Exercise 24 — Statement-Level

Why do statement-level triggers suit bulk inserts needing only a wake-up signal?

**Hint:** cuts notification volume dramatically.

### Exercise 25 — Worker Claiming

Can two workers both running `SELECT` on a pending row double-process it?

**Hint:** yes; use atomic claiming.

### Exercise 26 — `SKIP LOCKED`

How does `SKIP LOCKED` help multiple workers?

**Hint:** skips locked rows while claiming batches.

### Exercise 27 — Exactly-Once

Does `LISTEN`/`NOTIFY` provide per-consumer ACKs or offsets?

**Hint:** no.

### Exercise 28 — Reconnect

What steps are needed after reconnecting?

**Hint:** re-`LISTEN`, commit, and reconcile.

### Exercise 29 — Java API

Which pgJDBC interfaces handle notifications?

**Hint:** `PGConnection` and `PGNotification`.

### Exercise 30 — `PreparedStatement`

With what SQL do you bind channel and payload parameters?

**Hint:** `SELECT pg_notify(?, ?)`.

### Exercise 31 — Dedicated Connection

Why shouldn't a listener connection be returned to an HTTP request pool?

**Hint:** session and transaction lifecycle isolation.

### Exercise 32 — Security

Can you treat a channel name as a secret ACL?

**Hint:** no.

### Exercise 33 — Spoofed Notification

Should a worker execute a payload directly as a command?

**Hint:** no; verify state in the database.

### Exercise 34 — Multiple Listeners

Does one `NOTIFY` automatically partition distinct tasks across listening workers?

**Hint:** no, it fans out to all subscribers.

### Exercise 35 — Replication Lag

Why might reading a replica right after a primary `NOTIFY` miss the new data?

**Hint:** replication lag.

### Exercise 36 — 2PC

Can a transaction that ran `NOTIFY` always execute `PREPARE TRANSACTION`?

**Hint:** no.

### Exercise 37 — Sequence Order

Why can storing the highest `last_event_id` skip older events?

**Hint:** ID allocation order differs from commit order.

### Exercise 38 — Monitoring

Name three important metrics when running a listener/outbox pipeline.

**Hint:** queue usage, oldest unpublished event age, reconnect count, processing latency.

### Exercise 39 — Cache

Why should `NOTIFY`-driven cache invalidation still configure a TTL?

**Hint:** offline listeners miss signals.

### Exercise 40 — Broker

When should you pick a broker or CDC instead of `LISTEN`/`NOTIFY` alone?

**Hint:** durability, replay, per-consumer ACKs, and consumer groups.

## 58. Frequently Asked Questions

### Does `LISTEN` automatically deliver notifications emitted before registration?

No. Subscriptions are session-scoped from registration onward; query durable tables to catch up on prior state.

### Is `NOTIFY` delivered immediately when the SQL runs, or at `COMMIT`?

Only after the transaction successfully commits. `ROLLBACK` discards uncommitted notifications.

### Can notifications arrive while a listener session sits inside a long transaction?

Delivery may wait until the listener's transaction ends. Keep listener connections out of long transactions while waiting.

### Is the max payload 8,000 characters?

No. The typical limit is shorter than roughly 8,000 **bytes**, not character count.

### If I emit multiple identical `NOTIFY` calls, do I always receive that exact count?

No. Notifications sharing channel and payload within the same transaction may be coalesced.

### Can I `LISTEN` to a channel in another database?

Not directly. `LISTEN`/`NOTIFY` is scoped to a single database.

### Does `LISTEN` survive reconnects?

No. Re-subscribe on the new connection.

### Is there an ACK after a worker finishes handling a message?

`LISTEN`/`NOTIFY` has no built-in per-consumer ACK. Use status tables or a message broker when needed.

### Does `NOTIFY` replace a message broker?

Not for durable replay, consumer groups, per-consumer retries/ACKs, or high-volume fan-out requirements.

### Why keep polling if I already use `LISTEN`?

To catch durable tasks/events whose signals were missed during downtime, failover, or startup races.

### Should I put emails or tokens inside payloads?

No. Channels lack per-topic ACLs and payloads are never a secret vault.

### Does `pg_notification_queue_usage` tell me how many jobs are waiting?

No. It reports the fraction of the PostgreSQL notification queue currently occupied.

### Can triggers send `NOTIFY` inside the same transaction?

Yes. Call `PERFORM pg_notify(...)` inside the trigger function; delivery occurs only at commit.

### Can pgJDBC receive notifications?

Yes, via `PGConnection`/`PGNotification`. Use a dedicated connection, a wait loop, and reconnect/reconcile logic.

### Do multiple listening workers split tasks automatically?

No. Every subscriber receives the hint; workers must claim tasks atomically.

### If a producer fires `NOTIFY` and the listener crashes right after receiving it, is the job lost?

Notifications have no business ACK. If the event lived only in `NOTIFY`, it is lost. If stored in an outbox table, restarted workers can still find and process it.

## 59. Summary

Core commands:

~~~sql
-- Subscribe to notifications.
LISTEN app_events;

-- Emit a notification.
NOTIFY app_events, 'changed';

-- Emit via function.
SELECT pg_notify('app_events', 'changed');

-- Channels the current session listens to.
SELECT * FROM pg_listening_channels();

-- Unsubscribe from one or all channels.
UNLISTEN app_events;
UNLISTEN *;

-- Inspect notification queue fullness.
SELECT pg_notification_queue_usage();

-- Backend PID of the current session.
SELECT pg_backend_pid();
~~~

Key principles:

1. **`LISTEN` belongs to a session** and does not survive reconnects.
2. **`NOTIFY` is delivered upon `COMMIT`**; rollback cancels uncommitted notifications.
3. **Listeners inside long transactions experience delayed delivery**.
4. **`LISTEN` takes effect at `COMMIT`**; subscribe before initial reconciliation to avoid startup races.
5. **Identical channel/payload notifications within one transaction coalesce**; never count notifications to count business events.
6. **Payloads are byte-limited**, so send tiny hints or IDs only.
7. **The notification queue is finite**; monitor `pg_notification_queue_usage()`.
8. **`LISTEN`/`NOTIFY` is scoped to one database**, not cross-cluster pub/sub.
9. **There is no replay, per-consumer ACK, or consumer group**.
10. **There is no channel-level `GRANT` ACL**; never transmit sensitive data.
11. **Dedicated connections, autocommit, and reconnect/re-`LISTEN`** are the standard safe pattern.
12. **Periodic reconciliation** provides a safety net against lost signals.
13. **Transactional outboxes** persist events durably; `NOTIFY` merely wakes workers.
14. **Multiple workers require atomic claiming, leases, and idempotency** to avoid duplicate work.
15. **pgJDBC exposes `PGConnection`/`PGNotification`**, not a durable broker API.
16. **Bulk DML should avoid row-level notification storms** in favor of statement-level hints.
17. **Failover and replica lag** must be factored into architecture.
18. **Picking the right primitive** beats forcing one feature everywhere: `NOTIFY` for wake-up hints, outboxes for durability, brokers/CDC for distribution and replay when required.

Final architecture overview:

~~~text
Business transaction
        |
        +--> INSERT/UPDATE task
        |
        +--> INSERT durable outbox event
        |
        +--> Trigger pg_notify('notify_lab_outbox','changed')
        |
        v
      COMMIT
        |
        +--> Durable outbox row
        |
        +--> NOTIFY hint (may be lost if listener is offline)
                    |
                    v
            Dedicated listener
                    |
                    +--> Re-LISTEN on every reconnect
                    +--> Reconcile on startup
                    +--> Reconcile on notification
                    +--> Periodic fallback poll
                    |
                    v
              Claim durable events
                    |
                    v
              Idempotent processing
                    |
                    v
            Commit processing state
~~~

**Conclusion:** `LISTEN` and `NOTIFY` are simple, effective primitives for **signaling state changes in PostgreSQL quickly**. However, they are not a durable event log. Whenever work must never be dropped, combine notifications as a **wake-up signal** with durable state/outbox tables, retries, idempotency, and reconciliation.
