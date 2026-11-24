# Simulation Limits vs. a Running Servlet Container

`MockMvc` lets you send simulated HTTP requests into Spring MVC without starting a real Servlet container. It is very useful for testing controllers, routing, parameter binding, validation, exception handlers, filters, and response content in a fast test. However, `MockMvc` requests pass through simulated Servlet API objects in memory; requests do not pass through sockets, HTTP connectors, or the full processing lifecycle of Tomcat, Jetty, or Undertow.

Consequently, a passing `MockMvc` test proves that most of the Spring MVC pipeline is configured and behaves properly in the simulated environment. It does not prove that the application will behave identically when receiving requests through a running Servlet container. When test requirements involve connectors, the HTTP protocol, real cookies, multipart parsing, async I/O, or container deployment settings, you must run the application on a real server and send requests through an HTTP client.

## 1. Which Components Does a Request Pass Through?

In a running environment, a request typically traverses these layers:

```text
HTTP client
    |
    v
Network socket / TLS
    |
    v
Servlet container connector
    |
    v
Servlet container request processing
    |
    v
Servlet Filters
    |
    v
DispatcherServlet
    |
    v
HandlerMapping -> Controller -> Application services
    |
    v
HttpMessageConverter / View rendering
    |
    v
Servlet container response processing
    |
    v
Network socket / HTTP response
```

When using `MockMvc`, Spring Test creates `MockHttpServletRequest`, `MockHttpServletResponse`, and related simulated Servlet objects. The request is handed to `DispatcherServlet` to perform Spring MVC processing:

```text
Test code
    |
    v
MockMvc.perform(...)
    |
    v
MockHttpServletRequest / MockHttpServletResponse
    |
    v
DispatcherServlet
    |
    v
HandlerMapping -> Controller -> Application services
    |
    v
HttpMessageConverter / View rendering
    |
    v
Mock response returned to the test
```

The key point is that `MockMvc` does not bypass Spring MVC. It executes `DispatcherServlet`, handler mappings, argument resolvers, data binding, validation, exception resolvers, interceptors, and message converters according to the configuration supplied to the test. What is simulated is the Servlet API layer wrapping Spring MVC along with the request/response; neither a real container nor a network layer is started.

## 2. What MockMvc Tests Well

### Controller Mapping and Processing

You can verify whether the URL, HTTP method, path variables, query parameters, headers, content type, and other mapping conditions select the right handler.

```java
@RestController
@RequestMapping("/greetings")
class GreetingController {

    private final GreetingService greetingService;

    GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/{name}")
    Greeting greet(@PathVariable String name) {
        return greetingService.greet(name);
    }
}

record Greeting(String message) {
}
```

A slice test can mock the service to focus on the controller's HTTP contract:

```java
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(GreetingController.class)
class GreetingControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    GreetingService greetingService;

    @Test
    void returnsGreetingForTheRequestedName() throws Exception {
        given(greetingService.greet("Lan"))
                .willReturn(new Greeting("Hello, Lan"));

        mockMvc.perform(get("/greetings/{name}", "Lan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, Lan"));
    }
}
```

`@WebMvcTest` loads a web MVC slice and components related to the selected controller. The service is replaced with a mock so the test does not depend on downstream business logic. This is a good way to test request mapping, serialization, and the controller's response contract.

### Binding, Validation, and Data Conversion

MockMvc can test scenarios such as:

- Path variables or query parameters being converted into the right Java types.
- JSON request bodies being deserialized into DTOs.
- Bean Validation catching invalid data.
- `@ControllerAdvice` turning exceptions into the expected status and response body.
- `HttpMessageConverter` selecting formats matching `Content-Type` and `Accept`.
- Headers, status codes, and cookies being set on the simulated response.
- Views being selected and models prepared in the Spring MVC flow.

These checks are valuable because they execute through `DispatcherServlet` and real Spring MVC components in the test context. However, they do not test how the container receives and parses HTTP bytes from the network before the request reaches `DispatcherServlet`.

### Filters and Spring Security

