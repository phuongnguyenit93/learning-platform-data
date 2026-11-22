# Distinguishing Errors in the Code Under Test from Errors in Test Data Setup (Java)

## 1. The problem: a "green" test does not necessarily test the right code

A test typically has three phases: **Arrange** (preparing data and preconditions), **Act** (invoking the code under test, or *System Under Test* — SUT), and **Assert** (verifying the outcome). When testing exceptions, the boundary between Arrange and Act is especially important.

Consider the following JUnit 5 snippet:

```java
assertThrows(IllegalArgumentException.class, () -> {
    OrderLine line = makeOrderLine("", -2);
    orderService.calculate(line);
});
```

This is a **test snippet that requires the helper methods/classes and JUnit 5 to already be defined**, not a standalone Java SE program. The author wants to verify that `orderService.calculate(...)` rejects a negative quantity. However, `makeOrderLine("", -2)` may throw `IllegalArgumentException` before `calculate` ever runs—for example, due to an empty SKU. In that case, `assertThrows` still reports **PASS**, even though the SUT **was never called once**.

This is a **false positive**: the test satisfies the formal condition "an exception of type X was thrown," but it does not prove the behavior being tested.

The usual solution is:

1. Prepare the fixture **outside the `assertThrows` lambda**.
2. Ensure the fixture is valid with respect to **all conditions other than the one under test**.
3. Restrict the lambda to only **the action responsible for producing the expected exception**.
4. Also verify the error code, exception attributes, cause, or SUT interactions when valuable.
5. If the Arrange step fails, the test must report a **setup failure**, not be mistaken for a passing Act step.

**Core principle:** where an exception originates and when it occurs matter just as much as the exception type.

## 2. The three phases: Arrange — Act — Assert

| Phase | Responsibility | Common failures | Meaning for the test result |
| --- | --- | --- | --- |
| Arrange | Create objects, fixtures, stubs, mocks, DB data, test configuration | Factory missing data, JSON parse error, container fails to start, unconfigured mock | **The test has not yet reached the behavior under test** |
| Act | Invoke the SUT itself for a specific scenario | Business exception, validation error, dependency failure that the SUT must handle | This is **the failure belonging to the behavior the test evaluates** |
| Assert | Verify results, exceptions, state, interactions | Wrong assertion, buggy test helper, invalid result access | The test failed at the **verification step**, which does not mean the SUT threw the right exception |
| Cleanup/teardown | Close files, connections, transactions, test resources | Close, rollback, or cleanup error | Can fail the test even though Act/Assert already ran |

An exception thrown in Arrange is not automatically a "SUT bug." It may be a bug in the fixture builder itself, data seeding, test infrastructure, or the environment. Conversely, **test data setup is also code** and should be tested when it contains non-trivial logic. Separating the error source tells you whether to fix the fixture or fix the SUT.

When reading a test failure, identify **which phase** failed before deciding to change production code.

## 3. Why exception type alone is not enough

`assertThrows(IllegalArgumentException.class, executable)` checks whether an exception of type `IllegalArgumentException` or a subtype of it is thrown when executing `executable`. It **does not know your intent**: that exception could come from:

- A builder `new OrderLine(...)`;
- A validator inside a mock/stub;
- A JSON mapper;
- The SUT method;
- A callback triggered by the SUT;
- An assertion helper inside the same lambda;
- A data-preparation method called "conveniently" inside Act.

Incorrect example:

```java
assertThrows(IllegalStateException.class, () -> {
    Repository repository = createRepository();
    MyService service = new MyService(repository);
    service.run();
});
```

This is a JUnit snippet with application APIs already defined. `createRepository()` or the `MyService` constructor might throw `IllegalStateException` before `run()`. The test passes without proving that `run()` honors its contract.

**Fix:**

```java
Repository repository = createRepository();
MyService service = new MyService(repository);

IllegalStateException error =
        assertThrows(IllegalStateException.class, service::run);
```

If Arrange fails, the test still **FAILS**, but the failure points directly to the setup step. If Arrange succeeds, only `run` is inside the expected-exception scope.

There is no need to wrap setup in `try/catch` to "fix" a failure. Letting the framework report setup errors naturally is usually sufficient, provided the test is clearly structured.

