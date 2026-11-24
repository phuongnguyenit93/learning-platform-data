# PER_CLASS, Test Instances, and Context Re-initialization

Both JUnit Jupiter and the Spring TestContext Framework have a concept of lifecycle, but they manage two different kinds of objects. JUnit decides how many test instances are created for a test class; Spring manages the lifecycle of the `ApplicationContext`, which holds the beans injected into tests.

`@TestInstance(PER_CLASS)` tells JUnit to use a single instance for all test methods in a class. Meanwhile, Spring can reuse or re-initialize the `ApplicationContext` independently of this choice. Understanding both lifecycles avoids confusion about shared state, dependency injection, `@BeforeAll`, and the effects of `@DirtiesContext`.

## 1. What is a test instance?

A test instance is the object created by JUnit from the test class to hold the fields, constructor, and lifecycle methods of the test.

Example:

```java
class AccountServiceTest {

    private String accountId;

    @BeforeEach
    void setUp() {
        accountId = "ACC-01";
    }

    @Test
    void loadsAccount() {
        // Use accountId
    }
}
```

JUnit creates an `AccountServiceTest` object, then invokes lifecycle methods and test methods according to the configured lifecycle. The `accountId` field belongs to this test object, not to the Spring `ApplicationContext`.

JUnit Jupiter supports two main lifecycles:

- `PER_METHOD`: creates a new test instance for each test method. This is the default.
- `PER_CLASS`: creates one test instance for the entire test class and reuses it across test methods in the class.

You can visualize this as:

```text
PER_METHOD
Test class
   |
   +--> Instance A --> testOne()
   |
   +--> Instance B --> testTwo()
   |
   +--> Instance C --> testThree()


PER_CLASS
Test class
   |
   +--> Instance A
           |
           +--> testOne()
           +--> testTwo()
           +--> testThree()
```

The key difference is that instance fields of the test class are preserved between methods when using `PER_CLASS`. Consequently, state mutated by one test method can be observed by the next test method.

## 2. Default PER_METHOD lifecycle

If `@TestInstance` is not declared, JUnit Jupiter uses `PER_METHOD`.

```java
class CounterTest {

    private int counter;

    @BeforeEach
    void setUp() {
        counter = 0;
    }

    @Test
    void incrementsCounter() {
        counter++;
        assertEquals(1, counter);
    }

    @Test
    void startsAtZero() {
        assertEquals(0, counter);
    }
}
```

Each test method runs on a fresh test instance. Therefore, the `counter` field of the first method is not shared with the instance of the second method. `@BeforeEach` still runs before each method and prepares state for its corresponding instance.

`PER_METHOD` makes tests less dependent on execution order because each method has its own test object. This is the right choice when tests need mutable fixtures stored in instance fields.

## 3. Declaring PER_CLASS

To use a single instance for the whole class, place `@TestInstance(TestInstance.Lifecycle.PER_CLASS)` on the test class:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class CounterTest {

    private int counter;

    @BeforeEach
    void setUp() {
        counter = 0;
    }

    @Test
    void incrementsCounter() {
        counter++;
        assertEquals(1, counter);
    }

    @Test
    void alsoStartsAtZero() {
        assertEquals(0, counter);
    }
}
```

Both test methods use the same `CounterTest` object. However, `@BeforeEach` resets `counter` to 0 before each method, so the test does not depend on the value left behind by the previous method.

If `setUp()` were removed, the value of `counter` would persist after a test method modifies it. A subsequent test could observe the modified value.

### Benefits of PER_CLASS

One obvious benefit is that `@BeforeAll` and `@AfterAll` can be instance methods instead of being required to be `static`:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class DatabaseScenarioTest {

    private TestDataset dataset;

    @BeforeAll
    void createSharedDataset() {
        dataset = new TestDataset();
        dataset.prepare();
    }

    @AfterAll
    void removeSharedDataset() {
        dataset.close();
    }

    @Test
    void readsFirstRecord() {
        // Use dataset
    }

    @Test
    void readsSecondRecord() {
        // Continue using dataset
    }
}
```

