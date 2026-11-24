# Starting a real server with RANDOM_PORT in Spring Boot Test

## 1. Why run a real HTTP server?

Testing Java methods or unit-testing services verifies internal logic, yet does not prove an HTTP request passes through a **socket**, is received by the embedded server, reaches the right controller, converts query/body data into Java objects, and returns the right status, headers, or JSON. **MockMvc** tests Spring MVC with mock servlet requests, which is usually faster but opens no network port. When you need to verify an endpoint receiving HTTP over a real network stack, use:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpIntegrationTest {
    // Test using an HTTP client to call the real embedded server.
}
~~~

With **RANDOM_PORT**, Spring Boot creates a WebServerApplicationContext, starts the embedded web server, and asks the operating system to choose an available port, essentially equivalent to **server.port=0**. Clients connect to the allocated port after the server starts. Do not hardcode a port like 8080 in test source because it easily collides during parallel runs on developer machines or CI.

**Expected outcomes:** You know when to pick RANDOM_PORT, how to obtain the port via **@LocalServerPort**, send GET/POST requests with **TestRestTemplate** or JDK **HttpClient**, assert HTTP status and JSON, distinguish it from MockMvc, and understand traps around transaction rollback, Spring context state, security, and concurrency.

**Illustrative versions:** Java 17+, Spring Boot **3.3.5**, Gradle, Spring MVC/embedded Tomcat from spring-boot-starter-web, JUnit Jupiter from spring-boot-starter-test. In other Spring Boot generations, recommended client/annotation names may change.

## 2. Four WebEnvironment modes of @SpringBootTest

| Value | Server started? | Characteristics | When to choose |
|---|---|---|---|
| **MOCK** (default) | Does not start a real embedded HTTP server | Mock web ApplicationContext if web stack is present; can use MockMvc | MVC tests, full context, no socket needed |
| **RANDOM_PORT** | **Yes** | Embedded server opens an OS-assigned port | HTTP integration tests, network boundaries, and servlet-container behavior |
| **DEFINED_PORT** | **Yes** | Port from server.port or usually 8080 if unconfigured | Special integrations requiring a specific port |
| **NONE** | No | ApplicationContext without a web environment | Testing beans/services without HTTP |

Illustrative example (not a complete runnable project):

~~~java
@SpringBootTest // WebEnvironment.MOCK
class WithoutRealServerTest {}

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RandomHttpServerTest {}

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.DEFINED_PORT)
class FixedHttpServerTest {}

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class NonWebContextTest {}
~~~

**Why does RANDOM_PORT fit CI?** When multiple suites run concurrently, two servers trying to use a fixed port easily collide. With port 0, the OS assigns a port upon binding, significantly reducing that risk. RANDOM_PORT does not guarantee test success if the sandbox forbids sockets, web dependencies are missing, or resources are exhausted.

**Setting webEnvironment=RANDOM_PORT is not enough to create an HTTP server in a non-web project.** The example below uses spring-boot-starter-web, providing Spring MVC, embedded Tomcat, and Jackson. If the project only has the base starter, do not assume endpoints/servers exist.

## 3. Request flow with RANDOM_PORT

~~~text
Gradle/JUnit Jupiter
        |
        | @SpringBootTest(RANDOM_PORT)
        v
Spring TestContext / Spring Boot bootstrap
        |
        | @SpringBootApplication, beans, MVC mappings, filters
        v
WebServerApplicationContext
        |
        | embedded Tomcat binds port 0
        v
OS allocates real port: 51xxx
        |                         |
        v                         v
@LocalServerPort              TestRestTemplate
        |                         |
        +-----------+-------------+
                    |
                 HTTP/TCP
                    |
                    v
           Tomcat servlet stack
                    |
             DispatcherServlet
                    |
             @RestController
                    |
          Jackson message converter
                    |
                    v
            HTTP status/body/headers
                    |
                    v
             JUnit assertions
~~~

Spring starts the ApplicationContext **before `@Test` methods run**. When the context has bean, mapping, startup, or binding errors, the test can fail before assertions. Once the server starts successfully, the test client connects over real HTTP even though server and test run **in the same JVM**.

In traditional MockMvc tests, **mvc.perform(...)** builds mock requests and dispatches them through Spring MVC infrastructure without sending requests over sockets. Never confuse “having a DispatcherServlet” with “having a listening TCP port”.