## 4. Standalone Java 17+ example: false positive and fix

The following program does not require JUnit so it can be run directly with JDK 17+. It defines a simple `expectThrows` helper solely to illustrate behavior similar to an exception expectation, **not as a full replacement for JUnit**.

Scenarios:

- **BROAD_SCOPE:** a single lambda wraps both Arrange and Act. Arrange throws `IllegalArgumentException`, and the test thinks it "caught the right error."
- **SETUP_FAILED:** separates Arrange out and clearly reveals the fixture error.
- **ACT_FAILED:** creates a fixture with a valid SKU but a negative quantity to intentionally test the SUT's validation; only calls the SUT inside `expectThrows`.
- **SUCCESS_TOTAL:** includes a happy-path check.
- Automated checks stop the program with `AssertionError` if any result is incorrect.

Create the file **`TestBoundaryDemo.java`**:

```java
public class TestBoundaryDemo {
    record OrderLine(String sku, int quantity) {}

    static OrderLine arrange(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("fixture: sku is blank");
        }
        return new OrderLine(sku, quantity);
    }

    static int calculate(OrderLine line) {
        if (line.quantity() < 0) {
            throw new IllegalArgumentException("sut: quantity is negative");
        }
        return line.quantity() * 10;
    }

    static <T extends Throwable> T expectThrows(
            Class<T> type, Runnable action) {
        try {
            action.run();
        } catch (Throwable error) {
            if (type.isInstance(error)) {
                return type.cast(error);
            }
            throw new AssertionError("Wrong exception: " + error, error);
        }
        throw new AssertionError("Expected " + type.getSimpleName());
    }

    public static void main(String[] args) {
        IllegalArgumentException misleading =
                expectThrows(IllegalArgumentException.class, () -> {
                    OrderLine line = arrange("", -2);
                    calculate(line);
                });
        System.out.println("BROAD_SCOPE: " + misleading.getMessage());

        try {
            arrange("", -2);
            throw new AssertionError("Setup should fail");
        } catch (IllegalArgumentException error) {
            System.out.println("SETUP_FAILED: " + error.getMessage());
        }

        OrderLine validFixture = arrange("SKU-1", -2);
        IllegalArgumentException expected =
                expectThrows(IllegalArgumentException.class,
                        () -> calculate(validFixture));
        if (!"sut: quantity is negative".equals(expected.getMessage())) {
            throw new AssertionError("Wrong failure origin");
        }
        System.out.println("ACT_FAILED: " + expected.getMessage());

        OrderLine normalFixture = arrange("SKU-1", 3);
        int total = calculate(normalFixture);
        if (total != 30) {
            throw new AssertionError("Unexpected total");
        }
        System.out.println("SUCCESS_TOTAL: " + total);
        System.out.println("CHECKS: PASS");
    }
}
```

Commands to run in the directory containing the file:

```bash
javac -encoding UTF-8 TestBoundaryDemo.java
java TestBoundaryDemo
```

**Verified standard output:**

```text
BROAD_SCOPE: fixture: sku is blank
SETUP_FAILED: fixture: sku is blank
ACT_FAILED: sut: quantity is negative
SUCCESS_TOTAL: 30
CHECKS: PASS
```

### Interpreting the output

1. `BROAD_SCOPE` prints **fixture: sku is blank**, not the quantity error from `calculate`. Overly broad lambda scoping hid the true error source.
2. `SETUP_FAILED` illustrates that separating Arrange makes a setup error visible as a distinct failure, not the behavior under test.
3. `validFixture` has a valid SKU but a negative quantity. **Negative quantity is the deliberate input for SUT validation**, not a builder error; therefore Arrange does not throw.
4. `ACT_FAILED` occurs only because `calculate` throws. Checking the message here is meant to clearly distinguish fixture vs. SUT in the demo.
5. `SUCCESS_TOTAL` confirms that the normal processing path returns `30`.
6. `expectThrows` catches `Throwable` in an **illustrative test harness** to inspect the thrown `Throwable` type and turn mismatches into `AssertionError`. This is not advice to add broad `catch(Throwable)` blocks in production code.

In real applications, use your testing framework's assertions; JUnit's `assertThrows` already provides full failure reporting and supports custom messages.

