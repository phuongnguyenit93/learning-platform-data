# BytesMessage and Binary Content

> **Module:** Spring Framework – JMS  
> **Group:** Message Model  
> **Topic:** When to use `BytesMessage`, how to encode and read binary payloads, data format contracts, and how to integrate with Spring JMS.

## Learning Objectives

After this lesson, you will be able to:

1. Explain what `jakarta.jms.BytesMessage` is and distinguish it from `TextMessage`, `StreamMessage`, `MapMessage`, and `ObjectMessage`.
2. Create a binary message with `Session.createBytesMessage()`, write using `writeBytes()` or primitive write methods, and read it accurately by state using `readBytes()`, `getBody(byte[].class)`, and `getBodyLength()`.
3. Understand the **write-only** and **read-only** states, the read cursor position, `reset()`, `clearBody()`, and related exceptions.
4. Define an explicit binary contract (byte order, encoding, version, length, content type) and verify a frame yourself using Java 17.
5. Use Spring JMS's `JmsTemplate` and `@JmsListener` to send/receive `byte[]` or `BytesMessage`, enforce size limits, and handle errors.
6. Recognize trade-offs around interoperability, memory, message size, security, and reliability when transmitting binary data through a broker.

## 1. What Is BytesMessage?

In JMS/Jakarta Messaging, every message has a **header**, **properties**, and a **body**. `BytesMessage` is the message type whose **body is a stream of bytes that JMS does not automatically interpret according to any business schema**. The producer decides which bytes are written; the consumer must know how to read those exact bytes.

For example, the body may contain:

- A PNG, JPEG, PDF fragment, or a compressed sequence of bytes.
- A Protocol Buffers, CBOR, Avro binary payload, or a binary format agreed upon by two services.
- A data frame containing an identifier, version, length, and content.
- Primitive values written sequentially with `writeInt()`, `writeLong()`, `writeBoolean()`, `writeUTF()`, etc.

```text
             JMS message
+--------------------------------------------+
| Header: JMSMessageID, JMSDestination, ...  |
+--------------------------------------------+
| Properties: contentType, schemaVersion, ...|
+--------------------------------------------+
| Body: 89 50 4E 47 0D 0A 1A 0A ...         |
|       (bytes, e.g. PNG signature)          |
+--------------------------------------------+
```

**JMS does not infer "this is a PNG image" or "this is protobuf version 2" from the `BytesMessage` type alone.** If the consumer needs that information, the application must define the byte format and corresponding metadata. A byte array that is valid at the transport level is not necessarily valid business data.

Modern Jakarta Messaging uses the `jakarta.jms` package. Many older JMS examples use `javax.jms`; do not mix these two APIs in the same modern Java/Spring example. Spring Framework 6+ uses Jakarta.

## 2. When to Use BytesMessage?

| Need | Usually suitable message type | Notes |
| --- | --- | --- |
| Send text content with clear charset/meaning | `TextMessage` | Convenient for JSON, XML, plain text; primary payload is String |
| Send a byte array or existing binary format | **`BytesMessage`** | Preserves the exact byte sequence according to an agreed format |
| Send primitive values in sequential order | `StreamMessage` or `BytesMessage` | `StreamMessage` has typed stream semantics; `BytesMessage` is for a specific byte layout |
| Send primitive key/value pairs | `MapMessage` | Body is a map; field names are stored as data item names |
| Send a Serializable Java object | `ObjectMessage` | Tied to Java serialization; requires security and version-compatibility review |

**Use `BytesMessage` when binary is an essential part of the contract**, such as fixed-width sensor data, small thumbnails, protobuf understood by both systems, or frames of a legacy protocol. Do not assume every "complex" payload must be bytes: JSON text can be easier to observe and evolve if binary is not required.

### Do Not Confuse a Binary Payload with Unbounded "File Streaming"

The name `BytesMessage` contains the word "bytes", yet a JMS message itself remains a broker-managed unit of send/receive. `readBytes()` allows *incremental client-side reading of the body*, but it **does not automatically turn JMS into a large-file streaming service or guarantee constant broker memory usage**. Each provider has its own message size limits, quotas, and storage costs.

For videos, database backups, multi-gigabyte ZIPs, or large files, a better architecture is usually to **store the blob in object storage** and send a small JMS message containing the object identifier, access-controlled location, size, checksum, and version. Manage object lifetime and access permissions separately from JMS acknowledgment.

## 3. Binary Body and Metadata Are Two Separate Parts

The standard components of a message:

