# ArgumentCaptor for Inspecting Data Sent to Dependencies in Spring Boot Tests

## 1. The Problem to Solve: Returning the Right Result Is Not Enough

In a Spring Boot application, a service often calls other components: a repository saving data, an HTTP client sending requests, a publisher emitting events, or an adapter sending emails. A method might **not return the data that needs to be verified**, yet still pass an important object to a dependency.

For example, `OrderService.placeOrder(...)` generates an order ID and then calls `EventPublisher.publish(event)`. A test checking only that `placeOrder` returns a UUID is insufficient: the service could still send the wrong email, drop SKUs, publish the event twice, or publish nothing. We need to observe the **actual argument passed at the dependency boundary**.

Mockito provides `ArgumentCaptor<T>` to extract that argument from a recorded mock invocation so we can inspect its details using JUnit or AssertJ. The typical pattern is:

```java
verify(publisher).publish(eventCaptor.capture());
OrderPlacedEvent event = eventCaptor.getValue();
assertEquals(expectedEmail, event.buyerEmail());
```

Meaning:
- `verify(publisher)` verifies that the expected method was actually called; by default, **exactly once**.
- `eventCaptor.capture()` registers a matcher to capture the argument in the verified invocation.
- `getValue()` returns the captured argument; subsequent assertions verify the business-required properties.

**Key point:** `ArgumentCaptor` does not verify data correctness on its own, nor does it assert that the call occurred. Confidence comes from **verification combined with explicit assertions**. A captor also only sees calls to the configured mock; it does not prove that a real dependency saved to a database or successfully delivered a message.

## 2. When Should You Use ArgumentCaptor?

Use a captor when the data passed to a mock cannot be compared easily with a single literal value, or when you need to inspect multiple fields of an object:

- A service generates UUIDs, timestamps, correlation IDs, amounts, or computed fields and passes a DTO to a repository or message publisher.
- An adapter maps an input request into another command/event; the test needs to check exact mapping.
- A dependency returns `void`, so the observable outcome is primarily the invocation and the data sent.
- Multiple calls occur to the same method, and you need to inspect each argument and their order.
- You need to verify key fields of a complex object without coupling the test to fields outside the contract.

You do not need a captor for every call. When the entire argument is known upfront and has a proper `equals`, this is clearer:

```java
verify(publisher).publish(expectedEvent);
```

When only one simple condition needs checking inline at the call site, `argThat` is concise too:

```java
verify(publisher).publish(argThat(event ->
        event != null && event.buyerEmail().equals("buyer@example.test")));
```

Both snippets above are **illustrative within a test that already has `publisher` and the relevant Mockito imports**, not standalone Java programs. Choose a captor when you want to **read the full passed object clearly**, write multiple assertions, or compare against values generated during execution.

## 3. Mechanism: Mock Records Calls, verify Selects Calls, Captor Extracts Arguments

The test workflow has four steps:

1. **Create a mock** of the dependency and supply it to the real object under test (SUT – system under test). For unit tests, constructor instantiation of the service is usually enough.
2. **Invoke behavior** on the real service: `service.placeOrder(...)`. Mockito records the `publisher.publish(...)` call made on the mock.
3. **Verify the call with the captor**: `verify(publisher, times(1)).publish(captor.capture())`. If the expected call did not occur, this step fails; do not proceed assuming an argument was captured.
4. **Read data and assert**: `captor.getValue()`, `assertEquals`, `assertAll`, `containsExactly`, etc. to inspect the data sent.

Two common ways to declare a captor:

```java
// Approach 1: declare directly inside a test method.
ArgumentCaptor<OrderPlacedEvent> captor =
        ArgumentCaptor.forClass(OrderPlacedEvent.class);

// Approach 2: use MockitoExtension or open mock annotations before the test.
@Captor
ArgumentCaptor<OrderPlacedEvent> eventCaptor;
```

With `@Captor`, you need a Mockito annotation initialization mechanism, such as `@ExtendWith(MockitoExtension.class)` in JUnit Jupiter. Without initialization, the field can be `null` and the test will fail before checking data. For generic types like `ArgumentCaptor<List<String>>`, `@Captor` also avoids awkward raw-type casts.

