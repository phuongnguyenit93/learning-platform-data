# Mocking Repositories and Verifying Business Rules in Spring Boot Unit Tests

## 1. Goal: Testing Business Logic Without Depending on a Database

In a Spring Boot application, a service typically receives input data, checks business conditions, reads data via repositories, computes results, and asks a repository to persist changes. If every service test had to boot a Spring context and database, test runs would become slow, environment-dependent, and hard to diagnose when they fail.

A **mock repository** is a test double created by a library like Mockito to stand in for the real repository at the service boundary. We can specify what data the fake repository returns (`stubbing`), execute the **real** service, and verify that the service:

1. Fetches the right data needed for business decisions.
2. Applies rules, thresholds, and exception branches accurately.
3. Constructs the right object to save or pass to dependencies.
4. Calls the repository only when permitted; saves nothing when input is invalid.
5. Returns a value or throws an exception matching the contract.

Example: an invoice for an active **VIP** customer gets a 10% discount when the original subtotal is **500,000 VND or more**. Regular customers receive no discount. Inactive or non-existent customers must be rejected and **no invoice created**.

Unit tests can thoroughly verify all of these decisions using `Mockito.mock`, `@Mock`, `when(...).thenReturn(...)`, `verify(...)`, and `ArgumentCaptor`, without a real database.

**Boundary to remember:** When `verify(invoiceRepository).save(invoice)` passes, it proves the service **requested saving** that object on the mock; it does not prove valid SQL, transaction commit, valid entity mapping, or that a row actually exists in the database.

## 2. Distinguishing Roles Before Writing Tests

| Component | Role in the test | Use real or fake/mock? |
|---|---|---|
| `InvoiceService` | Holds the logic branches to verify (SUT: system under test) | **Real** |
| `CustomerRepository` | Supplies customer data to the service | Mock, returning `Optional<Customer>` per scenario |
| `InvoiceRepository` | Receives the invoice persistence request | Mock, inspecting the data passed into `save` |
| `Customer`, `Invoice`, enum `CustomerTier` | Business data/value types | **Real**, constructed with clear fixtures |
| JUnit Jupiter | Executes tests and asserts results | Testing framework |
| Mockito | Creates mocks, stubs, and verifies interactions | Support framework |
| Spring ApplicationContext / database | Infrastructure needed for integration tests | Not needed for the illustrative unit tests |

In production, a repository might be an interface extending `JpaRepository`, `CrudRepository`, or a custom storage port. In a unit test, what matters is keeping the **contract the service uses**: read methods return data or empty, and write methods accept the entity to save. Mockito does not require a real repository connected to a database in order to create a mock.

Do not mock `InvoiceService` itself: doing so only tests behavior scripted onto the mock, bypassing the business branches you want to protect.

## 3. Defining the Business Contract and Test Cases

Suppose the invoicing application has these rules:

- `customerId` must be positive and `subtotal` must be greater than 0.
- The customer must exist in the repository.
- The customer must be active (`active == true`).
- Only customers with `tier == VIP` and `subtotal >= 500_000` receive a 10% discount on `subtotal`.
- `REGULAR` customers receive no discount, even when the subtotal meets the threshold.
- `payable = subtotal - discount`.
- For valid requests, the service builds an `Invoice`, calls `invoiceRepository.save(invoice)` exactly once, and returns the saved result.
- For invalid requests, missing customers, or inactive customers, the service must not call the repository to save an invoice.

Test case table:

| Scenario | Mock repository data | Expected result | Interactions to verify |
|---|---|---|---|
| VIP at exact threshold 500,000 | Customer exists, `active=true`, `VIP` | Discount 50,000; payable 450,000 | Calls `findById`, saves exact `Invoice` once |
| VIP below threshold 499,999 | Active VIP customer | No discount; payable 499,999 | Saves undiscounted invoice |
| REGULAR 800,000 | Active regular customer | No discount; payable 800,000 | Saves exact invoice |
| Missing customer | `Optional.empty()` | Not-found exception | Does not call `save` |
| Inactive customer | Customer exists with `active=false` | State exception | Does not call `save` |
| Invalid ID or non-positive subtotal | No query needed | `IllegalArgumentException` | No interaction with either repository |

