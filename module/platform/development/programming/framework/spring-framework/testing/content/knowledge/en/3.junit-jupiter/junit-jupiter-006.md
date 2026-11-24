# assertAll and Diagnostic Failure Messages

JUnit Jupiter provides `assertAll` to group multiple related assertions within a single test. When executing this group, JUnit continues running the remaining assertions even if one assertion fails, and then reports the collected failures together. This structure lets developers see multiple discrepancies in a single run instead of fixing one failure at a time across repeated runs.

Failure messages are also an essential part of a test. An assertion indicates which condition was not met; a good message helps readers understand which object, field, or business rule that result belongs to. Combining `assertAll` with meaningful messages makes test results easier to read and diagnose.

## 1. The Problem with Using Only Standard Assertions

JUnit Jupiter provides assertions such as `assertEquals`, `assertTrue`, `assertNotNull`, and `assertThrows`. Each assertion checks one condition. When an assertion fails, it throws an assertion error and the current test method stops at that point.

Example:

```java
@Test
void returnsOrderDetails() {
    OrderResponse response = orderService.getOrder("ORDER-42");

    assertEquals("ORDER-42", response.getId());
    assertEquals(OrderStatus.CONFIRMED, response.getStatus());
    assertEquals(new BigDecimal("120000"), response.getTotal());
    assertEquals(2, response.getItems().size());
}
```

If the first assertion fails, subsequent assertions are never executed. The developer only sees the first failure in that run. After fixing that bug and re-running, another failure may surface.

This behavior makes sense when verification steps depend on one another or when you want to fail fast if a foundational precondition is wrong. However, for multiple independent properties of the same result, stopping at the first assertion slows down diagnosis.

## 2. How Does assertAll Work?

`assertAll` accepts a group of `Executable` instances. Each executable is typically written as a lambda containing one or more assertions. JUnit executes each executable in the group in turn, collects any errors that occur, and then reports a composite failure if at least one error occurred.

Example:

```java
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;

@Test
void returnsOrderDetails() {
    OrderResponse response = orderService.getOrder("ORDER-42");

    assertAll("order response",
            () -> assertEquals("ORDER-42", response.getId()),
            () -> assertEquals(
                    OrderStatus.CONFIRMED,
                    response.getStatus()
            ),
            () -> assertEquals(
                    new BigDecimal("120000"),
                    response.getTotal()
            ),
            () -> assertEquals(2, response.getItems().size())
    );
}
```

If the status, total amount, and item count are all wrong, JUnit reports all three failures in the same run. One failing assertion does not prevent the remaining executables in the group from running.

The execution flow can be visualized as follows:

```text
Execute the action under test
              |
              v
       assertAll("...")
              |
       +------+------+
       |      |      |
       v      v      v
   Assertion A  B    C
       |      |      |
       +------+------+
              |
              v
      Collect failures
              |
       +------+------+
       |             |
  No failures   Has failures
       |             |
       v             v
      PASS     Report composite failure
```

If all assertions in the group pass, `assertAll` finishes normally and the test continues. If there are failures, JUnit throws `MultipleFailuresError` containing the collected errors. The test method is marked failed, and the report can display each individual failure.

`assertAll` does not turn multiple assertions into multiple test methods. They still belong to the same test case, sharing the test's fixture and state. Its purpose is to group related checks for more convenient diagnosis.

## 3. Adding a Heading to an Assertion Group

You can pass a heading string as the first argument:

```java
assertAll("order response",
        () -> assertEquals("ORDER-42", response.getId()),
        () -> assertEquals(OrderStatus.CONFIRMED, response.getStatus())
);
```

The heading helps readers recognize which part of the result the check group describes. Name it after the object or property group, such as:

- `order response`
- `customer profile`
- `payment result`
- `pagination metadata`

For tests verifying multiple groups of properties, you can nest `assertAll` groups to add structure:

```java
assertAll("order response",
        () -> assertAll("identity",
                () -> assertEquals("ORDER-42", response.getId()),
                () -> assertEquals(
                        OrderStatus.CONFIRMED,
                        response.getStatus()
                )
        ),
        () -> assertAll("amounts",
                () -> assertEquals(
                        new BigDecimal("120000"),
                        response.getTotal()
                ),
                () -> assertEquals(
                        new BigDecimal("10000"),
                        response.getShippingFee()
                )
        )
);
```

