# Choosing Test Doubles at the Right Boundary Instead of Mocking the Entire Business Chain

In a Spring Boot application, a request can flow through a controller, application service, domain policy, repository, HTTP client, and message broker. Mockito makes it easy to mock almost anything, yet **being able to mock does not mean you should**. If a test replaces every participant with `when(...).thenReturn(...)`, it can pass even when pricing math, guard checks, state decisions, and real business coordination are completely broken.

Central principle of this lesson:

> **Keep the logic you intend to prove real; introduce test doubles at boundaries where the test does not need—or cannot safely, quickly, and deterministically run—the real component.**

That boundary is usually an **outbound port** (payment gateway, email sender, clock, repository, HTTP client, message producer), not every method along the call chain. Conversely, when testing only a controller's HTTP contract, mocking the application service at the **MVC slice boundary** makes complete sense. The exact same object can be the **SUT** (*system under test*) in one test and an out-of-scope dependency in another.

This lesson progresses from concepts and decision matrices to runnable examples in Java 17+, JUnit Jupiter 5, Mockito, and Spring Boot 3.4+/Spring Framework 6.2+; covering real checkout logic with a fake payment gateway, Spring bean overrides, MVC slices, design flaws, and code review practices.

## 1. What will you learn?

You will be able to:

- Explain the differences between **SUT, collaborator, inbound boundary, and outbound boundary**.
- Distinguish **dummy, stub, fake, mock, and spy** and choose based on practical need.
- Show why mocking policies, services, and repositories while asserting fake inputs yields low-value tests.
- Write **unit tests running real domain and orchestration logic**, doubling only out-of-scope communication.
- Combine **state assertions** (values, records, state) with intentional **interaction assertions**.
- Use `@MockitoBean` to replace beans at the right scope in Spring TestContext without confusing it with Mockito's `@Mock`.
- Contrast mocking a service in `@WebMvcTest` with mocking the service itself in a test claiming to verify business logic.
- Decide when an in-memory fake suffices and when a real database/HTTP/broker integration or contract test is required.
- Spot risks when bean overrides bypass AOP, fragment context caches, or let test doubles drift from real contracts.

## 2. What is the SUT, and what does "the right boundary" mean?

The **SUT** is the part of the system a test **is responsible for proving correct**. It may be a class, a group of classes, an endpoint, or a broader workflow. **Collaborators** are what the SUT calls to get its job done.

Checkout example:

```text
                         HTTP request
                              |
                              v
                     CheckoutController
                         (inbound)
                              |
                              v
                      CheckoutService
                      /       |      \
                     v        v       v
                 Catalog   DiscountPolicy    ... business rules
                    \         /
                     v       v
                    amount + discount
                              |
                  +-----------+-----------+
                  |                       |
                  v                       v
             PaymentGateway             OrderStore
             (outbound port)            (outbound port)
                  |                       |
                  v                       v
           external payment API     SQL / persistence adapter
```

If the goal is "members receive a 10% discount, the exact net amount is sent to the payment gateway, and a receipt is saved after successful charge," then **Catalog, DiscountPolicy, and CheckoutService are the real logic that must run**. `PaymentGateway` can be a mock; `OrderStore` can be an in-memory fake if the test is not verifying SQL.

If the goal is "HTTP POST parses JSON into `CheckoutCommand` and returns HTTP 200 with the expected JSON," the controller/MVC layer is the SUT. Inside `@WebMvcTest`, `CheckoutService` can be mocked because domain math lies outside the HTTP mapping test's scope. Separate service tests still protect the real calculations.

**No single boundary fits every test.** Boundaries follow the **contract the test commits to protecting**. That is why writing "This test must fail if ..." before choosing what to mock is so effective.

## 3. Five test double types and their actual purposes

A test double stands in for a collaborator during testing. Common terms:

| Kind | Meaning | Good fit | Risk if overused |
|---|---|---|---|
| **Dummy** | Object passed merely to satisfy a parameter list; never used by the test | Constructor demands an unrelated dependency for this test case | Hides bloated classes taking too many dependencies |
| **Stub** | Supplies canned return values for specific calls | HTTP client returning fixed payload; external FX policy returning one rate | Overly "happy" stub values fail to cover edge variants |
| **Fake** | Working simplified implementation, typically in memory | In-memory order store, fake clock, fake message sink | Fails to reproduce real transactions, constraints, and concurrency |
| **Mock** | Programmable double supporting stubbing and call verification | `PaymentGateway`: checking charged amount and call count | Locks tests to interaction minutiae instead of valuable outcomes |
| **Spy** | Wraps an object with real logic, selectively overriding/observing | Legacy code lacking seams where certain real methods must stay | Unstubbed methods run for real, causing side effects and brittle tests |

In Mockito, the word `mock` typically refers to any object created by `Mockito.mock`, even when used strictly as a **stub** returning values. Distinguishing conceptual test-double roles does not require separate library classes for each.

A single test might combine them:

```java
PaymentGateway payment = mock(PaymentGateway.class); // Mockito mock
when(payment.charge(216_000L)).thenReturn("tx-001"); // Stubbing
verify(payment).charge(216_000L);                    // Interaction assertion
```

This is an **illustrative snippet**; `PaymentGateway` is defined completely in the example section. Only use `mock` and `verify` to guard interactions that genuinely belong to the requirement.

## 4. Why mocking the entire business chain is an anti-pattern

Look at this "test":

```java
// COUNTER-EXAMPLE: only asserts what the mock itself was told to return.
CheckoutService service = mock(CheckoutService.class);

CheckoutCommand command = new CheckoutCommand("BOOK", 2, true);
CheckoutReceipt expected = new CheckoutReceipt(
        "BOOK", 2, 240_000L, 24_000L, 216_000L, "tx-001");

when(service.checkout(command)).thenReturn(expected);

assertEquals(expected, service.checkout(command));
```

This test **never executes the real `CheckoutService.checkout`**. Even if the real implementation stops summing prices, drops discounts, forgets to save receipts, or always throws, this test stays green because it instructed Mockito to return `expected`.

A subtler variation:

```java
// COUNTER-EXAMPLE when testing discount rules:
// Catalog, DiscountPolicy, PaymentGateway, and OrderStore
// are all mocked; every business result is pre-decided by the test.
when(catalog.unitPriceVnd("BOOK")).thenReturn(120_000L);
when(discountPolicy.discountVnd(240_000L, true))
        .thenReturn(24_000L);
when(paymentGateway.charge(216_000L)).thenReturn("tx-001");
```

