# Spring Boot Test Matrix: Happy Path, Invalid Input, Boundary Values, and Dependency Failures

## 1. Purpose and How to Read the Matrix

A test-case matrix turns **business rules and API contracts** into executable scenarios with expected outcomes and concrete verification evidence. In Spring Boot, four groups should be clearly separated:

- **Happy path:** valid request, business operation succeeds; verify both the return value **and** proper side effects.
- **Invalid input:** missing fields, wrong types, malformed formats, or constraint violations; the request must be rejected before calling dependencies or persisting data.
- **Boundary values:** tests just below, at, and just above allowed thresholds. Valid boundaries belong in the happy path group; invalid boundaries belong in the invalid input group.
- **Dependency failure:** a downstream service, database, or external system returns an error, times out, loses connection, or returns an unfulfilled business result. You must distinguish **business rejection** from **technical failure**.

Each row must answer: what are the initial conditions, what action is performed, what response is correct, which components are/are not called, and what side effects must be verified. Never treat a single HTTP status code as enough to declare PASS.

## 2. Lock Down the Sample Contract Before Building the Matrix

Consider an illustrative Spring Boot API: `POST /api/orders`, creating an order for an item SKU. This is a **sample contract defined for this lesson**, not a universal default for every system.

JSON request:

```json
{
  "sku": "SKU-01",
  "quantity": 5
}
```

Rules:

1. `sku` is a string that is non-`null`, non-empty, and not whitespace-only.
2. `quantity` must be present, an integer, and within **1 to 10**, inclusive.
3. When the data is valid, the system calls `InventoryPort.reserve(sku, quantity)` once to reserve stock. Returning `true` means stock was reserved; `false` means out of stock.
4. If reservation succeeds, return `201 Created` and JSON containing a non-blank `orderId`. A real application may also persist the order; if so, verify it is saved exactly once.
5. Invalid request data → `400 Bad Request`, without calling the inventory system. Business out-of-stock → `409 Conflict`. Unavailable inventory dependency, connection failure, timeout, or technical 5xx response translated by the adapter into a dependency failure → `503 Service Unavailable`.
6. The adapter and exception-handling mechanism must genuinely implement the mappings in item 5. If your product uses `422`, `502`, or `504`, update expected outcomes according to the approved contract rather than tweaking tests to fit arbitrary behavior.

Sample Spring Boot 3+ DTO using Jakarta Bean Validation:

```java
package example;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateOrderRequest(
    @NotBlank String sku,
    @NotNull @Min(1) @Max(10) Integer quantity
) {}
```

The controller needs `@Valid @RequestBody CreateOrderRequest request` and the `spring-boot-starter-validation` dependency. Use `Integer` to distinguish missing/`null` fields from `0`; if primitive `int` is used, missing data may default to `0`, making error semantics unclear. `@Min`/`@Max` check value bounds, not JSON parsing itself. Malformed JSON or `quantity: "abc"` is typically rejected by the JSON deserialization layer before Bean Validation runs.

## 3. Sample Test-Case Matrix

IDs M01–M19 are stable identifiers linking requirements, automated tests, and test runs. The “Inventory” column describes stubbed/mocked dependency responses; “Not called” is a **mandatory assertion** for invalid inputs.

| ID | Category | Data or Scenario | Inventory | Expected Result and Evidence |
| --- | --- | --- | --- | --- |
| M01 | Normal happy path | `sku=SKU-01`, `quantity=5` | `true` | `201`; non-blank `orderId`; calls `reserve("SKU-01", 5)` once |
| M02 | Valid lower boundary | `quantity=1` | `true` | `201`; calls inventory with exact value `1` |
| M03 | Valid upper boundary | `quantity=10` | `true` | `201`; calls inventory with exact value `10` |
| M04 | Invalid input | Missing `sku` field | Not called | `400`; inventory not called / order not created |
| M05 | Invalid input | `sku="   "` | Not called | `400`; confirms `@NotBlank` rejects whitespace-only strings |
| M06 | Invalid input | Missing `quantity` field | Not called | `400`; inventory not called |
| M07 | Invalid input | `quantity=null` | Not called | `400`; inventory not called |
| M08 | Just below lower boundary | `quantity=0` | Not called | `400`; inventory not called |
| M09 | Negative value | `quantity=-1` | Not called | `400`; inventory not called |
| M10 | Just above upper boundary | `quantity=11` | Not called | `400`; inventory not called |
| M11 | Far out of bounds | `quantity=2147483647` | Not called | `400`; inventory not called; no integer overflow in processing |
| M12 | Wrong type | `quantity="abc"` | Not called | `400` because it cannot parse as an integer; inventory not called |
| M13 | Broken JSON | JSON missing closing brace | Not called | `400`; inventory not called; error returned safely |
| M14 | Business rejection | Valid request `quantity=5` | `false` | `409`; order not created; not turned into `503` |
| M15 | Dependency timeout | Valid request | Timeout mapped by adapter to dependency exception | `503` per sample contract; no stack trace exposed |
| M16 | Dependency connection failure | Valid request | Connection refused / network error | `503`; no false success reported |
| M17 | Dependency returns 5xx | Valid request | HTTP `500`/`503` from inventory | `503` after adapter mapping; no-order-created rule preserved |
| M18 | Dependency abnormal response | Valid request | Payload violates schema, treated as unavailable by adapter | `503` if that is adapter policy; must have adapter test confirming classification |
| M19 | Error precedence | `quantity=0` **and** inventory is down | Must not be called | `400`; no inventory call made; avoids `503` masking input validation error |

