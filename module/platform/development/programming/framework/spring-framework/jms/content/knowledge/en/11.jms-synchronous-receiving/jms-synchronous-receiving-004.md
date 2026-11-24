# receiveSelected with Filter Expressions in Spring JMS

## 1. Objectives and problem statement

In Spring JMS, `JmsTemplate.receive(destination)` retrieves a message matching the specified destination. When a single Queue holds multiple event types, tenants, or business priority levels, an application sometimes wants to **synchronously receive only messages whose metadata satisfies a condition**.

`JmsTemplate.receiveSelected(destinationName, selector)` is the API for that scenario. It creates a JMS consumer with a **message selector**; the provider evaluates the selector against **JMS headers and JMS properties**, and delivers only matching messages to the consumer.

~~~java
Message message = jmsTemplate.receiveSelected(
        "orders.queue",
        "tenant = 'north' AND amount >= 100");
~~~

This is not a database query function, does not use SQL `SELECT`, and does not filter a JSON body. It is **a synchronous receive call that can block**, subject to the configured receive timeout.

Example:

~~~text
Queue orders.queue
  |
  +-- order-1: tenant=north; amount=50
  +-- order-2: tenant=north; amount=150
  +-- order-3: tenant=south; amount=300
  |
  v
receiveSelected(
  "orders.queue",
  "tenant = 'north' AND amount >= 100"
)
  |
  +-- Receives order-2
  +-- order-1, order-3 are not consumed by this consumer
~~~

In a **Queue**, non-matching messages can remain waiting for another consumer (or another receive call with a matching selector), per broker policy. Do not think of `receiveSelected` as calling `receive` to pull an arbitrary message and then discarding non-matching ones yourself.

Lesson objectives:

1. Understand Spring's `receiveSelected` and `receiveSelectedAndConvert` contracts.
2. Write selectors using comparisons, `AND`, `OR`, `NOT`, `IN`, `BETWEEN`, `LIKE`, and `IS NULL`.
3. Distinguish JMS properties/headers from the JSON body.
4. Handle property types, three-valued logic `TRUE/FALSE/UNKNOWN`, timeouts, and `null` results properly.
5. Build a runnable Spring Boot + Artemis + Java 17 example.
6. Analyze transactions/ACK, competing consumers, performance, security, and testing.

## 2. Where the API lives in Spring

`org.springframework.jms.core.JmsOperations` is the interface grouping JMS operations, while `org.springframework.jms.core.JmsTemplate` is the commonly used implementation. In Spring Framework 6:

| API | Return value | Meaning |
| --- | --- | --- |
| `receive(String destinationName)` | `jakarta.jms.Message` or `null` | Receive without a selector |
| `receiveSelected(String destinationName, String messageSelector)` | `Message` or `null` | Receive raw JMS message matching selector |
| `receiveSelectedAndConvert(String destinationName, String messageSelector)` | `Object` or `null` | Receive by selector and convert body with converter |
| `receiveSelected(String messageSelector)` | `Message` or `null` | Uses the configured **default destination** |
| `receiveSelectedAndConvert(String messageSelector)` | `Object` or `null` | Converts message from the default destination |
| `receiveSelected(Destination destination, String messageSelector)` | `Message` or `null` | Uses a JMS `Destination` object instead of a name |

**Overload note:** a call with **one** String such as `receiveSelected("tenant = 'north'")` takes the selector parameter, not the Queue name. To specify both Queue and filter, use the **two**-parameter overload.

These APIs belong to Spring JMS rather than the raw `jakarta.jms.MessageConsumer` API. Spring uses `ConnectionFactory`, `Session`, and `MessageConsumer` underneath and translates checked `JMSException` into runtime `org.springframework.jms.JmsException`.

~~~text
Application thread
      |
      v
JmsOperations / JmsTemplate
      |
      +-- ConnectionFactory and Session
      +-- MessageConsumer(destination, selector)
      |
      v
JMS broker/provider
      |
      +-- Selects matching message from headers/properties
      |
      v
Message or null on timeout
~~~

### 2.1. How does synchronous receiving differ from a listener?

- `receiveSelected` is actively called by an application thread; the thread may wait.
- `@JmsListener(selector = "...")` runs inside a Spring-managed listener container, suitable for continuous processing.
- Both can use the same JMS selector syntax, but resource lifecycles, wait times, and concurrency models differ.
- A successful `receiveSelected` call **consumes** the message per ACK/transaction policy; it is not a "peek" command.

