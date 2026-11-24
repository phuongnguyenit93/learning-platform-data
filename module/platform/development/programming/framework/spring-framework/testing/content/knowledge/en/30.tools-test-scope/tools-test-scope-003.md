# How Spring Boot Test Slices Differ from @ContextConfiguration

When writing tests for a Spring Boot application, two configuration approaches are commonly mentioned: test slices such as `@WebMvcTest` and `@DataJpaTest`, and the `@ContextConfiguration` annotation from the Spring TestContext Framework. Both can create a Spring application context for a test, but they solve two different problems.

**A test slice defines the scope of components and auto-configuration to load for one layer of the application.** For example, `@WebMvcTest` focuses on Spring MVC, whereas `@DataJpaTest` focuses on JPA repositories and entities.

**`@ContextConfiguration` defines the configuration sources used to create an application context.** It tells Spring which Java configuration classes, XML resources, context initializers, or context loaders to load. On its own, this annotation does not create component-filtering rules and does not activate a Boot test slice.

Therefore, test slices and `@ContextConfiguration` are not direct drop-in replacements for each other. One selects the testing scope; the other declares the configuration sources of the context.

## 1. What Is a Test Slice?

Spring Boot provides testing annotations tailored to individual slices of an application. Each slice loads the components relevant to a layer while excluding unrelated beans so that tests start faster and stay focused.

For example, an application may consist of the following layers:

```text
HTTP request
    |
    v
Controller / Spring MVC
    |
    v
Service / business logic
    |
    v
Repository / JPA
    |
    v
Database
```

When testing only a controller, the test typically does not need a database or all real services. `@WebMvcTest` loads the MVC infrastructure and the selected controller, while business dependencies can be replaced with mocks. When testing only a JPA repository, `@DataJpaTest` loads entities, repositories, and the required persistence configuration.

Test slices typically share these characteristics:

- Use the Spring TestContext Framework to manage the application context and test lifecycle.
- Load a group of auto-configurations suited to the layer under test.
- Use component filters to restrict which bean types are discovered.
- Do not start the entire application like `@SpringBootTest`.
- Can add needed beans or configuration via `@Import`, `@TestConfiguration`, or a mock bean mechanism.

Common slices:

| Annotation | Primary scope | Example components tested |
| --- | --- | --- |
| `@WebMvcTest` | Spring MVC | Controllers, mappings, converters, validation, controller advice |
| `@WebFluxTest` | Spring WebFlux | Reactive controllers and WebFlux infrastructure |
| `@DataJpaTest` | JPA | Entities, repositories, JPA mappings and queries |
| `@JdbcTest` | JDBC | JDBC components and database operations |
| `@JsonTest` | JSON serialization | Jackson/Gson/Jsonb mappers and serializers |
| `@RestClientTest` | REST client | Components calling HTTP services and supporting mock server |
| `@DataMongoTest` | MongoDB | Mongo mappings and repositories |

The exact list depends on the Spring Boot version and the modules on the classpath. You can check the documentation for the Boot version your project uses to see which slices are supported.

## 2. What Is @ContextConfiguration?

`@ContextConfiguration` belongs to the Spring TestContext Framework, in the package:

```java
org.springframework.test.context.ContextConfiguration
```

This annotation specifies metadata for Spring to create an application context for a test. Commonly used attributes include:

- `classes`: Java configuration classes or component classes used as configuration sources.
- `locations`: paths to configuration resources, typically XML.
- `initializers`: `ApplicationContextInitializer` instances run while preparing the context.
- `loader`: a custom context loader if needed.
- `inheritLocations` and `inheritInitializers`: control inheriting configuration from a parent test class.
- `name`: name of the context configuration when hierarchy management is needed.

Example declaring Java configuration:

```java
@Configuration
public class PricingTestConfig {

    @Bean
    DiscountPolicy discountPolicy() {
        return new FixedDiscountPolicy(0.10);
    }

    @Bean
    PricingService pricingService(DiscountPolicy discountPolicy) {
        return new PricingService(discountPolicy);
    }
}
```

Test using `@ContextConfiguration`:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = PricingTestConfig.class)
class PricingServiceTest {

    @Autowired
    private PricingService pricingService;

    @Test
    void appliesConfiguredDiscount() {
        BigDecimal result = pricingService.calculate(
                new BigDecimal("100.00"));

        assertThat(result).isEqualByComparingTo("90.00");
    }
}
```

`SpringExtension` integrates JUnit Jupiter with the Spring TestContext Framework. `@ContextConfiguration` specifies the configuration class used to create the context, after which Spring injects `PricingService` into the test.

In this example, the test does not need a Spring Boot test slice. It uses a Spring context defined directly with Java configuration.

### Using XML as a configuration source

`@ContextConfiguration` can also point to an XML resource:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(locations = "classpath:/test-context.xml")
class LegacyServiceTest {

    @Autowired
    private LegacyService legacyService;
}
```

This approach is useful for older Spring applications or when a test needs to verify a specific XML configuration. `@ContextConfiguration` does not require the project to use Spring Boot.

## 3. Comparing the Two Concepts

| Criterion | Spring Boot test slice | `@ContextConfiguration` |
| --- | --- | --- |
| Purpose | Creates a test context focused on one layer | Declares configuration sources for the test context |
| Bean scope | Restricted by the slice type and Boot filters | Depends on declared classes/resources and what they import/scan |
| Auto-configuration | Loads the group of auto-configurations matching the slice | Does not automatically activate Boot slice auto-configuration |
| Component scanning | Has slice-specific filters | Follows declared component scan configuration |
| Examples | `@WebMvcTest`, `@DataJpaTest`, `@JsonTest` | `@ContextConfiguration(classes = TestConfig.class)` |
| Requires Spring Boot? | Yes, these are Boot testing annotations | No, belongs to Spring TestContext Framework |
| Can they be combined? | Can add configuration sources or beans when needed | Can appear alongside Boot test configuration if using the right bootstrapper |

The key distinction: `@ContextConfiguration` answers “which configuration should be loaded?”, whereas a test slice answers “which layer is being tested and what does Boot need to prepare for that layer?”.

## 4. Example: Testing a Controller with @WebMvcTest

Suppose a controller depends on a service:

```java
public interface OrderService {
    OrderResponse findById(long id);
}

@RestController
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/orders/{id}")
    public OrderResponse find(@PathVariable long id) {
        return orderService.findById(id);
    }
}
```

Test slice:

```java
@WebMvcTest(OrderController.class)
class OrderControllerWebMvcTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @Test
    void returnsOrderAsJson() throws Exception {
        given(orderService.findById(42L))
                .willReturn(new OrderResponse(42L, "READY"));

        mockMvc.perform(get("/orders/{id}", 42))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.status").value("READY"));
    }
}
```

`@WebMvcTest(OrderController.class)` focuses on the specified controller and Spring MVC infrastructure. `OrderService` is not an MVC bean loaded automatically by this slice, so the test supplies a mock bean using `@MockitoBean`.

`@MockitoBean` belongs to Spring Framework 6.2 and later. On older Spring Boot versions that do not yet have this annotation, projects typically use `@MockBean` from Spring Boot Test. Use the annotation appropriate for your managed dependency version.

This test verifies that the controller receives the request, binds the path variable, calls the service, and serializes the result. It does not test the real service implementation or database.

### Adding controller advice or web configuration

If the controller relies on a `@RestControllerAdvice`, converters, or custom web configuration, you can bring the needed components into the slice with `@Import`:

```java
@WebMvcTest(OrderController.class)
@Import({OrderExceptionHandler.class, ApiWebConfiguration.class})
class OrderControllerWebMvcTest {
    // MockMvc test.
}
```

