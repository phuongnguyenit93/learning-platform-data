# Limitations of Mock Web Environments with Container Filters and Network Configuration

## 1. Purpose and scope

In Spring Boot Testing, a **mock web environment** loads the web application context and processes requests using mock Servlet APIs **without starting a Servlet container listening on a real HTTP port**. This mechanism is very helpful for testing Spring MVC, yet it is not sufficient to conclude that **all Servlet container filters, URL mappings, dispatcher types, connector configurations, network ports, TLS, proxies, and transport behavior** have been verified.

This lesson examines boundaries frequently overlooked when writing integration tests:

- `@SpringBootTest(webEnvironment = MOCK)` loads a mock web context without starting an embedded server.
- `@AutoConfigureMockMvc(addFilters = true)` lets MockMvc execute `Filter` instances added to its **mock filter chain**; that **does not mean** real container filter registration has been verified.
- `FilterRegistrationBean`, `@WebFilter`, and `@ServletComponentScan` govern **Servlet container registration**, including URL patterns, servlet names, dispatch types, ordering, and async support.
- Settings such as `server.port`, `server.servlet.context-path`, `server.ssl.*`, `server.compression.*`, `server.forward-headers-strategy`, and connector limits must be tested at the **right boundary**.
- `@SpringBootTest(webEnvironment = RANDOM_PORT)` with a real HTTP client adds the embedded server and network path, yet still does not reproduce production reverse proxies, DNS, ingress, load balancers, or the Internet.

**Hands-on objective:** build a Java 17+ / Spring Boot 3.x application containing **one Spring bean filter** and **one filter registered exclusively via `FilterRegistrationBean`**; use MockMvc to prove request handling / filter beans and faked request metadata; use real HTTP to verify container filter URL mapping and context path. From this, know precisely what each test proves.

This lesson covers only the **Servlet stack / Spring MVC**; WebFlux has a different web filter model and Netty server, contrasted later. There is no database, Docker, or security provider in the sample code to keep it easy to reproduce; those topics are discussed in the limitations and production sections.

## 2. Two layers to distinguish: Spring MVC pipeline and Servlet container

### 2.1. MockMvc passes through DispatcherServlet without a network connector

Execution path of `MockMvc.perform(...)`:

```text
JUnit test
  |
  +-- MockMvc.perform(...)
       |
       +-- MockHttpServletRequest / MockHttpServletResponse
       +-- MockFilterChain (Filters registered with MockMvc)
       +-- DispatcherServlet
            +-- HandlerMapping / HandlerAdapter
            +-- converters / validators / exception resolvers
            +-- controller --> service --> repository (if loaded)
       |
       +-- Mock response --> status/header/jsonPath assertions
```

This is a conceptual diagram. In Spring Framework, MockMvc **invokes `DispatcherServlet` directly** with mock Servlet API implementations from `spring-test`, needing no running server.

Things MockMvc can still test very well:

- request mappings by method/path, path variables, query parameters;
- argument binding, type conversion, `@Valid`, and validation;
- JSON/XML converters present in the test application context;
- controller advice, exception resolvers, response status/body;
- real service/repository logic when using a full test context;
- `Filter` instances actually added to the mock filter chain;
- many Spring Security authorization/CSRF cases with Spring Security Test.

Things **not proven simply because MockMvc passes**:

- whether embedded Tomcat/Jetty/Undertow starts and binds a port;
- whether the servlet container applies URL pattern / dispatcher mappings and startup lifecycle identically to production;
- whether raw HTTP request bytes are parsed by the connector identically to production;
- header/body limits, timeouts, connection reuse, keep-alive, HTTP/2;
- TLS handshakes, certificates, proxy trust, actual forwarding;
- container access logs, network-layer compression, multi-connector behavior;
- requests/responses crossing sockets with client and server on separate threads.

### 2.2. Real HTTP with `RANDOM_PORT`

Execution path of a live HTTP test:

```text
JUnit client thread
  |
  +-- HttpClient GET http://127.0.0.1:<random-port>/demo/api/...
       |
       +-- TCP loopback + HTTP bytes
       +-- embedded server connector
       +-- ServletContext / servlet/filter registrations
       +-- mapped Filter chain by URL/dispatcher/order
       +-- DispatcherServlet
            +-- controller/service/repository
       +-- response encoding + socket
  |
  +-- HttpClient receives status, headers and body
```

Now there is a real server/port in the test process, and requests flow through the container. However, the test machine is still only calling **loopback localhost**. When proxies/TLS/ingress are absent from the test environment, that segment remains **unverified**.

### 2.3. Context breadth is an independent axis

| Configuration | Context loaded | Request path | Embedded server |
|---|---|---|---|
| `@WebMvcTest` + MockMvc | MVC slice | Mock Servlet | No |
| `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` | Full test `ApplicationContext` per config/profile | Mock Servlet | No |
| `@SpringBootTest(RANDOM_PORT)` + HTTP client | Full test `ApplicationContext` per config/profile | HTTP over real socket | Yes |
| `@SpringBootTest(RANDOM_PORT)` + MockMvc | Can have full context and server if MockMvc is also configured | **`mockMvc.perform` is still the mock path** | Server may be running, yet that call skips the socket |
| Staging through proxy/gateway | Deployed system in staging | HTTP(S) across multiple hops | Yes, plus real infrastructure |

**Remember:** the name `@SpringBootTest` does not automatically guarantee real HTTP. The default `webEnvironment` is `MOCK`. Conversely, having a running server does not turn `MockMvc.perform(...)` into a network call.

## 3. Filters are three distinct concepts in one system

The word "filter" appears at multiple layers, yet those layers carry different responsibilities.

### 3.1. Servlet Filter: the executing component

In the Servlet API, a `jakarta.servlet.Filter` has the primary method:

```java
void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException;
```

This is an **illustrative signature** of the Servlet interface, not a standalone runnable source file.

A filter can inspect/modify requests, set response headers, reject requests, or call `chain.doFilter(...)` to proceed. In real applications, filters handling authentication, correlation IDs, encoding, CORS, or logging may need to run strictly before or after others.

