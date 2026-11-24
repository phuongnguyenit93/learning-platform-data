# JSON, Plain Text, Binary, and XML Formats When Matching Converters Exist

## Lesson Objectives and Scope

After this lesson, you will be able to:

1. Explain why the same HTTP endpoint can receive or return **JSON**, **plain text**, **binary data**, and **XML**, yet not every format is automatically available.
2. Distinguish **Content-Type** from **Accept**, understanding representation negotiation and when HTTP 400, 406, or 415 is returned.
3. Choose the right Java type such as record/DTO, `String`, `byte[]`, `Resource`, `InputStreamResource`, `Mono<T>`, or `Flux<T>` for the HTTP payload.
4. Distinguish **HttpMessageConverter** in Spring MVC from **HttpMessageReader/HttpMessageWriter/Encoder/Decoder** in WebFlux.
5. Know which libraries typically provide JSON/XML, the limitations of String/binary converters, and how to inspect the converter/codec list at runtime.
6. Build a runnable **Spring Boot 3.3.x, Java 17+** application that accepts and returns JSON/XML, `text/plain`, and `application/octet-stream` with accurate headers.
7. Understand the equivalent WebFlux implementation, including classpath conditions for XML codecs and reactive body differences.
8. Test using curl, MockMvc, and WebTestClient, and diagnose wrong media types, bad serialization, charset issues, payload limits, and XML security risks.

**Context:** JSON and codecs in the Spring Boot web-runtime. This lesson uses APIs from **Spring Boot 3.3.x / Spring Framework 6.1.x / Java 17+**. API names in Spring Framework 7 or Spring Boot 4 may differ; do not alter packages/classes in the 3.3 examples to match newer documentation.

**Core principle:** Headers only describe the content type; converting objects to bytes (and back) requires a **converter/codec compatible with both the Java type and the media type**. Setting `Accept: application/xml` does not automatically install XML serialization, just as setting `Content-Type: application/json` does not turn an arbitrary `String` into valid JSON.

## 1. HTTP Bodies Can Carry Multiple Representations

An HTTP message consists of method/status, URL, headers, and body. The body is bytes; how they are interpreted depends on the media type.

Example responses carrying the same business meaning ("product id=7, name=pen"):

### JSON

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":7,"name":"pen"}
~~~

### Plain text

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8

7,pen
~~~

### XML

~~~http
HTTP/1.1 200 OK
Content-Type: application/xml

<product><id>7</id><name>pen</name></product>
~~~

### Binary

~~~http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="product.bin"

...bytes not necessarily text...
~~~

These examples are **different representations**, not an automatic format conversion requiring zero code. JSON/XML have structured schemas, plain text can be any convention defined by the API, and binary consists of application-produced bytes. Converters do not decide business schemas or generate PDF/ZIP/image contents from arbitrary DTOs.

**Important:** `Content-Type` is metadata; the actual bytes must match the declared format. If the body is JSON but labeled `application/xml`, the XML parser will fail. If the body is arbitrary text labeled `application/json`, JSON clients may fail to parse it.

## 2. What Is a Media Type / MIME Type?

An HTTP media type has the form:

~~~text
type/subtype; parameter=value
~~~

Examples:

~~~text
application/json
application/problem+json
application/xml
text/xml
text/plain; charset=UTF-8
application/octet-stream
image/png
application/pdf
application/x-ndjson
text/event-stream
~~~

Common classifications:

| Media Type | Typical Content | Suitable Java Handler |
|---|---|---|
| `application/json` | JSON object/array | Jackson `ObjectMapper` and JSON converter/codec |
| `application/*+json` | Vendor JSON or Problem Details | JSON converter/codec with matching supported media types |
| `text/plain` | Plain text | String converter/encoder/decoder |
| `application/octet-stream` | Bytes without higher-level structural metadata | `byte[]`/`DataBuffer`/`Resource` |
| `application/xml`, `text/xml` | XML document | Jackson XML, JAXB, or configured XML reader/writer |
| `application/*+xml` | Vendor XML type | Depends on XML converter's supported media types |
| `application/pdf` | Real PDF file | `byte[]`/`Resource` writer, provided bytes are valid PDF |
| `image/png` | Real PNG image | `byte[]`/`Resource` writer; bytes must be PNG |
| `application/x-ndjson` | Individual JSON object per line | Matching streaming JSON codec |
| `text/event-stream` | Server-Sent Events | SSE writer/encoder when supported by WebFlux or MVC |

**application/octet-stream** does not mean a file has no type. It represents a generic binary payload when the API provides no specialized media type. If you know the payload is PNG or PDF, declare `image/png` or `application/pdf` matching the actual bytes, along with a disposition header if download is desired.

### File Extensions Are Not Content-Type

The URL `/report.pdf` and header `Content-Type: application/json` can coexist in HTTP; the server still sends JSON bytes if the application produces JSON. Clients may get confused or block the content. Keep formats, filenames, and headers aligned, especially for browser and download-manager clients.

### Charset Does Not Automatically Make Bytes Valid Text

`text/plain; charset=UTF-8` indicates that bytes should be decoded as UTF-8. If the server writes bytes in another encoding while labeling them UTF-8, Vietnamese characters can become corrupted. Modern networked JSON uses UTF-8; for XML, pay attention to both the `Content-Type` charset and any XML declaration.

## 3. Two Conversion Directions: Reading Requests and Writing Responses

Before calling a controller, Spring must turn the request body into the desired Java type. After the controller returns a value, Spring must write the response body.

~~~text
CLIENT
  |
  |  HTTP request
  |  Content-Type: application/json
  |  Body: {"name":"pen"}
  v
Spring HTTP infrastructure
  |
  +-- Pick converter/reader for (Java target type, request media type)
  |      -> decode/deserialize bytes into ProductInput
  |
  v
Controller + Service
  |
  |  Java value ProductView
  v
Spring HTTP infrastructure
  |
  +-- Based on Accept, produces, supported media types, and Java return type
  |      -> pick representation/converter/writer
  |      -> serialize ProductView to JSON/XML/...
  |
  v
HTTP response with matching Content-Type and bytes
~~~

Four facts to remember:

1. **Reading** depends on the **request `Content-Type`** and **Java parameter type**.
2. **Writing** depends on the **request `Accept`**, **`produces`**, **Java return type**, and **available writers**.
3. **Response `Content-Type`** must accurately describe the bytes returned by the server.
4. Both routing conditions (`consumes`/`produces`) and converters/codecs can reject a request.

There is no universal `toString()` operation capable of converting any object into semantically valid JSON, XML, PDF, or binary.

## 4. Content-Type and Accept Are Different

| Header | Sender | Meaning |
|---|---|---|
| Request `Content-Type` | Client | Format of the **request body being sent** |
| Request `Accept` | Client | Response formats the client **can accept** |
| Response `Content-Type` | Server | Actual format of the **response body** |
| Response `Content-Disposition` | Server | Hints how to display/download content and filename |
| Response `Vary` | Server | Which request headers affect representation so caches distinguish them |

Example where the client sends XML yet wants JSON back:

~~~http
POST /api/convert HTTP/1.1
Content-Type: application/xml
Accept: application/json

<product><id>7</id><name>pen</name></product>
~~~

This is a valid request **if** the endpoint accepts XML input and can emit JSON output. Input `Content-Type` and output `Accept` **do not have to match**.

### Accept Precedence

~~~http
Accept: application/json, application/xml;q=0.5
~~~

The client prefers JSON over XML. Spring evaluates handler and writer capabilities; when both formats are supported, JSON is chosen based on content negotiation rules and quality weights.

If `Accept` is `*/*`, the client states it can accept multiple formats without specifying one. If an endpoint supports both JSON and XML, do not promise a single fixed outcome for clients omitting `Accept`; specify `Accept` explicitly in tests.

### GET Usually Does Not Need a Request Content-Type

