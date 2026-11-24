# Nested Configuration Classes and the Scope of Loaded Beans

When testing with Spring, an `ApplicationContext` is built from configuration classes, component scans, imported beans, and merged property sources. Configuration determines **which beans are present in the context**; scope determines **how each bean is created and shared within that context**. The two concepts are related but not interchangeable: loading a bean into the context does not mean every test receives a new instance, and choosing `prototype` scope does not make Spring recreate the entire context.

Spring Test allows declaring configuration directly inside a test class using a static nested configuration class. Spring Boot also provides `@TestConfiguration` to add beans for testing while preserving the main application configuration. By understanding how nested classes are detected and imported, you can build lean contexts, swap collaborators per test group, and avoid altering production configuration. At the same time, understanding bean scopes explains why a singleton can retain state across multiple tests or why a request-scoped bean only exists during a single HTTP request.

## 1. Configuration Determines Which Beans Are Loaded

An `ApplicationContext` holds bean definitions and the bean instances created from those definitions. A bean can enter the context through several paths:

- Declaring `@Bean` methods inside a `@Configuration` class.
- Scanning components with `@ComponentScan` or Spring Boot's component scan mechanism.
- Importing configuration or component classes with `@Import`.
- Loading XML resources via `@ImportResource` or `@ContextConfiguration(locations = ...)`.
- Being registered by auto-configuration, an `ImportSelector`, a registrar, or Spring extension mechanisms.

In testing, annotations such as `@ContextConfiguration`, `@SpringBootTest`, `@WebMvcTest`, and `@DataJpaTest` determine how the context is created. Test configuration can supplement or replace part of the bean graph depending on the annotation and declaration.

For example, a plain Spring context can load only the specified beans:

```java
@Configuration
class BillingConfiguration {
    @Bean
    BillingService billingService(PaymentGateway gateway) {
        return new BillingService(gateway);
    }
}

@Configuration
class BillingTestConfiguration {
    @Bean
    PaymentGateway paymentGateway() {
        return new InMemoryPaymentGateway();
    }
}

@SpringJUnitConfig(classes = {
        BillingConfiguration.class,
        BillingTestConfiguration.class
})
class BillingIntegrationTest {
    @Autowired
    private BillingService billingService;
}
```

The context above contains `BillingService` and the `PaymentGateway` implementation provided by the test configuration. It does not need to scan the entire application package if the test only requires these two components.

One point to remember: configuration annotations are not a list of bean instances created immediately. Spring registers bean definitions first; instances are created according to each bean's scope and initialization timing. By default, singletons are usually instantiated eagerly when context refresh completes, whereas lazy beans may only be created when first requested.

## 2. Static Nested Configuration Classes

Java allows declaring a class inside another class. With Spring configuration, a static nested class is often used to place configuration close to the test class that uses it:

```java
class CatalogIntegrationTest {
    @Configuration
    static class CatalogTestConfiguration {
        @Bean
        CatalogRepository catalogRepository() {
            return new InMemoryCatalogRepository();
        }
    }
}
```

The nested configuration class should be `static`. A non-static inner class requires an instance of the enclosing class to be instantiated; Spring does not automatically have an appropriate test instance to construct that configuration object. A static nested class does not depend on an enclosing instance and can be processed by Spring as an independent configuration class.

### 2.1. How Spring Test Detects Nested Configuration

With `@ContextConfiguration`, if neither `classes` nor `locations` is declared, the Spring TestContext Framework can detect static nested classes annotated with `@Configuration` inside the test class to use as default configuration classes. This allows writing:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration
class CatalogIntegrationTest {
    @Autowired
    private CatalogService catalogService;

    @Configuration
    static class Config {
        @Bean
        CatalogRepository catalogRepository() {
            return new InMemoryCatalogRepository();
        }

