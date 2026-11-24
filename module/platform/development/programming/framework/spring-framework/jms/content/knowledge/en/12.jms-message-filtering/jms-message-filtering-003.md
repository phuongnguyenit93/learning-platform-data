# Comparison Syntax and Logical Operators in the SQL Subset of JMS Message Selectors

> **Topic:** Message filtering in Spring Framework JMS (Jakarta Messaging).  
> **Goal:** Write selectors using comparison operators `=`, `<>`, `<`, `<=`, `>`, `>=`; logical operators `AND`, `OR`, `NOT`; parentheses, three-valued logic, `IS NULL`, `BETWEEN`, `IN`, and `LIKE`. Understand the limits of the SQL92 subset syntax and apply it correctly via `JmsTemplate` or `@JmsListener`.

**Example versions:** Java 17+, Spring Framework 6.x, Spring Boot 3.5.x, Jakarta Messaging 3.1 (`jakarta.jms`), and Apache ActiveMQ Artemis. This article focuses on **JMS message selectors**, not JDBC, Spring Data JPA, or a SQL query running against a database.

## 1. What does a message selector filter?

JMS allows a consumer to receive only messages for which the filter expression over **JMS headers and JMS message properties** evaluates to **TRUE**. For instance:

~~~sql
region = 'APAC' AND score >= 8 AND urgent = TRUE
~~~

A message with `region='APAC'`, `score=9`, and `urgent=true` will match. If `region='EU'` or `score=4`, the message does not match. In particular, if a property is absent, the selector may evaluate to **UNKNOWN**, which also **does not match**.

~~~text
 Producer sends TextMessage + JMS properties
                |
                v
         Queue / Topic broker
                |
        Message selector
        +----------------+
        | TRUE?          |
        +-------+--------+
           YES  |   NO (FALSE/UNKNOWN)
                |
      Matching consumer
~~~

**Do not confuse data layers:**
- **JMS header:** e.g., `JMSPriority`, `JMSType`, `JMSCorrelationID`.
- **JMS property:** e.g., `region`, `score`, `urgent`, set by the producer with `setStringProperty`, `setIntProperty`, `setBooleanProperty`.
- **Message body:** JSON/XML/String/object bytes; **standard selectors do not parse the body**.

For example, a JSON body:

~~~json
{"region":"APAC","score":9,"urgent":true}
~~~

is **not sufficient** for the selector `region = 'APAC'` to work. The producer must also set the corresponding JMS properties, or the application must choose an appropriate routing topology/consumer-side parsing.

### Producer setting properties

~~~java
// Java code snippet inside a MessageCreator callback with jakarta.jms.Session.
TextMessage message = session.createTextMessage(
        "{\"orderId\":\"ORD-7\"}");
message.setStringProperty("region", "APAC");
message.setIntProperty("score", 9);
message.setBooleanProperty("urgent", true);
return message;
~~~

The snippet above illustrates the API and is not a standalone Java file; `session` is provided by Spring/JMS when creating the message.

**Correct meaning:** only matching messages are delivered to **the consumer using that selector**. A non-matching message is not automatically deleted from the queue; it can wait for an eligible consumer or be affected by TTL, retention, and other consumers. With a Topic, subscription/durability policies also determine whether messages are retained.

## 2. Why does the syntax resemble SQL without being full SQL?

Jakarta Messaging defines a selector as a `String` whose syntax is based on a **subset of SQL92 conditional expressions**. There are no database query constructs like `SELECT`, `FROM`, `JOIN`, subqueries, `ORDER BY`, or general JSON/regex functions.

A valid selector:

~~~sql
(orderState = 'READY' AND amountMinor >= 10000)
OR (urgent = TRUE AND region = 'VN')
~~~

A `SELECT * FROM ... WHERE ...` statement is **not** a valid selector. The JMS provider validates selector syntax when the consumer registers; invalid syntax must raise a JMS error (Spring usually wraps it in `JmsException`). However, a **syntactically valid** selector with a wrong property name or mismatched value type may simply fail to match without throwing an exception.

### Components

| Component | Example | Role |
| --- | --- | --- |
| Identifier | `region`, `amountMinor`, `JMSPriority` | References header/property |
| String literal | `'APAC'`, `'READY'` | String to compare |
| Numeric literal | `8`, `-10`, `2.5` | Exact integer or approximate number |
| Boolean literal | `TRUE`, `FALSE` | Logical value |
| Comparison | `=`, `<>`, `>`, `>=`, `<`, `<=` | Produces conditional result |
| Logic | `NOT`, `AND`, `OR` | Combines or negates conditions |
| Grouping | `( ... )` | Specifies precedence |
| Special predicates | `IS NULL`, `BETWEEN`, `IN`, `LIKE` | Extended comparison predicates |

