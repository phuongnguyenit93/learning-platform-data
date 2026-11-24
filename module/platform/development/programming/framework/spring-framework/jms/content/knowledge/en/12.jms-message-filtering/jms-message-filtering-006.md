# Missing Values and Three-Valued Logic in JMS Message Selectors

> **Context:** Spring Framework – JMS · **Topic:** Message filtering.  
> **Goal:** Understand precisely what happens when a JMS message **lacks a property**, why a selector expression can evaluate to **TRUE**, **FALSE**, or **UNKNOWN**, how `AND`/`OR`/`NOT` propagate unknown values, and how to write safe filters for producers/consumers. This article includes truth tables, a standalone runnable Java 21 example, and a Spring Boot + ActiveMQ Artemis application for practical verification.

## 1. Error-prone scenario: "not READY" is not necessarily selected

A consumer wants to receive orders that are **not** in the `READY` state:

```java
@JmsListener(
    destination = "orders.events",
    selector = "NOT (status = 'READY')")
public void handle(String payload) {
    // ...
}
```

If a message has `status='BLOCKED'`, the condition is `NOT FALSE = TRUE`: the consumer receives it.

If a message **has no `status` property**, the condition `status = 'READY'` is **not FALSE**. According to Jakarta Messaging/SQL92, referencing an absent property is treated as `NULL`, comparing with `NULL` yields `UNKNOWN`, and `NOT UNKNOWN` remains `UNKNOWN`. **The message does not match the selector** because JMS accepts only `TRUE`.

Therefore, the expression below is what actually expresses "not READY, **including missing status**":

```sql
status IS NULL OR status <> 'READY'
```

Whereas if business rules require **`status` to exist and differ from READY**:

```sql
status IS NOT NULL AND status <> 'READY'
```

These are two different contracts. Do not add an `IS NULL` branch without first deciding whether messages missing metadata should be processed, ignored, routed to an error queue, or fixed at the producer.

**Takeaway to remember:** `NOT` does not automatically turn `UNKNOWN` into `TRUE`.

## 2. Which data is a message selector evaluated against?

A JMS selector is a conditional expression using a **subset of SQL92 syntax**, evaluated by the JMS provider against **certain JMS header fields and JMS message properties**, not the body.

```text
JMS TextMessage
├── Headers per JMS
│   ├── JMSPriority
│   ├── JMSCorrelationID
│   └── JMSType
├── Properties set by producer
│   ├── status = "READY"        (String, may be absent)
│   ├── retryCount = 3          (int, may be absent)
│   └── urgent = false         (boolean, may be absent)
└── Body
    {"status":"READY","retryCount":3}     <-- selector DOES NOT read this JSON
```

Suppose the producer sends:

```java
// Fragment: a jakarta.jms.Message message is available.
message.setStringProperty("status", "READY");
message.setIntProperty("retryCount", 3);
message.setBooleanProperty("urgent", false);
```

Then the selector can use `status`, `retryCount`, and `urgent`. If the producer **only** places `"status"` inside the JSON body of a `TextMessage` **without** calling `setStringProperty`, then from the selector's perspective, the `status` property **does not exist**.

JMS header fields allowed in standard selectors are `JMSDeliveryMode`, `JMSPriority`, `JMSMessageID`, `JMSTimestamp`, `JMSCorrelationID`, and `JMSType`. Some headers such as `JMSCorrelationID` and `JMSType` can have null values; `JMSMessageID` is managed by the provider. Do not assume every JMS header getter corresponds to a standard selector name.

**Property names are case-sensitive:** `status` and `Status` are two different identifiers. Keywords `AND`, `OR`, `NOT`, `IS NULL` are syntactically case-insensitive.

## 3. Missing property: why is it called NULL?

According to the Jakarta Messaging 3.1 specification, when a selector expression references a **property absent from the message**, the value of that reference is `NULL` during evaluation. This is a **selector rule**, not a requirement that the application must call `setStringProperty("status", null)`.

Distinguish:

| What does the message have? | How the producer created it | Meaning in selector |
| --- | --- | --- |
| No `status` | Did not call any setter for `status` | `status` is treated as `NULL`. |
| `status = "READY"` | `setStringProperty("status","READY")` | String `READY`, present. |
| `status = ""` | `setStringProperty("status","")` | Empty string, **not NULL**. |
| `urgent = false` | `setBooleanProperty("urgent", false)` | Boolean `FALSE`, **not NULL**. |
| `retryCount = 0` | `setIntProperty("retryCount",0)` | Integer `0`, **not NULL**. |
| `retryCount = "0"` | `setStringProperty("retryCount","0")` | String `"0"`, does not automatically become number 0 in selector comparisons. |

