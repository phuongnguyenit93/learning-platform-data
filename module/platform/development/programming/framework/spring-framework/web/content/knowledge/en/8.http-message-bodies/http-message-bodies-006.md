# Content Negotiation by Accept and Media Type Selection in Spring MVC

## 1. Objectives and Context

An HTTP resource can have **multiple representations**: JSON for applications, plain text for CLI tools, HTML for browsers, XML for integration systems. **Content negotiation** is the process of determining which representation fits the capabilities and preferences stated by the client, the server's capabilities, controller mappings, and message converters.

In Spring MVC (Servlet stack), this lesson helps you:

- Correctly read the `Accept` header, media types, wildcards, `q` weights, and their relationship to `Content-Type`.
- Understand how `ContentNegotiationManager` determines requested media types; understand modern defaults and customization strategies.
- Explain how `@GetMapping(produces=...)`, `@RequestMapping(produces=...)`, `@ResponseBody`/`@RestController`, and `HttpMessageConverter` work together to choose a representation.
- Know when `406 Not Acceptable` occurs, and distinguish it from `415 Unsupported Media Type` and other errors.
- Design endpoints supporting one or multiple representations, test with `curl`/MockMvc, and mind `Vary: Accept` caching, versioning, and security.

Examples use **Java 17+ with Spring Framework 6.2/Spring Boot 3.x** (plus Spring MVC + Jackson dependencies); do not apply Spring WebFlux assumptions. Commands/tests describe expected behavior on the sample app rather than asserting fixed HTTP error bodies/outputs across every server or security configuration.

## 2. Distinguishing Resource, Representation, and Media Type

A **resource** is an entity identified by a URI, such as `/api/media/items/7`. The same resource can be presented in different representations, for example:

```http
GET /api/media/items/7 HTTP/1.1
Host: localhost:8080
Accept: application/json
```

The server may return:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":7,"name":"Pen"}
```

Whereas another client requests plain text:

```http
GET /api/media/items/7 HTTP/1.1
Host: localhost:8080
Accept: text/plain
```

The server may return:

```http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

