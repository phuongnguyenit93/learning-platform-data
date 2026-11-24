# The `params`, `headers`, `consumes`, and `produces` Conditions in Spring WebFlux

## 1. Objectives

In Spring WebFlux, `@RequestMapping` selects a controller handler based on multiple conditions of the HTTP request, not only the URL and HTTP method. Four commonly used attributes to narrow down a mapping are:

- **`params`**: a query parameter must be present, must be absent, or must carry a matching value.
- **`headers`**: a request header must be present, must be absent, or must carry a matching value.
- **`consumes`**: the media type of the request body that the handler accepts, usually taken from `Content-Type`.
- **`produces`**: the response media type that the handler can generate, matched against `Accept` through content negotiation.

These are **handler-selection conditions**. They are evaluated before the controller method runs. They differ from argument binding (`@RequestParam`, `@RequestHeader`, `@RequestBody`), decoding the body, validating data, or serializing the response.

After this lesson, you can read and write condition expressions, understand how class-level and method-level mappings combine, predict common HTTP errors, and test with `WebTestClient`.

## 2. How Is a Handler Selected for a Request?

```text
HTTP request
    |
    v
Path / URI pattern
    |
    v
HTTP method
    |
    v
params condition
    |
    v
headers condition
    |
    v
consumes condition (Content-Type)
    |
    v
produces condition (Accept)
    |
    v
Select matching handler
    |
    v
Controller -> service -> response body
```

Example:

```java
@PostMapping(
        path = "/orders",
        params = "source=partner",
        headers = "X-Partner-Version=2",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
)
public Mono<OrderResponse> create(
        @RequestBody Mono<CreateOrder> body) {
    return body.flatMap(orderService::create);
}
```

The method is selected only when the path, HTTP method, query parameter, header, and both media-type conditions all match. Once the handler has been selected, the message reader decodes the body into `CreateOrder`; only then do the controller and service handle the business logic. A successful mapping does not guarantee valid JSON or valid data.

| Attribute | Question | Data source |
|---|---|---|
| `params` | Does the query parameter satisfy the condition? | URL query string |
| `headers` | Does the header satisfy the condition? | HTTP request headers |
| `consumes` | Does the server accept a body of this media type? | `Content-Type` |
| `produces` | Can the server return a format the client accepts? | `Accept` |

## 3. `params`: Conditions on Query Parameters

`params` accepts one or more expressions. All expressions in a mapping must be satisfied together.

| Expression | Meaning |
|---|---|
| `"mode"` | The query parameter `mode` must be present |
| `"!mode"` | The query parameter `mode` must be absent |
| `"mode=compact"` | `mode` must have the value `compact` |
| `"mode!=compact"` | `mode` must not have the value `compact` |

Example of two handlers on the same path handling two response shapes:

```java
@GetMapping(path = "/reports", params = "format=compact")
public Mono<Report> compact() {
    return reportService.compact();
}

@GetMapping(path = "/reports", params = "format=full")
public Mono<Report> full() {
    return reportService.full();
}
```

```text
GET /reports?format=compact  -> compact()
GET /reports?format=full     -> full()
```

Combining multiple conditions:

```java
@GetMapping(
        path = "/reports",
        params = {"format=compact", "tenant", "!debug"}
)
public Mono<Report> compactForTenant() {
    return reportService.compact();
}
```

The request needs `format=compact`, must have the `tenant` parameter, and must not have the `debug` parameter. The conditions in the array are combined with AND.

### `params` Differs from `@RequestParam`

```java
@GetMapping(path = "/search", params = "scope=public")
public Flux<Result> search(
        @RequestParam("q") String query,
        @RequestParam(defaultValue = "20") int limit) {
    return searchService.searchPublic(query, limit);
}
```

- `params="scope=public"` decides whether the method is selected.
- `@RequestParam("q")` binds the value of `q` into the argument.
- `defaultValue="20"` is a binding rule for `limit`, not a mapping condition.

In WebFlux, `@RequestParam` binds query parameters. Form data and multipart are accessed using WebFlux's own mechanisms; do not assume the Servlet request parameter concept applies unchanged.