Reading a property in code should not be used to guess whether it exists:

```java
// Fragment: jakarta.jms.Message incoming is available.
boolean exists = incoming.propertyExists("status");
Object value = incoming.getObjectProperty("status");

System.out.println("exists=" + exists);
System.out.println("value=" + value);
```

`propertyExists` is an explicit check for a property's presence. For an **absent** property, `getObjectProperty` returns `null` per the API contract; other typed getters have their own conversion/exception rules. **Do not use `getBooleanProperty(...) == false` or any assumed default value to conclude a property was set.**

**Three distinct concepts:**

1. **Java `null`:** a reference in Java code.
2. **Absent JMS property / selector `NULL`:** missing information in the JMS envelope.
3. **`UNKNOWN`:** the logical outcome when an expression cannot be confirmed true or false due to `NULL`.

The predicate `status IS NULL` yields **TRUE/FALSE**; whereas `status = 'READY'` when `status` is absent yields **UNKNOWN**.

## 4. Why must there be TRUE, FALSE, and UNKNOWN?

Ordinary Boolean logic has two values:

```text
TRUE   FALSE
```

Selectors apply three-valued logic:

```text
TRUE       (T): proposition is definitely true
FALSE      (F): proposition is definitely false
UNKNOWN    (U): insufficient data to determine true or false
```

**The most important message delivery rule:**

| Final selector result | Does the consumer match? |
| --- | --- |
| `TRUE` | **Yes**: the message is eligible for this consumer. |
| `FALSE` | **No**. |
| `UNKNOWN` | **No**. |

`FALSE` and `UNKNOWN` have the **same deliver/do-not-deliver outcome**, yet they are **not synonymous** because they can yield different results when combined further with `AND`, `OR`, or `NOT`. For example, `FALSE OR TRUE = TRUE` and `UNKNOWN OR TRUE = TRUE`, whereas `FALSE OR FALSE = FALSE` while `UNKNOWN OR FALSE = UNKNOWN`.

The broker does not necessarily attach an "UNKNOWN" label in the UI for each message; this is an **expression evaluation** model, not a business status on the message. A message that does not match a queue consumer can remain waiting for another consumer or another selector; retention/expiration/redelivery depend on the destination and broker policies.

## 5. Standard truth tables per SQL92/Jakarta Messaging

Using notation `T=TRUE`, `F=FALSE`, `U=UNKNOWN`.

### 5.1. AND operation

| `A AND B` | B=T | B=F | B=U |
| --- | --- | --- | --- |
| **A=T** | T | F | U |
| **A=F** | F | F | F |
| **A=U** | U | F | U |

Meaning:

- `T AND U = U`: one condition is true while the other lacks data → cannot yet conclude both are true.
- `F AND U = F`: one condition is definitely false → the entire expression is false even though one condition lacks data.
- `U AND U = U`: both are undetermined.

### 5.2. OR operation

| `A OR B` | B=T | B=F | B=U |
| --- | --- | --- | --- |
| **A=T** | T | T | T |
| **A=F** | T | F | U |
| **A=U** | T | U | U |

Meaning:

- `T OR U = T`: one branch is definitely true → the entire OR is true.
- `F OR U = U`: the first branch is false, the second lacks data → the overall result remains undetermined.
- `U OR U = U`.

### 5.3. NOT operation

| A | `NOT A` |
| --- | --- |
| T | F |
| F | T |
| U | U |

**NOT cannot fix missing data**. Thus every variant of `status <> 'READY'`, `NOT (status = 'READY')`, and `status NOT IN (...)` requires thinking through the case where `status` does not exist.

## 6. Step-by-step example with the `status` property

Suppose the selector is `status = 'READY'`. There are three messages:

| Message | Property status | `status = 'READY'` | Is it selected? |
| --- | --- | --- | --- |
| M1 | `READY` | T | Yes |
| M2 | `BLOCKED` | F | No |
| M3 | **no property** | U | No |

Adding `NOT`:

| Message | `status = 'READY'` | `NOT (status = 'READY')` | Is it selected? |
| --- | --- | --- | --- |
| M1 | T | F | No |
| M2 | F | T | Yes |
| M3 | U | U | **No** |

To include M3, use:

```sql
status IS NULL OR status <> 'READY'
```

Evaluation:

| Message | `status IS NULL` | `status <> 'READY'` | OR | Is it selected? |
| --- | --- | --- | --- | --- |
| M1 = READY | F | F | F | No |
| M2 = BLOCKED | F | T | T | Yes |
| M3 = missing | T | U | **T** | Yes |

If you only want valid statuses, you can use:

```sql
status IS NOT NULL AND status <> 'READY'
```

