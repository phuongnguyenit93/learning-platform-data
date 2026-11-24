# Comparing SpEL Results with Reference Java Logic

## Objectives

A SpEL expression typically represents a rule that the application could also write in Java. To verify whether the expression is accurate, build an **independent reference Java logic** and run both approaches on the same data set. The SpEL result is compared against the Java result to detect discrepancies in conditions, data types, nulls, conversion, collection order, or boundary handling.

This testing approach is especially useful when expressions are long, have many conditions, use selection/projection, or are stored as configuration. It verifies SpEL's actual behavior rather than merely checking whether the expression parses successfully.

After this lesson, you will be able to:

- Write reference Java logic for a SpEL expression.
- Evaluate both approaches on the same root object and parameters.
- Compare Boolean, scalar, object, and collection results.
- Align semantics for null, numbers, enums, dates/times, and conversion.
- Test boundary data, invalid data, and empty-result cases.
- Distinguish parse errors, evaluation errors, and bugs in Java logic.
- Use parameterized tests or differential tests to expand coverage.
- Avoid writing a Java reference that simply copies the expression's bugs verbatim.

## 1. Why is reference Java logic needed?

An expression parsing successfully does not prove the business rule is expressed accurately. Example:

~~~text
#root.active and #root.total >= #minimumTotal
~~~

The expression may be syntactically valid yet still use the wrong property, miss a condition, or mishandle null values. A test checking only the expression's result on a single sample input may fail to catch those cases.

Reference Java logic provides a second representation for the same rule. When the two results differ, the test indicates that at least one implementation does not match the expected rule.

This approach fits:

- Pricing, discount, tax, or eligibility rules.
- Filtering collections with selection.
- Transforming collections with projection.
- Checking state and access permissions.
- Expressions with variables passed from EvaluationContext.
- Expressions modified by configurators or stored outside source code.
- Upgrading Spring Framework or changing EvaluationContext/ConversionService.

The Java reference should express business intent in readable code. Do not create a Java method that simply invokes the same SpEL expression, because then the two results are not independent and the test cannot detect logic errors.

## 2. General comparison workflow

For each rule to verify:

1. Write out the rule clearly in business language.
2. Write the SpEL expression implementing that rule.
3. Write an independent Java function representing the same rule.
4. Prepare a shared input set for both approaches.
5. Create an EvaluationContext with the exact root object and variables.
6. Evaluate the expression and invoke the Java reference.
7. Compare results according to the exact semantics of the data type.
8. Repeat with boundary cases, nulls, and invalid data.

For example, the rule is: an order is accepted when it is active, its total is at least the minimum threshold, and its status is APPROVED.

SpEL:

~~~text
#root.active
and #root.total.compareTo(#minimumTotal) >= 0
and #root.status == #requiredStatus
~~~

Java reference:

~~~java
static boolean isAccepted(
        Order order,
        BigDecimal minimumTotal,
        OrderStatus requiredStatus) {

    return order.isActive()
        && order.getTotal().compareTo(minimumTotal) >= 0
        && order.getStatus() == requiredStatus;
}
~~~

Both approaches use the same data yet are implemented independently. When testing, if results differ, inspect each condition and data type instead of just changing the assertion to make the test green.

## 3. Complete example: comparing Boolean results

Suppose the model:

~~~java
public enum OrderStatus {
    NEW, APPROVED, PAID, CANCELLED
}

public class Order {
    private final boolean active;
    private final BigDecimal total;
    private final OrderStatus status;

    public Order(
            boolean active,
            BigDecimal total,
            OrderStatus status) {
        this.active = active;
        this.total = total;
        this.status = status;
    }