### Case sensitivity

- Keywords `AND`, `OR`, `NOT`, `TRUE`, `FALSE`, `LIKE`, etc. are **case-insensitive**.
- **Property names/identifiers are case-sensitive**: `Region` differs from `region`.
- **String literals are case-sensitive**: `'APAC'` differs from `'apac'`, `'US'` differs from `'US '`.

Agree on property names and types/values in the producer–consumer contract; do not guess from message body field names.

## 3. Literals and naming rules

### 3.1. Strings in single quotes

~~~sql
region = 'APAC'
eventType = 'InvoiceCreated'
customerName = 'O''Reilly'
~~~

JMS uses **single quotes** for Strings. An embedded single quote is escaped with **two single quotes**: `'O''Reilly'` evaluates to `O'Reilly`.

When writing a Java String:

~~~java
String selector = "region = 'APAC' AND urgent = TRUE";
String withQuote = "customerName = 'O''Reilly'";
~~~

Do not use `"APAC"` to write a String literal in standard JMS selectors. Java escaping and SQL-style literal escaping are **two separate layers**.

### 3.2. Numeric literals

~~~sql
quantity >= 10
temperature <= -2.5
totalMinor > 100000
delta <> 0
~~~

Exact integers have no decimal point and fall within `long` range; approximate numbers have a decimal point or scientific notation (`7E3`). Comparisons between numeric types apply Java numeric promotion per the specification. JMS does **not** have a fixed SQL DECIMAL type in selectors; if monetary amounts matter, use a `long` property in minor units, keeping units and overflow limits consistent.

### 3.3. Boolean literals

~~~sql
urgent = TRUE
enabled <> FALSE
NOT (active = FALSE)
~~~

`TRUE` is a Boolean, not the string `'true'`. Producer with proper types:

~~~java
message.setBooleanProperty("urgent", true);
message.setIntProperty("score", 9);
message.setStringProperty("region", "APAC");
~~~

If the producer uses `setStringProperty("urgent","true")`, the comparison `urgent = TRUE` **does not auto-convert** to Boolean. Fix the property type or the selector contract.

### 3.4. NULL

An unset property is treated as `NULL` in a selector. `NULL` is not the same as the String `'NULL'`, the empty string `''`, or Boolean `FALSE`. Ordinary comparisons with NULL produce **UNKNOWN**, not TRUE or FALSE. To check for a missing property, use:

~~~sql
region IS NULL
region IS NOT NULL
~~~

### 3.5. Identifiers and reserved words

Property names must generally follow Java-style identifier rules, e.g., `region`, `orderId`, `tenantId`, `_type`. Avoid names with hyphens/spaces or reserved keywords `NOT`, `AND`, `OR`, `BETWEEN`, `LIKE`, `IN`, `IS`, `ESCAPE`, `NULL`, `TRUE`, `FALSE`.

The `JMSX` prefix is reserved for JMS-defined properties, and `JMS_` for provider-specific properties. Application properties should have a clear namespace/naming convention without abusing reserved prefixes.

## 4. The six comparison operators

| Operator | Meaning | Example |
| --- | --- | --- |
| `=` | Equal | `region = 'VN'` |
| `<>` | Not equal | `state <> 'DONE'` |
| `>` | Greater than | `score > 8` |
| `>=` | Greater than or equal | `score >= 8` |
| `<` | Less than | `attempts < 3` |
| `<=` | Less than or equal | `amountMinor <= 100000` |

**Use `<>` instead of `!=`** when you want a portable selector. A broker may support `!=` as an extension; the JMS specification does not require it.

**Type restrictions:** String and Boolean only support `=` and `<>`, not ordering comparisons with `>` or `<`. String comparisons are based on exact character sequences; do not rely on SQL collation-style lexical ordering.

### Common type mismatch

~~~java
message.setStringProperty("score", "9"); // String, not int
~~~

The selector:

~~~sql
score >= 8
~~~

does not match under standard semantics. Even though some JMS getters can parse a String into a number, **property getter conversions are not applied in selectors**. Comparing incompatible types evaluates to FALSE; if one side is NULL, it evaluates to UNKNOWN.

Examples to test to prevent drift:
- `setIntProperty("score",9)` matches `score >= 8`.
- `setStringProperty("score","9")` does not match `score >= 8`.
- `setStringProperty("region","APAC")` matches `region = 'APAC'`.
- `setBooleanProperty("active",true)` matches `active = TRUE`.
- `setStringProperty("active","true")` does not match `active = TRUE`.

**Note on negation:** When a type mismatch yields FALSE, wrapping with `NOT(...)` can turn FALSE into TRUE. Do not rely on selectors alone for schema validation; consumers must also validate message properties/schemas at the application layer.

