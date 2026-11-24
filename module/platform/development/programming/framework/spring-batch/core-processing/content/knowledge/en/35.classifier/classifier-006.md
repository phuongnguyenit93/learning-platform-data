# Default Classifier

In Spring Batch, a **Classifier** is a strategy used to classify an input object and select a corresponding result. The result is usually a delegate responsible for performing the next step of work, such as an ItemWriter or ItemProcessor. Thanks to a classifier, a step can route items to multiple processing branches without scattering many conditionals throughout writers or processors.

In the Spring Classification package, **SubclassClassifier** is the general-purpose implementation commonly used when you want to pick a result based on an object's class. It takes a type map and a default value. When the item's class matches an entry in the map or a supported supertype, the classifier returns the registered delegate; if no mapping is found, it returns the default value.

The default value is a critical part of the contract. It defines what happens to items without a specific mapping. Without choosing a clear fallback, the application can drop data, throw a NullPointerException, or misroute items. Therefore, a default classifier must be configured and tested like a real business branch.

## 1. What Is a Classifier?

A Classifier is a small abstraction with a single responsibility: accept an object and return a classification result.

Basic contract:

~~~java
public interface Classifier<C, T> {

    T classify(C classifiable);
}
~~~

Where:

- C is the type of object being classified.
- T is the result type returned by the classifier.
- classifiable is the object to route.

For example, a classifier accepts a Payment and returns the matching ItemWriter:

~~~text
Payment
   |
   v
Classifier<Payment, ItemWriter<Payment>>
   |
   +---- CashPayment ----> cashWriter
   |
   +---- CardPayment ----> cardWriter
   |
   +---- Unknown type ---> fallbackWriter
~~~

A Classifier does not process data itself and does not write items. It only chooses the delegate. The composite component or caller executes the selected delegate afterward.

## 2. Why Do You Need a Classifier in Spring Batch?

A job can read multiple item types from the same source. Depending on the item type, the application may need to:

- Write cash transactions to one table.
- Write card transactions to another table.
- Route error records to an error writer.
- Use a different processor for each subtype.
- Send each group of data to a separate output resource.

Without a classifier, routing logic often gets stuffed into one large writer with many if/else branches. When adding a new item type, the main writer has to change and can affect existing branches.

A classifier separates the routing decision from the write/transform action. Each delegate keeps a clear responsibility, while the classifier describes the rule for choosing a delegate.

## 3. Default Classifier in Spring Classification

A common implementation for class-based mapping is **SubclassClassifier<C, T>**. It is configured with:

- Type map: maps classes to corresponding results.
- Default value: fallback result when no matching mapping is found.

Conceptual example:

~~~java
Map<Class<? extends Payment>, ItemWriter<? super Payment>> typeMap =
        new HashMap<>();

typeMap.put(CashPayment.class, cashPaymentWriter);
typeMap.put(CardPayment.class, cardPaymentWriter);

SubclassClassifier<Payment, ItemWriter<? super Payment>> classifier =
        new SubclassClassifier<>();
classifier.setTypeMap(typeMap);
classifier.setDefaultValue(unsupportedPaymentWriter);
~~~

This snippet illustrates the idea of configuring a type map and fallback. Specific overloads/generic types must match the Spring Batch and Spring Classification versions used by your project.

When the classifier receives an item:

1. Retrieve the runtime class of the item.
2. Look up a matching mapping in the type map according to the implementation's class/subclass rules.
3. If found, return the mapped value.
4. If not found, return the default value.

Default classifier does not mean Spring Batch automatically knows your application's default writer. The application must supply a meaningful fallback value.

## 4. What Is the Default Value Used For?

The default value handles classes not declared in the type map. For instance, the system currently supports CashPayment and CardPayment, but later the source adds VoucherPayment.

If the classifier has no mapping for VoucherPayment, the default value decides the outcome:

| Default value | Behavior |
|---|---|
| UnsupportedPaymentWriter | Writes the record to an output dedicated to unsupported types |
| RejectingPaymentWriter | Throws an exception so the step fails |
| AuditWriter | Saves the business key and item type for investigation |
| Null | No delegate; the caller may fail when using the result |

