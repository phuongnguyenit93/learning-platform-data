# Distinguishing Portless Handler Testing from Real-Server HTTP Testing in Spring Boot

## 1. The Essence of the Question “Has the API Been Tested?”

When a developer says “the `POST /api/quotes` endpoint has tests,” you need to ask **which layers the request actually passed through**. There are at least four distinct levels:

1. **Unit/direct call:** calling a service or controller Java method directly. No HTTP request, no servlet, no socket.
2. **Spring MVC mock request:** using `MockMvc` to go through `DispatcherServlet` and simulated request/response objects, verifying that MVC mappings, binding, validation, converters, advice, and filters are wired together, **without starting an HTTP server**.
3. **Full application context but still mock HTTP:** `@SpringBootTest` defaults to `webEnvironment=MOCK`; real app beans are created, yet `MockMvc` still does not open a port.
4. **Live HTTP integration:** `@SpringBootTest(webEnvironment=RANDOM_PORT)` starts embedded Tomcat (or the appropriate server), and `TestRestTemplate`/`WebTestClient` sends HTTP over TCP to a random port.

There is also the **deployed E2E** level, which calls the system behind a proxy, ingress, TLS, identity provider, and dependencies in a real environment. A live HTTP test inside a local JVM **does not** automatically test all of this infrastructure.

This lesson belongs to the **Web runtime testing** group. The complete Java example uses **Spring Boot 3.5.16, Java 17+, Spring MVC, Maven, JUnit Jupiter, Mockito, MockMvc, TestRestTemplate**, and a separate Servlet. The goal is to put the same contract through multiple test levels to understand clearly what each level catches and misses.

**Short rule:** Unit tests answer “is the logic right?”; MockMvc answers “does Spring MVC handle the request properly?”; real HTTP answers “does the embedded server receive and route real HTTP properly?”; staging/E2E answers “is the path through the deployment infrastructure right?”.

## 2. Comparison by Technology and Processing Layer

| Test Type | Has ApplicationContext? | Has Real `DispatcherServlet`? | Has Real HTTP Server? | Has Network Socket? |
| --- | --- | --- | --- | --- |
| JUnit calling `new PriceService()` | No | No | No | No |
| JUnit calling `new QuoteController(service)` | No | No | No | No |
| `MockMvcBuilders.standaloneSetup` | Not required | MVC infrastructure set up for test | No | No |
| `@WebMvcTest` + `MockMvc` | Yes, MVC slice | Yes | No | No |
| `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` | Yes, full app | Yes | No | No |
| `@SpringBootTest(RANDOM_PORT)` + HTTP client | Yes, full app | Yes, inside MVC | Yes | Yes |
| `@SpringBootTest(DEFINED_PORT)` + HTTP client | Yes, full app | Yes, inside MVC | Yes | Yes |
| HTTP smoke through deployed ingress | Deployed app | Depends on runtime | Yes | Yes, through proxy/LB |

`MockMvc` **does not simply call the controller directly**. It creates a `MockHttpServletRequest`, passes it into Spring MVC `DispatcherServlet`, and executes most MVC processing. However, it does **not** require Tomcat to start, bind a port, accept TCP, select a Servlet by URL pattern, or negotiate TLS.

### 2.1. The Four `webEnvironment` Modes of Spring Boot 3.5

| Mode | What Starts? |
| --- | --- |
| `MOCK` (default) | Web ApplicationContext with a Servlet mock environment, **does not start an embedded web server** |
| `RANDOM_PORT` | Embedded HTTP server on a **random port** assigned by the OS |
| `DEFINED_PORT` | Embedded HTTP server on `server.port`, typically 8080 by default |
| `NONE` | ApplicationContext without a web environment |

`@SpringBootTest` **without `webEnvironment`** means `MOCK` when web dependencies are present. Do not use `@LocalServerPort` with `MOCK` and believe the application has opened a port.

### 2.2. Differences Commonly Misunderstood

| Question | Answer |
| --- | --- |
| “Is using `@SpringBootTest` an E2E HTTP test?” | **No**, by default there is no server |
| “Does `MockMvc` only test a Java method?” | **No**, it runs the MVC pipeline |
| “Does using `WebTestClient` guarantee real HTTP calls?” | **No**, it has bind-to-context/controller without opening a socket |
| “Does a full context test always check Servlet URL registration?” | **No**, when the mock environment has no container dispatch |
| “Does RANDOM_PORT mean testing TLS and ingress?” | **No**, it must actually pass through configured TLS/proxy |
| “Does a unit/direct test check Spring MVC `@Valid`?” | **Not automatically**, validation requires framework invocation |
| “If TestRestTemplate sees HTTP 500 without throwing, does the test pass?” | **No**, you need to assert status/body |

## 3. Direct Handler Call: Simple but Not an HTTP Contract Test

Suppose a price calculation method:

```java
QuoteResponse quote(String sku, int quantity) {
    long price = switch (sku) {
        case "pen" -> 12_000L;
        case "book" -> 35_000L;
        default -> throw new ProductNotFoundException(sku);
    };
    return new QuoteResponse(
            sku, quantity, price, price * quantity);
}
```

This is a **snippet**; the project code in section 9 uses `Math.multiplyExact` and validates inputs.

A typical unit test:

```java
PriceService service = new PriceService();
assertEquals(
        new QuoteResponse("pen", 2, 12000, 24000),
        service.quote("pen", 2));
```

In this snippet there is no HTTP request. It does not check:

- Whether `@PostMapping("/quotes")` has been registered by Spring.
- Whether the JSON body deserializes into `QuoteRequest`.
- Whether `@Valid`, `@Min`, `@Max` are triggered by MVC.
- Whether `@RestControllerAdvice` converts the exception to HTTP 404.
- Header/Accept/Content-Type, URL variables, path matching.
- Servlet filters, servlet mappings, Tomcat, TCP/HTTP.

**Why still use unit tests?** They are fast, deterministic, require no context/DB, and are well-suited for testing dozens or hundreds of edge cases, invariants, and branch logic. Do not turn every pricing rule into a test that starts the server.

