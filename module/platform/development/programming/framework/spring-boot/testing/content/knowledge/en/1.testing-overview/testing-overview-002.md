# A Test Case Consists of Preconditions, an Action, and an Expected Result

## 1. Why Does a Test Case Need All Three Parts?

A **test case** describes a specific scenario to verify whether the system behaves according to requirements. For someone else to re-run it and reach the same conclusion, a test case must answer three questions:

1. **Preconditions (Given / Arrange):** Before testing, what must the data, state, environment, and relevant permissions look like?
2. **Action (When / Act):** Which operation does the user, program, or test perform on the system?
3. **Expected result (Then / Assert):** What can be observed and verified after the action to conclude pass or fail?

An easy formula to remember: **Given a state → perform an action → verify a specific result**. Missing any part makes a test ambiguous: data cannot be reproduced, the operation to test is unclear, or the run finishes with no PASS/FAIL criteria.

In Spring Boot, a test case can target a Java method, a service, an HTTP controller, a repository, or an integration flow. The three-part structure stays the same; only the way state is set up, the action is executed, and the result is observed changes.

## 2. The Three Components of a Test Case

| Component | What to Describe | Example: Reserving Stock in Inventory |
| --- | --- | --- |
| **Preconditions** | System state, sample data, dependencies, required configuration; what must be true *before* invoking the feature. | Item has 3 units in stock, request reserves 2 units; test inventory is isolated from other cases. |
| **Action** | A business-meaningful operation with concrete input data. | Call `reserve(2)`. |
| **Expected result** | Return value, post-action state, side effects, or error that must occur; verifiable via assertions. | Reservation accepted, stock has exactly 1 unit remaining. |

**Preconditions are not the expected result.** For example, “inventory has 3 items” is the data before testing; “inventory has 1 item remaining” is the state to verify after the action. **The action is also not an assertion:** calling an API only triggers the feature, while checking the HTTP status code, body, or data state determines PASS/FAIL.

A case can have multiple assertions if they together prove **one behavior**. For instance, a successful reservation must confirm both the accepted result and the remaining stock after deduction. Do not mix multiple independent business flows into a single case, because when it fails, pinpointing the cause becomes difficult.

## 3. Designing Test Scenarios Before Writing Code

Example business requirement: “Only allow reserving a positive quantity that does not exceed available stock; if rejected, do not change stock.”

| Case ID | Preconditions | Action | Expected Result |
| --- | --- | --- | --- |
| TC-01 — sufficient stock | Stock = 3 | Reserve 2 | Returns success; stock = 1 |
| TC-02 — insufficient stock | Stock = 1 | Reserve 2 | Returns failure; stock remains = 1 |
| TC-03 — invalid quantity | Stock = 3 | Reserve 0 | Returns failure; stock remains = 3 |
| TC-04 — exact stock | Stock = 2 | Reserve 2 | Returns success; stock = 0 |

The cases above cover the normal path, rejection scenarios, and boundaries. The “stock remains unchanged” condition in failure cases is crucial: checking only the return value can miss a bug where the system deducts stock before rejecting.

When documenting a test case in docs or a test management tool, you can add **ID, scenario name, related requirement, input data, execution steps, and actual result**. Those fields support management, but do not replace the three core components.

## 4. Java 17 Example: Arrange – Act – Assert

The following example is a standalone Java program requiring neither Spring Boot nor a testing library. Each case creates its own inventory to avoid affecting the others.

**File: `TestCaseDemo.java`**

~~~java
public class TestCaseDemo {
    static final class Inventory {
        private int stock;

        Inventory(int stock) {
            this.stock = stock;
        }

        boolean reserve(int quantity) {
            if (quantity <= 0 || quantity > stock) {
                return false;
            }
            stock -= quantity;
            return true;
        }

        int remaining() {
            return stock;
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        // TC-01 — Arrange: stock has 3, need to reserve 2
        Inventory available = new Inventory(3);

        // Act: invoke the feature under test
        boolean accepted = available.reserve(2);

        // Assert: both return value and subsequent state
        check(accepted, "TC-01: must accept order");
        check(available.remaining() == 1, "TC-01: remaining stock must be 1");
        System.out.println("TC-01: PASS");

        // TC-02 — Arrange: stock only has 1, need to reserve 2
        Inventory insufficient = new Inventory(1);

        // Act
        boolean rejected = insufficient.reserve(2);

        // Assert: reject and do not deduct stock
        check(!rejected, "TC-02: must reject order");
        check(insufficient.remaining() == 1, "TC-02: stock must not change");
        System.out.println("TC-02: PASS");
    }
}
~~~

Run in the directory containing the file with JDK 17 or higher:

~~~bash
javac TestCaseDemo.java
java TestCaseDemo
~~~

Exact output when both cases pass:

~~~text
TC-01: PASS
TC-02: PASS
~~~

The `check` method throws an `AssertionError` if the condition is false, so it will **not** print the PASS line for a failing case. In real projects, JUnit 5 provides assertions such as `assertTrue`, `assertFalse`, `assertEquals`, and a test runner to manage many cases; the plain Java example here simply clarifies the test case structure.

## 5. Applying This to Spring Boot Testing

For a controller, the three parts correspond to:

- **Arrange:** initialize the application or MVC slice under test, prepare requests and mock data, and set the authenticated user if the endpoint requires authentication.
- **Act:** send the request using `MockMvc`, `WebTestClient`, or an appropriate HTTP client.
- **Assert:** verify HTTP status, JSON/body, headers, and, if the business contract requires it, data state after the request.

The Spring Boot 3.x example below tests an HTTP endpoint returning simulated stock. The Spring Boot project needs `spring-boot-starter-web` and `spring-boot-starter-test` dependencies; both files belong under the same package.

**File `src/main/java/com/example/testing/StockController.java`:**

~~~java
package com.example.testing;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StockController {
    @GetMapping("/api/stock")
    public Map<String, Object> stock() {
        return Map.of("sku", "SKU-1", "available", 3);
    }
}
~~~

**File `src/test/java/com/example/testing/StockControllerTest.java`:**

~~~java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(StockController.class)
class StockControllerTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void stockEndpointReturnsExpectedResponse() throws Exception {
        // Arrange: MVC test context is initialized;
        // GET /api/stock request needs no body.

