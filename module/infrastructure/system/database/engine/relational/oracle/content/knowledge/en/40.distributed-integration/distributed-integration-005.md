# Advanced Queuing: Queue Tables, Enqueue, Dequeue, and Transactionality

Oracle Advanced Queuing (AQ) is the built-in messaging mechanism in Oracle Database. An application can send a message to a queue, allowing another process to receive and process the message later. Because messages are stored and managed inside the database, AQ can coordinate sending/receiving messages with the application's SQL transactions.

AQ is commonly used to decouple processing steps within a system: a transactional application records an order and emits an event; a worker receives the event to send notifications, update downstream systems, or perform background work. Producers and consumers do not need to run at the same time yet can still coordinate through messages stored in the queue.

Core concepts:

- **Queue table**: internal storage table holding messages and metadata managed by AQ.
- **Queue**: logical message stream created on a queue table, with enqueue/dequeue settings and processing policies.
- **Enqueue**: operation that puts a message into a queue.
- **Dequeue**: operation that reads, locks, or retrieves a message from a queue.
- **Payload**: the business content of a message, which can be an object type, `RAW`, or another AQ-supported type.
- **Transaction visibility**: determines whether an enqueue/dequeue operation participates in the current transaction or runs independently.

The most critical design point in AQ is ensuring that messages and business data changes share the same transaction boundary when atomicity is required. If updating an order and enqueuing an event commit together, the system avoids the scenario where an order commits while the notification message is lost.

## 1. Architecture and Message Lifecycle

A queue table can store messages for one or more queues. The queue defines how applications interact with messages, while the queue table is where AQ stores payloads and metadata needed to track state.

A basic processing flow:

1. The producer constructs a payload containing event information.
2. The producer calls **DBMS_AQ.ENQUEUE** to place the message into the queue.
3. The producer's transaction commits; the message becomes available to consumers if enqueue uses `ON_COMMIT` mode.
4. The consumer calls **DBMS_AQ.DEQUEUE** to retrieve the message.
5. The consumer processes the payload and updates business data.
6. The consumer commits; the message is confirmed processed and removed from the ready-message set.
7. If the consumer rolls back, the dequeue operation is undone and the message can be processed again.

Diagram:

~~~text
        Producer Application
               |
        Build payload/message
               |
               v
       DBMS_AQ.ENQUEUE
               |
       Transaction COMMIT
               |
               v
       +------------------+
       |      Queue       |
       |   Queue table    |
       +------------------+
               |
       DBMS_AQ.DEQUEUE
               |
               v
        Consumer Application
               |
        Business processing
               |
         COMMIT / ROLLBACK
               |
       +-------+--------+
       |                |
     COMMIT           ROLLBACK
       |                |
       v                v
 Message is        Message returns to
 confirmed         a state eligible for
 processed         reprocessing
~~~

AQ stores and manages messages inside the database. Applications should not manipulate internal queue tables directly with `INSERT`, `UPDATE`, or `DELETE`. Use `DBMS_AQ` and `DBMS_AQADM` to create queues, enqueue, dequeue, manage subscribers, and administer queues.

## 2. Queue Tables and Queues

### Queue Table

A queue table is the storage structure created via **DBMS_AQADM.CREATE_QUEUE_TABLE**. When creating a queue table, the DBA declares the payload type and whether the queue table supports multiple consumers.

The payload can be:

- **ADT (Abstract Data Type)**: an application-defined SQL object type. This is convenient when messages have a clear structure with multiple fields.
- **RAW**: binary data whose encoding/decoding is defined by the application.
- **ANYDATA** or other supported payload types: used when representing multiple data types or integrating via corresponding APIs.

With ADT payloads, both producer and consumer must use compatible object types. When modifying type definitions, evaluate the impact on applications actively enqueuing/dequeuing and on existing messages in the queue.

### Queue

A queue is created via **DBMS_AQADM.CREATE_QUEUE** on an existing queue table. A queue can have enqueue and dequeue enabled/disabled independently via **START_QUEUE** and **STOP_QUEUE**.

A queue can be configured with attributes such as:

- Retry count when a consumer rolls back or message processing fails.
- Wait interval before the next retry.
- Message retention time after dequeue.
- Exception queue receiving expired messages or messages exceeding retry limits.
- Distribution rules and subscribers in multi-consumer models.

Queue table and queue are not the same concept. A queue table is the storage backing; a queue is the logical object used by producers/consumers.

### Single-Consumer and Multi-Consumer Queues

