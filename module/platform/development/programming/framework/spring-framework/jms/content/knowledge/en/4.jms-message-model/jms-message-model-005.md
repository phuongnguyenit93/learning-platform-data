# StreamMessage and Typed Value Sequences in JMS / Spring JMS

## 1. What Is StreamMessage?

`StreamMessage` is one of the five **body** types in JMS (Java Message Service, now the **Jakarta Messaging** specification). It stores an **ordered sequence** of provider-supported Java primitive values, `String`s, and `byte[]`s. The producer writes values sequentially using methods like `writeString()`, `writeInt()`, and `writeDouble()`; the consumer reads them **in the exact corresponding order** using `readString()`, `readInt()`, and `readDouble()`.

Example logically structured message:

~~~text
StreamMessage Body:
  [0] String  = "ORDER"
  [1] int     = 42
  [2] double  = 18.75
  [3] boolean = true
  [4] byte[]  = [1, 2, 3]

Valid reads per schema:
  readString()  → "ORDER"
  readInt()     → 42
  readDouble()  → 18.75
  readBoolean() → true
  readObject()  → byte[] {1, 2, 3}
~~~

**Core point:** `StreamMessage` is a **positional sequence of typed fields**; it is **not** `java.util.stream.Stream`, not a continuous TCP data stream, and not an arbitrary object serialized into a message. When sending a message, the application writes the body according to the schema fields. When receiving, the consumer must know that schema and read sequentially.

In Spring Framework, `JmsTemplate` can send/receive `StreamMessage` directly, but you must explicitly build and parse the message body. `JmsTemplate` does not automatically infer a positional schema of values.

### 1.1. Position in the JMS Message Model

~~~text
JMS Message
├─ Headers    (JMSMessageID, JMSCorrelationID, JMSDestination, ...)
├─ Properties (schemaVersion, producerName, businessType, ...)
└─ Body       (StreamMessage: fields written sequentially)
               ┌─────────┬─────┬───────┬───────┬────────────┐
               │ String  │ int │double │boolean│ byte[]     │
               ├─────────┼─────┼───────┼───────┼────────────┤
               │ "ORDER" │ 42  │ 18.75 │ true  │ {1,2,3}    │
               └─────────┴─────┴───────┴───────┴────────────┘
~~~

`Headers` and `Properties` have their own APIs. Values inside `StreamMessage` **do not inherently carry field names**; if you need routing/filtering on an attribute, place it in a message property, e.g. `message.setIntProperty("schemaVersion", 1)`. Do not confuse `getIntProperty(...)` with `readInt()`:

- `getIntProperty("schemaVersion")` retrieves a property by **name** and does not advance the body read cursor.
- `readInt()` reads the **next body field** and advances the read cursor.

## 2. When to Use StreamMessage? Comparison with Other Message Types

| JMS message type | Body represents | Access pattern | Best suited for |
| --- | --- | --- | --- |
| `TextMessage` | A `String` | `getText()` | JSON, XML, plain text |
| `BytesMessage` | Binary byte stream | Read bytes/primitives via `read...` methods, self-managed binary format | Defined binary protocols, byte-level layouts |
| `MapMessage` | Typed **name → value** pairs | `getInt("quantity")`, `getString("type")` | Named field sets, order-independent access |
| `StreamMessage` | **Positional sequence of typed values** | `readString()`, `readInt()`, `readObject()` in order | Simple sequential formats where the consumer knows exact order/types |
| `ObjectMessage` | `Serializable` Java object | `getObject()` | Java integration using serialization under tight contracts; requires security and compatibility review |

Example of two messages carrying the same data but interpreted differently:

~~~java
// Illustrative code snippet in a callback with jakarta.jms.Session session:
StreamMessage stream = session.createStreamMessage();
stream.writeString("BOOK"); // element at index 0
stream.writeInt(3);         // element at index 1

MapMessage map = session.createMapMessage();
map.setString("kind", "BOOK");
map.setInt("quantity", 3);  // read by name, independent of position
~~~

With `StreamMessage`, the consumer must **know** that index 0 is the item kind and index 1 is the quantity. With `MapMessage`, the consumer looks up by names `kind` and `quantity`. The two message types share the same business meaning but are not interchangeable at the API level.