## 5. AND, OR, and NOT

### AND — both conditions are true

~~~sql
region = 'APAC' AND score >= 8
~~~

If region matches but score is low, the result is FALSE. Use AND for rules where multiple constraints are all mandatory.

### OR — at least one condition is true

~~~sql
region = 'APAC' OR region = 'EU'
~~~

Either side being true makes the whole expression TRUE. Be careful when mixing OR with AND: without parentheses, it may filter **more broadly** than the contract.

### NOT — negating a condition

~~~sql
NOT (state = 'DONE')
~~~

For state READY, the result is TRUE. For DONE, FALSE. However, for a **missing** `state` property, `state = 'DONE'` is UNKNOWN, and `NOT UNKNOWN` remains UNKNOWN — the message is not selected.

To also select messages missing `state`:

~~~sql
state IS NULL OR state <> 'DONE'
~~~

Do not write `state != 'DONE'` if you need cross-broker compatibility. Do not assume `NOT` turns NULL into TRUE.

## 6. Operator precedence and parentheses

Logical operator precedence (highest to lowest):

1. `NOT`
2. `AND`
3. `OR`

Comparison operators produce conditions combined by logical operators. Parts at the same precedence level are evaluated left-to-right per standard syntax. **The safest practice is to write explicit parentheses** for any condition containing both AND and OR.

Example missing parentheses:

~~~sql
region = 'APAC' AND score >= 8 OR urgent = TRUE
~~~

is interpreted as:

~~~sql
(region = 'APAC' AND score >= 8) OR urgent = TRUE
~~~

Thus a message with `region='EU', urgent=TRUE` still matches. If the requirement is "only APAC and (high score or urgent)", write:

~~~sql
region = 'APAC' AND (score >= 8 OR urgent = TRUE)
~~~

| region | score | urgent | Without parentheses | With parentheses |
| --- | ---: | --- | --- | --- |
| APAC | 9 | FALSE | TRUE | TRUE |
| APAC | 3 | TRUE | TRUE | TRUE |
| EU | 9 | TRUE | **TRUE** | **FALSE** |
| EU | 9 | FALSE | FALSE | FALSE |

This is a **contract bug**, not a syntax error: the provider still accepts it and the consumer may receive messages outside the intended scope.

### NOT over a group

~~~sql
NOT (region = 'APAC' OR region = 'EU')
~~~

differs from:

~~~sql
NOT (region = 'APAC') OR region = 'EU'
~~~

Similarly, `a = 1 AND (b = 2 OR c = 3)` differs from `(a = 1 AND b = 2) OR c = 3`. Test important combinations, especially when a property can be missing.

## 7. Three-valued logic: TRUE, FALSE, and UNKNOWN

JMS uses SQL92-style logic over NULL values. An expression can evaluate to **TRUE (T)**, **FALSE (F)**, or **UNKNOWN (U)**. JMS **selects a message only when the entire selector is TRUE**; both FALSE and UNKNOWN fail to match.

### 7.1. AND truth table

| AND | T | F | U |
| --- | --- | --- | --- |
| T | T | F | U |
| F | F | F | F |
| U | U | F | U |

If `region` is missing and `score=3`:
- `region = 'APAC'` is U.
- `score >= 8` is F.
- `U AND F` becomes **F**.

### 7.2. OR truth table

| OR | T | F | U |
| --- | --- | --- | --- |
| T | T | T | T |
| F | T | F | U |
| U | T | U | U |

If `region` is missing but `urgent=TRUE`:
- `region = 'APAC'` is U.
- `urgent = TRUE` is T.
- `U OR T` becomes **T**, so the message is still selected.

### 7.3. NOT truth table

| A | NOT A |
| --- | --- |
| T | F |
| F | T |
| U | U |

`NOT (region = 'APAC')` does not select messages missing `region` because `NOT U = U`. Use `region IS NULL OR region <> 'APAC'` if the contract wants to include missing cases.

### 7.4. Application matrix

| Data | Selector | Result | Matches? |
| --- | --- | --- | --- |
| state=DONE | `state <> 'DONE'` | F | No |
| state=READY | `state <> 'DONE'` | T | Yes |
| state missing | `state <> 'DONE'` | U | No |
| state missing | `NOT (state = 'DONE')` | U | No |
| state missing | `state IS NULL` | T | Yes |
| state missing | `state IS NOT NULL` | F | No |
| state missing, urgent=true | `state = 'READY' OR urgent = TRUE` | T | Yes |
| state missing, urgent=false | `state = 'READY' OR urgent = TRUE` | U | No |

**Lesson:** Never write a negated condition and assume every message missing that field will be selected. NULL must be handled **intentionally**.

## 8. IS NULL and IS NOT NULL