A filter existing inside the Spring `ApplicationContext` is **not sufficient** to prove how the Servlet container registered it across URLs or dispatchers.

### 3.2. Filter registration: configuration for the container

In a Spring Boot Servlet application, common registration mechanisms are:

1. Declaring a `Filter` as a Spring bean (e.g., `@Component`): Boot normally auto-registers the filter with the embedded servlet container, typically mapped to `/*`.
2. Declaring a `FilterRegistrationBean<T extends Filter>`: configures **URL patterns**, **servlet names**, **order**, **dispatcherTypes**, **asyncSupported**, enabled/disabled state, and other options.
3. Using Servlet API `@WebFilter` alongside `@ServletComponentScan` so the container discovers Servlet components per supported scanning rules.
4. In Spring Security, `DelegatingFilterProxy` and `springSecurityFilterChain` bridge beans in the Spring context with Servlet container registration.

These mechanisms are **related yet not identical**. A filter declared via `FilterRegistrationBean` should not accidentally be registered a second time by combining a stereotype bean annotation with manual registration without understanding how Boot handles registration. If you must combine them, verify Boot/container behavior and avoid double registration.

### 3.3. MockMvc filter chain: a different registration mechanism

Spring Test provides `MockFilterChain`. With standalone MockMvc, you can configure:

```java
mockMvc = MockMvcBuilders.standaloneSetup(controller)
        .addFilters(new CharacterEncodingFilter())
        .build();
```

This is an **illustrative snippet**, requiring a controller and full imports. The filter is only placed into the mock chain by this setup; **no container `ServletContext.addFilter(...)` runs over a real connector**.

With `@AutoConfigureMockMvc(addFilters = true)`, Boot adds matching filters from the Spring context into MockMvc. However, that is not proof that all registration beans, URL patterns, servlet mappings, dispatcher types, or lifecycle hooks of a **real Servlet container** were verified properly.

**Avoid the extreme claim "MockMvc runs no filters at all."** That is false whenever filters are registered in the mock chain. The accurate statement is: *MockMvc tests filter logic added to the mock chain; real HTTP tests verify container-specific registration through a live server*.

## 4. Container filter properties that must be verified at the right layer

### 4.1. URL patterns

A `FilterRegistrationBean` can register a filter only for:

```java
registration.addUrlPatterns("/api/private/*");
```

The real container uses Servlet URL patterns to decide which requests enter the filter. Expectations:

- Requests to `/api/private/inspect` will match.
- Requests to `/api/public/inspect` bypass **that registration**, assuming no other mapping covers it.
- If the application sets `server.servlet.context-path=/demo`, external clients call `/demo/api/private/inspect`, yet the filter URL pattern remains relative to the **path inside the application context**, i.e. `/api/private/*`, without hardcoding `/demo`.

Mocking a request to `/api/private/inspect` does not prove the real container applied that mapping. Send real HTTP to the running server port and compare headers/effects between URLs inside and outside the pattern.

### 4.2. DispatcherType

Servlets define dispatch types such as:

- `REQUEST`: initial request from client;
- `FORWARD`: internal forward via `RequestDispatcher`;
- `INCLUDE`: including a resource;
- `ASYNC`: asynchronous dispatch;
- `ERROR`: error dispatch.

A filter participates only in dispatch types permitted by its registration. With `FilterRegistrationBean`, `setDispatcherTypes(...)` configures this. Per Spring Boot Servlet documentation, when dispatch types are omitted, the Servlet specification default is **`REQUEST`**.

Example:

```java
registration.setDispatcherTypes(
        DispatcherType.REQUEST,
        DispatcherType.ASYNC,
        DispatcherType.ERROR);
```

This is an illustrative snippet using `jakarta.servlet.DispatcherType` imports. If a filter is responsible for async or error dispatches as well, configure it accordingly and **write a test exercising real dispatches**. Never assume a synchronous MockMvc request test covers `ASYNC`/`ERROR` dispatches.

**Note on `OncePerRequestFilter`:** this class also exposes hooks like `shouldNotFilterAsyncDispatch()` and `shouldNotFilterErrorDispatch()`. Allowing `ASYNC`/`ERROR` in registration is **one requirement**, yet filter implementation logic can still opt out of certain dispatches. Verify **both the mapping and the filter's own logic**.

### 4.3. Filter order

Critical concerns such as security, logging, encoding, forwarded-header handling, and request wrappers can depend on execution order.

```java
registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
```

This is a snippet for `FilterRegistrationBean`. Boot defines default orders for many built-in filters/registrations; if ordering a plain `Filter` bean, you can use annotations or implement `Ordered` where appropriate, whereas with a registration bean prefer `setOrder(...)` per API.

**Do not test order merely by asserting that two headers both exist.** Two filters can run in the wrong order and still both set headers. When order is part of the contract, write a test where filter A sets a request attribute/wrapper that filter B depends on, and verify the chained behavior over real HTTP.

### 4.4. `asyncSupported` and error handling

A filter or servlet can be registered with `asyncSupported = true/false`. Misconfiguration can cause async processing to fail on the real container even though a MockMvc test does not go through the same container lifecycle.

If an application uses `DeferredResult`, `Callable`, Servlet async, or error pages, dedicated live-server tests should check dispatcher types, filter behavior, and cleanup. A MockMvc test with `asyncDispatch(...)` is very helpful for the **Spring MVC async contract**, yet still does not reproduce container async timeouts, connectors, or network behavior.

### 4.5. Init parameters, lifecycle, and `ServletContextInitializer`

A filter can be initialized via `init(FilterConfig)`, read init parameters, or depend on container lifecycle. `FilterRegistrationBean` is a `ServletContextInitializer` responsible for registering filters in the Servlet container.

Mock Servlet objects and `MockFilterChain` do not prove that the **actual registration configuration inside the embedded container** ran just like production. If a filter depends on container init parameters, mappings, servlet names, or initialization order, verify it through a live server and, where needed, container inspection/observability.

## 5. Differences among ways to "exclude filters"

It is easy to change the wrong thing when a filter blocks a request.

