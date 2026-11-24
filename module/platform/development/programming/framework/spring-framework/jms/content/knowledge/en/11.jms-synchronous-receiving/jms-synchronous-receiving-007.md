# Receiving in a Transacted Session — Spring Framework JMS

## 1. Objectives and scope

In Jakarta Messaging (JMS)'s **synchronous receive** model, an application thread calls `MessageConsumer.receive(...)` or `JmsTemplate.receive(...)` and waits for a message. When receiving takes place inside a **transacted Session**, the message is **not acknowledged merely because `receive()` returned**. Acknowledgement of messages received in the transaction happens on **commit**, whereas **rollback** restores received messages so they can be redelivered.

After this lesson, you will be able to:

- Distinguish **received**, **business-processed**, and **JMS committed/acknowledged**.
- Create a local JMS transaction using `Session.SESSION_TRANSACTED`, and use `receive(timeout)`, `commit()`, and `rollback()`.
- Combine multiple receives or **receive + send** within a single JMS transaction.
- Understand message redelivery, `JMSRedelivered`, `JMSXDeliveryCount`, retries, DLQ, and failure timing.
- Avoid confusing `JmsTemplate.setSessionTransacted(true)` **without a transaction manager** with `JmsTemplate.receive()` inside **`JmsTransactionManager`/`@Transactional`**.
- Understand the limits of local JMS transactions regarding databases, HTTP, email, payments, idempotency, and ambiguous commit outcomes.
- Run a Java 17, Spring Boot, and ActiveMQ Artemis example to observe **receive → rollback → redeliver → commit** firsthand.

**Core point:** A JMS transaction only guarantees atomicity for **the JMS operations belonging to that transaction**. It does not automatically span all work inside a Java method or a database transaction.

## 2. How does synchronous receiving differ from asynchronous receiving?

### 2.1. `receive()` occupies the calling thread

With the classic JMS API:

~~~java
Message m = consumer.receive(5_000L);
~~~

- If a matching message arrives before the deadline, the call returns `Message`.
- If 5,000 ms elapse without a message, the call returns `null`.
- `receive(0)` waits indefinitely per the JMS API; avoid it on request threads without a cancellation/stop mechanism.
- `receiveNoWait()` immediately returns an available message or `null`.
- With the classic API, `connection.start()` is required to enable delivery to the consumer.

By contrast, a `@JmsListener` is invoked **asynchronously** by a listener container. It can also run inside a JMS transaction, yet that is a **different execution model** from calling `receive()` directly.

### 2.2. Three milestones to distinguish

~~~text
Broker                      Synchronous consumer
  |                                  |
  +--------- deliver M ------------->|
  |                                  | receive() returns M
  |                                  | BUSINESS PROCESSING
  |                                  |
  |   if session transacted          |
  |<--------- commit() --------------|  acknowledges M
  |                                  |
  |         or                       |
  |<--------- rollback() ------------|  M may be redelivered
~~~

`receive()` returning only means **the message was delivered to the application**. Durability of business effects and ACK state depend on the transaction boundary. Inside a transacted Session, calling `message.acknowledge()` **does not replace** `session.commit()`.

## 3. Nature of a JMS transacted Session

### 3.1. A sequence of transactions

A transacted Session manages a sequence of local transactions:

~~~text
create transacted Session
          |
          v
Transaction T1 open
   +-- receive M1
   +-- receive M2
   +-- send M3
          |
    commit / rollback
          |
          v
Transaction T2 starts
   +-- receive ...
          |
    commit / rollback
          |
         ...
~~~

Per the Jakarta Messaging specification, a transacted Session encompasses both its **input stream** (received messages) and its **output stream** (sent messages):

- **Commit:** messages received in the transaction are acknowledged; messages sent in the transaction are committed and become eligible for delivery.
- **Rollback:** messages sent in the transaction are discarded; messages received are recovered so the provider can redeliver them.
- Each Session runs one transaction at a time sequentially, not multiple concurrent transactions on the same Session.
- After `commit()` or `rollback()`, the Session begins the next transaction.
- When a Session with an incomplete local transaction is `close()`d, the spec requires **rolling back the uncommitted transaction**.

If an application receives M1, M2 and sends M3 within the **same Session transaction**, it can commit all three operations together. However, if M3 is sent using a different Session, you **cannot** assume they belong to the same local transaction.

### 3.2. Level of guarantees

| What you want | Does a JMS local transacted Session guarantee it? |
|---|---|
| Receive M without ACKing before commit | Yes |
| Rollback makes M eligible for redelivery | Yes, per JMS and provider policy |
| Receiving M and sending reply X in the **same JMS Session/transaction** as one atomic JMS unit | Yes |
| Roll back a JDBC transaction at the same time | No, if using JMS local tx alone |
| Roll back an already succeeded HTTP call/payment/email | No |
| Never have duplicate business effects on network failure | No |
| `JmsTemplate.receive()` automatically keeps the transaction open for subsequent code | Not by default |
| Message is redelivered immediately on the very next `receive()` | No general guarantee on ordering or timing |

### 3.3. Acknowledgement mode is ignored in a transacted Session

With the classic API, create a Session via:

~~~java
Session session = connection.createSession(
        true, Session.SESSION_TRANSACTED);
~~~