- **JMS Header:** `JMSMessageID`, `JMSCorrelationID`, `JMSTimestamp`, `JMSDestination`, `JMSDeliveryMode`, `JMSExpiration`, `JMSRedelivered`, etc. These headers serve delivery, routing, and correlation.
- **Application Properties:** application-defined names/values, such as `contentType="application/octet-stream"`, `schemaVersion=1`, `jobId="job-42"`. These are **application conventions**, not automatic HTTP headers or a default JMS schema.
- **Body:** the actual bytes to transmit, for example `0xCA 0xFE 0x01 ...`.

Example contract for sending a small thumbnail:

```text
JMS destination : thumbnail.generate
JMSCorrelationID: request-42

Properties:
  contentType    = application/vnd.example.image-task
  schemaVersion  = 1
  objectId       = image-42

Body (binary):
  magic (2 bytes) + version (1 byte)
  + payloadLength (4 bytes, big-endian)
  + raw image bytes (payloadLength bytes)
```

In this example, the version appears **in both the property and the frame** solely to enable early classification and consistency checking. Real applications are not required to duplicate it: choose a single source of truth for the schema and validation rules if two copies exist. Headers/properties are handy for **message selectors** and broker observability, while the body allows the codec to operate independently of JMS transport.

Do not confuse `JMSMessageID` with a business ID or checksum. `JMSMessageID` is assigned by the provider to identify the message in the messaging system; if the same business task is re-sent as another message, the message ID can change. If idempotency is needed, design a separate stable business key.

## 4. BytesMessage Read/Write API

Create an empty message:

```java
BytesMessage message = session.createBytesMessage();
```

Here `session` is a `jakarta.jms.Session` provided by an active JMS provider and connection. The illustrative snippet **requires a JMS environment**, not a Java program compiled with just `javac`.

### 4.1. Writing Raw Bytes

```java
byte[] payload = new byte[] {
        (byte) 0xCA, (byte) 0xFE, 0x01, 0x02, 0x03
};

BytesMessage message = session.createBytesMessage();
message.writeBytes(payload);
message.setStringProperty("contentType", "application/octet-stream");
message.setIntProperty("schemaVersion", 1);

producer.send(message);
```

`producer` is a `jakarta.jms.MessageProducer` bound to the destination, or called via `send(destination, message)` depending on how it was created. The statements above only illustrate creation/sending inside an application that already has a connection, session, and broker. `writeBytes(byte[])` copies bytes into the body; **it does not turn the array into Java object serialization**.

There is an overload:

```java
message.writeBytes(payload, 1, 3); // Write 3 bytes starting at offset 1: FE 01 02
```

Check the offset, length, and body limit before sending; do not send array slices outside the payload.

### 4.2. Writing Primitive Values Sequentially

`BytesMessage` also provides typed pairs:

| Write | Corresponding read | Meaning |
| --- | --- | --- |
| `writeBoolean(boolean)` | `readBoolean()` | Boolean value |
| `writeByte(byte)` | `readByte()` / `readUnsignedByte()` | Signed or unsigned byte on read |
| `writeShort(short)` | `readShort()` / `readUnsignedShort()` | 16-bit value |
| `writeChar(char)` | `readChar()` | One Java `char` |
| `writeInt(int)` | `readInt()` | 32-bit value |
| `writeLong(long)` | `readLong()` | 64-bit value |
| `writeFloat(float)` | `readFloat()` | 32-bit floating-point |
| `writeDouble(double)` | `readDouble()` | 64-bit floating-point |
| `writeUTF(String)` | `readUTF()` | String in the method's **modified UTF-8** |
| `writeBytes(byte[])` | `readBytes(byte[])` | Raw byte array, without field names |

Example:

```java
BytesMessage m = session.createBytesMessage();
m.writeInt(42);
m.writeBoolean(true);
m.writeUTF("DONE");
```

The consumer must read in the exact **order and types**: `readInt()` → `readBoolean()` → `readUTF()`. If the sender changes the order without updating the contract, all bytes still arrive, but the decoder may misinterpret them or throw an exception.

**Specifically:** `writeUTF()` / `readUTF()` uses a *modified UTF-8* variant with API-specific length framing; it is **not equivalent** to `writeBytes(text.getBytes(StandardCharsets.UTF_8))`. When integrating with Python, Go, or a protocol specifying "raw UTF-8", encode explicitly using `StandardCharsets.UTF_8` and define the length yourself. Do not treat `writeUTF` as an arbitrary UTF-8 codec.

### 4.3. The Body Has Write-Only and Read-Only States

