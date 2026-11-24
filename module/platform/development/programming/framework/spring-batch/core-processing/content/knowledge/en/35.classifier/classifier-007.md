# Item Does Not Match the Classifier

In Spring Batch, a Classifier is used to select a matching delegate for each item. For example, a CARD transaction is sent to CardPaymentProcessor, and a TRANSFER transaction is sent to BankTransferProcessor. However, input data can contain a new item type, a null value, a blank string, a misspelled code, or a subtype the classifier does not yet recognize.

When the classifier cannot find a matching branch, an explicit policy is required. With ClassifierCompositeItemProcessor, the classifier must return an ItemProcessor for the composite to invoke to process the item. If the classifier returns null, the composite has no delegate to invoke and usually throws a NullPointerException. ClassifierCompositeItemProcessor does not automatically treat null as filter, skip, or fallback.

Therefore, when no matching route exists, the application must proactively choose one of these behaviors: fail fast to stop the Step, forward the item to a fallback processor, produce a rejected/quarantine result, or pick a delegate intentionally to filter the item. These behaviors differ in business meaning, skip counts, auditing, and restartability.

## 1. Classifier Selects a Delegate per Item

A Classifier receives an input object and returns a classification result. When used with ClassifierCompositeItemProcessor, the classification result is a delegate ItemProcessor:

~~~text
ItemReader
    |
    v
Input item
    |
    v
ClassifierCompositeItemProcessor
    |
    v
Classifier.classify(item)
    |
    +---- CARD -------> CardPaymentProcessor
    |
    +---- TRANSFER ---> TransferPaymentProcessor
    |
    +---- CASH -------> CashPaymentProcessor
    |
    +---- No match ---> No-match policy
~~~

Example item:

~~~java
public record Payment(
        String paymentId,
        String type,
        BigDecimal amount) {
}
~~~

Simple classifier:

~~~java
return payment -> switch (payment.type()) {
    case "CARD" -> cardProcessor;
    case "TRANSFER" -> transferProcessor;
    case "CASH" -> cashProcessor;
    default -> null;
};
~~~

The last snippet returns null for every unrecognized type. This is not a safe way to handle no-match for ClassifierCompositeItemProcessor. The composite requires a valid delegate; if it receives null, invoking process on the delegate will fail. Replace default with an explicit policy.

## 2. Common No-Match Cases

An item can fail to match the classifier for several reasons:

| Case | Example | Possible meaning |
|---|---|---|
| New value | type is WALLET yet the application does not support it yet | Producer extended the schema |
| Typo | TRANSFRE instead of TRANSFER | Invalid source data |
| Blank string | type is whitespace | Missing required data |
| Null | type missing from payload | Input mapping or contract missing field |
| Different casing | card instead of CARD | Inconsistent normalization rules |
| Whitespace | " CARD " | Input not trimmed |
| New class/subtype | A new Payment implementation | Model expanded yet registry not updated |
| Missing configured route | New enum exists yet processor not registered | Deployment configuration error |

Not every case should go to the same fallback branch. A new type may represent a producer change requiring a consumer rollout; a misspelled string may be bad data; a missing route may be a configuration bug requiring the Job to stop.

Distinguish per-item data errors from application configuration errors. If a required route must exist yet a deployment forgot to register the delegate, skipping massive numbers of items hides the configuration bug.

## 3. Distinguishing No-Match, Filter, and Skip

These three scenarios have distinct semantics:

- **No-match:** the classifier cannot find a delegate. This is an unresolved routing decision.
- **Filter:** a delegate is selected and returns null. The item is intentionally dropped, does not reach the writer, and counts toward filter count.
- **Skip:** a component throws an exception configured as skippable. Spring Batch records a skip at the corresponding stage and can invoke SkipListener.

| Behavior | Decision point | Outcome |
|---|---|---|
| No-match returns null | Classifier | No delegate; composite may throw NullPointerException |
| Fail fast | Classifier throws exception | Step fails, unless exception is handled by policy |
| Fallback | Classifier returns fallback processor | Item is processed by fallback logic |
| Filter | Delegate returns null | Item does not reach writer |
| Skip | Reader/processor/writer throws skippable exception | Item is skipped per fault-tolerance policy |
| Quarantine | Fallback builds rejected output or dedicated writer stores error | Record exists for audit or replay |

Do not use null from the classifier to signify filtering. To filter, the classifier must still select a valid processor; that processor itself returns null.

## 4. Policy 1: Fail Fast When No Route Exists

