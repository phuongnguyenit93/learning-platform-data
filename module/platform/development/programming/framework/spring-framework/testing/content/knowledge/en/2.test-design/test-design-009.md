# Avoid Copying the Implementation Algorithm into Assertions

A test is valuable only when it can catch a defect in the code under test. Therefore, the mechanism that determines the expected result must be independent of how the program computes that result. If a test duplicates the exact same algorithm, branching conditions, or formula from production code to compute expected values, both sides can share the same bug and the test still passes.

In test design for Spring applications, this principle is especially important for business services, monetary calculations, discount rules, classification, sorting, state transitions, and queries with non-trivial logic. Derive expected outcomes from the business contract, independently calculated examples, or meaningful domain properties. Then invoke production code and compare the actual outcome against those expectations.

## 1. Why Should Tests Not Repeat the Algorithm?

A test typically has three parts:

1. **Arrange**: prepare inputs and needed collaborators.
2. **Act**: invoke the behavior under test.
3. **Assert**: compare the actual result with what is expected.

The risk appears when Assert re-runs the algorithm from Act to compute the expected value. When that happens, the test ceases to be an independent source of verification.

Suppose a shipping policy states that orders totaling 500,000 VND or more receive free shipping; orders below that threshold incur a 30,000 VND fee. A service might implement the rule like this:

~~~java
public class ShippingFeeService {

    private static final BigDecimal FREE_SHIPPING_LIMIT =
            new BigDecimal("500000");

    private static final BigDecimal STANDARD_FEE =
            new BigDecimal("30000");

    public BigDecimal calculate(BigDecimal subtotal) {
        if (subtotal.signum() < 0) {
            throw new IllegalArgumentException("Subtotal must not be negative");
        }

        if (subtotal.compareTo(FREE_SHIPPING_LIMIT) >= 0) {
            return BigDecimal.ZERO;
        }

        return STANDARD_FEE;
    }
}
~~~

This is a straightforward implementation. Yet if the test uses the same threshold, same comparison operator, and same conditional branch to compute expected, a boundary defect can be duplicated in both places.

### Error-Prone Approach

~~~java
@Test
void calculatesShippingFee() {
    BigDecimal subtotal = new BigDecimal("500000");

    BigDecimal expected =
            subtotal.compareTo(new BigDecimal("500000")) >= 0
                    ? BigDecimal.ZERO
                    : new BigDecimal("30000");

    BigDecimal actual = service.calculate(subtotal);

    assertEquals(expected, actual);
}
~~~

This test looks as if it checks the result, yet it copied the policy and conditional implementation into computing `expected`. If both service and test change **>=** to **>**, the test can stay green even though an order at the exact threshold is charged wrongly.

Moving the duplicated formula into a test helper does not solve the issue either. If the helper still repeats the service's algorithm, both sides carry the same failure risk.

### Approach with Independent Outcomes

Take test cases and outcomes directly from the defined policy and write expected outcomes explicitly:

~~~java
class ShippingFeeServiceTest {

    private final ShippingFeeService service = new ShippingFeeService();

    @ParameterizedTest
    @CsvSource({
        "499999, 30000",
        "500000, 0",
        "750000, 0"
    })
    void calculatesShippingFeeFromPolicy(
            String subtotalText,
            String expectedFeeText) {

        BigDecimal subtotal = new BigDecimal(subtotalText);
        BigDecimal expected = new BigDecimal(expectedFeeText);

        BigDecimal actual = service.calculate(subtotal);

        assertEquals(0, actual.compareTo(expected));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.calculate(new BigDecimal("-1"))
        );
    }
}
~~~

Input and expected outcome pairs are declared independently. The test checks cases just below the threshold, right at the threshold, and above the threshold. If the service accidentally changes **>=** to **>**, the 500,000 VND case fails the test.

In this example, comparing `BigDecimal` with **compareTo** checks numeric value regardless of scale. If scale is part of the output contract—for instance, an API required to return two decimal places—assert scale or JSON formatting separately as an explicit requirement.

## 2. Derive Expected Values from the Contract, Not the Code Under Test

The best source for expected outcomes is usually the business specification, product rules, examples confirmed by domain stakeholders, or independently verified reference datasets.

For example, for a service computing payable amount, the specification might state:

- Quantity multiplied by unit price yields the line-item subtotal.
- Pre-discount total is the sum of line-item subtotals.
- A 10% discount applies to the pre-discount total.
- The discount amount is rounded to the smallest currency unit per the agreed rule.

