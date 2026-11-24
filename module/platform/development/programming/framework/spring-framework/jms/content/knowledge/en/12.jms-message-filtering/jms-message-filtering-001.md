# Message Selectors and Filterable Headers/Properties in Spring JMS

## 1. Real-world problem and goals

In a JMS Queue or Topic, systems often send multiple types of messages, while each consumer only needs to process a subset. For example:

- The invoicing service only processes `eventType='INVOICE'`.
- A worker serving the European region only cares about `region='EU'`.
- A high-value task requires `amount >= 100` and `ready = TRUE`.
- A process replying to a request needs `JMSCorrelationID='order-42'`.

A **Message selector** is a condition provided by the consumer to the Jakarta Messaging provider when creating a consumer or subscription. Only messages with matching headers/properties are delivered to that consumer. It is useful when a destination contains multiple message types and you want to filter **before the application processing step**, instead of invoking the handler and then using `if` to discard them.

Goals: understand the path of a selector; identify exactly which JMS headers can be used; attach properties with the right types, SQL92 expressions, NULL, and three-valued logic; implement Spring `JmsTemplate` and `@JmsListener`; distinguish between Queue and Topic; and run a Java 17 example on an Artemis broker.

**The most important rule:** a selector can reference certain **JMS message properties** and **six standard JMS headers**; **it does not read JSON/XML/binary bodies**. A SQL selector is not a full database query SQL.

## 2. Where is a selector evaluated?

~~~text
Producer sends JMS Message
   ├── Header: JMSCorrelationID, JMSType, JMSPriority, ...
   ├── Properties: eventType, region, amount, ready, ...
   └── Body: JSON / Text / Bytes / Object ...
          |
          v
    JMS Queue / Topic
          |
          v
  Provider evaluates selector
    ├── TRUE                -> message can be delivered to consumer
    └── FALSE or UNKNOWN    -> not delivered to that consumer
~~~

A consumer with the selector:

~~~sql
eventType = 'INVOICE' AND region = 'EU'
~~~

will receive messages that have the **JMS properties** `eventType=INVOICE` and `region=EU`. If the body is `{"eventType":"INVOICE","region":"EU"}` but the JMS properties do not contain these names, the selector **does not match**.

Selectors help the provider reduce unnecessary data transmission, but they do **not** validate schemas or access permissions. A producer might attach the wrong property or use a data type different from the contract. The consumer must still verify the body, authorization, idempotency, business rules, transactions, and retries.

## 3. Headers, properties, and body have different roles

~~~text
JMS Message
├── Headers defined by JMS
│   ├── JMSMessageID
│   ├── JMSCorrelationID
│   ├── JMSPriority
│   ├── JMSDeliveryMode
│   ├── JMSTimestamp
│   ├── JMSType
│   ├── JMSExpiration, JMSReplyTo, JMSDeliveryTime...
│   └── JMSDestination, JMSRedelivered...
├── Properties (attached before send)
│   ├── eventType = "INVOICE"    [String]
│   ├── region = "EU"            [String]
│   ├── amount = 130             [int]
│   ├── ready = true             [boolean]
│   └── JMSXGroupID = "billing"  [JMS-defined]
└── Body
    └── {"orderId":"O-21", "items":[...]}
~~~

In Spring JMS, use `MessagePostProcessor` to add properties after the converter creates the `Message`:

~~~java
// Code snippet in a service that has JmsTemplate injected.
jmsTemplate.convertAndSend("orders.events", jsonPayload, message -> {
    message.setStringProperty("eventType", "INVOICE");
    message.setStringProperty("region", "EU");
    message.setIntProperty("amount", 130);
    message.setBooleanProperty("ready", true);
    return message;
});
~~~

Here `jsonPayload` is already available in the service. For the selector `amount >= 100`, the `amount` property is sent as an **int** type, not the String "130". The message body and JMS property may share the same meaning, but the broker does not automatically extract JSON fields into properties.

## 4. The exact six JMS headers filterable by a standard selector

According to Jakarta Messaging 3.1, referencing **standard headers** in a selector is limited to:

| Header | Type in selector | Example | Key point |
|---|---|---|---|
| `JMSDeliveryMode` | String `'PERSISTENT'` / `'NON_PERSISTENT'` | `JMSDeliveryMode = 'PERSISTENT'` | Although the Java API uses int constants, the selector uses strings. |
| `JMSPriority` | Number 0–9 | `JMSPriority >= 7` | Broker priority may be subject to policy and does not guarantee absolute processing order. |
| `JMSMessageID` | Provider-generated String | `JMSMessageID = 'ID:...'` | Cannot be self-assigned before send; the actual ID is needed if filtering by message ID. |
| `JMSTimestamp` | Long integer epoch millis | `JMSTimestamp > 1700000000000` | Can be disabled and equal to 0; not identical to the business date. |
| `JMSCorrelationID` | String or NULL | `JMSCorrelationID = 'order-42'` | Usually set by the producer, used for request/reply correlation. |
| `JMSType` | String or NULL | `JMSType = 'invoice.v1'` | Header attached by the producer, not automatically the Java class name. |

**Headers that cannot be used directly in a standard JMS selector:** `JMSDestination`, `JMSReplyTo`, `JMSExpiration`, `JMSDeliveryTime`, and `JMSRedelivered`. Some have getters on `jakarta.jms.Message`, but **having a getter does not mean a selector can reference it**.

Non-portable examples:

~~~sql
JMSExpiration > 1700000000000
JMSDeliveryTime < 1700000100000
JMSRedelivered = TRUE
~~~

Do not infer from header names in application documentation and write arbitrary selectors. If a vendor has proprietary extensions, mark them as vendor-dependent and test against the actual broker version.

### 4.1. Common pitfall: JMSDeliveryMode

~~~java
producer.send(message, jakarta.jms.DeliveryMode.PERSISTENT, 4, 60_000L);
~~~

This is a JMS API snippet with `producer` and `message` already available. The value `DeliveryMode.PERSISTENT` is an integer constant when calling the API, but the selector uses:

~~~sql
JMSDeliveryMode = 'PERSISTENT'
~~~

not a comparison with `2`. `JMSPriority`, by contrast, uses numeric comparison such as `JMSPriority > 4`.

### 4.2. Correlation ID and JMSType

~~~java
message.setJMSCorrelationID("request-729");
message.setJMSType("invoice.v1");
~~~

Both of these headers can be set by the producer before send and used in a selector. If a system uses `JMSType`, `eventType`, and a separate type id for the JSON converter, clearly document the contract of each field. They do not stay synchronized with one another automatically.

## 5. Filterable message properties

According to Jakarta Messaging, a property value can be `boolean`, `byte`, `short`, `int`, `long`, `float`, `double`, or `String`.

| Property sent by producer | Valid condition |
|---|---|
| `setStringProperty("region", "EU")` | `region = 'EU'` |
| `setStringProperty("eventType", "INVOICE")` | `eventType IN ('INVOICE', 'REFUND')` |
| `setIntProperty("amount", 130)` | `amount >= 100` |
| `setLongProperty("createdAt", 1730000000000L)` | `createdAt >= 1720000000000` |
| `setBooleanProperty("ready", true)` | `ready = TRUE` |
| `setDoubleProperty("score", 0.8)` | `score > 0.5` |

A JMS message property name must be a valid **selector identifier** following Java identifier rules; use readable CamelCase/lowerCamelCase names like `eventType`, `region`, `orderCount`. Do not use names with spaces or hyphens if you want to reference them with a standard selector. Property names are case-sensitive: `eventType` differs from `EventType`.

Three categories of properties by name:
1. **Application-defined:** do not start with `JMS`, such as `eventType`, `tenantRegion`.
2. **JMSX-defined:** start with `JMSX`, for example `JMSXGroupID`, `JMSXDeliveryCount`.
3. **Provider-specific:** follow the `JMS_<vendor>` convention or proprietary names published by the provider.

Applications should agree on **name + type + meaning** for each property as part of the message contract. Changing `amount` from `int` to `String` or `eventType` to `EventType` can cause old selectors to stop matching even when the Java consumer does not change.

### JMSXGroupID and JMSXDeliveryCount are different

- `JMSXGroupID` is a property used to identify a message group and can be attached by the client before send. Consumer grouping/affinity still depends on the broker, not an automatic consequence of the selector.
- `JMSXDeliveryCount` is a **required** property set by the provider when the message is received: usually 1 on the first delivery, and 2 or higher on redelivery. Although it belongs to the JMSX properties family, the specification states that **the effect of using a selector on a property set by the provider upon receive is undefined**.

