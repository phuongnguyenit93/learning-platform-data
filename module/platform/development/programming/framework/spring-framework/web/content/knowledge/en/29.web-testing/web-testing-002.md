# MockMvc: `standaloneSetup` and `webAppContextSetup`

## 1. What does MockMvc test?

`MockMvc` is a Spring MVC Test (`spring-test`) tool used to create simulated HTTP requests, send them through `DispatcherServlet`, and inspect responses **without starting a real HTTP server on a network port**. It creates `MockHttpServletRequest` and `MockHttpServletResponse`, exercising handler mapping, data binding, message conversion, exception resolution, and the configured MVC components.

```text
MockMvc.perform(GET/POST/PUT/...)
    │
    ▼
MockHttpServletRequest
    │
    ▼
[Filters if added to MockMvc]
    │
    ▼
DispatcherServlet
    ├─ HandlerMapping
    ├─ HandlerAdapter / argument resolvers
    ├─ Controller → service or mock service
    ├─ HandlerExceptionResolver / @ControllerAdvice
    └─ HttpMessageConverter
    │
    ▼
MockHttpServletResponse
    │
    ▼
andExpect(status, headers, JSON, model, view...)
```

Basic example (illustrative only; the classes appear in the complete program below):

```java
mockMvc.perform(get("/api/greetings/{name}", "Ada"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.message").value("Hello, Ada"));
```

- `perform(...)` sends a mock request.
- `get(...)` / `post(...)` / `put(...)` / `delete(...)` describe the method, path, query, headers, cookies, and body.
- `andExpect(...)` verifies status, JSONPath, content type, headers, forwarded/redirected URL, or model/view.
- `andDo(print())` helps diagnose requests and responses; do not print sensitive payloads/headers.
- `andReturn()` returns `MvcResult` for deeper inspection.

**Two ways to build MockMvc that must be understood clearly**:

```text
MockMvcBuilders.standaloneSetup(controllerInstance)
    → minimal MVC infrastructure, manual configuration
    → does not load a real application context

MockMvcBuilders.webAppContextSetup(webApplicationContext)
    → uses MVC beans/configurations in a Spring web context
    → context is initialized beforehand by Spring TestContext/Boot
```

Both use the same request execution DSL, but test different scopes. That is the central topic of this lesson.

## 2. `standaloneSetup` — testing isolated controllers

`MockMvcBuilders.standaloneSetup(Object... controllers)` accepts controller instances directly (or classes to instantiate in appropriate cases) and initializes the Spring MVC infrastructure needed to run those controllers.

```java
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

GreetingService service = new GreetingService();
GreetingController controller = new GreetingController(service);

MockMvc mockMvc = MockMvcBuilders
    .standaloneSetup(controller)
    .setControllerAdvice(new ApiErrorAdvice())
    .build();
```

The classes are defined in the runnable example in section 7. With this approach:

1. **Does not load a Spring application context** to component-scan all `@Service`, `@Repository`, `@Configuration` beans or auto-wire controllers. Dependencies are supplied by the test via constructor/setter, often using fakes or Mockito mocks.
2. The builder creates a basic Spring MVC configuration including dispatching, request mapping, binding, and response conversion, so the test still exercises real MVC mechanics rather than merely calling `controller.greet("Ada")`.
3. Global `@ControllerAdvice` **is not auto-discovered via component scan**; you must use `.setControllerAdvice(adviceInstance)` if you want to test the corresponding handler.
4. Production-specific MVC configuration (custom converters, global validators, interceptors, locale resolvers, custom argument resolvers, filters/Security) may **not be present**. When they affect the test, configure them explicitly on the builder.
5. Lightweight initialization, well suited for testing many input, status, and body variations of a controller.

Example using Mockito to isolate the service layer:

```java
GreetingService mockService = Mockito.mock(GreetingService.class);
Mockito.when(mockService.greetingFor("Ada"))
    .thenReturn("Hello, Ada");

MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new GreetingController(mockService))
    .build();

mvc.perform(get("/api/greetings/{name}", "Ada"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.message").value("Hello, Ada"));

Mockito.verify(mockService).greetingFor("Ada");
```

This is an **illustrative snippet**; you need to import `Mockito` and the static MockMvc/JUnit helpers as in the complete example. Mocking the service tests the controller independently of a database; it does not verify the real service's implementation/wiring.

### Additional configuration with `StandaloneMockMvcBuilder`

Useful hooks:

- `setControllerAdvice(...)`: register exception handlers and binding advice to be tested.
- `setMessageConverters(...)`: specify HTTP converters, e.g. a non-default Jackson configuration.
- `setValidator(...)`: validator used when checking `@Valid`/binding.
- `setConversionService(...)`: conversion rules for path/query/body.
- `setCustomArgumentResolvers(...)` / `setCustomReturnValueHandlers(...)`: custom method argument/return mechanisms.
- `addInterceptors(...)`: run selected MVC interceptors.
- `defaultRequest(...)`: request properties applied by default.
- `alwaysExpect(...)` / `alwaysDo(...)`: shared expectations/hooks for the test suite.

Example:

```java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new GreetingController(new GreetingService()))
    .setControllerAdvice(new ApiErrorAdvice())
    .defaultRequest(get("/").accept(MediaType.APPLICATION_JSON))
    .build();
```

This **illustrates the builder**; `MediaType` and static `get` must be imported. Using `alwaysExpect(status().isOk())` will cause intentional HTTP 404 tests to fail, so only set global expectations when all cases share that condition.

**Do not confuse:** `standaloneSetup` still uses MVC infrastructure built for the test. It is close to a unit test in scope/controller dependencies, but it is not a pure unit test of a Java method.

## 3. `webAppContextSetup` — testing Spring MVC configuration in a context

`MockMvcBuilders.webAppContextSetup(WebApplicationContext)` uses an **already initialized Spring web application context** (with a `ServletContext`). `DispatcherServlet` discovers controllers, handler mappings, converters, validators, exception resolvers, `@ControllerAdvice`, and the MVC beans present in the context. This helps catch component-scan, bean-injection, and configuration errors that standalone setup may miss.

Example with Spring Boot:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class GreetingWebContextTest {
    @Autowired
    WebApplicationContext webContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.webAppContextSetup(webContext).build();
    }

    @Test
    void responds() throws Exception {
        mockMvc.perform(get("/api/greetings/{name}", "Ada"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("Hello, Ada"));
    }
}
```

This is a **short illustrative snippet**, omitting imports and models; section 7 has the complete program. `@SpringBootTest(webEnvironment=MOCK)` in Spring Boot Servlet/MVC starts an appropriate application context without **opening a real server port**. When the test class sits under the root package containing `@SpringBootApplication`, Boot finds the corresponding startup configuration.

Differences from standalone:

- Controller/service/advice are constructed and injected by Spring as beans. If a bean is missing, the context may fail to start.
- Real Spring MVC configuration is applied (e.g. `WebMvcConfigurer`, exception resolvers, message converters configured by the context).
- Context loading cost is usually higher and may trigger database/messaging/application startup logic if declared by the app.
- Spring TestContext **caches the application context** across tests with compatible configurations. Avoid `@DirtiesContext` or needlessly changing profiles/properties per class, as that easily invalidates the cache.

### Plain Spring Framework TestContext

Even without Boot, JUnit 5 and Spring can be combined:

```java
@SpringJUnitWebConfig(classes = TestWebConfig.class)
class MvcContextTest {
    @Autowired
    WebApplicationContext context;

    MockMvc mockMvc;

    @BeforeEach
    void setup() {
        mockMvc = MockMvcBuilders.webAppContextSetup(context).build();
    }
}
```

This is an **illustrative sample, not a standalone file**: `TestWebConfig` must be created with `@EnableWebMvc`, the controller, and required dependencies. `@SpringJUnitWebConfig` combines `@ExtendWith(SpringExtension.class)`, `@ContextConfiguration`, and `@WebAppConfiguration`. If using separate annotations, configure both the context and the web environment properly, not just `@ContextConfiguration`.

## 4. Comparison table for choosing

| Criterion | `standaloneSetup` | `webAppContextSetup` |
| --- | --- | --- |
| Input | Specific controller instance/class | Initialized `WebApplicationContext` |
| ApplicationContext | Does not load application context | Uses context from Spring TestContext/Boot |
| Service/repository DI | Test creates/mocks dependencies manually | Beans managed and injected by Spring |
| `@ControllerAdvice` | Must be registered via `setControllerAdvice` when needed | Discovers advice beans in the context |
| Converter/validator/interceptor | Default MVC, customized on builder | Uses declared MVC beans/configuration |
| Security/filters | Must be wired explicitly when needed | Also needs to ensure the filter chain actually enters MockMvc |
| Ability to detect wiring errors | Limited | Better, depending on how much of the context is loaded |
| Execution time | Usually fast, compact setup | Has context startup cost, cached |
| Real network/server port | No | No |
| Primary goal | Controller contract, edge cases | MVC configuration and collaboration between beans |

**Practical choices:**

- When testing many request shapes of a controller and mocking services: `standaloneSetup` fits well because dependencies are clearly controlled and tests run fast.
- When verifying `@ControllerAdvice`/`WebMvcConfigurer`, custom converters, filters, wiring, and behavior under app configuration: `webAppContextSetup` is a better fit.
- In larger projects, combine standalone for most controller tests with representative context tests to protect MVC configuration.
- Spring Boot `@WebMvcTest` creates an **MVC slice context** and usually auto-injects `MockMvc`. It has a smaller scope than full-context `@SpringBootTest` and is **not synonymous** with the `webAppContextSetup` builder itself, though it uses Spring MVC Test infrastructure.

## 5. Matchers and accurate testing techniques

Common calls:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

mockMvc.perform(get("/api/greetings/{name}", "Ada")
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Request-Id", "test-1"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.message").value("Hello, Ada"));

mockMvc.perform(post("/api/books")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"title\":\"Spring\"}"))
    .andExpect(status().isCreated());

mockMvc.perform(get("/absent"))
    .andExpect(status().isNotFound());
```

