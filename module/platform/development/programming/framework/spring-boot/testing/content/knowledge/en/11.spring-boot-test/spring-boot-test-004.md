# `@AutoConfigureMockMvc` with a full context

## 1. Goal: run Spring MVC close to the real application, without starting an HTTP server

When testing a Spring Boot API, we want more than knowing what a controller method returns. Many bugs only surface when a real request flows through **request mapping, JSON conversion, validation, servlet filters, exception handling, services, and repositories**. For applications using Spring MVC (Servlet stack), combining:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class ProductApiTest {
    // Tests using MockMvc.
}
```

loads the **full Spring Boot application context** while auto-configuring a `MockMvc` bean to send requests **inside the test process**. `MockMvc` uses mock Servlet API requests/responses and Spring MVC's processing pipeline, **without opening a network port or starting an embedded HTTP server**.

That is the point to understand accurately: **full context ≠ real HTTP server**. The test suite can exercise real controllers/services/repositories while still not testing sockets, TLS, proxies, HTTP/2, container/network behavior, or full production deployment characteristics.

After this lesson, you will be able to:

- Distinguish `@SpringBootTest + @AutoConfigureMockMvc` from `@WebMvcTest`, `MockMvcBuilders.standaloneSetup(...)`, and `RANDOM_PORT` testing.
- Set up a Spring MVC test using **real application beans** across controller → service → repository.
- Verify status codes, JSON bodies, content types, 404 errors, request validation, and malformed JSON errors with JUnit Jupiter.
- Understand `addFilters`, Spring Security, CSRF, `@ActiveProfiles`, bean mocking, transactions, and context caching.
- Read the right imports/dependencies for Spring Boot 3.x and Spring Boot 4.x; troubleshoot common IDE/CLI/CI errors.

**Context:** Spring Boot Testing, Java 17+, JUnit Jupiter. The example runs standalone in **a Spring Boot 3.x Servlet MVC project** with the listed dependencies; there is no database, Docker, networking, or Spring Security in the basic sample. Examples for Boot 4.x are marked separately because packages/modules have changed.

## 2. Execution mechanism and each annotation's responsibility

### 2.1. `@SpringBootTest`: loading application configuration

`@SpringBootTest` initializes the Spring Boot ApplicationContext based on the application's configuration, rather than loading only an MVC “slice”. In a typical application with `@SpringBootApplication`, this includes component scanning and auto-configuration applicable to the present dependencies.

For example, the context may contain:

- `@RestController` / `@ControllerAdvice`;
- `@Service`, `@Repository`, and their dependencies;
- `@ConfigurationProperties`, configuration beans, MVC converters, validators;
- Security filter chain if Spring Security is enabled;
- DataSource/JPA/migrations/external clients if required by application configuration.

**“Full” must be understood within the scope of the test configuration actually loaded.** Test profiles, `properties`, exclusions, conditional beans, and mock overrides can make the context differ from production. `@SpringBootTest` does not automatically load integrations whose dependencies are absent from the classpath or disabled.

When using `WebEnvironment.MOCK` on Servlet MVC:

- Creates a web application context with a mock servlet environment.
- **Does not** start embedded Tomcat/Jetty/Undertow to listen for HTTP.
- Allows testing real beans in the context.
- Does not require `@LocalServerPort` since there is no real listening port.

`MOCK` is the default for `@SpringBootTest`, but stating it explicitly in tutorials or integration tests can make intent clearer. If Servlet MVC is absent from the classpath, Boot detects a different web application type; do not apply `MockMvc` to a WebFlux-only app without checking configuration.

### 2.2. `@AutoConfigureMockMvc`: creating MockMvc for the context

This annotation **does not replace** `@SpringBootTest` and does not turn the test into `@WebMvcTest`. It adds auto-configuration for `MockMvc` backed by the web application context under test.

In a standard test:

```java
@Autowired
MockMvc mockMvc;
```

is enough to perform requests. You do not need to manually write `MockMvcBuilders.standaloneSetup(controller)`, because doing so can accidentally bypass controller advice, filters, message converters, or the real application context's MVC configuration.

Conceptual processing path:

```text
JUnit Jupiter
   │
   ├── Spring TestContext → initializes / reuses cached ApplicationContext
   │     ├── Spring MVC infrastructure and DispatcherServlet
   │     ├── Controller + ControllerAdvice
   │     ├── Real Service + Real Repository (if present)
   │     └── Filter, Converter, Validator, Security ... per configuration
   │
   └── MockMvc.perform(mock request)
         → [Servlet Filter chain if registered]
         → DispatcherServlet → HandlerMapping
         → Controller → Service → Repository
         → HttpMessageConverter / ExceptionResolver
         → mock HTTP response
         → andExpect(...) for assertions
