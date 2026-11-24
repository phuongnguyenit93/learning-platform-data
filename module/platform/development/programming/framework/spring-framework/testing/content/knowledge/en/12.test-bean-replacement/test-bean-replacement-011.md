# Resetting Mocks and Safety Under Parallel Test Execution

In unit tests, a mock is usually created fresh for each test method, so invocation state and stub configuration are not shared long-term. In Spring integration tests, a mock can be registered to replace a bean in the `ApplicationContext`. Because Spring TestContext caches and reuses contexts, that mock bean can persist across multiple test methods or multiple test classes.

This creates two problems to manage: **mock state must be reset at the right time**, and **multiple tests must not concurrently mutate or use the same mock in conflicting ways**. If one test leaves behind stubs or invocations, the next test may receive stale results. If two tests run in parallel against the same mock bean, one test may reset the mock while the other is stubbing, invoking, or verifying it.

## 1. Why Do Mocks Need to Be Reset?

A Mockito mock stores at least two important groups of state:

- **Stubbing:** rules declared with `when(...).thenReturn(...)`, `doReturn(...).when(...)`, `thenThrow(...)`, or similar APIs.
- **Invocation history:** the list of calls that occurred, including methods, arguments, and details used for verification.

Example:

```java
when(orderRepository.findById(42L)).thenReturn(Optional.of(order));

service.findOrder(42L);

verify(orderRepository).findById(42L);
```

After the test finishes, the mock can still retain the stub returning `order` and the invocation history for `findById(42L)`. If the mock is reused, the next test may accidentally receive the same result or verification may see invocations from the earlier test.

In ordinary unit tests, Mockito creates a fresh mock per test instance or `@BeforeEach`, so state is naturally isolated. In Spring tests, a mock bean managed by the context can be shared due to caching. Therefore, an explicit reset policy is needed.

## 2. Mock Beans in Spring and the ApplicationContext Lifecycle

Spring supports replacing beans in tests with Mockito mocks. Depending on the version, a project may use Spring Boot's `@MockBean` or Spring Framework's `@MockitoBean`.

### 2.1. `@MockitoBean` in Spring Framework 6.2 and Later

Spring Framework 6.2 provides `@MockitoBean` in the package `org.springframework.test.context.bean.override.mockito`. This annotation instructs Spring to create or replace a bean with a Mockito mock in the `ApplicationContext`.

```java
@SpringJUnitConfig(OrderServiceTestConfig.class)
class OrderServiceTest {

    @MockitoBean
    private OrderRepository orderRepository;

    @Autowired
    private OrderService orderService;

    @Test
    void returnsOrderWhenRepositoryFindsIt() {
        var order = new Order(42L, "PENDING");
        when(orderRepository.findById(42L)).thenReturn(Optional.of(order));

        Order result = orderService.findOrder(42L);

        assertEquals(order, result);
        verify(orderRepository).findById(42L);
    }
}
```

`@MockitoBean` is processed by Spring TestContext and the mock is registered as a bean in the context. Other injected beans receive that mock instead of the specified real bean. The test can use the mock to control dependency outcomes without starting external services.

If you want to guarantee that a real bean already exists and must be replaced, you can use `enforceOverride = true`. When no matching bean exists to replace, the context fails instead of silently creating an extra mock bean:

```java
@MockitoBean(enforceOverride = true)
private OrderRepository orderRepository;
```

This is useful when the test's goal is to verify that the right bean in the application configuration was replaced. If the test intentionally creates a new mock for an interface without a real bean, there is no need to enable `enforceOverride`.

### 2.2. `@MockBean` in Older Spring Boot Projects

Older Spring Boot projects typically used `@MockBean`:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;
}
```

`@MockBean` belongs to Spring Boot Test. Starting in Spring Boot 3.4, this annotation was deprecated in favor of Spring Framework's bean override mechanism, which includes `@MockitoBean`. When upgrading, use the exact annotation and `MockReset` enum matching your project's dependency version; the two APIs reside in different packages.

Do not mix `@MockBean` and `@MockitoBean` arbitrarily in the same test suite. Follow the Spring Boot/Spring Framework version managed by the project and keep declarations consistent.

### 2.3. Why Can a Mock Bean Be Shared Across Tests?

Spring TestContext caches the `ApplicationContext` to avoid reinitializing expensive beans. Tests with compatible context configurations can receive the same cached context. A mock bean is a bean inside that context, so multiple tests can access the same instance.

```text
Test A --------+
               |
               v
        Cached ApplicationContext
               |
               v
        OrderRepository mock
               ^
               |
