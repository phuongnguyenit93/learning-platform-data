# BETWEEN, IN, LIKE, and IS NULL in JMS Message Selectors (Spring Framework JMS)

## 1. Why filter messages before the consumer receives them?

Imagine a queue `orders.events` containing many messages sent by different applications:

- Orders with TotalAmount from 100 to 500 need to go to the promotion-check group.
- Events with EventType in the set "ORDER_CREATED", "ORDER_PAID" need one consumer to process them.
- Messages with CorrelationKey starting with "ORD-" need to route to one business flow.
- Messages without a Region attached need a dedicated consumer to detect and handle them under a missing-data policy.

If a consumer receives all messages and then uses if/else to discard unwanted ones, it wastes bandwidth and delivery time while also risking **acknowledging/committing a message meant for another consumer**. JMS provides the **message selector** mechanism so a consumer declares its matching criteria right when creating the consumer or subscription.

A selector is a String expression following **a subset of SQL-92 conditional syntax**. The JMS provider uses **headers and message properties** to evaluate the expression; only when the result is **TRUE** is the message eligible for delivery to the consumer carrying that selector.

Core operators covered in this lesson:

| Operator | Example | When to use? |
| --- | --- | --- |
| BETWEEN | AmountMinor BETWEEN 1000 AND 5000 | Numeric range inclusive of both endpoints. |
| NOT BETWEEN | PriorityScore NOT BETWEEN 1 AND 3 | Numeric values outside the range. |
| IN | EventType IN ('CREATE', 'UPDATE') | Belongs to a listed set of **strings**. |
| NOT IN | Region NOT IN ('VN', 'SG') | String not in the listed set. |
| LIKE | CorrelationKey LIKE 'ORD-%' | String pattern matching with wildcards. |
| NOT LIKE | CorrelationKey NOT LIKE 'TMP-%' | Excludes strings matching the pattern. |
| IS NULL | Region IS NULL | Property does not exist or supported header has a null value. |
| IS NOT NULL | Region IS NOT NULL | Property exists and is not null. |

**Important:** a selector is not a database SQL query, cannot read a JSON body directly, does not support full SQL, and does not create consumer groups or partition access rights. It is a **filter at the JMS delivery layer**; specific storage and indexing features and performance depend on the broker.

## 2. Distinguishing body, headers, and message properties

A JMS message has three areas:

~~~mermaid
flowchart LR
  P["Producer"] --> M["JMS Message"]
  M --> H["Standard headers: JMSType, JMSPriority..."]
  M --> R["Properties: EventType, AmountMinor, Region..."]
  M --> B["Body: TextMessage JSON / MapMessage / BytesMessage"]
  H --> S["JMS selector"]
  R --> S
  B --> X["Cannot be read directly by standard selectors"]
  S --> C["Matching consumer/subscription"]
~~~

For example, a producer sends a TextMessage with a JSON body:

~~~json
{
  "orderId": "O-42",
  "amountMinor": 2500,
  "region": "VN"
}
~~~

With only this body, the selector "AmountMinor BETWEEN 1000 AND 5000" **cannot** look up the `amountMinor` field inside JSON. A JMS property must be attached outside the body:

~~~java
jmsTemplate.convertAndSend(
        "orders.events",
        "{\"orderId\":\"O-42\",\"amountMinor\":2500,\"region\":\"VN\"}",
        message -> {
            message.setIntProperty("AmountMinor", 2500);
            message.setStringProperty("Region", "VN");
            message.setStringProperty("EventType", "ORDER_CREATED");
            return message;
        });
~~~

This is a **snippet** inside an application that has `JmsTemplate` injected; it does not have a standalone `main()`. `MessagePostProcessor` receives the `jakarta.jms.Message` after the converter creates it, then attaches the proper property types.

Now the selector can use `AmountMinor`, `Region`, and `EventType` **without parsing the body**. The consumer still needs to parse and validate JSON after receiving; JMS filtering does not replace business contract checks.

### 2.1. Names accessible to a selector

The Jakarta Messaging 3.1 specification restricts standard header references in selectors to these names: **JMSDeliveryMode, JMSPriority, JMSMessageID, JMSTimestamp, JMSCorrelationID, JMSType**. In addition, message properties with valid names can be accessed. **Do not assume every JMS header can be used in a selector**; for instance, `JMSExpiration` or `JMSDeliveryTime` being headers does not make them standard selector names.

Application-set message properties should have simple, stable names that are valid under Java identifier rules:

~~~text
EventType
AmountMinor
CustomerTier
Region
CorrelationKey
SchemaVersion
~~~

Avoid naming properties like JSON paths such as `order.amount`, names with spaces, or SQL keywords as identifiers. Property names are case-sensitive: `EventType` **differs** from `eventType`. Names starting with `JMSX` belong to the standard JMSX group, and `JMS_` is the provider-specific namespace; do not use them arbitrarily for application contracts.

### 2.2. Evaluated on actual typed values, not display strings

~~~java
message.setIntProperty("AmountMinor", 2500);       // Numeric.
message.setStringProperty("EventType", "CREATE");   // String.
message.setBooleanProperty("Urgent", true);         // Boolean.
~~~

The selector sees the corresponding types that were set. It **does not automatically apply String-to-Number conversions** that property getter methods may support.

~~~sql
AmountMinor BETWEEN 1000 AND 5000
EventType IN ('CREATE', 'UPDATE')
Urgent = TRUE
~~~

The syntax above shows JMS selector expressions, not full SQL SELECT statements. In Java code, pass each expression as a String.

## 3. BETWEEN: matching a numeric range inclusive of both endpoints

Syntax per specification:

~~~sql
arithmetic_expression BETWEEN lower_expression AND upper_expression
arithmetic_expression NOT BETWEEN lower_expression AND upper_expression
~~~

Meaning:

~~~text
X BETWEEN A AND B
        equivalent to
(X >= A) AND (X <= B)

X NOT BETWEEN A AND B
        equivalent to
(X < A) OR (X > B)
~~~

`BETWEEN` **includes** both the lower and upper bounds. It is not a half-open interval like `A <= X < B`.

Example:

~~~sql
AmountMinor BETWEEN 1000 AND 5000
~~~

| AmountMinor set | Result |
| --- | --- |
| 999 | FALSE |
| 1000 | TRUE — exact lower bound |
| 2500 | TRUE |
| 5000 | TRUE — exact upper bound |
| 5001 | FALSE |
| Missing | UNKNOWN, does not match |

Here `AmountMinor` should be set using `setIntProperty` or `setLongProperty`. If the sender uses `setStringProperty("AmountMinor", "2500")`, you **must not** expect `BETWEEN` to convert `"2500"` into the number 2500 automatically.

### 3.1. Numeric types and precision

Jakarta Messaging supports exact integer and approximate floating numeric literals and applies Java numeric promotion rules during comparisons. Comparisons between exact and approximate numbers may trigger promotion, so for **monetary amounts**, use integer minor units per contract:

~~~java
message.setLongProperty("AmountMinor", 125_000L);
~~~

~~~sql
AmountMinor BETWEEN 100000 AND 200000
~~~

When using minor units, the contract must define the currency, scale, and `long` range. Avoid passing money as a `double` property and assuming decimal comparisons will have exact precision.

### 3.2. Does BETWEEN support dates and times?

JMS selectors have no standard SQL DATE/TIMESTAMP type with `NOW()`, `DATE_TRUNC()`, or automatically parsed date strings. The specification suggests expressing time as **Java long milliseconds**. Sending example:

~~~java
message.setLongProperty(
        "OccurredAtEpochMs",
        java.time.Instant.parse(
                "2026-10-30T10:00:00Z").toEpochMilli());
~~~

When building the selector, compute the bounds in Java:

~~~java
long from = java.time.Instant.parse(
        "2026-10-30T00:00:00Z").toEpochMilli();
long to = java.time.Instant.parse(
        "2026-10-31T00:00:00Z").toEpochMilli();

String selector = "OccurredAtEpochMs >= " + from
        + " AND OccurredAtEpochMs < " + to;
~~~

Both are **snippets**, not standalone main files. In the time-window example, an **exclusive upper bound** is used to represent one UTC day and avoid guessing "the last millisecond of the day." With `BETWEEN`, the upper bound is **included**, which is unsuitable when adjacent time windows must not overlap.

### 3.3. When to use NOT BETWEEN?

~~~sql
PriorityScore NOT BETWEEN 1 AND 3
~~~

When the numeric property exists, values less than 1 or greater than 3 match. If `PriorityScore` does not exist, the comparison cannot be decided, so the result is **UNKNOWN** rather than treating missing as "outside the range."

To also receive messages missing `PriorityScore`, use:

~~~sql
PriorityScore IS NULL
OR PriorityScore NOT BETWEEN 1 AND 3
~~~

This is a different business requirement; explicitly add the missing branch, and do not broaden filtering unless requested.

### 3.4. Common mistakes with BETWEEN

- Assuming `BETWEEN` excludes the upper bound; in fact it **includes** both bounds.
- Writing the total amount as a String property and then applying numeric `BETWEEN`.
- Using approximate decimals for money requiring exact calculations.
- Using standard SQL date literals in a JMS selector; use epoch milliseconds instead.
- Changing timezones before computing day bounds, causing messages to fall into another day.
- Writing `BETWEEN 5000 AND 1000` thinking the provider will swap the bounds automatically.
- Assuming `NOT BETWEEN` automatically selects messages with missing properties; it yields UNKNOWN.
- Failing to validate negative values/ranges on sender and consumer.

## 4. IN: matching a list of String literals

JMS syntax:

~~~sql
property_name IN ('VALUE_A', 'VALUE_B', 'VALUE_C')
property_name NOT IN ('VALUE_A', 'VALUE_B', 'VALUE_C')
~~~

According to Jakarta Messaging, **IN uses a String-typed or NULL identifier and a list of string literals**. It is not general SQL `IN` with subqueries, arbitrary expression lists, or numeric literal lists.

Example:

~~~sql
EventType IN ('ORDER_CREATED', 'ORDER_PAID', 'ORDER_CANCELLED')
~~~

roughly equivalent to:

~~~sql
EventType = 'ORDER_CREATED'
OR EventType = 'ORDER_PAID'
OR EventType = 'ORDER_CANCELLED'
~~~

| EventType | Result of IN |
| --- | --- |
| "ORDER_CREATED" | TRUE |
| "ORDER_PAID" | TRUE |
| "ORDER_SHIPPED" | FALSE |
| "order_created" | FALSE due to different String case |
| Property absent | UNKNOWN |

### 4.1. IN is not for listing numbers in standard syntax

Do not write:

~~~sql
AmountMinor IN (100, 200, 300)
~~~

This form is not part of standard Jakarta Messaging `IN` syntax because elements must be string literals. If `AmountMinor` is numeric and the set of numbers is small, express it with comparisons:

~~~sql
AmountMinor = 100 OR AmountMinor = 200 OR AmountMinor = 300
~~~

And if the data is really an enum/routing label, it is better to use a String property:

~~~java
message.setStringProperty("CustomerTier", "GOLD");
~~~

~~~sql
CustomerTier IN ('GOLD', 'PLATINUM')
~~~

### 4.2. Case sensitivity and differences from database SQL

Selector keywords such as `IN`, `AND`, and `LIKE` can be written in uppercase or lowercase. However, **property names** and **String values** must match the exact identifier/string. Do not expect a database SQL collation to turn `"vn"` into `"VN"`.

Producers should normalize enums before attaching properties (per contract). For example, standardize `Region` to always be an uppercase ISO code. Consumers should not try to build case-insensitive expressions using SQL functions like `UPPER()`/`LOWER()`, because those functions are not part of standard JMS selectors.

### 4.3. NOT IN and missing values

~~~sql
Region NOT IN ('VN', 'SG')
~~~

With `Region="US"`, the condition is TRUE. With `Region="VN"`, FALSE. If **Region is not set**, the result is UNKNOWN rather than TRUE.

If the goal is "not in VN/SG, **including when region is unspecified**":

~~~sql
Region IS NULL OR Region NOT IN ('VN', 'SG')
~~~

Distinguish the business intent: messages missing `Region` may need quarantine rather than entering the same workflow as other countries.

### 4.4. Strings containing single quotes

JMS string literals are enclosed in single quotes. An embedded single quote is represented by **writing two consecutive single quotes**, not by inserting a backslash as in Java.

~~~sql
OwnerName IN ('O''Reilly', 'D''Angelo')
~~~

This is JMS selector syntax. Inside a double-quoted Java String:

~~~java
String selector =
        "OwnerName IN ('O''Reilly', 'D''Angelo')";
~~~

Do not use double quotes around string literals in a JMS selector. This example also reminds us not to build selectors directly from arbitrary input without escaping and allowlisting.

## 5. LIKE: String pattern matching with % and _

`LIKE` processes String patterns; it is **not** a regular expression and not Java `String.matches(...)`.

| Symbol in pattern | Meaning |
| --- | --- |
| % | Any sequence of characters, including the empty string. |
| _ | Exactly **one** arbitrary character. |
| Other characters | Matches that exact character. |
| ESCAPE | Sets an escape character so % or _ is interpreted literally. |

Example:

~~~sql
CorrelationKey LIKE 'ORD-%'
~~~

Matches `"ORD-1"`, `"ORD-ABC"`, and also `"ORD-"` because `%` can be empty. Does not match `"INV-1"` or `"ord-1"` under normal character comparison.

~~~sql
RegionCode LIKE 'V_'
~~~

Matches `"VN"`, `"VA"`, or any two characters starting with `V`, but does not match `"V"` or `"VNA"`.

### 5.1. Distinguishing % and _

