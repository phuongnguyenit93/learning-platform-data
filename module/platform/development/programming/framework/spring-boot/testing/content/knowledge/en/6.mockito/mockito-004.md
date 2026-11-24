# Mockito ArgumentMatchers, `eq`, and the Consistent Matcher Rule

## 1. Lesson Goals

When testing a service in Spring Boot, we often use Mockito to simulate a repository, HTTP client, payment gateway, or other adapter. A stub statement must answer **for which arguments the mock returns the configured result**; a verify statement must answer **whether a call occurred with arguments satisfying a condition**. `ArgumentMatchers` gives us the vocabulary to express those conditions.

For example, when a service sends a charge command containing an order ID, amount, and note:

- The order ID must **exactly equal** `ORD-42`.
- The amount can be **any `long` value** when we only need to isolate the gateway's return value.
- The note can be **`null`** if the contract allows it.
- During business verification, the actual amount may need to be **exactly 120,000 VND**, rather than just “any amount.”

Mockito provides matchers such as `eq("ORD-42")`, `anyLong()`, `nullable(String.class)`, `isNull()`, `argThat(...)`… yet they are not ordinary Java values that can be placed anywhere. Mockito records matchers per invocation, and there is one crucial rule: **if you use a matcher for one argument in a stubbed or verified call, every argument of that call must be provided via matchers**. Violating this is a common cause of `InvalidUseOfMatchersException`.

After this lesson, you will be able to:

1. Choose properly between literals, `eq`, `anyX`, `isNull`, `nullable`, and custom matchers.
2. Use matchers consistently in `when(...).thenReturn(...)`, `verify(...)`, and `doReturn(...).when(...)`.
3. Understand why `eq(...)` is **not** the same as passing a real argument, even though it checks the same equality condition.
4. Distinguish equality via `equals` from reference identity via `same`.
5. Write meaningful tests with Java 17, JUnit Jupiter, and Mockito while avoiding overly broad stubs that let bugs slip through.
6. Read mismatch errors, invalid matcher usage errors, and strict stubbing errors, and choose the right fix.

## 2. What Problem Do Matchers Solve?

Suppose a gateway interface has the signature:

```java
String charge(String orderId, long amount, String note);
```

To stub an exact call, Mockito allows passing literals:

```java
when(gateway.charge("ORD-42", 120_000L, "gift"))
        .thenReturn("TX-99");
```

The statement above applies only to equivalent arguments under Mockito's standard comparison. If the test wants to fix the order ID while ignoring the amount and note, it can use matchers:

```java
when(gateway.charge(
        eq("ORD-42"),
        anyLong(),
        nullable(String.class)
)).thenReturn("TX-99");
```

Here all three arguments are matchers:

- `eq("ORD-42")` matches the exact string value.
- `anyLong()` matches any `long` (and non-null `Long` for wrapper parameters).
- `nullable(String.class)` matches a `String` or `null`.

Mockito uses the same mechanism during verification:

```java
verify(gateway).charge(
        eq("ORD-42"),
        eq(120_000L),
        isNull()
);
```

An easy summary:

| Action | Example | Meaning |
| --- | --- | --- |
| Stubbing | `when(mock.find(...)).thenReturn(value)` | If a real call matches the matchers, supply the configured answer |
| Verification | `verify(mock).save(...)` | Assert that a call occurred satisfying the matchers |
| Literal | `verify(mock).send("A", 1)` | Exact values `"A"` and `1`, no matchers needed |
| `eq` | `verify(mock).send(eq("A"), anyInt())` | Keep an equality check inside a call that uses matchers |
| `argThat` | `verify(mock).send(eq("A"), intThat(n -> n > 0))` | Apply a custom predicate check |

Matchers **do not execute production calls**. Stubs define mock behavior and `verify` inspects recorded interaction history on the mock; the service's real logic must still be exercised in the Act step.

## 3. Mandatory Rule: If You Use Matchers, Use Them for **Every Argument**

This is the core of the lesson. Consider the interface:

```java
interface BillingPort {
    String charge(String orderId, long amount, String note);
}
```

### 3.1. Two Valid Ways

**Approach A — use no matchers at all:**

```java
when(port.charge("ORD-42", 120_000L, "gift"))
        .thenReturn("TX-1");

verify(port).charge("ORD-42", 120_000L, "gift");
```

**Approach B — all arguments are matchers:**

```java
when(port.charge(
        eq("ORD-42"),
        anyLong(),
        anyString()
)).thenReturn("TX-1");

verify(port).charge(
        eq("ORD-42"),
        eq(120_000L),
        eq("gift")
);
```

`eq` is also a matcher. When you want to keep one specific argument alongside `anyLong()`, wrap that value in `eq(...)`. The matchers do not all have to be the same kind; simply ensure **every argument position** is represented by a matcher.

### 3.2. Two Invalid Ways

```java
// WRONG: one literal mixed with two matchers in the same call.
when(port.charge("ORD-42", anyLong(), anyString()))
        .thenReturn("TX-1");

// WRONG: one matcher mixed with literals for the remaining arguments.
verify(port).charge(eq("ORD-42"), 120_000L, "gift");
```

The lines above are **intentional error examples** and must not be copied into passing tests. When Mockito records a number of matchers that does not match the argument count, it can throw `org.mockito.exceptions.misusing.InvalidUseOfMatchersException`, showing expected vs. recorded matchers.

