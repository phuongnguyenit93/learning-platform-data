# Splitter and Downstream Aggregator

## Lesson Objectives

In the **Splitter** chapter of the **SPRING_INTEGRATION_CORE** module, this lesson connects splitting a message into multiple parts with downstream result aggregation. The focus is on designing a complete message flow using `Message`, `MessageChannel`, endpoints, and the Java DSL, while determining how transformers, routers, filters, and error handling affect group completion.

After this lesson, you will be able to:

- Explain the roles of `correlationId`, `sequenceNumber`, and `sequenceSize`.
- Write a `split → process each part → aggregate` flow using the Java DSL.
- Distinguish group completion conditions from the calculation that produces the combined result.
- Handle rejected items, late results, timeouts, and empty inputs.
- Design tests for completeness, group isolation, and result ordering.

Examples use Java 17 and Spring Integration 6.5 APIs. The project should manage dependency versions with an appropriate BOM; the code snippets do not require choosing a specific Spring Boot version. The main configuration is an example running inside a Spring Context, while extension snippets clearly indicate where they substitute.

## 1. Why Does a Splitter Often Pair with an Aggregator?

Suppose an order has three product lines. The system needs to calculate the price for each line and then return one summary table for the entire order:

~~~text
Order O-100
  Line 1: 2 × 120000
  Line 2: 3 ×  50000
  Line 3: 1 ×  70000

Result:
  Line 1: 240000
  Line 2: 150000
  Line 3:  70000
  Total:  460000
~~~

The splitter defines the units of work. Intermediate endpoints process each unit. The aggregator gathers related results before building an order-level response.

~~~mermaid
flowchart LR
    A["Message containing Order"] --> S["Splitter"]
    S --> P1["Message line 1"]
    S --> P2["Message line 2"]
    S --> P3["Message line 3"]
    P1 --> W["Process each line"]
    P2 --> W
    P3 --> W
    W --> G["Aggregator: group and wait for completeness"]
    G --> R["Message containing OrderSummary"]
~~~

In this lesson, a **downstream aggregator** is an aggregator positioned after the splitter in the message path; there may be multiple channels and processing steps between the two endpoints.

| Component | Question to answer | Example in the order flow |
|---|---|---|
| Splitter | What parts is one request split into? | One `LineTask` per order line |
| Transformer or service activator | What result does each part produce? | One `LineResult` |
| Correlation strategy | Which group does this result belong to? | Group of one order split |
| Release strategy | When can the combined result be produced? | Once results for all lines have arrived |
| Output processor | What is the result group converted into? | `OrderSummary` containing the list and total amount |
| Message group store | Where does waiting aggregation data live? | Application memory in the example |

