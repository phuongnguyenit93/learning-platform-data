# Testing Outbound Data Instead of Only Counting Calls

> **Module:** Spring Boot – testing  
> **Category:** Business unit tests  
> **Focus:** A dependency called once can still receive **wrong data**. Good tests verify the **payload, business values, and side effects** sent across the unit's outbound boundary.

## 1. The Problem: Right Call Count Is Not Enough to Prove Business Correctness

Suppose a system has an order-creation use case. After saving the order, the service must send an `OrderCreated` event to an event-publishing port. Tests like this are very common:

```java
service.place(command);
verify(publisher, times(1)).publish(any(OrderCreatedEvent.class));
```

This only proves: **the mock publisher received one `publish` call with an argument of type `OrderCreatedEvent`**. It **does not prove** the customer, SKU, quantity, amount, currency, or order ID was sent accurately.

Suppose the service has a bug and actually sends:

```text
orderId        = 501
recipientEmail = wrong@example.test  <-- Wrong recipient
sku            = SKU-9
quantity       = 3
total          = 0.00                <-- Wrong total
currency       = USD
```

A call-counting test can still pass. That is **false confidence**: checking something true yet far weaker than the business contract.

A valuable test clearly answers:

1. **Was it sent or not?** For instance, an event published upon successful order creation.
2. **Where was it sent and what type?** For instance, to `OrderEventPublisher`, as an `OrderCreatedEvent`.
3. **What is the payload content?** Saved order ID, normalized email, SKU, quantity, total amount, and currency.
4. **Under what conditions is it sent?** Not published when input is invalid or saving fails.
5. **Are there call-count and ordering constraints?** Assert “exactly once” or “save before publish” only when that is actually the contract.

This lesson covers **business unit tests with outbound collaborators**. Mockito helps verify the data **a unit hands off to an external port**; it does not by itself prove Kafka, SMTP, an HTTP endpoint, or a real database received the data.

## 2. Four Levels of Checking Outbound Interactions

| Test approach | What it actually verifies | Bugs that can still slip through |
| --- | --- | --- |
| `verify(publisher).publish(any())` | At least one invocation matching the matcher and default count; ignores content | Event contains wrong ID, recipient, or amount |
| `verify(publisher, times(1)).publish(any(OrderCreatedEvent.class))` | Exactly one invocation with an argument of the expected type | Every field inside the event can still be wrong |
| `verify(publisher).publish(expectedEvent)` | Event matches expected via `equals` with one matching invocation | If the publisher receives **an extra differing event**, this assertion alone does not necessarily fail |
| `verify(publisher).publish(captor.capture())` + content assertions | Captures the actual event and asserts fields/DTO, while also verifying count | Protects only asserted fields; still a mock, not real delivery |

A great option when the argument is an **immutable Java record** whose fields form the full contract: use `verify(publisher).publish(new OrderCreatedEvent(...))`. Records implement component-wise `equals`, keeping assertions concise and concrete.

When events contain dynamic fields (timestamps, correlation IDs, UUIDs), large payloads, or require field-by-field failure messages, use **`ArgumentCaptor`**, then assert exact contract fields. When a test invokes once and a captor is used in `verify(publisher).publish(captor.capture())`, Mockito confirms one matching invocation; to catch **any** unintended extra events, consider `verifyNoMoreInteractions(publisher)` or verify all meaningful invocations.

**Important:** never optimize tests for “as many `verify` calls as possible”. Verify the data and behavior that users, downstream systems, or the database actually rely on.

## 3. Designing the Contract Before Writing Mockito Code

Consider these concrete requirements:

- Inputs include `customerEmail`, `sku`, `unitPrice`, and `quantity`.
- Email and SKU are `trim()`-med before saving/publishing.
- `quantity` must be greater than 0, and `unitPrice` non-negative.
- Total = `unitPrice × quantity`, rounded to two decimal places with `HALF_UP`.
- After the repository returns a valid ID, the service sends exactly **one** `OrderCreatedEvent` containing that ID, normalized email, normalized SKU, quantity, total, and `currency="USD"`.
- If input is invalid or the repository throws, **do not publish an event**.
- The service returns a receipt containing the ID and total for the caller.

Independent expected table:

| Value | Input or dependency result | Expected outbound value |
| --- | --- | --- |
| `customerEmail` | `" buyer@example.test "` | `"buyer@example.test"` |
| `sku` | `" SKU-9 "` | `"SKU-9"` |
| `quantity` | `3` | `3` |
| `unitPrice` | `12.50` | Used to compute total, not an event field |
| `total` | `12.50 × 3` | `37.50` |
| `orderId` | Mock repository returns `501` | `501` |
| `currency` | Defined by example rule | `"USD"` |

If you only verify the publisher was called once, bugs like **sending an untrimmed email**, **hardcoding quantity to 1**, **always sending total 0**, or **using a temporary ID before saving** would still pass. With this table, we know the exact expected payload to verify.

## 4. Runnable Spring Boot/Java 17 Test Project

The sample below uses **Spring Boot 3.5.0, Java 17, JUnit Jupiter, and Mockito**. All unit tests run **without loading a Spring context**, since what is being verified is the business logic of `CheckoutService`. You can use this exact design for a service registered as a bean in a real application, while unit tests do not need to boot Spring to check outbound ports.

