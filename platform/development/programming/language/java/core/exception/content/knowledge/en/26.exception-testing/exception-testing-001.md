# Contract-Based Testing of Success and Failure Paths in Java

A Java method does not only have a *happy path*; its contract also specifies what happens when input is invalid, resources are missing, I/O fails, or an asynchronous operation fails. If tests only check "callable and returns the right result", bugs such as throwing the wrong exception type, losing `cause`, accidentally swallowing errors, or leaving partial state can easily slip into production.

This lesson belongs to **Java Core – Exception / Testing**, targeting **Java 17+**. The goal is to write tests that verify **the exact contract** on both paths: return values and side effects on success; error type, important details, cause/suppressed exceptions, and post-error state on failure. The standalone Java programs below compile and run directly with `javac`/`java`; the JUnit 5 sections are explicitly noted as examples using a testing library.

## 1. A Method's Contract Is More Than Its Return Type

Consider the API:

```java
int calculateTotal(int unitPrice, int quantity)
```

Such a signature does not tell the whole contract. The application must decide:

- **Valid input conditions:** for example `unitPrice >= 0`, `quantity > 0`.
- **Success result:** how the total is calculated; is there an overflow limit?
- **Failure conditions:** invalid input; result out of bounds; dependency failure.
- **Error type:** `IllegalArgumentException`, `ArithmeticException`, `IOException`, business exceptions...
- **Error information:** which message or error code is a stable part of the API?
- **State after failure:** was data partially updated, a lock held, a resource left open, or an external request already sent?
- **Special signals:** cancellation, interrupt, or timeout if the API supports them.
- **Order and scope of side effects:** which conditions must be checked *before* mutating state?

A good test is not one that makes existing code "green" at all costs. It must verify the code against the **intended contract** defined independently.

Illustrative comparison:

| Scenario | Input/Setup | What to verify |
|---|---|---|
| Typical success | `unitPrice=100`, `quantity=2` | Returns `200`, does not throw |
| Success at valid boundary | `unitPrice=0`, `quantity=1` | Returns `0` if the contract allows it |
| Failure due to quantity | `quantity=0` | Throws `IllegalArgumentException` |
| Failure due to price | `unitPrice=-1` | Throws the specified error type |
| Overflow | `unitPrice=Integer.MAX_VALUE`, `quantity=2` | Does not silently return a wrong value; reports an error per policy |
| Dependency failure | Fake data store throws `IOException` | Preserves/transforms the exception per contract, does not report success |
| Cleanup failure | Work body and `close()` both throw | Primary error is preserved, close error is in `Suppressed` if using TWR |

**Testing both paths does not necessarily mean a 50/50 case split.** The number of tests should follow **the branches and guarantees of the API**, especially high-risk boundaries.

## 2. Success Path: What Needs to Be Asserted?

Happy-path tests must **assert the outcome**, not just "no exception occurred". Depending on the method, check:

1. Return value or produced data.
2. Object state after the operation.
3. Expected side effects: persisting data, incrementing counters, invoking dependencies.
4. Side effects that **must not happen**: no duplicate writes, no unnecessary fallback calls.
5. Immutability of objects/inputs if specified by the contract.
6. Resources closed or ownership transferred at the right boundary.

Example of a test that is too weak:

```java
service.createOrder(validRequest);
```

This is only an illustrative snippet. It does not prove the order was created with the right amount or saved. The test needs to read the result or inspect observable state:

```java
Order order = service.createOrder(validRequest);
assertEquals(expectedTotal, order.total());
```

This is a **JUnit integration example**, assuming types `service`, `Order`, `validRequest`, and `expectedTotal` are already defined and `assertEquals` is imported from JUnit. In real tests, verify important state instead of repeating the exact same algorithm in the expected value; if the same wrong formula is written in both production and test, the test can still pass.

A useful rule of thumb: **each assertion should answer one guarantee of the contract**. Do not assert every internal implementation detail, because a valid refactoring must still preserve the public contract.

## 3. Failure Path: Checking More Than Just That an Exception Exists

