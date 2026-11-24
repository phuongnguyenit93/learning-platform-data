# Spying Real Beans, Side Effects, and Safe Stubbing

## 1. What is a spy, and why does "replacing a bean" not always mean a full mock?

In Spring Boot projects, you sometimes want to keep **most of a Spring bean's real behavior** while altering or observing **certain methods** during testing. For instance, a service performs real pricing, validation, and orchestration, and only a single gateway call or hard-to-control lookup is replaced with a fixed response. That is the use case for a **spy** (*partial mock*).

Mockito can spy on a Java object; Spring Boot Test 3.3.x provides `@SpyBean` to apply a spy to a bean inside `ApplicationContext`. A spy **differs critically from a default mock**: **unstubbed methods normally execute real code**. Consequently, a spy can mutate state, send network requests, write to databases, or throw real exceptions. Caution is required even during the **Arrange step**, not just during Act.

In this lesson:

- **Real behavior**: calls to the real bean's methods execute unless stubbed.
- **Stubbing**: configuring Mockito to return a value, throw an error, do nothing, or run a custom answer for a matching invocation.
- **Verification**: checking that a method was called the expected number of times with expected arguments; it does not invoke the method a second time.
- **Side effect**: writing to a DB, mutating counters, publishing events, making HTTP calls, updating caches, or any action beyond computing a return value.
- **Safe stubbing**: setting up stubs **without accidentally running real methods during configuration**, typically via `doReturn`/`doThrow`/`doAnswer`/`doNothing`.

Lesson goal: understand spy scope, create and use `@SpyBean` for the right version, see why `when(spy.method())` is dangerous, practice safe stubbing patterns, design assertions for side effects, and recognize when to replace a spy with a mock.

## 2. Comparing mocks, plain Java spies, and Spring bean spies

| Tool | Target object | Unstubbed call | Lives in Spring `ApplicationContext`? |
| --- | --- | --- | --- |
| `Mockito.mock(Foo.class)` | Mockito mock | Returns default value; no real code runs | No, unless manually registered in context |
| `@Mock` with `MockitoExtension` | Mockito mock initialized for test | Does not run real code by default | Does not replace Spring beans automatically |
| `Mockito.spy(realObject)` | Mockito spy around a Java object | Normally runs real code on the spy | Does not replace Spring beans automatically |
| `@Spy` with `MockitoExtension` | Mockito spy on a test field | Normally runs real code | Does not replace Spring beans automatically |
| `@MockBean` (Boot 3.3.x) | Mock registered/replaced in Spring Test context | Does not run real code by default | **Yes** |
| `@SpyBean` (Boot 3.3.x) | Spy applied to a Spring bean in Test context | **Runs real code unless stubbed** | **Yes** |

Choose based on the contract under test:

1. Want a **truly isolated unit test** away from gateways/DBs? Mock collaborators and instantiate the real service via constructor.
2. Want Spring to wire **real beans** and simply observe a few methods? `@SpyBean` may fit.
3. Want Spring to wire the real service while **preventing real payment/email/HTTP calls**? Usually use `@MockBean` for **side-effecting dependencies** and only spy where real logic must stay active.
4. Want to verify a call happened without altering behavior? A spy and `verify(...)` can help, provided verifying that interaction has real business value.

**Do not equate `@Spy` with `@SpyBean`.** If a test has `@Autowired CheckoutService service` and a `@Spy PriceCalculator calculator` field, `service` is unlikely to hold that spy. Spring may still inject a different real `PriceCalculator` from the context. `@SpyBean` operates at the Test context bean level, ensuring Spring-wired services use the spy the test observes.

## 3. Core behavior: spies still execute real methods

With a regular mock:

```java
Calculator calculator = mock(Calculator.class);
int result = calculator.calculate(100); // Default int -> 0
```

With a spy:

```java
Calculator calculator = spy(new Calculator());
int result = calculator.calculate(100); // Real calculate(...) runs
```

Both snippets are **illustrative syntax**; running them standalone requires defining `Calculator` and Mockito imports.

If `calculate(...)` queries a database, writes audit records, or mutates a variable, the spy performs those effects. Mockito **does not turn a real method into a side-effect-free function** merely by wrapping it in a spy.

### Three easily missed nuances

**(1) Stubbing can call real code:** on a spy, `when(spy.calculate(100)).thenReturn(110)` forces Java to evaluate `spy.calculate(100)` before passing the result to `when(...)`, so the real method can run **during Arrange**.

**(2) Stubs apply only to matching invocations:** if you stub `doReturn(110).when(spy).calculate(100)` yet the SUT calls `calculate(101)`, `calculate(101)` still executes for real.

**(3) Spies observe; they do not inherently isolate:** writing `verify(spy).calculate(100)` only confirms the invocation was recorded. It never erases or undoes prior side effects.

With Spring beans, there is one more catch: the context starts during test setup. Side effects in `@PostConstruct`, bean initialization, `ApplicationRunner`, or startup listeners during context refresh occur **before any test method can stub the spy**.

## 4. Golden rule: `when(...).thenReturn(...)` can be dangerous on spies

In Mockito, the two styles below usually behave identically **once stubbed**, yet **differ at setup time**:

```java
// Risky: spy.method() executes immediately during stubbing.
when(spy.method(arg)).thenReturn(fakeValue);

// Safer for spies: skips calling the real method when creating the stub.
doReturn(fakeValue).when(spy).method(arg);
```

Both lines are **syntax patterns** assuming `spy`, `method`, `arg`, and `fakeValue` are defined. Do not copy verbatim as a standalone Java class.

**Why do they differ?** In `when(spy.method(arg))`, Java must execute `spy.method(arg)` first to obtain the argument passed to `when(...)`. Mockito records the invocation and attaches the stubbing, but on a spy that initial call hits the real method by default. With `doReturn(value).when(spy).method(arg)`, Mockito enters stub-definition mode before the method call executes, skipping the real implementation during setup.

