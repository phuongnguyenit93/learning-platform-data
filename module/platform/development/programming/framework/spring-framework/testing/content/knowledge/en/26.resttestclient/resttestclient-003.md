# Binding to a Controller, ApplicationContext, or MVC Router Function

`RestTestClient` is Spring's synchronous HTTP test client for testing REST endpoints. With Spring MVC, the client can be bound directly to a controller, bound to a `WebApplicationContext`, or bound to an MVC `RouterFunction`. All three approaches allow sending requests and checking status, headers, and body using an API close to a real HTTP client.

The difference lies in the scope of MVC infrastructure brought into the test:

- Binding to a controller creates an MVC environment focused around the specified controller.
- Binding to an ApplicationContext uses the MVC configuration and beans in the application's context.
- Binding to a router function directly tests routes declared using Spring MVC's functional endpoint model.

Choosing the right binding mode helps the test verify the exact boundary needed while avoiding initializing unrelated components.

## 1. What Is RestTestClient?

`RestTestClient` provides a synchronous request/response API for REST endpoints. Familiar test style:

~~~java
client.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo(42);
~~~

Main steps:

1. Choose an HTTP method such as `get()`, `post()`, `put()`, `patch()`, or `delete()`.
2. Provide the URI and request components such as headers, content type, query parameters, and body.
3. Call `exchange()` to send the request.
4. Check the status, headers, and body in the response.

With Spring MVC, `RestTestClient` can run on mock infrastructure without opening a network port. This is useful for fast controller and HTTP mapping tests. If you want to test communication through an HTTP connector and a running server, use server binding instead of mock binding.

`RestTestClient` belongs to Spring Framework 7.0 and later. When a project uses an older Spring Framework version, use the tool corresponding to that version, such as MockMvc or WebTestClient with an appropriate adapter. Do not add dependencies or change versions just to run examples if the project has not upgraded.

## 2. Binding Directly to a Controller

`bindToController(...)` is suitable when you want to test one or several specific controllers without initializing the entire `WebApplicationContext`.

Example controller:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    OrderResponse get(@PathVariable long id) {
        return orderService.findById(id);
    }
}
~~~

Create the client using the instantiated controller:

~~~java
OrderService orderService = mock(OrderService.class);
given(orderService.findById(42L))
        .willReturn(new OrderResponse(42L, "PAID"));

RestTestClient client = RestTestClient
        .bindToController(new OrderController(orderService))
        .build();

client.get()
        .uri("/api/orders/42")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(42)
        .jsonPath("$.status").isEqualTo("PAID");
~~~

In the example, the controller is instantiated directly and receives a mock service via its constructor. The test focuses on how Spring MVC maps the request to the handler and produces the response.

### 2.1. When Should You Use bindToController?

Choose this approach when:

- The test only needs a single controller or a small group of controllers.
- You want to verify the controller's mapping, binding, serialization, and response.
- Dependencies can be provided directly via constructor or mocks.
- Other global beans and configuration in the application context are not needed.

This is a lean choice for focused tests. However, because it does not load the entire MVC configuration of the application, components such as `@ControllerAdvice`, custom `Converter`, `Formatter`, `Validator`, message converters, interceptors, or filters may not match production configuration unless the test registers them in the builder.

For example, if a controller relies on shared exception advice, a directly bound test needs to add the advice to the standalone configuration if the builder in the Spring version being used provides that option. If the test's goal is to verify application-wide configured advice and MVC components, binding to the context is more appropriate.

Do not instantiate a controller with `new` when the goal is to test Spring bean injection, proxies, or bean configuration. `bindToController` tests the controller supplied to the test environment; it does not prove that the application's component scanning or dependency injection works.

## 3. Binding to WebApplicationContext

`bindToApplicationContext(...)` uses the application's `WebApplicationContext`. Spring MVC test infrastructure is configured based on the beans and configuration in the context, so tests can include more components than individual controllers.

