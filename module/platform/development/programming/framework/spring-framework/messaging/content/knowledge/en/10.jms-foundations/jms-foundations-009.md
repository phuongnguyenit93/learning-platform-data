# Delivery Mode, Priority, and Time-to-Live in JMS Messages

When sending messages using Jakarta Messaging (JMS), a producer can specify three Quality of Service (QoS) attributes:

- **Delivery mode:** whether the message must be persisted if the provider fails, or whether message loss is acceptable to reduce transport overhead.
- **Priority:** which message the provider should prioritize when multiple messages are waiting.
- **Time to live (TTL):** how long the message remains valid before expiring.

These three attributes are independent. A message can be persistent, high priority, and short-lived at the same time. In Spring Framework, `JmsTemplate` and the fluent `JmsClient` API help configure these values when sending.

## 1. Delivery Mode: PERSISTENT and NON_PERSISTENT

JMS defines two modes via `jakarta.jms.DeliveryMode`:

| Constant | Value | Meaning |
| --- | ---: | --- |
| `DeliveryMode.PERSISTENT` | 2 | Instructs the provider to write the message to stable storage during the send operation |
| `DeliveryMode.NON_PERSISTENT` | 1 | Does not require the provider to write the message to stable storage; favors lower overhead and higher throughput |

### PERSISTENT

When sending a persistent message, the provider must save the message to stable storage as part of the send operation. The goal is to minimize message loss if the provider crashes. Under the JMS contract, only catastrophic storage hardware failure is considered a permissible cause for losing a persistent message.

Choose persistent for messages whose loss in transit has business consequences, such as:

- Commands to create or update orders.
- Payment requests or transaction postings.
- Business events that must be retained for consumers to process after a broker restart.

Persistent can increase I/O cost, storage usage, and send latency. Actual impact depends on the broker, journal/store configuration, batching, and provider implementation.

### NON_PERSISTENT

With non-persistent, the provider does not need to write the message to stable storage. This is a lower-overhead mode, suitable when the application can tolerate losing some messages if the provider fails, such as:

- High-frequency telemetry.
- Metrics or reconstructible observability data.
- Transient state updates where newer updates supersede older ones.

JMS requires non-persistent to have an at-most-once guarantee: the provider may lose a message, but must not deliver the same message twice under this contract.

### Delivery mode does not replace acknowledgement and transactions

Delivery mode primarily governs reliability while the provider transports the message to the destination. It does not itself guarantee that a message will be kept indefinitely in a queue after a consumer receives it, nor does it replace consumer transactions or acknowledgement.

The destination's retention policy and how the consumer acknowledges/commits determine when a message is removed from the destination. If a consumer processes a message and then rolls back or loses connection before acknowledgement, the provider may redeliver depending on session/transaction semantics. Applications should still design idempotent consumers for critical business logic.

## 2. Priority: Priority Levels from 0 to 9

JMS defines ten priority levels:

- `0`: lowest.
- `9`: highest.
- `0–4`: normal priority levels.
- `5–9`: expedited priority levels.
- Default value: `4`.

Priority is a hint to the provider when selecting the next message to deliver. The provider should attempt to deliver expedited messages before normal messages, but JMS **does not require the provider to implement strict priority ordering**.

This means:

- High priority does not guarantee immediate delivery.
- A message already delivered to a consumer or in progress is not "preempted" by a higher-priority message.
- Do not rely on priority as a substitute for designing business ordering.
- Actual behavior depends on the broker, queue configuration, and consumer load.

Illustrative categorization:

| Priority | Illustrative usage |
| ---: | --- |
| 0–2 | Low-urgency background tasks |
| 3–4 | Normal work |
| 5–7 | Work needing prompt processing |
| 8–9 | Urgent messages, low volume |

This is merely an application convention. JMS does not assign fixed business meanings to individual numbers.

Do not set every message to priority 9. If everything is marked urgent, priority no longer distinguishes important traffic; normal messages can be starved for long periods as the broker continually prioritizes new messages.