### Scenario 1: the real method throws an exception

Suppose `spy` wraps an empty list:

```java
List<String> spy = spy(new ArrayList<>());

// WRONG: empty list's get(0) throws IndexOutOfBoundsException
// right during Arrange; the test never finishes setting up the stub.
when(spy.get(0)).thenReturn("replacement");
```

Safe approach:

```java
List<String> spy = spy(new ArrayList<>());

doReturn("replacement").when(spy).get(0);

assertEquals("replacement", spy.get(0));
verify(spy).get(0);
```

These excerpts require imports for `List`, `ArrayList`, `Mockito.spy`, `Mockito.doReturn`, `Mockito.verify`, and `Assertions.assertEquals`. The full test example below demonstrates the same principle.

### Scenario 2: the real method has side effects

Suppose `Gateway.charge(...)` makes a real HTTP payment request when executed. Writing:

```java
when(gatewaySpy.charge("order-1")).thenReturn("tx-test");
```

**can charge money during test setup**. Even if the test subsequently PASSES, side effects were not prevented. When stubbing a gateway on a spy:

```java
doReturn("tx-test")
        .when(gatewaySpy)
        .charge("order-1");
```

Still, a **full mock** is usually far better if there is no reason to run any real gateway behavior. Safe stubbing only protects **the stubbed invocation**, not any other method on the spy that might hit external systems.

## 5. Choosing `doXxx` APIs for spies

| Need | Preferred API | Notes |
| --- | --- | --- |
| Returning method, supply fake value | `doReturn(value).when(spy).method(args)` | Skips real method during stubbing |
| Method should throw simulated exception | `doThrow(exception).when(spy).method(args)` | Also works for `void` methods |
| `void` method should skip real execution | `doNothing().when(spy).voidMethod(args)` | Useful when real code sends emails/events |
| Custom response logic | `doAnswer(answer).when(spy).method(args)` | Avoids real method unless answer explicitly calls it |
| Restore real implementation behavior | `doCallRealMethod().when(spy).method(args)` | Use deliberately; real method can still trigger side effects |
| Method returns sequential results | `doReturn(v1, v2).when(spy).method(args)` | Only stubs matching invocations; useful for retry/count tests |

On regular mocks, `when(mock.method()).thenReturn(...)` is more readable and standard. On **spies**, prefer `doReturn` / `doThrow` / `doAnswer` to avoid running real methods during setup.

### Tradeoff of `doReturn`

`doReturn` sacrifices some compile-time type checking compared to `when(...).thenReturn(...)` because its parameter type is `Object`. Certain return-type mismatches only surface at runtime. Keep stubbing simple and type-accurate rather than using `doReturn` mechanically on every mock.

### Do not overuse `doNothing`

On a **regular mock**, `void` methods already do nothing by default, so `doNothing()` is rarely needed. On a **spy**, unstubbed `void` methods run for real. If calling the real method sends emails or writes data, `doNothing().when(spy).send(...)` helps; however, if the entire gateway need not run for real, replacing it with a mock is safer and clearer.

## 6. Hands-on project: Spring Boot 3.3.x and Java 17+

The example below creates beans **genuinely inside a Spring context** alongside a small counter to observe side effects. It never touches networks, databases, or real payment APIs, letting you explore spies safely without external impact.

We use Spring Boot **3.3.5**, JDK 17+, and Gradle. Boot 3.3.x uses `org.springframework.boot.test.mock.mockito.SpyBean`. From Boot 3.4 onward, this API is deprecated in favor of Spring Framework's `@MockitoSpyBean`; do not switch imports before the project uses Framework 6.2+.

Directory tree:

```text
spy-bean-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/spylab/
│   ├── SpyLabApplication.java
│   ├── EffectRecorder.java
│   ├── QuoteCalculator.java
│   ├── ChargeGateway.java
│   ├── AuditPublisher.java
│   └── CheckoutService.java
└── src/test/java/com/example/spylab/
    ├── CheckoutSpyBeanTest.java
    └── PlainMockitoSpyTest.java
```

All Java files live in package `com.example.spylab`; placing tests in the same package allows `@SpringBootTest` to locate the `@SpringBootApplication` class automatically.

### 6.1. Gradle configuration

`settings.gradle`:

```groovy
rootProject.name = 'spy-bean-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

`spring-boot-starter-test` brings in Spring Boot Test, JUnit Jupiter, and Mockito. You do not need to add `MockitoExtension` to a `@SpringBootTest` class just to use `@SpyBean`.

If your Spring Boot project has its own BOM/plugins, keep your current dependency management instead of copying these example versions verbatim. Internet access to Maven Central is needed for the initial dependency download, along with a Gradle version compatible with Boot 3.3.x.

### 6.2. Application root

`src/main/java/com/example/spylab/SpyLabApplication.java`:

```java
package com.example.spylab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SpyLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SpyLabApplication.class, args);
    }
}
```

This project has no HTTP server because it uses only `spring-boot-starter`, without the web starter.

### 6.3. Side-effect recorder separate from the spies

`src/main/java/com/example/spylab/EffectRecorder.java`:

```java
package com.example.spylab;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class EffectRecorder {
    private final AtomicInteger quoteCalls = new AtomicInteger();
    private final AtomicInteger chargeCalls = new AtomicInteger();
    private final AtomicInteger auditCalls = new AtomicInteger();

    public void recordQuote() {
        quoteCalls.incrementAndGet();
    }

    public void recordCharge() {
        chargeCalls.incrementAndGet();
    }

    public void recordAudit() {
        auditCalls.incrementAndGet();
    }

    public int quoteCalls() {
        return quoteCalls.get();
    }

    public int chargeCalls() {
        return chargeCalls.get();
    }

    public int auditCalls() {
        return auditCalls.get();
    }

    public void reset() {
        quoteCalls.set(0);
        chargeCalls.set(0);
        auditCalls.set(0);
    }
}
```

The counter provides independent proof of **whether real method bodies executed**. `verify(spy).method(...)` only tells us Mockito saw a call, not whether execution was intercepted or ran for real. With this counter, we verify both *invocation* and *side effect*.

We avoid JVM-wide static counters; because Spring contexts can be cached, the test resets state in `@BeforeEach`. In real apps, persistent state similarly requires explicit cleanup or transaction handling rather than relying on Mockito resets.

### 6.4. Real pricing bean

`src/main/java/com/example/spylab/QuoteCalculator.java`:

```java
package com.example.spylab;

