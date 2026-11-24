# MockMvcTester and AssertJ Integration by Supported Spring Version

`MockMvc` is a tool for testing Spring MVC using simulated requests and responses. Starting with Spring Framework 6.2, Spring Test also provides `MockMvcTester`, an API built on top of MockMvc that uses the AssertJ assertion style.

With the traditional API, tests typically call `mockMvc.perform(...)` and chain matchers via `andExpect(...)`. With `MockMvcTester`, tests can build requests using methods such as `get()` and verify results using `assertThat(...)`, for example `hasStatusOk()`, `bodyText()`, or `bodyJson()`.

`MockMvcTester` makes test authoring more consistent with tests that already use AssertJ. It still uses the MockMvc infrastructure underneath, so requests do not go over HTTP sockets and do not start a real Servlet container.

## 1. What Is MockMvcTester?

`MockMvcTester` belongs to the `spring-test` module, in the package:

```java
org.springframework.test.web.servlet.assertj
```

It provides an AssertJ-style facade for requests executed with MockMvc. Tests still exercise Spring MVC components such as `DispatcherServlet`, handler mappings, controllers, argument resolvers, message converters, exception resolvers, and filters registered in the test environment.

The main difference lies in how requests are created and results are asserted:

```java
// Traditional MockMvc API
mockMvc.perform(get("/greetings/Lan"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.message").value("Hello, Lan"));

// AssertJ-style MockMvcTester API
assertThat(mockMvcTester.get().uri("/greetings/Lan"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.message")
        .isEqualTo("Hello, Lan");
```

Both approaches can test the same request. `MockMvcTester` does not replace the MockMvc engine; it provides a more convenient API for expressing requests and assertions.

### What Goals Does MockMvcTester Fit?

- Writing AssertJ-style assertions without chaining multiple `ResultMatcher` instances.
- Checking HTTP statuses with readable assertions such as `hasStatusOk()`.
- Verifying text or JSON response bodies with dedicated assertions.
- Using the same assertion style as other unit tests and integration tests in the project.
- Providing a consistent MVC testing API when the development team already uses AssertJ extensively.

If a project already has many traditional MockMvc tests, migrating all of them is not required. Both APIs can coexist, and the choice depends on readability, consistency, and the needs of each test.

## 2. Required Spring Versions and Dependencies

The ability to use `MockMvcTester` depends on the Spring Test version, not just whether the project has AssertJ.

| Component | Support Condition |
| --- | --- |
| Spring Framework | `MockMvcTester` was introduced in Spring Framework 6.2 |
| Spring Boot | Spring Boot 3.4 or later manages Spring Framework 6.2 or later and can auto-configure `MockMvcTester` when AssertJ is on the test classpath |
| AssertJ | A compatible AssertJ version is required on the test classpath to use the assertion API and for Boot's auto-configuration mechanism to detect it |
| Spring Test | The `spring-test` module matching the Spring Framework version in use is required |

With Spring Boot, the `spring-boot-starter-test` dependency usually provides Spring Test, AssertJ, and other common testing libraries. In a Spring Boot 3.4+ project, when using `@WebMvcTest` or `@AutoConfigureMockMvc` and AssertJ is present, you can inject the Boot-configured `MockMvcTester`.

Gradle example for Spring Boot:

```groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

If the project uses Spring Framework directly, you need to declare `spring-test` 6.2 or later and AssertJ in the test scope. Use dependency management or a BOM to ensure the `spring-test` version is compatible with other Spring modules:

```groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.assertj:assertj-core")
    testImplementation("org.junit.jupiter:junit-jupiter")
}
```

The configuration snippet above assumes versions are managed by the project's BOM or dependency constraints. If dependency management is not used, specific compatible versions must be declared for each library.

### If the Project Uses Spring Framework 6.1 or Spring Boot 3.3 or Earlier

Spring Framework versions prior to 6.2 do not include the `MockMvcTester` class. Simply adding `assertj-core` to a project using an older Spring Test version will not make this class available. When Spring cannot yet be upgraded, continue using the traditional MockMvc API.

If you want to use `MockMvcTester`, upgrade Spring Boot or Spring Framework as a compatible set of versions. Do not upgrade `spring-test` to 6.2 on its own while other Spring modules remain on an older incompatible line.

## 3. Creating MockMvcTester in Spring Boot

In a Spring Boot application, `MockMvcTester` can be injected directly once Boot has auto-configured MockMvc and AssertJ is on the classpath.

Controller example:

```java
@RestController
public class GreetingController {

