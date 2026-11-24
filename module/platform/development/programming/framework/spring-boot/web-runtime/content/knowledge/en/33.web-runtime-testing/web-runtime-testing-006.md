# Testing Mappings, Statuses, Headers, JSON, and Content Negotiation

**Module:** Spring Boot - web-runtime  
**Parent topic:** Web runtime testing

## 1. Problem Statement: Running Code Is Not Enough—The HTTP Contract Must Be Right

A Spring Boot REST controller can return the right data when a developer opens a browser yet still violate the HTTP contract in multiple ways: a slightly wrong URL mapping, a POST method accidentally handled as GET, returning 200 when 404 is needed, missing the `Location` header on 201, turning booleans into strings, or accepting `application/xml` even though the API only supports JSON.

An HTTP API is more than its body. The observable contract includes:

1. **Request mapping:** HTTP method, path, path variables, query parameters, headers, `consumes`, and `produces`.
2. **Status:** 200, 201, 204, 400, 401, 403, 404, 405, 406, 409, 415, 422, 500..., with proper semantics.
3. **Response headers:** `Content-Type`, `Location`, `Cache-Control`, `Vary`, `ETag`, `Allow`, security headers, or required custom headers.
4. **JSON representation:** field names, data types, nested objects, arrays, null, missing fields, serialization, and encoding.
5. **Content negotiation:** the difference between request **Accept** and **Content-Type**, picking the right representation, and rejecting unsupported ones.
6. **Correctness on the wire:** some behaviors can only be checked when a real HTTP server runs, not via MockMvc alone.

For example, a device resource API might have this contract:

~~~text
GET    /api/widgets/1         Accept: application/json
  -> 200 application/json, JSON object, Vary: Accept

GET    /api/widgets/1         Accept: text/plain
  -> 200 text/plain, plain text representation

GET    /api/widgets/1         Accept: application/xml
  -> 406 Not Acceptable

POST   /api/widgets           Content-Type: application/json
                               Accept: application/json
  -> 201 Created, Location: /api/widgets/{new-id}, JSON object

POST   /api/widgets           Content-Type: text/plain
  -> 415 Unsupported Media Type

POST   /api/widgets           Content-Type: application/json
                               malformed JSON
  -> 400 Bad Request

GET    /api/widgets/999       Accept: application/json
  -> 404 Not Found
~~~

**Lesson goal:** build and test this entire contract using **Spring Boot 3.3 / Java 17+**, utilizing **MockMvc**, **@WebMvcTest**, **@SpringBootTest**, **@AutoConfigureMockMvc**, **RANDOM_PORT**, JUnit 5, and Java `HttpClient`. Specifically, distinguish what a test slice can prove from what requires running real embedded Tomcat.

**Version note:** this demo uses **Spring Boot 3.3.13** so examples share APIs from the 3.3 branch. This is not a recommendation to pick 3.3 for new production projects; the 3.3 branch has reached end of open-source support. Production should use a currently maintained Spring Boot version, apply patches, and adjust imports/testing APIs if moving to a newer major branch.

## 2. Understanding Which Layer Is Under Test

Different testing layers do not offer identical capabilities:

| Approach | What Starts? | What It Can Verify | What It Does Not Automatically Prove |
| --- | --- | --- | --- |
| Unit test calling controller method | Java class + fake dependencies | Pure logic inside the method | Spring MVC handler mappings, converters, real HTTP status. |
| **MockMvc standaloneSetup** | Spring MVC test infrastructure around a specified controller | Mappings/converters configured for standalone | Full Boot auto-config, container, and real filters unless added. |
| **@WebMvcTest + MockMvc** | MVC slice containing controllers, MVC mappings, converters, selected advice/filters | Method/path, status, headers, JSON, media negotiation at the MVC layer | Embedded server socket/TLS/compression/HTTP2; all business beans. |
| **@SpringBootTest + @AutoConfigureMockMvc** | Full ApplicationContext, mocked servlet request/response | Web MVC + app auto-config + filters/beans in context | Network/server connector behavior. |
| **@SpringBootTest(RANDOM_PORT)** | Full context + real embedded HTTP server | Status/headers/body over network, serialization, server behavior | Public ingress/CDN behavior if tests bypass the proxy. |
| End-to-end through ingress | Gateway, TLS, proxy, service deployment | Public URL, forwarding, auth/routing/caching | Cannot easily isolate failures by individual layer. |

**MockMvc does not use real TCP sockets.** It sends a **`MockHttpServletRequest`** through Spring MVC and receives a **`MockHttpServletResponse`**. Thus it is very effective for verifying controller contracts, yet cannot replace testing compression thresholds, connector timeouts, HTTP/2 framing, TLS, reverse proxies, or shutdown behavior.

**@WebMvcTest** scans a subset of web-layer beans and does not automatically load every **`@Service`**, **`@Repository`**, or app configuration. If a controller depends on a service, the slice test needs fakes/mocks such as **`@MockBean`** in Spring Boot 3.3; do not autowire a real database just to test a 404 status. On newer Boot versions, the mock bean API may change; check documentation for your version.

**@SpringBootTest** defaults to `webEnvironment=MOCK` and does not open an HTTP listener automatically. To test over sockets, choose **RANDOM_PORT**. To use MockMvc in the full context, add **@AutoConfigureMockMvc**.

## 3. Mapping: Conditions Spring MVC Uses to Select a Handler

A Spring MVC handler may declare:

~~~java
@GetMapping(
    path = "/api/widgets/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE)
public WidgetDto find(@PathVariable long id) {
    // Domain lookup and return.
    return someWidget;
}
~~~

The code above is an **illustrative snippet, not a standalone program**. The runnable example section includes the complete controller.

Spring MVC evaluates a set of conditions to select a handler:

- **HTTP method:** GET/POST/PUT/PATCH/DELETE; the wrong method usually yields **405 Method Not Allowed** when the URL matches a mapping.
- **Path:** class-level + method-level `@RequestMapping`; path variables; nested routes; servlet context path.
- **params:** e.g., `@GetMapping(params="active=true")` only matches requests meeting the query condition.
- **headers:** can require a specific request header to be present/match a value.
- **consumes:** restricts media types read from the **request Content-Type**, important for POST/PUT/PATCH with bodies.
- **produces:** restricts response media types a handler can produce, selected based on **request Accept**.
- **Argument conversion:** converting string path/query to long/enum/date can fail and lead to 400.
- **Message conversion:** Jackson reads/writes JSON; an unsuitable converter can raise 400/415/406 or server errors depending on cause.

**Testing mappings is not just checking whether a URI exists.** You need to verify the right method, path, Accept, consumes, and rejection cases. For instance, GET and POST on the same URL have completely different contracts.

### 3.1. Content-Type and Accept Are Not Synonymous

| Header | Direction | Meaning |
| --- | --- | --- |
| **Content-Type** | Request sent to server | Media type of the current **request body**; e.g., `application/json`. |
| **Accept** | Request sent to server | Which **response media types** the client accepts; e.g., `application/json` or `text/plain`. |
| Response **Content-Type** | Returned by server | Actual media type of the chosen response body. |
| **Vary: Accept** | Response/caching | Caches must account for Accept when representations differ by this header. |

A request may look like:

~~~http
POST /api/widgets HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json

{"name":"Spring Tests"}
~~~

If the client sends **Accept: text/plain** while the POST endpoint only offers a JSON response, the server can return **406**. If the client sends **Content-Type: text/plain** while the endpoint only consumes JSON, it can return **415**.

**Do not require Content-Type on GET when sending no body**, and do not write tests expecting GET to require `Content-Type: application/json` on the request just to return JSON. On ordinary GETs, **Accept** is the important condition for response format.

### 3.2. 406 and 415 Differ

**406 Not Acceptable:** the server has no representation matching the Accept header requested by the client, based on content negotiation/`produces` config.  
**415 Unsupported Media Type:** the server does not accept the request entity media type declared in Content-Type per `consumes` or converter support.

**400 Bad Request** can occur when Content-Type is properly `application/json` yet the body is invalid JSON, field conversion fails, or validation rejects it.

**405 Method Not Allowed** occurs when a URL has a mapping, but the HTTP method is unsupported. **404** means no resource/route per endpoint semantics; a GET to a valid URL whose id does not exist can intentionally return 404 from the controller.

Status codes can be handled via **@ControllerAdvice**, custom exception handlers, or proxies; the demo uses Spring MVC defaults and `ResponseEntity` for clarity.

## 4. When Should Exact JSON Be Expected?

Do not equate “a response has a string that looks like JSON” with “a valid JSON HTTP response.” Verify all of these:

1. **Content-Type**: the app actually returns **`application/json`**, not `text/plain` containing JSON braces.
2. **Parseable JSON** using Jackson/a JSON parser.
3. **Property names** match: `id`/`name`/`active` differs from `ID`/`Name`/`activeFlag`.
4. **Types** match: `id` number, `active` boolean, `name` string; do not accept `"1"` instead of `1` if the contract specifies number.
5. **Values** match, including Unicode and whitespace where required.
6. **Field presence/absence**: a missing field differs from null or an empty string.
7. **Array/nested structures**: element count, order when meaningful, relationships.
8. **No leaked internal fields**: `passwordHash`, `internalMemo`, credentials; test negative assertions.
9. **Error representation**: 400/404/500 may have different error JSON; do not assume all errors match success DTOs.

JSON object member order is rarely part of the contract. Do not compare raw JSON strings expecting fixed field order or whitespace; use **jsonPath**, JSON parsing, or **content().json(...)** with suitable strictness.

**Jackson with Java records:** Spring Boot 3.3 uses Jackson compatible with Java 17, serializing **`record WidgetDto(long id, String name, boolean active)`** into fields `id`/`name`/`active`. If the project uses a naming strategy (`snake_case`), JsonViews, custom modules, or `@JsonProperty`, test the actual serialized data rather than judging by Java field names alone.

## 5. Runnable Spring Boot 3.3 / Java 17+ Project

We build a **Widget** API with two representations at the same URL:

- **GET /api/widgets/{id}** with **produces="application/json"** returning `WidgetDto`.
- **GET /api/widgets/{id}** with **produces="text/plain"** returning a human-readable string.
- **POST /api/widgets** with **consumes="application/json", produces="application/json"** creating a widget and returning **201 Created** and `Location`.
- Requests for non-existent item ids return **404**.
- Invalid JSON or blank name returns **400**.
- Unsupported Accept returns **406**; unsupported request Content-Type returns **415**.

Having two GETs on the same path with different **produces** shows Spring MVC picking a representation by Accept; tests always send an **explicit Accept** to avoid ambiguity from clients sending `*/*`.

Structure:

~~~text
web-contract-demo/
  pom.xml
  src/main/java/com/example/webcontract/
    WebContractDemoApplication.java
    WidgetDto.java
    CreateWidgetRequest.java
    WidgetController.java
  src/main/resources/
    application.properties
  src/test/java/com/example/webcontract/
    WidgetControllerMvcTests.java
    WidgetFullContextMvcTests.java
    WidgetLiveHttpTests.java
    WidgetJsonTests.java
~~~

### 5.1. Complete pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>web-contract-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**No need for `spring-boot-starter-webflux`** just to use MockMvc. `starter-web` uses Spring MVC/Servlet and default embedded Tomcat; `starter-test` brings JUnit Jupiter, Spring Test, AssertJ, Hamcrest, Mockito, and JSON testing tools aligned with the BOM.

**Boot 3.3.13 is an illustrative version**, not meant for long-term use in new systems because this branch has ended OSS support. If moving to Spring Boot 4.x, testing packages/artifacts and APIs may differ and should be updated per the docs for the version in use.

### 5.2. application.properties

Create **src/main/resources/application.properties**:

~~~properties
spring.application.name=web-contract-demo
server.port=8080

# Do not enable path extension negotiation automatically.
# Clients should use Accept to choose representation.
~~~

Do not force a global default Content-Type for all endpoints. Spring MVC chooses the **HttpMessageConverter** and type based on return value/Accept/produces. Behind a reverse proxy, URLs/`Location` may need forwarded headers handling separately.

### 5.3. Main Class

Create **src/main/java/com/example/webcontract/WebContractDemoApplication.java**:

~~~java
package com.example.webcontract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebContractDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebContractDemoApplication.class, args);
    }
}
~~~

Each public class/record resides in a matching filename. Root package **com.example.webcontract** covers the controllers/DTOs. No `web.xml` or `@EnableWebMvc` is needed; `@EnableWebMvc` can alter Boot MVC auto-configuration when misused.

### 5.4. DTOs: JSON Number, String, and Boolean

Create **src/main/java/com/example/webcontract/WidgetDto.java**:

~~~java
package com.example.webcontract;

public record WidgetDto(long id, String name, boolean active) {
}
~~~

Create **src/main/java/com/example/webcontract/CreateWidgetRequest.java**:

~~~java
package com.example.webcontract;

public record CreateWidgetRequest(String name) {
}
~~~

Two Java records serve as **DTOs** to receive/return HTTP JSON. There is no JPA entity/database in the demo; state lives in a `ConcurrentHashMap` and resets on app restart. In real projects, separate persistence/service/security and test at levels matching dependencies.

### 5.5. Complete WidgetController

Create **src/main/java/com/example/webcontract/WidgetController.java**:

~~~java
package com.example.webcontract;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/api/widgets")
public class WidgetController {

    private final Map<Long, WidgetDto> widgets =
            new ConcurrentHashMap<>(Map.of(
                    1L, new WidgetDto(1L, "Spring MVC", true),
                    2L, new WidgetDto(2L, "Spring Testing", false)
            ));

    private final AtomicLong nextId = new AtomicLong(100L);

