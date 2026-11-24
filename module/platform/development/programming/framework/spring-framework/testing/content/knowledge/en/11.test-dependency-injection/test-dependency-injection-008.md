# Dependency Injection in Nested Test Classes

JUnit Jupiter lets you group related tests using the `@Nested` annotation. When a test class is nested inside another class, the nested class can still declare its own dependencies and needs to be prepared before tests run. With Spring Framework Test, `SpringExtension` coordinates with the TestContext Framework to inject beans into each test instance, including instances of nested test classes.

Both mechanisms participate with distinct responsibilities:

- JUnit Jupiter manages the nested class structure, creates test instances, and executes lifecycle callbacks.
- Spring Test manages the `ApplicationContext`, prepares test instances, and injects dependencies according to Spring configuration.

In the usual case, the nested class inherits Spring configuration from its enclosing class. This lets test groups share the same context while declaring dependencies right in the class where they are used. Starting in Spring Framework 5.3, `@NestedTestConfiguration` was added to control this configuration inheritance.

## 1. Nested test classes in JUnit Jupiter

A class annotated with `@Nested` is a test class nested inside another test class. A nested class must be a non-`static` member class because it is bound to an instance of its enclosing class.

```java
class OrderServiceTests {

    @Nested
    class CreateOrder {

        @Test
        void createsAnOrder() {
            // Test order creation behavior.
        }
    }

    @Nested
    class CancelOrder {

        @Test
        void cancelsAnExistingOrder() {
            // Test order cancellation behavior.
        }
    }
}
```

Nested test groups help organize tests by behavior or context. Display names in IDEs and reports can show the path from the enclosing class to the nested class, helping readers see which branch a test is verifying.

JUnit Jupiter still treats each `@Test` method as a separate execution. Under the default `PER_METHOD` lifecycle, JUnit creates a fresh test instance for each test method. For nested tests, an instance of the enclosing class is also created to serve as the enclosing instance for the nested class.

## 2. SpringExtension injects dependencies into test instances

For Spring to participate in the JUnit Jupiter lifecycle, register `SpringExtension`. The concise way is using the composed annotation `@SpringJUnitConfig`:

```java
@SpringJUnitConfig(classes = OrderTestConfiguration.class)
class OrderServiceTests {

    @Autowired
    private OrderService orderService;

    @Nested
    class CreateOrder {

        @Autowired
        private OrderRepository orderRepository;

        @Test
        void createsAnOrder() {
            // Use orderService and orderRepository.
        }
    }
}
```

In this example, `@SpringJUnitConfig` registers `SpringExtension` and specifies the context configuration. Spring injects `OrderService` into the outer class instance and `OrderRepository` into the nested class instance. When the nested class inherits configuration from the outer class, both dependencies are resolved from the same `ApplicationContext`.

`SpringExtension` implements JUnit Jupiter's `TestInstancePostProcessor` callback. During test instance post-processing, the extension invokes Spring TestContext to prepare the instance. `DependencyInjectionTestExecutionListener` injects appropriately annotated fields and setters. This process applies to the nested class's test instance whenever `SpringExtension` is registered for that test.

Consequently, `@Autowired` fields declared in the nested class are injected before `@BeforeEach` callbacks and test methods on that instance execute.

## 3. Spring configuration is inherited from the enclosing class

When a test class uses `@Nested`, Spring must determine which configuration annotations on the enclosing class apply to the nested class. Since Spring Framework 5.3, the TestContext Framework supports this inheritance mechanism via `@NestedTestConfiguration`.

The default mode is `EnclosingConfiguration.INHERIT`. The nested class inherits Spring configuration from its enclosing test class:

```java
@SpringJUnitConfig(classes = SharedOrderTestConfiguration.class)
class OrderServiceTests {

    @Nested
    class CreateOrder {
        // Uses context from SharedOrderTestConfiguration.
    }

    @Nested
    class CancelOrder {
        // Also uses the inherited Spring configuration.
    }
}
```

If no additional Spring configuration is declared in the nested classes, child classes share the same context metadata. When a matching entry is in the cache, Spring Test can reuse the same `ApplicationContext`.

Spring Test annotations that can be inherited under this mechanism include context configuration annotations such as `@ContextConfiguration`, `@ContextHierarchy`, `@WebAppConfiguration`, `@TestPropertySource`, `@ActiveProfiles`, and certain test execution annotations such as `@Transactional` or `@Sql`. Exact scope depends on the annotation and Spring version in use.

### 3.1. Adding dedicated configuration to a nested class

By default, a nested class can add its own Spring configuration. With `@ContextConfiguration`, classes or resources declared on the nested class are merged with inherited configuration according to that annotation's inheritance rules:

