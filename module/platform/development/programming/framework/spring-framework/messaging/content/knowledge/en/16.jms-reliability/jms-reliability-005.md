# Retry Policy, Delay, and Provider Dead-Letter Queues

> Goal: understand how a JMS provider handles messages that are rolled back or fail delivery; distinguish application retry from broker redelivery; configure the number of attempts, delay/backoff, and the Dead Letter Queue (DLQ); coordinate the broker policy with Spring listener transactions, error handling, and idempotency.

## 1. Why do we need a redelivery policy?

A consumer may fail to process a message because of a transient error such as a database timeout, a downstream service being down, or a lost connection. With a transacted session, the listener can throw an exception to roll the message back. The broker can then redeliver the message to the consumer.

If the broker redelivers immediately and the listener keeps failing, the message can create a continuous rollback loop. This loop consumes CPU, network, and listener threads, and also slows down other messages. If the number of redeliveries is not bounded, a permanently failing message can occupy the queue indefinitely.

A retry/redelivery policy usually needs to answer four questions:

1. Should we retry when the listener rolls back?
2. How long do we wait before the next redelivery?
3. What is the maximum number of failed deliveries?
4. After the attempts run out, where does the message go and who is responsible for handling it?

JMS defines the acknowledgement mechanism, transactions, and metadata for recognizing redelivery. However, configuring the delay, the limit on delivery attempts, and the DLQ target are features each provider implements; there is no portable configuration API that applies the same way to every broker.

## 2. Distinguishing three layers of retry

You need to clearly separate retry in application code, broker redelivery, and moving a message to the DLQ:

| Layer | Who does it? | Scope |
|---|---|---|
| Application retry | Listener/service code or a retry library | Re-invoking an operation within the same message delivery, for example calling an API or querying a database |
| JMS redelivery | JMS provider/broker | Redelivering the message after a transaction rollback, a session recover, or an unacknowledged delivery |
| Dead Letter Queue | Broker/provider | Moving the message to an error address/queue after exceeding the failed-delivery threshold or per provider policy |

Example: the listener calls a payment API. It may retry the API twice within the same JMS delivery to handle a short timeout. If it still fails, the listener throws an exception; the JMS transaction rolls back and the broker may redeliver the message after a delay. After the maximum number of failed deliveries, the broker moves the message to the DLQ.

Do not confuse Spring Integration's `errorChannel` with a DLQ. `errorChannel` is an error-handling flow within the application context; a DLQ is a destination managed by the broker. An error flow that handles the exception and returns normally can cause the listener invocation to end successfully and the transaction to commit. If you want a rollback, the error flow must rethrow the exception or throw a different exception according to the transaction configuration.

## 3. Conditions for the broker to redeliver a message

The broker usually redelivers when the previous delivery was not committed/acknowledged. Common situations include:

- The listener throws an exception in a transacted JMS session and the container rolls back.
- The application calls `Session.rollback()` in a local transaction.
- The session/connection closes before the transaction is committed.
- The client uses `CLIENT_ACKNOWLEDGE` and calls a recovery mechanism such as `Session.recover()` per the JMS API.
- The consumer loses its connection or the lease/timeout expires before the acknowledgement is recorded, depending on the provider.

With a Spring listener container, configure `sessionTransacted=true` so the listener invocation runs in a local JMS transaction. If the listener ends normally, the container commits; if an exception escapes the listener, the container rolls back and the provider may redeliver.

DMLC factory example:

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
class JmsListenerConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-8");
        return factory;
    }
}
```

The example uses `jakarta.jms` for Spring Framework 6/7; Spring Framework 5 uses `javax.jms`. You need to let the exception propagate out of the listener if you want the transaction to roll back. Catching the exception, merely logging it, and returning normally usually makes the container treat the processing as successful and commit the message.

Spring warns that the default `AUTO_ACKNOWLEDGE` does not guarantee reliability for a listener container. If you need dependable redelivery, use a transacted session or a suitable transaction manager rather than relying on the listener throwing an exception under the default acknowledgement mode.

## 4. Metadata for recognizing a redelivered message

JMS provides two useful pieces of metadata:

- `JMSRedelivered`: a boolean header indicating the provider has probably delivered the message before without it being acknowledged. A value of `true` is a signal to guard against duplicate processing; it does not tell you how far the business logic got.
- `JMSXDeliveryCount`: a standard property indicating how many times the message has been delivered. The first receive has the value 1; a value of 2 or more indicates the message has been redelivered.

According to the Jakarta Messaging specification, the provider does not guarantee that `JMSXDeliveryCount` is always absolutely accurate in every failure scenario because it is not required to persist this counter before every delivery. Therefore, use it to observe and to support policy, not as an idempotency key or as exact evidence of how many times a side effect occurred.

Example of reading metadata in a listener:

```java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.springframework.jms.annotation.JmsListener;

