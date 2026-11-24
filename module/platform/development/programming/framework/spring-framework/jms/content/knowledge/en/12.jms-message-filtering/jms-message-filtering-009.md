# Testing Matching, Non-Matching, and Wrong-Type Messages

> **Topic:** Message filtering in Spring Framework JMS. This lesson focuses on testing **JMS Message Selectors** when messages **match**, **do not match**, **lack a property**, **have the wrong property type**, or **carry a different JMS body type than expected**. Key point: a selector chooses messages based on **JMS headers and message properties**, **without reading the JSON/text body**. An unselected message is not automatically deleted from the queue.

## 1. Goals and outcomes to prove

After this lesson, you can:

1. Write SQL-92 subset selectors such as `eventType = 'order.created' AND score >= 8`.
2. Distinguish "message **does not match** due to value" from "**does not match** due to property type", and from "**does not match** due to missing property".
3. Explain why `setStringProperty("score", "9")` is **not equivalent** to `setIntProperty("score", 9)` when using the numeric selector `score >= 8`.
4. Know that `NULL` produces three-valued logic: TRUE, FALSE, UNKNOWN; only TRUE is selected.
5. Test `receiveSelected` with a uniquely identified dataset, a finite timeout, and verify that **unmatched messages remain** on the test queue.
6. Distinguish **wrong property type in selector** from **wrong JMS body type** (`TextMessage` vs `BytesMessage`): a selector can match metadata even when the consumer cannot decode the body.
7. Build and run a Java 17/Spring Boot 3.3.5/ActiveMQ Artemis program with explicit assertions for each case.
8. Diagnose `InvalidSelectorException` syntax errors, case-sensitive properties, producer/consumer mismatches, and competition among multiple consumers.

**PASS criteria:** Only messages with a numeric `score` meeting the threshold are selected by `score >= 8`; low-score, String-score, and missing-score messages **are not taken** by that selector. Afterward, the unmatched messages must still be receivable with appropriate selectors on an **isolated test queue**. A message with a `BytesMessage` body can still match a selector based on `score` — a body type error must be detected **after** receiving.

## 2. Which fields does a selector actually inspect?

A JMS selector is a SQL-92 subset conditional expression. The JMS provider uses it to decide whether a message should be delivered to a specific consumer.

~~~text
Producer A                       Broker / Queue                Consumer #1
  TextMessage
  properties:
    eventType = "invoice"
    score = 9 (int)  ------------> message pending
                                           |
                                           v
                                  selector:
                                  eventType = 'invoice'
                                  AND score >= 8  -----> DELIVERED (TRUE)

Producer B
  TextMessage
  properties:
    eventType = "invoice"
    score = "9" (String) --------> message pending
                                           |
                                           v
                                  same selector --------> NOT DELIVERED (FALSE)
                                                         message remains in queue
~~~

A selector can use:
- **Standard JMS headers allowed in selectors**: `JMSDeliveryMode`, `JMSPriority`, `JMSMessageID`, `JMSTimestamp`, `JMSCorrelationID`, `JMSType`.
- **Message properties** set by the producer, such as `eventType`, `score`, `schemaVersion`, `tenantId`, `urgent`.
- **Certain suitable JMSX/provider properties**, depending on the specification and provider support.

A selector **cannot** directly read:
- `TextMessage.getText()` or a field inside a JSON body.
- The byte array of a `BytesMessage`.
- A Java DTO attribute existing only in producer memory that was not mapped to a JMS property.
- Arbitrary JMS headers: for example, `JMSExpiration` **is not in the list of standard header references** permitted by JMS selectors, even though it has a getter on `Message`.

To filter by a business field inside JSON, the producer must **copy that field into a JMS property** (if appropriate), or let the consumer parse/validate after receiving. Broker-side body filtering sometimes exists as a vendor-specific feature (e.g., Artemis XPath), which is **not a portable JMS selector**.

## 3. Property type is part of the message contract

Consider these two calls:

~~~java
// Same digit 9, but different data types on the wire.
message.setIntProperty("score", 9);       // java.lang.Integer, JMS int
message.setStringProperty("score", "9");  // java.lang.String, JMS String
~~~

These two statements are **two separate examples**, and should not be called sequentially on the same property if the goal is to demonstrate type differences: the second overwrites the first. In a real experiment, create **two separate messages**.

Selector:

~~~sql
score >= 8
~~~

**Results per Jakarta Messaging 3.1:**
- `score` is **int 9** → valid numeric comparison → TRUE.
- `score` is **int 3** → valid numeric comparison → FALSE.
- `score` is **String "9"** → comparing String with numeric literal is type-mismatched → FALSE; the provider **does not auto-parse** the string into a number for standard JMS selectors.
- No `score` property → value is treated as `NULL` → result UNKNOWN → not selected.

**Easy pitfall:** the conversion rules of the `message.getIntProperty("score")` API when reading properties are not selector rules. JMS supports certain getter conversions from `String` to numbers, yet **JMS selectors do not apply that getter conversion table**. Hence, a consumer reading `getIntProperty("score") == 9` from a String property **does not prove** a numeric selector will match.

### 3.1. Result matrix to test

Assume all messages have `eventType = "order.created"`, and selector:

~~~sql
eventType = 'order.created' AND score >= 8
~~~