~~~bash
curl -i -H 'Accept: application/json' http://localhost:8080/api/products/7
~~~

The `Accept` header requests a JSON response. Do not add `Content-Type: application/json` to a bodyless GET just to ask for JSON. Conversely, when sending a JSON POST body, the request `Content-Type` is essential.

## 5. Spring MVC Uses HttpMessageConverter

Spring MVC on the Servlet stack uses:

~~~java
org.springframework.http.converter.HttpMessageConverter<T>
~~~

The interface and implementations read/write HTTP bodies via `HttpInputMessage`/`HttpOutputMessage` abstractions tied to Servlet requests/responses.

Representative implementations in Spring Framework 6:

| Converter | Typical Java Type | Media Types / Role |
|---|---|---|
| `MappingJackson2HttpMessageConverter` | JavaBean, DTO, record, Map/List | JSON via Jackson `ObjectMapper` |
| `StringHttpMessageConverter` | `String` | Text and the converter's supported media types |
| `ByteArrayHttpMessageConverter` | `byte[]` | Raw bytes; can default to `application/octet-stream` on write |
| `ResourceHttpMessageConverter` | `Resource` | Reads/writes resources and file streams |
| `MappingJackson2XmlHttpMessageConverter` | DTO/JavaBean | XML via Jackson `XmlMapper` when extension is present |
| `Jaxb2RootElementHttpMessageConverter` | JAXB-annotated bean | XML when appropriate JAXB components exist |
| `SourceHttpMessageConverter` | `javax.xml.transform.Source` | Reads/writes XML `Source` |
| `FormHttpMessageConverter` | `MultiValueMap` and form parts | `application/x-www-form-urlencoded` and form/multipart support |

This is an **illustrative** list, not a guarantee that every converter exists in every application. Spring Boot auto-configuration inspects dependencies and settings. `starter-web` typically includes Jackson JSON; XML requires the Jackson XML extension or JAXB support as described in Boot 3.3 documentation.

### Questions to Ask When Selecting a Converter

- Java type: `String`, `byte[]`, `Resource`, or `Product`?
- Media type: `application/json`, `text/plain`, `application/xml`?
- Reading or writing?
- Is the converter registered?
- Does `canRead`/`canWrite` return true for that type and media type?
- Is another converter ordered earlier with overly broad support?

A converter handles **representation** only. It does not perform authentication, business validation, database access, or turn arbitrary objects into real PDF files.

## 6. Spring WebFlux Uses Readers, Writers, and Codecs

WebFlux uses these contracts:

~~~java
org.springframework.http.codec.HttpMessageReader<T>
org.springframework.http.codec.HttpMessageWriter<T>
org.springframework.core.codec.Decoder<T>
org.springframework.core.codec.Encoder<T>
~~~

Request body data normally flows as `Publisher<DataBuffer>`; decoders turn bytes into objects, encoders turn objects into `DataBuffer`s, and HTTP readers/writers integrate codecs with media types and headers.

~~~text
HTTP request Flux<DataBuffer>
       |
       v
HttpMessageReader
       |
       v
Decoder (Jackson JSON / String / JAXB XML / ...)
       |
       v
Mono<Product> or Flux<Product>
       |
       v
WebFlux controller + service
       |
       v
HttpMessageWriter
       |
       v
Encoder (Jackson JSON / String / binary / JAXB XML / ...)
       |
       v
HTTP response Publisher<DataBuffer>
~~~

**Do not use MVC `HttpMessageConverter` to configure a WebFlux server.** Conversely, WebFlux codecs do not replace MVC message converters.

### JSON in WebFlux

Typically `Jackson2JsonDecoder`/`Jackson2JsonEncoder` paired with `HttpMessageReader`/`Writer` are used when Jackson is on the classpath. Controllers can receive `@RequestBody Mono<Product>` and return `Mono<Product>`.

### XML in WebFlux

Spring Framework 6.1 includes **Jaxb2XmlDecoder/Jaxb2XmlEncoder** in package `org.springframework.http.codec.xml`. They apply to compatible JAXB types when required JAXB libraries and registration are present. Do not assume adding **jackson-dataformat-xml** to WebFlux turns JAXB codecs into `MappingJackson2XmlHttpMessageConverter`; the latter belongs to **MVC**.

Check that the **XML decoder/encoder is actually registered in the WebFlux registry** and that DTOs are supported. Otherwise, add JAXB dependencies/codecs per application needs.

### Backpressure and Aggregation

A single JSON document may require aggregating bytes in memory during decoding; NDJSON allows streaming object by object. WebFlux provides backpressure but does not eliminate all buffering. The `spring.codec.max-in-memory-size` limit must be evaluated independently of file uploads and proxy size limits.

## 7. JSON: Objects, Arrays, Strings, and Java Types

JSON is a standardized syntax of values: object, array, string, number, boolean, null.

~~~json
{
  "id": 7,
  "name": "pen",
  "inStock": true,
  "tags": ["stationery", "office"],
  "price": 12.5
}
~~~

Java can represent this structure with a DTO or record:

~~~java
public record ProductDto(
        long id,
        String name,
        boolean inStock,
        java.util.List<String> tags,
        java.math.BigDecimal price) {}
~~~

This is an illustrative record declaration for a Java 17+ project. Jackson can serialize the record's accessors according to their types, provided runtime modules/settings support them.

### JSON Text Is Not the Same as a Java String

For example, the response body:

~~~text
hello
~~~

is not a valid JSON string literal because JSON strings require quotes:

~~~json
"hello"
~~~

If a controller returns `String` with `produces=application/json`, **`StringHttpMessageConverter` can write the raw String**, rather than Jackson adding quotes. Therefore, to return JSON objects or arrays, use typed DTOs, records, or Maps and let the JSON converter/codec serialize them.

### Never Build JSON via String Concatenation

Anti-pattern:

~~~java
String json = "{\"name\":\"" + name + "\"}";
~~~

If `name` contains quotes, backslashes, or control characters, the JSON breaks. With untrusted input, it also opens response-manipulation risks. Use `ObjectMapper`/DTOs for proper escaping and representation.

### Data Types Requiring Explicit Decisions

- **Number:** JSON numbers do not distinguish `long`/`double`/`BigDecimal`; client and server must agree on integer ranges, precision, and units.
- **Date/time:** avoid guessing formats and timezones; use `java.time` and matching Jackson configuration.
- **null/missing:** an absent property is not strictly identical to a null-valued property.
- **unknown fields:** can be ignored or rejected depending on mapper/deserialization policy.
- **Enum:** can be represented as names or custom strings; consider API versioning.
- **Nested objects/circular graphs:** avoid serializing ORM entities directly due to lazy-loading, cycles, or secrets.

### Malformed JSON Typically Returns 400

~~~http
POST /api/products HTTP/1.1
Content-Type: application/json

