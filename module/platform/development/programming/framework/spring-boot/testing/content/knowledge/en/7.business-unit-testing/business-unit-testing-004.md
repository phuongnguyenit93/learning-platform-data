# Distinguishing Input Errors from Dependency Failures or Business-State Conflicts

A failed request can stem from several distinct causes: a client sent malformed data, a downstream dependency failed to respond, or the input data was completely valid yet **the current business state forbids the action**. If you lump all of them into `IllegalArgumentException`, return HTTP 400 for every error, or write unit tests that merely check “an exception was thrown”, the application becomes hard to handle, hard to monitor, and prone to unsafe retries.

In Spring Boot, distinguishing causes must begin at the **business contract and dependency boundaries**, before translating them into HTTP statuses, logs, or retry policies at the appropriate layer. Unit tests must prove the **exact error type, exact failure condition, absence of unintended side effects**, and never confuse a system outage with a user mistake.

## 1. Three Error Categories to Keep Separate

| Error category | Identifying question | Examples | Typical action required |
|---|---|---|---|
| **Invalid input** | Do the parameters/request themselves violate the contract before knowing any system state? | `quantity <= 0`, blank SKU, end date before start date | Report the invalid field/rule clearly; caller fixes input before resending |
| **Business-state conflict** | Is the data well-formed, yet the action is invalid given current real state? | Product discontinued; stock has 2 left while 5 requested; cancelled order cannot be paid | Report business conflict/rejection; caller changes action, picks another resource, or waits for state change |
| **Dependency/infrastructure failure** | Did a required external system/device/service fail so we **cannot yet conclude** whether the request is valid? | Catalog API timeout, DB connection lost, broker unavailable, upstream 503 | Record the incident; may retry under controlled rules if safe, or return a temporary error and monitor operations |

One additional category also matters: **internal bugs/contract violations**, such as an unexpected `NullPointerException` from buggy code, adapter data violating the agreed contract, arithmetic overflow, or unexpected exceptions. Never classify these automatically as “user entered bad input”. For non-existent resources, there can also be a dedicated **not found** error; it is not automatically invalid input, especially when an identifier is syntactically valid yet no record exists.

### Same message “cannot process”, different remedies

- “Quantity is 0”: the caller fixes `quantity`; resending the exact same request will not help.
- “Quantity 5 but stock is 2”: the request is syntactically valid; inventory must be replenished or quantity adjusted.
- “Could not read stock due to catalog timeout”: it is **unknown** whether stock is sufficient; reporting “out of stock” here is a false conclusion.

Thus, error classification directly shapes **user messaging, retry safety, HTTP contracts, logs/metrics, and how unit tests are written**.

## 2. Placing Classification Boundaries in the Right Layer

A Spring Boot application may follow this chain:

```text
HTTP request
   │
   ▼
Controller + Bean Validation
   │  Checks shape: required, length, types, simple bounds
   ▼
Application/Domain service
   │  Checks input rules tied to the use case
   │  Calls port to read required state
   │  Checks invariants and business state
   ▼
Repository / HTTP client / message broker adapter
   │  Translates timeout/transport/DB failures into meaningful dependency errors
   ▼
Exception handler / API contract
      Maps each error category into the right response
```

**Boundary 1: input.** Check what can be known **before any I/O**. Controllers use `@Valid`/`@NotBlank`/`@Positive` to catch invalid request shapes; services still guard critical invariants when they may also be invoked by message consumers, scheduled jobs, or other services. Do not tie business services to `HttpServletRequest` just to tell error categories apart.

**Boundary 2: business state.** Requires trustworthy state data to decide. For instance, “product is inactive” is a valid entity state where rules disallow quoting; “available stock is less than requested quantity” conflicts with current stock state. An order cannot move from CANCELLED back to PAID if the state machine forbids it. State errors can change over time, unlike permanently invalid inputs.

**Boundary 3: dependencies.** Adapters must separate **communication failures** from **valid business responses**. Timeouts, refused connections, and DNS/DB unavailability must never be turned into “product not found” or “out of stock”. If upstream succeeds and indicates the product is inactive, that is state data for business rules, not a transport error. If upstream returns 409/422 with documented business semantics in the contract, the adapter should interpret it per contract rather than blindly treating every non-2xx as a network error.