From a small example, you can calculate independently: two items with subtotals of 25,000 and 10,000 VND; a 10% discount equals 3,500 VND; the payable amount is 31,500 VND. The test should state the inputs and the 31,500 VND result from the verified example rather than calling a production discount function to construct `expected`.

~~~java
@Test
void appliesTenPercentDiscountToKnownSubtotal() {
    var lines = List.of(
            new OrderLine("A", 2, new BigDecimal("12500")),
            new OrderLine("B", 1, new BigDecimal("10000"))
    );

    BigDecimal actual = pricingService.calculatePayable(lines);

    assertEquals(
            0,
            actual.compareTo(new BigDecimal("31500"))
    );
}
~~~

What matters is that the number 31,500 is determined from rules and an independent example. Do not compute `expected` by calling **calculatePayable**, **calculateDiscount**, or a production helper sharing the same logic.

### Keep Each Expected Value's Origin Clear

When a test covers many cases, document the reason behind key values through test names or meaningful data. Examples:

- **returnsFreeShippingAtThreshold** describes policy at the threshold.
- **roundsDiscountAccordingToCurrencyRule** describes the rounding rule.
- **rejectsQuantityBelowZero** describes valid input bounds.

For complex cases, a brief comment can cite the business clause or example that `expected` comes from. Avoid comments explaining each line of the algorithm; the aim is clarifying the source of expectation.

Do not pull private constants from the service as the source of `expected` if the test verifies the policy represented by those constants. If both service and test reference the same wrong constant, changing the constant hides the defect. You can share constants for data outside the rule under test, yet expected outcomes of the rule itself must be determined independently.

## 3. Common Forms of Algorithm Duplication

### Repeating the Same Calculation Formula

If a service calculates a discount by multiplying by a rate and the test calculates `expected` by multiplying by the same rate, a bug in how the rate or rounding is applied appears on both sides.

Instead of writing:

~~~java
BigDecimal expected = subtotal.multiply(discountRate);
assertEquals(expected, service.calculateDiscount(subtotal, discountRate));
~~~

use numeric examples computed independently from the specification, especially for fractional values, thresholds, and rounding rules. For instance, verify the discount amount for a known subtotal and specific rate.

### Repeating Conditional Branches

If production uses **if**, **switch**, or conditional expressions to classify states, the test should not copy the same conditions to select `expected`. List each input and its prescribed output state explicitly.

For example, if an order may transition from **PENDING** to **PAID**, but not from **CANCELLED** to **PAID**, the test should directly assert each valid or invalid state pair according to the business state-transition table.

### Repeating Loops and Collection Transformations

A service sorting a list by creation timestamp should not be tested by copying the comparator into the test to produce the expected list. For a small dataset, write out the required output order explicitly.

~~~java
@Test
void sortsOrdersByCreationTime() {
    var input = List.of(
            order("C", "2026-03-03T10:00:00Z"),
            order("A", "2026-03-01T10:00:00Z"),
            order("B", "2026-03-02T10:00:00Z")
    );

    var result = orderService.sortByCreationTime(input);

    assertEquals(
            List.of("A", "B", "C"),
            result.stream().map(Order::id).toList()
    );
}
~~~

The list **A, B, C** is the explicit outcome derived from sample data. The test does not sort the input with the same comparator to compare against the service result.

### Using the Production Code Itself to Generate Expected

A test is meaningless if `expected` comes from the very method under test:

~~~java
var expected = service.calculate(input);
var actual = service.calculate(input);

assertEquals(expected, actual);
~~~

Both calls can return the same wrong result. Similarly, avoid calling another production helper if that helper shares the algorithm or dependency the test aims to verify.

### Using the Same Converter to Build Expected Output

When testing JSON, XML, dates, or serialized payloads, be cautious about using production's `ObjectMapper`, formatter, or converter to build `expected`. If the serializer has a bug, both `expected` and `actual` can mirror that bug.

For example, if the goal is verifying a public JSON format, compare against a contract-defined JSON literal or assert specific fields and values. If the goal is verifying a converter, `expected` must be defined independently of that converter.

## 4. Use Concrete Examples to Test Boundary Cases

Examples with fixed expected values are especially useful where algorithms have boundaries or error-prone rules. Do not pick just one ordinary case; choose data that distinguishes a correct implementation from common bugs.

Cases worth considering:

| Rule type | Data to watch | What to verify |
|---|---|---|
| Threshold | Just below, right at, and right above threshold | Comparison operators and boundary policy |
| Currency | Fractional values, half-unit results | Rounding rules and scale |
| Quantities | 0, 1, large numbers, negative numbers | Valid bounds and edge behavior |
| Dates and times | Before/after day rollover, time zones, leap years | Time boundaries and calendar rules |
| Collections | Empty, single element, duplicates, reversed order | Behavior across sizes and orderings |
| State | Every important state-transition pair | Allowed and rejected transitions |
| Pagination | First page, last page, out of bounds, size 0 or invalid | Offsets, limits, and total counts |

Boundary tests with fixed expectations catch bugs better than adding many tests with similar inputs. For example, if free shipping starts at 500,000 VND, three cases at 499,999, 500,000, and 500,001 give a much sharper signal than three values all below the threshold.

## 5. For Complex Algorithms, Build an Independent Oracle

For simple algorithms, hand-calculated examples work well. For complex algorithms—such as inventory allocation, scheduling, ranking, routing, or multi-tier pricing—a few hardcoded examples may not provide enough coverage.

In that case, you need a **test oracle**: an authoritative source determining right answers to compare against actual outcomes. There are several ways to build an oracle without blindly copying implementation.

### Independently Verified Golden Datasets

Use a set of inputs and outputs computed or approved by an authoritative source. Store this dataset as a fixture and reuse it across tests.

Example: a shipping fee table validated by business operations per zone, weight, and delivery method. The test reads rows from the fixture and checks that the service returns the matching fee.

Manage the source and version of golden datasets carefully. When policy changes, update the fixture alongside business changes and document why. Never silently regenerate expected values using the new service.

### Independent Reference Model

For large algorithms, you can write a simpler reference model to produce comparison outputs. Build this model from the specification independently and avoid reusing production functions, decision structures, or error-prone assumptions.

For instance, production might use an optimized data structure to allocate orders across warehouses. A reference model on small inputs can exhaustively search combinations following the specification. Because the implementations differ, the chance both share the exact same bug drops.

Even so, a reference model is still code and can contain bugs. Validate it against verified examples and retain several hardcoded expected outcomes so tests do not rely solely on the model.

### Property and Business Invariant Checks

You do not always need the exact expected output for every input. Some algorithms must always satisfy business-defined invariants.

Examples:

- Shipping fees must never be negative.
- Payable amount must not exceed pre-discount subtotal when only discounts apply.
- Paginated results must not contain more items than the requested page size.
- Applying a completed normalization again leaves the result unchanged.
- Sorting an already-sorted list preserves order.

These properties complement concrete expected-value examples. However, an overly broad invariant can let bugs slip by. For instance, a sort function returning the unsorted input list still preserves element count and non-negative elements. Pair invariants with concrete ordering examples.

### Relational Checks Across Multiple Runs

For certain problems, you can verify relationships between inputs and outputs instead of computing the entire expected result. This is commonly called relational or metamorphic testing.

For example, if a string normalizer is specified as idempotent, normalizing the output a second time must yield the same string:

~~~java
@Test
void normalizationIsIdempotent() {
    String once = normalizer.normalize("  Spring   Test  ");
    String twice = normalizer.normalize(once);

    assertEquals(once, twice);
}
~~~

This test verifies a property independent of implementation details. Yet it does not prove the normalized string matches the desired format—if the normalizer always returned an empty string, idempotency would still hold. Therefore, combine it with a concrete output example:

~~~java
@Test
void normalizesKnownInputToExpectedValue() {
    assertEquals(
            "Spring Test",
            normalizer.normalize("  Spring   Test  ")
    );
}
~~~

A good relation comes from the business specification and can detect specific bugs. Do not pick a property merely because it is easy to write.

## 6. Separate Data Setup from Expected-Value Computation

Test helpers are great for keeping Arrange concise. However, helpers should assist in constructing data, stubbing dependencies, or expressing shared assertions; they must not hide a copy of the algorithm under test.

For example, this helper simply creates an `Order` with declared fields:

~~~java
private Order order(String id, BigDecimal subtotal) {
    return new Order(id, subtotal);
}
~~~

This helper executes no pricing rules. It keeps the test focused on behavior.

Conversely, this helper destroys test independence if it duplicates production's total calculation rule:

~~~java
private BigDecimal expectedTotal(List<OrderLine> lines) {
    return lines.stream()
            .map(line -> line.unitPrice()
                    .multiply(BigDecimal.valueOf(line.quantity())))
            .reduce(BigDecimal.ZERO, BigDecimal::add);
}
~~~

