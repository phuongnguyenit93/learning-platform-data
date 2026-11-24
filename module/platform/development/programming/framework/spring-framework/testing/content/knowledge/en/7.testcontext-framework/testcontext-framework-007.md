# @SpringJUnitWebConfig for Web Testing

When testing a Spring MVC application, sometimes we need more than a directly instantiated controller. We want Spring to load web configuration, create MVC beans, register controllers, converters, exception resolvers, and related components inside an environment with a ServletContext. **@SpringJUnitWebConfig** serves that exact need in the Spring TestContext Framework for JUnit Jupiter.

This annotation combines Spring's JUnit Jupiter integration, loads application configuration, and enables web context semantics for the test. As a result, the test can receive a Spring-managed WebApplicationContext and use it to verify web behavior, typically together with MockMvc.

Remember that @SpringJUnitWebConfig prepares a web application context for testing. It does not automatically start a real HTTP server and does not create MockMvc on its own. The test author still needs to select application configuration, register required beans, and build an appropriate test client.

## 1. What Is @SpringJUnitWebConfig?

@SpringJUnitWebConfig is a composed annotation in Spring Test, located in the package:

~~~java
import org.springframework.test.context.junit.jupiter.web.SpringJUnitWebConfig;
~~~

It combines annotations that are commonly declared together:

- **@ExtendWith(SpringExtension.class):** connects the Spring TestContext Framework with JUnit Jupiter. Spring can manage the test instance, inject dependencies into the test, run callbacks, and apply TestContext features.
- **@ContextConfiguration:** specifies how to load the ApplicationContext from configuration classes, XML resources, or initializers.
- **@WebAppConfiguration:** instructs TestContext to create a WebApplicationContext instead of a standard ApplicationContext and sets the web resource root for the ServletContext.

Thanks to this combination, a test class can write:

~~~java
@SpringJUnitWebConfig(classes = WebTestConfig.class)
class GreetingControllerTest {
    // Spring injects WebApplicationContext and other dependencies.
}
~~~

Instead of declaring separately:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = WebTestConfig.class)
@WebAppConfiguration
class GreetingControllerTest {
}
~~~

Both forms express the same configuration goal. Using @SpringJUnitWebConfig keeps the test class concise and makes clear that this is a JUnit Jupiter test requiring a web application context.

### 1.1. This Annotation Is for JUnit Jupiter

@SpringJUnitWebConfig belongs to Spring Test's JUnit Jupiter integration. It supplies SpringExtension via meta-annotation, so the test class does not need to repeat @ExtendWith(SpringExtension.class).

With JUnit 4, the typical configuration is @RunWith(SpringRunner.class), combined with @ContextConfiguration and @WebAppConfiguration. You cannot use @SpringJUnitWebConfig as a drop-in replacement for the JUnit 4 runner.

### 1.2. How Does WebApplicationContext Differ from a Standard ApplicationContext?

ApplicationContext manages beans and services of a Spring application. WebApplicationContext extends that model for a web environment, bound to a ServletContext and required web components.

In an MVC application, WebApplicationContext can contain:

- Controllers and beans used by controllers.
- RequestMappingHandlerMapping and RequestMappingHandlerAdapter.
- HttpMessageConverter instances to read requests and write responses.
- HandlerExceptionResolver instances to map exceptions.
- LocaleResolver, ViewResolver, and other MVC components.
- Interceptors or web beans configured in the application.

WebApplicationContext lets tests verify MVC configuration inside a simulated web environment. It does not mean the application is running inside Tomcat, Jetty, or a real servlet container.

## 2. Main Configuration Attributes

@SpringJUnitWebConfig provides attributes to forward configuration to the underlying annotations it combines.

| Attribute | Purpose |
| --- | --- |
| classes | Configuration classes used to create the context |
| locations | Paths to configuration resources, typically XML |
| initializers | ApplicationContextInitializer classes to run when creating the context |
| inheritLocations | Governs how locations are inherited from a parent test class |
| inheritInitializers | Governs how initializers are inherited |
| loader | Selects the appropriate ContextLoader |
| name | Context name in certain TestContext configurations |
| resourcePath | Web resource root path for @WebAppConfiguration |

