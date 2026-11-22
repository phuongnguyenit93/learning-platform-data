# Reproducing a Primary Exception with Multiple Suppressed Exceptions

## 1. Practice Objectives

A Java failure does not necessarily consist of a single exception. When a program is performing work and encounters error A, and then resource cleanup also fails with B, C, and D, Java must decide **which error represents the primary failure** and **where to keep the remaining errors**. If you choose the wrong cleanup approach or only log a single exception at an outer layer, you can lose critical diagnostic evidence.

In this practice exercise, you will **deliberately reproduce a primary exception alongside multiple suppressed exceptions** using `try-with-resources` and a fake resource implementing `AutoCloseable`. There is no need to corrupt real files, sockets, or databases.

After completing this exercise, you will be able to:

1. Create multiple resources with a controlled initialization order.
2. Make the `try` body throw a primary `IOException`, while multiple `close()` calls also throw other `IOException` instances.
3. Observe Java closing resources **in reverse order of declaration** and continuing to close remaining resources after one `close()` fails.
4. Inspect the **primary** exception, as well as the count and order of `getSuppressed()`.
5. Distinguish between **resource initialization** errors, **work body** errors, and **resource closing** errors.
6. Prove that wrapping an exception with `new IllegalStateException(message, cause)` **does not automatically transfer suppressed exceptions from the cause to the wrapper**.
7. Write JUnit 5 assertions using `assertSame`, `assertEquals`, and an event history instead of merely checking that "an exception was thrown."
8. Understand the limitations of a fake: suppressed exceptions indicate that cleanup also failed, but they do not prove that a transaction was rolled back or that data was successfully flushed.

### Prerequisites

You should have a basic understanding of `try`, `catch`, `finally`, checked exceptions, `IOException`, and the `AutoCloseable` interface. The main example uses Java 17 syntax with **no external libraries**, and can be run with `javac --release 17`. The JUnit 5 snippets are clearly marked as fragments that require a project configured with JUnit.

**Core problem:** a single operation can encounter multiple errors at the same time, yet the caller needs one meaningful primary outcome. Secondary errors must not accidentally erase or replace the primary cause.

## 2. What Are Primary Exceptions and Suppressed Exceptions?

In a `try-with-resources` construct, Java takes responsibility for calling `close()` when exiting the scope. If multiple exceptions occur, one exception is the **primary** exception, and exceptions raised during cleanup can be **attached** via `Throwable.addSuppressed`.

Example scenario:

~~~text
Open A                     OK
Open B                     OK
Open C                     OK
Execute body               IOException("body failed")
Close C                    IOException("close C failed")
Close B                    IOException("close B failed")
Close A                    IOException("close A failed")

Exception thrown to the caller:
    primary:    IOException("body failed")
    suppressed: IOException("close C failed")
                IOException("close B failed")
                IOException("close A failed")
~~~

This is an **illustrative scenario diagram**, not the official output of the program. It demonstrates two rules:

- If the **body has already thrown an error**, that error remains the primary exception; subsequent `close()` errors are added to `getSuppressed()`.
- If the **body completes normally**, the first `close()` error in reverse closing order becomes the primary exception; subsequent closing errors are suppressed onto it.

The suppressed exceptions are **real diagnostic data**, not "exceptions that disappeared and can be forgotten." They can reflect failures to flush data, release a connection, return a resource to a pool, or close another handle.

### 2.1. How Does Cause Differ from Suppressed?

| Relationship | Java API | Common Meaning |
| --- | --- | --- |
| **Cause** | `getCause()`, constructor taking `cause` | The inner exception is the underlying cause of the outer exception |
| **Suppressed** | `getSuppressed()`, `addSuppressed()` | Secondary exceptions that occurred alongside a primary error, typically during cleanup |
| **Stack trace** | `getStackTrace()` | The stack frames recorded for each exception |

For example, `new IllegalStateException("Service failed", ioError)` creates a new exception whose cause is `ioError`. If `ioError` has three suppressed exceptions, those three errors **still belong to `ioError`**. By default, they are not copied onto `IllegalStateException`.

A primary exception can **simultaneously** have both a cause and suppressed exceptions. When diagnosing an issue, you must follow both branches of information, not just `getCause()`.

## 3. Why Use a Fake Resource for Reproduction?

To trigger errors at the exact right moment, do not rely on a filesystem running out of space or a server randomly closing connections. That makes tests hard to reproduce and risky for data. Instead, create a class that can **deliberately throw exceptions** based on configuration flags.

A fake serving this purpose needs:

- Resource names `A`, `B`, `C` to distinguish them.
- An `events` list recording the order `open:A`, `close:C`, ...
- `failOpen` to make the constructor throw `IOException`.
- `failClose` to make `close()` throw `IOException`.
- A work body that can deliberately throw its own exception.
- No threads, sleep, or network; the event sequence is **deterministic**.
- A fresh event list per scenario to avoid polluting results across tests.

Configuring a failure in the **constructor** only simulates an initializer failing to complete. It does not simulate every partial-allocation failure inside a constructor. The case where an internal resource is opened and then the constructor fails is discussed separately later.

## 4. Complete Java 17 Program

The `SuppressedPracticeDemo` program consists of four independent scenarios:

1. `bodyAndThreeClosesFail()` — the body throws an error, and all three `close()` calls also fail.
2. `secondOpenFails()` — A has opened, B fails to open, and Java must close A.
3. `onlyClosesFail()` — the body succeeds, but all three `close()` calls fail.
4. `wrappedFailure()` — the read error is wrapped; the suppressed exception remains on the original cause.

Save the entire code below as **`SuppressedPracticeDemo.java`**:

