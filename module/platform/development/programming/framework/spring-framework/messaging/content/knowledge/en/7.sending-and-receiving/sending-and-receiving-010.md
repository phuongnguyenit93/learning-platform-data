# MessagePostProcessor and Enriching Metadata After Conversion

## Learning Objectives

After this lesson, you will be able to:

- Explain what MessagePostProcessor is and where it fits in the message-sending flow.
- Distinguish payload-to-Message conversion from the Message post-processing step.
- Use MessagePostProcessor to add trace ID, event type, source, and other metadata after the converter creates a Message.
- Create a new Message with MessageBuilder while preserving existing payload and headers.
- Understand the ordering among MessageConverter, MessagePostProcessor, and MessageChannel.send.
- Distinguish MessagePostProcessor from MessageBuilder, MessageConverter, and ChannelInterceptor.
- Use a post processor in convertAndSend and a request post processor in convertSendAndReceive.
- Avoid overwriting critical metadata, returning null, or performing heavy work inside the callback.

## 1. Why Do We Need Message Post-Processing?

When sending a Java object, an application often wants a template to convert the payload into a Message and send it to a channel. The converter is responsible for creating the Message from the payload and initial headers. However, some metadata is only known at send time, after the payload has been converted:

- A trace ID or correlation ID generated for the current send call.
- The name of the service or component emitting the message.
- An event type or schema version defined by application convention.
- A tenant ID, locale, or classification metadata needed by the consumer.
- An event emission timestamp or an observability header.

This metadata can be added using MessageBuilder before sending. However, when using a template and convertAndSend, Spring provides a dedicated callback to process the Message after the converter has created it: MessagePostProcessor.

MessagePostProcessor is useful when you want to reuse a shared converter while adding metadata specific to each send call. It keeps two responsibilities distinct: the converter turns the payload into a Message; the post processor adjusts the created Message.

## 2. What Is MessagePostProcessor?

MessagePostProcessor is a functional interface in Spring Framework's org.springframework.messaging.core package. The contract has one method:

~~~java
Message<?> postProcessMessage(Message<?> message);
~~~

The callback receives the created Message and returns:

- A post-processed Message, usually a new Message with adjusted headers or content.
- The input Message itself if no changes are needed.

The callback must not return null. If no changes are made, return the original Message.

Because it is a functional interface, it can be implemented with a lambda:

~~~java
MessagePostProcessor processor = message -> MessageBuilder
        .fromMessage(message)
        .setHeader("traceId", "trace-92")
        .build();
~~~

MessagePostProcessor is not a channel and does not send Messages itself. The template invokes the callback during the send process and then forwards the resulting Message to the destination.

## 3. Position of the Post Processor in the Send Flow

When calling convertAndSend(destination, payload, postProcessor), the conceptual flow is:

~~~mermaid
flowchart LR
    A["Java Payload"]
    B["MessageConverter"]
    C["Initial Message"]
    D["MessagePostProcessor"]
    E["Post-processed Message"]
    F["MessageChannel.send"]
    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
~~~

This ordering is significant:

1. The template receives the Java payload.
2. MessageConverter converts the payload into a Message and creates the converter's required headers.
3. MessagePostProcessor receives the created Message.
4. The callback can add, replace, or remove metadata by building an appropriate Message.
5. The template sends the post-processed Message to the channel.

Because the callback runs after conversion, it can inspect the Message headers and payload prepared by the converter. That is why the API name emphasizes post-processing the Message.

The post processor runs on the execution thread of the template send operation. If the callback performs slow work, the send operation is prolonged as well. By default it does not run on a consumer thread and does not introduce asynchrony on its own.

## 4. Using convertAndSend with MessagePostProcessor

Spring Integration provides MessagingTemplate in the org.springframework.integration.core package. The template supports the overload:

~~~java
template.convertAndSend(channel, payload, postProcessor);
~~~

The template converts the payload into a Message, invokes the post processor, and sends the processed Message to the channel.

Short example:

~~~java
MessagingTemplate template = new MessagingTemplate();

MessagePostProcessor addMetadata = message -> MessageBuilder
        .fromMessage(message)
        .setHeader("eventType", "order.created")
        .setHeader("traceId", "trace-92")
        .setHeader("producer", "checkout")
        .build();

template.convertAndSend(channel, "ORD-92", addMetadata);
~~~

The payload remains ORD-92. The post processor adds the eventType, traceId, and producer headers after the template has converted the payload into a Message.

If you need to send a pre-constructed Message, use send(channel, message). In that case, the application can create a new Message with MessageBuilder before calling send. Overloads accepting MessagePostProcessor belong to conversion operations like convertAndSend; do not assume every call to MessageChannel.send automatically invokes this callback.