**The core boundary quartet** for integer range `[1, 10]` is `0, 1, 10, 11`: two valid points and two invalid points. `-1` and huge integers are extra risk-based cases. If the contract changes (for example, raising the max to 100), update boundaries and test data together.

M18 should only be asserted as `503` when the adapter defines malformed responses as “dependency unavailable”; other systems might use `502 Bad Gateway`. Never guess from an error that the HTTP layer happens to emit by accident.

## 4. Turning the Matrix into Executable Checks

A quality test needs **arrange (input)**, **act (action)**, and **assert (PASS condition)**. Beyond the status code, check:

| Category | HTTP Boundary Assertions | Service/Adapter Assertions | Side Effects |
| --- | --- | --- | --- |
| Success | `201`, `orderId` content and structure | Calls inventory with right `sku`, `quantity`, call count | If a repository exists, saves exactly one order; never twice |
| Invalid input | `400` and matching error contract | Does not call service or inventory before validation passes | Nothing saved, no events published, no stock reserved |
| Boundary | `1` and `10` accepted; `0` and `11` rejected | Boundary values passed unchanged to service | No implicit rounding, casting, or bound shifting |
| Out of stock | `409` and safe business error details | `reserve` returns `false` | Order not created |
| Technical dependency failure | `503` per contract, no internal details leaked | Adapter classifies timeout, connection error, upstream 5xx accurately | No “success” state recorded; check consistency and retry rules |

Do not only assert `verify(inventory).reserve(...)`: on invalid-input paths, `verifyNoInteractions(inventory)` or `verifyNoInteractions(orderService)` at the right layer proves the request never penetrated deeper into the system. When multiple components exist, also verify repositories, event publishers, and important side effects.

When error responses use a standard body like Problem Details (`application/problem+json`), assert the published fields (`status`, `type`, `title`, or `detail` per contract); do not hardcode unstable internal messages, stack traces, or timestamps.

## 5. Runnable JUnit Jupiter + Mockito Service Example

The example below is **a single self-contained Java 17 test file**, placed at `src/test/java/example/OrderServiceTest.java` in a project with JUnit Jupiter and Mockito (typically included via `spring-boot-starter-test`). The nested classes serve as minimal fixtures illustrating M01–M03 and M14–M16; in a real project, replace them with your application's `OrderService` and `InventoryPort`.

```java
package example;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class OrderServiceTest {
    interface InventoryPort {
        boolean reserve(String sku, int quantity);
    }

    static class OutOfStockException extends RuntimeException {}
    static class DependencyUnavailableException extends RuntimeException {}

    static class OrderService {
        private final InventoryPort inventory;

        OrderService(InventoryPort inventory) {
            this.inventory = inventory;
        }

        String create(String sku, int quantity) {
            if (!inventory.reserve(sku, quantity)) {
                throw new OutOfStockException();
            }
            return UUID.randomUUID().toString();
        }
    }

    @ParameterizedTest
    @ValueSource(ints = {1, 5, 10})
    void validQuantityReservesExactlyOnce(int quantity) {
        InventoryPort inventory = mock(InventoryPort.class);
        when(inventory.reserve("SKU-01", quantity)).thenReturn(true);

        String orderId = new OrderService(inventory)
                .create("SKU-01", quantity);

        assertNotNull(orderId);
        assertFalse(orderId.isBlank());
        verify(inventory).reserve("SKU-01", quantity);
        verifyNoMoreInteractions(inventory);
    }

    @Test
    void noStockProducesBusinessFailure() {
        InventoryPort inventory = mock(InventoryPort.class);
        when(inventory.reserve("SKU-01", 5)).thenReturn(false);

        OrderService service = new OrderService(inventory);

        assertThrows(OutOfStockException.class,
                () -> service.create("SKU-01", 5));
        verify(inventory).reserve("SKU-01", 5);
        verifyNoMoreInteractions(inventory);
    }

    @Test
    void unavailableInventoryDoesNotBecomeSuccess() {
        InventoryPort inventory = mock(InventoryPort.class);
        when(inventory.reserve("SKU-01", 5))
                .thenThrow(new DependencyUnavailableException());

        OrderService service = new OrderService(inventory);

        assertThrows(DependencyUnavailableException.class,
                () -> service.create("SKU-01", 5));
        verify(inventory).reserve("SKU-01", 5);
        verifyNoMoreInteractions(inventory);
    }
}
```

