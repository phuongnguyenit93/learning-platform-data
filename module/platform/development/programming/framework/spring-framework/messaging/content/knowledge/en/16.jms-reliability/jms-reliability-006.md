# Designing Idempotent Processing with Business Keys

## Objectives

After this lesson, you can:

- Explain why a JMS message can be processed multiple times even though the broker supports acknowledgement and redelivery.
- Distinguish message redelivery from a producer resending the same business event.
- Choose a stable business idempotency key and determine the correct uniqueness scope of the key.
- Design an inbox/processed-message table with a unique constraint to prevent a side effect from being applied twice.
- Put the recording of "already processed" and the business data update in the same database transaction.
- Coordinate the database transaction with the JMS local transaction to handle the failure window between the DB commit and the JMS acknowledgement.
- Handle concurrency, retention, replay, payload conflicts, and side effects that call external systems.
- Understand the roles of `JMSRedelivered`, `JMSXDeliveryCount`, Spring Integration `IdempotentReceiverInterceptor`, and `MetadataStore`.
- Build a Spring JMS consumer that can receive the same message again but records it only once in the business ledger.

## 1. What is idempotent processing?

An operation is called *idempotent* if performing it once or many times with the same business key produces the same business result.

For example, the payment event `payment-1001` requires recording a receipt of 125.00. If the same event is delivered twice, the system may only create one ledger entry:

~~~text
First receipt:
payment-1001
    |
    v
Record key + post ledger entry 125.00
    |
    v
COMMIT

Next receipt:
payment-1001
    |
    v
Key already exists
    |
    v
Skip side effect
~~~

Idempotency does not mean the listener is called only once. The listener may be called multiple times; what must be guaranteed is that the same business operation does not change the business state multiple times.

In a messaging system, a common approach is to accept *at-least-once* delivery and then make the consumer idempotent. This is the practical way to handle retry, redelivery, restart, and failures at the transaction boundary.

## 2. Why does JMS still need idempotency?

JMS provides acknowledgement, transactions, and redelivery. However, delivering the message and updating the business database usually belong to two different resources.

Spring Framework explains this clearly: when `sessionTransacted=true` is enabled, each listener invocation runs in a JMS local transaction. If the listener fails, the receipt of the message is rolled back. But other database operations run independently of the JMS transaction. Therefore you need duplicate detection in the listener to handle the case where the database has committed but the JMS transaction has not. See [Spring Framework 6.2.19: AbstractMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html).

A typical failure window:

~~~text
JMS broker                 Consumer                  Database
    |                         |                          |
    |---- deliver message --->|                          |
    |                         |---- BEGIN DB TX -------->|
    |                         |---- write business ----->|
    |                         |---- COMMIT DB ---------->|
    |                         |                          |
    |                JVM / process crashes               |
    |                         X                          |
    |<--- JMS COMMIT has not happened                    |
    |                         |                          |
    |---- redeliver message ->|                          |
    |                         |---- check business key   |
    |                         |---- key already exists   |
    |                         |---- skip side effect     |
    |<--- JMS COMMIT ---------|                          |
~~~

If the consumer has no idempotency, the redelivery could post a ledger entry, debit money, create an order, or issue an invoice one more time.

### Situations that can produce duplicate messages

- The listener finishes processing but the JVM stops before the JMS transaction commits.
- The connection is dropped before the acknowledgement completes.
- The consumer rolls back the transaction because of an exception.
- The broker redelivers the message after the consumer restarts.
- The producer resends the same business event after a timeout because it does not know whether the previous send succeeded.
- The outbox relay republishes an event because the process stopped after publishing but before marking the outbox row as sent.
- An operator replays a message from the DLQ or from an archive store.

You need to distinguish **redelivery of the same JMS message** from **the producer republishing the same business event**. A producer republishing can create a new JMS message with a different `JMSMessageID`, but it still carries the same business key.

## 3. Designing the business idempotency key

The business key must identify a specific business operation and stay unchanged across every retry or republish.

Example:

| Business operation | Suitable key | Error-prone key |
|---|---|---|
| Recording a payment | `paymentId` or `paymentAttemptId` | `orderId` if one order has multiple payments |
| Refund | `refundId` | `orderId` if multiple refunds are possible |
| Creating an invoice | `invoiceRequestId` | `customerId` |
| Updating one version of an aggregate | `aggregateId + eventVersion` | Only `aggregateId` |
| Receiving events per tenant | `tenantId + eventId` | `eventId` if the ID is only unique within a tenant |

