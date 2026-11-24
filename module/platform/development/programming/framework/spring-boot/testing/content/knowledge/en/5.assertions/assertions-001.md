# Choosing Observable Outcomes to Verify Behavior in Testing

## 1. Goal: assertions must prove what the user or another system receives

A test typically has three parts: setup (**Arrange**), executing the action (**Act**), and verifying the result (**Assert**). The hardest part is not writing `assertEquals` or `assertThat`, but **choosing which facts to check**.

For example, when a customer reserves 3 items from an inventory of 10, the business contract may require:

1. The system reports that the reservation succeeded.
2. The remaining stock quantity is then 7.
3. No unrequested second reservation occurs.
4. If the requested quantity exceeds the available stock, the system rejects it and **does not mutate** the stock.

Checking only "whether the method returns a non-null object" does not prove those behaviors. Checking "whether the internal method `calculateRemaining()` was called once" is not enough either: the method might be called while the final data is still wrong.

An **observable outcome** is an output or state change that a party entitled to use the system's contract can perceive: a return value, exception/error category, persisted state after the action, HTTP status/body/header, emitted event, saved record, command sent to an external port, and so on. The scope of observation depends on **the boundary of the test**; a unit test sees the state of a fake, whereas an integration test can see data in a real database.

Learning objectives:

- Turn business requirements into one or more **verifiable propositions**.
- Distinguish assertions about **outcomes** from assertions about **implementation details**.
- Choose the right observation target by layer: plain Java, service, web, persistence, messaging, and security.
- Design both success and failure cases, including **what must not happen**.
- Write assertions strong enough to catch real bugs without coupling to details outside the contract.
- Recognize false positives, brittle tests, nondeterministic tests, and state/transaction pitfalls in Spring Boot.

## 2. From requirement to observable contract

Before writing an assertion, answer four questions:

1. **Stimulus:** what specific action is performed, and with what data?
2. **Required outcome:** what must be true after the action?
3. **Forbidden outcome:** what must absolutely not happen?
4. **Observation boundary:** where can the test observe the outcome without depending on how the internal code is written?

A short template:

> Given [initial condition], when [action], then [observable outcome] and [invariant still holds]; if it cannot be performed, then [error/rejection behavior] and [no unintended side effects occur].

Example:

> When stock for `ITEM-7` is 10, reserving 3 items must return `RESERVED` with 7 remaining. When requesting 11 items, it must return `INSUFFICIENT` and stock must remain 10.

There are three common categories of evidence:

| Category | Question the test answers | Examples |
| --- | --- | --- |
| **Output** | What does the caller receive? | `ReservationResult(status=RESERVED, remaining=7)`, HTTP 201, JSON containing `id` |
| **State** | What state can be read afterward? | Balance, database row count, order status |
| **Effect / interaction at the boundary** | What external effect did the system produce? | Publish an event, call a payment gateway, send an email, skip calling an API when input is invalid |

Not every behavior needs all three categories. For a pure pricing function, output is enough. For a write operation, checking output alone can create a **false positive** if the code returns "success" but forgets to save. For a command with no return value, state/effect is where the evidence lives.

An **invariant** is a proposition that must always hold, such as "stock is non-negative", "debits and credits of a journal entry balance", or "each idempotency key leads to at most one business transaction". Invariants are often more worth asserting than the call count of an internal helper.

## 3. Runnable example with Java 17 and JUnit Jupiter

The following example does not need a Spring context. It models a stock reservation service and an in-memory fake repository to focus on choosing assertions. In a Spring Boot project using `spring-boot-starter-test`, JUnit Jupiter is typically already on the test classpath. Run it via the `test` task configured with JUnit Platform.

### 3.1. Production code: `src/main/java/example/StockService.java`

```java
package example;

import java.util.Objects;

public final class StockService {
    public interface StockRepository {
        int quantityOf(String sku);
        void setQuantity(String sku, int quantity);
    }

    public enum Status {
        RESERVED,
        INSUFFICIENT
    }

    public record Result(Status status, int remaining) {}

    private final StockRepository repository;

    public StockService(StockRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public Result reserve(String sku, int amount) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        int available = repository.quantityOf(sku);
        if (available < amount) {
            return new Result(Status.INSUFFICIENT, available);
        }

        int remaining = available - amount;
        repository.setQuantity(sku, remaining);
        return new Result(Status.RESERVED, remaining);
    }
}
```

