# Ensuring Priority Is Propagated Correctly in Spring Integration

## 1. The Problem: A High-Priority Message Processed Like a Normal Message

An order service receives a `PaymentRiskDetected` event over HTTP, assigns a high priority, and passes it through these steps:

~~~mermaid
flowchart LR
    A["HTTP / Gateway"] --> B["Validate and assign priority"]
    B --> C["Transformer"]
    C --> D{"Router"}
    D --> E["Splitter"]
    E --> F["Aggregator"]
    F --> G["PriorityChannel"]
    G --> H["Service Activator"]
~~~

At ingress, the system logs `priority=9`. Yet when the consumer dequeues from `PriorityChannel`, the message has the default priority, or is even missing the `priority` header. It ends up waiting behind less urgent messages.

The root cause can come from several places:

- A Transformer constructs a new `Message` and **fails to preserve** required headers.
- A Gateway passes only the payload, stripping metadata or routing into an API that drops the desired header.
- A Router sends the message through a branch/adapter that does not honor the same priority contract.
- A Splitter or Aggregator generates new messages without a priority rule for each child message or aggregated output.
- An adapter forwards the message to JMS/RabbitMQ/Kafka **without mapping** the internal header to the broker's native priority mechanism, or the broker does not support/enable priority.
- The priority value is stored in an invalid data type, overwritten by a default, or escalated arbitrarily by an untrusted source.

**Ensuring priority is propagated correctly** is more than “setting `priority` on a message”. It is an **end-to-end metadata contract**: defining values, origin, transformations, traversal across EIPs and adapters, test criteria, and verification right at the point where messages are selected for processing.

In the `SPRING_INTEGRATION_PATTERN` module, this discipline allows Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation to stay loosely coupled while preserving **business prioritization intent**.

### Learning Objectives

After this lesson, you will be able to:

1. Standardize the `priority` header and distinguish **business priority** from **broker priority**.
2. Verify header preservation when building new `Message`s, transforming, splitting, aggregating, routing, or calling Gateways.
3. Design explicit priority mappers at HTTP, JMS, RabbitMQ, and Kafka boundaries.
4. Prevent unauthorized clients from assigning HIGH or passing malformed values.
5. Write unit/integration tests verifying priority **at every boundary**, not just at the producer.
6. Monitor cases where priority is lost, downgraded, escalated, or misinterpreted in operations.

## 2. What Conditions Define “Correct Priority”?

| Requirement | Verification question |
| --- | --- |
| **Value** | Is priority an integer, enum, or explicit numeric range? |
| **Semantics** | Does a larger number mean higher importance? |
| **Trusted source** | Who is authorized to classify HIGH, NORMAL, LOW? |
| **Continuity** | When a message is rebuilt, is priority ever dropped or overwritten? |
| **Branching rules** | How do child messages or aggregated results inherit, lower, or raise priority? |
| **Adapter compatibility** | Is the Spring header mapped to the property/metadata used by the target? |
| **Observability** | Is priority verified before and after every major boundary? |
| **Business correctness** | Does priority starve low-priority work or allow unauthorized callers to hog workers? |

A clean design defines two concepts:

- **`businessPriority`**: the decision made by the domain, such as `HIGH`, `NORMAL`, `LOW`; can live in canonical payload/metadata.
- **`priority`**: the numeric value used by a scheduler, `PriorityChannel`, or specific adapter; usually derived from business priority.

If a producer emits `businessPriority=HIGH` while the target adapter only understands numeric `priority`, define an explicit mapping, assert the output, and never assume the adapter understands domain enums automatically.

## 3. The `priority` Header in Spring Messaging

In Spring Integration, a `Message<T>` consists of:

~~~text
Message
  ├─ payload: business content
  └─ headers:
       id, timestamp,
       priority,
       correlationId, sequenceNumber,
       businessEventId, ...
~~~

The header used for priority is conventionally named **`priority`**. With `PriorityChannel`, message selection order relies on the message's priority header (or a configured comparator); higher values normally go first by default.

Define the contract in application code:

~~~java
final class PriorityHeaders {
    private PriorityHeaders() {}

    static final String PRIORITY = "priority";
    static final String ORIGINAL_PRIORITY = "originalPriority";
    static final String PRIORITY_SOURCE = "prioritySource";
    static final String BUSINESS_EVENT_ID = "businessEventId";
}

enum WorkClass {
    HIGH, NORMAL, LOW
}

record WorkCommand(String eventId, String type) {}

static int toPriority(WorkClass type) {
    return switch (type) {
        case HIGH -> 9;
        case NORMAL -> 5;
        case LOW -> 1;
    };
}
~~~

Levels 9–5–1 are an **illustrative application policy**, not a mandatory Spring Integration scale. If a target uses a 0–9 range like JMS, define a mapping; never assign a value like 100 assuming every target preserves it unchanged.

### Attaching Priority When Creating a Message

~~~java
Message<WorkCommand> message = MessageBuilder
        .withPayload(new WorkCommand("E-17", "PAYMENT_RISK"))
        .setHeader(PriorityHeaders.PRIORITY, 9)
        .setHeader(PriorityHeaders.ORIGINAL_PRIORITY, 9)
        .setHeader(PriorityHeaders.PRIORITY_SOURCE, "business-policy-v1")
        .setHeader(PriorityHeaders.BUSINESS_EVENT_ID, "E-17")
        .build();
~~~

In this example, `WorkCommand` is a project-defined business payload type. The `businessEventId` header must remain **stable** across retries/redeliveries; never use a message instance's `MessageHeaders.ID` as a unique business identifier.

### Data Type Rules

A solid contract specifies:

- `priority` is an **`Integer`** (or numeric type actually supported across all endpoints), within the application's allowed range.
- **Higher values** mean higher priority on the chosen channel.
- Missing or wrongly typed values are **rejected or defaulted under strict control**, never silently escalated to HIGH.
- `originalPriority` is retained for auditing during aging or escalation; it is not a header `PriorityChannel` natively interprets.
- Every `priority` change should carry provenance, such as `prioritySource` or `priorityPolicyVersion`.

