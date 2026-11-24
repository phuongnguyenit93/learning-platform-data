# content-type, content-length, and binary data in STOMP

## 1. Why does STOMP need these two headers?

STOMP is a frame-based messaging protocol. A frame has a command, headers, a blank line separating the headers from the body, and an optional body section. The SEND, MESSAGE, and ERROR commands can carry a body; the remaining commands do not have a body.

The two headers describe two different aspects of the body:

- **content-type** indicates the format or content type of the body, as a MIME type. The receiver uses this information to choose how to decode or convert the payload.
- **content-length** indicates the exact number of octets (bytes) in the body. The decoder uses this value to determine where the body ends.

STOMP was originally designed with text-oriented frames, but the body can be binary data. Therefore, you must not assume the body is always a UTF-8 string or that you can find the end by converting the whole body into a String.

These two headers do not replace each other. content-type does not tell you the length of the body; content-length does not tell you whether the body is JSON, text, an image, or binary data.

## 2. Frame structure and body position

STOMP frame structure:

~~~text
COMMAND
header-name:header-value
header-name:header-value

body bytes
NULL
~~~

Parts:

1. Command is on the first line, for example SEND or MESSAGE.
2. Each header is on its own line in the form name:value.
3. A blank line ends the header section.
4. The body begins immediately after the blank line.
5. The frame ends with a NULL octet with the value 0x00.

STOMP 1.2 uses UTF-8 by default for the command and headers. The body can be text or arbitrary bytes. The NULL mark at the end of the frame is a protocol delimiter byte, not implicitly part of the body.

Example of a text frame:

~~~text
SEND
destination:/queue/orders
content-type:text/plain;charset=utf-8
content-length:8

Xin chào
^@
~~~

In this example, the body is UTF-8 encoded. The ^@ line only represents the NULL octet that terminates the frame; it is not the two characters caret and @ being sent.

## 3. content-type: describing the MIME type of the body

content-type is an optional header, but it should be present when the frame carries a body. Its value must be a MIME type that describes the format of the body.

Some commonly used values:

| content-type | Content | Typical handling |
| --- | --- | --- |
| text/plain;charset=utf-8 | UTF-8 text | Decode to String |
| application/json | JSON | Parse into a DTO or JSON structure |
| application/xml;charset=utf-8 | UTF-8 XML | Parse XML |
| application/octet-stream | Generic bytes | Keep payload as byte[] |
| image/png | PNG image | Keep byte[] or pass to an image processor |
| application/pdf | PDF file | Keep byte[] or pass to a PDF processor |

If the MIME type begins with text/, STOMP 1.2 implies UTF-8 by default. If you use a different text encoding, declare the charset, for example text/plain;charset=utf-16.

Some MIME types do not begin with text/ yet still contain textual data, such as application/xml. When an explicit encoding is needed, declare the corresponding charset, for instance application/xml;charset=utf-8.

If the body has a content-type, the receiver uses that MIME type to understand the content. If the body has no content-type, according to STOMP 1.2 the receiver should treat the body as a binary blob. Therefore, do not rely on guessing that a body without a header is definitely UTF-8 text.

### 3.1. content-type does not validate the content

The content-type header is only metadata supplied by the sender. It does not prove that the body actually matches the declared format.

For example, a client can send content-type:image/png while the body contains another file. The server needs to check the size, format signature (magic bytes), structure, and business rules before storing or processing the data.

Do not use the MIME type as a security boundary, and do not automatically trust a file name sent by the client.

## 4. content-length: length measured in octets

content-length is the number of octets in the body. One octet corresponds to one 8-bit byte. This value does not count:

- The command and headers.
- The blank line separating the headers from the body.
- The NULL octet that terminates the frame.
- Bytes belonging to the next frame.

Example:

~~~text
SEND
destination:/queue/binary
content-type:application/octet-stream
content-length:4

[0x41 0x00 0xFF 0x42]
[frame terminator: 0x00]
~~~

The body has exactly four bytes: 0x41, 0x00, 0xFF, and 0x42. The NULL octet at the end of the frame is the fifth byte after the body, and is not counted in content-length.

If content-length is present, the receiver must read exactly the declared number of octets, regardless of whether the body contains NULL bytes. After that number of bytes, the frame must still have the terminating NULL octet.

### 4.1. When is content-length mandatory?

According to STOMP 1.2:

- SEND, MESSAGE, and ERROR should include content-length when a body exists to make frame parsing easier.
- If the body contains any NULL octet, the frame must have content-length.
- If content-length is declared, the decoder must read exactly that number of octets before checking for the frame-terminating NULL byte.

Therefore, for arbitrary binary data, always send content-length. Binary data can contain 0x00 at any position; without a length, the decoder can mistake that byte for the end of the body and truncate the rest.

## 5. Distinguishing character count from byte count

This is a common mistake when sending accented text or non-ASCII characters.

In Java:

- String.length() counts UTF-16 code units.
- codePointCount() counts Unicode code points.
- content-length needs the actual number of bytes after encoding the body.

For example, the string Xin chào has 8 UTF-16 code units, but needs 9 bytes when encoded in UTF-8 because the character à takes two bytes.

~~~java
String body = "Xin chào";
byte[] bytes = body.getBytes(StandardCharsets.UTF_8);

System.out.println("textChars=" + body.length());
System.out.println("utf8Bytes=" + bytes.length);
~~~

Stdout:

~~~text
textChars=8
utf8Bytes=9
~~~

When building a STOMP frame by hand, calculate the length from the encoded byte array:

~~~java
byte[] body = text.getBytes(StandardCharsets.UTF_8);
int contentLength = body.length;
~~~

Do not use text.length() to fill in content-length. For images, PDFs, protobuf, or compressed data, take the length directly from the byte array.

## 6. How the decoder delimits the body

There are two cases:

### 6.1. Frames with content-length

Suppose the header says content-length:4. The decoder reads exactly four octets of body. If the second byte is 0x00, the decoder still keeps it in the body because the length already determines the ending position.

After four bytes, the decoder requires the frame-terminating NULL octet. If the terminating byte is absent or the frame is cut off partway through, the frame is incomplete and the decoder needs more data.

### 6.2. Frames without content-length

If there is no content-length, the decoder looks for the first NULL octet after the body starts to determine the ending point.

This approach works for text bodies that do not contain NULL. It is unsafe for arbitrary binary data because a 0x00 byte can be part of the data.

### 6.3. Consequences of declaring the wrong length

| Mistake | Possible consequence |
| --- | --- |
| content-length smaller than the real body | The extra bytes may be mistaken for the next frame or cause a parse error |
| content-length larger than the real body | The decoder keeps waiting for the missing bytes; the frame hangs or times out |
| Omitting content-length when the body has 0x00 | The body is truncated at the first NULL byte |
| Counting by characters instead of bytes | Unicode text is read with too few or too many bytes |
| Counting the frame-terminating NULL byte as well | The decoder waits for one more terminator byte and does not complete the frame |

You should not fix the mistake by trimming the payload or dropping NULL bytes. Fix the byte length calculation and how the frame is built on the sender.

## 7. Binary data in STOMP

STOMP 1.2 allows the body to be an arbitrary sequence of octets. This enables the protocol to carry:

- Images, audio, and video.
- PDFs, ZIPs, and attachments.
- Protobuf data or custom binary formats.
- Compressed or encrypted data blocks.
- Payloads containing NULL bytes and values that are invalid if interpreted as UTF-8.

Example of a four-byte body:

~~~text
0x41 0x00 0xFF 0x42
~~~

You cannot accurately represent this entire body with an ordinary UTF-8 String without additional encode/decode rules. Keep the byte[] intact at the transport layer and convert only when you know the exact format.

### 7.1. Do not convert binary to Base64 unless needed

You can encode binary to Base64 and send it as text/plain or application/json. That approach is useful when an intermediary system supports only text, but the data size increases by roughly one-third and an extra encode/decode step is needed.

If the client, broker, and server all support binary bodies, sending byte[] directly with application/octet-stream and content-length is more efficient.

### 7.2. Do not confuse a WebSocket binary frame with a STOMP body

WebSocket has text frames and binary frames. STOMP is a sub-protocol packaged inside a WebSocket message. A STOMP frame still has a command and headers; its body can be binary bytes.

At the Spring layer, StompSubProtocolHandler can receive a WebSocket TextMessage or BinaryMessage and then pass the data to the STOMP decoder. Therefore, the application should not drop STOMP headers on its own just because the transport uses a binary WebSocket frame.

## 8. Java 17+ example: creating a STOMP frame with a NULL byte