This is a simplified algorithm for testing purposes. In a real application, a "read quantity then write new quantity" operation must handle concurrency via transactions, optimistic/pessimistic locking, or a conditional update statement. The unit tests below **do not prove concurrency safety**.

### 3.2. Test with a fake repository: `src/test/java/example/StockServiceTest.java`

```java
package example;

import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class StockServiceTest {
    private static final String SKU = "ITEM-7";

    static final class InMemoryStock
            implements StockService.StockRepository {
        private final Map<String, Integer> quantities = new HashMap<>();

        InMemoryStock(int initialQuantity) {
            quantities.put(SKU, initialQuantity);
        }

        @Override
        public int quantityOf(String sku) {
            return quantities.getOrDefault(sku, 0);
        }

        @Override
        public void setQuantity(String sku, int quantity) {
            quantities.put(sku, quantity);
        }
    }

    @Test
    void reservationReportsSuccessAndChangesStock() {
        var stock = new InMemoryStock(10);
        var service = new StockService(stock);

        StockService.Result result = service.reserve(SKU, 3);

        assertAll(
                () -> assertEquals(StockService.Status.RESERVED,
                        result.status()),
                () -> assertEquals(7, result.remaining()),
                () -> assertEquals(7, stock.quantityOf(SKU))
        );
    }

    @Test
    void insufficientStockIsRejectedWithoutMutation() {
        var stock = new InMemoryStock(10);
        var service = new StockService(stock);

        StockService.Result result = service.reserve(SKU, 11);

        assertAll(
                () -> assertEquals(StockService.Status.INSUFFICIENT,
                        result.status()),
                () -> assertEquals(10, result.remaining()),
                () -> assertEquals(10, stock.quantityOf(SKU))
        );
    }

    @Test
    void invalidAmountThrowsAndDoesNotChangeStock() {
        var stock = new InMemoryStock(10);
        var service = new StockService(stock);

        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> service.reserve(SKU, 0)
        );

        assertAll(
                () -> assertEquals("amount must be positive",
                        error.getMessage()),
                () -> assertEquals(10, stock.quantityOf(SKU))
        );
    }

    @ParameterizedTest
    @CsvSource({
        "1, 9",
        "9, 1",
        "10, 0"
    })
    void reservationSupportsBoundaries(int amount, int expectedRemaining) {
        var stock = new InMemoryStock(10);
        var service = new StockService(stock);

        StockService.Result result = service.reserve(SKU, amount);

        assertAll(
                () -> assertEquals(StockService.Status.RESERVED,
                        result.status()),
                () -> assertEquals(expectedRemaining,
                        result.remaining()),
                () -> assertEquals(expectedRemaining,
                        stock.quantityOf(SKU))
        );
    }
}
```

The environment needs the JUnit Jupiter API, `junit-jupiter-params`, and the Jupiter engine. With Spring Boot 3.x / Java 17, a typical Gradle Groovy DSL configuration is:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a snippet added to a **build that already has Spring Boot BOM/repositories configured**, not a standalone `build.gradle` file. Use the project's wrapper:

```bash
./gradlew test --tests example.StockServiceTest
```

On Windows: `.\gradlew.bat test --tests example.StockServiceTest`. The tests print no business stdout; if the assertions pass, the runner marks four test methods as passed, with the parameterized method executing three times. How method names and execution counts are displayed depends on the build/IDE report.

**Why do the three assertions in the success test have distinct value?**

- `result.status() == RESERVED`: the service returned the right status.
- `result.remaining() == 7`: the service reported the right remaining amount.
- `stock.quantityOf(SKU) == 7`: the repository actually received the new state.

If a developer accidentally deletes `repository.setQuantity(sku, remaining)`, the first two assertions can still pass while the last one fails. This shows that **the returned result and the persisted state are not the same piece of evidence**.

If the condition changes from `available < amount` to `available <= amount`, reserving exactly 10 items will fail; that is why boundary values are chosen. If the insufficient-stock branch accidentally deducts inventory, the rejection test still catches the invalid mutation.

### 3.3. Which assertions are too weak?

```java
// Does not prove the final status or data:
assertNotNull(result);

// Too broad if the contract requires specifically RESERVED:
assertTrue(result.status() != null);

// This may just repeat a buggy formula:
assertEquals(10 - amount, result.remaining());

// Derive expected from a business example to catch miscalculations:
assertEquals(7, result.remaining());
```