Note: `MessageHeaders.ID` and `MessageHeaders.TIMESTAMP` are special metadata typically regenerated by the framework whenever a new message is built. Copying headers does not guarantee preserving those two fields, nor do they substitute for a business event ID.

## 4. Knowing the Boundaries: Preserving a Header Does Not Equal Ordered Execution

~~~mermaid
flowchart TD
    A["Message with priority=9"] --> B{"Which component does it cross?"}
    B --> C["DirectChannel"]
    B --> D["PriorityChannel"]
    B --> E["ExecutorChannel"]
    B --> F["Broker adapter"]
    C --> G["Synchronous dispatch; no automatic reordering"]
    D --> H["Dequeued by priority/comparator"]
    E --> I["Executor handoff; thread pool's own scheduling"]
    F --> J["Requires mapping + broker support"]
~~~

| Component | If header remains `priority=9` | Does it guarantee “runs first”? |
| --- | --- | --- |
| `DirectChannel` | Header reaches the handler unless altered. | No: synchronous handoff, not a priority queue. |
| `ExecutorChannel` | Header can reach the worker. | No: executor scheduling depends on pool state and task submission order. |
| `QueueChannel` FIFO | Header is stored with the message. | No: standard FIFO dequeuing ignores the priority header. |
| `PriorityChannel` | Header is read by priority/comparator logic. | Orders **waiting** messages per policy; never preempts running tasks. |
| `PublishSubscribeChannel` | Subscribers can inspect the header. | No: subscribers do not automatically become priority schedulers. |
| External broker | Header must map properly for broker/consumer use. | Depends on broker support, queue/topic config, and consumers. |

For example: a consumer has already picked up a LOW message running for 30 seconds. Then a HIGH message enters `PriorityChannel`. HIGH can only be prioritized **relative to other messages still waiting in the queue** on the next poll; it cannot interrupt the running LOW handler.

## 5. Transformer: The Most Common Source of Lost Priority

A Transformer can return either a **payload** or a complete **`Message`**. When returning a payload, Spring Integration forwards request headers across many endpoint types. However, when a Transformer builds a response `Message` manually, applies header filtering/overwrites, or goes through a custom adapter, **do not take preserving every header for granted**.

### Easy Mistake: Building a New Message with Payload Only

~~~java
// Anti-pattern: only call this helper directly; do not register alongside
// the proper Transformer on the same inputChannel.
public Message<NormalizedCommand> transformBad(
        Message<RawCommand> incoming) {

    NormalizedCommand payload = normalize(incoming.getPayload());

    // Accidentally drops all business headers when building a fresh Message.
    return MessageBuilder.withPayload(payload).build();
}
~~~

When calling this helper directly, the inbound `priority=9` is lost along with `businessEventId` and downstream-required headers. Some Transformer endpoints copy/merge request headers and may preserve certain headers even when the processor returns a `Message`; therefore **test the actual output of your exact version and configuration**, rather than judging from a single `MessageBuilder` line. Still, whenever constructing a `Message` explicitly, state your header preservation/override policy clearly in code.

### Explicit Approach: Intentional Copying and Re-Validation

Example payload types and simple normalization logic (placed in appropriate application classes):

~~~java
record RawCommand(String orderId, String type) {}
record NormalizedCommand(String orderId, String action) {}

static NormalizedCommand normalize(RawCommand raw) {
    return new NormalizedCommand(
            raw.orderId(),
            raw.type().trim().toUpperCase(Locale.ROOT));
}
~~~

~~~java
@Transformer(inputChannel = "rawCommands",
             outputChannel = "normalizedCommands")
public Message<NormalizedCommand> normalizeAndPreserve(
        Message<RawCommand> incoming) {

    NormalizedCommand payload = normalize(incoming.getPayload());
    int priority = requirePriority(incoming.getHeaders());

    return MessageBuilder.withPayload(payload)
            .copyHeaders(incoming.getHeaders())
            .setHeader(PriorityHeaders.PRIORITY, priority)
            .build();
}

private static int requirePriority(MessageHeaders headers) {
    Object raw = headers.get(PriorityHeaders.PRIORITY);
    if (!(raw instanceof Integer priority)
            || priority < 0 || priority > 9) {
        throw new IllegalArgumentException(
                "priority must be an integer between 0 and 9");
    }
    return priority;
}
~~~

Here `copyHeaders(...)` works well to illustrate an **internal flow** already carrying trusted metadata. **Never blindly copy all headers out to HTTP/JMS/Kafka**: headers can contain reply channel objects, error channels, internal context, or non-serializable types. At external boundaries, use an explicit **allowlist** of exportable headers.

### Why Re-Validate After a Transformer?

A Transformer might:

- Change the payload while needing to preserve priority.
- Split one command into another command with its own importance.
- Receive a header as `String` ("9") while downstream expects `Integer`.
- Use `MessageBuilder` and then call `setHeader("priority", null)` or overwrite it from an untrusted property.

If it is a normalizing Transformer, the contract should be “**output priority equals policy-verified priority**”, not “copy whatever existed at the source if present”.

## 6. Header Enricher: Applying Policy at One Clear Point

Spring Integration offers **Header Enricher** to attach or update message metadata without mixing header logic into every business handler.

Concept:

~~~text
Inbound raw message
  -> validate trusted fields
  -> classify(WorkClass)
  -> Header Enricher (priority = 9/5/1)
  -> Transformer / Filter / Router
  -> priority-aware destination
~~~

Illustrative Java DSL example:

~~~java
@Bean
IntegrationFlow inboundPriorityFlow() {
    return IntegrationFlow.from("classifiedInput")
            .enrichHeaders(headers -> headers
                    .headerFunction("priority",
                            message -> priorityFromTrustedPayload(
                                    message.getPayload())))
            .channel("priorityReady")
            .get();
}
~~~

`priorityFromTrustedPayload(...)` is application-defined and returns a policy-valid numeric value. Across Spring Integration versions, check the exact `HeaderEnricherSpec` DSL signature in your version. What matters is **classifying from validated data**, never copying unverified priority values straight from clients.

