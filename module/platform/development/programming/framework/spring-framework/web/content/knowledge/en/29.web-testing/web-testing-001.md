# Distinguishing Standalone Controller Testing, Infrastructure Testing, and HTTP via a Real Server

When testing a Spring Web endpoint, the first question is **what are we trying to prove?** A successful Java method call does not prove that the URL, JSON, filters, or HTTP actually work. Conversely, starting the entire application to test a small calculation branch can make the test slow and hard to diagnose when it fails.

This lesson uses Spring MVC (Servlet) as the main example, distinguishing three boundaries: **standalone controller**, **in-memory Spring MVC infrastructure**, and **HTTP to a real server**. Spring Boot 3.3 utilities are presented as a convenient way to configure tests; Spring Framework concepts do not depend on whether Spring Boot is used.

## 1. Understanding the testing boundaries

A real HTTP request passes through multiple layers, typically in this flow:

```text
HTTP client → embedded server TCP port → Servlet filters
            → DispatcherServlet → handler mapping / argument resolver
            → Controller → Service → other dependencies
            → message converter / exception handler → HTTP response
```

Tests can target different points along this flow:

| Approach | How it executes | Loads Spring context? | Opens HTTP port? | What it proves best |
| --- | --- | --- | --- | --- |
| Calling controller method directly | Instantiate object manually, call method like regular Java | No | No | Controller handling branches and dependency interactions |
| `MockMvcBuilders.standaloneSetup(...)` | Instantiate controller manually, build default/explicitly configured MVC components around it | Not needed | No | Request mapping, binding, JSON, status, and advice configured by the test |
| `MockMvcBuilders.webAppContextSetup(...)` | Use a real `WebApplicationContext` along with the Spring MVC configuration | Yes | No | Controller integration with MVC config, beans, resolvers, converters, and included interceptors/filters |
| Spring Boot `@WebMvcTest` + `MockMvc` | Load an application slice serving Spring MVC, mock required collaborators | Yes, limited to web slice | No | Web layer with the configuration actually loaded by the slice |
| Spring Boot `@SpringBootTest` + `@AutoConfigureMockMvc` | Load a broader application context; send simulated requests through MVC | Yes, near/full app per configuration | No | Interactions across multiple real beans, MVC, and app config, without network testing |
| `@SpringBootTest(webEnvironment = RANDOM_PORT)` + HTTP client | Start embedded server, send requests to localhost/real port | Yes | **Yes** | Real HTTP transport, container/Servlet integration, serialization, and runtime configuration |

**Key takeaway:** `MockMvc` simulates Servlet requests/responses and executes many MVC processing steps, but **does not open a socket**. Therefore, a 200 status from `MockMvc` is not equivalent to proof that the server can accept an HTTP request over the network.

The phrase **“infrastructure testing”** here mainly refers to *web* infrastructure (Spring MVC configuration, filters, converters, exception resolvers, dependency injection), and does not automatically mean testing PostgreSQL, Redis, or external services. Those dependencies are only truly tested when the test actually starts/connects to them.

## 2. Shared sample application across testing levels

Assume a Spring Boot 3.3, Java 17+ project with `spring-boot-starter-web` and `spring-boot-starter-test`, using JUnit Jupiter. Place the following classes in package `com.example.demo`. Use the same `GET /api/greetings/{name}` endpoint to see exactly which layer is tested.

File `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

File `src/main/java/com/example/demo/GreetingService.java`:

```java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

File `src/main/java/com/example/demo/GreetingController.java`:

```java
package com.example.demo;

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
    public GreetingDto greet(@PathVariable String name) {
        return new GreetingDto(greetingService.greet(name));
    }

    public record GreetingDto(String message) {}
}
```

When the application runs, a `GET /api/greetings/An` request returns HTTP 200 with JSON having the `message` field as `"Hello, An"`. The record describes the response data clearly; converting it to JSON is handled by MVC/Jackson, **not** by the `greet` method building a JSON string itself.