    @GetMapping(
            value = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<WidgetDto> json(
            @PathVariable("id") long id) {

        WidgetDto widget = widgets.get(id);

        if (widget == null) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok()
                .varyBy(HttpHeaders.ACCEPT)
                .cacheControl(CacheControl.noStore())
                .header("X-Widget-Format", "json")
                .body(widget);
    }

    @GetMapping(
            value = "/{id}",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> text(
            @PathVariable("id") long id) {

        WidgetDto widget = widgets.get(id);

        if (widget == null) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok()
                .varyBy(HttpHeaders.ACCEPT)
                .header("X-Widget-Format", "text")
                .contentType(MediaType.TEXT_PLAIN)
                .body("widget:" + widget.id() + ":" + widget.name());
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<WidgetDto> create(
            @RequestBody CreateWidgetRequest input) {

        if (input == null ||
                input.name() == null ||
                input.name().isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        long id = nextId.getAndIncrement();
        WidgetDto created =
                new WidgetDto(id, input.name().trim(), true);

        widgets.put(id, created);

        URI location = ServletUriComponentsBuilder
                .fromCurrentRequest()
                .path("/{id}")
                .buildAndExpand(id)
                .toUri();

        return ResponseEntity.created(location)
                .body(created);
    }
}
~~~

**Explanation by HTTP Contract:**

1. **@RequestMapping("/api/widgets")** is the shared prefix.
2. Two **@GetMapping("/{id}")** methods are distinguished by **produces**: JSON and text. An explicit request `Accept` lets Spring pick the handler.
3. **@PathVariable("id") long id** converts the path segment to long; non-numeric input may be rejected with 400.
4. **ResponseEntity.notFound().build()** yields **404** with no body in the demo, leaking no persistence exceptions.
5. **ResponseEntity.ok()** produces 200; **header("X-Widget-Format", ...)** is an observable header for testing.
6. **varyBy(HttpHeaders.ACCEPT)** explicitly sets **Vary: Accept** so caches know the two representations depend on Accept. Not every Spring MVC response adds `Vary: Accept` automatically.
7. **CacheControl.noStore()** sets **Cache-Control: no-store** on the JSON response, aiding header testing though not replacing system-wide security/caching.
8. **@PostMapping(consumes=JSON, produces=JSON)** constrains request/response formats.
9. **@RequestBody** uses Jackson to deserialize JSON into `CreateWidgetRequest`; syntactically invalid JSON is typically rejected by MVC with 400 before entering the method.
10. **Blank name validation** happens inside the controller so the demo needs no Bean Validation dependency; production should use Jakarta Validation + `@Valid` where appropriate.
11. **ConcurrentHashMap** holds demo data in one instance; **AtomicLong** generates IDs on concurrent POSTs within the process.
12. **ResponseEntity.created(location)** sets **201 Created** and **Location** from the actual request URI (via `ServletUriComponentsBuilder`), avoiding hardcoded localhost.
13. **Successful POST returns WidgetDto JSON**, and the new resource is genuinely stored in the map so a GET to `Location` succeeds.
14. **No security** in the demo, so never use this code for APIs with sensitive data without adding authentication/authorization.

### 5.6. Points to Reflect On

**Are two GETs on the same path with different `produces` valid?** Yes: `produces` is part of the request mapping condition. However, when a client sends **Accept: */*** or omits Accept, the two variants can compete and selection depends on how mappings/converters are configured. Public APIs should define a clear default representation or design unambiguous routes/negotiation; the lesson's tests intentionally send matching Accept headers. Do not conflate a browser's `Accept: text/html` with a REST client's `Accept: application/json`.

**Why is `no-store` only on JSON?** That is an illustrative choice to inspect headers. A production app needs consistent cache policies across all representations of equal sensitivity; the text variant here exists purely to demonstrate content negotiation, not as a standard caching rule.

**Location behind a proxy:** the path is built from the current request. If the app sits behind HTTPS ingress while the backend only sees `http://service:8080`, `Location` may point to the wrong scheme/host. You can use **`server.forward-headers-strategy`** when proxies are trusted, and test through the public gateway. Never accept unsanitized forwarded headers due to host-header poisoning risks.

## 6. Running the API Manually Before Automated Testing

In the project directory:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Keep the server running in the first terminal and test in a second terminal. Note that **`mvn clean test`** runs the tests in the later sections once you have created the files; if you have only added main/DTO/controller without tests yet, it only compiles/tests what exists.

### 6.1. JSON Response

~~~bash
curl -si \
  -H 'Accept: application/json' \
  http://localhost:8080/api/widgets/1
~~~

Expect status **200**, Content-Type compatible with **application/json**, `Vary` containing `Accept`, `Cache-Control: no-store`, and `X-Widget-Format=json`.

Data-wise JSON body:

~~~json
{
  "id": 1,
  "name": "Spring MVC",
  "active": true
}
~~~

Do not require the JSON to have the exact key order or whitespace shown in the example.

### 6.2. Text Representation

~~~bash
curl -si \
  -H 'Accept: text/plain' \
  http://localhost:8080/api/widgets/1
~~~

Expect **200**, Content-Type compatible with **text/plain**, `X-Widget-Format=text`, `Vary` containing `Accept`. Exact body:

~~~text
widget:1:Spring MVC
~~~

This text body is not JSON, so do not use `jsonPath` to verify it.

### 6.3. Requesting an Unsupported Response Type

~~~bash
curl -si \
  -H 'Accept: application/xml' \
  http://localhost:8080/api/widgets/1
~~~

Both GET handlers only produce JSON/text, so when the request asks for XML, Spring MVC rejects content negotiation with **406 Not Acceptable**. Do not predict an exact error body because MVC/Boot error handling can vary.

### 6.4. Creating a Resource with JSON

~~~bash
curl -si \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary '{"name":"Test Widget"}' \
  http://localhost:8080/api/widgets
~~~

Expect **201 Created**, Location looking like **http://localhost:8080/api/widgets/100** on a freshly started instance, with body:

~~~json
{
  "id": 100,
  "name": "Test Widget",
  "active": true
}
~~~

**ID 100 is only guaranteed when this is the first create request in a fresh process.** If another test or request already created data, the ID will increment. Automated tests must read the actual ID from the response and verify `Location` against it, rather than hardcoding 100.

### 6.5. Wrong Request Body Media Type

~~~bash
curl -si \
  -X POST \
  -H 'Content-Type: text/plain' \
  -H 'Accept: application/json' \
  --data-binary 'name=BadRequestType' \
  http://localhost:8080/api/widgets
~~~

Expect **415 Unsupported Media Type** because `@PostMapping` only consumes `application/json`.

### 6.6. Malformed JSON

~~~bash
curl -si \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary '{"name":' \
  http://localhost:8080/api/widgets
~~~

Expect **400 Bad Request** from Jackson/Spring MVC message conversion. This is a JSON syntax error, distinct from business validation errors.

### 6.7. Non-Existent Resource

~~~bash
curl -si \
  -H 'Accept: application/json' \
  http://localhost:8080/api/widgets/999
~~~

Expect **404 Not Found**. In the demo the controller returns `ResponseEntity.notFound().build()`, so do not hardcode a JSON error body.

### 6.8. Undeclared HTTP Method

~~~bash
curl -si \
  -X DELETE \
  -H 'Accept: application/json' \
  http://localhost:8080/api/widgets/1
~~~

Expect **405 Method Not Allowed**, because the path has GET but no DELETE handler. The HTTP response may include **Allow** handled by MVC, though the order or set of methods (including HEAD/OPTIONS) may vary; do not assert an exact literal `Allow` string unless explicitly part of the contract.

## 7. Testing Mappings, Statuses, Headers, and JSON with @WebMvcTest + MockMvc

**@WebMvcTest(WidgetController.class)** loads the web slice and auto-configures MockMvc. The demo controller has no external service dependency so the slice test is self-contained; in a real app, use `@MockBean` for service dependencies per Spring Boot 3.3 APIs.

Create **src/test/java/com/example/webcontract/WidgetControllerMvcTests.java**:

~~~java
package com.example.webcontract;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(WidgetController.class)
class WidgetControllerMvcTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void getJsonMatchesMappingStatusHeadersAndFields()
            throws Exception {
        mvc.perform(get("/api/widgets/{id}", 1)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string(
                        HttpHeaders.VARY, "Accept"))
                .andExpect(header().string(
                        HttpHeaders.CACHE_CONTROL, "no-store"))
                .andExpect(header().string(
                        "X-Widget-Format", "json"))
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.name").value("Spring MVC"))
                .andExpect(jsonPath("$.active").value(true))
                .andExpect(jsonPath("$.passwordHash").doesNotExist());
    }

    @Test
    void getTextUsesDifferentRepresentation()
            throws Exception {
        mvc.perform(get("/api/widgets/1")
                        .accept(MediaType.TEXT_PLAIN))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_PLAIN))
                .andExpect(header().string(
                        HttpHeaders.VARY, "Accept"))
                .andExpect(header().string(
                        "X-Widget-Format", "text"))
                .andExpect(content().string("widget:1:Spring MVC"));
    }

    @Test
    void unsupportedAcceptReturns406() throws Exception {
        mvc.perform(get("/api/widgets/1")
                        .accept(MediaType.APPLICATION_XML))
                .andExpect(status().isNotAcceptable());
    }

    @Test
    void unknownWidgetReturns404() throws Exception {
        mvc.perform(get("/api/widgets/999")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound());
    }

    @Test
    void wrongMethodReturns405() throws Exception {
        mvc.perform(delete("/api/widgets/1")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isMethodNotAllowed());
    }

    @Test
    void postConsumesJsonAndReturns201Location()
            throws Exception {
        String body = mapper.writeValueAsString(
                new CreateWidgetRequest("Java Book"));

        MvcResult result = mvc.perform(
                    post("/api/widgets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().exists(HttpHeaders.LOCATION))
                .andExpect(jsonPath("$.name").value("Java Book"))
                .andExpect(jsonPath("$.active").value(true))
                .andReturn();

        JsonNode created = mapper.readTree(
                result.getResponse().getContentAsString());
        long id = created.path("id").asLong();

        assertTrue(id >= 100L);

        String location =
                result.getResponse().getHeader(HttpHeaders.LOCATION);
        assertTrue(location.endsWith("/api/widgets/" + id));

        mvc.perform(get("/api/widgets/{id}", id)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value((int) id))
                .andExpect(jsonPath("$.name").value("Java Book"));
    }

    @Test
    void postTextBodyReturns415() throws Exception {
        mvc.perform(post("/api/widgets")
                        .contentType(MediaType.TEXT_PLAIN)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("name=wrong"))
                .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void postMalformedJsonReturns400() throws Exception {
        mvc.perform(post("/api/widgets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("{\"name\":"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void postBlankNameReturns400() throws Exception {
        mvc.perform(post("/api/widgets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"  \"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void noInternalFieldInJson() throws Exception {
        MvcResult response = mvc.perform(
                    get("/api/widgets/1")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andReturn();

        JsonNode node = mapper.readTree(
                response.getResponse().getContentAsString());

        assertEquals(1L, node.get("id").longValue());
        assertTrue(node.get("active").isBoolean());
        assertFalse(node.has("passwordHash"));
    }
}
~~~

**Import note:** Static imports for `MockMvcRequestBuilders` and `MockMvcResultMatchers` are required. The Java code uses **`MvcResult`** to read the runtime-generated ID value and compare `Location`. Avoid constructing a fixed URL with ID 100 in tests.

### Breakdown of Each Assertion Group

| Requirement | MockMvc Assertion | Value |
| --- | --- | --- |
| GET succeeds | **status().isOk()** | Exact HTTP 200. |
| JSON media type | **content().contentTypeCompatibleWith(APPLICATION_JSON)** | Does not confuse `text/plain` containing JSON. |
| Custom header | **header().string("X-Widget-Format", "json")** | Mapping selected JSON variant. |
| Cache header | **header().string(CACHE_CONTROL, "no-store")** | Response policy applied. |
| Vary header | **header().string(VARY, "Accept")** | Caches distinguish the two representations. |
| JSON number | **jsonPath("$.id").value(1)** | `id` has the right numeric value. |
| JSON string | **jsonPath("$.name").value("Spring MVC")** | Domain string matches. |
| JSON boolean | **jsonPath("$.active").value(true)** | Real boolean, not `"true"`. |
| No leaked field | **jsonPath("$.passwordHash").doesNotExist()** | Negative JSON contract. |
| Text variant | **content().string(...)** | Exact plain text body. |
| Wrong Accept | **status().isNotAcceptable()** | 406, does not silently return XML. |
| Wrong Content-Type | **status().isUnsupportedMediaType()** | 415. |
| Missing item | **status().isNotFound()** | 404. |
| Wrong method | **status().isMethodNotAllowed()** | 405. |
| POST created | **status().isCreated()**, `Location` exists | 201 + resource link. |
| Malformed body | **status().isBadRequest()** | 400. |

**Do not assert raw JSON strings by field order.** Jackson can change property order while the contract remains valid. `JSONPath` and `JsonNode` check values directly. For JSON arrays, check count/membership/order if ordering is actually promised by the API.

**Not every error has a JSON error document.** The tests above only check 400/404/405/406/415 status because default framework error bodies can vary across MVC/Boot server layers. If an app has a `@ControllerAdvice` returning **`ProblemDetail`** under a published schema, add assertions for `application/problem+json` and contracted fields.

## 8. @WebMvcTest Does Not Load Ordinary Business Services

Example in a real project:

~~~java
@RestController
class OrderController {
    private final OrderService service;

    OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/api/orders/{id}")
    OrderDto get(@PathVariable long id) {
        return service.get(id);
    }
}
~~~

This is an **illustrative snippet depending on `OrderService`/`OrderDto` absent from the demo**, not a standalone program.

When using **@WebMvcTest(OrderController.class)**, Spring does not automatically scan regular `@Service`/`@Repository` beans. Therefore the test must supply collaborators. In Spring Boot 3.3, for example:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerSliceTests {

    @Autowired
    MockMvc mvc;

    @MockBean
    OrderService service;

    // Mockito.when(service.get(42L)).thenReturn(...);
    // Then mvc.perform(get("/api/orders/42")) andExpect(...).
}
~~~

Required imports include **org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest**, **org.springframework.boot.test.mock.mockito.MockBean**, **org.springframework.beans.factory.annotation.Autowired**, and **org.springframework.test.web.servlet.MockMvc**. This is a directional snippet; `OrderService`/`OrderDto` and test methods are not yet defined.

If a test reports **`NoSuchBeanDefinitionException` / failed to load ApplicationContext**, check whether collaborators need to be mocked/imported. Do not switch to `@SpringBootTest` just to hide configuration problems without considering test scope.

### Security FilterChain in the Test Slice

**@WebMvcTest** can pull in corresponding Security configurations/filters when Spring Security is on the classpath. A POST test may return **403 CSRF** even when the controller is right. In that case:

- Use **spring-security-test**, **@WithMockUser**, **SecurityMockMvcRequestPostProcessors.csrf()**, or contract-appropriate mock authentication.
- Test both **401/403** and role-based authorization like production.
- Do not disable the entire filter chain just to turn tests green if security is part of the contract.
- If intentionally testing a controller in isolation from security, document the scope clearly and maintain separate security integration tests.

The main demo omits Spring Security to focus on mapping/status/headers/JSON/media types, so those security statuses need testing whenever a real app includes that dependency.

## 9. @SpringBootTest + @AutoConfigureMockMvc: Full Context Yet Still Mock HTTP

This option fits when you need MVC mappings together with real application configuration, filters, custom converters, `ControllerAdvice`, interceptors, or service wiring.

Create **src/test/java/com/example/webcontract/WidgetFullContextMvcTests.java**:

~~~java
package com.example.webcontract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WidgetFullContextMvcTests {

    @Autowired
    MockMvc mvc;

    @Test
    void fullContextUsesSameJsonContract()
            throws Exception {

        mvc.perform(get("/api/widgets/1")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string(
                        HttpHeaders.VARY, "Accept"))
                .andExpect(jsonPath("$.name").value("Spring MVC"));
    }
}
~~~

**Key point:** `@SpringBootTest` (default `MOCK`) loads the **entire ApplicationContext**, while `@AutoConfigureMockMvc` creates the mock web testing infrastructure. It still **does not open an HTTP socket**. Do not think `@AutoConfigureMockMvc` is equivalent to `RANDOM_PORT`.

Usually slower than `@WebMvcTest` because more beans are initialized; use it when verifying integration of real filters/advice/security/serialization config.

## 10. @SpringBootTest(RANDOM_PORT): Testing Through a Real HTTP Connector

A MockMvc test misses failures below the servlet stack or in infrastructure. To test real HTTP, start embedded Tomcat on a random port and use **Java 17 HttpClient**.

Create **src/test/java/com/example/webcontract/WidgetLiveHttpTests.java**:

~~~java
package com.example.webcontract;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class WidgetLiveHttpTests {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newHttpClient();
    private final ObjectMapper mapper = new ObjectMapper();

    private HttpResponse<String> get(String path, String accept)
            throws Exception {

        HttpRequest req = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(5))
                .header("Accept", accept)
                .GET()
                .build();

        return client.send(req,
                HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void jsonAndTextAreNegotiatedOverRealHttp()
            throws Exception {

        HttpResponse<String> json =
                get("/api/widgets/1", "application/json");

        assertEquals(200, json.statusCode());
        assertTrue(json.headers()
                .firstValue("content-type")
                .orElse("")
                .startsWith("application/json"));

        JsonNode data = mapper.readTree(json.body());

        assertEquals(1L, data.path("id").asLong());
        assertEquals("Spring MVC", data.path("name").asText());
        assertTrue(data.path("active").isBoolean());
        assertTrue(data.path("active").asBoolean());
        assertFalse(data.has("passwordHash"));

        HttpResponse<String> text =
                get("/api/widgets/1", "text/plain");

        assertEquals(200, text.statusCode());
        assertTrue(text.headers()
                .firstValue("content-type")
                .orElse("")
                .startsWith("text/plain"));
        assertEquals("widget:1:Spring MVC", text.body());

        assertEquals(406,
                get("/api/widgets/1", "application/xml")
                        .statusCode());
    }

    @Test
    void invalidRequestMediaTypeIs415()
            throws Exception {

        HttpRequest request = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:"
                            + port + "/api/widgets"))
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "text/plain")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString("wrong"))
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(415, response.statusCode());
    }

    @Test
    void absentWidgetReturns404() throws Exception {
        assertEquals(404,
                get("/api/widgets/999", "application/json")
                        .statusCode());
    }
}
~~~

**Why a random port?** When CI or a developer runs multiple services, hardcoding 8080 can collide. `@LocalServerPort` receives the embedded server's actual port. Tests do not need to assume the main application is running in a terminal.

**Why use Java HttpClient instead of WebTestClient?** JDK 17 includes `java.net.http.HttpClient`, so a Servlet MVC project does not have to add reactive web dependencies just to test HTTP. Spring Boot 3.3 also offers **TestRestTemplate** and can integrate **WebTestClient** if appropriate dependencies exist; choose the API per need. Avoid using APIs that only exist in Boot 4.x and pasting them into Boot 3.3 code.

**This is still not an end-to-end public topology test.** Testing over `127.0.0.1` does not test TLS termination, Nginx rewrites, CDN caching, or Load Balancers. Those boundaries require separate tests in matching environments.

## 11. @JsonTest: Testing Serializers Independently of HTTP

If a project has a custom Jackson naming strategy, custom serializers, or JsonViews, bugs can arise before handler mapping is even involved. **@JsonTest** tests the JSON mapping slice and `ObjectMapper` without starting a web context.

Create **src/test/java/com/example/webcontract/WidgetJsonTests.java**:

~~~java
package com.example.webcontract;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JsonTest
class WidgetJsonTests {

    @Autowired
    ObjectMapper mapper;

    @Test
    void recordFieldsHaveStableNamesAndTypes()
            throws Exception {

        WidgetDto widget =
                new WidgetDto(7L, "JSON Testing", true);

        String json = mapper.writeValueAsString(widget);
        JsonNode node = mapper.readTree(json);

        assertEquals(7L, node.path("id").asLong());
        assertEquals("JSON Testing",
                node.path("name").asText());
        assertTrue(node.path("active").isBoolean());
        assertTrue(node.path("active").asBoolean());
        assertFalse(node.has("internalMemo"));
    }

    @Test
    void inputRecordDeserializesCorrectly()
            throws Exception {

        CreateWidgetRequest request =
                mapper.readValue(
                        "{\"name\":\"Java Book\"}",
                        CreateWidgetRequest.class);

        assertEquals("Java Book", request.name());
    }
}
~~~

**@JsonTest** is another slice—do not combine **@JsonTest** and **@WebMvcTest** simultaneously on the same test class. Keep them in separate classes by purpose. `@JsonTest` verifies `ObjectMapper`/record types; it **does not** verify HTTP Content-Type, Accept, routing, status, or response headers.

### Avoid Unnecessary Testing of Implementation Details

There is no need to assert internal Jackson converter class names or bean counts when what you really want to know is whether the **API returns the right JSON contract**. Unit JSON tests help when schemas use custom serializers, yet MVC integration tests must still verify the representation over HTTP.

## 12. Run Workflow and What Is Proven

Run the full test suite:

~~~bash
mvn clean test
~~~

This command builds the app and runs JUnit classes ending in `Tests` in the declared structure. When Maven Surefire/JUnit Jupiter are properly managed by the Spring Boot parent, tests should run without a manual server on port 8080.

**Maven output may vary** by environment, CPU count, dependency cache, and logging, so no fixed seconds/console line counts are stated. What to verify is that Maven exits with **exit code 0**, tests executed, and there are no unexpected failures/errors/skips.

Result matrix:

| Test Class | Real Web Stack? | What It Tests |
| --- | --- | --- |
| `WidgetJsonTests` | No | Jackson record serialization/deserialization, field names/types. |
| `WidgetControllerMvcTests` | Mock MVC slice | GET/POST mappings, statuses 200/201/400/404/405/406/415, headers, JSON. |
| `WidgetFullContextMvcTests` | Full context but mock requests | MVC + Boot app beans/filter/config wiring. |
| `WidgetLiveHttpTests` | Real embedded server on random port | JSON/text negotiation over HTTP connector, Content-Type, 404, 406, 415. |

**Do not report “tests passed” if Maven has not actually been run.** The code in this lesson is sample material for building and running a project; verification requires running the command after creating the project. A Knowledge lesson does not imply a build was executed in the reader's workspace.

### Why Do These Negative Tests Have High Value?

A happy-path GET 200 is usually easy to get right. Production bugs often live at the boundaries:

- An endpoint accidentally accepts `text/plain` as JSON leading to inconsistent behavior.
- An `Accept: application/xml` request hits a converter fallback returning an unexpected content type.
- Malformed JSON returns 500 instead of 400.
- A non-existent resource causes the service to return null + 200.
- POST succeeds yet forgets **`Location`**.
- API returns right data but wrong **`Content-Type`** header.
- An unsupported custom media type version silently falls back to default.
- Missing **`Vary`** cache header causes a CDN to serve cached JSON/text variants to the wrong clients.
- Internal fields appear in JSON from serializing an entity instead of a DTO.

Adding tests for **failure boundaries** prevents regressions far more effectively than repeating many nearly identical happy-path tests.

## 13. Writing Tests Around the HTTP Contract Instead of Implementation

A good test follows **Given – When – Then**:

- **Given:** widget ID 1 exists, client accepts `application/json`.
- **When:** `GET /api/widgets/1`.
- **Then:** HTTP 200, `Content-Type: application/json`, `Vary: Accept`, `id` is number 1, `name` matches, `active` is boolean true, and no internal fields exist.

If lookup changes from a `Map` to JDBC without altering the HTTP contract, an ideal controller contract test stays green. If the URL or public field schema changes, the test turns red because that may be a breaking change.

### Do Not Assert Too Little

Poor:

~~~java
mvc.perform(get("/api/widgets/1"))
        .andExpect(status().isOk());
~~~

This test fails to catch an endpoint returning text instead of JSON, missing body, wrong headers, or wrong values. Especially in this demo where multiple representations share a URL, you must send `Accept`.

### Do Not Assert Too Many Non-Contract Details

It is also poor to assert:

- Fixed JSON field order when clients do not care.
- Exact unpublished default auto-generated error bodies.
- Exception stacktraces/messages inside 4xx responses.
- Full embedded Tomcat `Date`/`Server` header contents or `Allow` ordering.
- Response latency always under 1ms in uncontrolled CI.
- `Location` always containing port 8080 when the server runs `RANDOM_PORT`.

Test what clients genuinely depend on and the application guarantees.

### When to Use `content().json`?

MockMvc can compare JSON structurally:

~~~java
mvc.perform(get("/api/widgets/1")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(content().json(
        "{\"id\":1,\"name\":\"Spring MVC\",\"active\":true}"
    ));
~~~

This is a snippet inside a JUnit test that already has `mvc`/imports, not a standalone class. For complex schemas, using **`jsonPath`** or Jackson **`JsonNode`** distinguishes numeric/string/boolean types and missing-field checks more clearly. Structural comparison also avoids whitespace and field-ordering sensitivity.

## 14. Testing Headers Properly

**Headers can repeat or hold lists of values**, so pick matching assertions. Common headers to verify in Spring MVC:

| Header | Purpose | How to Test |
| --- | --- | --- |
| **Content-Type** | Media type of response | `contentTypeCompatibleWith(...)`, or `contentType(...)` if exact contract. |
| **Location** | URI of newly created resource after 201 | Header exists + verify URI path/host per deployment. |
| **Cache-Control** | Cacheability of representation | Header string, or parse/cache policy per requirement. |
| **Vary** | Cache key varies by request header | Verify it contains `Accept` (do not hardcode order if multiple values). |
| **ETag** | Representation validator | Test header/conditional GET `If-None-Match` and 304 if implemented. |
| **Last-Modified** | Time-based validator | Test conditional GET when present. |
| **Allow** | Supported methods on 405/OPTIONS | Verify expected methods exist without forcing exact order. |
| **Content-Disposition** | File download filename/attachment | Header assertion + encoding/filename semantics. |
| **Set-Cookie** | Session/cookie flags | In security tests, verify `Secure`, `HttpOnly`, `SameSite` per context. |
| **X-Widget-Format** | Demo's custom representation signal | Exact `json`/`text` header. |

**Do not assume every response includes `ETag` or `Cache-Control`.** They must be produced by controllers, middleware, or the container. In the demo, `Cache-Control: no-store` is only added for JSON GETs, while `Vary` comes from calling **`varyBy(HttpHeaders.ACCEPT)`**; do not claim Spring always emits `Vary: Accept` automatically.

### Vary and Caching with Content Negotiation

Two representations of the same resource can share a URL while differing by `Accept`. If a CDN/shared cache ignores `Accept` and the response lacks the proper `Vary` header, a client expecting text could receive cached JSON or vice versa. Testing **`Vary: Accept`** therefore has real value when an API serves multiple variants on one URI.

Besides `Accept`, responses may vary by **`Accept-Encoding`**, **`Accept-Language`**, **`Origin`**, or other headers depending on behavior. Do not confuse `Vary` with a header that enables CORS, nor use **`Vary: *`** as a substitute for proper cache design.

### ETag and 304: An Extended Test Scenario

If an API implements `ETag`, tests should issue two requests:

~~~text
1. GET /resource -> 200, ETag: "v1"
2. GET /resource, If-None-Match: "v1" -> 304 Not Modified
~~~

This is an **extended scenario**, not output from the demo `WidgetController` because the demo does not add `ETag`. With 304, the body normally contains no representation; verify status, headers, and conditional request semantics rather than expecting a JSON body like a 200 response.

## 15. Content Negotiation in Detail: Accept, q-Values, and Wildcards

A client may send:

~~~http
Accept: application/json, text/plain;q=0.2
~~~

**q** is the quality preference; the client prefers JSON over text in this example. Spring MVC evaluates compatibility and preference when picking handlers/converters. With simple **`Accept: application/json`** and **`Accept: text/plain`**, the demo picks the variant unambiguously.

Several scenarios worth dedicated tests in real APIs:

- **Accept: */*** or missing `Accept`: may allow multiple variants. If an API registers multiple `@GetMapping` methods on the same path differing only in `produces`, define a clear default/policy and test against ambiguity.
- **Accept: application/*:** may be compatible with `application/json`, depending on available variants.
- **Accept: application/xml:** the demo does not support XML, expecting 406.
- **Accept: application/json;q=0.2,text/plain;q=0.9:** tests preference for text if the contract and negotiation allow it.
- **Accept: application/vnd.acme.widget+json:** vendor media types may require dedicated `produces`/converters; do not assume `application/json` mapping covers every structured syntax suffix.
- **Accept-Language:** can select the representation's locale, without converting JSON to `text/plain`.
- **Accept-Encoding:** governs content compression (gzip/br), **not** choosing JSON vs text in the controller. Usually handled by connector/proxy compression.
- **URL `.json`/`.xml` suffixes:** modern Spring MVC should not rely on suffix/path extension negotiation by default; prefer `Accept` or explicit configuration when genuinely needed.

**HTTP 406 is a valid outcome when the server cannot produce a representation the client requests.** Some servers/APIs fall back to a default representation instead, so test statuses according to the **actual configured contract**, rather than enforcing 406 on every endpoint globally.

### consumes First or produces First?

Spring MVC checks multiple mapping conditions. On a request with both an invalid **Content-Type** and invalid **Accept**, the resulting error status can depend on handler matching/resolvers. **Do not write a test expecting both 406 and 415** on a single request violating both. Test each error independently: wrong consumes + valid Accept → 415; right consumes + wrong Accept → 406.

### Content-Type with a Charset Parameter

A response may state:

~~~http
Content-Type: text/plain;charset=UTF-8
~~~

When a charset is appended, **`contentTypeCompatibleWith(MediaType.TEXT_PLAIN)`** is better than asserting exact **`"text/plain"`** when the contract only requires the media type. If the contract mandates a specific charset, verify **`Content-Type`** parameters and byte decoding separately.

## 16. Serialization Errors and Exception Handling

An invalid POST body can fail in several ways:

| Input | Failure Area | Typical Status |
| --- | --- | --- |
| Invalid JSON syntax | `HttpMessageNotReadableException`/converter | **400** |
| Valid JSON yet blank name | Business validation in demo | **400** |
| Path `id="abc"` while controller expects `long` | Argument type conversion | **400** |
| `Content-Type=text/plain` while `consumes=application/json` | Mapping/media restriction | **415** |
| `Accept=application/xml` while only producing JSON/text | Negotiation | **406** |
| Widget missing from in-memory map | Domain lookup | **404** |
| DELETE on a GET-only URI | Method restriction | **405** |
| Authenticated user lacking permission | Security authorization in secured app | **403** |
| Unauthenticated on login-required resource | Security challenge/entry point | **401** |
| Service bug/unhandled exception | Server error | **500** |

**Error payloads can differ when using `@ControllerAdvice`/`ProblemDetail`**. Spring Framework offers **`ProblemDetail`**/`ErrorResponse` APIs, and Spring Boot provides an option to enable Problem Details handling in certain configurations. To test **`application/problem+json`**, implement and publish a clear error contract, then assert exact **`type`/`title`/`status`/`detail`** instead of relying on incidental default bodies.

**Never return raw `exception.getMessage()` to clients** when it might contain SQL/URIs/PII. Test which error details may be exposed and ensure stacktraces never appear in production error responses. Even when the status is right, sensitive data in the body is still a regression.

## 17. JSON Shape, Unicode, and Null vs Missing

A JSON contract is more than “the body has `id`.” Watch for:

~~~json
{
  "id": 7,
  "name": "Java Book",
  "active": true,
  "tags": ["spring", "web"],
  "description": null
}
~~~

Distinctions:

- **`id=7`** is a number; **`"7"`** is a string.
- **`active=true`** is a boolean; **`"true"`** is a string.
- **`tags=[]`** is an empty array; **`tags=null`** is null; **`tags`** absent is missing.
- **`description=null`** differs from **`description=""`** and from omitting the field.
- **`name="Java Book"`** (or Unicode text like `"Sách Java"`) must round-trip cleanly; never assume every client uses the same default platform encoding.
- JSON **object field order** does not matter, though array element order matters if the API promises sorting.
- Floats have rounding/tolerance issues: currency usually requires `BigDecimal` and a defined representation contract rather than careless binary float equality tests.

Spring Boot/Jackson behavior can change with **`@JsonInclude`**, **`@JsonIgnore`**, **`@JsonProperty`**, custom serializers/deserializers, or **`spring.jackson.*`** properties. Write `JsonTest` and MVC-level tests to lock down the exact representation clients see.

When hiding sensitive fields, use explicit DTOs; never expose raw JPA entities with all fields directly in responses.

## 18. Why Tests Can Be Flaky and How to Stabilize Them

Reliable HTTP tests must be independent, highly deterministic, and free of external network reliance.

**Common sources of flakiness:**

- Hardcoding **`server.port=8080`** in integration tests instead of `RANDOM_PORT`.
- Sharing global/static data across test methods and asserting ID is always 100.
- Depending on JUnit test method execution order.
- Testing against a real DB/shared staging environment holding state from previous runs.
- Asserting timestamps, random UUIDs, or unstable byte content lengths.
- Client timeouts set too short in CI.
- Comparing raw JSON string order instead of parsing trees.
- Using sleep to wait for the server when `@SpringBootTest` already manages lifecycle.
- Using wildcard `Accept` causing two same-path mappings to compete.
- Running tests with a different profile without pinning production configs affecting converters/security.
- Using `@Transactional` on `RANDOM_PORT` and expecting server transactions to be rolled back by the client test thread.

**Key insight on `@Transactional` + `RANDOM_PORT`:** client and server run across separate threads/process boundaries. A transaction started inside the test method does not wrap the transaction opened by the server request. Therefore default test rollback does not automatically roll back DB work from HTTP requests; use a proper cleanup strategy for integration tests hitting real DBs.

**How to stabilize:**

- Use in-memory/fake services for MVC slices, mocking dependencies where appropriate.
- Use `RANDOM_PORT` for real HTTP tests.
- Use unique test data or transaction/environment cleanup, independent of ordering.
- Separate tests requiring external databases/brokers into dedicated integration suites.
- Check header/JSON semantics instead of unimportant framework-generated values.
- Maintain test profiles for auth/locale/timezone/serialization policies as needed.
- On failures, use MockMvc's **`andDo(print())`** carefully to inspect mock request/response details, yet **never enable raw body/header dumps on production CI data** since logs can leak secrets.
- For time-sensitive tests, inject a `Clock`/fake clock instead of `Thread.sleep` whenever possible.

## 19. Security, Filters, Cookies, and Content Negotiation

**Do not disable Spring Security just to make POST return 201.** If the production API requires login or CSRF, 401/403 is part of the contract. Use Spring Security test support and appropriate test principals/tokens. Verify properly:

- Unauthenticated → challenge/401 or login redirect per config.
- Authenticated yet forbidden → 403.
- Cookie/session flags and token transport.
- CSRF rejection on unsafe methods in cookie/session models.
- CORS preflight `OPTIONS` and `Vary: Origin` when cross-origin browser clients exist.
- Content negotiation of error messages: 401/403 returning proper JSON/`ProblemDetail`.
- No tokens/passwords leaked in response body, `Location`, or custom headers.

**@WebMvcTest** can load filters present in the web slice, and **`@AutoConfigureMockMvc(addFilters=false)`** can skip filters when testing purely controller behavior. Use that option only intentionally, and maintain separate integration tests for security filters. If tests pass only because filters were stripped, never claim the production API is properly protected.

**CORS differs from content negotiation.** CORS uses `Origin`/`Access-Control-Allow-*` and browser policy; `Accept` chooses representation media type. A single response may need both `Vary: Accept` and `Vary: Origin` if responses vary by `Origin` and cache semantics require it.

## 20. Reverse Proxy, Host, Location, and TLS

In production:

~~~text
Client HTTPS https://api.example.test/catalog/api/widgets
    |
    v
Nginx / ingress [TLS termination, path rewrite]
    |
    v
Spring Boot http://widgets-service:8080/api/widgets
~~~

If the controller constructs `Location` from the internal request without handling trusted forwarded headers, HTTP 201 may return **`Location: http://widgets-service:8080/api/widgets/100`**, wrong for external clients.

Spring Boot provides configuration:

~~~properties
# Only enable when proxy strips/sets Forwarded headers
server.forward-headers-strategy=framework
~~~

Or `native` strategy where appropriate. However, **`Forwarded`/`X-Forwarded-Host`/`X-Forwarded-Proto`/`X-Forwarded-Prefix` must come from trusted proxies**—never trust headers sent arbitrarily by internet clients. Otherwise an attacker can replace the host in `Location` or links with a malicious hostname.

A localhost test cannot prove public HTTPS `Location` headers are right. You need an integration/e2e test through ingress or an environment simulating sanitized forwarded headers:

1. POST via public URL.
2. Verify status 201.
3. Verify **`Location`** points to the right `https`/public host/prefix.
4. GET that exact `Location` returns 200.
5. Verify spoofed `Host`/`Forwarded` headers do not alter `Location` when requests enter through the edge.

## 21. Common Mistakes When Writing MockMvc Tests

| Symptom | Cause | Solution |
| --- | --- | --- |
| `@WebMvcTest` fails to load ApplicationContext | Controller missing `@Service` collaborator | `@MockBean` or `@Import` scoped dependency. |
| `MockMvc = null` | Missing `@WebMvcTest`/`@AutoConfigureMockMvc` or missing `@Autowired` | Use proper annotations/imports. |
| 200 yet wrong JSON body | Test only asserted status | `jsonPath` + `Content-Type` + schema/field types. |
| 404 when calling controller | Wrong `@RequestMapping` prefix/context path | Check mappings and path variables. |
| 405 instead of 404 | URL has a handler yet HTTP method unsupported | Check method and `Allow`/handler config. |
| 406 on GET | `Accept` incompatible with `produces` | Send matching `Accept`; test negative contract. |
| 415 on POST | `Content-Type` incompatible with `consumes` | JSON `Content-Type` and valid JSON body. |
| 400 when sending JSON | Malformed body or argument conversion/validation | Check request body, converter, and error contract. |
| 403 on POST tests | CSRF/security filter | Use security-test, `csrf()`, valid principal; do not disable security blindly. |
| Exact content type test fails | Charset/media parameters appended | Use `contentTypeCompatibleWith` when contract permits. |
| `Location` test fails in `RANDOM_PORT` | Hardcoded 8080 or host | Read actual `Location`, parse/compare path per contract. |
| Missing `Vary` header | Code omitted `varyBy`, proxy cache unconfigured | Add `Vary` when response actually varies by `Accept`. |
| JSON `id` is sometimes 100, sometimes 101 | Shared mutable state, test order | Read generated ID; do not predict fixed sequence. |
| `@SpringBootTest` does not open socket | Using default `MOCK` environment | Pick `RANDOM_PORT`. |
| `@WebMvcTest` passes yet deployment fails | MockMvc does not test TLS/connector/proxy | Add real HTTP + e2e tests. |
| MockMvc error body differs from curl | Container error handling not fully executed | Test real server if error page format is part of contract. |
| `jsonPath` misses field due to `snake_case` | Custom Jackson naming strategy | Test schema per API, not Java property names. |
| Response JSON order differs | Comparing raw strings | Parse JSON/`JsonNode`. |
| `.accept(MediaType.APPLICATION_JSON)` on POST yet 415 | Request `Content-Type` still wrong | Distinguish `Accept` from `Content-Type`. |
| WebFlux handler test fails imports | Used `MockMvc` instead of `WebTestClient`/`@WebFluxTest` | Check Servlet vs Reactive runtime. |

## 22. API Pre-Release Testing Checklist

- [ ] GET/POST/PATCH/DELETE mappings match correct HTTP methods and URLs.
- [ ] Path variable/query param conversion and validation are tested.
- [ ] Each happy path has proper status (200/201/204) and accurate response body.
- [ ] Error paths cover 400/401/403/404/405/406/409/415 per real contract, without forcing inapplicable statuses.
- [ ] Response `Content-Type` matches body; request `Content-Type`/`Accept` tested independently.
- [ ] JSON property names, numeric/boolean/string types, nested/arrays, null/missing, and Unicode are accurate.
- [ ] No internal/secret fields leaked in JSON.
- [ ] 201 Created includes `Location` pointing to the created resource and clients can follow the URL.
- [ ] `Cache-Control`, `Vary`, `ETag`, `Last-Modified`, and security headers are checked when contracted by the API.
- [ ] Multi-representation endpoints have tests for varying `Accept` headers and negative 406.
- [ ] Unsupported request media types have negative 415; malformed JSON yields 400.
- [ ] Do not assert field order or internal server error bodies unless contracted.
- [ ] `@WebMvcTest` tests use appropriate fake services/mocks; do not boot DB needlessly.
- [ ] Full context tests via `@SpringBootTest + @AutoConfigureMockMvc` when filters/advice/converters matter.
- [ ] Real connector tests via `@SpringBootTest(RANDOM_PORT)` for HTTP behavior.
- [ ] If the app uses security, test 401/403/CSRF/CORS with real filters.
- [ ] If an API gateway is present, test public HTTPS URLs, `Location`, and forwarded-header trust.
- [ ] Do not hardcode IDs, random ports, timestamps, or test execution order.
- [ ] Run `mvn clean test` on CI, check test failures, and verify test classes actually ran.
- [ ] Sync docs/OpenAPI with tested media types, statuses, headers, and error schemas.
- [ ] When upgrading Spring Boot/Jackson/Spring Security, rerun contract tests and update behavior per version.

## 23. Self-Check Questions

**1. Why is a test asserting only `status().isOk()` insufficient?**  
Because it misses wrong `Content-Type`, headers, JSON shape, values, or media negotiation.

**2. Does `@WebMvcTest` start a real Tomcat instance?**  
No. It configures an MVC slice/`MockMvc` and a mock servlet environment.

**3. Does `@SpringBootTest` without `webEnvironment` configured open a real HTTP socket?**  
No. It defaults to `MOCK`.

**4. What is `@SpringBootTest(RANDOM_PORT)` for?**  
Starting a real embedded HTTP server on a random port, testing over the network.

**5. Does `@AutoConfigureMockMvc` turn `@SpringBootTest` into a real HTTP integration test?**  
No. It provides `MockMvc` within the full context.

**6. How do `Accept` and `Content-Type` differ?**  
`Accept` states the response media types the client wants; request `Content-Type` states the media type of the uploaded body.

**7. When is 406 expected?**  
When the server cannot/will not return a representation matching `Accept` per configuration.

**8. When is 415 expected?**  
When the request entity media type is unsupported by the endpoint or converters.

**9. What does invalid JSON syntax with a valid `Content-Type` usually return?**  
400 Bad Request if the converter cannot read the body.

**10. What does `GET /api/widgets/999` return in the demo?**  
404, because the controller cannot find the item.

**11. What does `DELETE` on a GET-only URL usually return?**  
405 Method Not Allowed.

**12. Why use `Vary: Accept`?**  
Because the same URL has distinct JSON/text representations depending on `Accept`, so caches must distinguish them.

**13. Which header should 201 Created verify?**  
`Location`, and you can also follow the location to verify the newly created resource exists.

**14. Why not hardcode ID 100 in POST tests?**  
Because state can change; read the actual ID from the response and verify `Location` matches.

**15. Can `JsonPath` check types?**  
You can combine `JSONPath`, `JsonNode`, and type-specific assertions to distinguish boolean/string/number.

**16. When using Spring Security in a real app, why might a MockMvc POST return 403?**  
Due to CSRF or authorization; you need `security-test` and a valid principal/CSRF token.

**17. Should an app trust absolute `Location` generated from `Forwarded` headers sent by arbitrary clients?**  
No. Only use forwarded metadata from trusted, properly configured proxies.

**18. Does `@JsonTest` verify HTTP status/`Content-Type`?**  
No. It verifies serialization/deserialization outside web HTTP mapping.

**19. Why does MockMvc success not guarantee production ingress works?**  
Because it does not test TCP/TLS, reverse proxies, edge rewrites, socket timeouts, and caching.

**20. Will content negotiation with `Accept: */*` always pick the JSON variant in the demo?**  
Do not assume so. Clients/tests should send explicit `Accept`, or the server should have an unambiguous default variant policy.

## 24. Official References

- **Spring Boot 3.3 – Testing Spring Boot Applications:** https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html — `@WebMvcTest`, `MockMvc`, `@AutoConfigureMockMvc`, `@SpringBootTest(MOCK/RANDOM_PORT)`, `TestRestTemplate`, JSON tests.
- **Spring Framework – MockMvc:** https://docs.spring.io/spring-framework/reference/testing/mockmvc.html — Spring MVC server-side test framework.
- **Spring Framework – MockMvc Assertions:** https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/requests.html — request/response verification through `MockMvc`.
- **Spring Framework – Request Mapping:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html — HTTP method/path/params/headers/consumes/produces matching.
- **Spring Framework – Content Types/Negotiation:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/content-negotiation.html — Accept-based response selection, media type strategies.
- **Spring Framework 6.1 – ResponseEntity HeadersBuilder:** https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/ResponseEntity.HeadersBuilder.html — `cacheControl`, `location`, `varyBy`, `build`.
- **Spring Framework – Message Converters:** https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html — Jackson JSON, `StringHttpMessageConverter`, and converter behavior.
- **Spring Framework – Error Responses:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html — `ProblemDetail` and exception handling.
- **Spring Security – MockMvc Testing:** https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html — CSRF, mock authentication, protected endpoints.
- **HTTP Semantics RFC 9110:** https://www.rfc-editor.org/rfc/rfc9110.html — 200/201/400/404/405/406/415, `Accept`, `Content-Type`, and `Vary` semantics.
- **Spring Boot 3.3.13 Release Announcement:** https://spring.io/blog/2025/06/19/spring-boot-3-3-13-available-now/ — sample version and end of OSS support notice for the 3.3 branch.