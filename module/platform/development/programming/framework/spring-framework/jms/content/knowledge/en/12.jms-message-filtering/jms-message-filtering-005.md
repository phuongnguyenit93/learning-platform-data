# Distinguishing String Types from Numeric Types in JMS Message Properties and Selectors

## 1. Why might a value of "12" fail to be filtered?

In **Spring Framework JMS**, a producer might send two messages both having a property named `orderCount`, and someone reading the console sees the same value "12". Yet those two messages do not necessarily match the same **JMS message selector**:

```java
// Message A: property has int type.
messageA.setIntProperty("orderCount", 12);

// Message B: property has String type.
messageB.setStringProperty("orderCount", "12");
```

Then a consumer configured with the selector:

```sql
orderCount = 12
```

will match **message A**, and will not match **message B**. Conversely:

```sql
orderCount = '12'
```

will match **message B**, and will not match **message A**.

The single quotes around `'12'` **are not just a presentation detail**: according to Jakarta Messaging selector syntax, that is a **String literal**. The number `12` without quotes is a **numeric literal**. JMS selectors do not silently coerce the String `"12"` to the number 12 before comparing.

This lesson focuses on **one exact issue: how the data type of a JMS property affects message filtering syntax and results**. This is a common cause of the bug "the Queue has messages, yet the consumer with a selector does not receive them."

### Visualizing the processing flow

```text
Producer A                              Producer B
setIntProperty("orderCount", 12)        setStringProperty("orderCount", "12")
           |                                       |
           +-------------------+-------------------+
                               |
                          JMS Queue
                               |
                    Consumer with selector
                        orderCount = 12
                               |
                    only message A matches
                               |
                        Spring handler
```

A selector receives only messages for which the expression evaluates to **TRUE**. Results of **FALSE** or **UNKNOWN** do not cause that message to be delivered to the consumer carrying that selector.

## 2. What is a JMS property? How does it differ from body and header?

A JMS message has three conceptual regions:

1. **Headers**: standard fields defined by JMS such as `JMSMessageID`, `JMSPriority`, `JMSCorrelationID`, `JMSType` (with usage scope in selectors restricted by the specification).
2. **Properties**: additional name–value pairs attached to the message by the application or provider, such as `orderCount`, `region`, `retryCount`.
3. **Body**: the main content of `TextMessage`, `BytesMessage`, `MapMessage`, etc.

**A JMS selector reads certain JMS headers and message properties; it does not directly query JSON/XML or body fields.**

For example, the following message has a text body:

```json
{"orderId":"O-101","amount":120}
```

If the producer only creates a `TextMessage` containing this JSON without setting the `amount` property, the selector:

```sql
amount > 100
```

cannot find a property named `amount`; the expression evaluates to **UNKNOWN**, not TRUE. To filter with a selector, the producer must write a separate property before sending:

```java
TextMessage msg = session.createTextMessage(
        "{\"orderId\":\"O-101\",\"amount\":120}"
);
msg.setIntProperty("amount", 120);
```

This is a **snippet inside a `MessageCreator` or a method with a valid `Session`**, not a standalone runnable Java program.

### Standard property types

Jakarta Messaging supports strictly the following groups of property values:

| Type when writing | Java/Jakarta Messaging API | Example |
| --- | --- | --- |
| Boolean | `setBooleanProperty` | `setBooleanProperty("paid", true)` |
| Byte | `setByteProperty` | `setByteProperty("level", (byte) 2)` |
| Short | `setShortProperty` | `setShortProperty("attempts", (short) 3)` |
| Integer | `setIntProperty` | `setIntProperty("count", 12)` |
| Long | `setLongProperty` | `setLongProperty("amountMinor", 12000L)` |
| Float | `setFloatProperty` | `setFloatProperty("score", 12.5F)` |
| Double | `setDoubleProperty` | `setDoubleProperty("score", 12.5D)` |
| String | `setStringProperty` | `setStringProperty("count", "12")` |

There is no separate standard property type for `BigDecimal`, `LocalDate`, `UUID`, or an arbitrary Java bean. `setObjectProperty` only accepts the wrapper types `Boolean`, `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`, and `String` per the specification. Do not assume `setObjectProperty("price", new BigDecimal("1.25"))` is valid on every JMS provider.

**A property's name and type are determined when the producer writes it**; both details must be agreed upon across producer, consumer, and event schema documentation.

## 3. Whichever setter writes the property determines the type the selector sees

### 3.1. Writing a proper numeric property

```java
jmsTemplate.send("orders.in", session -> {
    TextMessage msg = session.createTextMessage("ORDER-001");
    msg.setIntProperty("orderCount", 12);
    msg.setLongProperty("amountMinor", 105_000L);
    msg.setDoubleProperty("riskScore", 0.75D);
    return msg;
});
```

