# Configuring explicitQosEnabled, deliveryMode, priority, and timeToLive in Spring JMS

When sending messages with JMS, a producer can specify three QoS (Quality of Service) attributes:

- **deliveryMode:** instructs the provider whether to persist the message durably or allow non-persistent delivery.
- **priority:** message priority level, from 0 to 9.
- **timeToLive:** duration the message remains valid, in milliseconds.

In Spring Framework, `JmsTemplate` provides setters to configure these three values. However, there is a flag that determines whether those values are actually passed into the send operation: `explicitQosEnabled`.

This is the most common configuration pitfall: setting `deliveryMode`, `priority`, and `timeToLive` alone is not enough. You must set `explicitQosEnabled=true`, or use `setQosSettings` so Spring enables this flag automatically.

## 1. The Four Properties and Their Meanings

### explicitQosEnabled

`explicitQosEnabled` controls how `JmsTemplate` invokes JMS `MessageProducer`:

- When `false`, Spring calls `MessageProducer.send(message)`. The provider uses the producer's default QoS.
- When `true`, Spring calls `MessageProducer.send(message, deliveryMode, priority, timeToLive)`. The three values configured on the template are passed explicitly on the send.

The default value of `explicitQosEnabled` is `false`.

Therefore, if you only call:

```java
template.setPriority(8);
template.setTimeToLive(30_000);
```

these values are stored on `JmsTemplate`, but are not used as QoS parameters on send while the explicit flag remains `false`.

### deliveryMode

JMS defines two constants in `jakarta.jms.DeliveryMode`:

| Constant | Value | Meaning |
| --- | ---: | --- |
| `DeliveryMode.PERSISTENT` | 2 | Requests the provider to store the message in durable storage |
| `DeliveryMode.NON_PERSISTENT` | 1 | Does not require the provider to store the message in durable storage |

In Spring there are two ways to set it:

```java
template.setDeliveryMode(DeliveryMode.PERSISTENT);
template.setDeliveryPersistent(true);
```

`setDeliveryPersistent(true)` is equivalent to choosing `PERSISTENT`; `false` is equivalent to `NON_PERSISTENT`.

Choose persistent for commands or events that must not be lost while in transit through the provider. Choose non-persistent for data that can be regenerated or where loss during a broker failure is acceptable. Delivery mode does not replace transactions, acknowledgement, or consumer-side idempotency.

### priority

Priority is an integer from 0 to 9:

- `0`: lowest.
- `9`: highest.
- JMS default: `4`.

Example:

```java
template.setPriority(7);
```

Priority is a hint to the provider when selecting the next message to deliver. It does not guarantee strict ordering or preemption of a message a consumer is already processing. Brokers may have their own policies for applying priority.

Define a priority convention in your application, such as 0–2 for background tasks, 3–4 for normal work, and 5–9 for work needing earlier processing. Avoid assigning the highest level to every message.

### timeToLive

TTL is the message's lifetime, measured in milliseconds:

```java
template.setTimeToLive(30_000); // 30 seconds
```

- `0`: the message does not expire.
- `5_000`: expires after approximately 5 seconds.
- `60_000`: expires after approximately 1 minute.

The provider uses TTL to determine the expiration time. Messages that expire while awaiting delivery should be discarded according to provider policy. TTL is not a processing timeout: it does not stop a consumer if the consumer has already received the message and is processing it.

## 2. Default Values of JmsTemplate

In Spring Framework 7.0.10, the defaults of `JmsTemplate` are:

| Property | Default Value |
| --- | --- |
| `deliveryMode` | `DeliveryMode.PERSISTENT` (2) |
| `priority` | `4` |
| `timeToLive` | `0` |
| `explicitQosEnabled` | `false` |

The key point is that these getter values do not mean Spring always passes them to the producer. When `explicitQosEnabled=false`, Spring invokes the `send(message)` overload, letting the producer/provider use its default QoS.

JMS producers typically default to persistent, priority 4, and TTL 0. However, a broker may apply its own policies or override client-requested QoS. If you need to ensure the application sends a specific QoS set, enable explicit QoS and verify behavior on a real provider.

## 3. Explicit Configuration via Setters

Example configuring a template dedicated to an orders queue:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.jms.core.JmsTemplate;

JmsTemplate template = new JmsTemplate(connectionFactory);

template.setDeliveryMode(DeliveryMode.PERSISTENT);
template.setPriority(7);
template.setTimeToLive(60_000);

// Enable so Spring passes the three values above into MessageProducer.send(...).
template.setExplicitQosEnabled(true);
```

Once configured, send calls using the template apply this QoS set:

```java
template.convertAndSend("orders", orderCreated);
```

You can also use the shorter form:

```java
template.setDeliveryPersistent(true);
template.setPriority(7);
template.setTimeToLive(60_000);
template.setExplicitQosEnabled(true);
```

`setDeliveryPersistent(true)` sets the delivery mode to `PERSISTENT`; it does not enable `explicitQosEnabled` by itself.

### Registering as a Spring bean

In a Spring application, configure the template once before sharing it with services:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class JmsConfiguration {

    @Bean
    JmsTemplate ordersJmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);

        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setPriority(7);
        template.setTimeToLive(60_000);
        template.setExplicitQosEnabled(true);

        return template;
    }
}
```