This is an **illustrative excerpt** with undeclared variables rather than a standalone test. If the SUT is `CheckoutService`, this runs the service's orchestration yet **skips the real discount rules**. Changing the policy to a 5% discount leaves the test passing because 24,000 was hardcoded by the test. Only if **orchestration** (call counts and order across collaborators) is the sole target does such a test match its narrow scope.

**Three signals of a low-value test:**

1. The test claims to verify pricing, yet hardcodes calculated amounts inside `when(discountPolicy...).thenReturn(...)`.
2. The only assertion compares outputs directly against data the test itself fed into mocks.
3. Safe refactors—merging two helpers, renaming a mapper, or adjusting internal layering—break the test even though business behavior never changed.

Good tests **do not forbid mocks**; they place mocks where **controlling the external world** is needed so critical business decisions still run for real.

## 5. Choosing doubles by layer: checkout application example

| Layer | In checkout logic tests | In MVC slice tests | In persistence integration tests |
|---|---|---|---|
| `CheckoutController` | Not needed | **Real** | Usually unnecessary when testing repositories only |
| `CheckoutService` | **Real** | Can be mocked | Can be real if testing end-to-end flow |
| `Catalog` | **Real**, when pricing rules are under test | Not needed | Real or explicit fixture |
| `DiscountPolicy` | **Real** | Not needed | Real if queries/transactions involve it |
| `PaymentGateway` | Mock/fake at outbound boundary | Not needed when service is mocked | Fake/mock or separate sandbox/contract test |
| `OrderStore` | In-memory fake when SQL is out of scope | Not needed | **Real DB adapter** and suitable test DB |
| Spring bean wiring | Usually unnecessary | MVC context only | Real when wiring is part of the target |
| Real infrastructure calls | No | No | Only the exact infrastructure the test protects |

**Risk-driven** decisions matter equally:

- Wrong totals or discounts lose money: run the real policy, checking edge cases and outputs.
- Real payment gateways charge real cards: never call them in unit tests; mock at the outbound interface.
- SQL queries can fail even when fake stores pass: write dedicated tests against a real DB rather than substituting fakes for all DB tests.
- JSON mapping or HTTP validation can break even when services pass: add MVC slice tests or HTTP integration tests.
- Spring AOP transactions, retries, caching, and security can be skipped by mocks: verify them at proper integration boundaries.

## 6. Designing ports and adapters so replacement happens cleanly

Code organization stays straightforward when separated into:

- **Domain rules / policies**: pricing formulas, discounts, order preconditions, state transitions.
- **Application services**: orchestrating a use case and calling required ports.
- **Outbound ports**: interfaces expressing what the domain needs, e.g., `PaymentGateway.charge(amount)` or `OrderStore.save(receipt)`.
- **Outbound adapters**: implementations talking to HTTP, databases, brokers, or email.
- **Inbound adapters**: controllers, REST endpoints, message handlers, or scheduled jobs.

Dependency graph:

```text
CheckoutService --> Catalog (real domain logic)
                --> DiscountPolicy (real domain logic)
                --> PaymentGateway [interface] --> HTTP adapter (outside unit test)
                --> OrderStore [interface] ----> SQL adapter (outside unit test)

Unit test:
  new CheckoutService(real Catalog, real DiscountPolicy,
                      mock PaymentGateway, fake OrderStore)

Spring integration test:
  Spring creates real CheckoutService/Catalog/DiscountPolicy
  and replaces PaymentGateway bean only
```

**Why do interfaces help here?** The service remains unaware of URLs, JDBC, Spring HTTP clients, or messaging protocols. Tests can swap adapters without touching business logic. Still, **never create interfaces for every class automatically**: for pure domain classes free of external infrastructure, testing the concrete implementation directly is clearer.

## 7. Complete Java 17+ example: real checkout business logic, doubles at the right boundaries

The runnable example fits a **Spring Boot 3.4+/Spring Framework 6.2+**, Java 17+, JUnit Jupiter 5, and Mockito project; most **unit tests require no Spring context**. It models:

- `Catalog` prices `BOOK` at 120,000 VND and `PEN` at 20,000 VND.
- Members get 10% off the subtotal; for simplicity, all amounts use **`long` integers in VND**, rounding discounts down via integer division when not divisible by 10. This is a **demo rule**, not universal financial rounding advice.
- The service rejects non-positive quantities or unknown SKUs **before calling payment**.
- `PaymentGateway` returns a transaction reference; only **after a successful charge** does the service persist the receipt via `OrderStore`.
- If payment throws, the service saves no receipt. Production systems must also handle idempotency, retries, and uncertain network outcomes; this simple test does not prove atomicity between gateway and database.

### 7.1. File layout

```text
src/main/java/com/example/checkout/
    CheckoutDemoApplication.java
    CheckoutCommand.java
    CheckoutReceipt.java
    Catalog.java
    DiscountPolicy.java
    PaymentGateway.java
    DemoPaymentGateway.java
    OrderStore.java
    InMemoryOrderStore.java
    CheckoutService.java
    CheckoutController.java

src/test/java/com/example/checkout/
    CheckoutServiceUnitTest.java
    CheckoutSpringBoundaryTest.java
    CheckoutControllerSliceTest.java
```

Main files live in package `com.example.checkout`. `DemoPaymentGateway` is a **safe demo-only bean placeholder**: it intentionally throws rather than making network calls and should never be mistaken for a production adapter.

### 7.2. Boot application

**`src/main/java/com/example/checkout/CheckoutDemoApplication.java`**

```java
package com.example.checkout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CheckoutDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CheckoutDemoApplication.class, args);
    }
}
```

### 7.3. Use-case input and output

**`src/main/java/com/example/checkout/CheckoutCommand.java`**

```java
package com.example.checkout;

public record CheckoutCommand(
        String sku,
        int quantity,
        boolean member) {
}
```

**`src/main/java/com/example/checkout/CheckoutReceipt.java`**

```java
package com.example.checkout;

public record CheckoutReceipt(
        String sku,
        int quantity,
        long subtotalVnd,
        long discountVnd,
        long totalVnd,
        String paymentReference) {
}
```

These `record`s generate `equals`, `hashCode`, and component accessors, simplifying value assertions in unit tests. Choosing `long` keeps demo math transparent; production systems should define explicit money types, currencies, bounds, and domain rounding rules.

### 7.4. Real catalog and discount logic

**`src/main/java/com/example/checkout/Catalog.java`**