Typically, use `capture()` inside **`verify(...)` after executing the behavior**, rather than placing a captor inside `when(...)` to probe data. Mockito recommends captors for verification; using them during stubbing makes tests harder to read or fail because no invocation has happened yet.

## 4. Complete Java 17+ Example: Capturing Order Event Data

### 4.1. Contract to Protect

A service takes an email and a list of SKUs, generates an order UUID, and publishes an `OrderPlacedEvent` to `EventPublisher`. We want to prove:

1. The event is published **exactly once** when placing a valid order.
2. The UUID inside the event equals the UUID returned to the caller.
3. The email sent is trimmed, and the SKU list preserves order and elements.
4. The event stores an **immutable copy** of the list, so mutating the input list afterward does not alter event data.
5. Two valid orders produce **two calls**; each event can be checked in invocation order.
6. Invalid input **publishes no event at all**.

The classes below run in a Java 17+ project configured with JUnit Jupiter and Mockito (in a Spring Boot project, these libraries are typically provided by `spring-boot-starter-test`). This is a unit test; no Spring context startup is needed.

### 4.2. Record Representing the Outgoing Data

File `src/main/java/com/example/testing/OrderPlacedEvent.java`:

```java
package com.example.testing;

import java.util.List;
import java.util.Objects;
import java.util.UUID;

public record OrderPlacedEvent(
        UUID orderId,
        String buyerEmail,
        List<String> skuCodes) {

    public OrderPlacedEvent {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(buyerEmail, "buyerEmail");
        skuCodes = List.copyOf(skuCodes);
    }
}
```

Java 17 records provide component-based `equals`/`hashCode`. `List.copyOf` creates a collection unmodifiable through the collection API while preserving order and duplicates. The code assumes `skuCodes` contains no `null` elements and SKUs are immutable `String` values; `List.copyOf` throws `NullPointerException` if the collection or any element is `null`.

### 4.3. Dependency and Real Service

File `src/main/java/com/example/testing/EventPublisher.java`:

```java
package com.example.testing;

public interface EventPublisher {
    void publish(OrderPlacedEvent event);
}
```

File `src/main/java/com/example/testing/OrderService.java`:

```java
package com.example.testing;

import java.util.List;
import java.util.UUID;

public final class OrderService {
    private final EventPublisher publisher;

    public OrderService(EventPublisher publisher) {
        this.publisher = publisher;
    }

    public UUID placeOrder(String buyerEmail, List<String> skuCodes) {
        if (buyerEmail == null || buyerEmail.isBlank()
                || skuCodes == null || skuCodes.isEmpty()) {
            throw new IllegalArgumentException("Invalid order input");
        }

        UUID orderId = UUID.randomUUID();
        OrderPlacedEvent event =
                new OrderPlacedEvent(orderId, buyerEmail.trim(), skuCodes);
        publisher.publish(event);
        return orderId;
    }
}
```

The service is plain Java so the test focuses on dependency-calling behavior. In real Spring Boot, you can add `@Service` and constructor-inject `EventPublisher`; Mockito's verification remains identical. The example omits a real broker or repository because what we are verifying is **the data the service passes to its dependency**.

### 4.4. Test Using @Mock, @Captor, and MockitoExtension

File `src/test/java/com/example/testing/OrderServiceTest.java`:

```java
package com.example.testing;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    EventPublisher publisher;

    @Captor
    ArgumentCaptor<OrderPlacedEvent> eventCaptor;

    @Test
    void publishesCorrectDataExactlyOnce() {
        OrderService service = new OrderService(publisher);
        List<String> inputSkus =
                new ArrayList<>(List.of("SKU-2", "SKU-1"));

        UUID returnedId = service.placeOrder(
                "  buyer@example.test  ", inputSkus);

        verify(publisher).publish(eventCaptor.capture());
        OrderPlacedEvent published = eventCaptor.getValue();

        assertAll("event data",
                () -> assertEquals(returnedId, published.orderId()),
                () -> assertEquals(
                        "buyer@example.test", published.buyerEmail()),
                () -> assertEquals(
                        List.of("SKU-2", "SKU-1"), published.skuCodes()));

        inputSkus.add("SKU-LATE");
        assertEquals(
                List.of("SKU-2", "SKU-1"), published.skuCodes());
        verifyNoMoreInteractions(publisher);
    }

    @Test
    void capturesEveryPublishedEventInInvocationOrder() {
        OrderService service = new OrderService(publisher);

        UUID firstId = service.placeOrder(
                "first@example.test", List.of("A", "A"));
        UUID secondId = service.placeOrder(
                "second@example.test", List.of("B"));

        verify(publisher, times(2)).publish(eventCaptor.capture());

        List<OrderPlacedEvent> events = eventCaptor.getAllValues();
        assertEquals(2, events.size());
        assertEquals(firstId, events.get(0).orderId());
        assertEquals("first@example.test", events.get(0).buyerEmail());
        assertEquals(List.of("A", "A"), events.get(0).skuCodes());
        assertEquals(secondId, events.get(1).orderId());
        assertEquals("second@example.test", events.get(1).buyerEmail());
        assertEquals(List.of("B"), events.get(1).skuCodes());
        verifyNoMoreInteractions(publisher);
    }

    @Test
    void rejectsInvalidOrderWithoutPublishing() {
        OrderService service = new OrderService(publisher);

        assertThrows(IllegalArgumentException.class,
                () -> service.placeOrder(" ", List.of("A")));
        assertThrows(IllegalArgumentException.class,
                () -> service.placeOrder(
                        "buyer@example.test", List.of()));

        verifyNoInteractions(publisher);
    }
}
```

**Why are these assertions meaningful?**

- `verify(publisher).publish(...)` defaults to `times(1)`. If the service publishes zero or two events, this verification fails.
- `getValue()` lets us read the `OrderPlacedEvent` and check the **dynamic UUID**, normalized email, and SKU list. Just `verify(publisher).publish(any())` would not prove any of those fields are right.
- With two calls, `times(2)` verifies the count; `getAllValues()` returns captured arguments in matching invocation order so the first and second events can be inspected individually.
- `verifyNoMoreInteractions` adds that no other unverified calls occurred on that mock. Use selectively; asserting too strictly on non-contract auxiliary interactions can make tests brittle during refactoring.
- `verifyNoInteractions` confirms invalid input does not touch the publisher at all, not merely a single overload.
- `inputSkus.add(...)` checks the post-condition regarding **defensive copying**, since the record uses `List.copyOf`. This is not proof about a real broker.

These three tests are designed to **pass** with the three production classes above. They print no separate `stdout`; Gradle/Maven output depends on the runner. Only conclude they genuinely pass in your project after running the build and reading the report.

### 4.5. Running Tests in a Spring Boot Project

With Gradle Wrapper on Linux/macOS:

```bash
./gradlew test --tests "com.example.testing.OrderServiceTest"
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.testing.OrderServiceTest"
```

With Maven Wrapper on Linux/macOS:

```bash
./mvnw -Dtest=OrderServiceTest test
```

On Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=OrderServiceTest test
```

Prerequisites: the project has JUnit Jupiter, Mockito Core, the Mockito JUnit Jupiter extension, and a Jupiter discovery runner (Gradle usually configures `useJUnitPlatform()`; Maven needs a compatible Surefire). If not using Spring Boot starter, declare those test dependencies explicitly. Do not compile these files directly with `javac` lacking JUnit/Mockito on the classpath; wrapper commands are standard inside a project.

## 5. getValue(), getAllValues(), and Invocation Counts

For `publish(event)`, each call carries one argument. Different verifications check different things:

| Need | Usage | Important note |
|---|---|---|
| Single call | `verify(publisher).publish(captor.capture())` | Defaults to exactly once |
| Two calls | `verify(publisher, times(2)).publish(captor.capture())` | Every matching call is added to the captor |
| Read value after single capture | `captor.getValue()` | If multiple values were captured, typically returns the **last** one |
| Read all captured values | `captor.getAllValues()` | List of values in capture order, convenient for inspecting each call |
| No interactions at all | `verifyNoInteractions(publisher)` | Do not call `getValue` when nothing was captured |

If you write `verify(publisher).publish(captor.capture())` when two calls happened, Mockito reports too many invocations; verification does not substitute for `times(2)`. Conversely, `getValue()` after multiple captures only inspects the last value and **does not prove earlier calls' values**.

For methods with multiple parameters:

```java
// Illustrative snippet in a test with a mock:
// void send(String recipient, Notification payload)
ArgumentCaptor<String> toCaptor = ArgumentCaptor.forClass(String.class);
ArgumentCaptor<Notification> payloadCaptor =
        ArgumentCaptor.forClass(Notification.class);