If every item must belong to a supported type, the simplest approach is throwing a meaningful exception:

~~~java
public class UnsupportedPaymentTypeException
        extends RuntimeException {

    public UnsupportedPaymentTypeException(String type) {
        super("Unsupported payment type: " + type);
    }
}
~~~

Classifier:

~~~java
Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> paymentClassifier =
        payment -> {
            String type = normalize(payment.type());

            return switch (type) {
                case "CARD" -> cardProcessor;
                case "TRANSFER" -> transferProcessor;
                case "CASH" -> cashProcessor;
                default -> throw new UnsupportedPaymentTypeException(type);
            };
        };
~~~

With this approach, the Job detects items outside the current contract early. If the exception is not configured as skippable, the Step fails. This is the right choice when a new type could change fee calculations, statuses, or how data is persisted.

Do not use generic IllegalArgumentException for all errors if you need to distinguish no-match from other bugs. A dedicated exception makes skip/retry configuration and log analysis much more accurate.

## 5. Policy 2: Use a Fallback Processor

If the Job must continue processing items with unsupported types, the classifier can return a fallback processor. A fallback is a real delegate, configured and managed just like other processors.

Example fallback producing a rejected result:

~~~java
@Component
public class UnsupportedPaymentProcessor
        implements ItemProcessor<Payment, PaymentResult> {

    @Override
    public PaymentResult process(Payment payment) {
        return PaymentResult.rejected(
                payment.paymentId(),
                payment.type(),
                "UNSUPPORTED_PAYMENT_TYPE");
    }
}
~~~

Classifier:

~~~java
@Bean
Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> paymentClassifier(
        CardPaymentProcessor cardProcessor,
        TransferPaymentProcessor transferProcessor,
        CashPaymentProcessor cashProcessor,
        UnsupportedPaymentProcessor fallbackProcessor) {

    Map<String, ItemProcessor<Payment, PaymentResult>> routes = Map.of(
            "CARD", cardProcessor,
            "TRANSFER", transferProcessor,
            "CASH", cashProcessor);

    return payment -> {
        String type = normalize(payment.type());
        return routes.getOrDefault(type, fallbackProcessor);
    };
}
~~~

When the type is absent from the map, the fallback is selected and returns a valid PaymentResult. The writer can save rejected results to an audit table or route to another output based on result status.

A fallback should never silently turn an unknown type into a valid transaction. Retain payment ID, raw type, rejection reason, and batch ID if investigation/replay is needed. If the payload contains sensitive data, store only required fields or store the raw payload in a restricted-access area.

## 6. Policy 3: Route to Quarantine

A fallback processor can convert an unsupported item into an output type that explicitly conveys quarantine status:

~~~java
public record PaymentResult(
        String paymentId,
        String status,
        String reason,
        BigDecimal amount) {

    public static PaymentResult accepted(
            String paymentId,
            BigDecimal amount) {
        return new PaymentResult(
                paymentId, "ACCEPTED", null, amount);
    }

    public static PaymentResult rejected(
            String paymentId,
            String reason) {
        return new PaymentResult(
                paymentId, "REJECTED", reason, null);
    }
}
~~~

Fallback:

~~~java
public class QuarantinePaymentProcessor
        implements ItemProcessor<Payment, PaymentResult> {

    @Override
    public PaymentResult process(Payment payment) {
        return PaymentResult.rejected(
                payment.paymentId(),
                "NO_CLASSIFIER_MATCH:" + payment.type());
    }
}
~~~

One writer can write both accepted and rejected items with a status discriminator. If quarantine needs to be saved to a separate table or resource, use a dedicated routing writer or split into a subsequent Step after normalizing output.

Quarantine differs from skip: the item still produces a result that can be inspected and reconciled. This fits when the system must continue the batch without losing unsupported records.

If the writer stores quarantine data in the same database and chunk transaction, rejected results can commit with the chunk. If writing to an external system outside the database, idempotency keys and retry handling are needed.

## 7. Policy 4: Intentional Filter

Sometimes an item does not need to be processed by any business branch, such as a record type permitted to be ignored under the contract. Even then, the classifier must still return a valid delegate:

~~~java
@Component
public class IgnorePaymentProcessor
        implements ItemProcessor<Payment, PaymentResult> {

    @Override
    public PaymentResult process(Payment payment) {
        return null;
    }
}
~~~

Classifier:

~~~java
return payment -> {
    String type = normalize(payment.type());
    return routes.getOrDefault(type, ignorePaymentProcessor);
};
~~~