Test B --------+
```

JUnit's `@TestInstance(PER_METHOD)` creates a new test class instance per method by default, yet it does not recreate the entire Spring `ApplicationContext`. Thus, injected test fields can point to the same mock bean even though the test objects differ.

This is a key difference between a local `@Mock` and `@MockitoBean`:

| Characteristic | Local Mockito `@Mock` | Spring `@MockitoBean` |
|---|---|---|
| Where managed | Test instance or Mockito extension | Spring ApplicationContext |
| Typical lifecycle | One test instance/method | Follows cached context lifecycle |
| Shared across tests | No, if created fresh properly | Possible, when tests share a context |
| Reset | Create a new mock or reset manually | Spring-managed reset policy |
| Suitable for | Standalone logic unit tests | Spring integration/slice tests needing bean replacement in context |

## 3. Spring's Mock Reset Policy

`@MockitoBean` has a `reset` attribute that determines when Spring resets the mock. The options in `MockReset` are `BEFORE`, `AFTER`, and `NONE`.

| Mode | Behavior | Use Case |
|---|---|---|
| `AFTER` | Resets mock after each test method | Default; clears stubbing and invocations after test completion |
| `BEFORE` | Resets mock before each test method | Want to start the method with a clean mock before `@BeforeEach` configures stubs |
| `NONE` | Does not automatically reset | Use only when the test actively manages all mock state |

With `@MockitoBean`, the default mode is `AFTER`. Spring TestContext uses an integrated Mockito listener to reset mocks according to this policy. A test method can set up stubs in preparation and use them in the test body; after the test finishes, Spring resets the mock so the next test does not inherit leftover state.

Example explicitly declaring the default mode:

```java
@MockitoBean(reset = MockReset.AFTER)
private OrderRepository orderRepository;
```

If you want to reset before the method:

```java
@MockitoBean(reset = MockReset.BEFORE)
private OrderRepository orderRepository;
```

Here `MockReset` is Spring Framework's `org.springframework.test.context.bean.override.mockito.MockReset`. For Spring Boot's legacy `@MockBean`, the corresponding enum lives in `org.springframework.boot.test.mock.mockito`. When reading or migrating code, check imports so you do not mix up the two types.

### 3.1. `AFTER` Reset: The Default Choice

With `AFTER`, tests run against a mock already reset from the previous run. After the test method finishes, Spring resets the mock to clear stubbing and invocation history.

```java
@SpringJUnitConfig(OrderServiceTestConfig.class)
class OrderServiceTest {

    @MockitoBean(reset = MockReset.AFTER)
    private OrderRepository orderRepository;

    @Autowired
    private OrderService orderService;

    @Test
    void findsExistingOrder() {
        when(orderRepository.findById(1L))
                .thenReturn(Optional.of(new Order(1L, "PENDING")));

        assertEquals("PENDING", orderService.findOrder(1L).status());
    }

    @Test
    void returnsEmptyWhenOrderDoesNotExist() {
        when(orderRepository.findById(2L)).thenReturn(Optional.empty());

        assertTrue(orderService.findOrderOptional(2L).isEmpty());
    }
}
```

Both methods can share the same mock bean because Spring resets the mock after each method. The first test's stub is not kept around to affect the second test.

### 3.2. `BEFORE`: Reset Before Setting Up Fixtures

`BEFORE` clears mock state before a test method runs. This is useful when the test's `@BeforeEach` configures fresh stubbing and wants to guarantee any invocations from prior runs are cleared before fixtures are built.

```java
@MockitoBean(reset = MockReset.BEFORE)
private PaymentGateway paymentGateway;

@BeforeEach
void setUp() {
    when(paymentGateway.isAvailable()).thenReturn(true);
}