In production, the fallback should be chosen according to the business contract. If an unrecognized item type is invalid data, a reject writer or explicit exception is usually safer than silently ignoring it.

Do not use a default writer that only logs and returns success if downstream requires ensuring every item was processed. When a fallback is used, include metrics or auditing to know how many items entered that branch.

## 5. Mapping by Class and Subclass

SubclassClassifier is designed to classify based on an object's type. The type map can declare mappings for a concrete class or a supertype to apply to matching subtypes according to the implementation's lookup rules.

Example model:

~~~java
public abstract class Payment {
    private String paymentId;
}

public class CashPayment extends Payment {
    private BigDecimal cashAmount;
}

public class CardPayment extends Payment {
    private String cardReference;
}

public class CorporateCardPayment extends CardPayment {
    private String companyCode;
}
~~~

If the map contains CashPayment and CardPayment, a CorporateCardPayment can use the parent CardPayment mapping via subclass lookup. This avoids registering every subtype if they truly share the same handling.

If CorporateCardPayment needs its own writer, register a specific mapping for that class. Specific mappings should take precedence according to the lookup semantics of the SubclassClassifier version in use.

Do not assume every implementation traverses interfaces the same way it traverses superclasses. If the domain model relies heavily on interfaces, verify lookup behavior or use a custom classifier with explicit interface rules.

## 6. Specific Class Mapping vs Supertype Mapping

A type map can contain mappings for both subtypes and superclasses:

~~~java
Map<Class<? extends Payment>, ItemWriter<? super Payment>> typeMap =
        new HashMap<>();

typeMap.put(Payment.class, generalPaymentWriter);
typeMap.put(CardPayment.class, cardPaymentWriter);
typeMap.put(CorporateCardPayment.class, corporateCardWriter);
typeMap.put(CashPayment.class, cashPaymentWriter);
~~~

The goal is:

- CashPayment uses cashPaymentWriter.
- CardPayment uses cardPaymentWriter.
- CorporateCardPayment uses corporateCardWriter if the concrete class is recognized.
- Another subtype of Payment can use generalPaymentWriter if lookup walks up to Payment.class.

Exact precedence depends on the classifier implementation. With multiple inheritance levels or complex mappings, write unit tests for every runtime class instead of relying on Map insertion order.

## 7. Do Not Confuse Class-Based Classifier with Field-Based Classifier

SubclassClassifier classifies by runtime class. It does not automatically read a business field such as paymentType, region, or status.

For example, two objects of the same class PaymentRecord have different type fields:

~~~java
public class PaymentRecord {
    private String paymentType;
    private BigDecimal amount;
}
~~~

If you want to route by paymentType, use a custom classifier:

~~~java
Classifier<PaymentRecord, ItemWriter<? super PaymentRecord>> classifier =
        payment -> switch (payment.getPaymentType()) {
            case "CASH" -> cashWriter;
            case "CARD" -> cardWriter;
            default -> unsupportedWriter;
        };
~~~

Class-based mapping fits when subtypes represent differences in structure or behavior. Field-based mapping fits when a single DTO type holds a business discriminator.

Do not create many subclasses just to replace a discriminator field if the domain model does not need type distinction at the Java level.

## 8. ClassifierCompositeItemWriter

Spring Batch provides **ClassifierCompositeItemWriter<T>** to route items to the writer selected by a classifier. It is an ItemWriter whose delegate is determined per item.

Example:

~~~java
@Bean
public ClassifierCompositeItemWriter<Payment> paymentWriter(
        ItemWriter<Payment> cashPaymentWriter,
        ItemWriter<Payment> cardPaymentWriter,
        ItemWriter<Payment> unsupportedPaymentWriter) {

    Classifier<Payment, ItemWriter<? super Payment>> classifier =
            new SubclassClassifier<>(
                    Map.of(
                            CashPayment.class, cashPaymentWriter,
                            CardPayment.class, cardPaymentWriter),
                    unsupportedPaymentWriter);

    return new ClassifierCompositeItemWriterBuilder<Payment>()
            .classifier(classifier)
            .build();
}
~~~

