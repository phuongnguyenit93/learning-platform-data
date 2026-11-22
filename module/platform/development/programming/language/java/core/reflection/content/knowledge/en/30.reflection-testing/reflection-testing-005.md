# Testing Target Code Errors Preserved via `InvocationTargetException`

## 1. Goal of This Test Lesson

When invoking a method via Java Reflection, `Method.invoke(receiver, args...)` can fail at **two distinct layers**:

1. **Reflection layer**: unable to find the method, insufficient permissions, wrong receiver or arguments. These are errors during call preparation/dispatch.
2. **Target code layer**: the method was actually invoked and its own body threw an exception or error.

At the second layer, `Method.invoke` wraps the `Throwable` thrown by the **target method** in a `java.lang.reflect.InvocationTargetException`. The original object can be retrieved via `getCause()` or `getTargetException()`. A good test must prove **the right wrapper type**, **the exact original cause object**, and **the right content/cause chain**; comparing only the wrapper's message string easily misses bugs.

Core expected example:

```java
Method method = Target.class.getDeclaredMethod("fail");
try {
    method.invoke(null);
    throw new AssertionError("Expected InvocationTargetException");
} catch (InvocationTargetException e) {
    Throwable original = e.getCause();
    // Check type, message, and/or identity of original.
}
```

The snippet above is an **illustrative sample** and must be placed in a context with imports, a `Target` class, and handling for remaining checked exceptions. A standalone runnable example is in section 5.

## 2. Contract of `Method.invoke` and the Wrapper

Abbreviated signature:

```java
public Object invoke(Object obj, Object... args)
        throws IllegalAccessException, InvocationTargetException;
```

Behaviors to distinguish:

| Condition | Error observed on reflection call | `InvocationTargetException`? |
| --- | --- | --- |
| Target code throws `IllegalStateException` | `InvocationTargetException` containing `IllegalStateException` | Yes |
| Target code throws checked `IOException` | `InvocationTargetException` containing `IOException` | Yes |
| Target code throws `AssertionError` | `InvocationTargetException` containing `AssertionError` | Yes |
| Target code throws `IllegalArgumentException` | `InvocationTargetException` containing `IllegalArgumentException` | Yes |
| Caller passes wrong argument types/count to `Method.invoke` | Typically direct `IllegalArgumentException` | No |
| No access permission to the method | `IllegalAccessException`, or error when attempting to open access | No |
| Looking up a non-existent method via `getDeclaredMethod` | `NoSuchMethodException` at the **lookup step**, before invoke | No |
| Target code succeeds | Result returned (or `null` for `void` methods) | No |

With `Method.invoke`, **an exception thrown by the target** is wrapped in `InvocationTargetException` even when it is an unchecked exception or `Error`. The fact that `Method.invoke` returns `Object` does not alter the original exception's identity.

`InvocationTargetException` extends `ReflectiveOperationException`. `getTargetException()` is a historical API; in modern code, `getCause()` expresses the causal relationship consistently with `Throwable`. For the wrapper created by `Method.invoke` after the target throws, both methods return the same target throwable object.

Edge cases: if the JVM or environment fails **before** transferring control into the target code (such as linking or class-loading errors), do not automatically assume every observed `Throwable` is a wrapped target error. Verify the actual operation and exception type.

## 3. What Must Be Asserted to Guarantee "Preserved Intact"

For a call where you **intentionally trigger** an exception in the target, verify at increasing levels of precision:

- **Correct wrapper type:** `assertThrows(InvocationTargetException.class, () -> method.invoke(...))`.
- **Original cause present:** `assertNotNull(wrapper.getCause())`.
- **Correct cause type:** e.g., `assertInstanceOf(IllegalStateException.class, wrapper.getCause())` or exact class check when required by contract.
- **Throwable identity:** if the test holds a reference to the thrown object, `assertSame(original, wrapper.getCause())`. This is stronger evidence than comparing messages: the wrapper preserves the **exact original Throwable**, without creating another object in its place.
- **Same object across APIs:** `assertSame(wrapper.getCause(), wrapper.getTargetException())`.
- **Message/cause chain:** when part of the tested contract, verify `original.getMessage()` and `original.getCause()`; do not only assert strings formed from the wrapper.
- **Originating source:** when truly necessary, inspect the cause's stack trace for the target method or use a marker set by the target to prove the body ran. Avoid depending on file paths, line numbers, or the full order of stack frames, which can vary.

