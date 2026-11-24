# Avoiding Parallel Execution When Using @DirtiesContext or Unsafe Shared Mocks

JUnit Jupiter can run multiple test methods or test classes concurrently. Parallel execution reduces suite duration, but some Spring integration tests share stateful resources: cached `ApplicationContext` instances, singleton beans, mock beans, mock HTTP servers, or asynchronous tasks. If one test mutates or closes a resource while another test is still using it, outcomes can depend on execution timing.

Special caution is required with `@DirtiesContext` and mocks registered inside the Spring `ApplicationContext`. Both can affect other tests sharing the same context. This article explains the origins of these race conditions and how to restrict parallelism using JUnit Jupiter.

## 1. Why can Spring tests share state?

The Spring TestContext Framework caches `ApplicationContext` instances to avoid re-initializing contexts for every test class. Tests with the same context configuration can receive the same context instance. Because beans are singletons by default, those tests can also access the same bean instances.

Example of two test classes sharing configuration:

```java
@SpringBootTest
class OrderControllerTests {
    // Uses ApplicationContext with this configuration.
}

@SpringBootTest
class InventoryControllerTests {
    // If context configuration is equivalent, may reuse the same cached context.
}
```

Sharing a context is generally safe when tests only read configuration and each request uses isolated data. Risk arises when a test mutates a singleton bean, resets a mock, edits mutable configuration, or closes the context while another test is still active.

JUnit Jupiter does not run in parallel by default unless parallel execution is configured. However, a project may enable this mode in `junit-platform.properties`, Maven/Gradle, or test runtime settings. Confirm whether the test suite actually runs in parallel before diagnosing a race condition.

## 2. What does @DirtiesContext do?

`@DirtiesContext` marks an `ApplicationContext` as no longer suitable for reuse. Spring TestContext closes the context and evicts it from the context cache at the specified point. The next test needing a context with the same configuration must create a new one.

The annotation can be applied at the method level:

```java
@Test
@DirtiesContext
void changesSingletonConfiguration() {
    // Changes context state that other tests should not inherit.
}
```

Or at the class level:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextMutationTests {
    // After all tests in the class finish, context is closed and evicted from cache.
}
```

Modes depend on where the annotation is placed:

| Attribute | Mode | When the context is marked dirty |
|---|---|---|
| `methodMode` (annotation on method) | `BEFORE_METHOD` | Before that test method |
| `methodMode` (annotation on method) | `AFTER_METHOD` | After that test method; this is the method-level default |
| `classMode` (annotation on class) | `BEFORE_CLASS` | Before the test methods in the class |
| `classMode` (annotation on class) | `AFTER_CLASS` | After the test methods in the class complete; this is the class-level default |
| `classMode` (annotation on class) | `BEFORE_EACH_TEST_METHOD` | Before each test method in the class |
| `classMode` (annotation on class) | `AFTER_EACH_TEST_METHOD` | After each test method in the class |

Choose the mode according to when context state is altered and when the context must be discarded. Marking dirty before a method/class makes Spring create a fresh context for that run; after-method/class modes close the current context once the designated test scope finishes.

### Race condition when the context is closed

Suppose two test classes share a cached context:

```text
Test A                              Test B
------                              ------
using ApplicationContext            using the same context
@DirtiesContext runs after Test A
Spring closes context
                                    continues calling bean
                                    bean/context is already closed
                                    test may fail
```

When Test A finishes and marks the context dirty, Spring can close the context that Test B is still using. Test B may hit errors from destroyed beans, closed connection pools, or an inactive context. This is why `@DirtiesContext` must be treated as an operation affecting all tests sharing that context.

`@DirtiesContext` is not a general reset mechanism for every test. Each context closure forces the suite to re-initialize many beans and infrastructure components, slowing down tests. Use it only when a test genuinely alters configuration or singleton state that cannot be safely restored otherwise.

## 3. Why can shared mocks cause race conditions?

Mocks typically hold state: stubbing, invocation history, verification, and resets. If multiple tests use the same mock instance, these operations can interleave.

Example of a Spring context containing a mock bean:

```java
@SpringBootTest
class OrderServiceTests {

    @MockitoBean
    private InventoryGateway inventoryGateway;

    @Autowired
    private OrderService orderService;