~~~sql
trackingId IS NULL
trackingId IS NOT NULL
region IS NULL OR region = 'APAC'
~~~

`IS NULL` evaluates to TRUE if the property is missing/NULL; `IS NOT NULL` evaluates to TRUE when present and non-NULL.

If a producer sends `setStringProperty("region", "")`, `region` is an **empty string**, not NULL. To also filter empty strings:

~~~sql
region IS NULL OR region = ''
~~~

Contract versioning example: v1 messages lack `schemaVersion`; v2 messages have it. **Only when the v1 contract specifies that missing version means v1** should the selector be written:

~~~sql
schemaVersion IS NULL OR schemaVersion = 1
~~~

If a missing version is a protocol violation, do not silently interpret it as v1: use a validator and quarantine/DLQ.

## 9. BETWEEN and NOT BETWEEN

`BETWEEN` checks a **closed numeric range inclusive of both endpoints**:

~~~sql
score BETWEEN 5 AND 9
~~~

Equivalent to:

~~~sql
score >= 5 AND score <= 9
~~~

The values 5 and 9 **both** match. `NOT BETWEEN` selects values outside the range:

~~~sql
score NOT BETWEEN 5 AND 9
~~~

which has the same meaning as `score < 5 OR score > 9`. If `score` is missing, the comparison yields UNKNOWN; to include missing values, write:

~~~sql
score IS NULL OR score NOT BETWEEN 5 AND 9
~~~

Do not use BETWEEN to order Strings alphabetically: portable String comparisons only have `=` and `<>`.

Timestamps can be represented as a numeric property `eventTimeMillis` of type `long`, then compared with a range. That is milliseconds since epoch per contract, **not** a SQL database `DATE '2026-10-30'` literal.

## 10. IN and NOT IN: string lists

In standard JMS selectors, `IN` is defined for a String identifier (or NULL) and a **list of String literals**:

~~~sql
region IN ('VN', 'TH', 'SG')
state NOT IN ('DONE', 'CANCELLED')
~~~

`region IN ('VN','TH','SG')` is equivalent to OR-ed equality checks on `region`.

**Not portable:**

~~~text
score IN (1, 2, 3)  // JMS IN does not support numeric lists
region IN ()        // Empty list is invalid
region IN ('VN', 2)  // Do not mix String and numbers
~~~

Replace numeric IN with:

~~~sql
score = 1 OR score = 2 OR score = 3
~~~

If `region` is missing, both `region IN (...)` and `region NOT IN (...)` evaluate to UNKNOWN and do not auto-select. For a contract allowing missing `region`:

~~~sql
region IS NULL OR region NOT IN ('VN', 'TH', 'SG')
~~~

## 11. LIKE, NOT LIKE, and ESCAPE

`LIKE` applies to String properties; patterns use:

- `%` — matches **0 or more** characters.
- `_` — matches **exactly 1** character.

~~~sql
eventType LIKE 'Invoice%'
clientId LIKE 'web_'
correlationId NOT LIKE 'test-%'
~~~

| Value | Condition | Result |
| --- | --- | --- |
| InvoiceCreated | `eventType LIKE 'Invoice%'` | TRUE |
| Invoice | `eventType LIKE 'Invoice%'` | TRUE because % can be empty |
| InvoiceX | `eventType LIKE 'Invoice_'` | TRUE |
| InvoiceXY | `eventType LIKE 'Invoice_'` | FALSE |
| web1 | `clientId LIKE 'web_'` | TRUE |
| web12 | `clientId LIKE 'web_'` | FALSE |

To match a literal `_`, use `ESCAPE`:

~~~sql
clientId LIKE 'A!_%' ESCAPE '!'
~~~

Meaning: literal prefix `A_`, followed by any string. A message with `clientId='A_blue'` matches, while `clientId='Ablue'` does not. Choosing `!` instead of backslash avoids overlap between Java String escaping and selector escaping.

`LIKE` is **not** Java regex: `.*`, `[0-9]`, `^`, and lookahead have no regex meaning here. `LIKE '%suffix'` over a large backlog can be expensive to evaluate, depending on the broker/index. If the property is missing, `LIKE`/`NOT LIKE` becomes UNKNOWN.

## 12. Arithmetic and limits of the SQL subset

Selectors support arithmetic operators:

~~~sql
(quantity * unitPriceMinor) >= 100000
temperature + offset < 40
(score - penalty) >= 7
~~~

Arithmetic precedence: unary `+`/`-`, then `*`/`/`, then binary `+`/`-`. Use parentheses to prevent misinterpretation; numeric promotion follows Java rules. Avoid relying on behavior in cases of overflow, division by zero, decimal precision, or missing property values.

