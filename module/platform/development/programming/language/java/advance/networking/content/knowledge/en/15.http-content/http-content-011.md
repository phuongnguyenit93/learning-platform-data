# Form Encoding, JSON, and Multipart: The Boundary Between HTTP API and Data Encoders

## 1. The Problem: Why Can the Server Interpret the Same POST Data in Three Different Ways?

A Java application wants to send a username, a note, and an attachment to an HTTP server. If using `HttpClient`, it can send a `POST` request with different body types:

- `application/x-www-form-urlencoded`: **name–value fields** encoded into a byte string, typically in the form `name=Lan+Anh&note=a%2Bb`.
- `application/json`: data **serialized according to JSON syntax**, such as `{"name":"Lan Anh","active":true}`.
- `multipart/form-data`: a **MIME multipart body** with parts separated by a boundary; each part has its own headers and can contain text fields or **binary file bytes**.

All three can use the **same HTTP method POST, same URL, same HTTP version, and same TCP/TLS**, yet the **byte structure of the request body and the server-side decoding process differ**. If a client sends JSON while setting the header `Content-Type: application/x-www-form-urlencoded`, the server may pick the wrong parser and return an error; it does not automatically "recognize" JSON just because the content has curly braces.

**Key principle:**

> The HTTP API manages the method, URI, headers, status, and content transmission. The **encoder/serializer** decides which bytes objects/fields/files are converted into; the server-side **decoder/parser** must interpret those bytes according to the appropriate media type and contract.

In Java 17, `HttpClient` and `HttpRequest.BodyPublishers` **do not automatically turn a POJO into JSON or a Map into multipart** just because you choose `POST`. The developer or a dedicated library must build the right representation, attach the exact headers, test decoding capability, and enforce resource limits.

This lesson focuses on the **boundary between the HTTP API and data encoders**, without conflating encoding with transport, URL, content compression, or TLS.

## 2. Separating Four Responsibilities: Data → Bytes → HTTP → Business Logic

A request passes through the following boundaries:

```text
Data in Java application
  Map<String,String>, DTO, String, File/byte[]
         |
         | (1) Serializer / content encoder
         v
Byte sequence of the representation
  form percent-encoding / JSON UTF-8 / multipart MIME
         |
         | (2) HttpRequest.BodyPublisher + Content-Type
         v
HTTP message
  method + URI + request headers + request body
         |
         | (3) HttpClient + HTTP framing + TCP/TLS, depending on connection
         v
HTTP server
         |
         | (4) Check Content-Type, size, parser, validation
         v
Server-side Java entity/command → business logic processing
```

Several important boundaries:

1. **`Content-Type` describes the media type of the request content.** It does not perform serialization itself. Setting `Content-Type: application/json` on a body that is not yet JSON is wrong.
2. **`BodyPublisher` supplies bytes to the HTTP client.** `BodyPublishers.ofString(x, UTF_8)` encodes string `x` into UTF-8; **it does not automatically escape JSON fields, percent-encode forms, or generate multipart boundaries**.
3. **`Content-Length` or HTTP transfer framing** describes how the byte count is transmitted; it does not determine form/JSON/multipart syntax. Switching from HTTP/1.1 to HTTP/2 does not turn JSON into a form.
4. **Response status/body** is a separate matter: the server can return a JSON response even if the request sent multipart; request `Content-Type` and response `Content-Type` are two headers in **opposite directions**.
5. **Business logic** sits behind the parser: a body that decodes cleanly does not mean the user has permission to upload, the data is valid, or the payment succeeded.

### `Content-Type` and `Accept` Cannot Be Swapped

- `Content-Type: application/json` on a **request** says: "I am sending JSON".
- `Accept: application/json` on a **request** says: "I want to receive a response of this acceptable media type, if the server can provide it".
- `Content-Type: application/json` on a **response** says: "The response body is JSON".

`Accept` is not a toggle to enable a JSON serializer in `HttpClient`. If an API requires sending/receiving JSON, both the request body and the corresponding headers must be handled according to the contract.

## 3. Comparing Three Common Content Types

| Criterion | URL-encoded form | JSON | Multipart form-data |
|---|---|---|---|
| Header media type | `application/x-www-form-urlencoded` | `application/json` | `multipart/form-data; boundary=...` |
| Body structure | `key=value&key2=value2`, percent-encoding | Objects, arrays, strings, numbers, booleans, null per JSON | Multiple parts, boundary + per-part headers + content |
| Suitable data | Simple text forms, short fields | Nested structured APIs, DTOs | Combining fields and file uploads |
| Text encoding | Form URL encoding rules, usually UTF-8 | JSON serialization, UTF-8 for network interchange | Text per part/form charset convention; binary kept as raw bytes |
| Binary file | Inconvenient: must be represented as text/extra encoding | Must be converted to a string like base64 per contract | **Supports files as raw bytes inside a part** |
| Server-side parser | Form decoder | JSON parser | MIME multipart parser |
| Delimiters | `&`, `=`, and `%HH` | JSON tokens/escapes | `--boundary` and CRLF per MIME |
| Built-in Java 17 | `URLEncoder`/`URLDecoder` + BodyPublisher | BodyPublisher accepts String/bytes; **no standard JSON object mapper built into HttpClient** | Can construct bytes/stream manually; **no high-level multipart form builder helper built into HttpClient** |
| Common mistakes | Encoding the entire string wrongly, confusing `+` and `%2B` | Concatenating JSON manually, wrong escapes/types | Wrong boundary, broken CRLF, converting binary to text |
| Resource protection | Limit field count/size | Limit nesting/depth/size | Limit part count, file size, total size, filename |

**Do not choose a media type based on the HTTP method.** `POST`/`PUT` can carry JSON, form, or multipart depending on the endpoint; `GET` typically has no request content defined by general semantics. What matters is that **the server and client agree on the same media type and schema contract**.