## 3. Time to Live: Message Lifetime

TTL is the duration in milliseconds that a message remains valid after being sent.

| TTL | Meaning |
| ---: | --- |
| `0` | Does not expire; the message has no expiration timestamp |
| `5_000` | Expires after roughly 5 seconds |
| `60_000` | Expires after roughly 1 minute |
| `300_000` | Expires after roughly 5 minutes |

When a producer sends a message with a TTL greater than 0, the provider computes the expiration timestamp:

```text
JMSExpiration = send time + timeToLive
```

`JMSExpiration` is an absolute timestamp in milliseconds since the Unix epoch (1970-01-01 UTC). This header is set by the provider upon sending; the application does not set expiration by directly editing the message header.

When an undelivered message reaches its expiration time, the provider should discard it. Consumers should not receive expired messages, though JMS does not strictly guarantee that can never happen. JMS also does not define a standard notification for message expiration. If the application needs to know when messages are dropped due to TTL, use monitoring or the broker's dedicated dead-letter/expired-message mechanism.

### TTL is not a processing timeout

TTL limits how long a message waits to be delivered while still on the provider side. It does not set a maximum duration for consumer processing once the message has been delivered.

Example: a message with a 30-second TTL is received by a consumer at second 20. The consumer can keep processing past second 30; TTL does not automatically abort processing that has already started. If processing time needs to be bounded, configure timeouts at the consumer/service layer.

### TTL and transactions

For messages sent inside a transacted session, JMS starts measuring TTL from the time the client calls send, not when the transaction commits. If the transaction takes a long time to commit, the message may have already consumed part of its TTL before becoming available to consumers.

### TTL and delivery delay are two different attributes

- **TTL:** the message expires after a period of time.
- **Delivery delay:** the message is not delivered until after a delay period elapses.

If you need "deliver only after 30 seconds and expire after 5 minutes," configure delivery delay and TTL separately if the provider supports JMS 2.0. TTL is not a way to schedule future message delivery.

## 4. Configuring QoS with JmsTemplate

`JmsTemplate` provides the properties:

- `setDeliveryMode(int)` or `setDeliveryPersistent(boolean)`.
- `setPriority(int)`.
- `setTimeToLive(long)`.
- `setExplicitQosEnabled(boolean)`.
- `setQosSettings(QosSettings)`.

A common point of confusion is that `JmsTemplate` stores default QoS values as follows:

| Property | Default value |
| --- | --- |
| Delivery mode | `PERSISTENT` |
| Priority | `4` |
| Time to live | `0` |
| `explicitQosEnabled` | `false` |

When `explicitQosEnabled=false`, `JmsTemplate` invokes the send method without passing explicit QoS settings. The provider may use administrative defaults configured on the ConnectionFactory/broker. Therefore, merely calling `setPriority(7)` or `setTimeToLive(60_000)` is not enough to ensure those values are applied on send.

To make `JmsTemplate` use its own configured values, enable explicit QoS:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@Bean
JmsTemplate orderJmsTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);

    template.setDeliveryPersistent(true);
    template.setPriority(7);
    template.setTimeToLive(60_000);

    // Must be enabled to apply configured QoS values.
    template.setExplicitQosEnabled(true);

    return template;
}
```

Once configured, payloads can be sent normally:

```java
jmsTemplate.convertAndSend("orders", order);
```

`JmsTemplate` uses the configured QoS settings for send operations. Finish configuring the template before sharing it across multiple services; the template is designed to be thread-safe once configured.

### Using QosSettings

You can group the three QoS values into one object:

```java
import jakarta.jms.DeliveryMode;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.QosSettings;

JmsTemplate template = new JmsTemplate(connectionFactory);

