# MessageConversionException When Data or Content Type Is Invalid

## Objectives

When Spring converts a payload from a transport representation into a Java object, or converts a Java object into a payload for sending, conversion can fail. `MessageConversionException` represents an error raised during Spring Messaging message conversion.

After this lesson, you will be able to:

- Correctly identify `org.springframework.messaging.converter.MessageConversionException`.
- Distinguish actual conversion failures from cases where a converter does not support a data type or MIME type.
- Understand the roles of `MessageHeaders.CONTENT_TYPE`, target class, and payload.
- Read the failed message and root cause from the exception.
- Determine whether a failure occurred in the converter, handler, or transport step.
- Handle errors in synchronous, asynchronous, and Spring Integration flows.
- Distinguish identically named exceptions in Spring Messaging, JMS, and AMQP.
- Write converters with clear error messages and test malformed data.

## 1. What Is MessageConversionException?

The class `org.springframework.messaging.converter.MessageConversionException` is the exception thrown by Spring Messaging `MessageConverter` implementations when payload conversion fails.

Class hierarchy:

~~~text
RuntimeException
  └── NestedRuntimeException
       └── MessagingException
            └── MessageConversionException
~~~

Characteristics:

- It is an unchecked exception because `MessagingException` extends `NestedRuntimeException`, which ultimately extends `RuntimeException`.
- It belongs to package `org.springframework.messaging.converter`.
- It can hold the failing message in the `failedMessage` property.
- It can hold the original exception in `cause`.
- It can be constructed with a descriptive message, with a cause, or with both a failed message and a cause.

Main constructors in Spring Framework 7:

~~~java
new MessageConversionException("Cannot decode payload");

new MessageConversionException(
        "Cannot decode payload",
        originalException
);

new MessageConversionException(
        failedMessage,
        "Invalid payload",
        originalException
);
~~~

When a failed message is present, it can be accessed via:

~~~java
Message<?> failed = exception.getFailedMessage();
Throwable cause = exception.getCause();
Throwable rootCause = exception.getRootCause();
Throwable mostSpecificCause = exception.getMostSpecificCause();
~~~

Not every constructor includes a failed message. For instance, an outbound error occurs while converting an object before a new message is created; in that case, the converter can use a constructor taking only a description and a cause.

## 2. Where Do Conversion Errors Occur?

A conversion flow typically has two directions.

### Inbound: transport payload to Java object

~~~mermaid
flowchart LR
    A["Received payload"] --> B["Spring Message"]
    B --> C["Read contentType"]
    C --> D["Select MessageConverter"]
    D --> E["fromMessage(message, targetClass)"]
    E --> F["Java Object"]
    E --> X["MessageConversionException"]
~~~

For example, the application receives a JSON bytes payload, the header specifies `application/json`, and the converter is asked to create `OrderCreated.class`. If the JSON is truncated, syntactically invalid, or cannot be mapped per converter configuration, parsing may fail.

### Outbound: Java object to transport payload

~~~mermaid
flowchart LR
    A["Java Object"] --> B["toMessage(payload, headers)"]
    B --> C["Select format and serialize"]
    C --> D["Spring Message"]
    D --> E["Adapter / transport"]
    C --> X["MessageConversionException"]
~~~

For example, the application tries to send an object, but the converter cannot serialize a field or data type. The error can appear before the message is ever sent to a broker.

Converters do not send messages over the network themselves. `MessageConversionException` concerns conversion; broker connection errors, access permissions, timeouts, or delivery failures belong to other error classes.

## 3. Distinguishing null from MessageConversionException

This is an essential distinction when reading the API.

The `MessageConverter` contract specifies:

- `fromMessage(message, targetClass)` returns an object if conversion succeeds.
- `toMessage(payload, headers)` returns a message if conversion succeeds.
- If the converter does not support the media type, payload type, or cannot accept the conversion per contract, it should return `null`.

Thus, not every situation a converter cannot handle automatically produces a `MessageConversionException`.

| Situation | Typical outcome |
|---|---|
| Converter does not support `application/xml` | Returns `null` so another converter can be tried. |
| Target class is not among types supported by the converter | Returns `null`. |
| Content type mismatches when strict matching is enabled | Returns `null`. |
| JSON is routed to the right converter, but JSON syntax is corrupted | Converter may throw `MessageConversionException` with the parser error as cause. |
| Payload is text while converter expects a byte array | May return `null` or throw an exception depending on implementation and call path. |
| Custom converter accepts the right format, but data violates rules | Should throw `MessageConversionException` describing the data error. |

