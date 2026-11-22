# Asserting the Right Exception Type Instead of Merely Asserting Failure

## 1. Why “an error occurred” is not enough to conclude a test is correct

When a Java method fails, the thrown exception is not merely a signal that something went wrong. The **exception type** is part of the contract between the method and its caller: invalid input is typically distinguished from invalid object state, I/O errors, asynchronous task failures, task cancellation, or timeouts.

Suppose a port-parsing API is designed according to these rules:

- `null` or blank input: **IllegalArgumentException** due to missing data.
- Input that cannot be parsed as an integer: **NumberFormatException**.
- Numeric value outside the range 1 to 65535: **IllegalArgumentException** due to out-of-bounds value.
- Valid value: returns the port number.

A test that only verifies “some exception was thrown” can PASS even if the code unexpectedly throws **NullPointerException**, **IndexOutOfBoundsException**, or a system error completely outside the contract. A new bug has changed the nature of the failure, yet the test fails to catch it.

**Core learning point:** When testing failure paths, verify the **exact failure condition**, the **exception class specified by the contract**, and—where meaningful—the **message, cause, suppressed exceptions, and data state after failure**. Do not make tests overly broad just to keep them passing.

The goal is not always to require the *exact runtime class* in every system. Some APIs commit to an entire **exception family**, intentionally allowing subtypes. What matters is **choosing an assertion that matches the contract**, rather than inadvertently ignoring differences between parent and child types.

## 2. Exception hierarchy directly affects assertions

Java has a class hierarchy in which `NumberFormatException` extends `IllegalArgumentException`. Part of the structure looks like this:

~~~text
Throwable
├── Error
└── Exception
    ├── IOException
    └── RuntimeException
        ├── IllegalArgumentException
        │   └── NumberFormatException
        ├── IllegalStateException
        └── NullPointerException
~~~

These are only representative branches, not the entire JDK hierarchy. Because of inheritance:

~~~java
// Illustrative code that can be placed in main.
Throwable failure = new NumberFormatException("invalid number");

System.out.println(failure instanceof IllegalArgumentException); // true
System.out.println(failure.getClass() == IllegalArgumentException.class); // false
System.out.println(failure.getClass() == NumberFormatException.class); // true
~~~

Comparing with **instanceof** or **Class.isInstance** accepts subclasses. Comparing with **failure.getClass() == Expected.class** requires the exact runtime class. If a test expects `IllegalArgumentException` while the implementation throws `NumberFormatException`, the first approach PASSES whereas the second FAILS.

This does not by itself say which one is right for the business logic: if the API promises `IllegalArgumentException` **or a subclass**, an assignable assertion is appropriate; if the API promises `IllegalArgumentException` specifically for a `null` condition, an exact assertion is valuable for catching regressions.

## 3. Levels of exception-checking strength

| Check level | Example | What it actually verifies | What it leaves unverified |
| --- | --- | --- | --- |
| Any exception | Catch Throwable and mark PASS | Some Throwable occurred | Whether the error contract is right or wrong |
| Parent class or subtype | assertThrows(RuntimeException.class, ...) | A RuntimeException or subtype occurred | Whether it is the intended error |
| Specific class or subtype | assertThrows(IllegalArgumentException.class, ...) | Belongs to the IllegalArgumentException family | Exact runtime class |
| Exact class | assertThrowsExactly(IllegalArgumentException.class, ...) | Exact runtime class matches | Message/cause/state |
| Class and semantics | Exact type + message/cause/suppressed/state | Key aspects of failure behavior | Untested input branches |

A test expecting **Exception.class**, **RuntimeException.class**, or especially **Throwable.class** is usually too broad. It can accept new bugs, setup errors, or even the test’s own **AssertionError** if the author places other assertions inside the lambda.

However, an exact-class test can also be too strict if the API intentionally allows different subtypes across implementations. **Assertion strength must be balanced against the API’s level of commitment.**