## 4. `application/x-www-form-urlencoded`: Encoded Field Pairs

### 4.1. Structure

Suppose a form has:

```text
name = Cà phê
note = a+b&c=d
```

When using UTF-8 and form encoding, the body becomes:

```text
name=C%C3%A0+ph%C3%AA&note=a%2Bb%26c%3Dd
```

Explanation:

- The `=` sign **separates the field name and the encoded value**.
- The `&` sign **separates field pairs**.
- A space **inside a value** is represented by `+` per `application/x-www-form-urlencoded` rules.
- A literal plus sign **as data** must be encoded as `%2B`; if left unencoded, the decoder will interpret it as a space.
- An `&` inside a value must be encoded as `%26`; an `=` inside a value as `%3D`.
- Unicode characters such as `à` are converted to UTF-8 bytes and then to `%HH`; for example, UTF-8 for `à` is `C3 A0`, so it is represented as `%C3%A0`.

These are **form encoding rules**, not simply "URL-encoding the entire URL". Distinguish this from URI syntax: form decoding treats `+` as a space, whereas in a URL path, a literal plus sign is not by default a space.

### 4.2. Java 17: Encode Each Key/Value

```java
// Illustrative snippet inside a method.
String encoded = "name="
        + URLEncoder.encode("Cà phê", StandardCharsets.UTF_8)
        + "&note="
        + URLEncoder.encode("a+b&c=d", StandardCharsets.UTF_8);

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/form"))
        .header("Content-Type",
                "application/x-www-form-urlencoded; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                encoded, StandardCharsets.UTF_8))
        .build();
```

Note that `URLEncoder.encode` belongs to `java.net.URLEncoder`, not `HttpClient`. It encodes **field values** according to form rules and does not provide a general URL builder for path/query/fragment.

**Wrong:**

```java
// Intentionally wrong code: encoding the whole body after joining & and =.
String wholeForm = "name=Cà phê&note=a+b";
String wrong = URLEncoder.encode(
        wholeForm, StandardCharsets.UTF_8);
// The = and & field separators are also encoded -> form structure is lost.
```

**Right:** encode **each field name and each value**, then join pairs with `=` and `&`. For multiple values with the same name (e.g., checkboxes `tag=A&tag=B`), the server must know the contract for **repeated keys**; do not arbitrarily convert into a Map that keeps only the last value.

### 4.3. `URLDecoder` Is Only for Form-Encoded Data

On the receiving side, a form parser typically:

1. Determines the charset and reads the body bytes within limits.
2. Properly splits pairs and key/value, handling percent-escapes per standard.
3. Decodes `+` to space and `%HH` to byte.
4. Decodes bytes using the agreed charset (usually UTF-8).
5. Applies data type validation, required fields, size, and duplicate policy.

Do not call `URLDecoder.decode` arbitrarily on every URL/path/raw JSON: turning `+` into a space will corrupt URIs or non-form data. Decoding twice can also lead to filter bypasses; avoid double-encoding/double-decoding between reverse proxy and application.

### 4.4. When Is Form Appropriate?

- Simple text form fields from HTML or legacy clients.
- OAuth/token endpoints or APIs with an explicit `application/x-www-form-urlencoded` contract.
- Small, flat payloads with no binary files.

Forms are not nested JSON structures. If you need arrays, deep objects, or distinction among numbers/booleans/null, using a dedicated contract or JSON is usually clearer. A form field is fundamentally always transmitted as text; the server must validate/convert it rather than assuming `"42"` is a safe integer.

## 5. `application/json`: Serialization with Its Own Syntax and Data Types

### 5.1. JSON Represents Structured Data

Sample JSON body:

```json
{
  "name": "Cà phê",
  "active": true,
  "quantity": 2,
  "tags": ["drink", "local"],
  "address": null
}
```

Unlike forms:

- Strings must be enclosed in double quotes and special characters **escaped per JSON syntax**.
- `true`, `false`, `null`, numbers, and arrays/objects have distinct semantics. `"42"` is different from the number `42`.
- JSON can be nested multiple levels; the parser should limit total size, nesting depth, and complexity.
- Property names and schema/validation are decided by the API. Not every JSON object is valid just because the parser accepts its syntax.

### 5.2. `BodyPublisher.ofString` Is Not a JSON Serializer

```java
// Illustrative code: already-valid JSON literal, independent of external variables.
String json = "{\"name\":\"Cà phê\",\"active\":true}";

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/api/items"))
        .header("Content-Type", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, StandardCharsets.UTF_8))
        .build();
```

The snippet above sends the bytes of an existing JSON string. **`BodyPublishers.ofString` does not validate JSON, does not automatically escape a DTO, and knows nothing about JSON schema**. If `json` is `"hello"` with proper quotes, it still sends those string bytes; whereas a Java string `hello` without JSON quoting will not be a valid JSON string.

### 5.3. Do Not Concatenate JSON from Untrusted Data

**Wrong:**

```java
// Intentionally wrong code: external input may contain " and control characters.
String json = "{\"name\":\"" + userInput + "\"}";
```

If `userInput` is `Alice "QA"`, manually concatenated JSON can become syntactically invalid. If the input contains escape characters, control characters, or unexpected structure, the bug is even more severe.

**Right in real applications:** use a serializer such as Jackson/Gson/Jakarta JSON to convert a DTO/Map into JSON bytes; handle API validation and field whitelisting separately. Conceptual example (not standalone code since it requires an external dependency):

```java
// Illustrative snippet with Jackson when the project already includes the library.
byte[] jsonBytes = objectMapper.writeValueAsBytes(dto);
HttpRequest.BodyPublisher publisher =
        HttpRequest.BodyPublishers.ofByteArray(jsonBytes);
```

A real serializer must safely handle escaping, Unicode, type mapping, unknown properties configuration, date/time, large numbers, null, and polymorphic types. **Do not trust data from a JSON response/request just because the serializer succeeded**; schema validation, authorization, and business rules are still necessary.

