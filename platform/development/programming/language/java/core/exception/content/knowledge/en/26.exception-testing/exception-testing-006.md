# Creating a Fake Resource to Simulate Initialization or Close Failures in Java

## 1. Why Test Failures at Resource Open and Close Time?

In Java, resources such as file streams, sockets, database connections, transaction handles, or external system clients typically have a **lifecycle**: initialization/allocation → usage → closing/release. Failures do not happen only when processing data. **Opening a resource** can fail; **closing a resource** can also throw an exception, even when the main body of work has already completed successfully.

If you only test the "opens, works, closes" happy path, the program can hide serious bugs:

- Resource A is already open, but initializing resource B fails. Is A closed?
- The `try` body throws an exception, and then `close()` also throws. Which exception reaches the caller? Is the secondary failure lost?
- The `try` body completes normally, but `close()` throws. Is the failure reported to the caller?
- There are two resources, and each `close()` throws. Does Java continue closing the remaining resource?
- A constructor fails **after having already allocated some internal resources**. Who is responsible for cleaning up those partially allocated resources?
- Is a resource closed twice, forgotten, or used after being closed?
- Can a test using a real file, network, or database reproduce a failure at the **exact desired point**, or is it prone to flakiness caused by the environment?

A **fake resource** is a test implementation whose behavior is controlled by data and failure flags. It can record events such as `init:A`, `close:B`, count close calls, and proactively throw `IOException` at designated points. As a result, tests focus on the **lifecycle contract**, without depending on a failing real disk or a disconnected real network.

The goal of this lesson is to create and use a fake resource with Java 17 to prove release order, the primary exception (*primary exception*), attached suppressed exceptions (*suppressed exceptions*), and postconditions when initialization or closing fails.

## 2. Java Mechanisms to Understand Before Writing a Fake

### 2.1. `AutoCloseable` Is the Resource-Closing Contract

The basic interface:

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

This is an **illustrative signature** of `AutoCloseable`, not a new implementation file to create. An implementing class may narrow the checked exception, for example declaring `close() throws IOException`. `Closeable` in `java.io` is a subinterface with a specific contract and usage for I/O.

Try-with-resources syntax:

~~~java
try (Resource resource = acquire()) {
    use(resource);
}
~~~

This is an **illustrative fragment** (requiring `Resource`, `acquire`, and `use`). Java automatically calls `close()` when leaving the block, whether the body completes normally or exits via an exception, `return`, or another supported control-flow transfer. Closing follows the exception rules of try-with-resources; `close()` itself may throw a new exception.

**Important:** try-with-resources helps invoke cleanup for resources that were successfully initialized; it **does not automatically roll back side effects** such as a file write, database commit, or HTTP request sent before the failure.

### 2.2. Closing in Reverse Order of Declaration

~~~java
try (Resource first = openFirst();
     Resource second = openSecond()) {
    doWork();
}
~~~

The fragment above declares two resources. If both initialize successfully, the closing order is **`second.close()` then `first.close()`**. This is a deterministic Java rule, independent of the scheduler or machine speed.

If `openSecond()` throws an exception during initialization, the `first` resource that was already successfully acquired must still be closed. However, `second` **is not registered as a successfully initialized resource** and will not have `close()` called on it by try-with-resources. If creating `second` had already opened an internal socket before throwing, its initialization code is responsible for cleaning up the partially opened resource.

### 2.3. Failures in the Body and Failures in `close()`

Core rules:
- **`try` body throws A, `close()` throws B:** A remains the primary exception, and B is attached to A via `getSuppressed()`.
- **Body completes normally, `close()` throws B:** B becomes the primary exception propagating out of try-with-resources.
- **Multiple resources fail to close:** Java still attempts to close the remaining resources. Reverse closing order determines which exception is treated as primary if the body had no error.
- **Subsequent resource initialization throws A, already-opened resource close throws B:** A is the primary exception, and B is attached as suppressed.

These rules are well suited to testing with a fake, because a test can trigger a failure at the exact right spot without forcing a real filesystem or network failure.

## 3. How Does a Fake Resource Differ from a Mock and a Stub?

There are three common ways to simulate dependencies:

| Type | Characteristics | When Appropriate |
| --- | --- | --- |
| **Fake** | Has a simple implementation with real in-memory state; records events, mutates state, and proactively throws configured errors | Testing resource lifecycle, closing order, and post-failure state |
| **Stub** | Returns pre-programmed values or exceptions; usually has minimal logic/state | Controlling a dependency's result to test a specific branch |
| **Mock** | Object created by a tool/function to verify interactions, call counts, arguments, and order | Testing collaborator call contracts via Mockito or a similar mechanism |

These terms can overlap depending on the community and framework. This lesson chooses a **plain-Java fake**, because a stateful implementation (event log, fail flags, close count) reproduces the behavior without depending on a mocking library.

A good fake should have:
- **Explicit failure control:** the ability to choose failures on init, on use, and on close.
- **Event recording:** ensuring tests can distinguish `init`, `use`, and `close` in exact order.
- **Deterministic behavior:** no randomness, no `Thread.sleep` to "guess" failure timing.
- **Identity:** knowing which resource is A, B, or C.
- **Repeatability:** each test creates a fresh fake/event log, without leaking state from a previous test to the next.
- **Appropriate realism:** modeling the `AutoCloseable` contract accurately without assuming cleanup behavior that a real resource does not guarantee.