On the failure path, verification layers typically include:

- **Exception type:** the API must throw the promised type, not an accidental `NullPointerException` caused by a bug.
- **Message or error code:** only check the stable part that is meaningful to callers.
- **Cause:** when a higher layer wraps an exception, is the original error still in `getCause()`?
- **Suppressed:** if cleanup also fails, is the secondary error preserved?
- **No false success result:** do not return a default value that makes the caller think the operation succeeded.
- **No forbidden side effects:** failed validation must not deduct money, write partial data, or transition to an invalid state.
- **Resources released:** `close`, `unlock`, rollback, or release according to the contract.
- **Error occurs only in the right scope:** do not let an exception from another dependency accidentally make the test "pass".

Example of a weak test:

```java
assertThrows(Exception.class, () -> repository.load("bad-id"));
```

This snippet is JUnit 5 syntax, not a standalone runnable program. It can accept many unintended errors. If the contract only allows `IllegalArgumentException` when the input ID is invalid, use:

```java
IllegalArgumentException error = assertThrows(
        IllegalArgumentException.class,
        () -> repository.load("bad-id"));
```

Then check the important message/error code and, if there is state, verify that the state was not modified.

JUnit 5's `assertThrows(Expected.class, executable)` also accepts **subclasses of the expected type**. When the contract strictly requires one exact class, consider `assertThrowsExactly` (if your JUnit version supports it) or compare `error.getClass()`.

## 4. Standalone Java 17 Example: Testing Input and Result Contracts

Create the file `PriceContractTest.java`. This is a pure JDK test suite with `main`, requiring no JUnit.

```java
public class PriceContractTest {
    static int total(int price, int quantity) {
        if (price < 0) {
            throw new IllegalArgumentException("price must be >= 0");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be > 0");
        }
        return Math.multiplyExact(price, quantity);
    }

    static void check(boolean condition, String description) {
        if (!condition) {
            throw new AssertionError(description);
        }
    }

    static void expectIllegalArgument(
            Runnable action, String expectedMessage) {
        try {
            action.run();
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException e) {
            check(expectedMessage.equals(e.getMessage()),
                    "Wrong message: " + e.getMessage());
        }
    }

    public static void main(String[] args) {
        check(total(100, 2) == 200, "Wrong normal total");
        System.out.println("success: normal");

        check(total(0, 1) == 0, "Wrong boundary total");
        System.out.println("success: boundary");

        expectIllegalArgument(() -> total(-1, 2),
                "price must be >= 0");
        System.out.println("failure: negative price");

        expectIllegalArgument(() -> total(10, 0),
                "quantity must be > 0");
        System.out.println("failure: invalid quantity");

        try {
            total(Integer.MAX_VALUE, 2);
            throw new AssertionError("Expected ArithmeticException");
        } catch (ArithmeticException expected) {
            System.out.println("failure: overflow");
        }
    }
}
```

Compile and run:

```bash
javac PriceContractTest.java
java PriceContractTest
```

Output:

```text
success: normal
success: boundary
failure: negative price
failure: invalid quantity
failure: overflow
```

How the test works:

- The two success cases verify **concrete results**.
- The two invalid-input cases verify the exact **error type** and message specified by the API itself.
- `Math.multiplyExact` detects overflow, allowing the test to confirm an error instead of silently receiving a wrong number.
- `check` throws `AssertionError` if an invariant is violated. This is an **actively checked** test suite and does not depend on running the JVM with the `-ea` flag.
- In `expectIllegalArgument`, if the method does not throw, the program throws `AssertionError`; it is **not accidentally caught** by `catch (IllegalArgumentException)`.

Note: Java's `assert` statement can be disabled by default if `-ea` is not used. For a standalone `main` test suite like this, `if (!condition) throw new AssertionError(...)` ensures the test always performs assertions. When using JUnit, JUnit assertions do not depend on the `-ea` flag.

## 5. Choosing Representative Values: Normal, Boundary, and Invalid

Success/failure tests should be designed using **equivalence partitioning** and **boundary value analysis**.