Therefore, **do not** select messages with:

~~~sql
JMSXDeliveryCount >= 3
~~~

to implement a portable retry/DLQ policy. You can read the count in the consumer for logging/diagnostics; limiting redelivery attempts should be configured on the provider/broker or a controlled retry layer.

## 6. Syntax: a subset of SQL92

A JMS selector is a conditional expression string, **not** a query with `SELECT`, `FROM`, `WHERE`, joins, or JSON queries.

### 6.1. Common operators

~~~sql
eventType = 'INVOICE'
eventType <> 'REFUND'
amount >= 100
ready = TRUE
eventType = 'INVOICE' AND region = 'EU'
region = 'EU' OR region = 'APAC'
NOT (ready = TRUE)
(eventType = 'INVOICE' OR eventType = 'REFUND') AND amount > 0
~~~

Comparison operators `=`, `<>`, `>`, `>=`, `<`, `<=`, logical operators `AND`, `OR`, `NOT`, and parentheses all have their selector meanings. Operator precedence determines the result; when there are two business condition groups, use parentheses to avoid ambiguity. Operator keywords are case-insensitive, while identifiers are case-sensitive.

**Note on quotes:** String literals use **single quotes**, for example `'EU'`; do not use `"EU"`. The string `'EU'` differs from `'eu'`; if normalization is needed, normalize the property when sending.

### 6.2. IN, BETWEEN, and LIKE

~~~sql
eventType IN ('INVOICE', 'REFUND', 'CANCEL')
amount BETWEEN 100 AND 500
orderCode LIKE 'INV-%'
orderCode LIKE 'INV_'
orderCode LIKE 'AB#_%' ESCAPE '#'
~~~

- `IN` works with a set of String literals.
- `BETWEEN` is inclusive of both the lower and upper bounds; `amount BETWEEN 100 AND 500` matches numeric values from 100 to 500.
- `LIKE` is for Strings; `%` represents any sequence of characters (possibly empty), and `_` represents exactly one character.
- `ESCAPE '#'` designates `#` to escape wildcards. The pattern `'AB#_%'` matches strings starting with literal `AB_`, followed by any sequence of characters.

If you need to match a string containing a single quote, double the quote inside the literal:

~~~sql
customerName = 'O''Brien'
~~~

Do not concatenate user input directly into a selector without control. JMS selectors do not have JDBC `?` bind parameters. Use fixed selectors, an enum/value allowlist, or a safe expression builder with proper escaping.

### 6.3. Property types are preserved, no automatic casting

Common mismatch:

~~~java
message.setStringProperty("amount", "130");
~~~

and the selector:

~~~sql
amount > 100
~~~

The `amount` property has type String, while numeric comparison requires numeric. **The type conversion rules of `getIntProperty()` methods do not apply to selector expressions.** Send it with `setIntProperty("amount", 130)` if the contract requires numeric comparison.

Similarly, `setStringProperty("ready", "true")` is not the same as `setBooleanProperty("ready", true)`. For `ready = TRUE` to work, the property must be sent as a boolean type. All producers writing to the same Queue/Topic must agree on data types.

### 6.4. Syntax errors are reported when setting up the consumer

The provider must validate selector syntax when the application supplies the expression. With a selector such as:

~~~sql
amount >=
~~~

The JMS API throws `InvalidSelectorException`. When using Spring, the checked JMS exception may be converted by Spring into an unchecked `JmsException`; errors may occur when the listener container starts up or when recreating the consumer. Therefore, fixed selectors should be integration-tested before deployment.

## 7. NULL and three-valued logic

If a property **does not exist** in a message, the selector treats it as NULL. Comparisons with NULL usually evaluate to **UNKNOWN**. A message is selected only when the expression evaluates to TRUE.

| Expression | When region property is missing | Result |
|---|---|---|
| `region = 'EU'` | No region | UNKNOWN |
| `region <> 'EU'` | No region | UNKNOWN |
| `NOT (region = 'EU')` | No region | UNKNOWN |
| `region IS NULL` | No region | TRUE |
| `region IS NOT NULL` | No region | FALSE |
| `region = 'EU' OR region IS NULL` | No region | TRUE |