import org.springframework.stereotype.Component;

@Component
public class QuoteCalculator {
    private final EffectRecorder recorder;

    public QuoteCalculator(EffectRecorder recorder) {
        this.recorder = recorder;
    }

    public int totalCents(int subtotalCents) {
        recorder.recordQuote();

        if (subtotalCents < 0) {
            throw new IllegalArgumentException("negative subtotal");
        }

        return subtotalCents + subtotalCents / 10;
    }
}
```

For example, `totalCents(100)` returns `110` and increments `quoteCalls`. When safely stubbed with `doReturn(125)` for that argument, the counter does not increment because the real body never runs. That is precisely what we want to observe.

### 6.5. Real gateway and publisher, safe inside the example sandbox

`src/main/java/com/example/spylab/ChargeGateway.java`:

```java
package com.example.spylab;

import org.springframework.stereotype.Component;

@Component
public class ChargeGateway {
    private final EffectRecorder recorder;

    public ChargeGateway(EffectRecorder recorder) {
        this.recorder = recorder;
    }

    public String charge(int totalCents) {
        recorder.recordCharge();
        return "tx-live";
    }
}
```

`src/main/java/com/example/spylab/AuditPublisher.java`:

```java
package com.example.spylab;

import org.springframework.stereotype.Component;

@Component
public class AuditPublisher {
    private final EffectRecorder recorder;

    public AuditPublisher(EffectRecorder recorder) {
        this.recorder = recorder;
    }

    public void publish(String transactionId) {
        recorder.recordAudit();
    }
}
```

These are **real beans**, yet they only increment in-memory counters instead of calling payment processors or message brokers. In production, `charge(...)` or `publish(...)` can cause irreversible side effects—which is why spying real gateways demands careful thought.

### 6.6. Real business orchestration service

`src/main/java/com/example/spylab/CheckoutService.java`:

```java
package com.example.spylab;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final QuoteCalculator calculator;
    private final ChargeGateway gateway;
    private final AuditPublisher auditPublisher;

    public CheckoutService(
            QuoteCalculator calculator,
            ChargeGateway gateway,
            AuditPublisher auditPublisher) {
        this.calculator = calculator;
        this.gateway = gateway;
        this.auditPublisher = auditPublisher;
    }

    public Receipt checkout(int subtotalCents) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("negative subtotal");
        }

        int total = calculator.totalCents(subtotalCents);
        String transactionId = gateway.charge(total);
        auditPublisher.publish(transactionId);
        return new Receipt(total, transactionId);
    }

    public record Receipt(int totalCents, String transactionId) {
    }
}
```

Execution flow under test:

```text
CheckoutService.checkout(100)
    ├── QuoteCalculator.totalCents(100)  -> 110
    │       └── recorder.quoteCalls += 1
    ├── ChargeGateway.charge(110)        -> "tx-live"
    │       └── recorder.chargeCalls += 1
    ├── AuditPublisher.publish("tx-live")
    │       └── recorder.auditCalls += 1
    └── Receipt(110, "tx-live")
```

In a spy test, any **unstubbed** method still executes its real body, including calls to `EffectRecorder`.

## 7. Complete Spring Boot test suite: 6 key scenarios

Create `src/test/java/com/example/spylab/CheckoutSpyBeanTest.java`:

```java
package com.example.spylab;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.SpyBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

@SpringBootTest
class CheckoutSpyBeanTest {

    @Autowired
    CheckoutService checkoutService;

    @Autowired
    EffectRecorder recorder;

    @SpyBean
    QuoteCalculator calculator;

    @SpyBean
    ChargeGateway gateway;

    @SpyBean
    AuditPublisher auditPublisher;

    @BeforeEach
    void resetRecordedEffects() {
        recorder.reset();
    }

    @Test
    void unstubbedSpyCallsRealMethods() {
        CheckoutService.Receipt result =
                checkoutService.checkout(100);

        assertEquals(
                new CheckoutService.Receipt(110, "tx-live"),
                result
        );
        assertEquals(1, recorder.quoteCalls());
        assertEquals(1, recorder.chargeCalls());
        assertEquals(1, recorder.auditCalls());

        verify(calculator, times(1)).totalCents(100);
        verify(gateway, times(1)).charge(110);
        verify(auditPublisher, times(1)).publish("tx-live");

        InOrder order = inOrder(calculator, gateway, auditPublisher);
        order.verify(calculator).totalCents(100);
        order.verify(gateway).charge(110);
        order.verify(auditPublisher).publish("tx-live");
    }

    @Test
    void doReturnStubsGatewayWithoutChargingDuringSetup() {
        doReturn("tx-test").when(gateway).charge(110);

        // Stubbing does not call real ChargeGateway.charge.
        assertEquals(0, recorder.chargeCalls());

        CheckoutService.Receipt result =
                checkoutService.checkout(100);

        assertEquals(
                new CheckoutService.Receipt(110, "tx-test"),
                result
        );
        assertEquals(1, recorder.quoteCalls());
        assertEquals(0, recorder.chargeCalls());
        assertEquals(1, recorder.auditCalls());

        verify(gateway, times(1)).charge(110);
        verify(auditPublisher).publish("tx-test");
    }

