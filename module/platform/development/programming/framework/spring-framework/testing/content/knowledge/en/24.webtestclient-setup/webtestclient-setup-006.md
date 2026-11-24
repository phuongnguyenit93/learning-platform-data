# MockMvcWebTestClient for Using the Same Testing API with MVC

Spring provides `MockMvcWebTestClient` to test Spring MVC applications using the fluent API of `WebTestClient`. This lets you write requests and assertions in a unified client style, while server-side processing still executes through MockMvc and Servlet MVC.

The key point is that `MockMvcWebTestClient` acts as a bridge: the test calls `WebTestClient`, but requests are executed by MockMvc. As a result, you can use familiar assertions such as status, headers, body, and JSONPath; when needed, you can also extract the result to verify MVC-specific details such as handler, model, or view using MockMvc matchers.

## 1. Why Is MockMvcWebTestClient Needed?

Spring has two common HTTP testing APIs:

- **MockMvc** provides an API that simulates Servlet requests and responses. It fits Spring MVC and offers deep matchers for handlers, models, views, sessions, flash attributes, and many Servlet request details.
- **WebTestClient** provides an HTTP-client-style testing API: build a request, call `exchange()`, and verify status, headers, and body. This API is commonly used with Spring WebFlux and can also be used with Spring MVC through `MockMvcWebTestClient`.

If a project has multiple modules or applications using both MVC and WebFlux, using the same client API style makes test organization more consistent. A helper that verifies JSON responses can accept `WebTestClient` without needing to know whether requests are sent to a real WebFlux server or routed through MockMvc.

For MVC, `MockMvcWebTestClient` still uses the MockMvc infrastructure. It does not turn Servlet controllers into WebFlux controllers and does not start a real HTTP server.

## 2. Architecture of the Bridge

Processing flow when using `MockMvcWebTestClient`:

~~~text
Test code
   |
   v
WebTestClient fluent API
   |
   v
MockMvcWebTestClient bridge
   |
   v
MockMvc
   |
   v
DispatcherServlet / Spring MVC
   |
   v
Controller, filters, interceptors, converters
   |
   v
Mock HTTP response
   |
   v
WebTestClient response assertions
~~~

Typical steps in a test:

1. Create the client using `MockMvcWebTestClient.bindToController(...)` or `bindToApplicationContext(...)`.
2. Build the request using `client.get()`, `client.post()`, `uri(...)`, `header(...)`, `bodyValue(...)`, or corresponding APIs.
3. Call `exchange()` to execute the request through MockMvc.
4. Verify the response using `expectStatus()`, `expectHeader()`, `expectBody()`.
5. If MVC-specific assertions are needed, call `returnResult()` to get the exchange result and pass it to `MockMvcWebTestClient.resultActionsFor(...)`.

The two assertion layers serve different purposes: WebTestClient verifies what the client sees via the HTTP response; MockMvc matchers additionally inspect internal details of MVC processing.

## 3. Creating a Client with bindToController

`bindToController(...)` is suitable when you want to test one or a few standalone controllers without building the full Spring application context.

Example controller:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GreetingController {

    @GetMapping("/greeting")
    Greeting greeting() {
        return new Greeting("Hello MVC");
    }
}

record Greeting(String message) {}
~~~

Create a WebTestClient backed by MockMvc:

~~~java
import org.springframework.test.web.servlet.client.MockMvcWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient client = MockMvcWebTestClient
    .bindToController(new GreetingController())
    .build();
~~~

Call the endpoint and verify the response:

~~~java
import org.springframework.http.MediaType;

client.get()
    .uri("/greeting")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.message").isEqualTo("Hello MVC");
~~~

Here, the test does not call `MockMvc.perform(...)`. It uses the WebTestClient API from start to finish. `MockMvcWebTestClient` forwards that request to MockMvc for Spring MVC to handle.

### When to use bindToController?

Choose this approach when:

- The test focuses on a single controller's mappings and responses.
- You do not need all beans or configuration from the application context.
- You want an isolated, lightweight test with explicit configuration.
- You can supply the controller's dependencies directly via constructor or mocks.

If the controller needs services, repositories, or other components, pass mock dependencies into the controller when instantiating it, or switch to binding with an application context if you want Spring to manage wiring.

## 4. Creating a Client with bindToApplicationContext

In real applications, controllers often depend on many Spring MVC components: dependency injection, controller advice, message converters, interceptors, formatters, validators, and other web configurations. When you want to test alongside that configuration, use `bindToApplicationContext(...)`.

Example with Spring Boot:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.test.web.servlet.client.MockMvcWebTestClient;

@WebMvcTest(GreetingController.class)
class GreetingControllerTest {

    @Autowired
    WebApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = MockMvcWebTestClient
            .bindToApplicationContext(applicationContext)
            .build();
    }

    @Test
    void returnsGreeting() {
        client.get()
            .uri("/greeting")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("Hello MVC");
    }
}
~~~

`@WebMvcTest` creates a test slice focused on Spring MVC. The application context is injected into the test and then used to build the client. For controllers with service dependencies, use the mock bean mechanism appropriate for your Spring Boot version to provide those dependencies to the context.

In tests requiring full application configuration, you can use `@SpringBootTest` with a web application context. Whether the created context is broad or narrow, the core idea remains that the client is bound to the MVC context via `MockMvcWebTestClient`.

## 5. Comparing the Two Initialization Modes

| Criterion | `bindToController(...)` | `bindToApplicationContext(...)` |
|---|---|---|
| Scope | One or a few specified controllers. | MVC components registered in the ApplicationContext. |
| Dependency injection | Dependencies can be passed into the controller on instantiation. | Spring retrieves controllers and dependencies from the context. |
| Controller advice | Requires extra configuration if needed. | Uses advice registered in the context. |
| Interceptors, converters, validators | Configured via the builder if needed. | Uses the MVC configuration in the context. |
| Speed and isolation | Usually lighter and more isolated. | Reflects application configuration more closely, but the context is broader. |
| Purpose | Focused controller testing. | Testing controllers within the application's MVC configuration. |

No single option fits every test. Choose the smallest scope that still includes the components on which the tested behavior depends.

## 6. Using WebTestClient to Build Requests

After creating the client, the request-building API looks very similar to calling an HTTP client:

~~~java
client.get()
    .uri("/products?page=2")
    .header("X-Client-Id", "test-client")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk();
~~~

Commonly used methods:

| API | Purpose |
|---|---|
| `get()`, `post()`, `put()`, `patch()`, `delete()` | Select the HTTP method. |
| `uri(...)` | Set the path and query string. |
| `header(name, value)` | Add a request header. |
| `headers(consumer)` | Configure multiple headers. |
| `cookie(name, value)` | Add a cookie. |
| `accept(mediaType)` | Set the Accept header. |
| `contentType(mediaType)` | Set the Content-Type. |
| `bodyValue(value)` | Provide an object to encode as the request body. |
| `body(...)` | Provide a publisher or body inserter. |
| `exchange()` | Send the request through the configured binding and obtain a response spec. |

POST JSON example:

~~~java
client.post()
    .uri("/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .bodyValue(new CreateOrderRequest("BOOK-01", 2))
    .exchange()
    .expectStatus().isCreated()
    .expectHeader().exists("Location")
    .expectBody()
    .jsonPath("$.status").isEqualTo("CREATED");
~~~

Query parameter example:

~~~java
client.get()
    .uri(uriBuilder -> uriBuilder
        .path("/products")
        .queryParam("keyword", "spring")
        .queryParam("page", 2)
        .build())
    .exchange()
    .expectStatus().isOk();
~~~

The convenience is that tests describe requests from the client's perspective. It also makes it easier to reuse request-building or assertion helpers across tests that use WebTestClient.

## 7. Asserting Status and Headers

WebTestClient has dedicated expectation groups for status:

~~~java
client.get()
    .uri("/orders/101")
    .exchange()
    .expectStatus().isOk();
~~~

Common cases:

~~~java
.expectStatus().isOk()
.expectStatus().isCreated()
.expectStatus().isAccepted()
.expectStatus().isNoContent()
.expectStatus().isBadRequest()
.expectStatus().isNotFound()
.expectStatus().is5xxServerError()
~~~

Headers can be checked:

~~~java
client.get()
    .uri("/orders/101")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectHeader().exists("ETag")
    .expectHeader().valueEquals("X-Api-Version", "v1");
~~~

These assertions verify the external HTTP contract: status codes and headers received by the client. When an endpoint returns a response without a body, you can assert status and headers without calling `expectBody`.

## 8. Asserting JSON Bodies

WebTestClient supports asserting JSON directly:

~~~java
client.get()
    .uri("/orders/101")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .json("""
        {
          "orderId": 101,
          "status": "CONFIRMED"
        }
        """);
~~~

If you only need to inspect specific fields, use JSONPath:

~~~java
client.get()
    .uri("/orders/101")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.orderId").isEqualTo(101)
    .jsonPath("$.status").isEqualTo("CONFIRMED")
    .jsonPath("$.customer.name").isEqualTo("Nguyễn An")
    .jsonPath("$.items[1].sku").isEqualTo("PEN-02");
~~~

WebTestClient's JSONPath has a style similar to MockMvc's JSONPath matcher, making it easier to migrate tests from one API to the other. However, this is a WebTestClient expectation, not `MockMvcResultMatchers.jsonPath(...)`.

When you need to decode the body into a Java type:

~~~java
client.get()
    .uri("/orders/101")
    .exchange()
    .expectStatus().isOk()
    .expectBody(OrderResponse.class)
    .value(order -> {
        assertThat(order.status()).isEqualTo("CONFIRMED");
        assertThat(order.items()).hasSize(2);
    });
~~~

Example using AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
~~~

Verifying via a deserialized object works well when the test cares about data types and multiple response properties. JSONPath works well when you want to keep assertions close to the actual JSON structure.

## 9. Combining Client-Side Assertions with Server-Side MockMvc Assertions

An important benefit of `MockMvcWebTestClient` is the ability to take the WebTestClient result and hand it over to MockMvc to inspect internal Spring MVC details.

Example:

~~~java
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.servlet.client.MockMvcWebTestClient;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.result.MockMvcResultMatchers;

EntityExchangeResult<byte[]> result = client.get()
    .uri("/greeting")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .returnResult();

ResultActions mvcResult = MockMvcWebTestClient.resultActionsFor(result);

mvcResult
    .andExpect(MockMvcResultMatchers.handler().methodName("greeting"));
~~~

Here:

1. WebTestClient sends the request and checks the status.
2. `returnResult()` returns the exchange result containing the response and information retained by the bridge from MockMvc.
3. `resultActionsFor(result)` retrieves the corresponding MockMvc `ResultActions`.
4. The test continues using MockMvc matchers to check the handler or other MVC details.

This is a key distinction between `MockMvcWebTestClient` and a WebTestClient connected to a real server: results from the bridge can be converted back into MockMvc ResultActions.

## 10. MVC Matchers Usable After resultActionsFor

Once you have `ResultActions`, you can use familiar MockMvc matchers. For example:

~~~java
MockMvcWebTestClient.resultActionsFor(result)
    .andExpect(handler().methodName("greeting"));
~~~

Some useful matcher groups:

| Matcher | Information Verified |
|---|---|
| `handler()` | Selected handler, controller type, and method handling the request. |
| `model()` | Model attributes and binding results. |
| `view()` | View name or view state. |
| `flash()` | Flash attributes. |
| `request()` | Request attributes, session, or async state. |
| `forwardedUrl(...)` | Forwarded URL. |
| `redirectedUrl(...)` | Redirected URL. |
| `resolvedException()` | Exception resolved in the MVC result. |

Example with a controller using Model:

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
class GreetingPageController {

    @GetMapping("/greeting-page")
    String greeting(Model model) {
        model.addAttribute("message", "Hello MVC");
        return "greeting";
    }
}
~~~

After sending the request through the client and obtaining the exchange result, you can verify the model and view:

~~~java
EntityExchangeResult<byte[]> result = client.get()
    .uri("/greeting-page")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .returnResult();

MockMvcWebTestClient.resultActionsFor(result)
    .andExpect(model().attribute("message", "Hello MVC"))
    .andExpect(view().name("greeting"));
~~~

This example shows how the two assertion layers complement each other: WebTestClient verifies the HTTP outcome, while MockMvc confirms that Spring MVC prepared the model and chose the expected view. In a real application, the view resolver and template engine must be configured appropriately for the test context.

## 11. Choosing the Right Result Type to Retain the Body

WebTestClient provides several ways to read the response body:

| Usage | Result Type | When Appropriate |
|---|---|---|
| `expectBody()` | BodyContentSpec; `returnResult()` typically returns `EntityExchangeResult<byte[]>`. | Wanting to check raw JSON or obtain the exchange result for `resultActionsFor`. |
| `expectBody(MyType.class)` | BodySpec<MyType, ?>; `returnResult()` returns the deserialized result. | Wanting assertions on a Java object. |
| `expectBodyList(MyType.class)` | ListBodySpec<MyType>; result contains a list of objects. | Endpoint returns a JSON array. |
| `expectBody(Void.class)` | BodySpec<Void, ?>. | Endpoint has no response body. |

If you need to transition to MockMvc matchers, keep the result returned by `returnResult()`. Do not just call `expectBody().jsonPath(...)` and discard the result if you still need to check the handler, model, or view afterward.

## 12. Reusing Test Helpers

Because `WebTestClient` has a unified API, you can write helpers accepting a client to share HTTP assertions:

~~~java
static void assertGreetingResponse(WebTestClient client) {
    client.get()
        .uri("/greeting")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.message").isEqualTo("Hello MVC");
}
~~~

This helper depends only on the WebTestClient API. It can be called with a client created via `MockMvcWebTestClient` for MVC or a client bound appropriately for a WebFlux application.

However, not every test should be shared. If an assertion inspects Servlet MVC specifics such as model, view, or handler method, it needs the MockMvc bridge. If an assertion depends on a WebFlux-specific exchange result or reactive behavior, it belongs to WebFlux tests. Keep the shared portion at the HTTP contract offered by both applications.

## 13. How Does MockMvcWebTestClient Differ from Real-Server Testing?

| Criterion | MockMvcWebTestClient | WebTestClient Connected to a Real Server |
|---|---|---|
| Processing backend | MockMvc and Spring MVC inside the test process. | A running HTTP server, such as embedded Tomcat/Jetty/Undertow or a WebFlux server. |
| Real network and sockets | No. | Yes. |
| Actual Servlet container | Does not start a real container. | Yes if the MVC application runs on an embedded Servlet container. |
| Asserting HTTP status/headers/body | Yes. | Yes. |
| Asserting MVC handler/model/view | Can convert result to MockMvc matchers. | No MockMvc ResultActions available for direct inspection. |
| Speed and isolation | Usually faster and easier to isolate. | Consumes more resources and involves more runtime components. |
| Best suited for | Controllers, mappings, MVC configuration, and HTTP contracts at the mock server level. | Full application integration, connectors, filter/container behavior, and real HTTP communication. |

If the goal is to test controllers and the HTTP contract without opening a server, `MockMvcWebTestClient` is appropriate. If you need to verify the embedded server, port, connector, TLS, network behavior, or container configuration, run the application with a real web environment and use WebTestClient connected to the server.

Do not treat using the same WebTestClient API as proof that the test went over the network or through a Servlet container. The execution backend determines the test scope.

## 14. Dependencies and Versions

`MockMvcWebTestClient` is provided in Spring Test and has been available since Spring Framework 5.3. When using it, the project needs the Spring MVC/MockMvc testing classes and the WebTestClient API on the test classpath.

In Spring Boot projects, let Spring Boot dependency management keep Spring module versions aligned. If WebTestClient is not yet on the classpath, add the Spring WebFlux dependency in test scope under the project's dependency management, rather than adding the full reactive starter to runtime just to get the test API.

Gradle example when the project already uses Spring Boot dependency management:

~~~groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.springframework:spring-webflux")
}
~~~

