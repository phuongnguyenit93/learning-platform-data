# Initializing MockMvcTester from a Controller or Existing MockMvc

`MockMvcTester` is an AssertJ-style Spring MVC testing API introduced in Spring Framework 6.2. It uses `MockMvc` underneath to run requests through `DispatcherServlet` with simulated Servlet requests/responses, without needing to start a real HTTP server.

There are two primary initialization entry points corresponding to two scenarios:

- `MockMvcTester.of(...)`: passes controllers directly into the tester to build a standalone MVC configuration.
- `MockMvcTester.create(mockMvc)`: wraps a `MockMvc` instance that has already been created and configured beforehand.

Additionally, when a `WebApplicationContext` is available, `MockMvcTester.from(...)` can be used so the tester creates `MockMvc` from the application context itself. This article focuses on initializing from controllers and from an existing `MockMvc`, while placing both approaches in their proper usage context.

## 1. Prerequisites

`MockMvcTester` is available starting in Spring Framework 6.2 and resides in the package:

```java
import org.springframework.test.web.servlet.assertj.MockMvcTester;
```

The tester uses AssertJ for writing assertions, so AssertJ must be on the test classpath. If using Spring Boot 3.4 or later, `spring-boot-starter-test` usually provides the necessary test libraries, including AssertJ. For plain Spring Framework projects, declare `spring-test` and `assertj-core` in test dependencies while managing compatible versions via the project's BOM or dependency management.

Gradle example when the project manages versions itself:

```groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.assertj:assertj-core")
}
```

The examples use JUnit Jupiter. With Spring Framework prior to 6.2, `MockMvcTester` is not available; you can continue using `MockMvc` with `MockMvcResultMatchers` or upgrade Spring Framework.

## 2. Initializing Directly from a Controller with of(...)

When you only want to test one or a few controllers with minimal MVC configuration, use `MockMvcTester.of(...)`:

```java
MockMvcTester mvc = MockMvcTester.of(new GreetingController());
```

This method creates a standalone configuration similar to `MockMvcBuilders.standaloneSetup(...)`. Spring builds the minimal MVC infrastructure required for `DispatcherServlet` to serve annotated controllers. There is no need to create a separate `MockMvc` first.

Controller example:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GreetingController {

    @GetMapping("/greeting")
    String greeting(@RequestParam(defaultValue = "World") String name) {
        return "Hello, " + name;
    }
}
```

Test initializing the tester and sending a request:

```java
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingControllerTests {

    private final MockMvcTester mvc =
            MockMvcTester.of(new GreetingController());

    @Test
    void returnsGreeting() {
        assertThat(mvc.get().uri("/greeting").param("name", "Ada"))
                .hasStatusOk()
                .hasBodyTextEqualTo("Hello, Ada");
    }
}
```

`mvc.get()` creates a GET request using the tester's API; `.uri(...)` sets the path; `.param(...)` adds a query parameter. `assertThat(...)` wraps the request result to invoke AssertJ assertions such as `hasStatusOk()` and `hasBodyTextEqualTo(...)`.

### Passing a Controller Instance or Class?

`of(Object... controllers)` accepts one or more controller instances; the API also allows passing controller types (`Class`) for Spring to instantiate. For example:

```java
MockMvcTester mvc = MockMvcTester.of(
        new GreetingController(),
        new HealthController());
```

When a controller has dependencies, it is usually better to instantiate it and pass dependencies explicitly:

```java
GreetingService service = name -> "Welcome, " + name;
GreetingController controller = new GreetingController(service);
MockMvcTester mvc = MockMvcTester.of(controller);
```

This approach makes the controller's dependencies explicit and does not rely on component scanning or dependency injection from an application context. If passing a class for Spring to instantiate, do not assume application dependencies will be automatically injected as they would when the controller is managed by a container.

## 3. Customizing Configuration When Initializing from a Controller

`of(Object... controllers)` only creates minimal MVC infrastructure. If you need controller advice, filters, converters, argument resolvers, or other MVC configuration, use the overload that accepts a collection of controllers and a builder customizer function:

```java
MockMvcTester mvc = MockMvcTester.of(
        List.of(new GreetingController()),
        builder -> builder
                .setControllerAdvice(new ApiExceptionHandler())
                .addFilters(new RequestAuditFilter())
                .build());