        @Bean
        CatalogService catalogService(CatalogRepository repository) {
            return new CatalogService(repository);
        }
    }
}
```

When there are multiple nested configuration classes, specify `classes` explicitly if you need exact control over the configuration set or want to avoid relying on default detection. Example:

```java
@ContextConfiguration(classes = {
        CatalogIntegrationTest.RepositoryConfig.class,
        CatalogIntegrationTest.ServiceConfig.class
})
class CatalogIntegrationTest {
    @Configuration
    static class RepositoryConfig {
        @Bean
        CatalogRepository catalogRepository() {
            return new InMemoryCatalogRepository();
        }
    }

    @Configuration
    static class ServiceConfig {
        @Bean
        CatalogService catalogService(CatalogRepository repository) {
            return new CatalogService(repository);
        }
    }
}
```

Splitting configuration by responsibility can be useful when a test has many beans. For a small test, a single nested configuration class is usually easier to read than multiple scattered configuration classes.

### 2.2. Nested `@Configuration` Inside `@SpringBootTest`

In Spring Boot, if a test has a nested class annotated with `@Configuration`, that class may be treated as the primary configuration for the test instead of searching for the application's `@SpringBootConfiguration`. This can unintentionally cause the test to load only the small nested configuration and skip the application's auto-configuration or component scan.

The following example may lead an author to think they are only adding a fake bean, when in fact they have supplied a replacement configuration:

```java
@SpringBootTest
class OrderIntegrationTest {
    @Configuration
    static class TestConfig {
        @Bean
        Clock clock() {
            return Clock.systemUTC();
        }
    }
}
```

If the goal is to **supplement** the main Spring Boot configuration with test beans, use `@TestConfiguration`:

```java
@SpringBootTest
class OrderIntegrationTest {
    @Autowired
    private OrderService orderService;

    @TestConfiguration
    static class AdditionalTestConfiguration {
        @Bean
        Clock testClock() {
            return Clock.fixed(
                    Instant.parse("2026-11-12T08:30:00Z"), ZoneOffset.UTC);
        }
    }
}
```

`@TestConfiguration` is designed to declare additional configuration for tests. It preserves Spring Boot's discovery of the main application configuration while adding test beans to the context. When multiple beans of the same type exist, use `@Primary` or `@Qualifier` according to your injection intent.

### 2.3. Top-Level `@TestConfiguration` and `@Import`

A top-level `@TestConfiguration` is typically imported explicitly into the tests that need it:

```java
@TestConfiguration
class FakePaymentConfiguration {
    @Bean
    PaymentGateway paymentGateway() {
        return new InMemoryPaymentGateway();
    }
}