## 4. An example API with multiple failure conditions

Consider the following method:

~~~java
// Illustration inside a Java class.
static int parsePort(String input) {
    if (input == null || input.isBlank()) {
        throw new IllegalArgumentException("port required");
    }
    int port = Integer.parseInt(input);
    if (port < 1 || port > 65535) {
        throw new IllegalArgumentException("port out of range");
    }
    return port;
}
~~~

According to this implementation:

- **parsePort(null)** throws `IllegalArgumentException` specifically, with message **port required**.
- **parsePort("  ")** also throws `IllegalArgumentException` with the same message.
- **parsePort("abc")** throws `NumberFormatException` from `Integer.parseInt`.
- **parsePort("70000")** throws `IllegalArgumentException` because it is outside the allowed range.
- **parsePort("8080")** returns `8080`.
- A long numeric string that cannot be represented as an `int` causes `NumberFormatException` from `Integer.parseInt` before the range check.

These types are **the contract chosen for this example**, not a rule that every parser must behave identically. When the product changes its contract, documentation and tests must be updated deliberately—not merely tweaked to make tests PASS.

If someone accidentally removes the `null` check, the expression **input.isBlank()** may throw `NullPointerException`. A test requiring only “some RuntimeException” would still PASS, whereas a test requiring `IllegalArgumentException` specifically will FAIL and expose the regression.

## 5. Complete Java 17+ example without JUnit dependencies

The following program provides two simple helpers to illustrate the difference:

- **expectExact**: accepts only the exact runtime class via `getClass` comparison.
- **expectAssignable**: accepts the expected class or a subclass via `Class.isInstance`.

The program also verifies an application-created message, exception wrapping with `cause`, a cleanup error recorded in `suppressed`, and a success path. This is a learning example; in real projects, use a test framework such as JUnit Jupiter for full reporting and test lifecycle support.

Save the file **ExactExceptionTestDemo.java**:

~~~java
import java.io.IOException;

public class ExactExceptionTestDemo {
    @FunctionalInterface
    interface ThrowingAction {
        void run() throws Exception;
    }