## 3. Selectors inspect metadata only, not the JSON body

Producer sends JSON:

~~~java
jmsTemplate.convertAndSend(
        "orders.queue",
        "{\"orderId\":\"O-42\",\"region\":\"VN\",\"amount\":150}",
        message -> {
            message.setStringProperty("region", "VN");
            message.setIntProperty("amount", 150);
            message.setStringProperty("eventType", "order.created");
            return message;
        });
~~~

The snippet above has two independent parts:

- **Body:** JSON String containing fields `orderId`, `region`, `amount`.
- **JMS properties:** `region` as String, `amount` as int, `eventType` as String.

Valid selector:

~~~sql
region = 'VN' AND amount >= 100 AND eventType = 'order.created'
~~~

A selector **cannot** read JSON fields such as:

~~~sql
body.region = 'VN'
JSON_VALUE(body, '$.amount') >= 100
~~~

Those two lines are not standard JMS selector expressions. If the producer only puts `region` in the body without calling `setStringProperty("region", "VN")`, the filter `region = 'VN'` will not match.

**Design principle:** fields needed for broker filtering should be published as properties with stable names and data types. Detailed business data stays in the body. If selectors need to inspect too many JSON fields, consider splitting Queues or changing routing rather than duplicating the entire payload into properties.

### 3.1. Permitted JMS headers in selectors

Jakarta Messaging 3.1 allows direct references in selectors only to the following standard JMS header fields:

- `JMSDeliveryMode`
- `JMSPriority`
- `JMSMessageID`
- `JMSTimestamp`
- `JMSCorrelationID`
- `JMSType`

Examples:

~~~sql
JMSType = 'order.created'
JMSPriority >= 6
JMSCorrelationID = 'corr-42'
~~~

Do not assume every `JMS`-prefixed header is portable in selectors. `JMSRedelivered`, `JMSDestination`, `JMSReplyTo`, `JMSExpiration`, and `JMSDeliveryTime` are not in the standard referenceable header list above; a provider may offer extensions, which must be verified separately.

`JMSX...` is the property namespace defined by Jakarta Messaging; `JMS_...` is provider-specific; application properties should normally use names such as `eventType`, `tenant`, `schemaVersion`, and `amount`.

## 4. Filter expression syntax

A JMS selector is **a conditional expression** based on a subset of SQL-92 syntax, not a full SQL query. Do not include `WHERE`, `FROM`, or `SELECT`.

### 4.1. Comparison operators

~~~sql
eventType = 'order.created'
eventType <> 'order.cancelled'
amount >= 100
attemptCount < 3
JMSPriority > 5
~~~

- Strings are enclosed in single quotes `'...'`.
- Numbers are written as numeric literals, not strings.
- `<>` is the standard SQL/JMS inequality operator; do not assume `!=` is understood by every provider.
- String, numeric, and boolean comparisons follow type rules; there is no automatic coercion like in some scripting languages.

### 4.2. AND, OR, NOT, and parentheses

~~~sql
eventType = 'order.created' AND amount >= 100

region = 'VN' OR region = 'SG'

eventType = 'order.created'
  AND (region = 'VN' OR region = 'SG')

NOT (status = 'cancelled')
~~~

Standard logical precedence is `NOT`, `AND`, `OR`; use parentheses to clarify intent and prevent unexpected evaluation.

### 4.3. IN and BETWEEN

~~~sql
region IN ('VN', 'SG', 'TH')
amount BETWEEN 100 AND 500
eventType NOT IN ('debug', 'test')
~~~

`IN` checks membership in a grammar-valid value set. `BETWEEN` checks an inclusive range. This is still a String selector; no PreparedStatement or Java List is passed into the API.

### 4.4. LIKE and wildcards

~~~sql
eventType LIKE 'order.%'
reference LIKE 'INV_2026%'
reference NOT LIKE 'TEST%'
~~~

In `LIKE`:

- `%` matches any sequence of zero or more characters.
- `_` matches exactly one character.
- `ESCAPE` is used when literal `%` or `_` characters must be matched.

For example, `region LIKE 'V_'` matches `VN` but not `VNM`. This is not a regular expression; the pattern `order.*` does not mean the same thing as `order.%`.

