# Testing Suppressed Exceptions and Resource Close Order in Java

## 1. Learning Objectives

When using `try-with-resources`, Java closes resources automatically, but a proper test should not merely verify that resources were closed. You need to verify the **close order**, **which exception is the primary error**, **which exceptions are placed into `getSuppressed()`**, and whether Java continues attempting to close other resources after one `close()` fails.

A simple example:

```java
try (Resource a = openA();
     Resource b = openB();
     Resource c = openC()) {
    doWork();
}
```

This is an **illustrative code snippet**; you must define `Resource` and the called methods yourself. For resources that have been initialized successfully, the normal order is:

```text
Open:  A → B → C
Body:  doWork()
Close: C → B → A
```

If `doWork()` throws exception E and the `close()` calls also throw, Java prioritizes keeping **E as the primary exception**. Close failures are attached to E as **suppressed exceptions**, preventing the original error from being lost while preserving diagnostic data about cleanup failures.

If the `try` body succeeds but the first `close()` throws an exception, the exception from that `close()` becomes the **primary exception**; subsequent resource close errors are added to its suppressed list.

This lesson uses a **compilable/runnable** Java 17+ example, verifies event order and the suppressed list via automated checks, and demonstrates how to write JUnit tests, edge cases, and common implementation mistakes.

## 2. Concepts to Distinguish

**Primary exception** is the `Throwable` chosen as the main failure of the entire `try-with-resources` block. When the block body throws an exception, the body error is usually primary. When the body succeeds, the first close failure that occurs becomes primary if any close error happens.

**Suppressed exception** is a `Throwable` attached to the primary exception via `Throwable.addSuppressed(...)`, typically representing secondary failures that occur while closing the remaining resources. It can be retrieved using `Throwable.getSuppressed()`.

**Cause** is the `getCause()` relationship, typically representing "this error was caused by another error" when an application wraps an exception using a constructor like `new Exception(message, cause)`. Suppressed is **not** cause; both exist independently on the same `Throwable`.

**LIFO (Last In, First Out)** in the context of resource closing means that resources declared/initialized later are closed first.

**Cleanup failure** is an error from `close()`, `finally`, rollback, or another cleanup action. Not every cleanup failure is automatically attached as suppressed by Java; the standard behavior discussed here applies specifically to `try-with-resources` and situations using `addSuppressed`.

**AutoCloseable** is the Java interface with a `close()` method. The `Closeable` type in `java.io` extends `AutoCloseable` and uses a narrower exception type in its `close()` signature. Resources must conform to their close contract; not every `close()` performs only a trivial operation.

## 3. Ordering Rules of try-with-resources

Java processes the resource specification in two opposite directions:

1. Initializers in the header are evaluated **from left to right**.
2. The `try` body starts only after the required initializers complete.
3. Upon exiting the block, resources that were successfully initialized have `close()` called **from right to left**.
4. Java still attempts to close earlier resources when a close operation throws an exception.
5. Any `catch`/`finally` blocks placed **after** the `try-with-resources` body execute after the resource close attempts, according to statement semantics.

Example:

```java
try (InputStream in = openInput();
     OutputStream out = openOutput()) {
    copy(in, out);
} catch (IOException ex) {
    report(ex);
}
```

This is a **code snippet** that requires importing `java.io.InputStream`, `OutputStream`, `IOException`, and the application methods. If both have been initialized, the close order is `out.close()` followed by `in.close()`. By the time execution enters the `catch` outside the resource header, close attempts for both have already been made.

Close order can matter when a wrapper depends on an underlying resource. For example, a stream built on top of another stream should generally be created later and closed first. However, many wrappers have a `close()` that **also closes the delegate**: do not arbitrarily manage the same resource twice without checking its idempotency/double-close contract.

## 4. Case A: The try Body Fails and close Also Fails

Suppose the `try` body throws `IllegalArgumentException("body-failed")`, and then all three resources `C`, `B`, `A` throw in `close()`. Java keeps one primary exception, which is the body error:

```text
PRIMARY
  IllegalArgumentException("body-failed")
    SUPPRESSED
      IllegalStateException("close-C-failed")
      IllegalStateException("close-B-failed")
      IllegalStateException("close-A-failed")
```

The events occur in chronological order:

```text
open-A
open-B
open-C
body
throw body-failed
close-C  -> throw close-C-failed  -> suppressed
close-B  -> throw close-B-failed  -> suppressed
close-A  -> throw close-A-failed  -> suppressed
propagate body-failed
```