    public boolean isActive() {
        return active;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
~~~

Create the expression once:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#root.active and " +
    "#root.total.compareTo(#minimumTotal) >= 0 and " +
    "#root.status == #requiredStatus"
);
~~~

Java reference:

~~~java
static boolean isAccepted(
        Order order,
        BigDecimal minimumTotal,
        OrderStatus requiredStatus) {

    return order.isActive()
        && order.getTotal().compareTo(minimumTotal) >= 0
        && order.getStatus() == requiredStatus;
}
~~~

Comparison test:

~~~java
@Test
void spelMatchesJavaReferenceForOrderEligibility() {
    Order order = new Order(
        true,
        new BigDecimal("150.00"),
        OrderStatus.APPROVED
    );

    BigDecimal minimumTotal = new BigDecimal("100.00");
    OrderStatus requiredStatus = OrderStatus.APPROVED;

    StandardEvaluationContext context =
        new StandardEvaluationContext(order);
    context.setVariable("minimumTotal", minimumTotal);
    context.setVariable("requiredStatus", requiredStatus);

    Boolean spelResult =
        expression.getValue(context, Boolean.class);

    boolean javaResult =
        isAccepted(order, minimumTotal, requiredStatus);

    assertEquals(javaResult, spelResult);
}
~~~

The key point is that the Java reference receives the exact same order, minimumTotal, and requiredStatus as the EvaluationContext. Do not construct a separate data set for Java and SpEL, otherwise differing results may come from inputs rather than logic.

## 4. Comparing scalars and numeric types

For numeric results, do not assume every Java and SpEL comparison behaves identically across all numeric types. Clearly specify source types, target types, precision, and rounding rules.

Example total-calculation expression:

~~~text
#root.unitPrice.multiply(new java.math.BigDecimal(#root.quantity))
~~~

Java reference:

~~~java
static BigDecimal calculateTotal(OrderLine line) {
    return line.getUnitPrice()
        .multiply(BigDecimal.valueOf(line.getQuantity()));
}
~~~

Comparison:

~~~java
BigDecimal spelResult =
    expression.getValue(context, BigDecimal.class);

BigDecimal javaResult = calculateTotal(line);

assertEquals(0, javaResult.compareTo(spelResult));
~~~

With BigDecimal, compareTo compares numeric value without requiring identical scale. equals considers scale as well, so 10.0 and 10.00 are not equal under equals despite having the same numeric value. Choose the comparison matching the data contract.

When checking floating point, define a tolerance if business rules allow rounding error. Do not arbitrarily add tolerance for currency or values requiring decimal precision; use the appropriate type and rounding rules instead.

Numeric cases to test:

- Positive numbers, negative numbers, and zero.
- Values right at the threshold.
- Values just below and just above the threshold.
- Large or small values near type limits.
- BigDecimal with different scales.
- Null values if allowed by the model.
- Conversions among Integer, Long, Double, and BigDecimal if the expression uses conversion.

## 5. Comparing collection selection

For collection selection, the Java reference is typically a stream filter or loop. Compare both the selected elements and order if order is part of the contract.

SpEL:

~~~text
#root.orders.?[
    #this.active and #this.total.compareTo(#minimumTotal) >= 0
]
~~~

Java reference:

~~~java
List<Order> javaResult = orders.stream()
    .filter(Order::isActive)
    .filter(order ->
        order.getTotal().compareTo(minimumTotal) >= 0)
    .toList();
~~~

Evaluating SpEL:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(customer);
context.setVariable("minimumTotal", minimumTotal);

List<?> spelResult =
    expression.getValue(context, List.class);
~~~

Comparing:

~~~java
assertEquals(javaResult.size(), spelResult.size());

for (int i = 0; i < javaResult.size(); i++) {
    Order expected = javaResult.get(i);
    Order actual = (Order) spelResult.get(i);

    assertEquals(expected.getId(), actual.getId());
}
~~~

Comparing by ID or business fields is usually clearer than identity comparison. If the model defines equals/hashCode matching the semantics being tested, assertEquals can be used directly on the collection.

With List, order is usually meaningful and must be checked. With Set, determine whether to compare membership only or iteration order as well. With Map, compare keys/values and do not assume ordering if the implementation does not guarantee order.

## 6. Comparing projection and result structure

Projection transforms each element into a new value. The Java reference can use map:

SpEL:

~~~text
#root.orders.?[#this.active].![#this.id]
~~~

Java:

~~~java
List<String> javaResult = orders.stream()
    .filter(Order::isActive)
    .map(Order::getId)
    .toList();
~~~

When comparing, check:

- Whether the result type is accurate.
- Number of elements.
- Value of each element.
- Order if the collection is ordered.
- Handling of null elements.
- Nested collection structure if there are multiple projection levels.

Nested projections do not automatically flatten. For example, if each Department has a list of Employees, an expression projecting employee names per department produces a nested list structure. The Java reference must use map at the same level to produce the matching structure; do not use flatMap if SpEL does not flatten the result.

## 7. Ensuring identical semantics

Java and SpEL can differ in conversion, null handling, operator behavior, or property access. When comparing, explicitly decide on the desired rule and make both implementations follow that same rule.

### Null

Define whether null is allowed and what it means:

- Null is invalid input and must be rejected.
- Null is treated as false.
- Null is replaced with a default value.
- Null is a distinct state that must be preserved.

SpEL example using safe navigation:

~~~text
#root.customer?.active == true
~~~

Corresponding Java reference:

~~~java
boolean javaResult =
    order.getCustomer() != null
        && order.getCustomer().isActive();
~~~

If the Java reference defaults null to false while SpEL throws an exception due to missing safe navigation, the test will expose the difference.

### BigDecimal and arithmetic

If Java uses compareTo, the expression should express the same semantics, for example:

~~~text
#root.total.compareTo(#minimumTotal) >= 0
~~~

Do not compare using Java equals in the reference and numeric comparison differently in SpEL without intent.

### String and enum

Explicitly specify whether comparisons are case-sensitive. If Java uses equalsIgnoreCase, the expression needs to call the corresponding method or normalize both sides. If status is an enum, comparing enum constants usually avoids string spelling bugs.

### Date and time

Both implementations must use the same timezone, Clock, locale, and time-boundary rules. Do not call LocalDateTime.now() separately in the two implementations and compare directly if the timestamps could differ. Pass a fixed Clock or timestamp into both implementations.

### Conversion

If the expression relies on TypeConverter/ConversionService, the Java reference must apply the same conversion rules or receive pre-normalized data. Do not let SpEL auto-convert String to Integer while the Java reference parses using a different rule.

## 8. Comparing variables in EvaluationContext

If the expression uses variables, the Java reference must receive those same values as explicit parameters.

SpEL:

~~~text
#root.score >= #minimumScore
and #root.status == #requiredStatus
~~~

Java:

~~~java
static boolean qualifies(
        Student student,
        int minimumScore,
        StudentStatus requiredStatus) {

    return student.getScore() >= minimumScore
        && student.getStatus() == requiredStatus;
}
~~~

In tests, set variables on the context:

~~~java
context.setVariable("minimumScore", minimumScore);
context.setVariable("requiredStatus", requiredStatus);
~~~

Do not read variables from a global field in the Java reference while SpEL reads from the context. That creates two different data sources and can mask variable-passing bugs.

If a separate context is created per request, the Java reference should also be invoked with parameters belonging to that exact request. Do not reuse a mutable context across parallel tests if it can mix variable values.

## 9. Using parameterized tests to cover many cases

Instead of checking only one data set, use JUnit 5 parameterized tests to run the same rule against multiple inputs.

Example:

~~~java
@ParameterizedTest
@MethodSource("orderCases")
void spelMatchesJavaReference(
        Order order,
        BigDecimal minimumTotal,
        OrderStatus requiredStatus) {

    StandardEvaluationContext context =
        new StandardEvaluationContext(order);
    context.setVariable("minimumTotal", minimumTotal);
    context.setVariable("requiredStatus", requiredStatus);

    Boolean spelResult =
        expression.getValue(context, Boolean.class);

    boolean javaResult =
        isAccepted(order, minimumTotal, requiredStatus);

    assertEquals(javaResult, spelResult);
}