Expressions **not** part of the JMS selector standard:

~~~text
SELECT * FROM messages WHERE region = 'VN'
WHERE region = 'VN'
score != 8
LOWER(region) = 'vn'
CAST(score AS INTEGER) > 8
JSON_VALUE(body, '$.region') = 'VN'
ORDER BY score DESC
score > 8 -- SQL comment
~~~

Some vendors have proprietary extensions for XPath/JSON or string conversion, but **they must not be assumed to be standard features**. When portable behavior is required, use only the defined JMS selector grammar.

## 13. Allowed JMS headers that can be referenced

According to Jakarta Messaging 3.1, the set of headers directly referenceable in selectors includes only:

| Header | Example |
| --- | --- |
| `JMSDeliveryMode` | `JMSDeliveryMode = 'PERSISTENT'` |
| `JMSPriority` | `JMSPriority >= 7` |
| `JMSMessageID` | `JMSMessageID = 'ID:...'` |
| `JMSTimestamp` | `JMSTimestamp >= 1761868800000` |
| `JMSCorrelationID` | `JMSCorrelationID = 'req-123'` |
| `JMSType` | `JMSType = 'OrderPlaced'` |

Warnings:
- In a **selector**, `JMSDeliveryMode` is treated as the String `'PERSISTENT'` or `'NON_PERSISTENT'`; do **not** use `JMSDeliveryMode=2` even though the Java API has integer enums/constants.
- `JMSPriority` is compared numerically.
- `JMSMessageID`, `JMSCorrelationID`, and `JMSType` may be NULL.
- `JMSRedelivered` and `JMSExpiration` **are not among the six standard selector headers**. A broker may have extensions, but they are not portable.
- `JMSXGroupID`/`JMSXDeliveryCount` are properties with special rules, not JMS headers that can be compared arbitrarily; provider-defined receive-time properties have portability restrictions.

Normally, business filtering should use application properties such as `eventType`, `region`, `tenantId` rather than hardcoding provider-generated message IDs.

## 14. Applying with Spring JmsTemplate

Spring `JmsTemplate` provides `receiveSelected` and `receiveSelectedAndConvert`:

~~~java
// Java code snippet in a Spring bean with JmsTemplate template.
template.setReceiveTimeout(2_000L);

Message raw = template.receiveSelected(
        "orders.in",
        "region = 'APAC' AND score >= 8");

Object payload = template.receiveSelectedAndConvert(
        "orders.in",
        "region = 'EU' AND urgent = TRUE");
~~~

The two calls above **are two separate receives**, not two ways of reading the same message. `receiveSelected` returns `jakarta.jms.Message` or `null`; `receiveSelectedAndConvert` invokes the converter to return a Java object (usually String for `TextMessage` with the default `SimpleMessageConverter`).

**Both are blocking receives:** when the queue still has non-matching messages, the consumer can still wait until timeout and then return null. By default, receive configuration may wait indefinitely if no timeout is set. Do not use tight unthrottled polling loops or synchronous HTTP requests without deadlines.

### @JmsListener(selector=...)

~~~java
@Component
public class RegionalListener {

    @JmsListener(
        destination = "orders.in",
        selector = "region = 'APAC' AND score >= 8")
    public void process(String orderId) {
        System.out.println("APAC=" + orderId);
    }
}
~~~

This is a Spring class snippet; it requires `@Component` and `@JmsListener` imports, configured listener infrastructure/connection factory, and no unintended competing consumers. With `@JmsListener`, the selector is attached to the listener container; Spring manages JMS consumer creation, transactions/retries/lifecycle.

### Direct Jakarta Messaging API

~~~java
String selector = "region = 'APAC' AND score >= 8";
MessageConsumer consumer =
        session.createConsumer(destination, selector);
~~~

This is a code snippet; it requires `jakarta.jms.Session`, `Destination`, `MessageConsumer`, and closing resources by their proper owner. The specification requires the provider to verify syntax when the consumer is created; with Spring, checked JMS errors are usually translated into Spring `JmsException`.

### Queue and Topic must be understood differently

With a **Queue**, a message is delivered to one eligible consumer; if multiple consumers compete (including an unfiltered consumer), there is no broadcast giving each group a copy. With a **Topic**, the selector belongs to the subscription; different subscribers can each receive their own copy if topology and subscription timing match. Durable subscriptions and message retention/TTL determine whether messages can be received while a subscriber is offline.

**A selector is not an authorization mechanism:** if tenant isolation is needed, broker ACLs, identity, destination policies, and business-layer tenant checks are still required.

## 15. Runnable lab: Spring Boot 3.5 + Java 17 + Artemis