@SpringBootTest
@Import(FakePaymentConfiguration.class)
class PaymentIntegrationTest {
    @Autowired
    private PaymentService paymentService;
}
```

`@TestConfiguration` is marked as a test component and is normally excluded from regular component scanning. This is intentional: a fake or test bean should not accidentally appear in a production context just because it resides in a scanned package. `@Import` indicates which test actively uses that configuration.

You can place a nested `@TestConfiguration` directly inside the test class so its scope of use is immediately visible at the declaration site. If multiple test classes share a configuration, a top-level configuration combined with `@Import` avoids duplication and makes dependencies explicit.

## 3. Distinguishing Ways to Bring Beans into the Context

Similar-looking annotations have different meanings:

| Mechanism | Effect | Suitable Case |
|---|---|---|
| `@ContextConfiguration(classes = ...)` | Specifies configuration used to build the Spring Test context | Spring integration tests needing a specific set of configurations |
| `@SpringBootTest(classes = ...)` | Specifies the Spring Boot application configuration source | Loading the application from a specific main configuration |
| `@Import(...)` | Adds configurations or components to the current configuration | Adding test beans or configuration modules |
| `@TestConfiguration` | Marks additional configuration intended for tests | Fakes, fixed clocks, in-memory adapters |
| `@ComponentScan` | Scans packages to discover components | Loading a group of components by package and filter |
| `@ImportResource` | Loads XML configuration | Applications still using XML or needing to test XML configuration |

Do not confuse `@Import` with `@ComponentScan`. Import adds known configuration types; component scan searches for multiple components within a package region according to filters. For tests, explicit imports generally keep the context smaller and easier to explain.

### 3.1. Component Scanning Can Load More Beans Than Expected

A test configuration with a broad `@ComponentScan` can pull in adapters, clients, or production configurations that the test does not need:

```java
@Configuration
@ComponentScan("com.example")
class BroadTestConfiguration {
}
```

If the root package contains many modules, the context may require datasources, HTTP clients, or properties that the test did not intend to use. Restrict packages or use filters:

```java
@Configuration
@ComponentScan(
        basePackages = "com.example.catalog",
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = RemoteCatalogClient.class))
class CatalogTestConfiguration {
}
```

In many cases, declaring `@Bean` or `@Import` for a few specific components is clearer than scanning a large package and excluding beans one by one.

### 3.2. Bean Creation Conditions

A bean may only be registered when conditions are satisfied, such as `@Profile`, `@ConditionalOnProperty`, `@ConditionalOnClass`, or custom conditions. Thus, a class being inside a component scan does not guarantee the bean always appears.

```java
@Configuration
@Profile("integration")
class IntegrationGatewayConfiguration {
    @Bean
    PaymentGateway paymentGateway() {
        return new SandboxPaymentGateway();
    }
}
```

If a bean is missing, check profiles and conditions before adding another bean of the same type to the test. Two coexisting beans can cause `NoUniqueBeanDefinitionException` or cause Spring to pick the wrong implementation.

## 4. Nested Configuration Classes in JUnit `@Nested` Tests

A nested configuration class and a JUnit `@Nested` test class are two different concepts:

- A nested configuration class is a Java class inside another class, usually `static`, used by Spring to register beans.
- A JUnit `@Nested` class is a group of tests nested inside another test class, usually non-static and having its own JUnit test lifecycle.

Spring Test provides the `@NestedTestConfiguration` annotation to control how nested test classes inherit configuration from the enclosing test class. The default is `INHERIT`, meaning Spring configuration from the enclosing class is inherited into the nested test class according to the corresponding rules.

Example:

```java
@SpringBootTest
class CustomerIntegrationTest {
    @Autowired
    CustomerService customers;

    @Nested
    class WhenCustomerExists {
        @Test
        void loadsCustomer() {
            assertThat(customers).isNotNull();
        }
    }

    @Nested
    class WhenCustomerIsMissing {
        @Test
        void handlesMissingCustomer() {
            assertThat(customers).isNotNull();
        }
    }
}
```

Both test groups share the Spring configuration from the enclosing class. They do not automatically receive separate `ApplicationContext` instances just because they are placed in two nested classes.

If you want a nested test class not to inherit configuration from the enclosing class, you can use:

```java
@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
class CustomerIntegrationTest {
    @Nested
    @SpringBootTest(classes = CustomerOnlyTestApplication.class)
    class IsolatedCustomerConfigurationTest {
        // The nested test class's configuration is used independently.
    }
}
```

`OVERRIDE` makes the nested test class declare its own configuration instead of inheriting the enclosing configuration. This mechanism is useful when a nested test group needs a completely different context. Do not use it merely to group tests by scenario name or business state if the tests still require the same bean graph.

You can configure the project-wide default via the `spring.test.enclosing.configuration` property in `junit-platform.properties`, or declare the annotation at the appropriate level. If you change the default, ensure both IDEs and CI load that configuration.

## 5. What Is Bean Scope?

Scope determines the lifecycle and sharing boundaries of a bean instance. In Spring, the default scope is `singleton`. A singleton bean is created once per bean definition in an `ApplicationContext` and is shared whenever components request that bean.

Common scopes:

| Scope | Meaning | Common Usage |
|---|---|---|
| `singleton` | One instance per bean definition in one container | Stateless services, repositories, configuration |
| `prototype` | Creates a new instance each time the container resolves the bean | Short-lived stateful objects managed by the caller |
| `request` | One instance for the lifecycle of one HTTP request | Data tied to a single request |
| `session` | One instance for the lifecycle of an HTTP session | Per-user session state |
| `application` | One instance within the `ServletContext` scope | Web application state |
| `websocket` | One instance for the lifecycle of a WebSocket session | Per-WebSocket connection state |
| custom scope | Lifecycle defined by the application or an extension | Specialized application needs |

`singleton` does not mean a single instance across the entire JVM. Two different `ApplicationContext` instances can create two different singleton instances for the same class/bean name. Similarly, tests using the context cache can observe the same singleton instance across multiple test classes if they share a context.

## 6. Singleton Scope and Its Impact on Tests

If no scope is declared, a bean defaults to singleton:

```java
@Component
class RequestCounter {
    private final AtomicInteger count = new AtomicInteger();

