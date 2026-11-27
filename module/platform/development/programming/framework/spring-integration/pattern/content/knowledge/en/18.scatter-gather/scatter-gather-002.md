# Gathering Results from Parallel Branches

## 1. Context: multiple processing branches, one combined decision

In the **Scatter gather** chapter of the **SPRING_INTEGRATION_PATTERN** module, we learn how to implement Enterprise Integration Patterns with **Spring Integration** to build loosely coupled and extensible message flows. A message can be sent to multiple independent processing branches; the branches execute business logic, return results, and are then combined into a single response. This pattern pairs naturally with Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation, and testing.

Suppose a system needs to **find the best shipping quote** for an order. Each request is queried concurrently across three suppliers:

- **warehouseSupplier**: internal warehouse quote.
- **partnerSupplier**: shipping partner quote.
- **backupSupplier**: backup quote.

Each supplier returns a price and a status. The application wants to receive **one QuoteReport** containing all three outcomes, clearly indicating which supplier did not respond or declined to quote, and selecting the lowest valid price.

~~~mermaid
flowchart LR
    Q["QuoteRequest"] --> S["Scatter"]
    S --> A["Warehouse supplier"]
    S --> B["Partner supplier"]
    S --> C["Backup supplier"]
    A -->|"SupplierOutcome"| G["Gather / Aggregator"]
    B -->|"SupplierOutcome"| G
    C -->|"SupplierOutcome"| G
    G --> R["QuoteReport + best offer"]
~~~

If the suppliers have different latencies, responses may arrive in the order **partner → backup → warehouse**, rather than the request dispatch order. Gather must identify **which replies belong to the same request**, know when completion criteria are met, and avoid mixing results across different customers.

**Learning objectives**

1. Distinguish **Scatter**, **Gather**, and **Aggregator**; distinguish fan-out from true parallel execution.
2. Understand the two styles, **auction** and **distribution**, in Spring Integration.
3. Design correlationId, sequenceNumber, sequenceSize, and replyChannel so Gather receives all results in the right group.
4. Write Java DSL using ScatterGatherHandler, RecipientListRouter, and Aggregator, with branches running on a bounded Executor.
5. Define release strategy, gatherTimeout, groupTimeout, partial results, and late arrivals.
6. Handle a failing branch without automatically losing all other results, while not masking system errors.
7. Test full result collection, arbitrary reply arrival order, concurrent requests, missing replies, duplicates, and retries.

## 2. What is Gather actually responsible for?

**Scatter** sends a request to multiple recipients or sub-flows. **Gather** receives the corresponding replies and combines them into one output per the business contract.

~~~text
Request
  |
  +-- scatter --> Supplier A -- reply A --+
  +-- scatter --> Supplier B -- reply B --+--> Gather --> Report
  +-- scatter --> Supplier C -- reply C --+
~~~

Gather typically performs four tasks:

1. **Correlation**: identifies which replies belong to the same request.
2. **Accumulation**: holds replies in a MessageGroup or equivalent state store.
3. **Release**: decides whether enough information has arrived to complete the group.
4. **Aggregation**: transforms the replies into a single meaningful final result.

Gather **does not automatically** verify that all external systems committed, does not automatically prevent duplicate effects, and does not automatically know whether a silent supplier is an error or a valid result. Those must be defined by business rules and error/recovery policies.

### 2.1. Gather is different from merely wiring messages together

If three branches send into the same channel and a consumer receives them one by one, that is only **collecting messages in one place**. To produce a correct response, the consumer needs to know:

- Which original request generated these replies?
- How many replies are expected?
- Is the second reply arriving a duplicate from the same supplier?
- When should we stop waiting?
- Does a failed supplier count as having replied?
- Can we pick the first price immediately or must we wait for all quotes?

**Gather** is a contract-driven synchronization point for results, not just a converging channel.

### 2.2. Scatter-Gather vs. Splitter-Aggregator

| Aspect | Scatter-Gather | Splitter-Aggregator |
| --- | --- | --- |
| Input | One request querying multiple recipients | One payload containing multiple items to split |
| Scatter/Split | Sends the request to multiple suppliers/branches | Creates child messages from a collection or payload |
| Processing branches | Usually handle different perspectives/services | Usually process items of the same kind |
| Gather/Aggregate | Merges supplier replies | Combines child results into a batch result |
| Correlation | Links replies back to the right request | Links children back to the right parent message |
| Timeout | Important for slow suppliers / lost replies | Important for lost or failing children |

Both can use AggregatingMessageHandler. However, **one request broadcast to multiple suppliers** is different from **a list of 100 items split by a Splitter**; do not swap pattern names and ignore semantics.

## 3. Two Scatter-Gather styles supported by Spring Integration

Spring Integration provides **ScatterGatherHandler** as a request/reply endpoint coordinating a request dispatcher and an AggregatingMessageHandler. There are two main variants:

### 3.1. Auction: broadcasting the request to all subscribers

The **auction** variant uses a **PublishSubscribeChannel**. Each eligible subscriber receives a copy of the request message; all are invited to reply to select or aggregate a result.

Example: three shipping carriers are all asked for quotes to pick the best offer.

~~~mermaid
flowchart TB
    I["One request"] --> P["PublishSubscribeChannel"]
    P --> S1["Subscriber A"]
    P --> S2["Subscriber B"]
    P --> S3["Subscriber C"]
    S1 --> G["Gather"]
    S2 --> G
    S3 --> G
~~~

**Important note:** A PublishSubscribeChannel without a TaskExecutor invokes subscribers on the **sender's thread** by default. Just having three subscribers does not mean they run in parallel; true parallelism requires an appropriate Executor or an async boundary within each sub-flow.

When the Aggregator needs sequence metadata, set **applySequence(true)** on the PublishSubscribeChannel if configuring the channel directly. With the Scatter-Gather DSL from Spring Integration **6.0**, the framework conveniently sets applySequence=true for the variants it creates; if building a router/channel manually or using an older version, verify the actual configuration.

### 3.2. Distribution: selecting recipients conditionally

The **distribution** variant uses a **RecipientListRouter**. Only recipients whose selectors match receive the request.

Example: international orders also query customsSupplier; domestic orders only query two carriers.

~~~mermaid
flowchart LR
    I["QuoteRequest"] --> R["RecipientListRouter"]
    R -->|"Always receives"| A["Warehouse"]
    R -->|"Always receives"| B["Partner"]
    R -->|"International only"| C["Customs"]
    A --> G["Gather"]
    B --> G
    C --> G
~~~

**How many replies are expected?** If customs is not selected, Gather must expect **2**, not 3. That is why RecipientListRouter's applySequence matters: sequenceSize needs to reflect **the number of recipients actually selected**, not the maximum number of mappings.

### 3.3. Choosing auction or distribution?

| Need | Usually appropriate choice |
| --- | --- |
| Every supplier needs to see the request | Auction / PublishSubscribeChannel |
| Recipients participate only when a selector matches | Distribution / RecipientListRouter |
| Need to pick the lowest price from invited suppliers | Either; Gather processes results |
| Need multiple threads on your own | Executor on PublishSubscribeChannel or each branch |
| Need results from every mandatory branch | Release by expected reply count, explicit fail/timeout |
| Tolerate some suppliers not responding | Terminal failure outcome or partial release with status |

Do not use RecipientListRouter just to mimic a Splitter breaking down items in a list when the real need is item-by-item processing. Choosing the right pattern makes correlation and per-reply responsibilities clearer.

## 4. Correlation, sequence, and replyChannel are Gather's contract

For the Aggregator to accurately match three quotes, each reply must retain metadata linking it to the parent request.

| Information | Role |
| --- | --- |
| **requestId** | Stable business identifier across retries |
| **correlationId** | Groups reply messages within one Scatter-Gather execution |
| **sequenceNumber** | Logical recipient/branch position in the set |
| **sequenceSize** | Number of replies the group expects to receive |
| **replyChannel** | Destination for the branch to send its reply back to Gather |
| **errorChannel** | Destination for handling request/branch errors |
| **supplierId** | Logical identity of the result source, for deduplication and audit |

If three suppliers are selected:

~~~text
Request req-701:
  warehouse -> correlation=G-701, sequenceNumber=1, sequenceSize=3
  partner   -> correlation=G-701, sequenceNumber=2, sequenceSize=3
  backup    -> correlation=G-701, sequenceNumber=3, sequenceSize=3
~~~

If a new request **req-702** runs concurrently, it must have its own correlation group, e.g., G-702. Never use a fixed key like "quotes" for all requests, because results from different customers could be mixed.

### 4.1. Each supplier's replyChannel

In **ScatterGatherHandler**, the framework creates a reply destination for Gather (if no external gatherChannel is provided) and enriches the scattered messages with headers directing replies back there.

Therefore, in each recipient sub-flow:

- To return a result to Gather, the final endpoint must **produce a non-null reply**.
- Do not explicitly configure outputChannel elsewhere if you want the framework to use the request's replyChannel.
- If transferring messages over a broker or manually recreating Messages, verify **preservation of correlation, sequence, and reply metadata** based on the adapter's serialization capabilities.
- If a one-way handler returns null, Gather will **have no reply** from that branch; the group may never complete.

Spring Integration documentation also notes that an explicit **gatherChannel** can be configured so suppliers send replies to that channel. This is an architectural option; it is not strictly necessary when local sub-flows can reply via headers.

### 4.2. Sequence is not an idempotency key

SequenceNumber=2 only states that this is **the reply at position 2** in the group; it does not prove the supplier succeeded, nor does it guarantee the event was sent only once.

For retries:

~~~text
idempotencyKey = trustedTenantId + ":" + requestId + ":" + supplierId
~~~