Do not over-model an entire database or socket if the goal is simply to verify that Java calls `close()` and preserves exceptions. An overly complex fake can introduce its own bugs into tests.

## 4. Complete Java 17 Example: Three Init/Body/Close Scenarios

The following program is complete enough to compile and run, **without needing JUnit or any third-party library**. `FakeResource` records events into a `List<String>` and has two independent flags:

- `failInit`: throws `IOException` in the constructor after recording the `init` marker.
- `failClose`: records the `close` marker and then throws `IOException` when called to close.

The `report` method records the primary failure and each exception in `getSuppressed()`. Three scenarios cover the core branches.

Save as **`FakeResourceFailureDemo.java`**:

~~~java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public class FakeResourceFailureDemo {
    static final class FakeResource implements AutoCloseable {
        private final String name;
        private final List<String> events;
        private final boolean failClose;

        FakeResource(String name, List<String> events,
                     boolean failInit, boolean failClose) throws IOException {
            this.name = name;
            this.events = events;
            this.failClose = failClose;
            events.add("init:" + name);
            if (failInit) {
                throw new IOException("init " + name + " failed");
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

    static void report(String label, List<String> events, IOException failure) {
        events.add("primary:" + failure.getMessage());
        for (Throwable suppressed : failure.getSuppressed()) {
            events.add("suppressed:" + suppressed.getMessage());
        }
        System.out.println(label + " -> " + String.join(" | ", events));
    }

    static void bodyAndCloseFail() {
        List<String> events = new ArrayList<>();
        try (FakeResource a = new FakeResource("A", events, false, true);
             FakeResource b = new FakeResource("B", events, false, true)) {
            events.add("body");
            throw new IOException("body failed");
        } catch (IOException failure) {
            report("body-fail", events, failure);
        }
    }

    static void secondInitFails() {
        List<String> events = new ArrayList<>();
        try (FakeResource a = new FakeResource("A", events, false, true);
             FakeResource b = new FakeResource("B", events, true, false)) {
            events.add("unreachable");
        } catch (IOException failure) {
            report("init-fail", events, failure);
        }
    }

    static void closeOnlyFails() {
        List<String> events = new ArrayList<>();
        try (FakeResource a = new FakeResource("A", events, false, true);
             FakeResource b = new FakeResource("B", events, false, true)) {
            events.add("body:ok");
        } catch (IOException failure) {
            report("close-fail", events, failure);
        }
    }

    public static void main(String[] args) {
        bodyAndCloseFail();
        secondInitFails();
        closeOnlyFails();
    }
}
~~~

Compile and run with JDK 17+ from the directory containing the file:

~~~bash
javac --release 17 FakeResourceFailureDemo.java
java FakeResourceFailureDemo
~~~

**Stdout verified with JDK 17:**

~~~text
body-fail -> init:A | init:B | body | close:B | close:A | primary:body failed | suppressed:close B failed | suppressed:close A failed
init-fail -> init:A | init:B | close:A | primary:init B failed | suppressed:close A failed
close-fail -> init:A | init:B | body:ok | close:B | close:A | primary:close B failed | suppressed:close A failed
~~~

### 4.1. Scenario 1 — Body and Both Closes Fail

In `bodyAndCloseFail()`:
1. `FakeResource A` initializes successfully.
2. `FakeResource B` initializes successfully.
3. The `try` body adds the `body` event and then throws `IOException("body failed")`.
4. Java calls `B.close()` first; it records `close:B` and throws `IOException("close B failed")`.
5. Java continues by calling `A.close()`; A records `close:A` and also throws.
6. The `catch` block receives `body failed` as the **primary** exception, while the two close failures are in `failure.getSuppressed()` in the order B then A.

Notable check: **both B and A are attempted to be closed, even though `B.close()` already threw an exception.** With an improperly hand-written `finally`, you could accidentally skip closing A when `B.close` fails.

### 4.2. Scenario 2 — Constructor B Fails While A Is Already Open

In `secondInitFails()`:
1. Constructor A records `init:A` and initializes successfully.
2. Constructor B records `init:B` and then throws `IOException("init B failed")`.
3. The `try` body **does not run**, so `unreachable` does not appear.
4. A is a successfully created resource, so Java calls `A.close()`.
5. B does not have `close()` called on it because its constructor did not return a complete resource.
6. `A.close()` also throws, but `init B failed` remains the primary exception; `close A failed` is suppressed.

This is an often-overlooked test. It proves that try-with-resources **does not only close after the body begins**, but also cleans up resources that were successfully initialized before a failing resource initializer.

### 4.3. Scenario 3 — Body Succeeds, Close Fails

In `closeOnlyFails()`, the body only adds `body:ok`. Upon exiting the block:
1. `B.close()` throws and becomes the **primary** exception.
2. `A.close()` is still called, and its failure becomes **suppressed** alongside B's failure.
3. The caller cannot treat the overall operation as "succeeded without error", even though the body ran to completion.

**Domain note:** whether a close failure affects already-processed data depends on the resource type. For some output streams, a `close`/flush failure can mean data was not fully written. For other resources, a close failure might only affect cleanup. You must know the real resource's contract; do not assume data is always lost or always saved.

## 5. Try-with-Resources Behavior Matrix

| Resource initializer | Body | Close | Exception reaching caller |
| --- | --- | --- | --- |
| All succeed | Succeeds | All succeed | No exception |
| A opens successfully, B init fails | Does not run | A closes successfully | B init failure |
| A opens successfully, B init fails | Does not run | A.close fails | B init primary; A close suppressed |
| All open successfully | Throws X | All closes succeed | X |
| All open successfully | Throws X | B.close throws Y | X primary; Y suppressed |
| All open successfully | Succeeds | B.close throws Y | Y primary |
| All open successfully | Succeeds | B.close throws Y, A.close throws Z | Y primary; Z suppressed |
| All open successfully | Throws X | B.close throws Y, A.close throws Z | X primary; Y and Z suppressed |
| A init fails immediately | Does not run | No header resource completed initialization | A init failure; internal cleanup of A is the implementation's responsibility |

In this table, "init failure" is an exception thrown during resource initialization; **close failure** is an exception from `close()`. If the exception type is a `RuntimeException` rather than an `IOException`, the primary/suppressed rules still apply under normal try-with-resources conditions.

A `catch (IOException e)` only catches matching `IOException`s. If a fake throws a non-`IOException` unchecked exception from `close()` or the body, the program needs a catch/throws matching that type; do not catch `Throwable` broadly just to make every test "pass".

## 6. Designing a Fake That Can Inject Failures at Specific Points

In the runnable example, the constructor takes:

~~~java
FakeResource(String name,
             List<String> events,
             boolean failInit,
             boolean failClose) throws IOException
~~~

This is a **signature fragment** of the constructor already in the program. Using two booleans is enough for a small lesson. For tests with many failure modes, you can use an enum instead of multiple booleans to avoid misreading:

~~~java
enum FailurePoint {
    NONE,
    INIT,
    READ,
    WRITE,
    FLUSH,
    CLOSE
}
~~~

This is a **Java 17 fragment**, which can be placed in a class or its own properly named file. Each enum value describes **one failure location** selected for an instance. If you need to simulate "body fails and close also fails", you must allow multiple failure points or separate configuration for lifecycle and operations; do not use a single enum and accidentally exclude dual-failure scenarios.

A clear fake configuration can include:
- `resourceId`: resource name for tracing.
- `failAtInit` or an injected exception on initialization.
- `failAtClose` or an injected exception on close.
- `events`: list receiving events in order.
- `closeCount`: close call count for assertions.
- `opened`/`closed`: lifecycle state.
- `payload`/`buffer`: internal data if tests need to verify reads/writes.

For concurrent tests, a shared `ArrayList` is not thread-safe by itself. All experiments in `FakeResourceFailureDemo` run synchronously on a single thread, so `ArrayList` is sufficient. If you want to test multiple threads, use thread-safe structures/synchronization mechanisms and coordinate with latches, not `Thread.sleep` as proof of ordering.

### 6.1. Inject an Exception Object or Just a Boolean Flag?

Both approaches are useful:

**Using a flag:**

~~~java
if (failClose) {
    throw new IOException("close failed");
}
~~~

Simple, deterministic, and suitable for teaching suppressed-exception rules.

**Using a test-supplied exception:**

~~~java
if (closeFailure != null) {
    throw closeFailure;
}
~~~

This is a fragment where `closeFailure` is an `IOException` provided by the test. The advantage is that you can assert **identity**: whether the primary or suppressed exception is the exact object injected. Be careful not to reuse the same exception object across multiple test runs, because the stack trace and suppressed list attached to the object can skew the evidence.

In real tests, create a fresh exception for each test rather than using a suite-wide singleton `Throwable`.

## 7. Checking the Event Log Instead of Only Checking the Exception Class

A weak test:

~~~java
assertThrows(IOException.class, () -> useResource());
~~~

This is a **JUnit 5 fragment**, where `useResource` is a hypothetical method. It only proves that an `IOException` escaped; it does not prove that the resource was closed, whether any exception was suppressed, or whether the body actually ran.

A good test also checks **postconditions**:
- `init:A` happens before `init:B`.
- `close:B` happens before `close:A` when both were initialized.
- `body` does not run if the second initializer fails.
- `close()` on a resource whose initialization failed is not called by try-with-resources.
- Each successfully initialized resource is closed **exactly once** by the try-with-resources construct in the tested flow.
- The primary exception still has the expected object/type/message.
- `getSuppressed()` contains the close failures in the right count and order.
- No test-owned resources are leaked.

Do not just write `verify(close())` once and ignore order: resource B's close might throw and prevent hand-written cleanup from reaching A. With an event log, ordering bugs show up immediately in the output.

### 7.1. Adding a Close Counter When Exact Assertions Are Needed

A fake can define:

~~~java
private int closeCount;

@Override
public void close() throws IOException {
    closeCount++;
    events.add("close:" + name);
    if (failClose) {
        throw new IOException("close " + name + " failed");
    }
}

int closeCount() {
    return closeCount;
}
~~~

This is a **fragment to add to the fake class**, not a standalone class. When tests run on a single thread, an `int` counter is enough. Concurrent tests need proper synchronization (for example `AtomicInteger`) and a strategy to read state after all tasks have genuinely finished.

**Closing once by try-with-resources** does not prove that every real library's `close()` is idempotent. If business code also calls `close()` manually, the resource may be called to close a second time; depending on the implementation, that may or may not fail. Tests must match the resource's contract.

## 8. JUnit 5 Example: Asserting Initialization Failure and Cleanup of A

Below is an **illustrative JUnit 5 test snippet**. It assumes you have placed `FakeResourceFailureDemo` in the same package as the test and have JUnit Jupiter on the classpath. Appropriate imports/static imports include `org.junit.jupiter.api.Test`, `java.util.ArrayList`, `java.util.List`, `java.io.IOException`, and `org.junit.jupiter.api.Assertions.*`.

~~~java
@Test
void secondInitializerFailureClosesFirstResource() {
    List<String> events = new ArrayList<>();

    IOException error = assertThrows(IOException.class, () -> {
        try (var a = new FakeResourceFailureDemo.FakeResource(
                     "A", events, false, true);
             var b = new FakeResourceFailureDemo.FakeResource(
                     "B", events, true, false)) {
            events.add("body");
        }
    });

    assertEquals("init B failed", error.getMessage());
    assertEquals(1, error.getSuppressed().length);
    assertEquals("close A failed",
                 error.getSuppressed()[0].getMessage());
    assertIterableEquals(List.of("init:A", "init:B", "close:A"), events);
}
~~~

What is verified:
- B's init failure is the **primary exception**, even though closing A also throws.
- B has no `close:B` in the event log.
- A was cleaned up exactly once according to the `close:A` event.
- The body did not execute because `body` does not appear.

You do not necessarily need to add Mockito to test this order. With an event-recording fake, you can verify both the cause and the lifecycle using plain Java and JUnit.

## 9. JUnit 5 Example: Body Failure Plus Multiple Close Failures

Another test:

~~~java
@Test
void bodyFailureIsPrimaryAndCloseFailuresAreSuppressed() {
    List<String> events = new ArrayList<>();

    IOException error = assertThrows(IOException.class, () -> {
        try (var a = new FakeResourceFailureDemo.FakeResource(
                     "A", events, false, true);
             var b = new FakeResourceFailureDemo.FakeResource(
                     "B", events, false, true)) {
            events.add("body");
            throw new IOException("body failed");
        }
    });

    assertEquals("body failed", error.getMessage());
    assertEquals(2, error.getSuppressed().length);
    assertEquals("close B failed",
                 error.getSuppressed()[0].getMessage());
    assertEquals("close A failed",
                 error.getSuppressed()[1].getMessage());
    assertIterableEquals(
            List.of("init:A", "init:B", "body", "close:B", "close:A"),
            events);
}
~~~

This is a **JUnit 5 test fragment**, with the same imports as the previous section. The test not only sees an `IOException`, it also proves that **no close failure hides the body's `IOException`** and that **A still closes after `B.close()` fails**.

If `getSuppressed().length == 0` even though you configured close to throw, the real code might be using hand-written cleanup, the resource might not be registered in try-with-resources, or the exception might have been wrapped improperly and you are inspecting the wrong outer `Throwable` object.

## 10. Open-Time Failures: Constructors Are Not Automatically Closed by Try-with-Resources

This is an important boundary:

~~~java
try (ConnectionLike c = new ConnectionLike()) {
    work(c);
}
~~~

This fragment assumes `ConnectionLike` is `AutoCloseable` and `work` exists. If the constructor `new ConnectionLike()` **throws an exception before returning an object**, the resource initializer expression has not completed; try-with-resources **cannot call `close()` on an object that was never assigned as an initialized resource**.

This differs from the "A opened, B failed to initialize" case: Java still closes **A**, but does not automatically clean up inside **B**. If B had already opened a socket or file handle before throwing due to a failed setup step, B's constructor/factory must handle **partial acquisition**.

### 10.1. Designing a Factory That Cleans Up Partially Opened Resources

Suppose you need to open an input stream and then read a header to initialize an object:

~~~java
static ParsedInput openParsed(Path path) throws IOException {
    InputStream in = Files.newInputStream(path);
    try {
        Header header = readHeader(in); // May throw IOException.
        return new ParsedInput(in, header); // Takes ownership of the stream.
    } catch (IOException | RuntimeException failure) {
        try {
            in.close();
        } catch (IOException closeFailure) {
            failure.addSuppressed(closeFailure);
        }
        throw failure;
    }
}
~~~

This is a **design fragment**, requiring imports for `java.io.InputStream`, `java.io.IOException`, `java.nio.file.Files`, `java.nio.file.Path`, and definitions for `Header`, `ParsedInput`, and `readHeader`. The idea:

1. `Files.newInputStream` opens the stream.
2. If header parsing or object construction throws, the factory still **owns** the stream and must attempt to close it.
3. If closing also fails, keep the original failure as primary and attach the close failure via `addSuppressed`.
4. If initialization succeeds, the factory **transfers ownership** of the stream to `ParsedInput`; this class must close the stream when its `close()` is called.

In real code, you must clearly define **when ownership transfers** and whether the `ParsedInput` constructor can throw after receiving the stream. If the constructor has side effects before throwing, the catch branch must cover them without mistakenly closing a stream whose ownership has already been transferred. If the failure is another unchecked type or a serious error, an appropriate policy is also needed; the fragment above only illustrates expected exceptions.

### 10.2. Do Not Put Unopened Resources on the Must-Close List

A fake can record `init:B` and then throw, but it **should not automatically add B to the "successfully opened" list**. In tests, distinguish:
- `initAttempted`: initialization started;
- `initialized`: initialization completed;
- `registeredForClose`: the resource became managed by try-with-resources;
- `closed`: `close` was called and what its outcome was.

For a constructor that throws an exception, the fake can log `initAttempted` without logging `closed` for that instance itself. If you need to verify partially opened internal resources, you must have separate events for them; the absence of `close:B` in a TWR trace **does not prove that B's internal handles are all safe**.

## 11. What Does a Fake Close Failure Mean for Real Resources?

`close()` does not have a universal postcondition of "data has been flushed and all effects are complete." Each resource's contract differs:

| Resource | What a close failure may involve | What to verify separately |
| --- | --- | --- |
| File-writing `OutputStream` | Final flush/write failure, filesystem error | How much of the file was written, whether data is durable |
| `BufferedWriter` | Buffer flush or delegate close encountered an error | Whether data was pushed down to the underlying stream |
| JDBC `Connection` | Connection release error; transaction state may vary | Auto-commit, transaction state, whether commit/rollback occurred |
| JDBC `Statement` / `ResultSet` | Driver cleanup failure | Resource lifecycle, driver behavior |
| Socket/channel | Close error, remote state uncertain | Whether packets were sent/received, whether the server processed them |
| Lock/lease handle | Release failure or lease not yet expired | Whether any process still holds access |
| Custom fake resource | Whatever rules you configure | Whether the fake accurately models the real object's contract |

**Do not turn every close failure into "rolled back" or "written successfully."** Fakes help verify Java control flow and application policy; they do not prove every condition of a real filesystem, driver, or remote service.

### 11.1. Cleanup Is Not Rollback

A resource can be closed after an operation has already caused side effects:
- Data was appended to a file, and then closing failed.
- A database transaction was committed, and then closing the connection failed.
- A payment request was sent, the response was lost, and then closing the socket failed.

An `IOException` from `close()` does not automatically restore prior state. If an operation requires all-or-nothing semantics, use transactions, staging, or atomic publish where supported; across multiple distinct systems, you need idempotency, compensation, or reconciliation. Fake tests should include a scenario where **side effects occur before the failure** if the contract must assert post-failure state.

## 12. Avoiding Losing the Primary Exception with Hand-Written `finally`

Anti-pattern:

~~~java
Resource a = openA();
Resource b = openB();
try {
    work(a, b);
} finally {
    b.close();
    a.close();
}
~~~

This is a **fragment** with hypothetical functions/types. If `b.close()` throws:
- `a.close()` **is not called** unless there is separate protection.
- The exception from `b.close()` can mask the exception from `work`.
- If `openB()` throws before entering `try`, the `finally` block **does not run either**, leaking A.

Try-with-resources handles those exit paths with proper Java semantics. For most `AutoCloseable` resources, **prefer try-with-resources** over hand-writing nested `finally` blocks that are hard to verify.

### 12.1. Close Failures Masking Body Failures

With hand-written cleanup:

~~~java
try {
    throw new IOException("body failed");
} finally {
    throw new IOException("close failed");
}
~~~

This is a **fragment** inside a method that allows `throws IOException`. The exception from `finally` replaces the outgoing throw; if you do not preserve the body exception, you lose the original root cause. Try-with-resources has suppressed-exception rules to avoid this problem when both the body and close throw.

Do not put `return` inside `finally` to "return a default state", because that can also mask an exception propagating outward. If you must perform manual cleanup due to a special API, design preservation of the primary exception and test the failure paths.

## 13. `Throwable.getSuppressed()`: Reading Secondary Failures from the Right Place

When you have a `Throwable primary`:

~~~java
Throwable[] sideFailures = primary.getSuppressed();
for (Throwable secondary : sideFailures) {
    System.err.println("suppressed: " + secondary);
}
~~~

This is a fragment assuming `primary` exists. `getSuppressed()` returns an array that may be empty; never unconditionally access `[0]` when there are no suppressed exceptions.

Suppressed exceptions matter because they:
- Show that cleanup/close also failed after the primary cause.
- Help identify which resource had a problem.
- Carry their own stack trace, which may point to a different layer.
- Can indicate that resource state is uncertain.

When logging, pass the **primary `Throwable`** to a logger capable of printing causes and suppressed exceptions so information is not lost. Logging only `e.getMessage()` or throwing a new wrapper without a cause hides evidence.

### 13.1. How Does It Differ from `cause`?

- **Cause:** usually represents "the outer exception was caused by the inner exception", for example `new IllegalStateException("failed", ioException)`.
- **Suppressed:** represents secondary errors attached to the primary exception, typically cleanup failures occurring when a primary exception already exists.

Do not assume suppressed exceptions are part of `getCause()` by default. If an exception has both a cause and suppressed exceptions, you must inspect both. `Throwable.printStackTrace()` normally displays these relationships; logger configurations may abbreviate or truncate them, so diagnostic tooling should preserve full details when possible.

### 13.2. Pitfalls of Attaching Suppressed Exceptions Manually

`Throwable.addSuppressed(other)` has constraints: a throwable cannot be added as suppressed to itself, and the argument must not be null. If suppression was disabled when creating a `Throwable` via a special constructor, adding may have no observable effect. With ordinary throwables created by `IOException`, suppression behaves as shown in the examples.

Do not write code that unconditionally calls `primary.addSuppressed(closeFailure)` in every situation without knowing exception ownership, because you may accidentally add it multiple times or record the same failure repeatedly. Try-with-resources is usually more reliable when you only need to clean up `AutoCloseable` resources.

## 14. Resource Opened Successfully, Then `close()` Throws: Should You Close Twice?

If `close()` throws, you cannot conclude whether the resource is fully closed or still open: that depends on the implementation. For example, a close might have already released the handle and then thrown while flushing a buffer; calling `close()` again will not necessarily ensure the data is written. Conversely, an early failure in close might leave the resource unreleased.

A fake should model the exact contract when testing retry-close policies. Do not assume by default that:
- `close()` is always idempotent for every `AutoCloseable`.
- A throwing `close()` means the resource is definitely still open.
- Calling `close()` twice is safe.
- Close failures only affect logs and never affect outcomes.

### 14.1. Testing Use-After-Close When It Matters

If your API requires that a resource not be used after `close()`, the fake can maintain a `closed` flag and throw `IllegalStateException` when `read()`/`write()` is called after closing. Tests should separate:
- How many times `close` was requested.
- Whether the resource reports itself as closed.
- Whether business methods still call the resource after close.

However, do not impose "every resource throws when read after close" onto all libraries if the real contract differs. The fake should reflect **the contract you need to guarantee**.

## 15. Simulating Multi-Tier Initialization Failures

Consider a service that needs three resources:

~~~text
Open A ──> Open B ──> Open C ──> process
            |
            +-- B init fails
                |
                +-- A must be cleaned up
                +-- C must not be opened
                +-- body does not run
~~~

A thorough test suite should check:
1. If A init fails, there is no B/C/body.
2. If B init fails, A closes; C/body do not run.
3. If C init fails, B then A close; body does not run.
4. If C init fails and both B/A closes fail, C init is primary, and B/A closes are suppressed in order.
5. If the body fails, C/B/A close in reverse order; the body failure remains primary.
6. If the body succeeds and `C.close` fails, B/A are still attempted to be closed.

You only need to change the fake configuration in each test; there is no need to create real databases or sockets with random faults.

### 15.1. Partial Constructor Failure and Internal Cleanup Responsibility

Suppose you create a `CompositeClient` consisting of a socket and a buffer. If the socket is already open but creating the buffer throws, the `CompositeClient` object may not have finished construction; an outer try-with-resources will not call `CompositeClient.close()` on an object whose constructor failed. The factory/constructor must clean up the socket along the failure path.

A dedicated test using a fake socket will verify:
- the socket is created successfully;
- the second step throws;
- `socket.close` is called exactly once;
- the second-step error remains primary if `socket.close` also throws.

This check differs from testing that header resource A is closed when B init fails. You need to know **which resource owns the handle at each stage**.

## 16. Asynchronous Testing Requires Additional Synchronization

For example, `ExecutorService.submit` runs a task containing try-with-resources. If the task throws a body or close error, `Future.get()` may throw `ExecutionException` with the corresponding cause. The test must inspect **the task's cause**, not merely see that `get()` failed:

~~~java
Future<Void> future = executor.submit(() -> {
    try (FakeResource r = openFake()) {
        performWork(r);
    }
    return null;
});

ExecutionException wrapper = assertThrows(
        ExecutionException.class, future::get);
Throwable cause = wrapper.getCause();
~~~

This is a **JUnit 5 fragment**, assuming `executor`, `FakeResource`, `openFake`, `performWork`, and imports exist. If the resource is created and used inside a worker, a shared event log must be thread-safe or read **after a synchronization point** such as `get()` or `CountDownLatch.await()`. An `ArrayList` written concurrently by multiple threads is unsafe; replace it with a suitable synchronized list/queue when needed.

Do not use `Thread.sleep(100)` and then assert "close was called", because scheduling varies by machine. Use `Future` completion or a latch to establish the proper happens-before relationship.

### 16.1. Do Not Confuse Cancellation with Successful Close

If a task is being canceled or interrupted:
- Exiting try-with-resources when the task actually leaves scope triggers cleanup.
- `Future.cancel(true)` is only a cancellation/interrupt request subject to the implementation and the worker's cooperation.
- `Future.isCancelled()` **does not guarantee** that `close()` has executed.
- If a worker is blocked indefinitely in an API that does not support interruption, cleanup may not have run yet either.
- If `close()` throws while an interruption exception is active, you must check the primary/suppressed behavior of the actual execution path.

Tests that need to confirm cleanup must have a **channel confirming the worker has exited** (a latch in `finally`, job state, or an equivalent mechanism), rather than only asserting `cancel(true) == true`.

## 17. When to Use Mockito Instead of a Hand-Written Fake?

If a dependency is a large interface and the goal is only to verify the number of `close()` calls, a mock can save code. An illustrative Mockito example:

~~~java
AutoCloseable resource = mock(AutoCloseable.class);
doThrow(new IOException("close failed")).when(resource).close();
~~~

This is a **Mockito fragment**, requiring the Mockito dependency, imports/static imports, and an appropriate test environment. `AutoCloseable.close()` declares `throws Exception`, so the checked exception `IOException` can be configured there according to the interface.

However, a mock does not automatically prove the closing order of multiple objects, does not automatically test partial acquisition, and does not guarantee that the fake setup matches real resource behavior. When you need to test a state machine and multiple failure scenarios, a fake with an event log is usually easier to read. When you need short interaction verification in a service, Mockito/JUnit is a reasonable choice.

**There is no need to bring Mockito into the runnable Java 17 example** in this lesson; the core behavior is verified with a plain-Java fake.

## 18. Distinguishing "Fake Verifying Java Semantics" from "Integration Test Verifying Infrastructure"

A fake resource is a **unit-test double**. By itself, it cannot prove that:
- The OS flushed data to disk.
- A real socket was released at the right time.
- A real JDBC driver handles `close` errors as assumed.
- An HTTP request was canceled by the remote server.
- A connection pool recovers to a clean state after a close exception.
- A native/library resource closes safely while interrupted.

Use complementary integration tests when the real contract depends on a driver, filesystem, or server. For example, a database may need tests for connection errors, rollback, close, and transaction state against a real test instance. However, integration tests cannot deterministically force every hardware fault either; you may need fault injection in a client adapter, proxy, or controlled test fixture.

### 18.1. An Adapter Layer Makes Failure Testing Easier

If business code calls `Files.newOutputStream` directly everywhere, it is hard to replace with a fake to proactively trigger init/close failures. You can extract resource creation into an interface/factory:

~~~java
@FunctionalInterface
interface ResourceFactory<R extends AutoCloseable> {
    R open() throws Exception;
}
~~~

This is a **Java 17 fragment**. A business method accepting `ResourceFactory<R>` can use a fake in unit tests and the real implementation in production. However, choosing the broad checked exception `Exception` here is only for illustration; production code should narrow the type when appropriate, such as `IOException`.

Dependency injection does not require a framework: constructor injection or passing a factory to a method is enough for many simple tests. What matters is creating a seam to inject failures **at the exact right time** without modifying business source code just for tests.

## 19. Checking Error Details Beyond the Message

A test that only asserts `error.getMessage()` is a step, but it may not be enough. You should evaluate:
- **Exception type** (`IOException`, `SQLException`, custom type).
- **Identity** if you injected the exact exception object and the test requires that exact cause.
- **Cause chain**, if a service wraps exceptions.
- **Suppressed list** (length, order, type, message).
- **State** of the resource and data after the failure.
- **Side effects** that occurred before the failure.
- **Logging/reporting** if the contract requires it.
- **Close call count and order**.
- **Leaks** when an exception occurs in an initializer or body.

With standard try-with-resources, suppressed exceptions are attached to the primary exception when close failures occur during unwinding. But if an upper layer wraps the exception with `new RuntimeException("...", e)`, you must inspect `e` (the wrapper's cause) to find the suppressed exceptions in the right place; do not assume suppressed exceptions from the cause are automatically copied onto the wrapper.

### 19.1. Avoid Asserting Stack Trace Line Numbers in Business Unit Tests

You can assert the class/method of a `Throwable` if needed for investigation, but hardcoding `FakeResourceFailureDemo.java:42` in a unit test is brittle when adding comments or refactoring. The goal of this lesson is **lifecycle semantics and exception preservation**, not source line layout. Asserting type/cause/suppressed/events is much more durable.

## 20. Common Anti-Patterns

### 20.1. "The test saw an `IOException`, so cleanup is fine"

Wrong: it could have been an init, body, or close failure. Check **the primary error source, suppressed exceptions, and the event log**.

### 20.2. "If closing B throws, A must have been closed"

True for try-with-resources that registered both A and B without anything abnormal breaking the cleanup flow; **false** for unprotected hand-written `finally { b.close(); a.close(); }`. Test the actual implementation.

### 20.3. "If a constructor throws, TWR will call `close` on the failing object itself"

Wrong: the resource initializer did not return a complete object. TWR only cleans up previously initialized resources; cleaning up partial acquisition inside a constructor/factory is a separate responsibility.

### 20.4. "Close failures always become primary"

Wrong: if the body or a later initializer already threw a primary exception, the close failure is suppressed. If the body succeeded, the first close failure (in closing order) can become primary.

### 20.5. "`getSuppressed()[0]` is always present"

Wrong: the array can be empty. Always check or iterate with a loop; do not turn diagnostic code into a source of `ArrayIndexOutOfBoundsException`.

### 20.6. "`close()` throwing means the resource is definitely still open"

Wrong: the implementation may have already released most resources before throwing. You only know the real state through the contract and proper observation.

### 20.7. "A fake with the right output proves a real DB rolls back properly"

Wrong: a fake does not replace a driver and transaction protocol. You need integration tests, transaction semantics, and real evidence.

### 20.8. "Reusing one fake across multiple tests is more convenient"

Old events and state easily cause false positives or false negatives. Create a fresh fake for each test or reset via an explicit mechanism so the suite does not depend on execution order.

### 20.9. "Just call `close` from an external thread after cancel"

Not necessarily safe for shared resources; proper ownership and thread-safety are required. When a worker has not yet exited scope, external cleanup can race with the worker.

### 20.10. "Just catch `Throwable` in the fake so tests don't crash"

Broad catches can hide real bugs in test logic. Catch only the type the test is checking; let assertion failures and unexpected exceptions fail the test.

### 20.11. "Mocking `close()` to throw is enough to test all bugs"

Simulating a failure at close does not cover init failures, close order, partially opened resources, or side effects. You need a full test matrix across all failure points.

### 20.12. "Suppressed = cause"

They are two different mechanisms. Close failures go into the primary exception's suppressed list in try-with-resources, not necessarily into `getCause()`.

## 21. Decision Tree When Building a Fake Resource Test Suite

~~~text
Does the application own AutoCloseable resources?
|
+-- How many resources are initialized?
|     +-- One: test init-fail / body-fail / close-fail
|     +-- Multiple: test failure at each init position and reverse close
|
+-- Can the body throw?
|     +-- Yes: have body throw X and close throw Y, verify X is primary
|     +-- No: have close throw, verify close failure is primary
|
+-- Does the constructor/factory allocate internally?
|     +-- Yes: test partial acquisition cleanup
|     +-- No: test close of successfully initialized resources
|
+-- Are there persistent side effects?
|     +-- Yes: add transaction/rollback/compensation tests
|     +-- No: verify in-memory state and event log
|
+-- Is there an executor/concurrency?
      +-- Yes: synchronize with latch/future and thread-safe event log
      +-- No: plain-Java fake is sufficient
~~~

This is a decision diagram for test design. Not every project needs the same number of cases, but every behavior that the API **promises** must have its failure paths tested.

## 22. QA Checklist for Fake Resources

- [ ] The fake implements the exact `AutoCloseable` interface or resource contract to be simulated.
- [ ] There is a deterministic way to inject failures at the initializer and at `close()`.
- [ ] With multiple resources, the event log records accurate identity and init/close order.
- [ ] Each test uses its own fake/state, with no data leaking between tests.
- [ ] There is an all-success baseline case.
- [ ] There is a case where resource A init fails: body does not run, `close` is not called on the failed A.
- [ ] There is a case where B init fails after A: A is closed, B has no `close:B`.
- [ ] There is a case where body throws X and close throws Y: X is primary, Y is suppressed.
- [ ] There is a case where body succeeds and close throws: the close failure reaches the caller.
- [ ] There is a case where two closes both fail: all eligible resources are still attempted to be closed; suppressed order is exact.
- [ ] There is a case where a constructor/factory opens internal resources and then fails: partially opened handles are cleaned up according to ownership.
- [ ] Assert type, cause, suppressed, event log, and resource state; not just a single message string.
- [ ] Do not hardcode source line numbers in lifecycle tests.
- [ ] For concurrency, establish a reliable synchronization point before asserting cleanup.
- [ ] Do not treat a canceled `Future` as proof that the worker has finished cleanup.
- [ ] If the real resource has transactions/flushing, have separate integration tests for postconditions.
- [ ] Do not double-log exceptions or swallow failures and return false success.
- [ ] Preserve cause and suppressed exceptions when wrapping exceptions across layers.
- [ ] Do not use a fake to promise behavior that a real driver or remote service does not guarantee.

## 23. Practice Exercise

A service needs to open an `InputStream` to read a configuration file while also opening an `OutputStream` to write results. In order, it opens input, opens output, reads data, writes results, and then exits try-with-resources.

Build a `FakeInput` and `FakeOutput` with failure options:
1. Input init fails before output starts; assert output is never opened.
2. Input opens successfully, output init fails; assert input is closed once and the body does not run.
3. Body read throws `IOException("read failed")`, input close also fails, and output close fails; assert the read failure is primary and the two close failures are suppressed in **reverse closing order**.
4. Body succeeds, only output close fails; assert the caller receives the output close failure.
5. Output close fails and then input close fails; assert input is still attempted to be closed.
6. Output constructor opens a temporary file before init fails; assert the factory-owned temporary file is cleaned up, without expecting TWR to call `close()` on the partially initialized object.
7. If the output file was partially written before close failed, define what output state is allowed to exist and how transactions/staging/publish solve consistency.
8. With a task running on `ExecutorService`, verify that body/close failures travel through `ExecutionException.getCause()`; add a latch to verify cleanup when cancellation is requested.

Use one event log per test, inject distinctly named exceptions (`input-init`, `output-init`, `read`, `write`, `input-close`, `output-close`), and assert both **the exception outcome and the operation history**. There is no need to corrupt real files or networks to reproduce failure cases.

## 24. Conclusion

A fake resource lets you create failure conditions at **exact lifecycle points** and prove that the program reacts correctly, instead of waiting for the OS or a real dependency to occasionally fail. For Java try-with-resources, the key properties to test are:

- Successfully initialized resources are closed in **reverse order**.
- Failures from the body or an initializer are preserved as **primary** when cleanup also throws.
- Secondary `close()` failures are placed in **`getSuppressed()`**, without erasing the primary failure.
- A resource that **fails to initialize** does not have `close()` called on it automatically by TWR, so the constructor/factory must clean up internally allocated parts.
- Cleanup does not mean rolling back prior side effects.

**Reliable test results** must verify the exception, suppressed exceptions, event order, and resource postconditions. When applied to real files, sockets, or databases, combine unit tests using fakes with integration tests at infrastructure boundaries so you do not infer guarantees that the resource implementation does not provide.
