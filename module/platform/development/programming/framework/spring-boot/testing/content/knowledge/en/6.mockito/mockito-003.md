# Mockito: when–thenReturn, thenThrow, and Simulating Multiple Calls

## 1. Lesson Goals and Spring Boot Context

In Java/Spring Boot testing, **Mockito** simulates a dependency's behavior so we can test logic without accessing a real database, HTTP service, queue, or file system. Two groups of operations must be distinguished:

- **Stubbing (configuring responses):** specifies what the mock should do when receiving a matching call, such as `when(repository.findName("A")).thenReturn("Lan")`.
- **Verification (verifying interactions):** checks how many times the code under test actually called the mock, with which arguments, and (when important) in what order, e.g., `verify(repository, times(2)).findName("A")`.

`when(...).thenReturn(...)` provides normal results; `when(...).thenThrow(...)` simulates errors. **Consecutive stubbing** lets multiple calls to **the same method with the same argument matcher conditions** return different results in sequence: fail first, succeed next; run out of data; or step through a series of states.

This lesson applies to common scenarios:

1. A repository/mock returns a fixed value.
2. A remote client suffers a transient failure and succeeds on retry.
3. A dependency returns different values on the 1st, 2nd, 3rd, and subsequent calls.
4. A service stops retrying after a maximum number of attempts; the actual call count must be verified.
5. `void` methods throwing errors; checked exceptions; spies calling real methods during setup.
6. Argument- or state-based mocking when a fixed sequence is insufficient.
7. Distinguishing mocked unit tests from real tests of HTTP timeouts, retry policies, and consistency.

**Principle:** Stubs represent initial data/conditions; assertions represent the code's outcome; verification represents important interactions. Stubbing correctly when the code never calls the dependency **does not prove the business logic works**.

## 2. Basic API: when, thenReturn, thenThrow

Mockito commonly uses these static methods:

| API | Meaning | Pattern |
| --- | --- | --- |
| `mock(Type.class)` | Creates a mock of the type | `Client client = mock(Client.class);` |
| `when(mock.call(args))` | Starts defining behavior for a call **with a return value** | `when(client.read("A"))` |
| `thenReturn(value)` | Returns a value | `when(client.read("A")).thenReturn("ok");` |
| `thenThrow(exception)` | Throws the specified exception | `when(client.read("A")).thenThrow(new IllegalStateException());` |
| `thenThrow(ExceptionType.class)` | Mockito instantiates an exception of the specified type on call | `when(client.read("A")).thenThrow(IllegalStateException.class);` |
| `thenAnswer(answer)` | Computes a dynamic response from the invocation | `when(client.read(anyString())).thenAnswer(inv -> ...);` |
| `doThrow(...).when(mock).voidMethod()` | Simulates an error on a `void` method | `doThrow(new IllegalStateException()).when(client).reset();` |
| `verify(mock, times(n)).call(args)` | Verifies exactly `n` matching calls | `verify(client, times(2)).read("A");` |
| `InOrder` | Verifies interaction order when ordering is part of the contract | `InOrder order = inOrder(client);` |

### A Single Fixed Response

```java
Client client = mock(Client.class);
when(client.read("A")).thenReturn("READY");

String result = client.read("A");  // "READY"
String again = client.read("A");   // "READY"

verify(client, times(2)).read("A");
```

This is an **excerpt**: `Client` and `read` are illustrative interfaces, not a standalone Java class; the complete runnable example is in Section 7.

On a regular mock, `when(client.read("A"))` **does not perform real I/O**; Mockito records the invocation and stores the behavior. If a method is unstubbed, the mock usually returns a type-appropriate default value (e.g., `null` for typical references, `false` for `boolean`, `0` for `int`; some types receive empty objects via Mockito support). Do not rely on defaults instead of explicitly stubbing an important contract.

### Simulating Exceptions

```java
when(client.read("A"))
    .thenThrow(new IllegalStateException("Remote unavailable"));

assertThrows(IllegalStateException.class, () -> client.read("A"));
```

`thenThrow` fits methods **with a return value**. In a regular mock stub, the exception is thrown when the **method is actually called**, not when `thenThrow` is declared. If the code does not touch the dependency, no exception is thrown. This lets us test the service's error-handling logic rather than testing the mock directly.

## 3. Simulating Consecutive Calls with thenReturn