A retry from partner reuses requestId and supplierId to avoid repeating side-effectful operations. However, a brand-new, intentional price comparison round may need a new requestId even if the sku stays the same.

### 4.3. What are the consequences of lost headers or wrong correlation?

- Missing proper **correlationId**: replies are not grouped together.
- **sequenceSize=0/missing** with the default release strategy: Gather may not know when it has enough.
- Each branch generates a new correlationId: no group ever reaches the required count.
- A branch drops **replyChannel**: the reply never returns to Gather.
- A branch returns a message without preserving required request metadata: may cause routing errors or timeouts.
- Copying client-supplied headers unverified: may leak errors/replies to unintended channels.

The framework's correlation IDs serve **combining messages within an execution**; if reconciliation and crash recovery across restarts are needed, you must add a **business requestId** and persistent state.

## 5. When is Gather allowed to release?

With three mandatory branches, the usual rule is **wait for all three replies**. By default, Aggregator can use SimpleSequenceSizeReleaseStrategy: comparing group size against sequence metadata to decide release.

~~~mermaid
flowchart TD
    A["Reply arrives at Gather"] --> C["Find MessageGroup by correlationId"]
    C --> S["Store reply in MessageGroupStore"]
    S --> D{"ReleaseStrategy satisfied?"}
    D -->|"Not yet"| W["Keep waiting"]
    D -->|"Yes"| G["MessageGroupProcessor / Aggregation"]
    G --> O["QuoteReport"]
~~~

### 5.1. Wait for all vs. pick a "good enough" subset

| Release policy | When to use | Trade-off |
| --- | --- | --- |
| **All N replies** | All suppliers mandatory or full audit required | Latency depends on the slowest branch |
| **Minimum K replies** | Enough data to make a controlled decision | May miss a better quote arriving late |
| **At least one qualifying offer** | Fast decision toward a clear target | Must prove an early result is good enough |
| **Timeout expired** | Cannot hold the request indefinitely | Partial/incomplete must be explicitly disclosed |

**Do not replace the all-N rule with size() >= K just to avoid timeouts** if the business requires all N. A K-of-N strategy must have an explicit contract regarding missing suppliers, report status, late replies, and the possibility that a better price arrives later.

### 5.2. Does a failure outcome count as a reply?

Yes, if the contract defines that each supplier returns **a terminal SupplierOutcome**:

- SUCCESS, with a price.
- UNAVAILABLE, unable to provide a price.
- REJECTED, valid business rejection.

Then three outcomes (one of which is UNAVAILABLE) can still complete the group at **3/3**. Gather returns a QuoteReport with **2 prices and 1 unavailable supplier**, rather than pretending all three quotes were valid.

Conversely, if a branch just throws an exception and returns no message, Gather may **wait with missing replies**. An ErrorMessage on errorChannel does not automatically count as a SupplierOutcome in the group.

### 5.3. Do not confuse a complete group with all side effects committed

The Aggregator only knows the replies it **received**. A supplier might return ACCEPTED without having truly completed the external business action. If Scatter-Gather is used for state-changing operations (not just fetching quotes), you must clearly define the semantics of each reply and idempotency on each branch.

## 6. Java 17 example: defining request, outcome, and report

The following example illustrates querying three suppliers for quotes. We define typed outcomes so even **a branch declining to quote** returns a message to Gather instead of staying silent.

### 6.1. Request and results

~~~java
import java.math.BigDecimal;
import java.util.List;

record QuoteRequest(
        String requestId,
        String sku,
        int quantity) {
    QuoteRequest {
        if (requestId == null || requestId.isBlank()
                || sku == null || sku.isBlank()
                || quantity <= 0 || quantity > 1000) {
            throw new IllegalArgumentException("INVALID_QUOTE_REQUEST");
        }
    }
}

record SupplierOutcome(
        String requestId,
        String supplierId,
        String status,
        BigDecimal totalPriceVnd,
        String errorCode) {

    static SupplierOutcome success(
            QuoteRequest request,
            String supplierId,
            BigDecimal price) {
        if (price == null || price.signum() <= 0) {
            throw new IllegalArgumentException("INVALID_SUPPLIER_PRICE");
        }
        return new SupplierOutcome(
                request.requestId(), supplierId,
                "SUCCESS", price, null);
    }

    static SupplierOutcome unavailable(
            QuoteRequest request,
            String supplierId,
            String errorCode) {
        return new SupplierOutcome(
                request.requestId(), supplierId,
                "UNAVAILABLE", null, errorCode);
    }
}

record QuoteReport(
        String requestId,
        int expectedSuppliers,
        int receivedOutcomes,
        String reportStatus,
        SupplierOutcome bestOffer,
        List<SupplierOutcome> outcomes) {}
~~~

**Sample contract:**

- SUCCESS carries a positive **totalPriceVnd**.
- UNAVAILABLE is a **business-meaningful** terminal result with no price and an errorCode.
- The Report distinguishes full responses (**receivedOutcomes=3**) from full valid quotes (**maybe only 2 SUCCESS**).
- If all are UNAVAILABLE, **bestOffer=null** intentionally and reportStatus must clearly state NO_OFFER.

In production, use enums instead of status strings and validate supplierId against an allowlist. requestId must be stable for one logical request; when a customer intentionally requests a new quote, a new requestId can be issued.

### 6.2. Port for each branch

~~~java
interface SupplierQuotePort {
    SupplierOutcome quote(QuoteRequest request);
}
~~~

The port can be implemented via HTTP, database, calculation model, or adapter. The quote() method must have a clear error contract:

- No price available: return SupplierOutcome UNAVAILABLE per business conditions.
- Invalid request data: fail at ingress before scatter or use a classified domain error.
- Timeout/infrastructure: decide on per-supplier retry or return a failure outcome once concluded terminal.
- Never return null directly because Gather needs a branch reply.

## 7. Gather: picking the lowest quote while keeping all outcomes

A Gather should not just take the first arriving message or keep only the lowest price and forget the other suppliers. To audit and explain the decision, return a **QuoteReport** containing a deterministically sorted list of outcomes.

~~~java
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.springframework.integration.store.MessageGroup;

final class QuoteReportFactory {
    private static final int EXPECTED_SUPPLIERS = 3;

    private QuoteReportFactory() {}

    static QuoteReport fromGroup(MessageGroup group) {
        List<SupplierOutcome> outcomes = group.getMessages().stream()
                .map(message -> (SupplierOutcome) message.getPayload())
                .sorted(Comparator.comparing(
                        SupplierOutcome::supplierId))
                .toList();

        if (outcomes.size() != EXPECTED_SUPPLIERS) {
            throw new IllegalStateException("INCOMPLETE_SUPPLIER_GROUP");
        }

        String requestId = outcomes.get(0).requestId();
        Set<String> identities = new HashSet<>();
        for (SupplierOutcome outcome : outcomes) {
            if (!requestId.equals(outcome.requestId())) {
                throw new IllegalStateException("MIXED_REQUEST_IDS");
            }
            if (!identities.add(outcome.supplierId())) {
                throw new IllegalStateException("DUPLICATE_SUPPLIER_REPLY");
            }
        }

        SupplierOutcome best = outcomes.stream()
                .filter(outcome -> "SUCCESS".equals(outcome.status()))
                .min(Comparator
                        .comparing(SupplierOutcome::totalPriceVnd)
                        .thenComparing(SupplierOutcome::supplierId))
                .orElse(null);

        long successCount = outcomes.stream()
                .filter(outcome -> "SUCCESS".equals(outcome.status()))
                .count();
        String reportStatus = successCount == EXPECTED_SUPPLIERS
                ? "COMPLETE"
                : best == null ? "NO_OFFER" : "PARTIAL_SUPPLIER_FAILURE";

        return new QuoteReport(
                requestId,
                EXPECTED_SUPPLIERS,
                outcomes.size(),
                reportStatus,
                best,
                List.copyOf(outcomes));
    }
}
~~~

**Design points of the example:**

1. Requires **exactly three terminal outcomes**, one from each supplier.
2. Two messages with the same supplierId cause a duplicate error instead of silently being treated as two quote sources.
3. When all 3 outcomes are present but one supplier is UNAVAILABLE, reportStatus is PARTIAL_SUPPLIER_FAILURE; still picks the lowest price **among valid offers**.
4. When all three are UNAVAILABLE, reportStatus is NO_OFFER, with no bestOffer.
5. Arrival order does not affect the result because outcomes are sorted by supplierId.

This is a **processor for a complete group**. If you want to emit a report when only 2/3 replies arrive due to timeout, you must design a **separate processor for partial groups** based on the expected supplier manifest and return status INCOMPLETE; do not reuse the code above and simply replace EXPECTED_SUPPLIERS with the number of arrived messages.

### 7.1. Default release strategy does not check every invariant

The Aggregator's ReleaseStrategy decides when a group is eligible for release; it does not replace all validations in QuoteReportFactory. In Spring Integration 5.0+, the default uses **SimpleSequenceSizeReleaseStrategy** when partial release is not configured; it optimizes performance but is not a durable reply deduplication system.

If one supplier sends a duplicate message while another supplier has not replied yet, duplicate detection policies must be tested. Do not infer that message count equaling sequenceSize means each supplier returned one result.

## 8. Creating three mock suppliers to study the Gather mechanism

To illustrate the processing path, three suppliers are implemented with pure calculations. Prices here are **simulated data** only and do not reflect real shipping rates.

~~~java
import java.math.BigDecimal;

final class WarehouseSupplier implements SupplierQuotePort {
    @Override
    public SupplierOutcome quote(QuoteRequest request) {
        return SupplierOutcome.success(
                request,
                "WAREHOUSE",
                BigDecimal.valueOf(85_000L)
                        .multiply(BigDecimal.valueOf(request.quantity())));
    }
}

