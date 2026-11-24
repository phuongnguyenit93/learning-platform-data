# Testing Each Composite Branch

In Spring Batch, a composite can route or pass items through multiple processors in different ways. `CompositeItemProcessor` chains processors in a fixed sequence, while `ClassifierCompositeItemProcessor` selects one delegate based on item characteristics. When multiple processing branches exist, checking only the final outcome of a Job is not enough: you must verify each input type routes to the right delegate, unselected branches are never called, and each branch's error behavior is handled properly.

Testing each branch helps catch bugs such as a classifier misclassifying items, an item falling into an unexpected default branch, a delegate receiving the wrong data type, a branch returning `null` with the wrong semantics, or exceptions being hidden. Combine unit tests for the classifier/delegates with integration tests for the Step to verify routing in a real Batch pipeline.

## 1. Distinguishing Chain Composites and Branch Composites

Two common composite styles behave differently:

**Chain processor** uses `CompositeItemProcessor`: each delegate receives the previous delegate's output and runs in configured order.

```text
Input
  |
  v
NormalizeProcessor
  |
  v
EnrichProcessor
  |
  v
ValidateProcessor
  |
  v
Output
```

**Branch processor** uses `ClassifierCompositeItemProcessor`: the classifier selects one delegate suited to the item, and that delegate processes the item.

```text
                 +--> CardProcessor --------+
                 |                          |
Input --> Classifier                         +--> Result
                 |                          |
                 +--> BankTransferProcessor -+
```

For chains, testing focuses on delegate order, intermediate input/output types, and stopping behavior on `null` or exceptions. For branches, verify every classification condition, that the right delegate is called, and that other delegates are not called for the same item.

A Job can combine both: the classifier picks a branch, and each branch uses its own chain. In that case, test routing and chains as two separate responsibilities, then verify integration at the Step level.

## 2. Identifying Branches to Test

Before writing tests, list all possible inputs and their corresponding branches. For example, a payment processing Job has three types:

| Input Type | Selected Delegate | Expected Outcome |
|---|---|---|
| `CARD` | `cardPaymentProcessor` | Process card payment. |
| `BANK_TRANSFER` | `bankTransferProcessor` | Process bank transfer. |
| `WALLET` | `walletProcessor` | Process digital wallet payment. |
| Unsupported type | Reject/fallback branch or explicit error | Do not silently pick a wrong processor. |

Each branch should have at least one test verifying successful routing. For branches with complex conditions, add boundary and invalid-case tests. If the classifier has a default branch, explicitly test which inputs land in the default branch.

Do not merely count tests. A test might run the Job successfully while only exercising the `CARD` branch; that does not prove `BANK_TRANSFER` or `WALLET` is wired properly.

## 3. Domain and Classifier Example

Suppose the reader returns `Payment` and the processor must produce `PaymentResult`:

```java
public enum PaymentMethod {
    CARD,
    BANK_TRANSFER,
    WALLET
}

public record Payment(
        String paymentId,
        PaymentMethod method,
        BigDecimal amount) {
}

public record PaymentResult(
        String paymentId,
        String status,
        String providerReference) {
}
```

Delegates share the same input/output type in this example so the classifier can route a `Payment` to the appropriate processor:

```java
ItemProcessor<Payment, PaymentResult> cardPaymentProcessor = payment ->
        cardGateway.charge(payment);

ItemProcessor<Payment, PaymentResult> bankTransferProcessor = payment ->
        bankGateway.submit(payment);

ItemProcessor<Payment, PaymentResult> walletProcessor = payment ->
        walletGateway.pay(payment);
```

In a real application, each delegate can call a distinct service, check distinct fields, or build specialized outputs. If branches have different input models, you can use a shared sealed hierarchy/interface with controlled casts in delegates, or build adapters to keep type contracts safe.

The classifier determines the branch based on `PaymentMethod`:

```java
Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>>
        paymentClassifier = payment -> switch (payment.method()) {
            case CARD -> cardPaymentProcessor;
            case BANK_TRANSFER -> bankTransferProcessor;
            case WALLET -> walletProcessor;
        };
```