This is a critical difference compared to reading a plain `byte[]`.

```text
createBytesMessage()
        |
        v
 [ WRITE-ONLY ] -- writeBytes/writeInt/... --> [ WRITE-ONLY ]
        |
        | reset()
        v
 [ READ-ONLY; cursor = 0 ] -- readBytes/readInt/... --> [ READ-ONLY ]
        |
        | reset(): cursor returns to 0
        +-----------------------------------> [ READ-ONLY ]
        |
        | clearBody(): clears body
        v
 [ WRITE-ONLY; empty body ]
```

- A newly created message starts in **write-only** mode. Writing works, but attempting to read the body before `reset()` throws `MessageNotReadableException`.
- `reset()` switches the body to **read-only** and places the read position at the **beginning of the byte stream**. It does not delete data, does not create a new message, and is not an "acknowledgment".
- A message received from the provider is already in **read-only** mode with the cursor at the start. Listeners usually read right away and **do not need to call `reset()` initially**.
- Attempting to write to a read-only body throws `MessageNotWriteableException`.
- `clearBody()` **deletes the entire body** and returns it to write-only mode. This method **does not clear headers or properties**; clearing properties uses `clearProperties()`, which has a different purpose.
- When you need to re-read from the start of a `BytesMessage` still in scope, `reset()` sets the cursor back to 0. This is a client-side operation on the message object and does not ask the broker to re-send.

Do not use `clearBody()` to "reset the cursor for re-reading": it destroys the body. Do not use `reset()` to try to re-open write access: it sets read-only mode.

### 4.4. Reading BytesMessage with readBytes

On a **received** (read-only) message:

```java
long n = message.getBodyLength();
if (n < 0 || n > 1_048_576) {
    throw new IllegalArgumentException("Unexpected body size: " + n);
}

byte[] data = new byte[(int) n];
int total = 0;
while (total < data.length) {
    byte[] chunk = new byte[Math.min(8192, data.length - total)];
    int count = message.readBytes(chunk);
    if (count < 0) {
        throw new IllegalStateException("Truncated BytesMessage");
    }
    System.arraycopy(chunk, 0, data, total, count);
    total += count;
}
```

Here `message` is a `BytesMessage` received from the broker; the 1 MiB limit in the example **merely illustrates how to reject unexpected payloads**. The array is allocated from `getBodyLength()` after checking the limit; the method returns `long`, so do not cast `long` to `int` before checking. In practice, the read loop needs a guard if a provider abnormally returns 0 repeatedly; a production consumer must also enforce time limits and an error strategy.

`readBytes(buffer)` returns the **number of bytes actually copied**, not the buffer length; at the end of the stream, it returns **-1**. If fewer bytes remain than the buffer size, only the beginning of the buffer is updated. Always handle the exact returned byte count. Once `readBytes` advances the cursor, subsequent reads begin from the new position.

For small payloads when a convenient API is preferred, there is an alternative:

```java
byte[] data = message.getBody(byte[].class);
```

JMS/Jakarta Messaging supports `Message.getBody(byte[].class)` to retrieve the entire body of a `BytesMessage` without downcasting to `BytesMessage` in appropriate cases. This option **allocates an array holding the entire body**, so you still must control size and memory cost. If the byte format must be preserved for another system, do not arbitrarily convert the body into a `String` just for logging.

### 4.5. What Errors Can Occur When Reading Primitives?

- `MessageNotReadableException`: reading while the body is write-only.
- `MessageNotWriteableException`: writing while the body is read-only.
- `MessageEOFException`: attempting to read primitive data past the end of the stream.
- `MessageFormatException`: reading with the wrong format/type or content violating decode rules of the called method.
- `JMSException`: provider or JMS operation error; inspect cause and retry policy.

Not every error should be retried indefinitely. A repeatedly malformed payload is typically a **poison message**; classify by root cause, log appropriate metadata, and apply broker retry/dead-letter policies.

## 5. A Binary Contract Must Specify "Which Byte Means What"

If two services define a custom binary frame, the format specification must at minimum lock down:

1. **Magic/version:** how to detect the right format and evolve versions.
2. **Length:** number of bytes, offset, and numeric type of the length field; maximum accepted limit.
3. **Byte order:** big-endian/little-endian for multi-byte numbers.
4. **Charset:** UTF-8, UTF-16, or no text; never infer from the OS default charset.
5. **Framing:** positions of header, payload, checksum, signature, extensions.
6. **Compression/encryption:** algorithm, order of operations, key retrieval, and error handling.
7. **Compatibility:** whether unknown fields may be ignored, which fields are required, how old schemas are recognized.
8. **Limits:** message size, decompressed size, nesting depth, total records; data access permissions.

