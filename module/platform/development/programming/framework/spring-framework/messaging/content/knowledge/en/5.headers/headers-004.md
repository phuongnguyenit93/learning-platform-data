# NativeMessageHeaderAccessor and External Protocol Headers

## 1. Objectives

A message in Spring has a payload and a set of headers describing the message. When a message traverses an external protocol such as STOMP or JMS, in addition to metadata used for Spring's internal processing, the message also carries headers belonging to that protocol itself. Spring needs to retain these headers so it can read, process, and forward them when encoding the message back out to the protocol.

NativeMessageHeaderAccessor is the base class for that scenario. It extends MessageHeaderAccessor and separately manages headers coming from external sources. In applications, we typically use a protocol-specific subclass, such as StompHeaderAccessor or JmsMessageHeaderAccessor, rather than instantiating NativeMessageHeaderAccessor directly.

After this lesson, readers will be able to:

- Distinguish standard Spring headers from native headers of an external protocol.
- Explain the native header storage structure and why Spring separates them from processing headers.
- Read, replace, add, and remove native headers using the proper API.
- Use StompHeaderAccessor to create and read messages carrying STOMP headers.
- Understand how protocol headers are mapped to common headers such as destination and content type.
- Modify headers of an existing message without attempting to mutate immutable MessageHeaders directly.
- Avoid losing metadata, mistakenly trusting external data, or placing sensitive information in headers.

## 2. Headers in a Spring Message

A Spring Message has two parts:

- **Payload** is the primary data, such as an Order object, a JSON string, or a byte array.
- **Headers** are metadata describing the message, such as id, timestamp, content type, destination, correlation id, or protocol information.

The MessageHeaders type is a readable Map. The map itself is designed to be immutable after the message is created; you should not call put or remove directly on message.getHeaders(). To modify headers, use MessageHeaderAccessor or an appropriate subclass and create a new message.

Not all headers serve the same purpose. They can be divided into two groups:

| Group | Purpose | Examples |
|---|---|---|
| Spring processing headers | Serve internal Spring processing, routing, or coordination | id, timestamp, contentType, simpDestination, simpSessionId |
| Native protocol headers | Preserve header names and values in the format of the source/target protocol | destination, receipt, subscription, x-trace-id in STOMP |

The name “native” here means the original header of the external protocol or message source. It does not mean operating system headers or special JVM data.

A header can be mapped to a common Spring property while simultaneously being represented in the native header map. For instance, in STOMP, destination and content-type are protocol headers; Spring also provides common accessors so applications can read destination and content type without manually parsing STOMP strings.

## 3. How Does NativeMessageHeaderAccessor Store Data?

NativeMessageHeaderAccessor extends MessageHeaderAccessor. External headers are stored separately in a sub-map under the key NativeMessageHeaderAccessor.NATIVE_HEADERS.

The logical structure can be visualized as follows:

~~~text
Message
├── payload
└── MessageHeaders
    ├── id
    ├── timestamp
    ├── contentType
    ├── simpDestination
    ├── simpSessionId
    └── nativeHeaders
        ├── destination -> ["/app/orders"]
        ├── content-type -> ["application/json"]
        └── x-trace-id -> ["trace-123"]
~~~

The native header map has type Map<String, List<String>>. Header names are Strings and each name can map to a list of values. This multi-valued structure lets Spring represent protocol sources that allow repeated or multi-valued headers. However, whether a header can appear multiple times and what those values mean depend on the protocol specification. Do not assume every protocol handles duplicate headers identically.

Key points:

- Generic Spring headers can hold Objects; native headers are represented as Strings.
- Native headers are kept in a separate area, avoiding mixing protocol metadata with internal orchestration metadata.
- NativeMessageHeaderAccessor has protected constructors and is designed to be used indirectly via protocol subclasses.
- The getNativeHeaders() method is protected so subclasses can access the internal map.
- The toNativeHeaderMap() method returns a copy of the native header map, not the internal map for direct modification.