This expression **does not validate** that `status` has a value from a valid business enum; it only checks that the property exists and differs from READY when types are comparable. For tighter contract control, specify `status IN ('BLOCKED', 'CANCELLED')` and test schema versions.

### 6.1. A proposition that looks "always true" but fails on missing data

```sql
status = 'READY' OR status <> 'READY'
```

When `status` has a valid String, it is T; however, when `status` is absent:

```text
UNKNOWN OR UNKNOWN = UNKNOWN
```

So it **does not match**. This is why the law of excluded middle from two-valued Boolean logic cannot be applied verbatim when `NULL` exists.

## 7. Example combining AND/OR in order filtering

Selector:

```sql
eventType = 'OrderCreated' AND retryCount > 2
```

Suppose `eventType='OrderCreated'` is set and `retryCount` is missing:

```text
TRUE AND UNKNOWN = UNKNOWN
```

The message is **not** delivered to the consumer. If `eventType='OrderCancelled'` (left condition false) and `retryCount` is missing:

```text
FALSE AND UNKNOWN = FALSE
```

Still not delivered, though with a different logical outcome.

Second selector:

```sql
eventType = 'OrderCreated' OR retryCount > 2
```

With matching `eventType` and missing `retryCount`:

```text
TRUE OR UNKNOWN = TRUE
```

The message is selected. With wrong `eventType` and missing `retryCount`:

```text
FALSE OR UNKNOWN = UNKNOWN
```

Not selected.

**Debugging tip:** break a complex selector down into individual comparisons, assign T/F/U to each part according to the metadata **actually present in JMS properties**, and evaluate via the truth tables. Avoid relying on "English-sounding conditions" because NOT/NULL can mislead intuition.

## 8. `IS NULL` and `IS NOT NULL` have special meaning

These two operators turn the question "is the value known?" into a proposition **that yields T or F** for the checked field.

| Property status | `status IS NULL` | `status IS NOT NULL` |
| --- | --- | --- |
| Missing | TRUE | FALSE |
| `"READY"` | FALSE | TRUE |
| `""` | FALSE | TRUE |
| `"BLOCKED"` | FALSE | TRUE |

Use when needed:

- **Selecting legacy messages missing a field:** `schemaVersion IS NULL`.
- **Selecting only messages with metadata:** `tenantId IS NOT NULL`.
- **Supporting two sources, one not yet sending the new property:** `(region IS NULL OR region = 'APAC')`.

However, `IS NULL` **does not replace validation**: `tenantId IS NOT NULL` is also true when `tenantId` is the empty string `""` or a malformed string. Combine with producer/consumer validation; do not treat selectors as a complete schema validator.

### What not to do

- Writing `status = NULL` or `status <> NULL` to test for missing data. **Use `IS NULL`/`IS NOT NULL`**; `NULL` is not an ordinary comparable literal in the selector syntax subset.
- Writing `status = 'null'` thinking that means null. `'null'` is a four-character **String literal**.
- Treating `NOT (status IS NULL)` and `status IS NOT NULL` as different filters: they are equivalent for checking presence properly, whereas `NOT (status = 'READY')` is **not** the same as `status IS NULL OR status <> 'READY'`.
- Treating an empty string as NULL. If business rules want an empty string to also mean "unset", define that explicitly, e.g., `status IS NULL OR status = ''`.

## 9. LIKE, IN, BETWEEN, and NOT when a property is missing

The SQL92 selector subset supports operators like `LIKE`, `IN`, and `BETWEEN` with corresponding data-type/NULL rules.

| Selector | Message missing referenced property | Result on that sub-expression |
| --- | --- | --- |
| `status IN ('READY','BLOCKED')` | status missing | U |
| `status NOT IN ('READY','BLOCKED')` | status missing | U |
| `status LIKE 'PAY%'` | status missing | U |
| `status NOT LIKE 'PAY%'` | status missing | U |
| `retryCount BETWEEN 1 AND 5` | retryCount missing | U |
| `retryCount NOT BETWEEN 1 AND 5` | retryCount missing | U |
| `retryCount > 0` | retryCount missing | U |

These operations do not automatically treat missing data as "not in the set" or "outside the range". `NOT UNKNOWN = UNKNOWN`.

For example, to match starting with `PAY` **or missing the code**:

```sql
eventCode IS NULL OR eventCode LIKE 'PAY%'
```

To get records with `retryCount` outside 1–5 **or missing**:

```sql
retryCount IS NULL OR retryCount NOT BETWEEN 1 AND 5
```

**Do not broaden filters arbitrarily:** adding `OR property IS NULL` will cause legacy messages or producer bugs to start being processed by the consumer. That is a business change requiring testing and a migration plan.

### Comparison and arithmetic operators