| Case | How producer sets `score` | JMS property value | Selector result | Reason |
| --- | --- | --- | --- | --- |
| MATCH | `setIntProperty("score", 9)` | integer `9` | **TRUE → received** | `9 >= 8` is a valid numeric comparison |
| NON_MATCH | `setIntProperty("score", 3)` | integer `3` | **FALSE → not received** | `3 >= 8` is false |
| WRONG_TYPE | `setStringProperty("score", "9")` | string `"9"` | **FALSE → not received** | String does not automatically become a number |
| MISSING | `score` property not set | `NULL` | **UNKNOWN → not received** | Comparison operator with NULL yields UNKNOWN |
| WRONG_EVENT | `setIntProperty("score", 9)`, but `eventType = "other"` | integer `9` | **FALSE → not received** | `eventType` clause does not match |
| WRONG_BODY_TYPE | `BytesMessage` with `score` int `10` | integer `10`, bytes body | **TRUE → can be received** | Selector does not read/check body |

In the runnable run, we use a random `runId` and a dedicated test queue to isolate each execution. Unmatched messages are verified **after attempting to select the matching message** using other selectors. Do not rely on an empty queue or default broker ordering to draw conclusions.

### 3.2. Comparing with a String literal

If a producer intentionally sends `score` as String `"9"`, the corresponding String selector is:

~~~sql
score = '9'
~~~

This selector can pick the String `"9"` message, yet **will not** pick the integer `9` message because the two types differ. This is an additional test proving the provider retains wrong-type messages until a matching consumer arrives.

Do not choose String for data requiring threshold comparisons or numeric math. String comparison uses character ordering and string-supported operators (commonly `=`, `<>`, `LIKE`); **do not use `score >= '8'` to fake numeric comparison**. The producer contract should explicitly specify `int`/`long` for the field and all parties must comply.

## 4. FALSE differs from UNKNOWN: missing or NULL property

JMS selectors use SQL's three-valued logic: `TRUE`, `FALSE`, `UNKNOWN`.

An absent property is replaced with `NULL` in the expression. Comparing with NULL does not directly return FALSE, but usually UNKNOWN. **Only TRUE selects the message**.

| Expression | `score = 9` (int) | `score = 3` (int) | No `score` |
| --- | --- | --- | --- |
| `score >= 8` | TRUE | FALSE | UNKNOWN |
| `NOT (score >= 8)` | FALSE | TRUE | UNKNOWN |
| `score IS NULL` | FALSE | FALSE | TRUE |
| `score IS NOT NULL` | TRUE | TRUE | FALSE |
| `score >= 8 OR score IS NULL` | TRUE | FALSE | TRUE |
| `score >= 8 AND score IS NOT NULL` | TRUE | FALSE | FALSE |

**Important consequence:** `NOT (score >= 8)` **does not select** messages missing `score`. To fetch messages missing the field, use `score IS NULL`. Do not use `score = NULL` or `score <> NULL` to test for NULL; they do not behave like `IS NULL`/`IS NOT NULL`.

Three-valued logic also affects compound expressions:
- `TRUE AND UNKNOWN` → UNKNOWN;
- `FALSE AND UNKNOWN` → FALSE;
- `TRUE OR UNKNOWN` → TRUE;
- `FALSE OR UNKNOWN` → UNKNOWN;
- `NOT UNKNOWN` → UNKNOWN.

Example for a message missing `score`:
- `eventType = 'order.created' AND score >= 8` → UNKNOWN → not received.
- `eventType = 'order.created' AND score IS NULL` → TRUE → received.
- `eventType = 'order.created' OR score >= 8` → TRUE if `eventType` matches, even when `score` is missing.

Therefore, test **missing properties** as well, not just wrong values. An expression using `OR` can accidentally broaden the set of received messages beyond expectations.

## 5. Selector syntax and error-prone cases

### 5.1. Common operators

| Need | Valid selector | Note |
| --- | --- | --- |
| String comparison | `eventType = 'order.created'` | String literal in single quotes |
| Numeric comparison | `score >= 8` | `score` must be an appropriate numeric type |
| Boolean | `urgent = TRUE` | `TRUE` has no quotes |
| Combination | `eventType = 'order.created' AND score >= 8` | Both sides must be TRUE |
| One of multiple types | `eventType IN ('order.created','order.updated')` | Elements must match type |
| By prefix | `eventType LIKE 'order.%'` | `%` is a wildcard in LIKE |
| Missing property | `score IS NULL` | Do not write `score = NULL` |
| Present property | `score IS NOT NULL` | Does not prove right type |
| Based on header | `JMSPriority >= 7` | Priority is a valid JMS header |
| Distinguishing delivery mode | `JMSDeliveryMode = 'PERSISTENT'` | This is a **String in selectors**, not number `2` |
| By correlation | `JMSCorrelationID = 'request-123'` | ID must be set by producer |

**Property names are case-sensitive:** `eventType` and `EventType` are two different identifiers. Selector keywords (`AND`, `OR`, `IN`, `LIKE`) are case-insensitive, while **property names and String literal contents** are case-sensitive.

### 5.2. Syntax errors and data errors are different

- `score >=` → **syntax error**; the provider must reject invalid selectors, typically with `jakarta.jms.InvalidSelectorException` or a Spring-wrapped exception.
- `score >= 8` when producer set String `"9"` → **syntactically valid expression, wrong data type**; not required to throw an exception on consumer creation. The message simply **does not match**.
- `score > 8` when property is missing → **valid syntax**, evaluates to UNKNOWN, does not match.
- `score >= 8` when score is int `3` → **valid syntax**, evaluates to FALSE, does not match.