```

**There is no network hop** in this diagram. Requests execute inside the test JVM and responses are `MockHttpServletResponse`.

### 2.3. Do not confuse “MockMvc” with “every bean is mocked”

The word `Mock` in **MockMvc** refers only to mocking **Servlet API requests/responses**; it does not mean `@Service` or `@Repository` automatically becomes a Mockito mock. When combining `@SpringBootTest` with `@AutoConfigureMockMvc`, real services/repositories will run unless you intentionally replace them.

If a service needs a real database, the test can execute real SQL; if a bean calls an external API on startup, the test can also trigger real I/O unless isolated. That is both the strength of testing multi-layer collaboration and the responsibility of fixture setup.

## 3. Choosing the right test type: comparison table

| Approach | Context / infrastructure | Best suited for |
|---|---|---|
| Unit test calling controller method directly | No Spring MVC pipeline | Very small logic inside a method, fastest |
| `MockMvcBuilders.standaloneSetup(controller)` | Manually configured Mock MVC for a controller | Controlled mapping/binding/exception behavior without loading all of Spring |
| `@WebMvcTest(Controller.class)` | **MVC slice**; limited component scan and auto-configuration | Fast web layer tests; dependencies outside MVC are usually mocked/imported |
| **`@SpringBootTest + @AutoConfigureMockMvc`** | **Full ApplicationContext** + mock Servlet, no real server | Integration from HTTP contract through MVC, services, and real beans |
| `@SpringBootTest(webEnvironment = RANDOM_PORT)` | Full context **and real embedded server** | Verifying real HTTP stack, network, ports, client serialization |
| Deployed staging/production-like E2E | Deployed system and real external dependencies | Verifying ingress, TLS, proxies, cloud/network/external JVM config |

**Prefer the narrowest option that still catches the bug you want to find.** Not every controller test needs a full context; nor should you rely only on `@WebMvcTest` if the bug lies in how a service and repository interact.

### 3.1. Why do `@WebMvcTest` and full context differ?

`@WebMvcTest` only loads MVC-related components, such as controllers, controller advice, filters, converters, and annotation-supported MVC infrastructure. Ordinary services/repositories are **not scanned automatically as in the full application**. Authors usually supply controller dependencies via mocks or test configurations.

In contrast, `@SpringBootTest` initializes the entire application configuration. If real services involve JPA repositories, migrations, or an external client bean, they may be initialized. This gives tests broader integration coverage, but also makes them slower or harder to isolate.

**Note:** `@WebMvcTest` already configures MockMvc. Adding `@AutoConfigureMockMvc` to `@WebMvcTest` does not turn that slice into a full context. Only by using `@SpringBootTest` (without otherwise restricting the context) do you get the full application model covered in this lesson.

### 3.2. Why doesn't `RANDOM_PORT` use MockMvc to test real HTTP?

With `@SpringBootTest(webEnvironment = RANDOM_PORT)`, Spring Boot opens an embedded HTTP server on a random port. You can use `TestRestTemplate`, `WebTestClient`, or a suitable client to send requests over a real socket.

Conversely, `MockMvc.perform(...)` **does not send HTTP to that server**; it runs through the mock Servlet pipeline. If a test uses `RANDOM_PORT` yet only calls `MockMvc`, you have not tested the network hop. Avoid mistaking an in-process integration test for a real HTTP integration test.

## 4. Versions and dependencies: verify before copying code

### 4.1. Spring Boot 3.x

In Boot 3.x, common imports are:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
```

A **Spring Boot 3.x, Java 17+** project with REST MVC, JSON, and Bean Validation typically needs the following dependencies:

**Gradle Groovy DSL — relevant snippet in `build.gradle`:**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Maven — relevant snippet in `pom.xml`:**

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

These snippets are **not standalone build files**: a real build needs the Boot plugin/parent/BOM, repositories, compiler/toolchain, and appropriate Surefire/JUnit Platform setup. Do not duplicate dependencies if the project already declares them. Boot 3.x uses the Jakarta namespace, e.g., `jakarta.validation.Valid` and `jakarta.validation.constraints.Min`.

**Why add the validation starter?** In modern Spring Boot branches, you should not assume the web starter includes a Bean Validation implementation. The example in section 5 uses `@Valid` + `@Min` and expects HTTP 400 for invalid input; a working Bean Validation provider is required, typically brought in by `spring-boot-starter-validation`.

### 4.2. Spring Boot 4.x changes packages and modules

In **Spring Boot 4.x**, the corresponding annotation package is organized inside the MVC test module:

```java
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
```

Modular starters include:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-webmvc-test'
}
```

This is a **guide snippet for Boot 4.x projects**, not an instruction to change packages in a 3.x project. Boot 4 also includes changes to Java, testing libraries, JSON, and other modules; check your project's dependency BOM, APIs/JUnit, and version documentation before migrating all code.

**Important:** seeing `Cannot resolve symbol AutoConfigureMockMvc` does not mean the annotation was deleted. First verify the exact Boot major version and import the matching package, then check that test dependencies resolved. Do not mix Boot 4 modules with Boot 3 ad hoc.

### 4.3. Annotation options

On Boot 3.x, `@AutoConfigureMockMvc` supports common options:

- `addFilters = true` (**default**): registers Servlet `Filter`s from the application context into MockMvc.
- `addFilters = false`: skips adding filters from the context to MockMvc; do not use this as a way to “fix” 401/403 if security is a testing goal.
- `print` and `printOnlyOnFailure`: control printing request/response diagnostics per configuration and test outcome.
- HtmlUnit/Selenium integrations are enabled when matching dependencies are present, depending on version and supported options.

In Boot 4.x, HtmlUnit/WebDriver options are organized differently; do not assume every Boot 3 attribute retains the exact same name. `addFilters`, `print`, and `printOnlyOnFailure` remain documented on the Boot 4 annotation.

## 5. Complete example: GET/POST through real controller, service, and repository

We build a small REST API with no external database dependency to prove a full context runs real beans. The repository holds an **immutable price table** in memory; no test mutates shared data.

Endpoints:

- `GET /api/products/BOOK` → JSON product details.
- `GET /api/products/UNKNOWN` → HTTP 404.
- `POST /api/products/BOOK/quotes` with JSON body `{"quantity":3}` → HTTP 201, total = 3600.
- POST quantity 0 → HTTP 400 from Bean Validation.
- POST malformed JSON body → HTTP 400 from message conversion.

Use **Java 17+ / Spring Boot 3.x** as in section 4.1. Do not add Spring Security for the main example; if your learning project already has the security starter, read section 8 before running requests expected to return 200/201.

### 5.1. File structure

```text
project/
├── build.gradle                   # or pom.xml
└── src/
    ├── main/java/com/example/fullmvc/
    │   ├── FullMvcApplication.java
    │   ├── ProductRepository.java
    │   ├── ProductService.java
    │   └── ProductController.java
    └── test/java/com/example/fullmvc/
        └── ProductApiIntegrationTest.java