Example:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerRestTest {

    @Autowired
    WebApplicationContext context;

    @MockBean
    OrderService orderService;

    RestTestClient client;

    @BeforeEach
    void setUp() {
        client = RestTestClient
                .bindToApplicationContext(context)
                .build();
    }

    @Test
    void returnsOrderFromMvcApplicationContext() {
        given(orderService.findById(42L))
                .willReturn(new OrderResponse(42L, "PAID"));

        client.get()
                .uri("/api/orders/42")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(42)
                .jsonPath("$.status").isEqualTo("PAID");
    }
}
~~~

The example uses `@WebMvcTest` to load the MVC slice. The selected controller and related MVC components are configured according to the test slice; the service is replaced by a mock so the test does not need to access the business layer or a real database.

If a fuller MVC configuration is needed, you can use a context created by `@SpringJUnitConfig`, `@ContextConfiguration`, or `@SpringBootTest`, depending on the goal. `bindToApplicationContext(context)` does not automatically turn a narrow context into a full context; bean scope is still determined by how the context is initialized.

### 3.1. Components Tested Together with the Context

When binding to a context, tests can verify how MVC components collaborate:

- Controllers registered in the context.
- `@ControllerAdvice` or `@RestControllerAdvice` handling exceptions.
- `HttpMessageConverter` reading request bodies and writing response bodies.
- `ConversionService`, `Formatter`, and `Validator` converting/validating data.
- Interceptors and MVC configuration registered in the context.
- Integrated configurations such as Spring Security, if the test context loads them and requests pass through the corresponding filter chain.

This brings the test closer to the application configuration, but can also make the context heavier and dependent on more beans. If a test fails due to an unrelated component, review the scope of the loaded context.

### 3.2. @WebMvcTest or @SpringBootTest?

These two approaches serve different purposes:

| Context initialization method | Scope | When suitable |
|---|---|---|
| `@WebMvcTest` | MVC test slice, usually limited to controllers and required web components | Testing mapping, binding, validation, advice, and responses |
| `@SpringJUnitConfig` / `@ContextConfiguration` | Test context explicitly declared with specified configuration | Testing custom MVC configuration without needing all of Boot |
| `@SpringBootTest` | Spring Boot application context with broader scope | Verifying integration across multiple application beans and configuration |

`RestTestClient.bindToApplicationContext(context)` uses the injected context; it does not dictate which test annotation must be used. Choose the test context first, then bind the client to that context.

## 4. Binding to a Spring MVC Router Function

Spring MVC supports functional endpoints via `RouterFunction`. Instead of using annotations like `@GetMapping`, the application declares routes and handlers with a functional API.

An MVC router function uses types in the `org.springframework.web.servlet.function` package, such as `RouterFunction`, `ServerRequest`, and `ServerResponse`. Do not confuse these types with WebFlux router functions in the `org.springframework.web.reactive.function.server` package.

Example route declaration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.web.servlet.function.RequestPredicates.GET;
import static org.springframework.web.servlet.function.RequestPredicates.accept;
import static org.springframework.web.servlet.function.RouterFunctions.route;

@Configuration
class OrderRoutes {

    @Bean
    RouterFunction<ServerResponse> orderRoutes(OrderHandler handler) {
        return route()
                .route(GET("/api/orders/{id}")
                                .and(accept(MediaType.APPLICATION_JSON)),
                        handler::getOrder)
                .build();
    }
}
~~~

Handler:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

@Component
class OrderHandler {

    private final OrderService orderService;

    OrderHandler(OrderService orderService) {
        this.orderService = orderService;
    }

    ServerResponse getOrder(ServerRequest request) {
        long id = Long.parseLong(request.pathVariable("id"));
        OrderResponse response = orderService.findById(id);
        return ServerResponse.ok().body(response);
    }
}
~~~

You can bind directly to the router function:

~~~java
OrderService orderService = mock(OrderService.class);
OrderHandler handler = new OrderHandler(orderService);

RouterFunction<ServerResponse> routes = route()
        .GET("/api/orders/{id}", handler::getOrder)
        .build();

