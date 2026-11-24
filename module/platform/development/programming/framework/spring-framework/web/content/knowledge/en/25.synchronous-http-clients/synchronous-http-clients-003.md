# Sending Requests with URI Templates, Query, Form, and Multipart Using Spring's Synchronous HTTP Client

## 1. Lesson Objectives

A Spring application often needs to call another HTTP API to fetch data, look up status, submit a form, or upload a file with metadata. With a **synchronous** HTTP client, the calling thread typically waits until the response is received and processed or a timeout/error occurs. If the URL and request body are constructed incorrectly, seemingly small issues such as `+`, `&`, `Content-Type`, and filenames can cause the server to receive different data than intended.

This lesson belongs to the **synchronous HTTP clients** group in Spring Framework Web. The main examples use **Java 17+, Spring Framework 6.1+, and Spring Boot 3.2+**, because `RestClient` was introduced in Spring Framework 6.1. To study in the Spring 6.2 branch, a compatible Spring Boot 3.4 or 3.5 can be used; pick a specific Boot 3.x version managed by the project rather than manually mixing Spring jars of different versions. The `RestTemplate` section describes the compatible option for existing code.

After this lesson, you should be able to:

- Distinguish **URI template**, **path variable**, **query parameter**, **form-urlencoded body**, and **multipart/form-data body**.
- Use `RestClient.get()`/`post()`, `.uri(...)`, `.accept(...)`, `.contentType(...)`, `.body(...)`, `.retrieve()`.
- Pass URI variables via map/arguments, and build queries with `UriBuilder`/`UriComponentsBuilder` instead of uncontrolled string concatenation.
- Understand why `C++`, `a&b`, spaces, `/`, and already percent-encoded strings must be encoded in the right context and **not double-encoded**.
- Send `application/x-www-form-urlencoded` using `MultiValueMap<String,String>` to preserve repeated values.
- Send `multipart/form-data` using `MultiValueMap<String,Object>`, `FileSystemResource`, and `HttpEntity<?>` for individual parts with their own headers.
- Understand how message converters pick a representation, auto-generate the multipart `boundary`, and parse JSON responses.
- Handle HTTP 4xx/5xx, network errors, timeouts, retries, idempotency, and payload sizes.
- Run a Spring Boot application with HTTP endpoints verifying all three cases and test using `RestClient`/JUnit.
- Know when to keep using `RestTemplate` and when the asynchronous `WebClient` is needed.

**Scope:** this is a **synchronous** HTTP client. The `RestClient` API looks like `WebClient` with fluent chaining, but it **does not** return `Mono`/`Flux` and does not automatically become non-blocking. If called from a Netty event loop in WebFlux while waiting on I/O, you can block the event loop; when high I/O throughput is required, choose WebClient/reactive downstream or offload blocking work to a bounded worker with resource limits.

## 2. Request Map: Where Does the Data Go?

Examine a hypothetical request:

```http
POST /orders/sku-42?region=vn&tag=urgent&tag=gift HTTP/1.1
Host: inventory.example.test
Accept: application/json
Content-Type: application/x-www-form-urlencoded

customer=Linh+An&note=C%2B%2B%20%26%20Java
```

Breakdown:

| Component | Example | Meaning |
| --- | --- | --- |
| URI path | `/orders/sku-42` | Identifies the resource; `sku-42` may come from `{id}` |
| Query string | `region=vn&tag=urgent&tag=gift` | Parameters in the URL, can repeat with the same name |
| `Accept` | `application/json` | Which representation the client wants to receive |
| `Content-Type` | `application/x-www-form-urlencoded` | Type of the **request body** being sent |
| Form field | `customer=Linh+An` | Form decoder interprets `+` as a space |
| Encoded form value | `note=C%2B%2B%20%26%20Java` | Literal `C++ & Java` after decoding |
| HTTP method | `POST` | Operation on the resource; does not replace specifying the body |

With **multipart**, the body is split into multiple parts with `Content-Disposition`, field name, optional filename, and per-part `Content-Type`. Multipart is not like a form-urlencoded string joined with `&`.

These locations require **different encoding tools**. A common mistake is using `URLEncoder` meant for HTML forms to construct an entire URI path, or manually appending `?`/`&` while forgetting to encode each component.

## 3. Synchronous HTTP Clients in Spring

According to Spring Framework documentation:

| API | Model | When Suitable |
| --- | --- | --- |
| `RestClient` | Synchronous, fluent API | New code on Spring Framework 6.1+ |
| `RestTemplate` | Synchronous, template methods | Existing applications, maintenance/integration |
| HTTP Service Client | Java interface with HTTP exchange annotations; backend can use RestClient | Wanting a declarative HTTP contract |
| `WebClient` | Non-blocking/reactive | Reactive I/O, many concurrent requests, async streaming |
| Java 11+ `HttpClient.send` | Synchronous JDK API without Spring dependency | Plain Java or needing to understand HTTP primitives |

The exercises use `RestClient` because it is the modern API in the Spring 6.x line and supports converters like `RestTemplate`. In Spring Framework 7.x, `RestTemplate` was marked deprecated, but **do not infer that all Spring 6.x applications must be rewritten immediately**; choose based on the actual version and system lifecycle.

### How Does Synchronous Differ from Reactive?

```text
Thread A: RestClient.get() ------ waiting I/O ------ response DTO
Thread B: WebClient.get() ------ returns Mono -------- subscription/callback

RestClient + Tomcat Servlet app: can be reasonable for short outbound HTTP calls.
RestClient on Netty WebFlux event loop: can cause blocking/starvation.
```

RestClient returns a DTO when the operation finishes (or throws an exception), not a Publisher you can hold before invoking. If the client times out, the remote server may still be processing the request; a timeout does not prove the operation did not commit.

## 4. Initializing RestClient for the Right Version

Maven dependencies for a Spring Boot 3.2+ application:

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-test</artifactId>
  <scope>test</scope>
</dependency>
```

This is a **dependencies snippet** to add to the `pom.xml` generated by Spring Initializr, **not** a standalone POM. `spring-boot-starter-web` provides Spring MVC to build the local demo server along with HTTP message converters/Jackson. The `spring-web` library contains `RestClient`; there is no need to add WebFlux just to use RestClient.

Minimal initialization:

```java
RestClient client = RestClient.create();
```

Or configured:

```java
RestClient client = RestClient.builder()
    .baseUrl("https://api.example.test")
    .defaultHeader("X-App", "learning")
    .build();
```

The `RestClient` class is `org.springframework.web.client.RestClient`. A client after `build()` can be shared across threads per Spring documentation; do **not** assume that makes mutable POJOs/request bodies thread-safe. Production projects should create a singleton Bean with configured base URL/timeouts/error policy instead of creating a new RestClient for each request.

### Simple HTTP GET Request

```java
ItemView item = client.get()
    .uri("/items/{id}", "SKU-42")
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .body(ItemView.class);
```

This is a **snippet** requiring a client and an `ItemView` record, not a standalone class. `.uri("/items/{id}", "SKU-42")` substitutes the placeholder with the URI variable per the encoding policy. `.retrieve().body(ItemView.class)` performs a synchronous HTTP exchange and uses a message converter to decode JSON; the method may return null if there is no suitable body, so do not call `item.id()` without null checks.

## 5. URI Templates: Do Not Mix Path Variables and Queries

A URI template has placeholders:

```text
https://api.example.test/items/{id}
https://api.example.test/items/{id}?locale={locale}
https://api.example.test/search?q={keyword}&page={page}
```

Placeholders are **not literal paths**. They are replaced with values so Spring can encode them according to the URI component. Example:

```java
String id = "SKU-42";

