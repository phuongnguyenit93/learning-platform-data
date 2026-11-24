# `@TestBean` and Factory Methods for Replacement Instances

In Spring testing, we sometimes need to replace a real bean with a test-provided implementation. For example, `OrderService` uses `PaymentGateway` to send payment requests; an integration test wants to keep `OrderService` and the Spring configuration intact while replacing the real gateway with a fake that returns success or failure based on the test scenario. Spring Framework 6.2 provides `@TestBean` to register a replacement instance created by a test factory method.

`@TestBean` annotates a field in a test class. Spring locates the bean to replace by the field's type, qualifier, or bean name; it then invokes a `static`, no-argument factory method to create the replacement instance. That instance is placed into the `ApplicationContext` and also injected into the test field. As a result, other beans in the context use the replacement implementation through normal dependency injection.

## 1. What Problem Does `@TestBean` Solve?

An integration test often needs to keep many parts of the application running for real, while controlling a specific dependency. That dependency might be a payment gateway, a shipping service, an email sender, or an external API client.

For example, the production configuration registers a gateway:

```java
@Configuration
class PaymentConfiguration {
    @Bean
    PaymentGateway paymentGateway(PaymentHttpClient client) {
        return new RemotePaymentGateway(client);
    }
}
```

`OrderService` receives the gateway via its constructor:

```java
@Service
class OrderService {
    private final PaymentGateway paymentGateway;

    OrderService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    PaymentResult checkout(Order order) {
        return paymentGateway.charge(
                new PaymentRequest(order.id(), order.total()));
    }
}
```

In a test, we want to use the real `OrderService` while controlling the gateway's result. We can write a fake:

```java
final class FakePaymentGateway implements PaymentGateway {
    private PaymentResult nextResult = PaymentResult.approved("test-payment-1");

    void setNextResult(PaymentResult result) {
        this.nextResult = result;
    }

    @Override
    public PaymentResult charge(PaymentRequest request) {
        return nextResult;
    }
}
```

`@TestBean` lets you register this fake to replace the gateway bean in the test context. The test does not need to manually instantiate `OrderService` or build a separate `ApplicationContext` just to replace one dependency.

## 2. Basic Syntax

`@TestBean` belongs to the package:

```java
import org.springframework.test.context.bean.override.convention.TestBean;
```

The annotation is placed on a non-`static` field in the test class. If no factory method name is specified, Spring looks for a no-argument static method with the same name as the field or the specified bean name.

```java
@SpringBootTest
class OrderServiceIntegrationTest {
    @TestBean
    private PaymentGateway paymentGateway;

    @Autowired
    private OrderService orderService;

    static PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }

    @Test
    void completesCheckoutWithFakeGateway() {
        PaymentResult result = orderService.checkout(
                new Order("order-42", new BigDecimal("30.00")));

        assertThat(result.approved()).isTrue();
        assertThat(paymentGateway).isInstanceOf(FakePaymentGateway.class);
    }
}
```

In the example, the `paymentGateway` field asks Spring to replace the matching bean with the instance produced by `paymentGateway()`. The factory method must be `static`, take no parameters, and return a type compatible with `PaymentGateway`.

The replacement happens in the context's bean factory. Other injection points requesting that bean, such as the `OrderService` constructor, also receive the replacement instance. The `@TestBean`-annotated field in the test class is injected with the same instance so the test can configure or inspect the fake.

`@TestBean` was introduced in Spring Framework 6.2. If the project uses an older Spring Framework version, this annotation will not be on the classpath. With Spring Boot, use a Boot version that manages Spring Framework 6.2 or later; do not arbitrarily upgrade `spring-test` alone and create version mismatches across Spring modules.

## 3. Factory Method Naming Rules

The factory method is a core part of `@TestBean`. By default, Spring derives the method name from the annotated field or the specified bean name.

Simple example:

```java
@TestBean
private CustomerRepository customerRepository;

static CustomerRepository customerRepository() {
    return new InMemoryCustomerRepository();
}
```

The field name is `customerRepository`, so the default factory method is `customerRepository()`. The method must be static and have a single return type compatible with the field type.

If the annotation specifies a bean name:

```java
@TestBean(name = "primaryPaymentGateway")
private PaymentGateway gateway;

static PaymentGateway primaryPaymentGateway() {
    return new FakePaymentGateway();
}
```

When `name` is specified and `methodName` is omitted, the bean name is used to derive the factory method name. In the example, Spring looks for `primaryPaymentGateway()`.