**RANDOM_PORT does not mean each test method creates a new server.** Spring TestContext can cache the ApplicationContext across tests with equivalent configurations; when reusing a context, the same server/port may be reused.

## 4. Obtaining the actual port: @LocalServerPort

In Spring Boot 3.3.x, the package is **org.springframework.boot.test.web.server.LocalServerPort**:

~~~java
import org.springframework.boot.test.web.server.LocalServerPort;

@LocalServerPort
int port;
~~~

This annotation reads the runtime property **local.server.port**, reflecting the actual port after the web server starts. **server.port=0** is a configuration directive asking the OS to pick a port, not a port a client can connect to. When constructing a URI manually, use the port from @LocalServerPort:

~~~java
URI uri = URI.create(
    "http://127.0.0.1:" + port + "/api/quotes");
~~~

These snippets must go inside a test class with appropriate URI imports. You can read the port via **Environment.getProperty("local.server.port", Integer.class)** once the test has a context, though that is unnecessary when using @LocalServerPort.

**Do not inject @LocalServerPort into a production bean constructor created before the server is initialized.** The property is only present once the server has bound. A test field injected by Spring after startup is the natural usage.

Also do not assert that the port always equals 8080, is always above 50000, or differs on every run. The right approach is simply verifying a valid port (1..65535) and **using that exact port number**.

## 5. Hands-on Spring Boot 3.3.5 project: Quote REST API

We design a stateless REST API to focus on sending real HTTP without needing a database or external services.

**Specification:**
- **GET /api/quotes?product=book&quantity=2** → status **200**, JSON response containing product=book, quantity=2, totalCents=2400.
- **POST /api/quotes** with JSON product=pen, quantity=4 → **201**, totalCents=1000.
- Unit prices: book **1200 cents**, pen **250 cents**.
- Valid quantity is **1 to 1000**; product must not be null/blank.
- Out-of-range quantity → **400**, unsupported product → **404**.
- GET missing required query parameters or non-integer quantity → **400** at the Spring MVC binding layer.
- Does not persist resources to a DB; POST illustrates HTTP 201 and JSON handling rather than creating an invoice in persistence.

### 5.1. File structure

~~~text
settings.gradle
build.gradle
src/main/java/demo/randomport/QuoteApplication.java
src/main/java/demo/randomport/QuoteRequest.java
src/main/java/demo/randomport/QuoteResponse.java
src/main/java/demo/randomport/QuoteController.java
src/test/java/demo/randomport/QuoteRandomPortTest.java
src/test/java/demo/randomport/QuoteMockMvcTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'random-port-http-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Explanation:** spring-boot-starter-web provides Spring MVC, Jackson, and embedded Tomcat; spring-boot-starter-test provides JUnit Jupiter, Spring Boot Test, Spring Test/MockMvc, and TestRestTemplate. useJUnitPlatform() configures Gradle to run JUnit Jupiter. Neither Spring Security nor a DB is included in this sample; adding them would change HTTP/error behavior and setup.

### 5.2. Production classes

**src/main/java/demo/randomport/QuoteApplication.java**

~~~java
package demo.randomport;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QuoteApplication {
    public static void main(String[] args) {
        SpringApplication.run(QuoteApplication.class, args);
    }
}
~~~

**src/main/java/demo/randomport/QuoteRequest.java**

~~~java
package demo.randomport;

public record QuoteRequest(String product, int quantity) {
}
~~~

**src/main/java/demo/randomport/QuoteResponse.java**

~~~java
package demo.randomport;

public record QuoteResponse(
        String product, int quantity, long totalCents) {
}
~~~

Java 17 records fit concise DTOs well. Jackson in Spring Boot 3.3 supports the records in this example. Each public type sits in a matching Java file, and QuoteResponse provides component-based equals/hashCode, making object assertions straightforward.

**src/main/java/demo/randomport/QuoteController.java**