This example illustrates combining a classifier with the composite writer. Adjust generic types and constructors for your specific API version; some versions configure SubclassClassifier via setters rather than a constructor.

The composite writer receives a chunk from the step, the classifier selects a delegate for each item, and the delegate writer performs the write. Register delegates with lifecycle/state appropriately if they are ItemStreams. When using stateful writers, ensure Spring Batch opens, updates, and closes internal streams inside the composite according to your application configuration.

## 9. Routing by Item Type Within the Same Chunk

A single chunk can contain multiple subtypes:

~~~text
Chunk:
  CashPayment
  CardPayment
  CashPayment
  CorporateCardPayment
  UnknownPayment
~~~

The classifier determines the writer for each item. Consequently, one chunk can be distributed across multiple delegates. Understand transaction boundaries and delegate behavior:

- Writers sharing the same transaction manager/resource can participate in the chunk's transaction.
- A delegate writing files or calling APIs may not roll back with the database.
- A delegate throwing an exception can fail the chunk.
- Chunk retries may invoke a delegate again that already performed side effects.

Do not assume routing across multiple writers creates a distributed transaction. If delegates write to different resources, design idempotency, staging, or an outbox per resource.

## 10. Default Classifier in Spring Configuration

You can declare SubclassClassifier as a bean for reuse:

~~~java
@Bean
public Classifier<Payment, ItemWriter<? super Payment>> paymentClassifier(
        ItemWriter<Payment> cashPaymentWriter,
        ItemWriter<Payment> cardPaymentWriter,
        ItemWriter<Payment> unsupportedPaymentWriter) {

    Map<Class<? extends Payment>, ItemWriter<? super Payment>> routes =
            new HashMap<>();
    routes.put(CashPayment.class, cashPaymentWriter);
    routes.put(CardPayment.class, cardPaymentWriter);

    SubclassClassifier<Payment, ItemWriter<? super Payment>> classifier =
            new SubclassClassifier<>();
    classifier.setTypeMap(routes);
    classifier.setDefaultValue(unsupportedPaymentWriter);
    return classifier;
}
~~~

Then inject the classifier into the composite writer:

~~~java
@Bean
public ClassifierCompositeItemWriter<Payment> paymentCompositeWriter(
        Classifier<Payment, ItemWriter<? super Payment>> paymentClassifier) {

    return new ClassifierCompositeItemWriterBuilder<Payment>()
            .classifier(paymentClassifier)
            .build();
}
~~~

The classifier bean only holds routing rules. Delegate writers should be configured separately so each writer has its own name, resource, SQL, and lifecycle.

If the classifier holds mutable state or the type map changes at runtime, multiple steps may observe different routing rules within the same job. Usually, configure an immutable map before the step runs and do not modify it during processing.

## 11. Configuring the Composite Writer in a Step

The composite writer can be wired like a normal writer:

~~~java
@Bean
public Step routePaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Payment> paymentReader,
        ItemProcessor<Payment, Payment> paymentProcessor,
        ClassifierCompositeItemWriter<Payment> paymentCompositeWriter) {

    return new StepBuilder("routePaymentsStep", jobRepository)
            .<Payment, Payment>chunk(100, transactionManager)
            .reader(paymentReader)
            .processor(paymentProcessor)
            .writer(paymentCompositeWriter)
            .build();
}
~~~

From the step's perspective, there is only one writer: the composite. Choosing the concrete writer happens inside the composite via the classifier.

If a delegate writer needs to open resources or save state, ensure the composite/step is aware of that stream. Not every custom wrapper forwards the ItemStream lifecycle automatically. Verify the component's contract and register delegates properly.

## 12. ClassifierCompositeItemProcessor

Spring Batch also has **ClassifierCompositeItemProcessor<I, O>** to select a processor by input item. This is how to use a classifier when item types need different transformations:

~~~text
Input item
   |
   v