The outer group describes the response, while the inner groups categorize identity fields and monetary amounts. Nested structure is useful when a result has multiple independent sections. When there are only two or three simple assertions, a flat group is usually easier to read.

Avoid creating many nesting levels just to make code look structured. Headings should help locate failures faster; if a reader must expand multiple levels to understand what an assertion checks, the structure has become overly complex.

## 4. Adding Messages to Individual Assertions

JUnit Jupiter assertions generally have an overload taking a message. With `assertEquals`, the message can be passed after expected and actual:

```java
assertEquals(
        OrderStatus.CONFIRMED,
        response.getStatus(),
        "order status"
);
```

On failure, the report includes expected, actual, and the author-provided message. The message should answer the question: **What is this assertion checking?**

Example:

```java
assertAll("order response",
        () -> assertEquals(
                "ORDER-42",
                response.getId(),
                "order id"
        ),
        () -> assertEquals(
                OrderStatus.CONFIRMED,
                response.getStatus(),
                "order status"
        ),
        () -> assertEquals(
                new BigDecimal("120000"),
                response.getTotal(),
                "order total"
        )
);
```

When an error occurs, readers can immediately identify which field is wrong. While expected and actual values alone might let you deduce the condition from code, a business-meaningful message makes reports far easier to interpret, especially when multiple assertions compare the same data types.

### Messages Should Be Specific and Concise

Messages such as `"failed"`, `"wrong value"`, or `"assertion failed"` add no useful information. Describe the field or rule instead:

| Less Helpful Message | Clearer Message |
|---|---|
| `"wrong value"` | `"order total"` |
| `"status failed"` | `"new order should be PENDING"` |
| `"not equal"` | `"customer email"` |
| `"check result"` | `"page number should be zero-based"` |

A message does not need to repeat expected and actual in full if JUnit already displays them. Reserve the message for the context or meaning of the verified condition.

## 5. Using a Message Supplier for Dynamic Messages

JUnit Jupiter allows passing a `Supplier<String>` instead of a pre-constructed message string. The supplier is invoked only if the assertion fails, so you can use it to construct dynamic messages without building strings on every passing check.

```java
String orderId = "ORDER-42";

assertEquals(
        OrderStatus.CONFIRMED,
        response.getStatus(),
        () -> "unexpected status for order " + orderId
);
```

Another example with a boolean condition:

```java
assertTrue(
        response.getItems().size() > 0,
        () -> "order " + orderId + " should contain at least one item"
);
```

Suppliers are useful when the message needs to include identifiers or contextual data. For static messages, passing a string literal directly is usually simpler and easier to read.

Avoid dumping entire objects or sensitive data into failure messages. Include only the details necessary to identify the scenario. A long message filled with unrelated data can clutter reports and risk leaking information in CI logs.

## 6. Combining assertAll with Meaningful Messages

The following example combines a group heading, individual messages, and message suppliers:

```java
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Test
void returnsExpectedOrderResponse() {
    String orderId = "ORDER-42";
    OrderResponse response = orderService.getOrder(orderId);

    assertAll("order response: " + orderId,
            () -> assertEquals(
                    orderId,
                    response.getId(),
                    "response id"
            ),
            () -> assertEquals(
                    OrderStatus.CONFIRMED,
                    response.getStatus(),
                    () -> "unexpected status for " + orderId
            ),
            () -> assertEquals(
                    new BigDecimal("120000"),
                    response.getTotal(),
                    "total amount"
            ),
            () -> assertTrue(
                    response.getItems().size() > 0,
                    () -> "order " + orderId + " should contain items"
            )
    );
}
```

Here there are three layers of diagnostic information:

1. The heading `order response: ORDER-42` identifies which order the group belongs to.
2. Each assertion message identifies which property or rule failed.
3. The expected and actual values provided by the assertion show the exact discrepancy.

This structure is especially helpful when tests run in CI and the reader only has the failure report without running a debugger locally. They can identify the test, the subject, and the failing properties before opening the source code to investigate further.

## 7. Placing Preconditions Outside assertAll

Because `assertAll` continues executing the remaining executables, be careful with assertions that depend on a foundational precondition.