There are two main syntaxes, **identical in meaning**:

```java
when(client.read("A")).thenReturn("one", "two", "three");
```

```java
when(client.read("A"))
    .thenReturn("one")
    .thenReturn("two")
    .thenReturn("three");
```

Behavior:

| Call to `client.read("A")` | Value |
| --- | --- |
| 1 | `"one"` |
| 2 | `"two"` |
| 3 | `"three"` |
| 4 | `"three"` |
| 5, 6, ... | `"three"` |

**Crucial rule:** once the listed results are exhausted, **the last behavior repeats for all subsequent calls**. Mockito does not default to `null` or signal end-of-sequence. Similarly, if the chain ends with `thenThrow`, subsequent calls keep throwing the last exception.

### Implications for Tests

- To know the service actually called three times, you must write `verify(client, times(3)).read("A")`.
- Using `thenReturn("one","two")` **does not** mean the dependency is only allowed to be called twice.
- In retry tests, you often want “fail on first attempt, succeed on second”; verification must prove the service **stops** after succeeding.
- A sequence belongs to **mock + method + argument matching condition**: `read("A")` and `read("B")` can have two independent stubs.

### Do Not Confuse with Redeclaring a Stub

```java
when(client.read("A")).thenReturn("one");
when(client.read("A")).thenReturn("two");
```

This is **two stub declarations for the same call**; the later declaration takes precedence rather than returning “one then two”. For sequential behavior, pass `thenReturn("one","two")` or chain `thenReturn` on **the same** `OngoingStubbing`.

Also note: if the first stub throws an exception, attempting `when(client.read("A")).thenReturn("new")` in a second declaration may trigger that exception during re-setup. Use `doReturn("new").when(client).read("A")` if you genuinely must replace an exception-throwing stub, though creating a fresh mock per test is cleaner than overriding complex behavior.

## 4. Combining thenThrow and thenReturn to Test Retries

Suppose a remote catalog experiences brief interruptions: the first call throws `TemporaryFailure`, and the second returns data. Proper stubbing:

```java
when(client.read("SKU-1"))
    .thenThrow(new TemporaryFailure("timeout"))
    .thenReturn("Product price: 100");

String result = service.loadWithRetry("SKU-1", 3);

assertEquals("Product price: 100", result);
verify(client, times(2)).read("SKU-1");
```

This excerpt uses `service` and `TemporaryFailure` defined in Section 7. If `loadWithRetry` retries only the right transient error and stops on success, attempt 1 fails and attempt 2 succeeds. Even though the stub allows further calls to keep returning the success value, the code **must not make a third call**.

Common sequences:

| Scenario | Stub | Expected interaction |
| --- | --- | --- |
| Immediate success | `thenReturn("ok")` | Called 1 time |
| Transient failure then success | `thenThrow(new TemporaryFailure()).thenReturn("ok")` | Called 2 times |
| Two failures then success | `thenThrow(e1).thenThrow(e2).thenReturn("ok")` | Called 3 times if retry budget allows |
| All three calls fail | `thenThrow(new TemporaryFailure("down"))` | Service throws after 3 calls, verify `times(3)` |
| Success then failure on next call | `thenReturn("ok").thenThrow(e)` | Only shows the failure if the service actually calls again |
| Two values then fixed | `thenReturn("A","B")` | From the 2nd call onward, always returns `"B"` |
| Exception sequence | `thenThrow(e1, e2)` | Call 1 throws `e1`; from call 2 onward throws `e2` unless another behavior follows |

If a **retry budget** says “at most three attempts,” agree whether that means **3 total attempts** or “1 initial call + 3 retries” (= 4 attempts). That is a contract detail the test must make explicit. In Section 7's example, `maxAttempts=3` means **at most 3 total calls**.

### The Final Exception Can Repeat Too

```java
when(client.read("A"))
    .thenReturn("first")
    .thenThrow(new IllegalStateException("outage"));
```

- Call 1: returns `first`.
- Call 2: throws `IllegalStateException`.
- Call 3 onward: continues throwing the exception per the final behavior.
- To simulate “fail twice, then succeed,” the order must be `thenThrow(e1).thenThrow(e2).thenReturn("ok")`.

Never treat “configured 3 results” as proof that the service made 3 calls. `verify` and return assertions are the proof.

## 5. Checked Exceptions, Unchecked Exceptions, and Throwing Conditions