given(orderService.findById(42L))
        .willReturn(new OrderResponse(42L, "PAID"));

RestTestClient client = RestTestClient
        .bindToRouterFunction(routes)
        .build();

client.get()
        .uri("/api/orders/42")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(42)
        .jsonPath("$.status").isEqualTo("PAID");
~~~

This test verifies the route predicate, path variable, handler, and response generation in an MVC functional endpoint. Because the router function is provided directly, the test can isolate the route under test without loading the entire application context.

### 4.1. When Should You Use bindToRouterFunction?

Choose this approach when:

- Endpoints are declared using Spring MVC functional routing.
- You want to test route predicates and handler functions.
- You want to verify paths, methods, header predicates, and router responses.
- Required handlers or dependencies can be provided directly.

If the router function is registered as a bean in the application context and depends on shared configuration, binding to the context tests both bean registration and application configuration. Binding directly to a router function is more focused, but does not prove the route was properly registered by the application's components/configuration.

## 5. Comparing the Three Binding Modes

| Criterion | Controller | ApplicationContext | Router function |
|---|---|---|---|
| Builder input | Controller instance | `WebApplicationContext` | MVC `RouterFunction` |
| Scope | One or a specified group of controllers | MVC beans/configuration in the context | The provided route function |
| Suitable for | Annotation-based controllers | MVC configuration integration testing | Functional endpoints |
| Dependencies | Usually passed directly to the controller | Retrieved from the context | Usually provided via handler or context |
| Advice/converter/interceptor | Must be registered in test configuration if needed | Follows context configuration | Needs configuration or context binding if relying on shared components |
| Verifies component scanning/bean registration | No | Yes within context scope | No when binding a route instance directly |
| Startup cost | Usually low | Depends on context size | Usually low |

Selection rules:

- Annotation-based controller needing focused tests: `bindToController`.
- Need to verify shared MVC beans: `bindToApplicationContext`.
- Endpoints using Spring MVC functional routing: `bindToRouterFunction`.

## 6. Requests and Responses Work the Same Across All Three Modes

Once the client is created, the API for sending requests and making assertions is essentially the same. JSON POST example:

~~~java
client.post()
        .uri("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Request-Source", "web")
        .body("""
                {
                  "sku": "COFFEE-01",
                  "quantity": 2
                }
                """)
        .exchange()
        .expectStatus().isCreated()
        .expectHeader().exists(HttpHeaders.LOCATION)
        .expectBody()
        .jsonPath("$.sku").isEqualTo("COFFEE-01");
~~~

Tests should describe data according to the HTTP contract a real client sends:

- Use the right method and path.
- Place query parameters, path variables, and headers in the right places.
- Declare `Content-Type` for the body and `Accept` for the response.
- Send properly formatted JSON or form data.
- Verify status, response headers, and body.

Do not turn a controller-bound test into a test that calls Java methods directly. The purpose of RestTestClient is to verify the HTTP path through the MVC test infrastructure.

## 7. Combining with MVC Configuration and Exception Handling

Suppose the application has a `@RestControllerAdvice` mapping an order-not-found error:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleNotFound(
            OrderNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError("ORDER_NOT_FOUND", ex.getMessage()));
    }
}
~~~

When testing advice configured in the application, bind the client to `WebApplicationContext` so requests go through that configuration:

~~~java
client.get()
        .uri("/api/orders/999")
        .exchange()
        .expectStatus().isNotFound()
        .expectBody()
        .jsonPath("$.code").isEqualTo("ORDER_NOT_FOUND");
~~~

If binding directly to a controller, ensure the advice is registered in the test configuration. Otherwise, the test may receive a default error response different from the real application. This is why binding scope should be chosen based on the components the test needs to prove.

Similarly, custom formatters, validators, or message converters can change request binding outcomes. If a test needs to verify a shared converter, use a context containing that converter or register it explicitly in the test configuration.

## 8. Distinguishing MVC Router Functions and WebFlux Router Functions