{"id": 7, "name":
~~~

The body is not valid JSON, so the decoder/converter rejects it with a body-reading error, typically HTTP 400. Do not mistake this for "route not found."

## 8. Plain Text: text/plain and Charset

A plain-text endpoint typically uses Java type `String`:

~~~java
@GetMapping(
    path = "/greeting",
    produces = MediaType.TEXT_PLAIN_VALUE
)
String greeting() {
    return "Xin chào";
}
~~~

This method belongs inside a `@RestController`. When the client sends `Accept: text/plain`, Spring selects a matching writer to emit text bytes. Understand response encoding and `Content-Type`, especially when Vietnamese characters are involved.

### Plain Text Is Not a JSON String

The body:

~~~text
Xin chào
~~~

is `text/plain`. If the API wants a JSON string, the body must be:

~~~json
"Xin chào"
~~~

The two representations have different bytes and clients parse them differently. Do not return raw text labeled `application/json` just to "make the API look like JSON."

### UTF-8 and Content-Type

Example:

~~~http
Content-Type: text/plain; charset=UTF-8
~~~

If creating bytes manually:

~~~java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
~~~

When reading raw text bytes:

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

These are illustrative snippets requiring `import java.nio.charset.StandardCharsets`. Align charsets between client and server to prevent corrupting accented characters.

**Never rely on platform default charset** for binary/text protocols when consistent output across Windows, Linux, and containers is required. In Spring MVC 3.3, Boot configures UTF-8 as the default String converter encoding per documentation; custom configuration or proxies can still alter results, so test actual responses.

### When to Use String for Real Text

`String` works well for small plain text, health markers, or text configuration endpoints with clear contracts. For large content, consider streaming `Resource` or streaming APIs. For structured fields/annotations, JSON DTOs are easier to evolve and validate.

## 9. Binary: byte[], Resource, and Content-Disposition

Binary payloads consist of bytes that may contain `0x00` or `0xFF`; they are not UTF-8 character strings. Never pass them casually through `new String(bytes)` and `getBytes()` if you need **byte-for-byte preservation**.

Example three-byte payload:

~~~text
41 00 FF
~~~

This is hex notation for bytes `0x41`, `0x00`, `0xFF`. The first byte is ASCII `'A'`; the other two do not form ordinary printable text.

### byte[] for Small Payloads

~~~java
@GetMapping(
    path = "/download",
    produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
)
byte[] download() {
    return new byte[] {0x41, 0x00, (byte) 0xFF};
}
~~~

This snippet sits inside a `@RestController`. MVC's `ByteArrayHttpMessageConverter` or WebFlux's binary codec writes the bytes verbatim. Returning a small `byte[]` is convenient, whereas returning a 1 GB array creates severe memory pressure.

### Resource for Large Content or Files

In MVC, `ResourceHttpMessageConverter` supports `org.springframework.core.io.Resource`. Example returning an **existing file at an application-controlled path**:

~~~java
@GetMapping("/download/report")
ResponseEntity<Resource> report() {
    Resource file = new FileSystemResource(
            Path.of("/var/app/reports/report.pdf"));
    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_PDF)
            .header(
                HttpHeaders.CONTENT_DISPOSITION,
                ContentDisposition.attachment()
                    .filename("report.pdf").build().toString()
            )
            .body(file);
}
~~~

This is an illustrative snippet in an MVC controller requiring imports for `Resource`, `FileSystemResource`, `Path`, and HTTP types, assuming the file exists and is readable. Never construct paths directly from client-supplied filenames without normalization/allowlisting, to prevent path traversal.

**Important:** `Content-Type: application/pdf` asserts the payload is PDF; **the `Resource` converter does not generate PDFs** from JSON data. The file must contain valid PDF bytes.

### Content-Disposition

~~~http
Content-Disposition: attachment; filename="report.pdf"
~~~

This header suggests the browser download the file with that filename; it does not force client compliance, protect data, or act as authorization. For Unicode filenames, use Spring's `ContentDisposition` builder to encode/quote safely instead of concatenating unvalidated inputs into headers.

### Content-Length, Range, Caching

Libraries or resource handlers may support `Content-Length`, `Last-Modified`, `ETag`, and `Range` depending on the `Resource` type and handler. Do not assume returning `ResponseEntity<byte[]>` automatically provides streaming or `Range` support. For large downloads, look into `Resource`/`ResourceRegion` or streaming endpoints matching your framework version.

### byte[] Can Represent PNG, ZIP, or PDF Without a Specialized Converter

A raw binary writer can send PNG/PDF/ZIP bytes with the right media type **provided the application already generated valid bytes**. The writer not understanding PDF internals is not a bug: its job is copying bytes and headers; generating valid file formats belongs to the processing layer.

## 10. XML: Only When Converters/Codecs and Libraries Are Ready

XML is a markup format with elements, attributes, namespaces, escaping, and well-formedness rules.

~~~xml
<product>
    <id>7</id>
    <name>pen</name>
</product>
~~~

A Java POJO can be mapped to XML via several mechanisms:

- **Jackson XML:** module `com.fasterxml.jackson.dataformat:jackson-dataformat-xml`, using `XmlMapper`. Spring MVC provides `MappingJackson2XmlHttpMessageConverter`.
- **JAXB:** uses the Jakarta XML Binding API and a runtime implementation. Spring MVC provides `Jaxb2RootElementHttpMessageConverter` when applicable; WebFlux provides `Jaxb2XmlEncoder`/`Jaxb2XmlDecoder` when the codec registry and JAXB are available.
- **Custom XML:** uses `Marshaller`/`Unmarshaller`, `Source`/XML streams, or custom writers for special API contracts.

### Adding produces=application/xml Alone Is Not Enough

~~~java
@GetMapping(produces = MediaType.APPLICATION_XML_VALUE)
Product product() {
    return new Product(...);
}
~~~

This is an illustrative snippet. Without a converter/codec able to write `Product` as XML, the endpoint **will not work** from the annotation alone. Negotiation or write errors can occur depending on timing and mapping; do not promise one uniform status across all setups.

### Jackson XML in Spring MVC and Java 17+

Gradle dependencies using Spring Boot 3.3 dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'com.fasterxml.jackson.dataformat:jackson-dataformat-xml'
}
~~~

Maven needs the equivalent dependency. Boot manages the version when the BOM/plugin is configured. Jackson XML annotation package:

~~~java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;
~~~

JavaBean example:

~~~java
@JacksonXmlRootElement(localName = "product")
public class Product {
    private long id;
    private String name;

    public Product() {}

    public long getId() { return id; }
    public void setId(long id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}
~~~

This is an illustrative POJO that must be placed in a validly named file/class with imports; the complete example later uses a nested `public static class` to stay runnable.

With the Jackson XML converter registered, DTOs can be read/written as XML. When switching to XML, **root and property element forms** may need annotations; do not assume the XML root name always equals the class name or matches JSON field names.

### XML Is Not 1:1 Equivalent to JSON

JSON array:

~~~json
{"tags":["java","spring"]}
~~~

XML may use repeated tags, wrapper elements, or attributes:

~~~xml
<product>
    <tags>
        <tag>java</tag>
        <tag>spring</tag>
    </tags>
</product>
~~~

Exact mapping depends on the DTO, Jackson XML/JAXB annotations, and mapper configuration. Namespaces, XML attributes, CDATA, mixed content, and schema validation all need separate attention; you cannot guarantee every JSON document has a lossless XML equivalent.

### XML Security

XML carries attack surfaces such as external entity resolution/XXE, XML bombs, deeply nested structures, and huge documents. For untrusted XML input:

- Use up-to-date parser/converter libraries configured with safe protections.
- Disable DTDs and external entity access unless legitimately required.
- Enforce limits on request size, nesting depth, entity expansion, and resource usage.
- Never log XML containing secrets or configure parsers to read local files.
- Audit the specific parser's security policies and test rejected payloads; never assume all XML decoders share identical defaults.

**Do not** enable XML if the API does not need it; many applications offer only JSON to reduce contract overhead and maintenance surface.

## 11. consumes and produces: Declaring the Endpoint Contract

In a controller:

~~~java
@PostMapping(
    path = "/api/products",
    consumes = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    },
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    }
)
~~~

Meaning:

- The POST body **can** be JSON or XML.
- The client **can** request a JSON or XML response.
- Spring must have a suitable reader/converter **for the input type** and writer **for the output type**.
- `consumes`/`produces` are routing/content-negotiation conditions; they do not install codecs.

A JSON request to the endpoint can receive an XML response:

~~~http
POST /api/products HTTP/1.1
Content-Type: application/json
Accept: application/xml

{"id":7,"name":"pen"}
~~~

The server can deserialize JSON into `Product` and then serialize `Product` into XML. When business data transformation is needed, the controller/service decides the transformation; converters handle only wire representation.

### One Handler Supporting Multiple Media Types

When business logic is identical, maintaining one method is usually cleaner:

~~~java
@GetMapping(
    path = "/api/products/{id}",
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    }
)
Product get(@PathVariable long id) {
    return new Product(...);
}
~~~

This avoids duplicating two methods with the same path/HTTP method differing only in `produces` and having to sync business logic. If XML and JSON require markedly different schemas, design dedicated DTOs or methods intentionally.

### Do Not Guess Responses When Accept Is Ambiguous

An endpoint advertising both JSON and XML has multiple acceptable representations when a client sends `Accept: */*`. Which converter takes precedence can depend on registry order, media type specificity, and configuration. Clients needing a specific representation should send an **explicit `Accept`**; automated tests should as well.

## 12. Runnable Spring Boot MVC Example: JSON, Text, Binary, and XML

This is a **standalone Spring MVC project**, using Java 17+ and Spring Boot 3.3.x. It includes embedded Tomcat from `starter-web` and Jackson XML from the extra dependency.

### 12.1. Dependencies

In a `build.gradle` already containing the Spring Boot Gradle plugin, repositories, and Java toolchain:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'com.fasterxml.jackson.dataformat:jackson-dataformat-xml'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is the **dependencies block**, not the full `build.gradle`. If using Maven, add the equivalent dependencies per the Spring Boot BOM. You do not need to declare a manual version for `jackson-dataformat-xml` when Boot dependency management manages it.

### 12.2. Complete Java Source File

Create **src/main/java/com/example/formats/FormatsApplication.java**:

~~~java
package com.example.formats;

import java.util.Locale;
import java.util.Map;

import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class FormatsApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormatsApplication.class, args);
    }

    @JacksonXmlRootElement(localName = "product")
    public static class Product {

        private long id;
        private String name;

        public Product() {}

        public Product(long id, String name) {
            this.id = id;
            this.name = name;
        }

        public long getId() {
            return id;
        }

        public void setId(long id) {
            this.id = id;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }
    }

    @RestController
    @RequestMapping("/api")
    public static class FormatsController {

        @GetMapping(
                path = "/products/{id}",
                produces = {
                    MediaType.APPLICATION_JSON_VALUE,
                    MediaType.APPLICATION_XML_VALUE
                }
        )
        public Product find(@PathVariable long id) {
            return new Product(id, "item-" + id);
        }

        @PostMapping(
                path = "/products/echo",
                consumes = {
                    MediaType.APPLICATION_JSON_VALUE,
                    MediaType.APPLICATION_XML_VALUE
                },
                produces = {
                    MediaType.APPLICATION_JSON_VALUE,
                    MediaType.APPLICATION_XML_VALUE
                }
        )
        public Product echo(@RequestBody Product product) {
            return product;
        }

        @GetMapping(
                path = "/text",
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        public String text() {
            return "Xin chào";
        }

        @PostMapping(
                path = "/text/upper",
                consumes = MediaType.TEXT_PLAIN_VALUE,
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        public String upper(@RequestBody String text) {
            return text.toUpperCase(Locale.ROOT);
        }

        @GetMapping(
                path = "/bytes",
                produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
        )
        public ResponseEntity<byte[]> bytes() {
            byte[] data = new byte[] {
                0x41, 0x00, (byte) 0xFF
            };

            return ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_OCTET_STREAM)
                    .header(
                            HttpHeaders.CONTENT_DISPOSITION,
                            ContentDisposition.attachment()
                                    .filename("sample.bin")
                                    .build().toString()
                    )
                    .body(data);
        }

        @PostMapping(
                path = "/bytes/count",
                consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        public Map<String, Integer> count(@RequestBody byte[] data) {
            return Map.of("size", data.length);
        }
    }
}
~~~

**This is a complete Java file** inside a Spring Boot project with declared dependencies. Do not compile it with bare `javac` without Spring, Servlet, and Jackson on the classpath. The nested `public static Product` has a zero-argument constructor and getters/setters so both Jackson JSON and Jackson XML can read/write it; `@JacksonXmlRootElement` determines the XML root element.

### 12.3. Configuration and Startup

Create **src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080
~~~

From the Gradle project root:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Wait for the embedded server to start. If port 8080 is busy, change `server.port` and adjust the URLs in test commands.

### 12.4. JSON Response

~~~bash
curl -i http://localhost:8080/api/products/7 \
  -H 'Accept: application/json'
~~~

Typical response:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"id":7,"name":"item-7"}
~~~

Headers may include parameters; key order, whitespace, and content length are determined by the runtime. The body conveys `id=7` and `name=item-7`.

### 12.5. XML Response from the Same Endpoint

~~~bash
curl -i http://localhost:8080/api/products/7 \
  -H 'Accept: application/xml'
~~~

An equivalent XML body:

~~~xml
<product>
    <id>7</id>
    <name>item-7</name>
</product>
~~~

Jackson XML may omit newline whitespace or add an XML declaration depending on settings; therefore **never assert byte-for-byte raw XML string equality** as a default contract. Tests should verify XML well-formedness, root element, and required field contents.

### 12.6. JSON Request, XML Response

~~~bash
curl -i -X POST http://localhost:8080/api/products/echo \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/xml' \
  --data '{"id":8,"name":"pen"}'
~~~

The JSON request is deserialized into `Product`, and then `Product` is serialized into XML. The exercise proves **input `Content-Type` and output `Accept` are independent**.

### 12.7. XML Request, JSON Response

~~~bash
curl -i -X POST http://localhost:8080/api/products/echo \
  -H 'Content-Type: application/xml' \
  -H 'Accept: application/json' \
  --data '<product><id>8</id><name>pen</name></product>'
~~~

Logical JSON response body:

~~~json
{"id":8,"name":"pen"}
~~~

If this POST fails in another project, verify that the XML converter is registered, the POJO has compatible constructor/getters/setters/annotations, request `Content-Type`, parser, and exception logs. Never "fix" it by labeling XML bytes as JSON.

### 12.8. Text/plain

~~~bash
curl -i http://localhost:8080/api/text \
  -H 'Accept: text/plain'
~~~

Body produced by the code:

~~~text
Xin chào
~~~

Send a text body:

~~~bash
curl -i -X POST http://localhost:8080/api/text/upper \
  -H 'Content-Type: text/plain; charset=UTF-8' \
  -H 'Accept: text/plain' \
  --data-binary 'hello'
~~~

Exact body for ASCII:

~~~text
HELLO
~~~

ASCII is chosen here for simple byte/text comparison; for accented text, verify UTF-8 and Unicode normalization in your environment.

### 12.9. Binary Response

~~~bash
curl -i http://localhost:8080/api/bytes \
  -H 'Accept: application/octet-stream'
~~~

The response carries three bytes `0x41 0x00 0xFF`, not three printable characters. Save it to a file:

~~~bash
curl -sS http://localhost:8080/api/bytes -o sample.bin
~~~

On Linux/macOS, inspect hex:

~~~bash
od -An -tx1 sample.bin
~~~

Expected hex values:

~~~text
41 00 ff
~~~

Spacing and line formatting from `od` may vary; the three bytes are what matter. Do not open arbitrary binary files as UTF-8 to inspect correctness.

### 12.10. Binary Request, JSON Response

Create `input.bin` containing `0x41, 0x00, 0xFF`, or upload the downloaded `sample.bin`:

~~~bash
curl -i -X POST http://localhost:8080/api/bytes/count \
  -H 'Content-Type: application/octet-stream' \
  -H 'Accept: application/json' \
  --data-binary '@sample.bin'
~~~

Response body:

~~~json
{"size":3}
~~~

This demonstrates `ByteArrayHttpMessageConverter` reading raw bytes into the `byte[]` parameter while Jackson's JSON converter writes the returned `Map` as JSON.

### 12.11. PowerShell: Avoiding Escaping Errors

On Windows, invoke `curl.exe` to avoid PowerShell's `curl` alias:

~~~powershell
curl.exe -i -H "Accept: application/json" "http://localhost:8080/api/products/7"
curl.exe -i -H "Accept: application/xml" "http://localhost:8080/api/products/7"
curl.exe -sS "http://localhost:8080/api/bytes" -o sample.bin
curl.exe -i -X POST "http://localhost:8080/api/bytes/count" -H "Content-Type: application/octet-stream" -H "Accept: application/json" --data-binary "@sample.bin"
~~~

When sending JSON/XML with many quotes, a reliable pattern is writing the body to a UTF-8 file and passing `--data-binary "@payload.json"` or `"@payload.xml"` rather than relying on escaping differences between PowerShell 5.1 and PowerShell 7.

## 13. Testing the MVC Example with MockMvc

Create **src/test/java/com/example/formats/FormatsApplicationTests.java**:

~~~java
package com.example.formats;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FormatsApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void producesJsonWhenClientAcceptsJson() throws Exception {
        mvc.perform(get("/api/products/9")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(9))
            .andExpect(jsonPath("$.name").value("item-9"));
    }

    @Test
    void producesXmlWhenClientAcceptsXml() throws Exception {
        mvc.perform(get("/api/products/9")
                    .accept(MediaType.APPLICATION_XML))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_XML))
            .andExpect(content().string(
                    containsString("<name>item-9</name>")));
    }

    @Test
    void canReadXmlAndReturnJson() throws Exception {
        mvc.perform(post("/api/products/echo")
                    .contentType(MediaType.APPLICATION_XML)
                    .accept(MediaType.APPLICATION_JSON)
                    .content(
                        "<product><id>8</id><name>pen</name></product>"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(8))
            .andExpect(jsonPath("$.name").value("pen"));
    }

    @Test
    void returnsPlainText() throws Exception {
        mvc.perform(post("/api/text/upper")
                    .contentType(MediaType.TEXT_PLAIN)
                    .accept(MediaType.TEXT_PLAIN)
                    .content("hello"))
            .andExpect(status().isOk())
            .andExpect(content().string("HELLO"));
    }

    @Test
    void returnsExactBinaryBytes() throws Exception {
        mvc.perform(get("/api/bytes")
                    .accept(MediaType.APPLICATION_OCTET_STREAM))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_OCTET_STREAM))
            .andExpect(content().bytes(
                    new byte[]{0x41, 0x00, (byte) 0xFF}));
    }

    @Test
    void rejectsUnsupportedRequestContentType() throws Exception {
        mvc.perform(post("/api/products/echo")
                    .contentType(MediaType.TEXT_PLAIN)
                    .content("hello"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void rejectsUnacceptableResponseType() throws Exception {
        mvc.perform(get("/api/products/9")
                    .accept(MediaType.APPLICATION_PDF))
            .andExpect(status().isNotAcceptable());
    }

    @Test
    void rejectsMalformedJson() throws Exception {
        mvc.perform(post("/api/products/echo")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("{bad-json"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

PowerShell:

~~~powershell
.\gradlew.bat test
~~~

These tests verify JSON/XML selection, converting XML input into JSON output, plain text, byte-exact binary output, invalid input media types (415), invalid output media types (406), and malformed JSON (400).

**Note:** The XML test checks for a field in XML rather than enforcing a fixed raw string with specific indentation/whitespace. If DTO/XML mapping changes, add XML parser assertions for namespaces/roots/schemas instead of relying on whitespace positions.

`MockMvc` tests the Servlet MVC pipeline without opening a real TCP socket. It does not replace integration tests when deployment involves reverse proxies, TLS, or container body size limits.

## 14. Configuring Converters in Spring Boot MVC

Spring Boot 3.3 automatically registers converters based on the classpath. With `starter-web`, JSON is typically available out of the box. Adding the Jackson XML extension enables the corresponding XML converter under Boot auto-configuration.

### Observing the Actual Registry

You can inject `RequestMappingHandlerAdapter` in an MVC application and print the list:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter;

@Configuration(proxyBeanMethods = false)
class ConverterDiagnostics {

    @Bean
    ApplicationRunner showConverters(
            RequestMappingHandlerAdapter adapter) {
        return args -> adapter.getMessageConverters().forEach(
                c -> System.out.println(
                        c.getClass().getSimpleName() + " " +
                        c.getSupportedMediaTypes()
                )
        );
    }
}
~~~

This is an **optional diagnostic configuration class** in the MVC project. It helps inspect runtime converters; it does not run standalone via `javac`. Do not assume identical output order across all versions/classpaths.

### When to Add a New Converter?

If an uncommon format has a clear contract, you can write an `HttpMessageConverter` or register an additional converter bean. For `text/plain`, JSON, `byte[]`, and `Resource`, you normally **do not need** a custom converter. For XML, prefer standard integrated XML libraries over concatenating XML Strings manually.

### Modifying ObjectMapper

If you only want to change field naming, date formats, inclusion, or JSON serializers/deserializers, adjust `ObjectMapper`/Boot Jackson customizers instead of replacing the entire message converter.

Example property:

~~~yaml
spring:
  jackson:
    serialization:
      indent-output: true
~~~

This enables pretty-printing for Jackson JSON. It does not alter binary bytes or automatically add an XML writer if dependencies are missing.

### WebMvcConfigurer

~~~java
@Configuration(proxyBeanMethods = false)
class ConverterConfig implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        // Only modify after identifying the converter to fine-tune.
    }
}
~~~

This is a configuration snippet requiring matching Spring imports. `extendMessageConverters` lets you adjust the already-registered list. **Never use `@EnableWebMvc` just to add XML**, as doing so can disable Boot's MVC auto-configuration conveniences.

## 15. Equivalent Example in Spring WebFlux

This section uses a **separate project**—do not add `starter-webflux` to the MVC project expecting it to switch to reactive. When Spring Boot sees both `starter-web` and `starter-webflux`, it normally selects MVC by default.

### Dependencies

In the `build.gradle` of a WebFlux project with plugin/repositories configured:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'jakarta.xml.bind:jakarta.xml.bind-api'
    implementation 'org.glassfish.jaxb:jaxb-runtime'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Here XML uses **JAXB** in WebFlux 6.1, not MVC's `MappingJackson2XmlHttpMessageConverter`. Spring WebFlux provides `Jaxb2XmlDecoder`/`Jaxb2XmlEncoder` when classpath and configuration align. If the runtime does not register XML codecs, inspect the registry and configure explicitly as needed; do not assume all XML dependencies are auto-detected identically.

### Java Source File for WebFlux

Create **src/main/java/com/example/reactiveformats/ReactiveFormatsApplication.java**:

~~~java
package com.example.reactiveformats;

import java.util.Locale;

import jakarta.xml.bind.annotation.XmlAccessType;
import jakarta.xml.bind.annotation.XmlAccessorType;
import jakarta.xml.bind.annotation.XmlRootElement;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveFormatsApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ReactiveFormatsApplication.class, args);
    }

    @XmlRootElement(name = "product")
    @XmlAccessorType(XmlAccessType.FIELD)
    public static class Product {

        private long id;
        private String name;

        public Product() {}

        public Product(long id, String name) {
            this.id = id;
            this.name = name;
        }

        public long getId() {
            return id;
        }

        public void setId(long id) {
            this.id = id;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }
    }

    @RestController
    public static class Controller {

        @GetMapping(
                path = "/api/products/{id}",
                produces = {
                    MediaType.APPLICATION_JSON_VALUE,
                    MediaType.APPLICATION_XML_VALUE
                }
        )
        public Mono<Product> get(@PathVariable long id) {
            return Mono.just(new Product(id, "item-" + id));
        }

        @PostMapping(
                path = "/api/products/echo",
                consumes = {
                    MediaType.APPLICATION_JSON_VALUE,
                    MediaType.APPLICATION_XML_VALUE
                },
                produces = {
                    MediaType.APPLICATION_JSON_VALUE,
                    MediaType.APPLICATION_XML_VALUE
                }
        )
        public Mono<Product> echo(
                @RequestBody Mono<Product> input) {
            return input;
        }

        @PostMapping(
                path = "/api/text/upper",
                consumes = MediaType.TEXT_PLAIN_VALUE,
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        public Mono<String> upper(
                @RequestBody Mono<String> input) {
            return input.map(
                    s -> s.toUpperCase(Locale.ROOT));
        }

        @GetMapping(
                path = "/api/bytes",
                produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
        )
        public Mono<byte[]> bytes() {
            return Mono.just(
                    new byte[]{0x41, 0x00, (byte) 0xFF});
        }
    }
}
~~~

This is a complete file inside a WebFlux project with matching dependencies. JAXB annotations declare the root and field mapping for the JAXB XML codec. Jackson JSON serializes/deserializes via getters/setters. There is no Servlet `HttpMessageConverter` in this code.

If the application fails to handle XML despite having JAXB dependencies, an **intentional** way to register `Jaxb2XmlDecoder`/`Encoder` is inside `ServerCodecConfigurer`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.DecoderHttpMessageReader;
import org.springframework.http.codec.EncoderHttpMessageWriter;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.http.codec.xml.Jaxb2XmlDecoder;
import org.springframework.http.codec.xml.Jaxb2XmlEncoder;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
class AdditionalXmlCodecs implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.customCodecs().register(
                new DecoderHttpMessageReader<>(
                        new Jaxb2XmlDecoder()));
        configurer.customCodecs().register(
                new EncoderHttpMessageWriter<>(
                        new Jaxb2XmlEncoder()));
    }
}
~~~

