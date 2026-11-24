# Integrating AssertJ-Style Assertions

`RestTestClient` provides a synchronous way to send HTTP requests and verify responses. After calling `exchange()`, you can use the client's built-in assertions or hand the response over to AssertJ. The latter is useful when you want to write `assertThat(...)`-style assertions, leverage familiar AssertJ checks, and combine them with status, header, cookie, content type, and body verification.

The main entry point for this integration is `RestTestClientResponse`. This interface implements `AssertProvider<RestTestClientResponseAssert>`, so AssertJ can automatically obtain the specialized assertion when `assertThat(response)` is called. The specialized assertion lets you inspect the HTTP response and then transition to AssertJ assertions for strings, byte arrays, JSON, headers, and cookies.

AssertJ integration for `RestTestClient` was introduced in Spring Framework 7.0. The examples below use Spring Framework 7.0 or later APIs.

### Required Dependencies

The testing APIs reside in `spring-test`; AssertJ must be on the test classpath to use `assertThat(...)`:

```xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.assertj</groupId>
    <artifactId>assertj-core</artifactId>
    <scope>test</scope>
</dependency>
```

Let Spring Boot dependency management or the Spring Framework BOM manage versions so Spring modules from the same release line remain compatible. If you use JSON comparison or specialized JSON assertions, add the JSON assertion library supported by your Spring version; Spring 7.0 documentation illustrates JSONAssert, while 7.1 documentation supports JSONUnit or JSONAssert.

## Preparing RestTestClient

`RestTestClient` resides in package `org.springframework.test.web.servlet.client`. It can test controllers using mock servlet requests/responses, load an entire `WebApplicationContext`, test functional endpoints via a router function, or connect to a running server.

Example initialization with `WebApplicationContext`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.servlet.client.RestTestClient;
import org.springframework.web.context.WebApplicationContext;

@SpringJUnitConfig(WebConfig.class)
class PersonApiTest {

    private RestTestClient client;