Classifier
   |
   +---- CashPayment ----> CashPaymentProcessor
   |
   +---- CardPayment ----> CardPaymentProcessor
   |
   +---- Other ----------> UnsupportedPaymentProcessor
~~~

Conceptual example:

~~~java
Classifier<Payment, ItemProcessor<?, ?>> processorClassifier =
        payment -> {
            if (payment instanceof CashPayment) {
                return cashPaymentProcessor;
            }
            if (payment instanceof CardPayment) {
                return cardPaymentProcessor;
            }
            return unsupportedPaymentProcessor;
        };

ClassifierCompositeItemProcessor<Payment, PaymentResult> processor =
        new ClassifierCompositeItemProcessorBuilder<Payment, PaymentResult>()
                .classifier(processorClassifier)
                .build();
~~~

Delegate processors need input/output types compatible with the generic types published by the composite. Because the classifier picks the processor at runtime, the compiler cannot prove every branch returns the exact output type. Design a common output type or use explicit adapters for each subtype.

If each processor returns a completely different result type, you can use a sealed result type, a common interface, or a DTO envelope so the writer handles them uniformly.

## 13. Default Processor When There Is No Mapping

The default value of a processor classifier can be a processor dedicated to handling unsupported subtypes:

- Return a result carrying status UNSUPPORTED for an error writer to handle later.
- Throw UnsupportedPaymentTypeException so the step fails.
- Normalize the item into a common fallback DTO if business rules permit.

Do not let a fallback processor return null if that causes the item to vanish without auditing. Null from an ItemProcessor means filtering; if an unsupported item is an error, represent the error with an exception or an explicit error output.

## 14. Classifier Does Not Replace ItemProcessor

The classifier decides the delegate; the processor performs the transformation.

| Component | Responsibility |
|---|---|
| Classifier | Select branch/delegate based on item |
| ItemProcessor | Validate, transform, or filter item |
| ClassifierCompositeItemProcessor | Use classifier to pick processor |
| ItemWriter | Write item |
| ClassifierCompositeItemWriter | Use classifier to pick writer |

If branch-selection logic is also performing data mapping, separating concerns becomes hard to test. Keep the classifier small so routing can be tested independently of business transformations.

## 15. Classifying by Exception Type

A classifier can also accept Throwable and return a corresponding policy or result. This idea is used in some Spring retry/exception-handling mechanisms.

For example, a classifier can categorize:

- Timeouts as retryable.
- Validation exceptions as skippable.
- Configuration exceptions as fatal.

However, classifying exceptions does not itself configure retry or skip. The step still needs a RetryPolicy, SkipPolicy, or corresponding fault-tolerant configuration.

Do not confuse a SubclassClassifier used for selecting delegates with a specialized exception classifier. The same Classifier abstraction can classify many kinds of inputs and return many kinds of results.

## 16. When Should You Use SubclassClassifier?

SubclassClassifier fits when:

- Java subtypes represent different item types requiring different handling.
- Class-to-delegate mappings are relatively static.
- There is a common fallback for unregistered subtypes.
- Rules based on the class hierarchy are sufficient to decide routing.

For example:

- Payment subtype to writer.
- Event subtype to processor.
- Command class to handler.
- Exception class to policy/result.

It is less suitable when:

- Routing depends on multiple fields at once.
- Rules vary by job parameter or runtime data.
- A database lookup is needed to pick a delegate.
- Complex interface hierarchies must be handled in ways default lookup does not satisfy.
- Routing is needed by tenant, region, time, or business state.

In those cases, a custom Classifier is usually clearer. Keep lookup logic outside the writer/processor and ensure the classifier can be unit tested independently.

## 17. Should Default Value Fail Fast or Route to Fallback?

The decision depends on what an unrecognized item means:

| Scenario | Appropriate default |
|---|---|
| New subtype is invalid data under the contract | Reject writer or exception |
| New subtype is allowed to be stored for later processing | Quarantine/error writer |
| Every subtype can use the same generic write path | General writer |
| Cannot determine business meaning | Fail fast |
| Unknown type is accepted yet must be tracked | Audit/fallback writer with metrics |