### 4.1. File structure

```text
outbound-payload-test/
├── pom.xml
└── src/
    ├── main/java/com/example/outbound/
    │   ├── OutboundDemoApplication.java
    │   ├── PlaceOrderCommand.java
    │   ├── OrderDraft.java
    │   ├── SavedOrder.java
    │   ├── OrderCreatedEvent.java
    │   ├── OrderReceipt.java
    │   ├── OrderRepository.java
    │   ├── OrderEventPublisher.java
    │   └── CheckoutService.java
    └── test/java/com/example/outbound/
        └── CheckoutServiceTest.java
```

### 4.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>outbound-payload-test</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-test` provides JUnit Jupiter, Mockito, AssertJ, Spring Test, and common testing utilities. No `@SpringBootTest` is needed for this unit test sample. Checking bean wiring or real connectors later belongs to a different test scope.

### 4.3. Application Java code

Place each `public record`/`public interface`/`public class` in the **exact file** matching its type name, under package `com.example.outbound`.

```java
// OutboundDemoApplication.java
package com.example.outbound;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OutboundDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(OutboundDemoApplication.class, args);
    }
}
```

```java
// PlaceOrderCommand.java
package com.example.outbound;

import java.math.BigDecimal;

public record PlaceOrderCommand(
        String customerEmail, String sku,
        BigDecimal unitPrice, int quantity) {}
```

```java
// OrderDraft.java
package com.example.outbound;

import java.math.BigDecimal;

public record OrderDraft(
        String customerEmail, String sku,
        int quantity, BigDecimal total) {}
```

```java
// SavedOrder.java
package com.example.outbound;

public record SavedOrder(long id) {}
```

```java
// OrderCreatedEvent.java
package com.example.outbound;

import java.math.BigDecimal;

public record OrderCreatedEvent(
        long orderId,
        String recipientEmail,
        String sku,
        int quantity,
        BigDecimal total,
        String currency) {}
```

```java
// OrderReceipt.java
package com.example.outbound;

import java.math.BigDecimal;

public record OrderReceipt(long orderId, BigDecimal total) {}
```

```java
// OrderRepository.java
package com.example.outbound;

public interface OrderRepository {
    SavedOrder save(OrderDraft draft);
}
```

```java
// OrderEventPublisher.java
package com.example.outbound;

public interface OrderEventPublisher {
    void publish(OrderCreatedEvent event);
}
```

```java
// CheckoutService.java
package com.example.outbound;

import java.math.BigDecimal;
import java.math.RoundingMode;

public final class CheckoutService {
    private final OrderRepository repository;
    private final OrderEventPublisher publisher;

    public CheckoutService(
            OrderRepository repository,
            OrderEventPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    public OrderReceipt place(PlaceOrderCommand command) {
        if (command == null
                || command.customerEmail() == null
                || command.customerEmail().isBlank()
                || command.sku() == null
                || command.sku().isBlank()
                || command.unitPrice() == null
                || command.unitPrice().signum() < 0
                || command.quantity() <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }

        String email = command.customerEmail().trim();
        String sku = command.sku().trim();
        BigDecimal total = command.unitPrice()
                .multiply(BigDecimal.valueOf(command.quantity()))
                .setScale(2, RoundingMode.HALF_UP);

        OrderDraft draft = new OrderDraft(
                email, sku, command.quantity(), total);

        SavedOrder saved = repository.save(draft);
        if (saved == null || saved.id() <= 0) {
            throw new IllegalStateException("No valid saved order ID");
        }

        OrderCreatedEvent event = new OrderCreatedEvent(
                saved.id(), email, sku,
                command.quantity(), total, "USD");
        publisher.publish(event);

        return new OrderReceipt(saved.id(), total);
    }
}
```

**Unit boundary:** `CheckoutService` is real; `OrderRepository` and `OrderEventPublisher` are dependency interfaces. In real applications, those interfaces have implementations/adapters and `CheckoutService` may be registered as a Spring bean. So that the unit test example runs and the sample app boots standalone, the service class is not annotated with `@Service`; this lesson configures no real adapters and does not claim events reach a broker.

**Business note:** ID `501` is returned by the mock repository in tests; the event must use the **saved** ID. Amount 37.50 comes from 12.50 × 3; expected values must not be calculated by calling the service.

### 4.4. Unit test thoroughly verifying outbound data