@Test
void processesPaymentWhenGatewayIsAvailable() {
    // Stub in setUp is configured on a clean mock.
}
```

Spring performs the reset in a callback prior to the test method; JUnit preparation callbacks such as `@BeforeEach` run within the method execution lifecycle. Consequently, stubs configured in `@BeforeEach` remain intact when the test body executes.

### 3.3. `NONE`: Taking Responsibility for State Management

`NONE` disables automatic resetting. Stubs and invocations can persist across multiple tests sharing the same context:

```java
@MockitoBean(reset = MockReset.NONE)
private OrderRepository orderRepository;
```

This mode is rarely needed. If a test chooses `NONE`, it must ensure stubbing and invocations do not leak into other tests. You can call `Mockito.reset(...)` or `clearInvocations(...)` intentionally, though manual cleanup is easily skipped when a test fails or has multiple branches.

Choose `NONE` only for a clear reason, such as a mock whose state is intentionally managed by a shared fixture. If each test needs its own scenario, `AFTER` or `BEFORE` is usually simpler and safer.

## 4. `reset()`, `clearInvocations()`, and Creating a Fresh Mock

Mockito provides distinct cleanup operations. Understand their effects before using them.

| API | Clears Stubbing | Clears Invocation History | Use When |
|---|---|---|---|
| `Mockito.reset(mock)` | Yes | Yes | Need to return the mock completely to its initial state |
| `Mockito.clearInvocations(mock)` | No | Yes | Want to keep stubs while restarting verification |
| Creating a new mock | Yes, since a new mock has no state | Yes | Want to isolate tests with separate instances |

Example:

```java
when(repository.count()).thenReturn(5L);
service.loadCount();

clearInvocations(repository);

verifyNoInteractions(repository); // Old invocations were cleared
assertEquals(5L, repository.count()); // Stub still remains
```

The example above only illustrates the difference between the two kinds of state; in a real test, note that the final `repository.count()` call itself creates a new invocation after `clearInvocations`.

`reset(mock)` clears both stubs and call history. After a reset, unstubbed calls return defaults based on return type, such as `null`, `0`, `false`, or empty collections depending on Mockito configuration. This is why resetting too early can cause tests to fail with confusing errors.

Creating a new mock is usually the best option in plain unit tests. Resetting a mock bean in Spring serves a different purpose: the mock belongs to a cached context and is injected into multiple beans, so Spring needs a state-cleanup mechanism to keep the context reusable.

## 5. Resetting a Mock Does Not Mean Recreating the Bean

When Spring resets a `@MockitoBean`, Spring clears Mockito state on the same mock instance. Spring does not necessarily remove the bean from the ApplicationContext and construct a new mock object.

This matters when another bean already had the mock injected into a constructor or field. That bean retains a reference to the same instance; resetting returns the instance to a clean mock state without rebuilding the entire context.

```text
Cached ApplicationContext
       |
       +---- OrderService
       |         |
       |         +---- reference to OrderRepository mock
       |
       +---- OrderRepository mock
                  |
                  +---- stubbing + invocations

After reset:
       |
       +---- OrderService still holds the same reference
       |
       +---- OrderRepository mock is still the same instance,
             but stubbing and invocations have been cleared
```

If a test replaces a bean with another instance outside the bean override mechanism, beans that already injected the old reference may not automatically receive the new instance. Therefore, use Spring's `@MockitoBean`/`@MockBean` mechanism when replacing beans in the context rather than mutating the bean factory after other beans have been created.

## 6. Why Can Resetting Mocks Be Unsafe Under Parallel Execution?

JUnit Jupiter runs tests sequentially by default. When parallel execution is enabled, multiple test methods or test classes can run concurrently. If they share a Spring context and access the same mock bean, operations on the mock can interleave.

Example of two tests using the same `orderRepository`:

```text
Test A                         Test B
------                         ------
stub findById(1)               stub findById(2)
call service(1)                call service(2)
verify findById(1)             verify findById(2)
reset mock AFTER               reset mock AFTER
```

If the two tests run concurrently:

- Stubs from A and B can coexist on the same mock, making results depend on arguments and setup order.
- Invocation history holds calls from both tests, so verification can see interactions from the other test.
- One test can reset the mock while the other test is executing or verifying.
- A freshly configured stub can be reset before the other test calls the dependency.
- Unstable execution order can cause flaky failures that only appear intermittently on CI.

`AFTER` reset only ensures the mock is cleaned after a test method via listener lifecycle callbacks. It does not turn a shared mock bean into a thread-local mock. `BEFORE` also does not resolve conflicts if two tests start concurrently: one test can reset the mock after the other has already stubbed it.

Mockito supports using mocks in certain multithreaded scenarios, yet that does not make a scenario where multiple tests concurrently mutate stubbing, invocation history, and resets independent. The problem here is that tests share mutable state, not merely internal library thread safety.

## 7. JUnit Jupiter Parallel Execution

By default, JUnit Jupiter does not enable parallel execution. It can be enabled via `junit-platform.properties` on the test classpath:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
```