Services inject this `JmsTemplate` and send messages to the corresponding destination. Avoid mutating QoS setters per request on a shared template, because multiple threads may send concurrently and share that configuration.

## 4. Using QosSettings to Configure All Three Values

Spring provides `org.springframework.jms.support.QosSettings` to bundle delivery mode, priority, and TTL into a single object:

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

Important detail: in Spring Framework 7.0.10, `setQosSettings(settings)`:

1. Checks that settings is not null.
2. Automatically calls `setExplicitQosEnabled(true)`.
3. Assigns delivery mode.
4. Assigns priority.
5. Assigns time to live.

Therefore, you do not need to call `setExplicitQosEnabled(true)` again after `setQosSettings`.

Use `QosSettings` when you want to group a QoS set into a readable configuration or pass a configuration bundle between components. The values remain template-level configuration; that template applies the same QoS set to sends made through it.

## 5. How Spring Actually Sends the Message

Logically, `JmsTemplate`'s send step is equivalent to:

```java
if (template.isExplicitQosEnabled()) {
    producer.send(
            message,
            template.getDeliveryMode(),
            template.getPriority(),
            template.getTimeToLive()
    );
}
else {
    producer.send(message);
}
```

This is pseudo-code illustrating the branching logic, not a replacement for Spring's internal implementation.

| explicitQosEnabled | JMS Overload Invoked | QoS Source |
| --- | --- | --- |
| `false` | `send(message)` | Producer/provider default |
| `true` | `send(message, deliveryMode, priority, timeToLive)` | Values configured on `JmsTemplate` |

This distinction explains why an application can read getters showing `priority=8` yet outgoing messages still have the default priority if the explicit flag was not enabled.

If the broker has an override policy, the final values applied by the broker may still differ from what the client sent. Template getters only reflect Spring-side configuration, not proof that the broker applied them.

## 6. Configuring Per-Send QoS with JmsClient

If messages within the same application need different QoS, Spring Framework 7.0+ provides the fluent `JmsClient` API. Each operation can specify its own QoS:

```java
import org.springframework.jms.core.JmsClient;

JmsClient client = JmsClient.create(connectionFactory);

client.destination("orders")
        .withDeliveryPersistent(true)
        .withPriority(8)
        .withTimeToLive(30_000)
        .send(urgentOrder);

client.destination("telemetry")
        .withDeliveryPersistent(false)
        .withPriority(2)
        .withTimeToLive(5_000)
        .send(telemetryEvent);
```

In this example:

- The message sent to `orders` is persistent, priority 8, TTL 30 seconds.
- The message sent to `telemetry` is non-persistent, priority 2, TTL 5 seconds.

Operations carry their own settings without mutating setters on a shared `JmsTemplate`. The example requires a valid `ConnectionFactory` and destinations configured on the provider. This is an API example; the configuration-checking program in the next section does not connect to a broker.

## 7. Java 17+ Example: Checking QoS Values

The following example verifies the defaults, setting setters before explicit is enabled, enabling explicit, and using `QosSettings`. It does not require a broker because it only reads configuration stored on `JmsTemplate`.

Create `src/main/java/JmsTemplateQosDemo.java`:

```java
import jakarta.jms.DeliveryMode;
import org.springframework.jms.core.JmsClient;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.QosSettings;

public class JmsTemplateQosDemo {

    private static String modeName(int mode) {
        return switch (mode) {
            case DeliveryMode.PERSISTENT -> "PERSISTENT";
            case DeliveryMode.NON_PERSISTENT -> "NON_PERSISTENT";
            default -> "UNKNOWN(" + mode + ")";
        };
    }

    private static void print(String label, JmsTemplate template) {
        System.out.println(label + ".deliveryMode="
                + modeName(template.getDeliveryMode()));
        System.out.println(label + ".priority=" + template.getPriority());
        System.out.println(label + ".timeToLiveMs="
                + template.getTimeToLive());
        System.out.println(label + ".explicitQosEnabled="
                + template.isExplicitQosEnabled());
    }

    // Requires a JmsClient configured with a provider to actually send.
    static void sendUrgent(JmsClient client, String payload) {
        client.destination("orders")
                .withDeliveryPersistent(true)
                .withPriority(8)
                .withTimeToLive(30_000)
                .send(payload);
    }

    public static void main(String[] args) {
        JmsTemplate template = new JmsTemplate();
        print("default", template);

        template.setDeliveryMode(DeliveryMode.NON_PERSISTENT);
        template.setPriority(7);
        template.setTimeToLive(60_000);
        print("configuredWithoutExplicit", template);

        template.setExplicitQosEnabled(true);
        print("explicit", template);

        template.setQosSettings(new QosSettings(
                DeliveryMode.PERSISTENT, 9, 5_000));
        print("qosSettings", template);
    }
}
```