    static final class FailingClose implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static int parsePort(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("port required");
        }
        int port = Integer.parseInt(input);
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("port out of range");
        }
        return port;
    }

    static int loadPort() {
        try {
            return parsePort("not-a-number");
        } catch (NumberFormatException original) {
            throw new IllegalStateException("config invalid", original);
        }
    }

    static void writeWithCloseFailure() throws IOException {
        try (FailingClose resource = new FailingClose()) {
            throw new IOException("write failed");
        }
    }

    static <T extends Throwable> T expectExact(
            Class<T> type, ThrowingAction action) {
        try {
            action.run();
        } catch (Throwable actual) {
            if (actual.getClass() != type) {
                throw new AssertionError("Expected " + type.getSimpleName()
                        + ", got " + actual.getClass().getSimpleName(), actual);
            }
            return type.cast(actual);
        }
        throw new AssertionError("Expected " + type.getSimpleName()
                + ", but no exception was thrown");
    }

    static <T extends Throwable> T expectAssignable(
            Class<T> type, ThrowingAction action) {
        try {
            action.run();
        } catch (Throwable actual) {
            if (!type.isInstance(actual)) {
                throw new AssertionError("Expected a subtype of "
                        + type.getSimpleName(), actual);
            }
            return type.cast(actual);
        }
        throw new AssertionError("Expected " + type.getSimpleName()
                + ", but no exception was thrown");
    }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        IllegalArgumentException blank = expectExact(
                IllegalArgumentException.class, () -> parsePort(null));
        require("port required".equals(blank.getMessage()), "wrong message");
        System.out.println("blank: " + blank.getClass().getSimpleName());

        NumberFormatException badNumber = expectExact(
                NumberFormatException.class, () -> parsePort("abc"));
        System.out.println("malformed: " + badNumber.getClass().getSimpleName());

        IllegalArgumentException broad = expectAssignable(
                IllegalArgumentException.class, () -> parsePort("abc"));
        System.out.println("broad assertion accepts: "
                + broad.getClass().getSimpleName());

        boolean wrongTypeDetected = false;
        try {
            expectExact(IllegalArgumentException.class, () -> parsePort("abc"));
        } catch (AssertionError mismatch) {
            wrongTypeDetected = mismatch.getMessage().equals(
                    "Expected IllegalArgumentException, got NumberFormatException");
        }
        require(wrongTypeDetected, "exact assertion must reject subclasses");
        System.out.println("exact assertion rejects wrong subtype: true");

        IllegalStateException wrapped = expectExact(
                IllegalStateException.class, ExactExceptionTestDemo::loadPort);
        require(wrapped.getCause() instanceof NumberFormatException,
                "cause must be NumberFormatException");
        System.out.println("wrapped cause: "
                + wrapped.getCause().getClass().getSimpleName());

        IOException primary = expectExact(
                IOException.class, ExactExceptionTestDemo::writeWithCloseFailure);
        require("write failed".equals(primary.getMessage()), "wrong primary");
        require(primary.getSuppressed().length == 1, "missing close error");
        require("close failed".equals(primary.getSuppressed()[0].getMessage()),
                "wrong suppressed");
        System.out.println("primary: " + primary.getMessage());
        System.out.println("suppressed: " + primary.getSuppressed()[0].getMessage());

        require(parsePort("8080") == 8080, "valid input failed");
        System.out.println("valid result: " + parsePort("8080"));
        System.out.println("ALL CHECKS PASSED");
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac --release 17 ExactExceptionTestDemo.java
java ExactExceptionTestDemo
~~~

Here is the actual verified stdout when compiled and run:

~~~text
blank: IllegalArgumentException
malformed: NumberFormatException
broad assertion accepts: NumberFormatException
exact assertion rejects wrong subtype: true
wrapped cause: NumberFormatException
primary: write failed
suppressed: close failed
valid result: 8080
ALL CHECKS PASSED
~~~

In the training helper, **catch(Throwable)** is used to catch even the wrong `Throwable` type and throw `AssertionError`; this is **not** an exception-handling pattern for silently recovering in production code. Checks using explicit `AssertionError` should work without enabling Java’s **-ea** flag.

## 6. Interpreting the output: overly broad assertions accept the wrong subtype

Two key lines:

~~~text
broad assertion accepts: NumberFormatException
exact assertion rejects wrong subtype: true
~~~

When the tester asks for **IllegalArgumentException or a subclass**, `NumberFormatException` is valid because it extends `IllegalArgumentException`. But when **IllegalArgumentException** specifically is required, the same exception fails the assertion.

This prevents a test stating “all invalid inputs must throw IllegalArgumentException” from inadvertently overlooking the requirement to distinguish **malformed number** from **missing input**. Each error carries a different meaning for the caller. Conversely, if the contract only promises the **IllegalArgumentException family**, an exact test can unnecessarily couple code to a specific subclass choice.

When reviewing tests, the right question is: **Which class is the caller allowed to rely on?** If the caller uses a dedicated `catch(NumberFormatException)` to report a format error, replacing `NumberFormatException` with `IllegalArgumentException` breaks the contract. If the caller only uses `catch(IllegalArgumentException)`, subtypes may be permitted by design.

## 7. JUnit Jupiter `assertThrows` accepts subclasses

In JUnit Jupiter 5, **assertThrows(Expected.class, executable)** accepts an exception of class `Expected` **or any of its subtypes**. For example:

~~~java
// JUnit Jupiter, requires the JUnit dependency and the example class in the same package.
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PortExceptionFamilyTest {
    @Test
    void nonNumericPortBelongsToIllegalArgumentFamily() {
        IllegalArgumentException failure = assertThrows(
                IllegalArgumentException.class,
                () -> ExactExceptionTestDemo.parsePort("abc"));
    }
}
~~~