| Configuration | Effect | What it does NOT prove or change |
|---|---|---|
| `@AutoConfigureMockMvc(addFilters = false)` | Omits filter beans from the application context in MockMvc per config | Does not remove beans and does not prove the filter won't run on a real server |
| `@WebMvcTest(excludeFilters = ...)` | Tunes component-scan candidates in an MVC slice | Not a generic filter to strip all auto-configs or `@Bean`/`@Import` beans |
| `FilterRegistrationBean.setEnabled(false)` | Disables that bean's **registration** in the Servlet container | Does not necessarily remove the filter bean instance from the Spring context |
| `FilterRegistrationBean.addUrlPatterns(...)` | Restricts mapping in the Servlet container | Does not automatically control every filter added into MockMvc |
| Spring Security test user/CSRF postprocessor | Supplies test authentication/CSRF context | Does not bypass filters; does not prove real OIDC/TLS |
| `@SpringBootTest(RANDOM_PORT)` + HTTP client | Traverses real filter/servlet container inside test JVM | Does not include production gateways/proxies on the request path |

**Never use `addFilters = false` to "fix" an HTTP 401/403 and still claim security rules were tested.** With MockMvc, supply principals and CSRF tokens using Spring Security Test when needed. With real HTTP, send valid test credentials/cookies/tokens via the HTTP client.

## 6. Complete example in Java 17+ and Spring Boot 3.x

The sample code is designed to separate **filter logic in MockMvc** from **container URL mapping over live HTTP**, while also showing that MockMvc can fabricate "HTTPS-like" request metadata without any TLS.

**Supported scope:** Spring Boot 3.x, Servlet MVC, Java 17+, JUnit Jupiter, `spring-boot-starter-web`, and `spring-boot-starter-test`. No Spring Security, R2DBC, JPA, databases, external APIs, or real proxies.

### 6.1. Dependencies

**Gradle Groovy DSL** — inside a project already having the Boot plugin, dependency management, Java toolchain, and repositories:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Maven** — inside a `pom.xml` already having the Spring Boot parent/BOM and appropriate test plugin:

```xml
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
```

These are **dependency snippets**, not complete build files; do not add duplicate dependencies if your project already has them. JDK 17 includes `java.net.http.HttpClient`. Spring Boot 3 uses `jakarta.servlet.*` packages, not `javax.servlet.*` from Boot 2 applications.

### 6.2. File structure

```text
src/
├── main/java/com/example/boundary/
│   ├── BoundaryApplication.java
│   ├── ProbeController.java
│   ├── GlobalStampFilter.java
│   └── ScopedFilterConfiguration.java
└── test/java/com/example/boundary/
    ├── MockBoundaryTest.java
    └── RealContainerBoundaryTest.java
```

All production classes sit in `com.example.boundary`, sharing the package of `@SpringBootApplication` so default component scan finds the controller, filter bean, and configuration.

### 6.3. Spring Boot application

**File `src/main/java/com/example/boundary/BoundaryApplication.java`:**

```java
package com.example.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}
```

No hardcoded port. `MOCK` tests start no server; `RANDOM_PORT` tests let Boot select an available port.

### 6.4. Controller reading request metadata

**File `src/main/java/com/example/boundary/ProbeController.java`:**

```java
package com.example.boundary;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ProbeController {

    public record Snapshot(
            String path,
            String scheme,
            boolean secure,
            int port,
            String remoteAddress
    ) {}

    @GetMapping({"/public/inspect", "/private/inspect"})
    public Snapshot inspect(HttpServletRequest request) {
        return new Snapshot(
                request.getRequestURI(),
                request.getScheme(),
                request.isSecure(),
                request.getServerPort(),
                request.getRemoteAddr());
    }
}
```

The controller merely reflects **values supplied by the Servlet request**. In MockMvc, those values can be set manually by the test on the mock request; in live HTTP, they are populated by the container from the actual HTTP connection/headers and applied configuration.

This lesson deliberately excludes sensitive info or tokens from the response. In production applications, **never expose a public endpoint echoing arbitrary request headers or remote addresses** just for debugging, as it can leak data or widen the attack surface. This endpoint exists strictly as a learning fixture.

### 6.5. Filter bean running across requests

**File `src/main/java/com/example/boundary/GlobalStampFilter.java`:**

```java
package com.example.boundary;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class GlobalStampFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        response.setHeader("X-Global-Stamp", "active");
        chain.doFilter(request, response);
    }
}
```

This is a Spring `@Component` Servlet `Filter`. In MockMvc tests using `@AutoConfigureMockMvc` with default `addFilters = true`, matching filters from the context are added to the mock chain. In real HTTP tests, Boot auto-registers this `Filter` bean with the embedded Servlet container.

Both tests **assert `X-Global-Stamp: active` on both paths**. That avoids the misconception that MockMvc "skips all Filters".

### 6.6. Dedicated filter registered only via `FilterRegistrationBean`

**File `src/main/java/com/example/boundary/ScopedFilterConfiguration.java`:**

```java
package com.example.boundary;

import java.io.IOException;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration(proxyBeanMethods = false)
public class ScopedFilterConfiguration {

    @Bean
    FilterRegistrationBean<ScopedFilter> scopedFilterRegistration() {
        FilterRegistrationBean<ScopedFilter> registration =
                new FilterRegistrationBean<>();

        registration.setFilter(new ScopedFilter());
        registration.addUrlPatterns("/api/private/*");
        registration.setDispatcherTypes(DispatcherType.REQUEST);
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return registration;
    }

    static final class ScopedFilter implements Filter {
        @Override
        public void doFilter(
                ServletRequest request,
                ServletResponse response,
                FilterChain chain)
                throws IOException, ServletException {

            ((HttpServletResponse) response)
                    .setHeader("X-Scoped-Stamp", "private-only");
            chain.doFilter(request, response);
        }
    }
}
```

**Three intentional details:**

1. `ScopedFilter` has **no** `@Component` and is not exposed as a standalone `@Bean Filter`. It is passed strictly inside `FilterRegistrationBean` to avoid unintended extra registration paths.
2. URL pattern `/api/private/*` restricts container registration to the private branch inside the application context.
3. `DispatcherType.REQUEST` and ordering are declared explicitly; the live test proves the **URL branch** without pretending to test all dispatcher types or ordering interactions.