### 5.4. Charset of JSON

JSON exchanged between systems over the Internet is standardized to use UTF-8 (RFC 8259). The `application/json` media type **has no `charset` parameter defined in the media type registration per RFC 8259**; some legacy APIs use `application/json; charset=UTF-8` to convey the convention, but **you should not rely on the charset parameter to alter modern JSON decoding**. When using Java, proactively produce UTF-8 bytes.

In the runnable example below, the header includes `application/json; charset=UTF-8` to compare with the form and verify exact matching with the demo client/server, **not as a recommendation to always attach charset to every JSON request**. In new applications, `Content-Type: application/json` + UTF-8 bytes is the normal choice.

### 5.5. JSON and Binary

A JSON string cannot carry arbitrary raw binary bytes and remain valid JSON text. If an API truly needs to attach a file via JSON, it can agree on a base64 string and decode it, but the payload grows in size and complicates memory/validation. For uploading files alongside fields, **multipart** is usually more suitable. There are also cases where raw `application/octet-stream` or `image/png` is sent directly for a known resource; not every upload has to be multipart.

## 6. `multipart/form-data`: Boundary and Individual MIME Parts

### 6.1. Why Is Multipart Different from Form/JSON?

When a browser submits a form with a file, the body can consist of **multiple parts**. Each part contains:

- A **delimiter** separating parts according to `boundary`.
- **Part headers**, especially `Content-Disposition: form-data; name="..."`; for files, typically `filename="..."` and `Content-Type`.
- A **blank CRLF line**, followed by the **part content**: encoded text or file bytes.
- At the end of the body, a **closing delimiter** `--boundary--`.

Descriptive example (text field + small text file, not a full binary body):

```http
POST /upload HTTP/1.1
Host: example.test
Content-Type: multipart/form-data; boundary=DemoBoundaryX9

--DemoBoundaryX9
Content-Disposition: form-data; name="label"

Cà phê
--DemoBoundaryX9
Content-Disposition: form-data; name="file"; filename="data.bin"
Content-Type: application/octet-stream

...raw binary file bytes...
--DemoBoundaryX9--
```

In **actual** bytes, MIME/boundary lines are separated by **CRLF = `\r\n`**, not arbitrary `\n` newlines; the example above is formatted for readability. Remember that the request's `Content-Type` header **must have a boundary parameter matching the body delimiter exactly**.

### 6.2. What Is a Boundary?

With the header:

```http
Content-Type: multipart/form-data; boundary=DemoBoundaryX9
```

The delimiters in the body are prefixed with two hyphens:

- Start of part: `--DemoBoundaryX9\r\n`
- End of part headers: `\r\n\r\n`
- To next part: `\r\n--DemoBoundaryX9\r\n`
- End of multipart: `\r\n--DemoBoundaryX9--\r\n`

**Do not confuse the `boundary=...` parameter with the `--boundary` delimiter line**. The header value does **not** automatically include the two-hyphen prefix; the delimiter adds `--` per the multipart format.

The boundary must be syntactically valid and **must not appear as a delimiter sequence inside the content of any part**. In production, use an ASCII boundary unlikely to collide, ensuring that all body parts, the Content-Type header, and the stream builder share **the exact same value**. Some libraries generate the boundary automatically; **do not manually overwrite `Content-Type` with a different boundary than the one the library generated**.

### 6.3. Files Are Kept as Bytes

A binary file such as `00 0D 0A FF 2A` must go into the part **as exact bytes**, not converted via `new String(fileBytes, UTF_8)` and then `getBytes(UTF_8)` to send. The byte `FF` may not be valid UTF-8 and will be altered during text decoding.

For a text part like `label = Cà phê`, the application can explicitly choose UTF-8, and the server/parser needs to know the corresponding charset. For a file part, `Content-Type: application/octet-stream` or the file's exact media type describes the data; however, the server must still inspect the actual file rather than blindly trusting headers sent by the client.

### 6.4. `Content-Disposition`, `name`, `filename`

A part typically has:

```http
Content-Disposition: form-data; name="file"; filename="photo.png"
Content-Type: image/png
```

- `name` is the **field name**, for the server to map into the form API.
- `filename` is the **name declared by the sender**, not a path permitted to be written directly on the server.
- The part's `Content-Type` describes the **type of content inside the part**, distinct from `Content-Type: multipart/form-data` at the whole-request level.

**Filename security:** do not trust `filename` from the client. Strip path separators, special names, and NUL/control characters; generate a server-side name and write into a permission-restricted directory. Check extension/MIME signature and malware per policy; never allow writing files outside the intended directory (path traversal).

### 6.5. Text Fields and Files in the Same Request

A multipart request can have multiple fields with the same name, multiple files, ordered parts, and parts without a filename. The server needs a contract for handling **repeated fields**, maximum part count, empty files/empty fields, and size limits. Avoid assuming "multipart = exactly one file".

**There is no automatic checksum/business-success guarantee** just because multipart was transmitted over HTTP. If an upload requires integrity, verify bytes/hash, store temporarily, inspect the file, commit, and respond with a resource ID per contract.

## 7. Boundary with the Java 17 API: `BodyPublisher` + `Content-Type`

In `java.net.http`, `HttpRequest.BodyPublisher` supplies the body bytes for the request; `HttpRequest.Builder.header("Content-Type", ...)` adds metadata. These two operations **do not magically synchronize formats with each other**.

| Data to send | Commonly used `BodyPublisher` | Appropriate `Content-Type` |
|---|---|---|
| UTF-8 percent-encoded form | `BodyPublishers.ofString(form, UTF_8)` | `application/x-www-form-urlencoded`, optionally specifying charset |
| JSON produced by a serializer | `ofString(json, UTF_8)` or `ofByteArray(jsonBytes)` | `application/json` |
| Multipart built into bytes by a builder | `ofByteArray(multipartBytes)` | `multipart/form-data; boundary=...` |
| Large multipart with streaming | `BodyPublishers.ofInputStream(supplier)` or custom publisher | `multipart/form-data; boundary=...` |
| Whole binary file | `BodyPublishers.ofFile(path)` | `application/octet-stream` or the file's media type |
| No request body | `BodyPublishers.noBody()` | Usually no `Content-Type` header needed |