Because JUnit retains a single instance for the class, non-static lifecycle methods can access instance fields. This is useful when a class has a shared resource or fixture prepared once and used by its test methods.

However, shared resources need a clear cleanup strategy. If each test method mutates the dataset, restore its state before the next method or design independent scenarios.

## 4. PER_CLASS does not mean the Spring context has only one lifecycle

This is an important distinction to make:

| Concept | Managed object | Deciding component |
|---|---|---|
| Test instance lifecycle | Test class object | JUnit Jupiter |
| `ApplicationContext` lifecycle | Spring context and beans in the context | Spring TestContext Framework |
| Test method lifecycle | Pre/post steps per method | JUnit and extensions |
| Test transaction lifecycle | Transaction bound to the test method | Spring TestContext transaction support |

A test class using `PER_CLASS` only means JUnit reuses the test object. It does not require Spring to create a fresh context once per class, nor does it prevent Spring from reusing a context across test classes.

Conversely, two different test classes can have two separate test instances while sharing the same Spring `ApplicationContext` if their test configurations are equivalent and the context remains in the cache.

```text
JUnit test class A                 JUnit test class B
      |                                   |
      v                                   v
  Test instance A                     Test instance B
      |                                   |
      +----------------+------------------+
                       |
                       v
             Spring TestContext cache
                       |
                       v
             ApplicationContext C1
                       |
             +---------+---------+
             |                   |
          Bean X               Bean Y
```

The diagram shows that the test instance and the Spring context are two separate management layers. Creating a new test instance does not imply creating new beans in the context.

## 5. How does SpringExtension prepare a test instance?

When `SpringExtension` is registered, JUnit invokes extension callbacks at points in the test lifecycle. One key callback is `TestInstancePostProcessor`.

After JUnit creates the test instance, `SpringExtension` forwards the instance preparation event to the Spring TestContext Framework. Spring can then inject the dependencies declared on the test class:

```java
@SpringBootTest
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrder() {
        Order order = orderService.createOrder(
                new CreateOrderCommand("CUSTOMER-42")
        );

        assertNotNull(order.getId());
    }
}
```

With `PER_CLASS`, the `OrderServiceTest` instance is created once. Spring prepares that instance and injects `OrderService`. Test methods in the class use that same `orderService` field.

With `PER_METHOD`, JUnit creates a new instance for each method and Spring prepares each new instance according to the corresponding lifecycle.

This does not mean Spring creates a new `OrderService` each time it injects. If the context is reused, the singleton `OrderService` bean may still be the exact same object across multiple test instance preparations.

## 6. The two lifecycles operate independently

Consider two cases:

**Case A: new test instance, reused context.**

With `PER_METHOD`, JUnit creates a new test object for each method. If the tests share the same configuration and the Spring context remains in the cache, Spring can inject the same singleton bean from the reused context.

**Case B: reused test instance, re-initialized context.**

With `PER_CLASS`, JUnit keeps one test object for the entire class. If the context is marked dirty, Spring can close the old context and create a new one when the next test needs it. JUnit's test object remains the old object.

The following table summarizes this:

| Test instance | Spring context | Result |
|---|---|---|
| New per method | Reused | New test object, beans may be shared |
| One instance for the class | Reused | Both test object and context persist |
| New per method | Re-created | New test object receives dependencies from the current context |
| One instance for the class | Re-created | Test object stays the same; Spring dependencies need to be updated to the new context |

Therefore, when investigating a test failure caused by shared state, identify whether the state lives in the test instance or in a Spring bean. The two places have different reset mechanisms.

## 7. When is the Spring context re-initialized?

The Spring TestContext Framework caches `ApplicationContext` instances by test configuration. When a context remains valid and its configuration matches, Spring can reuse that context.

A context can be evicted from the cache and require re-creation in cases such as:

- A test uses `@DirtiesContext` to mark the context dirty.
- The context becomes invalid after a configuration or Spring-managed state change.
- The cache evicts the context under its capacity limit policy.
- A test class requires a different context configuration than existing cached contexts.

In everyday testing, `@DirtiesContext` is the common explicit way to tell Spring that the context has been mutated and should no longer be reused.

Example:

```java
@SpringBootTest
class FeatureRegistryTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void registersTemporaryFeature() {
        featureRegistry.enable("temporary");

        assertTrue(featureRegistry.isEnabled("temporary"));
    }
}
```

After the test method, Spring marks the context dirty, removes it from the cache, and closes it. When another test needs a context with the same configuration, Spring creates a fresh context.

## 8. Combining PER_CLASS with @DirtiesContext

When using `PER_CLASS`, the test instance is reused even though the Spring context may be re-initialized between methods. Therefore, you must pay attention to dependencies injected into the test instance.

Example:

```java
@SpringBootTest
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class FeatureRegistryTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void enablesTemporaryFeature() {
        featureRegistry.enable("temporary");

        assertTrue(featureRegistry.isEnabled("temporary"));
    }

    @Test
    void startsWithoutTemporaryFeature() {
        assertFalse(featureRegistry.isEnabled("temporary"));
    }
}
```

After the first method, the context is marked dirty. The test instance remains the same object because the lifecycle is `PER_CLASS`.

The Spring TestContext Framework coordinates between the listener that marks the context dirty and `DependencyInjectionTestExecutionListener`. When a context becomes dirty, Spring instructs the dependency injection listener to re-inject field- or setter-managed dependencies into the test instance before the next test method runs. As a result, the `featureRegistry` field can be updated to reference the bean from the new context.

This point is crucial: JUnit does not re-create the test instance in the situation above. Spring proactively re-prepares dependencies on the instance currently in use.

The reinjection mechanism applies to dependency injection managed by Spring TestContext. It does not reset arbitrary fields of the test class. For example, a field `int counter` mutated by the test itself retains its old value unless reset in `@BeforeEach`.

### Distinguishing Spring dependencies from test-owned state

| Component | When context is dirty | How to handle |
|---|---|---|
| Spring-injected `@Autowired` field | Spring TestContext can re-inject via reinjection mechanism | Uses dependency from the new context |
| Test data fields such as `counter`, `input` | Not automatically reset | Re-initialize in `@BeforeEach` |
| Static fields | Belong to neither test instance nor context | Restore state manually |
| Constructor-passed dependencies | `PER_CLASS` instance constructor does not re-run | Avoid holding constructor dependencies from a closed context if context may reload within the class |
| Singleton bean in old context | Old context is closed | Use bean from the new context after Spring re-prepares dependencies |

## 9. Caveats with constructor injection and PER_CLASS

Constructor injection supplies dependencies when JUnit creates the test instance. With `PER_CLASS`, the constructor is invoked only once for the class.

Example:

```java
@SpringBootTest
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class OrderServiceTest {

    private final OrderService orderService;

    OrderServiceTest(OrderService orderService) {
        this.orderService = orderService;
    }

    @Test
    void createsOrder() {
        // Use orderService
    }
}
```

If the Spring context is closed and recreated while the test instance is still reused, the `final` field `orderService` still references the object passed to the original constructor. Spring cannot re-invoke the constructor on the same object to replace that `final` field.

Therefore, when a class uses constructor injection and might dirty the context between methods, design the lifecycle so dependencies are not held past the old context's closure. Options include:

- Use `PER_METHOD` so each method gets a fresh test instance when the context has been refreshed after a previous method.
- Avoid dirtying the context between methods; if you only need to discard the context after the whole class, consider an appropriate class-level mode.
- Use field or setter injection managed by Spring TestContext if Spring needs to reinject dependencies into a `PER_CLASS` test instance.
- Use method parameter injection when a dependency is only needed in one method and should be retrieved from the context when the method runs.