verify(client).send(toCaptor.capture(), payloadCaptor.capture());
assertEquals("buyer@example.test", toCaptor.getValue());
// Continue asserting fields of payloadCaptor.getValue().
```

This illustrates syntax for a hypothetical `client` interface and `Notification` type, **not a standalone Java file**. With multiple calls, verify the right `times(n)` and correlate `getAllValues()` across both captors by index.

## 6. An Easily Missed Detail: Captors Hold Object References

Mockito records **the object passed in**, rather than taking a deep snapshot of all fields at the moment of the call. If the SUT passes a mutable object and mutates it **after calling the mock**, by the time the test runs `getValue()`, that object may hold the later state.

Warning example:

```java
// Pseudocode inside a SUT where MutableMessage allows state mutation:
MutableMessage message = new MutableMessage("QUEUED");
publisher.publish(message);
message.setStatus("SENT");
```

If the test inspects the captor after the service finishes, `captor.getValue().getStatus()` can be `"SENT"`, even though the status **at the time of `publish`** was `"QUEUED"`. Because the captor holds a reference, tests cannot treat post-call state as proof of state at invocation time.

How to reduce this risk:
- Prefer **immutable** DTOs/commands/events (`record`, `List.copyOf`, defensive copies for mutable internals).
- If a mutable object must be sent and you need a **snapshot at call time**, use `doAnswer` to copy the relevant fields right when the mock receives the call.
- Do not mutate the object returned by the captor in tests, as that can mutate the same object the mock received; avoid relying on such side effects.

`List.copyOf` only copies the list structure and **does not deep-copy mutable elements**. With `List<MutableItem>`, each `MutableItem`'s contents can still change; use immutable element records or deep copies as required by the contract.

## 7. Captors and Matchers: Choosing the Right Check Level

| Tool | Primary purpose | Good fit |
|---|---|---|
| Concrete value in `verify` | Compare the whole argument via `equals` | `verify(repo).save(expected)` |
| `eq(expected)` | Equality matcher when combined with other matchers | `verify(client).send(eq("x"), any())` |
| `any(Type.class)` | Only verify a non-null argument of the type without checking fields | `verify(repo).save(any(Order.class))` |
| `argThat(predicate)` | Check a condition inline at verification | `argThat(e -> e.status().equals("READY"))` |
| `ArgumentCaptor` | Read the real argument, check multiple fields, dynamic values, multiple calls | Capturing an event containing a service-generated UUID |

**Matcher rule:** Whenever a Mockito call uses an argument matcher for one parameter, the remaining parameters must also use matchers (`eq(...)`, `any(...)`, `capture()`, etc.). Mixing matchers with raw literals triggers `InvalidUseOfMatchersException`.

Valid example for a two-parameter method:

```java
verify(client).send(
        eq("buyer@example.test"), payloadCaptor.capture());