This test PASSES because `NumberFormatException` is an `IllegalArgumentException`. It **does not prove** that the exact runtime class is `IllegalArgumentException`.

**`assertThrows` returns the caught Throwable** with the matching generic type. You can continue inspecting `message`, `cause`, `suppressed`, and related details. Do not merely call `assertThrows` and discard the returned exception in a test whose contract also specifies other properties.

When is checking an exception family sufficient? For example, an abstraction may use multiple file-reading implementations whose contract only guarantees `IOException` or a subtype. In that case, `assertThrows(IOException.class, ...)` can be more appropriate than forcing an exact class that the implementation never promised.

## 8. JUnit Jupiter `assertThrowsExactly` requires the exact runtime class

JUnit Jupiter provides **assertThrowsExactly(Class<T>, Executable)** on supported versions. This method PASSES only when the exception has the exact runtime class; a subclass is not enough.

A JUnit 5 example using the class from the Java SE program in section 5:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ExactPortExceptionJUnitTest {
    @Test
    void missingInputHasExactType() {
        IllegalArgumentException failure = assertThrowsExactly(
                IllegalArgumentException.class,
                () -> ExactExceptionTestDemo.parsePort(null));
        assertEquals("port required", failure.getMessage());
    }

    @Test
    void malformedNumberHasExactType() {
        assertThrowsExactly(
                NumberFormatException.class,
                () -> ExactExceptionTestDemo.parsePort("abc"));
    }

    @Test
    void outOfRangeHasExactType() {
        IllegalArgumentException failure = assertThrowsExactly(
                IllegalArgumentException.class,
                () -> ExactExceptionTestDemo.parsePort("70000"));
        assertEquals("port out of range", failure.getMessage());
    }

    @Test
    void validPortWorks() {
        int port = assertDoesNotThrow(
                () -> ExactExceptionTestDemo.parsePort("8080"));
        assertEquals(8080, port);
    }
}
~~~

This is a valid test class in the context of **a project configured with JUnit Jupiter** containing **ExactExceptionTestDemo** in the same package/classpath. It is not a standalone Java SE program that can be run with `javac` alone without the JUnit dependency. Run it with your project build tool’s test runner.

If your JUnit Jupiter version is too old to have **assertThrowsExactly**, you can call **assertThrows** and then check **assertEquals(Expected.class, failure.getClass())**. What matters is expressing the exact-type requirement clearly, not the specific API name.

**Avoid over-constraining the contract:** Use `assertThrowsExactly` when the runtime class is genuinely promised. If an API only declares `IOException` and permits subtypes, an exact `IOException` check can make the test FAIL even when the implementation is valid.

## 9. In plain Java: `isInstance` vs. `getClass`

Without JUnit, you can distinguish them as follows:

~~~java
// Illustrative code; failure is a non-null Throwable.
boolean acceptsSubtype =
        IllegalArgumentException.class.isInstance(failure);
boolean exactClass =
        failure.getClass() == IllegalArgumentException.class;
~~~

Or:

~~~java
// Illustrative code.
if (!(failure instanceof IllegalArgumentException)) {
    throw new AssertionError("Wrong exception family");
}

if (failure.getClass() != IllegalArgumentException.class) {
    throw new AssertionError("Wrong exact exception class");
}
~~~

**instanceof** evaluates to `true` for subtypes and does not throw `NullPointerException` when `failure` is `null`; when `failure` is `null`, `instanceof` evaluates to `false`. **failure.getClass()** requires a non-null object. In framework-based tests, assertion APIs generally produce clearer failure messages than a hand-written boolean comparison.

Do not use **failure.toString().contains("IllegalArgumentException")** to determine the class. A message and class name can match by substring without being the actual runtime class; use **getClass()** or Java type checks.