~~~java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public class SuppressedPracticeDemo {
    static final class TrackedResource implements AutoCloseable {
        private final String name;
        private final List<String> events;
        private final boolean failClose;

        TrackedResource(String name, List<String> events,
                        boolean failOpen, boolean failClose) throws IOException {
            this.name = name;
            this.events = events;
            this.failClose = failClose;
            events.add("open:" + name);
            if (failOpen) {
                throw new IOException("open " + name + " failed");
            }
        }

        @Override
        public void close() throws IOException {
            events.add("close:" + name);
            if (failClose) {
                throw new IOException("close " + name + " failed");
            }
        }
    }

    static String identify(Throwable error) {
        return error.getClass().getSimpleName() + ": " + error.getMessage();
    }

    static void report(String title, List<String> events, Throwable error) {
        System.out.println(title);
        System.out.println("events=" + String.join(", ", events));
        System.out.println("primary=" + identify(error));
        Throwable[] suppressed = error.getSuppressed();
        System.out.println("suppressed-count=" + suppressed.length);
        for (int i = 0; i < suppressed.length; i++) {
            System.out.println("suppressed[" + i + "]=" + identify(suppressed[i]));
        }
    }

    static void bodyAndThreeClosesFail() {
        List<String> events = new ArrayList<>();
        IOException original = new IOException("body failed");
        try (TrackedResource a = new TrackedResource("A", events, false, true);
             TrackedResource b = new TrackedResource("B", events, false, true);
             TrackedResource c = new TrackedResource("C", events, false, true)) {
            events.add("work");
            throw original;
        } catch (IOException error) {
            report("CASE body-and-close", events, error);
            System.out.println("same-primary-object=" + (error == original));
        }
    }

    static void secondOpenFails() {
        List<String> events = new ArrayList<>();
        try (TrackedResource a = new TrackedResource("A", events, false, true);
             TrackedResource b = new TrackedResource("B", events, true, false);
             TrackedResource c = new TrackedResource("C", events, false, true)) {
            events.add("work");
        } catch (IOException error) {
            report("CASE open-failure", events, error);
        }
    }

    static void onlyClosesFail() {
        List<String> events = new ArrayList<>();
        try (TrackedResource a = new TrackedResource("A", events, false, true);
             TrackedResource b = new TrackedResource("B", events, false, true);
             TrackedResource c = new TrackedResource("C", events, false, true)) {
            events.add("work:ok");
        } catch (IOException error) {
            report("CASE close-only", events, error);
        }
    }

    static void wrappedFailure() {
        List<String> events = new ArrayList<>();
        try (TrackedResource a = new TrackedResource("A", events, false, true)) {
            events.add("work");
            throw new IOException("read failed");
        } catch (IOException original) {
            IllegalStateException wrapper =
                    new IllegalStateException("service failed", original);
            report("CASE wrapped", events, wrapper);
            System.out.println("cause=" + identify(wrapper.getCause()));
            System.out.println("cause-suppressed-count="
                    + wrapper.getCause().getSuppressed().length);
        }
    }

    public static void main(String[] args) {
        bodyAndThreeClosesFail();
        secondOpenFails();
        onlyClosesFail();
        wrappedFailure();
    }
}
~~~

### 4.1. Compiling and Running

JDK 17 or newer is required. In the directory containing the file:

~~~bash
javac --release 17 SuppressedPracticeDemo.java
java SuppressedPracticeDemo
~~~

**Exact stdout verified by actual compilation and execution:**

~~~text
CASE body-and-close
events=open:A, open:B, open:C, work, close:C, close:B, close:A
primary=IOException: body failed
suppressed-count=3
suppressed[0]=IOException: close C failed
suppressed[1]=IOException: close B failed
suppressed[2]=IOException: close A failed
same-primary-object=true
CASE open-failure
events=open:A, open:B, close:A
primary=IOException: open B failed
suppressed-count=1
suppressed[0]=IOException: close A failed
CASE close-only
events=open:A, open:B, open:C, work:ok, close:C, close:B, close:A
primary=IOException: close C failed
suppressed-count=2
suppressed[0]=IOException: close B failed
suppressed[1]=IOException: close A failed
CASE wrapped
events=open:A, work, close:A
primary=IllegalStateException: service failed
suppressed-count=0
cause=IOException: read failed
cause-suppressed-count=1
~~~

This is the output of the exact program shown above when run standalone, without depending on machine paths, network addresses, or scheduler timing. If you change the resource names, number of resources, or exception messages, the output changes accordingly.

### 4.2. Factors That Make the Example Deterministic

- `events` are recorded on the same thread. There is no executor, no async callback, and no scheduling dependency.
- Each method creates its own `new ArrayList<>()`, so one scenario's history does not bleed into another scenario.
- Each `TrackedResource.close()` always records the event **before** throwing an error (if configured to fail).
- Each close exception has a message containing the resource name.
- The closing order is **defined by the Java language**: C → B → A.
- `IOException original` in the first scenario is created beforehand and thrown directly, allowing **object identity** to be checked via `error == original`.

This ensures that tests only fail when behavior genuinely differs from expectations, not because a machine is fast or slow.

## 5. Scenario 1 Analysis: One Primary and Three Suppressed

In `bodyAndThreeClosesFail()`, all three resources initialize successfully. The `try` body records `work` and then throws the **exact object** `original`.

Sequence of events:

~~~text
open A                  succeeded
open B                  succeeded
open C                  succeeded
work                    recorded event
throw original          IOException("body failed")
        |
        v
close C                 throws IOException("close C failed")
        |               -> original.addSuppressed(closeC)
        v
close B                 throws IOException("close B failed")
        |               -> original.addSuppressed(closeB)
        v
close A                 throws IOException("close A failed")
                        -> original.addSuppressed(closeA)
        |
        v