**Test point:** `getMessage()` of the primary exception remains `body-failed`, `getSuppressed().length == 3`, and the messages of the elements are in the order `C, B, A`. Do not conclude that because `close-C` failed, `close-B` and `close-A` did not run.

Note: the suppressed list records errors in **the order they are added** during cleanup. For `close()` calls that throw directly in this example, this matches the reverse close order. If code manually adds other suppressed exceptions or wrappers have nested cleanup, you need to analyze the exact structure rather than generalizing that every `getSuppressed()` array in every program always reflects only the resource header close order.

## 5. Case B: Body Succeeds, Multiple close Calls Fail

If the body completes normally but `C.close()` fails first, `C` is treated as the primary exception:

```text
PRIMARY
  IllegalStateException("close-C-failed")
    SUPPRESSED
      IllegalStateException("close-B-failed")
      IllegalStateException("close-A-failed")
```

Order:

```text
open-A
open-B
open-C
body completed normally
close-C  -> failure becomes primary
close-B  -> failure suppressed on close-C failure
close-A  -> failure suppressed on close-C failure
propagate close-C-failed
```

**Tests must distinguish body errors from close errors.** Not every exception escaping `try-with-resources` is an error in the body. If a read/write task completes and then `close` encounters a flush/commit failure, the state of the data must be verified; you should not automatically assume the body did not execute.

With `OutputStream` or buffered resources, some write errors may only surface **at flush/close time**, not during the earlier `write` call. Therefore, asserting that the body ran is not equivalent to asserting that all data was durably persisted.

## 6. Case C: Opening a Later Resource Fails

Suppose `A` and `B` have been initialized, but creating `C` throws an exception. Then:

- The `try` body **does not run**.
- `C` was not initialized successfully, so **there is no resource C in the header for Java to call close on**.
- Previously initialized resources (`B`, `A`) are still closed in reverse order.
- The exception thrown by initializing `C` is **primary**.
- If `B.close()` and `A.close()` also fail, they are attached as suppressed in the order `B` then `A`.

```text
open-A
open-B
attempt to open C -> throw open-C-failed
close-B -> suppressed close-B-failed
close-A -> suppressed close-A-failed
propagate open-C-failed
```

A constructor may allocate internal resources and then throw before returning the object. In that case, `try-with-resources` **cannot automatically call `close()` on an object that was never successfully registered**. The constructor/factory must manage rollback and cleanup of its own temporary resources. This is a case that needs dedicated testing when building complex resources.

## 7. Standalone Java 17+ Program with Automated Verification

The following example uses a custom `AutoCloseable`, an event list, exceptions with easily recognizable messages, and a `verify(...)` helper. It tests **three cases**: body error + close errors, close errors only, and initialization error. If any result is incorrect, the program throws `AssertionError` instead of printing `TESTS: PASS`.