## 5. Recommended JUnit 5 pattern

For the test "negative quantity must be rejected," separate clearly:

```java
@Test
void rejectsNegativeQuantity() {
    // Arrange: valid SKU; negative quantity is the input under test.
    OrderLine line = new OrderLine("SKU-1", -2);

    // Act + assert exception: contains only the SUT call.
    IllegalArgumentException error = assertThrows(
            IllegalArgumentException.class,
            () -> service.calculate(line));

    // Additional Assert: prove the right reason.
    assertEquals("QUANTITY_NEGATIVE", error.getMessage());
}
```

This is a **JUnit 5 snippet**; it will not compile standalone without `OrderLine`, `service`, the `@Test` import, and static assertion imports. The string `QUANTITY_NEGATIVE` assumes a **stable application-defined error code**; do not mix it with the message from `TestBoundaryDemo` above, as those are two independent examples with different contracts.

If the test builder validates the SKU, build the fixture right before `assertThrows`:

```java
OrderLine line = fixtureBuilder()
        .sku("SKU-1")
        .quantity(-2)
        .build();

IllegalArgumentException error = assertThrows(
        IllegalArgumentException.class,
        () -> service.calculate(line));
```

If `build()` throws, JUnit reports a failure from Arrange; it is **not** treated as the expected exception for `service.calculate`. This is also an illustrative snippet requiring the builder and SUT to be declared.

### `assertThrows` vs. `assertThrowsExactly`

- `assertThrows(Expected.class, executable)` accepts `Expected` **or any subtype**.
- `assertThrowsExactly(Expected.class, executable)` requires the exact runtime class `Expected`, as supported by the JUnit Jupiter API.
- Choose "exact" when subtype differences matter to the error contract; avoid overusing it when subclasses are valid.

Neither method **automatically verifies the origin of the exception**. The lambda must be properly scoped, and when needed you should assert the error code, cause, or interactions.

## 6. When to use `assertDoesNotThrow` for Arrange?

Sometimes you want to make explicit that the setup step **must not fail**:

```java
OrderLine fixture = assertDoesNotThrow(
        () -> fixtures.createValidOrderLine("SKU-1", -2),
        "Fixture setup must succeed");

IllegalArgumentException error = assertThrows(
        IllegalArgumentException.class,
        () -> service.calculate(fixture));
```

This is an illustrative JUnit 5 and application-API snippet. `assertDoesNotThrow` can make a "setup failed" message stand out more clearly instead of letting the exception appear as an ordinary failure. **It is optional:** if Arrange code is simple, calling the fixture helper directly outside `assertThrows` is usually clearer and involves less wrapper noise.

Do not wrap the entire test body in `assertDoesNotThrow` and then check another exception; the goal is phase separation, not adding assertions around every line.

Important: a setup helper may intentionally reject an invalid fixture. If so, choose a fixture that matches your intent; do not force the helper to skip validation or swallow errors just to get past Arrange.

## 7. Valid input for setup vs. invalid input for the SUT

A common source of confusion:

- You want to test that the SUT rejects a **negative quantity**.
- The fixture builder also validates that **quantity must not be negative**.
- When calling the builder, an exception is thrown early and never reaches the SUT.

If the builder truly guarantees it only constructs valid objects, you need to decide on a testing strategy:

1. Test the input through a SUT API **upstream of the builder's validation**, such as calling a service that accepts an unvalidated DTO/request.
2. Use a test value object that can represent the invalid state at the exact boundary under test, if the architecture allows it.
3. If the invalid state **cannot exist according to the contract**, asking "how does the SUT handle a negative quantity in an already-validated object" may be testing behavior unreachable via the public API. Adjust the test goal rather than using reflection or breaking invariants arbitrarily.
4. If the builder itself owns that validation, move the exception test to the builder instead of claiming to test the service.

**"Valid fixture"** here means it is constructed **successfully** and satisfies the other preconditions of the test, not necessarily that every field is valid according to the rule the SUT is supposed to check. Make explicit which layer owns each validation rule.

## 8. Verifying the SUT was actually invoked

Scoping `assertThrows` is the first line of defense. In some complex cases you also need to verify **interactions**:

```java
Order input = validOrderFixture();

IllegalStateException error = assertThrows(
        IllegalStateException.class,
        () -> service.submit(input));

verify(repository).save(input);
```

This is a **JUnit + Mockito snippet** assuming `service`, `repository`, and `verify` are configured. Only add verification if it **truly belongs to the contract under test**. For example, if business rules require validation **before** writing to the repository, then a validation-failure test should instead assert `verifyNoInteractions(repository)` or `verify(repository, never()).save(any())`, depending on the goal.

Do not lock down every implementation detail with mock verifications; tests become brittle under refactoring even when behavior is unchanged. The primary guarantee is usually **a narrow Act scope + contract-compliant state/exception**. Verification is supplementary evidence when meaningful.

If a mock is configured to throw the exact exception type you expect, distinguish between testing **how the SUT translates/propagates a dependency error** versus accidentally testing only **that the mock throws**. A meaningful test must prove the SUT's policy (e.g., error translation, valid fallback, rollback, or state recording), not merely that a stub can throw an exception.

## 9. Do not put assertions inside a lambda expecting a SUT exception

Incorrect:

```java
assertThrows(AssertionError.class, () -> {
    Result result = sut.execute();
    assertEquals("OK", result.status());
});
```

This is a JUnit snippet **intentionally illustrating a design mistake**. The test proves that some assertion failed, but it can accidentally "pass" because a test assertion errored rather than because the SUT behaved properly. Even when testing a custom assertion utility itself, name and scope the test clearly.

For a normal business test:

```java
Result result = sut.execute();
assertEquals("OK", result.status());
```

Or when expecting an error from the SUT:

```java
BusinessException ex = assertThrows(
        BusinessException.class,
        () -> sut.execute());
assertEquals(ErrorCode.CONFLICT, ex.code());
```

These are illustrative snippets with application types/enums defined. **Do not merge multiple phases into a single lambda** when merging can obscure the source of an exception.

## 10. Failures in `@BeforeEach` and `@BeforeAll`

JUnit Jupiter provides lifecycle callbacks:

- `@BeforeAll`: prepares shared resources/state according to the test class lifecycle configuration.
- `@BeforeEach`: prepares state before each test.
- `@Test`: test body containing Act and Assert.
- `@AfterEach` and `@AfterAll`: cleanup.

Example:

```java
@BeforeEach
void setup() {
    order = fixtureFactory.createOrder(); // May fail.
}

@Test
void rejectsNegativeQuantity() {
    assertThrows(IllegalArgumentException.class,
            () -> service.calculate(order));
}
```

This is a **JUnit 5 snippet** requiring fields `order`, `service`, `fixtureFactory`, and imports. If `setup()` throws `IllegalArgumentException`, **the test method is never executed**. JUnit records the failure in lifecycle setup; `assertThrows` inside the test method never gets a chance to prove SUT behavior.

This is a benefit of lifecycle separation, though it creates risk if errors are masked:

```java
@BeforeEach
void setup() {
    try {
        order = fixtureFactory.createOrder();
    } catch (Exception ignored) {
        order = null;
    }
}
```

This is an **anti-pattern**: the setup error is swallowed, and the test later fails with an NPE or an unrelated error deeper down. It is better to let setup fail **at the right place**.

A few notes:
- Put only **truly shared setup** in `@BeforeEach`; test-specific fixtures belong inside the test for readability.
- Avoid unnecessary global side effects in `@BeforeAll`, as a failure there can affect many tests in the same class.
- Use reliable cleanup for resources; failures in `@AfterEach` should be treated as a separate issue.
- Shared state across tests can cause flaky failures during parallel runs; prefer isolation.

## 11. Teardown failures differ from Act failures

A test may complete the SUT call and assertions successfully, yet `@AfterEach` or a `close()` call throws an exception. That does not mean the production behavior under test failed in the same way.

Example:

```java
@Test
void processesOrder() throws Exception {
    try (TestDatabase db = startDatabase()) {
        Result result = sut.process(db);
        assertEquals(Result.SUCCESS, result);
    }
}
```

This is a **design snippet**, requiring `TestDatabase` to implement `AutoCloseable`, `Result`, and application APIs. When the body fails and `db.close()` also fails, try-with-resources preserves the **body exception** as the primary exception and attaches the close error in `getSuppressed()`. If the body succeeds but close fails, the close error is reported as primary.

