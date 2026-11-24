# Creating Requests and Verifying Results with Fluent Assertions

`MockMvcTester` is an AssertJ-style Spring MVC testing API introduced in Spring Framework 6.2. It allows writing a request and verifying its result using a fluent assertion chain: build the request, specify the URI and payload, and then assert the HTTP status and response body in the same expression.

`MockMvcTester` still uses `MockMvc` and `DispatcherServlet` underneath. Requests are processed through Spring MVC in a mock environment without opening an HTTP port or starting a real servlet container. The main change is that creating requests and expressing assertions become more concise and seamless.

## 1. Prerequisites for Using MockMvcTester

`MockMvcTester` is available starting in Spring Framework 6.2 and requires AssertJ on the test classpath. In a Spring Boot project, `spring-boot-starter-test` typically provides the required testing libraries, including AssertJ.

Gradle dependency example when using Spring Boot:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

If managing dependencies directly, you need `spring-test` version 6.2 or later and a compatible `assertj-core`. Let the Spring Boot BOM or the project's dependency management align versions consistently; do not upgrade `spring-test` alone to a version different from the rest of Spring Framework.

With Spring Boot 3.4 or later, when AssertJ is on the classpath and the test uses MockMvc configuration, Boot can auto-configure the `MockMvcTester` bean. Older Spring Boot projects may not have this auto-configuration yet; `MockMvcTester` can still be created manually if the actual Spring Framework version is already 6.2 or later.

## 2. Creating MockMvcTester from MockMvc

`MockMvcTester` can be created from a configured `MockMvc`. This approach is suitable when the test uses a `WebApplicationContext` and wants to reuse existing MVC configuration:

```java
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

MockMvc mockMvc = MockMvcBuilders
    .webAppContextSetup(webApplicationContext)
    .build();

MockMvcTester mvc = MockMvcTester.create(mockMvc);
```

If testing only a single controller with minimal configuration, you can create `MockMvc` with `standaloneSetup(...)` and wrap it with `MockMvcTester`:

```java
MockMvc mockMvc = MockMvcBuilders
    .standaloneSetup(new GreetingController())
    .build();

MockMvcTester mvc = MockMvcTester.create(mockMvc);
```

Choose `webAppContextSetup` when you want to use the beans and MVC configuration loaded in the web application context. Choose `standaloneSetup` when the test scope focuses on a controller and does not need the entire web context.

## 3. Injecting MockMvcTester in Spring Boot

With a Spring Boot version that supports auto-configuration for `MockMvcTester`, you can inject it directly into the test:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

@SpringBootTest
@AutoConfigureMockMvc
class GreetingControllerTests {

    @Autowired
    private MockMvcTester mvc;
}
```

`@SpringBootTest` loads the application's application context. `@AutoConfigureMockMvc` configures the MockMvc infrastructure; in supporting Boot versions, the `MockMvcTester` bean is created based on that infrastructure if AssertJ is available.

If the `MockMvcTester` bean is missing, check the Spring Framework version, Spring Boot version, and AssertJ on the test classpath. With Spring Framework 6.2 without corresponding Boot auto-configuration, you can inject `MockMvc` and call `MockMvcTester.create(mockMvc)` in test setup.

## 4. Creating Requests and Verifying Status with Fluent Assertions

`MockMvcTester` provides request builders for common HTTP methods such as `get()`, `post()`, `put()`, `patch()`, `delete()`, `options()`, and `head()`. The builder lets you set the URI, path variables, parameters, headers, cookies, session, content type, and request body.

Suppose a controller returns a plain-text greeting:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GreetingController {

    @GetMapping("/greeting")
    String greeting(
            @RequestParam(defaultValue = "friend") String name) {
        return "Hello " + name;
    }
}
```

With traditional `MockMvc`, tests typically call `perform(...)` and chain `andExpect(...)`. With `MockMvcTester`, the request builder can be passed directly into AssertJ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