Run in a Maven project with test libraries configured: `mvn test -Dtest=OrderServiceTest` (if the project uses the Maven Wrapper, you can run `./mvnw test -Dtest=OrderServiceTest`, or `mvnw.cmd` on Windows). The tests print no stdout by design; PASS/FAIL results are reported by Maven/JUnit. Do not assert the exact randomly generated UUID: in this example, verifying that a non-blank ID is generated upon successful reservation is sufficient.

**Intentional limitation:** the fixture's `OrderService` includes no HTTP, Bean Validation, or repository, so these tests **do not prove** `400`/`409`/`503`, transactions, or persistence. That belongs to controller, adapter, and integration tests at their respective layers.

## 6. Testing HTTP and Bean Validation with MockMvc

In a real application, use `@WebMvcTest` and `MockMvc` to verify invalid input is blocked before invoking the service. For Spring Framework 6.2+ / Spring Boot 3.4+, you can use `@MockitoBean` to replace the controller's dependency with a mock; on older versions, use the mocking annotation supported by your project.

The example below is **an excerpt inside a test method that already has `MockMvc mockMvc` and a mocked `orderService` configured**; it is not a standalone runnable Java program:

```java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"sku\":\"SKU-01\",\"quantity\":0}"))
    .andExpect(status().isBadRequest());

verifyNoInteractions(orderService);
```

This assumes the controller has `@Valid` and the DTO from section 2, so `quantity=0` is rejected before the controller calls the service. Static imports for `post`, `status`, `verifyNoInteractions`, and the import for `MediaType` are required. To test `quantity=11`, missing fields, `null`, whitespace-only `sku`, or malformed JSON, change the input payload and assert the corresponding status and side effects.

The happy path also needs a representative HTTP test, with the stubbed service returning a fixed ID for deterministic assertions:

```java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"sku\":\"SKU-01\",\"quantity\":5}"))
    .andExpect(status().isCreated())
    .andExpect(jsonPath("$.orderId").isNotEmpty());
```

This snippet assumes the controller returns a body with a JSON property `orderId`. Before running, configure the mock service to return a successful result; otherwise, the mock might return `null` or fail the test for the wrong reason. For M14–M18, stub the service/adapter to throw the **mapped exception** and verify `409` or `503` at the HTTP boundary. To verify real HTTP dependency errors, use an HTTP stub server capable of returning `500`, closing connections, or inducing timeouts; mocking the service alone does not prove HTTP client timeout configuration works.

Required exception handlers per the sample contract:

- `OutOfStockException` → `409 Conflict`.
- `DependencyUnavailableException` (thrown by the adapter on timeouts, connection drops, upstream 5xx, or policy-defined malformed responses) → `503 Service Unavailable`.
- Unknown errors → safe server error response per global policy; never catch all `RuntimeException`s and turn them into `201` or `400`.

## 7. Designing Test Data So Nothing Slips Through

Start from each field in the contract, listing equivalence classes and boundary points. For example:

| Field / Condition | Valid Class | Invalid Class | Points to Test |
| --- | --- | --- | --- |
| `sku` | String with at least one non-whitespace character | Missing, `null`, empty, whitespace-only | `"SKU-01"`, `""`, `"   "` |
| `quantity` | Integer in `[1, 10]` | Missing, `null`, out of range, unparseable | `0, 1, 5, 10, 11`, `"abc"` |
| `reserve` | `true` | Business `false`; technical exceptions | success, out-of-stock, timeout, connection error, upstream 5xx |
| Error mechanism | Contract-compliant response | Wrong mapping or internal leak | `400`, `409`, `503` and body checks |

Steps to follow:

1. **Extract measurable rules:** required fields, types, value domains, responses, dependency interactions, side effects, retry and timeout policies.
2. **Pick representatives from each class:** a normal value, two valid boundaries, and two invalid boundaries; at least one case for each dependency error type handled differently.
3. **Attach a clear oracle:** status, JSON, exception, mock calls, saved data, emitted events, transaction state.
4. **Assign test layers:** controller for parsing/validation and HTTP contract; service for business branches; adapter for HTTP client and mapping; integration for database/transactions/serialization/bean wiring.
5. **Run and reconcile with the matrix:** keep IDs stable, record test names, priority, outcomes, and actual defects. When requirements change, revisit affected rows and expected outcomes.

