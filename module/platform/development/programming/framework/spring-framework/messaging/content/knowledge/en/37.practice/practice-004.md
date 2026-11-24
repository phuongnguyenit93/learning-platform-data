# Experimenting with Durable Topics and Duplicate Message Handling

## Objectives

In the publish/subscribe model, a publisher sends an event to a Topic and multiple independent subscribers can receive the same event. If a subscriber pauses or the application restarts, an ordinary subscriber may miss messages sent while offline. When the system recovers, the broker can also redeliver a message whose business processing succeeded on the consumer, but whose acknowledgement did not complete.

This lab uses Spring JMS, Jakarta Messaging, and ActiveMQ Artemis to build a durable topic subscription, send persistent messages, and handle duplicate delivery with idempotency. Result storage uses PostgreSQL to illustrate how to combine business transactions with broker acknowledgement.

After this lesson, you will be able to:

- Distinguish between a Topic, non-durable subscriptions, and durable subscriptions.
- Distinguish persistent delivery mode from durable subscriptions.
- Configure a Spring JMS publisher and listener for a Topic.
- Keep a subscription stable across restarts.
- Detect redeliveries using JMSRedelivered and JMSXDeliveryCount.
- Prevent duplicate processing using an event ID and a database unique constraint.
- Understand the failure window between database commit and JMS acknowledgement.
- Test offline subscribers, duplicate messages, rollbacks, and dead-letter queues.

The examples use Java 17+, Spring Boot 4.x, Spring Framework 7.x, Jakarta Messaging, and ActiveMQ Artemis. JMS types use the `jakarta.jms` package.

## 1. Understanding Topics and Durable Subscriptions

A Topic is a publish/subscribe destination. A publisher sends a message to a Topic; each matching subscription can receive its own copy of the message. A subscriber does not consume messages from a Topic in the usual queue competing-consumer manner. The broker manages delivery per subscription.

### 1.1. Non-Durable Subscription

A non-durable subscription typically exists only while the subscriber is active. When the consumer disconnects, messages published during that time are generally not retained for the subscriber. When the consumer reconnects, it resumes receiving new messages.

This approach fits update data that can be missed, such as presence signals or certain UI notifications. It is not suitable if the subscriber must receive every event even when the service is offline.

### 1.2. Durable Subscription

A durable subscription has a stable name and client identifier. The broker retains messages destined for the subscription while the consumer is temporarily offline, then delivers non-expired messages when the subscriber reconnects.

With Jakarta Messaging, a durable subscription is identified by a client ID and a subscription name. The subscription name must be unique within the scope of the client ID. Both values need to remain stable across restarts of the same logical subscriber.

Example:

- Topic: inventory.events
- Client ID: inventory-projection-client
- Subscription name: inventory-projection-v1

When the application restarts with the same client ID and subscription name, it resumes the registered subscription. If you change the name or client ID, the broker may treat it as a different subscription; the old subscription's backlog does not automatically transfer to the new subscription.

**Note:** the durable subscription must be created before the messages to be retained are published. If no durable subscriber has registered yet, old messages are not automatically replayed to a subscription created later.

### 1.3. Persistent Messages and Durable Subscriptions Are Two Different Mechanisms

Two concepts are often confused:

| Mechanism | What does it protect? | What does it NOT guarantee by itself? |
|---|---|---|
| DeliveryMode.PERSISTENT | Requests the broker to store messages durably upon sending, subject to broker capability and configuration. | Does not automatically create a backlog for a non-durable subscriber. |
| Durable subscription | Retains messages for the subscription while the subscriber is offline. | Does not automatically make non-persistent messages persistent. |
| Session transaction / acknowledgement | Determines when the broker considers a message successfully processed by the consumer. | Does not automatically combine database side effects and JMS acknowledgement into a single transaction. |
| Application-level idempotency | Prevents the same event from applying business side effects multiple times. | Does not replace broker persistence, retention, or retry policies. |

For an offline subscriber to receive missed events, you usually need both messages sent with PERSISTENT mode and a subscriber with a durable subscription. The broker must also be configured with appropriate persistence, quotas, and retention. Messages can expire according to TTL or be affected by storage policies when the broker runs out of space.