ItemView item = client.get()
    .uri("/items/{id}", id)
    .retrieve()
    .body(ItemView.class);
```

If the value comes from a user, do not concatenate:

```java
String unsafe = "/items/" + userSuppliedId;
```

This is an anti-pattern: an ID containing `?`, `#`, `/`, `%`, or spaces can alter the URI's meaning. Use template expansion and ID validation in the domain layer.

### Using Multiple Variables with a Map

```java
Map<String, Object> params = Map.of(
    "shop", "vn",
    "id", "SKU-42");

ItemView item = client.get()
    .uri("/shops/{shop}/items/{id}", params)
    .retrieve()
    .body(ItemView.class);
```

This is a snippet importing `java.util.Map`. Using a map avoids relying on positional argument order when a URI has multiple placeholders.

**Do not assume a URI variable containing a slash will be accepted by the server.** If an item ID contains `a/b`, template encoding may represent it as `a%2Fb`; many servers/gateways have policies blocking encoded slashes or decoding before routing. Design path-safe/opaque IDs and test through real ingress rather than trying to “work around” it with double encoding.

## 6. Query Parameters with UriBuilder Instead of String Concatenation

When you need a URI like:

```text
GET /search?q=C%2B%2B%20%26%20Java&page=2&tag=java&tag=spring%20web
```

Do not write manually:

```java
String url = "/search?q=" + keyword + "&tag=" + tag;
```

If `keyword="C++ & Java"`, literal `+`/`&` can be interpreted differently by decoders/query parsers. Use a URI builder and **URI variables** when strict encoding is needed.

```java
SearchResult result = client.get()
    .uri(b -> b.path("/search")
        .queryParam("q", "{q}")
        .queryParam("page", 2)
        .queryParam("tag", "{tag1}", "{tag2}")
        .build(Map.of(
            "q", "C++ & Java",
            "tag1", "java",
            "tag2", "spring web")))
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .body(SearchResult.class);
```

This is a snippet with an application-defined `SearchResult`. `queryParam("tag", ...)` can add repeated parameter values, while `UriBuilder.build(Map)` expands URI variables.

**Encoding key point:** use `DefaultUriBuilderFactory` with an appropriate mode, typically `TEMPLATE_AND_VALUES` (template variable values are strictly encoded). If the project substitutes a custom `UriBuilderFactory` or passes a pre-built `URI`, encoding rules may differ. When queries contain `+`, percent escapes, or reserved characters, test **the actual URI sent on the wire** instead of guessing from Java strings.

## 7. Configuring URI Builder Encoding Explicitly

`DefaultUriBuilderFactory` is the factory Spring uses to build URI builders. Defaults since Spring 5.1 shifted toward `TEMPLATE_AND_VALUES`, but explicit configuration makes code less dependent on altered client defaults.

```java
DefaultUriBuilderFactory factory =
    new DefaultUriBuilderFactory("https://api.example.test");

factory.setEncodingMode(
    DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

RestClient client = RestClient.builder()
    .uriBuilderFactory(factory)
    .build();
```

Imports:

```java
import org.springframework.web.util.DefaultUriBuilderFactory;
import org.springframework.web.client.RestClient;
```

This is a snippet in config/test with Spring on the classpath. With `TEMPLATE_AND_VALUES`, the template is processed and **variable values** are encoded as data, keeping `C++ & Java` from breaking delimiters. In the runnable app example below, we use this exact configuration.

### Empty, Missing, and Multi-Value Query Parameters

```text
/search                  q is absent
/search?q=               q is present, empty value
/search?q=one&q=two      q repeated twice
/search?q=a%2Bb          q is literal "a+b" when decoded
```

The API must clearly define **missing** vs **empty string** and repeated values. For `page`, `-1` parses as a number but may violate the domain range; validation is a separate server step.

### Optional Query Values

If a query parameter is optional, only call `queryParamIfPresent(...)` with an `Optional`, or add the parameter conditionally inside the builder lambda. **Never** send the string `"null"` just because a Java variable is null; in Spring, `queryParam("q", null)` may also produce a valueless parameter depending on the API. Every API should define absent vs empty clearly.

## 8. Encoding URIs: Percent Encoding vs Form Encoding Differ

Multiple representations exist:

| Input Value | In URI Query Variable (e.g., Strict Encoding) | In Form-Urlencoded |
| --- | --- | --- |
| `A B` | `A%20B` | `A+B` |
| `C++` | `C%2B%2B` | `C%2B%2B` |
| `a&b` | `a%26b` | `a%26b` |
| `x=y` | `x%3Dy` | `x%3Dy` |
| `a/b` | `a%2Fb` when strict variable | `a%2Fb` |
| `100%` | `100%25` | `100%25` |

This table illustrates **values** under strict encoding, not a promise that every HTTP client/version produces the exact same bytes if configured differently. `%20` and `+` can both represent a space when decoding a form, but **in URI queries many parsers do not treat them as completely equivalent**. A literal `+` sign is very easily lost if the client fails to encode properly when the server parses queries using form conventions.

### Why Not Use URLEncoder for URI Paths?

`java.net.URLEncoder` encodes according to **application/x-www-form-urlencoded**, meaning **space → +**. In a path, `+` can be a literal plus sign rather than a space. Therefore, do not take `URLEncoder.encode(id)` and concatenate it into a path. Use `UriBuilder`, `UriComponentsBuilder`, or context-appropriate URI template expansion.

### Do Not Double-Encode

If the original value is `"a/b"`, the encoder can send `a%2Fb`. If you pass the **already-encoded string** `"a%2Fb"` into the client as unencoded data, a second encode pass can produce `a%252Fb`. The server receives literal `a%2Fb` after one decode, not a slash. Rule: **keep values unencoded in the business layer; encode once at the HTTP boundary**. If you already have a properly built/encoded `URI`, pass `uri(URI)` and do not feed it back into a template expander.

## 9. Building a Complete URI with UriComponentsBuilder

Sometimes the same URI is used for both RestClient and RestTemplate. `UriComponentsBuilder` helps build a complete `java.net.URI`:

```java
URI uri = UriComponentsBuilder
    .fromUriString("https://api.example.test")
    .path("/items/{id}")
    .queryParam("q", "{q}")
    .queryParam("page", 2)
    .encode()
    .buildAndExpand(Map.of(
        "id", "SKU-42",
        "q", "C++ & Java"))
    .toUri();

ItemView item = client.get()
    .uri(uri)
    .retrieve()
    .body(ItemView.class);
```

This snippet requires imports `java.net.URI`, `java.util.Map`, `org.springframework.web.util.UriComponentsBuilder`. Calling `encode()` **before** `buildAndExpand` ensures URI variables are strictly encoded per the builder contract; literal template special characters have different semantics from variable values.

**Important:** `RestClient.uri(URI)` uses the already-built URI; it does not re-encode like `uri(String, variables)`. If a protocol/API requires a specific query parameter order for request signing, do not rely on an unordered Map; construct the canonical request per the service's signing specification, including explicit ordering and escaping.

## 10. GET Parameters Differ from POST Form Body

The following HTTP request pair is **not the same**:

```http
GET /search?name=Linh+An HTTP/1.1
Host: example.test

POST /form HTTP/1.1
Host: example.test
Content-Type: application/x-www-form-urlencoded

name=Linh+An
```

