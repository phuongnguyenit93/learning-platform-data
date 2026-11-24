# Choosing Converters for Strings, byte[], Resource, JSON, and XML in Spring MVC

> **Scope:** Spring Web MVC (Servlet stack) running on Java 17+ with Spring Boot 3.x / Spring Framework 6.x examples. This lesson focuses on how Spring reads and writes **HTTP message bodies** via `HttpMessageConverter` when a controller receives `@RequestBody`, or returns `@ResponseBody` or `ResponseEntity<?>`. The five value groups to distinguish are **`String`, `byte[]`, `Resource`, JSON objects, and XML objects**. Jackson converter names changed in Spring Framework 7; the demo code uses APIs compatible with the Spring 6.x branch.

## 1. HTTP Bodies and Converters: The Problem to Solve

A handler can return many different Java types:

```java
@GetMapping("/hello")
public String hello() {
    return "Xin chào";
}

@GetMapping("/profile")
public ProfileDto profile() {
    return new ProfileDto(7, "Lan");
}
```

Both are Java values, but their wire formats differ:

```http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

Xin chào
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":7,"name":"Lan"}
```

Spring MVC does not automatically guess that every `String` is JSON or every object is XML. When a value passes through body processing, the framework chooses an `HttpMessageConverter` capable of handling the current **Java data type** and **media type**. The converter is responsible for turning HTTP bytes into a Java object (reading), or a Java object into HTTP bytes (writing).

Keep the role of each component in mind:

| Component | Role |
| --- | --- |
| `@RequestBody` | Tells Spring to read the **request body** into a Java argument |
| `@ResponseBody` / `@RestController` | Tells Spring to write the return value into the **response body** |
| `ResponseEntity<T>` | Provides status, headers, and body; the body still normally goes through a converter |
| `HttpMessageConverter<T>` | Reads/writes bodies for the Java types and media types it supports |
| Request `Content-Type` | Client announces the **format of the body being sent** |
| Request `Accept` | Client announces the **response format it can accept** |
| Response `Content-Type` | Server announces the **actual format of the returned body** |
| Mapping `consumes` / `produces` | Restricts route media types for request/response |

**Two directions must be distinguished:** with `@RequestBody`, Spring inspects the Java parameter type and request `Content-Type`; with `@ResponseBody`, Spring inspects the return value type, writable converters, `Accept`, and configured `produces` and `Content-Type` constraints.

## 2. Common Converters for the Five Data Groups

| Java Value | Common Spring MVC Converter | Media Types to Note | Example Usage |
| --- | --- | --- | --- |
| `String` | `StringHttpMessageConverter` | Mainly text bodies, typically returning `text/plain` unless otherwise selected | Text, hand-built CSV, character content |
| `byte[]` | `ByteArrayHttpMessageConverter` | Broadly supports `*/*`; defaults to writing `application/octet-stream` | Small binary payloads, data already in memory |
| `Resource` | `ResourceHttpMessageConverter` | Resource/file data; typically `application/octet-stream` or declared media type | Returning files, downloads, byte streams from resource sources |
| JSON POJO/record | `MappingJackson2HttpMessageConverter` | `application/json`, typically including `application/*+json` | REST JSON APIs |
| XML POJO/record | `MappingJackson2XmlHttpMessageConverter` | `application/xml`, `text/xml`, and XML suffixes when supported | XML integration / content negotiation |

The Jackson 2 converter names in the table match **Spring Framework 6.x**. Starting in Spring Framework 7.x, the converter API was updated for the newer Jackson generation; verify against your exact version's documentation before declaring or customizing converter classes. General controller APIs like `@RequestBody`, `ResponseEntity`, `produces`, and `consumes` remain the key mechanisms.

Another group in Spring is `FormHttpMessageConverter` for `application/x-www-form-urlencoded` / multipart within its respective scope, though it is not the primary focus of this lesson. Do not use `StringHttpMessageConverter` to hand-craft JSON/XML when a dedicated converter and strongly typed DTO better fit the requirement.

### 2.1. Are Converters Always Available?

No. Some converters ship with Spring Web; JSON/XML converters depend on corresponding serialization libraries on the classpath and MVC configuration. Spring Boot usually auto-configures a set of converters matching your dependencies. For example:

- Adding **Spring Web** to a Spring Boot 3.x project normally brings in Jackson JSON.
- To use Jackson XML in the example, you need `com.fasterxml.jackson.dataformat:jackson-dataformat-xml` at the version managed by Spring Boot.
- Without a suitable XML converter, even if the client sends `Accept: application/xml`, Spring **cannot automatically produce XML from arbitrary Java objects** just by changing a header.
- A system can explicitly change converters/their order, supported media types, or `ObjectMapper`. Do not treat the table as a fixed guarantee for every application.

## 3. Converter Selection Flow at the Controller Layer

Conceptual diagram:

```text
                      HTTP request
                           |
       +-------------------+---------------------+
       |                                         |
@RequestBody T                              Handler execution
       |                                         |
Content-Type + T                           Return value (T)
       |                                         |
canRead(T, media type)?                    @ResponseBody / ResponseEntity
       |                                         |
read(...) -> T                            Accept + produces + Content-Type
       |                                         |
Controller uses object                     canWrite(T, media type)?
                                                 |
                                             write(...) -> HTTP body
```

When Spring processes a request, there are two distinct phases:

1. **Handler selection**: `@RequestMapping` and its variants `@GetMapping`, `@PostMapping` can restrict routes with `consumes` and `produces`; failing these conditions can exclude a mapping before any converter runs.
2. **Reading/writing the body**: a registered converter must support the Java type and valid media type. For responses, Spring also performs content negotiation, typically based on `Accept` and the body type.

Converter order **can matter** when multiple converters claim to handle the same Java type/media type. Spring checks matching converters in the registered list. Therefore, a custom converter declaring overly broad support like `*/*` or inserted at the front of the list can cause unexpected output.

### 3.1. Distinguishing Three Places Where Media Types Are Set

```java
@PostMapping(
    path = "/documents",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE)
public DocumentDto create(@RequestBody DocumentDto input) {
    return input;
}
```

- `consumes = application/json` means the method expects a JSON request body. The client needs to send `Content-Type: application/json`.
- `produces = application/json` means the method produces a JSON response, and the client should accept `application/json` in its `Accept` header.
- `ResponseEntity.ok().contentType(MediaType.APPLICATION_JSON).body(...)` sets a specific response `Content-Type`. It **does not force Spring to turn an arbitrary `String` into valid JSON**.

When a client sends an XML body to a route with `consumes = application/json` only, the typical result is **415 Unsupported Media Type**. When a client only accepts XML but the route only has `produces = application/json`, the typical result is **406 Not Acceptable**. Additionally, if the format is acceptable at the header level but the body has invalid syntax or cannot be decoded, you typically receive **400 Bad Request** due to a request-reading error.

## 4. `StringHttpMessageConverter` — Returning or Receiving Text

Text response example:

```java
@GetMapping(path = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
public String hello() {
    return "Xin chào Spring MVC";
}
```

Because the method belongs to a `@RestController` (or has `@ResponseBody`), Spring writes the string to the body rather than treating it as a view name. Since the return type is `String`, the String converter is normally chosen and produces a text body.

Things to remember:

- `StringHttpMessageConverter` reads/writes strings; it does not map JSON objects to DTOs.
- `Content-Type` is determined by mapping, headers, and negotiation; if you want specific plain text content, use `produces = "text/plain"` or set the content type explicitly with `ResponseEntity`.
- For Unicode, proper encoding is required. In modern Spring Boot, UTF-8 is commonly used for text; you can explicitly declare `text/plain;charset=UTF-8` in the output contract when needed.
- A `String` containing `{"ok":true}` is still just characters. Setting `produces = "application/json"` **does not verify** that the string is valid JSON. You can accidentally return malformed JSON.
- If you want a JSON string scalar (e.g., a valid JSON response `"hello"` with quotes in the body), you must understand the difference between the String converter and Jackson. It is best to return a DTO/object when building JSON APIs to avoid configuration-dependent converter selection.

Receiving text example:

```java
@PostMapping(
        path = "/echo-text",
        consumes = MediaType.TEXT_PLAIN_VALUE,
        produces = MediaType.TEXT_PLAIN_VALUE)
public String echoText(@RequestBody String body) {
    return "text: " + body;
}
```

With `Content-Type: text/plain` and body `Java`, the server returns body `text: Java`. `@RequestBody` reads the **body**, not the query string. If only `?body=Java` is sent with an empty body, a method with a required `@RequestBody` may fail due to a missing body.

## 5. `ByteArrayHttpMessageConverter` — Raw `byte[]`