```

The customizer function receives a `StandaloneMockMvcBuilder` and must return `MockMvc` via `.build()`. This is equivalent to configuring `MockMvcBuilders.standaloneSetup(...)` first and then passing the built MockMvc to the tester.

Example when registering a specific converter or validator:

```java
MockMvcTester mvc = MockMvcTester.of(
        List.of(controller),
        builder -> builder
                .setValidator(validator)
                .setControllerAdvice(exceptionHandler)
                .build());
```

Add only the components required by the test scenario. Standalone configuration does not automatically load the application's full Spring MVC configuration, so settings like interceptors, formatters, custom converters, or the security filter chain must be explicitly registered if the test depends on them.

## 4. Initializing from an Existing MockMvc with create(...)

If a project has already built `MockMvc` and wants to adopt the AssertJ API, use `MockMvcTester.create(mockMvc)`:

```java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new GreetingController())
        .addFilters(new RequestAuditFilter())
        .build();

MockMvcTester mvc = MockMvcTester.create(mockMvc);
```

`create(...)` creates a tester that delegates requests to the exact `MockMvc` passed in. It does not rebuild controllers or replace MockMvc's configuration. Existing settings such as filters, interceptors, controller advice, message converters, and exception resolvers continue to belong to that MockMvc instance.

This is useful when:

- The test suite already has helpers or fixtures that create MockMvc.
- MockMvc is configured using `webAppContextSetup(...)` or `standaloneSetup(...)` with extensive customizations.
- Some older tests use MockMvc and you want to use AssertJ in new tests.
- MockMvc is provided by Spring Boot test configuration or injected into the test class.

Complete example with an already configured MockMvc:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.assertj.core.api.Assertions.assertThat;

class ExistingMockMvcTests {

    private MockMvc mockMvc;
    private MockMvcTester mvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new GreetingController())
                .build();
        mvc = MockMvcTester.create(mockMvc);
    }

    @Test
    void reusesExistingMockMvc() {
        assertThat(mvc.get().uri("/greeting"))
                .hasStatusOk()
                .hasBodyTextEqualTo("Hello, World");
    }
}
```

In the example, creating `MockMvc` and creating `MockMvcTester` are two separate steps. If `mockMvc` was already created elsewhere, simply call `create(mockMvc)`; there is no need to rebuild it.

## 5. When You Have a WebApplicationContext: from(...)

`MockMvcTester.from(applicationContext)` is a convenient option when you want the tester to build MockMvc itself from an already refreshed `WebApplicationContext`:

```java
@SpringJUnitConfig(WebConfig.class)
class WebLayerTests {

    @Autowired
    private WebApplicationContext applicationContext;

    @Test
    void usesApplicationMvcConfiguration() {
        MockMvcTester mvc = MockMvcTester.from(applicationContext);

        assertThat(mvc.get().uri("/greeting"))
                .hasStatusOk();
    }
}
```

`from(...)` reads the Spring MVC configuration and controllers from the application context. If you need to customize the builder before creating MockMvc, there is an overload accepting a function:

```java
MockMvcTester mvc = MockMvcTester.from(
        applicationContext,
        builder -> builder.addFilters(new RequestAuditFilter()).build());
```

Distinguishing the three factory methods:

| Method | Input | Who Creates MockMvc? | Use Case |
|---|---|---|---|
| `of(controllers...)` | Controller instances or types | `MockMvcTester` builds standalone MockMvc | Testing controllers with minimal MVC infrastructure |
| `create(mockMvc)` | Existing MockMvc | You or test configuration created MockMvc | Reusing an existing MockMvc configuration |
| `from(applicationContext)` | Refreshed WebApplicationContext | `MockMvcTester` builds MockMvc from context | Testing with Spring MVC configuration in the application context |

## 6. Using MockMvcTester in Spring Boot Tests