`GET` queries live in the URI; `POST` form fields live in the **body**. The same server might accept both query and form via `@RequestParam` when running **Spring MVC/Servlet**, but do not build a client assuming form-urlencoded is a query string.

Form bodies are typically built with `MultiValueMap<String,String>`:

```java
MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
form.add("name", "Linh & An");
form.add("tag", "java");
form.add("tag", "C++");
```

`MultiValueMap` holds multiple values for the same key; a plain `Map<String,String>` cannot express `tag` appearing twice. This is also a safe way to avoid manual body string concatenation.

## 11. POST application/x-www-form-urlencoded with RestClient

```java
MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
form.add("name", "Linh & An");
form.add("tag", "java");
form.add("tag", "C++");

FormReply reply = client.post()
    .uri("/form")
    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
    .accept(MediaType.APPLICATION_JSON)
    .body(form)
    .retrieve()
    .body(FormReply.class);
```

This is a snippet requiring a client and a `FormReply` record. With standard Spring Web message converters configured, `FormHttpMessageConverter` serializes the fields into a **form-urlencoded body**, percent-encodes values, sets the appropriate Content-Type, and sends a synchronous POST.

Illustrative wire body **conceptually**:

```text
name=Linh+%26+An&tag=java&tag=C%2B%2B
```

Key order, charset/encoding, and headers depend on the converter/configuration; use an integration test to guarantee the contract. Do not construct concatenated strings by hand in business logic.

### Content-Type and Accept Are Different

- `.contentType(APPLICATION_FORM_URLENCODED)`: the client **is sending a form**.
- `.accept(APPLICATION_JSON)`: the client **wants to receive JSON**.
- `.body(form)`: the value to be encoded by the form writer.
- `.retrieve().body(FormReply.class)`: decodes the JSON response into a record.

If you send a form map while setting Content-Type to `application/json`, the server may not receive the expected form and return 400/415. Conversely, a JSON DTO body does not automatically become a form just by calling `.post()`.

## 12. Message Converter Selection for Form and Multipart

Spring HTTP message conversion chooses a writer based on the **Java body type** and **Content-Type**.

| Java Body | Intended Content-Type | Typically Suitable Converter |
| --- | --- | --- |
| `MultiValueMap<String,String>` | `application/x-www-form-urlencoded` | `FormHttpMessageConverter` |
| `MultiValueMap<String,Object>` containing Resource/HttpEntity | `multipart/form-data` | `FormHttpMessageConverter` / `AllEncompassingFormHttpMessageConverter` |
| Java record DTO | `application/json` | `MappingJackson2HttpMessageConverter` |
| `String` | `text/plain` | `StringHttpMessageConverter` |
| `byte[]` | `application/octet-stream` | `ByteArrayHttpMessageConverter` |
| `Resource` | streams binary content per converter | `ResourceHttpMessageConverter` |

The Spring Framework reference allows multipart parts to be `Object`, `Resource`, or `HttpEntity<?>` with their own headers. Spring automatically chooses a part converter based on content and headers.

**Note:** When `MultiValueMap` contains at least one **non-String** part, the converter may infer multipart; if it contains only Strings, the default is typically form-urlencoded. To keep intent clear, **explicitly set the desired `Content-Type`**, especially when you want multipart with only text fields. Never assume the response's `Content-Type` matches the request's.

### Can Multipart Contain Only Text?

Yes. A client can send multipart where all parts are text. Because that is still a multipart representation, set `MediaType.MULTIPART_FORM_DATA` explicitly or ensure the converter classifies it correctly. If there are no files and the endpoint only needs a few fields, form-urlencoded is usually simpler and lighter.

## 13. What Is Multipart?

HTTP multipart/form-data consists of parts separated by a **boundary** specified in the header.

```http
POST /upload HTTP/1.1
Host: example.test
Content-Type: multipart/form-data; boundary=someUniqueBoundary

--someUniqueBoundary
Content-Disposition: form-data; name="description"

Demo document
--someUniqueBoundary
Content-Disposition: form-data; name="file"; filename="sample.txt"
Content-Type: text/plain

hello
--someUniqueBoundary--
```

This illustrates the structure of an HTTP payload; **do not hand-write it** when using Spring RestClient. Spring's multipart converter generates an appropriate boundary, writes each part, and writes the closing marker.

A multipart request can contain:
- Text field `description`.
- File `file` from `Resource`.
- JSON metadata `meta` encoded by Jackson.
- Other parts with their own media types and headers.

Do not confuse the overall multipart `Content-Type` with an individual part's `Content-Type`. A `multipart/form-data` request can contain `application/json` on the `meta` part.

## 14. Building Multipart with MultiValueMap<String,Object>

```java
MultiValueMap<String, Object> parts =
    new LinkedMultiValueMap<>();

parts.add("description", "Demo document");
parts.add("file",
    new FileSystemResource(Path.of("sample.txt")));

UploadReply reply = client.post()
    .uri("/upload")
    .contentType(MediaType.MULTIPART_FORM_DATA)
    .accept(MediaType.APPLICATION_JSON)
    .body(parts)
    .retrieve()
    .body(UploadReply.class);
```

This is a snippet inside a method that already has a client and an existing `sample.txt`. Imports `org.springframework.core.io.FileSystemResource`, `org.springframework.util.MultiValueMap`, `LinkedMultiValueMap`, `java.nio.file.Path`.

- `"description"` is a plain form part.
- `"file"` uses FileSystemResource; the converter can obtain the filename and read the file content.
- `contentType(MULTIPART_FORM_DATA)` declares the entire request as multipart.
- Do **not** manually set the boundary in the header; the converter is responsible for it.
- The `parts` body is processed synchronously; the request factory implementation may buffer or stream depending on configuration. Do not claim every client streams files with O(1) memory by default.

### Why Use FileSystemResource Instead of byte[]?

`FileSystemResource` provides the filename, path, and stream content via the Resource API, fitting a file already on disk. If you use raw `byte[]`, the converter will not always treat it as **a file with a filename** as desired. If the API requires a filename, use a Resource with a proper `getFilename()` or wrap the part in `HttpEntity<Resource>` with the appropriate Content-Disposition.

## 15. JSON Part and HttpEntity with Per-Part Headers

A multipart request can include JSON metadata:

```java
record Meta(String source) {}

HttpHeaders jsonHeaders = new HttpHeaders();
jsonHeaders.setContentType(MediaType.APPLICATION_JSON);

HttpEntity<Meta> jsonPart =
    new HttpEntity<>(new Meta("draft"), jsonHeaders);

MultiValueMap<String, Object> parts =
    new LinkedMultiValueMap<>();

parts.add("description", "Demo document");
parts.add("file",
    new FileSystemResource(Path.of("sample.txt")));
parts.add("meta", jsonPart);

UploadReply reply = client.post()
    .uri("/upload")
    .contentType(MediaType.MULTIPART_FORM_DATA)
    .body(parts)
    .retrieve()
    .body(UploadReply.class);
```

This is a **snippet**: `Meta` record/`UploadReply` must match the server contract. `HttpEntity` wraps **part content + part headers**, not a new HTTP request. The JSON part has `Content-Type: application/json`, encoded by the Jackson converter when the corresponding dependency is present. The file part remains FileSystemResource.