Java distinguishes:

- **Unchecked exceptions**: `RuntimeException` and subclasses; typically stubbed with `thenThrow` without requiring `throws` on the method.
- **Checked exceptions**: e.g., `IOException`; Mockito requires the checked exception type to be **compatible with the stubbed method's `throws` declaration**, otherwise it reports a stubbing configuration error. Check compiler/Mockito enforcement against the real signature.

Valid example:

```java
interface FileGateway {
    String download(String path) throws java.io.IOException;
}
```

```java
FileGateway gateway = mock(FileGateway.class);

when(gateway.download("report.txt"))
    .thenThrow(new java.io.IOException("Network failed"))
    .thenReturn("OK");
```

In Java, the test method containing `when(gateway.download(...))` must declare `throws IOException` or handle the checked exception because the Java expression still carries the `throws` signature. A complete test appears in Section 7.

Example **violating the contract**:

```java
interface SimpleGateway {
    String ping(); // Does not declare throws IOException.
}
// Mockito rejects stubbing ping() to throw an undeclared checked IOException:
// when(mock.ping()).thenThrow(new IOException("x"));
```

This is not “HTTP simulation succeeded,” it is an invalid test definition. In real adapters, you may need to throw an unchecked wrapper like `RemoteServiceUnavailableException` or declare `throws IOException` on the method appropriately.

With `thenThrow(SomeException.class)`, Mockito instantiates an exception of that class when called; with an instance `thenThrow(new SomeException("message"))`, the test can assert a stable message. Avoid asserting full stack traces from mocked exceptions; stack trace details depend on exception instantiation and the JVM.

## 6. void Methods: doThrow, doNothing, and Behavior Chains

`when(mock.voidMethod())` **does not compile**, because `void` is not a value that can be passed to `when(T)`. Use the `do...when(...)` family:

```java
Notifier notifier = mock(Notifier.class);
doThrow(new IllegalStateException("service stopped"))
    .when(notifier).send("message");

assertThrows(IllegalStateException.class,
    () -> notifier.send("message"));
```

`Notifier` is an illustrative interface; the runnable test in Section 7 uses an `evict` method.

On a regular mock, `void` already **does nothing** by default, so `doNothing()` alone is usually redundant. It is useful when chaining behaviors:

```java
doThrow(new IllegalStateException("busy"))
    .doNothing()
    .when(notifier).send("message");
```

When calling `send("message")`:

- Call 1: throws `IllegalStateException`.
- Call 2: does nothing.
- Call 3 onward: repeats the final behavior (`doNothing`) in the same stub.
- You can chain `doThrow`/`doNothing`/`doAnswer` on the same `Stubber` when multi-step scenarios are needed.

**Warning:** `doThrow` does not “bypass” checked exception rules. If you pass `doThrow(new IOException())` to a `void send()` method that does not declare `throws IOException`, Mockito rejects the invalid checked exception. Only a `void` method declaring `throws IOException` can be stubbed with `doThrow(new IOException(...))`.

## 7. Complete Practice Example: JUnit Jupiter + Mockito + Java 17

This example tests mocks and a small retry service **without a database, network, or starting a Spring context**. It uses Spring Boot 3.5.0 as a sample version so the Spring Boot BOM manages Mockito/JUnit. In a real project, keep your existing Spring Boot version and only add `spring-boot-starter-test` in test scope; do not copy version numbers blindly.

### 7.1. Structure

```text
mockito-sequence-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── MockitoSequenceTest.java
```

### 7.2. Complete pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>mockito-sequence-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 7.3. File src/test/java/example/MockitoSequenceTest.java