```java
package com.example.checkout;

import org.springframework.stereotype.Component;

@Component
public class Catalog {

    public long unitPriceVnd(String sku) {
        if (sku == null) {
            throw new IllegalArgumentException("sku is required");
        }
        return switch (sku) {
            case "BOOK" -> 120_000L;
            case "PEN" -> 20_000L;
            default -> throw new IllegalArgumentException(
                    "unknown sku: " + sku);
        };
    }
}
```

**`src/main/java/com/example/checkout/DiscountPolicy.java`**

```java
package com.example.checkout;

import org.springframework.stereotype.Component;

@Component
public class DiscountPolicy {

    public long discountVnd(long subtotalVnd, boolean member) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException(
                    "subtotal must not be negative");
        }
        return member ? subtotalVnd / 10 : 0L;
    }
}
```

Both classes hold **real business rules**: price lookup, SKU validation, and discount percentage. Do not mock either class in pricing tests. If the discount breaks from 10% to 5%, monetary assertions must turn **red**.

### 7.5. Two outbound ports and illustrative adapters

**`src/main/java/com/example/checkout/PaymentGateway.java`**

```java
package com.example.checkout;

public interface PaymentGateway {
    String charge(long amountVnd);
}
```

**`src/main/java/com/example/checkout/OrderStore.java`**

```java
package com.example.checkout;

public interface OrderStore {
    void save(CheckoutReceipt receipt);
}
```

**`src/main/java/com/example/checkout/DemoPaymentGateway.java`**

```java
package com.example.checkout;

import org.springframework.stereotype.Component;

@Component
public class DemoPaymentGateway implements PaymentGateway {

    @Override
    public String charge(long amountVnd) {
        throw new IllegalStateException(
                "Demo adapter: no real payment gateway configured");
    }
}
```

This adapter **intentionally avoids network calls**. It exists so Boot registers a real `PaymentGateway` bean, letting tests demonstrate **replacing an existing bean** via `@MockitoBean`. Real deployments must substitute an actual sandbox/production payment adapter with proper config, timeouts, security, idempotency, and observability.

**`src/main/java/com/example/checkout/InMemoryOrderStore.java`**

```java
package com.example.checkout;

import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class InMemoryOrderStore implements OrderStore {
    private final List<CheckoutReceipt> saved = new ArrayList<>();

    @Override
    public void save(CheckoutReceipt receipt) {
        saved.add(receipt);
    }

    public List<CheckoutReceipt> receipts() {
        return List.copyOf(saved);
    }
}
```

This is a simple **fake persistence** component. It implements real `save` and `receipts` behavior so tests can assert saved records. Yet a fake **cannot prove** JPA mappings, unique constraints, indexes, transactions, locks, or SQL accuracy. Database tests must run against a real adapter and suitable test DB at another level.

In this example, `InMemoryOrderStore` is marked as a Spring component purely for demo convenience. Production apps should use a real repository adapter and register fakes only in test scope or dedicated profiles.

### 7.6. Application service: real logic to protect

**`src/main/java/com/example/checkout/CheckoutService.java`**

```java
package com.example.checkout;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final Catalog catalog;
    private final DiscountPolicy discountPolicy;
    private final PaymentGateway paymentGateway;
    private final OrderStore store;

    public CheckoutService(
            Catalog catalog,
            DiscountPolicy discountPolicy,
            PaymentGateway paymentGateway,
            OrderStore store) {
        this.catalog = catalog;
        this.discountPolicy = discountPolicy;
        this.paymentGateway = paymentGateway;
        this.store = store;
    }

    public CheckoutReceipt checkout(CheckoutCommand command) {
        if (command == null) {
            throw new IllegalArgumentException("command is required");
        }
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }

        long unitPrice = catalog.unitPriceVnd(command.sku());
        long subtotal = Math.multiplyExact(
                unitPrice, command.quantity());
        long discount = discountPolicy.discountVnd(
                subtotal, command.member());
        long total = Math.subtractExact(subtotal, discount);

        String paymentReference = paymentGateway.charge(total);
        CheckoutReceipt receipt = new CheckoutReceipt(
                command.sku(),
                command.quantity(),
                subtotal,
                discount,
                total,
                paymentReference);

        store.save(receipt);
        return receipt;
    }
}
```

Notice the **boundary split**: every pricing calculation executes real Java code. `PaymentGateway` and `OrderStore` are the two external ports we can double. When `charge` throws, `store.save` is never called because saving occurs after charging in the real flow.

`Math.multiplyExact` and `Math.subtractExact` help tests catch integer overflow via `ArithmeticException` rather than silent wraparound. Real products still need explicit monetary caps, handling for charged-but-unsaved states, and idempotency.

### 7.7. Controller for the MVC slice example

**`src/main/java/com/example/checkout/CheckoutController.java`**

```java
package com.example.checkout;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/checkouts")
public class CheckoutController {
    private final CheckoutService service;

    public CheckoutController(CheckoutService service) {
        this.service = service;
    }

    @PostMapping
    public CheckoutReceipt checkout(
            @RequestBody CheckoutCommand command) {
        return service.checkout(command);
    }
}
```

This controller simply deserializes JSON, calls the application service, and returns the result; security, bean validation annotations, exception mapping, and HTTP 201 are omitted for brevity. Real production APIs must cover those explicit HTTP contracts in tests.

## 8. The most important unit test: mock payment, fake store, real business logic

**`src/test/java/com/example/checkout/CheckoutServiceUnitTest.java`**

```java
package com.example.checkout;

import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class CheckoutServiceUnitTest {

    @Test
    void calculatesRealRulesBeforeChargingAndSaving() {
        PaymentGateway paymentGateway = mock(PaymentGateway.class);
        InMemoryOrderStore store = new InMemoryOrderStore();

        CheckoutService service = new CheckoutService(
                new Catalog(),
                new DiscountPolicy(),
                paymentGateway,
                store);

        when(paymentGateway.charge(216_000L))
                .thenReturn("tx-001");

        CheckoutReceipt receipt = service.checkout(
                new CheckoutCommand("BOOK", 2, true));

        assertAll("real checkout result",
                () -> assertEquals("BOOK", receipt.sku()),
                () -> assertEquals(2, receipt.quantity()),
                () -> assertEquals(240_000L, receipt.subtotalVnd()),
                () -> assertEquals(24_000L, receipt.discountVnd()),
                () -> assertEquals(216_000L, receipt.totalVnd()),
                () -> assertEquals("tx-001",
                        receipt.paymentReference()));

        assertEquals(List.of(receipt), store.receipts());
        verify(paymentGateway).charge(216_000L);
    }

    @Test
    void rejectsUnknownSkuBeforeExternalCharge() {
        PaymentGateway paymentGateway = mock(PaymentGateway.class);
        InMemoryOrderStore store = new InMemoryOrderStore();

        CheckoutService service = new CheckoutService(
                new Catalog(),
                new DiscountPolicy(),
                paymentGateway,
                store);

        assertThrows(IllegalArgumentException.class,
                () -> service.checkout(
                        new CheckoutCommand("MISSING", 2, false)));

        verifyNoInteractions(paymentGateway);
        assertTrue(store.receipts().isEmpty());
    }

    @Test
    void paymentFailureDoesNotSaveReceipt() {
        PaymentGateway paymentGateway = mock(PaymentGateway.class);
        InMemoryOrderStore store = new InMemoryOrderStore();

        CheckoutService service = new CheckoutService(
                new Catalog(),
                new DiscountPolicy(),
                paymentGateway,
                store);

        doThrow(new IllegalStateException("declined"))
                .when(paymentGateway).charge(216_000L);

        assertThrows(IllegalStateException.class,
                () -> service.checkout(
                        new CheckoutCommand("BOOK", 2, true)));

        verify(paymentGateway).charge(216_000L);
        assertTrue(store.receipts().isEmpty());
    }
}
```