The fix:

```java
when(port.charge(eq("ORD-42"), anyLong(), anyString()))
        .thenReturn("TX-1");

verify(port).charge(
        eq("ORD-42"),
        eq(120_000L),
        eq("gift")
);
```

**Key distinction:** The consistency rule applies within **a single method call** being stubbed or verified; it does not force you to use matchers in every call throughout the test. One test can use literals in its first call and matchers in its second call, as long as each call is internally consistent.

### 3.3. Why Does Mockito Require This?

Functions like `any()`, `eq()`, and `argThat()` record matching conditions in Mockito's internal matcher stack and then return a **dummy value** so Java can compile the method call. Depending on the type, that return value may be `null`, `0`, `false`, or another placeholder. The returned Java value **is not the matcher itself**.

Because matchers are recorded separately from the Java arguments passed to the mock method, Mockito must match the number of recorded matchers against the number of parameters in that call. Mixing matchers and literals leaves no uniform list of matchers to interpret the invocation.

Important consequences:

- Do not store `String order = eq("ORD-42")` and use `order` as production data.
- Do not use `anyLong()` to generate sample amounts or pass it into a real service.
- Do not invoke matchers outside a Mockito stubbing/verification context; stray matchers remain on the internal stack and can break a subsequent Mockito call.
- Do not expect `eq("A")` to return the string `"A"`. It is an expression for Mockito, not an identity function.

## 4. `eq(...)`: Matching by Value, Not Reference

`ArgumentMatchers.eq(expected)` expresses the condition that the actual argument **equals** `expected`. For objects, equivalence uses the type's `equals` semantics; for primitives, it compares values.

Example:

```java
verify(port).charge(
        eq("ORD-42"),
        eq(120_000L),
        eq("gift")
);
```

If all three arguments are concrete values, the following is usually easier to read and equally valid:

```java
verify(port).charge("ORD-42", 120_000L, "gift");
```

So **when do you actually need `eq`?** When at least one other argument in **the same call** is checked using a matcher:

```java
verify(port).charge(
        eq("ORD-42"),   // Specific.
        anyLong(),      // Flexible.
        isNull()        // Must be null.
);
```

### 4.1. `eq` vs. `same`

Consider a Java 17 record:

```java
record Address(String city, String street) {}

Address expected = new Address("HCM", "Le Loi");
Address actual = new Address("HCM", "Le Loi");
```

`expected` and `actual` are two distinct instances, but the record provides component-based `equals`:

- `eq(expected)` matches `actual` because the two records are equal by value.
- `same(expected)` matches **only the exact same instance**.
- `refEq(expected)` can perform reflection-based field comparison when `equals` is missing, but should be used deliberately; it is usually better to design value objects with proper `equals/hashCode`.

In most service tests, contracts care about **data transferred across a boundary**, so `eq` or field assertions fit better than `same`. Checking reference identity should be reserved for contracts that explicitly require passing the exact same instance, such as a cache or identity-sensitive object manager.

### 4.2. Comparing Complex Objects

If `PaymentRequest` is a record with `orderId`, `amount`, and `currency`, you can verify:

```java
verify(paymentPort).pay(
        eq(new PaymentRequest("ORD-42", 120_000L, "VND"))
);
```

This is an **illustrative snippet** requiring the project's `paymentPort` and `PaymentRequest` record. It fits when **every field of the object** is part of the contract.

If the request contains timestamps, generated IDs, or unstable metadata, do not force `eq` on the entire object only to end up fixing the test constantly. Use `argThat` to select key fields or `ArgumentCaptor` to inspect individual fields.

**Do not confuse `eq` with `assertEquals`:** `eq` declares an argument condition for Mockito; JUnit's `assertEquals` verifies an observed value.

## 5. Table of Common Matchers and `null` Semantics

The difference between `any()` and typed matchers is a common source of false failures. The semantics below match Mockito 5.x APIs and fit Java 17.

| Matcher | Matching condition | Matches `null`? | When to use |
| --- | --- | --- | --- |
| `eq("A")` | Value equals `"A"` | No, unless expected is `null` | Pin a specific value in a call using matchers |
| `eq(5L)` | `long` value equals 5 | N/A for primitives | Exact number must match |
| `any()` | Any reference argument; note varargs | **Yes** | Don't care about the object, including `null` |
| `any(String.class)` | Instance of `String` | **No** | Any non-null `String` |
| `anyString()` | Non-null `String` | **No** | Any string, including empty string |
| `anyInt()` / `anyLong()` | Primitive or non-null wrapper of that type | **No** for wrappers | Any number of the right type |
| `anyList()` / `anyMap()` | Non-null collection/map of the right type | **No** | Don't care about elements, only that container is non-null |
| `isNull()` | Strictly `null` | **Yes, only null** | Argument must be null |
| `notNull()` | Any non-null argument | **No** | Contract requires a value |
| `nullable(String.class)` | `String` or `null` | **Yes** | Parameter may be omitted/null |
| `startsWith("PRE-")` | String starting with prefix | No | IDs with a prefix |
| `contains("x")` | String containing substring | No | Metadata/descriptions containing a token |
| `argThat(predicate)` | Custom condition | Depends on predicate | Check specific fields or patterns |
| `same(object)` | Same reference as sample object | Can compare null reference, though `isNull` is clearer | Contract about instance identity |