final class PartnerSupplier implements SupplierQuotePort {
    @Override
    public SupplierOutcome quote(QuoteRequest request) {
        return SupplierOutcome.success(
                request,
                "PARTNER",
                BigDecimal.valueOf(80_000L)
                        .multiply(BigDecimal.valueOf(request.quantity())));
    }
}

final class BackupSupplier implements SupplierQuotePort {
    @Override
    public SupplierOutcome quote(QuoteRequest request) {
        return SupplierOutcome.success(
                request,
                "BACKUP",
                BigDecimal.valueOf(95_000L)
                        .multiply(BigDecimal.valueOf(request.quantity())));
    }
}
~~~

If the request has **quantity=2**, the prices are 170,000 VND, 160,000 VND, and 190,000 VND respectively. Gather will select **PARTNER** as bestOffer while keeping all three offers for comparison.

## 9. Java DSL: Scatter-Gather with branches running in parallel

Spring Integration Java DSL provides **scatterGather(scatterer, gatherer, options)**. In this example:

- **scatterer** declares three recipient sub-flows.
- Each sub-flow has an **ExecutorChannel** so processing runs on a thread pool.
- The final endpoint in each sub-flow returns a **SupplierOutcome**.
- **gatherer** uses QuoteReportFactory as the MessageGroupProcessor.
- **options** limits how long ScatterGatherHandler waits for results.
- The Report is sent to a QueueChannel used for the example/testing.

### 9.1. Flow configuration

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableIntegration
class QuoteScatterGatherConfig {

    @Bean
    SupplierQuotePort warehouseSupplier() {
        return new WarehouseSupplier();
    }

    @Bean
    SupplierQuotePort partnerSupplier() {
        return new PartnerSupplier();
    }

    @Bean
    SupplierQuotePort backupSupplier() {
        return new BackupSupplier();
    }

    @Bean
    MessageChannel quoteRequestsChannel() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel quoteReportsChannel() {
        return new QueueChannel();
    }

    @Bean
    ThreadPoolTaskExecutor quoteWorkers() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(3);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(30);
        executor.setThreadNamePrefix("quote-worker-");
        return executor;
    }

    @Bean
    IntegrationFlow quoteComparisonFlow(
            @Qualifier("warehouseSupplier")
            SupplierQuotePort warehouse,
            @Qualifier("partnerSupplier")
            SupplierQuotePort partner,
            @Qualifier("backupSupplier")
            SupplierQuotePort backup,
            @Qualifier("quoteWorkers")
            ThreadPoolTaskExecutor executor) {

        return IntegrationFlow.from("quoteRequestsChannel")
                .scatterGather(
                        scatter -> scatter
                                .recipientFlow(flow -> flow
                                        .channel(c -> c.executor(executor))
                                        .handle(QuoteRequest.class,
                                                (request, headers) ->
                                                        warehouse.quote(request)))
                                .recipientFlow(flow -> flow
                                        .channel(c -> c.executor(executor))
                                        .handle(QuoteRequest.class,
                                                (request, headers) ->
                                                        partner.quote(request)))
                                .recipientFlow(flow -> flow
                                        .channel(c -> c.executor(executor))
                                        .handle(QuoteRequest.class,
                                                (request, headers) ->
                                                        backup.quote(request))),
                        gather -> gather
                                .outputProcessor(
                                        QuoteReportFactory::fromGroup),
                        options -> options
                                .gatherTimeout(5_000))
                .channel("quoteReportsChannel")
                .get();
    }
}
~~~

**Version note:** This example targets Spring Integration Java DSL **6.x and later**, where the Scatter-Gather DSL conveniently configures applySequence for the scatterer it creates. If your project uses a different version, consult the corresponding API and test the actual sequence headers received; do not copy a configuration and assume behavior mechanically.

### 9.2. Why is this parallel processing?

Without an ExecutorChannel, each recipient may be dispatched sequentially on the thread calling ScatterGatherHandler; total duration could approximate the sum of the three suppliers.

With an ExecutorChannel and sufficient pool capacity, the three supplier operations are **submitted** to run independently. When the tasks can actually execute concurrently:

~~~text
Total processing time is roughly
  max(warehouse latency, partner latency, backup latency)
  + scatter/gather overhead
~~~

This is an **estimate when resources are sufficient and there are no shared bottlenecks**, not a framework guarantee. An overloaded thread pool, small connection pool, supplier rate limit, shared lock, or slow network can make latency significantly higher.

### 9.3. Why must the final handler return a reply?

In each branch, the snippet:

~~~java
.handle(QuoteRequest.class,
        (request, headers) -> warehouse.quote(request))
~~~

returns a **non-null SupplierOutcome**, allowing Spring Integration to create a reply for Gather to receive. If replaced with:

~~~java
// Anti-pattern for Scatter-Gather requiring all 3 replies:
.handle(QuoteRequest.class, (request, headers) -> {
    warehouse.quote(request);
    return null;
})
~~~

the Warehouse branch produces no reply. Gather does not automatically treat calling quote as an outcome; the group may only contain two messages and wait until timeout. A one-way endpoint can be valid in another flow, but does not satisfy the **request/reply contract** of this example.

### 9.4. Do not set a different outputChannel at the end of a branch

If the Warehouse branch returns an outcome but routes output to a different channel that does not lead back to Gather, ScatterGatherHandler will still miss the reply. The example needs to use the **replyChannel** mechanism attached by ScatterGatherHandler; if the system has a dedicated gatherChannel, every branch must be configured to send to that exact gatherChannel.

**Do not attach replyChannel from untrusted client data.** Control channels and correlation metadata must be created or verified by internal components.

### 9.5. Sending a test request

~~~java
import org.springframework.messaging.support.MessageBuilder;

QuoteRequest request = new QuoteRequest(
        "req-701", "SKU-99", 2);

// Bean quoteRequestsChannel is injected from Spring.
quoteRequestsChannel.send(
        MessageBuilder.withPayload(request).build());

// Bean quoteReportsChannel is a QueueChannel in the example.
var response = quoteReportsChannel.receive(5_000);
if (response == null) {
    throw new IllegalStateException("QUOTE_REPORT_TIMEOUT");
}
QuoteReport report = (QuoteReport) response.getPayload();
~~~

With the three mock suppliers and no errors, the report contains three outcomes, reportStatus COMPLETE, and bestOffer.supplierId equals PARTNER.

**Distinguish the two timeouts:** gatherTimeout(5_000) is how long **ScatterGatherHandler waits for the aggregator reply**; receive(5_000) on the producer side is how long **the test/client waits to read from the output QueueChannel**. These two timeouts do not replace each other. With a DirectChannel at ingress, the send() call may already block until Scatter-Gather finishes before reaching the receive() statement.

## 10. Gathering by completion order, not declaration order

When the three suppliers are processed on ExecutorChannel, their replies can arrive in any order:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant SG as ScatterGatherHandler
    participant W as Warehouse
    participant P as Partner
    participant B as Backup
    participant G as Aggregator
    C->>SG: req-701
    par Three concurrent requests
        SG->>W: req-701
        SG->>P: req-701
        SG->>B: req-701
    end
    P-->>G: PARTNER, 160000, sequence=2
    B-->>G: BACKUP, 190000, sequence=3
    Note over G: 2/3 replies, keep waiting
    W-->>G: WAREHOUSE, 170000, sequence=1
    G-->>SG: QuoteReport, 3/3 replies
    SG-->>C: Report
~~~

**Never assume:** that the first element in MessageGroup is the first declared supplier, or that the last element is always the slowest supplier across runs. Arrival order is an operational property that varies with thread scheduling, network, and load.

### 10.1. Two different kinds of ordering

- **Sorting results in the report** by supplierId, timestamp, or price makes output readable. This does not alter how branches execute.
- **Preserving business execution order** requires a separate strategy, which usually eliminates parallelism. You cannot simultaneously guarantee that all side effects commit in a fixed order and freely run in parallel without additional coordination.

In the quoting example, execution order does not matter; all suppliers are independent. Only the **bestOffer selection rule** and report display order need to be deterministic.

### 10.2. One request entering two different groups is a bug

If a branch creates its own correlationId instead of preserving the correlation provided by Scatter-Gather, replies may split into multiple groups:

~~~text
req-701:
    warehouse -> correlation=G-701-A
    partner   -> correlation=G-701-B
    backup    -> correlation=G-701-C
~~~

Each group receives only 1/3 reply and does not release under default rules. When payload transformation is needed, use Transformers/Handlers so that **reply metadata is properly preserved**; do not assign a new correlationId per supplier if the goal is the same Gather.

## 11. One branch does not respond: timeout vs. business error

With three suppliers, a branch may:

- Return a valid result, but slowly.
- Intentionally return UNAVAILABLE.
- Hit an HTTP timeout without knowing whether the request was processed.
- Throw an exception before creating a reply.
- Create a reply but send it to the wrong outputChannel.
- Reply after Gather has already finished.

Do not lump all cases under one generic FAILED label. You must distinguish **terminal response**, **missing reply**, **unknown state**, and **late arrival**.

### 11.1. Gather timeout: waiting for an aggregated result

In ScatterGatherHandler, **gatherTimeout** is the wait limit for the aggregator's result. In a synchronous setup, the thread executing Scatter-Gather may block while waiting. If no result arrives before the limit, the handler may return null; when **requiresReply=true** (the default), it throws an error like ReplyRequiredException.

Thus gatherTimeout does not mean "if 2/3 replies arrive, automatically aggregate 2". It only bounds **the request/reply wait time**.

