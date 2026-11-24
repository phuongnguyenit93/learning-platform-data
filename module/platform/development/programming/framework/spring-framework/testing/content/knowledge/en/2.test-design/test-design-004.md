# Equivalence Partitioning, Boundary Values, and Invalid Data

When testing a feature that accepts input data, the number of possible cases is often huge. An API accepting quantities from 1 to 100 already has at least one hundred valid values—not counting missing values, `null`, negative numbers, oversized numbers, strings, decimals, and malformed JSON. Testing only a few arbitrary values can miss bugs. Testing every possibility quickly costs more than it returns.

Equivalence Partitioning, Boundary Value Analysis, and invalid-data test design help select a small yet well-justified set of cases. The three techniques are usually combined: equivalence partitioning splits the input domain into groups expected to behave alike; boundary value analysis targets transition points between groups; invalid-data testing confirms the system rejects bad input per contract without unintended side effects.

In a Spring application, these techniques apply across layers: unit tests for business rules, controller tests with `MockMvc`, integration tests for flows through Spring, and persistence tests for data constraints. Choosing the right layer keeps each test focused on the behavior it needs to protect.

## 1. Start from the Input Contract

Before grouping data, state clearly what the feature accepts and how it must respond. The contract may come from business requirements, API specifications, validation annotations, domain rules, or database constraints.

Suppose an order-creation API accepts a `quantity` field with these rules:

- The field is required.
- The value must be an integer.
- The minimum value is 1 and the maximum is 100.
- Both 1 and 100 are accepted.
- If input is invalid, the API returns an input error per application convention and does not invoke order-creation business logic.

This contract defines the valid domain as integers from 1 to 100, inclusive. It also points out the input categories to examine: out-of-range values, missing values, `null`, and wrong-type representations.

Do not infer the contract solely from Java types. For instance, declaring a field as `Integer` does not automatically restrict values to 1 through 100; declaring `int` cannot clearly distinguish a missing field from a default 0 after certain binding steps. Rules must come from requirements and be explicitly enforced in the application.

## 2. Equivalence Partitioning

### 2.1. Concept

Equivalence partitioning divides the input domain into classes (partitions) such that values within the same partition are expected to be processed similarly. Instead of testing every value, we pick one or a few representatives from each partition.

A good equivalence partition is based on system behavior, not merely on values looking alike. If two groups of values lead to different outcomes under the contract, split them into two partitions even when both are valid.

For example, with `quantity` from 1 to 100, the input domain can be partitioned as follows:

| Partition | Representative data | Expected behavior |
|---|---|---|
| Valid | `25` | Accept and proceed |
| Below lower bound | `0` or `-3` | Reject because less than 1 |
| Above upper bound | `101` or `500` | Reject because greater than 100 |
| Missing field | `{}` | Reject because `quantity` is missing |
| `null` value | `{"quantity": null}` | Reject because field is required |
| Wrong data type | `{"quantity": "abc"}` | Reject because it cannot convert to integer |

These partitions ensure coverage of both the valid region and the ways input can be invalid. A representative such as `25` verifies normal processing; `0` represents below-limit; `101` represents above-limit.

### 2.2. When Should One Partition Be Split into Multiple?

Being equally valid or equally invalid does not always put values in the same partition. Split partitions whenever rules or expected outcomes differ.

For example, if orders receive tiered discounts:

- `quantity` from 1 to 10: no discount.
- `quantity` from 11 to 50: 5% discount.
- `quantity` from 51 to 100: 10% discount.
- Outside 1 to 100: reject.

Here, the valid domain must be split into three separate partitions because the same request produces different business outcomes. Testing only `quantity = 25` will not verify the rules for the other two tiers.

Factors that commonly split equivalence partitions:

- Different business rules or processing tiers by value range.
- Different user roles or access permissions.
- Different current resource states, such as active, locked, or deleted.
- Different formats, lengths, character sets, or data structures.
- Rules depending on time, time zone, currency, or configuration.