## 10. Testing checked and unchecked exceptions according to contract

**Checked exceptions** such as `IOException`, `SQLException`, `InterruptedException`, and `ExecutionException` are typically enforced by the compiler so callers catch or declare them. **Unchecked exceptions** such as `IllegalArgumentException`, `IllegalStateException`, `NumberFormatException`, and `CancellationException` do not have that requirement.

When testing, however, the checked/unchecked distinction **does not replace** the exact error type. For example:

~~~java
// Illustrative JUnit code when api.read() can throw IOException.
IOException error = assertThrows(
        IOException.class,
        () -> api.read());
~~~

This assertion accepts `IOException` subtypes. If the contract requires **FileNotFoundException** specifically, use the corresponding assertion; if the API only promises the `IOException` family, the assertion above is sufficient.

Do not use **assertThrows(Exception.class, ...)** to lump `InterruptedException` (caller interrupted), `ExecutionException` (worker failed), and `IOException` (I/O error) into a single passing branch of a test. These exceptions signal different conditions and require different handling policies.

Do not include every `Error` in recovery tests as if it were an ordinary exception. A test helper may catch `Throwable` to inspect its type, but production applications should not routinely “recover” from arbitrary `Error`s.

## 11. Exception wrapping: check both outer type and cause

A service layer may wrap a low-level error into a higher-level abstraction:

~~~java
// The loadPort method from the example.
static int loadPort() {
    try {
        return parsePort("not-a-number");
    } catch (NumberFormatException original) {
        throw new IllegalStateException("config invalid", original);
    }
}
~~~

The exception caught by the caller is **IllegalStateException**; the original exception is **NumberFormatException** in **getCause()**. Asserting only that a `RuntimeException` occurred does not verify the wrapping policy or that error details were preserved.

JUnit pattern:

~~~java
// Inside @Test, with the corresponding JUnit static imports.
IllegalStateException wrapper = assertThrowsExactly(
        IllegalStateException.class,
        ExactExceptionTestDemo::loadPort);

assertEquals("config invalid", wrapper.getMessage());
assertNotNull(wrapper.getCause());
assertEquals(NumberFormatException.class,
             wrapper.getCause().getClass());
~~~

If a developer replaces it with **new IllegalStateException(original.getMessage())**, the outer-type test still PASSES, but **assertNotNull(wrapper.getCause())** FAILS, catching the loss of the original exception.

When an API promises that `cause` is any subtype of `IOException`, replace **assertEquals(IOException.class, cause.getClass())** with **assertInstanceOf(IOException.class, cause)** if subtypes are allowed. In any test, distinguish **outer exception class**, **cause class**, and **business message**.

## 12. Checking suppressed exceptions: was the primary error masked?

In try-with-resources, when the main block throws exception A and `close()` throws exception B, Java keeps A as **primary** and attaches B to **A.getSuppressed()** if suppression is enabled.

Snippet from the runnable program:

~~~java
static void writeWithCloseFailure() throws IOException {
    try (FailingClose resource = new FailingClose()) {
        throw new IOException("write failed");
    }
}
~~~

A test stronger than merely asserting `IOException`:

~~~java
// Inside JUnit @Test with the appropriate Assertions imports.
IOException primary = assertThrowsExactly(
        IOException.class,
        ExactExceptionTestDemo::writeWithCloseFailure);

assertEquals("write failed", primary.getMessage());
assertEquals(1, primary.getSuppressed().length);
assertEquals(IOException.class,
             primary.getSuppressed()[0].getClass());
assertEquals("close failed",
             primary.getSuppressed()[0].getMessage());
~~~

If production code is changed to a careless `finally` block that closes the resource, the **close failed** error can mask **write failed**. A test checking only `IOException` still PASSES, whereas checks on the primary message and suppressed exceptions FAIL. This is a classic example where **the right class with the wrong semantics is still a bug**.