    int next() {
        return count.incrementAndGet();
    }
}
```

```java
@Configuration
class CounterConfiguration {
    @Bean
    RequestCounter requestCounter() {
        return new RequestCounter();
    }
}
```

Within the same context, places injecting `RequestCounter` receive the same instance. This suits stateless services or beans managing shared resources, but it can cause state leakage if the bean holds mutable data per test or per request.

Test illustrating singleton identity:

```java
@SpringJUnitConfig(CounterConfiguration.class)
class SingletonScopeTest {
    @Autowired
    private RequestCounter firstReference;

    @Autowired
    private RequestCounter secondReference;

    @Test
    void injectsTheSameSingletonInstance() {
        assertThat(firstReference).isSameAs(secondReference);
    }
}
```

In a test suite, Spring can cache and reuse contexts across classes with equivalent configurations. If one test increments the counter to 5, the next test may see that value if it shares the context and the bean is not reset.

Good solutions are usually keeping singleton beans stateless, moving per-call state into parameters or local objects, or providing an explicit reset mechanism for test fixtures. `@DirtiesContext` should only be used when the context itself has been altered and cannot be restored; it is not a general-purpose way to clean up all data.

## 7. Prototype Scope

Prototype creates a new instance each time the bean is requested from the container:

```java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
class ReportDraft {
    private final List<String> lines = new ArrayList<>();

    void addLine(String line) {
        lines.add(line);
    }

    List<String> lines() {
        return List.copyOf(lines);
    }
}
```

Each call to `applicationContext.getBean(ReportDraft.class)` returns a new instance:

```java
@Test
void createsANewPrototypeInstanceForEachLookup() {
    ReportDraft first = context.getBean(ReportDraft.class);
    ReportDraft second = context.getBean(ReportDraft.class);

    assertThat(first).isNotSameAs(second);
}
```

Prototype fits when you need an object with its own state and the caller takes responsibility for its lifecycle after retrieval. Spring creates and configures the bean but does not manage full destruction callbacks for prototypes as it does for singletons; the caller must release resources owned by the prototype.

### 7.1. Prototype Injected into a Singleton

A common mistake is injecting a prototype directly into a singleton:

```java
@Component
class ReportService {
    private final ReportDraft draft;

    ReportService(ReportDraft draft) {
        this.draft = draft;
    }
}
```

`ReportService` is a singleton. When the singleton is created, Spring resolves the `ReportDraft` dependency once and keeps that instance in the field. Having `ReportDraft` in prototype scope does not make Spring automatically replace the field with a new instance on each method call.

If you need a new prototype per operation, use `ObjectProvider`:

```java
@Component
class ReportService {
    private final ObjectProvider<ReportDraft> drafts;

    ReportService(ObjectProvider<ReportDraft> drafts) {
        this.drafts = drafts;
    }

    ReportDraft newDraft() {
        return drafts.getObject();
    }
}
```

Each call to `getObject()` resolves the bean according to its scope, so for a prototype it yields a new instance. You can use `ObjectFactory`, `Provider`, or a scoped proxy depending on your needs, though `ObjectProvider` is often convenient in Spring because it supports additional resolution operations.

## 8. Request and Session Scope

Web scopes require a web-aware `ApplicationContext` and an appropriate HTTP context. `request` creates one bean instance per HTTP request; `session` creates one instance per HTTP session.

```java
@Component
@RequestScope
class RequestMetadata {
    private String correlationId;

    void setCorrelationId(String value) {
        this.correlationId = value;
    }

