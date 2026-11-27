# Incomplete group — Handling Incomplete Message Groups

## 1. Objectives and Context

In the **Correlation and state** chapter of the **SPRING_INTEGRATION_CORE** module, an incomplete group is a situation where a group has received some messages but has not yet met the condition to aggregate. This lesson connects `Message`, `MessageChannel`, the aggregator endpoint, routers, and Java DSL to design intentional ways to end waiting.

After this lesson, you will be able to:

- Distinguish a "group missing data" from a "group closed in the framework."
- Identify causes that make a group wait forever.
- Choose among partial results, full failure, and controlled retries.
- Configure wait times, metadata lifecycles, and discarded-message channels.
- Design output data so consumers know what is still missing.
- Build test cases for duplicates, late messages, and application restarts.

Suppose a service fetches shipping quotes from three providers **A, B, C**. Each inquiry has its own request key. If A and B respond while C does not, the service must decide when to stop waiting and what to report to the caller.

## 2. Understanding Incomplete Groups Properly

### 2.1. Correlation, Release, and Output Are Three Separate Decisions

An aggregator holds messages by correlation key and asks `ReleaseStrategy` whether the group is ready to aggregate. `MessageGroupProcessor` creates the output result from the released group. Correlation defaults to using the `correlationId` header; you can replace it with a custom strategy. These are independent roles in the aggregator mechanism. [Aggregator documentation](https://docs.spring.io/spring-integration/reference/aggregator.html)

In the quote example:

| Decision | Business question | Lesson's choice |
| --- | --- | --- |
| Correlation | Which replies belong to the same inquiry? | Same `requestKey` |
| Normal release | Have all required replies arrived? | All of A, B, and C present |
| Output | What structure does the consumer need? | Received quotes, missing list, completeness flag |
| Timeout | Until when to wait? | Configured idle period expires |
| After closing | How are late replies handled? | Routed to a dedicated monitoring channel |

Let:

~~~text
E = {A, B, C}       expected set of providers
R = {A, B}          set of providers that replied
M = E \ R = {C}     missing set
~~~

The group is complete when `M` is empty. Under a contract requiring all three sources, a group with two quotes is still incomplete even if it can already return something useful to the user.

### 2.2. Lifecycle Completion Does Not Guarantee Business Completeness

`MessageGroup` tracks completion state and holds related messages. Group lifecycle state exists to manage processing inside the framework. [MessageGroup API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/store/MessageGroup.html)

The application should model separately:

- **Data complete:** all contracted sources have arrived.
- **Done waiting:** the application will not wait any longer for this inquiry.

An inquiry may be done waiting while having only two out of three quotes. Thus, a business field like `complete` must be computed from the received sources rather than inferred from the fact that the aggregator emitted output.

### 2.3. Reaching the Count Does Not Mean Having All Components

`SimpleSequenceSizeReleaseStrategy` compares message count against expected sequence size; this strategy does not check for duplicate `sequenceNumber`s. Do not treat it as a deduplication mechanism. [SimpleSequenceSizeReleaseStrategy API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/aggregator/SimpleSequenceSizeReleaseStrategy.html)

For instance, A sends two messages with different IDs and B sends one message:

~~~text
Messages: A1, A2, B1
Count:    3
Sources:  {A, B}
Missing:  {C}
~~~

If `group.size() == 3` were used, the application would draw the wrong conclusion. In this lesson, release is based on the set of unique sources. Deduplicating messages before storing is still necessary if you want to prevent groups from growing bloated.

## 3. Why Might a Group Never Become Complete?

Do not assume every incomplete group is caused by a slow external service.

| Cause | Example | Remediation direction |
| --- | --- | --- |
| Branch does not respond | C fails to reply due to a network error | Deadline, bounded retry, or partial result |
| Filter drops a reply | Filter discards an invalid quote while expectation stays three sources | Record an error outcome or adjust contract before dispatching branches |
| Router does not dispatch all branches | Only A and B serve that delivery region | Store the actual selected source set |
| Inconsistent correlation | A uses order ID, B uses inquiry ID | Normalize keys before grouping |
| Transformer loses metadata | Drops the `requestKey` header | Preserve or deterministically reconstruct the key |
| Key collision across multiple inquiries | Retry reuses the key of an already closed inquiry | Include version or attempt in the key |
| Mismatched sequence metadata | Expecting three parts while upstream emitted only two | Fix the sequence contract where branches are created |
| State loss | Application stops while groups reside in memory | Choose an appropriate store and design recovery |

For example, if C returns "address not supported," that may be **a valid reply with a no-offer status**. C did respond, just with no price to compare. If a filter deletes that message, the system turns a known outcome into silence.

In real systems, consider a payload like:

~~~text
BranchOutcome:
  source
  status = SUCCESS | NO_OFFER | FAILED
  quote
  errorCode
~~~

Then distinguish "received outcomes from all branches" from "all branches succeeded." The Java example below uses only successful quotes to stay focused on incomplete groups.

## 4. Choose the Business Policy Before Configuring

### 4.1. Three Ways to End Waiting

| Policy | When appropriate | Output contract |
| --- | --- | --- |
| Return received partial set | Comparison page can display fewer options | Explicitly list missing sources and partial status |
| Fail the whole run | Missing results lead to wrong decisions | Emit failure result or follow-up error event |
| Retry missing branch | Transient failure, time budget remains | Bounded retry count and explicit attempt key |

For the quote example, we choose **returning received parts after timeout**. Another subsystem can use the missing list for error metrics or retry decisions. Aggregation itself does not emit retry commands.

If data feeds financial settlement, returning partial data may violate the contract. In that case, the timeout branch must produce a traceable failure outcome rather than publishing figures as if complete.

### 4.2. Four Properties That Do Not Replace One Another

| Property | Role |
| --- | --- |
| `groupTimeout` | Schedules when to run timeout handling for the group |
| `sendPartialResultOnExpiry` | Chooses whether to aggregate available parts on expiry |
| `expireGroupsUponCompletion` | Chooses whether to delete the whole group after normal release |
| `expireGroupsUponTimeout` | Chooses whether to delete the whole group during timeout handling |

On the timeout path when release is still unmet, `sendPartialResultOnExpiry(true)` aggregates what has arrived; `false` sends those parts to the discard path. Enabling this flag alone does not create a timer. [Expiry handling source](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/aggregator/AbstractCorrelatingMessageHandler.java)

`expireGroupsUponCompletion(false)` retains closed-group metadata after normal release. Group messages are cleared from the processed group. [AggregatingMessageHandler API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/aggregator/AggregatingMessageHandler.html), [afterRelease source](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/aggregator/AggregatingMessageHandler.java)

Similarly, choose `expireGroupsUponTimeout(false)` to keep closed-group markers after timeout. If metadata is wiped completely, a message with the same key can open a new group. The timeout flag defaults to `true`, so configure it explicitly when you want to block that behavior. [AbstractCorrelatingMessageHandler API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/aggregator/AbstractCorrelatingMessageHandler.html)

## 5. Java DSL Example: Complete Quotes and Partial Quotes

### 5.1. Contract of the Example

The example uses Java 17 and APIs available in Spring Integration 6.5.0. It requires `org.springframework.integration:spring-integration-core` and compatible Spring dependencies; in a Spring Boot project, use Boot's version management.

Assumptions:

- Every inquiry asks exactly three sources: A, B, C.
- The `requestKey` header identifies one inquiry run, scoped by tenant and attempt.
- Replies entering the flow carry a `QuoteReply` payload.
- If one source sends multiple prices during one inquiry, the example picks the lowest price. This is an illustrative rule; systems with price updates need an explicit versioning contract.
- The two-second timeout is chosen for observing the example, not as an operational recommendation.

Flow diagram:

~~~mermaid
flowchart TD
    I["quoteReplies: Message with requestKey"] --> A["Aggregator and MessageGroupStore"]
    A -->|Has A, B, C| O["Build QuoteBatch"]
    A -->|Timeout: only A, B| O
    O --> R{"QuoteBatch.complete?"}
    R -->|true| C["completeQuotes"]
    R -->|false| P["partialQuotes"]
    A -->|Same key already closed| D["discardedReplies"]
~~~

`outputProcessor` lets you build a custom output payload instead of the default payload collection. Here, the same processor handles both full release and partial release. [AggregatorSpec API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/AggregatorSpec.html)

### 5.2. Configuration and Demo Program

~~~java
import java.math.BigDecimal;
import java.time.Duration;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Collectors;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.store.MessageGroup;
import org.springframework.integration.store.MessageGroupStore;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
@EnableIntegration
public class IncompleteGroupDemo {

    private static final Set<String> EXPECTED = Set.of("A", "B", "C");
    private static final String REQUEST_KEY = "requestKey";

    public record QuoteReply(String supplier, BigDecimal price) {
        public QuoteReply {
            if (!EXPECTED.contains(supplier)) {
                throw new IllegalArgumentException("Unknown supplier: " + supplier);
            }
            if (price == null || price.signum() < 0) {
                throw new IllegalArgumentException("Price must be non-negative");
            }
        }
    }

    public record QuoteBatch(
            String requestKey,
            boolean complete,
            Set<String> missingSuppliers,
            Map<String, BigDecimal> quotes) {
    }

    @Bean
    public DirectChannel quoteReplies() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel completeQuotes() {
        return new QueueChannel();
    }

    @Bean
    public QueueChannel partialQuotes() {
        return new QueueChannel();
    }

    @Bean
    public QueueChannel discardedReplies() {
        return new QueueChannel();
    }

    @Bean
    public MessageGroupStore quoteGroupStore() {
        return new SimpleMessageStore();
    }

    @Bean
    public IntegrationFlow quoteFlow(MessageGroupStore quoteGroupStore) {
        return IntegrationFlow.from(quoteReplies())
                .aggregate(spec -> spec
                        .messageStore(quoteGroupStore)
                        .correlationStrategy(message -> {
                            String key = message.getHeaders()
                                    .get(REQUEST_KEY, String.class);
                            if (key == null || key.isBlank()) {
                                throw new IllegalArgumentException(
                                        "Missing requestKey");
                            }
                            return key;
                        })
                        .releaseStrategy(group ->
                                receivedSuppliers(group).containsAll(EXPECTED))
                        .groupTimeout(2_000L)
                        .sendPartialResultOnExpiry(true)
                        .expireGroupsUponCompletion(false)
                        .expireGroupsUponTimeout(false)
                        .minimumTimeoutForEmptyGroups(60_000L)
                        .expireTimeout(30_000L)
                        .expireDuration(Duration.ofSeconds(5))
                        .discardChannel(discardedReplies())
                        .outputProcessor(IncompleteGroupDemo::toBatch))
                .<QuoteBatch, Boolean>route(
                        QuoteBatch::complete,
                        mapping -> mapping
                                .channelMapping(true, "completeQuotes")
                                .channelMapping(false, "partialQuotes"))
                .get();
    }

    private static Set<String> receivedSuppliers(MessageGroup group) {
        return group.getMessages().stream()
                .map(message -> (QuoteReply) message.getPayload())
                .map(QuoteReply::supplier)
                .collect(Collectors.toSet());
    }

    private static QuoteBatch toBatch(MessageGroup group) {
        Map<String, BigDecimal> quotes = new TreeMap<>();
        for (Message<?> message : group.getMessages()) {
            QuoteReply reply = (QuoteReply) message.getPayload();
            quotes.merge(reply.supplier(), reply.price(), BigDecimal::min);
        }

        Set<String> missing = new TreeSet<>(EXPECTED);
        missing.removeAll(quotes.keySet());

        String requestKey = group.getOne().getHeaders()
                .get(REQUEST_KEY, String.class);

        return new QuoteBatch(
                requestKey,
                missing.isEmpty(),
                Set.copyOf(missing),
                Map.copyOf(quotes));
    }

    private static Message<QuoteReply> reply(
            String requestKey, String supplier, String price) {
        return MessageBuilder
                .withPayload(new QuoteReply(supplier, new BigDecimal(price)))
                .setHeader(REQUEST_KEY, requestKey)
                .build();
    }

    private static void show(String label, Message<?> message) {
        if (message == null) {
            throw new IllegalStateException("No message for: " + label);
        }
        System.out.println(label + ": " + message.getPayload());
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             IncompleteGroupDemo.class)) {

            DirectChannel input =
                    context.getBean("quoteReplies", DirectChannel.class);
            QueueChannel full =
                    context.getBean("completeQuotes", QueueChannel.class);
            QueueChannel partial =
                    context.getBean("partialQuotes", QueueChannel.class);
            QueueChannel discarded =
                    context.getBean("discardedReplies", QueueChannel.class);

            String fullKey = "tenant-01:req-001:attempt-1";
            input.send(reply(fullKey, "A", "30000"));
            input.send(reply(fullKey, "B", "28000"));
            input.send(reply(fullKey, "C", "32000"));
            show("Full", full.receive(1_000));

            String partialKey = "tenant-01:req-002:attempt-1";
            input.send(reply(partialKey, "A", "30000"));
            input.send(reply(partialKey, "B", "28000"));
            show("Partial", partial.receive(5_000));

            input.send(reply(partialKey, "C", "32000"));
            show("Late", discarded.receive(1_000));
        }
    }
}
~~~