**Do not make rigid claims in `MockMvc` about this scoped header.** How `FilterRegistrationBean` is wired into the mock chain and whether URL patterns are enforced can differ from how a real container applies the registration; that is precisely why the live test uses socket requests to verify the filter registration contract.

### 6.7. `MOCK` test: filter in context and fabricated request metadata

**File `src/test/java/com/example/boundary/MockBoundaryTest.java`:**

```java
package com.example.boundary;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
    classes = BoundaryApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
class MockBoundaryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void springFilterBeanRunsInMockFilterChain()
            throws Exception {

        mvc.perform(get("/api/public/inspect")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string(
                        "X-Global-Stamp", "active"))
                .andExpect(jsonPath("$.path").value(
                        "/api/public/inspect"));
    }

    @Test
    void httpsAndRemoteAddressCanBeFakedWithoutTls()
            throws Exception {

        mvc.perform(get("/api/public/inspect")
                .with(request -> {
                    request.setScheme("https");
                    request.setSecure(true);
                    request.setServerPort(443);
                    request.setRemoteAddr("203.0.113.10");
                    return request;
                }))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Global-Stamp", "active"))
                .andExpect(jsonPath("$.scheme").value("https"))
                .andExpect(jsonPath("$.secure").value(true))
                .andExpect(jsonPath("$.port").value(443))
                .andExpect(jsonPath("$.remoteAddress")
                        .value("203.0.113.10"));
    }
}
```

**Expected outcome:** **2 `@Test` methods pass** in a properly configured Spring Boot 3.x MVC project. There is no real HTTPS port 443 and no connection from `203.0.113.10`. Those fields are populated on `MockHttpServletRequest` by the test itself.

This is a key learning point: the controller returning `"https"` and `secure=true` in MockMvc **does not prove certificates are trusted, TLS handshakes succeed, or actual traffic is encrypted**. The test only checks how the controller responds to faked request properties.

The test also proves a `Filter` Spring bean **can execute in the mock chain**, while concluding **nothing** about `ScopedFilter`'s URL mapping from that result.

### 6.8. Real container test: port, context path, and filter registration

**File `src/test/java/com/example/boundary/RealContainerBoundaryTest.java`:**

```java
package com.example.boundary;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = BoundaryApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "server.servlet.context-path=/demo"
)
class RealContainerBoundaryTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    private HttpResponse<String> get(String path)
            throws Exception {

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(
                        "http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    @Test
    void privateUrlIsMappedToContainerRegisteredFilter()
            throws Exception {

        assertThat(port).isGreaterThan(0);

        HttpResponse<String> response =
                get("/demo/api/private/inspect");

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.headers().firstValue(
                "X-Global-Stamp")).contains("active");
        assertThat(response.headers().firstValue(
                "X-Scoped-Stamp")).contains("private-only");

        JsonNode json = mapper.readTree(response.body());
        assertThat(json.path("path").asText()).isEqualTo(
                "/demo/api/private/inspect");
        assertThat(json.path("scheme").asText()).isEqualTo(
                "http");
        assertThat(json.path("secure").asBoolean()).isFalse();
    }

    @Test
    void publicUrlDoesNotMatchPrivateFilterRegistration()
            throws Exception {

        HttpResponse<String> response =
                get("/demo/api/public/inspect");

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.headers().firstValue(
                "X-Global-Stamp")).contains("active");
        assertThat(response.headers().firstValue(
                "X-Scoped-Stamp")).isEmpty();

        JsonNode json = mapper.readTree(response.body());
        assertThat(json.path("path").asText()).isEqualTo(
                "/demo/api/public/inspect");
    }

    @Test
    void realContextPathChangesReachableHttpUrl()
            throws Exception {

        HttpResponse<String> missingPrefix =
                get("/api/public/inspect");

        assertThat(missingPrefix.statusCode()).isEqualTo(404);

        HttpResponse<String> correctPrefix =
                get("/demo/api/public/inspect");

        assertThat(correctPrefix.statusCode()).isEqualTo(200);
    }
}
```

**Expected outcome:** **3 `@Test` methods pass** in a Spring Boot 3.x project with an embedded Servlet MVC server from the web starter and no interfering security/proxy config. The client sends real HTTP requests to the loopback port chosen by Boot; context path `/demo` is configured on the server in the test class.

This live test proves:

- The embedded server opens a real TCP port.
- A client can GET over a socket into the application.
- The global filter bean is applied by the container.
- The URL-pattern-registered filter affects only `/api/private/*` (the public URL lacks its header).
- `server.servlet.context-path=/demo` alters the client-reachable route.

**Do not claim** it verified HTTPS, mTLS, reverse proxies, all `DispatcherType` values, or other containers: the URI is `http://127.0.0.1`, and the snippet exercises only `REQUEST` and the specific embedded container selected by dependencies.

### 6.9. Running the tests

Linux/macOS — choose **one** build tool for your project:

```bash
# Gradle Wrapper:
./gradlew test --tests "com.example.boundary.MockBoundaryTest"
./gradlew test --tests "com.example.boundary.RealContainerBoundaryTest"

# Or Maven Wrapper:
./mvnw -Dtest=MockBoundaryTest test
./mvnw -Dtest=RealContainerBoundaryTest test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.boundary.MockBoundaryTest"
.\gradlew.bat test --tests "com.example.boundary.RealContainerBoundaryTest"

# Or Maven Wrapper:
.\mvnw.cmd "-Dtest=MockBoundaryTest" test
.\mvnw.cmd "-Dtest=RealContainerBoundaryTest" test
```

In total, the example has **5 JUnit tests**, comprising **2 MockMvc tests + 3 live HTTP tests**. The code prints no explicit `stdout`; Spring Boot, Maven/Gradle, and IDEs may log startup/test summaries per configuration. Inspect the test report to confirm tests actually executed rather than trusting the exit code of a cached build.

## 7. Why should you not rigidly compare every MockMvc and live server result?

### 7.1. Different servlet configurations can be simulated differently