Create the file **`SuppressedCloseOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class SuppressedCloseOrderDemo {
    private static final List<String> EVENTS = new ArrayList<>();

    static final class NamedResource implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;

        NamedResource(String name, boolean failOnClose) {
            this.name = name;
            this.failOnClose = failOnClose;
            EVENTS.add("open-" + name);
        }

        @Override
        public void close() {
            EVENTS.add("close-" + name);
            if (failOnClose) {
                throw new IllegalStateException("close-" + name + "-failed");
            }
        }
    }

    static NamedResource failToOpen(String name) {
        EVENTS.add("open-attempt-" + name);
        throw new IllegalArgumentException("open-" + name + "-failed");
    }

    static Throwable runBodyCase(boolean failBody) {
        EVENTS.clear();
        try (NamedResource a = new NamedResource("A", true);
             NamedResource b = new NamedResource("B", true);
             NamedResource c = new NamedResource("C", true)) {
            EVENTS.add("body");
            if (failBody) {
                throw new IllegalArgumentException("body-failed");
            }
        } catch (Exception ex) {
            return ex;
        }
        throw new AssertionError("Expected a failure");
    }

    static Throwable runInitCase() {
        EVENTS.clear();
        try (NamedResource a = new NamedResource("A", true);
             NamedResource b = new NamedResource("B", true);
             NamedResource c = failToOpen("C")) {
            EVENTS.add("body");
        } catch (Exception ex) {
            return ex;
        }
        throw new AssertionError("Expected initialization failure");
    }

    static String suppressed(Throwable error) {
        return Arrays.stream(error.getSuppressed())
                .map(Throwable::getMessage)
                .collect(Collectors.joining(","));
    }

    static void verify(String actual, String expected) {
        if (!expected.equals(actual)) {
            throw new AssertionError("Expected: " + expected + ", actual: " + actual);
        }
    }

    public static void main(String[] args) {
        Throwable bodyError = runBodyCase(true);
        String bodyEvents = String.join(",", EVENTS);
        verify(bodyEvents, "open-A,open-B,open-C,body,close-C,close-B,close-A");
        verify(bodyError.getMessage(), "body-failed");
        verify(suppressed(bodyError),
                "close-C-failed,close-B-failed,close-A-failed");
        System.out.println("BODY_EVENTS: " + bodyEvents);
        System.out.println("BODY_PRIMARY: " + bodyError.getMessage());
        System.out.println("BODY_SUPPRESSED: " + suppressed(bodyError));

        Throwable closeError = runBodyCase(false);
        String closeEvents = String.join(",", EVENTS);
        verify(closeEvents, "open-A,open-B,open-C,body,close-C,close-B,close-A");
        verify(closeError.getMessage(), "close-C-failed");
        verify(suppressed(closeError), "close-B-failed,close-A-failed");
        System.out.println("CLOSE_EVENTS: " + closeEvents);
        System.out.println("CLOSE_PRIMARY: " + closeError.getMessage());
        System.out.println("CLOSE_SUPPRESSED: " + suppressed(closeError));

        Throwable initError = runInitCase();
        String initEvents = String.join(",", EVENTS);
        verify(initEvents, "open-A,open-B,open-attempt-C,close-B,close-A");
        verify(initError.getMessage(), "open-C-failed");
        verify(suppressed(initError), "close-B-failed,close-A-failed");
        System.out.println("INIT_EVENTS: " + initEvents);
        System.out.println("INIT_PRIMARY: " + initError.getMessage());
        System.out.println("INIT_SUPPRESSED: " + suppressed(initError));
        System.out.println("TESTS: PASS");
    }
}
```

Compile and run from the directory containing the file, using JDK 17 or later:

```bash
javac -encoding UTF-8 SuppressedCloseOrderDemo.java
java SuppressedCloseOrderDemo
```

**Standard output verified with `javac` and `java`:**

```text
BODY_EVENTS: open-A,open-B,open-C,body,close-C,close-B,close-A
BODY_PRIMARY: body-failed
BODY_SUPPRESSED: close-C-failed,close-B-failed,close-A-failed
CLOSE_EVENTS: open-A,open-B,open-C,body,close-C,close-B,close-A
CLOSE_PRIMARY: close-C-failed
CLOSE_SUPPRESSED: close-B-failed,close-A-failed
INIT_EVENTS: open-A,open-B,open-attempt-C,close-B,close-A
INIT_PRIMARY: open-C-failed
INIT_SUPPRESSED: close-B-failed,close-A-failed
TESTS: PASS
```

### Reading the Verification Output

- `BODY_EVENTS` proves opening `A,B,C` from left to right, executing the body, and then closing `C,B,A` in LIFO order.
- `BODY_PRIMARY` is the body error; the suppressed order is `C,B,A`.
- `CLOSE_PRIMARY` is the error in `C.close()` because the body did not fail; `B` and `A` were still called.
- `INIT_EVENTS` shows **no `body` and no `close-C`**, because initialization of C did not succeed; B/A still closed.
- The `verify` method checks exact values. If the event order changes or a suppressed exception is missing, the check throws `AssertionError` and does not print `TESTS: PASS`.
- Each case clears `EVENTS` before running; resources always run sequentially on the main thread, so the demo does **not** rely on nondeterministic scheduling order.
- The exceptions from `close()` are `IllegalStateException` (unchecked), so the overridden `close()` method does not need to declare `throws Exception`. A real resource may use checked exceptions and must be handled with an appropriate signature.

Use this test suite to learn **Java rules**, not by using fake `NamedResource` as production resources. Real-world operations such as DB connections, stream flushes, and socket closes can have side effects, timeouts, or their own semantics.

## 8. Writing a JUnit 5 Test: Asserting Order and Suppressed Exceptions

When turning the example into a real test, you can use **JUnit Jupiter (JUnit 5)**. The following snippet is an *illustrative test method* that must be placed inside a test class with the JUnit 5 library and appropriate imports added. It is not a standalone Java SE program:

```java
@Test
void bodyFailureKeepsCloseErrorsSuppressed() {
    List<String> events = new ArrayList<>();

    class R implements AutoCloseable {
        final String name;
        R(String name) {
            this.name = name;
            events.add("open-" + name);
        }
        @Override
        public void close() {
            events.add("close-" + name);
            throw new IllegalStateException("close-" + name);
        }
    }

    IllegalArgumentException thrown = assertThrows(
            IllegalArgumentException.class, () -> {
                try (R a = new R("A");
                     R b = new R("B");
                     R c = new R("C")) {
                    events.add("body");
                    throw new IllegalArgumentException("body");
                }
            });

    assertEquals("body", thrown.getMessage());
    assertEquals(List.of(
            "open-A", "open-B", "open-C", "body",
            "close-C", "close-B", "close-A"), events);
    assertEquals(List.of("close-C", "close-B", "close-A"),
            Arrays.stream(thrown.getSuppressed())
                  .map(Throwable::getMessage)
                  .toList());
}
```

Required imports (not part of the method above):

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
```

In this JUnit test, three independent factors are verified:

1. **Primary type and message:** `assertThrows(IllegalArgumentException.class, ...)` and `getMessage()`.
2. **Lifecycle order:** the event list must match completely from open to close.
3. **Suppressed order:** `getSuppressed()` contains the errors from C, B, A.

If you only assert `thrown.getSuppressed().length == 3`, you can still miss a bug where `close()` is called in the wrong order. If you only assert events, you can miss a bug where **errors are not preserved**. Combining both creates a more useful test.

Use `assertThrowsExactly` when you need to distinguish the exact error type and your JUnit version supports it; `assertThrows` accepts subtypes of the expected type as well. There is no need to assert the full stack trace text because frame names and source lines can change across compilers/runtimes.

## 9. Test Matrix to Cover

| Scenario | Expected Primary | Suppressed | Close Order |
| --- | --- | --- | --- |
| Body succeeds, all closes succeed | No exception | Empty | C → B → A |
| Body fails, all closes succeed | Body error | Empty | C → B → A |
| Body fails, only C close fails | Body error | C | C → B → A |
| Body fails, C and A close fail | Body error | C then A | C → B → A |
| Body fails, all three closes fail | Body error | C then B then A | C → B → A |
| Body succeeds, C close fails | close-C error | Empty | C → B → A |
| Body succeeds, C/B/A closes fail | close-C error | B then A | C → B → A |
| Initializing C fails, B/A closes succeed | C initialization error | Empty | B → A |
| Initializing C fails, B/A closes fail | C initialization error | B then A | B → A |
| Initializing A fails | A initialization error | Usually empty; depends on design if constructor adds errors | No initialized header resources to close |
| Header contains a null resource reference | Depends on body and other resources | No close error for the null resource | Null resource is skipped |

This is a **matrix for designing tests**; not every system needs a separate test for each row if already covered by parameterized tests or component contracts. For resource-management libraries, initialization-failure and close-failure cases are the most important because bugs may only appear on rare failure paths.

A good strategy is to create a `FakeResource` supporting three options: no error, initialization error, and close error, then run the necessary combinations. Each test must explicitly check **primary**, **getSuppressed()**, and **event order** rather than looking at a single "closed" boolean.

## 10. How Suppressed Exceptions Differ from Cause

Two `Throwable` APIs:

```java
Throwable cause = error.getCause();
Throwable[] cleanupFailures = error.getSuppressed();
```

This is a code snippet inside a method that has `Throwable error`.

- `getCause()` points to a single causal link when an exception is wrapped or assigned a cause.
- `getSuppressed()` returns an **array** of `Throwable`s attached via `addSuppressed`, such as errors that occurred while closing remaining resources.
- **Both cause and suppressed can exist on the same `Throwable`**.
- A suppressed exception can also have its own **cause** and **suppressed** exceptions, creating a multi-level error structure.

Example:

```text
OrderProcessingException (primary)
  Caused by: SQLException
  Suppressed: IOException("close output")
  Suppressed: IOException("close input")