A **single-consumer queue** fits when each message only needs to be received and processed by one consumer. Multiple consumer processes can compete to pull messages, but each message is successfully dequeued by only one consumer via AQ's locking mechanism.

A **multi-consumer queue** fits when a single message must be distributed to multiple subscribers. For example, a payment event may need delivery to accounting, warehouse, and notification services. Each subscriber maintains its own delivery state.

| Characteristic | Single-Consumer | Multi-Consumer |
|---|---|---|
| Purpose | One message processed by one consumer | One message can be received by multiple subscribers |
| Queue table | Created with `multiple_consumers = FALSE` | Created with `multiple_consumers = TRUE` |
| Consumer identity | No `consumer_name` needed for simple models | Dequeue typically specifies `consumer_name` |
| Delivery | Multiple workers compete for messages | Each subscriber gets its own logical delivery |
| Example | Order processing queue | Event broadcast queue for multiple systems |

Choosing single vs. multi-consumer is decided when creating the queue table. Determine the distribution model before creating the queue table, as this should not be treated as something you can arbitrarily change once messages exist in the system.

## 3. Preparing Privileges and Payload Types

For illustration, assume the application has schema `APP` and needs an order event queue. The payload includes order ID, event type, timestamp, and description.

Create a SQL object type:

~~~sql
CREATE TYPE app.order_event_t AS OBJECT (
  order_id   NUMBER,
  event_type VARCHAR2(30),
  event_time TIMESTAMP WITH TIME ZONE,
  detail     VARCHAR2(2000)
);
/
~~~

The administrative account needs privileges to create queue tables and queues, typically via appropriate AQ administration privileges. Producer/consumer accounts need privileges to use AQ packages, access the payload type, and enqueue/dequeue on the target queue.

After the queue is created, the DBA can grant queue privileges via **DBMS_AQADM.GRANT_QUEUE_PRIVILEGE**. Concrete examples are placed right after queue creation so the object already exists. If producer and consumer share the same schema, both privileges can be granted to that schema. Actual privileges depend on deployment setup and Oracle version; the DBA must ensure users have package execution, type access, and required queue privileges. Do not grant broad AQ admin privileges to application accounts that only need enqueue or dequeue.

## 4. Creating Queue Tables and Queues with DBMS_AQADM

Create a single-consumer queue table:

~~~sql
BEGIN
  DBMS_AQADM.CREATE_QUEUE_TABLE(
    queue_table        => 'APP.ORDER_QTAB',
    queue_payload_type => 'APP.ORDER_EVENT_T',
    multiple_consumers => FALSE
  );
END;
/
~~~

Create a queue on the queue table:

~~~sql
BEGIN
  DBMS_AQADM.CREATE_QUEUE(
    queue_name  => 'APP.ORDER_Q',
    queue_table => 'APP.ORDER_QTAB',
    max_retries => 5,
    retry_delay => 60
  );
END;
/
~~~

Enable enqueue and dequeue:

~~~sql
BEGIN
  DBMS_AQADM.START_QUEUE(
    queue_name => 'APP.ORDER_Q',
    enqueue    => TRUE,
    dequeue    => TRUE
  );
END;
/
~~~

Once started, the queue can accept and serve messages according to granted privileges. If enqueue or dequeue has not been enabled on the queue, the corresponding operation will fail even though the queue table and queue exist.

Grant privileges to producer and worker after the queue exists:

~~~sql
BEGIN
  DBMS_AQADM.GRANT_QUEUE_PRIVILEGE(
    privilege  => 'ENQUEUE',
    queue_name => 'APP.ORDER_Q',
    grantee    => 'APP_PRODUCER'
  );

  DBMS_AQADM.GRANT_QUEUE_PRIVILEGE(
    privilege  => 'DEQUEUE',
    queue_name => 'APP.ORDER_Q',
    grantee    => 'APP_WORKER'
  );
END;
/
~~~

### Configuring Retries and Exception Queues

When a consumer pulls a message and the transaction rolls back, AQ can retry delivering the message. Queues have retry count and retry delay attributes. Once retries are exhausted, the message can move to an exception queue per queue policy and state.

The example above sets `MAX_RETRIES` to 5 and `RETRY_DELAY` to 60 seconds at queue creation. If a queue already exists and its policy must be changed, use the queue alteration admin procedure appropriate for your version, then verify configuration via AQ views. Do not re-run `CREATE_QUEUE` on an existing queue.

An exception queue holds messages that can no longer be delivered normally under retry/expiration policies. Establish a process to monitor, investigate failed payloads, and decide whether to replay or discard messages. Never delete messages from an exception queue without identifying the root cause.