A byte array is byte data **already in memory**:

```java
@GetMapping(path = "/bytes", produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
public ResponseEntity<byte[]> bytes() {
    byte[] data = new byte[] {0x41, 0x42, 0x43};
    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .body(data);
}
```

The HTTP body consists of the exact three hex bytes `41 42 43`, corresponding to the ASCII characters `ABC`. There are no added JSON quotes, Base64, or JSON array characters.

Use `byte[]` when:

- The body is small or medium-sized and all bytes are already needed in RAM.
- Reading/writing binary protocols, compressed data, or very small files.
- You need **exact byte control** through the HTTP converter without JSON serialization.

Do not use `byte[]` to read an entire very large file just to send it to the client; it forces the application to hold the content in memory. When the content source is a file or a streamable resource, see `Resource` in Section 6.

If the client sends binary data:

```java
@PostMapping(
        path = "/byte-count",
        consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
        produces = MediaType.TEXT_PLAIN_VALUE)
public String byteCount(@RequestBody byte[] body) {
    return "bytes=" + body.length;
}
```

If the client sends the three bytes `ABC` with `Content-Type: application/octet-stream`, the response body is `bytes=3`. The count here is the **number of bytes**, not the number of Unicode characters.

The default media type of `ByteArrayHttpMessageConverter` when writing is typically `application/octet-stream`, even though the converter supports multiple media types. In REST, explicitly set `Content-Type` according to the data's real meaning (e.g., a PNG image should be `image/png`), rather than assuming the client can guess the format from a file extension.

## 6. `ResourceHttpMessageConverter` — Returning Resources/Files

`org.springframework.core.io.Resource` is an abstraction for data accessible through a resource source, such as `ClassPathResource`, `FileSystemResource`, `ByteArrayResource`, or a suitable stream source. Spring MVC can write `Resource` content to the response via `ResourceHttpMessageConverter`.

Example of downloading an embedded file:

```java
@GetMapping(path = "/download", produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
public ResponseEntity<Resource> download() {
    Resource body = new ByteArrayResource(
            "FILE\n".getBytes(StandardCharsets.UTF_8));

    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .header(HttpHeaders.CONTENT_DISPOSITION,
                    "attachment; filename=\"example.txt\"")
            .body(body);
}
```

When the client calls `GET /download`, the server sends the header `Content-Disposition: attachment; filename="example.txt"` and **5 bytes** for `FILE` plus a newline. `ByteArrayResource` is used here solely to demonstrate with synthetic data; for existing files, you can use `FileSystemResource` or `PathResource` in accordance with access policies.

### 6.1. How Do `byte[]` and `Resource` Differ?

| Question | `byte[]` | `Resource` |
| --- | --- | --- |
| Representation | Content resides in a byte array | Handle/abstraction to the content |
| Memory | Usually holds the entire body in RAM | Can read data from file/stream while writing |
| Large files | Not ideal | Usually more suitable if Resource type and infrastructure match |
| Primary converter | `ByteArrayHttpMessageConverter` | `ResourceHttpMessageConverter` |
| File metadata | Set headers manually | Also need to explicitly set `Content-Type`, `Content-Disposition` when required |
| Streaming | Immediately writes existing bytes | Can open stream when writing, depending on `Resource` |

**Important for streaming:** `Resource` does not guarantee that every implementation can reopen its stream. `InputStreamResource` may only be readable once, and calculating Content-Length can consume the stream if subclassed/wrapped improperly. With `InputStreamResource`, you must understand lazy stream supplier conventions and support limits; avoid pre-reading the stream to measure its length and then expecting the converter to read it again. For regular files, choosing an appropriate Resource allows the system to handle sizing/streaming more conveniently.

### 6.2. Downloads, Caching, and HTTP Range

Responses returning `Resource` may interact with Spring MVC's partial-content/Range support under certain conditions. Do not equate `Resource` with **every endpoint automatically supporting resumable downloads**. Functionality depends on how the controller returns the Resource, the Resource type, headers, configuration, and HTTP infrastructure.

If production downloads are needed:

1. Verify user permissions for the file before creating the `Resource`.
2. Do not concatenate paths directly from queries or URLs to read files without normalizing and checking for path traversal.
3. Set the exact `Content-Type`; if downloading is desired rather than inline display, set `Content-Disposition: attachment` with a safely sanitized filename.
4. Test Content-Length, memory profile, Range, timeouts, missing files, and I/O errors using integration tests with sufficiently large files.