    @GetMapping("/greetings/{name}")
    public Map<String, String> greet(@PathVariable String name) {
        return Collections.singletonMap("message", "Hello, " + name);
    }
}
```

Test using `@WebMvcTest`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;

@WebMvcTest(GreetingController.class)
class GreetingControllerTest {

    @Autowired
    private MockMvcTester mvc;

    @Test
    void returnsGreetingAsJson() {
        assertThat(mvc.get().uri("/greetings/{name}", "Lan"))
                .hasStatusOk()
                .bodyJson()
                .extractingPath("$.message")
                .isEqualTo("Hello, Lan");
    }
}
```

`@WebMvcTest` creates a Spring MVC test slice. Boot configures MockMvc and, when the required conditions are met, provides the `MockMvcTester` bean. The test does not need to create `MockMvc` manually or call `MockMvcTester.create(...)` in this case.

If the controller depends on services or other beans outside the MVC slice, provide them using mock beans or test configuration appropriate for the Spring Boot version in use. `MockMvcTester` only changes the API for performing requests and assertions; it does not create missing business dependencies automatically.

### Using with the Full Application Context

If the goal is to test multiple layers of the application with real configuration, you can use `@SpringBootTest` combined with `@AutoConfigureMockMvc`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ApplicationMvcTest {

    @Autowired
    private MockMvcTester mvc;

    @Test
    void servesConfiguredEndpoint() {
        assertThat(mvc.get().uri("/greetings/Lan"))
                .hasStatusOk()
                .bodyJson()
                .extractingPath("$.message")
                .isEqualTo("Hello, Lan");
    }
}
```

This test loads a broader application context than `@WebMvcTest`, but still uses MockMvc. It does not open a network port to receive real HTTP requests.

## 4. Creating MockMvcTester Manually

If you do not use Spring Boot auto-configuration, you can create MockMvc first and then wrap it with `MockMvcTester.create(...)`.

Example using standalone setup:

```java
class GreetingControllerStandaloneTest {

    private MockMvcTester mvc;

    @BeforeEach
    void setUp() {
        MockMvc mockMvc = MockMvcBuilders
                .standaloneSetup(new GreetingController())
                .build();

        mvc = MockMvcTester.create(mockMvc);
    }

    @Test
    void returnsGreeting() {
        assertThat(mvc.get().uri("/greetings/Lan"))
                .hasStatusOk()
                .bodyJson()
                .extractingPath("$.message")
                .isEqualTo("Hello, Lan");
    }
}
```

`MockMvcTester.create(mockMvc)` uses the exact MockMvc object that was configured. Therefore, if MockMvc is created with `standaloneSetup`, the test has the corresponding standalone scope. If MockMvc is created with `webAppContextSetup`, the tester uses the MVC infrastructure of that web application context.

Example using a web application context:

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = WebMvcConfig.class)
class GreetingControllerContextTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvcTester mvc;

    @BeforeEach
    void setUp() {
        MockMvc mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();

        mvc = MockMvcTester.create(mockMvc);
    }

    @Test
    void usesMvcConfigurationFromContext() {
        assertThat(mvc.get().uri("/greetings/Lan"))
                .hasStatusOk()
                .bodyJson()
                .extractingPath("$.message")
                .isEqualTo("Hello, Lan");
    }
}
```

If the Spring Security filter chain needs to participate, integrate security into MockMvc before creating the tester:

```java
MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();

MockMvcTester mvc = MockMvcTester.create(mockMvc);
```

`MockMvcTester` does not add filters or security configuration that the original MockMvc does not already have. It inherits the scope and behavior of the MockMvc passed into it.

## 5. Creating Requests and Asserting Status

MockMvcTester provides methods for creating requests by HTTP method. For example:

```java
mvc.get().uri("/products");
mvc.post().uri("/products");
mvc.put().uri("/products/{id}", 12);
mvc.patch().uri("/products/{id}", 12);
mvc.delete().uri("/products/{id}", 12);
```

The request builders allow configuring the URI and necessary request attributes before execution. URI templates with variables can be used to avoid manually concatenating path strings.

After the request is executed, use AssertJ to verify the status:

```java
assertThat(mvc.get().uri("/health"))
        .hasStatusOk();
```

For endpoints that return errors according to an API contract, you can check the corresponding status and error body using the assertions provided for MockMvcTester results. The exact assertion syntax should be checked in the Javadoc of the exact Spring Test version your project uses, as the API can expand across release lines.

### Chaining Multiple Assertions

Assertions can be chained together to describe the expected response:

```java
assertThat(mvc.get().uri("/greetings/Lan"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.message")
        .isEqualTo("Hello, Lan");
```

Reading in order: send a GET, assert HTTP 200, read the response body as JSON, extract the `message` field, and compare the value. This style leverages AssertJ's assertion chaining capability.