JMS selectors allow `=`, `<>`, `>`, `>=`, `<`, `<=` along with arithmetic within supported limits. When an operand is `NULL`, ordinary comparisons evaluate to U. However, **two values with incompatible types** are a different issue: for example, a property set as String `"3"` compared with `retryCount > 2` **does not convert String to number 3 by default**; the specification states that an incompatible-type expression evaluates to FALSE in such a comparison.

Distinguish **missing property** (NULL → UNKNOWN) from **present property with wrong type** (may yield FALSE or an error depending on operation/provider rules); they often produce the same "no match" symptom, but their root causes and fixes differ.

## 10. Standalone Java 21 example: computing three-valued logic yourself

Before using a broker, you can prove the truth tables in plain Java. File `TriLogicDemo.java`:

```java
public class TriLogicDemo {

    enum Truth { TRUE, FALSE, UNKNOWN }

    static Truth not(Truth x) {
        return switch (x) {
            case TRUE -> Truth.FALSE;
            case FALSE -> Truth.TRUE;
            case UNKNOWN -> Truth.UNKNOWN;
        };
    }

    static Truth and(Truth a, Truth b) {
        if (a == Truth.FALSE || b == Truth.FALSE) {
            return Truth.FALSE;
        }
        if (a == Truth.TRUE && b == Truth.TRUE) {
            return Truth.TRUE;
        }
        return Truth.UNKNOWN;
    }

    static Truth or(Truth a, Truth b) {
        if (a == Truth.TRUE || b == Truth.TRUE) {
            return Truth.TRUE;
        }
        if (a == Truth.FALSE && b == Truth.FALSE) {
            return Truth.FALSE;
        }
        return Truth.UNKNOWN;
    }

    public static void main(String[] args) {
        Truth t = Truth.TRUE;
        Truth f = Truth.FALSE;
        Truth u = Truth.UNKNOWN;

        System.out.println("TRUE AND UNKNOWN = " + and(t, u));
        System.out.println("FALSE AND UNKNOWN = " + and(f, u));
        System.out.println("TRUE OR UNKNOWN = " + or(t, u));
        System.out.println("FALSE OR UNKNOWN = " + or(f, u));
        System.out.println("NOT UNKNOWN = " + not(u));
        System.out.println("UNKNOWN OR TRUE = " + or(u, t));
    }
}
```

Compile and run with Java 21:

```bash
javac TriLogicDemo.java
java TriLogicDemo
```

**Exact stdout** of this program:

```text
TRUE AND UNKNOWN = UNKNOWN
FALSE AND UNKNOWN = FALSE
TRUE OR UNKNOWN = TRUE
FALSE OR UNKNOWN = UNKNOWN
NOT UNKNOWN = UNKNOWN
UNKNOWN OR TRUE = TRUE
```

The program demonstrates operator rules and requires no Jakarta JMS dependency at all. It is **not a SQL92 parser** and does not simulate every data-type/provider case. To verify a real selector, you must run a consumer against a broker and observe which messages are delivered.

## 11. Spring Boot + Artemis example: two selectors, two separate queues

Experiment goals:

1. Prove `status IS NULL` allows receiving messages missing `status`.
2. Prove `status = 'READY' AND retryCount > 2` **does not receive** messages missing `retryCount`, even when `status` matches.
3. Prove both FALSE and UNKNOWN fail to match and **the message remains on the queue** per queue/broker policy.
4. Avoid mixing test messages for two selectors on the same queue, which would cause a competing listener to steal the other listener's workload.

This is a **runnable Spring Boot application** with two `@JmsListener` endpoints on **two independent queues**:

- `demo.selector.status`: selects `status = 'READY' OR status IS NULL`.
- `demo.selector.retry`: selects `status = 'READY' AND retryCount > 2`.

Prerequisites: **Java 21**, **Spring Boot 3.3.5**, a separate Artemis broker running at `tcp://localhost:61616`, and the two test queues provisioned or Artemis configured with appropriate auto-create. The example does not rely on a default embedded broker.

### 11.1. Gradle

File `settings.gradle`:

```groovy
rootProject.name = 'selector-three-valued-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain { languageVersion = JavaLanguageVersion.of(21) }
}

repositories { mavenCentral() }

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
```

File `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: ${JMS_BROKER_URL:tcp://localhost:61616}
    user: ${JMS_USER:artemis}
    password: ${JMS_PASSWORD:artemis}
  jms:
    pub-sub-domain: false
```

The `artemis/artemis` values here are only local examples; replace them with an authorized user/password/account in real environments, never hard-coding production secrets. `pub-sub-domain=false` confirms destinations are queues. The JMS starter dependency **does not replace starting the broker or provisioning queues**.

### 11.2. Full Java code