## 7. JSON — `MappingJackson2HttpMessageConverter`

The JSON converter turns a body like this into a Java object:

```http
POST /api/messages/json
Content-Type: application/json
Accept: application/json

{"text":"Chao ban"}
```

Controller:

```java
@PostMapping(
        path = "/messages/json",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
public MessageDto echoJson(@RequestBody MessageDto input) {
    return input;
}
```

With `record MessageDto(String text) { }`, the Jackson deserializer reads JSON into a Java object; the Jackson serializer writes that object to JSON. Jackson JSON is required (typically included when adding Spring Boot starter web compatible with Boot 3.x).

### 7.1. Why Return a DTO Instead of a Concatenated JSON String?

Avoid:

```java
// Anti-pattern: concatenating JSON manually.
return "{\"text\":\"" + userInput + "\"}";
```

Manual string concatenation does not properly handle quotes, newlines, escaping, and edge cases. For JSON APIs, use a DTO/record and let Jackson serialize it:

```java
public record MessageDto(String text) {
}
```

This is an **illustrative type definition**; when placed in the same file as `public class DemoApplication`, remove `public` from the record or move it to `MessageDto.java`. Returning `MessageDto` ensures the serializer matches the object type and handles required escaping rules.

### 7.2. JSON Is Not a Media Type for Every Value

If a response is actually a file/binary but you set `application/json`, clients may misinterpret it. If an endpoint can return two representations for **the same object**, install the converters and use clear content negotiation. In production APIs, the DTO schema must be appropriate and must not directly serialize entities containing sensitive information.

For JSON requests, `@Valid @RequestBody MessageDto input` can trigger Bean Validation if configured with the appropriate dependency. Conversion is only the **reading step**, not data validation or authorization.

## 8. XML — `MappingJackson2XmlHttpMessageConverter`

The XML converter is a separate option alongside JSON. In Spring Framework 6.x, the Jackson XML converter uses `XmlMapper` from the library:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-xml</artifactId>
</dependency>
```

The snippet above is a Maven dependency placed inside `<dependencies>`, letting Spring Boot parent/BOM manage the version. Do not randomly add a mismatched Jackson version alongside the active dependency set.

A record annotated with an explicit XML root name:

```java
@JacksonXmlRootElement(localName = "message")
record MessageDto(String text) {
}
```

Import `com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement`. With the XML converter registered, handler:

```java
@PostMapping(
        path = "/messages/xml",
        consumes = MediaType.APPLICATION_XML_VALUE,
        produces = MediaType.APPLICATION_XML_VALUE)
public MessageDto echoXml(@RequestBody MessageDto input) {
    return input;
}
```

A matching request:

```http
POST /api/messages/xml
Content-Type: application/xml
Accept: application/xml

<message><text>Chao ban</text></message>
```

The XML response has a `message` element and a child `text` containing `Chao ban`. Exact formatting (XML declaration, whitespace, namespaces) depends on serializer configuration; tests should not compare every byte verbatim if the contract only specifies XML structure/values.

Spring MVC also has other XML converters, such as `Jaxb2RootElementHttpMessageConverter` when compatible JAXB is present, `MarshallingHttpMessageConverter` based on Spring OXM, and `SourceHttpMessageConverter` for `Source` types. **Do not equate** "XML support" with "definitely using Jackson XML"; verify your classpath and converter list. Java 17 no longer bundles JAXB in the JDK as older Java versions did; using JAXB requires adding a compatible API/provider.

### 8.1. Do You Need Two Endpoints to Return JSON and XML?

Not necessarily. If the same DTO type has converters for both media types and the mapping allows them:

```java
@GetMapping(
        path = "/messages/format",
        produces = {
            MediaType.APPLICATION_JSON_VALUE,
            MediaType.APPLICATION_XML_VALUE
        })