In most new projects, classes is the readable choice for Java configuration. locations remains useful when the application uses XML or needs to test an existing XML configuration.

### 2.1. Using classes with Java Configuration

~~~java
@SpringJUnitWebConfig(classes = WebTestConfig.class)
class GreetingControllerTest {
}
~~~

Spring loads WebTestConfig and the beans it declares. If the configuration needs to import other configurations, use @Import inside the configuration class or declare the appropriate test configuration.

### 2.2. Using locations with XML

~~~java
@SpringJUnitWebConfig(
    locations = "classpath:/spring/test-web-context.xml"
)
class LegacyWebControllerTest {
}
~~~

Spring loads the XML resource from the specified location. Classpath paths usually fit files placed in test resources. For filesystem resources, use path syntax compatible with ContextLoader and the build environment.

Do not declare multiple configuration sources simultaneously just to get a test to start. Choose configuration that reflects the exact scope being tested and ensure key beans are created the way the application expects.

### 2.3. resourcePath and the Web Resource Root

@SpringJUnitWebConfig lets you set resourcePath, the attribute corresponding to @WebAppConfiguration. By default, the web resource root is:

~~~text
src/main/webapp
~~~

If the test needs a separate web directory, you can specify:

~~~java
@SpringJUnitWebConfig(
    classes = WebTestConfig.class,
    resourcePath = "src/test/webapp"
)
class StaticResourceWebTest {
}
~~~

resourcePath specifies the web resource root used to build the simulated ServletContext. It is not a path for bean configuration; that responsibility belongs to classes or locations.

Distinguish clearly:

- classes/locations: where Spring reads configuration to create beans and the WebApplicationContext.
- resourcePath: which directory the ServletContext sees web resources from.

If the application does not have traditional web resources or the test does not verify resource lookups, you can keep the default or configure a resource root matching the project layout. Do not change resourcePath merely to relocate an XML file.

## 3. Preparing Web Configuration for Tests

@SpringJUnitWebConfig does not automatically infer the entire MVC configuration of an application. The test needs to specify one or more configuration classes containing the appropriate beans.

The small example below uses plain Spring MVC:

~~~java
@FunctionalInterface
interface GreetingService {
    String greet(String name);
}

@RestController
@RequestMapping("/greetings")
class GreetingController {
    private final GreetingService greetingService;

    GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping(
        value = "/{name}",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    String greet(@PathVariable String name) {
        return greetingService.greet(name);
    }
}
~~~

Web configuration:

~~~java
@Configuration
@EnableWebMvc
class WebTestConfig {

    @Bean
    GreetingService greetingService() {
        return name -> "Hello, " + name;
    }