**Note:** JDK 17 `HttpClient` has no standard high-level `multipartBuilder()` factory. Examples using `MultipartEntityBuilder` belong to Apache HttpClient or other libraries, **not** the JDK built-in `java.net.http.HttpClient`. You can assemble bytes manually as in the demo, but you should use a reliable multipart library for production servers/clients.

### Where Does `Content-Length` Come From?

- `ofString` produces bytes according to the charset, and the runtime can know the body length.
- `ofByteArray` normally knows the length from the number of bytes in the array.
- `ofInputStream` may not know the total byte count in advance; HTTP framing depends on the protocol/implementation.

You **should not compute `Content-Length` using `String.length()`**, because Java `String` measures UTF-16 code units, whereas HTTP content length is measured in **content bytes**. With Unicode, a single character can take multiple UTF-8 bytes.

### Do Not Manually Modify `Transfer-Encoding`

`Transfer-Encoding` in HTTP/1.1 and framing in HTTP/2 are the responsibility of the HTTP client/transport. Do not edit `Content-Type` to "enable chunked", and do not use URL-encoding as a workaround for framing. **`Content-Encoding`** (e.g., gzip) is a content coding/transformation layer distinct from MIME media type and form percent-encoding.

### Synchronous vs. Asynchronous Does Not Change Representation

`client.send(...)` and `client.sendAsync(...)` can both use the same `HttpRequest`/`BodyPublisher`. The main difference is how **responses are awaited and completion is managed**, not in the definition of `application/json`/`multipart/form-data`. Wrong percent-encoding or boundary will be wrong whether using the sync or async API.

## 8. Runnable Java 17: Three POSTs with the Same `HttpClient`, Different `BodyPublisher` and `Content-Type`

To verify this knowledge **without needing the Internet, DNS, or frameworks**, the following program starts a `com.sun.net.httpserver.HttpServer` on loopback, sends three POST requests to three paths, and prints the results:

1. **Form:** uses `URLEncoder.encode` on each value, builds the form string, and sends with `ofString(form, UTF_8)`.
2. **JSON:** uses a **fixed, already-valid JSON literal** for the demo, sent in UTF-8 with `ofString`. Production must use a serializer to convert dynamic data.
3. **Multipart:** uses `ByteArrayOutputStream` to create CRLF delimiters, two parts `label` and `file`, preserves file bytes `00 0D 0A FF 2A`, and sends with `ofByteArray` and a `Content-Type` containing the **same boundary**.

The demo server **is not a general-purpose multipart parser**. It checks `Content-Type` and compares the received byte sequence against a fixture generated by `multipartBody()`. This integrity check proves that binary bytes are preserved across transport; it does not replace real MIME multipart parsing, size limits, streaming, and validation.

Create the file **`HttpEntityEncodingDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;

public class HttpEntityEncodingDemo {
    private static final String BOUNDARY = "DemoBoundaryX9";
    private static final String FORM_TYPE =
            "application/x-www-form-urlencoded; charset=UTF-8";
    private static final String JSON_TYPE =
            "application/json; charset=UTF-8";
    private static final String MULTIPART_TYPE =
            "multipart/form-data; boundary=" + BOUNDARY;
    private static final byte[] FILE_BYTES =
            {0, 13, 10, (byte) 0xff, 42};

    private static void writeAscii(
            ByteArrayOutputStream out, String value) {
        out.writeBytes(value.getBytes(StandardCharsets.US_ASCII));
    }

    private static byte[] multipartBody() {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        writeAscii(out, "--" + BOUNDARY + "\r\n");
        writeAscii(out,
                "Content-Disposition: form-data; name=\"label\"\r\n"
                + "\r\n");
        out.writeBytes("Cà phê".getBytes(StandardCharsets.UTF_8));

        writeAscii(out, "\r\n--" + BOUNDARY + "\r\n");
        writeAscii(out,
                "Content-Disposition: form-data; name=\"file\";"
                + " filename=\"data.bin\"\r\n");
        writeAscii(out,
                "Content-Type: application/octet-stream\r\n\r\n");
        out.writeBytes(FILE_BYTES);

        writeAscii(out, "\r\n--" + BOUNDARY + "--\r\n");
        return out.toByteArray();
    }

    private static void respond(
            HttpExchange exchange, int code, String message)
            throws IOException {
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(code, bytes.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
        exchange.close();
    }

    private static void handle(HttpExchange exchange)
            throws IOException {
        if (!"POST".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "Only POST");
            return;
        }

        String path = exchange.getRequestURI().getPath();
        String contentType = exchange.getRequestHeaders()
                .getFirst("Content-Type");
        byte[] received = exchange.getRequestBody().readAllBytes();

        if ("/form".equals(path) && FORM_TYPE.equals(contentType)) {
            respond(exchange, 200, "FORM "
                    + new String(received, StandardCharsets.UTF_8));
        } else if ("/json".equals(path)
                && JSON_TYPE.equals(contentType)) {
            respond(exchange, 200, "JSON "
                    + new String(received, StandardCharsets.UTF_8));
        } else if ("/multipart".equals(path)
                && MULTIPART_TYPE.equals(contentType)) {
            // Check bytes of test payload, not a MIME parser.
            boolean exact = Arrays.equals(
                    received, multipartBody());
            respond(exchange, exact ? 200 : 400,
                    "MULTIPART integrity=" + exact);
        } else {
            respond(exchange, 415, "Unsupported content type");
        }
    }

    private static HttpResponse<String> post(
            HttpClient client, String base, String path,
            String contentType, HttpRequest.BodyPublisher publisher)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(base + path))
                .header("Content-Type", contentType)
                .timeout(Duration.ofSeconds(3))
                .POST(publisher)
                .build();
        return client.send(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByAddress(
                                new byte[] {127, 0, 0, 1}), 0), 0);
        server.createContext("/", HttpEntityEncodingDemo::handle);
        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            // HttpClient is not AutoCloseable in Java 17.
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();

            String form = "name="
                    + URLEncoder.encode(
                            "Cà phê", StandardCharsets.UTF_8)
                    + "&note="
                    + URLEncoder.encode(
                            "a+b&c=d", StandardCharsets.UTF_8);
            HttpResponse<String> formResult = post(
                    client, base, "/form", FORM_TYPE,
                    HttpRequest.BodyPublishers.ofString(
                            form, StandardCharsets.UTF_8));

            // This JSON is a trusted literal for demo; do not concatenate
            // user data into JSON using string concatenation.
            String json = "{\"name\":\"Cà phê\",\"active\":true}";
            HttpResponse<String> jsonResult = post(
                    client, base, "/json", JSON_TYPE,
                    HttpRequest.BodyPublishers.ofString(
                            json, StandardCharsets.UTF_8));

            byte[] multipart = multipartBody();
            HttpResponse<String> multiResult = post(
                    client, base, "/multipart", MULTIPART_TYPE,
                    HttpRequest.BodyPublishers.ofByteArray(multipart));

            if (formResult.statusCode() != 200
                    || jsonResult.statusCode() != 200
                    || multiResult.statusCode() != 200) {
                throw new IllegalStateException(
                        "Unexpected HTTP response");
            }

            System.out.println(
                    "FORM status=" + formResult.statusCode());
            System.out.println("FORM data="
                    + formResult.body().substring("FORM ".length()));
            System.out.println(
                    "JSON status=" + jsonResult.statusCode());
            System.out.println("JSON data="
                    + jsonResult.body().substring("JSON ".length()));
            System.out.println(
                    "MULTIPART status=" + multiResult.statusCode());
            System.out.println(multiResult.body());
            System.out.println(
                    "Binary file bytes=" + FILE_BYTES.length);
        } finally {
            server.stop(0);
        }
    }
}
```