Do not lump all four scenarios into "selector failed." Receiving no message is not enough to prove invalid selector syntax or server permission blocking.

### 5.3. Property names and escaping

JMS selector identifiers follow rules like Java identifiers. Use simple names such as `eventType`, `tenantId`, `score`, `schemaVersion`. Names containing dots, hyphens, or special characters may require vendor-specific mechanisms to filter; avoid relying on extended syntax when portable JMS is desired.

For String literals, embedded single quotes must be written as two single quotes. For example, value `O'Brien` in a selector:

~~~sql
customerName = 'O''Brien'
~~~

Do **not** concatenate unvalidated user input into a selector. Use validated IDs/enums or exact escaping mechanisms; when building complex dynamic conditions, it is best to map inputs onto an application-defined set of safe values.

## 6. Lifecycle of **unmatched** messages on a queue

With a **standard JMS queue** and a consumer with a selector:

~~~text
Broker queue demo.selector.tests
  |
  |-- Message #1: score=9 (int)
  |       |
  |       +--> Consumer selector score >= 8: receives #1
  |
  |-- Message #2: score=3 (int)
  |       |
  |       +--> Consumer selector score >= 8: NOT received
  |       +--> still pending, another matching consumer can receive
  |
  |-- Message #3: score="9" (String)
  |       |
  |       +--> Consumer selector score >= 8: NOT received
  |       +--> Consumer selector score = '9': can receive
  |
  |-- Message #4: missing score
          |
          +--> Consumer selector score >= 8: NOT received
          +--> Consumer selector score IS NULL: can receive
~~~

**Not matching ≠ deleted.** On a queue, a message not matching one consumer's selector can stay in the queue waiting for another consumer. However, you must not claim it stays there forever: TTL/expiration, broker purges, queue filters, DLQ/expiry addresses, quotas, and other consumers can all affect it.

Distinguish especially:
- **Consumer selector:** the broker already routed the message into the queue; the consumer receives only messages whose selector is TRUE.
- **Artemis queue/address filter:** can filter right when the message is routed, preventing the message from ever entering that queue. That is a different layer.
- **Topic non-durable subscription:** messages not matching a subscriber may not be retained for that subscriber in the same way as a queue; do not extrapolate queue behavior to all topics/subscriptions.

To prove an unmatched message is **still pending**, retry with another selector, or use broker browse/metrics on the test queue. Never say "receive returned null so the message was dropped."

## 7. Architecture of the complete test suite

We will create **five cases** on one test queue and use a dedicated `runId`:

| Case ID | Body | Properties | Selected by `score >= 8`? |
| --- | --- | --- | --- |
| `HIGH` | `TextMessage("case:HIGH")` | `score` int `9` | Yes |
| `LOW` | `TextMessage("case:LOW")` | `score` int `3` | No |
| `WRONG_TYPE` | `TextMessage("case:WRONG_TYPE")` | `score` String `"9"` | No |
| `MISSING` | `TextMessage("case:MISSING")` | No `score` | No |
| `WRONG_BODY_TYPE` | `BytesMessage` containing 2 bytes | `score` int `10` | **Yes**: selector ignores body |

Test sequence:
1. Generate a UUID `runId` and send four `TextMessage` instances: HIGH, LOW, WRONG_TYPE, MISSING.
2. Consumer with `runId = 'uuid' AND score >= 8` receives **HIGH**.
3. Call the same selector again and wait a finite timeout → `null`; proving no **numeric-matching** message remains at that moment.
4. Use `score = '9'` to retrieve WRONG_TYPE and verify the property is indeed `String`.
5. Use `score < 8` to retrieve LOW, and `score IS NULL` to retrieve MISSING; proving previously excluded messages **were not consumed by the earlier consumer**.
6. Send an additional `BytesMessage` with `score=10`; use the numeric selector to receive it; check `instanceof BytesMessage` instead of assuming `TextMessage`.
7. Print `ALL_ASSERTIONS_PASSED` only after all assertions succeed.

**Why send WRONG_BODY_TYPE last?** So the first numeric receive has only one matching message (HIGH), keeping verification results independent of delivery order. When the bytes case is sent afterward, the body-type test is completely isolated.

**Why does every selector include `runId`?** If the queue still holds messages from an earlier run, an overly broad selector could receive stale messages and invalidate the test. A fresh UUID `runId` and `caseId` check make each measurement independent.

## 8. Runnable project: Java 17 + Spring Boot 3.3.5 + Artemis

### 8.1. Prerequisites

- JDK 17+, Gradle installed (or generate Gradle wrapper).
- **ActiveMQ Artemis** broker at `tcp://localhost:61616`; **anycast** queue named `demo.selector.tests` pre-created or auto-create enabled on the test broker.
- Credentials `demo/demo` are merely examples for a configured learning broker; replace them with real credentials of your test environment.
- Account has **send** and **consume** permissions on this queue.
- No other consumers reading from the demo queue, and no overly short queue-level filter/TTL dropping messages.
- Run on an **isolated test** environment; never use a queue carrying live business data.