## 5. Enqueue: Putting Messages into a Queue

Producers use **DBMS_AQ.ENQUEUE**. Key parameters:

- **queue_name**: name of the target queue.
- **enqueue_options**: enqueue options, including transaction visibility and delivery behaviors.
- **message_properties**: metadata such as priority, delay, expiration, correlation, and recipient list.
- **payload**: message content matching the type declared for the queue table.
- **msgid**: message ID generated and returned by AQ.

Example enqueuing an order event:

~~~sql
DECLARE
  l_enqueue_options    DBMS_AQ.ENQUEUE_OPTIONS_T;
  l_message_properties DBMS_AQ.MESSAGE_PROPERTIES_T;
  l_payload            APP.ORDER_EVENT_T;
  l_msgid              RAW(16);
BEGIN
  l_enqueue_options.visibility := DBMS_AQ.ON_COMMIT;

  l_payload := APP.ORDER_EVENT_T(
    1001,
    'ORDER_PAID',
    SYSTIMESTAMP,
    'Payment completed'
  );

  DBMS_AQ.ENQUEUE(
    queue_name         => 'APP.ORDER_Q',
    enqueue_options    => l_enqueue_options,
    message_properties => l_message_properties,
    payload            => l_payload,
    msgid              => l_msgid
  );

  DBMS_OUTPUT.PUT_LINE('Message ID: ' || RAWTOHEX(l_msgid));

  COMMIT;
END;
/
~~~

The message is enqueued with `ON_COMMIT` visibility. Thus, it becomes available to consumers only after the transaction commits. If the transaction rolls back before commit, the enqueued message is also rolled back.

### Enqueuing in the Same Transaction as Business DML

An application often needs to update business data and emit a corresponding event in the same transaction.

~~~sql
DECLARE
  l_enqueue_options    DBMS_AQ.ENQUEUE_OPTIONS_T;
  l_message_properties DBMS_AQ.MESSAGE_PROPERTIES_T;
  l_payload            APP.ORDER_EVENT_T;
  l_msgid              RAW(16);
BEGIN
  UPDATE app.orders
  SET    status = 'PAID',
         paid_at = SYSTIMESTAMP
  WHERE  order_id = 1001;

  IF SQL%ROWCOUNT = 0 THEN
    RAISE_APPLICATION_ERROR(-20001, 'Order not found');
  END IF;

  l_enqueue_options.visibility := DBMS_AQ.ON_COMMIT;

  l_payload := APP.ORDER_EVENT_T(
    1001,
    'ORDER_PAID',
    SYSTIMESTAMP,
    'Order payment committed'
  );

  DBMS_AQ.ENQUEUE(
    queue_name         => 'APP.ORDER_Q',
    enqueue_options    => l_enqueue_options,
    message_properties => l_message_properties,
    payload            => l_payload,
    msgid              => l_msgid
  );

  COMMIT;
EXCEPTION
  WHEN OTHERS THEN
    ROLLBACK;
    RAISE;
END;
/
~~~

If the `UPDATE` succeeds but `ENQUEUE` fails, the exception handler rolls back the entire transaction. If `ENQUEUE` succeeds but commit fails, neither the order update nor the message is committed. This is a major advantage of AQ with `ON_COMMIT`: business data and messages share the exact same commit outcome in a single Oracle transaction.

Do not place `COMMIT` inside a shared enqueue helper procedure if callers need to control the transaction. Commit at the layer owning the transaction to avoid accidentally committing other changes made by the caller.

## 6. Message Properties and Processing Order

The payload holds business content. Message properties hold metadata controlling delivery and filtering.

Common properties:

| Property | Meaning |
|---|---|
| `PRIORITY` | Priority of the message |
| `DELAY` | Delay duration before the message becomes eligible for dequeue |
| `EXPIRATION` | Duration a message remains valid before expiring |
| `CORRELATION` | Application-defined value used to group or filter related messages |
| `EXCEPTION_QUEUE` | Queue receiving expired or undeliverable messages per policy |
| `RECIPIENT_LIST` | List of recipients in a multi-consumer queue |
| `SENDER_ID` | Sending agent details in supported models |

Message ordering depends on the queue table's sort order configuration. If the queue table is configured to sort by enqueue time, messages are generally processed chronologically. If sort order includes priority, AQ can prioritize messages by priority ahead of enqueue time. Therefore, never assume setting `PRIORITY` changes ordering unless the queue table was created with a matching sort order.