Commonly encountered related classes:

| Class | Role |
|---|---|
| MessageHeaderAccessor | Reads and modifies general Spring headers |
| NativeMessageHeaderAccessor | Adds storage for native headers |
| SimpMessageHeaderAccessor | Provides common headers for simple messaging protocols such as destination, message type, session |
| StompHeaderAccessor | Maps and manages STOMP headers |
| JmsMessageHeaderAccessor | Accesses JMS metadata through Spring's abstraction |

For WebSocket/STOMP, the inheritance hierarchy is StompHeaderAccessor → SimpMessageHeaderAccessor → NativeMessageHeaderAccessor → MessageHeaderAccessor. Therefore, StompHeaderAccessor has both general Spring messaging APIs and the ability to read/write STOMP native headers.

## 4. Main APIs of NativeMessageHeaderAccessor

| API | Meaning |
|---|---|
| containsNativeHeader(name) | Checks whether a native header with that name exists |
| getNativeHeader(name) | Gets the entire List<String> of values for the header; returns null if absent |
| getFirstNativeHeader(name) | Gets the first value; returns null if absent |
| setNativeHeader(name, value) | Sets a single new value, replacing any old values for the same name |
| addNativeHeader(name, value) | Appends a value to the current list |
| addNativeHeaders(headers) | Adds native headers from a MultiValueMap |
| removeNativeHeader(name) | Removes the header and returns its previous values |
| toNativeHeaderMap() | Returns a copy of Map<String, List<String>> |
| copyHeaders(map) | Copies general headers; if map contains `NativeMessageHeaderAccessor.NATIVE_HEADERS`, copies native header values into the accessor and replaces native values with the same name |
| copyHeadersIfAbsent(map) | Copies general headers if the key is absent; the native header map is only populated when the accessor has no native map yet, without merging individual missing native keys |

Note: `NativeMessageHeaderAccessor` overrides these two methods to handle the `NATIVE_HEADERS` key specially. `copyHeaders` loads native headers from the map and overwrites native values with matching names. `copyHeadersIfAbsent` only loads the entire native map when the accessor does not yet have a native map; it does not merge individual missing native keys. This rule differs from a simple reading of the general `MessageHeaderAccessor` description.

Example operations on an accessor:

~~~java
accessor.setNativeHeader("x-trace-id", "trace-123");
accessor.addNativeHeader("x-label", "priority");

String traceId = accessor.getFirstNativeHeader("x-trace-id");
List<String> labels = accessor.getNativeHeader("x-label");

boolean hasReceipt = accessor.containsNativeHeader("receipt");
List<String> removed = accessor.removeNativeHeader("x-obsolete");
~~~

setNativeHeader replaces old values. addNativeHeader appends a value to the list. Use multiple values only when the protocol and adapter permit it; if the protocol specifies a single value or defines a rule for picking the first value, follow that rule.

Do not take the map from toNativeHeaderMap() and expect modifying that map to update the accessor. It is a copy for reading, inspection, or conversion. To modify the managed data, call set/add/remove methods on the accessor while it is still mutable.

## 5. Distinguishing setHeader and setNativeHeader

This is the easiest point of confusion when working with external protocols.

- setHeader(name, value) sets a general header at the MessageHeaders level. This header serves the application or the Spring pipeline.
- setNativeHeader(name, value) puts a header into the nativeHeaders area so the protocol integration layer can use it when converting messages.

Example:

~~~java
accessor.setHeader("internalAuditId", "audit-42");
accessor.setNativeHeader("x-trace-id", "trace-123");
~~~

internalAuditId is internal metadata. It does not automatically become a header on the STOMP wire. x-trace-id is placed in the native area so the STOMP handling layer can translate it into a protocol header, if the adapter/endpoint permits that header.

Do not put all data into native headers just to transmit it. Data for internal use such as a Principal object, channel, or processing state should stay in appropriate general headers. Conversely, if you need to preserve an original protocol header across a processing step and forward it, use native headers or the protocol's specialized API.