**Security note:** do not place production credentials in YAML; set `SPRING_ARTEMIS_USER` and `SPRING_ARTEMIS_PASSWORD` via environment/secret manager outside sample environments.

### 8.2. Directory structure

~~~text
jms-selector-cases/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/SelectorCasesApplication.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-selector-cases'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: "tcp://localhost:61616"
    user: "demo"
    password: "demo"
  jms:
    cache:
      enabled: false
~~~

`mode: native` ensures Spring Boot uses an out-of-process broker, rather than silently falling back to an embedded broker when you want to test a real queue. Caching is disabled in this **small demo** to make test observations straightforward; do not treat this as a configuration recommendation for high-throughput applications.

### 8.3. Full Java code

`src/main/java/demo/SelectorCasesApplication.java`:

~~~java
package demo;

import java.util.UUID;

import jakarta.jms.BytesMessage;
import jakarta.jms.JMSException;
import jakarta.jms.Message;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class SelectorCasesApplication {

    private static final String QUEUE = "demo.selector.tests";
    private static final long TIMEOUT_MS = 750L;

    public static void main(String[] args) {
        SpringApplication.run(SelectorCasesApplication.class, args);
    }

    @Bean
    ApplicationRunner checkCases(JmsTemplate template) {
        return args -> {
            // UUID contains only safe characters when inserted into a String literal.
            String runId = UUID.randomUUID().toString();
            String base = "runId = '" + runId + "'";

            // Configure once before tests, do not mutate concurrently.
            template.setReceiveTimeout(TIMEOUT_MS);

            // Same TextMessage body type; score property differs.
            sendText(template, runId, "HIGH", 9, null);
            sendText(template, runId, "LOW", 3, null);
            sendText(template, runId, "WRONG_TYPE", null, "9");
            sendText(template, runId, "MISSING", null, null);

            System.out.println("SENT_TEXT_CASES=4");

            String numeric = base + " AND score >= 8";

            // Positive test: int 9 satisfies numeric condition.
            Message high = expectCase(
                    template.receiveSelected(QUEUE, numeric), "HIGH");
            if (!(high.getObjectProperty("score") instanceof Integer)) {
                throw new IllegalStateException("HIGH score is not int");
            }
            System.out.println("NUMERIC_MATCH=HIGH");

            // Negative test: LOW, WRONG_TYPE, MISSING must not match.
            Message unexpected = template.receiveSelected(QUEUE, numeric);
            if (unexpected != null) {
                throw new IllegalStateException(
                        "Unexpected numeric match: "
                        + unexpected.getStringProperty("caseId"));
            }
            System.out.println("NO_OTHER_NUMERIC_MATCH=true");

            // String "9" matches String literal, does not match numeric >= 8.
            Message wrongType = expectCase(
                    template.receiveSelected(
                            QUEUE, base + " AND score = '9'"),
                    "WRONG_TYPE");
            if (!(wrongType.getObjectProperty("score") instanceof String)) {
                throw new IllegalStateException("Expected String score");
            }
            System.out.println("STRING_TYPED_MATCH=WRONG_TYPE");

            // Score 3 fails threshold 8, yet remains in the queue.
            Message low = expectCase(
                    template.receiveSelected(
                            QUEUE, base + " AND score < 8"),
                    "LOW");
            if (!(low.getObjectProperty("score") instanceof Integer)) {
                throw new IllegalStateException("LOW score is not int");
            }
            System.out.println("LOW_SCORE_RECOVERED=LOW");

            // Missing property must be checked with IS NULL.
            Message missing = expectCase(
                    template.receiveSelected(
                            QUEUE, base + " AND score IS NULL"),
                    "MISSING");
            if (missing.propertyExists("score")) {
                throw new IllegalStateException(
                        "MISSING unexpectedly has score");
            }
            System.out.println("MISSING_SCORE_RECOVERED=MISSING");

            // Fifth case: body is BytesMessage, score is still numeric.
            template.send(QUEUE, session -> {
                BytesMessage bytes = session.createBytesMessage();
                bytes.writeBytes(new byte[] {1, 2});
                bytes.setStringProperty("runId", runId);
                bytes.setStringProperty(
                        "caseId", "WRONG_BODY_TYPE");
                bytes.setIntProperty("score", 10);
                return bytes;
            });

            Message bodyCase = expectCase(
                    template.receiveSelected(QUEUE, numeric),
                    "WRONG_BODY_TYPE");
            if (!(bodyCase instanceof BytesMessage)) {
                throw new IllegalStateException(
                        "Expected BytesMessage body");
            }
            System.out.println("BYTE_BODY_SELECTED=true");

            System.out.println("ALL_ASSERTIONS_PASSED");
        };
    }

    private static void sendText(
            JmsTemplate template,
            String runId,
            String caseId,
            Integer numericScore,
            String textScore) {

        template.convertAndSend(
                QUEUE, "case:" + caseId, message -> {
                    message.setStringProperty("runId", runId);
                    message.setStringProperty("caseId", caseId);

                    if (numericScore != null) {
                        message.setIntProperty(
                                "score", numericScore);
                    }
                    if (textScore != null) {
                        message.setStringProperty(
                                "score", textScore);
                    }
                    return message;
                });
    }

    private static Message expectCase(
            Message message, String expectedCase)
            throws JMSException {

        if (message == null) {
            throw new IllegalStateException(
                    "Timed out waiting for " + expectedCase);
        }
        String actual = message.getStringProperty("caseId");
        if (!expectedCase.equals(actual)) {
            throw new IllegalStateException(
                    "Expected " + expectedCase + ", got " + actual);
        }
        return message;
    }
}
~~~