**Do not use `StreamMessage` just because you want to "stream" large files.** It is a sequential body format for a single JMS message; the application/broker is still bound by message size and memory limits. Transferring large files or datasets requires chunking strategies, object storage, or specialized protocols suited to actual load requirements.

## 3. API for Creating and Writing Value Sequences

With **Jakarta Messaging** (`jakarta.jms.*`, used in Spring Framework 6+/Spring Boot 3+), creating a message looks like:

~~~java
StreamMessage message = session.createStreamMessage();
message.writeString("ORDER");
message.writeInt(42);
message.writeDouble(18.75);
message.writeBoolean(true);
message.writeBytes(new byte[] {1, 2, 3});
~~~

Here `session` is a `jakarta.jms.Session` provided by a JMS provider; this example is **only a code snippet** and must live in a method permitted to throw `JMSException`. For legacy JMS APIs using `javax.jms.*`, stick strictly to one library generation within a single project.

### 3.1. Corresponding Write/Read Methods

| Value type | Write to StreamMessage | Direct read |
| --- | --- | --- |
| `boolean` | `writeBoolean(boolean)` | `readBoolean()` |
| `byte` | `writeByte(byte)` | `readByte()` |
| `short` | `writeShort(short)` | `readShort()` |
| `char` | `writeChar(char)` | `readChar()` |
| `int` | `writeInt(int)` | `readInt()` |
| `long` | `writeLong(long)` | `readLong()` |
| `float` | `writeFloat(float)` | `readFloat()` |
| `double` | `writeDouble(double)` | `readDouble()` |
| `String` | `writeString(String)` | `readString()` |
| `byte[]` | `writeBytes(byte[])` or `writeBytes(byte[], off, len)` | `readBytes(byte[])` or `readObject()` |
| Primitive wrapper, `String`, `byte[]` | `writeObject(Object)` | `readObject()` |

`writeObject(...)` **does not mean** you can write any arbitrary Java object. The API only permits primitive wrappers (such as `Integer`, `Boolean`, `Double`), `String`, and `byte[]`. Example:

~~~java
message.writeObject(Integer.valueOf(7));     // valid: equivalent to writeInt(7)
message.writeObject("hello");                // valid: equivalent to writeString
message.writeObject(new byte[] {10, 20});    // valid: one byte[] field

// Invalid for StreamMessage:
// message.writeObject(new java.util.ArrayList<String>());
// message.writeObject(new java.math.BigDecimal("12.5"));
~~~

For objects outside the supported types, the provider must raise a format error (typically `MessageFormatException`), **not serialize the object automatically** like `ObjectMessage`. If business data is a multi-field object, agree on how to map its fields into `StreamMessage` fields or use another format such as JSON inside `TextMessage`.

### 3.2. Each Write Appends One Positional Field

~~~java
message.writeInt(10);     // field #0: int 10
message.writeString("A"); // field #1: String "A"
message.writeInt(20);     // field #2: int 20
~~~

Consumer reads:

~~~java
int first = message.readInt();      // 10
String second = message.readString(); // "A"
int third = message.readInt();      // 20
~~~

In the read example, `message` must **be in read-only mode with the cursor at the beginning**. For a message just created by a producer, call `reset()` before reading it yourself; for a newly received message, the provider already puts it into read-only mode. This is an important difference compared to ordinary getter/setter APIs.

There is no standard method like `getField(2)` or `get("quantity")` on `StreamMessage`. To reach the third field, read/consume the preceding fields per the contract; to re-read, `reset()` moves the cursor back to the start, without allowing random jumps to arbitrary positions.

## 4. Body Lifecycle: Write-Only, Reset, Read-Only, and ClearBody

### 4.1. State Diagram

~~~text
session.createStreamMessage()
          │
          ▼
      WRITE-ONLY
  (writeInt / writeString /...)
          │
          │ reset() or message has been sent/received
          ▼
      READ-ONLY
  (readInt / readString /...)
          │                  │
          │ reset()          │ clearBody()
          ▼                  ▼
      READ-ONLY          WRITE-ONLY (empty body)
  (cursor to start)      (write new body)
~~~

