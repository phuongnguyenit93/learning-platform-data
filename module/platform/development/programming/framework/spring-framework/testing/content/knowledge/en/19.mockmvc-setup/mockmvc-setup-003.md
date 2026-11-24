# `webAppContextSetup` with Real MVC Configuration

`MockMvc` enables testing Spring MVC requests and responses without starting an HTTP server. When creating `MockMvc` via `MockMvcBuilders.webAppContextSetup(webApplicationContext)`, the test uses a `WebApplicationContext` already loaded by Spring with the application's actual web configuration. Requests pass through `DispatcherServlet` and the MVC components registered in the context, allowing you to test how controllers collaborate with mappings, converters, validators, interceptors, exception handlers, and view resolvers.

This is the right choice when the goal is to test the behavior of the full Spring MVC configuration in a test environment. The test still runs in a mock servlet environment; it does not open network ports and does not test the specific behavior of a real running servlet container.

## How Does `webAppContextSetup` Work?

`MockMvcBuilders` provides two common setup approaches:

| Builder Method | Context Used | Testing Scope |
|---|---|---|
| `standaloneSetup(controller)` | Controllers passed directly along with optional test configuration | Focused on the controller; the test configures the needed MVC components itself |
| `webAppContextSetup(wac)` | The application's `WebApplicationContext` | Uses the Spring MVC configuration loaded in the context |

With `webAppContextSetup`, Spring Test initializes `DispatcherServlet` in a simulated servlet environment backed by the provided `WebApplicationContext`. When a request is executed, `DispatcherServlet` uses the MVC components provided or discovered by the context, such as:

- `HandlerMapping` to resolve the handler matching the URL, HTTP method, and mapping conditions.
- `HandlerAdapter` to invoke the corresponding controller or handler.
- `HandlerExceptionResolver` and `@ControllerAdvice` to handle exceptions thrown during request processing.
- `HttpMessageConverter` to read request bodies and write response bodies, such as converting JSON to objects and vice versa.
- `ConversionService`, `Formatter`, and `Validator` to convert, format, and validate input data.
- `HandlerInterceptor` to run pre- and post-handler logic according to the MVC configuration.
- `ViewResolver` to resolve views when a controller returns a view name instead of a response body.

These components are used according to the loaded configuration. For instance, if the application registers a custom JSON converter, CORS rules, a locale-checking interceptor, or a `@RestControllerAdvice`, tests can observe their effects through requests and responses.

An essential requirement is that the passed object must be a `WebApplicationContext` containing the appropriate MVC configuration. A plain `ApplicationContext` without web context cannot substitute for it.

## Loading WebApplicationContext in Plain Spring

For Spring MVC applications that do not use Spring Boot, Spring Test can load Java configuration using `@ContextConfiguration` and create a simulated servlet context using `@WebAppConfiguration`.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = WebMvcConfig.class)
class ProductControllerMvcTest {

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
    void returnsProductAsJson() throws Exception {
        mockMvc.perform(get("/api/products/{id}", 42)
                        .accept("application/json"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42));
    }
}
```

`WebMvcConfig` in the example is the application's MVC configuration, not a separate configuration built only to instantiate a controller for `MockMvc`. That configuration typically enables Spring MVC and registers controllers along with required components:

```java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
@EnableWebMvc
@ComponentScan(basePackages = "com.example.web")
class WebMvcConfig implements WebMvcConfigurer {
    // Register interceptors, formatters, converters, CORS, etc. if needed by the application.
}
```

Services, repositories, and dependencies required by controllers must also be present in the context or in a parent context. In applications that split a root context and a servlet context, the root context usually holds services/repositories while the servlet context holds controllers and MVC configuration. When using `@ContextHierarchy`, ensure the injected `WebApplicationContext` is the context tied to the `DispatcherServlet` under test, so the test uses the right handler and MVC configuration.

`@WebAppConfiguration` tells Spring Test that the test needs a web application context and a `MockServletContext`. Without this annotation in a plain Spring test setup, the context may not be a `WebApplicationContext`, causing injection or `MockMvc` construction to fail.

## Loading Real Configuration in Spring Boot

In Spring Boot applications, `@SpringBootTest` loads the application context along with MVC configurations auto-configured by Boot or customized by the project. `MockMvc` can be built manually from `WebApplicationContext`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import org.springframework.http.MediaType;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ProductControllerIntegrationTest {

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
    void returnsProductUsingApplicationMvcConfiguration() throws Exception {
        mockMvc.perform(get("/api/products/{id}", 42L)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(42));
    }
}
```