The snippet above requires a Spring `JmsTemplate jmsTemplate` variable and importing `jakarta.jms.TextMessage`; the Queue/provider must already be ready.

Corresponding selectors:

```sql
orderCount = 12
amountMinor >= 100000
riskScore > 0.5
```

Because the values carry numeric types, they can use numeric comparisons and other numeric expressions permitted by the specification. The clause `amountMinor >= 100000` applies to the `long` value according to selector numeric promotion rules.

### 3.2. Writing a String property even when content looks numeric

```java
jmsTemplate.send("orders.in", session -> {
    TextMessage msg = session.createTextMessage("ORDER-002");
    msg.setStringProperty("orderCount", "12");
    msg.setStringProperty("postalCode", "00123");
    return msg;
});
```

Matching selectors are:

```sql
orderCount = '12'
postalCode = '00123'
```

`postalCode` is an **identifier**, not a quantity for addition/subtraction: keeping `String` is the right choice because `"00123"` must preserve leading zeros. `orderCount` represents a quantity, so if the producer wants the consumer to compare numbers, it is better to write `int` from the start.

**Do not use `String` just because the original value came from HTTP JSON, CSV, a config file, or a form.** The application must parse/validate at the producer layer and set the **right property type** when sending to JMS.

### 3.3. `setObjectProperty` does not mean "everything becomes String"

```java
msg.setObjectProperty("countA", Integer.valueOf(12));
msg.setObjectProperty("countB", "12");
```

- `countA` has type `Integer` and matches `countA = 12`.
- `countB` has type `String` and matches `countB = '12'`.

When using `setObjectProperty`, the object's wrapper type matters greatly. For example, `Integer.valueOf(12)` is not the same as `"12"`.

## 4. Literals in JMS selector syntax: quoted or unquoted?

JMS message selectors use **a subset of SQL-92 conditional expression syntax**. They are **not** full SQL queries and do not get automatic database type-casting rules.

| Selector literal | Semantic type | Valid example |
| --- | --- | --- |
| `12` | Exact numeric integer | `orderCount = 12` |
| `-5` | Negative number | `balanceDelta < 0` |
| `12.5` | Approximate numeric | `riskScore >= 12.5` |
| `'12'` | String, **not a number** | `orderCount = '12'` |
| `'PAID'` | String | `paymentState = 'PAID'` |
| `TRUE` / `FALSE` | Boolean | `isPaid = TRUE` |
| `'true'` | String | `isPaid = 'true'` |
| `NULL` | Undefined value in null checks | `orderCount IS NULL` |

**Double quotes** `"12"` in Java typically delimit a **Java String containing the selector**, not a String literal in the selector language. For example:

```java
String numericSelector = "orderCount = 12";
String textSelector = "orderCount = '12'";
```

The first expression has a numeric literal; the second has a string literal. Single quotes sit **inside** the Java string, so they need no escaping in Java source.

Use **single quotes** to enclose strings in a selector. If the string value contains a single quote character, double it inside the literal:

```java
String selector = "customerName = 'O''Brien'";
```

This example matches a `customerName` property with value `O'Brien`.

### Outcome prediction table

Assume that at selector evaluation time, the message actually has the exact property type in the second column:

| Property written | Actual type | Selector | Result |
| --- | --- | --- | --- |
| `setIntProperty("n", 12)` | int | `n = 12` | TRUE |
| `setIntProperty("n", 12)` | int | `n = '12'` | FALSE |
| `setStringProperty("n", "12")` | String | `n = '12'` | TRUE |
| `setStringProperty("n", "12")` | String | `n = 12` | FALSE |
| `setStringProperty("n", "12")` | String | `n > 10` | FALSE |
| `setLongProperty("n", 12L)` | long | `n > 10` | TRUE |
| `setDoubleProperty("n", 12.5)` | double | `n >= 12` | TRUE |
| `setBooleanProperty("paid", true)` | boolean | `paid = TRUE` | TRUE |
| `setStringProperty("paid", "true")` | String | `paid = TRUE` | FALSE |
| `setStringProperty("paid", "true")` | String | `paid = 'true'` | TRUE |
| Property `n` not set | Absent | `n = 12` | UNKNOWN |
| Property `n` not set | Absent | `n IS NULL` | TRUE |

*TRUE* means the message is selected; *FALSE* and *UNKNOWN* are not delivered to the consumer carrying that selector.

## 5. Important rule: getters may cast types, selectors do not

This is a very common source of confusion:

```java
msg.setStringProperty("orderCount", "12");

String raw = msg.getStringProperty("orderCount"); // "12"
int parsed = msg.getIntProperty("orderCount");    // 12
```

According to Jakarta Messaging's **property read conversion table**, reading a `String` property as a number via `getIntProperty` may be supported if the string represents a valid integer.

However, the selector:

```sql
orderCount > 10
```