```

The app class resides in root package `com.example.fullmvc`. The remaining classes share the package, placing them inside `@SpringBootApplication`'s default component scan.

### 5.2. Application entry point

**File `src/main/java/com/example/fullmvc/FullMvcApplication.java`:**

```java
package com.example.fullmvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FullMvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(FullMvcApplication.class, args);
    }
}
```

No manual servlet or `MockMvc` setup is needed in production code. Spring Boot configures MVC based on the classpath; `MockMvc` is a test tool.

### 5.3. Real repository with immutable data

**File `src/main/java/com/example/fullmvc/ProductRepository.java`:**

```java
package com.example.fullmvc;

import java.util.Map;
import java.util.Optional;

import org.springframework.stereotype.Repository;

@Repository
public class ProductRepository {
    private final Map<String, Long> prices = Map.of(
            "BOOK", 1200L,
            "PEN", 500L
    );

    public Optional<Long> findUnitPrice(String sku) {
        return Optional.ofNullable(prices.get(sku));
    }
}
```

This is a real `@Repository` bean. It uses neither Mockito nor a database. `Map.of(...)` prevents structural modification, keeping tests isolated since shared data cannot be mutated. If you replace the repository with real JPA, you must prepare a database and fixtures per section 9.

### 5.4. Real service enforcing business rules

**File `src/main/java/com/example/fullmvc/ProductService.java`:**

```java
package com.example.fullmvc;

import java.util.Optional;

import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Optional<ProductView> find(String sku) {
        return repository.findUnitPrice(sku)
                .map(price -> new ProductView(sku, price));
    }

    public Optional<QuoteView> quote(String sku, int quantity) {
        return repository.findUnitPrice(sku)
                .map(price -> new QuoteView(
                        sku,
                        quantity,
                        Math.multiplyExact(price, (long) quantity)
                ));
    }

    public record ProductView(String sku, long unitPrice) {}

    public record QuoteView(
            String sku,
            int quantity,
            long total
    ) {}
}
```

The service knows nothing about HTTP status codes, JSON, or `MockMvc`. It takes a real dependency via constructor injection and returns Java records. `Math.multiplyExact` guards multiplication against overflow, though the example does not need to test the overflow branch; add corresponding cases if that is part of your project's business contract.

### 5.5. Real controller and validation

**File `src/main/java/com/example/fullmvc/ProductController.java`:**

```java
package com.example.fullmvc;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/products")
public class ProductController {
    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/{sku}")
    public ProductService.ProductView get(
            @PathVariable String sku
    ) {
        return service.find(sku).orElseThrow(() ->
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Product not found"));
    }

    @PostMapping("/{sku}/quotes")
    @ResponseStatus(HttpStatus.CREATED)
    public ProductService.QuoteView quote(
            @PathVariable String sku,
            @Valid @RequestBody QuoteRequest request
    ) {
        return service.quote(sku, request.quantity())
                .orElseThrow(() ->
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND,
                                "Product not found"));
    }