For example, a customer code allowing only uppercase letters and digits may need separate partitions for well-formed codes, lowercase letters, missing characters, special characters, and overly long codes. If malformed variants produce the exact same validation error, one representative per rule group may suffice; if the API returns distinct errors per condition, split groups accordingly.

### 2.3. Choosing Representative Values

Representative values should be simple, readable, and clearly depict the partition they represent. For the valid partition 1 to 100, choose 25. For below 1, choose 0. For above 100, choose 101.

Avoid picking only adjacent values or familiar numbers without consulting the rules. A midpoint value represents the typical valid partition, but it cannot replace boundary tests. That is why equivalence partitioning is commonly paired with boundary value analysis.

For multi-field inputs, consider relationships between fields. For instance, `startDate` and `endDate` can each be individually valid dates yet form an invalid combination when `endDate` precedes `startDate`. Partitions must account for cross-field conditions, not only isolated fields.

## 3. Boundary Value Analysis

### 3.1. Why Test Boundaries?

Bugs frequently occur at transitions between processing regions: confusing `>` with `>=`, miscalculating max length, missing the final day of a period, or off-by-one index errors. Boundary value analysis focuses on these transition points.

For a valid interval with lower bound `min` and upper bound `max`, a standard value set is:

- `min - 1`: just below lower bound.
- `min`: exact lower bound.
- `min + 1`: just above lower bound.
- `max - 1`: just below upper bound.
- `max`: exact upper bound.
- `max + 1`: just above upper bound.

For `quantity` from 1 to 100, the values to watch are:

| Position | Value | Expected outcome |
|---|---:|---|
| Just below min | 0 | Reject |
| Min | 1 | Accept |
| Just above min | 2 | Accept |
| Just below max | 99 | Accept |
| Max | 100 | Accept |
| Just above max | 101 | Reject |

This six-value set catches far more common defects than testing one mid-range valid value and one far-out invalid value.

### 3.2. Inclusive vs. Exclusive Boundaries

Limit conditions may include or exclude the boundary value itself. These two rules are not equivalent:

```java
quantity >= 1 && quantity <= 100
```

```java
quantity > 1 && quantity < 100
```

The first accepts both 1 and 100; the second rejects both. Tests must reflect the exact contract rather than testing only interior values.

For strings of length 3 to 20 characters, check lengths 2, 3, 4, 19, 20, and 21. For 0-indexed result pages, check page 0, page 1, the last page, and an out-of-range page per API policy. For effective dates, test right before, right at, and right after the transition instant, while specifying time zone and precision clearly.

### 3.3. Discrete vs. Continuous Boundaries

For discrete domains like integers, use adjacent values `min - 1`, `min`, `min + 1`. For continuous domains like decimal monetary amounts or timestamps, determine the precision supported by the system before choosing near-boundary values.

For instance, if monetary amounts are stored to two decimal places with a minimum of 0.01, test cases can include 0.00, 0.01, and 0.02. If the API accepts only whole minor currency units, decimal inputs must be tested against formatting rules.

Do not pick an arbitrary tiny epsilon for every continuous domain. Near-boundary values should reflect data-type precision, business units, and system rounding rules.

### 3.4. Boundaries Across Multiple Conditions

When a feature has many fields, each field can have its own boundaries. Testing every combination of all boundary values scales rapidly. Prioritize instead:

1. Test each field at its boundaries while holding the other fields at stable valid values.
2. Test combinations with business significance, such as interdependent fields.
3. Add high-risk combinations where an error in one field might alter how another is processed.

For example, a registration form has `age` from 18 to 65 and `startDate` not in the past. First test age boundaries with a valid start date; then test date boundaries with a valid age. Finally, test combinations relevant to business rules. This makes root causes clear when a test fails.

## 4. Designing Invalid-Data Tests

### 4.1. Invalid Data Takes Many Forms

An input can fail at different layers. Classifying failures identifies which component is responsible for detection and what outcome to verify.