For the rule `quantity > 0`:

| Group | Example Input | Expectation |
|---|---:|---|
| Smallest valid value | `1` | Success |
| Common valid value | `5` | Success |
| Boundary just outside valid range | `0` | `IllegalArgumentException` |
| Negative value | `-1` | `IllegalArgumentException` |
| Very large positive value | `Integer.MAX_VALUE` | Per calculation limits and overflow behavior |

For a `String` that must be non-`null` and non-blank, distinguish:

- `null`: null error per contract.
- `""`: empty string.
- `"   "`: whitespace only.
- `"A"`: minimal valid value.
- `" A "`: whether it is trimmed/normalized depends on the contract.
- Unicode characters: handle according to actual requirements, do not assume ASCII-only.

Do not invent expectations without defining the policy first. Some APIs allow empty strings but forbid `null`, some allow `0`, and some treat "not found" as `Optional.empty()` rather than an exception. Tests must **reflect published guarantees**, not apply one generic error type to every API.

## 6. With JUnit 5: Writing Clear Success and Failure Tests

JUnit Jupiter is a common tool for organizing Java unit tests. The examples in this section **require the appropriate JUnit Jupiter dependencies and a Maven/Gradle/IDE test runner**; they are not files that can run with plain `javac` alone.

Suppose the production file is `PricePolicy.java`:

```java
public final class PricePolicy {
    public int total(int price, int quantity) {
        if (price < 0) {
            throw new IllegalArgumentException("price must be >= 0");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be > 0");
        }
        return Math.multiplyExact(price, quantity);
    }
}
```

Test file `PricePolicyTest.java`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class PricePolicyTest {
    private final PricePolicy policy = new PricePolicy();

    @Test
    void returnsTotalForValidInput() {
        int result = assertDoesNotThrow(() -> policy.total(100, 2));
        assertEquals(200, result);
    }

    @Test
    void acceptsMinimumValidQuantity() {
        assertEquals(0, policy.total(0, 1));
    }

    @Test
    void rejectsNegativePrice() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> policy.total(-1, 2));

        assertEquals("price must be >= 0", error.getMessage());
    }

    @Test
    void rejectsZeroQuantity() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> policy.total(10, 0));

        assertEquals("quantity must be > 0", error.getMessage());
    }

    @Test
    void detectsOverflow() {
        assertThrows(ArithmeticException.class,
                () -> policy.total(Integer.MAX_VALUE, 2));
    }
}
```

Analysis:

- `assertDoesNotThrow(...)` makes the expectation of no exception explicit; **you still must assert the return value**. Merely "not throwing" is not enough to prove the calculation contract.
- `assertThrows` only passes if the executable **actually throws a matching exception**.
- The test captures the `error` object itself, allowing it to inspect the message/cause/suppressed exceptions or error code.
- Each test has a name describing the scenario and expectation. If a test fails, the method name helps quickly identify the violated guarantee.

Execution in a Maven project typically uses `mvn test`; in a Gradle project configured with JUnit Platform, it is `gradle test` or `./gradlew test`. These commands require a project with a build file, JUnit dependencies, and appropriate test configuration. Do not run JUnit files with `java PricePolicyTest` like the `main`-based examples.

**You do not need to add `assertDoesNotThrow` to every happy-path test**: a call that throws an unexpected exception will normally fail a JUnit test anyway. Use it when it makes the contract clearer or when capturing a result inside a lambda.

## 7. Exception Type: When to Check Subtypes, When to Check Exact Class?

Suppose the contract states "throws `IllegalArgumentException` if input is invalid". `assertThrows(IllegalArgumentException.class, ...)` accepts subclasses, which fits if the contract allows custom subclasses.

If the contract specifies **one exact error type**, you can use:

```java
IllegalArgumentException error = assertThrowsExactly(
        IllegalArgumentException.class,
        () -> policy.total(-1, 1));