With this configuration, Jupiter can run test methods and classes concurrently according to execution mode. If the project has not enabled parallel execution, tests within a single JUnit run typically execute sequentially according to the engine's scheduler.

Do not enable parallel execution solely to shorten runtime without first identifying shared resources. Beyond mock beans, resources that can cause contention include:

- Mutable singleton beans in the ApplicationContext.
- Shared database records or schemas.
- Files, temporary directories, or fixed ports.
- System properties, default locale, timezone, and system clock.
- Static fields, singleton caches, or library-level shared state.
- Containers or external services mutated concurrently by multiple tests.

## 8. How to Protect Tests When Parallel Execution Is Needed

### 8.1. Prefer Local Mocks for Unit Tests

If you are only testing a service's logic and do not need a Spring context, create fresh mocks per test using the Mockito extension:

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceUnitTest {

    @Mock
    private OrderRepository orderRepository;

    @InjectMocks
    private OrderService orderService;

    @Test
    void findsOrder() {
        when(orderRepository.findById(1L))
                .thenReturn(Optional.of(new Order(1L, "PENDING")));

        assertEquals("PENDING", orderService.findOrder(1L).status());
    }
}
```

With JUnit's default `PER_METHOD`, each test method gets a new test instance; the Mockito extension initializes fresh mocks for that instance. This is a simple isolation strategy when bean wiring or Spring configuration is not under test.

### 8.2. Do Not Run Tests Sharing the Same Mock Bean Concurrently

If tests need `@MockitoBean` in the same context, keep that group of tests sequential. The simplest approach is leaving parallel execution disabled for that group or configuring an appropriate execution mode.

JUnit Jupiter provides `@ResourceLock` to synchronize tests using the same logical resource:

```java
@SpringJUnitConfig(OrderServiceTestConfig.class)
@ResourceLock("shared-order-repository-mock")
class OrderServiceIntegrationTests {

    @MockitoBean
    private OrderRepository orderRepository;

    @Test
    void findsPendingOrder() {
        when(orderRepository.findById(1L))
                .thenReturn(Optional.of(new Order(1L, "PENDING")));
        // ...
    }

    @Test
    void returnsEmptyForMissingOrder() {
        when(orderRepository.findById(2L)).thenReturn(Optional.empty());
        // ...
    }
}
```

`@ResourceLock` makes tests with the same resource name obey JUnit Platform locking within the same test execution. You can place the annotation on a class to guard all tests in the class, or on methods to guard specific methods.

If multiple classes share a mock bean and need locking across those classes, declare the same resource name on all relevant classes/methods. The resource name must match consistently; two different names do not form the same lock.

`@ResourceLock` coordinates only within a single JUnit execution/JVM. It does not create a distributed lock across multiple forked Gradle processes, Maven forks, or multiple CI workers. If a resource is shared across JVMs, isolate the resource or use an appropriate external locking mechanism.

### 8.3. Use `@Isolated` for Tests Requiring Global Exclusivity in a JUnit Run

JUnit Jupiter provides `@Isolated` to mark a test class that must run in isolation from all other tests in the same test plan. It is useful when a test touches global state that is hard to model with a specific resource lock.

```java
@Isolated
class GlobalConfigurationTests {

