# setHeaderIfAbsent: Adding Default Headers with MessageBuilder

In the **MessageBuilder** chapter of the **SPRING_INTEGRATION_CORE** module, `setHeaderIfAbsent` helps add missing metadata to a message before it enters processing endpoints. This approach is useful when multiple gateways or adapters send data into the same flow: senders are allowed to provide certain options, while the integration flow supplies the required default values.

This lesson focuses on the rule for preserving existing values, API call ordering, how to incorporate this operation into Java DSL, and how to test the behavior. The examples use Spring Integration's `MessageBuilder`, the 6.5 API line, and Java 17 or later. The illustrative tests use JUnit Jupiter 5; your project needs `spring-integration-core` and the corresponding JUnit configuration to run the code.

## 1. The Problem: Adding Defaults While Keeping the Sender's Choice

Suppose an order intake flow uses two custom headers:

- `locale`: the language used when generating notifications, defaulting to `vi-VN`.
- `maxAttempts`: the maximum number of attempts that the business processing component will read, defaulting to the integer `3`.

Orders from the website may already carry `locale=en-US`, whereas orders from an internal job might not have this header yet. The desired rule is:

| Input Message | Header After Adding Defaults |
| --- | --- |
| Missing `locale` | `locale=vi-VN` |
| Already has `locale=en-US` | Keeps `locale=en-US` |
| Already has `maxAttempts=5` | Keeps integer `5` |
| Missing `maxAttempts` | `maxAttempts` is integer `3` |

`maxAttempts` here is an application-defined header name. Adding the header does not configure Spring Integration retry by itself; another component must actively read and apply that value.

This enrichment rule fits a data-preparation step before a transformer, filter, or router. It also allows gateways to share a single flow while still passing request-specific options.

## 2. API and What "Absent" Means

How to call it on a `MessageBuilder<T>`:

```java
builder.setHeaderIfAbsent(String headerName, Object headerValue);
```

