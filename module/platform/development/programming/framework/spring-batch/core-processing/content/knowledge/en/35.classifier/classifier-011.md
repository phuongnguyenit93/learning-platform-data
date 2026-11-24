# Testing Every Classifier Branch

In Spring Batch, a classifier selects the next handler based on an item's characteristics or execution outcome. For example, domestic orders go through a domestic tax processor, international orders go through an export fee processor, and orders with missing data are routed to a manual review branch.

A classifier can have many branches, boundary conditions, and a default branch. If you only test one happy path, bugs such as misclassifying values near thresholds, forgetting a new enum value, returning a null delegate, or routing an item to the wrong writer may only surface during real batch runs.

Thorough testing must cover two layers:

- **The classifier:** for every input, does the classification result match the rules?
- **The branched components:** does the selected processor or writer actually receive the right items and execute the right behavior?

In Spring Batch, classifiers are commonly used with ClassifierCompositeItemProcessor or ClassifierCompositeItemWriter. This article focuses on testing every branch, boundary values, fallbacks, errors, and Step behavior when a selected branch fails.

## 1. What Does a Classifier Do?

A Classifier is a classification function: it accepts an input object and returns a selected result based on conditions.

In Spring Batch, the general interface looks like:

~~~java
public interface Classifier<C, T> {
    T classify(C classifiable);
}
~~~

Where:

- C is the input data type to classify.
- T is the classification result, typically a processor, writer, or handler.

For example, classifying orders by value and region:

~~~text
Order
  |
  v
OrderClassifier
  |
  +--> HIGH_VALUE
  |
  +--> INTERNATIONAL
  |
  +--> DOMESTIC
  |
  +--> REVIEW
~~~

A classifier should contain clear branch-selection rules and be independently testable. Avoid placing database queries, API calls, or side effects inside classify if avoidable. A pure, deterministic, side-effect-free classifier is easy to test and causes fewer surprises when Spring Batch re-invokes the component.

## 2. Identify All Branches Before Writing Tests

Before creating tests, list every possible return value and the conditions leading to each result.

Example:

| Branch | Condition | Processing |
| --- | --- | --- |
| HIGH_VALUE | Total amount greater than or equal to threshold | Priority processor/writer |
| INTERNATIONAL | Not HIGH_VALUE and customer type is international | Foreign currency handling |
| DOMESTIC | Not in the two branches above and domestic customer | Domestic handling |
| REVIEW | Missing data or requires verification | Send to inspection queue |

This table clarifies priority order. If an order is both high value and international, which branch must the classifier choose? Without specifying order, two developers can write two different classification implementations and both think theirs is right.

Document explicitly:

- Conditions for each branch.
- Priority order when multiple conditions hold true.
- How nulls and missing data are handled.
- Default branch for unrecognized values.
- Which cases must throw an exception instead of choosing a fallback.
- Whether any branch must never receive items.

Do not use one generic default branch for all invalid data if doing so masks schema or business errors.

## 3. Writing a Classifier with Explicit Outcomes

Example data model:

~~~java
public record Order(
        long orderId,
        String region,
        BigDecimal totalAmount) {
}

public enum OrderRoute {
    HIGH_VALUE,
    INTERNATIONAL,
    DOMESTIC,
    REVIEW
}
~~~

Classifier:

~~~java
public class OrderRouteClassifier
        implements Classifier<Order, OrderRoute> {

    private static final BigDecimal HIGH_VALUE_LIMIT =
            new BigDecimal("1000000.00");

    @Override
    public OrderRoute classify(Order order) {
        if (order == null || order.region() == null
                || order.totalAmount() == null) {
            return OrderRoute.REVIEW;
        }

        if (order.totalAmount().compareTo(HIGH_VALUE_LIMIT) >= 0) {
            return OrderRoute.HIGH_VALUE;
        }

        if ("INTERNATIONAL".equals(order.region())) {
            return OrderRoute.INTERNATIONAL;
        }

        if ("DOMESTIC".equals(order.region())) {
            return OrderRoute.DOMESTIC;
        }

        return OrderRoute.REVIEW;
    }
}
~~~

Here, HIGH_VALUE is checked before region. Thus an international order with a total amount greater than or equal to the threshold is classified as HIGH_VALUE. Tests must verify this priority policy.

If business rules want all international orders to go to INTERNATIONAL regardless of amount, swap the condition order and update the test matrix accordingly. What matters is that rules are intentional and tested.

## 4. Testing the Classifier Directly