catch (IOException e)
e == original           true
e.getSuppressed()       [closeC, closeB, closeA]
~~~

Observations:
- `primary=IOException: body failed` — the body failure remains primary.
- `suppressed-count=3` — all three close errors are preserved.
- `suppressed[0]` is C, `[1]` is B, `[2]` is A — matching the reverse closing order.
- `same-primary-object=true` — Java does not force creating a new wrapper just because cleanup failed; in this scenario, the primary exception is the exact object thrown by the body.

**Key takeaway:** a single exception can hold **multiple** suppressed exceptions, not just one. If diagnostic code only calls `getSuppressed()[0]`, you will miss B and A. If logging code only prints `error.getMessage()`, the close failures vanish from the report.

### 5.1. What Happens If Only Two Closes Fail?

If you change `failClose` on resource B to `false`, Java still calls `B.close()`, but it does not throw. In that case:
- The event log **still contains** `close:B`.
- The primary exception is still `body failed`.
- Suppressed only contains close C and close A.
- The suppressed order is C then A; there is **no placeholder element** for the successful B.

Therefore, you cannot use the length of the suppressed array to infer how many resources were closed. It only reflects the number of attached secondary errors, not the total number of cleanup calls.

## 6. Scenario 2 Analysis: Initializer Failure and Suppressed Error from a Prior Resource

In `secondOpenFails()`:
- A opens successfully, but is configured with `failClose=true`.
- Constructor B records `open:B` and then throws `IOException("open B failed")`.
- C is never opened.
- The body is not executed.
- Java closes A; `A.close()` throws an error and is suppressed onto the open B error.

Diagram:

~~~text
try (A = new Resource(...);
     B = new Resource(...);
     C = new Resource(...)) {
    work();
}

A created OK
B constructor throws  <-- primary
C is not created
body does not run
A.close() throws      <-- suppressed
~~~

Therefore, stdout shows:

~~~text
events=open:A, open:B, close:A
primary=IOException: open B failed
suppressed-count=1
suppressed[0]=IOException: close A failed
~~~

**`close:B` does not appear** because constructor B did not return a complete resource for `try-with-resources` to register for closing. Neither `open:C` nor `work` appears because Java stops evaluating subsequent initializers as soon as B throws.

### 6.1. What If a Resource Is Partially Opened Inside a Constructor?

This is a different situation from A opening completely and B failing. For example, constructor B opens an internal file and then fails while reading the header. `try-with-resources` **does not automatically call `B.close()`** if constructor B has not finished.

The constructor or factory creating B must perform **internal cleanup when partial acquisition fails**. A factory design can use `try`/`catch` to close the newly created handle before throwing, keeping the initialization error as primary and attaching the close error via `addSuppressed()`.

However, ownership transfer must be designed carefully: if the factory returns the object successfully, the new object assumes responsibility for closing; if the factory fails, the factory retains ownership and must clean up the handles it created. Test fakes should separate the case where **initializer B fails to complete** from the case where **resource A fails to close afterward**.

## 7. Scenario 3 Analysis: Body Succeeds, but Close Fails

In `onlyClosesFail()`, the body only records `work:ok` and throws no exception. However, when exiting the scope:

1. `C.close()` is called first and throws `IOException("close C failed")`.
2. Java records close C as **primary** because there is no body exception.
3. `B.close()` is called next; its error is suppressed onto primary C.
4. `A.close()` is also called and suppressed.

Key output:

~~~text
events=open:A, open:B, open:C, work:ok, close:C, close:B, close:A
primary=IOException: close C failed
suppressed-count=2
suppressed[0]=IOException: close B failed
suppressed[1]=IOException: close A failed
~~~

This is an important difference from Scenario 1. **The primary exception is not necessarily an exception from the body.** It is the first error that takes the primary role according to the `try-with-resources` execution and cleanup flow. When the body succeeds and close C fails, C becomes primary.

If the body finishes running and the code returns `"SUCCESS"` while `close()` is swallowed by an empty `catch`, the caller can receive false confirmation. For some output streams, a close failure can also affect buffered data that has not yet been flushed. However, you must not assume that **every** close failure causes data loss: that depends on the resource's contract.

### 7.1. When Only One Close Fails

If `C.close()` succeeds but `B.close()` fails, B is primary. If `A.close()` fails afterward, A is suppressed. If all of C, B, and A succeed, no exception is thrown from cleanup, and the body result can be returned normally.

Quick reference table:

| Body | Close C | Close B | Close A | Primary | Suppressed |
| --- | --- | --- | --- | --- | --- |
| Error X | Error C | Error B | Error A | X | C, B, A |
| Error X | OK | Error B | OK | X | B |
| OK | Error C | Error B | Error A | C | B, A |
| OK | OK | Error B | Error A | B | A |
| OK | OK | OK | Error A | A | None |
| OK | OK | OK | OK | None | None |

The column order in the table follows the **actual closing order**. Note that this is the reverse of the resource declaration order in the header.

## 8. Scenario 4 Analysis: A Wrapper Does Not Automatically Carry Its Cause's Suppressed Exceptions

In `wrappedFailure()`:
1. A opens normally.
2. The body throws `IOException("read failed")`.
3. `A.close()` throws `IOException("close A failed")`.
4. The original primary `read failed` has **one suppressed exception**: `close A failed`.
5. `catch` creates `new IllegalStateException("service failed", original)`.
6. The program prints information about both the **wrapper** and the **cause**.

Output:

~~~text
CASE wrapped
events=open:A, work, close:A
primary=IllegalStateException: service failed
suppressed-count=0
cause=IOException: read failed
cause-suppressed-count=1
~~~