A test that only checks the calculation while ignoring `save` would miss a bug where the service builds a different invoice and saves incorrect data. Conversely, `verify(save(any()))` alone does not prove the discount amount is right. Combine **business value assertions** with **verification at the repository boundary**.

## 4. Complete Java 17+ Example: Real Service, Mock Repositories

The following files belong in a Spring Boot project using Java 17+ and test dependencies including JUnit Jupiter, Mockito, and the Mockito JUnit Jupiter extension (typically included via `spring-boot-starter-test`). The example focuses on unit testing so it does not start Spring, JPA, or a database.

### 4.1. Business code

File: `src/main/java/com/example/testing/InvoiceService.java`.

The non-`public` enum, records, and interfaces are placed in the same file so the example compiles immediately as a single production file; in real applications, they can be split into separate files.

```java
package com.example.testing;

import java.util.NoSuchElementException;
import java.util.Optional;

enum CustomerTier {
    REGULAR, VIP
}

record Customer(long id, boolean active, CustomerTier tier) {}

record Invoice(
        long customerId,
        int subtotal,
        int discount,
        int payable) {}

interface CustomerRepository {
    Optional<Customer> findById(long customerId);
}

interface InvoiceRepository {
    Invoice save(Invoice invoice);
}

public final class InvoiceService {
    private final CustomerRepository customers;
    private final InvoiceRepository invoices;

    public InvoiceService(
            CustomerRepository customers,
            InvoiceRepository invoices) {
        this.customers = customers;
        this.invoices = invoices;
    }

    public Invoice issue(long customerId, int subtotal) {
        if (customerId <= 0 || subtotal <= 0) {
            throw new IllegalArgumentException("Invalid invoice input");
        }

        Customer customer = customers.findById(customerId)
                .orElseThrow(() ->
                        new NoSuchElementException("Customer not found"));

        if (!customer.active()) {
            throw new IllegalStateException("Customer inactive");
        }

        int discount = customer.tier() == CustomerTier.VIP
                && subtotal >= 500_000
                ? subtotal / 10
                : 0;

        Invoice invoice = new Invoice(
                customerId,
                subtotal,
                discount,
                subtotal - discount);

        return invoices.save(invoice);
    }
}
```

Key design decisions explained:

- Input data is validated **before** calling any repository. Therefore, `subtotal <= 0` must have zero repository interactions.
- `findById` returns `Optional<Customer>`. `Optional.empty()` is mapped to this example's business exception; never call `get()` without checking presence.
- Inactive customers are blocked before calling `save`.
- The threshold uses `>= 500_000`, so **exactly 500,000** qualifies for the discount.
- `Invoice` is a Java record: `equals` compares every component by value, convenient for assertions.
- `issue` returns whatever `invoices.save` returns. In unit tests, we must configure this answer if we want an `Invoice` instead of Mockito's default mock return value.

The example uses `int` as whole currency units to focus on the test technique, with integer-division discount (`subtotal / 10`). For systems with fractional currency, multiple currencies, or different rounding rules, use a money type/`BigDecimal` and test the rounding policy separately. Do not generalize the sample formula into a universal accounting rule.

### 4.2. Tests using @Mock and MockitoExtension

File: `src/test/java/com/example/testing/InvoiceServiceTest.java`.