template.setQosSettings(new QosSettings(
        DeliveryMode.PERSISTENT,
        8,
        30_000
));
```

`setQosSettings` automatically enables `explicitQosEnabled=true` and assigns delivery mode, priority, and TTL on the template.

Use `DeliveryMode.NON_PERSISTENT` if the application tolerates message loss to reduce storage overhead. Set priority and TTL according to the SLA of the message type being sent.

## 5. Per-Send Configuration with JmsClient (Spring Framework 7.0+)

Spring Framework 7.0 introduces the fluent `JmsClient` API. `OperationSpec` allows configuring QoS per operation, useful when an application sends multiple message types with different policies:

```java
import org.springframework.jms.core.JmsClient;

JmsClient client = JmsClient.create(connectionFactory);

client.destination("orders")
        .withDeliveryPersistent(true)
        .withPriority(8)
        .withTimeToLive(30_000)
        .send("urgent-order:42");

client.destination("telemetry")
        .withDeliveryPersistent(false)
        .withPriority(2)
        .withTimeToLive(5_000)
        .send("cpu=0.72");
```

The first example sends a persistent message with priority 8 and a 30-second TTL. The second sends a non-persistent message with priority 2 and a 5-second TTL. Both require a configured JMS `ConnectionFactory` and the corresponding destinations on the provider.

The `withDeliveryPersistent`, `withPriority`, and `withTimeToLive` methods belong to the current operation's configuration. This is cleaner than mutating the global QoS state of a shared `JmsTemplate`.

## 6. Java 17+ Example: Inspecting JmsTemplate QoS Configuration

The following example does not require a broker connection; it inspects the configuration values Spring holds inside `JmsTemplate`. Sending real messages still requires a JMS provider and ConnectionFactory.

Create `src/main/java/JmsQosConfigDemo.java`:

```java
import jakarta.jms.DeliveryMode;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.QosSettings;

public class JmsQosConfigDemo {

    private static String modeName(int mode) {
        return switch (mode) {
            case DeliveryMode.PERSISTENT -> "PERSISTENT";
            case DeliveryMode.NON_PERSISTENT -> "NON_PERSISTENT";
            default -> "UNKNOWN(" + mode + ")";
        };
    }

    private static void print(String label, JmsTemplate template) {
        System.out.println(label + " deliveryMode: "
                + modeName(template.getDeliveryMode()));
        System.out.println(label + " priority: " + template.getPriority());
        System.out.println(label + " timeToLiveMs: "
                + template.getTimeToLive());
        System.out.println(label + " explicitQosEnabled: "
                + template.isExplicitQosEnabled());
    }