**This is the heart of the lesson.**

- `new Catalog()` and `new DiscountPolicy()` are **real implementations**. Changing pricing or discount logic changes outputs and gets caught by the tests.
- `PaymentGateway` is a **mocked outbound port**. The unit test charges no real money while verifying the exact amount crossing the boundary.
- `InMemoryOrderStore` is a **fake**. We assert the saved record contains the right fields without needing JPA, transactions, or a DB server.
- `assertAll` groups related assertions on the receipt; `verify` confirms `charge(216_000L)` ran **once** in the success case.
- The unknown-SKU test verifies failure happens **before hitting the external boundary**.
- The gateway-failure test confirms no receipt is saved after payment fails.

**Why not mock `CheckoutService`?** It is the SUT—it must execute for tests to catch bugs. **Why not mock `DiscountPolicy`?** Because discounts are a committed rule that executes quickly and deterministically. **Why mock payment?** Because charging is an external side effect outside calculation verification and unsafe to execute live in unit tests.

### 8.1. What does this test still leave unproven?

It does not prove:

- HTTP request/response mapping works.
- Spring beans are scanned and wired properly.
- The real payment adapter handles live APIs, timeouts, retries, signatures, and idempotency.
- The SQL/JPA store commits or rolls back properly.
- Charging and saving are atomic; external gateways do not join database transactions.

Those gaps are **reasons to add tests at subsequent boundaries**, not reasons to mock everything together.

## 9. When to verify interactions vs. assert state?

Two common observation styles exist.

**State/result assertions** check meaningful outputs or state:

```java
assertEquals(216_000L, receipt.totalVnd());
assertEquals(List.of(receipt), store.receipts());
```

**Interaction assertions** check calls made to collaborators:

```java
verify(paymentGateway).charge(216_000L);
```

Here, the payment gateway is an outbound boundary where charging **once** matters, so `verify` earns its keep. By contrast, verifying every internal call:

```java
// COUNTER-EXAMPLE: test couples to call graph rather than contract.
verify(catalog).unitPriceVnd("BOOK");
verify(discountPolicy).discountVnd(240_000L, true);
verify(mapper).toReceipt(any());
verify(auditHelper).buildText(any());
```

breaks easily when refactoring (variables above are illustrative and undeclared), even when responses and side effects remain identical. Moreover, `Catalog`, `DiscountPolicy`, and mappers in our real design are **real objects**, not mocks to verify. Replacing them with mocks solely to verify helper calls couples tests to implementation details.

**Decision rule:** if calling a collaborator with specific counts/arguments is an **important contract** (no double charges, no emails on failure, publish events after commit), verify it. If it is merely an internal calculation step, assert the final output and key side effects.

Never call `verifyNoMoreInteractions(...)` out of habit in every test: it breaks tests whenever a harmless query is added. Use it only when **emitting no extra calls/effects** is a real invariant to protect.

## 10. Mock vs. fake on an outbound port: which to pick?

For `OrderStore` in unit tests, both options work:

1. **Mock `OrderStore`:** `verify(store).save(expectedReceipt)`. Concise when you only guard the save call or when the store interface is complex.
2. **Fake `OrderStore`:** use an in-memory implementation and inspect `store.receipts()`. Helpful for simulating basic read/write sequences and multi-step flows.

Choose a fake when the double's behavior stays small and easy to maintain. **Never hand-build a mock database** replicating transactions, locks, filtering, pagination, and SQL when your goal already requires DB semantics. Whenever correctness depends on SQL or JPA mappings, test against a real database with fixtures and cleanup.

For `PaymentGateway`, a mock returning `"tx-001"` suffices for unit tests. When domain logic must handle slow networks or complex error codes, a richer fake or HTTP stub server helps, paired with contract/integration tests verifying the adapter against real protocols.

**Fakes can still have bugs:** a test passing against a semantically inaccurate fake masks production failures. Keep fakes faithful to the **essential contract** and simple; never trust them to mimic all production behavior.

## 11. Scoped bean replacement with Spring TestContext

A plain Java Mockito mock:

```java
PaymentGateway gateway = mock(PaymentGateway.class);
```

creates an object only inside the test method. It **does not replace** the `PaymentGateway` bean injected into `CheckoutService` from `ApplicationContext`. In `@SpringBootTest`, merely declaring a `@Mock`/`mock(...)` field leaves the Spring-managed service holding the real bean.

To verify Spring wiring while keeping domain services real, use Spring Framework **6.2+** **`@MockitoBean`** to replace a single bean. Spring Boot **3.4+/3.5** manages a Spring Framework version supporting it; in Spring Boot **3.3 and earlier**, Boot's `@MockBean` was standard (deprecated since 3.4 and discouraged for new projects).

**Comparing mechanisms:**

| Mechanism | Replaces bean in Spring context? | When to use |
|---|---|---|
| `Mockito.mock(...)` | No | Unit tests instantiating SUT via constructor |
| `@Mock` + `MockitoExtension` | No | Auto-initializing mocks injected into unit-test SUTs |
| `@MockitoBean` | Yes | Spring context tests replacing a dependency bean with a Mockito mock |
| `@MockitoSpyBean` | Wraps real bean | Special partial-mock cases; watch AOP/side effects |
| `@TestConfiguration` + `@Import` | Registers test beans via config | Real test fakes/adapters rather than interactive mocks |
| `@TestBean` (Spring TestContext) | Yes | Factory-method overrides supplying a concrete implementation |
| Legacy Spring Boot `@MockBean` | Yes, in supported Boot versions | Pre-3.4 Boot projects or migration phases |