**does not apply** the conversion table used for getters. `orderCount` remains a **String** because it was set with `setStringProperty`. The numeric comparison is a type mismatch, resulting in **FALSE**.

```text
Producer writes setStringProperty("orderCount", "12")
                     |
                     +--> getIntProperty("orderCount")
                     |    READ conversion table -> int 12
                     |
                     +--> selector "orderCount > 10"
                          DOES NOT apply conversion table -> FALSE
```

The Jakarta Messaging specification explicitly states that **the type of a property in a selector matches the type used when setting the property**, and conversions for property getters **are not applied when running selectors**.

### Other getter cases

- `getStringProperty("count")` can convert integer 12 into string `"12"`. This does **not** turn the original property into a String inside selectors.
- `getIntProperty("count")` on String `"12"` can return 12.
- `getIntProperty("count")` on String `"12x"` must throw `NumberFormatException` if parsing is invalid.
- Conversions outside the supported table can throw `MessageFormatException`.
- `getObjectProperty("count")` helps inspect the **actual type**: an int property returns an `Integer` wrapper, while a String property returns a `String`.

**Do not use the success of `getIntProperty` as evidence that a numeric selector must match.** The two behaviors follow different rules.

## 6. Numeric comparisons: int, long, float, and double

When both sides have **numeric** meaning, JMS selectors allow comparisons:

```sql
orderCount > 10
orderCount >= 10
orderCount < 100
orderCount <> 0
orderCount BETWEEN 10 AND 20
amountMinor + feeMinor >= 100000
```

### 6.1. Can Integer and Long match each other?

Unlike **String vs. number**, comparisons across numeric families can be valid. The specification allows comparing **exact numeric** with **approximate numeric** and applies **Java numeric promotion** rules when needed.

For example:

```java
msg.setIntProperty("n", 12);
```

can be compared with literal `12`, and if using `setLongProperty("n", 12L)`, the selector `n > 10` is still a proper numeric comparison. There is no need to convert `long` to String.

### 6.2. Floating-point comparisons require attention to precision

```java
msg.setDoubleProperty("ratio", 0.1D);
```

The selector `ratio > 0.05` has numeric meaning. However, `double`/`float` have binary representation errors, so do not build financial logic requiring **exact decimal comparison** using floating-point values without evaluating error margins.

For money, a usually clearer strategy is using minor units:

```java
msg.setLongProperty("amountMinor", 12_345L);
```

and filtering:

```sql
amountMinor >= 10000
```

This example represents `12_345` minor units, not a Java `BigDecimal` embedded directly into a property.

### 6.3. Do not use ordering comparisons for Strings

JMS selectors only support `=` and `<>` comparisons for **String** and **Boolean**. Do not write:

```sql
postalCode > '10000'
```

expecting it to compare strings in lexicographical order, or assuming it converts `postalCode` into a number. For Strings, use `=`, `<>`, `LIKE`, and `IN` per proper syntax.

## 7. `BETWEEN`, `IN`, `LIKE`: choosing the right operator for the right type

### 7.1. `BETWEEN` is for numeric expressions

If the producer writes:

```java
msg.setIntProperty("orderCount", 15);
```

the selector:

```sql
orderCount BETWEEN 10 AND 20
```

evaluates to TRUE. However, if the producer writes `setStringProperty("orderCount", "15")`, the selector above does **not** convert `"15"` to a number; the result does not match.

### 7.2. `IN` uses String literals

```java
msg.setStringProperty("region", "VN");
```

the selector:

```sql
region IN ('VN', 'SG', 'TH')
```

matches because `region` is a String. In standard JMS selector syntax, `IN` is defined for a **String-valued or NULL identifier** with a list of String literals. Do not assume SQL `n IN (1, 2, 3)` is supported by portable JMS selectors. For numeric properties, express it explicitly:

```sql
n = 1 OR n = 2 OR n = 3
```

If a broker system supports an extension for numeric `IN`, that may be proprietary; do not depend on it when wanting Jakarta Messaging-portable code.

### 7.3. `LIKE` is a string pattern filter

```java
msg.setStringProperty("customerCode", "VIP-007");
```

the selector:

```sql
customerCode LIKE 'VIP-%'
```

matches the `VIP-` prefix. `%` matches any sequence of characters, and `_` matches a single character. `LIKE` is not a numeric comparison.

If a business ID is `"000007"`, storing a String and filtering with `customerCode = '000007'` preserves leading zeros, instead of parsing to integer 7 and losing formatting.

## 8. Missing properties, NULL, and negation

Selectors use **three-valued logic**: TRUE, FALSE, and UNKNOWN. If a message lacks the `orderCount` property, the expression:

```sql
orderCount = 12
```

has no numeric value to compare, so the result is **UNKNOWN**. It does not match. To check presence/absence of a property:

```sql
orderCount IS NULL
orderCount IS NOT NULL
```