This is an **optional supplementary class**, only needed after verifying the registry lacks a suitable XML codec and the DTO genuinely supports JAXB. If default codecs already include XML, do not register duplicates. Avoid `registerDefaults(false)` because it drops JSON, text, and binary codecs.

### Buffer Configuration for WebFlux

~~~yaml
spring:
  codec:
    max-in-memory-size: 512KB
~~~

This Boot 3.3 property bounds in-memory buffering on codecs when aggregating data. It is not a cap on entire file uploads or every response. For large JSON/XML documents, consider quotas, streaming, and request size limits. When using a manually created `WebClient`, verify its codec config instead of assuming server properties apply.

### Testing WebFlux with curl

~~~bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/products/7

curl -i -H 'Accept: application/xml' \
  http://localhost:8080/api/products/7

curl -i -X POST \
  -H 'Content-Type: text/plain' \
  -H 'Accept: text/plain' \
  --data-binary 'hello' \
  http://localhost:8080/api/text/upper
~~~

JSON and XML require matching codecs; the text endpoint returns `HELLO`. For XML, if the application rejects the representation, inspect the exact error and XML codec registry rather than swapping media types to hide the bug.

## 16. Testing WebFlux with WebTestClient

Create **src/test/java/com/example/reactiveformats/ReactiveFormatsApplicationTests.java**:

~~~java
package com.example.reactiveformats;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ReactiveFormatsApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void writesJson() {
        client.get()
                .uri("/api/products/7")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(7)
                .jsonPath("$.name").isEqualTo("item-7");
    }

    @Test
    void writesXmlWhenJaxbCodecIsAvailable() {
        client.get()
                .uri("/api/products/7")
                .accept(MediaType.APPLICATION_XML)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_XML);
    }

    @Test
    void readsTextAndReturnsUppercase() {
        client.post()
                .uri("/api/text/upper")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("HELLO");
    }

    @Test
    void rejectsUnacceptableMediaType() {
        client.get()
                .uri("/api/products/7")
                .accept(MediaType.APPLICATION_PDF)
                .exchange()
                .expectStatus().isNotAcceptable();
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

`WebTestClient` verifies WebFlux's HTTP-level behavior. The XML test confirms headers/status when the JAXB codec is available; in other environments, a custom codec and JAXB runtime may be required. Add XML parser assertions if the API mandates specific XML schemas/namespaces.

**Never** call `.block()` inside a WebFlux controller to unwrap XML/JSON objects from `Mono`, and never call `subscribe()` manually to write responses. The runtime manages subscription/cancellation while codecs operate on publishers.

## 17. Form, Multipart, and Raw Binary: Distinguishing Multi-Layer Content

A `multipart/form-data` request can carry a PNG file, JSON metadata, and text parts in a single body:

~~~http
POST /upload HTTP/1.1
Content-Type: multipart/form-data; boundary=...

--...
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"name":"demo"}
--...
Content-Disposition: form-data; name="file"; filename="image.png"
Content-Type: image/png

...PNG bytes...
--...--
~~~

This is an abbreviated multipart diagram, not a valid wire payload because the boundaries/footer use ellipses.

**The top-level request `Content-Type` is `multipart/form-data`**; each part can have its own `Content-Type` such as `application/json` or `image/png`. Accordingly:

- MVC provides `MultipartFile`, `Part`, `@RequestPart`, and `MultipartResolver`/Servlet multipart support.
- WebFlux provides `FilePart`, `Part`, `PartEvent`, or `getMultipartData` depending on needs.
- `@RequestPart` for a JSON metadata part can use a message converter/reader for that **part body** when properly formatted.
- Do not use `@RequestBody byte[]` to read multipart requests and assume all bytes are the PNG file.
- Reading raw bodies and manually parsing boundaries is unnecessary and error-prone.

`application/x-www-form-urlencoded` is also not JSON; MVC typically uses `@RequestParam`/`@ModelAttribute`, while WebFlux offers `getFormData` and appropriate body readers.

## 18. When Is Streaming Needed Instead of Buffering the Whole Body?

Using `byte[]` works for small payloads. For large files/downloads or Server-Sent Events, avoid loading everything into memory.

### MVC Streaming

Spring MVC provides `StreamingResponseBody`, `Resource`, and resource handlers. When using `StreamingResponseBody`, the application writes bytes directly to `OutputStream` instead of Jackson DTO serialization.

Illustrative snippet:

~~~java
@GetMapping(
    path = "/stream",
    produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
)
StreamingResponseBody stream() {
    return output -> {
        output.write(new byte[]{0x41, 0x42, 0x43});
    };
}
~~~

This is a method inside `@RestController` importing `StreamingResponseBody`, not a standalone program. For large datasets, handle I/O, flushing, exceptions/cancellation, and resource ownership. Do not assume streaming makes every task zero-heap.

### WebFlux Streaming

WebFlux can write `Flux<DataBuffer>`, `Resource`, or `Flux<DTO>` depending on media type. With NDJSON:

~~~java
@GetMapping(
    path = "/events",
    produces = MediaType.APPLICATION_NDJSON_VALUE
)
Flux<EventDto> events() {
    return Flux.just(
        new EventDto(1, "started"),
        new EventDto(2, "finished")
    );
}
~~~

This snippet requires record `EventDto` and appropriate imports. NDJSON emits multiple JSON objects line-by-line, **not a single JSON array**. Streaming can be buffered by proxies/clients; test using `curl -N` or a reactive client with `bodyToFlux`.

### Binary Streaming and DataBuffer Ownership

In WebFlux, pooled `DataBuffer` instances may require proper release per contract when application code retains/discards buffers. When returning normal DTOs or small `byte[]` via standard codecs, let the framework manage lifecycles. Never subscribe to the raw body manually while also passing the same body to `@RequestBody`; streams do not replay automatically.

## 19. Common HTTP Error Codes by Format