**Boundary 4: external outcome.** `@RestControllerAdvice` or an error mapper converts exceptions into the HTTP contract. The domain layer should preserve meaning and avoid embedding HTTP codes into every business class. A particular status code is an **API contract decision**, not an inherent property of every `IllegalStateException`.

## 3. Behavior Matrix and Required Tests

| Scenario | Correct error/outcome | What the unit test should prove |
|---|---|---|
| SKU `null`, empty, or whitespace-only | Invalid input | Right exception; **catalog not called** |
| Non-positive quantity | Invalid input | Right exception; **catalog not called** |
| Valid SKU and quantity, catalog returns active product with enough stock | Success | Accurate quote, exact dependency call count |
| Product is inactive | Business state | State-conflict exception, not disguised as timeout |
| Stock less than requested quantity | Business state | Rule enforced, no quote produced |
| Catalog HTTP timeout or connection failure | Dependency failure | Error propagated/mapped with the right type, not turned into “bad SKU” or “out of stock” |
| Syntactically valid SKU missing from catalog | Dedicated not found per contract | Not conflated with malformed input data |
| Invalid input while simulated catalog is also failing | Invalid input first | Dependency not called; input error not masked by timeout |
| Adapter returns malformed data violating contract | Contract/internal failure | Not blamed on caller; requires alert and adapter tests |

A test like `assertThrows(RuntimeException.class, ...)` is usually too weak: invalid input, business conflict, and timeout can all be `RuntimeException`. Use **specific exception types** and assertions on side effects/dependency calls where needed.

## 4. Complete Java 17+ Example: Catalog-Based Quoting

Suppose an internal API quotes a SKU:

1. `sku` must be non-blank and `quantity > 0`.
2. Catalog returns a `Product` with `active` status, `available` stock count, and `unitPriceVnd`.
3. Quote only if the product is active and stock is sufficient; total equals price times quantity.
4. Catalog may fail with timeout; a valid SKU that does not exist also has its own error.

This is a **read-only quoting** use case. It does not reserve stock, so it does not prove concurrency safety when two customers buy simultaneously. Actual stock deduction requires transactions/atomic updates or reservations verified in appropriate integration tests.

### 4.1. Production file: separating errors by meaning

Create **`src/main/java/com/example/shop/stock/StockQuoteService.java`**:

```java
package com.example.shop.stock;

import java.util.Objects;

public final class StockQuoteService {

    public record Product(String sku, long unitPriceVnd,
                          int available, boolean active) {
    }

    public record Quote(String sku, int quantity, long totalVnd) {
    }

    // Port: the adapter is responsible for returning Product, or throwing NotFound/Unavailable.
    @FunctionalInterface
    public interface ProductCatalog {
        Product find(String sku);
    }

    public static final class InvalidInputException extends RuntimeException {
        public InvalidInputException(String message) {
            super(message);
        }
    }

    public static final class BusinessStateException extends RuntimeException {
        public BusinessStateException(String message) {
            super(message);
        }
    }

    public static final class ProductNotFoundException extends RuntimeException {
        public ProductNotFoundException(String message) {
            super(message);
        }
    }

    public static final class CatalogUnavailableException extends RuntimeException {
        public CatalogUnavailableException(String message) {
            super(message);
        }
    }

    private final ProductCatalog catalog;

    public StockQuoteService(ProductCatalog catalog) {
        this.catalog = Objects.requireNonNull(catalog, "catalog");
    }

    public Quote quote(String sku, int quantity) {
        // Input is validated before calling the external system.
        if (sku == null || sku.isBlank()) {
            throw new InvalidInputException("sku must not be blank");
        }
        if (quantity <= 0) {
            throw new InvalidInputException("quantity must be positive");
        }

        // Port returns a non-null Product or throws a classified error.
        Product product = catalog.find(sku);
        if (product == null) {
            throw new IllegalStateException("Catalog violated non-null contract");
        }

        // Negative data returned by the catalog is a contract violation, not an input error.
        if (product.available() < 0 || product.unitPriceVnd() < 0) {
            throw new IllegalStateException("Catalog returned invalid product");
        }

        // Check business state only after catalog data is valid.
        if (!product.active()) {
            throw new BusinessStateException("product is inactive");
        }
        if (product.available() < quantity) {
            throw new BusinessStateException("insufficient stock");
        }

        long total = Math.multiplyExact(product.unitPriceVnd(), quantity);
        return new Quote(product.sku(), quantity, total);
    }
}
```