Filters are part of the Servlet pipeline. MockMvc can run filters if they are added to MockMvc. In Spring Boot, `@AutoConfigureMockMvc` adds the application's `Filter` beans to the simulated chain by default; the `addFilters` attribute adjusts this behavior.

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class SecurityMvcTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsAnUnauthenticatedRequest() throws Exception {
        mockMvc.perform(get("/api/private"))
                .andExpect(status().isUnauthorized());
    }
}
```

The example above tests the Spring Security filter chain if the chain is configured and wired into MockMvc. It is useful for testing authorization, authentication entry points, CSRF, and responses produced by security filters. If `addFilters = false` is set, or if `standaloneSetup` is used without adding the filter, the test will not pass through the filter under test.

Even when a filter runs in MockMvc, the test still does not prove that the container registers the filter with the exact URL patterns, dispatcher types, ordering, and mapping rules used in the deployment environment. Real filter registration configuration must be tested at the server tier when that poses a risk to the application.

## 3. Parts MockMvc Does Not Fully Simulate

### Network, Connectors, and the HTTP Protocol

MockMvc does not open TCP ports and does not handle client connections. Therefore it cannot test:

- TLS handshakes, certificates, HTTPS redirects, or cipher configurations.
- HTTP/2, keep-alive, connection reuse, and connection-closing behavior.
- The container's HTTP parser, request lines, raw headers, and malformed HTTP cases.
- Limits on request line length, header size, body size, or header count enforced by the connector.
- Request read timeouts, connection timeouts, and connection limits.
- Response compression, chunked transfer encoding, and how responses are flushed to the network.

For instance, a MockMvc test might send an arbitrarily long header and receive a normal response, whereas a real server connector could reject the request for exceeding the header limit. If you need to verify such limits, send requests to a started server with the corresponding connector configuration and check the status or connection-closing behavior.

### Cookies, Sessions, and Real Request Lifecycles

MockMvc provides `MockHttpSession` and APIs to attach sessions to requests. This works well for testing session read/write logic in the application. However, the test does not by itself prove that the container creates and sends `Set-Cookie`, that clients send the cookie back on the next request, or that session timeouts or session persistence behave as in the real environment.

When you need to verify the real cookie flow, use an HTTP client with a cookie jar or capture `Set-Cookie` from the first response and send `Cookie` in the follow-up request to a running server. If the system uses session replication or a distributed session store, test against the corresponding store configuration.

### Multipart Parsing and Upload Limits

MockMvc supports `multipart(...)` and `MockMultipartFile`, allowing you to test controllers receiving files, part names, metadata, and upload processing results.

```java
mockMvc.perform(multipart("/documents")
                .file(new MockMultipartFile(
                        "file",
                        "notes.txt",
                        "text/plain",
                        "sample content".getBytes(StandardCharsets.UTF_8))))
        .andExpect(status().isCreated());