For an absent property, `IS NULL` evaluates to TRUE.

A subtle point: if property `orderCount` is **String `"12"`**, numeric comparisons are type-mismatched. Under specification rules, comparing two incompatible types evaluates to FALSE; **do not think `orderCount <> 12` is a portable way to catch only non-12 String properties**. Compare with the matching type `orderCount <> '12'`, or better yet, standardize the property schema.

### Property names are case-sensitive

```java
msg.setIntProperty("orderCount", 12);
```

Correct selector:

```sql
orderCount = 12
```

Selector using a different name:

```sql
OrderCount = 12
```

will reference a different identifier, usually returning UNKNOWN if `OrderCount` does not exist.

Choose property names that are valid JMS selector identifiers (such as `orderCount`, `retryCount`, `region`), avoiding reserved keywords like `AND`, `OR`, `BETWEEN`, `LIKE`, `IN`. The prefixes `JMSX` and `JMS_` are reserved for standard/provider properties; do not use them arbitrarily for custom properties.

## 9. Applying in Spring JMS: sending properties and declaring selectors

### 9.1. Producer using `MessagePostProcessor`

If the application sends payloads via `JmsTemplate.convertAndSend`, properties can be attached inside a `MessagePostProcessor`:

```java
jmsTemplate.convertAndSend(
        "orders.in",
        "ORDER-001",
        message -> {
            message.setIntProperty("orderCount", 12);
            message.setStringProperty("region", "VN");
            return message;
        }
);
```

Here:

- `"ORDER-001"` is the **body** after Spring `MessageConverter` converts it into a JMS message.
- `orderCount` is an `int` **numeric property**.
- `region` is a **String property**.
- The selector `orderCount >= 10 AND region = 'VN'` can match if destination, provider, and consumer are compatibly configured.
- If accidentally changed to `setStringProperty("orderCount", "12")`, the `orderCount >= 10` part stops matching.

`MessagePostProcessor` is invoked **before sending**; properties generally cannot be arbitrarily modified on a received message because received message properties are read-only by default.

### 9.2. Consumer using `@JmsListener(selector = ...)`

```java
@Component
class HighVolumeListener {

    @JmsListener(
            destination = "orders.in",
            selector = "orderCount >= 10 AND region = 'VN'")
    public void handle(String body) {
        System.out.println("High volume: " + body);
    }
}
```

This is a **class in a Spring application** with JMS infrastructure, requiring imports for `org.springframework.stereotype.Component` and `org.springframework.jms.annotation.JmsListener`. The selector inspects only **properties/headers**; the handler receives the body processed by the converter.

Do not place this listener on the same Queue in the synchronous receive demo in section 10 if you want to observe exact output: two competing consumers can steal messages from each other. In production applications, actively design selectors and concurrency across consumers.

### 9.3. Synchronous consumer using `receiveSelected`

```java
JmsTemplate receiver = new JmsTemplate(connectionFactory);
receiver.setReceiveTimeout(1_000L);

Message numeric = receiver.receiveSelected(
        "orders.in", "orderCount >= 10");
Message textual = receiver.receiveSelected(
        "orders.in", "orderCount = '12'");
```

This is a snippet inside a method with `ConnectionFactory connectionFactory` and `import jakarta.jms.Message`. If no matching message is available within the wait timeout, each call can return **`null`**. Do not interpret `null` as "the Queue is completely empty": the Queue may contain messages not matching the selector or already handled by another consumer.

## 10. Full demo Java 17 + Spring Boot + Artemis: two messages with the same numeric content

The demo is designed to prove **same displayed value `12`, different property types, hence different selector results**.

- Send message `NUMERIC-12` with property `orderCount` of type `int` and value `12`.
- Send message `STRING-12` with property `orderCount` of type `String` and value `"12"`.
- Receive with numeric selector `orderCount = 12`: receives only `NUMERIC-12`.
- Next, try numeric selector `orderCount > 10`: does not receive the remaining `STRING-12`, so it times out and returns `null`.
- Receive with string selector `orderCount = '12'`: receives `STRING-12`.
- Read the raw property to confirm `getObjectProperty` is `String` while `getIntProperty` can still return `12` per the conversion table.

**Environment:** Java 17+, Gradle compatible with Spring Boot 3.3.x, Spring Boot 3.3.13, external Apache ActiveMQ Artemis JMS provider. This program **does not declare `@JmsListener`**, to avoid consumer competition with `JmsTemplate.receiveSelected`.

### 10.1. Starting a local broker

A machine with Docker can run an Artemis broker for learning:

```bash
docker run --detach --rm --name artemis-selector-types -p 61616:61616 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest-alpine
```

Wait for the broker to be ready via `docker logs artemis-selector-types`. The broker must have Queue `demo.selector.property-types` or allow auto-creating Queues. Many test Artemis configurations enable auto-create; in controlled environments, proactively provision destinations and grant appropriate permissions.