### 4.5. IS NULL and IS NOT NULL

~~~sql
traceId IS NULL
traceId IS NOT NULL
~~~

If a JMS property does not exist, the selector treats its value as `NULL`. Comparisons with NULL have special semantics, covered in section 5.

### 4.6. Booleans, numeric values, and property names

~~~sql
urgent = TRUE
isTest = FALSE
amount >= 100
attemptCount <= 2
~~~

For those selectors to work, the producer must set matching types:

~~~java
message.setBooleanProperty("urgent", true);
message.setBooleanProperty("isTest", false);
message.setIntProperty("amount", 150);
message.setIntProperty("attemptCount", 1);
~~~

Compare that with:

~~~java
message.setStringProperty("amount", "150");
~~~

A String `amount` property does not automatically become an integer when evaluated against `amount >= 100`. Type conversions that may exist on property getter methods **do not apply automatically** to selector expressions.

### 4.7. Literals and case sensitivity

Identifier/property names are case-sensitive: `eventType` differs from `EventType`. Keywords `AND`, `OR`, and `LIKE` are case-insensitive, while **string literal values** are compared character-by-character.

Single quotes inside a String literal are doubled:

~~~sql
customerName = 'O''Hara'
~~~

to represent the name `O'Hara`. `NULL` differs from the string `'NULL'`. Name properties following JMS identifier rules; do not use selector keywords as property names.

## 5. TRUE, FALSE, and UNKNOWN: why do many messages fail to match?

JMS selectors use **three-valued logic**: `TRUE`, `FALSE`, and `UNKNOWN`. Only messages whose expression evaluates to **TRUE** match. If a property is missing or NULL, many comparisons evaluate to UNKNOWN.

For a message lacking the `status` property:

| Expression | Result | Matches? |
| --- | --- | --- |
| `status = 'NEW'` | UNKNOWN | No |
| `status <> 'CANCELLED'` | UNKNOWN | No |
| `NOT (status = 'CANCELLED')` | UNKNOWN | No |
| `status IS NULL` | TRUE | Yes |
| `status IS NOT NULL` | FALSE | No |
| `status IS NULL OR status <> 'CANCELLED'` | TRUE | Yes |

A common mistake:

~~~sql
status <> 'CANCELLED'
~~~

does not mean "every message not equal to CANCELLED, including those missing status." If the intent is to also receive messages missing `status`:

~~~sql
status IS NULL OR status <> 'CANCELLED'
~~~

**Operational consequence:** a Queue with a backlog can still cause `receiveSelected` to return `null` because all remaining messages lack the property, have the wrong type, or fail the filter.

### 5.1. An absent property differs from an empty string value

If the producer does not set `region`, `region IS NULL` matches. If the producer calls `setStringProperty("region", "")`, the property exists and is no longer NULL. If the producer calls `setStringProperty("region", "null")`, that is a four-character String, not JMS null.

Do not substitute `region = ''` or `region = 'null'` for checking missing properties. The data contract should explicitly define how "unspecified" is represented: omitting the property or using a specific valid sentinel value.

## 6. Wait time and null results

`receiveSelected` is **synchronous receiving**, so the calling thread can block until a matching message arrives or the wait time expires.

In Spring Boot:

~~~properties
spring.jms.template.receive-timeout=1500ms
~~~

Or when configuring `JmsTemplate`:

~~~java
// Configuration snippet, performed before sharing the template:
jmsTemplate.setReceiveTimeout(1500L);
~~~

Spring `JmsTemplate` conventions:

| Receive timeout | Behavior |
| --- | --- |
| Positive number (milliseconds) | Waits up to the specified duration |
| `0` | Waits indefinitely |
| Negative number such as `-1` | `receiveNoWait`, checks immediately without blocking |

On timeout:

~~~java
// Illustrative snippet in a service with JmsOperations injected:
Message received = operations.receiveSelected(
        "orders.queue", "eventType = 'order.created'");
if (received == null) {
    // No MATCHING message within the wait time.
    // This does not prove the Queue is empty.
}
~~~

Do not immediately interpret `null` as a broker failure. The broker may be healthy while the Queue holds only non-matching messages. Conversely, connection failures or invalid selector syntax usually throw `JmsException`, rather than returning a normal null.

If called from an HTTP request handler, an overly large timeout wastes threads and resources. For continuously consuming workers, `@JmsListener` is usually better than a polling loop.