## 6. Verifying Text and JSON Response Bodies

MockMvcTester provides body assertions suited to the response content type.

### Text Body

For an endpoint returning a plain string:

```java
@RestController
class StatusController {

    @GetMapping(value = "/status-text", produces = MediaType.TEXT_PLAIN_VALUE)
    String statusText() {
        return "service-ready";
    }
}
```

Test:

```java
assertThat(mvc.get().uri("/status-text"))
        .hasStatusOk()
        .bodyText()
        .isEqualTo("service-ready");
```

`bodyText()` returns an assertion for text content. Tests can compare the entire string or use AssertJ string assertions such as `contains`, `startsWith`, and `isEqualTo`.

### JSON Body

For JSON responses, `bodyJson()` provides an assertion API tailored to JSON structure. You can extract a value using JSONPath:

```java
assertThat(mvc.get().uri("/greetings/Lan"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.message")
        .isEqualTo("Hello, Lan");
```

For JSON containing arrays or nested objects, JSONPath lets you verify the fields of interest without comparing the entire JSON string character by character.

Response example:

```json
{
  "id": 12,
  "owner": {
    "username": "alice"
  },
  "tags": ["spring", "testing"]
}
```

JSONPath expressions can target:

| Field | JSONPath |
| --- | --- |
| ID | `$.id` |
| Owner's username | `$.owner.username` |
| First element of tags | `$.tags[0]` |

If you need to assert the entire JSON, you can use the appropriate JSON assertion for the Spring Test version in use. When only a few response properties need checking, `extractingPath(...)` usually makes tests less sensitive to field ordering and unrelated data.

## 7. Using MockMvcTester with Error Responses

An endpoint can return errors through `@ExceptionHandler`, `@RestControllerAdvice`, `ResponseStatusException`, or default resolvers. MockMvcTester still verifies the HTTP result through the same Spring MVC processing flow.

Example controller throwing an exception:

```java
@RestController
class OrderController {

    @GetMapping("/orders/{id}")
    Map<String, String> find(@PathVariable long id) {
        throw new OrderNotFoundException(id);
    }
}
```

Advice mapping the exception to a response:

```java
@RestControllerAdvice
class ApiErrorHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<Map<String, String>> handle(OrderNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Collections.singletonMap("error", exception.getMessage()));
    }
}
```

The test can focus on the status and error content:

```java
assertThat(mvc.get().uri("/orders/{id}", 77))
        .hasStatus(HttpStatus.NOT_FOUND)
        .bodyJson()
        .extractingPath("$.error")
        .isEqualTo("Order 77 was not found");
```

The example assumes `OrderNotFoundException` returns the message `Order 77 was not found` and the advice is registered in the MVC context. When testing an unhandled exception, distinguish between errors mapped to a response by Spring MVC and errors that actually escape the dispatch process. The assertion API for failures and exceptions may vary by version; consult the corresponding Javadoc if you need to inspect the root cause instead of the response.

## 8. Combining MockMvcTester with Spring Security

MockMvcTester uses MockMvc underneath, so post-processors and filters integrated with MockMvc remain the foundation of the test. When an endpoint requires authentication, you need to configure the security filter chain and establish an authentication state for the request.

Example with Spring Security Test:

```java
assertThat(mvc.get().uri("/profile")
        .with(user("alice").roles("USER")))
        .hasStatusOk()
        .bodyText()
        .isEqualTo("alice");
```

The `user(...)` request post-processor creates an `Authentication` for the simulated user. If using a Boot auto-configured `MockMvcTester`, ensure the security configuration is actually loaded and the filter chain is attached to MockMvc. If creating MockMvc manually, use `.apply(springSecurity())` before calling `MockMvcTester.create(...)`.

Similarly, you can use appropriate post-processors for HTTP Basic, JWT, or CSRF if the project declares the corresponding Spring Security Test module. `MockMvcTester` does not replace the authentication setup mechanism; it only provides a different way to assert on MockMvc results.

## 9. Comparing MockMvcTester and Traditional MockMvc

| Criterion | Traditional MockMvc | MockMvcTester |
| --- | --- | --- |
| Execution style | `mockMvc.perform(RequestBuilder)` | `mvc.get()`, `mvc.post()`, or corresponding request builder |
| Assertion | `andExpect(ResultMatcher)` | AssertJ `assertThat(...)` and fluent assertions |
| Status check | `status().isOk()` | `hasStatusOk()` |
| JSON check | `jsonPath(...)` | `bodyJson().extractingPath(...)` |
| Text check | `content().string(...)` | `bodyText().isEqualTo(...)` |
| Underlying infrastructure | Spring MVC Test | Spring MVC Test/MockMvc |
| Version requirement | Available in older Spring lines | Spring Framework 6.2 or later |
| AssertJ | Not required | Required on the classpath |
| Starts a real HTTP server | No | No |