Therefore, when analyzing a test stack trace:
- Check whether the primary exception came from Arrange, Act, Assert, or cleanup.
- Inspect `getSuppressed()` when multiple errors occur.
- Do not modify the SUT to "make the test pass" when the failure is container teardown or connection cleanup.
- Do not blindly swallow cleanup exceptions; resource leaks between tests can cause later failures.

Conversely, a SUT error must not disappear just because cleanup also failed. `try-with-resources` helps preserve that information.

## 12. Mocks/stubs: test configuration errors and SUT errors can share the same type

A test might use Mockito:

```java
when(repository.load("A")).thenReturn(null);
assertThrows(NullPointerException.class,
        () -> service.process("A"));
```

This is a JUnit/Mockito snippet. A `NullPointerException` could be a bug in the SUT or simply the result of a mock returning `null` in violation of its contract. For the test to be useful, identify **which failure is expected**:
- If you are testing how the SUT handles a dependency returning empty/missing data, assert the proper business error code or fallback instead of blindly expecting an NPE.
- If you are testing that the SUT rejects a `null` input, construct that input separately from mock setup.
- If a mock returns `null` because a stub is missing, fix the fixture rather than rushing to change production logic.
- If a `when(...)` or `thenAnswer(...)` callback throws, it may happen during Arrange when configuring the mock, or during Act depending on execution timing.

An important rule: **a mock should simulate a dependency with a clear contract**, not arbitrarily make the dependency "do anything" just to force an exception.

## 13. Multi-step test fixtures: make phases explicit

In integration tests, Arrange may include creating a schema, seeding data, fetching a test token, configuring an HTTP client, opening a transaction, and building a request. If all of this is hidden inside a single "magic" helper, setup failures become very hard to diagnose.

You can break Arrange into named steps:

```java
TestDatabase db = startTestDatabase();
Customer customer = seedCustomer(db, "fixture-001");
Request request = newRequest(customer.id());

Response response = application.handle(request);

assertEquals(409, response.status());
```

This is an integration test snippet requiring application APIs to be defined. If `seedCustomer` fails due to a duplicate key or DB connection error, the test fails **before Act**; do not conflate that with the application returning 409. Each step should only create data needed for the scenario.

When a test has multiple failure branches, label them clearly with helpers/variable names, but avoid masking every error behind an overly generic custom exception like "test failed." If you wrap a setup error, preserve its cause:

```java
try {
    seedData();
} catch (SQLException ex) {
    throw new TestSetupException("Cannot seed test database", ex);
}
```

This snippet requires a custom `TestSetupException` and importing `java.sql.SQLException`. Wrapping like this is helpful at complex setup boundaries; avoid wrapping every tiny call or putting passwords/connection strings in the message.

## 14. Parameterized tests and data-provider errors

In JUnit 5, inputs often come from `@MethodSource`, `@CsvSource`, or other parameter sources. If the data-provider method throws an exception while generating arguments, **the test invocation has not yet been formed or has not executed Act as intended**.

Example:

```java
static Stream<Arguments> cases() {
    return Stream.of(
            Arguments.of("SKU-1", -1),
            Arguments.of("SKU-2", -2));
}

@ParameterizedTest
@MethodSource("cases")
void rejectsNegativeQuantity(String sku, int quantity) {
    OrderLine line = new OrderLine(sku, quantity);
    assertThrows(IllegalArgumentException.class,
            () -> service.calculate(line));
}
```

This is a JUnit Jupiter Parameterized Tests snippet requiring `junit-jupiter-params`, imports for `Stream` and `Arguments`, and application classes/fields. If `cases()` computes data using a helper that can fail, an error in the **data source** is different from an error in `service.calculate`.

Recommendations:
1. Use simple, named, easy-to-inspect arguments whenever possible.
2. If the data source depends on IO/DB, consider moving it into an integration fixture instead of triggering hard-to-diagnose side effects inside an annotation source.
3. Give invocations clear names so you can tell which input set failed.
4. Do not let an empty or invalid data source create the illusion that the entire requirement was tested.