```

This is an illustrative structure, not mandatory output from a runtime. `cause` describes the business-level source of failure, whereas suppressed records cleanup errors that **should not replace the primary cause**.

If you use `logger.error("failed", error)`, many logging frameworks print both suppressed exceptions and cause. When investigating, do not ignore the `Suppressed: ...` lines of a stack trace. Also do not confuse "suppressed" with "safely handled and ignorable": a close failure can involve data loss, locks, transactions, or unreleased resources.

## 11. Approximate Mechanism Generated by the Compiler

`try-with-resources` is not simply:

```java
try {
    body();
} finally {
    resource.close();
}
```

This manual `finally` pattern **can allow an exception from `close()` to mask an exception from `body()`**, so it does not preserve the suppressed behavior of try-with-resources.

Conceptually, for a single resource, the compiler needs a primary `Throwable` and handles close errors along these lines:

```java
Throwable primary = null;
try {
    body();
} catch (Throwable thrown) {
    primary = thrown;
    throw thrown;
} finally {
    if (resource != null) {
        if (primary != null) {
            try {
                resource.close();
            } catch (Throwable closeFailure) {
                primary.addSuppressed(closeFailure);
            }
        } else {
            resource.close();
        }
    }
}
```

This is **structurally approximate pseudocode**, not a standalone program; `resource` and `body()` are assumed to exist. It helps explain why the body error remains prioritized and secondary close errors are added to the primary. Do not copy this snippet to replace Java syntax: real generated code must handle multiple resources, scopes, initialization, exception types, and other language details.

When multiple resources are declared, you can think of it conceptually as multiple nested `try-with-resources` layers, ensuring **reverse close order**. Remember that resources are already closed before any outer `catch`/`finally` runs.

Why can generated code catch `Throwable`? Because it must preserve the primary regardless of what kind of `Throwable` the body throws, **unlike the advice against writing `catch (Throwable)` in the business layer and swallowing all errors**. This is a detail of the compiler mechanism, not a policy to "recover from every `Error`".

## 12. Testing Close When Resource Initialization Fails

Not only the `try` body, but also an **initializer** can throw an exception:

```java
try (Connection con = openConnection();
     PreparedStatement ps = con.prepareStatement(sql);
     ResultSet rs = ps.executeQuery()) {
    consume(rs);
}
```

This is an **illustrative JDBC code snippet** requiring imports for `java.sql.Connection`, `PreparedStatement`, `ResultSet`, and methods/variables `openConnection`, `sql`, `consume`. If `ps.executeQuery()` throws an error while initializing `rs`:

- `rs` has not been recognized as a successfully initialized resource, so it is not closed by the header.
- `ps` is closed.
- `con` is closed.
- If `ps.close()` and `con.close()` throw, they can appear in the suppressed list of the exception from `executeQuery()`.

Unit tests can use fake JDBC or controlled mocks, while integration tests with a real driver still need to verify **transaction semantics, rollback, and connection pooling**. Do not assume `Connection.close()` is equivalent to transaction rollback in every situation; it depends on the driver and transaction configuration.

If a resource's constructor/factory throws after opening an internal file descriptor, it must clean up what it allocated; TWR cannot call `close()` on a variable that was never successfully assigned.

## 13. Close Order with Nested Resources and Wrappers

Two syntaxes can be equivalent in order if there are no other side effects:

```java
try (A a = createA();
     B b = createB(a)) {
    use(b);
}
```

and a nested structure:

```java
try (A a = createA()) {
    try (B b = createB(a)) {
        use(b);
    }
}
```

Both are **code snippets requiring application types/methods to be defined**; `b` closes before `a` when both have been created.

However, a wrapper `B` may automatically close `A` when `B.close()` is called. In that case, if both are also in the header, `A.close()` may be called an additional time. For resources with idempotent close, this may have no effect. For other resources, a double close may throw an error or cause side effects. Testing must be based on **the actual contract of the wrapper/delegate**, not only language rules.

### External Resources Since Java 9

Java 9+ allows using a previously declared resource variable if it is final or effectively final:

```java
InputStream in = Files.newInputStream(path);
try (in) {
    use(in);
}
```

This is a **code snippet** requiring imports for `java.io.InputStream`, `java.nio.file.Files`, and `Path`; the enclosing method must handle `IOException`. Upon exiting `try`, `in` is already closed, even though the variable remains in scope. Do not continue using that stream as if it were still open, and do not wrap it in a second `try` to close it again if the resource type does not allow it.

In all cases, close order still depends on the **resource specification of each `try`**, along with the nesting structure.

## 14. Null Resource References, Non-Idempotent Close, and Edge Cases

TWR can have a `null` resource reference:

```java
AutoCloseable maybeResource = null;
try (maybeResource) {
    perform();
}
```

This is a Java 9+ code snippet with `perform()` defined by the application; if `maybeResource` is not reassigned, it is effectively final. Java **does not call `close()`** on a null resource reference, so no `NullPointerException` is automatically raised solely by the close step for that reference.

However, **a null resource should not be treated as ideal API design**. If the presence of a resource is mandatory, validate early with `Objects.requireNonNull` or design the factory to return a meaningful value.

Some edge cases to test according to system requirements:

- Non-idempotent `close()`: calling it twice may throw an error or mutate state.
- `close()` with order dependencies: wrapper/delegate, transaction/session, stream/filter.
- `close()` blocking for a long time or never returning: TWR only guarantees **attempting to call**, with no default deadline.
- `close()` throwing `Error` instead of a checked exception: suppression mechanics can involve `Error` `Throwable`s; do not catch them and continue.
- `close()` mutating data or flushing: a failure on close can be critical even when the body succeeds.
- Cleanup manually attaching suppressed exceptions via `addSuppressed`: inspect the contents rather than only counting them.
- A resource shared across multiple owners: do not let two owners both believe they are responsible for closing it.

Unusual failure scenarios should be tested with fake resources, while driver/native resource semantics require integration tests.

## 15. Notes on Throwable.addSuppressed

`Throwable.addSuppressed(Throwable exception)` adds a secondary `Throwable` to the current object. Key points to remember:

- `getSuppressed()` returns an array of attached exceptions; it is not `getCause()`.
- `addSuppressed(null)` throws `NullPointerException`.
- Self-suppression (suppressing a `Throwable` onto itself) is not allowed; the operation may throw `IllegalArgumentException`.
- Some subclasses can use a special `Throwable` constructor to **disable suppression**; in that case, `getSuppressed()` does not retain added errors in the usual way.
- In application code that manages cleanup manually, be careful to preserve the meaningful primary exception. By default, TWR handles this standard case better.

An **extreme self-suppression case** can occur if a resource's `close()` deliberately rethrows **the exact same `Throwable` instance** that was thrown from the body. This is not a normal close contract. Do not assume every faulty or misbehaving resource follows a simple error model; another error may arise from the suppression operation itself.

In other words, a resource should produce a new/appropriate exception when close fails, rather than reusing the same `Throwable` instance that is currently the primary.

## 16. finally and catch Outside try-with-resources

Consider:

```java
try (Resource r = open()) {
    work();
} catch (Exception ex) {
    inspect(ex.getSuppressed());
} finally {
    recordCompletion();
}
```

This is a code snippet with type `Resource` and methods `open`, `work`, `inspect`, `recordCompletion`. When `catch` receives the exception, Java has already attempted `r.close()`. If the body failed and close also failed, `catch` can read suppressed exceptions directly at that point.

**Warning:** if your `catch` or `finally` **throws a new exception**, or `recordCompletion()` throws, the final observed error may be different and mask the original cause if not preserved. `try-with-resources` manages errors from **resource closes in the header**; it does not automatically preserve every exception arising from any `finally` block you write yourself.

Bad example:

```java
try (Resource r = open()) {
    work();
} finally {
    throw new IllegalStateException("reporting failed");
}
```

This is a **discouraged** snippet. It deliberately throws in `finally` and can prevent the primary error from the body/close from being the propagated exception. When writing additional observability/metrics/cleanup code, ensure you do not accidentally replace important errors or make logs unreliable.

## 17. Reading Stack Traces and Suppressed Structure

Java's `Throwable.printStackTrace()` typically displays suppressed exceptions with the label `Suppressed:`, as illustrated below:

```text
java.lang.IllegalArgumentException: body-failed
    at Demo.work(Demo.java:10)
    Suppressed: java.lang.IllegalStateException: close-C-failed
        at Demo$Resource.close(Demo.java:25)
    Suppressed: java.lang.IllegalStateException: close-B-failed
        at Demo$Resource.close(Demo.java:25)
    Suppressed: java.lang.IllegalStateException: close-A-failed
        at Demo$Resource.close(Demo.java:25)
