# Transactional Outbox and Idempotent Processing as a Data Coordination Strategy

## Learning Objectives

After this lesson, you can:

- Explain the dual-write bug when a business operation both updates the database and sends a JMS Message.
- Design a transactional outbox to store business changes and events in the same database transaction.
- Organize a relay that reads the outbox, sends Messages to JMS, and then marks the events as published.
- Understand why an outbox usually provides at-least-once publication and can produce duplicates.
- Design an idempotent consumer using an inbox/deduplication record committed together with the business side effects.
- Distinguish a JMS local transaction from a database transaction and understand the failure window between the two commits.
- Handle retries, poison events, dead-lettering, ordering, concurrency, and retention.
- Know when to use a polling relay, CDC, or XA/JTA.
- Implement a Java 17 example with Spring JMS, Spring JDBC, H2, and ActiveMQ Classic.

## 1. The Dual-Write Problem Between the Database and JMS

A service often performs two actions in the same business operation:

1. Update business data in the database.
2. Send an event via JMS so other services can react.

For example, when creating an order, the application saves the order and then publishes an order.created event to a Queue or Topic.

If these two actions use two independent resources, an ordinary transaction cannot automatically guarantee that both succeed together or both fail together.

~~~mermaid
flowchart LR
    A["Create order"]
    B["Database commit"]
    C["JMS send"]
    D["Downstream service"]

    A --> B --> C --> D
~~~

Both execution orders have a failure window:

- **Database first, JMS second:** the database commit succeeds, but the application stops or the broker fails before sending the Message. The order exists, but downstream does not receive the event.
- **JMS first, database second:** the broker receives the Message, but the database transaction rolls back. Downstream processes an event for a business change that was not committed.

This is the dual-write bug. Calling the database in a transaction and then calling JmsTemplate immediately afterwards does not turn the two resources into one atomic transaction.

A broker that supports persistent delivery also does not solve dual-write by itself. Persistent delivery helps the broker store the Message after receiving it; it does not coordinate the commit with the event-publishing service's database.

## 2. How Does the Transactional Outbox Solve the Problem?

The transactional outbox stores the event to be published in an outbox table inside the very database that stores the business data. The business change and the outbox record are written in the same local database transaction.

A separate relay process reads the committed outbox records, sends the event to JMS, and then marks the record as published.

~~~mermaid
flowchart TB
    A["Application service"]
    B["One database transaction"]
    C["Business table"]
    D["Outbox table"]
    E["Outbox relay"]
    F["JMS broker"]
    G["Consumer"]
    A --> B
    B --> C
    B --> D
    D --> E --> F --> G
~~~

Important rules:

- If the business transaction rolls back, both the business data and the outbox event roll back.
- If the transaction commits, both the business data and the outbox event exist.
- The relay only reads events that have been committed, and then tries to send them to the broker.
- If the broker is temporarily unavailable, the event remains in the outbox for the relay to retry.

The outbox turns event publishing into recoverable work after the database commit. The application no longer depends on a JMS send call succeeding at the exact same moment as the business transaction.

## 3. Structure of the Outbox Table

A practical outbox table typically stores the following fields:

| Field | Purpose |
|---|---|
| event_id | Unique, stable ID of the event |
| aggregate_type | Type of aggregate, for example Order |
| aggregate_id | ID of the order or source entity |
| aggregate_version | Version/sequence to control ordering |
| event_type | Event type, for example order.created |
| destination | Queue or Topic to publish to |
| payload | Event content captured at the time it occurred |
| status | Status NEW, IN_PROGRESS, PUBLISHED, or FAILED |
| attempts | Number of times the relay attempted to send |
| created_at | Time the event was created |
| published_at | Time the relay marked it published |
| last_error | Most recent error when sending failed |

Condensed DDL example:

~~~sql
CREATE TABLE outbox (
    event_id VARCHAR(64) PRIMARY KEY,
    aggregate_id VARCHAR(128) NOT NULL,
    event_type VARCHAR(128) NOT NULL,
    destination VARCHAR(255) NOT NULL,
    payload CLOB NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL,
    last_error VARCHAR(2000) NULL
);

CREATE INDEX idx_outbox_pending
    ON outbox(status, created_at);
~~~

event_id must be unique and must not change when the relay retries. The consumer uses this ID to recognize an event that was already processed earlier.

The payload should be an immutable snapshot of the data to publish. If the relay only stores aggregate_id and later reads the entity in its current state, an old event may be published with newer data and no longer accurately reflect the moment the business event occurred.

In a system with multiple event types, store the schema version or content type. Consumers need to know how to decode the payload and handle schema changes over time.

Do not store passwords, access tokens, or unnecessary sensitive data in the payload. An event may pass through brokers, logs, traces, and many downstream systems.

