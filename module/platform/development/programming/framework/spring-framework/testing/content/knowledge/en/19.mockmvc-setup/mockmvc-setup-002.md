# standaloneSetup with Selected Controllers

When testing a Spring MVC controller, we sometimes want to focus on only one or a few specific controllers. We need to send requests through the MVC processing mechanism to verify URL mapping, parameter binding, data conversion, and the HTTP response, without loading the application's entire web configuration. `MockMvcBuilders.standaloneSetup(...)` is designed for that scope.

`standaloneSetup` takes controller instances supplied by the test, builds minimal Spring MVC infrastructure around them, and returns a builder for configuring `MockMvc`. Controllers are still processed through `DispatcherServlet` in a simulated servlet environment. As a result, tests can verify HTTP behavior at the MVC layer without starting Tomcat, Jetty, or a real server.

What must be handled explicitly are dependencies and MVC components outside the selected controllers. The test instantiates the controller, supplies fake services or required dependencies, and then additionally registers `@ControllerAdvice`, converters, validators, interceptors, or filters if the behavior under test relies on them.

## 1. What Testing Scope Does `standaloneSetup` Address?

A Spring MVC controller can receive a request through multiple steps: Spring finds the matching handler, converts input data, invokes the controller method, handles exceptions, and turns the result into an HTTP response. Calling a Java method directly only tests logic inside the controller; it bypasses these HTTP and MVC steps.

For example, a direct call:

```java
ProductResponse response = controller.getById(42L);
```

does not verify that the path `/api/products/42` is mapped properly, that `42` is bound to `@PathVariable`, or that the response is serialized as JSON.

With `standaloneSetup`, the test sends requests through `MockMvc`:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(controller)
        .build();

mockMvc.perform(get("/api/products/42"))
        .andExpect(status().isOk());
```

The builder creates a minimal MVC environment dedicated to the passed-in controllers. That environment contains the components needed to register handlers, invoke controllers, and capture responses. Application configurations are not loaded automatically merely because a controller carries Spring annotations.

This approach fits when you want to:

- Test a selected controller without initializing the entire application context.
- Verify request mapping, path variables, query parameters, headers, and request bodies.
- Verify status codes, response headers, content types, and JSON responses.
- Verify how the controller handles exceptions, validation, or data conversion when you supply the corresponding configuration.
- Keep tests focused, fast, and minimally coupled to application-wide configuration.

## 2. Creating `MockMvc` from a Controller

Suppose an API has a controller that returns product information. The controller depends on a service to fetch data.

Declare the return data type:

```java
public record ProductResponse(long id, String name) {
}
```

Declare the service:

```java
public interface ProductService {
    ProductResponse findById(long id);
}
```

The controller uses constructor injection:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/{id}")
    public ProductResponse getById(@PathVariable long id) {
        return productService.findById(id);
    }
}
```

In the test, we create a mock for the service and pass that mock into the controller's constructor. Then we pass the controller instance to `standaloneSetup`.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class ProductControllerTest {

    @Mock
    private ProductService productService;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        ProductController controller = new ProductController(productService);

        mockMvc = MockMvcBuilders
                .standaloneSetup(controller)
                .build();
    }

    @Test
    void shouldReturnProductAsJson() throws Exception {
        when(productService.findById(42L))
                .thenReturn(new ProductResponse(42L, "Mechanical Keyboard"));

        mockMvc.perform(get("/api/products/{id}", 42L)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.name").value("Mechanical Keyboard"));

        verify(productService).findById(42L);
    }
}
```

Each step in the test has a specific purpose:

1. `@ExtendWith(MockitoExtension.class)` initializes and manages Mockito mocks for the JUnit Jupiter test.
2. `@Mock ProductService` creates a fake dependency so the test controls the data the controller receives.
3. `new ProductController(productService)` instantiates the controller with explicitly supplied dependencies.
4. `standaloneSetup(controller)` registers the selected controller in an isolated MVC environment.
5. `build()` creates `MockMvc` for the test to perform requests.
6. `perform(get(...))` sends a simulated request; `andExpect(...)` assertions check the HTTP response.
7. `verify(...)` confirms the controller called the service with the right id.

`standaloneSetup` does not component-scan packages and does not automatically discover services to inject like a full application context does. Therefore, constructor injection is a convenient way to instantiate controllers with explicit dependencies. If a controller uses field injection or setter injection, the test must supply those values appropriately before passing the instance to the builder; do not assume the builder performs the application's full autowiring process.

## 3. Selecting One or Multiple Controllers

The method name `standaloneSetup` makes its usage clear: whatever controllers you pass in are the controllers registered in the test's MVC environment.

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(productController)
        .build();
```