## 5. Adding Metadata While Preserving the Existing Message

Message is designed as an immutable envelope. Do not mutate the Message headers map directly. Use MessageBuilder.fromMessage to create a new Message based on the input Message.

Example:

~~~java
Message<?> enriched = MessageBuilder
        .fromMessage(message)
        .setHeader("traceId", "trace-92")
        .setHeader("producer", "checkout")
        .build();
~~~

This approach preserves the payload and existing headers while adding new headers. If you set a header that already exists using setHeader, the old value is replaced with the new value.

Before overwriting, determine who owns that header and follow the application's conventions. Standard framework headers such as ID, timestamp, replyChannel, and errorChannel carry control semantics; do not arbitrarily alter or strip them.

If you want to keep an existing value, check before adding:

~~~java
MessagePostProcessor addTraceIfMissing = message -> {
    if (message.getHeaders().containsKey("traceId")) {
        return message;
    }

    return MessageBuilder
            .fromMessage(message)
            .setHeader("traceId", "trace-92")
            .build();
};
~~~

The example above does not overwrite traceId if the producer or an earlier step already set it. This rule is useful when multiple components enrich metadata.

## 6. Commonly Added Metadata

### 6.1. Trace ID and Correlation ID

Trace IDs help follow a processing flow across multiple components. Correlation IDs link related messages, especially in request-reply or when one business operation emits multiple events.

~~~java
MessagePostProcessor tracing = message -> MessageBuilder
        .fromMessage(message)
        .setHeader("traceId", traceId)
        .setHeader("correlationId", correlationId)
        .build();
~~~

The traceId and correlationId values must be generated or obtained from a trusted application context. If an ID already exists, decide clearly whether to preserve the original ID, generate a new one, or store both by convention.

### 6.2. Event Type and Schema Version

Consumers may need to know which event type the payload represents and under which schema version:

~~~java
MessagePostProcessor eventMetadata = message -> MessageBuilder
        .fromMessage(message)
        .setHeader("eventType", "order.created")
        .setHeader("schemaVersion", 2)
        .build();
~~~

Do not use schemaVersion to replace true DTO or wire schema versioning. A header is only metadata; producer and consumer must still agree on the payload structure.

### 6.3. Source, Tenant, and Locale

Source or tenant metadata can support routing, logging, and data isolation:

~~~java
MessagePostProcessor contextMetadata = message -> MessageBuilder
        .fromMessage(message)
        .setHeader("sourceService", "checkout")
        .setHeader("tenantId", tenantId)
        .setHeader("locale", "vi-VN")
        .build();
~~~

Do not trust a tenant ID or access permissions merely because they appear in headers. The consumer must still authenticate and authorize against trusted data sources. Avoid placing tokens, passwords, or secrets in headers because metadata may be logged or transmitted across other systems.

### 6.4. Timestamp

MessageHeaders includes a system timestamp when the Message is created. If business logic needs an event emission time by its own convention, you can add a separate header such as eventCreatedAt or publishedAt. Clearly define the meaning and time zone of the timestamp value; do not overwrite the framework's standard timestamp.

## 7. Runnable Java 17 Example with QueueChannel

The following example uses Spring Integration's MessagingTemplate and QueueChannel. The template converts a String into a Message, then MessagePostProcessor adds metadata. The consumer pulls the Message and reads both payload and headers.

### 7.1. Maven Configuration

Create the file pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>message-post-processor-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>6.5.10</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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

spring-integration-core provides MessagingTemplate and QueueChannel, and transitively brings in the compatible spring-messaging dependency. If the application uses other integrations, manage dependency versions with a BOM matching the Spring version in use.

### 7.2. Complete Program

Create the file src/main/java/demo/MessagePostProcessorDemo.java:

~~~java
package demo;

import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.core.MessagePostProcessor;
import org.springframework.messaging.support.MessageBuilder;

public class MessagePostProcessorDemo {

    public static void main(String[] args) {
        QueueChannel channel = new QueueChannel(10);

        MessagingTemplate template = new MessagingTemplate();
        template.setSendTimeout(1_000);
        template.setReceiveTimeout(1_000);

        MessagePostProcessor metadataProcessor = message ->
                MessageBuilder.fromMessage(message)
                        .setHeader("eventType", "order.created")
                        .setHeader("traceId", "trace-92")
                        .setHeader("producer", "checkout")
                        .build();

        // Payload is converted into a Message before the callback runs.
        template.convertAndSend(channel, "ORD-92", metadataProcessor);

        Message<?> received = template.receive(channel);

        if (received == null) {
            throw new IllegalStateException("No message received");
        }

        System.out.println("payload=" + received.getPayload());
        System.out.println(
                "eventType=" + received.getHeaders().get("eventType")
        );
        System.out.println(
                "traceId=" + received.getHeaders().get("traceId")
        );
        System.out.println(
                "producer=" + received.getHeaders().get("producer")
        );
    }
}
~~~