Never use `@Primary` or `spring.main.allow-bean-definition-overriding=true` as a "trick" to push tests past duplicate bean errors. Each alters bean registration differently and masks broken configuration. When overriding is truly needed, use the official mechanism and let missing/ambiguous bean errors surface.

### 11.1. Distinguishing `REPLACE` and `REPLACE_OR_CREATE`

Spring Framework's `@MockitoBean` defaults to **`REPLACE_OR_CREATE`**: it replaces a matching bean if found, or creates a new mock if none exists. For tests meant to prove **the bean already exists and gets replaced**, write:

```java
@MockitoBean(enforceOverride = true)
PaymentGateway gateway;
```

`enforceOverride = true` requires **`REPLACE`** and fails if no matching target bean exists. It prevents false passes when production configuration actually forgot to register the dependency.

When an MVC slice intentionally **omits the real `CheckoutService`**, default `@MockitoBean` makes sense to supply a mocked collaborator for the controller. Creating a new mock bean there is by design.

**Note:** bean overrides resolve targets by type/name/qualifier. When multiple same-type beans exist, supply `@Qualifier` or an explicit name; never assume the framework guesses the right adapter.

## 12. Spring Boot example: replacing only `PaymentGateway`, keeping the service real

This test verifies `ApplicationContext` builds `Catalog`, `DiscountPolicy`, and `CheckoutService`, while **replacing only `PaymentGateway`**. No real demo gateway runs, and no network opens.

**`src/test/java/com/example/checkout/CheckoutSpringBoundaryTest.java`**

```java
package com.example.checkout;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest(
        classes = CheckoutDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class CheckoutSpringBoundaryTest {

    @Autowired
    CheckoutService service;

    @Autowired
    InMemoryOrderStore store;

    @MockitoBean(enforceOverride = true)
    PaymentGateway paymentGateway;

    @Test
    void retainsRealBusinessBeansAndReplacesOnlyGateway() {
        when(paymentGateway.charge(216_000L))
                .thenReturn("tx-spring");

        CheckoutReceipt receipt = service.checkout(
                new CheckoutCommand("BOOK", 2, true));

        assertAll("Spring-managed checkout",
                () -> assertEquals(240_000L,
                        receipt.subtotalVnd()),
                () -> assertEquals(24_000L,
                        receipt.discountVnd()),
                () -> assertEquals(216_000L,
                        receipt.totalVnd()),
                () -> assertEquals("tx-spring",
                        receipt.paymentReference()));

        assertEquals(List.of(receipt), store.receipts());
        verify(paymentGateway).charge(216_000L);
    }
}
```

**Why is `enforceOverride=true` valid here?** `DemoPaymentGateway` is a `@Component` implementing `PaymentGateway`. `@MockitoBean` replaces that existing bean without fabricating a missing bean to patch broken config. `CheckoutService` stays a real Spring bean, testing real context wiring.

The class contains one test method so the example need not manage singleton state cleanup on `InMemoryOrderStore` across multiple methods. In larger suites sharing stateful fake stores across cached contexts, design proper isolation/resets; **`@MockitoBean` does not reset unrelated beans**.

### 12.1. `@MockitoBean` scope and Spring AOP

Spring TestContext's **`REPLACE`**/`REPLACE_OR_CREATE` overrides swap the bean directly with a mock instance. Mocked beans typically **lose Spring AOP advice** attached to the original bean (such as `@Transactional`, `@Cacheable`, `@Retryable`, or method security).

That is fine when replacing an **outbound gateway outside the verification scope**. However, if you mock the **business service itself** and claim its transactions, retries, or security work, the test misses its target: the real proxy and logic were replaced away.

`@MockitoSpyBean` wraps the real bean and can remain behind Spring AOP proxies. Even then, spies are not risk-free: `when(spy.method())` can run real code during stub setup; use `doReturn`/`doThrow` where needed and verify proxy/cache/retry interactions.

### 12.2. Why avoid a full Boot context for every unit test?

`@SpringBootTest` boots a context with real overhead: bean initialization, configuration processing, component scanning, and cache management. To verify a 10% discount rule, `new DiscountPolicy()` + JUnit suffices. Reserve Spring context tests for verifying important wiring, configuration, and bean replacement.

## 13. MVC slice: when mocking the application service is the right boundary

It may sound contradictory: "Do not mock `CheckoutService`," followed by "Mock `CheckoutService` in `@WebMvcTest`." The difference is the **SUT**.

In an MVC slice test, you are not testing pricing math. You are testing the controller's **routing, JSON binding/serialization, and HTTP responses**. Therefore, collaborator `CheckoutService` lies outside the scope and can be mocked. Separate unit/context tests still protect the business rules.

**`src/test/java/com/example/checkout/CheckoutControllerSliceTest.java`**

```java
package com.example.checkout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CheckoutController.class)
class CheckoutControllerSliceTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    CheckoutService service;

    @Test
    void mapsJsonCommandAndReturnsReceipt() throws Exception {
        CheckoutCommand command =
                new CheckoutCommand("BOOK", 2, true);
        CheckoutReceipt receipt = new CheckoutReceipt(
                "BOOK", 2, 240_000L, 24_000L, 216_000L,
                "tx-http");

        when(service.checkout(command)).thenReturn(receipt);

        mvc.perform(post("/api/checkouts")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "sku": "BOOK",
                                  "quantity": 2,
                                  "member": true
                                }
                                """))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.sku").value("BOOK"),
                        jsonPath("$.subtotalVnd").value(240_000),
                        jsonPath("$.discountVnd").value(24_000),
                        jsonPath("$.totalVnd").value(216_000),
                        jsonPath("$.paymentReference").value("tx-http"));

        verify(service).checkout(command);
    }
}
```

**Explanation:**

- `@WebMvcTest(CheckoutController.class)` loads the Spring MVC slice without loading all services and repositories like a full application context.
- `@MockitoBean` provides a mocked `CheckoutService` to the controller's constructor. Because the real service need not exist in the MVC slice, `enforceOverride=true` is omitted here.
- `MockMvc` verifies the endpoint binds the JSON record and serializes the JSON response. The test calls no payment gateway, reads no catalog, and never pretends to verify discount math.
- `verify(service).checkout(command)` catches controller bugs passing malformed inputs whenever record mapping is under test.

**Limitation:** if the project includes Spring Security or custom HTTP setups, add appropriate test security/fixtures so tests reflect real API contracts. Never disable authentication or CSRF lightly just to turn a test green. This demo includes no Spring Security dependency.