**Why separate these checks?** Blank `sku` or `quantity <= 0` is wrong right from the input, without touching the catalog. `product.active()` and `product.available()` are known only after reading state data. If `catalog.find` throws `CatalogUnavailableException`, the service **does not** catch it to produce `InvalidInputException`; thus the true cause is preserved.

The example explicitly defines the **port contract**: the adapter returns a non-null `Product` when found; throws `ProductNotFoundException` when the product does not exist; throws `CatalogUnavailableException` when the dependency is unavailable. This is an **example design**, not default exceptions thrown automatically by Spring/HTTP clients. A real adapter must catch HTTP/DB/timeout errors by type and translate them to this contract.

One detail worth noting: `available < 0` violates the contract. In real applications, **validate catalog data before applying state rules**, so invalid state is never misreported as “insufficient stock”. Placing negative-data validation before business-state checks ensures accurate error categorization. The complete implementation demonstrates contract checking, and ordering should always be reviewed as adapters and malformed-data tests expand.

### 4.2. Test file: using a fake to separate causes

Create **`src/test/java/com/example/shop/stock/StockQuoteServiceTest.java`**:

```java
package com.example.shop.stock;

import org.junit.jupiter.api.Test;

import com.example.shop.stock.StockQuoteService.BusinessStateException;
import com.example.shop.stock.StockQuoteService.CatalogUnavailableException;
import com.example.shop.stock.StockQuoteService.InvalidInputException;
import com.example.shop.stock.StockQuoteService.Product;
import com.example.shop.stock.StockQuoteService.ProductCatalog;
import com.example.shop.stock.StockQuoteService.ProductNotFoundException;
import com.example.shop.stock.StockQuoteService.Quote;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

class StockQuoteServiceTest {

    private static final class FakeCatalog implements ProductCatalog {
        Product product;
        RuntimeException failure;
        int calls;

        @Override
        public Product find(String sku) {
            calls++;
            if (failure != null) {
                throw failure;
            }
            return product;
        }
    }

    private final FakeCatalog catalog = new FakeCatalog();
    private final StockQuoteService service = new StockQuoteService(catalog);

    @Test
    void blankSkuIsInvalidInputWithoutCatalogCall() {
        assertThrows(InvalidInputException.class,
                () -> service.quote("  ", 2));
        assertEquals(0, catalog.calls);
    }

    @Test
    void zeroQuantityIsInvalidInputWithoutCatalogCall() {
        assertThrows(InvalidInputException.class,
                () -> service.quote("BOOK-1", 0));
        assertEquals(0, catalog.calls);
    }

    @Test
    void activeProductWithStockReturnsQuote() {
        catalog.product = new Product("BOOK-1", 200_000L, 5, true);

        Quote quote = service.quote("BOOK-1", 2);

        assertEquals(new Quote("BOOK-1", 2, 400_000L), quote);
        assertEquals(1, catalog.calls);
    }

    @Test
    void inactiveProductIsBusinessStateError() {
        catalog.product = new Product("BOOK-1", 200_000L, 5, false);

        assertThrows(BusinessStateException.class,
                () -> service.quote("BOOK-1", 1));
        assertEquals(1, catalog.calls);
    }

    @Test
    void insufficientStockIsBusinessStateError() {
        catalog.product = new Product("BOOK-1", 200_000L, 1, true);

        assertThrows(BusinessStateException.class,
                () -> service.quote("BOOK-1", 2));
        assertEquals(1, catalog.calls);
    }

    @Test
    void negativeStockIsInvalidCatalogDataBeforeBusinessChecks() {
        catalog.product = new Product("BOOK-1", 200_000L, -5, false);

        assertThrows(IllegalStateException.class,
                () -> service.quote("BOOK-1", 1));
        assertEquals(1, catalog.calls);
    }

    @Test
    void negativeUnitPriceIsInvalidCatalogDataBeforeBusinessChecks() {
        catalog.product = new Product("BOOK-1", -1L, 5, false);

        assertThrows(IllegalStateException.class,
                () -> service.quote("BOOK-1", 1));
        assertEquals(1, catalog.calls);
    }

    @Test
    void catalogTimeoutRemainsDependencyError() {
        CatalogUnavailableException timeout =
                new CatalogUnavailableException("catalog timeout");
        catalog.failure = timeout;

        CatalogUnavailableException thrown =
                assertThrows(CatalogUnavailableException.class,
                        () -> service.quote("BOOK-1", 2));

        assertSame(timeout, thrown);
        assertEquals(1, catalog.calls);
    }

    @Test
    void missingProductHasItsOwnError() {
        catalog.failure =
                new ProductNotFoundException("BOOK-1 not found");

        assertThrows(ProductNotFoundException.class,
                () -> service.quote("BOOK-1", 2));
        assertEquals(1, catalog.calls);
    }

    @Test
    void invalidInputIsDetectedEvenWhenCatalogWouldFail() {
        catalog.failure =
                new CatalogUnavailableException("catalog unavailable");

        assertThrows(InvalidInputException.class,
                () -> service.quote("", -1));
        assertEquals(0, catalog.calls);
    }
}
```

