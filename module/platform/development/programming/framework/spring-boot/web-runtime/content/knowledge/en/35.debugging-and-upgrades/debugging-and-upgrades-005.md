# 405, 406, and 415 Due to Method or Format Mismatches in Spring Boot

## 1. Read the Meaning of All Three Codes Before Changing the API

A client calls the right hostname and believes the `/api/products` URL is right, yet the server returns one of three error codes:

- **405 Method Not Allowed:** the HTTP method (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`, ...) is not allowed for the resource/route.
- **406 Not Acceptable:** the server cannot produce a **response** representation matching the media types requested by the client in `Accept`.
- **415 Unsupported Media Type:** the representation type of the **request body** declared in `Content-Type` is not accepted by the endpoint/decoder.

All three are HTTP contract errors, but at different layers. Do not "quick-fix" them by opening `@RequestMapping` to every method, deleting all `consumes`/`produces`, or returning `200 OK` for every error. Fix **the client sending the wrong request**, or update the server API contract **when business requirements truly call for it**.

This lesson uses **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 21, Gradle, and JUnit 5**; most concepts apply to Java 17+. The MVC and WebFlux examples are **two separate applications**. A request's actual status can still be altered by Spring Security, reverse proxies, gateways, CORS, custom exception handlers, path matching, or content negotiation configuration. Error response bodies shown in this article are illustrative, not byte-exact outputs of every system.

## 2. Three HTTP Dimensions Must Be Separated

```text
HTTP request
   |
   +-- request method: GET / POST / PUT / PATCH / DELETE
   |        └── @GetMapping, @PostMapping, ... ─── 405
   |
   +-- Content-Type: is the request body JSON/XML/text/multipart?
   |        └── consumes + input reader ───────── 415
   |
   +-- Accept: which response format does the client accept (JSON/XML/text)?
            └── produces + output writer ──────── 406
```

A valid POST request:

```http
POST /api/products HTTP/1.1
Host: 127.0.0.1:8080
Content-Type: application/json
Accept: application/json

{"name":"Pen"}
```

Here `Content-Type` describes the **bytes being sent to the server**. `Accept` describes the **data representation the client wants the server to return**. They may share the same value, yet they are not the same header.

If a controller accepts JSON yet returns `text/plain`, a valid request can carry `Content-Type: application/json` together with `Accept: text/plain`. If the controller accepts text and returns JSON, the two headers swap. Meanwhile, the HTTP method is an independent constraint unrelated directly to JSON or XML.

## 3. Comparison Table of 405/406/415 and Commonly Confused Codes

| Status | Name | When to suspect? | What to check |
| --- | --- | --- | --- |
| **405** | Method Not Allowed | Same path has a mapping, but not for this method | Actual method, `@...Mapping`, `Allow` |
| **406** | Not Acceptable | Server cannot produce the output format the client wants | `Accept`, `produces`, response converter |
| **415** | Unsupported Media Type | Server cannot read the body format sent by the client | `Content-Type`, `consumes`, input converter |
| **400** | Bad Request | Malformed JSON, argument binding failure, missing required body | Body syntax, DTO, validation |
| **404** | Not Found | Path does not match (or resource is hidden) | Path, context path, proxy rewrite |
| **401/403** | Auth/security errors | Security filter blocks before controller | Credentials, ACL, CSRF, CORS |
| **413** | Content Too Large | Body exceeds size limit | Proxy/servlet/codec limits |
| **422** | Unprocessable Content | Used by some APIs for business validation | Specific API contract; not Spring default |
| **500** | Server error | Unexpected conversion/serialization/custom handler bug | Exception stack and codec configuration |

**Do not infer status from a single header alone.** A request can have both the wrong method and the wrong media type. Spring mapping checks multiple conditions and filters can fail earlier; diagnostic tests should keep the other dimensions **valid** and vary only the one dimension under test.

## 4. Which Layers Does a Request Pass Through in Spring MVC?

```text
Browser/SDK -> proxy/WAF -> Tomcat (Servlet)
                              |
                              v
                    Servlet filters / Security / CORS
                              |
                              v
                        DispatcherServlet
                              |
                              v
                    RequestMappingHandlerMapping
                      path, method, params, headers,
                      consumes, produces
                              |
             +----------------+----------------+
             |                |                |
          mapping          argument         response
          mismatch         reader           writer
           405/...         415/400          406/500
                              |
                              v
                       Controller/service
                              |
                              v
                      HTTP status/headers/body
```

`@RestController` does not bypass routing. The controller may **never be invoked** if method, `consumes`, or `produces` fails to match. Once mapping succeeds, `@RequestBody` still needs an `HttpMessageConverter` to read the body. After the handler returns a value, `@ResponseBody`/`ResponseEntity` still needs a converter to write an acceptable media type.

Therefore, 415 can arise during **mapping** or while **reading the body**; 406 can arise during **mapping** or when **selecting an output representation**. A converter failure while serializing after handler selection can also turn into 500. Never pin every 406/415 onto a single line of code.

## 5. 405: HTTP Method Does Not Match Route, Not a JSON Error

Suppose a controller declares only:

```java
@GetMapping("/api/products/{id}")
public ProductView get(@PathVariable String id) {
    return new ProductView(id, "Demo item");
}
```

Client sends:

```http
POST /api/products/p1 HTTP/1.1
Content-Type: application/json

{"name":"Pen"}
```

Here `POST /api/products/p1` has **no mapping** in the example, whereas `GET /api/products/p1` does. 405 is the proper contract error. Fix it by calling **GET** to read the resource, or design a dedicated POST/PUT/PATCH endpoint if business logic requires a write action.

Common causes of 405:

- `fetch(url)` or `curl` actually sends `GET` while the API only defines `POST`.
- HTML forms default to GET, and `method="post"` cannot directly emit `PUT`.
- SDK/HTTP client picks the wrong verb.
- A redirect chain causes the final request to use a different method than expected.
- Gateway/WAF blocks `PATCH`, `DELETE`, or `OPTIONS`.
- The route has a class-level prefix differing from documentation.
- Browser preflight `OPTIONS` is blocked by security/proxy.

Do not advise "changing `@GetMapping` to `@RequestMapping` allowing all methods" just to silence 405. GET has different safe/idempotent semantics from POST; opening the wrong method can introduce security and caching bugs.

## 6. The `Allow` Header Is an Important Hint for 405

A response may include:

```http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD
```

Per HTTP semantics, a 405 response should advertise supported methods for the target resource via `Allow`. Spring MVC/WebFlux normally populates this from mappings. However, **do not depend** on byte-exact ordering/content because frameworks may handle `HEAD`/`OPTIONS` automatically and proxies may add/modify headers.

For instance, if a client sends `GET /api/products` when only `POST /api/products` exists, `Allow` can mention `POST`. `Allow` is a clue that the path was handled by **a mapping with another method**, not proof that the controller you expected actually ran.

When `Allow` looks surprising, inspect all actual mappings, wildcard routes, filter/router ordering, and ingress rewrites. Never let a frontend infer from `Allow` that the user is authorized to invoke every listed method; `Allow` is not authorization.

## 7. `HEAD` and `OPTIONS` Behave Differently from Other Methods

Spring Framework 6.1 supports HTTP `HEAD` for `@GetMapping` under standard behavior. `HEAD` headers match GET, **without a response body**. Thus:

```bash
curl -I http://127.0.0.1:8080/api/products/p1
```

is normally not a 405 test case just because the controller omits `@HeadMapping`.

Similarly, Spring MVC/WebFlux handles HTTP `OPTIONS` automatically, typically returning `Allow` when a route matches. A browser CORS preflight is a **special `OPTIONS` request** carrying `Origin` and `Access-Control-Request-Method`, sometimes blocked by a reverse proxy or Spring Security before reaching the controller.

If a browser sends a cross-origin JSON POST, first verify **whether `OPTIONS` succeeded**, before analyzing whether POST returned 405/406/415. Do not add `@PostMapping` to fix a preflight `OPTIONS` policy issue.

## 8. How Does 405 Differ from 404?

In the demo:

```text
GET  /api/products/p1 -> matching GET route, handler can return 200
POST /api/products/p1 -> path has GET but no POST, typically 405
GET  /api/unknown     -> no path mapping, typically 404
```

Yet HTTP status is not an infallible test for "right URL": the request might be hitting **an API gateway** or **another wildcard handler**, with 405/404 emitted there. An authenticated system might intentionally return 404 to avoid leaking resource existence.

To distinguish them, log the matched route template, service/instance version, and normalized correlation ID; do not log full URLs if paths/queries contain PII, credentials, or signed tokens.

## 9. Watch Out for `curl -d` and Redirects When Investigating 405

The command:

```bash
curl -d '{"name":"Pen"}' http://127.0.0.1:8080/api/products
```

sends **POST** by default, even without `-X POST`. Someone testing GET who accidentally leaves `-d` can trigger 405 due to the method change.

Conversely:

```bash
curl -i http://127.0.0.1:8080/api/products
```

sends GET. To reproduce explicitly:

```bash
curl -i -X GET http://127.0.0.1:8080/api/products
curl -i -X POST http://127.0.0.1:8080/api/products
```

Watch HTTP redirects as well: clients can convert POST to GET when following `301`/`302` in some cases, whereas `307`/`308` preserve the method under HTTP semantics. When debugging, use a verbose trace **with credentials stripped** or the browser Network tab; do not look solely at the final URL after redirects.

## 10. 415: Server Rejects the Request Body's Media Type

Controller:

```java
@PostMapping(
    path = "/api/products",
    consumes = MediaType.APPLICATION_JSON_VALUE)
public ProductView create(@RequestBody CreateProductRequest input) {
    return new ProductView("p1", input.name());
}
```

Client sends:

```http
POST /api/products HTTP/1.1
Content-Type: text/plain
Accept: application/json

{"name":"Pen"}
```

The body looks like JSON, yet the header says `text/plain`. `consumes=application/json` rejects that input type at mapping time. Returning **415 Unsupported Media Type** is appropriate.

Fix it by sending the **right `Content-Type`** with valid JSON. If clients genuinely need to send `text/plain`, the API needs **a separate representation/handler** with tests, rather than deleting `consumes` to accept every body format.

## 11. `consumes` and Request Decoders Are Two Validation Layers

`consumes` constrains routing:

```java
@PostMapping(
    path = "/api/products",
    consumes = MediaType.APPLICATION_JSON_VALUE)
```

Once the method is chosen, `@RequestBody` also requires a Spring `HttpMessageConverter` (MVC) or `HttpMessageReader` (WebFlux) compatible with the input type. Scenarios:

1. Header `Content-Type: text/plain`, mapping only accepts JSON → **415** during matching.
2. Mapping does not constrain `consumes`, yet no converter can read the body for the parameter type → can also be **415**.
3. Header and converter match, yet body `{"name":` is malformed → typically **400**.
4. Valid JSON body yet DTO validation fails → typically 400 with Bean Validation or the API contract's status.
5. Body too large → can be 413 or another status from proxy/server/codec limits.
6. Invalid charset/parameters → determine whether failure is in media matching or decoding; do not assume every case is 415.

`@RequestBody(required=true)` does not replace `consumes`. A missing body can cause 400 even with the right JSON `Content-Type`. Conversely, a valid media type does not guarantee the JSON parser or business validation succeeds.

## 12. Missing `Content-Type`, Charsets, and Vendor JSON

In a JSON API:

```http
Content-Type: application/json
```

and:

```http
Content-Type: application/json;charset=UTF-8
```

are normally both compatible with `consumes="application/json"` in Spring Framework 6.1. Spring evaluates media type parameters and compatibility rather than doing a naive `String.equals("application/json")`.

If a request carries a JSON body with **no `Content-Type`**, a JSON-only API can reject it with 415. Do not rely on the server guessing JSON from a leading `{`.

A vendor type such as:

```http
Content-Type: application/vnd.example.product+json
```

may be supported by a Jackson converter via `application/*+json`, yet **that does not guarantee** `@PostMapping(consumes="application/json")` matches the vendor media type. If the API contracts vendor JSON, declare `consumes` explicitly and test mapping **together with the converter**.

Do not use `consumes="!text/plain"` to inadvertently accept everything except text; whitelisting media types per business contract is far safer to control.

## 13. `curl -d` Does Not Send JSON `Content-Type` by Default

Common mistake:

```bash
curl -i \
  -d '{"name":"Pen"}' \
  http://127.0.0.1:8080/api/products
```

Even though the body looks like JSON, curl defaults to `Content-Type: application/x-www-form-urlencoded`. On a JSON-only controller, 415 is the predictable outcome.

Fix:

```bash
curl -i \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"name":"Pen"}' \
  http://127.0.0.1:8080/api/products
```

On curl versions supporting `--json`:

```bash
curl -i --json '{"name":"Pen"}' \
  http://127.0.0.1:8080/api/products
```

`--json` sends the body and sets the JSON headers; check `curl --version` on your CI runner. Do not assume `-d`/`--data-raw` and `--json` share the same default headers.

## 14. Multipart and Form Data Are Different Input Types from JSON

| Client body | Typical `Content-Type` | Appropriate binding |
| --- | --- | --- |
| JSON | `application/json` | `@RequestBody SomeDto` with Jackson |
| Text | `text/plain` | `@RequestBody String` |
| HTML form | `application/x-www-form-urlencoded` | `@RequestParam`, `@ModelAttribute` in MVC |
| Multipart | `multipart/form-data; boundary=...` | `MultipartFile`, `@RequestPart` MVC; `FilePart` WebFlux |
| XML | `application/xml` | XML codec/converter and supported model |
| Binary | `application/octet-stream` | Byte array/stream/`DataBuffer` per stack |

A `@PostMapping(consumes="application/json")` endpoint will not read a browser `application/x-www-form-urlencoded` form. If the app needs forms, design a separate handler and matching input binding.

For multipart:

```bash
curl -i -F 'file=@sample.txt' \
  http://127.0.0.1:8080/api/uploads
```

`curl -F` generates the boundary. **Do not** manually set `Content-Type: multipart/form-data` without a boundary. If uploads hit 415/400, inspect `consumes` mapping, multipart codec, boundary, max size, and `@RequestPart` name. Not all multipart parsing errors are 415.

## 15. 406: Server Cannot Produce a Response Matching `Accept`

A JSON-only endpoint:

```java
@GetMapping(
    path = "/api/products/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE)
public ProductView get(@PathVariable String id) {
    return new ProductView(id, "Demo item");
}
```

Client sends:

```http
GET /api/products/p1 HTTP/1.1
Accept: application/xml
```

The client wants XML only, while the mapping advertises JSON only; Spring can return **406 Not Acceptable**. This is **output negotiation**, not a request `Content-Type` issue: a GET request may have no body at all.

If the product genuinely supports JSON only, fix the client to send:

```http
Accept: application/json
```

Do not enable XML output just to make a misconfigured Postman call succeed. If clients genuinely require XML, you must build XML representations, codecs/converters, models, and compatibility tests.

## 16. `produces` Differs from Installing a Message Converter

Example:

```java
@GetMapping(
    path = "/api/products/{id}",
    produces = {"application/json", "application/xml"})
```

only states that the mapping **can be selected** when the client accepts either media type. It **does not install Jackson XML** or guarantee that the Java object serializes to XML.

To produce real `application/xml`, you need an output converter/codec and compatible DTO mapping depending on your Spring stack. Otherwise writing can fail with `406`, conversion errors, or `500` after handler selection. Therefore, **do not claim every response-writing failure is 406**.

Similarly, in MVC `MappingJackson2HttpMessageConverter` writes JSON when supported; Spring WebFlux uses `HttpMessageWriter`. Do not copy MVC converter config into WebFlux expecting identical writer types.

## 17. `Accept` Wildcards and Quality Values (`q`)

The `Accept` header can list multiple representations:

```http
Accept: application/json
Accept: application/json, text/plain;q=0.5
Accept: application/*;q=0.9, text/plain;q=0.2
Accept: */*
```

`*/*` in the example represents the wildcard for **any media type**, rendered in valid HTTP syntax in the saved article.

Quality factor `q` normally ranges in `[0,1]`, with `q=0` meaning **not acceptable** for that representation. Spring evaluates compatibility, specificity, and write capability, rather than reading only the first entry.

For a JSON-only endpoint:

```text
Accept: application/json      -> may succeed
Accept: application/*         -> may succeed
Accept: */*             -> may succeed
Accept: application/xml       -> 406 when no XML representation exists
```

If a browser client sends `Accept: text/html`, a JSON-only endpoint can return 406; do not confuse that with `/error` rendering an HTML error page, because **normal responses** and **error rendering** negotiate separately.

`Accept-Encoding: gzip, br` controls compression/content coding, not JSON/XML media type negotiation. Changing gzip will not fix a 406 caused by `Accept: application/xml`.

## 18. `consumes`/`produces` on Class vs. Method: Watch Overrides

Spring Framework allows:

```java
@RestController
@RequestMapping(
    path = "/api",
    consumes = "application/json",
    produces = "application/json")
class ExampleController {
    @PostMapping(path = "/plain",
        consumes = "text/plain",
        produces = "text/plain")
    String plain(@RequestBody String value) {
        return value;
    }
}
```

This is an **integration snippet** requiring imports and package context. For `consumes` and `produces`, method-level declarations **override** class-level conditions rather than intersecting the two lists.

Checklist when reading code:

- Is there a `@RequestMapping` annotation on the class or an implemented interface?
- Does `@GetMapping`/`@PostMapping` on the method override `consumes`/`produces`?
- Are there `headers="content-type=..."` or `params=...` conditions adding constraints?
- Are there two `@RequestMapping` annotations on one method? Spring recommends **not placing multiple mapping annotations on the same element** because only one may take effect.
- Does `spring.mvc.contentnegotiation.*`/`WebMvcConfigurer` or a custom codec alter behavior?

Prefer `consumes`/`produces` over manual `headers="Content-Type=..."` conditions so you get the framework's media type compatibility and negotiation logic.

## 19. MVC Demo Code: Project and Dependencies

This app reproduces 405, 406, and 415 separately on routes with explicit contracts. The sample **has no database or Spring Security** and binds loopback only to avoid misuse as a public API.

```text
build.gradle
src/main/java/com/example/httpcodes/
    HttpCodesApplication.java
    CreateItemRequest.java
    ItemView.java
    ItemController.java
src/main/resources/application.properties
src/test/java/com/example/httpcodes/
    HttpCodesMvcTest.java
    HttpCodesLiveTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The Gradle Wrapper must be generated with a Gradle version supporting Java 21; Spring Initializr can scaffold it. `spring-boot-starter-web` provides MVC, embedded Tomcat, and Jackson JSON in default setups; `starter-test` brings MockMvc/JUnit Jupiter/AssertJ.

## 20. Main Class and Request/Response DTOs

**`HttpCodesApplication.java`:**

```java
package com.example.httpcodes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpCodesApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpCodesApplication.class, args);
    }
}
```

**`CreateItemRequest.java`:**

```java
package com.example.httpcodes;

public record CreateItemRequest(String name) {
}
```

**`ItemView.java`:**

```java
package com.example.httpcodes;

public record ItemView(String id, String name) {
}
```

Java records expose default `name()`/`id()` accessors and Jackson in Spring Boot 3.3 binds/serializes them. **Records do not validate business data automatically**: `String name` can still be `null` if a client omits the field and Bean Validation is not enabled. This article focuses on HTTP contracts; real validation should add `@Valid`, constraints, and dedicated tests.

## 21. Controller: One JSON GET, One JSON POST, and One Text POST

**`ItemController.java`:**

```java
package com.example.httpcodes;

import java.util.Locale;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ItemController {

    @GetMapping(
        path = "/api/items/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ItemView get(@PathVariable("id") String id) {
        return new ItemView(id, "Demo item");
    }

    @PostMapping(
        path = "/api/items",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ItemView> create(
            @RequestBody CreateItemRequest input) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new ItemView("i1", input.name()));
    }

    @PostMapping(
        path = "/api/text/upper",
        consumes = MediaType.TEXT_PLAIN_VALUE,
        produces = MediaType.TEXT_PLAIN_VALUE)
    public String upper(@RequestBody String text) {
        return text.toUpperCase(Locale.ROOT);
    }
}
```

Design notes:

- `GET /api/items/i1` produces JSON; `Accept: application/xml` triggers 406.
- `GET /api/items` has no GET mapping while `POST /api/items` exists; used to reproduce 405.
- `POST /api/items` accepts JSON only; `Content-Type: text/plain` triggers 415.
- `POST /api/text/upper` demonstrates valid text input/output, avoiding the misconception that every endpoint must accept JSON.

`create()` returns a fixed ID without persisting to a DB. `GET /api/items/i1` returns a fixed demo name even after posting a different item name; **this is a stateless test app**, not a persistence example.

## 22. Local Configuration and Running the HTTP Server

**`src/main/resources/application.properties`:**

```properties
server.address=127.0.0.1
server.port=8080
server.error.include-message=never
server.error.include-stacktrace=never
server.error.include-binding-errors=never
```

Run:

```bash
./gradlew bootRun
```

There is no Security starter in the demo, so requests require no credentials; never deploy an unauthenticated app directly onto the Internet. To test 405/406/415 cleanly, the curl commands below introduce **only one broken dimension** per test.

## 23. 200/201 Baseline Before Reproducing Errors

Valid GET:

```bash
curl -i \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/api/items/i1
```

Expect HTTP `200` and logical JSON body:

```json
{"id":"i1","name":"Demo item"}
```

Valid POST:

```bash
curl -i \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"name":"Pen"}' \
  http://127.0.0.1:8080/api/items
```

Expect HTTP `201 Created`, JSON body:

```json
{"id":"i1","name":"Pen"}
```

Headers and whitespace can vary by runtime; **do not assert the entire raw HTTP response**. Check status, compatible content type, and JSON field values.

## 24. Reproduce 405 by Changing Method, Keeping Path

```bash
curl -i \
  -X GET \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/api/items
```

`/api/items` has only a POST mapping → expect `405 Method Not Allowed`. The `Allow` header should reflect supported methods; do not assert exact ordering or the full raw header string.

Comparison control:

```bash
curl -i \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"name":"Pen"}' \
  http://127.0.0.1:8080/api/items
```

Changing only the method (and supplying the required body) → succeeds. With the wrong method, the create handler is never invoked; do not try to "fix 405" by relaxing Spring Security for all methods.

## 25. Reproduce 415 by Changing Request `Content-Type`

```bash
curl -i \
  -H 'Content-Type: text/plain' \
  -H 'Accept: application/json' \
  --data '{"name":"Pen"}' \
  http://127.0.0.1:8080/api/items
```

Expect `415 Unsupported Media Type`. Although the body has JSON braces, the server **honors the request's `Content-Type` contract** rather than silently treating arbitrary text as JSON.

Comparison changing only:

```http
Content-Type: application/json
```

allows the same body to be read into `CreateItemRequest`. This isolates input media negotiation from output negotiation.

Sending `Content-Type: application/json` to `/api/text/upper` can also return 415 on that text-only endpoint. `consumes` conditions are **per handler**, not a single global Spring Boot property.

## 26. Reproduce 406 by Changing Response `Accept`

```bash
curl -i \
  -H 'Accept: application/xml' \
  http://127.0.0.1:8080/api/items/i1
```

Expect `406 Not Acceptable`, because the endpoint only declares `produces=application/json`. **There is no request body**, so `Content-Type` is not involved in this request.

Comparison:

```bash
curl -i \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/api/items/i1
```

returns JSON.

With POST, you can also send **valid input** `Content-Type: application/json` alongside **unsupported output** `Accept: application/xml`; the expected outcome is 406. However, in clean experiments, GET isolates 406 most simply.

## 27. Malformed JSON Returns 400, Not 415 by Default

```bash
curl -i \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"name":' \
  http://127.0.0.1:8080/api/items
```

The mapping accepts JSON, yet the parser cannot parse malformed JSON. Spring MVC typically raises `HttpMessageNotReadableException`, returning `400 Bad Request`.

A syntactically valid JSON body violating constraints (empty/missing `name`) is yet another **validation issue** requiring Bean Validation or explicit business checks. `@RequestBody` also handles missing bodies (`required=true`), typically returning 400. Never assume 415 covers all input errors.

If the client declares `application/xml` while sending a JSON body, 415 occurs **before** Jackson JSON ever gets a chance to parse. When testing, keep other factors valid so you measure the right layer.

## 28. `MockMvc`: Testing Each Code Independently Without TCP

**`src/test/java/com/example/httpcodes/HttpCodesMvcTest.java`:**

```java
package com.example.httpcodes;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(ItemController.class)
class HttpCodesMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void jsonGetWorks() throws Exception {
        mvc.perform(get("/api/items/i1")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value("i1"))
                .andExpect(jsonPath("$.name").value("Demo item"));
    }

    @Test
    void wrongMethodIs405() throws Exception {
        mvc.perform(get("/api/items")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isMethodNotAllowed())
                .andExpect(header().string(
                        HttpHeaders.ALLOW, containsString("POST")));
    }

    @Test
    void wrongRequestContentTypeIs415() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.TEXT_PLAIN)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Pen\"}"))
                .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void wrongResponseAcceptIs406() throws Exception {
        mvc.perform(get("/api/items/i1")
                        .accept(MediaType.APPLICATION_XML))
                .andExpect(status().isNotAcceptable());
    }

    @Test
    void validPostReturns201Json() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Pen\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name").value("Pen"));
    }

    @Test
    void malformedJsonReturns400() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("{\"name\":"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void correctPlainTextWorks() throws Exception {
        mvc.perform(post("/api/text/upper")
                        .contentType(MediaType.TEXT_PLAIN)
                        .accept(MediaType.TEXT_PLAIN)
                        .content("hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("HELLO"));
    }
}
```

Run:

```bash
./gradlew test
```

**Expectation:** all seven tests PASS when dependencies, JDK, and sources match. `MockMvc` exercises Spring MVC handler dispatch and message converters, yet **does not open a TCP socket**, so it does not prove gateways, Tomcat TLS, or browser CORS work.

Check `Allow` using `containsString("POST")` rather than matching the entire header string, because the framework may include `OPTIONS` handling or vary ordering. Do not assert exact raw text of 405/406/415 error bodies since Spring Boot error formatting can vary across profiles.

## 29. Real HTTP Integration Test with `RANDOM_PORT`

**`src/test/java/com/example/httpcodes/HttpCodesLiveTest.java`:**

```java
package com.example.httpcodes;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "server.address=127.0.0.1")
class HttpCodesLiveTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate client;

    @Test
    void callsCorrectEmbeddedServer() {
        assertThat(port).isBetween(1, 65535);

        ResponseEntity<String> result =
                client.getForEntity("/api/items/i1", String.class);
        assertThat(result.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(result.getBody()).contains("\"id\":\"i1\"");
    }

    @Test
    void methodMismatchRemains405OverHttp() {
        ResponseEntity<String> result =
                client.getForEntity("/api/items", String.class);
        assertThat(result.getStatusCode())
                .isEqualTo(HttpStatus.METHOD_NOT_ALLOWED);
    }
}
```

`@LocalServerPort` injects the **OS-assigned** port, and `TestRestTemplate` in Boot real-server tests accepts relative URLs. Do not hardcode `localhost:8080` when running `RANDOM_PORT`: the test might accidentally hit another process.

Live-network tests catch network/Servlet filter differences. To verify a real ingress/gateway, run an end-to-end setup through the proxy rather than only hitting embedded localhost.

## 30. Spring MVC Exception Classes to Pinpoint the Failing Layer

| Common Spring MVC Exception | Associated status | Scope |
| --- | --- | --- |
| `HttpRequestMethodNotSupportedException` | 405 | HTTP method mismatch |
| `HttpMediaTypeNotSupportedException` | 415 | Input `Content-Type` unsupported |
| `HttpMediaTypeNotAcceptableException` | 406 | Output `Accept`/representation incompatible |
| `HttpMessageNotReadableException` | 400 | JSON/body parse or read failure |
| `MethodArgumentNotValidException` | 400 under default validation | `@Valid` DTO rejected |
| `MissingServletRequestParameterException` | 400 | Required parameter missing |
| `HttpMessageNotWritableException` | Potentially 500 | Output codec failed to write object |
| `NoHandlerFoundException`/`NoResourceFoundException` | 404 per flow | No handler/resource found |

A single status does not have only **one** possible exception source. `@RestControllerAdvice`, `ResponseEntityExceptionHandler`, `DefaultHandlerExceptionResolver`, Security, and `/error` can all shape the response. If a custom handler catches all `Exception`s and returns 500, you can **break 405/406/415**.

When investigating, identify the exception type and mapping condition **without logging raw request bodies or `Authorization` headers**.

## 31. `ProblemDetail`: Standardizing Error Bodies While Preserving HTTP Semantics

Spring Framework 6 supports RFC 9457 `ProblemDetail`. In Spring Boot 3.3, enable it for MVC via:

```properties
spring.mvc.problemdetails.enabled=true
```

For a WebFlux project, Boot provides the corresponding setting:

```properties
spring.webflux.problemdetails.enabled=true
```

A 415 response can look like:

```json
{
  "type": "about:blank",
  "title": "Unsupported Media Type",
  "status": 415,
  "detail": "The request media type is not supported"
}
```

**Do not treat the JSON above as a fixed output**: actual `title`/`detail`/`instance` and error media type depend on exception resolvers, localization, Boot config, and the client's `Accept` header. Enabling `ProblemDetail` **changes the error representation**, not whether a wrong method or media type becomes valid.

When writing custom `@ControllerAdvice`:

- Preserve the proper HTTP status and the `Allow` header for 405.
- Respect content negotiation and relevant headers.
- Do not catch all framework exceptions and turn them into 500.
- Do not expose stack traces, query secrets, or credentials inside `detail`.
- Verify whether frontends/clients parse `application/problem+json` or only `application/json`.

## 32. WebFlux Differs from MVC in Read/Write Layer, Not in 405/406/415 Semantics

Spring WebFlux uses reactive `DispatcherHandler`, `HttpMessageReader`, and `HttpMessageWriter`, instead of MVC `DispatcherServlet` and `HttpMessageConverter`. Yet the contract is the same:

| Aspect | MVC | WebFlux |
| --- | --- | --- |
| Method mismatch | `@GetMapping` / `@PostMapping` | Same |
| `Content-Type`/input | `consumes` + converter | `consumes` + reader |
| `Accept`/output | `produces` + converter | `produces` + writer |
| Typical 405 | `HttpRequestMethodNotSupportedException` | `MethodNotAllowedException` |
| Typical 415 | `HttpMediaTypeNotSupportedException` | `UnsupportedMediaTypeStatusException` |
| Typical 406 | `HttpMediaTypeNotAcceptableException` | `NotAcceptableStatusException` |
| Slice test | `@WebMvcTest`/MockMvc | `@WebFluxTest`/WebTestClient |

Exception classes are framework internals, **not a public wire contract**. Clients should rely only on HTTP status, stable error codes, and documented response media types.

If a server includes both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Boot normally prioritizes the MVC Servlet app type. A controller returning `Mono` does not prove runtime is WebFlux; inspect the actual application context and dependencies.

## 33. Separate WebFlux Project: Gradle and Files

Create a separate project—do not mix it with the MVC demo:

```text
build.gradle
src/main/java/com/example/fluxerrors/
  FluxErrorsApplication.java
  BookIn.java
  BookOut.java
  BookController.java
src/test/java/com/example/fluxerrors/
  BookWebFluxTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories { mavenCentral() }

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') { useJUnitPlatform() }
```

Do not add `spring-boot-starter-web` to runtime when testing WebFlux's reactive web server.

## 34. WebFlux Controller: Same Contract, Reactive Return Types

**`FluxErrorsApplication.java`:**

```java
package com.example.fluxerrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FluxErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(FluxErrorsApplication.class, args);
    }
}
```

**`BookIn.java`:**

```java
package com.example.fluxerrors;

public record BookIn(String title) {
}
```

**`BookOut.java`:**

```java
package com.example.fluxerrors;

public record BookOut(String id, String title) {
}
```

**`BookController.java`:**

```java
package com.example.fluxerrors;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class BookController {

    @GetMapping(path = "/api/books/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<BookOut> get(@PathVariable("id") String id) {
        return Mono.just(new BookOut(id, "Demo book"));
    }

    @PostMapping(path = "/api/books",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<BookOut>> create(
            @RequestBody Mono<BookIn> input) {
        return input.map(book -> ResponseEntity.status(
                HttpStatus.CREATED)
                .body(new BookOut("b1", book.title())));
    }
}
```

`Mono` is a reactive result; it does not fix method or media type mismatches. `@RequestBody Mono<BookIn>` is decoded by WebFlux codecs when the request matches.

## 35. WebFlux Tests Using `@WebFluxTest` + `WebTestClient`

**`BookWebFluxTest.java`:**

```java
package com.example.fluxerrors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(BookController.class)
class BookWebFluxTest {

    @Autowired
    WebTestClient client;

    @Test
    void methodMismatchIs405() {
        client.get()
                .uri("/api/books")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isEqualTo(HttpStatus.METHOD_NOT_ALLOWED);
    }

    @Test
    void acceptMismatchIs406() {
        client.get()
                .uri("/api/books/b1")
                .accept(MediaType.APPLICATION_XML)
                .exchange()
                .expectStatus().isEqualTo(HttpStatus.NOT_ACCEPTABLE);
    }

    @Test
    void contentTypeMismatchIs415() {
        client.post()
                .uri("/api/books")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue("{\"title\":\"Spring\"}")
                .exchange()
                .expectStatus().isEqualTo(HttpStatus.UNSUPPORTED_MEDIA_TYPE);
    }

    @Test
    void correctJsonCreatesBook() {
        client.post()
                .uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue("{\"title\":\"Spring\"}")
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.title").isEqualTo("Spring");
    }
}
```

`@WebFluxTest` creates a mock web layer without necessarily opening a Netty socket. To test real HTTP runtime, use `@SpringBootTest(RANDOM_PORT)` with an auto-bound `WebTestClient` or JDK `HttpClient`. Never test WebFlux with `@WebMvcTest` and conclude the reactive stack works.

## 36. Spring `WebClient`/`RestClient` Clients Must Also Honor the Media Contract

A `WebClient` call prone to 415:

```java
webClient.post()
        .uri("/api/books")
        .contentType(MediaType.TEXT_PLAIN)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue("{\"title\":\"Spring\"}")
        .retrieve()
        .bodyToMono(String.class);
```

**Integration snippet**, requiring a `WebClient` bean/`baseUrl` and imports. The body looks like JSON yet the header declares `text/plain`. Better:

```java
webClient.post()
        .uri("/api/books")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(new BookIn("Spring"))
        .retrieve()
        .bodyToMono(BookOut.class);
```

`WebClient`'s `retrieve()` emits error signals by default for many HTTP 4xx/5xx responses. If client code only logs `onError`, inspect the **actual response status and sanitized headers** instead of discarding error details or retrying the exact invalid payload endlessly.

`RestClient`, `RestTemplate`, OkHttp, and JDK `HttpClient` must also send the right method/headers; they do not automatically assume a `"{...}"` string is JSON.

## 37. Browser `fetch`, HTML Forms, and CORS

Frontend wrong method:

```javascript
fetch("/api/items");
```

Defaults to GET; if the endpoint only accepts POST, it can return 405.

Stringified body without explicit headers:

```javascript
fetch("/api/items", {
  method: "POST",
  body: JSON.stringify({name: "Pen"})
});
```

Do not rely on browser-inferred media type headers. Specify explicitly:

```javascript
fetch("/api/items", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Accept": "application/json"
  },
  body: JSON.stringify({name: "Pen"})
});
```

For cross-origin JSON requests, the browser may send an `OPTIONS` preflight before POST. If the preflight receives 403/405 from security/proxy, the POST request **may never even be sent**. Inspect every request in the Network tab. CORS is an origin-permission issue, not fixed by loosening `consumes`/`produces`.

HTML `<form method="post">` normally sends `form-urlencoded` unless multipart `enctype` is specified; a JSON-only `@RequestBody` will not automatically read HTML forms.

## 38. XML Config, Vendor JSON, and Converter Classpath

When an API truly needs:

```http
Accept: application/xml
```

the server must have matching JSON/XML representations—such as an XML converter, mapper, DTO annotations, and tests. Simply adding:

```java
@GetMapping(path = "/api/items/{id}",
        produces = {"application/json", "application/xml"})
```

does not install an XML converter. Check the dependency tree, Boot BOM, and actual response `Content-Type` and body.

For vendor JSON:

```http
Content-Type: application/vnd.example.product+json
Accept: application/vnd.example.product+json
```

a Jackson converter can read some `application/*+json` types, yet a **mapping** with `consumes="application/json"` does not automatically match every vendor type. If the API truly supports vendor JSON, declare the explicit input/output media types and test each converter. Do not open every `+json` suffix without reviewing the contract/version.

In `application/problem+json`, `problem+json` is an **error media type**; a client sending `Accept: application/problem+json` is not asking for a normal `application/json` business response.

## 39. Security and CORS Can Mask Expected 405/415 Responses

With Spring Security enabled:

- An unauthenticated request can receive `401`.
- Authenticated without sufficient permission can receive `403`.
- A cookie/session POST missing a CSRF token can receive `403`.
- A blocked `OPTIONS` preflight can make the browser report a CORS error even when the POST method/body contract is valid.

Security filters run before handler mapping. If a `MockMvc` 405 test suddenly returns 403 after adding Spring Security, **do not** fix it by disabling CSRF in production. Add Spring Security test dependencies, test user/CSRF properly per policy, and isolate mapping behavior. For stateless bearer-token REST APIs, design CSRF strategy around your authentication mechanism rather than applying one blanket recipe everywhere.

An API returning `Allow: POST` does not mean the caller is authorized to execute POST.

## 40. Gateways, Redirects, and Reverse Proxies: Pinpointing Which Layer Rejected

Actual path:

```text
Client -> CDN/WAF -> API Gateway -> Ingress -> Spring Boot
```

A 405 can happen because a gateway allows only GET/POST and blocks PATCH; a 415 can happen because a gateway rejects `application/octet-stream` before Spring ever sees it; a 406 can stem from proxy content negotiation or cached responses.

Checklist:

1. Identify which service/instance emitted the status—is there a trace ID or distinguishing response flag?
2. Verify the actual method/URI after redirects or path rewrites.
3. Compare `Content-Type` and `Accept` forwarded by the proxy against policy.
4. Check registered handler mappings in the exact deployed build/version.
5. Check whether default error body/headers come from the gateway or Boot.
6. Never disable the WAF just to make 415 vanish; check data contracts and security policy.

A passing localhost test does not prove the API passes through ingress. To confirm root cause, test the **same request** direct-to-app (when authorized) and through the proxy in a controlled environment.

## 41. Safe HTTP Observability When Hunting Contract Mismatches

A helpful structured log:

```json
{
  "event": "http_contract_mismatch",
  "method": "POST",
  "route": "/api/items",
  "status": 415,
  "requestMediaFamily": "text",
  "acceptMediaFamily": "json",
  "serviceVersion": "3.3-demo"
}
```

This is a **suggested format**, not printed by Spring Boot by default. Client-supplied `Content-Type`/`Accept` values can be overly long or unusual; normalize them into a **finite category** before using them as metrics tags.

Do not log:
- Bearer `Authorization`, `Cookie`, `Set-Cookie`, or API keys.
- Raw request/response bodies containing PII.
- Full paths/queries containing emails, codes, or signed URLs.
- Unsanitized user-controlled headers or unreviewed stack traces.

Logging method, route template, status, timing, correlation ID, and normalized content/accept categories suffices for most 405/406/415 investigations.

## 42. Symptoms and Root-Cause Investigation Hints

| Symptom | Suspected cause | Verification step |
| --- | --- | --- |
| POST endpoint yet seeing 405 | Client sent GET or proxy blocked POST | `curl -i -X POST`, `Allow`, gateway logs |
| `curl -d` JSON-looking returns 415 | Default `Content-Type` is `form-urlencoded` | Send `application/json` header |
| JSON `@RequestBody` yet XML returns 415 | `consumes`/reader does not accept XML | Input contract + converter |
| Browser asks for XML yet JSON API returns 406 | `Accept` is XML only | Fix `Accept` or add real XML output |
| Malformed JSON returns 400 | Jackson read/parse failure | Fix body; keep `Content-Type` |
| 405 only in browser | CORS `OPTIONS` or redirect | Network tab per request |
| 403 in MockMvc when expecting 415 | Spring Security/CSRF before mapping | Test auth/csrf |
| HTTP 415 after upgrade | Client headers/converter/classpath changed | Dependency diff, sanitized request capture |
| 406 after adding `produces=application/xml` | Missing XML writer | Test converter/output |
| 500 during response serialization | Encoder/DTO error | Stack/codec; do not call it 406 |
| `@PostMapping` on method doesn't work | Component scan, prefix, conditions/overlapping mappings | Inspect registered mappings |
| Local PASS, gateway FAIL | Gateway rewrite/media policy | Direct vs. proxied smoke test |

## 43. Debugging After Upgrading Spring Boot or Spring Framework

When upgrading from Boot 2.x to 3.x, check:

- Spring Framework 6.x, Java 17+, and Jakarta Servlet namespaces in MVC.
- `RequestMappingHandlerMapping` conditions, path pattern/trailing-slash differences.
- Body readers/writers and Jackson/codec dependencies managed by the Boot BOM.
- Custom `WebMvcConfigurer` content negotiation, `@ControllerAdvice`, and `ResponseEntityExceptionHandler`.
- Spring Security filter chain, CSRF/CORS before mapping.
- Whether `RestTemplate`/`RestClient`/`WebClient`/frontend SDKs changed default headers.
- Gateway routing/redirect behavior, `Content-Type` forwarding, and proxy caching.
- `ProblemDetail` enabled changing legacy JSON error bodies to `application/problem+json`.
- Test suites using real HTTP beyond `MockMvc`/WebFlux slices.

Do not assume "the upgrade turned 405 into 415" without comparing a **fixed request** (method/path/`Content-Type`/`Accept`/body) across versions. Maintain regression tests for 200/201, 400, 404, 405, 406, 415, and security cases per contract. The goal is to know **which condition changed**, not guess from status codes.

## 44. Practical Step-by-Step Diagnostic Workflow

1. **Record status** and timestamp/traceId; do not guess from error body text.
2. **Confirm who emitted the error:** gateway, security, Servlet/WebFlux router, or controller.
3. **Isolate method:** keep path and media types valid, try the method from API docs. For 405, inspect `Allow` if present.
4. **Isolate input media:** keep method, `Accept`, and body syntax valid; vary only `Content-Type`; check `consumes` and readers.
5. **Isolate output media:** keep method/input valid; vary only `Accept`; check `produces` and writers.
6. **Isolate syntax:** keep both media headers valid and send malformed JSON; confirm 400 vs. 415.
7. **Inspect mapping hierarchy:** class-level + method-level conditions, wildcard routes, interface annotations, handler ordering.
8. **Run local slice tests:** `@WebMvcTest`/`@WebFluxTest`; if they PASS while full HTTP FAILS, suspect filters/server/proxy.
9. **Test real HTTP:** `@SpringBootTest(RANDOM_PORT)` and a client without hardcoded 8080.
10. **Fix the right layer** and add regression tests; never open input/output/methods globally.
11. **Verify pre/post-deployment** through the real proxy and save sanitized evidence.

If multiple conditions are wrong simultaneously, split them into independent tests. `Content-Type: application/json` does not prove the body is valid; `Accept: application/json` does not prove the server has a converter for the Java return type; `@PostMapping` does not prove the client sent POST.

## 45. Review Questions

1. Why does 405 differ from 404 even on the same URL?
2. What is the `Allow` header in a 405 response used for?
3. Why is `HEAD` on `@GetMapping` usually handled even without `@HeadMapping`?
4. How does a CORS preflight `OPTIONS` differ from a business POST?
5. Why does body `{"name":"Pen"}` with header `text/plain` cause 415?
6. Which `Content-Type` does `curl -d` send by default?
7. Which header describes the request body, and which header describes the desired response format?
8. What can a JSON-only endpoint return when receiving `Accept: application/xml`?
9. With Jackson XML on the classpath yet `produces` set to JSON only, is an XML client guaranteed to succeed?
10. Malformed JSON with `Content-Type: application/json` usually yields what status?
11. How do method-level `consumes`/`produces` interact with class-level declarations?
12. Why shouldn't you test both the wrong method and wrong `Content-Type` simultaneously when verifying 405?
13. How should vendor `+json` be checked across mapping and converters?
14. How does `HttpMessageConverter` differ from WebFlux's `HttpMessageReader`/`Writer`?
15. Why can `fetch(url)` trigger 405 when the developer thinks it's a POST?
16. With Spring Security, can 403 appear before 415?
17. Why shouldn't `Authorization`/cookies/raw bodies be logged in production just to debug 415?
18. What happens if a custom `@ControllerAdvice` catches every `Exception` and returns 500?
19. When hitting 406, why shouldn't you just change `Accept-Encoding`?
20. How do you tell whether a 415 came from the gateway or from Spring Boot?
21. What issues can occur when upgrading Boot 2.x to 3.x even if method and URL stay unchanged?
22. Which test verifies a real HTTP socket beyond a mock dispatcher?
23. Why shouldn't you assert verbatim `ProblemDetail` error bodies across all releases?
24. When should a new media type be added to the API, and when should only the client be fixed?
25. Does an MVC app that adds WebFlux libraries solely for `WebClient` become a reactive web server?

**Exercise A:** Run the MVC demo. On the same route, send a valid request first; then vary method once, `Content-Type` once, and `Accept` once. Record statuses and `Allow` if present.

**Exercise B:** Run `HttpCodesMvcTest`, add a malformed-JSON test yielding 400, and compare with 415 on when failure occurs.

**Exercise C:** Enable `spring.mvc.problemdetails.enabled=true` in a test profile, compare status/`Allow` before and after, and check that clients parse the error media type properly.

**Exercise D:** Use the WebFlux demo, compare 405/406/415 with MVC inside `@WebFluxTest`; do not rely on Java exception class names as API contracts.

**Exercise E:** Place a reverse proxy in front of Spring Boot; test the same request via proxy and direct connection to tell where the error code originates.

**Exercise F:** Intentionally add a multipart or vendor JSON route, write explicit `consumes`, and test success/415/400 cases.

## 46. Conclusion and Reference Sources

Remember the trio:

```text
405 Method Not Allowed
    -> Check HTTP method, path/mapping, Allow

415 Unsupported Media Type
    -> Check request Content-Type, consumes, input decoder

406 Not Acceptable
    -> Check response Accept, produces, output writer
```

In Spring Boot, inspect the **actual request being sent**, understand `@RequestMapping` conditions, separate mapping from conversion, and prove behavior with `MockMvc`/`WebTestClient` plus a real HTTP test. During upgrades, inspect message converters/codecs, security, gateways, and error response formats rather than allowing every media type indiscriminately.

**Official documentation for cross-reference:**

- HTTP Semantics RFC 9110 — HTTP status 405/406/415, Accept, Content-Type, Allow: https://www.rfc-editor.org/rfc/rfc9110.html
- Spring Framework 6.1 — `RequestMapping` API (`consumes`/`produces`): https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/bind/annotation/RequestMapping.html
- Spring Framework — MVC mapping requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — WebFlux mapping requests: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html
- Spring Framework — MVC Message Converters: https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html
- Spring Framework — MVC Error Responses/`ProblemDetail`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Boot 3.3 — Servlet web and error handling: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Reactive web: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Security — CORS integration: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