### 3.1. Specifying `methodName`

To decouple the field name from the factory method name or make the intent clearer, use the `methodName` attribute:

```java
@TestBean(methodName = "createFakePaymentGateway")
private PaymentGateway paymentGateway;

static PaymentGateway createFakePaymentGateway() {
    return new FakePaymentGateway();
}
```

`methodName` specifies the name of the static method that Spring looks for. The method must still take no parameters and return a type compatible with the field.

You can combine `name` and `methodName`:

```java
@TestBean(
        name = "paymentGateway",
        methodName = "createSandboxGateway",
        enforceOverride = true)
private PaymentGateway gateway;

static PaymentGateway createSandboxGateway() {
    return new SandboxPaymentGateway();
}
```

Here, `paymentGateway` is the bean being replaced; `createSandboxGateway()` is the factory method. The field name `gateway` is no longer used to select the bean because `name` explicitly specifies the target bean.

### 3.2. Factory Method in Another Class

The factory method can be placed in the test class, a superclass, an interface implemented by the test class, or the enclosing class hierarchy for nested tests. If you want to use an external utility class, you can specify the fully qualified name using the `fully.qualified.ClassName#methodName` syntax:

```java
@TestBean(methodName = "com.example.test.TestBeanFactories#createPaymentGateway")
private PaymentGateway paymentGateway;
```

Utility class:

```java
package com.example.test;

public final class TestBeanFactories {
    private TestBeanFactories() {
    }

    public static PaymentGateway createPaymentGateway() {
        return new FakePaymentGateway();
    }
}
```

This approach is useful when multiple test classes share a complex factory or when you want to keep the test class focused on scenarios. The external factory must still be a no-argument static method returning a compatible type.

### 3.3. Search Scope and Visibility

Spring searches for the factory method in the class declaring the `@TestBean` field, its superclasses, and implemented interfaces. If the field is inside a nested test class, Spring also searches the enclosing class hierarchy. This allows placing shared factories in a base test class or enclosing class when the test structure fits.

The field and factory method do not have to be `public`. They can be `private`, package-private, `protected`, or `public`, depending on project conventions. Even so, keeping factories in an easy-to-read scope with clear names helps maintainers immediately see how replacement beans are created.

If Spring cannot find the factory method, finds multiple matching methods with the same name, or the method does not match the required signature, the context will fail to initialize. Check the name, `static` modifier, parameter count, and return type before adjusting bean configuration.

## 4. Selecting the Bean to Replace by Type or Name

By default, Spring uses the type of the `@TestBean` field to find a matching bean definition in the context. If there is only one bean of that type, selection is straightforward. If multiple beans exist, narrow the choice with a qualifier or bean name.

### 4.1. Replacing by Type

```java
@TestBean
private PaymentGateway paymentGateway;

static PaymentGateway paymentGateway() {
    return new FakePaymentGateway();
}
```

Spring searches for a bean whose type matches `PaymentGateway`. If the context has only one candidate, that bean is replaced.

### 4.2. Using `@Qualifier` When Multiple Beans Share the Same Type

Suppose the application has two gateways:

```java
@Bean
@Qualifier("primary")
PaymentGateway primaryGateway() {
    return new RemotePaymentGateway(primaryClient);
}

@Bean
@Qualifier("backup")
PaymentGateway backupGateway() {
    return new RemotePaymentGateway(backupClient);
}
```

The test can specify which bean to replace using a qualifier:

```java
@TestBean
@Qualifier("primary")
private PaymentGateway paymentGateway;

static PaymentGateway paymentGateway() {
    return new FakePaymentGateway();
}
```

Without a qualifier, the field name is used as a fallback qualifier when candidates need to be disambiguated. That means the field name can affect which bean is selected. Use a field name that clearly indicates the target bean and avoid renaming it arbitrarily if bean selection relies on the name.

### 4.3. Replacing by Name with `name` or `value`

When you know the exact bean name, you can use `name`:

```java
@TestBean(name = "backupGateway")
private PaymentGateway gateway;

static PaymentGateway backupGateway() {
    return new FakePaymentGateway();
}
```

`value` is an alias for `name`, so you can write the shorthand:

```java
@TestBean("backupGateway")
private PaymentGateway gateway;
```

When using the `value` shorthand, the default factory method is derived from the bean name if `methodName` is not specified. Selecting by name is especially useful when multiple beans implement the same interface and the test needs to replace an exact one.

## 5. `enforceOverride`: Requiring the Bean to Exist