Create file `src/main/java/com/example/jms/SelectorNullDemoApplication.java`:

```java
package com.example.jms;

import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class SelectorNullDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SelectorNullDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner publishCases(JmsTemplate template) {
        return args -> {
            // Queue A: status missing => IS NULL is TRUE.
            send(template, "demo.selector.status",
                    "S-READY", "READY", null);
            send(template, "demo.selector.status",
                    "S-MISSING", null, null);
            send(template, "demo.selector.status",
                    "S-BLOCKED", "BLOCKED", null);
            send(template, "demo.selector.status",
                    "S-EMPTY", "", null);

            // Queue B: must satisfy status READY and retryCount > 2.
            send(template, "demo.selector.retry",
                    "R-3", "READY", 3);
            send(template, "demo.selector.retry",
                    "R-MISSING", "READY", null);
            send(template, "demo.selector.retry",
                    "R-2", "READY", 2);
            send(template, "demo.selector.retry",
                    "R-BLOCKED", "BLOCKED", null);
        };
    }

    private static void send(
            JmsTemplate template,
            String queue,
            String caseId,
            String status,
            Integer retryCount) {

        template.send(queue, session -> {
            TextMessage message = session.createTextMessage(caseId);
            message.setStringProperty("caseId", caseId);

            // Omitting the property is how a missing value is produced.
            if (status != null) {
                message.setStringProperty("status", status);
            }
            if (retryCount != null) {
                message.setIntProperty("retryCount", retryCount);
            }
            return message;
        });
    }
}

@Component
class SelectorConsumers {

    @JmsListener(
            destination = "demo.selector.status",
            selector = "status = 'READY' OR status IS NULL")
    public void onStatus(TextMessage message) throws JMSException {
        System.out.println(
                "STATUS " + message.getText()
                + " hasStatus="
                + message.propertyExists("status"));
    }

    @JmsListener(
            destination = "demo.selector.retry",
            selector = "status = 'READY' AND retryCount > 2")
    public void onRetry(TextMessage message) throws JMSException {
        System.out.println("RETRY " + message.getText());
    }
}
```

Explanation:

- `@SpringBootApplication` creates the application context; `@EnableJms` enables `@JmsListener` detection.
- `ApplicationRunner` is invoked by Spring Boot after context initialization. It sends eight messages, split across two queues; listener lifecycle is managed by Spring.
- `JmsTemplate.send` uses `MessageCreator` to construct a raw `TextMessage`. No `MessageConverter` is needed and there is no confusing JSON body; the payload contains only the case ID.
- `status == null` on the **Java variable passed to the helper method** results in **not calling `setStringProperty`**. This is the intentional way to produce a message **missing the property**.
- `retryCount` uses `setIntProperty`, so the arithmetic expression `retryCount > 2` has a compatible type.
- The listener receives a raw `TextMessage` and uses `propertyExists("status")` to show that S-MISSING truly lacks the property.
- Each listener processes only messages whose selector expression evaluates to `TRUE`; non-matching messages do not enter that listener's callback.

### 11.3. Expected results under standard logic

Table for queue `demo.selector.status`:

| Message | status | `status = 'READY'` | `status IS NULL` | OR | Listener receives? |
| --- | --- | --- | --- | --- | --- |
| S-READY | READY | T | F | T | **Yes** |
| S-MISSING | missing | U | T | T | **Yes** |
| S-BLOCKED | BLOCKED | F | F | F | No |
| S-EMPTY | `""` | F | F | F | No |

Table for queue `demo.selector.retry`:

| Message | status | retryCount | `status='READY'` | `retryCount > 2` | AND | Listener receives? |
| --- | --- | --- | --- | --- | --- | --- |
| R-3 | READY | 3 (int) | T | T | T | **Yes** |
| R-MISSING | READY | missing | T | U | U | No |
| R-2 | READY | 2 (int) | T | F | F | No |
| R-BLOCKED | BLOCKED | missing | F | U | F | No |

Because listeners run asynchronously, log order is not guaranteed. In a **clean** test environment, the set of business lines to observe is:

```text
STATUS S-READY hasStatus=true
STATUS S-MISSING hasStatus=false
RETRY R-3
```

This is the **expected set of lines**, not a guaranteed stdout order and excluding Spring Boot startup logs. On queue `demo.selector.status`, S-BLOCKED/S-EMPTY remain; on queue `demo.selector.retry`, R-MISSING/R-2/R-BLOCKED remain unless another consumer, TTL, expiry, or policy removes them. Do not interpret the leftover description as a guarantee that messages are retained indefinitely.

### 11.4. How to run

From a project with Gradle wrapper:

```bash
# Linux/macOS:
./gradlew bootRun

# Windows:
gradlew.bat bootRun
```