## 2. Redelivery and Duplicate Messages

Duplicates can occur in several situations:

1. The consumer receives a message and runs business processing.
2. The database commits successfully.
3. The consumer or broker encounters an error before the JMS session commits the acknowledgement.
4. The broker has not received confirmation, so it redelivers the message.

On the second delivery, the database side effect may have already happened from the first attempt. If the listener repeats the operation without idempotency, data will be updated twice.

Another situation happens on the publisher side: the application sends a persistent message but loses the connection before learning the send outcome. The publisher may resend the same event. The resend can produce a new JMSMessageID even though it is still the same business event.

Therefore, distinguish between:

- **JMSMessageID:** provider-generated ID for a specific message; useful for tracing broker activity and redeliveries.
- **Business event ID:** application-generated stable ID for a business event; used to deduplicate even when the publisher resends a message.
- **JMSRedelivered:** flag indicating the provider is redelivering the message.
- **JMSXDeliveryCount:** delivery count reported by the provider, if the provider supplies this property.

Do not use JMSMessageID as the sole idempotency key. If the publisher resends the same event in a new send call, the provider may assign a different ID. The business event ID must remain unchanged across all retries of the same event.

### 2.1. At-Least-Once and Idempotent Consumers

With durable subscriptions and transacted listeners, applications usually design consumers so they can safely receive unacknowledged messages again. That is why consumers must be safe when processing the same event multiple times.

An idempotent consumer guarantees that if the same event ID arrives multiple times, the business side effect is applied only once. Subsequent deliveries read back the stored outcome and acknowledge the message without executing the side effect again.

Do not promise exactly-once simply because persistent delivery or durable subscriptions are enabled. Business-level exactly-once requires coordinating the broker, transactions, database, publisher, and consumer. The common pattern is repeatable delivery combined with idempotent processing.

## 3. Preparing the Spring Boot Project and Broker

The example uses ActiveMQ Artemis as the JMS provider and PostgreSQL as the store for processing state.

### 3.1. Dependencies

In Maven, add the following dependencies; versions are managed by Spring Boot dependency management:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-artemis</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-jackson2</artifactId>
    </dependency>

    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

**Note on Jackson in Spring Boot 4:** Spring Boot 4 prefers Jackson 3. This lab keeps the Jackson 2 `com.fasterxml.jackson.*` imports to focus on JMS, so the `spring-boot-jackson2` module is needed for Spring Boot to auto-configure a compatible `ObjectMapper` bean. This module is deprecated and should only be used as a transition step; for new projects, prefer Jackson 3 (`tools.jackson.*`) and `JsonMapper`.

The Spring Boot Artemis starter provides JMS integration and a ConnectionFactory for Artemis. Spring Boot can also auto-configure JmsTemplate and the listener infrastructure. This example defines dedicated beans for the Topic to clarify delivery mode and durable subscriptions.

### 3.2. Connection Configuration

In application.properties:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=your-artemis-user
spring.artemis.password=your-artemis-password

spring.datasource.url=jdbc:postgresql://localhost:5432/inventory
spring.datasource.username=your-database-user
spring.datasource.password=your-database-password
~~~

The credentials above are placeholders. In production, inject them via environment variables or a secret manager; do not commit real passwords to the repository.

The broker needs persistent storage enabled and permission to create or manage Topics/destinations according to environment policies. In production, provision destinations, storage quotas, expiration, redelivery, and dead-letter addresses via broker configuration instead of relying on auto-create.

### 3.3. Enabling JMS Listeners

In the application class:

~~~java
package com.example.inventory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class InventoryMessagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            InventoryMessagingApplication.class,
            args
        );
    }
}
~~~

In Spring Boot, JMS listener infrastructure can be auto-configured when a JMS provider and listener annotations are present. `@EnableJms` is placed explicitly here to illustrate enabling annotation-driven listeners in the example.

## 4. Creating a Publisher Sending Persistent Messages to a Topic