Do not combine constructor injection, `PER_CLASS`, and mid-class context reloads without carefully checking whether dependencies still reference beans from a closed context.

## 10. @BeforeAll and dependency injection under PER_CLASS

With `PER_CLASS`, `@BeforeAll` can be an instance method. This enables using fields already prepared on the test instance:

```java
@SpringBootTest
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class CatalogServiceTest {

    @Autowired
    private CatalogService catalogService;

    private List<String> productIds;

    @BeforeAll
    void loadSharedProductIds() {
        productIds = catalogService.findFeaturedProductIds();
    }

    @Test
    void hasFeaturedProducts() {
        assertFalse(productIds.isEmpty());
    }

    @Test
    void firstProductIdIsAvailable() {
        assertNotNull(productIds.get(0));
    }
}
```

Here `catalogService` is injected by Spring into the test instance, while `productIds` is test data prepared once. Methods share this list.

Consider whether that data is immutable. If one test modifies `productIds`, another test can see the change. If each test needs an independent list, make a copy or re-prepare the data in `@BeforeEach`.

With `PER_METHOD`, `@BeforeAll` must normally be `static` because no shared class-level test instance is retained. If you need to access Spring dependencies during setup before all test methods, you can consider `PER_CLASS`, provided you manage instance state and dependencies according to the principles above.

## 11. PER_CLASS does not extend transactions across the whole class

Another misconception is assuming that sharing a test instance across a class also shares a transaction.

Spring TestContext transaction support typically manages transactions per test method. If a class or method is annotated with `@Transactional`, each test method usually runs in its own transaction and is rolled back after the method under the default configuration.

```java
@SpringBootTest
@Transactional
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class AccountRepositoryTest {

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void createsAccount() {
        accountRepository.save(new Account("ACC-01"));
        assertTrue(accountRepository.findById("ACC-01").isPresent());
    }

    @Test
    void doesNotSeePreviousUncommittedAccount() {
        assertFalse(accountRepository.findById("ACC-01").isPresent());
    }
}
```

The test instance is shared, yet the transaction does not become a single transaction for the entire class. Database state is managed per test method transaction. The example assumes no pre-existing `ACC-01` data and that each method runs under a standard test transaction.

Distinguish clearly:

- Instance fields of the test class persist under `PER_CLASS`.
- Test transactions are managed per test method lifecycle.
- Singleton beans persist for the lifecycle of the context.
- Contexts can be cached or refreshed independently.

If a test commits a transaction, executes asynchronous operations, or writes to non-transactional resources, dedicated cleanup is required. `PER_CLASS` neither cleans up data automatically nor extends transactions.

## 12. Mutable state and test execution order

With `PER_CLASS`, every test method accesses the same instance fields. If a test method mutates state without resetting it, results may depend on execution order.

Example prone to order dependency:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class ShoppingCartTest {

    private final List<String> items = new ArrayList<>();

    @Test
    void addsBook() {
        items.add("BOOK-01");
        assertEquals(1, items.size());
    }

    @Test
    void startsWithEmptyCart() {
        assertTrue(items.isEmpty());
    }
}
```

If `addsBook()` runs first, `startsWithEmptyCart()` fails because the list still contains data. In the reverse order, both might pass.

The improvement is to prepare state before each method:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class ShoppingCartTest {

    private List<String> items;

    @BeforeEach
    void setUp() {
        items = new ArrayList<>();
    }

    @Test
    void addsBook() {
        items.add("BOOK-01");
        assertEquals(1, items.size());
    }

    @Test
    void startsWithEmptyCart() {
        assertTrue(items.isEmpty());
    }
}
```

If shared state is genuinely the purpose of the test, name and organize the tests so readers understand that dependency. However, most tests should be independent so they can run individually, be re-run, or be reordered without changing results.

## 13. Parallel execution with PER_CLASS

A `PER_CLASS` test instance is shared by multiple methods. If JUnit is configured for parallel test execution, multiple methods may access the same fields or fixture concurrently.