```

This is a **JUnit snippet**; it requires importing `assertThrowsExactly` and having `policy` defined. You can use `assertEquals(IllegalArgumentException.class, error.getClass())` if an exact check is needed after `assertThrows`.

Do not test too narrowly if a public library allows a family of exceptions. For example, a JDBC or HTTP client contract may promise a base checked exception or a driver-specific subclass; a test enforcing an exact implementation class can break on a dependency upgrade even though public behavior remains valid.

Conversely, do not test too broadly:

```java
assertThrows(RuntimeException.class, () -> parse("not-a-number"));
```

This statement can pass because of an unexpected `NullPointerException` in the implementation. If the contract specifies `NumberFormatException` or `IllegalArgumentException`, test accordingly. When seeing an unfamiliar exception, determine whether it is the **expected error** or a bug accidentally accepted by the test.

## 8. Message and Error Code: What Is Worth Locking Down in Tests?

Exception messages are usually meant for human diagnostics. Some parts are worth testing:

- Stable error codes, such as `E_INVALID_QUANTITY`.
- Constraint or invalid field names if specified by the public contract.
- Important safe values that help the caller understand the error.
- The exact message **if it is published as part of the API**.

Do not by default check **character-by-character** messages generated by the JDK, drivers, or external libraries. Messages can change across JDK versions, locales, drivers, formatting updates, or dependency upgrades. For example, asserting the verbatim text of a JDK `NumberFormatException` message easily creates brittle tests when the API never promised that format.

Illustrative JUnit example:

```java
IllegalArgumentException error = assertThrows(
        IllegalArgumentException.class,
        () -> service.applyQuantity(-1));

assertTrue(error.getMessage().contains("quantity"));
```

This is an integration snippet requiring `service` and imports for `assertTrue` and `assertThrows`. `contains("quantity")` is only appropriate when the contract actually requires that information; it is not automatically a better check in all cases.

If the application needs machine-readable errors, prefer **exception classes, enum error codes, or dedicated fields** rather than forcing callers to parse messages. Testing stable error codes is generally more resilient than testing prose that might be localized.

## 9. Verifying the Cause Chain with `getCause()`

A service may wrap a low-level error into a meaningful business-layer exception:

```java
try {
    return repository.load(id);
} catch (IOException e) {
    throw new IllegalStateException("Không tải được hồ sơ", e);
}
```

This is an **illustrative code snippet** inside a method where the variables are defined. The failure contract may require:

1. The caller receives `IllegalStateException`.
2. The wrapper's message conveys the profile-loading context.
3. `getCause()` is still the `IOException`, preserving the underlying cause.
4. No false success result is returned.
5. No duplicate logging at every layer; the top-level handler handles logging per policy.

### Standalone Java 17 program: verifying cause and success case

File `CauseContractTest.java`:

```java
import java.io.IOException;

public class CauseContractTest {
    @FunctionalInterface
    interface Repository {
        String read() throws IOException;
    }