    @Bean
    GreetingController greetingController(
            GreetingService greetingService) {
        return new GreetingController(greetingService);
    }
}
~~~

@EnableWebMvc registers the required Spring MVC infrastructure. GreetingController is registered as a bean so MVC can discover its mappings. In real projects, configuration can use @ComponentScan, @Import, or existing web configuration instead of this explicit declaration.

There is no need to create a brand-new configuration solely for tests if the application already has suitable web configuration that tests can load safely. However, slice tests or small context tests can often use a minimal configuration to focus on the behavior under test.

## 4. Example: Testing a Controller with MockMvc

A common pattern is loading WebApplicationContext with @SpringJUnitWebConfig, then creating MockMvc from that context.

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.web.SpringJUnitWebConfig;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

@SpringJUnitWebConfig(classes = WebTestConfig.class)
class GreetingControllerTest {

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
    void returns_greeting_for_requested_name() throws Exception {
        mockMvc.perform(get("/greetings/{name}", "An"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.TEXT_PLAIN
            ))
            .andExpect(content().string("Hello, An"));
    }
}
~~~

The example uses MockMvc to dispatch a request through the MVC infrastructure loaded into WebApplicationContext. The test verifies:

1. The URL maps to the controller.
2. The path variable binds to the name parameter.
3. The controller calls the service and produces the response content.
4. Spring MVC returns HTTP 200 with the contracted content type and body.

MockMvc does not open a TCP port and does not send requests over the network. It processes requests inside a simulated servlet environment, allowing verification of the MVC stack without starting a server.

### 4.1. Why Use webAppContextSetup?

MockMvcBuilders has multiple ways to construct MockMvc. Two common options:

| Builder Method | Scope |
| --- | --- |
| webAppContextSetup(WebApplicationContext) | Uses the loaded WebApplicationContext, suitable when verifying MVC configuration and web beans in the context |
| standaloneSetup(controller) | Builds MVC infrastructure for the specified controller, suitable for isolated controller tests with minimal setup |

When using @SpringJUnitWebConfig, webAppContextSetup leverages the very WebApplicationContext created by TestContext. It sends the test through mappings, converters, resolvers, and configuration registered in the context.

standaloneSetup does not require @SpringJUnitWebConfig in many cases, because the test can instantiate the controller directly. That approach is fast and lean, yet does not prove that the application's MVC configuration loads properly.

### 4.2. Testing Invalid Requests

Suppose a controller accepts a request body and uses Bean Validation:

~~~java
public record CreateGreetingRequest(
    @NotBlank String name
) {}

@RestController
@RequestMapping("/api/greetings")
class GreetingApiController {