Run on a dedicated test broker with queues containing no old messages. If reusing the same queues across multiple `bootRun` executions, `ApplicationRunner` will send **eight more** messages each time; non-matching messages can accumulate on the broker, creating backlog.

The broker can auto-create queues when auto-create is enabled. If the environment disables auto-create, provision both queues via Artemis administration before running. Calling Java `Session.createQueue` or `JmsTemplate.send` **does not guarantee** physical queue existence on every JMS broker.

## 12. Why use two queues for the experiment?

If you place two `@JmsListener` endpoints with different selectors on the **same queue**, the two consumers can **compete** for messages matching their selectors. A single message might match both selectors, yet in a point-to-point queue it does not become two copies for both listeners to process. That causes log counts not to reflect the truth tables directly.

The experiment uses two queues to keep the test sets independent:

- Queue A tests `OR` and `IS NULL`.
- Queue B tests `AND` and missing data.
- Each message goes only into its corresponding queue.

If you want to broadcast the same event to multiple consumer groups, design a topic and subscriptions or multiple fan-out queues; do **not** treat two consumers on the same queue as a broadcast model.

### Are unmatched messages lost?

You should not give a blanket "yes" or "no" for all destination types:

- With a **queue**, a message not matching this consumer can keep waiting for another consumer with a matching selector, wait for a selector change/redeploy, or be affected by TTL, expiry, broker quotas, and policies.
- With a **topic**, whether a message is retained depends on whether the subscription is durable or non-durable, active/offline, the selector registered at subscribe time, and broker policies. Do not use queue reasoning to assume a topic always keeps excluded messages.
- **A selector is not a delete, ACK, or DLQ command.** Being filtered out does not mean processed-with-failure or routed to dead-letter.

So when a consumer receives no messages, inspect queue backlog, consumer selectors, expiry/DLQ, and routes before concluding the producer never sent them.

## 13. Wrong-type data: completely different from missing data

JMS selectors **do not apply** conversions like `Message`'s typed getters when evaluating properties.

Producer example:

```java
// Creating a new JMS Message:
message.setStringProperty("retryCount", "3");
```

Yet the consumer uses:

```sql
retryCount > 2
```

`retryCount` **is not missing**; it exists as **String `"3"`**, while `2` is a numeric literal. Under JMS selector type-comparison rules, this incompatible case does not match, rather than auto-parsing `"3"` into number `3`.

Conversely:

```java
message.setIntProperty("retryCount", 3);
```

allows the selector to evaluate the numeric type properly.

**Do not use `IS NOT NULL` as a substitute for type checking:** `retryCount IS NOT NULL` is still TRUE when the value is String `"3"`, even though numeric comparison may fail.

### Boolean false differs from a missing property

Two messages:

```java
message.setBooleanProperty("urgent", false);
```

and a message where `urgent` was never set at all.

| Selector | urgent=false | urgent missing |
| --- | --- | --- |
| `urgent = FALSE` | TRUE | UNKNOWN |
| `urgent = TRUE` | FALSE | UNKNOWN |
| `NOT urgent` | TRUE | UNKNOWN |
| `urgent IS NULL` | FALSE | TRUE |
| `urgent IS NOT NULL` | TRUE | FALSE |

**Business-dependent solution:** if missing `urgent` should mean "not urgent", use `urgent IS NULL OR urgent = FALSE`; if missing is a contract violation, use validation and route the message to a controlled flow. Do not let "missing means false" appear implicitly.

## 14. Syntax, precedence, and parentheses

Several easily confused rules:

- Logical operator precedence: **`NOT` > `AND` > `OR`**.
- Parentheses `(...)` clarify intent and prevent adding an `IS NULL` branch from altering the entire condition.
- Use single quotes for String literals: `'READY'`, not double quotes like Java strings inside a selector.
- `<>` is the SQL92 inequality operator; `!=` is **not a guaranteed portable symbol** in the JMS selector subset.
- Operator keywords are case-insensitive, whereas **property names are case-sensitive**.
- Names starting with `JMSX` or `JMS_` are reserved for standard/provider use; pick your own application property names without squatting on reserved prefixes.
- The provider validates syntax when creating the consumer; invalid expressions can throw `InvalidSelectorException`/`JMSException` depending on the API, rather than silently matching nothing.
- JMS does not support full SQL, so do not add `COALESCE`, `CASE WHEN`, SQL joins, or SQL comments into selectors.

Compare two expressions:

```sql
status = 'READY' AND retryCount > 2 OR status IS NULL
```

and:

```sql
status = 'READY' AND (retryCount > 2 OR status IS NULL)
```