**Do not use `HttpEntity` to replace top-level request headers.** Top-level RestClient `.contentType(...)`/`.accept(...)` belong to the HTTP request; part HttpEntity headers apply only to that part. If the service expects the part name to be `metadata` instead of `meta`, they must match exactly.

## 16. ByteArrayResource and the Filename Issue

Sometimes the file resides in memory (e.g., a small previously generated report):

```java
byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);

Resource resource = new ByteArrayResource(bytes) {
    @Override
    public String getFilename() {
        return "report.txt";
    }
};

MultiValueMap<String, Object> parts =
    new LinkedMultiValueMap<>();
parts.add("file", resource);
```

This is a snippet importing `java.nio.charset.StandardCharsets`, `org.springframework.core.io.ByteArrayResource`, `Resource`.

`ByteArrayResource` may have **no filename** by default; many servers require `Content-Disposition: form-data; name="file"; filename="..."` to bind to a file part. Override `getFilename()` when the contract requires a filename.

**Memory caution:** `ByteArrayResource` holds all bytes in heap; it is unsuitable for multi-GB uploads. `InputStreamResource` is not an unconditional replacement either: it is typically non-repeatable, its filename can be null, and some converters/request factories need content length or body replay. Choose `FileSystemResource` for real files or a tested streaming adapter for large file uploads.

## 17. Form and Multipart Differ from JSON Bodies

A common mistake:

```java
client.post()
    .uri("/upload")
    .contentType(MediaType.APPLICATION_JSON)
    .body(parts);
```

This is an **anti-pattern** if `parts` is a `MultiValueMap<String,Object>` intended for multipart. The JSON converter will not generate `Content-Disposition` or boundaries for files.

Distinguish:

| Need to Send | Content-Type | Java Request Body |
| --- | --- | --- |
| JSON DTO | `application/json` | `new CreateOrder(...)` |
| Simple form fields | `application/x-www-form-urlencoded` | `MultiValueMap<String,String>` |
| File + text + JSON parts | `multipart/form-data` | `MultiValueMap<String,Object>` |
| Single non-multipart binary | `application/octet-stream` | `byte[]`/`Resource` per writer |
| Query filters | Located in URL | `UriBuilder.queryParam(...)`, no body needed |

A Spring MVC server can use `@RequestParam` to read form fields or `@RequestPart` for multipart JSON/file parts. A Spring WebFlux server has its own form/multipart body APIs. The RestClient client is only responsible for emitting the HTTP payload per contract; the server framework could be Java, Node, Python, or another system.

## 18. Quick Comparison: RestClient, RestTemplate, and JDK HttpClient

### RestClient (Spring 6.1+)

```java
Book book = client.get()
    .uri("/books/{id}", id)
    .retrieve()
    .body(Book.class);
```

### RestTemplate (For Compatibility)

```java
RestTemplate restTemplate = new RestTemplate();

Book book = restTemplate.getForObject(
    "https://api.example.test/books/{id}",
    Book.class, id);
```

### Java 17 HttpClient (Without Spring Converters)

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.test/books/42"))
    .GET().build();

HttpResponse<String> response =
    HttpClient.newHttpClient().send(
        request, HttpResponse.BodyHandlers.ofString());
```

These are **snippets** requiring a `Book` record/`id` or the corresponding Java HTTP imports. `HttpClient.send` is synchronous; to deserialize a JSON DTO, you must use a JSON parser (such as Jackson) yourself and manually build multipart/form encoding without Spring converters. A standalone runnable Java 17 sample without external networking appears in a later section.

## 19. How Does RestTemplate Send Form and Multipart?

RestTemplate still uses `HttpMessageConverter` in the Spring 6.x line.

### Form-urlencoded

```java
MultiValueMap<String, String> form =
    new LinkedMultiValueMap<>();
form.add("name", "Linh");
form.add("tag", "java");
form.add("tag", "C++");

HttpHeaders headers = new HttpHeaders();
headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);

HttpEntity<MultiValueMap<String, String>> entity =
    new HttpEntity<>(form, headers);

FormReply reply = restTemplate.postForObject(
    "https://api.example.test/form",
    entity, FormReply.class);
```

### Multipart

```java
MultiValueMap<String, Object> parts =
    new LinkedMultiValueMap<>();
parts.add("description", "Demo document");
parts.add("file",
    new FileSystemResource(Path.of("sample.txt")));

HttpHeaders headers = new HttpHeaders();
headers.setContentType(MediaType.MULTIPART_FORM_DATA);

HttpEntity<MultiValueMap<String, Object>> entity =
    new HttpEntity<>(parts, headers);

UploadReply reply = restTemplate.postForObject(
    "https://api.example.test/upload",
    entity, UploadReply.class);
```

These two snippets require `RestTemplate restTemplate`, response records, and imports. RestTemplate uses a top-level request `HttpEntity`, whereas RestClient separates `.headers(...)` and `.body(...)`. Do not take a `RequestEntity`/`HttpEntity` from RestTemplate, pass it into RestClient.body, and expect RestClient to interpret top-level headers the same way.

### API Comparison

| Task | RestTemplate | RestClient |
| --- | --- | --- |
| GET URI template | `getForObject(url,Dto.class,vars)` | `get().uri(url,vars).retrieve().body(Dto.class)` |
| GET ResponseEntity | `getForEntity(...)` | `retrieve().toEntity(Dto.class)` |
| POST form/multipart | `postForObject(url,HttpEntity,Dto.class)` | `post().contentType(...).body(map).retrieve().body(Dto.class)` |
| Set request headers | `HttpEntity`/`RequestEntity` | `header/headers/accept/contentType` |
| Customize per response status | `ResponseErrorHandler` | `onStatus(...)` |
| Underlying HTTP transport | `ClientHttpRequestFactory` | `ClientHttpRequestFactory` |
| Async response publisher | No | No |

**Do not mix MVC server object types** (`MultipartFile` representing an already-received upload) with client upload files (`Resource`). `MultipartFile` can appear in HTTP service interface client APIs, but for manual RestClient multipart bodies, use Resource/HttpEntity explicitly.

## 20. Handling HTTP Responses, Errors, and Null Bodies

RestClient `retrieve()` provides response metadata/body:

```java
ResponseEntity<ItemView> result = client.get()
    .uri("/items/{id}", "SKU-42")
    .retrieve()
    .toEntity(ItemView.class);

int status = result.getStatusCode().value();
ItemView body = result.getBody();
```

This is a snippet. `getStatusCode()` is `HttpStatusCode`; do not assume it is always the `HttpStatus` enum. `getBody()` can be null for bodyless responses.

By default `retrieve()` can throw `RestClientResponseException`/subclasses when the server returns 4xx or 5xx; other transport/converter errors can also be `RestClientException`. Do not assume every exception has an HTTP status: **connect timeout, DNS failure, TLS handshake** have no HTTP response from the server to read.

### Custom Status Handling

```java
ItemView item = client.get()
    .uri("/items/{id}", "SKU-42")
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        (request, response) -> {
            throw new IllegalStateException(
                "Remote item not found");
        })
    .body(ItemView.class);
```

This is a snippet showing one customization approach, not the sole policy. Do not swallow every 404 into `null` and treat it as success if the API must distinguish not-found from upstream outage. For 401/403, check credentials and permissions; for 429/503, backoff may be needed; for format errors, inspect bounded bodies and sanitize before logging.

### Timeouts and Status Codes Are Not the Same

An HTTP 504 returned by a gateway is a **response** (with a status). A client connect/read timeout is typically an **exception with no HTTP response**. The same POST request may already have been processed by the remote service even if the client timed out waiting for the reply.

## 21. Timeouts and ClientHttpRequestFactory

For synchronous clients, you must think about timeouts and connection pools. An example with Spring's standard request factory:

```java
SimpleClientHttpRequestFactory requestFactory =
    new SimpleClientHttpRequestFactory();