MockMvc can use `MockServletContext` and execute `MockFilterChain`. An embedded server uses a container-initialized `ServletContext` applying real mappings and `ServletContextInitializer` instances. A MockMvc test and a live HTTP test might also load contexts with different profiles/properties, so comparing outputs without recording exact configs easily leads to false conclusions.

The runnable example intentionally **avoids asserting** whether `ScopedFilter`'s header appears in MockMvc; what we want to prove is **Servlet container URL mapping**, so we verify it on the live path. MockMvc is used only for the filter bean assertion and faked request scheme demonstration.

### 7.2. `addFilters=true` does not promise simulating all registration metadata

Having `@AutoConfigureMockMvc(addFilters = true)` does not mean:

- container init lifecycle ran identically to real startup;
- `FilterRegistrationBean` URL mappings were applied untouched;
- `DispatcherType.ERROR/ASYNC` and container mapping ordering were proven;
- security proxy setup or header trust works over the network.

Use MockMvc to verify callable filter logic, and use real HTTP to verify container and connector contracts.

### 7.3. A filter can reject a request on its own

If `Filter#doFilter` returns 403 before calling `chain.doFilter(...)`, the controller is never invoked. In MockMvc, that can be reproduced **if the right filter is registered**. However, if the filter only registers on specific URLs/dispatchers in a real container, forcing that filter onto every MockMvc request can produce results **that diverge from production**.

When you hit 403 in a live test yet 200 in MockMvc, check (a) which filter chain ran in each test, (b) security config, (c) URL/dispatcher mappings, and (d) environment properties, instead of assuming the controller is broken.

## 8. Which network configurations can a mock web environment not prove?

### 8.1. Port, bind address, and server startup

Spring Boot provides properties such as:

- `server.port`: HTTP port;
- `server.address`: interface bind address;
- `server.servlet.context-path`: context path of the Servlet application;
- `management.server.port`: management port if separate from app port.

In `webEnvironment = MOCK`, no socket listens, so injecting `server.port=8080` or seeing it in `Environment` proves only that the **config value resolved**, not that port 8080 bound cleanly.

In live HTTP tests, `RANDOM_PORT` picks a free port to avoid CI contention. When testing a specific port is required, `DEFINED_PORT` can help, provided parallel workers are isolated and the port is free. Never use production ports for routine local tests.

**Rule:** If the question is "did the app receive the port config?", unit/context tests may suffice. If the question is "can a client connect to the port?", you need a real server and HTTP client. If the question is "can external network users reach it?", test from the **target network**, not just localhost.

### 8.2. Context path and Servlet mapping

Configuring:

```properties
server.servlet.context-path=/demo
```

affects the URI called by an out-of-JVM client. A client request to `/demo/api/public/inspect` reaches the app, whereas `/api/public/inspect` returns 404 for missing the context path.

MockMvc can construct mock requests with context paths via builders/postprocessors. However, manually setting `contextPath("/demo")` or `servletPath(...)` on a mock request **does not prove** the live server's connector and `ServletContext` actually deployed that configuration.

### 8.3. Header limits, URI limits, request body size

Servlet containers can enforce limits on:

- total header size or request line length;
- number of headers / request params;
- form post or multipart request size;
- body read timeouts, connection timeouts;
- concurrent connections, backlog, and thread pools.

In MockMvc you can feed arbitrarily large mock request contents and headers directly; it **does not verify** whether the real connector accepts or rejects those raw bytes per policy.

To test 413/400/431 or other transport rejections from limits, send controlled payloads with a real HTTP client against the actual container and version, consulting version-specific properties. **Never assume every container returns the exact same status code** for every limit violation.

### 8.4. HTTP/2, compression, keep-alive, streaming

Properties like `server.http2.enabled`, `server.compression.enabled`, and other connector settings only take effect when the real server and protocol support execute. MockMvc can assert an app-set response header, yet cannot measure HTTP/2 negotiation, wire compression, chunked transfer, connection reuse, or client disconnects.

Even a live HTTP test must use the **right client/protocol** to prove the feature. JDK `HttpClient` negotiates protocols and handles certain behaviors by default; when testing HTTP/2, verify actual `HttpResponse.version()` and TLS/ALPN where relevant.

### 8.5. Request scheme and `isSecure()` can be faked

In the sample, MockMvc can set:

```java
request.setScheme("https");
request.setSecure(true);
request.setServerPort(443);
```

These are **three mock mutations inside a `RequestPostProcessor`**, not SSL configuration. If a controller builds absolute URLs from `request.getScheme()`, the test can check the output under faked HTTPS. However, it **does not verify** keystores, truststores, certificates, SNI, or TLS handshakes.

A live test intending to prove TLS must call `https://` against a real SSL server with an HTTP client configured with a valid trust chain. Never take a shortcut disabling certificate verification in production-oriented tests just to turn them green.

## 9. Forwarded headers, reverse proxies, and trust boundaries

### 9.1. Why don't mock headers prove a proxy is right?

When a reverse proxy terminates HTTPS and forwards HTTP to the backend, it can add:

```text
Forwarded: proto=https;host=shop.example.org
X-Forwarded-Proto: https
X-Forwarded-Host: shop.example.org
X-Forwarded-For: 203.0.113.10
```

This is an illustrative example, **not a recommendation to trust every header**. The backend may use these headers to build redirects/absolute URLs or determine the client address. However, an arbitrary client can also **forge** those headers unless the edge proxy strips or overwrites them.

A MockMvc test writing:

```java
mvc.perform(get("/api/public/inspect")
        .header("X-Forwarded-Proto", "https"))
        .andExpect(status().isOk());
```

only proves a request carrying that supplied header passes through the test pipeline. It **does not prove** the real trusted proxy adds the header properly, untrusted clients cannot spoof it, or the app trusts the right proxy hops.

### 9.2. `server.forward-headers-strategy`

In a Spring Boot Servlet app, the property:

```properties
server.forward-headers-strategy=framework
```

tells the framework to process forwarded headers via Spring's mechanism, such as `ForwardedHeaderFilter` where applicable. Common strategies include:

- `none`: do not handle forwarded headers via that strategy;
- `native`: rely on servlet container support;
- `framework`: use Spring Framework's support.