| Value | Pattern 'AB%' | Pattern 'AB_' |
| --- | --- | --- |
| "AB" | TRUE | FALSE |
| "ABC" | TRUE | TRUE |
| "ABCD" | TRUE | FALSE |
| "AB-123" | TRUE | FALSE |
| "ACD" | FALSE | FALSE |
| Missing property | UNKNOWN | UNKNOWN |

If you want exactly three characters, `_` is appropriate; if you want any suffix, use `%`.

### 5.2. ESCAPE for literal % and _

Suppose property `Code` contains `"ORD_2026"`. When writing:

~~~sql
Code LIKE 'ORD_%'
~~~

`_` is interpreted as **any single character**, so `"ORDX2026"` also matches. To require a **literal underscore**, choose an escape character such as `!`:

~~~sql
Code LIKE 'ORD!_%' ESCAPE '!'
~~~

The pattern `"ORD!_%"` means: the letters `"ORD"`, followed by a literal `_`, then any suffix. It matches `"ORD_2026"` and `"ORD_"`, and does not match `"ORDX2026"`.

To match a literal `%`:

~~~sql
Code LIKE 'DISCOUNT!%%' ESCAPE '!'
~~~

Explanation: `"DISCOUNT"`, followed by a literal `%` produced by `!%`, followed by the final `%` wildcard. Thus the pattern matches `"DISCOUNT%10"` or `"DISCOUNT%"`. If an **exact 100% match of a string** is required, using the `=` operator is usually easier to read and less risky than `LIKE`.

### 5.3. ESCAPE inside a Java String

~~~java
String selector =
        "Code LIKE 'ORD!_%' ESCAPE '!'";
~~~

This is a valid Java String; `!` does not need escaping at the Java layer. Choosing an explicit escape character keeps code from breaking when backslashes would otherwise be needed simultaneously in Java strings, SQL literals, and config files.

If the payload can contain the escape character itself or the pattern is generated from external input, define a complete escaping strategy for the target provider; do not naively concatenate a `LIKE` string expecting every character to be literal.

### 5.4. NOT LIKE and UNKNOWN

~~~sql
CorrelationKey NOT LIKE 'TMP-%'
~~~

Only matches Strings that **do not match** the pattern. If `CorrelationKey` is missing, the result of `LIKE` is UNKNOWN; `NOT UNKNOWN` remains UNKNOWN, so the message does not match.

To also receive messages missing `CorrelationKey`:

~~~sql
CorrelationKey IS NULL
OR CorrelationKey NOT LIKE 'TMP-%'
~~~

This can broaden the scope considerably, so test and review the contract before changing it.

### 5.5. LIKE is not regex or full-text search

The following expressions are **not** portable JMS selectors:

~~~text
Name REGEXP '^ORD-[0-9]+$'
Name ILIKE 'ord-%'
LOWER(Name) LIKE 'ord-%'
JSON_VALUE(Payload, '$.type') LIKE 'ORDER%'
~~~

Some providers have proprietary extensions, but extensions must not be treated as knowledge applicable to all JMS brokers. If regex or deep JSON inspection is needed, consider promoting the required routing labels to message properties and validating after receiving.

## 6. IS NULL and IS NOT NULL: handling absent properties

A property may **not be sent by the producer**. The selector treats the value of an absent property as NULL under SQL-92 logic and allows checking:

~~~sql
Region IS NULL
Region IS NOT NULL
~~~

| Case | Region IS NULL | Region IS NOT NULL |
| --- | --- | --- |
| No Region property | TRUE | FALSE |
| Region="VN" | FALSE | TRUE |
| Region="" | FALSE | TRUE |
| Region="UNKNOWN" | FALSE | TRUE |
| Referenceable header has null value | TRUE | FALSE |

**IS NULL does not mean a String containing the text "null".** If a producer sets `setStringProperty("Region", "null")`, that is still a non-null String value, so `Region IS NOT NULL` is TRUE.

### 6.1. Null, empty, and missing are three distinct states

~~~java
// Message A: do not call setStringProperty("Region", ...).
// Message B:
message.setStringProperty("Region", "");
// Message C:
message.setStringProperty("Region", "VN");
~~~

This snippet illustrates three different messages, not three statements run on the same message. With the selector `"Region IS NULL"`, only message A lacking the property matches under missing-property logic. Message B is an empty string, **not** NULL.

JMS property APIs have their own rules for null and data types; do not use a JSON `null` field inside a `TextMessage` body to infer that **message property Region is null**. When distinguishing explicit JSON null is required, the consumer must parse the body with a suitable converter/parser.

### 6.2. Why is Region = NULL wrong?

~~~sql
Region = NULL
Region <> NULL
~~~

Ordinary comparisons with NULL do not return TRUE: under three-valued logic, they return UNKNOWN. To check for a missing property, use:

~~~sql
Region IS NULL
~~~

For a present property:

~~~sql
Region IS NOT NULL
~~~

These are special operators that turn NULL/UNKNOWN into TRUE or FALSE. A similar rule applies to the standard headers allowed in selectors when such a header has a null value.

### 6.3. IS NULL used to filter messages missing metadata

A consumer dedicated to handling cases where the producer omitted `Region` can create the selector:

~~~sql
Region IS NULL AND EventType = 'ORDER_CREATED'
~~~

It only matches `ORDER_CREATED` events without a `Region` property. Even when filtered out, a message missing information may be a data-contract error; the consumer should clearly specify reject/quarantine rather than assuming `Region="VN"` or using server timezone as the source of truth.

## 7. Three-valued logic: TRUE, FALSE, UNKNOWN

This is the difference most likely to cause bugs compared to Java `if/else` filters. A selector matches only when the **final result is TRUE**. Both FALSE and UNKNOWN **do not match**.

Suppose:

~~~sql
AmountMinor BETWEEN 1000 AND 5000
~~~

If `AmountMinor` has not been set, the operand is NULL and the comparison evaluates to UNKNOWN. Wrapping `NOT` around the outside does **not** produce TRUE:

~~~sql
NOT (AmountMinor BETWEEN 1000 AND 5000)
~~~

When `AmountMinor` is missing, `NOT UNKNOWN = UNKNOWN`.

### 7.1. AND truth table

| AND | TRUE | FALSE | UNKNOWN |
| --- | --- | --- | --- |
| TRUE | TRUE | FALSE | UNKNOWN |
| FALSE | FALSE | FALSE | FALSE |
| UNKNOWN | UNKNOWN | FALSE | UNKNOWN |

### 7.2. OR truth table

| OR | TRUE | FALSE | UNKNOWN |
| --- | --- | --- | --- |
| TRUE | TRUE | TRUE | TRUE |
| FALSE | TRUE | FALSE | UNKNOWN |
| UNKNOWN | TRUE | UNKNOWN | UNKNOWN |

### 7.3. NOT truth table

| Expression | NOT |
| --- | --- |
| TRUE | FALSE |
| FALSE | TRUE |
| UNKNOWN | UNKNOWN |