The snippet above only illustrates different ways of choosing assertions, not a verbatim addition to the test file. `10 - amount` can still be appropriate if it is an **independent, trustworthy oracle**; the risk arises when `expected` is computed using the same algorithm or helper under test, causing a bug to appear on both sides.

### 3.4. Which assertions are too tight?

Suppose the contract only requires returning `RESERVED` and remaining 7, while the service is free to use a repository batch update or an atomic SQL update. A test verifying that "`setQuantity` was called **exactly once**" can break when the implementation changes, even though the external behavior remains correct.

Only check call counts when **the count itself belongs to the contract**: for example, a payment must only be charged once, no duplicate event may be published, or requests must not be retried beyond policy. Call counts on private helpers or cache lookups are usually implementation details that should not be pinned down.

## 4. Criteria for choosing good assertions

A good assertion usually meets six criteria:

1. **Derived from requirements:** a reader can trace the assertion back to a specific rule or contract.
2. **Distinguishes right from wrong:** if the production code violates the rule, the test actually fails.
3. **Observes at the appropriate boundary:** service tests observe return/state/outbound ports; web tests observe HTTP; persistence tests observe the DB.
4. **Minimally coupled to implementation:** valid refactoring, changing helpers, splitting methods, or optimizing structure does not break the test unnecessarily.
5. **Pinpoints the cause:** the message, test name, and fixture indicate which case broke.
6. **Stable across reruns:** does not depend on execution order, machine clock, shared data, or uncontrolled latency.

Examples:

| Requirement | Appropriate assertion | Insufficient or brittle assertion |
| --- | --- | --- |
| Free shipping when total ≥ 500,000 | `assertEquals(0, fee(500000))` | `fee >= 0` |
| Reservation updates stock | Success status **and** querying stock shows 7 remaining | Only `result != null` |
| Invalid input must be rejected | Proper error type/HTTP status **and** state unchanged | Only checking for an ERROR log |
| Resource created successfully | HTTP 201, valid `Location`, GET by URL finds resource | Only 2xx, or only calling `repository.save` |
| Do not charge twice | Actual transactions/charges or outbound port ≤ 1 per contract | Counting calls to an internal helper |
| Event carries right data | Event type, key, business payload, correlation id | Any message appearing |
| Do not leak others' data | 403/404 per policy, response omits data, DB unchanged | Only checking controller method returns non-null |

For a complex object, assert **the fields that belong to the contract**. Comparing the entire object can be useful when every field is meaningful; however, an overly broad snapshot breaks when unimportant metadata changes. Conversely, omitting critical fields like `currency` or `ownerId` weakens the test.

## 5. Observable outcomes by Spring Boot layer

A behavior can be observed from multiple layers. Choose the lowest observation point that sufficiently proves the risk under consideration.

| Test type | Action | Valuable observation points |
| --- | --- | --- |
| Java unit test | Call method/constructor | Return value, exception, object state |
| Service unit test | Call use case with fake/mock | Business result, fake state, important outbound commands |
| MVC slice `@WebMvcTest` | Send request via `MockMvc` | HTTP status, headers, JSON, validation/error mapping |
| JPA slice `@DataJpaTest` | Write/read entity/repository | Queried data, relationships, constraints, persistence behavior |
| `@SpringBootTest` + `MockMvc` | Request passes through real beans | HTTP response + DB data or related effects |
| `RANDOM_PORT` | Send HTTP to a listening server port | Status, content type/body, headers, cookies, network contract |
| Kafka/queue/integration | Send command or change input | Event received by broker/consumer, payload, final state |
| Security test | Access with specific principal/role | Allow/deny response, no data leakage, no forbidden effect |

**Observe at a narrow boundary first; widen when evidence is missing.** A `@WebMvcTest` with a mocked service can prove controller mapping and the JSON contract, but it does not prove that JPA saved correctly. A repository unit test using a fake does not prove real SQL. A full integration test can prove the whole flow, at the cost of being slower and harder to isolate.

### 5.1. Web: assert the HTTP contract instead of controller internals

Suppose `POST /api/reservations` accepts:

```json
{"sku":"ITEM-7","amount":3}
```

and, when stock is sufficient, returns HTTP 200:

```json
{"status":"RESERVED","remaining":7}
```

Below is an illustrative controller compatible with Spring MVC 6 / Boot 3.x, using `StockService` from section 3. File `src/main/java/example/StockController.java`:

```java
package example;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/reservations")
public class StockController {
    private final StockService service;

    public StockController(StockService service) {
        this.service = service;
    }

    public record ReserveRequest(String sku, int amount) {}

    @PostMapping
    public StockService.Result reserve(@RequestBody ReserveRequest request) {
        return service.reserve(request.sku(), request.amount());
    }
}
```

MVC slice test for Spring Boot 3.3.x: `src/test/java/example/StockControllerWebTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(StockController.class)
class StockControllerWebTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    StockService service;

    @Test
    void exposesStatusAndRemainingStockInJson() throws Exception {
        when(service.reserve("ITEM-7", 3))
                .thenReturn(new StockService.Result(
                        StockService.Status.RESERVED, 7));

        mvc.perform(post("/api/reservations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"sku":"ITEM-7","amount":3}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("RESERVED"))
                .andExpect(jsonPath("$.remaining").value(7));
    }
}
```

This snippet requires the Spring MVC runtime and an appropriate Spring Boot starter test dependency, a `@SpringBootApplication` configuration discoverable from the test package, and Boot 3.3.x. In Boot 3.4+ with Spring Framework 6.2+, Spring Framework's `@MockitoBean` is the replacement for `@MockBean`; in Boot 4.x, MVC test packages/modules also change. When a project has Spring Security filters, appropriate authentication/CSRF setup is required; an unexpected HTTP 401/403 may be a security test configuration issue. Do not copy Boot 3.3 annotations/imports verbatim to all Boot 4.x setups.

**What is proven:** route, JSON input, MVC dispatch, and output serialization/status assuming the service returns the right data. **What is not yet proven:** that the service deducts stock properly and the repository actually persists it, because the service is mocked. That is why the unit tests in section 3 are still necessary.

If the API contract also specifies `Content-Type: application/json`, a version header, `Location`, 400/409 error codes, or an error body format, add the corresponding assertions. Do not require the response body to match a raw JSON string character-for-character just because key ordering or whitespace differs, unless the contract specifies it.

### 5.2. Persistence: assert queryable state

For a JPA repository, persistence behavior should be verified through a **meaningful query**:

```java
// Illustrative snippet inside a @DataJpaTest with the corresponding entity/repository:
repository.saveAndFlush(new StockEntity("ITEM-7", 7));
entityManager.clear();

StockEntity reloaded = repository.findById("ITEM-7")
        .orElseThrow();

assertEquals(7, reloaded.getQuantity());
```

This is an **illustrative snippet**, not a standalone program: it requires `StockEntity`, `StockJpaRepository`, `EntityManager`, and appropriate imports. `saveAndFlush` requires a repository that supports that method, typically via `JpaRepository`.

Because JPA has a **first-level persistence context cache**, retrieving the same managed instance sometimes only proves in-memory state rather than verifying the database write/read cycle intended by the test. `flush` pushes pending changes to the database within the transaction, and `clear` detaches managed entities to force a re-query; whether the test uses a transaction and rolls back is another detail to verify. If the goal is to prove that data was **committed** and visible from another request/transaction, test with real transaction boundaries and do not blindly trust rollback tests.

When verifying schema constraints, unique keys, optimistic locking, isolation, or SQL dialect behavior, use a database sufficiently close to production (commonly via Testcontainers). A fake or H2 cannot prove every PostgreSQL/MySQL behavior.

### 5.3. Multi-layer service integration: assert at both ends

For a write use case, a `@SpringBootTest` + `@AutoConfigureMockMvc` test can verify both ends simultaneously:

```text
POST /api/reservations
      |
      v
Correct HTTP status/body       ← assertion 1
      |
Controller → Service
      |
Repository → Database
      |
re-read persisted data         ← assertion 2
```

Both ends show that the system both returns the right HTTP contract and performs the real effect. If you only verify `repository.save(...)`, the test does not prove transaction commit/constraints or that the data can be read back. If you only assert status 200, the implementation could return success while writing nothing.

By default, `@SpringBootTest` does not open a real HTTP port; with `@AutoConfigureMockMvc`, requests go through a mock servlet environment. `@SpringBootTest(webEnvironment = RANDOM_PORT)` starts a real HTTP server; transactions on the test thread and server thread can be separate, so `@Transactional` on the test does not automatically guarantee rollback of data committed by the server.

### 5.4. Events and outbound APIs: sometimes the interaction **is** the outcome

When the application is required to "send a charge command exactly once", the call to `PaymentGateway` is the observable effect at the **external boundary**. If the test cannot connect to the real payment system, mocking or faking the gateway is a reasonable tool.

