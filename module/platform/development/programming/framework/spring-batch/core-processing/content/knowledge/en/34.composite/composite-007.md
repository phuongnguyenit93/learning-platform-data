# Classifier-Selected Composite Processor

In Spring Batch, a Job may receive multiple kinds of items in the same data stream. Each item type may require different processing rules: BUY transactions need limit checks, SELL transactions need fee calculation, and TRANSFER transactions need source and target account validation. Putting all logic into one large ItemProcessor with many if/else branches makes the component hard to extend and hard to test.

**ClassifierCompositeItemProcessor** solves this routing problem. It takes an item, uses a **Classifier** to pick the right processor, and forwards the item to that delegate processor. Each item is routed according to its own classification result.

Keep in mind that a classifier-based composite processor picks **one processing branch per item**. It does not run all processors sequentially like CompositeItemProcessor. If one branch needs multiple sequential transformation steps, you can place a CompositeItemProcessor as the delegate for that branch.

## 1. The Multi-Processor Problem

Suppose a Job imports transactions from multiple sources. Each item has a transaction type and common data fields:

~~~java
public class Trade {

    private String tradeId;
    private String type;
    private BigDecimal amount;
    private String sourceAccount;
    private String targetAccount;

    // Getters and setters
}
~~~

Different transaction types need different processing:

| Type | Processing Rules |
|---|---|
| BUY | Validate amount and purchase limit, normalize order info |
| SELL | Validate sell quantity, calculate transaction fee |
| TRANSFER | Verify source/target accounts and check transfer rules |

A single monolithic processor might look like this:

~~~java
public class TradeProcessor implements ItemProcessor<Trade, TradeResult> {

    @Override
    public TradeResult process(Trade trade) {
        if ("BUY".equals(trade.getType())) {
            // BUY logic
        } else if ("SELL".equals(trade.getType())) {
            // SELL logic
        } else if ("TRANSFER".equals(trade.getType())) {
            // TRANSFER logic
        } else {
            throw new IllegalArgumentException(
                    "Unsupported trade type: " + trade.getType());
        }

        // ...
    }
}
~~~

As the number of types grows, this processor must know every rule, every dependency, and every change across branches. Adding a new type modifies an already large class, making testing and maintenance difficult.

With ClassifierCompositeItemProcessor, each rule can be extracted into a dedicated ItemProcessor and items are routed to the right processor.

## 2. How Does ClassifierCompositeItemProcessor Work?

ClassifierCompositeItemProcessor is a specialized ItemProcessor. It holds a Classifier responsible for selecting a delegate processor based on the current input.

Processing flow:

~~~text
ItemReader
    |
    v
Trade item
    |
    v
ClassifierCompositeItemProcessor
    |
    v
Classifier.classify(item)
    |
    +---- BUY ------> BuyTradeProcessor
    |
    +---- SELL -----> SellTradeProcessor
    |
    +---- TRANSFER -> TransferTradeProcessor
    |
    v
TradeResult
    |
    v
ItemWriter
~~~

Steps:

1. Spring Batch calls process(item) on ClassifierCompositeItemProcessor.
2. The composite passes the item to the Classifier.
3. The Classifier decides which delegate fits.
4. The composite calls process(item) on the selected delegate.
5. The delegate's result is returned to the Step.

For each item, the classifier can select a different processor. Two consecutive items in the same chunk do not have to pass through the same delegate.

## 3. Distinguishing ClassifierCompositeItemProcessor and CompositeItemProcessor

The two composites serve different purposes:

- **CompositeItemProcessor** chains multiple processors in sequence. The output of the previous processor becomes the input of the next processor.
- **ClassifierCompositeItemProcessor** picks one processor based on the item's classification result. Only the selected delegate is invoked for that item.

| Criterion | CompositeItemProcessor | ClassifierCompositeItemProcessor |
|---|---|---|
| Goal | Run a sequence of processors | Route to a single processor |
| Delegates called per item | Normally all delegates in the chain | One delegate selected by the classifier |
| Relationship between steps | Previous step output feeds next step | Branches are normally independent |
| Selection rule | Configuration order | Classifier |
| Suitable case | Normalize → validate → enrich | BUY → buy processor, SELL → sell processor |

Chain example:

~~~text
Input
  |
  v
NormalizeProcessor
  |
  v
ValidateProcessor
  |
  v
EnrichProcessor
  |
  v
Output
~~~

Routing example:

~~~text
Input
  |
  v
Classifier
  |
  +---- Type A --> Processor A
  |
  +---- Type B --> Processor B
  |
  +---- Type C --> Processor C
~~~

If each transaction type needs its own chain, the two mechanisms can be combined: the classifier picks a CompositeItemProcessor for that branch.

## 4. Creating Delegate ItemProcessors

Each delegate should focus on one business type. For example, all branches take Trade and return TradeResult:

~~~java
@Component
public class BuyTradeProcessor
        implements ItemProcessor<Trade, TradeResult> {

    private final TradingPolicy tradingPolicy;

    public BuyTradeProcessor(TradingPolicy tradingPolicy) {
        this.tradingPolicy = tradingPolicy;
    }

    @Override
    public TradeResult process(Trade trade) {
        tradingPolicy.validateBuy(trade);

        return new TradeResult(
                trade.getTradeId(),
                "BUY",
                trade.getAmount(),
                BigDecimal.ZERO);
    }
}
~~~

Processor for SELL:

~~~java
@Component
public class SellTradeProcessor
        implements ItemProcessor<Trade, TradeResult> {

    private final TradingPolicy tradingPolicy;
    private final FeeCalculator feeCalculator;

    public SellTradeProcessor(
            TradingPolicy tradingPolicy,
            FeeCalculator feeCalculator) {
        this.tradingPolicy = tradingPolicy;
        this.feeCalculator = feeCalculator;
    }

    @Override
    public TradeResult process(Trade trade) {
        tradingPolicy.validateSell(trade);
        BigDecimal fee = feeCalculator.calculate(trade.getAmount());

        return new TradeResult(
                trade.getTradeId(),
                "SELL",
                trade.getAmount(),
                fee);
    }
}
~~~

Processor for TRANSFER:

~~~java
@Component
public class TransferTradeProcessor
        implements ItemProcessor<Trade, TradeResult> {

    private final AccountService accountService;

    public TransferTradeProcessor(AccountService accountService) {
        this.accountService = accountService;
    }

    @Override
    public TradeResult process(Trade trade) {
        accountService.validateTransfer(
                trade.getSourceAccount(),
                trade.getTargetAccount(),
                trade.getAmount());

        return new TradeResult(
                trade.getTradeId(),
                "TRANSFER",
                trade.getAmount(),
                BigDecimal.ZERO);
    }
}
~~~

Because the delegates share the same input and output types, they fit into one ClassifierCompositeItemProcessor<Trade, TradeResult>. If branches produce different output types, standardize on a common output type or use an interface/sealed hierarchy so the writer can handle the results.

## 5. Configuring ClassifierCompositeItemProcessor

In Spring Batch, ClassifierCompositeItemProcessor lives in package org.springframework.batch.item.support. It is configured by providing a Classifier that returns delegate processors.

Java configuration example:

~~~java
@Bean
ClassifierCompositeItemProcessor<Trade, TradeResult> tradeProcessor(
        BuyTradeProcessor buyProcessor,
        SellTradeProcessor sellProcessor,
        TransferTradeProcessor transferProcessor) {

    ClassifierCompositeItemProcessor<Trade, TradeResult> composite =
            new ClassifierCompositeItemProcessor<>();

    composite.setClassifier(trade -> {
        return switch (trade.getType()) {
            case "BUY" -> buyProcessor;
            case "SELL" -> sellProcessor;
            case "TRANSFER" -> transferProcessor;
            default -> throw new IllegalArgumentException(
                    "Unsupported trade type: " + trade.getType());
        };
    });

    return composite;
}
~~~

The Classifier takes a Trade and returns the chosen ItemProcessor. The composite then invokes that delegate with the same item.

In some versions, setClassifier's generic signature represents the delegate using wildcards such as ItemProcessor<?, ? extends O>. Lambdas usually infer types when delegates share input/output types. If the compiler reports a generic error, declare the Classifier type explicitly per your Spring Batch API signature and keep delegates compatible with the common input/output types.