static Stream<Arguments> orderCases() {
    return Stream.of(
        Arguments.of(
            new Order(true, new BigDecimal("150"), OrderStatus.APPROVED),
            new BigDecimal("100"),
            OrderStatus.APPROVED
        ),
        Arguments.of(
            new Order(false, new BigDecimal("150"), OrderStatus.APPROVED),
            new BigDecimal("100"),
            OrderStatus.APPROVED
        ),
        Arguments.of(
            new Order(true, new BigDecimal("50"), OrderStatus.APPROVED),
            new BigDecimal("100"),
            OrderStatus.APPROVED
        ),
        Arguments.of(
            new Order(true, new BigDecimal("150"), OrderStatus.NEW),
            new BigDecimal("100"),
            OrderStatus.APPROVED
        )
    );
}
~~~

The cases above test valid, inactive, below-threshold total, and mismatched status respectively. Add cases right at the threshold, null data if allowed, and boundary values.

For tests with many parameters, naming cases or using descriptive Arguments helps quickly identify which case failed.

## 10. Differential testing with generated data

When a rule has many branches, many input sets can be generated to compare SpEL against the Java reference. This is differential testing: two implementations receive the same input and results are compared automatically.

Workflow:

1. Define the valid input domain.
2. Generate random inputs or use a boundary-coverage strategy.
3. Build the root object and context variables from the same input.
4. Evaluate SpEL.
5. Evaluate the Java reference.
6. Compare results.
7. When a mismatch occurs, save the seed and minimal reproducing input.
8. Turn the failing case into a fixed regression test.

Example dimensions of data to generate:

- Boolean active.
- Totals from negative, zero to large values.
- Enum statuses.
- Different minimum thresholds.
- Empty, single-element, and multi-element collections.
- Optional properties present or absent.
- Different runtime types if allowed by the model.

Generated data must be constrained to the valid domain. If generating invalid inputs, test separately that both implementations reject them under the same contract, rather than comparing an arbitrary outcome.

Do not rely only on random data. Keep explicit tests for boundary values because they are easy to read, review, and reproduce deterministically.

## 11. Comparing errors and failure behavior

Not every test should compare return values. Some rules require confirming both implementations reject invalid input.

For example, if total must be non-null:

- The Java reference may throw IllegalArgumentException with a business message.
- SpEL may throw SpelEvaluationException or wrap an exception from a getter/method.

The two implementations do not necessarily have to throw the exact same exception class. What needs comparison is the observable contract: whether the input is accepted, which category the error belongs to at the application layer, and whether data was unintentionally mutated.

Separate tests can be written for:

- Expression parse failure.
- Property or method access failure.
- Conversion failure.
- Null input rejection.
- Java reference validation failure.
- Functions or methods inside the expression throwing exceptions.

If the application needs a unified error API, translate technical exceptions into business errors at the service boundary. Do not compare full message text between SpEL and Java because wording can differ across versions and implementations.

## 12. Avoiding a Java reference with the same bugs as SpEL

A comparison test is only useful when the two implementations are independent enough for discrepancies to surface.

Do not:

- Write the Java reference by calling the same expression again.
- Copy the exact same condition chain verbatim without checking business meaning.
- Use the same helper suspected of being the bug source on both sides.
- Produce expected results by calling the code under test.
- Edit the Java reference merely to match SpEL output without checking business rules.

Do:

- Write the Java reference using readable code structures and meaningful names.
- Verify each condition against business requirements.
- Include explicit expected values for several important cases.
- Review boundary cases independently of implementation.
- When the two approaches differ, check the requirement before deciding which one is right.

The Java reference can also be wrong. Differential testing only detects disagreement; it does not by itself prove which implementation is right. A third oracle such as verified business examples or explicit expected values remains necessary for critical rules.

## 13. Common bugs and how to diagnose them

