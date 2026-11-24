# Expiration, Delivery Delay, and Differences Across JMS Providers

## 1. Two timing mechanisms with two different purposes

In JMS, a message can be retained in the broker for a limited time or delayed before a consumer can receive it. These two mechanisms are often confused:

- **Expiration / Time-to-live (TTL):** defines when a message expires. After that point, the provider must no longer deliver the message to a consumer.
- **Delivery delay:** defines the minimum amount of time that must elapse after sending before the provider is allowed to deliver the message.

TTL answers the question **until when is the message still valid?** Delivery delay answers the question **when is the earliest the message is allowed to become visible to a consumer?**

The two values are independent and can be used together. If the TTL is shorter than the delivery delay, the message can expire before it becomes eligible for delivery.

JMS standardizes the API and part of the semantics, but how a broker stores waiting messages, scans for expired messages, moves messages to an expiry destination, and supports advanced delivery schedules can differ across providers.

After this lesson, you should be able to:

- Explain TTL, JMSExpiration, and message expiration.
- Explain delivery delay and JMSDeliveryTime.
- Calculate the time window during which a message can be delivered.
- Configure TTL and delivery delay with the Jakarta Messaging API.
- Configure both values with Spring JmsTemplate.
- Distinguish delivery delay from redelivery delay, timeouts, and scheduled jobs.
- Understand the differences between ActiveMQ Classic, ActiveMQ Artemis, and IBM MQ.
- Design expiry queues/addresses, clock synchronization, and testing against a real broker.

## 2. Expiration and Time-to-live

### 2.1 What is TTL?

Time-to-live is the duration in milliseconds that a message is allowed to exist in the messaging system from the time it is sent. The producer sets the TTL when sending the message. The provider calculates the expiration timestamp and represents it through the standard `JMSExpiration` header.

Examples:

- TTL 60,000 ms: the message expires about 60 seconds after sending.
- TTL 300,000 ms: the message is valid for about 5 minutes.
- TTL 0: the message has no JMS expiration time.

TTL is commonly used for data that is only valid for a period of time, such as:

- A price or quote that is only valid for one minute.
- A stale status-update command that is no longer needed after a deadline.
- A cache invalidation event that can be ignored once the data has already been resynchronized.
- A transient notification that does not need processing if the consumer receives it too late.

TTL does not guarantee that the message will be processed within that period. It only limits how long the message remains eligible for delivery. If the consumer is inactive, the message may expire before it is received.

### 2.2 JMSExpiration

`JMSExpiration` is the absolute expiration timestamp calculated by the provider on send. The value is expressed in milliseconds since the UTC epoch.

With TTL equal to 0, `JMSExpiration` is 0, meaning it does not expire by TTL. With a positive TTL, the provider calculates expiration based on the send timestamp plus the TTL.

JMS specifies that for a transacted send, the TTL calculation starts when the client calls send, not when the transaction commits. Therefore, a long-held transaction can reduce the remaining validity time of the message as soon as the message is committed.

The provider should try to handle expiration accurately, but JMS does not mandate absolute timing precision. How the broker detects and removes expired messages depends on the implementation.

### 2.3 What happens when a message expires?

Once expiration is reached, the provider should not deliver that message to a consumer as a valid message. The broker can remove the message when:

- The message has just arrived at the broker.
- The message is waiting in the queue.
- The broker is preparing to dispatch the message to a consumer.
- A periodic expiration-scan task runs.

JMS does not standardize a common destination to store expired messages, nor does it guarantee the producer receives a notification that the message has expired. Many brokers offer a separate expiry queue or expiry address configuration to move expired messages to an inspection location.

Therefore, distinguish:

- **Expired message:** a message that exceeded its TTL.
- **Undeliverable / poison message:** a message that could not be processed after a number of redeliveries or per broker policy.
- **Dead-letter message:** a message moved to the DLQ under a dead-letter policy.

The expiry destination and the DLQ can be two different places with different operational procedures.

## 3. Delivery delay and JMSDeliveryTime

### 3.1 What is delivery delay?

Delivery delay is the minimum time from sending before the provider is allowed to deliver the message to a consumer. The standard API has been available since JMS 2.0.

Key APIs:

~~~java
MessageProducer producer = session.createProducer(destination);
producer.setDeliveryDelay(30_000L);
~~~

Or with the simpler `JMSContext` API:

~~~java
context.createProducer()
        .setDeliveryDelay(30_000L)
        .send(destination, "remind customer");
~~~

The duration is in milliseconds. The default value is 0, meaning no delay.

Delivery delay sets the **earliest time** the provider may deliver the message. It does not guarantee the consumer receives it at that exact instant. High broker load, an inactive consumer, or other messages in the queue can make receipt happen later.

### 3.2 JMSDeliveryTime

`JMSDeliveryTime` is a standard JMS 2.0 header representing the earliest time the message can be delivered, as milliseconds since the UTC epoch.

The provider calculates delivery time by adding the delivery delay to the time the client sends the message. With a transacted send, the reference point is still when the client calls send, not when the transaction commits.

A client must not receive the message before its delivery time. After that time, the provider can deliver the message when other conditions allow.

You can read the headers on a received message:

~~~java
long deliveryTime = message.getJMSDeliveryTime();
long expiration = message.getJMSExpiration();
~~~

These values are useful for observing how long a message was delayed and until when it remains valid. They are not handler execution timers.

### 3.3 Delivery delay is not a recurring schedule

Standard JMS delivery delay only delays the initial delivery. It does not by itself create a recurring schedule, cron, or automatically resend a message every hour.

If you need a recurring delivery schedule or cron, you need a broker scheduler extension, a separate scheduler service, or a durable scheduling application. These extended features are usually not portable across providers.

## 4. TTL and delivery delay when used together

Both values start from the send time, but have different meanings:

- Delivery time is the earliest time the message is allowed to be delivered.
- Expiration time is the time when the message is no longer allowed to be delivered.

Example of a message sent at 12:00:00:

| Setting | Value | Timestamp |
|---|---:|---|
| Send time | — | 12:00:00 |
| Delivery delay | 30 seconds | Earliest 12:00:30 |
| TTL | 120 seconds | Expires at 12:02:00 |
| Deliverable window | 90 seconds | From 12:00:30 until expiration |

If the TTL is only 20 seconds while the delivery delay is 30 seconds:

- The message expires at 12:00:20.
- The message is only eligible for delivery starting at 12:00:30.
- The message has already expired before becoming eligible for delivery.

Therefore, when using both values at the same time, ensure the TTL is longer than the delivery delay plus the time the consumer may need to work through the backlog.

A simple design formula:

~~~text
TTL > delivery delay + expected backlog wait time
~~~

This is only a design budget; the broker may still deliver later due to load, an outage, or an inactive consumer. If the business requires an absolute deadline, verify the deadline in the processing layer rather than relying solely on TTL.

## 5. Configuring with the Jakarta Messaging API

### 5.1 MessageProducer

With the simplified/classic API, TTL and delivery delay are properties of the producer:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.Session;

public class DelayedPublisher {

    public void publish(
            ConnectionFactory connectionFactory,
            Queue queue) {

        try (JMSContext context =
                     connectionFactory.createContext(Session.AUTO_ACKNOWLEDGE)) {

            context.createProducer()
                    .setDeliveryDelay(5_000L)
                    .setTimeToLive(60_000L)
                    .send(queue, "order.reminder");
        }
    }
}
~~~

The example uses Jakarta Messaging 2.0+ and requires a compatible provider ConnectionFactory. The producer is configured with a 5-second delivery delay and a 60-second TTL. The earliest the message is delivered is after 5 seconds, and it expires about 60 seconds after sending.

### 5.2 The MessageProducer API

With the Session/MessageProducer API, you can configure the producer before sending:

~~~java
MessageProducer producer = session.createProducer(queue);

try {
    producer.setDeliveryDelay(5_000L);
    producer.setTimeToLive(60_000L);

    TextMessage message = session.createTextMessage("order.reminder");
    producer.send(message);
}
finally {
    producer.close();
}
~~~

`MessageProducer.setDeliveryDelay` is available since JMS 2.0. These values apply to messages sent through that producer until the producer configuration changes.

In the classic API, the `send(message, deliveryMode, priority, timeToLive)` overload lets you specify the TTL for a single send. Delivery delay remains a producer property; there is no corresponding delivery delay parameter in this send overload.

### 5.3 Start time inside a transaction

If the Session is transacted, TTL and delivery delay are calculated from the moment send is called. Example:

1. The transaction starts at 12:00:00.
2. The application calls send with a 60-second TTL and a 10-second delay at 12:00:05.
3. The transaction commits at 12:00:50.
4. The expiration timestamp is still approximately 12:01:05, not 12:01:50.
5. The earliest eligible delivery time is still approximately 12:00:15.

A late transaction commit can leave the message with only a short window to be delivered after it appears in the broker.

## 6. Configuring with Spring JmsTemplate

### 6.1 TTL requires enabling explicit QoS

`JmsTemplate` supports configuring delivery mode, priority, TTL, and delivery delay.

When you want the delivery mode, priority, and TTL values configured by the application to be passed into the send call, you need to enable `explicitQosEnabled`:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class JmsConfiguration {

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);

        template.setExplicitQosEnabled(true);
        template.setTimeToLive(60_000L);
        template.setDeliveryDelay(5_000L);

        return template;
    }
}
~~~

Then send the message:

~~~java
jmsTemplate.convertAndSend(
        "orders.queue",
        "order.reminder");
~~~

In the example:

- `setTimeToLive(60_000L)` sets a 60-second TTL.
- `setDeliveryDelay(5_000L)` sets a 5-second delivery delay.
- `setExplicitQosEnabled(true)` tells JmsTemplate to use the configured QoS values for delivery mode, priority, and TTL.
- Delivery delay is applied separately through the JMS producer if the value is non-negative.

If you only call `setTimeToLive` without enabling explicit QoS, JmsTemplate may use the default value or a provider-administered value instead of the TTL set on the template.

### 6.2 Delivery delay has a separate setting

`JmsTemplate.setDeliveryDelay(long)` requires JMS 2.0. The default value is -1, meaning the template does not pass a delivery delay to the producer.

- -1: do not apply a delivery delay via the template.
- 0: send without delay.
- Positive number: minimum number of milliseconds to delay.

Unlike TTL, delivery delay is not in the group of QoS values controlled by `explicitQosEnabled`. Configure it separately and verify that the JMS provider supports JMS 2.0.

### 6.3 JmsTemplate and scope of application

The settings on JmsTemplate are template configuration, so all send operations using that instance are subject to the same TTL/delivery delay policy.

If each message needs a different delay time, do not mutate a property of a JmsTemplate shared across multiple threads per request. You can use a separate producer for that operation, or use `JmsTemplate.execute` with a Session/Producer callback to configure the MessageProducer for the specific send.

`MessagePostProcessor` operates on the JMS Message before sending. It can set JMS properties or a correlation ID, but standard delivery delay is a property of MessageProducer, not an arbitrary property on Message.

### 6.4 QosSettings

Spring JMS's `QosSettings` bundles delivery mode, priority, and TTL. It does not replace the delivery delay setting.

Example:

~~~java
import jakarta.jms.DeliveryMode;

import org.springframework.jms.support.QosSettings;

QosSettings qos = new QosSettings(
        DeliveryMode.PERSISTENT,
        4,
        60_000L);

jmsTemplate.setQosSettings(qos);
jmsTemplate.setDeliveryDelay(5_000L);
~~~

`setQosSettings` enables explicit QoS for delivery mode, priority, and TTL. Delivery delay is still configured with `setDeliveryDelay`.

## 7. Per-message delivery delay with Spring

When each message has a different delay, configure the producer for that exact send. The example below uses a Session callback so JmsTemplate manages the Connection/Session, while the application creates a producer with a specific delay:

~~~java
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

import org.springframework.jms.core.JmsTemplate;

public void sendDelayed(
        JmsTemplate jmsTemplate,
        String payload,
        long delayMillis,
        long ttlMillis) {

    jmsTemplate.execute(session -> {
        Queue queue = session.createQueue("orders.queue");
        MessageProducer producer = session.createProducer(queue);

        try {
            producer.setDeliveryDelay(delayMillis);
            producer.setTimeToLive(ttlMillis);

            TextMessage message = session.createTextMessage(payload);
            producer.send(message);
        }
        finally {
            producer.close();
        }

        return null;
    });
}
~~~

This is an illustrative method inside a service injected with JmsTemplate; it requires JMS 2.0 and a provider that supports delivery delay. The Session is managed by the template, and the producer is closed after sending.

If the application uses transactions, configure the transaction on JmsTemplate or the transaction manager as required. Do not commit or close the Session that the template is managing yourself.

## 8. Expiry destination and handling expired messages

Standard JMS does not specify a common expiry queue. A broker may provide its own configuration to move expired messages to another destination.

