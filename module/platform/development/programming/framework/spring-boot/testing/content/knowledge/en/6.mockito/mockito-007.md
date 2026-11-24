# doReturn, doThrow, and Limitations When Working with Spies

When testing Java with Mockito, `mock` and `spy` do not behave the same way. With a regular mock, unstubbed methods usually do not execute real logic; with a spy, unstubbed methods **execute real logic**. As a result, a familiar line like `when(spy.someMethod()).thenReturn(value)` can invoke the real method **during test setup**, before reaching the Act step you want to test. If that method reads a file, queries a database, mutates state, or throws an exception, the test can break right in the Arrange phase.

Mockito provides the `doReturn(...)`, `doThrow(...)`, `doAnswer(...)`, `doNothing()`, and `doCallRealMethod()` APIs. For spies—especially `doReturn` and `doThrow`—these APIs configure behavior **without running the stubbed method during setup**. However, a spy is a form of *partial mock*: most of the remaining code is still real, so it does not automatically guarantee safe, deterministic, or business-accurate tests.

**After this lesson, you can:** explain how mocks differ from spies; choose properly between `when(...).thenReturn(...)` and `doReturn(...).when(...)`; use `doThrow` for both `void` and value-returning methods; understand risks involving state, side effects, AOP proxies, and private/final methods; decide when to replace a spy with dependency injection; and write runnable JUnit 5 tests with Java 17+ and Spring Boot.

## 1. Mock, Spy, and Partial Mocking

| Characteristic | `mock(MyClass.class)` | `spy(new MyClass(...))` |
|---|---|---|
| Unstubbed methods | Usually use the mock's default answer: `null`, `false`, `0`, empty collection depending on return type/Mockito configuration | Call the **real** method by default |
| Constructor and state | Regular mocks do not run the real object's constructor by default | With `spy(instance)`, you supply an initialized object; Mockito builds the spy from that state |
| Setup via `when(target.method())` | Usually invokes only the mock method to record stubbing | **Can execute the real method** on the spy |
| `doReturn(value).when(target).method()` | Stubs without running real logic | Stubs without running real logic |
| Unintended side effects | Mainly from custom answers or test logic | Can arise from any unstubbed real method |
| When to use | Need to fake a dependency outside the test's scope | Need to preserve most real behavior and replace only one part for a specific reason |
| Design risk | Over-mocking makes tests only prove fake setup | Tests couple to internal structure, state, and side effects of the real class |

**A spy is not a mock that “returns real data.”** A spy carries the object's logic and invokes real methods by default; stubbing replaces only the specified calls. You cannot assume creating a spy automatically isolates I/O, databases, threads, transactions, or calls to other dependencies.

Short example:

```java
import java.util.ArrayList;
import java.util.List;

import static org.mockito.Mockito.spy;

List<String> observedList = spy(new ArrayList<>());
observedList.add("A");                  // Calls real ArrayList.add
String value = observedList.get(0);     // Calls real ArrayList.get
// value equals "A"
```

This is an **illustrative snippet**, not a standalone Java file with `main` or `@Test`. It shows that a spy still executes `ArrayList`'s logic. Complete examples with filenames and classes appear in Sections 4–7.

## 2. Why Can `when(spy.method()).thenReturn(...)` Be Dangerous?

With this syntax:

```java
when(spy.method()).thenReturn(result);
```

Java must evaluate `spy.method()` to pass its result to `when(...)`. Because a `spy` defaults to real methods, **the method can execute while you are stubbing**, before Mockito registers the `thenReturn` result.

Consider an empty list:

```java
List<String> spyList = spy(new ArrayList<>());

// COUNTER-EXAMPLE: real ArrayList.get(0) runs on an empty list.
when(spyList.get(0)).thenReturn("A");
```

This setup line throws `IndexOutOfBoundsException` because the real `get(0)` runs when the list has no elements. No business test even ran yet; the failure happens right in Arrange.

Switch to **doReturn**:

```java
List<String> spyList = spy(new ArrayList<>());

doReturn("A").when(spyList).get(0);

assertEquals("A", spyList.get(0));
```

Here `doReturn("A")` creates a stubber configuration; the `get(0)` call after `when(spyList)` is intercepted by Mockito to identify which method to stub without running the real `ArrayList.get` during setup. When the test later calls `get(0)`, Mockito returns the stubbed value.

**Key distinction:** `doReturn` only prevents running **the stubbed method during stubbing**. Other methods on the spy still run for real and can produce side effects. It does not turn the object into a plain mock.

## 3. `doReturn(...).when(spy).method(...)`: Mechanism and How to Read It

Basic pattern:

```java
doReturn(expectedValue).when(spyObject).method(arguments);
```

Read in order:

1. `doReturn(expectedValue)` declares the desired return value for a stubbed call.
2. `when(spyObject)` specifies the Mockito-managed target object.
3. `method(arguments)` identifies the method and arguments to stub; **does not execute real logic** during setup.
4. When code in Act calls the matching method and arguments, Mockito returns `expectedValue`.
5. Unstubbed calls continue using the spy's real methods per its default answer.

Another valuable case: a method on the spy was previously stubbed to throw an exception. Using `when(spy.method()).thenReturn(newValue)` to overwrite that stub triggers the old stub's exception during `when(...)`. `doReturn(newValue).when(spy).method()` lets you replace the configuration without triggering the call during setup.

**On plain mocks**, `when(mock.method()).thenReturn(value)` is usually clearer and checks the return type through generics. `doReturn(Object)` accepts a broad type, so a type error like:

```java
// COUNTER-EXAMPLE: increase() returns int, cannot validly return String.
// This line can pass Java's type check at the doReturn call,
// but Mockito detects the incompatible type when binding the stub.
doReturn("wrong type").when(spyCounter).increase();
```

surfaces only at **runtime** when Mockito attaches the stub. Therefore, `doReturn` is an intentional choice for spies and scenarios needing to avoid calling real methods—not a reason to replace every `when(...).thenReturn(...)` across all tests.

## 4. Complete Example: Seeing Side Effects Happen During Stubbing

The example below requires no Spring context—only Java 17+, JUnit Jupiter, and Mockito. We build a counter: real `increase()` increments state; `value()` returns state; `reset()` resets to 0.

**`src/main/java/com/example/testing/Counter.java`**

```java
package com.example.testing;

public class Counter {
    private int value;

    public int increase() {
        value++;
        return value;
    }

    public int value() {
        return value;
    }

    public void reset() {
        value = 0;
    }
}
```

**`src/test/java/com/example/testing/CounterSpyTest.java`**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.when;

class CounterSpyTest {

    @Test
    void whenOnSpyRunsRealMethodDuringStubbing() {
        Counter observed = spy(new Counter());

        when(observed.increase()).thenReturn(42);

        assertEquals(1, observed.value(),
                "Real increase() already ran during stubbing");
        assertEquals(42, observed.increase(),
                "Subsequent call uses the stubbed result");
        assertEquals(1, observed.value(),
                "Stub does not increment state when called");
    }

    @Test
    void doReturnAvoidsRealCallDuringStubbing() {
        Counter observed = spy(new Counter());

        doReturn(42).when(observed).increase();

        assertEquals(0, observed.value(),
                "Not incremented during stubbing");
        assertEquals(42, observed.increase());
        assertEquals(0, observed.value(),
                "Stubbed call does not run real increase()");
    }
}
```

Both tests are designed to **pass**, yet demonstrate the exact difference:

| Point in time | `when(spy.increase()).thenReturn(42)` | `doReturn(42).when(spy).increase()` |
|---|---:|---:|
| State right after creating spy | 0 | 0 |
| State right after stub setup | **1** (because real method ran) | **0** |
| Value returned on subsequent `increase()` | 42 | 42 |
| State after the stubbed call | 1 | 0 |

If `increase()` were replaced by a method sending an email or writing a database record, the side effect would happen **before the test's Act step even began**. That is why Mockito recommends considering `doReturn`/`doThrow` when stubbing spies.

**Scope note:** the example calls the real `observed.value()` and does not stub it. For objects with complex state, assert only the business effects you need to protect instead of coupling tests to private state outside the contract.

## 5. `doThrow(...).when(spy).voidMethod()`: Simulating Errors from void Methods

A `void` method has no value to pass into ordinary `when(...)`. Thus the following syntax is **invalid Java**:

```java
// COUNTER-EXAMPLE — DOES NOT COMPILE: reset() has return type void.
when(counter.reset()).thenThrow(new IllegalStateException());
```

Valid pattern:

```java
doThrow(new IllegalStateException("reset blocked"))
        .when(counterSpy).reset();
```

Stubbing does not run the real `reset()`. Only when code later calls `counterSpy.reset()` does Mockito throw the configured `IllegalStateException`.

Place the next test file in the same package (using `Counter.java` from Section 4):

**`src/test/java/com/example/testing/CounterFailureTest.java`**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.spy;

class CounterFailureTest {

    @Test
    void doThrowForVoidMethodDoesNotResetDuringSetup() {
        Counter observed = spy(new Counter());
        observed.increase();

        doThrow(new IllegalStateException("reset blocked"))
                .when(observed).reset();

        assertEquals(1, observed.value(),
                "Stub setup does not call real reset");

        IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                observed::reset);

        assertEquals("reset blocked", failure.getMessage());
        assertEquals(1, observed.value(),
                "Real reset method does not run when stub throws");
    }

    @Test
    void doThrowAlsoWorksForMethodWithReturnValue() {
        Counter observed = spy(new Counter());

        doThrow(new IllegalStateException("counter offline"))
                .when(observed).increase();

        IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                observed::increase);

        assertEquals("counter offline", failure.getMessage());
        assertEquals(0, observed.value());
    }
}
```