The first argument `true` enables local transactions in a Java SE/standalone environment. Once transacted, the acknowledgement mode is **ignored**: `Session.SESSION_TRANSACTED` as the second argument simply documents intent clearly.

You may also call:

~~~java
Session session = connection.createSession(
        Session.SESSION_TRANSACTED);
~~~

This is the single-parameter overload introduced in JMS 2.0.

**Do not confuse `Session.SESSION_TRANSACTED` with `Session.CLIENT_ACKNOWLEDGE`:**

- In non-transacted `CLIENT_ACKNOWLEDGE`, calling `message.acknowledge()` acknowledges **messages delivered on the Session**.
- In `AUTO_ACKNOWLEDGE`, the provider acknowledges automatically upon successful completion of synchronous receive.
- In a **transacted Session**, acknowledgement comes from **commit**; calling `message.acknowledge()` is ignored.
- On non-transacted sessions, `Session.recover()` asks to redeliver unacknowledged messages; on a transacted Session, use **rollback** instead of `recover()`.

## 4. Creating a transacted Session with Jakarta Messaging

### 4.1. Classic API: opening connection, Session, and consumer

The following is a **snippet** inside a method with a configured `ConnectionFactory`; not a complete file with `main`:

~~~java
try (Connection connection = connectionFactory.createConnection();
     Session session = connection.createSession(
             true, Session.SESSION_TRANSACTED)) {

    Queue queue = session.createQueue("orders.queue");

    try (MessageConsumer consumer = session.createConsumer(queue)) {
        connection.start();

        Message message = consumer.receive(5_000L);
        if (message == null) {
            session.rollback();
            return;
        }

        try {
            processMessage(message);
            session.commit();
        } catch (Exception error) {
            session.rollback();
            throw error;
        }
    }
}
~~~

Explanation:

1. `createConnection()` obtains a connection from the provider.
2. `createSession(true, ...)` creates a **local JMS transaction**.
3. `createQueue("orders.queue")` creates a `Queue` reference object; the physical destination must be provisioned or auto-created by the provider/broker.
4. `createConsumer(queue)` creates a consumer bound to the Session.
5. `connection.start()` enables delivery.
6. `receive(5_000L)` blocks at most 5 seconds and may return `null`.
7. Application processes the message **while the transaction remains open**.
8. Processing succeeds → `commit()`; retryable failure → `rollback()`.

`processMessage(...)` is a hypothetical business method. In production, clearly distinguish which side effects belong to the JMS transaction and which fall outside its scope.

### 4.2. Do not share a Session across multiple threads

A `Session` is designed for **one thread of control at a time**. Do not place a Session or `MessageConsumer` in a singleton and let HTTP requests/threads call `receive()`, `commit()`, and `rollback()` concurrently.

~~~text
CORRECT:
  Thread A → Session A → receive/commit
  Thread B → Session B → receive/rollback

WRONG:
  Thread A ─┐
            ├─ Session X → race between receive and commit
  Thread B ─┘
~~~

To increase concurrency, create separate Sessions/consumers with clear ownership or use a Spring listener container. `CachingConnectionFactory` and pools can **reuse resources when no longer concurrently in use**, but they do not make a single Session thread-safe.

### 4.3. Simplified API `JMSContext`

JMSContext provides a more concise expression:

~~~java
try (JMSContext context =
        connectionFactory.createContext(
                JMSContext.SESSION_TRANSACTED)) {

    Queue queue = context.createQueue("orders.queue");
    JMSConsumer consumer = context.createConsumer(queue);

    Message message = consumer.receive(5_000L);
    if (message == null) {
        context.rollback();
    } else {
        processMessage(message);
        context.commit();
    }
}
~~~

This is also a Java SE/standalone snippet. If `processMessage` throws an exception and `JMSContext` closes while the transaction is open, the transaction will roll back; to make intent explicit, catch errors and call `context.rollback()` actively.

Inside a Jakarta EE container managing JTA, do not assume the local transaction API behaves identically to Java SE; transactions are governed by container and JTA infrastructure.

## 5. Commit: when is a message actually ACKed?

### 5.1. Timeline

~~~text
t0  connection.start()
t1  consumer.receive(5000) called
t2  receive returns Message M
    M received within transaction, NOT YET ACKed
t3  business logic processes M
t4  session.commit() returns successfully
    ACK for M is committed
t5  next transaction begins
~~~

If no exception occurs before t4 yet the application **forgets to commit**, the message may remain unacknowledged and reappear upon rollback/close/recovery. Logging "processed" before commit is **not** proof of "committed."

### 5.2. Receiving multiple messages in one transaction

~~~java
// Snippet: session is a transacted Session.
Message first = consumer.receive(2_000L);
Message second = consumer.receive(2_000L);

if (first != null && second != null) {
    processMessage(first);
    processMessage(second);
    session.commit();   // ACKs both inside the JMS transaction.
} else {
    session.rollback(); // Any message received in tx is recovered.
}
~~~

If M1 already called an HTTP service successfully while M2 fails, rolling back makes M1 eligible for redelivery. The HTTP side effect **does not automatically roll back**. You need idempotency or to avoid batching non-compensatable business effects.

### 5.3. Tradeoffs of "one commit per N messages"

Batching can reduce commit calls and improve throughput when the broker has noticeable transaction overhead, yet:

- A failure near the end of the batch can cause the entire batch to be redelivered.
- Long-lived transactions hold resources longer.
- Transaction timeouts can trigger rollbacks.
- Duplicate business effects are more likely if DB/API handling is not idempotent.
- When pulling batches with `receive(timeout)`, you must define a clear policy: commit a partial batch or roll back if fewer than N messages arrive.

There is no universal optimal batch size. Measure commit latency, broker depth/delivering counts, retries, CPU, and throughput on your own workload.

## 6. Rollback and redelivery

When `session.rollback()` is called on a transacted Session:

- Receives in the transaction are recovered.
- The broker/provider can redeliver messages per its redelivery policy.
- Sends in the same transaction are discarded.
- The next transaction can begin on the same Session.

~~~text
Queue holds M
    |
    v
receive M: count=1, redelivered=false
    |
    +-- business exception
    |
session.rollback()
    |
    +-- broker redelivery delay / policy
    |
    v
receive M: count=2, redelivered=true
    |
    +-- processing succeeds
    |
session.commit() → ACK
~~~

Two useful headers/properties for investigation:

~~~java
boolean redelivered = message.getJMSRedelivered();
int deliveryCount =
        message.getIntProperty("JMSXDeliveryCount");
String messageId = message.getJMSMessageID();
~~~

The first delivery typically has `JMSRedelivered=false` and `JMSXDeliveryCount=1`. When redelivered due to rollback, the provider must mark redelivered and increment delivery count per the specification. However, the count is not absolute proof of how many times business code executed; the provider may deliver a message while the JVM crashes before the handler runs, or failovers may make the count imprecise.

**Do not conclude "after rollback, the very next receive will definitely return M."** The broker may apply delay/backoff, priorities, competing consumers, TTL/expiry, and DLQ routing. Redelivery may arrive later or no longer reside in the original queue.

### 6.1. A Java exception by itself is not a rollback

In raw JMS:

~~~java
Message m = consumer.receive(5_000L);
throw new IllegalStateException("business failed");
~~~

Throwing an exception **does not immediately invoke `session.rollback()`**. The Session still holds the open transaction until its owner commits, rolls back, or closes it. Closing a transacted Session requires rolling back an open transaction, yet applications should explicitly roll back rather than relying on cleanup.

### 6.2. Ambiguous commit outcome

If the network drops while `session.commit()` is executing, the broker **may have already committed** while the client never received the response; or the transaction rolled back. Jakarta Messaging explicitly notes that the outcome may be indeterminate.

~~~text
Client                  Broker
  |------ commit() ------>|
  |                       | may have committed successfully
  |       network down    |
  x                       |
Client is unsure whether transaction committed
~~~

Do not blindly re-execute payment or DB side effects when the JMS outcome is uncertain. Use idempotency keys, state reconciliation, and broker/retry observability.

## 7. Receive + send in the same JMS transaction

A major strength of a JMS transacted Session is that **input + output on the same Session** commit or roll back together:

~~~text
orders.in ──receive──► Transacted Session
                           |
                           +── send(OrderValidated) ──► orders.validated
                           |
                           +── commit:
                               ACK input + publish output
                           |
                           +── rollback:
                               input is recovered; output is discarded
~~~

Snippet:

~~~java
Queue inputQueue = session.createQueue("orders.in");
Queue outputQueue = session.createQueue("orders.validated");

try (MessageConsumer consumer = session.createConsumer(inputQueue);
     MessageProducer producer = session.createProducer(outputQueue)) {

    Message input = consumer.receive(5_000L);
    if (input != null) {
        try {
            String id = input.getStringProperty("orderId");
            TextMessage output =
                    session.createTextMessage("validated:" + id);

            producer.send(output); // Send within JMS transaction.
            session.commit();      // ACK input and commit output.
        } catch (JMSException | RuntimeException ex) {
            session.rollback();
            throw ex;
        }
    }
}
~~~

This snippet sits inside a method where `session` was created as transacted and the connection is `start()`ed. `JMSException` must be declared or handled in the enclosing method. `producer` and `consumer` share the **same Session**, which is required for the operations to belong to one local JMS transaction.

### 7.1. Avoiding request-reply deadlocks in the same transaction

Anti-pattern:

~~~text
Session T:
    send(request)     (request not yet committed)
    receive(reply)    (waits for responder to handle request)
    commit()          (unreachable while waiting for reply)
~~~

The responder typically cannot see the request because it has not been committed. If the caller waits for a reply before committing, it causes a **logical deadlock** or timeout. The right way is to commit the request first and then receive the reply in a subsequent transaction, with a correlation ID and timeout.

### 7.2. Queues and Topics do not change semantics because of transactions

A JMS transaction governs ACK/commit. It **does not turn** a non-durable Topic subscriber into a durable subscriber, does not disable TTL, does not guarantee every consumer succeeds, and does not impose a uniform retry policy across all brokers.

## 8. An important distinction in Spring `JmsTemplate`

Spring allows synchronous receiving via:

~~~java
Message raw = jmsTemplate.receive("orders.queue");
Object converted = jmsTemplate.receiveAndConvert("orders.queue");
~~~

These calls block the caller according to `receiveTimeout`. You can configure:

~~~java
@Bean
JmsTemplate pollingTemplate(ConnectionFactory cf) {
    JmsTemplate t = new JmsTemplate(cf);
    t.setReceiveTimeout(5_000L);
    return t;
}
~~~