Example:

~~~sql
Region = 'VN' OR AmountMinor BETWEEN 1000 AND 5000
~~~

Message lacks `Region` but `AmountMinor=2500`: left is UNKNOWN, right is TRUE, so `UNKNOWN OR TRUE = TRUE` and the message matches.

Message lacks `Region`, `AmountMinor=100`: left is UNKNOWN, right is FALSE, so `UNKNOWN OR FALSE = UNKNOWN` and it does not match.

Message has `Region="SG"`, `AmountMinor=100`: `FALSE OR FALSE = FALSE`; does not match.

### 7.4. A null check can change the entire logic

Compare:

~~~sql
Region <> 'VN'
~~~

and:

~~~sql
Region IS NULL OR Region <> 'VN'
~~~

The first **does not** receive messages missing `Region`. The second **does**. Both are valid, but they express different business policies.

If the goal is to receive only data with a valid `Region` other than VN:

~~~sql
Region IS NOT NULL AND Region <> 'VN'
~~~

### 7.5. AND, OR, NOT, and parentheses

Selectors prioritize logical operators: `NOT` higher than `AND`, `AND` higher than `OR`. So maintainers do not have to guess, use parentheses when combining multiple conditions.

~~~sql
EventType = 'ORDER_CREATED'
AND (Region = 'VN' OR Region = 'SG')
~~~

Do not omit parentheses if the intent is as above:

~~~sql
EventType = 'ORDER_CREATED'
AND Region = 'VN'
OR Region = 'SG'
~~~

By precedence, the second expression also selects **every** message with `Region='SG'` even when `EventType` is not `ORDER_CREATED`.

`BETWEEN` has its own `AND` **inside the range syntax**, so when mixing `BETWEEN` with `OR`, using parentheses is even more important:

~~~sql
(EventType = 'ORDER_CREATED'
 AND AmountMinor BETWEEN 1000 AND 5000)
OR (EventType = 'RETRY' AND Region = 'VN')
~~~

### 7.6. Summary table of behavior when a property is missing

| Condition | Property missing | Does it match? |
| --- | --- | --- |
| Score BETWEEN 1 AND 5 | UNKNOWN | No |
| Score NOT BETWEEN 1 AND 5 | UNKNOWN | No |
| Region IN ('VN','SG') | UNKNOWN | No |
| Region NOT IN ('VN','SG') | UNKNOWN | No |
| Code LIKE 'ORD-%' | UNKNOWN | No |
| Code NOT LIKE 'ORD-%' | UNKNOWN | No |
| Region IS NULL | TRUE | Yes |
| Region IS NOT NULL | FALSE | No |
| Region = NULL | UNKNOWN | No |
| Region IS NULL OR Region = 'VN' | TRUE | Yes |

## 8. Data types, identifiers, and syntax: rules to memorize

### 8.1. Types accepted by selectors

Properties of type `boolean`, `byte`, `short`, `int`, `long`, `float`, `double`, and `String` can participate in expressions depending on the operator; the specification does not allow taking arbitrary Java DTOs, `BigDecimal`, or `Instant` as directly filterable property values. Normalize metadata before sending.

~~~java
message.setIntProperty("Age", 20);
message.setStringProperty("Region", "VN");
message.setBooleanProperty("Approved", true);
~~~

~~~sql
Age BETWEEN 18 AND 65
Region IN ('VN', 'SG')
Approved = TRUE
~~~

Do **not** treat String `"20"` as int `20` when filtering; getter convenience conversions do not apply to selectors.

### 8.2. Strings and numbers are two different literal types

~~~sql
Age BETWEEN 18 AND 65
~~~

differs from:

~~~sql
Age BETWEEN '18' AND '65'
~~~

The second is not the standard way to compare a numeric property. In a serious routing system, the sender must attach the right property type (`setIntProperty`/`setLongProperty`), and the consumer uses numeric literals.

### 8.3. Valid identifiers and reserved words

- Property names can start with a Java letter, `_`, or `$`, followed by Java identifier parts.
- Property names are **case-sensitive**.
- Do not use `NOT`, `AND`, `OR`, `BETWEEN`, `LIKE`, `IN`, `IS`, `ESCAPE`, `TRUE`, `FALSE`, `NULL` as identifier names.
- String literals use single quotes, with internal single quotes doubled: `'O''Brien'`.
- Keywords and operator keywords are case-insensitive; String values are compared character-by-character and are not automatically uppercased.
- Parentheses can be used to make grouping explicit.
- `=` compares equality and `<>` compares inequality; do not use `==` or `!=` like Java.

### 8.4. Selectors are not database SQL

The following ideas do not belong to standard selectors:

~~~text
SELECT * FROM orders WHERE Region='VN'
JSON_EXTRACT(body, '$.region') = 'VN'
AmountMinor IN (100, 200, 300)
Region ILIKE 'vn%'
ORDER BY JMSTimestamp DESC
LIMIT 10
~~~

A selector is only a **conditional expression**, with no `SELECT`, `FROM`, `ORDER BY`, `LIMIT`, or `JOIN`. Some brokers have proprietary extensions, which sacrifice portability. Start with the syntax defined by Jakarta Messaging.

### 8.5. Invalid selector vs valid selector that does not match

Two different situations:

- **Invalid syntax:** something like `"Region IN ("` or unbalanced quotes. The Jakarta Messaging provider must detect this when the selector is supplied and throw `InvalidSelectorException`.
- **Valid syntax, wrong data:** e.g., `"Age BETWEEN 18 AND 65"` while the sender used `setStringProperty("Age","20")`. The selector may be completely valid yet fail to match as intended.

The provider cannot fully validate the types of all properties at consumer creation time because future messages are not yet known. Therefore, do not treat "listener started with no error" as proof that the selector is working properly.

## 9. How Spring JMS applies selectors

### 9.1. JmsTemplate.receiveSelected(...)

Spring `JmsTemplate` has overloads accepting a selector:

~~~java
Message message = jmsTemplate.receiveSelected(
        "orders.events",
        "AmountMinor BETWEEN 1000 AND 5000");
~~~

This is a snippet inside a Spring bean, requiring `import jakarta.jms.Message`. The method creates an appropriate consumer with the destination and selector, waits for a message, and returns `Message` or `null` on timeout.

When only the String payload converted by `MessageConverter` is needed:

~~~java
Object payload = jmsTemplate.receiveSelectedAndConvert(
        "orders.events",
        "EventType IN ('ORDER_CREATED','ORDER_PAID')");
~~~

The method receives a `Message` matching the selector and converts it with `MessageConverter`. With the default `SimpleMessageConverter` and a `TextMessage` body, the payload is typically a `String`. With a custom message converter, the type differs; the selector still inspects only JMS headers/properties.

**Note:** `receiveSelected` is synchronous/blocking. Set a finite `receiveTimeout` to avoid holding a thread indefinitely:

~~~java
jmsTemplate.setReceiveTimeout(2_000L); // Two seconds.
~~~

If no message matches, receive can return `null` even when the queue contains many **non-matching** messages. `null` only means this receive call did not obtain a matching message within the wait timeout, not that the queue is empty.

### 9.2. @JmsListener(selector = "...")

For asynchronous processing, use the annotation:

~~~java
@Component
class OrderListener {

    @JmsListener(
        destination = "orders.events",
        selector =
            "EventType IN ('ORDER_CREATED','ORDER_PAID') "
            + "AND AmountMinor BETWEEN 1000 AND 5000")
    public void process(String payload) {
        // Validate JSON payload and process business logic.
    }
}
~~~

This is a **snippet** inside an application with JMS listener infrastructure, not a standalone main class. It requires importing `org.springframework.stereotype.Component` and `org.springframework.jms.annotation.JmsListener`. For text messages, a suitable converter binds the payload to `String`.

In `@JmsListener`, `selector` is an attribute of the endpoint/consumer created by the container. If you want to change the selector per tenant or runtime config, you must have an appropriate configuration and consumer recreation/restart mechanism; do not expect mutating an external Java variable to update an already registered selector.

### 9.3. Configuring a consistent listener factory

An application that needs to control transactions, concurrency, domain, error handling, and recovery can define a factory:

~~~java
@Configuration
@EnableJms
class JmsListenerConfig {

    @Bean(name = "jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory factory(
            ConnectionFactory connectionFactory) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-3");
        return factory;
    }
}
~~~

The snippet above requires importing `jakarta.jms.ConnectionFactory`, Spring annotations, and `DefaultJmsListenerContainerFactory`. For real transactions, configure the provider/`ConnectionFactory` and error handling accordingly. Do not treat this stripped-down sample as a complete production configuration.

### 9.4. Using the plain JMS API

You can create a consumer directly:

~~~java
Queue queue = session.createQueue("orders.events");
String selector =
        "Region IN ('VN','SG') "
        + "AND AmountMinor BETWEEN 1000 AND 5000";

try (MessageConsumer consumer =
             session.createConsumer(queue, selector)) {

    Message message = consumer.receive(2_000L);
    // The consumer must be on a started Connection.
}
~~~

This is a snippet in a context with a JMS `Session` and an already started `Connection`. If the `Session` belongs to `JmsTemplate`/a transaction manager, do not manually close a framework-managed `Session` or `Connection`. For self-created consumers, close them with try-with-resources.

If only simple filtering in Spring is needed, `JmsTemplate.receiveSelected` or `@JmsListener` is usually clearer.

## 10. Runnable demo: Java 17, Spring Boot 3.3, and ActiveMQ Artemis

This section creates an application that sends messages with different properties to **four test queues** (each queue has its own UUID to avoid leftover messages). The application uses `JmsTemplate.convertAndSend(...)` to attach properly typed properties, then uses `receiveSelectedAndConvert(...)` to demonstrate the result of each operator.

**Design note:** the example uses only a single synchronous consumer on each receive, with no competing background listeners. Two cases with multiple matching messages **sort the results in Java before printing**, because business logic should not rely on the assumption that messages across queues/sessions always have a deterministic order.

### 10.1. Prepare the broker

Requires JDK 17+, Maven, Docker, and TCP port 61616 free. Start the Artemis broker:

~~~bash
docker run --detach --rm --name selector-demo-broker \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Wait for the broker to be ready before running the application. The demo image uses username/password `artemis`/`artemis` in the sample config; production requires dedicated accounts/permissions, pinned image versions, and never demo passwords.

Because the demo generates dynamic queue names, the broker must allow auto-creating queues. If a deployment disallows auto-creation, pre-declare the corresponding destinations and ACLs, or adjust the demo to use pre-provisioned queues.

Project structure:

~~~text
spring-jms-selectors/
├── pom.xml
└── src/main/
    ├── java/example/jmsselectors/SelectorDemoApplication.java
    └── resources/application.properties
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>spring-jms-selectors</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot 3.x is based on Spring Framework 6.x and Jakarta JMS (`jakarta.jms.*`), without mixing in Spring 5's `javax.jms.*`. Pinning the version in the example helps reproduce the API while learning; production should choose a supported version and test against organizational standards.

### 10.3. application.properties

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

The application only has a `CommandLineRunner`, needing no HTTP server or `@JmsListener`. Every receive is explicitly invoked by code, making it easy to observe which selector matches.

### 10.4. SelectorDemoApplication.java

~~~java
package example.jmsselectors;

import java.util.UUID;
import java.util.stream.Stream;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class SelectorDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SelectorDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(JmsTemplate jms) {
        return args -> {
            jms.setReceiveTimeout(3_000L);

            String runId = UUID.randomUUID()
                    .toString().replace("-", "");
            String qBetween = "demo.sel.between." + runId;
            String qIn = "demo.sel.in." + runId;
            String qLike = "demo.sel.like." + runId;
            String qNull = "demo.sel.null." + runId;

            // BETWEEN: both 15 and 20 belong to [15,20].
            sendNumber(jms, qBetween, "age-14", "Age", 14);
            sendNumber(jms, qBetween, "age-15", "Age", 15);
            sendNumber(jms, qBetween, "age-20", "Age", 20);
            sendNumber(jms, qBetween, "age-21", "Age", 21);

            String between = String.join(", ",
                    Stream.of(
                            take(jms, qBetween,
                                    "Age BETWEEN 15 AND 20"),
                            take(jms, qBetween,
                                    "Age BETWEEN 15 AND 20"))
                            .sorted()
                            .toList());
            System.out.println("BETWEEN: " + between);

            // IN: only select String-valued Department.
            sendText(jms, qIn, "finance", "Department", "FINANCE");
            sendText(jms, qIn, "legal", "Department", "LEGAL");
            sendText(jms, qIn, "warehouse", "Department", "WAREHOUSE");

            String in = String.join(", ",
                    Stream.of(
                            take(jms, qIn,
                                    "Department IN ('FINANCE','WAREHOUSE')"),
                            take(jms, qIn,
                                    "Department IN ('FINANCE','WAREHOUSE')"))
                            .sorted()
                            .toList());
            System.out.println("IN: " + in);

            // LIKE: !_ is a literal underscore, % is the suffix.
            sendText(jms, qLike, "literal-underscore",
                    "Code", "ORD_100");
            sendText(jms, qLike, "other",
                    "Code", "ORDX100");

            String like = take(jms, qLike,
                    "Code LIKE 'ORD!_%' ESCAPE '!'");
            System.out.println("LIKE: " + like);

            // IS NULL: one message lacks the GroupTag property.
            jms.convertAndSend(qNull, "missing");
            sendText(jms, qNull, "present",
                    "GroupTag", "G-A");

            String absent = take(jms, qNull,
                    "GroupTag IS NULL");
            String present = take(jms, qNull,
                    "GroupTag IS NOT NULL");
            System.out.println("IS NULL: " + absent);
            System.out.println("IS NOT NULL: " + present);
        };
    }

    private static void sendNumber(
            JmsTemplate jms,
            String queue,
            String body,
            String property,
            int value) {

        jms.convertAndSend(queue, body, message -> {
            message.setIntProperty(property, value);
            return message;
        });
    }

    private static void sendText(
            JmsTemplate jms,
            String queue,
            String body,
            String property,
            String value) {

        jms.convertAndSend(queue, body, message -> {
            message.setStringProperty(property, value);
            return message;
        });
    }

    private static String take(
            JmsTemplate jms,
            String queue,
            String selector) {

        Object body =
                jms.receiveSelectedAndConvert(queue, selector);
        if (!(body instanceof String text)) {
            throw new IllegalStateException(
                    "No matching TextMessage: " + selector);
        }
        return text;
    }
}
~~~