## 4. Writing Business Data and the Outbox in the Same Transaction

The business service must write both the aggregate and the outbox using the same transaction manager and the same database resource.

Example:

~~~java
@Transactional
public void createOrder(Order order) {
    orderRepository.insert(order);

    OutboxEvent event = new OutboxEvent(
            UUID.randomUUID().toString(),
            order.getId(),
            "order.created",
            serialize(order)
    );

    outboxRepository.insert(event);
}
~~~

When the method is called through the Spring transaction proxy:

- Spring starts a database transaction.
- The order data is written.
- The event is written to the outbox.
- If all operations complete, the transaction commits.
- If an operation throws a RuntimeException or Error, by default the transaction rolls back.

When the transaction commits, the database guarantees that the business data and the outbox row exist together. If inserting the outbox fails, the order is not committed in that transaction either.

### 4.1. @Transactional Must Actually Be Applied

In Spring's default proxy mode, @Transactional is activated when the method is called through the Spring proxy. A method in the same class calling another @Transactional method directly (self-invocation) usually does not go through the proxy and does not open a new transaction.

Place the transaction boundary on a public service method called from another bean. Use JdbcTemplate or DataSourceUtils to access the same DataSource that the transaction manager manages.

If the outbox is written to a different database than the business data, the two operations become a dual-write again. Bring the outbox into the same database transaction as the source aggregate.

### 4.2. Do Not Send JMS Inside the Transaction That Writes the Outbox

If you call JmsTemplate inside the same createOrder method, you have two independent resources again and return to the dual-write problem.

The transactional outbox writes the event to the database first. The relay sends JMS after the source transaction has committed. This decouples the business transaction from the moment the broker is available.

## 5. Outbox Relay: Read, Send, and Mark

The relay can run on a schedule, read a batch of pending events, send each event to its destination, and then update its status.

Basic flow:

~~~mermaid
sequenceDiagram
    participant R as Outbox relay
    participant DB as Database
    participant J as JMS broker

    R->>DB: Read NEW events
    DB-->>R: Committed events
    R->>J: Send Message with event_id
    J-->>R: Broker accepts send
    R->>DB: Mark PUBLISHED
    DB-->>R: Commit status
~~~

This order is intentional: only mark PUBLISHED after the JMS send operation returns successfully according to the client's contract.

If the send fails, keep the event in the pending state and increment attempts/last_error. The relay will try again according to the retry policy.

However, the send-then-mark order creates a duplicate window:

1. The broker has received the Message.
2. The relay application stops before updating the outbox to PUBLISHED.
3. Upon restart, the relay sees the event is still NEW and sends it again.
4. The broker may receive the same event_id a second time.

This is normal behavior for an outbox relay. You cannot eliminate this window merely by reversing the two operations: if you mark PUBLISHED before sending, a crash after marking but before sending can lose the event.

Therefore, an outbox usually prioritizes not losing events and accepts duplicates. The consumer must be idempotent.

## 6. At-Least-Once and Why You Should Not Promise Exactly-Once

An outbox relay usually provides an at-least-once publication model: an event is sent again until the relay records that it has been published successfully according to the system's policy.

An event can appear multiple times because:

- The relay sends successfully but crashes before marking PUBLISHED.
- The broker or client cannot return a clear outcome when the connection drops right at send time.
- The consumer finishes processing the database, but the JMS acknowledgement/commit fails.
- The broker redelivers after a rollback or a lost connection.
- An operator intentionally replays the event.

Therefore, event_id must stay stable across all retry attempts. Do not generate a new UUID each time the relay sends again, because the consumer will not recognize that it is the same event.

End-to-end exactly-once is a very strong claim. Even if the broker has deduplication or transactions, side effects outside the broker can still repeat if the application crashes between commit boundaries.

A practical design is usually:

- The producer writes the outbox atomically with the business data.
- The relay publishes at-least-once.
- The consumer deduplicates using event_id.
- The consumer's side effects and the inbox record are committed in the same database transaction.
- Side effects to external systems use an idempotency key or a follow-up outbox.

## 7. Inbox Pattern: Recording Processed Events

The consumer needs to know which event_ids have already been processed successfully. You can create an inbox table:

~~~sql
CREATE TABLE inbox (
    event_id VARCHAR(64) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

When receiving a Message, the consumer performs in one database transaction:

1. Check whether event_id is already in the inbox.
2. If it is already there, skip the side effects and return normally.
3. If it is not there yet, write event_id into the inbox.
4. Perform the business side effects.
5. Commit both the inbox record and the side effects together.

Example:

~~~java
@Transactional
public boolean processEvent(String eventId, OrderCreated event) {
    if (inboxRepository.exists(eventId)) {
        return false; // Duplicate: already processed earlier
    }

    inboxRepository.insert(eventId);
    orderProjectionRepository.apply(event);

    return true;
}
~~~

If the transaction commits, the inbox record and the side effects exist together. If a side effect fails, the transaction rolls back both; a later redelivery can try processing again.

If the database commit succeeds but the JMS acknowledgement fails, the broker may deliver the Message again. The next time, the consumer finds event_id in the inbox and skips the side effects.

### 7.1. A Unique Constraint Is the Final Line of Defense

Do not rely solely on a SELECT before an INSERT when multiple consumers can run concurrently:

- Consumer A checks that event_id does not exist yet.
- Consumer B also checks and sees it does not exist yet.
- Both try to insert and perform the side effects.

Make event_id a primary key/unique constraint. In production, use an atomic insert statement per the database dialect, such as INSERT ... ON CONFLICT DO NOTHING in PostgreSQL, and then check the number of inserted rows. With other databases, use an equivalent mechanism.

If the insert hits a duplicate, the transaction must not continue with the side effects as if it were a fresh processing pass. Handle the duplicate according to the database's semantics, or let the transaction roll back and then retry and check the inbox next time.

The runnable example below uses a single consumer thread to keep the checking flow sequential. The production guidance still requires a unique constraint and an atomic insert when there is concurrency.

### 7.2. Inbox and Side Effects Must Share the Same Database Transaction

If the inbox record is written in one database while the side effects are written in another database, the duplicate window reappears.

If the side effect is calling HTTP, sending an email, or writing to an external system, you cannot automatically make it atomic with the inbox database. Pass event_id as an idempotency key if the target system supports it; otherwise, design a separate workflow/saga or outbox for the downstream side effect.

## 8. JMS Transaction and Database Transaction Are Two Boundaries

Spring JMS lets you enable a local JMS transaction on the listener container:

~~~java
factory.setSessionTransacted(true);
~~~

Each time the listener processes a Message, it runs in a JMS Session transaction. If the listener completes normally, the container commits the JMS transaction. If the listener throws an exception, the container rolls back and the broker may redeliver the Message according to its redelivery policy.

If the listener calls a service that uses DataSourceTransactionManager, that database transaction is still an independent transaction from the JMS local transaction.

Common sequence:

~~~mermaid
sequenceDiagram
    participant B as JMS broker
    participant C as Listener container
    participant S as Spring service
    participant D as Database

    B->>C: Deliver Message in JMS transaction
    C->>S: Call service
    S->>D: BEGIN database transaction
    S->>D: Write inbox and side effects
    D-->>S: COMMIT database
    S-->>C: Method completes
    C->>B: COMMIT JMS acknowledgement
~~~

A situation can occur where the database commit succeeds but the JMS commit/acknowledgement fails. The broker redelivers the Message; the inbox detects the duplicate and prevents the side effects from running again.

If the database transaction rolls back, the exception must propagate out of the listener so that the container rolls back the JMS transaction. Do not swallow the exception and return normally, because then the container may commit the acknowledgement even though the business operation failed.

### 8.1. XA/JTA Is Another Option

If both the database and the JMS provider have XA resources, a JTA transaction coordinator can coordinate a two-phase commit distributed transaction.

XA can provide an atomic commit across the participating resources, but it comes with requirements for configuration, a recovery log, a transaction coordinator, an XA-capable connection factory, and operational overhead. It does not replace idempotency for side effects outside the transaction.

The transactional outbox is usually chosen when you want to avoid distributed transactions, accept at-least-once publication, and design idempotent consumers.

## 9. Retry, Backoff, and Dead-Letter

The relay needs a clear retry policy. If the broker is under maintenance, retrying too fast can create unnecessary load and excessive logs.

A common strategy:

- Increment attempts after each failed send.
- Use bounded exponential backoff with jitter.
- Store last_error with enough detail for diagnosis without recording secrets.
- Set a threshold on the number of attempts or the wait duration.
- Move unprocessable events to a FAILED/QUARANTINED state for operators to investigate.
- Have a replay tool once the root cause is fixed.

Do not delete failed events right away. Keep the payload, event_id, aggregate_id, and error so you can investigate or replay them.

The consumer also needs to distinguish:

- **Transient errors:** the database or a dependency is temporarily disrupted; can roll back so the broker redelivers.
- **Payload/schema errors:** repeated retries will not solve them; need a dead-letter or quarantine.
- **Business errors that cannot be recovered automatically:** persist the state and route to a manual handling workflow.
- **Duplicates:** this is a known outcome, so skip and acknowledge successfully after confirming the inbox record exists.

Brokers typically have maximum redelivery, redelivery delay, and a dead-letter queue. The specific configuration depends on the JMS provider. The outbox relay also needs its own error state; do not equate a relay failure with a consumer DLQ.

## 10. Ordering and Multiple Relay Instances

Ordering should be designed per aggregate or partition, not based solely on ORDER BY created_at.

If two events for the same order are published concurrently by multiple relays, event version 2 may reach the broker before version 1. Multiple consumer threads may also finish processing out of send order.

Commonly used measures:

- Store aggregate_version or sequence_number in the outbox.
- Publish the next event for an aggregate only after the previous event has been confirmed as published.
- Partition relays by aggregate_id.
- Use a message group/partition key if the broker supports it.
- Have the consumer check the version to detect missing or out-of-order events.
- Increase concurrency only when the business tolerates parallel processing.

When running multiple relay instances, do not let all of them read and send the same row. You can claim a batch in a short transaction with SELECT ... FOR UPDATE SKIP LOCKED if the database supports it, or use a claim status with lease_until and owner_id.

The claim flow should be short:

1. In a database transaction, claim NEW events and write owner/lease.
2. Commit the claim transaction.
3. Send JMS outside the transaction that holds the lock.
4. Mark PUBLISHED after the broker accepts.
5. If a worker dies, the lease expires so another worker can claim it again.

Do not hold a row lock while calling the broker over the network. A slow broker can keep the transaction and lock open too long and cause database contention.

A lease does not remove the duplicate window. A worker can send successfully and then die before marking; another worker will send again after the lease expires. The consumer must still be idempotent.

## 11. Polling Relay or CDC?

There are two common ways to move outbox events to the broker.

| Approach | How it works | Suitable when |
|---|---|---|
| Polling relay | The application periodically queries the outbox and sends JMS | Want minimal infrastructure, custom retry logic, moderate load |
| CDC | A tool reads the database transaction log and emits change events | High traffic, want to reduce polling, and have CDC infrastructure |

Polling is easy to implement but requires managing batch size, claiming, retry, ordering, and cleanup. Queries must have an index on status/created_at; avoid scanning the entire table on every cycle.

CDC reads the database's commit log such as WAL/binlog and sees only committed changes. The Debezium Outbox Event Router is a common example for routing outbox rows into Kafka. If the final target is JMS, you need a connector/bridge or a relay compatible with the JMS infrastructure; do not assume every CDC connector outputs directly to JMS.

Whether using polling or CDC, the consumer should still handle duplicates. A CDC connector can restart or replay records according to its offset/recovery semantics.

## 12. @TransactionalEventListener Does Not Replace a Durable Outbox

Spring has @TransactionalEventListener with the AFTER_COMMIT phase to handle application events after the transaction commits.

This is useful for internal side effects when durability limitations are acceptable. But if the process stops after the database commit and before the listener callback sends JMS, the in-memory event can be lost. There is no outbox record to recover from.

If the requirement is that the event must be published after the database commits even if the application restarts, write an outbox row in the source transaction. You can use an application event to wake the relay earlier, but the outbox remains the durable source of truth for the relay to rescan.

## 13. Runnable Java 17 Example: Spring JDBC, JMS, H2, and ActiveMQ

This example demonstrates both sides completely in a single JVM:

1. OrderService writes the order and the outbox row in the same H2 transaction.
2. OutboxRelay periodically sends events from the outbox to an ActiveMQ Queue.
3. ConsumerListener receives the JMS Message in a transacted listener session.
4. ConsumerService writes the inbox and the projection in the same database transaction.
5. The program sends the same event_id a second time to demonstrate that the duplicate is skipped.

To keep the example self-contained, the producer and consumer share one H2 database in the JVM. In production, each service usually owns its own database: the producer owns order/outbox; the consumer owns inbox and projection.

### 13.1. Maven Configuration

Create pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>transactional-outbox-jms-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>6.2.19</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-broker</artifactId>
            <version>6.1.6</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-client</artifactId>
            <version>6.1.6</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 13.2. Spring Configuration and Schema

Create src/main/java/demo/OutboxConfiguration.java:

~~~java
package demo;

import javax.sql.DataSource;

import jakarta.jms.ConnectionFactory;

import org.apache.activemq.ActiveMQConnectionFactory;
import org.h2.jdbcx.JdbcDataSource;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableJms
@EnableScheduling
@EnableTransactionManagement
public class OutboxConfiguration {

    @Bean
    public DataSource dataSource() {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:outboxdemo;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");
        dataSource.setPassword("");
        return dataSource;
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public PlatformTransactionManager transactionManager(
            DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    public InitializingBean databaseSchema(JdbcTemplate jdbc) {
        return () -> {
            jdbc.execute("""
                    CREATE TABLE orders (
                        order_id VARCHAR(64) PRIMARY KEY,
                        status VARCHAR(32) NOT NULL
                    )
                    """);

            jdbc.execute("""
                    CREATE TABLE outbox (
                        event_id VARCHAR(64) PRIMARY KEY,
                        aggregate_id VARCHAR(64) NOT NULL,
                        event_type VARCHAR(128) NOT NULL,
                        destination VARCHAR(255) NOT NULL,
                        payload VARCHAR(4000) NOT NULL,
                        status VARCHAR(20) NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        published_at TIMESTAMP NULL,
                        last_error VARCHAR(1000) NULL
                    )
                    """);

            jdbc.execute("""
                    CREATE INDEX idx_outbox_pending
                    ON outbox(status, created_at)
                    """);

            jdbc.execute("""
                    CREATE TABLE inbox (
                        event_id VARCHAR(64) PRIMARY KEY,
                        processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """);

            jdbc.execute("""
                    CREATE TABLE order_projection (
                        order_id VARCHAR(64) PRIMARY KEY,
                        status VARCHAR(32) NOT NULL
                    )
                    """);
        };
    }

    @Bean
    public ConnectionFactory connectionFactory() {
        return new ActiveMQConnectionFactory(
                "vm://outbox-demo?create=false"
        );
    }

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setDeliveryPersistent(true);
        return template;
    }

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");

        return factory;
    }

    @Bean
    @DependsOn("databaseSchema")
    public OrderService orderService(JdbcTemplate jdbc) {
        return new OrderService(jdbc);
    }

    @Bean
    @DependsOn("databaseSchema")
    public OutboxRelay outboxRelay(
            JdbcTemplate jdbc,
            JmsTemplate jmsTemplate) {
        return new OutboxRelay(jdbc, jmsTemplate);
    }

    @Bean
    @DependsOn("databaseSchema")
    public ConsumerService consumerService(JdbcTemplate jdbc) {
        return new ConsumerService(jdbc);
    }

    @Bean
    @DependsOn("databaseSchema")
    public ConsumerListener consumerListener(
            ConsumerService consumerService) {
        return new ConsumerListener(consumerService);
    }
}
~~~

### 13.3. OrderService Writes Order and Outbox Atomically

Create src/main/java/demo/OrderService.java:

~~~java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

public class OrderService {

    private final JdbcTemplate jdbc;

    public OrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void createOrder(String orderId, String eventId) {
        jdbc.update(
                "INSERT INTO orders(order_id, status) VALUES (?, ?)",
                orderId,
                "CREATED"
        );

        jdbc.update("""
                INSERT INTO outbox(
                    event_id,
                    aggregate_id,
                    event_type,
                    destination,
                    payload,
                    status,
                    attempts
                )
                VALUES (?, ?, ?, ?, ?, 'NEW', 0)
                """,
                eventId,
                orderId,
                "order.created",
                "orders.events",
                orderId
        );
    }
}
~~~

OrderService is a Spring bean called through a proxy from main. Because the two INSERT statements run under the same transaction manager and DataSource, if inserting the outbox fails then inserting the order also rolls back.

### 13.4. OutboxRelay Sends Events After Commit

Create src/main/java/demo/OutboxRelay.java:

~~~java
package demo;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.scheduling.annotation.Scheduled;

public class OutboxRelay {

    private final JdbcTemplate jdbc;
    private final JmsTemplate jmsTemplate;

    public OutboxRelay(
            JdbcTemplate jdbc,
            JmsTemplate jmsTemplate) {
        this.jdbc = jdbc;
        this.jmsTemplate = jmsTemplate;
    }

    @Scheduled(fixedDelay = 200)
    public void publishPending() {
        List<OutboxEvent> events = jdbc.query("""
                SELECT event_id, destination, event_type, payload
                FROM outbox
                WHERE status = 'NEW'
                ORDER BY created_at, event_id
                FETCH FIRST 10 ROWS ONLY
                """,
                (rs, rowNum) -> new OutboxEvent(
                        rs.getString("event_id"),
                        rs.getString("destination"),
                        rs.getString("event_type"),
                        rs.getString("payload")
                )
        );

        for (OutboxEvent event : events) {
            try {
                jmsTemplate.convertAndSend(
                        event.destination(),
                        event.payload(),
                        message -> {
                            message.setStringProperty(
                                    "eventId", event.eventId()
                            );
                            message.setStringProperty(
                                    "eventType", event.eventType()
                            );
                            return message;
                        }
                );

                jdbc.update("""
                        UPDATE outbox
                        SET status = 'PUBLISHED',
                            published_at = CURRENT_TIMESTAMP,
                            attempts = attempts + 1,
                            last_error = NULL
                        WHERE event_id = ?
                          AND status = 'NEW'
                        """,
                        event.eventId()
                );
            }
            catch (RuntimeException ex) {
                String error = ex.getClass().getSimpleName()
                        + ": " + ex.getMessage();

                if (error.length() > 900) {
                    error = error.substring(0, 900);
                }

                jdbc.update("""
                        UPDATE outbox
                        SET attempts = attempts + 1,
                            last_error = ?
                        WHERE event_id = ?
                          AND status = 'NEW'
                        """,
                        error,
                        event.eventId()
                );
            }
        }
    }

    private record OutboxEvent(
            String eventId,
            String destination,
            String eventType,
            String payload) {
    }
}
~~~

The relay has only one instance in the example. It queries a small batch, sends a Message with the eventId and eventType properties, and then marks it PUBLISHED. If the send fails, the row stays NEW and is retried in the next cycle.

In production with multiple relay instances, rows need to be claimed/leased safely before sending. This example does not implement distributed claiming to keep the illustration short and runs with one relay.

### 13.5. ConsumerService Uses the Inbox in the Same Transaction as the Side Effect

Create src/main/java/demo/ConsumerService.java:

~~~java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

public class ConsumerService {

    private final JdbcTemplate jdbc;

    public ConsumerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean process(String eventId, String orderId) {
        Integer existing = jdbc.queryForObject(
                "SELECT COUNT(*) FROM inbox WHERE event_id = ?",
                Integer.class,
                eventId
        );

        if (existing != null && existing > 0) {
            return false;
        }

        jdbc.update(
                "INSERT INTO inbox(event_id) VALUES (?)",
                eventId
        );

        jdbc.update("""
                INSERT INTO order_projection(order_id, status)
                VALUES (?, ?)
                """,
                orderId,
                "PROJECTED"
        );

        return true;
    }
}
~~~

This is a sequential example with a single listener consumer. In production, keep the primary key on inbox.event_id and use an atomic insert per the database dialect to handle races across multiple consumers.

### 13.6. JMS Listener Receives the Event and Distinguishes Duplicates

Create src/main/java/demo/ConsumerListener.java:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.jms.annotation.JmsListener;

public class ConsumerListener {

    private final ConsumerService consumerService;
    private final CountDownLatch firstProcessed = new CountDownLatch(1);
    private final CountDownLatch duplicateSkipped = new CountDownLatch(1);

    public ConsumerListener(ConsumerService consumerService) {
        this.consumerService = consumerService;
    }

    @JmsListener(
            destination = "orders.events",
            containerFactory = "jmsListenerContainerFactory"
    )
    public void receive(Message message) throws JMSException {
        if (!(message instanceof TextMessage textMessage)) {
            throw new IllegalArgumentException(
                    "Expected a TextMessage"
            );
        }

        String eventId = message.getStringProperty("eventId");
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing eventId property"
            );
        }

        boolean firstDelivery = consumerService.process(
                eventId,
                textMessage.getText()
        );

        if (firstDelivery) {
            firstProcessed.countDown();
        }
        else {
            duplicateSkipped.countDown();
        }
    }

    public boolean awaitFirst(long timeout, TimeUnit unit)
            throws InterruptedException {
        return firstProcessed.await(timeout, unit);
    }

    public boolean awaitDuplicate(long timeout, TimeUnit unit)
            throws InterruptedException {
        return duplicateSkipped.await(timeout, unit);
    }
}
~~~