Unit tests should call classify() directly with each input type. There is no need for JobLauncher or a Spring ApplicationContext when testing only classification rules.

Example:

~~~java
class OrderRouteClassifierTest {

    private final OrderRouteClassifier classifier =
            new OrderRouteClassifier();

    @Test
    void classifiesHighValueOrder() {
        Order order = new Order(
                1L,
                "DOMESTIC",
                new BigDecimal("1500000.00"));

        assertEquals(
                OrderRoute.HIGH_VALUE,
                classifier.classify(order));
    }

    @Test
    void classifiesInternationalOrderBelowThreshold() {
        Order order = new Order(
                2L,
                "INTERNATIONAL",
                new BigDecimal("500000.00"));

        assertEquals(
                OrderRoute.INTERNATIONAL,
                classifier.classify(order));
    }

    @Test
    void classifiesDomesticOrderBelowThreshold() {
        Order order = new Order(
                3L,
                "DOMESTIC",
                new BigDecimal("500000.00"));

        assertEquals(
                OrderRoute.DOMESTIC,
                classifier.classify(order));
    }

    @Test
    void sendsUnknownRegionToReview() {
        Order order = new Order(
                4L,
                "UNKNOWN",
                new BigDecimal("500000.00"));

        assertEquals(
                OrderRoute.REVIEW,
                classifier.classify(order));
    }
}
~~~

These tests confirm each primary outcome. However, you still need to test boundary values and cases where multiple conditions match simultaneously.

## 5. Testing Boundary Values

If a classifier uses an amount threshold, test values just below the threshold, equal to the threshold, and just above the threshold.

For threshold 1,000,000:

| Input | Expected result |
| ---: | --- |
| 999,999.99 | INTERNATIONAL or DOMESTIC by region |
| 1,000,000.00 | HIGH_VALUE |
| 1,000,000.01 | HIGH_VALUE |

Example:

~~~java
@ParameterizedTest
@CsvSource({
        "999999.99, DOMESTIC",
        "1000000.00, HIGH_VALUE",
        "1000000.01, HIGH_VALUE"
})
void classifiesAmountAtThreshold(
        String amount,
        OrderRoute expected) {

    Order order = new Order(
            10L,
            "DOMESTIC",
            new BigDecimal(amount));

    assertEquals(expected, classifier.classify(order));
}
~~~

Never use double for monetary values in threshold tests. BigDecimal compares decimal amounts accurately per business specifications.

In addition to monetary thresholds, test:

- Empty strings and whitespace-only strings.
- New or unrecognized enum values.
- Dates immediately before, on, and after cutoff.
- Quantities of zero, negative values, and maximum limits.
- Regions with differing casing if inputs are not normalized.
- Null in every field read by the classifier.

If inputs are normalized before classification, test the normalization step as well or verify the classifier receives normalized data per contract.

## 6. Testing Priority Order Among Conditions

A classifier can contain multiple conditions that are true at the same time. Write dedicated tests for overlapping cases to verify the priority branch.

Example:

~~~java
@Test
void highValueTakesPriorityOverInternationalRegion() {
    Order order = new Order(
            20L,
            "INTERNATIONAL",
            new BigDecimal("1500000.00"));

    assertEquals(
            OrderRoute.HIGH_VALUE,
            classifier.classify(order));
}
~~~

If you only test a domestic HIGH_VALUE order and a low-value INTERNATIONAL order, the test suite has not verified priority order.

For complex boolean conditions, build a combination table to ensure each condition takes both true and false values in critical scenarios. You do not need to enumerate every combination if there are many conditions, yet you must cover combinations that change branches.

## 7. Testing Null and Invalid Data

Null can appear on the object itself or on properties read by the classifier. Define the desired behavior:

- Return the REVIEW branch.
- Throw an input-data exception.
- Reject the input in validation before the classifier runs.

Example where the current classifier routes missing data to REVIEW:

~~~java
@Test
void sendsNullOrderToReview() {
    assertEquals(
            OrderRoute.REVIEW,
            classifier.classify(null));
}

@Test
void sendsMissingRegionToReview() {
    Order order = new Order(
            21L,
            null,
            new BigDecimal("100.00"));

    assertEquals(
            OrderRoute.REVIEW,
            classifier.classify(order));
}

@Test
void sendsMissingAmountToReview() {
    Order order = new Order(22L, "DOMESTIC", null);

    assertEquals(
            OrderRoute.REVIEW,
            classifier.classify(order));
}
~~~