        // Act + Assert: send request and verify contract.
        mockMvc.perform(get("/api/stock"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku").value("SKU-1"))
                .andExpect(jsonPath("$.available").value(3));
    }
}
~~~

In this example:

1. **Preconditions:** `@WebMvcTest(StockController.class)` builds the required MVC layer test context; the controller is provided and has no database dependency.
2. **Action:** `mockMvc.perform(get("/api/stock"))` dispatches a simulated request into the MVC layer.
3. **Expected result:** HTTP 200, field `sku` equals `SKU-1`, field `available` equals the number 3. Any wrong assertion causes the test to fail.

In a Gradle Spring Boot project configured with test dependencies and the `test` task, run `./gradlew test` on macOS/Linux or `gradlew.bat test` on Windows. The test runner reports PASS/FAIL; this test snippet does not print PASS lines itself like the plain Java example.

**Example limitation:** the controller intentionally returns fixed data to illustrate the HTTP contract. `@WebMvcTest` tests an MVC slice and does not by itself prove database writes or full application integration. For real features with persistence, prepare test records, perform the request, and verify data after the request in a test type with an appropriate repository/database. If the project enables Spring Security, configure the corresponding authentication/authorization context; otherwise, requests may be rejected before reaching the controller.

## 6. Expected Results Must Be Clear Enough to Decide PASS/FAIL

A phrase like “API works properly” is not measurable. Convert it into observable verifications:

| Vague | Concrete, Verifiable |
| --- | --- |
| “Order placed successfully” | `reserve(2)` returns `true` and stock drops from 3 to 1 |
| “API returns correctly” | HTTP 200; JSON has `sku = "SKU-1"` and `available = 3` |
| “Error handled reasonably” | Request exceeding stock returns rejection; stock does not change |
| “Data saved properly” | After the operation completes, querying the record by ID yields the specified fields |

The expected result can be a **return value**, **exception/error code**, **persisted state**, **emitted event**, or **absence of side effects**. Choose observation points based on the business contract, avoiding coupling tests to unnecessary internal implementation details.

The *actual* result is the value obtained at runtime; it is compared against the *expected* result. If it matches across all required assertions, the case PASSES; if it differs, the case FAILS and reports where it failed. Never write assertions based on the actual result you just observed merely to “make the test green”.

## 7. How Do You Make a Test Case Reliable?

**Preconditions must be reproducible.** Create fresh data, reset fixtures, or roll back transactions when appropriate. Avoid assuming the database already has a record created by someone else. Stub/mock only dependencies outside the target under test; if you mock the very logic you need to prove, the test loses its value.

**Actions must have deterministic inputs.** Clearly specify parameters, URL, method, body, headers, identity, and required step order. One case should focus on one scenario; preparation steps belong in Arrange, not mixed with the business action being measured.

**Assertions must verify all important consequences.** For update operations, check both the response and subsequent state if within the test's scope. For error cases, check whether the system preserves existing data unchanged. For APIs, HTTP 200 alone is usually insufficient to confirm the payload is correct.

**Independence and stability are essential.** Avoid shared data that other tests might modify, real wall-clock time, execution order, external networks, or `Thread.sleep` as a success condition. For asynchronous behavior, wait on an observable condition with a defined timeout instead of guessing durations.

## 8. Common Mistakes and How to Fix Them

1. **Missing Arrange:** the test relies on data left over from a previous run. **Fix:** create fixtures directly in the test/test setup, or isolate the environment.
2. **Act without Assert:** merely calling a method or endpoint lets logic bugs keep the test “green”. **Fix:** verify at least one concrete outcome tied to a requirement.
3. **Incomplete Assert:** checking only `accepted == true` without checking stock. **Fix:** verify post-condition state as well when it is part of the contract.
4. **Lumping unrelated scenarios together:** long cases make it hard to tell where a failure occurred. **Fix:** split into test cases named for their behaviors, each with its own Arrange/Act/Assert.
5. **Undefined expectations:** writing “fast response”, “success”, “reasonable” without criteria. **Fix:** define measurable statuses, data, time limits, or error types.
6. **Wrong test level:** using `@WebMvcTest` and concluding that business data was written to the database. **Fix:** choose unit, web slice, or integration tests according to the type of outcome you need to prove.

## 9. Self-Check Checklist Before Finalizing a Test Case

- [ ] Name/ID clearly states the behavior or scenario.
- [ ] Preconditions specify required data, state, and dependencies.
- [ ] Action describes exactly one test operation with concrete inputs.
- [ ] Expected result is measurable by assertions, including important side effects.
- [ ] Valid, invalid, and boundary cases are included as appropriate for the business rules.
- [ ] Re-runs independently without relying on leftover state from other cases.
- [ ] On failure, assertion messages help distinguish actual from expected values.

**Takeaway:** a good test case does not just “run”. It sets up the scenario to test (**Arrange/Given**), performs the right operation (**Act/When**), and provides clear evidence for its conclusion (**Assert/Then**).