In this example, an unrouted type is sent to IgnorePaymentProcessor, and that delegate returns null to filter the item. This is only appropriate when dropping the item is an intentional business decision.

Filtering does not automatically record reasons in SkipListener and creates no quarantine record. If auditing is required, record metrics or use a fallback that produces a rejected output instead of returning null.

Do not use filtering as the default handling for new types when the meaning of that type is unknown. A producer change could cause important data to vanish from output while the Job still finishes COMPLETED.

## 8. Normalizing Input Before Classification

Some no-match cases are caused solely by formatting differences. You can normalize type before looking up the route:

~~~java
private String normalize(String type) {
    if (type == null || type.isBlank()) {
        return "";
    }
    return type.trim().toUpperCase(Locale.ROOT);
}
~~~

Use Locale.ROOT for technical codes so results do not depend on the server's default locale.

Do not over-normalize by guessing values. For example, do not automatically turn "WIRE" into "TRANSFER" unless the contract specifies those two codes are equivalent. Aliases must be declared explicitly:

~~~java
Map<String, String> aliases = Map.of(
        "BANK_TRANSFER", "TRANSFER",
        "WIRE", "TRANSFER");
~~~

After normalization, look up the route key in the registry. If an alias is unrecognized, treat it as an unknown type. Normalization handles formatting differences, not validation.

## 9. Handling Null, Blank, and Missing Fields

The classifier should handle null before calling trim(), toUpperCase(), or switch:

~~~java
String type = payment == null ? null : payment.type();
~~~

In standard chunk processing, the reader should not emit null as an item because null typically marks end-of-data. However, the type property inside an item can be null or blank.

Errors can be separated:

~~~java
if (payment == null) {
    throw new IllegalArgumentException("Payment item must not be null");
}

if (payment.type() == null || payment.type().isBlank()) {
    throw new MissingPaymentTypeException(payment.paymentId());
}
~~~

A missing field can be a more serious contract violation than a new type. If you need to distinguish them, use dedicated exceptions or validate in a processor prior to routing. Do not let a NullPointerException from a switch or Map lookup serve as the sole error signal.

## 10. Distinguishing New Types from Missing Route Configuration

Two scenarios look similar yet have different root causes:

- Input contains type WALLET not yet supported by the application: new source data or unimplemented contract.
- Application has PaymentType.WALLET yet the registry lacks WalletPaymentProcessor: configuration/deployment bug.

If using a route map, validate configuration when constructing the bean:

~~~java
public class PaymentRouter {

    private final Map<PaymentType, ItemProcessor<Payment, PaymentResult>> routes;

    public PaymentRouter(
            Map<PaymentType, ItemProcessor<Payment, PaymentResult>> routes,
            Set<PaymentType> requiredTypes) {

        this.routes = Map.copyOf(routes);

        Set<PaymentType> missing = new HashSet<>(requiredTypes);
        missing.removeAll(routes.keySet());

        if (!missing.isEmpty()) {
            throw new IllegalStateException(
                    "Missing processors for payment types: " + missing);
        }
    }
}
~~~

Validating the registry at startup catches configuration errors before reading millions of items. Meanwhile, unknown types from payloads are handled inside classify() per the data policy.

Never use a fallback for a required delegate that is missing due to misconfiguration. If fallback covers both cases, the Job can succeed while every item of an already-supported type is quarantined.

## 11. Using an Enum to Reduce Routing Errors

If the list of types is fixed in the contract, using an enum lets the compiler help verify coverage:

~~~java
public enum PaymentType {
    CARD,
    TRANSFER,
    CASH
}
~~~

Parser converts source strings to enum:

~~~java
PaymentType parseType(String rawType) {
    String normalized = normalize(rawType);
    try {
        return PaymentType.valueOf(normalized);
    } catch (IllegalArgumentException ex) {
        throw new UnsupportedPaymentTypeException(normalized);
    }
}
~~~

Classifier:

~~~java
return payment -> switch (payment.paymentType()) {
    case CARD -> cardProcessor;
    case TRANSFER -> transferProcessor;
    case CASH -> cashProcessor;
};
~~~

When the enum grows, update the route registry and corresponding tests. With a Java enum switch expression without default, the compiler can help detect missing cases when the source enum changes and is recompiled. However, if JSON data carries a type not yet parsed into an enum, unknown values still need handling at deserialization.

Never map every unknown enum to a valid type like CASH. If processing must continue, use UNKNOWN or a separate raw-type representation and route it to fallback.