    public static void main(String[] args) {
        JmsTemplate template = new JmsTemplate();
        print("default", template);

        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setPriority(7);
        template.setTimeToLive(60_000);
        print("configuredButNotExplicit", template);

        template.setExplicitQosEnabled(true);
        print("explicit", template);

        template.setQosSettings(new QosSettings(
                DeliveryMode.NON_PERSISTENT, 2, 5_000));
        print("qosSettings", template);
    }
}
```

Create `pom.xml` at the project root:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>jms-qos-config-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>7.0.10</version>
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
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>JmsQosConfigDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Run from the directory containing `pom.xml`:

```bash
mvn -q clean compile exec:java
```

Stdout output:

```text
default deliveryMode: PERSISTENT
default priority: 4
default timeToLiveMs: 0
default explicitQosEnabled: false
configuredButNotExplicit deliveryMode: PERSISTENT
configuredButNotExplicit priority: 7
configuredButNotExplicit timeToLiveMs: 60000
configuredButNotExplicit explicitQosEnabled: false
explicit deliveryMode: PERSISTENT
explicit priority: 7
explicit timeToLiveMs: 60000
explicit explicitQosEnabled: true
qosSettings deliveryMode: NON_PERSISTENT
qosSettings priority: 2
qosSettings timeToLiveMs: 5000
qosSettings explicitQosEnabled: true
```

The output shows that setting delivery mode, priority, and TTL alone only changes the configuration stored in the template. You must enable explicit QoS or use `setQosSettings` for the template to apply those values during send operations.

## 7. Choosing Policies by Message Type

| Message type | Delivery mode | Priority | Suggested TTL |
| --- | --- | ---: | --- |
| Payment/order commands | Persistent | 5–8 by urgency | 0 or per business deadline |
| Profile update events | Persistent | 4 | Duration event remains useful |
| Droppable telemetry | Non-persistent | 1–3 | Short, e.g., a few seconds |
| Current state, newer replaces older | Non-persistent if loss acceptable | 2–4 | Short |
| Critical operational alerts | Persistent | 7–9 | Long enough for consumers to recover |

The TTL values in the table are only starting points. Determine TTL from the maximum time the business still accepts processing an older message. For financial commands, setting TTL too short can drop a valid request during a consumer outage; setting TTL too long can cause a stale command to execute after the system recovers.

Do not use priority as a substitute for separate queues for workloads with different SLAs. If urgent messages need dedicated resources or consumers, separating destinations and limiting load can be easier to operate.

## 8. Items to Verify on the Broker

JMS allows administrators to configure the provider to override QoS values sent by clients. Moreover, individual brokers can differ in how they persist messages, schedule priorities, sweep expired messages, and move messages to dead-letter queues.

In production deployments, verify:

- Whether the broker has a persistence store/journal enabled and appropriate storage policies.
- Whether the destination has capacity limits, message age limits, or retention policies.
- Whether priority is enabled/enforced by the broker for that destination.
- On what interval TTL is swept, and whether expired messages are moved to a dead-letter queue or discarded.
- Whether client-sent QoS values are overridden by broker policies.
- Whether transaction, acknowledgement, and redelivery policies align with business requirements.

Do not infer broker behavior solely from getter values on `JmsTemplate`. When confirmation is needed, send a test message through the real provider and inspect the headers set by the provider such as `JMSDeliveryMode`, `JMSPriority`, and `JMSExpiration`.

## 9. Common Mistakes

1. **Calling `setPriority(8)` but forgetting to enable explicit QoS.** `JmsTemplate` may still use provider- or administrator-configured defaults.
2. **Assuming persistent guarantees business-layer exactly-once processing.** Delivery mode does not replace transactions, acknowledgement, and idempotency.
3. **Assuming non-persistent is always lost on broker restart.** JMS allows the provider to retain it, though it does not require writing to stable storage; the application must accept the risk of loss.
4. **Assuming priority 9 is always delivered before all other messages.** The provider only has to make a best-effort prioritization, not enforce strict ordering.
5. **Using TTL as a consumer processing timeout.** TTL applies to how long a message waits to be delivered, and does not automatically abort processing once started.
6. **Setting TTL to 0 expecting immediate expiration.** In JMS, 0 means never expires.
7. **Directly editing `JMSExpiration`, `JMSPriority`, or `JMSDeliveryMode` on the message.** These are set by the provider on send; configure via the producer, JmsTemplate, or JmsClient.
8. **Assuming expired messages always emit a notification.** JMS does not define a standard notification for expiration.
9. **Mutating QoS on a shared template after the application is running.** Finish configuring before sharing the template; use `JmsClient` when per-operation QoS is needed.
10. **Not checking broker policies.** The broker can override QoS or enforce its own retention limits.

## 10. Pre-Send Checklist

- Choose persistent if losing messages in transit is unacceptable.
- Choose non-persistent only when the business tolerates message loss.
- Set meaningful priorities from 0–9 and avoid marking every message urgent.
- Derive TTL from the business usefulness window; remember 0 means no expiration.
- With `JmsTemplate`, enable `explicitQosEnabled` or use `setQosSettings`.
- Use `JmsClient` when per-operation QoS is needed.
- Verify actual QoS and policies on the broker.
- Design acknowledgement, transactions, redelivery, and idempotency independently of delivery mode.

## 11. References

- [Spring Framework – Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework – JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework – JmsClient Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsClient.html)
- [Spring Framework – QosSettings Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/QosSettings.html)
- [Jakarta Messaging – DeliveryMode Javadoc](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/deliverymode)
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.pdf)
