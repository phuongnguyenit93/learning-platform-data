# Loading Spring MVC Configuration for Integration Testing

When testing a Spring MVC controller, we usually want to send mock requests through the exact components the application uses at runtime: `DispatcherServlet`, handler mappings, controllers, argument resolvers, message converters, exception resolvers, interceptors, and related beans. If you only instantiate a controller and pass it directly to `MockMvcBuilders.standaloneSetup(...)`, the test can verify the controller's logic, but it does not prove that the application's Spring MVC configuration is loaded and wired together correctly.

Spring Test provides `WebApplicationContext` and `MockMvcBuilders.webAppContextSetup(...)` to build integration tests at the web layer. `WebApplicationContext` holds the configuration for a web application, including MVC beans and `ServletContext`. When passing this context to `webAppContextSetup`, Spring Test creates a `MockMvc` instance that uses the loaded configuration to handle requests via a mock servlet API.

## 1. Why Is Loading `WebApplicationContext` Needed?

In a Spring MVC application, an HTTP request passes through a chain of components before reaching a controller method:

```text
HTTP request
    |
    v
Servlet container
    |
    v
DispatcherServlet
    |
    +--> HandlerMapping finds the matching handler
    |
    +--> HandlerInterceptor runs before the handler
    |
    +--> HandlerAdapter invokes the controller
    |
    +--> ArgumentResolver converts the request into Java parameters
    |
    +--> Controller processes the request
    |
    +--> ReturnValueHandler / HttpMessageConverter creates the response
    |
    +--> ExceptionResolver handles exceptions if any occur
    v
HTTP response
```

These components are configured and connected together in the Spring MVC environment. For example, a controller might work properly when invoked directly, yet the actual route is not registered because component scanning targets the wrong package. An endpoint returning a DTO might work with the default converter, yet fail when the application uses a custom converter or Jackson configuration. An exception might be handled by `@ControllerAdvice`, yet a test that instantiates the controller in isolation will not load that advice.

Loading `WebApplicationContext` allows the test to go through the MVC configuration declared in the application. You can verify the interactions between controllers and the web infrastructure, rather than testing an isolated Java object alone.

`WebApplicationContext` extends `ApplicationContext` and adds the ability to work with `ServletContext`. In the Spring TestContext Framework, the `@WebAppConfiguration` annotation tells Spring that the test needs a web application context. The `@ContextConfiguration` annotation specifies the configuration source used to load beans.

## 2. Distinguishing `standaloneSetup` and `webAppContextSetup`

Spring MVC Test provides two common ways to create `MockMvc`:

| Creation method | Configuration used | Best-suited purpose |
| --- | --- | --- |
| `MockMvcBuilders.standaloneSetup(controller)` | Creates minimal MVC infrastructure for the passed controller; additional components can be customized. | Focused, fast controller testing with minimal dependence on application configuration. |
| `MockMvcBuilders.webAppContextSetup(wac)` | Uses the loaded `WebApplicationContext`, including MVC configuration and web application beans. | Integration testing of web configuration, mappings, converters, advice, interceptors, and bean wiring. |

Both approaches use `MockMvc` and can execute requests without starting a real HTTP server. The difference lies in the configuration source that `MockMvc` uses.

Example of `standaloneSetup`:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new GreetingController())
        .build();
```

The controller is instantiated directly. If the application has a `@ControllerAdvice`, interceptor, or custom message converter, the test must register those components individually if it wants to verify them. The application's MVC configuration is not loaded automatically just because the controller has `@RestController`.

With `webAppContextSetup`, you pass the context initialized by Spring Test:

```java
MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .build();
```

`MockMvc` uses the Spring MVC components from that context. This is the right choice when the test's goal is to confirm that the real web configuration works together with the controller.

## 3. Declaring Spring MVC Configuration for Tests

The example below uses Java configuration. `@EnableWebMvc` enables the Spring MVC infrastructure; `@ComponentScan` locates controllers and related web beans in the specified package.

```java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
@EnableWebMvc
@ComponentScan(basePackageClasses = GreetingController.class)
class WebConfig implements WebMvcConfigurer {
}
```

`basePackageClasses` helps specify the scan package based on a marker class. This avoids writing package names as strings, which easily break when packages are renamed. In a real application, you can use a marker in the root package containing controllers, or explicitly declare the scan scope according to the project structure.

Example controller:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
class GreetingController {

    @GetMapping("/{name}")
    GreetingResponse greeting(@PathVariable String name) {
        return new GreetingResponse("Hello, " + name);
    }
}

record GreetingResponse(String message) {
}
```

