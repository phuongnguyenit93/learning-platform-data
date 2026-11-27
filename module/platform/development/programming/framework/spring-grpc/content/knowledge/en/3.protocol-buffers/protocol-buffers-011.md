# Bytes, String, and Encoding

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **string** for UTF-8 text from **bytes** for arbitrary binary data in proto3.
- Explain how both types share wire type **LEN** yet enforce different content rules.
- Convert between Java **String**, **byte[]**, and **ByteString** without relying on the machine's default charset.
- Understand how ProtoJSON represents string and bytes.
- Choose the appropriate field type for text content, files, hashes, tokens, and binary payloads in Spring gRPC services.
- Evaluate the risks of changing a field from string to bytes or vice versa.

## 1. Choose string or bytes?

In **SPRING_GRPC** contracts, Protocol Buffers defines data transmitted between client and server. Both **string** and **bytes** carry a sequence of bytes on the wire, yet they have different semantics:

- **string** is for valid UTF-8 encoded text. Readers can interpret the content as Unicode text.
- **bytes** is for an arbitrary sequence of bytes. The content does not have to be text and can contain any byte value from 0 to 255.

Example:

~~~proto
syntax = "proto3";

message Document {
  string title = 1;
  string description = 2;
  bytes content = 3;
  bytes sha256_digest = 4;
}
~~~

**title** and **description** are text. **content** may be PDF data, an image, a compressed file, or an encrypted payload. **sha256_digest** is a 32-byte hash digest, not an arbitrary character string.

| Data | Recommended type | Reason |
| --- | --- | --- |
| Name, description, email address | **string** | UTF-8 text. |
| Plain text content | **string** | Must be handled as a Unicode string. |
| Images, PDFs, compressed data | **bytes** | May contain bytes invalid in UTF-8. |
| Hashes, digital signatures, binary keys | **bytes** | Must preserve every byte verbatim. |
| Text-formatted token per contract | **string** | If the token is defined as a character string. |
| Binary token or ciphertext | **bytes** | Must not be interpreted as text. |

Do not choose **bytes** merely because Protobuf ultimately transmits bytes. Choose the type based on data semantics and how client/server must process it.

## 2. string in proto3 Is UTF-8 Text

Declaration:

~~~proto
message Greeting {
  string message = 1;
}
~~~

A **string** field must contain valid UTF-8. Protobuf does not store strings using the operating system's default charset; the wire format uses UTF-8. When a parser encounters invalid UTF-8 in a string field, the message is not considered a valid Protobuf string and parsing may fail.

Example with Vietnamese text:

~~~java
String message = "Xin chào";
Greeting greeting = Greeting.newBuilder()
    .setMessage(message)
    .build();
~~~

Java represents **String** internally as UTF-16, while Protobuf converts string content to UTF-8 during serialization. Application code does not need to manually convert to byte[] before calling a string field's setter.

An important point is that **character count does not equal UTF-8 byte count**. For instance, ASCII letters take one byte, whereas many accented Vietnamese characters require multiple bytes. Do not use **String.length()** to estimate wire payload size.

~~~java
import java.nio.charset.StandardCharsets;

String text = "Xin chào";
int utf8Length = text.getBytes(StandardCharsets.UTF_8).length;

System.out.println(text.length()); // Number of UTF-16 code units in Java String
System.out.println(utf8Length);    // Number of bytes when UTF-8 encoded
~~~

If business rules treat two Unicode accented representations as equivalent—such as precomposed characters and combining character sequences—the application must define Unicode normalization at the business layer. Protobuf preserves the received string; it does not normalize content into a canonical Unicode form automatically.

## 3. bytes Represents Arbitrary Binary Data

Declaration:

~~~proto
message UploadChunk {
  string file_name = 1;
  bytes data = 2;
}
~~~

The **data** field has no UTF-8 requirement. It can hold 0x00, 0xFF, control bytes, or any byte pattern:

~~~java
import com.google.protobuf.ByteString;

byte[] raw = new byte[] {
    0x00, 0x41, (byte) 0xFF, 0x0A
};

UploadChunk chunk = UploadChunk.newBuilder()
    .setFileName("sample.bin")
    .setData(ByteString.copyFrom(raw))
    .build();
~~~

Protobuf Java maps:

| proto3 type | Java type |
| --- | --- |
| **string** | **java.lang.String** |
| **bytes** | **com.google.protobuf.ByteString** |