## 6. STOMP as a Typical Example

STOMP is a frame-based messaging protocol. A frame typically consists of a command, header lines, a blank line, a body, and a frame-terminating character.

Example SEND frame:

~~~text
SEND
destination:/app/orders
content-type:application/json
x-trace-id:trace-123

{"orderId":42}
~~~

In Spring, a STOMP frame is converted into a Message<?>. StompHeaderAccessor handles reading and creating STOMP headers.

When reading a frame:

- Original STOMP headers are stored in the native header sub-map.
- Several standard headers are mapped into Spring processing headers.
- Applications can use getDestination(), getContentType(), or getSessionId() instead of reading the native map manually for supported properties.
- Custom headers like x-trace-id can be read via getFirstNativeHeader("x-trace-id").

When creating an outbound message:

- setDestination() updates both Spring's common destination and STOMP's native destination.
- setContentType() updates the common content type and the corresponding native value.
- setNativeHeader() is used for custom STOMP headers.
- StompHeaderAccessor manages STOMP commands and frame preparation steps for client or server direction as needed.

Not every header in MessageHeaders is automatically sent onto a STOMP frame. Conversion is performed by the accessor and transport layer according to the protocol's mapping rules.

## 7. Java 17 Example: Creating and Reading Native STOMP Headers

The following example creates a Spring message with a SEND command, a destination, and a custom header. Then the program wraps the message with StompHeaderAccessor to read the values back. The example only exercises the in-memory abstraction without starting a WebSocket server or STOMP broker.

### 7.1. Project Structure

~~~text
native-header-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── NativeHeadersDemo.java
~~~

### 7.2. Maven Dependencies

Create pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>native-header-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.2.2</version>
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

spring-messaging contains Message, MessageHeaders, MessageBuilder, and the accessors. Maven will automatically download the required transitive dependencies.

### 7.3. Program

Create src/main/java/com/example/NativeHeadersDemo.java:

~~~java
package com.example;

import org.springframework.messaging.Message;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.MessageBuilder;

public class NativeHeadersDemo {

    public static void main(String[] args) {
        StompHeaderAccessor outgoing =
            StompHeaderAccessor.create(StompCommand.SEND);

        outgoing.setDestination("/app/orders");
        outgoing.setNativeHeader("x-trace-id", "trace-123");

        Message<String> message = MessageBuilder.createMessage(
            "Order created",
            outgoing.getMessageHeaders()
        );

        StompHeaderAccessor received = StompHeaderAccessor.wrap(message);

        System.out.println("command=" + received.getCommand());
        System.out.println("destination=" + received.getDestination());
        System.out.println(
            "traceId=" + received.getFirstNativeHeader("x-trace-id")
        );
        System.out.println("payload=" + message.getPayload());
    }
}
~~~

Run with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.NativeHeadersDemo
~~~

Output:

~~~text
command=SEND
destination=/app/orders
traceId=trace-123
payload=Order created
~~~

Explanation:

1. create(StompCommand.SEND) creates an accessor for a SEND frame.
2. setDestination() sets the destination Spring uses for routing and updates STOMP's native destination.
3. setNativeHeader() adds a custom header to the native header map.
4. getMessageHeaders() supplies headers for MessageBuilder to build the message. Once headers are packaged, the accessor defaults to no longer being mutable.
5. wrap(message) creates an accessor from an existing message to read or adjust headers.
6. getFirstNativeHeader() retrieves the first value of the x-trace-id header.

This example verifies storing and accessing metadata in a Spring Message. To test headers actually traveling over the network, you need a STOMP endpoint and an integration test sending/receiving frames over WebSocket or TCP transport.

## 8. Reading Native Headers When You Only Have a Message

In an interceptor or generic message-processing component, sometimes you only have a Message<?> without an existing StompHeaderAccessor. You can use NativeMessageHeaderAccessor's static method to get the first value from MessageHeaders:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.NativeMessageHeaderAccessor;