```java
package example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class MockitoSequenceTest {

    interface RemoteCatalog {
        String read(String key);
        void evict(String key);
        String download(String path) throws IOException;
    }

    static final class TemporaryFailure extends RuntimeException {
        TemporaryFailure(String message) {
            super(message);
        }
    }

    static final class CatalogService {
        private final RemoteCatalog remote;

        CatalogService(RemoteCatalog remote) {
            this.remote = remote;
        }

        // maxAttempts is the total number of calls, including the initial call.
        String loadWithRetry(String key, int maxAttempts) {
            if (maxAttempts < 1) {
                throw new IllegalArgumentException("maxAttempts must be >= 1");
            }

            for (int attempt = 1; attempt <= maxAttempts; attempt++) {
                try {
                    return remote.read(key);
                } catch (TemporaryFailure ex) {
                    if (attempt == maxAttempts) {
                        throw ex;
                    }
                }
            }

            throw new IllegalStateException("unreachable");
        }
    }

    @Test
    void oneStubReturnsSameResultOnEachCall() {
        RemoteCatalog remote = mock(RemoteCatalog.class);
        when(remote.read("A")).thenReturn("READY");

        assertEquals("READY", remote.read("A"));
        assertEquals("READY", remote.read("A"));

        verify(remote, times(2)).read("A");
        verifyNoMoreInteractions(remote);
    }

    @Test
    void thenReturnSequenceRepeatsTheLastValue() {
        RemoteCatalog remote = mock(RemoteCatalog.class);
        when(remote.read("A")).thenReturn("one", "two", "three");

        assertEquals("one", remote.read("A"));
        assertEquals("two", remote.read("A"));
        assertEquals("three", remote.read("A"));
        assertEquals("three", remote.read("A"));

        verify(remote, times(4)).read("A");
        verifyNoMoreInteractions(remote);
    }

    @Test
    void transientFailureThenSuccessNeedsExactlyTwoCalls() {
        RemoteCatalog remote = mock(RemoteCatalog.class);
        when(remote.read("SKU-1"))
                .thenThrow(new TemporaryFailure("temporary outage"))
                .thenReturn("DATA");

        CatalogService service = new CatalogService(remote);

        assertEquals("DATA", service.loadWithRetry("SKU-1", 3));
        verify(remote, times(2)).read("SKU-1");
        verifyNoMoreInteractions(remote);
    }

    @Test
    void persistentTransientFailureStopsAfterThreeAttempts() {
        RemoteCatalog remote = mock(RemoteCatalog.class);
        when(remote.read("SKU-2"))
                .thenThrow(new TemporaryFailure("still down"));

        CatalogService service = new CatalogService(remote);

        TemporaryFailure ex = assertThrows(TemporaryFailure.class,
                () -> service.loadWithRetry("SKU-2", 3));
        assertEquals("still down", ex.getMessage());
        verify(remote, times(3)).read("SKU-2");
        verifyNoMoreInteractions(remote);
    }

    @Test
    void voidMethodCanThrowAndThenDoNothing() {
        RemoteCatalog remote = mock(RemoteCatalog.class);
        doThrow(new IllegalStateException("busy"))
                .doNothing()
                .when(remote).evict("SKU-3");

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> remote.evict("SKU-3"));
        assertEquals("busy", ex.getMessage());

        remote.evict("SKU-3");
        remote.evict("SKU-3");

        verify(remote, times(3)).evict("SKU-3");
        verifyNoMoreInteractions(remote);
    }

    @Test
    void checkedIOExceptionCanBeStubbedWhenDeclared() throws IOException {
        RemoteCatalog remote = mock(RemoteCatalog.class);
        when(remote.download("report.txt"))
                .thenThrow(new IOException("network"))
                .thenReturn("REPORT");

        IOException ex = assertThrows(IOException.class,
                () -> remote.download("report.txt"));
        assertEquals("network", ex.getMessage());
        assertEquals("REPORT", remote.download("report.txt"));

        verify(remote, times(2)).download("report.txt");
        verifyNoMoreInteractions(remote);
    }

    @Test
    void thenAnswerCanUseAnInvocationCounter() {
        RemoteCatalog remote = mock(RemoteCatalog.class);
        AtomicInteger count = new AtomicInteger();

        when(remote.read("SKU-4")).thenAnswer(invocation -> {
            int attempt = count.incrementAndGet();
            if (attempt == 1) {
                throw new TemporaryFailure("first call failed");
            }
            return "DATA-" + attempt;
        });

        CatalogService service = new CatalogService(remote);

        assertEquals("DATA-2", service.loadWithRetry("SKU-4", 3));
        assertEquals(2, count.get());
        verify(remote, times(2)).read("SKU-4");
        verifyNoMoreInteractions(remote);
    }

    @Test
    void differentArgumentsHaveIndependentStubs() {
        RemoteCatalog remote = mock(RemoteCatalog.class);
        when(remote.read("A")).thenReturn("A1", "A2");
        when(remote.read("B")).thenReturn("B1", "B2");

        assertEquals("A1", remote.read("A"));
        assertEquals("B1", remote.read("B"));
        assertEquals("A2", remote.read("A"));
        assertEquals("B2", remote.read("B"));

        verify(remote, times(2)).read("A");
        verify(remote, times(2)).read("B");
        verifyNoMoreInteractions(remote);
    }

    @Test
    void doReturnAvoidsInvokingRealMethodOnSpyDuringSetup() {
        List<String> listSpy = spy(new ArrayList<>());
        doReturn("virtual").when(listSpy).get(0);

        assertEquals("virtual", listSpy.get(0));
        verify(listSpy).get(0);
        verifyNoMoreInteractions(listSpy);
    }
}
```