By default, `@TestBean` uses a replace-or-create strategy. If no matching bean is found in the context, Spring can register the bean created by the factory method as a new bean.

This is convenient when the test configuration lacks the corresponding production bean, but it can hide configuration errors. For example, a test intends to replace an existing `PaymentGateway`; if the production bean is excluded from the context due to a wrong profile or component scan, the test might still pass with a newly created bean without proving that an override occurred.

When you want the test to fail if there is no bean to replace, set `enforceOverride = true`:

```java
@TestBean(enforceOverride = true)
private PaymentGateway paymentGateway;

static PaymentGateway paymentGateway() {
    return new FakePaymentGateway();
}
```

With this configuration, Spring requires the target bean to already exist. If no matching bean is found, context creation fails. This is the clear choice when the test's goal is to replace a registered production bean.

| Configuration | When Target Bean Exists | When Target Bean Does Not Exist |
|---|---|---|
| `@TestBean` | Replaces bean with factory instance | Creates a new bean from factory |
| `@TestBean(enforceOverride = true)` | Replaces bean with factory instance | Fails during context initialization |

Choose according to the test's intent. If the test needs to supply a test-only collaborator not already in the context, the create-by-default behavior may fit. If the test must prove that a specific bean was replaced, `enforceOverride = true` helps catch missing configuration.

## 6. What Kind of Object Should the Factory Method Create?

A factory method can return a fake, a stub, or a specialized test implementation. It does not need to be a Mockito mock. This is a useful distinction: `@TestBean` focuses on creating a replacement instance via an ordinary Java method.

### 6.1. A Fake with Simple Behavior

```java
final class InMemoryCustomerRepository implements CustomerRepository {
    private final Map<Long, Customer> customers = new HashMap<>();

    @Override
    public Optional<Customer> findById(Long id) {
        return Optional.ofNullable(customers.get(id));
    }

    @Override
    public Customer save(Customer customer) {
        customers.put(customer.id(), customer);
        return customer;
    }
}
```

A test can replace the repository with the fake:

```java
@SpringBootTest
class CustomerServiceIntegrationTest {
    @TestBean
    private CustomerRepository customerRepository;

    @Autowired
    private CustomerService customerService;

    static CustomerRepository customerRepository() {
        return new InMemoryCustomerRepository();
    }
}
```

The fake implements part of the repository contract in memory. It helps verify the service and Spring wiring, but does not verify SQL, mappings, or real database transactions. If the goal is to test persistence, use a repository integration test with an appropriate database.

### 6.2. A Stub Returning Scenario-Based Results

```java
final class StubInventoryClient implements InventoryClient {
    private InventoryStatus nextStatus = InventoryStatus.AVAILABLE;

    void returnStatus(InventoryStatus status) {
        this.nextStatus = status;
    }

    @Override
    public InventoryStatus check(String sku) {
        return nextStatus;
    }
}
```

Factory method creating the stub:

```java
@TestBean
private InventoryClient inventoryClient;

static InventoryClient inventoryClient() {
    return new StubInventoryClient();
}
```

The test can force specific outcomes by accessing the injected field. Because the bean belongs to the singleton context, keep in mind that stub state can be shared if the context is cached or reused.

### 6.3. Using a Builder in the Factory Method

When a fake requires multiple configuration options, a builder helps express default test data:

```java
static PaymentGateway paymentGateway() {
    return FakePaymentGateway.builder()
            .defaultResult(PaymentResult.approved("test-payment"))
            .supportsRefunds(true)
            .build();
}
```

The factory method should focus on creating the instance with test defaults. If building the fake involves many steps or test-method-specific data, keep the factory simple and configure the fake in each test through an explicit API.

## 7. Lifecycle of the Replacement Bean

`@TestBean` creates a bean in the `ApplicationContext`, rather than creating a new object every time a test method runs. The bean is managed by the context lifecycle and is typically a singleton. Spring replaces the bean definition in the bean factory; injection points using that bean receive the replacement instance.

This means:

- The factory method is invoked when the context is created and the bean override is registered.
- The `@TestBean` field in the test receives the replacement instance.
- Other services in the context also receive that instance via dependency injection.
- If the context is cached and reused by Spring Test, the replacement bean can persist across multiple test methods or compatible test classes.
- Mutating state in the fake can affect subsequent tests if not reset.

Do not store per-test-method data in a singleton fake without a reset mechanism. You can provide a `reset()` API and call it in `@BeforeEach`, or design a stateless fake with fixed behavior. If a fake holds substantial state that cannot be safely restored, consider an appropriate context scope.