An expiry destination is useful for:

- Checking whether messages have too short a TTL.
- Detecting consumers processing backlog slowly.
- Analyzing clock skew between producer and broker.
- Reconciling notifications whose validity has expired.
- Distinguishing expired messages from messages that failed due to a listener error.

Some brokers call this an expiry address, expiry queue, or message expiry policy. You need to configure the target destination, access permissions, and the retention of that destination itself.

Do not replay expired messages automatically if the business deadline has already passed. Before resending, check whether the data is still valid and whether a new command with a new deadline needs to be created.

## 9. Differences across providers

Standard JMS defines the TTL and delivery delay APIs, but brokers can differ in how they store scheduled messages, scan for expiration, move expired messages, and support extended features.

### 9.1 Apache ActiveMQ Classic

ActiveMQ Classic supports message expiration. The producer sets the TTL; the client calculates the expiration timestamp on send and the broker checks the message on arrival, while awaiting dispatch, or during destination scans. The clocks of the producer and the broker must be synchronized to avoid messages expiring too early or too late.

ActiveMQ Classic also has a scheduler extension. The scheduler needs to be enabled with the broker configuration `schedulerSupport=true`. Applications can use provider-specific properties:

| Property | Meaning |
|---|---|
| `AMQ_SCHEDULED_DELAY` | Delay of the first delivery, milliseconds |
| `AMQ_SCHEDULED_PERIOD` | Interval between repeated deliveries |
| `AMQ_SCHEDULED_REPEAT` | Number of repeats |
| `AMQ_SCHEDULED_CRON` | Cron schedule |

Example of scheduling delivery after 60 seconds:

~~~java
import org.apache.activemq.ScheduledMessage;

message.setLongProperty(
        ScheduledMessage.AMQ_SCHEDULED_DELAY,
        60_000L);

producer.send(message);
~~~

These scheduler properties are an ActiveMQ Classic extension, not a portable JMS API. You need to enable the scheduler at the broker and check the version in use. Do not use them if the goal is to switch brokers without changing code.

### 9.2 Apache ActiveMQ Artemis

Artemis supports TTL per JMS and has an expiry address to move expired messages to another address. Administrators can configure the expiry address via address/queue policy.

Artemis supports scheduled delivery with its own property `_AMQ_SCHED_DELIVERY`, and also has the `Message.HDR_SCHEDULED_DELIVERY_TIME` constant in the corresponding API. The value is an absolute timestamp in milliseconds from the epoch, not a delay duration:

~~~java
long scheduledTime = System.currentTimeMillis() + 5_000L;

message.setLongProperty(
        "_AMQ_SCHED_DELIVERY",
        scheduledTime);

producer.send(message);
~~~

This is an Artemis extension. When using standard JMS 2.0, prefer `MessageProducer.setDeliveryDelay` or `JMSProducer.setDeliveryDelay` if the provider/client version supports it. When using the provider-specific property, synchronize clocks and align the API with the broker.

### 9.3 IBM MQ

IBM MQ supports delivery delay through JMS 2.0. When an application sets a delivery delay, the queue manager uses an internal staging queue and a delivery delay processor to hold the message until the delay elapses, then moves it to the target destination.

IBM MQ maintains expiration semantics while the message sits on the staging queue. Therefore a message can still expire before being moved to the target queue if the TTL has elapsed.

The IBM MQ documentation notes several limitations by feature, version, and topology. For example, delivery delay is not supported together with retained publications or message grouping in the cases described in the documentation. If the application uses retained publications or grouping, check the exact IBM MQ version before enabling delivery delay.

### 9.4 Comparison table

| Topic | ActiveMQ Classic | ActiveMQ Artemis | IBM MQ |
|---|---|---|---|
| TTL / expiration | Supported; broker checks expiration | Supported; has expiry address | Maps expiration per JMS/MQMD |
| Expired message routing | Broker-specific configuration | Expiry address | Appropriate policy/queue manager |
| Scheduled delivery extension | AMQ_SCHEDULED_DELAY and scheduler | _AMQ_SCHED_DELIVERY, absolute timestamp | JMS 2.0 delivery delay via staging queue |
| Scheduler enablement | Requires enabling schedulerSupport for the scheduler extension | Supports scheduled delivery | Queue manager processes via staging queue |
| Portability | Standard JMS TTL; custom scheduler properties | Standard JMS TTL; custom scheduled property | JMS TTL and JMS 2.0 delivery delay |
| Points to check | Client/broker clocks and scheduler persistence | Expiry address, scheduled property, clock | Retained publication, message grouping, and staging queue |