```

This is an illustrative snippet in a test where `client`, `eq`, and `payloadCaptor` are declared. If you only need to check one condition without reading many fields, `argThat` can be shorter; if you want clear per-field failure messages, a captor with `assertAll` is usually easier to maintain.

## 8. Applying This in Real Spring Boot Tests

**Unit tests with MockitoExtension:** As in Section 4, construct the real service via constructor with mock dependencies. This starts no `ApplicationContext`, runs fast, and works well to verify that a service **calls a port/interface with the right data**.

**Integration/slice tests with a Spring context:** When verifying mappings/controllers or Spring configuration along real paths, the mock must replace the exact bean used by the service. In modern projects, tools like `@MockitoBean` (on supported Spring Framework versions) or the mock-bean replacement mechanism for your Spring Boot version apply. If you create a standalone `@Mock` while the Spring service calls a different real bean, a captor on that mock will see **no invocations** even though the application called the other bean.

**Repository:** `verify(repository).save(captor.capture())` verifies what entity/data the service **requested** to save. It does not prove JPA mapping, database constraints, transactions, or committed rows. When risk lies in persistence, write integration tests with a real repository/database.

**Message broker/HTTP client:** Captors show what command/request/payload reached the mocked adapter. They do not confirm the broker received the message or the remote server handled it. For wire contracts, write integration/contract tests covering serialization, headers, retries, error responses, and real transport at the appropriate layer.

**Mockito and AOP/proxies:** Verify on the exact mock instance invoked by the code under test; avoid mixing spies/mocks across multiple instances or accidentally bypassing a Spring proxy when proxy behavior itself is what needs testing. Captors do not replace understanding the boundary between SUT and dependencies.

## 9. Common Errors and How to Analyze Them

### 9.1. "Wanted but not invoked"

Messages like `Wanted but not invoked` mean the verified invocation never occurred on **that mock** matching the matcher criteria. Check:
- Did the SUT actually execute the branch calling the dependency?
- Was a different instance of the publisher/repository accidentally created?
- Is a Spring service using a different bean from the test's mock?
- Do arguments/matchers match the actual call?

Do not fix this by deleting `verify` or switching to `any()` when the outgoing data itself is the risk you are testing.

### 9.2. "Too many actual invocations"

If default `verify(mock)` expects once and two calls occurred, that could be a duplicate-event bug or an imprecise test expectation. Confirm the contract and use exact `times(n)`. Never blindly bump `n` just to make the test green.

### 9.3. Calling getValue() Before Capturing

`getValue()` is only meaningful **after a corresponding verification/stubbing has captured successfully**. If the test never called `verify(...capture())`, or verification failed, do not assume the captor holds data. Inspect the JUnit/Mockito failure on the invocation first.

### 9.4. Checking Only "Event Was Published", Ignoring Its Data

```java
verify(publisher).publish(any(OrderPlacedEvent.class));
```

This confirms the mock received a non-null argument of the right type, yet **checks nothing** about the UUID, email, SKU list, amount, or metadata. In an `ArgumentCaptor` test, add assertions for every field belonging to the contract.

### 9.5. Captor Succeeds, but the Test Is Too Brittle

A test that captures a DTO and compares every internal field unrelated to requirements can break during valid refactoring. Prefer asserting fields defining the integration contract: IDs, recipients, amounts, statuses, item lists, and contract-defined timestamps/events. Do not assert clocks or random IDs against fixed literals unless you inject the generator or match against the returned value.

### 9.6. Mistaking a Mutable Object for a Snapshot

Captors only hold references. To inspect state **at the moment of the call**, switch to immutable events or capture a copy inside the invocation. Immutable events also prevent bugs when messages are later processed asynchronously.

### 9.7. Forgetting Order and Multiplicity Across Multiple Calls

`getAllValues()` inspects multiple invocations, and tests must decide whether invocation order is part of the contract. If order does not matter, compare relevant fields as collections or multisets as appropriate, **preserving duplicate counts when duplicates matter**. Do not blindly convert to a `Set` if publishing an event twice is a bug you need to catch.

## 10. Checklist Before Concluding an ArgumentCaptor Test Is Sound

- [ ] Testing the **real object** (service/adapter), while the dependency is the right mock instance.
- [ ] Behavior is executed first, followed by `verify(...capture())` on the right mock and method.
- [ ] Invocation count is verified (`times(n)`, default once, or `verifyNoInteractions` when required).
- [ ] `getValue()` is used for a single capture or `getAllValues()` for multiple invocations.
- [ ] Important internal data is asserted: dynamic IDs, normalized fields, collections, recipients, statuses…
- [ ] Content at invocation time is distinguished from state mutated after the invocation.
- [ ] Matchers are used consistently when the method has multiple arguments.
- [ ] **Calling the mock with right data** is distinguished from **the real dependency completing the operation**.
- [ ] The exact test class was run and Gradle/Maven/CI reports were checked rather than guessing from examples.

**Conclusion:** `ArgumentCaptor` lets Mockito inspect **the actual data transferred from a Spring Boot service to a mocked dependency**. The reliable flow is **execute service → verify exact invocation → capture argument → assert required business fields**. Use `getAllValues()` for multiple calls; watch out for mutable objects because captors do not take snapshots; and add appropriate integration tests whenever real database or broker processing must be proven.