### Delay and Expiration

- `DELAY` lets a producer enqueue a message immediately while delaying when consumers can receive it.
- `EXPIRATION` specifies how long a message can stay in the queue before expiring.
- Expired messages can be moved to an exception queue per configuration.
- A delayed message is not yet ready for consumer processing.

Delay is useful for timed retries or scheduled processing. Expiration is useful for messages valid only within a window, such as temporary verification requests. Set durations appropriate to business logic and establish monitoring for expired messages.

### Correlation

Correlation is application-assigned metadata used to identify groups of related messages. For instance, messages for the same order can use the order ID as their correlation. Consumers can dequeue only messages matching a specific correlation.

Correlation is not a primary key of the queue and does not replace `msgid`. **MSGID** is generated by AQ to identify a message; **CORRELATION** is an application value used to locate or group messages.

## 7. Dequeue: Receiving and Processing Messages

Consumers use **DBMS_AQ.DEQUEUE** to receive messages. Key parameters:

- **queue_name**: source queue.
- **dequeue_options**: retrieval mode, wait time, navigation, consumer name, and filter conditions.
- **message_properties**: metadata of the received message.
- **payload**: returned message content.
- **msgid**: message identifier.

Example of a consumer retrieving and processing one message:

~~~sql
DECLARE
  l_dequeue_options    DBMS_AQ.DEQUEUE_OPTIONS_T;
  l_message_properties DBMS_AQ.MESSAGE_PROPERTIES_T;
  l_payload            APP.ORDER_EVENT_T;
  l_msgid              RAW(16);
BEGIN
  l_dequeue_options.wait         := DBMS_AQ.NO_WAIT;
  l_dequeue_options.navigation   := DBMS_AQ.FIRST_MESSAGE;
  l_dequeue_options.dequeue_mode := DBMS_AQ.REMOVE;
  l_dequeue_options.visibility   := DBMS_AQ.ON_COMMIT;

  DBMS_AQ.DEQUEUE(
    queue_name         => 'APP.ORDER_Q',
    dequeue_options    => l_dequeue_options,
    message_properties => l_message_properties,
    payload            => l_payload,
    msgid              => l_msgid
  );

  DBMS_OUTPUT.PUT_LINE(
    'Order=' || l_payload.order_id ||
    ', event=' || l_payload.event_type
  );

  -- Perform consumer business updates here.

  COMMIT;
EXCEPTION
  WHEN OTHERS THEN
    ROLLBACK;
    RAISE;
END;
/
~~~

With `NO_WAIT`, if no matching message is ready, dequeue can terminate with an AQ timeout/end-of-fetch error, commonly `ORA-25228`. In background workers, handle a temporarily empty queue as a normal state rather than logging every empty poll as a system error.

### Dequeue Modes

| Mode | Behavior |
|---|---|
| `REMOVE` | Retrieves the message and marks it removed from the queue; removal commits with the transaction |
| `BROWSE` | Reads the message without removing it from the queue |
| `LOCKED` | Locks the message for inspection/processing within the transaction without yet removing it |

`REMOVE` is the standard mode for message-processing consumers. `BROWSE` is useful for inspecting content without consuming the message. `LOCKED` can be used when a message needs to be locked within a transaction for inspection before deciding the next action.

With `REMOVE` and `ON_COMMIT`, the message is retrieved inside the current transaction. If the consumer rolls back, removal is undone and the message can be redelivered. If it commits, dequeue is confirmed.

### Wait and Navigation

The `WAIT` attribute controls how long a consumer waits for a message:

- **NO_WAIT**: does not wait if no matching message is currently available.
- **FOREVER**: waits until a message arrives or another termination condition occurs.
- A numeric value: waits for the specified number of seconds per the API.

The `NAVIGATION` attribute controls where to start/search for messages in the queue, such as `FIRST_MESSAGE` or `NEXT_MESSAGE`. When processing single messages, `FIRST_MESSAGE` is usually straightforward. When reading multiple consecutive messages in the same session, choose navigation suitable for consistency requirements and AQ's message positioning behavior.

### Filtering Messages on Dequeue

Dequeue can use criteria such as:

- **consumer_name** in a multi-consumer queue.
- **correlation** to fetch messages belonging to a target group.
- **msgid** when retrieving a specific message.
- **condition** to filter based on message properties or payload attributes using AQ-supported syntax.

Do not create complex filter conditions without testing syntax and performance on your Oracle version. If multiple consumers share a queue, clearly define which messages each consumer handles and what happens to unmatched messages.