### 3.1. Calling the Controller Directly Is Still Not a Spring MVC Test

`new QuoteController(service).createQuote(new QuoteRequest("pen",0))` calls a Java method like any other method. `@Valid` placed on a parameter **does not run automatically** on a plain Java call. If the service checks quantity itself, it may still throw an exception, but that is not MVC's `MethodArgumentNotValidException`.

Unit tests and MVC validation tests are **two complementary layers**; do not treat the result of one layer as a proxy for the other.

## 4. MockMvc: Real Spring MVC Processing with Fake Servlet Objects

### 4.1. Request Path of MockMvc

```text
JUnit test
     |
     v
MockMvc.perform(post("/api/quotes"))
     |
     v
MockHttpServletRequest / MockHttpServletResponse
     |
     v
Configured servlet filters (if added)
     |
     v
DispatcherServlet
     |
     +--> HandlerMapping / HandlerAdapter
     +--> JSON converter + data binding
     +--> Bean Validation
     +--> @RestController / @Controller
     +--> @ControllerAdvice / @ExceptionHandler
     |
     v
MvcResult / JSON / status / headers
     |
     x    No socket/Tomcat listening port
```

The following behaviors can be tested with MockMvc:

- HTTP method and request mapping: GET/POST/PUT/DELETE, path/query variables.
- Request `Content-Type`, response `produces`, `Accept`, 404/405/406/415.
- JSON mapping and charset; URL-encoded form, mock multipart, validation.
- `HandlerInterceptor`, filters, and Spring Security **when configured in the mock test**.
- MVC exception handlers, body serialization, response headers.
- Simulated request-scoped state/session at the MVC level.

Behaviors that MockMvc **is insufficient to prove**:

- Embedded Tomcat/Jetty/Undertow starting/binding to the right network interface/port.
- The Servlet container selecting a custom `HttpServlet`, Jersey servlet, or multiple dispatchers by the right URL mapping.
- Actual TCP connection, OS sockets, HTTP protocol parsing, TLS/HTTP2 handshake.
- Reverse proxy/Ingress/CDN, real browser cookie rules, and network policies.
- Startup lifecycle/management listener on a separate port.
- Latency/throughput over real transport or production environment.

### 4.2. `standaloneSetup` and `webAppContextSetup`

Spring Framework supports two ways to build MockMvc:

```java
// Snippet A: controller created manually, no Spring Context needed.
MockMvc mvc = MockMvcBuilders
        .standaloneSetup(new QuoteController(new PriceService()))
        .setControllerAdvice(new ApiErrorHandler())
        .build();
```

With `standaloneSetup`, you must configure whatever is relevant yourself: MVC advice, converters, formatters, validator, filters, custom argument resolvers. It is suitable for focused MVC handler testing, **not representative of the entire application**.

```java
// Snippet B: uses MVC configuration inside WebApplicationContext.
MockMvc mvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .build();
```

Approach B uses the loaded `WebApplicationContext`, which is closer to the real MVC configuration. Boot's `@WebMvcTest` and `@AutoConfigureMockMvc` auto-configure MockMvc, which is usually simpler than writing a builder manually.

### 4.3. MockMvc Is Not a Browser

You can send `Origin` and test response CORS headers with MockMvc; however, there is no browser JavaScript runtime enforcing CORS/cookie policies. To verify a real cross-origin frontend, you need browser E2E or sufficiently authentic browser tests.

## 5. Web Slice: `@WebMvcTest` with Mock Collaborators

In Spring Boot 3.5:

```java
@WebMvcTest(QuoteController.class)
class QuoteControllerSliceTest {
    @Autowired MockMvc mvc;
    @MockitoBean PriceService service;
}
```

This is a **structural snippet**, without methods/imports yet. `@WebMvcTest` loads the beans needed to test Spring MVC, including `@Controller`, `@ControllerAdvice`, `@JsonComponent`, `Filter`, `HandlerInterceptor`, and corresponding MVC converters/configurers. It **does not automatically scan all `@Service`, `@Repository`, regular `@Component`, or `@ConfigurationProperties`** like a full application context.

`@MockitoBean` from **Spring Framework 6.2** has the package:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

This annotation creates/replaces a collaborator bean with a Mockito mock in the test context. There is no need to register the real service if the goal is solely to verify the MVC contract.

### 5.1. Questions Appropriate for a Slice

- Is the controller invoked properly with the JSON request?
- Does the JSON response have the right field names/structure?
- Does input `quantity=0` get rejected with 400 by Bean Validation?
- Is an unknown SKU returned as 404 with a stable code by `@RestControllerAdvice`?
- Are `Content-Type` and `Accept` handled properly?
- Are filters/headers, CORS, and handler advice configured appropriately for the MVC test?

A mock service can return test-controlled data. If the production service is missing a bean or has a broken JDBC config, the slice can still pass — that is its **isolation scope**, not a bug.

### 5.2. When Not to Extrapolate from a Slice

`@WebMvcTest` does not fully prove database migrations, external dependencies, Spring Bean wiring of production services, network listeners, custom Servlet dispatch, TLS/Ingress, or concurrency.

If a custom converter bean or configuration is not in the slice, use `@Import`/`@EnableConfigurationProperties` intentionally; do not import the entire application config indiscriminately, as that defeats the purpose of a slice.