Inject delegates from the Spring container instead of calling new BuyTradeProcessor() inside the classifier. Dependency injection allows delegates to share configuration, transaction-aware services, metrics, and managed dependencies.

## 6. The Classifier Is the Branch Decision Component

The classifier's job is to classify an item and return a delegate. It should not implement all the business logic of the branch. Keep classify logic simple, deterministic, and easy to test.

You can extract the classifier into its own class:

~~~java
public class TradeTypeClassifier
        implements Classifier<Trade, ItemProcessor<?, ? extends TradeResult>> {

    private final ItemProcessor<Trade, TradeResult> buyProcessor;
    private final ItemProcessor<Trade, TradeResult> sellProcessor;
    private final ItemProcessor<Trade, TradeResult> transferProcessor;

    public TradeTypeClassifier(
            ItemProcessor<Trade, TradeResult> buyProcessor,
            ItemProcessor<Trade, TradeResult> sellProcessor,
            ItemProcessor<Trade, TradeResult> transferProcessor) {
        this.buyProcessor = buyProcessor;
        this.sellProcessor = sellProcessor;
        this.transferProcessor = transferProcessor;
    }

    @Override
    public ItemProcessor<?, ? extends TradeResult> classify(Trade trade) {
        return switch (trade.getType()) {
            case "BUY" -> buyProcessor;
            case "SELL" -> sellProcessor;
            case "TRANSFER" -> transferProcessor;
            default -> throw new IllegalArgumentException(
                    "Unsupported trade type: " + trade.getType());
        };
    }
}
~~~

Declaring the classifier bean:

~~~java
@Bean
Classifier<Trade, ItemProcessor<?, ? extends TradeResult>> tradeClassifier(
        BuyTradeProcessor buyProcessor,
        SellTradeProcessor sellProcessor,
        TransferTradeProcessor transferProcessor) {

    return new TradeTypeClassifier(
            buyProcessor, sellProcessor, transferProcessor);
}
~~~

Then configuring the composite:

~~~java
@Bean
ClassifierCompositeItemProcessor<Trade, TradeResult> tradeProcessor(
        Classifier<Trade, ItemProcessor<?, ? extends TradeResult>> tradeClassifier) {

    ClassifierCompositeItemProcessor<Trade, TradeResult> composite =
            new ClassifierCompositeItemProcessor<>();
    composite.setClassifier(tradeClassifier);
    return composite;
}
~~~

Exact generic signatures for Classifier and the setter must match your Spring Batch/Spring Core version. The example illustrates separating responsibilities: the classifier only picks the processor; delegates perform the processing.

## 7. Handling Unsupported Types

The classifier needs explicit behavior when it does not recognize an item type. Three common options exist:

1. Throw an exception so the Step fails or applies a skip policy.
2. Route to a fallback processor dedicated to recording unsupported items.
3. Return null from a delegate processor if business logic wants to filter that item.

Do not return null from the classifier when the API requires a delegate processor. A null delegate can cause a NullPointerException when the composite tries to invoke process().

Fallback example:

~~~java
@Component
public class UnsupportedTradeProcessor
        implements ItemProcessor<Trade, TradeResult> {

    @Override
    public TradeResult process(Trade trade) {
        return TradeResult.rejected(
                trade.getTradeId(),
                "UNSUPPORTED_TYPE");
    }
}
~~~

The classifier can return the fallback for any unknown type:

~~~java
default -> unsupportedTradeProcessor;
~~~

Choosing fallback versus failing depends on the data contract. If a new type could alter monetary semantics or transaction states, stopping the Job is usually safer than silently emitting rejected records. If the system requires continuing and auditing every record, the fallback must clearly record the reason and ensure the writer handles that status properly.

## 8. Filtering Items in a Delegate Processor

A delegate ItemProcessor can return null to filter an item. When it does, the item is not forwarded to the writer and Spring Batch increments the filter count.

Example:

~~~java
@Component
public class BuyTradeProcessor
        implements ItemProcessor<Trade, TradeResult> {

    @Override
    public TradeResult process(Trade trade) {
        if (trade.getAmount().signum() <= 0) {
            return null;
        }
        return mapBuyTrade(trade);
    }
}
~~~

Returning null is an intentional filter decision, not a skip exception. If a delegate throws an exception, the Step only skips the item when the exception is configured as skippable and the skip limit has not been exceeded.