The method returns the builder itself to continue chaining calls. It assigns the value when the header name is not yet bound to a value; if a value already exists, it leaves it unchanged. This behavior is described in the [BaseMessageBuilder Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/support/BaseMessageBuilder.html#setHeaderIfAbsent(java.lang.String,java.lang.Object)).

In terms of the decision logic, you can picture it as follows; this is pseudocode, not copied source code:

```text
Read the current value of the header.
If there is no value yet:
    Set the default value.
If a value already exists:
    Keep it unchanged.
```

There is no check on whether a value is valid for business rules. Therefore, for a regular custom header:

| Existing Value | Call with Default `vi-VN` | Result |
| --- | --- | --- |
| No value | `setHeaderIfAbsent("locale", "vi-VN")` | `vi-VN` |
| `en-US` | Same as above | `en-US` |
| Empty string `""` | Same as above | Keeps empty string |
| Whitespace-only string `"   "` | Same as above | Keeps whitespace |
| Number `0` | Same as above | Keeps number `0` |
| Boolean `false` | Same as above | Keeps `false` |

The accessor checks whether the current value is `null`; it does not use "falsy" rules like some other languages. This explains the empty string, `0`, and `false` cases in the table. See [Spring Framework 6.2.11 MessageHeaderAccessor](https://github.com/spring-projects/spring-framework/blob/v6.2.11/spring-messaging/src/main/java/org/springframework/messaging/support/MessageHeaderAccessor.java).

Pass a non-`null` default value. The published API declares `headerValue` as a non-nullable parameter; do not use `null` as a value indicating "header is present." When you want to remove a header, use `removeHeader` or `setHeader` with `null`.

Header names must also be consistent: `locale` and `Locale` are two distinct keys. Using constants in your application avoids accidentally creating two headers with the same intended meaning.

### Choosing the Right MessageBuilder Class

The examples in this lesson use:

```java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;
```

Spring Framework also provides `org.springframework.messaging.support.MessageBuilder` with a method of the same name. When reading code or checking documentation, check the import to confirm which builder is in use; the extended Integration APIs are not completely identical. You can compare with the [Spring Framework MessageBuilder Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html).

## 3. Basic Example: Handling New and Existing Messages

The snippet below builds a message with the sender's own choice, then fills in the missing headers:

```java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

public class HeaderDefaultsExample {

    public static void main(String[] args) {
        Message<String> incoming = MessageBuilder
                .withPayload("ORDER-1001")
                .setHeader("locale", "en-US")
                .setHeader("source", "website")
                .build();

        Message<String> prepared = MessageBuilder
                .fromMessage(incoming)
                .setHeaderIfAbsent("locale", "vi-VN")
                .setHeaderIfAbsent("maxAttempts", 3)
                .build();

        System.out.println(prepared.getPayload());
        System.out.println(prepared.getHeaders().get("locale"));
        System.out.println(prepared.getHeaders().get("maxAttempts"));
        System.out.println(prepared.getHeaders().get("source"));
        System.out.println(incoming.getHeaders().get("maxAttempts"));
    }
}
```

Output:

```text
ORDER-1001
en-US
3
website
null
```

In this example:

1. `fromMessage(incoming)` initializes the builder from the payload and headers of the input message.
2. `locale` is already present, so the choice `en-US` is preserved.
3. `maxAttempts` is missing, so it is added with an `Integer` value.
4. The custom header `source` stays with the message.
5. The input message still does not have `maxAttempts`.

If creating a brand-new message, you can use it directly:

```java
Message<String> created = MessageBuilder
        .withPayload("ORDER-1002")
        .setHeaderIfAbsent("locale", "vi-VN")
        .setHeaderIfAbsent("maxAttempts", 3)
        .build();
```

For an existing message, `withPayload(incoming.getPayload())` only takes the payload and does not automatically carry over the input headers. If the goal is to add metadata while keeping existing context, `fromMessage` expresses that intent accurately. See [MessageBuilder 6.5.4 source code](https://github.com/spring-projects/spring-integration/blob/v6.5.4/spring-integration-core/src/main/java/org/springframework/integration/support/MessageBuilder.java).

## 4. Comparison with `setHeader` and Copy Methods

For writable custom headers, you can choose the API based on intent:

| API | When Header Exists | When Header Is Missing | Suitable Scenario |
| --- | --- | --- | --- |
| `setHeader(name, value)` | Replaces with the passed value | Adds the value | Apply a mandatory value or normalized result |
| `setHeaderIfAbsent(name, value)` | Keeps existing value | Adds the value | Fill in a single default |
| `copyHeaders(map)` | May overwrite with values from the map | Adds corresponding keys | Apply a higher-priority set of values |
| `copyHeadersIfAbsent(map)` | Keeps existing value | Adds missing keys | Fill in a set of defaults |

If the value passed to `setHeader` is `null`, that header is removed. Read-only system headers have their own rules and do not fall under the regular overwrite cases in this table. These methods are documented in the [Spring Integration 6.1.x MessageBuilder Javadoc](https://docs.spring.io/spring-integration/docs/6.1.x/api/org/springframework/integration/support/MessageBuilder.html).

Example with the same input:

```java
Message<String> incoming = MessageBuilder
        .withPayload("ORDER-1003")
        .setHeader("locale", "en-US")
        .build();

Message<String> forced = MessageBuilder.fromMessage(incoming)
        .setHeader("locale", "vi-VN")
        .build();

Message<String> defaulted = MessageBuilder.fromMessage(incoming)
        .setHeaderIfAbsent("locale", "vi-VN")
        .build();

// forced:    locale = vi-VN
// defaulted: locale = en-US
```

Choose `setHeaderIfAbsent` when the sender is allowed to decide. If the flow requires `vi-VN` after a policy-determination step, `setHeader` expresses that rule more clearly.

### Adding Multiple Defaults

```java
import java.util.Map;

Map<String, Object> defaults = Map.of(
        "locale", "vi-VN",
        "maxAttempts", 3,
        "notificationMode", "EMAIL"
);

Message<String> prepared = MessageBuilder
        .fromMessage(incoming)
        .copyHeadersIfAbsent(defaults)
        .build();
```

The default set should contain the headers that this processing step is responsible for managing. For example, if an endpoint only prepares notifications, adding `locale` and `notificationMode` is easier to justify than also deciding aggregator grouping metadata at the same time.

## 5. Call Order Determines Precedence

`setHeaderIfAbsent` checks the state of the builder at the moment it is called. It does not create a rule that protects the header from subsequent overwrite calls.

### The First Default Assigned Is Kept

```java
Message<String> firstDefaultWins = MessageBuilder
        .withPayload("ORDER-1004")
        .setHeaderIfAbsent("locale", "vi-VN")
        .setHeaderIfAbsent("locale", "en-US")
        .build();

// locale = vi-VN
```

### `setHeader` Can Replace an Already-Added Value

```java
Message<String> overridden = MessageBuilder
        .withPayload("ORDER-1005")
        .setHeaderIfAbsent("locale", "vi-VN")
        .setHeader("locale", "ja-JP")
        .build();

// locale = ja-JP
```

### Default Sets Must Be Ordered from Highest to Lowest Priority

Suppose a business unit wants a default of `locale=th-TH`, while the system-wide default is `vi-VN`:

```java
Map<String, Object> businessDefaults = Map.of(
        "locale", "th-TH"
);

Map<String, Object> systemDefaults = Map.of(
        "locale", "vi-VN",
        "maxAttempts", 3
);

Message<String> prepared = MessageBuilder
        .fromMessage(incoming)
        .copyHeadersIfAbsent(businessDefaults)
        .copyHeadersIfAbsent(systemDefaults)
        .build();
```

The precedence in this example is: **input value → business unit default → system default**. If the input is the `incoming` message with `locale=en-US` from earlier, the result remains `en-US`. If the input has no `locale`, the result is `th-TH`.

A `copyHeaders` call appearing later can change this precedence by overwriting custom headers. When the result differs from expectations, inspect the entire chain of operations on the builder.

## 6. Distinguishing a Missing Header from an Invalid Header

Suppose a business rule requires `locale` to be a non-blank string and only accepts a specific set of languages. `setHeaderIfAbsent` only handles missing values; it does not replace that validation step.

```java
Message<String> incoming = MessageBuilder
        .withPayload("ORDER-1006")
        .setHeader("locale", "   ")
        .build();

Message<String> prepared = MessageBuilder.fromMessage(incoming)
        .setHeaderIfAbsent("locale", "vi-VN")
        .build();

// locale is still "   ".
```

The application must choose a policy for invalid values. For example, if a blank string is treated as no language selected, you can normalize it beforehand:

```java
import org.springframework.util.StringUtils;

Object rawLocale = incoming.getHeaders().get("locale");
MessageBuilder<String> builder = MessageBuilder.fromMessage(incoming);

if (rawLocale instanceof String text && !StringUtils.hasText(text)) {
    builder.removeHeader("locale");
}

Message<String> prepared = builder
        .setHeaderIfAbsent("locale", "vi-VN")
        .build();
```

This snippet only handles blank strings. If the value is a number or a language code outside the supported list, the application still needs to decide whether to reject or normalize it. In an integration flow, a filter or validator can be placed before the default-enrichment step to enforce that decision.

### Data Types of Custom Headers

```java
Message<String> incoming = MessageBuilder
        .withPayload("ORDER-1007")
        .setHeader("maxAttempts", "5")
        .build();

Message<String> prepared = MessageBuilder.fromMessage(incoming)
        .setHeaderIfAbsent("maxAttempts", 3)
        .build();

Object actual = prepared.getHeaders().get("maxAttempts");
// actual is still String "5", not converted to Integer.
```

When a consumer expects `Integer`, reading a value that is currently a `String` via `get("maxAttempts", Integer.class)` will not auto-convert and may throw `IllegalArgumentException`. Align the data type contract across gateways, adapters, and consuming endpoints. Some standard headers also have their types checked by the accessor when set, such as `priority` requiring a numeric value; see [IntegrationMessageHeaderAccessor 6.5.4](https://github.com/spring-projects/spring-integration/blob/v6.5.4/spring-integration-core/src/main/java/org/springframework/integration/IntegrationMessageHeaderAccessor.java).

## 7. Do Not Confuse with Lazy Default Computation

In Java, arguments to a method call are evaluated before the method runs:

```java
builder.setHeaderIfAbsent("requestId", createRequestId());
```

`createRequestId()` is still called even if the builder already has `requestId`. `setHeaderIfAbsent` accepts an `Object`; this API does not take a `Supplier` to defer value creation automatically.

If computing the default has a cost or side effects, check first. The example below only invokes the ID generator when the input is missing `requestId`:

```java
import java.util.Objects;
import java.util.function.Supplier;

import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

public final class RequestIdDefaults {

    private RequestIdDefaults() {
    }

    public static <T> Message<T> apply(
            Message<T> input, Supplier<String> generator) {

        MessageBuilder<T> builder = MessageBuilder.fromMessage(input);

        if (input.getHeaders().get("requestId") == null) {
            String generated = Objects.requireNonNull(
                    generator.get(), "default requestId must not be null");
            builder.setHeaderIfAbsent("requestId", generated);
        }

        return builder.build();
    }
}
```

This method applies the missing-value rule for `requestId`; if an empty string is also invalid, an additional check is needed. Passing a `Supplier` directly into `setHeaderIfAbsent` does not instruct the framework to invoke the supplier: it is simply an object stored as the header value.

## 8. Adding the Default-Enrichment Step to Java DSL

You can extract common rules into a small helper method. The illustrative classes in this section are placed in the same application package.

```java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

public final class MessageDefaults {

    private MessageDefaults() {
    }

    public static <T> Message<T> apply(Message<T> input) {
        return MessageBuilder.fromMessage(input)
                .setHeaderIfAbsent("locale", "vi-VN")
                .setHeaderIfAbsent("maxAttempts", 3)
                .build();
    }
}
```

Configure a flow that receives a message via a channel and sends the result to a `QueueChannel`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.transformer.Transformer;

@Configuration
@EnableIntegration
public class OrderDefaultsConfiguration {

    @Bean
    public QueueChannel orderDefaultsOutput() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow orderDefaultsFlow(
            QueueChannel orderDefaultsOutput) {

        Transformer addDefaults = message -> MessageDefaults.apply(message);

        return IntegrationFlow.from("orderDefaultsInput")
                .transform(addDefaults)
                .channel(orderDefaultsOutput)
                .get();
    }
}
```

Here the lambda is typed as `Transformer`, so it receives the full `Message<?>` according to the interface contract. With regular DSL lambda overloads, the input is usually the payload; if using an overload that takes a `Class`, pass `Message.class` when you want to process the entire message. See the guide [DSL Basics: Lambdas and Message](https://docs.spring.io/spring-integration/reference/dsl/java-basics.html).

The flow can be tested manually with a small program:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;

public class OrderDefaultsDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                OrderDefaultsConfiguration.class)) {

            MessageChannel input = context.getBean(
                    "orderDefaultsInput", MessageChannel.class);
            QueueChannel output = context.getBean(
                    "orderDefaultsOutput", QueueChannel.class);

            input.send(MessageBuilder.withPayload("ORDER-1008")
                    .setHeader("locale", "en-US")
                    .build());

            Message<?> result = output.receive(1_000);
            if (result == null) {
                throw new IllegalStateException("No result received");
            }

            System.out.println(result.getHeaders().get("locale"));
            System.out.println(result.getHeaders().get("maxAttempts"));
        }
    }
}
```

The expected business results are `en-US` and `3`. You can insert a router after the default-enrichment step to branch based on `locale`, or place this step before a transformer that generates notification content.

When a transformer returns the entire message, application code is responsible for preparing the headers of the result. Using `fromMessage` in `MessageDefaults` preserves the input context within the scope of copyable headers, instead of creating a message from the payload alone. Propagation and read-only header rules are described in [Spring Integration: Message](https://docs.spring.io/spring-integration/reference/message.html).

### Declarative Approach with Header Enricher

If you only need to add a set of static values, Java DSL offers a direct declarative form:

```java
@Bean
public IntegrationFlow declarativeDefaultsFlow() {
    return IntegrationFlow.from("declarativeDefaultsInput")
            .enrichHeaders(headers -> headers
                    .header("locale", "vi-VN", false)
                    .header("maxAttempts", 3, false))
            .channel("declarativeDefaultsOutput")
            .get();
}
```

This is an alternative configuration option; the application must declare the appropriate output channel and consumer. The third parameter `false` of `header` specifies not to overwrite an existing header. With these two custom headers and non-`null` values, the business outcome matches adding defaults via the builder. Header Enricher also has expression options and `null`-handling rules, so do not assume every configuration of it is identical to a builder call. See [HeaderEnricherSpec 6.5.4](https://github.com/spring-projects/spring-integration/blob/v6.5.4/spring-integration-core/src/main/java/org/springframework/integration/dsl/HeaderEnricherSpec.java).

## 9. Message, Payload, and Builder Lifecycle

Adding headers through the builder does not mean mutating the input message's map directly. Avoid writing:

```java
// Invalid with standard MessageHeaders of an already-built message.
incoming.getHeaders().put("locale", "vi-VN");
```

With standard immutable messages, the operation above throws `UnsupportedOperationException`. The proper workflow is to initialize a builder from the message and obtain the result via `build()`.

Distinguish the message structure from the objects it references. If the payload or a header value is a mutable `List`, `fromMessage` does not automatically deep-copy that list. Mutating the list can still affect any other place holding the same reference. The examples in this lesson use strings and integers to focus on header default rules.

Do not share a single builder across multiple requests or execution threads. The builder holds mutable state while constructing a message; create a separate builder per processing run.

Also do not use reference comparison to conclude whether a processing step succeeded. When there are no changes, the builder may return the original message; the application should verify the payload and the headers belonging to the business contract. This behavior is shown in [BaseMessageBuilder 6.5.4](https://github.com/spring-projects/spring-integration/blob/v6.5.4/spring-integration-core/src/main/java/org/springframework/integration/support/BaseMessageBuilder.java).

### System Headers and Integration Context

`MessageHeaders.ID` and `MessageHeaders.TIMESTAMP` are read-only system headers. Do not use `setHeaderIfAbsent` to try to impose `id` or `timestamp`; if you need a business ID or business timestamp, create dedicated headers such as `requestId` or `businessCreatedAt`.

In flows with a gateway, preserving control headers also helps maintain reply and error-handling context. If you proactively add defaults for `replyChannel` or `errorChannel`, there must be a corresponding destination and a clear understanding of the flow's path; a channel name in a header does not create a consumer on its own.

For an aggregator, the default `correlationId` must reflect the proper grouping key. If child messages of the same order all lack a key and each message is assigned a fresh UUID, they will end up in different groups. Determine the grouping key where the business relationship is known and preserve it as messages pass through default-enrichment steps.

These considerations help you pick the right headers for default policies without stretching `setHeaderIfAbsent` into routing, retry, or aggregation logic.

## 10. Testing the Default-Enrichment Contract

The tests below use the `MessageDefaults` class declared in the Java DSL section. They verify business outcomes without depending on `id`, `timestamp`, or whether the builder allocates a new message object.

```java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class MessageDefaultsTest {

    @Test
    void addsMissingDefaultsAndKeepsInputUnchanged() {
        Message<String> input = MessageBuilder
                .withPayload("ORDER-2001")
                .setHeader("source", "batch")
                .build();

        Message<String> output = MessageDefaults.apply(input);

        assertEquals("ORDER-2001", output.getPayload());
        assertEquals("batch", output.getHeaders().get("source"));
        assertEquals("vi-VN", output.getHeaders().get("locale"));
        assertEquals(Integer.valueOf(3),
                output.getHeaders().get("maxAttempts", Integer.class));
        assertNull(input.getHeaders().get("locale"));
        assertNull(input.getHeaders().get("maxAttempts"));
    }

    @Test
    void preservesValuesChosenBySender() {
        Message<String> input = MessageBuilder
                .withPayload("ORDER-2002")
                .setHeader("locale", "en-US")
                .setHeader("maxAttempts", 5)
                .build();

        Message<String> output = MessageDefaults.apply(input);

        assertEquals("en-US", output.getHeaders().get("locale"));
        assertEquals(Integer.valueOf(5),
                output.getHeaders().get("maxAttempts", Integer.class));
    }

    @Test
    void existingEmptyZeroAndFalseValuesAreStillPresent() {
        for (Object existing : List.of("", "   ", 0, false)) {
            Message<String> input = MessageBuilder
                    .withPayload("ORDER-2003")
                    .setHeader("locale", existing)
                    .build();

            Message<String> output = MessageDefaults.apply(input);

            assertEquals(existing, output.getHeaders().get("locale"));
        }
    }

    @Test
    void doesNotConvertAnExistingCustomHeader() {
        Message<String> input = MessageBuilder
                .withPayload("ORDER-2004")
                .setHeader("maxAttempts", "5")
                .build();

        Message<String> output = MessageDefaults.apply(input);

        assertEquals("5", output.getHeaders().get("maxAttempts"));
        assertThrows(IllegalArgumentException.class,
                () -> output.getHeaders().get("maxAttempts", Integer.class));
    }

    @Test
    void firstDefaultWinsUntilExplicitlyOverridden() {
        MessageBuilder<String> builder = MessageBuilder
                .withPayload("ORDER-2005")
                .setHeaderIfAbsent("locale", "vi-VN")
                .setHeaderIfAbsent("locale", "en-US");

        assertEquals("vi-VN", builder.build().getHeaders().get("locale"));

        builder.setHeader("locale", "ja-JP");

        assertEquals("ja-JP", builder.build().getHeaders().get("locale"));
    }
}
```

Numeric and boolean values in the third test are used intentionally to clarify what "already has a value" means for a custom header. In a real flow, a contract validation step might reject those values because `locale` must be a language string.

At the flow-test level, send at least two messages through the input channel: one missing defaults and one with sender-specified choices. Then verify that downstream endpoints receive the expected headers while required context headers remain intact.

## 11. Common Errors and How to Fix Them

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| Existing header value is replaced | Used `setHeader`, `copyHeaders`, or a later overwrite step | Check operation order and overwrite settings |
| Empty string is not replaced by default | Empty string is still a value | Normalize or validate business rules before the default-enrichment step |
| Reading header with `Integer.class` fails | Sender passed a string, and builder kept it | Align types or add a controlled conversion step |
| Lost source headers or reply context | Created builder from payload without copying headers | Use `fromMessage` when enriching an existing message |
| Default generator runs even when header exists | Java arguments are evaluated before the method call | Only compute the value after checking the header is missing |
| Defaults differ across branches | Enrichment or overwrite steps have inconsistent order | Define a single consistent precedence policy |
| Aggregator groups into wrong buckets | Generated a distinct grouping key per child message | Derive the grouping key from the shared business relationship |

When applying this to an order flow, clearly define which headers the sender can choose, which headers must be normalized, and which endpoints have overwrite authority. Then use `setHeaderIfAbsent` for the defaults to be added in the chosen precedence order.