If null is a programming error and must never occur, you can use Objects.requireNonNull and test for the exception. Do not let null behavior depend accidentally on a NullPointerException at a comparison line.

### Distinguishing Fallback from Exception

Fallback fits when an intentional business branch exists, such as REVIEW. Exception fits when the input violates the contract and cannot be classified safely.

Do not route every strange value to DOMESTIC just because it is the most common branch. A new region could be INTERNATIONAL or a special type; wrong fallback can produce corrupted data while the Job still finishes COMPLETED.

## 8. Testing the Classifier with Parameterized Tests

When there are many input cases, MethodSource can create clearly named test cases with explicit data:

~~~java
static Stream<Arguments> routeCases() {
    return Stream.of(
            Arguments.of(
                    new Order(1L, "DOMESTIC", new BigDecimal("1500000")),
                    OrderRoute.HIGH_VALUE),
            Arguments.of(
                    new Order(2L, "INTERNATIONAL", new BigDecimal("500000")),
                    OrderRoute.INTERNATIONAL),
            Arguments.of(
                    new Order(3L, "DOMESTIC", new BigDecimal("500000")),
                    OrderRoute.DOMESTIC),
            Arguments.of(
                    new Order(4L, "OTHER", new BigDecimal("500000")),
                    OrderRoute.REVIEW)
    );
}

@ParameterizedTest(name = "case {index} returns {1}")
@MethodSource("routeCases")
void classifiesEveryRoute(Order input, OrderRoute expected) {
    assertEquals(expected, classifier.classify(input));
}
~~~

Parameterized tests reduce boilerplate, yet each case must remain readable. If a test fails, the case name or arguments should pinpoint which condition broke.

Avoid stuffing too many unrelated cases into one long undescribed list. Group tests by high value, region, null, and fallback so reports are easier to read.

## 9. Testing Every Branch of ClassifierCompositeItemWriter

ClassifierCompositeItemWriter selects a writer per item. One writer can receive the items classified into the same branch.

Example:

~~~java
@Bean
public ClassifierCompositeItemWriter<Order> orderWriter(
        ItemWriter<Order> highValueWriter,
        ItemWriter<Order> internationalWriter,
        ItemWriter<Order> domesticWriter,
        ItemWriter<Order> reviewWriter) {

    return new ClassifierCompositeItemWriterBuilder<Order>()
            .classifier(order -> {
                OrderRoute route = orderRouteClassifier.classify(order);
                return switch (route) {
                    case HIGH_VALUE -> highValueWriter;
                    case INTERNATIONAL -> internationalWriter;
                    case DOMESTIC -> domesticWriter;
                    case REVIEW -> reviewWriter;
                };
            })
            .build();
}
~~~

This configuration example uses Spring Batch 5. If your project uses a different version, check the corresponding builder and generic signatures. You can configure ClassifierCompositeItemWriter directly with the classifier setter if not using a builder.

### Testing Writer Routing

Mock each delegate and send a chunk containing items for all branches:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderWriterRoutingTest {

    @Mock
    private ItemWriter<Order> highValueWriter;

    @Mock
    private ItemWriter<Order> internationalWriter;

    @Mock
    private ItemWriter<Order> domesticWriter;

    @Mock
    private ItemWriter<Order> reviewWriter;

    private ClassifierCompositeItemWriter<Order> writer;

    @BeforeEach
    void setUp() {
        OrderRouteClassifier routeClassifier =
                new OrderRouteClassifier();

        writer = new ClassifierCompositeItemWriter<>();
        writer.setClassifier(order -> switch (routeClassifier.classify(order)) {
            case HIGH_VALUE -> highValueWriter;
            case INTERNATIONAL -> internationalWriter;
            case DOMESTIC -> domesticWriter;
            case REVIEW -> reviewWriter;
        });
    }

    @Test
    void routesItemsToEveryExpectedWriter() throws Exception {
        Order high = new Order(
                1L, "DOMESTIC", new BigDecimal("1500000"));
        Order international = new Order(
                2L, "INTERNATIONAL", new BigDecimal("500000"));
        Order domestic = new Order(
                3L, "DOMESTIC", new BigDecimal("500000"));
        Order review = new Order(
                4L, "OTHER", new BigDecimal("500000"));

        writer.write(new Chunk<>(
                List.of(high, international, domestic, review)));

        verify(highValueWriter).write(any());
        verify(internationalWriter).write(any());
        verify(domesticWriter).write(any());
        verify(reviewWriter).write(any());
    }
}
~~~

