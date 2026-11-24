# Criteria for Choosing Standalone or Context-Based Setup

`MockMvc` lets you test the Spring MVC processing flow without opening an HTTP server. When creating `MockMvc`, Spring Test provides two common setup approaches: `standaloneSetup(...)` and `webAppContextSetup(...)`.

`standaloneSetup(...)` creates a minimal MVC environment around controllers passed directly into the builder. `webAppContextSetup(...)` uses a `WebApplicationContext` loaded by Spring, so tests can use the actual MVC configuration and beans in that context.

The selection criterion lies in the scope to be verified. If the question focuses on the behavior of a controller with explicitly supplied dependencies, standalone setup is usually concise and fast. If you need to verify that a controller works with the MVC configuration and beans in the web context, use the context-based setup.

## 1. What Does MockMvc Do in Spring MVC Testing?

In a running application, an HTTP request passes through the Servlet container, reaches `DispatcherServlet`, and is routed by Spring MVC to a controller. The controller may use argument resolvers to turn the request into Java parameters, call a service, and then Spring MVC turns the result into a response through a message converter or view resolver.

`MockMvc` simulates the request/response handling portion of Spring MVC within the same test process. The test builds a request, sends it through `DispatcherServlet` configured for the test environment, and asserts status, headers, body, model, or view. No network port needs to be opened or socket traffic sent.

A typical test looks like:

```java
mockMvc.perform(get("/greetings/Lan"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.message").value("Hello, Lan"));
```

The difference between the two setup styles is how `MockMvc` receives controllers and the MVC infrastructure to handle that request.

## 2. Standalone Setup with standaloneSetup

`MockMvcBuilders.standaloneSetup(controller)` accepts one or more controllers directly. Spring Test builds the MVC infrastructure needed for the test around those controllers, without loading the application's `WebApplicationContext`.

Example controller and shared types:

```java
public class GreetingResponse {

    private final String message;

    public GreetingResponse(String message) {
        this.message = message;
    }

    public String getMessage() {
        return message;
    }
}

public interface GreetingService {
    GreetingResponse greet(String name);
}

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greetings/{name}")
    public GreetingResponse greet(@PathVariable String name) {
        return greetingService.greet(name);
    }
}
```

A standalone test can use Mockito to supply the service:

```java
@ExtendWith(MockitoExtension.class)
class GreetingControllerStandaloneTest {

    @Mock
    private GreetingService greetingService;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        GreetingController controller = new GreetingController(greetingService);

        mockMvc = MockMvcBuilders
                .standaloneSetup(controller)
                .build();
    }

    @Test
    void returnsGreetingAsJson() throws Exception {
        when(greetingService.greet("Lan"))
                .thenReturn(new GreetingResponse("Hello, Lan"));

        mockMvc.perform(get("/greetings/{name}", "Lan"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.message").value("Hello, Lan"));
    }
}
```

Here, the test instantiates `GreetingController` itself, passes the mock service into the constructor, and hands the controller to `standaloneSetup`. No component scanning, application configuration, or project Spring application context is loaded. The test still runs the MVC steps required to map the URL, invoke the controller, and write the response.

### How Much Infrastructure Is Configured?

The standalone builder provides default MVC components needed to run controller tests. It also lets you customize many parts of that infrastructure, for example:

- `setControllerAdvice(...)` to register `@ControllerAdvice` or `@RestControllerAdvice` needed in the test.
- `setMessageConverters(...)` to configure how objects are converted to JSON/XML or how request bodies are read.
- `setValidator(...)` to use a specific validator when testing `@Valid`.
- `setConversionService(...)` to configure type conversion.
- `addInterceptors(...)` to add interceptors.
- `addFilters(...)` to add servlet filters to MockMvc's processing chain.
- `setCustomArgumentResolvers(...)` to register custom argument resolvers.
- `setViewResolvers(...)` to configure view resolution in server-side rendering MVC tests.

Specific options depend on the Spring Framework version. The common rule is that the test must explicitly register any customized components it needs. The standalone builder does not automatically scan for all configuration beans in the application.

### When Is standaloneSetup Appropriate?

Choose standalone setup when you want to test the behavior of a single controller or a small group of controllers, such as:

- Are the URL and HTTP method mapped properly to the handler method?
- Are `@PathVariable`, `@RequestParam`, and `@RequestBody` bound properly under the MVC configuration used for the test?
- Does the controller call the service with the required data and produce the expected response?
- Are the status, headers, and JSON response correct?
- Does the controller handle exceptions as expected when the test registers the corresponding exception advice?
- Does a specific validation rule or converter work properly when the test provides that exact validator/converter?