    @Test
    void returnsAvailableInventory() {
        when(inventoryGateway.available("SKU-1")).thenReturn(10);
        assertThat(orderService.available("SKU-1")).isEqualTo(10);
    }
}
```

`@MockitoBean` registers a mock in the `ApplicationContext`. If two test classes share a context and the same mock bean, they can access the same mock instance concurrently. Suppose Test A configures a result for `SKU-1`, while Test B configures a different result or resets the mock while Test A is running. The outcome depends on how the operations interleave.

With `@MockitoBean`, the mock is reset after each test method by default. Resetting prevents sequential tests from inheriting each other's invocations or stubbing, but if test methods run concurrently on the same mock, one test can wipe state that another test currently relies on.

Spring Boot mock annotations such as `@MockBean` suffer from the same issue when mocks live in a shared context. In Spring Framework 6.2 you can use `@MockitoBean`; older Spring Boot projects may still use `@MockBean`.

### Mock resources requiring attention

| Resource | Shared state that can conflict |
|---|---|
| `@MockitoBean` / `@MockBean` | Tests mutate stubbing, verify, or reset on the same mock |
| `MockRestServiceServer` | Concurrent requests contend over declared expectations and responses |
| Fake repository or in-memory store | Tests write/delete data in the same collection |
| Mutable singleton bean | Tests mutate shared fields or configuration |
| Static test fixture | Tests modify static variables or global caches |

Not every mock is unsafe when called concurrently by multiple threads. The primary risk is multiple tests simultaneously altering the configuration and observable state of the same mock or fixture without synchronization. Distinguish between the application calling a mock concurrently as intended behavior versus multiple tests concurrently editing the mock's stubbing or resetting it.

## 4. Example of two tests mutating the same mock bean

Suppose two tests share one context and the same `InventoryGateway` mock:

```java
@SpringBootTest
class InventoryTests {

    @MockitoBean
    InventoryGateway inventoryGateway;

    @Autowired
    InventoryService inventoryService;

    @Test
    void reportsTenItems() {
        when(inventoryGateway.available("SKU-1")).thenReturn(10);
        assertThat(inventoryService.available("SKU-1")).isEqualTo(10);
    }

    @Test
    void reportsTwentyItems() {
        when(inventoryGateway.available("SKU-1")).thenReturn(20);
        assertThat(inventoryService.available("SKU-1")).isEqualTo(20);
    }
}
```

When run sequentially, each test sets up stubbing and completes before the next test starts. When run concurrently on the same mock, the sequence can become:

```text
Test A: stub SKU-1 -> 10
Test B: stub SKU-1 -> 20
Test A: calls service -> may receive 20
Test B: calls service -> receives current result
```

Even if individual Mockito calls are thread-safe, the two tests are still contending over the same logical state. Resetting the mock after one method can also erase stubbing or invocation history that the other method is using.

## 5. The safest approach: isolate state per test

Prefer giving each test its own data and mocks. For unit tests that do not need a Spring context, create the service and mock inside each method:

```java
@Test
void returnsTenItems() {
    InventoryGateway gateway = mock(InventoryGateway.class);
    when(gateway.available("SKU-1")).thenReturn(10);

    InventoryService service = new InventoryService(gateway);

    assertThat(service.available("SKU-1")).isEqualTo(10);
}
```

Each test gets a fresh mock, so stubbing, verification, and resets cannot affect other tests. When testing Spring wiring, use a test context but avoid mutating singleton mocks from multiple concurrently running tests.

With `MockRestServiceServer`, create a dedicated `RestTemplate` and mock server per test instead of sharing an expectation manager across tests:

```java
@Test
void readsOrder() {
    RestTemplate restTemplate = new RestTemplate();
    MockRestServiceServer server = MockRestServiceServer
            .bindTo(restTemplate)
            .build();

    InventoryClient client = new InventoryClient(restTemplate);
    server.expect(requestTo("https://inventory.example.test/orders/42"))
            .andRespond(withSuccess(
                    "{\"id\":\"42\"}", MediaType.APPLICATION_JSON));

    assertThat(client.findOrder("42").id()).isEqualTo("42");
    server.verify();
}
```

Here each test creates its own request factory and expectation manager. Another test cannot consume this test's expectations.

## 6. Restricting parallelism with JUnit Jupiter

JUnit Jupiter provides several mechanisms to control concurrent execution. Choose the mechanism matching the scope of the resource needing protection.

### 6.1. Disabling parallel execution across the entire suite

If a suite has many tests sharing contexts or mocks and they cannot yet be isolated, you can disable parallel execution in `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled = false
```

This is a simple, predictable choice for suites with many integration tests depending on shared state. In return, suite runtime may be longer. Re-enable parallelism only after tests are designed to be independent or have proper locking mechanisms.

### 6.2. Running tests within the same class sequentially

Use `@Execution(ExecutionMode.SAME_THREAD)` to require test nodes in a class to run on the same thread in execution-tree order:

```java
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