ConsumerService is another bean, so the call to process goes through the transaction proxy. The database transaction commits before process returns to the listener. The listener container uses sessionTransacted=true; if processing throws an exception, the JMS transaction can roll back so that the broker redelivers.

### 13.7. Running the Broker, Creating an Order, and Replaying a Duplicate

Create src/main/java/demo/TransactionalOutboxDemo.java:

~~~java
package demo;

import java.util.concurrent.TimeUnit;

import org.apache.activemq.broker.BrokerService;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jms.core.JmsTemplate;

public class TransactionalOutboxDemo {

    public static void main(String[] args) throws Exception {
        BrokerService broker = new BrokerService();
        broker.setBrokerName("outbox-demo");
        broker.setPersistent(false);
        broker.setUseJmx(false);

        broker.start();
        broker.waitUntilStarted();

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             OutboxConfiguration.class
                     )) {

            OrderService orderService =
                    context.getBean(OrderService.class);
            ConsumerListener listener =
                    context.getBean(ConsumerListener.class);
            JmsTemplate jmsTemplate =
                    context.getBean(JmsTemplate.class);
            JdbcTemplate jdbc =
                    context.getBean(JdbcTemplate.class);

            String orderId = "ORD-183";
            String eventId = "evt-183-001";

            orderService.createOrder(orderId, eventId);

            if (!listener.awaitFirst(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Outbox event was not consumed"
                );
            }

            if (!awaitPublished(jdbc, eventId, 10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Outbox row was not marked PUBLISHED"
                );
            }

            // Simulate broker redelivery or the relay resending the same event.
            jmsTemplate.convertAndSend(
                    "orders.events",
                    orderId,
                    message -> {
                        message.setStringProperty("eventId", eventId);
                        message.setStringProperty(
                                "eventType", "order.created"
                        );
                        return message;
                    }
            );

            if (!listener.awaitDuplicate(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Duplicate was not detected"
                );
            }

            Integer publishedRows = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM outbox "
                            + "WHERE event_id = ? AND status = 'PUBLISHED'",
                    Integer.class,
                    eventId
            );

            Integer inboxRows = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM inbox WHERE event_id = ?",
                    Integer.class,
                    eventId
            );

            Integer projectionRows = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM order_projection WHERE order_id = ?",
                    Integer.class,
                    orderId
            );

            System.out.println("outbox.publishedRows=" + publishedRows);
            System.out.println("consumer.inboxRows=" + inboxRows);
            System.out.println("consumer.projectionRows=" + projectionRows);
            System.out.println("consumer.duplicateSkipped=1");
        }
        finally {
            broker.stop();
            broker.waitUntilStopped();
        }
    }

    private static boolean awaitPublished(
            JdbcTemplate jdbc,
            String eventId,
            long timeout,
            TimeUnit unit) throws InterruptedException {

        long deadline = System.nanoTime() + unit.toNanos(timeout);

        while (System.nanoTime() < deadline) {
            Integer count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM outbox "
                            + "WHERE event_id = ? AND status = 'PUBLISHED'",
                    Integer.class,
                    eventId
            );

            if (count != null && count > 0) {
                return true;
            }

            Thread.sleep(25);
        }

        return false;
    }
}
~~~

