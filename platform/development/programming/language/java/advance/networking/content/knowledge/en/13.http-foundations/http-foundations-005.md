# Content-Type, charset, Content-Length, and Data Representation in HTTP

## 1. Why Must We Distinguish Content, Encoding, and Byte Count?

An HTTP message carries **representation data** (data representing a resource/message) along with metadata that helps the receiver interpret that data. Three fields are commonly confused:

- **`Content-Type`** indicates the media type of the representation, for example `text/plain`, `application/json`, `image/png`; some media types have a `charset` parameter specifying how to convert bytes into characters.
- **`charset`** is not a required standalone header; it is usually a **parameter** of `Content-Type`, for example `Content-Type: text/plain; charset=UTF-8`. It specifies how to **decode characters**, not how to frame TCP segments.
- **`Content-Length`** is the **number of octets (bytes)** declared according to HTTP semantics. When sending content over HTTP/1.1 without `Transfer-Encoding`, it is used to determine the number of content bytes in the message; **it is not the number of characters, the number of lines, the size of a Java object, or the byte count of the entire HTTP message including headers**.

For compressed data, there is another important layer: **`Content-Encoding`** such as `gzip` indicates that the representation bytes have undergone content coding. In that case, `Content-Length` (when applicable to the transmitted content) counts the **encoded/compressed bytes** in the HTTP content, not the pre-compression UTF-8 bytes.

Diagram of operations on the client/server:

```text
  Logical data
       |
       v
  Serialization by media type
  (text, JSON, XML, form, PNG, protobuf, ...)
       |
       v
  Character encoding if text data
  ("Xin chào" --> UTF-8 bytes)
       |
       v
  Optional Content-Encoding, e.g., gzip
       |
       v
  HTTP content bytes
       |
       +---- Content-Type: describes the underlying media type
       +---- charset: how to decode text if defined by the media type
       +---- Content-Encoding: content coding transformation
       +---- Content-Length: byte count per HTTP rules
       |
       v
  HTTP/1.1 framing or HTTP/2/3 framing
       |
       v
  Transport (TCP/TLS/QUIC respectively)
```

On the receiving side, the reverse is performed: determine the HTTP content boundary → decode content coding (if present) → decode bytes according to the valid media type and charset → parse into JSON/text/binary → validate business data. **You cannot infer the entire process from a single header alone**.

## 2. Reading an HTTP/1.1 Message Correctly

Example where the body is the string `Xin chào` in UTF-8:

```http
POST /notes HTTP/1.1
Host: example.test
Content-Type: text/plain; charset=UTF-8
Content-Length: 9

Xin chào
```

The visual snippet above is a human-readable representation of the message; in HTTP/1.1, header lines are separated by **CRLF** and there is an empty CRLF line between the header section and the body. The body is actually **nine UTF-8 bytes**, not eight bytes:

```text
Char:  X   i   n  [ ]  c   h    à      o
Hex:   58  69  6E  20   63  68  C3 A0   6F

String "Xin chào":
  8 UTF-16 code units (and 8 Unicode code points in this example)
  9 bytes when encoded in UTF-8
```

Because `à` is encoded into two bytes `C3 A0`, if you take `"Xin chào".length()` and set `Content-Length: 8`, an HTTP/1.1 receiver may treat the message as ending **before the last byte**. In an HTTP keep-alive system, the leftover data can also corrupt the framing of the next message. Do not try to fix this by increasing timeouts or relying on a single `socket.write()`: this is a **framing** bug.

**Header field names are case-insensitive**: `content-type`, `Content-Type`, or `CONTENT-TYPE` refer to the same field. In contrast, parameter values and media types must be interpreted according to their own rules (media type and parameter names are generally case-insensitive; the content bytes themselves do not change). When learning HTTP/1.1 structure, do not treat blank lines or `\n` in illustrative examples as protocol message framing that can arbitrarily replace CRLF.

## 3. `Content-Type` Describes the Representation Type

Common syntax:

```text
Content-Type: <type>/<subtype>; parameter=value

Examples:
Content-Type: text/plain; charset=UTF-8
Content-Type: text/html; charset=utf-8
Content-Type: application/json
Content-Type: application/octet-stream
Content-Type: multipart/form-data; boundary=----demo-boundary
```

The **media type** tells the receiver which parser/handler to use:

| Media type | Common content | Things to watch out for |
| --- | --- | --- |
| `text/plain` | Plain text | Must agree on charset when using non-ASCII characters |
| `text/html` | HTML | Charset may be declared via HTTP header and/or document metadata; precedence rules depend on HTML |
| `application/json` | JSON | JSON exchanged outside a closed ecosystem must use UTF-8 per RFC 8259 |
| `application/xml` or `text/xml` | XML | Has XML/media-type-specific encoding rules; do not assume the same defaults as JSON |
| `application/octet-stream` | Binary bytes | Do not force decoding into a `String` |
| `image/png` | PNG image | Parse according to the PNG format, do not decode as text |
| `application/x-www-form-urlencoded` | URL-encoded key/value form | Percent-encoding and form charset affect the bytes |
| `multipart/form-data; boundary=...` | Multiple parts (files, fields, ...) | Body bytes include boundaries, part headers, and CRLF, not just the file content |

**Do not infer the actual type solely from a file extension**. `file.json` can be sent with the wrong `Content-Type`; the client must follow the API contract, check the response media type, and validate the payload. `Content-Type` is not proof of safe content: do not trust an arbitrary upload just because it claims `image/png` or `application/json`.

**`Accept` is different from `Content-Type`:**

- A client sending `Accept: application/json` expresses its **preference/capability for receiving a response**.
- A client sending `Content-Type: application/json` **describes the body of the current request**.
- A server sending `Content-Type: application/json` describes the **selected response**.
- If the server does not support the request's media type, it may return `415 Unsupported Media Type`; if it cannot satisfy the options in `Accept`, it may return `406 Not Acceptable`. The actual behavior depends on the API contract.

Not every response has a body; when there is no body, `Content-Type` may be absent. If there are response bytes to process, it is important to determine the media type before parsing.

## 4. `charset`: From Bytes to Characters and Back

With `Content-Type: text/plain; charset=UTF-8`, the sender does:

```java
String text = "Xin chào";
byte[] body = text.getBytes(StandardCharsets.UTF_8);
int contentLength = body.length; // 9, not text.length() == 8
```

The receiver does the reverse:

```java
String decoded = new String(body, StandardCharsets.UTF_8);
```

Both snippets assume `import java.nio.charset.StandardCharsets;` and that `body` contains valid received UTF-8 data. When using Java APIs that return raw `byte[]`, **the caller is responsible** for choosing the right charset and validating the data.

Concepts that must be kept distinct:

- Java's `String.length()` counts **UTF-16 code units**, not UTF-8 bytes. Supplementary code point characters such as some emojis can occupy **two UTF-16 code units**.
- `String.codePointCount(...)` counts Unicode code points in a substring, which is still not the byte length.
- `text.getBytes(StandardCharsets.UTF_8).length` is the number of bytes after UTF-8 encoding; this is the quantity to use when calculating **body byte** size.
- `byte[].length` is the capacity of that specific array. If the body has a media-type-specific prefix/header/trailer, you must count **all bytes actually transmitted**, not just text bytes.
- `CharsetDecoder` with `CodingErrorAction.REPORT` is useful when you need to **reject invalid byte sequences** instead of silently replacing them with replacement characters.

**There is no single default charset that applies to all HTTP media types.** When sending text you control, the safe and interoperable approach is to choose UTF-8 **explicitly** both in the header (for media types that use a charset parameter) and when converting between Java `String` and bytes. For text missing a charset, fallback rules depend on the media type, protocol, and application; you should not arbitrarily rely on the platform default encoding.

### The `application/json` Case

RFC 8259 specifies that **JSON text exchanged between systems that are not part of a closed ecosystem must be encoded using UTF-8**. The `application/json` media type in the IANA registry **does not define a `charset` parameter**; adding `charset=UTF-8` does not change how an RFC-compliant receiver processes it. You should send:

```http
Content-Type: application/json
```

and encode the body as UTF-8. For example, `{"message":"Chào"}` is **19 UTF-8 bytes**; the runnable code in Section 9 confirms this. Even though the content is JSON text, `Content-Length` is still **19** when sent uncompressed, not the number of characters in the JSON string.

If code calls `json.getBytes()` without specifying a charset, the behavior depends on the JVM/JDK configuration and environment; for protocols, use `json.getBytes(StandardCharsets.UTF_8)` so you do not depend on implicit assumptions.

### UTF-8 and BOM

For JSON transmitted over the network, RFC 8259 states that generators **must not add a BOM** at the beginning of JSON text. Some parsers may ignore a BOM to improve interoperability, but you must not rely on that behavior. For HTML/XML, rules regarding BOM, encoding declarations, or HTTP charset may differ; follow the corresponding media type rather than applying JSON rules verbatim.