    @Test
    void doReturnStubsCalculatorWithoutExecutingRealCalculation() {
        doReturn(125).when(calculator).totalCents(100);

        assertEquals(0, recorder.quoteCalls());

        CheckoutService.Receipt result =
                checkoutService.checkout(100);

        assertEquals(
                new CheckoutService.Receipt(125, "tx-live"),
                result
        );
        assertEquals(0, recorder.quoteCalls());
        assertEquals(1, recorder.chargeCalls());
        assertEquals(1, recorder.auditCalls());

        verify(calculator).totalCents(100);
        verify(gateway).charge(125);
    }

    @Test
    void doThrowSimulatesGatewayFailureWithoutRealCharge() {
        doThrow(new IllegalStateException("gateway unavailable"))
                .when(gateway).charge(110);

        assertEquals(0, recorder.chargeCalls());

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> checkoutService.checkout(100)
        );

        assertEquals("gateway unavailable", error.getMessage());
        assertEquals(1, recorder.quoteCalls());
        assertEquals(0, recorder.chargeCalls());
        assertEquals(0, recorder.auditCalls());

        verify(gateway).charge(110);
        verifyNoInteractions(auditPublisher);
    }

    @Test
    void doNothingBlocksRealVoidPublisher() {
        doNothing().when(auditPublisher).publish("tx-live");

        assertEquals(0, recorder.auditCalls());

        CheckoutService.Receipt result =
                checkoutService.checkout(100);

        assertEquals(
                new CheckoutService.Receipt(110, "tx-live"),
                result
        );
        assertEquals(1, recorder.quoteCalls());
        assertEquals(1, recorder.chargeCalls());
        assertEquals(0, recorder.auditCalls());

        verify(auditPublisher, times(1)).publish("tx-live");
    }

    @Test
    void invalidInputNeverTouchesAnySpiedBean() {
        assertThrows(
                IllegalArgumentException.class,
                () -> checkoutService.checkout(-1)
        );

        assertEquals(0, recorder.quoteCalls());
        assertEquals(0, recorder.chargeCalls());
        assertEquals(0, recorder.auditCalls());

        verifyNoInteractions(calculator, gateway, auditPublisher);
    }
}
```

Run just this class:

```bash
./gradlew test --tests "com.example.spylab.CheckoutSpyBeanTest"
```

Windows:

```powershell
.\gradlew.bat test --tests "com.example.spylab.CheckoutSpyBeanTest"
```

**Expected: 6 tests PASS** on Spring Boot 3.3.5 with the code above. The tests print no fixed stdout. Gradle displays each method as `PASSED` due to logging configuration; HTML reports appear in `build/reports/tests/test/index.html`. If no Gradle Wrapper is present, run `gradle test` with a compatible Gradle installation.

### Expected outcomes table for the 6 tests

| Test | Return/exception | quoteCalls | chargeCalls | auditCalls |
| --- | --- | ---: | ---: | ---: |
| `unstubbedSpyCallsRealMethods` | `Receipt(110, "tx-live")` | 1 | 1 | 1 |
| `doReturnStubsGatewayWithoutChargingDuringSetup` | `Receipt(110, "tx-test")` | 1 | 0 | 1 |
| `doReturnStubsCalculatorWithoutExecutingRealCalculation` | `Receipt(125, "tx-live")` | 0 | 1 | 1 |
| `doThrowSimulatesGatewayFailureWithoutRealCharge` | `IllegalStateException` | 1 | 0 | 0 |
| `doNothingBlocksRealVoidPublisher` | `Receipt(110, "tx-live")` | 1 | 1 | 0 |
| `invalidInputNeverTouchesAnySpiedBean` | `IllegalArgumentException` | 0 | 0 | 0 |

In the table, counters measure **how many times real method bodies executed**, whereas `verify(spy).method(...)` measures **invocations recorded on the spy**. For stubbed methods, `verify` still PASSES because the SUT invoked the spy, while the side-effect counter stays 0. Distinguishing those two measurements is the core takeaway.

### 7.1. Test 1: default runs real methods

`unstubbedSpyCallsRealMethods` sets up no stubs. Results confirm the beans inside the Spring context perform the calculation, call the gateway, and publish. A spy is not a safe mock. `InOrder` verifies the required sequence: calculate first, charge second, publish last. Only assert order when the business contract actually depends on ordering.

### 7.2. Test 2: `doReturn` prevents side effects in Arrange and Act

`doReturn("tx-test").when(gateway).charge(110)` does not increment `chargeCalls` during setup. When checkout calls `gateway.charge(110)`, Mockito returns `"tx-test"` without executing the real `ChargeGateway.charge`. Even so, `QuoteCalculator` and `AuditPublisher` still run for real because they were not stubbed.

That is why **safely stubbing one method does not make the whole flow safe** when other collaborators have side effects. In production, if an audit publisher sends real messages, it must be mocked/stubbed separately or isolated via test fixtures.

### 7.3. Test 3: skips real calculation while other beans still run

`doReturn(125).when(calculator).totalCents(100)` blocks the calculator's real body during both setup and matching invocations. Checkout receives 125 and calls the real gateway with 125. `verify(gateway).charge(125)` verifies the argument passed downstream; the counter proves the gateway still ran.

If the goal is testing "real quoting logic," **do not stub the calculator**, as doing so skips the exact logic under protection. Stubbing belongs on dependencies outside the test's scope.

### 7.4. Test 4: `doThrow` avoids real charge while testing the error branch

`doThrow(new IllegalStateException(...)).when(gateway).charge(110)` does not call the real charge during setup. When the SUT reaches the gateway, Mockito throws the exception; audit is skipped because the flow aborts. The test uses `assertThrows`, checks the message, `verify(gateway)`, and `verifyNoInteractions(auditPublisher)`.

Note that the sample code includes no transactions or compensation. In real payment systems, a network exception may represent an **unknown outcome** (unclear whether the charge succeeded) rather than "definitely not charged." Mockito only simulates responses; proving safe retries requires provider/idempotency-level tests.

### 7.5. Test 5: `void` methods need `doNothing` when spied

`AuditPublisher.publish(...)` returns `void`. On a spy, leaving it unstubbed runs the real method and increments `auditCalls`. `doNothing().when(auditPublisher).publish("tx-live")` still records the interaction while skipping the real body. The test proves both: `verify` PASSES and the counter stays at 0.

On a pure **mock**, `void` methods already do nothing by default. Do not add redundant stubbing when default behavior suffices.

### 7.6. Test 6: validation before side effects

For negative subtotals, `CheckoutService` throws before touching calculator, gateway, or publisher. `verifyNoInteractions(...)` protects the invariant that "invalid input must not touch dependencies." Try deliberately moving `calculator.totalCents(...)` ahead of validation: the test FAILS because the spy is invoked and the quote side effect is recorded.

## 8. Plain Java `Mockito.spy`: demonstrating setup-time errors

You can explore spy safety principles without loading a Spring context. The file below is a standalone JUnit test in the same Gradle project:

`src/test/java/com/example/spylab/PlainMockitoSpyTest.java`:

```java
package com.example.spylab;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class PlainMockitoSpyTest {

    @Test
    void callingRealMethodDuringWhenCanFailBeforeAct() {
        List<String> spy = spy(new ArrayList<>());

        assertThrows(
                IndexOutOfBoundsException.class,
                () -> when(spy.get(0)).thenReturn("fake")
        );

        doReturn("fake").when(spy).get(0);

        assertEquals("fake", spy.get(0));
        // The throwing real call before stubbing may also be recorded by Mockito;
        // do not verify times(1) by default on the same spy here.
    }

    @Test
    void unstubbedMethodsStillChangeSpyState() {
        List<String> original = new ArrayList<>();
        List<String> spy = spy(original);

        spy.add("real");
        assertEquals(List.of("real"), spy);

        // Mockito.spy(realObject) normally creates a spy
        // copying state at the time of creation.
        assertEquals(List.of(), original);
        verify(spy).add("real");
    }
}
```

Run:

```bash
./gradlew test --tests "com.example.spylab.PlainMockitoSpyTest"
```

**Expected: 2 tests PASS.** Test 1 **intentionally** uses `assertThrows` to prove `when(spy.get(0))` runs for real and throws on an empty list, then uses `doReturn` to stub safely. Test 2 shows a plain Java spy is not a "delegating wrapper" over the original reference: Mockito ordinarily creates a spy copying the object's state, so mutating the spy does not necessarily mutate the original instance.

**Example boundary:** object-copying in `Mockito.spy(realObject)` is Mockito behavior for plain Java spies. `@SpyBean` integrates with the **Spring bean lifecycle**, so never mechanically extrapolate that a replaced Spring bean and a spy coexist as two independent plain Java objects.

Run both test classes:

```bash
./gradlew test
```

**Expected: 8 tests PASS** (6 Spring Boot tests + 2 plain Java Mockito tests) with the exact source above. Note that this is an **expected outcome derived from the code**, not a claim of execution in a pre-existing local environment.

## 9. How does `@SpyBean` work on real Spring beans?

Spring Boot Test 3.3.x applies Mockito spies via Spring Boot's test infrastructure. Key points for users of the API:

1. `@SpringBootTest` builds an `ApplicationContext` for the test.
2. During context preparation, Mockito test infrastructure processes `@SpyBean` declarations.
3. Matching beans in the context are spied; the `@SpyBean` test field receives the reference for stubbing and verification.
4. Collaborators receiving that bean from Spring interact through the spy at runtime.
5. After each test, spies/mocks in Boot Test can be **reset** per `MockReset`. On Boot 3.3.x `@SpyBean`, the default is `MockReset.AFTER`.

That final step **only resets Mockito stubbings and invocation history**. It **does not roll back databases, clear emitted messages, reset counters in other beans, or alter singleton state**. That is why our example calls `recorder.reset()`—`EffectRecorder` is a Spring singleton holding state untouched by spy resets.

### `@SpyBean` by type or name

On a field:

```java
@SpyBean
QuoteCalculator calculator;
```

Spring Boot infers the bean type from the field. If **multiple beans share the type**, pick the right bean using `name` or a qualifier matching your configuration. For example:

```java
@SpyBean(name = "priorityQuoteCalculator")
QuoteCalculator calculator;
```

The second snippet **only illustrates syntax**, assuming the context defines a `priorityQuoteCalculator` bean. Do not add it to the sample project unless you define that bean. Picking the wrong bean leaves the SUT calling a different bean, causing `verify` to report no invocations.

For objects registered directly as dependencies rather than regular bean definitions, Spring Boot may create an additional spied bean instead of replacing the existing dependency; always confirm which collaborator the SUT actually injects.

### One spy per context, not a fresh object per test method

Regular beans have `singleton` scope in a Spring context. TestContext caches contexts across tests sharing equivalent configuration. Boot-managed spies are reset per test lifecycle, yet **the underlying bean and business state** may persist across tests. Do not treat `@SpyBean` as full test-state isolation.

Good practice: avoid unnecessary shared mutable state, isolate test data, and rely on transaction rollbacks or explicit cleanup when touching persistence. When `@DirtiesContext` is truly needed to evict a cached context, weigh its cost carefully since it can slow down test suites dramatically.

## 10. AOP proxies: `@Transactional`, `@Cacheable`, and spying complexities

In Spring, a bean may already be wrapped in an **AOP proxy** to enforce `@Transactional`, `@Cacheable`, `@Async`, security advice, or other cross-cutting concerns. When spying meets proxies, distinguish between:

- The proxy object visible to other beans.
- The target object holding business logic.
- Where Mockito intercepts an invocation.
- Whether Spring advice runs before/after the invocation.

Do not claim "stubbing the method eliminates all side effects" across **every advice layer**. Safe stubbing prevents running the real **method body** during setup on a properly targeted spy; proxies and advisors can still execute surrounding behavior or open transactions elsewhere.

### 10.1. `proxyTargetAware` in Spring Boot 3.3

`@SpyBean` provides `proxyTargetAware` so Mockito APIs like `verify(...)` operate on the target of an AOP-advised bean. If a test misses an invocation even though the app clearly called the Spring proxy, check:

- Did the SUT actually receive the spied bean?
- Is it a JDK dynamic proxy or a CGLIB/class-based proxy?
- Is Mockito verifying the proxy or the target?
- What value is `proxyTargetAware` set to?
- Was the method called externally through the proxy or via internal self-invocation?

When needed, Spring's `spring-test` provides `AopTestUtils.getTargetObject(...)` or `getUltimateTargetObject(...)` to unwrap the target for diagnostics. Use this sparingly while understanding nested proxies; never strip off proxies in routine tests and conclude transaction/cache/security advice is still verified.

### 10.2. Self-invocation differs from external invocation

Example:

```java
@Service
public class ReportService {
    public void generate() {
        refreshCache(); // internal call via this
    }