Two key lessons:

- For `void` methods like `reset()`, `doThrow` is the standard, readable way to replace real behavior with an exception.
- `doThrow` **is not limited to void**. For `increase()` returning `int`, it can still simulate an error without incrementing the real counter during setup.

For a value-returning method on a **plain mock**, `when(mock.read()).thenThrow(error)` is usually more readable. On a **spy**, consider `doThrow(error).when(spy).read()` whenever real logic must not run during setup.

## 6. `doThrow` with Checked and Unchecked Exceptions

### 6.1. Unchecked Exceptions

`IllegalStateException`, `IllegalArgumentException`, or subclasses of `RuntimeException` do not require `throws` in the method signature. The `CounterFailureTest` examples use unchecked exceptions like these.

### 6.2. Checked Exceptions

Mockito validates **checked exceptions** against the method's signature. For example, a data-reading port declaring `throws IOException` can be stubbed to throw `IOException`:

```java
package com.example.testing;

import java.io.IOException;

public interface TextStore {
    String read(String path) throws IOException;
}
```

**`src/test/java/com/example/testing/TextStoreTest.java`**

```java
package com.example.testing;

import java.io.IOException;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;

class TextStoreTest {

    @Test
    void returnsConfiguredCheckedException() throws Exception {
        TextStore store = mock(TextStore.class);

        doThrow(new IOException("storage unavailable"))
                .when(store).read("welcome.txt");

        IOException thrown = assertThrows(IOException.class,
                () -> store.read("welcome.txt"));

        assertEquals("storage unavailable", thrown.getMessage());
    }
}
```

The example uses a **mock of the dependency** because the goal is purely controlling an I/O error. If you genuinely need to spy on an implementation whose method declares `read(...) throws IOException`, `doThrow(...).when(spy).read(...)` follows the exact same rule.

Do not attempt to configure `IOException` on a method **that does not declare** `IOException` or an allowed supertype: Mockito reports an invalid checked exception. When you hit that error, check the method's actual signature; do not arbitrarily swap in another exception if you intend to test the real contract.

Two common overloads:

```java
doThrow(new IllegalStateException("failed")).when(spy).reset();
doThrow(IllegalStateException.class).when(spy).reset();
```

The **instance** overload fits when you want to verify the exception message or payload. The **class** overload lets Mockito instantiate an exception of that type when called; do not rely on a specific generated stack trace or message.

## 7. Consecutive Stubbing: Changing Outcomes Across Calls

Sometimes a dependency fails after one success or returns a sequence of values. The `doReturn`/`doThrow` family lets you chain consecutive behaviors:

```java
Counter observed = spy(new Counter());

doReturn(10)
        .doReturn(20)
        .when(observed).increase();

assertEquals(10, observed.increase());
assertEquals(20, observed.increase());
assertEquals(20, observed.increase());
assertEquals(0, observed.value());
```

This is an **illustrative code snippet inside a `@Test`**, using `Counter`, `assertEquals`, `doReturn`, and `spy` from prior examples; it is not a standalone Java program. Mockito repeats the last behavior for subsequent calls once the listed sequence is exhausted.

You can combine them:

```java
Counter observed = spy(new Counter());

doReturn(10)
        .doThrow(new IllegalStateException("no more values"))
        .when(observed).increase();

assertEquals(10, observed.increase());
assertThrows(IllegalStateException.class, observed::increase);
```

Stub sequences are useful when **the sequence of responses from a dependency is part of the scenario under test** (e.g., API succeeds once then fails). Do not use them to simulate dozens of business branches on the service under test itself: if a test requires loading a complex mock script, that often signals dependencies have not been separated cleanly.

## 8. Stateful Spies: Why the Original Object and Spy Can Diverge

A common point of confusion in `Mockito.spy(realInstance)`: when spying on an ordinary object instance, Mockito **does not by default delegate every call back to the original instance**. Mockito builds the spy by copying the current state of the instance. If you keep a reference to the original object and mutate it later, do not expect the spy to observe those changes; and when calling real methods on the spy, do not expect the original object to update.

Example using `Counter` from Section 4:

```java
Counter original = new Counter();
Counter observed = spy(original);

original.increase();
original.increase();

assertEquals(2, original.value());
assertEquals(0, observed.value());

observed.increase();

assertEquals(1, observed.value());
assertEquals(2, original.value());
```

This is a **snippet inside a test**, not a standalone class. The results show that the two references hold separate counter states.