Both complete files use **Java 17+**, JUnit Jupiter 5+, and require no Spring context. `FakeCatalog` is a port fake matching the `find` method; the `calls` counter proves that invalid inputs do not cause I/O. Specific exception types let tests distinguish the three causes plus the “not found” case.

To run in a Spring Boot project configured with `spring-boot-starter-test` or JUnit Jupiter, inside the module directory containing the wrapper and test configuration:

```bash
# Maven Wrapper: run this class alone
./mvnw -Dtest=StockQuoteServiceTest test

# Or Gradle Wrapper when the test task uses JUnit Platform
./gradlew test --tests "com.example.shop.stock.StockQuoteServiceTest"
```

On Windows, use `mvnw.cmd` or `gradlew.bat`; run only the command matching your project's build tool. Expected outcome: **all test methods PASS**, with no mandatory business stdout. File names, packages, and classes are kept consistent. If Gradle has not configured JUnit Platform, enable `useJUnitPlatform()`; merely placing a file in `src/test/java` does not guarantee the test engine is configured properly.

**Testing limits:** these tests prove the classification rules of the **service under a fake catalog**. They do not prove that a real HTTP/DB adapter maps timeout/404/503 properly to port exceptions, that real transactions work, or that the HTTP handler returns the expected status. Those belong in adapter/integration/web tests respectively.

## 5. Writing Proper Assertions: Cause, Not Just Exception

To make tests diagnostic, verify multiple dimensions of the same behavior:

| Claim to prove | Suitable assertion | Why? |
|---|---|---|
| Input fails before dependency | `assertThrows(InvalidInputException.class, ...)` and `assertEquals(0, catalog.calls)` | Identifies exact error type and confirms zero I/O side effects |
| Product inactive or low stock | `assertThrows(BusinessStateException.class, ...)` | Prevents mislabeling as a network error |
| Catalog timeout | `assertThrows(CatalogUnavailableException.class, ...)` | Gives callers a dependency-failure signal to act on |
| Original exception not wrongly replaced | `assertSame(timeout, thrown)` in the example | Proves the service did not fabricate an input error from a timeout |
| Success | `assertEquals(new Quote(...), quote)` | Protects the business result rather than merely checking no exception occurred |
| Dependency called exact count per case | `assertEquals(1, catalog.calls)` | Prevents unexpected duplicate calls without a retry design |