The table above describes mechanisms published in the providers' documentation; actual capabilities also depend on the broker version, client library, destination configuration, and transport. Do not infer that every feature of one version exists in every other version.

## 10. Factors affecting expiration and delivery delay

### 10.1 Clock synchronization

JMSExpiration and JMSDeliveryTime are absolute timestamps. The producer computes the time from the sending machine's clock; the broker may compare it with its own clock.

If clocks drift apart:

- A message may be treated as expired early.
- A message may live longer than the expected TTL.
- Scheduled delivery may run earlier or later than expected.

Use NTP or the infrastructure's time synchronization mechanism. Monitor clock drift among applications, brokers, and nodes in the cluster.

### 10.2 Broker outage

If the broker stops while messages are waiting for scheduled delivery, whether the messages survive after restart depends on persistence and the provider's scheduler implementation.

Do not assume a scheduled message is always durable just because the message has a persistent delivery mode. Test a broker restart with the exact storage configuration and scheduler type in use.

### 10.3 Consumer backlog

Delivery delay only sets the earliest time. If the queue has a backlog, consumers lack capacity, or the broker is recovering, the message may be received much later.

TTL needs to be long enough for both the delay and the actual backlog wait time. If a message expires in the backlog, the broker may discard it before a consumer processes it.

### 10.4 Delivery mode and TTL are two separate concepts

- **Persistent delivery mode:** asks the provider to store the message with the broker's durable semantics.
- **TTL:** limits how long the message remains valid.
- **Delivery delay:** delays the earliest time delivery is allowed.

A persistent message can still expire. A non-expiring message is not automatically guaranteed to survive a broker restart if the delivery mode or broker persistence is inappropriate.

### 10.5 Broker administration policies

JMS allows the provider or an administrator to configure overrides for certain values of delivery mode, priority, TTL, and delivery delay. This capability is not mandatory in every provider.

If an application sets a 10-minute TTL but a broker policy overrides the TTL, the header after sending may reflect the overridden value. Check both client and broker configuration when observing results.

## 11. Distinguishing from other timing mechanisms

| Mechanism | What does it control? | Primary manager |
|---|---|---|
| TTL / expiration | Until when the message remains valid | Producer and broker |
| Delivery delay | Earliest time eligible for delivery | Producer and broker |
| Redelivery delay | How long to wait before redelivering after rollback/nack | Broker policy |
| Receive timeout | How long the consumer waits for a message | Consumer/API |
| Connection timeout | How long to wait to establish a connection | JMS client/provider |
| Listener recovery interval | Wait before Spring tries to recreate listener resources | Spring container |
| Scheduled job / cron | When to run a task or recurring schedule | Scheduler/application |

Delivery delay does not replace redelivery delay. If a listener throws an exception and the transaction rolls back, the broker uses the redelivery policy to decide the next delivery. Delivery delay primarily applies to the initial delivery.

TTL is also not a handler processing timeout. A message can be delivered before expiration and the listener can continue processing after the TTL has passed. If the business requires cancelling processing when the deadline expires, you must check the deadline in the application layer and design separate cancellation/compensation.

## 12. Testing expiration and delivery delay

You should have integration tests with the target broker rather than only mocking MessageProducer. Tests need to verify actual provider semantics.

### 12.1 TTL

- Send a message with a short TTL and receive it before expiration.
- Let the message sit in the queue past its TTL and verify the consumer does not receive it.
- Verify JMSExpiration on the sent/received message if the API/provider allows observing it.
- Check whether expired messages are moved to an expiry destination or discarded.
- Check that a TTL of 0 sets no TTL-based expiration.
- Check clock synchronization and the broker's expiration-processing timing.

### 12.2 Delivery delay

- Send a message with a 5-second delay.
- Verify the consumer does not receive it before the delivery time.
- Verify the message can be received after that time.
- Read JMSDeliveryTime and compare it with the send time.
- Test delay 0 and the default value.
- Test the provider when the broker restarts while the message is waiting.
- Check that a topic subscription exists at send time.

Do not test by requiring the message to appear at one exact millisecond. Use an acceptable time window and a wide enough timeout to avoid flaky tests due to the scheduler, CI, or broker load.