### 7.4. Running Tests and Expected Output

In the directory containing `pom.xml`:

```bash
mvn test
```

Or run only this class:

```bash
mvn test -Dtest=MockitoSequenceTest
```

**Expected:** All 9 `@Test` methods PASS; there is no `System.out.println`, so no fixed application stdout. Maven Surefire summarizes test counts and results in `target/surefire-reports`. The examples above clearly fix stubbing order and call counts; exact Maven output depends on plugin version and logging configuration.

Covered scenarios:

| Test method | Stub | Primary assertion | Verification |
| --- | --- | --- | --- |
| `oneStubReturnsSameResultOnEachCall` | Single `thenReturn` | Both calls return `READY` | `times(2)` |
| `thenReturnSequenceRepeatsTheLastValue` | `one,two,three` | Call 4 still returns `three` | `times(4)` |
| `transientFailureThenSuccessNeedsExactlyTwoCalls` | Error then data | Retry service returns `DATA` | `times(2)` |
| `persistentTransientFailureStopsAfterThreeAttempts` | Always throws | Service throws after 3rd attempt | `times(3)` |
| `voidMethodCanThrowAndThenDoNothing` | `doThrow` then `doNothing` | Only first call throws | `times(3)` |
| `checkedIOExceptionCanBeStubbedWhenDeclared` | `IOException` then string | Error then `REPORT` | `times(2)` |
| `thenAnswerCanUseAnInvocationCounter` | Dynamic call counter | `DATA-2` | `times(2)` |
| `differentArgumentsHaveIndependentStubs` | Two keys, two sequences | A1/B1/A2/B2 | Each key 2 times |
| `doReturnAvoidsInvokingRealMethodOnSpyDuringSetup` | Stub spy without calling real method on setup | Returns `virtual` from empty list | `get(0)` 1 time |

The demo places helper classes inside the test file to run standalone. In a real application, move `CatalogService` and `RemoteCatalog` to `src/main/java`, import them into the test, and let mocks simulate only the boundary. Do not include Mockito on the production classpath unless there is a special requirement.

## 8. How Does when(...).thenReturn Differ from doReturn(...).when?

For regular mocks, prefer `when(...).thenReturn(...)` because it is easier to read and provides compile-time return type checking. However, with a **spy** (an object wrapped/copied to preserve part of real behavior), the call inside `when(spy.realMethod())` can **execute the real method immediately during setup**.

Example:

```java
List<String> spyList = spy(new ArrayList<>());

// UNSAFE: list is empty, spyList.get(0) can throw during stubbing.
// when(spyList.get(0)).thenReturn("virtual");

// SAFE: does not call real get(0) during setup.
doReturn("virtual").when(spyList).get(0);
assertEquals("virtual", spyList.get(0));
```

**Spies with side effects** (DB calls, file writes, counter increments…) make `when(spy.call())` very dangerous. If partial mocking is needed, consider `doReturn` / `doThrow` / `doAnswer`; however, most tests can be designed more cleanly by injecting dependencies into the service and mocking dependencies rather than spying on the business class itself.

`doReturn` accepts `Object` and therefore does not get strict compile-time type checking like `thenReturn`; type mismatches may only appear at runtime. Only use it when it provides a real benefit.

Mockito also supports sequential stubbing with `doReturn("one","two").when(mock).getValue()`; this is useful for spies or overriding a stub that already throws an exception. On regular mocks, `when(...).thenReturn("one","two")` is usually clearer.

## 9. Matchers, Multiple Arguments, and Sequence Scope

Stubs match by **method + matchers/arguments**. When there is no match, the mock uses its default behavior or another matching stub. Example:

```java
when(client.read("A")).thenReturn("A1", "A2");
when(client.read("B")).thenReturn("B1", "B2");

client.read("A"); // A1
client.read("B"); // B1
client.read("A"); // A2
client.read("B"); // B2
```

The two sequences do not consume each other's state in independent stubs like this.

### Using Matchers with Multiple Parameters

Suppose a mock has `String find(String tenant, int version)`:

```java
when(mock.find(eq("tenant-1"), anyInt()))
    .thenReturn("v1", "v2");
```

This is an **excerpt**, requiring static imports `org.mockito.ArgumentMatchers.eq` and `anyInt`. If you use a matcher for one parameter, the remaining parameters in the same invocation must also use matchers (`eq(...)` for fixed values), for example:

```java
// WRONG: mixing matcher anyInt() and literal "tenant-1".
// when(mock.find("tenant-1", anyInt())).thenReturn("x");

// RIGHT:
when(mock.find(eq("tenant-1"), anyInt())).thenReturn("x");
```

Modern Mockito's `anyString()` typically matches **non-null** strings, so if you want to simulate `null` input, use `isNull()` or an appropriate matcher; do not assume every matcher matches every value. A sequence on a broad matcher like `anyString()` can be consumed by different keys matching the same matcher; if each key needs an independent sequence, stub per key or use `thenAnswer` tracking state per key.

### Overlapping Stubs

Stubs can overlap:

```java
when(client.read(anyString())).thenReturn("generic");
when(client.read("A")).thenReturn("specific");
```

On a regular mock in this example, the more specific stub declared later takes precedence for `"A"`; other keys use the generic stub. However, having many overlapping broad/narrow stubs or overriding a throwing stub can make declaration order hard to follow. Minimize overlap and state each stub's conditions clearly.

### Verification of Count and Order

`verify(mock, times(3)).call()` checks call count; it **does not** prove calls occurred in a particular order relative to other methods. When ordering is a requirement, use `InOrder`:

```java
InOrder order = inOrder(mock);
order.verify(mock).begin();
order.verify(mock).commit();
```

This is an illustrative excerpt; `mock` must have `begin` and `commit` methods, static import `inOrder` or call `Mockito.inOrder`, and the code under test must invoke both. `InOrder` is unnecessary if you only need to count calls to the same method. Do not assert ordering that is not part of the contract: tests become brittle when refactoring implementations.

A quick reference for modes:

| Verification | Condition |
| --- | --- |
| `verify(mock).read("A")` | Exactly 1 time by default |
| `verify(mock, times(2)).read("A")` | Exactly 2 times |
| `verify(mock, never()).read("A")` | Zero matching calls |
| `verify(mock, atLeastOnce()).read("A")` | At least 1 time |
| `verifyNoInteractions(mock)` | Mock has no recorded interactions |
| `verifyNoMoreInteractions(mock)` | No unverified interactions remain |

Do not confuse `verifyNoMoreInteractions` with testing business correctness: it checks interaction details and may need to be removed if valid extra interactions are added later.

## 10. Dynamic Simulation with thenAnswer When a Fixed Sequence Is Not Enough

`thenReturn` works well when the list of results is **known upfront** and short. For responses depending on arguments, retry counts, or state inside the double, use `thenAnswer`:

```java
AtomicInteger counter = new AtomicInteger();

when(client.read(anyString())).thenAnswer(invocation -> {
    String key = invocation.getArgument(0, String.class);
    int n = counter.incrementAndGet();
    if (n == 1) {
        throw new TemporaryFailure("temporary");
    }
    return key + "-value-" + n;
});
```

This excerpt uses the illustrative `TemporaryFailure`, static imports `anyString`/`when`, and `AtomicInteger`. After call 1 throws, call 2 returns a string with the key and `2`. Note that **the counter is global to the mock**, so calling another key still increments it. If you need per-key counts, store counters in a `Map<String, Integer>` or build a stateful fake class.

Use `thenAnswer` cautiously because it can pull too much logic into the mock; if the fake turns into a complex subsystem, tests become hard to read and prone to reproducing production bugs. For retries with clock/backoff, prefer injecting a clock/scheduler/fake sleeper or controllable time utility to avoid long `Thread.sleep` calls and test flakiness.