@Test
void returnsGreetingForRequestedName() {
    assertThat(mvc.get().uri("/greeting").param("name", "Mai"))
        .hasStatusOk()
        .bodyText()
        .isEqualTo("Hello Mai");
}
```

The expression above executes the request and checks the result in order:

1. `mvc.get()` creates a GET request.
2. `uri("/greeting")` selects the endpoint.
3. `param("name", "Mai")` sends a request parameter that the controller receives via `@RequestParam`.
4. `hasStatusOk()` verifies that the HTTP status is 200.
5. `bodyText().isEqualTo(...)` verifies the response content.

There is no need to declare an `MvcResult` variable, call `andReturn()`, or write a separate matcher for each standard assertion.

## 5. Verifying JSON Responses

For endpoints returning JSON, you can use `bodyJson()` to verify the JSON structure and query a field with JsonPath.

Example controller that creates an order and returns its order identifier:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @PostMapping("/orders")
    @ResponseStatus(HttpStatus.CREATED)
    OrderResponse create(@RequestBody CreateOrderRequest request) {
        return new OrderResponse("ORD-42", request.customerId());
    }
}

record CreateOrderRequest(String customerId) {
}

record OrderResponse(String id, String customerId) {
}
```

The test can send JSON and verify both the status and a field in the response:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;