This creates race condition risks when mutable state is unprotected:

```text
One PER_CLASS test instance
          |
          +------ testA() ----+
          |                   |
          +------ testB() ----+--> Mutate the same field
          |                   |
          +------ testC() ----+
```

If a class must run sequentially because of shared state, you can configure an appropriate execution mode, such as `@Execution(ExecutionMode.SAME_THREAD)`. However, a better approach is usually designing independent or immutable fixtures so state does not need synchronization across methods.

Do not use `PER_CLASS` solely to save creating a few test objects. That benefit is usually small compared to the cost of debugging shared-state or parallel-execution failures.

## 14. Configuring a default lifecycle for the whole test suite

Besides annotating individual test classes, JUnit Jupiter allows configuring a default lifecycle via `junit-platform.properties` on the test classpath:

```properties
junit.jupiter.testinstance.lifecycle.default = per_class
```

When this configuration is active, test classes that do not declare `@TestInstance` will use `PER_CLASS` as the default.

The file can be placed in the appropriate test resources location, typically:

```text
src/test/resources/junit-platform.properties
```

Changing the global default can affect test classes that rely on `PER_METHOD`, especially classes with mutable fields not reset in `@BeforeEach`. Review the entire test suite before changing the policy. For a specific group of tests needing `PER_CLASS`, annotating the class keeps the intent visible right at the point of use.

## 15. Common scenarios and troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Test method sees data created by a previous method | Using `PER_CLASS` with mutable fields not reset | Re-initialize in `@BeforeEach` |
| `@BeforeAll` fails because method is not static | Test uses default `PER_METHOD` lifecycle | Make the method `static` or declare `PER_CLASS` |
| Dependency field references a bean from an old context | Context became dirty, yet dependency was not updated by Spring TestContext | Check DI listener, injection style, and context reload timing |
| Constructor-injected bean does not change after context reload | `PER_CLASS` test instance does not re-run constructor | Avoid reloading context between methods or change dependency management |
| Two test classes share the same bean state | Spring context is reused from the cache | Reset beans, use independent fixtures, or mark context dirty when genuinely necessary |
| Test transaction mistakenly assumed shared across the class | Confusing test instance lifecycle with transaction lifecycle | Verify transactions per test method |
| Tests fail under parallel execution | Multiple methods concurrently access one test instance | Remove shared mutable state or adjust execution mode |
| Context restarts repeatedly | Context frequently marked dirty or configurations differ | Check `@DirtiesContext` and context configuration |

When investigating a failure, answer these in order: was a new test instance created; was the Spring context reused; is the dependency injected via field, setter, constructor, or method parameter; and does the mutated state belong to the test object, a bean, a transaction, or an external resource.

## 16. Choosing the right lifecycle

| Need | Choice |
|---|---|
| Each test needs its own instance state | `PER_METHOD` |
| Need instance methods for `@BeforeAll`/`@AfterAll` | `PER_CLASS` |
| Want to share an immutable fixture across methods | Can use `PER_CLASS` |
| Test has many independent mutable fields | Prefer `PER_METHOD` or explicit reset in `@BeforeEach` |
| Context may refresh between methods | Understand reinjection and avoid holding old constructor dependencies in `PER_CLASS` |
| Only want to share Spring beans | Let the Spring context cache manage it; no need for `PER_CLASS` just for this |
| Test methods may run in parallel | Avoid mutable state on shared test instances or configure sequential execution appropriately |

`PER_CLASS` fits when sharing a single test instance is intentional and state is clearly managed. `PER_METHOD` is generally easier to isolate because each method gets a fresh test object. Either way, the Spring context lifecycle is still managed independently through the TestContext Framework and its cache.

The key is not equating the test instance with the `ApplicationContext`. JUnit decides how test objects are created and reused; Spring decides how contexts are cached, closed, and re-initialized. Understanding these two lifecycles lets you accurately predict which dependencies persist, which state needs resetting, and how to keep tests safe when contexts change.