    String correlationId() {
        return correlationId;
    }
}
```

`@RequestScope` is a shorthand for a request-scoped bean and by default uses an appropriate scoped proxy so a request-scoped bean can be injected into a singleton. The proxy resolves the target instance for the current request.

A session scope example:

```java
@Component
@SessionScope
class ShoppingSession {
    private final List<String> itemIds = new ArrayList<>();

    void add(String itemId) {
        itemIds.add(itemId);
    }

    List<String> items() {
        return List.copyOf(itemIds);
    }
}
```

Do not inject an unproxied request/session object directly into a singleton in a way that resolves the target too early. Use `@RequestScope`/`@SessionScope` with the default scoped proxy or an appropriate provider so the target is retrieved while a request/session is active.

### 8.1. Testing Request Scope

When testing request-scoped beans, a request context must exist. `MockMvc` or a web test environment can set up the appropriate request lifecycle for MVC flows. If you call a service directly in a unit test with no request, accessing a request-scoped bean can throw `ScopeNotActiveException` or an equivalent error.

With Spring MVC, you can test across two separate requests to demonstrate each request receives its own target. Illustrative example:

```java
@SpringBootTest
@AutoConfigureMockMvc
class RequestMetadataIntegrationTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void createsRequestScopedMetadataForEachRequest() throws Exception {
        mockMvc.perform(get("/test/request-id"))
                .andExpect(status().isOk());

        mockMvc.perform(get("/test/request-id"))
                .andExpect(status().isOk());
    }
}
```

To verify two distinct targets, the test endpoint can return a correlation ID generated during the request or a test-only instance identifier. Do not compare proxy objects with `isNotSameAs`, because the proxy can be the exact same Java object while the underlying target changes per request.

### 8.2. Testing Session Scope

Session scope persists across multiple requests belonging to the same session. When testing, you must resend the same session cookie or use MockMvc's session-preserving mechanism. Two requests that do not share a session receive different session-scoped targets; two requests in the same session share the same target for the lifetime of the session.

Do not assume every request creates a new session or that sessions are automatically cleared when a test finishes. Manage sessions/cookies explicitly and clean up state per test.

## 9. Application Scope and WebSocket Scope

Application scope is bound to the `ServletContext` of a web application. It has a broader lifecycle than a request or session, yet still differs from singleton scope: singleton belongs to a bean definition within an `ApplicationContext`, whereas application scope belongs to the `ServletContext`.

In applications with multiple web application contexts or multiple servlet contexts, this distinction can matter. Do not use application scope just because you want to share data across the whole JVM; if the goal is a shared bean within a single Spring context, singleton is usually appropriate.

WebSocket scope is bound to a WebSocket session. The bean is created within the session and can be used across message handlers belonging to the same connection. Testing this scope requires setting up a real WebSocket session lifecycle or a supporting test environment; instantiating the service directly does not create a WebSocket context.

Web scopes only work when the corresponding scope is registered and the context has an active request/session/WebSocket context. If a test lacks that environment, an inactive scope error is usually a sign that the test is running the wrong context type or has not set up the required lifecycle.

## 10. Declaring Scope on `@Bean`

Scope can be declared on a component with `@Scope`, or on a `@Bean` method:

```java
@Configuration
class DraftConfiguration {
    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    ReportDraft reportDraft() {
        return new ReportDraft();
    }
}
```

By default, beans declared with `@Bean` are also singletons. If you need request or session scope, you can use the corresponding scope annotation:

```java
@Bean
@RequestScope
RequestMetadata requestMetadata() {
    return new RequestMetadata();
}
```

### 10.1. `proxyMode` and Scoped Proxies

When a bean has a shorter scope than a bean that depends on it—such as a request-scoped bean injected into a singleton—a scoped proxy allows the singleton to hold a stable proxy while the proxy resolves the target according to the active scope.

You can declare the proxy mode explicitly:

```java
@Bean
@Scope(value = WebApplicationContext.SCOPE_REQUEST,
       proxyMode = ScopedProxyMode.TARGET_CLASS)