However, **you must distinguish two transaction patterns**.

### 8.1. Calling `setSessionTransacted(true)` alone does not protect business code after receive

~~~java
JmsTemplate t = new JmsTemplate(connectionFactory);
t.setSessionTransacted(true);
t.setReceiveTimeout(5_000L);

Message m = t.receive("orders.queue");
processMessage(m); // This part is NOT wrapped in receive's local tx.
~~~

When **no Spring-managed transaction is active**, the template creates a local transacted Session for the operation. Under Spring `JmsTemplate`'s receive execution model, when the Session is locally created by the template, Spring **commits after receiving** and before returning the message to the caller.

Consequence:

- Once `receive()` returns the message, the local JMS receive has already committed.
- `processMessage(m)` executes **outside that transaction boundary**.
- An exception thrown in `processMessage` cannot roll back the already-committed receive.
- `setSessionTransacted(true)` on the template **does not automatically create a wider transaction wrapping lines outside `receive()`**.
- With `receiveAndConvert()`, understand the conversion step and transaction boundary clearly; do not assume converter failures can always roll back merely by toggling this local flag.

This is a very common architectural mistake: **"transacted session" does not mean "all subsequent business processing runs inside one transaction."**

### 8.2. When should `JmsTransactionManager` be used?

When you need:

~~~text
Spring-managed JMS transaction starts
  |
  +-- JmsTemplate.receive(queue)
  |
  +-- validate / business logic
  |
  +-- possibly JmsTemplate.send(output)
  |
  +-- commit or rollback when entire scope finishes
~~~

Spring provides `JmsTransactionManager`, which manages a **local transaction** for a `ConnectionFactory` and binds the JMS Session to the thread. `JmsTemplate` detects the bound session and reuses it rather than committing the local receive operation before the caller finishes processing.

## 9. Spring `JmsTransactionManager` + `@Transactional`

### 9.1. Configuring the transaction manager

In a Spring configuration class:

~~~java
@Bean("jmsTransactionManager")
JmsTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

Requires importing `org.springframework.jms.connection.JmsTransactionManager`, `jakarta.jms.ConnectionFactory`, and `org.springframework.context.annotation.Bean`. With Boot, also ensure transaction annotation infrastructure is enabled, e.g. via Spring Boot auto-configuration or `@EnableTransactionManagement` when needed.

`JmsTransactionManager` and `JmsTemplate` **must reference the same matching ConnectionFactory**, otherwise resource binding to the thread may fail.

### 9.2. Transaction wrapping synchronous receive and business logic

~~~java
@Service
public class TransactionalOrderPoller {

    private final JmsTemplate template;

    public TransactionalOrderPoller(JmsTemplate template) {
        this.template = template;
    }

    @Transactional("jmsTransactionManager")
    public boolean pollAndProcess() {
        Message m = template.receive("orders.queue");
        if (m == null) {
            return false;
        }

        try {
            String eventId = m.getStringProperty("eventId");
            if (eventId == null || eventId.isBlank()) {
                throw new IllegalArgumentException("Missing eventId");
            }

            // Invoke processing logic here, before JMS commit.
            System.out.println("processing eventId=" + eventId);
            return true;
            // Normal method return => manager commits JMS.
        } catch (JMSException ex) {
            throw new IllegalStateException("JMS read failed", ex);
            // RuntimeException => rolls back by default.
        }
    }
}
~~~

This is an **example class**, requiring imports for `jakarta.jms.Message`, `jakarta.jms.JMSException`, `org.springframework.jms.core.JmsTemplate`, `org.springframework.stereotype.Service`, and `org.springframework.transaction.annotation.Transactional`. Logging is illustrative; production requires genuine idempotent processing.

Flow:

1. **Another** Spring bean invokes `pollAndProcess()` through the Spring transaction proxy.
2. The manager starts a local JMS transaction.
3. `JmsTemplate.receive()` uses the Session bound to the transaction.
4. Business logic runs while the JMS transaction remains open.
5. Normal completion → manager commits and ACKs the received message.
6. `RuntimeException`/`Error` per default rollback rules → manager rolls back, making the message eligible for redelivery.

**Never catch an exception and return success** if you intend a rollback. Spring sees the method complete normally and may commit. If you prefer not to throw, intentionally mark the transaction rollback-only.

### 9.3. Checked exceptions and proxies

Spring defaults to rolling back on unchecked exceptions (`RuntimeException`, `Error`), while checked exceptions usually do not trigger rollback unless configured. You can use:

~~~java
@Transactional(
    transactionManager = "jmsTransactionManager",
    rollbackFor = Exception.class)
public void pollAndProcessChecked() throws Exception {
    Message m = template.receive("orders.queue");
    processChecked(m);
}
~~~

This is only a **method snippet** requiring `processChecked` and `template`. Do not enable `rollbackFor=Exception.class` mechanically if a checked exception represents a partially successful business outcome; choose rules according to your error taxonomy.

With Spring AOP proxies, calling `this.pollAndProcess()` within the same bean can **bypass the proxy**, so no transaction is opened. `@Transactional` also has no effect if the class is instantiated manually with `new` rather than managed as a Spring bean.

### 9.4. Transactions are bound to a thread

~~~text
Thread A, Spring JMS Tx A
    JmsTemplate.receive() -> Session A
    process()
    JmsTemplate.send()    -> Session A
    commit/rollback Tx A