- **When newly created:** the body is **write-only**; `write...()` works, while calling `read...()` throws `MessageNotReadableException`.
- **`reset()`:** puts the body into **read-only mode** and moves the cursor back to the start; does not clear data. Calling `reset()` again while reading lets you read from the beginning.
- **When a message is received:** the provider has already prepared the body in read-only mode; the consumer can call `read...()` directly. Calling `reset()` before the first read is unnecessary.
- **While read-only:** calling `write...()` throws `MessageNotWriteableException`.
- **`clearBody()`:** clears the **body** and switches back to write-only mode to build a new body. It **does not clear headers/properties**; to clear properties, use `clearProperties()`.
- **Sending the message:** the provider handles transmitting the sent message per the API. Do not treat retaining the local object after `send` as an open network stream; a sent message can still be manipulated by the client without mutating the copy already sent.

### 4.2. Example of reset and clearBody

The following is a **code snippet running inside a callback with `Session session`** to observe state transitions:

~~~java
StreamMessage m = session.createStreamMessage();
m.writeInt(7);
m.writeString("ok");

// m.readInt();   // error: MessageNotReadableException (write-only)

m.reset(); // switch to read-only and reset cursor to start
System.out.println(m.readInt());
System.out.println(m.readString());

m.reset(); // return to start without clearing body
System.out.println(m.readInt());

// m.writeInt(8); // error: MessageNotWriteableException (read-only)

m.clearBody(); // clear body; return to write-only
m.writeString("changed");
m.reset();
System.out.println(m.readString());
~~~

Stdout (with a normal provider):

~~~text
7
ok
7
changed
~~~

**Do not call `clearBody()` just to read from the beginning:** that call deletes data. Use `reset()` to re-read; use `clearBody()` when intentionally constructing a new body.

## 5. Sequential Reading Rules and JMS-Allowed Type Conversions

### 5.1. Order Matters More Than Variable Names

Suppose the producer writes:

~~~java
message.writeInt(42);
message.writeString("ORDER");
message.writeBoolean(true);
~~~

The consumer must read field #0 before field #1:

~~~java
int id = message.readInt();           // field 0: 42
String kind = message.readString();   // field 1: "ORDER"
boolean active = message.readBoolean(); // field 2: true
~~~

If the consumer calls `readBoolean()` directly on an `int` field, that conversion is invalid and throws `MessageFormatException`. Because the message **does not record field names in the body**, calling `readString()` cannot "skip" to the `kind` field: the first call applies to **field 0**. Some valid conversions can mask schema bugs: for example, `readString()` is allowed to read an `int` field and return a string, yet it still consumes **field 0** instead of advancing to the `String` field the caller expected.

### 5.2. Allowed Conversion Table

The JMS specification provides a conversion table for `StreamMessage`. The table below summarizes the **written type** in the left column and the **allowed read methods** in the right column (in addition to `readObject()`):

| Written field | Allowed types when reading |
| --- | --- |
| `boolean` | `boolean`, `String` |
| `byte` | `byte`, `short`, `int`, `long`, `String` |
| `short` | `short`, `int`, `long`, `String` |
| `char` | `char`, `String` |
| `int` | `int`, `long`, `String` |
| `long` | `long`, `String` |
| `float` | `float`, `double`, `String` |
| `double` | `double`, `String` |
| `String` | `boolean`, `byte`, `short`, `int`, `long`, `float`, `double`, `String` |
| `byte[]` | `byte[]` via `readBytes(byte[])`; `readObject()` also returns a `byte[]` |

Examples of valid conversions:

~~~java
// While in write-only mode:
message.writeByte((byte) 7);
message.writeInt(42);
message.writeFloat(2.5f);
message.writeString("123");

message.reset(); // now read
int a = message.readInt();       // widening byte -> int: 7
String b = message.readString(); // int -> String: "42"
double c = message.readDouble(); // widening float -> double: 2.5
int d = message.readInt();       // parse String "123" -> int: 123
~~~

Points to remember:

1. **Not every automatic Java conversion is supported by JMS.** For instance, `int → double` is valid widening in many Java expressions, yet it is **not an allowed conversion in `StreamMessage`**. `message.writeInt(42); message.reset(); message.readDouble();` is a format error. You must read `int` and cast to `double` in your code if needed.
2. **String-to-number conversions must be parseable.** `writeString("abc")` followed by `readInt()` can throw `NumberFormatException` (runtime), in addition to JMS format errors in other cases.
3. **String-to-boolean conversions must be explicit.** Java's `Boolean.valueOf("yes")` evaluates to `false`; therefore strings like `"yes"` or `"1"` must not be treated as safe boolean representations. Standardize on `"true"` / `"false"` or use `writeBoolean()` directly.
4. **No arbitrary narrowing.** A `long` field cannot be read with `readInt()` merely because its value is small; `double` cannot be read with `readFloat()`.
5. **`readObject()`** retrieves the next field as the corresponding Java wrapper: `writeInt(42)` gives `Integer`; `writeBoolean(true)` gives `Boolean`; `writeBytes(...)` gives `byte[]`. It does not expand the set of writable types.