## 12. Map-Based Classifier with Fallback

A Map usually fits well when there are many routes or routes are configurable:

~~~java
public class MapPaymentClassifier
        implements Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> {

    private final Map<String, ItemProcessor<Payment, PaymentResult>> routes;
    private final ItemProcessor<Payment, PaymentResult> fallback;

    public MapPaymentClassifier(
            Map<String, ItemProcessor<Payment, PaymentResult>> routes,
            ItemProcessor<Payment, PaymentResult> fallback) {
        this.routes = Map.copyOf(routes);
        this.fallback = fallback;
    }

    @Override
    public ItemProcessor<?, ? extends PaymentResult> classify(Payment payment) {
        String key = normalize(payment.type());
        return routes.getOrDefault(key, fallback);
    }
}
~~~

Map.copyOf rejects null keys or null values. That is a useful property for catching invalid route configurations immediately when creating the classifier.

If fallback could be null, validate it in the constructor rather than letting failure happen inside process(). A router should guarantee that every input either returns a valid delegate or throws a meaningful exception.

## 13. Classifier by Multiple Properties

A route can depend on both type and source system:

~~~java
public record PaymentRoute(
        String sourceSystem,
        PaymentType type) {
}
~~~

Route map:

~~~java
Map<PaymentRoute, ItemProcessor<Payment, PaymentResult>> routes = Map.of(
        new PaymentRoute("ERP", PaymentType.CARD), erpCardProcessor,
        new PaymentRoute("MOBILE", PaymentType.CARD), mobileCardProcessor,
        new PaymentRoute("ERP", PaymentType.TRANSFER), erpTransferProcessor);
~~~

Classifier:

~~~java
PaymentRoute key = new PaymentRoute(
        normalize(payment.sourceSystem()),
        payment.paymentType());

return routes.getOrDefault(key, fallbackProcessor);
~~~

When no route is found, determine the cause: unsupported type, unregistered source system, or disallowed type/source combination. You can distinguish them by checking each component and generating a specific exception/rejection reason.

Do not use one generic fallback if cases require different behavior. For example, a new type from a producer might be quarantined, whereas a misconfigured source system might need to fail the Step.

## 14. No-Match in ClassifierCompositeItemProcessor

ClassifierCompositeItemProcessor generally operates along this conceptual logic:

~~~java
public O process(I item) throws Exception {
    ItemProcessor<?, ? extends O> delegate = classifier.classify(item);
    return (O) delegate.process(item);
}
~~~

This is a behavioral description to explain the contract; actual implementations may use different generics/casts by version. The key point is that the composite needs the delegate returned by the classifier. If the delegate is null, there is no processor to invoke.

Therefore:

- The classifier should never return null to signify "do not process".
- A fallback must be a valid ItemProcessor.
- If filtering is needed, the selected delegate returns null.
- If the Step must stop, the classifier throws a dedicated exception.
- If quarantine is needed, the fallback returns a rejected output or records it per writer design.

Do not rely on NullPointerException as a mechanism to signal an unknown route. It does not reveal which route key was invalid and can make logs hard to analyze.

## 15. No-Match in ClassifierCompositeItemWriter

A classifier can also be used to route writers. With ClassifierCompositeItemWriter, the classifier picks an ItemWriter for the item. If no writer matches and it returns null, the composite has no delegate to write the item; a similarly explicit policy is required.

Options:

- Throw an exception so the chunk fails.
- Return a fallback writer to write to a quarantine table/file.
- Route to an intentional discard writer only if the API and business rules permit.
- Normalize outputs to a single type and use a single writer.

Do not confuse a processor returning null with a writer no-match. A processor returning null filters before the writer receives the item. A writer classifier has no filtering concept like ItemProcessor; a writer typically performs write side effects and needs a valid delegate.

## 16. Exception Handling and Skip Policy

If the classifier throws UnsupportedPaymentTypeException inside ClassifierCompositeItemProcessor, the exception occurs during the process phase. The Step can apply a skip policy if that exception type is configured as skippable:

~~~java
return new StepBuilder("importPaymentsStep", jobRepository)
        .<Payment, PaymentResult>chunk(100, transactionManager)
        .reader(paymentReader)
        .processor(classifierComposite)
        .writer(paymentWriter)
        .faultTolerant()
        .skip(UnsupportedPaymentTypeException.class)
        .skipLimit(20)
        .listener(paymentSkipListener)
        .build();
~~~