requestFactory.setConnectTimeout(3000);
requestFactory.setReadTimeout(5000);

RestClient client = RestClient.builder()
    .requestFactory(requestFactory)
    .baseUrl("https://api.example.test")
    .build();
```

This snippet requires importing `org.springframework.http.client.SimpleClientHttpRequestFactory`. The two values here are in **milliseconds** in the Spring 6.x API. Connect timeout bounds the connection step, read timeout is the wait time for read operations per transport; **they are not a total deadline for all DNS/TLS/upload/retry/response steps**.

Production may use Apache HttpComponents/Jetty/JDK client request factories depending on dependencies, connection pooling, and proxy/TLS needs. When switching transport, read how to configure that library's own pool/connection-request timeouts. Do not simply raise the timeout to 10 minutes to hide a slow upstream.

### Concurrent Load Limits

If 200 server request threads simultaneously call RestClient and wait 5 seconds, all 200 can be occupied. You need to:
- Measure p95/p99 outbound latency.
- Use bounded connection pools; avoid creating a client/connection pool per request.
- Apply bulkheads/concurrency quotas for downstreams prone to overload.
- Configure timeouts, retries with backoff/jitter, and circuit breakers per business needs.
- Set limits on file uploads, response sizes, and streaming readers.
- Track overall deadlines from caller/gateway to downstreams.

Do not cause a retry storm by retrying a saturated 503 endpoint all at once.

## 22. Retries, Idempotency, and Data Protection

URI/query GETs are usually safe to retry under HTTP semantics if the endpoint implements GET properly (does not mutate server state). A POST sending a form/multipart may create an order, upload, or payment, so **retries must not be enabled blindly**.

Scenarios:

| Scenario | Can Retry? | Notes |
| --- | --- | --- |
| Connect failure before sending HTTP | Possibly, if assessed safe | Still verify the request truly never reached the server |
| GET timeout | Often considered | Only if GET has no significant side effects |
| POST timeout after uploading bytes | **Dangerous** | Server may already have saved the file/committed |
| POST 409 conflict | Do not auto-retry | Requires domain conflict resolution |
| 429/503 | Per Retry-After/backoff if appropriate | Rate limit and server capacity |
| Multipart from non-repeatable InputStreamResource | Retry may be impossible | Body stream may already be consumed |
| Multipart from FileSystemResource | Can reopen file, but operation still has side effects | Use an idempotency key if needed |

An **idempotency key** must be supported by the server, persisted durably, and tied to actor/request semantics. An arbitrary header does not prevent duplicate uploads if the server ignores it. For large uploads, consider a resumable upload protocol or presigned URLs instead of long-running synchronous multipart POSTs.

### Data Security

- Never log raw Authorization, Cookie, API keys, form passwords, or binary multipart content.
- Never return raw error responses containing PII/tokens to clients.
- Never let clients specify arbitrary URLs if the backend calls RestClient on that URL (SSRF).
- Block unexpected redirects to internal networks per request factory/policy.
- Pin base hosts, allowlist schemes/hosts/ports, and never mix user-supplied raw URIs with trusted base URLs.
- Verify TLS certificates/hostnames; never disable SSL verification to “fix” errors.
- Validate filenames/paths and sizes before sending; filenames received from remote services remain untrusted metadata.
- Never send credentials to another host via uncontrolled redirects.
- Respect rate limits and authorization.

## 23. Runnable Spring Boot 3.2+ Exercise (Server + RestClient)

To verify end-to-end, create **a small Spring MVC application acting as the receiving server** and an integration test using `RestClient` as the **synchronous client** sending requests to localhost. This approach does not depend on public APIs, requires no tokens, and avoids mocking the entire multipart flow.

Maven/Gradle requirements:

- Java 17+.
- Spring Boot **3.2+** in the 3.x line.
- `spring-boot-starter-web`.
- `spring-boot-starter-test` (test scope).

Starting from Spring Initializr with the Maven wrapper, create the files:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  DemoController.java
src/test/java/com/example/demo/
  RestClientIntegrationTest.java
```

All three files share the package `com.example.demo`. The demo needs no database or Spring Security; it simply echoes back the parsed values to observe URI/query/form/multipart behavior.

### 23.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 23.2. DemoController.java

```java
package com.example.demo;

import java.io.IOException;
import java.util.List;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/demo")
public class DemoController {

    @GetMapping(path = "/items/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public ItemReply item(
            @PathVariable String id,
            @RequestParam String q,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(name = "tag", required = false)
                    List<String> tags) {

        return new ItemReply(id, q, page,
                tags == null ? List.of() : List.copyOf(tags));
    }

    @PostMapping(path = "/form",
                 consumes =
                   MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public FormReply form(
            @RequestParam String name,
            @RequestParam("tag") List<String> tags) {

        return new FormReply(name, List.copyOf(tags));
    }

    @PostMapping(path = "/upload",
                 consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public UploadReply upload(
            @RequestParam String description,
            @RequestPart("file") MultipartFile file,
            @RequestPart("meta") Meta meta) throws IOException {

        // Only read metadata and length, DO NOT save demo file.
        return new UploadReply(
            description,
            file.getOriginalFilename(),
            file.getSize(),
            meta.source());
    }

    public record ItemReply(
        String id, String q, int page, List<String> tags) {}

    public record FormReply(
        String name, List<String> tags) {}

    public record Meta(String source) {}

    public record UploadReply(
        String description, String filename,
        long size, String source) {}
}
```

**Explanation**: The MVC controller receives `@RequestParam` from query (GET) or form-urlencoded body (POST). `@RequestPart("file") MultipartFile` represents the file received on the server; the client sends `FileSystemResource`. `@RequestPart("meta") Meta` decodes the JSON part via Jackson thanks to the part's own `Content-Type: application/json`.

The code reads size from MultipartFile without saving the file. The demo uses `throws IOException` even though the method does not currently read the file stream: the declaration can be omitted if unneeded; Java permits redundant checked exception declarations. Production needs file size limits, filename validation, virus scanning, storage permissions, and proper stream processing.

## 24. RestClientIntegrationTest: URI Template, Query, Form, and Multipart

File `src/test/java/com/example/demo/RestClientIntegrationTest.java`:

```java
package com.example.demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.DefaultUriBuilderFactory;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class RestClientIntegrationTest {

    @LocalServerPort
    int port;

    private RestClient client() {
        DefaultUriBuilderFactory factory =
            new DefaultUriBuilderFactory(
                "http://localhost:" + port);

        factory.setEncodingMode(
            DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

        return RestClient.builder()
            .uriBuilderFactory(factory)
            .build();
    }

    @Test
    void uriTemplateAndRepeatedQueryValues() {
        DemoController.ItemReply result = client().get()
            .uri(builder -> builder
                .path("/demo/items/{id}")
                .queryParam("q", "{q}")
                .queryParam("page", 2)
                .queryParam("tag", "{tag1}", "{tag2}")
                .build(Map.of(
                    "id", "SKU-42",
                    "q", "C++ & Java",
                    "tag1", "java",
                    "tag2", "spring web")))
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(DemoController.ItemReply.class);

        assertNotNull(result);
        assertEquals("SKU-42", result.id());
        assertEquals("C++ & Java", result.q());
        assertEquals(2, result.page());
        assertEquals(
            java.util.List.of("java", "spring web"),
            result.tags());
    }

    @Test
    void postsFormUrlencoded() {
        MultiValueMap<String, String> form =
            new LinkedMultiValueMap<>();
        form.add("name", "Linh & An");
        form.add("tag", "java");
        form.add("tag", "C++");

        DemoController.FormReply reply = client().post()
            .uri("/demo/form")
            .contentType(
                MediaType.APPLICATION_FORM_URLENCODED)
            .accept(MediaType.APPLICATION_JSON)
            .body(form)
            .retrieve()
            .body(DemoController.FormReply.class);

        assertNotNull(reply);
        assertEquals("Linh & An", reply.name());
        assertEquals(
            java.util.List.of("java", "C++"),
            reply.tags());
    }

    @Test
    void postsMultipartWithTextFileAndJsonPart(
            @TempDir Path tempDir) throws IOException {

        Path file = tempDir.resolve("sample.txt");
        Files.writeString(
            file, "hello", StandardCharsets.UTF_8);

        HttpHeaders jsonHeaders = new HttpHeaders();
        jsonHeaders.setContentType(
            MediaType.APPLICATION_JSON);

        HttpEntity<DemoController.Meta> metadata =
            new HttpEntity<>(
                new DemoController.Meta("draft"),
                jsonHeaders);

        MultiValueMap<String, Object> parts =
            new LinkedMultiValueMap<>();
        parts.add("description", "Demo document");
        parts.add("file", new FileSystemResource(file));
        parts.add("meta", metadata);

        DemoController.UploadReply reply = client().post()
            .uri("/demo/upload")
            .contentType(MediaType.MULTIPART_FORM_DATA)
            .accept(MediaType.APPLICATION_JSON)
            .body(parts)
            .retrieve()
            .body(DemoController.UploadReply.class);

        assertNotNull(reply);
        assertEquals("Demo document",
                     reply.description());
        assertEquals("sample.txt", reply.filename());
        assertEquals(5L, reply.size());
        assertEquals("draft", reply.source());
    }
}
```

**This is a complete Java test for a Boot 3.2+ project with the right dependencies**, not test output already executed in the user's repository. The test does not use a mock request builder; it starts a real local HTTP server on RANDOM_PORT, simultaneously verifying URL encoding, form converter, multipart boundary/part headers, and server parsing.

`DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES` is a deliberate choice so `C++ & Java` and `spring web` are encoded as **variable values**. The test checks the decoded data on the server rather than relying on assumptions about URL string formatting.

### Running Tests

macOS/Linux:

```bash
./mvnw test
```

Windows PowerShell:

```powershell
.\mvnw.cmd test
```

If running the app first:

```bash
./mvnw spring-boot:run
```

By default when run standalone, the server listens on `http://localhost:8080` unless the port is changed. Tests use **RANDOM_PORT**, so do not hardcode :8080 inside tests.

### Expected Results

| Test | Status and Content |
| --- | --- |
| `uriTemplateAndRepeatedQueryValues` | 200, ID SKU-42, literal q `C++ & Java`, page 2, 2 tags |
| `postsFormUrlencoded` | 200, name `Linh & An`, tags `java`, `C++` |
| `postsMultipartWithTextFileAndJsonPart` | 200, filename sample.txt, file size 5, source draft |

The test assertions check domain data, not JSON property order, auto-generated multipart boundaries, or header casing.

## 25. Comparing Requests with Curl

After starting `DemoApplication` on port 8080, you can compare the HTTP requests with curl. If the base port was changed, update the URI accordingly.

### GET URI/Query

```bash
curl -i --get 'http://localhost:8080/demo/items/SKU-42' \
  --data-urlencode 'q=C++ & Java' \
  --data-urlencode 'page=2' \
  --data-urlencode 'tag=java' \
  --data-urlencode 'tag=spring web' \
  -H 'Accept: application/json'
```

`curl --get --data-urlencode` builds the query so you do not have to manually encode `+`/`&`. Sample JSON response:

```json
{
  "id": "SKU-42",
  "q": "C++ & Java",
  "page": 2,
  "tags": ["java", "spring web"]
}
```

### Form-Urlencoded

```bash
curl -i -X POST 'http://localhost:8080/demo/form' \
  --data-urlencode 'name=Linh & An' \
  --data-urlencode 'tag=java' \
  --data-urlencode 'tag=C++' \
  -H 'Accept: application/json'
```

`curl --data-urlencode` sends a form body with the appropriate form Content-Type. Response:

```json
{"name":"Linh & An","tags":["java","C++"]}
```

### Multipart (File + JSON Part)

Create `sample.txt` containing the five bytes `hello` with no trailing newline, then run:

```bash
curl -i -X POST 'http://localhost:8080/demo/upload' \
  -F 'description=Demo document' \
  -F 'file=@sample.txt;type=text/plain' \
  -F 'meta={"source":"draft"};type=application/json' \
  -H 'Accept: application/json'
```

Expected:

```json
{
  "description": "Demo document",
  "filename": "sample.txt",
  "size": 5,
  "source": "draft"
}
```

**Key point:** both `curl -F` and Spring's multipart converter manage the boundary automatically. Do not manually add `Content-Type: multipart/form-data` without a boundary when using curl or Spring; doing so easily prevents the server from parsing the parts.

## 26. Testing Request Generation Without a Real Network

When you only want to verify request method/URI/headers/body converter, Spring Test provides `MockRestServiceServer` to bind to `RestClient.Builder`.

Simple GET test example:

```java
RestClient.Builder builder = RestClient.builder()
    .baseUrl("https://api.example.test");

MockRestServiceServer server =
    MockRestServiceServer.bindTo(builder).build();

RestClient client = builder.build();

server.expect(requestTo(
        "https://api.example.test/items/SKU-42"))
    .andExpect(method(HttpMethod.GET))
    .andRespond(withSuccess(
        "{\"id\":\"SKU-42\"}",
        MediaType.APPLICATION_JSON));

ItemView response = client.get()
    .uri("/items/{id}", "SKU-42")
    .retrieve()
    .body(ItemView.class);

server.verify();
```

This is a **snippet inside a JUnit test method**, requiring `ItemView`, `HttpMethod`, `MediaType`, and static imports:

```java
import static org.springframework.test.web.client.match
    .MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match
    .MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response
    .MockRestResponseCreators.withSuccess;
```

**Note:** the imports above are line-wrapped in invalid Java syntax if copied verbatim; write them on single complete lines such as `import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;` in an actual file. The wrapped lines are only to show the namespaces, not a runnable file.

`MockRestServiceServer` is useful for testing client logic without network dependencies, but **does not replace** an HTTP integration test against a real server for multipart parsing, filenames, charsets, proxies, TLS, redirects, and large uploads. Tests should recognize that a form-urlencoded request body is a byte sequence while a multipart body has a dynamic boundary; do not hardcode a boundary literal in assertions.

## 27. Standalone Java 17: Form Encoding and URIs Differ

This is **a single JDK 17 file that compiles/runs without Spring dependencies**, demonstrating how `URLEncoder` produces a form-urlencoded representation.

File `FormEncodingDemo.java`:

```java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public class FormEncodingDemo {

    private static String encode(String value) {
        return URLEncoder.encode(
            value, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) {
        String name = "Linh & An";
        String tag = "C++";

        String body = "name=" + encode(name)
            + "&tag=" + encode(tag);

        System.out.println(body);
        System.out.println(
            "Do not use form encoding for URI path");
    }
}
```

Run:

```bash
javac FormEncodingDemo.java
java FormEncodingDemo
```

**Exact** stdout:

```text
name=Linh+%26+An&tag=C%2B%2B
Do not use form encoding for URI path
```

This is an educational illustration of form encoding; when using Spring RestClient, pass a `MultiValueMap` to the converter instead of concatenating fields manually. This plain JDK program sends no requests: a real sync HTTP example is already in the Spring Boot integration test.

### Why Import URLEncoder Only to Avoid Using It for Paths?

In a form body, spaces are encoded as `+` per form convention. URI paths need dedicated slash/path-segment handling; if `URLEncoder` is used directly, values containing spaces may not be interpreted by the server as intended. Spring's URI template builder has the right mechanism for path/query variables.

## 28. Advanced Scenario: Uploading Metadata and Filenames

Servers sometimes require this multipart structure:

```http
POST /upload HTTP/1.1
Content-Type: multipart/form-data; boundary=...

--...
Content-Disposition: form-data; name="meta"
Content-Type: application/json

{"source":"draft"}
--...
Content-Disposition: form-data; name="file"; filename="report.txt"
Content-Type: text/plain

hello
--...--
```

Several API contract details must be verified:

1. Part names must match: `file` differs from `upload`.
2. Text fields and JSON parts differ: `description` accepts a String, `meta` accepts a DTO.
3. Each part's `Content-Type` must be right for the server decoder to pick the converter.
4. Filename is provided by FileSystemResource/Resource#getFilename; for in-memory resources an override may be needed.
5. Request boundaries must not be hardcoded to the same value across clients.
6. File bytes can contain arbitrary binary data; do not convert them through `String`/UTF-8 and concatenate boundaries manually.
7. Never use raw user-supplied paths as client filesystem paths without an allowlist/authorization.
8. If files are large, check whether the HTTP transport can stream and verify retry/body repeatability policies.
9. Partial success followed by a timeout does not mean the remote service rolled back the file.
10. multipart/mixed and multipart/form-data are not interchangeable if the server contract distinguishes them.

### Choosing a Resource

| Resource | Source | Caveats |
| --- | --- | --- |
| `FileSystemResource` | File on disk | File may change between check and send; check permissions/size |
| `ByteArrayResource` | byte[] in memory | No default filename, retains all bytes in memory |
| `InputStreamResource` | Already-open InputStream | Non-repeatable; may lack filename/size and complicate retries |
| `UrlResource` | Remote URL | Never use arbitrary user-supplied URLs; SSRF and unintended fetches |
| `ClassPathResource` | Resource on classpath | Suitable for small fixtures; filename/stream metadata varies |

In production, guard file opening time, data ownership, size limits, and create temp files in a secure directory. Do not keep an `InputStream` open across multiple requests or threads without lifecycle management.

## 29. HTTP Statuses on Malformed Requests

Common errors:

| Status/Exception | Why It Occurs |
| --- | --- |
| 400 Bad Request | Missing form field, wrong type conversion, malformed multipart |
| 401 Unauthorized | Missing/invalid authentication |
| 403 Forbidden | Valid identity but insufficient permissions |
| 404 Not Found | URL/path variable does not map to a resource |
| 405 Method Not Allowed | Sending POST to a GET route or vice versa |
| 406 Not Acceptable | `Accept` incompatible with available representations |
| 409 Conflict | Operation conflicts with state/resource version |
| 413 Content Too Large | Payload/upload exceeds limit |
| 415 Unsupported Media Type | Sent body/part Content-Type is not supported |
| 422 Unprocessable Content | Syntactically valid body rejected by domain validation, if API uses this status |
| 429 Too Many Requests | Rate/quota limit |
| 500/502/503/504 | Server, gateway, or upstream failure/temporary overload |
| `ResourceAccessException` | I/O/connect/read timeout, DNS/TLS, etc. in RestClient |
| `RestClientResponseException` | HTTP error response and RestClient chooses to throw |

Not every system uses the exact same statuses; verify against the server API contract and tests. 4xx error codes are **responses from the server**, whereas `ResourceAccessException` can occur before any HTTP response is received.

### Why Are Media Type Errors So Common?

- Sending multipart without a boundary.
- Setting Content-Type application/json on a form map.
- Sending a text/plain body to a server that only accepts JSON.
- Using a JSON part without setting a part-level Content-Type.
- Passing a manually escaped JSON String body with bad escaping instead of passing a DTO for Jackson to encode.
- Thinking `Accept` specifies the request body type.

## 30. Common Mistakes When Writing Clients

1. **Using Spring Boot 3.0/3.1 while calling RestClient**: the API debuted in Spring Framework 6.1 (Boot 3.2+).
2. **Importing `WebClient` and expecting synchronous behavior**: WebClient is reactive and does not mechanically replace RestClient.
3. **Concatenating queries via string interpolation**: `+`/`&`/`#` break the URI.
4. **Using URLEncoder for path segments**: form encoding differs from URI path encoding.
5. **Double-encoding input that already contains `%2F`**: server receives the wrong value.
6. **Using default/custom URI factories without testing encoded special characters**.
7. **Confusing `.uri(URI)` with `.uri(String, vars)`**: the former takes an already-built URI.
8. **Putting queries in a form body or form fields in a query against the API contract**.
9. **Using Map<String,String> for repeated query/form fields**: loses multiple values.
10. **Failing to distinguish absent params from empty strings**: breaks defaults/validation.
11. **Setting Content-Type in the client to the response format**: confusing it with `Accept`.
12. **Sending a MultiValueMap<String,Object> multipart body while setting application/json**.
13. **Manually generating a multipart boundary out of sync between header and body**.
14. **Manually concatenating multipart byte streams via String**: corrupts binary files.
15. **Using ByteArrayResource without a filename when the server requires one**.
16. **Using non-repeatable InputStreamResource and then retrying POST**.
17. **Omitting part-level JSON Content-Type causing server DTO parsing failure**.
18. **Creating a new HTTP client/request factory per server request**: connection pool overhead.
19. **Missing connect/read timeouts**: threads hang indefinitely.
20. **Retrying POST/multipart after timeout without idempotency**: duplicate uploads/payments.
21. **Calling RestClient directly on the Netty event loop**: blocking.
22. **Assuming `retrieve().body(...)` is always non-null**: no-body/204 can be null.
23. **Catching every RestClientException and returning HTTP 200**: hides outages.
24. **Logging raw Authorization/form passwords/file bytes**: leaks secrets.
25. **Allowing users to choose arbitrary absolute URLs**: SSRF.
26. **Following Location/redirects from unallowlisted remotes**: can leak credentials.
27. **Assuming POST form works with a POJO JSON object**: requires the right converter.
28. **Ignoring repeated field order** when the server business contract depends on it.
29. **Using MultipartFile as a client upload Resource**: mixing up server and client APIs.
30. **Testing only with HTTP mocks and skipping server multipart parsers**.
31. **Hardcoding dynamic boundaries in assertions**: flaky tests.
32. **Failing to validate filenames/sizes before upload**.
33. **Depending on files existing at IDE-relative paths**: tests fail in other environments.
34. **Believing RestTemplate disappeared in Spring 6.2**: API remains; migrations depend on version.
35. **Believing RestClient automatically dispatches on a background thread**: synchronous client blocks the caller.
36. **Sending POST form-urlencoded without Content-Type**: converter/server may misinterpret.
37. **Using raw URI queries with unencoded `+`**: server may turn it into a space.
38. **Not testing charsets/Unicode in form fields**: Vietnamese text may suffer encoding bugs.
39. **Failing to separate 400 validation from 415 media mismatch**: makes requests hard for clients to fix.
40. **Reading huge upload files into `byte[]`**: memory pressure.