## 4. `headers`: Conditions on Request Headers

The `headers` syntax is similar to `params`, but applies to HTTP headers:

| Expression | Meaning |
|---|---|
| `"X-Client"` | The header must be present |
| `"!X-Client"` | The header must be absent |
| `"X-Client=mobile"` | The header must have the value `mobile` |
| `"X-Client!=mobile"` | The header must not have the value `mobile` |

Example:

```java
@GetMapping(path = "/dashboard", headers = "X-Client=mobile")
public Mono<Dashboard> mobile() {
    return dashboardService.mobile();
}

@GetMapping(path = "/dashboard", headers = "X-Client=web")
public Mono<Dashboard> web() {
    return dashboardService.web();
}
```

A request with `X-Client: mobile` matches the `mobile()` method.

Multiple conditions can be combined:

```java
@GetMapping(
        path = "/offers",
        params = "region=apac",
        headers = {"X-Channel=partner", "X-Partner-Id"}
)
public Flux<Offer> partnerOffers() {
    return offerService.partnerOffers();
}
```

The request needs `region=apac`, `X-Channel` with the value `partner`, and the `X-Partner-Id` header present.

Header names are case-insensitive per HTTP rules. Do not assume all header values are case-insensitive as well; follow the contract of the specific header.

### Do Not Use `headers` Instead of `consumes` or `produces`

You can check `Content-Type` or `Accept` with a header expression, but Spring has dedicated attributes for media types:

- `consumes` expresses the request body format.
- `produces` expresses the response format that can be negotiated.

Using these two attributes lets the mapping express its exact intent and be handled by the framework with media-type semantics.

## 5. `consumes`: Media Type of the Request Body

`consumes` restricts the media types the endpoint accepts, usually matched against the `Content-Type` request header.

```java
@PostMapping(
        path = "/products",
        consumes = MediaType.APPLICATION_JSON_VALUE
)
public Mono<Product> create(@RequestBody Mono<CreateProduct> body) {
    return body.flatMap(productService::create);
}
```

Matching request:

```http
POST /products HTTP/1.1
Content-Type: application/json
Accept: application/json

{"name":"Keyboard"}
```

If the client sends `Content-Type: text/plain`, the JSON mapping does not match and WebFlux usually returns **415 Unsupported Media Type**.

You can declare multiple media types:

```java
@PostMapping(
        path = "/imports",
        consumes = {
                MediaType.APPLICATION_JSON_VALUE,
                "text/csv"
        }
)
public Mono<ImportResult> importData(@RequestBody Mono<String> body) {
    return body.flatMap(importService::process);
}
```

One of the declared media types can match. However, declaring `text/csv` does not provide a CSV parser automatically; the application still needs logic to read that format and a compatible message reader.

### Wildcards and Negation

```java
@PostMapping(path = "/text", consumes = "text/*")
public Mono<String> acceptText(@RequestBody Mono<String> body) {
    return body;
}
```

`text/*` accepts media types in the text group if the codec can read the requested body type.

You can use a negation expression:

```java
@PostMapping(path = "/payload", consumes = "!text/plain")
public Mono<Void> acceptNonPlainText(@RequestBody Mono<byte[]> body) {
    return body.then();
}
```

A negation expression can widen the acceptance scope beyond the formats the application actually supports. An explicit allowlist is usually easier to maintain.

### Media Type Parameters and Body Decoding

A media type can have parameters, for example `application/json;charset=UTF-8`. Spring has parameter-matching rules: if both the condition and the request have the corresponding parameter, the values must be compatible; if the request does not send that parameter, matching may ignore the parameter according to Spring's semantics.

`consumes` only checks the media type. If Content-Type is right but the JSON is syntactically invalid or cannot be converted into the DTO, the error happens at the body reading/decoding step, usually mapped to 400. Field validation and business validation are separate steps as well.

## 6. `produces`: Media Type of the Response

`produces` describes the response format the handler can generate. Spring matches this condition against the media types the client accepts, usually sent via `Accept`.

```java
@GetMapping(
        path = "/products/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
)
public Mono<Product> find(@PathVariable String id) {
    return productService.find(id);
}
```