### 4.1. Event Payload

Create InventoryEvent.java:

~~~java
package com.example.inventory.contract;

public record InventoryEvent(
    String eventId,
    String sku,
    int quantity
) {}
~~~

eventId is a stable business identifier. The publisher must generate eventId once when creating the event and reuse the exact same ID when retrying the send of that event.

Do not generate a new UUID every time publish() is called for the same event. Doing so prevents the consumer from recognizing resends as the same operation.

### 4.2. Configuring JmsTemplate for a Topic

Create InventoryTopicConfiguration.java:

~~~java
package com.example.inventory.config;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;

import java.time.Duration;

import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.boot.jms.autoconfigure.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
public class InventoryTopicConfiguration {

    @Bean
    public JmsTemplate inventoryTopicTemplate(
        ConnectionFactory connectionFactory
    ) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(true);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setTimeToLive(Duration.ofDays(7).toMillis());
        return template;
    }

    @Bean
    public DefaultJmsListenerContainerFactory
            inventoryDurableTopicFactory(
                ConnectionFactory connectionFactory,
                DefaultJmsListenerContainerFactoryConfigurer configurer
            ) {

        DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

        configurer.configure(
            factory,
            ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory)
        );

        factory.setPubSubDomain(true);
        factory.setClientId("inventory-projection-client");
        factory.setSubscriptionDurable(true);
        factory.setSubscriptionName("inventory-projection-v1");
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");

        return factory;
    }
}
~~~

Key settings:

- pubSubDomain=true: destination name is treated as a Topic instead of a Queue.
- explicitQosEnabled=true: instructs JmsTemplate to use the configured QoS values.
- DeliveryMode.PERSISTENT: requests the broker to store messages durably per provider configuration.
- timeToLive: limits how long messages remain valid; seven days in this example.
- clientId and subscriptionName: identify a stable durable subscription.
- subscriptionDurable=true: registers a durable topic subscription.
- sessionTransacted=true: the listener session commits when the listener succeeds and rolls back when the listener throws an error.
- concurrency=1: uses a single consumer for the non-shared durable subscription in this example.

ConnectionFactoryUnwrapper.unwrapCaching allows the listener container to use the native ConnectionFactory instead of the caching wrapper configured by Spring Boot for regular JMS operations. This lets the listener container manage connections and recovery itself. The Boot configurer package may differ across major versions; use the package matching your project's Spring Boot BOM.

A standard durable subscription allows only one active consumer at a time. Do not arbitrarily increase concurrency or run multiple instances with the same client ID.

The seven-day TTL is only an example. Choose the duration based on the maximum consumer offline window and your system's data policy. Persistent messages still expire when their TTL elapses.

### 4.3. Publisher Sending TextMessage

Create InventoryEventPublisher.java:

~~~java
package com.example.inventory.messaging;

import com.example.inventory.contract.InventoryEvent;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.jms.TextMessage;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MessageConversionException;
import org.springframework.stereotype.Component;

@Component
public class InventoryEventPublisher {

    private final JmsTemplate topicTemplate;
    private final ObjectMapper objectMapper;

    public InventoryEventPublisher(
        @Qualifier("inventoryTopicTemplate")
        JmsTemplate topicTemplate,
        ObjectMapper objectMapper
    ) {
        this.topicTemplate = topicTemplate;
        this.objectMapper = objectMapper;
    }

    public void publish(InventoryEvent event) {
        final String body;

        try {
            body = objectMapper.writeValueAsString(event);
        }
        catch (JsonProcessingException ex) {
            throw new MessageConversionException(
                "Cannot serialize inventory event",
                ex
            );
        }

        topicTemplate.send("inventory.events", session -> {
            TextMessage message = session.createTextMessage(body);
            message.setStringProperty("eventId", event.eventId());
            return message;
        });
    }
}
~~~

The publisher sends JSON inside a TextMessage. eventId is also set as a message property so broker selectors or observability tools can use it, though the consumer still reads eventId from the payload and checks idempotency in the database.