With an exhaustive enum switch expression, the compiler can require handling every enum value. If the classifier might receive `null`, or if the discriminator comes from untrusted data, validate before classifying and define behavior when no branch matches.

## 4. Configuring ClassifierCompositeItemProcessor

`ClassifierCompositeItemProcessor<I, O>` is an `ItemProcessor<I, O>`. It uses a `Classifier` to pick a delegate for each input.

Java configuration example:

```java
@Bean
ItemProcessor<Payment, PaymentResult> paymentProcessor(
        ItemProcessor<Payment, PaymentResult> cardPaymentProcessor,
        ItemProcessor<Payment, PaymentResult> bankTransferProcessor,
        ItemProcessor<Payment, PaymentResult> walletProcessor) {

    ClassifierCompositeItemProcessor<Payment, PaymentResult> composite =
            new ClassifierCompositeItemProcessor<>();

    composite.setClassifier(payment -> switch (payment.method()) {
        case CARD -> cardPaymentProcessor;
        case BANK_TRANSFER -> bankTransferProcessor;
        case WALLET -> walletProcessor;
    });

    return composite;
}
```

The class lives in package `org.springframework.batch.item.support`; `Classifier` belongs to package `org.springframework.classify`. The composite picks a delegate per item. It does not invoke all processors sequentially like `CompositeItemProcessor`.

When using multiple beans of the same type, use `@Qualifier` so Spring injects the right delegate. Branch configuration should read like a routing table; avoid classifiers relying on implicit bean discovery order.

## 5. Testing Routing with Mock Delegates

A basic unit test verifies a `CARD` item is forwarded to the right processor:

```java
@Test
void cardPaymentIsRoutedOnlyToCardProcessor() throws Exception {
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> cardProcessor =
            mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> bankProcessor =
            mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> walletProcessor =
            mock(ItemProcessor.class);

    Payment payment = new Payment(
            "P-1001", PaymentMethod.CARD, new BigDecimal("250.00"));
    PaymentResult expected = new PaymentResult(
            "P-1001", "APPROVED", "CARD-REF-01");

    when(cardProcessor.process(payment)).thenReturn(expected);

    ClassifierCompositeItemProcessor<Payment, PaymentResult> composite =
            new ClassifierCompositeItemProcessor<>();
    composite.setClassifier(item -> switch (item.method()) {
        case CARD -> cardProcessor;
        case BANK_TRANSFER -> bankProcessor;
        case WALLET -> walletProcessor;
    });

    assertThat(composite.process(payment)).isEqualTo(expected);

    verify(cardProcessor).process(payment);
    verifyNoInteractions(bankProcessor, walletProcessor);
}
```

The test verifies three things: the result comes from the card branch, `cardProcessor` receives the exact item, and the other two branches are never called. `verifyNoInteractions` is especially helpful for catching classifiers that accidentally invoke multiple delegates or logic placed mistakenly outside a branch.

## 6. Writing Separate Tests for Every Branch

Do not test only the first branch and assume the remaining branches behave identically. Each branch may have its own services, mappings, validations, and exceptions.

A test for bank transfers:

```java
@Test
void bankTransferIsRoutedToBankProcessor() throws Exception {
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> cardProcessor =
            mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> bankProcessor =
            mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> walletProcessor =
            mock(ItemProcessor.class);

    Payment payment = new Payment(
            "P-2001", PaymentMethod.BANK_TRANSFER,
            new BigDecimal("900.00"));
    PaymentResult expected = new PaymentResult(
            "P-2001", "SUBMITTED", "BANK-REF-02");

    when(bankProcessor.process(payment)).thenReturn(expected);

    ClassifierCompositeItemProcessor<Payment, PaymentResult> composite =
            createComposite(cardProcessor, bankProcessor, walletProcessor);

    assertThat(composite.process(payment)).isEqualTo(expected);

    verify(bankProcessor).process(payment);
    verifyNoInteractions(cardProcessor, walletProcessor);
}
```

To avoid repeating configuration across tests, you can extract a `createComposite(...)` helper in the test class. The helper must construct the composite with the same classifier as production; do not write a simpler classifier in tests, as doing so tests different logic from the real configuration.