When Jackson is on the classpath, the default MVC configuration can use a JSON message converter to serialize the record into JSON. If the application has custom converter configuration, the integration test will use that configuration as long as it is loaded into the context.

If the controller depends on a service, the service must be a bean in the context. You can let component scanning detect `@Service`, or declare the bean in configuration. This allows Spring to perform dependency injection the same way the application is configured.

## 4. Using `@WebAppConfiguration` and `@ContextConfiguration`

With JUnit Jupiter, `SpringExtension` can be used to integrate the Spring TestContext Framework with JUnit 5. `@WebAppConfiguration` instructs Spring to create a `WebApplicationContext`, while `@ContextConfiguration` provides the configuration class used to load the context.

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.web.context.WebApplicationContext;

@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = WebConfig.class)
class GreetingControllerWebTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    @Test
    void contextIsLoaded() {
        // webApplicationContext can be used to build MockMvc.
    }
}
```

Each annotation has its own responsibility:

- `@ExtendWith(SpringExtension.class)` connects the JUnit Jupiter test lifecycle to the Spring TestContext Framework. Spring manages context creation and dependency injection into the test.
- `@WebAppConfiguration` requests a web-specific context type. Spring creates a `WebApplicationContext` along with a mock `ServletContext`.
- `@ContextConfiguration(classes = WebConfig.class)` specifies the Java configuration to load. `locations` can be used if the configuration is in XML.
- `@Autowired WebApplicationContext` retrieves the context created and managed by Spring Test.

If using XML configuration, it can be declared as:

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(locations = "classpath:test-mvc-context.xml")
class GreetingControllerWebTest {
    // ...
}
```

Do not declare both `classes` and `locations` for the same configuration unless intentionally combining configuration sources. Ensure the XML path exists on the test classpath and contains the MVC beans needed by the test.

`@WebAppConfiguration` has a `value` attribute to specify the resource base path for the web application. The default is `src/main/webapp`. If the test needs access to web resources in a different location, it can be explicitly declared, such as `@WebAppConfiguration("src/test/webapp")` or by using an appropriate classpath location. This resource base path relates to web resources and does not replace the bean configuration declared via `@ContextConfiguration`.

## 5. Building `MockMvc` from the Loaded Context

After Spring creates `WebApplicationContext`, use `MockMvcBuilders.webAppContextSetup(...)` to create the mock request dispatcher.

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

// Inside the test class:
private MockMvc mockMvc;

@BeforeEach
void setUp() {
    mockMvc = MockMvcBuilders
            .webAppContextSetup(webApplicationContext)
            .build();
}
```

`webAppContextSetup` accepts the Spring-managed context. When `build()` is called, Spring MVC Test prepares the `MockMvc` environment based on that web context. Requests are dispatched through `DispatcherServlet` in the mock servlet environment and handled by the application's mappings and handlers.

A complete test can send a GET request and verify the response:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

@Test
void shouldReturnGreetingAsJson() throws Exception {
    mockMvc.perform(get("/api/greetings/Lan")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.message").value("Hello, Lan"));
}
```

This test verifies multiple layers working together:

1. Handler mapping locates the `/api/greetings/{name}` endpoint.
2. Spring binds the value `Lan` to the `@PathVariable` parameter.
3. The controller returns `GreetingResponse`.
4. The message converter serializes the result into JSON.
5. `MockMvc` captures the HTTP status and response body for assertions to check.