This is a useful option for focused controller tests with few dependencies that need to run quickly. It also makes controller dependencies explicit because the test must supply them itself.

## 3. WebApplicationContext-Based Setup

`MockMvcBuilders.webAppContextSetup(webApplicationContext)` accepts a `WebApplicationContext` already created by Spring. Spring Test uses this context to configure `DispatcherServlet` and the Spring MVC components registered in the context.

Minimal MVC configuration example:

```java
@Configuration
@EnableWebMvc
public class WebMvcTestConfig {

    @Bean
    GreetingService greetingService() {
        return name -> new GreetingResponse("Hello, " + name);
    }

    @Bean
    GreetingController greetingController(GreetingService greetingService) {
        return new GreetingController(greetingService);
    }
}
```

A test loading this configuration as a `WebApplicationContext`:

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = WebMvcTestConfig.class)
class GreetingControllerContextTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();
    }

    @Test
    void usesMvcConfigurationFromWebApplicationContext() throws Exception {
        mockMvc.perform(get("/greetings/{name}", "Lan"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.message").value("Hello, Lan"));
    }
}
```

`@WebAppConfiguration` instructs Spring Test to create a web environment for the test and bind `WebApplicationContext` to a `MockServletContext`. `@ContextConfiguration` specifies the configuration used to load the context. `@EnableWebMvc` registers Spring MVC infrastructure, while the beans in the configuration provide controllers and services.

In real projects, the loaded configuration may be the production MVC configuration, a streamlined test configuration, or a context slice created by Spring Boot. The key is that `webAppContextSetup` uses beans and MVC infrastructure already present in the context rather than building a separate MVC configuration around the controller.

### What Is Used from the Context?

Depending on the loaded configuration, this approach can include:

- Controllers and beans registered in `WebApplicationContext`.
- Spring MVC's `HandlerMapping` and `HandlerAdapter`.
- Message converters and request/response content configuration.
- Formatters, converters, and validators configured in MVC.
- Registered interceptors, controller advice, and exception resolvers.
- View resolvers and other MVC components in the context.
- Dependent beans injected into controllers and web components.

Thus, tests can uncover errors in wiring MVC configuration and beans, such as a missing custom converter or improperly registered controller advice. If a test uses a simplified test context, it only verifies that simplified configuration; to verify the production configuration, you must load the actual production configuration under test.

### Context-Based Does Not Automatically Mean Every Servlet Filter Runs

`webAppContextSetup` uses the web application context to configure Spring MVC. If a test needs a specific servlet filter in MockMvc's request chain, register that filter appropriately, such as with `addFilters(...)` or the relevant library's integration mechanism. With Spring Security, projects typically use the corresponding test setup such as `springSecurity()` from Spring Security Test.

Do not assume that a filter declared in the deployment environment is automatically included in every MockMvc test. Verify that the test setup actually adds the filter or security filter chain under test.

## 4. Comparing the Two Setup Approaches

| Criterion | `standaloneSetup(...)` | `webAppContextSetup(...)` |
| --- | --- | --- |
| Input | Controllers passed directly | A loaded `WebApplicationContext` |
| Application context initialization | Does not load the application's context | Uses the context created by Spring Test or supplied |
| MVC infrastructure | Builder creates needed infrastructure and allows customization | Uses MVC infrastructure registered in the context |
| Controllers | Test specifies controllers | Controllers are obtained from the context via MVC configuration |
| Controller advice, converters, validators, interceptors | Usually must be registered explicitly in the builder if needed by the test | Used if already registered in the context |
| Controller dependencies | Passed directly by the test, typically as mocks or fakes | Injected by Spring from the context |
| Verification scope | Focused on controllers and configuration declared in the builder | Integration of controllers with the web context and loaded MVC configuration |
| Speed and isolation | Usually faster and more isolated | Usually takes time to build the context, which Spring can cache |
| Context configuration errors | Not aimed at catching application context configuration errors | Can catch errors in the loaded context |

Both approaches use Spring Test's simulated requests and responses. Neither starts a real Servlet container and neither tests opening HTTP ports, TLS, WAR deployment, or request handling through a network connector.

## 5. Decision Criteria: What Needs to Be Verified?

Frame the test goal as a concrete question before choosing a builder.

| Question to Answer | Usually Suitable Choice | Reason |
| --- | --- | --- |
| Does the controller call the service and return the right JSON for this input? | `standaloneSetup` | Only needs the controller and dependencies controlled in the test |
| Does the controller return the right status and headers when the service reports an error? | `standaloneSetup` if required advice is registered | Can control service outcomes and the exception handler supplied by the test |
| Does the controller work with configured production converters or formatters? | `webAppContextSetup` | Needs to use MVC configuration from the context |
| Does `@ControllerAdvice` declared in the application handle exceptions properly? | `webAppContextSetup` | Needs to confirm advice is registered and applied by the context |
| Does a custom interceptor or argument resolver participate in request processing? | `webAppContextSetup` | Needs components configured in the MVC context |
| Does a single controller work without loading the entire application configuration? | `standaloneSetup` | Small scope, easy to isolate, and fast |
| Do multiple MVC components collaborate properly in the loaded web configuration? | `webAppContextSetup` | Suitable for testing integration within the Spring web context |
| Does the application accept real HTTP requests over a network port? | Embedded server or real container | Both builders run in a mock environment |

There is no rule that one test type is always better than the other. The choice depends on the risks the test needs to detect. If a bug could reside in production MVC configuration, a test using only the standalone builder will not provide sufficient evidence.

## 6. Example: Testing the Same Controller for Two Different Goals

Suppose `GreetingController` handles `GET /greetings/{name}` by calling `GreetingService`.

### Goal A: Testing the Controller's Decisions

We want to confirm that the controller passes the right name to the service and returns the service result as JSON. We do not need to test component scanning or the application's custom converters. In that case:

```java
@ExtendWith(MockitoExtension.class)
class GreetingControllerBehaviorTest {

    @Mock
    GreetingService greetingService;

    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new GreetingController(greetingService))
                .build();
    }

    @Test
    void passesPathVariableToService() throws Exception {
        when(greetingService.greet("Lan"))
                .thenReturn(new GreetingResponse("Hello, Lan"));

        mockMvc.perform(get("/greetings/Lan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, Lan"));

        verify(greetingService).greet("Lan");
    }
}
```

This test verifies that the simulated request maps to the supplied controller, the path parameter is bound, and the controller invokes the service properly. Because the service is a mock, the test does not verify that the service or database works properly.

### Goal B: Testing the Loaded MVC Configuration

Suppose the application registers a `@RestControllerAdvice` to convert `GreetingNotFoundException` into an HTTP 404 response. To verify that the advice is actually discovered and applied from Spring configuration, load a context containing both the controller and advice and use `webAppContextSetup`.

```java
class GreetingNotFoundException extends RuntimeException {