For the `WALLET` branch, write a similar test verifying `walletProcessor` is the only delegate invoked. Each branch also needs tests for its delegate's internal logic, such as provider status code mapping or limit validation.

## 7. Extracting the Classifier as a Component for Direct Testing

When classification rules are complex, extract the classifier into a dedicated class instead of embedding all logic in a lambda inside bean configuration.

```java
public class PaymentProcessorClassifier
        implements Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> {

    private final ItemProcessor<Payment, PaymentResult> cardProcessor;
    private final ItemProcessor<Payment, PaymentResult> bankProcessor;
    private final ItemProcessor<Payment, PaymentResult> walletProcessor;

    public PaymentProcessorClassifier(
            ItemProcessor<Payment, PaymentResult> cardProcessor,
            ItemProcessor<Payment, PaymentResult> bankProcessor,
            ItemProcessor<Payment, PaymentResult> walletProcessor) {
        this.cardProcessor = cardProcessor;
        this.bankProcessor = bankProcessor;
        this.walletProcessor = walletProcessor;
    }

    @Override
    public ItemProcessor<?, ? extends PaymentResult> classify(Payment payment) {
        if (payment == null || payment.method() == null) {
            throw new IllegalArgumentException("Payment method is required");
        }

        return switch (payment.method()) {
            case CARD -> cardProcessor;
            case BANK_TRANSFER -> bankProcessor;
            case WALLET -> walletProcessor;
        };
    }
}
```

A standalone classifier can be unit tested without instantiating `ClassifierCompositeItemProcessor`. Tests can call `classify(payment)` and assert the returned delegate object. Then a composite test verifies Spring Batch invokes the selected delegate properly.

Extracting the classifier is beneficial when routing depends on multiple attributes, such as payment method, currency, tenant, or feature flags. If there is only a short, stable switch, a lambda can be clear enough.

## 8. Decision Table Testing

With multiple branches, using parameterized tests or a case table makes coverage easy to see:

| Input Method | Expected Delegate | Expected Behavior |
|---|---|---|
| `CARD` | `cardProcessor` | Calls card processing. |
| `BANK_TRANSFER` | `bankProcessor` | Calls bank transfer processing. |
| `WALLET` | `walletProcessor` | Calls wallet processing. |
| `null` | No delegate | Rejects input with an explicit error. |

Example parameterized test for a standalone classifier:

```java
@ParameterizedTest
@EnumSource(PaymentMethod.class)
void classifierReturnsDelegateForEverySupportedMethod(
        PaymentMethod method) {

    Payment payment = new Payment(
            "P-TEST", method, new BigDecimal("10.00"));

    ItemProcessor<?, ? extends PaymentResult> selected =
            classifier.classify(payment);

    assertThat(selected).isNotNull();
    assertThat(selected).isSameAs(expectedDelegateFor(method));
}
```

`expectedDelegateFor` is a test helper returning the mock matching the method. If each branch involves more conditions than a simple enum, `@MethodSource` can supply pairs of inputs and expected delegates.

Parameterized tests verify the classifier across all declared values, yet you still need composite tests to verify the delegate is actually invoked and its result returned.

## 9. Testing Default Branches and Unsupported Inputs

The classifier must have an explicit policy when receiving an unsupported item type. Three common options exist:

- Throw an exception so the Step fails or applies a skip policy.
- Select a fallback processor dedicated to unsupported inputs.
- Return a structured rejection result if business rules require continuing.

Do not silently send unrecognized inputs to an arbitrary valid branch. That can create side effects in the wrong system.

Example classifier with an explicit fallback:

```java
return payment -> switch (payment.method()) {
    case CARD -> cardProcessor;
    case BANK_TRANSFER -> bankProcessor;
    case WALLET -> walletProcessor;
    default -> unsupportedPaymentProcessor;
};
```

If an enum may be extended in a later version, the default branch needs a test verifying behavior. When using a switch expression without default, adding an enum value forces the compiler to require updating the classifier; this is often a good choice to force developers to handle new types.

Test null inputs separately because failures may happen before the switch executes. If `Payment` can be null from a reader, decide whether to reject in a validator/processor before the classifier or check inside the classifier.

## 10. Testing That Unselected Delegates Produce No Side Effects