Example:

~~~text
Expected suppliers: 3
Arrived in 5 seconds: WAREHOUSE, PARTNER
Missing: BACKUP

Aggregator still waits for 3/3
ScatterGatherHandler gatherTimeout=5000ms
=> Caller does not receive a complete QuoteReport
~~~

This is the right outcome if the contract **mandates all three sources**, but the application must provide clear error and recovery states rather than letting the caller hang indefinitely.

### 11.2. Group timeout: deciding what to do with an incomplete MessageGroup

The Aggregator provides **groupTimeout** or **groupTimeoutExpression** to trigger processing of an incomplete group upon expiration. If **sendPartialResultOnExpiry** is enabled, it can build a result from the group accumulated so far and emit a partial result, depending on release/expiry configuration.

~~~mermaid
flowchart TD
    A["Aggregator receives 2/3 outcomes"] --> B{"Group complete?"}
    B -->|"Yes"| C["Report COMPLETE / PARTIAL_SUPPLIER_FAILURE"]
    B -->|"No"| D["Wait until groupTimeout"]
    D --> E{"Allow partial release?"}
    E -->|"Yes"| F["Report INCOMPLETE, missing supplier"]
    E -->|"No"| X["Expire/discard per policy"]
~~~

If you want the caller to actually receive the partial result, **gatherTimeout must be compatible with groupTimeout and scheduler delay**. For example, groupTimeout=2 seconds and gatherTimeout=10 seconds gives the aggregator an opportunity to emit the partial result before ScatterGatherHandler times out. Setting tight or equal timeouts easily creates race conditions.

**Important:** by default, groupTimeout is typically measured from the last message added to the group; if you want a fixed deadline from when the request started, use a business deadline or a groupTimeoutExpression based on the group's creation timestamp as supported by your version. Do not assume all timeouts measure from request arrival time.

### 11.3. Partial reports need a dedicated contract

QuoteReportFactory.fromGroup() earlier intentionally required **all three terminal outcomes**. If partial release is enabled while still using that factory, it will throw INCOMPLETE_SUPPLIER_GROUP. To support partials, a separate processor is needed.

Domain example for incomplete reports:

~~~java
import java.util.List;

record PartialQuoteReport(
        String requestId,
        String reportStatus,
        List<String> missingSuppliers,
        List<SupplierOutcome> arrivedOutcomes,
        SupplierOutcome bestSoFar) {}
~~~

Rules:

1. Read the set of **invited** suppliers from a trusted manifest (in the fixed example: WAREHOUSE, PARTNER, BACKUP).
2. Verify the identity of each outcome.
3. Compute missingSuppliers as the expected set minus the received set.
4. Set reportStatus=INCOMPLETE if any reply is missing.
5. If selecting bestSoFar, clearly state it is **the best provisional price**, not necessarily the best price across all suppliers.

Do not infer expectedSuppliers from outcomes.size(), because a missing-reply scenario is precisely when the current size is **smaller than** the number of invited sources.

### 11.4. What does returning null from a handler mean?

If a supplier has no quote, the right approach under a **one-reply-per-supplier** contract is:

~~~java
return SupplierOutcome.unavailable(
        request,
        "BACKUP",
        "NO_QUOTE_FOR_SKU");
~~~

Do not write:

~~~java
// Wrong in a flow requiring all responses:
if (notAvailable) {
    return null;
}
~~~

In a one-way Service Activator, returning null may be a normal termination for the branch, but for a Gather expecting 3/3 replies, that branch will be missing an outcome. To use a **K-of-N** strategy without waiting for missing branches, you need a different release policy and an explicit incomplete status.

## 12. When one branch errors, do not accidentally discard the value of the other two

Spring Integration notes that **Scatter-Gather has special multi-request-reply error behavior**. If a synchronous sub-flow throws an exception up to ScatterGatherHandler, the exception may propagate upstream and the results from the other branches can no longer be used to build the report.

For branches running asynchronously, exceptions are typically converted into an ErrorMessage via MessagePublishingErrorHandler when supported by the executor/adapter. However, **an ErrorMessage sent to errorChannel does not automatically become a Gather reply**.

~~~mermaid
flowchart LR
    R["Scatter req-701"] --> W["Warehouse: SUCCESS"]
    R --> P["Partner: timeout"]
    R --> B["Backup: SUCCESS"]
    W --> G["Gather has 2/3"]
    B --> G
    P -.-> E["ErrorMessage / errorChannel"]
    E -.-> X["Not yet a SupplierOutcome"]
~~~

If you want all three terminal results, anticipated errors must be turned into **an explicit failure outcome** for the exact supplier.

### 12.1. Classifying errors per supplier

| Error | Can return terminal outcome immediately? | Appropriate handling |
| --- | --- | --- |
| Supplier actively declines SKU | Yes | UNAVAILABLE / NO_QUOTE |
| Supplier returns malformed contract data | Possibly | INVALID_SUPPLIER_RESPONSE; also alert |
| HTTP 429 | Not always | Bounded retry, rate limit; then timeout/terminal |
| HTTP timeout | Not necessarily | Idempotent retry if suitable, or UNKNOWN |
| Cannot resolve channel | No | Topology error, fix configuration |
| Thread pool rejects task | No | Backpressure and admission error |
| NullPointerException due to bug | Should not be silent | Alert, quarantine/retry after code fix |
| Reply arrives past deadline | No longer contributes to emitted report | Late-arrival policy, do not silently mutate report |

Do not use catch(Exception) to turn every system error into an unavailable quote. That hides deployment, schema, or circuit breaker bugs and makes reports look valid even when the framework failed.

### 12.2. Handling expected errors right inside the branch

Suppose a supplier adapter has a classified domain exception:

~~~java
final class SupplierUnavailableException
        extends RuntimeException {
    SupplierUnavailableException(String message) {
        super(message);
    }
}

final class SafePartnerQuoteAdapter implements SupplierQuotePort {
    private final SupplierQuotePort remote;

    SafePartnerQuoteAdapter(SupplierQuotePort remote) {
        this.remote = remote;
    }

    @Override
    public SupplierOutcome quote(QuoteRequest request) {
        try {
            return remote.quote(request);
        } catch (SupplierUnavailableException expected) {
            return SupplierOutcome.unavailable(
                    request,
                    "PARTNER",
                    "PARTNER_TEMPORARILY_UNAVAILABLE");
        }
    }
}
~~~

This adapter catches the exact domain error class considered terminal after the retry policy (if any). It does **not** swallow NullPointerException or unexpected runtime errors. If an unresolved timeout leaves the business request unable to conclude terminally, record an UNKNOWN state or handle it via an appropriate timeout/recovery path rather than immediately returning UNAVAILABLE.

### 12.3. ErrorMessage compensation for asynchronous branches

Spring Integration can configure **errorChannel** on ScatterGatherHandler so that when an async sub-flow errors, an error flow produces a **compensation reply** for Gather. With Java DSL:

~~~java
// Illustrative DSL snippet showing Scatter-Gather options:
.scatterGather(
        scatterer -> scatterer
                .recipientFlow(/* supplier A flow */)
                .recipientFlow(/* supplier B flow */),
        gatherer -> gatherer
                .outputProcessor(QuoteReportFactory::fromGroup),
        options -> options
                .gatherTimeout(10_000)
                .errorChannel("quoteScatterErrors"))
~~~

For compensation to actually reach Gather, the error handler response needs to preserve **replyChannel, correlationId, sequenceNumber, sequenceSize**, and the metadata Scatter-Gather uses to manage the original gatherResultChannel/reply.

Per documentation, when an error handler extracts **failedMessage** from MessagingException and creates a compensation Message:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

// Method snippet invoked from error flow, not main()
Message<SupplierOutcome> makeCompensation(
        MessagingException failure) {

    Message<?> failedMessage = failure.getFailedMessage();
    if (failedMessage == null
            || !(failedMessage.getPayload() instanceof QuoteRequest request)) {
        throw new IllegalStateException(
                "Insufficient metadata to recover Gather", failure);
    }

    Object source = failedMessage.getHeaders().get("supplierId");
    if (!(source instanceof String supplierId)
            || !java.util.Set.of(
                    "WAREHOUSE", "PARTNER", "BACKUP")
                    .contains(supplierId)) {
        throw new IllegalStateException(
                "Unknown failing supplier", failure);
    }

    // Use this path only when the error is classified
    // and business rules allow a terminal failure outcome.
    return MessageBuilder
            .withPayload(SupplierOutcome.unavailable(
                    request, supplierId, "SUPPLIER_FAILED"))
            .copyHeaders(failedMessage.getHeaders())
            .build();
}
~~~

In a real flow, **supplierId** must be attached to headers **by internal code in each branch**, not from untrusted input; for example, a Header Enricher before the I/O step. Additionally, the error handler must inspect the error cause and retry policy before calling makeCompensation(). This is an **illustrative snippet**, not a complete error flow.

**Do not copy all raw headers from external sources into public outputs.** Copying metadata above is meant to retain internal routing headers of failedMessage so compensation returns to Gather; there must be a trust boundary at ingress and an appropriate data policy.

### 12.4. Do not produce two replies for the same supplier

A timeout can cause:

1. The supplier actually produced a reply, but the network response was lost.
2. The error handler creates an UNAVAILABLE compensation.
3. A real reply arrives late with the same supplierId.

Gather and the state store must enforce a policy of **one terminal outcome per supplier per request**. If two results appear:

- Do not count them as two suppliers.
- Do not silently overwrite a published terminal report.
- Record the duplicate/late reply and reconcile if needed.