**ByteString** is Protobuf's immutable byte sequence type. The builder uses it to hold binary data; a built message does not allow mutating ByteString contents in place. You can obtain a copied byte[] via **toByteArray()** when another API requires a byte array.

Do not convert arbitrary binary data to String using the default charset. Decoding can replace invalid bytes with replacement characters, altering the content and breaking hashes or signatures.

## 4. Java API: Converting Between String, byte[], and ByteString

### Creating ByteString from UTF-8 Text

When a bytes field is defined by convention to hold UTF-8 text, you can use:

~~~java
import com.google.protobuf.ByteString;

String note = "Xin chào";
ByteString encodedText = ByteString.copyFromUtf8(note);
~~~

**copyFromUtf8()** encodes the String into UTF-8 bytes and creates a ByteString. This is convenient when a bytes contract genuinely specifies a UTF-8 payload.

### Reading ByteString as Text

Only convert bytes to String when you know the contract specifies UTF-8 content. If the data might come from an untrusted source, validate first:

~~~java
ByteString payload = chunk.getData();

if (payload.isValidUtf8()) {
    String text = payload.toStringUtf8();
    processText(text);
} else {
    rejectInvalidTextPayload();
}
~~~

**toStringUtf8()** does not turn binary data into meaningful text. With invalid byte sequences, decoding can substitute replacement sequences; therefore verify the contract or check UTF-8 validity before processing.

### Using byte[] with an Explicit Charset

When interacting with Java APIs that accept byte[], always specify UTF-8 explicitly:

~~~java
import java.nio.charset.StandardCharsets;

String text = "Spring gRPC";
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);

String restored = new String(utf8, StandardCharsets.UTF_8);
~~~

Never use **new String(bytes)** or **text.getBytes()** without specifying a charset in protocol-handling code. Results can differ across developer machines, containers, and production environments.

### ByteString and Byte Operations

Useful methods:

| Method | Purpose |
| --- | --- |
| **ByteString.copyFrom(byte[])** | Creates a ByteString from a byte array. |
| **ByteString.copyFromUtf8(String)** | Encodes a String to UTF-8 and creates a ByteString. |
| **byteString.toByteArray()** | Gets a byte array copy. |
| **byteString.toStringUtf8()** | Decodes bytes into a UTF-8 String. |
| **byteString.isValidUtf8()** | Checks whether the content is valid UTF-8. |
| **byteString.size()** | Number of bytes. |
| **byteString.isEmpty()** | Checks whether there are zero bytes. |

Immutable ByteString prevents an external byte array from being mutated after a message is built. For large payloads, still consider memory copies and message size limits.

## 5. string and bytes Share the Same Wire Type, Not the Same Semantics

In binary Protobuf, both **string** and **bytes** use wire type **2 (LEN, length-delimited)**. The structure consists of:

1. Tag containing field number and wire type.
2. Payload length encoded as a varint.
3. Content bytes.

Example:

~~~proto
message Sample {
  string text = 1;
  bytes raw = 2;
}
~~~

With **text = "A"** and **raw = [0x00, 0xFF]**, the payload bytes look like:

~~~text
0A 01 41
|  |  +-- UTF-8 byte of character A
|  +----- Length: 1
+-------- Tag field 1, wire type 2

12 02 00 FF
|  |  |  |
|  |  +--+-- Two arbitrary data bytes
|  +-------- Length: 2
+----------- Tag field 2, wire type 2
~~~

Having the same wire type does not mean the two types can safely replace each other. A string parser must validate UTF-8; a bytes parser accepts arbitrary bytes. Java APIs and ProtoJSON also differ.

## 6. How ProtoJSON Represents string and bytes

ProtoJSON uses:

- **string**: a JSON string, escaped according to JSON rules.
- **bytes**: a Base64 string representing the byte sequence.

Given:

~~~proto
message Attachment {
  string file_name = 1;
  string description = 2;
  bytes content = 3;
}
~~~

A JSON representation:

~~~json
{
  "fileName": "report.pdf",
  "description": "November report",
  "content": "JVBERi0xLjQK"
}
~~~

**content** is Base64, not decoded PDF text. JSON clients must Base64-decode it to recover the original bytes. When using **JsonFormat** from **protobuf-java-util**, the library handles this rule:

~~~java
import com.google.protobuf.ByteString;
import com.google.protobuf.util.JsonFormat;