```java
package com.example.testing;

import java.util.NoSuchElementException;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class InvoiceServiceTest {

    @Mock
    CustomerRepository customers;

    @Mock
    InvoiceRepository invoices;

    private InvoiceService service;

    @BeforeEach
    void setUp() {
        service = new InvoiceService(customers, invoices);
    }

    @Test
    void vipAtThresholdGetsDiscountAndIsSavedOnce() {
        when(customers.findById(7L)).thenReturn(Optional.of(
                new Customer(7L, true, CustomerTier.VIP)));

        when(invoices.save(any(Invoice.class)))
                .thenAnswer(call -> call.getArgument(0));

        Invoice result = service.issue(7L, 500_000);

        assertAll("VIP at exact threshold",
                () -> assertEquals(7L, result.customerId()),
                () -> assertEquals(500_000, result.subtotal()),
                () -> assertEquals(50_000, result.discount()),
                () -> assertEquals(450_000, result.payable()));

        ArgumentCaptor<Invoice> captor =
                ArgumentCaptor.forClass(Invoice.class);

        verify(customers).findById(7L);
        verify(invoices, times(1)).save(captor.capture());

        Invoice saved = captor.getValue();
        assertEquals(result, saved);
        verifyNoMoreInteractions(customers, invoices);
    }

    @Test
    void vipBelowThresholdGetsNoDiscount() {
        when(customers.findById(7L)).thenReturn(Optional.of(
                new Customer(7L, true, CustomerTier.VIP)));

        when(invoices.save(any(Invoice.class)))
                .thenAnswer(call -> call.getArgument(0));

        Invoice result = service.issue(7L, 499_999);

        assertEquals(0, result.discount());
        assertEquals(499_999, result.payable());

        verify(invoices).save(
                new Invoice(7L, 499_999, 0, 499_999));
    }

    @Test
    void regularCustomerGetsNoVipDiscount() {
        when(customers.findById(9L)).thenReturn(Optional.of(
                new Customer(9L, true, CustomerTier.REGULAR)));

        when(invoices.save(any(Invoice.class)))
                .thenAnswer(call -> call.getArgument(0));

        Invoice result = service.issue(9L, 800_000);

        assertEquals(0, result.discount());
        assertEquals(800_000, result.payable());
        verify(invoices).save(
                new Invoice(9L, 800_000, 0, 800_000));
    }

    @Test
    void missingCustomerNeverSavesInvoice() {
        when(customers.findById(20L))
                .thenReturn(Optional.empty());

        assertThrows(NoSuchElementException.class,
                () -> service.issue(20L, 500_000));

        verify(customers).findById(20L);
        verifyNoInteractions(invoices);
    }

    @Test
    void inactiveCustomerNeverSavesInvoice() {
        when(customers.findById(11L)).thenReturn(Optional.of(
                new Customer(11L, false, CustomerTier.VIP)));

        assertThrows(IllegalStateException.class,
                () -> service.issue(11L, 500_000));

        verify(customers).findById(11L);
        verifyNoInteractions(invoices);
    }

    @Test
    void invalidInputDoesNotAccessRepositories() {
        assertThrows(IllegalArgumentException.class,
                () -> service.issue(0L, 500_000));

        assertThrows(IllegalArgumentException.class,
                () -> service.issue(7L, 0));

        verifyNoInteractions(customers, invoices);
    }
}
```

**Important points in the code:**

- `@ExtendWith(MockitoExtension.class)` initializes `@Mock` fields before each test, integrates with the JUnit Jupiter lifecycle, and helps detect unnecessary stubbing.
- `@BeforeEach` constructs the **real service** with two mocks; do not use Spring `@Autowired` or `@SpringBootTest` just to verify calculations.
- `when(customers.findById(7L)).thenReturn(Optional.of(...))` supplies controlled input for the VIP branch.
- `when(invoices.save(any(Invoice.class))).thenAnswer(call -> call.getArgument(0))` makes the mock return the same object passed to it. This simulates the **chosen test contract**, not real database ID generation or commit behavior.
- `ArgumentCaptor` reads the `Invoice` the service requested to save and compares it with the returned value; `verify(..., times(1))` verifies the write count.
- Error cases **do not stub `save`**, because correct behavior requires the service not to call `save`; `verifyNoInteractions(invoices)` will turn red if the service violates this.
- `verifyNoMoreInteractions` in the first case intentionally guards against extra calls; avoid overusing it in tests that only need to verify business outcomes, as it can couple tests tightly to internal structure.