In Spring Boot, if `@AutoConfigureMockMvc` is already used, you can inject `MockMvc` and wrap it:

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsOrder() {
        MockMvcTester mvc = MockMvcTester.create(mockMvc);

        assertThat(mvc.get().uri("/api/orders/42"))
                .hasStatusOk();
    }
}
```

This is appropriate when you want to preserve the MockMvc configuration created by Spring Boot, including filters and web components registered in the test context. If your project and Spring Boot version auto-configure `MockMvcTester` directly, you can inject the tester directly according to that configuration; the example above shows how to explicitly adapt from an existing MockMvc.

## 7. Performing Requests and Writing Assertions

After initializing the tester using one of the approaches above, the request-sending API can use `MockMvcTester`'s builder:

```java
assertThat(mvc.get().uri("/api/orders/42"))
        .hasStatusOk();

assertThat(mvc.post().uri("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"customerId\":\"C-12\"}"))
        .hasStatus(HttpStatus.CREATED);
```

You can use `exchange()` when you need to keep the result and run multiple separate assertions:

```java
MvcTestResult result = mvc.post()
        .uri("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"customerId\":\"C-12\"}")
        .exchange();

assertThat(result).hasStatus(HttpStatus.CREATED);
assertThat(result).body().isNotEmpty();
```

`MockMvcTester` also supports static request builders like MockMvc, which is suitable when you already have a custom `RequestBuilder`:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

assertThat(mvc.perform(get("/greeting")))
        .hasStatusOk()
        .hasBodyTextEqualTo("Hello, World");
```

For normal cases, use the tester's request builder such as `mvc.get().uri(...)`. When using `perform(RequestBuilder)`, the tester accepts a pre-built request builder and executes it; this path does not automatically handle async requests the way the tester's dedicated builder API does.

## 8. Which Initialization Approach Should You Choose?

Choose `of(...)` when the test focuses on specific controllers, you want to supply dependencies explicitly, and there is no need to load the full application configuration. This approach is fast, clearly scoped, and well suited for isolated controller tests.

Choose `create(...)` when MockMvc already exists and has configuration that the test needs to preserve. This is the natural choice when gradually migrating from `MockMvcResultMatchers`-style assertions to AssertJ.

Choose `from(...)` when you want to use an initialized application context and let the tester build MockMvc from the real MVC configuration. If you need to preserve a specially pre-configured MockMvc, build MockMvc with the builder and wrap it using `create(...)`.

Do not use standalone tests to conclude that the application's entire MVC configuration works properly. If the application has important configuration such as Spring Security, custom converters, interceptors, or controller advice registered in the context, integration tests using the context or a correspondingly configured MockMvc are needed.

## 9. Common Mistakes

| Symptom | Common Cause | Resolution |
|---|---|---|
| `MockMvcTester` not found | Spring Framework older than 6.2 or missing `spring-test` | Use Spring Framework 6.2+ and declare the appropriate test dependency |
| Cannot resolve `assertThat` | AssertJ missing from the test classpath | Add `assertj-core` or use a test starter that includes AssertJ |
| Controller lacks dependencies | Using `of(...)` as if it creates an application context and injects beans | Instantiate the controller with explicit dependencies or use context-based setup |
| Filters or advice do not run | Using `of(controller)` with minimal standalone configuration | Use the customizing overload, `from(context)`, or a fully configured `create(mockMvc)` |
| MockMvc configuration lost when switching to tester | Building a new MockMvc instead of wrapping the old instance | Pass the exact instance into `MockMvcTester.create(mockMvc)` |
| JSON body not converted as expected | Tester lacks an appropriate message converter for structured body assertions | Configure MVC converters or use `withHttpMessageConverters(...)` appropriately |
| Test does not reflect security configuration | Standalone setup does not register the security filter chain | Use MockMvc from context or add security config/filter chain in standalone setup |

## 10. Takeaways

`MockMvcTester.of(controller...)` creates a tester in standalone mode from controllers; use the customizing overload when additional MVC configuration is needed. `MockMvcTester.create(mockMvc)` wraps an existing MockMvc and preserves that instance's configuration. If you have a `WebApplicationContext` and want the tester to build MockMvc from the context itself, use `MockMvcTester.from(context)`. Choose the factory method based on the configuration source the test needs, then use the tester's builder and AssertJ to perform requests and verify results.