```java
// CheckoutServiceTest.java
package com.example.outbound;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrowsExactly;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CheckoutServiceTest {

    @Mock
    OrderRepository repository;

    @Mock
    OrderEventPublisher publisher;

    @InjectMocks
    CheckoutService service;

    @Captor
    ArgumentCaptor<OrderDraft> savedDraftCaptor;

    @Captor
    ArgumentCaptor<OrderCreatedEvent> eventCaptor;

    private PlaceOrderCommand validCommand() {
        return new PlaceOrderCommand(
                " buyer@example.test ", " SKU-9 ",
                new BigDecimal("12.50"), 3);
    }

    @Test
    void sendsCorrectBusinessPayloadAfterSaving() {
        when(repository.save(any(OrderDraft.class)))
                .thenReturn(new SavedOrder(501L));

        OrderReceipt receipt = service.place(validCommand());

        verify(repository).save(savedDraftCaptor.capture());
        assertEquals(
                new OrderDraft("buyer@example.test", "SKU-9",
                        3, new BigDecimal("37.50")),
                savedDraftCaptor.getValue());

        verify(publisher).publish(eventCaptor.capture());
        assertEquals(
                new OrderCreatedEvent(
                        501L,
                        "buyer@example.test",
                        "SKU-9",
                        3,
                        new BigDecimal("37.50"),
                        "USD"),
                eventCaptor.getValue());

        assertEquals(new OrderReceipt(
                501L, new BigDecimal("37.50")), receipt);
    }

    @Test
    void invalidQuantityCausesNoOutboundCall() {
        PlaceOrderCommand invalid = new PlaceOrderCommand(
                "buyer@example.test", "SKU-9",
                new BigDecimal("12.50"), 0);

        assertThrowsExactly(IllegalArgumentException.class,
                () -> service.place(invalid));

        verifyNoInteractions(repository, publisher);
    }

    @Test
    void repositoryFailureDoesNotPublishAnEvent() {
        when(repository.save(any(OrderDraft.class)))
                .thenThrow(new IllegalStateException("Storage unavailable"));

        IllegalStateException failure = assertThrowsExactly(
                IllegalStateException.class,
                () -> service.place(validCommand()));

        assertEquals("Storage unavailable", failure.getMessage());
        verifyNoInteractions(publisher);
    }

    @Test
    void invalidSavedIdDoesNotPublishAnEvent() {
        when(repository.save(any(OrderDraft.class)))
                .thenReturn(new SavedOrder(0L));

        assertThrowsExactly(IllegalStateException.class,
                () -> service.place(validCommand()));

        verifyNoInteractions(publisher);
    }
}
```

**The four test methods** serve four clear goals:

1. Saves the right draft, publishes the right event **field-by-field**, and returns a receipt matching ID/total.
2. Invalid quantity calls neither repository nor publisher.
3. Storage failure does not publish, and propagates the error per contract.
4. Invalid ID returned by repository does not publish.

Critical assertions do not rest on mere invocation counts. The first test also verifies the payload saved to the repository before checking the payload published to the event port. Negative tests use `verifyNoInteractions` because the real requirement is **producing zero side effects** when preconditions fail.

### 4.5. Why do these test pieces work?

- `@ExtendWith(MockitoExtension.class)` initializes and manages Mockito mocks for JUnit Jupiter.
- `@Mock` creates fake dependencies without any real DB/broker.
- `@InjectMocks` constructs `CheckoutService` and injects mocks via constructor.
- `when(repository.save(any(OrderDraft.class))).thenReturn(new SavedOrder(501L))` controls the ID returned by the repository without dictating the event the service emits.
- `@Captor` creates typed `ArgumentCaptor` fields; `verify(...).save(captor.capture())` and `verify(...).publish(captor.capture())` capture the **exact arguments passed out by the service**.
- `assertEquals(expectedRecord, capturedRecord)` uses record value equality to check every component. For `BigDecimal`, equality also checks scale; because the code sets `setScale(2)`, expected `37.50` matches the exact scale.
- `verifyNoInteractions(publisher)` is stronger than merely checking no return value: it forces the service to emit zero events on those two error branches.

If someone accidentally modifies:

```java
// Illustrative bug snippet, do not apply to valid code:
publisher.publish(new OrderCreatedEvent(
        saved.id(),
        command.customerEmail(),  // Not trimmed
        sku,
        1,                         // Wrong quantity
        BigDecimal.ZERO,           // Wrong total
        "USD"));
```

`verify(publisher, times(1)).publish(any(OrderCreatedEvent.class))` would still pass; the event-capturing test above will fail. That is the difference between **verifying a call occurred** and **verifying the outbound data is right**.

## 5. Two Alternatives Besides `ArgumentCaptor`

### 5.1. Direct argument comparison with `equals`

With an immutable `record` DTO, you can write concisely in the test:

```java
verify(publisher).publish(new OrderCreatedEvent(
        501L, "buyer@example.test", "SKU-9",
        3, new BigDecimal("37.50"), "USD"));
```

This is a **drop-in replacement for the verify and captor lines in the success test**, not a standalone test you can paste outside a class. It is crisp, concise, and builds on record equality. If a DTO is a regular class lacking value-based `equals`, Mockito defaults to identity comparison; implement domain equality or use a captor.

Note: `verify(publisher).publish(expectedEvent)` checks only **one matching invocation**. If the code emits an extra event with different content, this invocation check alone might miss it. When the contract demands **only one event in total**, add:

```java
verifyNoMoreInteractions(publisher);
```

after verifying the expected event. When using `ArgumentCaptor` in `verify(publisher).publish(captor.capture())`, the captor matches compatible invocations and Mockito checks the default count; in this example the publisher has only one typed method `publish(OrderCreatedEvent)`.

### 5.2. `argThat` when only part of the payload belongs to the contract

When an event carries dynamic fields that need not match verbatim, tests can assert only the fields that matter:

```java
verify(publisher).publish(argThat(event ->
        event != null
        && event.orderId() == 501L
        && "buyer@example.test".equals(event.recipientEmail())
        && "SKU-9".equals(event.sku())
        && event.quantity() == 3
        && new BigDecimal("37.50").compareTo(event.total()) == 0
        && "USD".equals(event.currency())));
```

This snippet goes **inside the test class** after calling the service with a mock repository returning `501L`; it requires static import `org.mockito.ArgumentMatchers.argThat`. Advantage: expresses subsets/semantics cleanly and allows `compareTo` to avoid locking `BigDecimal` scale when scale is not part of the contract. Disadvantage: on mismatch, failure messages are usually less informative than `ArgumentCaptor` paired with descriptive assertions.

Never write a vacuous matcher like `argThat(event -> true)`: that merely renames `any()` and verifies nothing about data.

### 5.3. When to use which approach?

| Situation | Preferred approach | Reason |
| --- | --- | --- |
| Immutable record holding full contract | `verify(mock).send(expectedRecord)` | Short, direct, complete |
| DTO with many fields needing detailed mismatch diagnostics | `ArgumentCaptor` + `assertAll`/AssertJ | Pinpoints which field failed |
| Only part of the event is deterministic, rest dynamic | `argThat` or captor + per-field assertions | Avoids locking non-contract values |
| Multiple invocations requiring collection checks | `ArgumentCaptor#getAllValues()` | Retrieves every emitted event |
| Preferring to treat outbound data as pure output | Recording fake instead of mock | Easy to assert entire payload list |
| Only ensuring no side effect on error | `verifyNoInteractions` | Expresses negative contract cleanly |

## 6. Separating Call Count, Payload Content, and Call Order Assertions

### 6.1. Call count as an independent property

Some contracts truly require **exactly once** (such as one confirmation notification per order). Assert the count, yet **pair count with payload content**:

```java
ArgumentCaptor<OrderCreatedEvent> captor =
        ArgumentCaptor.forClass(OrderCreatedEvent.class);

verify(publisher, times(1)).publish(captor.capture());
assertEquals(expectedEvent, captor.getValue());
```

This is an **embeddable test snippet**, assuming `publisher`, `expectedEvent`, and static imports `verify`/`times`. Here `times(1)` asserts count while `assertEquals` asserts content. Never use `times(1)` as a substitute for payload assertions.

Similarly, if buggy code emits two notifications for one order when only one is allowed, checking a single payload without controlling total count can miss duplicates. Verify across methods, call `verifyNoMoreInteractions` after verifying expected calls, or use a recording fake and compare the full list.

### 6.2. Multiple emissions: `getAllValues()`

Suppose a batch processes two orders and must emit **one event per order**. Inspect every payload rather than merely counting two calls:

```java
ArgumentCaptor<OrderCreatedEvent> captor =
        ArgumentCaptor.forClass(OrderCreatedEvent.class);

verify(publisher, times(2)).publish(captor.capture());

assertThat(captor.getAllValues()).containsExactlyInAnyOrder(
        expectedEventForFirstOrder,
        expectedEventForSecondOrder);
```

This **illustrative snippet applies to a batch service**, not the current single-order `CheckoutService.place`. It requires AssertJ static import `assertThat`, Mockito `verify`/`times`, and independently constructed `expectedEventForFirstOrder`/`expectedEventForSecondOrder` records.

- `getValue()` returns the **last captured value**, making it unsuitable for checking all events.
- `getAllValues()` returns a list of every argument captured across verified invocations.
- `containsExactlyInAnyOrder` verifies **exact element count, contents, and multiplicity**, independent of order.
- If the contract mandates event order, switch to `containsExactly`; never enforce order when only set equality is required.

### 6.3. Call order only when part of the contract

If the requirement says “**publish only after save succeeds**”, relative ordering across two ports can carry business meaning:

```java
InOrder sequence = inOrder(repository, publisher);
sequence.verify(repository).save(any(OrderDraft.class));
sequence.verify(publisher).publish(any(OrderCreatedEvent.class));
```

This is a **supplementary snippet** inside a test, requiring `org.mockito.InOrder` and static import `org.mockito.Mockito.inOrder`. It verifies relative ordering, while **still needing separate data assertions**. Never verify ordering of private helpers or internal steps simply because they happen to run in a given sequence today.

Even when save precedes publish in unit tests, real DB/broker coordination can diverge due to transactions, acks, or network failures. Guaranteeing reliable emission after commit may require a transactional outbox and integration tests. Mockito unit tests do not prove that.

## 7. Verifying Outbound Data Across Different Outbound Port Types

The same mindset applies across many Spring Boot adapters:

| Outbound port | Worthwhile data to assert | Common mistake |
| --- | --- | --- |
| `EmailSender` | To/CC, template ID, subject, body containing order ID/amount, locale | Only `verify(sender).send(any())` |
| `OrderEventPublisher` | Event type, aggregate ID, correlation ID, SKU, amount, currency | Counting publish without checking payload |
| `PaymentGateway` | Amount/currency, order reference, idempotency key, callback URL | Only asserting gateway was invoked |
| `InventoryClient` | SKU, requested quantity, warehouse, reservation ID | Using `anyString()`/`anyInt()` for every field |
| `Repository` | Entity/draft saved with exact owner, state, total | Only `verify(repository).save(any())` |
| `WebhookClient` | Target URL, HTTP method, headers, JSON body, signature/identifier | Only asserting request was “sent” |
| Business-contract `AuditLogger` | Actor/action/resource ID, outcome, policy metadata | Only asserting any log entry was written |