If the route is not registered, the test typically receives status 404. If the converter cannot write the response in the requested media type, an error can occur while processing the response. These failures expose issues in the web configuration that a test invoking the controller directly would not reveal.

## 6. Testing MVC Components Loaded from the Context

The value of `webAppContextSetup` becomes clearer when the application has shared components. For instance, a `@ControllerAdvice` can standardize responses when a controller throws an exception.

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    ErrorResponse handleIllegalArgument(IllegalArgumentException exception) {
        return new ErrorResponse(exception.getMessage());
    }
}

record ErrorResponse(String message) {
}
```

The controller might throw an exception:

```java
@GetMapping("/validate")
GreetingResponse validate() {
    throw new IllegalArgumentException("Invalid greeting request");
}
```

If component scanning or configuration import has brought `ApiExceptionHandler` into `WebApplicationContext`, the test can verify the exception-handling output:

```java
mockMvc.perform(get("/api/greetings/validate"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.message").value("Invalid greeting request"));
```

Similarly, a complete MVC context can load and wire:

- `HandlerInterceptor` to run before and after controllers.
- `WebMvcConfigurer` to register formatters, converters, interceptors, CORS mappings, or resource handlers.
- `@ControllerAdvice` to handle exceptions and binding results across multiple controllers.
- Validators and validation configuration for request models.
- Custom argument resolvers and return value handlers.
- Beans used by controllers through dependency injection.

Example of configuring an interceptor. Suppose the interceptor is declared as a bean, for instance with `@Component`:

```java
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
class RequestAuditInterceptor implements HandlerInterceptor {
}
```

Then register the bean in the MVC configuration:

```java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
@EnableWebMvc
@ComponentScan(basePackageClasses = GreetingController.class)
class WebConfig implements WebMvcConfigurer {

    private final RequestAuditInterceptor requestAuditInterceptor;

    WebConfig(RequestAuditInterceptor requestAuditInterceptor) {
        this.requestAuditInterceptor = requestAuditInterceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(requestAuditInterceptor)
                .addPathPatterns("/api/**");
    }
}
```

When a test uses `webAppContextSetup`, the interceptor registered in the MVC config is invoked during request processing. If the test needs to verify interceptor behavior, send requests through `MockMvc` and check the observable effects rather than merely checking that the bean exists.

## 7. Root Context and Servlet Context in Multi-Tier Applications

A traditional Spring MVC application can split its context into two tiers:

- The root application context holds shared beans such as services, repositories, and infrastructure configuration.
- The servlet application context is a child context containing controllers, handler mappings, and MVC configuration for a `DispatcherServlet`.

The child context can access beans in the parent context. This organization is useful when an application has multiple servlets or needs to separate web configuration from business services.

Spring TestContext supports this structure with `@ContextHierarchy`:

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextHierarchy({
    @ContextConfiguration(name = "root", classes = RootConfig.class),
    @ContextConfiguration(name = "mvc", classes = WebConfig.class)
})
class GreetingControllerWebTest {

    @Autowired
    private WebApplicationContext webApplicationContext;
}
```

In this example, `RootConfig` represents the parent configuration and `WebConfig` represents the child web configuration. `WebConfig` can scan controllers and inject services from the parent context. When using a context hierarchy, keep bean boundaries clear: controllers and MVC configuration typically belong to the servlet context; shared services and repositories typically belong to the root context.

Not every application needs a hierarchy. For small applications or modern Java configurations, a single `WebApplicationContext` is usually sufficient. Use multiple tiers only when the application architecture genuinely has a root/servlet boundary or multiple servlet contexts.

## 8. Using Spring Boot Configuration in MVC Testing

In Spring Boot applications, loading configuration is typically performed through Boot's test annotations. Distinguish between two common options:

**`@SpringBootTest` combined with `@AutoConfigureMockMvc`** loads the application's application context and auto-configures `MockMvc`. This is the appropriate choice when you want broader integration testing, including web configuration and real application beans.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class GreetingControllerBootIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void shouldHandleGreetingRequest() throws Exception {
        mockMvc.perform(get("/api/greetings/Lan"))
                .andExpect(status().isOk());
    }
}
```

By default, `@SpringBootTest` uses a mock web environment when the application has an appropriate web application type. `MockMvc` dispatches requests through the mock servlet infrastructure without opening an HTTP port.

**`@WebMvcTest`** creates an MVC test slice, focusing on selected web components such as controllers, controller advice, converters, and relevant MVC configuration. Services or repositories are not automatically loaded as in a full application context; if a controller depends on a service, the test typically provides a mock bean for that dependency.

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;

@WebMvcTest(GreetingController.class)
class GreetingControllerSliceTest {
    // MockMvc is configured by Boot for the MVC slice.
}
```