`WebEnvironment.MOCK` creates a simulated servlet environment instead of starting a real server. This is the right environment for using `webAppContextSetup`. If you want to test over real HTTP, including the server and network stack, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` and an HTTP client; that is a different kind of test.

Spring Boot also provides `@AutoConfigureMockMvc` to automatically configure and inject `MockMvc`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ProductControllerAutoConfiguredTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsProduct() throws Exception {
        mockMvc.perform(get("/api/products/{id}", 42L))
                .andExpect(status().isOk());
    }
}
```

When using `@AutoConfigureMockMvc`, you do not need to call `webAppContextSetup` manually. This annotation is handy if you want Spring Boot to manage building MockMvc and apply Boot's customizers. This lesson focuses on manual setup to make clear how `WebApplicationContext` is passed into the builder.

## Testing Real MVC Components

The strength of `webAppContextSetup` stands out when tests traverse multiple configuration layers. A request can be mapped by `RequestMappingHandlerMapping`, JSON data processed by converters, validation executed on controller parameters, and exceptions translated into responses by `@ControllerAdvice`.

For example, a controller can accept a DTO from JSON and use Bean Validation:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @PostMapping
    ResponseEntity<ProductDto> create(
            @Valid @RequestBody CreateProductRequest request) {
        ProductDto created = productService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
```

Tests via MockMvc can assert both status and response for valid or invalid payloads:

```java
mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"name":"Keyboard"}
                        """))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.name").value("Keyboard"));

mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"name":""}
                        """))
        .andExpect(status().isBadRequest());
```

The requests above are illustrative examples; the DTO must have the appropriate constraints and the controller must be configured for validation to run. When using the real context, tests can catch configuration issues such as a missing validation provider, a converter not supporting a data type, incorrect mappings, or unregistered advice.

For controllers returning views, you can assert the view name and model:

```java
mockMvc.perform(get("/products/{id}", 42L))
        .andExpect(status().isOk())
        .andExpect(view().name("products/detail"))
        .andExpect(model().attributeExists("product"));
```

If the application uses a custom `ViewResolver`, `webAppContextSetup` lets tests verify results under the loaded configuration instead of manually setting up resolvers per controller.

## Interceptors and Servlet Filters

`HandlerInterceptor` is part of Spring MVC. When an interceptor is registered via `WebMvcConfigurer#addInterceptors`, it belongs to the MVC configuration used by `DispatcherServlet` in `webAppContextSetup`. Tests can verify interceptor behavior by sending normal requests and checking the appropriate status, headers, model, or side effects.

Servlet `Filter`s reside at the servlet layer before `DispatcherServlet`. When building MockMvc manually with `webAppContextSetup`, you need to add the filters you want to execute to the builder:

```java
mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .addFilters(characterEncodingFilter, requestAuditFilter)
        .build();
```

Adding filters to the builder makes them participate in MockMvc's request processing chain. The fact that a filter exists as a bean in the application context does not mean every manual MockMvc setup automatically adds that filter. Explicitly register the filters the test needs to run through.

With Spring Security, if the project uses `spring-security-test`, the security configuration can be applied to the builder:

```java
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;

mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

`springSecurity()` wires the security filter chain configured in the context into MockMvc. Tests can then use request post-processors such as `user("alice")`, `csrf()`, or test responses when unauthenticated:

```java
mockMvc.perform(get("/api/account").with(user("alice")))
        .andExpect(status().isOk());