For sensitive values like tokens, passwords, or payment details, tests **must never use real secrets**. Use dummy fixtures and assert masking/hashing/minimal-field rules. Never print real secrets into failure logs or snapshots.

### 7.1. Multi-argument email example

Suppose an interface declares:

```java
void send(String recipient, String subject, String body);
```

To verify exact recipient and content:

```java
verify(emailSender).send(
        eq("buyer@example.test"),
        eq("Order 501 confirmed"),
        argThat(body -> body != null
                && body.contains("SKU-9")
                && body.contains("37.50")));
```

This **illustrates usage in another test**: `emailSender` is a Mockito mock, `send` belongs to a hypothetical interface, and static imports `eq`, `argThat` come from `org.mockito.ArgumentMatchers`. Use matchers for **all three arguments** in the verify call to avoid `InvalidUseOfMatchersException` from mixing matchers and raw values.

Choose exact string vs structural assertions per contract:

- Exact subject required → `eq(...)` makes sense.
- Body may vary in whitespace/locale/template formatting → assert stable invariants like order ID, total, recipient where appropriate.
- Body is JSON → parse into an object/JSON tree and assert values; avoid coupling to key order, whitespace, or indentation unless verbatim formatting is the contract.

### 7.2. Saving to a repository is also outbound data

When a service calls a repository to save, `verify(repository).save(any(OrderDraft.class))` misses entities with wrong owner, total, or status. Capturing `OrderRepository#save` in the sample project verifies:

```text
Expected draft:
OrderDraft(
  customerEmail = "buyer@example.test",
  sku           = "SKU-9",
  quantity      = 3,
  total         = 37.50)
```

Unit tests verify that the service **proposed saving the exact right data**. They **do not prove** the repository/ORM persisted it, the transaction committed, or queries read it back properly. To test real persistence, add `@DataJpaTest` or an integration test with the real database type; expected values should still be asserted against the business contract.

## 8. Avoiding Brittle or False-Green Outbound Assertions

### 8.1. Expected must not repeat actual's bugs

Wrong:

```java
service.place(command);

OrderCreatedEvent actual = captor.getValue();
OrderCreatedEvent expected = actual;

assertEquals(expected, actual);
```

This snippet even lacks `verify(publisher).publish(captor.capture())` before `getValue()`, which would fail with `No argument value was captured`. Even with verify added, `expected = actual` is a tautology: it never defines what the value ought to be.

Better: derive expected from **known inputs and business rules**, paired with a controlled ID from the stub repository:

```java
new OrderCreatedEvent(
        501L, "buyer@example.test", "SKU-9",
        3, new BigDecimal("37.50"), "USD");
```

This is an independent expected value; any wrong transformation causes a mismatch failure.

### 8.2. `any()` in verify is a counter, not a payload oracle

`any()` and `any(OrderCreatedEvent.class)` work well for stubbing repositories or when you genuinely only care that an interaction occurred. Using them for all side-effect verification leaves the core question untested: **did the outbound message carry the right content?**

Another weak anti-pattern adding a verify:

```java
verify(publisher).publish(any(OrderCreatedEvent.class));
assertNotNull(service.place(command));
```

Not only does it ignore payload contents, it invokes `service.place` **a second time** inside the assertion, causing an extra side effect that can break counts or confuse readers. Invoke the use case **once**, capture its return value, then assert response and interactions.

### 8.3. Asserting non-contract details

Payload tests turn brittle when pinned to:

- HashMap JSON key ordering when consumers do not require it.
- Nanosecond-precision timestamps generated from a real clock.
- Specific random UUIDs when the contract only asks for valid/unique IDs.
- Internal helper names or mapper/private method call counts.
- Exact whitespace across an entire email body when only template ID and business fields are specified.

When a contract specifies semantic data rather than byte-for-byte formatting, assert semantics instead of verbatim snapshots. Conversely, when downstream truly relies on **signature bytes**, canonical JSON, exact headers, or mandatory templates, those details **become the contract** and should be tested directly.

### 8.4. Records, mutable objects, and reference capture

`ArgumentCaptor` retains **a reference to the passed object**, without automatically deep-cloning it at invocation time. If a payload is mutable and the service mutates it **after** calling the publisher, the captor later sees the modified state rather than what crossed the boundary at call time.

Best solutions:

1. Use immutable DTOs/records for events.
2. Make defensive copies when crossing asynchronous boundaries.
3. When point-in-time capture is required, use a recording fake or Mockito `doAnswer` to snapshot fields immediately upon invocation.

Illustrative example with a hypothetical mutable DTO:

```java
List<String> snapshots = new ArrayList<>();

doAnswer(invocation -> {
    MutableMessage message = invocation.getArgument(0);
    snapshots.add(message.getBody());
    return null;
}).when(sender).send(any(MutableMessage.class));
```