**Limitation to understand:** state may contain references to mutable objects, file handles, or other dependencies. Creating a spy from an object does not perform a **deep copy** of the entire object graph. If the original object and spy share a reference to a mutable collaborator, side effects on that collaborator can still be shared. Therefore, do not use a spy as a state-isolation or transaction mechanism.

If a tester checks `original.value()` after calling `observed.increase()` expecting an increment, they are observing the wrong object. Be explicit about whether the test invokes **the spy or the real instance**, and distinguish stubbing effects from object state divergence.

## 9. Practical Example: Replacing One I/O Operation in a Legacy Class While Keeping Real Rendering

A spy is most valuable when dealing with **a legacy class whose external dependency is not yet extracted**. Suppose a class both reads a template from disk and substitutes a customer name. We want to test the rendering logic without coupling the test to the filesystem.

**`src/main/java/com/example/testing/LegacyReportGenerator.java`**

```java
package com.example.testing;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class LegacyReportGenerator {

    public String loadTemplate(String filename) {
        try {
            return Files.readString(
                    Path.of(filename), StandardCharsets.UTF_8);
        } catch (IOException cause) {
            throw new UncheckedIOException(cause);
        }
    }

    public String render(String filename, String customer) {
        String template = loadTemplate(filename);
        return template.replace("{customer}", customer);
    }
}
```

**`src/test/java/com/example/testing/LegacyReportGeneratorTest.java`**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.spy;

class LegacyReportGeneratorTest {

    @Test
    void rendersCustomerWithoutOpeningFile() {
        LegacyReportGenerator observed =
                spy(new LegacyReportGenerator());

        doReturn("Hello, {customer}!")
                .when(observed).loadTemplate("welcome.txt");

        String result = observed.render("welcome.txt", "Mai");

        assertEquals("Hello, Mai!", result);
    }
}
```

**Mechanism:**

1. `render(...)` is **unstubbed**, so `LegacyReportGenerator`'s real code runs.
2. `render` invokes `loadTemplate("welcome.txt")` on the spy itself; the matching virtual call is intercepted by Mockito, returning the fake template.
3. The real `loadTemplate` does not open any file in this test.
4. The real `String.replace` executes and produces the business output to assert.

If the test instead wrote:

```java
// COUNTER-EXAMPLE: may open the real file right during stubbing.
when(observed.loadTemplate("welcome.txt"))
        .thenReturn("Hello, {customer}!");
```

`loadTemplate` could access the real file or throw `UncheckedIOException` during Arrange. This is a **classic scenario for `doReturn`**.

Condition for this technique to work reliably: the seam method `loadTemplate` must be interceptable by Mockito; do not treat private methods as stubbing seams. Self-invocation of a virtual method on a spy generally passes through Mockito's interception, but if the code uses private helpers, static/native methods, or calls restricted by the mock maker, expecting “only stub the helper” may fail. In that case, the sustainable path is extracting I/O into an explicit collaborator.

## 10. Better Design for New Code: Extract Collaborators and Mock Dependencies

`spy(LegacyReportGenerator)` helps when testing code that cannot be refactored yet, but it **should not become the default pattern for new code**. If a class mixes business logic and filesystem reads, extracting I/O behind an interface eliminates the need for partial mocking.

**`src/main/java/com/example/testing/TemplateSource.java`**

```java
package com.example.testing;

public interface TemplateSource {
    String read(String filename);
}
```

**`src/main/java/com/example/testing/ReportService.java`**

```java
package com.example.testing;

public final class ReportService {
    private final TemplateSource source;

    public ReportService(TemplateSource source) {
        this.source = source;
    }

    public String render(String filename, String customer) {
        return source.read(filename)
                .replace("{customer}", customer);
    }
}
```

**`src/test/java/com/example/testing/ReportServiceTest.java`**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class ReportServiceTest {

    @Test
    void rendersCustomerUsingTemplatePort() {
        TemplateSource source = mock(TemplateSource.class);
        when(source.read("welcome.txt"))
                .thenReturn("Hello, {customer}!");

        ReportService service = new ReportService(source);

        assertEquals("Hello, Mai!",
                service.render("welcome.txt", "Mai"));
    }
}
```

This is a pure unit test with **real logic** in `ReportService` and **I/O mocked at the dependency**. We do not care which private helpers `ReportService` calls internally; the test protects the output seen by the service's client. To verify the real file-reading adapter, write a dedicated test for the `TemplateSource` implementation using a controlled fixture.

In Spring Boot, dependency injection fits this approach naturally:

- Make `TemplateSource` an actual bean/adapter in the application.
- Have the service receive `TemplateSource` via constructor injection.
- Unit tests instantiate the service with `new ReportService(mockSource)`, avoiding `ApplicationContext` startup just to test string replacement.
- Integration tests start a context only when verifying Spring wiring, bean configuration, real I/O, or transactions.