```java
// Illustrative snippet inside a unit test where PaymentGateway and CheckoutService are declared:
var gateway = mock(PaymentGateway.class);
var service = new CheckoutService(gateway);

service.checkout("order-42", 120_000L);

verify(gateway, times(1)).charge("order-42", 120_000L);
```

This snippet is intentionally **not standalone** because it depends on the application's `PaymentGateway` and `CheckoutService` contracts. `verify(..., times(1))` makes sense when the contract forbids charging twice. For internal interactions not in the contract, asserting exact call counts can make tests brittle under refactoring.

If the goal is to verify the outbound HTTP request itself, testing against a mock HTTP server (WireMock or an equivalent) provides stronger evidence of method, URL, headers, body, and error handling. For a message broker, verifying `publisher.send` alone does not prove the broker received it or that the consumer processed it; use an integration test at the broker boundary when that is the risk you need to check.

## 6. Choosing both allowed outcomes and effects that **must not happen**

Many severe bugs live on the **failure path**. A "fails properly" test has two halves:

- **Proper rejection:** exception/error code/HTTP status/message per contract.
- **No forbidden effect:** do not charge money, do not reduce stock, do not write an order, do not emit a success event.

Example of requesting 11 items when stock only has 10:

```java
var stock = new InMemoryStock(10);
var service = new StockService(stock);

var result = service.reserve("ITEM-7", 11);

assertEquals(StockService.Status.INSUFFICIENT, result.status());
assertEquals(10, stock.quantityOf("ITEM-7"));
```

This excerpt is based on `InMemoryStock` from section 3. If you omit the second assertion, the test could pass while the system both rejects the request and silently deducts stock.

For APIs, consider these scenarios:

| Scenario | Returned outcome | Forbidden side effect |
| --- | --- | --- |
| Invalid input | 400 with error code per contract | No data written |
| Unauthenticated | 401 | Protected business logic not executed |
| Insufficient permissions | 403 or 404 per policy | Resource not leaked / data not modified |
| Conflict or out of stock | 409 or corresponding business code | No successful reservation created |
| Resource does not exist | 404 | Other resources not modified |
| Duplicate payment request | Per idempotency contract | Not charged a second time |
| External dependency timeout | Specified error / retry path | No fake success outcome produced |

These are **illustrative contracts**; Spring Boot does not automatically generate all of the HTTP statuses above by default. The application needs proper validation, exception mapping, security, and transaction behavior to satisfy them.

## 7. Matching assertion precision to contract precision

### 7.1. Exact match when the contract is exact

Integer monetary amounts, enum statuses, error codes, or stock quantities usually need **exact** values:

```java
assertEquals(7, remaining);
assertEquals("INSUFFICIENT_STOCK", errorCode);
```

Do not downgrade to `assertTrue(remaining >= 0)` when the goal is to verify that exactly 3 items were deducted.

For decimals, money, and floating-point numbers:

- Use `BigDecimal` for most monetary calculations and define scale/rounding per business rules.
- For scientific floating-point numbers, use a tolerance matching the specification, e.g., `assertEquals(expected, actual, 1e-9)` if that precision is allowed.
- Do not add overly wide tolerances that let calculation bugs slip through.
- With `BigDecimal`, `equals` distinguishes scale (`1.0` differs from `1.00`); if the contract treats them as numerically equal, consider `compareTo` or AssertJ's `isEqualByComparingTo`.

### 7.2. Ranges, collections, ordering, and uniqueness

If the contract only requires "at least one result" or "every result has status active", check that exact property. Do not enforce list ordering if the API does not guarantee sorting.

Examples with AssertJ:

```java
// Order is specified by the contract:
assertThat(ids).containsExactly("A", "B", "C");

// Order is unspecified, but exact values and counts must match:
assertThat(ids).containsExactlyInAnyOrder("A", "B", "C");

// Only uniqueness is required:
assertThat(ids).doesNotHaveDuplicates();
```

These three lines are options for **three different contracts**, not meant to appear together in the same test. `ids` is a list prepared in the actual test.

### 7.3. Time, random IDs, and metadata

Do not hard-code randomly generated timestamps or UUIDs if the contract does not promise fixed values. Instead:

- Inject `Clock.fixed(...)` into the service if you need to verify an **exact point in time** deterministically.
- For generated IDs, verify format, non-emptiness, uniqueness, or GET the resource back by that ID if that is part of the contract.
- For server-generated timestamps, check relationships like `createdAt <= updatedAt` and meaningful time bounds; do not assert real-world wall-clock time that can drift in CI.
- Do not pin headers like `Date`, `Server`, or JSON field order unless the contract requires them.

### 7.4. Error messages

An error message is an observable outcome **if the API/contract requires it to be stable**. For internal Java errors, the exception class and preserved state are usually enough; asserting every period in a message can be overly tight if the message is only for developers.

```java
assertThrows(IllegalArgumentException.class,
        () -> service.reserve("ITEM-7", 0));
```

If an API provides a stable `errorCode` and a localized `message`, prefer asserting the exact `errorCode` and minimal required schema/message; do not pin English wording if it can vary by locale.

## 8. Multiple assertions in one test: how many is enough?

A useful rule is **one behavioral scenario**, not "strictly one assert statement". A business outcome can require multiple complementary assertions, for example:

```java
assertAll(
        () -> assertEquals(StockService.Status.RESERVED,
                result.status()),
        () -> assertEquals(7, result.remaining()),
        () -> assertEquals(7, stock.quantityOf("ITEM-7"))
);
```

JUnit Jupiter's `assertAll` collects failures from assertions that can execute independently, helping report multiple discrepancies within the same scenario. Do **not** use it to chain a long sequence of interdependent actions or mix different use cases into a single test.

Split into separate tests when:

- Initial conditions differ significantly (in stock vs. out of stock).
- State must be reset independently.
- Failures would have different causes or contracts.
- The scenario becomes hard to read due to branching.

You can extract helpers for Arrange and domain-meaningful assertions, but avoid hiding all expected logic inside complex helpers. A name like `assertOrderPersistedWithTotal(...)` can be helpful when many tests share the same contract, provided the helper actually checks the critical fields.

## 9. Test oracle: where does `expected` come from?

A **test oracle** is an independent basis for knowing the right result. An oracle can be a specification, a business rule table, an approved example, an independent mathematical/invariant check, or a trusted reference system.

Good oracle sources:

1. **Clear specification:** "free shipping threshold at 500,000".
2. **Approved input/output table:** boundary values, error cases, authorization policies.
3. **Mathematical/business invariant:** after transferring money between two accounts with no fee, the sum of balances is unchanged.
4. **Metamorphic relation:** increasing a valid reservation quantity by one unit decreases remaining stock by one unit, given the same initial stock.
5. **Reference system:** only when you clearly understand its reliability and scope of comparison.

Common sources of false positives:

- Computing `expected` using the very method under test.
- Calling the same production helper in both Act and expected, then concluding the algorithm is correct.
- Asserting post-Act data from an object mutated by the **same source**, rather than observing through the proper storage port.
- Copying a response snapshot generated by current code and accepting it blindly without checking the contract.
- Asserting `true` simply because the build threw no exception.

**Independent oracle example:** with initial stock 10 and reserving 3, `expected = 7` comes from the known rule; there is no need to call a production `calculateRemaining` method to compute `expected`.

## 10. Assertion strength and deliberate fault testing

A very effective self-review technique is to ask:

> If I deliberately introduce a small, important bug into the code, will this assertion turn red?

For `StockService` in section 3, imagine these mutations:

| Deliberate mutation | Assertion that must catch it |
| --- | --- |
| Change `available < amount` to `available <= amount` | Case reserving exactly 10/10 |
| Delete `repository.setQuantity(...)` | Assertion reading quantity back from the fake |
| Return `RESERVED` even when stock is insufficient | Status assertion in the insufficient-stock branch |
| Still deduct stock when rejecting | Stock-unchanged assertion |
| Return `remaining = available` even after deducting stock | Assertion on `result.remaining` |
| Remove `amount <= 0` validation | Exception and state assertions |

You can run controlled experiments on a branch/sandbox and revert afterward; mutation testing tools can generate similar mutations automatically. You do not have to force every single assertion to catch every mutation; what matters is that **the test suite for a contract** catches meaningful deviations from that contract.

**100% line coverage does not mean good assertions.** Tests can execute every line while only calling methods and running `assertNotNull`. Mutation testing gives an additional perspective on fault-detection power, though mutation score also does not replace contract review and integration tests at critical boundaries.

## 11. When there are multiple users or asynchronous execution

### 11.1. Concurrency and transactions

A sequential unit test only proves behavior under sequential execution. With stock equal to 1 and two concurrent requests each reserving 1 item, the required invariant is that **two reservations cannot both succeed if both consume the single unit**.