An aggregator holds group state, so group lifecycle is part of flow design. Grouping and result-building concepts are covered in the [Spring Integration Aggregator documentation](https://docs.spring.io/spring-integration/reference/aggregator.html).

The combined result does not have to reconstruct the original payload. You can combine three order lines into a report, a sum total, or an object containing both successes and failures.

## 2. The Message Contract Between Splitter and Aggregator

### 2.1. Three Headers to Preserve

With a collection of known size, a splitter with `applySequence` enabled supplies sequence metadata on child messages:

| Header | Meaning | Example |
|---|---|---|
| `correlationId` | Identifies the group of the current split | `C-100` |
| `sequenceNumber` | Element position, starting from 1 | `1`, `2`, `3` |
| `sequenceSize` | Total number of elements in the sequence | `3` |

The splitter enables this behavior by default; the example below configures it explicitly to show the contract. See [splitter sequence configuration](https://docs.spring.io/spring-integration/reference/6.5/aggregator.html) and [SplitterSpec API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/SplitterSpec.html).

Example at one split level, when the input message has `id = C-100`:

~~~text
Original message: id=C-100, payload=Order(O-100, 3 lines)

Child message 1:
  id=M-1, correlationId=C-100, sequenceNumber=1, sequenceSize=3

Child message 2:
  id=M-2, correlationId=C-100, sequenceNumber=2, sequenceSize=3

Child message 3:
  id=M-3, correlationId=C-100, sequenceNumber=3, sequenceSize=3
~~~

Child messages have their own identities. `orderId` is a business key; `correlationId` is the message-linking key for the current aggregation step. Do not assume these two values are always identical.

### 2.2. Keeping Required Metadata When Replacing Payloads

After pricing a line, the payload changes from `LineTask` to `LineResult`. Group-linking headers must still continue onward:

~~~text
LineTask + sequence headers
            |
            v
        Transformer
            |
            v
LineResult + sequence headers
~~~

In the Java DSL, the `split`, `transform`, and `aggregate` verbs create the corresponding endpoints. Having a transformer return a payload is a convenient way to use the framework's reply-building mechanism. See [DSL Basics](https://docs.spring.io/spring-integration/reference/dsl/java-basics.html).

If you construct a new message manually, proactively copy the headers that must travel onward:

~~~java
Message<LineResult> resultMessage = MessageBuilder
        .withPayload(result)
        .copyHeaders(partMessage.getHeaders())
        .build();
~~~

This snippet illustrates message creation, where `result` and `partMessage` are supplied by the processing step. It requires `org.springframework.messaging.Message` and `org.springframework.messaging.support.MessageBuilder`.

System headers `id` and `timestamp` on the output message are managed by the builder. The goal is preserving business metadata and sequence-linking metadata without forcing the new message to reuse the old message's identity.

When messages cross a broker or process boundary, verify header mappings, deserialized data types, and the actual correlation key. A flow working in memory does not prove the contract across external systems.

## 3. Grouping Right and Knowing When Done Are Two Separate Concerns

An aggregator typically requires three independent decisions:

1. **Correlation:** selecting a group key from a message.
2. **Release:** deciding whether a group is ready.
3. **Aggregation:** computing the result payload when the group releases.

In the default configuration, the group key comes from `correlationId`. For fixed-size sequences, `SimpleSequenceSizeReleaseStrategy` compares accumulated message count against expected size. This strategy does not check for duplicate `sequenceNumber` values. Therefore, "count reached" is meaningful only when the flow guarantees each part yields exactly one result. See [SimpleSequenceSizeReleaseStrategy](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/SimpleSequenceSizeReleaseStrategy.html).

For a three-part group, the normal progression is:

~~~text
Receive part 2: group has 1/3 → wait
Receive part 1: group has 2/3 → wait
Receive part 3: group has 3/3 → build OrderSummary
~~~

Part 3 arriving does not itself prove parts 1 and 2 are present. That is why you must not use a rule like "release when a message arrives with `sequenceNumber == sequenceSize`" in flows that may run concurrently.

If you configure only `.aggregate()`, the default output processor produces a message containing a list of the group's payloads. When an explicit return contract is required, provide an output processor that builds a domain object. See [DefaultAggregatingMessageGroupProcessor](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/DefaultAggregatingMessageGroupProcessor.html).

In the next example, every order line produces a result, including lines rejected for invalid quantity. Thanks to that, the aggregator can still fulfill the count contract.

## 4. Complete Java DSL Example: Pricing Each Line Then Aggregating the Order

### 4.1. Dependencies and Organization

If the project already manages Spring Integration versions, the dependency for the main configuration is:

~~~xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-core</artifactId>
</dependency>
~~~

Place the class below in package `demo.integration`. The example uses `@EnableIntegration` to provide Spring Integration infrastructure when running in a standard Spring Context.

Main flow:

~~~text
orderInput
    → splitOrder
    → priceLine
    → orderAggregator
    → orderResults

Incomplete groups or late messages
    → aggregationDiscards
~~~

`orderResults` and `aggregationDiscards` are queues so results can be observed in tests. The example uses no gateway, so `send()` does not return an `OrderSummary`; consumers read results from `orderResults`.

### 4.2. Data Model and Configuration

~~~java
package demo.integration;

import java.math.BigDecimal;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.store.MessageGroup;
import org.springframework.integration.store.MessageGroupStore;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.MessageChannel;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class SplitAggregateConfig {

    public record OrderLine(
            int position,
            String sku,
            int quantity,
            BigDecimal unitPrice) {

        public OrderLine {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(unitPrice, "unitPrice");
            if (position < 1 || unitPrice.signum() < 0) {
                throw new IllegalArgumentException(
                        "position must be >= 1 and unitPrice must be >= 0");
            }
        }
    }

    public record Order(String orderId, List<OrderLine> lines) {
        public Order {
            Objects.requireNonNull(orderId, "orderId");
            lines = List.copyOf(lines);
            if (lines.isEmpty()) {
                throw new IllegalArgumentException("Order must have order lines");
            }
            long distinctPositions = lines.stream()
                    .map(OrderLine::position)
                    .distinct()
                    .count();
            if (distinctPositions != lines.size()) {
                throw new IllegalArgumentException("position must not be duplicated");
            }
        }
    }

    public record LineTask(String orderId, OrderLine line) {
    }

    public enum LineStatus {
        ACCEPTED, REJECTED
    }

    public record LineResult(
            String orderId,
            int position,
            String sku,
            LineStatus status,
            BigDecimal amount,
            String reason) {
    }

    public record OrderSummary(
            String orderId,
            List<LineResult> lines,
            BigDecimal acceptedTotal,
            boolean allSuccessful) {

        public OrderSummary {
            lines = List.copyOf(lines);
        }
    }

    @Bean
    public MessageChannel orderInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel orderResults() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel aggregationDiscards() {
        return new QueueChannel(100);
    }

    @Bean
    public MessageGroupStore orderGroupStore() {
        return new SimpleMessageStore();
    }

    @Bean
    public IntegrationFlow orderFlow(
            @Qualifier("orderInput") MessageChannel input,
            @Qualifier("orderResults") QueueChannel results,
            @Qualifier("aggregationDiscards") QueueChannel discards,
            @Qualifier("orderGroupStore") MessageGroupStore groupStore) {

        return IntegrationFlow.from(input)
                .split(
                        Order.class,
                        SplitAggregateConfig::splitOrder,
                        splitter -> splitter.applySequence(true))
                .<LineTask, LineResult>transform(
                        SplitAggregateConfig::priceLine)
                .aggregate(aggregator -> aggregator
                        .id("orderAggregator")
                        .messageStore(groupStore)
                        .outputProcessor(SplitAggregateConfig::summarize)
                        .groupTimeout(5_000)
                        .sendPartialResultOnExpiry(false)
                        .expireGroupsUponCompletion(false)
                        .expireGroupsUponTimeout(false)
                        .minimumTimeoutForEmptyGroups(60_000)
                        .discardChannel(discards))
                .channel(results)
                .get();
    }

    private static List<LineTask> splitOrder(Order order) {
        return order.lines().stream()
                .map(line -> new LineTask(order.orderId(), line))
                .toList();
    }

    private static LineResult priceLine(LineTask task) {
        OrderLine line = task.line();

        if (line.quantity() <= 0) {
            return new LineResult(
                    task.orderId(),
                    line.position(),
                    line.sku(),
                    LineStatus.REJECTED,
                    BigDecimal.ZERO,
                    "INVALID_QUANTITY");
        }

        BigDecimal amount = line.unitPrice()
                .multiply(BigDecimal.valueOf(line.quantity()));

        return new LineResult(
                task.orderId(),
                line.position(),
                line.sku(),
                LineStatus.ACCEPTED,
                amount,
                null);
    }

    private static OrderSummary summarize(MessageGroup group) {
        List<LineResult> lines = group.getMessages().stream()
                .map(message -> (LineResult) message.getPayload())
                .sorted(Comparator.comparingInt(LineResult::position))
                .toList();

        BigDecimal acceptedTotal = lines.stream()
                .filter(line -> line.status() == LineStatus.ACCEPTED)
                .map(LineResult::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        boolean allSuccessful = lines.stream()
                .allMatch(line -> line.status() == LineStatus.ACCEPTED);

        return new OrderSummary(
                lines.get(0).orderId(),
                lines,
                acceptedTotal,
                allSuccessful);
    }
}
~~~

### 4.3. Design Choices in the Example

**Splitting into `LineTask` instead of extracting only `OrderLine`.** Each part already carries `orderId`, decoupling pricing logic and business results from looking up the original order again.

**Materializing into a `List`.** The splitter knows how many elements to emit for a small order. This is an intentional choice for the example; for very large datasets, memory costs must be redesigned.

**Keeping default correlation and release.** The flow does not override `correlationStrategy` or `releaseStrategy`, because the sequence metadata generated by the splitter already matches the one-part-one-result rule.

**Sorting by business `position`.** The output processor builds the list per the return contract. Task completion order does not dictate display order.

**Returning an aggregated summary record.** `OrderSummary` makes the downstream data type explicit, holding both per-line results and the total amount. The result list is a copy, holding no reference to the store's internal collection.

**Not treating an incomplete group as a completed order.** `sendPartialResultOnExpiry(false)` sends groups failing to complete before timeout to the discard channel. The corresponding DSL methods are documented in [AggregatorSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/AggregatorSpec.html) and [CorrelationHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html).

**Retaining group traces briefly after completion.** The two options `expireGroupsUponCompletion(false)` and `expireGroupsUponTimeout(false)` allow rejecting late-arriving messages while metadata remains. The 60-second window in the example is illustrative; production must choose retention times based on retry limits and real latencies.

This example performs pure pricing without external side effects. When replacing `priceLine` with a service call, add per-part timeout, retry, and idempotency rules.

## 5. "Group Complete" Differs from "Every Part Succeeded"

With three order lines where the second line has `quantity = 0`, the flow emits three results:

~~~text
Line 1 → ACCEPTED, amount=240000
Line 2 → REJECTED, amount=0, reason=INVALID_QUANTITY
Line 3 → ACCEPTED, amount=70000

Aggregator receives all 3 results:
  acceptedTotal = 310000
  allSuccessful = false
~~~

The group has enough information to reply even though one business outcome failed.

The two conditions can be expressed as:

~~~text
complete = final results have been received for all expected parts

allSuccessful = every final result succeeded
~~~

This representation works well for multi-item checks, multi-source quote requests, or ingesting a batch of records. The caller knows which part failed without having to guess from a silent aggregator.

Do not mechanically convert every exception into `REJECTED`. Expected data errors and programming bugs require different handling. The result contract must specify which errors can be represented as data and which errors fail the entire run.

## 6. Filters and Routers Can Break the "Count Complete" Condition

### 6.1. Filter After Splitter Causes Missing Results

Suppose the splitter emits three messages with `sequenceSize = 3`, and then a filter drops one message:

~~~text
Splitter emits:     1, 2, 3        sequenceSize=3
Filter drops:          2
Aggregator gets:    1,    3        only 2 messages
~~~

Without another completion mechanism, the group keeps waiting. Spring Integration highlights this exact case in its [note on filters before an aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html).

Design options to choose from:

| Business need | Design approach |
|---|---|
| Process only valid parts and no need to report dropped ones | Filter the collection before the splitter so the splitter builds a sequence of the right size |
| Need to report every part, including dropped ones | Emit a `REJECTED` or `SKIPPED` result for that part |
| Accept incomplete results after a wait period | Design a dedicated timeout and partial payload |
| Count is governed by another contract | Supply a custom release strategy and test that contract |

In the order example, returning `LineResult(REJECTED)` preserves one terminal result per line. Merely logging on the filter's discard channel does not solve the aggregator missing a message.

### 6.2. Router Splits Paths but Still Needs a Convergence Point

A router can separate standard lines from lines needing special inspection:

~~~text
                         → standard processing ────┐
Splitter → Router                                  ├→ same aggregator
                         → special inspection ─────┘
~~~

Both branches must:

- Return the same payload contract, such as `LineResult`.
- Preserve the split's correlation metadata.
- Contribute the exact number of results per part expected by the release contract.
- Handle unrouted branches or early terminations.

If one part is sent concurrently down two branches and both return to the aggregator, the message count grows beyond the original sequence. When multiple results per part are needed, model another split/aggregate level or build a matching release contract.

## 7. Handling Errors Without Leaving Groups Waiting Forever

### 7.1. Synchronous vs. Asynchronous Errors

In flows using `DirectChannel`, exceptions from a handler typically propagate back to the caller on the same call stack. When an executor or poller is involved, errors must travel via the proper messaging mechanism; an `ErrorMessage` carries the exception as payload. Setting an `errorChannel` header does not automatically turn every synchronous call into asynchronous error handling. See [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

For a splitter–aggregator pair, the question to answer is: **after an error, does the failing part still produce a final result for the group?**

Example:

~~~text
Part 1 → succeeds → aggregator
Part 2 → service call fails → error flow
Part 3 → succeeds → aggregator
~~~

If the error flow only logs, the aggregator receives two results out of three parts. A timeout is still necessary even when the system has an error channel.

### 7.2. Three Common Error Policies

| Policy | Behavior of the failed part | Group-level behavior |
|---|---|---|
| Retry then return failure result | Bounded retries, then produce a failed `LineResult` | Can receive all results and return a report |
| Abort entire request | Record run failure, cancel or compensate other parts | Needs cancellation orchestration and group cleanup |
| Accept partial results | Failed part contributes no success result | Returns a payload explicitly listing missing parts after deadline |

Under the first policy, the compensating message for the failed part must retain the headers of the **failed child message**. Copying headers from the original order message will not carry that part's position and sequence size.

Illustrative snippet at the recovery point:

~~~java
// failedPart: child message retrieved from error/retry context.
// failureResult: final LineResult for that exact part.
// aggregateInput: channel entering the aggregator, bypassing the splitter.
Message<LineResult> recoveryMessage = MessageBuilder
        .withPayload(failureResult)
        .copyHeaders(failedPart.getHeaders())
        .build();

aggregateInput.send(recoveryMessage);
~~~

To apply this to the main configuration, split out a named channel before the aggregator and have recovery send to that channel. Do not send recovery back to `orderInput`, because that channel expects an `Order` and starts a new split.

The error flow must retrieve the failed message from the exception or actual recovery context. Do not assume the outer `ErrorMessage` wrapper's headers are the child message's headers.

### 7.3. Group Timeout Does Not Cancel In-Flight Tasks

If the second task is still calling an external service when the group expires, the aggregator does not automatically abort that HTTP request or execution thread.

Coordinate across:

- External call timeouts.
- Retry limits.
- Group wait timeouts.
- Gateway or caller reply timeouts.
- Policies for results arriving after the group has closed.

For instance, a caller waiting only 2 seconds while the aggregator waits 5 seconds produces a result after the caller stopped waiting. The flow must decide where that result goes rather than treating caller timeout as proof the group was canceled.

## 8. Timeouts, Partial Results, and Group Lifecycle

### 8.1. `groupTimeout` Is an Idle Period Without New Messages

With `groupTimeout(5_000)`, the group's forced-completion schedule resets whenever a new message arrives while the group remains unreleased. Thus it is a wait window measured from the group's latest message, not by default a 5-second absolute deadline from order receipt. Details are described in [Aggregator and Group Timeout](https://docs.spring.io/spring-integration/reference/aggregator.html#aggregator-and-group-timeout).

Example:

~~~text
t = 0s: part 1 arrives → timeout scheduled for t = 5s
t = 4s: part 2 arrives → timeout shifts to t = 9s
t = 9s: part 3 still missing → timeout handling runs
~~~

A group exists only after at least one message reaches the aggregator. If all parts are lost or fail before the aggregation point, the aggregator's timeout never detects that request; track request-level deadlines separately.

When business logic requires an absolute cutoff time, carry the deadline in the contract and use a matching timeout expression, along with rules for messages arriving past the deadline.

### 8.2. Partial Must Be a Deliberate Separate Contract

`sendPartialResultOnExpiry(true)` allows producing output from available messages when the group fails to meet release conditions at expiration. Flipping this single flag is not enough to turn `OrderSummary` into a proper partial response.

A partial response should state at least:

~~~text
requestId:       R-100
status:          PARTIAL
expectedCount:   3
receivedCount:   2
completedParts:  [1, 3]
missingParts:    [2]
acceptedTotal:   310000
~~~

The main example uses `false` to avoid returning a line-deficient total disguised as a fully processed order. If partial results are desired, update both the output processor and the result data type.

### 8.3. Completing a Group vs. Expiring a Group Have Different Effects

| Option | Effect to watch for |
|---|---|
| Keep metadata after completion | Allows detecting and discarding late messages with the same key |
| `expireGroupsUponCompletion(true)` | Deletes the group after normal completion; late messages with the same key can open a new group |
| `expireGroupsUponTimeout(true)` | Allows deleting the group after timeout; consider late results |
| `minimumTimeoutForEmptyGroups(...)` | Bounds how long empty-group metadata is kept after release per the corresponding mechanism |
| Reaper or purge mechanism | Cleans up stale state per store and endpoint policies |

Lifecycle options are described in [CorrelationHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html). Scheduled group sweeping can use [MessageGroupStoreReaper](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroupStoreReaper.html); merely declaring a reaper does not replace scheduling invocations for it.

Metadata retention time is a bounded protection window. Once metadata is removed, an old message with the same correlation key can look like the start of a new group. If longer duplicate protection is required, implement business-level idempotency storage.

## 9. Parallel Processing: Splitters Do Not Spawn Threads

In the main configuration, consecutive steps use synchronous channels up to the output queue. Splitting into multiple messages does not mean lines run in parallel.

You can insert an `ExecutorChannel` right after the splitter:

~~~text
Splitter → ExecutorChannel → price each line → Aggregator
~~~

The following beans extend `SplitAggregateConfig`:

~~~java
@Bean
public org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor
        lineExecutor() {

    var executor =
            new org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("order-line-");
    return executor;
}

@Bean
public MessageChannel lineWorkers(
        @Qualifier("lineExecutor")
        org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor executor) {

    return new org.springframework.integration.channel.ExecutorChannel(executor);
}
~~~

Then inject `@Qualifier("lineWorkers") MessageChannel workers` into the flow bean method and insert `.channel(workers)` between `.split(...)` and `.transform(...)`.

With this extension:

- Results may arrive at the aggregator out of input order.
- Element-processing handlers must be thread-safe under concurrent calls.
- A full executor queue may cause task submission rejections.
- Queue wait time at the executor contributes to overall request latency.
- Retries and recovery must handle exceptions occurring on executor threads.

If a send is interrupted partway through, some parts may already have been dispatched for execution. Therefore, do not assume the entire order went unprocessed just because the caller caught an exception.

The aggregator groups results by key and release condition; sorting results inside `summarize` is a separate choice to satisfy business ordering. If downstream consumers need individual messages in order rather than one combined object, consider a resequencer.

## 10. Empty Collections and Unknown-Size Sources

### 10.1. No Child Messages Means No Group to Wait On

If the splitter returns an empty collection, it emits zero elements to the aggregator. There is no "child message #0" to announce group completion. The splitter can use a discard channel for inputs yielding empty containers; a `null` result has separate flow-termination semantics. See [Splitter](https://docs.spring.io/spring-integration/reference/splitter.html).

In the main configuration, the `Order` constructor rejects empty lists before a message enters the flow. That is a rule of the example, not a mandatory rule for every system.

If empty orders are valid, a clean design places a router before the splitter:

~~~text
Order with no lines → create empty OrderSummary → output

Order with lines    → splitter → process each line → aggregator → output
~~~

The empty branch must construct the result directly; waiting for an aggregator timeout will not help because no message ever creates a group.

### 10.2. Iterators and Streams May Not Supply Size

When the splitter cannot determine the size of an iterator or stream source, `sequenceSize` may be `0`. Sequence-count strategies then have no total element count to wait for. Certain specialized splitters can infer size, so inspect the actual implementation. See [Splitter Iterator Support](https://docs.spring.io/spring-integration/reference/splitter.html#splitter-iterators).

Design approaches:

| Input characteristics | Recommended direction |
|---|---|
| Small dataset, fits in memory | Convert to a collection before splitting |
| Large dataset, but total known from manifest | Carry expected count and build a matching release contract |
| Dataset with unknown size upfront | Use a verifiable completion protocol or time windows |
| Unbounded or continuous stream | Use micro-batches/windows with clear business boundaries |

An "all emitted" marker only indicates the producer finished sending. In parallel flows, the marker may arrive before in-flight results. To release based on a marker, know the expected total parts and verify results for those parts have arrived.

## 11. Custom Correlation, Retries, and Deduplication

### 11.1. Choosing Keys for Exactly-Once Processing

The main example uses splitter-generated correlation, so two input messages sharing `orderId` still form two independent groups.

This fits when the same order is intentionally repriced twice. It does not automatically prevent reprocessing a duplicated request.

If overriding correlation with `orderId`, decide upfront:

- Whether two concurrent executions for the same order are allowed.
- Whether different tenants can share an `orderId`.
- Whether after a retry, old and new results may share the same group.
- When a key is allowed to be reused.

A contract-driven key can combine `tenantId + orderId + processingRunId`. The key should have a stable representation and well-defined equality rules, especially with persistent stores.

### 11.2. Retries Must Not Create Extra Terminal Results

Suppose a group needs three parts but receives:

~~~text
Part 1 result
Part 1 result resent with a new Message.id
Part 3 result
~~~

The count is already three, yet part 2 is still missing. Count-based strategies do not replace duplicate-result detection.

Distinguish:

| Identity | Purpose |
|---|---|
| `Message.id` | Identifies a specific message instance |
| `processingRunId` or correlation key | Identifies a group-level processing run |
| `partId` or line position in a run | Identifies one unit of work |
| Side-effect idempotency key | Prevents repeating business actions such as ledger writes or payments |

One design places an idempotent receiver before the aggregator keyed by run and element. Even if a custom release strategy inspects the set of distinct part keys, you still must deduplicate inside the output processor; merely counting distinct keys does not strip duplicates from totals calculation.

If retrying the entire request with a new input message, the splitter can create a new group. Element-level deduplication and root-request deduplication are two scopes that must be designed separately.

## 12. Nested Splitters and Deployment Limits

### 12.1. Aggregating in Reverse Order of Split Levels

Example of a batch with multiple orders, each with multiple lines:

~~~text
Batch
  → batch-level splitter
      → Order
          → order-level splitter
              → LineTask
              → LineResult
          → order-level aggregator
      → OrderSummary
  → batch-level aggregator
  → BatchSummary
~~~

Each aggregation level must restore the enclosing level's metadata upon completion. Spring Integration supports sequence details for nested structures and `popSequence` behavior in aggregators. When manually creating messages or modifying sequence headers, preserve split-level metadata accurately; see [Sequence Details in Aggregator](https://docs.spring.io/spring-integration/reference/6.5/aggregator.html).

In this design, the order-level aggregator groups a single order's lines; the batch-level aggregator groups `OrderSummary` objects. If both group by an arbitrary `orderId` while dropping batch level, separate runs can collide.

### 12.2. In-Memory Stores Fit Examples, Not Crash Recovery

`SimpleMessageStore` in this lesson holds pending aggregation data inside the current process. If the application stops, the example has no mechanism to recover incomplete groups.

For recovery or multi-instance requirements, decide:

- Whether each group is routed to the same instance.
- Whether a shared or persistent store is used.
- Whether locking coordinates across instances.
- Whether payloads and headers serialize/deserialize with exact types.
- How in-progress groups after a restart are resumed or terminated.
- Whether emitting output and updating state require transactions or an outbox.

Merely swapping the store to a shared backend does not solve concurrency coordination and consistency on its own. An in-process lock does not coordinate across processes.

State cost can be estimated as:

~~~text
Pending aggregation footprint
  ≈ total payloads and headers sitting in incomplete groups
    + metadata of completed groups not yet purged
    + store auxiliary structures
~~~

Limits on group size, open group count, and state retention must accompany queue limits. If most waiting time is spent waiting on a slow service, increasing worker counts can cause open groups to accumulate rapidly.

## 13. Testing the Splitter–Aggregator Contract

This section provides test code for learners to run in a project with JUnit 5, `spring-test`, and Spring Integration. This is practice material for the lesson, not a report that tests have already been executed.

### 13.1. Integration Tests for the Main Flow

Place the test class in the same package as the configuration:

~~~java
package demo.integration;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import demo.integration.SplitAggregateConfig.LineStatus;
import demo.integration.SplitAggregateConfig.Order;
import demo.integration.SplitAggregateConfig.OrderLine;
import demo.integration.SplitAggregateConfig.OrderSummary;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = SplitAggregateConfig.class)
class SplitAggregateFlowTest {

    @Autowired
    @Qualifier("orderInput")
    MessageChannel input;

    @Autowired
    @Qualifier("orderResults")
    QueueChannel results;

    @Test
    void aggregatesAllThreeLines() {
        Order order = new Order("O-100", List.of(
                line(1, "A", 2, "120000"),
                line(2, "B", 3, "50000"),
                line(3, "C", 1, "70000")));

        assertTrue(input.send(MessageBuilder.withPayload(order).build()));

        OrderSummary summary = receiveSummary();

        assertEquals("O-100", summary.orderId());
        assertEquals(List.of(1, 2, 3), summary.lines().stream()
                .map(result -> result.position())
                .toList());
        assertEquals(0, new BigDecimal("460000")
                .compareTo(summary.acceptedTotal()));
        assertTrue(summary.allSuccessful());
    }

    @Test
    void rejectedLineStillContributesOneFinalResult() {
        Order order = new Order("O-200", List.of(
                line(1, "A", 1, "100000"),
                line(2, "B", 0, "50000")));

        assertTrue(input.send(MessageBuilder.withPayload(order).build()));

        OrderSummary summary = receiveSummary();

        assertEquals(2, summary.lines().size());
        assertEquals(LineStatus.REJECTED, summary.lines().get(1).status());
        assertEquals("INVALID_QUANTITY", summary.lines().get(1).reason());
        assertEquals(0, new BigDecimal("100000")
                .compareTo(summary.acceptedTotal()));
        assertFalse(summary.allSuccessful());
    }

    @Test
    void separateInputMessagesWithSameOrderIdCreateSeparateGroups() {
        Order first = new Order("O-SAME", List.of(
                line(1, "A", 1, "10")));
        Order second = new Order("O-SAME", List.of(
                line(1, "B", 1, "20")));

        assertTrue(input.send(MessageBuilder.withPayload(first).build()));
        assertTrue(input.send(MessageBuilder.withPayload(second).build()));

        OrderSummary firstSummary = receiveSummary();
        OrderSummary secondSummary = receiveSummary();

        assertEquals(0, new BigDecimal("10")
                .compareTo(firstSummary.acceptedTotal()));
        assertEquals(0, new BigDecimal("20")
                .compareTo(secondSummary.acceptedTotal()));
    }

    private OrderSummary receiveSummary() {
        Message<?> message = results.receive(1_000);
        assertNotNull(message, "Flow must produce an aggregated result");
        assertTrue(message.getPayload() instanceof OrderSummary);
        return (OrderSummary) message.getPayload();
    }

    private static OrderLine line(
            int position, String sku, int quantity, String price) {

        return new OrderLine(
                position, sku, quantity, new BigDecimal(price));
    }
}
~~~

The tests use queue `receive` with a timeout, avoiding arbitrary sleeps. The third test verifies isolation between two sends under default correlation; it does not prove business-level deduplication.

### 13.2. Scenarios to Test When Extending

| Scenario | Data or way to trigger | What to verify |
|---|---|---|
| Results arrive out of order | Give parts different processing durations | Only one summary emitted and return order matches contract |
| Two interleaved groups | Send parts for two correlation keys alternately | Payloads from the two groups never mix |
| One part missing | Omit sending one result into the aggregator | Does not release normally; timeout handles per policy |
| Filter drops element | Drop part #2 after the splitter | Reproduce missing group or confirm compensating result |
| Duplicate result sent | Send two messages with different IDs for the same part key | No double counting per chosen mechanism |
| Late result arrives | Send after completion/timeout | Discarded or starts new group per lifecycle policy |
| Empty input list | Create a request with no lines | Rejected early or returns empty summary directly |
| Iterator without total | Create source with unknown part count | Does not rely on default sequence-size release |
| Restart mid-group | Use environment with persistent store | Group resumes or terminates per rules |
| Executor overloaded | Use small queue and controlled blocking handler | Request failures are not silently lost |

To test timeouts quickly, create a test configuration with a short wait window and a named channel directly before the aggregator. Intentionally send messages containing `correlationId`, `sequenceNumber`, and `sequenceSize` to that channel; do not rely on random sleep durations hoping to produce an incomplete group.

## 14. Diagnosing Groups That Fail to Release

When a request produces no aggregated result, trace one concrete processing run:

~~~text
Original message
  → how many parts were split?
  → which branch did each part enter?
  → which parts produced a final result?
  → what correlation key do the results carry?
  → how many messages has the aggregator stored?
  → what condition is the release strategy waiting on?
  → has the group timed out, completed, or been purged?
~~~

| Symptom | Possible cause to check |
|---|---|
| Group has 2 messages and `sequenceSize=3` | Filter, branch failure, or missing recovery emission |
| `sequenceSize=0` | Split source has unknown size |
| Every result creates its own group | Lost or mis-modified correlation key |
| Two runs got mixed together | Correlation key too broad, key reuse |
| Released before all parts arrived | Duplicate result or release strategy mismatches contract |
| Summary missing lines yet looks complete | Partial result not represented in payload |
| Memory grows even after processing completes | Incomplete groups or completed metadata not purged |
| Timeouts never fire | No message ever reached aggregator or scheduler not running |
| Old message opens a new group | Old group metadata was already deleted |

Useful logs at split points, before aggregation, and at recovery/discard include: processing run, order ID, part key, correlation key, sequence number, sequence size, result status, and endpoint. Avoid logging entire payloads when they are large or contain sensitive data.

Metrics tied to operational contracts should include: open group count, oldest group age, time from first part to release, timed-out group count, discarded message count, and blocked duplicate count.

A well-designed splitter–aggregator pair must answer four questions: which processing run an element belongs to, how many results each part contributes, when the group terminates, and how long residual state is retained.