Fail fast is useful when misrouting could corrupt data. Fallback is useful when the system must ingest and isolate new data without losing a trace. There is no single right default value for every job; it must reflect the integration contract.

## 18. Do Not Let a Default Writer Silently Drop Items

An empty default writer:

~~~java
ItemWriter<Payment> discardWriter = chunk -> {
    // Write nothing.
};
~~~

is only appropriate if dropping items is permitted by business rules and has dedicated auditing/metrics. If used merely to avoid exceptions, the job can report COMPLETED while data is lost.

A safer fallback can write to a quarantine table:

~~~java
public class UnsupportedPaymentWriter implements ItemWriter<Payment> {

    private final JdbcTemplate jdbcTemplate;

    @Override
    public void write(Chunk<? extends Payment> chunk) {
        for (Payment payment : chunk) {
            jdbcTemplate.update("""
                    insert into unsupported_payment(payment_id, java_type)
                    values (?, ?)
                    """,
                    payment.getPaymentId(),
                    payment.getClass().getName());
        }
    }
}
~~~

This is an illustrative example. Quarantine writes must participate in an appropriate transaction and avoid writing unnecessary sensitive payloads. If the fallback writer fails to write, it should throw an exception so the step does not report false success.

## 19. Handling Null Input

Not every classifier has the same behavior on null input. SubclassClassifier may return the default value or have implementation/version-specific behavior. A custom classifier may throw NullPointerException if it calls getClass or accesses fields without null checks.

In normal chunk processing, ItemReader uses null to signal EOF, so processors/writers do not receive null as an item. However, a classifier can be used elsewhere or called directly in unit tests.

Specify null behavior:

- Null is not a valid item: fail fast with a clear exception.
- Null is a meaningful state: define a separate branch.
- Null is only permitted by framework contract: do not pass it into the classifier as an item.

Do not use a default writer to handle unexpected nulls if that hides upstream errors.

## 20. Type Map Should Be Configured Immutably

The type map is typically built when initializing the application context. Once the step starts, the mapping should not be altered:

~~~java
Map<Class<? extends Payment>, ItemWriter<? super Payment>> routes =
        Map.of(
                CashPayment.class, cashPaymentWriter,
                CardPayment.class, cardPaymentWriter);
~~~

An immutable map keeps routing consistent throughout job execution and avoids race conditions across threads.

If routing needs to vary by job parameter, create a step-scoped classifier/component with configuration resolved before execution starts. Do not mutate a singleton classifier shared by multiple jobs.

## 21. Thread Safety of Classifier and Delegates

A classifier usually only reads a type map and returns a delegate, so it can be shared if it holds no mutable state. However, delegate writers/processors might not be thread-safe.

Distinguish:

- Thread safety of the classifier.
- Thread safety of each delegate.
- Thread safety of the composite component.
- Transaction/resource isolation across threads.

If multiple partitions share one classifier, the mapping should be immutable. Delegate writers must have separate state/resources or be explicitly designed for concurrent use. Do not let two partitions write to the same file or the same mutable writer instance if the component does not support it.

## 22. Classifier and Transaction Boundaries

A classifier does not create new transactions. When the composite writer is invoked in a chunk, the selected delegate normally executes within the current transaction context if its resource participates in that transaction.

If a chunk routes items to two JDBC writers:

- Both can participate in the same transaction if using the same transaction manager/resource.
- An exception from one writer can roll back the chunk.
- If one writer already sent an API request or wrote a file, those side effects do not automatically roll back.
- A chunk retry can re-route the item and invoke the delegate again.

Therefore, classifier routing does not solve atomicity across multiple resources. Design idempotent delegates and decouple external side effects via an outbox or an appropriate publish step.

## 23. Delegate Call Order and Failures Between Branches

When a chunk contains multiple item types, the composite may invoke delegates according to the framework's implementation. Do not rely on writer invocation order if business correctness requires one branch to complete before another.

If there is a dependency between two branches, model it with separate steps/flows or an explicitly orchestrated writer. If order is purely for performance, check the implementation/version and write integration tests for the behavior you rely on.

