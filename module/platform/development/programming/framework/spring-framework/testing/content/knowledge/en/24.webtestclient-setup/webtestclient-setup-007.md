# Choosing the Test Boundary Each Mode Actually Covers

## The Test Boundary Determines What Enters the Test

WebTestClient provides a fluent API for sending requests and asserting HTTP responses. However, the exact same API can run at several different boundaries. Some modes create simulated requests/responses inside Spring WebFlux; another mode calls a running server over real HTTP.

Therefore, when choosing how to create WebTestClient, you first need to determine which part of the application the test wants to verify:

- A controller together with the minimal WebFlux components required to invoke it.
- WebFlux configuration and beans present in an ApplicationContext.
- A RouterFunction of the functional endpoint model.
- The entire application running behind a real HTTP port.

These options are not four quality levels in ascending order. Each option establishes a different boundary. A test at a narrow boundary can run fast and pinpoint failures in a single component; a test at a broader boundary can uncover configuration or integration issues that narrow tests cannot see. Choosing the mode based on the contract you need to verify keeps tests meaningful while avoiding pulling in unrelated components.

## Four Ways to Initialize WebTestClient

Commonly used factory methods:

~~~java
WebTestClient.bindToController(controller).build();

WebTestClient.bindToApplicationContext(applicationContext).build();

WebTestClient.bindToRouterFunction(routerFunction).build();

WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
~~~

The first three options integrate with Spring WebFlux's simulated test infrastructure. They do not send requests over a socket to a listening server. The last option creates a client that connects to a real running server.

| Mode | Primary Input | Boundary Tested | Not Automatically Included |
| --- | --- | --- | --- |
| bindToController | Controller instances | Controllers and minimal WebFlux infrastructure for mapping, binding requests, and writing responses | Full application configuration, component scan, and filter chain |
| bindToApplicationContext | WebFlux ApplicationContext | WebFlux infrastructure and beans/configurations registered in the context | HTTP connector and real server container behavior |
| bindToRouterFunction | RouterFunction | Routing and handlers of functional endpoints along with supporting WebFlux infrastructure | Annotated controller mappings and the full application context unless provided separately |
| bindToServer | Address of a running server | HTTP request/response over a connector to the running application serving requests | External systems not configured or not called by the application |

## bindToController: Focusing on the Controller

**bindToController(...)** is suitable when you want to test one or a few specific controllers. The test supplies controller instances directly; WebTestClient builds the WebFlux infrastructure needed to process requests and invoke them.

Example:

~~~java
WebTestClient client = WebTestClient
        .bindToController(new GreetingController(new GreetingService()))
        .build();

client.get()
        .uri("/greeting")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.message").isEqualTo("Hello");
~~~

This boundary is useful for verifying:

- Mapping from HTTP method and path to handler method.
- Reading path variables, query parameters, headers, and request bodies.
- Input parameter conversion, return type handling, and writing responses via WebFlux message codecs.
- Status and payload returned by the controller.
- Exception handling declared or configured directly for the test scope.

Because the controller is passed directly, the test does not prove whether the application's component scan finds the controller. Other application beans also do not automatically appear simply because the controller has constructor dependencies. Pass dependencies explicitly—typically mocks or fakes when the goal is to test controller behavior.

If you need to test a global concern such as controller advice or a validator, configure it on the controller spec if supported by the builder API, or switch to testing the ApplicationContext when you want to verify the application's real configuration. Manually adding a component to a test places it within that test boundary; it does not prove the component is properly registered in production configuration.

Choose this mode when the question is: "Given the provided dependencies, does the controller interpret requests and produce responses correctly?" It is not suitable for concluding that the entire WebFlux application is assembled properly.

## bindToApplicationContext: Verifying Assembled WebFlux Configuration

**bindToApplicationContext(applicationContext)** uses a prepared WebFlux ApplicationContext. WebTestClient obtains the request-handling infrastructure from the context, so the test passes through the WebFlux configuration and beans registered within that scope.

Example with a context built from test configuration:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = WebFluxTestConfig.class)
class GreetingWebFluxTests {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .build();
    }

    @Test
    void resolvesGreetingThroughConfiguredWebFluxInfrastructure() {
        client.get()
                .uri("/greeting")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello");
    }
}
~~~

Depending on the context configuration, this boundary may include:

- Controllers and handler mappings registered in the context.
- WebFlux configuration, message codecs, formatters, and validators.
- Registered WebFilters, exception handlers, and WebFlux infrastructure components.
- Real or mock business beans declared in the context.

Unlike bindToController, the test can detect bugs caused by missing WebFlux configuration imports, unregistered beans, or filters/handlers missing from the context's processing chain. It is the right choice when you need to confirm that Spring components are wired together properly.

