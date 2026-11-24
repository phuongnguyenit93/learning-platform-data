# Resetting State, Strict Stubbing, and Redundant Configuration

Mocks and spies help control collaborators in unit tests, yet they also hold state throughout a test run. A mock can store stubbed behaviors and invocation history; a spy additionally wraps a real object and can therefore hold that object's business state as well. If this state is shared or overly broadly configured, tests can depend on one another, mask bugs, or fail due to stubs that are never used.

Mockito provides reset, clear-invocation, and strict-stubbing mechanisms to manage these issues. You need to understand which piece of state each mechanism modifies and apply it in the right place. In most unit tests, creating fresh mocks per test and declaring only the stubs that test needs is the simplest, most readable approach.

## What state does a mock hold?

A Mockito mock generally has two key categories of state:

1. **Stubbing:** configured mock behavior, such as returning a specific object when `findById(10)` is called.
2. **Invocation history:** history of methods called, including method, arguments, and call counts.

~~~java
when(repository.findById(10L)).thenReturn(Optional.of(customer));

service.load(10L);

verify(repository).findById(10L);
~~~

The `when(...).thenReturn(...)` line configures stubbing. When the service calls the repository, Mockito records the invocation. `verify(...)` reads that history to confirm the interaction.

These two categories of state can be managed separately. `reset(mock)` clears both stubbing and invocation history. `clearInvocations(mock)` clears only invocation history while keeping stubbing. Choosing the wrong API can cause a test to lose stubbed behavior or carry over invocation history from an earlier phase.

| API | Stubbing | Invocation history | Purpose |
|---|---|---|---|
| `reset(mock)` | Cleared | Cleared | Returns the mock to an unconfigured state |
| `clearInvocations(mock)` | Kept | Cleared | Starts observing a new interaction phase |
| Creating a new mock | None from start | None from start | Isolates the test with a fresh collaborator |

## Why is resetting between tests usually unnecessary?

With JUnit Jupiter, the default lifecycle creates a new test instance per test method. When using `MockitoExtension`, fields annotated with `@Mock` are initialized and managed for that test instance. Therefore, each test normally gets fresh mocks rather than sharing the previous test's mocks.

~~~java
@ExtendWith(MockitoExtension.class)
class CustomerServiceTest {

    @Mock
    CustomerRepository repository;

    @InjectMocks
    CustomerService service;

    @Test
    void returnsCustomerWhenFound() {
        when(repository.findById(10L))
            .thenReturn(Optional.of(new Customer(10L, "Lan")));

        assertThat(service.findName(10L)).isEqualTo("Lan");
    }

    @Test
    void returnsFallbackWhenMissing() {
        when(repository.findById(20L)).thenReturn(Optional.empty());

        assertThat(service.findName(20L)).isEqualTo("Unknown");
    }
}
~~~

Both tests have their own mocks and service. Stubs from the first test do not leak into the second. There is no need to call `reset(repository)` in `@BeforeEach` or `@AfterEach`.

Only when intentionally using the `@TestInstance(PER_CLASS)` lifecycle, storing mocks in `static` fields, sharing fixtures across tests, or manually creating a mock scoped wider than a test method do you need to consider shared state. Even then, it is usually better to scope mocks and the object under test to individual tests or create fresh fixtures per test.

Having to reset mocks before every test so tests do not interfere with one another is a sign of poor design. Check why the mock is shared, whether the test can receive a fresh instance, and whether the real object under test holds mutable state.

## What does reset(mock) clear?

`Mockito.reset(mock)` clears all stubbing configurations and invocation history on the mock. After reset, the mock remains the same object, but any unstubbed calls revert to Mockito's default behavior (for example returning `null`, `false`, `0`, or an empty value matching the return type).

~~~java
@Test
void resetRemovesStubbingAndInvocationHistory() {
    List<String> names = mock(List.class);

    when(names.get(0)).thenReturn("Lan");
    names.get(0);
    verify(names).get(0);

    reset(names);

    // Old stub was removed; this call receives the default value (null).
    assertThat(names.get(0)).isNull();

    // History before reset was also cleared.
    verify(names).get(0);
}
~~~

The example above illustrates the API rather than normal test organization. After reset, the new `get(0)` call is recorded; thus the final `verify(names).get(0)` checks the new invocation, not the invocation before reset.

A common mistake is resetting a mock and forgetting to reconfigure its stubs:

~~~java
@BeforeEach
void setUp() {
    when(repository.findAll()).thenReturn(List.of(customer));
}