### 8.4. Explaining decisions in the code

1. `JmsTemplate` is a Spring Boot bean created from the Artemis `ConnectionFactory`; the code uses `convertAndSend(..., MessagePostProcessor)` to set JMS properties **before sending**.
2. `String` bodies are converted to `TextMessage` by the default `SimpleMessageConverter`. Hence HIGH/LOW/WRONG_TYPE/MISSING differ only in **metadata**, not body type.
3. `sendText` takes separate `Integer numericScore` and `String textScore`, never calling both `setIntProperty` and `setStringProperty` on the same message in the same case.
4. Each message carries `runId` and `caseId`. `runId` is added to **every selector**; `caseId` lets assertions verify the exact message.
5. `numeric` is `score >= 8`. Since `score` is `int`, HIGH matches; LOW fails threshold, WRONG_TYPE has a String so types mismatch, and MISSING yields UNKNOWN.
6. The second receive with `numeric` returns `null` after timeout when only LOW/WRONG_TYPE/MISSING remain. **This is not message loss**: subsequent tests deliberately receive those three messages via matching conditions.
7. `score = '9'` selects WRONG_TYPE; `score < 8` selects LOW; `score IS NULL` selects MISSING. These cases prove initially unmatched messages can still be consumed by other consumers.
8. `BytesMessage` with int `score=10` is sent **after** the four cases above are verified. The numeric selector matches despite the different body, because selectors do not read the body.
9. `expectCase` fails on timeout or unexpected `caseId`. The final PASS prints only if every single message matched accurately, not merely any message arriving.
10. `setReceiveTimeout(750L)` bounds the wait per receive call. Slow calls/broker failures can still lengthen total runtime; receive timeout does **not** cover connection setup, DNS/TLS, or broker recovery.
11. The test uses an isolated queue without competing consumers. In real systems, another consumer can receive/ack messages before the test does, making results unreliable.
12. Because no JMS transaction wraps the entire test, the test actively receives and verifies messages. If an assertion throws mid-way, remaining messages may stay in the test queue; using a fresh `runId` prevents confusion. Clean up data via admin tools on the **test queue** per allowed policy.

### 8.5. Running the program

In the project directory:

~~~bash
gradle bootRun
~~~

When the broker is ready, queue/ACLs are valid, and no other consumers compete, the lines printed by the **application** in sequence are:

~~~text
SENT_TEXT_CASES=4
NUMERIC_MATCH=HIGH
NO_OTHER_NUMERIC_MATCH=true
STRING_TYPED_MATCH=WRONG_TYPE
LOW_SCORE_RECOVERED=LOW
MISSING_SCORE_RECOVERED=MISSING
BYTE_BODY_SELECTED=true
ALL_ASSERTIONS_PASSED
~~~

Spring Boot/Artemis may print additional logs. The UUID changes on each run and is not printed, so the output above is stable. **Do not declare pass unless the final line appears**. If the broker is down, permissions are lacking, the queue is unrouted, or another consumer grabs messages, the program may throw an exception with no PASS output.

**Why isn't there a separate `WRONG_EVENT` in code?** The table in section 3 explains that case, while the program prioritizes isolating the two main test axes: **value match/mismatch** and **wrong type**. You can extend the test with `eventType` by adding a String property and an `AND` clause to the selector while keeping the `runId` check.

### 8.6. Extension: adding an event-type matching case

To catch property name mistakes, add a message with:

~~~java
// Snippet: inside producer's MessagePostProcessor.
message.setStringProperty("eventType", "order.created");
message.setIntProperty("score", 9);
~~~

Consumer uses:

~~~sql
eventType = 'order.created' AND score >= 8
~~~

If the producer changes to `setStringProperty("EventType", ...)` while keeping selector `eventType`, the target property does not exist and the expression becomes UNKNOWN. This is how to write a negative test for **case sensitivity**. Never treat a Java DTO having an `eventType` field as proof that a JMS property `eventType` is on the wire.

## 9. Wrong property type ≠ wrong JMS body type

There are two fundamentally different "type mismatch" errors:

| Axis | Example | How does the selector behave? | Where does the error surface? |
| --- | --- | --- | --- |
| Property metadata | `score` String `"9"` with numeric selector `score >= 8` | Does not match | During provider selector evaluation |
| JMS body | `BytesMessage` with `score` int `10` while consumer expects `TextMessage` | **Still matches** if metadata matches | When consumer casts/converts/deserializes |
| DTO schema | `TextMessage` JSON missing a required DTO field | Selector may still match | When JSON converter/validation runs |
| Custom property type | `urgent` String `"true"` with selector `urgent = TRUE` | Does not match due to String vs. Boolean | Broker/provider selector |
| JMS header policy | Selector uses `JMSPriority >= 7`, producer only calls `message.setJMSPriority(7)` | Actual priority may be overwritten by provider on send | QoS handling at producer/provider |

### 9.1. TextMessage vs. BytesMessage example