Thread B, Spring JMS Tx B
    JmsTemplate.receive() -> Session B
    process()
    commit/rollback Tx B
~~~

Do not assume Thread A's transaction automatically propagates into `ExecutorService`, `CompletableFuture`, or callbacks running on another thread. When multiple workers are needed, each worker creates its own transaction.

### 9.5. `TransactionTemplate` for programmatic scope control

~~~java
TransactionTemplate tx = new TransactionTemplate(jmsTransactionManager);

Boolean didWork = tx.execute(status -> {
    Message m = jmsTemplate.receive("orders.queue");
    if (m == null) {
        return false;
    }

    try {
        String eventId = m.getStringProperty("eventId");
        if (eventId == null) {
            status.setRollbackOnly();
            return false;
        }
        return true;
    } catch (JMSException ex) {
        throw new IllegalStateException(ex);
    }
});
~~~

This is a snippet with dependencies already injected. `TransactionTemplate` is an explicit way to keep **receive + processing** inside one properly scoped JMS transaction. It does not enlist a JDBC transaction into the local JMS transaction.

## 10. A JMS local transaction is NOT a DB transaction

### 10.1. Failure window: DB commits before JMS commits

~~~text
JMS receives M inside local transaction
          |
          v
Update database
          |
          v
DB COMMIT succeeds
          |
          v
JVM / network fails before JMS COMMIT
          |
          v
Broker rolls back/recovers, redelivers M
          |
          v
Another consumer may run the DB side effect again
~~~

The local `JmsTransactionManager` manages the JMS Session; it does not automatically roll back JDBC. Conversely, a database transaction manager does not automatically acknowledge JMS messages. That is why **JMS transacted receive alone is insufficient for exactly-once business effects**.

### 10.2. Idempotency key must be a stable business ID

The producer should attach a meaningful `eventId` independent of the JMS provider's ID, such as `eventId=order-created:42:v1`. A raw `JMSMessageID` can differ if the producer sends the same logical event twice.

The consumer can use a `processed_events` table with a unique constraint and business update in the **same database transaction**. PostgreSQL example:

~~~sql
BEGIN;

INSERT INTO processed_events(event_id)
VALUES ('order-created:42:v1')
ON CONFLICT (event_id) DO NOTHING;

-- ONLY when INSERT actually inserts a new row,
-- does the application run the business UPDATE in the same DB transaction.
UPDATE orders
SET state = 'PROCESSED'
WHERE id = 42;

COMMIT;
~~~

**Important:** The script above only illustrates the idea; **do not run both statements unconditionally** assuming duplicates are prevented. The application must inspect the inserted row count and execute the business update only when the event has not yet been processed, both within one DB transaction.

If the DB commits successfully yet JMS rolls back, the next delivery sees `eventId` already processed and finishes cleanly so JMS commits/acks without repeating the side effect. For external payment/email/HTTP APIs, use an idempotency token supported by the target service or an appropriate outbox/saga architecture.

### 10.3. When to consider JTA/XA?

When a single transaction must span both JMS and a database, JTA/XA can be used if the transaction manager, JDBC driver, and JMS ConnectionFactory **all** support it and are properly configured. JTA introduces tradeoffs in latency, recovery logs, coordinator overhead, timeouts, monitoring, and operations. It does not make non-transactional HTTP calls atomic.

Many microservices applications prefer **transactional outbox + idempotent consumer** over XA. Decide based on consistency requirements, failure scenarios, and operational capability.

## 11. Retries, DLQ, and poison messages

### 11.1. Transient failures

For example, a temporarily unresponsive dependency:

~~~text
receive M -> processing fails -> rollback
              |
              v
      redelivery delay/backoff
              |
              v
receive M again -> processing succeeds -> commit
~~~

Do not write tight rollback loops at high speed that overload the broker/DB. Attempt limits, delays, exponential backoff, dead-letter queues, and re-drive normally belong to **broker policies**, not JDBC or default annotations.

### 11.2. Permanent failures / poison messages

A message missing a required `schemaVersion` or bearing an invalid signature may **never** succeed through retries alone. Define:

- Classification of transient vs. permanent errors.
- Caps on redelivery attempts and delays.
- Routing to a DLQ/quarantine after max attempts or via a no-retry strategy.
- Logging correlation/eventId, queue, delivery count, exception type, and service instance.
- Controlled re-drive after fixing data, without inadvertently duplicating messages.

A valid pattern on the same broker/Session is **receive poison message → send quarantine copy in the same transacted Session → commit**. On commit, the original message is ACKed and the quarantine copy is sent atomically at the JMS layer; still guard sensitive payloads and prevent duplicate writes.

### 11.3. Do not skip every message with `JMSRedelivered=true`

The provider may have delivered a message once while the consumer was killed **before business code ran**. A redelivered message was not necessarily processed already. Deduplicate using a durable business `eventId`, not the redelivery flag as proof of "already processed."

## 12. Timeouts: receive, transaction, and processing

At least four timeouts/delays should be kept distinct:

| Kind | Meaning | Example |
|---|---|---|
| Receive timeout | Time thread waits in `receive()` | `receive(5_000L)` |
| Transaction timeout | Transaction limit set by manager/provider | 30 seconds, config-dependent |
| Business request timeout | Time spent calling DB/APIs during processing | 2 seconds |
| Broker redelivery delay | Wait before redelivering after rollback | 1 second, policy-dependent |