Compile/run with **JDK 17 or higher**, using only built-in JDK modules; `HttpServer` belongs to the `jdk.httpserver` module:

```bash
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 HttpEntityEncodingDemo.java
java --add-modules jdk.httpserver HttpEntityEncodingDemo
```

**Exact stdout in an environment allowing TCP loopback:**

```text
FORM status=200
FORM data=name=C%C3%A0+ph%C3%AA&note=a%2Bb%26c%3Dd
JSON status=200
JSON data={"name":"Cà phê","active":true}
MULTIPART status=200
MULTIPART integrity=true
Binary file bytes=5
```

### Reading the Results

- `FORM data` shows `URLEncoder` turning spaces into `+`, the character `à` into `%C3%A0`, and `+`, `&`, `=` inside data into percent-escapes.
- `JSON data` is **JSON text with intact syntax**, not a Java object automatically serialized by `HttpClient`. In the demo, the JSON is a fixed, already-valid string literal.
- `MULTIPART integrity=true` means the raw bytes of the entire multipart body arrived at the server matching the fixture bytes; the file bytes containing `00`, `0D`, `0A`, `FF`, and `2A` **did not pass through String decoding**.
- The same `HttpClient` and the same HTTP method `POST` sent three different content types thanks to the **BodyPublisher** and **Content-Type** configured accordingly.
- The demo server calls `readAllBytes()` only because the bodies are **small, fixed, and controlled**. Do not copy this pattern to public uploads: production must limit request size, use a streaming parser, enforce quotas/timeouts, and validate each part.
- `HttpClient` in Java 17 is not `AutoCloseable`; do not use try-with-resources on the client. The server has `stop(0)` in `finally` for cleanup.

**What must not be inferred:** `integrity=true` from a fixture comparison **does not prove** the program has a general-purpose multipart parser. A real MIME parser must locate delimiters properly in a binary stream, handle field names, headers, charsets, multiple files, multiple parts, filenames, errors, and resource limits.

## 9. Server Side: Choosing the Right Decoder by `Content-Type`

When the server receives an HTTP request, it must resolve **two distinct validation layers**:

1. **Is the media type allowed?** The `/upload` endpoint may allow `multipart/form-data`, while `/api/items` only allows `application/json`. If the body type is unsupported, status **`415 Unsupported Media Type`** is a common standard choice.
2. **Are the bytes syntactically/schema-valid?** Invalid JSON syntax, invalid percent-escapes, or multipart missing a boundary/closing delimiter must all be handled as input errors; `400 Bad Request` or another validation status may be returned per contract.

Do not assume a request is acceptable just because `Content-Type` is right. Headers can be self-declared by an attacker; the parser must still check bytes and limits.

### 9.1. A Form Parser Is Not a JSON Parser

`Content-Type: application/x-www-form-urlencoded` is typically parsed by server frameworks into a name–value multi-map. Repeated fields `tag=one&tag=two` must follow an explicit policy; an implementation that keeps only the last value can lose data. On the client, each value is percent-encoded rather than writing raw `&` inside data.

### 9.2. A JSON Parser Needs Validation Beyond Syntax

Receiving `{"role":"admin"}` may be completely valid JSON yet violate the caller's permission to modify roles. The server must whitelist writable fields, check enums, numbers, and lengths, guard against prototype/property injection depending on the language/framework, and verify authorization. For polymorphic deserialization, use safe configuration; do not deserialize arbitrary classes from input.

### 9.3. A Multipart Parser Must Handle Binary Properly