### Assign Once or Recompute Multiple Times?

- **Assign at ingress**: convenient once the message is classified and every downstream step shares one contract.
- **Verify at boundaries**: after crossing external adapters, deserialization, splitting/aggregating, or domain transitions, re-verify the value.
- **Recompute at Router**: only if policy dictates priority depends on the branch. Otherwise, routing should not alter priority.
- **Map before broker**: if the broker uses a different numeric range, map explicitly and log both before and after values.

A useful rule: **every place permitted to alter priority must declare its reason, mapping function, and test suite**.

## 7. Router and Filter: Steering Paths Without Losing Metadata

### Router

Router chooses a destination based on payload or headers. Merely choosing a channel **does not require changing priority**; however, a branch passing through a specialized adapter can drop or reinterpret metadata.

~~~mermaid
flowchart LR
    A["Message priority=9"] --> B{"Router"}
    B --> H["urgentInput"]
    B --> N["normalInput"]
    H --> C["Urgent Transformer"]
    N --> D["Normal Transformer"]
    C --> E["PriorityChannel"]
    D --> E
    E --> F["Handler"]
~~~

Verify the same contract at convergence points: messages from **both branches** must carry properly typed, accurate priority. One branch's Transformer building a new `Message` may lose metadata while the other branch keeps it.

### Filter

`Filter` decides whether a message continues. If Filter drops a message, no “propagated priority” appears on the success branch. Therefore:

- Do not mistake an empty `PriorityChannel` for lost priority; the message may have been filtered out.
- Emit separate metrics for `filtered_total{class}` and `priority_missing_total`.
- If filtered messages route to a discard channel, check the priority of messages sent to the discard/error path.
- If policy forbids dropping a HIGH message, Filter must encode explicit domain rules rather than merely prioritizing HIGH handling.

High priority **does not exempt messages from validation or authorization**. A HIGH message with a broken schema must still be rejected or quarantined per policy.

## 8. Splitter: Should Child Messages Inherit or Recompute Priority?

Suppose an `OrderConfirmed` event has 20 line items. A Splitter breaks it into a `ReserveItem` per SKU. There are at least three policies:

| Policy | Meaning | When appropriate |
| --- | --- | --- |
| **Inherit** | All child messages use the parent message's priority. | The whole order shares one urgency level. |
| **Derive** | Compute per-item priority from trusted item attributes. | One item has special handling or its own incident SLA. |
| **Cap/escalate** | Keep within bounds, raising/lowering per item deadline. | Distinct SLAs exist; log reason for adjustment. |

Example splitting logic at the application layer:

~~~java
static Message<ReserveItem> childMessage(
        Message<OrderCommand> parent,
        ReserveItem item) {

    int parentPriority = requirePriority(parent.getHeaders());
    int childPriority = item.isPerishable()
            ? Math.max(parentPriority, 7)
            : parentPriority;

    return MessageBuilder.withPayload(item)
            .setHeader(PriorityHeaders.PRIORITY, childPriority)
            .setHeader(PriorityHeaders.ORIGINAL_PRIORITY, parentPriority)
            .setHeader(PriorityHeaders.BUSINESS_EVENT_ID,
                    parent.getHeaders()
                            .get(PriorityHeaders.BUSINESS_EVENT_ID))
            .setHeader("parentOrderId", parent.getPayload().orderId())
            .build();
}
~~~

`ReserveItem`, `OrderCommand`, and `isPerishable()` are illustrative domain types/methods. When using Spring Integration's **Splitter endpoint**, the framework also attaches correlation and sequence headers so an **Aggregator** can reassemble results. **Do not build custom child messages that accidentally strip `correlationId`, `sequenceNumber`, or metadata needed by the Aggregator.** When managing messages manually, verify whether the framework adds correlation/sequence on output.

### Never Generate a Fresh Event ID for Every Retry of the Same Child Message

When spawning multiple child messages, assign each subtask its own deterministic key, for example:

~~~text
parentEventId = ORD-17
childBusinessId = ORD-17:SKU-A
childBusinessId = ORD-17:SKU-B
~~~

When retrying `ORD-17:SKU-A`, keep `childBusinessId` unchanged for deduplication. `MessageHeaders.ID` can change whenever a `Message` is rebuilt; do not use it as a business key.

## 9. Aggregator: Output Priority Must Have an Explicit Policy

An Aggregator collects multiple messages, stores correlation state, and emits an aggregated message once the release condition is met. An output may be formed from messages with differing priorities:

~~~text
Item A: priority=9
Item B: priority=5
Item C: priority=1
             |
          Aggregator
             |
       BatchResult: priority=?
~~~

Never rely on a header accidentally copied from the first, last, or arbitrary arriving message. **Output priority must be an explicit domain decision.**

Common policies:

- **MAX**: output equals the highest priority in the group; makes sense when one urgent item makes the whole batch urgent.
- **MIN**: output equals the lowest; fits when all items must meet a standard before proceeding, though it easily stalls important batches.
- **Weighted aggregation**: output depends on ratios, risk levels, or group deadlines.
- **Fixed parent priority**: output retains the original workflow priority regardless of child variations.

Example implementing MAX:

~~~java
static int aggregatePriority(List<Message<?>> parts) {
    return parts.stream()
            .mapToInt(message -> requirePriority(message.getHeaders()))
            .max()
            .orElseThrow(() -> new IllegalArgumentException(
                    "Cannot aggregate empty group"));
}

static Message<BatchResult> aggregateResult(
        List<Message<?>> parts,
        BatchResult payload,
        String correlationId) {

    int priority = aggregatePriority(parts);
    return MessageBuilder.withPayload(payload)
            .setHeader(PriorityHeaders.PRIORITY, priority)
            .setHeader("correlationId", correlationId)
            .build();
}
~~~

This is business logic used when building aggregator output; `@Aggregator`/Java DSL configuration and correlation group handling depend on your actual flow structure. Ensure `correlationId` is not unintentionally altered, and assert output priority **after Aggregator release**.