    @BeforeEach
    void setUp(WebApplicationContext context) {
        client = RestTestClient.bindToApplicationContext(context).build();
    }
}
```

If you only want to test one or a few controllers, you can use `RestTestClient.bindToController(...)`. If you need to test over real HTTP, use `RestTestClient.bindToServer()` and configure the base URL of the running server. The binding mode determines whether requests go through mock MVC infrastructure or over the network to a real server; the assertion API after `exchange()` serves the same goal of verifying the response.

`RestTestClient` has a request-sending API similar to `RestClient` up to the `exchange()` call. You can configure URI, path variables, query parameters, headers, content type, accept, cookies, and request body before execution.

## Two Response Checking Styles

After `exchange()`, there are two main styles:

| Style | Syntax | Suitable when |
|---|---|---|
| Built-in assertions | `expectStatus()`, `expectHeader()`, `expectBody()` | Wanting to keep all checks in a single RestTestClient chain |
| AssertJ integration | `RestTestClientResponse.from(...)` then `assertThat(...)` | Wanting to use AssertJ-style assertions or combine custom assertions |

Built-in assertions can be written as:

```java
client.get().uri("/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentType(MediaType.APPLICATION_JSON)
        .expectBody();
```

AssertJ integration converts the exchange result into `RestTestClientResponse`, then uses `assertThat`:

```java
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.client.RestTestClient;
import org.springframework.test.web.servlet.client.assertj.RestTestClientResponse;

import static org.assertj.core.api.Assertions.assertThat;

RestTestClient.ResponseSpec spec = client.get()
        .uri("/persons/1")
        .accept(MediaType.APPLICATION_JSON)
        .exchange();

RestTestClientResponse response = RestTestClientResponse.from(spec);

assertThat(response).hasStatusOk();
assertThat(response).hasContentTypeCompatibleWith(MediaType.APPLICATION_JSON);
```

`RestTestClientResponse.from(ResponseSpec)` is the direct conversion point from a response spec to an object usable with AssertJ. Because `RestTestClientResponse` is an `AssertProvider`, there is no need to manually call `response.assertThat()`; `assertThat(response)` automatically selects `RestTestClientResponseAssert`.

## Creating Response Assertions from ExchangeResult

If you want to use the built-in workflow first and then switch to AssertJ, you can obtain `ExchangeResult` via `returnResult()`:

```java
import org.springframework.test.web.servlet.client.ExchangeResult;

ExchangeResult result = client.get()
        .uri("/persons/1")
        .exchange()
        .returnResult();

RestTestClientResponse response = RestTestClientResponse.from(result);

assertThat(response).hasStatusOk();
assertThat(response).hasContentTypeCompatibleWith(MediaType.APPLICATION_JSON);
```

The two paths serve different purposes:

- `from(ResponseSpec)` converts the result immediately after `exchange()` to AssertJ.
- `from(ExchangeResult)` is useful when the test already used `returnResult()` to get the exchange result or needs to keep `ExchangeResult` for other checks.

`RestTestClientResponse` also provides `getExchangeResult()` to retrieve the underlying exchange result. This allows combining high-level assertions with reading request/response metadata stored by `ExchangeResult`.

## Checking HTTP Status

`RestTestClientResponseAssert` has methods to check status by exact code or by status group:

```java
assertThat(response).hasStatusOk();
assertThat(response).hasStatus(201);
assertThat(response).hasStatus(HttpStatus.CREATED);
assertThat(response).hasStatus2xxSuccessful();
assertThat(response).hasStatus3xxRedirection();
assertThat(response).hasStatus4xxClientError();
assertThat(response).hasStatus5xxServerError();
```

Choose a specific assertion when the status is part of the API contract. For example, resource-creation endpoints should usually be checked with `201 Created` rather than only confirming a 2xx group status. Group assertions are useful when multiple success codes are acceptable in a scenario.

You can attach a description to assertions for clearer failure messages:

```java
assertThat(response)
        .as("creating a person should return Created")
        .hasStatus(HttpStatus.CREATED);
```

These methods return the same assertion type, so multiple checks can be chained on a single response:

```java
assertThat(response)
        .hasStatus(HttpStatus.CREATED)
        .containsHeader(HttpHeaders.LOCATION)
        .hasContentTypeCompatibleWith(MediaType.APPLICATION_JSON);
```

## Checking Headers and Content-Type

The response assertion provides direct methods for checking headers:

```java
assertThat(response)
        .containsHeader(HttpHeaders.ETAG)
        .hasHeader(HttpHeaders.CACHE_CONTROL, "no-store")
        .doesNotContainHeader("X-Internal-Debug");
```

`containsHeader(name)` checks that the header exists. `hasHeader(name, value)` checks the primary value of the header. If you need to inspect a list of values or multiple headers at once, use `headers()` to obtain `HttpHeadersAssert`, an AssertJ-style map assertion:

```java
assertThat(response)
        .headers()
        .containsKey(HttpHeaders.ETAG)
        .containsKey(HttpHeaders.CACHE_CONTROL)
        .doesNotContainKey("X-Internal-Debug");
```

For `Content-Type`, distinguish exact comparison from compatibility comparison:

```java
assertThat(response).hasContentType(MediaType.APPLICATION_JSON);

assertThat(response)
        .hasContentTypeCompatibleWith(MediaType.APPLICATION_JSON);
```

`hasContentType(...)` checks that the content type matches the expected value. `hasContentTypeCompatibleWith(...)` checks whether the two media types are compatible, for example when the response is `application/json` and the expectation is `application/*`. If charset or media type parameters are part of the contract, check them specifically rather than relying only on compatibility.

You can also drill down into `MediaTypeAssert`:

```java
assertThat(response)
        .contentType()
        .isCompatibleWith(MediaType.APPLICATION_JSON);
```

## Checking Cookies

`cookies()` returns `CookieMapAssert`, allowing cookies to be inspected like a map keyed by cookie name. Beyond AssertJ's map checks, Spring provides dedicated assertions for cookie attributes:

```java
assertThat(response)
        .cookies()
        .containsCookie("SESSION")
        .hasPath("SESSION", "/")
        .isHttpOnly("SESSION", true)
        .isSecure("SESSION", true);
```

Available methods include:

| Assertion | Meaning |
|---|---|
| `containsCookie("SESSION")` | A cookie with the given name is present |
| `doesNotContainCookie("legacy")` | No cookie with the given name is present |
| `hasValue("theme", "dark")` | Cookie has the exact value |
| `hasPath("SESSION", "/")` | Cookie has the exact path |
| `hasDomain("SESSION", "example.test")` | Cookie has the exact domain |
| `hasMaxAge("remember", Duration.ofDays(30))` | Cookie has the exact max age |
| `isHttpOnly("SESSION", true)` | Checks the HttpOnly flag |
| `isSecure("SESSION", true)` | Checks the Secure flag |
| `hasCookieSatisfying("name", consumer)` | Checks the cookie using a custom assertion |

Example with a custom assertion:

```java
assertThat(response)
        .cookies()
        .hasCookieSatisfying("SESSION", cookie -> {
            assertThat(cookie.getValue()).isNotBlank();
            assertThat(cookie.getPath()).isEqualTo("/");
            assertThat(cookie.isHttpOnly()).isTrue();
            assertThat(cookie.getSecure()).isTrue();
        });
```

Do not assume every cookie requires `Secure` or the same `Max-Age`; assert according to your application's cookie policy and test environment. For session cookies, `HttpOnly` and `Secure` are often important security attributes to verify when the application is configured to enable them.

## Checking the Response Body as Text or Byte Array

`bodyText()` converts the body to a string and returns AssertJ's `AbstractStringAssert`. Thus all familiar string checks can be used:

```java
assertThat(response)
        .bodyText()
        .isEqualTo("Hello, Jane")
        .contains("Jane")
        .doesNotContain("stacktrace");
```

If you only want to check equality, you can use `hasBodyTextEqualTo(...)` directly on the response assertion:

```java
assertThat(response).hasBodyTextEqualTo("Hello, Jane");
```

`body()` returns a byte array assertion. Use it when you need to assert an empty body, byte content, or binary content:

```java
assertThat(response).body().isNotEmpty();

assertThat(response).body().isEqualTo(expectedBytes);
```

For responses with no content, you can assert an empty byte array:

```java
assertThat(response)
        .hasStatus(HttpStatus.NO_CONTENT)
        .body()
        .isEmpty();
```

If the body is encoded with a specific charset, `bodyText()` is a convenient way to inspect the decoded string. If the contract requires exact bytes, use `body()` and compare byte arrays.

## Checking JSON with bodyJson()

`bodyJson()` returns a specialized assertion for JSON. It supports JSON comparison and extracting values by JSONPath, then transitioning to the appropriate assertion type:

```java
assertThat(response)
        .bodyJson()
        .extractingPath("$.name")
        .asString()
        .isEqualTo("Jane");
```

Multiple fields can be checked by path:

```java
assertThat(response)
        .bodyJson()
        .extractingPath("$.id")
        .asNumber()
        .isEqualTo(42);

assertThat(response)
        .bodyJson()
        .extractingPath("$.active")
        .asBoolean()
        .isTrue();
```

JSON assertions can also check the presence or absence of a path:

```java
assertThat(response)
        .bodyJson()
        .hasPath("$.customer.email")
        .doesNotHavePath("$.internalSecret");
```

When the entire JSON response is the contract to protect, you can compare against sample JSON:

```java
assertThat(response)
        .bodyJson()
        .isStrictlyEqualTo("""
                {
                  "id": 42,
                  "name": "Jane",
                  "active": true
                }
                """);
```

If sample JSON is stored as a test resource file, you can use `withResourceLoadClass(...)` to specify the package containing the file:

```java
assertThat(response)
        .bodyJson()
        .withResourceLoadClass(PersonControllerTest.class)
        .isStrictlyEqualTo("person-created.json");
```

JSON comparison verifies many fields in a single assertion. JSONPath fits when only a few fields need checking or when the response contains dynamic values that should not go into fixtures. For responses with timestamps or auto-generated IDs, extract stable fields or fix test data before comparing the entire JSON.

## Custom Body Checks with AssertJ

If the body can be decoded into a DTO, you can use the built-in body workflow and run AssertJ inside `consumeWith(...)`:

```java
client.get().uri("/persons/{id}", 42L)
        .exchange()
        .expectStatus().isOk()
        .expectBody(Person.class)
        .consumeWith(result -> {
            Person person = result.getResponseBody();
            assertThat(person).isNotNull();
            assertThat(person.getId()).isEqualTo(42L);
            assertThat(person.getName()).isEqualTo("Jane");
        });
```

This is useful when you want to use the deserialized object to verify business rules or AssertJ's recursive comparison. Built-in `expectBody(Person.class)` handles decoding, while AssertJ verifies the object.

If you want to pull the object out of the expectation chain, call `returnResult()`:

```java
EntityExchangeResult<Person> result = client.get()
        .uri("/persons/{id}", 42L)
        .exchange()
        .expectStatus().isOk()
        .expectBody(Person.class)
        .returnResult();

Person person = result.getResponseBody();
assertThat(person)
        .isNotNull()
        .extracting(Person::getName)
        .isEqualTo("Jane");
```

For bodies with generic types such as `List<Person>`, use the overload accepting `ParameterizedTypeReference` to preserve generic type information:

```java
ParameterizedTypeReference<List<Person>> personListType =
        new ParameterizedTypeReference<>() {};

EntityExchangeResult<List<Person>> result = client.get()
        .uri("/persons")
        .exchange()
        .expectStatus().isOk()
        .expectBody(personListType)
        .returnResult();

assertThat(result.getResponseBody())
        .extracting(Person::getName)
        .containsExactly("Jane", "Jason");
```

Do not use `Person.class` to decode `List<Person>`; due to type erasure, generic element types can be lost. `ParameterizedTypeReference` preserves the type information required by the message converter.

## Combining AssertJ with ExchangeResult

`RestTestClientResponse` can retrieve the underlying `ExchangeResult`:

```java
ExchangeResult exchangeResult = response.getExchangeResult();

assertThat(exchangeResult.getResponseHeaders())
        .containsKey(HttpHeaders.ETAG);
assertThat(exchangeResult.getResponseBodyContent())
        .isNotEmpty();
```

This is an option when you need access to metadata without a dedicated assertion. Prefer `headers()`, `cookies()`, `bodyText()`, or `bodyJson()` when they meet your needs, because they directly express the test's intent. Use `ExchangeResult` for specialized checks such as request headers, URI, execution details, or raw response data.

## Organizing Assertions into Reusable Helpers

If multiple tests need to verify the same part of a response contract, you can create a helper accepting `RestTestClientResponse`:

```java
static void assertJsonResponse(RestTestClientResponse response) {
    assertThat(response)
            .hasStatusOk()
            .hasContentTypeCompatibleWith(MediaType.APPLICATION_JSON);

    assertThat(response)
            .bodyJson()
            .hasPath("$.id")
            .hasPath("$.status");
}
```

Tests call the helper after executing the request:

```java
RestTestClientResponse response = RestTestClientResponse.from(
        client.get().uri("/api/orders/{id}", 42L).exchange());

assertJsonResponse(response);
assertThat(response)
        .bodyJson()
        .extractingPath("$.status")
        .asString()
        .isEqualTo("PAID");
```

Helpers should group common conditions meaningful to the API contract, such as success status and media type. Keep test-specific assertions close to each test; if a helper knows too much about business data, it can obscure the behavior the test is meant to describe.

## When to Use AssertJ vs. Built-In Assertions?

RestTestClient's built-in assertions fit when you want to verify responses directly within the fluent workflow:

```java
client.get().uri("/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentType(MediaType.APPLICATION_JSON)
        .expectBody(Person.class)
        .consumeWith(result -> {
            Person person = result.getResponseBody();
            assertThat(person).isNotNull();
            assertThat(person.getName()).isEqualTo("Jane");
        });
```

AssertJ integration fits when you want to extract the response into an object and run multiple independent assertions:

```java
RestTestClientResponse response = RestTestClientResponse.from(
        client.get().uri("/persons/1").exchange());

assertThat(response).hasStatusOk();
assertThat(response).contentType()
        .isCompatibleWith(MediaType.APPLICATION_JSON);
assertThat(response).bodyJson()
        .extractingPath("$.name")
        .asString()
        .isEqualTo("Jane");
```

The built-in API's `expectAll(...)` lets multiple expectations run even if one fails. This is a failure-aggregation mechanism similar to soft assertions, though still part of RestTestClient itself. With AssertJ integration, you can use AssertJ features such as `SoftAssertions` when collecting multiple assertion failures in one test; keep a single executed response to avoid sending the same request multiple times.

## Notes When Checking the Response Body

If a test needs to read the response body, consume it via `body()`, `bodyText()`, `bodyJson()`, `expectBody(...)`, or `returnResult()` as appropriate. Ignoring the body completely can trigger buffer leak warnings in pooled-buffer test configurations. When an endpoint has no body, check the status and use a body assertion to verify emptiness or `expectBody().isEmpty()` in the built-in workflow.

Do not use `bodyJson()` for non-JSON responses or empty bodies. Use `bodyText()` for text, `body()` for byte content, and `bodyJson()` for JSON. Choose the assertion matching the media type and response contract.

## Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| `RestTestClient` not found | Using Spring Framework older than 7.0 or missing matching `spring-test` | Use Spring Framework 7.0 or later and matching test dependencies |
| `assertThat(response)` lacks HTTP assertions | Passed object is not `RestTestClientResponse` or AssertJ is missing | Use `RestTestClientResponse.from(...)` and add AssertJ to the test classpath |
| Cannot create response wrapper | Accidentally passed request spec instead of `ResponseSpec` or `ExchangeResult` | Call `exchange()` first, then pass the result to `from(...)` |
| `hasContentType` fails even though response is JSON | Exact comparison including media type parameters | Use `hasContentTypeCompatibleWith(...)` if only checking compatibility |
| `bodyJson()` fails to parse | Body is not valid JSON or version-appropriate JSON assertion dependency is missing | Check body, Content-Type, and JSON assertion dependency |
| Body assertion unexpectedly returns empty data | Response was not consumed properly or endpoint actually returns no body | Check status and use the right body API to read/consume the response |
| Generic response decoded into unwanted type | Used `Class<T>` for generic collection | Use `ParameterizedTypeReference<T>` |
| Assertion helper sends repeated requests | Helper executes requests itself instead of accepting an already-exchanged response | Create `RestTestClientResponse` once and pass it into the helper |

## Choosing Assertions by Goal

| Goal | Assertion |
|---|---|
| Check HTTP status | `hasStatusOk()`, `hasStatus(...)`, `hasStatus2xxSuccessful()` |
| Check Content-Type | `hasContentType(...)`, `hasContentTypeCompatibleWith(...)`, `contentType()` |
| Check headers | `containsHeader(...)`, `hasHeader(...)`, `headers()` |
| Check cookies | `cookies().containsCookie(...)`, `hasValue(...)`, `isHttpOnly(...)`, `isSecure(...)` |
| Check text body | `bodyText()` or `hasBodyTextEqualTo(...)` |
| Check byte body | `body()` |
| Compare JSON | `bodyJson().isStrictlyEqualTo(...)` or `isLenientlyEqualTo(...)` |
| Read a JSON field | `bodyJson().extractingPath(...).asString()` |
| Check decoded DTO | `expectBody(Person.class).consumeWith(...)` then AssertJ |
| Check generic collection | `expectBody(ParameterizedTypeReference<T>)` then AssertJ |

AssertJ integration for `RestTestClient` lets you transition from HTTP test expectation chains to AssertJ's expressive assertions. Use `RestTestClientResponse.from(...)` to create the entry point, inspect HTTP response status and metadata, and then pick `bodyText()`, `bodyJson()`, or `body()` based on content type. When assertions on a deserialized DTO are needed, use `expectBody(...)` and apply AssertJ inside the callback or on the returned result. This organization keeps tests clearly expressing the HTTP contract while still leveraging AssertJ's object and data comparison capabilities.
