# Scatter-Gather Sends One Request to Multiple Branches

## 1. The problem: one request needs multiple results before making a decision

An ordering system receives a `ConfirmOrder(orderId, customerId, quantity)` request. Before replying that **the order is confirmed**, the system must verify at least two independent conditions:

1. **Inventory**: can the warehouse reserve a sufficient quantity of items?
2. **Fraud**: does the request pass the risk check?

If it only calls Inventory and immediately confirms, the request might still lack Fraud approval. If it merely emits an event to both parties without collecting results, the system knows that it **sent the request**, but does not yet know whether **confirmation conditions are met**.

**Scatter–Gather** is an Enterprise Integration Pattern that solves the problem of **distributing one request to multiple processing branches (scatter)** and **collecting related results to produce a combined answer (gather)**. In Spring Integration, this pattern can combine Recipient List/Publish–Subscribe with an Aggregator and Gateway, while also providing dedicated Scatter–Gather support.

~~~mermaid
flowchart LR
    C[Caller] --> G[Gateway]
    G --> S{Scatter}
    S --> I[Inventory check]
    S --> F[Fraud check]
    I --> RI["InventoryReply"]
    F --> RF["FraudReply"]
    RI --> A[Gather / Aggregator]
    RF --> A
    A --> P{Decision policy}
    P -->|Both PASS| OK["CONFIRMED"]
    P -->|Any FAIL| NO["REJECTED"]
    P -->|Missing reply| TO["PENDING / TIMED_OUT"]
    OK --> C
    NO --> C
    TO --> C
~~~

The key to the pattern is: **branches replying to the same request must be grouped together accurately**, and the system must have clear rules for **when results are sufficient**, **what to do when results are missing**, and **how to handle duplicate/late replies**.

This lesson belongs to the **Scatter gather** chapter of the `SPRING_INTEGRATION_PATTERN` module. The module teaches how to implement Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows; combining Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation, and per-branch testing/observability.

### Learning objectives

After completing this lesson, you can:

1. Clearly explain the two phases of scatter and gather, distinguishing **dispatching a request** from **receiving all required replies**.
2. Distinguish Scatter–Gather from Recipient List, Publish–Subscribe, Splitter, and Content-Based Router.
3. Design request/reply payloads, `requestId`, `recipientId`, and the expected recipient set.
4. Configure a Java DSL flow with a Gateway, two branches, and result aggregation logic.
5. Explain correlation, sequence headers, release strategy, timeout, and message group.
6. Test success, rejected, missing, duplicate, foreign, and late replies.
7. Design retry, error channel, idempotency, backpressure, and observability along the right processing milestones.

## 2. The two phases of Scatter–Gather

### 2.1. Scatter: distributing one request to branches that must return a result

**Scatter** is the step of taking a logical request, deciding the set of branches that will process it, and sending a message to each of those branches. For example:

~~~text
CheckOrder(requestId=REQ-1001, orderId=ORD-1001)
     |
     +--> InventoryCheck(REQ-1001, ORD-1001)
     |
     +--> FraudCheck(REQ-1001, ORD-1001)
~~~

An important point: scatter is **one-to-many in terms of processing destinations**. Do not assume by default that sending is executed concurrently across multiple threads. With a `DirectChannel`, handlers may run synchronously on the publisher's call stack. When using an `ExecutorChannel`, a broker, or separate consumers, branches may process asynchronously. **Fan-out does not automatically imply parallel execution or durable delivery.**

### 2.2. Gather: combining replies belonging to the same request

Each branch must produce a **reply carrying enough identity information to know which request it belongs to and who sent it**:

~~~text
InventoryReply(
  requestId=REQ-1001,
  recipientId=inventory,
  outcome=PASS)

FraudReply(
  requestId=REQ-1001,
  recipientId=fraud,
  outcome=PASS)
~~~

The gatherer receives both and can produce:

~~~text
CombinedDecision(
  requestId=REQ-1001,
  confirmed=true,
  inventory=PASS,
  fraud=PASS)
~~~

If Fraud returns `FAIL`, the combined result must accurately reflect the policy. If Fraud has no reply, **never automatically treat "no response" as "PASS"**.

### 2.3. "One request" is different from "one single message"

At the business level, there is only one `REQ-1001`. At the messaging level:

- The Gateway creates a request message.
- The Scatterer creates/sends corresponding messages to the recipients.
- Each handler may create a new reply message.
- The Aggregator stores and emits a result message.
- Adapters may recreate messages/system IDs across boundaries.

Therefore, **`MessageHeaders.ID` is not a durable business key for the entire journey**. You should use `requestId` in the payload/metadata and apply appropriate correlation; if a broker is involved, explicit header mapping is required.

## 3. How does it differ from related patterns?

| Pattern | Question it answers | Automatically gathers replies? |
|---|---|---|
| **Publish–Subscribe** | "Which subscribers need to be notified of an event?" | Not by default. |
| **Recipient List Router** | "Which channels should a message be sent to?" | Not by default. |
| **Content-Based Router** | "Based on the payload, which branch does the message go to?" | Not by default. |
| **Splitter** | "What parts is a large payload split into?" | No; needs an Aggregator if you want to gather. |
| **Aggregator** | "When and how are messages in the same group combined?" | Yes at the gathering level, but does not scatter on its own. |
| **Scatter–Gather** | "How do we send a request to multiple branches and wait for/aggregate results?" | That is the configured gather part. |
| **Routing Slip** | "Which sequence of steps must a message pass through?" | Not by default; primarily a sequential route. |

### 3.1. Do not use Scatter–Gather for every fan-out

When `OrderCreated` is sent to Audit, Email, and Analytics and the caller **does not need to wait for all three**, a Publish–Subscribe Channel or Recipient List with per-branch recovery may be simpler. Conversely, if **Inventory and Fraud are conditions to confirm an order**, the results of both must participate in the decision; that is a clear Scatter–Gather need.

### 3.2. Do not confuse Scatter with Splitter

~~~text
Scatter–Gather:
  One order check request
    -> Inventory check for the same order
    -> Fraud check for the same order
    -> gather two different types of results

Splitter–Aggregator:
  Batch of 100 order lines
    -> 100 WorkItem messages
    -> process each item
    -> aggregate 100 results
~~~

Both patterns involve fan-out/fan-in, but **Scatter–Gather usually sends the same business request to multiple specialists/branches**, whereas Splitter splits data into parts. In a real flow, they can be combined.

### 3.3. Parallelism is an independent decision

Processing branches can be:

- **Synchronous:** easy to debug, but one slow branch can block the entire sending path.
- **Asynchronous within the JVM:** reduces caller thread binding, but introduces executor saturation, queues, and separate error handling.
- **Distributed over broker/HTTP:** better process isolation, but requires reply correlation, timeout, retry, idempotency, durability/ack, and late response handling.

Choose the execution mechanism based on latency/SLO and fault isolation level, not simply based on the name "Scatter–Gather".

## 4. Designing the request/reply contract before writing DSL

### 4.1. Minimum fields

| Entity | Key fields | Why needed? |
|---|---|---|
| `CheckOrderRequest` | `requestId`, `orderId`, `quantity`, `amountVnd` | Identifies the request and data for each branch. |
| `BranchReply` | `requestId`, `recipientId`, `outcome`, `reasonCode` | Correlates to the right group and identifies which branch replied. |
| `CombinedDecision` | `requestId`, `status`, `resultsByRecipient` | Final answer with full supporting evidence. |
| `ExpectedRecipients` | `{inventory, fraud}` | Knows the set of branches that **must** reply, not just total message count. |
| `deadline` | Milestone to conclude/transition state. | Prevents the group and Gateway from waiting indefinitely. |
| `attemptId` (if retrying) | Attempt ID per recipient. | Distinguishes duplicates from intentional retries. |

In this example, `requestId` is the key for **a single check request**. If an order is re-checked after data modification, a new request or new version/attempt should be created per the contract; do not let stale replies from a previous check mix into the new group.

### 4.2. The expected recipient set must be exact

In this lesson we choose a fixed set:

~~~text
expectedRecipients = {inventory, fraud}
~~~

If another workflow only needs Inventory, do not keep `expectedCount=2` and wait for Fraud forever. If an actual request selects `{inventory, fraud, compliance}`, you must lock in **the set of three recipients actually scattered to** and inform the gatherer of that set.

Relying only on `expectedCount=2` can be fooled:

~~~text
Received: inventory PASS
Received: inventory PASS  (duplicate)
Not yet received: fraud

messageCount = 2
uniqueRecipientCount = 1
complete = false
~~~

**When results can arrive in duplicate or from unexpected branches, a release condition based on the unique recipient set is safer than one based solely on count.**

### 4.3. Illustrative business rules

| Inventory | Fraud | Conclusion |
|---|---|---|
| PASS | PASS | `CONFIRMED` |
| FAIL | PASS | `REJECTED` |
| PASS | FAIL | `REJECTED` |
| FAIL | FAIL | `REJECTED` |
| PASS | No response yet | `PENDING` or `TIMED_OUT` per deadline |
| No response yet | PASS | `PENDING` or `TIMED_OUT` |
| Duplicate Inventory PASS, no Fraud yet | Insufficient results | Not `CONFIRMED` |