If the total-calculation algorithm itself is under test, this helper can suffer the same bug as production. Use pre-determined results or an independent oracle instead.

Guidelines for writing helpers:

- Name after data or business meaning, such as **anOrderWithTwoLines**.
- Pass key values explicitly rather than computing them with production logic.
- Avoid helpers named **expected...** that internally call the method under test.
- Keep important expected values visible in the test or fixture so readers can verify them easily.
- If a helper is shared across tests, keep it simple and exclude the business condition under test.

## 7. Applying This Principle Across Spring Test Levels

Independent expected-value verification applies at every test level. Spring provides environments to test beans, MVC, persistence, and integrations; Spring does not alter the principle governing where expected outcomes come from.

### Unit Tests for Business Services

For pure Java logic needing no container, instantiate the service directly and test with inputs having concrete expected outcomes. Do not use **@SpringBootTest** just to invoke a simple calculation method.

When the service has dependencies, use mocks to control dependency responses. Mock return values should also be fixed data derived from the dependency's contract.

~~~java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private OrderRepository repository;

    @InjectMocks
    private OrderService service;

    @Test
    void marksOrderAsPaidAfterSuccessfulPayment() {
        var order = new Order("order-42", OrderStatus.PENDING);

        when(repository.findById("order-42"))
                .thenReturn(Optional.of(order));

        service.markPaid("order-42");

        assertEquals(OrderStatus.PAID, order.status());
        verify(repository).save(order);
    }
}
~~~

In this example, the test specifies initial state and expected state upfront from business rules. If persistence calls need checking, verify the repository interaction. Do not call a production function to compute the expected state and compare it with what the service produced.

### Web Tests with MockMvc

With **@WebMvcTest**, the target is usually the HTTP contract: status, headers, JSON structure, validation, and error handling.

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @Test
    void returnsExpectedOrderRepresentation() throws Exception {
        when(orderService.findById("order-42"))
                .thenReturn(new OrderView("order-42", "PAID"));

        mockMvc.perform(get("/orders/order-42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("order-42"))
                .andExpect(jsonPath("$.status").value("PAID"));
    }
}
~~~

Values **order-42** and **PAID** are fixed contract data for the test. When verifying JSON serialization, explicitly assert the expected structure and format. Avoid using the same converter to build both actual responses and expected output, as converter bugs would be masked.

### Persistence Tests with `@DataJpaTest`

With **@DataJpaTest**, expected outcomes should come from prepared data and query rules. For example, when testing a repository query finding orders by customer, insert records with known customer IDs and assert the exact set of order IDs returned.

Do not run the same repository query to compute `expected` and then run it again for `actual`. Nor should you compute `expected` using an expression duplicating the WHERE clause when that clause itself is what is under test.

~~~java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void findsOrdersForTheRequestedCustomer() {
        repository.saveAll(List.of(
                new OrderEntity("order-1", "customer-A"),
                new OrderEntity("order-2", "customer-B"),
                new OrderEntity("order-3", "customer-A")
        ));

        var result = repository.findByCustomerId("customer-A");

        assertEquals(
                Set.of("order-1", "order-3"),
                result.stream().map(OrderEntity::getId).collect(Collectors.toSet())
        );
    }
}
~~~

Here `expected` is the concrete set of order IDs from the test data. The test verifies actual database query results rather than duplicating the query predicate in Java to construct the expected set.

### Integration Tests Across Beans and Infrastructure

With **@SpringBootTest**, you can test flows across beans, transactions, and the database. Even with broader scope, `expected` must still come from the contract or golden data. For example, when testing an order-creation transaction, explicitly specify the status, reference code, and amount expected to be persisted per the prepared scenario.

Do not read back data using a service-like calculation function to build `expected`. You may use repositories to observe persisted data, while comparison values must be derived independently from the scenario.

## 8. Combining Fixed Examples, Properties, and Mutation Testing

No single assertion style suffices for every algorithm. A high-signal test suite usually combines:

- **Fixed examples**: confirm a specific input yields a known result.
- **Boundary cases**: confirm behavior at edges and with unusual data.
- **Properties**: confirm invariants that must always hold.
- **Integration tests**: confirm the algorithm is invoked properly in Spring flows and works with needed real dependencies.