The last two requests **only illustrate the matcher API**: matching endpoints are required to run them. `contentType(MediaType.APPLICATION_JSON)` specifies the request body media type; `accept(MediaType.APPLICATION_JSON)` is the expected response media type. For a JSON POST, calling `.content(...)` alone may not be enough for the framework to pick the right converter.

Other expectations:

- `header().string("Location", "...")`: response headers.
- `content().json("{\"message\":\"...\"}")`: JSON structure matching.
- `handler().handlerType(GreetingController.class)` and `handler().methodName("greet")`: whether mapping hits the expected controller/method.
- `model().attributeExists("product")` / `view().name("products")`: MVC view rendering.
- `redirectedUrl("/login")` / `forwardedUrl("/...")`: redirect/forward.
- `request().asyncStarted()`, `asyncDispatch(...)`: controllers with Spring MVC async types.

**MockMvc does not test real HTTP networking:** requests go straight into the Servlet MVC infrastructure. To verify TCP, TLS, reverse proxies, servlet containers, HTTP keepalive, or browser behavior, you need end-to-end tests against a real server, such as `@SpringBootTest(webEnvironment = RANDOM_PORT)` and an HTTP client.

## 6. Security, filters, and mock servlet limits

**A common source of false positives:** `webAppContextSetup(context).build()` has an MVC context, but does not by default guarantee *every runtime servlet filter* has been added to the mock chain. For custom filters, you may need:

```java
MockMvc mockMvc = MockMvcBuilders
    .webAppContextSetup(context)
    .addFilters(auditFilter)
    .build();
```

This is an **illustrative snippet**: `auditFilter` is a `Filter` bean in the context. With Spring Security, when depending on `spring-security-test`, you can use `.apply(springSecurity())` (depending on the app needing the appropriate `springSecurityFilterChain`). When Spring Boot uses `@AutoConfigureMockMvc`, Boot has logic to add appropriate filters; verify which config runs in the test.

`@WithMockUser` creates a security context for the test, and does not replace ensuring a valid security filter chain when the test genuinely intends to verify authorization and CSRF. A GET returning 200 when filters are bypassed does not prove the endpoint is protected.

Similarly, MockMvc does not simulate a gateway dropping connections, TLS handshakes, HTTP/2 multiplexing, proxy header rewriting, socket timeouts, or real load limits. Choose tests according to the risk you want to check.

## 7. Complete Java 17+ example running both setups

This exercise uses **Java 17+, Spring Boot 3.3.13, Spring MVC, JUnit Jupiter**. Both test classes test the same controller and exception advice: standalone builds collaborators/advice manually; web context obtains them from Spring. Runs `gradle test` without opening an HTTP server or needing a database.

Structure:

```text
mockmvc-two-setups/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── GreetingApplication.java
    │   ├── GreetingService.java
    │   ├── GreetingController.java
    │   └── ApiErrorAdvice.java
    └── test/java/demo/
        ├── GreetingStandaloneTest.java
        └── GreetingWebContextTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'mockmvc-two-setups'
```

**`build.gradle`** — JDK 17+, Gradle 8.x (no Spring Boot plugin needed when only running tests):

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web:3.3.13'
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}

tasks.test {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed'
    }
}
```

The starters bring in Spring MVC/Jackson and Spring Test/JUnit/Mockito; there is no need to build a `bootJar` to learn the two builders.

**`src/main/java/demo/GreetingApplication.java`**

```java
package demo;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GreetingApplication {
}
```

The root configuration class is enough for `@SpringBootTest` to find and initialize the application context in package `demo`. No `main` method is needed because this example only runs tests.

**`src/main/java/demo/GreetingService.java`**

```java
package demo;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greetingFor(String name) {
        if ("missing".equals(name)) {
            throw new MissingNameException(name);
        }
        return "Hello, " + name;
    }
}