Multiple controllers can be passed when a test needs to verify endpoints belonging to a small group:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(productController, categoryController)
        .build();
```

These controllers are registered together in the MVC environment created by the builder. Ensure their mappings do not conflict unintentionally. If two controllers declare an HTTP method and path that can match the same request, handler registration may trigger an ambiguous mapping error or prevent the test from initializing.

Selecting specific controllers also keeps test responsibilities bounded. For instance, `ProductController` tests can verify `/api/products/{id}` without loading user management controllers, security configurations, repositories, or the application's datasource. Dependencies actually used by the controller under test still need to be supplied, typically as mocks or fakes.

## 4. Testing Various Request and Response Shapes

`MockMvc` provides request builders and result matchers to verify the HTTP contract. `standaloneSetup` still uses Spring MVC rules for the registered controllers, so you can test binding and serialization rather than merely calling Java methods.

### Path Variables and Query Parameters

Given the endpoints:

```java
@GetMapping
public List<ProductResponse> search(@RequestParam String keyword) {
    return productService.search(keyword);
}

@GetMapping("/{id}")
public ProductResponse getById(@PathVariable long id) {
    return productService.findById(id);
}
```

The test can send a query parameter or path variable:

```java
mockMvc.perform(get("/api/products")
                .queryParam("keyword", "keyboard"))
        .andExpect(status().isOk());

mockMvc.perform(get("/api/products/{id}", 42L))
        .andExpect(status().isOk());
```

Spring MVC binds strings from the URL to the corresponding parameter types. Tests can verify both valid and invalid cases, such as passing a string that cannot be converted into a `long`.

### Headers and Content Negotiation

A request can declare `Accept` to request a response media type:

```java
mockMvc.perform(get("/api/products/{id}", 42L)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON));
```

Similarly, when sending a request body, use `contentType(...)` to declare the input format. These assertions help catch cases where an endpoint returns the wrong media type or lacks a suitable converter.

### Request Body

Given an endpoint for creating a product:

```java
public record CreateProductRequest(String name) {
}