~~~java
package demo.randomport;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {

    @GetMapping
    public QuoteResponse getQuote(
            @RequestParam("product") String product,
            @RequestParam("quantity") int quantity) {
        return calculate(product, quantity);
    }

    @PostMapping
    public ResponseEntity<QuoteResponse> postQuote(
            @RequestBody QuoteRequest request) {
        QuoteResponse quote =
                calculate(request.product(), request.quantity());
        return ResponseEntity.status(HttpStatus.CREATED).body(quote);
    }

    private static QuoteResponse calculate(
            String product, int quantity) {
        if (product == null || product.isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "product must not be blank");
        }
        if (quantity < 1 || quantity > 1000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "quantity must be in 1..1000");
        }

        long priceCents = switch (product) {
            case "book" -> 1200L;
            case "pen" -> 250L;
            default -> throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND,
                    "Unknown product");
        };

        return new QuoteResponse(
                product, quantity, priceCents * quantity);
    }
}
~~~

Here **@GetMapping** receives query params converted by MVC; **@PostMapping** uses Jackson to deserialize the JSON request body into QuoteRequest, returning ResponseEntity/201. Missing or mistyped parameter errors can be handled by the framework before calculate; quantity-range or unknown-product errors occur inside the simple business logic in calculate.

**ResponseStatusException** returns the corresponding HTTP status, while the error body shape is not rigidly specified in this example. Do not assert raw error JSON having a fixed shape unless you configured a dedicated error contract, as framework or custom ControllerAdvice implementations can change it.

## 6. Real HTTP integration tests with TestRestTemplate and Java HttpClient

**src/test/java/demo/randomport/QuoteRandomPortTest.java**

~~~java
package demo.randomport;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class QuoteRandomPortTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate restTemplate;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void embeddedServerHasARealPort() {
        assertTrue(port > 0 && port <= 65535);
    }

    @Test
    void getWithRealHttpReturnsJson() {
        ResponseEntity<QuoteResponse> response =
                restTemplate.getForEntity(
                    "/api/quotes?product=book&quantity=2",
                    QuoteResponse.class);

        assertEquals(200, response.getStatusCode().value());
        assertEquals(
                new QuoteResponse("book", 2, 2400L),
                response.getBody());
        assertNotNull(response.getHeaders().getContentType());
        assertTrue(response.getHeaders().getContentType()
                .isCompatibleWith(MediaType.APPLICATION_JSON));
    }

    @Test
    void postJsonReturnsCreated() {
        ResponseEntity<QuoteResponse> response =
                restTemplate.postForEntity(
                    "/api/quotes",
                    new QuoteRequest("pen", 4),
                    QuoteResponse.class);

        assertEquals(201, response.getStatusCode().value());
        assertEquals(
                new QuoteResponse("pen", 4, 1000L),
                response.getBody());
    }

    @Test
    void quantityZeroReturns400() {
        ResponseEntity<String> response =
                restTemplate.getForEntity(
                    "/api/quotes?product=book&quantity=0",
                    String.class);
        assertEquals(400, response.getStatusCode().value());
    }

    @Test
    void unknownProductReturns404() {
        ResponseEntity<String> response =
                restTemplate.getForEntity(
                    "/api/quotes?product=unknown&quantity=1",
                    String.class);
        assertEquals(404, response.getStatusCode().value());
    }

    @Test
    void missingQuantityReturns400() {
        ResponseEntity<String> response =
                restTemplate.getForEntity(
                    "/api/quotes?product=book",
                    String.class);
        assertEquals(400, response.getStatusCode().value());
    }

    @Test
    void invalidQuantityBindingReturns400() {
        ResponseEntity<String> response =
                restTemplate.getForEntity(
                    "/api/quotes?product=book&quantity=abc",
                    String.class);
        assertEquals(400, response.getStatusCode().value());
    }

    @Test
    void plainJdkClientCanConnectToEmbeddedServer() throws Exception {
        URI uri = URI.create(
                "http://127.0.0.1:" + port
                    + "/api/quotes?product=book&quantity=1");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpClient client = HttpClient.newHttpClient();
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());

        JsonNode json = objectMapper.readTree(response.body());
        assertEquals("book", json.path("product").asText());
        assertEquals(1, json.path("quantity").asInt());
        assertEquals(1200L, json.path("totalCents").asLong());
    }
}
~~~

**Test breakdown:**