@SpringBootTest
@Execution(ExecutionMode.SAME_THREAD)
class SharedMockTests {
    // Tests in this class do not run concurrently with each other.
}
```

Note: `SAME_THREAD` on one class does not automatically lock tests in other classes. If another class uses the same mock bean or context, the two classes can still run concurrently under class-level settings. When resources are shared across multiple classes, use a shared `@ResourceLock` or broader isolation.

### 6.3. Using @ResourceLock for specific resources

`@ResourceLock` lets tests declare a named logical resource. Tests using the same lock name will not execute concurrently within a JUnit Jupiter execution:

```java
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;

@SpringBootTest
@ResourceLock(value = "shared-inventory-mock",
        mode = ResourceAccessMode.READ_WRITE)
class InventoryMockTests {

    @MockitoBean
    InventoryGateway inventoryGateway;

    // Tests accessing shared mock go here.
}
```

Every other test method or class accessing that mock must also declare the exact same resource name and compatible mode. If one test forgets to declare the lock, JUnit cannot automatically tell it uses the same resource.

Use `READ_WRITE` when tests may alter stubbing, reset, or invocation state. `READ` is only suitable when all involved tests strictly read a stable resource and no test writes during that period.

`@ResourceLock` fits when only a subset of tests needs serialization while the rest of the suite can still run in parallel. JUnit locks do not coordinate across separate JVM processes or independent build forks.

### 6.4. Using @Isolated for test classes needing exclusivity

When a class performs operations with broad impact on the context or hard-to-enumerate resources, `@Isolated` instructs that class to run separately from other tests in the same JUnit Jupiter execution:

```java
import org.junit.jupiter.api.parallel.Isolated;

@SpringBootTest
@Isolated
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class LegacyContextMutationTests {
    // Test modifies singleton configuration and needs to close context after class.
}
```

`@Isolated` is useful for test classes using `@DirtiesContext` when ensuring no other Jupiter test runs concurrently with that class. It reduces parallelism while the class runs. This annotation has been available since JUnit Jupiter 5.7; check the project's JUnit version before using it.

## 7. Choosing a strategy by sharing scope

| Scenario | Suitable handling |
|---|---|
| Two methods in the same class mutate the same mock | Create dedicated mocks or use `@Execution(SAME_THREAD)` |
| Multiple classes share a mock bean in the context cache | Use `@ResourceLock` with the same name on all involved classes or isolate contexts |
| A class using `@DirtiesContext` might close a context used by other classes | Use `@Isolated` or a shared lock across all tests using that context |
| Multiple tests share `MockRestServiceServer` | Create dedicated server/RestTemplate or lock the shared expectation manager |
| Multiple tests can work independently | Allow parallel execution |
| Shared resources are not yet identified and the suite is frequently flaky | Temporarily disable parallel execution to stabilize, then isolate group by group |

Do not add `@DirtiesContext` just to patch a flaky test caused by overwritten mocks. Doing so can close the context while other tests are running and worsen the issue. Identify the truly shared resource before choosing how to lock or isolate.

## 8. Asynchronous work must also finish before the test ends

A test method might finish while asynchronous work it launched is still running. For example, `@Async`, executors, schedulers, or reactive subscriptions may continue accessing beans after the test completes. If the next test resets a mock or `@DirtiesContext` closes the context, the leftover task might observe new state or destroyed beans.

With `CompletableFuture`, wait for the result in the test:

```java
CompletableFuture<Result> future = service.startAsyncWork();
Result result = future.get(5, TimeUnit.SECONDS);