What to understand:
- `wrapper.getSuppressed()` being empty in this scenario **does not mean cleanup succeeded**.
- `wrapper.getCause()` is the original `IOException`; `wrapper.getCause().getSuppressed()` has one error.
- Java **does not automatically copy** suppressed exceptions from a cause onto a new wrapper.
- A logging system must print the **cause chain and the suppressed exceptions of each throwable** if it wants complete evidence.

Do not fix this by mechanically "copying all suppressed exceptions onto every wrapper"; that can create duplicates, confuse causal relationships, or make reports harder to read. Preserving the cause properly is the natural way to retain the information.

### 8.1. How to Access Suppressed Exceptions Properly When a Wrapper Has a Cause

Illustrative fragment:

~~~java
Throwable primary = wrapper.getCause();
if (primary != null) {
    for (Throwable cleanupFailure : primary.getSuppressed()) {
        System.err.println("cleanup: " + cleanupFailure);
    }
}
~~~

`wrapper` is assumed to have been created from an exception with a cause. A `null` check is necessary because not every `Throwable` has a cause. For multi-layered exceptions, you need to traverse the various causes and inspect the suppressed exceptions of the **right `Throwable`**, not just the outermost wrapper.

## 9. Recommended Test Matrix

These are the key cases to cover when writing lifecycle tests:

| Case | Simulated Program | What to Assert |
| --- | --- | --- |
| 1 | A/B/C open successfully, body throws, C/B/A close all throw | Body is primary; suppressed C/B/A |
| 2 | A opens, B initializer throws, A.close throws | Init B is primary; suppressed A |
| 3 | A/B/C open successfully, body OK, C/B/A close throw | Close C is primary; suppressed B/A |
| 4 | Body throws, close A throws, wrapped in `IllegalStateException` | Wrapper cause is body `IOException`; suppressed is on cause |
| 5 | Body throws, all closes OK | Body is primary; suppressed is empty |
| 6 | Body OK, all closes OK | No exception; all resources closed |
| 7 | A init throws immediately | B/C not opened; body does not run |
| 8 | C init throws after A/B open | B then A must be closed |
| 9 | C init throws, B/A close both throw | Init C is primary; suppressed B/A |
| 10 | Body OK, only A.close throws | A is primary; suppressed is empty |
| 11 | Body throws, only B.close throws | Body is primary; suppressed B |
| 12 | Body executes `return`, close throws | Close exception can still prevent caller from receiving normal return |

You do not need to rewrite the entire program for each case. With a fake controlled by `failOpen`/`failClose` flags, you can vary each resource's configuration and the body's behavior. However, always create a **fresh event list** and fresh resources for each test to prevent shared `Throwable`s or state from making tests order-dependent.

### 9.1. Why `assertThrows` Alone Is Not Enough

A test like:

~~~java
assertThrows(IOException.class, () -> process());
~~~

This is a **JUnit 5 fragment**, requiring `process()` and JUnit Jupiter. It only proves that an `IOException` escaped; it does not tell you whether the `IOException` came from the body, initialization, or close, does not prove that all resources were attempted to be closed, and does not check suppressed exceptions.

A good test must verify:
- The type and identity/message of the primary exception.
- The count and order of suppressed exceptions.
- The event log of initialization, usage, and cleanup.
- No body event if an initializer failed.
- Which resources **were** and **were not** initialized.
- Postconditions that must still hold after failure.

## 10. Writing JUnit 5 Assertions for Multiple Suppressed Exceptions

The following is a **test fragment** assuming `SuppressedPracticeDemo.TrackedResource` is in the same package and the test has JUnit Jupiter. It uses `assertSame` to assert the exact body error object, not just an identical message.

~~~java
@Test
void bodyExceptionStaysPrimaryAndAllCloseFailuresAreSuppressed() {
    List<String> events = new ArrayList<>();
    IOException original = new IOException("body failed");

    IOException thrown = assertThrows(IOException.class, () -> {
        try (var a = new SuppressedPracticeDemo.TrackedResource(
                     "A", events, false, true);
             var b = new SuppressedPracticeDemo.TrackedResource(
                     "B", events, false, true);
             var c = new SuppressedPracticeDemo.TrackedResource(
                     "C", events, false, true)) {
            events.add("work");
            throw original;
        }
    });

    assertSame(original, thrown);
    assertEquals(3, thrown.getSuppressed().length);
    assertEquals("close C failed",
                 thrown.getSuppressed()[0].getMessage());
    assertEquals("close B failed",
                 thrown.getSuppressed()[1].getMessage());
    assertEquals("close A failed",
                 thrown.getSuppressed()[2].getMessage());
    assertIterableEquals(
            List.of("open:A", "open:B", "open:C", "work",
                    "close:C", "close:B", "close:A"),
            events);
}
~~~

To place this test into a JUnit 5 class, you need:
- `import org.junit.jupiter.api.Test;`
- `import java.util.List;`, `import java.util.ArrayList;`, `import java.io.IOException;`
- Static imports `assertThrows`, `assertSame`, `assertEquals`, `assertIterableEquals` from `org.junit.jupiter.api.Assertions`.
- Class `SuppressedPracticeDemo` and nested `TrackedResource` accessible from the test (e.g., in the same package).

### 10.1. Why `assertSame` Is Valuable

If you only use:

~~~java
assertEquals("body failed", thrown.getMessage());
~~~

you might actually be checking **a new wrapper with the same message**. `assertSame(original, thrown)` proves that `try-with-resources` preserved the exact exception object thrown by the body, and that the close errors were attached directly to that object.

This is appropriate for **a practice exercise on Java exception mechanics**. In ordinary business tests, not every API guarantees that the caller receives the exact same `Throwable` object; a valid wrapper may be used. Assert identity when the contract itself requires it.