## 6. Full Context MockMvc: Full Wiring but Still No Open Port

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class FullContextMockMvcTest {
    @Autowired MockMvc mvc;
}
```

This is a **snippet**. Spring Boot creates a real application context with component scanning and auto-configurations; service/repository beans can be real, while HTTP requests are still simulated by MockMvc.

| Aspect | `@WebMvcTest` | `@SpringBootTest(MOCK)` + MockMvc |
| --- | --- | --- |
| Spring context | A web slice | Near/full app context |
| Collaborators | Usually `@MockitoBean` | Usually real beans |
| Service dependency injection | Incomplete | Can be verified |
| JSON, MVC validation, advice | Yes | Yes |
| Embedded server port | No | No |
| Custom servlet URL registration via container | No | No |
| DB/repositories | Usually not loaded | Can use real/fake per profiles |
| Startup cost | Usually lower | Usually higher |

A full-context mock test is appropriate when you want to detect dependency injection errors, configuration/bean wiring issues, and interactions with internal app entities without opening a socket. **Full context may still access a database or downstream service** if the test uses real beans; having no network listener does not mean all I/O is mocked.

### 6.1. Transactional Tests

If a test-side transaction is created by `@Transactional` and the request is handled in the same thread/transaction context, DB changes via MockMvc can roll back after the test. However, async/multi-thread/other transaction propagation modes can break this assumption. Live HTTP tests have a clear difference discussed in section 15.

## 7. Live HTTP: `@SpringBootTest(RANDOM_PORT)` and a Real HTTP Client

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpServerTest {
    @LocalServerPort int port;
    @Autowired TestRestTemplate http;
}
```

With Spring Boot 3.5, `RANDOM_PORT` starts a real embedded web server, typically Tomcat for `spring-boot-starter-web`. `@LocalServerPort` is imported from `org.springframework.boot.test.web.server.LocalServerPort`; the port value is only valid after the context/server has started.

### 7.1. Why a Random Port?

- Reduces port collisions when CI/tests run in parallel, without requiring 8080 to always be free.
- The OS allocates a real port; the test uses the injected port number without hardcoding.
- Allows multiple test contexts to run independently in many cases.
- Enables testing the real server bind/start lifecycle.

`DEFINED_PORT` uses a configured port, which may suit some environments but risks conflicts easily. Do not choose it by default when a random port suffices.

### 7.2. TestRestTemplate

`TestRestTemplate` is Boot's convenient test HTTP client. It generally lets you inspect the `ResponseEntity` for 4xx/5xx without throwing solely because of HTTP status, so you must **assert status and body**. In this project, `spring-boot-starter-test` provides the needed dependency.

### 7.3. What Coverage Does Live HTTP Add?

- Tomcat genuinely selects the Servlet by URL patterns and dispatches.
- Real HTTP request/response bytes traverse TCP loopback.
- Registered container filters, headers, status, redirects, session handling.
- Context path/servlet path integration and custom servlet registration.
- Codec/converter behavior over HTTP transport.
- Management port when configured separately and tested against the real port.
- Compression/HTTP2/TLS if the app and test client **actually enable and require them**.

It **does not** prove proxy/Ingress, real TLS, cloud DNS, OAuth provider, or load balancing when the test only calls localhost HTTP. This is **live server integration**, not automatically production E2E.

## 8. Matrix for Selecting Test Level by Defect to Detect

| Risk to Verify | Unit/direct | MockMvc | Live HTTP |
| --- | :---: | :---: | :---: |
| Business total/quantity/exception | Yes | Possible | Possible |
| Spring `@GetMapping`/`@PostMapping` | No | **Yes** | **Yes** |
| JSON deserialization/serialization | No | Yes | Yes |
| Spring MVC `@Valid` | Does not auto-run | Yes | Yes |
| `@RestControllerAdvice` | Does not auto-run | Yes | Yes |
| MVC HandlerInterceptor | No | Yes if configured | Yes |
| Servlet filter logic | No | Yes if included in chain | Yes |
| Full production bean graph | No | Full-context MockMvc only | Yes |
| Custom Servlet/Jersey routing by container | No | **No** | Yes |
| Real embedded Tomcat binding port | No | No | **Yes** |
| TCP/HTTP transport | No | No | **Yes** |
| Browser CORS enforcement | No | No | Needs browser E2E |
| TLS/certificate | No | No | Only if test enables TLS |
| External Ingress/proxy rewrite | No | No | Only when request goes through proxy |
| DB transaction rollback between test/server | N/A | Depends on test | **Test-side rollback does not apply to server thread** |
| Concurrent load/p95 under stress | No | No | Needs dedicated workload performance test |

A “Yes” only means the tool **is capable of** proving it when appropriate assertions are written—not that adding an annotation automatically checks every case.

## 9. Runnable Java 17+ Project: Both MVC and a Separate Servlet

The project includes:

- `GET /api/ping` returning JSON.
- `POST /api/quotes` accepting JSON with `@Valid`, returning a quote.
- `PriceService` business logic and `ProductNotFoundException`.
- `ApiErrorHandler` translating errors to 400/404.
- `DemoHeaderFilter` adding the `X-Demo-Filter: on` header.
- `RawServletConfiguration` creating an `HttpServlet` at `/wire/*`, **outside Spring MVC**.

Four corresponding test classes: unit, MVC slice, full context mock, and live HTTP. No database, Docker, Redis, or partner API is required to run it.

### 9.1. Project Directory

```text
web-test-levels/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/webtests/
    │   │   ├── WebTestsApplication.java
    │   │   ├── PriceService.java
    │   │   ├── QuoteController.java
    │   │   ├── ApiErrorHandler.java
    │   │   ├── DemoHeaderFilter.java
    │   │   └── RawServletConfiguration.java
    │   └── resources/application.properties
    └── test/java/com/example/webtests/
        ├── PriceServiceTest.java
        ├── QuoteControllerSliceTest.java
        ├── FullContextMockMvcTest.java
        └── RealHttpServerTest.java
```

Package-private DTOs/exceptions/Servlets in the same Java file as a public class are valid. All belong to package `com.example.webtests`; the Spring Boot main class is at the same package root for component scanning.

### 9.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>web-test-levels</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
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

The parent manages versions of Spring Framework, Tomcat, Jackson, Hibernate Validator, Mockito, and JUnit. Do not pin individual transitive dependencies.

### 9.3. `WebTestsApplication.java`

```java
package com.example.webtests;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebTestsApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebTestsApplication.class, args);
    }
}
```

### 9.4. `PriceService.java`