### 5.3. `readObject()` Reads a Field, Not an Arbitrary Deserialized Object

~~~java
message.writeInt(42);
message.writeBoolean(true);
message.writeString("done");
message.reset();

Object x = message.readObject(); // Integer(42)
Object y = message.readObject(); // Boolean.TRUE
Object z = message.readObject(); // "done"
~~~

This is not `ObjectInputStream.readObject()` or `ObjectMessage.getObject()`. Do not use it to automatically "read an entire record" into an `OrderDto`. If you want a record, map each field explicitly and validate against the schema before constructing the DTO.

## 6. `byte[]` Fields in StreamMessage: Subtle Traps

`StreamMessage` permits **a field of type `byte[]`** among other fields. Do not confuse this with an entire `BytesMessage` or with `readByte()`.

Producer example:

~~~java
message.writeString("BINARY");
message.writeBytes(new byte[] {10, 20, 30, 40, 50});
message.writeInt(9);
~~~

Consumers have two ways to read a `byte[]` field:

### 6.1. Simple Way: `readObject()`

~~~java
message.reset();
String label = message.readString(); // "BINARY"
byte[] bytes = (byte[]) message.readObject();
int version = message.readInt();     // 9
~~~

Using `readObject()`, the `byte[]` field is returned as a single array; this is usually the simplest choice for moderately sized arrays. If you are **midway through reading** a `byte[]` field with `readBytes(...)`, do not switch to `readObject()` to "finish reading".

### 6.2. Buffered Way: `readBytes(byte[])`

The `readBytes(byte[] buffer)` API reads **bytes of a single `byte[]` field** into the provided buffer. Its return value is the number of bytes read in that call, **not the total length of the message**.

~~~java
import java.io.ByteArrayOutputStream;

// Code snippet inside a method; message is already reset/readable.
String label = message.readString();
byte[] buffer = new byte[2];
ByteArrayOutputStream out = new ByteArrayOutputStream();

while (true) {
    int count = message.readBytes(buffer);
    if (count > 0) {
        out.write(buffer, 0, count);
    }
    // If fewer bytes than buffer size are read, the byte[] field has ended.
    // -1: null or end of field; 0: empty field.
    if (count < buffer.length) {
        break;
    }
}

byte[] bytes = out.toByteArray(); // [10, 20, 30, 40, 50]
int version = message.readInt();  // 9
~~~

Suppose the buffer length is 2 and the field has 5 bytes; successive calls return **2, 2, 1**. If the field has exactly 4 bytes, calls return **2, 2, -1**: after the final full-buffer read, one more call is needed to confirm the end. If the field is an empty array, the first call returns **0**; if the field is `null`, it returns **-1**. When distinguishing `null` from an empty array matters, the schema should include a presence flag or use `readObject()` with a valid data contract.

**An easy-to-miss rule:** after the first `readBytes(...)` call on a `byte[]` field, you **must finish reading that field completely** before reading the next field. If you read 2 out of 5 bytes and then call `readInt()`, the provider throws `MessageFormatException` because the consumer has not finished the byte field.

~~~java
// Invalid state when byte[] field is longer than buffer:
message.readBytes(new byte[2]); // unread bytes may remain
int next = message.readInt();    // MessageFormatException
~~~

A single `writeBytes(bytes, offset, length)` call writes **one `byte[]` field** containing the selected slice. Two consecutive `writeBytes(...)` calls create **two separate fields**, not one concatenated field. The consumer must read each field in order.

## 7. Important Exceptions