With this setup, **all six tests are designed to pass**. Neither production methods nor tests print `stdout`; Maven/Gradle report logs according to the runner version, so exact real-project log text is not predicted here. The tests run against the illustrative service, not a fully initialized Spring Boot application.

### 4.3. Running the tests

With Gradle wrapper on Linux/macOS:

```bash
./gradlew test --tests "com.example.testing.InvoiceServiceTest"
```

With Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.testing.InvoiceServiceTest"
```

With Maven wrapper on Linux/macOS:

```bash
./mvnw -Dtest=InvoiceServiceTest test
```

With Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=InvoiceServiceTest test
```

Prerequisite: the project configures JUnit Platform/Surefire compatible with JUnit Jupiter; in Gradle, this typically includes `useJUnitPlatform()`. Afterward, inspect the actual report (`build/reports/tests/test/index.html` for Gradle `test` task, or `target/surefire-reports/` for Maven Surefire). Record `PASS` for a project only when you see the tests discovered and executed successfully; a green build whose test task was skipped or cached does not confirm a fresh run.

## 5. Three Forms of Verification to Combine Properly

### 5.1. Verifying business outcomes with assertions

Example:

```java
assertEquals(50_000, result.discount());
assertEquals(450_000, result.payable());
```

This checks the **output** of the VIP rule. Test names should describe context and expectation, such as `vipAtThresholdGetsDiscountAndIsSavedOnce`. For threshold-based rules, include tests **below, at, and above the threshold** when off-by-one differences pose risk. In the example, the exact 500,000 and 499,999 cases catch `>` vs `>=` bugs; you can add an above-threshold case like 500,001 or a larger figure if currency and rounding rules require deeper verification.

### 5.2. Verifying repository calls with verify

```java
verify(customers).findById(7L);
verify(invoices, times(1)).save(any(Invoice.class));
```

`verify` checks invocations on a mock; by default `verify(mock)` expects exactly one matching call. When the requirement is not to persist data for an inactive customer, `verifyNoInteractions(invoices)` expresses the contract more clearly than checking the exception alone.

However, `save(any(Invoice.class))` alone will not catch an invoice with a wrong `payable` or `customerId`. When you need to verify the outbound data, pass an expected object with proper `equals` or use an `ArgumentCaptor`.

### 5.3. Verifying outbound data with ArgumentCaptor

```java
ArgumentCaptor<Invoice> captor =
        ArgumentCaptor.forClass(Invoice.class);

verify(invoices).save(captor.capture());

Invoice saved = captor.getValue();
assertEquals(450_000, saved.payable());
assertEquals(50_000, saved.discount());
```

A captor reads the argument received by the mock. It does not prove database commit state, nor does it automatically take a deep snapshot of a mutable entity at the moment `save` is called. If the service mutates the same object afterward, the state the captor inspects later may have changed. For tests that need state **at the exact moment of the call**, prefer immutable value objects or use `doAnswer` to snapshot critical fields at invocation time.

Balance output checks with interaction checks: do not verify every internal helper method just because Mockito allows it; verify only interactions **that belong to the business contract**, such as saving exactly one invoice or saving nothing on rejection paths.

## 6. Stubbing Repositories Properly

### 6.1. Defining input data per test

`Optional.empty()` is meaningful domain data: customer not found. Stub it explicitly:

```java
when(customers.findById(20L)).thenReturn(Optional.empty());
```

Do not rely on Mockito's default return values and treat them as explicitly modeled business scenarios. Mocks typically return default values (`null`, 0, `false`, or empty values depending on type/library), so forgetting to stub `save` can cause `issue` to return `null` and fail for reasons unrelated to the rule under test.

`thenReturn` works well for fixed results. `thenAnswer` works well when the result depends on arguments:

```java
when(invoices.save(any(Invoice.class)))
        .thenAnswer(call -> call.getArgument(0));
```

This is a **simple simulation choice** for an example whose repository returns the saved entity. A real repository may populate IDs, versions, timestamps, or transform the entity; to prove those behaviors, use integration tests or a more faithful stub contract.

### 6.2. Avoid overly broad or excessive stubbing

Writing `when(customers.findById(anyLong()))...` in every test can hide a bug where the service queries the **wrong customerId**. When the input ID matters, stub and verify exact IDs like `7L`, `9L`, and `20L` as shown. Remove all unused stubs; `MockitoExtension` can raise `UnnecessaryStubbingException` under strict stubs. Rather than applying `lenient()` indiscriminately, place stubs only in the tests that actually need them.

Do not stub `invoices.save` in tests that must fail before saving. Stubbing it in `@BeforeEach` for all tests causes invalid/missing cases to trigger unused-stubbing warnings even when the service works correctly.

### 6.3. Mockito matchers must be consistent

When a method takes multiple parameters and one parameter uses a matcher, the other parameters must also use appropriate matchers like `eq(...)` or `any(...)`. Never mix raw literals with matchers in the same Mockito invocation, as that triggers `InvalidUseOfMatchersException`.

Illustrative example using a hypothetical interface:

```java
verify(auditClient).record(
        eq("INVOICE_CREATED"),
        any(Invoice.class));
```

The snippet above only illustrates matcher syntax within a test that has declared `auditClient` and imported `eq`/`any`; it is **not a standalone Java file**. When a field requires a stricter check than `any()`, use `eq(expected)`, `argThat`, or a captor.

### 6.4. Exceptions thrown by repositories

Unit tests can also simulate dependency failures, for example:

```java
when(invoices.save(any(Invoice.class)))
        .thenThrow(new IllegalStateException("storage unavailable"));
```

If the service contract requires translating infrastructure exceptions into business errors, the test must call the service and assert **the exact translated exception**. If the service intentionally lets the exception propagate, the test can verify that too. Do not assume a service must always catch exceptions; error handling depends on the module's transaction contract and architecture.

The standalone snippets in sections 5–6 illustrate statements within a test context where mocks and imports are declared. The complete runnable program is in section 4.

## 7. Do Not Confuse Mock-Repository Unit Tests with Repository Integration Tests

This is an essential boundary in Spring Boot:

| Question | Service unit test with mock repositories | Integration/repository test |
|---|---|---|
| Is the VIP discount rule applied correctly? | **Yes**, using fixtures and assertions | Possible, though usually unnecessary for pure calculations |
| Does the service call `save` with the right invoice? | **Yes**, via `verify`/captor | Can observe persisted data |
| Does the JPA `findById` query return the right data from DB? | **No**: the result was stubbed | **Yes**, against a database/test configuration |
| Are entity mappings, schema constraints, and unique keys right? | **No** | Tested via `@DataJpaTest`/appropriate integration tests |
| Does the transaction commit/rollback as in production? | **No** | Requires meaningful transaction/DB tests |
| Do concurrent invoice requests cause race conditions? | **No** | Requires concurrency/integration tests with proper invariants |
| Does the controller handle JSON, validation, and HTTP status properly? | **No** | Requires corresponding web/API tests |

In Spring Boot, `@DataJpaTest` is often the right choice to focus on repositories/JPA. For bugs tied to a specific database engine, consider Testcontainers with a production-like database. `@SpringBootTest` loads the application context for multi-component integration tests, at a higher runtime cost than plain Java unit tests. A default `@SpringBootTest` does not automatically mean a real HTTP server was started.

To test a service inside a Spring context with mocked beans, use the bean-replacement mechanism matching your **Spring Boot/Spring Framework version**; for example `@MockitoBean` in supported versions. A standalone `@Mock` field outside the context does not automatically replace a bean injected by Spring. If the code under test consists purely of business rules, instantiating the service directly with mocks is typically clearer and cheaper.