**Never treat this as an automatic anti-spoofing shield.** Whether using `native` or `framework`, define the **trust boundary** at the reverse proxy/ingress: the edge must strip or normalize forwarded headers arriving from untrusted clients before sending logically authenticated values to the backend.

### 9.3. `ForwardedHeaderFilter` and order

Per Spring Framework, `ForwardedHeaderFilter` wraps the request so `getScheme()`, `getServerName()`, and related fields reflect the forwarded metadata. It must run **before** other filters/handlers that depend on the rewritten metadata. For error/async dispatches, filter mappings must also be configured properly.

Therefore, MockMvc tests with faked headers are insufficient to prove:

- the filter is registered in the real container in the right order;
- forwarding from the real ingress works;
- trusted-hop selection / container valve algorithms behave properly;
- security redirects and `Secure`/`SameSite` cookies work across the network path;
- behavior when multiple `X-Forwarded-For` values and intermediate proxies exist.

Split testing cleanly:

1. **Unit/MockMvc:** forwarded-header parsing logic inside MVC/filters given controlled inputs.
2. **Live HTTP to embedded server:** container/filter strategy and request metadata through the connector.
3. **Staging/infrastructure:** real proxy trust, ingress/TLS, redirects, and client addresses across deployment hops.

### 9.4. Never log sensitive data while debugging

Request headers can contain `Authorization`, Cookies, session tokens, and personal IP addresses. Avoid `andDo(print())` dumping entire requests in CI when sensitive data is present; mask values or log only non-sensitive header names and metadata. Never treat client IPs in tests as proof of user identity.

## 10. Spring Security: filter chains and real authentication are two different goals

### 10.1. MockMvc can still test authorization

If the app uses Spring Security and its filter chain is wired into MockMvc, you can test:

- 401/403 when missing authentication or roles;
- requests accepted when the principal holds the right role;
- CSRF enforcement on unsafe methods;
- `SecurityContext` propagation into controllers in tests;
- security headers emitted by the app/filters.

For instance, Spring Security Test provides `@WithMockUser` or `user(...)` / `csrf()` request postprocessors. They enable fast, valuable authorization tests.

### 10.2. What mock users do not prove

A `@WithMockUser` test **does not execute production login/OIDC handshakes**, verify real issuer/JWK retrieval, establish TLS sessions, exercise browser cookie policies, or test proxy auth. Even localhost HTTP with a fake JWT does not prove the production IdP or gateway works.

Keep both test groups when security is required:

- **authorization tests** with MockMvc / Spring Security Test for fine-grained rules;
- **protocol/integration tests** over real HTTP and environments with matching authentication infrastructure for login, JWT decoding, session cookies, gateways, and OAuth redirects.

### 10.3. Why can a 403 failure be a filter problem rather than a controller bug?

A request can be rejected before reaching `DispatcherServlet` by a security filter or container filter. Debugging workflow:

1. Identify the status, exception, and where in the filter chain it stopped.
2. Check URL patterns/dispatchers in the real container.
3. Check auth/CSRF/roles and security filter ordering.
4. Compare the mock filter chain against the live chain.
5. Only then look for mapping/controller bugs.

**Never set `addFilters=false` across all tests** just to dodge 403s and claim the API meets its security contract.

## 11. Other HTTP differences between MockMvc and containers: classic cases

### 11.1. GET succeeds in MockMvc, fails to connect in live HTTP

**Possible causes:** server did not start, wrong `webEnvironment`, wrong port, bind address, firewall, or client targeting the wrong host.

Check `@SpringBootTest(webEnvironment = RANDOM_PORT)`, `@LocalServerPort`, server startup logs, and the URI built with the injected port. `@SpringBootTest(MOCK)` **opens no port**; that is not a MockMvc bug.

### 11.2. Live HTTP returns 404 while MockMvc returns 200

Possible causes:

- missing `server.servlet.context-path` in the real URI;
- servlet mapping, path prefix, case sensitivity, or encoded paths;
- proxy rewrites or header handling;
- the two tests load different profiles/configurations;
- the request hit a different server/port.

For example, the live test in Section 6 sets `/demo`, so calling without the prefix intentionally returns 404. The MockMvc test for the same app omits that context path; you cannot mechanically compare "the same URI" when test configurations differ.

### 11.3. Filter runs in MockMvc yet not in live HTTP

Possible causes: URL pattern mismatch, different `DispatcherType`, disabled registration, filter registered only by mock-context config, or ordering short-circuiting with another filter.

Inspect the **actual registration bean and live request**, not merely whether the bean exists in the application context. If the filter must run on async/error dispatches, ensure the mapping declares them and `OncePerRequestFilter` hooks do not skip them.

### 11.4. Live HTTP shows a filter effect missing in MockMvc

The filter may exist solely as a container registration (not an auto-added MockMvc filter bean), or register via `ServletContextInitializer`, `@ServletComponentScan`, `web.xml`, or a server container mechanism. In standalone MockMvc, you may also have forgotten `addFilters(...)`.

**Right conclusion:** the mock chain and live chain are not configured identically. Do not immediately "change" the production filter to satisfy MockMvc; first decide whether the test is verifying **filter logic** or **container registration**.

### 11.5. Live HTTP returns 400/413/431 while MockMvc accepts the request

Suspect raw header sizes, request line length, multipart/form size limits, encoding, or the HTTP protocol parser. Spring MVC validation returns 400 in both, whereas container rejection happens **before the controller** and must not be mistaken for a `@Valid` error.

Test with controlled HTTP payloads of exact sizes against the pinned container version. Do not predict exact status codes solely from property values without verifying experimentally on the target container.

### 11.6. HTTP redirect has wrong scheme/host

Suspect forwarded-header strategy, proxy trust, filter order, context path, or `Host` header. A MockMvc test with `request.setScheme("https")` only proves the controller builds URLs accurately **given faked request metadata**. Use live HTTP — and a proxy environment when relevant — to prove real user redirects.

## 12. Transaction and thread boundaries when moving to real HTTP

### 12.1. Test transactions with synchronous MockMvc