When `receive()` times out and returns `null`, if no message was received yet in the transaction, commit/rollback usually has negligible effect. However, if M1 was already received earlier in the **same transaction**, that decision will ACK or recover M1.

**Avoid indefinite `receive()` in HTTP request threads** without a cancellation mechanism or bounded server thread pool. Continuous polling typically suits background services; long-lived push/stream workloads fit asynchronous listener containers better.

## 13. Hands-on example: Java 17 + Spring Boot 3.5 + Artemis

The demo puts one message in a test queue and uses a **synchronous** consumer. After the first receive, the code intentionally calls `rollback()`, then receives again and calls `commit()`. It demonstrates JMS transaction boundaries using real API calls without relying on asynchronous listener annotations.

### 13.1. Environment requirements

Requires JDK 17+, Maven 3.9+, Docker, and ports `61616` and `8161` free.

Start the ActiveMQ Artemis broker:

~~~bash
docker run --detach --rm --name jms-tx-receive-lab \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Wait for broker startup and check:

~~~bash
docker logs jms-tx-receive-lab
~~~

Lab brokers normally allow auto-creating queues. In environments with auto-create disabled, pre-provision queue `lesson.jms.tx.receive` and send/consume permissions. Use demo credentials only in isolated environments.

### 13.2. Project structure

~~~text
jms-tx-receive-lab/
├── pom.xml
└── src/main/
    ├── java/example/TransactedReceiveApplication.java
    └── resources/application.properties
~~~

### 13.3. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.5</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>jms-tx-receive-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-artemis</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 13.4. `src/main/resources/application.properties`

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

### 13.5. `src/main/java/example/TransactedReceiveApplication.java`

~~~java
package example;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class TransactedReceiveApplication {

    private static final String QUEUE = "lesson.jms.tx.receive";

    public static void main(String[] args) {
        SpringApplication.run(TransactedReceiveApplication.class, args);
    }

    @Bean
    ApplicationRunner runDemo(JmsTemplate template,
                              ConnectionFactory connectionFactory) {
        return args -> {
            // Pre-send using template; this is a separate send operation.
            template.convertAndSend(QUEUE, "order-42");

            try (Connection connection =
                         connectionFactory.createConnection();
                 Session session = connection.createSession(
                         true, Session.SESSION_TRANSACTED)) {

                Queue queue = session.createQueue(QUEUE);

                try (MessageConsumer consumer =
                             session.createConsumer(queue)) {
                    connection.start();

                    // Transaction T1: receive then intentionally roll back.
                    Message first = consumer.receive(5_000L);
                    if (!(first instanceof TextMessage text1)) {
                        throw new IllegalStateException(
                                "First TextMessage not received");
                    }

                    System.out.println("firstBody=" + text1.getText());
                    System.out.println("firstRedelivered="
                            + first.getJMSRedelivered());
                    System.out.println("firstDeliveryCount="
                            + first.getIntProperty("JMSXDeliveryCount"));

                    session.rollback();
                    System.out.println("rolledBack=true");

                    // Transaction T2: receive again then commit.
                    Message second = consumer.receive(15_000L);
                    if (!(second instanceof TextMessage text2)) {
                        throw new IllegalStateException(
                                "Redelivered TextMessage not received");
                    }

                    System.out.println("secondBody=" + text2.getText());
                    System.out.println("secondRedelivered="
                            + second.getJMSRedelivered());
                    System.out.println("secondDeliveryCount="
                            + second.getIntProperty("JMSXDeliveryCount"));

                    if (!"order-42".equals(text2.getText())) {
                        session.rollback();
                        throw new IllegalStateException("Unexpected body");
                    }

                    session.commit();
                    System.out.println("committed=true");
                }
            }
        };
    }
}
~~~

This is a **complete Java file** with one public class matching the filename, using Java 17 `instanceof` pattern matching and Spring Boot auto-configured `JmsTemplate` and `ConnectionFactory`.

Points to observe:

1. `convertAndSend` is called beforehand so the queue holds exactly one `TextMessage`.
2. `Connection.createSession(true, Session.SESSION_TRANSACTED)` creates a local JMS transaction in standalone Java.
3. `connection.start()` is called before `consumer.receive(...)`.
4. The first receive obtains M **without** ACKing; `rollback()` makes the broker eligible to redeliver.
5. The second receive reads `JMSRedelivered` and `JMSXDeliveryCount`.
6. Only after checking the payload does `session.commit()` acknowledge M.
7. There is no shared mutable `Session`, and closing uses try-with-resources.
8. The example has no DB transaction, so do not infer it guarantees exactly-once business processing.

### 13.6. Running

In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

In a clean single-broker lab with one consumer and default redelivery without excessive delay, **the lines printed by the program** are typically:

~~~text
firstBody=order-42
firstRedelivered=false
firstDeliveryCount=1
rolledBack=true
secondBody=order-42
secondRedelivered=true
secondDeliveryCount=2
committed=true
~~~

The console also shows Spring Boot/Artemis logs. This is **expected output under specific conditions**, not a rigid guarantee across all providers/versions: the broker may configure delays, DLQs, prefetch, or have other consumers. `JMSXDeliveryCount` is not an infallible audit record across every failure/failover.