`@Import` adds beans to the context configured by the slice. This is usually a clear way to include required test or production configuration while preserving the scope of `@WebMvcTest`.

## 5. Example: Testing a Repository with @DataJpaTest

For the JPA layer, you can use:

```java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void findsOrderByStatus() {
        orderRepository.save(new Order("READY"));
        orderRepository.save(new Order("CANCELLED"));

        List<Order> result = orderRepository.findByStatus("READY");

        assertThat(result)
                .extracting(Order::getStatus)
                .containsExactly("READY");
    }
}
```

`@DataJpaTest` loads the required JPA components and detects entities and Spring Data repositories. The default configuration typically uses an embedded database if present on the test classpath and runs tests inside a transaction rolled back after each method.

If you want to use a configured database instead of an embedded one, you can use `@AutoConfigureTestDatabase(replace = Replace.NONE)` along with an appropriate test datasource. For production-specific databases, you can combine it with Testcontainers.

If you write `@ContextConfiguration(classes = OrderRepositoryTestConfig.class)` for a repository test, that configuration class itself must provide or import the required components such as entity manager factory, transaction manager, repository scanning, and datasource. `@DataJpaTest` prepares most of that setup by Boot convention, so it is usually more concise for JPA testing.

## 6. @ContextConfiguration Does Not Create a Boot Test Slice by Itself

A test using only:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class SomeSpringTest {
}
```

is instructing Spring Test to load `TestConfig`. It does not automatically acquire the behaviors specific to `@WebMvcTest`, `@DataJpaTest`, or `@JsonTest`.

For instance, if `TestConfig` only declares a controller bean, that does not automatically ensure the presence of:

- `DispatcherServlet` and required `HandlerMapping` beans.
- Message converters for JSON.
- Validation infrastructure.
- View resolvers.
- Required interceptors or controller advice.
- Spring Boot auto-configuration.

Those components must be explicitly configured/imported or prepared by a slice or Boot test annotation.

Similarly, `@ContextConfiguration` does not automatically create an embedded database, does not scan JPA entities and repositories, and does not configure `TestEntityManager`. Those tasks belong to the JPA test slice configuration or a project-authored configuration.

## 7. Combining Test Slices with Additional Configuration

A test slice may need extra test-specific beans or production configuration not automatically discovered by the slice. Spring Boot supports the following ways to add them:

### Using @Import

```java
@WebMvcTest(OrderController.class)
@Import(OrderWebConfiguration.class)
class OrderControllerTest {
}
```

`@Import` is suitable when you need to bring one or a few specific configuration classes, components, or beans into the context.

### Using @TestConfiguration

```java
@TestConfiguration
class OrderTestConfiguration {