| Data category | Example | Issue to detect |
|---|---|---|
| Missing data | Omitting `quantity` | Required field not supplied |
| Empty value | `null`, `""`, or whitespace-only string | Distinguish empty from missing and valid |
| Wrong type | String instead of number, object instead of string | Binding or data conversion failure |
| Invalid format | Email missing domain part, code with forbidden characters | Violates defined format |
| Out of range | Negative number, number exceeding limit | Violates bounds or valid domain |
| Relationship violation | End date before start date | Fields individually valid but combination invalid |
| Business violation | Ordering a discontinued product | Structurally valid data invalid in current state |
| Duplicate or conflict | Creating an account with an existing email | Uniqueness or resource state conflict |

Do not lump all these cases into a single test. They may be handled by different layers and produce different responses.

### 4.2. Distinguish Syntax/Binding, Validation, and Business Errors

**Syntax or binding errors** occur when a request cannot be parsed according to the structure expected by the API. For instance, the API expects an integer and the client sends an object. The error may happen before the controller is invoked.

**Validation errors** occur when data is parsed successfully yet violates constraints. For example, `quantity = 0` is syntactically a valid integer but falls outside the allowed range.

**Business errors** occur when data is well-typed and may pass basic validation yet conflicts with domain rules or current state. For example, quantity is within range, but the product is discontinued.

All three categories may result in 4xx responses, yet they need not share the same status code or error structure. Specific HTTP codes must follow the application's API contract. What matters is that tests verify detection at the right place, the right public response, and that processing stops when input is rejected.

### 4.3. Verify Side Effects

With invalid input, checking only the HTTP status is insufficient. A validation error could return 400 yet still call the service or write data if flow control is broken.

Depending on the feature, verify conditions such as:

- Business services are not invoked when a request fails web-layer validation.
- No record is created or state updated when an operation is rejected.
- No notification, email, or external event is dispatched for an invalid transaction.
- Existing data remains unaltered.
- Returned errors carry enough detail for clients to fix input without leaking stack traces, secrets, or internal details.

In integration tests with a database, read back state after the request to confirm data was untouched. In controller tests using mocks, verify the service had no interactions. Match side-effect checks to what the layer under test is responsible for controlling.

### 4.4. Distinguish Missing, Null, Empty, and Whitespace

The following states can carry different meanings:

```json
{}
```

```json
{"name": null}
```

```json
{"name": ""}
```

```json
{"name": "   "}
```

`@NotNull` checks only that a value is not `null`; it does not reject empty or whitespace-only strings. For required non-empty strings, `@NotBlank` may be needed. For strings allowed to be empty yet bounded in length, `@Size` carries a different meaning. Tests should mirror the exact annotations and contract in use.

## 5. Applying in Spring with Jakarta Bean Validation

Spring MVC can trigger Bean Validation on request bodies using `@Valid`. Constraints such as `@NotNull`, `@Min`, `@Max`, `@Size`, `@NotBlank`, and `@Pattern` declare input rules directly on DTOs.

Example DTO accepting quantity:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