Example resetting a fake:

```java
@SpringBootTest
class NotificationServiceIntegrationTest {
    @TestBean
    private NotificationGateway notificationGateway;

    @Autowired
    private NotificationService notificationService;

    private static RecordingNotificationGateway notificationGateway() {
        return new RecordingNotificationGateway();
    }

    @BeforeEach
    void resetGateway() {
        ((RecordingNotificationGateway) notificationGateway).reset();
    }
}
```

In this example, the factory returns a concrete implementation while the field has the interface type. Casting in setup shows that the test depends on the fake implementation. If casting is needed in multiple places, you can declare the field with the concrete fake type if that type is compatible and bean type selection remains unambiguous, or keep a helper method that returns the cast fake once.

## 8. `@TestBean` in a Context Hierarchy

Some applications use `@ContextHierarchy` to create parent and child contexts. By default, bean overrides apply across contexts in the hierarchy. This may be undesirable if the bean exists at only one level or if the same bean type appears at multiple levels.

Spring Framework 6.2.6 added the `contextName` attribute to `@TestBean`, allowing you to restrict the override to a named level in the context hierarchy:

```java
@ContextHierarchy({
        @ContextConfiguration(name = "root", classes = RootConfig.class),
        @ContextConfiguration(name = "web", classes = WebConfig.class)
})
class WebIntegrationTest {
    @TestBean(contextName = "root")
    private PaymentGateway paymentGateway;

    static PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
```

`contextName` must match the `name` on the `@ContextConfiguration` of the level to override. If the project uses Spring Framework 6.2.0 through 6.2.5, this attribute is not yet available; check the version before using it.

Do not use `contextName` when the test has only a single context. For simple configurations, leaving this attribute unset keeps the annotation concise.

## 9. `@TestBean` and Other Bean-Override Annotations

Spring Framework 6.2 standardized bean overriding in Spring Test. `@TestBean`, `@MockitoBean`, and `@MockitoSpyBean` can all replace beans in the test context, but they create instances differently.

| Annotation | Replacement Instance | Common Purpose |
|---|---|---|
| `@TestBean` | Static factory method provided by the test | Fake or custom implementation |
| `@MockitoBean` | Mockito mock | Stub responses and verify interactions |
| `@MockitoSpyBean` | Spy wrapping the real bean | Keep real behavior while observing or replacing part of it |

Example with `@MockitoBean`:

```java
@SpringBootTest
class OrderServiceMockBeanTest {
    @MockitoBean
    private PaymentGateway paymentGateway;

    @Autowired
    private OrderService orderService;

    @Test
    void usesConfiguredGatewayResponse() {
        when(paymentGateway.charge(any(PaymentRequest.class)))
                .thenReturn(PaymentResult.approved("mock-payment"));

        PaymentResult result = orderService.checkout(order());

        assertThat(result.approved()).isTrue();
        verify(paymentGateway).charge(any(PaymentRequest.class));
    }
}
```

This example uses a Mockito mock because the test needs stubbing and verification. If you need a fake with in-memory data or algorithms, `@TestBean` is usually more natural. If you want to observe a real bean, `@MockitoSpyBean` may fit.

There is no need to replace every collaborator with `@TestBean`. A hand-written fake is valuable when it models a meaningful contract; if the test only needs a simple response and call verification, `@MockitoBean` can be shorter.

## 10. Comparison with `@TestConfiguration` and `@Import`

`@TestConfiguration` declares additional configuration for tests; `@TestBean` directly marks the field to replace and the factory method creating the instance. Both approaches can achieve similar results, but their organization differs.

With `@TestConfiguration`:

```java
@TestConfiguration
class PaymentTestConfiguration {
    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}

@SpringBootTest
@Import(PaymentTestConfiguration.class)
class PaymentIntegrationTest {
    @Autowired
    private OrderService orderService;
}
```

With `@TestBean`:

```java
@SpringBootTest
class PaymentIntegrationTest {
    @TestBean
    private PaymentGateway paymentGateway;

    static PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }

    @Autowired
    private OrderService orderService;
}
```

`@TestConfiguration` fits when you want to group multiple beans, property settings, factories, or test infrastructure into a configuration class. `@TestBean` fits when the goal is to replace one specific bean and keep the factory right next to the test that uses it.

If multiple tests share a complex fake configuration, a top-level `@TestConfiguration` combined with `@Import` can be easier to reuse. If you are only replacing a single collaborator, `@TestBean` keeps the intent concise and direct.