**Note on `assertSame`:** in the illustrative test, the target assigns a reference to the newly created exception to a test-fixture field before throwing. This is how to test identity. In production, do not store Throwables in global static variables just for logging; tests can use small-scoped fixtures and run sequentially to avoid overwriting references.

## 4. How to Test a Real Method via Reflection

Reasonable testing steps:

1. Create a target with **deterministic** throwing behavior. Separate checked, unchecked, and `Error` cases if the contract covers all three.
2. Retrieve the exact `Method` using `getDeclaredMethod(name, parameterTypes...)` or `getMethod(...)`. If the method is `static`, pass receiver `null`; for an instance method, create a receiver of the proper class.
3. Invoke via `Method.invoke` inside a test helper that allows throwing `Throwable`.
4. Catch/assert `InvocationTargetException` and read `getCause()`. Compare **reference** if the fixture stores original; verify type and message.
5. Test reflection errors happening **before invocation** in a separate test so the two error layers are not accidentally merged.
6. If the application has a wrapper helper to unwrap and rethrow the cause, test that helper separately: the caller must see the original cause, no longer `InvocationTargetException`.

Do not construct a new `new IllegalStateException(message)` in test code and call `assertSame` against the target's exception: those are **two distinct objects** even with identical type and message. Nor should you compare `wrapper.getMessage()` against the business message; the wrapper and cause are two different layers.

## 5. Standalone Java 17+ Example: Testing Runtime, Checked, Error, Cause Chain, and Unwrap

Save file `InvocationTargetExceptionDemo.java`:

```java
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class InvocationTargetExceptionDemo {
    static final class Target {
        static Throwable lastThrown;
        static boolean called;

        public static void failRuntime() {
            IllegalStateException original =
                    new IllegalStateException("runtime failure");
            lastThrown = original;
            throw original;
        }

        public static void failChecked() throws IOException {
            IOException original = new IOException("checked failure");
            lastThrown = original;
            throw original;
        }

        public static void failError() {
            AssertionError original = new AssertionError("error failure");
            lastThrown = original;
            throw original;
        }

        public static void failIllegalArgument() {
            IllegalArgumentException original =
                    new IllegalArgumentException("inside target");
            lastThrown = original;
            throw original;
        }

        public static void failWithCause() {
            IOException root = new IOException("root cause");
            IllegalStateException original =
                    new IllegalStateException("outer cause", root);
            lastThrown = original;
            throw original;
        }

        public static void acceptInt(int number) {
            called = true;
        }
    }

    @FunctionalInterface
    interface ThrowingAction {
        void run() throws Throwable;
    }

    static <T extends Throwable> T expectThrows(
            Class<T> expectedType, ThrowingAction action) {
        try {
            action.run();
        } catch (Throwable actual) {
            if (!expectedType.isInstance(actual)) {
                throw new AssertionError(
                        "Expected " + expectedType.getName()
                                + ", got " + actual.getClass().getName(),
                        actual);
            }
            return expectedType.cast(actual);
        }
        throw new AssertionError(
                "Expected exception: " + expectedType.getName());
    }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void verifyTargetFailure(
            String methodName, Class<? extends Throwable> causeType)
            throws Exception {
        Method method = Target.class.getDeclaredMethod(methodName);
        Target.lastThrown = null;

        InvocationTargetException wrapper = expectThrows(
                InvocationTargetException.class,
                () -> method.invoke(null));

        Throwable original = wrapper.getCause();
        require(original != null, "Missing target cause");
        require(causeType.isInstance(original), "Wrong target type");
        require(original == Target.lastThrown, "Original identity lost");
        require(wrapper.getTargetException() == original,
                "Different target exception");
    }

    static Object invokeUnwrapped(Method method, Object receiver,
            Object... arguments) throws Throwable {
        try {
            return method.invoke(receiver, arguments);
        } catch (InvocationTargetException wrapper) {
            throw wrapper.getCause();
        }
    }

    public static void main(String[] args) throws Exception {
        verifyTargetFailure(
                "failRuntime", IllegalStateException.class);
        System.out.println("runtime=wrapped,preserved");

        verifyTargetFailure("failChecked", IOException.class);
        System.out.println("checked=wrapped,preserved");

        verifyTargetFailure("failError", AssertionError.class);
        System.out.println("error=wrapped,preserved");

        verifyTargetFailure(
                "failIllegalArgument", IllegalArgumentException.class);
        System.out.println("targetIllegalArg=wrapped");

        Method chained = Target.class.getDeclaredMethod("failWithCause");
        InvocationTargetException wrapper = expectThrows(
                InvocationTargetException.class,
                () -> chained.invoke(null));
        Throwable original = wrapper.getCause();
        require(original == Target.lastThrown, "Cause identity changed");
        require(original.getCause() instanceof IOException,
                "Nested cause type changed");
        require("root cause".equals(original.getCause().getMessage()),
                "Nested cause message changed");
        System.out.println("nestedCause=preserved");

        Method accepting = Target.class.getDeclaredMethod(
                "acceptInt", int.class);
        Target.called = false;
        expectThrows(IllegalArgumentException.class,
                () -> accepting.invoke(null, "not an int"));
        require(!Target.called, "Target should not have run");
        System.out.println("badArguments=directIllegalArgumentException");

        Method failing = Target.class.getDeclaredMethod("failRuntime");
        IllegalStateException escaped = expectThrows(
                IllegalStateException.class,
                () -> invokeUnwrapped(failing, null));
        require(escaped == Target.lastThrown, "Unwrap lost identity");
        System.out.println("unwrap=originalCause");
    }
}
```