## 8. Transactionality of ENQUEUE and DEQUEUE

Transaction visibility is the most important attribute when coordinating AQ with business DML.

Two common modes:

- **ON_COMMIT**: enqueue/dequeue operations participate in the session's current transaction.
- **IMMEDIATE**: operations execute in an independent transaction via AQ's autonomous mechanism.

### ON_COMMIT on Enqueue

When enqueuing with `ON_COMMIT`:

1. The message is created inside the current transaction.
2. Other sessions do not yet see the message as committed.
3. If the producer `COMMIT`s, the message becomes available.
4. If the producer `ROLLBACK`s, the message is discarded along with the transaction.

This guarantees the application can update business tables and enqueue a message in the same transaction.

Example:

~~~text
BEGIN TRANSACTION
    UPDATE ORDERS
    ENQUEUE ORDER_PAID
COMMIT
    -> ORDERS changes and message take effect together

If ROLLBACK
    -> UPDATE is undone
    -> Message also does not exist in queue
~~~

### ON_COMMIT on Dequeue

When dequeuing with `REMOVE` and `ON_COMMIT`:

1. The consumer retrieves and locks the message within the transaction.
2. The consumer performs business processing, such as inserting into an invoice table or updating status.
3. If `COMMIT`, both business changes and the dequeue operation are confirmed.
4. If `ROLLBACK`, business changes are undone and the message returns to deliverable state.

Example:

~~~text
BEGIN TRANSACTION
    DEQUEUE ORDER_PAID
    INSERT INVOICE
COMMIT
    -> Message is confirmed processed
    -> Invoice is recorded

If ROLLBACK
    -> Invoice is undone
    -> Message can be processed again
~~~

This mechanism prevents two dangerous situations:

- A message is removed from the queue while the consumer's business data was not committed.
- Business data is committed while the message is still considered unprocessed in the queue.

### IMMEDIATE and Independent Transactions

With `IMMEDIATE`, AQ executes the operation in an independent transaction. The enqueue/dequeue outcome can commit separately, regardless of whether the outer business transaction commits or rolls back.

Example where a producer updates an order yet enqueues with `IMMEDIATE`:

~~~text
BEGIN TRANSACTION
    UPDATE ORDERS
    ENQUEUE MESSAGE (IMMEDIATE COMMIT)
ROLLBACK
    -> UPDATE ORDERS is undone
    -> Message still exists in queue
~~~

This might be desired in certain designs, but it is usually unsuitable if the message describes a business change that has not yet committed reliably. Likewise, `IMMEDIATE` dequeue can confirm consuming a message independently; if downstream business processing later rolls back, the message may already have been removed in the independent transaction.

Therefore:

| Requirement | Typically Appropriate Visibility |
|---|---|
| Table updates and message emission must succeed/fail together | `ON_COMMIT` |
| Message consumption and consumer data updates must succeed/fail together | `ON_COMMIT` |
| Deliberately want AQ action independent of caller transaction | `IMMEDIATE`, after evaluating consequences |
| Must not lose messages when business processing fails | `DEQUEUE REMOVE` + `ON_COMMIT` |

`IMMEDIATE` is not a way to "commit faster" for a business transaction. It alters the atomicity boundary. Use it only when you have explicitly decided the message must persist or be removed independently of the outer transaction.

## 9. Retries, Rollback, and Error Handling

In asynchronous systems, consumers may hit transient errors such as deadlocks, connection failures, unavailable downstream services, or data not yet ready for processing. With `ON_COMMIT` dequeue, a consumer rollback undoes message removal. The message can be retried according to the queue's retry policy.

Operational properties to watch:

- **MAX_RETRIES**: number of times AQ redelivers a message after failed dequeues per queue mechanics.
- **RETRY_DELAY**: wait time before retrying.
- **EXPIRATION**: how long a message stays valid.
- **EXCEPTION_QUEUE**: destination for messages that can no longer be delivered normally due to retries/expiration or matching policy.

Retries help systems self-heal from transient errors. However, if a message always fails due to malformed payloads or invalid business data, endless retries only increase load. Configure retry limits, exception queues, and investigation procedures.

### Consumers Must Be Idempotent

Even though AQ manages messages transactionally, applications still need consumers designed to handle duplicate deliveries safely in scenarios involving external integrations, client errors, or retry workflows.

For example, an `ORDER_PAID` message may be redelivered if a consumer rolls back. The consumer should check whether an invoice was already created for that order, or use a business key/unique constraint to prevent duplicate recording.