```java
package com.example.webtests;

import org.springframework.stereotype.Service;

@Service
public class PriceService {

    public QuoteResponse quote(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (quantity < 1 || quantity > 100) {
            throw new IllegalArgumentException(
                    "quantity must be from 1 to 100");
        }

        long unitPrice = switch (sku) {
            case "pen" -> 12_000L;
            case "book" -> 35_000L;
            default -> throw new ProductNotFoundException(sku);
        };

        long total = Math.multiplyExact(
                unitPrice, (long) quantity);

        return new QuoteResponse(
                sku, quantity, unitPrice, total);
    }
}

class ProductNotFoundException extends RuntimeException {
    ProductNotFoundException(String sku) {
        super("Unknown SKU: " + sku);
    }
}
```

The service guards quantity/sku itself and has no HTTP dependency. `Math.multiplyExact` helps prevent silent overflow.

### 9.5. `QuoteController.java`

```java
package com.example.webtests;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record QuoteRequest(
        @NotBlank String sku,
        @Min(1) @Max(100) int quantity) {
}

record QuoteResponse(
        String sku, int quantity,
        long unitPriceVnd, long totalVnd) {
}

@RestController
@RequestMapping("/api")
public class QuoteController {

    private final PriceService priceService;

    public QuoteController(PriceService priceService) {
        this.priceService = priceService;
    }

    @GetMapping(value = "/ping",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> ping() {
        return Map.of("message", "pong");
    }

    @PostMapping(value = "/quotes",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public QuoteResponse createQuote(
            @Valid @RequestBody QuoteRequest request) {
        return priceService.quote(
                request.sku(), request.quantity());
    }
}
```

`@Valid` on the body causes MVC Bean Validation to check quantity/sku. When **calling the Java method directly**, the annotation does not automatically run, even though the service still has its own checks.

### 9.6. `ApiErrorHandler.java`

```java
package com.example.webtests;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> invalid(
            MethodArgumentNotValidException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(
                Map.of("code", "INVALID_REQUEST",
                       "message", "Invalid request data."));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, String>> badJson(
            HttpMessageNotReadableException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(
                Map.of("code", "INVALID_JSON",
                       "message", "JSON cannot be read."));
    }

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<Map<String, String>> unknown(
            ProductNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(
                Map.of("code", "SKU_NOT_FOUND",
                       "message", "Product not found."));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> illegal(
            IllegalArgumentException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(
                Map.of("code", "INVALID_REQUEST",
                       "message", "Invalid parameter."));
    }
}
```

The advice maps Java errors to public HTTP errors with stable codes; it does not expose raw stack traces.

### 9.7. `DemoHeaderFilter.java`

```java
package com.example.webtests;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class DemoHeaderFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws IOException, ServletException {
        response.setHeader("X-Demo-Filter", "on");
        filterChain.doFilter(request, response);
    }
}
```

In a live Servlet environment, the Filter bean is registered by Boot. MockMvc with auto-configured filters can also execute the filter logic. However, a filter working in MVC mock **is not enough** to prove Tomcat attached it to a custom Servlet path on a real server.

### 9.8. `RawServletConfiguration.java`

```java
package com.example.webtests;

import java.io.IOException;

import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RawServletConfiguration {

    @Bean
    ServletRegistrationBean<RawPingServlet> rawPingServlet() {
        ServletRegistrationBean<RawPingServlet> registration =
                new ServletRegistrationBean<>(
                        new RawPingServlet(), "/wire/*");
        registration.setName("rawPingServlet");
        return registration;
    }
}

class RawPingServlet extends HttpServlet {

    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws IOException {

        if (!"/ping".equals(request.getPathInfo())) {
            response.sendError(HttpServletResponse.SC_NOT_FOUND);
            return;
        }

        response.setCharacterEncoding("UTF-8");
        response.setContentType("text/plain");
        response.getWriter().write("raw-servlet-ok\n");
    }
}
```

**This is the empirical proof point:** `/wire/ping` belongs to a custom Servlet, **not** a Spring MVC `@GetMapping`. With live HTTP, embedded Tomcat matches `/wire/*` and invokes `RawPingServlet`. `MockMvc` attached to DispatcherServlet does not perform container-level Servlet selection, so it is insufficient to test this route.

### 9.9. `application.properties`

```properties
spring.application.name=web-test-levels
server.port=8080
```

No custom context path, SSL, DB, or Security is used in the demo to keep the scope focused. Test `RANDOM_PORT` will override the main port, avoiding contention with a running process on 8080.

## 10. Full Unit Test: No Spring, No Network

File `src/test/java/com/example/webtests/PriceServiceTest.java`:

```java
package com.example.webtests;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceServiceTest {

    private final PriceService service = new PriceService();

    @Test
    void computesTotalWithoutSpring() {
        assertEquals(
                new QuoteResponse("pen", 2, 12000, 24000),
                service.quote("pen", 2));
    }

    @Test
    void rejectsInvalidQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> service.quote("pen", 0));
    }

    @Test
    void rejectsUnknownSku() {
        assertThrows(ProductNotFoundException.class,
                () -> service.quote("missing", 1));
    }
}
```

The three tests do not create an ApplicationContext, do not open a port, and do not run DispatcherServlet. The results only prove the **business service**.

## 11. MVC Slice Test: `@WebMvcTest` + `MockMvc`

File `src/test/java/com/example/webtests/QuoteControllerSliceTest.java`:

```java
package com.example.webtests;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(QuoteController.class)
class QuoteControllerSliceTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    PriceService service;

    @Test
    void dispatchesJsonToController() throws Exception {
        given(service.quote("pen", 2))
                .willReturn(
                        new QuoteResponse("pen", 2, 12000, 24000));

        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"pen","quantity":2}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku").value("pen"))
                .andExpect(jsonPath("$.totalVnd").value(24000))
                .andExpect(header().string(
                        "X-Demo-Filter", "on"));

        verify(service).quote("pen", 2);
    }

    @Test
    void beanValidationRejectsBadQuantity() throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"pen","quantity":0}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_REQUEST"));
    }

    @Test
    void pingHasExpectedMapping() throws Exception {
        mvc.perform(get("/api/ping")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message")
                        .value("pong"));
    }

    @Test
    void wrongMethodReturns405() throws Exception {
        mvc.perform(post("/api/ping"))
                .andExpect(status().isMethodNotAllowed());
    }
}
```