Do not wrap `cases()` itself in `assertThrows` inside a service behavior test unless your goal is specifically to test the data source.

## 15. Cascading exceptions: primary vs. secondary failures

When setup, SUT, and teardown all fail, which exception the test reports depends on **the execution path and testing mechanism**:

- If Arrange throws, Act does not run.
- If Act throws, subsequent assertions in the same method usually do not run.
- If Arrange and Act succeed but Assert throws `AssertionError`, that is a verification failure.
- If cleanup throws after an earlier error, `try-with-resources` can record the cleanup error in `getSuppressed()`.
- If `finally` throws an exception without preserving the prior error, it can mask the original failure.
- JUnit extensions/lifecycle callbacks may report additional errors; how a runner formats multiple failures should not replace analyzing the stack trace and error origin.

**Do not look only at the exception class name.** An `IllegalArgumentException` from a fixture builder and an `IllegalArgumentException` from the SUT may share the same type yet have different causes. Messages, call stacks, error codes, origins, and preconditions help classify them.

If you need a stable failure contract to assert against, the application should use **domain exceptions or error codes** rather than matching library/JDK message strings that may change.

## 16. Verifying where an error occurred using markers when needed

In a complex test, you sometimes need to prove that Act actually started or that a dependency call occurred. You can use a controlled counter/test spy:

```java
AtomicInteger invocationCount = new AtomicInteger();
Sut sut = new Sut(() -> {
    invocationCount.incrementAndGet();
    throw new DomainException("DEPENDENCY_FAILED");
});

DomainException error = assertThrows(
        DomainException.class,
        sut::execute);

assertEquals(1, invocationCount.get());
```

This is a **design snippet**, not standalone; it requires `Sut`, `DomainException`, `AtomicInteger`, imports, and the constructor API shown. If Arrange fails before `assertThrows`, the counter will not be checked as a successful Act. When Act runs, the counter confirms that the expected call path was traversed.

Do not scatter markers throughout production code just for testing. Prefer purpose-built test spies/mocks and assert important state/interactions. Likewise, if the SUT is designed **not to call a dependency when input is invalid**, asserting a count of `0` is the right check.

## 17. Asynchronous code: SUT errors may occur after the initial Act

With `CompletableFuture` or `ExecutorService`, the Act call may only **start the work** and return a `Future`. An exception thrown later on a worker thread is not automatically caught by `assertThrows` around the submit/schedule call:

```java
CompletableFuture<String> future = sut.loadAsync(request);

CompletionException error = assertThrows(
        CompletionException.class,
        future::join);

assertInstanceOf(DependencyException.class, error.getCause());
```

This is a JUnit 5 snippet with SUT and application types. **Arrange** builds `request`, **Act** calls `sut.loadAsync`, and **Assert** observes the stage via `join`. `CompletionException` is the typical wrapper from `join()` when a future completes exceptionally; on cancellation, it may throw `CancellationException` directly. `Future.get()` uses `ExecutionException` and can throw `InterruptedException` on the waiting caller.

When setting up an async mock, be clear whether it throws **immediately during configuration**, throws **synchronously when Act calls it**, or returns a future that completes exceptionally **after Act**. You cannot wrap all steps in one `assertThrows` and conclude you tested the callback properly.

Avoid using `Thread.sleep` as the sole way to wait for async errors: tests become flaky. Use future completion, latches, controlled executors, and appropriate timeouts. If the caller is interrupted during `get()`, that is a failure of **the test's waiting path** unless cancellation/interruption is the scenario under test.

## 18. Expecting an exception does not mean accepting any Throwable

`assertThrows(Exception.class, ...)` or `assertThrows(RuntimeException.class, ...)` is too broad and can create similar false positives, even when wrapping only Act. For example, if you want to test a validation error and the SUT has a `NullPointerException` bug, expecting only `RuntimeException` will still let the bug pass the test.

Prefer:

- An exception type specific enough for the contract, such as `InvalidOrderException` or `IllegalArgumentException` when appropriate.
- `assertThrowsExactly` when a different subclass would violate the contract.
- Stable error codes or additional properties, rather than over-relying on exact SDK/JDK messages.
- Post-exception state/interaction checks, such as verifying the database was not written when validation failed.
- For retries/cancellation, asserting the exact invocation count and final state.