Proving this invariant requires tests with real transactions/requests, explicit synchronization mechanisms, and observation of both final data and both task outcomes. The `HashMap`-based unit test in section 3 does not prove atomicity or race-condition safety; production code needs appropriate optimistic/pessimistic locking or conditional updates.

When testing the DB:

- Check which transaction committed/rolled back and which thread owns the transaction.
- If the result must survive commit, read from an appropriate transaction/connection rather than looking only at a managed entity.
- Isolate test data; do not let test execution order or another test's data determine the outcome.

### 11.2. Eventual consistency and message queues

For consumers processing events asynchronously, the requirement is usually "the result eventually appears within a bound" rather than "within one millisecond".

Avoid:

```java
// Fragile: CI speed is not guaranteed.
Thread.sleep(1000);
assertEquals("PAID", readOrderStatus());
```

Instead, wait on a **condition** with a bounded timeout (for example, Awaitility if the appropriate test dependency is declared):

```java
// Illustrative snippet, requires Awaitility on the test classpath:
await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
            assertEquals("PAID", readOrderStatus()));
```

These two snippets illustrate waiting strategies, not standalone runnable programs: `readOrderStatus()` must be implemented; `await()` comes from Awaitility and `Duration` from Java. Choose timeouts based on SLA/test environment, and do not arbitrarily inflate timeouts to hide race conditions.

Assert additional invariants when required by the business: the event's effect is applied only once, correlation ID is preserved, failing messages go to DLQ, and retries do not create duplicate records. Counting messages on a topic alone is not enough to prove the consumer applied them properly.

## 12. Separating test assertions from test setup logic

Reliable tests separate three kinds of code:

- **Fixture/Arrange:** create users, initial stock, database rows, stub responses.
- **Act:** invoke the single action under test.
- **Assert:** read the outcome independently and compare against the contract.

Example to avoid:

```java
var result = service.reserve("ITEM-7", 3);
// Bad: mutating state after Act before asserting.
stock.setQuantity("ITEM-7", 7);
assertEquals(7, stock.quantityOf("ITEM-7"));
```

Here the test fixes the state itself after the action, so it can pass even if the service does nothing. Similarly, test data builders with side effects that save to the DB or publish events on their own can mask system bugs.

A trustworthy test must **establish its own initial state**, interact only through the behavior under test during Act, and then observe the outcome. If post-test cleanup is needed, cleanup must not participate in "making the result right" before assertions run.

For HTTP/JSON APIs, assertions should read **the actual response of the request just sent**; for the DB, prefer querying by business key/ID to verify that the right data appeared. For fakes, keep them simple and verifiable so the fake does not turn into a second complex system.

## 13. Common assertion mistakes in practice

| Symptom | Problem | How to improve |
| --- | --- | --- |
| `assertTrue(true)` or a test with no assertions | No proof of behavior | Add concrete outcomes to prove |
| `assertNotNull(response)` for every endpoint | Weak test; wrong status/body still passes | Assert status, JSON fields, and related effects |
| `verify(privateHelper, times(1))` | Coupled to implementation structure | Assert output/state; only verify outbound contracts |
| Comparing raw JSON strings | Brittle to whitespace/key order | Use JSONPath/object fields/schema per contract |
| Asserting full DTO with random timestamp/UUID | Flaky on unstable data | Fix `Clock` or assert required properties |
| Asserting status 200 for resource creation | May be too weak if contract specifies 201/Location | Match the exact HTTP contract |
| Asserting only success response on DB writes | Misses "returns success without saving" bugs | Re-read persisted state in integration tests |
| Asserting only exception, not state | May have deducted money/stock before throwing | Assert forbidden effects did not occur |
| Reusing data from another test | Order-dependent, prone to flaking | Create independent fixtures and cleanup |
| Fixed sleep before async assertion | Flaky on slow CI | Wait on condition with a timeout |
| Asserting total row count in a shared DB | Affected by concurrent data | Isolate DB/schema or filter by business ID |
| Asserting on a still-managed JPA entity | May only observe first-level cache | Flush/clear, re-query, and check transaction |
| Relying only on a fake to conclude real SQL works | Fakes do not enforce constraints or SQL dialect | Add `@DataJpaTest`/integration tests with an appropriate DB |

Failure analysis should also respect boundaries: JSON/body errors belong to the web contract; a container failing to start is an environment issue rather than a reason to alter business expectations; timeouts require investigating latency/races rather than raising timeouts indefinitely.