## 3. Level 1 — testing a standalone controller as a Java object

File `src/test/java/com/example/demo/GreetingControllerUnitTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class GreetingControllerUnitTest {
    @Test
    void delegatesNameToService() {
        GreetingService service = mock(GreetingService.class);
        when(service.greet("An")).thenReturn("Hello, An");

        GreetingController controller = new GreetingController(service);
        GreetingController.GreetingDto result = controller.greet("An");

        assertEquals("Hello, An", result.message());
        verify(service).greet("An");
    }
}
```

The test instantiates the controller with `new`, provides a mock service, and calls the method directly. It proves that the controller passes the name to the service and returns the expected result. No Spring context, `DispatcherServlet`, URL matching, JSON converter, or filter runs. If there is a typo in `@GetMapping("/...")`, this test can still pass.

**When to use:** checking decision branches, orchestration logic, or collaborator interactions. For a controller that only delegates in one line, the added value of a unit test is usually small; prioritize testing behavior with real risk and add a test verifying the HTTP contract at the MVC level.

## 4. Level 2a — MockMvc standalone: running Spring MVC in memory with manually chosen configuration

File `src/test/java/com/example/demo/GreetingControllerStandaloneTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class GreetingControllerStandaloneTest {
    @Test
    void mapsHttpRequestAndSerializesResponse() throws Exception {
        GreetingService service = mock(GreetingService.class);
        when(service.greet("An")).thenReturn("Hello, An");

        MockMvc mvc = MockMvcBuilders
                .standaloneSetup(new GreetingController(service))
                .build();

        mvc.perform(get("/api/greetings/An"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, An"));
    }
}
```

`standaloneSetup` does not load an application context. It builds enough MVC components to handle a mock request, so it tests path-to-handler mapping, `@PathVariable` values, and JSON response in the test configuration. However, the application's custom `@ControllerAdvice`, `WebMvcConfigurer`, converters, validators, filters, or security **do not appear automatically**: register them on the builder when they themselves are within the scope to be tested.

This is neither merely a unit test calling a method nor a real application test yet. It is a scoped web-behavior test built manually, typically fast and helpful for isolating the controller.

## 5. Level 2b — testing MVC/application configuration: real context, simulated requests

### 5.1. Spring Framework: webAppContextSetup

Once you have a `WebApplicationContext` loaded by Spring TestContext, you can build:

```java
// Snippet used inside a test that already has a configured WebApplicationContext.
MockMvc mvc = MockMvcBuilders.webAppContextSetup(webApplicationContext).build();
```

Here `webApplicationContext` must be a context created from the desired MVC configuration. `webAppContextSetup` obtains mappings, resolvers, converters, and many registered components from that context itself, thereby catching integration errors that standalone misses. Even so, the test still runs simulated requests and **does not** connect over TCP to an embedded server. You can use Spring TestContext with `@WebAppConfiguration`, `@ContextConfiguration`, or equivalent configuration annotations in a plain Spring Framework application.

### 5.2. Spring Boot: @WebMvcTest is a web slice

File `src/test/java/com/example/demo/GreetingControllerWebSliceTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(GreetingController.class)
class GreetingControllerWebSliceTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    GreetingService service;

    @Test
    void returnsGreetingThroughWebLayer() throws Exception {
        when(service.greet("An")).thenReturn("Hello, An");

        mvc.perform(get("/api/greetings/An"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, An"));
    }
}
```

`@WebMvcTest` is a **Spring Boot** utility, not a core Spring Framework annotation. It creates a context scoped to the web layer, auto-configures `MockMvc`, and typically uses mocks to replace collaborators outside the slice. In **Spring Boot 3.3**, `@MockBean` belongs to `org.springframework.boot.test.mock.mockito`; in newer Spring/Boot versions there is a different `@MockitoBean` API, so check your version before copying imports.

The test checks the MVC components loaded in the slice, but does not prove the real service/repository is wired properly. If security is added to the classpath, specify the expected filter chain and user/role/CSRF in the test rather than disabling filters just to get status 200; the slice can load appropriate security components.