1. @SpringBootTest(RANDOM_PORT) starts the real server before @Test methods.
2. @LocalServerPort retrieves the runtime port. Only check that the port is valid; never assert a fixed number.
3. @Autowired TestRestTemplate is Spring Boot 3.3's utility for real HTTP integration tests. Using **relative URLs** avoids repeating localhost:port in every get/post call.
4. On 400/404 responses, TestRestTemplate is designed for testing and typically **returns the status** for assertions rather than throwing an exception immediately on HTTP errors like a default-configured RestTemplate.
5. POST serializes the QuoteRequest record to JSON via Jackson, the server binds it back via @RequestBody, and returns QuoteResponse JSON.
6. GET returns QuoteResponse; assertEquals on the record verifies product, quantity, and totalCents completely. Assert Content-Type compatibility with application/json rather than comparing raw JSON with fixed property ordering.
7. The final test uses **Java 17 HttpClient**, connecting to **127.0.0.1:port** over a socket and parsing JSON with ObjectMapper to assert fields. In Java 17, HttpClient does not need try-with-resources here.
8. Tests do not write to a DB, so **no test depends on data created by another test**.

Cases per specification:

| Case | URL/Body | Expected Status | What is Verified |
|---|---|---|---|
| GET success | product=book, quantity=2 | 200 | totalCents=2400 |
| POST success | JSON pen, quantity=4 | 201 | totalCents=1000 |
| Quantity out of range | quantity=0 | 400 | Business validation |
| Product unknown | product=unknown | 404 | Resource/business lookup |
| Missing parameter | missing quantity | 400 | MVC required parameter |
| Mistyped parameter | quantity=abc | 400 | MVC type conversion |
| Runtime port | @LocalServerPort | valid | Embedded server has bound |
| JDK client | GET 127.0.0.1:port | 200 | Real HTTP and JSON parsing |

**Note:** @WithMockUser does not make a real HTTP request authenticated, because the server handles the request on a separate thread. If the app uses security, the client must send matching headers/tokens/cookies.

## 7. Comparison example: @WebMvcTest with MockMvc opens no socket

**src/test/java/demo/randomport/QuoteMockMvcTest.java**