## 14. Questions to ask before coding assertions

Use a simple decision tree:

```text
What behavior needs verification?
    |
    +-- Pure calculation function?
    |      -> assert return values/exceptions and boundary values.
    |
    +-- Command mutating state?
    |      -> assert response + re-read state + invariants.
    |
    +-- Calling an external port?
    |      -> assert command/payload/idempotency;
    |         mock port in unit tests, real protocol in integration if needed.
    |
    +-- HTTP API?
    |      -> assert status + headers/body/schema per contract;
    |         add DB/effect checks when proving the full flow.
    |
    +-- Async processing?
    |      -> assert final outcome using condition wait with timeout;
    |         verify no duplicates or forbidden effects.
    |
    +-- Rejection/exception?
           -> assert proper error + unchanged state/effects.
```

Test-writing checklist:

- [ ] I can state the behavior being proven in one clear business sentence.
- [ ] The test makes clear the initial condition and the single action under observation.
- [ ] `expected` comes from the contract or an independent oracle, not by copying production logic.
- [ ] Assertions are specific enough to catch a real bug that users care about.
- [ ] If the behavior mutates state, I verified post-action state where needed.
- [ ] If the behavior fails, I verified forbidden side effects did not happen.
- [ ] If checking mock interactions, I confirmed they represent a **contract boundary**, not internal details.
- [ ] The test does not rely on random timestamps, unguaranteed data ordering, a shared DB, or fixed sleeps.
- [ ] I know what the test **cannot prove** (real SQL, transactions, real HTTP, concurrency, etc.).
- [ ] When deliberately breaking key logic, at least one relevant assertion turns red.

## 15. Practice exercises with guided answers

**Exercise 1 — Catching a false success.** In `StockService.reserve`, temporarily delete `repository.setQuantity(sku, remaining)` in the sufficient-stock branch. Run `reservationReportsSuccessAndChangesStock`. The two output assertions may pass, but the state assertion must fail. Restore the code immediately after testing. Takeaway: when a behavior requires writing state, the test should read state back.

**Exercise 2 — Catching a boundary bug.** Change `available < amount` to `available <= amount`. Run the parameterized case reserving 10/10. Expecting `RESERVED` and remaining 0 must make the test fail. Restore the code. Takeaway: choosing boundary values is more valuable than testing only middle-range inputs.

**Exercise 3 — Writing the rejection path.** With stock = 10 and amount = 11, write a test asserting only `INSUFFICIENT`. Then deliberately mutate the code to deduct stock before returning the error: does the test still pass? Add `assertEquals(10, stock.quantityOf(SKU))` to catch the forbidden effect.

**Exercise 4 — From unit to HTTP.** Using the controller in section 5, state the exact endpoint contract: success 200 and JSON `status=RESERVED, remaining=7`. With `@WebMvcTest`, assert both status and both fields; explain why this test does not prove the database changed. To prove that, design an integration test with a real repository and re-read state.

**Exercise 5 — Reviewing assertions.** Classify the following assertions as "strong and contract-aligned", "too weak", or "too tight":

| Candidate assertion | When is it reasonable? |
| --- | --- |
| `assertNotNull(receipt)` | Only when non-null is literally the entire contract; insufficient for most payment problems |
| `assertEquals("PAID", receipt.status())` | When the status must be exact |
| `verify(gateway, times(1)).charge(...)` | When charging exactly once is an important effect |
| `verify(repository, times(2)).findById(...)` | Usually too tight if caching or refactoring is allowed |
| `assertEquals(7, queryStock("ITEM-7"))` | When the behavior requires the new stock to equal 7 |
| `assertEquals(expectedRawJsonString, responseBody)` | Only if exact bytes/characters are part of the contract, which is rare for standard JSON APIs |

**Completion criteria:** learners can not only write syntactically valid assertions, but also explain (a) the **contract** behind each assertion, (b) which **mutations** it catches, and (c) the **evidence gaps** of the chosen test level.

## Official references

- JUnit User Guide — assertions, grouped assertions, exception testing, parameterized tests: https://docs.junit.org/current/user-guide/
- AssertJ — object, collection, exception and field assertions: https://assertj.github.io/doc/
- Mockito — mocking, stubbing, verification: https://site.mockito.org/
- Spring Framework — MockMvc: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html
- Spring Boot — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Spring Framework — Testing Transactions: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