Distinguish three states:

1. **Declined to handle:** the converter returns `null`.
2. **Conversion failed:** the converter accepted handling, but the data could not be converted; may throw `MessageConversionException`.
3. **No matching converter found:** the composite or calling layer may report an error because no converter could be found. The specific exception depends on the orchestrating component.

If the application uses `CompositeMessageConverter`, a `null` value typically allows trying the next converter. An exception thrown by a converter usually fails the current process rather than being treated as a gentle decline.

## 4. Invalid Content Type and Unsupported MIME Types

`MessageHeaders.CONTENT_TYPE` describes the payload format. Examples:

| Content type | Format |
|---|---|
| `application/json` | JSON |
| `text/plain` | Plain text |
| `application/octet-stream` | Binary data |
| `application/xml` | XML |

Converters extending `AbstractMessageConverter` typically check two conditions before converting:

- Whether the target class or payload class is among the types supported by the converter.
- Whether the content type matches a MIME type supported by the converter.

Strict content type matching can be configured:

~~~java
converter.setStrictContentTypeMatch(true);
~~~

When strict matching is enabled, the converter must resolve a compatible content type. If the header is missing or the MIME type mismatches, the converter may return `null` because it does not accept that message.

Distinguish:

- **Valid MIME type, but unsupported:** the converter declines the message; usually returns `null`.
- **Missing content type:** the outcome depends on the resolver and strict matching.
- **Syntactically invalid MIME type:** an error may occur during MIME type parsing itself, from the resolver or parser. Do not assume that exception is always `MessageConversionException`.
- **Valid MIME type, but payload is in the wrong format:** the converter may begin parsing and then throw `MessageConversionException`.

Content type must reflect the actual bytes. Setting `application/json` on a non-JSON string will not turn that string into valid JSON.

## 5. Common Root Causes

### Syntactically invalid payload

Example of invalid JSON:

~~~json
{
  "orderId": "ORD-42",
  "total": 250000,
}
~~~

A trailing comma is invalid in standard JSON. A JSON converter can throw an exception when the parser reads the payload.

### Payload does not match target class

The consumer expects `OrderCreated.class`, yet the actual payload contains a different data type or structure. For instance, the consumer expects an object with a String `orderId` field, whereas the transmitted data contains a value whose structure cannot be mapped under the active configuration.

Not every schema difference causes an exception: some mappers can ignore unknown fields or assign default values. Behavior depends on the mapper and configuration.

### Wrong charset or encoding

The producer sends UTF-8, while the consumer decodes with another charset. Accented or non-ASCII characters can become garbled, leading to parse failures or corrupted content.

Standardize the charset on both sides and declare content type accurately, such as `text/plain;charset=UTF-8`.

### Wrong payload type

The converter expects `byte[]` but receives an unsupported Java object, or expects String but receives another object. If the converter does not accept that type, it may return `null`; if a custom converter accepted it for processing yet cannot interpret it, it may throw an exception.

### Incompatible schema or data version

The producer adds fields, renames fields, changes data types, or changes schema versions. Older consumers may not understand the new data, depending on the serializer/deserializer compatibility policy.

### Incorrect headers or metadata

Content type, type headers, charset, or metadata used to determine the target class may not match the payload. Never blindly trust type headers coming from external messages; enforce allowed-type allowlists and mapping rules.

## 6. Exception Structure and Reading Root Causes

Example of an exception with a failed message and cause:

~~~java
throw new MessageConversionException(
        message,
        "Expected payload format orderId=<id>",
        new IllegalArgumentException("Missing order id")
);
~~~

Details to inspect:

| Member | Meaning |
|---|---|
| `getMessage()` | Error description provided by the converter or calling layer. |
| `getFailedMessage()` | The message that caused the failure, if the exception was constructed with it. |
| `getCause()` | Direct wrapped cause, such as a parser exception. |
| `getRootCause()` | Deepest cause in the cause chain. |
| `getMostSpecificCause()` | Most specific identifiable cause. |
| Stack trace | Exact location in the converter, mapper, or adapter where the error originated. |

Useful logging example:

~~~java
catch (MessageConversionException ex) {
    Message<?> failed = ex.getFailedMessage();

    log.error(
            "Message conversion failed: messageId={}, contentType={}, payloadType={}, reason={}",
            failed != null ? failed.getHeaders().getId() : null,
            failed != null ? failed.getHeaders().get(MessageHeaders.CONTENT_TYPE) : null,
            failed != null ? failed.getPayload().getClass().getName() : null,
            ex.getMessage(),
            ex
    );

    throw ex;
}
~~~