    static String load(Repository repository) {
        try {
            return repository.read();
        } catch (IOException e) {
            throw new IllegalStateException("load failed", e);
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        check("OK".equals(load(() -> "OK")), "Success path failed");
        System.out.println("success = OK");

        IOException root = new IOException("disk offline");
        try {
            load(() -> {
                throw root;
            });
            throw new AssertionError("Expected IllegalStateException");
        } catch (IllegalStateException e) {
            check("load failed".equals(e.getMessage()),
                    "Wrong wrapper message");
            check(e.getCause() == root, "Original cause lost");
            System.out.println("outer = "
                    + e.getClass().getSimpleName());
            System.out.println("cause = "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Run:

```bash
javac CauseContractTest.java
java CauseContractTest
```

Output:

```text
success = OK
outer = IllegalStateException
cause = IOException
```

The dependency is replaced by a simple **fake** implementing the `Repository` interface, without needing a real database. The success path returns `"OK"`; the failure path throws **the exact `root` instance** to verify that the wrapper preserves its identity in `getCause()`.

Without checking the cause, a broken refactoring such as:

```java
throw new IllegalStateException("load failed");
```

could still pass tests for exception type and message while **losing the root cause**. That is why exception contract tests need more depth than `assertThrows`.

## 10. Verifying State and Side Effects After Failure

An API with side effects does not only promise to "throw the right exception". It may also promise:

- Validation runs **before** writing data.
- When a dependency fails, success counters do not increment.
- A failed transaction rolls back according to rules.
- Resources are closed even if the body throws an exception.
- A retry does not duplicate a transaction that already succeeded.

Pure Java example `MutationContractTest.java`:

```java
public class MutationContractTest {
    static final class Wallet {
        private int balance;

        Wallet(int initialBalance) {
            balance = initialBalance;
        }

        int balance() {
            return balance;
        }

        void debit(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("invalid amount");
            }
            if (amount > balance) {
                throw new IllegalStateException("insufficient funds");
            }
            balance -= amount;
        }
    }

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Wallet wallet = new Wallet(100);
        wallet.debit(40);
        check(wallet.balance() == 60, "Successful debit is wrong");
        System.out.println("success balance = " + wallet.balance());

        try {
            wallet.debit(-1);
            throw new AssertionError("Expected invalid amount");
        } catch (IllegalArgumentException expected) {
            check(wallet.balance() == 60,
                    "Balance changed after validation error");
            System.out.println("invalid balance = " + wallet.balance());
        }

        try {
            wallet.debit(70);
            throw new AssertionError("Expected insufficient funds");
        } catch (IllegalStateException expected) {
            check(wallet.balance() == 60,
                    "Balance changed after insufficient funds");
            System.out.println("insufficient balance = " + wallet.balance());
        }
    }
}
```

Run:

```bash
javac MutationContractTest.java
java MutationContractTest
```

Output:

```text
success balance = 60
invalid balance = 60
insufficient balance = 60
```

After the successful debit, the balance is 60. The two failed debits must **leave the balance unchanged**. If the implementation updates the balance before throwing, the test will fail even if the exception type is still correct.

This is a synchronous, in-memory example; it does **not** demonstrate how to build a real-world thread-safe e-wallet or guarantee cross-system transactions. For databases, use appropriate transaction boundaries and fixtures, testing both rollback and commit per contract.

## 11. Resource Cleanup: Checking Both Primary and `Suppressed`

An easily overlooked case is `try-with-resources`: the `try` body throws error A, and `close()` throws error B. In Java, **A is primary**, and B is attached to A via `getSuppressed()`. If the code is rewritten into a manual `finally` block incorrectly, B can **mask A**.

Standalone Java 17 file `ResourceExceptionContractTest.java`:

```java
import java.io.IOException;

public class ResourceExceptionContractTest {
    static final class Resource implements AutoCloseable {
        private final boolean failOnClose;

        Resource(boolean failOnClose) {
            this.failOnClose = failOnClose;
        }

        @Override
        public void close() throws IOException {
            if (failOnClose) {
                throw new IOException("close failed");
            }
        }
    }

    static String execute(boolean fail) throws Exception {
        try (Resource resource = new Resource(fail)) {
            if (fail) {
                throw new IllegalStateException("body failed");
            }
            return "completed";
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        check("completed".equals(execute(false)),
                "Expected successful result");
        System.out.println("success = completed");

        try {
            execute(true);
            throw new AssertionError("Expected primary exception");
        } catch (IllegalStateException e) {
            check("body failed".equals(e.getMessage()),
                    "Primary exception changed");

            Throwable[] suppressed = e.getSuppressed();
            check(suppressed.length == 1,
                    "Expected exactly one suppressed exception");
            check(suppressed[0] instanceof IOException,
                    "Expected IOException in suppressed");
            check("close failed".equals(suppressed[0].getMessage()),
                    "Wrong cleanup message");

            System.out.println("primary = " + e.getMessage());
            System.out.println("suppressed = "
                    + suppressed[0].getMessage());
        }
    }
}
```

Run:

```bash
javac ResourceExceptionContractTest.java
java ResourceExceptionContractTest
```

Output:

```text
success = completed
primary = body failed
suppressed = close failed
```

When `fail=false`, the work body succeeds and `close()` does not throw; the result is `"completed"`. When `fail=true`, both the work body and close fail. The test verifies that **the primary exception is not overwritten**, while the cleanup error is not lost.

Other cases worth testing if the API promises to manage multiple resources:

1. Body succeeds, `close()` fails: the cleanup exception becomes primary.
2. Body fails, multiple `close()` calls fail: multiple suppressed exceptions appear in reverse closing order.
3. Second resource constructor fails: the first resource must still be closed.
4. `try` body returns a value, but close fails: the caller sees the close error instead of the success result.
5. Manual cleanup helper throws an unchecked exception: precedence must be defined by the contract.

Do not only verify that `close()` was called using a mock; **if the contract requires preserving the primary exception**, checking cause/suppressed is what catches lost diagnostic data.

## 12. Checked Exceptions, Unchecked Exceptions, and Choosing Test Boundaries

Two error paths are often confused:

- **Checked exceptions**, such as `IOException`: the method must declare `throws` or catch them. Tests should verify that `IOException` is propagated or wrapped according to the contract.
- **Unchecked exceptions**, such as `IllegalArgumentException`, `IllegalStateException`: still need testing when the error type is part of the contract, even though the compiler does not require declaring them.

Do not treat checked exceptions as "important errors" and unchecked exceptions as mere bugs. An `IllegalArgumentException` can be an expected validation response; an `IOException` can come from a transient dependency issue; classify them by **business meaning**.

If the API specifies that an `IOException` from the repository must pass through the service, the test expects a checked exception. If the service intentionally converts it into a business exception with a cause, test both the wrapper and the cause. However, tests **should not invent wrapping rules** just for code consistency: they must follow the contract that callers actually rely on.

For an `Optional<T>` or `Result<T>` API, "not found" can be a **normal path** that does not throw an exception. In that case, the system's failure test may check `Optional.empty()` rather than `assertThrows`. Which conditions use exceptions must be decided at the API level before writing tests.

## 13. Exceptions from `Future` and `CompletableFuture`

When an asynchronous task fails, the exception type observed by the **caller** can differ from the error thrown by the **worker**:

- `Future.get()` typically throws `ExecutionException` if the task fails; the original error is in `getCause()`.
- `CompletableFuture.join()` typically throws `CompletionException` when a stage completes exceptionally; the cause is in `getCause()`.
- `CompletableFuture.get()` uses `ExecutionException` for normal exceptional completion.
- When the caller is waiting on `get()` and **the caller itself is interrupted**, it may receive `InterruptedException`; this alone does not mean the worker failed or was canceled.
- A canceled `Future` can cause `get()` to throw `CancellationException`; the canceled state does not guarantee the worker has finished cleaning up.
- A timeout in `get(timeout, unit)` can throw `TimeoutException` without automatically canceling the task.

Therefore, tests must **target the exact contract observed by the caller**, rather than confusing an `IOException` inside a `Callable` with an `IOException` thrown directly from `get()`.

### Standalone Java 17 example: completion paths of `CompletableFuture`

File `AsyncExceptionContractTest.java`:

```java
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CancellationException;

public class AsyncExceptionContractTest {
    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        CompletableFuture<String> success =
                CompletableFuture.completedFuture("ok")
                        .thenApply(String::toUpperCase);

        check("OK".equals(success.join()),
                "Wrong successful result");
        System.out.println("success = " + success.join());

        IOException root = new IOException("offline");
        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(root);

        try {
            failed.join();
            throw new AssertionError("Expected CompletionException");
        } catch (CompletionException e) {
            check(e.getCause() == root, "Cause was lost");
            System.out.println("cause = "
                    + e.getCause().getClass().getSimpleName());
        }

        CompletableFuture<String> canceled = new CompletableFuture<>();
        check(canceled.cancel(false), "Cancel should succeed");

        try {
            canceled.join();
            throw new AssertionError("Expected CancellationException");
        } catch (CancellationException expected) {
            check(canceled.isCancelled(), "Future must be canceled");
            System.out.println("canceled = true");
        }
    }
}
```

Run:

```bash
javac AsyncExceptionContractTest.java
java AsyncExceptionContractTest
```

Output:

```text
success = OK
cause = IOException
canceled = true
```

The test uses already-completed or directly canceled Futures, so its output is deterministic and **does not depend on thread scheduling**. It verifies the **result-observation** contract of `CompletableFuture`, without trying to prove the cancellation effect on a running worker.

If you need to test that a worker actually receives an interrupt, use `CountDownLatch`, `Future`, or an appropriate synchronization mechanism; avoid sleeping for an arbitrary duration and hoping the worker has reached the right point.

## 14. Testing Asynchronous Code Without Creating Races or Flaky Tests

Common anti-pattern:

```java
executor.submit(() -> updateState());
Thread.sleep(100);
assertEquals("DONE", state.get());
```

This is an **illustrative JUnit snippet** (not standalone), assuming `executor`, `updateState`, and `state` exist. `sleep(100)` does not guarantee the task finishes within 100 ms on CI. The test may pass locally and fail under load.

If you need to wait for a result, use synchronization with a deadline:

```java
Future<String> future = executor.submit(() -> "DONE");
String result = future.get(2, TimeUnit.SECONDS);
assertEquals("DONE", result);
```

This is an **integration snippet**, requiring `ExecutorService`, `Future`, `TimeUnit`, JUnit imports, and shutdown rules. A deadline prevents the test from hanging indefinitely, but it does not turn broken asynchronous code into correct code.

For complex scenarios, use `CountDownLatch` to enforce required ordering; when the test finishes, release latches in `finally`, shut down the executor, and handle interrupts properly. Never call `Thread.stop()` to "clean up" a hung test.

**Timeouts are only a safeguard against hanging**, not proof of correctness. The test must still assert the resulting state, exception type, and committed side effects.

## 15. Do Not Test Failure by Triggering an Unrelated Error

A test like the following can give a *false pass*:

```java
assertThrows(NullPointerException.class,
        () -> service.process(null));
```

If the actual contract requires `IllegalArgumentException`, the test above does not match expectations. Or a test might accidentally throw `NullPointerException` during fixture setup rather than inside `service.process(...)`.

Remedies:

1. Prepare fixtures **before** the exception-checking lambda.
2. Inside the lambda, place only **the action that the contract requires to fail**.
3. Verify the exact exception type and important error code/cause.
4. Verify side effects and state after failure.
5. If multiple errors are possible, isolate preconditions so only one condition is invalid.

A better JUnit example:

```java
OrderRequest request = new OrderRequest("A-1", -1);
IllegalArgumentException error = assertThrows(
        IllegalArgumentException.class,
        () -> service.createOrder(request));

assertEquals("INVALID_QUANTITY", error.getMessage());
```

This is an **illustrative snippet** with `OrderRequest`/`service` defined by the system. Construct `request` before `assertThrows` to avoid fixture initialization inside the lambda becoming the source of the exception. Assert the exact message only if `INVALID_QUANTITY` is a stable guarantee.

## 16. Failure Paths Must Not Produce False Success

A serious bug occurs when code catches an exception and returns a default value:

```java
try {
    return repository.read();
} catch (IOException e) {
    return "";
}
```

This is an illustrative snippet. It is only valid if the contract truly specifies `""` as a valid fallback result and callers can distinguish it from normal data. If the contract requires reporting an error, this is a bug: the exception was **swallowed**.

Tests must catch this broken behavior by:

- Having a fake repository throw `IOException`.
- Verifying that the service propagates `IOException` or wraps it in the right exception type.
- Asserting there is **no** success result.
- Checking that the cause remains intact if the error type is translated.

Similarly, a `return` inside `finally` can mask an exception being thrown. A failure-path test that checks the exact error type will detect when a program returns a normal result instead of throwing.

## 17. Testing Exception Messages and Causes After Refactoring

Refactoring can preserve the happy path while breaking the failure path in several ways:

- Removing `throw` or switching to returning `null`.
- Replacing `IOException` with `IllegalStateException` and forgetting the cause.
- Creating a new exception with a generic `"failed"` message instead of a stable error code.
- Converting `try-with-resources` to `try-finally`, causing a close exception to mask the primary exception.
- Replacing `throw e` with `throw new RuntimeException(e.getMessage())`, losing the cause stack.
- Catching `InterruptedException` and ignoring it, allowing the task to keep running.
- Catching `Exception` too broadly, turning programming errors into success fallbacks.

Therefore, when changing exception-related code, re-run **at least one success test and the corresponding failure tests for every affected contract**. Regression suites should focus on behavior observable by the caller rather than coupling tightly to where `catch` blocks live in the implementation.

## 18. Unit Tests, Integration Tests, and Where Responsibility Lies

Not every contract can be proven with mocked unit tests.

| Test Type | Best at Verifying |
|---|---|
| Unit test | Validation, exception type, stable message/code, cause wrapping, fallback choice, local state changes |
| Integration test | Real transaction rollback, resource closing, SQL/HTTP error mapping, adapters preserving cause |
| Inter-service contract test | Stable HTTP status/body, public error codes, retry semantics at boundaries |
| End-to-end test | User-facing behavior; operation success/failure across multiple components |

For example, mocking `Connection.rollback()` only proves the code **called** rollback in that specific test; it does not prove the database actually rolled back. Conversely, an integration test with a real database is more expensive but confirms end-to-end resource/transaction semantics.

When testing exceptions from a dependency, a fake/stub can deterministically throw errors for easy reproduction. Do not use a real network to trigger timeouts in a unit test unless necessary; that makes tests slow and flaky.

## 19. Distinguishing Expected Exceptions from Test Infrastructure Failures

When a test fails, read the signal:

- **Assertion failure:** observed behavior differs from the contract; inspect the assertion message and inputs.
- **Unexpected exception:** test/setup or production code threw another error; read the stack trace and cause.
- **Test timeout:** possible deadlock, waiting too long, overloaded environment, or a fixture failing to release a latch. Do not rush to increase timeouts if the logic is wrong.
- **Environment failure:** missing file, DB not running, different timezone/locale, permissions, or unconfigured dependencies.
- **Flaky test:** outcome depends on thread scheduling, wall-clock time, randomness, or shared state.

A good test must **fail when the contract is violated** and **stay stable when the contract is met**. Never turn a red test green by catching too broadly or removing an important assertion.

### JDK messages and stack traces should not be rigid oracles

If a test prints the entire `printStackTrace()` and compares 100% of the text, it easily breaks due to line numbers, file names, wrappers, or JDK versions. Use APIs like `getCause()`, `getSuppressed()`, and check error types. Only lock exact messages from code you control when there is a clear contract reason.

## 20. Checklist Before Concluding an Exception Contract Is Adequately Tested

- **Success:** are there typical inputs, valid boundaries, and assertions on results/side effects?
- **Invalid input:** does each group of invalid conditions test the appropriate exception type?
- **No exception:** do success tests accidentally call the method without checking the result?
- **Exception type:** are catches too broad (`Exception`/`RuntimeException`), allowing bugs to pass?
- **Message/code:** are you testing stable contract details rather than JDK/driver-generated details?
- **Cause:** do wrapped exceptions preserve the right root cause?
- **Suppressed:** are cleanup errors preserved properly without masking the primary exception?
- **State:** after failure, are partial updates and forbidden side effects avoided?
- **Async:** does the caller see `CompletionException`, `ExecutionException`, `CancellationException`, or `InterruptedException` in the right context?
- **Determinism:** do tests use fakes/latches/deadlines instead of arbitrary sleeps?
- **Isolation:** does each test have a clean fixture without depending on the execution order of other tests?
- **Observability:** do test assertions, test names, and failure messages help locate the violated guarantee?

**Remember:** contract-based exception testing means **verifying both how an API succeeds and how it rejects/fails**, including results, exception types, causes, suppressed exceptions, and post-error system state. A strong test suite does not merely prove "an exception occurred", it proves **the right exception in the right situation with no wrong side effects**.