Suppose an illustrative format:

| Byte offset | Length | Meaning |
| --- | --- | --- |
| `0..1` | 2 | Magic `0xCAFE`, big-endian |
| `2` | 1 | Version, value `1` |
| `3..6` | 4 | Payload length, signed 32-bit integer, big-endian; must be non-negative |
| `7..` | Per length | UTF-8 payload in the demo; in real systems, may be schema-defined binary |

For the payload "HELLO" (5 ASCII bytes, which is also UTF-8), the frame is:

```text
CA FE | 01 | 00 00 00 05 | 48 45 4C 4C 4F
magic | ver| payload len | H  E  L  L  O
```

Total length is **12 bytes**. This is **a custom sample format**, not a mandatory `BytesMessage` structure. `BytesMessage` itself **does not automatically prepend magic, version, or length as in the table**; the producer must write them and the consumer must parse them if agreed upon.

## 6. Standalone Java 17 Example: Encoding and Decoding a Binary Frame

This example uses pure Java I/O so you can verify the **body format** before introducing JMS. It **does not start a broker or create a BytesMessage**, and produces deterministic output for verification. When moving into JMS, you can send the entire `frame` with `writeBytes(frame)`.

Create the file **`BinaryFrameDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class BinaryFrameDemo {
    private static final int MAGIC = 0xCAFE;
    private static final int VERSION = 1;
    private static final int MAX_BODY_BYTES = 1024;

    public static void main(String[] args) throws IOException {
        byte[] payload = "HELLO".getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeShort(MAGIC);           // 2 bytes, big-endian
            out.writeByte(VERSION);          // 1 byte
            out.writeInt(payload.length);   // 4 bytes, big-endian
            out.write(payload);             // payload bytes
        }

        byte[] frame = buffer.toByteArray();

        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(frame))) {

            int magic = in.readUnsignedShort();
            int version = in.readUnsignedByte();
            int length = in.readInt();

            if (magic != MAGIC || version != VERSION) {
                throw new IOException("Unsupported frame");
            }
            if (length < 0 || length > MAX_BODY_BYTES) {
                throw new IOException("Invalid payload length");
            }

            byte[] decoded = in.readNBytes(length);
            if (decoded.length != length || in.read() != -1) {
                throw new IOException("Truncated or trailing frame");
            }

            System.out.printf("Magic: %04X%n", magic);
            System.out.println("Version: " + version);
            System.out.println("Payload length: " + decoded.length);
            System.out.println("Payload: " +
                    new String(decoded, StandardCharsets.UTF_8));
            System.out.println("Frame bytes: " + frame.length);
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac BinaryFrameDemo.java
java BinaryFrameDemo
```

Exact output:

```text
Magic: CAFE
Version: 1
Payload length: 5
Payload: HELLO
Frame bytes: 12
```

Key points to understand:

- `DataOutputStream`/`DataInputStream` are paired in this code to define write/read order. Choosing **big-endian** is part of the demo contract, independent of the host machine.
- `readUnsignedShort()` reads the magic unsigned; if `readShort()` were called, `0xCAFE` would be represented as a negative number, even though the two bytes are unchanged.
- `readNBytes(length)` returns the bytes read; the program **checks both sufficient length and no trailing bytes** to avoid accepting malformed frames.
- `MAX_BODY_BYTES` blocks an oversized declared length before allocation. When parsing from untrusted sources, do not immediately allocate `new byte[length]` right after reading the length.
- If the payload is PNG or protobuf, the code must pass `decoded` to the corresponding codec; do **not** assume `new String(...)` for non-text data.

**Note on sample scope:** this demo only illustrates a small frame already in RAM. It does not replace checksum/authentication verification, file chunking, or schema evolution in a real system.

## 7. Integrating with Spring JMS

Spring Framework 6+ provides `JmsTemplate` for sending and `@JmsListener` for receiving. You need a compatible JMS provider, a `jakarta.jms.ConnectionFactory`, destination configuration, and Spring JMS dependencies. The following examples are **classes belonging to the same Spring application**; each file cannot be run with `javac` alone because of framework dependencies and the broker.

There are two approaches:

- **Manually create `BytesMessage`** when you need control over properties and how bytes are written: `JmsTemplate.send(destination, session -> session.createBytesMessage())`.
- **Use conversion** when you only have `byte[]`: `JmsTemplate.convertAndSend(destination, byte[])`. With the default `SimpleMessageConverter`, Spring converts `byte[]` to `BytesMessage`; on the receiving side it can convert back to `byte[]`.

### 7.1. Configuring a Listener with Local JMS Transaction

**File `BinaryJmsConfig.java`:**

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class BinaryJmsConfig {

    @Bean(name = "binaryListenerFactory")
    public DefaultJmsListenerContainerFactory binaryListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        return factory;
    }
}
```

The example uses a **queue** named `binary.jobs` (Spring JMS defaults to queues when pub/sub is not enabled). `setSessionTransacted(true)` makes the listener container use a local JMS transaction to commit/roll back message receipt. It **does not automatically combine** the JMS transaction with a database transaction or external side effects. If processing fails, redelivery behavior, retry counts, and dead-letter handling depend on the provider and application configuration.

### 7.2. Producer Manually Creating BytesMessage

**File `BinaryJobPublisher.java`:**

```java
import jakarta.jms.BytesMessage;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

import java.util.Objects;

@Service
public class BinaryJobPublisher {
    private static final int MAX_BYTES = 1_048_576;

    private final JmsTemplate jmsTemplate;

    public BinaryJobPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(byte[] payload, String jobId) {
        Objects.requireNonNull(payload, "payload");
        if (jobId == null || jobId.isBlank()) {
            throw new IllegalArgumentException("jobId is required");
        }
        if (payload.length > MAX_BYTES) {
            throw new IllegalArgumentException("Payload too large");
        }

        jmsTemplate.send("binary.jobs", session -> {
            BytesMessage message = session.createBytesMessage();
            message.writeBytes(payload);
            message.setStringProperty(
                    "contentType", "application/octet-stream");
            message.setIntProperty("schemaVersion", 1);
            message.setStringProperty("jobId", jobId);
            return message;
        });
    }
}
```

`publish` only succeeds in completing the send operation per the JMS/provider contract. It **does not prove that a consumer has finished processing the job**. In production, decide TTL, delivery mode, and atomicity between DB updates and JMS sends according to business needs. Do not put secrets into properties or logs.

Here `payload` consists of bytes of an agreed format. If you need to send the exact "CA FE ..." frame from section 6, the producer passes the **`frame` array** built by the codec; `writeBytes` preserves the bytes as-is. Setting `schemaVersion=1` on the producer side is only useful if the consumer checks and understands the corresponding schema.

### 7.3. Listener Receiving BytesMessage Directly

**File `BinaryJobListener.java`:**

```java
import jakarta.jms.BytesMessage;
import jakarta.jms.JMSException;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class BinaryJobListener {
    private static final long MAX_BYTES = 1_048_576L;

    @JmsListener(
            destination = "binary.jobs",
            containerFactory = "binaryListenerFactory")
    public void onBinaryJob(BytesMessage message) throws JMSException {
        String type = message.getStringProperty("contentType");
        int version = message.getIntProperty("schemaVersion");
        String jobId = message.getStringProperty("jobId");

        if (!"application/octet-stream".equals(type) || version != 1) {
            throw new IllegalArgumentException("Unknown binary schema");
        }
        if (jobId == null || jobId.isBlank()) {
            throw new IllegalArgumentException("Missing jobId");
        }

        long length = message.getBodyLength();
        if (length < 0 || length > MAX_BYTES) {
            throw new IllegalArgumentException("Invalid body length");
        }

        byte[] body = message.getBody(byte[].class);
        if (body.length != length) {
            throw new IllegalStateException("Body length mismatch");
        }

        // In a real application, pass body to a validated business codec.
        System.out.println(
                "Received " + body.length + " bytes for job " + jobId);
    }
}
```

Spring allows a `@JmsListener` method to receive a raw `jakarta.jms.Message` or an appropriate subtype such as `BytesMessage`. By receiving the raw message, the listener checks size and metadata **before extracting the body into an array**. This illustrates rejecting small payloads; for untrusted binary data, you must also validate the **internal format of the body**.

If you call `publish(new byte[] {1, 2, 3}, "job-42")` and the broker, queue, and listener are all working properly, a successful run may print:

```text
Received 3 bytes for job job-42
```

This output is **conditional**, not a guaranteed result on every startup: it still depends on connection, transaction, delivery, broker state, retries, and consumer behavior. Do not infer "exactly once" from logs.

### 7.4. Concise Approach Using JmsTemplate Conversion

With the default `SimpleMessageConverter` and when only a binary body is needed:

```java
byte[] bytes = new byte[] {1, 2, 3, 4};
jmsTemplate.convertAndSend("binary.jobs", bytes);
```

Spring creates a `BytesMessage` from `byte[]`. A listener can receive the converted payload:

```java
@JmsListener(destination = "binary.jobs",
             containerFactory = "binaryListenerFactory")