A composite key can be **requestId + supplierId** (plus trusted tenantId if needed). Duplicate handling in Aggregator/MessageStore must be tested; do not assume the default release strategy automatically provides the right semantics.

## 13. MessageGroupStore, late replies, and group lifecycle

The Aggregator uses **MessageGroupStore** to accumulate replies. For local, short-lived examples, an in-memory store suffices for illustration. For workloads requiring recovery across restarts, you must choose a persistent store, transactions, locking, and corresponding cleanup policies.

### 13.1. How is a group created, released, and expired?

~~~text
New group
   -> receives reply #1
   -> receives reply #2
   -> receives reply #3
   -> ReleaseStrategy allows release
   -> MessageGroupProcessor creates QuoteReport
   -> Group is marked complete or expired
~~~

Per Aggregator documentation, once a group completes:

- If **expireGroupsUponCompletion=false** (default), the framework can retain metadata of completed groups to detect and discard late replies.
- If **expireGroupsUponCompletion=true**, the group is removed; a subsequent reply with the same correlation ID may **create a new group**, causing incorrect grouping or duplicate reports.
- For timed-out groups, **expireGroupsUponTimeout** has separate semantics, distinct from normal completion.

This leads to a trade-off: keeping metadata too long fills up the MessageStore; deleting too early lets late messages recreate the group. You must choose **retention matching the maximum redelivery window**, rather than keeping forever or deleting immediately by habit.

### 13.2. Correlation group and business report have different lifecycles

A local Scatter-Gather may finish in a few hundred milliseconds, while the quote's requestId remains stored for hours for lookup. Therefore:

- **MessageGroup** is technical state for assembling replies within an attempt.
- **QuoteReport** is the business result, which may need to be persisted alongside requestId.
- **Processing ledger** records per-supplier status for recovery when an attempt fails.
- **Outbox** is used when results or follow-up tasks need durable publishing.

Do not use an in-memory MessageGroup as **the single source of truth** for a business process that must survive restarts or span multiple instances.

### 13.3. Group store in a multi-instance environment

When replies can arrive at different instances, you need a correlation mechanism shareable across processes, or ensure all replies for a request land on the same instance:

- Use a shared persistent MessageGroupStore with proper locking/transactions.
- Or use broker routing by correlation key to direct replies to the same worker.
- Or move Gather to a service owning persistent state keyed by requestId.

Simply swapping SimpleMessageStore for a database is not enough if consumers have race conditions or lack a shared correlation contract. You must test concurrent arrivals, duplicates, database failover, and group cleanup.

### 13.4. Late replies must not silently alter results

Suppose an INCOMPLETE QuoteReport is emitted after 3 seconds, and then BACKUP sends a cheaper offer at second 8. You can choose one of two policies:

1. **Freeze result:** the published report is final as of the deadline; the late reply is stored/audited without affecting the selection.
2. **Revisioned result:** emit report version 2, marking version 1 as superseded; downstream must understand updates and be idempotent.

Never mutate a report that has already been used to place an order or process payment without a versioning/compensation contract. A late reply is not just a technical event; it can affect business decisions already executed.

## 14. Designing timeouts around an overall deadline

A Gather flow with multiple suppliers has several easily confused timeouts:

| Type | Where configured | Meaning |
| --- | --- | --- |
| **Supplier HTTP timeout** | Each supplier adapter | How long to wait for one supplier |
| **Aggregator groupTimeout** | MessageGroup / Aggregator | When to process an incomplete group |
| **ScatterGatherHandler gatherTimeout** | Request/reply endpoint | How long the caller waits for the aggregated result |
| **Gateway timeout** | Outer Gateway | How long the flow client waits for a reply |
| **Queue sendTimeout** | Bounded send channel | How long to wait to enqueue a message into a channel |

These timeouts are **not synonymous**, nor should they be set arbitrarily equal.

### 14.1. Example 8-second budget

Suppose the quote SLA is **8 seconds**:

~~~text
Client deadline                      8.0 s
  scatter overhead                   0.1 s
  supplier timeout                   4.0 s
  error/recovery + aggregation        1.0 s
  gather/client margin                2.9 s
~~~

This is an illustrative allocation. If each supplier has three sequential 4-second retries, total time will breach the SLA even though scatter runs in parallel. Therefore retry counts and backoff must fit within **the overall deadline**, not just be configured independently per endpoint.

### 14.2. The slowest branch governs latency under all-of-N

If three suppliers finish in 300 ms, 800 ms, and 2,200 ms, a Gather waiting for all three cannot return a complete result before roughly 2,200 ms (plus overhead), even though the first two replies arrived very early.

If the SLA cannot tolerate waiting for the third supplier, you can use partial release or **K-of-N**, but must disclose that **not all suppliers were consulted**. Do not claim "lowest market price" when only a subset of offers was received.

### 14.3. Never let groups live forever

A group waiting on a missing reply does not just hold one object; under high load, hundreds of thousands of groups can accumulate in MessageGroupStore.

Mitigations:

- Bounded queues and bounded executors.
- Group timeout/expiry or persistent progress state.
- Monitoring pending group count and group age.
- Dead-letter/recovery for repeatedly failing suppliers.
- Maximum reply limit per group.
- Filtering duplicate replies and unidentified inputs.

If waiting takes hours/days, consider a **durable workflow with a state machine** rather than keeping a request/reply caller blocked in ScatterGatherHandler.

## 15. Parallel does not mean free of resource cost

A program using ExecutorChannel for three branches typically sees two load dimensions:

1. **Concurrent Scatter-Gather requests**: how many requests are waiting for replies?
2. **Concurrent supplier tasks**: each request can spawn up to three tasks.

With 200 concurrent requests each dispatching 3 tasks, you can generate **600 near-simultaneous supplier invocations**. Simply enlarging the thread pool to reduce timeouts can overload the database, HTTP connection pools, or supplier rate limits.

### 15.1. Bounded TaskExecutor

In the earlier example, ThreadPoolTaskExecutor had:

~~~text
corePoolSize = 3
maxPoolSize  = 6
queueCapacity = 30
~~~

That is a **demo configuration**, not a production recommendation for all loads. When the queue is full, the executor may reject tasks; you need explicit backpressure, admission, retry, and error reporting policies. Do not treat a rejected task as a supplier returning UNAVAILABLE if the request was never dispatched.

### 15.2. Blocking I/O and connection limits

If quote suppliers use blocking HTTP, worker threads are held while waiting. A small pool protects resources but increases latency; an oversized pool can overload the system beyond capacity.

Measure and bound:

- Concurrent connections per supplier.
- Connect and read timeouts.
- Attempt counts and backoff.
- Circuit breakers when a supplier degrades.
- Per-supplier rate limits and bulkheads, so one failing supplier does not exhaust the entire pool.
- Concurrent in-flight Scatter-Gather requests.

### 15.3. Not every Publisher runs concurrently

PublishSubscribeChannel dispatches synchronously by default. RecipientListRouter also does not automatically create separate threads per recipient. Only with an appropriate async executor/channel/adapter can branches potentially execute in true parallel.

A diagram with three arrows is **not** proof of parallelism. Real tests must verify overlap or throughput under load, rather than relying on the name Scatter-Gather.

## 16. Replay and idempotency per supplier

Gathering one result from three suppliers does not guarantee the request was sent only once. If a message is redelivered by a broker, retried by a Gateway, or replayed by an operator, the entire scatter operation may execute again.

### 16.1. Distinguishing three key types

| Identifier | Scope | Purpose |
| --- | --- | --- |
| **requestId** | One logical quote request | Tracking/replay across attempts |
| **correlationId** | One scatter/gather group | Grouping replies within one attempt |
| **supplierId** | One logical branch | Identifying outcome source and preventing double counting |
| **attemptId** | One technical attempt | Metrics/tracing, does not replace idempotency key |

For operations needing side-effect protection:

~~~text
businessOperationKey = tenantId + ":" + requestId + ":" + supplierId
~~~

If only **reading quotes** via a read-only API, retries carry lower side-effect risk. But if a supplier records a reservation, creates an order, or locks a price, the idempotency key must be accepted/recorded by the provider per contract.

### 16.2. Retrying all branches after partial success

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant S as Scatter
    participant A as Supplier A
    participant B as Supplier B
    participant D as Supplier C
    C->>S: Request req-701, attempt 1
    S->>A: Request
    S->>B: Request
    S->>D: Request
    A-->>S: Success
    B-->>S: Success
    D--xS: Timeout
    C->>S: Retry request req-701
    S->>A: Request again
    S->>B: Request again
    S->>D: Request again
    Note over A,B: Idempotency if side effects exist
~~~

If only supplier C fails, a system with persistent progress can retry **only C** instead of calling A and B again. This optimization requires persisting per-supplier state and received replies; a local ScatterGatherHandler **does not automatically provide a durable inbox/outbox workflow**.

### 16.3. Do not use MessageHeaders.ID as a business key

A Message can be recreated when passing through Transformers/adapters or after a restart; MessageHeaders.ID is technical metadata, not a representation of a logical quote request. Use a stable requestId per the contract.

### 16.4. Do not mark success too early

A supplier returning HTTP 202 Accepted may only confirm the request entered a queue, not that a quote exists yet. If Gather requires **a final price**, do not treat ACCEPTED as SUCCESS with totalPriceVnd.

Define a clear contract for PENDING and deadlines; if you decide to wait for long-running async results, a durable workflow with subsequent result events may fit better than immediate request/reply.

## 17. Unit testing the report and per-supplier outcomes