Attachment attachment = Attachment.newBuilder()
    .setFileName("report.pdf")
    .setContent(ByteString.copyFrom(new byte[] {
        0x01, 0x02, (byte) 0xFE
    }))
    .build();

String json = JsonFormat.printer().print(attachment);

Attachment.Builder parsed = Attachment.newBuilder();
JsonFormat.parser().merge(json, parsed);

System.out.println(
    parsed.build().getContent().equals(attachment.getContent()));
// true
~~~

Do not use a general-purpose JSON serializer and assume it conforms to ProtoJSON. In particular, bytes must be represented as Base64 per the Protobuf contract; how another library serializes ByteString may be incompatible.

## 7. Is Changing a Field from string to bytes Safe?

At the wire format level, both string and bytes are length-delimited. If the string payload is valid UTF-8, the byte sequence can be read as bytes without changing the binary content. However, changing the type of a released field still has major impacts:

| Aspect | Changing string to bytes |
| --- | --- |
| Field number and wire type | Can stay the same if the number is unchanged; both use wire type 2. |
| Binary payload | Old UTF-8 bytes can be read as bytes. |
| Old non-UTF-8 data | Cannot validly exist as a Protobuf string; if present from another source, string parsers may already reject it. |
| Java API | Getter changes from **String** to **ByteString**; call sites must be updated. |
| ProtoJSON | Value changes from a JSON string to a Base64 string. |
| Business meaning | Clients may stop interpreting the content as text. |

In the reverse direction, changing bytes to string can only be done safely when **every existing payload is valid UTF-8** and all clients accept the API/JSON change. Arbitrary bytes such as images, ciphertext, or hashes cannot be faithfully converted into string.

Therefore, never treat sharing a wire type as sufficient reason to change a field type. If data semantics change, the safe approach is usually to add a new field with an unused number, run a transition period, and then retire the old field and reserve its number/name.

## 8. Choosing an Encoding for Text Data Stored in bytes

Sometimes a system receives a bytes payload whose content is actually text. In that case, the encoding must be part of the contract:

~~~proto
message TextPayload {
  string media_type = 1;
  string charset = 2;
  bytes content = 3;
}
~~~

If **charset = "UTF-8"** is specified, consumers can decode content as UTF-8. If multiple charsets are supported, define an allowlist, handling for unsupported charsets, and clear conversion rules.

Never guess encoding from the leading bytes or runtime environment. Use a fixed convention whenever possible; UTF-8 is usually the right choice for new text.

If the payload is regular text data and preserving the exact original bytes is unnecessary, **string** is simpler. Use bytes paired with a charset when the contract requires storing exact raw bytes, supporting multiple encodings, or transmitting undecoded content.

## 9. Large Payloads and gRPC Streaming

The bytes field fits small or medium binary data inside a single message. However, embedding an entire large file into one request can:

- Increase memory required on both client and server.
- Create byte array copies when converting between APIs.
- Increase latency before the server can begin processing data.
- Hit message size limits or limits configured by server/client.

For large files, consider a **client-streaming RPC** sending multiple chunks:

~~~proto
message UploadChunk {
  string upload_id = 1;
  int64 offset = 2;
  bytes data = 3;
  bool last = 4;
}

message UploadResult {
  string upload_id = 1;
  int64 bytes_received = 2;
}

service FileService {
  rpc Upload(stream UploadChunk) returns (UploadResult);
}
~~~

Each message carries one slice of data; the server validates upload id, offset, chunk ordering, size, and end condition. This example only illustrates schema structure; the application must still define handling for duplicate chunks, missing chunks, retries, authentication, and temporary storage.

Do not split payloads into chunks arbitrarily while ignoring message limits, flow control, and recovery. For very large files, streaming enables sequential processing and better memory control than a single huge message.

## 10. Testing Encoding and Round-Trip

A test suite should cover:

1. ASCII and Unicode strings, including accented text.
2. Bytes containing 0x00, 0xFF, and non-UTF-8 byte sequences.
3. Binary Protobuf serialize/parse and exact content comparison.
4. ProtoJSON conversion, confirming bytes are emitted as Base64 and parsed back byte-for-byte.
5. Rejecting or handling deliberately when bytes are asked to decode as UTF-8 but contain invalid data.
6. Verifying payload sizes and chunk behavior when streaming is used.