**A test named “invalidInput...” that only calls `assertNotNull(exception)` is insufficient.** Assert stable messages/rules when they form part of the contract, but avoid pinning tests to internal phrasing that changes trivially. Exception type, meaningful error codes, and side effects are the primary signals.

With Mockito, you can use `verifyNoInteractions(catalog)` on invalid inputs and `verify(catalog, times(1)).find("BOOK-1")` on success, though that is **illustrative syntax** requiring Mockito mocks. The hand-written fake in the complete example keeps the rules clear without extra annotation/mock lifecycle overhead.

## 6. Check Ordering and Invariant Boundaries

A sensible flow for many use cases is:

```text
1. Validate input without I/O
      │ if invalid -> InvalidInput
      ▼
2. Query dependency per port contract
      │ if timeout/unreachable -> DependencyFailure
      │ if not found -> NotFound per contract
      ▼
3. Validate returned data matches internal contract
      │ if schema/impossible values -> Internal/ContractFailure
      ▼
4. Check business state/rules
      │ if unsatisfied -> BusinessStateConflict
      ▼
5. Compute/execute action and return result
```

**Do not turn this diagram into a rigid law for every system.** Some input rules depend on looked-up data, or an operation may require locks/transactions so decisions remain valid at write time. What matters is that each condition has a clear **source of truth** and **result type**; never turn a state-read failure into a conclusion of “business requirement not met”.

In section 4's code, to classify catalog responses with `available < 0` accurately, keep the **negative contract-data check** before `available < quantity`. In real projects, adapter/DTO validation often enforces this invariant while parsing responses. Tests must include dedicated cases for nonsensical data rather than sharing `BusinessStateException` with valid-but-insufficient stock.

## 7. Mapping to HTTP: Suggestions, Not Absolute Rules

In a Spring Boot REST API, classified errors can be mapped to HTTP statuses and stable error codes:

| Error category | HTTP status to consider | Example response message/code |
|---|---|---|
| Request missing/violating validation | **400 Bad Request** or **422 Unprocessable Content** per contract | `INVALID_QUANTITY`, `INVALID_SKU` |
| Valid ID format but resource missing | **404 Not Found** in appropriate resource APIs | `PRODUCT_NOT_FOUND` |
| Current state forbids action | **409 Conflict** or **422** depending on semantics | `PRODUCT_INACTIVE`, `INSUFFICIENT_STOCK` |
| Dependency temporarily unavailable | **503 Service Unavailable**, sometimes **502/504** per gateway role and contract | `CATALOG_UNAVAILABLE` |
| Internal bug/unexpected invariant failure | **500 Internal Server Error** unless mapped more specifically | `INTERNAL_ERROR` |

HTTP statuses and error codes should be **designed consistently at the API boundary**. Not every business exception must map to 409; an API may specify rule errors as 422. There is no rule that “every remote client exception returns 503”; if a remote service returns a structured business rejection, the adapter can interpret it as a business rejection.

When using `@RestControllerAdvice`, keep error responses consistent: machine-readable codes, safe user messages, and request/trace IDs for debugging. Never expose credentials, internal URLs, stack traces, or DB details in responses. Service unit tests verify exception types/causes; a separate **web slice test** proves HTTP mapping, response bodies, and live validation.

### Why not catch every error and throw `InvalidInputException`?

This is an **anti-pattern**:

```java
try {
    return catalog.find(sku);
} catch (Exception ex) {
    throw new InvalidInputException("Invalid SKU");
}
```

This illustration assumes a class where `catalog`, `sku`, and the exception are defined. If the catalog times out, downstream returns 503, code hits an NPE, or mapping breaks, everything gets turned into “Invalid SKU”. Users are told to fix their input pointlessly and the system loses signal of a real outage. When translating library exceptions into port exceptions, **catch the exact transport error group** and preserve the cause:

```java
try {
    return remoteClient.lookup(sku);
} catch (SocketTimeoutException ex) {
    throw new CatalogUnavailableException(
            "catalog request timed out", ex);
}
```