Processing pattern:

~~~sql
BEGIN
  -- Dequeue message with ON_COMMIT and REMOVE.

  INSERT INTO app.processed_events(event_id, processed_at)
  VALUES (:event_id, SYSTIMESTAMP);

  -- Perform business updates in the same transaction.

  COMMIT;
EXCEPTION
  WHEN DUP_VAL_ON_INDEX THEN
    -- Event already processed previously; apply appropriate acknowledgment policy.
    ROLLBACK;
  WHEN OTHERS THEN
    ROLLBACK;
    RAISE;
END;
/
~~~

The example above illustrates deduplication; explicitly decide whether duplicate handling counts as success or requires logging and reconciliation. Never swallow all exceptions blindly, as that can hide business errors.

If a consumer calls external systems like email, HTTP APIs, or payment services, an Oracle transaction cannot roll back side effects already executed in external systems. Use idempotency keys, outbox/inbox tables, controlled retries, or confirmation mechanisms native to the external service.

## 10. Multi-Consumer Queues and Subscribers

When a message must be received independently by multiple components, create a queue table with `multiple_consumers = TRUE`.

Example creating an event queue table:

~~~sql
BEGIN
  DBMS_AQADM.CREATE_QUEUE_TABLE(
    queue_table        => 'APP.EVENT_QTAB',
    queue_payload_type => 'APP.ORDER_EVENT_T',
    multiple_consumers => TRUE
  );

  DBMS_AQADM.CREATE_QUEUE(
    queue_name  => 'APP.EVENT_Q',
    queue_table => 'APP.EVENT_QTAB'
  );
END;
/
~~~

Create a subscriber for the queue:

~~~sql
DECLARE
  l_subscriber SYS.AQ$_AGENT;
BEGIN
  l_subscriber := SYS.AQ$_AGENT('BILLING', NULL, NULL);

  DBMS_AQADM.ADD_SUBSCRIBER(
    queue_name => 'APP.EVENT_Q',
    subscriber => l_subscriber
  );

  DBMS_AQADM.START_QUEUE(
    queue_name => 'APP.EVENT_Q',
    enqueue    => TRUE,
    dequeue    => TRUE
  );
END;
/
~~~

Additional subscribers such as `INVENTORY` or `NOTIFICATION` can be added. If messages are delivered to all subscribers, each subscriber receives its own message delivery. If recipients must be restricted, producers can specify a recipient list via AQ APIs.

When dequeuing, the consumer specifies the subscriber name:

~~~sql
DECLARE
  l_dequeue_options    DBMS_AQ.DEQUEUE_OPTIONS_T;
  l_message_properties DBMS_AQ.MESSAGE_PROPERTIES_T;
  l_payload            APP.ORDER_EVENT_T;
  l_msgid              RAW(16);
BEGIN
  l_dequeue_options.consumer_name := 'BILLING';
  l_dequeue_options.wait := DBMS_AQ.NO_WAIT;
  l_dequeue_options.dequeue_mode := DBMS_AQ.REMOVE;
  l_dequeue_options.visibility := DBMS_AQ.ON_COMMIT;

  DBMS_AQ.DEQUEUE(
    queue_name         => 'APP.EVENT_Q',
    dequeue_options    => l_dequeue_options,
    message_properties => l_message_properties,
    payload            => l_payload,
    msgid              => l_msgid
  );

  -- Specific processing for subscriber BILLING.

  COMMIT;
END;
/
~~~

Multi-consumer queues are useful when multiple systems need the same event but process it independently. If subscriber `BILLING` has dequeued and committed, the message may still be pending for subscriber `INVENTORY`. Processing status must therefore be understood per subscriber, not just as one overall state for the message.

## 11. Queue Lifecycle: Start, Stop, and Message Management

A queue must be enabled for enqueue and/or dequeue before applications can use it.

Start queue:

~~~sql
BEGIN
  DBMS_AQADM.START_QUEUE(
    queue_name => 'APP.ORDER_Q',
    enqueue    => TRUE,
    dequeue    => TRUE
  );
END;
/
~~~

Pause enqueue while still allowing consumers to drain messages:

~~~sql
BEGIN
  DBMS_AQADM.STOP_QUEUE(
    queue_name => 'APP.ORDER_Q',
    enqueue    => TRUE,
    dequeue    => FALSE,
    wait       => TRUE
  );
END;
/
~~~