### 12.3 TTL combined with delivery delay

Test two cases:

1. TTL longer than delay: the message has a window to be delivered after the delay ends.
2. TTL shorter than delay: the message expires before becoming eligible for delivery.

This is an important test to catch unreasonable configurations in production.

### 12.4 Testing provider differences

If the application supports multiple brokers, run the same integration test suite on each provider/version. Especially check:

- Expiry address/queue.
- Scheduler persistence after restart.
- Delivery delay extensions.
- Message grouping and retained publications.
- Admin overrides.
- Clock skew and expiration accuracy.

## 13. Common mistakes

- **Confusing TTL with delivery delay:** one value defines the expiration time, the other defines the earliest delivery time.
- **Setting TTL shorter than delivery delay:** the message can expire before being delivered.
- **Assuming TTL starts after the delay ends:** TTL starts from the send time.
- **Assuming delivery delay guarantees on-time delivery:** it is only the earliest time, not a delivery deadline.
- **Thinking TTL 0 means immediate expiration:** in JMS, TTL 0 means no TTL-based expiration.
- **Forgetting explicitQosEnabled in JmsTemplate:** the configured TTL may not be passed to send if explicit QoS is not enabled.
- **Thinking MessagePostProcessor can set standard delivery delay:** delivery delay is a producer property, not a message property.
- **Using vendor properties as standard JMS API:** scheduler properties are not portable.
- **Using an absolute timestamp as a duration:** Artemis's scheduled-delivery property expects an epoch timestamp, whereas JMS setDeliveryDelay takes a duration in milliseconds.
- **Not synchronizing clocks:** producer and broker may compute expiration differently.
- **Confusing the expiry queue with the DLQ:** expiry handles expired messages; the DLQ handles messages that cannot be delivered/processed per policy.
- **Assuming a persistent message cannot expire:** persistent and TTL are independent.
- **Confusing delivery delay with redelivery delay:** initial delivery and redelivery are two different mechanisms.
- **Not testing restart:** scheduled messages can depend on the provider's storage and scheduler.

## 14. Design and operations checklist

Before configuring TTL or delivery delay, check:

- How long is the message still valid?
- Is the TTL calculated from the send time as desired?
- Is delivery delay needed for the initial delivery, or is it trying to solve redelivery?
- Is the TTL longer than the delay plus expected backlog time?
- Has JmsTemplate enabled explicit QoS if TTL needs to be applied?
- Is delivery delay configured on the right producer/template?
- Is one shared template being used for many different delays?
- Do the provider and JMS client support JMS 2.0 delivery delay?
- Are any vendor-specific scheduler properties being used?
- Are the producer, broker, and consumer clocks synchronized?
- Are expired messages discarded or moved to an expiry destination?
- Does scheduler state survive a broker restart?
- Does the broker have a policy overriding TTL or delivery delay?
- Are expiration, DLQ, and redelivery policy distinguished?
- Have integration tests verified TTL, delay, the combined case, and broker-specific behavior?

When you design TTL, delivery delay, and expiry policy correctly, the application can drop stale messages, delay messages until the right moment, and keep consistent behavior when switching JMS providers. The standard API should be preferred for portability; broker extensions should only be used when the application truly needs a specific feature and accepts provider coupling.

## 15. References

- [Jakarta Messaging 3.1 Specification — Message delivery time and delay](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Jakarta Messaging MessageProducer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer)
- [Spring Framework 6.2 — JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
- [ActiveMQ Classic — Message Expiry](https://activemq.apache.org/components/classic/documentation/message-expiry)
- [ActiveMQ Classic — Delay and Schedule Message Delivery](https://activemq.apache.org/components/classic/documentation/delay-and-schedule-message-delivery)
- [ActiveMQ Artemis — Message Expiry](https://artemis.apache.org/components/artemis/documentation/latest/message-expiry.html)
- [ActiveMQ Artemis — Scheduled Messages](https://artemis.apache.org/components/artemis/documentation/latest/scheduled-messages)
- [IBM MQ — Delivery delay for JMS messages](https://www.ibm.com/docs/en/ibm-mq/9.3.x?topic=applications-delivery-delay-jms-messages)
- [IBM MQ — JMSMessage and JMSExpiration](https://www.ibm.com/docs/en/ibm-mq/10.0.x?topic=messaging-jmsmessage)