One delegate may write successfully and then the next delegate fails. If the two writers do not share a transaction, the first output may already be committed. Retrying may call the first writer again; idempotency is necessary.

## 24. Composite Writer and ItemStream Delegates

Some delegate writers implement ItemStream to manage files or checkpoints. When wrapping them in a composite, ensure lifecycles are propagated properly:

- open is called before write.
- update is called to persist state.
- close is called when the step ends.
- Delegates open the right resources.
- Delegate state keys do not collide.

If the composite does not automatically manage delegate streams under your configuration/version, you may need to register delegates as step streams or use a wrapper supporting ItemStream. Check the actual API instead of assuming every object referenced in a classifier gets automatic lifecycle management.

Especially for file writers, missing close can lose buffered data or leave incomplete files. For restartable writers, missing update can lose delegate-specific checkpoints.

## 25. Mapping Classes Across Different Packages/Modules

In large applications, subtypes may be defined in separate modules. The classifier needs visibility of those classes to register mappings. Avoid circular dependencies:

- Domain module defines Payment and subtypes.
- Batch module defines classifier/routing.
- Infrastructure module provides delegate writers.

Place the mapping in the composition/configuration module where both domain types and delegates are visible. Do not make the domain model depend directly on Spring Batch writers.

If new plugins/modules can be added dynamically, SubclassClassifier with a static map may not suffice. In that case you need a registry with a clear lifecycle and update rules, yet the registry must be frozen per job execution so restarts remain deterministic.

## 26. Unit Testing SubclassClassifier

A classifier should be tested independently of a Spring Batch step:

~~~java
class PaymentClassifierTest {

    private final ItemWriter<Payment> cashWriter = chunk -> {};
    private final ItemWriter<Payment> cardWriter = chunk -> {};
    private final ItemWriter<Payment> fallbackWriter = chunk -> {};

    private SubclassClassifier<Payment, ItemWriter<? super Payment>> classifier;

    @BeforeEach
    void setUp() {
        Map<Class<? extends Payment>, ItemWriter<? super Payment>> routes =
                new HashMap<>();
        routes.put(CashPayment.class, cashWriter);
        routes.put(CardPayment.class, cardWriter);

        classifier = new SubclassClassifier<>();
        classifier.setTypeMap(routes);
        classifier.setDefaultValue(fallbackWriter);
    }

    @Test
    void selectsWriterForExactClass() {
        assertSame(cashWriter, classifier.classify(new CashPayment()));
        assertSame(cardWriter, classifier.classify(new CardPayment()));
    }

    @Test
    void selectsDefaultForUnknownClass() {
        assertSame(fallbackWriter,
                classifier.classify(new VoucherPayment()));
    }
}
~~~

The classes and constructors in this example are illustrative models. Real tests should cover exact classes, subclasses, superclass mappings, unknown types, and null behavior per implementation/version.

Use assertSame when the goal is verifying the classifier returns the exact registered delegate instance. Use assertEquals if the result is a value object rather than a collaborator.

## 27. Testing Mappings with Superclasses and Specific Subtypes

When a type map has multiple levels, verify explicitly:

| Runtime type | Expected mapping |
|---|---|
| CashPayment | cash writer |
| CardPayment | card writer |
| CorporateCardPayment | corporate writer if registered specifically; otherwise card writer via superclass lookup |
| VoucherPayment | default writer |

This test protects behavior when the domain adds new subtypes. If a new subtype accidentally falls into a general writer, the test catches it before production data is misrouted.

For interfaces, write dedicated tests if the application expects interface mappings to apply. If the implementation does not look up interfaces according to your required contract, use a custom classifier to explicitly define precedence among exact classes, superclasses, and interfaces.

## 28. Testing Default Value and Unknown Types

The default branch should be tested as a critical branch:

- Does an unregistered class receive the right fallback?
- Does the fallback record the business key and runtime type?
- Does the fallback throw an exception if data is unacceptable?
- Do metrics/audits increment when the fallback branch is invoked?
- Is a new subtype mistakenly routed to the default writer?