**Important:** start with a clean Queue, with no leftover messages from a previous run and no other consumers, if you want to compare against the illustrative output below. Do not use demo passwords in production.

### 10.2. Gradle project

File `settings.gradle`:

```groovy
rootProject.name = 'jms-selector-property-types'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

File `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
  jms:
    pub-sub-domain: false
    template:
      receive-timeout: 800ms
```

`receive-timeout: 800ms` lets non-matching selector checks **return `null` after a finite wait**, rather than blocking indefinitely. This timeout applies to receive methods using the **auto-configured `JmsTemplate`**. It does not create or alter property data types.

### 10.3. Full Java class

Create `src/main/java/example/jms/SelectorPropertyTypesApplication.java`:

```java
package example.jms;

import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class SelectorPropertyTypesApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                SelectorPropertyTypesApplication.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(JmsTemplate jmsTemplate) {
        return args -> {
            String queue = "demo.selector.property-types";

            // A. Same value 12 but property is Integer.
            jmsTemplate.convertAndSend(
                    queue, "NUMERIC-12", message -> {
                        message.setIntProperty("orderCount", 12);
                        message.setStringProperty("region", "VN");
                        return message;
                    });

            // B. Same display value "12" but is String.
            jmsTemplate.convertAndSend(
                    queue, "STRING-12", message -> {
                        message.setStringProperty("orderCount", "12");
                        message.setStringProperty("region", "VN");
                        return message;
                    });

            Object numeric = jmsTemplate.receiveSelectedAndConvert(
                    queue, "orderCount = 12");

            // After numeric is received, only String "12" remains.
            // Numeric selector cannot compare String > 10.
            Object noNumericMatch =
                    jmsTemplate.receiveSelectedAndConvert(
                            queue, "orderCount > 10");

            // String selector finds the remaining String message.
            Message stringMessage = jmsTemplate.receiveSelected(
                    queue, "orderCount = '12'");

            if (!(stringMessage instanceof TextMessage textMessage)) {
                throw new IllegalStateException(
                        "Missing expected STRING-12 TextMessage");
            }

            System.out.println("NUMERIC_EQUALS=" + numeric);
            System.out.println("NUMERIC_GT_AGAIN=" + noNumericMatch);
            System.out.println("STRING_EQUALS=" + textMessage.getText());
            System.out.println("STRING_TYPE=" +
                    stringMessage.getObjectProperty(
                            "orderCount").getClass().getSimpleName());
            System.out.println("STRING_GET_INT=" +
                    stringMessage.getIntProperty("orderCount"));
        };
    }
}
```

The class uses `ApplicationRunner`, so the lambda can throw exceptions from JMS getters. Spring Boot creates `JmsTemplate` and `ConnectionFactory` from the starter and configuration. The default `SimpleMessageConverter` converts `String` payloads into `TextMessage`.

### 10.4. Running and observing output

From the directory containing `build.gradle`, if a compatible Gradle is installed:

```bash
gradle bootRun
```

If the project has a Gradle Wrapper: Linux/macOS uses `./gradlew bootRun`; Windows uses `gradlew.bat bootRun`.

With the broker ready, a clean Queue, no other consumers, and successful sends, the expected **lines printed by the application itself** are:

```text
NUMERIC_EQUALS=NUMERIC-12
NUMERIC_GT_AGAIN=null
STRING_EQUALS=STRING-12
STRING_TYPE=String
STRING_GET_INT=12
```

Explanation:

- `NUMERIC_EQUALS=NUMERIC-12`: numeric property matches numeric literal.
- `NUMERIC_GT_AGAIN=null`: after the numeric message is received, the String property `"12"` remains; it does not match the numeric comparison `> 10`.
- `STRING_EQUALS=STRING-12`: selector `= '12'` matches String.
- `STRING_TYPE=String`: the property was actually written with type String.
- `STRING_GET_INT=12`: the getter is allowed to convert a valid numeric string to int; **the selector does not perform the corresponding conversion**.

This is the **expected output under the stated conditions**, not the result of an actual broker run executed while authoring the article. Broker dispatch, queue backlog, other consumers, permissions, or networking can alter results or raise errors. Do not turn the demo into a millisecond-exact real-time test.

Stop the learning environment when finished:

```bash
docker stop artemis-selector-types
```

## 11. Distinguishing filtering with `@JmsListener` vs. `JmsTemplate`

In Spring, a selector can be placed on an **asynchronous consumer** or a **synchronous consumer**.

**Asynchronous:**

```java
@JmsListener(
        destination = "orders.events",
        selector = "orderCount >= 10 AND region = 'VN'")
public void onHighVolumeOrder(String body) {
    // Only runs if the message matches the selector.
}
```

**Synchronous:**

```java
Object result = jmsTemplate.receiveSelectedAndConvert(
        "orders.events",
        "orderCount >= 10 AND region = 'VN'");