RequestMetadata requestMetadata() {
    return new RequestMetadata();
}
```

`TARGET_CLASS` uses a class-based proxy; `INTERFACES` uses an interface-based proxy and requires the bean to implement suitable interfaces. The `@RequestScope` and `@SessionScope` annotations already configure scoped proxies by default in the standard way. There is no need to specify proxy mode explicitly if the default meets your needs.

A scoped proxy does not turn the target scope into a singleton. The proxy is the object injected; the real target is still resolved for the current request/session. Thus, two fields can hold the same proxy reference while receiving different targets in different scopes.

## 11. Full `@Configuration` Mode and `proxyBeanMethods`

`@Configuration` uses a proxy mechanism for `@Bean` methods by default so that calls between bean methods in the same configuration class are routed through the container. This preserves singleton semantics:

```java
@Configuration
class ServiceConfiguration {
    @Bean
    Repository repository() {
        return new InMemoryRepository();
    }

    @Bean
    Service service() {
        return new Service(repository());
    }
}
```

With the default proxy configuration, the call to `repository()` inside `service()` is intercepted by Spring and returns the registered singleton bean, rather than creating an independent repository outside the container.

If you set `proxyBeanMethods = false`, the configuration uses non-proxied mode (lite behavior): direct calls between Java methods are ordinary Java calls. In that case, `service()` calling `repository()` can create a new instance instead of obtaining the container-managed bean. To avoid confusion, use method parameter injection:

```java
@Configuration(proxyBeanMethods = false)
class ServiceConfiguration {
    @Bean
    Repository repository() {
        return new InMemoryRepository();
    }

    @Bean
    Service service(Repository repository) {
        return new Service(repository);
    }
}
```

Spring resolves the `Repository` parameter from the context. This style works clearly with both proxied and non-proxied configurations, while also making bean dependencies explicit.

When testing a nested configuration class, pay attention to `proxyBeanMethods` if `@Bean` methods call one another. A test can see two different instances even though the default bean definition is singleton if the code calls the method directly in lite mode.

## 12. Bean Scope and the Context Cache in Spring Test

The context cache reuses `ApplicationContext` instances across tests with equivalent configurations within the same JVM. Because singleton scope is tied to bean definitions within a context, singleton instances are also shared for as long as the context is reused.

This means:

- JUnit's `PER_METHOD` creates a new test instance per method, but does not create a new Spring context.
- `PER_CLASS` keeps one test instance for the class, but does not inherently change Spring bean scopes.
- Singleton beans in the context cache can be shared across multiple test classes.
- Prototype beans are resolved anew each time they are requested from the container, but a prototype injected directly into a singleton can still be retained in the singleton's field.
- Request/session beans require the proper active web scope; the context cache does not create requests or sessions for tests.

If a test mutates singleton state and cannot reset it, `@DirtiesContext` can mark the context for eviction from the cache. However, if you only need to clear database records or messages, use appropriate transactions/cleanup. Closing the context does not automatically delete data in external systems.

## 13. Verifying Bean Scope with `ApplicationContext`

For singleton and prototype, you can write tests focused on scope behavior:

```java
@SpringJUnitConfig(ScopeTestConfiguration.class)
class BeanScopeTest {
    @Autowired
    private ApplicationContext context;

    @Test
    void singletonReturnsTheSameInstance() {
        Object first = context.getBean("sharedComponent");
        Object second = context.getBean("sharedComponent");

        assertThat(first).isSameAs(second);
    }

    @Test
    void prototypeReturnsDifferentInstances() {
        Object first = context.getBean("draftComponent");
        Object second = context.getBean("draftComponent");

        assertThat(first).isNotSameAs(second);
    }
}

@Configuration
class ScopeTestConfiguration {
    @Bean("sharedComponent")
    Object sharedComponent() {
        return new Object();
    }