JmsTemplate uses the delivery mode configured on the bean. Without explicitQosEnabled, delivery mode/priority/TTL values set on the template might not take effect as expected.

JMSMessageID is assigned by the broker after sending. It is useful for logs and investigations, but does not replace eventId.

## 5. Creating a Durable Topic Listener

### 5.1. Database Schema to Prevent Duplicate Processing

Create the inventory and processed_event tables. The SQL example below targets PostgreSQL:

~~~sql
CREATE TABLE inventory (
    sku VARCHAR(80) PRIMARY KEY,
    quantity BIGINT NOT NULL CHECK (quantity >= 0)
);

CREATE TABLE processed_event (
    event_id VARCHAR(128) PRIMARY KEY,
    payload_hash CHAR(64) NOT NULL,
    outcome VARCHAR(40) NOT NULL,
    jms_message_id VARCHAR(255),
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

processed_event stores one row per processed business event. The unique primary key on event_id acts as the barrier preventing two consumers from applying the same event multiple times.

payload_hash helps detect cases where a producer accidentally reuses an eventId for a different payload. If eventId already exists but the hash mismatches, that is a contract or ID-generation bug; never silently treat the new message as a valid duplicate.

### 5.2. Idempotent Processing Service

Create InventoryEventService.java:

~~~java
package com.example.inventory.service;

import com.example.inventory.contract.InventoryEvent;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryEventService {

    private final JdbcTemplate jdbcTemplate;

    public InventoryEventService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public ApplyResult applyOnce(
        InventoryEvent event,
        String jmsMessageId
    ) {
        validate(event);
        String hash = payloadHash(event);

        int inserted = jdbcTemplate.update("""
            INSERT INTO processed_event (
                event_id,
                payload_hash,
                outcome,
                jms_message_id,
                processed_at
            )
            VALUES (?, ?, 'PROCESSING', ?, CURRENT_TIMESTAMP)
            ON CONFLICT (event_id) DO NOTHING
            """,
            event.eventId(),
            hash,
            jmsMessageId
        );

        if (inserted == 0) {
            StoredEvent stored = jdbcTemplate.queryForObject(
                """
                SELECT payload_hash, outcome
                FROM processed_event
                WHERE event_id = ?
                """,
                (rs, rowNum) -> new StoredEvent(
                    rs.getString("payload_hash"),
                    rs.getString("outcome")
                ),
                event.eventId()
            );

            if (!stored.payloadHash().equals(hash)) {
                throw new EventIdCollisionException(
                    "eventId was reused with a different payload"
                );
            }

            return new ApplyResult(stored.outcome(), true);
        }

        int updated = jdbcTemplate.update(
            """
            UPDATE inventory
            SET quantity = quantity + ?
            WHERE sku = ?
            """,
            event.quantity(),
            event.sku()
        );

        String outcome = updated == 1
            ? "APPLIED"
            : "REJECTED_UNKNOWN_SKU";

        jdbcTemplate.update(
            """
            UPDATE processed_event
            SET outcome = ?
            WHERE event_id = ?
            """,
            outcome,
            event.eventId()
        );

        return new ApplyResult(outcome, false);
    }

    private void validate(InventoryEvent event) {
        if (event == null
                || event.eventId() == null
                || event.eventId().isBlank()
                || event.sku() == null
                || event.sku().isBlank()
                || event.quantity() <= 0) {
            throw new IllegalArgumentException(
                "Invalid inventory event"
            );
        }
    }

    private String payloadHash(InventoryEvent event) {
        String canonical = event.eventId()
            + "\n" + event.sku()
            + "\n" + event.quantity();

        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(canonical.getBytes(StandardCharsets.UTF_8));

            return HexFormat.of().formatHex(digest);
        }
        catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                "SHA-256 is unavailable",
                ex
            );
        }
    }

    private record StoredEvent(
        String payloadHash,
        String outcome
    ) {}

    public record ApplyResult(
        String outcome,
        boolean duplicate
    ) {}

    public static class EventIdCollisionException
            extends RuntimeException {

        public EventIdCollisionException(String message) {
            super(message);
        }
    }
}
~~~