The `QueueChannel`s here are observation points using `receive`. In real applications, attach consumers for each output path and capacity bounds matching your load.

### 5.3. Interpreting the Results

Expected observations:

| Label | Notable payload fields | Reason |
| --- | --- | --- |
| `Full` | `complete=true`, no missing sources | A, B, C all replied |
| `Partial` | `complete=false`, `missingSuppliers={C}` | Timed out with only A, B |
| `Late` | C's `QuoteReply` | Group with same key already closed and metadata was retained |

The iteration order of elements in immutable collections is not part of the example's contract.

The processor does not need to guess "am I being called because of timeout or because everything arrived?" It computes `complete` from the sources present. Because normal release requires all of A, B, C, an incomplete result in the example signifies the path where waiting ended with missing data.

If you change the strategy to a quorum of two out of three sources, a result without all three can emit via normal release. In that case, add a dedicated field such as `completionPolicy`; do not infer the cause of emission solely from the `complete` flag.

`expireTimeout` and `expireDuration` configure stale-group scanning, supporting state cleanup beyond live timeout schedules. `groupTimeout`, `minimumTimeoutForEmptyGroups`, and these options are part of the DSL API used in the example. [CorrelationHandlerSpec API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html)

## 6. Distinguishing Types of Wait Times

### 6.1. Idle Period After the Latest Message