## 31. Production Implementation Checklist

### URI and Query

- [ ] Using template variables/UriBuilder instead of raw URL concatenation?
- [ ] URI variables containing `&`, `+`, spaces, slashes, and Unicode tested?
- [ ] Not passing already-encoded data into an encoder a second time?
- [ ] DefaultUriBuilderFactory/encoding mode configuration specified explicitly where needed?
- [ ] Repeated query params and missing/empty values handled per API contract?
- [ ] Base URL/scheme/host/port allowlisted; no SSRF from user input?
- [ ] Not putting secrets in query URLs/logs when alternatives exist?

### Body and Converters

- [ ] `Content-Type` accurately reflects the request body?
- [ ] `Accept` accurately reflects the desired response representation?
- [ ] `MultiValueMap<String,String>` for form-urlencoded with repeated values?
- [ ] `MultiValueMap<String,Object>` and Resource/HttpEntity for multipart?
- [ ] File parts have the right filename, size, media type, and part name?
- [ ] JSON parts have part-level `Content-Type`?
- [ ] Not manually managing multipart boundaries?
- [ ] Large multipart files have size quotas and streaming/repeatability policies?
- [ ] Charset/Unicode/form encoding tested?

### Reliability

- [ ] Connect/read timeouts have explicit, measured values?
- [ ] Clients/request factories/connection pools reused under control?
- [ ] Retries distinguish GET/POST and idempotency keys?
- [ ] HTTP errors separated from transport errors?
- [ ] Response DTOs have clear nullable/no-body semantics?
- [ ] Not blocking reactive event loops if the application is WebFlux?
- [ ] 429/503 have backoff/jitter and circuit-breaker/bulkhead policies?
- [ ] Client does not automatically follow unsafe redirects?
- [ ] Never logging secrets/file contents/PII?

### Tests and Operations

- [ ] Integration tests for URI templates + special characters + repeated queries?
- [ ] Form-urlencoded tests with plus signs/ampersands/Unicode?
- [ ] Multipart tests sending FileSystemResource + JSON HttpEntity part?
- [ ] Tests for 400/415/413 and safe error bodies?
- [ ] Timeouts, connection resets, invalid TLS, and rate-limits tested in staging?
- [ ] Tested through real gateway/proxy if encoding/redirects could be altered?
- [ ] File upload/response size limits and per-downstream metrics enabled?
- [ ] JUnit does not depend on fixed ports or files outside temp dirs?

## 32. Self-Check Questions

**1.** Is RestClient an asynchronous HTTP client?

**Answer:** No. RestClient is synchronous, blocking the calling thread until a response/error arrives. WebClient is the reactive/non-blocking one.

**2.** Why is `"/items/" + id` less safe than `.uri("/items/{id}", id)`?

**Answer:** URI template expansion encodes the value according to context, whereas raw concatenation can turn characters into path/query delimiters.

**3.** When a query needs the value `C++ & Java`, what should you do?

**Answer:** Use a URI builder with template variables and an appropriate encoding mode (e.g., TEMPLATE_AND_VALUES), and verify the value decodes properly on the server.

**4.** Is URLEncoder suitable for URI paths?

**Answer:** No. It encodes as application/x-www-form-urlencoded, where spaces become `+`, which differs from URI path semantics.

**5.** Do query params and form fields occupy the same place in an HTTP request?

**Answer:** No. Queries live in the URL; form-urlencoded is the request body.

**6.** Why is `MultiValueMap` better than `Map<String,String>` for forms?

**Answer:** MultiValueMap retains multiple values with the same name such as `tag=java&tag=webflux`.

**7.** Which Content-Type is needed to send a form body?

**Answer:** `application/x-www-form-urlencoded`.

**8.** To send a file + metadata in the same request, which representation should be used?

**Answer:** `multipart/form-data` with `MultiValueMap<String,Object>` containing a Resource, text fields, and HttpEntity for parts with custom headers.

**9.** Who should generate the multipart boundary?

**Answer:** The HTTP message converter/RestClient; the application should not hardcode header and body separators.

**10.** Why use FileSystemResource for a file part?

**Answer:** It provides the stream and filename from the file on disk so the converter can generate the right Content-Disposition.

**11.** Does ByteArrayResource always send a filename?

**Answer:** No. You may need to override getFilename or wrap with the appropriate headers.

**12.** How does an HttpEntity containing a JSON part differ from top-level HttpEntity in RestTemplate?

**Answer:** In a multipart map, HttpEntity represents the body/headers **of that part**. A top-level RestTemplate HttpEntity represents the body/headers of the entire request.

**13.** When the server returns 204, is `retrieve().body(Dto.class)` guaranteed to be non-null?

**Answer:** No. An HTTP response can have no body; handle null or use ResponseEntity when status is needed.

**14.** If a POST upload times out, is it certain the server did not save the file?

**Answer:** No. The server may have received/committed before the client lost the response; retries require idempotency.

**15.** Does Spring Boot 3.0 include RestClient?

**Answer:** Not in Boot 3.0's default Spring Framework 6.0; use Boot 3.2+ or a version with Framework 6.1+ to get RestClient.

**16.** Do you need to manually convert a multipart FileSystemResource into `byte[]` first?

**Answer:** No. The message converter can consume a Resource directly; holding all bytes on the heap is usually unnecessary.

**17.** If a JSON part's Content-Type is set to text/plain, what can happen?

**Answer:** The server fails to pick the right JSON decoder to bind the DTO, causing a request/part conversion error; wrap in HttpEntity with application/json.

**18.** In a WebFlux server, should you call synchronous RestClient on the Netty event loop?

**Answer:** No. It can block the loop; choose reactive WebClient or bridge blocking work onto a bounded scheduler when unavoidable.

## 33. References

- Spring Framework 6.2 — REST Clients, RestClient/RestTemplate/HTTP Interface and Multipart: https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html
- Spring Framework 6.2 — URI Links, UriBuilder/encoding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-uri-building.html
- Spring Framework — `DefaultUriBuilderFactory` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/util/DefaultUriBuilderFactory.html
- Spring Framework — `UriComponentsBuilder` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html
- Spring Framework — `RestClient` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/client/RestClient.html
- Spring Framework — `RestTemplate` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/client/RestTemplate.html
- Spring Framework — `FormHttpMessageConverter` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/http/converter/FormHttpMessageConverter.html
- Spring Framework — `HttpEntity` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/http/HttpEntity.html
- Spring Framework — `FileSystemResource` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/io/FileSystemResource.html
- Spring Framework — `MockRestServiceServer` tests: https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-client.html
- Spring Framework 6.2 — Spring MVC Multipart forms: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/multipart-forms.html
- Java 17 — `URLEncoder` Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html
- Java 17 — `HttpClient` Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- HTTP Semantics RFC 9110 — Content-Type, Accept, methods, status codes: https://www.rfc-editor.org/rfc/rfc9110.html