    @Test
    void changesGlobalConfigurationTemporarily() {
        // Test modifies global state and restores it afterward.
    }
}
```

`@Isolated` affects JUnit Platform scheduling within a single run; it neither replaces cleanup nor synchronizes across different JVMs. Use it only when a test truly needs exclusivity across the entire test plan, because the annotation reduces parallelism.

### 8.4. Use Separate Contexts When Independent Mock State Is Needed

If two test groups need different mock configurations and must run in parallel, you can design a separate context for each group. The context cache distinguishes configurations and bean overrides; distinct configurations produce separate contexts, giving each group its own mock bean.

However, do not intentionally create many contexts just to work around a reset issue when a `@ResourceLock` or sequential execution already meets your needs. Many contexts increase startup time, connection pool count, and resources to manage.

### 8.5. Avoid Sharing Mutable Stubs Across Tests

Even when tests run sequentially, set up stubs within each test or `@BeforeEach`, rather than relying on stubs from a previous test. Do not treat test execution order as part of the contract.

Several useful principles:

- Each test configures the mock responses it needs.
- Do not let a test depend on invocation history generated by another test.
- Do not store mocks or stub results in shared static fields.
- Do not use `@TestInstance(PER_CLASS)` to share mutable mocks unless there is a clear reason and proper synchronization.
- Avoid calling `reset()` from an arbitrary thread or callback while another test might be using the mock.

## 9. `@DirtiesContext` Is Not a Parallel Locking Mechanism

`@DirtiesContext` removes a context from the cache and closes it according to the specified scope. This annotation is useful when a test mutates context state so it cannot be safely reused.

However, `@DirtiesContext` does not synchronize two running tests. If test A closes the context while test B is still using beans from that context, test B may encounter errors or undefined behavior. Therefore:

- Do not use `@DirtiesContext` as a substitute for `@ResourceLock`.
- Do not assume `@DirtiesContext` waits for all other tests using the context to finish.
- Avoid running tests in parallel if they share a context and one test can mark the context dirty.
- If context configuration needs resetting, coordinate test ordering or isolate contexts appropriately.

Resetting a mock and evicting a context from the cache solve two different problems. Resetting keeps the mock bean while clearing Mockito state; `@DirtiesContext` closes and removes the context according to the chosen scope.

## 10. Reset Ordering and the JUnit/Spring Lifecycle

Spring TestContext integrates with JUnit through `SpringExtension`. TestContext listeners are invoked at lifecycle points to prepare the context, inject dependencies, manage transactions, and reset bean overrides.

At a high level, for a test method:

```text
Spring prepares test context and injects fields
                  |
                  v
Reset mock if configured as BEFORE
                  |
                  v
JUnit @BeforeEach
                  |
                  v
Test method
                  |
                  v
JUnit @AfterEach
                  |
                  v
Reset mock if configured as AFTER
                  |
                  v
End of test method
```

The diagram shows the high-level order to explain the reset policy. Callback details can depend on other extensions and listeners registered in the test. If another extension also mutates mocks or context state, check that extension's execution order.

With `BEFORE`, stubbing in `@BeforeEach` is configured after the reset. With `AFTER`, the test's stubbing and invocations are cleaned up after the method finishes. If `NONE` is used, Spring performs no automatic reset step.

## 11. Error-Prone Situations

### 11.1. Leftover Stubs from a Previous Test

Symptom: a test does not declare a stub for a call, yet the service still receives a specific object. The cause may be a reused mock bean that was not reset.

How to handle it:

- Check whether `@MockitoBean` uses the default reset or `AFTER`/`BEFORE`.
- If using `NONE`, check manual cleanup.
- Ensure tests do not depend on execution order.

### 11.2. Verification Sees Invocations from Another Test

Symptom: `verify(mock).someMethod()` fails because there are more invocations than expected. If the mock is shared, invocation history may contain interactions from another or prior test.

The fix is resetting/clearing invocations at the right time or ensuring tests do not run concurrently on the same mock. `clearInvocations` clears only invocation history while preserving stubs; `reset` clears both.

### 11.3. Tests Fail Intermittently When CI Enables Parallel Execution

Symptom: running tests individually succeeds, while running the full suite or running on CI fails flakily.

Check:

- Do multiple tests share `@MockitoBean` in the same context?
- Does any test use `reset = NONE` or call `Mockito.reset()` manually?
- Does any test use `@DirtiesContext` while other tests are still using the context?
- Are JUnit parallel execution or build-tool parallel forks enabled?
- Are system properties, static state, files, ports, or database data shared?

Then choose `@ResourceLock`, `@Isolated`, sequential execution, or separate resources/contexts matching the actually shared scope.

### 11.4. Mock Reset Wipes Stubs Configured in `@BeforeEach`

With `BEFORE`, Spring resets before JUnit runs `@BeforeEach`; stubs configured in that callback remain active when the test method begins. If the test manually calls `Mockito.reset()` after `@BeforeEach`, the newly configured stubs are wiped. Avoid unnecessary manual resets inside the test body.

### 11.5. A Test Needs Invocations Preserved for Assertions in `@AfterEach`

If you need to inspect invocations in `@AfterEach`, `AFTER` mode typically resets after test method cleanup callbacks. However, do not rely on listener details if another extension also manipulates mocks. Placing assertions directly in the test method after the action under test makes the lifecycle clearer.

## 12. Example of Organizing Safe Spring Tests

Suppose `OrderService` depends on `OrderRepository`. An integration test needs to replace the repository with a mock in the Spring context:

```java
@SpringJUnitConfig(OrderServiceTestConfig.class)
@ResourceLock("order-service-repository-mock")
class OrderServiceSpringTest {