- Use a library that knows how to read MIME multipart and stream.
- Limit total body size, single-part size, part count, filename length, header size, and receive time.
- Generate server-side filenames, use permission-restricted temporary storage, and scan content when policy requires.
- Do not trust a file's `Content-Type`, and do not execute files or expose them at a public URL immediately.
- Do not concatenate file bytes into a Java `String` to split boundaries; if writing a parser for study, handle bytes/streams and MIME standards carefully.
- For repeated field names and multiple files, clearly define mapping to lists/collections at the application layer.

**Do not** rely on an external `filename` or `Content-Length` to allocate unbounded arrays. A request body may lack `Content-Length` or exceed the application limit; quotas must be enforced while reading, not only checked after buffering all bytes.

## 10. Encoding, Charset, `Content-Type`, `Content-Encoding`, and TLS

These terms can appear together in a single request, but they are **different layers**:

| Term | Responsibility | Example |
|---|---|---|
| **Form percent-encoding** | Represent characters of names/values in `%HH`, `+` syntax | `a+b%26c` |
| **JSON serialization** | Convert structured data into standard JSON text | `{"count":2}` |
| **Multipart MIME encoding** | Assemble multiple parts with boundaries, headers, and bytes | `--B\r\n...` |
| **Charset (UTF-8)** | Convert text to bytes and vice versa | `Cà phê` → UTF-8 bytes |
| **`Content-Type`** | Identify the media type of the content | `application/json` |
| **`Content-Encoding`** | Content coding (if applied) such as gzip | `Content-Encoding: gzip` |
| **HTTP framing** | Transmit messages with proper byte boundaries | `Content-Length`/HTTP/1.1 chunked/HTTP/2 frames |
| **TLS** | Secure the transport channel, authenticate peer per configuration | HTTPS |

**Misconception:** "I set `Content-Type` to JSON so `HttpClient` will escape user input into JSON." The header only describes the content. Conversely, you can serialize JSON correctly yet forget `Content-Type`; server middleware may pick a different decoder, reject it, or fail to parse it.

**Misconception:** "Multipart already contains files, so it encrypts/protects against eavesdropping." Multipart is a content format, **not security encryption**. To protect the transport channel, use HTTPS/TLS and access controls; to protect stored data, another mechanism is required.

**Misconception:** "UTF-8 is gzip." UTF-8 converts characters to bytes, whereas gzip compresses bytes; the processing order and headers are different.

## 11. Streaming and Memory Management for Large Bodies

`BodyPublishers.ofByteArray` and `ofString` typically represent content already in memory. For files of hundreds of MiB or multi-file uploads, creating a single `byte[]` for the entire multipart body can cause heavy heap pressure.

Available approaches:

- **Streaming multipart builder**: creates a sequence of publishers/reads files as streams, emitting headers/part data/boundaries in the right order without buffering all bytes upfront. Use a supporting library if available.
- **`BodyPublishers.ofFile(path)`**: suitable when the request body itself is the file (does not wrap in multipart); if the endpoint expects multipart, an additional builder layer is required.
- **`BodyPublishers.ofInputStream(supplier)`**: can supply an input stream, but the supplier, retry/replay capability, and cleanup must be designed. Do not assume a single-use stream can be safely replayed after a redirect/auth challenge.
- **Reactive/custom publisher**: used when backpressure and explicit lifecycle are needed, with limits on concurrency, outstanding writes, and cancellation.
- **Server-side streaming parser**: receives chunks and enforces quotas early, instead of `readAllBytes()` on untrusted input.

**Be careful with retries:** If the client must resend a request after an error, a `BodyPublisher` wrapping a file/stream may not support automatic replay or the data may have changed between attempts. Design the content source to be able to open a new stream/reference an immutable file, or do not auto-retry without guarantees.

### Budget for the Entire Request

Required limits:

- Total request size.
- Size per field, per file, and number of fields/parts.
- Body receive time and parse time.
- CPU for JSON nesting/number parsing and multipart boundary search.
- Temporary disk space and total quota per user/tenant.
- Concurrent uploads, concurrency, and backpressure.
- Business timeouts, authorization, and temporary file cleanup on failure.

**No `Content-Type` header automatically sets these limits.**

## 12. Security Risks in Each Format

### 12.1. Form

- Incorrect or double decoding can bypass access checks/data filtering.
- Unexpected repeated fields can bypass policies if the gateway and application pick different values.
- Form data still needs CSRF protection when using cookie-based browser workflows; percent-encoding **does not prevent CSRF**.
- Do not treat forms as safe to log passwords just because the body "looks like a query string".

### 12.2. JSON

- Syntactically valid JSON input can still violate the schema: negative amounts, admin privileges, disallowed enums.
- The parser must handle duplicate object names per contract. Do not assume all parsers keep the first/last key consistently.
- Limit nesting depth, element count, and size to reduce DoS risk.
- Serializer/deserializer libraries must be configured safely regarding polymorphism and data types; do not use arbitrary class loading from input.

### 12.3. Multipart

- Filenames, paths, extensions, MIME headers, and file contents are all untrusted data.
- Long/malformed boundaries, millions of tiny parts, oversized files, or abnormal part headers can exhaust parser resources.
- Check hash/virus/signature when business logic requires; stage temporarily and commit safely.
- Unicode part text/filenames may need specific encoding rules; avoid turning `filename` directly into a filesystem path.
- Never let an attacker pick a server-side file via `filename=../../secret`.
- A completed HTTP file upload does not mean the file has been scanned/indexed/committed to domain storage.

## 13. Choosing a Format by Requirement and Testing

| Practical need | Suggested format | Reason |
|---|---|---|
| Simple text form passing key–value pairs | `application/x-www-form-urlencoded` | Easy compatibility with form endpoints, but each field must be encoded |
| API creating objects with numbers, booleans, arrays, nested fields | `application/json` | Clear syntax/data types, uses standard serializer/parser |
| File upload with description, category, and multiple fields | `multipart/form-data` | Each part has metadata, files transfer bytes without JSON escaping |
| Uploading a single whole file to a dedicated URI | `application/octet-stream` or file media type | No need for multipart overhead |
| Client sending a compressed payload | Actual media type + appropriate `Content-Encoding` | Content coding is independent of serialization |
| API does not accept the sent body type | Return `415` when semantically appropriate | Client must adjust `Content-Type`/representation per contract |