In an MVC slice, **mocking the service hits the right boundary**. In a `CheckoutService` unit test, **mocking the service defeats the test**. The same technique yields different value depending on scope.

## 14. Bean overrides across Spring Boot versions

Never copy an annotation without checking version context:

| Project | Standard annotation for mocking a Spring bean | Import |
|---|---|---|
| Spring Boot 3.3 and earlier | Spring Boot `@MockBean` | `org.springframework.boot.test.mock.mockito.MockBean` |
| Spring Boot 3.4/3.5, Spring Framework 6.2+ | **Prefer `@MockitoBean`** | `org.springframework.test.context.bean.override.mockito.MockitoBean` |
| Spring Boot 4.x / Spring Framework 7.x | **`@MockitoBean`** and compatible mechanisms | Spring TestContext `MockitoBean`; check version-matched test starter modules |

In Spring Boot 3.4, `@MockBean` and `@SpyBean` were **deprecated** in favor of Spring Framework's `@MockitoBean` and `@MockitoSpyBean`. Migration is not a 100% mechanical import swap: supported annotation placements, bean selection, and override behaviors differ. Audit tests after migrating, especially when `@MockBean` lived on `@Configuration` classes or multiple beans shared a type.

In Boot 3.3 projects, `CheckoutSpringBoundaryTest` in Section 12 would use `@MockBean` instead of `@MockitoBean` and drop `enforceOverride` because the legacy API lacks that attribute. These are **version choices**; never mix both annotation styles arbitrarily in one project.

When needing a fake instead of a Mockito mock, use `@TestConfiguration` and `@Import` to register a test implementation; Spring Framework 6.2+ also provides `@TestBean` for factory-method overrides. Watch bean names, qualifiers, and scopes. Avoid broad overriding setups that silently suppress important production beans under protection.

## 15. Where to place mocks or fakes at real application boundaries?

Typical scenarios:

### 15.1. External REST services

**Goal:** compute payloads and send requests with valid amount, currency, and idempotency keys. In unit tests, mock/fake a `PaymentGateway` interface. In adapter contract tests, use a mock HTTP server to verify JSON, headers, status mapping, and timeouts; in authorized integration tests, hit a sandbox API.

**Avoid:** mocking `CheckoutService` and asserting the mocked receipt. That skips both request serialization and business logic.

### 15.2. Email and notifications

**Goal:** send no emails on failed transactions; send one notification upon completion. Use a fake or spy on `NotificationPort` at the outbound boundary, asserting messages or verifying single calls. Never hit production SMTP.

**Avoid:** mocking the main handler and calling `verify(handler).handle(...)` when the test intends to guard notification-decision logic.

### 15.3. Repositories and databases

**Goal:** verify status transitions and save-vs-skip decisions. A simple fake repository or mocked save/load works for unit tests.

**Different goal:** verify queries, mappings, unique constraints, transactions, or optimistic locking. Use the real repository adapter against a proper test database; in-memory fakes never protect SQL.

### 15.4. Time, UUIDs, and randomness

Voucher expiration rules require deterministic time. Replace system clocks by injecting **`Clock.fixed(...)`** via a `Clock` dependency rather than using `Thread.sleep`. Whenever UUIDs or randomness affect outputs, inject controllable generators. This is a **control boundary**, not an excuse to mock entire policies.

### 15.5. Message brokers / async workers

Business event tests can use a fake `EventPublisher` recording emitted events; separate adapter tests verify serialization, partition keys, and delivery/retry behavior against a controlled broker. When business rules depend on after-commit publishing or eventual consistency, test at the real transaction/async boundary rather than trusting a lone `verify(publisher)`.

### 15.6. Spring Security and AOP

When testing HTTP access rules, transaction rollbacks, or retry advice, never mock the bean or proxy enforcing those policies. Use an appropriate Spring context or HTTP/integration test and assert observable effects. Outbound port mocks may still be useful to isolate external APIs.

## 16. A decision model for every dependency

Ask five questions for **each dependency** in a test:

1. **Is this logic the test is meant to prove?** If yes, run the real implementation. Only consider a double for out-of-scope external adapters like payment gateways.
2. **Is the real part cheap and deterministic?** Value objects, pure mappers, and discount policies are cheap; never mock them merely because they are injected.
3. **Does it carry side effects or environment dependencies?** Networks, DBs, clocks, filesystems, and brokers require isolation or controlled setup.
4. **Is the test checking outputs or protocol/interactions?** For domain logic, assert state/values; for outbound APIs, verify amounts, idempotency keys, and call counts; for SQL, test the real adapter.
5. **Would a double eliminate critical behavior?** Mocking a `@Transactional` bean or pricing method removes the exact execution path under test.

Quick decision table:

| If ... | Then ... |
|---|---|
| Pure class computing prices/rules | **Keep real**, no Spring needed |
| Business orchestration service under test | **Keep real**, inject mock/fake outbound ports |
| Controller mapping HTTP in `@WebMvcTest` | **Keep controller real**, mock service at slice boundary |
| External HTTP adapter needing serialization check | **Keep adapter real**, use mock HTTP server |
| DB SQL/mapping is the contract | **Keep repository real**, use test DB |
| Testing Spring bean wiring | Real Boot context, override minimal out-of-scope beans |
| Legacy class lacking a seam | Intentional temporary spy, consider extracting a port |
| Double has to mimic complex protocols/transactions | Use a real-infrastructure integration test instead of a custom fake |

## 17. Test doubles must never "feed the test its own answers"

A classic trap:

```java
// COUNTER-EXAMPLE: expected amount is stuffed directly into the stub
// of the very business policy the test claims to prove.
when(discountPolicy.discountVnd(240_000L, true))
        .thenReturn(24_000L);
```

If `DiscountPolicy` has a bug, Mockito still returns 24,000. The test measures orchestration at best, **never discount accuracy**.

A better setup:

```java
DiscountPolicy discountPolicy = new DiscountPolicy();
assertEquals(24_000L,
        discountPolicy.discountVnd(240_000L, true));
```

Then in the checkout test, inject **that real object** so the entire use case computes 216,000. These two layers complement each other: policy unit tests cover threshold tables, service unit tests verify orchestration, and Spring tests verify bean wiring.

Never copy a number from `when(...)` straight into `assertEquals(...)` without executing real logic in between. "Having assertions" is not enough; a test needs a **real execution path not fabricated by test setup**.

## 18. When having multiple mocks is completely reasonable