Spring TestContext can start a **test-managed transaction** for `@Transactional` test methods. In a synchronous MockMvc request executing on the same test thread, controller/service/repository calls can join that transaction when the transaction manager and propagation match; Spring rolls back the test transaction after the method by default.

However, not all side effects are guaranteed to roll back: async work, `REQUIRES_NEW`, external queues, files, remote HTTP calls, or separate transaction managers can escape it.

### 12.2. Real HTTP clients and servers use separate transactions

With `RANDOM_PORT` or `DEFINED_PORT`, client and server run on **different threads**, per Spring Boot guidelines. Test-thread transactions **do not apply** to server threads, so server-committed writes are not rolled back by `@Transactional` on the JUnit test.

**Consequence:** swapping `mockMvc.perform(post(...))` for a real HTTP client while still assuming DB writes roll back can make the suite order-dependent. Use dedicated test DBs/schemas, explicit seeding and cleanup, Testcontainers, or proper fixture management.

### 12.3. Parallel tests and network environment

- `RANDOM_PORT` avoids fixed-port collisions yet does not eliminate all race conditions.
- Tests with HTTP servers can still collide on static state, DBs, brokers, caches, or management ports.
- Context caching can reuse contexts with matching configs; mutable singleton state must be reset.
- A test mutating JVM-global system properties without restoring them can break other tests.
- Never use `@DirtiesContext` as a replacement for cleaning up externally committed data.

## 13. Which test method for each contract?

| What needs to be proven | Preferred test | Why |
|---|---|---|
| Controller returns right JSON/status | MockMvc slice/full-context | Fast, covers Spring MVC pipeline |
| `Filter#doFilter` sets headers / blocks requests properly | MockMvc with matching filter chain | Tests filter logic without starting a server |
| `FilterRegistrationBean` maps only one URL pattern | **Real HTTP + embedded container** | Tests mappings enforced by the Servlet container |
| Filter runs during `ERROR`/`ASYNC` dispatches | Live server exercising those dispatches | Synchronous mock requests are insufficient |
| Port binds and clients can connect | `RANDOM_PORT`/`DEFINED_PORT` + HTTP client | Requires a real socket |
| Real context path and servlet mapping | Real HTTP with URI including context path | Measures client reachability |
| Changing `X-Forwarded-Proto` alters redirect logic | MockMvc + right filter config | Tests Spring logic with controlled inputs |
| Real proxy strips spoofed headers | Staging/E2E through trusted proxy | Tests at the actual trust boundary |
| TLS certificates / HTTPS | Real HTTPS + truststore, or staging | Requires real handshake/certificates |
| Header-size / connector limits | Real HTTP against right container | MockMvc lacks a network parser |
| HTTP/2, gzip, streaming, keep-alive | Live protocol/client tests | Involves transport and connector |
| Spring Security authorization | MockMvc + security filter chain | Fast rule verification |
| OAuth/SSO/real browser cookies | Live HTTP/browser/infra integration | Mock principals do not simulate login protocols |
| DB rollback across requests | Depends on thread/test model; real HTTP needs explicit cleanup | Test transactions do not span server threads |

**Optimizing the test suite:** most mapping/JSON/validation/security rules belong in MVC tests. Only container/network contracts need selective HTTP tests. Add infrastructure tests when proxies, TLS, or ingress are part of the requirements.

## 14. Versions: Spring Boot 2, 3, and 4

### 14.1. Spring Boot 3.x (the runnable code in this lesson)

Key imports:

```java
import jakarta.servlet.Filter;
import jakarta.servlet.DispatcherType;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
```

Boot 3.x projects typically use `spring-boot-starter-web` and `spring-boot-starter-test`. Boot 3 requires Java 17+ and uses Jakarta Servlet packages.

### 14.2. Spring Boot 2.x

Spring Boot 2.x commonly uses `javax.servlet.*` rather than `jakarta.servlet.*`, with different Java/dependency baselines. Copying Boot 3 Java sources into Boot 2 will fail to compile Servlet imports. Check version compatibility rather than assuming every annotation/test class shares the same package.

The core principles — **`MOCK` starts no server**, **`MockMvc` uses a mock Servlet pipeline**, **`RANDOM_PORT` starts a real embedded server** — remain true, though code/builds must match the older docs.

### 14.3. Spring Boot 4.x

Boot 4 modularizes testing and moves several packages/starters. For example, `@AutoConfigureMockMvc` is organized under:

```java
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
```

MVC starters include `spring-boot-starter-webmvc` and `spring-boot-starter-webmvc-test`, depending on the release. Cross-check Servlet API, JSON/Jackson, test modules, and JDK requirements against your project's Boot 4 BOM.

**Do not migrate Boot 3 to 4 by changing one import while leaving all old dependencies unchanged.** This lesson's runnable code explicitly targets Spring Boot 3.x; do not assume it compiles untouched across every Boot 4.x branch.

### 14.4. WebFlux differs from Servlet MVC

With WebFlux, you typically use `WebFilter`, `WebTestClient`, and a reactive server (such as Reactor Netty); it does not use `jakarta.servlet.Filter`/`FilterRegistrationBean` in the same way unless running on a Servlet stack.

`WebTestClient` also has **serverless modes** when bound to handlers/contexts and a **real HTTP mode** when bound to a server. Never judge from the client's name alone whether traffic crossed the network; check how the test binds it.

## 15. Practice exercises

### Exercise A. Explain two non-contradictory results

In MockMvc, this test:

```java
mvc.perform(get("/api/public/inspect")
        .with(request -> {
            request.setScheme("https");
            request.setSecure(true);
            return request;
        }))
        .andExpect(jsonPath("$.scheme").value("https"));
```

passes. Can we conclude the server has HTTPS enabled?

**Answer:** no. The test merely faked request metadata; there was no TLS handshake, certificate, connector, or real HTTPS port. Testing HTTPS requires an SSL server and an HTTPS client verifying trust.

### Exercise B. Filter runs only on the private endpoint

You register a filter via `FilterRegistrationBean` with `addUrlPatterns("/api/private/*")`. When the app has context path `/demo`, which two URIs should the client test?