~~~java
// Snippet: receiver gets raw JMS message from a consumer/filter.
if (received instanceof jakarta.jms.TextMessage text) {
    String body = text.getText();
    // parse JSON or process String
} else if (received instanceof jakarta.jms.BytesMessage bytes) {
    // process bytes per specific contract
} else {
    throw new IllegalArgumentException(
            "Unsupported JMS body type");
}
~~~

This is a snippet requiring the `received` variable returned by the consumer. Do not cast blindly:

~~~java
String body = ((jakarta.jms.TextMessage) received).getText();
~~~

If the actual message is a `BytesMessage`, that cast throws `ClassCastException`, even though the selector matched completely.

With `JmsTemplate.receiveSelectedAndConvert`, `SimpleMessageConverter` can return `String` for `TextMessage` and `byte[]` for `BytesMessage`. Thus casting the result to `String` can also fail on bytes payloads. A custom Jackson/JSON converter can also throw `MessageConversionException` when content type, class/schema, or JSON does not match. That is a **decode-layer error**, not a selector error.

### 9.2. When can a wrong property type be a severe bug?

Suppose producer A sends:

~~~java
message.setIntProperty("retryCount", 3);
~~~

Yet producer B reads data from an HTTP form and sends:

~~~java
message.setStringProperty("retryCount", "3");
~~~

If a listener requires `retryCount < 5`, every message from B can **fail to be received by that consumer** even though operators see "retryCount 3" on a dashboard. The result is growing queue backlog or messages waiting until TTL expires.

To prevent this:
- Publish a schema **for JMS properties**, not only the JSON body.
- Use a shared producer helper class for common properties, tested so `getObjectProperty` returns the right wrapper type.
- Monitor pending message counts by selector/destination and queue age.
- Define how non-conforming data is handled, e.g., a consumer inspecting non-standard messages on a separate queue or a controlled quarantine/browse mechanism. Do **not** leave an unfiltered fallback consumer on a production queue accepting all messages without a safe processing architecture.

## 10. Do not overlook critical edge cases

### 10.1. Boolean vs. String

~~~java
message.setBooleanProperty("urgent", true);
~~~

Correct selector:

~~~sql
urgent = TRUE
~~~

The selector `urgent = 'true'` uses a String literal; it is not equivalent to Boolean TRUE. Tests must cover `true`, `false`, String `"true"`, and a missing property. Do not parse Strings inside selectors to legitimize a producer sending the wrong type.

### 10.2. Numeric promotion

Comparisons among JMS numeric types (such as int and long/double literals) follow numeric promotion rules supported by the specification. However, converting String `"9"` to a number is **not** part of this group. Tests should cover `int`, `long`, negative values, large numbers, and boundaries (e.g., `score = 8` passes `>=8`; `7` fails) if business requires them.

### 10.3. NULL and negation logic

Do not write:

~~~sql
NOT (score >= 8)
~~~

expecting "all non-passing messages, including missing." Messages missing `score` stay UNKNOWN after `NOT`. If business wants both low scores and missing scores, use:

~~~sql
score < 8 OR score IS NULL
~~~

This selector still does **not** automatically handle messages with String `score` `"9"`. To isolate wrong-type data, design a separate validation/observability pipeline instead of guessing types with non-portable expressions.

### 10.4. LIKE is not a numeric operator

`eventType LIKE 'order.%'` is valid when `eventType` is a String. Do not use `score LIKE '9%'` to filter int `score` `9`. That is wrong-type data/wrong-layer condition.

### 10.5. Case sensitivity

Property names and String values are case-sensitive: `eventType = 'Invoice'` differs from `eventType = 'invoice'`. SQL keywords are case-insensitive. Tests should include messages with the same value in different casing when multiple producers/SDKs exist.

### 10.6. Invalid syntax can be caught before any message arrives

The JMS provider **must** validate selector syntax when creating the consumer. `score >=` is invalid even when the queue is empty; the provider can throw `InvalidSelectorException` during consumer creation. This differs from `score >= 8` when `score` is a String: the syntax is completely valid and the provider simply evaluates FALSE upon encountering the message.

Spring `JmsTemplate` usually translates checked JMS exceptions into runtime Spring `JmsException`. When writing syntax-error tests, verify the cause type and broker/provider logs instead of concluding from `receiveSelected(...) == null`.

## 11. Adding tests for `@JmsListener(selector=...)`

In production applications, JMS often receives asynchronously via `@JmsListener`, yet **selector rules are identical**: only messages whose expression evaluates to TRUE are delivered to the listener.

~~~java
// Snippet inside a @Component of a Spring application with JMS listeners enabled.
@JmsListener(
    destination = "orders.events",
    selector = "eventType = 'order.created' AND score >= 8")
public void onHighScore(String body) {
    System.out.println("HIGH_SCORE=" + body);
}
~~~

Requires importing `org.springframework.jms.annotation.JmsListener`, configuring a listener container, and `ConnectionFactory`. This is a snippet—do **not** drop it into the runnable project in section 8 on the same queue, as this listener can compete for messages and break synchronous tests.

A common mistake is unit-testing by calling `onHighScore("...")` directly and claiming the selector works. Calling the Java method directly **bypasses the JMS provider**, so it does not test the selector at all. To test for real:
1. Start the listener container against a test broker.
2. Send messages with defined properties and types.
3. Use a `CountDownLatch` or recorded state to wait for callbacks with a finite timeout.
4. Assert only matching messages were processed; verify unmatched messages remain on the queue or are handled by a dedicated consumer.
5. Never use fixed `Thread.sleep` as the sole synchronization proof in concurrency tests.