## 11. Context Caching and `@TestBean` Field Names

The Spring TestContext Framework caches the `ApplicationContext` based on merged configuration. Bean overrides are part of the test configuration, and field metadata—including qualifier/name—can affect how the context cache key is computed.

If multiple test classes replace the same bean in the same way, keep field names and qualifiers consistent. For example, if all of them replace the `paymentGateway` bean, use the `paymentGateway` field name across related classes rather than naming it `gateway` in one class and `fakeGateway` in another without a configuration reason.

Renaming the field can change how Spring infers candidates or produce a different override configuration, leading to a context cache miss and starting a new context. Do not rename a field arbitrarily if it participates in bean selection.

Context caching also means a singleton fake can be shared. Keep fakes free of per-test-method mutable state or reset state in `@BeforeEach`. If a dedicated context is truly needed because a test alters context state irreversibly, you can use `@DirtiesContext` with an appropriate scope. Do not use this annotation merely to clean up database or file data.

## 12. Which Beans Can Be Replaced?

`@TestBean` replaces singleton beans. If the target bean has a non-singleton scope, overriding it causes an error. This aligns with the test context model: a single replacement instance is registered in the bean factory and shared across injection points.

If the application has prototype or request-scoped beans, consider testing appropriately for that scope:

- For prototypes, create an appropriate factory/provider or test the logic at the component level without replacing the bean with a singleton `@TestBean`.
- For request/session scopes, use a web test context and the corresponding scope mechanisms; `@TestBean` does not turn a request-scoped bean into a singleton eligible for arbitrary replacement.
- For a `FactoryBean`, when overriding a bean produced by a `FactoryBean`, Spring replaces the `FactoryBean` with a singleton bean corresponding to the value returned by the factory method.

Before using `@TestBean`, verify that the target bean is a singleton and know the exact bean name/type registered by the context.

## 13. Common Errors and How to Handle Them

### Factory method not found

Check whether the default method name matches the field name or bean name. If using a different name, declare `methodName`. Verify that the method is `static`, has no parameters, and is in the class hierarchy searchable by Spring; if it is in another class, use the `ClassName#methodName` syntax.

### Incompatible factory method return type

The return type must be compatible with the annotated field type. If the field is `PaymentGateway`, the factory can return `FakePaymentGateway` because the fake implements that interface. An unrelated type prevents the context from initializing.

### Multiple beans of the same type

Use `@Qualifier` or `name` to specify the candidate. Otherwise, Spring may fail to determine which bean to replace or use the field name as a fallback qualifier.

### Test still runs even though the production bean is missing

By default, `@TestBean` may create a new bean if no matching bean is found. If the test must replace an existing bean, use `enforceOverride = true` to turn a missing bean into a configuration error.

### Fake bean retains state between tests

The replacement bean belongs to the context and can be cached. Reset the fake in `@BeforeEach`, make the fake stateless, or isolate the context when genuinely justified.

### Placing the annotation on a `static` field

`@TestBean` is placed on a non-`static` instance field. Only the factory method is `static`. Keep these two requirements distinct.

### Using `@TestBean` with a prototype bean

Only singleton beans can be overridden. Check the target bean's scope and choose an appropriate testing approach if the bean uses another scope.

### Mistakenly using `@TestBean` instead of a mock

`@TestBean` does not provide Mockito's `when` or `verify` APIs. If you need Mockito stubbing/interaction verification, use `@MockitoBean`; if you need a fake with custom behavior, use `@TestBean`.

### Overriding the wrong level in a context hierarchy

If the same bean type appears at multiple levels, use `contextName` on Spring Framework 6.2.6 or later to restrict the override to the matching named level.

## 14. Process for Using `@TestBean`

When you need to replace a bean in a Spring integration test, follow this sequence:

1. Identify the production bean to replace and check its type, bean name, qualifier, and scope.
2. Declare a `@TestBean` instance field with an appropriate type.
3. Select the bean by default type, qualifier, or `name` if the context has multiple candidates.
4. Write a `static`, no-argument factory method returning a fake/stub of a compatible type.
5. Let Spring infer the method from the field/bean name or specify `methodName` explicitly.
6. Use `enforceOverride = true` if the test must ensure the production bean actually exists before replacing it.
7. Run the scenario through the real autowired bean and verify behavior at the business boundary.
8. If the fake holds state, reset it between test methods because the context may be cached.
9. If using a context hierarchy, identify the level to override and use `contextName` when supported by your Spring version.