    @Bean
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC);
    }
}
```

Importing the test configuration:

```java
@WebMvcTest(OrderController.class)
@Import(OrderTestConfiguration.class)
class OrderControllerTest {
}
```

`@TestConfiguration` marks additional configuration dedicated to tests. For configurations nested inside a test class, Boot has specific rules so they are not picked up automatically by regular production component scanning; using `@Import` makes the intent to add configuration to the test context explicit.

### Using @ContextConfiguration when you genuinely need to specify context sources

You can combine Spring Test configuration metadata with appropriate test annotations, provided you understand which bootstrapper is in use. Boot test slices have their own bootstrappers and type filters. If your goal is simply to add a bean to a slice, `@Import` or `@TestConfiguration` is usually clearer than redeclaring `@ContextConfiguration`.

If you declare `@ContextConfiguration(classes = ...)` on a test using a Boot slice, make sure that class list does not unintentionally replace or drop application configuration needed by the slice. When selecting configuration sources for an entire Boot application, `@SpringBootTest(classes = ...)` usually expresses intent more clearly.

## 8. Distinguishing from @SpringBootTest

`@SpringBootTest` is a Spring Boot testing annotation used to create a context following the Boot application startup mechanism. Its scope is typically broader than a test slice.

| Annotation | Scope | When to use |
| --- | --- | --- |
| `@WebMvcTest` | MVC slice | Testing controllers and web infrastructure |
| `@DataJpaTest` | JPA slice | Testing repositories, entities, and persistence |
| `@JsonTest` | JSON slice | Testing serialization/deserialization |
| `@SpringBootTest` | Full application context per Boot configuration | Integration testing across multiple layers |
| `@ContextConfiguration` | Configuration source for a Spring Test context | Creating a custom Java/XML context, typically without full Boot |

`@SpringBootTest` can be combined with `@AutoConfigureMockMvc` to test MVC inside the full application context without opening an HTTP port. If a real server is needed, you can choose `webEnvironment = RANDOM_PORT`.

`@ContextConfiguration` can be used in many kinds of Spring tests, but it is not a variant of `@SpringBootTest`. If you want Spring Boot to start a context according to the application's conventions, use the appropriate Boot annotation rather than expecting `@ContextConfiguration` to discover and run all Boot configuration automatically.

## 9. WebApplicationContext and @WebAppConfiguration

In plain Spring Test, if a test needs a `WebApplicationContext`, you can combine `@ContextConfiguration` with `@WebAppConfiguration`:

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = WebMvcTestConfig.class)
class WebApplicationContextTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    @Test
    void createsWebApplicationContext() {
        assertThat(webApplicationContext.getServletContext()).isNotNull();
    }
}
```

`@WebAppConfiguration` instructs Spring Test to create a web environment with a `MockServletContext`. `@ContextConfiguration` supplies the configuration source for the context. The two annotations play complementary roles.

This is still not equivalent to `@WebMvcTest`: `@WebAppConfiguration` creates a web application context, but does not automatically apply the filters and auto-configuration specific to Spring Boot's MVC slice. You must configure MVC appropriately in `WebMvcTestConfig` or use a Boot slice if the goal is MVC testing by Boot convention.

## 10. Context Caching and Its Impact on the Test Suite

The Spring TestContext Framework can cache application contexts across test classes with equivalent configurations. The cache key can be affected by configuration sources, active profiles, property sources, context customizers, context loaders, and other metadata.

This applies to both test slices and tests using `@ContextConfiguration`:

- Two tests with equivalent configurations can reuse a context to reduce startup time.
- Two tests with different configurations may create separate contexts.
- `@DirtiesContext` marks a context to be removed from the cache or closed according to the declared scope.
- Changing configuration or mock beans can cause tests to use different context cache keys.

Do not assume every test using the same annotation shares the same context. For example, two `@WebMvcTest` classes selecting different controllers or using different additional configurations can create separate cache entries.

With test slices, the context is usually smaller and has fewer dependencies, yet singleton beans are still shared within that context. With `@ContextConfiguration`, if multiple tests use the same configuration class and equivalent metadata, the context can also be reused. Avoid mutating shared singleton state across tests without an appropriate reset mechanism.

## 11. Common Supporting Annotations

`@ContextConfiguration` and test slices can be paired with annotations that help configure the test environment:

| Annotation | Purpose |
| --- | --- |
| `@ActiveProfiles` | Selects Spring profiles for the test context |
| `@TestPropertySource` | Declares additional or overriding properties in tests |
| `@DynamicPropertySource` | Registers dynamic properties, commonly used with Testcontainers |
| `@Import` | Adds specific configurations or beans |
| `@TestConfiguration` | Defines configuration dedicated to tests |
| `@DirtiesContext` | Marks the context as needing refresh/removal from the cache |
| `@WebAppConfiguration` | Requests a WebApplicationContext with a simulated Servlet context |

These annotations do not negate the role of a test slice. For example, `@ActiveProfiles("test")` can be used with `@DataJpaTest` to select the test profile; `@DynamicPropertySource` can supply a container database URL to a JPA slice.