**Rule of thumb:** if tests repeatedly need `doReturn` to intercept multiple methods **on the class under test itself**, ask whether a dependency or responsibility should be extracted from that class.

## 11. When to Use `@Spy` and MockitoExtension?

In unit tests, Mockito provides the `@Spy` annotation to declare a spy field, usually paired with JUnit Jupiter's `MockitoExtension` to process annotations. This is still a plain Java Mockito spy, **not automatically a Spring bean**.

Example based on `Counter.java`:

**`src/test/java/com/example/testing/AnnotatedCounterSpyTest.java`**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Spy;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.doReturn;

@ExtendWith(MockitoExtension.class)
class AnnotatedCounterSpyTest {

    @Spy
    private Counter observed = new Counter();

    @Test
    void annotationCreatesAUsableSpy() {
        doReturn(7).when(observed).increase();

        assertEquals(7, observed.increase());
        assertEquals(0, observed.value());
    }
}
```

If you create spies directly with `spy(new Counter())` as in earlier sections, you **do not need** `@ExtendWith(MockitoExtension.class)` just for `Mockito.spy` to work.

Common pitfalls with annotations:

- Writing `@Spy` without initializing annotations (`MockitoExtension`, `MockitoAnnotations.openMocks`, or an equivalent runner/mechanism) provides no guarantee the field is wrapped as a spy.
- Using `@Spy` on a test-managed field **does not replace beans** that Spring injects into other application classes.
- Combining `@InjectMocks` with spies can initialize objects/constructors unexpectedly; constructing dependencies and the SUT explicitly via constructors is more transparent.
- Spies still run real methods when unstubbed; the extension does not turn them into plain mocks.

## 12. Spies with a Spring Boot Context: Real Beans, AOP Proxies, and Annotation Versions

Sometimes you need to test a bean inside `ApplicationContext` because behavior depends on Spring configuration, bean wiring, or AOP. Here, a plain Java spy and a Spring Test spy bean must be clearly distinguished.

**In Spring Boot 3.3 branches**, tests support `@SpyBean` from `org.springframework.boot.test.mock.mockito` to replace/wrap a bean in the test context per Boot's mechanism. **Starting in Spring Framework 6.2**, `@MockitoSpyBean` exists in `org.springframework.test.context.bean.override.mockito`; newer Spring Boot releases adopt this mechanism. Do not import both annotations into the same class assuming they behave identically across all versions.

Directional syntax example **for Spring Boot 3.3 projects**, requiring a real context and bean to run:

```java
// Spring Boot 3.3 test configuration; this is not a standalone file.
@SpringBootTest
class OrderServiceContextTest {

    @SpyBean
    OrderService orderService;

    @Test
    void usesRealBeanUnlessStubbed() {
        // doReturn(...).when(orderService).someMethod(...);
        // Act via the real context-provided bean, then assert behavior.
    }
}
```

Requires importing `@SpringBootTest`, `@SpyBean`, `@Test`, and defining a real `OrderService` in the module. Do not add this snippet to a project where that bean does not exist. With Spring Framework 6.2+ using `@MockitoSpyBean`, check the docs for your exact version rather than copying old syntax blindly.

**Special notes on Spring AOP:**

- Beans with `@Transactional`, `@Cacheable`, `@Async`, or other advice may be wrapped in a **Spring proxy**, not just a standalone Mockito object.
- When spying on a bean, calls going through proxies/advice can behave differently from direct calls on the spy; stubbing at the wrong boundary can still trigger advice or fail to test what you think you are testing.
- With `@MockitoSpyBean`, Spring TestContext wraps the bean; if an AOP proxy is present, the proxy may still surround the spy target. Exact stubbing and verification behavior depends on the bean/proxy/advice and Spring version; check the corresponding documentation.
- **Self-invocation** in Spring AOP (one method calling another on the same instance) normally **bypasses the Spring proxy**. That is separate from Mockito spy interception. Do not use Mockito intercepting a self-call in a unit test to conclude that transaction or caching aspects apply to self-invocations in production.
- A test checking pure logic should not start a Spring context and spy on a bean just to call a few Java methods.

If your goal is to verify that transactions, caching, security, retries, or HTTP actually work through proxies, write an **integration test asserting observable outcomes** through the real boundary. Do not base all assertions on spy call counts.

## 13. Limitations of Spies: What `doReturn`/`doThrow` Cannot Fix

### 13.1. Only Stubbed Methods Are Replaced

After:

```java
doReturn("fake").when(observed).loadTemplate("welcome.txt");
```

other methods such as `render(...)` still run for real, and `loadTemplate("other.txt")` also runs for real if arguments do not match. When you truly want every filename to return a fake template, use a matcher:

```java
doReturn("Hello, {customer}!")
        .when(observed).loadTemplate(anyString());