A good business key has these characteristics:

1. **Stable:** the producer creates it once and keeps it unchanged on retry.
2. **Unique per business operation:** two different operations do not share a key.
3. **Independent of transport:** the key does not change when the message is resent through the broker or via a different producer.
4. **Clear scope:** determine whether the key is unique system-wide, per tenant, per event type, or per consumer.
5. **Not reused:** a key that has been completed must not be used for a new business operation.

### Composite key by consumer and business key

A system may have multiple consumers performing different side effects for the same event. Therefore the inbox typically uses a composite key:

~~~sql
PRIMARY KEY (consumer_name, business_key)
~~~

Example:

- `payment-ledger / payment-1001`
- `customer-notification / payment-1001`
- `analytics-projection / payment-1001`

Each consumer can process the same event once for its own side effect.

If multiple tenants can have the same `paymentId`, put the tenant into the business key or into a separate column in the unique constraint:

~~~sql
PRIMARY KEY (consumer_name, tenant_id, business_key)
~~~

Do not add a deployment version to `consumer_name` arbitrarily. If you rename `payment-ledger-v1` to `payment-ledger-v2`, the system may treat all old messages as unprocessed and post to the ledger again. Only change the namespace when you deliberately want to create a new side-effect flow or a controlled replay.

### Avoid using JMSMessageID as the business key

The JMS fields have their own purposes:

| Field | Purpose | Use as an idempotency key? |
|---|---|---|
| `JMSMessageID` | Message identifier assigned by the provider | Not recommended; a producer resending the same event may create a new ID |
| `JMSCorrelationID` | Links a request and reply or related messages | Only if the business contract explicitly defines it as the operation key |
| `JMSRedelivered` | Indicates the message was probably delivered before | No; it is only a redelivery indicator |
| `JMSXDeliveryCount` | Number of times the provider delivered the message | No; it serves observation and retry handling |
| Business key | Identifies the business operation | Yes |

The business key should be carried in the payload or in a JMS property/header agreed between producer and consumer. For example: `paymentId`, `refundId`, `eventId`.

## 4. JMSRedelivered and JMSXDeliveryCount are only diagnostic metadata

Jakarta Messaging 3.1 defines:

- `JMSRedelivered`: if true, the message was probably delivered before but not acknowledged.
- `JMSXDeliveryCount`: the number of times a message has been delivered; the first time has the value 1, and 2 or more indicates it has been redelivered.

The provider must set `JMSRedelivered` when redelivering per the contract and increment `JMSXDeliveryCount`. However, the specification says the `JMSXDeliveryCount` value is not guaranteed to be absolutely accurate after some provider failures. See [Jakarta Messaging 3.1, §3.4.7, §3.5.11 and §6.2.11](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.pdf).

You can read the metadata for logging:

~~~java
boolean redelivered = message.getJMSRedelivered();

int deliveryCount = message.propertyExists("JMSXDeliveryCount")
        ? message.getIntProperty("JMSXDeliveryCount")
        : 1;

log.info(
        "JMS delivery: redelivered={}, deliveryCount={}",
        redelivered,
        deliveryCount
);
~~~

Do not run the duplicate check only when `JMSRedelivered == true`. A producer can republish the same payment event as a new JMS message with `JMSRedelivered == false`, yet the business operation is still the same payment. The business key must be checked for every message.

## 5. Inbox table and unique constraint

A common implementation is to store one record for each business key the consumer has processed.

Example schema:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(100) NOT NULL,
    business_key  VARCHAR(160) NOT NULL,
    processed_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    payload_hash  VARCHAR(128),
    PRIMARY KEY (consumer_name, business_key)
);

CREATE TABLE payment_ledger (
    entry_id  BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    payment_id VARCHAR(80) NOT NULL,
    account_id VARCHAR(80) NOT NULL,
    amount DECIMAL(19, 2) NOT NULL
);
~~~

`processed_event` is the inbox/deduplication table. The unique constraint in the database is the final arbitration mechanism when multiple threads or multiple instances receive the same key.

### Use insert-first, not check-then-insert

The approach prone to race conditions:

~~~text
Consumer A: SELECT key -> not found
Consumer B: SELECT key -> not found
Consumer A: write side effect
Consumer B: write side effect
Consumer A: INSERT key
Consumer B: INSERT key
~~~

Two consumers may both see that the key does not exist before either records it.

A safer approach:

1. Open a database transaction.
2. Try to `INSERT` the business key into the inbox table.
3. The unique constraint allows exactly one transaction to claim the key.
4. Only the transaction whose insert succeeds performs the business write.
5. Commit the inbox row and the business write in the same transaction.

~~~text
BEGIN DB TRANSACTION
        |
        v
INSERT processed_event(consumer_name, business_key)
        |
        +---- duplicate key
        |         |
        |         v
        |      ROLLBACK
        |      return DUPLICATE
        |
        +---- insert succeeds
                  |
                  v
          update business data
                  |
                  v
               COMMIT
~~~

Do not use an in-memory `Set` as the sole mechanism. It does not protect multiple instances, loses data on restart, and is not synchronized with the database transaction. A `SELECT` before the insert also does not replace the unique constraint.

### Why must it be the same DB transaction?

If you write the inbox first and commit separately, and only then update the business data, the process may stop between the two steps. The redelivery sees the key already exists and skips, while the side effect never happened.

If you update the business data first and write the inbox in a separate transaction, the process may stop after the business write commits but before the inbox commits. The redelivery will perform the business write again.

Putting both in the same transaction makes the database commit or roll back everything:

- Transaction rollback: the inbox row does not exist and the business write does not exist; the message can be processed again.
- Transaction commit: both the inbox row and the business write exist; the next processing is blocked by the unique constraint.

## 6. Coordinating the database transaction with the JMS transaction

A Spring listener container can enable a local JMS transaction:

~~~java
container.setSessionTransacted(true);
~~~

With this configuration, receiving the message and the acknowledgement are managed by the JMS transaction. If the listener throws an exception, the container rolls back the JMS transaction and the broker may redeliver the message.

However, `DataSourceTransactionManager` and the JMS local transaction are two separate transactions. Spring recommends using a local JMS transaction together with a local database transaction and duplicate detection in the listener logic to cover the failure window after the DB commit but before the JMS commit.

### Recommended processing flow

~~~text
JMS listener receives event
        |
        v
DB transaction begins
        |
        v
INSERT inbox key (unique)
        |
        +---- duplicate
        |       |
        |       v
        |   DB rollback
        |   listener returns normally
        |       |
        |       v
        |   JMS transaction commit
        |
        +---- new key
                |
                v
        update business tables
                |
                v
           DB commit
                |
                v
        listener returns normally
                |
                v
         JMS transaction commit
~~~

If the DB transaction fails because of a transient error, let the exception escape the listener. The JMS transaction then rolls back and the message is redelivered per the broker policy.

If the DB commit succeeds but the JMS commit has not happened, the broker may redeliver. The next processing will hit the unique key and skip the side effect, then the listener completes normally so the JMS transaction commits.

### XA/JTA is another option

You can coordinate JMS and the database in a distributed XA/JTA transaction if both resources support XA and are registered with the transaction coordinator.

- Message receipt and the database write participate in the same transaction.
- The coordinator manages the shared commit/rollback.
- Reduces the failure window between the two resources.
- In exchange you need an XA-capable provider, JTA configuration, a transaction log, recovery operations, and higher processing cost.

Spring Framework lists two options: duplicate detection in the listener, or an XA transaction spanning message receipt and business processing. For many applications, a local transaction plus an inbox unique key is simpler and more efficient. Choose XA when multi-resource consistency is truly required.

## 7. Complete Java 17 example: Spring JMS + H2 inbox

The example uses Java 17, Spring Framework 6.2.19, ActiveMQ Classic 6.2.6, and H2. The broker runs embedded in the same JVM. The program sends two separate JMS messages with the same `paymentId`; the consumer creates only one ledger entry.

Directory structure:

~~~text
jms-idempotent-consumer/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── IdempotentConsumerDemo.java
~~~

The `pom.xml` file:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jms-idempotent-consumer</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>6.2.19</spring-framework.version>
        <activemq.version>6.2.6</activemq.version>
        <h2.version>2.3.232</h2.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-broker</artifactId>
            <version>${activemq.version}</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-client</artifactId>
            <version>${activemq.version}</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>${h2.version}</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
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