| Exception / situation | Common cause | Fix |
| --- | --- | --- |
| `MessageNotReadableException` | Calling `read...()` while the body is still write-only | Call `reset()` before reading a newly created message yourself; received messages arrive read-only |
| `MessageNotWriteableException` | Calling `write...()` on a read-only body | To replace the body, call `clearBody()` and rewrite; consider creating a new message |
| `MessageFormatException` | Reading with a type not in the conversion table; `writeObject` with a disallowed class; reading a new field before finishing a `byte[]` field | Standardize schema/version and read types; finish reading the byte field |
| `MessageEOFException` | Reading another field when no fields remain in the stream | Use a schema specifying field count/types; catch EOF intentionally only if the format allows it |
| `NumberFormatException` | Trying to read a primitive from an unparseable `String`, e.g. `"abc"` as `int` | Validate payloads; prefer writing primitives with proper types instead of strings |
| Other `JMSException` | Provider, connection, transport, or resource error | Check exception/cause, broker logs, transactions, and retry policy |

**EOF is neither a timeout nor a broker disconnect error.** `MessageEOFException` occurs when reading past the last field of a body. A receive timeout happens at the `receive(timeout)` / `JmsTemplate.receive(...)` layer, typically returning `null`; never equate the two.

Example checking for end of stream after known fields:

~~~java
import jakarta.jms.MessageEOFException;

// After reading all fields expected by the schema:
try {
    message.readObject();
    throw new IllegalStateException("Unexpected trailing field");
} catch (MessageEOFException expected) {
    System.out.println("End of stream");
}
~~~

This checks for *no trailing fields* when the format specifies a fixed length; in an extensible format, adjust handling accordingly. Do not rely on EOF errors as a complete replacement for version/schema contracts.

## 8. Spring JMS: Creating and Reading StreamMessage Properly

Spring JMS layers conveniences atop the Jakarta Messaging API:

- `JmsTemplate.send(destination, MessageCreator)` lets you create the **exact JMS message type** via a `Session` callback; for `StreamMessage`, prefer this approach.
- `JmsTemplate.receive(destination)` returns a **raw `jakarta.jms.Message`**, which you can check with `instanceof StreamMessage` and read field by field per schema.
- `convertAndSend(...)` / `receiveAndConvert(...)` use `MessageConverter`; the default converter handles `String → TextMessage`, `byte[] → BytesMessage`, `Map → MapMessage`, and `Serializable → ObjectMessage`. It **does not automatically turn an arbitrary record into a sequence of `StreamMessage` fields**.
- With `@JmsListener`, to process `StreamMessage`, ensure the listener adapter/converter passes either the **raw JMS message** or a payload produced by a custom converter to your handler; do not assume declaring a DTO parameter alone tells Spring field positions and types.
- `getBody(Class<T>)` on `jakarta.jms.Message` **must not be used with `StreamMessage`**: the specification requires throwing `MessageFormatException`. Use `read...()` or `readObject()`.

### 8.1. Complete Demo: Spring Boot 3 and Apache ActiveMQ Artemis

This demo creates a `StreamMessage` with five fields following a defined schema, sends it to a queue, then receives the raw message from that same queue and reads it back. Requirements: **Java 17+**, **Maven**, **Docker**, and a running broker. The sample version **Spring Boot 3.5.7** uses the `jakarta.jms.*` namespace; real projects should align versions via their own BOM.

**Step 1. Start local Artemis:**

~~~bash
docker run --rm -d --name stream-jms-broker \
  -p 127.0.0.1:61616:61616 \
  apache/artemis:latest-alpine
~~~

This is a local learning environment; the image uses default lab credentials `artemis/artemis`. Wait for the broker to be ready by checking `docker logs stream-jms-broker`. For production deployments, configure dedicated users/roles, TLS, resource limits, queue auto-creation rules, and monitoring.