### Testing Client/Server at the Boundary

1. **Golden bytes test**: for forms, verify exact percent-encoding; for JSON, verify the parser reads the right types; for multipart, verify binary hash/byte-for-byte.
2. **Media type test**: right `Content-Type` succeeds; wrong media type is rejected cleanly, not parsed arbitrarily.
3. **Charset test**: Unicode `Cà phê`, emoji, accented characters, plus sign, ampersand, quotes, backslash, control characters.
4. **Multipart boundary test**: missing/mismatched boundary, missing closing delimiter, non-standard CRLF, malformed part headers, repeated parts.
5. **Limits**: file exceeding quota, too many parts, overly deep JSON, too many form fields, timeout, truncated request body.
6. **Security**: `filename` containing `../`, absolute names, NUL, spoofed MIME, HTML/script payloads, malicious files.
7. **Response**: status `200/201/202/204/400/413/415/422` per API contract; client does not mistake an error body for a success response.
8. **Concurrency**: multiple simultaneous uploads, temporary resources cleaned up, no cross-tenant file overwrites.
9. **Retry**: whether the `BodyPublisher` is replayable by design; operations with side effects have idempotency keys and deadlines.

Do not just compare `String` after decoding multipart binary: it can lose bytes. Use byte-for-byte comparison or a suitable checksum for the raw payload, and a dedicated parser for the MIME structure.

## 14. Common Mistakes: Confusing Layers

| Mistake | Why it is wrong | How to fix |
|---|---|---|
| Setting `Content-Type: application/json` but sending text `name=Lan` | The header does not turn text into JSON | Serialize valid JSON and set a matching header |
| Assuming `BodyPublishers.ofString(dto.toString())` is JSON | `toString()` does not follow JSON schema/escaping | Use a serializer |
| Concatenating JSON via `"{...}" + userInput` | Missing escaping, wrong types, structural injection | Serialize objects via a library |
| URL-encoding the **entire form string** | Encodes away the `&`/`=` separators | Encode each key/value then join |
| Using `URLEncoder` for the whole URL/path | `+`, `/`, and reserved characters have different semantics | Use a URI builder/per-component escaping |
| Forgetting to encode `+` in a field | Decoder interprets `+` as a space | `URLEncoder.encode("a+b", UTF_8)` produces `a%2Bb` |
| Forgetting consistent charset | Unicode turns into garbled characters | UTF-8 on encode/decode, specified clearly in contract |
| Sending `multipart/form-data` without a boundary | Server does not know the delimiter | Let the builder generate matching header/boundary |
| Writing header boundary A but body boundary B | Parser fails/splits parts wrongly | Use a single boundary value for both |
| Using `\n` instead of `\r\n` in MIME part delimiters | Invalid multipart wire format | Use standard CRLF |
| Converting file bytes to `String` then back to bytes | Can corrupt binary (e.g., `0xFF`) | Write raw bytes into stream/publisher |
| Trusting client-supplied `filename` | Path traversal/file overwrite | Generate server-side name, validate, sandbox |
| Trusting a file's MIME header as safe | Client can spoof media type | Inspect/scan/enforce content policy |
| Using `readAllBytes()` for unbounded public uploads | Memory exhaustion | Streaming + quota |
| Assuming `ofFile(path)` wraps in multipart | It emits file content, not form fields/boundary | Use a multipart builder |
| Computing `Content-Length` with `String.length()` | UTF-8 Unicode characters have different byte lengths | Let `BodyPublisher`/HTTP client compute/stream properly |
| Thinking `Content-Type` is gzip or TLS | Confuses serialization/compression/transport layers | Distinguish `Content-Type`, `Content-Encoding`, HTTPS |
| Thinking POST always uses JSON | POST accepts many media types per contract | Choose the right endpoint/format |
| Seeing HTTP 200 and assuming the upload is fully processed | Server may stage, scan/commit later | Rely on resource/status contract |
| Retrying multipart uploads infinitely on timeout | Can create duplicate resources and waste bandwidth | Idempotency + retry limit + resume policy |
| Not closing input/file streams on error | Leaks descriptors/temp files | `try-with-resources`/cleanup |
| Assuming Java 17 `HttpClient` has a JSON/multipart serializer | `HttpClient` only transports request/response body publishers | Use an appropriate serializer/parser/builder |

## 15. Exercises and Self-Check Questions

**Question 1.** Why can form, JSON, and multipart all be sent using `POST`?

**Answer:** `POST` is an HTTP method defining the request-handling semantics at a resource. The **request content** syntax is described separately by `Content-Type` and the bytes produced by the serializer/`BodyPublisher`.

**Question 2.** What does `name=Lan+Anh` in a form decode to? How do you send literal `Lan+Anh`?

**Answer:** `Lan Anh`, because `+` represents a space in form encoding. To send a literal plus sign, percent-encode `+` as `%2B`.

**Question 3.** Why can `URLEncoder.encode("name=A&B", UTF_8)` not replace encoding each field separately and then joining?

**Answer:** It also encodes `=`/`&`, which are form separators, turning the whole string into a single value component and destroying the field structure.

**Question 4.** Does `HttpRequest.BodyPublishers.ofString(json, UTF_8)` guarantee that `json` is valid JSON?

**Answer:** No. It only converts a `String` into bytes per charset. Use a JSON serializer to produce content and a server-side parser/validator to verify it.

**Question 5.** A Java object has fields `active=true` and `count=2`. Should JSON send them as strings `"true"`, `"2"` or as boolean/number?