Run in the directory containing the file:

```bash
javac --release 17 -encoding UTF-8 InvocationTargetExceptionDemo.java
java InvocationTargetExceptionDemo
```

Expected stdout:

```text
runtime=wrapped,preserved
checked=wrapped,preserved
error=wrapped,preserved
targetIllegalArg=wrapped
nestedCause=preserved
badArguments=directIllegalArgumentException
unwrap=originalCause
```

Each line is printed **only after all corresponding assertions succeed**. If an assumption fails, the program throws `AssertionError` and will not print that step's result line. `expectThrows` intentionally uses a minimal harness without external library dependencies; in a project using JUnit 5, using `org.junit.jupiter.api.Assertions.assertThrows` is more standard.

### Why Is This Example Valuable for Verification?

- `verifyTargetFailure` checks wrapper, type, **identity**, and consistency between `getCause()`/`getTargetException()` simultaneously for unchecked, checked, `Error`, and `IllegalArgumentException` thrown **from inside the target**.
- `failWithCause` confirms the **original cause chain** inside the target does not vanish when the reflection wrapper is added.
- `acceptInt` clarifies that an `IllegalArgumentException` caused by **calling reflection with wrong arguments** is a direct exception; the target does not execute and there is no `InvocationTargetException`.
- `invokeUnwrapped` simulates adapter code that chooses to return the business cause. The test confirms the caller receives the **exact original exception**, with no second wrapper and without being replaced by another object of the same type with a different identity.

In the example, the fixture stores `Target.lastThrown` as `static`. Since `main` runs sequentially and resets the fixture before cases, this is safe for a learning model; real tests running in parallel should use independent fixtures or synchronization mechanisms to avoid state contention.

## 6. Equivalent Implementation in JUnit 5