assertThat(result.status()).isEqualTo("DONE");
```

With Reactor, use `StepVerifier` to confirm the publisher completes or explicitly cancel the stream:

```java
StepVerifier.create(service.process())
        .expectNextMatches(result -> result.isSuccessful())
        .verifyComplete();
```

Do not let background tasks hold references to test singleton beans or mocks after the method ends. If a test creates its own executor, shut it down in `@AfterEach` or `try/finally` and wait for tasks to finish within a time bound.

## 9. @DirtiesContext does not replace data cleanup

`@DirtiesContext` closes and evicts the context from the cache; it is not a rollback mechanism for all data outside the context. Databases, files, message brokers, static state, or shared servers may still retain data after the context closes.

For those resources, clean up at the appropriate scope:

- Use transaction rollback for database data when tests run inside suitable transactions.
- Delete test-specific records or namespaces when operations fall outside rolled-back transactions.
- Create per-test topics, queues, buckets, or directories when possible.
- Close clients, executors, and subscriptions created by the test.
- Do not share a static mutable fixture across parallel tests without synchronization.

A fresh context does not mean external systems have returned to their initial state.

## 10. Example of controlled parallel configuration

You can enable parallelism for the suite and lock only the test groups sharing resources. Example `junit-platform.properties` file:

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
junit.jupiter.execution.parallel.mode.classes.default = concurrent
junit.jupiter.execution.parallel.config.strategy = dynamic
```

Test classes sharing a mock bean declare the same lock:

```java
@SpringBootTest
@ResourceLock(value = "shared-payment-gateway",
        mode = ResourceAccessMode.READ_WRITE)
class PaymentGatewayIntegrationTests {
    // Shares resource lock with every other class accessing this mock.
}
```

A class mutating the context and needing to close it afterward:

```java
@SpringBootTest
@Isolated
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class PaymentConfigurationMutationTests {
    // Does not run concurrently with other Jupiter tests.
}
```

There is no need to lock tests that do not share resources. The goal is to preserve parallelism where tests are independent and serialize specifically where shared state exists.

## 11. Signs of a race condition

Common indicators:

- A test always passes in isolation but fails occasionally when running the full suite.
- Mock return values do not match the stubbing in the current test.
- Invocation counts vary across runs.
- Tests report closed contexts or destroyed beans while requests are still processing.
- An expectation on `MockRestServiceServer` is consumed prematurely by another test.
- Failures vanish when parallel execution is disabled or when re-running the failed test alone.

To investigate, record the test class/method names, start/end timestamps, context identity if needed, and shared mock resources. Re-running with parallelism disabled helps determine whether the failure is contention-related, though it is not the final fix if the suite still needs to run in parallel.

## 12. Common mistakes

| Symptom | Common cause | How to handle |
|---|---|---|
| Other tests fail after one test uses `@DirtiesContext` | Context cache entry was closed while other tests were still using it | Serialize related tests with `@Isolated` or a shared `@ResourceLock` |
| Mock returns random wrong data | Multiple tests stub the same singleton mock bean | Create separate mocks or lock all tests using that mock |
| Stubbing disappears mid-test | Mock was reset after a concurrently running test method | Avoid sharing mutable mocks; serialize related tests |
| `MockRestServiceServer` reports unmatched request | Request from another test used the same expectation manager | Create dedicated servers per test or use a resource lock |
| `@Execution(SAME_THREAD)` still fails to prevent races across classes | Annotation only controls that class's execution tree | Use a shared lock or `@Isolated` when excluding other classes is required |
| Fresh context yet test data remains | Data lives in a database, file, or system outside the context | Clean up out-of-context resources separately |
| Test finishes while async task keeps running | Background work was not awaited or cancelled | Await futures, verify/cancel publishers, and shut down executors |

## 13. Takeaways

Spring TestContext can cache and share `ApplicationContext` instances across tests. `@DirtiesContext` closes the context at the configured point, so it can break other tests using the same context if they run concurrently. Mock beans and mock servers also hold shared state; stubbing, resetting, or consuming expectations from multiple tests can yield nondeterministic results. Prefer isolating mocks and data per test. When sharing is necessary, use `@ResourceLock` for related test groups, `@Execution(SAME_THREAD)` for nodes within the same class, or `@Isolated` for classes requiring exclusivity. Disable parallel execution across the suite until shared resources are under control, and always finish asynchronous tasks before a test ends.