```

This request is built in memory; it does not test how a real container or multipart resolver parses boundaries from a byte stream over the network, writes temporary files, enforces size limits, handles interrupted uploads, or cleans up temporary files. Multipart limits configured in Spring Boot and the container must be tested with real HTTP requests if they are critical requirements.

### Servlet Mapping, Dispatching, and Container Configuration

The container manages Servlet registration, URL mappings, filter mappings, listeners, dispatcher types, and several deployment rules. MockMvc starts the Spring MVC pieces needed for testing but does not reproduce the entire process of deploying the application into a container.

Differences can arise in:

- The application's context path and servlet path when deployed under a non-root path.
- Filters registered via `FilterRegistrationBean`, `web.xml`, `ServletContextInitializer`, or container-specific configuration.
- Filter ordering and whether filters apply to `REQUEST`, `ASYNC`, `ERROR`, `FORWARD`, or `INCLUDE` dispatches.
- Servlet listeners, session listeners, and container lifecycle callbacks.
- Welcome pages, the default servlet, static resource mappings, forwards/includes, and container error pages.
- JNDI resources, datasources, or components supplied by the container environment.

MockMvc can still set `contextPath`, `servletPath`, or simulate some dispatch types. That helps test Spring MVC logic in those contexts, but it does not replace verifying the actual deployment configuration applied by the container.

### Async, Streaming, and Network Responses

MockMvc supports testing part of Spring MVC's asynchronous requests, such as asserting that a request entered the async state and executing `asyncDispatch` to verify the final result:

```java
MvcResult result = mockMvc.perform(get("/reports/async"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(result))
        .andExpect(status().isOk());
```

This is a useful test for the Spring MVC async flow. It does not verify how the container manages async I/O, timeouts, executors, client disconnects, backpressure, streaming, or incremental response flushing over a socket.

If an endpoint uses `StreamingResponseBody`, `SseEmitter`, streaming JSON, or large payloads, add a test sending HTTP requests to a real server. That test can read responses incrementally, verify received events, check timeouts, and observe behavior when the client closes the connection.

## 4. Distinguishing Spring Boot Test Types

Annotation names can mislead you into thinking every Spring test runs a real server. Look at `webEnvironment` and how requests are sent.

| Setup | Application Context | Real Servlet Container? | How Requests Are Sent |
|---|---|---|---|
| `@WebMvcTest` | Web MVC slice | No | Inject `MockMvc`. |
| Default `@SpringBootTest` | Full application context with a simulated web environment | No | Can be combined with `@AutoConfigureMockMvc`. |
| `@SpringBootTest(webEnvironment = MOCK)` + `@AutoConfigureMockMvc` | Full application context with a mock web environment | No | `MockMvc`. |
| `@SpringBootTest(webEnvironment = RANDOM_PORT)` | Full application context | Yes, embedded server started | HTTP client such as `TestRestTemplate` or `RestClient`. |
| `@SpringBootTest(webEnvironment = DEFINED_PORT)` | Full application context | Yes, embedded server listens on configured port | HTTP client targeting that port. |

For example, `@SpringBootTest` combined with `@AutoConfigureMockMvc` still sends requests via MockMvc. Loading all application beans does not turn MockMvc into an HTTP client, nor does it start an embedded server automatically.

To test requests through an embedded container, use `RANDOM_PORT`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GreetingHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void servesGreetingThroughTheEmbeddedServletContainer() {
        ResponseEntity<String> response =
                http.getForEntity("/greetings/Lan", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).contains("Hello, Lan");
    }
}
```

Spring Boot starts an embedded server on a random port and configures `TestRestTemplate` to call that application. Requests traverse the HTTP stack and running Servlet container, so the test can uncover many issues MockMvc cannot see. A random port also allows multiple test contexts to run in parallel with minimal fixed-port collisions.

If you prefer `RestClient`, you can build a client pointing to the host and port injected via `@LocalServerPort`. With `TestRestTemplate`, Spring Boot already configures the base URL for the test server.

## 5. Choosing the Test Level by Risk

You do not need to move every controller test to a real server. Starting a container slows tests down and increases resource cost. Choose tools based on the behavior that needs to be proven.

| Goal | Suitable Test Approach |
|---|---|
| URL mapping, status, JSON, validation, exception advice | `@WebMvcTest` + MockMvc. |
| Controller interaction with services, repositories, and app config | `@SpringBootTest` + MockMvc, depending on the scope to load. |
| Spring Security filter chain and filter responses | MockMvc with filters fully configured; add server tests if registration or dispatch mapping must be verified. |
| Connectors, HTTP parser, header/body limits, TLS, HTTP/2 | HTTP client calling a real server with matching configuration. |
| Cookies across multiple requests, session cookies, and real multipart uploads | HTTP client calling a real server. |
| Async I/O, streaming, SSE, client disconnects, or response flushing | HTTP client calling a real server; verify timing and chunked data as needed. |
| Differences between embedded container and external deploy environment | Run tests in the target deployment container/environment. |

A practical strategy can consist of three tiers:

1. **MVC slice tests:** numerous, fast, verifying each controller's contract.
2. **Application integration tests:** moderate in number, loading the full context and using MockMvc to verify wiring, security, and bean interactions.
3. **Real-server tests:** focused on container- or HTTP-transport-dependent behaviors, running against an embedded server or the actual deployment container.

These tiers provide complementary evidence. MockMvc isolates Spring MVC bugs quickly; server tests verify the application starts up and serves requests through a real container.

## 6. Limitations of Embedded Server Tests

`RANDOM_PORT` tests the embedded container that the application starts during tests. If production uses the same container type and equivalent configuration, this provides closer evidence to the live environment than MockMvc.

However, embedded server tests do not by themselves prove that production is identical. Several differences can exist outside the application process:

- Reverse proxies, ingress controllers, load balancers, and TLS termination.
- DNS, firewalls, network policies, and hosting platform limits.
- External Tomcat/Jetty/Undertow configuration if production deploys a WAR into a separately managed container.
- Secrets, JNDI, volumes, file permissions, environment variables, and platform-provided resources.
- Multi-instance scaling settings, session replication, and load balancing.

If the application runs inside an external Tomcat, tests with embedded Tomcat do not verify every rule of that external Tomcat. When an issue appears only after deployment, create tests or smoke tests in the exact container type and configuration close to production, and test through the proxy as well if requests pass through one.

## 7. Example: One Requirement, Two Test Tiers

Suppose a document upload endpoint must:

- Return `201 Created` when the file is valid.
- Reject files larger than the configured limit.
- Record metadata and return JSON.

MockMvc is well suited to verifying that the controller receives the right `file` part, calls the service, and returns JSON matching the contract. You can send `MockMultipartFile` for valid files, missing parts, or invalid metadata.

A real HTTP test complements this by sending a multipart request with boundaries through the connector and confirming the upload limit is actually enforced. That test should use a file exceeding the threshold and assert the status/response according to the configured policy. If the limit is enforced at a reverse proxy before requests reach the application, test through the corresponding proxy; calling the embedded server directly will not verify that proxy layer.

Similarly, for endpoints requiring login, MockMvc can verify authorization and CSRF filter logic. A real server test can verify that the session cookie is issued, sent back, and maintains state across two HTTP requests. If production uses SSO or an authenticating proxy, add tests at that integration boundary.

## 8. Common Misconceptions

### "MockMvc returns an HTTP response, so it definitely tested the HTTP server"

MockMvc's response comes from `MockHttpServletResponse`. It exposes status, headers, cookies, and body for assertions, but it is not a response written over a socket by a connector. In-memory response structures do not prove how the server encodes or transmits responses over the network.

### "Using `@SpringBootTest` means a web server was started"

Not true in all cases. `@SpringBootTest` defaults to a simulated web environment. When combined with `@AutoConfigureMockMvc`, tests still send requests via MockMvc. To start an embedded server, choose `RANDOM_PORT` or `DEFINED_PORT`.

### "MockMvc cannot test filters or security"

MockMvc can run filters and the Spring Security filter chain when they are added to the MockMvc setup. What must be distinguished is executing filter logic in the simulated chain versus verifying the container's filter registration, URL patterns, dispatcher types, and real ordering.

### "Testing async with asyncDispatch equals testing async on a server"

`asyncDispatch` verifies async processing results within the Spring MVC test model. It does not fully simulate the executors, sockets, timeouts, streaming, and client disconnects of a live container serving requests.

### "Embedded server tests are absolute proof of production"

An embedded server represents only the server and configuration started in the test. If production has proxies, external containers, TLS termination, or platform-specific resources, those components must be tested at the appropriate deployment tier.

## 9. How to Interpret Test Results

When a MockMvc test fails, check whether the request selected the right handler, which filters ran, which exception resolver handled errors, and how the simulated response was built. This is the scope where MockMvc gives a very strong signal.

When MockMvc passes yet real requests fail, inspect the layers before and after `DispatcherServlet`: connector, TLS, HTTP parsing, filter registration, servlet mapping, multipart parsing, session cookies, async transport, and proxies. The contrast between the two outcomes usually reveals whether the issue lies in Spring MVC or in the Servlet/HTTP environment.

When designing tests, state clearly which behavior is being proven. For example, "controller returns `413 Payload Too Large` when the service rejects the file" differs from "container rejects a request exceeding the multipart limit before the controller is invoked." Both behaviors may return the same status code yet originate at two different layers and require two different types of tests.

## 10. Checklist for Choosing MockMvc vs. a Real Server

- [ ] Is the goal only to test Spring MVC mapping, binding, validation, or response contracts? Use MockMvc.
- [ ] Need to load the full application context without needing HTTP transport? Use `@SpringBootTest` with MockMvc.
- [ ] Need to prove requests go through the connector and Servlet container? Use `RANDOM_PORT` or `DEFINED_PORT` with an HTTP client.
- [ ] Need to test TLS, HTTP/2, connector limits, or the HTTP parser? Use a real server with matching connector configuration.
- [ ] Need to test cookies/sessions across multiple requests or real multipart parsing? Use a real server.
- [ ] Need to test async streaming, flushing, timeouts, or client disconnects? Use a real server.
- [ ] Does production have a reverse proxy or external container? Add tests in that exact environment when behavior depends on it.
- [ ] Does the MockMvc test include the necessary filters in the simulated chain?
- [ ] Does the test accurately describe the layer it is verifying?

`MockMvc` is a highly effective tool for testing Spring MVC because it runs `DispatcherServlet` without opening a server. Its limits lie in behaviors handled by the Servlet container, connectors, and network. Combining MockMvc for the MVC layer with targeted real-HTTP tests for container risks yields a fast, clearly scoped test suite with the right evidence for your application's runtime environment.