If the project already has **JUnit Jupiter** configured, a single test can be written as follows. The snippet below **belongs in a test class in the same package**, referencing `InvocationTargetExceptionDemo.Target` from the example above; the JUnit Jupiter dependency must be added to the build before compiling tests.

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ReflectionExceptionTest {
    @Test
    void preservesOriginalException() throws Exception {
        Method method =
                InvocationTargetExceptionDemo.Target.class
                        .getDeclaredMethod("failRuntime");

        InvocationTargetException wrapper = assertThrows(
                InvocationTargetException.class,
                () -> method.invoke(null));

        Throwable original = wrapper.getCause();
        assertNotNull(original);
        assertInstanceOf(IllegalStateException.class, original);
        assertSame(InvocationTargetExceptionDemo.Target.lastThrown,
                original);
        assertSame(original, wrapper.getTargetException());
        assertEquals("runtime failure", original.getMessage());
    }

    @Test
    void wrongArgumentFailsBeforeTarget() throws Exception {
        Method method =
                InvocationTargetExceptionDemo.Target.class
                        .getDeclaredMethod("acceptInt", int.class);

        InvocationTargetExceptionDemo.Target.called = false;
        assertThrows(IllegalArgumentException.class,
                () -> method.invoke(null, "bad argument"));
        assertFalse(InvocationTargetExceptionDemo.Target.called);
    }
}
```

This test is not a standalone program with `main`; execute it using JUnit 5's runner, e.g., Gradle with `test { useJUnitPlatform() }` when the project environment declares the proper dependencies.

**Do not** write `assertThrows(IllegalStateException.class, () -> method.invoke(null))` for the first test: the reflection call produces `InvocationTargetException` on the caller side; `IllegalStateException` is inside `getCause()`.

When testing asynchronous tasks, apply the proper boundary: determine whether there is another future/async wrapper (`ExecutionException`, `CompletionException`) first. Do not assume every Throwable from another thread passes through `InvocationTargetException`.

## 7. Testing Stack Traces and Cause Chains Without Being Too Brittle

`InvocationTargetException` and the original exception can have **two different stack traces**:

- The wrapper belongs to the reflection layer at the time of invocation.
- The cause keeps the stack trace from when the original Throwable was created/thrown in the target.

To test meaningful properties, prefer asserting stable information: exception class, business message, reference identity when a fixture exists, and `getCause()`. When you must inspect the stack, only confirm it contains a frame for the target method:

```java
// Illustrative snippet inside a test that already has Throwable original:
boolean containsTarget = java.util.Arrays.stream(
        original.getStackTrace())
        .anyMatch(frame -> frame.getMethodName()
                .equals("failRuntime"));
if (!containsTarget) {
    throw new AssertionError("Target stack frame missing");
}
```

Avoid comparing the entire `StackTraceElement[]`, source line numbers, or internal reflection implementation names, as the JVM/JDK or optimizer may alter those details. If the target modifies its stack with `setStackTrace`, disables stack traces, or reuses an exception with an old stack, that is a specific contract of the target to test accordingly, not a reason for all tests to expect identical stacks.

`Throwable.getCause()` may itself hold another exception created by the target; distinguish them:

```text
InvocationTargetException    ← wrapper created by reflection
  └─ IllegalStateException   ← actual exception thrown by target code
       └─ IOException        ← deeper cause attached by target code