| Scenario | Typical Response | What to Check |
|---|---|---|
| Syntactically invalid JSON request | 400 Bad Request | JSON parser, DTO, `Content-Type` |
| Syntactically invalid XML request | 400 Bad Request | XML parser, DTO mapping, `Content-Type` |
| Required `@RequestBody` with empty body | 400 Bad Request | Required/body binding |
| Sending `text/plain` to an endpoint consuming only JSON/XML | 415 Unsupported Media Type | Request `Content-Type` |
| Client only accepts PDF while endpoint only produces JSON/XML | 406 Not Acceptable | `Accept`, `produces`, available writers |
| No controller path matches | 404 Not Found | Handler mapping, path |
| Unsupported HTTP method | 405 Method Not Allowed | `GET`/`POST`/`PUT`, etc. |
| Serializer fails while writing object | May be 500 or stream error | Converter/writer, object graph |
| Body exceeds size limit | Status depends on layer/config | Proxy/server/codec limits |
| Image payload returns non-PNG bytes | Client fails to parse despite HTTP 200 | Actual bytes and `Content-Type` |

**Do not guarantee a single status for all missing-XML-converter scenarios.** When a handler matches `consumes`/`produces` yet lacks a converter capable of reading/writing the DTO, the error can vary across handler selection, framework versions, and exception handling. Inspect application logs and test on the exact version.

### Do Not Confuse 406 with 415

- **415:** the client sent a request body whose media type the server cannot accept/read.
- **406:** the client requested a response representation the server cannot provide.

For example, `Accept: application/xml` paired with `Content-Type: application/json` is not a cause of 415. Only adjust `Content-Type`/`consumes` when the input format is rejected.

## 20. Distinguishing Converters, Encoders, Parsers, and Schema Validators

Concepts frequently conflated:

| Concept | Role |
|---|---|
| `HttpMessageConverter` (MVC) | Integrates reading/writing HTTP bodies with content types |
| `HttpMessageReader`/`Writer` (WebFlux) | Integrates HTTP bodies with reactive codecs |
| Jackson `ObjectMapper` | Serializes/deserializes JSON |
| Jackson `XmlMapper` | Serializes/deserializes XML via Jackson |
| JAXB `Marshaller`/`Unmarshaller` | Maps Java objects and XML via JAXB |
| String decoder/encoder | Converts bytes and characters according to charset |
| `byte[]`/`Resource` converter | Reads/writes raw bytes and resources |
| JSON Schema/XML Schema validator | Validates structure against application-defined schemas |
| Bean Validation | Validates constraints on Java DTOs, e.g., `@NotBlank` |
| `ConversionService` | Converts between Java types during binding, not an HTTP body decoder |

**A well-formed XML document does not automatically satisfy an XML Schema**, and a parseable JSON object does not automatically pass Bean Validation or business rules.

DTO example:

~~~java
public record CreateProduct(
    @NotBlank String name,
    @Min(1) int quantity
) {}
~~~

This is an illustrative Java 17+ record requiring `jakarta.validation` constraints and `spring-boot-starter-validation`. Once the converter/codec constructs the DTO, Spring Validation validates it when `@Valid` is present on the parameter. Validation does not make the parser understand malformed structure.

## 21. Data Representation and API Versioning

An API supporting multiple formats must decide whether they share **the same semantic schema**. For example, a Java record with `price` (`BigDecimal`), date/time, and `tags`:

~~~json
{
  "id": 3,
  "price": "19.95",
  "effectiveAt": "2026-01-01T00:00:00Z",
  "tags": ["new", "sale"]
}
~~~

This is an application-designed hypothetical contract, not Jackson's mandatory default for `BigDecimal` (Jackson does not force `BigDecimal` to serialize as a String unless using a String field or custom serializer).

XML representations may require root elements, namespaces, and wrapper elements for tags. When clients depend on a long-lived schema, changing field names, number types, or array structures breaks contracts even if the endpoint still returns 200.

### Watch Out for Accept and Versioning

~~~http
Accept: application/vnd.example.product.v1+json
~~~

This is an example custom vendor media type. JSON converters can match `application/*+json`, but the handler's `produces` must permit that representation and the API must maintain the versioned contract. Do not assume adding `+json` creates automatic data versioning.

### Vary: Accept with Caches

If one URL can return JSON or XML based on `Accept`, caches/proxies need to distinguish representations, typically via:

~~~http
Vary: Accept
~~~

Do not assume this header is automatically added by the framework across every path, proxy, or cache setup. Verify actual behavior and configure caching policies so an XML client never receives cached JSON for the same URL.

## 22. JSON/XML Parsing and Security Considerations

### Do Not Deserialize Arbitrary Java Types from Input

If a mapper enables overly broad polymorphic default typing for untrusted data, attackers may coerce unexpected object types. Use explicit target DTOs and safe mapper settings. Never put persistence entities, password hashes, or tokens directly into responses.

### Limit Size, Depth, and Concurrent Requests

A huge JSON array or deeply nested XML document can exhaust CPU/memory. Enforce limits at multiple layers:

- Reverse proxy or ingress.
- Servlet container / Reactor Netty HTTP runtime.
- Codec/request body aggregation.
- Multipart settings.
- Business-level counts, pagination, rate limits, and timeouts.

Never raise `max-in-memory-size` to hundreds of MBs solely to silence errors without evaluating concurrent requests and memory budgets.

### XML Entity Expansion / External Resources

Never allow parsers to fetch external DTDs, external entities, or access the filesystem/network on client-supplied XML unless strictly required and sandboxed. Check configurations and test XXE/DoS protections for your exact parser implementation.

### Content-Type Sniffing

Browsers may interpret content differently from server headers if protections are missing. For binary downloads or untrusted content, consider:

~~~http
X-Content-Type-Options: nosniff
~~~

This header is part of security hardening; it does not replace authentication/authorization and does not repair malformed bytes.

### User-Uploaded Binary Files

When accepting image/PDF/ZIP uploads, do not blindly trust client-supplied filenames, extensions, or `Content-Type`. Verify magic bytes, use safe parsers, enforce size limits, run antivirus checks, isolate storage, enforce access control, and configure download `Content-Disposition`. Never store uploaded files directly under client-supplied names/paths.

## 23. Practical Debugging: Identifying Which Converter/Codec Participates

When responses look wrong:

1. **Confirm the web stack:** MVC or WebFlux? Are both `starter-web` and `starter-webflux` present?
2. **Inspect incoming headers:** Are request `Content-Type` and `Accept` actually reaching the server intact?
3. **Inspect controller annotations:** `consumes`/`produces`, path, and HTTP method.
4. **Inspect Java types:** `@RequestBody Product` vs. `String`/`byte[]`? Does the controller return DTO, `String`, `Resource`, `Mono`/`Flux`?
5. **Inspect classpath:** Is Jackson JSON present? For XML, is `jackson-dataformat-xml` or appropriate JAXB API/runtime present?
6. **Inspect the converter/codec registry:** supported types/media types, ordering, and customizations.
7. **Inspect exceptions:** `HttpMessageNotReadableException`, `HttpMessageNotWritableException`, `UnsupportedMediaType`, `NotAcceptable`, `DataBufferLimitException`, XML parse errors.
8. **Test with curl:** use `-i` for headers, `-H Accept` explicitly, `--data-binary` for raw bodies, `-o` when downloading binary.
9. **Inspect actual bytes:** JSON parser/XML parser/hex viewer—never rely solely on file extensions.
10. **Check proxy/cache/security:** forwarded headers, cache `Vary`, CORS, content sniffing, and payload limits.

### Logging Converters in MVC

~~~java
@Configuration(proxyBeanMethods = false)
class DiagnosticsConfig {

    @Bean
    ApplicationRunner listConverters(
            RequestMappingHandlerAdapter adapter) {
        return args -> adapter.getMessageConverters().forEach(
                converter -> System.out.println(
                    converter.getClass().getName())
        );
    }
}
~~~

This is a configuration snippet requiring imports in an MVC project. It inspects MVC's runtime adapter list, not WebFlux codecs.

### Logging Codecs in WebFlux