| Delegate Result | Behavior |
|---|---|
| Returns object | Item continues to writer |
| Returns null | Item is filtered, does not reach writer |
| Throws skippable exception | Item is skipped per fault-tolerance policy |
| Throws non-skippable exception | Step fails, unless handled by another policy |

Do not use null to represent unsupported errors if auditing or reprocessing is needed; filtering does not record an exclusion reason on its own.

## 9. Combining a Classifier with Per-Branch CompositeItemProcessors

Sometimes each item type needs multiple sequential steps. For example, BUY needs normalize, validate, and enrich; SELL needs normalize, validate, and fee calculation.

You can create a CompositeItemProcessor per branch and let the classifier select the corresponding composite:

~~~text
                    Classifier
                   /          \
                BUY            SELL
                 |               |
                 v               v
          Composite BUY    Composite SELL
             |   |   |        |   |   |
             v   v   v        v   v   v
          Normalize       Normalize
          Validate        Validate
          Enrich          Fee calculation
~~~

Example declaring the BUY branch:

~~~java
@Bean
CompositeItemProcessor<Trade, TradeResult> buyPipeline(
        NormalizeBuyProcessor normalize,
        ValidateBuyProcessor validate,
        EnrichBuyProcessor enrich) throws Exception {

    CompositeItemProcessor<Trade, TradeResult> composite =
            new CompositeItemProcessor<>();
    composite.setDelegates(List.of(normalize, validate, enrich));
    composite.afterPropertiesSet();
    return composite;
}
~~~

The example assumes processors have compatible intermediate types. If NormalizeBuyProcessor returns NormalizedBuy instead of Trade, subsequent delegates must accept the right intermediate type; CompositeItemProcessor generics do not always catch every mismatch at compile time because the delegate list uses wildcards. Configure type chains clearly and test them.

The classifier can return ItemProcessor<Trade, TradeResult> where the actual delegate is a CompositeItemProcessor<Trade, TradeResult>. That way each branch has its own pipeline while the Step still sees a single composite processor.

## 10. Using a Map to Route by Type

When there are many item types, delegates can be stored in a Map instead of writing a long switch:

~~~java
@Bean
Classifier<Trade, ItemProcessor<?, ? extends TradeResult>> tradeClassifier(
        BuyTradeProcessor buy,
        SellTradeProcessor sell,
        TransferTradeProcessor transfer,
        UnsupportedTradeProcessor fallback) {

    Map<String, ItemProcessor<Trade, TradeResult>> processors = Map.of(
            "BUY", buy,
            "SELL", sell,
            "TRANSFER", transfer);

    return trade -> processors.getOrDefault(trade.getType(), fallback);
}
~~~

A map makes adding new types an explicit configuration change. Guard against null keys and normalize types if source data does not guarantee consistent casing.

Normalization example:

~~~java
String type = trade.getType() == null
        ? ""
        : trade.getType().trim().toUpperCase(Locale.ROOT);

return processors.getOrDefault(type, fallback);
~~~

Do not use the machine's default locale to normalize technical type codes. Locale.ROOT ensures results do not vary with server language settings.

If item types are defined by an enum, use the enum as the map key or parse strings to the enum in a validation step before classification. This reduces typos and gives compiler assistance.

## 11. Classifying by Multiple Attributes

A classifier does not have to rely on just one field. It can combine type, source system, region, or status:

~~~java
return trade -> {
    if ("ERP".equals(trade.getSourceSystem())
            && "BUY".equals(trade.getType())) {
        return erpBuyProcessor;
    }

    if ("MOBILE".equals(trade.getSourceSystem())
            && "BUY".equals(trade.getType())) {
        return mobileBuyProcessor;
    }

    if ("SELL".equals(trade.getType())) {
        return sellProcessor;
    }

    return unsupportedProcessor;
};
~~~

As conditions grow, consider creating an immutable routing key:

~~~java
public record TradeRoute(String sourceSystem, TradeType type) {
}
~~~

The classifier can build a key from the item and look up Map<TradeRoute, ItemProcessor<...>>. This separates key normalization from business processing and makes individual routes easy to test.

If conditions have precedence, document that order explicitly. Placing a general condition before a specific one can steal items meant for the specific branch.