In many projects, `spring-test` is already included via `spring-boot-starter-test`; in that case, only add the missing module. Check the actual dependency graph before adding anything to avoid duplicate declarations or pulling in a Spring version mismatched with the BOM.

Key packages:

| Component | Package |
|---|---|
| `WebTestClient` | `org.springframework.test.web.reactive.server` |
| `MockMvcWebTestClient` | `org.springframework.test.web.servlet.client` |
| `MockMvc` | `org.springframework.test.web.servlet` |
| MockMvc result matchers | `org.springframework.test.web.servlet.result` |

## 15. Common Pitfalls

### Confusing MockMvcWebTestClient with a WebFlux server

`MockMvcWebTestClient` uses WebTestClient as the client-side API, but requests are handled by MockMvc and Spring MVC. Controllers remain Servlet MVC controllers.

### Thinking exchange() opens a real HTTP connection

When a client is created with `MockMvcWebTestClient`, `exchange()` invokes the bridge inside the same test process. No real port or socket is opened.

### Using bindToController when application configuration is needed

If the test relies on controller advice, interceptors, validators, or message converters declared in the application context, use `bindToApplicationContext` so those configurations participate.

### Forgetting to call returnResult before resultActionsFor

`resultActionsFor` requires the exchange result returned by WebTestClient. Save the result using `returnResult()` before converting it to MockMvc ResultActions.