    public record QuoteRequest(@Min(1) int quantity) {}
}
```

Responsibilities across layers:

- `@GetMapping`/`@PostMapping` define routes.
- `@PathVariable` binds the SKU from the path.
- `@RequestBody` pairs with a JSON converter to deserialize the request into the record.
- `@Valid` triggers validation; `@Min(1)` rejects zero or negative quantities.
- `@ResponseStatus(CREATED)` sets HTTP 201 when a quote is successfully created.
- `ResponseStatusException(NOT_FOUND)` is resolved into HTTP 404 by the MVC exception resolver.
- Response objects are serialized to JSON by the matching converter on the classpath.

The controller receives the **real service** via constructor; the service receives the **real repository**. There are no fakes or mock dependencies in this source.

### 5.6. JUnit Jupiter integration test using MockMvc

**File `src/test/java/com/example/fullmvc/ProductApiIntegrationTest.java`:**

```java
package com.example.fullmvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        classes = FullMvcApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
class ProductApiIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ApplicationContext context;

    @Autowired
    ProductService service;

    @Autowired
    ProductRepository repository;

    @Test
    void loadsControllerServiceAndRepositoryFromFullContext() {
        assertThat(context.getBean(ProductController.class))
                .isNotNull();
        assertThat(context.getBean(ProductService.class))
                .isSameAs(service);
        assertThat(context.getBean(ProductRepository.class))
                .isSameAs(repository);
    }

    @Test
    void getProductReturnsJsonThroughRealComponents()
            throws Exception {
        mvc.perform(get("/api/products/BOOK")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.sku").value("BOOK"))
                .andExpect(jsonPath("$.unitPrice").value(1200));
    }

    @Test
    void unknownProductReturnsNotFound()
            throws Exception {
        mvc.perform(get("/api/products/UNKNOWN"))
                .andExpect(status().isNotFound());
    }

    @Test
    void validQuoteReturnsCreatedAndCalculatedTotal()
            throws Exception {
        mvc.perform(post("/api/products/BOOK/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"quantity\":3}"))
                .andExpect(status().isCreated())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.sku").value("BOOK"))
                .andExpect(jsonPath("$.quantity").value(3))
                .andExpect(jsonPath("$.total").value(3600));
    }

    @Test
    void nonPositiveQuantityFailsBeanValidation()
            throws Exception {
        mvc.perform(post("/api/products/BOOK/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"quantity\":0}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void malformedJsonIsRejectedByMessageConverter()
            throws Exception {
        mvc.perform(post("/api/products/BOOK/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{"))
                .andExpect(status().isBadRequest());
    }
}
```

The suite contains **6 `@Test` methods**, with no separate `@ExtendWith(SpringExtension.class)` needed since `@SpringBootTest` already integrates Spring TestContext with JUnit Jupiter in supported configurations.

**Expectation:** in a clean Spring Boot 3.x project with the dependencies above and no extra security or external backends, all **6 tests pass**. The code does not actively write to stdout. Do not assert a specific log line because Gradle, Maven, and IDEs format reports differently.

### 5.7. Running via Gradle/Maven Wrapper

Linux/macOS:

```bash
# Use if the project runs Gradle:
./gradlew test --tests "com.example.fullmvc.ProductApiIntegrationTest"

# Or if the project runs Maven:
./mvnw -Dtest=ProductApiIntegrationTest test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.fullmvc.ProductApiIntegrationTest"

# Or Maven:
.\mvnw.cmd "-Dtest=ProductApiIntegrationTest" test
```

Run only **one** set of commands matching your project's build tool. For Maven multi-module or Gradle multi-project builds, target the appropriate module and test task/goal. If the application context is cached, a second run may be faster, yet you should still inspect the test report to ensure all six methods were discovered and executed.

## 6. Tracing each layer in the request pipeline from the example

### 6.1. Valid GET product

The call:

```java
mvc.perform(get("/api/products/BOOK"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.unitPrice").value(1200));
```

is an **excerpt** from the complete test.

Execution sequence:

1. MockMvc constructs a mock Servlet request with the GET method and given path.
2. Spring MVC locates the handler for `/api/products/{sku}`.
3. Path variable `BOOK` is bound to parameter `sku`.
4. Controller calls `ProductService.find("BOOK")`.
5. Service calls the real repository and finds price `1200L`.
6. Spring MVC serializes record `ProductView("BOOK", 1200L)` into JSON.
7. `andExpect` verifies status and payload.

If in production you rename the route, omit the service bean, swap converters, or change the response type, this test catches the integration defect — something a unit test calling `controller.get("BOOK")` directly could miss.

### 6.2. Valid POST quote

The request carries header `Content-Type: application/json` and JSON `{"quantity":3}`. The RequestBody converter constructs `QuoteRequest(3)`; Bean Validation accepts the value; the service multiplies `1200 × 3 = 3600`; the response status is 201.

This test proves **multiple layers work together**: POST routing, JSON deserialization, annotation-based validation, service calculation, repository lookup, JSON serialization, and HTTP status.

**Note:** the code uses `@ResponseStatus(CREATED)` specifying “201” for this quote example; a real-world API might use 200 if quoting is a pure calculation creating no resource. Choose status codes per your project's API contract; do not slap 201 on every POST merely because it is a POST.

### 6.3. Invalid request and malformed JSON

Both tests expect 400, yet for **two different reasons**:

- `{"quantity":0}` is valid JSON, deserializes fine, but violates `@Min(1)`. Spring MVC handles the validation error.
- `"{"` is syntactically invalid JSON; the request cannot be deserialized into an object, so the message converter raises a request body error, typically `HttpMessageNotReadableException`.

When debugging 400s, inspect the *resolved exception* and binding/validation errors instead of assuming every 400 comes from `@Valid`. You can capture `MvcResult` to investigate:

```java
var result = mvc.perform(post("/api/products/BOOK/quotes")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"quantity\":0}"))
        .andExpect(status().isBadRequest())
        .andReturn();

assertThat(result.getResolvedException()).isNotNull();
```

This snippet is **only an illustration inside a test that already has `mvc` and required imports**; it does not assume all APIs return error bodies in the same format, as Spring Boot can use different `ErrorAttributes`/`ProblemDetail`/controller advice configurations.

### 6.4. Non-existent GET and 404

For a SKU absent from the map, the repository returns `Optional.empty()`; the service returns empty; the controller throws `ResponseStatusException(HttpStatus.NOT_FOUND, ...)` and the MVC resolver turns it into HTTP 404.

Tests should assert 404 at the **API boundary**, not merely assert the repository returned empty. That way, if the controller accidentally changes to returning 200 with a null body, the test catches the contract regression.

## 7. Enabling/disabling Servlet filters: what does `addFilters` affect?

The default of `@AutoConfigureMockMvc` is `addFilters = true`. `Filter` beans from the context are registered with MockMvc, which matters whenever requests must pass through:

- Spring Security filter chain;
- CORS or correlation/request ID filters;
- Logging, locale, encoding, tenant, or tracing filters;
- Project-defined custom filters.

If you write:

```java
@AutoConfigureMockMvc(addFilters = false)
```

you explicitly ask auto-configuration **not to register filters from the ApplicationContext into MockMvc**. This can be handy to isolate routing issues while debugging, but the test then **no longer proves the behavior of the skipped filters**.

### 7.1. Why can `addFilters=false` produce a “false green” test?

Suppose an endpoint requires authentication and CSRF. An unauthenticated POST request without a CSRF token should be rejected. If filters are removed, the request reaches the controller and returns 201; the test turns green even though the real security flow was bypassed.

**Rule:** if the test aims to verify application behavior under security, **keep filters enabled** and create an authenticated test user/token via Spring Security Test utilities. Only disable filters when test scope is explicitly narrowed and security is verified by dedicated tests elsewhere.

### 7.2. Status codes change when Spring Security is present

When `spring-boot-starter-security` is added without overriding defaults, endpoints may be protected by Spring Security auto-configuration:

- An unauthenticated GET request may receive 401 or redirect/403 depending on the authentication entry point and client headers.
- A POST request missing a CSRF token may receive 403 **before** the controller or Bean Validation runs.
- Consequently, a POST `{"quantity":0}` test might get 403 instead of 400. That is not automatically a validation bug; the filter chain blocked the request upfront.

When testing endpoints requiring an authenticated user, Spring Security Test supports `@WithMockUser` or request post-processors like `user(...)`. When CSRF is enabled, add `with(csrf())` for unsafe methods like POST.

**Snippet for projects that have added `spring-security-test`, not part of the runnable example in section 5:**

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;

// Snippet inside a test that already has MockMvc:
mvc.perform(post("/api/products/BOOK/quotes")
        .with(user("alice").roles("USER"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"quantity\":3}"))
        .andExpect(status().isCreated());
```

This snippet only passes if the app's security policy permits that role to call the endpoint and other configs are valid. Never treat a mock test user as production authentication; tests must also add negative cases (401/403) to enforce access rules.

**Distinction:** `@WithMockUser` and `with(csrf())` satisfy two separate conditions. Having an authenticated user does not bypass CSRF if CSRF protection is enabled.

## 8. Full context yet external dependencies can still be isolated

The test in section 5 has no DB or network. In real applications, loading a full context may cause beans to require:

- DataSource, migrations, Hibernate EntityManager;
- Kafka/RabbitMQ brokers, S3, or REST clients;
- Redis, OpenSearch, email gateways;
- OAuth/OIDC discovery, secrets, or configuration servers;
- Schedulers, runners, or startup listeners.

**Do not blindly disable every bean just so the context barely starts.** Instead, define the test's integration boundary:

1. To verify **controller + service + repository + database**, use an appropriate test database such as Testcontainers with explicit migrations/seeding/cleanup and proper transactions.
2. To verify **controller + real service without sending external API calls**, override external gateway beans with mocks/fakes; the in-scope business layers still run for real.
3. To verify **only controller mapping/serialization/validation**, `@WebMvcTest` with mocked dependencies is usually lighter and clearer.

### 8.1. `@MockitoBean`, `@MockBean`, and versions

In Spring Framework **6.2+** (typically with Spring Boot 3.4+), test bean overriding provides `@MockitoBean`. Projects on Boot 3.3.x and below typically use Spring Boot's `@MockBean`; the older Boot annotation is deprecated in newer releases.

**Snippet illustrating override syntax in a supporting Spring Framework project, not runnable standalone:**

```java
@MockitoBean
RemotePriceGateway remotePriceGateway;
```

If `RemotePriceGateway` is a real application bean, the annotation replaces or creates a mock bean according to framework rules and declaration. You then stub the mock in tests with Mockito to control responses. Ensure you **use the right import for your version** and verify the service receives that overridden bean.

Do not use Mockito's `@Mock` instead of `@MockitoBean` expecting Spring to inject it into controllers/services automatically; standalone `@Mock` only creates a mock inside the test class without replacing the singleton bean inside `ApplicationContext`.

### 8.2. Test profiles and environment-specific configuration

Use `@ActiveProfiles("test")` and `src/test/resources/application-test.properties` when tests need configuration differing from production. You can use `@SpringBootTest(properties = "...")` for a few simple overrides.

Example:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK,
    properties = {
        "app.external-notifications.enabled=false",
        "app.jobs.auto-start=false"
    }
)
@AutoConfigureMockMvc
@ActiveProfiles("test")
class FullContextApiTest {
}
```

This is a snippet and only meaningful if the application actually defines those properties and its beans are designed to honor them. Spring Boot does not inherently understand `app.external-notifications.enabled` or `app.jobs.auto-start`, as those are hypothetical application property names.

### 8.3. Do not automatically equate full-context tests with end-to-end tests

Even when mocking external gateways and using a real test DB, requests still travel through the mock Servlet API. If a bug only triggers in reverse proxy headers, TLS handshakes, HTTP connection reuse, server ports, or the server container, MockMvc cannot fully verify it. Supplement with `RANDOM_PORT` tests or an appropriate deployment environment.

## 9. Transactions, data, and test independence

### 9.1. What does `@Transactional` on a test class do?

When a test method runs inside a transaction opened by Spring TestContext, Spring typically **rolls back that transaction after each test** by default. Under `MOCK`, synchronous servlet request handling usually executes on the **same thread** as the test and can join the test transaction if the transaction manager and propagation match.

However, rollback **does not magically apply to all side effects**:

- A test transaction does not cover HTTP calls to a real server on another thread.
- Transactions/async work spawned onto separate threads have their own transaction contexts.
- Database code using `REQUIRES_NEW` propagation can commit independently.
- Message publishing, file writes, external emails, or caches may not roll back.
- The repository in the example uses `Map.of(...)`, so there is **no database transaction** to roll back.

With `@SpringBootTest(webEnvironment = RANDOM_PORT)`, client and server run on separate threads, so a transaction started on the test method **does not automatically roll back server-side request transactions**. This is a critical difference when migrating tests from MockMvc to real HTTP.

### 9.2. Appropriate fixture strategies

- Immutable data like the map in the example: no cleanup required.
- JPA databases: seed intentionally, clean up/roll back per real architecture; avoid relying on state left by other tests.
- Tests modifying price tables/clocks/caches: reset state in teardown or create scoped fixture beans.
- Tests with schedulers: disable/guard out-of-scope jobs so they do not race against assertions.
- Tests with Testcontainers: use isolated container schemas/fixtures and avoid depending on fixed ports.

**Do not use `@DirtiesContext` as a default hammer to clean databases.** It marks the Spring context non-reusable in cache and incurs startup cost; it does not guarantee external data is reset. Design cleanup for the actual resource.

## 10. Context caching, performance, and test scope

A full context is typically more expensive to start than an MVC slice because it instantiates many beans. Spring TestContext caches contexts by a key derived from configuration, profiles, test properties, bean overrides, and relevant customizers.

When multiple test classes share the same context configuration, they can reuse the context. This speeds up the suite, while reminding you **not to carelessly mutate singleton state**. A shared mutable in-memory service or repository can leave unexpected data for subsequent tests.

Guidelines:

- Avoid introducing unnecessary annotation/property variations across classes testing the same setup.
- Prefer unit/slice tests for cases that do not require a full context.
- Avoid spinning up a Spring context merely to test pure Java calculations.
- Only use `@DirtiesContext` when a test genuinely corrupts context state that cannot be reset.
- For nested/parameterized tests, keep fixtures isolated and know when contexts are reused.
- Do not assume short execution time means tests actually ran; Gradle also has up-to-date/task caching.

## 11. Reading responses and improving assertion quality

### 11.1. Status alone is necessary but insufficient

This example is **too weak**:

```java
mvc.perform(get("/api/products/BOOK"))
        .andExpect(status().isOk());
```

HTTP 200 does not prove the JSON is right. Also verify:

- Content type compatible with `application/json`.
- Key field names and types.
- Business values computed by the service.
- Fields that must not be exposed (if privacy/security is part of the contract).
- 4xx/5xx error rules and error bodies if the API has a defined schema.

The complete snippet in section 5 checks `$.sku` and `$.unitPrice`; the quote case checks SKU, quantity, and total. When APIs have many properties, assert only contract-relevant fields rather than locking tests to unimportant serialization details.

### 11.2. Asserting responses with `jsonPath`

`jsonPath("$.total").value(3600)` checks the value at that JSONPath. This syntax is independent of whether controller beans are mocked or real: it asserts the mock HTTP response. In systems with special JSON types like `BigDecimal`, timestamps/timezones, or enums, write assertions compatible with your serialization contract.

Avoid comparing **raw JSON strings** if property ordering is not part of the contract. Use JSONPath or JSON content comparison to avoid flakiness from field order changes.

### 11.3. Debugging with `andDo(print())`

When a test fails and you need to inspect the request/response, you can use:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;

// Inside a test:
mvc.perform(get("/api/products/BOOK"))
        .andDo(print())
        .andExpect(status().isOk());
```

This is an illustrative snippet, not a complete file. `print()` can write headers/bodies to test logs, so **never log tokens, sensitive cookies, or real personal data** into CI artifacts. With `@AutoConfigureMockMvc`, you can configure `printOnlyOnFailure` depending on version to reduce noise.

### 11.4. Inspecting resolved exceptions

When you want to see where a 400/404/500 originated, use `MvcResult.getResolvedException()`. For exceptions handled by a resolver, that property may hold the corresponding exception; for errors occurring before the resolver or test runner failures, behavior can differ. Do not claim every error is always populated in that field.

## 12. Spring MVC async and filter behavior

If a controller returns `Callable`, `DeferredResult`, `CompletableFuture`, or another MVC-supported async type, MockMvc may require **two phases**: initiating the request and dispatching the async result.

**Illustrative snippet (assuming endpoint `/api/async` actually performs async handling):**

```java
var mvcResult = mvc.perform(get("/api/async"))
        .andExpect(request().asyncStarted())
        .andReturn();

mvc.perform(asyncDispatch(mvcResult))
        .andExpect(status().isOk());
```

Requires static imports `request` and `asyncDispatch` from Spring MVC Test. This is not a standalone runnable example. Do not apply `asyncDispatch` to the synchronous endpoints in section 5.

**Note:** async code running on another thread may not share ThreadLocal security/transaction/request context without explicit propagation. Thus a passing synchronous MockMvc test does not prove async behavior is sound.

## 13. Common errors and troubleshooting

| Symptom | Common Cause | Where to Check |
|---|---|---|
| `No qualifying bean of type MockMvc` | Missing `@AutoConfigureMockMvc` or missing Servlet MVC test config | Check annotations, starter, web environment |
| Context reports `Failed to load ApplicationContext` | Missing bean, DB, migration, remote client, wrong profile/secret | Read the first meaningful root cause |
| 404 on an endpoint clearly present in source | Wrong package scan, route/prefix, method, active profile, or test app class | Check `@SpringBootApplication` root and `RequestMapping` |
| GET returns 401/403 instead of 200 | Spring Security filters are active | Set up test auth matching policy |
| POST returns 403 instead of 201/400 | CSRF or security policy blocks before MVC | Add test user/CSRF matching security requirements |
| POST quantity=0 still returns 201 | Missing Bean Validation provider, missing `@Valid`, annotation on wrong DTO field | Check `spring-boot-starter-validation` and validation config |
| JSON body returns 400 before controller | Malformed JSON, wrong content type, converter cannot deserialize DTO | Check request body, MediaType, record/constructor |
| Response has body but JSON assertion fails | Field name/type/serialization differs from expected | Read actual response, JSONPath, and contract |
| `@Autowired ProductRepository` fails | Bean not scanned or excluded by conditional config | Check packages, annotations, and dependencies |
| Isolated test passes, full suite fails | Shared mutable singleton, DB fixture, or leaked cache/global state | Isolate and reset the proper resource |
| MockMvc finds route yet cannot connect via localhost | MockMvc does not open an HTTP server | Use `RANDOM_PORT` when network requests are needed |
| MockMvc runs but security is skipped | `addFilters=false` or custom MockMvc setup omits filter chain | Keep filters and verify access-control tests |
| IDE compiles while Gradle/Maven fails imports | Spring Boot 3 and 4 use different test packages | Check version/dependencies/imports accordingly |
| Test runs 0 methods | Wrong JUnit Platform/Surefire/filter or skipped/cached task | Read test reports, task options, test counts |
| Test is unusually slow | Full context loads DB/remote config or repeatedly dirties/misses cache | Group tests, optimize fixtures, use slices appropriately |
| MockMvc test passes, real server fails | Container/network/proxy/TLS differs from mock Servlet | Add `RANDOM_PORT`/end-to-end tests |

### 13.1. Layer-by-layer debugging workflow

When a test fails, do not tweak annotations at random. Check sequentially:

1. **Did the test run?** JUnit Jupiter/Surefire/Gradle discovery, test count.
2. **Did the context start?** If not, read the bean/configuration root cause.
3. **Was MockMvc injected?** If missing, check Servlet MVC classpath and `@AutoConfigureMockMvc`.
4. **Did a filter block before the controller?** Especially authentication/CSRF.
5. **Did the route match?** Method, path variable, mapping prefix, content type.
6. **Did body parsing and validation pass?** JSON converter, DTO, `@Valid`.
7. **Did service/repository have the right data?** Fixtures, transactions, business logic.
8. **Are response serialization and status right?** MVC exception handler, JSONPath.
9. **Is there IDE/CLI/CI drift?** JDK, resolved dependencies, active profiles, environment, cache, and test command.

A failure at step 2 (context failure) cannot be fixed by changing `jsonPath` at step 8. A 403 from a security filter does not prove Bean Validation is broken.

## 14. Best practices for real Spring Boot projects

### 14.1. Organizing tests by goal

A sensible structure may include:

- **Unit tests:** business rules/calculations, no Spring context.
- **MVC slice tests:** controller advice, mappings, JSON/validation, mocked services if appropriate.
- **Full-context MockMvc tests:** a few key business flows through controller → service → repository, filters, and transactions.
- **HTTP integration tests:** flows requiring a real embedded server/socket or real client.
- **End-to-end tests:** deployment environment traits that earlier test levels cannot prove.

Do not force every scenario into full-context tests; nor eliminate integration tests just because unit tests are fast.

### 14.2. Clean configuration, independent of personal machines

- Use Gradle/Maven Wrapper and a shared JDK/toolchain with CI.
- Prefer `@ActiveProfiles("test")`/test resources for environments.
- Never access production DBs, queues, or email in tests.
- Never print secrets in `print()` or failure logs.
- Seed/clean up fixtures per test or within verified transactions.
- Never alter the HTTP contract just to make a test pass on one machine.
- Document the framework major version and test starters in the project README.

### 14.3. What to verify before opening a pull request?

After running an individual test, run the full test suite recognized by your build/CI, such as `./gradlew test` or `./mvnw test` per the repo. Read reports to confirm test counts, skipped tests, and where any failures occurred. With Gradle, `UP-TO-DATE` or `FROM-CACHE` does not prove tests just re-ran; use `--rerun-tasks` when forcing fresh execution verification.

If a module defines a dedicated integration test task, run that exact task/goal. A `@SpringBootTest` can still be configured separately from the `test` task; the annotation **does not by itself decide** which build task executes the class.

## 15. Practice exercises

### Exercise A: Choosing the right test scope

A controller only needs verification of mappings and JSON fields from a mocked service. Full-context MockMvc or `@WebMvcTest`?

**Hint:** `@WebMvcTest` is usually more appropriate. It tests MVC behavior without loading external infrastructure. If a suspected bug involves miswiring real service/repository beans in the full application, adding one full-context MockMvc test is valuable.

### Exercise B: Reading HTTP 403

A POST quote test sends valid JSON yet returns 403 after adding Spring Security. What needs fixing?

**Answer:** inspect the security filter chain and CSRF policy. If the endpoint requires an authenticated user, configure Spring Security Test with appropriate user/roles and CSRF token. **Do not set `addFilters=false` to let requests bypass security and conclude the API is verified.**

### Exercise C: Is validation running?

A test sending `POST ... {"quantity":0}` returns HTTP 201. Name at least three things to check?

**Answer:** does the DTO have `@Min(1)`; does the method have `@Valid @RequestBody`; does the test runtime include a Jakarta Bean Validation provider (such as `spring-boot-starter-validation`). Then verify the right endpoint/method receives the request and no custom handler bypasses validation.

### Exercise D: Full context yet still no HTTP port

Why does `@Autowired MockMvc` work while `http://localhost:8080/api/products/BOOK` fails to connect?

**Answer:** `@SpringBootTest(webEnvironment=MOCK)` does not start an HTTP server. `MockMvc.perform(get(...))` runs in-JVM on mock requests/responses; to genuinely send HTTP over a socket, use `RANDOM_PORT` and an appropriate client.

### Exercise E: Cross-layer verification

In the example, if the repository lacks `BOOK` or the service miscalculates the total, which tests can catch it?

**Answer:** the successful GET verifies repository data and JSON; the POST quote verifies service calculation and response contract. To pinpoint errors even more accurately, add unit tests for `ProductService.quote(...)` while keeping a few full-context tests for wiring and the request pipeline.

### Pre-signoff checklist

- [ ] `@AutoConfigureMockMvc` version and starter/imports match your Spring Boot version.
- [ ] `@SpringBootTest(webEnvironment=MOCK)` actually creates a Servlet MVC context.
- [ ] `MockMvc` is injected from the context, not accidentally replaced by standalone setup.
- [ ] Controllers, services, and repositories in test scope are real beans or explicitly documented overrides.
- [ ] GET/POST requests verify both status codes and payload/business fields.
- [ ] Negative tests exist: not found, invalid body/validation, and error handlers per API contract.
- [ ] Filters/Spring Security/CSRF are not bypassed if part of the contract.
- [ ] Test data is independent; rollback/cleanup accounts for threads and side effects.
- [ ] No real out-of-scope external services are called; no production connections.
- [ ] In-process MockMvc is not mistaken for real HTTP server integration.
- [ ] Context caching is used sensibly without overusing `@DirtiesContext`.
- [ ] JUnit/Gradle/Maven/CI executes the right suite and records reports.
- [ ] Fixtures and assertions do not depend on test execution order.
- [ ] Logs/debug output do not leak tokens, cookies, or sensitive data.

## 16. Conclusion

**`@SpringBootTest + @AutoConfigureMockMvc` is the choice for Spring MVC integration testing with a full application context, while still using mock Servlet requests/responses without opening an HTTP server.** It fits when you need to verify a request traveling through the MVC pipeline to real services/repositories under full test-context control inside the same JVM. `@WebMvcTest` is smaller and typically faster; `RANDOM_PORT` tests more real HTTP properties.

Understanding this boundary cleanly helps you pick tests that are strong enough, write meaningful assertions, avoid bypassing security filters, keep data independent, and minimize drift between developer machines and CI.

## Official references

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `MOCK`, `@AutoConfigureMockMvc`, and MVC testing.
- [Spring Boot 3.5 — @AutoConfigureMockMvc Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/AutoConfigureMockMvc.html): package, `addFilters`, `print`, and options.
- [Spring Boot 4.0 — @AutoConfigureMockMvc Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/webmvc/test/autoconfigure/AutoConfigureMockMvc.html): new package/module in Boot 4.
- [Spring Boot 4 — Build Systems & Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html): `spring-boot-starter-webmvc` and `spring-boot-starter-webmvc-test`.
- [Spring Framework — MockMvc Overview](https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html): DispatcherServlet mechanics with mock Servlet API, no real server.
- [Spring Framework — Configuring MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/setup.html): `standaloneSetup` vs. `webAppContextSetup`.
- [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): filter chain integration and security testing.
- [Spring Security — Testing CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): using `with(csrf())` for HTTP methods requiring CSRF.