public record CreateOrderRequest(
        @NotNull
        @Min(1)
        @Max(100)
        Integer quantity
) {
}
```

Here `Integer` is paired with `@NotNull` to represent a missing value clearly. `@Min(1)` and `@Max(100)` define lower and upper bounds. For constraints to activate in a Spring Boot application, the project needs the validation dependency, typically `spring-boot-starter-validation`.

Controller triggering validation:

```java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    ResponseEntity<Void> create(@Valid @RequestBody CreateOrderRequest request) {
        orderService.create(request.quantity());
        return ResponseEntity.accepted().build();
    }
}
```

`@Valid` instructs Spring to validate constraints on the request object before executing the controller method body. If validation fails, Spring routes the error through the application's exception handling mechanism. If JSON cannot be deserialized into the DTO, binding/deserialization failure may occur before Bean Validation runs.

## 6. Testing Equivalence Partitions and Boundary Values with MockMvc

`@WebMvcTest` is well suited to verifying the controller's web contract: requests bind, validation fires, and HTTP responses match expectations. The service can be mocked to confirm the controller does not pass invalid data down to business logic.

The following example uses JUnit 5 and Mockito. `OrderService` is a controller dependency:

```java
interface OrderService {
    void create(Integer quantity);
}
```

Testing valid values, including both endpoints:

```java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @ParameterizedTest
    @ValueSource(ints = {1, 2, 25, 99, 100})
    void acceptsQuantityInsideAllowedRange(int quantity) throws Exception {
        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"quantity": %d}
                                """.formatted(quantity)))
                .andExpect(status().isAccepted());

        verify(orderService).create(quantity);
    }
}
```

Values 1 and 100 confirm both inclusive endpoints are accepted; 2 and 99 lie just inside each endpoint; 25 represents the normal valid region. If additional business tiers exist within the range, add representatives for each tier.

Testing out-of-range values:

```java
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ParameterizedTest
@ValueSource(ints = {0, 101})
void rejectsQuantityOutsideAllowedRange(int quantity) throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"quantity": %d}
                            """.formatted(quantity)))
            .andExpect(status().isBadRequest());

    verifyNoInteractions(orderService);
}
```

Values 0 and 101 lie just outside the valid interval. Verifying no interaction with the service proves the request was blocked before entering business logic. If the application uses another status code for validation errors, replace the assertion with the code defined in the API contract.

Missing and `null` cases can be tested separately because they represent different input partitions:

```java
import org.junit.jupiter.api.Test;

import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void rejectsMissingQuantity() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{}"))
            .andExpect(status().isBadRequest());

    verifyNoInteractions(orderService);
}