For example, if `response` might be `null`, the following snippet can produce confusing cascading errors:

```java
assertAll("response",
        () -> assertNotNull(response),
        () -> assertEquals("ORDER-42", response.getId()),
        () -> assertEquals(
                OrderStatus.CONFIRMED,
                response.getStatus()
        )
);
```

If response is `null`, `assertNotNull` fails, yet the subsequent lambdas still execute. They will proceed to throw `NullPointerException`. The report then contains both the initial null failure and secondary errors from dereferencing null.

If subsequent assertions require response to exist, verify the precondition beforehand:

```java
assertNotNull(response, "order response should be returned");

assertAll("order response",
        () -> assertEquals("ORDER-42", response.getId(), "response id"),
        () -> assertEquals(
                OrderStatus.CONFIRMED,
                response.getStatus(),
                "response status"
        )
);
```

When `response` is null, the test stops at the precondition assertion and the message focuses on the root cause. When response exists, the assertion group checks its independent properties.

You can apply the same principle to other conditions: before grouping assertions, determine whether they are genuinely independent or share a mandatory precondition state.

## 8. Do Not Repeat Actions Under Test Inside Each Lambda

`assertAll` is meant for grouping checks. The test's primary action should be executed once in the Act section, after which lambdas only observe and assert the outcomes.

Problematic style:

```java
assertAll("reservation",
        () -> assertTrue(inventoryService.reserve("BOOK-01", 2)),
        () -> assertEquals(3, inventoryService.getAvailableQuantity("BOOK-01"))
);
```

In this example, the `reserve` call sits in one lambda of the group while reading the quantity sits in another. If another assertion group also calls state-mutating actions, results may depend on execution count. The test becomes harder to reason about and risks executing business operations multiple times.

Clearer approach:

```java
boolean reserved = inventoryService.reserve("BOOK-01", 2);
int availableQuantity =
        inventoryService.getAvailableQuantity("BOOK-01");

assertAll("reservation result",
        () -> assertTrue(reserved, "reservation should succeed"),
        () -> assertEquals(
                3,
                availableQuantity,
                "remaining stock quantity"
        )
);
```

The action runs exactly once. Observed values are captured before assertions run, so each lambda verifies a single condition.

## 9. assertAll and Commonly Used Overloads

In JUnit Jupiter, `assertAll` can accept executables in several forms:

```java
assertAll(
        () -> assertEquals("Lan", customer.getName()),
        () -> assertTrue(customer.isActive())
);
```

Or with a heading:

```java
assertAll("customer",
        () -> assertEquals("Lan", customer.getName()),
        () -> assertTrue(customer.isActive())
);
```

You can also pass a collection or stream of `Executable` instances when the check list is built dynamically. For ordinary tests, inline lambdas are usually easier to read because conditions sit directly at the call site.

For example, verifying a list can use a stream to build executables:

```java
List<Executable> checks = IntStream.range(0, expectedNames.size())
        .mapToObj(index -> (Executable) () ->
                assertEquals(
                        expectedNames.get(index),
                        actualNames.get(index),
                        "name at index " + index
                )
        )
        .toList();

assertAll("customer names", checks);
```

This approach fits when the number of assertions depends on data. Ensure the actual list has the expected size before indexing into it; otherwise, out-of-bounds errors may appear instead of the value mismatch the test meant to diagnose. For small, fixed lists, explicit lambdas are usually clearer.

## 10. When Should You Use assertAll?

`assertAll` is helpful when conditions describe the same result and can be verified independently:

- Checking multiple fields of a DTO or response.
- Checking multiple properties of an entity after processing.
- Checking metadata fields of a paginated result.
- Checking multiple formatting rules on a value.
- Checking a group of HTTP response headers or properties.

You do not need to use `assertAll` for every test. A single assertion is usually the clearest choice when a test has only one condition. Sequential assertions also fit when a later condition depends on an earlier one or when failing fast avoids cascading errors.

Consider the following guide:

| Situation | Appropriate Style |
|---|---|
| Only a single condition | Direct assertion |
| Multiple independent properties of the same result | `assertAll` |
| Later condition requires earlier condition to hold | Precondition assertion first, then further checks |
| Operation mutates state | Execute once before the assertion group |
| Many repetitive data-driven checks | Collection/stream of executables if it improves clarity |