### Timeouts, Partial Releases, and Late Messages

If an Aggregator releases on timeout before all child messages arrive:

- The priority policy must apply to **the messages that actually arrived**, or use the durably stored parent priority.
- Late-arriving messages may start a new group or be discarded depending on configuration; avoid accidentally escalating an already completed workflow.
- Duplicate messages from redelivery can skew group counts or priority; pair with proper deduplication and release strategy.

An Aggregator backed by a persistent message store also **does not automatically guarantee** every custom header survives serialization/restart; test with your actual message types and converter/store.

## 10. Gateway and Request–Reply: Two Separate Metadata Directions

A Gateway bridges method calls and message flows. Distinguish:

1. **Request priority**: priority as the request enters the flow.
2. **Reply priority**: priority of the response once the flow finishes processing.

There is no general reason why a reply must share the request's priority. For example, returning a result to a user may follow its own policy, whereas an internal reply merely completes correlation.

### Typed Gateway Passing a Message with Explicit Headers

~~~java
@MessagingGateway(defaultRequestChannel = "commandInput")
interface CommandGateway {
    void submit(Message<WorkCommand> command);
}
~~~

The caller constructs the message explicitly:

~~~java
gateway.submit(MessageBuilder
        .withPayload(new WorkCommand("E-17", "PAYMENT_RISK"))
        .setHeader(PriorityHeaders.PRIORITY, 9)
        .setHeader(PriorityHeaders.BUSINESS_EVENT_ID, "E-17")
        .build());
~~~

The verification point is the message received at `commandInput`, not merely the caller's method arguments.

If the Gateway only accepts payload `submit(WorkCommand command)`, metadata must be **derived or enriched** via method mapping/annotations/ingress policy. Never expect priority to materialize when the payload omits it and the caller supplies no headers.

### Reply and Error Channel Headers

Spring Integration uses internal headers such as reply channel and error channel to coordinate request–reply, timeouts, and errors. When building a new message:

- Preserve headers needed for the **request–reply protocol** when the same flow relies on it.
- Do not export headers holding internal channel objects over brokers/HTTP indiscriminately.
- Do not let a custom `priority` header overwrite or break reply-routing contracts.
- Across an async boundary, a reply may arrive after the Gateway has already timed out; high priority on the reply does not un-timeout the caller.

## 11. Mapping Priority Over HTTP: Trust Must Come First

HTTP has no universal priority queuing mechanism replacing `PriorityChannel`. You can convey priority via an **application header** or JSON field, but the receiver must map it explicitly.

Example upstream request:

~~~http
POST /api/work
Content-Type: application/json
X-Work-Priority: HIGH
X-Event-Id: E-17

{"type":"PAYMENT_RISK","orderId":"ORD-17"}
~~~

This is an application-specific contract, not an automatic Spring Integration feature. The receiving system:

1. Authenticates the source and checks permission to assign HIGH.
2. Validates the header or payload; rejects any value outside the allowed set.
3. If only trusted clients may specify it, maps HIGH → 9; otherwise classifies via server-side rules.
4. Sets `priority=9` on the internal message.
5. Logs/traces `prioritySource=trusted-api-v1` and the event ID.

### Why Not Pass Raw Client Headers Through?

If an Internet client can send `X-Work-Priority: HIGH` and be treated as HIGH, a single actor can monopolize workers with ordinary requests. Priority is **resource allocation authority**, not harmless metadata.

For service-to-service calls:

- Use service-identity authentication/authorization.
- Maintain an allowlist of escalation permissions per endpoint/event type.
- Apply rate limits and quotas per tenant or caller.
- Never allow retries of LOW work to escalate indefinitely to HIGH.
- Behind proxies/load balancers, verify headers are preserved rather than renamed, re-cased, or multi-valued.

## 12. Mapping Priority Over JMS

JMS has a standard **message priority** in `JMSPriority`, typically ranging **0–9**, with a default producer priority of **4** unless overridden. This is a JMS message property, **different** from a Spring message merely carrying a custom `priority` header.

~~~text
Spring message:
  headers["priority"] = 9
        |
        | JMS outbound adapter / header mapping / producer QoS
        v
JMS message:
  JMSPriority = 9
        |
      JMS broker
~~~

To ensure proper mapping, verify the **exact adapter, header mapper, and producer configuration** in your version:

- Is Spring's priority mapped to actual JMS priority?
- Does the adapter have QoS / explicit QoS enabled or a default producer setting overriding it?
- Does the broker/destination actually honor priority, and how does ordering behave under competing consumers?
- On inbound receipt, is `JMSPriority` mapped back to `priority` per internal contract?

**Never only assert `message.getHeaders().get("priority") == 9` before the JMS outbound adapter.** That proves Spring-side metadata, **not** that the real JMS message carries `JMSPriority=9`.

### End-to-End JMS Test

1. Publish messages with levels `9` and `1` through the real adapter.
2. Use a JMS consumer/probe to read `JMSPriority` off the raw message.
3. Use the Spring Integration JMS inbound adapter to check the priority value entering the flow.
4. When testing ordering, keep consumers stopped until messages are enqueued; if HIGH arrives after LOW has already been delivered, the broker cannot “recall” LOW from a consumer.

Ordering outcomes still depend on broker implementation and consumer concurrency; **accurate priority metadata propagation** and **broker priority scheduling** are two separate tests.

## 13. Mapping Priority Over RabbitMQ / AMQP

In AMQP 0-9-1, messages have **`BasicProperties.priority`**. RabbitMQ supports priority ordering when **the queue is configured to support priorities**, typically via the `x-max-priority` argument at queue declaration time.

~~~text
Spring Message priority=9
  -> outbound adapter mapping
  -> AMQP BasicProperties.priority=9
  -> RabbitMQ queue declared with x-max-priority
  -> broker selects waiting messages by priority
~~~

If the adapter only sends a **custom application header** named `priority` without setting `BasicProperties.priority`, RabbitMQ will not use it for delivery ordering.

AMQP checklist:

| Verification point | Consequence if missing |
| --- | --- |
| Value mapped into `BasicProperties.priority`. | Broker treats all messages as equal priority. |
| Queue declared with priority support. | Messages carry the property, yet the queue does not reorder by priority. |
| Priority range valid and consistent with queue. | High values get capped/normalized unexpectedly. |
| Prefetch and consumer concurrency properly tuned. | LOW messages already prefetched before HIGH arrives still process first. |
| Retry/requeue preserves business priority. | Requeued messages lose or escalate priority. |

A practical reality to remember: **broker message priority only applies to work not yet dispatched to a consumer**. High consumer prefetch pulls many LOW messages off the broker queue into consumer memory; newly arrived HIGH messages cannot take slots ahead of tasks already buffered inside a consumer.

Do not alter `x-max-priority` on an existing queue expecting the broker to apply it immediately: depending on queue declaration rules, changing arguments may require controlled migration/redeclaration.

## 14. Kafka: No Built-In Per-Record Broker Priority Queue

Kafka stores records by **partition and offset**. Kafka records have headers, yet application headers like `priority=9` **do not cause Kafka to reorder records by priority** within a partition.

Thus there are two separate goals:

- **Carrying priority across Kafka**: encode into a record header or payload, and have the inbound mapper decode it to reconstruct the Spring message accurately.
- **Executing priority scheduling**: separate topics/partitions/consumer pools with quotas, use a dispatcher after consumption, or design work selection at the application tier.

### Example Contract Over Kafka

~~~text
Producer:
  businessEventId = E-17
  priority = 9
  topic = work-events

Kafka record:
  key = ORD-17
  headers["work-priority"] = bytes("9")
  value = serialized WorkCommand

Consumer:
  decode bytes("9") -> Integer(9)
  validate domain policy
  Spring Message headers["priority"] = 9
~~~

This example illustrates only the **wire contract**. Spring Kafka / Spring Integration Kafka adapters differ in header mappers and serializers across versions and configurations. Never assume `Integer` survives binary header transport without verifying the codec. For critical events, maintain encode/decode and versioning contract tests.

### How Should Ordering Be Handled?

| Requirement | Viable design |
| --- | --- |
| Preserve ordering per `orderId` | Use a consistent key/partition strategy; do not arbitrarily reorder records of the same aggregate if domain logic relies on order. |
| HIGH needs dedicated capacity | Split topics or consumer groups/worker pools with per-class quotas. |
| Priority must govern dequeue | Consume into a durable application work scheduler with explicit policy and proper offset/ACK handling. |
| Both preserve ordering and prioritize HIGH | Evaluate trade-offs: reordering within the same aggregate can violate business causality. |

**Do not equate a Kafka record header `priority` with broker-side priority scheduling.** Keeping the header intact is only half the requirement.

## 15. Header Mapping: Never Blindly Copy Across Process Boundaries

Within an internal flow, `copyHeaders` preserves metadata. When crossing to external systems, use an explicit **allowlist** and a versioned schema.

Example outbound contract:

~~~text
Required:
  businessEventId     : string
  workPriority        : integer 0..9
  priorityPolicyVersion: string

Optional:
  correlationId       : string
  originalPriority    : integer 0..9
  deadlineEpochMillis : long

Do not export:
  replyChannel object
  errorChannel object
  internal authentication context
  Java class instances not supported by wire serializer
~~~

When sending through a broker:

1. Map canonical priority → appropriate protocol property (JMS priority, AMQP property, Kafka header).
2. Serialize types per wire contract; never assume Java objects survive intact.
3. Record metadata at the source of truth; if auditing is needed, store `prioritySource` and policy version.
4. Inbound, validate/decode and construct a fresh `Message` with normalized `priority`.
5. Never let external broker users escalate priority beyond policy even if the header decodes cleanly.

Some mappers drop headers or rename keys. Testing only with a publisher and consumer sharing an in-memory channel **does not test the wire boundary**.

## 16. Time-Varying Priority: Distinguishing Original and Effective

To prevent starvation, systems may use aging or deadline escalation. When doing so, maintain **two values**:

- `originalPriority`: level assigned by business policy at ingress.
- `priority` or `effectivePriority`: level used by the scheduler **at decision time**.

Example:

~~~text
T0: originalPriority=1, effectivePriority=1
T+30s: effectivePriority=5 (aging policy)
T+60s: effectivePriority=9 (deadline escalation)
~~~

Do not **overwrite `originalPriority`** and lose history. When forwarding to another broker, decide explicitly what gets transmitted: original, effective, or both. During retries:

- Keep `businessEventId` stable.
- Keep `originalEnqueueTime` so wait age is never reset.
- Whenever priority is raised, log the reason and policy version.
- Cap escalation so a retry storm cannot turn every failing LOW message into HIGH.

### Do Not Expect a Clock-Reading Comparator to Re-Order a Heap

A heap-backed `PriorityChannel` or priority queue does not automatically re-sort all elements simply because `System.currentTimeMillis()` increases. True aging requires **promotion/requeue/rebuild or a scheduler** that re-evaluates age when selecting messages. This is a scheduling problem that accurate header propagation alone cannot solve.

## 17. Retry, Redelivery, and Error Channel: Does Priority Travel with Errors?

When a handler throws an exception, the error may:

- Propagate back to caller/poller and trigger rollback.
- Be wrapped in an `ErrorMessage` sent to `errorChannel`.
- Be routed to a retry queue/DLQ.
- Be redelivered by the broker according to ACK/offset policy.

On every path, verify **which metadata is preserved**. An `ErrorMessage` has an exception as its payload, not the original business payload; reading `errorMessage.getHeaders().get("priority")` does not automatically match the failed message's priority. Depending on the exception, source, and error handler, you may need to extract the original failed message from `MessagingException` and normalize metadata for DLQ/retry.

### Recommended Retry Rules