@Test
void findsCustomer() {
    reset(repository);

    // findAll() no longer has a stub; the result may be null.
    assertThat(service.findAll()).contains(customer);
}
~~~

In this example, reset wiped out the configuration just created in setup. If a test needs to alter a collaborator's behavior, configure a dedicated stub inside that test instead of resetting a mock configured for shared use.

Mockito recommends minimizing `reset()` in ordinary tests. Resetting between steps of the same test usually signals that the test is doing too much or that a mock is shared beyond its necessary scope. Splitting scenarios into separate tests is usually clearer.

## How does clearInvocations(mock) differ from reset(mock)?

`clearInvocations(mock)` clears invocation history while preserving stubbing. It is useful in multi-phase tests where the same stubbed behavior must stay active, but you only want to verify calls originating from the subsequent phase.

~~~java
@Test
void clearsOnlyInvocationHistory() {
    List<String> names = mock(List.class);
    when(names.get(0)).thenReturn("Lan");

    names.get(0);
    verify(names).get(0);

    clearInvocations(names);

    // Stub is still active.
    assertThat(names.get(0)).isEqualTo("Lan");

    // History was cleared; only new invocations count.
    verify(names).get(0);
}
~~~

One case where `clearInvocations` can fit is testing a two-phase interaction protocol: first preparing or initializing the collaborator, then inspecting only the calls made by the primary action. However, consider moving preparation into a fixture or creating a separate mock so tests do not need manual history clearing.

Do not use `clearInvocations` to hide extra interactions. If a service calls a collaborator unexpectedly, clearing history before verifying can erase evidence of that bug.

## Spies also have state to manage

Mocks replace implementations with stubbed behavior. Spies wrap a real object: unstubbed methods usually execute real implementations, and mutations on the object can persist after calls.

~~~java
class NameFormatter {
    private int callCount;

    String format(String name) {
        callCount++;
        return name.trim().toUpperCase();
    }

    int callCount() {
        return callCount;
    }
}
~~~

A spy can be created as follows:

~~~java
NameFormatter realFormatter = new NameFormatter();
NameFormatter formatter = spy(realFormatter);

assertThat(formatter.format(" lan ")).isEqualTo("LAN");
assertThat(formatter.callCount()).isEqualTo(1);
~~~

If the test calls real methods, the `callCount` state changes. `reset(formatter)` clears stubbing and invocation history managed by Mockito, but does not restore the internal state of the real object back to its initial values. If `callCount` is already 1, resetting the spy does not return it to 0.

Therefore, to isolate tests using spies, create a fresh real object for every test. Do not use a global spy, reset it, and assume the underlying object has been refreshed.

### Stubbing a spy without accidentally calling the real method

With mocks, the common style is:

~~~java
when(repository.findById(10L)).thenReturn(Optional.of(customer));
~~~

With spies, the expression inside `when(...)` can invoke the real method while configuring the stub:

~~~java
NameFormatter formatter = spy(new NameFormatter());

// May call the real format() implementation during stubbing.
when(formatter.format(" lan ")).thenReturn("TEST");
~~~

If the real method has side effects, accesses resources, or throws an exception for that input, configuring the stub can cause unwanted effects. Use the `doReturn(...).when(spy)...` form to avoid calling the real implementation during stubbing:

~~~java
doReturn("TEST").when(formatter).format(" lan ");

assertThat(formatter.format(" lan ")).isEqualTo("TEST");
~~~

Sibling APIs include `doThrow()`, `doAnswer()`, and `doNothing()`. Use them when stubbing a spy without executing the real method during setup.

Spies should be used intentionally, typically when needing to preserve most real behavior while replacing a specific collaboration point. If you have to stub many methods on a spy or reset it constantly, consider extracting the dependency via an interface or constructor injection to use clearer mocks/fakes.

## What is strict stubbing?

Strict stubbing requires declared stubs to match the test's actual calls. It catches two kinds of problems early:

- **Unnecessary stubbing:** the test configured a stubbed behavior, yet no call used that stub.
- **Stubbing argument mismatch:** the test configured a call with certain arguments, while actual code called the same method with different arguments; this often indicates either the stub or the code under test is wrong.

Mockito provides strictness levels:

| Level | Behavior |
|---|---|
| `STRICT_STUBS` | Detects unused stubs and suspicious mismatches; automatically marks used stub calls as verified for `verifyNoMoreInteractions` |
| `WARN` | Logs warnings about mismatched stubbing instead of failing the test in strict mode |
| `LENIENT` | Skips strict stubbing checks |

When using `MockitoExtension` with JUnit Jupiter, strict stubbing is the standard default mode. You can declare the strictness level explicitly using `@MockitoSettings`.