class MissingNameException extends RuntimeException {
    MissingNameException(String name) {
        super("Name not found: " + name);
    }
}
```

The service has no DB and has two behaviors: returning a greeting, or throwing a business exception when name is `missing`.

**`src/main/java/demo/GreetingController.java`**

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingController {
    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/{name}")
    public GreetingResponse greet(@PathVariable("name") String name) {
        return new GreetingResponse(greetingService.greetingFor(name));
    }
}

record GreetingResponse(String message) {}
```

The response uses a record, which Jackson converts to JSON with property `message`.

**`src/main/java/demo/ApiErrorAdvice.java`**

```java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorAdvice {
    @ExceptionHandler(MissingNameException.class)
    public ResponseEntity<ErrorResponse> handleMissing(MissingNameException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ErrorResponse(ex.getMessage()));
    }
}

record ErrorResponse(String error) {}
```

The handler maps `MissingNameException` to HTTP 404 with JSON body `{"error":"Name not found: missing"}`.

**`src/test/java/demo/GreetingStandaloneTest.java`**

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class GreetingStandaloneTest {
    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        GreetingController controller =
            new GreetingController(new GreetingService());

        mvc = MockMvcBuilders.standaloneSetup(controller)
            .setControllerAdvice(new ApiErrorAdvice())
            .build();
    }

    @Test
    void returnsGreeting() throws Exception {
        mvc.perform(get("/api/greetings/{name}", "Ada"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.message").value("Hello, Ada"));
    }

    @Test
    void mapsBusinessErrorWithExplicitAdvice() throws Exception {
        mvc.perform(get("/api/greetings/{name}", "missing"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.error").value("Name not found: missing"));
    }
}
```

This class **does not use `@SpringBootTest`**. `new GreetingService()` and `new ApiErrorAdvice()` are created directly by the test, making it clear where the controller dependencies and exception handler are configured.

**`src/test/java/demo/GreetingWebContextTest.java`**

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class GreetingWebContextTest {
    @Autowired
    private WebApplicationContext context;

    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = MockMvcBuilders.webAppContextSetup(context).build();
    }

    @Test
    void usesSpringManagedControllerAndService() throws Exception {
        mvc.perform(get("/api/greetings/{name}", "Ada"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.message").value("Hello, Ada"));
    }

    @Test
    void discoversAdviceInSpringContext() throws Exception {
        mvc.perform(get("/api/greetings/{name}", "missing"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.error").value("Name not found: missing"));
    }
}
```

In the web context setup, Spring finds `GreetingController`, `GreetingService`, and `ApiErrorAdvice` by component scanning from package `demo`, then performs constructor injection. The test verifies both the HTTP contract **and** that the Spring components are wired properly.

From the project directory, using JDK 17+ and Gradle 8.x:

```bash
gradle test
```

The command runs **4 `@Test` methods** (two standalone and two web context). When passing, Gradle reports `BUILD SUCCESSFUL` and generates a report at `build/reports/tests/test/index.html`. Detailed log lines may vary by Gradle, operating system, and test runner; there is no need to predict exact stdout.

If you want to run via the Gradle Wrapper, you can generate the wrapper with an installed Gradle and run `./gradlew test` (Linux/macOS) or `gradlew.bat test` (Windows).

## 8. Extending tests by goal

**Controller requiring real validation:** If the code uses `@Valid`, Jakarta Bean Validation, and custom validators, standalone needs to ensure validators/converters match runtime. Web context tests help catch misconfigured `Validator`/`@ControllerAdvice` beans. A Spring Boot application may need the `spring-boot-starter-validation` dependency; `spring-boot-starter-web` does not guarantee the entire Bean Validation API/implementation.

**Controller requiring Security:** With `spring-security-test`, configure MockMvc with the right filter chain and appropriate user/CSRF. `@WithMockUser` does not make filters appear automatically if the MockMvc builder does not attach security. Controller advice can handle domain exceptions, whereas authentication failures are primarily handled in the filter chain; do not confuse the two layers.

**Testing MVC async:** For `Callable`, `DeferredResult`, or Spring MVC async return types, you can assert `request().asyncStarted()` and then call `asyncDispatch`:

```java
MvcResult pending = mvc.perform(get("/async"))
    .andExpect(request().asyncStarted())
    .andReturn();

mvc.perform(asyncDispatch(pending))
    .andExpect(status().isOk());
```

This is an **illustrative snippet**, requiring a suitable `/async` endpoint. Do not use this API to assume every Reactor `Flux` is equivalent to servlet async.

**Boot MVC test slice:** `@WebMvcTest(GreetingController.class)` typically loads a web slice faster than full `@SpringBootTest` and injects `MockMvc` via `@AutoConfigureMockMvc`. The controller's service dependencies need mocks or corresponding test beans (Boot 3.3 uses `@MockBean`; newer versions have `@MockitoBean`). This is an intermediate option between standalone and full context, distinct from the direct role of the two builders being studied.

**Testing databases/external APIs:** Standalone is suited for mocking collaborators; full context may also need a fake/embedded DB or stubbed external service for stability. Do not use mock requests to confirm DB migrations, network retries, secure cookies at a proxy, or successful TLS handshakes.

## 9. Common mistakes when choosing and writing tests

1. **Assuming `standaloneSetup` automatically component-scans all beans.** Pass controller dependencies, advice, and MVC customizations manually.
2. **Forgetting `setControllerAdvice`** in standalone, causing the service to throw an exception that is not converted as at runtime.
3. **Instantiating the controller with `new` inside a web-context test.** Doing so bypasses the dependency injection you want to verify; use the beans in the context.
4. **Forgetting `@WebAppConfiguration`/`@SpringJUnitWebConfig`** when using plain Spring TestContext, resulting in no `WebApplicationContext` with a `ServletContext`.
5. **Thinking `webAppContextSetup` runs a real HTTP server.** Both builders use a mock servlet; `RANDOM_PORT` is needed for network integration.
6. **Not attaching filters/Security chain** when testing authorization, giving 200/403 assertions the wrong meaning.
7. **Asserting only status 200** while ignoring JSON, headers, content-type, and exception handling.
8. **Setting `alwaysExpect(status().isOk())`** on a builder also used for testing 404/400 cases.
9. **Sending a JSON request without `Content-Type: application/json`**, leading to 415 or behavior differing from runtime.
10. **Confusing `@WebMvcTest` with a full context**, then expecting services/repositories to be component-scanned automatically.
11. **Mocking the very class under test**, such as mocking `GreetingController` and assuming request mapping and serialization were tested.
12. **Using `@DirtiesContext` indiscriminately** or varying configuration per class, making the context cache ineffective.
13. **Comparing the entire JSON string rigidly** when key ordering/escaping may differ; prefer JSONPath or JSON structural matching.
14. **Assuming MockMvc reproduces production network/Servlet containers**, when TLS/proxy, connection, and socket limits lie outside test scope.

When a case fails, inspect `andDo(print())` and analyze in order: path/method → handler mapping → argument binding → controller/service exception → advice → converters → filters/Security → response assertions.

## 10. Self-check questions

1. **Does `standaloneSetup(new Controller(...))` load `@Service` via Spring?** → No. The test manually creates or mocks collaborators and passes them into the controller.
2. **Does standalone automatically detect production `@RestControllerAdvice`?** → No; you need `setControllerAdvice` or manual configuration.
3. **Does `webAppContextSetup(context)` use a server socket?** → No; it uses `DispatcherServlet` on simulated requests/responses.
4. **Which should you choose to detect missing bean injection in a controller?** → A web-context test is more likely to catch it because Spring actually instantiates and wires the beans.
5. **Why are context tests usually slower than standalone?** → They need to load the context, though TestContext caches contexts with identical configurations.
6. **What is the risk of using `@SpringBootTest(MOCK)` while forgetting the Security filter in MockMvc?** → Authorization tests can give misleading results; verify that the filter chain is applied.
7. **When should `@WebMvcTest` be used?** → When you want an MVC slice with selected controllers/advice/converters, faster than loading the whole application.
8. **If you want to test HTTPS/a real port, is MockMvc enough?** → No; you need an HTTP client hitting a real server in an appropriate environment.
9. **To test a controller's 404 JSON error, what must be asserted?** → HTTP 404 and the error body (e.g. `$.error`), while ensuring the advice is properly registered.

## 11. References

- Spring Framework — MockMvc configuring/setup: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/setup.html
- Spring Framework — Setup options: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/setup-options.html
- Spring Framework — MockMvc requests: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/requests.html
- Spring Framework — MockMvc expectations: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/expectations.html
- Spring Framework 6.1 — `MockMvcBuilders` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/test/web/servlet/setup/MockMvcBuilders.html
- Spring Framework 6.1 — `StandaloneMockMvcBuilder` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/test/web/servlet/setup/StandaloneMockMvcBuilder.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/docs/3.3.13/reference/html/features.html#features.testing