The name `RouterFunction` appears in both Spring MVC and Spring WebFlux, but the two types do not share request/response types:

| Spring MVC | Spring WebFlux |
|---|---|
| `org.springframework.web.servlet.function.RouterFunction` | `org.springframework.web.reactive.function.server.RouterFunction` |
| Servlet MVC `ServerRequest` and `ServerResponse` | Reactive `ServerRequest` and `ServerResponse` |
| Processed with the Servlet model and synchronous API | Processed reactively with `Mono`/`Flux` |
| Can be tested with `RestTestClient` | Typically tested with `WebTestClient` |

Do not pass a WebFlux `RouterFunction` to MVC's `RestTestClient.bindToRouterFunction(...)`. If the application uses WebFlux functional endpoints, choose WebTestClient and its corresponding binding API.

## 9. When Should You Bind to a Real Server?

The three binding modes in this article focus on mock MVC infrastructure. They do not open network ports and do not verify the full behavior of the Servlet container, connector, or proxy.

When you need to test real HTTP communication, you can run the application on a random port:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @LocalServerPort
    int port;

    RestTestClient client;

    @BeforeEach
    void setUp() {
        client = RestTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();
    }

    @Test
    void servesOrderOverHttp() {
        client.get()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isOk();
    }
}
~~~

This kind of test is suitable when you need to check the server connector, port configuration, server-level filters, serialization over an HTTP connector, or interaction with a real HTTP client. Startup cost is higher than mock tests and usually takes additional time for the application to become ready.

You do not need a real server for every controller test. Use mock bindings for most fast MVC tests; add targeted integration tests for behavior that only appears when the server is actually running.

## 10. Common Mistakes When Choosing a Binding Mode

| Symptom | Common cause | Resolution |
|---|---|---|
| Controller test does not see custom advice | Bound directly to the controller without registering advice | Register advice in the test or bind to the context |
| Custom converter does not run | Test does not use a context/configuration with the converter | Bind to `WebApplicationContext` or register the converter |
| Controller needs dependencies but test cannot instantiate it | Instantiated controller directly without dependencies | Pass mocks/stubs via constructor or use a context |
| Functional route returns 404 in test | Bound the wrong router function or route predicate does not match | Use MVC `RouterFunction` and check method/path/headers |
| Route exists in application but standalone router-bound test cannot find it | Test only supplies a different router instance | Retrieve the router bean from context or bind the full context |
| Using RestTestClient for WebFlux routes | Confusing MVC and WebFlux APIs | Use WebTestClient for WebFlux |
| Test expects real Servlet container behavior while using mock binding | Mock infrastructure does not open sockets/run a real connector | Bind to a running server |
| Test context takes too long to start | Using full application context for a test needing only one controller | Consider `bindToController` or an MVC test slice |

## 11. Workflow for Choosing and Creating RestTestClient

Before writing a test, determine which kind of endpoint you are testing:

1. If the endpoint is an annotation-based controller and only handler behavior needs checking, instantiate the controller with its required dependencies and use `bindToController`.
2. If you need to verify advice, converters, validators, interceptors, or bean registration in the application, initialize an appropriate `WebApplicationContext` and use `bindToApplicationContext`.
3. If the endpoint is declared with Spring MVC functional routing, create or retrieve the MVC `RouterFunction` and use `bindToRouterFunction`.
4. If you need to verify the connector and real HTTP communication, start the server and use `bindToServer`.
5. After binding, write requests according to the HTTP contract and assert on status, headers, and body.

No single binding mode is always best. Test quality depends on whether the scope of initialized infrastructure matches the behavior being verified. Binding too narrowly can miss shared MVC configuration; binding too broadly slows down tests and makes failure root causes harder to pinpoint.

When choosing among controller, ApplicationContext, and router function, start from the actual entry point of the endpoint. Annotation-based controllers should be tested via controller or context; functional endpoints should be tested via MVC router function or a context where that router is registered. Clear binding makes tests reflect the application structure accurately and stay meaningful as MVC configuration evolves.