public String readTraceId(Message<?> message) {
    return NativeMessageHeaderAccessor.getFirstNativeHeader(
        "x-trace-id",
        message.getHeaders()
    );
}
~~~

This static method reads the native header area from the message's header map and returns null if the header name is not found. If you need to manipulate multiple headers or need STOMP-specific APIs, wrap the message with StompHeaderAccessor.

You can inspect the entire native map using an accessor:

~~~java
StompHeaderAccessor accessor = StompHeaderAccessor.wrap(message);
Map<String, List<String>> nativeHeaders = accessor.toNativeHeaderMap();

nativeHeaders.forEach((name, values) ->
    System.out.println(name + " = " + values)
);
~~~

The returned map is a copy. The snippet above is only for observation, logging, or conversion; do not use it as a way to modify a message's native headers.

## 9. Modifying Native Headers of an Existing Message

MessageHeaders is immutable after the message is created. Do not do this:

~~~java
message.getHeaders().put("x-trace-id", "trace-123");
~~~

That call is not a valid way to update a message and can throw UnsupportedOperationException.

Create a new accessor from the message and then build a new message:

~~~java
StompHeaderAccessor accessor = StompHeaderAccessor.wrap(message);
accessor.setNativeHeader("x-processed-by", "order-service");

Message<?> updated = MessageBuilder.createMessage(
    message.getPayload(),
    accessor.getMessageHeaders()
);
~~~

wrap(message) copies existing headers into a mutable accessor. The original message is unchanged; updated is a new message carrying the added header. When getMessageHeaders() is called, the accessor defaults to transitioning to an immutable state to avoid header edits after the message has been published to other components.

If a pipeline needs to pass an accessor across multiple components before finalizing the message, MessageHeaderAccessor provides setLeaveMutable(true) and setImmutable(). Keep headers mutable only within a controlled scope; before sharing the message across threads or other components, finish editing and freeze the headers.

## 10. Mapping Between Native Headers and Processing Headers

Native headers and processing headers can describe the same concept while serving two different layers.

For STOMP:

| STOMP header | How Spring commonly exposes it |
|---|---|
| destination | SimpMessageHeaderAccessor.getDestination() |
| content-type | MessageHeaderAccessor.getContentType() and StompHeaderAccessor |
| subscription | subscription id of SimpMessageHeaderAccessor |
| id in SUBSCRIBE/UNSUBSCRIBE | subscription id depending on command context |
| x-trace-id | Custom native header, read with getFirstNativeHeader() |
| receipt | Native STOMP header, read via StompHeaderAccessor API |

StompHeaderAccessor translates several standard STOMP headers into corresponding processing headers so Spring's processing layer has a unified API. The original protocol headers remain managed in the native header map so frames can be reconstructed or protocol needs served.

For example, calling setDestination("/app/orders") on StompHeaderAccessor updates Spring's destination and the native destination header. If you only set a generic header named destination via setHeader(), do not expect it to have the same effect as the specialized setDestination() API.

When converting bidirectionally, use the protocol-specific accessor to keep mappings consistent. Manually editing only one of the two representations can leave them out of sync.

## 11. Native Headers in a Custom Protocol

If integrating an internal protocol or a custom broker, you can subclass NativeMessageHeaderAccessor. The subclass should be responsible for:

- Creating an accessor from parsed protocol headers.
- Normalizing common headers needed for Spring processing.
- Keeping protocol-specific headers in the native header map.
- Providing typed getters/setters for important headers.
- Converting a Spring Message into a protocol frame or request when sending outbound.
- Clearly defining rules for repeated headers, null values, encoding, and unsupported headers.

NativeMessageHeaderAccessor has protected constructors accepting a native header map or a Message. Thus an integration class can call super(...) from its constructor. However, storing the map alone is not enough for protocol integration; you must implement conversion between external frames and Spring Messages on both inbound and outbound paths.

Do not create a generic subclass just to hold String headers if the project already has an official accessor for that protocol. Prefer StompHeaderAccessor or JmsMessageHeaderAccessor to preserve the mapping rules Spring provides.