    GreetingNotFoundException(String name) {
        super(name);
    }
}

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(GreetingNotFoundException.class)
    ResponseEntity<Map<String, String>> handleNotFound(
            GreetingNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Collections.singletonMap("error", exception.getMessage()));
    }
}
```

```java
@Configuration
@EnableWebMvc
class GreetingWebConfig {

    @Bean
    GreetingService greetingService() {
        return name -> {
            throw new GreetingNotFoundException(name);
        };
    }

    @Bean
    GreetingController greetingController(GreetingService service) {
        return new GreetingController(service);
    }

    @Bean
    ApiExceptionHandler apiExceptionHandler() {
        return new ApiExceptionHandler();
    }
}
```

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = GreetingWebConfig.class)
class GreetingControllerMvcConfigurationTest {

    @Autowired
    WebApplicationContext webApplicationContext;

    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();
    }

    @Test
    void appliesControllerAdviceFromWebContext() throws Exception {
        mockMvc.perform(get("/greetings/{name}", "Lan"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("Lan"));
    }
}
```

In this example, the service intentionally throws an exception so the test focuses on how Spring MVC handles exceptions. `ApiExceptionHandler` is a bean in the web context; the test verifies that Spring MVC's exception resolver uses that advice to produce a 404 response.

If you switch this test to `standaloneSetup(new GreetingController(service))` without calling `.setControllerAdvice(new ApiExceptionHandler())`, the advice is not automatically discovered from the application configuration because no application context is loaded. The test may receive a different response than in the production configuration. This is a classic example of choosing a builder based on the scope under test.

## 7. Using Spring Boot Test Types

In Spring Boot applications, several annotations help prepare `MockMvc` without writing all the setup manually.

### `@WebMvcTest`