## 12. Choosing in Specific Scenarios

| Need | Suggested choice | Reason |
| --- | --- | --- |
| Testing controllers and HTTP mappings | `@WebMvcTest` | Loads the MVC slice without needing the entire application |
| Testing JPA repositories and entity mappings | `@DataJpaTest` | Loads JPA infrastructure and repositories |
| Testing JSON serializers | `@JsonTest` | Loads JSON test infrastructure |
| Testing REST clients | `@RestClientTest` | Prepares client testing and mock server |
| Testing a service with a few self-defined Java beans | `@ContextConfiguration` | Specifies a small context based on test configuration |
| Testing a plain Spring application using XML | `@ContextConfiguration(locations = ...)` | Loads the exact XML resource |
| Testing multiple Boot application layers together | `@SpringBootTest` | Loads a broad application context |
| Adding advice or converters to an MVC slice | `@Import` on the slice | Preserves the slice and adds needed beans |
| Creating helper beans dedicated to a slice | `@TestConfiguration` combined with `@Import` | Separate, readable test configuration |

A quick selection workflow:

1. Identify the layer to test: MVC, JPA, JSON, REST client, or the full application.
2. If a matching test slice exists, start with that slice.
3. Add missing dependencies via mock beans or `@Import`/`@TestConfiguration`.
4. If you need a custom Spring context without needing a Boot slice, use `@ContextConfiguration`.
5. If you need to start multiple layers per Boot configuration, use `@SpringBootTest`.
6. Only use `@ContextConfiguration` alongside a Boot annotation when there is a specific reason regarding context sources and you understand how the Boot annotation's bootstrapper merges configurations.

## 13. Common Mistakes

### Thinking @ContextConfiguration automatically enables auto-configuration

`@ContextConfiguration` only specifies context sources. If a test needs Boot auto-configuration, use `@SpringBootTest`, a Boot test slice, or declare the appropriate auto-configuration mechanism in custom configuration.

### Using @WebMvcTest but expecting real services to load automatically

The MVC slice focuses on the web layer and usually excludes services/repositories from component scanning. Mock the service or import a very specific configuration if the test's goal genuinely requires that bean.

### Using @ContextConfiguration for an MVC test while forgetting MVC configuration

`@WebAppConfiguration` creates a WebApplicationContext and MockServletContext; it does not automatically register the full Spring MVC infrastructure. You must configure MVC explicitly or use `@WebMvcTest`.

### Using @SpringBootTest for every small test

A full application context is often time-consuming and pulls in databases or external services. When only a controller or repository is needed, a slice is usually more focused and faster.

### Adding @ContextConfiguration to a slice just to add one bean

If you only need a single configuration class or test bean, `@Import` usually expresses intent more clearly and has less risk of altering the context sources the Boot slice relies on.

### Confusing a slice with a pure mock test

A test slice still creates a Spring application context and runs real components within the slice's scope. For example, `@DataJpaTest` genuinely initializes JPA repositories and the test database; `@WebMvcTest` runs Spring MVC infrastructure. Dependencies outside the scope are typically mocked or added intentionally.

## 14. Conclusion

Spring Boot test slices such as `@WebMvcTest`, `@DataJpaTest`, and `@JsonTest` help test a single layer with the appropriate auto-configuration group and component filters. `@ContextConfiguration` is a foundational annotation of the Spring TestContext Framework, used to specify Java configurations, XML resources, initializers, or loaders that build an application context.

Choose a test slice when you want to test a layer by Spring Boot conventions. Use `@ContextConfiguration` when you need a directly defined Spring context and control over configuration sources. When a slice needs extra beans, prefer `@Import` or `@TestConfiguration`; when you need the whole Boot application, use `@SpringBootTest`. Understanding each annotation's role keeps tests well-scoped, starts just enough context, and accurately reflects the layer under test.