Flow inside applyOnce():

1. Validate the event and compute a hash from its business content.
2. Insert eventId into processed_event.
3. If eventId already exists, read the stored outcome.
4. If the payload hash differs, raise a collision error so the message is handled per permanent-error/DLQ policy.
5. If the hash matches, return the previous outcome and mark duplicate=true.
6. If this is a new event, update inventory.
7. Record outcome APPLIED or REJECTED_UNKNOWN_SKU.
8. Commit the database transaction.

The INSERT ... ON CONFLICT statement uses PostgreSQL syntax. For MySQL, SQL Server, Oracle, or other databases, use a unique constraint and the corresponding insert-if-absent/upsert statement. Do not omit the unique constraint, because checking with SELECT first and then inserting can suffer from a race condition when two messages arrive concurrently.

The inventory update side effect and the processed_event record live in the same database transaction. If the database update fails, both changes roll back; redelivery can retry processing. If the transaction commits, the next delivery sees eventId already present and does not update inventory again.

REJECTED_UNKNOWN_SKU is a persisted business outcome. The listener can acknowledge the message after the rejection outcome has committed. For transient technical errors, the service must throw an exception so the transaction rolls back and the broker can redeliver.

### 5.3. Listener Receiving TextMessage

Create InventoryTopicListener.java:

~~~java
package com.example.inventory.messaging;

import com.example.inventory.contract.InventoryEvent;
import com.example.inventory.service.InventoryEventService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageFormatException;
import jakarta.jms.TextMessage;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.support.converter.MessageConversionException;
import org.springframework.stereotype.Component;

@Component
public class InventoryTopicListener {

    private static final Logger log =
        LoggerFactory.getLogger(InventoryTopicListener.class);

    private final ObjectMapper objectMapper;
    private final InventoryEventService service;

    public InventoryTopicListener(
        ObjectMapper objectMapper,
        InventoryEventService service
    ) {
        this.objectMapper = objectMapper;
        this.service = service;
    }

    @JmsListener(
        destination = "inventory.events",
        containerFactory = "inventoryDurableTopicFactory"
    )
    public void receive(Message message) throws JMSException {
        if (!(message instanceof TextMessage textMessage)) {
            throw new MessageFormatException(
                "Expected a TextMessage"
            );
        }

        final InventoryEvent event;

        try {
            event = objectMapper.readValue(
                textMessage.getText(),
                InventoryEvent.class
            );
        }
        catch (JsonProcessingException ex) {
            throw new MessageConversionException(
                "Invalid inventory event JSON",
                ex
            );
        }

        boolean redelivered = message.getJMSRedelivered();
        int deliveryCount = message.propertyExists("JMSXDeliveryCount")
            ? message.getIntProperty("JMSXDeliveryCount")
            : 1;

        InventoryEventService.ApplyResult result =
            service.applyOnce(event, message.getJMSMessageID());

        log.info(
            "eventId={} outcome={} duplicate={} redelivered={} " +
            "deliveryCount={} jmsMessageId={}",
            event.eventId(),
            result.outcome(),
            result.duplicate(),
            redelivered,
            deliveryCount,
            message.getJMSMessageID()
        );
    }
}
~~~

The listener does not acknowledge the message itself. Because the listener factory uses sessionTransacted=true:

- Listener returns normally: the container commits the JMS session and the message is acknowledged.
- Listener throws an exception: the container rolls back the JMS session; the broker can redeliver the message per its redelivery policy.
- Listener receives an eventId already in the database: the service returns the prior outcome, the listener finishes normally, and the broker can acknowledge this delivery.

Do not catch and ignore every exception. If the listener swallows a database error and returns normally, the broker considers the message processed and commits the acknowledgement even though the business operation failed.

## 6. Understanding Transactions Between JMS and the Database

The example above has two local transactions:

1. A database transaction managed by `@Transactional` in InventoryEventService.
2. A JMS transaction managed by the listener container via sessionTransacted=true.

When the listener calls the service, the database transaction completes before the listener method returns. Only after that does the listener container commit the JMS session. These two local transactions do not automatically form a single distributed transaction.