Requests are still processed via WebFlux's mock requests and responses. The test does not open a TCP port and does not pass through a real connector or server container. Thus, it does not verify issues that only appear upon server deployment, such as port configuration, TLS, sockets, connection limits, or specific integration with the server runtime.

The scope of the test depends on the loaded context. A minimal context importing only a few configurations remains a minimal test context; using bindToApplicationContext does not automatically turn it into the full production application context. Check explicitly which configuration classes or bootstrap mechanism create the context.

Choose this mode when the question is: "Do the WebFlux beans and configuration in this context cooperate to handle requests properly?"

## bindToRouterFunction: Focusing on Functional Endpoints

Spring WebFlux allows declaring HTTP endpoints using functional routing instead of annotated controllers. A RouterFunction describes how to select a route based on a request and dispatch the request to the corresponding handler.

**bindToRouterFunction(routerFunction)** fits when you want to test a RouterFunction directly. The test does not need to set up annotated controller mappings for these routes.

Example:

~~~java
import static org.springframework.web.reactive.function.server.RequestPredicates.GET;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;
import static org.springframework.web.reactive.function.server.ServerResponse.ok;

RouterFunction<ServerResponse> routes = route(
        GET("/greeting"),
        request -> ok().bodyValue(Map.of("message", "Hello"))
);

WebTestClient client = WebTestClient
        .bindToRouterFunction(routes)
        .build();

client.get()
        .uri("/greeting")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.message").isEqualTo("Hello");
~~~

This boundary allows verifying:

- Whether predicates match the right method, path, header, or request conditions.
- Whether the route selects the expected handler or returns not found.
- Whether the handler produces the right status, headers, and body.
- Whether filters composed directly onto the RouterFunction take the intended effect.

For instance, if routes are built from multiple functions and combined using RouterFunctions.route(...) or andOther(...), the test can send requests through that combined result to verify routing order and outcomes.

Because the RouterFunction is passed directly, the test does not prove that the application's annotated controllers work. It also does not automatically test every bean or WebFilter that exists only in another ApplicationContext. If a filter, codec, or shared component is part of the contract to verify, include that configuration in an appropriate test boundary, typically bindToApplicationContext.

Choose this mode when the question is: "Do the provided functional routes and handlers classify requests and return responses correctly?"

## bindToServer: Going Over HTTP to a Running Server

**bindToServer()** creates a WebTestClient that connects to a server listening at a configured address. Requests are sent through a client connector and enter the server as real HTTP requests.

Example:

~~~java
WebTestClient client = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

client.get()
        .uri("/greeting")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.message").isEqualTo("Hello");
~~~

With Spring Boot, a test can start the application on a random port and connect to that port. The exact startup mechanism depends on the test setup; the key requirement is that the server must be ready before WebTestClient sends requests.

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GreetingServerTests {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();
    }

    @Test
    void servesGreetingOverHttp() {
        client.get()
                .uri("/greeting")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello");
    }
}
~~~

This boundary includes the components actually used by the running application to serve requests, such as:

- The server connector and the HTTP transport path from client to server.
- The server runtime and deployment settings enabled in the test environment.
- The active WebFlux handler chain, filters, security, and message codecs in the application.
- The business beans and dependencies that the application actually connects to in the test configuration.

Because a real server is present, this mode is suitable for catching bugs that do not surface in mock requests/responses, such as server settings, connectors, or differences on the HTTP wire. It also tests the application after startup and component assembly according to the test environment's configuration.

However, "going through a real server" does not mean "having tested every external system." If databases, message brokers, or third-party APIs are replaced by mocks, the test still covers only that mock configuration. If you need to verify integration with real dependencies, configure those dependencies and manage their lifecycles explicitly.

Choose this mode when the question is: "Does the running application accept HTTP requests through the server and return the responses observed by a client?"

## Comparing by What the Test Actually Needs to Verify

| Question to Answer | Appropriate Mode | Why |
| --- | --- | --- |
| Does a controller handle requests and return DTOs properly with provided dependencies? | bindToController | Narrow scope focused on the controller |
| Do controllers, WebFilters, codecs, and WebFlux configuration in the context cooperate properly? | bindToApplicationContext | Goes through the WebFlux infrastructure assembled in the context |
| Does a functional route pick the right handler and response? | bindToRouterFunction | Passes the RouterFunction directly into the test |
| Does the running server accept HTTP requests and return responses over a connector? | bindToServer | Sends requests over HTTP to a real server |
| Are TLS settings, connectors, or server runtime behaviors correct? | bindToServer | Mock modes do not go through a real server connector |
| Do component scanning or application configuration register the right controllers/filters/beans? | bindToApplicationContext or bindToServer | Requires the context created by the corresponding application configuration |