The class above is a complete Java 17 example with `main()`, a `CommandLineRunner` bean, and helper methods. It uses `JmsTemplate` configured by Spring Boot via the Artemis starter, the default `String ↔ TextMessage` converter, `MessagePostProcessor` to attach metadata, and `receiveSelectedAndConvert` to select messages.

### 10.5. Running the program and output

In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

With a properly running broker, valid queue permissions, no competing consumers, and each receive succeeding within the timeout, the output printed by the application itself is:

~~~text
BETWEEN: age-15, age-20
IN: finance, warehouse
LIKE: literal-underscore
IS NULL: missing
IS NOT NULL: present
~~~

Spring Boot and Artemis may print additional logs. To keep the output deterministic, the code sorts the two bodies in `BETWEEN` and `IN` before printing. Non-matching messages (`age-14`, `age-21`, `legal`, `other`) **are not received by the selector-based receives**; they remain as messages in the queue per broker policy and can be received by other consumers.

If a selector returns `null` due to timeout or broker blocking, `take()` throws an exception with the selector string instead of printing a misleading result as if it succeeded. The demo uses UUID queues to avoid stale messages from prior runs. `@JmsListener` is **not yet needed** because the goal is to compare the operators in a clear sequence.

Stop the broker:

~~~bash
docker stop selector-demo-broker
~~~

### 10.6. Experiments changing each operator

**BETWEEN:** change to `Age BETWEEN 14 AND 21`, receiving four messages (adjust the demo to receive four times). Change to `Age BETWEEN 15 AND 19`, leaving only `"age-15"`. If using `Age NOT BETWEEN 15 AND 20`, the two messages outside the range are selected; a missing `Age` still does not match automatically.

**IN:** add a message `Department="FINANCE"` and check whether it matches. Change `Department` to lowercase `"finance"` to observe case sensitivity. Try `Department NOT IN ('FINANCE','WAREHOUSE')` to receive `"legal"`.

**LIKE:** replace `"ORD_100"` with `"ORDX100"`. With pattern `"ORD!_%"`, it does not match; if using `"ORD_%"` (without escape), `"ORDX100"` can match because `_` is a wildcard.

**IS NULL:** add a message with `GroupTag=""` and run the `IS NULL` selector; that message does not match because the property exists. Use `IS NOT NULL` to receive messages with an empty string.

**UNKNOWN:** add a message without `Age`, then test `Age NOT BETWEEN 15 AND 20`. It does not match because of UNKNOWN, whereas `Age IS NULL` matches.

## 11. Combining multiple operators for real-world problems

Example of a consumer handling requests in Vietnam/Singapore, with total amount within a range and selecting only CREATE/UPDATE events:

~~~sql
(EventType IN ('ORDER_CREATED', 'ORDER_UPDATED'))
AND (Region IN ('VN', 'SG'))
AND (AmountMinor BETWEEN 100000 AND 500000)
~~~

The producer must attach:

~~~java
message.setStringProperty("EventType", "ORDER_CREATED");
message.setStringProperty("Region", "VN");
message.setLongProperty("AmountMinor", 250000L);
~~~

If `AmountMinor` is missing, the entire expression is UNKNOWN even when the other two parts are TRUE; the message does not match. Do not mistake this for "broken filtering": the broker simply obeys the JMS properties actually sent.

### 11.1. Routing by prefixed name

~~~sql
(EventType IN ('ORDER_CREATED','ORDER_CANCELLED'))
AND CorrelationKey LIKE 'ORD-%'
~~~

Matches the required events having a `CorrelationKey` formatted as `"ORD-..."`. If `CorrelationKey` is not sent, `LIKE` is UNKNOWN and the message does not match. When bad data needs to be quarantined, use another consumer with selector `CorrelationKey IS NULL`; however, carefully examine interactions with other consumers on the same queue.

### 11.2. Group scanning for missing metadata

~~~sql
(EventType = 'ORDER_CREATED')
AND (Region IS NULL OR CorrelationKey IS NULL)
~~~

This is a contract-checking flow. A selector dedicated to "invalid data" does not replace body validation and cannot classify all schema errors; for example, a body missing `orderId` while headers are intact will not be caught by the selector.

### 11.3. Time ranges in UTC

If the producer writes `CreatedAtEpochMs` as `long` milliseconds, the consumer can select:

~~~sql
CreatedAtEpochMs >= 1793318400000
AND CreatedAtEpochMs < 1793404800000
~~~

The numbers in the expression only illustrate the epoch millisecond format; in real use, compute bounds from the business domain's `Instant`/`ZoneId` and test them. This is a **half-open** interval, usually safer than `BETWEEN` for consecutive time windows.

### 11.4. Does "not in set" mean "in the other set"?

Not always. With `Region NOT IN ('VN','SG')`, a message missing `Region` is not in the set in the sense of a Java null-check, yet in a JMS selector the result is UNKNOWN and does not match. If the business rule wants "other countries and unassigned", you must additionally write `Region IS NULL`.

## 12. Performance, latency, and Queue/Topic semantics

### 12.1. Queue: unmatched messages are not consumed and discarded

With a Queue, the selector determines which messages are eligible for a consumer. Messages that do not match this consumer's selector can still wait for another consumer with matching criteria or a consumer without a selector.

It does not mean every filtered-out message is automatically moved to another queue. A selector **is not a router that moves messages between destinations**: it only governs selection per consumer/subscription.

If there is only one consumer with an overly narrow selector, the queue can accumulate messages nobody selects. Monitor queue depth, message age, group/selector distribution, and branches with no subscribers.

### 12.2. Topic: selectors belong to subscriptions

With a Topic, the selector is attached when the subscription is created. Unmatched messages may not be added to that subscription; other subscriptions can have different selectors and receive matching copies. Interactions among durable subscriptions, selector changes, and cleanup depend on the JMS API/broker, so subscription lifecycles must be managed explicitly.

Do not infer that "topic message did not match selector" means no subscriber received it. It only failed to match one specific subscription.

### 12.3. Avoid overly expensive selectors