~~~java
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.STRICT_STUBS)
class PricingServiceTest {
    // ...
}
~~~

Strict stubbing makes tests cleaner because used stubs are handled by Mockito as already-verified interactions within the strict-stubs mechanism. It does not replace assertions on business outcomes. Tests must still verify the outputs, state, or exceptions they actually care about.

## UnnecessaryStubbingException: configured but unused

A stub is considered unnecessary when the test makes no matching call. For example:

~~~java
@ExtendWith(MockitoExtension.class)
class CustomerServiceTest {

    @Mock
    CustomerRepository repository;

    @InjectMocks
    CustomerService service;

    @BeforeEach
    void setUp() {
        when(repository.count()).thenReturn(1L);
    }

    @Test
    void returnsFallbackWhenCustomerIsMissing() {
        when(repository.findById(20L)).thenReturn(Optional.empty());

        assertThat(service.findName(20L)).isEqualTo("Unknown");
    }
}
~~~

The test only calls `findById(20L)`; the `count()` stub in `@BeforeEach` goes unused. Because it is a different method, the example clearly illustrates an unused stub without introducing an argument-mismatch case. Under strict stubbing, Mockito can throw `UnnecessaryStubbingException` when the test session ends.

The best fix is moving the stub directly into the test that needs it:

~~~java
@Test
void returnsNameWhenCustomerExists() {
    when(repository.findById(10L))
        .thenReturn(Optional.of(new Customer(10L, "Lan")));

    assertThat(service.findName(10L)).isEqualTo("Lan");
}

@Test
void returnsFallbackWhenCustomerIsMissing() {
    when(repository.findById(20L)).thenReturn(Optional.empty());

    assertThat(service.findName(20L)).isEqualTo("Unknown");
}
~~~

Each test declares only the data and collaborator behavior needed for that scenario. Configuration stays close to assertions, readers easily understand test preconditions, and strict stubbing does not have to ignore unused stubs.

If multiple tests genuinely need the same stub, it can live in a shared fixture, provided every test using that fixture calls the stub. If only a few tests use it, local configuration is usually clearer.

## PotentialStubbingProblem: stub argument mismatch

Suppose a test configures:

~~~java
when(repository.findByEmail("lan@example.test"))
    .thenReturn(Optional.of(customer));
~~~

Yet the service actually calls:

~~~java
repository.findByEmail("lan@exampl.test");
~~~

This might be a typo in production code or in the test. Strict stubbing can detect argument mismatches and report `PotentialStubbingProblem`, identifying discrepancies earlier than returning a mock default and failing at a downstream assertion.

When encountering a mismatch error:

1. Read the arguments in the stub and the arguments in the actual invocation.
2. Determine which value is right according to the business contract.
3. Fix the test fixture or production code based on the evidence.
4. Only switch to a matcher like `anyString()` if the test does not need to check a specific value; if the argument has business meaning, keep exact matching.
5. If stubbing the same method multiple times with different arguments, consider `doReturn(...).when(...)` or BDD `willReturn(...).given(...)` so Mockito does not treat a call made during stubbing as an invocation to check.

Do not change all stubs to `any()` just to eliminate strictness errors. Doing so can stop tests from checking whether the unit passes the right data to its collaborators.

## When to use lenient stubbing?

Sometimes a stub may be used in some tests of a shared fixture while unused in others. Mockito lets you mark that specific stub as lenient:

~~~java
lenient()
    .when(featureFlags.isEnabled("new-checkout"))
    .thenReturn(true);
~~~

Or you can set strictness for the entire test class:

~~~java
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class LegacyServiceTest {
    // ...
}
~~~

Lenient reduces the ability to catch redundant configuration. Therefore, prefer this order:

1. Move the stub into the specific test method.
2. Split shared fixtures into smaller fixtures grouped by behavior.
3. If the stub is genuinely optional with a clear reason, mark just that stub with `lenient()`.
4. Only switch the whole class to `LENIENT` for a special reason and once you understand which strictness checks are bypassed.

Do not add `lenient()` to every stub just to silence test suite errors. Strict stubbing errors usually signal that test setup is broader than actually needed or that arguments between test and code do not match.

## Strict stubbing does not mean verifying every call

Distinguish three questions:

- Was the stub used?
- Did the unit call the collaborator with the expected arguments and count?
- Is the business outcome right?

Strict stubbing primarily helps detect unused stubs and mismatches. `verify()` is used when the interaction is part of the contract to confirm, such as requiring the service to reserve the exact inventory quantity. Assertions verify observable outcomes like totals, state, or exceptions.