Some businesses may **fail-fast** when one branch returns FAIL, but must understand that remaining branches may still be processing. Late results and their side effects must be handled; do not assume fail-fast automatically cancels everything.

## 5. Correlation, sequence, and release strategy

### 5.1. Correlation ID to group accurately

Spring Integration has sequence/correlation headers supporting routing, splitting, and aggregation in corresponding configurations, typically including:

- `correlationId`: identifies a message group.
- `sequenceNumber`: position of a part within a sequence.
- `sequenceSize`: size of the sequence when defined.

The Scatterer/Gatherer must create or propagate appropriate grouping information. **Do not assume the `correlationId` header always equals the payload `requestId`** or is automatically preserved across every type of adapter. If relying on framework correlation, inspect the specific Scatter–Gather configuration and header mapping across boundaries.

### 5.2. A requestId is different from a traceId

| ID | Purpose |
|---|---|
| `requestId` | Groups results of **one check invocation**. |
| `orderId` | Business entity that may be checked multiple times. |
| `traceId` | Links observability steps across services/threads. |
| `correlationId` | Group key used by the Aggregator per configuration. |
| `recipientId` | Distinguishes InventoryReply from FraudReply. |
| `MessageHeaders.ID` | ID of a specific message; not durable across all conversions/replays. |

For example, the same `traceId` may contain multiple attempts for the same order; using traceId as a group ID without adding request/attempt ID can cause misgrouping.

### 5.3. Release strategy decides when gather is complete

An Aggregator has two related but distinct responsibilities:

1. **Correlation strategy:** which messages belong to the same group?
2. **Release strategy:** when is the group allowed to emit a result?

If release only checks `group.size() == 2`, it **does not prove on its own** that both recipients are present when duplicates may exist, or that there is no foreign reply. A more robust business strategy must inspect `recipientId`, `requestId`, and accepted result types; controlling duplicates and foreign replies before deciding.

### 5.4. A message group is not a transactional database

The Aggregator can use a `MessageGroupStore` to hold pending replies and manage expiration. Depending on configuration, the group store can be in-memory or persistent. **Do not infer from the name Aggregator that groups automatically survive a JVM crash, automatically replay replies, or guarantee exactly-once.**

To recover after a crash, you need to consider:

- Is the store durable and what is the transaction boundary?
- How are released/expired groups cleaned up and tombstoned?
- Will a late reply be treated as a new group?
- Does the broker ack happen before or after the reply is saved to the group?
- Does retrying a branch create duplicate outcomes/side effects?

## 6. Domain model for a request traversing multiple branches

### 6.1. Using DTOs with clear identity and outcome

The examples target **Java 17+, Spring Boot 3.x, Spring Integration 6.x** with `spring-boot-starter-integration`. Types in the code blocks below are assumed to belong to the same package; when placing them into a project, split `public` types into separate Java files per language rules.

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

record CheckOrderRequest(
        String requestId,
        String orderId,
        int quantity,
        BigDecimal amountVnd) {

    CheckOrderRequest {
        if (requestId == null || requestId.isBlank()
                || orderId == null || orderId.isBlank()
                || quantity <= 0 || amountVnd == null
                || amountVnd.signum() <= 0) {
            throw new IllegalArgumentException("INVALID_CHECK_REQUEST");
        }
    }
}

enum BranchVerdict {
    PASS, FAIL
}

record BranchReply(
        String requestId,
        String recipientId,
        BranchVerdict verdict,
        String reasonCode) {

    BranchReply {
        if (requestId == null || requestId.isBlank()
                || recipientId == null || recipientId.isBlank()) {
            throw new IllegalArgumentException("INVALID_REPLY_ID");
        }
        Objects.requireNonNull(verdict, "verdict");
    }
}

enum DecisionStatus {
    CONFIRMED, REJECTED
}

record CombinedDecision(
        String requestId,
        DecisionStatus status,
        Map<String, BranchReply> repliesByRecipient) {

    CombinedDecision {
        Objects.requireNonNull(requestId, "requestId");
        Objects.requireNonNull(status, "status");
        repliesByRecipient = Map.copyOf(repliesByRecipient);
    }
}
~~~

Here `CombinedDecision` only exists when **complete and valid results are present**. `PENDING`/`TIMED_OUT` states are represented by another response type or error/recovery workflow in later sections. Do not create `CONFIRMED` and leave `repliesByRecipient` missing a branch.

### 6.2. Why must `recipientId` be included in the reply?

Two branches might return the same `PASS` or `FAIL` data structure. If you only receive:

~~~text
PASS
PASS
~~~

the gatherer does not know whether these are two different branches, or the same Inventory sending twice. Therefore the reply needs:

~~~text
{requestId: "REQ-1", recipientId: "inventory", verdict: "PASS"}
{requestId: "REQ-1", recipientId: "fraud", verdict: "PASS"}
~~~

**Do not trust an arbitrary recipientId supplied by an external client.** In an internal flow, the branch handler knows its own identity and creates the reply based on server-side logic. For replies over broker/HTTP, you must authenticate the source, authorize it, and validate payload/schema.

### 6.3. Separating branch processing from the overall decision

A branch should only know its own responsibility:

~~~java
final class InventoryCheck {
    BranchReply check(CheckOrderRequest request) {
        boolean enoughStock = request.quantity() <= 10;
        return new BranchReply(
                request.requestId(),
                "inventory",
                enoughStock ? BranchVerdict.PASS : BranchVerdict.FAIL,
                enoughStock ? "STOCK_OK" : "INSUFFICIENT_STOCK");
    }
}

final class FraudCheck {
    private static final BigDecimal REVIEW_LIMIT =
            new BigDecimal("10000000");

    BranchReply check(CheckOrderRequest request) {
        boolean acceptable =
                request.amountVnd().compareTo(REVIEW_LIMIT) <= 0;
        return new BranchReply(
                request.requestId(),
                "fraud",
                acceptable ? BranchVerdict.PASS : BranchVerdict.FAIL,
                acceptable ? "RISK_OK" : "RISK_REVIEW_REQUIRED");
    }
}
~~~

These two rules are **for illustration only**: Inventory does not query a real warehouse; Fraud is not a production anti-fraud engine. They return deterministic replies to make testing the pattern easy without calling external APIs.

### 6.4. Do not let a branch decide the outcome of the whole order

If Inventory returns PASS, it only confirms **the inventory condition per the Inventory contract**. It should not return `CONFIRMED` for the entire order, because Fraud might FAIL. The overall decision belongs to the **post-gather decision policy**, once the exact set of replies is known.

## 7. Decision combiner: reconciling replies before concluding

### 7.1. Result combining rules

Assume each request requires **exactly one final result** from Inventory and Fraud. We need:

- Both `recipientId` values belong to the allowlist.
- The same expected `requestId`.
- No duplicate recipients.
- No missing recipients.
- Each reply has a valid `verdict`.
- `CONFIRMED` only when both PASS.
- Conversely, when both replies are present and any is FAIL, return `REJECTED`.

~~~java
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

final class ReplyCombiner {
    static final Set<String> REQUIRED =
            Set.of("inventory", "fraud");

    CombinedDecision combine(
            String requestId, Collection<BranchReply> replies) {

        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException("INVALID_REQUEST_ID");
        }
        Objects.requireNonNull(replies, "replies");

        Map<String, BranchReply> byRecipient =
                new LinkedHashMap<>();

        for (BranchReply reply : replies) {
            Objects.requireNonNull(reply, "reply");
            if (!requestId.equals(reply.requestId())) {
                throw new IllegalArgumentException(
                        "FOREIGN_REQUEST_REPLY");
            }
            if (!REQUIRED.contains(reply.recipientId())) {
                throw new IllegalArgumentException(
                        "UNEXPECTED_RECIPIENT");
            }
            if (byRecipient.putIfAbsent(
                    reply.recipientId(), reply) != null) {
                throw new IllegalArgumentException(
                        "DUPLICATE_RECIPIENT_REPLY");
            }
        }

        if (!byRecipient.keySet().equals(REQUIRED)) {
            throw new IllegalStateException(
                    "INCOMPLETE_RECIPIENT_RESULTS");
        }

        boolean allPassed = byRecipient.values().stream()
                .allMatch(reply ->
                        reply.verdict() == BranchVerdict.PASS);

        return new CombinedDecision(
                requestId,
                allPassed
                        ? DecisionStatus.CONFIRMED
                        : DecisionStatus.REJECTED,
                byRecipient);
    }
}
~~~

### 7.2. Why not simply use `allMatch(PASS)`?

~~~java
// Anti-pattern: only inspects replies that have arrived.
boolean confirmed = replies.stream()
        .allMatch(r -> r.verdict() == BranchVerdict.PASS);
~~~

With a collection containing only Inventory PASS, the result above is `true`, even though Fraud has not replied. With an **empty** collection, `allMatch` also returns `true` per stream logic rules. Therefore, **completeness must be checked first**.

Similarly:

~~~java
boolean complete = replies.size() == 2;
~~~

is still wrong when the collection has two Inventory replies and no Fraud reply.

### 7.3. Duplicates are data or transport errors that must be handled

In the example, `ReplyCombiner` **rejects duplicates**, making it easy for tests to catch bugs. Production may **intentionally deduplicate** if using an at-least-once broker, but needs:

1. A result key consisting of `requestId + recipientId` plus an `attemptId` if the retry policy allows multiple attempts.
2. A rule to choose the authoritative result: final-only, latest version, CAS first-commit, or state machine.
3. Audit and metrics for duplicates; do not silently count them as a new recipient.
4. Verification of whether two duplicate replies have **conflicting** verdicts.
5. Idempotency on side effects before creating the reply.

Do not blindly pick the "last arriving" reply as right without knowing attempt ordering, commit state, and transport delay.

### 7.4. Fail-fast can be a different policy

If Inventory FAILS, some systems want to return REJECTED immediately without waiting for Fraud. This **differs from the wait-for-all rule in the example code**. With fail-fast:

- You still need to know which branches were dispatched and may still be in-flight.
- Do not assume cancelling a Future or Gateway timeout will roll back work in other branches.
- You need to store/handle late replies, group state, and side effects.
- The response contract must state clearly whether the early result is considered **final**.

This lesson prioritizes **wait-for-all** to clearly demonstrate Scatter–Gather; fail-fast is treated as an extension with different risks.

## 8. Unit testing the combiner before framework integration

### 8.1. Case where both PASS

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReplyCombinerSuccessTest {
    private final ReplyCombiner combiner = new ReplyCombiner();

    private static BranchReply reply(
            String branch, BranchVerdict verdict) {
        return new BranchReply(
                "REQ-1", branch, verdict, "TEST");
    }

    @Test
    void bothRecipientsPassReturnsConfirmed() {
        CombinedDecision result = combiner.combine(
                "REQ-1",
                List.of(
                        reply("inventory", BranchVerdict.PASS),
                        reply("fraud", BranchVerdict.PASS)));

        assertEquals(DecisionStatus.CONFIRMED, result.status());
        assertEquals(2, result.repliesByRecipient().size());
        assertEquals("REQ-1", result.requestId());
    }

    @Test
    void arrivalOrderDoesNotAffectDecision() {
        CombinedDecision result = combiner.combine(
                "REQ-1",
                List.of(
                        reply("fraud", BranchVerdict.PASS),
                        reply("inventory", BranchVerdict.PASS)));

        assertEquals(DecisionStatus.CONFIRMED, result.status());
    }
}
~~~

The result has the same meaning regardless of whether the reply order is Fraud → Inventory or vice versa. In an asynchronous system, **do not rely on arrival order** to distinguish the two branches.

### 8.2. One branch FAILS, overall result is REJECTED

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReplyCombinerRejectTest {
    private final ReplyCombiner combiner = new ReplyCombiner();

    @Test
    void fraudFailureMakesCombinedDecisionRejected() {
        CombinedDecision decision = combiner.combine(
                "REQ-7",
                List.of(
                        new BranchReply("REQ-7", "inventory",
                                BranchVerdict.PASS, "STOCK_OK"),
                        new BranchReply("REQ-7", "fraud",
                                BranchVerdict.FAIL, "RISK_DENIED")));

        assertEquals(DecisionStatus.REJECTED,
                decision.status());
        assertEquals(BranchVerdict.FAIL,
                decision.repliesByRecipient().get("fraud").verdict());
    }
}
~~~

### 8.3. Testing missing, duplicate, and wrong request replies

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class ReplyCombinerInvalidTest {
    private final ReplyCombiner combiner = new ReplyCombiner();

    @Test
    void inventoryOnlyCannotConfirmTheOrder() {
        assertThrows(IllegalStateException.class, () ->
                combiner.combine("REQ-8", List.of(
                        new BranchReply("REQ-8", "inventory",
                                BranchVerdict.PASS, "OK"))));
    }

    @Test
    void twoInventoryRepliesCannotSubstituteFraud() {
        BranchReply inventory = new BranchReply(
                "REQ-9", "inventory", BranchVerdict.PASS, "OK");

        assertThrows(IllegalArgumentException.class, () ->
                combiner.combine("REQ-9",
                        List.of(inventory, inventory)));
    }

    @Test
    void foreignRequestResultIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                combiner.combine("REQ-10", List.of(
                        new BranchReply("REQ-10", "inventory",
                                BranchVerdict.PASS, "OK"),
                        new BranchReply("REQ-OLD", "fraud",
                                BranchVerdict.PASS, "OK"))));
    }

    @Test
    void unknownRecipientIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                combiner.combine("REQ-11", List.of(
                        new BranchReply("REQ-11", "inventory",
                                BranchVerdict.PASS, "OK"),
                        new BranchReply("REQ-11", "analytics",
                                BranchVerdict.PASS, "OK"))));
    }

    @Test
    void emptyResultSetCannotBecomeConfirmed() {
        assertThrows(IllegalStateException.class, () ->
                combiner.combine("REQ-12", List.of()));
    }
}
~~~

These tests only verify **the result after a reply collection has been received**. They do not verify whether the Spring Integration scatterer sends to both branches, whether replies return to the gatherer, whether the gateway times out properly, or whether a broker preserves correlation. Those belong to the integration tests below.

## 9. Implementing Scatter–Gather in Spring Integration

### 9.1. Role of framework components

Spring Integration provides `ScatterGatherHandler` and corresponding Java DSL APIs to build scatter/gather flows. Architecturally:

~~~text
MessagingGateway
  |
  v
order.checks.input
  |
  v
ScatterGatherHandler
  |
  +-- Scatter: RecipientListRouter / PublishSubscribeChannel
  |       +-- Inventory service
  |       +-- Fraud service
  |
  +-- Gather: AggregatingMessageHandler
          -> release strategy
          -> output processor / combined decision
          -> reply to Gateway
~~~

**Two common scatter styles** use a recipient list (optionally conditional) or broadcast to subscribers of a Publish–Subscribe Channel. Regardless of the choice, the gatherer must know **replies from which recipients are expected**, receive reply messages rather than just dispatch events, and have a timeout/error policy.

### 9.2. Java DSL example: two recipient flows, one result

To focus on the pattern, both branches use synchronous services in the same JVM and return `BranchReply`. There is no real database, HTTP, or broker. This is an **illustrative configuration in Spring Integration 6.x Java DSL style**; when adopting it in a project, verify the exact DSL signatures and behavior of your dependency version, especially for `scatterGather`, `recipientFlow`, `releaseStrategy`, and `outputProcessor`.

~~~java
import java.util.List;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;