### 5.3. @SpringBootTest + @AutoConfigureMockMvc: broad context, requests still mocked

File `src/test/java/com/example/demo/GreetingControllerContextTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class GreetingControllerContextTest {
    @Autowired
    MockMvc mvc;

    @Test
    void usesRealServiceBeanThroughMvc() throws Exception {
        mvc.perform(get("/api/greetings/An"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, An"));
    }
}
```

`@SpringBootTest` defaults to `webEnvironment = MOCK`: it creates an application context with a simulated web environment **without starting an embedded server**. `@AutoConfigureMockMvc` lets you test `DispatcherServlet` against the loaded beans, MVC mappings, converters, and configurations. Unlike the slice example, the service here is a real bean; if the application has a datasource, messaging, or beans that are heavy to initialize, loading the full context also brings those costs and dependencies. Only consider the database or external services tested when the test actually uses those systems.

**Comparing the MockMvc approaches:** standalone is manually built infrastructure; `@WebMvcTest` is a web slice from the Spring context; `@SpringBootTest` is a broader context. They can all return the same JSON in this example, but **what they prove as evidence and why they fail differ**.

## 6. Level 3 — real HTTP through an embedded server

File `src/test/java/com/example/demo/GreetingControllerLiveHttpTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
class GreetingControllerLiveHttpTest {
    @Autowired
    TestRestTemplate client;

    @Test
    void answersActualHttpRequest() {
        ResponseEntity<GreetingController.GreetingDto> response =
                client.getForEntity(
                        "/api/greetings/An",
                        GreetingController.GreetingDto.class
                );

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("Hello, An", response.getBody().message());
    }
}
```

Spring Boot starts an embedded server on a random available port. `TestRestTemplate`, provided by the test environment, sends HTTP requests to that server and knows the running port. Thus the test passes through the HTTP client, loopback network connection, servlet container, filter chain, MVC, and application beans. To create a different client manually (such as `RestClient` or `WebTestClient.bindToServer()`), use a base URL pointing to localhost and the assigned port; client configuration determines whether a real network request is sent.

**A common mistake:** declaring `@SpringBootTest(webEnvironment = RANDOM_PORT)` yet only calling `mockMvc.perform(...)` and claiming “real HTTP was tested.” Starting the server alone does not prove requests are sent to the socket; the **client/execution path of the call** determines the tested boundary.

A real server helps verify issues hard to reproduce with mock Servlets, such as container-dependent behavior, error pages, port configuration, and part of HTTP transport. It still **does not automatically** test reverse proxies, TLS termination, DNS, load balancers, firewalls, production databases, or cloud infrastructure. Those parts require dedicated integration testing environments.

Transaction note: if a test method is marked `@Transactional` when using a real server, the client and server run on different threads/transactions; the test transaction rollback **does not automatically roll back** data changes committed in the server-side request. Use data cleanup mechanisms, a dedicated test database, or appropriate application-side transactions.

## 7. Comparing the same bug and choosing a test level

Suppose a developer accidentally changes `@GetMapping("/{name}")` to `@GetMapping("/fixed")` while keeping the method body unchanged:

- **Calling the controller directly** can still pass because it ignores routing annotations.
- **MockMvc standalone**, **web slice**, and **full-context MockMvc** will detect that `GET /api/greetings/An` no longer reaches the right handler.
- **Real HTTP** also detects the bug; additionally, it can catch server/container/transport bugs that MockMvc cannot reproduce.

Suppose a global `@ControllerAdvice` is registered via application configuration, but a standalone test forgets to add it to the builder. The standalone test may fail to prove the runtime error body/status; a context-based test will have a chance to test the right advice **if the advice is actually loaded**. If security filters are used in production, you must consider the filter chain of each mode; do not assume “MockMvc tests security” just because `mockMvc.perform` is used.