The `src/main/java/demo/IdempotentConsumerDemo.java` file:

~~~java
package demo;

import java.math.BigDecimal;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageListener;
import jakarta.jms.TextMessage;

import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.broker.BrokerService;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.SimpleMessageListenerContainer;
import org.springframework.transaction.support.TransactionTemplate;

public class IdempotentConsumerDemo {

    public static void main(String[] args) throws Exception {
        // Database shared by the inbox and the business write.
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:idempotent_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        jdbc.execute("""
                CREATE TABLE processed_event (
                    consumer_name VARCHAR(100) NOT NULL,
                    business_key VARCHAR(160) NOT NULL,
                    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (consumer_name, business_key)
                )
                """);

        jdbc.execute("""
                CREATE TABLE payment_ledger (
                    entry_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    payment_id VARCHAR(80) NOT NULL,
                    account_id VARCHAR(80) NOT NULL,
                    amount DECIMAL(19, 2) NOT NULL
                )
                """);

        DataSourceTransactionManager dbTransactionManager =
                new DataSourceTransactionManager(dataSource);

        TransactionTemplate dbTransaction =
                new TransactionTemplate(dbTransactionManager);

        PaymentService paymentService =
                new PaymentService(jdbc, dbTransaction);

        BrokerService broker = new BrokerService();
        broker.setBrokerName("idempotent-jms-demo");
        broker.setPersistent(false);
        broker.setUseJmx(false);
        broker.start();
        broker.waitUntilStarted();

        ActiveMQConnectionFactory connectionFactory =
                new ActiveMQConnectionFactory(
                        "vm://idempotent-jms-demo?create=false"
                );

        SimpleMessageListenerContainer container =
                new SimpleMessageListenerContainer();

        CountDownLatch handled = new CountDownLatch(2);

        try {
            container.setConnectionFactory(connectionFactory);
            container.setDestinationName("payments.idempotent.demo");
            container.setConcurrentConsumers(1);

            // JMS receipt + listener execution use a local JMS transaction.
            container.setSessionTransacted(true);

            container.setMessageListener((MessageListener) message -> {
                try {
                    String body = ((TextMessage) message).getText();
                    String[] fields = body.split("\\|", -1);

                    if (fields.length != 3) {
                        throw new IllegalArgumentException(
                                "Expected paymentId|accountId|amount"
                        );
                    }

                    Payment payment = new Payment(
                            fields[0],
                            fields[1],
                            new BigDecimal(fields[2])
                    );

                    boolean applied = paymentService.apply(payment);

                    System.out.println(
                            "result=" + (applied ? "APPLIED" : "DUPLICATE")
                                    + " businessKey=" + payment.paymentId()
                    );

                    handled.countDown();
                }
                catch (JMSException ex) {
                    throw new IllegalStateException(
                            "Cannot read payment message",
                            ex
                    );
                }
            });

            container.afterPropertiesSet();
            container.start();

            JmsTemplate sender = new JmsTemplate(connectionFactory);

            // Two separate JMS messages but the same business operation.
            String event = "payment-1001|account-7|125.00";
            sender.convertAndSend("payments.idempotent.demo", event);
            sender.convertAndSend("payments.idempotent.demo", event);

            if (!handled.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for both messages"
                );
            }
        }
        finally {
            container.stop();
            container.destroy();
            broker.stop();
            broker.waitUntilStopped();
        }

