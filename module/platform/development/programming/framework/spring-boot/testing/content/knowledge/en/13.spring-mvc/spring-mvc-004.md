# Verifying Status, Headers, Content Type, and Response Content

## 1. Four Aspects of the HTTP Contract in Spring MVC

A Spring MVC endpoint with correct business logic that returns the wrong **HTTP status**, misses a **header**, sets the wrong **Content-Type**, or returns an incorrect **JSON body** can still break clients. Controller tests should therefore check more than "no exception thrown"; they must prove what the client actually receives.

Four main questions:

1. **Status:** What HTTP code is returned for success, resource creation, no body, invalid input, or not found?
2. **Headers:** Do important metadata headers such as `Location`, `Cache-Control`, `ETag`, and `X-Request-Id` match the contract?
3. **Content-Type:** What media type does the response actually carry—for example, `application/json` or `text/plain`? Is the charset wrong or affected by content negotiation?
4. **Response body:** Does the JSON have the right fields, values, data types, arrays, nested objects, business errors, or empty body?

In Spring Boot using **Spring MVC**, `MockMvc` is a common tool: it processes requests using Spring MVC infrastructure with mock request/response objects, **without running an HTTP server on a real port**. A focused `@WebMvcTest` is usually enough to test the web boundary; use `@SpringBootTest` when the goal is multi-layer wiring or an end-to-end server.

A single request might need checks across all four parts:

~~~http
HTTP/1.1 201 Created
Location: /api/items/SKU-7
X-Catalog-Version: v1
Content-Type: application/json

{"sku":"SKU-7","name":"Notebook","quantity":2}
~~~

This is an **illustrative response contract**. Headers like `X-Catalog-Version` are explicitly set by the application; Spring does not emit them automatically for every controller. Actual responses may vary JSON key order because JSON object fields have no semantic ordering.

**Testing goal:** pick a specific behavior, construct a request with exact inputs/headers, and assert the HTTP output per contract. Avoid coupling tests to metadata such as random timestamps, container headers, or error strings outside the contract.

## 2. MockMvc Matchers: Where to Assert?

Typical flow:

~~~java
mvc.perform(get("/api/items/{sku}", "SKU-7")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(header().string("X-Catalog-Version", "v1"))
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.sku").value("SKU-7"));
~~~

This code is **part of a test that has a `MockMvc mvc` bean**. The builders/matchers are typically statically imported from:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
~~~

You can chain `.andExpect(...)` calls or use `.andExpectAll(...)` to group multiple expectations. When inspecting a failing request/response:

~~~java
mvc.perform(get("/api/items/SKU-7"))
   .andDo(print())
   .andExpect(status().isOk());
~~~

`print()` requires a static import from `MockMvcResultHandlers.print`. This is a **local diagnostic tool**; do not tie test assertions to logger stdout or indiscriminately print bodies containing secrets.

Distinguishing the two directions:

| Aspect | Request Configuration | Response Verification |
| --- | --- | --- |
| HTTP method/path | `get(...)`, `post(...)`, `delete(...)` | `status()`, `handler()` if needed |
| Request body media type | `.contentType(MediaType.APPLICATION_JSON)` | `content().contentTypeCompatibleWith(...)` |
| Response format desired by client | `.accept(MediaType.APPLICATION_JSON)` | `content().contentType(...)` or compatible |
| Header sent to server | `.header("X-Trace-Id", "...")` | `header().string(...)` for headers returned by server |
| Outbound/inbound body | `.content(json)` | `jsonPath(...)`, `content().json(...)`, `content().string(...)` |

Calling `contentType(...)` on the **request builder** does not mean the response will carry that `Content-Type`; the controller and message converters determine the response. `accept(...)` signals the format the client accepts during content negotiation, **not** an automatic guarantee that the response is valid.

## 3. Checking HTTP Status: Codes and Meanings Must Match the Scenario

Status reflects processing semantics, not merely "equals 200" everywhere.

| Scenario | Common Code | MockMvc Matcher |
| --- | --- | --- |
| Successful GET retrieval | 200 OK | `status().isOk()` |
| POST creating a resource | 201 Created | `status().isCreated()` |
| Successful DELETE with no body | 204 No Content | `status().isNoContent()` |
| DTO fails validation | 400 Bad Request | `status().isBadRequest()` |
| Unauthenticated | 401 Unauthorized | `status().isUnauthorized()` |
| Insufficient permissions | 403 Forbidden | `status().isForbidden()` |
| Resource does not exist | 404 Not Found | `status().isNotFound()` |
| Method not supported on route | 405 Method Not Allowed | `status().isMethodNotAllowed()` |
| Client requests unproducible response media type | 406 Not Acceptable | `status().isNotAcceptable()` |
| Request sends media type unsupported by controller | 415 Unsupported Media Type | `status().isUnsupportedMediaType()` |
| Resource state conflict | 409 Conflict | `status().isConflict()` |

Responses like `202 Accepted`, `206 Partial Content`, and `304 Not Modified` carry specific semantics; tests must follow the API contract rather than guessing or defaulting codes. To check a specific numeric code beyond named matchers, use `status().is(422)` (when the API actually specifies 422) or the corresponding supported matcher.

### Pitfalls of Asserting Only the Status

- `status().isOk()` **does not prove the body is right**. A controller returning 200 with a body missing `sku` will still PASS.
- `status().isNotFound()` **does not prove the error JSON is right**. Depending on the controller/advice, a 404 response can be empty or contain an error body.
- `status().isCreated()` does not prove `Location` is present; if the contract requires `Location`, assert it explicitly.
- `status().isNoContent()` is not enough to prove an empty body; also assert `content().string("")` when protecting a 204 rule.
- Status 400 from validation differs from status 400 from malformed JSON; depending on your goals, test both causes separately.

Do not write a "GET not found" test by calling **an undeclared path** when the goal is testing the branch where the service returns empty. A 404 from the router not knowing an endpoint is a different contract from `GET /api/items/{sku}` returning 404 because the SKU does not exist.

## 4. Headers: Metadata Is Part of the Contract Too

HTTP headers can control redirects, caching, auth, ETags, cookies, encoding, and tracing. Spring MVC lets you return headers via `ResponseEntity` or response APIs.

| Header | When to Check | Matcher Example |
| --- | --- | --- |
| `Location` | POST creating a resource, redirects | `header().string(HttpHeaders.LOCATION, "/api/items/SKU-7")` |
| `Cache-Control` | Non-cacheable APIs or TTL caching | `header().string(HttpHeaders.CACHE_CONTROL, "no-store")` |
| `ETag` | Cache validation/optimistic representation | `header().string(HttpHeaders.ETAG, "\"v1\"")` |
| `X-Catalog-Version` | Application-defined header | `header().string("X-Catalog-Version", "v1")` |
| `Vary` | Response depends on `Accept`/`Origin` | Assert contracted values; mind multiple tokens |
| `Content-Type` | Response body type | Prefer `content().contentType...` |
| `Content-Disposition` | File downloads, filename | Check when explicitly produced by controller |
| `Set-Cookie` | Sessions/auth/custom cookies | `cookie()` matchers or appropriate header checks |

Common matchers:

~~~java
.andExpect(header().exists(HttpHeaders.LOCATION))
.andExpect(header().string(HttpHeaders.LOCATION, "/api/items/SKU-7"))
.andExpect(header().doesNotExist("X-Deprecated-Flag"))
~~~

This is an **illustrative `andExpect` chain**. `header().string(...)` checks a single header value; `header().exists(...)` proves the header is present. If a header has multiple values, use an appropriate multi-value matcher instead of joining values with commas when parsers might normalize tokens or casing differently.

### Avoid Exact String Matches for Dynamic Headers

`Date`, correlation IDs, tokens, or dynamically generated ETags should not be asserted against a fixed random value. Instead:

- Assert that the header **exists** if the contract only requires presence.
- Assert the **format** using a Hamcrest matcher/regex or parse it into a meaningful type.
- If a value must be echoed from the request, send a fixed ID and assert that exact value.
- Assert exact `Location` only when the path/URI contract is stable; with dynamic host/port, parse the URI and check `path`/`scheme` as required.

HTTP header names are **case-insensitive** per protocol, though characters and spacing inside **values** can matter. Do not write tests requiring `Content-Type` to be stored with `Content-Type` casing instead of `content-type` unless that is somehow contracted.

## 5. Content-Type: Valid JSON Is More Than Just the Media Type Name

`Content-Type` on the **response** tells clients how the body is encoded. For JSON APIs this is usually `application/json`, though frameworks/converters can add parameters like `charset=UTF-8` or emit specialized media types like `application/problem+json`.

Two important matcher styles:

~~~java
.andExpect(content().contentType(MediaType.APPLICATION_JSON))
~~~

This matcher compares the full media type (including parameters). If the response is `application/json;charset=UTF-8`, it **does not necessarily equal** `MediaType.APPLICATION_JSON`.

~~~java
.andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
~~~

This matcher checks **media type compatibility** and is usually preferable when the contract is simply "the response is JSON" without pinning charset parameters. If the contract genuinely requires a specific `charset`, use `content().encoding(...)` or inspect the parsed media type directly.

### Request Content-Type and Accept Are Not Interchangeable

~~~http
POST /api/items
Content-Type: application/json
Accept: application/json

{"sku":"SKU-7","name":"Notebook","quantity":2}
~~~

- Inbound `Content-Type`: tells the server how to interpret **the data the client sent**, e.g. JSON.
- Inbound `Accept`: tells the server which media type the client **wants back**.
- Outbound `Content-Type`: tells the client which response type the server actually **selected and generated**.

If a method has `@PostMapping(consumes = "application/json")` and the client sends `text/plain`, it typically receives **415**. If `@GetMapping(produces = "application/json")` is used but the client accepts only `application/xml`, it typically receives **406**. Such tests verify that the controller/request mapping is properly configured and no unintended converter handles that media type.

### Do Not Force Content-Type on Bodyless Responses

`204 No Content` has no response body. Do not assert that every empty 204/304/404 response **must have** `application/json`: when code writes no body, the message converter might not set `Content-Type`. Likewise, do not assume every exception in a `@WebMvcTest` produces the same error JSON format as the production server; `@ControllerAdvice` and error-handling configuration determine that.

## 6. Response Body: Comparing the Right Data Shape

### JSONPath for Key Fields

~~~java
.andExpect(jsonPath("$.sku").value("SKU-7"))
.andExpect(jsonPath("$.quantity").value(2))
.andExpect(jsonPath("$.name").value("Notebook"))
~~~

JSONPath inspects the **parsed JSON structure**, independent of whitespace or key order. For nested objects, use `$.customer.id`; for arrays, use `$[0].sku` or `$.items[0].sku`. Matchers like `exists()`, `doesNotExist()`, `isArray()`, and `isNotEmpty()` are useful when chosen with the exact semantics in mind.

**Distinguishing present vs. null:** `jsonPath("$.middleName").doesNotExist()` expresses that no non-null value exists according to matcher semantics; it is not identical to "key is present with value `null`". When you need to distinguish all three states—**absent / JSON null / empty string**—parse the response JSON into a `JsonNode` and check `has`/`isNull`/`asText`.

### content().json for Objects or Arrays

With Spring Framework 6.2+:

~~~java
.andExpect(content().json(
        """
        {"sku":"SKU-7","name":"Notebook","quantity":2}
        """,
        JsonCompareMode.STRICT
))
~~~

`JsonCompareMode` is `org.springframework.test.json.JsonCompareMode`. `STRICT` forbids extra fields and requires matching array order, while **not enforcing JSON object key order**. `LENIENT` allows extra fields on JSON objects and may relax array ordering per comparator rules. If the API has a closed schema contract, `STRICT` helps catch unexpected extra fields; if the API intentionally adds fields over time that a given test does not care about, JSONPath on critical fields is usually more resilient.

JSON comparison helpers may require the JSONassert library on the classpath; with Spring Boot 3.5, `spring-boot-starter-test` normally includes the needed test dependencies.

### content().string for Plain Text and Empty Bodies

If the endpoint returns explicit plain text:

~~~java
.andExpect(content().string("ready"))
~~~

If the contract specifies no response body:

~~~java
.andExpect(content().string(""))
~~~

**Do not compare JSON as raw strings** unless property order and whitespace are actually part of the contract. For instance, `{"a":1,"b":2}` and `{"b":2,"a":1}` represent the exact same JSON object semantically even though their raw strings differ.

## 7. Runnable Example: Spring Boot 3.5, Java 17, @WebMvcTest, and MockMvc

We build an `/api/items` API. Per the contract:

- `GET /api/items/{sku}`: returns **200**, headers `X-Catalog-Version: v1`, `Cache-Control: no-store`, `Content-Type: application/json`, and the item body if found; returns **404** and an empty body if the SKU is absent.
- `POST /api/items` accepting JSON with valid SKU, name, and quantity: returns **201**, a `Location` header pointing to the resource URI, the version header, and the created JSON body. For data violating validation, returns **400** before calling the catalog.
- `DELETE /api/items/{sku}`: returns **204** and an empty body when deleted, or **404** if absent.

All files share package `com.example.mvctest`, Java 17+, JUnit Jupiter. The test uses a **real controller** and mocks `ItemCatalog` in the Spring context. No HTTP port is opened, and no database is called.

### 7.1. Sample Application

**File `src/main/java/com/example/mvctest/MvcTestApplication.java`:**

~~~java
package com.example.mvctest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcTestApplication.class, args);
    }
}
~~~