```java
@SpringJUnitConfig(classes = SharedOrderTestConfiguration.class)
class OrderServiceTests {

    @Nested
    @ContextConfiguration(classes = AuditTestConfiguration.class)
    class AuditedOrderTests {
        // Context has both shared configuration and additional audit configuration.
    }
}
```

Beans from both configurations must be compatible with each other. If both declare beans of the same type or name, resolve them with qualifiers, `@Primary`, or appropriate bean organization.

### 3.2. Disabling inheritance with OVERRIDE

When a nested test needs configuration independent from its enclosing class, you can use:

```java
@Nested
@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
class IsolatedNestedTests {
    // Declare dedicated Spring configuration for this test group.
}
```

In `OVERRIDE` mode, Spring Test does not inherit test context annotations from the enclosing class. The nested class must declare the configuration annotations it needs. Inheritance from a test class's superclass remains a separate mechanism.

You can place `@NestedTestConfiguration` on a test class or use a meta-annotation to establish a shared convention. Projects can also place this annotation in `package-info.java` to change the default for tests in that package.

### 3.3. Changing the default via system property

Spring Test allows changing the default inheritance mode via a system property:

```text
spring.test.enclosing.configuration=override
```

The value `inherit` retains the default inheritance behavior. Package- or class-level configuration can clarify rules at a narrower scope. When using a global setting, make sure nested test groups declare all required context configuration.

## 4. Complete example: sharing beans across outer and nested classes

Suppose a service depends on a repository:

```java
public interface OrderRepository {
    Optional<Order> findById(long id);
}

public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Order find(long id) {
        return repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Order not found"));
    }
}
```

Java configuration for tests:

```java
@Configuration
class OrderTestConfiguration {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    OrderService orderService(OrderRepository orderRepository) {
        return new OrderService(orderRepository);
    }
}
```

The test class can inject the service in the outer class and the repository in the nested class:

```java
@SpringJUnitConfig(classes = OrderTestConfiguration.class)
class OrderServiceNestedTests {

    @Autowired
    private OrderService orderService;

    @Nested
    class FindOrder {

        @Autowired
        private OrderRepository orderRepository;

        @Test
        void serviceIsInjectedIntoEnclosingTestInstance() {
            assertThat(orderService).isNotNull();
        }

        @Test
        void repositoryIsInjectedIntoNestedTestInstance() {
            assertThat(orderRepository).isNotNull();
        }

        @Test
        void nestedTestCanUseTheSharedServiceBean() {
            assertThat(orderService.find(42L)).isNotNull();
        }
    }
}
```

`OrderService` and `OrderRepository` are created as beans in the context. Each test instance receives references to beans via Spring's injection mechanism. If beans use the default singleton scope, different test instances can reference the same bean instance; creating a new test instance does not imply creating a new context or new singleton beans.

The example assumes `InMemoryOrderRepository` contains test data for order ID 42. In a real project, you can use a fake repository, persistence test configuration, or mock bean depending on the test goal.

## 5. Field and setter dependency injection

Field injection is common in Spring tests:

```java
@Nested
class UpdateOrder {

    @Autowired
    private OrderService orderService;

    @Test
    void updatesOrder() {
        assertThat(orderService).isNotNull();
    }
}
```

Setter injection is also supported:

```java
@Nested
class DeleteOrder {

    private OrderService orderService;

    @Autowired
    void setOrderService(OrderService orderService) {
        this.orderService = orderService;
    }

    @Test
    void deletesOrder() {
        assertThat(orderService).isNotNull();
    }
}
```

Field injection fits small test fixtures because it requires minimal setup code. Setter injection can be useful when you want to perform additional preparation after the dependency is supplied. Both are processed by Spring during the test instance preparation step.

Do not manually call setters or instantiate beans in `@BeforeEach` just to replace injection already managed by Spring. Let one clear mechanism be responsible for supplying test dependencies.

## 6. Injecting dependencies via test method parameters

`SpringExtension` also supports resolving parameters for test methods and compatible lifecycle methods. You can place `@Autowired` on parameters:

```java
@SpringJUnitConfig(classes = OrderTestConfiguration.class)
class OrderServiceNestedTests {

    @Nested
    class FindOrder {

        @Test
        void findsOrder(@Autowired OrderService orderService) {
            assertThat(orderService).isNotNull();
        }
    }
}
```

This is useful when a dependency is only needed in one method. It can also be used in `@BeforeEach`:

```java
@Nested
class FindOrder {

    private OrderService orderService;

    @BeforeEach
    void setUp(@Autowired OrderService service) {
        this.orderService = service;
    }

    @Test
    void findsOrder() {
        assertThat(orderService).isNotNull();
    }
}
```