    @MockitoBean(reset = MockReset.AFTER)
    private OrderRepository orderRepository;

    @Autowired
    private OrderService orderService;

    @Test
    void returnsExistingOrder() {
        var order = new Order(42L, "PENDING");
        when(orderRepository.findById(42L))
                .thenReturn(Optional.of(order));

        Order result = orderService.findOrder(42L);

        assertEquals(42L, result.id());
        verify(orderRepository).findById(42L);
    }

    @Test
    void reportsMissingOrder() {
        when(orderRepository.findById(99L))
                .thenReturn(Optional.empty());

        assertThrows(OrderNotFoundException.class,
                () -> orderService.findOrder(99L));

        verify(orderRepository).findById(99L);
    }
}
```

In this example, each method sets up its own stubs and verifies its own interactions. `AFTER` cleans the mock after the method; `@ResourceLock` coordinates other tests declaring the same resource name within the same JUnit execution. If parallel execution is not enabled, the lock may be unnecessary, yet it clearly documents the protected resource if the suite's execution configuration changes.

If two tests do not need Spring wiring, convert them into unit tests with `@Mock` and `@InjectMocks`. Then each test instance has its own mock and no shared lock is needed.

## 13. Checklist Before Enabling Parallel Execution

Before allowing Spring tests to run concurrently, determine:

- Which tests use `@MockitoBean` or `@MockBean`?
- Do those tests share an `ApplicationContext` and the same mock beans?
- Are mocks reset automatically, and does reset happen before or after tests?
- Does any test use `MockReset.NONE` or manual resetting?
- Do tests concurrently modify stubbing or verify invocations on one mock?
- Does any test use `@DirtiesContext` on a context that other tests are using?
- Can Spring mock beans be replaced by local mocks in unit tests?
- Can `@ResourceLock` or `@Isolated` be used to protect shared resources?
- Does the build tool run multiple JVMs/forks or multiple CI workers simultaneously?
- Are databases, files, ports, system properties, and static state isolated?

There is no need to lock every test just because it uses Spring. Only tests capable of accessing and mutating the same resource need coordination. Overly broad locking reduces parallelism and can mask unnecessary shared-state designs.

## 14. Practical Principles

- Use local mocks created per test for plain unit tests.
- Use `@MockitoBean` when replacing a bean in the Spring context; use `@MockBean` in legacy codebases matching their Spring Boot version.
- Keep automatic reset at `AFTER` or `BEFORE` unless there is a clear reason to pick `NONE`.
- Understand that reset cleans the same mock instance; it does not create a new instance or refresh the `ApplicationContext`.
- Never let tests depend on stubs or invocations from other tests.
- If multiple tests share a mock bean, do not let them concurrently stub, call, verify, or reset the same mock; use `@ResourceLock`, `@Isolated`, or sequential execution.
- Remember that JUnit locks do not coordinate across multiple JVMs or multiple CI workers.
- Do not use `@DirtiesContext` as a locking mechanism; it only removes and closes the context from the cache.
- Separate tests needing independent contexts when parallelism is genuinely required, while weighing context creation cost.
- Run tests both individually and as a full suite in the CI configuration to catch order-dependency or shared-state bugs.

Mock resetting and parallel execution coordination are two sides of the same test-state management problem. Spring can reuse an `ApplicationContext`, so mock beans can also be reused. A reset policy ensures each test starts or ends with the mock in a deterministic state; locking or isolation ensures two tests do not mutate the same mock simultaneously. By choosing the right boundaries for unit tests, Spring integration tests, and parallel execution, a test suite can benefit from context caching while keeping results stable across local runs and CI.