This is the root configuration class discovered by Spring Boot test. `@WebMvcTest` still starts only a **web slice**, does not execute `main`, and does not automatically scan all application services or repositories.

**File `src/main/java/com/example/mvctest/ItemView.java`:**

~~~java
package com.example.mvctest;

public record ItemView(String sku, String name, int quantity) {
}
~~~

**File `src/main/java/com/example/mvctest/CreateItemRequest.java`:**

~~~java
package com.example.mvctest;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateItemRequest(
        @NotBlank String sku,
        @NotBlank String name,
        @Min(1) int quantity
) {
}
~~~

Constraints on `CreateItemRequest` execute when Spring MVC processes `@Valid @RequestBody` with a compatible Jakarta validation provider. A Java record itself **does not run validation** when instantiated via `new`.

**File `src/main/java/com/example/mvctest/ItemCatalog.java`:**

~~~java
package com.example.mvctest;

import java.util.Optional;

public interface ItemCatalog {
    Optional<ItemView> findBySku(String sku);

    ItemView create(CreateItemRequest request);

    boolean remove(String sku);
}
~~~

This is the mocked collaborator in the web slice. In a real application, this interface would be implemented by a service calling a repository. Controller tests only stub the mock's behavior and verify the HTTP contract; they **do not test persistence**.