This is also an **adapter snippet**, not a standalone file. It requires `CatalogUnavailableException` to have a constructor accepting `Throwable` and `remoteClient.lookup` to actually throw `SocketTimeoutException`; different Spring HTTP clients use different timeout exception classes. When implementing, catch the exact exception of the client in use while preserving the cause for operational observability.

## 8. Retry, Logging, and Side Effects by Error Category

- **Invalid input:** usually do not retry the same data. Log structured validation codes and avoid logging sensitive payloads in full.
- **Business-state conflict:** usually do not immediately retry the exact same action; wait for state changes or let the user adjust choices. If retrying due to transaction contention, enforce consistent rules and clear limits.
- **Dependency failure:** may retry **only when the error is known to be transient** and the operation is safe to repeat. Use timeouts, backoff, and attempt caps; monitor circuit breakers/metrics as appropriate.
- **Bug/invariant failure:** investigate the data source or code; blind retries usually amplify load and mask the root cause.

Especially for **charging money, creating orders, or publishing events**, a timeout does not prove the action never happened. A request may have been processed remotely while its response was lost. Retrying without an **idempotency key** or duplicate protection risks applying side effects twice. Service unit tests can check retry-decision policies; integration/contract tests must prove the system handles timeouts, idempotency, and transactions across real boundaries.

In logs, distinguish `INPUT_REJECTED`, `STATE_CONFLICT`, and `DEPENDENCY_TIMEOUT` via metrics or structured fields; keep correlation IDs for tracing. Avoid logging every invalid user input at ERROR severity, which creates operational alert noise.

## 9. Common Confusions

1. **Seeing `IllegalArgumentException` and assuming invalid HTTP input.** That exception may come from a bug, library, or internal argument; the source and contract determine its classification.
2. **Seeing upstream HTTP 404 and assuming missing input.** The SKU may be syntactically valid while the resource does not exist, is hidden, or follows another remote contract; design a dedicated not-found path.
3. **Treating downstream HTTP 409/422 as a network failure.** It may be a valid business response; the adapter must inspect schema/codes before deciding.
4. **Treating every 5xx as “out of stock” or “ineligible”.** Lacks state evidence; map it to a dependency failure with an appropriate error code.
5. **Using one generic exception for all failures.** Callers cannot tell whether to fix input, change state, or safely retry.
6. **Asserting only the exception without dependency call counts.** Bad input could still fire network requests or DB writes before failing.
7. **Always mocking dependencies to return business values without testing failure paths.** Unit tests stay green on happy paths while missing adapter/service bugs on timeouts or invalid state.
8. **Confusing business state with contract-violating data.** `available = 0` is valid stock state; `available = -5` usually indicates abnormal upstream data.
9. **Using retries to “solve” invalid input or side-effecting operations.** Retries do not fix bad data and can cause duplicates on timeout.
10. **Putting HTTP codes into domain models and testing everything through MockMvc.** Unit tests should check rules directly on objects; separate web slice/integration tests verify HTTP mapping.

## 10. Checklist Before Finalizing Business Unit Tests

- [ ] I have identified the **source of truth** for each condition: input, entity state, or dependency.
- [ ] Locally checkable input conditions are validated **before calling dependencies**.
- [ ] Business-state violations are not conflated with request-format errors or timeouts.
- [ ] Transport errors and DB/HTTP timeouts are classified meaningfully by adapters, preserving cause when wrapping.
- [ ] Resource not found and contract-violating upstream data are handled by explicit policies.
- [ ] Unit tests check **specific exception types** and behavior, not merely “throws RuntimeException”.
- [ ] For invalid input, tests prove **no dependency call/side effect**; for dependency failure, tests prove no fabricated business outcome.
- [ ] For success, tests check real business outputs, boundary cases, and key invocation counts.
- [ ] HTTP statuses/error codes are verified separately at the controller/advice layer per contract.
- [ ] Retries apply only where appropriate; for side effects, required idempotency/transactions and integration tests exist.

**Core principle:** *Invalid input* can be determined from the request alone; *business state* can only be concluded from trustworthy state data; *dependency failure* means the necessary evidence could not be obtained. Good unit tests keep these three conclusions separate and prove the system performs no unwanted actions when rejecting a request.