This snippet is **not part of the runnable project in section 4**: `MutableMessage`/`sender` are illustrative types/variables requiring imports for `ArrayList`/`List` and Mockito `doAnswer`/`any`. It demonstrates snapshotting **values** at call time. Avoid complex `doAnswer` setups when records/immutable objects already prevent post-call mutation.

### 8.5. Dynamic timestamps and IDs

When an event contains `createdAt`, `eventId`, or `correlationId`, clarify the contract:

- **Must the exact value match a rule?** Inject a fixed `Clock` and controllable ID generator, then assert equality.
- **Must it merely be valid/non-empty?** Assert properties such as non-null, parseable UUID, or matching correlation ID.
- **Must it echo an upstream ID?** Supply a fixed upstream ID and assert the event forwards that exact value.
- **Must it be unique across emissions?** Test multiple invocations and assert distinctness rather than asserting a hardcoded UUID.

Never assert `Instant.now()` directly against another `Instant.now()`: timing drift causes flaky tests and fails to prove payload accuracy.

### 8.6. Asynchronous and reactive flows

When a service publishes inside `CompletableFuture`, Reactor, or listeners, an immediate `verify` can execute **before** the async task emits the message. Therefore:

- Supply a controllable executor/scheduler in unit tests so tasks complete deterministically.
- Await the completion stage or use proper async test utilities instead of fixed `Thread.sleep`.
- In Reactor, verify signals/results with `StepVerifier` where appropriate and ensure publishers are subscribed.
- For message brokers, use integration tests that consume and assert real payloads.

A test passing only because a mock was called on the test thread does not prove external delivery succeeded across a network boundary.

## 9. Failure Paths: Assert “Nothing Sent” and Proper State

Counting successful events is not enough. Branches that must stay silent are also part of the outbound contract.

| Scenario | Service expectation | How to verify |
| --- | --- | --- |
| Null command | Reject, neither save nor publish | `assertThrowsExactly` + `verifyNoInteractions` |
| Quantity 0 | Reject, neither save nor publish | Unit test in section 4 |
| Negative price | Reject, neither save nor publish | Input validation + no interactions |
| Repository throws exception | Propagate failure, do not publish | Stub exception + `verifyNoInteractions(publisher)` |
| Repository returns invalid ID | Do not publish bad event | Stub ID 0 + no publish |
| Save succeeds | Emit complete event once | Capture payload, assert record |
| Publisher throws error | Per contract: propagate/retry/queue | Assert exact error type and explicit policy |

In the sample service, if the publisher throws after the repository saved, the service propagates the exception. **That does not automatically roll back the save**. Unit tests with mocks cannot enforce atomicity between a database and a broker. Architectures requiring “never lose events after commit” often evaluate **transactional outbox**, idempotent retries, or dedicated delivery protocols, backed by integration tests covering transactions, outbox rows, and consumers.

An easily overlooked bug: `verifyNoInteractions` is only valid when enforcing an actual requirement. If a service is permitted to emit an audit event on validation failure, `verifyNoInteractions(allMocks)` would be overly strict. Distinguish **forbidden business outbound calls** from **permitted audit/logging calls**.

## 10. Which Test Double Fits: Mock, Stub, Spy, or Recording Fake?

| Type | Purpose | In this lesson |
| --- | --- | --- |
| **Stub** | Returns canned data to steer control flow | `when(repository.save(...)).thenReturn(new SavedOrder(501))` |
| **Mock** | Records and verifies interactions | `publisher` to capture events |
| **Spy** | Wraps a real object while allowing observation/partial stubbing | Use only when real behavior and observation are both truly needed |
| **Recording fake** | Simple implementation appending received events to a list | Lets you assert the full `sentEvents` list like output |

A clean alternative is replacing the mock publisher with a **recording fake**. It lets you compare the entire list of events and frames “outbound payload” clearly as observable output.

Runnable recording fake class if added at `src/test/java/com/example/outbound/RecordingPublisher.java`:

```java
// RecordingPublisher.java
package com.example.outbound;

import java.util.ArrayList;
import java.util.List;

final class RecordingPublisher implements OrderEventPublisher {
    private final List<OrderCreatedEvent> events = new ArrayList<>();

    @Override
    public void publish(OrderCreatedEvent event) {
        events.add(event);
    }

    List<OrderCreatedEvent> events() {
        return List.copyOf(events);
    }
}
```

You can add this test method to `CheckoutServiceTest` (inside the class, with JUnit `assertEquals` and Mockito `when` already imported):

```java
@Test
void recordingFakeExposesWholeOutboundEvent() {
    RecordingPublisher recording = new RecordingPublisher();
    OrderRepository stubRepository = draft -> new SavedOrder(501L);
    CheckoutService concreteService =
            new CheckoutService(stubRepository, recording);

    concreteService.place(validCommand());

    assertEquals(
            java.util.List.of(new OrderCreatedEvent(
                    501L, "buyer@example.test", "SKU-9",
                    3, new BigDecimal("37.50"), "USD")),
            recording.events());
}
```

This test uses no `@Mock publisher`; it inspects the recording fake—the **output list**—after invoking the service. Choosing mock/captor vs fake is a style choice; both assert payload accuracy effectively. A recording fake does not replace a real Kafka producer or SMTP server and does not verify serialization or out-of-process delivery.