    @Cacheable("reports")
    public String refreshCache() {
        return "ok";
    }
}
```

This is an **illustrative snippet**, not part of the runnable project in Sections 6–8; it requires cache config and proper imports. The internal `refreshCache()` call can **bypass proxy advice** under proxy-based Spring AOP. Never assume a spy observes and stubs self-invocations identically to external calls through a proxy. If cache/transaction behavior is part of the contract, test across the real proxy boundary and verify state/cache/DB effects rather than verifying an internal method call.

### 10.3. Spying `@Transactional` does not undo external side effects

Suppose a real method starts a transaction, calls a payment gateway, and writes to the DB. A transaction rollback may revert DB changes under certain conditions, yet it **cannot undo a charge already sent to an external gateway**. Using a spy to test error paths requires isolating non-DB services with mocks/test doubles or a safe sandbox environment.

In particular, with `@SpringBootTest(webEnvironment = RANDOM_PORT)`, HTTP requests run on server threads; `@Transactional` on the test method does not automatically roll back server-side transactions. That is an integration test boundary, not a Mockito bug.

## 11. `@SpyBean` vs. `@MockBean` when dangerous side effects exist

Picture a payment system:

```text
CheckoutService (real)
  ├── FraudPolicy (real logic)
  ├── PaymentGateway (real HTTP charge)
  └── ReceiptPublisher (sends real messages)