Goal: send four messages to the queue `selector.demo`, use different expressions to sequentially receive **exactly one message** each time, and observe `IS NULL`, numeric/Boolean property types, and the difference between `receiveSelected`/`receiveSelectedAndConvert`.

### 15.1. Initialize the project

At https://start.spring.io/ select:
- Maven, Java 17, Spring Boot **3.5.x**.
- Group `com.example`, artifact `jms-selector-lab`.
- Package `com.example.jmsselector`.
- Dependency `spring-boot-starter-artemis` (Spring for Apache ActiveMQ Artemis).

Add the embedded broker to `pom.xml` with the Spring Boot parent/BOM:

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

This is an **additional** dependency, not a standalone `pom.xml`. It uses the Artemis version managed by Boot's BOM.

### 15.2. Configuration

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=jms-selector-lab
spring.main.web-application-type=none
spring.artemis.mode=embedded
spring.artemis.embedded.queues=selector.demo
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
~~~

Because the lab **has no `@JmsListener`**, `@EnableJms` is not needed; Boot provides `JmsTemplate` once the starter and embedded broker are properly configured.

### 15.3. Complete Java code

File `src/main/java/com/example/jmsselector/JmsSelectorLabApplication.java`:

~~~java
package com.example.jmsselector;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class JmsSelectorLabApplication {

    private static final String QUEUE = "selector.demo";

    public static void main(String[] args) {
        SpringApplication.run(JmsSelectorLabApplication.class, args);
    }

    @Bean
    ApplicationRunner runDemo(JmsTemplate template) {
        return args -> {
            template.setReceiveTimeout(1_500L);

            send(template, "APAC-HIGH", "APAC", 9, true);
            send(template, "EU-HIGH", "EU", 9, true);
            send(template, "APAC-LOW", "APAC", 4, false);
            send(template, "NO-REGION", null, 9, true);

            System.out.println("HIGH=" + receiveText(
                    template,
                    "region = 'APAC' AND score >= 8 AND urgent = TRUE"));

            System.out.println("MISSING=" + receiveText(
                    template,
                    "region IS NULL"));

            System.out.println("EU=" + receiveText(
                    template,
                    "region = 'EU'"));

            Object low = template.receiveSelectedAndConvert(
                    QUEUE, "region = 'APAC' AND score < 8");
            System.out.println("LOW=" + low);

            System.out.println("EMPTY=" + receiveText(
                    template,
                    "score >= 0"));
        };
    }

    private static void send(
            JmsTemplate template,
            String body,
            String region,
            int score,
            boolean urgent) {

        template.send(QUEUE, session -> {
            TextMessage message = session.createTextMessage(body);
            if (region != null) {
                message.setStringProperty("region", region);
            }
            message.setIntProperty("score", score);
            message.setBooleanProperty("urgent", urgent);
            return message;
        });
    }

    private static String receiveText(
            JmsTemplate template,
            String selector) throws JMSException {

        Message message = template.receiveSelected(QUEUE, selector);
        if (message == null) {
            return "null";
        }
        if (!(message instanceof TextMessage text)) {
            throw new IllegalStateException(
                    "Expected TextMessage");
        }
        return text.getText();
    }
}
~~~

**Why is the output deterministic?**
- `APAC-HIGH` is the only message with `region='APAC', score>=8, urgent=TRUE`.
- `NO-REGION` is the only message missing the `region` property, so it matches `region IS NULL`.
- `EU-HIGH` matches `region='EU'`.
- The remaining `APAC-LOW` matches `region='APAC' AND score<8`.
- The queue is then empty; calling `receiveSelected` one more time waits up to about 1.5 seconds and returns `null`.
- There are no competing listeners and no reliance on FIFO order across messages with different selectors.
- `JmsTemplate`'s default converter returns a String for a TextMessage via `receiveSelectedAndConvert`; the lab registers no custom converter.

### 15.4. Running

Linux/macOS:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Ignoring framework/broker logs, the lines printed by the application in order are:

~~~text
HIGH=APAC-HIGH
MISSING=NO-REGION
EU=EU-HIGH
LOW=APAC-LOW
EMPTY=null
~~~

**What the lab proves:** filtering on properties and `IS NULL` logic, and how to use Spring JmsTemplate. **What it does not prove:** exactly-once business effects, redelivery, broker persistence/HA, selector latency under heavy load, or durable Topic subscriptions. If another broker or competing consumer is present, use a clean test environment and verify broker metrics.

### 15.5. Variations to try yourself