## 11. Organizing Assertions by Boundary in Spring Boot Testing

**Unit tests (no Spring context):** Use Mockito/recording fakes to verify the service builds and passes the right commands/events/entities to dependencies. Fast and easy to pinpoint bugs. `CheckoutServiceTest` proves the service's transformation rules.

**Spring slice tests:** When testing controllers via `@WebMvcTest` with mocked services, assert HTTP request binding and JSON/status responses; that **does not prove** the real service emits accurate events. Test outbox or service logic with real classes or appropriate integration tests.

**Integration tests:** Run real adapters against network-boundary test doubles (such as an HTTP stub server) to assert serialized JSON, headers, queue topics, DB/outbox rows, and adapter mapping. While unit tests verify the record holds total 37.50, integration tests verify that exact record serializes into the right JSON/Avro message.

**E2E/system tests:** Send requests from an external client into the running application and observe real downstream/consumer state, keeping retries, duplicate delivery, and eventual consistency in mind.

Boundary diagram:

```text
                     UNIT TEST
PlaceOrderCommand ──► CheckoutService (REAL)
                           │
             ┌─────────────┴────────────────┐
             ▼                              ▼
      OrderRepository MOCK          OrderEventPublisher MOCK
      capture OrderDraft            capture OrderCreatedEvent
             │                              │
       assert draft fields           assert event fields
             │                              │
             └─────────────┬────────────────┘
                           ▼
                 assert OrderReceipt

                INTEGRATION TEST
CheckoutService ──► repository adapter ──► test DB
               └──► publisher adapter  ──► broker/HTTP fake or real
                           │
               assert saved row and serialized message
```

Never conclude “the event reached Kafka” solely from `verify(publisher).publish(...)` on a Mockito mock. Every test level proves its corresponding boundary.

## 12. Mutation Thinking: Testing Your Tests with Deliberate Wrong Changes

After writing tests, ask: **“If production code sent wrong data, which assertion would turn red?”** You can test deliberate wrong edits on a temporary branch and revert:

| Hypothetical service bug | `times(1) + any()` | Content assertions |
| --- | --- | --- |
| Sends untrimmed recipient email | Can still pass | Fails: expected email mismatches |
| Changes quantity `3` to `1` | Can still pass | Fails: wrong quantity |
| Sends total `0.00` | Can still pass | Fails: wrong total |
| Uses ID `0` instead of `501` | Can still pass | Fails: wrong orderId |
| Sends `EUR` instead of `USD` | Can still pass | Fails: wrong currency |
| Emits no event | Fails | Fails |
| Emits two events | May fail if verify counts **all** matching calls | Fails when enforcing exactly one event |
| Does not publish on repository error | `verifyNoInteractions` catches it | Negative contract protected |

You do not need a mutation-testing framework to apply this mindset. For logic-heavy modules, tools like PIT help find weak assertions, though mutation scores should be interpreted against real contracts because not every generated mutant corresponds to a meaningful business bug.

**Minimal sanity check:** if changing `"USD"` to `"EUR"` in production code leaves call-counting tests green, your tests fail to protect currency. When expected payloads are asserted independently, that mutation fails.

## 13. Common Mockito Mistakes

### Mistake A. Re-testing your own stubbing

```java
when(repository.save(any())).thenReturn(new SavedOrder(501L));
assertEquals(new SavedOrder(501L),
        repository.save(new OrderDraft(
                "buyer@example.test", "SKU-9", 3,
                new BigDecimal("37.50"))));
```

This snippet only verifies the mock returns what was stubbed, **never calling the service**; it tests nothing about the use case. Stub dependencies to steer upstream inputs, **call the service**, then verify outbound payloads and return values.

### Mistake B. Putting captors inside `when(...)`

Mockito recommends capturing during **verification**, because if the method is never called, the failure fires cleanly at verify and is easy to diagnose. Never put `captor.capture()` inside stubbing conditions and expect it to replace outbound assertions.

### Mistake C. Mixing matchers and raw arguments

```java
// Wrong if using matcher for one parameter while leaving another raw:
verify(sender).send(eq("buyer@example.test"), "Subject", anyString());

// Right: use matchers for all parameters in this invocation:
verify(sender).send(
        eq("buyer@example.test"),
        eq("Subject"),
        anyString());
```

This snippet illustrates usage with a hypothetical `send(String,String,String)` method. If not using matchers, pass all three expected values for direct value comparison.

### Mistake D. Asserting captured values without context

An event with the right amount yet wrong orderId or recipient is still a broken event. Never assert just one “easy-to-pass” field. Cover the fields consumers use for decisions alongside key business invariants.

### Mistake E. Over-verifying every internal detail

When the requirement is solely emitting the right `OrderCreatedEvent`, avoid verifying how many times a formatter/private mapper ran or inconsequential internal step ordering. Tests should survive valid refactoring without rewriting expectations.

### Mistake F. Ignoring extra invocations

`verify(publisher).publish(expectedEvent)` can pass even when an extra event is also emitted. When the contract requires strictly one event, check **all outbound calls** using captor/`getAllValues()` or `verifyNoMoreInteractions` after verified invocations.