Numeric `BETWEEN`/`IN` on clear routing properties can be easier to optimize than evaluating `LIKE` with a leading wildcard, though actual effectiveness depends on how the broker optimizes/indexes selectors. Jakarta Messaging **does not guarantee indexing**, constant cost, or response latency.

Practices:

- Set small, stable, properly typed routing metadata that is frequently queried.
- Prefer equality or `IN` over discrete enums where suitable.
- Avoid `LIKE '%suffix'` on large queues, especially without provider-specific optimization mechanisms.
- Do not create thousands of distinct selectors per user/tenant unless the broker is designed to handle that load.
- Test under load with a realistic message mix, realistic listener/consumer counts, and multiple producers.
- Do not copy the entire JSON body into message properties just to filter; balance metadata/size/PII costs.

### 12.4. When should you separate queues/topics instead of using selectors?

If consumer groups have different lifecycles, QoS, retention, permissions, retry counts, or SLAs, separating queues/topics by domain can be clearer than cramming everything into one queue and filtering. Selectors fit **metadata segmentation** within the same communication model, not a replacement for all topology design.

For example: `payment.commands` and `analytics.events` have completely different processing characteristics. Using one queue plus a selector instead of proper topology can lead to unmanageable backlogs and permissions.

## 13. Selectors and security

A JMS selector **is not an authorization boundary**. Users/tenants are not guaranteed isolation merely because their consumers have selector `Region='VN'`; broker ACLs, credentials, permissions, and resource separation are still required when needed.

### 13.1. Do not concatenate external input directly

If a user passes a `Region` value and you concatenate:

~~~java
String selector = "Region = '" + userInput + "'";
~~~

input containing single quotes or extra conditional clauses can break the expression or alter its meaning. JMS selectors have no standard parameter-binding API equivalent to SQL `PreparedStatement`.

For a **finite enum set**, it is best to check an allowlist:

~~~java
Set<String> allowed = Set.of("VN", "SG", "TH");
if (!allowed.contains(userInput)) {
    throw new IllegalArgumentException("Unsupported region");
}
String selector = "Region = '" + userInput + "'";
~~~

This is a Java 17 snippet (`import java.util.Set`) safe only when `userInput` is restricted to a fixed allowlist as above. For arbitrary Strings, you must escape literals (single quote -> doubled single quote), control length, property names, and expressions; never turn a client-supplied string directly into a selector without validation.

~~~java
static String quoteSelectorString(String value) {
    return "'" + value.replace("'", "''") + "'";
}
~~~

The function above handles only **String literal quoting** and does not automatically ensure safety for property names or `LIKE` patterns. If input goes into `LIKE`, you must also handle `%`/`_` wildcards and `ESCAPE` per contract.

### 13.2. Property names and PII

Do not put card numbers, access tokens, sensitive emails, or personal data into routing properties if broker logs/metrics can record metadata. Use non-sensitive domain labels and grant least-privilege access to consumers. Consider encryption/masking for payloads, adhering to the system's data policies.

## 14. Common errors and how to diagnose them

| Symptom | Possible cause | Check/fix |
| --- | --- | --- |
| `BETWEEN` selector does not match even though JSON body has `AmountMinor` | Property was not attached on the JMS Message; only inside body | Attach `setIntProperty`/`setLongProperty` before send. |
| `AmountMinor BETWEEN` does not match `"2500"` | Property is String, not numeric | Use `setIntProperty` instead of `setStringProperty`. |
| `IN` errors or does not work with a list of numbers | Standard `IN` only accepts string literals | Use `OR` with numeric equality or switch to enum strings. |
| `IN` does not match `"vn"` against `'VN'` | String literal/case differs | Normalize enums on the producer and test. |
| `LIKE 'ORD_%'` matches `ORDX123` too | `_` is a wildcard | Use `LIKE 'ORD!_%' ESCAPE '!'`. |
| `LIKE 'ORD-%'` matches `"ORD-"` | `%` allows the empty string | Add pattern/validation requiring a non-empty suffix. |
| `NOT LIKE` misses messages lacking `Code` | `NOT UNKNOWN` remains `UNKNOWN` | Consider `Code IS NULL OR ...` if policy allows. |
| `IS NULL` does not match `Region=""` | Empty string is still a value | Use `Region = ''` if contract requires accepting empty strings. |
| `Region = NULL` misses messages lacking `Region` | Comparing with NULL returns UNKNOWN | Use `IS NULL`. |
| Multiple `OR` conditions receive messages with wrong `EventType` | Missing parentheses grouping `AND`/`OR` | Write explicitly `(A AND (B OR C))`. |
| `InvalidSelectorException` when creating consumer | Syntax error: quotes, parentheses, keywords | Unit test selectors and verify on a real broker. |
| Listener runs while only queue depth grows | No messages match metadata; wrong property name/type | Inspect message headers/properties and active selector. |
| `JmsTemplate.receiveSelected` returns `null` | Timeout or no matching message | Do not conclude queue is empty; check selector and `receiveTimeout`. |
| Right date type, wrong window | Epoch seconds vs milliseconds, timezone offset | Contract UTC/epochMillis, build bounds with `Instant`. |
| Only one tenant receives messages | One consumer selector too broad/narrow or wrong ACL topology | Audit naming/selectors, security config, and consumer count. |
| Changing `@JmsListener.selector` has no effect | Old container still running with previous selector | Redeploy/recreate subscription/container appropriately. |
| High broker CPU with many consumers using `LIKE` | Expensive/leading-wildcard selector, many variants | Benchmark broker, simplify metadata/topology. |

### 14.1. Step-by-step debugging workflow

1. **Real data:** use the broker console/debug client to inspect properties **and their actual types**, not just the body.
2. **Real selector:** check the expression actually used by the Spring listener/container after configuration resolution, not just source code.
3. **Syntax:** are quotes/parentheses balanced, is `IN` used with string literals, and is `LIKE`/`ESCAPE` correct?
4. **Names:** is the property identifier cased properly, and is any reserved keyword misused?
5. **Null:** is a missing field causing UNKNOWN, and is `IS NULL` needed?
6. **Domain:** is the consumer receiving from a Queue or Topic, and is the subscription right?
7. **Timeout:** how long does `receiveSelected` wait, and was a matching message actually sent during that window?
8. **Transaction:** was the message committed, or did the selector miss because the producer failed to attach properties on send?
9. **Schema error:** are body and JMS metadata inconsistent on `EventType`/`Region`/`Version`?
10. **Operations:** backlog metrics, unconsumed messages, retries, dead-letter, expiry, and listener health.

## 15. Design scenarios worth thinking through

### 15.1. Filtering by amount when two producer versions exist

Producer v1 sets `AmountMinor` as String `"2500"`; producer v2 sets it as `int 2500`. Even though business data is identical, a numeric `BETWEEN` selector only works reliably with v2.

The solution is not trying to write a "self-casting" selector; standardize the contract, version metadata, deploy compatible consumers, or add a new numeric property alongside during migration.