```

You want to verify that the service runs the fraud check, charges once, and publishes a receipt on success. A **safer configuration** in Spring Boot 3.3.x is:

```java
@SpringBootTest
class CheckoutIntegrationStyleTest {
    @Autowired
    CheckoutService checkoutService;

    @SpyBean
    FraudPolicy fraudPolicy; // Keep real logic to observe it.

    @MockBean
    PaymentGateway paymentGateway; // Block real gateway.

    @MockBean
    ReceiptPublisher receiptPublisher; // Block real event publishing.

    @Test
    void chargesOnceAfterApproval() {
        // Stub gateway mock, call service, assert results,
        // and verify interactions per contract.
    }
}
```

This is an **illustrative architectural example** requiring real domain classes and imports. It is not runnable inside Section 6's project because `FraudPolicy`/`ReceiptPublisher` are undefined. Its point:

- **SUT and business policies** run real logic.
- **External side-effecting collaborators** are fully mocked.
- Verify only meaningful interactions, such as `verify(paymentGateway, times(1)).charge(...)`.
- When needing to override specific conditions of a real policy, use `doReturn(...)` on the spy for matching calls.

### Safety rules for choosing spy vs. mock

| Testing goal | Usually better choice |
| --- | --- |
| Unit testing `CheckoutService` logic | Real service + Mockito mock dependencies, no Spring loaded |
| Checking Spring bean wiring/DI | `@SpringBootTest` + test doubles for external gateways |
| Observing a real bean and overriding one controllable method | `@SpyBean` with intentional `doXxx` stubbing |
| Real payment/email/HTTP must NEVER happen on any branch | `@MockBean` or sandbox/fake guarding **every** path |
| Testing `@Transactional`/`@Cacheable`/AOP | Real Spring test asserting effects at boundaries rather than verifying methods alone |
| Testing controller HTTP status/JSON | `@WebMvcTest` + `MockMvc` + mocked collaborators |
| Testing a real DB-connected system | Spring integration test + Testcontainers/test DB with clear fixtures/cleanup |

Spies are particularly helpful when refactoring legacy code or preserving real logic while overriding one unstable spot. In well-tested designs, constructor injection plus mocked boundaries is easier to maintain.

## 12. Important limitations of safe stubbing

### 12.1. Arguments must match, or the real method still runs

Example:

```java
doReturn("tx-test").when(gateway).charge(110);