**Choosing by intent:**

- Want **any non-null string**: `anyString()`.
- Want **a string or null**: `nullable(String.class)` (clearer intent than `any()`).
- Want **only null**: `isNull()`.
- Want **exact string "ORD-42"**: `eq("ORD-42")` when combining matchers, or a literal otherwise.
- Want **a positive integer**: `intThat(value -> value > 0)`; `anyInt()` also matches 0 and negatives.
- Want **a collection with specific elements**: `eq(List.of(...))` or a content-checking matcher, not `anyList()` when contents matter.

**Warning:** untyped `any()` can match `null` for ordinary object arguments, but as of Mockito 5 it **no longer automatically matches an entire varargs group**. For varargs methods, see Section 11 and explicitly choose whether to match an element or the whole array.

## 6. Complete Runnable Example with Java 17 + JUnit Jupiter + Mockito

This example uses a real service and a mocked gateway interface without a Spring context. It demonstrates matchers in stubbing, verification, `null` handling, and business outcomes.

### 6.1. Production File

**`src/main/java/example/CheckoutService.java`:**

```java
package example;

import java.util.Objects;

public final class CheckoutService {
    public interface PaymentPort {
        String charge(String orderId, long amountInVnd, String note);
    }

    public record Receipt(String orderId, String transactionId) {}

    private final PaymentPort paymentPort;

    public CheckoutService(PaymentPort paymentPort) {
        this.paymentPort = Objects.requireNonNull(paymentPort);
    }

    public Receipt checkout(String orderId, long amountInVnd, String note) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }
        if (amountInVnd <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        String transactionId =
                paymentPort.charge(orderId, amountInVnd, note);

        return new Receipt(orderId, transactionId);
    }
}
```

The class uses a Java 17 record and manual constructor injection. No Spring annotations are needed because the goal is to study matchers independently of the framework.

### 6.2. Complete Test File

**`src/test/java/example/CheckoutServiceTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.ArgumentMatchers.longThat;
import static org.mockito.ArgumentMatchers.nullable;
import static org.mockito.ArgumentMatchers.startsWith;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class CheckoutServiceTest {
    @Test
    void allowsNullableNoteWhileKeepingOrderIdExact() {
        var gateway = mock(CheckoutService.PaymentPort.class);
        when(gateway.charge(
                eq("ORD-42"),
                anyLong(),
                nullable(String.class)
        )).thenReturn("TX-9");

        var service = new CheckoutService(gateway);
        CheckoutService.Receipt receipt =
                service.checkout("ORD-42", 120_000L, null);

        assertEquals("ORD-42", receipt.orderId());
        assertEquals("TX-9", receipt.transactionId());
        verify(gateway).charge(
                eq("ORD-42"),
                eq(120_000L),
                isNull()
        );
    }

    @Test
    void usesExactLiteralArgumentsWhenNoMatcherIsNeeded() {
        var gateway = mock(CheckoutService.PaymentPort.class);
        when(gateway.charge(
                "ORD-43", 50_000L, "gift"
        )).thenReturn("TX-10");

        var service = new CheckoutService(gateway);
        var receipt = service.checkout(
                "ORD-43", 50_000L, "gift");

        assertEquals("TX-10", receipt.transactionId());
        verify(gateway).charge("ORD-43", 50_000L, "gift");
    }

    @Test
    void verifiesBusinessConstraintsWithCustomMatchers() {
        var gateway = mock(CheckoutService.PaymentPort.class);
        when(gateway.charge(
                eq("ORD-44"),
                anyLong(),
                startsWith("campaign-")
        )).thenReturn("TX-11");

        var service = new CheckoutService(gateway);
        var receipt = service.checkout(
                "ORD-44", 80_000L, "campaign-2026");

        assertEquals("TX-11", receipt.transactionId());
        verify(gateway).charge(
                eq("ORD-44"),
                longThat(value -> value > 0),
                argThat(note -> note != null
                        && note.endsWith("-2026"))
        );
    }

    @Test
    void typedStringMatcherDoesNotAcceptNull() {
        var gateway = mock(CheckoutService.PaymentPort.class);
        when(gateway.charge(
                eq("ORD-45"),
                anyLong(),
                anyString()
        )).thenReturn("TX-non-null");

        assertNull(gateway.charge("ORD-45", 100L, null));
        assertEquals(
                "TX-non-null",
                gateway.charge("ORD-45", 100L, "ok")
        );
    }

    @Test
    void rejectsInvalidAmountBeforeCallingGateway() {
        var gateway = mock(CheckoutService.PaymentPort.class);
        var service = new CheckoutService(gateway);

        assertThrows(IllegalArgumentException.class,
                () -> service.checkout("ORD-46", 0L, "gift"));
        verifyNoInteractions(gateway);
    }
}
```

**Code QA note:** These tests use `mock(...)` directly, so neither `MockitoExtension` nor Spring is required to initialize mocks. Imports use Mockito 5.x/JUnit Jupiter APIs; `longThat` handles primitive `long`. `CheckoutService.java` and the test file have packages/classes matching their paths; the intentional error snippets from Section 3 are **not** in this test file.

### 6.3. Dependencies and How to Run