1. Change `setIntProperty("score",score)` to `setStringProperty("score", Integer.toString(score))` and observe that `score >= 8` no longer matches.
2. Select specifically with `NOT (region = 'APAC')` against NO-REGION: result is UNKNOWN. Use `region IS NULL OR region <> 'APAC'` to include missing values.
3. Add a message with region EU, score 2, urgent true. Compare `region='APAC' AND score>=8 OR urgent=TRUE` with `region='APAC' AND (score>=8 OR urgent=TRUE)`; the unparenthesized expression can pick EU.
4. Use `clientId LIKE 'A!_%' ESCAPE '!'` with `A_blue`/`Ablue` messages to test literal wildcards.
5. Try an invalid-syntax selector in a test queue; observe the error when the consumer is created, and do not push it to a shared environment.

Do not run two consecutive selectors on **a single message** and treat the second result as an independent check: the first successful receive already consumed that message.

## 16. Building selectors dynamically: preventing unintended expression changes

A JMS selector is a String. The JMS API has no prepared statements or parameter binding like JDBC. Directly concatenating untrusted input into an expression can cause **selector injection** or widen the filter scope incorrectly:

~~~java
// Anti-example: region may contain single quotes and other operators.
String selector = "region = '" + region + "'";
~~~

The safe approach is to accept only allowlisted values or use an expression-building model in trusted code.

### Standalone Java 17: allowlist builder

File `SelectorBuilder.java`:

~~~java
import java.util.Set;

public final class SelectorBuilder {

    private static final Set<String> REGIONS =
            Set.of("APAC", "EU", "US");

    private SelectorBuilder() {}

    public static String forRegionAndScore(
            String region, int minScore) {

        if (!REGIONS.contains(region)) {
            throw new IllegalArgumentException("Unknown region");
        }
        if (minScore < 0 || minScore > 100) {
            throw new IllegalArgumentException("Invalid score");
        }

        return "region = '" + region
                + "' AND score >= " + minScore;
    }

    public static void main(String[] args) {
        System.out.println(forRegionAndScore("APAC", 8));
    }
}
~~~

Run with JDK 17+:

~~~bash
javac SelectorBuilder.java
java SelectorBuilder
~~~

Exact stdout:

~~~text
region = 'APAC' AND score >= 8
~~~

If the application must accept free-form strings, escape single quotes into two single quotes (`'` → `''`), enforce length/character policies, and test dangerous inputs. **Escaping does not replace authorization**. For multi-tenant systems, broker ACLs and business authorization must remain independent of selectors.

## 17. How to diagnose non-matching selectors

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Queue has messages but `receiveSelected` returns null | No message matches, or timeout | Inspect actual headers/properties, selector, queue depth |
| `score >= 8` does not pick score "9" | Score was sent as a String | Check setter property type, not just text value |
| `region='VN'` does not match | Property named `Region` or value `vn` | Check case sensitivity of identifier and literal |
| `NOT(state='DONE')` misses messages lacking state | NOT UNKNOWN = UNKNOWN | Add `state IS NULL` if contract allows |
| `region IN ('VN','TH')` does not select | Region missing, non-String, or wrong case | Check type/null |
| Used `score IN (1,2)` | `IN` in JMS only supports String literals | Use OR with numeric comparisons |
| `JMSDeliveryMode=2` does not match | JMS selectors treat this header as a String | Use `'PERSISTENT'` or `'NON_PERSISTENT'` |
| Consumer receives messages for the wrong region | OR without parentheses | Group with `region='APAC' AND (...)` |
| Used `JSON_VALUE` or JSON body filtering | Not part of portable selectors | Set the required JMS properties |
| Error immediately when creating consumer | Invalid syntax, missing quote/parenthesis | Read root cause `JMSException`/Spring `JmsException` |
| Another consumer "steals" the message | Multiple consumers on the same queue | Check selectors/concurrency/topology |
| Topic misses older events | Subscription/retention, not syntax | Check durable subscription and registration timing |
| LIKE is slow | Broad pattern, many matches, large backlog | Benchmark broker, simplify condition |
| Selector filters too broadly across tenants | Direct input concatenation or wrong parentheses | Allowlist builder, ACLs, and integration tests |

**Distinguish syntax errors from logic errors:**
- The provider must validate syntax when the selector is supplied; invalid syntax can throw `JMSException`.
- Wrong property type, missing property, or wrong value casing usually evaluates silently to **FALSE/UNKNOWN**.
- `null` from `receiveSelected` may simply mean **no matching message within the wait time**, not that the queue is empty.

## 18. Performance, security, and subscription lifecycle

Selectors execute at the JMS provider/broker layer, but the specification **does not guarantee** specific indexing, execution optimization, or latency. Some brokers index properties; others must evaluate conditions across many messages.