~~~java
@Test
void reservesRequestedQuantityAndReturnsOrder() {
    when(inventory.reserve("SKU-1", 2)).thenReturn(true);

    Order result = service.place(new OrderCommand("SKU-1", 2));

    assertThat(result.quantity()).isEqualTo(2);
    verify(inventory).reserve("SKU-1", 2);
}
~~~

Not every stub needs a matching `verify()` call. Under `STRICT_STUBS`, calls that matched a stub are automatically treated as verified in the context of `verifyNoMoreInteractions`. Adding `verifyNoMoreInteractions()` to every test usually couples tests excessively to implementation details and hampers refactoring. Only verify interactions meaningful to the unit's contract.

## Managing mock beans in Spring Test

In pure Mockito tests, `MockitoExtension` creates and manages mocks per test session. In Spring integration tests, mocks can be registered in the ApplicationContext to replace a real bean, such as via `@MockitoBean` in modern Spring Framework.

Because an ApplicationContext can be cached and reused across multiple tests, mock beans in the context have a different lifecycle from ordinary mock fields. Spring provides a policy for resetting mock beans after tests; `@MockitoBean` defaults to resetting after each test method. This clears stubbing and invocations from the previous test while keeping the cached context. This reset policy is independent of `MockitoExtension`'s strict stubbing: Spring resetting a mock bean does not automatically mean the mock bean participates in the same Mockito test session or undergoes unused-stubbing checks under the same lifecycle.

~~~java
@SpringJUnitConfig(AppTestConfig.class)
class CheckoutIntegrationTest {

    @MockitoBean
    PaymentGateway paymentGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void completesCheckoutWhenPaymentSucceeds() {
        when(paymentGateway.charge(any()))
            .thenReturn(PaymentResult.approved());

        var result = checkoutService.checkout(command());

        assertThat(result.isSuccessful()).isTrue();
    }
}
~~~

The example assumes the context contains `CheckoutService` and `PaymentGateway` beans along with their corresponding types. Even when using mock beans in a context, still declare stubs locally inside each test so strictness and fixture scope remain easy to track. If you need to customize a bean override's reset mode, do so based on actual test needs and the Spring version in use.

Do not confuse resetting a mock bean with recreating the entire ApplicationContext. Resetting a mock only refreshes Mockito state on the replacement bean; it does not reinitialize other beans and does not roll back side effects outside the mock such as database data, files, or sent messages.

## Checklist when tests report stubbing errors or leaked state

When Mockito reports an error or results depend on test order, diagnose step by step:

1. **Find unused stubs.** Does the stub belong to the current test method? Can it be moved out of `@BeforeEach` or a shared fixture?
2. **Compare arguments.** Do actual invocation arguments match the stub? Which value is right per the contract?
3. **Check mock scope.** Is the mock shared via a static field, `PER_CLASS`, Spring context, or global fixture?
4. **Determine the reset type.** Do both stubs and invocations need clearing, or only interaction history?
5. **Inspect spies.** Does the real object inside the spy retain mutable state or side effects from a previous test?
6. **Look for lenient hiding bugs.** Is the stub genuinely optional, or was it marked lenient just to bypass warnings?
7. **Check effects outside Mockito.** Resetting mocks does not undo database writes, files, messages, threads, or real object state.

| Symptom | Resolution |
|---|---|
| `UnnecessaryStubbingException` | Move the stub into the test that uses it; narrow shared fixtures |
| `PotentialStubbingProblem` | Compare stub arguments against actual invocations and fix the wrong source |
| Later test receives results from an old stub | Check if the mock is shared; prefer creating a fresh mock |
| Spy still keeps old counters or state after reset | Instantiate a new real object and create a new spy |
| `verifyNoMoreInteractions` fails due to unexpected call | Review the interaction contract; do not clear history to hide bugs |
| Test only passes when using LENIENT | Identify redundant stubs or overly broad fixtures before relaxing strictness |

## Principles of application

Let each test own its mocks, stubs, and data. Configure behavior right inside the test that needs it, keep strict stubbing enabled to catch redundant setup, and verify only interactions belonging to the unit's contract.

Use `reset()` when you genuinely need to clear both stubbing and invocation history on the same mock; use `clearInvocations()` when you only need to start a new observation phase. For spies, instantiate a fresh real object if clean state is needed because Mockito reset does not revert internal object state. When strict stubbing reports an error, fix the fixture or arguments before considering lenient.

These practices keep mocks and spies aligned with the scope of a single test, surface configuration mistakes early, and keep test results stable across runs.