Do not choose bindToServer simply because it has a wider boundary. It requires starting a server, typically takes longer, and may require managing ports, dependencies, or test data. If a controller test can verify the needed contract at bindToController, adding a server increases cost without producing additional useful evidence.

Conversely, if the bug to catch lies in WebFilter registration or message codec configuration, a test that instantiates the controller directly will not cover that part. In that case, expand the boundary to ApplicationContext or a real server.

## Client Configuration Does Not Change the Server Boundary

WebTestClient allows configuring the client side after choosing how to connect. Example:

~~~java
WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .configureClient()
        .defaultHeader("X-Test-Client", "mvc-suite")
        .build();
~~~

**configureClient()** transitions from server/test-infrastructure configuration to WebTestClient client configuration. Options such as default headers, client-side filters, or response timeout affect how the client sends requests and handles responses.

Adding a base URL, default header, or client filter does not turn bindToController into bindToServer. The server-side boundary is still determined by the initial bind method. Likewise, increasing the response timeout does not cause the test to cover additional connectors, filters, or application beans.

When you need to configure both sides, identify them separately:

- **Server/test-infrastructure side:** controller, ApplicationContext, RouterFunction, or running server.
- **Client side:** base URL, default headers, authentication headers, client filters, client codecs, and response timeout.

Separating the two sides makes tests easier to read: one configuration specifies where requests go, while the other specifies how the client sends and observes requests.

## WebTestClient with Spring MVC Is a Different Boundary

WebTestClient is commonly used with Spring WebFlux. Spring Framework also provides the **MockMvcWebTestClient** adapter to use the WebTestClient-style testing API while requests are executed by Spring MVC's MockMvc.

Example:

~~~java
WebTestClient client = MockMvcWebTestClient
        .bindToController(new GreetingMvcController())
        .build();

client.get()
        .uri("/greeting")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.message").isEqualTo("Hello");
~~~

This is MockMvc integration, not WebFlux's bindToApplicationContext and not bindToServer. It is useful when you want to use WebTestClient's request/response assertion style for a Spring MVC application while keeping MockMvc's mock boundary.

If you need to inspect MockMvc-specific details further, the adapter provides a way to retrieve the MockMvc result from the exchange result via **MockMvcWebTestClient.resultActionsFor(...)**. This grants access to additional MockMvc assertions or testing APIs when needed.

Therefore, when a project uses Spring MVC, choose the MockMvc adapter if the goal is testing MVC in a mock environment. Only use bindToServer when you want to send requests through a running server.

## Common Mistakes When Choosing the Wrong Mode

### Using bindToController while expecting component scanning to work

Controllers are passed directly, so the test does not verify whether Spring Boot discovers the controller via component scan. If you need to verify bean registration from application configuration, use an appropriately bootstrapped ApplicationContext.

### Using bindToApplicationContext while thinking the HTTP connector was tested

ApplicationContext mode processes requests through WebFlux's mock server-side exchange. It tests framework configuration in the context, but does not open a port or send data over a socket. Use server mode for connector behavior.

### Using bindToRouterFunction for annotated controllers

RouterFunction is the functional routing model. It does not replace RequestMappingHandlerMapping and does not discover methods annotated with @GetMapping or @PostMapping. For annotated controllers, choose controller mode or context mode.

### Using bindToServer before the server is ready

The client cannot connect if the application has not started or the port is not yet determined. In tests using a random port, construct the URL only after the test framework has provided the server port.

### Assuming server mode automatically tests databases and external services

Server mode only goes through the running application. Deeper integration depends on the beans and dependencies configured by the test environment. A mock repository remains a mock repository even when requests go over real HTTP.

### Configuring the client and misunderstanding the server-side boundary

Default headers, client filters, or base URL belong to client configuration. They do not add controllers, filters, or application beans to the server-side infrastructure under test.

## Workflow for Choosing a Boundary Before Writing Tests

1. State clearly the behavior to protect: controller mapping, WebFlux configuration, functional route, or HTTP server.
2. Identify which components must run for real for the test to be meaningful; list components that can be replaced with mocks or fakes.
3. Choose bindToController, bindToApplicationContext, bindToRouterFunction, or bindToServer according to that boundary.
4. Check the source of infrastructure setup: controller instance, ApplicationContext, RouterFunction, or server address.
5. Configure the client side separately if headers, filters, base URL, or timeouts are needed.
6. Send requests using exchange() and verify status, headers, and body against the HTTP contract.
7. If another boundary needs verification, write a test suited to that boundary rather than assuming one mode covers every layer.

A test provides evidence only for the components that actually lie on the request path in the test configuration. Choosing the right boundary clarifies exactly what has been verified, what remains outside scope, and where to place another test when further verification is needed.