If the client sends `Accept: application/json`, the mapping matches. If the client only accepts `text/plain` while the handler only produces JSON, WebFlux usually returns **406 Not Acceptable**.

You can declare multiple representations:

```java
@GetMapping(
        path = "/catalog",
        produces = {
                MediaType.APPLICATION_JSON_VALUE,
                MediaType.APPLICATION_XML_VALUE
        }
)
public Mono<Catalog> catalog() {
    return catalogService.load();
}
```

The application needs an encoder/codec suitable for the chosen representation. Declaring `produces=application/xml` does not automatically install Jackson XML or an XML codec.

### Accept, Wildcards, and q-values

Examples:

| `Accept` | Meaning |
|---|---|
| `application/json` | Client accepts JSON |
| `application/*` | Client accepts media types under application |
| Wildcard of any kind | Client places no media-type restriction |
| `application/json, text/plain` | Client accepts multiple types |
| `application/json;q=0.9, text/plain;q=0.5` | JSON is preferred over text |

If the request has no `Accept`, typically the client places no specific restriction and any media type can be considered acceptable. When there are multiple options, content negotiation and available message writers decide the suitable representation.

You can use negation such as `produces="!text/plain"`, but that does not guarantee every remaining media type has an encoder. Use it only when negation semantics are genuinely needed.

### `Content-Type` and `Accept` Are Two Different Directions

A request can send:

```http
Content-Type: application/json
Accept: text/plain
```

That means the client sends a JSON body but wants to receive a text response. `consumes` checks the incoming part; `produces` checks the outgoing part. The two conditions are independent.

## 7. Combining Class-Level and Method-Level

You can declare shared conditions at the class level:

```java
@RestController
@RequestMapping(
        path = "/api/v1",
        headers = "X-Api-Version=2",
        produces = MediaType.APPLICATION_JSON_VALUE
)
public class CatalogController {

    @GetMapping(path = "/items", params = "view=compact")
    public Mono<Item> compact() {
        return Mono.just(new Item("compact"));
    }

    @PostMapping(
            path = "/items",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Item> create(@RequestBody Mono<Item> body) {
        return body;
    }

    @GetMapping(
            path = "/plain",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> plain() {
        return Mono.just("ready");
    }
}
```

How to read it:

- Class-level `path` creates the `/api/v1` prefix.
- Class-level `headers` requires every method to have `X-Api-Version=2`.
- `params` on the `compact` method adds its own condition.
- `consumes` on the `create` method restricts the body media type.
- `produces` on the `plain` method overrides the class-level JSON, so that endpoint returns text.

| Condition | When declared on both class and method |
|---|---|
| Path | Combined into a specific path |
| HTTP method | Conditions are combined |
| `params` | Method-level adds to class-level conditions |
| `headers` | Method-level adds to class-level conditions |
| `consumes` | Method-level overrides class-level if declared |
| `produces` | Method-level overrides class-level if declared |

Do not assume every attribute combines the same way. In particular, `consumes` and `produces` have an override rule at the method level.

### Do Not Stack Multiple Mapping Annotations on the Same Method

Do not write both `@GetMapping` and `@RequestMapping` on the same method. These are both request-mapping annotations; Spring warns and uses only the first mapping.

Combine the conditions into one annotation:

```java
@GetMapping(path = "/items", params = "mode=full")
public Mono<Item> items() {
    return Mono.just(new Item("example"));
}
```

## 8. Distinguishing Mapping Conditions from Binding and Codecs

| Tool | Role | Example |
|---|---|---|
| `params` | Select handler by query | `params="mode=full"` |
| `@RequestParam` | Bind query into argument | `@RequestParam String mode` |
| `headers` | Select handler by header | `headers="X-Client=web"` |
| `@RequestHeader` | Bind header into argument | `@RequestHeader("X-Client") String client` |
| `consumes` | Select handler by Content-Type | `consumes="application/json"` |
| `@RequestBody` | Read and decode body | `@RequestBody Mono<CreateOrder>` |
| `produces` | Select representation by Accept | `produces="application/json"` |
| `@ResponseBody` / `@RestController` | Write response via message writer | `Mono<OrderResponse>` |