@JmsListener(
        destination = "orders.incoming",
        containerFactory = "ordersListenerFactory"
)
public void receive(Message message) throws JMSException {
    boolean redelivered = message.getJMSRedelivered();
    Object count = message.getObjectProperty("JMSXDeliveryCount");

    log.info("redelivered={}, deliveryCount={}", redelivered, count);
    process(message);
}
```

This is a snippet illustrating how to read metadata; `log` and `process` are components supplied by the application. For a listener method that receives a DTO directly, you can use a `jakarta.jms.Message` parameter or a suitable `@Header` to read metadata depending on the adapter/converter configuration.

## 5. Delay and exponential backoff

Redelivery delay is the wait after a failed delivery before the broker tries to deliver again. A delay gives the dependency time to recover and avoids retry bursts.

An exponential backoff schedule typically has the form:

\[d_n = \min(d_{max}, d_0 \times m^{n-1})\]

Where:

- `d0`: the initial wait time.
- `m`: the multiplier, usually greater than 1.
- `n`: the ordinal number of the next redelivery.
- `dmax`: the maximum delay cap.

Example `d0=1s`, `m=2`, `dmax=30s`: the waits are 1s, 2s, 4s, 8s, 16s, and then at most 30s. The provider may additionally support jitter/collision avoidance so that many consumers do not retry at the same moment.

A delay is not the same as `Thread.sleep()` in the listener. Sleeping in the listener holds the thread and may keep the transaction/session open for the entire wait. Broker-side delayed redelivery usually frees the consumer to process other messages, but how messages are ordered in the queue depends on the provider.

You need to distinguish redelivery delay from scheduled/initial delivery delay. JMS 2.0 has a delivery-delay API for newly sent messages; that is the time delaying the first delivery, not a retry policy after a rollback. Redelivery delay is usually a separate broker configuration.

## 6. Delivery-attempt limits and poison messages

A poison message is a message that keeps causing failures and cannot be processed successfully under the current configuration. Common causes:

- JSON/XML with a syntax error or a payload that does not match the schema.
- A type ID the consumer does not support or required data that is missing.
- A business rule that cannot be satisfied with the current data.
- Consumer and producer version incompatibility.
- A code bug that makes the same branch always throw an exception.

A broker policy usually has a maximum delivery attempts threshold. When a message exceeds the threshold, the broker may move the message to the DLQ, discard it, or apply a provider-specific action. Do not assume every provider counts the same way: some configurations count redeliveries after the first, others describe total delivery attempts. Read the provider's documentation carefully and test the threshold boundary.

Do not set an unlimited threshold for every queue. For transient errors, bounded retry with a delay is reasonable. For permanent errors such as a wrong payload, continuous retry cannot fix the data and only clogs the queue. You need to move the poison message to the DLQ/quarantine or handle the business error per the contract.

## 7. What is a Dead Letter Queue?

A Dead Letter Queue (DLQ) is a destination used to hold messages the broker cannot deliver successfully after a number of attempts or under a configured error condition. The DLQ lets the system continue processing valid messages in the main queue while retaining the failing messages for investigation.

A DLQ is usually a durable queue operated as a quarantine area. The operations team can view the payload/metadata, determine the cause, fix the data or code, and then replay in a controlled way.

A DLQ does not fix messages by itself and does not mean the message has been permanently deleted. Depending on the provider, the message may be moved to a dead-letter address, a default dead-letter queue, or discarded if no suitable target is configured. You must verify the actual configuration before production.

### DLQ differs from Expiry Queue

| Destination | Why messages are moved there |
|---|---|
| DLQ / Dead Letter Address | Delivery failed, the redelivery count was exceeded, or the message was rejected per policy |
| Expiry Queue / Expiry Address | The message expired by TTL/expiration before being consumed |

An expired message is not necessarily a poison message. Conversely, a message that failed delivery many times may not yet have exceeded its TTL. You should manage the DLQ and the expiry destination separately to distinguish the causes.

## 8. Example configuration with Apache ActiveMQ Artemis

ActiveMQ Artemis configures redelivery and dead-lettering at the broker through `address-setting` in `broker.xml`. Illustrative example:

```xml
<address-settings>
  <address-setting match="orders.incoming">
    <dead-letter-address>DLQ</dead-letter-address>
    <max-delivery-attempts>5</max-delivery-attempts>
    <redelivery-delay>1000</redelivery-delay>
    <redelivery-delay-multiplier>2.0</redelivery-delay-multiplier>
    <max-redelivery-delay>30000</max-redelivery-delay>
    <redelivery-collision-avoidance-factor>0.1</redelivery-collision-avoidance-factor>
  </address-setting>