Asserting only the final result does not prove only one branch ran. A buggy classifier could invoke a secondary branch by mistake and still return the expected outcome.

Verify:

- The right delegate is called the exact number of times.
- Unselected delegates receive no calls.
- No service belonging to another branch is called.
- No stray output is produced from unrelated branches.

Example:

```java
verify(cardProcessor, times(1)).process(cardPayment);
verifyNoInteractions(bankProcessor, walletProcessor);
verifyNoInteractions(bankGateway, walletGateway);
```

If delegates share a service, verify the arguments passed to the service or use per-branch collaborators. Do not use `verifyNoInteractions` on a collaborator that the selected branch also legitimately invokes.

## 11. Testing Null Results from a Branch

A delegate can return `null` per the `ItemProcessor` contract to filter an item. With a classifier composite, the null result is returned to the Step and the item does not reach the writer.

Example test:

```java
@Test
void nullFromSelectedBranchFiltersItem() throws Exception {
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> cardProcessor =
            mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> bankProcessor =
            mock(ItemProcessor.class);

    Payment payment = new Payment(
            "P-3001", PaymentMethod.CARD, new BigDecimal("0.00"));
    when(cardProcessor.process(payment)).thenReturn(null);

    ClassifierCompositeItemProcessor<Payment, PaymentResult> composite =
            new ClassifierCompositeItemProcessor<>();
    composite.setClassifier(item -> item.method() == PaymentMethod.CARD
            ? cardProcessor : bankProcessor);

    assertThat(composite.process(payment)).isNull();
    verify(cardProcessor).process(payment);
    verifyNoInteractions(bankProcessor);
}
```

Do not confuse a null result with the classifier failing to find a delegate. If the classifier returns null, the composite has no processor to call and may throw `NullPointerException`. Have the classifier return a fallback delegate or throw a meaningful exception instead of returning null.

## 12. Testing Exceptions in Each Branch

Each delegate may throw distinct exception types. Unit tests must verify exceptions from the selected branch propagate outward and other branches do not run.

```java
@Test
void exceptionFromSelectedBranchIsPropagated() throws Exception {
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> cardProcessor =
            mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> bankProcessor =
            mock(ItemProcessor.class);

    Payment payment = new Payment(
            "P-4001", PaymentMethod.BANK_TRANSFER,
            new BigDecimal("500.00"));
    RuntimeException failure = new IllegalStateException("bank unavailable");
    when(bankProcessor.process(payment)).thenThrow(failure);

    ClassifierCompositeItemProcessor<Payment, PaymentResult> composite =
            new ClassifierCompositeItemProcessor<>();
    composite.setClassifier(item -> item.method() == PaymentMethod.CARD
            ? cardProcessor : bankProcessor);

    assertThatThrownBy(() -> composite.process(payment))
            .isSameAs(failure);

    verify(bankProcessor).process(payment);
    verifyNoInteractions(cardProcessor);
}
```

At the unit test level, verify the composite does not swallow exceptions. At the Step level, verify those exceptions are classified properly into retry, skip, or failure per the Job's policy.

## 13. Testing Logic Inside Each Delegate

Correct routing does not prove delegates implement business rules accurately. Each branch needs its own unit tests for its internal logic.

Example card branch:

- Positive amount and supported currency: calls gateway with accurate data.
- Zero or negative amount: returns validation failure or throws business exception.
- Gateway declines transaction: maps status accurately.
- Gateway timeout: throws transient exception so policy can retry.
- Response missing reference: handles per contract without fabricating success.

Example bank transfer branch:

- Valid target account: constructs transfer request accurately.
- Missing account: data error or business rejection.
- Bank unavailable: transient exception.
- Re-sent request: keeps idempotency key stable.

Example wallet branch:

- Valid wallet ID: calls the right service.
- Locked wallet: returns matching business result.
- Insufficient limit: does not send payment request.
- Timeout after service may have processed: looks up status or retries with the same idempotency key.

These tests should check outcomes and interactions with that branch's own services, without needing to assemble the entire `ClassifierCompositeItemProcessor` if the goal is solely delegate logic.

## 14. Testing Branch-Specific Dependencies

If each branch uses a different service, inject corresponding mocks to verify only the right service is invoked:

```java
@Test
void cardBranchCallsCardGatewayOnly() throws Exception {
    CardGateway cardGateway = mock(CardGateway.class);
    BankGateway bankGateway = mock(BankGateway.class);

    ItemProcessor<Payment, PaymentResult> cardProcessor =
            new CardPaymentProcessor(cardGateway);
    ItemProcessor<Payment, PaymentResult> bankProcessor =
            new BankTransferProcessor(bankGateway);

    Payment payment = new Payment(
            "P-5001", PaymentMethod.CARD, new BigDecimal("100.00"));

    // Build classifier composite with the two processors above.
    // Call process(payment), then verify the corresponding gateway.

    verify(cardGateway).charge(any(CardChargeRequest.class));
    verifyNoInteractions(bankGateway);
}
```

Composite assembly is omitted in the snippet to focus on dependency assertions; full tests should use the same classifier as production. For shared services, inspect the request type or operation code to ensure the branch does not send the wrong command type.

## 15. Testing a Chain Inside a Branch

A branch may contain its own `CompositeItemProcessor` chain. For instance, card payments need card data normalization, fraud checks, and request mapping. Bank transfers have a different chain.

```text
Payment
   |
   v
Classifier
   |
   +-- CARD --> NormalizeCard -> FraudCheck -> CardRequest
   |
   +-- BANK --> ValidateAccount -> BankRequest
```

Test in two layers:

1. Test that the classifier picks the right chain for each payment type.
2. Test each chain to ensure internal delegates execute in the right order and pass the right outputs.

Do not write one giant test verifying every field of every delegate, routing, retry, and database at once. When a test fails, you need to tell whether the bug lies in the classifier or in a processor inside a branch.

## 16. Testing ClassifierCompositeItemWriter

When a composite is used for write routing, Spring Batch provides `ClassifierCompositeItemWriter<T>`. Testing is conceptually similar: create items of each type, verify the classifier selects the right writer, and ensure other writers receive no items.

Example routing by event type:

```text
Event
  |
  v
Writer classifier
  |
  +--> AuditWriter
  |
  +--> ArchiveWriter
  |
  +--> RejectedWriter
```

For writers, additionally verify:

- Items are forwarded to the right destination.
- Behavior when a chunk contains items from multiple branches.
- Writer invocation order/grouping per the contract of the active implementation.
- Exceptions from the chosen writer propagate to the Step.
- Retries do not create duplicate side effects in non-transactional destinations.
- Stateful writers are opened, updated, and closed under the proper lifecycle when wrapped or configured as streams.

Do not assume processor composite tests substitute for writer composite tests. The two components have different interfaces and semantics; tests must exercise the actual API in use.

## 17. Integration Testing with Job/Step

Unit testing the classifier verifies routing decisions, yet does not prove Spring configuration injects the right beans or the Step writes expected outputs. Use `@SpringBatchTest` and `JobLauncherTestUtils` to test the Job/Step inside the application context.

An integration test per branch can:

1. Prepare input containing a record belonging to that branch.
2. Launch the Job with test-specific JobParameters.
3. Assert `JobExecution` finishes `COMPLETED` when error-free.
4. Assert output matches the chosen branch.
5. Assert no output exists from other branches.
6. Assert Step counters and audit data match expectations.

If the Job uses real writers writing to a database, inspect target tables. If outputs go to an API or message broker, use a test server/broker or test adapter to observe requests. Avoid calling production systems in unit/integration tests.

### Verifying All Branches in One Job Run

A test can feed multiple input types and verify every branch executed. This is useful for verifying the overall flow, though separate unit tests per branch should still be kept so failures are easier to pinpoint.

Input example:

```text
P-01,CARD,100.00
P-02,BANK_TRANSFER,200.00
P-03,WALLET,50.00
```

After the Job runs, verify all three results carry the right provider reference/status and no record was misrouted. If processors filter items, compute expected counts per the filter policy.

## 18. Testing Filter Count and Writer Output

If a delegate returns `null`, the item is filtered and not sent to the writer. Integration tests should distinguish:

- Items read.
- Items filtered by processors.
- Items written successfully.
- Items skipped due to exceptions.