```

This requires static import `org.mockito.ArgumentMatchers.anyString` in a test context. `anyString()` matches non-null `String` arguments in modern Mockito versions; if `null` is valid input, use `isNull` or `nullable` rather than assuming `anyString` always matches null.

**Warning:** overly broad matchers can hide bugs: if production passes the wrong template name, stubbing all filenames still keeps the test green. Prefer exact arguments whenever paths or keys are part of the contract.

### 13.2. Does Not Make Every Call Safe

A spy of a service may have uninitialized dependencies:

```java
// COUNTER-EXAMPLE: if real getInvoice() needs repository,
// spy(new InvoiceService(null)) can still throw NPE on real calls.
InvoiceService observed = spy(new InvoiceService(null));
```

This is an illustrative snippet; `InvoiceService` is not defined in this lesson's runnable files. `doReturn` avoids a dangerous call during setup, yet **unstubbed execution paths still hit the null dependency**. Instead, pass mocked/faked dependencies via constructor injection or initialize a valid object.

### 13.3. Private, Static, Final, and Mock Makers

- `private` methods are not normal stubbing/verification targets for Mockito spies. Test public behavior or extract responsibilities that genuinely need faking.
- `static` methods belong to the class; spying an instance **does not stub static methods**. Mockito provides a separate static-mocking API (`mockStatic`) returning `MockedStatic`, which should only be used when necessary and closed properly.
- For `final` methods/classes, **mocking support depends on the Mockito version and mock maker**. Mockito 5 with the inline mock maker supports many `final` cases by default, whereas other setups/versions may not. Avoid the outdated rule “Mockito can never mock final,” and also avoid assuming every native/JVM API can be safely intercepted.
- Constructors and native/special methods have additional constraints; a spy is not a universal tool for suppressing all side effects.

### 13.4. Spies Do Not Isolate Databases, Threads, or External Resources

If a real method on a spy opens a socket, starts a transaction, emits an event, or mutates singleton state, spying the object **does not block those side effects**. `doReturn` only prevents the stubbed method itself from executing during setup and when matching invocations occur. For stable tests, use boundary mocks/fakes, dedicated test databases, Testcontainers, or controlled environments as appropriate.

### 13.5. Over-Mocking Internal Methods Produces Low-Value Tests

For instance, testing a service by stubbing `calculateDiscount()`, `validate()`, and `mapResult()`, then asserting `process()` returns the expected value. The important methods were replaced, so the test may merely prove stubs are wired together. Refactoring a helper name breaks the test even when behavior is right. Keep core business logic real and fake only out-of-scope dependencies.

### 13.6. State and Concurrency

A spy whose real methods depend on mutable state or that is shared across multiple tests risks state leakage, especially under parallel execution. Do not share a mutable spy across test methods unnecessarily. Mockito stubbing/verification can misbehave if multiple threads touch the same mock/spy concurrently; avoid concurrent stubbing on the same object and assert side effects at deterministic boundaries.

## 14. Related APIs: `doNothing`, `doAnswer`, `doCallRealMethod`

Beyond `doReturn` and `doThrow`, the `do...` family offers other options:

| API | When to use | Notes |
|---|---|---|
| `doNothing().when(mock).voidMethod()` | Want to skip a void method | On a plain mock, void methods already do nothing by default; `doNothing` may be redundant |
| `doNothing().when(spy).voidMethod()` | Want to suppress a real void method's side effect | Intentional stub; do not use to mask business side effects |
| `doAnswer(answer).when(target).method(...)` | Need response logic based on arguments or to record data | Keep answers simple; avoid building a hard-to-read “fake subsystem” |
| `doCallRealMethod().when(mock).method(...)` | Need to run the real method for a specific call on a mock when valid | Mock object may lack initialized state because its constructor never ran |
| `doCallRealMethod().when(spy).method(...)` | Want to undo prior stubbing for one method and run real logic | Still produces real side effects; not a full spy reset |

Example of `doNothing` with `Counter`:

```java
Counter observed = spy(new Counter());
observed.increase();

doNothing().when(observed).reset();