Run from the directory containing pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.TransactionalOutboxDemo
~~~

Program stdout:

~~~text
outbox.publishedRows=1
consumer.inboxRows=1
consumer.projectionRows=1
consumer.duplicateSkipped=1
~~~

### 13.8. Analyzing the Result

OrderService writes order ORD-183 and outbox event evt-183-001 in the same database transaction. If either INSERT fails, the transaction rolls back and no order is committed on its own.

OutboxRelay runs periodically, reads the NEW event, and sends a TextMessage to Queue orders.events. eventId is attached as a JMS property so the consumer uses it as a deduplication key. After the send returns successfully, the relay marks the outbox row PUBLISHED.

ConsumerListener receives the Message. ConsumerService checks the inbox, writes event_id, and updates order_projection in the same transaction. On the first pass, both the inbox row and the projection row are committed.

The program then sends the same event_id again to simulate a duplicate. ConsumerService finds the inbox row and returns false, so the projection is not inserted a second time. The output shows one inbox row, one projection row, and one skipped duplicate.

The example uses a single relay instance, a single consumer, and a non-persistent broker to focus on transaction/outbox/idempotency. It does not prove the broker's HA or durability capabilities. In production, use a broker configured for persistence, safe relay claiming, and an idempotent consumer.

## 14. Operations and Observability