```

When tracing root causes, **do not skip** the wrapper layer without recording which `Method` was invoked, yet do not let the wrapper obscure the inner business error type.

## 8. Common Mistakes When Writing Tests and Adapters

| Mistake | Consequence | How to check/fix |
| --- | --- | --- |
| `assertThrows(TargetException.class, () -> method.invoke(...))` | Test asserts the wrong exception layer | Assert `InvocationTargetException`, then inspect `getCause()` |
| Comparing only the wrapper message | Does not prove the original Throwable | Assert cause type, message, and identity if a fixture exists |
| Calling wrong overload/arguments and thinking the target threw | Direct `IllegalArgumentException` | Check a marker confirming the target body ran |
| Looking up wrong method and mixing `NoSuchMethodException` into invoke test | Target execution path is never tested | Separate lookup tests and invoke tests |
| Calling `getCause().getCause()` without checks | Potential `NullPointerException` if cause chain is short | Assert each layer per contract |
| Swallowing `InvocationTargetException` or logging only the wrapper | Loses business error context | Log cause, preserve stack and method context; decide unwrap policy explicitly |
| Unwrapping via `new RuntimeException(original.getMessage())` | Loses original identity, type, and stack | Rethrow `original` when API allows, or use `new RuntimeException("context", original)` to preserve cause |
| Testing with a `static lastThrown` field in parallel test suites | Race makes identity assertions flaky | Isolated fixtures, sequential runs, or proper synchronization |
| Invoking a private method without granting access | Test fails at the access layer | Use a public target to test the wrapper; test private access in a dedicated test |
| Asserting the entire stack trace | Brittle, JDK-dependent test | Check essential frames/properties only |
| Assuming all dynamic invocation mechanisms wrap errors with this wrapper | Incorrect analysis for `MethodHandle.invokeExact` or direct Java calls | Distinguish APIs; test each API's exception rules separately |

### When Building an Unwrap Helper, Preserve the Throwable

`Method.invoke` returns a wrapper exception to distinguish reflection code from exceptions inside the target. An adapter may want to **explicitly** surface the target exception back to the business boundary:

```java
static Object invokeAndRethrow(
        Method method, Object target, Object... arguments)
        throws Throwable {
    try {
        return method.invoke(target, arguments);
    } catch (InvocationTargetException e) {
        throw e.getCause();
    }
}
```

This is an illustrative snippet requiring imports for `Method`/`InvocationTargetException`, not a complete program. Declaring `throws Throwable` makes clear that the cause may be a checked exception, unchecked exception, **or `Error`**. In real application code, callers need a forwarding policy, checked exception declarations, and appropriate logging. Never catch every `Throwable` and continue silently after a serious error.

If the adapter interface only declares a narrow checked exception type, you may need to map exceptions per that contract. Whenever you must re-wrap, always set the original as the **cause** rather than merely copying its message.

## 9. Other API Cases: Do Not Apply Mechanically

- `Constructor.newInstance(...)` can also throw `InvocationTargetException` when the target constructor throws an exception, while errors before running the constructor must be separated.
- `MethodHandle.invoke` and `invokeExact` do not follow `Method.invoke`'s `InvocationTargetException` wrapping rule; they have their own contract and typically pass Throwables directly to the caller.
- Reflection calls may go through other proxies/adapters: an outer layer (e.g., dynamic proxy, future) can add its own wrapper. Tests must identify **which layer creates each wrapper** and verify the appropriate layer.
- `InvocationTargetException` itself is a class with public constructors; if the target explicitly throws an object of this type via `Method.invoke`, there will be an **outer wrapper** and a target exception on the inner layer. Do not classify causes solely by class name without knowing the call chain.

## 10. Regression Testing Checklist

Before finalizing tests:

1. Have you proved the target method actually ran and threw the expected error?
2. Have you asserted the outer `InvocationTargetException` wrapper?
3. Is `getCause()` non-`null`, with the right type, message, and **same Throwable** when a reference exists?
4. Does `getTargetException()` have the same identity as `getCause()`?
5. Is a deeper cause chain preserved when the target sets a cause?
6. Is there a separate test for wrong receiver/arguments to avoid confusing reflection errors with target errors?
7. For an unwrap helper, have you verified the original exception is surfaced without being recreated?
8. Does the test run reliably on Java 17+, without depending on volatile stack trace details?
9. If using JUnit 5, are runner and dependencies declared; if using a standalone harness, does stdout match accurately?
10. Have you avoided shared test state that causes wrong results under parallel execution?

## 11. Self-Check

**Question 1.** Target code calls `throw new IllegalArgumentException("bad")`. What does a caller using `Method.invoke` catch?

**Answer:** `InvocationTargetException` on the outside, with `IllegalArgumentException` as `getCause()`.

**Question 2.** The caller passes `String` into an `int` parameter of `Method.invoke` and the target has not run. Is there an `InvocationTargetException`?

**Answer:** No; this is a reflection argument error, typically a direct `IllegalArgumentException`.

**Question 3.** Do `getCause()` and `getTargetException()` on a wrapper created by `Method.invoke` return two copies of the exception?

**Answer:** No. They return the exact same target exception object; you can verify with `==` or JUnit `assertSame`.

**Question 4.** Target throws an `IOException` whose cause is `IllegalStateException`. Does the wrapper lose the cause chain?

**Answer:** No. The new wrapper points to `IOException`; `IOException` itself retains the established cause relationship.

**Question 5.** If an adapter needs to rethrow the original error, what should it do?

**Answer:** Catch `InvocationTargetException` and `throw e.getCause()` when the API signature permits; if forced to re-wrap, always attach the original cause.

**Takeaway:** With `Method.invoke`, **test two layers**: the `InvocationTargetException` wrapper describes the reflection mechanism, while `getCause()` is the exception/error actually thrown by target code. Quality tests verify **type, identity, message, cause chain, and the pre/post-target-execution boundary**.

References: [Java 17 `Method.invoke`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)), [`InvocationTargetException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html), [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/).