## 7. Spring Boot 3.3 + Java 17 + ActiveMQ Artemis project

This lab sends three messages to a dedicated Queue, receives selectively one by one using selectors, and verifies that non-matching messages remain receivable afterward. The application needs no asynchronous listener because we are studying **synchronous receiving**.

### 7.1. Running a local broker

On a machine with Docker:

~~~bash
docker run -d --rm --name artemis-selector-lab -p 127.0.0.1:61616:61616 -p 127.0.0.1:8161:8161 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest
~~~

Wait for the broker to be ready and check:

~~~bash
docker logs artemis-selector-lab
~~~

These are demo credentials and ports bound only to the loopback host; do not use these credentials in production. The sample broker normally supports automatic Queue creation. If your environment disables auto-create, pre-provision the Queue and send/receive permissions.

### 7.2. Gradle project

Directory tree:

~~~text
jms-selector-lab/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/demo/jms/SelectedReceiveApplication.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-selector-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'demo'
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
}
~~~

Use JDK 17+ and a Gradle version compatible with the declared plugins. Spring Boot 3 uses `jakarta.jms`; do not mix in older `javax.jms` clients.

`src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_BROKER_USER:demo}
spring.artemis.password=${JMS_BROKER_PASSWORD:demo}
spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=1500ms
~~~

The `${...}` expressions are written in standard Spring property placeholder syntax. `pub-sub-domain=false` specifies Queue mode. Password fallbacks are for local lab use only; production must use a secret manager or required environment variables.

### 7.3. Runnable Java class

`src/main/java/demo/jms/SelectedReceiveApplication.java`:

~~~java
package demo.jms;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import java.util.UUID;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class SelectedReceiveApplication {

    public static void main(String[] args) {
        SpringApplication.run(SelectedReceiveApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(JmsTemplate jmsTemplate) {
        return args -> {
            String queue = "lesson.selector." + UUID.randomUUID();

            send(jmsTemplate, queue, "order-1", "north", 50);
            send(jmsTemplate, queue, "order-2", "north", 150);
            send(jmsTemplate, queue, "order-3", "south", 300);

            Message highNorth = jmsTemplate.receiveSelected(
                    queue, "tenant = 'north' AND amount >= 100");
            System.out.println("HIGH_NORTH=" + text(highNorth));

            Object south = jmsTemplate.receiveSelectedAndConvert(
                    queue, "tenant = 'south'");
            System.out.println("SOUTH=" + south);

            Message remaining = jmsTemplate.receive(queue);
            System.out.println("REMAINING=" + text(remaining));

            Message missing = jmsTemplate.receiveSelected(
                    queue, "tenant = 'east'");
            System.out.println("NO_MATCH=" + (missing == null));
        };
    }

    private static void send(JmsTemplate template, String queue,
                             String body, String tenant, int amount) {
        template.convertAndSend(queue, body, message -> {
            message.setStringProperty("tenant", tenant);
            message.setIntProperty("amount", amount);
            return message;
        });
    }

    private static String text(Message message) throws JMSException {
        if (message == null) {
            return "(none)";
        }
        if (message instanceof TextMessage text) {
            return text.getText();
        }
        throw new IllegalStateException("Expected a TextMessage");
    }
}
~~~

**Explanation:**

1. Uses `UUID.randomUUID()` to pick a fresh Queue per run, preventing leftover messages from earlier runs from skewing results. In production, do not create random Queues without lifecycle cleanup; this is only for labs with auto-create enabled.
2. `send(...)` sets `tenant` as String and `amount` as int on JMS properties; the `order-N` String body is converted to a TextMessage by the default converter.
3. `receiveSelected(queue, "tenant = 'north' AND amount >= 100")` matches `order-2`, skipping `order-1` and `order-3`.
4. `receiveSelectedAndConvert(queue, "tenant = 'south'")` matches `order-3`; the default converter turns the TextMessage into a String.
5. `receive(queue)` without a selector retrieves the remaining `order-1` message.
6. `receiveSelected(queue, "tenant = 'east'")` has no match and returns `null` after the wait window.
7. `@EnableJms` is not used because the program has no `@JmsListener`; this is synchronous receiving.

### 7.4. Running and output

~~~bash
gradle bootRun
~~~

With the broker running, valid credentials, auto-creatable Queue, and no competing consumers, the lines printed by the program are:

~~~text
HIGH_NORTH=order-2
SOUTH=order-3
REMAINING=order-1
NO_MATCH=true
~~~

Spring Boot and Gradle may interleave other logs. Because the random Queue name is **not printed**, the four lines above remain consistent under demo conditions. The final receive waits roughly 1500ms before returning null; the program is not frozen.

Stop the broker:

~~~bash
docker stop artemis-selector-lab
~~~

## 8. What happens to non-matching messages?

**With a Queue**, the selector determines which messages are eligible for the consumer. If the current consumer only receives `tenant = 'north'`, `tenant='south'` messages can remain in the Queue for another consumer or another receive call. Messages are not deleted merely because a filter does not match. However, a message can expire via TTL, be affected by broker policy, or be consumed by another competing consumer.

**With a Topic**, the subscription model changes retention behavior. A non-durable subscription generally does not retain messages sent while the subscriber is offline. A subscription's selector determines which messages are delivered to that subscription; non-matching messages are not set aside "to be replayed later if you change the selector." Durable/shared subscriptions have their own identity and selector-update rules.

**Warning:** do not deduce "`null` return = empty Queue." A Queue holding thousands of non-matching messages can still cause this receiver to time out.

## 9. Synchronous receiving is not a browse/peek operation

`receiveSelected` performs **receive and consumption** per the ACK/transaction mode. It is not an API to "peek" at the Queue and leave messages untouched.

~~~java
// Snippet: This is consume, not peek:
Message message = jmsTemplate.receiveSelected(
        "orders.queue", "eventType = 'order.created'");
~~~

If you only want to inspect messages without consuming them, consider `JmsTemplate.browse(...)` / Jakarta JMS `QueueBrowser`. Queue contents can change concurrently; a browser is not an exact point-in-time snapshot and should not replace broker monitoring metrics.

When the session is non-transacted, acknowledgement can occur according to the configured acknowledge mode. With transacted sessions, consumption outcome depends on session commit/rollback. Never receive messages just to count them while ignoring ACK semantics.

## 10. @JmsListener(selector = ...) vs. receiveSelected

Both use JMS selectors, yet differ in execution model:

| Criterion | `receiveSelected` | `@JmsListener(selector = "...")` |
| --- | --- | --- |
| Receiving style | Thread actively polls | Listener container delivers actively |
| Blocks calling thread? | Possibly yes | Container manages dedicated threads |
| Timeout | Per `JmsTemplate` | Per container configuration |
| Resource lifecycle | Scoped to each receive operation | Consumer managed long-term by container |
| Selector | Can vary per call | Usually declared on annotation/factory |
| Best suited for | Jobs, CLIs, bounded polling, waiting workflows | Continuous / high-throughput consumers |
| When no message matches | `null` on timeout | Handler is not invoked |
| Error handling | Caller catches Spring `JmsException` | Listener error handler, transaction/retry config |

Separate listener example (do not add to the sample program as it would compete on the Queue):

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class NorthOrderListener {
    @JmsListener(
        destination = "orders.queue",
        selector = "tenant = 'north' AND amount >= 100")
    public void onOrder(String body) {
        System.out.println("HANDLED=" + body);
    }
}
~~~

This is an illustrative snippet requiring listener infrastructure enabled in a real app. Testing it concurrently against `receiveSelected` on the same Queue may produce unexpected results because both consumers are eligible for matching messages.

## 11. Dynamic selectors: escape literals, never treat as security

A selector is a String, not a PreparedStatement with proper parameter binding. Concatenating raw user input directly into the expression can alter its logic:

~~~java
// Do not do this:
String selector = "tenant = '" + rawTenant + "'";
~~~

If you must build a selector from a validated value, escape single quotes by doubling them:

~~~java
// Illustrative helper method:
static String selectorLiteral(String value) {
    if (value == null || value.length() > 64) {
        throw new IllegalArgumentException("Invalid selector value");
    }
    return "'" + value.replace("'", "''") + "'";
}
~~~

Then:

~~~java
String selector = "tenant = " + selectorLiteral(validatedTenant);
~~~

Enforce allowlists for property names, operators, and length limits; prefer static selectors for stable business logic. Never allow external clients to supply arbitrary selectors verbatim to the broker.

**Selectors are not authorization.** A `tenant = 'north'` filter does not protect other tenants' data if the JMS account can consume the broader Queue. Use ACLs, separate destinations, and proper tenant isolation mechanisms.

## 12. Transactions, ACK, and redelivery

The selector answers "which messages are eligible"; transactions/acknowledgement answer "how receipt is confirmed." They are two distinct mechanisms.

Critical message-processing flow:

1. `receiveSelected` selects a message.
2. Application validates schema/body/business metadata.
3. Performs DB updates / side effects.
4. Commits/ACKs per policy.
5. On error, rolls back/redelivers/DLQs per contract.

Do not assume receiving a `Message` means the database has committed; nor assume a message will not be redelivered if the JMS transaction rolls back.

Some Spring Boot options for the template (apply only when you understand the transaction lifecycle):

~~~properties
spring.jms.template.session.transacted=true
spring.jms.template.session.acknowledge-mode=auto
~~~

Do not put database `@Transactional` on a method and assume JMS and DB share an XA transaction. For critical systems, use idempotency/outbox or a properly coordinated transaction manager.

Selectors do not replace duplicate protection. A redelivered message can still match the selector again. Use a business event ID and persist processing state durably if side effects must not repeat.

## 13. Performance and monitoring

Selectors can reduce irrelevant messages delivered to a consumer, yet efficiency depends on the provider, how the broker stores/indexes properties, backlog depth, and consumer count. There is no universal guarantee that a complex selector is faster than splitting Queues.

Common issues:

- Queue contains many tenants while only a few have active consumers: non-matching messages pile up.
- Creating new consumers in a tight polling loop causes session/connection/broker overhead.
- Selectors with many `OR`s, `LIKE`s, and unstable property names are hard to optimize.
- Consumers blocking too long in HTTP handlers exhaust request threads.
- Multiple consumers with overlapping selectors compete for messages, affecting processing order.
- Overly strict selectors cause queue depth to grow even while the app appears healthy.

Monitor queue depth, message age, consumer count, retry/redelivery, poll timeout counts, `receiveSelected` wait duration, and `InvalidSelectorException` errors. For non-matching backlogs, establish proper consumer, routing, TTL, or DLQ policies.

**Do not use selectors to solve every routing requirement:** when each workload must be processed independently, or tenant isolation is a security requirement, splitting Queues and configuring the broker accordingly can be much cleaner.

## 14. Testing: what mocks cannot prove

Unit tests can verify selector strings and null-handling logic. JUnit 5/Mockito example (snippet must sit inside a test class with test dependencies):

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.jms.core.JmsOperations;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@Test
void receivesOnlyHighValueNorthOrders() {
    JmsOperations operations = mock(JmsOperations.class);
    String filter = "tenant = 'north' AND amount >= 100";

    when(operations.receiveSelectedAndConvert(
            "orders.queue", filter)).thenReturn("order-2");

    Object body = operations.receiveSelectedAndConvert(
            "orders.queue", filter);

    assertEquals("order-2", body);
    verify(operations).receiveSelectedAndConvert(
            "orders.queue", filter);
}
~~~

Mockito does not run the broker's JMS parser. The test above only proves the code invokes the expected method/selector String and handles the mock return.

Only **integration tests against a broker** prove the provider evaluates selectors as intended. Your suite should cover:

1. Messages with properly typed int/long/String/boolean properties.
2. Messages missing properties, `IS NULL`, and `NOT` expressions.
3. Case mismatch `EventType` vs `eventType`.
4. String literals containing single quotes requiring escaping.
5. Non-matching selector -> `null` after receive timeout.
6. After selected receive, non-matching messages still remain in the Queue for other consumers.
7. Invalid selector syntax -> exception, not silently turned into `null`.
8. Transaction rollback/redelivery and concurrent consumers if production requires them.

When testing, use isolated Queues, clean up test messages, and avoid competing listeners. In CI, use a broker container/Testcontainers; never test broken selectors against a production broker.

## 15. Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `receiveSelected` returns `null` while Queue has messages | No matching messages or timeout | Inspect actual properties, syntax, and TTL |
| `amount >= 100` does not match body containing 150 | Body is not a JMS property | Set `amount` via `setIntProperty` |
| `amount >= 100` does not match String `"150"` | Wrong property type | Align numeric contract; do not expect auto-coercion |
| `body.status = 'NEW'` fails to work | JMS does not access JSON body | Use a `status` JMS property |
| `status <> 'CANCELLED'` skips messages missing `status` | NULL -> UNKNOWN | Use `status IS NULL OR ...` when appropriate |
| Selector fails immediately | Syntax error / bad quoting | Check grammar and single-quote escaping |
| Thread blocks too long | Default indefinite timeout | Set a finite receive timeout |
| Single String argument misbehaves | `receiveSelected(String)` overload takes selector for default destination | Use the two-parameter overload |
| Another consumer grabbed the message | Competing consumers | Use an isolated Queue or isolated test |
| Non-matching messages accumulate in backlog | No suitable consumer | Fix routing or lifecycle policies |
| Topic subscriber misses older messages | Non-durable subscription / offline | Choose an appropriate subscription model |
| Consumer receives duplicates | Rollback/redelivery | Idempotency, transactions, retry/DLQ |
| Unit tests pass but broker receives wrong messages | Mock does not run JMS selector engine | Add integration tests |

## 16. Deployment checklist

- [ ] Destination and Queue/Topic mode are configured properly.
- [ ] Selector references valid JMS headers/properties, not JSON body fields.
- [ ] Producer sets properties with exact names and types.
- [ ] Null/UNKNOWN behavior and `IS NULL` are verified.
- [ ] Finite receive timeout chosen per SLA; `null` is handled explicitly.
- [ ] `receiveSelected` is not used for browsing/peeking.
- [ ] Appropriate consumers exist for non-matching messages.
- [ ] If selectors are built dynamically: validate and escape String literals.
- [ ] ACL/tenant isolation is designed independently of selectors.
- [ ] Transactions, ACK, and redelivery are handled.
- [ ] Integration tests exist against a real broker of the target deployment type.
- [ ] Metrics cover backlog, message age, timeouts, and consumer count.

## 17. Self-assessment questions

**1.** Why is `receiveSelected` not equivalent to receiving a message first and filtering with Java `if`?

Because the selector is sent to the consumer and the JMS provider only delivers matching messages; non-matching messages are not consumed by that consumer.

**2.** Can you filter on an `orderId` that exists only inside the JSON body?

No. Standard JMS selectors do not read the body; to filter on it, set `orderId` as a JMS property or change routing.

**3.** Does `setStringProperty("amount", "150")` match `amount >= 100`?

Not as the intended numeric comparison. Use `setIntProperty`/`setLongProperty` and properly typed numeric literals.

**4.** What does `receiveSelected` returning `null` prove?

No matching message was received within the operation's wait window; it does not prove the Queue is empty.

**5.** Does `status <> 'CANCELLED'` select a message missing `status`?

No. UNKNOWN does not match; add `status IS NULL` if you want to include messages missing the property.

**6.** Do non-matching messages vanish from the Queue automatically?

Not merely because the selector did not match. They can wait for another consumer subject to broker policy/TTL.

**7.** Does `receiveSelected("orders.queue")` mean "receive from Queue orders.queue"?

No. The single-argument overload specifies a selector for the default destination; use `receiveSelected(queueName, selector)`.

**8.** When should `@JmsListener(selector=...)` be used?

When continuous processing is needed with container-managed consumers, concurrency, and resources, rather than synchronous polling.

**9.** Can selectors replace broker ACLs in a multi-tenant application?

No. They are only a receive filter mechanism, not a security boundary.

**10.** How do you inspect a Queue without consuming messages?

Use `QueueBrowser`/`JmsTemplate.browse` or broker metrics, instead of `receiveSelected`.

## 18. Official documentation

- Jakarta Messaging 3.1 Specification, **Message selection** section: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging API — Message selectors: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message
- Jakarta Messaging API — MessageConsumer: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageconsumer
- Spring Framework 6.1 — `JmsTemplate`, `receiveSelected`, `receiveSelectedAndConvert`: https://docs.spring.io/spring-framework/docs/6.1.1/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework 6.1 — `JmsOperations`: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/jms/core/JmsOperations.html
- Spring Framework — Using Spring JMS: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Boot 3.3 — JMS and Artemis: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html

**Remember:** `receiveSelected` is synchronous receiving with a **selector evaluated over JMS headers/properties**, not a body query. A proper implementation standardizes property names/types, handles NULL and timeouts, understands ACK/transactions, and plans for non-matching messages.