| Item | Policy |
| --- | --- |
| Business event ID | Preserved across every attempt. |
| Original priority | Preserved for auditing and policy restoration. |
| Effective priority | May adjust per retry/age, strictly under a defined policy. |
| Attempt count | Incremented per attempt, persisted durably if needed. |
| Error reason | Distinguish transient vs. permanent errors. |
| DLQ | Retain event ID, priority source, error context, and sanitized payload. |
| ACK/offset | Finish delivery per contract only once side effects or durable handoff succeed. |

### Common Bug: Retries Unintentionally Receive a Default Priority

~~~java
Message<WorkCommand> retry = MessageBuilder
        .withPayload(failedMessage.getPayload())
        .build();
~~~

This snippet drops both the priority contract and business event ID. If a retry adapter emits this new message and consumers receive missing metadata, it can fall back to default priority or cause hard-to-control duplicates.

At the retry boundary, rebuild the message from **validated canonical fields**, for example:

~~~java
Message<WorkCommand> retry = MessageBuilder
        .withPayload(failedMessage.getPayload())
        .setHeader(PriorityHeaders.PRIORITY,
                requirePriority(failedMessage.getHeaders()))
        .setHeader(PriorityHeaders.BUSINESS_EVENT_ID,
                failedMessage.getHeaders()
                        .get(PriorityHeaders.BUSINESS_EVENT_ID))
        .setHeader("attempt",
                ((Number) failedMessage.getHeaders()
                        .getOrDefault("attempt", 0)).intValue() + 1)
        .build();
~~~

This illustrates rebuilding metadata in an **internal processing path**; with a real broker, handle serialization, ACKs, and prevent infinite retry loops. Never let a poison HIGH message consume all slots; pair bounded retries, backoff, and DLQ with fairness.

## 18. Example Internal Flow Verifying Priority End-to-End

The following minimal pattern keeps scope tight: assign priority explicitly at ingress, have the Transformer intentionally preserve metadata, then send into `PriorityChannel`. A poller processes in channel order.

~~~mermaid
flowchart LR
    A["Request -> priorityAssigned"] --> B["Normalize + validate headers"]
    B --> C["PriorityChannel"]
    C --> D["Poller"]
    D --> E["Service Activator"]
    E --> F["Business DB / metrics"]
~~~

Java configuration:

~~~java
@Configuration
@EnableIntegration
class PriorityFlowConfig {

    @Bean("priorityReady")
    MessageChannel priorityReady() {
        return new DirectChannel();
    }

    @Bean("pendingPriority")
    PollableChannel pendingPriority() {
        return new PriorityChannel(200);
    }

    @Bean
    IntegrationFlow enqueuePriorityFlow() {
        return IntegrationFlow.from("priorityReady")
                .channel("pendingPriority")
                .get();
    }

    @Bean
    IntegrationFlow consumePriorityFlow(PriorityWorkHandler handler) {
        return IntegrationFlow.from(
                        "pendingPriority",
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(200)
                                        .maxMessagesPerPoll(1)))
                .handle(handler, "handle")
                .get();
    }
}
~~~

Service Activator:

~~~java
@Service
class PriorityWorkHandler {
    public void handle(Message<WorkCommand> message) {
        int priority = requirePriority(message.getHeaders());
        String eventId = String.valueOf(
                message.getHeaders().get(
                        PriorityHeaders.BUSINESS_EVENT_ID));

        // Execute business logic and record metrics by priority/eventId.
        // Apply separate idempotency + transaction for critical side effects.
    }
}
~~~

The snippet wires `MessageChannel` and `PollableChannel` by bean name in DSL. `PriorityWorkHandler` invokes the validation helper from Section 5 (placed in a shared class in practice). This is an **illustrative in-memory queue**, not a configuration guaranteeing zero message loss on process crash.

### Limitations to State Clearly

- `PriorityChannel` chooses among **unconsumed** waiting messages; it never cancels a running handler.
- Ordering across equal-priority messages may require a dedicated tie-breaker.
- Pollers may run concurrently or across multiple instances in production, making **completion** order differ from dequeue order.
- Preserving headers alone does **not** prevent priority starvation under continuous HIGH arrivals.
- When durable messaging and redelivery are required, choose a supporting store/broker and verify transaction boundaries, ACKs, idempotency, and metadata schemas.

## 19. Testing the Contract at Every Boundary

A thorough test suite checks **before/after Transformer**, **after Router**, **after Splitter/Aggregator**, **before/after wire adapters**, and **at the consumer**.

### Test 1 — Transformer Preserves Priority When Changing Payload

~~~java
@Test
void transformerPreservesTrustedPriority() {
    RawCommand raw = new RawCommand("ORD-17", "PAYMENT_RISK");
    Message<RawCommand> input = MessageBuilder.withPayload(raw)
            .setHeader(PriorityHeaders.PRIORITY, 9)
            .setHeader(PriorityHeaders.BUSINESS_EVENT_ID, "E-17")
            .build();

    Message<NormalizedCommand> output =
            transformer.normalizeAndPreserve(input);

    assertEquals(9,
            output.getHeaders().get(PriorityHeaders.PRIORITY));
    assertEquals("E-17",
            output.getHeaders().get(PriorityHeaders.BUSINESS_EVENT_ID));
    assertEquals("ORD-17", output.getPayload().orderId());
    assertEquals("PAYMENT_RISK", output.getPayload().action());
}
~~~

The test above assumes using `RawCommand`, `NormalizedCommand`, and the Transformer bean from Section 5. **Direct method** unit tests confirm code policy, yet you also need **endpoint integration tests** to verify how Spring Integration actually copies/merges reply headers.

### Test 2 — PriorityChannel Dequeues Higher Messages First

~~~java
@Test
void priorityChannelReceivesHigherPriorityFirst() {
    PriorityChannel channel = new PriorityChannel(20);
    channel.send(MessageBuilder.withPayload("LOW")
            .setHeader("priority", 1).build());
    channel.send(MessageBuilder.withPayload("HIGH")
            .setHeader("priority", 9).build());

    assertEquals("HIGH", channel.receive(0).getPayload());
    assertEquals("LOW", channel.receive(0).getPayload());
}
~~~