        Integer ledgerRows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM payment_ledger",
                Integer.class
        );

        BigDecimal ledgerTotal = jdbc.queryForObject(
                "SELECT COALESCE(SUM(amount), 0) FROM payment_ledger",
                BigDecimal.class
        );

        System.out.println("paymentLedgerRows=" + ledgerRows);
        System.out.println(
                "paymentLedgerTotal=" + ledgerTotal.setScale(2).toPlainString()
        );
    }

    private record Payment(
            String paymentId,
            String accountId,
            BigDecimal amount) {
    }

    private static class PaymentService {

        private static final String CONSUMER_NAME = "payment-ledger";

        private final JdbcTemplate jdbc;
        private final TransactionTemplate transaction;

        private PaymentService(
                JdbcTemplate jdbc,
                TransactionTemplate transaction) {
            this.jdbc = jdbc;
            this.transaction = transaction;
        }

        boolean apply(Payment payment) {
            try {
                transaction.executeWithoutResult(status -> {
                    // Unique constraint atomically claims the business key.
                    jdbc.update("""
                            INSERT INTO processed_event (
                                consumer_name,
                                business_key
                            ) VALUES (?, ?)
                            """,
                            CONSUMER_NAME,
                            payment.paymentId()
                    );

                    // The side effect is in the same DB transaction as the inbox row.
                    jdbc.update("""
                            INSERT INTO payment_ledger (
                                payment_id,
                                account_id,
                                amount
                            ) VALUES (?, ?, ?)
                            """,
                            payment.paymentId(),
                            payment.accountId(),
                            payment.amount()
                    );
                });

                return true;
            }
            catch (DuplicateKeyException duplicate) {
                // The transaction has already rolled back before the DuplicateKeyException
                // is caught outside the TransactionTemplate.
                return false;
            }
        }
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=demo.IdempotentConsumerDemo
~~~

The stdout produced by the program:

~~~text
result=APPLIED businessKey=payment-1001
result=DUPLICATE businessKey=payment-1001
paymentLedgerRows=1
paymentLedgerTotal=125.00
~~~

Explanation:

1. Two JMS messages are sent separately, but both carry `paymentId=payment-1001`.
2. The listener calls `PaymentService.apply()`.
3. The first transaction inserts `payment-ledger / payment-1001` into `processed_event`, then writes one row to `payment_ledger`.
4. The second transaction violates the primary key of `processed_event`. Spring translates the error into `DuplicateKeyException`; the transaction rolls back before the service returns `false`.
5. The listener treats the duplicate as an already-processed result, returns normally, and the JMS transaction acknowledges the second message.
6. The database has only one ledger row, and the total amount remains 125.00.

The example uses in-memory H2 and a non-persistent broker to focus on the idempotency algorithm. In production, use a durable database, a connection pool, broker persistence, security, schema migration, and a suitable redelivery/DLQ policy.

## 8. Using @Transactional in a Spring application

In a real Spring application, you can split the listener and the business service into two beans. The service uses a database transaction; the listener container uses a local JMS transaction.

Service:

~~~java
@Service
public class PaymentService {

    private final JdbcTemplate jdbc;

    public PaymentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(transactionManager = "transactionManager")
    public void apply(PaymentEvent event) {
        jdbc.update("""
                INSERT INTO processed_event(consumer_name, business_key)
                VALUES (?, ?)
                """,
                "payment-ledger",
                event.paymentId()
        );

        jdbc.update("""
                INSERT INTO payment_ledger(payment_id, account_id, amount)
                VALUES (?, ?, ?)
                """,
                event.paymentId(),
                event.accountId(),
                event.amount()
        );
    }
}
~~~

The listener catches the duplicate outside the transaction proxy:

~~~java
@Component
public class PaymentListener {

    private final PaymentService paymentService;

    public PaymentListener(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @JmsListener(destination = "payments.queue")
    public void receive(PaymentEvent event) {
        try {
            paymentService.apply(event);
        }
        catch (DuplicateKeyException duplicate) {
            // The DB transaction in the service has already rolled back.
            // Return normally so the JMS container acknowledges the duplicate.
            log.info("Duplicate payment ignored: {}", event.paymentId());
        }
    }
}
~~~

Listener container configuration:

~~~java
@Bean
public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-5");

    return factory;
}
~~~

Database transaction manager configuration:

~~~java
@Bean
public PlatformTransactionManager transactionManager(DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}
~~~

Points to note:

- `PaymentService` must be a separate bean invoked through the Spring proxy; self-invocation within the same bean may bypass the transactional proxy.
- Catch `DuplicateKeyException` outside the transactional method so the transaction has fully rolled back before the listener returns normally.
- If the exception is not a duplicate but a database/network error, let it escape the listener so the JMS transaction rolls back and the broker can redeliver.
- Do not swallow all exceptions and return normally; the container may then commit the message even though business processing failed.
- If there are multiple transaction managers, specify the manager name for `@Transactional`.

## 9. Handling multiple consumers and multiple instances

The unique constraint must live in a data store shared among the instances.

Suppose two instances receive the same business event almost simultaneously:

~~~text
Instance A                    Database                    Instance B
    |                            |                            |
    |---- INSERT key ----------->|<----------- INSERT key ----|
    |                            |                            |
    |                     unique constraint                   |
    |                            |                            |
    |<--- INSERT succeeds -------|------ duplicate error ---->|
    |                            |                            |
    |---- business write ------->|                            |
    |---- COMMIT --------------->|                            |
    |                            |<---- ROLLBACK -------------|
~~~

The database ensures only one transaction claims the key. The other instance receives a duplicate key and skips the side effect.

Do not rely on:

- `synchronized` within one JVM.
- A local `ConcurrentHashMap` or `HashSet`.
- A SELECT before the INSERT.
- A lock that exists only in the memory of one node.

If you use Redis or Spring Integration's `ConcurrentMetadataStore`, you need to use an atomic put-if-absent operation or the corresponding selector. However, if the metadata store and the business database are two different systems, there is still a failure window between marking the key and the business commit. For a side effect in the database, an inbox row in the same DB transaction is usually the easiest to guarantee.

## 10. Payload conflict: same key but different content

A dangerous case is the same business key with different payloads.

Example:

~~~text
paymentId=payment-1001, amount=125.00
paymentId=payment-1001, amount=950.00
~~~

You should not automatically treat the second message as a legitimate duplicate. It could be:

- A producer bug creating two contents for the same operation.
- An event that was modified after being published.
- A key collision because the business key design does not have a sufficient scope.
- A forged message or corrupted data.

You can additionally store a `payload_hash`, event type, and schema version in the inbox table:

~~~sql
ALTER TABLE processed_event
    ADD COLUMN payload_hash VARCHAR(128);
~~~

When you encounter a key that already exists:

1. Read the stored hash.
2. Compare it with the hash of the new payload.
3. If they are the same, treat it as a duplicate of the same content.
4. If they differ, raise an alert, write an audit record, and move the message to quarantine/DLQ per policy.
5. Do not silently skip a business conflict.

The hash should be generated from a stable representation (canonical serialization), not from arbitrary JSON bytes if the field order or whitespace can change while the business content does not.

## 11. Retention and replay

The inbox table can grow continuously. Deleting keys must be based on how long the system may still receive the event again.

Retention must be longer than:

- The broker redelivery window.
- The producer's retries.
- The time a message sits in the DLQ.
- The time operations allows replay.
- The time events are kept in the event archive.
- The retry windows of external systems.

If you delete keys too early, an old message that is replayed can become a new side effect.

Options:

- Keep keys long-term for business operations that may be performed only once, such as payment capture or refund.
- Keep keys per a retention policy agreed with the producer, broker, and DLQ.
- Use month/day partitions when the event volume is large, but ensure partition retention does not wrongly delete keys still within the replay window.
- Use a business table unique key as evidence of processing if the business record exists for the whole lifecycle that needs protection.

Do not use a short default TTL merely to limit the size of the inbox. The dedupe period is part of the reliability contract.

## 12. Side effects outside the database

A database transaction cannot by itself roll back an HTTP request that has already succeeded in another system.

Example:

~~~text
BEGIN DB TX
  INSERT inbox key
  call Payment Provider
  provider has charged successfully
  DB transaction rollback
END
~~~

When the message is redelivered, the consumer may charge again. Writing the inbox key in the DB is not enough to protect a side effect that lies outside that transaction.

Ways to handle it:

### The provider's idempotency key

Send the business key to the external API if the provider supports it:

~~~http
Idempotency-Key: payment-1001
~~~

The provider stores the key and returns the result of the old operation when it receives the same key again. You need to read the provider's contract on scope, retention, and behavior when the payload changes.

### Transactional Outbox

If you need to publish an event after updating the database:

1. Update the business tables.
2. Insert an outbox row in the same DB transaction.
3. Commit.
4. The relay reads the outbox and publishes the JMS message.
5. The relay marks it as published after sending successfully.

If the relay crashes after publishing but before marking, it may republish. The consumer still needs an idempotency key.

### Inbox + Outbox

Combine inbox and outbox to create a processing chain:

- The inbox prevents one input event from causing a DB side effect twice.
- The outbox ensures the output event is stored together with the business update.
- The next consumer uses its own inbox to dedupe the output event.

This is a common way to build event-driven workflows without needing a distributed transaction for every service.

## 13. Spring Integration IdempotentReceiverInterceptor and MetadataStore

If a message goes through a Spring Integration flow, you can use `IdempotentReceiverInterceptor` to support the Enterprise Integration Pattern Idempotent Receiver.

The interceptor is an AOP Advice applied to `MessageHandler.handleMessage()`. It uses a `MessageSelector` or `MetadataStoreSelector` to decide whether a message has already been processed. When it is deemed a duplicate, the interceptor can:

- Mark the header `duplicateMessage=true` so the handler decides how to handle it.
- Route the message to `discardChannel`.
- Throw an exception if `throwExceptionOnRejection` is configured.

Java configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;

@Bean
public IdempotentReceiverInterceptor idempotentReceiverInterceptor(
        ConcurrentMetadataStore metadataStore) {

    return new IdempotentReceiverInterceptor(
            new MetadataStoreSelector(
                    message -> (String) message.getHeaders().get("businessKey"),
                    message -> "processed",
                    metadataStore
            )
    );
}
~~~

Then attach the interceptor to the Spring Integration endpoint with `@IdempotentReceiver` or an endpoint advice configuration.

### Choosing the right MetadataStore

Spring Integration has several implementations:

- `SimpleMetadataStore`: stored in memory, does not keep state across restarts.
- `PropertiesPersistingMetadataStore`: stored in a properties file; by default flushes when the application context closes normally.
- `JdbcMetadataStore`: stored in a database.
- Redis, MongoDB, Hazelcast, and other implementations.

If you run multiple instances, you need a `ConcurrentMetadataStore` with atomic operations. Do not use an in-memory metadata store as the sole dedupe source in production.

`IdempotentReceiverInterceptor` helps filter and mark duplicates, but the application must still design the business key, retention, and transactions correctly. If the metadata store is not in the same transaction as the business database, account for the failure window between the two places. For an important side effect in the same database, a unique inbox table and the business write in the same transaction is usually the easier choice to control.

See [Spring Integration: Idempotent Receiver](https://docs.spring.io/spring-integration/reference/6.5/handler-advice/idempotent-receiver.html) and [Metadata Store](https://docs.spring.io/spring-integration/reference/6.5/meta-data-store.html).

## 14. Redelivery limit, poison message, and DLQ

Idempotency protects against a message being processed successfully multiple times. It does not solve messages that cannot be processed because of bad data or permanent errors.

You need to classify:

- **Transient failure:** the database temporarily loses its connection, an external service times out. You can retry with backoff.
- **Permanent business failure:** data is missing or violates a business rule. You can move to rejection/quarantine.
- **Poison message:** always makes the listener fail, causing the broker to redeliver indefinitely if there is no limit.
- **Duplicate:** the business key has already been processed with the same payload. Typically record the duplicate and complete the listener normally.

Configure the broker redelivery policy with:

- The maximum number of attempts.
- The delay/backoff between attempts.
- A dead-letter queue (DLQ).
- A procedure for investigating and replaying the DLQ.
- Metrics for redelivery count and message age.

Do not use `JMSXDeliveryCount` as the business key or as the sole condition for skipping a message. Use it to observe retries and detect poison messages.

When replaying from the DLQ, keep the original business key. If you change the key during replay, the system will treat it as a new operation.

## 15. Common mistakes

1. **Using JMSMessageID as the idempotency key.** A producer resending the same event may create a new JMSMessageID. Use a stable business key in the payload/property.
2. **Deduplicating only when JMSRedelivered=true.** The producer can republish the event as a new message with the flag false.
3. **Using orderId for every operation.** One order can have multiple payments, refunds, or invoices. Choose a key that represents the right operation.
4. **Using check-then-insert.** Two concurrent consumers can both see that the key does not exist. Use a unique constraint and insert-first.
5. **Using an in-memory Set as the source of truth.** It is lost on restart and not synchronized across instances.
6. **Writing the inbox and business data in two separate transactions.** A crash between the two commits can lose the side effect or apply it twice.
7. **Writing the inbox before the side effect and committing separately.** If the process stops after marking, a replayed message is skipped even though the business work never ran.
8. **Writing the business data first and marking separately.** If the process stops between the two steps, the redelivery may repeat the side effect.
9. **Catching every exception and returning normally.** The JMS container may commit the message even though business processing failed. Only treat a confirmed duplicate as a successful result.
10. **Using one key for consumers with independent side effects.** Scope by consumer/operation so each consumer can process once.
11. **Skipping the same key with a different payload.** Compare the payload hash or event version and put the conflict into quarantine.
12. **Deleting inbox keys too early.** A replay from the DLQ or a producer retry can create a new side effect.
13. **Assuming the JMS transaction automatically includes the database.** The local JMS transaction and local DB transaction are independent; use the inbox pattern or XA/JTA.
14. **Calling an external API and relying only on the DB inbox.** Use the provider's idempotency key or a transactional outbox/saga.
15. **Assuming idempotency means end-to-end exactly-once.** Each side-effect boundary needs its own mechanism; delivery can still repeat.
16. **Ignoring concurrency.** Configuring multiple listener threads requires a shared database unique constraint or atomic store.
17. **Replaying the DLQ with a new business key.** Loses the ability to recognize an operation that has already been processed.
18. **Not testing the crash window.** Test failures before the DB commit, after the DB commit but before the JMS commit, and failures when publishing the output event.

## 16. Idempotent consumer design checklist

- [ ] Determine exactly which business operation needs protection.
- [ ] Choose a stable business key that does not depend on the JMS transport ID.
- [ ] Determine the scope by consumer, tenant, event type, or aggregate version.
- [ ] Put the business key into the payload or a JMS property under a clear contract.
- [ ] Create an inbox table with a unique constraint.
- [ ] Use insert-first instead of SELECT then INSERT.
- [ ] Write the inbox key and the business side effect in the same DB transaction.
- [ ] Catch the duplicate key outside the transaction that has rolled back.
- [ ] Only treat a duplicate as success if the payload/key is consistent.
- [ ] Enable `sessionTransacted=true` or a suitable transaction strategy for the listener container.
- [ ] Let transient errors escape the listener so JMS rolls back/redelivers.
- [ ] Design the listener to be idempotent when multiple consumer instances run in parallel.
- [ ] Keep keys long enough for redelivery, retry, and DLQ replay.
- [ ] Use the provider's idempotency key or an outbox for side effects outside the DB.
- [ ] Configure the redelivery limit, backoff, and DLQ.
- [ ] Monitor duplicate count, redelivery count, payload conflicts, and DLQ handling.
- [ ] Test restart, concurrent duplicates, DB rollback, and failure between the DB/JMS commits.

## 17. Conclusion

Idempotent processing with a business key is an important layer of protection for a JMS consumer under the at-least-once model. Choose a key that represents the right business operation, record the key in an inbox table with a unique constraint, and perform the inbox insert together with the business write in one database transaction. Combined with a JMS local transaction, this handles the case where the DB commit succeeds but the JMS acknowledgement has not completed: the message may be redelivered but the side effect is not repeated. `JMSRedelivered` and `JMSXDeliveryCount` help observe retries; they do not replace the business key. For side effects outside the database, use the provider's idempotency contract, outbox/inbox, or XA/JTA depending on the consistency requirements.

## Official references

- [Spring Framework 6.2.19 Javadoc: AbstractMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html) — sessionTransacted, duplicate message detection, DB/JMS transaction boundary, and XA/JTA.
- [Spring Framework 6.2 Reference: Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html) — listener container, local JMS transaction, and redelivery when a listener fails.
- [Spring Framework 6.2.19 Javadoc: DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html) — transaction manager, concurrency, acknowledgement, and container behavior.
- [Jakarta Messaging 3.1 Specification, §3.4.7, §3.5.11, §6.2.11](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.pdf) — JMSRedelivered, JMSXDeliveryCount, acknowledgement, and duplicate delivery.
- [Spring Integration 6.5 Reference: Idempotent Receiver](https://docs.spring.io/spring-integration/reference/6.5/handler-advice/idempotent-receiver.html) — IdempotentReceiverInterceptor, MetadataStoreSelector, duplicate header, and discard behavior.
- [Spring Integration 6.5 Reference: Metadata Store](https://docs.spring.io/spring-integration/reference/6.5/meta-data-store.html) — persistent MetadataStore implementations, ConcurrentMetadataStore, and retention.