Item 7: Pen
```

This is **one URL, two representations**, provided the server genuinely supports both. The response `Content-Type` header confirms the **actual format sent**, while the request `Accept` header states **what format the client wants to receive**. `charset` and certain other headers depend on converters/configuration; the HTTP samples here are illustrative, not byte-for-byte guarantees.

A media type has syntax `type/subtype` and may carry parameters:

- `application/json`: JSON.
- `text/plain`: plain text.
- `text/html`: HTML.
- `application/xml`: XML.
- `application/problem+json`: JSON Problem Details format.
- `application/vnd.example.v1+json`: application-specific JSON (vendor media type).
- `text/plain;charset=UTF-8`: content type with a charset parameter.

**Simply returning a Java object does not make the server produce XML/CSV/HTML automatically.** A serialization mechanism for that representation must exist, be configured, and satisfy media type conditions.

## 3. Semantics of Accept

`Accept` tells the server which media types the client accepts in the **response**. It is a header for the *response representation*, not a description of the request body. General syntax:

```http
Accept: application/json, text/plain;q=0.6, */*;q=0.1
```

According to HTTP Semantics (RFC 9110):

- **Missing `Accept`:** the client does not restrict the server to a specific list of media types; the server can pick any available representation. HTTP does not mandate "must be JSON".
- **`Accept: */*`:** allows any media type. It does not say the client *prefers* JSON.
- **`Accept: application/*`:** allows subtypes in the `application` group (such as `application/json`), if supported by the server.
- **`Accept: application/json`:** specifies JSON only; if the server only has `text/plain`, Spring MVC typically returns HTTP 406.
- **`Accept: application/json, text/plain`:** both have the default quality factor `q=1`; this header alone does not prescribe which representation is chosen when both match.
- **`q`:** preference weight between `0` and `1`; defaults to `1` when omitted; `q=0` means that representation is not acceptable.
- **Wildcards:** `*/*` matches any type, `text/*` matches subtypes under text. More specific media ranges generally take precedence when determining the q value for a specific media type.

Example:

```http
Accept: application/json;q=0.9, text/plain;q=0.4
```

If both JSON and text can be served, JSON is **preferred by q**. Flipping q to `application/json;q=0.2, text/plain;q=0.9` expresses a preference for text. `q` is a **relative quality weight**, not a 90% probability that the server returns JSON.

Another example:

```http
Accept: application/json;q=0, text/plain;q=1
```

Per HTTP semantics, the client excludes JSON and accepts text. This only succeeds when the server actually has a text representation; otherwise, the server may return 406 or, per the HTTP spec, choose to ignore preferences. In Spring MVC applications with explicit `produces`, incompatibility typically yields 406.

A pitfall to avoid misreading:

```http
Accept: application/json;q=0, */*;q=0.8
```

**Wildcards do not automatically "rescue" an excluded JSON type:** the specific media range `application/json` takes precedence when determining the q factor for JSON itself. Acceptability is calculated using specificity and q, not merely the highest q anywhere in the header.

### Quick Reference Table

| Accept | HTTP Intent | When Endpoint Only Returns JSON |
| --- | --- | --- |
| No header | No restriction specified | Usually JSON, if the framework selects it |
| `*/*` | Accepts everything | Usually JSON |
| `application/json` | Wants JSON | JSON (if a converter can write it) |
| `application/*` | Accepts application family | JSON can match |
| `text/plain` | Wants text only | Usually 406 |
| `application/xml` | Wants XML only | Usually 406 |
| `application/json;q=0` | Rejects JSON | Usually 406 if no other valid variant exists |
| `application/json;q=0.2,text/plain;q=0.9` | Prefers text over JSON | A JSON-only endpoint can still return JSON because q=0.2 is still acceptable |

These are the **HTTP model and common outcomes**; specific mappings, codecs, and interceptors determine the final status of an application.

## 4. Accept and Content-Type: Two Data Directions

Four situations:

| Header | Direction | Question |
| --- | --- | --- |
| Request `Accept` | Client → Server | "Which format do I want for the response?" |
| Request `Content-Type` | Client → Server | "Which format is the body I am **sending**?" |
| Response `Content-Type` | Server → Client | "Which format is the body the server is **returning**?" |
| Response `Vary` | Server → client/cache | "Which request headers influence the response variant?" |

A POST can send both simultaneously:

```http
POST /api/media/echo HTTP/1.1
Content-Type: application/json
Accept: application/json

{"id":7,"name":"Pen"}
```

- `Content-Type: application/json` specifies how the server **reads** the body. In Spring MVC, `consumes` and `HttpMessageConverter.canRead` govern this direction.
- `Accept: application/json` influences how the server **writes** the response. In Spring MVC, `produces` and `HttpMessageConverter.canWrite` govern this direction.
- If the body is labeled `text/plain` while the endpoint only accepts JSON → typically **415 Unsupported Media Type**.
- If valid JSON is sent in the body while the client requests XML for the response and the endpoint only returns JSON → typically **406 Not Acceptable**.
- If JSON syntax is invalid even with the right `Content-Type`, the error is typically **400 Bad Request** because the body cannot be read/deserialized. Do not confuse 400 with 406 or 415.

`Accept-Language` selects language, `Accept-Encoding` selects content coding such as gzip, while `Accept` here selects **media type**. These headers represent orthogonal negotiation dimensions and do not substitute for each other. CORS `Access-Control-Allow-Headers`/`Access-Control-Allow-Methods` are also a separate concern.

## 5. How Does Spring MVC Resolve Media Types and Select a Representation?

Overall flow, viewed as two related decisions:

```text
HTTP request: path + method + Accept + (Content-Type if body present)
            |
            v
ContentNegotiationManager
  -> determines requested/acceptable media types
            |
            v
RequestMappingHandlerMapping
  -> selects handler matching path, HTTP method, params/headers,
     consumes (request body) and produces (response)
            |
            v
Handler return value: object / String / ResponseEntity / ...
            |
            v
RequestResponseBodyMethodProcessor or HTTP entity processor
  -> matches acceptable media types against types writable
     by HttpMessageConverter for the return type
            |
            v
Selects response media type + converter -> serializes body
            |
            v
HTTP response: status + Content-Type + body
```

**This is a logical diagram, not a rigid sequence for every internal branch.** Handler mapping receives `Accept` info from the negotiation manager when evaluating `produces` conditions; when preparing to write the response, Spring again uses acceptable/producible media types alongside the converter set. A handler may match path/method and still fail to write the body as desired.

### 5.1. Default Content Negotiation in Modern Spring MVC

In uncustomized Spring MVC 6.x, **the `Accept` header is inspected by default** to determine requested media types. Do not copy legacy Spring MVC 4.x patterns where path extensions like `.json` were historically favored.

In common 6.x applications:

- `GET /api/items/7` and `GET /api/items/7.json` are **not automatically the same route**. Suffix/path extension matching depends on routing configuration and is not a default mechanism to rely on.
- Query `?format=json` **does not control** content negotiation by default. Enabling it requires configuring an explicit strategy.
- Without `Accept` or when the client sends `*/*`: Spring can pick a server-supported type, but if you declare multiple handlers on the same path with different `produces` and define no default priority, **do not assume the choice is always deterministic**. Design an explicit default representation when the API contract requires one.
- Filters, error handlers, controller advice, Spring Security, and reverse proxies can make observed statuses/headers differ from examples.

### 5.2. `@RequestMapping(produces=...)` as a Mapping Condition

```java
@GetMapping(path = "/books/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
public Book book(@PathVariable long id) {
    return new Book(id, "Java");
}
```

`produces` describes the response type the method **commits to provide** as a handler-selection condition. `Accept: application/json` is compatible; `Accept: application/xml` is incompatible when only the JSON handler exists.

Notes:

- Method-level `produces` **overrides** a class-level declaration rather than "appending to" the class list.
- A method can declare `produces = {"application/json", "application/xml"}`, **but declaring it alone does not create XML output capability**. A converter and serializer supporting that object type must be present.
- Use `produces` when an API commits to a stable response media type and wants clients to receive 406 when requesting unsupported formats.
- If using a plain `@Controller` and returning `String` as a **view name**, `@ResponseBody` is needed to serialize the value; with `@RestController`, behavior is equivalent to `@Controller + @ResponseBody` on methods.
- `produces` is typically evaluated during method selection; the actual converter is checked during response writing. Debug these two points separately.

### 5.3. `HttpMessageConverter` Decides Which Types Can Be Written

Spring MVC writes `@ResponseBody`/`ResponseEntity` bodies through converters:

| Converter (Concept) | Typical Data/Format Written |
| --- | --- |
| `MappingJackson2HttpMessageConverter` | Java object → JSON via Jackson ObjectMapper |
| `StringHttpMessageConverter` | `String` → text; defaults to text media types and can be configured otherwise |
| `ByteArrayHttpMessageConverter` | `byte[]` → byte stream |
| `MappingJackson2XmlHttpMessageConverter` or other XML converter | Java object → XML if proper library is present and registered |
| `FormHttpMessageConverter` | Form/`MultiValueMap` per supported media types |

Converter names/choices can change across Spring versions and configurations; for example, `StringHttpMessageConverter` can support multiple media types and converter selection is affected by ordering. **Do not assume JSON from a `String`** merely because the client sent `Accept: application/json`; for valid JSON, return a suitable DTO/record and use a JSON converter.

If no converter can write the return type in the required media type, Spring cannot perform content negotiation as desired. Distinguishing "mapping rejected `produces`" from "converter cannot write" is critical when reading logs.

### 5.4. Media Type Selection Is the Intersection of Three Factors

A helpful mental model:

1. **Client accepts** (`Accept` + q + wildcards).
2. **Handler advertises** (`produces` or inferred capability if omitted).
3. **Converter actually supports** the Java return type and target media type.

A valid choice must satisfy all relevant layers. Adding `produces="application/xml"` alone is not enough without an XML converter. Adding Jackson to the classpath does not serve clients wanting XML either. Raising a media type's q does not "create" a representation the server does not support.

## 6. Java 17+ Spring Boot Example: One URL, Two Representations

The goal is to illustrate two methods handling the **same URL** with different `produces`. When `Accept` is explicit, Spring MVC selects the matching method.

Create a Maven Spring Boot 3.x project on Java 17+ with `spring-boot-starter-web` (usually including Jackson JSON). Place both files below in package `com.example.demo`.

File `src/main/java/com/example/demo/DemoApplication.java`:

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

File `src/main/java/com/example/demo/MediaController.java`:

```java
package com.example.demo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/media")
public class MediaController {

    @GetMapping(path = "/items/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Item itemJson(@PathVariable("id") long id) {
        return new Item(id, "Pen");
    }

    @GetMapping(path = "/items/{id}",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String itemText(@PathVariable("id") long id) {
        return "Item " + id + ": Pen";
    }

    @GetMapping(path = "/json-only/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Item jsonOnly(@PathVariable("id") long id) {
        return new Item(id, "Pen");
    }

    @PostMapping(path = "/echo",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Item echo(@RequestBody Item item) {
        return item;
    }

    public record Item(long id, String name) {}
}
```

Key points:

- `GET /api/media/items/7` + `Accept: application/json` → `itemJson` handler, Java object serialized to JSON by Jackson.
- Same URL + `Accept: text/plain` → `itemText` handler, String written by the text converter.
- `GET /api/media/json-only/7` + `Accept: text/plain` → no matching representation handler, typically 406.
- `POST /api/media/echo` uses `consumes` for the **incoming** body and `produces` for the **outgoing** body.
- `itemJson` and `itemText` share the same URL and GET method but differ in `produces`, so both can be registered. **Do not rely on behavior when `Accept` states no clear preference**: the two mappings may tie in priority, and the outcome depends on matching logic/configuration. Production APIs should define an explicit default format in the contract and design clear fallbacks.
- The example has no database; regardless of the `id` received, the sample resource is named `Pen`. In a real service, "resource not found" is a business 404, not a content negotiation error.

Run inside the configured Maven Boot project:

```bash
./mvnw spring-boot:run
```

Windows PowerShell: `.\mvnw.cmd spring-boot:run`. Boot defaults to port 8080 unless `server.port` is changed. You cannot run `javac MediaController.java` standalone without Spring/Boot/Jackson dependencies on the classpath.

## 7. Testing with curl and Predicting Status/Content-Type

In the examples below, `curl -i` displays status and headers. In Windows PowerShell (especially older versions), prefer `curl.exe`; the `\` line continuation is bash/zsh syntax—write each command on a single line in PowerShell.

### 7.1. Requesting JSON

```bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/media/items/7
```

Expected **200 OK**, `Content-Type` compatible with `application/json`, body:

```json
{"id":7,"name":"Pen"}
```

Do not assert JSON field order when the serializer can be reconfigured.

### 7.2. Requesting text/plain

```bash
curl -i -H "Accept: text/plain" \
  http://localhost:8080/api/media/items/7
```

Expected **200 OK**, `Content-Type` compatible with `text/plain`, exact body:

```text
Item 7: Pen
```

### 7.3. q-Value Preferring Text

```bash
curl -i -H "Accept: application/json;q=0.2, text/plain;q=0.9" \
  http://localhost:8080/api/media/items/7
```

With both `produces` handlers and standard MVC configuration, text has the higher weight so the plain-text representation is preferred. Swap the weights to observe JSON being preferred:

```bash
curl -i -H "Accept: application/json;q=0.9, text/plain;q=0.2" \
  http://localhost:8080/api/media/items/7
```

Do not infer that q=0.2 "forbids" JSON: any positive q still indicates acceptability, just with lower priority.

### 7.4. Wildcard

```bash
curl -i -H "Accept: text/*" \
  http://localhost:8080/api/media/items/7
```

In this example, `text/plain` is compatible with `text/*`, so the client can receive plain text. Testing `Accept: */*` or omitting Accept can match multiple representations; if the API design requires deterministic results, do not test against an uncommitted default.

### 7.5. 406 When No Suitable Representation Exists

```bash
curl -i -H "Accept: application/xml" \
  http://localhost:8080/api/media/json-only/7
```

Expected **406 Not Acceptable**. `GET /api/media/json-only/7` has an existing GET mapping, but `produces=application/json` cannot satisfy `application/xml`. Do not change the route or HTTP method. Fix it on the client by accepting JSON, or extend the server to actually support XML if the contract requires it.

To see that a request to a single-representation endpoint does not fail just because the client prefers another format, try:

```bash
curl -i -H "Accept: application/json;q=0.2, application/xml;q=0.9" \
  http://localhost:8080/api/media/json-only/7
```

JSON **is still acceptable** (q=0.2 > 0), so the JSON endpoint can fulfill the request. The server is not forced to output XML merely because XML has a higher q if XML is unsupported.

### 7.6. 415 Is the Opposite Direction's Error

```bash
curl -i -X POST http://localhost:8080/api/media/echo \
  -H "Content-Type: text/plain" \
  -H "Accept: application/json" \
  --data "hello"
```

Expected **415 Unsupported Media Type** because `consumes=application/json`, while the request body is declared as `text/plain`. Setting `Accept: application/json` does not fix 415 because Accept only specifies the **response** format.

Valid POST:

```bash
curl -i http://localhost:8080/api/media/echo \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data '{"id":7,"name":"Pen"}'
```

Expected **200 OK** and a JSON object matching the sent body (echo demo).

POST with a valid JSON body requesting an XML response:

```bash
curl -i http://localhost:8080/api/media/echo \
  -H "Content-Type: application/json" \
  -H "Accept: application/xml" \
  --data '{"id":7,"name":"Pen"}'
```

Typically **406** because the endpoint only declares JSON output; the JSON input is still valid. Depending on configuration, rejection may occur during request mapping before the controller is invoked.

## 8. MockMvc: Testing Contract Behavior

Create `src/test/java/com/example/demo/MediaControllerTest.java` in a project with `spring-boot-starter-test`, in the same package:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(MediaController.class)
class MediaControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsJsonRepresentation() throws Exception {
        mvc.perform(get("/api/media/items/7")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.name").value("Pen"));
    }

    @Test
    void acceptsPlainTextRepresentation() throws Exception {
        mvc.perform(get("/api/media/items/7")
                .accept(MediaType.TEXT_PLAIN))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.TEXT_PLAIN))
            .andExpect(content().string("Item 7: Pen"));
    }

    @Test
    void usesRequestedQualityPreference() throws Exception {
        mvc.perform(get("/api/media/items/7")
                .header("Accept",
                        "text/plain;q=0.9, application/json;q=0.2"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.TEXT_PLAIN));
    }

    @Test
    void acceptsTextWildcard() throws Exception {
        mvc.perform(get("/api/media/items/7")
                .accept(MediaType.parseMediaType("text/*")))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.TEXT_PLAIN));
    }

    @Test
    void returns406ForUnsupportedResponseType() throws Exception {
        mvc.perform(get("/api/media/json-only/7")
                .accept(MediaType.APPLICATION_XML))
            .andExpect(status().isNotAcceptable());
    }

    @Test
    void returns415ForUnsupportedRequestBodyType() throws Exception {
        mvc.perform(post("/api/media/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.APPLICATION_JSON)
                .content("hello"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void handlesValidJsonPost() throws Exception {
        mvc.perform(post("/api/media/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"id\":7,\"name\":\"Pen\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("Pen"));
    }
}
```

Run:

```bash
./mvnw test
```

PowerShell: `.\mvnw.cmd test`. This is a **test sample runnable in a Boot app with complete dependencies**, not a claim that a command was executed here. If the project integrates Spring Security, custom advice, custom converters, or customized `@WebMvcTest`, configure the test accordingly before interpreting statuses.

To test tightly against the HTTP contract, check **status, compatible Content-Type, appropriate body**, and special response headers when needed. Do not test `Content-Type` using a fixed string with charset if the framework is allowed to add or omit charset parameters. Do not couple tests to JSON field order.

## 9. Configuring ContentNegotiationManager When Truly Needed

Spring MVC provides `WebMvcConfigurer.configureContentNegotiation` to configure strategies. Modern defaults normally use `Accept` only. If there is a requirement to support `?format=json` or `?format=txt`, you can explicitly enable the **query parameter strategy**.

Configuration example (standalone class in the same application package, but apply only if the product **genuinely wants** a `format` parameter):

```java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.config.annotation.ContentNegotiationConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MediaNegotiationConfig implements WebMvcConfigurer {

    @Override
    public void configureContentNegotiation(
            ContentNegotiationConfigurer configurer) {
        configurer
            .favorParameter(true)
            .parameterName("format")
            .mediaType("json", MediaType.APPLICATION_JSON)
            .mediaType("txt", MediaType.TEXT_PLAIN);
    }
}
```

Then `?format=json`/`?format=txt` can influence requested media types and matching mappings. **Do not copy this configuration class into the project and expect tests checking Accept alone to behave identically when requests contain a format parameter**: the parameter strategy can change priority if enabled. Define a clear contract when Accept and `format` conflict.

Notes:

1. Enabling `favorParameter(true)` is an API design decision, **not a fix for "Spring does not understand Accept"**.
2. The media type mapping list such as `json`, `txt` must be controlled; never let clients supply arbitrary extensions/media types.
3. When using query parameters, consider **cache keys** (URI query strings are part of the target), unlike caching by the Accept header.
4. The general recommendation is to avoid relying on **path extensions** like `/users.json` for format selection in new Spring MVC projects. Suffix routing has historical issues with parsing/ambiguity and reflected file download (RFD) risks.
5. If an API only commits to JSON, simply using `produces=application/json` is clearer than a set of ambiguous fallback strategies.

### 9.1. Should You Force `defaultContentType`?

Spring MVC lets you configure a default content type in content negotiation. However, choosing a default must follow the application's contract: if the API only serves JSON, JSON is reasonable; if a resource has multiple formats, clearly define which variant a client without Accept receives, then **test it**. Do not assume `defaultContentType` alone automatically resolves all equally matched `produces` handlers deterministically.

If the server must reject requests missing `Accept` per its own rules, that is a **custom application policy**, not an HTTP default. Normally you should not force clients to specify `Accept` when serving a single format.

## 10. Default Content, 406, and Missing Converters

### 10.1. When Does 406 Happen?

Per HTTP, a server may return 406 when no representation satisfies `Accept`; the RFC also allows ignoring preferences in certain cases. **Spring MVC with explicit `produces` constraints typically returns 406** when path/method match but `Accept` does not, via `HttpMediaTypeNotAcceptableException`.

For example, `GET /api/media/json-only/7` has a GET mapping, and the client sends `Accept: application/xml`: the error is **406**, not 404/405/415.

Do not conclude from status 406 that the controller ran; with `produces`, Spring can exclude the mapping before calling the method. If a mapping is chosen but the converter cannot write, an exception can also occur during response writing; depending on the case and version, not every serialization failure becomes 406 (some are 500 server errors).

### 10.2. When Does 415 Happen?

`415 Unsupported Media Type` reflects an unsupported **request representation**: the body's `Content-Type` does not match `consumes` or the server's decoders. Even if the client sends `Accept: application/json`, the body can still be `text/plain` and trigger 415. `HttpMediaTypeNotSupportedException` is the typical Spring exception.

### 10.3. When Do 400, 404, and 405 Happen?

- `400`: malformed JSON syntax, undeserializable body, or invalid binding/validation; can happen even when `Content-Type` is right.
- `404`: URL has no matching mapping/resource.
- `405`: URL matches, but the HTTP method is unsupported; typically includes an `Allow` header.
- `406`: response media type cannot satisfy `Accept`.
- `415`: request body media type is unsupported.

If a request violates **multiple conditions simultaneously**, do not predict the error by treating the list above as a strict precedence order; mapping stages, converters, filters, exception handlers, and customizations determine which status surfaces first.

### 10.4. `Content-Type` on Error Responses Need Not Match Success Responses

When Spring Boot uses controller advice or `ProblemDetail`, error responses may be `application/problem+json`, an HTML error page, or an empty body depending on configuration. Do not mistakenly conclude an endpoint returns XML just because a 406 test has no JSON body; negotiation errors may require an intentional fallback so clients can still read error details. A `406` response is not guaranteed to list every supported representation; to advertise capabilities to clients, document them in OpenAPI or API docs.

## 11. Media Types with +json Suffix and Versioning

Some APIs use vendor media types such as:

```http
Accept: application/vnd.example.item.v1+json
```

The intent is to request a representation with a **specific** media type. Modern JSON converters may support `application/*+json`, but **a `produces = application/json` mapping does not automatically match every vendor media type**. If you want an endpoint to handle `application/vnd.example.item.v1+json`, declare the corresponding `produces` and verify that a converter supports writing that exact type.

Illustrative extension example:

```java
@GetMapping(
    path = "/versioned/{id}",
    produces = "application/vnd.example.item.v1+json")
public Item versioned(@PathVariable("id") long id) {
    return new Item(id, "Pen");
}
```

This snippet **must be added as a method inside a controller where the `Item` type already exists** (or define `Item`/import annotations yourself); it is not a standalone Java file. Do not automatically treat `Accept: application/json` as equivalent to the vendor media type above. Media-type versioning helps define clear representations, though it complicates clients, caching, and docs; weigh it against URL/header versioning based on your goals.

When using `application/problem+json`, distinguish it from the resource's success media type. Error responses are a separate contract and do not prove an endpoint supports `problem+json` as a success representation.

## 12. Caching: When Responses Depend on Accept, Consider Vary

Suppose `GET /api/media/items/7` returns JSON or text depending on `Accept`. An intermediate cache unaware of variants could serve the text version to a client wanting JSON if it keys the cache solely by URL. The header:

```http
Vary: Accept
```

tells caches that response selection depends on the request's `Accept` header. Consider emitting this header **for relevant responses**, not just a single success branch. Spring or reverse proxies **may** add `Vary` in certain features like CORS, but you should not assume every content-negotiated response automatically gets `Vary: Accept` in all setups.

The application can attach the header for multi-variant responses:

```java
@GetMapping(path = "/cached/{id}", produces = "application/json")
public ResponseEntity<Item> cachedJson(@PathVariable long id) {
    return ResponseEntity.ok()
            .varyBy("Accept")
            .body(new Item(id, "Pen"));
}
```

This is an illustrative method placed in a controller with suitable `ResponseEntity`, `GetMapping`, `PathVariable`, and `Item` record imports; **it is not a complete standalone program**. If your project uses an API version lacking the builder method above, you can use `header(HttpHeaders.VARY, HttpHeaders.ACCEPT)` on the builder. `Vary` must accurately reflect the headers that actually affect the representation, and does not replace cache policies, TTL, or ETag.

Note: if a response contains user-specific/authorized data, `Vary: Accept` alone **does not make private content safe for shared caches**. Proper `Cache-Control`, authentication, and authorization are still required.

## 13. Production Diagnostics: From Request to Converter

When clients receive an unexpected format or 406:

1. **Capture the real request:** path, method, `Accept`, `Content-Type`, body; tools like browsers, curl, and API gateways may inject `Accept: */*` or multiple types.
2. **Separate read/write directions:** 415 points to `Content-Type`/`consumes`; 406 points to `Accept`/`produces`/canWrite; 400 points to syntax/deserialization.
3. **Inspect mappings:** controller methods and `@RequestMapping(produces=...)` at class/method levels; method-level overrides class-level. Verify path/method before digging into formats.
4. **Inventory actual representations:** not just annotations, but also Jackson XML libraries, converters, and serialization of the Java return type.
5. **Audit q/wildcards:** check q=0, omitted q (default 1), wildcards, and subtypes; never simply "pick the first Accept element".
6. **Check negotiation strategy:** Spring MVC 6.x defaults to Accept; look for custom `WebMvcConfigurer`, `ContentNegotiationManager`, `favorParameter`, `defaultContentType`.
7. **Check `String` returns:** `@Controller` without `@ResponseBody` may render a view name; `@RestController` writes a response body.
8. **Inspect converters:** if a DTO fails JSON serialization on special types (cycles, lazy proxies, unsupported serializers), changing `Accept` will not reliably fix it.
9. **Check caches/gateways:** one URL with multiple formats needs `Vary: Accept` and suitable cache config; proxies may strip or alter headers.
10. **Do not assume fixed default error bodies:** Spring Boot/`ProblemDetail`/advice can vary. Check status and headers, then log safely.
11. **Inspect registered mappings:** Spring Boot Actuator `/actuator/mappings` if dependencies and configuration permit; do not expose sensitive actuators publicly just to debug.
12. **Vary one variable at a time:** keep URL/method fixed and vary `Accept`; test wildcards, q, and missing Accept. Separately vary `Content-Type` on POST.

For logging, consider debug level on mapping/HTTP converter selection classes in test environments; avoid logging bodies, tokens, and personal data solely to investigate negotiation.

## 14. API Design: Practical Choices

**JSON-only APIs:** declare `produces=application/json` on endpoints, include Jackson, and use DTOs/records as responses. `Accept: application/json` succeeds; `Accept: application/xml` typically returns 406. This is a simple, easy-to-document design.

**Multi-format APIs:** define the list of supported representations; provide a converter for each format; decide the default response explicitly; document `Accept` and q; test status/content-type and `Vary`. If using multiple handlers on the same URL distinguished by `produces`, test both explicit headers and missing/tied cases to avoid ambiguous selection.

**Export/report APIs:** if JSON, CSV, and PDF are **structurally distinct export formats** with different document-generation logic, you can use `Accept` or dedicated export URLs (`/reports/42.csv` only when explicitly designed/routed). Never merely swap the `Content-Type` header while still sending a JSON body; the media type must reflect the content.

**API clients:** set `Accept` to the formats you actually know how to parse, rather than always sending `*/*`. Set `Content-Type` to match the body **you are actually sending**. If an API offers multiple representations, clients can use weighted `Accept` values when prepared to handle multiple formats.

## 15. Common Pitfalls and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating `Accept` as the request body format | Misdebugging 406 as 415 | Distinguish `Accept` and `Content-Type` |
| Declaring `produces="application/xml"` without installing a converter | Cannot serialize objects to proper XML | Add/configure converter and test with real DTOs |
| Returning `String` in `@Controller` expecting a response body | Spring may treat String as a view name | Use `@ResponseBody`/`@RestController` |
| Expecting `GET /items.json` to switch format by suffix | 6.x routing does not rely on suffix strategy by default | Use Accept or declare explicit routes |
| Expecting `?format=xml` to work by default | Parameter strategy is off | Configure explicitly or use Accept |
| Ignoring q or wildcards | Wrong media type selected | Use the framework's parser/negotiation |
| Assuming q=0.1 means forbidden | Rejecting valid representations | Only q=0 excludes; positive q is acceptable |
| Missing tests for incompatible Accept | 406 only discovered in production | Test with MockMvc and real clients |
| Omitting `Vary: Accept` when caching variants | Caches can mix JSON and text | Design Vary and cache policies explicitly |
| Using a JSON converter while setting `Content-Type` to XML | Payload and label mismatch | Serialize real XML or stop advertising XML |
| Forgetting error exceptions/responses also have media types | Clients cannot parse errors consistently | Design explicit error formats and test 406 cases |
| Using wildcard `*/*` in tests while hardcoding JSON | Different representation may be chosen later | Test with specific Accept when contracts require stability |

## 16. Self-Check Questions

**1.** A GET endpoint only specifies `produces = application/json`, and a client sends `Accept: application/xml`. What is the typical status?

**Answer:** `406 Not Acceptable`; the path/method may match, but no suitable representation exists.

**2.** A client sends a JSON body with `Content-Type: text/plain` to a POST with `consumes = application/json`, while setting `Accept: application/json`. Does that resolve the error?

**Answer:** No. `Accept` does not fix the request body's label; `415` is typically returned.

**3.** Does `Accept: text/plain;q=0.8, application/json;q=0.2` force the server to always pick text?

**Answer:** No. It prefers text **if the server has a text variant**; JSON with q=0.2 is still acceptable if only JSON exists.

**4.** Does `Accept: */*` mean "JSON only"?

**Answer:** No. It accepts any media type.

**5.** If a JSON converter is present, is `produces = "application/xml"` enough to output XML?

**Answer:** No. An XML converter/serializer that genuinely supports the return type is needed, along with a compatible mapping.

**6.** Can two handlers share the same GET method and URL with different `produces`?

**Answer:** Yes. This is one way to provide separate representations by Accept; you must define how requests with no Accept or tied preferences behave.

**7.** If the same URL returns JSON or text depending on `Accept`, which header should intermediate caches watch?

**Answer:** `Vary: Accept`, along with appropriate caching policies.

**8.** Why does 406 not always mean the controller method ran?

**Answer:** `produces` can disqualify the mapping during handler selection before the controller is invoked.

## 17. References

- Spring Framework 6.2 — Content Types and Negotiation Configuration: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/content-negotiation.html
- Spring Framework 6.2 — Mapping Requests, produces/consumes conditions: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework 6.2 — HTTP Message Conversion: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html
- Spring Framework 6.2 — @ResponseBody: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/responsebody.html
- Spring Framework 6.2 — Error Responses: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
- RFC 9110 — HTTP Semantics, Accept/q/wildcard/Vary and 406/415: https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