The first expression is `(status='READY' AND retryCount>2) OR status IS NULL` because `AND` takes precedence over `OR`; it will accept messages **missing status**. The second expression requires `status` to be READY first, so a message missing `status` does not match. This can be a major business difference caused solely by parentheses.

**Safe pattern to use instead:** always add parentheses around a compound condition when mixing `AND` with `OR`, e.g., `eventType='OrderCreated' AND (status IS NULL OR status <> 'READY')`.

## 15. Safe selector patterns for heterogeneous data

### 15.1. Strict default: accept only full-contract messages

```sql
eventType = 'OrderCreated'
AND schemaVersion = 1
AND tenantId IS NOT NULL
AND status IN ('READY', 'BLOCKED')
```

This skips messages missing any of these properties; it does **not** certify that `tenantId` has a valid value or that the payload conforms to a JSON schema.

### 15.2. Compatible with old producers missing an optional property

Suppose an older version does not set `region` and you want to default to APAC:

```sql
eventType = 'OrderCreated'
AND (region IS NULL OR region = 'APAC')
```

Appropriate only when business has agreed that **absent region = APAC**, compatibility tests exist, and there is a plan to retire the fallback once migration completes.

### 15.3. Select all messages outside READY, including missing status

```sql
status IS NULL OR status <> 'READY'
```

Use only if messages missing `status` are something the consumer must actively handle. If a missing status indicates corrupted data, separate a validation/DLQ queue instead of letting it into the business flow.

### 15.4. Select only non-READY messages that have a status value

```sql
status IS NOT NULL AND status <> 'READY'
```

Add valid-enum checking during processing. A String `'WRONG'` also differs from READY.

### 15.5. Select messages with urgent=false or missing urgent

```sql
urgent = FALSE OR urgent IS NULL
```

Differs from `NOT urgent` because missing `urgent` evaluates to UNKNOWN in that branch.

### 15.6. Clarifying schemaVersion support boundaries

```sql
eventType = 'OrderCreated'
AND schemaVersion = 1
```

Skips messages missing `schemaVersion`. If legacy producers lack this property, receiving legacy messages requires explicitly designing a branch:

```sql
eventType = 'OrderCreated'
AND (schemaVersion IS NULL OR schemaVersion = 1)
```

However, **verify that the legacy body schema is actually compatible with v1**, rather than just letting the selector accept more messages. The consumer could fail parsing or misprocess if the body violates the contract.

## 16. Observing and testing when messages are not selected

A selector evaluating to U does not throw an exception by default; it typically just causes the message **not to match**. This makes production debugging harder than an explicit parse error.

### Verification checklist

1. **Separate three layers:** did the producer send? did the broker receive? did the consumer selector match? An HTTP/API producer returning success does not prove the consumer received it.
2. **Check the right broker and destination:** queue/topic, namespace, address/routing, consumers, ACLs.
3. **Inspect message properties:** `propertyExists`, case-sensitive names, actual `String/int/boolean` types, and message headers.
4. **Do not look at the JSON body to conclude the selector sees a property.**
5. **Compute T/F/U for each condition:** if missing, mark U; use AND/OR/NOT tables to find the final result.
6. **Check every consumer's selector:** a message in a queue might be picked up by another consumer, including one with an empty selector, so do not infer from a single listener's logs.
7. **Compare configs across environments:** broker provider, version, auto-create policy, producer metadata, selector after redeploy.
8. **Monitor backlog and TTL/expiry:** unmatched messages may stay, expire, or be consumed by another consumer depending on the system.
9. **Measure messages missing metadata:** producers should emit metrics or have contract tests checking required properties to prevent silent backlogs.
10. **Use a separate test queue** when changing selectors; do not inject fake messages, purge backlogs, or test an unfiltered consumer on a production queue.

### Mandatory regression tests

| Test case | Input JMS property | Test selector | Expected |
| --- | --- | --- | --- |
| Direct match | status READY | `status='READY'` | MATCH |
| Direct mismatch | status BLOCKED | `status='READY'` | NO MATCH (F) |
| Direct missing | no status | `status='READY'` | NO MATCH (U) |
| Missing with NOT | no status | `NOT(status='READY')` | NO MATCH (U) |
| Missing with IS NULL | no status | `status IS NULL` | MATCH |
| Empty differs from NULL | status `""` | `status IS NULL` | NO MATCH |
| False differs from NULL | urgent=false | `urgent IS NULL` | NO MATCH |
| Boolean missing | no urgent | `NOT urgent` | NO MATCH (U) |
| AND false with unknown | status BLOCKED, missing retry | `status='READY' AND retryCount>2` | NO MATCH (F) |
| AND true with unknown | status READY, missing retry | Same selector | NO MATCH (U) |
| OR true with unknown | status READY, missing retry | `status='READY' OR retryCount>2` | MATCH |
| String is not numeric | retryCount String `"3"` | `retryCount>2` | NO MATCH due to incompatible type |