    @PostMapping
    ResponseEntity<String> create(
            @Valid @RequestBody CreateGreetingRequest request) {
        return ResponseEntity.ok("Hello, " + request.name());
    }
}
~~~

A web context test can send an invalid body:

~~~java
mockMvc.perform(post("/api/greetings")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"name": ""}
            """))
    .andExpect(status().isBadRequest());
~~~

For this example to run, the classpath needs an appropriate validation provider and MVC configuration must register the required components. In Spring Boot, the validation starter typically provides the relevant dependencies. With plain Spring Framework, declare the provider and matching dependencies explicitly.

The test above only checks status. If the API promises a specific error structure, verify the fields, error codes, or stable messages per contract as well. Avoid asserting on full internal exception details when they are not part of the committed API contract.

### 4.3. Testing Exception Mapping

A WebApplicationContext can include @ControllerAdvice or HandlerExceptionResolver. Using webAppContextSetup lets tests verify that exceptions are translated into responses according to the loaded MVC configuration.

Example:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<String> handleIllegalArgument(
            IllegalArgumentException exception) {
        return ResponseEntity.badRequest().body(exception.getMessage());
    }
}
~~~

The test can configure the controller to throw IllegalArgumentException and verify both status and response body. The goal is to prove the exception passes through MVC exception resolution in the context, not merely that a Java method catches an exception.

## 5. WebApplicationContext and ServletContext in Tests

With @SpringJUnitWebConfig, a test can inject web objects:

~~~java
@SpringJUnitWebConfig(classes = WebTestConfig.class)
class WebContextTest {

    @Autowired
    WebApplicationContext webApplicationContext;

    @Autowired
    ServletContext servletContext;

    @Test
    void loads_a_web_application_context() {
        assertThat(webApplicationContext).isNotNull();
        assertThat(servletContext).isNotNull();
        assertThat(webApplicationContext.getServletContext())
            .isSameAs(servletContext);
    }
}
~~~

The ServletContext in this environment is typically a MockServletContext provided by Spring Test. It simulates capabilities needed for web testing, such as accessing resources and servlet metadata. It is not the ServletContext of a running Tomcat instance.

Injecting WebApplicationContext is helpful when you need to:

- Build MockMvc from the full MVC context.
- Access web configuration beans.
- Inspect servlet context resources.
- Verify registered interceptors, converters, or exception resolvers.
- Construct a test component requiring WebApplicationContext.

Do not treat asserting that the context started successfully as sufficient proof that all endpoints work. Send requests or verify specific behaviors matching the test goal.

## 6. Combining with TestContext Framework Annotations

@SpringJUnitWebConfig is a starting point. It can be combined with other Spring TestContext annotations to control the environment.

### 6.1. @ActiveProfiles

If the application has profile-specific configuration, @ActiveProfiles specifies profiles activated during the test:

~~~java
@SpringJUnitWebConfig(classes = WebTestConfig.class)
@ActiveProfiles("test")
class ProfiledWebTest {
}
~~~

Beans or properties selected by profile are applied when creating the context. Use test profiles containing only necessary configuration, avoiding production credentials or external endpoints in tests.

### 6.2. @TestPropertySource

@TestPropertySource can supply test-specific properties:

~~~java
@SpringJUnitWebConfig(classes = WebTestConfig.class)
@TestPropertySource(properties = {
    "app.web.greeting-prefix=Hello",
    "app.web.feature-enabled=true"
})
class GreetingConfigurationTest {
}
~~~

Properties are loaded into the TestContext's Environment. To test binding into @ConfigurationProperties or @Value, inject the bean and verify behavior using those values.

### 6.3. @DirtiesContext

The TestContext Framework caches ApplicationContext instances for reuse across tests with the same configuration. If a test alters the context in an unrecoverable way that affects other tests, @DirtiesContext can mark the context for eviction from the cache.

Do not use @DirtiesContext as a routine way to clean up data. For database state, use transactions, fixtures, and boundary-appropriate cleanup. @DirtiesContext forces the context to be recreated, which can slow down the suite significantly.

### 6.4. @ContextHierarchy

Some web applications have a root context and a servlet-specific context. @ContextHierarchy allows describing multiple ApplicationContext levels when the application architecture requires them.

Conceptual example:

~~~java
@ContextHierarchy({
    @ContextConfiguration(classes = RootConfig.class),
    @ContextConfiguration(classes = WebConfig.class)
})
@WebAppConfiguration
@ExtendWith(SpringExtension.class)
class HierarchicalWebContextTest {
}
~~~

If a hierarchy is not needed, do not add it merely because the application has multiple configuration packages. A single context is usually easier to understand and easier to cache.

## 7. Distinguishing @SpringJUnitWebConfig from Other Options

Spring's web testing annotations serve different goals. Choosing the right annotation keeps test scope clear.

| Option | Source | Goal | Auto-creates MockMvc? | Real server? |
| --- | --- | --- | --- | --- |
| @SpringJUnitWebConfig | Spring Framework Test | Loads WebApplicationContext per specified config for JUnit Jupiter | No | No |
| @SpringJUnitConfig | Spring Framework Test | Loads standard ApplicationContext for JUnit Jupiter | No | No |
| @WebAppConfiguration + @ContextConfiguration | Spring Framework Test | Separately declares web context and context configuration | No | No |
| @WebMvcTest | Spring Boot Test | MVC slice with Boot auto-configuration and web-layer bean scoping | Depends on Boot test config; typically uses MockMvc | No |
| @SpringBootTest + @AutoConfigureMockMvc | Spring Boot Test | Loads Boot application context and configures MockMvc | Yes | No |
| @SpringBootTest with RANDOM_PORT | Spring Boot Test | Runs the application via an embedded web server | No need for MockMvc | Yes |

### 7.1. Compared to @SpringJUnitConfig

@SpringJUnitConfig combines SpringExtension and ContextConfiguration to create a standard ApplicationContext. It suits service or repository tests that use Spring configuration without needing a WebApplicationContext.

@SpringJUnitWebConfig adds a web application context. If a test needs ServletContext, MVC infrastructure, or MockMvc built from WebApplicationContext, use the web annotation.

Do not use @SpringJUnitWebConfig for a service unit test simply because the class belongs to a web application. Creating a web context makes the test heavier without adding evidence if the behavior is unrelated to web concerns.

### 7.2. Compared to @WebAppConfiguration and @ContextConfiguration

You can declare the three annotations separately:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = WebTestConfig.class)
@WebAppConfiguration
class ExplicitWebContextTest {
}
~~~

@SpringJUnitWebConfig is a shorthand for this common combination and provides aliases to configure attributes of the underlying annotations. When each piece needs to be highlighted explicitly, the expanded form remains useful in documentation or tests with specialized configuration.

### 7.3. Compared to @WebMvcTest

@WebMvcTest is a Spring Boot Test annotation. It creates an MVC-focused slice and applies Spring Boot auto-configuration, typically loading only beans within the required web scope. Controller collaborators are usually replaced with mocks.

@SpringJUnitWebConfig belongs to the Spring Framework TestContext Framework. It loads WebApplicationContext from specified classes or locations. It does not apply Spring Boot's slice rules automatically and does not restrict beans the same way @WebMvcTest does.

Choose @WebMvcTest when testing the MVC slice of a Spring Boot application. Choose @SpringJUnitWebConfig when configuring a web context explicitly via Spring TestContext, especially in non-Boot Spring MVC applications or when a custom web context is needed.

### 7.4. Compared to @SpringBootTest

@SpringBootTest initializes a Spring Boot application context per application configuration. When paired with @AutoConfigureMockMvc, tests can use MockMvc without opening a server. When using webEnvironment = RANDOM_PORT, Spring Boot starts an embedded server on a random port.

@SpringJUnitWebConfig does not boot a Spring Boot application via the @SpringBootTest mechanism. It loads the specified Spring configuration and creates a web context for TestContext. If the goal is verifying Boot auto-configuration, application properties, server startup, or full Boot application wiring, use the appropriate Boot tooling.

## 8. @SpringJUnitWebConfig Does Not Start an HTTP Server

This is a common point of confusion when starting out with this annotation.

@WebAppConfiguration causes TestContext to create a WebApplicationContext and a simulated ServletContext. MockMvc dispatches requests directly through Spring MVC test infrastructure. No TCP socket is opened and no real HTTP request travels over the network.

If you need to test:

- Port binding.
- Embedded Tomcat/Jetty/Undertow.
- Servlet container behavior.
- HTTP connectors, compression, or network timeouts.
- TLS or reverse proxy integration.

then a WebApplicationContext with MockMvc is not enough. Use @SpringBootTest(webEnvironment = RANDOM_PORT) or stand up an appropriate container/server environment.

Conversely, if you need to verify mappings, validation, converters, exception handlers, or interceptors, MockMvc usually provides suitable evidence without needing a real server.

## 9. Configuring Dependencies and Test Doubles

@SpringJUnitWebConfig does not dictate that every collaborator must be a real bean. Tests can combine a real context with test double beans at appropriate boundaries.

For example, a real controller and real MVC infrastructure can use a stub/mock service to test response mapping. Test beans can be registered with @TestConfiguration or using a bean override mechanism compatible with your Spring version.

~~~java
@TestConfiguration
class GreetingTestBeans {

    @Bean
    @Primary
    GreetingService greetingService() {
        return name -> "Test greeting for " + name;
    }
}
~~~

Then import the configuration into the test:

~~~java
@SpringJUnitWebConfig(classes = {
    WebTestConfig.class,
    GreetingTestBeans.class
})
class GreetingControllerWithTestServiceTest {
}
~~~

In this example, if both WebTestConfig and GreetingTestBeans register a GreetingService bean under the same conditions, understand the bean selection rules carefully. @Primary helps Spring prefer the test bean for by-type injection, yet having two beans present can still affect injection by name or into collections. Another approach is creating a separate test configuration that registers only the needed beans.

If a test aims to verify full application behavior, do not replace real services just to simplify setup. If the goal is solely the controller contract, replacing the service is reasonable because the test does not claim to verify service business logic.

## 10. Context Caching and Test Independence

The Spring TestContext Framework caches ApplicationContext instances across tests when configurations are equivalent. This reduces startup time. @SpringJUnitWebConfig participates in that mechanism through context configuration metadata.

To keep tests stable:

- Do not alter bean definitions or shared singleton state across tests.
- Create independent test data.
- Clean up database state using transactions or appropriate cleanup.
- Avoid modifying global ServletContext state without restoring it.
- Use @DirtiesContext only when the test genuinely renders the context non-reusable.

If one test needs different properties or beans than the rest, TestContext may create a separate context due to the differing configuration. This is correct for isolation but can make the suite expensive. Organize tests into stable configuration groups where possible.

### 10.1. Do Not Arbitrarily Share Mutable MockMvc Setup

MockMvc can often be built once from WebApplicationContext and reused if its configuration is immutable. If tests need different filters, default requests, or custom builders, create separate configurations or build separate instances per test group.

Do not mutate the state of a shared object across tests running in parallel. For tests with mutable fakes or mock state, recreate them per test or use an appropriate lifecycle.

### 10.2. Transactions in Web Tests

TestContext can manage transactions for test methods when appropriate transaction configuration is present. However, MockMvc and a real server have different execution boundaries.

With MockMvc, requests are usually processed in the same process and thread that invokes the test. Depending on how transactions are configured, persistence operations may participate in the test transaction. With a server running on a random port, requests are handled on a server thread, and the test transaction on the client thread does not automatically span the request's transaction.

Therefore, do not assume @Transactional on a test method will roll back changes created by an HTTP request to a real server. Identify transaction boundaries and verify post-request data according to the actual environment.

## 11. Testing Resources and Servlet-Specific Behavior

Another reason to use @SpringJUnitWebConfig is testing behavior that depends on ServletContext or the web resource root.

For example, the application might read a resource from ServletContext, use servlet configuration, or require a component initialized in the web context. In that case:

1. Choose the appropriate resourcePath.
2. Place test resources in the corresponding directory.
3. Load WebApplicationContext with @SpringJUnitWebConfig.
4. Inject ServletContext or the bean under test.
5. Verify behavior through the web/resource API rather than merely asserting that the context exists.

Do not use resourcePath as a replacement for Spring classpath resources. Classpath resources, bean configuration files, and ServletContext web resources resolve differently.

If a modern application serves static resources from a separate frontend or CDN, testing ServletContext resources may no longer reflect the production path. Test web resources only when that is genuinely a Spring application responsibility.

## 12. Common Mistakes

### Missing Bean Configuration for Controllers

@SpringJUnitWebConfig creates a WebApplicationContext but does not automatically find every class in the project if the configuration does not declare component scanning or beans. When requests return 404, verify that the controller is registered and RequestMappingHandlerMapping picked up the mappings.

### Confusing resourcePath with locations

locations points to context configuration. resourcePath points to the ServletContext web application root. Mixing up these attributes can prevent Spring from finding configuration or resources.

### Assuming the Annotation Auto-Creates MockMvc

@SpringJUnitWebConfig only loads the web context. The test must build MockMvc via webAppContextSetup or use another test configuration that supplies a suitable client.

### Using @SpringJUnitWebConfig to Test Boot Auto-Configuration

This annotation belongs to Spring Framework Test and does not automatically trigger the @SpringBootTest workflow. If the goal is Boot auto-configuration or server startup, use Spring Boot Test annotations.

### Using MockMvc to Conclude Network/Server Behavior

MockMvc does not test ports, sockets, TLS, or a running servlet container. Use RANDOM_PORT or a real server/container when that is the goal.

### Loading Too Much Configuration

A huge context slows down tests and makes failures harder to isolate. Load only the configuration needed for the behavior under test. If a test needs the entire application, clearly mark it as an integration test.

### Mocking the Wrong Part Under Test

If testing an exception resolver while replacing the controller or resolver with a mock, the test may bypass the critical path. Keep the target component real and replace collaborators outside the scope.

### Forgetting Web or Servlet Dependencies

Spring MVC needs matching dependencies and the appropriate Servlet API. If missing from the classpath, WebApplicationContext or MVC infrastructure may fail to initialize. Check test module dependencies and the Spring version in use.

## 13. Process for Building a Web Test with @SpringJUnitWebConfig

You can follow this workflow:

**Step 1 – Identify the goal.** Clarify whether the test needs to verify controller mappings, validation, exception handling, interceptors, resources, or the full HTTP server.

**Step 2 – Choose the layer.** If you need Spring WebApplicationContext and MVC infrastructure without Boot auto-configuration, consider @SpringJUnitWebConfig. If you need a Boot MVC slice, consider @WebMvcTest. If you need a real server, use @SpringBootTest with RANDOM_PORT or an equivalent environment.

**Step 3 – Choose context configuration.** Use classes for Java configuration or locations for XML. Load only necessary beans.

**Step 4 – Choose resourcePath.** Keep the default if suitable; change it when the test requires a dedicated web resource root.

**Step 5 – Inject WebApplicationContext.** Use @Autowired to receive the context managed by TestContext.

**Step 6 – Build MockMvc.** Use MockMvcBuilders.webAppContextSetup when verifying the loaded MVC configuration.

**Step 7 – Prepare data and collaborators.** Use fixtures, test beans, or mocks at appropriate boundaries. Keep the component the test needs to prove real.

**Step 8 – Send requests and assert.** Verify status, headers, response body, exception mapping, and contracted side effects.

**Step 9 – Clarify boundaries.** Document whether the test runs a real server, uses a real database, and which collaborators were replaced.

## 14. Example of a Complete Test Structure

A simple structure might look like this:

~~~text
src
├── main
│   ├── java
│   │   └── example
│   │       ├── GreetingController.java
│   │       ├── GreetingService.java
│   │       └── WebConfig.java
│   └── webapp
└── test
    ├── java
    │   └── example
    │       ├── WebTestConfig.java
    │       └── GreetingControllerTest.java
    └── resources
        └── spring
            └── test-web-context.xml
~~~

In practice, tests can load production configuration if it does not pull in unsuitable dependencies. Alternatively, tests can import a narrow configuration to verify the web contract specifically. The important part is that test configuration clearly expresses which beans and infrastructure participate.

## 15. Reviewing a @SpringJUnitWebConfig Test

When reading or reviewing a test class, ask yourself:

- Why does the test need WebApplicationContext?
- Do classes or locations match the scope?
- Does resourcePath need to be changed?
- Does the test need MockMvc or only the context?
- Is MockMvc built from WebApplicationContext or a standalone controller?
- Which controllers, converters, resolvers, and interceptors are running for real?
- Which collaborators are replaced and why?
- Is the test verifying MVC behavior or accidentally claiming to test server/network behavior?
- Does the test depend on shared state or dirty the context cache?
- Do assertions verify the observable contract?

A test class can be very short and still valuable if its boundaries are clear. Conversely, a test that loads the entire context and sends a request can still be weak if it only asserts status without verifying key results.

## Conclusion

@SpringJUnitWebConfig is a composed annotation for JUnit Jupiter combining SpringExtension, ContextConfiguration, and WebAppConfiguration to create a WebApplicationContext for testing. It is useful when tests need Spring Framework web configuration and want to leverage TestContext injection, lifecycle, and MVC infrastructure capabilities.

Remember that this annotation does not create MockMvc automatically and does not start a real HTTP server. When combined with MockMvcBuilders.webAppContextSetup, tests can verify mappings, binding, validation, exception handling, and MVC configuration in a simulated web context. If the goal is Boot auto-configuration, an embedded server, or network behavior, choose Spring Boot Test tooling or an appropriate server environment. Defining clear boundaries ensures tests produce solid evidence and prevents confusion about what was actually verified.