Combined example:

```java
@PostMapping(
        path = "/orders",
        params = "source=partner",
        headers = "X-Partner-Id",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
)
public Mono<OrderResponse> create(
        @RequestParam("source") String source,
        @RequestHeader("X-Partner-Id") String partnerId,
        @RequestBody Mono<CreateOrder> body) {

    return body.flatMap(order ->
            orderService.create(source, partnerId, order));
}
```

The mapping condition helps select the method; the argument resolver supplies data to the method after it has been selected.

## 9. Common HTTP Statuses When Mappings Do Not Match

| Scenario | Common status | Explanation |
|---|---|---|
| No matching path | 404 Not Found | No handler found |
| Path matches but HTTP method is not supported | 405 Method Not Allowed | Method not supported |
| `params` does not satisfy condition | Usually 400 Bad Request in WebFlux | May be `UnsatisfiedRequestParameterException` |
| `headers` does not satisfy condition | May leave no handler and return 404 | No mapping satisfies the header condition |
| `consumes` does not match Content-Type | 415 Unsupported Media Type | Server does not accept the request media type |
| `produces` is incompatible with Accept | 406 Not Acceptable | No suitable representation |

The exact status also depends on the set of handler candidates and the configured exception handling. Do not conclude that every mapping mismatch is a 404.

Distinguish two errors:

1. Sending `Content-Type: text/plain` to a handler that only accepts JSON: the mapping does not match, usually 415.
2. Sending `Content-Type: application/json` but the body has invalid JSON syntax: the mapping may have selected the handler; the message reader fails when decoding, usually 400.

## 10. Trying Requests with curl

Suppose the controller has base path `/api/v1`, requires `X-Api-Version: 2`, and the compact endpoint needs `view=compact`, `X-Client=web`, and a JSON response:

```bash
curl -i \
  -H "X-Api-Version: 2" \
  -H "X-Client: web" \
  -H "Accept: application/json" \
  "http://localhost:8080/api/v1/items?view=compact"
```

Example success response:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"name":"compact"}
```

Sending JSON to POST:

```bash
curl -i -X POST \
  -H "X-Api-Version: 2" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"name":"new-item"}' \
  "http://localhost:8080/api/v1/items"
```

If you send `Content-Type: text/plain`, the `consumes=application/json` mapping does not match and usually returns 415.

Try `produces` by calling `/api/v1/plain` with `Accept: text/plain`. If you only send `Accept: application/json` while the endpoint only generates text, you usually receive 406.

## 11. Runnable Java 17+ Project: Spring Boot WebFlux and WebTestClient

This Maven project tests the four kinds of conditions with HTTP tests. Uses Java 17+, Maven, and Spring Boot 3.3.5.

Structure:

```text
request-mapping-conditions/
├── pom.xml
└── src/
    ├── main/java/edu/demo/
    │   ├── RequestMappingConditionsApplication.java
    │   ├── CatalogController.java
    │   └── Item.java
    └── test/java/edu/demo/
        └── RequestMappingConditionsTest.java
```

### 11.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>request-mapping-conditions</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
```

### 11.2. `RequestMappingConditionsApplication.java`

```java
package edu.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestMappingConditionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                RequestMappingConditionsApplication.class, args);
    }
}
```

### 11.3. `Item.java`

```java
package edu.demo;

public record Item(String name) {
}
```

### 11.4. `CatalogController.java`

```java
package edu.demo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping(
        path = "/api/v1",
        headers = "X-Api-Version=2",
        produces = MediaType.APPLICATION_JSON_VALUE
)
public class CatalogController {

    @GetMapping(
            path = "/items",
            params = {"view=compact", "!debug"},
            headers = "X-Client=web"
    )
    public Mono<Item> compact() {
        return Mono.just(new Item("compact"));
    }

    @GetMapping(
            path = "/items",
            params = "view=full",
            headers = "X-Client=web"
    )
    public Mono<Item> full() {
        return Mono.just(new Item("full"));
    }

    @PostMapping(
            path = "/items",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Item> create(@RequestBody Mono<Item> body) {
        return body;
    }

    @GetMapping(
            path = "/plain",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> plain() {
        return Mono.just("ready");
    }
}
```