### 6.1. Failure Windows

| Failure timing | Possible state | Recovery |
|---|---|---|
| Before database commit | DB rolls back; JMS session rolls back when the listener throws an error. | Broker redelivers the message. |
| After DB commit, before JMS commit | Side effect is persisted; acknowledgement may not be committed. | Broker may redeliver; eventId turns the subsequent attempt into a no-op. |
| After JMS commit | Message has been acknowledged. | No need to redeliver that message for this transaction. |
| Publisher sent successfully without recording send status | Message may already be on the broker while the publisher is unaware. | Publisher can resend; keep the same eventId so the consumer deduplicates. |

If an atomic commit between JMS and the database is required, JTA/XA can be used with an XA-capable ConnectionFactory and a transaction coordinator. This is a more complex option requiring appropriate broker, datasource, transaction manager, and operational configuration. For many systems, local transactions combined with an idempotent consumer and a transactional outbox are easier to control.

### 6.2. Why Not Use AUTO_ACKNOWLEDGE for Critical Processing?

With AUTO_ACKNOWLEDGE, the provider acknowledges automatically according to session rules. If a listener processes side effects and then hits an error or container shutdown in an unfavorable window, the application may not achieve the desired rollback semantics.

Spring Framework recommends using transacted sessions when reliability is needed for listeners, including durable topic subscriptions. Let exceptions propagate to the container when rollback is needed; only turn an error into a normal business outcome once that outcome state has been intentionally persisted.

## 7. Testing Offline Subscribers and Persistent Messages

Follow this sequence to verify durable subscriptions work:

1. Start ActiveMQ Artemis with persistent storage enabled.
2. Start the consumer application for the first time.
3. Verify the listener creates the durable subscription with the configured client ID and subscription name.
4. Stop the consumer or stop the listener container without deleting the durable subscription.
5. While the consumer is offline, have the publisher send one or more messages to inventory.events with DeliveryMode.PERSISTENT.
6. Restart the consumer with the same client ID and subscription name.
7. Verify the consumer receives the non-expired messages retained for the subscription.
8. Inspect the database to confirm each eventId modified inventory only once.

If the durable subscription was never created before publishing, do not expect the broker to retroactively retain old messages for a non-existent subscription.

Do not call unsubscribe or delete the durable subscription during normal restart procedures. Deleting the subscription can discard pending backlogs and prevent the consumer from receiving offline messages.

### 7.1. Testing Duplicates

Send the same payload twice with the same eventId:

~~~json
{
  "eventId": "inventory-receipt-00042",
  "sku": "BOOK-001",
  "quantity": 5
}
~~~

Suppose initial inventory has quantity equal to 10:

- First time: processed_event does not yet contain eventId, inventory increases to 15, and outcome is saved as APPLIED.
- Second time: eventId already exists and the payload hash matches, the service returns duplicate=true; inventory remains 15.

Two fresh publish calls may have two different JMSMessageIDs. This has no impact because deduplication relies on the business eventId.

### 7.2. Testing Redelivery After Rollback

You can create an integration test that forces the database transaction to fail before commit:

1. Publish a new event.
2. Have the service throw an error before the database transaction commits.
3. Verify processed_event and inventory changes both roll back.
4. Verify the JMS session rolls back.
5. Restore the database and let the broker redeliver the message.
6. Verify the redelivery creates one processed_event record and applies the side effect only once.

To test the failure window after DB commit but before JMS commit, use fault injection in an integration test or a broker test environment. After the DB commits, force JMS acknowledgement to fail; when the message is redelivered, verify the service returns duplicate=true and inventory does not increase again.

### 7.3. Testing Misused Event IDs

Send two payloads with the same eventId but different SKUs or quantities. The hashes will differ and the service throws EventIdCollisionException.

This is a producer or contract bug, not a valid duplicate. Configure bounded redelivery policies and a dead-letter queue so permanently failing messages are not redelivered infinitely. Log alerts with eventId, JMSMessageID, and correlation ID for investigation.