**Answer:** `/demo/api/private/inspect` and `/demo/api/public/inspect`. The live HTTP test must verify the header/effect appears on private and is absent on public. The registration pattern stays `/api/private/*` without prepending the context path.

### Exercise C. Why doesn't `addFilters=false` remove a filter bean?

Given:

```java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc(addFilters = false)
class ExampleTest {
}
```

Question: is a Spring bean `GlobalStampFilter` removed from the `ApplicationContext`?

**Answer:** not by default. The annotation alters filter registration on **MockMvc**, not component scanning or Spring context bean definitions. On a real server, Boot can still register the filter per application config.

### Exercise D. Missing `ERROR` dispatch

A filter sets only `setDispatcherTypes(DispatcherType.REQUEST)`, yet requirements demand audit logging on error dispatches too. Is a passing synchronous GET test enough?

**Answer:** no. Configure `ERROR` mapping appropriately, check `OncePerRequestFilter`/container logic, and run a test triggering a real error dispatch. Note that responses may already be committed before error pages run, so do not assert headers blindly; design an explicit fixture.

### Exercise E. Proxy trusts untrusted `X-Forwarded-For`

An Internet client sends `X-Forwarded-For: 127.0.0.1` and the backend treats it as localhost. Where could the bug be?

**Answer:** misconfigured trust boundary. The proxy/ingress must strip or overwrite forwarded headers from untrusted clients; the backend should only trust metadata from properly configured proxies. A MockMvc test injecting a faked header tests parsing logic only and cannot catch an edge proxy failing to sanitize headers.

### Exercise F. Choosing test scope for HTTP 413

A large upload passes in MockMvc yet receives an error status from live Tomcat. Should you change controller validation to match the mock run?

**Answer:** no. Check body size, multipart/connector limits, proxy limits, request encoding, and exception layers. Use a live HTTP test against the designated server/container to verify expected behavior. The exact status depends on where the request was rejected rather than guessing from one config flag.

### Exercise G. DB test over live HTTP does not roll back

A JUnit test with `@Transactional` POSTs over `RANDOM_PORT`; the record remains after the test. Is `@Transactional` broken?

**Answer:** not necessarily. The HTTP server executes on a separate thread/transaction, so test-thread rollback does not roll back server work. Use explicit data cleanup or an isolated test database.

## 16. Checklist before finalizing filter/container/network tests

- [ ] Know whether the test uses `@WebMvcTest`, `@SpringBootTest(MOCK)`, or `RANDOM_PORT`.
- [ ] Know precisely whether requests go through MockMvc or an HTTP client/socket.
- [ ] Do not treat a filter bean's presence in the context as proof of container registration.
- [ ] Do not treat MockMvc `addFilters=true` as proof of real URL patterns or dispatcher mappings.
- [ ] Distinguish `FilterRegistrationBean`, `@WebFilter`/`@ServletComponentScan`, and Spring `@Component`.
- [ ] Avoid double registration from declaring the same filter across multiple mechanisms unchecked.
- [ ] Account for `DispatcherType.REQUEST/ASYNC/ERROR` and `OncePerRequestFilter` hooks when needed.
- [ ] Test execution order when filters depend on one another rather than just checking header presence.
- [ ] Write real HTTP tests for contracted URL patterns or network properties.
- [ ] With context paths, keep client URIs and registration patterns clearly distinct.
- [ ] Use `@LocalServerPort` only for real embedded server tests.
- [ ] Never call localhost over HTTP and claim TLS/proxies/DNS were tested.
- [ ] Trust forwarded headers only from safely configured proxies/hops.
- [ ] Keep security filter chains and CSRF active rather than bypassing them unintentionally.
- [ ] Define HTTP client timeouts, headers, body encoding, and ports explicitly.
- [ ] Never rely on test `@Transactional` to roll back server threads over real HTTP.
- [ ] Match Servlet packages and test starters to the Boot major version.
- [ ] Never touch production DBs, production endpoints, or real secrets in CI.
- [ ] Keep mock tests focused on fast feedback; let real HTTP tests verify container boundaries.
- [ ] Add dedicated E2E tests when contracts depend on proxies, gateways, TLS, or deployment infrastructure.

## 17. Conclusion

**A mock web environment has no Servlet container running over the network.** It is powerful for testing Spring MVC request handling, and filter logic can still run when wired into `MockFilterChain`. However, contracts belonging to **Servlet container registration** (URL patterns, dispatcher types, ordering, lifecycle) and **networking** (ports, client-facing context paths, connectors, TLS, compression, forwarded headers through proxies) require additional verification at their real boundaries.

With Spring Boot, use **MockMvc for web logic** and **`RANDOM_PORT` + an HTTP client for container/transport contracts**, adding staging/proxy/TLS tests when deployment characteristics are part of the requirements. Never escalate every test to live HTTP, and never use a green MockMvc run to claim the entire production network environment is proven.

## Official documentation

- [Spring Framework — MockMvc Overview](https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html): mock Servlet API + `DispatcherServlet` without a running server.
- [Spring Framework — MockMvc Filter Registrations](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/filters.html): registering filters in `MockFilterChain` during tests.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `MOCK`, `RANDOM_PORT`, embedded servers, and transaction caveats.
- [Spring Boot 3.5 — FilterRegistrationBean Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/FilterRegistrationBean.html): registering filters by URL/servlet mappings and startup lifecycle.
- [Spring Boot 3.5 — Embedded Web Servers How-to](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): Servlet/Filter/Listener registration, default dispatch type, and lifecycle.
- [Spring Boot 3.5 — AutoConfigureMockMvc Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/AutoConfigureMockMvc.html): `addFilters` and mock configuration.
- [Spring Framework — Servlet Filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): `ForwardedHeaderFilter`, trust boundaries, async/error dispatcher mappings.
- [Spring Boot 3.5 — ForwardHeadersStrategy](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/ServerProperties.ForwardHeadersStrategy.html): `NATIVE/FRAMEWORK/NONE`.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): ports, SSL, HTTP/2, compression, and forwarded headers.
- [Java 17 — HttpClient Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP client for testing embedded servers over sockets.