observed.reset();
assertEquals(1, observed.value()); // Not reset because the void method was stubbed
```

This is an illustrative test snippet using static imports `doNothing`, `spy`, and `assertEquals`. On an unstubbed `Counter`, `reset()` sets `value` back to 0.

**Test-design question:** what am I proving by skipping `reset`? If the business goal is to prove reset works, `doNothing` removes the very logic under test. If the goal is to test another step where reset is an unrelated side effect in a legacy system, this stub can serve as a temporary seam.

## 15. Common Errors and Resolutions

| Symptom | Common cause | Resolution |
|---|---|---|
| `IndexOutOfBoundsException` right at `when(spy.get(0))` | Real `get(0)` ran on an empty list during Arrange | `doReturn("A").when(spy).get(0)` or test with a populated list |
| Repository/file/network called while “just stubbing” | `when(spy.method())` ran the real method | Use `doReturn`/`doThrow` on the method, or mock the external dependency |
| Exception from old stub when replacing a stub | `when(spy.method())` triggered the exception-throwing stub | Use `doReturn`/`doThrow` to replace the configuration |
| Compile error on `when(spy.voidMethod())` | `void` cannot be an argument to `when` | Use `doThrow`/`doNothing`/`doAnswer` for void methods |
| Mockito reports incompatible return type | `doReturn(Object)` bypasses Java compile-time generic checking | Verify the method's real return type; on plain mocks prefer `when().thenReturn()` |
| Mockito rejects checked exception | Exception incompatible with the method's `throws` clause | Pick an exception matching the contract and signature; never substitute arbitrarily |
| Test reads original object while spy updated state | `spy(real)` does not delegate everything back to the original instance | Interact consistently via the spy; check whether collaborator references are shared |
| Stub with specific argument does not take effect | Runtime call passes a different argument | Check actual input; use deliberate matchers without making them too broad |
| `@Spy` field is null / not a Mockito spy | `MockitoExtension`/`MockitoAnnotations` not activated | Initialize annotations properly or use `spy(new ...)` |
| Stubbing on a Spring bean behaves unexpectedly | Confused plain spy with proxy/version-specific bean annotation | Inspect Spring context, proxies, bean override, and AOP advice |
| `verify` on private/static/final method acts unexpectedly | Method/mock-maker limitations or verifying the wrong object | Check method kind, Mockito version/mock maker, and the real behavior to protect |
| Test fails after refactoring while API remains valid | Test depends on internal helper/call counts | Move assertions to public results, errors, or contract side effects |

Never “fix” a test by stubbing more and more internal methods just to make it pass. If a test keeps demanding broader spy stubbing, either the class's responsibilities are poorly separated or the test is verifying implementation rather than requirements.

## 16. When to Use a Spy vs. When to Avoid It?

Use these questions to decide:

1. **Do you genuinely need most of the object's real methods to run?** If not, mocking separate dependencies usually suffices.
2. **Is the method to replace an I/O operation or external collaborator that can be extracted behind an interface?** If so, prefer constructor injection for testability and maintainability.
3. **Does the object carry complex state or side effects on construction/real calls?** If so, spying makes tests unpredictable.
4. **Is the test protecting business behavior or merely verifying internal call chains?** Prefer return values, exceptions, persisted data, and specified side effects.
5. **Are real Spring proxies/transactions/async/caching required to prove behavior?** If so, use test context/integration tests asserting boundaries rather than plain Java spies.
6. **Does a spy provide a safe transitional seam when refactoring legacy code?** If so, document the temporary seam and plan to extract collaborators later.

**Good fit:** testing real rendering inside a legacy class while intercepting just the file-reading method; observing a meaningful public port; or temporarily replacing an expensive path while migrating an older design.

**Usually poor fit:** spying the business service itself and stubbing out validation/calculation; spying every Spring bean to feel “production-like”; spying real objects with hard-to-control side effects; spying just to count private/helper invocations when the final response is the contract.

## 17. Running the Examples with JUnit Jupiter, Mockito, and Spring Boot

In a Spring Boot 3.x/Java 17+ project using Gradle with version management via the Spring Boot plugin/BOM, you can use:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-test` in Spring Boot 3.x supplies JUnit Jupiter and Mockito, including `MockitoExtension` via its test integration. The unit examples in Sections 4–11 can use `testImplementation 'org.springframework.boot:spring-boot-starter-test'` without needing to start Spring. If the module already declares the starter/dependencies, do not add duplicates.

**Directories and run command:**

```text
src/main/java/com/example/testing/
    Counter.java
    LegacyReportGenerator.java
    TemplateSource.java
    ReportService.java
    TextStore.java
src/test/java/com/example/testing/
    CounterSpyTest.java
    CounterFailureTest.java
    TextStoreTest.java
    LegacyReportGeneratorTest.java
    ReportServiceTest.java
    AnnotatedCounterSpyTest.java
```

```bash
./gradlew test --tests com.example.testing.CounterSpyTest --tests com.example.testing.CounterFailureTest --tests com.example.testing.TextStoreTest --tests com.example.testing.LegacyReportGeneratorTest --tests com.example.testing.ReportServiceTest --tests com.example.testing.AnnotatedCounterSpyTest
```

On Windows PowerShell, use `.\gradlew.bat`; in multi-project Gradle builds, qualify the module task, e.g. `:your-module:test` when that module exists. Placed into matching filenames and packages on Java 17+, all classes run with the stated dependencies.