**Suppressed is not cause:** `cause` expresses causality/wrapping; `suppressed` records secondary failures during cleanup. If a service also wraps the primary exception in another exception, the suppressed exceptions may live on **wrapper.getCause()** rather than being copied onto the wrapper.

## 13. Checking the message: when should it be matched exactly?

A message committed by the application itself can be a useful part of the contract to test:

~~~java
// JUnit illustration.
IllegalArgumentException error = assertThrowsExactly(
        IllegalArgumentException.class,
        () -> ExactExceptionTestDemo.parsePort(null));
assertEquals("port required", error.getMessage());
~~~

Conversely, a JDK-generated message such as `NumberFormatException` details may vary across JDK versions or inputs. If an API only promises **NumberFormatException**, do not turn verbatim JDK message text into a contract unless necessary.

A sensible priority order:

1. Exact exception type or exception family as specified by the contract.
2. Exact message/error code **if explicitly published by the application**.
3. Correct `cause`/`suppressed` if error details must be preserved.
4. Correct data or resource state after failure.
5. Exact object identity if the rule is to rethrow the same `Throwable`.

A test that only uses **failure.getMessage().contains("error")** proves neither the source nor the type of the error. Different errors can share the same keyword, and `message` can be `null`.

## 14. When you need to verify the exact exception instance

Some APIs deliberately **rethrow the exact same** original error object:

~~~java
// Illustrative code inside an appropriate class.
static void rethrow(IOException original) throws IOException {
    throw original;
}
~~~

JUnit can verify:

~~~java
// Inside @Test; rethrow is defined appropriately.
IOException original = new IOException("disk failure");
IOException actual = assertThrowsExactly(
        IOException.class,
        () -> rethrow(original));
assertSame(original, actual);
~~~

**assertSame** is stronger than comparing messages: it ensures a new `IOException` was not created with only the same message while losing `cause`, `suppressed`, or the stack trace.

Do not use an identity assertion when the API is **allowed** to wrap the exception. In that case, check **wrapper.getCause() == original**. The goal is to preserve the contract’s relationship between `Throwable`s, not to lock down implementation details unnecessarily.

## 15. Testing state after failure: the right exception is still not enough

A money-transfer error might throw the right `IllegalStateException` when crediting the destination account fails, yet still have debited the source account. A test that only checks the exception class PASSES even though data was left partially mutated.

Anti-pattern example:

~~~java
// Contextual illustrative code.
from.debit(amount);
to.credit(amount); // May throw IllegalStateException.
~~~

If the API promises that failure leaves state unchanged, the test must capture a snapshot beforehand and compare afterward:

~~~java
// Contextual JUnit; Account and transfer are defined by the application.
long sourceBefore = from.balance();
long targetBefore = to.balance();

assertThrowsExactly(IllegalStateException.class,
        () -> transfer(from, to, amount));

assertEquals(sourceBefore, from.balance());
assertEquals(targetBefore, to.balance());
~~~

When code has external side effects (files, databases, remote services), add integration tests, transaction tests, or appropriate idempotency models. **The exact exception type alone does not prove that cleanup or rollback completed.**

## 16. Testing the success path and `assertDoesNotThrow`

If every test only tries invalid inputs, a parser could reject valid inputs as well and still pass all those tests. You must test the success path separately:

~~~java
// Contextual JUnit.
int port = assertDoesNotThrow(
        () -> ExactExceptionTestDemo.parsePort("8080"));
assertEquals(8080, port);
~~~

**assertDoesNotThrow** verifies that the lambda throws no exception, while **assertEquals** verifies that the returned value is correct. `assertDoesNotThrow` alone can PASS if the method returns the wrong value without throwing.

In the runnable Java SE program, **require(parsePort("8080") == 8080, ...)** verifies both non-throwing behavior and the result. On failure, it explicitly throws `AssertionError` instead of merely printing a message.