### 7.2. Real Controller Intentionally Returning Status/Headers/Body

**File `src/main/java/com/example/mvctest/ItemController.java`:**

~~~java
package com.example.mvctest;

import java.net.URI;

import jakarta.validation.Valid;

import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

@RestController
@RequestMapping("/api/items")
public class ItemController {
    private final ItemCatalog catalog;

    public ItemController(ItemCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping(
            value = "/{sku}",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<ItemView> findBySku(
            @PathVariable String sku
    ) {
        return catalog.findBySku(sku)
                .map(item -> ResponseEntity.ok()
                        .cacheControl(CacheControl.noStore())
                        .header("X-Catalog-Version", "v1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(item))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<ItemView> create(
            @Valid @RequestBody CreateItemRequest request
    ) {
        ItemView saved = catalog.create(request);
        URI location = UriComponentsBuilder
                .fromPath("/api/items/{sku}")
                .encode()
                .buildAndExpand(saved.sku())
                .toUri();

        return ResponseEntity.created(location)
                .header("X-Catalog-Version", "v1")
                .contentType(MediaType.APPLICATION_JSON)
                .body(saved);
    }

    @DeleteMapping("/{sku}")
    public ResponseEntity<Void> delete(@PathVariable String sku) {
        if (catalog.remove(sku)) {
            return ResponseEntity.noContent().build();
        }
        return ResponseEntity.notFound().build();
    }
}
~~~

Important details in the controller:

- `ResponseEntity.ok()` sets 200; `created(location)` sets 201 + `Location`; `noContent()` sets 204.
- `CacheControl.noStore()` emits the `Cache-Control: no-store` directive, instructing clients/caches not to store the response.
- `contentType(MediaType.APPLICATION_JSON)` explicitly specifies JSON responses when a body is present.
- `UriComponentsBuilder.fromPath(...).encode().buildAndExpand(...)` builds the URI path and encodes path variables properly; in the test, the SKU is `SKU-7`, keeping `Location` deterministic.
- `@Valid` ensures invalid payloads are rejected at the web boundary before calling `catalog.create(...)`, provided a validation provider is on the classpath.
- Not-found GET and not-found DELETE explicitly return `ResponseEntity.notFound().build()` with an empty body; **do not assume** a JSON error envelope is present if none has been designed.

### 7.3. Test Verifying All Four Response Aspects

**File `src/test/java/com/example/mvctest/ItemControllerTest.java`:**

~~~java
package com.example.mvctest;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.json.JsonCompareMode;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ItemController.class)
class ItemControllerTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    ItemCatalog catalog;

    @Test
    void getItem_whenFound_returns200HeadersJsonAndFields()
            throws Exception {
        ItemView item = new ItemView("SKU-7", "Notebook", 2);
        when(catalog.findBySku("SKU-7"))
                .thenReturn(Optional.of(item));

        mvc.perform(get("/api/items/{sku}", "SKU-7")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Catalog-Version", "v1"
                ))
                .andExpect(header().string(
                        HttpHeaders.CACHE_CONTROL, "no-store"
                ))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                ))
                .andExpect(jsonPath("$.sku").value("SKU-7"))
                .andExpect(jsonPath("$.name").value("Notebook"))
                .andExpect(jsonPath("$.quantity").value(2))
                .andExpect(content().json(
                        """
                        {"sku":"SKU-7","name":"Notebook","quantity":2}
                        """,
                        JsonCompareMode.STRICT
                ));