## 12. Classifying by Class Type

Items do not always carry a type field. If a reader emits multiple subclasses, the classifier can choose a processor by class:

~~~java
public sealed interface Payment
        permits CardPayment, BankTransfer {
}

public record CardPayment(
        String paymentId,
        BigDecimal amount) implements Payment {
}

public record BankTransfer(
        String paymentId,
        BigDecimal amount,
        String destinationAccount) implements Payment {
}
~~~

The classifier can inspect the runtime type:

~~~java
return payment -> {
    if (payment instanceof CardPayment) {
        return cardPaymentProcessor;
    }
    if (payment instanceof BankTransfer) {
        return bankTransferProcessor;
    }
    throw new IllegalArgumentException(
            "Unsupported payment class: " + payment.getClass().getName());
};
~~~

If the system has many subclasses, you can use a hierarchy-aware classifier or a class-keyed registry. Define behavior for new subclasses and unregistered classes. Avoid using getClass().getSimpleName() as a routing key if class names may change during refactoring.

## 13. Classifiers Should Be Lightweight and Side-Effect-Free

The classifier is called for every item requiring routing. Therefore, keep it fast, deterministic, and free of side effects.

Avoid:

- Calling a REST API to choose a processor per item when the route can come from data or a cache.
- Querying the database repeatedly for every item just to pick a branch.
- Mutating shared state inside classify().
- Creating a new delegate processor for every item.
- Writing business data inside the classifier.

Classifiers should rely on attributes already on the item or a pre-configured immutable registry. If branch selection requires external lookups, consider enriching items in a separate step or using a cache with appropriate TTL and thread safety.

Creating a new delegate for every item forfeits dependency injection, increases allocations, and complicates lifecycle management. Inject Spring-managed delegates instead.

## 14. Thread Safety of the Classifier and Delegates

In a multi-threaded Step or when multiple JobExecutions run concurrently, the same singleton classifier/delegate can receive concurrent calls. The classifier and all delegates must be thread-safe.

Principles:

- Keep the classifier stateless or reading only immutable configuration.
- Do not hold currentTrade in a field.
- Do not mutate route Maps after the Step starts.
- Avoid mutable shared state in delegate processors.
- Services used by delegates must be thread-safe.
- If a delegate holds StepExecution-scoped state, use an appropriate scope while still evaluating multi-threading within the same StepExecution.

Example immutable route map:

~~~java
private final Map<String, ItemProcessor<Trade, TradeResult>> routes;

public TradeTypeClassifier(
        Map<String, ItemProcessor<Trade, TradeResult>> routes) {
    this.routes = Map.copyOf(routes);
}
~~~

Map.copyOf protects the map structure from modification through the passed reference. It does not make the processors stored in the map thread-safe; each delegate must still be designed accordingly.

If a delegate holds file handles, cursors, or checkpoints, do not share the same instance across workers unless the implementation supports it. Use separate StepScope/partition-scoped processors when state belongs to individual workers.

## 15. Skip and Retry Across Branches

ClassifierCompositeItemProcessor sits inside the Step's processor pipeline. Therefore, exceptions from delegates are treated as process-phase errors and governed by the Step's fault-tolerance policy.

Example:

~~~java
return new StepBuilder("processTradesStep", jobRepository)
        .<Trade, TradeResult>chunk(100, transactionManager)
        .reader(tradeReader)
        .processor(classifierCompositeItemProcessor)
        .writer(tradeWriter)
        .faultTolerant()
        .skip(InvalidTradeException.class)
        .skipLimit(50)
        .retry(TemporaryPricingException.class)
        .retryLimit(3)
        .build();
~~~

If BuyTradeProcessor throws InvalidTradeException, the item is handled per the skip policy. If SellTradeProcessor throws TemporaryPricingException, the Step can retry per the configured policy.

Do not use the same exception type for permanent business errors and transient infrastructure errors if they require different policies. Well-defined exceptions enable accurate skip/retry selection.

Retry can re-invoke the delegate or related processing depending on fault-tolerance mechanics. The classifier must yield a consistent route for the same item and routing data throughout execution. Do not alter routes based on mutable global state between retry attempts.

## 16. Filter, Skip, and Route Fallback