The following example uses standard Java to create a SEND frame containing four binary bytes. This is a standalone program that illustrates how to package the frame; it does not open a socket or send data to a broker.

**StompBinaryFrameDemo.java**

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

public class StompBinaryFrameDemo {

    public static void main(String[] args) {
        String text = "Xin chào";
        byte[] textBytes = text.getBytes(StandardCharsets.UTF_8);

        byte[] payload = {
            (byte) 0x41,
            (byte) 0x00,
            (byte) 0xFF,
            (byte) 0x42
        };

        String headers =
            "SEND\n" +
            "destination:/queue/binary\n" +
            "content-type:application/octet-stream\n" +
            "content-length:" + payload.length + "\n" +
            "\n";

        ByteArrayOutputStream frame = new ByteArrayOutputStream();
        frame.writeBytes(headers.getBytes(StandardCharsets.UTF_8));
        frame.writeBytes(payload);
        frame.write(0);

        System.out.println("textChars=" + text.length());
        System.out.println("textUtf8Bytes=" + textBytes.length);
        System.out.println("payloadBytes=" + payload.length);
        System.out.println("frameBytes=" + frame.size());
        System.out.println("bodyContainsNul=" + (payload[1] == 0));
    }
}
~~~

Compile and run:

~~~bash
javac StompBinaryFrameDemo.java
java StompBinaryFrameDemo
~~~

Stdout:

~~~text
textChars=8
textUtf8Bytes=9
payloadBytes=4
frameBytes=92
bodyContainsNul=true
~~~

In the created frame:

- The header block takes 87 bytes.
- The body takes 4 bytes.
- The NULL byte at the end of the frame takes 1 byte.
- The total frame is 92 bytes.
- content-length writes only 4, not 5 or 92.

This example shows that content-length counts only the body. The header block and the frame terminator are outside the calculation.

## 9. Reading content-type and content-length in Spring

The Spring Framework provides StompHeaderAccessor to read and write STOMP headers in a safer way than accessing a Map directly.

Some APIs:

| API | Purpose |
| --- | --- |
| getContentType() | Reads the MIME type from the content-type header |
| setContentType(MimeType) | Writes content-type |
| getContentLength() | Reads content-length, returning Integer or null if absent |
| setContentLength(int) | Writes content-length |
| getFirstNativeHeader(name) | Reads the first value of a native STOMP header |
| setNativeHeader(name, value) | Writes a native STOMP header |

Example of reading metadata from a Spring Message:

~~~java
Message<byte[]> message = ...;

StompHeaderAccessor accessor = StompHeaderAccessor.wrap(message);

MimeType contentType = accessor.getContentType();
Integer contentLength = accessor.getContentLength();

byte[] body = message.getPayload();
~~~

StompHeaderAccessor keeps the native header information of the STOMP frame while also mapping content-type into Spring's MessageHeaders.CONTENT_TYPE.

If content-length is absent, getContentLength() returns null. Do not guess the length from content-type on your own; use body.length to know the size of the byte array created by the decoder.

## 10. Spring StompDecoder and the byte[] payload

StompDecoder takes data as a ByteBuffer and decodes it into a list of Spring Messages with a byte[] payload.

This is important because the decoder needs to preserve the body data intact before the business layer decides whether to convert it or not.

General process:

1. The WebSocket transport receives a text or binary frame.
2. StompSubProtocolHandler passes the data to a ByteBuffer.
3. BufferingStompDecoder accumulates data if the frame is not yet complete.
4. StompDecoder reads the command, headers, content-length, and body.
5. The decoder creates a Message<byte[]> together with native STOMP headers.
6. Spring routes the message to a controller or the broker.
7. If the controller requires another payload type, MessageConverter performs the conversion based on content-type and the target type.

If a frame is split across multiple receives, the decoder can return an empty list until enough data arrives. BufferingStompDecoder uses content-length when present to determine how much data is still missing and supports buffer size limits.

## 11. MessageConverter and content-type in Spring

Spring's MessageConverter converts the payload from serialized bytes into the Java type that the listener or controller requires, and vice versa.

Some commonly used converters:

| Converter | Payload type | Commonly used MIME type |
| --- | --- | --- |
| ByteArrayMessageConverter | byte[] | application/octet-stream |
| StringMessageConverter | String | text/plain |
| Jackson JSON converter | DTO/JSON object | application/json |
| Custom converter | Business type or custom binary | Application-defined MIME type |