A transactional outbox needs metrics and operational processes, not just a database table.

You should monitor:

- Count of NEW or IN_PROGRESS events.
- Age of the oldest NEW event.
- Failed send count per destination.
- Duration from created_at to published_at.
- Count of events moved to FAILED/quarantine.
- Rate of duplicates skipped by the consumer.
- JMS redelivery and dead-letter counts.
- Processing latency from when the event was created to when the side effects completed.

If the outbox backlog grows continuously, the relay or the broker is not keeping up with the event write rate. Examine batch size, number of relay workers, broker limits, network, payload size, and consumer speed.

You can partition or archive PUBLISHED outbox rows over time. Do not delete events that are NEW/IN_PROGRESS. The inbox also needs retention; delete records only after the system's maximum replay period has passed and it is certain no source can replay old events.

If you delete inbox records too early, a replayed old event can run the side effects again. Inbox retention must be longer than the period over which the broker, backups, operators, or CDC can replay events.

## 15. Common Mistakes

1. **Writing the order and immediately sending JMS in the same method and thinking @Transactional covers both:** DataSourceTransactionManager does not automatically manage JMS resources.
2. **Writing the outbox after commit using an in-memory callback:** a process crash can lose the event before writing the outbox.
3. **Marking PUBLISHED before sending:** a crash between the two operations can lose the event.
4. **Generating a new event_id on retry:** the consumer cannot recognize the duplicate.
5. **Assuming the relay only sends once:** a crash after send and before mark can create duplicates.
6. **Having no unique constraint on inbox.event_id:** multiple consumers can process the same event concurrently.
7. **Writing the inbox and the side effects in two different transactions:** an event can be marked processed even though the side effect rolled back, or vice versa.
8. **Swallowing exceptions in the JMS listener:** the container may commit the acknowledgement even though the business operation failed.
9. **Using AUTO_ACKNOWLEDGE when reliable redelivery is needed:** configure an appropriate listener transaction, for example sessionTransacted=true.
10. **Assuming a JMS local transaction automatically includes the database:** two local resource transactions are independent unless XA/JTA is used.
11. **Not controlling relay concurrency:** multiple relays may send the same row; you need claim/lease or CDC.
12. **Holding database locks while calling the broker:** a slow network can hold the transaction and locks for too long.
13. **Not managing ordering:** multiple workers can publish or process events for the same aggregate out of order.
14. **Retrying poison events infinitely:** you need limits, quarantine, and a dead-letter policy.
15. **Deleting inbox records too early:** an old replay can create duplicate side effects.
16. **Using the inbox to prevent every side effect outside the database:** email or HTTP needs an idempotency key or its own workflow.
17. **Using @TransactionalEventListener(AFTER_COMMIT) as a durable outbox:** an in-process callback does not store events to recover after a crash.
18. **Promising exactly-once merely because persistent JMS messages are used:** broker persistence does not turn database and JMS commits into one atomic transaction.