@PostMapping
@ResponseStatus(HttpStatus.CREATED)
public ProductResponse create(@RequestBody CreateProductRequest request) {
    return productService.create(request);
}
```

Test sending JSON:

```java
mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                        {"name":"Mechanical Keyboard"}
                        """))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.name").value("Mechanical Keyboard"));
```

For this test to run, the test environment needs the corresponding JSON `HttpMessageConverter`, typically the Jackson converter in Spring Boot applications with the default web dependency. If the project lacks that converter or uses a custom converter, register the needed converter in the builder.

## 5. Registering `@ControllerAdvice` When Needed

`standaloneSetup` does not automatically discover all `@ControllerAdvice` classes in the project. If a test wants to verify how the application handles exceptions globally, pass the needed advice to the builder using `setControllerAdvice(...)`.

Example exception:

```java
public class ProductNotFoundException extends RuntimeException {
    public ProductNotFoundException(long id) {
        super("Product " + id + " was not found");
    }
}
```

Advice converting the exception into a response with status 404:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

public record ApiError(String message) {
}

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public ApiError handleProductNotFound(ProductNotFoundException exception) {
        return new ApiError(exception.getMessage());
    }
}
```

Register the advice when building `MockMvc`:

```java
mockMvc = MockMvcBuilders
        .standaloneSetup(controller)
        .setControllerAdvice(new ApiExceptionHandler())
        .build();
```

If the service throws `ProductNotFoundException`, the test can verify the response:

```java
when(productService.findById(404L))
        .thenThrow(new ProductNotFoundException(404L));

mockMvc.perform(get("/api/products/{id}", 404L))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.message").value("Product 404 was not found"));
```

A controller can also declare `@ExceptionHandler` inside the class itself. Handlers belonging to the selected controller can be discovered when registering the controller. Advice outside the controller needs to be supplied explicitly.

## 6. Adding Validators, Converters, and Other MVC Components

The builder provides methods to customize the MVC infrastructure to match the behavior the test needs to verify. Only add components directly related to the test scope; having to copy almost the entire application configuration into the test is a sign that you should consider `webAppContextSetup` or a Spring Boot test slice.

### Validation

If a controller uses `@Valid` on a request body, the test needs a corresponding validator and a Bean Validation provider on the test runtime classpath.

```java
public record CreateProductRequest(
        @NotBlank String name
) {
}

@PostMapping
public ProductResponse create(@Valid @RequestBody CreateProductRequest request) {
    return productService.create(request);
}
```

A `LocalValidatorFactoryBean` can be supplied:

```java
LocalValidatorFactoryBean validator = new LocalValidatorFactoryBean();
validator.afterPropertiesSet();

mockMvc = MockMvcBuilders
        .standaloneSetup(controller)
        .setValidator(validator)
        .build();
```

`LocalValidatorFactoryBean` implements Spring's validator interface and integrates with Bean Validation. In real tests, you need to import `jakarta.validation.Valid`, `jakarta.validation.constraints.NotBlank`, and `org.springframework.validation.beanvalidation.LocalValidatorFactoryBean`; a provider dependency such as Hibernate Validator must also be present. Without a provider, constraints may not be enforced as expected.

### Message Converters

When you need to test a custom converter, register it via `setMessageConverters(...)`:

```java
mockMvc = MockMvcBuilders
        .standaloneSetup(controller)
        .setMessageConverters(new MappingJackson2HttpMessageConverter(objectMapper))
        .build();
```

`MappingJackson2HttpMessageConverter` uses the passed-in `ObjectMapper`. This is helpful when the application configures custom naming strategies, date formats, modules, or serialization rules. Note that when specifying the converter list manually, provide all converters needed by the endpoints under test, such as the JSON converter or converters for other formats.

### Conversion Service and Argument Resolvers

A controller may accept custom data types in path or query parameters, or use a custom `HandlerMethodArgumentResolver`. The builder allows supplying a `FormattingConversionService` and custom argument resolvers:

```java
mockMvc = MockMvcBuilders
        .standaloneSetup(controller)
        .setConversionService(conversionService)
        .setCustomArgumentResolvers(customArgumentResolver)
        .build();
```

Use the same conversion rules required by the endpoint. If custom formatters or resolvers are not registered, standalone tests may fail even though the real application configures them in `WebMvcConfigurer`.

### Interceptors and Filters

Interceptors can be added with `addInterceptors(...)`:

```java
mockMvc = MockMvcBuilders
        .standaloneSetup(controller)
        .addInterceptors(requestAuditInterceptor)
        .build();
```

Filters belong to the servlet filter chain and can be added with `addFilters(...)`:

```java
mockMvc = MockMvcBuilders
        .standaloneSetup(controller)
        .addFilters(requestLoggingFilter)
        .build();
```

Registering a specific filter or interceptor helps test its interaction with the controller. However, manually adding one component does not mean the application's full filter ordering, registration conditions, and security configuration have been verified. If you need to verify the exact real filter chain, load the application's web configuration.

### View Resolvers and Other Components

For controllers that return a view name instead of JSON, the test may need to register an appropriate `ViewResolver` on the builder. Similarly, if the result depends on a locale resolver, content negotiation manager, flash map manager, or async configuration, provide the corresponding setup. The goal is to make clear which components participate in the test so results are explainable and repeatable.

## 7. Testing Asynchronous Controllers

A controller may return `Callable`, `DeferredResult`, or another asynchronous result type. In that case, the initial request may end in an async-started state; the test needs to obtain `MvcResult` and then dispatch the async result to assert on the final response.

```java
MvcResult result = mockMvc.perform(get("/api/products/async/42"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(result))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42));
```

This snippet requires static imports of `asyncDispatch` from `MockMvcRequestBuilders`, `asyncStarted` from `MockMvcResultMatchers.request`, and the `MvcResult` type. If the controller uses a custom executor or timeout, the builder can configure an appropriate async request timeout. Tests should also avoid depending on arbitrary execution timing of background tasks.

## 8. How Does `standaloneSetup` Differ from `webAppContextSetup` and `@WebMvcTest`?

These three test setups share similar goals, but the amount of configuration loaded differs.

| Testing Approach | Source of Controllers and Configuration | Suitable When |
| --- | --- | --- |
| `standaloneSetup(controller)` | Controller instances are passed directly; minimal MVC infrastructure is created by the builder; additional collaborators are registered explicitly. | Focusing on a single controller or a small group of controllers. |
| `webAppContextSetup(wac)` | A loaded `WebApplicationContext` along with the application's MVC configuration and beans. | Needing to test coordination between controllers and the real web configuration. |
| `@WebMvcTest` | Spring Boot creates an MVC test slice and selects relevant web components. | The project uses Spring Boot and you want to test controllers in a Boot-configured slice. |

With `standaloneSetup`, controllers are instantiated directly, dependencies are passed explicitly, and components outside the default scope must be added as needed. With `webAppContextSetup`, the test uses an already configured context, so component scanning, MVC config, advice, and corresponding beans participate according to that configuration. `@WebMvcTest` is Spring Boot's convenient option for creating an MVC slice; it is still a Spring test context and has its own bean selection mechanism.

`standaloneSetup` is not a pure unit test because requests still pass through Spring MVC and a simulated `DispatcherServlet`. Neither is it a full-application integration test because it does not automatically load the configuration and beans of the entire application.

## 9. What Standalone Tests Verify and Their Limitations

A test using `standaloneSetup` can verify:

- Controller mappings are selected for the HTTP method and URL.
- Spring binds path variables, query parameters, headers, and request bodies.
- The controller receives the bound data properly and calls dependencies with the expected arguments.
- Response status, headers, content type, and body are generated correctly.
- Validation, exception handlers, converters, interceptors, or filters registered for the test behave properly within that configuration scope.

The test does not automatically verify:

- Whether the application's component scan discovers the controller at runtime.
- That beans are injected and configured properly in the real application context.
- That the application's `WebMvcConfigurer`, `@ControllerAdvice`, filters, or security chain are fully registered in the real order, unless the test configures those components itself.
- That datasource, transaction, repository, or external system integrations work properly.
- Whether a real server starts up, binds a port, and accepts requests over the network successfully.

This boundary is important when interpreting results. A passing standalone test shows that the controller together with the MVC infrastructure assembled for the test handles the request properly. It does not prove that the production application loads the same controller or the same configuration.

## 10. Common Mistakes

**Passing a class instead of a controller instance.**

`standaloneSetup` takes controller instances. Create the controller with the required dependencies and pass the instance into the builder.

**Forgetting to supply controller dependencies.**

If the controller uses constructor injection, create mocks or fakes for dependencies and pass them to the constructor. A controller created with `new` does not automatically receive services from a Spring application context.

**Assuming component scanning still runs.**

The builder registers only the specified controllers. Other controllers in the package are not discovered automatically. If a request targets an unregistered controller, the mapping will not exist in the test environment.

**Not registering `@ControllerAdvice`.**

Global advice is not automatically scanned from the project. Pass the advice via `setControllerAdvice(...)` if the test needs to verify that exception handling.

**Missing converters or validators.**

JSON requests, JSON responses, or `@Valid` may not work as expected if the required dependencies or configuration are absent from the test. Check the test runtime classpath and register appropriate converters/validators.

**The test is copying too much of the application configuration.**

If you have to register many converters, resolvers, interceptors, filters, and beans to reproduce almost the entire MVC config, the test may lose its narrow-scope advantage. Consider using `webAppContextSetup` or `@WebMvcTest` to test the configuration declared at the source.

**Confusing `MockMvc` with a real HTTP server.**

`MockMvc` executes requests in a simulated servlet environment. It does not open TCP ports and does not test networking, reverse proxies, or server configuration. Use real-server tests when those factors are part of what needs to be verified.

## 11. Workflow for Building Tests with Selected Controllers

A practical workflow can follow this order:

1. Identify the controllers and endpoints to test; select only directly relevant controllers.
2. Create mocks or fakes for the controller's dependencies.
3. Instantiate the controller using its constructor or a test factory.
4. Call `MockMvcBuilders.standaloneSetup(controller)` to create the builder.
5. Register advice, validators, converters, resolvers, interceptors, or filters if the behavior under test requires them.
6. Call `build()` to create `MockMvc`.
7. Send requests representing the scenarios to test.
8. Assert status, headers, body, and dependency invocations.
9. When you need to verify the application's actual MVC configuration, move to a test using `WebApplicationContext` or a Spring Boot MVC slice.

Minimal setup example:

```java
ProductController controller = new ProductController(productService);

MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(controller)
        .setControllerAdvice(new ApiExceptionHandler())
        .build();
```

This example highlights two decisions of the test: which controller is under test and which advice is included in the MVC environment. Remaining configuration choices can be added based on the endpoint's needs.

## Conclusion

`MockMvcBuilders.standaloneSetup(...)` creates `MockMvc` around one or more selected controller instances. It is a fitting way to test the HTTP and MVC behavior of controllers within a narrow scope, with dependencies and extension components provided explicitly.

Standalone tests can verify mapping, binding, serialization, responses, and how a controller collaborates with registered collaborators. When the goal shifts to verifying component scanning, bean wiring, or the entire MVC configuration of the application, use `webAppContextSetup` or an appropriate test slice to test that context itself.