```

Both use the same Jakarta Messaging selector data-type rules. Differences:

| Topic | `@JmsListener(selector=...)` | `JmsTemplate.receiveSelected(...)` |
| --- | --- | --- |
| Who creates the consumer? | Spring listener container | `JmsTemplate` during the call |
| Property type checked | Per setter when producer sends | Identical |
| Selector scope | Consumer bound to listener | Only the consumer in that receive call |
| Processing flow | Async callback when message arrives | Calling thread blocks until received or timeout |
| No match | Handler does not receive that message | Can return `null` on timeout |
| Best suited for | Continuous processing | Bounded synchronous checks and tasks |

`@JmsListener` **does not auto-parse JSON bodies** to read an `orderCount` field. When the payload is a DTO containing `int count`, if the producer did not attach a JMS property, the selector still cannot use that field.

### Another consumer may still receive the message

In a Queue, a message not matching consumer A's selector can stay on the Queue for consumer B with a different selector or an unfiltered consumer. With a Topic, delivery semantics depend on subscriptions; a message not matching a subscription's selector is not delivered to that subscription.

If an app runs both a listener with selector `orderCount = 12` and an unfiltered consumer on the same Queue, the unfiltered consumer may receive the message first. Therefore, when testing property types, **avoid competing consumers** for clear results.

## 12. Inspecting property types properly when debugging

When a selector fails to match, the first step is not arbitrarily adding single quotes to the condition, but **verifying the type at send time**.

### 12.1. Using `getObjectProperty`

```java
Message message = ...; // An actual JMS Message just received.

Object raw = message.getObjectProperty("orderCount");

if (raw == null) {
    System.out.println("orderCount missing");
} else {
    System.out.println("type=" + raw.getClass().getSimpleName());
    System.out.println("value=" + raw);
}
```

This is a snippet inside a method with a valid `Message message`; `getObjectProperty` can throw `JMSException`, so the method must declare or handle the checked exception. For `setIntProperty`, the type is usually `Integer`; for `setStringProperty`, the type is `String`.

### 12.2. Checking `propertyExists`

```java
if (!message.propertyExists("orderCount")) {
    System.out.println("Property has not been set");
}
```

Distinguish a **missing property** from a **present property with the wrong type**. Do not patch it with `orderCount IS NULL` if the real issue is `"12"` being written as a String instead of an int.

### 12.3. Observing actual headers/properties, not just the body

With a `TextMessage`, `getText()` is not enough to verify properties. When logging for debugging, record allowed metadata:

```text
messageId=...
property=orderCount
propertyType=java.lang.String
propertyValue=12
selector=orderCount > 10
matchExpected=false
```

This is an **illustrative** log format, not output from a specific program. Avoid logging payloads or properties containing tokens, personal information, or operational secrets. If the broker provides a management console displaying property types, use it for cross-checking, while still testing with the Jakarta JMS API to avoid misleadingly similar console renderings.

### 12.4. Practical checklist

1. Which setter did the producer call for the property? `setIntProperty` or `setStringProperty`?
2. Does the property name match exact **casing**?
3. Is the consumer using a **numeric** selector or a **single-quoted String literal**?
4. Is the property actually on the message, or is the data only inside the JSON body?
5. Is another consumer receiving from the same Queue?
6. Was the message expired, rolled back, redelivered, or moved to DLQ?
7. Does the broker/provider have custom rules, transformations, or selector extensions?
8. Did the schema change between producer versions?

## 13. Designing a property schema to prevent type mismatches

This is a **cross-application contract**: the producer in service A and consumer in service B must agree on property names, types, and corresponding selectors.

Simple contract example:

| Property | JMS Type | Meaning | Example selector |
| --- | --- | --- | --- |
| `eventType` | String | Event type | `eventType = 'ORDER_CREATED'` |
| `region` | String | Region code | `region IN ('VN','SG')` |
| `orderCount` | int | Order quantity | `orderCount >= 10` |
| `amountMinor` | long | Total amount in minor units | `amountMinor > 100000` |
| `isPriority` | boolean | Business flag | `isPriority = TRUE` |
| `createdAtEpochMs` | long | Unix time in ms | `createdAtEpochMs >= 1760000000000` |
| `postalCode` | String | Identifier keeping leading zeros | `postalCode = '00123'` |

Decide the **type right when building the event schema**:

- **Quantities, retry counts, scores compared by magnitude:** use appropriate `int`/`long`/`float`/`double`.
- **Identifiers, card numbers, phone numbers, ZIP codes, invoice codes with leading zeros:** typically use `String`, not numeric comparisons.
- **Timestamps requiring greater/less-than comparisons:** use `long` epoch millis per schema contract if selectors need to filter them.
- **Business states:** typically use a `String` with a constrained value set or a true `boolean`; do not silently convert String `"true"` to boolean on the consumer.

### Producer receiving data from HTTP/CSV

Data coming from a request or CSV may arrive as a String, but needs validation:

```java
String rawCount = "12"; // Example input data already validated.