A very important consequence: `NOT UNKNOWN` is still UNKNOWN; `TRUE AND UNKNOWN` is UNKNOWN; `FALSE AND UNKNOWN` is FALSE; `TRUE OR UNKNOWN` is TRUE.

If you intend to receive messages "not belonging to EU" **including messages without a region**, write explicitly:

~~~sql
region <> 'EU' OR region IS NULL
~~~

If you only want messages that have an explicit region other than EU:

~~~sql
region IS NOT NULL AND region <> 'EU'
~~~

Do not assume a missing property turns into Java defaults like `0`, `false`, or an empty string. The three states TRUE/FALSE/UNKNOWN help prevent conditions from accidentally selecting or excluding the wrong data.

## 8. Should you filter by header or application property?

| Need | Suitable approach | Why |
|---|---|---|
| Event type | `eventType`, `schemaVersion` | Clear business contract, independent of Java class. |
| Region, task category | `region`, `category` | Allows producer/consumer to agree on an enum. |
| Business priority level | `businessPriority` | Independent of broker QoS; only compare with JMSPriority if you actually want QoS. |
| A specific request/reply | `JMSCorrelationID` | Standard header for linking flows. |
| By delivery mode | `JMSDeliveryMode` | Has two special strings PERSISTENT/NON_PERSISTENT. |
| Classifying excessive redeliveries | Read `JMSXDeliveryCount` in the handler | Do not use a selector on a receive-time property as a portable policy. |
| Field nested deep in JSON | Promote to a JMS property if filtering is truly needed, or split destinations | The broker does not parse JSON bodies for selectors. |

Copy a field from the body to a JMS property only when needed: the producer must keep them **consistent**. For example, having `region=US` in the body while the property is `region=EU` will cause the EU consumer to receive a message outside its expected flow.

## 9. Spring JmsTemplate: receiveSelected and receiveSelectedAndConvert

Synchronously receive a message with a selector:

~~~java
// Code snippet inside a service that has JmsTemplate injected.
jakarta.jms.Message message = jmsTemplate.receiveSelected(
        "orders.events", "eventType = 'INVOICE' AND amount >= 100");
~~~

If you need to receive and convert the body via the template's MessageConverter:

~~~java
Object object = jmsTemplate.receiveSelectedAndConvert(
        "orders.events", "region = 'APAC'");
~~~

**Distinctions:**
- `receiveSelected` returns `jakarta.jms.Message`, giving access to `JMSCorrelationID`, `getIntProperty`, `getStringProperty`, and the body.
- `receiveSelectedAndConvert` returns a Java payload; it does not keep the raw Message in the result, so if you need headers/properties, choose an appropriate API/adapter.
- `receiveTimeout` is configured on `JmsTemplate`; when the timeout expires with no matching message, it returns `null`. Avoid changing `setReceiveTimeout` on a singleton per request.
- With a String destination name, the template must be configured with the right Queue/Topic mode (`pubSubDomain`); a name alone does not prove the destination type.
- Do not use synchronous receive inside a web request if it can block for a long time without a timeout/capacity plan.

For applications receiving messages continuously, `@JmsListener` and a listener container are usually more appropriate than writing an infinite `receiveSelected` loop.

## 10. @JmsListener(selector=...) for asynchronous consumers

Spring supports declaring a selector directly on the annotation:

~~~java
package example.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class EuropeanInvoiceConsumer {
    @JmsListener(
            destination = "orders.events",
            selector = "eventType = 'INVOICE' AND region = 'EU'")
    public void process(String payload) {
        System.out.println("EU invoice: " + payload);
    }
}
~~~

This is a standalone consumer component, requiring JMS infrastructure/`@EnableJms` or appropriate Spring Boot configuration and a broker with the `orders.events` destination. **Do not enable this component at the same time as the synchronous receive demo below** if you want deterministic output: consumers on the same Queue can compete for messages.

The selector can be configured via environment properties:

~~~yaml
app:
  messaging:
    orders-queue: orders.events
    eu-selector: "eventType = 'INVOICE' AND region = 'EU'"
~~~

Inside the `@Component` class:

~~~java
@JmsListener(
    destination = "${app.messaging.orders-queue}",
    selector = "${app.messaging.eu-selector}")
public void processEuropeanInvoice(String payload) {
    System.out.println(payload);
}
~~~

Spring resolves placeholders for annotation attributes when registering the listener endpoint. Changing the configuration file while the listener is running does **not** automatically guarantee that every consumer/subscription will be recreated with the new selector; lifecycle and migration must be managed according to the provider.

For production:
- Configure `DefaultJmsListenerContainerFactory`/transactions, concurrency, destination resolver, and converter according to the contract.
- `selector` does not govern transactions, ACK, retries, or DLQ.
- Do not trust selectors as authorization; message properties may be set incorrectly or intentionally spoofed by another producer.
- For Topics, the selector applies per subscription rather than all subscribers sharing a single Queue cursor.

## 11. Spring Boot and embedded Artemis demo using real selectors

The example runs with Java 17, Spring Boot 3.5.16 (Spring Framework 6 branch), and embedded Artemis. Goal: send three messages to a Queue and use three different selectors to receive them. There are no competing listeners and each selector matches only one message, so the output does not depend on broker delivery priority order.

**Project structure:**

~~~text
jms-selector-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/jms/SelectorLabApplication.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-selector-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'

    // Needed only to run the embedded Artemis broker in the lab.
    runtimeOnly 'org.apache.activemq:artemis-jakarta-server'
}
~~~

Spring Boot 3.5.16 is the final release with OSS support in the 3.5.x line (June 2026). This is a fixed milestone for the lab; production projects should choose a supported Boot/JDK branch according to the application lifecycle and corresponding BOM.

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: embedded
    embedded:
      queues: demo.selector
      persistent: false
~~~

`src/main/java/example/jms/SelectorLabApplication.java`:

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class SelectorLabApplication {
    private static final String QUEUE = "demo.selector";

    public static void main(String[] args) {
        SpringApplication.run(SelectorLabApplication.class, args);
    }

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setReceiveTimeout(2_000L);
        return template;
    }

    @Bean
    ApplicationRunner runCases(JmsTemplate template) {
        return args -> {
            publish(template, "invoice-eu",
                    "INVOICE", "EU", 130, true, "cid-eu");
            publish(template, "invoice-apac",
                    "INVOICE", "APAC", 85, false, "cid-apac");
            publish(template, "refund-apac",
                    "REFUND", "APAC", 65, true, "cid-refund");

            // Select the first message by type, amount, and boolean.
            printMatch(template,
                    "eventType = 'INVOICE' AND amount >= 100 "
                    + "AND ready = TRUE",
                    "invoice-eu");

            // This time the APAC invoice message is still in the Queue.
            printMatch(template,
                    "region = 'APAC' AND amount BETWEEN 80 AND 90",
                    "invoice-apac");

            // Combine standard header and app property.
            printMatch(template,
                    "JMSCorrelationID = 'cid-refund' "
                    + "AND eventType IN ('REFUND', 'REVERSAL')",
                    "refund-apac");

            Message remaining = template.receiveSelected(
                    QUEUE, "eventType = 'INVOICE'");
            if (remaining != null) {
                throw new IllegalStateException(
                        "Unexpected extra invoice message");
            }
            System.out.println("REMAINING=none");
        };
    }

    private static void publish(JmsTemplate template, String body,
            String eventType, String region, int amount,
            boolean ready, String correlationId) {

        template.convertAndSend(QUEUE, body, message -> {
            message.setStringProperty("eventType", eventType);
            message.setStringProperty("region", region);
            message.setIntProperty("amount", amount);
            message.setBooleanProperty("ready", ready);
            message.setJMSCorrelationID(correlationId);
            return message;
        });
    }

    private static void printMatch(JmsTemplate template,
            String selector, String expected) throws JMSException {

        Message message = template.receiveSelected(QUEUE, selector);
        if (!(message instanceof TextMessage text)) {
            throw new IllegalStateException(
                    "No TextMessage for selector: " + selector);
        }

        String actual = text.getText();
        if (!expected.equals(actual)) {
            throw new IllegalStateException(
                    "Expected " + expected + " but got " + actual);
        }

        System.out.println("MATCH=" + actual
                + "|eventType=" + message.getStringProperty("eventType")
                + "|amount=" + message.getIntProperty("amount"));
    }
}
~~~