Mockito provides the `Answer<T>` API; the lambda receives `InvocationOnMock`, from which you can inspect `getArgument(index, Type.class)`. Do not read non-existent argument indices or cast to the wrong type; the test will fail due to mock setup rather than business logic.

## 11. Using @Mock, @InjectMocks, and Spring Boot at the Right Layer

### Unit Tests with MockitoExtension

In a Spring Boot project with `spring-boot-starter-test`, Mockito provides `@Mock` and `@InjectMocks` for unit tests, typically combined with `@ExtendWith(MockitoExtension.class)`:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CatalogServiceUnitTest {
    @Mock
    RemoteCatalog remote;

    @InjectMocks
    CatalogService service;

    @Test
    void retriesOneTransientFailure() {
        when(remote.read("A"))
            .thenThrow(new TemporaryFailure("timeout"))
            .thenReturn("READY");

        assertEquals("READY", service.loadWithRetry("A", 3));
        verify(remote, times(2)).read("A");
    }
}
```

This is an **excerpt requiring `RemoteCatalog`, `CatalogService`, `TemporaryFailure`, and the static imports** from the previous section; it is not a standalone test. `@InjectMocks` attempts to inject mocks via constructor/setter/field where possible; prefer **constructor injection** so dependencies are obvious. `MockitoExtension` can enable strict stub checks by default: unused stubs are usually flagged as a sign of poor test design. Do not sprinkle `lenient()` to hide warnings; if genuinely needed, explain why.

### Inside a Spring ApplicationContext: Mocks Are Different

- `@Mock` creates a Mockito mock **outside** the Spring context when used only with `MockitoExtension`.
- `@MockitoBean` (`org.springframework.test.context.bean.override.mockito.MockitoBean`) replaces/registers a bean in the Spring test context in Spring Framework 6.2+/Spring Boot 3.4+; Boot 4 uses this annotation.
- The older Spring Boot `@MockBean` is deprecated in Boot 3.4/3.5 and should not be relied on when migrating to Boot 4.
- `@WebMvcTest` tests an MVC slice, whereas `@SpringBootTest` starts a broader Spring context. Pick the right level; there is no need to load the full Spring context just to test a retry loop.

In Spring Boot 4, there are technology-specific test starters like `spring-boot-starter-webmvc-test` in addition to the general test starter; follow your release line. Even so, **Mockito's `when/thenReturn/thenThrow` syntax stays the same in spirit** regardless of how Spring Boot configures test beans.

### Gradle Kotlin DSL

In a project with the Spring Boot plugin and dependency management applied:

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
```

With Maven, use `test` scope as in the POM in Section 7. When a project uses Spring Boot's dependency management, avoid manually mixing incompatible major versions of Mockito or JUnit without testing them.

## 12. Distinguishing Simulated Retry in Unit Tests from Real Retry

A mock sequence checks **that the code calls its dependency and handles the results**. It **does not prove**:

- The real HTTP client has proper connect/read timeouts configured.
- The real retry policy has proper backoff, jitter, or timeout budget.
- A Spring Retry/Resilience4j proxy, circuit breaker, or `@Retryable` annotation is actually applied.
- Database transactions roll back/commit accurately after failures.
- Idempotency of POST/write operations during retries.
- Logging/metrics/tracing work properly in the deployed environment.

The unit test example in Section 7 simulates a **hand-written** retry loop. If your application uses `@Retryable` via a Spring proxy, calling `new Service(...)` directly **bypasses the proxy**, so the test will not verify real retry behavior. In that case, you need an integration/slice test with an appropriate Spring context or dedicated proxy configuration test; mock the dependency at the outer boundary and verify call counts through the proxied bean. Do not add `@SpringBootTest` just to compensate for a unit test missing the logic under test.

**Test permanent failures:** when `thenThrow` always throws, the service must stop at the final attempt. **Test recovery:** when an error is followed by success, the service must stop right after succeeding. **Test non-retryable errors:** for permanent errors (`IllegalArgumentException`/validation/business denial), the system should usually throw immediately instead of retrying pointlessly. Which errors are retryable depends on the application contract.

When retrying an operation with side effects (charging, reserving stock, sending messages), a timeout **does not prove the previous attempt failed**: the dependency may have processed it while the response was lost. You need an idempotency key, deduplication, or compensation specification; mocking `thenThrow(...).thenReturn(...)` alone cannot guarantee safety for real side effects.

## 13. Common Mistakes and Fixes