</address-settings>
```

In the example, Artemis applies the policy to addresses matching `orders.incoming`, waits 1 second before redelivery, increases the delay by a factor of 2, caps the delay at 30 seconds, and moves messages exceeding the threshold to the `DLQ` address. You need to create/bind the queue that receives the DLQ and confirm the actual address name the JMS destination maps to in your broker.

The properties `max-delivery-attempts`, `redelivery-delay`, `redelivery-delay-multiplier`, `max-redelivery-delay`, and `dead-letter-address` are Artemis-specific configuration, not portable JMS properties. If no dead-letter address is configured, the behavior after exceeding the threshold depends on the Artemis version/configuration; the broker documentation describes the message as possibly being dropped.

## 9. Example configuration with ActiveMQ Classic

ActiveMQ Classic uses a client-side `RedeliveryPolicy` to set the delay and number of redeliveries. Example:

```java
import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.RedeliveryPolicy;

ActiveMQConnectionFactory connectionFactory =
        new ActiveMQConnectionFactory("tcp://localhost:61616");

RedeliveryPolicy policy = connectionFactory.getRedeliveryPolicy();
policy.setInitialRedeliveryDelay(1_000L);
policy.setUseExponentialBackOff(true);
policy.setBackOffMultiplier(2.0);
policy.setMaximumRedeliveries(5);
```

This is the ActiveMQ Classic client's own API, not usable with Artemis or another JMS provider. `maximumRedeliveries` describes the number of redeliveries allowed after the first delivery; you need to read the semantics of your client version carefully. The DLQ policy is configured separately at the broker, usually through a destination policy/dead-letter strategy; ActiveMQ Classic has a default DLQ `ActiveMQ.DLQ` and supports configuring a dedicated DLQ per destination.

Do not copy ActiveMQ Classic class or property names to Artemis. Even though both products belong to Apache ActiveMQ, their redelivery/DLQ configuration models differ.

## 10. Coordinating application retry with broker redelivery

Application retry suits some short transient errors, for example an HTTP service call that times out within a few hundred milliseconds. Broker redelivery suits cases that need to wait longer for the dependency to recover and where you do not want to hold the listener thread/transaction during the wait.

A strategy you can use:

1. Retry the downstream operation a small number of times within a short period.
2. If it still fails, throw the exception out of the listener.
3. The listener container rolls back the JMS transaction.
4. The broker waits per the redelivery delay and then redelivers the message.
5. After the delivery-attempts threshold, the broker moves the message to the DLQ.

If you use Spring Retry `RetryTemplate` in the service, decide clearly what happens when attempts run out. If the recovery callback swallows the exception and returns normally, the listener may commit the message even though the business logic is incomplete. If you want the broker to redeliver, you must let the error escape the listener or proactively roll back per the transaction contract.

Avoid multiplying the number of attempts unintentionally. For example 3 application attempts per delivery × 5 broker deliveries can produce up to 15 downstream calls. Set an overall retry budget and account for the wait time, per-attempt timeout, transaction duration, and business deadline.

Do not retry permanent errors such as validation, wrong authentication/authorization, or an unsupported schema. You can route directly to quarantine/DLQ per the application/provider policy instead of consuming the entire number of attempts.

## 11. Spring Integration error flow and the broker DLQ

If a JMS message is received through a Spring Integration inbound adapter, errors can be sent to `errorChannel` depending on configuration. This is an error flow within the application; it is not automatically the broker's DLQ.

Since Spring Integration 4.2, conversion errors of an inbound adapter/gateway can also be sent to `errorChannel`. If the error flow handles the failing message and then ends normally, the transaction may commit and the message is removed from the queue. If you want a rollback so the broker redelivers, the error flow must rethrow the exception or another exception. Check the exact version and configured flow.

For a permanent error, the error flow can write the message to a quarantine destination or durably store the payload/metadata before completing the transaction. If publishing to quarantine and acknowledging the original message must be atomic, you need the same JMS transaction/session or a suitable transactional mechanism; do not assume two independent operations are atomic.

## 12. Designing the DLQ operating procedure

A DLQ must be operated as a process with an owner, not just a queue that was created:

1. **Classify:** separate transient errors, data errors, configuration errors, and code errors.
2. **Observe:** record the original destination, message ID, event ID, correlation ID, delivery count, time, and cause of the error.
3. **Protect data:** restrict read access to the DLQ, avoid logging sensitive payloads, and set a suitable retention.
4. **Investigate:** determine whether the failing message is due to the producer, consumer, broker, or a downstream dependency.
5. **Fix the cause:** deploy a code, configuration, or data-mapping fix before replaying.
6. **Controlled replay:** choose small batches, monitor the results, and keep the event ID unchanged so deduplication works.
7. **Close the incident:** record the cause, the number of messages, the time affected, and how it was recovered.

Do not automatically move all messages in the DLQ back to the main queue on a schedule. If the cause has not been fixed, the messages will keep failing and return to the DLQ, creating an operational loop.

When replaying, consider keeping the same business event ID so the consumer recognizes this as the same event. If you create a new event ID, the system may treat the replay as a new business operation and apply the side effect again. Whether to keep or create a new ID must follow the application's replay contract.

## 13. Idempotency and duplicate delivery

Retry/redelivery usually carries at-least-once semantics: a message can be delivered multiple times if the previous processing was not acknowledged or the commit result is unclear. The broker cannot know whether an external HTTP call or database transaction has already produced a side effect.

The consumer needs to be idempotent:

- Use a stable `eventId`/`commandId` generated by the application.
- Record processed event IDs in an inbox table with a unique constraint.
- Update the business data and the inbox in the same database transaction.
- Use an idempotency key when calling a payment API or downstream service, if available.
- If the duplicate has already completed, end the listener successfully so the transaction commits and the broker stops redelivering.

`JMSRedelivered` and `JMSXDeliveryCount` help recognize delivery history; they do not replace an idempotency key. Do not assume the DLQ removes duplicates or ensures an exactly-once business effect.

## 14. Choosing a policy by error type

| Error type | Suggested action |
|---|---|
| Short database timeout | A few application retries; if attempts run out, roll back so the broker redelivers after a delay |
| Downstream service outage | Broker-side delay/backoff, limit the number of deliveries, and alert on the outage |
| Payload with the wrong schema or corrupted JSON | Quarantine/DLQ early; do not retry indefinitely |
| Missing permission or wrong credentials | Stop/reduce retry, alert on the configuration; avoid causing an authentication storm |
| Legitimate business-rule rejection | Record the business rejection result and commit per the contract; do not treat every rejection as a technical error |
| Code bug causing a repeating exception | Limit redelivery, DLQ, and alert to avoid a poison message blocking the queue |
| Broker restart or network interruption | Use the listener container/provider recovery; handle duplicates and unclear send results |

One queue may need a different policy from another. For example a payments queue may need a long retry delay and a closely monitored DLQ; a telemetry queue may accept discarding some expired messages. Set the policy by business value and SLA; do not use one undifferentiated shared configuration.

## 15. Testing retry, delay, and the DLQ

You need to test with the exact broker/provider and version being deployed:

1. Listener succeeds: the message is committed and not redelivered.
2. Listener throws an exception in a transacted session: the broker redelivers the message.
3. Check `JMSRedelivered` and `JMSXDeliveryCount` on the next receive.
4. Confirm the actual delay is close to the configured policy; measure both jitter and the delay cap.
5. Cause continuous failure to confirm the delivery-attempts threshold and the behavior when it is exceeded.
6. Confirm the message arrives at the correct DLQ address/queue and still retains the necessary metadata.
7. Confirm a message whose TTL expires follows the expiry policy and is not confused with the poison-message DLQ.
8. Replay the message after fixing the error and confirm idempotency prevents a repeated side effect.
9. Restart the broker while a consumer is processing to check redelivery and unclear commit results.
10. Check that the main queue keeps processing valid messages when a poison message is moved to the DLQ.

Do not only check that the XML/Java configuration was loaded. You must confirm the actual behavior using delivery count, timestamps, queue depth, DLQ contents, and broker logs.

## 16. Metrics and alerts

You should track:

- The number of redeliveries per destination.
- The number of messages entering the DLQ over time and by error type.
- Queue depth, the age of the oldest message, and the consumption rate.
- The rate of listener exceptions, rollbacks, and retry exhaustion.
- The actual delay between redeliveries.
- The number of replayed messages and the replay success rate.
- Consumer count, processing latency, and downstream error rate.

Alert when the DLQ grows abnormally, oldest-message-age exceeds the SLA, the delivery count rises quickly, or queue depth keeps increasing. Attach the correlation ID and event ID to logs to trace a message across multiple deliveries.

## 17. Common mistakes

- **Assuming standard JMS defines a common DLQ configuration:** the redelivery limit, delay, and DLQ routing depend on the provider.
- **Confusing application retry with broker redelivery:** one re-invokes an operation inside the listener; the other redelivers the whole message.
- **Using `Thread.sleep()` in the listener to delay:** holds the thread and may keep the transaction/session open.
- **Using `AUTO_ACKNOWLEDGE` but expecting a rollback when the listener fails:** requires a transacted session or a suitable transaction manager.
- **Swallowing the exception after application retries are exhausted:** the listener may return successfully and the message is committed.
- **Setting infinite retry:** a poison message can clog the queue and consume resources.
- **Not configuring the DLQ address/queue:** the provider may discard the message after the threshold instead of keeping it.
- **Confusing the DLQ with the expiry queue:** the two destinations represent two different causes.
- **Assuming the delivery count is an absolute counter:** `JMSXDeliveryCount` is not guaranteed to be absolutely accurate across every failure.
- **Replaying without checking idempotency:** business side effects may be repeated.
- **Configuring ActiveMQ Classic policy for Artemis:** the two providers have different APIs and broker configuration.
- **Assuming Spring errorChannel automatically puts messages into the broker DLQ:** the error channel is a flow within the application, while the DLQ is a destination managed by the broker.

## 18. Procedure for building a retry and DLQ policy

1. Determine which kinds of errors are recoverable and which are permanent.
2. Choose a local JMS transaction or a suitable transaction manager so a listener failure can roll back.
3. Choose the number of attempts, initial delay, multiplier, maximum delay, and jitter according to the SLA.
4. Determine the exact attempt-counting semantics of the broker/version.
5. Configure the DLQ address/queue and access permissions; configure expiry separately.
6. Set a small application retry and limit the total number of downstream calls.
7. Ensure the exception is propagated out of the listener when broker redelivery is needed.
8. Design idempotency/inbox and a replay procedure.
9. Test rollback, delayed redelivery, max attempts, DLQ, expiry, and broker restart.
10. Monitor queue depth, delivery count, retry exhaustion, and the DLQ; periodically review backlogged messages.

## 19. Conclusion

The JMS transaction and exception propagation determine when a message can be redelivered; the JMS provider determines the delay, the number of redeliveries, and the destination that receives failing messages. The Spring listener container helps manage transactions and listener lifecycle, while the redelivery/DLQ policy must be configured for the specific broker.

A dependable design needs bounded retry, exponential backoff/jitter where appropriate, a DLQ with an investigation and replay procedure, and an idempotent consumer. Distinguish transient errors from poison messages, check the delivery counter's semantics per provider, and test actual behavior instead of assuming every JMS broker behaves the same.

## References

- [Jakarta Messaging 3.1 — JMSRedelivered and JMSXDeliveryCount](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Integration — JMS Support and Inbound Conversion Errors](https://docs.spring.io/spring-integration/reference/jms.html)
- [Apache ActiveMQ Artemis — Redelivery and Dead Letter Addresses](https://activemq.apache.org/components/artemis/documentation/)
- [Apache ActiveMQ Classic — Message Redelivery and DLQ Handling](https://activemq.apache.org/components/classic/documentation/message-redelivery-and-dlq-handling)
- [Apache ActiveMQ Classic — Redelivery Policy](https://activemq.apache.org/components/classic/documentation/redelivery-policy)