An assertion group should be semantically cohesive. Do not bundle unrelated checks simply because they reside in the same test method. A focused group keeps failure reports readable and helps developers identify the affected area.

## 11. Reading Failure Reports to Find Root Causes

When `assertAll` fails, start from the group heading and each component failure. Then cross-check expected, actual, and the message written in the test.

A systematic way to read reports:

1. **Identify the test method:** know which scenario ran.
2. **Read the group heading:** identify which object or part of the result was under test.
3. **Inspect each failure:** note which assertions failed, not just the total failure count.
4. **Compare expected and actual:** determine the exact discrepancy.
5. **Cross-check fixtures and actions:** see whether input data or processing explains the mismatch.
6. **Pinpoint the root error:** distinguish independent mismatches from errors caused by a failed precondition.

For example, if the `order response` group has failures on `response status` and `total amount`, that tells you both observed properties missed expectations. You cannot yet conclude whether the bug lies in the service, DTO mapping, or stored data. Trace the test's data and actions to determine where the discrepancy originated.

Good messages do not replace root-cause investigation. They shorten the localization step by giving specific enough context to start from.

## 12. Common Mistakes When Using assertAll and Messages

| Practice | Consequence | Improvement |
|---|---|---|
| Grouping unrelated assertions | Reports are hard to categorize | Group by object or topic |
| Overly generic heading like `"test"` | Does not help locate failing area | Use headings describing the response or properties |
| Message just says `"failed"` | Adds no context | State field name or rule |
| Asserting after dereferencing a possibly null object | Triggers secondary errors | Check precondition first |
| Performing actions inside multiple lambdas | May execute business logic repeatedly | Act once, assert afterward |
| Using assertAll for every single assertion | Verbose code with no extra insight | Use direct assertions where appropriate |
| Nesting too many levels | Hard to follow report structure | Nest only when groups have real meaning |
| Putting entire objects into messages | Long reports and potential data exposure | Add only necessary identifiers or context |

A good test does not try to maximize message volume. It provides just enough information for readers to understand the failure condition without guessing.

## 13. Combining assertAll with Arrange–Act–Assert

You can keep tests readable by clearly separating the three sections:

```java
@Test
void createsConfirmedOrderResponse() {
    // Arrange
    CreateOrderCommand command = new CreateOrderCommand(
            "CUSTOMER-42",
            List.of(new OrderLineCommand("BOOK-01", 2))
    );

    // Act
    OrderResponse response = orderService.create(command);

    // Assert
    assertNotNull(response, "order response should be returned");

    assertAll("created order",
            () -> assertEquals(
                    OrderStatus.CONFIRMED,
                    response.getStatus(),
                    "initial order status"
            ),
            () -> assertEquals(
                    "CUSTOMER-42",
                    response.getCustomerId(),
                    "customer id"
            ),
            () -> assertEquals(
                    1,
                    response.getItems().size(),
                    "number of order lines"
            )
    );
}
```

Fixtures and commands show initial conditions. The action is called exactly once. The precondition assertion guarantees the response exists, and `assertAll` verifies independent properties of the outcome.

In practice, class names and state rules depend on the application. What matters is that each part of the test clearly expresses prepared data, action, and expected evidence.

## 14. The Value of Failure Messages in the Development Workflow

Automated tests commonly run on developer machines and in CI after every change. When a test fails, the person reading the report may not be the author of the test or the author of the change. Group headings and clear messages help them understand the context without needing to run a debugger immediately.

When combined properly:

- `assertAll` shows which multiple conditions failed together.
- Assertion messages identify the meaning of each condition.
- Expected and actual display the exact mismatch.
- Fixtures and the Act section allow reproducing the scenario.
- The test method name indicates the behavior being protected.

Together, this information forms an actionable report. Developers can isolate the problem, review the relevant changes, and decide whether to fix the logic, fixture data, or test expectations.

JUnit Jupiter cannot determine the business cause of a failure on its own. Test authors must select meaningful assertion groups, place messages appropriately, and keep setup easy to understand. Done well, `assertAll` catches multiple mismatches in a single run, and failure messages turn those mismatches into clear diagnostic information.