The factory method should be easy to read and responsible for creating exactly one replacement instance. Keep the fake small, model only the contract the service needs, and avoid putting complex business logic into the test factory.

## 15. Comprehensive Example: Replacing a Gateway and Testing Both Approval and Decline

Suppose `PaymentService` calls a `PaymentGateway`. The test wants to keep the service, repository, and Spring configuration real, while controlling gateway responses.

```java
final class ConfigurablePaymentGateway implements PaymentGateway {
    private PaymentResult nextResult;
    private final List<PaymentRequest> requests = new ArrayList<>();

    ConfigurablePaymentGateway() {
        this.nextResult = PaymentResult.approved("test-payment");
    }

    void returnResult(PaymentResult result) {
        this.nextResult = result;
    }

    List<PaymentRequest> requests() {
        return List.copyOf(requests);
    }

    void reset() {
        requests.clear();
        nextResult = PaymentResult.approved("test-payment");
    }

    @Override
    public PaymentResult charge(PaymentRequest request) {
        requests.add(request);
        return nextResult;
    }
}
```

Test class:

```java
@SpringBootTest
class PaymentServiceIntegrationTest {
    @TestBean(enforceOverride = true)
    private PaymentGateway paymentGateway;

    @Autowired
    private PaymentService paymentService;

    private ConfigurablePaymentGateway fakeGateway() {
        return (ConfigurablePaymentGateway) paymentGateway;
    }

    static PaymentGateway paymentGateway() {
        return new ConfigurablePaymentGateway();
    }

    @BeforeEach
    void resetGateway() {
        fakeGateway().reset();
    }

    @Test
    void completesPaymentWhenGatewayApproves() {
        fakeGateway().returnResult(
                PaymentResult.approved("payment-42"));

        PaymentResult result = paymentService.pay(
                new PaymentRequest("order-42", new BigDecimal("30.00")));

        assertThat(result.approved()).isTrue();
        assertThat(fakeGateway().requests()).hasSize(1);
        assertThat(fakeGateway().requests().get(0).orderId())
                .isEqualTo("order-42");
    }

    @Test
    void returnsDeclinedResultWhenGatewayRejects() {
        fakeGateway().returnResult(PaymentResult.declined("insufficient-funds"));

        PaymentResult result = paymentService.pay(
                new PaymentRequest("order-43", new BigDecimal("90.00")));

        assertThat(result.approved()).isFalse();
        assertThat(result.reason()).isEqualTo("insufficient-funds");
    }
}
```

In this example, the factory method is static and returns a `ConfigurablePaymentGateway`. The field is declared with the `PaymentGateway` interface so Spring selects the bean by type and the service continues to depend on the abstraction. The `fakeGateway()` helper performs the cast in a single place so the test can control the fake. `@BeforeEach` resets state because the replacement bean follows the context lifecycle and can be reused across test methods.

If you want to avoid casting, you can declare the field with the concrete type `ConfigurablePaymentGateway` and use `@Qualifier` or `name` to identify the interface bean to replace. When doing so, ensure the field type remains compatible with the target bean and does not introduce ambiguity in the context.

## 16. Principles to Remember

- `@TestBean` belongs to Spring Framework 6.2 and is used on an instance field in a test class.
- Spring creates the replacement bean from a `static`, no-argument factory method whose return type is compatible with the field.
- By default, the factory method name is derived from the field name or bean name; use `methodName` when a different name is needed.
- The bean is selected by type, qualifier, or the name specified via `name`/`value`.
- `enforceOverride = true` requires the target bean to exist; by default Spring can create a new bean if no candidate is found.
- The factory method can live in the test class, superclass, interface, enclosing hierarchy, or an external class referenced via `ClassName#methodName`.
- The replacement bean is placed into the `ApplicationContext`, so other injection points receive that instance as well.
- Only singleton beans can be replaced; stateful fakes must be reset when the context is reused.
- Use `@TestBean` for fakes/custom implementations; use `@MockitoBean` when Mockito stubbing/verification is needed and `@MockitoSpyBean` when spying on a real bean.
- With a context hierarchy, use `contextName` from Spring Framework 6.2.6 onward when restricting the override to a specific level.

`@TestBean` lets you replace a collaborator with an instance created by a test factory method while keeping the rest of the Spring context active. By selecting the right bean, naming the factory clearly, and managing fake state according to the context lifecycle, integration tests can control external dependencies while still verifying the wiring and behavior of real services.