int orderCount;
try {
    orderCount = Integer.parseInt(rawCount);
} catch (NumberFormatException ex) {
    throw new IllegalArgumentException(
            "orderCount must be a valid integer", ex);
}

jmsTemplate.convertAndSend("orders.in", "ORDER-003",
        msg -> {
            msg.setIntProperty("orderCount", orderCount);
            return msg;
        });
```

This is a snippet inside a service with `JmsTemplate` injected. If business bounds are required (e.g., 0–1,000), check the range after parsing; `Integer.parseInt` only checks valid numeric representation within `int` range, without enforcing business rules automatically.

### Avoid changing types under the same name without versioning

If an old producer version emits `orderCount` as a String while a new version switches to `int`, a consumer using:

```sql
orderCount >= 10
```

will see only messages with a proper numeric property; unprocessed old messages will not match. Do not "quick-patch" with assumptions about automatic SQL conversions.

A clear migration strategy:

1. Add a new `int` property `orderCountInt` in the producer, while temporarily keeping String `orderCountText` if compatibility is needed.
2. Update new consumers to filter `orderCountInt >= 10`.
3. Monitor backlog and remaining old producer versions.
4. Once the parallel phase ends, drop the old property per the upgrade plan.

You can also use an `int` `schemaVersion` to distinguish variants. Avoid using an ambiguous selector on a property name that is sometimes String and sometimes int in a large system whenever possible.

## 14. JMS headers and special type cases

Not all selector identifiers are custom properties. Certain **JMS headers** are allowed in selectors by the specification and have their own types/representations.

### `JMSPriority` is numeric

```sql
JMSPriority >= 7
```

this is a numeric expression. **`JMSPriority = '7'` is not equivalent**, because `'7'` is a String literal.

### `JMSDeliveryMode` is represented as a String in selectors

Even though the Java API returns delivery mode as integer constants `DeliveryMode.PERSISTENT` / `NON_PERSISTENT`, **in JMS selectors** the `JMSDeliveryMode` header is treated as having special String values:

```sql
JMSDeliveryMode = 'PERSISTENT'
```

This is an exception **defined by the JMS selector specification**, not because the provider auto-casts every property. Do not use this exception as an excuse to write `orderCount = '12'` when the property is actually an `int`.

### `JMSType`, `JMSCorrelationID`, `JMSMessageID`

These headers can be used in selectors per JMS rules when values and syntax fit, but they do not replace custom properties for quantities/prices. Some headers can be NULL and are subject to three-valued logic.

### Do not confuse `JMSXDeliveryCount` with a custom String `"1"`

`JMSXDeliveryCount` is an integer JMS-defined property (supplied by the provider in delivery context). Selectors, if supported by the broker and present, must use a matching numeric literal. Do not set a String property of the same name `"1"` and assume equivalence.

## 15. Performance, operations, and safety when using selectors

Selectors are useful because the JMS provider can **filter messages before delivering them to consumers**. However:

- Selectors do not make **non-matching messages disappear** from a Queue; they can continue waiting for another consumer, causing backlog.
- Many complex selectors, many consumers, and large Queues can increase broker cost; measure on the real provider instead of guessing.
- A mistyped property can cause an entire new consumer group to **miss old messages**, even though bodies look valid on dashboards.
- Some brokers have proprietary selector syntax/extensions. When Jakarta Messaging portability is required, stick to the specification's SQL-92 subset.
- Do not put raw user input into selectors via uncontrolled String concatenation. If dynamic identifier filtering is needed, validate and escape single quotes per JMS syntax; better yet, use allowlists and explicit configuration.

For example, when a region code is `"O'Brien"`, the JMS literal must be `'O''Brien'`. Never build selector conditions from unvalidated input if it allows altering expression semantics.

**Do not use selectors for business authentication/authorization.** Selectors are routing and delivery optimization tools; broker/queue security and producer/consumer permissions must be configured separately.

## 16. Common errors, questions, and exercises

### Quick troubleshooting table

| Symptom | Likely cause to check | Resolution |
| --- | --- | --- |
| `orderCount > 10` misses messages showing "12" | Property is actually String `"12"`. | Producer uses `setIntProperty`, rather than blindly changing the selector. |
| `orderCount = '12'` misses messages | Property is actually int 12. | Use `orderCount = 12` for numeric properties. |
| `getIntProperty` returns 12 yet selector `> 10` still fails to match | Getter is allowed to parse String to number; selector does not convert. | Use `getObjectProperty` to inspect original type. |
| `postalCode` loses leading zeros | Code stored as int. | Choose a String property and quoted selector. |
| `paid = TRUE` does not match | Producer used String `"true"`. | Use a boolean property or String selector matching the contract. |
| `amountMinor >= 1000` does not match | Field only in JSON body, not yet a JMS property. | Set a separate numeric JMS property before sending. |
| Selector `OrderCount = 12` receives nothing | Property name casing differs from `orderCount`. | Match exact name and casing. |
| `n IN (1,2,3)` syntax error/non-portable | `IN` in standard JMS is for String literal lists. | For numbers use `n=1 OR n=2 OR n=3`. |
| String property `name > 'A'` errors/misbehaves | String comparisons only support `=`, `<>`; `LIKE` for patterns. | Fix the filtering logic. |
| Invalid selector causes startup failure | Invalid selector syntax. | Read root cause `InvalidSelectorException`; test with the provider. |
| Consumer sees no messages despite valid selector | Another consumer took Queue messages, TTL expired, wrong destination, or ACLs. | Check broker, Queue/Topic, concurrency, transactions. |
| Schema change drops routing for old messages | Same property name written with two types across versions. | Version the schema, migrate incrementally, test backlog. |

### Question 1

Producer:

```java
msg.setStringProperty("quantity", "9");
```

What happens with the two selectors `quantity > 5` and `quantity = '9'`?

**Answer:** `quantity > 5` does not match because a String is not used as a number; `quantity = '9'` matches.

### Question 2

Producer:

```java
msg.setIntProperty("quantity", 9);
```

Does the selector `quantity = '9'` match?

**Answer:** No. Literal `'9'` is a String, whereas the property has type `int`. Use `quantity = 9`.

### Question 3

Why can `msg.getStringProperty("quantity")` return `"9"` when the producer called `setIntProperty("quantity", 9)`?

**Answer:** Getters allow converting a numeric value to String per the conversion table. Reading as a String does not change the original type in selectors.

### Question 4

`msg.setLongProperty("totalMinor", 1_000_000L)` and selector `totalMinor >= 500000`: is this appropriate?

**Answer:** Yes. This is a proper numeric comparison. Using `long` for minor currency units also avoids floating-point errors in simple exact comparisons.

### Question 5

If property `region` does not exist, is `region = 'VN'` FALSE or UNKNOWN?

**Answer:** UNKNOWN. Only TRUE makes a message match; use `region IS NULL` to find messages missing the property.

### Question 6

A consumer uses `orderCount <> 10`. Should it be used to find every message where property `orderCount` is **not** int 10, including String `"10"`?

**Answer:** No. Cross-type comparison is not a reliable way to classify schemas; compare with the right type, attach a dedicated schema property/flag, or standardize the producer.

### Question 7

You want to filter postal code `00123`. What property type should you write?

**Answer:** String `"00123"`, and select with `postalCode = '00123'`. It is an identifier, not a number used for arithmetic.

### Practice exercises

From the demo in section 10:

1. Change `setIntProperty("orderCount", 12)` to `setStringProperty("orderCount", "12")`. Predict the result of `receiveSelectedAndConvert(queue, "orderCount = 12")`; run on a clean Queue to verify.
2. Replace one message with `setLongProperty("orderCount", 12L)`. Try `orderCount >= 10` and explain numeric promotion.
3. Add `region = 'VN'` with `AND`, then intentionally change `region` to `"vn"` to verify String equality is case-sensitive.
4. Write `postalCode = "00123"` and test a string selector; verify why parsing int 123 loses formatting.
5. Create a message without the `orderCount` property; compare `orderCount = 12` against `orderCount IS NULL`.

**In all exercises**, use a dedicated Queue or a controlled Queue reset, do not allow other listeners/consumers to compete, and use a finite receive timeout to avoid hanging the program.

## 17. Official references and takeaways

- [Jakarta Messaging 3.1 Specification — 3.5 Message Properties and 3.8 Message Selection](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Jakarta Messaging 3.1 — Message interface API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message)
- [Spring Framework — Sending a Message with JmsTemplate and MessagePostProcessor](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
- [Spring Framework 6.2 — JmsTemplate API, receiveSelected/receiveSelectedAndConvert](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Getting Started — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
- [Spring Boot 3 — JMS / ActiveMQ Artemis Configuration](https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html)

**Summary of rules to remember:**

1. **The setter determines the type:** `setIntProperty("n", 12)` differs from `setStringProperty("n", "12")`.
2. **Selectors preserve the actual type:** `n = 12` differs from `n = '12'`; `n > 10` is meaningful only when `n` is numeric.
3. **Getter conversion does not mean selector conversion:** `getIntProperty` can parse `"12"`, but selectors do not auto-parse.
4. **Selectors do not read JSON bodies:** to filter on a field, attach a supported property/header.
5. **Design a consistent schema:** agree on names, types, value ranges, and versions between producer and consumer; test on a real broker to avoid silent routing bugs.
