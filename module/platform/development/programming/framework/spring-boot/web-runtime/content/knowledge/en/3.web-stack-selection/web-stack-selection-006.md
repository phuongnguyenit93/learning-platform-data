# Using WebClient in an MVC Application Without Changing the Server Model

Spring MVC and WebClient solve two different problems. **Spring MVC** receives requests from browsers or clients, maps URLs to controllers, and produces responses via the Servlet model. **WebClient** is an HTTP client used by the application to proactively call an external service.

Therefore, an application can continue running Spring MVC on Tomcat/Jetty/Undertow while using WebClient to call other REST APIs. Adding the WebFlux library to use WebClient does not mean switching the server to WebFlux. Spring Boot recognizes both stacks and prioritizes Spring MVC when both are present.

This lesson explains how to choose dependencies, configure WebClient, call services from MVC controllers/services, manage timeouts and errors, write tests, and avoid situations that could accidentally switch the application to a reactive server.

## 1. Distinguishing the server stack and the HTTP client

A web application typically has two communication directions:

- **Inbound (requests entering the application)**: a browser or client calls the application's endpoints. Spring MVC uses the Servlet API to accept requests, execute controllers, and write responses.
- **Outbound (requests leaving the application)**: a controller or service calls another API. WebClient constructs an HTTP request, sends it to the target system, and converts the response into Java objects.

These two directions are independent. Choosing WebClient for outbound calls does not force the inbound server to use WebFlux.

| Component | Role | Example |
|---|---|---|
| Spring MVC | Handles incoming HTTP requests following the Servlet model | **@RestController**, **@GetMapping**, **DispatcherServlet** |
| Servlet container | Server accepting requests for the MVC application | Tomcat, Jetty, Undertow |
| WebClient | Sends HTTP requests from the application to another service | GET catalog, POST payment, calling an identity provider |
| WebFlux server | Reactive web stack handling incoming requests | **DispatcherHandler**, reactive server such as Reactor Netty |

A request can travel through this flow:

~~~text
Browser / API client
        |
        | HTTP request
        v
Servlet container (Tomcat)
        |
        v
Spring MVC Controller
        |
        v
Application Service
        |
        | WebClient: outbound HTTP request
        v
Remote REST API
        |
        | HTTP response
        v
WebClient -> Service -> MVC Controller
        |
        v
Servlet response
~~~

Key takeaway: WebClient is a client API. WebFlux is a web framework that can be used on the server side. Using the WebClient library together with Spring MVC is a scenario supported by Spring Boot.

## 2. Required dependencies

If the project already has Spring MVC via **spring-boot-starter-web**, add **spring-boot-starter-webflux** to get WebClient and the required reactive components.

**Gradle (Groovy):**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

If **spring-boot-starter-web** is already present, simply add the WebFlux dependency and keep the MVC dependency as is.

**Maven:**

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Dependency versions are managed by the project's Spring Boot parent or BOM. Do not add custom versions for individual Spring libraries when the project already uses Boot's dependency management.

### 2.1. Why does the application still run MVC after adding WebFlux?

When both Spring MVC and WebFlux are on the classpath, Spring Boot configures **Spring MVC** by default. This decision enables MVC applications to use WebClient without changing their server stack.

In this situation:

- **spring-boot-starter-web** provides Spring MVC and the Servlet container.
- **spring-boot-starter-webflux** provides WebClient, Reactor, and WebFlux components.
- Boot detects MVC and chooses the Servlet model as the web application type.
- MVC controllers, **DispatcherServlet**, and embedded Tomcat continue working as before.

You do not need to add **@EnableWebFlux** just to use WebClient. Nor should you set **spring.main.web-application-type=reactive** if your goal is to keep the Servlet server. If the project explicitly configures the application type, verify that it remains **servlet**.

You can confirm via startup logs: an MVC application typically starts embedded Tomcat and registers **DispatcherServlet**. If you see the application starting a reactive web server, inspect dependencies, the **spring.main.web-application-type** property, and custom web configurations.

## 3. How does WebClient work?

WebClient provides a fluent API to describe an HTTP request. The request is not sent until the reactive publisher is subscribed to. Operators such as **retrieve()**, **bodyToMono()**, and **timeout()** build the response-processing pipeline.

A simple GET:

~~~java
Mono<CatalogItem> result = webClient.get()
        .uri("/items/{id}", 42)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToMono(CatalogItem.class);
~~~

Explanation:

1. **get()** selects the GET HTTP method.
2. **uri(...)** constructs the URI and substitutes path parameters.
3. **accept(...)** declares the response media type expected by the application.
4. **retrieve()** prepares to send the request and handle the response.
5. **bodyToMono(...)** converts the response body into an asynchronous object.

For requests requiring a body, you can use **bodyValue()**:

~~~java
Mono<CatalogItem> created = webClient.post()
        .uri("/items")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateCatalogItemRequest("Keyboard"))
        .retrieve()
        .bodyToMono(CatalogItem.class);
~~~

WebClient supports headers, query parameters, path variables, request bodies, filters, codecs, and various response types. Create a reusable client rather than instantiating a new one on every request to a controller.

## 4. Configuring a shared WebClient

Spring Boot auto-configures a **WebClient.Builder** when WebFlux is on the classpath. This builder can receive customizers and codec/observation settings managed by Boot. Inject the builder and build a dedicated WebClient for the target service.

Example structure:

~~~text
com.example.shop
├── ShopApplication.java
├── catalog
│   ├── CatalogClientConfiguration.java
│   ├── CatalogClientProperties.java
│   ├── CatalogClient.java
│   ├── CatalogController.java
│   └── CatalogItem.java
└── application.yml
~~~

**CatalogClientProperties.java**

~~~java
package com.example.shop.catalog;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "clients.catalog")
public record CatalogClientProperties(String baseUrl) {
}
~~~

**CatalogClientConfiguration.java**

~~~java
package com.example.shop.catalog;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogClientProperties.class)
public class CatalogClientConfiguration {

    @Bean
    WebClient catalogWebClient(
            WebClient.Builder builder,
            CatalogClientProperties properties) {

        return builder.clone()
                .baseUrl(properties.baseUrl())
                .build();
    }
}
~~~

Use **clone()** to configure a dedicated builder for this client without mutating the builder injected elsewhere. Once built, a WebClient can be reused across requests; it is designed to be immutable and safe to share.

**application.yml**

~~~yaml
server:
  port: 8080

clients:
  catalog:
    base-url: http://localhost:9090
~~~

In this example, the MVC application runs on port 8080 and the Catalog service runs on port 9090. Real addresses should be supplied via environment-specific configuration, such as environment variables or deployment profiles, rather than hard-coded in services.

If you need multiple services, create a separate WebClient bean per upstream to manage base URLs, authentication headers, filters, and timeouts per service. Avoid using a single global base URL for systems with different connection policies.

## 5. Calling WebClient from an MVC service in imperative style

In traditional MVC applications, services usually accept and return plain Java objects. You can use WebClient inside the service and await the result with **block()** at the boundary between the reactive client and imperative code.

**CatalogItem.java**

~~~java
package com.example.shop.catalog;

public record CatalogItem(long id, String name) {
}
~~~

**CatalogClient.java**

~~~java
package com.example.shop.catalog;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(
            @Qualifier("catalogWebClient") WebClient webClient) {
        this.webClient = webClient;
    }

    public CatalogItem findById(long id) {
        return findByIdAsync(id).block(Duration.ofSeconds(4));
    }

    public Mono<CatalogItem> findByIdAsync(long id) {
        return webClient.get()
                .uri("/items/{id}", id)
                .retrieve()
                .bodyToMono(CatalogItem.class)
                .timeout(Duration.ofSeconds(3));
    }
}
~~~

In this example:

- **findByIdAsync()** returns **Mono<CatalogItem>**, preserving WebClient's reactive API.
- **timeout(Duration.ofSeconds(3))** bounds how long the publisher waits for a response.
- **findById()** calls **block(Duration.ofSeconds(4))** to return a Java object to imperative code.
- The block duration limit is longer than the publisher timeout to avoid indefinite waiting if an issue occurs in the pipeline.

When the upstream returns HTTP 4xx or 5xx, **retrieve()** raises **WebClientResponseException** by default. Connection or request errors can raise **WebClientRequestException**; Reactor timeouts raise a timeout error. The application should translate these errors into meaningful integration errors, log them safely, and return an appropriate HTTP status to callers. Do not expose raw internal error details or sensitive upstream data externally.