**Answer:** If the contract requires boolean and number, JSON must carry `true` and `2` without quotes. A proper serializer preserves data types per the model; form encoding mainly converts fields to text.

**Question 6.** A multipart header says `boundary=abc123`. What is the delimiter starting a part?

**Answer:** `--abc123\r\n`. `--` is prepended to the boundary value in the body; the closing delimiter is `--abc123--` with CRLF in the appropriate positions.

**Question 7.** If a file contains byte `0xFF` which is not valid UTF-8, can you read the file into a `String` and re-encode it before sending multipart?

**Answer:** No. Converting through `String` can replace invalid bytes and corrupt the data. Keep file bytes intact in the part.

**Question 8.** Does `BodyPublishers.ofFile(path)` automatically generate multipart part headers and the closing boundary?

**Answer:** No. It supplies the file content; a separate builder is needed if the endpoint requires `multipart/form-data`.

**Question 9.** The server sees `Content-Type: application/json` but the payload is `name=A&b=B`. What should it do?

**Answer:** Select the parser by media type and return a clear client error when syntax/schema is invalid. Do not guess and deserialize arbitrarily if the contract does not allow it.

**Question 10.** Must `application/json` include `charset=UTF-8` in the header?

**Answer:** No. RFC 8259 specifies UTF-8 for JSON interchange between systems and does not define a `charset` parameter on the media type. Produce UTF-8 bytes and set `Content-Type: application/json` per contract.

**Question 11.** If the browser has already generated a boundary for `FormData`, should you overwrite `Content-Type` with literal `multipart/form-data`?

**Answer:** No. Overwriting can cause a missing/mismatched boundary. Let the browser/library generate a `Content-Type` matching the payload's boundary.

**Question 12.** Does the part header `Content-Disposition: form-data; name="file"; filename="../../secret"` allow the server to write to that path?

**Answer:** No. `filename` is untrusted data posing a path traversal risk; the server must use a name/path it controls and validate against policy.

**Question 13.** Why should `Content-Length` not be taken from `json.length()`?

**Answer:** `String.length()` counts UTF-16 code units, whereas HTTP length counts encoded body bytes. UTF-8 Unicode can occupy multiple bytes.

**Question 14.** Why does the demo server returning `MULTIPART integrity=true` not prove there is a production multipart parser?

**Answer:** The demo only compares all received bytes against a known fixture. A real parser must split parts/boundaries on arbitrary data, handle binary, charsets, part counts, filenames, and resource limits.

**Question 15.** If an upload endpoint returns `202 Accepted`, does that mean the file has been virus-scanned, durably stored, and published?

**Answer:** No. `202` only indicates acceptance for processing; you must track status and confirm progress/commit per contract.

**Question 16.** A client POSTs multipart with a non-rereadable file stream; the HTTP request times out. Should it retry immediately and unconditionally?

**Answer:** No. The stream may not be replayable, and the server may have already received part/all of the file and created a resource. You need a request ID/idempotency, retry budget, the ability to open a new stream, or an upload protocol with proper resume support.

## 16. Practical Checklist: Media Type Contract and Encoder/Parser

Before sending a request body in Java 17:

1. **Lock down the contract**: does the endpoint accept form, JSON, multipart, or raw bytes? Are media type and charset required?
2. **Separate the serialization layer**: form encodes each key/value in UTF-8; JSON uses a serializer; multipart builder creates boundaries/parts and keeps raw file bytes.
3. **`BodyPublisher` must emit the exact bytes**: `ofString` uses an explicit charset, `ofByteArray` uses unmodified binary, streaming large sources has a lifecycle.
4. **`Content-Type` must match the representation**: form vs. JSON vs. multipart with boundary; do not attach arbitrary headers that do not correspond to the payload.
5. **Do not manually assign `Content-Length` based on `String.length()`**; let the HTTP client/`BodyPublisher` manage framing.
6. **For multipart**, verify `name`, `filename`, part `Content-Type`, closing delimiter, CRLF, and that the boundary does not collide in the data.
7. **On the server side**, only use a parser matching the media type, and check syntax/schema, required fields, duplicate policy, type conversion, and access permissions.
8. **Resource limits**: total bytes, field/part counts, file size, timeouts, CPU, disk quota, and concurrency.
9. **Do not trust `filename`/MIME from the client**, prevent path traversal, inspect files, stage temporarily, and commit under control.
10. **Test Unicode, `+`, `&`, `=`, quotes, null bytes, and binary** with golden bytes/hashes, not just by eyeballing JSON/text.
11. **Inspect status, headers, and error body** after `send`; `400/413/415` are typically valid HTTP responses, not automatically `IOException`.
12. **Do not confuse transmission success with business success**: validation/scan/commit/reconciliation must have explicit statuses.
13. **Retry with policy**: is the streaming body replayable, is the operation idempotent, and where are the overall deadline and cleanup?

**Final takeaway:** `HttpClient`/HTTP APIs specialize in building and transporting **requests/responses**; `URLEncoder`, JSON serializers, and multipart builders specialize in turning **data representations into bytes**. The `Content-Type` header describes the content so the server can choose a parser; it does not transform the payload itself. Forms use percent-encoding, JSON uses JSON serialization, and multipart uses boundaries/part headers and raw file bytes. Separating these responsibilities properly prevents character bugs, wrong content types, corrupted binary files, parser mismatches, and upload vulnerabilities.

### References

- [RFC 9110 — HTTP Semantics, request content and Content-Type](https://www.rfc-editor.org/rfc/rfc9110)
- [HTML Living Standard — form URL encoding](https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#application/x-www-form-urlencoded-encoding-algorithm)
- [RFC 8259 — JSON Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259)
- [RFC 7578 — multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578)
- [RFC 2046 — MIME multipart media types and boundary](https://www.rfc-editor.org/rfc/rfc2046)
- [Java SE 17 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html)
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 17 — URLEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html)
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