@MessagingGateway
interface OrderCheckGateway {
    @Gateway(
            requestChannel = "order.checks.input",
            replyTimeout = 5000)
    CombinedDecision evaluate(CheckOrderRequest request);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class ScatterGatherOrderConfiguration {

    @Bean
    InventoryCheck inventoryCheck() {
        return new InventoryCheck();
    }

    @Bean
    FraudCheck fraudCheck() {
        return new FraudCheck();
    }

    @Bean
    ReplyCombiner replyCombiner() {
        return new ReplyCombiner();
    }

    @Bean
    IntegrationFlow scatterGatherOrders(
            InventoryCheck inventory,
            FraudCheck fraud,
            ReplyCombiner combiner) {

        return IntegrationFlow.from("order.checks.input")
                .scatterGather(
                        scatterer -> scatterer
                                .recipientFlow(flow -> flow
                                        .handle(
                                                CheckOrderRequest.class,
                                                (request, headers) ->
                                                        inventory.check(request)))
                                .recipientFlow(flow -> flow
                                        .handle(
                                                CheckOrderRequest.class,
                                                (request, headers) ->
                                                        fraud.check(request))),
                        gatherer -> gatherer
                                .releaseStrategy(group -> {
                                    Set<String> seen =
                                            group.getMessages().stream()
                                                    .map(Message::getPayload)
                                                    .map(BranchReply.class::cast)
                                                    .map(BranchReply::recipientId)
                                                    .collect(
                                                            java.util.stream.Collectors
                                                                    .toSet());
                                    return seen.containsAll(
                                            ReplyCombiner.REQUIRED);
                                })
                                .outputProcessor(group -> {
                                    List<BranchReply> replies =
                                            group.getMessages().stream()
                                                    .map(Message::getPayload)
                                                    .map(BranchReply.class::cast)
                                                    .toList();
                                    if (replies.isEmpty()) {
                                        throw new IllegalStateException(
                                                "NO_BRANCH_REPLIES");
                                    }
                                    return combiner.combine(
                                            replies.get(0).requestId(),
                                            replies);
                                }))
                .get();
    }
}
~~~

**Meaning of each part:**

1. The Gateway receives `CheckOrderRequest` and requires **one** `CombinedDecision`.
2. The Scatterer creates paths to **two independent recipient flows**: Inventory and Fraud.
3. Each handler **must return `BranchReply`**, instead of just performing a side effect and returning `null`.
4. The Release strategy waits until both `inventory` and `fraud` are seen. It does not release merely because total reply count equals two.
5. The Output processor converts the reply set into a business decision via `ReplyCombiner`, continuing to check IDs, duplicates, and foreign recipients.
6. After gather, the result completes along the Gateway's reply path; the caller does not receive a raw list of messages if the contract only requires `CombinedDecision`.

### 9.3. Conditions for the code above to behave meaningfully

In a real flow, **the correlation metadata used by the gatherer to group messages** must be emitted by the scatterer, and branch replies must preserve the proper return/correlation path. If you add a Transformer that recreates the message, an outbound adapter, or a custom handler that drops `replyChannel`, `correlationId`, or required sequence headers, replies may not return to the group the Gateway is waiting on.

Therefore, the sample code focuses on request/reply **within a single application context**. When moving to HTTP/Kafka/JMS/AMQP, you must add adapter-level tests, reply destinations, a durable correlation store if needed, and timeout/recovery. Do not assume you can serialize a `replyChannel` object from one JVM directly to another process.

### 9.4. Why is release strategy alone not enough to solve duplicates?

The release strategy in the example waits for **two unique recipient IDs**. If Inventory sends a reply **twice** and Fraud replies once, the group can have three messages and still satisfy the release condition. Then `ReplyCombiner` **throws a duplicate error**: the result is not published as successful.

This is a **fail-closed choice to catch bugs**, not a complete deduplication system. Production may need to filter duplicates **before** the Aggregator or design a group processor that accepts one final result/recipient per idempotency key and attempt/version, depending on delivery semantics. Do not set release strategy to `group.size() >= 2` if duplicates can occur.

### 9.5. The end of a recipient flow must produce a reply

If the Inventory branch is written as:

~~~java
// One-way endpoint: does not reply to the Gatherer.
.handle(message -> {
    inventoryClient.reserve(message.getPayload());
})
~~~

then the request may have caused a side effect in the warehouse, but the gatherer has no `InventoryReply` to make a decision. When designing Scatter–Gather:

- Define a concrete reply type for each recipient.
- Report PASS only when the branch business logic has satisfied the contract, not merely when the message was received.
- Specify clearly if a branch has a long-running task: return PENDING or wait until deadline?
- Do not return `null` and expect the Aggregator to fabricate a result.
- If a handler produces multiple replies, define whether a recipient is allowed to have multiple results.

### 9.6. Why not use a Gateway calling two services sequentially?

Calling Inventory then Fraud sequentially can be the **simple and right** approach when business scope is small, latency is low, and independent scaling is not needed. Scatter–Gather brings additional benefits and costs:

| Approach | Advantage | Drawback |
|---|---|---|
| Sequential services | Easy to understand, short transaction/error path. | Latency can add up, directly coupled to service ordering. |
| Synchronous Scatter–Gather | Decouples the two branches, clear gather contract. | May still run on caller thread, latency affected by handlers. |
| Asynchronous Scatter–Gather | Can process in parallel, isolates threads. | Correlation, timeout, queue, late reply, error recovery are harder. |
| Durable workflow orchestrator | Manages long-running work, retries, human approvals. | Higher design/operational cost. |

Do not pick Scatter–Gather just because there are two functions to call. Pick it when **the multi-branch contract and reply set** are genuinely an important part of the architecture.

## 10. Integration tests for the Scatter–Gather flow

### 10.1. Both branches PASS

~~~java
import java.math.BigDecimal;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(ScatterGatherOrderConfiguration.class)
class ScatterGatherHappyPathTest {
    @Autowired
    OrderCheckGateway gateway;

    @Test
    void oneRequestProducesTwoRepliesAndOneDecision() {
        CheckOrderRequest request = new CheckOrderRequest(
                "REQ-A", "ORD-A", 2, new BigDecimal("5000000"));

        CombinedDecision result = gateway.evaluate(request);

        assertEquals("REQ-A", result.requestId());
        assertEquals(DecisionStatus.CONFIRMED, result.status());
        assertEquals(Set.of("inventory", "fraud"),
                result.repliesByRecipient().keySet());
        assertEquals(BranchVerdict.PASS,
                result.repliesByRecipient().get("inventory").verdict());
        assertEquals(BranchVerdict.PASS,
                result.repliesByRecipient().get("fraud").verdict());
    }
}
~~~

This test, when run against a Java DSL configuration compatible with the project's Spring Integration version, verifies **the fan-out, reply-producing handlers, gather, output processor, and Gateway reply**. Unlike the unit test in section 8, it requires a Spring context and the framework's real correlation mechanism.

### 10.2. One branch FAILS still must return a valid decision

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(ScatterGatherOrderConfiguration.class)
class ScatterGatherRejectionTest {
    @Autowired
    OrderCheckGateway gateway;

    @Test
    void fraudRejectsHighValueOrder() {
        CheckOrderRequest request = new CheckOrderRequest(
                "REQ-B", "ORD-B", 2, new BigDecimal("15000000"));

        CombinedDecision decision = gateway.evaluate(request);

        assertEquals(DecisionStatus.REJECTED, decision.status());
        assertEquals(BranchVerdict.PASS,
                decision.repliesByRecipient().get("inventory").verdict());
        assertEquals(BranchVerdict.FAIL,
                decision.repliesByRecipient().get("fraud").verdict());
    }