// Yet the SUT calls 115 because inputs or calculations changed.
checkoutService.checkout(105);
```

This **counter-example** builds on Section 6's project: `checkout(105)` yields total `115` (integer division), which fails to match the `charge(110)` stub, causing real `ChargeGateway.charge(115)` to run. With a real external gateway, a small argument mismatch can trigger severe side effects.

Do not hide this risk behind `anyInt()` if you want to verify the exact amount; use a **full mock** for the gateway instead. If a broad matcher on a spy is unavoidable, remember every other unstubbed method still executes for real.

### 12.2. Safe stubbing cannot stop effects during context initialization

If a bean has a `@PostConstruct` that sends data, test methods run **after** the context has already started. `doReturn(...).when(spy).method(...)` inside a test cannot turn back time to block `@PostConstruct`. Separate side effects from bean initialization, use test config/`@Profile`/`@ConditionalOn...` to exclude dangerous components, or replace dependencies before context creation.

### 12.3. Resetting a spy does not reset real state

In Boot 3.3.x, `@SpyBean` resets after each test method by default. That clears Mockito stubbing/invocations, **not DB rows, caches, files, or counters** mutated by real methods. A test passing alone yet failing in the suite usually indicates leftover state rather than Mockito forgetting to reset.

### 12.4. Verifying invocations does not prove side effects happened or were blocked

Two distinct checks:

```java
verify(gateway, times(1)).charge(110);
assertEquals(0, recorder.chargeCalls());
```

Both PASS in the `doReturn` test: the service called the spy once, yet the real `charge` body never ran. Thus, when the contract is "do not send real transactions," verifying call counts alone **is insufficient**; inspect external boundaries or use a full mock that truly isolates the gateway.

### 12.5. Stubbing one overload does not block another overload

If a class defines both `charge(int)` and `charge(Money)`, stubbing `charge(110)` leaves `charge(new Money(...))` untouched. The same holds for other method names or non-matching arguments.

### 12.6. Final, static, and private methods

Modern Mockito supports mocking many final/static cases depending on mock maker and version; **do not** blindly apply outdated advice claiming "final methods can never be spied." Still:

- Private methods are not public APIs to verify/stub directly like collaborators.
- Static mocking uses scoped APIs like `MockedStatic`, not standard `@SpyBean`.
- Spring proxies, final classes/methods, and bytecode generation can interact in subtle ways.
- Extract side-effecting collaborators behind injectable interfaces or beans instead of spying private/static behavior.

### 12.7. Async methods may not have finished when verifying

If `@Async` or a thread pool executes side effects after the SUT returns, calling `verify(...)` too early can fail intermittently. Await completion via `CompletableFuture`/latch/signal per contract before verifying. Never rely on `Thread.sleep(100)` as a reliable fix; tests become flaky and fail to guard against late side effects.

## 13. Combining with `@WebMvcTest`, `@DataJpaTest`, and Spring TestContext

`@SpyBean` operates on beans inside the **active test context**. A slice test only builds **part of the application**:

- `@WebMvcTest` loads MVC controllers, advice, and web-slice components; regular services/repositories are usually absent.
- `@DataJpaTest` focuses on JPA entities/repositories and persistence config, omitting unrelated gateways/services.
- `@SpringBootTest` builds a broader context per source configuration.

Placing `@SpyBean SomeService` into a slice where that bean does not exist can cause Boot 3.3's `@SpyBean` to register a new spied instance, letting the test run while altering the slice's scope. That does not prove production wiring works. In controller tests, mocking service dependencies is usually clearer. In repository tests, asserting DB state is more valuable than spying repositories and verifying query calls.

When facing missing-bean errors, recheck the **test goal** before adding a spy just to "make the context start." A spy can mask structural test issues if it does not represent a real bean within the tested scope.

## 14. Spring Boot 3.3 `@SpyBean` vs. Spring Framework 6.2 `@MockitoSpyBean`

Choose the API matching your **project's actual version**.

### Spring Boot 3.3.x

```java
import org.springframework.boot.test.mock.mockito.SpyBean;

@SpyBean
QuoteCalculator calculator;
```

This is a **Spring Boot Test** annotation. It integrates Mockito spies with the test `ApplicationContext` and supports default resets. This lesson's complete example uses this branch.

### Spring Boot 3.4+ with Spring Framework 6.2+

Spring Boot's `@SpyBean` and `@MockBean` are **deprecated as of 3.4** in favor of Spring Framework's APIs:

```java
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

@MockitoSpyBean
QuoteCalculator calculator;
```

This is **equivalent syntax for stacks with supporting Spring Framework versions**, not a valid import in Boot 3.3. Never rewrite `@SpyBean` to `@MockitoSpyBean` without upgrading the BOM.

**Important:** the two annotations are not 100% behaviorally identical. Spring Framework's `@MockitoSpyBean` uses the **WRAP bean override** mechanism and requires an existing matching bean, whereas Boot's `@SpyBean` could conditionally register a new spied bean when absent. Check qualifiers/names, scopes, targeted beans, and context caching during migration.

In modern Spring Framework, `@MockitoBean` replaces a bean with a mock while `@MockitoSpyBean` wraps a real bean in a spy. Never switch casually between them, because *running real methods* carries real side-effect risk.

## 15. Common failure symptoms and diagnostics

| Symptom | Likely cause | How to handle |
| --- | --- | --- |
| DB written or email sent during stubbing | `when(spy.method())` ran the real method | Switch to `doReturn`/`doThrow`/`doNothing` or mock the dependency |
| `IndexOutOfBoundsException` before Act | Spy invoked real getter on empty list | `doReturn(...).when(spy).get(0)` |
| `verify(spy)` reports "Wanted but not invoked" | SUT uses another bean/instance; proxy/target mismatch | Check injection, bean name, and AOP proxy |
| Test PASSES alone, FAILS in suite | Real state unreset; context cache reused | Clean up fixtures, reset state, isolate test data |
| Real bean still makes HTTP calls despite stubbed method | Different method/argument called, or side effect in another bean | Mock the full boundary; verify arguments and all paths |
| Real service missing in `@WebMvcTest` | Slice does not load regular services | Mock collaborator or import intentional config |
| `NotAMockException` during verify | Verifying real object/wrong proxy, or spy not injected | Verify Mockito spy and Spring proxy target |
| `UnnecessaryStubbingException` | Stub configured but unused | Remove unused stub or adjust test case |
| AOP cache/transaction behaves unexpectedly | Spy/proxy/self-invocation and advice shift boundaries | Test through public proxy and assert boundary effects |
| Stub misses second invocation | Code passes different arguments, calls another overload, or spy reset | Inspect actual invocations and contract matchers |
| Cannot find `@MockitoSpyBean` in Boot 3.3 | Annotation belongs to newer Spring Framework | Use `@SpyBean` for your BOM or upgrade stack intentionally |

### Ordered debugging strategy

1. **Read the first meaningful stack trace**. Did it fail during context refresh, Arrange/stubbing, Act, or Assert/Verify?
2. **Identify the actual instance in use**: did the service get a Spring bean or an object created via `new`? Do type and name match the spied bean?
3. **Check the stubbing call**: did it use `when(spy.realMethod())` or `doReturn(...).when(spy).realMethod()`?
4. **Check matchers**: did the actual invocation match the stubbed arguments? Otherwise the spy may run for real.
5. **Audit all side-effecting dependencies**: block at payment/network/email/DB boundaries so tests stay safe.
6. **Inspect post-test state**: Mockito reset is not business state reset.
7. **If Spring AOP is present**, distinguish proxy, target, self-invocation, and advice.
8. **Minimize test scope**: for pure Java logic, mock collaborators and skip full contexts.
9. **Verify with both assertions and verifications**: are outputs/exceptions right, and are side effects/call counts valid?
10. **Rerun the related test group** to uncover context caching and state leakage.

## 16. Designing tests to avoid brittleness

For business logic, favor asserting observable outputs and state; verify calls **when they are part of the contract**, such as "never charge twice" or "do not publish events when the gateway fails."

**Brittle test:**

```java
verify(service).calculateTax();
verify(service).normalizeName();
verify(service).buildRequest();
verify(service).save();
verifyNoMoreInteractions(service);
```

This is an **illustrative counter-example**, not standalone code with defined classes/methods. It locks down implementation details: refactoring a helper method breaks the test even when business behavior is unchanged.

**Behavior-focused test:**

```java
CheckoutService.Receipt result = checkoutService.checkout(100);