### 13.7. Inspecting the broker after commit

Use the Artemis management console at `http://localhost:8161` or CLI/metrics:

- Was queue `lesson.jms.tx.receive` created properly?
- Is the consumer count as expected?
- Was the message in delivering/unacknowledged state before commit?
- After successful commit with no other traffic, is the queue backlog empty?
- Was any message routed to a DLQ due to policy?

Note that queue depth showing 0 **while a message is being delivered** does not by itself prove it has been ACKed; brokers may display delivering counts separately.

Cleanup:

~~~bash
docker stop jms-tx-receive-lab
~~~

The container runs with `--rm` and no persistent volume mounted. When stopped, demo broker data is discarded; do not use this setup for production.

## 14. Comparing transactional receive approaches

| Approach | Who commits/rolls back | Is post-receive processing code inside the JMS transaction? |
|---|---|---|
| Raw `MessageConsumer.receive()` on an app-owned transacted Session | Application calls `session.commit()`/`rollback()` | **Yes**, if not committed/closed before processing |
| `JMSContext.SESSION_TRANSACTED` in Java SE | Application calls `context.commit()`/`rollback()` | **Yes** within the context's transaction scope |
| `JmsTemplate.receive()` with `sessionTransacted=true`, no Spring transaction manager | `JmsTemplate` auto-commits local receive | **No**, code after `receive()` runs outside that tx |
| `JmsTemplate.receive()` inside `@Transactional("jmsTransactionManager")` | Spring transaction manager | **Yes for JMS resources**, when invoked through the proxy properly |
| `JmsTemplate.receive()` inside JMS `TransactionTemplate` | Spring transaction manager | **Yes for JMS resources** within the callback |
| `@JmsListener` using a transacted listener container | Listener container | Yes for the listener callback, though **this is asynchronous receiving** |

Choose a solution based on synchronous polling needs, worker count, transaction duration, retry rules, database effects, and clarity of resource ownership.

## 15. Common mistakes

### Mistake 1 — Calling `message.acknowledge()` in a transacted Session

~~~java
Message m = consumer.receive(5_000L);
if (m != null) {
    m.acknowledge(); // Does NOT replace Session.commit().
}
~~~

Per JMS, `acknowledge()` is ignored on a transacted Session. To ACK, call `session.commit()` after successful processing.

### Mistake 2 — Logging "committed" before committing

~~~java
Message m = consumer.receive(5_000L);
System.out.println("received=true");  // Accurate if m != null.
System.out.println("committed=true"); // Wrong if not committed yet.
~~~

Especially when a network error occurs during commit, distinguish `COMMITTED`, `ROLLED_BACK`, and `UNKNOWN_OUTCOME`.

### Mistake 3 — Closing a Session expecting auto-commit

~~~java
try (Session session =
        connection.createSession(true, Session.SESSION_TRANSACTED)) {
    // receive...
    // No commit.
}
// Closing a transacted Session must roll back an open transaction.
~~~

Do not treat `try-with-resources` as an automatic message-acknowledgement mechanism.

### Mistake 4 — `JmsTemplate.setSessionTransacted(true)` followed by processing outside `receive()`

The Spring template can commit right inside the receive operation before returning the message. Use a transaction manager wrapping the workflow or a raw Session if processing must occur before JMS ACK.

### Mistake 5 — Catching exceptions and returning normally

In a `@Transactional` method, swallowing errors and returning normally lets the framework commit the message even though business processing failed. Throw an exception that triggers rollback or mark rollback-only intentionally.

### Mistake 6 — Thinking `Session.recover()` rolls back a transaction

`recover()` belongs to non-transacted sessions. In a transacted Session, use `rollback()`.

### Mistake 7 — Omitting `Connection.start()` before raw JMS receive

With the classic API, starting the connection is required for consumers to receive messages. Spring templates/containers manage this differently; do not confuse the two APIs.

### Mistake 8 — Not checking `null` when `receive(timeout)` expires

~~~java
Message m = consumer.receive(500L);
String id = m.getJMSMessageID(); // Potential NullPointerException.
~~~

Always check `m == null` before reading body/headers/properties.

### Mistake 9 — Sharing one Session across multiple threads

Threads can commit or roll back each other's transactions; a JMS Session is not a concurrently shareable resource. Give each worker its own session or use a proper manager/container.

### Mistake 10 — Sending a request and waiting for a reply before committing on the same Session

The responder generally cannot see an uncommitted request, causing logical deadlocks or timeouts. Separate the request-sending transaction from the reply-receiving transaction.

### Mistake 11 — Assuming one local JMS transaction covers JDBC

It does not. Use idempotency/outbox, or JTA/XA when infrastructure and requirements genuinely warrant it.

### Mistake 12 — Rolling back a poison message endlessly

Can cause tight loops and choke the broker. Define retry delays, max attempts, DLQs, triage, and re-drive procedures.

### Mistake 13 — `@Transactional` bypassed due to self-invocation

Calling `this.pollAndProcess()` inside the same bean can bypass the AOP proxy and fail to start a transaction. Invoke through a Spring-managed bean or use `TransactionTemplate`.

### Mistake 14 — Using the wrong transaction manager or ConnectionFactory

The JMS manager may point to a different factory than `JmsTemplate`, breaking resource binding. Check multi-broker configs, wrappers, caching/pooling, and manager bean names.