Another mistake: a test catches all exceptions and logs them without calling **fail()** or throwing `AssertionError`. The test runner then marks it PASS because the test method exits normally. Tests must let actual assertion failures reach the runner.

## 17. Test matrix for each input category

For the specific parser in this lesson:

| Input | Condition | Expected result |
| --- | --- | --- |
| null | Missing port | Exact IllegalArgumentException, message port required |
| Two-space string | Blank | Exact IllegalArgumentException, message port required |
| "abc" | Cannot parse as number | Exact NumberFormatException |
| "0" | Below range 1–65535 | Exact IllegalArgumentException, message port out of range |
| "70000" | Exceeds maximum port | Exact IllegalArgumentException, message port out of range |
| "8080" | Valid | Returns 8080 |
| "65535" | Valid upper bound | Returns 65535 |
| "999999999999" | Not representable as int | Exact NumberFormatException |

When using **@ParameterizedTest** in JUnit, each invocation should carry its expected class and a descriptive display name. Do not collapse all invalid inputs into a single test expecting only **RuntimeException.class**, because that ignores the distinct rules of each branch.

Separating cases also improves failure diagnostics: you see immediately which input, error type, and message mismatched. A long test calling multiple `assertThrows` without scenario names is usually harder to investigate than an explicit test matrix.

## 18. Async: `ExecutionException`, `CompletionException`, and root errors

In asynchronous tests, the exception seen by the consumer may be a wrapper:

- **Future.get()** when a task fails typically throws `ExecutionException` whose `cause` is the worker error.
- **CompletableFuture.join()** typically throws `CompletionException` whose `cause` is the stage error.
- **CancellationException** may be thrown directly when the `Future` was canceled.
- **Future.get(timeout)** may throw `TimeoutException` because the caller timed out waiting, even if the task has not necessarily failed.
- **InterruptedException** from `get` may mean the caller was interrupted while waiting, which does not mean the worker was canceled.

JUnit example:

~~~java
// Contextual illustration with JUnit Jupiter.
CompletableFuture<Integer> failed =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("bad payload"));

CompletionException wrapper = assertThrowsExactly(
        CompletionException.class, failed::join);
assertEquals(IllegalArgumentException.class,
             wrapper.getCause().getClass());
~~~

If you write **assertThrows(RuntimeException.class, failed::join)**, the test does not distinguish `CompletionException` from `CancellationException` or other direct runtime errors. If you switch to **get()**, the wrapper is typically `ExecutionException` instead of `CompletionException`—the assertion must be updated to match the new contract.

For concurrency, avoid using `Thread.sleep` with arbitrary durations as the sole way to trigger failure conditions. Use `CountDownLatch` or an already abnormally completed `CompletableFuture` to keep tests deterministic.

## 19. Do not catch the test’s own `AssertionError`

An anti-pattern:

~~~java
// JUnit anti-pattern, do not use.
try {
    assertEquals(1, actual);
} catch (Throwable ignored) {
    // The test runner can no longer see the assertion failure.
}
~~~

Even more dangerous:

~~~java
// JUnit anti-pattern.
assertThrows(Throwable.class, () -> {
    assertEquals(1, 2);
});
~~~

An `AssertionError` thrown by **assertEquals** is also a **Throwable**. Therefore, `assertThrows(Throwable.class, ...)` can PASS even though the exception did not come from production code—only from a deliberately failing assertion!

To avoid false positives:

- Place only the **operation under test** inside the `assertThrows` lambda.
- Use a specific expected class matching the contract.
- Place assertions on `message`/`cause`/state **after** obtaining the `Throwable`.
- Do not catch `Throwable` and ignore it in a test method.
- Let JUnit report `AssertionError` normally when a check fails.

The example’s **expectExact** helper only catches `Throwable` to inspect the exact runtime class, and explicitly throws `AssertionError` when the class is wrong or no exception was thrown; it does not swallow failures.