### 11.1. Tests to keep separate from pure unit tests

**Producer unit tests** can use mocks to verify `setIntProperty` was called instead of `setStringProperty`. Yet they **do not prove** broker selector syntax/semantics. Only an **integration test** against a real JMS provider (e.g., an isolated Artemis) proves the broker selects messages per contract.

If multiple provider versions exist, run cross-provider tests against the JMS spec, especially for filter-extension differences. Never run a Java unit test mocking SQL and conclude Artemis or another broker handles everything identically.

## 12. Testing Spring JMS with a test case matrix

| ID | Input data | Selector | Expected | Good evidence |
| --- | --- | --- | --- | --- |
| T01 | `score` int 9 | `score >= 8` | Match | `receiveSelected` returns matching `caseId` |
| T02 | `score` int 8 | `score >= 8` | Boundary match | Boundary message is received |
| T03 | `score` int 7 | `score >= 8` | No match | Timeout, then re-received with `score < 8` |
| T04 | `score` String "9" | `score >= 8` | No match | Timeout, then received with `score = '9'` |
| T05 | No `score` | `score >= 8` | No match (UNKNOWN) | Re-received with `score IS NULL` |
| T06 | No `score` | `NOT (score >= 8)` | No match (UNKNOWN) | Not received; `IS NULL` receives it |
| T07 | `eventType` String "order.created" | `eventType = 'order.created'` | Match | Exact ID received |
| T08 | `EventType`, missing `eventType` | `eventType = 'order.created'` | No match | `eventType IS NULL` is true |
| T09 | `urgent` Boolean true | `urgent = TRUE` | Match | Message is received |
| T10 | `urgent` String "true" | `urgent = TRUE` | No match | String selector `urgent = 'true'` matches |
| T11 | `BytesMessage`, score int 10 | `score >= 8` | Match despite bytes body | Raw message is `BytesMessage` |
| T12 | Any message | `score >=` | Syntax error | `InvalidSelectorException`/Spring wrapper |
| T13 | `score` int 9 | `score = '9'` | No match | String literal differs from number |
| T14 | `score` int 9, mismatched eventType | `score >= 8 AND eventType = 'other'` | No match | AND condition fails |
| T15 | `score` int 9, different runId | `runId = 'a' AND score >= 8` | No match | No cross-run data contamination |

You do not have to push all 15 cases into one queue simultaneously. Group by risk, assign unique IDs, send the exact test messages, and **clean up in a controlled manner** after each group. For negative cases, **prove the message is still present** when the test goal is filtering, rather than assuming the message vanished after timeout.

## 13. Diagnosing when messages are not received

### 13.1. Recommended investigation order

1. **Connectivity and permissions:** broker URL, credentials, port/TLS, and `send`/`consume` permissions. An authorization error is not a selector error.
2. **Actual destination:** do producer and consumer use the same queue/address/routing type? Are there queue filters or diverts?
3. **Was the message sent:** did the producer hit an error or leave a transaction uncommitted? Are messages pending on the test queue?
4. **Does the property exist:** print property names and types via `getObjectProperty` in the test environment; avoid printing sensitive payloads.
5. **Is the selector right:** syntax, quotes, case-sensitive property names, String vs. number, NULL logic.
6. **Is the consumer started:** in classic JMS `Connection.start()` must be called for delivery; Spring templates/containers usually manage this.
7. **Are there competing consumers on the queue:** another listener may have consumed and ACKed the message before the test received it.
8. **TTL/expiry/DLQ:** did the message expire or get moved by policy?
9. **Timeout:** is wait time sufficient; is the provider slow or truly unmatched?
10. **Body conversion:** if the raw message is received yet DTO conversion fails, the issue is in the converter/schema, not the selector.

### 13.2. Observing a queue without accidentally consuming messages

When metadata inspection is needed:
- Use appropriate **broker management/queue browse** tools, strictly with authorized permissions.
- If writing a JMS `QueueBrowser` tool, understand that browsing does not guarantee an atomic snapshot under concurrent modifications.
- Never attach an "unfiltered" consumer to a production queue just to "print messages" and accidentally ACK live data.
- Never delete queues, purge, or alter expiry policies just to make a test PASS.

**Safety with sensitive data:** properties may contain tenant IDs, trace IDs, and business identifiers. Log only fields needed for debugging, stripping personal data/passwords/tokens from logs.

## 14. Testing producer–consumer type independence and schema contracts

A system has two producers:
- Java producer uses `message.setIntProperty("schemaVersion", 2)`.
- STOMP producer or another gateway might send the `schemaVersion` property as String `"2"`.

The JMS consumer uses `schemaVersion >= 2`. Results can differ even though dashboards display "2". Therefore, the API contract should specify:

~~~text
Property contract:
  eventType      : String, required
  schemaVersion  : int, required
  tenantId       : String, required
  attempt        : int, optional
  urgent         : boolean, optional

Body contract:
  Content type   : UTF-8 JSON inside TextMessage
  Schema version : matches schemaVersion property
  Event ID       : stable String for deduplication
~~~

Here `schemaVersion` must be an actual JMS primitive `int` type, not merely JSON text. Each producer should have a contract test proving **exact property types**, and consumers should have broker integration tests proving selectors select accurately.