Run from the directory containing pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.MessagePostProcessorDemo
~~~

Stdout:

~~~text
payload=ORD-92
eventType=order.created
traceId=trace-92
producer=checkout
~~~

### 7.3. Result Analysis

The producer only passes the payload ORD-92 to convertAndSend. The template uses MessageConverter to create the Message. Then the metadataProcessor callback receives the Message and uses MessageBuilder.fromMessage to add three headers.

QueueChannel receives the post-processed Message. The consumer calls receive and reads both the payload and the headers. This shows the post processor is called before the Message is sent to the channel.

The example does not change the payload, perform network serialization, or create a broker. It simply demonstrates enriching metadata on a Message in an internal send flow.

## 8. Using a Post Processor with Request-Reply

Spring Integration's MessagingTemplate also supports a request post processor in the convertSendAndReceive operation:

~~~java
Object reply = template.convertSendAndReceive(
        requestChannel,
        requestPayload,
        requestMessage -> MessageBuilder
                .fromMessage(requestMessage)
                .setHeader("traceId", traceId)
                .setHeader("requestType", "inventory.check")
                .build()
);
~~~

Here, the template converts requestPayload into a request Message, invokes the request post processor, and sends the request. If a reply arrives within receive timeout, the template converts and returns the reply result per the API called.

The post processor in this overload processes **the request Message before sending**. It is not a callback for post-processing the reply. If you need to adjust the reply, handle it in the consumer, reply handler, or on the receiving side after receiving the reply.

Request-reply still requires a handler or endpoint that sends a response back to the reply channel properly. Adding metadata with a post processor does not automatically create a reply and does not guarantee the consumer completed business processing.

## 9. How MessagePostProcessor Differs from Other Components

| Component | Responsibility | Primary Timing |
|---|---|---|
| MessageConverter | Converts a Java payload into a Message or converts payload on receive | During conversion |
| MessagePostProcessor | Adjusts an already-created Message, typically to add metadata | After Message creation, before sending |
| MessageBuilder | Creates a new Message and sets payload/headers | When the application explicitly constructs a Message |
| ChannelInterceptor | Observes or intercepts send/receive activity at a channel | At the channel boundary |
| MessageHandler | Processes a Message on the consumer side | After the Message is delivered to the handler |

### 9.1. MessageConverter

The converter determines how the payload is represented inside the Message. For example, Strings, byte arrays, or DTOs may require different converters. A post processor does not replace a converter and should not be used to turn a DTO into JSON through ad-hoc string concatenation.

### 9.2. MessageBuilder

MessageBuilder is useful when the application already has a payload or Message and wants to construct an envelope with specific headers. MessagePostProcessor commonly uses MessageBuilder inside its callback to adjust the Message produced by the template.

### 9.3. ChannelInterceptor

ChannelInterceptor applies at the channel boundary and can observe many send/receive operations passing through the channel. MessagePostProcessor is passed to a specific template call, so its scope is usually narrower and more explicit.

If you need to attach metadata per convertAndSend call, use a post processor. If you need cross-cutting logic for every Message passing through a channel, consider ChannelInterceptor.

### 9.4. JMS MessagePostProcessor

Spring JMS has a separate MessagePostProcessor interface for JMS Messages, belonging to the Spring JMS API. It is not the same type as Spring Messaging's org.springframework.messaging.core.MessagePostProcessor. When importing, check the package to avoid confusing two callbacks with the same name that handle two different Message types.

## 10. Rules for Handling Headers and Metadata

When adding metadata, apply these principles:

1. **Use consistent header names:** standardize on camelCase or a naming convention across the whole system.
2. **Do not overwrite system headers:** avoid altering ID, timestamp, replyChannel, or errorChannel unless there is a clear reason and you understand the consequences.
3. **Clearly define header ownership:** a trace ID created by a gateway may need to be preserved end-to-end; downstream services should not arbitrarily generate another value.
4. **Keep data types stable:** if schemaVersion is numeric, every producer should send the same type; do not send Integer sometimes and String other times.
5. **Do not put secrets in headers:** metadata may appear in logs, traces, or transports.
6. **Do not trust metadata for authorization:** validate tenant and access permissions at trusted boundaries.
7. **Return a valid Message:** postProcessMessage must never return null.
8. **Do not change the payload unintentionally:** use fromMessage if you only want to add headers; if replacing the payload, document why and verify data types.
9. **Do not create ambiguous timestamps:** specify UTC, epoch, or an agreed time format.
10. **Do not make callbacks heavy:** avoid database queries, HTTP calls, or waiting on locks inside a post processor if metadata can be prepared beforehand.