    @Test
    void inventoryRejectsQuantityAboveAvailableStock() {
        CheckOrderRequest request = new CheckOrderRequest(
                "REQ-C", "ORD-C", 12, new BigDecimal("5000000"));

        CombinedDecision decision = gateway.evaluate(request);

        assertEquals(DecisionStatus.REJECTED, decision.status());
        assertEquals(BranchVerdict.FAIL,
                decision.repliesByRecipient().get("inventory").verdict());
        assertEquals(BranchVerdict.PASS,
                decision.repliesByRecipient().get("fraud").verdict());
    }
}
~~~

Here `REJECTED` is a **valid business outcome** evaluated by both branches, different from a **technical failure** such as a lookup timeout, handler exception, or missing reply.

### 10.3. What synchronous tests do not yet prove

This is a demo using in-JVM services without external systems. The tests above do **not** yet prove:

- The two branches actually execute concurrently in time.
- Replies can travel through a message broker and return to the right group.
- Groups survive crash/restart.
- Duplicates and retries do not cause side effects.
- The Gateway returns PENDING/TIMED_OUT per contract when a reply is missing.
- Thread pools/reply queues behave properly under overload.
- Metrics and error channels are observed properly.

Subsequent sections add test plans for these cases without confusing accepted/dispatched with completed.

## 11. One branch does not respond: timeout is not PASS

### 11.1. What happens when Fraud does not reply?

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Gateway
    participant S as Scatter
    participant I as Inventory
    participant F as Fraud
    participant A as Gatherer
    C->>G: CheckOrder REQ-20
    G->>S: Dispatch request
    S->>I: Inventory check
    S->>F: Fraud check
    I-->>A: inventory PASS
    Note over F: Timeout / no reply
    Note over A: Missing Fraud result
    A--xG: Cannot emit complete decision
    G-->>C: Timeout or pending per contract
~~~

If the gatherer requires both recipients, **an Inventory PASS alone is not enough to produce `CONFIRMED`**. With a synchronous Gateway, the request may wait until `replyTimeout` and time out. However, a Gateway timeout **does not necessarily expire the message group** or cancel the Fraud task at the same time.

### 11.2. Distinguishing three deadlines

| Timeout type | Question | Related configuration point |
|---|---|---|
| **Branch timeout** | How long can Inventory/Fraud be called? | HTTP client, DB, outbound gateway, broker request/reply. |
| **Gather/group timeout** | When must an incomplete group expire/release/go to recovery? | Aggregator/group store/expiry strategy. |
| **Caller/Gateway reply timeout** | How long is the caller willing to wait? | MessagingGateway, HTTP ingress, SLA. |

The three timeouts do not necessarily have the same value. For instance, a Gateway waits 3 seconds, while a Fraud consumer only replies after 5 seconds: the caller has already timed out while Fraud may still continue. If the group store keeps the group, there must be a strategy for releasing, expiring, or handling late replies.

**Dangerous mistake:** Catching a timeout exception and returning `CONFIRMED` to the caller because Inventory already PASSED. That violates the mandatory two-condition policy.

### 11.3. Policies when results are missing

Valid options depending on the business:

1. **Fail closed:** return `TIMED_OUT`/`CANNOT_CONFIRM`, do not confirm the order.
2. **PENDING:** create an operation ID and let the caller check status later; appropriate when the business allows processing longer than an HTTP request.
3. **Partial result:** report clearly Inventory PASS, Fraud MISSING; never present as a complete conclusion.
4. **Retry Fraud:** retry only that branch within deadline, max attempts, and idempotency bounds.
5. **Manual review:** route the request to a review queue per policy if automatic verification is not possible.

There is no "always best" option without knowing confirmation conditions and SLO requirements.

### 11.4. A DTO for reporting missing results

If reporting is needed when the deadline expires, separate it from `CombinedDecision`:

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

record IncompleteCheckReport(
        String requestId,
        Set<String> responded,
        Set<String> missing,
        String status) {}

final class MissingReplyInspector {
    IncompleteCheckReport inspect(
            String requestId,
            Collection<BranchReply> observed) {

        Set<String> responded = new LinkedHashSet<>();
        for (BranchReply reply : observed) {
            if (!requestId.equals(reply.requestId())) {
                throw new IllegalArgumentException("FOREIGN_REPLY");
            }
            if (!ReplyCombiner.REQUIRED.contains(
                    reply.recipientId())) {
                throw new IllegalArgumentException(
                        "UNEXPECTED_RECIPIENT");
            }
            responded.add(reply.recipientId());
        }

        Set<String> missing =
                new LinkedHashSet<>(ReplyCombiner.REQUIRED);
        missing.removeAll(responded);

        return new IncompleteCheckReport(
                requestId,
                Set.copyOf(responded),
                Set.copyOf(missing),
                missing.isEmpty() ? "ALL_REPLIED" : "INCOMPLETE");
    }
}
~~~

This is only **an application function inspecting an observed set of replies**. It does not wait on its own, does not configure `groupTimeout`, and does not generate `ErrorMessage`. Therefore, testing the Inspector must not be used to claim that the Scatter–Gather framework timeout works.

### 11.5. Testing missing replies without real waiting

~~~java
import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MissingReplyInspectorTest {
    @Test
    void inventoryOnlyLeavesFraudMissing() {
        IncompleteCheckReport report =
                new MissingReplyInspector().inspect(
                        "REQ-55",
                        List.of(new BranchReply(
                                "REQ-55", "inventory",
                                BranchVerdict.PASS, "OK")));

        assertEquals(Set.of("inventory"), report.responded());
        assertEquals(Set.of("fraud"), report.missing());
        assertEquals("INCOMPLETE", report.status());
    }
}
~~~

## 12. Synchronous, asynchronous, and truly parallel fan-out

### 12.1. Synchronous: one slow branch can block the whole request

If both branches use `DirectChannel` and synchronous handlers, the duration of the dispatch path can be affected by the duration of each branch. Even though a diagram splits into two paths, do not promise "both calls always run in parallel" just because Scatter–Gather was configured.

For example, Inventory takes 50 ms and Fraud takes 2 seconds. In a synchronous configuration, the caller may have to wait nearly 2 seconds or more, depending on dispatch order and how branch handlers execute. Do not treat the latency simply as `max(50ms, 2s)` in every setup if execution is effectively sequential.

### 12.2. Asynchronous: faster but harder

An architecture with an executor/broker:

~~~mermaid
flowchart TB
    G[Gateway] --> S[Scatter]
    S --> Q1[(inventory.requests)]
    S --> Q2[(fraud.requests)]
    Q1 --> W1[Inventory Worker]
    Q2 --> W2[Fraud Worker]
    W1 --> R1[(inventory.replies)]
    W2 --> R2[(fraud.replies)]
    R1 --> C[Correlated Gatherer]
    R2 --> C
    C --> D[Combined Decision / Timeout]
~~~

Benefits:

- Both workers can process independently and concurrently.
- Separate thread pools, queues, and retry policies can be assigned.
- Processes can be separated when using a broker/adapter.

In return:

- Successful `send` might only mean enqueued.
- Full queues, rejected tasks, or broker disconnects require separate error paths.
- A worker may crash after committing but before sending the reply.
- Replies may arrive out of order, duplicated, lost, or after the deadline.
- If the group store is in-memory, a JVM crash can lose gather state.
- Messages from another system must carry correlation/reply destinations transportable over the wire.

### 12.3. TaskExecutor is not synonymous with a durable broker

If you add a `TaskExecutor` to the scatter channel, handlers can run on worker threads. However, in-memory tasks **are not automatically persisted across JVM restarts**. And a **shared** executor for Fraud/Inventory can be saturated by the slower branch, starving the remaining branch.

When stronger isolation is needed, recipients can be placed behind **separate queues/brokers**, with per-branch consumer capacity, retry, DLQ, and idempotency. Yet a "broker" also does not automatically have suitable durability/ack/retention policies unless configured.

### 12.4. When should the Gateway return immediately?

If the Fraud check takes minutes or requires human approval, holding a synchronous Gateway waiting for all replies may be unreasonable. Instead:

~~~text
POST /check-orders
  -> 202 Accepted
  -> requestId / status URL

Workers process asynchronously
  -> Gatherer updates durable status

GET /check-orders/{requestId}
  -> PENDING / CONFIRMED / REJECTED / TIMED_OUT
~~~

This pattern still uses scatter/gather at the processing layer, while **the API contract** shifts to an eventual result. That is an intentional architectural choice, not a default property of `@MessagingGateway`.

## 13. Error handling: how does one failing branch affect things?

### 13.1. Throwing an exception is different from returning FAIL

Suppose Fraud returns:

~~~java
new BranchReply(
        "REQ-100",
        "fraud",
        BranchVerdict.FAIL,
        "RISK_DENIED");
~~~

This is a **business result** and can be used by the gatherer to produce `REJECTED`. In contrast:

~~~java
throw new IllegalStateException("Fraud service unavailable");
~~~

is a **technical error**, which normally **does not produce a normal `BranchReply`** unless an error flow is explicitly designed to translate the error into a result with an appropriate status. When a branch throws an exception:

- In a synchronous flow, the exception may propagate to the sender/Gateway.
- In an asynchronous flow, the error may go to `ErrorMessage`/`errorChannel` or an error handler depending on the adapter/poller/executor.
- A scattered branch without a reply can leave the group missing a result.
- Other branches may have already produced side effects before the error occurred.

Do not catch every exception and convert it to `PASS` just to "have enough results".

### 13.2. Layered error matrix

| Layer | Example error | Mitigation |
|---|---|---|
| **Input** | Missing requestId/amount, invalid quantity. | Validate before scatter; do not generate N requests from malformed input. |
| **Scatter** | Recipient has no consumer, channel does not exist. | Config/readiness check, dispatch error, controlled fallback. |
| **Executor/queue** | Queue full, task rejected. | Backpressure/bounded retry/overload status, no silent drop. |
| **Branch** | Inventory HTTP timeout, Fraud service unavailable. | Per-branch retry, deadline, error/recovery, idempotency. |
| **Reply transport** | Lost reply or wrong correlation header. | Correlation mapping, durable replies, late reply policy. |
| **Gather** | Duplicate, unexpected recipient, group expired. | Dedupe/quarantine, release and cleanup policy. |
| **Decision** | Data mismatch or invalid status. | Refuse decision, audit, do not Confirm. |
| **Gateway** | Reply timeout before gather. | PENDING/TIMED_OUT contract; do not assume tasks were cancelled. |

### 13.3. `errorChannel` does not automatically create a valid reply

In Spring Integration, `ErrorMessage` can carry an exception for an error flow to process. However, **not every error is automatically sent to every `errorChannel`**, and **an ErrorMessage does not automatically satisfy the `BranchReply` contract**. If you want the gatherer to still return a combined result when one branch fails:

1. Define a branch result with status `ERROR`/`UNAVAILABLE` or an appropriate business status.
2. Convert the error into a branch result with the **exact requestId + recipientId** only when allowed by the contract.
3. Distinguish **branch technical error** from **business FAIL**; do not conflate them.
4. Decide on fail-fast, wait-for-all, or partial-result per policy and deadline.
5. Ensure the error flow does not loop infinitely if it also fails.

For example, a system might return `CANNOT_CONFIRM_INVENTORY_UNAVAILABLE` instead of `REJECTED_FRAUD`. Neither is `CONFIRMED`, but they differ in cause and retryability.

### 13.4. Where to retry?

**Do not automatically retry the entire Scatter–Gather** when only Fraud fails. Retrying the whole request could call Inventory again even though it already succeeded, and if Inventory already reserved stock, it could create a **double reservation**.

A usually safer design:

~~~text
REQ-200
  inventory -> PASS (reservationId=R-1)
  fraud     -> TIMEOUT

Retry policy:
  inventory -> keep previous outcome if still valid
  fraud     -> retry within limits
~~~

Note that whether the Inventory outcome is still valid is also a business rule: a stock hold may expire, quantities may change, or a reservation may be cancelled. You cannot always reuse Inventory PASS indefinitely.

### 13.5. Idempotency and compensation

If a branch only **reads state**, retries generally carry lower side-effect risk. If Inventory **reserves stock** or Fraud **writes an inspection record**, re-invoking can create new state.

Therefore:

- Use a stable operation key based on `requestId + recipientId` or a reservation ID supported by the target system.
- Use a separate retry attempt ID to observe invocation attempts.
- Design timeouts with uncertain outcomes: look up/reconcile before repeating a reservation.
- If Fraud FAILS after Inventory has reserved, you may need **reservation release/compensation**.
- Do not assume Scatter–Gather creates a distributed transaction spanning both branches.

## 14. Dynamic branch count per message: expected recipients must not be hardcoded

### 14.1. When are there two branches and when are there three?

In the earlier example, every request required `inventory` and `fraud`. In practice, international orders may additionally require `compliance`:

~~~text
VN order:
  expectedRecipients = {inventory, fraud}

INTL order:
  expectedRecipients = {inventory, fraud, compliance}
~~~

A Recipient List Router can select recipients conditionally. **The gatherer must know the exact set scattered to**, otherwise:

- A VN request could wait for Compliance that was never invoked.
- An INTL request could release after two replies and skip mandatory Compliance.
- Retry/resend could target different recipients than the original request if policy changes mid-flight.

### 14.2. Planning recipients before scattering

You can define an immutable plan:

~~~java
import java.util.Set;

record ScatterPlan(
        String requestId,
        String policyVersion,
        Set<String> expectedRecipients) {

    ScatterPlan {
        if (requestId == null || requestId.isBlank()
                || policyVersion == null || policyVersion.isBlank()) {
            throw new IllegalArgumentException("INVALID_SCATTER_PLAN");
        }
        expectedRecipients = Set.copyOf(expectedRecipients);
        if (expectedRecipients.isEmpty()) {
            throw new IllegalArgumentException("NO_RECIPIENTS");
        }
    }
}

final class RecipientPlanner {
    ScatterPlan plan(String requestId, String market) {
        return switch (market) {
            case "VN" -> new ScatterPlan(
                    requestId, "policy-v1",
                    Set.of("inventory", "fraud"));
            case "INTL" -> new ScatterPlan(
                    requestId, "policy-v1",
                    Set.of("inventory", "fraud", "compliance"));
            default -> throw new IllegalArgumentException(
                    "UNSUPPORTED_MARKET");
        };
    }
}
~~~

This is **illustrative Java policy code**, not a full DSL configuration for a dynamic Recipient List in Spring Integration. When applying it:

1. The Planner must select recipients from a **trusted allowlist**.
2. The Scatterer must actually send to **the exact selected recipients**.
3. The Gatherer must receive the exact plan or expected set and not re-guess it using the "latest" policy.
4. The Plan needs a version if policy changes while a request is still in flight.
5. With fail-fast/retry, do not automatically shrink the expected set after one recipient errors.

### 14.3. Policy snapshots prevent mid-flight changes

~~~text
T1: Request REQ-1 creates plan v1
    expected = {inventory, fraud}

T2: Configuration changes to policy v2
    expected for new requests = {inventory, fraud, compliance}

T3: REQ-1 receives both inventory and fraud
~~~

If the gatherer reads **policy v2** to compute the expected set for REQ-1 at T3, it will wait for a Compliance reply **that was never scattered**. Therefore you must use the expected recipients from **the plan locked at T1** or a replan/checkpoint mechanism with an explicit contract.

### 14.4. Do not fan-out to arbitrary channels from client payloads

If a client supplies a channel name like `orders.admin.internal` and asks to scatter there, the system risks **route injection** or sending data to unauthorized branches. A dynamic recipient list needs:

- Authentication/authorization at ingress.
- Separation between business keys and bean/channel names.
- Mapping through a server-side allowlist.
- Limits on recipient count to avoid unbounded fan-out.
- Control over which sensitive payload fields each recipient is allowed to see.
- Recording policy version and recipient selection in appropriate logs/audits.

## 15. Correlation when replies cross threads or systems

### 15.1. Same request, different threads

When Inventory and Fraud run on different executors, the two replies can arrive at the gatherer in any order:

~~~mermaid
sequenceDiagram
    participant G as Gatherer
    participant I as Inventory
    participant F as Fraud
    I-->>G: Inventory PASS REQ-1
    F-->>G: Fraud PASS REQ-2
    F-->>G: Fraud PASS REQ-1
    I-->>G: Inventory PASS REQ-2
    Note over G: Must separate into two groups REQ-1 and REQ-2
~~~

If you rely only on arrival order or just `orderId` when multiple checks occur, groups will be mismatched. In parallel processing, the correlation key must be **stable and sufficiently distinct**.

### 15.2. Minimum correlation checks

Each reply should be checked for:

~~~text
requestId    : non-empty; the group being replied to
recipientId  : belongs to the locked expectedRecipients
attemptId    : if retry/redelivery needs distinction
status       : valid value for the recipient
payload      : matches schema and referenced identity
traceContext : if cross-transport tracing is needed
~~~

For an Inventory reply with `reservationId`, ensure the reservation belongs to the right `orderId`/`requestId`; checking recipientId alone is not enough to prevent mixing data across different orders.

### 15.3. Do not serialize internal `replyChannel` objects over a broker

Spring Integration Gateway/Scatter–Gather within the same JVM may use message headers containing channel references or internal return-address mechanisms. Across Kafka, JMS, HTTP, or AMQP, a `MessageChannel` object from JVM A **has no direct meaning** in JVM B.

Instead, define:

1. A valid **reply topic/queue/endpoint** with a gather consumer.
2. A Correlation ID/request ID serialized in a transferable type.
3. A Header mapper allowing necessary metadata.
4. Authentication and authorization of reply producers.
5. TTL/retention/dead-letter strategy for expired replies.
6. A Group state store with durability matching restart requirements.

### 15.4. When a reply arrives after the deadline

~~~text
12:00:00  Request REQ-9 is scattered
12:00:01  Inventory PASS
12:00:03  Gateway returns TIMED_OUT
12:00:05  Fraud PASS arrives at gatherer
~~~

Handling options:

- **Intentionally discard the late reply**, record metrics/audit; do not emit a second decision to a caller that already timed out.
- **Update operation status** if the API allows querying/reconciliation after timeout.
- **Execute compensation** if an earlier branch already created side effects but the overall result is no longer valid.
- **Emit a reconciliation/adjustment event** if downstream systems need to be notified of the final outcome.

**Risk:** if the old group already expired and the gatherer creates a new group from Fraud PASS, it must not be treated as a new request waiting indefinitely for Inventory. You need a policy for **late arrivals and completed/expired group IDs**, not just memory cleanup.

## 16. Controlled asynchronous testing

### 16.1. Why `Thread.sleep` is not a completion signal

A test like:

~~~java
gateway.evaluate(request);
Thread.sleep(500);
assertEquals(2, resultCounter.get());
~~~

flakes easily in CI due to varying thread scheduling and machine load. For testing async Scatter–Gather, use:

- `CountDownLatch` to verify a handler **has started**.
- Another latch to control **when it is allowed to return its reply**.
- `Future` to observe whether the Gateway waits/times out properly.
- `await(timeout)` instead of fixed sleeps.
- `finally` to always release latches and clean up executors.

### 16.2. Test plan for one slow branch

~~~text
Given:
  Inventory Handler is fast and returns PASS.
  Fraud Handler has started but waits on a release latch.

When:
  Send REQ-X through the Gateway on a separate thread.
  Wait for Fraud to signal started.

Then (before release):
  Gateway does not yet have a completed CombinedDecision.
  Gatherer has not yet released.

When:
  Open the release latch so Fraud returns PASS.

Then:
  Gateway receives one CombinedDecision CONFIRMED.
  repliesByRecipient contains exact inventory and fraud.
~~~

Do not use the same thread for both the synchronous Gateway call and the latch control logic; if the test thread is blocked in `gateway.evaluate(...)`, it will not be able to open the latch in time.

### 16.3. Timeout tests must have predictable outcomes

When Fraud does not respond:

1. Submit the request on a thread/future to avoid blocking the test.
2. Use a finite deadline for `Future.get` and the Gateway reply timeout.
3. Verify no spurious `CombinedDecision(CONFIRMED)` is produced.
4. Check group state or configured error/recovery behavior.
5. Release latches in `finally` and ensure workers/executors shut down.
6. Let Fraud send a late reply after the deadline to test the late-result policy separately.

Note: the exception type thrown by the Gateway may vary by configuration/version; tests should assert **business outcome and cause chain** rather than depending on unstable message text.

### 16.4. Testing duplicates and replies from other groups

If the framework does not provide a direct way to inject replies via a convenient API, create a separate integration test:

- A mock scatterer sends Inventory PASS twice, with Fraud not yet replying.
- The gatherer **does not** emit CONFIRMED based on those two messages.
- When Fraud replies, the group processor handles the duplicate per contract (fail closed or configured dedupe).
- A reply from `REQ-OLD` is not placed into group `REQ-NEW`.
- An unknown recipient is not counted toward the expected set.

To verify the release/dedupe semantics of `AggregatingMessageHandler`, tests must go through the real handler configuration, **not just call `ReplyCombiner.combine(...)`**.

### 16.5. Test assertions must distinguish each milestone

| Assertion | Evidence |
|---|---|
| Scatterer selected two recipients | Each handler was invoked/received the request. |
| Broker/executor accepted | Submit/enqueue acknowledged per contract. |
| Branch finished | Valid `BranchReply` or failure outcome exists. |
| Gather completed | Correct group and release strategy produced the result. |
| Gateway returned | Caller received `CombinedDecision`/status/error. |
| Side effects committed | Evidence from DB/transport/remote service, not just a counter. |

A test that only observes "handler was called" does not prove **the gatherer combined the results**. Conversely, only asserting the Gateway returns `CONFIRMED` may miss duplicates or a skipped branch if the combiner/release strategy is flawed.

## 17. Observability: tracking each branch and each group

### 17.1. A request must be traceable to every reply

Desired operational trace:

~~~text
REQ-1001
  SCATTER_PLANNED expected={inventory,fraud}
  RECIPIENT_DISPATCHED inventory
  RECIPIENT_DISPATCHED fraud
  BRANCH_COMPLETED inventory PASS
  BRANCH_COMPLETED fraud PASS
  GATHER_RELEASED uniqueRecipients=2
  DECISION_RETURNED CONFIRMED
~~~

For a failing request:

~~~text
REQ-1002
  SCATTER_PLANNED expected={inventory,fraud}
  BRANCH_COMPLETED inventory PASS
  BRANCH_FAILED fraud FRAUD_SERVICE_TIMEOUT
  GATHER_EXPIRED missing={fraud}
  DECISION_UNAVAILABLE status=TIMED_OUT
~~~

This is an **application-proposed log schema**, not Spring Integration's default output. Do not log `BRANCH_COMPLETED` the moment a queue accepts the task; wait for the outcome per the branch contract.

### 17.2. Structured log fields

| Field | Purpose |
|---|---|
| `requestId` | Connects scatter, branch replies, and gather for one check invocation. |
| `orderId` | Business investigation; may relate to multiple requests. |
| `traceId`/`spanId` | Distributed tracing across threads/services. |
| `recipientId` | Branch being called, awaited, or failing. |
| `policyVersion` | Version of recipient selection/release rules. |
| `expectedRecipients` | Set of branches locked at scatter time. |
| `attemptId` | Distinguishes attempts during retry/redelivery. |
| `durationMs` | Latency of the branch and the entire request. |
| `outcome`/`reasonCode` | PASS/FAIL/ERROR/TIMED_OUT and cause. |
| `groupState` | Waiting, completed, expired per workflow. |

Do not log full customer PII, tokens, sensitive request payloads, or Fraud score details without clear authorization and purpose. For tracing, also check context propagation when crossing a `TaskExecutor` or transport boundary: MDC/thread-locals do not automatically follow every worker thread.

### 17.3. Metrics must separate scatter, gather, and business results

| Illustrative metric | Purpose |
|---|---|
| `scatter_requests_total` | How many requests started fan-out? |
| `scatter_recipient_dispatch_total{recipient}` | How many times was sending to each branch attempted? |
| `branch_completed_total{recipient,outcome}` | How many final outcomes did each branch produce? |
| `branch_failed_total{recipient,reason}` | Per-branch technical errors. |
| `branch_latency_seconds{recipient}` | Which branch is causing high latency? |
| `gather_groups_pending` | How many groups still lack full results? |
| `gather_groups_completed_total` | How many groups were released per policy? |
| `gather_groups_expired_total` | How many groups lacked replies before deadline? |
| `gather_duplicate_replies_total{recipient}` | Are there many redeliveries/duplicates? |
| `scatter_combined_decisions_total{status}` | CONFIRMED/REJECTED and other contract statuses. |
| `reply_late_total{recipient}` | Which replies arrive after group expiry? |
| `executor_queue_depth` | Is the worker pool saturated? |

These are **illustrative** metric names, not meters automatically registered by Spring Integration in every project. Use bounded-cardinality labels like recipient/status/reason code; do **not** use `requestId`, `orderId`, or `traceId` as metric labels because they have huge cardinality. Such IDs belong in logs/traces with appropriate retention and access controls.

### 17.4. Message History does not replace business audit

Spring Integration Message History can show which components a message passed through when enabled, but:

- Does not prove each branch committed side effects.
- Does not store the expected recipient set for a request.
- Does not reconcile duplicate recipients or cross-group replies.
- Does not replace distributed tracing across transports.
- Does not make the group store durable.

For critical workflows, persist **request context/expected set, reply outcomes, decision version, and final processing state** in a place that satisfies audit/recovery requirements.

## 18. Scatter–Gather test matrix

| ID | Scenario | What to verify |
|---|---|---|
| SG-01 | One request, Inventory PASS, Fraud PASS | Returns exactly one `CONFIRMED`, both recipients present. |
| SG-02 | Inventory FAIL, Fraud PASS | `REJECTED`, not `CONFIRMED`. |
| SG-03 | Inventory PASS, Fraud FAIL | `REJECTED`, preserves Fraud's reason. |
| SG-04 | Both FAIL | `REJECTED`, does not discard either result. |
| SG-05 | Fraud replies before Inventory | Same result as reverse order. |
| SG-06 | Only Inventory replies | Does not release complete decision. |
| SG-07 | Only Fraud replies | Does not release complete decision. |
| SG-08 | Two Inventory replies, Fraud missing | Duplicate does not substitute for missing recipient. |
| SG-09 | Reply from another request | Not merged into current group. |
| SG-10 | Reply from unknown recipient | Rejected or quarantined per policy. |
| SG-11 | One branch returns `null` / one-way | Does not claim all replied; clear timeout/error. |
| SG-12 | Input missing requestId | Validation blocks before fan-out. |
| SG-13 | Two requests running concurrently | No mixed replies, exactly two groups. |
| SG-14 | Fraud slow, Inventory fast | Gateway does not return CONFIRMED before Fraud. |
| SG-15 | Fraud timeout | Deadline/recovery, not silently PASS. |
| SG-16 | Late reply after group expiry | Clear policy: ignore, update status, or reconcile. |
| SG-17 | Branch throws technical exception | Distinguish technical error from business FAIL. |
| SG-18 | Executor saturated | Rejection/backpressure, no silent drop. |
| SG-19 | Recipient channel has no consumer | Dispatch failure/timeout observed. |
| SG-20 | Broker redelivers reply | Correct dedupe/duplicate detection. |
| SG-21 | Worker commits then loses ack | Retry does not duplicate side effects. |
| SG-22 | Gateway timeout before gather timeout | Group/late reply handled independently. |
| SG-23 | Group store reset/restart | Matches chosen durability/recovery contract. |
| SG-24 | INTL order adds Compliance | Expected set accurately includes three recipients. |
| SG-25 | VN order only two recipients | Does not wait for unscattered Compliance. |
| SG-26 | Policy changes while request is pending | Expected set locked at scatter does not drift. |
| SG-27 | Fraud data returns wrong `orderId` | Reconciliation rejects mismatched identity result. |
| SG-28 | Reply via HTTP/Kafka/JMS adapter | Correlation and schema restored accurately. |
| SG-29 | Group releases but one branch FAILS | Do not equate release with business success. |
| SG-30 | Inventory reserved, Fraud FAILS | Compensation/reservation release per policy. |
| SG-31 | Recipient List has conditional recipient | Expected subset/release logic does not hardcode two. |
| SG-32 | Fail-fast on one FAIL | In-flight branches, late replies, and side effects handled. |

### 18.1. Splitting test levels

| Level | Verifies | Does not prove on its own |
|---|---|---|
| **Branch unit test** | Inventory/Fraud logic and proper BranchReply creation. | That messages reached the gatherer. |
| **Combiner unit test** | Required IDs, duplicate, foreign, PASS/FAIL. | Gateway timeout, group persistence. |
| **Spring Integration test** | Scatterer, subscriber/recipient, correlation, release, output processor, Gateway. | Broker serialization if no broker is used. |
| **Adapter test** | Reply destination, header mapping, transport ack/retry. | All business side effects if mocked. |
| **System test** | Deadlines, failover, crash, replay, compensation, final status. | Real-world failure modes outside test scope. |

For high-reliability requirements, layers must be combined. **Combiner unit tests do not replace integration tests**; and a happy-path Gateway test is not enough to prove duplicates or timeouts are handled properly.

## 19. Troubleshooting procedure for a stuck Scatter–Gather

Suppose the Gateway hits timeout while Fraud has not been recorded. An effective investigation sequence:

1. **Input:** is the request valid, and is `requestId` truly unique for this check?
2. **Planner:** what is the expected recipient set? Were Inventory/Fraud/Compliance selected under the right policy version?
3. **Scatter:** was dispatch sent to each target channel/queue? Any rejection, full queue, or stopped endpoint?
4. **Branch started:** did the Fraud handler receive the request? Did it stall on HTTP/DB/gateway?
5. **Branch outcome:** did Fraud complete without emitting `BranchReply`, or emit a reply with the wrong schema/recipient ID?
6. **Reply transport:** did the return destination and correlation headers survive adapters? Did the reply go to a channel with no consumer?
7. **Gather:** did the reply enter the right message group, did the group already expire/release, or did duplicate/foreign checks cause policy rejection?
8. **Gateway:** did the caller reply timeout occur before or after gather? Did caller retries create new requests while the old one was still running?
9. **Recovery:** do we need to retry Fraud individually, reconcile external state, or compensate the Inventory reservation?
10. **Observability:** record the root cause, add a regression test, and consider alerts on backlog/group age.

If Inventory PASS is logged while Fraud has no `BRANCH_STARTED`, inspect scatter/dispatch and consumer readiness first before rushing to increase the Fraud HTTP timeout. If Fraud completed but gather did not see the reply, focus on return route/correlation and transport. If both replies arrived yet the group did not release, check the release strategy and message group state.

## 20. Common design mistakes

| Misconception | Consequence | Proper design |
|---|---|---|
| "Scatter–Gather is just Publish–Subscribe, just send to multiple places." | No step to collect results and make a combined decision. | Define gather/correlation/release/output contracts. |
| "Fan-out means every handler runs in parallel." | High latency when channels/handlers are synchronous. | Inspect execution model, executors, and brokers. |
| "Two replies are enough for two recipients." | Two duplicates from Inventory substitute for Fraud. | Check **unique recipientId** and expected set. |
| "If the first reply is PASS, we can Confirm." | Skips Fraud or Compliance. | Wait-for-all or approved fail-fast; never confirm with missing conditions. |
| "`group.size()==2` is always accurate." | Duplicates and foreign messages trigger wrong release. | Release by expected set and validate replies. |
| "No reply means business FAIL for the branch." | Mixes timeout/transport errors with business refusal. | Separate technical/PENDING/TIMED_OUT errors with a retry policy. |
| "`send=true` means both branches finished processing." | API declares success prematurely. | Track dispatched, accepted, completed, gathered, committed. |
| "Gateway timeout automatically cancels all workers." | Side effects continue, replies arrive late. | Explicit late reply, idempotency, and compensation handling. |
| "Having an `errorChannel` means gatherer gets an ERROR reply automatically." | Group misses reply and times out. | Error flow must return a contract-compliant result when appropriate. |
| "Using `traceId` as group ID always works." | Multiple requests in the same trace get mixed. | Use dedicated request/group ID and version when needed. |
| "When adding a recipient, only update the Scatterer." | Gatherer waits for the wrong count or releases early. | Lock expected recipients per request. |
| "Retry the whole request when only one branch times out." | Duplicates reservations, emails, or side effects. | Retry the specific recipient with idempotency/reconciliation. |
| "Group store is always durable." | State lost on restart. | Choose store/transaction/delivery semantics matching requirements. |
| "Java reply channel can be serialized to Kafka." | Consumer in another JVM has no reply destination. | Reply topic/queue and correlation header with clear mapping. |
| "Order ID is enough to correlate all replies." | Two checks for the same order get mixed. | Request ID + attempt/version per contract. |
| "Aggregator release equals business success." | All results may arrive while one branch FAILED. | Separate **completeness** from **decision status**. |
| "`@MessagingGateway` always returns an object if sent." | Timeout or missing reply; there may be no result. | Design clear timeout/error/status responses. |
| "One branch FAIL means other branches rolled back." | Partial side effects and held inventory. | Compensation or saga state when needed. |
| "Adding an arbitrary branch to the recipient list is harmless." | Data leaks to unauthorized channels. | Server-side allowlist/authorization. |
| "Message History proves every branch committed." | Lacks business outcome data. | Separate structured outcome/audit/monitoring. |

## 21. Practice exercises

1. **Basic fan-out:** use `InventoryCheck` and `FraudCheck`; send one `CheckOrderRequest`, collect two `BranchReply` messages, and produce `CombinedDecision`.
2. **Identity check:** have Inventory and Fraud both return PASS but with different `requestId` values; verify the combiner does not return CONFIRMED.
3. **Duplicate:** have Inventory reply twice while Fraud has not replied. Write a test proving the group is **not complete** just because two messages exist.
4. **Different ordering:** reverse the order of the two replies and prove the conclusion does not change.
5. **Business rejection:** have Inventory FAIL and Fraud PASS; distinguish `REJECTED` from an exception inside the handler.
6. **One-way handler:** replace the Fraud handler with a function that returns no reply. Observe the gatherer/gateway and identify why the message group does not complete.
7. **Java DSL:** configure `scatterGather` with two `recipientFlow` definitions; verify both branch replies and the output processor for one request.
8. **Dynamic Recipient List:** VN orders select two recipients, INTL orders select three. Ensure the expected set is locked per request.
9. **Release strategy:** try releasing on `group.size()==2` and create a duplicate; replace with a rule based on recipient identity and compare outcomes.
10. **Parallel execution:** put both branches onto an appropriate executor. Use latches to prove concurrent execution is possible and the Gateway still waits for both.
11. **Timeout:** have Fraud produce no reply. Test the Gateway deadline, group expiry, and verify no spurious CONFIRMED is emitted.
12. **Late reply:** Fraud replies after the deadline. Design a policy to ignore, update status, or reconcile; test that no duplicate decision is produced.
13. **Controlled retry:** make Fraud time out on the first try and PASS on the second; retry only Fraud without calling Inventory again once reserved.
14. **Compensation:** Inventory already reserved, Fraud FAILS. Build a reservation release model with idempotency and evaluate failure when compensation itself fails.
15. **Transport:** move Fraud behind a broker/HTTP. Define reply destination and correlation mapper, and test round-trip across the adapter.
16. **Two requests for the same order:** send `REQ-A` and `REQ-B` for `ORD-1`, reorder replies, and prove groups do not mix.
17. **Response schema:** have a reply carry `recipientId=inventory` but a mismatched `orderId`; add validation to prevent mis-correlation.
18. **Crash/restart:** simulate gatherer restart when only the Inventory reply has arrived; design group store/recovery per delivery contract.
19. **Observability:** add `SCATTER_PLANNED`, `BRANCH_COMPLETED`, `GATHER_RELEASED`, `GATHER_EXPIRED` logs and a per-recipient dashboard.
20. **SLO:** compare waiting at the Gateway against an API returning `202 Accepted` + status endpoint when one branch has long-running processing.

### Completion criteria

An implementation can be considered to satisfy this lesson when it:

- Has a concrete reply contract for **each recipient**.
- Defines the expected recipient set per request rather than hardcoding total message count.
- Does not merge replies from other requests/attempts or unknown recipients.
- Does not turn duplicates into proof that all branches replied.
- Distinguishes business FAIL from technical error, timeout, and missing reply.
- Has deadlines for caller and group, plus a late reply policy.
- Tracks accepted/processed/gathered rather than looking only at `send`.
- Has appropriate retry/idempotency/compensation if branches have side effects.
- Includes combiner unit tests and integration tests running through real scatter/gather.

## 22. Self-check questions

**Question 1:** A request requires Inventory and Fraud. Inventory PASSES, Fraud has no reply yet. May CONFIRMED be returned?

**No.** Under a wait-for-all contract, two valid results are required. You can return PENDING/TIMED_OUT depending on the deadline, but must not assume Fraud PASSED.

**Question 2:** Two received messages both carry `recipientId=inventory`. The Aggregator has two messages; does that mean both branches are done?

**Not yet.** This may be an Inventory duplicate; the unique recipient set is still missing Fraud.

**Question 3:** Does Scatter–Gather guarantee that both handlers run in parallel?

**No.** Concurrency depends on channels/executors/brokers and execution configuration, not solely on the pattern.

**Question 4:** How does a Fraud handler returning `BranchReply(verdict=FAIL)` differ from throwing an exception?

**FAIL** is a business result for the combiner to produce REJECTED; an exception is a technical failure and may leave no normal reply, requiring an error/recovery policy.

**Question 5:** Is `correlationId` guaranteed to always equal `requestId`?

**No.** You must inspect the correlation mechanism in the flow and mapping across adapters; `requestId` should still exist as a stable business identifier.

**Question 6:** When a client times out, is it guaranteed that Inventory has not reserved stock?

**No.** The handler may have already committed and the reply been lost/delayed. Idempotency/reconciliation is needed before retrying.

**Question 7:** If the Gateway receives both replies and one is FAIL, can the Aggregator release?

**Yes**, if the release strategy specifies two final results; however, the **decision status** must be REJECTED, not CONFIRMED.

**Question 8:** Why is retrying the entire Scatter–Gather dangerous when Fraud errors?

**Because** it may call Inventory again even if it already reserved stock or caused side effects, leading to duplicate reservations without idempotency.

**Question 9:** An INTL request additionally requires Compliance. Is the old gatherer waiting only for Inventory/Fraud still correct?

**No.** The expected set must include Compliance, otherwise it may confirm early without checking a mandatory condition.

**Question 10:** Why should `traceId` not be used as the sole group key?

**Because** multiple checks can share the same trace. A dedicated request/group ID is needed to avoid mixing replies.

**Question 11:** When Fraud returns a reply after group expiry, should a new group be opened automatically to send another conclusion to the old caller?

**Not by default.** A late-result policy, operation state, and protection against duplicate decisions are required.

**Question 12:** Does a passing `ReplyCombiner` test prove that the Scatterer and Gateway work?

**Not yet.** That is a unit test of combining logic. Integration tests are needed for routing, reply path, correlation, group release, and timeouts.

**Question 13:** Does using a broker automatically make Scatter–Gather exactly-once?

**No.** Brokers have their own delivery/ack semantics; dedupe, idempotency, durable stores, and appropriate transaction/recovery are required.

**Question 14:** When Fraud FAILS and Inventory has already reserved successfully, what may need to be done?

**Compensation**, such as releasing the reservation, if the business contract does not allow continuing to hold stock. Cases where compensation itself fails must also be managed.

## 23. Conclusion

**Scatter–Gather sends one request to multiple branches** to obtain **independent evaluations/results**, and then **gathers the matching replies** before making a conclusion. In Spring Integration, the scatterer can use Recipient List or Publish–Subscribe, while the gatherer relies on the Aggregator, correlation, release strategy, and output processor to produce the combined answer.

The decisive point is not "how many messages were sent out" but **which exact and complete results were received**. A reply set is only trustworthy when validating `requestId`, `recipientId`, expected set, duplicates, foreign replies, business status, and deadlines. For asynchronous or distributed flows, you must also handle executors/queues, multi-layer timeouts, error channels, retries, idempotency, late replies, and per-branch side effects.

In `SPRING_INTEGRATION_PATTERN`, start from the **business contract**, write unit tests for decision/reconciliation, then integration tests for Gateway → Scatter → Branch Replies → Gather. If the caller does not need to wait for results, simple Publish–Subscribe may be more suitable; if **multiple conditions are required to confirm**, Scatter–Gather is a meaningful choice. Proper design keeps message flows loosely coupled, extensible, testable, and clearly traceable when a branch encounters trouble.