public void receive(byte[] bytes) {
    System.out.println("Received " + bytes.length + " bytes");
}
```

**These two approaches are mutually exclusive alternatives**, and must not be registered in parallel on the same queue if you want a single consumer to observe all messages: competing listeners on a queue split messages among themselves. With automatic `byte[]` conversion, the converter can read the entire body to construct the array before the method runs, so it is unsuitable when you need to check size on the raw message **before allocating**. If your application uses a custom `MessageConverter`, verify the mapping again.

## 8. Chunked Reading: When Should You Use It?

With a received `BytesMessage`, `getBodyLength()` returns `long`, and `readBytes(buffer)` allows reading in chunks:

```java
byte[] buffer = new byte[8192];
int count;
while ((count = message.readBytes(buffer)) != -1) {
    if (count == 0) {
        throw new IllegalStateException("No forward progress");
    }
    // Only process buffer[0..count), do not use the entire buffer.
}
```

This snippet is a **handler pattern inside a listener**: `message` must be in read-only state and, depending on the codec, the comment logic must be replaced with real processing. The code is not standalone; it is solely an API pattern explaining the cursor.

Before the loop, enforce a threshold from `getBodyLength()` and track total bytes read. Piping chunks into a controlled `OutputStream` can avoid **making another full-body copy at the application layer**. However, the JMS provider may still buffer the whole message or enforce other broker limits; do **not** assume end-to-end streaming merely from a `readBytes()` loop.

Use `getBody(byte[].class)` when the payload is small, trusted, and simplicity is desired. Use bounded `readBytes()` when you need control over reading or want to avoid allocating one very large array. For large files, consider object storage with a message carrying a reference.

## 9. Important Design Issues for Binary Content

### 9.1. Charset and Binary Are Not the Same Thing

- `byte[]` does not carry a charset.
- `new String(bytes)` uses the default charset if none is specified; it can corrupt data into the wrong string.
- Converting text to bytes should use `text.getBytes(StandardCharsets.UTF_8)`; converting back should use `new String(bytes, StandardCharsets.UTF_8)` **only when you are certain the body is UTF-8**.
- For PNG/PDF/protobuf payloads, do not apply a text decoder to "peek" and re-send; doing so can alter the data.
- Base64 encodes bytes into characters for transport over text channels, at the cost of increased size. If JMS already uses `BytesMessage`, there is no need for Base64 **just to send a byte array**.

### 9.2. Byte Order and Parsing Primitives

In custom-defined frames, producer and consumer must agree on big-endian or little-endian. Java's `DataOutputStream`/`DataInputStream` is a convenient pair for demonstrating big-endian; clients in other languages must read using that exact byte order.

Do not mix them inadvertently:

```text
writeInt(0x01020304) -> 01 02 03 04  (big-endian per demo)
raw byte sequence   -> 04 03 02 01  (different little-endian)
```

A decoder written for little-endian can misread lengths, fail, or request abnormal memory allocations. Therefore, check magic, version, and max length **before** reading/allocating the payload.

### 9.3. Evolving Schemas Without Breaking Old Consumers

Binary data is hard to inspect visually, making versioning and clear documentation even more vital. For example, v1 uses the frame `magic + version + length + bytes`. If v2 adds a compression flag, you can:

- Define a new version and an explicit v2 decoder.
- Keep a v1-compatible reader during a transition period.
- Never reuse version 1 for a new layout that old decoders do not understand.
- Maintain test suites with "golden bytes" files for each version, language, and broker/provider to support.
- Attach schema ID/version in properties if selectors or management tools use them, but do not rely solely on an unverified property.

For protobuf/Avro, **`BytesMessage` only transports bytes**; compatibility rules live in the application's schema registry/codec, not in JMS itself.

### 9.4. Compression, Encryption, and Data Integrity

Compressing before sending can reduce bytes on the wire at the cost of CPU, latency, and **decompression bomb** risks. A declared `compressedSize` field may be small while the decompressed output is huge; enforce thresholds on both *encoded size* and *decoded size*.

TLS and broker authentication protect the transport channel as configured. If end-to-end encryption or message-level signatures are needed, design keys, versions, and verification separately; do not assume `BytesMessage` encrypts payloads automatically.

Checksums detect accidental corruption but do not replace signatures or MACs against tampering when data crosses trust boundaries. Do not log binary payloads containing PII/secrets; log sufficient metadata for tracing (message ID, job ID, content type, size, schema, controlled hash).

### 9.5. Never Perform Dangerous Operations on Untrusted Data

Even when a valid body arrives through the broker, the consumer must treat the data source as **untrusted input** at the business boundary:

1. Validate message size and decompressed size.
2. Validate schema, version, magic, length, and checksum/signature as required.
3. Use safe parsers; limit nesting depth, field counts, and element counts.
4. Never automatically Java-deserialize payload bytes into arbitrary objects.
5. If receiving filenames/paths, never concatenate them directly into filesystem paths; validate and normalize per application rules.
6. Classify permanent data errors to avoid infinite retries on the same poison message.
7. Route failed messages to DLQ/quarantine per broker policy for controlled investigation.

### 9.6. Reliability, Acknowledgment, and Duplicate Handling

`BytesMessage` **carries no special reliability mechanism** distinct from other JMS message types. `PERSISTENT`/`NON_PERSISTENT`, queue/topic, transactions, TTL, acknowledgment, retries, and dead-lettering are all design axes independent of body format.

For instance, an image-processing message is received by a consumer, the thumbnail is saved successfully, and then the JVM crashes **before the JMS transaction commits**. The broker may redeliver the message. If the consumer creates a new file on every delivery, duplicates can occur. Use a stable business ID to check idempotency, write results under a unique key, or persist processing state and business effects in an appropriate transaction.

Enabling `setSessionTransacted(true)` does not merge a database transaction and a JMS transaction into one; you still must design for consistency when one step succeeds and the other fails.

## 10. BytesMessage Testing Process

To separate encoding bugs from broker bugs, test from small to large.

### Test A — Pure Codec Round-Trip

1. Run `BinaryFrameDemo`; verify the frame is 12 bytes long and payload is "HELLO".
2. Add test cases: empty payload, payload containing `0x00`, `0xFF`, and UTF-8 encoded Vietnamese characters.
3. Change one magic or version byte: the decoder must reject it.
4. Change length to negative, too large, smaller, or larger than the actual byte count: the decoder must reject it.
5. Pass a golden frame between the Java codec and another language client if the system is polyglot.

### Test B — JMS Round-Trip

1. Start the provider and create the `binary.jobs` queue.
2. Send `byte[]` with `convertAndSend` and verify the consumer receives the exact byte-for-byte values.
3. Use a `send` producer with `BytesMessage` to add `contentType`/`schemaVersion`/`jobId`; have the consumer verify properties and body.
4. Send a message with an invalid `schemaVersion` and test an oversized payload; confirm the listener intentionally rejects them.
5. Observe transaction/ack configuration and DLQ behavior when the decoder throws an exception.

### Test C — Operational Failures

- Consumer paused while producer keeps sending: observe queued message count; verify TTL and delivery mode suit requirements.
- Consumer crashes after executing side effects but before ack: verify idempotency on the same job ID.
- Broker receives large messages: monitor producer/broker limits, heap, network, and backlog; verify "message too large" behavior.
- Verify failing messages do not retry forever, and that the DLQ retains enough metadata to investigate without exposing sensitive payloads.

### Metrics Worth Observing

| Metric / signal | Meaning |
| --- | --- |
| Body bytes by type/version | Detect abnormal payload size growth |
| Queue backlog and message age | Consumer falling behind or stopped |
| Parse/schema error rate | Producer and consumer incompatibility |
| Retry/redelivery count | Logic bugs, resource exhaustion, or unstable side effects |
| DLQ count | Messages unprocessable after retry policy |
| Processing latency | Delay from broker delivery to business completion |

Do not log full bodies to production logs just for easy debugging; data can be large, unreadable, and contain information requiring protection.

## 11. Common Mistakes and Fixes

**"BytesMessage is file upload."** False. It is a JMS message body type. Large files should usually be stored outside the broker, sending only a reference with metadata/access policy.

**"writeBytes automatically writes length and schema."** False. It writes the supplied bytes; if the format needs length/version, the application must define and encode them.

**"After creating a message, you can call readBytes immediately."** False. A new message is write-only. You must call `reset()` to switch to read-only, or read a message received from the provider which is already read-only.

**"reset() deletes the body."** False. `reset()` resets the read position and switches to read-only. `clearBody()` is what deletes the body for rewriting.

**"getBodyLength() returns int."** False. It returns `long`; array allocation must check bounds before casting to `int`.

**"readBytes(buffer) always fills the buffer."** False. The method returns the number of bytes copied; it may be smaller than the buffer and returns -1 at end of stream.

**"writeUTF equals raw file UTF-8."** False. `writeUTF/readUTF` uses the API's modified UTF-8; when an external format requires UTF-8 bytes, use `StandardCharsets.UTF_8` and an explicit length convention.

**"Just setting contentType lets any consumer decode it."** False. A property is metadata; the consumer still needs the matching codec/schema and actual data validation.

**"Once a converter turns it into byte[], no extra memory is used."** False. Converting `BytesMessage` to `byte[]` usually allocates the entire body. Enforce size limits on the raw message or choose an appropriate file transfer mechanism.

**"BytesMessage eliminates duplicate deliveries."** False. Format does not control delivery/ack; proper idempotency and transaction scoping are still required.

**"Binary bytes can be printed as a String for inspection without harm."** Not recommended. Decoding with the wrong charset can lose information if re-encoded, and logging raw binary can leak data.

## 12. Self-Check Knowledge Quiz

**Question 1.** In `BytesMessage`, does `writeBytes(new byte[]{0x01, 0x02})` automatically add JSON field names or payload length?

**Answer:** No. It writes the exact bytes of the array. If the contract needs headers/length, the producer must encode them separately.

**Question 2.** Immediately after `session.createBytesMessage()`, is calling `getBodyLength()` valid?

**Answer:** No, while the body is still write-only. `getBodyLength()` requires read-only state; you can call `reset()` after writing, or call it on a received message.

**Question 3.** What is the difference between `reset()` and `clearBody()`?

**Answer:** `reset()` switches to read-only, sets the cursor to the start, and preserves the body. `clearBody()` clears the body, switches to write-only, and keeps properties intact.

**Question 4.** You call `readBytes(buffer)` with an 8-byte buffer when only 3 bytes remain; how must you handle it?

**Answer:** Based on the returned byte count (3), use only `buffer[0..3)`. A subsequent read at end of stream returns -1; do not treat the remaining buffer slots as new data.

**Question 5.** A frame has a 2-byte magic, 1-byte version, 4-byte length, and 5-byte payload. How many total bytes is the body?

**Answer:** 12 bytes, strictly per the application-defined format; not automatic JMS overhead.

**Question 6.** Why should `schemaVersion` be included when using protobuf or custom binary?

**Answer:** The decoder needs to know how to interpret the layout and handle version compatibility; `BytesMessage` itself carries no business schema.

**Question 7.** What message type does Spring's `JmsTemplate.convertAndSend("binary.jobs", byte[])` normally create with the default converter?

**Answer:** `BytesMessage` via `SimpleMessageConverter`. If the converter is replaced with a custom implementation, verify again.

**Question 8.** A sent message is 200 MiB, while the listener accepts `byte[]` and then checks "length must be under 1 MiB". Does this check prevent large converter allocation?

**Answer:** Not reliably. The converter may allocate the 200 MiB array **before** entering the method. For size limits, enforce them at the broker/client and/or accept raw `BytesMessage`, checking `getBodyLength()` before reading the entire body; consider object storage references.

**Question 9.** A consumer persists binary data successfully and crashes before JMS ack; can the message come back?

**Answer:** Yes. This is an acknowledgment/transaction concern, independent of format; idempotency keyed by a stable business key is required.

## Key Takeaway

`BytesMessage` is **a stream of bytes that does not self-describe business semantics**. Use it when producer and consumer share an explicit contract on the binary format. Distinguish write-only/read-only states, read the exact returned byte count, enforce size bounds before allocation, and document and test schema/version/charset/byte order. In Spring JMS, `JmsTemplate` and `@JmsListener` simplify sending and receiving, while ultimate reliability still depends on the broker, transactions, retries, and deduplication logic.

### Official References

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): `BytesMessage`, message body, send/receive, and `createBytesMessage/writeBytes/readBytes/getBody` examples.
- [Jakarta Messaging BytesMessage API](https://jakarta.ee/specifications/messaging/3.0/apidocs/jakarta/jms/BytesMessage.html): read-only/write-only states, `reset`, `clearBody`, primitive readers/writers, and exceptions.
- [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html): `JmsTemplate` and `SimpleMessageConverter` for `byte[]`/`BytesMessage`.
- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@JmsListener`, raw JMS message parameters, and listener factories.
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): listener containers and message processing.