## 20. Setup/cleanup errors can cause false PASSes

Consider a test meant to verify parsing a stream:

~~~java
// Illustrative JUnit anti-pattern.
assertThrows(IOException.class, () -> {
    InputStream input = openInput(); // The open step itself may throw IOException.
    parse(input);                    // The operation that actually needs to be tested.
});
~~~

If **openInput()** throws `IOException` because the file does not exist, the test PASSES even though **parse(input)** never ran. The error has the **right class** but the **wrong source**.

A clearer structure is to prepare reliable inputs/fixtures outside the lambda, then put only the operation under test inside the lambda. If the contract covers both open and parse together, you can keep them together, but verify `message`/`cause`, observed outcomes, or side effects as well to confirm the right stage failed.

Also consider when **close()** in `finally` or try-with-resources throws an `IOException` of the same type as the work error. With only `assertThrows(IOException.class)`, the test can PASS when the primary work error was masked by the `close` error. **Checking `suppressed` and `message` or identity** helps catch the wrong error source.

## 21. Mutation thinking: if the code is broken, will the test FAIL?

When evaluating test quality, test hypothetical faulty mutations:

1. Remove the `null` check: `parsePort(null)` throws `NullPointerException`.
2. Wrap the parse error in a new `IllegalArgumentException`: `parsePort("abc")` no longer produces an exact `NumberFormatException`.
3. Remove the range check: `parsePort("70000")` returns `70000`.
4. Catch `NumberFormatException` and return a fallback: the test expecting an exception no longer receives one.
5. Replace try-with-resources with a `finally` block that masks the primary error: still `IOException`, but with different `message`/`suppressed`.
6. Create a wrapper without passing `cause`: outer type is still right, but `cause` is lost.
7. When a `Future` is canceled, the consumer receives `CancellationException` instead of exceptional completion from the worker.

Tests written as **assertThrows(Exception.class)** can miss several of these mutations. Testing exact type + `cause`/`suppressed` + state catches far more critical regressions.

You can use a mutation-testing framework to evaluate test strength in a project, though not every tool automatically generates all the mutations above. The primary goal is **contract-based testing mindset**, not just running tests for the sake of it.

## 22. Checklist for reviewing an exception test

1. Are the **input and state that trigger the failure** set up accurately?
2. Does it **assert a specific exception type**, rather than catching `Exception` or expecting any error?
3. **Do you want the exact runtime class or allow subclasses?** Does the assertion express that choice accurately?
4. Have **JUnit `assertThrows` and `assertThrowsExactly`** been distinguished properly?
5. Does the **operation inside the lambda** isolate the stage under test, avoiding false PASSes from setup/cleanup?
6. Is the test’s own **AssertionError** ever swallowed or treated as the expected `Throwable`?
7. Are **wrapper/`cause`** checked when the API translates exceptions to a higher layer?
8. Are **suppressed exceptions** checked when both the main work and `close()` can fail?
9. Are **message/error code** stable and part of the contract, rather than depending on an unpromised JDK string?
10. Does **state after failure** satisfy invariants and rollback/atomicity guarantees?
11. Is the **happy path** verified along with its result, not only failure paths?
12. Are **async/timeout/interruption/cancellation** distinguished by their proper types?
13. Does **each input and failure branch** have its own test or clear parameterized case?
14. **If the implementation throws a different exception**, will the test suite actually FAIL, or accidentally PASS due to an overly broad assertion?

**Conclusion:** A trustworthy exception test does not stop at “an error occurred.” It verifies the **right error type per the contract and the right failure semantics**. In JUnit Jupiter, **assertThrows** accepts subtypes, whereas **assertThrowsExactly** requires the exact runtime class. Combining checks on **message, cause, suppressed, identity, and state** where needed catches both exception-type regressions and masked/swallowed errors—issues that an overly broad assertion easily misses.