### Using only WebTestClient matchers for every assertion

WebTestClient checks the HTTP response. If you need to verify handlers, models, views, flash attributes, or resolved exceptions at the MVC layer, use `MockMvcWebTestClient.resultActionsFor(...)` and MockMvc matchers.

### Using resultActionsFor with a client not backed by MockMvc

`resultActionsFor` is a bridge intended for exchange results produced by `MockMvcWebTestClient`. Do not use it with a WebTestClient connected to a real server or a binding that does not retain MockMvc results.

### Adding the WebFlux runtime starter just to get WebTestClient

An MVC application does not need to enable the WebFlux runtime just to write tests with WebTestClient. If required APIs are missing, add the appropriate dependency in test scope and keep Spring module versions aligned.

## 16. Workflow for Choosing APIs in MVC Tests

When writing tests for MVC controllers:

1. Choose `bindToController` when you need isolated testing of a controller; choose `bindToApplicationContext` when you need the application's MVC configuration.
2. Use WebTestClient to build requests according to the HTTP contract: method, URI, headers, cookies, content type, and body.
3. Call `exchange()` and verify status, headers, and body using WebTestClient expectations.
4. If the response is JSON, use `expectBody().json(...)`, JSONPath, or deserialize to a Java type.
5. If you need to inspect handler, model, view, flash, or Servlet MVC details, call `returnResult()` and use `MockMvcWebTestClient.resultActionsFor(...)`.
6. If you need to test networking or a real embedded Servlet container, use a real test server instead of the MockMvc bridge.

`MockMvcWebTestClient` enables Spring MVC to use WebTestClient's client testing style while preserving deep inspection capabilities via MockMvc when needed. Understanding the active binding and knowing when to switch from client assertions to MVC assertions keeps tests consistent while verifying the right layer of application behavior.