The test above confirms each branch's delegate is invoked. For stricter verification, capture each delegate's chunk and verify that only items belonging to that branch appear in that chunk.

### Checking Chunk Contents

Example using ArgumentCaptor:

~~~java
@Captor
private ArgumentCaptor<Chunk<Order>> highValueChunk;

@Test
void sendsOnlyHighValueItemsToHighValueWriter() throws Exception {
    Order high1 = new Order(
            1L, "DOMESTIC", new BigDecimal("1500000"));
    Order high2 = new Order(
            2L, "INTERNATIONAL", new BigDecimal("2000000"));
    Order normal = new Order(
            3L, "DOMESTIC", new BigDecimal("100000"));

    writer.write(new Chunk<>(List.of(high1, high2, normal)));

    verify(highValueWriter).write(highValueChunk.capture());

    assertEquals(
            List.of(1L, 2L),
            highValueChunk.getValue().getItems().stream()
                    .map(Order::orderId)
                    .toList());
}
~~~

In real tests, initialize Mockito annotations using MockitoExtension or MockitoAnnotations.openMocks. Depending on the generic signature of ItemWriter.write, you may need to declare ArgumentCaptor with a wildcard or use argThat to avoid type errors.

ClassifierCompositeItemWriter may group items by delegate before calling the writer. Therefore, do not assume each item triggers a separate write call. Also do not assert invocation order across delegates if the implementation does not guarantee ordering; assert the set of delegates invoked and the contents of each delegate's chunks.

## 10. Testing Branches with No Items

A chunk might contain no items for a particular branch. That branch's delegate must not be invoked during this write.

Example chunk with only domestic orders:

~~~java
@Test
void doesNotCallInternationalWriterWhenChunkHasNoInternationalOrders()
        throws Exception {

    Order domestic = new Order(
            10L, "DOMESTIC", new BigDecimal("100.00"));

    writer.write(new Chunk<>(List.of(domestic)));

    verify(domesticWriter).write(any());
    verifyNoInteractions(internationalWriter);
    verifyNoInteractions(highValueWriter);
    verifyNoInteractions(reviewWriter);
}
~~~

This test helps catch classifiers or composite configurations that mistakenly broadcast items to multiple delegates.

For empty chunks, define expected behavior per component and version. Usually there are no items to classify so delegates do not need to receive chunks. Tests can verify no delegate is called if that is the application's contract.

## 11. Testing Classifier Returning a Default Delegate

If the classifier supports a fallback, tests must verify the fallback is chosen for all unrecognized values:

~~~java
@Test
void routesUnknownRegionToReviewWriter() throws Exception {
    Order unknown = new Order(
            30L, "NEW_REGION", new BigDecimal("100.00"));

    writer.write(new Chunk<>(List.of(unknown)));

    verify(reviewWriter).write(any());
    verifyNoInteractions(domesticWriter);
    verifyNoInteractions(internationalWriter);
    verifyNoInteractions(highValueWriter);
}
~~~

Do not merely assert that the classifier returns REVIEW; verify REVIEW maps to the right reviewWriter. Those two layers can be misconfigured independently.

### Never Return a Null Delegate

If the classifier returns null, the composite has no valid writer to handle the item. Depending on implementation, failure may occur during grouping or when invoking write. Check for null right inside the classifier or configure an explicit fallback.

Example:

~~~java
private ItemWriter<Order> writerFor(OrderRoute route) {
    ItemWriter<Order> selected = writers.get(route);
    if (selected == null) {
        throw new IllegalArgumentException(
                "No writer configured for route " + route);
    }
    return selected;
}
~~~

Tests should confirm unconfigured route values produce a clear exception instead of a hard-to-diagnose NullPointerException.

## 12. Testing ClassifierCompositeItemProcessor

ClassifierCompositeItemProcessor selects a processor by input. This is used when item types need different transformation logic:

~~~text
OrderInput
    |
    v
Classifier
    |
    +--> DomesticProcessor
    |
    +--> InternationalProcessor
    |
    +--> ReviewProcessor
~~~

Configuration example:

~~~java
@Bean
public ClassifierCompositeItemProcessor<Order, OrderResult>
        orderProcessor(
                ItemProcessor<Order, OrderResult> domesticProcessor,
                ItemProcessor<Order, OrderResult> internationalProcessor,
                ItemProcessor<Order, OrderResult> reviewProcessor) {

    ClassifierCompositeItemProcessor<Order, OrderResult> composite =
            new ClassifierCompositeItemProcessor<>();

    composite.setClassifier(order -> switch (orderRouteClassifier.classify(order)) {
        case HIGH_VALUE, DOMESTIC -> domesticProcessor;
        case INTERNATIONAL -> internationalProcessor;
        case REVIEW -> reviewProcessor;
    });

    return composite;
}
~~~

Merging HIGH_VALUE into domestic here only illustrates processor selection; real applications may use a dedicated processor for HIGH_VALUE. Keep business rules consistent between processor and writer if both branch.

### Testing Each Selected Processor

You can mock processor delegates:

~~~java
@Test
void delegatesInternationalOrderToInternationalProcessor()
        throws Exception {

    Order input = new Order(
            40L, "INTERNATIONAL", new BigDecimal("500.00"));
    OrderResult expected = new OrderResult(40L, "CROSS_BORDER");

    when(internationalProcessor.process(input)).thenReturn(expected);

    OrderResult result = composite.process(input);

    assertEquals(expected, result);
    verify(internationalProcessor).process(input);
    verifyNoInteractions(domesticProcessor, reviewProcessor);
}
~~~

Repeat checks for every branch. For a processor returning null to filter an item, tests must confirm null is propagated properly per contract; do not confuse null output with a classifier error.

### Testing Exceptions from the Selected Processor

~~~java
@Test
void propagatesFailureFromSelectedProcessor() throws Exception {
    Order input = new Order(
            41L, "INTERNATIONAL", new BigDecimal("500.00"));

    when(internationalProcessor.process(input))
            .thenThrow(new IllegalStateException("pricing unavailable"));

    assertThrows(
            IllegalStateException.class,
            () -> composite.process(input));

    verify(internationalProcessor).process(input);
    verifyNoInteractions(domesticProcessor, reviewProcessor);
}
~~~

ClassifierCompositeItemProcessor does not retry processors itself. Retry is behavior of the Step's fault-tolerant configuration. Unit tests confirm exceptions propagate outward; integration tests confirm Step retry/skip per policy.

## 13. Testing the Classifier Independently from Routing Components

A testable design extracts the classifier into a separate bean:

~~~java
@Bean
public Classifier<Order, OrderRoute> orderRouteClassifier() {
    return new OrderRouteClassifier();
}
~~~

Then writer/processor mapping only converts OrderRoute to a delegate:

~~~java
@Bean
public Classifier<Order, ItemWriter<? super Order>> orderWriterClassifier(
        Classifier<Order, OrderRoute> routeClassifier,
        ItemWriter<Order> highWriter,
        ItemWriter<Order> internationalWriter,
        ItemWriter<Order> domesticWriter,
        ItemWriter<Order> reviewWriter) {

    return order -> switch (routeClassifier.classify(order)) {
        case HIGH_VALUE -> highWriter;
        case INTERNATIONAL -> internationalWriter;
        case DOMESTIC -> domesticWriter;
        case REVIEW -> reviewWriter;
    };
}
~~~

This separation produces two test suites:

- Test OrderRouteClassifier to verify business conditions.
- Test route-to-delegate mapping to verify each route selects the right bean.

When adding a new route, the compiler can help catch switch expressions missing the new enum if there is no default. Mapping tests must also add a case for that route.

If the classifier and mapping are written in one combined lambda, you can still test it directly, yet it is harder to tell whether a bug lies in conditions or delegate wiring. Separate classes when classification rules have many branches or are reused in multiple places.

## 14. Testing the Default Branch When an Enum Expands

When adding a new enum value, two choices exist:

**Exhaustive switch:** no default; the compiler requires handling every enum constant on recompilation.

**Default branch:** all unhandled values enter a fallback branch.

Example:

~~~java
return switch (route) {
    case HIGH_VALUE -> highWriter;
    case INTERNATIONAL -> internationalWriter;
    case DOMESTIC -> domesticWriter;
    case REVIEW -> reviewWriter;
};
~~~

Exhaustive switches help catch newly unconfigured routes. For data coming from external systems, unrecognized values still need handling before converting into an enum.

If using default:

~~~java
return switch (route) {
    case HIGH_VALUE -> highWriter;
    case INTERNATIONAL -> internationalWriter;
    case DOMESTIC -> domesticWriter;
    default -> reviewWriter;
};
~~~