`STOP_QUEUE` parameters let you control stopping enqueue/dequeue and waiting for active operations per policy. Check exact parameter semantics for your Oracle version. During queue maintenance, coordinate with producers/consumers to avoid unexpected errors.

View queue configuration:

~~~sql
SELECT name,
       queue_table,
       enqueue_enabled,
       dequeue_enabled
FROM   user_queues
ORDER BY name;
~~~

View queue tables:

~~~sql
SELECT queue_table,
       object_type,
       sort_order,
       recipients
FROM   user_queue_tables
ORDER BY queue_table;
~~~

Views such as `USER_QUEUES`, `ALL_QUEUES`, `DBA_QUEUES`, and corresponding queue table views let you inspect status, payload type, sort order, and queue properties. View names/columns may vary by version and access privileges.

### Message Retention and Cleanup

Queues can be configured to retain messages for a period after dequeue for auditing or tracking. Retention differs from readiness for dequeue: a message confirmed as processed is no longer delivered to consumers, yet metadata/messages may be retained per the retention policy.

When cleaning up old data, use AQ-managed mechanisms like **DBMS_AQADM.PURGE_QUEUE_TABLE** according to your designed policy. Never delete rows directly from queue tables or internal AQ tables with plain SQL. Plan purging carefully, as it can remove data needed for investigation and reconciliation.

When decommissioning a queue, the teardown sequence normally involves stopping the queue, dropping the queue, and then dropping the queue table if no other queues use that table. Never drop a queue table holding messages that must be kept or queues still in use by applications.

## 12. Inspecting and Monitoring AQ

AQ monitoring should track message counts and processing progress, not just whether the queue is enabled.

Useful metrics:

- Number of messages waiting to be processed.
- Age of messages in the queue.
- Enqueue and dequeue rates.
- Retry counts and message count in exception queues.
- Consumer error rate.
- Latency from message creation to processing completion.
- Whether any queue or subscriber has a steadily growing backlog.

You can start with queue views:

~~~sql
SELECT name,
       queue_table,
       enqueue_enabled,
       dequeue_enabled,
       retention
FROM   user_queues
ORDER BY name;
~~~

AQ provides views to monitor queue tables, queues, and messages. Queue-table-generated views are typically named `AQ$<queue_table>`; they can be queried to inspect message states per privileges and version. Prefer Oracle-documented administrative views over accessing internal storage tables directly.

Checking message queues normally requires appropriate privileges. In multi-schema environments, use corresponding `DBA_` or `GV$` views if supported by your version and granted to your account.

### Checking Stuck Messages

If a backlog grows:

1. Confirm dequeue is enabled on the queue.
2. Check whether consumer processes are running and have dequeue privileges.
3. Check whether messages are delayed or expired.
4. Inspect retry counts and exception queues.
5. Check whether consumers are holding long transactions or locking messages.
6. Measure payload processing times and business errors.
7. Check whether the queue table is growing in size or cleanup is lagging.

Do not immediately scale up consumers if the root cause is repeatedly failing messages, an inactive subscriber, or consumers blocked by long transactions. Adding workers can increase database load without clearing the backlog.

## 13. AQ and Transactions in Real-World Applications

### Producer Transactions

Producers should perform business DML and enqueue in the same transaction when the message reflects the outcome of that DML.

Example: create an order and enqueue `ORDER_CREATED`. If order creation fails, the message is not emitted. If enqueue fails, the order also rolls back so data and messages stay aligned.

### Consumer Transactions

Consumers should dequeue with `REMOVE` and perform database updates in the same transaction. If processing fails, roll back so the message can be retried. If processing succeeds, commit to confirm both business changes and the dequeue.

### Do Not Hold Transactions Too Long

Consumers should limit how long they hold message locks. A long-running transaction keeps messages locked longer, reduces throughput, and prevents other workers from processing those messages. Design work in steps with clear transaction boundaries.

If a message requires very long processing, dequeue it and record work status in a business table within the same transaction; another worker performs the long-running processing under a separate workflow. Design explicit states and retries so work is not lost if a process stops.

### AQ Does Not Replace Distributed Transactions for External Systems

If a producer needs to commit Oracle and call a REST API, email, or external message broker, a single Oracle transaction cannot automatically commit/roll back synchronously with external systems. AQ atomically stores the message with the Oracle transaction, after which a consumer forwards the message externally. The consumer needs retries, idempotency, and external delivery tracking.

This is one way to implement a transactional outbox: the business transaction writes data and enqueues an event; a worker reads the event and forwards it externally. AQ provides the in-database queue, while retry/reconciliation and idempotency logic still belong to application design.