Never enforce a rigid rule like "one mock per test." A real use case might legitimately call three outbound ports: a tax API, a payment API, and an event bus. An orchestration unit test can double all three, **provided core decision rules and verified state still run for real**, and adapter contracts are guarded elsewhere.

For example, user registration involves:

- `UserPolicy` checking password, email, and eligibility rules.
- `UserRepository` at the persistence boundary.
- `EmailGateway` at the email boundary.
- `AuditPublisher` at the event boundary.

A unit test can pair a fake repository, mock email gateway, and fake event publisher while keeping `UserPolicy` and `RegisterUserService` real. The raw number of doubles is not the issue; **which parts of the contract they replace** is what counts.

A "thin orchestrator" test verifying ports are called in sequence also has value when ordering is part of the contract. Just never substitute it for domain-rule tests, and avoid `InOrder` on steps whose order may safely change.

## 19. Spotting "chain-mocking" in code reviews

Watch for these signs:

- Test named `calculatesDiscountCorrectly` where `DiscountPolicy` is a `@Mock`.
- Test named `processesOrder` where `CheckoutService` is overridden with `@MockitoBean` and assertions inspect only stubbed JSON.
- Assertions consist mostly of `verify(...)` on internal helpers with few business outcome checks.
- Long chains of `when(...).thenReturn(...)` script an entire scenario where almost zero production code runs.
- Tests depend on private methods, mapper class names, intermediate DTO details, or call counts of non-contract helpers.
- Changing a domain rule leaves tests green because all numbers were hardcoded in stubs.
- Behavior-preserving internal refactors break dozens of tests.
- Fake repositories keep expanding to reimplement complex SQL, transactions, filtering, and sorting just to keep tests green.

**Quick review test:** point at the Act line and ask "what real code executes here?" If Act invokes a mocked SUT, insist on clarifying its limited goal or rewriting it to run real logic. If Act invokes a real service whose policy is mocked, decide whether the test protects orchestration or domain rules and fill any missing coverage.

**Mutation thought experiment:** suppose someone changes the discount from 10% to 9%. Which test turns red? If none fails, the suite does not protect the discount rule. Likewise, delete the `OrderStore.save` call: which test catches the lost data? In Section 8's unit test, the assertion on the fake store fails immediately.

## 20. Risks of overly broad Spring bean overrides

### 20.1. Replacing the bean actually under test

If the goal is testing transactions on `CheckoutService` yet you add `@MockitoBean CheckoutService`, transaction advice and real methods may never run. A green test only proves the mock returned data. Keep the bean/proxy under test real and replace only outbound dependencies.

### 20.2. Creating a mock even when production lacks the bean

Default `@MockitoBean` can **replace or create**; if a misconfigured module drops the real bean, tests still get a mock and pass. When missing wiring must be caught, use `enforceOverride=true` or proper integration bootstrapping tests.

### 20.3. Multiple beans of the same type

If both `StripePaymentGateway` and `BankPaymentGateway` implement `PaymentGateway`, a type-only annotation is ambiguous. Match the exact qualifier or bean name injected by the real SUT; never override an arbitrary bean assuming it swaps the right adapter.

### 20.4. Fragmented context caches

Spring TestContext caches `ApplicationContext` instances by configuration, including customizers from mock bean definitions. Two tests with different `@MockitoBean` sets spin up separate contexts, inflating CI runtime. Avoid creating dozens of full-context tests with varying mock permutations when fast unit or slice tests suffice.

### 20.5. Stateful fake beans and parallel tests

A stateful singleton like `InMemoryOrderStore` preserves data across test methods sharing a context. Reset fixtures safely or keep test data independent. Never let parallel tests mutate a shared fake concurrently without explicit concurrency control.

### 20.6. `@MockitoSpyBean` and real methods

Unstubbed spy methods run for real, even during `when(spy.method())`. For side-effecting methods, use `doReturn`/`doThrow` appropriately; better yet, separate boundaries so partial mocking is unnecessary. Never turn a spy test into method-by-method scripting inside a service.

### 20.7. AOP is not verified by mocks

A bean directly replaced by `@MockitoBean` no longer necessarily carries the original bean's advice. `@Transactional`, `@Cacheable`, `@Retryable`, or method security on that replaced bean **are not being tested**. To verify advice, keep the bean real, invoke through its proxy, and assert observable effects.

## 21. Keeping tests independent, fast, and trustworthy

A sensible testing strategy can combine:

1. **Domain unit tests:** run real value objects, policies, and use-case logic with minimal dependencies.
2. **Application service unit tests:** fake persistence, mock external APIs at outbound ports, assert outputs and needed side effects.
3. **MVC slice tests:** real controllers, mocked services if testing HTTP contracts only, covering validation/serialization/security as required.
4. **Persistence integration tests:** real repositories with an appropriate test DB to verify queries, mappings, and constraints.
5. **External adapter contract tests:** HTTP stub servers or controlled sandboxes verifying wire protocols and error mapping.
6. **Few, focused end-to-end tests:** wire real components for high-risk flows, accepting higher runtime and isolated setup.

No single "testing pyramid" ratio fits every product. Proportions vary with risk, architecture, and maintenance cost. Still, **unit tests free of external resources** stay fast and reliable, while integration/contract layers catch bugs invisible to mocks and fakes.

### 21.1. When to pick a fake over a mock?

- Fakes suit simple read/write state supporting state assertions.
- Mocks suit external ports needing argument/call-count checks or simulated exceptions.
- Real collaborators suit cheap, deterministic pure logic.
- Testcontainers / real DBs suit transactional or query behavior fakes cannot reproduce.

### 21.2. When to refactor instead of adding more mocks?

If a class requires 10 mocks just to test one simple branch, it probably carries too many responsibilities. Split domain policies, application orchestration, and outbound adapters; inject via constructors; define interfaces at infrastructure seams. Refactor to improve design—**not merely to appease Mockito**.

## 22. Running the examples with Gradle and Spring Boot

The files in Sections 7–13 target **Java 17+, Spring Boot 3.4+/3.5 with Spring Framework 6.2+, JUnit Jupiter 5, Mockito, and Jackson**. Running both `@SpringBootTest` and `@WebMvcTest` requires the starters inside a Gradle project with configured **Spring Boot plugin/BOM and repositories**.