## 8. Common Mistakes When Mocking Repositories

| Mistake | Consequence | Fix |
|---|---|---|
| Mocking the service containing business logic | Bypasses the logic under test | Instantiate the real service, mock its dependencies |
| Only calling `verify(save(any()))` | Misses wrong amounts/IDs/fields saved | Assert data with `eq`, record `equals`, or captor |
| Only asserting the returned amount | Might save the wrong entity or save twice | Verify `save` calls when part of the contract |
| Forgetting to stub `save` while asserting its return value | Mock may return `null` | Stub an appropriate return or assert captured data |
| Using `anyLong()` to stub every ID | Can miss querying the wrong customer | Stub and verify exact IDs |
| Stubbing `save` in setup for every test | Failure branches don't use it, harder to maintain | Stub only in cases that need `save` |
| Ignoring `Optional.empty()` | Not-found branch remains unprotected | Add a missing-customer test verifying no save |
| Checking only the exception without side effects | Service might save before throwing | `verifyNoInteractions(invoices)` when no write is allowed |
| Mocking data objects like `Customer` or `Invoice` | Over-mocked, hard-to-read tests | Use real values/records |
| Assuming mock `save` proves DB commit | Overstating test evidence | Add appropriate real-DB integration tests |
| Verifying every internal helper call | Brittle tests during valid refactoring | Verify only interactions that are part of the contract |
| Skipping boundary-value tests | `>` vs `>=` bugs slip through | Test below, at, and when needed above thresholds |

## 9. Structuring Tests for Long-Term Value

**Name tests after behavior**, not generic method names. `vipAtThresholdGetsDiscountAndIsSavedOnce` describes input, condition, and outcome, reading much better than `testIssue1`.

**Prepare minimal data per test.** With `MockitoExtension`, each test receives fresh mocks according to the test lifecycle, reducing order dependencies. Avoid shared global mock repositories across tests unless reset and state are deliberately managed.

**Test failure branches as thoroughly as success paths.** A service creating an invoice for an inactive customer can corrupt business data; `verifyNoInteractions` makes the “do not write” contract verifiable.

**Separate logic checks from real integration.** Unit tests should be fast and deterministic via fixtures. Real repository tests should focus on queries, mappings, constraints, and transactions. Web tests focus on status/body/validation. Multiple test layers complement each other and prevent one big test from breaking for too many unrelated reasons.

**Avoid uncontrolled random data.** If a service uses time, inject `Clock`; if it generates UUIDs and the contract requires deterministic IDs, consider injecting an ID source or comparing against captured data instead of guessing UUIDs. For exchange rates or policy configs, pass them as explicit test inputs.

## 10. Checklist Before Concluding a Service Meets Requirements

- [ ] The service under test is a real instance; repositories are the exact mocks passed in.
- [ ] Every `when(...)` intentionally returns data to trigger a specific business branch.
- [ ] Key outputs are asserted: discount, payable, exceptions, and boundary values.
- [ ] Required interactions are verified: querying the right customer, saving the right invoice, the right number of times.
- [ ] **No-save** behavior is verified for invalid input, missing customers, or inactive customers.
- [ ] Data passed to `save` is thoroughly checked; not just `any()`.
- [ ] Mock behavior is not treated as proof of real database commits.
- [ ] Tests are independent, with no unused stubs or cross-test state dependencies.
- [ ] Integration tests are planned when risks involve JPA mapping, SQL, transactions, or infrastructure.
- [ ] The proper test task was executed and the Gradle/Maven/CI report inspected before claiming a pass on a real project.

**Conclusion:** Mocking repositories with Mockito isolates Spring Boot services to **verify business rules quickly, clearly, and repeatably**. Good tests tailor mock repository data per scenario, execute the real service, assert outcomes, and verify meaningful interactions (especially saved data and no-save branches). When the question shifts to SQL, JPA, transactions, or the real database, use the corresponding integration tests.