### 11.5. `RequestMappingConditionsTest.java`

```java
package edu.demo;

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
class RequestMappingConditionsTest {

    @Autowired
    private WebTestClient client;

    @Test
    void paramsAndHeadersSelectCompactHandler() {
        client.get()
                .uri("/api/v1/items?view=compact")
                .header("X-Api-Version", "2")
                .header("X-Client", "web")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                    .jsonPath("$.name").isEqualTo("compact");
    }

    @Test
    void paramsSelectFullHandler() {
        client.get()
                .uri("/api/v1/items?view=full")
                .header("X-Api-Version", "2")
                .header("X-Client", "web")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                    .jsonPath("$.name").isEqualTo("full");
    }

    @Test
    void absentDebugParameterIsRequired() {
        client.get()
                .uri("/api/v1/items?view=compact&debug=true")
                .header("X-Api-Version", "2")
                .header("X-Client", "web")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().is4xxClientError();
    }

    @Test
    void headerConditionMustMatch() {
        client.get()
                .uri("/api/v1/items?view=compact")
                .header("X-Api-Version", "2")
                .header("X-Client", "mobile")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().is4xxClientError();
    }

    @Test
    void jsonRequestMatchesConsumesCondition() {
        client.post()
                .uri("/api/v1/items")
                .header("X-Api-Version", "2")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(new Item("created"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                    .jsonPath("$.name").isEqualTo("created");
    }

    @Test
    void unsupportedContentTypeReturns415() {
        client.post()
                .uri("/api/v1/items")
                .header("X-Api-Version", "2")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue("not-json")
                .exchange()
                .expectStatus().isEqualTo(415);
    }

    @Test
    void methodLevelProducesOverridesClassLevel() {
        client.get()
                .uri("/api/v1/plain")
                .header("X-Api-Version", "2")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.TEXT_PLAIN)
                .expectBody(String.class)
                    .isEqualTo("ready");
    }

    @Test
    void unacceptableResponseTypeReturns406() {
        client.get()
                .uri("/api/v1/plain")
                .header("X-Api-Version", "2")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isEqualTo(406);
    }
}
```

### 11.6. Running the Tests

From the directory containing `pom.xml`:

```bash
mvn test
```

When dependencies download successfully and assertions are right, Maven Surefire will report eight tests run, with no failures or errors. The tests confirm:

1. `view=compact` and `X-Client=web` select the compact handler.
2. `view=full` selects the full handler.
3. Having `debug` makes the `!debug` condition fail.
4. An incorrect `X-Client` header makes the mapping not match.
5. A JSON request satisfies `consumes`.
6. `text/plain` does not satisfy `consumes=application/json` and receives 415.
7. Method-level `produces=text/plain` overrides class-level JSON.
8. A client that accepts only JSON while the endpoint generates only text receives 406.

The tests use `is4xxClientError()` for `params` and `headers` mismatches because the exact result depends on the condition type and the set of handler candidates. The two media-type tests check the specialized statuses 415 and 406 directly.

## 12. Common Mistakes

| Mistake | Why it is wrong | How to fix |
|---|---|---|
| Using `params` without sending the corresponding query | The mapping is not selected | Send the right query or remove the condition |
| Confusing `params` with `@RequestParam` | One selects the handler, the other binds the argument | Use each for its intended purpose |
| Using `headers=Content-Type` instead of `consumes` | Ignores media-type semantics | Use `consumes` |
| Using `headers=Accept` instead of `produces` | Does not express content negotiation clearly | Use `produces` |
| Confusing `consumes` with the response format | `consumes` is the incoming body | Use `produces` for the response |
| Sending an unsupported Content-Type | Mapping does not match, usually 415 | Fix the request or supported media types |
| Incompatible Accept | No suitable representation, usually 406 | Fix Accept or support a suitable representation |
| Using `!debug` while the client still sends debug | The condition requires the parameter to be absent | Remove the parameter or change the mapping |
| Thinking method-level `produces` is added to class-level | Method-level overrides class-level | Declare the full conditions on the method |
| Stacking `@GetMapping` and `@RequestMapping` | Spring uses only the first mapping | Combine into one annotation |
| Using header mapping to verify an API key | Mapping does not check identity/permissions | Use Spring Security |
| Thinking consumes validates valid JSON | It only checks the media type | Use codecs, validation, and business rules |