| Symptom | Possible cause | How to handle |
|---|---|---|
| SpEL and Java produce different Booleans | Non-equivalent condition, null, or operator | Break the rule into individual conditions and compare |
| Numeric results differ slightly | Different precision, scale, rounding, or numeric type | Standardize types and comparison rules |
| Collections have same elements in different order | One implementation does not preserve ordering like the other | Determine whether order is part of the contract |
| Collections have different element counts | Different predicate, null handling, or conversion | Inspect individual elements and conditions |
| Projections have different structures | One side flattens or maps at the wrong level | Compare result types and structure at each level |
| Fails only on null | Safe navigation and Java null check are not equivalent | Define the null contract and align both sides |
| Fails only with enum/String | Different normalization or comparison rules | Use enums or normalize Strings explicitly |
| Fails only with dates/times | Different timezone, locale, or current time | Pass fixed Clock/ZoneId |
| Flaky test passing and failing | Using real-time data, unseeded random, or shared context | Fix inputs and isolate contexts |
| Both violate the requirement identically | Java reference copied the same wrong assumption | Add independent expected values from business rules |

When a mismatch occurs, record the inputs, variables, root type, expression version, and each side's result. Then shrink the input to locate the first condition where results diverge.

## 14. Workflow for building a comparison test suite

1. **Lock down the business rule.** Write conditions in clear language and identify boundary cases.
2. **Write the Java reference.** Use plain code, explicit parameters, and no calls back into SpEL.
3. **Write the expression.** Keep root object and context variable names consistent.
4. **Prepare a shared fixture.** Use the same objects and parameters for both approaches.
5. **Choose comparison method.** Specify equals, compareTo, field comparison, or collection ordering.
6. **Test basic cases.** Cover true, false, and at-threshold.
7. **Test nulls and conversion.** Use the application's actual EvaluationContext/ConversionService.
8. **Test collections.** Compare counts, elements, structure, and order.
9. **Expand data.** Use parameterized or differential testing for broad input domains.
10. **Keep regression cases.** Every fixed mismatch should become a permanent test.
11. **Verify with an independent oracle.** For critical rules, check several expected values determined from business requirements.

## 15. Best practices

- Always write down the business rule clearly before writing the two implementations.
- Keep the Java reference independent of the expression under test.
- Use the same root object and same variables for both SpEL and Java.
- Request an explicit result type from getValue when appropriate.
- Compare BigDecimal with compareTo if the contract is based on numeric value.
- Verify both collection contents and order when order is meaningful.
- Align null handling, conversion, locale, timezone, and rounding.
- Use parameterized tests for branches and boundary values.
- Use differential testing to expand inputs, saving seeds and failing cases.
- Test error behavior separately without relying on full exception messages.
- Do not share a mutable EvaluationContext across tests running in parallel.
- Keep explicit expected values for critical rules.
- Convert every discovered mismatch into a regression test.

## 16. Review checklist

Before accepting a SpEL expression, verify:

- [ ] The business rule is clearly described.
- [ ] An independent Java reference exists.
- [ ] Both approaches use the same root object and parameters.
- [ ] EvaluationContext variables align with corresponding Java parameters.
- [ ] Result types and comparison methods are defined.
- [ ] Null handling is equivalent.
- [ ] Numeric precision, scale, and rounding are appropriate.
- [ ] Locale, timezone, and current time are fixed when needed.
- [ ] Collection size, elements, structure, and order are checked.
- [ ] ConversionService in tests matches application configuration.
- [ ] Boundary values and invalid inputs are tested.
- [ ] Exception/validation behavior is tested.
- [ ] Java reference does not call the expression again or copy the same bug.
- [ ] Independent expected values exist for critical business cases.
- [ ] Mismatch cases are retained as regression tests.

## Conclusion

Comparing SpEL against reference Java logic verifies behavior using two independent implementations on the same data. The Java reference must express the same business rule without calling back into the expression under test. Compare results according to the exact data type, align null handling, conversion, precision, timezone, and collection ordering, and then expand coverage with parameterized or differential testing. When the two results differ, use the inputs and individual conditions to isolate the discrepancy, while keeping independent expected values for critical rules.