## 8. Redelivery Policy and Dead-Letter Queue

A transient error such as database unavailable can be retried. A permanent data error such as malformed JSON or an eventId collision should not be retried infinitely.

The broker should be configured for the following factors:

- Maximum redelivery attempts.
- Delay or backoff between redeliveries.
- Dead-letter address/queue for messages exceeding the limit.
- Retention and alerting for dead-letter messages.
- How to replay messages after the issue is fixed.

Specific redelivery and dead-letter configuration depends on the broker. With Artemis, configure address settings, dead-letter address, max-delivery-attempts, and redelivery-delay according to provider documentation. Do not assume property names or configuration XML from another broker are shared Jakarta Messaging settings.

A consumer should not automatically ack a permanently failing message just to avoid retries. Let the broker route the message to the DLQ after the configured number of deliveries, or implement a quarantine workflow with clear auditing.

When replaying from a DLQ, keep the business event ID intact. If the side effect already committed before the message went to the DLQ, the idempotency store will prevent the replay from altering data again.

## 9. Managing Multiple Subscribers and Scale-Out

A Topic can have multiple independent durable subscriptions. Example:

| Client ID | Subscription name | Consumer | Purpose |
|---|---|---|---|
| inventory-projection-client | inventory-projection-v1 | Inventory projection | Update stock levels |
| audit-service-client | audit-events-v1 | Audit service | Record history |
| notification-client | user-notifications-v1 | Notification service | Send notifications |

Each independent durable subscription receives its own copy of messages. One offline subscriber does not cause other subscribers to lose backlogs as long as the broker retains them and retention policies allow.

If multiple instances need to process the same logical subscription together, consider shared durable subscriptions per Jakarta Messaging 2.0+ and broker support. Spring supports configuring shared subscriptions via subscriptionShared and subscriptionName. Verify broker support for shared durable subscriptions, consumer limits, client IDs, and concurrency before scaling out.

Do not launch multiple instances of the same non-shared durable subscription with the same client ID expecting them to load-balance automatically. A standard durable subscription does not allow competing consumers simultaneously; use a shared subscription or an appropriate queue architecture when competing consumers are required.

If processing order per aggregate is mandatory, high concurrency can cause completion order to differ from receipt order. Carry the aggregate ID and sequence number in the event, then serialize processing per aggregate or use a broker-supported partitioning/ordering mechanism.

## 10. Producer Retries and Transactional Outbox

Consumer idempotency handles duplicate deliveries, but producers also need to avoid losing events when updating a database and sending JMS messages.

A common failure:

1. Update the business database.
2. Send the JMS message.
3. The process crashes between the two steps.

If the database commits but the message was not sent, downstream services never learn that the change occurred. If the message was sent but the application failed to record the send result, the publisher might resend.

The transactional outbox solves dual-write:

1. In the same database transaction as the business change, write an outbox row.
2. A worker reads unpublished outbox rows.
3. The worker sends a persistent JMS message with eventId taken from the outbox.
4. Upon successful send, mark the row as published.
5. If the worker crashes after sending but before marking, the worker can resend the same eventId.
6. Consumers deduplicate using processed_event.

An outbox does not make the broker and database commit in a single transaction. It creates a durable event source so the publisher can retry; consumer idempotency handles cases where the relay resends.

Do not generate a new eventId when the relay retries the same outbox row. The event ID must be created and persisted when writing the outbox row.

## 11. Retention and Operating Durable Subscriptions

Durable subscriptions can accumulate backlogs when consumers go offline. Therefore, monitor:

- Pending message count per subscription.
- Age of the oldest message.
- Publish rate and consume rate.
- Broker storage capacity.
- Expired messages and messages routed to the DLQ.
- Consumer offline duration.
- Duplicate/redelivery count.
- eventId collisions or payload errors.

TTL policies must balance recovery time against storage capacity. If a message expires before the consumer returns, the durable subscription cannot redeliver the expired message.

When permanently decommissioning a subscriber, operators must decide whether to keep the backlog, replay to a new consumer, or delete the subscription. Only unsubscribe after confirming the backlog is no longer needed or has been archived/migrated according to procedure.