mockMvc.perform(post("/api/account")
                .with(user("alice"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Alice\"}"))
        .andExpect(status().isOk());
```

When using `.apply(springSecurity())`, do not add the same `springSecurityFilterChain` again via `.addFilters(...)`, as that can cause the security chain to run twice. For custom filters, add the required filters deliberately.

## Customizing the Builder

`webAppContextSetup` returns a builder, so you can attach shared settings applied to every request in the test suite:

```java
mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .defaultRequest(get("/").accept(MediaType.APPLICATION_JSON))
        .alwaysExpect(status().isOk())
        .build();
```

Only place conditions in `alwaysExpect` that genuinely hold for every request. The example above is only suitable if all requests in the test class are expected to return `200 OK`; it is not suitable for tests checking `400`, `401`, `404`, or `201`.

Other useful customizations:

- `addFilters(...)` adds servlet filters to the request chain.
- `defaultRequest(...)` sets defaults such as headers or request attributes.
- `alwaysDo(...)` applies a `ResultHandler` to every request, such as logging requests/responses during debugging.
- `alwaysExpect(...)` applies a shared `ResultMatcher`.
- `apply(...)` applies additional configurators, such as `springSecurity()`.

You can call `andDo(print())` on a specific request to inspect request and response details when a test fails:

```java
mockMvc.perform(get("/api/products/{id}", 42L))
        .andDo(print())
        .andExpect(status().isOk());
```

In a stable test suite, it is usually best to create `MockMvc` once per test class or reuse the instance built from the context. Spring Test caches application contexts; building the builder does not require restarting the entire context for each request.

## Limitations to Understand Properly

`webAppContextSetup` tests Spring MVC inside a mock servlet environment. It processes requests through `DispatcherServlet` and registered components, but does not perform several operations of a real server:

- Does not open sockets, bind ports, or pass requests through a network stack.
- Does not verify connector configuration, TLS, reverse proxies, server request limits, or Tomcat/Jetty/Undertow-specific behavior.
- Does not automatically prove that every servlet filter from the deployment environment is registered; required filters must be present in the MockMvc chain.
- Does not replace integration tests over real HTTP when verifying deployment configuration or network infrastructure interactions.

In addition, `webAppContextSetup` uses the exact context passed to it. If the test loads the wrong context—for example, loading only the root context while omitting the servlet context containing MVC configuration—handler mappings or converters may not appear as expected. Check the application's context structure before adjusting the builder.

`@WebMvcTest` in Spring Boot is an MVC test slice: it loads only a selected subset of web-layer components and typically requires mocking dependencies outside the slice. If you pass a slice's `WebApplicationContext` to `webAppContextSetup`, the builder still uses that context, but the configuration scope remains the slice. To test the full application configuration, load an appropriate application context, such as with `@SpringBootTest`.

## Common Errors and Troubleshooting

| Symptom | Possible Cause | Troubleshooting |
|---|---|---|
| Cannot inject `WebApplicationContext` or context is not a web context | Plain Spring test is missing `@WebAppConfiguration`, or config loads the wrong context type | Use `@WebAppConfiguration` and load the MVC configuration |
| Request returns `404` even though controller exists | Controller is not component-scanned/imported into the context; wrong servlet context or URL mapping | Check scan config, mappings, and the injected context |
| Cannot convert JSON | Converter or Jackson configuration is missing from the context | Load the actual MVC configuration and inspect dependencies/converters |
| Validation does not run | Missing validation provider, constraints, or required configuration | Check Bean Validation dependencies and MVC configuration |
| `@ControllerAdvice` does not handle exception | Advice is not discovered in the active context | Include advice in component scan or import the relevant configuration |
| Interceptor does not run | Interceptor is not registered in the loaded MVC config | Check `WebMvcConfigurer#addInterceptors` |
| Filter does not run | Filter was not added to the MockMvc builder | Use `.addFilters(...)` or the appropriate MockMvc configuration mechanism |
| Spring Security filter runs twice | Both `.apply(springSecurity())` and manual addition of the same filter chain | Register the security filter chain only once |
| Tests pass but real deployment still fails on the server | MockMvc does not run the real network stack or servlet container | Add HTTP tests with a real server when the scope requires it |

## When Should You Choose `webAppContextSetup`?

Choose `webAppContextSetup` when the test needs to verify that controllers work with the application's MVC configuration: mappings, converters, formatters, validators, interceptors, advice, view resolvers, or security configurations wired into MockMvc. It is also a good choice when testing multiple controllers within the same web context configuration.

If you only need to test the logic of a single controller with a small set of dependencies and want fast setup, `standaloneSetup` may be a better fit. If you need to test the server, network ports, TLS, or servlet container behavior, run the application in a real server environment and send HTTP requests. Choosing the right setup ensures each test proves the exact slice of behavior it was designed to verify.