## 13. Mapping Design Checklist

- Are the path and HTTP method specific enough? Prefer shortcuts such as `@GetMapping` and `@PostMapping`.
- Is `params` really needed to select different handlers, or do you just need to bind an argument?
- Which headers are routing conditions, and which belong to authentication/security?
- Does `consumes` properly restrict the body formats the codec supports?
- Does `produces` match a representation that the message writer can actually create?
- Are the class-level conditions and method-level overrides as intended?
- Are there two mappings with duplicate conditions or causing ambiguity?
- Have you tested missing parameters/headers, wrong Content-Type, wrong Accept, and malformed bodies?
- Are error responses clear without leaking internal details?
- Are API keys/tokens verified by a suitable security mechanism?

## 14. Self-Check Exercises

**Exercise 1.** What request does the following mapping need?

```java
@GetMapping(path = "/items", params = {"type=book", "!archived"})
public Flux<Item> books() {
    return itemService.books();
}
```

**Answer:** The request must have `type=book` and must not have the `archived` query parameter, for example `/items?type=book`.

**Exercise 2.** How does `headers="X-Mode"` differ from `headers="X-Mode=fast"`?

**Answer:** The first expression requires the header to be present with any value; the second requires a matching value of `fast`.

**Exercise 3.** The client sends `Content-Type: application/json` and `Accept: text/plain`. Which condition checks each header?

**Answer:** `consumes` checks Content-Type; `produces` checks whether the response is compatible with Accept.

**Exercise 4.** An endpoint accepts only `consumes=application/json`, and the client sends text/plain. Common status?

**Answer:** 415 Unsupported Media Type.

**Exercise 5.** An endpoint generates only `produces=application/json`, and the client accepts only text/plain. Common status?

**Answer:** 406 Not Acceptable.

**Exercise 6.** Class-level `produces=application/json`, method-level `produces=text/plain`. Does the method accept both types?

**Answer:** No. Method-level `produces` overrides class-level for that method.

**Exercise 7.** Why should you not put both `@GetMapping` and `@RequestMapping` on the same method?

**Answer:** Spring warns and uses only the first mapping; combine the conditions into one annotation.

**Exercise 8.** Does `consumes=application/json` guarantee the body has a valid `name` field?

**Answer:** No. It only restricts the media type. Decoding, Bean Validation, and business validation are separate steps.

## 15. Key Takeaways

- `params` and `headers` are handler-selection conditions, supporting presence, absence, and value checks.
- `consumes` checks the request body via Content-Type; a mismatch is usually 415.
- `produces` takes part in content negotiation with Accept; a mismatch is usually 406.
- Multiple conditions in the same mapping must all be satisfied together.
- Class-level provides shared conditions; method-level adds conditions, with special override rules for `consumes` and `produces`.
- `@RequestParam`, `@RequestHeader`, `@RequestBody`, and codecs perform binding/serialization after the handler is selected.
- Use `WebTestClient` to test both valid and invalid requests.
- Mapping conditions do not replace authentication, authorization, or business validation.

When debugging a controller that is not invoked, check in order: **path → HTTP method → params → headers → Content-Type/consumes → Accept/produces**.

## Official Documentation

- Spring Framework, **Spring WebFlux – Mapping Requests**: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html
- Spring Framework, **Spring WebFlux – Annotated Controllers**: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
- Spring Framework, **Spring WebFlux – `@RequestParam`**: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestparam.html
- Spring Framework, **Spring WebFlux – `@RequestBody`**: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework, **`RequestMapping` API 6.2**: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/web/bind/annotation/RequestMapping.html
- Spring Framework, **`UnsatisfiedRequestParameterException`**: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/web/server/UnsatisfiedRequestParameterException.html
- Spring Framework, **WebTestClient**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html