With `groupTimeout(2_000L)`, the timeout schedule resets when a new message arrives while the group has not yet released. Hence, this is an activity-based wait period per group, not a guarantee that the whole request finishes in two seconds. [Group Timeout documentation](https://docs.spring.io/spring-integration/reference/aggregator.html#_aggregator_and_group_timeout)

~~~text
t = 0.0 s   A arrives
t = 1.5 s   B arrives
t ≈ 3.5 s   timeout triggers if C still has not arrived
~~~

Design consequence: a source sending repeated replies continuously can prolong waiting. Deduplicating before the aggregator mitigates this; an absolute deadline is still necessary if the contract mandates a hard cutoff.

### 6.2. Deadline Tied to Group Creation Time

Replace `groupTimeout(2_000L)` with:

~~~java
.groupTimeout(group ->
        new java.util.Date(group.getTimestamp() + 2_000L))
~~~

The timeout function can return a `Date` to indicate an absolute point in time. Do not configure both forms simultaneously on the same endpoint. [groupTimeout API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html#groupTimeout(java.util.function.Function))

The starting point here is **group** creation time, which may be later than when the user sent the request. If a request is created at 10:00:00 yet the first reply only arrives at 10:00:04, a group-based limit does not automatically cover those earlier four seconds.

If the contract is "reply within five seconds of receiving the request," record `deadlineAt` right at the start of the workflow, propagate it consistently across branches, and use that timestamp for the termination policy.

### 6.3. When No Replies Arrive at All

If A, B, and C all stay silent, a flow that only receives replies has no message yet to create a group. You cannot rely on a schedule of a non-existent group to emit an empty result.

A complete design tracks the request from the start:

1. Record the pending request with its expected source set and deadline.
2. Dispatch the branches.
3. Update results as replies arrive.
4. At deadline, terminate the request even if zero replies arrived.
5. Ensure the completion path and deadline path publish at most one final result.

You can use a dedicated deadline coordinator and a request state store. If using an initiation message to create the group, distinguish it from provider replies; never let it inflate the business reply count.

### 6.4. Gateway Timeout Is a Different Limit

A gateway's reply timeout serves the caller; an aggregator's timeout serves the group. If the caller has already stopped waiting before the group emits its result, a partial result does not magically reach the original caller.

When integrating a gateway, align deadlines, result-receiving channels, and status lookup. Synchronous flows need enough budget for aggregation and downstream work. Asynchronous flows can return a request ID and later allow querying or pushing result events.

## 7. Closed Groups, Late Messages, and State Cleanup

### 7.1. Why Keep a Trace?

After inquiry `req-002:attempt-1` has already returned a result missing C, a later reply from C must not silently alter the published result.

In the example, both group-expiration flags are `false`. Retained metadata acts as a trace that this key has ended. The `discardedReplies` path preserves evidence rather than silently dropping late replies.

If metadata has been cleaned up or lost on restart with an in-memory store, the same key can be accepted as a brand-new group. The late-message policy therefore has a bounded validity window, not a perpetual guarantee.

Business options for late replies include:

- Record and ignore.
- Emit an adjustment event with a new version.
- Store for supplier quality analytics.
- Route to a dedicated reconciliation workflow.

Never feed a reply from an old attempt into a new attempt merely because they share an order ID.

### 7.2. Retaining Metadata Also Consumes Resources

Keeping every closed key forever causes group counts to grow with total requests ever processed. Define how long late messages remain recognizable, then clean up metadata.

In the example, `minimumTimeoutForEmptyGroups(60_000L)` sets a minimum retention floor for empty groups under the corresponding cleanup mechanism. Periodic scan intervals can make actual cleanup happen later than that minimum mark. This is not real-time precision. [Empty group retention API](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/AbstractCorrelatingMessageHandler.html#setMinimumTimeoutForEmptyGroups(long))

Simple design estimate:

~~~text
Retained markers ≈ completed requests per second × retention duration
~~~

At 500 requests per second with 10-minute retention, markers alone account for roughly 300,000 groups. Also factor in key size, metadata, indexes, and store overhead.

### 7.3. Reaper vs. Per-Group Timeout Schedules

`MessageGroupStoreReaper` provides a `run()` method to scan overdue groups in a store. Defining a reaper bean is not enough for it to scan periodically; you need a mechanism invoking `run()` on a schedule. [MessageGroupStoreReaper API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/store/MessageGroupStoreReaper.html)

If replacing the example's purge settings with a reaper, explicitly design:

- Which store falls under the reaper's ownership.
- Overdue threshold for waiting groups.
- Metadata retention window for closed groups.
- Scan interval and acceptable delay.

Avoid attaching multiple cleanup mechanisms with conflicting thresholds. For instance, a scan that expires groups after one second makes a two-second wait policy stop behaving as readers of the configuration expect.

## 8. Restarts, Concurrency, and Reliability

### 8.1. Durable Storage Does Not Mean Full Workflow Recovery

`SimpleMessageStore` stores data in memory. Spring Integration provides store options backed by JDBC, Redis, and MongoDB for different persistence needs. Choosing a store is part of data durability design. [Message Store documentation](https://docs.spring.io/spring-integration/reference/message-store.html)

When moving to persistent storage, also answer:

- Which payloads and headers are persisted, and in what format are they restored?
- Who resumes pending groups after a restart?
- How are timeout schedules re-established or replaced by scanning?
- What happens if the application stops mid-way between sending output and persisting completion state?
- How do consumers prevent reprocessing the exact same result?

A persistent store does not automatically turn "read group, emit result, update store, and call external service" into an atomic transaction.

### 8.2. Two Kinds of Keys to Distinguish

A **correlation key** identifies messages belonging to the same processing run. A **synchronization lock** protects concurrent mutations to state.

With multiple instances operating on one store, the design must ensure checking and closing the same group never produce multiple final results. Evaluate locking mechanisms, transactions, and store-sharing rules fitting your deployment.

Even when synchronization protects state well, consumers should still enforce an idempotency contract on results, such as `requestKey + resultVersion`. This covers replays during recovery or retries after network errors.

### 8.3. Do Not Mix Unrelated State Spaces

Each aggregator should have a clear store and key scope. The documentation warns against sharing one `MessageGroupStore` across multiple endpoints that perform expiry because callbacks can affect the wrong groups. When sharing physical infrastructure, partition storage spaces as supported by the implementation. [Aggregator state management documentation](https://docs.spring.io/spring-integration/reference/aggregator.html)

In the quote design, keys must also distinguish tenant, request, and attempt. For example:

~~~text
tenant-01 / req-002 / attempt-1
tenant-01 / req-002 / attempt-2
tenant-02 / req-002 / attempt-1
~~~

If key components are arbitrary strings, use unambiguous encoding or structured keys; do not simply concatenate strings with a delimiter that could appear inside the data.

### 8.4. Timeouts Are Not Flow Exceptions

A group missing data at deadline can be an expected business outcome. In the example, it travels through `partialQuotes`. `errorChannel` is for processing errors; `discardedReplies` is for messages dropped by policy.

Errors on synchronous segments can return to the sender's thread. Errors occurring on a scheduler or executor need a corresponding error path; do not assume the waiting caller can still catch those exceptions. [Error Handling documentation](https://docs.spring.io/spring-integration/reference/error-handling.html)

When the processor or a consumer of timeout results fails, log the full request key, preserve evidence, and decide whether to retry. Do not report success merely because the scheduler fired.

## 9. Behavior-Based Testing

The `main` example demonstrates three basic paths. In production implementations, test at the level of data contracts and flow behavior.

| Scenario | Expectation |
| --- | --- |
| Receive A, B, C within wait time | One complete `QuoteBatch` |
| Receive only A, B | One result missing C after timeout |
| Receive only A | Result missing B and C |
| Receive A, A, B | Does not release normally; C is still missing |
| Receive C after partial result emitted | Goes to discard while metadata is retained |
| Receive old reply after metadata cleanup | Verify re-acceptance and idempotency policies |
| Two interleaved `requestKey`s | Sources never mix across requests |
| Reply missing `requestKey` | Rejected with an explicit error |
| Zero replies arrive | Request coordinator handles the deadline |
| Two threads deliver final part and timeout concurrently | Does not produce two final successful results |
| Restart while group is waiting | Recovers per chosen store and policy |
| Result-receiving path fails | Error evidence recorded and recovery policy executed |

Simply asserting that a collection has two elements is insufficient for the partial path. Assert at least the request key, `complete=false`, exact `missingSuppliers`, and exact received sources.

To test timeouts:

- Use short test wait durations with enough headroom for the CI scheduler.
- Wait for results using bounded waits; avoid fixed `Thread.sleep` guesses.
- Also verify no complete result is emitted after a partial result was already finalized.
- For race conditions, repeat controlled scenarios and verify the number of published results.
- For restarts, use a store matching production; an in-memory store does not prove state recovery.

## 10. Diagnosing a Stuck Group

When someone reports "the aggregator never returns a result," investigate in order:

1. **Identify one concrete inquiry.** Capture tenant, `requestKey`, attempt, and deadline.
2. **Check expected set.** Which branches were actually dispatched? Did a router skip a branch?
3. **Trace each reply.** Which branch never returned, was dropped by a filter, or lost its correlation key?
4. **Inspect the release condition.** Is it checking count, unique sources, or branch statuses?
5. **Inspect timing schedules.** Using idle wait or fixed deadline? Are duplicate messages resetting the timer?
6. **Check outcomes and post-close state.** Is the group still waiting, partially emitted, discarded, or deleted?
7. **Check the result sink.** Is there a consumer, a processing error, or a caller that already timed out?

Useful indicators include pending group count, oldest group age, partial-result ratio, most frequently absent source, late message volume, and retained metadata count.

Do not put high-cardinality `requestKey` values into metric labels. Keep those keys in logs or traces; metrics should use bounded dimensions such as supplier, result type, and environment.

## 11. Practice Exercises

Extend the example in three steps:

1. Replace the fixed A, B, C set with a source set selected per request. Ensure all replies in the same group share the same expected contract.
2. Add `BranchOutcome` so a `NO_OFFER` reply still counts as a completed branch. Distinguish branches that responded from usable quotes.
3. Design a retry branch for missing sources with a time budget and a new attempt key. Specify clearly where replies from the previous attempt go.

Your solution succeeds when it explains outcomes for: A replying twice, B reporting no offer, C arriving after deadline; and when zero sources reply. Each case must specify emitted data, when waiting ends, retained state, and how subsequent messages are handled.