In a Spring Boot 3.x project already managing versions via the Spring Boot BOM, Gradle Groovy DSL usually declares:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is an addition to an **existing build**, not a standalone `build.gradle`: the project also needs the `java` plugin, repositories, and the BOM, Spring Boot plugin, or equivalent dependency management. With Maven starter test:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

If using JUnit and Mockito **without Spring Boot**, explicitly declare `junit-jupiter`, `mockito-core`, and the JUnit Platform launcher/engine according to a compatible BOM or versions for that build.

In the project directory with Gradle Wrapper:

```bash
./gradlew test --tests example.CheckoutServiceTest
```

On Windows:

```powershell
.\gradlew.bat test --tests example.CheckoutServiceTest
```

Expected result: **5 passing tests**; no fixed business stdout because the tests only use assertions. Exact task/timing display depends on Gradle version and environment.

Lessons from each test:

| Test | Stubbing | Verification | Risk proven |
| --- | --- | --- | --- |
| `allowsNullableNote...` | `eq` + `anyLong` + `nullable` | `eq` + `eq` + `isNull` | Pins exact ID, allows null note, checks actual amount |
| `usesExactLiteral...` | All literals | All literals | No matchers needed when all arguments are exact |
| `verifiesBusinessConstraints...` | Prefix matcher | `longThat` + `argThat` | Business constraints rather than just “anything” |
| `typedStringMatcher...` | `anyString()` | Checks mock output | `null` does not match typed string matcher |
| `rejectsInvalidAmount...` | No stub | `verifyNoInteractions` | Invalid input does not call external system |

**Limitation:** The first test only proves `PaymentPort` was called with the right arguments and the mock response was forwarded by the service. It does not prove the real payment system works, real HTTP requests are valid, or data is committed to a database. Those belong to broader integration tests.

## 7. Choosing `eq`, `any`, `isNull`, and `nullable` in Practice

### 7.1. `anyString()` Does Not Replace `nullable(String.class)`

Some APIs permit a null note:

```java
// Only matches non-null String notes:
when(port.charge(eq("ORD-1"), anyLong(), anyString()))
        .thenReturn("TX-1");

// Matches both String and null notes:
when(port.charge(eq("ORD-1"), anyLong(), nullable(String.class)))
        .thenReturn("TX-1");

// Only matches null notes:
when(port.charge(eq("ORD-1"), anyLong(), isNull()))
        .thenReturn("TX-1");
```

These lines are **independent alternatives**; do not put all three stubs in the same test just to experiment, because later stubs can shadow/collide with earlier ones and strict stubbing can flag unused stubs. Put each case in its own test or compare their meaning before implementing.

Matchers do not decide **whether the contract allows null**. If the service logic forbids null, verify that the service rejects it properly instead of making stubs more permissive just to turn a test green.

### 7.2. `any()` Can Be Too Broad

```java
verify(port).charge(any(), anyLong(), any());
```

This can pass even with the wrong order ID or wrong note, and it does not reject null for either reference parameter. If the order ID is an important requirement, use `eq("ORD-42")`:

```java
verify(port).charge(
        eq("ORD-42"),
        eq(120_000L),
        nullable(String.class)
);
```

Make matchers **just narrow enough for the contract**: stubbing can be relaxed on some inputs to avoid coupling to meaningless details; verification should stay tight on high-risk fields to catch regressions.

### 7.3. When Matchers Are Unnecessary, Use Literals

```java
verify(port).charge("ORD-42", 120_000L, "gift");
```

Direct, readable, and completely valid. Do not wrap every value in `eq` out of habit if the call has no other matchers. The “all arguments must be matchers” rule is a **conditional rule**: it triggers only when **at least one matcher appears in the same call**.

## 8. `argThat`: Expressing Argument-Based Constraints

`argThat(ArgumentMatcher<T>)` checks a custom condition, often used when an object has many fields and only a few matter.

Example external interface:

```java
interface NotificationPort {
    void publish(String topic, Notice notice);
}

record Notice(String orderId, long amount, String currency) {}
```

Illustrative verification snippet:

```java
verify(notifier).publish(
        eq("payment.completed"),
        argThat(notice ->
                notice != null
                && notice.orderId().equals("ORD-42")
                && notice.amount() == 120_000L
                && notice.currency().equals("VND"))
);
```

This snippet is **not standalone**: it requires `NotificationPort`, `Notice`, mock `notifier`, and a call in Act. Since the first argument uses `eq`, the second also uses a matcher (`argThat`), preserving consistency.

### 8.1. Avoid Null-Pointer Pitfalls in Predicates

Unsafe:

```java
// Risk of NullPointerException if note is null.
argThat(note -> note.startsWith("promo-"))
```

Safer:

```java
argThat(note -> note != null && note.startsWith("promo-"))
```

If null is **permitted** by the contract, write the condition accordingly rather than excluding null by default:

```java
argThat(note -> note == null || note.startsWith("promo-"))
```

### 8.2. Primitives and Generic Types

`argThat` is a generic matcher returning a reference type, whereas `int`/`long` are primitives. For primitive parameters, modern Mockito provides dedicated matchers:

```java
verify(port).charge(
        eq("ORD-42"),
        longThat(value -> value >= 100_000L),
        anyString()
);
```