`@MockitoBean` mocks `PriceService` so the JSON/MVC contract test does not depend on real quote logic. `@WebMvcTest` in Boot 3.5 auto-configures MockMvc. `DemoHeaderFilter` is a `@Component` implementing Filter and belongs to the types an MVC slice can scan; with the default test configuration including filters, the header assertion proves the mock filter chain ran.

**Do not infer from this test that Tomcat registered a real filter/Servlet**. If using `@AutoConfigureMockMvc(addFilters=false)` or `MockMvcBuilders.standaloneSetup` without adding filters, filter behavior will differ.

When `@WebMvcTest` fails because the `PriceService` bean is missing and there is no `@MockitoBean`, that is usually because the slice does not load regular `@Service` beans, not a production startup failure.

## 12. Full Context but HTTP Still Mocked

File `src/test/java/com/example/webtests/FullContextMockMvcTest.java`:

```java
package com.example.webtests;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class FullContextMockMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void checksMvcWithRealServiceButNoPort() throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"book","quantity":2}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.unitPriceVnd")
                        .value(35000))
                .andExpect(jsonPath("$.totalVnd")
                        .value(70000));
    }
}
```

Unlike the MVC slice: the real `PriceService` is created and called by the controller. However, there is no Tomcat listening port. `@AutoConfigureMockMvc` only builds a mock request pathway. If this test passes, there is additional evidence that dependency injection and business logic inside the full Spring context are correct; it **does not yet** tell whether the real `RawPingServlet` is routed by Tomcat.

## 13. Live Server Test with Real Port

File `src/test/java/com/example/webtests/RealHttpServerTest.java`:

```java
package com.example.webtests;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpServerTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate http;

    private String url(String path) {
        return "http://127.0.0.1:" + port + path;
    }

    @Test
    void serverIsReallyListening() {
        assertTrue(port > 0);

        ResponseEntity<Map> response = http.getForEntity(
                url("/api/ping"), Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("pong",
                response.getBody().get("message"));
    }

    @Test
    void quoteWorksOverHttp() {
        ResponseEntity<QuoteResponse> response =
                http.postForEntity(
                        url("/api/quotes"),
                        new QuoteRequest("pen", 3),
                        QuoteResponse.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(
                new QuoteResponse("pen", 3, 12000, 36000),
                response.getBody());
        assertEquals("on",
                response.getHeaders().getFirst("X-Demo-Filter"));
    }

    @Test
    void invalidInputReturns400() {
        ResponseEntity<Map> response =
                http.postForEntity(
                        url("/api/quotes"),
                        new QuoteRequest("pen", 0),
                        Map.class);

        assertEquals(HttpStatus.BAD_REQUEST,
                response.getStatusCode());
        assertEquals("INVALID_REQUEST",
                response.getBody().get("code"));
    }

    @Test
    void unknownSkuReturns404() {
        ResponseEntity<Map> response =
                http.postForEntity(
                        url("/api/quotes"),
                        new QuoteRequest("missing", 1),
                        Map.class);

        assertEquals(HttpStatus.NOT_FOUND,
                response.getStatusCode());
        assertEquals("SKU_NOT_FOUND",
                response.getBody().get("code"));
    }

    @Test
    void tomcatDispatchesNonMvcServlet() {
        ResponseEntity<String> response =
                http.getForEntity(
                        url("/wire/ping"), String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("raw-servlet-ok\n", response.getBody());
        assertEquals("on",
                response.getHeaders().getFirst("X-Demo-Filter"));
    }

    @Test
    void unknownServletPathIs404() {
        ResponseEntity<String> response =
                http.getForEntity(
                        url("/wire/missing"), String.class);

        assertEquals(HttpStatus.NOT_FOUND,
                response.getStatusCode());
        assertNotEquals("raw-servlet-ok\n", response.getBody());
    }
}
```

This is real HTTP through embedded Tomcat:

- `port > 0` proves a random port was assigned.
- The client sends HTTP to loopback; the JSON/body/headers response goes over real transport.
- The `/wire/ping` route is handled by the Servlet container's **RawPingServlet**, not by an MVC controller.
- The filter header on both MVC and non-MVC endpoints shows that the registered Servlet filter takes effect on live HTTP requests.
- HTTP 400/404 is verified at the public boundary, not merely by invoking a Java exception.

**Limitations:** the local server does not inherently include a reverse proxy, TLS, browser CORS enforcement, or external service integration. This test is also not a p95/throughput benchmark.

## 14. Running Maven and Checking with curl

### 14.1. Running All JUnit Tests

Requires Java 17+, Maven, and all source files:

```bash
java -version
mvn -version
mvn clean test
```

The `RANDOM_PORT` tests do not require port 8080 to be free. Maven/Surefire will display test counts and results according to the plugin version; there is no fixed stdout line guaranteed across every environment. If a test fails, inspect the stack trace at the affected layer.

### 14.2. Running the Real Project

```bash
mvn clean package
java -jar target/web-test-levels-1.0.0.jar
```

In another terminal:

```bash
curl -i http://127.0.0.1:8080/api/ping

curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: application/json" \
  -d '{"sku":"pen","quantity":3}'

curl -i http://127.0.0.1:8080/wire/ping
```

Expected:

- `GET /api/ping`: **HTTP 200**, JSON `{"message":"pong"}`.
- `POST /api/quotes`: **HTTP 200**, JSON with these exact values:

```json
{"sku":"pen","quantity":3,"unitPriceVnd":12000,"totalVnd":36000}
```

- `GET /wire/ping`: **HTTP 200**, `Content-Type: text/plain`, body with a trailing newline:

```text
raw-servlet-ok
```

- Both routes subject to the filter have the header `X-Demo-Filter: on`.

### 14.3. Negative Cases

```bash
curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: application/json" \
  -d '{"sku":"pen","quantity":0}'

curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: application/json" \
  -d '{"sku":"missing","quantity":1}'

curl -i http://127.0.0.1:8080/wire/missing

curl -i -X POST http://127.0.0.1:8080/api/ping
```

Expected respectively: **400 `INVALID_REQUEST`**, **404 `SKU_NOT_FOUND`**, **404 from RawPingServlet**, and **405 Method Not Allowed from MVC**. If Security/CSRF is added, a POST request may be blocked before the controller with 401/403; that needs testing according to its own security contract.

## 15. Transaction Rollback: A Difference That Often Breaks Tests

When using a database and `@Transactional` on a test method, Spring TestContext usually rolls back the **test thread's** transaction after the method. However, in `RANDOM_PORT`, the test's HTTP client and the server-side request handler run in **different threads**, creating **different transactions**.

### 15.1. Anti-Pattern

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class OrderHttpIntegrationTest {
    // Sends POST /orders over HTTP and assumes the INSERT done by the server
    // will be rolled back because of @Transactional on the test method.
}
```

This is a **warning snippet**, not a complete test. The JUnit thread's transaction does not wrap the server thread, so DB writes committed inside the server can remain after the test.

### 15.2. Solutions

- Each test uses unique IDs/tenant namespace; controlled cleanup.
- Use a Testcontainers DB or a dedicated test schema/database.
- Reset the DB by truncate/snapshot/rollback at the proper boundary when permitted.
- For Kafka/email/payment, use stubs/sandboxes and avoid real side effects.
- Do not use `@DirtiesContext` as a way to clean up data committed outside the context.
- Do not make tests depend on execution order or shared mutable state.

With full-context MockMvc, when the request runs in the same thread/transaction, test rollback **can** work; however, async tasks or distinct transaction propagation still need verification. This demo does not use a database, so this caveat only applies when extending the project.

## 16. WebTestClient and WebFlux: The Client Name Does Not Decide Whether There Is a Socket

`WebTestClient` can operate in two modes:

| Creation Method | Has HTTP Server? | Purpose |
| --- | --- | --- |
| `WebTestClient.bindToController(...)` | No | Mock reactive controller |
| `WebTestClient.bindToApplicationContext(...)` | No | In-memory handler pipeline |
| `WebTestClient.bindToServer().baseUrl("http://...")` | Yes if server exists | HTTP integration |
| Boot WebTestClient in `@WebFluxTest` | No | Reactive web slice |
| Boot WebTestClient in `@SpringBootTest(RANDOM_PORT)` | Yes | Live server |

To use WebTestClient in Boot 3.5 MVC tests, `spring-webflux` must be on the classpath. If you do not want to add a reactive dependency for tests, `TestRestTemplate` is a convenient choice.

### 16.1. WebFlux Equivalent of the MVC Test Pyramid

- JUnit + `StepVerifier`: tests `Mono/Flux` services directly, no HTTP.
- `@WebFluxTest` + `WebTestClient`: tests reactive handlers, codecs/validation/webfilters in-memory.
- `@SpringBootTest(RANDOM_PORT)` + WebTestClient: starts a reactive HTTP server (typically Reactor Netty) and calls real TCP.

If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Boot 3.5 **prioritizes inbound MVC**. When intentionally testing a reactive runtime with both dependencies, check `spring.main.web-application-type=reactive` per the documentation for the exact version.

### 16.2. Be Careful with Boot 4 APIs

Some Boot 4 documentation mentions `RestTestClient` and new package names/test support. This project uses **Boot 3.5.16** and `TestRestTemplate`; do not copy code/test classes verbatim from documentation of another major version and assume they compile.

## 17. Security, Filters, Cookies, and CORS Across Test Levels

### 17.1. Spring Security in MockMvc

If the project has `spring-boot-starter-security`, do not blindly disable filters to “make tests pass.” With `spring-security-test`, you can use:

- `@WithMockUser` to simulate user/roles in mock tests.
- `SecurityMockMvcRequestPostProcessors.csrf()` for POST/PUT/DELETE if CSRF is used.
- 401/403 assertions for anonymous and wrong roles.
- Checking `@AutoConfigureMockMvc(addFilters=true)` and ensuring the Security filter chain is integrated.

**MockMvc can test security filter logic** in a mock environment; not every authorization unit/slice case needs a socket.

### 17.2. What Live HTTP Needs to Supplement

Verify `Set-Cookie` cookies, session stickiness, redirects, actual authentication headers, servlet filter registration, and security boundaries over a port. If HTTPS is enabled, test `Secure`/`SameSite` cookies, certificate trust, and HTTP→HTTPS redirects. However, a local HTTP demo **does not** automatically prove TLS, mTLS, or proxy behavior.

### 17.3. CORS and the Browser

MockMvc and TestRestTemplate can send Origin/OPTIONS and assert CORS headers. However, they are not browsers and **do not enforce blocking JavaScript cross-origin responses**. You need browser E2E when CORS is a real risk. Do not take curl 200 as proof that a browser will read the response.

### 17.4. Multipart/Upload/Streaming

MockMvc supports mock multipart requests and controller logic assertions, but actual body size limits, reverse proxy buffering, file spill-to-disk, chunked transfer, slow network clients, and HTTP/2 require live/server/deployment tests. Passing a 10 KiB mock multipart case does not prove a 2 GiB upload through a gateway works.

## 18. When Is Local Real HTTP Still Not Enough?

| Feature | Why Local Random-Port Does Not Prove It | Supplementary Test |
| --- | --- | --- |
| API gateway/Ingress | No path rewrite/load balancer | Staging smoke through gateway |
| TLS/mTLS | Cleartext HTTP demo | SSL-enabled server and actual truststore |
| OAuth/SSO | No identity provider | Sandbox authorization flow |
| Database schema | No DB in demo | Testcontainers and migrations |
| Kafka/Redis/email | Does not call downstream | Contract/integration tests |
| Browser cookies | No browser | Browser end-to-end |
| CORS enforcement | HTTP client does not enforce SOP | Browser E2E |
| Container orchestration | Single JVM | Cluster staging |
| HPA/autoscaling | No load and replicas | Load/scale test |
| Long-running resource leaks | A few short requests | Soak testing |
| CDN/browser cache | Localhost bypasses CDN | Staging frontend journey |
| Network policy/DNS | Not in a real pod/VPC | Network-level test |
| HTTP/2/compression | Unknown if not enabled or asserted | Dedicated protocol test |

A real server test only proves **the behaviors that the request actually traverses and the assertions actually check**.

## 19. Choosing the Right Test Suite in CI

A generally effective strategy:

- **Many unit tests** for business/domain edge cases; run on every commit.
- **MVC/WebFlux slice tests** for HTTP contracts, validation, advice, mock auth; run on every commit/PR.
- **Some full-context mock tests** to catch DI/configuration mistakes, when needed.
- **Live HTTP RANDOM_PORT tests** for servlet routing, startup/listener, headers/cookies, HTTP transport; run on every PR.
- **Testcontainers/sandbox integration** for DB/downstream, migrations, and transactions; with isolation.
- **Staging smoke/browser E2E** for proxy/TLS/cross-origin/real deployment.
- **Load/soak** to measure concurrency/p95/p99/throughput, not mixed into functional integration tests.

There is no need to repeat 100 pricing calculations through real Tomcat when unit tests already cover the branches properly; only a few contract/wiring/transport cases add distinct value.

### 19.1. Common Sources of Flakiness

- Hardcoding 8080 for random-port tests.
- `DEFINED_PORT` colliding with a running service.
- DB tests sharing data/IDs across methods, misunderstood transaction rollback.
- Mock singletons retaining state across tests/context cache.
- Using `Thread.sleep(100)` to “wait for async,” instead of bounded awaits.
- Spring context caching causing mutable data to persist; overusing `@DirtiesContext`.
- Parallel tests creating the same file/temp dir or external resource.
- HTTP clients without timeouts; tests hanging indefinitely.
- Spinning up real contexts unnecessarily often, slowing CI down.
- Test methods asserting only `status=200` without asserting the right body/owner/Content-Type.

Remedies: random ports, unique fixtures, deterministic fake clocks, bounded awaits, Testcontainers isolation, explicit profiles, and meaningful assertions.

## 20. Process for Diagnosing Test Failures at the Right Layer

1. **Unit fails:** check business logic/conditions; do not look for Tomcat bugs.
2. **Unit passes, MockMvc fails 404/405:** check controller mapping, URL/method, context path, and handler selection.
3. **MockMvc fails 400/415:** check DTO/`@Valid`/converters/Content-Type.
4. **MockMvc passes, full-context mock fails startup:** check dependency injection, config/profiles, missing beans.
5. **Full-context mock passes, live HTTP fails:** check embedded server binding, servlet registration, filter chain, request paths, TCP, active port.
6. **Live HTTP passes, deployed ingress fails:** check proxy rewrite, TLS, X-Forwarded-* and network policies.
7. **HTTP status right, body wrong:** check JSON naming, error advice, codec, or fallback route.
8. **Only real HTTP + database leaves rows:** check transaction boundaries and fixture cleanup.
9. **Security mock passes, browser fails:** check cookies, CSRF, CORS, redirects, TLS, and identity flow.
10. **Functional tests pass but production is slow:** need load/soak profiling, do not convert all functional tests into performance tests.

Do not treat removing filters/disabling validation/permitting all routes as a way to “turn the build green.” Fix the right component and add a regression test at the corresponding boundary.

### 20.1. Quick Symptom Table

| Symptom | Primary Suspect | How to Check |
| --- | --- | --- |
| `@SpringBootTest` but connection refused | `MOCK` does not open a server | Use `RANDOM_PORT` |
| `@LocalServerPort` empty | No server | Check webEnvironment |
| `@WebMvcTest` missing Service bean | Slice does not scan services | `@MockitoBean` or import |
| Unit test calling controller PASSES, HTTP 400 | MVC validation/conversion | MockMvc test body |
| MockMvc PASSES, live `/wire/ping` 404 | Wrong Servlet mapping | Test `ServletRegistrationBean` |
| MockMvc filter PASSES, other servlet lacks header | Different container filter registration | Live HTTP non-MVC |
| Live HTTP 200 locally, 404 behind proxy | Path rewrite/context path | Gateway E2E |
| Live POST 403 | Security/CSRF | Check policy/credentials |
| TestRestTemplate receives 500 without failing test | Status not asserted | Assert `getStatusCode()` |
| DB row remains after `@Transactional RANDOM_PORT` test | Client/server transactions differ | Reset database |
| Both WebFlux/MVC starters, test runs MVC | Boot selects MVC | Specify web application type |
| MockMvc only sees HTML index | SPA fallback | Assert JSON Content-Type/body |
| CI fails port in use | Fixed port | `RANDOM_PORT` |
| Browser CORS error even though curl 200 | Browser origin policy | Browser E2E |

## 21. Exercises and Self-Check

### Exercise A: Change Mapping

Change `@PostMapping("/quotes")` to `@PostMapping("/quote")` while keeping the old tests. Unit `PriceServiceTest` still passes; MockMvc/live HTTP tests calling `/api/quotes` fail. Lesson: mapping is a web-layer responsibility.

### Exercise B: Remove `@Valid`

Keep the controller/service but delete `@Valid` on `QuoteRequest`. `PriceService` still rejects quantity 0 as `IllegalArgumentException`, and the advice may still return 400. Thus asserting 400 alone is insufficient to prove **Bean Validation** ran. Add a test checking a validation-specific message/code or mock verification that the service is not called with invalid input. This is an important example of **false positives**.

### Exercise C: Remove Advice

Delete `ApiErrorHandler`. Unit tests still throw the right Java exception, but the HTTP error JSON contract changes. MockMvc/live HTTP assertions for `SKU_NOT_FOUND` must fail.

### Exercise D: Change Custom Servlet Mapping

Change `/wire/*` to `/other/*`. Spring MVC slice tests still pass, while live `RealHttpServerTest.tomcatDispatchesNonMvcServlet` fails. This test proves a Servlet container routing risk that MockMvc does not cover.

### Exercise E: Enable Context Path

Add `server.servlet.context-path=/shop`. Live paths become `/shop/api/quotes` and `/shop/wire/ping`. In MockMvc, the mock request context path must be set properly if simulating the exact Servlet context; do not manually add `/shop` to `@RequestMapping`.

### Exercise F: Add Security

Add the Security starter and protect `/api/quotes` with a role. Write MockMvc tests with `@WithMockUser`/CSRF for positive/negative cases; write live tests with corresponding credentials/session. Verifying auth is different from disabling filters.

### Exercise G: Add PostgreSQL

Have `PriceService` read prices from a DB; keep the slice test mocking the service to test the MVC contract. Add live/full-context tests with Testcontainers, schema migrations, and data reset. Verify in practice why `@Transactional` on a live HTTP test does not roll back the server transaction automatically.

### Exercise H: Two Ways of Using WebTestClient

Build one WebTestClient bound-to-controller and one bound-to-server; same JSON assertions, yet only the second proves requests go over a socket. Indicate the binding clearly in the test name.

### Quick Questions

1. **Does `@SpringBootTest` open a port by default?** No, `MOCK`.
2. **Does MockMvc go through DispatcherServlet?** Yes, with mock Servlet request/response.
3. **Does MockMvc test real Tomcat Servlet selection?** No.
4. **Does `@WebMvcTest` load all repositories/services?** No, MVC slice only.
5. **What does `@MockitoBean` solve?** Creates/replaces a collaborator bean with a mock in the test context.
6. **Does full-context MockMvc have a server?** No, unless a separate runtime server is configured.
7. **How to test a real port?** `@SpringBootTest(RANDOM_PORT)` + HTTP client.
8. **Why must `@LocalServerPort` be used?** Not hardcoding a random port.
9. **Does WebTestClient always go over TCP?** No, depends on binding.
10. **Why is test-side rollback insufficient for live HTTP?** Server and client run in different threads/transactions.
11. **Does a local TCP test prove TLS/Ingress?** No, unless tested through them.
12. **Does CORS from curl prove Browser behavior?** No.
13. **Is a 200 status enough for correctness?** No, body/headers/owner assertions are needed.
14. **When to use MockMvc more than live HTTP?** When testing MVC contracts/validation quickly and in isolation.
15. **Are all three levels—unit, mock, live—needed?** Yes, when risks exist in logic, MVC integration, and the actual server boundary.

## 22. Checklist Before Confirming “The Web Runtime Has Been Tested”

- [ ] Clearly state whether tests use unit/direct, MockMvc slice, full-context mock, or live HTTP.
- [ ] Do not call default `@SpringBootTest` a server integration test.
- [ ] MVC contracts have tests for method/path/JSON/`@Valid`/advice/error response.
- [ ] Collaborators are mocked only in slices where appropriate.
- [ ] Full-context tests verify important DI/configuration.
- [ ] When custom Servlets/Jersey exist, live HTTP tests cover the URL owner.
- [ ] Use `RANDOM_PORT` and `@LocalServerPort` to avoid port conflicts.
- [ ] TestRestTemplate 4xx/5xx statuses are all asserted.
- [ ] Headers, Content-Type, body, and status are checked rather than just 200.
- [ ] Spring Security/CSRF/CORS are tested with the right filters/runtime and negative cases.
- [ ] Database transactions/cleanup do not mistakenly rely on test-side rollback when server threads differ.
- [ ] Test dependencies do not mix Boot 3.5/Boot 4 APIs incorrectly.
- [ ] Reverse proxy/TLS/management ports are tested in the appropriate environment.
- [ ] Smoke tests exist through the executable JAR when packaging matters.
- [ ] Browser E2E is used for client-side enforcement and UI flows.
- [ ] Load/soak tests address concurrency/throughput, not inferred from functional HTTP tests.
- [ ] The suite is sufficiently fast/deterministic, without fixed ports/sleeps/conflicting fixtures.
- [ ] Test conclusions state accurately which boundary was verified.

## 23. Official References

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): MOCK, RANDOM_PORT, DEFINED_PORT, NONE, MockMvc, TestRestTemplate, WebTestClient, and rollback caveat.
- [Spring Boot 3.5 — Auto-configured Spring MVC Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.spring-mvc-tests): `@WebMvcTest`, `@MockitoBean`, MockMvc configuration.
- [Spring Framework 6.2 — MockMvc Overview](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/overview.html): MVC request processing with mock Servlet objects.
- [Spring Framework — MockMvc Setup Options](https://docs.spring.io/spring-framework/reference/testing/mockmvc/setup-options.html): `standaloneSetup` vs `webAppContextSetup`.
- [Spring Framework — MockMvc Request Builders](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/requests.html): building mock requests.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): bind-to-controller/context/server.
- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): Tomcat and server properties.
- [Spring Security — MockMvc Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): mock user, filters, and CSRF.
- [Spring Framework — Test Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback/transaction boundaries.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): JUnit lifecycle, assertions, parallel execution.

**Conclusion:** `MockMvc` tests Spring MVC using simulated request/response objects without **opening a port**. `RANDOM_PORT` lets you test a **real server** (Tomcat/Servlet registration/TCP/HTTP) and verify things mocks cannot see. Do not use one level to replace all others: unit tests protect logic, MVC slices protect HTTP contracts, full-context mocks protect wiring, live HTTP protects the container boundary, and staging/browser/load tests protect the remaining deployment boundaries.