**Expected result:** every test method completes with no assertion failures; Gradle prints `BUILD SUCCESSFUL` in a properly configured environment. The JUnit tests in these examples produce no fixed business stdout. This is the **expected result based on the example code**, not a claim that tests were run on a specific workspace. **COUNTER-EXAMPLE** snippets and **non-standalone illustrations** are not extra files in the run list.

View reports at `build/reports/tests/test/index.html` or `build/test-results/test/` under the module's build directory. When encountering a stubbing error, check the stack trace during Arrange to see whether a real method executed before Act.

## 18. Practice Exercises

### Exercise A — Spotting a Bug Before the Act Step

Read the snippet:

```java
List<String> observed = spy(new ArrayList<>());
when(observed.get(0)).thenReturn("first");
assertEquals("first", observed.get(0));
```

1. Which expression executes real logic while stubbing?
2. Which exception is likely thrown, and why?
3. Fix it using `doReturn` and explain why the assertion then passes.

**Suggested answer:** `observed.get(0)` inside `when(...)` runs for real on the empty list and throws `IndexOutOfBoundsException`. Use `doReturn("first").when(observed).get(0)` to skip the real call during setup.

### Exercise B — Verifying State at Stubbing Time

Using the `Counter` class from this lesson, write two tests: one using `when(spy.increase()).thenReturn(10)` and one using `doReturn(10).when(spy).increase()`. Right after stubbing, assert state is **1** and **0** respectively. Then call `increase` and observe both return **10** without incrementing the counter further.

### Exercise C — Failures on void Methods

Using a spy of `Counter`, increment the counter to 1, then configure `doThrow(new IllegalStateException("blocked")).when(spy).reset()`. Verify:

- Stub setup does not call the real reset.
- Calling `reset` raises `IllegalStateException` caught by `assertThrows`.
- Counter value remains 1 after the exception.

Explain why `when(spy.reset()).thenThrow(...)` does not compile.

### Exercise D — Identifying a Better Design Solution

An `InvoiceService` class queries the database, calculates tax, and sends emails, and a test uses a spy to stub all three helpers. Propose dependency boundaries (repository, tax policy, email port). State which logic should run for real in unit tests, what can be mocked, and when integration tests with a real database are needed.

### Exercise E — Spring AOP and Spies

A `@Transactional` bean has two public methods; method A calls method B via `this.methodB()`. A unit-test spy intercepts the call to B. Can you conclude from that that Spring's transaction advice applies to B in production?

**Suggested answer:** No. Mockito interception and calls through a Spring AOP proxy are separate mechanisms; self-invocation in Spring AOP normally bypasses the proxy. Design an integration test across the real boundary if you want to verify transaction behavior.

## 19. Checklist Before Accepting a Spy Test

- [ ] I can state a concrete reason why a **spy** is needed instead of mocking a dependency or using a real object.
- [ ] I understand unstubbed methods run for real and can trigger side effects.
- [ ] On spies, I use `doReturn`/`doThrow` whenever the real method must not run during Arrange.
- [ ] For `void` methods, I never attempt to pass the call into `when(voidMethod())`.
- [ ] Stubbed exception types match the method signature, especially checked exceptions.
- [ ] I do not confuse the spy with the original object; state and collaborators are controlled.
- [ ] Stubs specify accurate arguments and are not so broad as to mask wrong behavior.
- [ ] I do not try to stub private methods or assume final/static/native methods behave identically across all mock makers.
- [ ] I do not treat Mockito spies as substitutes for Spring proxy/transaction/async behavior.
- [ ] I run the **real logic under test**; mocks/stubs apply only at justified boundaries.
- [ ] Assertions verify contract outcomes, errors, or side effects rather than helper call counts alone.
- [ ] Tests survive internal refactorings that preserve behavior; integration tests still guard essential real boundaries.

**Key takeaway:** `doReturn` and `doThrow` let you configure a spy **without accidentally executing real methods during stubbing**. They do not remove partial-mock limitations: shared state, I/O, AOP proxies, interception limits, and coupling to implementation details. For new code, prefer extracting dependencies and testing behavior through clear contracts; use spies intentionally, mainly for inspecting or safely migrating legacy code.

### References

- Mockito 5 Javadoc: https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/Mockito.html — sections *Spying on real objects*, *doReturn/doThrow family*.
- Spring Framework TestContext: https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html — `@MockitoSpyBean` and bean override/AOP behavior.
- Spring Boot 3.3 Javadoc: https://docs.spring.io/spring-boot/docs/3.3.0/api/org/springframework/boot/test/mock/mockito/SpyBean.html — `@SpyBean` annotation used in Boot 3.3.