public MessageDto format() {
    return new MessageDto("Xin chào");
}
```

- `Accept: application/json` → JSON converter.
- `Accept: application/xml` → XML converter, if available libraries and configuration support `MessageDto`.
- `Accept: text/plain` → typically **406 Not Acceptable** because the route does not promise a text representation.
- `Accept: */*` → both are acceptable; do not write tests assuming XML is always chosen. Negotiation rules and ordering can affect the choice.

For external integration APIs, clearly document supported media types and test each read/write path with integration tests.

## 9. Complete Runnable Example: Five Body Types in One Application

This example uses Spring Boot 3.x and Spring Framework 6.x on Java 17+, including:

- A `String` text response.
- `byte[]` response and request.
- A `Resource` file response.
- JSON request/response objects.
- XML request/response objects (requiring Jackson XML).
- One JSON/XML endpoint using the `Accept` header to pick the representation.

### 9.1. Maven Dependencies

Create a Spring Boot 3.x project on [Spring Initializr](https://start.spring.io/) with **Java 17+** and **Spring Web**. If the project already has the Spring Web dependency generated by Initializr, keep it. In `pom.xml`, add the XML dependency alongside Spring Web:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.dataformat</groupId>
        <artifactId>jackson-dataformat-xml</artifactId>
    </dependency>
</dependencies>
```

This is a **`<dependencies>` snippet**, not a standalone POM file; Spring Initializr provides `project`, `parent`/BOM, Maven plugins, and metadata. When using Spring Boot's dependency management, you usually do not need to declare the Jackson XML version.

### 9.2. Complete Java Source

Replace the contents of `src/main/java/com/example/demo/DemoApplication.java` with the complete code below. There is only one `public class`; the package-private top-level `MessageDto` record is valid in the same file:

```java
package com.example.demo;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@JacksonXmlRootElement(localName = "message")
record MessageDto(String text) {
}

@RestController
@RequestMapping("/api")
class ConverterController {

    @GetMapping(path = "/text", produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> text() {
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(
                        "text/plain;charset=UTF-8"))
                .body("Xin chào Spring MVC");
    }

    @PostMapping(
            path = "/echo-text",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String echoText(@RequestBody String body) {
        return "text: " + body;
    }

    @GetMapping(
            path = "/bytes",
            produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<byte[]> bytes() {
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .body(new byte[] {65, 66, 67});
    }

    @PostMapping(
            path = "/byte-count",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String byteCount(@RequestBody byte[] data) {
        return "bytes=" + data.length;
    }

    @GetMapping(
            path = "/download",
            produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<Resource> download() {
        Resource file = new ByteArrayResource(
                "FILE\n".getBytes(StandardCharsets.UTF_8));

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"example.txt\"")
                .body(file);
    }

    @PostMapping(
            path = "/messages/json",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public MessageDto json(@RequestBody MessageDto input) {
        return input;
    }

    @PostMapping(
            path = "/messages/xml",
            consumes = MediaType.APPLICATION_XML_VALUE,
            produces = MediaType.APPLICATION_XML_VALUE)
    public MessageDto xml(@RequestBody MessageDto input) {
        return input;
    }

    @GetMapping(
            path = "/messages/format",
            produces = {
                    MediaType.APPLICATION_JSON_VALUE,
                    MediaType.APPLICATION_XML_VALUE
            })
    public MessageDto format() {
        return new MessageDto("Xin chào");
    }
}
```

**Why does Spring pick the right converter?**

- `text()` returns `ResponseEntity<String>`, so the body is a String, written by the string converter.
- `bytes()` returns `ResponseEntity<byte[]>`, so the body is a byte array (not a JSON list).
- `download()` returns `ResponseEntity<Resource>`, so the Resource converter reads the resource content.
- `json()` accepts and returns `MessageDto` with `application/json`, so the JSON converter reads/writes it.
- `xml()` accepts and returns `MessageDto` with `application/xml`, so the XML converter reads/writes it.
- `format()` also returns `MessageDto`, but the route allows both JSON and XML; the `Accept` value determines the output.

### 9.3. Running the Application

From the project root directory:

```bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell or Command Prompt
mvnw.cmd spring-boot:run
```

### 9.4. Verifying Requests and Responses

**Text:**

```bash
curl -s -H 'Accept: text/plain' \
  http://localhost:8080/api/text
```

UTF-8 body:

```text
Xin chào Spring MVC
```

**Text request:**

```bash
curl -s -X POST \
  -H 'Content-Type: text/plain' \
  -H 'Accept: text/plain' \
  --data-binary 'Java' \
  http://localhost:8080/api/echo-text
```

Body:

```text
text: Java
```

**Byte response:**

```bash
curl -s -o sample.bin -H 'Accept: application/octet-stream' \
  http://localhost:8080/api/bytes
xxd -p sample.bin
```

If `xxd` is available on your machine, the printed line is:

```text
414243
```

This is the **hex representation of the three bytes**; cURL saves the binary body to `sample.bin` without extra newline characters. It is not a JSON output `[65,66,67]`.

**Byte request:**

```bash
curl -s -X POST \
  -H 'Content-Type: application/octet-stream' \
  --data-binary 'ABC' \
  http://localhost:8080/api/byte-count
```

Body:

```text
bytes=3
```

**Resource download:**

```bash
curl -s -OJ http://localhost:8080/api/download
```

With a cURL client supporting `-OJ`/Content-Disposition, the file is saved as `example.txt` (unless environment or filename conflicts lead to different handling). Its content is `FILE` and a trailing newline, totaling **5 bytes**. If you do not want the client to pick the filename from the header, use `curl -s -o local.txt URL` to save to a chosen file.

**JSON input and output:**

```bash
curl -s -X POST http://localhost:8080/api/messages/json \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary '{"text":"Chao ban"}'
```

Data-equivalent JSON body:

```json
{"text":"Chao ban"}
```

**XML input and output:**

```bash
curl -s -X POST http://localhost:8080/api/messages/xml \
  -H 'Content-Type: application/xml' \
  -H 'Accept: application/xml' \
  --data-binary '<message><text>Chao ban</text></message>'
```

Value-equivalent XML body:

```xml
<message><text>Chao ban</text></message>
```

Jackson XML may emit an XML declaration or equivalent formatting; the snippet above shows **structure and values**, without promising byte-for-byte parity unless the serializer is explicitly configured.

**Negotiation by `Accept`:**

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/messages/format

curl -i -H 'Accept: application/xml' \
  http://localhost:8080/api/messages/format

curl -i -H 'Accept: text/plain' \
  http://localhost:8080/api/messages/format
```

The first two requests receive `200 OK` with the corresponding JSON/XML `Content-Type`, while the third request typically receives **406 Not Acceptable** because the mapping only allows JSON/XML. To compare results in Windows PowerShell, use `curl.exe` and write each command on a single line to avoid Bash line-continuation syntax.

## 10. When the Wrong Converter Is Selected or None Is Found

### 10.1. `406 Not Acceptable`: Client Does Not Accept What the Server Can Produce

Example:

```http
GET /api/messages/format
Accept: text/plain
```

In the demo, the route only has `produces = application/json, application/xml`. The typical result is 406. The fix is for the client to request a truly supported representation, or for the server to implement the additional representation (along with the matching converter/mapping). Do not force an incorrect `Content-Type` to bypass the error.

### 10.2. `415 Unsupported Media Type`: Request Body Is Not Supported

Example:

```http
POST /api/messages/json
Content-Type: application/xml

<message><text>Hi</text></message>
```

The mapping only specifies `consumes = application/json`; the request may be rejected with 415 **before reading the body**. A 415 can also occur when no converter can read the body into the required parameter type for the declared media type.

### 10.3. `400 Bad Request`: Malformed Payload Content

```http
POST /api/messages/json
Content-Type: application/json

{"text":
```

The header correctly specifies JSON, but the body has invalid syntax. Jackson fails to parse it and Spring MVC typically returns 400. Parse errors, field type errors, validation errors, and business content errors are distinct categories; handle errors consistently instead of changing media types to mask failures.

### 10.4. `500 Internal Server Error` or Response-Writing Errors

Even when the route and `Accept` are compatible, the server can still fail while serializing an object—for instance due to circular references, getters throwing exceptions, missing serializer configuration, or an object that cannot be represented by available converters. To diagnose, check the actual converter class used, the root stack trace, and the Java return type. Do not assume every response error is 406; 406 primarily indicates an **inability to satisfy a client-acceptable format**.

### 10.5. Why Does `return "index";` Sometimes Return a View and Sometimes Text?

```java
@Controller
class PageController {
    @GetMapping("/page")
    public String page() {
        return "index";
    }
}
```

In `@Controller`, `String` can be a **view name**. When the method has `@ResponseBody` or the class uses `@RestController`, the String becomes the **HTTP body** and converters get the chance to handle it. This is a difference at the return-value handler layer, not a bug in the String converter.

## 11. Configuring Converters in Spring MVC and Spring Boot

### 11.1. Usually, No Manual Registration Is Needed

Spring Web MVC registers a default set of converters depending on which libraries are present. Spring Boot also automatically adds/adjusts converters according to dependencies and its own configuration. In an application using `spring-boot-starter-web` and Jackson, a `@RestController` returning a DTO already gets JSON. Adding a compatible Jackson XML dependency typically enables XML unless another configuration blocks it.

Checking dependencies matters more than writing a new converter bean just to fix `406`. When both JSON and XML are supported and the client sends no specific `Accept`, which format the application picks depends on converter order and negotiation policy.

### 11.2. `extendMessageConverters` vs. `configureMessageConverters`

In Spring Framework **6.x**:

```java
@Configuration
class ConverterConfig implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        // Inspect or customize the list already configured by MVC.
        // Do not remove default converters without a reason.
    }
}
```

The snippet above is an **illustrative config**; it requires importing `org.springframework.context.annotation.Configuration`, `org.springframework.web.servlet.config.annotation.WebMvcConfigurer`, `org.springframework.http.converter.HttpMessageConverter`, and `java.util.List`. `extendMessageConverters` lets you adjust the list after the default configuration step.

In contrast, `configureMessageConverters(List<...>)` in Spring MVC 6.x can **replace the default converter registration mechanism** if you populate converters yourself; in Spring Boot, additional bean auto-registration mechanisms must also be considered. Do not add only a JSON converter and break String, Resource, or other pre-existing converter support. Also avoid adding `@EnableWebMvc` in Boot unless you intentionally want to take over MVC configuration.

If you only need a specific format for a single endpoint, declare `consumes`/`produces`, use `ResponseEntity`, and pick the right body type before touching the application-wide converter list.

### 11.3. Inspecting the Active Converter Order

In a Boot 3.x / Framework 6.x application, you can observe the converter list configured by MVC:

```java
// Standalone diagnostic snippet; not required in the demo.
@Component
class ConverterPrinter implements ApplicationRunner {

    private final RequestMappingHandlerAdapter adapter;

    ConverterPrinter(RequestMappingHandlerAdapter adapter) {
        this.adapter = adapter;
    }

    @Override
    public void run(ApplicationArguments args) {
        for (HttpMessageConverter<?> converter
                : adapter.getMessageConverters()) {
            System.out.println(converter.getClass().getSimpleName());
        }
    }
}
```

This snippet requires importing `org.springframework.stereotype.Component`, `org.springframework.boot.ApplicationRunner`, `org.springframework.boot.ApplicationArguments`, `org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter`, and `org.springframework.http.converter.HttpMessageConverter`; it is **diagnostic code**, not a fixed assertion on output or list order. Converter names and counts depend on the version and classpath.

If overly broad media types are configured on a custom converter, it may be chosen ahead of a more appropriate converter. Test `Accept: */*`, `Accept: application/json`, and `Accept: application/xml` after changing the order.

## 12. Choosing Based on Application Requirements

| Output Requirement | Recommended Java Return Type | Media Type | Reason |
| --- | --- | --- | --- |
| Simple text message | `String` | `text/plain;charset=UTF-8` | Plain text form |
| Small hand-built CSV data | `String` / `byte[]` | `text/csv` | Proper encoding and CSV escaping |
| Small binary already in RAM | `byte[]` | `application/octet-stream` or specific type | Sends bytes directly |
| Disk file / streamable resource | `Resource` | Actual type, with `Content-Disposition` for downloads | Avoids holding the whole file in a single array |
| Schema-backed REST payload | DTO/record | `application/json` | Jackson mapping and JSON escaping |
| Contract-based XML integration | DTO/record with proper XML mapping | `application/xml` | Compatible with Jackson XML/JAXB |
| Same object supporting JSON/XML | DTO/record | `produces={JSON,XML}` | Selects representation via `Accept` |

Do not use `String`/`byte[]` just to avoid designing a DTO. Do not use `Resource` instead of JSON for schema-based objects. Converters transform data **on the wire**; they do not replace validation, authentication/authorization, sensitive data encryption, or request size controls.

## 13. Common Pitfalls and Production Risks

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Confusing request `Content-Type` with `Accept` | 415 or 406 | Clarify read vs. write body direction |
| Returning a JSON-like `String` | May return invalid text or bypass serializer | Return a DTO via Jackson |
| Sending a JSON object while forcing `produces=text/plain` | Unsuitable converter or broken contract | Use `application/json` |
| Assuming `byte[]` is Base64 JSON | Client fails to parse | Distinguish raw binary from Base64 JSON |
| Reading large files into a byte array | High RAM usage, poor scalability | Use `Resource`/appropriate streaming |
| Assuming XML is always available | 406, 500, or missing converter | Add XML dependency and test classpath |
| Customizing an overly broad `*/*` converter | Overrides default converters | Restrict `supportedMediaTypes` and control order |
| Dropping default converters when overriding config | String/Resource/JSON stop working | Prefer safe extension mechanisms |
| Returning a Resource from a client-chosen path | File disclosure, path traversal | Authorize access and restrict paths |
| Deserializing JSON/XML into an entity with privilege fields | Mass assignment, field exposure | Use request DTOs, validate, explicit mapping |
| Blindly trusting client filename/media type | Spoofed file formats, injection | Validate content, sanitize filenames |
| XML parser allowing external entities | XXE, unintended resource reads | Use updated XML libraries and harden parser config |

Especially for XML, if you add a custom parser or new converter, check **XXE / external entity resolution**, document size limits, and nesting depth. Do not enable external entities when processing untrusted data. For JSON, pay attention to nesting depth, request size, and fields that must not be deserialized into domain entities.

### 13.1. Quick Debugging Checklist

1. Check whether the method has `@ResponseBody`/`@RestController` or returns `ResponseEntity`.
2. Record the **runtime body type** and the `@RequestBody` parameter type.
3. Inspect request `Content-Type`, `Accept`, and mapping `consumes`/`produces`.
4. Confirm the corresponding converter dependency is on the runtime classpath.
5. Check the converter list + ordering if custom config exists.
6. Use `curl -i` or integration tests to inspect status, response `Content-Type`, and actual body.
7. If you see 400/500, inspect the converter's root exception; do not confuse data errors with negotiation errors.

## 14. Self-Check

**Question 1.** A client sends `POST /messages/json` with `Content-Type: application/xml`, but the mapping only specifies `consumes=application/json`. What is returned?

**Answer:** Typically **415 Unsupported Media Type**, because the request body format does not match.

**Question 2.** An endpoint returns `ResponseEntity<byte[]>` with three bytes `65,66,67` and media type `application/octet-stream`. What does the client receive?

**Answer:** Three bytes `41 42 43` in hex (ASCII `ABC`), not a JSON array or Base64.

**Question 3.** An endpoint returns `MessageDto` and supports JSON and XML. The client sends `Accept: application/xml`, but the app has no XML converter yet. Will it automatically convert JSON to XML?

**Answer:** No. A matching XML converter supporting the Java type must be on the classpath; otherwise, the response cannot satisfy the XML contract.

**Question 4.** Why is `return "{\"text\":\"hi\"}";` a bad approach for a JSON API?

**Answer:** It is a manual String with risks of improper escaping, wrong content type, and converter-selection coupling; return a DTO/record so Jackson serializes it.

**Question 5.** Why is `Resource` usually better than `byte[]` for large files?

**Answer:** `Resource` can represent a data source read while sending the response, rather than loading the entire file into a byte array beforehand; you must still pick an appropriate Resource type and streaming configuration.

**Question 6.** Does `@GetMapping(produces=APPLICATION_JSON_VALUE)` guarantee that any returned `String` is valid JSON?

**Answer:** No. `produces` is the mapping's media type contract; it does not replace object serialization via a JSON converter or validate raw JSON.

## 15. Authoritative References

- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html): core converters, JSON/XML, and required dependencies.
- [Spring Framework 6.2 — Configuring Message Converters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/message-converters.html): `configureMessageConverters` and `extendMessageConverters`.
- [Spring Framework — Request Mapping: consumes/produces](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): mappings based on Content-Type/Accept.
- [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): status, headers, and body converters.
- [Spring Framework — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): decoding request bodies and validation.
- [Spring Framework — @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html): turning return values into HTTP response bodies.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): converter auto-configuration in Boot 3.x.
- [Spring Framework — HTTP Range Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-range.html): partial content mechanism for `Resource` under appropriate conditions.

**Practical summary:** Start from the **Java type of the body** and the **media type required by the HTTP request/response**, then let the right converter read or write it. Use `String` for text, `byte[]` for in-memory binary, `Resource` for resource sources, DTO/record + Jackson for JSON, and a compatible converter/XML mapping for XML. Check `Content-Type`, `Accept`, `consumes`, `produces`, runtime libraries, and converter ordering together before customizing MVC configuration.