assertEquals(110, result.totalCents());
verify(gateway, times(1)).charge(110);
```

This excerpt comes from the context test in Section 7, assuming beans exist and are otherwise unstubbed. If "charge exactly once" is a business rule, `times(1)` protects it. If the goal is "never trigger a real charge," assert counters/external fake state or replace the gateway with a mock, since `verify` alone does not prevent charging.

Avoid spying the **system under test itself** whenever you can call the real SUT and mock its collaborators. Spying the SUT turns tests into internal call-graph checks, whereas tests should protect external outputs and side effects.

## 17. Checklist before spying a real bean

Before accepting a test with `@SpyBean`, answer:

1. **Why is a spy needed?** If fake returns and call verification are enough, would a mock suffice?
2. **Are there dangerous side effects in the real method or its collaborators?** DB, HTTP, email, queues, payments?
3. **Does stubbing use `doXxx`?** Avoid `when(spy.method())` running real code during Arrange.
4. **If arguments fail to match, what happens?** The real method can execute.
5. **Does the SUT receive the exact spied bean?** Check type, qualifier, name, and Spring context.
6. **Are AOP proxies involved?** `@Transactional`, `@Cacheable`, `@Async`, security advice?
7. **Does the bean have `@PostConstruct` or init side effects?** Test stubs may arrive too late.
8. **Is real state properly cleaned up/reset?** Mockito reset is insufficient.
9. **Have all threads/async tasks finished before verification?**
10. **Are outputs/state asserted alongside interaction verification?**
11. **Are verified call counts, arguments, and ordering genuinely part of the contract?**
12. **Which API does the stack use?** Boot 3.3 `@SpyBean` or Framework 6.2+ `@MockitoSpyBean`?

## 18. Controlled hands-on exercises

Using the complete code from Sections 6–8:

1. Run the full test suite and confirm **8 tests PASS**.
2. In `doReturnStubsGatewayWithoutChargingDuringSetup`, temporarily change the stub line to `when(gateway.charge(110)).thenReturn("tx-test")` **only in the sandbox project**; predict `recorder.chargeCalls()` incrementing before `checkoutService.checkout(...)` is even called. Restore `doReturn` after observing.
3. Keep `doReturn("tx-test").when(gateway).charge(110)` yet invoke checkout with a subtotal producing a total other than 110; prove real `charge(...)` still runs when arguments miss.
4. In `doNothingBlocksRealVoidPublisher`, remove `doNothing` and observe how `auditCalls` shifts from 0 to 1.
5. In `doThrowSimulatesGatewayFailureWithoutRealCharge`, verify that no audit was published even though the real calculator ran.
6. Switch the gateway to `@MockBean` with an appropriate stub; explain why a mock is safer when an external gateway carries dangerous side effects.
7. Suppose `QuoteCalculator` is annotated `@Cacheable`; analyze why cache behavior must be tested across the Spring proxy rather than merely verifying a single internal call.
8. Explain why `@SpyBean`'s Mockito reset does not replace `recorder.reset()` in `@BeforeEach`.

Exercises 2 and 3 intentionally demonstrate **risks** on an in-memory sandbox; never experiment against live payment gateways, email servers, or production databases.

## 19. References by version

- [Mockito — Spying on real objects and doReturn/doThrow](https://javadoc.io/doc/org.mockito/mockito-core/5.15.2/org.mockito/org/mockito/Mockito.html): explains real methods on spies and stubbing differences.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): mocks/spies in `ApplicationContext`, context cache impact, AOP proxies, and test slices.
- [Spring Boot 3.3 — SpyBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/mock/mockito/SpyBean.html): `name`, `classes`, `reset`, `proxyTargetAware`.
- [Spring Framework — @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): modern TestContext bean override/wrap mechanisms.
- [Spring Boot 3.4 Release Notes — Deprecations](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes): API migration from `@SpyBean` to `@MockitoSpyBean`.

## 20. Summary

**A spy preserves real behavior by default.** When applying `@SpyBean` to a Spring bean in Boot 3.3.x, unstubbed methods execute real business logic and trigger side effects. On spies, `when(spy.method())` can run the real method during test setup; therefore, **`doReturn`, `doThrow`, `doNothing`, and `doAnswer` are safer stubbing choices** for calls you need to intercept.

Even with proper stubs, other methods or mismatched invocations can still run for real. Check **return values, actual calls, and side effects** together, manage state across tests, distinguish beans from AOP proxies, and use full mocks for dependencies that tests must never invoke for real. Spies are valuable when applied purposefully—not as a default substitute for isolated test design.