## 11. Testing Resource B Initialization Failure

JUnit 5 fragment:

~~~java
@Test
void failedSecondInitializerClosesFirstResource() {
    List<String> events = new ArrayList<>();

    IOException thrown = assertThrows(IOException.class, () -> {
        try (var a = new SuppressedPracticeDemo.TrackedResource(
                     "A", events, false, true);
             var b = new SuppressedPracticeDemo.TrackedResource(
                     "B", events, true, false);
             var c = new SuppressedPracticeDemo.TrackedResource(
                     "C", events, false, true)) {
            events.add("work");
        }
    });

    assertEquals("open B failed", thrown.getMessage());
    assertEquals(1, thrown.getSuppressed().length);
    assertEquals("close A failed",
                 thrown.getSuppressed()[0].getMessage());
    assertIterableEquals(
            List.of("open:A", "open:B", "close:A"), events);
}
~~~

This test is especially useful because it separates two responsibilities:
- Java automatically closes resources **that were successfully initialized earlier**.
- B's initialization code is responsible for handling **any internal resources of B that were partially allocated**, if applicable.

You should not expect `close:B` in the event log. Constructor B threw before a valid instance was assigned to the `try-with-resources` resource variable.

### 11.1. Variant Where C Initialization Fails

Move `failOpen=true` to C, and set `failClose=true` on A and B. Expected:
- Events: `open:A`, `open:B`, `open:C`, `close:B`, `close:A`.
- Primary: `open C failed`.
- Suppressed: `close B failed` then `close A failed`.
- No `work`; no `close:C`.

This is an extension exercise that can be predicted directly from the rules, without guessing at runtime.

## 12. Testing Failures That Only Occur in `close()`

JUnit 5 fragment:

~~~java
@Test
void firstCloseFailureBecomesPrimaryWhenBodySucceeds() {
    List<String> events = new ArrayList<>();

    IOException thrown = assertThrows(IOException.class, () -> {
        try (var a = new SuppressedPracticeDemo.TrackedResource(
                     "A", events, false, true);
             var b = new SuppressedPracticeDemo.TrackedResource(
                     "B", events, false, true);
             var c = new SuppressedPracticeDemo.TrackedResource(
                     "C", events, false, true)) {
            events.add("work:ok");
        }
    });

    assertEquals("close C failed", thrown.getMessage());
    assertEquals(2, thrown.getSuppressed().length);
    assertEquals("close B failed",
                 thrown.getSuppressed()[0].getMessage());
    assertEquals("close A failed",
                 thrown.getSuppressed()[1].getMessage());
    assertIterableEquals(
            List.of("open:A", "open:B", "open:C", "work:ok",
                    "close:C", "close:B", "close:A"),
            events);
}
~~~

**Key point to emphasize:** even though the body completed, the entire `try-with-resources` invocation can still end with an exception caused by `close()`. An exception occurring "after business logic" cannot be assumed safe to swallow; with an output stream, closing is often where an incomplete write is detected.

Conversely, you must not conclude that a close exception definitely undid earlier operations. To verify data integrity, you need tests with a real implementation or an appropriate state model.

## 13. Trying an "Observational" Fake Error Without Breaking Tests

When studying suppressed exceptions, create exceptions with distinct messages:

~~~java
IOException body = new IOException("body failed");
IOException closeA = new IOException("close A failed");
IOException closeB = new IOException("close B failed");
~~~

This is a Java fragment. Do not reuse **the same exception object** for both body and close. When the compiler generates cleanup, it may call `primary.addSuppressed(closeFailure)`. If `closeFailure == primary`, `Throwable.addSuppressed` forbids self-suppression and can throw `IllegalArgumentException`, derailing the test from the intended scenario.

To verify the **identity** of suppressed exceptions, you can inject a dedicated exception per resource:

~~~java
IOException errorB = new IOException("close B failed");
IOException errorA = new IOException("close A failed");
~~~

A fake can support a constructor accepting these objects or an appropriate supplier callback, and when `close()` throws the exact injected object, the test can call `assertSame(errorB, suppressed[0])`. However, there is no need to overcomplicate the main example: checking type, message, order, and the event log already expresses most of the behavior.

### 13.1. Why Not Use a Singleton Throwable Across an Entire Suite?

`Throwable` is a **stateful** object: it stores a stack trace, cause/suppressed exceptions, and related metadata. Reusing a single exception instance across multiple tests can retain suppressed exceptions from previous tests, making results order-dependent. Create a new instance for each case, especially when demonstrating `getSuppressed()`.

## 14. How Java Preserves Exceptions in `try-with-resources`

You can think of Java compiling `try-with-resources` into cleanup logic with the following semantics:

~~~java
Throwable primary = null;
try {
    work();
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
~~~

This is **Java-like pseudocode to explain a single resource**, not an exact bytecode translation of every compiler/JDK, and not code to copy into production. For multiple resources, the compiler generates nested cleanup blocks to close them in reverse order. The main takeaway is:

- If a primary already exists from the body or an initializer, any close failure is attached to the primary.
- If no primary exists yet, a close failure can become the thrown exception.
- Remaining resources are still cleaned up via the nested structure.
- The compiler handles the rules accurately, avoiding many common pitfalls of hand-written `finally` blocks.

**Do not use `catch (Throwable)` in business code just because the pseudocode here does.** That illustrates how the language preserves exception signals, not a recommendation to catch every `Error` and continue running.

### 14.1. Hand-Written `finally` Code Often Masks the Primary Error

A familiar mistake:

~~~java
try {
    throw new IOException("body failed");
} finally {
    throw new IOException("close failed");
}
~~~

This is a **fragment inside a method declaring `throws IOException`**. An exception thrown from `finally` can replace an exception propagating out of the body. If you hand-write cleanup for multiple resources:

~~~java
try {
    work();
} finally {
    b.close();
    a.close();
}
~~~

This is a fragment with undefined variables and methods. If `b.close()` throws, the call to `a.close()` may never happen; furthermore, a body error can be masked. For `AutoCloseable`, prefer `try-with-resources` unless there is a special lifecycle requirement and all branches are thoroughly tested.

## 15. Where Do Suppressed and Cause Appear in Logs?

In the `wrappedFailure` example, there are two objects:

~~~text
IllegalStateException("service failed")         <-- outer wrapper
    suppressed: []                               <-- empty
    cause ->
        IOException("read failed")               <-- original exception
            suppressed:
                IOException("close A failed")
~~~

If a log only prints `wrapper.getMessage()`, you lose both the cause and the suppressed exception. If code inspects `wrapper.getSuppressed()` and concludes "there were no close errors," that conclusion is checking **the wrong object**.

When a logger can print a full `Throwable`, pass the exception object (not just its message) so it can display the stack trace, cause chain, and suppressed exceptions. In layered applications, choose a single layer responsible for logging to avoid logging the same error repeatedly at every `catch`.

### 15.1. `printStackTrace()` Displays Relationships

Fragment:

~~~java
try {
    runOperation();
} catch (IOException e) {
    e.printStackTrace();
}
~~~

This is a fragment with a hypothetical `runOperation`. When an exception has suppressed exceptions, the output typically includes a `Suppressed: ...` section with the secondary error's frames and possibly `... N more` for shared frames. Do not treat `... N more` as lost errors; it is simply a shorthand notation for duplicated stack frames.

In production, consider a logging framework and protect sensitive data rather than printing freely to `stderr`. This practice exercise uses `report` to print a concise format for deterministic `stdout`, but it **does not replace a full stack trace** when investigating a real failure.

## 16. Outcome After a Close Failure: Cleanup Does Not Mean Rollback

A realistic sequence:

~~~text
Open output stream
Write 1000 bytes
Work body finishes
close() -> IOException
~~~

A close failure may reflect a buffer flush failure. However, to know how much of those 1000 bytes actually persisted or survived, you must rely on the specific `OutputStream` contract, the filesystem, and integration tests. A fake that throws an exception on close **cannot prove that real file contents were rolled back**.

The same applies to JDBC:
- `Connection.close()` is not a substitute for transaction rollback across all drivers and pools.
- If a commit already occurred before close, a close error does not automatically undo the commit.
- If the connection is lost during commit, the state may be indeterminate; reconciliation is required.

When a primary exception reports that an operation failed, do not automatically conclude "no external side effects occurred." When multiple suppressed exceptions involve different resources, logs must retain enough context to know which resources need additional cleanup or reconciliation.

### 16.1. Should You Retry `close()` When `close()` Throws?

There is no single right answer for every `AutoCloseable`. A `close()` call may have already released the resource before throwing due to a flush error; retrying `close()` may be pointless or even cause new side effects. Some implementations guarantee `close()` is idempotent, while others do not.

A test fake can model `closeCount` and a closed state flag if the product contract requires it. Do not impose "close error = definitely still open" or "calling a second time is always safe" solely from the `AutoCloseable` interface.

## 17. Adding a Close Counter and State Flag If Needed

Example extension to the fake class:

~~~java
private int closeCount;
private boolean closed;

@Override
public void close() throws IOException {
    closeCount++;
    closed = true;
    events.add("close:" + name);
    if (failClose) {
        throw new IOException("close " + name + " failed");
    }
}
~~~

This is a **fragment to add to the fake**, not a complete class. If you set `closed = true` **before throwing**, the fake models a resource that transitions to closed even when close reports an error. If you set it after the step that can throw, the fake models not transitioning state when close fails. Both are **modeling assumptions**; choose the one that matches the real resource's contract in your test.

In a single-threaded test, an `int` close counter is sufficient. For concurrent code, use synchronization or `AtomicInteger` and read it after the worker has truly finished. `Future.isCancelled()` alone does not prove `close()` has finished running.

## 18. Testing Partial Initialization Failures Inside a Resource

Suppose you need to open an input stream and then read a header before returning an object:

~~~java
static ParsedFile openParsedFile(Path path) throws IOException {
    InputStream in = Files.newInputStream(path);
    try {
        Header header = readHeader(in);
        return new ParsedFile(in, header);
    } catch (IOException | RuntimeException failure) {
        try {
            in.close();
        } catch (IOException cleanupError) {
            failure.addSuppressed(cleanupError);
        }
        throw failure;
    }
}
~~~

This is a **design fragment**, requiring definitions for `ParsedFile`, `Header`, `readHeader`, and imports for `Files`/`Path`/`InputStream`/`IOException`. The idea:
1. The factory owns the stream once `Files.newInputStream` succeeds.
2. If parsing or construction fails before ownership is transferred, the factory closes the stream.
3. If closing the stream also fails, keep the parsing/construction exception as primary and add the close error as suppressed.
4. If the object is returned successfully, `ParsedFile` takes responsibility for closing the stream in its `close()`.

The exact point of ownership transfer must be clearly defined. If the `ParsedFile` constructor throws **after receiving the stream**, the factory code must still handle cleanup since no result was returned. Partial initialization is why testing resource initializers differs from testing body failures.

### 18.1. Mini Exercise on Partial Initialization

Create a `FakeInputStream` that records events:
- `open:stream`;
- `readHeader` throws `IOException("invalid header")`;
- `close:stream` throws `IOException("stream close failed")`.

Expected: the `invalid header` error is primary, and `stream close failed` is suppressed. Also ensure no `ParsedFile` object is returned. This is a **factory cleanup** test, not proof that TWR will close an uninitialized object.

## 19. Do Not Collapse All Exceptions Into a "Success" Result

If code does:

~~~java
try (Resource a = openA();
     Resource b = openB()) {
    process(a, b);
} catch (IOException ignored) {
}
return true;
~~~

This is a fragment assuming the types and functions already exist. It can discard both body errors and close/suppressed errors, then return `true`. The caller loses the ability to distinguish success from partial failure.

If the current layer is authorized to handle the error, it can:
- Preserve and propagate the exception along with its cause and suppressed exceptions.
- Convert it into a structured result `Failure(code, cause)` if the API uses result types.
- Perform controlled cleanup, rollback, or compensation and record the actual state.
- Return `UNKNOWN`/`PENDING` when external side effects cannot yet be verified.

Do not convert an `IOException` into `Optional.empty()` if empty means "no data"; nor should you treat a close failure as unimportant just because the body finished running.

## 20. Testing Multiple Resources Without Losing Secondary Errors

A flow with three resources can track:
- Resource ID: `A`/`B`/`C`.
- Error type: open/body/close.
- Location of the primary error.
- List of suppressed exceptions with order and resource.
- When each resource completed initialization.
- Side-effect state, if any.
- Correlation ID / job ID in multi-request system tests.

For single-threaded tests with a single event list, resource IDs and messages are enough. In production systems, a message like `"close A failed"` may be insufficient because you do not know which request A belonged to. Do not log tokens or private data just to identify a resource; use safe technical IDs.

Some `Throwable`s in production have truncated stack traces due to runtime configuration, but `getSuppressed()` is the direct API for reading attached errors. If an exception is wrapped across multiple layers, locate the exact primary object where the suppressed exceptions are attached.

## 21. Advanced Exercise: Multiple Suppressed Exceptions Not Caused by `close()`

`Throwable.addSuppressed` is a general API; although `try-with-resources` is its most familiar source, applications can also deliberately attach secondary errors to a primary exception.

Example aggregating two separate cleanup steps:

~~~java
IOException primary = new IOException("operation failed");
try {
    cleanupCache();
} catch (IOException e) {
    primary.addSuppressed(e);
}
try {
    cleanupTempFile();
} catch (IOException e) {
    primary.addSuppressed(e);
}
throw primary;
~~~

This is a **fragment** inside a method declaring `throws IOException`, with two hypothetical cleanup methods. This pattern is only appropriate when you have verified that:
- `primary` is the most important error to propagate.
- The two cleanup steps are independent or allowed to proceed when one fails.
- Each exception is a valid object, not identical to `primary`.
- Resource lifecycles could not be expressed more simply with `try-with-resources`.
- Callers/logging receive and preserve the error rather than swallowing it in an empty outer `catch`.

Avoid adding the primary object to itself: `primary.addSuppressed(primary)` is invalid. Avoid passing `null`. Do not assume every `Throwable` has suppression enabled if a custom constructor disables it.

## 22. Async Testing When Exceptions Are Wrapped by `Future`

If a flow using fakes runs inside a `Callable` via `ExecutorService.submit`, exceptions from the task can be delivered to the caller wrapped in an `ExecutionException`. In that case:
- `ExecutionException` is the wrapper for observing a failure through `Future`.
- `wrapper.getCause()` is the error thrown by the task.
- Suppressed close errors reside on the **cause**, not automatically on `ExecutionException`.

JUnit 5 fragment:

~~~java
Future<?> future = executor.submit(() -> {
    try (Resource resource = openResource()) {
        doWork(resource);
    }
    return null;
});

ExecutionException wrapper = assertThrows(
        ExecutionException.class, future::get);

Throwable primary = wrapper.getCause();
Throwable[] cleanupFailures = primary.getSuppressed();
~~~

This is a **fragment** requiring Java concurrency imports, JUnit Jupiter, and defined `Resource`, `openResource`, and `doWork` types/methods. In real tests, remember to shut down the executor during proper cleanup. Do not treat `Future.isDone() == true` as task success; it can finish due to failure or cancellation.

If using `CompletableFuture.join()`, the wrapper is typically `CompletionException` instead of `ExecutionException`. To find suppressed exceptions, continue inspecting the underlying cause. A `whenComplete` callback that throws a new exception has its own precedence rules; it does not mean observer errors automatically become suppressed on the source.

### 22.1. Race with Cancellation

`Future.cancel(true)` can request an interrupt, but it does not guarantee the worker has actually exited `try` and called `close()`. To verify that cleanup completed, use a latch in `finally` or a dedicated completion channel. Reading the event log immediately after `cancel()` returns `true` can be too early, causing flaky tests. This is not a limitation of suppressed exceptions, but an **asynchronous lifecycle** issue.

## 23. Common Mistakes When Reproducing Suppressed Exceptions

### 23.1. Creating Only One Close Error While Expecting Multiple Suppressed Exceptions

If the body does not throw and `B.close()` is the first close to fail, it becomes primary, **not suppressed**. To get multiple suppressed exceptions, you need an earlier body/initializer primary error or at least one primary close failure followed by additional close failures.

### 23.2. Expecting Closing Order A, Then B, Then C

`try-with-resources` with resources declared A/B/C closes **C, then B, then A**. If your event log shows a different order, check the order in which resources were declared and whether there is any manual closing code.

### 23.3. Expecting `B.close` to Run When Constructor B Throws

If an initializer fails to return an object successfully, TWR does not manage closing B itself. It only closes resources that were successfully created before it.

### 23.4. Inspecting Only the Outermost Exception After Wrapping

If a wrapper preserves a cause, inspect `wrapper.getCause().getSuppressed()`. `wrapper.getSuppressed().length == 0` does not prove cleanup succeeded.

### 23.5. Catching an Exception and Throwing a Wrapper Without a Cause

~~~java
catch (IOException e) {
    throw new IllegalStateException("service failed");
}
~~~

This is a fragment. It loses the normal cause link to the primary and suppressed exceptions, making diagnosis difficult. Use `new IllegalStateException("service failed", e)` when wrapping.

### 23.6. Catching and Printing Only `getMessage()`

`getMessage()` is only the message of a single `Throwable`. It does not list suppressed exceptions, causes, or stack traces. Use a logger with full `Throwable` support or read the API directly.

### 23.7. Assuming Every Failed Resource Close Left the Resource Unreleased

`close()` can throw before or after releasing part of a resource. Actual resource state depends on the contract; your fake must represent the specific situation under test.

### 23.8. Reusing the Same Exception Instance at Two Throw Sites

Doing so can trigger self-suppression or cause suppressed exceptions from a previous test to persist into the next test. Create separate exceptions for the body and each close.

### 23.9. Tests Relying on Stack Trace Line Numbers

Line numbers change whenever source code is formatted or refactored. Practice tests should assert semantics: primary identity/type, suppressed exceptions, and event order, rather than hardcoding `Foo.java:47`.

### 23.10. Tests Not Cleaning Up Executors or Real Resources

When testing beyond synchronous examples, always manage the lifecycle of executors, temporary directories, and real resources. Do not try to induce file-close failures by altering permissions or disk space uncontrollably on a shared system.

## 24. Practice Completion Checklist

- [ ] Create a fake implementing `AutoCloseable` with an ID and `open/close` history.
- [ ] Arrange three resources A/B/C in a single `try-with-resources`.
- [ ] Make the body throw an `IOException` with a distinct message.
- [ ] Make C/B/A close all throw **distinct `IOException` objects**.
- [ ] Verify that the body failure is primary.
- [ ] Verify `getSuppressed().length == 3`.
- [ ] Verify suppressed exceptions are in the order C, B, A.
- [ ] Verify `close:C`, `close:B`, and `close:A` all appear.
- [ ] Use `assertSame` to check the primary object when the test requires identity.
- [ ] Simulate B initializer failure; verify A still closes and C/body do not run.
- [ ] Simulate body success with all three closes failing; verify close C is primary.
- [ ] Create a wrapper with a cause and check suppressed exceptions on the cause.
- [ ] Avoid writing manual cleanup that drops the primary exception or skips resources.
- [ ] Do not reuse singleton exceptions across test cases.
- [ ] Include at least one happy-path test to ensure normal body and close behavior.
- [ ] Distinguish close failures from transaction rollback or data durability guarantees.
- [ ] Conclude a test passes only when stdout/assertions reflect the defined contract.

## 25. Extension Exercises with Guided Answers

### Exercise A — Change Resource B to Close Successfully

In `bodyAndThreeClosesFail`, change B to `failClose=false`, keeping the body failure and A/C close failures. Before running, predict:
- The event log still includes `close:B`.
- The primary exception is still `body failed`.
- Suppressed only contains `close C failed` and `close A failed`.
- Suppressed length is 2, in the order C then A.

### Exercise B — Test C Constructor Failure After A and B

A and B initialize successfully, C has `failOpen=true`, and A/B have `failClose=true`. Predict:
- Primary: `open C failed`.
- Suppressed: `close B failed`, `close A failed`.
- Events: `open:A` → `open:B` → `open:C` → `close:B` → `close:A`.
- No `close:C` and no body event.

### Exercise C — No Body Exception, Only B and A Close Fail

Let `C.close` succeed, while `B.close` and `A.close` throw. Predict:
- Primary: `close B failed`.
- Suppressed: `close A failed`.
- Full close events: C, then B, then A.

### Exercise D — Outer Wrapper with Multiple Levels of Cause

Wrap the original `IOException` in an `IllegalStateException`, then wrap that in another `RuntimeException` with a cause. Call `getCause()` twice to reach the original exception, then read `getSuppressed()`. Do not expect the outer wrapper to contain the original's suppressed exceptions. Write a short note distinguishing the cause relationship from the suppressed relationship.

### Exercise E — Simulating Side Effects Before Close Fails

Give the fake a data buffer. In the body, write a record, then make close throw. Determine whether the record was already written into the fake's state before close. If the requirement is "no data visible on failure," add explicitly tested staging/commit logic. **Do not assume an exception automatically rolls back state.**

## 26. Summary

To accurately reproduce **a primary exception with multiple suppressed exceptions** in Java, create a fake `AutoCloseable` that can throw on close, place multiple resources in `try-with-resources`, and deliberately throw an exception from the body or an initializer.

Five key takeaways:

1. **Body/initializer already threw:** that error is primary; subsequent close failures are stored in `getSuppressed()`.
2. **Body succeeded:** the first close failure in reverse closing order is primary; subsequent close failures are suppressed.
3. **Resources close in reverse order:** with A/B/C declared, Java closes C/B/A; one close failure does not stop compiler-generated cleanup from attempting to close the remaining resources.
4. **Initializer failed:** previously opened resources are cleaned up; an uninitialized object does not have `close` called automatically by TWR.
5. **Wrappers with a cause do not copy suppressed exceptions:** to investigate all errors, inspect both `getCause()` and `getSuppressed()` on the right object.

A good test does not stop at "an `IOException` occurred": it verifies **primary identity, suppressed count and order, the event log, and post-failure state**. That is how you turn Java's exception handling mechanics into verifiable guarantees while avoiding overpromising rollback or external resource success.