## 12. Limitations, Security, and Common Pitfalls

### 12.1. Not Every Header Travels End-to-End Across the System

Adapters, message converters, brokers, or clients may filter, rename, normalize, or strip headers. The fact that a value appears in an internal message's native header map does not automatically guarantee it will arrive at the final destination. Verify mapping configuration and write integration tests at transport boundaries.

### 12.2. Do Not Trust Native Headers as Authenticated Data

Native headers often originate from external clients or brokers. A client can send x-user-id, x-role, or x-tenant-id itself. Do not use these values to grant permissions or determine identity unless they have been verified by a server-side authentication mechanism.

Use the Principal established by Spring Security or the authentication layer for sender identity. If a tenant or correlation id from an external header is needed, validate its format, enforce length limits, and check its relationship with the authenticated session/context.

### 12.3. Do Not Put Secrets in Custom Headers

Headers may be logged, displayed in admin tools, or passed across multiple systems. Do not place passwords, access tokens, API keys, or sensitive personal data into native headers unless the protocol and security architecture explicitly specify how they are protected. When using STOMP over the network, enable TLS and manage credentials using an appropriate authentication mechanism.

### 12.4. Do Not Confuse Header Names and APIs

Common mistakes:

- Using setHeader() when intending to send a custom header out over the protocol.
- Using setNativeHeader() for metadata intended solely for internal use.
- Calling getFirstNativeHeader() and assuming every header has only one value.
- Using addNativeHeader() without checking whether the protocol supports repeated headers.
- Mutating MessageHeaders directly instead of wrapping the message with an accessor.
- Modifying the map returned by toNativeHeaderMap() expecting the original data to change.
- Reading destination manually from the native map when the protocol accessor already provides getDestination().
- Assuming native headers of one protocol will automatically map to another protocol.
- Trusting headers received from clients without validation.

## 13. Testing Native Headers

A test suite should verify the following behaviors:

1. A newly created accessor records native headers accurately.
2. setNativeHeader replaces previous values.
3. addNativeHeader appends values according to protocol rules.
4. getFirstNativeHeader returns the first value and returns null when absent.
5. removeNativeHeader removes the corresponding header.
6. toNativeHeaderMap returns a copy and does not allow modifications to that map to affect the accessor.
7. StompHeaderAccessor keeps destination/content type synchronized between processing headers and native headers.
8. wrap(message) preserves custom headers already packaged in the message.
9. MessageHeaders cannot be mutated directly after the message is created.
10. Integration tests confirm headers are actually sent/received over the transport, if the application depends on retaining headers over the network.

Tests should cover both standard and custom headers. A test that merely reads back the accessor immediately after setting is insufficient to prove headers are serialized, transmitted through a broker, and properly restored on the receiving side.

## 14. Summary

NativeMessageHeaderAccessor establishes a clear boundary between Spring's internal metadata and original headers of external protocols. Native headers are stored in a multi-valued map under the NATIVE_HEADERS key; the accessor provides APIs to read, set, add, and remove values without manually manipulating internal structures.

In STOMP applications, prefer StompHeaderAccessor. Use common APIs such as getDestination() for Spring-normalized information, and getFirstNativeHeader()/getNativeHeader() for custom protocol headers. When modifying an existing message, wrap it into a mutable accessor and create a new message. Finally, always verify mappings at transport boundaries and treat externally received native headers as data that must be validated.

## References

- Spring Framework 6.2.2 — NativeMessageHeaderAccessor: https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/messaging/support/NativeMessageHeaderAccessor.html
- Spring Framework 6.2.2 — MessageHeaderAccessor: https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/messaging/support/MessageHeaderAccessor.html
- Spring Framework 6.2.x — StompHeaderAccessor: https://docs.spring.io/spring-framework/docs/6.2.x-SNAPSHOT/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaderAccessor.html
- Spring Framework 6.2.2 — StompHeaders: https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaders.html