**block()** causes the current Servlet thread to wait for the result. This is straightforward and suitable when keeping services/controllers imperative, though while waiting, that thread cannot process other requests. Set timeouts and concurrency limits suited to the MVC thread pool size and upstream capacity.

Do not call **block()** inside a reactive pipeline or on a WebFlux/Reactor Netty event-loop thread. In those contexts, blocking can throw an error or stall the event loop.

## 6. MVC controllers still return plain objects

Controllers can continue using imperative services as before.

**CatalogController.java**

~~~java
package com.example.shop.catalog;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/catalog")
public class CatalogController {

    private final CatalogClient catalogClient;

    public CatalogController(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    @GetMapping("/{id}")
    public CatalogItem getItem(@PathVariable long id) {
        return catalogClient.findById(id);
    }
}
~~~

When a client sends:

~~~http
GET /api/catalog/42 HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

MVC receives the request, invokes **CatalogController**, the service uses WebClient to call **http://localhost:9090/items/42**, receives JSON, and decodes it into **CatalogItem**. The controller then returns the object so the MVC message converter writes the JSON response.

Example response:

~~~json
{
  "id": 42,
  "name": "Keyboard"
}
~~~

Inbound requests are still handled by the Servlet container and Spring MVC. WebClient only performs the outbound call to the Catalog API.

## 7. Using WebClient asynchronously while keeping Spring MVC

If you want to avoid holding a Servlet thread while waiting for an upstream, you can return **Mono** from an MVC controller:

~~~java
@GetMapping("/async/{id}")
public Mono<CatalogItem> getItemAsync(@PathVariable long id) {
    return catalogClient.findByIdAsync(id);
}
~~~

Spring MVC recognizes reactive return types such as **Mono** via reactive adapters and handles the result using Servlet asynchronous request processing. The request still enters **DispatcherServlet** and the server remains on the Servlet stack; there is no need to migrate the whole application to WebFlux.

Difference between the two approaches:

| Invocation style | Controller return type | Waiting behavior |
|---|---|---|
| Imperative | **CatalogItem** | Servlet thread waits for the result at **block()** |
| MVC async | **Mono<CatalogItem>** | MVC starts async processing and completes the response when the publisher emits the result |

Use the imperative style when existing code is structured synchronously and traffic fits. Use the async style when you want to leverage non-blocking I/O waiting, especially when making multiple concurrent outbound calls. Both are still Spring MVC.

Do not convert parts of your code to reactive solely to use WebClient. If you choose to return **Mono**, keep the pipeline reactive across the asynchronous segment; do not call **block()** and wrap the result back into **Mono.just()**, as that negates async processing benefits.

## 8. Timeouts, connection pools, and resource limits

Request timeouts should be designed across multiple layers:

- **Connect timeout**: limits the time to establish a TCP connection.
- **Response timeout**: limits the time waiting for response data at the HTTP client configuration level.
- **Publisher timeout**: limits how long the reactive pipeline waits for completion.
- **MVC request timeout**: limits server-side request processing time if the application configures this mechanism.

**Mono.timeout(...)** bounds the publisher duration, while **block(Duration)** bounds how long the caller waits. These two limits do not fully replace transport-level connection settings. For production systems, configure connect/response timeouts and connection pools suitable for the HTTP connector library in use.

If the application uses Reactor Netty, you can customize the connector using **ReactorClientHttpConnector** and **HttpClient**. Example transport configuration snippet:

~~~java
HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
        .responseTimeout(Duration.ofSeconds(3));

WebClient webClient = builder.clone()
        .baseUrl(baseUrl)
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
~~~

This snippet requires imports from Netty and Reactor Netty:

~~~java
import io.netty.channel.ChannelOption;
import java.time.Duration;
import reactor.netty.http.client.HttpClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
~~~

When supplying a custom connector, re-check TLS, proxy, metrics, tracing, and connection pool settings used by your application. If Boot or your deployment platform customized the connector, replacing the connector can drop some of those settings. Preserve any required customizers when creating a custom transport.

Do not set excessively long timeouts just to mask upstream errors. Timeouts must align with SLAs, endpoint processing time, and the inbound request's time budget. If a request calls multiple upstreams sequentially, total wait time must stay within what the calling client accepts.

## 9. Handling HTTP statuses and upstream errors

WebClient provides two common APIs for reading responses:

- **retrieve()**: suitable for standard flows; 4xx/5xx statuses are converted into exceptions by default.
- **exchangeToMono()** or **exchangeToFlux()**: used when branching on status/headers and taking direct control of body reading.

Example using **onStatus()** to customize errors:

~~~java
return webClient.get()
        .uri("/items/{id}", id)
        .retrieve()
        .onStatus(
                status -> status.is4xxClientError(),
                response -> response.createException()
        )
        .onStatus(
                status -> status.is5xxServerError(),
                response -> response.createException()
        )
        .bodyToMono(CatalogItem.class);
~~~

The example preserves default exception types while showing where behavior can be customized per status group. If you need to map an upstream 404 to a specific business outcome, map the status here or at the service boundary.

An error-handling policy should distinguish:

- **4xx from upstream**: the request sent to the upstream was invalid or the resource does not exist. Depending on contract, map to a business error or gateway error.
- **5xx from upstream**: the upstream failed; usually represented as a service dependency failure.
- **Network error**: DNS, connection refused, TLS, or closed connection.
- **Timeout**: upstream responded too slowly or connection did not complete within the time budget.
- **Decode error**: body does not match the data type or JSON is invalid.

Do not retry every error automatically. Retries can help with transient errors and idempotent operations, but retrying a POST that creates an order or payment can cause duplicate execution without idempotency keys and deduplication mechanisms. When retrying, bound the attempt count, backoff, jitter, and total duration.

You can use **@ControllerAdvice** to translate integration exceptions into consistent API responses. Logs should include correlation ID, upstream name, method, sanitized path, status, and duration; avoid logging Authorization headers, cookies, tokens, or sensitive data in response bodies.

## 10. Sending headers, query parameters, and bodies

WebClient supports building requests to fit each requirement.

**Query parameters:**

~~~java
webClient.get()
        .uri(uriBuilder -> uriBuilder
                .path("/items")
                .queryParam("category", "keyboard")
                .queryParam("page", 0)
                .build())
        .retrieve()
        .bodyToFlux(CatalogItem.class);
~~~

**Per-request headers:**

~~~java
webClient.get()
        .uri("/profile")
        .headers(headers -> headers.setBearerAuth(accessToken))
        .retrieve()
        .bodyToMono(Profile.class);
~~~

Do not hard-code tokens in source code or application.yml committed to a repository. Credentials should come from a secret manager or environment secret management.

**POST JSON:**

~~~java
webClient.post()
        .uri("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(createOrderRequest)
        .retrieve()
        .bodyToMono(OrderResponse.class);
~~~

If the body is a collection or generic type, use **ParameterizedTypeReference** to preserve type information when decoding:

~~~java
ParameterizedTypeReference<List<CatalogItem>> itemListType =
        new ParameterizedTypeReference<>() {};

Mono<List<CatalogItem>> items = webClient.get()
        .uri("/items")
        .retrieve()
        .bodyToMono(itemListType);
~~~

Build URIs using templates or **UriBuilder** instead of manual string concatenation, especially when query parameters contain spaces, Unicode characters, or characters needing URL encoding.

## 11. Configuring shared authentication and filters

If all requests to an upstream need the same header or correlation ID, you can add a filter when constructing the client:

~~~java
WebClient webClient = builder.clone()
        .baseUrl(baseUrl)
        .filter((request, next) -> {
            ClientRequest updated = ClientRequest.from(request)
                    .header("X-Application", "shop-api")
                    .build();
            return next.exchange(updated);
        })
        .build();
~~~

Filter requires import:

~~~java
import org.springframework.web.reactive.function.client.ClientRequest;
~~~

Filters can be used for correlation IDs, logging metadata, authentication, or metrics. Avoid logging full bodies/tokens and avoid modifying headers that could invalidate request signatures.

For OAuth2, Spring Security provides integrations for OAuth2 Client and WebClient. Use proper access-token/refresh-token management rather than writing ad-hoc token issuance and renewal logic in a simple filter.

If each request needs the current user's token, explicitly define whether the token is retrieved from SecurityContext, OAuth2AuthorizedClient, or a credential service. Do not use a single application-wide static token in place of individual user identities.

## 12. Testing an MVC application with outbound WebClient

Test the two boundaries separately:

**Testing the MVC controller:** mock **CatalogClient** to verify URLs, statuses, and JSON responses exposed by your application. This test does not need to call the real Catalog service.

**Testing WebClient integration:** run an HTTP mock server such as WireMock or OkHttp MockWebServer, point the base URL to the mock server, and verify request method, path, headers, body, status, and response decoding.

Important test cases:

- 200 response with valid JSON decodes into the DTO.
- 404/500 responses map to appropriate errors.
- Server down or closed connection produces a clear integration error.
- Slow server triggers the configured timeout.
- Invalid JSON is handled as a decode error.
- Authentication headers and correlation IDs are sent properly and not logged.
- MVC controllers are still tested with MockMvc.
- If a controller returns Mono, verify that the MVC async request completes and returns the expected response.

Example controller test with MockMvc using Mockito to stub the service:

~~~java
@WebMvcTest(CatalogController.class)
class CatalogControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    CatalogClient catalogClient;

    @Test
    void returnsCatalogItem() throws Exception {
        given(catalogClient.findById(42))
                .willReturn(new CatalogItem(42, "Keyboard"));

        mockMvc.perform(get("/api/catalog/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.name").value("Keyboard"));
    }
}
~~~

This example uses **@MockitoBean** from newer Spring Framework versions; in older Spring Boot/Spring Framework versions, projects may use **@MockBean**. Add the corresponding static imports for **given**, **get**, **status**, and **jsonPath**. If a test only verifies the controller, there is no need to load WebClient configuration or connect to a real upstream.

## 13. Common issues

| Symptom | Possible cause | Resolution |
|---|---|---|
| Added WebFlux, but application starts a reactive server | MVC dependency missing, application type set to reactive, or custom web config | Check both starters and **spring.main.web-application-type**; keep **servlet** if intended |
| Cannot inject **WebClient.Builder** | WebFlux not on classpath or auto-configuration excluded | Add the appropriate starter and check auto-configuration conditions |
| Controller waits too long after calling API | Missing timeout or slow upstream | Configure timeouts on both the publisher and transport layers |
| MVC threads held during API calls | Calling **block()** on request thread | Bound timeouts/concurrency or return a reactive type for MVC async handling |
| 4xx/5xx errors turn into generic 500s | Upstream exceptions not mapped at service/API boundary | Classify statuses and map to intentional API errors |
| JSON fails to decode | Mismatched Content-Type, JSON structure, or DTO | Inspect actual response, codecs, and data types |
| Shared builder mutated unexpectedly | Multiple configs mutate the same builder | Clone the builder before configuring a specific client |
| A new WebClient is created per request | Client instantiated inside controller or request-handling method | Register WebClient as a reusable bean |
| Retries create duplicate orders/payments | Retrying non-idempotent operations | Use idempotency keys and bounded retry policies |
| Upstream calls fail after custom connector config | New connector dropped TLS/proxy/pool or observability config | Check transport settings and retain required customizers |

## 14. Deployment checklist

Before introducing WebClient into an MVC application, confirm:

1. The project still includes **spring-boot-starter-web** and only adds WebFlux for client needs.
2. Boot detects the application as Servlet/MVC; embedded server and **DispatcherServlet** are still initialized.
3. WebClient is built from the configured **WebClient.Builder** and reused.
4. Base URLs, credentials, and environment-specific headers are externalized outside source code.
5. Appropriate connect/response/publisher timeouts are configured.
6. Status, network, timeout, and decode errors are categorized.
7. Do not block on an event loop; if calling **block()** in MVC, account for thread occupancy.
8. Retries apply only to appropriate operations and are bounded.
9. Logs exclude tokens, cookies, and sensitive data.
10. Separate MVC tests and HTTP client tests with a mock upstream are in place.

## 15. Key takeaways

Spring MVC handles incoming requests using the Servlet model; WebClient sends outgoing requests using a reactive API. Both can coexist in a single Spring Boot application. When adding **spring-boot-starter-webflux** alongside **spring-boot-starter-web**, Boot prioritizes MVC by default when both stacks are present.

For imperative code, you can call **Mono.block()** at the service boundary with a bounded wait time. For asynchronous needs, MVC can accept **Mono** and complete responses via Servlet async processing while keeping the MVC server. Configure reusable clients, timeouts, connection pools, error handling, and upstream tests so integrations remain stable in production.