The converter needs to support both the content-type and the target type. If there is no suitable converter, Spring may throw a MessageConversionException or a message processing error.

You should not ask Spring to convert application/octet-stream into a String. For binary, use byte[] or Message<byte[]> to keep the data intact.

## 12. Receiving binary in @MessageMapping

A controller can receive the whole Spring Message<byte[]> to inspect the headers and body itself:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Controller;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

@Controller
public class BinaryUploadController {

    private final BinaryStorage binaryStorage;

    public BinaryUploadController(BinaryStorage binaryStorage) {
        this.binaryStorage = binaryStorage;
    }

    @MessageMapping("/binary.upload")
    public void upload(Message<byte[]> message) {
        StompHeaderAccessor headers = StompHeaderAccessor.wrap(message);

        MimeType contentType = headers.getContentType();
        Integer declaredLength = headers.getContentLength();
        byte[] body = message.getPayload();

        if (!MimeTypeUtils.APPLICATION_OCTET_STREAM.equals(contentType)) {
            throw new IllegalArgumentException("Expected application/octet-stream");
        }

        if (declaredLength != null && declaredLength.intValue() != body.length) {
            throw new IllegalArgumentException("Unexpected binary payload length");
        }

        binaryStorage.store(body);
    }
}
~~~

BinaryStorage is a service provided by the application to check and store data. This example assumes that the service has already been registered as a Spring bean.

The client sends to the destination /app/binary.upload. Spring strips the /app prefix when mapping the destination to the @MessageMapping("/binary.upload") method.

When using Message<byte[]>, the controller directly accesses the byte[] payload and native STOMP headers. There is no step converting the payload into a String or DTO.

If you use a @Payload byte[] parameter instead of Message<byte[]>, make sure ByteArrayMessageConverter is registered and content-type is compatible with application/octet-stream.

## 13. Sending binary with the Spring STOMP client

Spring provides StompSession to send and receive STOMP messages. You can set destination and content-type and then send byte[]:

~~~java
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.util.MimeTypeUtils;

public void sendBinary(StompSession session, byte[] payload) {
    StompHeaders headers = new StompHeaders();
    headers.setDestination("/app/binary.upload");
    headers.setContentType(MimeTypeUtils.APPLICATION_OCTET_STREAM);

    session.send(headers, payload);
}
~~~

StompSession uses a MessageConverter to convert the payload into byte[] before the encoder builds the frame. For a byte[] payload, SimpleMessageConverter can keep the byte array as is; you can configure another converter if the application needs custom rules.

Spring's StompEncoder is responsible for encoding a Spring Message into a STOMP frame. When building a frame yourself with a byte array, the application must compute content-length accurately itself. When using Spring's client encoder, let the encoder create the framing from the converted payload and avoid computing the length using String.length().

## 14. Sending JSON and text with the right content-type

For JSON:

~~~text
SEND
destination:/app/orders.create
content-type:application/json
content-length:34

{"orderId":"A-100","priority":5}
^@
~~~

The JSON body must be encoded according to the charset agreed upon by both sides, usually UTF-8. content-length must equal the number of bytes after JSON encoding, not the number of characters in the JSON string.

For text:

~~~text
SEND
destination:/app/chat.send
content-type:text/plain;charset=utf-8
content-length:9

Xin chào
^@
~~~

In the text example, the string has 8 UTF-16 code units but 9 UTF-8 bytes. If content-length is omitted, the frame can still be delimited by NULL because the body does not contain NULL, but STOMP 1.2 recommends having content-length when a body exists.

## 15. Size limits and handling large data

A binary body can be very large. STOMP allows the server to apply limits on the number of headers, header line length, and body size to protect memory and prevent attacks from clients.

Spring also has buffer limits for STOMP frames. BufferingStompDecoder can reject a frame when content-length exceeds the configured limit or the total buffer exceeds the limit.

When designing uploads:

- Set size limits at the proxy, WebSocket transport, STOMP decoder, and business layer.
- Do not rely solely on the content-length declared by the client.
- Check body.length after the decoder creates the byte[].
- Avoid keeping multiple copies of the same payload in memory.
- For large files, consider uploading via HTTP/object storage and then sending a STOMP notification containing metadata or an authorized URL.
- If you must transmit chunks over STOMP, design explicit chunk ID, sequence, checksum, timeout, retry, and chunk reassembly mechanisms.
- Limit the number of concurrent uploads per user/session.