This snippet illustrates how to gather metadata. Ensure the payload is non-null before calling `getClass()` if your application's message contract permits null payloads. Do not log full payloads or all headers if they may contain tokens, credentials, or personal data.

## 7. Distinguishing from Other Messaging Exceptions

Do not catch every messaging error under a single exception. The classes below represent different stages:

| Exception | Meaning |
|---|---|
| `MessagingException` | Base class for errors related to Spring Messaging. |
| `MessageConversionException` | Converter could not convert the payload for the format/type it accepted. |
| `MessageHandlingException` | Handler could not process the message or handler business logic failed. |
| `MessageDeliveryException` | Message could not be delivered to the requested channel/destination. |
| `MethodArgumentResolutionException` | Could not resolve/bind a handler method parameter. |
| `InvalidMimeTypeException` | MIME type had invalid syntax when parsed; this is not another name for MessageConversionException. |

An example to distinguish them:

- Corrupted JSON during converter parsing: conversion error.
- JSON parses into an object successfully, but data violates ordering rules: handler validation/business error.
- Channel cannot find a target or cannot dispatch: delivery/routing error.
- Handler method cannot bind parameters per declaration: argument resolution error.

Identifying the exact stage helps fix the real root cause and avoid unnecessary retries.

## 8. Same Exception Name in JMS and AMQP

Across the Spring ecosystem, several classes share the name `MessageConversionException`, but their packages and hierarchies differ.

| Module | Fully qualified class | Base class |
|---|---|---|
| Spring Messaging | `org.springframework.messaging.converter.MessageConversionException` | `MessagingException` |
| Spring JMS | `org.springframework.jms.support.converter.MessageConversionException` | `JmsException` |
| Spring AMQP | `org.springframework.amqp.support.converter.MessageConversionException` | `AmqpException` |

Do not mix up imports. Wildcard imports across multiple packages can cause class name collisions, compilation errors, or catching the wrong exception type.

Spring AMQP also describes conversion exceptions as client-side errors when a converter cannot convert an object/message; the error itself is not a protocol error or broker failure. JMS and AMQP have their own converters, listener containers, and acknowledgement mechanisms.

In flows with adapters, an exception from a protocol converter may be wrapped or turned into an error message at the Integration layer. Inspect the root cause and actual class in the stack trace rather than looking only at the outermost exception name.

## 9. Error Handling in Spring Integration

How an exception is surfaced depends on whether the flow executes synchronously or asynchronously.

### Synchronous flow with DirectChannel

With `DirectChannel`, the handler usually runs on the thread calling send. If a converter or handler throws an exception in this call stack, the exception can propagate back to the sender.

~~~text
Producer
   |
   v
DirectChannel
   |
   v
Converter / Handler
   |
   +---- success ---> continue flow
   |
   +---- exception ---> caller receives exception
~~~

This behavior closely resembles a normal Java method call.

### Asynchronous flow

With `ExecutorChannel`, queues/pollers, or task executors, the sender may have already moved on before the handler finishes. Normal exceptions cannot propagate back to the sender across a call stack that has already unwound.

Spring Integration supports converting errors into an `ErrorMessage` and sending it to:

1. The `errorChannel` specified in the `MessageHeaders.ERROR_CHANNEL` header, if present.
2. The global `errorChannel` if no specific channel is set.

This applies to tasks managed by Spring Integration under the corresponding async mechanism. Do not assume every exception on any thread automatically appears on the error channel.

### Gateway

A gateway can receive downstream errors and by default rethrows them to the caller. An `error-channel` can be configured to route exceptions into an error-handling flow or produce an error response per the application contract.

If the error flow consumes the error and returns a normal result, the caller may receive the transformed response instead of the original exception. Clarify whether a conversion failure must halt the workflow or can be turned into a business response.

## 10. Conversion Errors When Receiving Messages from RabbitMQ

When using Spring Integration AMQP inbound adapters/gateways, messages from RabbitMQ are converted to Spring Messaging `Message<?>` via a converter.

According to Spring Integration 7.1.1 documentation:

- If there is no error channel, conversion errors are thrown back to the listener container for the error handler to process.
- The default error handler treats conversion errors as fatal; the message may be rejected and routed to a dead-letter exchange if the queue is configured for it.
- If an error channel is configured, the `ErrorMessage` payload may be `ListenerExecutionFailedException`, carrying the failed message and cause.
- With acknowledge mode AUTO, if the error flow consumes the error without rethrowing an exception, the original message may be acknowledged.
- If the error flow throws an exception, the listener container and error handler decide whether to requeue.
- With acknowledge mode MANUAL, the error context may contain the channel and delivery tag so the flow can decide ack/nack/reject.