If a system **intentionally** uses only String properties due to transport limitations, design selectors for String/equality or revise the schema/transport. Apache Artemis Core has a `convert_string_expressions:` extension for certain filter expressions; that is **not portable JMS selector syntax**. Do not rely on this extension in application code meant to run across multiple JMS providers without compatibility tests.

### 14.1. How do queue filters and consumer selectors differ?

Artemis supports **queue filters** in broker configuration and **consumer filters/selectors** in clients:
- Queue filters decide **which messages are routed into a queue**.
- Consumer selectors decide **which messages already in the queue are delivered to a consumer**.
- An unmatched queue filter may prevent a message from ever existing in that queue; an unmatched consumer selector normally leaves the message waiting for another consumer, unless another policy intervenes.

If a test concludes "unmatched messages remain on the queue," ensure the test uses a **consumer selector**, not confused with a queue-level filter.

## 15. Designing cleanup and test reliability

A reliable test does not destroy data and does not rely on luck:
- Use a dedicated queue, e.g., `demo.selector.tests`, and a fresh UUID `runId`.
- Use finite timeouts; never let receive block indefinitely.
- Send test cases in a controlled step and begin assertions only after sends return successfully.
- **Do not depend on message ordering** if multiple messages can match simultaneously; ideally design each selector to expect a single unique case.
- For negative tests, after `null`, verify unmatched messages are still available via another selector.
- Never use production messages or queues with other active consumers.
- Avoid automatic purging in `finally` unless exact ownership can be proven; clean up using test/broker tooling scoped to run IDs and dedicated permissions.
- An integration test might fail mid-way leaving other messages pending. Subsequent runs must use a new `runId` and never treat old messages as passes.
- Configure TTL/retention so failed test messages do not linger forever; if TTL is too short, test data can expire before verification, causing false failures.
- This test does not prove persistent delivery across restarts, DB–broker distributed transactions, or exactly-once side effects. Those belong to separate tests.

## 16. Pre-production selector acceptance checklist

- [ ] Property name and JMS type of every field are documented in the **contract**.
- [ ] Producers call the right `setIntProperty`/`setStringProperty`/`setBooleanProperty`.
- [ ] Consumers filter only on **headers/properties**, never assuming JSON bodies are parsed automatically.
- [ ] Tests cover positive, negative-by-value, wrong-type, and missing/NULL cases.
- [ ] Invalid-syntax tests exist to distinguish consumer-creation failures from non-matches.
- [ ] Case-sensitivity and boundary-value tests exist where relevant.
- [ ] Use `IS NULL` when missing fields must be accepted; do not rely on `NOT(expression)`.
- [ ] Integration tests run against a real broker, verifying unmatched messages **remain** on the right queue.
- [ ] No queue filters, stray consumers, or short TTLs interfere with test results.
- [ ] Verify receivers handle raw `TextMessage`/`BytesMessage` properly with converters.
- [ ] Selector expressions with dynamic values are validated/escaped, never accepting untrusted raw strings.
- [ ] Metrics exist for queue depth, message age, conversion errors, and DLQ to detect "no matching consumer" messages.
- [ ] Test on an isolated queue, never purge live data, and maintain a test-data cleanup plan.

### Self-check questions

1. Why does `setStringProperty("score", "9")` fail `score >= 8`, even while `getIntProperty("score")` sometimes still returns 9?
2. Is `score >= 8` FALSE or UNKNOWN when a message lacks the `score` property?
3. Why does `NOT (score >= 8)` not receive messages missing `score`? Write the proper selector to receive them.
4. Is a `BytesMessage` with `score=10` excluded by selector `score >= 8`? When does the consumer detect the wrong body type?
5. Can a JMS selector directly read an `amount` field inside a JSON body?
6. If a consumer selector does not match, can you claim the message was deleted from the queue?
7. Are `eventType` and `EventType` considered the same JMS property name?
8. What kind of error does `score >=` cause, and at which step does that error normally appear?
9. Why is `runId` needed in integration tests run repeatedly against the same queue?
10. What is the difference between an Artemis queue filter and a JMS consumer selector?

**Remember:** Selector testing must cover **value + type + missing property + body type + queue/consumer scope**. A selector matches only when the expression evaluates to **TRUE**. A String `score` does not automatically convert to int; an absent value is NULL/UNKNOWN; messages not chosen by a consumer selector typically **remain on the queue**, not deleted. Promote filterable fields to properly typed JMS properties and always verify with integration tests on a real broker.

## References

1. Jakarta Messaging 3.1 Specification, `3.5 Message properties` and `3.8 Message selection`: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
2. Jakarta Messaging 3.1 API — `Message` (property types, getters/setters, selector): https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message
3. Spring Framework 6.1 — `JmsTemplate` (receiveSelected, receiveAndConvert, receiveTimeout): https://docs.spring.io/spring-framework/docs/6.1.16/javadoc-api/org/springframework/jms/core/JmsTemplate.html
4. Spring Framework — Receiving a Message: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
5. Apache ActiveMQ Artemis — Filter Expressions (consumer vs queue filtering, JMS and Core differences): https://artemis.apache.org/components/artemis/documentation/latest/filter-expressions.html
6. Spring Boot 3.3 — JMS and Artemis: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
7. Spring Integration — Using JMS Message Selectors: https://docs.spring.io/spring-integration/reference/jms.html