**Code explanation:**
1. `convertAndSend` creates a `TextMessage` from the String payload using the default converter.
2. `MessagePostProcessor` attaches application properties with the proper types; `JMSCorrelationID` is a standard header.
3. The first consumer selects the EU invoice with amount=130 and ready=true. The second consumer selects the APAC invoice with amount=85. The third consumer filters by the `JMSCorrelationID` header and the `eventType` set.
4. Receives do not match other messages, while those other messages remain in the Queue for subsequent receives to select; they are not dropped.
5. `ApplicationRunner.run` is declared to throw Exception, so calling `getText()`/`getIntProperty()` with checked `JMSException` inside the helper still compiles validly.
6. One Runner executes sequentially, with no other listeners, without depending on delivery order for heterogeneous messages.

**Running:** in the project directory, use JDK 17+ and a compatible Gradle version. If the project has a Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If there is no Wrapper yet, you can use a pre-installed Gradle:

~~~bash
gradle bootRun
~~~

After the Spring Boot and Artemis log lines, the stdout **printed by the program itself** when all steps succeed is:

~~~text
MATCH=invoice-eu|eventType=INVOICE|amount=130
MATCH=invoice-apac|eventType=INVOICE|amount=85
MATCH=refund-apac|eventType=REFUND|amount=65
REMAINING=none
~~~

If a selector is wrong or receiving gets no message within 2 seconds, the code fails with a clear error. `persistent: false` is a lab choice and does not prove durability/HA/TLS. Do not copy single-consumer and ordering assumptions into multi-replica applications.

### Variations to try

- Change `setIntProperty("amount", amount)` to `setStringProperty("amount", Integer.toString(amount))`: the numeric selector stops matching.
- Change the selector to `eventType = 'invoice'`: the String literal differs from `'INVOICE'` and does not match.
- Try omitting `region` and using the selector `region IS NULL` or `region = 'EU' OR region IS NULL`.
- Attach `message.setJMSType("invoice.v1")` and filter with `JMSType = 'invoice.v1'`.
- Try invalid syntax `amount >=`: the consumer must report `InvalidSelectorException` instead of selecting randomly.
- Do not run the `EuropeanInvoiceConsumer` component in section 10 on the same Queue in this demo; it can compete and alter the output.

## 12. Low-level Jakarta Messaging API

Classic JMS allows creating a consumer with a selector:

~~~java
// Code snippet inside a callback with a real jakarta.jms.Session and Queue.
jakarta.jms.MessageConsumer consumer =
        session.createConsumer(queue,
                "region = 'EU' AND eventType = 'INVOICE'");
~~~

With the `JMSContext` API:

~~~java
// Code snippet when a real jakarta.jms.JMSContext and Queue are available.
jakarta.jms.JMSConsumer consumer =
        context.createConsumer(queue, "region = 'EU'");
~~~

When using the classic API, `Connection.start()` is required before receiving; `JmsTemplate` and Spring listener containers usually manage connections/sessions for you. Null or an empty selector string means **no filtering**.

Do not arbitrarily create/destroy new consumers per user request when high throughput is needed; consumer count and caching, subscription cost, query evaluation, and access permissions all affect operations. Use stable selectors for long-lived listeners, or choose explicit Queue/Topic routing models when workloads have many partitions.

## 13. Key differences between Queue and Topic

### Queue: unmatched messages are not automatically dropped

A JMS Queue can have multiple competing consumers. With selectors:
- The EU consumer only receives messages with `region='EU'`.
- The APAC consumer only receives messages with `region='APAC'`.
- A message with `region='US'` is **not** delivered to these two consumers; it can remain in the Queue for another consumer in the future, unless expiry/admin policies take effect.
- A consumer **without a selector** on the same Queue can receive messages intended for the EU/APAC groups, because it is also eligible. A selector does not "reserve ownership" of the entire Queue.

~~~text
Queue orders.jobs
├── Consumer EU:    region = 'EU'
├── Consumer APAC:  region = 'APAC'
└── Consumer ANY:   no selector

Message EU   -> EU or ANY (depending on broker distribution)
Message APAC -> APAC or ANY
Message US   -> ANY if present, otherwise may remain in Queue
~~~