## 16. Design Checklist

Before putting an outbox into production, confirm:

- The order/aggregate and the outbox row use the same database transaction.
- event_id is stable, unique, and sent in the Message.
- The payload is a snapshot with a clear schema version.
- The relay marks PUBLISHED only after the send is accepted.
- Retries have backoff, limits, and store last_error.
- Multiple relay instances use claim/lease or an appropriate CDC mechanism.
- Ordering is defined per aggregate if the business requires it.
- The consumer has a unique inbox event_id.
- The inbox and database side effects share the same transaction.
- The JMS listener transaction rolls back when processing fails.
- Duplicates are acknowledged after confirming they were processed earlier.
- Side effects outside the database have an idempotency key or their own workflow.
- The outbox/inbox has retention, archive, and replay policies.
- Dashboards exist for backlog, oldest event age, failures, redelivery, and duplicates.

## 17. Self-Check Questions

1. How does dual-write occur when a business operation both commits to the database and sends JMS?
2. Why must the outbox row be written in the same transaction as the aggregate?
3. Should the relay mark PUBLISHED before or after sending JMS?
4. What does a crash after the broker accepts the Message but before marking create?
5. Why is a transactional outbox usually at-least-once?
6. What property must event_id have so the consumer can recognize duplicates?
7. Why must the inbox record and the side effects lie in the same transaction?
8. How does a unique constraint help resolve races across multiple consumers?
9. How does sessionTransacted=true affect JMS acknowledgement/rollback?
10. Why do a JMS local transaction and a database transaction still have a duplicate window?
11. When is XA/JTA needed instead of an outbox?
12. Why is @TransactionalEventListener(AFTER_COMMIT) not equivalent to a durable outbox?
13. How do multiple relay instances avoid claiming the same event?
14. What needs to be done to preserve ordering per aggregate?
15. Why must inbox retention be longer than the replay window?
16. When the side effect is an HTTP call, how do you prevent repeated execution?

## 18. Conclusion

The transactional outbox coordinates database changes and event publication by writing the aggregate together with the event in a single local transaction. The relay sends committed events to JMS and marks their status after the broker accepts. This avoids losing events due to a crash between the database commit and the first JMS send.

The relay can still send duplicates if it crashes after the broker receives the Message but before marking PUBLISHED. Therefore, the consumer needs an inbox/deduplication record with a unique event_id and must write that record together with the side effects in one database transaction. A JMS local transaction helps roll back the acknowledgement when the listener fails, but does not by itself turn JMS and the database into one atomic transaction.

A production design additionally needs claim/lease or CDC, retry/backoff, dead-lettering, ordering, idempotency for side effects outside the database, retention, and metrics. The goal is never to lose a committed event and to ensure that redelivery does not cause the business operation to execute repeatedly.

## Official References

- Spring Framework — Receiving a Message, Processing Messages Within Transactions: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework — Using @Transactional: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — JDBC Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- AWS Prescriptive Guidance — Transactional outbox pattern: https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html
- Debezium — Outbox Event Router: https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html
- Jakarta Messaging specification: https://jakarta.ee/specifications/messaging/
- Apache ActiveMQ Classic: https://activemq.apache.org/components/classic/