## 16. Production deployment checklist

- [ ] Clearly choose synchronous polling vs. `@JmsListener`; avoid accidentally competing on the same queue.
- [ ] In raw JMS, ensure the `Session` is truly transacted and the connection is `start()`ed.
- [ ] Receive messages with an appropriate timeout and handle `null`.
- [ ] Commit **after** all JMS operations in the transaction succeed; roll back on retryable failures.
- [ ] Never use `acknowledge()` or `recover()` instead of commit/rollback on a transacted Session.
- [ ] With `JmsTemplate`, establish a transaction boundary **wrapping receive + business processing**, not just `setSessionTransacted(true)`, if ACK must follow processing.
- [ ] `JmsTransactionManager` and `JmsTemplate` use the matching ConnectionFactory.
- [ ] `@Transactional` executes via proxy with proper rollback rules.
- [ ] Never share a Session/JMSContext concurrently across threads.
- [ ] DB/external side effects use idempotency / stable business event IDs.
- [ ] Retry, delay, max attempts, DLQ, and safe re-drive procedures are configured.
- [ ] Metrics track queue depth, delivering count, redeliveries, DLQs, transaction failures, and latency.
- [ ] Logs capture eventId, JMSMessageID, JMSRedelivered, JMSXDeliveryCount, outcome, and consumer instance.
- [ ] Tested rollback, process crash, timeouts, broker restart, unknown commit outcome, and DB-before-JMS-commit.
- [ ] Demo broker credentials/lifecycle are never used in production.
- [ ] Message delivery counts are never treated as proof that business side effects occurred.

## 17. Self-check questions

**1. Has `receive()` in a transacted Session already ACKed a successfully returned message?** No. Only commit acknowledges messages received in the transaction.

**2. Why does `message.acknowledge()` have no effect?** JMS specifies that this method is ignored inside a transacted Session; acknowledgement is governed by commit/rollback.

**3. If M1 and M2 are received and then rolled back, which messages are recovered?** All messages received in the same transaction, including M1 and M2, subject to broker policy.

**4. If M is received and X is sent on the same Session and then committed, what happens?** M is ACKed and X is committed as one local atomic JMS unit.

**5. If `JmsTemplate.setSessionTransacted(true)` is enabled without a transaction manager, can processing after `receive()` roll back the receive?** Not by default; the template may have already committed its local transaction inside the receive operation.

**6. How can Spring process business logic before ACKing?** Run `JmsTemplate.receive()` inside a `JmsTransactionManager`-managed transaction wrapping the processing, or use a raw transacted Session.

**7. When does `receive(timeout)` return `null`?** When the timeout expires without a matching message; still check whether any earlier message was already received in the same transaction.

**8. Does `Session.recover()` replace `rollback()` in a transacted Session?** No. Use rollback.

**9. If JMS rolls back while a DB update already committed, does the DB roll back automatically?** No. You need idempotency, an outbox, or an appropriate distributed transaction.

**10. Why does `JMSRedelivered=true` not prove code ran previously?** The provider may have delivered the message while the application crashed before the callback/business code executed.

**11. What is wrong with request-reply in the same local transaction before commit?** The responder may not see the uncommitted request, causing the caller to wait indefinitely for a reply.

**12. When a JMS commit hits a network error, why must retries be cautious?** The commit outcome may be ambiguous; blind retries of side effects create duplicates.

**13. Why does `@Transactional` fail to activate on self-invocation?** An internal call can bypass the Spring proxy holding the transaction advice.

**14. Should one singleton Session be shared by 20 polling threads?** No. Sessions must be used sequentially; multiple workers need separate Sessions.

**15. Why do poison messages require a DLQ?** Retrying an unfixable error easily causes rollback loops, wastes resources, and blocks other messages.

## 18. Official references

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): transactions, message acknowledgement, recovery, and commit outcome ambiguity.
- [Jakarta Messaging 3.1 API — Session](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/session): `SESSION_TRANSACTED`, `commit()`, `rollback()`, `close()`, and threading rules.
- [Jakarta Messaging 3.1 API — MessageConsumer](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageconsumer): `receive()`, `receive(timeout)`, `receiveNoWait()`.
- [Jakarta Messaging API — Message](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message): acknowledgement, headers, redelivery.
- [Jakarta EE Tutorial — JMS concepts](https://jakarta.ee/learn/docs/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html): local JMS transactions and avoiding send-then-receive deadlocks.
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): synchronous `JmsTemplate.receive` and receive timeouts.
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): transaction manager, resource binding, and threading.
- [Spring Framework 6.2 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `receive`, `receiveAndConvert`, `setSessionTransacted`.
- [Spring Framework 6.2 — JmsTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html): local JMS transaction manager.
- [Spring Boot 3.5 — JMS and Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): `spring-boot-starter-artemis` and `ConnectionFactory`.
- [ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html): test broker.

**Conclusion:** With **synchronous receiving in a transacted Session**, successful receipt is only the first step. **Commit** acknowledges received messages; **rollback** recovers them so the broker can redeliver. In Spring, distinguish `JmsTemplate` auto-committing a local receive from a **`JmsTransactionManager` transaction wrapping receive + processing**. When business logic involves a DB or external non-JMS APIs, add idempotency and appropriate consistency mechanisms to prevent duplicates.