content-length helps delimit the frame; it is not an automatic capacity limit and does not stop a client from sending oversized data.

## 16. Security when receiving binary payloads

Do not treat content-type or the file name as proof of safety.

- Authenticate the sender and check access permissions for the destination.
- Check the actual MIME type and magic bytes of the file.
- Limit body size, message count, and send rate.
- Do not store files directly using a path name provided by the client.
- Scan for malware or inspect content according to business policy.
- Do not write the entire binary body to logs.
- Do not deserialize Java objects or custom data from the client without validation and schema restrictions.
- Use TLS/WSS in production environments.
- Check that content-type and the payload type are compatible before converting.

A malicious client can send content-type:application/json while the body is not JSON, or declare image/png for non-image content. The server must handle parse errors safely and avoid exposing stack traces.

## 17. Common mistakes

| Symptom | Cause | How to handle |
| --- | --- | --- |
| Binary payload is truncated at byte 0x00 | Missing content-length | Send content-length equal to the number of body bytes |
| Incomplete frame | content-length larger than actual bytes sent, or missing final NULL byte | Recalculate the byte length and add a separate terminator |
| Decoder mistakes the next frame for the body | content-length is too large | Check the payload length and frame limits |
| Unicode text is corrupted or truncated | Used String.length() instead of UTF-8 byte length | Encode first and then take byte[].length |
| Controller receives String instead of byte[] | Wrong converter or content-type chosen | Use application/octet-stream and ByteArrayMessageConverter |
| No suitable converter | MIME type is not supported by any converter | Register a suitable MessageConverter or receive Message<byte[]> |
| JSON parse fails | content-type is not application/json or body is not valid JSON | Check MIME type, charset, and schema |
| Spring rejects a large frame | Exceeded buffer/message size limit | Adjust limits carefully or move uploads to HTTP/object storage |
| Client and server calculate different lengths | One side counts characters, the other counts bytes | Standardize the encoding and count in octets |
| content-type header is ignored | Wrong header name, wrong MIME type, or custom converter does not read the header | Use the exact lowercase name and check native headers |
| Binary body is converted into text | Application calls String constructor on byte[] | Keep byte[] until the encoding is known |
| Frame contains a NULL byte without content-length | Violates the STOMP 1.2 delimitation rule | Always send content-length with a body containing 0x00 |

## 18. Design and testing checklist

- [ ] Choose the right MIME type for each kind of body.
- [ ] Use an explicit UTF-8 charset for text when interoperability is needed.
- [ ] Calculate content-length from the byte array after encoding.
- [ ] Do not include headers, the blank line, or the final NULL byte of the frame in content-length.
- [ ] Always include content-length if the body contains a 0x00 byte.
- [ ] Keep byte[] for binary payloads and convert only through an appropriate converter.
- [ ] Check StompHeaderAccessor.getContentType() and getContentLength().
- [ ] Confirm that MessageConverter supports the MIME type and the target payload type.
- [ ] Test accented Unicode, emoji, byte 0x00, byte 0xFF, and an empty body.
- [ ] Test frames split across multiple receives and frames cut off partway through.
- [ ] Test content-length that is smaller, larger, and exceeding limits.
- [ ] Limit size, send rate, number of sessions, and concurrent uploads.
- [ ] Validate file content independently of the content-type declared by the client.

## 19. References

- [STOMP Protocol Specification 1.2 — Frames and Headers](https://stomp.github.io/stomp-specification-1.2.html#Frames_and_Headers)
- [STOMP Protocol Specification 1.2 — SEND Frame](https://stomp.github.io/stomp-specification-1.2.html#SEND)
- [Spring Framework 7.0.10 — STOMP](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp.html)
- [Spring Framework 7.0.10 — Flow of Messages](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/message-flow.html)
- [Spring Framework 7.0.10 — Annotated Controllers](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-annotations.html)
- [Spring Framework API — StompDecoder](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/simp/stomp/StompDecoder.html)
- [Spring Framework API — StompEncoder](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/simp/stomp/StompEncoder.html)
- [Spring Framework API — StompHeaderAccessor](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaderAccessor.html)
- [Spring Framework API — ByteArrayMessageConverter](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/converter/ByteArrayMessageConverter.html)
- [Spring Framework API — MessageConverter](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/converter/MessageConverter.html)