Note that this test must enqueue **both messages before calling receive**. If LOW is already picked up by a consumer before HIGH is sent, priority cannot reverse an already-started delivery.

### Test 3 — Reject Wrong Types and Out-of-Range Values

~~~java
@Test
void rejectsInvalidPriorityInsteadOfSilentlyEscalating() {
    Message<String> invalid = MessageBuilder.withPayload("WORK")
            .setHeader("priority", "9")
            .build();

    assertThrows(IllegalArgumentException.class,
            () -> requirePriority(invalid.getHeaders()));
}
~~~

If HTTP/JMS/Kafka adapters convert priority from strings/bytes to numbers, test the **decoder** separately so the result is `Integer(9)` before entering `PriorityChannel`.

### Test 4 — Aggregator Applies MAX Policy

~~~java
@Test
void aggregateUsesHighestPriorityOfChildren() {
    List<Message<?>> parts = List.of(
            MessageBuilder.withPayload("A")
                    .setHeader("priority", 1).build(),
            MessageBuilder.withPayload("B")
                    .setHeader("priority", 9).build(),
            MessageBuilder.withPayload("C")
                    .setHeader("priority", 5).build());

    assertEquals(9, aggregatePriority(parts));
}
~~~

### Test 5 — Header Mappers Against a Real Broker

| Boundary | Output verification |
| --- | --- |
| HTTP ingress | Priority from untrusted sources is validated/re-classified. |
| Transformer | `priority` is preserved/transformed per policy alongside `businessEventId`. |
| Router/Filter | Both success and discard/error paths retain contract metadata. |
| Splitter | Child priority follows inherit/derive; correlation/sequence remain intact. |
| Aggregator | Output priority follows MAX/parent/deadline, never randomly the last message. |
| Gateway | Request priority reaches target channel; reply priority has its own policy if needed. |
| JMS outbound | Real JMS message carries expected `JMSPriority`. |
| RabbitMQ outbound | `BasicProperties.priority` is set; queue supports priority. |
| Kafka | Priority encodes/decodes accurately; never claim Kafka reorders by header. |
| Retry/DLQ | Event ID, original/effective priority, attempt, and error reason survive replay. |

Broker tests should use Testcontainers or a suitable staging broker when thoroughly verifying real adapters. Never run a single “header propagation test” and assume broker scheduling and business commits both work.

## 20. Operational Observability: Pinpointing Where Priority Changes

Track three checkpoints:

1. **Assigned**: priority after policy validation at ingress.
2. **Enqueued**: priority right before the queue/broker.
3. **Consumed**: priority actually received and acted upon by the handler.

For each message, traces can record:

~~~text
eventId = E-17
correlationId = ORD-17
assignedPriority = 9
enqueuedPriority = 9
consumedPriority = 9
prioritySource = business-policy-v1
destination = pendingPriority
adapter = local-priority-channel
~~~

Metrics:

| Metric | Meaning |
| --- | --- |
| `priority_missing_total{endpoint}` | Messages reaching an endpoint without the contract header. |
| `priority_invalid_total{endpoint}` | Wrongly typed, out-of-range, or unauthorized header. |
| `priority_changed_total{from,to,reason}` | Tracks legitimate or anomalous priority changes. |
| `priority_mismatch_total{boundary}` | Wire/consumer priority differs from validated priority outside policy. |
| `queue_depth{priority}` | Pending messages per level, showing workload shape. |
| `oldest_pending_age_seconds{priority}` | Detects starvation even when priority propagates intact. |
| `retries_total{priority}` | Failures/retries shifting traffic across priority levels. |
| `processed_total{priority}` | Actual completed throughput per level, not just enqueues. |

In tracing, add normalized metadata to spans/logs **after filtering sensitive data**. Avoid logging raw payloads, tokens, full HTTP headers, or unnecessary PII.

### Debugging a Delayed HIGH Message

Trace starting from `eventId`:

~~~text
1. Did policy classify it as HIGH?
2. Was the Spring header Integer(9) right after ingress?
3. Did any Transformer construct a new Message or overwrite headers?
4. Did the Router direct it to the right destination?
5. Did Splitter/Aggregator apply the output policy?
6. Did the outbound adapter map the right broker property?
7. Does the target queue/topic support priority scheduling?
8. Were LOW messages already prefetched/running before HIGH arrived?
9. Did the consumer read the right priority while HIGH backlog itself was huge?
10. Are there retries, timeouts, DB locks, or worker saturation?
~~~

If priority propagates intact at every checkpoint yet HIGH is still slow, the root cause lies in **capacity, scheduling, retries, or downstream bottlenecks**—not lost headers.

## 21. Anti-Patterns to Avoid

| Anti-pattern | Why it is wrong | Fix |
| --- | --- | --- |
| Setting `priority` only at producer without downstream tests. | An EIP or adapter may drop or alter metadata. | Contract tests at every boundary and wire integration tests. |
| Calling `MessageBuilder.withPayload(...)` in a custom Transformer without a header policy. | Crucial metadata may vanish from output. | Copy intentionally, re-validate, and test the real endpoint. |
| Copying all internal headers to HTTP/JMS/Kafka. | Leaks internal data, includes unserializable objects, or gets dropped silently. | Header allowlist + versioned wire contract. |
| Allowing external clients to set HIGH directly. | Can hog workers/queues and break quotas. | Server-side classification, authz, and rate limiting. |
| Setting priority=9 for Kafka expecting records to jump ahead of earlier offsets. | Kafka does not reorder by custom headers. | Separate topics/consumers or application-tier scheduling. |
| Setting Spring `priority` without configuring AMQP/JMS mapping. | Broker property may stay unset or overridden by defaults. | Inspect the native broker message property. |
| Confusing `PriorityChannel` with `DirectChannel`. | DirectChannel does not reorder by priority. | Place an actual queue/scheduler where prioritization is needed. |
| Letting Aggregator output priority depend on whichever message arrives last. | Non-deterministic under concurrency and retries. | Define explicit MAX/MIN/parent/deadline policy and test it. |
| Generating new event IDs or wiping `originalPriority` on retry. | Breaks deduplication and loses escalation history. | Keep business ID and original metadata durably. |
| Testing only headers while ignoring starvation. | High priority can still starve all other work. | Add aging/fairness, quotas, and queue-age monitoring. |