## 5. What Does `Content-Length` Actually Count?

According to HTTP Semantics (RFC 9110), `Content-Length` is a **non-negative decimal integer** in **octets** (bytes). When a message has body content and does not use HTTP/1.1 transfer coding, the value is the **byte length of the HTTP content** so the recipient knows where the message ends.

```text
String original: "Xin chào"         -> length() = 8
UTF-8 encoded: 58 69 6E 20 63 68 C3 A0 6F
HTTP content bytes: 9             -> Content-Length: 9
```

It does not include:

- HTTP header lines (e.g., `Host`, `Content-Type`, and separating CRLF).
- TCP header, TLS record header, IP packet header.
- Characters in a Java `String` or number of code points.
- Number of JSON objects, number of lines, or number of files in a form.
- Pre-gzip byte count if the HTTP content is sending **gzipped bytes**.

**The sender is responsible for providing the exact size when handling framing manually.** In Java's `HttpClient`, standard body publishers with a known byte count let the transport compute `Content-Length`; **do not manually set `Content-Length` to a character count**. For streams whose size is not known in advance, let the HTTP stack use the appropriate valid framing.

### Important Exceptions

Do not assert that every `Content-Length` that appears means "the body definitely has that many bytes." RFC 9110 allows/restricts specific cases:

- A response to `HEAD` **has no response body**; if `Content-Length` is sent, its value must equal the number of bytes that **would have been sent** in the content of the corresponding `GET` response.
- A `304 Not Modified` response **has no body**; if it contains `Content-Length`, it must represent the number of bytes that **would have been** in the corresponding `200 OK` response.
- Do not send `Content-Length` in a `1xx` or `204 No Content` response; also do not send it in a `2xx` response to `CONNECT`.
- In HTTP/1.1, the presence and length of a message body must follow the **framing precedence order** of RFC 9112, rather than looking at a single header field in isolation.

For an empty body, `Content-Length: 0` means zero content bytes. However, a **request without a body** does not always need this field; how the application/HTTP layer constructs the message depends on the method and contract.

## 6. Distinguishing `Content-Encoding` from `Transfer-Encoding`

These are two different layers:

| Header | What it describes | Example | Decoding order |
| --- | --- | --- | --- |
| `Content-Type` | Media type of the representation | `application/json` | Select parser after obtaining decoded representation bytes |
| `charset` parameter | Character encoding if defined by the media type | `UTF-8` | Convert text bytes into characters |
| `Content-Encoding` | **Content coding** applied to the representation | `gzip` | Decompress/decode content coding before parsing JSON/text |
| `Transfer-Encoding` | Transfer coding/framing in **HTTP/1.1** | `chunked` | HTTP stack strips framing when reading the message |
| `Content-Length` | Octet count related to representation/message content per RFC rules | `39` | Framing when permitted and no transfer coding is present |

Example of sending gzipped JSON `{"message":"Chào"}`:

```http
POST /inspect HTTP/1.1
Host: localhost
Content-Type: application/json
Content-Encoding: gzip
Content-Length: 39

<39 gzip bytes - binary content, cannot be represented as raw JSON text>
```

In the executed Java example:

- The **pre-compression** UTF-8 JSON is **19 bytes** long.
- Using the JDK's `GZIPOutputStream` produced **39 bytes** of compressed data in the test run.
- The HTTP body sends **39 gzipped bytes** → `Content-Length: 39`.
- The server reads all 39 bytes, decompresses them into 19 UTF-8 bytes, and only then reads the JSON text.

**Do not call `new String(compressedBytes, UTF_8)` to parse JSON.** Decoding `Content-Encoding: gzip` must come before charset decoding and parsing. A high-level HTTP client may support automatic content-coding decompression depending on configuration; code using raw body bytes or primitive HTTP servers must verify whether the library handles it automatically.

**`Transfer-Encoding: chunked` is not gzip.** In HTTP/1.1, chunked describes how to transmit a message body as sized chunks with a terminator. After the HTTP decoder strips chunk framing, the application receives the content bytes. A sender **must not send both `Transfer-Encoding` and `Content-Length`** in the same HTTP/1.1 message. Combining the two fields improperly risks causing different boundary interpretations between a proxy and a backend.

## 7. HTTP/1.1 Chunked, HTTP/2, and HTTP/3

When the content size is known before sending an HTTP/1.1 response, a valid `Content-Length` can be used. For a streaming response whose size is unknown, HTTP/1.1 can use **`Transfer-Encoding: chunked`**, for example:

```http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
Transfer-Encoding: chunked

5
Hello
0

```

This is a visual example of chunk lines (on the wire, standard CRLF must be used); `5` is the **byte count in hex**, not `Content-Length`. The chunk terminator `0` marks the end of data. For multi-byte UTF-8 data, chunk sizes still count bytes, and a single UTF-8 character can be split across chunks while the final stream decoder still reconstructs it when assembling the bytes properly.

In HTTP/2 and HTTP/3, framing uses **the respective protocol's `DATA` frames**; HTTP/1.1-style `Transfer-Encoding: chunked` is not used. `Content-Length` may exist as metadata to check content size, but it is not a TCP byte-stream delimiter like in HTTP/1.1. Do not manually parse HTTP/2 over an `InputStream` as raw HTTP/1.1 lines.

**Practical takeaway:** use `HttpClient`, a server framework, or a standard HTTP library to handle framing rather than computing chunked/HTTP2 frames by hand. The application should choose the correct media type/charset/bytes; the transport layer is responsible for framing according to the HTTP version.

## 8. Typical Mistakes When Computing Content-Length

This snippet illustrates the wrong approach:

```java
String body = "Xin chào";
int wrong = body.length(); // 8, NOT the UTF-8 length.
```

Correct:

```java
byte[] utf8 = body.getBytes(StandardCharsets.UTF_8);
int correct = utf8.length;  // 9 bytes
```