`@WebMvcTest` creates a Spring MVC test slice focusing on selected web components. It is usually appropriate when you want to test controllers together with Boot's auto-configured MVC setup without initializing all services, repositories, and other application components.

Dependencies outside the slice are typically provided using mock beans or test configurations suited to the Spring Boot version in use. `@WebMvcTest` is a Spring context-based test; it is not equivalent to manually passing controllers to `standaloneSetup`.

### `@SpringBootTest` Combined with `@AutoConfigureMockMvc`

If many application beans and configurations need to participate together, you can use:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ApplicationMvcIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void servesConfiguredEndpoint() throws Exception {
        mockMvc.perform(get("/health-view"))
                .andExpect(status().isOk());
    }
}
```

This is a broader Spring context test with MockMvc. If only an MVC slice is needed, `@WebMvcTest` is usually more economical. If only a single controller needs testing without application configuration, standalone setup may suffice.

When you need to test HTTP over a network port, use `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` or deploy the application to the target container and send real HTTP requests. `@AutoConfigureMockMvc` still uses a mock environment; it does not turn the test into a network test on its own.

## 8. Common Setup Selection Mistakes

### Using standalone While Expecting Component Scan to Discover Beans

The standalone builder accepts only the passed controllers and components registered on the builder. It does not scan packages to automatically discover the application's controller advice, interceptors, converters, or validators. If the goal is to test components discovered from Spring configuration, use context-based setup or register them explicitly in the standalone test.

### Using webAppContextSetup While Loading a Context Missing Required Configuration

`webAppContextSetup` only uses what the supplied context has loaded. If the test context omits a converter, security configuration, or production controller advice, the test cannot verify that component. Check whether the test configuration accurately reflects the portion of the application required by the test goal.

### Using the Full Application Context for Every Controller Test

Loading the entire application can slow down tests, increase coupling to databases or external services, and make failures harder to isolate. If the goal is simply binding, status codes, and responses of one controller, a standalone test can provide faster feedback. Reserve broad context tests for behaviors that genuinely need integration.

### Assuming MockMvc Proves Proper Container Deployment

Both standalone and context-based setups process simulated requests. They do not test HTTP connectors, TLS, deployment descriptors, real context paths, or the startup lifecycle of Tomcat/Jetty/Undertow. Use an embedded server or a real container for those requirements.

### Over-Verifying Internal Calls in Standalone Tests

Mocking services helps control data and verify necessary interactions. However, controller tests should prioritize observable HTTP behavior. Only verify service calls when argument passing or operation selection is a critical part of the behavior; avoid coupling tests to every implementation detail.

## 9. Workflow for Choosing and Organizing Tests

You can apply the following workflow to each group of controllers:

1. State clearly what must be proven: isolated controller behavior, integration with MVC configuration, or real HTTP runtime.
2. List the mandatory participating components: controllers, services, advice, converters, validators, interceptors, filters, security chain, and other beans.
3. If only the controller and controllable dependencies are needed, start with `standaloneSetup`.
4. If beans and configuration registered in the Spring web context are needed, use `webAppContextSetup` or an appropriate Spring Boot test slice.
5. If you need to verify requests over an HTTP port or container behavior, use an embedded server or a real deployment container.
6. Keep tests at the smallest scope that can fully answer the question; add broad context tests for risks that standalone tests cannot catch.

| Scope | Suggested Test Type |
| --- | --- |
| Single controller, mocked service, JSON response | Standalone MockMvc |
| Controller with configured controller advice, converters, interceptors | Context-based MockMvc |
| MVC slice in Spring Boot | `@WebMvcTest` |
| Multiple application layers participating while still using mock requests | `@SpringBootTest` + `@AutoConfigureMockMvc` |
| Real HTTP requests through an embedded server | `@SpringBootTest(webEnvironment = RANDOM_PORT)` |
| Deployment on an external container | Test on the target container |

## 10. Conclusion

`standaloneSetup(...)` is suitable when you want to test controllers in a small MVC environment where the test actively supplies controllers, dependencies, and additional configurations. `webAppContextSetup(...)` is suitable when you want to test controllers within a `WebApplicationContext` together with the loaded MVC infrastructure and beans.

Choose based on which components must participate and what kinds of bugs need to be caught. Standalone keeps controller tests isolated, fast, and explicit about dependencies; context-based validates MVC configuration and coordination among beans in the web context. When requirements involve HTTP networking or a real Servlet container, a test tier with a real server/container is required because both MockMvc setup styles run in a simulated environment.