Create `pom.xml` in the root directory:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>jms-template-qos-demo</artifactId>
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
                    <mainClass>JmsTemplateQosDemo</mainClass>
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
default.deliveryMode=PERSISTENT
default.priority=4
default.timeToLiveMs=0
default.explicitQosEnabled=false
configuredWithoutExplicit.deliveryMode=NON_PERSISTENT
configuredWithoutExplicit.priority=7
configuredWithoutExplicit.timeToLiveMs=60000
configuredWithoutExplicit.explicitQosEnabled=false
explicit.deliveryMode=NON_PERSISTENT
explicit.priority=7
explicit.timeToLiveMs=60000
explicit.explicitQosEnabled=true
qosSettings.deliveryMode=PERSISTENT
qosSettings.priority=9
qosSettings.timeToLiveMs=5000
qosSettings.explicitQosEnabled=true
```

The output shows that calling the three setters does not automatically enable explicit QoS. `setQosSettings`, on the other hand, automatically enables the flag and replaces all three values.

## 8. Choosing the Right Configuration

| Need | How to Configure |
| --- | --- |
| A shared QoS set for all messages sent by a template | Three setters + `setExplicitQosEnabled(true)` |
| Grouping delivery mode, priority, and TTL into one object | `setQosSettings(new QosSettings(...))` |
| Different QoS per send | `JmsClient` with `withDeliveryPersistent`, `withPriority`, `withTimeToLive` |
| Using the JMS provider's defaults | Keep `explicitQosEnabled=false` and do not expect template QoS setters to apply |

If several fixed QoS profiles are needed for different message classes, you can create multiple separately configured `JmsTemplate` beans. If QoS varies per operation, use `JmsClient` or a dedicated message-sending abstraction with explicit per-send settings.

Do not mutate setters on a shared `JmsTemplate` immediately before each send to simulate per-message QoS. Multiple threads can send concurrently and observe values at different points.

## 9. Notes on Providers and Expiration

### Providers may apply their own policies

`explicitQosEnabled=true` ensures Spring calls the send overload with the three QoS parameters. It does not guarantee the broker ignores administrative policies. A broker may cap priority, enforce expiration policies, or override delivery behavior. Verify actual messages on the broker and destination configuration.

### TTL is not a consumer timeout

TTL measures how long a message remains valid while awaiting delivery. Once a consumer has received the message, TTL does not interrupt running logic. Use a separate timeout in the service/consumer if processing duration must be bounded.

### TTL and delivery delay are independent

Spring JMS also has `setDeliveryDelay(long)` in versions supporting JMS 2.0. Delivery delay defines the earliest time the provider may deliver the message; TTL defines when the message expires. Do not use TTL as a substitute for delayed scheduling.

### Transactions do not reset TTL

With a transacted session, TTL is measured from the moment the client sends the message. If the transaction commits late, part of the TTL has already elapsed before the message becomes visible to consumers.

## 10. Common Pitfalls

1. **Setting priority or TTL while forgetting to enable explicit QoS.** The template still calls `send(message)`, so producer/provider defaults are used.
2. **Thinking `setDeliveryPersistent(true)` enables explicit QoS.** This setter only changes the delivery mode.
3. **Confusing `deliveryMode` with acknowledgement mode.** Delivery mode controls durability while the provider transports the message; acknowledgement mode controls consumer receipt confirmation.
4. **Setting priority outside the 0–9 range.** JMS specifies ten priority levels; use constants or validated values.
5. **Setting TTL in seconds instead of milliseconds.** For example, 30 seconds must be passed as `30_000`.
6. **Using TTL 0 expecting immediate expiration.** In JMS, TTL 0 means no expiration.
7. **Assuming template getters prove the broker accepted that QoS.** Getters only reflect Spring configuration; the broker may apply different policies.
8. **Sharing one template and mutating QoS before every send.** Shared mutable configuration can create race conditions across threads.
9. **Using TTL as a processing timeout.** TTL does not stop a consumer after the message has been delivered.
10. **Configuring `QosSettings` and then unintentionally calling individual setters afterward.** Later setters partially overwrite values in the configured QoS bundle.

## 11. Pre-Send Checklist

- Choose delivery mode based on tolerance for message loss.
- Choose priority within 0–9 and define a shared convention.
- Choose TTL based on how long old messages remain business-valid; remember the unit is milliseconds.
- Decide whether to use provider defaults or pass explicit QoS.
- If using individual setters, set `explicitQosEnabled=true`.
- If using `QosSettings`, remember it enables explicit QoS automatically.
- Use `JmsClient` or separate templates when different QoS profiles are needed.
- Verify policies and actual values on the broker.
- Monitor expired messages, priority, redeliveries, and send failures in integration environments.

## 12. References

- [Spring Framework – JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework – QosSettings Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/QosSettings.html)
- [Spring Framework – JmsClient Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsClient.html)
- [Jakarta Messaging – MessageProducer Javadoc](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer)
- [Jakarta Messaging – DeliveryMode Javadoc](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/deliverymode)