## 14. Common Errors

### Queue Not Started

The queue table and queue were created, but enqueue/dequeue has not been enabled. Check `USER_QUEUES` or `DBA_QUEUES` and run `START_QUEUE` with the proper enqueue/dequeue flags.

### Insufficient Enqueue/Dequeue Privileges

A user may see the queue yet lack privileges to perform operations. Check queue privileges via `DBMS_AQADM` along with package/type execution privileges. Grant least privileges to producers and consumers.

### Incompatible Payload

The PL/SQL variable payload type must match the queue table. For ADTs, verify schema, type name, attribute structure, and `EXECUTE` privilege on the type. Never pass a payload of a different type than the queue expects.

### Empty Queue or Dequeue Timeout

With `NO_WAIT`, having no matching message can raise `ORA-25228`. Handle this as an empty-queue or wait-timeout condition in worker logic. When using a finite `WAIT`, tune polling so it does not create constant query load.

### Messages Continuously Retried

Consumers may be rolling back due to business or technical errors. Inspect consumer logs, retry counts, retry delays, and exception queues. Determine whether the failure is transient or a data error before replaying messages.

### Messages Processed Twice

Can result from retries, consumer rollbacks after external side effects, or applications enqueuing the same event multiple times. Use business keys, unique constraints, inbox/processed-events tables, and idempotent handlers.

### Message Does Not Appear Even After Producer Ran ENQUEUE

Check visibility. If enqueue uses `ON_COMMIT`, the producer must commit. If the transaction rolled back, the message was not saved. Check exception paths, whether enqueue is enabled on the queue, producer privileges, and ORA/AQ errors in the session; also confirm the transaction actually committed.

### Consumer Dequeued Yet Business Update Was Not Recorded

If `REMOVE` dequeue used `IMMEDIATE` or the transaction committed before business processing finished, the message may have been acknowledged separately. Use `ON_COMMIT` and commit alongside business changes. Inspect transaction boundaries in calling code.

## 15. AQ Implementation Workflow

1. **Define the message model.** Choose ADT or RAW payload; define fields, versioning, and size.
2. **Choose single or multi-consumer.** Decide whether workers compete to process or multiple subscribers receive the same event.
3. **Create payload type.** Define the SQL object type and type usage privileges.
4. **Create queue table.** Use `DBMS_AQADM.CREATE_QUEUE_TABLE` with the appropriate payload type and `multiple_consumers`.
5. **Create queue.** Configure retries, delay, retention, and exception queue per requirements.
6. **Create subscribers if needed.** For multi-consumer, register consumers and define recipients.
7. **Start queue.** Enable enqueue/dequeue per role.
8. **Grant least privileges.** Grant `ENQUEUE` to producers, `DEQUEUE` to consumers, and necessary package/type privileges.
9. **Implement producer.** Enqueue in the same transaction as business DML when atomicity is needed.
10. **Implement consumer.** Dequeue with `REMOVE` and `ON_COMMIT`, process idempotently, and commit/roll back explicitly.
11. **Test failure modes.** Test producer rollback, consumer rollback, empty queues, retries, expiration, and exception queues.
12. **Monitor production.** Track backlogs, latency, retries, exception queues, and queue table storage usage.

## 16. Key Design Principles

- A queue table stores messages; a queue is the logical stream producers/consumers interact with.
- Use `DBMS_AQADM` to create/manage queues and `DBMS_AQ` to enqueue/dequeue.
- Choose payload type and single/multi-consumer before creating the queue table.
- Enqueue `ON_COMMIT` alongside DML so messages reflect committed business state.
- Dequeue `REMOVE` with `ON_COMMIT` alongside database updates so rollbacks return messages to the queue.
- `IMMEDIATE` creates an independent transaction boundary; use it only when that behavior is explicitly required.
- Design idempotent consumers because messages can be redelivered or producers may emit duplicate events.
- Configure retries, retry delays, expiration, and exception queues according to expected failure modes.
- Never manipulate internal AQ tables directly; use Oracle-supported APIs and views.
- Monitor backlogs, wait times, retries, and exception messages; rehearse handling failed messages.
- Do not assume Oracle transactions cover side effects in REST APIs, email, or external systems.
- Keep transactions short and clearly define where commit/rollback occurs to avoid locking messages too long.

Advanced Queuing provides a durable messaging mechanism right inside Oracle Database. When queue tables, payloads, enqueue/dequeue, and transaction visibility are properly configured, producers and consumers can operate independently while preserving consistency between messages and business data.