Traditional MockMvc has a rich ecosystem of matchers and remains a stable API. MockMvcTester provides a more natural AssertJ experience, especially when the team is already familiar with `assertThat`, `isEqualTo`, `contains`, and assertion chains.

The two APIs are not mutually exclusive. A project can keep older tests using `MockMvc`, write new tests with `MockMvcTester`, or use `MockMvc` directly in cases requiring a specialized matcher not yet conveniently expressed with AssertJ.

## 10. Limitations of MockMvcTester

The new name and fluent API do not change MockMvc's testing scope. MockMvcTester still uses simulated Servlet requests/responses inside the test process.

It does not verify:

- Whether embedded Tomcat, Jetty, or Undertow starts successfully.
- Whether connectors open ports and accept requests over TCP.
- Whether TLS, reverse proxies, load balancers, or network routing work properly.
- Whether a WAR deploys properly on an external Servlet container.
- Whether container settings such as context path, session cookies, error pages, or multipart limits operate properly in production.

If you need real HTTP testing, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` or deploy the application to the target container and send requests via an HTTP client. MockMvcTester is suited for testing Spring MVC in a mock environment, whereas testing the server runtime requires a different test level.

## 11. Common Mistakes When Adopting MockMvcTester

### MockMvcTester Class Not Found

A common cause is that the project is using Spring Framework prior to 6.2. Check the actual Spring Test version on the test classpath. Adding AssertJ cannot supply a class that does not exist in that Spring Test version.

### Spring Boot Cannot Inject MockMvcTester

Check the following conditions:

- The project is using Spring Boot 3.4 or later, or a newer Boot version that supports it.
- `spring-boot-starter-test` or an equivalent dependency provides Spring Test and AssertJ.
- The test has enabled MockMvc configuration, such as `@WebMvcTest` or `@AutoConfigureMockMvc`.
- Auto-configuration has not been excluded or overridden in a way that prevents the bean from being created.

If not using Boot auto-configuration, create `MockMvc` and then call `MockMvcTester.create(mockMvc)`.

### Spring Test and Spring Framework Version Mismatch

Do not mix `spring-test` 6.2 with Spring 6.1 modules in the same application. Use Spring Boot dependency management or an appropriate BOM so that Spring modules are version-aligned.

### AssertJ Missing from the Test Classpath

MockMvcTester relies on AssertJ. With Spring Boot, `spring-boot-starter-test` usually brings AssertJ in. With plain Spring Framework, you need to add `assertj-core` in `testImplementation` or the equivalent test scope.

### Expecting MockMvcTester to Start a Server

MockMvcTester does not create a server. If you need to test requests over an HTTP port, use an embedded server or a real container.

### Converting Every Assertion to the New API Unnecessarily

There is no need to rewrite all existing tests. Choose the API that makes tests readable and fits the current version. Traditional MockMvc remains useful when the team already has many matchers or helpers based on `ResultMatcher`.

## 12. Adoption Workflow in a Project

1. Check the Spring Framework/Spring Boot version managed in the build.
2. Confirm Spring Test is 6.2 or later and AssertJ is on the test classpath.
3. If using Spring Boot 3.4 or later, try injecting `MockMvcTester` in a `@WebMvcTest` or a test with `@AutoConfigureMockMvc`.
4. If using Spring Framework directly, configure MockMvc as needed and create the tester via `MockMvcTester.create(mockMvc)`.
5. Write a small test checking status and body to confirm the dependencies and API work.
6. Choose `bodyText()` for text, `bodyJson()` and JSONPath for JSON, along with appropriate status assertions.
7. Retain traditional MockMvc when tests use specialized matchers or when the project cannot upgrade versions yet.
8. Use an embedded server or real container for network and Servlet runtime testing requirements.

## 13. Conclusion

`MockMvcTester` is the AssertJ API for MockMvc, introduced in Spring Framework 6.2. Spring Boot 3.4 or later can auto-configure this bean when AssertJ is on the test classpath and MockMvc is enabled. With plain Spring Framework, you can create a tester from a configured MockMvc using `MockMvcTester.create(mockMvc)`.

The new API makes requests and assertions easier to read in AssertJ style, such as `hasStatusOk()`, `bodyText()`, and `bodyJson().extractingPath(...)`. It still uses Spring MVC Test's mock environment. Choose MockMvcTester when the version supports it and the fluent style makes tests clearer; keep traditional MockMvc when compatibility or existing matchers are needed. Both require an embedded server or real container if the goal is to test the HTTP runtime.