    @Bean("draftComponent")
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    Object draftComponent() {
        return new Object();
    }
}
```

The test above verifies scope through direct container lookups. For request/session scope, you need a web context and a request/session lifecycle; you cannot substitute that by calling `getBean()` in a context without an active web scope.

If you need to verify whether a bean was loaded, you can use `containsBean`, `getBeanNamesForType`, or autowire the dependency. However, tests should prioritize the behavior of components using the bean rather than asserting the list of every internal bean in the context, unless the configuration itself is the subject under test.

## 14. Common Mistakes

### Using Nested `@Configuration` When You Only Want to Add Beans

In `@SpringBootTest`, a nested `@Configuration` can replace the automatically discovered main configuration source. If you want to add test beans to the application, use a nested `@TestConfiguration` or import an explicit test configuration.

### Declaring a Non-Static Nested Configuration

Non-static inner classes require an instance of the enclosing class. Use a static nested class so Spring can instantiate the configuration independently.

### Scanning Packages Too Broadly

`@ComponentScan` can pull in unrelated clients, datasources, or production configurations. Limit packages/filters or import the needed beans.

### Assuming `singleton` Means One Instance for the Entire JVM

Singleton is defined per bean definition within one container. Two separate contexts can have two instances; context caching can cause multiple tests to see the same instance.

### Injecting a Prototype into a Singleton and Expecting a New Instance Per Call

Dependencies are resolved when the singleton is created. Use `ObjectProvider<T>` or an equivalent provider to request a new prototype at the time it is needed.

### Accessing Request Scope Without a Request

Unit tests calling a service directly may lack a request context. Use appropriate web tests or design abstractions so business logic does not depend directly on request-scoped state.

### Using `@DirtiesContext` to Clean Up a Database

Closing a context does not mean database data, files, or broker messages are deleted. Use transaction rollback or clean up the actual resources.

### Calling `@Bean` Methods Directly in Lite Configuration

When `proxyBeanMethods = false`, direct Java calls can create new instances. Use method parameter injection so Spring supplies bean dependencies.

## 15. Workflow for Choosing Configuration and Scope

When designing a test context, answer these questions in order:

1. Does the test need the entire application, a slice, or just a specific set of beans?
2. Does the main configuration come from `@SpringBootTest`, `@ContextConfiguration`, or an imported test configuration?
3. Is the nested class being used a configuration class or a JUnit `@Nested` test class?
4. If using Spring Boot, does the nested class need to replace the main configuration or only supplement beans? Choose `@Configuration` or `@TestConfiguration` accordingly.
5. Which beans are created via `@Bean`, component scan, import, profile, or condition?
6. Does each bean's scope match the lifecycle of the data it holds?
7. Are any mutable singletons shared across the context cache?
8. Is any prototype injected into a singleton and needing a provider for repeated resolution?
9. Are web-scoped beans accessed within a valid request/session context?
10. Does the test need state cleanup at the method, request, session, context, or external-system level?

A good test context loads only the beans needed for the behavior under test. Configuration classes clarify bean definition sources; scopes clarify instance lifecycles; cleanup ensures data does not leak into other scenarios. When these three parts are designed explicitly, integration tests become easier to read and predict.

## 16. Key Principles to Remember

- Configuration determines which bean definitions are loaded; scope determines how instances are created and shared.
- A static nested `@Configuration` class can be detected by Spring Test as the default configuration when no explicit configuration source is specified.
- In Spring Boot, use `@TestConfiguration` when you want to add test beans while preserving the main application configuration.
- Use `@Import` to bring top-level test configuration into the right tests; avoid overly broad component scans.
- JUnit's `@Nested` differs from nested configuration classes; `@NestedTestConfiguration` controls inheriting configuration from the enclosing test class.
- Singleton is one instance per bean definition within an `ApplicationContext`, not one instance across the entire JVM.
- Prototype creates a new instance when the container resolves the bean; injecting it directly into a singleton does not make the dependency change on every call.
- Request/session/application/WebSocket scopes require the proper web context and corresponding lifecycle.
- Context caching can cause singleton beans to be shared across multiple tests; JUnit creating a new test instance does not mean Spring creates a new context.
- Use `@DirtiesContext` when the context genuinely cannot be reused; clean up databases, files, and brokers with dedicated mechanisms.

Nested configuration classes keep test configuration close to where it is used, while bean scopes define the lifetime and sharing boundaries of each dependency. Combining both mechanisms properly produces a lean `ApplicationContext`, avoids accidentally loading production beans, and keeps state across tests under control.