Parameters resolved by `SpringExtension` must be distinguishable from parameters managed by JUnit or other extensions. If a test class registers multiple extensions that could handle the same parameter, use appropriate qualifier annotations or explicit resolver configuration to avoid conflicts.

## 7. Constructor injection in nested test classes

Spring Test supports constructor injection for test classes via `@TestConstructor` or a constructor annotated with `@Autowired`. You can choose the mode that automatically injects all constructor parameters:

```java
@SpringJUnitConfig(classes = OrderTestConfiguration.class)
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class OrderServiceConstructorTests {

    private final OrderService orderService;

    OrderServiceConstructorTests(OrderService orderService) {
        this.orderService = orderService;
    }
}
```

For nested test classes, JUnit must also pass the enclosing instance according to non-static member class rules. Therefore, field injection or method parameter injection is often easier to read and less error-prone when a nested class only needs a few beans. If using constructor injection, ensure constructor parameters are supported by `SpringExtension` and do not conflict with how JUnit instantiates nested instances.

The default constructor autowire mode can be controlled by `@TestConstructor` or the `spring.test.constructor.autowire.mode` property depending on the Spring version. Do not enable the global mode if only one group of tests needs constructor injection.

## 8. Lifecycle of outer and nested classes

With JUnit Jupiter, lifecycle callbacks of the enclosing class participate in running nested tests. For example, `@BeforeEach` in the outer class runs before `@BeforeEach` in the nested class for each nested test invocation. `@AfterEach` callbacks run in reverse order.

```java
@SpringJUnitConfig(classes = OrderTestConfiguration.class)
class OrderServiceNestedTests {

    @Autowired
    OrderService orderService;

    @BeforeEach
    void prepareOuterTest() {
        // Outer class dependencies have already been injected.
    }

    @Nested
    class FindOrder {

        @Autowired
        OrderRepository orderRepository;

        @BeforeEach
        void prepareNestedTest() {
            // Nested class dependencies have already been injected.
        }

        @Test
        void findsOrder() {
            assertThat(orderService).isNotNull();
            assertThat(orderRepository).isNotNull();
        }
    }
}
```

Dependency injection happens during test instance post-processing, prior to setup callbacks of that test instance. Thus `@BeforeEach` methods can safely use injected fields.

By default, JUnit uses `PER_METHOD`. If switched to `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`, test instances are reused within their corresponding class scope. This affects instance field state and `@BeforeAll` usage, but does not change how Spring injects dependencies into test instances. Avoid letting mutable state from one nested test affect another.

A nested class can use a non-static `@BeforeAll` when its lifecycle is `PER_CLASS`. Without changing the lifecycle, `@BeforeAll` must still follow JUnit Jupiter's `static` rules.

## 9. Context is shared, test instances are separate

There are two lifecycles to understand:

| Component | Typical lifecycle |
|---|---|
| Test instance | Created by JUnit per `PER_METHOD` or `PER_CLASS` lifecycle. |
| Nested test instance | Created per nested test and tied to an enclosing instance. |
| Spring `ApplicationContext` | Cached by the TestContext Framework based on merged configuration. |
| Singleton bean | Typically lives for the duration of the context and is referenced by multiple test instances. |

For example, two nested classes can both receive an `OrderService` bean from the same context. Each nested class has its own field holding a reference to that bean, yet the singleton bean pointed to by both fields may be the same object.

This matters when beans hold mutable state. If one test modifies shared singleton state, subsequent tests may observe that change. Clean up data or reset state with appropriate fixtures; only use `@DirtiesContext` when the context genuinely cannot be safely reused.

## 10. Organizing nested tests by business context

A common pattern is placing shared dependencies on the outer class while nested classes focus on each group of behaviors:

```java
@SpringJUnitConfig(classes = OrderTestConfiguration.class)
class OrderServiceTests {

    @Autowired
    OrderService orderService;

    @Nested
    class Create {

        @Test
        void createsOrder() {
            // Test valid order creation.
        }

        @Test
        void rejectsInvalidQuantity() {
            // Test invalid input data.
        }
    }

    @Nested
    class Find {

        @Test
        void returnsExistingOrder() {
            // Test finding an existing order.
        }

        @Test
        void reportsMissingOrder() {
            // Test missing order case.
        }
    }

    @Nested
    class Cancel {

        @Test
        void cancelsPendingOrder() {
            // Test canceling a pending order.
        }
    }
}
```

If a dependency is only needed for one group of behaviors, you can inject it directly inside that nested class. This makes the dependency's usage scope explicit and keeps the outer class from accumulating fields used by only one test branch.

If all nested classes need the same service, injecting it on the outer class can reduce repetition. Both approaches are valid; choose based on actual sharing and test readability.

## 11. Combining nested tests with dedicated configuration

Some test groups may need specific profiles or properties. Because configuration annotations are inherited by default, declare only the differences on the nested class:

```java
@SpringJUnitConfig(classes = PaymentTestConfiguration.class)
@ActiveProfiles("test")
class PaymentServiceTests {

    @Nested
    @TestPropertySource(properties = "payment.mode=offline")
    class OfflinePayment {
        // Adds property for the offline test group.
    }

    @Nested
    @TestPropertySource(properties = "payment.mode=online")
    class OnlinePayment {
        // Adds property for the online test group.
    }
}
```

Different properties produce different context metadata, so the two nested groups may require two separate contexts. Do not expect them to share a context merely because they sit inside the same outer test class.

If you want a nested group not to inherit outer configuration, use `@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)` and declare all required configuration explicitly. Changing the inheritance policy should be deliberate because it affects both context annotations and related Spring Test annotations.

## 12. Interaction with @TestExecutionListeners

Spring Test uses `TestExecutionListener` implementations to perform work across the test lifecycle, including injecting dependencies. The default `DependencyInjectionTestExecutionListener` handles injecting dependencies declared in test classes.

If you customize the listener list with `@TestExecutionListeners`, pay attention to inheritance mode and default listeners. Replacing the listener list improperly can drop the dependency injection listener, causing `@Autowired` fields in the outer or nested class to remain unassigned.

When you only want to add a custom listener, use the merge attribute appropriate for your Spring version instead of accidentally replacing all default listeners. If dependency injection fails in a nested class, check both that `SpringExtension` is registered and that the injection listener remains active in the TestContext configuration.

## 13. Common mistakes

### Missing SpringExtension

`@Nested` only structures tests in JUnit Jupiter. It does not automatically enable Spring dependency injection. If tests need `@Autowired`, you must register `SpringExtension` via `@ExtendWith(SpringExtension.class)` or `@SpringJUnitConfig`.

### Expecting Spring to inject fields when the nested class is not part of a Spring test

If a nested class sits inside a test class that has not registered `SpringExtension` or lacks appropriate context metadata, `@Autowired` fields are not processed. Check extension registration and context configuration before debugging beans.

### Using Spring prior to 5.3 while expecting nested configuration inheritance

`@NestedTestConfiguration` was introduced in Spring Framework 5.3. In older versions, you must declare Spring configuration explicitly for nested tests in the manner supported by that version; do not assume configuration from the enclosing class is automatically inherited.

### Unintended configuration inheritance

If a nested class needs an isolated context while still in `INHERIT` mode, configuration annotations from the outer class may be merged in. Use `OVERRIDE` when you want to stop inheriting Spring configuration from the enclosing class.

### Confusing test instances with bean instances

A new test instance does not mean Spring creates a new singleton bean. Multiple test instances can reference the same bean in the context cache. Manage shared state carefully.

### Nested class needs a dependency but the field is placed in the wrong scope

A private field on the outer class does not automatically become a field of the nested class. A nested class can access members of its enclosing instance per Java rules, but if a dependency is needed directly in the nested test, declaring field injection right in the nested class makes the intent clearer.

### Constructor injection conflicts with nested instance creation

A nested class has an enclosing instance supplied by JUnit per JUnit Jupiter rules. When constructor injection does not resolve as expected, check `@TestConstructor` and parameter resolvers. For simple nested tests, field or method parameter injection is usually easier to configure.

### @TestExecutionListeners dropping the injection listener

If the listener list is replaced without keeping required default listeners, dependency injection can stop working. Check listener configuration and merge mode when customizing listeners.

### Using @DirtiesContext to fix every state error

`@DirtiesContext` evicts the context from the cache and forces tests to re-initialize the context. If you only need to reset data or a collaborator's state, clean up state within that scope to avoid unnecessarily rebuilding the entire context.

## 14. Choosing the right dependency injection approach

| Need | Approach |
|---|---|
| Multiple nested classes share a service | Inject the service in the outer class if every test group needs it. |
| Only one nested class needs a repository | Place an `@Autowired` field right inside that nested class. |
| Dependency needed in only one test method | Use a method parameter with `@Autowired`. |
| Want constructor injection for tests | Use `@TestConstructor` or an `@Autowired` constructor, keeping nested enclosing instances in mind. |
| Nested class needs additional beans/config | Use `@ContextConfiguration` to add configuration per merge rules. |
| Nested class needs a dedicated context | Use `@NestedTestConfiguration(OVERRIDE)` and declare independent configuration. |
| Need the same context for multiple nested groups | Keep configuration metadata equivalent so the TestContext cache can reuse it. |

When writing nested tests with Spring, let JUnit manage the structure and lifecycle of nested classes while letting `SpringExtension` prepare each test instance. Use inherited configuration when test groups truly share the same environment; inject dependencies at the right usage scope so tests remain readable and easy to maintain.