Do not assume every conversion error is automatically retried or automatically sent to a dead-letter queue. The outcome depends on acknowledge mode, error handler, error channel, queue/DLX, and broker configuration.

## 11. Diagnostic Procedure

When encountering `MessageConversionException`, check in order:

1. **Identify the full class.** Inspect the package to see whether it is from Spring Messaging, JMS, or AMQP.
2. **Identify the conversion direction.** Did the failure happen in `fromMessage` or `toMessage`?
3. **Check content type.** Is the MIME type valid and supported by the converter? Is charset present?
4. **Check target class.** What type does the handler request? Does the converter support it?
5. **Check payload runtime type.** Is the actual payload a String, byte array, or object?
6. **Inspect bytes/content.** Is it truncated, wrongly encoded, missing fields, or structurally invalid?
7. **Read cause/root cause.** Look for parser exceptions, charset decoder exceptions, reflection/binding errors, or custom validation errors in the converter.
8. **Check converter selection.** Are multiple converters registered? Did composite ordering let a general converter claim the message first?
9. **Check adapters and header mappers.** Were content type, native headers, or type metadata altered across the transport?
10. **Check retry/acknowledgement.** Is the error permanently bad data or a transient infrastructure fault?

Never fix the issue by catching the exception and silently returning `null`. Doing so can drop messages or allow the flow to proceed with incomplete data.

## 12. Runnable Java 17+ Example: Custom Converter Throwing MessageConversionException

The following example creates a converter that accepts only `text/plain` and target class `OrderData`. The payload must follow the format `orderId=<id>`. If the data is malformed, the converter throws `MessageConversionException` preserving the failed message and cause.

A message with an unsupported MIME type is declined by the converter returning `null`, clearly illustrating the difference between “declined to handle” and “accepted but data invalid”.

Project structure:

~~~text
message-conversion-error-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          MessageConversionErrorDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>message-conversion-error-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>7.0.10</spring-framework.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### MessageConversionErrorDemo.java

~~~java
package demo;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.AbstractMessageConverter;
import org.springframework.messaging.converter.MessageConversionException;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

public class MessageConversionErrorDemo {

    public record OrderData(String orderId) {
    }

    static final class OrderTextConverter extends AbstractMessageConverter {

        private static final String PREFIX = "orderId=";

        OrderTextConverter() {
            super(MimeTypeUtils.TEXT_PLAIN);
            setStrictContentTypeMatch(true);
        }

        @Override
        protected boolean supports(Class<?> clazz) {
            return OrderData.class == clazz;
        }

        @Override
        protected Object convertFromInternal(
                Message<?> message,
                Class<?> targetClass,
                Object conversionHint) {

            Object payload = message.getPayload();

            if (!(payload instanceof String text)) {
                throw new MessageConversionException(
                        message,
                        "Expected a String payload",
                        new IllegalArgumentException("Payload must be text")
                );
            }

            if (!text.startsWith(PREFIX) || text.length() == PREFIX.length()) {
                throw new MessageConversionException(
                        message,
                        "Expected payload format orderId=<id>",
                        new IllegalArgumentException("Missing or invalid order id")
                );
            }

            return new OrderData(text.substring(PREFIX.length()));
        }
    }

    public static void main(String[] args) {
        OrderTextConverter converter = new OrderTextConverter();

        Message<String> malformed = MessageBuilder
                .withPayload("not-an-order")
                .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
                .build();

        try {
            converter.fromMessage(malformed, OrderData.class);
        }
        catch (MessageConversionException ex) {
            System.out.println("exception=" + ex.getClass().getSimpleName());
            System.out.println("failedMessagePresent="
                    + (ex.getFailedMessage() != null));
            System.out.println("cause=" + ex.getCause().getClass().getSimpleName());
        }

        Message<String> unsupportedContentType = MessageBuilder
                .withPayload("orderId=ORD-42")
                .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
                .build();

        Object result = converter.fromMessage(
                unsupportedContentType,
                OrderData.class
        );

        System.out.println("unsupportedContentTypeResult=" + result);
    }
}
~~~

Run from the project directory with Java 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MessageConversionErrorDemo
~~~

Stdout output:

~~~text
exception=MessageConversionException
failedMessagePresent=true
cause=IllegalArgumentException
unsupportedContentTypeResult=null
~~~

Explanation:

1. The converter declares support for `text/plain` and accepts only target class `OrderData`.
2. `setStrictContentTypeMatch(true)` requires the content type to match the declared MIME type.
3. The first message has a valid content type, but the payload does not match the `orderId=<id>` format.
4. The converter accepted the message and intentionally threw `MessageConversionException`.
5. The exception retains the failed message and `IllegalArgumentException` as its cause.
6. The second message has `application/json`, which is not in the supported MIME types. The converter declines handling and returns `null`, without throwing an exception in this case.

This is a custom converter demonstrating the rule. Real JSON converters use their own parser/mapper and may wrap parser errors into `MessageConversionException` depending on the implementation.

## 13. Testing and Prevention

Include dedicated tests for each data category:

- Valid payload with valid content type.
- Syntactically invalid payload with valid content type.
- Syntactically valid payload with incompatible target class.
- Supported content type with wrong charset.
- Valid content type that the converter does not support.
- Missing content type when strict matching is enabled.
- Untrusted headers or type metadata.
- Payload exceeding size limits.
- Old and new schemas during rolling deployments.

A test should verify both the outcome and the exception context:

- Is it the right exception type?
- Is the failed message attached?
- Does the cause preserve the parser/decoder error?
- Is error information sufficient to identify the converter and target class?
- Is the message retried endlessly or acknowledged improperly?

### Handling rules by error type

| Error type | Handling approach |
|---|---|
| Malformed data, unfixable by retry | Reject or route to dead-letter/quarantine; preserve metadata for investigation. |
| Incompatible schema version | Fix producer/consumer contract or implement migration/compatibility. |
| Wrong content type | Fix producer/header mapper; do not change target class to mask the error. |
| Wrong charset | Synchronize encoding and content type across both ends. |
| Converter does not support format | Register the appropriate converter or adjust the agreed format. |
| Transient infrastructure error in downstream handler | Retry with limits per policy; do not treat permanent parse errors as transient. |

Never retry a message with a malformed payload indefinitely. Each retry receives the same bytes and hits the same failure, while potentially clogging queues or inflating log volume. If using an error channel, define clearly whether the error flow will rethrow, reject, ack, or move the message to an error store.

## 14. Pre-Production Checklist

- [ ] Use the right class `org.springframework.messaging.converter.MessageConversionException` when working with Spring Messaging.
- [ ] Identify whether the converter is invoked on the inbound or outbound side.
- [ ] Distinguish `null` (converter declined) from exceptions (conversion failed).
- [ ] Align content type, charset, and payload format.
- [ ] Ensure target class and schema are compatible with the producer.
- [ ] Preserve root cause in exceptions.
- [ ] Retain failed message when appropriate for investigation.
- [ ] Log message ID, content type, payload type, and converter; do not log secrets or sensitive raw payloads.
- [ ] Configure error channels or gateway error flows properly for sync/async processing.
- [ ] Test acknowledge, retry, requeue, and dead-letter policies.
- [ ] Ensure permanent conversion errors are not retried infinitely.
- [ ] Include tests with malformed payloads, wrong content types, and old/new schemas.

## Key Takeaways

- Spring Messaging's `MessageConversionException` lives in package `org.springframework.messaging.converter` and extends `MessagingException`.
- The exception may carry a failed message and cause; use them to locate the payload and root cause.
- A converter that does not support a MIME type or data type normally returns `null` per the `MessageConverter` contract.
- A malformed payload after a converter accepts handling can cause the converter to throw `MessageConversionException`.
- A wrong content type does not always produce this exception; strict matching can cause the converter to return `null`.
- Conversion errors differ from handler, delivery, routing, or broker connection errors.
- Spring Integration handles errors differently between sync and async flows; AMQP also depends on listener containers and acknowledgement modes.
- Never retry permanently malformed data infinitely; fix the producer/schema or route failing messages to quarantine/DLQ.

## Official Documentation

- [Spring Framework Javadoc: MessageConversionException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConversionException.html)
- [Spring Framework Javadoc: MessagingException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessagingException.html)
- [Spring Framework Javadoc: MessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConverter.html)
- [Spring Framework Javadoc: AbstractMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/AbstractMessageConverter.html)
- [Spring Integration Reference: Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference: Inbound AMQP Message Conversion](https://docs.spring.io/spring-integration/reference/amqp/conversion-inbound.html)
- [Spring JMS Javadoc: MessageConversionException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/converter/MessageConversionException.html)
- [Spring AMQP Javadoc: MessageConversionException](https://docs.spring.io/spring-amqp/docs/current/api/org/springframework/amqp/support/converter/MessageConversionException.html)