Spring Boot configures `ServerCodecConfigurer` and `CodecCustomizer`. A standalone `ServerCodecConfigurer.create()` instance you instantiate manually does not include Boot customizers, so never use it as proof of the runtime registry. Debug the active `WebFluxConfigurer`/`CodecCustomizer` or inspect the configured bean to see available decoders/encoders.

DEBUG/TRACE logs can expose headers/bodies, especially with `spring.codec.log-request-details`; enable only in accordance with data protection policies.

## 24. Common Mistakes and Fixes

### Mistake 1: Client Requests XML Without XML Dependencies

Symptom: JSON API works, XML requests/responses fail. Check whether Spring MVC has `MappingJackson2XmlHttpMessageConverter` or a matching JAXB converter, and whether WebFlux has a registered JAXB XML codec. Add the needed dependency/config and test; never swap XML headers to JSON to hide the issue.

### Mistake 2: Controller Returns a String Containing JSON with application/json

Symptom: clients fail to parse JSON, particularly when the String lacks quotes or proper escaping. Return a DTO/Map and let Jackson serialize. If it is truly plain text, return `text/plain`.

### Mistake 3: Converting byte[] to String Before Sending

Symptom: binary files corrupt, `0xFF` bytes become replacement characters, or byte lengths change. Return `byte[]`/`Resource` without charset transformations.

### Mistake 4: XML Nested Collections Differ from JSON

Symptom: XML has unexpected wrapper tags or misses items when parsed. Define proper XML mapping annotations/schemas and test nested arrays, attributes, and namespaces. Never assume 1:1 XML=JSON mapping.

### Mistake 5: Corrupted Unicode Text

Symptom: Vietnamese diacritics break in plain text or XML. Check `Content-Type`, charset, actual bytes, XML encoding declaration, shell encoding, and proxies. Use UTF-8 consistently.

### Mistake 6: Using @RequestBody Product for Raw octet-stream

Symptom: converter cannot read `Product` from `application/octet-stream`. If the payload is genuinely raw bytes, accept `byte[]`/`Resource` and invoke a business parser afterward; never label raw bytes as `application/json`.

### Mistake 7: GET Without Accept Produces Unexpected Format

Symptom: the same endpoint returns JSON for one client and XML for another. When a specific format is needed, clients should send explicit `Accept`; the server can also establish an intentional default representation via configuration/mapping.

### Mistake 8: Reading Multipart as a JSON Body

Symptom: 415 errors or JSON parser choking on boundaries. Use `@RequestPart`/`MultipartFile`/`FilePart` per stack, separating the JSON metadata part from file parts.

### Mistake 9: Custom Converter Accepts Every Media Type

Symptom: JSON/XML/text serializes incorrectly after adding a custom converter. Restrict `canRead`/`canWrite`/`supports` to exact Java types and media types, preserve default converters, and add regression tests.

### Mistake 10: Abusing XML Parser Resources

Symptom: XML entities/DTDs trigger network calls, local file reads, or CPU/memory spikes. Configure parsers securely, block external entities, and enforce quotas.

## 25. Exercises and Self-Check Questions

**Question 1.** Request body is XML, `Accept` is `application/json`. Can the server return JSON?

**Answer:** Yes, if the endpoint accepts XML input, has a reader to decode XML into a Java object, and has a JSON writer to encode the response.

**Question 2.** Why does adding `produces=application/xml` not guarantee a DTO will be returned as XML?

**Answer:** A converter/codec supporting both the Java type and XML is still required. Annotations do not install serializer libraries.

**Question 3.** Do Spring MVC and WebFlux share `HttpMessageConverter`?

**Answer:** No. MVC uses `HttpMessageConverter`; WebFlux uses `HttpMessageReader`/`Writer` and `Encoder`/`Decoder` integrated with Reactive Streams.

**Question 4.** A response has `Content-Type: application/pdf` but the body is a JSON string. Can clients reliably open it as a PDF?

**Answer:** No. Headers do not generate PDFs. The server must supply real PDF bytes.

**Question 5.** To return a 100 MB ZIP file, should you allocate a large `byte[]` in the controller?

**Answer:** Usually use `Resource`/streaming and manage I/O, memory, and timeouts. `byte[]` holds the entire file in heap memory at once.

**Question 6.** Why can `StringHttpMessageConverter` cause surprises when returning `String` with `produces=application/json`?

**Answer:** Because the String converter writes raw text without wrapping it as a JSON string literal. Returning a DTO or record is the clean way to emit JSON objects/arrays.

**Question 7.** Why is HTTP 415 different from HTTP 406?

**Answer:** 415 concerns an unsupported request body media type; 406 concerns a client-requested response representation the server cannot produce.

**Question 8.** Is successful XML parsing enough to guarantee business validity?

**Answer:** No. XML Schema/Bean Validation, authentication/authorization, and business rules are still required.

**Question 9.** In WebFlux, does adding `jackson-dataformat-xml` guarantee a JAXB XML codec is automatically available?

**Answer:** No. MVC's Jackson XML extension and WebFlux's JAXB codecs are separate mechanisms. Check dependencies, DTO annotations, and the actual WebFlux codec registry.

**Question 10.** Why might serving XML/JSON at the same URL require `Vary: Accept` for HTTP caches?

**Answer:** Because the representation changes based on `Accept`; if a cache serves one cached version for all `Accept` headers, clients can receive the wrong format.

**Question 11.** When uploading a PNG file via multipart, what is the top-level `Content-Type`?

**Answer:** Typically `multipart/form-data`; the file part itself can have `Content-Type: image/png`. Multipart parsing is needed instead of treating the entire body as PNG bytes.

**Question 12.** When reading `byte[]` containing `0x41 0x00 0xFF`, should you convert to `String` to assert output?

**Answer:** No. Use length, checksums, or byte-array/hex comparisons; converting to `String` can corrupt bytes invalid under a character encoding.

## 26. Pre-Deployment Checklist

- [ ] Confirmed whether the HTTP body genuinely uses JSON, text, binary, or XML.
- [ ] Declared `consumes`/`produces` matching the contract, distinguishing `Content-Type` and `Accept`.
- [ ] Verified Java types: DTO/record, `String`, `byte[]`, `Resource`, or `Mono`/`Flux`.
- [ ] For MVC, verified matching `HttpMessageConverter`s; for WebFlux, verified matching readers/writers/codecs.
- [ ] XML enabled only when required modules/implementations and safe parser configs are present.
- [ ] JSON serialized via `ObjectMapper`/DTOs, never via string concatenation.
- [ ] Text uses explicit encoding, consistently UTF-8 where appropriate.
- [ ] Binary preserved byte-for-byte, with specific media types when the file format is known.
- [ ] Downloads set proper `Content-Disposition` and enforce access controls.
- [ ] Large files use streaming/`Resource` with memory and timeout limits.
- [ ] Tests cover JSON/XML/text/binary, 400/406/415, malformed XML, and exact binary bytes.
- [ ] Checked cache `Vary`, proxies, CORS, and content sniffing when serving multiple representations.
- [ ] Verified XML parsers protect against XXE/DTD/external entities and payload DoS.
- [ ] Never expose entities/passwords/tokens via JSON/XML serialization.
- [ ] Avoided adding `@EnableWebMvc` or `@EnableWebFlux` just to add a converter.
- [ ] Inspected actual runtime converter/codec lists instead of guessing from annotations.

## References

- [Spring Boot 3.3 — Servlet Web Applications / HttpMessageConverters](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot 3.3 — Reactive Web Applications / HTTP Codecs](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html)
- [Spring Framework 6 — HTTP Message Conversion (MVC)](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html)
- [Spring Framework 6.1 — MappingJackson2XmlHttpMessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/converter/xml/MappingJackson2XmlHttpMessageConverter.html)
- [Spring Framework 6.1 — HTTP XML codecs (Jaxb2XmlDecoder/Encoder)](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/codec/xml/package-summary.html)
- [Spring Framework — WebFlux Codecs Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html)
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