Tests must verify out-of-list values route accurately to reviewWriter. However, default can mask newly added enum constants that have not yet been evaluated by business rules. You can record metrics or log warnings when fallback is used.

## 15. Testing Purity and Determinism

A classifier is typically called many times and can be re-invoked when chunks retry. Results should depend on inputs and fixed configuration, not random state.

A hard-to-test classifier:

~~~java
public OrderRoute classify(Order order) {
    if (repository.isPriorityCustomer(order.customerCode())) {
        return random.nextBoolean()
                ? OrderRoute.HIGH_VALUE
                : OrderRoute.REVIEW;
    }
    return OrderRoute.DOMESTIC;
}
~~~

If business rules genuinely require a customer lookup, extract enrichment/lookup into a processor or inject a dependency with an explicit contract. If the classifier must use a dependency, tests must control the dependency and verify behavior when it times out, finds no data, or returns varying results.

Do not call external APIs inside classify() if results can be computed or loaded upfront. Retries can call the classifier again; side effects inside a classifier are easily repeated and hard to observe.

## 16. Testing Exception Classifiers and Retry Policies

Spring Batch can use classifiers inside exception-classification policies, such as selecting retry policies or rollback behavior by exception type. When an application configures these policies, test every important exception type.

Example matrix:

| Exception | Expected behavior |
| --- | --- |
| TransientDataAccessException | Bounded retry |
| DeadlockLoserDataAccessException | Bounded retry if operation is idempotent |
| InvalidOrderException | Skip/reject up to limit |
| IllegalStateException from config | Fail fast |
| AuthenticationException | Fail and require config fix |

Classifier/policy tests should verify:

- Specific exceptions classify into the intended group.
- Whether subclasses are treated like their superclass.
- Whether unknown exceptions enter the default policy.
- Retry limits are enforced.
- Non-retryable exceptions are not retried unintentionally.
- Data errors are not misclassified as transient errors.

Do not use a broad retry policy for every RuntimeException. Programming bugs or data errors do not disappear on retry.

Exception classifiers should be tested separately from item routing. An OrderRouteClassifier and a RetryPolicy classifier have different inputs/outputs even though both use the classification idea.

## 17. Testing the Full Step with Multiple Branches

Unit tests verify the classifier and delegates individually, yet do not prove Step wiring is right. Integration tests should run the Step with data containing at least one item per branch.

Example scenario:

~~~text
Input:
  Order 1 -> HIGH_VALUE
  Order 2 -> INTERNATIONAL
  Order 3 -> DOMESTIC
  Order 4 -> REVIEW

Expected:
  high_value_output       = [1]
  international_output   = [2]
  domestic_output         = [3]
  review_output           = [4]
~~~

After running the Step:

- Verify BatchStatus and ExitStatus.
- Count items in each output.
- Verify business IDs in each output.
- Confirm no item appears in two branches.
- Confirm no item was dropped.
- Confirm branches with no items did not create unintended side effects.

Do not merely assert total item count equals input count. For example, all four items could be written yet two swapped branches; the total count still looks right.

### Testing Error Branches

Create a delegate that intentionally throws an exception:

~~~text
Chunk has items of HIGH_VALUE and DOMESTIC
  |
  v
HIGH_VALUE writer writes successfully in transaction
  |
  v
DOMESTIC writer throws exception
  |
  v
Chunk rolls back per transaction manager
~~~

If both delegates write to the same database and share the same transaction, integration tests must verify the chunk's data rolled back. If delegates write files or call APIs, tests must reflect side effects that do not roll back automatically.

## 18. Testing Delegate ItemStreams

Some writers chosen by a classifier are ItemStreams, such as FlatFileItemWriter. Ensure the Step manages each delegate's lifecycle:

- open(ExecutionContext).
- update(ExecutionContext).
- close().

ClassifierCompositeItemWriter should not be assumed to automatically forward every delegate's lifecycle in every version. Check the interfaces and documentation of your Spring Batch version; if delegates require ItemStream, register streams with the Step appropriately.

Example:

~~~java
return new StepBuilder("routeOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(classifierCompositeWriter)
        .stream(highValueFileWriter)
        .stream(internationalFileWriter)
        .stream(domesticFileWriter)
        .stream(reviewFileWriter)
        .build();
~~~

If using a builder or delegate wrapper that supports stream propagation, verify exact behavior rather than double-registering. Test restart with file outputs to confirm each writer restores its checkpoint properly and does not overwrite another branch's file.

## 19. Testing Multiple Branches in a Chunk and Grouping

A single chunk can contain multiple items of the same branch or multiple different branches:

~~~text
Chunk:
  HIGH_VALUE
  DOMESTIC
  HIGH_VALUE
  REVIEW
  INTERNATIONAL
  DOMESTIC

Groups sent to delegates:
  highValueWriter      -> 2 items
  domesticWriter       -> 2 items
  reviewWriter         -> 1 item
  internationalWriter  -> 1 item
~~~

Tests should verify:

- Each item goes to only one delegate.
- Every classified item is sent to its matching delegate.
- Each delegate's chunk contains only items belonging to that branch.
- Item order within the same branch is preserved if required by contract.
- Do not assume invocation order across delegates if the implementation uses a map or grouping that does not guarantee order.

If downstream depends on ordering across branches, ClassifierCompositeItemWriter may not be the right abstraction. Use a custom coordinating writer with explicit ordering or split into appropriate Steps/flows.

## 20. Testing When a Branch Is Unconfigured

If the classifier returns a route yet the mapping lacks a delegate, that is a configuration bug. It can be handled by:

- Exhaustive switch on enum.
- Map validated completely when initializing the application context.
- Throwing an explicit exception when no delegate is found.
- Default reject writer if business rules allow.

Configuration validation example:

~~~java
EnumMap<OrderRoute, ItemWriter<Order>> writers =
        new EnumMap<>(OrderRoute.class);

writers.put(OrderRoute.HIGH_VALUE, highValueWriter);
writers.put(OrderRoute.INTERNATIONAL, internationalWriter);
writers.put(OrderRoute.DOMESTIC, domesticWriter);
writers.put(OrderRoute.REVIEW, reviewWriter);

for (OrderRoute route : OrderRoute.values()) {
    if (!writers.containsKey(route) || writers.get(route) == null) {
        throw new IllegalStateException(
                "Missing writer for route " + route);
    }
}
~~~

Tests for missing delegates should fail early at startup rather than waiting for a rare item to hit that branch in production.

## 21. Testing Retry and Side Effects per Branch

If a delegate fails, chunk retry may re-invoke the composite writer and reclassify items. On every retry, the same input should go to the same branch if the classifier is deterministic.

Tests must verify:

- The classifier does not change routes across calls with the same input.
- Delegates are re-invoked per policy.
- Database writers can roll back before retrying.
- API/message/file delegates have idempotency or dedicated recovery mechanisms.
- No item shifts to another branch due to mutated state.

Do not let the classifier depend on global variables or state that mutates per invocation. If routes change over time, resolve the route at one point and store it in the item/context so retries use the same decision.

For example, you can attach the route to a DTO after classification:

~~~java
public record RoutedOrder(
        Order order,
        OrderRoute route) {
}
~~~

Then processors/writers use the resolved route rather than recomputing from mutable data. Only do this when business rules require routes to stay fixed across chunks/restarts.

## 22. Testing the Classifier When New Data Arrives

Classifiers often need updates when adding regions, product types, customer tiers, or event types. Tests should expose unsupported values.

Example:

~~~java
@Test
void unknownRegionUsesReviewRoute() {
    Order order = new Order(
            70L, "NEW_REGION", new BigDecimal("200.00"));

    assertEquals(
            OrderRoute.REVIEW,
            classifier.classify(order));
}
~~~

If business rules want to fail instead of falling back:

~~~java
@Test
void rejectsUnsupportedRegion() {
    Order order = new Order(
            71L, "NEW_REGION", new BigDecimal("200.00"));

    assertThrows(
            UnsupportedRegionException.class,
            () -> strictClassifier.classify(order));
}
~~~

Choose between fallback and fail based on safe-handling capability. Fallback works well when a clear review queue exists; fail fits when every branch must be preconfigured and processing unlisted values could corrupt data.

## 23. Coverage: Do Not Measure Lines Alone

High line coverage does not mean every branch was tested. A classifier can have every line executed yet complex conditions remain untested on both sides.

Example:

~~~java
if (amount >= limit && approved) {
    return HIGH_VALUE;
}
return STANDARD;
~~~

At minimum, these tests are needed:

| amount >= limit | approved | Result |
| --- | --- | --- |
| true | true | HIGH_VALUE |
| false | true | STANDARD |
| true | false | STANDARD |

These cases prove each condition can alter the outcome. If nulls, unknowns, or short-circuits exist, add corresponding tests.

You can use JaCoCo or your project's coverage tool to inspect branch coverage. Still, coverage is only a supporting metric; assertions must verify the right business outcomes.

Do not write tests solely to hit 100% branch coverage by executing every line without asserting outputs, delegates, or side effects.

## 24. Common Pitfalls

### Only Testing Popular Branches

Rare branches like REVIEW or INTERNATIONAL may be misconfigured. Write tests for every classification outcome.

### Not Testing Values Near Thresholds

Bugs using greater-than instead of greater-than-or-equal often only appear at boundaries. Test below, at, and above thresholds.

### Not Testing Overlapping Conditions

An item can satisfy multiple conditions. Verify priority order.

### Only Testing the Classifier, Not Routing

The classifier can return the right enum while the enum-to-writer mapping is wrong. Test both mapping and composite behavior separately.

### Only Verifying a Delegate Was Called

Items could still be misrouted. Capture chunks and assert the business ID of each item.

### Asserting Uncommitted Delegate Call Orders

The composite may group items by writer and use collections without guaranteed iteration order. Assert contents and membership instead of non-contractual ordering.

### Returning Null When No Delegate Exists

Failures surface late as NullPointerException. Reject invalid routes or use an explicit fallback.

### Using Fallback to Hide New Routes

New enum values might get routed into an old branch unnoticed. Consider exhaustive switches or fallback alerts.

### Ignoring Null and Missing Fields

Classifiers may throw NullPointerException or pick the wrong branch. Define null policies explicitly and test each case.

### Classifier Having Side Effects

Retries can re-invoke the classifier and repeat API/database operations. Keep classifiers pure or make dependencies idempotent.

### Forgetting to Register Delegate ItemStreams

File writers may fail to save checkpoints or close properly. Verify lifecycles and restarts for every delegate.

### Writing Only Unit Tests Without Running the Step

Unit tests do not verify wiring, stream registration, transactions, retries, and skips. Add integration tests for framework behavior.

## 25. Classifier Test Matrix

A practical matrix can include:

| Group | Case | Expectation |
| --- | --- | --- |
| Each branch | Representative input per route | Correct route |
| Boundary | Below, at, and above threshold | Right operator and branch |
| Priority | Input matching multiple conditions | Priority route selected |
| Null | Null object or field | REVIEW or exception per contract |
| Unknown | Unsupported enum/region/type | Fallback or explicit exception |
| Mapping | Route to processor/writer | Right delegate |
| Grouping | Chunk with multiple routes | Items land in the right delegate's chunk |
| Empty branch | Chunk with no items for route | Corresponding delegate not called |
| Failure | Selected delegate throws exception | Exception propagates properly |
| Retry | Same item reprocessed | Stable route, idempotent side effects |
| Stream | Delegate implements ItemStream | Proper open/update/close and restart |
| Step | Run data containing all routes | Accurate outputs, no lost/duplicate items |

This matrix is a framework for test design. Not every classifier needs all cases; choose based on actual conditions and components.

## 26. Workflow for Testing Every Classifier Branch

When building a test suite, follow these steps:

1. List all routes and branch selection conditions.
2. Document priority order when conditions overlap.
3. Define null, unknown, and fallback policies.
4. Write unit tests calling the classifier directly for each route.
5. Check values just below, equal to, and above every threshold.
6. Use parameterized tests for structurally similar cases.
7. Test mappings from routes to processors or writers.
8. With composite writers, capture each delegate's chunks and assert item membership.
9. Confirm delegates with no items are not called.
10. Test exceptions from both the classifier and selected delegates.
11. Verify ItemStream lifecycles if delegates manage resources/checkpoints.
12. Run integration tests with the Step to verify wiring, transactions, retries, and outputs.
13. Use branch coverage to spot unexecuted branches, then add meaningful assertions.

A classifier should be deterministic, easy to test, and free of side effects. When rules change, update the route table and test cases together to prevent business logic and delegate mappings from drifting apart.

## Conclusion

Testing every classifier branch requires verifying both classification rules and the selected components. Start with a route matrix, check every branch, boundary values, overlapping conditions, nulls, and unknowns; then test ClassifierCompositeItemProcessor or ClassifierCompositeItemWriter to be sure items reach the right delegates. For writers, verify chunk contents and avoid relying on delegate invocation order unless the implementation guarantees it. Test exceptions, retries, idempotency, and ItemStream lifecycles; finally run integration tests to verify Step wiring and actual outputs. Branch coverage helps find unexecuted branches, while assertions on business outcomes prove the classifier works accurately.