With an API that actually manages transfer, you usually **do not attach `Content-Length` manually**: pass the exact bytes to the body publisher and let the library compute it:

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .header("Content-Type", "text/plain; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofByteArray(utf8))
        .build();
```

*This snippet is part of a program that has `uri`, `utf8`, and `import java.net.http.HttpRequest`.* Some headers controlled by the Java HTTP client (including `Content-Length`) are restricted from manual setting by implementation policy. Do not try to force them via internal options; if the body has a fixed size, use the appropriate byte-array/string/file publisher.

### `HttpURLConnection` / Raw Stream

If an API requires you to provide the streaming size **before sending**, you must convert to bytes first:

```java
// Code snippet: HttpURLConnection conn already exists.
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
conn.setDoOutput(true);
conn.setRequestProperty("Content-Type", "application/json");
conn.setFixedLengthStreamingMode(bytes.length);
try (OutputStream out = conn.getOutputStream()) {
    out.write(bytes);
}
```

*This snippet is not a standalone program; it assumes `conn` is an HTTP URL connection that has not started sending, `json` is a valid JSON string, and the caller handles `IOException`. Requires importing `OutputStream` and `StandardCharsets`.* Calling `setFixedLengthStreamingMode` after the connection/stream is already open may be too late; use it when the exact byte count is already known. Avoid opening a `Writer` with one charset while computing the length with UTF-8.

## 9. Complete Java 17+ Program: HTTP Client/Server Loopback

This example runs without Internet access: `com.sun.net.httpserver.HttpServer` serves the `/inspect` endpoint on loopback, and `java.net.http.HttpClient` sends two HTTP/1.1 requests.

- **Request 1:** `text/plain; charset=UTF-8`, payload `Xin chào`. The server reads the bytes, verifies `Content-Length` against the received byte count, and decodes UTF-8.
- **Request 2:** `application/json` + `Content-Encoding: gzip`. The client encodes JSON to UTF-8, compresses it, and sends the **compressed bytes**; the server decompresses before decoding.
- Both server responses are `text/plain; charset=UTF-8` and are sent as UTF-8 bytes with the exact size.
- The client uses `BodyPublishers.ofByteArray(...)`, so the transmitted byte count **is determined in advance** and the HTTP client sets framing accordingly. The code **does not manually populate the `Content-Length` header**.

**File `HttpRepresentationDemo.java`:**

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

public final class HttpRepresentationDemo {
    private static byte[] gzip(byte[] bytes) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (GZIPOutputStream zipper = new GZIPOutputStream(output)) {
            zipper.write(bytes);
        }
        return output.toByteArray();
    }

    private static void handle(HttpExchange exchange) throws IOException {
        try (exchange) {
            if (!"POST".equals(exchange.getRequestMethod())) {
                exchange.sendResponseHeaders(405, -1);
                return;
            }

            String mediaType = exchange.getRequestHeaders()
                    .getFirst("Content-Type");
            String encoding = exchange.getRequestHeaders()
                    .getFirst("Content-Encoding");
            String declared = exchange.getRequestHeaders()
                    .getFirst("Content-Length");
            byte[] received = exchange.getRequestBody().readAllBytes();

            byte[] decoded = received;
            if ("gzip".equalsIgnoreCase(encoding)) {
                try (GZIPInputStream unzip = new GZIPInputStream(
                        new ByteArrayInputStream(received))) {
                    decoded = unzip.readAllBytes();
                }
            }
            String text = new String(decoded, StandardCharsets.UTF_8);
            boolean correctLength = declared != null
                    && Long.parseLong(declared) == received.length;
            String response = "type=" + mediaType
                    + "; lengthMatches=" + correctLength
                    + "; content=" + text;
            byte[] responseBytes =
                    response.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type",
                    "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, responseBytes.length);
            exchange.getResponseBody().write(responseBytes);
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        server.createContext("/inspect", HttpRepresentationDemo::handle);
        server.start();
        try {
            URI uri = URI.create("http://" +
                    (loopback.getHostAddress().contains(":")
                        ? "[" + loopback.getHostAddress() + "]"
                        : loopback.getHostAddress())
                    + ":" + server.getAddress().getPort() + "/inspect");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3)).build();

            String message = "Xin chào";
            byte[] utf8 = message.getBytes(StandardCharsets.UTF_8);
            HttpRequest plain = HttpRequest.newBuilder(uri)
                    .header("Content-Type", "text/plain; charset=UTF-8")
                    .POST(HttpRequest.BodyPublishers.ofByteArray(utf8))
                    .build();
            HttpResponse<String> plainResponse = client.send(plain,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            System.out.println("text UTF-16 units=" + message.length()
                    + ", UTF-8 bytes=" + utf8.length);
            System.out.println("text reply: " + plainResponse.body());

            String json = "{\"message\":\"Chào\"}";
            byte[] jsonBytes = json.getBytes(StandardCharsets.UTF_8);
            byte[] compressed = gzip(jsonBytes);
            HttpRequest zipped = HttpRequest.newBuilder(uri)
                    .header("Content-Type", "application/json")
                    .header("Content-Encoding", "gzip")
                    .POST(HttpRequest.BodyPublishers.ofByteArray(compressed))
                    .build();
            HttpResponse<String> zippedResponse = client.send(zipped,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            System.out.println("JSON UTF-8 bytes=" + jsonBytes.length
                    + ", gzip bytes=" + compressed.length);
            System.out.println("gzip reply: " + zippedResponse.body());
        } finally {
            server.stop(0);
        }
    }
}
```

**Compile and run with JDK 17** (the HTTP server is in the `jdk.httpserver` JDK module):

```bash
javac --release 17 --add-modules jdk.httpserver HttpRepresentationDemo.java
java --add-modules jdk.httpserver HttpRepresentationDemo
```

**Actual tested stdout:**

```text
text UTF-16 units=8, UTF-8 bytes=9
text reply: type=text/plain; charset=UTF-8; lengthMatches=true; content=Xin chào
JSON UTF-8 bytes=19, gzip bytes=39
gzip reply: type=application/json; lengthMatches=true; content={"message":"Chào"}
```

### Explaining the Output

**Line 1:** Java's `String.length()` counts 8 UTF-16 code units; the UTF-8 payload has 9 bytes. The HTTP request's `Content-Length` is generated from the exact bytes because a byte-array publisher is used.

**Line 2:** The server reads `Content-Type` and receives the exact 9-byte body. The flag `lengthMatches=true` means the `Content-Length` field (in the tested HTTP/1.1 request) is a decimal number matching `received.length`. The server decodes the bytes into `Xin chào` using UTF-8.

**Line 3:** The original JSON text encodes to 19 UTF-8 bytes; after `GZIPOutputStream`, it is 39 bytes. The compressed length depends on the content and algorithm/implementation, so the right lesson here is to **take the actual `compressed.length`**, rather than estimating from character count. The result 39 is the output of the test example on the JDK used in this article.

**Line 4:** The server sees `Content-Type: application/json`, decodes `Content-Encoding: gzip` to get the JSON text, and `Content-Length` matches the number of **compressed bytes** received. If the server immediately passed the 39 compressed bytes into `new String(..., UTF_8)`, it would not get valid JSON.

**Demo limitations:** this is a test server, not a production API. `readAllBytes()` and `GZIPInputStream.readAllBytes()` **have no size limit**; untrusted input can cause excessive memory consumption or a decompression bomb. The code also assumes all text requests are UTF-8 and only handles `gzip`/no content encoding; production code must validate media type, charset, content coding, byte/trailer limits, and error responses before parsing. The sample request uses HTTP/1.1 with an explicit content-length, so comparing the header is meaningful in the test; **not every valid HTTP request is required to have a `Content-Length`**.

## 10. Using Java `HttpClient` at the Right Data Layer

Some common operations:

| Purpose | Java 17 API | Notes |
| --- | --- | --- |
| Send UTF-8 text | `BodyPublishers.ofString(text, StandardCharsets.UTF_8)` | Must set an appropriate `Content-Type`; the library cannot know the application's media type policy from a string |
| Send serialized/compressed bytes | `BodyPublishers.ofByteArray(bytes)` | Publisher size is determined by the actual bytes |
| Send a file | `BodyPublishers.ofFile(path)` | Media type is based on contract/file, do not infer with certainty from filename alone |
| Receive response as bytes | `BodyHandlers.ofByteArray()` | Preserves raw bytes to handle content coding/format yourself |
| Receive text with a known charset | `BodyHandlers.ofString(StandardCharsets.UTF_8)` | Use when the protocol/API specifies UTF-8 |
| Inspect response media type | `response.headers().firstValue("Content-Type")` | Validate before parsing outside short examples |
| Inspect HTTP status | `response.statusCode()` | Do not assume a 200 automatically means a valid payload |

For responses with `Content-Encoding: gzip`, if the library you use does **not** decompress automatically, you must read the bytes, gunzip them, and then parse according to the media type. You cannot expect `BodyHandlers.ofString(UTF_8)` to automatically decompress every content coding just because you chose UTF-8 as the charset.

**Safe client-side order:** check status → cap byte size → check `Content-Type` → read the body with a bounded API → decode `Content-Encoding` if needed → decode charset → parse/validate. For `application/json`, use a controlled JSON library instead of handling complex JSON via manual string slicing.

Note: for **untrusted** data sources, a self-declared `Content-Length` header may be missing or wrong. Do not let that header unconditionally dictate how much memory is allocated; enforce a cap per the application contract and verify received bytes.

## 11. Multipart and Form Encoding: Bodies Beyond Plain Text

Two common formats also use `Content-Type` but calculate bytes differently:

### 11.1. `application/x-www-form-urlencoded`

The content has a percent-encoded key/value structure. For example, spaces can become `+`, and non-ASCII characters are typically represented as percent-encoded UTF-8 bytes according to the form charset. Therefore, the HTTP body byte count **does not equal** the character count of the original input values.

Each value must be encoded using an appropriate API, such as `URLEncoder.encode(value, StandardCharsets.UTF_8)` when following form encoding rules; do not use the raw string instead of the encoded body to compute `Content-Length`.

### 11.2. `multipart/form-data`

The body consists of multiple parts, each with its own headers and boundary. Example:

```http
Content-Type: multipart/form-data; boundary=BOUNDARY

--BOUNDARY
Content-Disposition: form-data; name="note"

Xin chào
--BOUNDARY--
```

This is a readable illustration; on the wire, proper CRLF is required, and there are often per-part `Content-Type` headers and binary file bytes. **`Content-Length`, if present, must count the entire multipart body bytes**, including boundary markers, CRLFs, part headers, each part's payload, and the closing delimiter; not just the bytes of a file or a text field.

If you use a multipart client library, let the library generate the boundary, headers, and body. Concatenating strings manually and estimating with `String.length()` is very error-prone when UTF-8 or binary files are involved.

## 12. Receiving Data on the Server and Protecting Resources

Do not just check `Content-Length` accurately; a server must enforce **trust limits** on the body:

1. Only support the media types defined by the endpoint. For example, a JSON API requires `application/json` and rejects `text/plain` if there is no corresponding parsing rule.
2. Choose the charset according to the media type. JSON uses UTF-8; `text/plain` may need to read the charset parameter and only support an allowed set of charsets.
3. Enforce a limit on **encoded bytes** before reading or storing the body. When `Content-Length` is too large, you can reject early; when the header is absent, you must still limit the number of stream bytes actually read.
4. If `Content-Encoding: gzip`, enforce an additional limit on **decoded bytes**, decompression ratio, and CPU time to prevent decompression bombs.
5. Distinguish HTTP framing errors (handled by the HTTP server stack) from representation parsing errors (where the application returns 400/415/422 per contract).
6. Constrain the charset decoder and parser. Validate JSON syntax/schema, nesting depth, and string/array sizes, not just `Content-Type`.
7. Avoid trusting `Content-Length` as proof of integrity; it only provides a byte count per framing rules, not a signature or checksum.

A helper method can read at most `maxBytes` from an `InputStream` without calling `readAllBytes()` unboundedly:

```java
// Illustrative code snippet; requires import java.io.*, byte[].
static byte[] readAtMost(InputStream in, int maxBytes) throws IOException {
    if (maxBytes < 0) throw new IllegalArgumentException();
    ByteArrayOutputStream output = new ByteArrayOutputStream();
    byte[] chunk = new byte[8192];
    int read;
    while ((read = in.read(chunk)) != -1) {
        if (read > maxBytes - output.size()) {
            throw new IOException("HTTP content exceeds limit");
        }
        output.write(chunk, 0, read);
    }
    return output.toByteArray();
}
```

This is an isolated fragment, not a complete runnable file. It illustrates bounding byte count before unbounded allocation; **it does not decode `Content-Encoding`** and does not replace the server's HTTP framing. In real request processing, you must handle timeouts, abort/close, status code responses, and connection release according to the framework.

## 13. Wrong `Content-Length` and HTTP Request Smuggling Risks

HTTP/1.1 uses message boundaries to distinguish requests on a keep-alive connection. If a reverse proxy and a backend **disagree on the length**, a byte stream can be interpreted into two different request splits; this is the root cause of several types of **request smuggling**.

Inputs that require strict handling:

- `Content-Length` containing non-numeric characters or negative values.
- Values too large, causing overflow when parsed into `int`/`long`.
- Multiple conflicting `Content-Length` headers; must follow RFC rules and the HTTP stack's policy, not arbitrarily pick the first or last one.
- A message containing both `Transfer-Encoding` and `Content-Length`. RFC 9112 gives precedence to `Transfer-Encoding` on receipt, but this is a suspicious situation; senders **must not send both** and intermediaries must handle it per the standard to avoid parser disagreement.
- A `Content-Length` header known to be incorrect that is still forwarded downstream.

**Do not write your own HTTP/1.1 parser using `readLine()` and `parseInt(Content-Length)` for untrusted traffic** when a battle-tested stack is available. Choose an up-to-date version/server/proxy framework, limit header/body sizes, and stay consistent in how framing is handled at every hop.

Even when `Content-Length` is correct, the data inside can still be invalid JSON, invalid schema, invalid charset, or contain malicious payloads; **a valid length does not equal valid data**.

## 14. Differences Between Content-Length, Transfer Progress, and Integrity

Learners sometimes use `Content-Length` to decide:

- **Progress bar:** when the body size is known, the byte count helps estimate progress. With streaming/chunked, the total size may not be known in advance.
- **Memory allocation:** do not allocate an array directly from an untrusted `Content-Length`. Always have an application upper bound.
- **Download integrity:** a file having the expected byte count is only a length check. To verify integrity/content/origin, use transport security (TLS), digests/signatures/checksums per your threat model, and trusted metadata.
- **Compression:** a high compression ratio means small encoded bytes, but decoded bytes can be huge. `Content-Length` only reflects the encoded bytes sent, and does not reveal the decoded size.
- **Response caching:** `Content-Type`/`Content-Encoding` and `Vary`/negotiation affect how representations are interpreted. Caches must not mix gzip/plain variants or different media types in a way that breaks the application.

In summary: `Content-Length` answers **how many octets** per HTTP rules; `Content-Type` answers **what kind of representation this is**; `charset` answers **how text bytes are decoded**; `Content-Encoding` answers **what transformation the bytes underwent**. They complement each other and cannot replace one another.

## 15. Practical Diagnostic Scenarios

| Symptom | Cause to check | Action to take |
| --- | --- | --- |
| Vietnamese text turns into `Ã `/mojibake | Sender and receiver disagree on charset | Check raw bytes, `Content-Type` charset, UTF-8 decoder |
| Server reads body missing the last byte | Used `String.length()` as `Content-Length` | Encode to bytes first and use the byte count |
| Server sees JSON as garbled characters | Parsing gzipped bytes as UTF-8 | Check `Content-Encoding`, decompress first |
| HTTP 415 Unsupported Media Type | Request media type differs from what API accepts | Set the correct `Content-Type` per contract |
| HTTP 406 Not Acceptable | Server cannot return a variant matching `Accept` | Check `Accept` and content negotiation support |
| Client hangs while reading body | Wrong framing, unclosed stream, timeout | Use an HTTP library, deadlines, and measure actual bytes |
| Response has no `Content-Length` | May be streaming/chunked/HTTP2; not necessarily an error | Let the HTTP stack handle framing, set a streaming limit |
| Valid UTF-8 JSON but header has an odd `charset` | JSON media type does not define a `charset` parameter | Follow JSON UTF-8 and the API contract |
| `Content-Length` matches yet file is corrupted | Byte count does not verify integrity | Check media format, digest/signature |
| `HEAD` response has `Content-Length` but no body | Header may indicate the corresponding `GET` size | Do not try to read a body from that header in `HEAD` |
| Proxy/backend disagree on `Content-Length` / `Transfer-Encoding` | Risk of desynchronization/request smuggling | Harden server/proxy and reject invalid framing |
| Binary body converted to `String` then re-sent | Data may be altered or lose bytes | Pass `byte[]`/`InputStream` directly |

## 16. Practice Exercises

**Exercise 1 — UTF-8.** Given the Java snippet `String s = "Xin chào";`. Why is `s.length()==8` while a request containing UTF-8 has `Content-Length` 9? Which API computes the bytes?

**Exercise 2 — Gzip.** A JSON payload is 19 bytes before compression and 39 bytes after compression. An HTTP request sends the 39 compressed bytes with `Content-Type: application/json` and `Content-Encoding: gzip`. What should `Content-Length` be in HTTP/1.1? What must the receiver do before parsing JSON?

**Exercise 3 — Media type.** A client sends JSON but sets `Content-Type: text/plain` and `Accept: application/json`. Which direction does each header describe? When might the server respond with 415?

**Exercise 4 — HTTP/1.1 framing.** If a request has both `Content-Length: 8` and `Transfer-Encoding: chunked`, what should be done? Is a sender allowed to proactively emit both?

**Exercise 5 — HEAD.** A server responds to `HEAD` with `Content-Length: 3200`. Is it valid to read 3200 bytes of body in the `HEAD` response? What is the number 3200 allowed to represent?

**Exercise 6 — Multipart.** An uploaded file contains 1000 bytes, and the multipart body also has boundaries, part headers, and CRLFs. Does `Content-Length` equal 1000? If using a library to build multipart, should you calculate it manually or let the library manage it?

**Exercise 7 — Charset.** A client receives `application/octet-stream` containing a PNG. Should it call `new String(bodyBytes, UTF_8)` before saving? Why or why not?

**Exercise 8 — Streaming.** A server streams content incrementally without knowing the total byte count before sending headers. What can HTTP/1.1 use instead of `Content-Length`? Does HTTP/2 use `Transfer-Encoding: chunked` in the same way?

**Suggested Answers:**

1. `String.length()` counts UTF-16 code units; `à` requires two UTF-8 bytes. Use `s.getBytes(StandardCharsets.UTF_8).length`.
2. `Content-Length: 39` because the HTTP content is gzipped. The receiver must read the body, gunzip it to obtain the 19 UTF-8 bytes, and then parse JSON.
3. `Content-Type` describes the current request body; `Accept` describes the desired response. The server may return `415` if it does not accept the request media type.
4. A sender must not send both per RFC 9112. The receiver/proxy must handle framing according to the standard and security policy, without arbitrarily picking one value.
5. There is no body for a `HEAD` response; if the field is sent, its value must match the number of bytes that would be sent by the corresponding `GET` response.
6. No: `Content-Length`, if present, must include all bytes of the multipart body. Let the HTTP/multipart library manage framing.
7. No. PNG is binary; `String` decoding can alter or lose bytes. Keep the raw bytes and pass them to a PNG decoder.
8. HTTP/1.1 typically uses chunked transfer coding when appropriate; HTTP/2 uses its own `DATA` frames and does not use HTTP/1.1 chunked.

## References

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html), especially the sections on `Content-Type`, `Content-Encoding`, and `Content-Length`.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html), message framing, `Transfer-Encoding: chunked`, and rules to avoid framing ambiguity.
- [RFC 8259 — JSON Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259.html), JSON UTF-8 and the `application/json` media type.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html), HTTP version selection and request handling.
- [Java SE 17 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html), sending strings, byte arrays, files, and streams.
- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html), receiving bytes or strings by charset.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html), local HTTP server used in the example.
- [Java SE 17 — HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html), request/response headers, body streams, and `sendResponseHeaders`.
- [Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html), explicit UTF-8 encoding across machines.