Example dependencies in `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **snippet added to a configured Spring Boot build**, not a standalone `build.gradle`. `spring-boot-starter-test` in Spring Boot 3.4+/3.5 pulls in standard JUnit Jupiter, Mockito, and Spring Test integrations.

Run from the directory containing the Gradle wrapper:

```bash
./gradlew test --tests com.example.checkout.CheckoutServiceUnitTest --tests com.example.checkout.CheckoutSpringBoundaryTest --tests com.example.checkout.CheckoutControllerSliceTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.checkout.CheckoutServiceUnitTest --tests com.example.checkout.CheckoutSpringBoundaryTest --tests com.example.checkout.CheckoutControllerSliceTest
```

In multi-project Gradle builds, use the right task path such as `:your-module:test` if that module exists. Package and file paths must match the listed files. **Never copy incomplete counter-examples as runnable Java classes**; those snippets exist solely for design comparison.

**Expected outcomes under valid configuration:**

- `CheckoutServiceUnitTest` has 3 tests: valid checkout, invalid SKU skips payment, failed payment saves no receipt.
- `CheckoutSpringBoundaryTest` has 1 test: real Spring beans compute amounts properly while Mockito replaces `PaymentGateway`; assertions pass on store and gateway.
- `CheckoutControllerSliceTest` has 1 test: HTTP POST JSON maps to command and returns JSON with total and `paymentReference` from the mocked service.
- In total, the example contains **5 test methods**; with matching dependencies and setup, Gradle is expected to report `BUILD SUCCESSFUL`.
- These JUnit tests print no fixed business stdout; `DemoPaymentGateway` makes no network calls and should not be invoked during these tests.

These are **expected outcomes from inspecting the code**, not a claim of execution against a live repository. Check test reports at `build/reports/tests/test/index.html` and XML results in the module's `build/test-results/test/`.

### 22.1. If tests fail to start the context

Checklist of causes:

- `@MockitoBean` must exist in the active Spring Test version; Boot 3.3 requires the legacy API or an upgrade.
- `@SpringBootTest(classes=CheckoutDemoApplication.class)` must scan the beans in `com.example.checkout`.
- `enforceOverride=true` requires a real `PaymentGateway` bean; in the demo, `DemoPaymentGateway` provides it. If missing, investigate rather than turning off the safeguard.
- `@WebMvcTest` requires Jackson/web support from `starter-web`. If Spring Security is on the classpath, POST requests may require a principal/CSRF token per tested policy.
- If `@Autowired` fails, inspect the root cause under `Failed to load ApplicationContext`, checking bean ambiguity and qualifiers.
- If tests fail together in a suite due to stateful singleton fake data, audit context caching and isolation rather than forcing test ordering.

## 23. Hands-on exercises

### Exercise A — choosing the right SUT and boundaries

Requirement: vouchers have an expiration date, discount only new customers, and then charge payment and save the order.

Identify which components must run for real when testing **voucher rules**, and which can be doubles. Hint: real voucher policy, fixed clock, fake customer lookup if external, mock payment gateway, fake order repository if not verifying SQL.

### Exercise B — spotting a false-positive test

Given this test:

```java
CheckoutService mockService = mock(CheckoutService.class);
when(mockService.checkout(command)).thenReturn(receipt);
assertEquals(receipt, mockService.checkout(command));
```

This is an illustrative snippet with `command` and `receipt` undeclared. Answer: if you delete the entire body of the real `CheckoutService.checkout`, would this test fail? If not, fix it by instantiating the real service and doubling only outbound collaborators.

### Exercise C — testing payment errors

Using Section 8's example, make the gateway throw `IllegalStateException("declined")`; assert charge call count, exception, and empty store. Next try negative quantities and unknown SKUs; charge must never be called on invalid inputs.

### Exercise D — choosing MVC slice vs. service unit tests

An API accepts POST JSON with a misspelled `quantity` field, resulting in HTTP 400 instead of the expected output while discount logic is completely right. Where should you fix and test this? Hint: controller/MVC binding/validation and HTTP contracts need dedicated tests; domain unit tests cannot catch JSON mapping bugs.

### Exercise E — transactions and persistence

Can the fake `OrderStore` check "save ran after charge"? Can it prove JPA transaction commits, unique constraints, or rollbacks during real server HTTP handling? Explain why separate database integration and transaction-boundary tests are required.

### Exercise F — replacing the right bean

A Spring context holds two beans implementing `PaymentGateway`, one for card and one for bank. If a test declares `@MockitoBean PaymentGateway gateway;`, what risk arises? Propose an explicit bean name/qualifier and explain when `enforceOverride=true` fits.

## 24. Review checklist before approving a test

- [ ] Does the test state a clear goal and contract: **which bug makes it turn red**?
- [ ] Is the SUT a real implementation rather than a mock returning hardcoded `expected` data?
- [ ] Do critical domain rules (pricing, discounts, eligibility, state transitions) execute for real?
- [ ] Are test doubles focused at outbound boundaries, external APIs, DBs, clocks, or truly out-of-scope collaborators?
- [ ] Do doubles reflect minimal essential contract details without over-simulating complex systems?
- [ ] Did I separate unit/service tests from MVC controller slices, mocking services only when out of scope?
- [ ] Are there assertions on **results and state**, rather than verifying internal call graphs alone?
- [ ] Are interactions verified only when arguments, order, or call counts carry business meaning?
- [ ] When using a Spring context, am I replacing the **right bean** with the version-appropriate annotation?
- [ ] Do I understand `@MockitoBean` can create missing beans by default, and consider `enforceOverride=true` when verifying bean existence?
- [ ] Have I avoided accidentally mocking away proxy/transaction/cache/security behavior under test?
- [ ] Are fake beans, context caching, parallel runs, and data isolation handled intentionally?
- [ ] Do DB/HTTP/messaging adapters have separate tests protecting real protocols and infrastructure?
- [ ] Would a valid internal refactor leave the test green as long as the contract holds?
- [ ] When the test turns red, does the failure point to a business discrepancy rather than an uncalled helper method?

**Remember:** **More or fewer mocks is not a quality metric by itself.** The true criterion is **which parts of the system actually execute, which parts are doubled, and why**. A trustworthy checkout unit test runs real pricing, discounts, guards, and orchestration, doubling only payment gateways or storage when out of scope. A trustworthy MVC slice test can mock the application service to focus on HTTP contracts without claiming business logic is proven. Placing test doubles at the right boundaries keeps tests fast, bug-catching, and resilient to refactoring.

### References

- Spring Framework — Bean Overriding in Tests: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html
- Spring Framework 6.2 — `@MockitoBean` and `@MockitoSpyBean`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Spring Boot 3.4 Release Notes — deprecation of `@MockBean` and `@SpyBean`: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes
- Mockito API — `mock`, `when`, `verify`, `spy`: https://site.mockito.org/
- Spring Boot — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