Avoid `assertThrows(Throwable.class, ...)` for normal business tests: it can treat `AssertionError` or other serious errors as a false "success." Some test-framework internals have reasons to catch `Throwable` to record test failures, but that is **not an appropriate assertion pattern** for application tests.

## 19. Test setup should not be made to "always succeed" by swallowing errors

An anti-pattern:

```java
OrderLine prepare() {
    try {
        return fixtureFactory.create();
    } catch (Exception ignored) {
        return null;
    }
}
```

This snippet assumes an application-defined factory. It turns a fixture error into `null`, causing Act or Assert to throw `NullPointerException` far from the real root cause.

How to fix:
- Preserve the original setup exception, or wrap it with its cause and a message **that contains no sensitive data**.
- Keep fixtures small with clear preconditions, and test helpers separately if they are complex.
- Isolate test databases/fixtures from unnecessary network or time dependencies.
- Do not use `assumeTrue` assumptions to automatically skip every setup error; tests may become **aborted/skipped** instead of exposing broken configuration.
- For truly optional external dependencies, define a clear integration-test policy and environment conditions; never disguise broken setup as a passing test.

A test whose setup succeeds does not guarantee the SUT works; conversely, a setup failure must always be investigated before concluding the SUT has a bug.

## 20. Matrix of test scenarios and expected outcomes

| Scenario | Failure point | Expected outcome |
| --- | --- | --- |
| Builder has invalid SKU, SUT never called | Arrange | Test reports a setup error, does not pass as a SUT exception |
| Builder valid, SUT rejects negative quantity | Act | `assertThrows` catches the expected domain exception |
| Builder valid, SUT throws unexpected NPE | Act | Test expecting specific validation must FAIL |
| SUT succeeds, expected assertion differs from actual | Assert | Failure due to assertion, not mistaken for a SUT exception |
| `@BeforeEach` cannot connect to test DB | Lifecycle Arrange | Reports setup/lifecycle failure; does not claim SUT ran |
| `@MethodSource` generates bad data | Parameter source | Reports data-source error, not an Act failure |
| Mock config fails before test body | Arrange | Test fails in setup, not swallowed |
| Stub throws expected exception type, but SUT skips policy | Act | Verify mapping/fallback/state, not only exception type |
| Future fails after submit | Async completion | Observe `join()`/`get()` and cause |
| Cleanup throws after Assert passes | Teardown | Test may fail due to cleanup; classify accurately |
| Both Act and `close()` fail | Act + Cleanup | Inspect primary exception and `getSuppressed()` |
| Setup helper swallows exception and returns null | Arrange | Fix helper; do not "patch NPE" in SUT when source is fixture |

This matrix is useful for test reviews and flaky-test triage. The goal is to prove **the behavior of the exact component under test**, not just turn an assertion green.

## 21. Checklist before accepting an exception test

1. The test name describes the **SUT** behavior, not just the exception class name.
2. Arrange and Act live in clearly identifiable code blocks.
3. `assertThrows` wraps only the operation expected to throw, excluding unrelated constructors or fixture helpers.
4. The fixture is built successfully and contains abnormal values **only intentionally for the SUT to check**.
5. The expected exception type is specific enough; when needed, assert stable error codes/causes/attributes.
6. The test verifies that the SUT performed—or **did not perform**—important side effects.
7. Errors in `@BeforeEach`/`@BeforeAll`, data providers, or mock setup are not swallowed.
8. Cleanup/teardown errors are distinguished from Act failures; inspect suppressed exceptions when appropriate.
9. Async tests distinguish synchronous errors at submit time from later exceptional completion.
10. Broad `catch(Exception)` or `assertThrows(Throwable.class)` is not used to "make tests green."
11. When a test fails, the stack trace indicates the **phase** and **error origin**; do not change production code merely because the same exception type appeared.
12. For integration tests, test data, transactions, and dependencies are isolated, with proper cleanup and timeouts.

**Takeaway:** a passing `assertThrows` only proves **a matching exception occurred somewhere inside the lambda**—not that **the exact code under test** threw it. To keep tests trustworthy, separate Arrange from Act, build fixtures intentionally, narrow the expected-exception scope, and verify behavior against the contract.