`StepExecution` counters such as read count, filter count, write count, process skip count, and write skip count confirm outcomes at the Step level. Do not assert only total line counts in a file if a branch can filter or skip.

Example branch filtering payments below a threshold:

```java
if (payment.amount().compareTo(minimumAmount) < 0) {
    return null;
}
```

Tests must verify below-threshold payments never reach the writer, `filterCount` increases appropriately, and other branches still process normally.

## 19. Retry and Skip per Branch

A Step can apply a shared retry/skip policy to exceptions thrown by any delegate. If branches have distinct error types, use distinct exception types or an explicitly classifying policy.

Example:

```java
return new StepBuilder("processPaymentsStep", jobRepository)
        .<Payment, PaymentResult>chunk(100, transactionManager)
        .reader(paymentReader)
        .processor(paymentProcessor)
        .writer(paymentWriter)
        .faultTolerant()
        .retry(PaymentProviderUnavailableException.class)
        .retryLimit(3)
        .skip(InvalidPaymentException.class)
        .skipLimit(25)
        .build();
```

Tests should cover:

- Transient errors in the card branch are retried and later succeed.
- Transient errors in the bank transfer branch are also handled per policy.
- Data errors in a branch are skipped if permitted.
- Exceptions outside policy fail the Step.
- Retry exhaustion yields the right final status and failure metadata.
- Unselected branches are not called on any attempt.

If per-branch policies differ, create distinct exception subclasses or use custom exception-based policies. Do not classify by message text when stable types can be used.

## 20. Side Effects and Idempotency Across Branches

Delegates can be re-invoked due to retries, rollbacks, or restarts. If a branch calls a payment API, sends messages, or writes files, tests must prove side effects are safe when repeated.

For example, idempotency keys should derive from the business operation ID:

```java
String key = "payment-" + payment.paymentId();
cardGateway.charge(request, key);
```

Do not generate a new random key on each processor invocation. If an API already processed a request before the response timed out, retries must reuse the same key or check operation status before resending.

For multi-system flows, consider a transactional outbox to record sending intent within the chunk transaction and relay per branch. Test relay replays and consumer deduplication separately from classifier tests.

## 21. Testing Concurrency and Thread Safety

A classifier composite does not run branches in parallel automatically. However, if a Step uses multi-threaded processing or multiple Jobs run concurrently, the same composite bean and singleton delegates can be invoked from multiple threads.

Concurrency tests must verify:

- The classifier holds no mutable state from previous items.
- Delegates do not store `currentPayment` in shared fields.
- Dependencies such as clients/caches have proper thread safety.
- Results never mix across two different payments.
- Idempotency keys and correlation IDs always stay tied to the right item.
- Outputs from each branch do not write to a shared resource unintentionally.

If a delegate is not thread-safe, use an appropriate scope, deliberate synchronization, or adjust concurrency settings. Do not assume that because the classifier picks one delegate per item, that delegate is called by only one thread at a time.

## 22. Observing Branches in Tests and Operations

At the Step level, `ItemProcessListener` sees the composite processor as a single processor. It does not emit separate callbacks for each internal delegate.

When per-branch observability is needed, you can:

- Record metrics inside the classifier or delegates.
- Wrap each delegate with a decorator recording duration and outcomes.
- Write structured logs with branch name and business correlation ID.
- Maintain separate counters for items passing through each branch.
- Use tracing spans for service calls within each branch.

In tests, spies/mocks can verify branch counts. In production, metric tags should have low cardinality such as `branch=card` or `branch=bank`; do not use payment IDs as tags.

Do not log full payment payloads or sensitive identifiers just to verify routing.

## 23. Common Mistakes When Testing Composite Branches

### Testing Only One Branch

Remaining branches may remain unwired or misclassified by the classifier. Write tests for every discriminator value and every fallback.

### Checking Only the Final Output

Output can match even when the wrong delegate was also called. Verify the selected delegate and assert other delegates had no interactions.

### Using a Different Classifier in Tests Than in Production

Tests may pass while the real bean configuration is broken. Reuse the production classifier or build the composite with the same configuration.

### Not Testing Unsupported Inputs