**Step 2. Create `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-stream-message-demo</artifactId>
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

**Step 3. Create `src/main/resources/application.properties`:**

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis

spring.jms.template.receive-timeout=5s
~~~

The receive timeout prevents the program from blocking forever when no message arrives; the demo broker can auto-create queues under default settings, whereas in production queues should be explicitly declared and authorized.

**Step 4. Create `src/main/java/com/example/jms/StreamMessageApplication.java`:**

~~~java
package com.example.jms;

import java.util.Arrays;
import java.util.Locale;

import jakarta.jms.Message;
import jakarta.jms.MessageEOFException;
import jakarta.jms.StreamMessage;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class StreamMessageApplication {

    public static void main(String[] args) {
        SpringApplication.run(StreamMessageApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JmsTemplate jmsTemplate) {
        return args -> {
            // Producer writes 5 fields per schema version 1.
            jmsTemplate.send("demo.stream.orders", session -> {
                StreamMessage message = session.createStreamMessage();
                message.setIntProperty("schemaVersion", 1);
                message.writeString("ORDER");
                message.writeInt(42);
                message.writeDouble(18.75);
                message.writeBoolean(true);
                message.writeBytes(new byte[] {1, 2, 3});
                return message;
            });

            // Receive raw JMS message; do not use receiveAndConvert().
            Message incoming = jmsTemplate.receive("demo.stream.orders");
            if (incoming == null) {
                System.out.println("Receive timeout");
                return;
            }
            if (!(incoming instanceof StreamMessage stream)) {
                throw new IllegalStateException(
                        "Expected StreamMessage, got "
                                + incoming.getClass().getName());
            }

            // Schema must match the order written by the producer.
            int schemaVersion = stream.getIntProperty("schemaVersion");
            if (schemaVersion != 1) {
                throw new IllegalStateException(
                        "Unsupported schemaVersion: " + schemaVersion);
            }

            String kind = stream.readString();
            int orderId = stream.readInt();
            double amount = stream.readDouble();
            boolean active = stream.readBoolean();
            byte[] flags = (byte[]) stream.readObject();

            System.out.printf(Locale.ROOT,
                    "version=%d kind=%s id=%d amount=%.2f active=%s bytes=%s%n",
                    schemaVersion, kind, orderId, amount, active,
                    Arrays.toString(flags));

            try {
                // No fields left; demonstrates EOF detection.
                stream.readObject();
                throw new IllegalStateException("Unexpected trailing field");
            } catch (MessageEOFException expected) {
                System.out.println("End of stream");
            }
        };
    }
}
~~~

**Step 5. Run from the directory containing `pom.xml`:**

~~~bash
mvn spring-boot:run
~~~

When the broker is running and the message is received properly, the two lines printed by our code are:

~~~text
version=1 kind=ORDER id=42 amount=18.75 active=true bytes=[1, 2, 3]
End of stream
~~~

Spring and Artemis startup/shutdown logs may also appear. If no message arrives within the timeout, the program prints:

~~~text
Receive timeout
~~~

Execution walkthrough:

1. `JmsTemplate.send(...)` obtains a `Session` from the provider; the callback calls `session.createStreamMessage()` and writes the body sequentially.
2. `schemaVersion` is a **message property** used to select a decoder; it is not field #0 and does not shift body read positions.
3. The provider sends the message via the broker. The consumer calls `JmsTemplate.receive(...)` to fetch **the raw JMS Message itself**.
4. The received message is in read-only mode; the consumer reads `String, int, double, boolean, byte[]` per the schema. Here `readObject()` is used for `byte[]` to read the whole field at once.
5. `readObject()` after the last field throws `MessageEOFException`; the code uses it to detect unexpected trailing fields.
6. Spring manages `Session`/`Connection` on send/receive; **creating and interpreting `StreamMessage` fields** remains the application's responsibility.

To stop the broker after the demo:

~~~bash
docker stop stream-jms-broker
~~~

**Example limitations:** it intentionally sends and receives in the same application for easy verification. Production systems normally run producers and consumers in independent processes; both sides must still agree on schema, queue, headers, and delivery semantics. This demo does not prove cross-database transactions, exactly-once delivery, or failover recovery.

### 8.2. Using Asynchronous Listeners

In continuous message-processing systems, consumers usually use `@JmsListener` or a listener container instead of synchronous `receive()`. For `StreamMessage`, define an explicit payload parsing strategy:

- If the handler can receive raw `jakarta.jms.Message`, check `instanceof StreamMessage` and call `read...()` methods according to the schema.
- If the project uses a global converter, write/test a custom `MessageConverter` that converts `StreamMessage` to a record/DTO based on `schemaVersion` with full validation, instead of relying on defaults.
- When handling format errors, decide the requeue/retry/DLQ policy; schema-corrupted messages can fail repeatedly in an infinite loop if redelivered unclassified.

Listener containers handle acknowledgment and transactions, yet they **do not replace a schema decoder**. If body reading throws an exception, whether the message is redelivered or routed to a DLQ depends on transactions, acknowledgment mode, broker redelivery policy, and how the framework catches/handles exceptions.

## 9. Schema Design and Version Compatibility

Because a `StreamMessage` body carries no field names, **the schema must be an explicit contract between producer and consumer**. Example clear definition:

| Order | Type | Business name | Convention |
| --- | --- | --- | --- |
| Header property | `int` | `schemaVersion` | 1 |
| Field 0 | `String` | `kind` | `"ORDER"` |
| Field 1 | `int` | `orderId` | Positive integer |
| Field 2 | `double` | `amount` | Demo example; monetary amounts should use minor units/decimal schema to avoid rounding issues |
| Field 3 | `boolean` | `active` | Activation status |
| Field 4 | `byte[]` | `flags` | Binary payload with separate specification |

### 9.1. Why Can Reordering Break Consumers?

Producer version 1 writes `String, int, double`. Producer version 2 unilaterally changes that to `String, double, int`. Consumer version 1 will attempt to read field #1 with `readInt()`, encounter a `double`, and fail with `MessageFormatException`. Even when two versions fall under a valid conversion, it can introduce **silent data corruption** by assigning values to the wrong business fields.

**How to manage changes:**

1. Carry `schemaVersion` in a property or an agreed leading field; the consumer reads the version before decoding.
2. Document the field layout **completely and in order**, including types, units, nullability, constraints, and byte encodings.
3. Maintain per-version decoders or tested compatibility policies. For multi-version schemas, never insert a field into the middle without bumping the version.
4. For optional fields, specify explicit presence flags or field counts rather than relying solely on EOF.
5. Validate data after reading: value bounds, string lengths, and array sizes; do not trust data merely because a read method matched the type.
6. Standardize error reporting, retry/DLQ handling, and observability of `schemaVersion` to trace mismatches.

### 9.2. When Should Another Format Be Used?

`StreamMessage` fits well when both sides are controlled by the same team, the schema is short and rarely changes, and sequential primitive reads/writes are beneficial. If multiple languages/frameworks, optional fields, complex backward compatibility, or tooling/schema registries are involved, consider JSON, Avro, or Protobuf inside `TextMessage` or `BytesMessage`. JMS defines the **message type API**, not cross-language serialization or version semantics for your business records.

If using `double` for money, beware of floating-point representation errors. Financial domains typically use `long` counts of minor units (cents, etc., per convention) or schema-validated decimal strings instead of expecting exact `double` arithmetic.

## 10. Common Bugs in Real-World Code

### Mistake 1: Reading Out of Order

~~~java
message.writeInt(42);
message.writeString("OK");
message.reset();

// WRONG if expecting the first element to be "OK":
String status = message.readString(); // actually "42" due to allowed conversion
~~~

This bug is subtler than an exception: converting `int` to `String` is valid so the consumer **throws no error**, yet business data lands in the wrong field. Enforce a schema and ordering tests.

### Mistake 2: Assuming All Java Widening Works

~~~java
message.writeInt(42);
message.reset();
// message.readDouble(); // MessageFormatException: int -> double is not allowed
long value = message.readLong(); // 42, valid: int -> long
~~~

Rely on the JMS conversion table, not Java casting intuition.

### Mistake 3: Forgetting `reset` When Reading a Newly Created Message

~~~java
StreamMessage m = session.createStreamMessage();
m.writeInt(1);
// m.readInt(); // MessageNotReadableException
m.reset();
int one = m.readInt(); // 1
~~~

A **received** message is already read-only; do not force consumers to call `reset()` just for the initial read.

### Mistake 4: Calling `clearBody` Just to "Rewind"

`clearBody()` **deletes the content** and switches back to write-only mode. To re-read from the beginning, use `reset()`.

### Mistake 5: Moving to the Next Field Before Finishing `byte[]`

`readBytes(buffer)` can return the buffer length multiple times. Keep reading until the return value is **less than `buffer.length`**, even if that requires one final call returning `-1`. Calling `readInt()` while bytes remain unconsumed throws `MessageFormatException`.

### Mistake 6: Misreading the Meaning of EOF

`MessageEOFException` means no fields remain in the body; it does not mean `receive()` timed out. `readBytes(...)` returning `-1` to signal the end of a **`byte[]` field** is also not `MessageEOFException` for the whole message.

### Mistake 7: Calling `writeObject` with an Arbitrary Java Entity

`StreamMessage.writeObject(new Order(...))` is invalid if `Order` is not among the JMS-permitted types. Either split it into individual `writeString/writeInt/...` calls, or use an appropriate message type/serializer.

### Mistake 8: Using `convertAndSend` Expecting a `StreamMessage`

`convertAndSend("demo.stream", orderDto)` goes through `MessageConverter`. There is no default rule "turning each DTO property into a `StreamMessage` field". Use `send(..., session -> session.createStreamMessage())` or a tested custom converter.

### Mistake 9: Calling `getBody` on `StreamMessage`

`message.getBody(List.class)`, `message.getBody(byte[].class)`, or `getBody(Object.class)` must not be used to read a `StreamMessage`; the specification requires `MessageFormatException` for `StreamMessage`. Read using `read...()` APIs.

### Mistake 10: Omitting `schemaVersion`

Consumers will decode incorrectly when the producer adds, changes, or drops fields. Include a version/contract and validate thoroughly before business processing.

### Mistake 11: Ignoring Transactions, Acknowledgments, and Duplicates

`StreamMessage` only defines the **body format**; it does not govern redelivery, transactions, or ordering across consumers. Given possible redelivery after failures, handlers must be idempotent where needed; schema parse failures need a DLQ policy to prevent infinite retry loops.

### Mistake 12: Trusting Payloads from Uncontrolled Sources

Consumers should not write to databases or call downstream services based solely on fields successfully read. Validate `String` lengths, element counts, `byte[]` sizes, numeric ranges, units, sender authorization, and valid versions. For cross-language data, align charset and provider primitive mappings where needed.

## 11. Self-Check Knowledge Quiz

**Question 1.** How does `StreamMessage` differ from `BytesMessage`?  
**Answer:** `StreamMessage` is a sequence of **positionally typed fields**; `BytesMessage` is a byte stream following an application-managed format. Both use sequential reads, but their body contracts differ.

**Question 2.** If you call `writeInt(5)` and then `reset()`, can you read it with `readDouble()`?  
**Answer:** **No**; `int → double` is not in the allowed conversion table. You can call `readInt()`/`readLong()`/`readString()`.

**Question 3.** Why does `readString()` sometimes throw no exception even when code reads the wrong field?  
**Answer:** JMS allows converting many primitives to `String`. The consumer still consumes the next field, potentially causing silent schema bugs.

**Question 4.** A `byte[]` field has 4 bytes, and the buffer length is 2. Two `readBytes` calls return 2 and 2; are you ready to read the next field?  
**Answer:** Not yet. You must call `readBytes` once more to receive `-1`, confirming the end of the field.

**Question 5.** How does `reset()` differ from `clearBody()`?  
**Answer:** `reset()` moves the cursor to the start and sets read-only mode; `clearBody()` deletes the body and sets write-only mode.

**Question 6.** Does Spring's `JmsTemplate.convertAndSend(dto)` create a `StreamMessage` from DTO fields by default?  
**Answer:** No. Use `send` with a `MessageCreator` or a custom converter that explicitly defines the schema.

**Question 7.** What does `readObject()` return after `writeInt(42)`?  
**Answer:** An `Integer` representing 42, not a DTO. After `writeBytes(...)`, it returns `byte[]`.

**Question 8.** What happens if `readObject()` is called after reading all fields of a `StreamMessage`?  
**Answer:** It throws `MessageEOFException`. This is a body-reading state, not a `receive()` timeout.

**Question 9.** Why is a `schemaVersion` message property better than relying solely on EOF?  
**Answer:** The consumer knows which decoder to select **before** reading body fields; EOF only tells you no fields remain, not the positions or meanings of fields across versions.

**Question 10.** Should you call `getBody(Object.class)` to fetch the entire `StreamMessage`?  
**Answer:** No. `getBody` does not support `StreamMessage`; use the sequential read methods.

## 12. Official References

1. [Jakarta Messaging 3.1 Specification — Message body types, StreamMessage, and conversion table](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
2. [Jakarta EE 11 Javadoc — StreamMessage: mode, read/write, readBytes, readObject, reset](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/streammessage)
3. [Jakarta EE 11 Javadoc — Message: headers, properties, clearBody, getBody](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/message)
4. [Spring Framework Reference — Sending Messages / Message Converters](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
5. [Spring Framework Reference — Receiving Messages](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
6. [Spring Framework 6.2.14 Javadoc — JmsTemplate](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
7. [Spring Boot Reference — JMS with ActiveMQ Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html)
8. [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)