Only use this configuration if unsupported payment types are genuinely allowed to be skipped. If an unsupported type indicates the producer sent a broken schema or deployment lacks a processor, fail-fast is usually better.

SkipListener has a dedicated callback for the process phase:

~~~java
public class PaymentSkipListener
        implements SkipListener<Payment, PaymentResult> {

    @Override
    public void onSkipInProcess(Payment item, Throwable cause) {
        // Record the business key and skip cause.
    }
}
~~~

If the classifier throws before producing output, the item can still be passed to onSkipInProcess because the error occurred during process. If an error occurs when the writer writes quarantine output, the callback will be onSkipInWrite. Distinguish stages properly for auditing.

## 17. Retry or Skip When No Route Exists?

A no-match caused by invalid data usually does not disappear on retry. With the same item and same classifier/configuration, retrying selects the same result. Thus, retry is inappropriate for a deterministic unknown type.

| Cause | Appropriate behavior |
|---|---|
| Type not supported in contract | Fail or quarantine per business rules |
| Typo/missing field | Validation failure; skip only when allowed |
| Missing route registry due to config | Fail fast, fix deployment |
| Policy lookup temporarily unreachable | Bounded retry on lookup |
| Transient cache failure | Retry or safe fallback per policy |
| Delegate fails due to business data | Skip/fail depending on exception and contract |

Do not retry UnsupportedPaymentTypeException just to re-run against the same immutable route map. If a route might appear after loading policy from an external service, distinguish that exception from transient lookup errors.

## 18. Impact of Retry and Restart

A classifier should be deterministic and repeatable. If a route depends on time, counters, call order, or mutable state, the same item can be routed differently on retry or restart.

Unstable example:

~~~java
return payment -> {
    if (retryCounter++ % 2 == 0) {
        return cardProcessor;
    }
    return fallbackProcessor;
};
~~~

When a chunk rolls back, the classifier may already have been called and mutated the counter in memory. A retry could send the same payment to fallback. After a restart, the counter is initialized differently again.

For stable routing:

- Rely on immutable fields of the item.
- Use explicit routing keys.
- Pin policy/schema versions in JobParameters or ExecutionContext.
- Do not modify the route map while the Step is running.
- If route decisions must be persisted, store them by business key with clear transaction semantics.

Retry should only apply to transient errors. Deterministic no-matches should have a fail, reject, or filter decision up front.

## 19. Thread Safety of Fallback and Classifier

The classifier and fallback processor are usually Spring singletons. If the Step runs with multiple threads or multiple JobExecutions, the same instance can be invoked concurrently.

Safe design:

- Keep the route map immutable after initialization.
- Do not store the current item in a field.
- Do not swap the fallback delegate while the Step is running.
- Make the fallback processor stateless or use thread-safe dependencies.
- If metrics are needed, use Micrometer or concurrent counters.
- If the fallback writes audits, use a transaction-aware writer/repository and idempotency keys.

Do not use a mutable ArrayList/HashMap to collect unmatched items from multiple threads. You can use concurrent structures for telemetry, yet important quarantine data should be persisted durably through a writer/database rather than kept only in memory.

## 20. Observing and Auditing Unmatched Items

When choosing a fallback, you need to know how many items did not match and why:

- Raw route key or normalized type value.
- Source system and schema version.
- Item business key.
- JobExecution ID and StepExecution ID.
- Fallback/rejection reason.
- Occurrence count by type.
- Timestamp and batch ID.

Do not log the full payload if it contains personal data or secrets. You can store the raw payload in a restricted-access quarantine store and log a reference ID.

Useful metrics:

- Items per route.
- Unmatched items.
- Items missing route keys.
- Filtered items.
- Skipped items.
- Errors caused by route configuration.

Distinguish no-match count from skip count and filter count. A fallback can produce a rejected output, so it still counts as processed and written rather than skipped.

## 21. Testing Classifier No-Match

Unit test all input types and every policy:

1. Supported types select the right delegate.
2. New types select fallback or throw an exception per policy.
3. Null types do not cause an unexplained NullPointerException.
4. Blank strings are handled properly.
5. Casing and whitespace are normalized accurately.
6. Aliases are supported only when declared.
7. Missing delegates in the registry catch configuration errors at startup.
8. Fallback returns a rejected result with business key and reason.
9. Filter delegates return null and do not reach the writer.
10. Retrying the same item still selects the same delegate.

Example fallback test:

~~~java
@Test
void routesUnknownTypeToFallback() throws Exception {
    Payment payment = new Payment(
            "PAY-99", "WALLET", new BigDecimal("10.00"));

    when(fallbackProcessor.process(payment))
            .thenReturn(PaymentResult.rejected(
                    "PAY-99", "WALLET", "UNSUPPORTED_TYPE"));

    ItemProcessor<?, ? extends PaymentResult> selected =
            classifier.classify(payment);

    assertSame(fallbackProcessor, selected);
    assertEquals(
            "REJECTED",
            ((ItemProcessor<Payment, PaymentResult>) selected).process(payment).status());
}
~~~

This example illustrates delegate selection and fallback output. In real tests, you can use a helper with appropriate generic types to avoid unnecessary casts.

## 22. Testing the Composite and Step Integration

Classifier unit tests do not prove the Step handles skip/filter/transactions accurately. Have integration tests for:

- Fallback is invoked and rejected output is written.
- Fail-fast exceptions cause the Step to be FAILED.
- Skippable exceptions increment skip count accurately.
- Filtering increments filter count and the writer receives no item.
- Quarantine writer failure rolls back the chunk per transaction.
- Transient retries do not create duplicates.
- Restarts preserve the route map and policy version.

Example dataset:

~~~text
PAY-01 CARD       -> CardPaymentProcessor
PAY-02 TRANSFER   -> TransferPaymentProcessor
PAY-03 WALLET     -> Fallback/Quarantine
PAY-04 null       -> MissingType policy
PAY-05 CASH       -> CashPaymentProcessor
~~~

After running the Job, reconcile:

- Total inputs.
- Accepted outputs.
- Rejected/quarantine outputs.
- Filter count.
- Skip count per stage.
- Records actually committed.

Do not merely assert Job COMPLETED. A Job can finish COMPLETED yet have filtered or quarantined many items; verify whether that is the intended business outcome.

## 23. When Should You Split Routes into Separate Steps?

If item types differ not only in processors but also in transactions, retry/skip policies, output resources, or schedules, a classifier inside one Step may no longer be the right structure.

Consider splitting Steps when:

- Each type uses a different database or transaction manager.
- Each type needs its own retry/skip limit.
- One type requires a separate output file or schema.
- Types must be restartable independently.
- Inputs can be pre-classified into separate staging streams.
- Separate status reporting per type is required.

ClassifierCompositeItemProcessor only routes processors within one StepExecution. It does not create new StepExecutions or transaction boundaries per branch.

If branches still share the reader, writer, and transaction policy, a composite usually keeps configuration lean. If each branch has a different lifecycle, splitting Steps makes operations and restarts clearer.

## 24. Common Pitfalls

**Returning null from the classifier:** the composite has no delegate to call and may throw NullPointerException. Return a fallback or throw a meaningful exception.

**Treating a null delegate as a filter:** filtering occurs when a valid ItemProcessor is called and returns null.

**Using fallback for configuration errors:** a route missing due to deployment can be masked as an unsupported item. Validate the registry at startup.

**Using one fallback for all unknown cases:** new types, typos, and missing fields may need different policies. Classify the no-match reason.

**Dropping new types without auditing:** the Job finishes yet data can be lost. Write rejected output or fail per contract.

**Over-normalizing strings:** undefined aliases can merge two distinct business types into one. Declare aliases explicitly.

**Using skip for deterministic route errors:** retry/skip cannot fix a missing registry or broken contract. Distinguish config bugs from data errors.

**Retrying unknown types indefinitely:** the same item usually still fails to match. Retry only transient lookup failures.

**Confusing no-match with delegate errors:** the classifier failing to pick a processor is a routing error; a selected delegate failing during processing is a process error.

**Not testing null/blank:** the classifier may throw NullPointerException or misroute.

**Omitting fallback from reconciliation:** rejected output can still count as a successful write; skip/filter/reject must be reported separately.

## Conclusion

When an item does not match the classifier, ClassifierCompositeItemProcessor does not choose an alternative behavior automatically. The classifier must return a valid delegate or throw a meaningful exception; returning null usually causes an error when the composite invokes the delegate. Decide explicitly whether no-match should fail the Step, route to fallback/quarantine, or filter intentionally. Distinguish no-match from a delegate returning null and from skip exceptions so audits, metrics, and retries stay accurate. Normalize route keys explicitly, validate required registries at startup, keep the classifier deterministic across retries/restarts, and test both unit and Step integration levels. If each branch has different transactions or lifecycles, consider splitting into separate Steps rather than letting a classifier hide operational differences.