Verify the data contract before running Spring Integration. Unit tests help separate business logic errors from channel/correlation bugs.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class SupplierOutcomeTest {

    @Test
    void supplierSuccessContainsPositivePrice() {
        QuoteRequest request = new QuoteRequest(
                "req-800", "SKU-1", 2);

        SupplierOutcome result = SupplierOutcome.success(
                request, "WAREHOUSE",
                new BigDecimal("170000"));

        assertEquals("req-800", result.requestId());
        assertEquals("WAREHOUSE", result.supplierId());
        assertEquals("SUCCESS", result.status());
        assertEquals(new BigDecimal("170000"),
                result.totalPriceVnd());
        assertNull(result.errorCode());
    }

    @Test
    void unavailableOutcomeIsTerminalButNotAPrice() {
        QuoteRequest request = new QuoteRequest(
                "req-801", "SKU-2", 1);

        SupplierOutcome result = SupplierOutcome.unavailable(
                request, "PARTNER", "NO_QUOTE");

        assertEquals("UNAVAILABLE", result.status());
        assertNull(result.totalPriceVnd());
        assertEquals("NO_QUOTE", result.errorCode());
    }

    @Test
    void invalidPriceIsNotAcceptedAsSuccess() {
        QuoteRequest request = new QuoteRequest(
                "req-802", "SKU-3", 1);

        assertThrows(IllegalArgumentException.class,
                () -> SupplierOutcome.success(
                        request,
                        "BACKUP",
                        BigDecimal.ZERO));
    }
}
~~~

### 17.1. Invariants to verify in QuoteReportFactory

Beyond the example above, unit tests with a mock MessageGroup should cover:

1. Three valid outcomes from three suppliers → COMPLETE and accurate lowest price.
2. Two SUCCESS, one UNAVAILABLE → PARTIAL_SUPPLIER_FAILURE.
3. Three UNAVAILABLE → NO_OFFER.
4. Two outcomes with the same supplierId → reject duplicate.
5. Outcomes with two different requestIds → reject mixed group.
6. Group with only 2/3 → must not produce COMPLETE.

If constructing a MessageGroup in unit tests, use the APIs/constructors of your Spring Integration version and attach sequence/correlation headers properly. This does not replace integration tests where the framework actually scatters and gathers replies.

## 18. Integration testing with Spring context: all three results

Since QuoteScatterGatherConfig defines the flow and three mock suppliers, it can be tested directly with **JUnit 5 + spring-test**. QuoteReportsChannel is a QueueChannel, so after synchronous ScatterGatherHandler completion, the test can read the report with receive(0).

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(QuoteScatterGatherConfig.class)
class QuoteScatterGatherTest {

    @Autowired
    @Qualifier("quoteRequestsChannel")
    MessageChannel input;

    @Autowired
    @Qualifier("quoteReportsChannel")
    QueueChannel reports;

    @BeforeEach
    void clearReports() {
        while (reports.receive(0) != null) {
            // Drain queue from previous test if Spring context is reused.
        }
    }

    @Test
    void gathersThreeRepliesAndChoosesCheapest() {
        QuoteRequest request = new QuoteRequest(
                "req-901", "SKU-9", 2);

        assertTrue(input.send(
                MessageBuilder.withPayload(request).build()));

        Message<?> reply = reports.receive(0);
        assertNotNull(reply);

        QuoteReport report = (QuoteReport) reply.getPayload();
        assertEquals("req-901", report.requestId());
        assertEquals(3, report.expectedSuppliers());
        assertEquals(3, report.receivedOutcomes());
        assertEquals("COMPLETE", report.reportStatus());
        assertEquals("PARTNER", report.bestOffer().supplierId());
        assertEquals(new BigDecimal("160000"),
                report.bestOffer().totalPriceVnd());

        assertEquals(Set.of(
                "WAREHOUSE", "PARTNER", "BACKUP"),
                report.outcomes().stream()
                        .map(SupplierOutcome::supplierId)
                        .collect(java.util.stream.Collectors.toSet()));
        assertNull(reports.receive(0));
    }

    @Test
    void concurrentRequestsKeepTheirOwnCorrelation() throws Exception {
        ExecutorService producers = Executors.newFixedThreadPool(2);
        try {
            Callable<Boolean> first = () -> input.send(
                    MessageBuilder.withPayload(
                            new QuoteRequest(
                                    "req-902", "SKU-2", 1)).build());
            Callable<Boolean> second = () -> input.send(
                    MessageBuilder.withPayload(
                            new QuoteRequest(
                                    "req-903", "SKU-3", 3)).build());

            Future<Boolean> sentA = producers.submit(first);
            Future<Boolean> sentB = producers.submit(second);
            assertTrue(sentA.get());
            assertTrue(sentB.get());

            Message<?> resultA = reports.receive(1_000);
            Message<?> resultB = reports.receive(1_000);
            assertNotNull(resultA);
            assertNotNull(resultB);

            QuoteReport reportA =
                    (QuoteReport) resultA.getPayload();
            QuoteReport reportB =
                    (QuoteReport) resultB.getPayload();

            // Order of the two reports is not guaranteed.
            assertEquals(Set.of("req-902", "req-903"),
                    Set.of(reportA.requestId(), reportB.requestId()));
            assertEquals(3, reportA.receivedOutcomes());
            assertEquals(3, reportB.receivedOutcomes());

            for (QuoteReport report : List.of(reportA, reportB)) {
                assertTrue(report.outcomes().stream().allMatch(
                        outcome -> report.requestId()
                                .equals(outcome.requestId())));
            }
        } finally {
            producers.shutdownNow();
        }
    }
}
~~~

**What these two tests prove:**

- One request fans out to three suppliers and combines into exactly one QuoteReport.
- QuoteReport retains all three sources and selects bestOffer by price and tie-break rule.
- Two concurrent requests do not mix replies when correlation and flow are properly configured.
- The test does not depend on the arrival order of the two reports.

**Limitation:** the mock suppliers run very fast, so this test does not prove that **the three supplier calls overlapped in time**. An Executor might be configured yet still complete nearly sequentially due to scheduling. To verify parallelism, a barrier synchronization test is needed as shown next.

## 19. Testing that three branches can truly execute concurrently

One way to verify true parallelism is using **CountDownLatch or CyclicBarrier** in the three mock suppliers: every branch must start before any branch is allowed to finish. If the flow runs the three branches sequentially on one thread, the test will time out.

### 19.1. Test probe using latches

~~~java
import java.math.BigDecimal;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

final class ParallelQuoteProbe {
    final CountDownLatch allStarted = new CountDownLatch(3);
    final CountDownLatch release = new CountDownLatch(1);