@Test
void createsOrderAndReturnsItsIdentifier() {
    assertThat(mvc.post().uri("/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "customerId": "C-208"
                }
                """))
        .hasStatus(HttpStatus.CREATED)
        .bodyJson()
        .extractingPath("$.id")
        .isEqualTo("ORD-42");
}
```

`contentType(...)` declares the request payload media type; `content(...)` sends the JSON body; `accept(...)` indicates the client expects a JSON response. `hasStatus(...)` verifies the specific status; `bodyJson()` switches to JSON assertions; `extractingPath(...)` retrieves the value at the specified JSONPath.

If you only need to compare the entire response body as text, use `bodyText()`. When you need to verify JSON structure or specific fields, `bodyJson()` keeps tests less sensitive to field ordering and whitespace in the JSON string.

## 6. Verifying HTTP Errors and Business Responses

Fluent assertions are also useful when testing error scenarios. For example, an endpoint that does not find an order may return status 404 and an error JSON standardized by `@ControllerAdvice`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.http.HttpStatus;

@Test
void returnsNotFoundForUnknownOrder() {
    assertThat(mvc.get().uri("/orders/{id}", "missing"))
        .hasStatus(HttpStatus.NOT_FOUND)
        .bodyJson()
        .extractingPath("$.code")
        .isEqualTo("ORDER_NOT_FOUND");
}
```

The test checks both the HTTP status code and the business error code. Checking only status 404 can miss cases where the response contains the wrong error code; checking only the JSON body can miss cases where the application returns the wrong HTTP status.

For errors handled by `@ExceptionHandler` or `@ControllerAdvice`, verify the final response that the client receives. If the goal is to directly test the exception thrown before Spring handles it, that is a different testing goal and may require testing the exception at the service layer or invoking the appropriate component directly.

## 7. Configuring Request Details

`MockMvcTester`'s request builder supports common request details similar to MockMvc's request builder:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.http.MediaType;

assertThat(mvc.get().uri("/account")
        .header("X-Trace-Id", "trace-276")
        .cookie(new jakarta.servlet.http.Cookie("locale", "vi"))
        .sessionAttr("userId", "U-17")
        .accept(MediaType.APPLICATION_JSON))
    .hasStatusOk();
```

Commonly used methods include:

| Method | Purpose |
|---|---|
| `uri(...)` | Select the URI and pass path variables |
| `param(...)` / `queryParam(...)` | Set a request parameter or query parameter |
| `header(...)` | Add an HTTP header |
| `cookie(...)` | Add a cookie to the request |
| `session(...)` / `sessionAttr(...)` | Set the session or a session attribute |
| `contentType(...)` | Declare the request body media type |
| `accept(...)` | Declare the response media type accepted by the client |
| `content(...)` | Set the request body |

Include only the data that belongs to the endpoint's contract. For example, if the controller reads `@RequestHeader`, use `header(...)`; if the controller reads `@RequestParam`, use `param(...)` or `queryParam(...)`. Do not substitute a parameter for a header just because the field names match.

## 8. Comparing MockMvcTester and Traditional MockMvc

Both APIs test Spring MVC through the MockMvc infrastructure. The main difference lies in how requests are built and assertions are expressed.

| Aspect | MockMvc | MockMvcTester |
|---|---|---|
| Building requests | `mockMvc.perform(get(...))` | `mvc.get().uri(...)` |
| Checking status | `.andExpect(status().isOk())` | `.hasStatusOk()` |
| Checking text | `.andExpect(content().string("..."))` | `.bodyText().isEqualTo("...")` |
| Checking JSON | `jsonPath("$.id").value(...)` | `.bodyJson().extractingPath("$.id").isEqualTo(...)` |
| Intermediate result | `MvcResult` | Fluent assertions from request/result |
| Execution infrastructure | `DispatcherServlet` and mock servlets | Reuses the MockMvc infrastructure |

Example of the same test written both ways:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Traditional MockMvc
mockMvc.perform(get("/greeting").param("name", "Mai"))
    .andExpect(status().isOk())
    .andExpect(content().string("Hello Mai"));

// MockMvcTester
assertThat(mvc.get().uri("/greeting").param("name", "Mai"))
    .hasStatusOk()
    .bodyText().isEqualTo("Hello Mai");
```

`MockMvc` remains useful when you need `ResultMatcher`, `ResultHandler`, `MvcResult`, or fine-grained controls already established in existing tests. `MockMvcTester` is well suited when you want to write assertions directly in AssertJ style. Both styles can coexist in a project; there is no need to migrate all tests just to use the new API.

## 9. Limitations and Common Mistakes

`MockMvcTester` is not an HTTP client sending requests over the network. It does not verify server ports, TLS, reverse proxies, or differences of a real servlet container. When those behaviors must be verified, use tests that start a server and send real HTTP requests.

Some common mistakes:

| Symptom | Cause to Check |
|---|---|
| `MockMvcTester` not found | Spring Framework older than 6.2 or `spring-test` dependency is not on the test classpath |
| Cannot inject bean in Spring Boot | Boot does not yet have supporting auto-configuration, AssertJ is missing, or MockMvc configuration is not enabled |
| `NoSuchMethodError` or Spring compatibility errors | Spring Framework modules use unaligned versions; check the BOM and dependency overrides |
| Request does not match endpoint | Wrong method, URI, context path, servlet path, or request parameter |
| JSON body fails to bind | Wrong `Content-Type`, invalid JSON, or unsuitable message converter |
| Status assertion passes but body fails | Inspect `bodyText()` or `bodyJson()` separately and verify what the controller returns |

When migrating an existing test to `MockMvcTester`, preserve the original request scenario and the conditions being verified. Change the assertion style first, then confirm the status and body still express the same HTTP contract.

## 10. Workflow for Writing Fluent Assertions

1. Ensure the project uses Spring Framework 6.2 or later and has AssertJ on the test classpath.
2. Create or inject `MockMvcTester` from the MockMvc infrastructure.
3. Choose the HTTP method and URI using `get()`, `post()`, or the corresponding builder.
4. Add path variables, parameters, headers, cookies, session, and body matching the endpoint.
5. Use `hasStatusOk()` or `hasStatus(...)` to assert the HTTP status.
6. Use `bodyText()` or `bodyJson()` to verify the response body.
7. Keep traditional MockMvc for tests requiring specialized matchers or result handlers.

`MockMvcTester` keeps both the request and the assertions in a single readable expression: describe what the client sends, then verify what the Spring MVC server returns. Understanding the version prerequisites and how it complements traditional MockMvc will help you apply fluent assertions in the right places without changing the testing scope.