```

This is only an **illustrative stack trace**, not the output of `SuppressedCloseOrderDemo.java`, and line numbers/formatting are not guaranteed. In real systems, logging frameworks may be configured to limit stack traces; collectors or APM tools may drop suppressed sections if unsupported or truncated.

When investigating an error, ask:

1. Is the primary exception a body, initializer, or close error?
2. How many elements are in the suppressed list, and in what order?
3. Does each suppressed exception have its own cause/suppressed exceptions?
4. Which resources were closed, and which were never successfully initialized?
5. If close failed, is there unflushed data or an incomplete transaction?

In logs containing real data, check policies protecting **secrets and personal information**: cause/suppressed messages from drivers may contain URLs, SQL, tokens, or payloads. Do not automatically expose entire `Throwable`s in HTTP responses or broad-access sinks just to inspect suppressed exceptions.

## 18. Common Testing Mistakes

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Asserting only that an exception was thrown | Cannot tell whether it is a body error or close error | Assert type, message/cause, suppressed, and event order |
| Assuming resources close in A → B → C order | Violates header LIFO | Verify C → B → A |
| Thinking close-C failing skips close-B/A | TWR still attempts to close remaining resources | Have fake resources record events for every close |
| Checking suppressed via `getCause()` | Cause and suppressed are two different relationships | Use `getSuppressed()` |
| Asserting suppressed count while ignoring order | Misses wrong close-order bugs | Assert the message array in order |
| Treating all close errors as always suppressed | If the body succeeds, the first close error is primary | Also test the body-succeeds case |
| Ignoring mid-header initialization failures | Earlier resources must still be closed | Test init failures at A/B/C |
| Using real DB/network close to force timing errors | Slow, flaky, hard to predict | Unit test with fakes, separate integration tests |
| Wrapping with `catch (Throwable)` and swallowing all | Can hide `Error` and produce wrong results | Rely on TWR, classify errors at boundaries |
| Writing manual `finally` and letting close mask body exception | Loses the primary cause | Use `try-with-resources` |
| Testing against full stack trace text | Depends on version/source lines | Assert `Throwable` API and events |
| Assuming successful close means data is durably committed | Resource APIs have their own semantics | Test transaction/flush/durability separately |

## 19. Unit Test and Integration Test Strategy

**Unit tests** are the best place to verify Java mechanics, using fake resources with controlled behavior:

- Collect a list of `open-X`, `body`, `close-X` events.
- Trigger errors in body/initializer/close via flags.
- Assert the primary exception type, message, `getSuppressed()`, and call order.
- Do not depend on network connections, drivers, filesystems, or clocks.

**Integration tests** additionally verify the real contract of resources:

- Under a connection pool, does `Connection.close()` return the handle to the pool or actually close the physical connection?
- Do `ResultSet`, `Statement`, and `Connection` have mutual auto-close relationships?
- Does `OutputStream.close()` flush data and report errors?
- How do transaction-bound resources roll back/commit when close fails?
- Do sockets, files, locks, and schedulers have appropriate timeouts/cancellation?

Do not use fake resources to "prove" JDBC rollback or file durability; fakes only test your application's logic and the programmed Java semantics.

Thread-related tests should have clear timeouts and synchronization. However, the closing rules of **a synchronous `try-with-resources` statement** do not require concurrency to test; spawning multiple threads does not improve the accuracy of resource header ordering and only makes results harder to reproduce.

## 20. Checklist Before Completing a Test

1. Identify the order of **successfully initialized** resources and the reverse close order.
2. Include cases for **body failure**, **body success with close failure**, and **initializer failure**.
3. Assert the primary exception from the right origin.
4. Assert each element of `getSuppressed()` for exact count, content, and order.
5. Verify that already-initialized resources are still attempted to be closed after a close failure.
6. Verify that resources that failed to initialize are not closed by the header.
7. For cleanup errors, do not confuse suppressed with cause and do not automatically swallow errors.
8. Check that outer `catch`/`finally` blocks do not replace the original error.
9. Distinguish demo/fake code from real-resource side effects.
10. Read stack traces, causes, and suppressed exceptions in a controlled manner to avoid leaking sensitive information.
11. Do not use full stack trace text as the primary assertion of a unit test.
12. For systems with DB/file/network, add integration tests for flush, rollback, close idempotency, and post-failure state.

**Remember:** resources in `try-with-resources` are **initialized from left to right and closed from right to left**. If the body or an initializer fails, that error usually remains **primary**, while close errors are recorded via `getSuppressed()`. If the body succeeds, the first close error becomes primary. A good test must verify **both event order and `Throwable` structure** so error information is not lost and cleanup is not assumed to have succeeded when it actually did not.