@Test
void rejectsNullQuantity() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""{"quantity": null}"""))
            .andExpect(status().isBadRequest());

    verifyNoInteractions(orderService);
}
```

Wrong-type input should also be tested at the web layer:

```java
@Test
void rejectsNonNumericQuantity() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""{"quantity": "many"}"""))
            .andExpect(status().isBadRequest());

    verifyNoInteractions(orderService);
}
```

In this example, the string `"many"` cannot be converted into an `Integer` under standard binding settings. For inputs such as decimals, oversized numbers, or numeric strings, behavior can depend on Jackson configuration and application coercion policies. Clarify whether the API allows conversion and assert according to actual configuration; do not assume all setups treat those inputs identically.

The code snippets illustrate how to structure tests. In an actual project, supply imports, test slice configuration, and matching dependencies, and assert the exact HTTP codes and response contracts published by the application.

## 7. Testing at the Right Layer in a Spring Application

A rule can be tested at multiple layers, yet each layer should stay focused on its own responsibility.

| Test layer | What to test | Suitable examples |
|---|---|---|
| Domain/service unit test | Pure Java business rules and domain partitions | Valid quantity, discount tier, start/end date relation |
| Validation test | Constraints on DTOs or input objects | `@NotNull`, `@Min`, `@Max`, `@Pattern` |
| `@WebMvcTest` with `MockMvc` | JSON binding, validation activation, HTTP codes, and response structure | Missing field, wrong type, out-of-range value |
| `@SpringBootTest` | Integration flow through Spring configuration and involved beans | Request flowing through controller, service, and integration components |
| Persistence test | Data constraints and storage behavior | Unique constraints, foreign keys, check constraints, rollback |

You do not need to put every data combination into `@SpringBootTest`. Testing each rule at the smallest viable layer keeps tests fast and root causes obvious. Use integration tests only when verifying collaboration across components such as validation, transactions, and the database.

Database constraints still serve a distinct role. API validation returns early, friendly errors; database constraints protect integrity when writes enter through multiple paths or under concurrency. A service test may miss a unique-constraint violation triggered by two concurrent requests, so such cases require persistence or integration testing.

## 8. Process for Designing a Test Suite

For a feature accepting input, proceed in this order:

1. **Rewrite rules as explicit conditions.** Identify required fields, data types, valid ranges, formats, cross-field relationships, and state-dependent rules.
2. **Partition equivalence classes.** List input groups with identical expected behavior. Split partitions whenever business outcomes or responses differ.
3. **Pick representatives per partition.** Favor simple, clear values that demonstrate the rule accurately.
4. **Add boundary values.** For every bound, test just below, right at, and just above the bound where the domain permits.
5. **Add invalid data per root cause.** Cover missing, `null`, empty, wrong type, wrong format, out of range, relationship violation, and business violation.
6. **Choose the test layer.** Verify pure rules in unit tests, HTTP contracts in `MockMvc`, and bean or database integration at the corresponding layer.
7. **Verify both outcomes and side effects.** Beyond status or return value, confirm whether services, databases, events, or external actions are invoked appropriately.

As field count grows, do not mechanically multiply all value sets together. Test each condition independently first, then add combinations that business rules truly depend on or that carry high risk. When two fields are related—such as `startDate <= endDate`—design valid and invalid cases specifically for that relationship.

## 9. Common Mistakes

**Testing only one valid and one invalid value.** Two cases often miss inclusive/exclusive bounds, intermediate business partitions, and distinct invalid-input types. Use partitioning to ensure every group has a representative, then add boundaries.

**Testing boundaries without testing the interior.** Values 1, 2, 99, and 100 are valuable, yet they do not represent interior business tiers. If pricing or permissions change at an internal threshold, test around that threshold.

**Collapsing all invalid inputs into one partition.** Missing fields, `null`, wrong types, and business violations pass through different components. Separating them lets tests distinguish binding, validation, and business failures.

**Using primitive types and ignoring missing fields.** `int` cannot represent `null`; when a field is required and missing must be distinguished from a numeric value, wrapper types like `Integer` with appropriate constraints are clearer.

**Assuming `@NotNull` forbids empty strings.** That constraint forbids only `null`. For strings that must not be empty or whitespace-only, choose `@NotBlank` or a matching rule.

**Asserting only the error status.** A request might return an error status while still invoking a service or causing side effects. Check interactions or persisted state according to the tested layer's responsibility.

**Over-specifying exact error message text in every test.** If message text is not a stable contract, locking onto exact phrasing makes tests brittle to copy edits or localization. Usually prefer status, stable error codes, field names, and required public fields. Assert verbatim messages only when required by product specs.

**Relying solely on controller validation.** Data can reach services via message consumers, scheduled jobs, batch processes, or internal calls. Critical business rules should be enforced at a layer protecting all entry points; web validation only guards the HTTP contract.

## 10. Combining All Three Techniques in One Example

For the contract where `quantity` is a required integer from 1 to 100, a concise test suite can be organized as:

| Target | Input | Technique | Verification |
|---|---|---|---|
| Normal valid path | `25` | Equivalence partitioning | Request accepted |
| Lower boundary | `0`, `1`, `2` | Boundary value | 0 rejected; 1 and 2 accepted |
| Upper boundary | `99`, `100`, `101` | Boundary value | 99 and 100 accepted; 101 rejected |
| Missing field | `{}` | Invalid data | Validation fails, service not called |
| Null value | `{"quantity": null}` | Invalid data | Validation fails, service not called |
| Wrong type | `{"quantity": "many"}` | Invalid data | Binding fails, service not called |

If discount rules are later added at thresholds 10 and 50, add business partitions and boundary checks around those thresholds: 9, 10, 11 and 49, 50, 51. If the API adds a product-status condition, add partitions for active and discontinued products and verify corresponding business responses.

Equivalence partitioning enables systematic representative selection; boundary value analysis targets comparison-prone edges; invalid-data testing ensures the system rejects contract violations while preserving protected state. Combining them at the appropriate Spring testing layer yields a suite that covers key rules while keeping every case's purpose clear.