| Question to answer | Suitable starting point | Additional test when needed |
| --- | --- | --- |
| Does the controller pass arguments and pick the right branch? | Direct method call with mocks/stubs | MockMvc if URL and contract matter |
| Are path, query, header, validation, converter, JSON, and status correct? | MockMvc standalone or `@WebMvcTest` | Context-based MockMvc when relying on actual configuration |
| Do `@ControllerAdvice`, filters, interceptors, WebMvcConfigurer, and Security work together? | `webAppContextSetup` / `@WebMvcTest` with proper config | `@SpringBootTest + @AutoConfigureMockMvc` if broader beans are needed |
| Does the controller connect to the app's real services/repositories/config? | `@SpringBootTest + @AutoConfigureMockMvc` | Real HTTP if transport/container also matters |
| Can the endpoint actually receive HTTP on a port and return a response? | `@SpringBootTest(RANDOM_PORT)` + HTTP client | Deployment environment testing for real proxy/TLS/infra |

There is no “higher level is always better” rule for every test. A sensible test suite usually has many fast tests at small boundaries to pinpoint failures clearly, plus context tests to verify wiring, and a few real HTTP tests for representative or high-risk flows. Weigh the cost of initializing the Spring context, container, and external dependencies. Spring TestContext caches contexts for reuse across tests with equivalent configurations, though it does not eliminate integration cost completely.

## 8. Running and reading results

With a Spring Boot 3.3 project declaring `spring-boot-starter-web` and `spring-boot-starter-test`, place each class in the package/file shown above and run:

```bash
./gradlew test
```

On Windows PowerShell you can use `.\gradlew.bat test`. The sample tests assert:

1. Unit: the method returns the expected string and called the service with the right argument.
2. Standalone: the mock MVC request matches the path and JSON response.
3. Web slice: the MVC slice uses the mock service and returns the right status/JSON.
4. Full context: the real service bean is wired through MVC and returns the right response.
5. Live HTTP: the HTTP client receives status 200 and deserializes the JSON returned by the embedded server.

These are **expectations from the example source**, not pre-supplied execution logs. If a test fails to run, check dependencies/versions, security configuration, or context before concluding the controller functionality is broken. When a lesson uses plain Spring Framework without Spring Boot, replace Boot annotations (`@WebMvcTest`, `@SpringBootTest`) with appropriate Spring TestContext configuration.

## 9. Common pitfalls and verification checklist

- **Confusing unit tests with HTTP tests:** calling `controller.greet(...)` directly does not verify route annotations, binding, or serialization.
- **Confusing MockMvc with a real server:** MockMvc processes simulated Servlet requests in memory; it does not prove a network port is open.
- **Confusing a full context with full integration:** a context may contain mock beans or an in-memory/fake datasource; check whether dependencies are real or fake.
- **Standalone missing configuration:** if behavior depends on an exception handler, custom JSON module, interceptor, or security filter, configure the builder manually or switch to a context-based test.
- **Overusing @WebMvcTest for business logic:** collaborators are usually mocked, so the test does not prove real business/service logic works.
- **Using RANDOM_PORT without sending network requests:** choose an HTTP client actually targeting the server; do not call MockMvc as a stand-in for transport.
- **Tests overly coupled to verbatim JSON strings:** if field order/formatting is not a public contract, use JSONPath or parse the body to check meaningful values.
- **Live HTTP tests using persistent data:** isolate state, manage fixtures, and clean up data; be especially careful with transaction rollbacks when client and server are on separate threads.

Before considering a test sufficient, ask: **(1)** which layers did the request pass through? **(2)** was a Spring context loaded and which beans are in it? **(3)** which dependencies are mocks? **(4)** did real TCP/HTTP occur? **(5)** is the assertion proving status, body, authorization, validation, or business outcome? Answers must be grounded in the test's actual setup and calls, not just annotation names.

### References

- Spring Framework — MockMvc overview: https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html
- Spring Framework — MockMvc setup options: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/setup-options.html
- Spring Framework — WebTestClient setup (mock or live server): https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