Practical advice:
- Prefer clear equality/range predicates over overly long strings or `LIKE '%keyword%'` when throughput matters.
- Do not duplicate JMS properties unnecessarily; metadata also has transmission/storage costs.
- Do not use an unthrottled `receiveNoWait` loop to compensate for a non-matching selector.
- Monitor queue depth, oldest message age, matched deliveries, TTL/expiry, redelivery/DLQ, and consumer count.
- When multiple business groups need independent copies, design Topic/subscriptions or dedicated routing rather than using one queue with multiple selectors expecting broadcast.
- Changing a durable Topic subscription's selector requires checking lifecycle, resubscribe capability, and broker policies. A new selector does not mean older messages from before the subscription existed will be replayed.
- Selectors are not a security boundary: broker authentication/TLS/ACLs and business tenant validation are still necessary.
- Producer–consumer contracts must specify property names, types, optional/required status, selectors, and versioning; a rolling deploy that abruptly changes a property will cause messages to silently stop matching.

### When not to use a selector?

If message selection depends deeply on the JSON body and multiple business transformations, consider:
- Promoting a few **minimal routing attributes** to JMS properties owned by the producer.
- Splitting destinations/queues/topics by business group.
- Receiving then validating/routing inside a service, while accepting that the message has already been delivered/ACKed depending on transactions.
- Using broker-specific filter extensions **only when** the organization accepts lock-in and has integration tests.

Avoid writing a selector like a complex SQL query containing all business conditions; it should remain a metadata filter with a clear contract.

## 19. Go-live checklist

- Does the producer set the right JMS properties, not just the JSON body?
- Are property names/literals consistent in casing and types?
- Are apostrophes in String literals properly escaped with `''`?
- Do comparison operators use `<>` instead of `!=` where portability is required?
- Do String/Boolean operations only use `=` and `<>`?
- Do selectors containing both AND/OR have parentheses to avoid overly broad filtering?
- Have TRUE/FALSE/UNKNOWN cases been tested for missing properties?
- Are `IS NULL`/`IS NOT NULL` used when the contract allows missing properties?
- Does `IN` only take a String list, `BETWEEN` use numbers, and `LIKE` use wildcards/ESCAPE correctly?
- Have JMS headers been checked against the allowed list?
- Is `JMSDeliveryMode` compared as a String rather than an int?
- Does `receiveSelected` have a controlled timeout?
- Are queue/topic semantics, competing consumers, subscription durability, and TTL properly understood?
- Does the selector builder have allowlisting/escaping and independent tenant ACLs?
- Are there integration tests against a real broker for selectors and property types?
- Are queue backlog/latency measured when changing selectors in production?
- Is there a runbook for unmatched messages, poison messages, DLQ, and new version rollouts?

## 20. Practice exercises

1. Given region APAC, score=8, urgent=FALSE, evaluate `region='APAC' AND (score>8 OR urgent=TRUE)`.
2. Find a message where `a=1 AND b=2 OR c=3` differs from `a=1 AND (b=2 OR c=3)`.
3. State is missing: why does `NOT(state='DONE')` fail to match while `state IS NULL OR state <> 'DONE'` matches?
4. Write a selector matching `status` READY/RETRY and `attempts < 4`.
5. Try `setStringProperty("score","9")` and explain why `score >= 8` does not select it.
6. Rewrite `score IN (1,2,3)` as `OR`-ed numeric comparisons.
7. Write a selector for property `clientId` starting with literal `A_`, not A + any character.
8. Write a String literal for the name `O'Reilly` and distinguish escaping in a Java String from escaping in a JMS selector.
9. Why is `JMSDeliveryMode='PERSISTENT'` valid while `JMSDeliveryMode=2` is not portable?
10. With a Queue having 2 consumers using 2 selectors, is it guaranteed both receive the same message? When should a Topic be used?
11. Using `SelectorBuilder`, test a region containing a single quote and the `OR` keyword, verifying it is rejected before creating a consumer.
12. For a message missing `region`, evaluate `region='APAC' OR urgent=TRUE` when `urgent` is TRUE and when FALSE; explain the UNKNOWN logic.
13. Describe an integration test that catches a producer change from `Region` to `region` causing lost matches.
14. Explain why `LIKE '%suffix'` on a large queue can be costly, and propose an appropriate property routing design.
15. Write a rollout plan for adding a new required property while older consumers are still running.

## Official sources

- Jakarta Messaging 3.1, **`jakarta.jms.Message` — Message Selectors:** https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message
- Jakarta Messaging 3.1 Specification, **3.8 Message Selection:** https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta EE Tutorial — **Message Selectors:** https://jakartaee.github.io/jakartaee-documentation/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html
- Spring Framework 6.2 — **JmsTemplate.receiveSelected / receiveSelectedAndConvert API:** https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework 6.2 — **@JmsListener selector:** https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/jms/annotation/JmsListener.html
- Spring Framework 6.2 — **Receiving a Message:** https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Boot 3.5 — **JMS and Artemis configuration:** https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