processed_event also needs retention. Keep deduplication records for at least the maximum duration a message could be redelivered or replayed. If records are purged too early, an old replayed message could apply its side effect again. With global event IDs, keys can be kept long-term or old keys archived under a queryable policy.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Enabling PERSISTENT only while using a non-durable subscriber | Offline consumers can still miss messages. | Create a durable subscription before publishing. |
| Using a durable subscription while sending NON_PERSISTENT | Messages can be lost during broker failures. | Use DeliveryMode.PERSISTENT and enable broker persistence. |
| Changing client ID or subscription name after restart | Creates a different subscription and misses the old backlog. | Keep identifiers stable across deployments. |
| Using JMSMessageID as the deduplication key | Publisher resending the same event may get a new ID. | Use a stable business event ID. |
| Checking only JMSRedelivered | Fails to detect a publisher resending the same event as a new message. | Deduplicate by eventId in the database. |
| Acking before committing side effects | Messages can be lost if business changes are not yet persisted. | Use transacted listeners and commit business changes before the listener returns. |
| DB commits while JMS commit fails | Broker redelivers and may repeat side effects. | Unique eventId and side effects inside the same DB transaction. |
| Catching and swallowing all exceptions | Broker treats the message as processed even though business logic failed. | Propagate errors that require rollback; classify business outcomes separately. |
| Infinitely retrying malformed messages | A poison message loops continuously. | Bounded redelivery and DLQ. |
| Running multiple consumers on a non-shared durable subscription | Subscription/client conflicts or startup errors. | Use a single consumer or a supported shared durable subscription. |
| Purging processed_event too early | Old replays can re-apply side effects. | Retain dedup records across the replay/retention window. |
| Treating a Topic like a Queue | Misunderstanding that every subscriber gets its own copy. | Choose the right pub/sub or competing-consumer model. |

## 13. Practice Checklist

- [ ] Broker has persistent storage enabled and retention/quotas configured.
- [ ] Topic destination is provisioned or auto-created under an explicit policy.
- [ ] Publisher uses pubSubDomain=true.
- [ ] Publisher enables explicit QoS and DeliveryMode.PERSISTENT.
- [ ] TTL matches the expected maximum consumer offline duration.
- [ ] Durable subscription has a stable client ID and subscription name.
- [ ] Durable subscription is created before needing to retain backlog.
- [ ] Listener uses sessionTransacted=true.
- [ ] Retryable exceptions propagate to the listener container.
- [ ] Every business event has a stable eventId across resends.
- [ ] Database has a unique constraint on eventId.
- [ ] Side effects and processed_event commit within the same DB transaction.
- [ ] Payload hash is checked to detect misused eventIds.
- [ ] JMSRedelivered and JMSXDeliveryCount are logged for observability.
- [ ] Broker has bounded redelivery, backoff, and a DLQ.
- [ ] Tested taking the subscriber offline and restarting with the same identity.
- [ ] Tested sending the same eventId twice and verified the side effect ran only once.
- [ ] Tested DB rollback, JMS redelivery, and the DB commit/JMS ack window.
- [ ] Retention policies are defined for backlogs and processed_event.
- [ ] Evaluated shared durable subscriptions before scaling across multiple instances.

## References

- [Spring Framework Reference — Using JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): JmsTemplate, DefaultMessageListenerContainer, transactions, and duplicate detection.
- [Spring Framework Reference — Receiving JMS Messages](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): listener containers, transacted sessions, and acknowledgement.
- [Spring Framework Reference — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@JmsListener` and listener factory configuration.
- [Spring Boot Reference — JMS](https://docs.spring.io/spring-boot/reference/messaging/jms.html): Artemis auto-configuration, JmsTemplate, and listener infrastructure.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): durable subscriptions, persistent delivery, acknowledgement, redelivery, and duplicate delivery.
- [ActiveMQ Artemis Documentation](https://activemq.apache.org/components/artemis/documentation/): persistence, address settings, redelivery, and dead-letter configuration.