To **distinguish F and U**, do not rely only on received message counts: neither state matches. You need the input metadata and must evaluate the expression or use a separate truth-table program like in section 10. If the broker provides selector tracing, use it per provider documentation, without assuming every broker logs three-valued states to the console.

## 17. Common mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using `NOT (status='READY')` to also catch missing status | Missing status → U, not received | `status IS NULL OR status <> 'READY'` if business truly wants missing ones. |
| Treating FALSE and UNKNOWN as the same | Wrong predictions when adding OR/NOT | Use T/F/U truth tables. |
| Treating `""` as NULL | Misfilters messages with empty Strings | Validate and add an explicit empty condition. |
| Treating `false` as an unset property | Accidentally skips Boolean false messages | Use `propertyExists` and proper typed Boolean comparison. |
| Using `status = NULL` | Not standard null checking | `status IS NULL`. |
| Putting status only in the JSON body | Selector sees absent property → U | Set JMS property in `MessagePostProcessor` or `MessageCreator`. |
| Setting retryCount as String `"3"` while comparing `> 2` | Type-mismatched comparison; no match | `setIntProperty("retryCount",3)`. |
| Property name differs in casing | `status` differs from `Status` | Standardize field-name contract. |
| Omitting parentheses when mixing AND/OR | Selector matches more broadly or narrowly than intended | Use parentheses per business rules. |
| Assuming unmatched messages are deleted | Unexpected backlog and messages silently piling up | Monitor queue consumers, expiry, TTL, and DLQ. |
| Using selectors as a schema validator | Present yet nonsensical data still gets received | Perform schema validation on producer/consumer. |
| Using a queue with multiple listeners like topic broadcast | Messages get split among consumers | Use topic/subscriptions or fan-out queues if copies are needed. |
| Testing only complete data | Missing-property regressions go undetected | Add missing/empty/false/zero/wrong-type cases. |

## 18. Self-check questions and exercises

1. When `status` is missing, what does `status='READY'` evaluate to? Why is it not delivered?
2. Why does `NOT(status='READY')` not select a message missing `status`?
3. Write the `AND` and `OR` truth tables for T/F/U; state the meaning of `FALSE AND UNKNOWN` and `TRUE OR UNKNOWN`.
4. Write a selector for "not READY and status must exist".
5. Write a selector for "not READY or missing status". Why does it differ from question 4?
6. Are `status=""` and missing `status` the same? Which operator distinguishes them?
7. One producer sets `urgent=false`, another omits the `urgent` property. Which message does `NOT urgent` select?
8. With `eventType='OrderCreated'` and `retryCount` missing, compute the result of `eventType='OrderCreated' AND retryCount>2` and the `OR` version.
9. Why is `setStringProperty("retryCount","3")` not equivalent to `setIntProperty("retryCount",3)` in a selector?
10. Why can't a selector see `status` inside a `TextMessage` JSON body?
11. Compare the meaning of `status IS NULL` and `status = 'null'`.
12. When two `@JmsListener` endpoints use two selectors on the same queue, why can't the two log outputs be treated as fan-out?
13. Design a test matrix for messages missing `schemaVersion` when upgrading producers from legacy to v1.
14. If queue backlog grows while listeners report no errors, what information would you inspect first?
15. Use `propertyExists` and truth tables to explain why a message was filtered out despite carrying a JSON body with the right field.

**Conclusion:** In JMS selectors, **missing property ⇒ NULL ⇒ ordinary comparisons yield UNKNOWN**; `NOT UNKNOWN` remains UNKNOWN, and only **TRUE** matches. `IS NULL`/`IS NOT NULL` explicitly express desired behavior for missing metadata; `AND`/`OR` must be evaluated via truth tables. Writing selectors correctly is not only SQL92 syntax, but also **the contract of setting properly typed properties and making business decisions for missing data**.

### Official references

- [Jakarta Messaging 3.1 – Message selector and Null values](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#message-selector) — defines the SQL92 subset, missing properties, AND/OR/NOT truth tables, and the TRUE-only condition.
- [Jakarta Messaging – Message API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message) — `propertyExists`, JMS headers/properties, and getters/setters.
- [Spring Framework – Annotated JMS Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html) — `@JmsListener(selector=...)`, listener container factory, and raw JMS arguments.
- [Spring Framework – Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html) — `JmsTemplate` and `MessageCreator`.
- [Apache ActiveMQ Artemis – JMS Support](https://artemis.apache.org/components/artemis/documentation/latest/) — broker/JMS queue routing, consumers, message selection, and backlog management.