Using `longThat` avoids `argThat` boxing/unboxing issues that can trigger a `NullPointerException` from the dummy value used to compile. For `int`, use `intThat(...)`. If you only need an exact value, `eq(120_000L)` is even clearer.

### 8.3. When Should You Avoid `argThat`?

If a predicate gets long or has many branches, test failures become hard to diagnose. When you need to inspect and assert multiple fields after a call, choose `ArgumentCaptor`. If the data is an immutable record with proper `equals` and all fields belong to the contract, `eq(new Notice(...))` can be simpler than a predicate.

Matchers should be **pure conditions**—no database writes, state mutations, network calls, or counter increments. Mockito may evaluate matchers during internal operations, and tests must not depend on how many times a predicate runs.

## 9. `ArgumentCaptor`: Extracting Arguments to Assert Individual Properties

A captor is helpful when a service constructs rich objects: events, HTTP requests, emails, DTOs. You want to verify the event-sending call occurred and then inspect each field.

Example testing an event producer:

```java
// Illustrative snippet: assumes mock notifier and Notice record exist.
Notice sent = new Notice("ORD-42", 120_000L, "VND");
notifier.publish("payment.completed", sent);

ArgumentCaptor<Notice> noticeCaptor =
        ArgumentCaptor.forClass(Notice.class);

verify(notifier).publish(
        eq("payment.completed"),
        noticeCaptor.capture()
);

Notice captured = noticeCaptor.getValue();
assertEquals("ORD-42", captured.orderId());
assertEquals(120_000L, captured.amount());
assertEquals("VND", captured.currency());
```

Requires imports `org.mockito.ArgumentCaptor`, `org.mockito.Mockito.verify`, and `org.junit.jupiter.api.Assertions.assertEquals`. This is a **snippet inside a test with initialized mocks**, not a standalone Java file. In `verify(...)`, `capture()` is a matcher, so the accompanying topic argument must use `eq(...)` when matchers are used.

| Need | Choice |
| --- | --- |
| Whole object matches via `equals` | `eq(expected)` or literal |
| A few short criteria | `argThat(...)` |
| Multiple fields needing clear assertions | `ArgumentCaptor` |
| Inspect all invocations | `captor.getAllValues()` with verify count |
| Only need non-null argument | `notNull()` or `any(Type.class)` |

Mockito recommends preferring captors in **verification** rather than **stubbing**. Captors in stubs make test flow hard to read, and if the call never happens there is nothing to inspect. For conditional stubbing, use `argThat` or built-in matchers.

## 10. Matchers in `when`, `verify`, `doReturn`, and `doThrow`

The consistency rule applies everywhere Mockito interprets mock calls.

### 10.1. Stubbing Return Values

```java
when(port.charge(eq("ORD-42"), anyLong(), isNull()))
        .thenReturn("TX-9");
```

### 10.2. Verification

```java
verify(port).charge(eq("ORD-42"), eq(120_000L), isNull());
```

By default, `verify(mock).method(...)` verifies **exactly one** matching call. If business logic requires checking a count:

```java
verify(port, times(2)).charge(
        eq("ORD-42"), anyLong(), nullable(String.class)
);
```

This is a **syntax example**, not the right assertion for every payment case: if the contract only permits charging once, `times(2)` is wrong for the business rule. Mockito matching arguments does not define correct behavior; the business specification does.

### 10.3. `doReturn` with Spies or Special Stubbing

```java
doReturn("TX-9").when(port)
        .charge(eq("ORD-42"), anyLong(), isNull());
```

On a regular mock, this is an alternative to `when(...).thenReturn(...)`. On a **spy**, `when(spy.method(...))` can execute the real method during stub setup; `doReturn(...).when(spy).method(...)` avoids running the real method while stubbing. Avoid spies when unnecessary; prefer mocking clear boundaries or building simple fakes.

### 10.4. `doThrow` for `void` Methods

```java
// Illustrative with interface AuditPort { void record(String type, long amount); }
doThrow(new IllegalStateException("audit unavailable"))
        .when(auditPort)
        .record(eq("PAYMENT"), anyLong());
```

This snippet requires `auditPort` to be a mock of that interface. For void methods, `when(auditPort.record(...))` does not compile because the return type is `void`; use the `doThrow`/`doAnswer`/`doNothing` family where appropriate.

For the syntax above, imports typically come from `org.mockito.Mockito` for `when`, `verify`, `doReturn`, `doThrow`, `times`; and `org.mockito.ArgumentMatchers` for `eq`, `anyLong`, `isNull`.

## 11. Edge Cases Requiring Care: Overloaded Methods, Varargs, Generics

### 11.1. Overloaded Methods

Suppose an interface has two overloads:

```java
void send(String message);
void send(int code);
```

Calling `send(any())` may not resolve the desired overload in complex declarations; `anyString()` specifies `String`, and `anyInt()` specifies `int`.

With overloads taking multiple reference types, untyped `any()` can trigger a Java compiler **ambiguous method call** error. Pick `any(String.class)` or an explicit cast/type witness instead of changing test logic. Mockito does not alter how Java resolves overloads at compile time.

### 11.2. Varargs Parameters

Suppose:

```java
interface TagPort {
    void attach(String id, String... tags);
}
```

Varargs are represented as arrays in Java, and Mockito 5 changed varargs matching semantics compared to older Mockito:

- To match **the entire varargs array**: use `any(String[].class)` at the array position.
- To check **individual vararg elements**: pass `String` matchers at the corresponding element positions of the call.
- If tag count or contents belong to the contract, `eq(new String[] {...})` warrants attention to array comparison behavior; often an `ArgumentCaptor`/assertion or explicit element matching is clearer.

Illustrative example with a mock `tags`:

```java
verify(tags).attach(eq("ORD-42"), any(String[].class));
```

In Mockito 5, this matches a non-null `String[]` argument; it does not verify the number of tags or each tag's content. If the boundary requires exactly two tags, use matchers/assertions targeting exact count and values. When migrating tests from Mockito 4 to 5, recheck varargs stubs/verifications using `any()` against your resolved version's documentation.

### 11.3. Generic Collections

With `List<String>`, `anyList()` matches a non-null list without proving any elements. When a test must ensure the list contains a specific SKU, use `argThat(list -> list != null && list.contains("SKU-7"))` or a captor with detailed assertions.

Keep Java type inference and method signatures in mind. An overly generic matcher like `any()` can reduce readability or pick the wrong overload; typed matchers are usually better.

## 12. Checking Real Values: Do Not Let Broad Matchers Hide Bugs

Suppose the service has a bug passing `amount = 0` to the payment gateway, yet the test writes:

```java
verify(port).charge(anyString(), anyLong(), any());
```

The test can still pass. `anyLong()` does not mean “a valid long”—it matches 0 and negative numbers too.

If the contract requires the amount to be **exactly 120,000**:

```java
verify(port).charge(
        eq("ORD-42"),
        eq(120_000L),
        nullable(String.class)
);
```

If the contract only requires a **positive** amount without a fixed number:

```java
verify(port).charge(
        eq("ORD-42"),
        longThat(amount -> amount > 0L),
        nullable(String.class)
);
```

The two assertions enforce two different contracts. Stubbing matchers can be broader to define mock responses, while verification must focus on the outputs/effects the test needs to prove.

**Practical selection rules:**

1. If all arguments must match exact values, use literals or expected object equality.
2. If only some arguments need flexibility, use `eq` on fixed parts and matchers on the rest.
3. If null behavior is explicit, use `isNull` or `nullable` instead of ambiguous `any()`.
4. For custom business conditions, use `argThat`/`intThat`/`longThat`.
5. To inspect a rich object, use `ArgumentCaptor`, assert important fields, and avoid coupling to unstable metadata.

## 13. Distinguishing Mockito Matchers from Spring Boot Bean Overrides

In Spring Boot, there are two independent concerns:

- **Providing a mock bean in Spring TestContext**: Spring Boot 3.3 commonly uses `@MockBean`; Spring Framework 6.2+ provides `@MockitoBean`, and newer Boot releases recommend this mechanism.
- **Expressing conditions on mock call arguments**: uses `ArgumentMatchers.eq`, `anyLong`, `argThat`, etc. from Mockito.

Illustrative example with Spring Framework supporting `@MockitoBean`:

```java
@SpringBootTest
class PaymentFlowTest {
    @MockitoBean
    PaymentPort paymentPort;

    @Test
    void processesOrder() {
        when(paymentPort.charge(
                eq("ORD-42"),
                anyLong(),
                isNull()
        )).thenReturn("TX-9");

        // Invoke a real use case bean, then assert results.
    }
}
```

This is an **illustrative skeleton**, not a standalone test: `PaymentPort` must be a valid bean type, `@SpringBootApplication` or a proper test context is required, the real use case must be called, and assertions must be added. Do not copy this directly and treat an empty test as verifying behavior.

`@MockBean`/`@MockitoBean` determines **which bean in the Spring context is a mock**; they do not change matcher rules. Mixing literals and matchers still throws Mockito errors in Spring Boot just as in plain JUnit. Conversely, `NoSuchBeanDefinitionException` or a missing Spring context is not automatically an `InvalidUseOfMatchersException`.

In pure unit tests, prefer `mock(PaymentPort.class)` passed via constructor as in Section 6; do not start Spring just to use `eq` or `verify`.

## 14. Reading and Fixing Common Errors

### 14.1. `InvalidUseOfMatchersException`

Symptoms typically include messages like “N matchers expected, M recorded” or explain that a matcher was used outside verification/stubbing.

**Common causes:**

- Mixing literals with matchers in the same multi-argument call.
- Calling `eq()`/`any()` beforehand to store in a variable, or passing matchers into a **real object** instead of a mock.
- Using a matcher inside a sub-expression that is not a direct argument to the Mockito call.
- Leaving a stray matcher after another helper call, shifting Mockito's matcher stack.
- Using a generic matcher for a primitive parameter, causing null unboxing or overload issues.

**How to investigate:**

1. Identify the exact `when(...)`, `verify(...)`, or `doReturn(...).when(...)` line reported.
2. Count the **actual** parameters of the resolved method overload.
3. If any argument uses a matcher, convert **all** other arguments to matchers (usually `eq(...)`), or remove all matchers if every argument is fixed.
4. Search for any `any/eq/argThat` calls outside Mockito context right before the error; they can misalign the matcher stack.
5. Rerun the smallest test; do not try to fix it with `lenient()` or by changing the Spring context when the root cause is matchers.