These three behaviors are distinct:

- **Route fallback:** the classifier picks a processor dedicated to handling unsupported types.
- **Filter:** a delegate returns null; the item is intentionally excluded and never reaches the writer.
- **Skip:** a delegate throws a configured skippable exception; Spring Batch records a skip count and invokes relevant listeners.

Do not use fallback to hide classification errors if new item types should halt the Job. Do not use filtering for invalid data that needs auditing. Do not use skipping just because an item type lacks a processor; that is a routing/configuration issue, not necessarily an item error.

## 17. Integrating with a Step

ClassifierCompositeItemProcessor is configured like a standard ItemProcessor:

~~~java
@Bean
Step processTradesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Trade> tradeReader,
        ClassifierCompositeItemProcessor<Trade, TradeResult> tradeProcessor,
        ItemWriter<TradeResult> tradeWriter) {

    return new StepBuilder("processTradesStep", jobRepository)
            .<Trade, TradeResult>chunk(200, transactionManager)
            .reader(tradeReader)
            .processor(tradeProcessor)
            .writer(tradeWriter)
            .build();
}
~~~

The Step does not need to know how many delegates exist or which field the classifier inspects. It simply sees one ItemProcessor<Trade, TradeResult>.

This keeps Step configuration concise and separates routing from transaction/write behavior. If one transaction type needs a completely different writer, the classifier processor does not pick the writer itself. In that case you can:

- Normalize all branches to one output type and use one writer.
- Attach a discriminator to the output so the writer decides how to persist it.
- Use a separate classifier writer if the problem truly requires routing at the write stage.
- Split into separate Steps/flows if each type has its own lifecycle or transaction.

Do not put writer-selection logic inside the processor just to trigger write side effects. The processor should produce output; the writer is responsible for persistence.

## 18. When Should You Split into Multiple Steps?

ClassifierCompositeItemProcessor works well when branches belong to the same Step and share a reader/writer/transaction boundary. If each item type has significantly different operational needs, splitting Steps may be clearer.

Consider multiple Steps or flows when:

- Each type uses a different transaction manager or database.
- Each type needs different retry/skip policies.
- One branch needs its own resource or chunk size.
- Branches must run independently in parallel or on separate schedules.
- Each data type must be restartable independently.
- Separate status reporting per type is required.

Classifying in a processor does not create a separate StepExecution per branch. All delegates still execute within the same StepExecution, chunk lifecycle, and Step fault-tolerance configuration.

If branches require distinct error policies, you can use distinct exception types with exception-classified policies, or split into Steps for independent configuration and simpler operations.

## 19. Logging and Metrics per Branch

When routing multiple item types, you need visibility into how many items each delegate handles and which branch throws errors.

You can record:

- Route key or item type.
- Items received by each delegate.
- Items filtered per branch.
- Errors and skips by exception type.
- Processing duration per delegate.
- Items successfully written by output type.

Metrics collectors must be thread-safe if the Step runs concurrently. Do not use a shared mutable HashMap to increment counters from multiple threads. Use Micrometer Counter/Timer or an appropriate concurrent collector.

Do not rely solely on classifier logs to assume items were written successfully. A delegate may return a result while the writer or transaction later fails. Distinguish processor invocation, writer invocation, and commit.

## 20. Testing the Classifier Independently

Because the classifier is routing logic, it can be unit tested without launching a Job.

Example:

~~~java
@Test
void selectsProcessorByTradeType() {
    ItemProcessor<Trade, TradeResult> buy = trade -> buyResult(trade);
    ItemProcessor<Trade, TradeResult> sell = trade -> sellResult(trade);
    ItemProcessor<Trade, TradeResult> transfer = trade -> transferResult(trade);

    TradeTypeClassifier classifier =
            new TradeTypeClassifier(buy, sell, transfer);

    assertSame(buy, classifier.classify(tradeOfType("BUY")));
    assertSame(sell, classifier.classify(tradeOfType("SELL")));
    assertSame(transfer, classifier.classify(tradeOfType("TRANSFER")));
}
~~~

Check:

- Every supported type selects the right delegate.
- Unsupported types throw an exception or pick the fallback per policy.
- Null/blank type values are handled explicitly.
- Case normalization works properly.
- Multi-attribute conditions honor the right precedence.
- The classifier does not instantiate a new delegate on every classify call.