| Mistake or misconception | Harm | Right approach |
| --- | --- | --- |
| Writing two `when(...).thenReturn` statements expecting consecutive calls | Later stub overwrites earlier stub | Combine `thenReturn("A","B")` or chain on the same ongoing stubbing |
| Assuming a sequence ends automatically after the last result | Test misses cases where service calls too many times | Assert `times(n)`, remember the final behavior repeats |
| Asserting only the return value without verifying retry call count | Misses redundant/excess calls | `verify(mock, times(expected)).call(...)` |
| `when(mock.voidMethod())` | Does not compile in Java | `doThrow(...).when(mock).voidMethod()` |
| `thenThrow(new IOException())` when method does not declare throws | Mockito rejects the checked exception | Use an exception matching the signature or an unchecked wrapper |
| `when(spy.method())` causes side effects or throws during setup | Test fails before invoking the code under test | `doReturn`/`doThrow` for spies |
| Using a matcher for one parameter and a literal for another | Mockito throws `InvalidUseOfMatchersException` | Use matchers for all parameters, `eq(...)` for literals |
| `anyString()` expected to match `null` | Stub is never matched | Use `isNull()`/`nullable(String.class)` per contract |
| Stubbing per key while the call passes a different key | Receives default (possibly `null`), confusing failures | Check actual arguments and stub the exact signature |
| Unused stubbing flagged by StrictStubs | Sign of excess setup or unreached code path | Fix the test and stub only interactions that will happen |
| Calling `reset(mock)` mid-test for multiple phases | Loses history and stubs, hard to inspect | Use separate tests, fresh mocks, or clean fixture setup |
| Long `Thread.sleep` to test retry | Slow and flaky tests | Inject a clock/scheduler/fake sleeper and assert attempt count |
| Using mocks to conclude real HTTP timeouts work | No real network/client exercised | Write adapter tests with WireMock/MockWebServer or proper integration tests |
| Using `times(3)` without checking outcome/exception | May call 3 times while still behaving wrongly | Combine with status/value/exception assertions |
| Overusing `verifyNoMoreInteractions` in every test | Locks down implementation details | Verify only interactions critical to the contract |

### Checklist Before Finalizing Tests

- [ ] Stubs match the right method and arguments?
- [ ] For multi-call sequences, is the order explicit and do you remember the last behavior repeats?
- [ ] Is it clear whether `maxAttempts` includes the initial attempt?
- [ ] Is success after retry asserted along with the exact call count?
- [ ] Do persistent failures stop at the exact limit?
- [ ] Are non-retryable errors thrown immediately when required?
- [ ] Do `void` methods use `doThrow`/`doNothing` properly?
- [ ] Are checked exceptions valid under `throws`?
- [ ] Does any spy avoid unintentionally invoking real methods during stubbing?
- [ ] Are matchers and literals never mixed in the same invocation?
- [ ] Are real network/DB calls absent from unit tests?
- [ ] When behavior depends on a Spring proxy, is there an appropriate context test?
- [ ] Does the test verify both business conditions and key interactions, rather than just one?

## 14. Official References

- [Mockito API — Mockito, examples of when/thenReturn/thenThrow/consecutive calls](https://javadoc.io/static/org.mockito/mockito-core/5.24.0/org.mockito/org/mockito/Mockito.html)
- [Mockito API — OngoingStubbing](https://javadoc.io/static/org.mockito/mockito-core/5.24.0/org.mockito/org/mockito/stubbing/OngoingStubbing.html)
- [Mockito API — Stubber for doThrow/doNothing](https://javadoc.io/static/org.mockito/mockito-core/5.24.0/org.mockito/org/mockito/stubbing/Stubber.html)
- [Mockito API — VerificationMode](https://javadoc.io/static/org.mockito/mockito-core/5.24.0/org.mockito/org/mockito/verification/VerificationMode.html)
- [Spring Boot — Test Scope Dependencies](https://docs.spring.io/spring-boot/reference/testing/test-scope-dependencies.html)

**Key takeaway:** `when(...).thenReturn/thenThrow` defines **what the mock returns/throws**; chaining defines **progression across multiple calls**; `verify(..., times(n))` confirms **how many times the code actually called it**. Combining business outcomes, exceptions, call counts, and retry limits produces tests that catch real bugs rather than merely proving the mock was configured.