### Mistake G. Failing to await async completion

When publishing is scheduled asynchronously, verifying immediately causes random failures. Control completion or use proper condition-waiting utilities rather than arbitrary sleeps.

## 14. How to Run and What to Expect

Inside the `outbound-payload-test` directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn test
mvn -Dtest=CheckoutServiceTest test
```

In the sample project before adding the optional `RecordingPublisher` test, `CheckoutServiceTest` has **4 `@Test` methods**. With the recording-fake method from section 10 added, there are **5 methods**. Maven typically prints `BUILD SUCCESS` when all assertions pass; task counts, timings, and log formatting have no fixed stdout string. This example contains no `System.out.println`.

To inspect outcomes, check Surefire reports in `target/surefire-reports/` for executed, skipped, and failed counts. **Never cite a “build success” line as proof of accurate payloads if tests only use `any()`/`times(1)`.** Assertions and expected values determine what a suite proves.

To confirm wrong outbound data is actually caught, temporarily mutate the currency string in `CheckoutService` (on a working branch, then revert):

```java
// Valid line in the example code:
publisher.publish(new OrderCreatedEvent(
        saved.id(), email, sku,
        command.quantity(), total, "USD"));

// Deliberate bad mutation test:
publisher.publish(new OrderCreatedEvent(
        saved.id(), email, sku,
        command.quantity(), total, "EUR"));
```

Running `sendsCorrectBusinessPayloadAfterSaving` must fail at the event comparison. Both snippets above are solely for illustrating assertion validation; **never leave broken code in the application**.

## 15. Code Review Checklist

- [ ] **Outbound boundaries** are clearly identified (repository, publisher, email, HTTP, audit, payment).
- [ ] Tests invoke the **real unit**; they do not merely call mocks/stubs and assert stubbed values.
- [ ] Expected values derive independently from business rules and test fixtures.
- [ ] Key contract fields are asserted: recipient, ID, amount, currency, quantity, status, correlation key.
- [ ] Trim/normalize/map/round transformations have concrete examples with independent expected values.
- [ ] When the contract specifies one event, **strictly one event** is enforced so extra calls cannot slip through.
- [ ] When multiple events occur, `getAllValues()` checks the full set or sequence as required.
- [ ] When emission is forbidden on invalid/failure paths, **no side effects** are verified.
- [ ] Tests are not coupled to random IDs/timestamps or non-contract ordering.
- [ ] Immutable events are preferred; `ArgumentCaptor` reference behavior on mutable objects is understood.
- [ ] Async flows await and observe completion properly.
- [ ] “Mock was called” is distinguished from “real adapter serialized/delivered message or DB committed”.
- [ ] You can name at least one wrong outbound field value that causes the test to fail.

## 16. Self-Assessment Questions

**1.** Does `verify(emailSender, times(1)).send(any())` prove an email was sent to the right address?  
**Answer:** No. It proves only that one matching invocation happened; assert the recipient (and essential content).

**2.** When is `verifyNoInteractions(publisher)` alone sufficient?  
**Answer:** When the behavior to protect is **sending nothing at all** on a specific branch, such as invalid input. If the service uses multiple collaborators and only the publisher is forbidden, verify only the publisher.

**3.** Is `verify(publisher).publish(new OrderCreatedEvent(...))` sensible?  
**Answer:** Yes, when the event is a record/value object with proper equality and independent expected data. Guard against extra invocations if the contract allows only one event in total.

**4.** Is a test checking total 37.50 without checking currency sufficient?  
**Answer:** No, if consumers depend on currency; 37.50 USD and 37.50 EUR have completely different meanings.

**5.** How do `ArgumentCaptor#getValue()` and `getAllValues()` differ?  
**Answer:** `getValue()` retrieves the last captured argument; `getAllValues()` returns a list of all captured arguments for verifying multiple invocations.

**6.** Why can't you claim Kafka received a message based solely on Mockito `verify`?  
**Answer:** Mocks only record calls at the unit boundary; they do not run producer serialization, networking, broker acknowledgements, or consumers. Integration/system tests cover that.

**7.** Why are immutable payloads helpful?  
**Answer:** Events cannot be modified after invocation, keeping captured arguments and communication contracts stable and avoiding false observations on mutable objects.

**8.** If a repository throws an exception, what should be asserted?  
**Answer:** Contract-compliant error handling and **no event published**; in the example, `assertThrowsExactly` + `verifyNoInteractions(publisher)`.

## 17. References

- Mockito – `ArgumentCaptor`: https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/ArgumentCaptor.html
- Mockito – verification and matchers: https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/Mockito.html
- JUnit 5 User Guide – Writing tests/Assertions: https://junit.org/junit5/docs/current/user-guide/
- Spring Boot 3.5 – Testing: https://docs.spring.io/spring-boot/3.5/reference/testing/index.html
- AssertJ Core Documentation: https://assertj.github.io/doc/

**Key takeaway:** never stop at “called once”. For outbound side effects, tests must prove **what data left the unit, whether that data is business-accurate, and under which scenarios nothing may be sent**. When proving messages actually reached external systems, add integration tests at the corresponding boundary, because unit tests with mocks only observe method calls.