## 21. Testing ClassifierCompositeItemProcessor

Unit tests for the composite verify that the selected delegate is actually invoked and its output is returned:

~~~java
@Test
void delegatesItemToSelectedProcessor() throws Exception {
    ItemProcessor<Trade, TradeResult> buy = mock(ItemProcessor.class);
    ItemProcessor<Trade, TradeResult> sell = mock(ItemProcessor.class);

    Trade trade = tradeOfType("BUY");
    TradeResult expected = new TradeResult(
            trade.getTradeId(), "BUY", trade.getAmount(), BigDecimal.ZERO);

    when(buy.process(trade)).thenReturn(expected);

    ClassifierCompositeItemProcessor<Trade, TradeResult> composite =
            new ClassifierCompositeItemProcessor<>();
    composite.setClassifier(item ->
            "BUY".equals(item.getType()) ? buy : sell);

    assertSame(expected, composite.process(trade));
    verify(buy).process(trade);
    verifyNoInteractions(sell);
}
~~~

This test verifies a BUY item only goes through the buy processor. Add tests for remaining branches and cases where the classifier returns a fallback or throws an exception.

## 22. Step Integration Testing

Unit testing routing does not prove chunks, transactions, skips, retries, and writers work when running a Job. Write a Step integration test with a fixture containing multiple item types:

~~~text
Input:
  T-001 BUY
  T-002 SELL
  T-003 TRANSFER
  T-004 BUY

Routing:
  T-001 -> BuyTradeProcessor
  T-002 -> SellTradeProcessor
  T-003 -> TransferTradeProcessor
  T-004 -> BuyTradeProcessor

Expected output:
  4 TradeResults with matching route/type
~~~

With Spring Batch Test, you can run the Step or Job and assert:

- Job/Step finishes with the expected status.
- readCount and writeCount match.
- Outputs of each type are produced by the right delegate.
- Filtered items do not appear in the output.
- Exceptions in a delegate are skipped/retried per policy.
- Writer produces no duplicates on retry/restart.

If delegates have external dependencies such as a pricing API or account service, use mocks or stubs for deterministic results. Do not depend on production services in unit tests.

## 23. Common Mistakes

**Confusing classifier composite with processor chain:** ClassifierCompositeItemProcessor only picks one delegate per item; it does not run all delegates sequentially.

**Missing default branch:** a new item type can cause the composite to receive a null delegate and fail obscurely. Choose fail-fast or an explicit fallback.

**Returning null from the classifier:** null is not how you filter items; return a valid delegate or throw an exception.

**Instantiating a new processor inside classify():** forfeits dependency injection, increases allocations, and complicates lifecycle control. Inject managed delegates.

**Incompatible generic input/output:** delegates must accept compatible input and return output compatible with O of the composite. Internal processor chains must also match intermediate types.

**Putting too much business logic in the classifier:** routing becomes hard to test and maintain. Only classify in the classifier; keep business logic in delegates.

**Using one fallback to hide every new type:** critical data may be mishandled. Choose policy based on the data contract.

**Assuming each branch has its own transaction or Step:** all composite delegates still run inside the same StepExecution and chunk lifecycle.

**Ignoring thread safety:** singleton classifiers and delegates can be called concurrently. Keep state immutable or synchronize shared state.

**Not testing retries:** the classifier must pick consistent routes when the same item is reprocessed.

**Routing on unnormalized strings:** BUY, buy, and strings with whitespace may enter different branches if input is not normalized.

## Conclusion

ClassifierCompositeItemProcessor enables choosing a suitable ItemProcessor for each item based on the result of a Classifier. It fits when a Step handles multiple data types where each type needs distinct business rules. Separate delegates by responsibility, inject them from the Spring container, and keep the classifier lightweight, deterministic, and side-effect-free. Clearly distinguish this routing mechanism from CompositeItemProcessor, which chains multiple processors sequentially; if a branch needs multiple steps, place a composite as that branch's delegate. Define behavior for unsupported types, control filter/skip/retry behavior, ensure thread safety, and test both standalone routing and Step integration to verify exact delegates, outputs, transactions, and restart behavior.