`@WebMvcTest` is useful when focusing on a controller's HTTP contract. `@SpringBootTest` combined with `@AutoConfigureMockMvc` fits when you need to verify multiple configurations and beans working together. For Spring Framework without Boot, the pair `@WebAppConfiguration` and `@ContextConfiguration` with `webAppContextSetup` is the direct configuration approach.

Avoid mixing annotations mechanically. Choose one context-creation mechanism suited to the application type and test scope. Once using a Boot test slice, there is no need to manually create a second `WebApplicationContext` just to build `MockMvc`.

## 9. Filters and Spring Security in `MockMvc`

`WebApplicationContext` holds Spring beans, whereas servlet filters belong to the servlet chain. If the application has filters that must be tested, ensure those filters are registered in the `MockMvc` configuration or auto-configured by the testing mechanism in use.

With Spring Security, MVC tests typically need to integrate the security filter chain. In a Spring Security Test setup, `springSecurity()` can be applied when building `MockMvc` from the web context:

```java
mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

The snippet above requires importing `SecurityMockMvcConfigurers.springSecurity` and having the corresponding Spring Security configuration in the context along with the Spring Security test dependency. If the filter chain is omitted, a test might access an endpoint successfully even though real requests require authentication or authorization.

With Spring Boot, `@AutoConfigureMockMvc` registers filters in the application context by default; the `addFilters` attribute can adjust this behavior. If you intentionally disable filters in a test, understand that the test is bypassing part of the HTTP processing chain.

## 10. Context Reuse and Keeping Tests Stable

The Spring TestContext Framework includes an application context caching mechanism. Tests using the same context configuration can share an already initialized context, reducing test execution time. Therefore, there is no need to reinitialize `WebApplicationContext` in every test method.

`MockMvc` can be built once in `@BeforeEach` or stored in a shared field if its configuration does not change. Which approach fits depends on the customizers and state set up by the tests. Avoid mutating singleton beans or shared state inside the context directly, as that causes tests to depend on execution order.

`@DirtiesContext` marks a context to be evicted from the cache and recreated afterward. Use it only when a test genuinely alters context state or configuration in an unrecoverable way. Using this annotation excessively slows down tests and often masks shared-state design issues.

Several principles help keep integration tests stable:

1. Use explicit test configuration and load only the necessary packages.
2. Ensure controllers, advice, converters, and interceptors are within the scan scope or imported.
3. Verify requests through URLs, methods, headers, and bodies as an HTTP client would.
4. Assert on status, headers, and response body; when needed, also verify side effects in the service or persistence layer.
5. Avoid letting tests depend on data or state left over from previous tests.
6. Use a context hierarchy only when the application actually has separate root and servlet contexts.

## 11. Common Mistakes When Loading MVC Configuration

**Omitting `@WebAppConfiguration`.**

When a test needs `WebApplicationContext` but only uses plain `@ContextConfiguration`, Spring may create a non-web application context. Injecting `WebApplicationContext` or building `MockMvc` against a web context then lacks the right context type. Declare `@WebAppConfiguration` for plain Spring MVC tests.

**Having `@WebAppConfiguration` without a configuration source.**

This annotation determines the context type and mock web environment; it does not automatically find all controllers in the project. You must declare `@ContextConfiguration` with appropriate Java or XML config.

**Component scanning the wrong package.**

The context initializes successfully, yet controllers are not registered, causing requests to return 404. Check the marker class's package, `@ComponentScan` scope, and controller annotations.

**Not enabling or loading MVC configuration.**

With plain Java configuration, the configuration typically requires `@EnableWebMvc` along with `WebMvcConfigurer` if customizing MVC. With XML, the corresponding MVC namespace and elements must be declared. Do not assume that merely creating a `WebApplicationContext` registers the entire MVC infrastructure.

**Using `standaloneSetup` in tests expected to verify application-wide configuration.**

`standaloneSetup` creates minimal infrastructure around the passed controller. If you need to verify `@ControllerAdvice`, converters, interceptors, or handler mappings from the application configuration, use `webAppContextSetup` or the corresponding Spring Boot test mechanism.

**Missing required dependencies or converters.**

A controller returning JSON needs the corresponding message converter. Verify that the Jackson dependency or custom converter is present on the test runtime classpath and configured in the context.

**Skipping filters in tests.**

Requests through `MockMvc` may not reflect real security or filtering behavior if the filter chain has not been registered. Check filter and Spring Security configuration when endpoints rely on them.

**Confusing `MockMvc` with a running server.**

`webAppContextSetup` uses the mock servlet API and `DispatcherServlet` in the test environment. It does not start Tomcat, Jetty, or a real server, nor does it test port binding or network connections. If you need to verify the whole application over real HTTP, use a test with an appropriate web environment, such as `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` in Spring Boot.

## 12. Process for Choosing and Implementing Tests

When writing a Spring MVC test, first determine what needs to be verified:

| Goal | Implementation approach |
| --- | --- |
| Verify logic of a single controller with minimal configuration | `standaloneSetup(controller)` |
| Verify a controller with MVC config, advice, converters, and interceptors | Load `WebApplicationContext`, then use `webAppContextSetup(wac)` |
| Verify the MVC slice of a Spring Boot application | `@WebMvcTest` |
| Verify broad integration with the Spring Boot application context via MockMvc | `@SpringBootTest` + `@AutoConfigureMockMvc` |
| Verify the application over real HTTP and a real server | Spring Boot test with `RANDOM_PORT` or the corresponding deployed test environment |

For plain Spring MVC testing, the implementation sequence is typically:

1. Create a Java or XML configuration containing the application's MVC setup.
2. Add `@ExtendWith(SpringExtension.class)` to integrate JUnit Jupiter with Spring Test.
3. Add `@WebAppConfiguration` to instruct Spring to create a web application context.
4. Declare `@ContextConfiguration` to specify the configuration source to load.
5. Inject `WebApplicationContext` into the test.
6. Use `MockMvcBuilders.webAppContextSetup(webApplicationContext).build()` to create `MockMvc`.
7. Send requests using `perform(...)` and verify status, headers, body, and related effects.

When a test fails, read the error layer by layer: did the context initialize; was the controller registered; did the route match; did the request bind; did the converter write the response; did advice handle the exception; did a filter block the request? This layered check helps pinpoint which configuration was not loaded or connected.

## Conclusion

`WebApplicationContext` is the Spring environment for web applications, containing MVC beans and linked to `ServletContext`. In Spring Framework Testing, combining `@WebAppConfiguration`, `@ContextConfiguration`, and `MockMvcBuilders.webAppContextSetup(...)` lets you test requests through the loaded Spring MVC configuration.

This approach fits when you need to verify that multiple web components work together properly: mappings, controllers, converters, exception advice, interceptors, and dependency injection. `MockMvc` still runs in a mock servlet environment, so it tests Spring MVC integration without replacing an HTTP test against a real server. Choose `standaloneSetup`, a web application context, a Boot MVC slice, or a full Boot context according to the exact scope you need to verify.