A complementary technique is mutation testing. Mutation testing tools make small edits to production code—such as changing **>=** to **>** or altering a conditional value—and re-run tests. If a change breaks behavior while all tests remain green, the suite may not be sensitive enough to that defect.

For example, with the free-shipping policy, changing **>=** to **>** must cause the exact-threshold test to fail. If that mutant survives, review test data and expected values at boundary conditions.

Mutation testing does not prove tests are perfect. A mutant may not alter observable behavior within test scope, or equivalent forms may exist. Still, it provides a useful signal about the suite's ability to catch specific bug classes.

Code coverage must also be interpreted carefully. Executed lines do not imply independent expected values or strong assertions. A high-coverage test can still duplicate an algorithm and miss defects. Judge tests by the broken behaviors they can detect, not solely by lines executed.

## 9. Signs a Test Is Duplicating Production Code

When reviewing a test, watch for these signs:

- `expected` is calculated using the same formula or conditional branches as the method under test.
- The test calls the production method itself or a shared helper to obtain `expected`.
- The test reads private constants from the service as `expected` for the very rule governed by those constants.
- The test uses the same mapper, formatter, or converter to construct both `expected` and `actual`.
- A test helper contains loops, comparators, or business rules identical to production.
- Whenever the algorithm changes, the author has to make the exact same edit to `expected` without any specification change.

When spotting these signs, ask: **If the implementation has a bug, is the current source of `expected` likely to have the exact same bug?** If yes, find a more independent source of truth.

## 10. How to Design Tests with Independent Checks

A practical workflow includes these steps:

1. **Identify public behavior**: describe inputs, outputs, and specified conditions.
2. **Select discriminating examples**: include typical, boundary, and key error cases.
3. **Determine expected values before running**: derive from business rules, verified examples, or golden data.
4. **Write simple Arrange**: build data using builders or fixtures free of the algorithm under test.
5. **Invoke only the behavior under test**: avoid calling production helpers to construct `expected`.
6. **Assert meaningful outcomes**: check values, state, ordering, or observable contracts.
7. **Add properties or mutation checks when needed**: strengthen defect detection without turning tests into copies of implementation.

For example, when testing a fee rule, first write down the policy table and expected values at each threshold. Then write tests with concrete values. When testing queries, identify which records must appear per the query contract. When testing state transitions, list allowed and disallowed transitions.

## 11. What Should and Should Not Be Shared Between Test and Production

Not all code sharing compromises independence. Distinguish sharing infrastructure from sharing the logic under verification.

| Safe to share when appropriate | Avoid sharing when testing that logic |
|---|---|
| Application data types and domain models | Production functions calculating expected values |
| Entity builders taking explicit values | Helper builders computing business fields via the same algorithm |
| JUnit, Mockito, and Spring TestContext | Same mapper or converter building expected values in a serializer test |
| Technical constants unrelated to the rule under test | Policy constants shared by both actual and expected |
| Verified static data fixtures | Fixtures generating expected values via the service under test |

A test can share `Order` or DTO types because they form the contract's data structures. Yet if the test verifies how a service totals an order, do not call the model's total-calculation method to generate `expected`.

When a business rule is reused in multiple places, extracting it into a shared production component can be good design. Even then, tests for that component still need independent expectations. Two services calling the same shared function do not prove that function is right.

## 12. Example of the Impact of Copying the Algorithm

Suppose a policy sets shipping fee to 30,000 VND when order value is below 500,000 VND, and 0 once the threshold is reached.

If both implementation and test use a strict greater-than check, an order of exactly 500,000 VND is charged wrongly while the test may remain green. A test with a fixed expected value right at the threshold catches the defect.

Similarly, if both production and test round down instead of rounding `HALF_UP`, cases with fractional rounding outcomes expose the bug only when expected values are calculated from an independent rule.

This is why discriminating data matters. A suite of trivial values may fail to separate a valid algorithm from a buggy variant. Pick inputs where differing implementations produce differing outputs.

## 13. Conclusion on Check Design

A good test needs an independent basis for asserting which result is correct. For straightforward logic, use concrete input-output pairs derived from the specification. For complex algorithms, combine golden datasets, independent reference models, business invariants, and relational checks. In Spring tests, uphold this principle whether testing a service directly, through an MVC slice, a repository slice, or the full `ApplicationContext`.

When reading an assertion, ask yourself: if production code is wrong, can this check notice? If `expected` is built using the same formula, condition, converter, or helper as production, the answer may be no. Keep the source of expectation clear, independent, and concrete enough that a real defect makes the test fail.