New types can land in an unsafe default branch. Define an explicit fallback or exception and test it.

### Skipping Null and Exception Tests

Branches can filter items or throw errors. Verify `null` behaves as a filter while exceptions propagate to the Step.

### Testing Only the Classifier Without Testing Delegates

Correct routing does not guarantee business logic inside a branch is right. Unit test each delegate with valid, boundary, and invalid inputs.

### Testing Only Delegates Without Testing Routing

A well-tested delegate can still never be called if the classifier is wrong. Test the composite to confirm the path from input to the right delegate.

### Writing One Oversized Integration Test

When it fails, isolating which branch broke is hard. Separate branch tests, classifier tests, and end-to-end Job tests.

### Assuming the Composite Runs Branches in Parallel

The classifier selects one delegate per item; it does not parallelize automatically. If concurrency is needed, test Step/partition settings separately.

### Ignoring Side Effects on Retry

A branch may invoke an API multiple times. Test idempotency, timeouts, and unknown outcomes.

## 24. Recommended Test Matrix

A test suite for composite routing can be organized as follows:

| Test Layer | Case | What to Verify |
|---|---|---|
| Classifier unit | Each valid discriminator | Returns the exact delegate. |
| Classifier unit | Null/unknown discriminator | Clear fallback or exception. |
| Branch unit | Valid input per branch | Expected output and dependency calls. |
| Branch unit | Boundary/invalid input | Proper validation or business rejection. |
| Composite unit | Each item type | Only the matching delegate is invoked. |
| Composite unit | Delegate returns `null` | Null result, no other delegates called. |
| Composite unit | Delegate throws exception | Exception propagates, other branches do not run. |
| Step integration | One input per branch | Expected writers/outputs and counters. |
| Step integration | Retry/skip per exception | Accurate BatchStatus, ExitStatus, and counters. |
| Restart integration | Restart after committed chunk | Routing and side effects do not repeat erroneously. |
| Concurrency | Multiple items/Jobs concurrently | No state leakage across branches. |

Not every project needs tests for every row if a branch lacks that behavior. Prioritize real business paths and risks that could corrupt data.

## 25. Workflow for Testing Each Composite Branch

When implementing a composite with routing, follow this sequence:

1. List all discriminators and their matching branches.
2. Define defaults/fallbacks and behavior for null or unsupported inputs.
3. Unit test the classifier to verify every input type selects the right delegate.
4. Unit test each delegate independently with valid, boundary, and error inputs.
5. Unit test the composite to verify only the chosen branch is invoked.
6. Verify `null` filtering and exception propagation.
7. If a branch contains a chain, test internal delegate order separately.
8. Integration test the Step/Job to confirm bean wiring, outputs, and counters.
9. Test retry/skip/failure for exceptions from relevant branches.
10. Test idempotency if branches produce non-transactional side effects.
11. Test concurrency if the Step or Job runs across multiple threads/partitions.
12. Use per-branch metrics/logs to aid diagnostics without exposing sensitive payloads.

| Question | Evidence in Tests |
|---|---|
| Did type A input enter the right branch? | Verify delegate A was invoked with the matching item. |
| Was branch B called by mistake? | `verifyNoInteractions` or verify zero calls. |
| How are unsupported inputs handled? | Assert expected fallback result or exception. |
| Does the branch filter items? | Assert processor returns null and writer receives no item. |
| What happens when a branch fails? | Assert exception propagation and proper Step retry/skip/fail. |
| Do all branches work in a real Job? | Integration test with representative inputs per branch and verify outputs. |

## Conclusion

Testing each composite branch requires verifying both the classification decision and the selected delegate's logic. For `ClassifierCompositeItemProcessor`, write tests for every discriminator, verify the right delegate is invoked while other branches receive no items, test each delegate separately for valid, boundary, and error inputs, and verify behavior for unsupported inputs, `null`, and exceptions. Unit tests for the classifier/composite pinpoint routing bugs, while Step/Job integration tests verify bean wiring, writer outputs, counters, and retry/skip policies. If branches trigger side effects or run concurrently, add idempotency and thread-safety tests. Clearly distinguish branch routing from chain-based `CompositeItemProcessor` so tests verify the exact semantics of the component in use.