JUnit 5 example:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.content.v1.Sample;
import com.google.protobuf.ByteString;
import com.google.protobuf.util.JsonFormat;
import org.junit.jupiter.api.Test;

class StringBytesTest {
    @Test
    void preservesUnicodeStringAndArbitraryBytes() throws Exception {
        byte[] raw = new byte[] {
            0x00, 0x41, (byte) 0xFF
        };

        Sample source = Sample.newBuilder()
            .setText("Xin chào")
            .setRaw(ByteString.copyFrom(raw))
            .build();

        Sample decoded = Sample.parseFrom(source.toByteArray());

        assertEquals("Xin chào", decoded.getText());
        assertArrayEquals(raw, decoded.getRaw().toByteArray());
    }

    @Test
    void preservesBytesThroughProtoJson() throws Exception {
        Sample source = Sample.newBuilder()
            .setRaw(ByteString.copyFrom(new byte[] {
                0x00, (byte) 0xFF
            }))
            .build();

        String json = JsonFormat.printer().print(source);
        Sample.Builder builder = Sample.newBuilder();
        JsonFormat.parser().merge(json, builder);

        assertEquals(source.getRaw(), builder.build().getRaw());
    }

    @Test
    void validatesUtf8BeforeTreatingBytesAsText() {
        ByteString arbitrary = ByteString.copyFrom(
            new byte[] { (byte) 0xFF, 0x00 });

        assertFalse(arbitrary.isValidUtf8());
    }
}
~~~

The snippets above use the **Sample** class with the schema:

~~~proto
syntax = "proto3";

package learning.content.v1;
option java_package = "com.example.content.v1";
option java_multiple_files = true;

message Sample {
  string text = 1;
  bytes raw = 2;
}
~~~

These are example tests based on the generated Java API; run them in a project with compatible Protobuf and protobuf-java-util versions.

## 11. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using string for images or ciphertext | Text parsers/serializers may reject or corrupt bytes | Use **bytes**. |
| Using bytes for text without recording encoding | Consumers do not know how to decode | Use **string** or specify the charset explicitly. |
| Calling getBytes() without specifying a charset | Results vary across environments | Use **StandardCharsets.UTF_8**. |
| Converting arbitrary bytes to String | Loses or replaces invalid bytes | Check UTF-8 and only decode per contract. |
| Thinking string and bytes are safely interchangeable due to same wire type | Breaks Java API and ProtoJSON, and may break semantics | Evaluate binary, source, JSON, and business impact separately. |
| Serializing ByteString with a general JSON library | JSON does not match ProtoJSON | Use **JsonFormat** when ProtoJSON is needed. |
| Sending large files in a single message | High memory usage, latency, and risk of exceeding limits | Consider client-streaming with controlled chunks. |

## 12. Practice Exercise

Design a message for a document storage service:

~~~proto
message StoredDocument {
  string document_id = 1;
  string file_name = 2;
  string media_type = 3;
  bytes content = 4;
  bytes sha256_digest = 5;
}
~~~

Tasks:

1. Explain why **file_name** and **media_type** are string, while **content** and **sha256_digest** are bytes.
2. Create a Java message whose content contains 0x00 and 0xFF; serialize/parse and verify all bytes are preserved.
3. Convert the message to ProtoJSON and inspect how the bytes fields are represented.
4. Try decoding content as UTF-8 and check **isValidUtf8()** before processing.
5. Explain the risks of changing the content field from bytes to string while keeping the same field number.
6. Propose a streaming RPC if documents can exceed the system's accepted message size limit.

**Completion criteria:** choose types by semantics, convert in Java without relying on default charsets, preserve bytes across round-trips, and explain the difference between wire compatibility and API/JSON compatibility.

## 13. Key Takeaways

- **string** is valid UTF-8 text; **bytes** is arbitrary binary data.
- Java maps string to **String** and bytes to **ByteString**.
- Both use wire type **LEN**, yet content validation rules and Java APIs differ.
- ProtoJSON outputs string as a JSON string and bytes as Base64.
- Only convert bytes to text when the encoding is known; use UTF-8 explicitly and validate data when necessary.
- Sharing a wire type does not guarantee string/bytes changes are compatible with Java code, JSON, or business logic.
- For large payloads, consider streaming instead of packing all data into one message.

Choosing properly between string and bytes keeps Protocol Buffers contracts lossless, prevents encoding bugs across environments, and helps Spring gRPC services exchange both text and binary data reliably.