~~~java
package demo.randomport;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(QuoteController.class)
class QuoteMockMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void mapsAndSerializesWithoutOpeningPort() throws Exception {
        mvc.perform(get("/api/quotes")
                        .param("product", "book")
                        .param("quantity", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.product").value("book"))
                .andExpect(jsonPath("$.quantity").value(2))
                .andExpect(jsonPath("$.totalCents").value(2400));
    }

    @Test
    void missingQuantityIsBadRequest() throws Exception {
        mvc.perform(get("/api/quotes")
                        .param("product", "book"))
                .andExpect(status().isBadRequest());
    }
}
~~~

@WebMvcTest only loads MVC-related components as a slice and opens no real embedded server. In this example, QuoteController injects no external service so the slice runs directly. If a controller injects QuoteService or a repository, the slice usually needs a test bean or appropriate mock.

| Criterion | @WebMvcTest + MockMvc | @SpringBootTest(RANDOM_PORT) |
|---|---|---|
| TCP port | No | **Yes** |
| Real servlet container handling requests | No | Yes, with starter-web/Tomcat |
| Verifies MVC routing and JSON | Yes | Yes |
| Full application context | No by default, it is a slice | Usually yes |
| Speed | Usually faster | Usually higher startup cost |
| Network boundary | No | Yes |
| Real error page/connector behavior | Limited | Better suited |
| External DB data | Depends on test configuration | Depends on test configuration |

**@SpringBootTest(webEnvironment=MOCK) + @AutoConfigureMockMvc** lets you test more beans than a web slice while still using mock requests. If you need to test sockets or embedded server configuration, calling mvc.perform alone is not enough.

## 8. Running the example, results, and JUnit reports

With a project containing the Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

The files listed in this lesson provide **source code and build configuration**; if you create the project manually without generating a wrapper, ./gradlew does not exist yet. Use a compatible Gradle installation to generate the wrapper or run gradle test.

In this source, **QuoteRandomPortTest has 8 @Test methods** and **QuoteMockMvcTest has 2 @Test methods**, totaling **10 test methods**. Without extra tests and with all environment requirements met, all are designed to PASS. Inspect the report at:

~~~text
build/reports/tests/test/index.html
~~~

You can run a single class:

~~~bash
./gradlew test --tests demo.randomport.QuoteRandomPortTest
./gradlew test --tests demo.randomport.QuoteMockMvcTest
~~~

Do not assert hardcoded port numbers or full startup logs: ports vary by OS, while Tomcat/Gradle logs vary by configuration. Stable assertions target HTTP status, JSON, and specified headers.

## 9. Why doesn't @Transactional on the test roll back server-side data?

This is the single most important trap when moving from MockMvc/unit tests to real HTTP integration.

With Spring TestContext, @Transactional on a test method typically opens a **test-managed transaction** and rolls back at the end of the test. However, when using RANDOM_PORT or DEFINED_PORT:
- The HTTP client executes on the **test thread**.
- The server receives HTTP on an **embedded server thread**.
- Thread-bound transaction context **does not automatically propagate over TCP**.
- If a server-side service uses its own transaction and commits database changes, **rolling back the test transaction does not roll back changes committed on the server**.

Snippet illustrating the false assumption:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class OrderHttpTest {
    // Sends POST /orders using a real HTTP client.
    // CANNOT assume server-side DB writes
    // will roll back when the test method ends.
}
~~~

This snippet is not a standalone runnable file; it highlights a transaction scenario needing special care. In an app with a POST endpoint creating entities, data committed by the server can persist into the next test.

**How to isolate data for real HTTP tests:**
1. Use a **dedicated test database/schema** or Testcontainers with an appropriate lifecycle.
2. Generate unique IDs/namespaces per test.
3. Clean up via repositories, @Sql/scripts, API fixtures, or schema resets **in the right transaction and against the right data source**.
4. Avoid assuming @DirtiesContext wipes the database; it evicts ApplicationContext from cache, leaving external DB data intact.
5. Handle mid-test crashes: with ephemeral DBs, leftover data does not pollute future runs or environments.
6. If tests run in parallel, never delete another test's data; use isolated prefixes/keys or isolated resources.

In the demo project, GET and POST compute **statelessly**, so no DB cleanup is needed. This is an intentional choice to keep focus on RANDOM_PORT.

## 10. ApplicationContext caching and parallel execution

Spring TestContext caches ApplicationContext by effective test configuration to reduce startup overhead. With RANDOM_PORT:
- Methods in one test class usually share the same context/server/port.
- Classes with equivalent configuration can reuse the cached context; classes with different profiles, properties, or mock beans can spawn new contexts.
- @DirtiesContext can shut down the server and create a new context, at which point the OS may assign a different port.
- A singleton service, fake Map, or Spring cache can retain state across tests sharing the same context.
- Dynamic ports only prevent **port** collisions; they do not automatically isolate databases, Redis, Kafka topics, files, or external accounts.
- Parallel tests sharing mutable beans or mocks can interfere with one another even when ports are valid.

**Never rely on test execution order** or assume test B runs after test A. When running a real server, keep each scenario independent with its own fixtures/setup/teardown. Check concurrency in both CI and your IDE since runner configurations may differ.

**Do not overuse @DirtiesContext** to cure state-leaking tests. It forces Spring and the embedded server to restart, which is very slow; locate where state leaks and clean it up first. Reserve @DirtiesContext for tests that genuinely modify unrecoverable context/configuration state.

## 11. Security, headers, and real HTTP

When an application adds Spring Security, the real server enforces authentication/authorization via the filter chain. In tests:
- Send the appropriate **Authorization** header, token, session cookie, or basic auth.
- Assert 401 for missing/invalid credentials, 403 when authenticated but unauthorized, and 200/201 when permitted.
- For POST/PUT/DELETE in browser sessions, understand CSRF requirements.
- Never assume @WithMockUser on a test method propagates to the server thread of a real HTTP request.

HTTP tests can also verify Content-Type, Accept, CORS headers, redirects, cookies, cache headers, and ETag; however, **assert only what belongs to the contract**. For instance, without security here, we only assert JSON content type on GET and status/body on the remaining cases.

**A real server does not replicate a browser or reverse proxy.** CORS enforcement is browser logic; TLS termination, DNS, ingress, load balancers, and multi-instance behavior generally require appropriate staging/E2E environments. Localhost RANDOM_PORT cannot replace those checks.

## 12. Choosing the right HTTP client

**TestRestTemplate:** Convenient for Spring Boot 3.3; accepts relative paths, serializes requests/deserializes responses via converters, and inspects HTTP 4xx/5xx errors via ResponseEntity.

~~~java
ResponseEntity<String> result = restTemplate.getForEntity(
        "/api/quotes?product=book&quantity=0",
        String.class);
assertEquals(400, result.getStatusCode().value());
~~~

**Java 17 HttpClient:** Spring-independent JDK client, using @LocalServerPort to construct URIs and inspect response status, headers, and body:

~~~java
URI uri = URI.create("http://127.0.0.1:" + port
        + "/api/quotes?product=pen&quantity=1");
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();
HttpResponse<String> response = HttpClient.newHttpClient().send(
        request, HttpResponse.BodyHandlers.ofString());
assertEquals(200, response.statusCode());
~~~

These two snippets are code **inside a @Test method with declared variables and imports**, not standalone Java files. JDK 17 HttpClient does not implement AutoCloseable; do not use try-with-resources with HttpClient on this JDK version.

**WebTestClient:** Spring Boot also supports WebTestClient for real-server tests with matching client dependencies/auto-configuration. In an MVC project, ensure WebFlux client/test libraries are on the test classpath when using WebTestClient. Note that WebTestClient's bindToController/bindToApplicationContext modes **do not use networking**; to test a real server you must target the running base URL.

**RestAssured:** Convenient HTTP assertion library requiring a separate dependency. If multiple tests run in parallel, avoid setting port in uncontrolled global state; configure per-request with the runtime port.

Pick one client that fulfills the goal. The example suite uses TestRestTemplate primarily, plus HttpClient to demonstrate a TCP connection independent of Spring test helpers.

## 13. Additional details easily overlooked

### 13.1. Management port differs from application port

When using Actuator with **management.server.port** set differently from server.port, management endpoints can run on a separate server/port. Then @LocalServerPort denotes the application port; **@LocalManagementPort** gets the management server port where supported. This example does not include Actuator.

### 13.2. WebFlux and embedded servers other than Tomcat

Spring Boot picks the stack from dependencies. In the example, starter-web ⇒ MVC + Tomcat by default. With WebFlux-only, RANDOM_PORT can use Netty/reactive server; if both MVC and WebFlux are present, MVC typically wins unless spring.main.web-application-type=reactive is configured. Thus, when adapting this approach to a WebFlux project, verify server type and client dependencies.

### 13.3. External services and Testcontainers

The application server port **is not** the PostgreSQL container port, fake HTTP server port, or message broker port. When tests need runtime addresses of external dependencies, use separate configuration (such as @DynamicPropertySource or proper Testcontainers integration), never local.server.port by mistake.

### 13.4. Timeouts and asynchronous tasks

Real HTTP calls may wait on DBs, networks, or background tasks. Configure sensible client/test timeouts; avoid Thread.sleep with guessed delays hoping things “finished”. For endpoints returning 202 Accepted, receiving 202 only confirms the request was accepted — **it does not prove the async job completed**. Poll status with a deadline and clean up properly.

### 13.5. HTTP error details can vary by configuration

The sample tests only assert HTTP status on 400/404 errors because error bodies are not strictly specified. When an app uses @ControllerAdvice/ProblemDetail/custom error codes, assert bodies according to the real contract. Do not write raw JSON expectations tied to incidental framework output of a single version.

## 14. Common errors and fixes

| Symptom | Cause | Solution |
|---|---|---|
| Connection refused at localhost:8080 | Hardcoded 8080 under RANDOM_PORT | Use @LocalServerPort or TestRestTemplate relative paths |
| @LocalServerPort = 0/fails to resolve | Wrong webEnvironment, import, or read before server startup | Check RANDOM_PORT, web dependencies, and annotation package |
| @Autowired TestRestTemplate fails | Missing test dependency or wrong bootstrap mode | Check starter-test and @SpringBootTest(RANDOM_PORT) |
| MockMvc passes yet HttpClient fails | Mock requests use no sockets | Check server startup, ports, filters, security |
| Port binding error in CI | Sandbox forbids binding or fixed port used | Check loopback permissions and use RANDOM_PORT |
| JSON/body differs from expected | Different DTO/serializer/message converter | Assert fields/content type per contract |
| 401/403 when expecting 200 | Spring Security blocks anonymous or CSRF | Send real credentials, check filter chain |
| 400 when quantity=abc | MVC cannot convert String to int | Confirm binding error is expected |
| @Transactional test still writes DB | Server thread uses separate transaction | Clean DB/test fixtures, do not rely on test rollback |
| Test passes alone, fails in full suite | Shared context/state, DB/cache, or parallelism | Isolate data, clean up the right source |
| Suite slow with many RANDOM_PORT tests | Starting full context/server repeatedly | Move small logic to unit/MockMvc, reduce redundant context configs |
| Management endpoint on different port | Separate management.server.port configured | Use management port, not application port |
| Port changes on every run | OS assigns port dynamically | Never assert a concrete port number, use @LocalServerPort |

**Short investigation workflow:** confirm annotations/imports and web starter → read startup logs and bean errors → check port/URL/method/body/auth → assert status before body → check state/transactions/server threads → run isolated and full suite to find isolation bugs.

## 15. Building a layered testing strategy

- **Unit/JUnit Jupiter:** Numerous business cases, fast execution without a context.
- **@WebMvcTest + MockMvc:** Mapping, validation, JSON/headers in the MVC slice, no sockets opened.
- **@SpringBootTest(MOCK) + @AutoConfigureMockMvc:** When full context is needed yet mock HTTP requests suffice.
- **@SpringBootTest(RANDOM_PORT):** Select high-value cases covering real HTTP, filter/auth flows, startup, container behavior, and multi-bean integration.
- **Testcontainers or real DB/broker integration:** Verifying persistence, transactions, and external protocols.
- **Staging/E2E:** Verifying proxies/TLS, ingress, service discovery, production-like config, and multi-instance setups.

Do not force every controller test onto RANDOM_PORT by default. A healthy test suite has many fast unit/MVC tests and targeted real HTTP tests matched to real risks, without paying unnecessary startup costs.

## 16. Self-check

**1. Why doesn't `@SpringBootTest` without `webEnvironment` imply a real HTTP server?**  
Because the default is **MOCK**, providing a mock web environment without opening an embedded server over TCP.

**2. `server.port` is set to 0. How do you obtain the actual connection port?**  
Use `@LocalServerPort`, read `local.server.port` after startup, or use `TestRestTemplate` with compatible relative URLs.

**3. Must two `RANDOM_PORT` tests have two different ports?**  
No. Spring TestContext can cache contexts/servers and reuse the port; a port is only chosen on server startup.

**4. A `@Transactional` test sends a POST creating a real entity over HTTP; does test rollback delete the server-committed row?**  
Not automatically, because server and client run on separate threads/transactions. Cleanup and test DB isolation are required.

**5. Why doesn't adding `@WithMockUser` alone guarantee `TestRestTemplate` gets 200 past server security?**  
The test thread's fake security context does not automatically travel as credentials on a real HTTP request; appropriate authentication must be sent.

**6. What tests should use MockMvc instead of RANDOM_PORT?**  
Mapping, validation, JSON conversion, and controller logic that do not require network ports or servlet container network-level behavior.

**7. Where does `GET quantity=abc` return 400?**  
During Spring MVC's binding/type conversion before the controller invokes `calculate(int quantity)`.

**8. Can `RANDOM_PORT` test production reverse proxies or TLS ingress?**  
Not by default; it only runs a local embedded server. Appropriate integration/staging environments are needed to test proxy/network deployment.

## 17. Official documentation

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html) — WebEnvironment, random ports, and transactional behavior.
- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html) — server.port=0, @LocalServerPort.
- [Spring Boot 3.3 — TestRestTemplate](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/client/TestRestTemplate.html) — HTTP test client.
- [Spring Boot 3.3 — SpringBootTest](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/SpringBootTest.html) — choosing webEnvironment.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html) — mock MVC requests.
- [JDK 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html) — standard Java HTTP client.

**Conclusion:** **RANDOM_PORT starts a real HTTP server on an OS-allocated port**, unlike MockMvc. Use @LocalServerPort or TestRestTemplate to send requests to the right port, verify status/headers/JSON, and remember to manage transactions, databases, shared state, and security as real integration components.