    SupplierOutcome invoke(
            QuoteRequest request,
            String supplierId,
            long unitPrice) {

        allStarted.countDown();
        try {
            if (!release.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("PARALLEL_PROBE_TIMEOUT");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("PROBE_INTERRUPTED", ex);
        }

        return SupplierOutcome.success(
                request,
                supplierId,
                BigDecimal.valueOf(unitPrice)
                        .multiply(BigDecimal.valueOf(request.quantity())));
    }
}
~~~

Wire three calls to this probe into the three recipient sub-flows instead of the SupplierQuotePort beans in the config; each branch passes its corresponding supplierId and unitPrice.

Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.support.MessageBuilder;

// Body of an integration test that already injects:
// MessageChannel input; QueueChannel reports; ParallelQuoteProbe probe.
@Test
void threeSupplierTasksCanOverlap() throws Exception {
    ExecutorService callerPool = Executors.newSingleThreadExecutor();
    try {
        Future<Boolean> send = callerPool.submit(() ->
                input.send(MessageBuilder
                        .withPayload(new QuoteRequest(
                                "req-parallel", "SKU-P", 1))
                        .build()));

        // All three suppliers must enter the probe before release.
        assertTrue(probe.allStarted.await(
                3, TimeUnit.SECONDS));
        probe.release.countDown();

        assertTrue(send.get(8, TimeUnit.SECONDS));
        assertNotNull(reports.receive(1_000));
    } finally {
        probe.release.countDown(); // Avoid hanging workers if an assertion fails.
        callerPool.shutdownNow();
    }
}
~~~

**Test prerequisite:** requires a **dedicated test Spring context** where the three supplier beans from QuoteScatterGatherConfig are replaced by three ports calling the same ParallelQuoteProbe. The `@Test` snippet is a method fragment placed into that test class and **does not run standalone** without declaring the injected fields and test flow. This is a more deterministic overlap check than measuring elapsed milliseconds or calling Thread.sleep.

### 19.2. Do not reuse the same probe across multiple tests

A CountDownLatch cannot be reset once it reaches 0. Create a fresh probe per test or use separate test contexts. Also release the latch in `finally`, because if an assertion fails while workers are still waiting, the suite could hang or interfere with other tests.

### 19.3. Passing this test does not guarantee production always meets SLA

Three tasks hitting the probe simultaneously proves **overlap capability** in the test context; it does not prove the production system has enough CPU, HTTP connections, thread pool size, or capacity for every request to finish before deadline.

Production still needs load tests measuring **p95/p99 gather duration, active worker count, queue depth, supplier timeouts, and partial report rate**.

## 20. Testing UNAVAILABLE branches and groups with missing replies

A production test suite cannot only have three suppliers returning valid prices. At minimum, you must simulate **one reply as a failure outcome** and **one branch emitting no reply**; these two cases are completely different to Gather.

### 20.1. Branch returning an intentional failure outcome

Replace PartnerSupplier in the test with:

~~~java
final class UnavailablePartnerSupplier
        implements SupplierQuotePort {

    @Override
    public SupplierOutcome quote(QuoteRequest request) {
        return SupplierOutcome.unavailable(
                request,
                "PARTNER",
                "NO_CAPACITY");
    }
}
~~~

With WAREHOUSE and BACKUP still returning offers:

~~~text
Expected: 3 replies
Received:
  WAREHOUSE -> SUCCESS
  PARTNER   -> UNAVAILABLE
  BACKUP    -> SUCCESS

Gather group = 3/3 terminal outcomes
Report:
  reportStatus = PARTIAL_SUPPLIER_FAILURE
  bestOffer    = WAREHOUSE
  receivedOutcomes = 3
~~~

This is **partial supplier success**, not **partial aggregation**. The Aggregator still receives all three terminal results to release.

### 20.2. Branch producing no reply

In a dedicated test Spring context, deliberately configure the Partner sub-flow to return null:

~~~java
// Used only as an anti-pattern test case.
.recipientFlow(flow -> flow
        .handle(QuoteRequest.class, (request, headers) -> null))
~~~

Here Gather defaults to expecting 3 replies but only receives 2. With a short explicitly configured gatherTimeout, the test must verify:

1. No COMPLETE QuoteReport is created.
2. The caller receives a timeout/reply-required failure per the endpoint semantics of the version in use.
3. Incomplete groups are not retained indefinitely without a cleanup policy.
4. If partial aggregation is enabled, the report clearly identifies which supplier is missing.

Do not use Thread.sleep to "wait long enough". Use bounded synchronization/timeout tools such as CompletableFuture, Awaitility, or an inspected MessageGroupStore with limits.

### 20.3. Error in a synchronous sub-flow

Create a synchronous processing branch that throws IllegalStateException before replying. The test verifies that the branch exception may propagate to the caller and does not produce a complete Gather result. This behavior differs from a valid SupplierOutcome.unavailable reply.

When product requirements state "one failing supplier does not spoil the other two quotes", you must design **a dedicated error boundary inside each sub-flow**, rather than relying on ScatterGatherHandler automatically ignoring exceptions.

### 20.4. Error in an asynchronous sub-flow

Create a branch running on ExecutorChannel that throws an exception. Wire an errorChannel to receive ErrorMessage, extract failedMessage, and inspect correlation/reply metadata. If using compensation, emit **one** terminal SupplierOutcome back to Gather, then verify the report contains all three outcomes.

Also write a test where the error handler cannot identify supplierId or failedMessage is missing: **do not guess the supplier**; instead send the error to quarantine/alerting. A compensation carrying the wrong source identity can cause the Aggregator to mis-correlate or double-count.

## 21. A Gather configuration pattern for partial release

In an advanced exercise, if the business accepts a decision from two of three suppliers and the processing window is a few seconds, the Aggregator's timeout mechanism can be configured separately from gatherTimeout.

~~~java
// DSL snippet focused only on Gather; recipient flows
// are defined similarly to the previous example.
.scatterGather(
        scatterer -> scatterer
                .recipientFlow(/* supplier A */)
                .recipientFlow(/* supplier B */)
                .recipientFlow(/* supplier C */),
        gatherer -> gatherer
                .groupTimeout(2_000)
                .sendPartialResultOnExpiry(true)
                .outputProcessor(PartialQuoteReportFactory::fromGroup),
        options -> options
                .gatherTimeout(10_000))
~~~

To turn this snippet into an executable program, you must define:

- Replying recipientFlows as in the full Java DSL section.
- **PartialQuoteReportFactory** knowing the set of invited suppliers and distinguishing INCOMPLETE from COMPLETE.
- An appropriate MessageGroupStore and cleanup/late-arrival policy.
- Per-request deadlines, not just illustrative hardcoded constants.

**groupTimeout does not automatically verify at least 2 replies.** When a group only has 1 reply upon timeout, a partial configuration may still emit a result from 1 reply if policy permits. If the business requires at least 2, configure **ReleaseStrategy and the partial processor** to enforce minCount or use an appropriate workflow state; do not say "groupTimeout=2000 means 2-of-3".

### 21.1. K-of-N does not guarantee finding the best price

If K=2, N=3 and BACKUP is the cheapest supplier but responds slowly, a report completing right after two replies may pick a worse price compared to all three offers. That is a business trade-off.

When defining K:

- Disclose how many suppliers responded.
- Define the minimum number of valid offers, not just terminal outcomes.
- Clearly mark status as INCOMPLETE/PARTIAL.
- Define an SLA for late replies and report freeze/update rules.
- Do not execute automated payments on a report that has not met the required confidence level.

### 21.2. When should request/reply Scatter-Gather NOT be used?

Do not hold a request thread waiting too long when:

- Suppliers may respond after minutes or hours.
- Each branch is a saga with multiple side effects and compensations.
- The system must recover across restarts without losing progress.
- A request has thousands of recipients or an unknown number of replies.
- Decisions must be revised repeatedly as late replies arrive.

In those cases, an **asynchronous workflow with inbox/outbox and per-supplier state** is usually more appropriate. It is still Scatter-Gather at the pattern level, without necessarily being implemented via a caller-blocking ScatterGatherHandler.

## 22. Monitoring Gather quality

A flow may scatter many requests, yet if Gather frequently misses replies, the aggregation feature fails business needs. Measure both ends.

| Metric / signal | Meaning |
| --- | --- |
| **scatter_requests_total** | Total requests dispatched |
| **scatter_selected_recipients{route}** | Number of invited recipients, by bounded route |
| **supplier_requests_total{supplier}** | Invocation attempts per supplier |
| **supplier_outcomes_total{supplier,status}** | Terminal outcomes per source |
| **supplier_latency_seconds{supplier}** | Supplier latency |
| **gather_expected_replies** | Expected replies per correlation group |
| **gather_received_replies** | Received replies, not success count |
| **gather_duration_seconds** | Time from scatter to result |
| **gather_timeout_total** | Requests hitting timeout |
| **gather_partial_report_total** | Count of INCOMPLETE reports |
| **gather_group_pending** | Unreleased groups count |
| **gather_group_age_seconds** | Age of waiting groups |
| **gather_late_reply_total** | Replies arriving after deadline or group completion |
| **gather_duplicate_reply_total** | Multiple replies with same supplier identity/request |
| **gather_correlation_errors_total** | Replies missing or carrying wrong correlation metadata |
| **gather_error_recovery_failed_total** | Error flow failed to produce compensation/alert |
| **scatter_executor_rejections_total** | Tasks rejected due to overload |

Metrics with supplier/route labels should be constrained by an **allowlist**. Do not use arbitrary requestId, orderId, tenantId, or raw error messages as metric labels due to cardinality and data-leak risks. Those belong in logs/traces with proper access controls and retention.

### 22.1. Example Gather decision log

~~~json
{
  "requestId": "req-701",
  "expectedSuppliers": 3,
  "receivedOutcomes": 3,
  "successfulOffers": 2,
  "supplierFailures": 1,
  "bestSupplier": "WAREHOUSE",
  "reportStatus": "PARTIAL_SUPPLIER_FAILURE",
  "gatherDurationMs": 1820
}
~~~

This is a **sample log**. Do not log raw supplier credentials, tokens, customer PII, or entire HTTP responses. If a request receives 2/3 outcomes because one supplier stays silent, reportStatus must be INCOMPLETE rather than PARTIAL_SUPPLIER_FAILURE per the distinction in this lesson.

### 22.2. Alerts to watch for

- Rising gatherTimeout rate after changing thread pools or supplier adapters.
- Many pending groups exceeding allowed age.
- One supplier stopped replying while requests are still being sent to it.
- Groups with duplicate sequenceNumber or supplierId.
- Abnormal bestOffer results due to schema/currency conversion bugs.
- ErrorMessages landing on global errorChannel without proper Gather recovery.
- Reports for the same requestId emitted twice after redelivery/restart.
- Queue depth growing without a corresponding rise in incoming requests.

**Observe root causes:** a timeout can stem from a slow supplier, worker pool starvation, lost replyChannel header, wrong group correlation, or an Aggregator failing to release. Do not conclude "supplier timeout" just because the caller did not receive a report.

## 23. Auction option with PublishSubscribeChannel

The full Java DSL example above uses the **distribution** variant because it declares a RecipientListRouter with three recipientFlows. When you want to broadcast the same request to a pre-registered set of subscribers, you can use the **auction** variant with PublishSubscribeChannel.

An auction channel with a TaskExecutor:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

// Inside @Configuration that already has the quoteWorkers bean.
@Bean
PublishSubscribeChannel quoteAuctionChannel(
        ThreadPoolTaskExecutor quoteWorkers) {
    PublishSubscribeChannel channel =
            new PublishSubscribeChannel(quoteWorkers);
    channel.setApplySequence(true);
    return channel;
}
~~~

Supplier Service Activators can subscribe to **quoteAuctionChannel**. In the auction variant of ScatterGatherHandler, this channel acts as the **scatterChannel**; an AggregatingMessageHandler still handles Gather.

**Do not use both an auction scatterChannel and a recipient-list scatterer together** as if they were two required steps. They are two alternative approaches. With plain Bean/Java configuration, you must explicitly wire the channel, gatherer, replyChannel, and applySequence; Java DSL provides convenience helpers for assembling Scatter-Gather, though exact version APIs must be verified.

### 23.1. Is Auction the same as a regular PublishSubscribeChannel?

Not entirely. PublishSubscribeChannel only broadcasts messages to subscribers; **it does not wait for replies and build a QuoteReport on its own**. The Gather part is handled by ScatterGatherHandler and AggregatingMessageHandler.

When using PublishSubscribeChannel outside Scatter-Gather, if subscribers return replies with nothing collecting them, that is not yet a true Scatter-Gather system.

### 23.2. When not to put an Executor on both layers?

If PublishSubscribeChannel already has an executor, you may not need another ExecutorChannel at the start of each sub-flow for the same task. Two chained executor layers can increase thread hops, queuing, and make total deadline calculation confusing.

Pick one async boundary intentionally, unless per-supplier bulkheads/capacity isolation are needed. Use metrics/traces to verify where I/O runs and actual backpressure.

## 24. Common mistakes when Gathering parallel results

| Mistake | Consequence | How to avoid |
| --- | --- | --- |
| Assuming Scatter-Gather runs in parallel automatically | Branches may run sequentially | ExecutorChannel or PublishSubscribeChannel with executor |
| Simply wiring three replies into one channel | No proper correlation/release | Aggregator or workflow state |
| Forgetting applySequence on a custom scatterer | Gather does not know when N is reached | Verify sequence metadata |
| Using a fixed correlation key for all requests | Mixes offers across different requests | Separate correlation per request/attempt |
| Dropping replyChannel in a branch | Gather misses the result | Preserve internal routing headers |
| Final handler returns null | No reply, group may hang | Return a non-null terminal outcome |
| Unhandled synchronous supplier exception | Discards replies from other branches | Dedicated error boundary and compensation |
| Treating ErrorMessage as a normal reply | Confuses Throwable payload with business outcome | Convert errors to typed outcomes when appropriate |
| Setting gatherTimeout without groupTimeout/cleanup | Incomplete groups linger | Distinguish both timeouts, manage MessageGroupStore |
| Enabling partial release with a 3-of-3 processor | Processor fails when group only has 2 | Dedicated partial report contract and factory |
| Counting replies instead of recipient identities | One duplicate supplier masks a missing supplier | Deduplicate by requestId + supplierId |
| Deleting group immediately upon release | Late reply may create a new group | Retention/tombstone and late-arrival policy |
| Unconditionally retrying whole Scatter-Gather | Re-invokes branches that already had side effects | Per-supplier idempotency and retry budget |
| Using MessageHeaders.ID for deduplication | Technical ID may change across redelivery | Business requestId and supplierId |
| Unbounded thread pool | Overloads HTTP/DB and queues | Bounded pool, rate limit, circuit breaker |
| Treating an ACCEPTED quote as complete | Decides before a final price exists | Clear outcome semantics |
| Choosing bestOffer by arrival order | Non-deterministic results | Deterministic price and tie-break comparator |
| Not logging expected/received | Unknown which branch is missing | Manifest, metrics, tracing |

## 25. Practice exercise: Gathering results from three order-check services

An order-processing system needs results from three services:

- **inventoryCheck**: is there enough stock?
- **fraudCheck**: what is the risk level?
- **shippingEstimate**: what is the estimated shipping cost?

Request:

~~~java
record OrderAssessmentRequest(
        String requestId,
        String orderId,
        String tenantId,
        int itemCount) {}
~~~

The three branches return typed results:

~~~text
InventoryOutcome:
  supplierId = INVENTORY
  available = true/false

FraudOutcome:
  supplierId = FRAUD
  risk = LOW / MEDIUM / HIGH

ShippingOutcome:
  supplierId = SHIPPING
  estimatedCost = valid monetary amount
~~~

A combined **AssessmentReport**:

1. Original requestId.
2. Sources that responded.
3. Outcome of each source, including failure outcomes if any.
4. Status COMPLETE, DEGRADED, INCOMPLETE, or FAILED per contract.
5. Decision: APPROVE, MANUAL_REVIEW, or HOLD.

### 25.1. Practice steps

1. Build three ports using outcome records or a sealed hierarchy with clear supplier identifiers.
2. Create an IntegrationFlow with distribution Scatter-Gather and three recipientFlows.
3. Add ExecutorChannel with a bounded ThreadPoolTaskExecutor to test parallel execution.
4. Have each branch return **a non-null result**; known domain errors become terminal failure outcomes with safe codes.
5. Use Aggregator to produce AssessmentReport when all three terminal outcomes arrive.
6. Inspect the actual correlationId/sequenceNumber/sequenceSize received at each branch and Gather.
7. Use CountDownLatch to prove the three branches can overlap.
8. Make fraudCheck slower than the other two branches and prove Aggregator waits per policy.
9. Make shippingEstimate return no reply and verify gatherTimeout and group state/cleanup.
10. Add groupTimeout and a partial processor for an INCOMPLETE report listing missing sources.
11. Send two different requestIds concurrently; outcomes must never mix.
12. Simulate a duplicate reply from inventoryCheck and a late reply after a partial report.
13. Have fraudCheck throw an async exception; build an error flow with valid compensation or quarantine if impossible.
14. Retry the request after one branch caused a side effect; verify idempotency key per logical action.
15. Add metrics for duration, expected/received, supplier failures, pending groups, and late replies.

### 25.2. Acceptance criteria

| Criterion | Expected observation |
| --- | --- |
| Proper fan-out | All three suppliers invited once per policy |
| Parallelism | All three branches hit the concurrency probe before release |
| Correlation | Each request has its own group |
| Complete gather | 3/3 terminal outcomes produce one AssessmentReport |
| Branch business error | Represented as an outcome without erasing the other two branches |
| Branch technical error | Clear error flow/retry or incomplete report |
| Group timeout | Does not report COMPLETE if replies are still missing |
| Duplicate reply | Not counted as a fourth supplier |
| Late reply | Follows freeze or revision policy |
| Replay | Causes no duplicate side effects outside contract |
| Monitoring | Distinguishes timeouts, errors, incomplete, duplicates, and latency |

### 25.3. Self-check questions

1. How does Scatter's role differ from Gather's?
2. Does PublishSubscribeChannel create multiple threads by default?
3. How do auction and distribution differ in selecting recipients?
4. Why must sequenceSize reflect the number of recipients actually selected?
5. Where must a branch's replyChannel header lead?
6. Does a terminal UNAVAILABLE outcome count as a reply?
7. Does an ErrorMessage on the global errorChannel automatically count as a reply for Aggregator?
8. Why might the same requestId have multiple correlation groups across retries?
9. Is a Gather based on arrival order deterministic?
10. How do gatherTimeout and groupTimeout differ?
11. When partial release is enabled, why is a QuoteReportFactory requiring 3 outcomes no longer suitable?
12. What problem arises when one supplier sends two replies while another stays silent?
13. How does expireGroupsUponCompletion affect late replies?
14. Why doesn't increasing worker threads automatically solve all timeouts?
15. When should a request/reply ScatterGatherHandler be replaced by a durable workflow?

## 26. Pre-deployment checklist

- Clearly chose **auction** or **distribution** per supplier invitation rules.
- Bounded the number of recipients and concurrent scattered requests.
- Parallelism implemented with suitable executors/channels and **tested**.
- Each request has its own correlation group; each branch preserves sequence metadata.
- Final endpoint of each branch returns a **non-null reply** when Gather requires it.
- All replies return to the configured gather/replyChannel.
- Expected suppliers manifest is managed, not inferred from arrived reply count.
- ReleaseStrategy accurately reflects all-of-N, K-of-N, or business deadline.
- ErrorMessage and failure outcomes are separated; async errors have errorChannel/recovery.
- Supplier timeout, groupTimeout, gatherTimeout, and Gateway timeout have a consistent budget.
- Partial results are marked INCOMPLETE and list missing sources.
- QuoteReport/AssessmentReport does not depend on reply arrival order.
- Duplicate protection exists per requestId + supplierId or logical action.
- MessageGroupStore, group expiry, tombstones, and late-arrival policy match the SLA.
- Persistent progress/outbox/inbox exists if recovery across restarts is required.
- Supplier side effects have proper idempotency or reconciliation.
- Thread pools, HTTP connection pools, queues, and rate limits are bounded.
- Logs/metrics distinguish scatter attempts, supplier outcomes, and completed/incomplete gathers.
- Tests cover at least: success, one failure outcome, missing reply, async error, concurrent requests, parallel overlap, duplicates, and timeout.

**Conclusion:** Gathering results from parallel branches is more than collecting a few messages. A reliable Scatter-Gather must define **who is invited**, **which request each reply belongs to**, **what counts as complete**, **what happens when a branch errors or lags**, and **when a report may be published**. In Spring Integration, combining ScatterGatherHandler, RecipientListRouter or PublishSubscribeChannel, Aggregator, correlation/sequence, ExecutorChannel, and proper error handling builds a fast, testable, observable aggregation pipeline without hiding missing results.

## References

- [Spring Integration Reference — Scatter-Gather](https://docs.spring.io/spring-integration/reference/scatter-gather.html): auction/distribution, ScatterGatherHandler, replyChannel, error handling, gatherTimeout, and configuration.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): MessageGroup, correlation/release strategy, groupTimeout, partial results, and late arrivals.
- [Spring Integration Reference — PublishSubscribeChannel](https://docs.spring.io/spring-integration/reference/channel/configuration.html): executor, applySequence, and error handling.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): scatterGather, recipientFlow, outputProcessor, and channel.
- [Spring Integration API — ScatterGatherSpec](https://docs.spring.io/spring-integration/docs/6.5.2/api/org/springframework/integration/dsl/ScatterGatherSpec.html): gatherTimeout, gatherChannel, and errorChannel.
- [Spring Integration API — AggregatorSpec](https://docs.spring.io/spring-integration/docs/6.2.6/api/org/springframework/integration/dsl/AggregatorSpec.html): groupTimeout, sendPartialResultOnExpiry, releaseStrategy.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): ErrorMessage, errorChannel, and synchronous/asynchronous exception handling.
- [Enterprise Integration Patterns — Scatter-Gather](https://www.enterpriseintegrationpatterns.com/patterns/messaging/BroadcastAggregate.html): pattern for broadcasting a request to multiple recipients and aggregating replies.