Do not multiply every combination (every `sku` × every `quantity` × every inventory error); that creates redundant tests without meaningfully increasing bug detection. Use one valid baseline case (M01), vary **one factor at a time**, then add a few high-risk combinations like M19 to check validation-before-dependency precedence. For fields with strong interactions, pairwise testing can help, though critical business rules still warrant explicit tests.

## 8. Prioritizing and Organizing the Test Suite in Spring Boot

You can assign priorities as follows (adjusting for system risk):

- **P0 – run on every pull request:** M01, M02, M03, M04, M06, M08, M10, M14, M15, M19. These cover the baseline flow, primary boundaries, validation precedence, and critical dependency failure paths.
- **P1 – run regularly in CI:** M05, M07, M09, M11, M12, M13, M16, M17, M18 and contract-variant scenarios.
- **Add as required:** duplicate requests, idempotency keys, retry/backoff, circuit breakers, concurrency, race conditions, DB failures after stock reservation, rollback/compensation. Only assert expected behavior after locking down rules for those capabilities.

Suggested layering:

| Layer | Appropriate Tooling | Purpose |
| --- | --- | --- |
| Service unit | JUnit Jupiter + Mockito | Success/out-of-stock branches, call counts, and arguments |
| MVC slice | `@WebMvcTest` + `MockMvc` | HTTP status, JSON, validation, exception handlers |
| Adapter / HTTP client | MockWebServer or WireMock | Upstream 5xx, timeouts, connection errors, response parsing |
| Integration | `@SpringBootTest`; Testcontainers when real DB needed | Wiring, transactions, persistence, rollback conditions |
| Smoke / end-to-end | Application running in controlled environment | Critical cross-layer contracts and real configuration |

Mocks or fakes should be strict enough to fail when called with wrong arguments; avoid letting default mock return values (`false`/`null`) accidentally mask a branch. For timeouts, use a stub and a short, bounded client timeout; avoid long `Thread.sleep` calls that make tests slow and flaky. Shared data must be isolated across tests so execution order does not affect results.

## 9. Common Pitfalls and How to Catch Them

**Happy path only:** testing `quantity=5` passes, while `>=` vs `>` boundary bugs go uncaught. Fix with the `0, 1, 10, 11` quartet.

**Calling dependencies on bad input:** controller misses `@Valid` or lets the service call inventory before validating. A `400` test paired with `verifyNoInteractions` catches this.

**Collapsing all errors into 500:** out-of-stock (`false`) is a business rejection, whereas timeout is a technical error. Test M14 alongside M15 to ensure `409` and `503` are not mixed up.

**Mocking at too high a layer:** stubbing `OrderService` and seeing `503` does not prove the client has timeouts configured or the adapter maps upstream 5xx correctly. Write dedicated adapter tests with a mock server plus a wiring integration test if critical.

**Assertions too weak or too brittle:** asserting only `201` without checking body, call count, or saved data; or asserting randomly generated UUIDs/timestamps and unstable framework error messages. Assert the exact contract guarantees.

**Unsafe retries:** reserving stock has side effects. If a timeout occurs after inventory already processed the request, retrying may double-reserve. Only expect retries when idempotency keys, retry policies, and consistency guarantees are specified and tested separately; never assume “timeout means retry.”

**Confusing layer responsibilities:** Bean Validation does not replace business checks like stock availability or resource ownership; conversely, service unit tests alone cannot prove HTTP status codes. The matrix should state clearly which layer owns each assertion.

## 10. Minimal Template to Apply to Another Endpoint

Copy the row structure below and fill it with the endpoint's **real contract**:

| Test ID | Rule / Risk | Given: Data + Dependency State | When | Then: Response + System State | Layer | Priority |
| --- | --- | --- | --- | --- | --- | --- |
| TC-001 | Normal valid value | Valid input; dependency succeeds | Call API | Correct status/body; side effect exactly once | MVC + service | P0 |
| TC-002 | Below / at / above boundary | `min-1`, `min`, `max`, `max+1` | Call API | Boundaries accepted/rejected accurately | MVC | P0 |
| TC-003 | Missing / invalid field | Invalid field | Call API | Validation error; dependency not called | MVC | P0 |
| TC-004 | Business rejection | Dependency returns negative business outcome | Call API | Business error; no success outcome created | Service + MVC | P0 |
| TC-005 | Technical failure | Timeout / connection / 5xx | Call API | Technical error per contract; consistent state | Adapter + integration | P0/P1 |

Matrix acceptance checklist: **(1)** every key requirement has at least one case; **(2)** `min-1, min, max, max+1` points are right; **(3)** bad input blocks side effects; **(4)** business failures differ from technical failures; **(5)** timeouts/5xx are checked at the right layer; **(6)** status, body, invocations, and post-operation state are all asserted; **(7)** tests are independent, deterministic, and repeatable. When all seven criteria hold, the matrix serves both as a test design document and a map for maintaining your regression suite as APIs evolve.