### 14.2. Unmatched Stubbing Causes the Mock to Return Default Values

An unstubbed mock call usually returns defaults, such as `null` for `String` and `0` for primitives; some types have special default values in Mockito. For example, `anyString()` **does not** match `null`:

```java
when(port.charge(eq("ORD-42"), anyLong(), anyString()))
        .thenReturn("TX-9");

// If note is null, the stub above does not match.
String result = port.charge("ORD-42", 120_000L, null);
```

`result` will be `null` for a mock returning `String` under default answer rules, unless configured otherwise. If `null` is valid input, switch to `nullable(String.class)` or `isNull()` as required. If null input is a bug, fix the caller and add assertions rather than widening the stub to mask the bug.

### 14.3. `Wanted but not invoked` / `Arguments are different!`

Mockito recorded calls (or none at all), yet `verify(...)` found no invocation matching the matchers.

- Check whether the service was actually invoked in Act.
- Check that the exact mock instance was injected into the service.
- Compare expected ID, amount, note, whitespace, casing, object `equals`, and nullability.
- If verification uses `anyLong()` and still fails, the mismatch may be on another argument (`eq`/`isNull`) or a different method.
- Only relax matchers when the contract is truly flexible; do not use `any()` to erase an important business failure.

### 14.4. `UnnecessaryStubbingException` and `PotentialStubbingProblem`

When using `@ExtendWith(MockitoExtension.class)`, strict stubbing can report:

- **Unused stubbing:** the test declared a stub that no code path ever used.
- **Stubbing argument mismatch:** code called the same method with arguments different from the configured stub under the active strictness.

This is **not necessarily** a “mixing literal and matcher in one call” error. Even a syntactically valid matcher stub can be unused or too narrow.

Fix by removing the unused stub, moving the stub into the test that actually needs it, or reconciling the expected inputs. `lenient()` should only be used with a clear reason, not as the default way to make tests pass.

### 14.5. Spy Invoking Real Code During Stubbing

`when(spy.method(anyString()))` can invoke the real method with the matcher's dummy value during stubbing, causing side effects or errors. For spies, use:

```java
doReturn(expected).when(spy)
        .method(anyString());
```

This is a **general pattern**, not a standalone program; `spy` and `expected` must be initialized with concrete types. Apply the matcher consistency rule if `method` has multiple arguments.

### 14.6. Mockito Version, Java, or Inline Mock Maker Errors

`ClassNotFoundException`, `NoSuchMethodError`, agent instrumentation warnings on newer JDKs, or errors mocking `final` classes can stem from dependency/bytecode tooling. Check the Mockito version managed by the Spring Boot BOM, Byte Buddy, the active JDK, and `testRuntimeClasspath`; do not blame `eq` for every failure. Version numbers and support vary by Spring Boot release; use versions compatible with your current build.

## 15. Exercises: Fixing Invalid Calls

Given the interface:

```java
interface TransferGateway {
    boolean transfer(String source, String target, long amount);
}
```

Below are independent snippets. Classify each as valid/invalid and explain why.

### Exercise A

```java
when(gateway.transfer("A", anyString(), anyLong()))
        .thenReturn(true);
```

**Invalid:** mixes literal `"A"` with two matchers. Fix:

```java
when(gateway.transfer(eq("A"), anyString(), anyLong()))
        .thenReturn(true);
```

### Exercise B

```java
verify(gateway).transfer("A", "B", 50L);
```

**Valid:** uses no matchers and checks three exact values. No need to wrap everything in `eq`.

### Exercise C

```java
verify(gateway).transfer(eq("A"), eq("B"), anyLong());
```

**Valid matcher syntax**, but potentially **too broad** for the contract. If transferring exactly 50 is a core requirement, use `eq(50L)` instead of `anyLong()`.

### Exercise D

```java
when(gateway.transfer(eq("A"), anyString(), 50L))
        .thenReturn(true);
```

**Invalid:** `50L` is a literal in a call that already uses matchers. Fix:

```java
when(gateway.transfer(eq("A"), anyString(), eq(50L)))
        .thenReturn(true);
```

### Exercise E

```java
String source = eq("A");
boolean done = realGateway.transfer(source, "B", 50L);
```

**Invalid matcher usage:** `eq("A")` does not return data for business code; it records a Mockito matcher and returns a dummy value. Pass `"A"` directly to the real object; never use matchers outside stubbing/verification.

### Exercise F

```java
verify(gateway).transfer(
        eq("A"), eq("B"), longThat(n -> n > 0)
);
```

**Valid matcher usage** and meaningful if the contract requires a positive amount rather than a fixed amount. If transferring 50 is required, this test is not strong enough.

### Exercise G — `null`

Suppose `target` can be null in a legacy API (not recommended for money transfer design):

```java
when(gateway.transfer(eq("A"), anyString(), anyLong()))
        .thenReturn(true);
```

`anyString()` **does not** match `null`. If matching null is genuinely needed, change it to `nullable(String.class)`; if only null, use `isNull()`. However, in a real transfer domain, a null target is likely invalid input; test that the service rejects it and performs no transfer rather than blindly accepting null.

## 16. Hands-On Practice in a Spring Boot Project

### Practice 1 — Matchers and Logic Boundaries

Using the two Java files from Section 6:

1. Run all of `CheckoutServiceTest`.
2. Change the stub in `allowsNullableNoteWhileKeepingOrderIdExact` from `nullable(String.class)` to `anyString()`.
3. Rerun: the call with a null note no longer matches, `transactionId` is no longer `TX-9`, and the assertion fails.
4. Restore `nullable(String.class)` and rerun.

Be able to explain **why** two `String`-typed matchers behave differently on `null`.

### Practice 2 — The All-Arguments Rule

In a sandbox test, temporarily change:

```java
when(gateway.charge(
        eq("ORD-42"), anyLong(), nullable(String.class)
)).thenReturn("TX-9");
```

to:

```java
when(gateway.charge(
        "ORD-42", anyLong(), nullable(String.class)
)).thenReturn("TX-9");
```

Predict `InvalidUseOfMatchersException`. Record the argument count, matcher count, and corrected line. Then revert; never leave intentionally broken tests in CI.

### Practice 3 — Proving Overly Broad Matchers

Temporarily change `CheckoutService.checkout` to call the gateway with `amountInVnd = 1L` instead of the caller's requested amount. Compare two verifications:

```java
verify(gateway).charge(eq("ORD-42"), anyLong(), isNull());
```

and:

```java
verify(gateway).charge(eq("ORD-42"), eq(120_000L), isNull());
```

The first verification still passes, while the second fails. Revert the code. Conclusion: matchers must reflect **the risk you want to catch**, not just convenience.

### Practice 4 — Captor Instead of a Long Predicate

Suppose a service publishes an event with `orderId`, `customerId`, `amount`, `currency`, and `createdAt`. Write a verification using `eq("payment.completed")` and `ArgumentCaptor<Event>` for the payload, then assert the four business fields. For dynamically generated `createdAt`, check only according to contract (or inject a `Clock`) instead of hard-coding a timestamp.

### Practice 5 — Pull Request Review

A teammate proposes:

```java
verify(emailGateway).send(anyString(), anyString(), anyString());
```

If this is an order confirmation email, discuss three points: must the recipient match the customer's address, must the subject contain a keyword or fixed template ID, and must the body contain the order ID? You can replace `anyString()` with `eq(...)`, `contains(...)`, `argThat(...)`, or a captor per contract. Do not assume every field must be exact if content may vary by locale/template.

## 17. Checklist When Reviewing Matchers in Mockito Tests

- [ ] I know which **mock method** is being stubbed/verified and its exact argument count.
- [ ] If at least one matcher is used, **every argument in that call** uses a matcher.
- [ ] For fixed values alongside matchers, I use `eq(...)`.
- [ ] When all values are fixed, I can use literals for readability.
- [ ] I distinguish `eq` (value equality) from `same` (instance identity).
- [ ] I distinguish `any()` (can match null) from typed matchers (`anyString()`, `any(Class)`… which generally do not match null).
- [ ] I use `isNull`/`nullable` according to the nullability contract.
- [ ] I never pass a matcher's return value into real code or store it in a data variable.
- [ ] `argThat` predicates are pure, null-safe when needed, and free of side effects.
- [ ] For primitives, I use appropriate primitive matchers rather than accidentally unboxing `null`.
- [ ] For complex objects, I consider a captor + field assertions over long predicates.
- [ ] I guard critical boundaries with matchers **narrow enough** to catch business bugs.
- [ ] I know strict stubbing mismatch, missing invocation, and `InvalidUseOfMatchersException` are distinct errors.
- [ ] I have verified Mockito/JUnit on the right test classpath, module, and compatible Spring Boot version.
- [ ] Tests assert important outputs/state, not just verifying a call unrelated to the contract.

## 18. Summary

Three rules to remember:

**1. Within a single stubbed or verified call: either use no matchers, or use matchers for every argument.** Use `eq(value)` to keep a fixed value alongside other matchers.

**2. Choose matchers based on the contract.** `anyLong()` does not guarantee a positive or exact amount; `anyString()` does not match null; `nullable(String.class)` can match null. Add `argThat` and captors only when they provide better evidence.

**3. Matchers are a mock-call description mechanism, not Java data.** They record conditions inside Mockito and return dummy values. Never use matchers outside stubbing/verification, never mix matchers with literals, and never make tests so broad that bugs pass unnoticed.

## Official References for Your Project's Mockito Version

- Mockito 5.x, `ArgumentMatchers` JavaDoc (all-arguments rule, `eq`, `any`, `nullable`): https://www.javadoc.io/doc/org.mockito/mockito-core/5.21.0/org.mockito/org/mockito/ArgumentMatchers.html
- Mockito 5.x, `ArgumentCaptor` JavaDoc: https://www.javadoc.io/doc/org.mockito/mockito-core/5.21.0/org.mockito/org/mockito/ArgumentCaptor.html
- Mockito 5.x, `Mockito` JavaDoc (stubbing, verification, spy, argument matching): https://www.javadoc.io/doc/org.mockito/mockito-core/5.21.0/org.mockito/org/mockito/Mockito.html
- Mockito JUnit Jupiter extension: https://www.javadoc.io/doc/org.mockito/mockito-junit-jupiter/
- JUnit User Guide: https://docs.junit.org/current/user-guide/
- Spring Boot Testing: https://docs.spring.io/spring-boot/reference/testing/