If the default value is a quarantine writer, integration tests must verify the item appears in the quarantine output and does not appear in the tables/files of valid branches.

If the default value is a rejecting writer, verify the step fails with a diagnosable exception and the transaction rolls back as expected.

## 29. Integration Testing ClassifierCompositeItemWriter

Unit testing the classifier does not prove the composite invokes delegates properly. An integration test can:

1. Create two or three test-double writers, each recording received business keys.
2. Configure SubclassClassifier with a type map and default writer.
3. Build ClassifierCompositeItemWriter.
4. Send a chunk containing multiple subtypes.
5. Verify each item reaches the right writer.
6. Verify unknown subtypes go to the default branch.
7. Verify exceptions from delegates propagate and the step does not report false success.

If you need to check write call counts or item grouping per call, assert specifically per API/version. The most important contract is that items are routed accurately and delegate failures are handled properly.

## 30. Testing the Composite Processor

For ClassifierCompositeItemProcessor, test:

- Each subtype picks the right processor.
- Outputs from processors are compatible with the shared output type.
- The fallback processor handles unknown types per contract.
- Processors return null only when intentionally filtering.
- Exceptions from delegates propagate for fault-tolerant policies to handle.

One test per delegate helps distinguish classifier bugs from business transformation bugs. If you only test the entire job, when output is wrong it is hard to tell whether routing or a processor caused the error.

## 31. Testing Routing by Business Discriminator

If a custom classifier is field-based, test both valid and invalid values:

~~~java
Classifier<PaymentRecord, ItemWriter<? super PaymentRecord>> classifier =
        record -> switch (record.getPaymentType()) {
            case "CASH" -> cashWriter;
            case "CARD" -> cardWriter;
            case "VOUCHER" -> voucherWriter;
            default -> unsupportedWriter;
        };
~~~

Cases to test:

- paymentType is CASH.
- paymentType is CARD.
- paymentType is VOUCHER.
- paymentType is null.
- paymentType is blank.
- Lowercase or non-standard casing if the contract requires normalization.
- New unsupported values.

Do not automatically uppercase/trim if doing so alters the contract. If normalization is a business rule, place it in an explicit validation/normalization step and test it separately.

## 32. Configuring Mappings by JobParameters

Some jobs need routing to vary by tenant, region, or output version. A classifier can be built from job parameters, provided you ensure:

- Mappings are resolved before the step processes items.
- Restarting a JobInstance receives the exact same routing configuration.
- Delegates/resources have distinct identities per output key.
- Mappings are not modified while the step is running.
- Configuration is validated before opening resources.

If the same JobInstance restarts with a different routing map, previously committed items may have gone to a different delegate than post-restart items. Store the routing version or an identifying parameter to confirm configuration did not change.

## 33. Classifier and Partitioning

Classifier routing items within a single step differs from partitioning:

- Classifier chooses a delegate for each item in a chunk.
- Partitioning splits the workload into separate executions/partitions, typically by key range or resource.

If the goal is parallel execution by tenant or shard, partitioning is usually more appropriate than routing items across different writers in the same thread.

Both mechanisms can be combined, yet writer instances, transactions, and output resources must be controlled per partition. Do not let multiple partitions write to one mutable delegate or one file without synchronization/partition-specific resources.

## 34. Classifier Performance

Class-based classifiers usually have low overhead compared to writer I/O. However, complex routing can affect throughput:

- Avoid reflection or per-item database lookups if possible.
- Keep the type map immutable and lookups simple.
- Do not log every classify call at INFO level in large jobs.
- Use per-branch metrics instead of per-item logs.
- If items must be grouped by delegate to reduce write calls, verify the composite implementation does so; do not assume it.

For custom classifiers based on multiple fields, compute the discriminator once in the processor if it is expensive and store the result in the output DTO when appropriate.

## 35. Logging and Observability for the Default Branch

The fallback branch is often where new subtypes or contract-violating data are discovered. Track:

- Number of items routed to each delegate.
- Number of items entering the default branch.
- Unsupported runtime classes or discriminators.
- Job/step execution identity.
- Business keys needed for investigation.
- Exception counts from each delegate.