### 15.2. A tenant must not be allowed to read another tenant's messages

A selector `TenantId='A'` can help internal routing, but **it does not replace ACLs**. When data isolation is a security requirement, destination/subscription permissions and broker accounts are the primary control layer. Never allow clients to supply their own selectors to access other data.

### 15.3. Filtering orders containing a specific item

If `ProductSku` only exists inside the JSON body, selectors cannot look it up directly. You can expose `ProductCategory` or `RequiresReview` as a JMS property after producer validation, or design a separate queue/route. The consumer must still validate the body; a routing property is a **projection** from business data, not a replacement for the original contract.

### 15.4. Messages that nobody consumes

A queue contains messages missing `EventType`, while all consumers have `EventType IN (...)` selectors. They will pile up. A dedicated strategy is needed: add a controlled `EventType IS NULL` consumer, quarantine, or producer-side contract validation; monitor backlog and dead-letter policies.

### 15.5. Filtering by a deadline timestamp

If a deadline is stored in a `long DeadlineEpochMs` business property, a selector can compare against **a numeric literal computed when the consumer is created**. However, selectors have no portable `NOW()` function that updates every millisecond. In long-running listeners, clock-dependent business deadlines should be validated in the handler rather than embedding a fixed "now" into a selector expecting it to update itself.

## 16. Production selector checklist

- [ ] Filterable fields are in standard-supported JMS headers/properties, not only in the body.
- [ ] Producer attaches properties with exact types: `int`/`long` for `BETWEEN`, `String` for `IN`/`LIKE`.
- [ ] Property names are valid, non-keyword, stable, and consistently cased.
- [ ] `BETWEEN` is understood as **inclusive**; consider half-open bounds for consecutive time windows.
- [ ] `IN` only uses a string literal list, never subqueries or numeric lists.
- [ ] `LIKE` uses `%` and `_` intentionally; use `ESCAPE` when literal `%` or `_` is needed.
- [ ] Missing properties are explicitly designed; `NOT` does not turn `UNKNOWN` into `TRUE`.
- [ ] `IS NULL`/`IS NOT NULL` are used properly, not confused with JSON `null` or empty strings.
- [ ] Parentheses are present when mixing `AND`/`OR` and `BETWEEN`.
- [ ] No reliance on implicit String-to-number conversion or non-standard SQL functions.
- [ ] Unvalidated/unescaped user input is never concatenated into a selector.
- [ ] `@JmsListener` `containerFactory`, Queue/Topic, and `ConnectionFactory` are properly configured.
- [ ] A finite `receiveTimeout` is set if using `JmsTemplate.receiveSelected`.
- [ ] Integration tests exist against the real broker/provider and real property dataset.
- [ ] Backlog metrics and a handling path for unmatched messages are in place.
- [ ] Selectors are not used as a tenant security mechanism or a replacement for schema validation.

## 17. Self-check questions

**Question 1. Does BETWEEN include both lower and upper bounds?** Yes. `X BETWEEN 10 AND 20` matches 10 and 20.

**Question 2. Does IN accept AmountMinor IN (100,200) per standard JMS?** No. Standard `IN` uses a list of string literals with a String-valued identifier.

**Question 3. Does LIKE 'ORD-%' match 'ORD-'?** Yes, because `%` can match the empty string.

**Question 4. Does LIKE 'AB_' match 'AB'?** No. The `_` requires exactly one character.

**Question 5. How do you include a literal `_` in a pattern?** Choose `ESCAPE`; for example `Code LIKE 'ORD!_%' ESCAPE '!'`.

**Question 6. If Region is missing, is Region <> 'VN' TRUE or UNKNOWN?** UNKNOWN; the selector does not match.

**Question 7. If Region is missing, what is Region IS NULL?** TRUE.

**Question 8. If Region="", what is Region IS NULL?** FALSE, because an empty string is still a provided value.

**Question 9. Can a selector directly read a JSON body to check $.amount?** Not under standard Jakarta Messaging.

**Question 10. Why doesn't String "20" automatically match Age BETWEEN 18 AND 65?** Selectors do not apply getter String->int conversions; the property type must match.

**Question 11. Which outcomes cause a selector to choose a message?** Only TRUE, never FALSE or UNKNOWN.

**Question 12. Does JmsTemplate.receiveSelected returning null mean the queue is empty?** Not necessarily; there may be non-matching messages or a timeout.

**Question 13. Where does @JmsListener(selector=...) create the filter?** The listener container creates the JMS consumer/subscription with the selector; the broker/provider uses metadata to filter message delivery.

**Question 14. If NOT LIKE is used on a missing property, is the message received?** No; `NOT UNKNOWN` remains `UNKNOWN`. To include missing values, check `IS NULL` separately.

**Question 15. Should selector TenantId='tenant-A' be used instead of broker ACLs?** No. Selectors only filter delivery; they do not grant permissions or enforce security isolation.

### Practice exercises

1. Run the demo and verify the exact output of `BETWEEN`/`IN`/`LIKE`/`IS NULL`.
2. Change the two age endpoints to prove `BETWEEN` is inclusive of its bounds.
3. Change `Department` to lowercase and predict whether `IN` will match.
4. Change `Code` from `"ORD_100"` to `"ORDX100"`, comparing `LIKE` with `ESCAPE` vs. without `ESCAPE`.
5. Send a message missing `Age` and compare `Age NOT BETWEEN 15 AND 20` against `Age IS NULL`.
6. Add a sender setting `setStringProperty("Age","20")`, and observe why numeric `BETWEEN` does not match.
7. Write a `@JmsListener` with a selector combining `IN`, `BETWEEN`, and `LIKE`; use Testcontainers Artemis or a test broker to verify.
8. Write a test suite separating TRUE, FALSE, and UNKNOWN for `AND`/`OR` expressions and `NULL`.
9. Configure two consumers with non-overlapping selectors; check queue depth when messages match neither.
10. Build a versioned naming contract for `EventType`, `Region`, `AmountMinor` and test producer/consumer compatibility.
11. Design dedicated handling for `Region IS NULL` instead of defaulting messages to `Region='VN'`.
12. Simulate a user-supplied selector, test single quotes, and demonstrate the need for allowlisting/quoting.

## 18. Official references

- Jakarta Messaging 3.1, section 3.8 Message selection and 3.8.1.2 Null values: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging 3.1 specification document/PDF: https://jakarta.ee/specifications/messaging/3.1/
- Spring Framework, Receiving a Message (JmsTemplate): https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring Framework 6.2 JmsTemplate API, receiveSelected and receiveSelectedAndConvert: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework, Annotation-driven Listener Endpoints (@JmsListener): https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Framework 6.2 JmsListener API, selector attribute: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/annotation/JmsListener.html
- Spring Boot Getting Started, Messaging with JMS: https://spring.io/guides/gs/messaging-jms/
- Apache ActiveMQ Artemis Docker: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