## 11. Performance, Thread Safety, and Testability

MessagePostProcessor runs on the template's send path. A callback can execute quickly, such as reading a trace ID from context, creating metadata, and returning a new Message. If the callback calls external services or performs blocking operations, send latency increases.

If a post processor is shared across multiple threads, keep it stateless or ensure shared data is safe under concurrent access. Avoid storing per-request trace IDs in a mutable field of the processor; obtain values from parameters or an appropriate per-call context.

You can unit-test the callback in isolation by creating a sample Message, invoking postProcessMessage, and asserting on payload and headers. Write tests for these cases:

- Header is added when not yet present.
- Header is preserved or replaced according to policy.
- Payload remains unchanged when only adding metadata.
- Standard headers are not accidentally overwritten.
- Callback does not return null.
- Concurrent requests do not mix up each other's metadata.

Simple verification example:

~~~java
Message<String> input = MessageBuilder
        .withPayload("ORD-92")
        .setHeader("eventType", "order.created")
        .build();

Message<?> output = metadataProcessor.postProcessMessage(input);

assert output.getPayload().equals("ORD-92");
assert output.getHeaders().get("traceId").equals("trace-92");
assert output.getHeaders().get("producer").equals("checkout");
~~~

In real projects, use JUnit or your existing testing framework instead of relying only on Java assert, since assert can be disabled if the JVM is not launched with -ea.

## 12. Common Mistakes

1. **Thinking the post processor runs before the converter:** the callback receives the Message after the converter has finished creating it.
2. **Using post processor with every send API:** the callback only runs on overloads accepting MessagePostProcessor; MessageChannel.send does not invoke it automatically.
3. **Returning null:** the contract requires returning the processed Message or the input Message.
4. **Mutating MessageHeaders directly:** the headers map is not a structure for in-place mutation; create a new Message with MessageBuilder.
5. **Overwriting headers unintentionally:** setHeader replaces the existing value; check first if existing metadata must be preserved.
6. **Replacing payload when only wanting to add metadata:** use fromMessage to keep the payload and other headers.
7. **Putting heavy business logic in the callback:** the post processor sits on the send path and can increase latency.
8. **Storing request metadata in a mutable field of the processor:** multiple threads may share the instance and mix metadata across Messages.
9. **Using a converter to do the post processor's job:** the converter handles payload representation; the post processor handles adjusting the created Message.
10. **Confusing ChannelInterceptor with MessagePostProcessor:** one callback attaches to a template call; the other intercepts at the channel boundary.
11. **Confusing Spring Messaging with Spring JMS:** two packages can have interfaces with the same name but different Message types.
12. **Assuming adding a header means it propagates through every broker:** an adapter may support only a subset of metadata or map headers according to protocol rules.

## 13. Self-Check Questions

1. Which package does MessagePostProcessor belong to?
2. What data types does postProcessMessage accept and return?
3. Why is the post processor called after MessageConverter?
4. Which convertAndSend overloads accept a MessagePostProcessor?
5. How do you add traceId while preserving the payload and other headers?
6. What happens when setHeader writes to a key that already exists?
7. Why must postProcessMessage never return null?
8. How does MessagePostProcessor differ from ChannelInterceptor in scope of application?
9. Does the request post processor in convertSendAndReceive process the request or the reply?
10. Why should you avoid HTTP calls or heavy database queries inside the callback?
11. Why should you check the package when encountering an interface named MessagePostProcessor?
12. Which metadata should not be overwritten or placed into headers?

## 14. Conclusion

MessagePostProcessor is Spring Messaging's callback for processing a Message after it has been created, typically after payload conversion by MessageConverter and before the template sends the Message to a channel. It is well suited for adding trace IDs, correlation IDs, event types, sources, or per-send metadata.

When using the callback, build a new Message via MessageBuilder.fromMessage if you only want to add headers; note that setHeader can replace existing values and you must never return null. Distinguish converter, post processor, and channel interceptor clearly so logic is placed in the right layer. Keep callbacks short, concurrency-safe, and never treat metadata as an authentication mechanism.

## Official References

- Spring Framework MessagePostProcessor API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/MessagePostProcessor.html
- Spring Framework MessageSendingOperations API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/MessageSendingOperations.html
- Spring Framework MessageBuilder API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html
- Spring Framework MessageConverter API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConverter.html
- Spring Integration MessagingTemplate reference: https://docs.spring.io/spring-integration/reference/6.5/channel/template.html
- Spring Integration MessagingTemplate API: https://docs.spring.io/spring-integration/api/org/springframework/integration/core/MessagingTemplate.html