        verify(catalog).findBySku("SKU-7");
    }

    @Test
    void getItem_whenUnknown_returns404AndEmptyBody()
            throws Exception {
        when(catalog.findBySku("MISSING"))
                .thenReturn(Optional.empty());

        mvc.perform(get("/api/items/{sku}", "MISSING")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andExpect(content().string(""));

        verify(catalog).findBySku("MISSING");
    }

    @Test
    void postItem_whenValid_returns201LocationHeadersAndJson()
            throws Exception {
        CreateItemRequest request =
                new CreateItemRequest("SKU-7", "Notebook", 2);
        ItemView saved = new ItemView("SKU-7", "Notebook", 2);
        when(catalog.create(request)).thenReturn(saved);

        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "sku":"SKU-7",
                                  "name":"Notebook",
                                  "quantity":2
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        HttpHeaders.LOCATION, "/api/items/SKU-7"
                ))
                .andExpect(header().string(
                        "X-Catalog-Version", "v1"
                ))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                ))
                .andExpect(jsonPath("$.sku").value("SKU-7"))
                .andExpect(jsonPath("$.quantity").value(2));

        verify(catalog).create(request);
    }

    @Test
    void postItem_whenInvalid_returns400BeforeCallingCatalog()
            throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "sku":" ",
                                  "name":"Notebook",
                                  "quantity":0
                                }
                                """))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(catalog);
    }

    @Test
    void postItem_whenRequestIsText_returns415()
            throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("not-json"))
                .andExpect(status().isUnsupportedMediaType());

        verifyNoInteractions(catalog);
    }

    @Test
    void getItem_whenClientAcceptsOnlyXml_returns406()
            throws Exception {
        mvc.perform(get("/api/items/{sku}", "SKU-7")
                        .accept(MediaType.APPLICATION_XML))
                .andExpect(status().isNotAcceptable());

        verifyNoInteractions(catalog);
    }

    @Test
    void deleteItem_whenRemoved_returns204AndEmptyBody()
            throws Exception {
        when(catalog.remove("SKU-7")).thenReturn(true);

        mvc.perform(delete("/api/items/{sku}", "SKU-7"))
                .andExpect(status().isNoContent())
                .andExpect(content().string(""));

        verify(catalog).remove("SKU-7");
    }

    @Test
    void deleteItem_whenMissing_returns404()
            throws Exception {
        when(catalog.remove("MISSING")).thenReturn(false);

        mvc.perform(delete("/api/items/{sku}", "MISSING"))
                .andExpect(status().isNotFound())
                .andExpect(content().string(""));

        verify(catalog).remove("MISSING");
    }
}
~~~

### Explaining Each Assertion Group

1. **GET 200:** combines `status`, two response headers, `Content-Type`, JSONPath on three fields, and strict JSON comparison. Additional `verify` confirms the controller passed the right SKU.
2. **GET 404:** tests the same `/api/items/{sku}` route with the dependency returning `Optional.empty()`. This is the **business missing-resource branch**, not merely a 404 from an invalid URL.
3. **POST 201:** checks status, `Location` matching the created resource, custom header, JSON media type, and returned body.
4. **POST 400:** `@Valid` rejects blank SKU and quantity 0; mock catalog is never called. The test intentionally **does not assert an error JSON body** because the example defines no global error handler/body.
5. **POST 415:** the controller only `consumes = application/json`, but the request sends `text/plain`.
6. **GET 406:** the method only `produces = application/json`, but the client only specifies `Accept: application/xml`.
7. **DELETE 204/404:** proves the status code and empty body reflect the collaborator's result.

### Why Is @SpringBootTest Not Needed?

`@WebMvcTest(ItemController.class)` loads MVC controllers, converters, validation, slice-scoped advice/filters, and `MockMvc`. `ItemCatalog` is an out-of-slice collaborator, so `@MockitoBean` creates a mock bean in the context. This tests the **controller's HTTP contract** without needing a real service or repository.

In Spring Boot 3.4/3.5, `@MockitoBean` comes from Spring Framework 6.2. In Boot 3.3 and earlier, the matching API is Spring Boot's `@MockBean`; pick the annotation that matches your version. Never use plain `@Mock` expecting it to replace a Spring bean.

If the application has Spring Security, the filter chain may return 401/403 before the controller. The example assumes **security is not installed**; in projects with security, use `spring-security-test` and configure auth/CSRF per contract rather than unconditionally disabling filters.

## 8. Dependencies, Project Layout, and Run Commands

In a **Spring Boot 3.5.x, Java 17** project using Gradle Groovy DSL, the relevant dependencies/test task block is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is a **`build.gradle` snippet**, assuming the project already declares the Spring Boot 3.5.x plugin, repositories, dependency management, and Java 17+ toolchain/JDK.

- `spring-boot-starter-web` provides Spring MVC, Jackson, and servlet web infrastructure.
- `spring-boot-starter-validation` provides the Jakarta validation API/provider so `@Valid` + `@NotBlank`/`@Min` take effect.
- `spring-boot-starter-test` provides JUnit Jupiter, MockMvc, Mockito, and test helpers including JSON comparison support.

Place all 6 files (application, 3 model/interface/controller files, and test; verify all files `MvcTestApplication`, `ItemView`, `CreateItemRequest`, `ItemCatalog`, `ItemController`, `ItemControllerTest`) under the paths shown in Section 7.

Run from the directory containing the Gradle Wrapper:

~~~bash
./gradlew test --tests "com.example.mvctest.ItemControllerTest"
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.mvctest.ItemControllerTest"
~~~

When dependencies and configuration match, the suite of eight tests will PASS. The tests do not intentionally call `System.out.println`, so there is **no fixed stdout** from application code; Gradle/JUnit output varies by log level and version. This code depends on Spring/Mockito/JUnit and cannot be run via plain `javac ItemControllerTest.java` without assembling the corresponding classpath.

## 9. When You Need to Check a Uniform JSON Error Body

Many APIs prefer not to return empty bodies for 400/404 errors and instead adopt an error envelope:

~~~json
{
  "code": "ITEM_NOT_FOUND",
  "message": "Item does not exist"
}
~~~

This is an **illustrative specification**, not automatic JSON emitted by every `@WebMvcTest`. To meaningfully test an error body, the controller or `@ControllerAdvice` must actually return that object, and the test slice must load that advice.

One standalone alternative inside the controller:

~~~java
record ApiError(String code, String message) {
}

@GetMapping("/{sku}")
public ResponseEntity<?> findBySku(@PathVariable String sku) {
    return catalog.findBySku(sku)
            .<ResponseEntity<?>>map(item -> ResponseEntity.ok(item))
            .orElseGet(() -> ResponseEntity.status(404)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new ApiError(
                            "ITEM_NOT_FOUND", "Item does not exist"
                    )));
}
~~~

**This code snippet is an alternative approach**, not an extra method to paste into `ItemController` from Section 7 (since `@GetMapping` would collide). It requires the accompanying imports/record in the same class. When adopting this approach, error tests then have a real basis to assert:

~~~java
.andExpect(status().isNotFound())
.andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
.andExpect(jsonPath("$.code").value("ITEM_NOT_FOUND"))
.andExpect(jsonPath("$.message").value("Item does not exist"))
~~~

Do not mix the alternative's expected error body into tests for the original controller, where the `notFound().build()` branch intentionally returns no body.

### @ControllerAdvice and Exception Handlers

If using `@RestControllerAdvice` to map exceptions into bodies (or `ProblemDetail`), tests should assert **status + Content-Type + stable fields** such as `code`/`type`/`title`/`status` per the API. Avoid asserting verbatim timestamps, localized details, or server-generated paths unless they are contracted.

Spring Framework provides `ProblemDetail`/RFC Problem Details whose media type is typically `application/problem+json`. If an application actually returns `application/problem+json`, assert against that exact contract; **do not force `MediaType.APPLICATION_JSON`** when a dedicated Problem Details media type was chosen.

## 10. Checking Arrays, Nested Objects, Nulls, and Missing Fields

For an item-listing API:

~~~json
{
  "items": [
    {"sku":"A-1","quantity":2},
    {"sku":"B-2","quantity":5}
  ],
  "total": 2,
  "nextPage": null
}
~~~

We can verify the structure using JSONPath:

~~~java
.andExpect(jsonPath("$.items").isArray())
.andExpect(jsonPath("$.items[0].sku").value("A-1"))
.andExpect(jsonPath("$.items[1].quantity").value(5))
.andExpect(jsonPath("$.total").value(2))
~~~

This is an **illustrative matcher snippet** for an endpoint actually returning the JSON above, not a new method in Section 7's test suite. These assertions check array ordering if the API specifies sorting; if the list order is not guaranteed, avoid hardcoding indices and instead compare contents as sets or stabilize/sort input data.

To distinguish a `nextPage` key that is **present and null** from an omitted key, parse the JSON with Jackson:

~~~java
MvcResult result = mvc.perform(get("/api/items"))
        .andExpect(status().isOk())
        .andReturn();

JsonNode body = objectMapper.readTree(
        result.getResponse().getContentAsString()
);

assertTrue(body.has("nextPage"));
assertTrue(body.get("nextPage").isNull());
~~~

This is a **test snippet assuming a `GET /api/items` endpoint**, an `ObjectMapper objectMapper` bean, and imports for `MvcResult`, `JsonNode`, and `assertTrue`; it does not run standalone. `has(...)` indicates the field is present even when its JSON value is null, while `isNull()` verifies the field actually holds JSON null.

For objects with additional properties, `content().json(..., JsonCompareMode.STRICT)` is useful when the API publishes a closed schema. For extensible APIs, assert only the required contract fields; do not assert the absence of all other fields unless security or compatibility demands it.

## 11. Impact of Content Negotiation, MessageConverter, and Encoding

When a controller returns a Java object, Spring MVC uses an `HttpMessageConverter` to serialize the object into response bytes. The Jackson JSON converter normally produces a JSON body if Jackson is on the classpath, the endpoint supports JSON, and the client accepts that media type.

General pipeline:

~~~text
MockMvc.perform(request)
    -> HandlerMapping: finds route
    -> ArgumentResolver: binds input, @RequestBody
    -> Validation (if @Valid and provider)
    -> Controller calls collaborator
    -> ReturnValueHandler handles ResponseEntity
    -> HttpMessageConverter serializes body
    -> MockHttpServletResponse
    -> status / headers / content type / body
~~~

This diagram omits filters, interceptors, advice, and proxies, yet clearly shows **why tests must go through MockMvc** rather than calling `controller.findBySku("SKU-7")` directly when testing HTTP responses.

- Calling the controller directly can verify `ResponseEntity.getStatusCode()` and custom headers created in Java, but **does not verify JSON serialization, request mapping, or media negotiation**.
- `.accept(MediaType.APPLICATION_JSON)` only declares willingness to receive JSON; if the controller misconfigures `produces` or lacks a converter, the response can fail with 406/500.
- `.contentType(MediaType.APPLICATION_JSON)` on the request tells the parser to read JSON; if the body is malformed, Spring can return 400 before invoking the method.
- For text responses, charset can affect `getContentAsString()`. If a test checks exact Unicode characters, configure encoding explicitly and use `content().encoding(StandardCharsets.UTF_8)` when that is part of the contract.

**Do not assume `charset=UTF-8` is present in every `application/json`.** Under modern JSON standards, UTF-8 is standard, and Spring/Jackson often omit an explicit charset parameter from JSON `Content-Type`. `contentTypeCompatibleWith` fits when you only need the media type, while `encoding(...)` fits when encoding itself is a requirement.

## 12. When to Use Flexible Matchers Instead of Exact Equality

| Check Type | Exact Match When | More Flexible When |
| --- | --- | --- |
| HTTP status | Specific status code is contracted, e.g. POST must be 201 | Testing only 2xx is rarely sufficient for public APIs |
| `Location` header | Fixed path is required | Dynamic host/port: parse URI and check path |
| `Cache-Control` header | Exact directive string is specified by API | Extra valid directives may appear: parse tokens per contract |
| `Content-Type` | Protocol dictates full media type and params | JSON may include charset: use compatible matching |
| JSON body | Closed API schema forbidding extra fields | Extensible API: JSONPath on essential fields |
| Text body | Exact verbatim string is the contract | Localized or routine log messages vary |
| Array order | API explicitly specifies sorting | Unsorted: compare independent of order |
| Timestamp | Input uses a fixed `Clock` | Real-time data: check format/reasonable range |

### Useful Matchers Beyond the Example

~~~java
.andExpect(header().exists("X-Trace-Id"))
.andExpect(header().doesNotExist("X-Deprecated-Flag"))
.andExpect(content().string(""))
.andExpect(jsonPath("$.items").isArray())
.andExpect(jsonPath("$.items[0].sku").exists())
~~~

This is an **illustrative matcher snippet**. Do not apply all of these simultaneously to an endpoint that does not return `items` arrays. Write assertions for outputs **actually designed**, not fields that merely "seem nice to have."

For `ETag`, values are normally enclosed in double quotes per protocol; if a controller sets `eTag("v1")`, expect a header like `ETag: "v1"`. If the API supports conditional `If-None-Match`/304, test conditional GET behavior separately; asserting only that an `ETag` header exists does not prove full cache validation behavior.

## 13. Response Status vs. Resolved Exception and Handler

MockMvc also provides matchers to inspect Spring MVC internals:

~~~java
.andExpect(handler().handlerType(ItemController.class))
.andExpect(handler().methodName("findBySku"))
~~~

This is an **optional matcher snippet** requiring static import `MockMvcResultMatchers.handler`. It is helpful if a test must confirm a route maps to a specific method, though it can make tests brittle when refactoring controller internals without changing the HTTP contract.

For HTTP errors, you can inspect the exception handled by `@ControllerAdvice`/resolvers via `result.getResolvedException()` (after `andReturn()`). However, clients **do not see** Java exceptions; they see status/headers/body. Therefore **prefer asserting the HTTP contract**; assert exception classes only when testing framework infrastructure specifically.

`MockMvc` runs through Spring MVC request handling on mock servlet objects, **not through a real servlet container**. Behaviors tied to container error-page mappings, reverse-proxy compression, TLS, or gateway-added headers **are not proven** by a web slice. To test real end-to-end sockets, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` with an appropriate client and test environment.

## 14. Common Mistakes When Testing Status, Headers, Content, and Body

1. **Asserting only 200.** Tests stay green even when the JSON response has wrong fields or missing headers. **Fix:** check all essential contract parts.
2. **Confusing request `Content-Type` with response `Content-Type`.** Calling `.contentType(...)` before `perform` proves nothing about the response. **Fix:** use `content().contentType...` after `perform`.
3. **Confusing `Accept` with request body media type.** A client accepting JSON does not mean its request payload is JSON. **Fix:** set both according to their roles.
4. **Using `content().string(exactJson)` on JSON.** Key order and whitespace are not stable guarantees under JSON contracts. **Fix:** use `jsonPath` or `content().json`.
5. **Comparing exact `application/json` when the server adds a charset.** Tests break over non-contract parameters. **Fix:** use `contentTypeCompatibleWith(MediaType.APPLICATION_JSON)`.
6. **Requiring JSON `Content-Type` on empty 204/404 responses.** No converter may run. **Fix:** assert status and empty body; assert `Content-Type` only if specified by the API.
7. **Testing 404 using a wrong URL instead of the service-not-found branch.** Fails to prove the controller handles missing records. **Fix:** stub the collaborator to return empty on the valid route.
8. **POST 201 forgetting `Location`.** Clients do not receive the new resource URI specified by the API contract. **Fix:** assert `HttpHeaders.LOCATION`.
9. **Using Mockito `@Mock` expecting the Spring controller to receive it.** The controller bean may use another dependency or fail to wire. **Fix:** use `@MockitoBean` for your version in Spring TestContext.
10. **Asserting verbatim error JSON that has not been designed.** Boot/resolver bodies may be empty or vary by config. **Fix:** define an explicit error contract via advice/controller and assert stable fields.
11. **Overlooking security filters.** Tests receive 401/403 for missing auth/CSRF and get misdiagnosed as controller bugs. **Fix:** configure `spring-security-test` appropriately.
12. **Hardcoding dynamic headers/times/IDs.** Tests fail intermittently when timestamps or ports change. **Fix:** fix inputs or assert structure/format.
13. **Not testing 415/406.** `consumes`/`produces` declarations can be broken without happy-path tests noticing. **Fix:** add negative content-negotiation tests when part of the contract.
14. **Calling the controller directly and claiming HTTP is tested.** Message converters and request mappings never executed. **Fix:** use MockMvc.
15. **Using `@SpringBootTest` for every JSON check.** Starts the entire application unnecessarily. **Fix:** `@WebMvcTest` for the MVC boundary or `@JsonTest` when testing serialization alone.
16. **Using regex/substrings instead of a JSON parser for nested fields.** Breaks easily if formatting changes. **Fix:** JSONPath/Jackson `JsonNode`.
17. **Asserting every default header/stack trace.** Couples tests to container/framework internals. **Fix:** assert only headers required by the contract.
18. **Not testing empty bodies.** A DELETE returning 204 that accidentally emits JSON can slip through. **Fix:** add `content().string("")`.

## 15. Practical Workflow and Code Review Checklist

When tasked with testing a Spring MVC endpoint:

1. **Write an HTTP contract table:** method + path, request headers/body, status, response headers/body for each scenario.
2. **Choose the test layer:** `@WebMvcTest` for just the web boundary, `@JsonTest` for just JSON mapping, `@SpringBootTest` when the full system or a real server is needed.
3. **Keep the controller real:** mock out-of-slice collaborators with `@MockitoBean`, never mocking the class under test.
4. **Arrange:** stub catalog/service inputs and outputs, fixing IDs and test data.
5. **Act:** call `mvc.perform(...)` with the right HTTP method, path, request `Content-Type`, `Accept`, and body.
6. **Assert:** check **status → headers → response `Content-Type` → body**, keeping assertions to what the scenario contracts.
7. **Verify collaborations:** use `verify` when collaborator calls are core behavior; verify validation rejections never call dependencies.
8. **Add negative cases:** missing entity, invalid payload, unsupported request media type, unacceptable response media type, empty body.
9. **Run both standalone and in the suite:** avoid relying on leftover Mockito state or test class execution order.
10. **Check stability:** do not assert dynamic metadata or depend on servlet container internals inside mock MVC tests.

Checklist:

- [ ] HTTP methods/paths and valid/error scenarios are categorized.
- [ ] 200, 201, 204, 400, 404 (and 406/415 if needed) are tested in the right scenarios, not assigned arbitrarily.
- [ ] `Location`, cache, version/correlation headers, or `ETag` are asserted only when part of the contract.
- [ ] Request `Content-Type`, request `Accept`, and response `Content-Type` are clearly distinguished.
- [ ] Response JSON is compared by structure/fields, not character ordering.
- [ ] 204 and empty-body cases include empty-body assertions.
- [ ] Validation errors do not invoke collaborators when requests are rejected at the MVC boundary.
- [ ] Error JSON is asserted only when a handler/controller explicitly defines it.
- [ ] Spring Security, filters, and custom advice are configured to match the test goal.
- [ ] Tests do not claim to prove TLS, proxies, container error pages, or full persistence.
- [ ] Imports match the Spring Boot/Spring Framework/JUnit versions used in the actual project.

**Remember:** A reliable Spring MVC test does not just ask "did the request reach the controller?", it asks **"what exact status code, headers, media type, and body does the client receive?"** `MockMvc` + `@WebMvcTest` verifies that contract quickly and independently of real services or databases, provided assertions reflect designed behavior.

### References

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring Framework 6.2 — Defining Expectations](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/expectations.html)
- [Spring Framework 6.2 — ContentResultMatchers API](https://docs.spring.io/spring-framework/docs/6.2.17/javadoc-api/org/springframework/test/web/servlet/result/ContentResultMatchers.html)
- [Spring Framework — HTTP Content Negotiation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/content-negotiation.html)