Do not log full objects if they contain personal data or secrets. Business keys and runtime types are usually enough to locate the record in the source.

If the default branch receives new items frequently, consider upgrading the contract and registering an official mapping rather than leaving them permanently in fallback.

## 36. Common Pitfalls

| Scenario | Cause | Resolution |
|---|---|---|
| Unknown subtype causes NullPointerException | Default value not configured or fallback returns null | Register a non-null default delegate or fail explicitly |
| Subclass goes to unexpected writer | Superclass mapping applied via hierarchy lookup | Register a specific mapping and test precedence |
| Interface mapping has no effect | Class-hierarchy lookup implementation does not handle interfaces as expected | Use a custom classifier or verify interface behavior |
| All subtypes go to default | Type map uses a different class than runtime type or wrong generic mapping | Check runtime classes and map keys |
| Field discriminator is ignored | Used SubclassClassifier for field-based routing | Write a custom Classifier by business field |
| Items vanish silently | Default writer discards data | Use quarantine/reject branch and metrics |
| Fallback processor filters items unintentionally | Returns null for unsupported types | Throw exception or return error result |
| Composite writer writes partially then fails | Delegates use different resources/transactions | Idempotency, staging, and integration tests |
| Delegate is not opened/closed | Stream lifecycle not forwarded/registered | Manage delegate ItemStreams explicitly |
| Routing changes after restart | Mapping depends on unversioned runtime config | Keep routing config stable per JobInstance |
| Multiple partitions write same resource | Shared mutable delegate or output path | Create separate writers/resources per partition |
| Excessive logging | Logging every classify call at high level | Use per-branch metrics and selective logging |

## 37. Workflow for Building a Default Classifier

1. **Identify input:** classify by runtime class or business discriminator?
2. **Choose result:** which writer, processor, policy, or handler is returned?
3. **Create type map:** declare concrete mappings and required superclass mappings.
4. **Choose default value:** fallback, quarantine, or reject per business contract.
5. **Define unknown/null behavior:** prevent unintended null results.
6. **Keep mappings stable:** immutable configuration within a JobInstance.
7. **Connect composite:** use ClassifierCompositeItemWriter or ClassifierCompositeItemProcessor when appropriate.
8. **Manage delegate lifecycle:** register ItemStreams and resources properly.
9. **Check transactions:** determine whether delegates share the same transaction resource.
10. **Write unit tests:** exact class, subclass, superclass, unknown, and fallback.
11. **Write integration tests:** send chunks with multiple subtypes and verify routing/outputs.
12. **Monitor fallback:** metrics, audits, and a process for updating mappings when new subtypes arrive.

## 38. Key Principles to Remember

- A Classifier takes an object and returns a classification result; it does not write or transform items itself.
- SubclassClassifier is the common implementation for mapping classes/subclasses to delegates.
- Type map defines specific mappings; default value defines the result when no mapping is found.
- Default value must reflect the business contract; never let null or an empty writer silently lose data.
- SubclassClassifier classifies by runtime type, not by reading discriminator fields automatically.
- With superclass and specific subtype mappings, test lookup precedence for the version in use.
- Do not assume interface lookup behaves identically to superclass lookup.
- ClassifierCompositeItemWriter routes items to matching writers; ClassifierCompositeItemProcessor selects processors per item.
- Delegates need compatible input/output types and proper lifecycles.
- Classifier routing does not create distributed transactions across delegates.
- Keep type maps immutable and routing deterministic across restarts.
- Test the default branch, unknown subtypes, null behavior, delegate exceptions, and transaction outcomes.
- Use metrics/audits to detect items entering fallback; avoid logging sensitive payloads.
- Use partitioning when the goal is parallelizing workloads across shards/tenants rather than just picking a writer per item.

A default classifier helps a Spring Batch job route item types via one centralized rule. When the type map is clear, the fallback is chosen intentionally, and composite delegates are tested alongside transactions/lifecycles, the application can expand with new subtypes while keeping control over where data is processed.