## 22. Practice Exercises

**Exercise 1 — Preserving priority during transformation.** Create a `RawCommand` with `priority=9` and `businessEventId`. Write a Transformer emitting `NormalizedCommand` and verify output after the endpoint. Test a broken header-dropping version, identify why it failed, and fix it.

**Exercise 2 — Ingress policy.** Have an HTTP client send `X-Work-Priority=HIGH`. Design server-side classification: authorized callers get 9; ordinary callers requesting HIGH for a report get downgraded to 1 with a metric recorded. Test wrong types, missing values, and out-of-range inputs.

**Exercise 3 — Two-branch Router.** Route HIGH and LOW messages through two different Transformers converging onto a `PriorityChannel`. Prove both branches preserve `priority` and business event IDs.

**Exercise 4 — Splitter/Aggregator.** An order has three items receiving priorities 9, 5, and 1. Implement a MAX policy for Aggregator output and test duplicates, timeouts, and partial releases with a stable correlation ID.

**Exercise 5 — JMS/AMQP adapter.** Send a message with Spring priority header 9. Inspect the native `JMSPriority` or `BasicProperties.priority` on the broker; if wrong, identify the header mapper, producer QoS, or queue setting causing it.

**Exercise 6 — Kafka.** Encode priority as record header bytes and decode back to `Integer` at the consumer. Explain why two records in the same partition still follow offset order rather than custom priority values.

**Exercise 7 — Retry and DLQ.** A HIGH message fails transiently three times. Verify retries keep event ID, original priority, and attempt count, then route to DLQ/quarantine per policy.

**Exercise 8 — Observability.** Add traces for assigned/enqueued/consumed priority. Add mismatch and oldest pending age metrics. Reproduce two failures—dropped header vs. intact header with congested consumer—and distinguish their signals.

### Self-Assessment Questions

**1. Does header `priority=9` make `DirectChannel` execute a message ahead of `priority=1`?** No. DirectChannel dispatches synchronously and has no priority queue.

**2. When a Transformer returns a new `Message`, should you assume all headers remain intact?** No. Define a header policy and test the endpoint output, especially with reconstructed messages or custom mappers.

**3. Which message does Aggregator take priority from?** It must be domain-defined, such as MAX of child messages or stored parent priority.

**4. Does Spring message `priority=9` automatically mean `JMSPriority=9`?** Never assume so. Verify the adapter mapping and actual JMS message property.

**5. Does RabbitMQ prioritize messages if you only set a custom application header named `priority`?** Do not assume so; you need `BasicProperties.priority` and a queue configured to support priority.

**6. Does Kafka sort records by a custom `priority` header?** No. Kafka maintains records by offset/partition with its own semantics.

**7. Why preserve `originalPriority` when using aging?** To know the initial level, trace escalation, and avoid resetting history across retries.

**8. Why can a HIGH message still be slow even when the consumer receives the right header?** Due to capacity, prefetch, backlog, slow handlers, concurrency, or downstream bottlenecks—not lost metadata.

## 23. Pre-Production Checklist

- [ ] Priority contract published: type, range, direction, default, and HIGH/NORMAL/LOW semantics.
- [ ] Trusted classification services/policies defined; raw external client priorities never trusted blindly.
- [ ] Stable `businessEventId`, `originalPriority`, and source metadata attached for auditing where needed.
- [ ] Tested after every Transformer building new messages and every header-enrichment step.
- [ ] Router verified to preserve headers on all branches; Filter/discard/error paths handle metadata cleanly.
- [ ] Splitter defines inherit/derive policy without breaking correlation/sequence metadata.
- [ ] Aggregator defines explicit output priority policy and is tested for timeouts, duplicates, and partial releases.
- [ ] Gateway/request–reply has separate request and reply priority contracts where needed.
- [ ] HTTP ingress validates sources and mappings, enforcing per-tenant quotas and authorization.
- [ ] JMS verifies actual `JMSPriority`; RabbitMQ verifies `BasicProperties.priority` and queue setup; Kafka verifies encode/decode without assuming reordering.
- [ ] Every external boundary uses an allowlist and versioned schema; internal object headers are never blindly copied out.
- [ ] Retry/DLQ preserves business ID, original priority, attempt, and failure reason; poison HIGH messages cannot consume all capacity.
- [ ] Tests verify high- and low-priority messages waiting simultaneously before polling, not just send order.
- [ ] Assigned/enqueued/consumed priority, mismatch counts, queue age, and retries per class are measured.
- [ ] Fairness/aging/capacity designed separately to prevent starvation; accurate priority metadata alone is not enough.
- [ ] For durable sources, transactions/ACK/redelivery, idempotency, and crash recovery are verified.

**Key takeaway:** **Priority only works when it is normalized, preserved across every message reconstruction, mapped properly at adapters, and actively honored by the target scheduler/broker.** Spring Integration lets you compose loosely coupled EIPs; in return, every Transformer, Splitter, Aggregator, Gateway, and external boundary must enforce an explicit metadata contract. Test **where priority is consumed**, not only where the header is first set.

### References

- [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html): channel types and PriorityChannel.
- [Spring Integration — Message Headers](https://docs.spring.io/spring-integration/reference/message.html): Message structure and headers across flows.
- [Spring Integration — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): transforming messages and endpoint reply-header handling.
- [Spring Integration — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation, sequence, release, and output.
- [RabbitMQ — Priority Queues](https://www.rabbitmq.com/docs/priority): broker-side prioritization and queue configuration.
- [Apache Kafka — Documentation](https://kafka.apache.org/documentation/): partitions, offsets, and record headers.

*Examples illustrate contracts and design principles. Before applying them to a project, verify APIs, mappers, serialization, and priority behavior in your exact Spring Integration, Spring Framework, and broker versions; these do not replace integration tests against real systems.*