JMS does not mandate a specific load-distribution strategy among multiple eligible consumers. When strict isolation, separate SLAs/backlogs/ACLs, or data residency are required, consider separate Queues/broker namespaces instead of relying solely on property filtering.

### Topic: selectors belong to subscriptions

With a Topic, each subscription receives copies of messages matching its selector at **publish time**; other subscriptions with matching selectors can simultaneously receive copies of the same message.

~~~text
Topic sales.order.events
  ├── subscription billing  (eventType = 'PAID')
  └── subscription analytics (region IN ('EU', 'APAC'))
~~~

If both subscriptions match, both can receive a copy. If a subscription is created **after** a message has already been published, a new selector does not turn it into a historical query. A durable subscription has its own identity and backlog; changing a selector or subscription name is not simply editing a single String line — it requires a migration plan and checking provider policies. Shared subscriptions across multiple replicas have load-sharing semantics within the same group, which is not equivalent to multiple independent subscriptions.

## 14. Selectors do not replace security, retries, or transactions

**Security:** properties like `tenantId` or `region` are values sent by the producer, so selectors cannot be treated as an authorization barrier. Use broker authentication/ACLs, separate namespaces or Queues, validate tenant ownership, and guard against input spoofing.

**Retry:** selectors do not handle redelivery, backoff, retry attempt limits, or DLQ. For rolled-back messages, transactions/ACK and broker redelivery policy govern behavior. `JMSXDeliveryCount` should be read after receiving; do not use a selector on a set-on-receive property as a portable policy.

**Stuck messages:** if all consumers have overly narrow selectors, messages can accumulate on the Queue for a long time. The broker does not automatically treat "no selector match" as an error to route to DLQ. Alerting is needed on Queue depth, message age, expiry, and active selectors/versions. If a producer changes a property from `eventType` to `EventType`, new messages can become unmatched without any obvious exception.

**Performance:** a message selector is not a SQL query with uniform indexing across all vendors. Performance impact depends on consumer count, predicate complexity, message rate, provider implementation, and protocol. Benchmark on the real broker; when thousands of filter groups or independent deliveries are needed, routing into separate Queues/Topics can be easier to manage.

## 15. Common errors and diagnostics

| Symptom | Common cause | Fix |
|---|---|---|
| JSON body has `region=EU` but listener does not receive | `region` was not attached as a JMS property. | Attach `setStringProperty("region","EU")` before send. |
| `amount >= 100` does not select `"130"` | Property is a String type, not int/long. | Fix the producer to use a numeric property. |
| `eventType='invoice'` does not match | Actual data is `INVOICE`; String literals are case-sensitive. | Standardize the enum. |
| `EventType` does not match `eventType` | Identifiers are case-sensitive. | Use one consistent name in the contract. |
| `NOT (region = 'EU')` does not receive messages missing region | UNKNOWN does not become TRUE under NOT. | Use `OR region IS NULL` if missing region should be included. |
| `JMSRedelivered=TRUE` or `JMSExpiration>...` is not portable | Not among the six standard selector headers. | Separate logic appropriately or use documented provider-specific features. |
| `JMSXDeliveryCount >= 3` is unreliable | Property is set upon receive; selector effect is undefined. | Configure retry/max attempts/DLQ on the broker. |
| Listener startup failure | Invalid selector syntax, wrong name/quotes/parentheses. | Test `InvalidSelectorException` and the string after placeholder resolution. |
| Queue backlog despite online consumer | No messages match, typo or wrong property type. | Inspect actual JMS properties, selectors, and broker metrics. |
| EU group receives non-EU messages | Another consumer has no selector or property data was spoofed. | Check all consumers on the Queue; use ACLs/partitioning if needed. |
| New Topic subscriber misses history | Subscription did not exist at publish time. | Provision durable subscriptions before publishing and manage migration. |

Do not look only at Java method names or payloads in logs. Inspect the raw JMS headers/properties of messages on the broker and compare them with the selector actually used by the container.

## 16. Essential test suite

A system using selectors should test:

1. Selector syntax is accepted by the provider; invalid selectors must fail clearly when creating the consumer.
2. `String`/`int`/`boolean` properties are sent with the right types; test wrong types to understand failures.
3. Missing properties, `IS NULL`/`IS NOT NULL`, `NOT`, and UNKNOWN logic.
4. Allowed headers (such as `JMSCorrelationID`, `JMSType`, `JMSPriority`) are set/read accurately.
5. Queue with two consumers having different selectors; with/without an unfiltered consumer; backlog when unmatched.
6. Topic with two matching subscriptions; durable/shared cases and subscriptions created after publishing.
7. Transaction rollback/ACK, retry/DLQ, and message expiry are not confused with selectors.
8. Security: messages with spoofed tenant/region properties do not bypass ACLs.
9. Observability: metrics for queue depth, eligible/unmatched, message age, DLQ, consumer count, and selector version.
10. Throughput with realistic selector/consumer counts; do not extrapolate performance from the embedded demo.

Store the **selector contract** in source control: destination, owner, Queue/Topic type, required properties/types, selector expression, subscription lifecycle, and change plan when the producer updates its schema. Unmatched selectors can stay silent for a long time without monitoring.

## 17. Self-check questions

**Question 1.** A JSON body has `{"region":"EU"}` but the message has no region property. Does `region = 'EU'` match?  
**Answer:** No. A missing property yields UNKNOWN; selectors do not read JSON bodies.

**Question 2.** The producer uses `setStringProperty("amount","130")`, and the consumer uses `amount >= 100`. Why is this wrong?  
**Answer:** A String property is not automatically converted to numeric in a selector; `setIntProperty`/`setLongProperty` must be used per the contract.

**Question 3.** `JMSPriority`, `JMSReplyTo`, `JMSDeliveryTime`, `JMSCorrelationID` — which headers are allowed in a standard selector?  
**Answer:** `JMSPriority` and `JMSCorrelationID`. The other two are not among the six allowed names.

**Question 4.** If region is missing, does `NOT (region = 'EU')` match?  
**Answer:** No. NOT UNKNOWN remains UNKNOWN; use `OR region IS NULL` if the business rule intends to include missing values.

**Question 5.** With a Queue having EU and APAC selectors, does a US message disappear automatically?  
**Answer:** Not solely because of the selector. It can stay in the Queue until another consumer arrives or expiry/admin policy applies. An unfiltered consumer can receive any eligible message.

**Question 6.** Should `JMSXDeliveryCount >= 3` be used as a listener condition?  
**Answer:** No. It is a property set by the provider upon receive; the specification does not define the outcome of using it as a selector. Configure redelivery/DLQ and observe the delivery count inside the handler.

**Question 7.** In Spring, what is the common way to receive asynchronously with a selector?  
**Answer:** `@JmsListener(destination=..., selector=...)` or a configured listener container. `JmsTemplate.receiveSelected` is the synchronous option with a timeout.

**Question 8.** Does a Topic subscription created after messages are published receive historical messages matching the new selector?  
**Answer:** There is no guarantee. Selectors are applied to subscriptions existing at the time the message is published; they do not create retroactive history.

## 18. Final checklist and official references

- [ ] Do not use the JSON body as a direct data source for selectors; attach the properties needed for filtering.
- [ ] Choose only from the six standard selector headers or appropriate application/JMSX properties.
- [ ] Identifier names, String/number/boolean types, NULL, quoting/escaping, and SQL92 syntax are all tested.
- [ ] Do not use `JMSXDeliveryCount` as a selector to decide retry/DLQ.
- [ ] Distinguish between competing Queue consumers and Topic subscriptions with message copies.
- [ ] Have transaction/ACK and redelivery policies, plus monitoring for unmatched messages.
- [ ] Store selector configuration in version control and evaluate it on the real provider/broker.
- [ ] Broker ACLs and tenant isolation do not rely on producer-set properties.

**References:**
- [Jakarta Messaging 3.1 specification — sections 3.8 Message selection, 3.5 Message properties, 4 Queue/Topic semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html).
- [Jakarta Messaging API — Message selectors](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message).
- [Spring Framework — Annotation-driven JMS listener endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html).
- [Spring Framework 6.2.14 JmsTemplate — receiveSelected](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html).
- [Spring JMS @JmsListener Javadoc — selector](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/jms/annotation/JmsListener.html).
- [Spring Boot 3.5 — JMS/Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html).
- [Spring Boot 3.5.16 release](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/).
