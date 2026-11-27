# Creating the Correlation ID at Ingress

## 1. Context: Receiving Multiple Messages and Knowing Which Belong to the Same Job

In the **Content-based correlation** chapter of the **SPRING_INTEGRATION_PATTERN** module, we learn to implement Enterprise Integration Patterns with **Spring Integration** to build loosely coupled, extensible message flows. Alongside Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, establishing a **correlation ID as soon as a message enters the system** is a fundamental condition for tracking and combining processing branches accurately.

For example, an order management system receives three independent events over HTTP or a broker:

| Event | Source | Related Content |
| --- | --- | --- |
| PAYMENT_CONFIRMED | Payment service | Payment for order ORD-101 |
| INVENTORY_RESERVED | Warehouse service | Inventory for order ORD-101 |
| ADDRESS_VERIFIED | Delivery service | Delivery address for order ORD-101 |

The three events may arrive at different times, from different producers, or even after a service restart. An **Aggregator** wants to emit a READY_TO_FULFILLMENT decision only when **all three results for the same order and the same processing round** have arrived.

~~~mermaid
flowchart LR
    P["Payment event"] --> I["Trusted ingress"]
    W["Inventory event"] --> I
    D["Address event"] --> I
    I --> K["Create/restore correlation key"]
    K --> B["Business events / channels"]
    B --> G["Aggregator by key"]
    G --> R["Order readiness"]
    G -.->|"Error / timeout"| E["Error / recovery"]
~~~

If each event generates a new UUID at ingress:

~~~text
PAYMENT_CONFIRMED   -> correlationId = 6c30...a1
INVENTORY_RESERVED  -> correlationId = f29b...d2
ADDRESS_VERIFIED    -> correlationId = 49ed...c9
~~~

The Aggregator sees **three different groups**, each missing two events. It has no way to know the messages all belong to ORD-101.

If only orderId is used as the correlation ID in a multi-tenant system:

~~~text
Tenant A / ORD-101 -> correlationId = ORD-101
Tenant B / ORD-101 -> correlationId = ORD-101
~~~

The Aggregator can **mix data from two different customers**. That is not merely a grouping bug, but potentially a data-isolation breach.

**Lesson Objectives**

1. Understand that a correlation ID is a **logical group key**, not a message ID, trace ID, or idempotency key.
2. Identify the **ingress** boundary as the earliest place with enough trustworthy information to create or restore the key.
3. Design a content-based key from tenant, business identity, and workflow epoch.
4. Compare **deterministic** keys with a random ID generated **once for the entire workflow**.
5. Attach correlation metadata to a Spring Message using MessageBuilder, with validation and without trusting client-supplied control headers.
6. Configure an Aggregator using the default header or a custom CorrelationStrategy to assemble the right groups.
7. Test across different tenants, different epochs, retries of the same logical event, missing/spoofed headers, fan-out, and incomplete groups.
8. Coordinate group timeout, persistent state, idempotency, logging, and error channels for safe operations.

## 2. What Is Content-Based Correlation?

**Correlation** answers the question: *which process, order, batch, or transaction does this message share with other messages?*

**Content-based correlation** determines the answer using information **inside the payload or validated business content**. For example, payment, inventory, and delivery events all carry a business order reference, so the application can use that reference as a component of the group key.

~~~text
Input content:
  orderRef = ORD-101
  workflowEpoch = 7

Authenticated tenant:
  tenantId = tenant-A

Derived correlation key:
  order-readiness:v1:tenant-A:ORD-101:7
~~~

For the same tenant, orderRef, and epoch, events of different types receive the same **group key**. For a different tenant or different epoch, they must receive a different key.

### 2.1. Correlation ID Differs from Message ID, Trace ID, and Event ID

| Identifier | Represents | Same Across Three Messages in the Same Workflow? |
| --- | --- | --- |
| **Spring MessageHeaders.ID** | A specific Spring Message object | Not guaranteed |
| **eventId** | A logical event, used for dedup/redelivery | No: each event type usually has a different eventId |
| **correlationId** | A group of related messages | **Yes**, for the same workflow/epoch |
| **traceId** | An observability/diagnostic trace | Not necessarily, especially across long-lived brokers |
| **requestId** | An HTTP/API request or a business command | Depends on contract; not implicitly the group ID |
| **orderId / batchId** | A business entity or batch | May repeat across multiple processing rounds |
| **workflowEpoch** | One run/version of a workflow on the same entity | Distinguishes a new workflow from an old redelivery |

Example:

~~~text
logical group = tenant-A / ORD-101 / epoch-7

event-001: PAYMENT_CONFIRMED      correlationId = group-7
event-002: INVENTORY_RESERVED     correlationId = group-7
event-003: ADDRESS_VERIFIED       correlationId = group-7

event-002 delivered again:
  eventId remains event-002
  correlationId remains group-7
  MessageHeaders.ID may change
~~~

**One group contains multiple event IDs.** Do not use eventId as correlationId if you want multiple distinct events to be grouped together. Conversely, do not use correlationId to assume each event appears only once.

### 2.2. Why Create It at Ingress?

Ingress is the first boundary where the application can:

- Authenticate the producer/actor and establish a **trusted tenant**.
- Parse, validate schema, and enforce payload size limits.
- Identify the business object the event actually belongs to.
- Look up the current workflow epoch in a registry/state store.
- Create or look up the group key according to policy.
- Attach a consistent internal header **before the message is branched by a Router/Filter/Splitter**.
- Record event identity, version, and correlation decisions for reconciliation.

This is a **responsibility boundary**, not necessarily an HTTP controller. With Kafka/JMS, ingress is the consumer adapter plus the initial validation/mapping layer; with an API, it may be the controller or application service right after authentication. Every entry point for the same workflow must use the **same key-generation/lookup contract**.

### 2.3. Do Not Confuse “Creating an ID” with “Generating a New UUID for Every Message”

There are two distinct situations:

1. **Starting a new workflow:** you may generate an opaque random group ID once, then store a durable mapping between the business object and the group ID.
2. **Receiving the second, third, or redelivered message of that workflow:** you must **look up the same group ID**, or recompute a deterministic key from the same trusted data.

If every incoming message calls UUID.randomUUID() without consulting a mapping, related replies/events will never be grouped properly by the Aggregator.

## 3. Choosing Components of the Correlation Key

A good group key must satisfy these conditions:

1. **Same workflow → same key**, even across adapters and redeliveries.
2. **Different tenant → different key**, when data is multi-tenant.
3. **Different workflow generation → different key**, when the same order is legitimately reprocessed.
4. **Stable**: never based on thread, receipt timestamp, technical message ID, or arrival order.
5. **Canonical**: all producers are normalized using a published rule.
6. **Does not leak sensitive data** in metric labels, URLs, or public logs.
7. **Cannot be arbitrarily specified by a client** to inject into someone else's group.

### 3.1. Four Ways to Choose a Key

| Choice | Pros | Risks |
| --- | --- | --- |
| **orderRef** | Simple | Collides across tenants or across workflow epochs |
| **tenantId + orderRef** | Isolates tenants | Can mix multiple processing runs of the same order |
| **tenantId + orderRef + epoch** | Separates customers and runs | Requires a trustworthy and stable workflow epoch |
| **Opaque group ID with durable mapping** | Hides orderRef, supports identity changes | Requires a registry and lookup/recovery |

In this lesson, we use **tenantId + orderRef + epoch**, with a version prefix:

~~~text
order-readiness:v1:tenant-A:ORD-101:7
~~~

In production, if tenant/orderRef can contain delimiters or Unicode characters, do not concatenate strings arbitrarily. Use **length encoding**, a type-safe composite key, or canonical encoding (and store hashed/opaque keys if needed). The Java examples restrict the character set to eliminate ambiguity.

### 3.2. Epoch Only Increments When a Truly New Workflow Begins

Suppose order ORD-101 completes epoch 7, and later business policy requires re-running the entire readiness process:

~~~text
ORD-101 / epoch 7 -> group A already completed
ORD-101 / epoch 8 -> new group B created
~~~

If a message from epoch 7 is redelivered, it **must** retain epoch 7; never “bump the epoch by arrival time” such that redelivery creates a bogus group B. State must be stored in a workflow registry and looked up by the **logical workflow** identity, rather than blindly checking only the latest epoch.

### 3.3. Business IDs Can Be Wrong or Spoofed

An HTTP client could send:

~~~json
{
  "eventId": "evt-91",
  "orderRef": "ORD-101",
  "workflowEpoch": 7,
  "correlationId": "tenant-admin:ORD-999:1"
}
~~~

Never use the correlationId field from this payload or HTTP header for internal routing without verifying permissions and mappings. Take **tenant from the authenticated principal**; verify orderRef and epoch against permissions/registry; then **internally generate** the correlation header, overwriting or discarding any value the producer tried to inject.

In particular, having a syntactically valid correlation ID **does not prove** the producer is authorized to access the group. Authentication, authorization, and tenancy validation remain independent requirements.

## 4. Canonicalization Policy

Before constructing a key, define the exact transformations:

- Should leading/trailing whitespace be trimmed?
- Is the order code case-sensitive?
- Is Unicode normalization accepted or ASCII only?
- Does the tenant ID come from the principal or from input?
- Are “000123” and “123” the same orderRef?
- Is the epoch signed by the producer or determined by the registry?

**Do not turn distinct business IDs into the same ID** through overly aggressive normalization. For example, if the system allows orderRef "ab" and "AB" to be two separate orders, calling toUpperCase() causes a collision bug.

For the contract illustrated in this lesson:

~~~text
tenantId: lowercase ASCII [a-z0-9_-]+, taken from verified context
orderRef: uppercase ASCII [A-Z0-9_-]+, converted from input per contract
epoch: positive integer, confirmed by the workflow registry
kind: one of the three allowed event types
~~~

**Use Locale.ROOT** when changing case so behavior does not depend on the JVM locale. If the product does not allow case normalization, preserve original casing and validate exact spelling.

### 4.1. When Are HMAC or Opaque IDs Needed?

If a correlation key contains sensitive internal identifiers or tenant names, consider:

- Generating a **UUID/ULID for the group** once and storing a durable mapping.
- Or computing **HMAC-SHA-256** over the canonical composite identity with a KMS-managed key, defining clear version/key rotation rules.

Hashing/HMAC **does not replace authorization**. HMAC can reduce exposure of business IDs inside a system, but if the application still logs raw payloads or exposes tenants through another API, data can still leak. Never put the HMAC secret in code, logs, or public configs.

## 5. Java 17: Input Model and Verified Identity

The example focuses on three result types for the same order. Each producer emits an independent message; no Splitter is used to generate parts.

### 5.1. Untrusted Raw Payload

~~~java
enum PartKind {
    PAYMENT,
    INVENTORY,
    ADDRESS
}

record OrderPartEvent(
        String eventId,
        String orderRef,
        int claimedEpoch,
        PartKind kind,
        boolean approved) {

    OrderPartEvent {
        if (eventId == null
                || !eventId.matches("[A-Za-z0-9_-]{1,80}")) {
            throw new IllegalArgumentException("INVALID_EVENT_ID");
        }
        if (orderRef == null || orderRef.isBlank()
                || orderRef.length() > 64) {
            throw new IllegalArgumentException("INVALID_ORDER_REF");
        }
        if (claimedEpoch < 1 || kind == null) {
            throw new IllegalArgumentException("INVALID_WORKFLOW_PART");
        }
    }
}
~~~

The **claimedEpoch** field is a claim from the source, not yet a verified workflow epoch. The **approved** field here simply illustrates a domain result; external producers must be authenticated for permission to emit the corresponding event type. Never allow an arbitrary client to send approved=true and let the Aggregator make decisions on it.

### 5.2. Verified Actor and Workflow Binding

~~~java
record VerifiedActor(
        String principalId,
        String tenantId) {
    VerifiedActor {
        if (principalId == null || principalId.isBlank()
                || tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("INVALID_VERIFIED_ACTOR");
        }
    }
}

record VerifiedWorkflowBinding(
        String tenantId,
        String orderRef,
        int epoch) {
}

interface WorkflowBindingResolver {
    VerifiedWorkflowBinding resolve(
            VerifiedActor actor,
            OrderPartEvent event);
}
~~~

**WorkflowBindingResolver** is a business port. A real implementation must:

1. Verify the actor/producer is authorized to report **that PartKind**.
2. Look up the order in the **trusted tenant's** data store, never trusting a tenantId from the payload as fact.
3. Match orderRef against durably stored identity.
4. Match claimedEpoch against an existing workflow instance, including redeliveries of older epochs.
5. Return **VerifiedWorkflowBinding** matching the business record, or reject.
6. Never auto-increment epoch based on arrival time.

In a multi-worker/multi-instance setup, the resolver must rely on consistent state. Never spawn a new workflow epoch merely because one instance does not see a mapping in its local cache.

## 6. Content-Based Correlation Key Builder Function

Isolating key construction into a pure function makes it testable before starting Spring Integration.

~~~java
import java.util.Locale;

final class OrderCorrelationKeys {
    private static final String PREFIX = "ordready:v1:";

    private OrderCorrelationKeys() {
    }

    static String from(VerifiedWorkflowBinding binding) {
        if (binding == null) {
            throw new IllegalArgumentException("MISSING_BINDING");
        }

        String tenant = binding.tenantId();
        if (tenant == null
                || !tenant.matches("[a-z0-9_-]{1,48}")) {
            throw new IllegalArgumentException("INVALID_TENANT");
        }

        String order = binding.orderRef();
        if (order == null) {
            throw new IllegalArgumentException("MISSING_ORDER_REF");
        }

        String canonicalOrder = order
                .trim()
                .toUpperCase(Locale.ROOT);
        if (!canonicalOrder.matches("[A-Z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("INVALID_ORDER_REF");
        }

        if (binding.epoch() < 1) {
            throw new IllegalArgumentException("INVALID_EPOCH");
        }

        return PREFIX
                + tenant + ":"
                + canonicalOrder + ":"
                + binding.epoch();
    }
}
~~~

The function above uses the ":" delimiter safely **only because** each component is regex-restricted not to contain ":". If expanded to Unicode or arbitrary delimiters, you must change the encoding strategy; otherwise, two distinct component tuples could produce the same key string.

### 6.1. Examples of Same/Different Keys

~~~text
from(tenant-a, ORD-101, epoch 7)
  -> ordready:v1:tenant-a:ORD-101:7

from(tenant-a, " ord-101 ", epoch 7)
  -> ordready:v1:tenant-a:ORD-101:7

from(tenant-b, ORD-101, epoch 7)
  -> ordready:v1:tenant-b:ORD-101:7

from(tenant-a, ORD-101, epoch 8)
  -> ordready:v1:tenant-a:ORD-101:8
~~~

The first two strings match under the published **case-insensitive rule**. The latter two yield different keys because the tenant or epoch differs.

### 6.2. Why Have a Version Prefix?

If correlation rules change from v1 to v2, never silently keep the same prefix while altering the computation:

~~~text
ordready:v1:tenant-a:ORD-101:7
ordready:v2:<opaque-hmac>
~~~

You need a migration plan:

- Configure producers/ingress to understand the key version.
- Retain the ability to look up pending v1 groups.
- Map v1 → v2 or drain before switching.
- Never mix two key formats for the same workflow in one Aggregator.
- When rotating HMAC keys, store the secret version and compatibility window.

Changing the algorithm without versioning can split remaining events of an active group onto a different key.

## 7. Ingress Enriches the Message and Actively Drops Spoofed Headers

Here ingress receives **OrderPartEvent** alongside **VerifiedActor** from the authentication layer. It calls WorkflowBindingResolver to obtain a trusted binding, computes a key, and constructs a **new Spring Message**.

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

final class OrderEventIngress {
    static final String GROUP_KEY = "businessCorrelationKey";
    static final String TRUSTED_TENANT = "trustedTenantId";
    static final String BUSINESS_EVENT_ID = "businessEventId";
    static final String WORKFLOW_EPOCH = "workflowEpoch";

    private final WorkflowBindingResolver bindings;
    private final MessageChannel correlatedInput;

    OrderEventIngress(
            WorkflowBindingResolver bindings,
            MessageChannel correlatedInput) {
        this.bindings = bindings;
        this.correlatedInput = correlatedInput;
    }

    void accept(OrderPartEvent event, VerifiedActor actor) {
        VerifiedWorkflowBinding binding =
                bindings.resolve(actor, event);
        String groupKey = OrderCorrelationKeys.from(binding);

        Message<OrderPartEvent> internal =
                MessageBuilder.withPayload(event)
                        .setHeader(GROUP_KEY, groupKey)
                        .setHeader(TRUSTED_TENANT, binding.tenantId())
                        .setHeader(WORKFLOW_EPOCH, binding.epoch())
                        .setHeader(
                                BUSINESS_EVENT_ID,
                                event.eventId())
                        .setHeader(
                                IntegrationMessageHeaderAccessor
                                        .CORRELATION_ID,
                                groupKey)
                        .build();

        if (!correlatedInput.send(internal)) {
            throw new IllegalStateException(
                    "CORRELATED_EVENT_DISPATCH_REJECTED");
        }
    }
}
~~~

This method **does not call copyHeaders() from an untrusted incoming Message**, does not read client-supplied errorChannel/replyChannel/routingSlip, and does not take tenant from an arbitrary HTTP header. The code attaches only the necessary internal metadata.

**In production**, you may add verified trace context, schemaVersion, server-assigned receivedAt, and outbox/transaction boundaries as needed. Every added header must have a defined source, owner, and permitted usage scope.

### 7.1. Why Attach Both CORRELATION_ID and businessCorrelationKey?

These two fields are related but do not necessarily keep the same value everywhere:

- **IntegrationMessageHeaderAccessor.CORRELATION_ID**: default technical header used by Aggregator/Resequencer.
- **businessCorrelationKey**: stable business key created at ingress, used across topologies, logs, replays, and custom correlation.

Initially both may hold the same value. However, a **Splitter** or a component with apply-sequence enabled can **reset the technical correlation/sequence headers** for child groups. At that point businessCorrelationKey still links back to the **parent workflow** and allows a custom CorrelationStrategy on the business Aggregator.

Do not force every nested Splitter/Scatter-Gather to share one global CORRELATION_ID. You may need **separate correlation IDs for child groups** alongside a durable **parent business key** to tie them back to the same workflow.

### 7.2. A New Message ID on Every Build Is Normal

MessageBuilder may create a Spring Message with a new MessageHeaders.ID. That is normal behavior for technical identity, **not a correlation bug**, provided that:

- Business eventId remains unchanged on redelivery.
- Workflow binding is stable.
- The generated group key remains identical.
- Deduplication and downstream side effects handle replays per policy.

### 7.3. Ingress send() Does Not Guarantee Business Commit

With a **DirectChannel**, send() usually runs the handler on the same thread; exceptions can propagate back to the caller. With an **ExecutorChannel**, a successful send() may mean only that the executor accepted the task. With a **QueueChannel/broker**, enqueuing does not mean the Aggregator has released or the DB has committed.

The API contract must distinguish **accepted for processing** from **business completed**. When an async API returns 202 Accepted, group completion is communicated via a status endpoint or subsequent event, never by retroactively changing the returned HTTP status.

## 8. Ingress with HTTP, Broker, and Gateway

### 8.1. HTTP: Enforcing Tenant at the Security Boundary

An HTTP controller can:

1. Receive the JSON request and parse it into a DTO.
2. Validate the auth token/session and map it to VerifiedActor.
3. Pass the event and actor to OrderEventIngress.
4. Return 202 with an eventId/trackingId when accepted for async processing.

~~~text
HTTP request
  headers: X-Tenant=tenant-b, X-Correlation-ID=anything
  body: orderRef=ORD-101, eventType=PAYMENT

Spring Security principal:
  verified tenantId=tenant-a

BindingResolver:
  checks permissions for ORD-101 belonging to tenant-a
  determines groupKey=ordready:v1:tenant-a:ORD-101:7
~~~

Never trust X-Tenant/X-Correlation-ID just because the client sent them. If the API allows clients to supply a **clientRequestId** for tracing, store it as **untrusted request metadata** after validating length/characters; never turn it into a key that can join across tenants.

### 8.2. Broker: Preserving IDs Across Retries and Restarts

With Kafka/JMS or another broker, a message can be redelivered when the consumer has not acked/committed. Ingress must:

- Authenticate the topic/queue source and ACLs.
- Parse and validate schemaVersion.
- Obtain the verified tenant and order binding from trusted sources.
- Recompute the same groupKey from normalized/verified data.
- Keep the logical eventId stable across redeliveries.
- Never use a partition offset as a business correlation key (offsets vary per record and do not represent a workflow).
- Choose ack/requeue/error handling appropriate for an incomplete group.

If a process generates a random group ID without **saving the mapping** before acking the message, a restart can generate a different group ID. When recovery is required, use a deterministic key or a durable transactional/outbox mapping.

### 8.3. Gateway: Request/Reply Correlation Differs from Group Correlation

A Spring Integration **Messaging Gateway** typically creates a temporary **replyChannel** to match a reply back to the exact Java request/reply call. It is not synonymous with the business correlationId used by the application to gather three events for the same order.

~~~text
API gateway invocation
  replyChannel = temporary gateway channel
  businessCorrelationKey = ordready:v1:tenant-a:ORD-101:7
~~~

If the application needs to wait for **three events from independent systems** over a long duration, do not block a synchronous Gateway indefinitely. Use durable workflow state plus a status API or callback/completion event. Even for a short request/reply flow, protect the framework-generated replyChannel so clients cannot control it.

## 9. Using the Correlation Key in the Aggregator

Spring Integration correlates by default on **IntegrationMessageHeaderAccessor.CORRELATION_ID**. Messages sharing the same header value are placed into the same **MessageGroup**. **When a group is released** is the separate responsibility of **ReleaseStrategy**; having a correlation key alone is not enough.

~~~mermaid
flowchart TD
    A["OrderPartEvent"] --> I["Ingress: verify + key"]
    I --> C["businessCorrelationKey"]
    C --> G["Aggregator"]
    G --> K{"CorrelationStrategy"}
    K --> Q["MessageGroup by key"]
    Q --> S{"ReleaseStrategy has all 3 kinds?"}
    S -->|"No"| W["Keep group waiting"]
    S -->|"Yes"| P["OutputProcessor"]
    P --> O["OrderReadiness"]
~~~

### 9.1. Crucial Detail: Are All Three Event Kinds Present?

Three events coming from different sources **do not necessarily carry sequenceNumber/sequenceSize** generated by a Splitter. If you only set correlationId and rely on the default SequenceSizeReleaseStrategy, the Aggregator will not know when enough messages have arrived to release.

In this example, the completion criterion is:

~~~text
Group is complete when it has exactly:
  PAYMENT
  INVENTORY
  ADDRESS

Do not use:
  group.size() == 3

If all three messages are PAYMENT due to retries or producer errors,
group.size() == 3 still does not prove all three branches arrived.
~~~

The right design is to check the **identity of each component**, while also having deduplication/an inbox upstream of the Aggregator if the broker can redeliver.

### 9.2. Result Data Model

~~~java
import java.util.List;

record OrderReadiness(
        String groupKey,
        String tenantId,
        String orderRef,
        int epoch,
        String decision,
        List<OrderPartEvent> evidence) {
}
~~~

**OrderReadiness** is the business outcome assembled from the three inputs. In the demo code, the decision is READY only when all three have approved=true; if any component is not approved, the decision is REVIEW_REQUIRED. Production logic must follow real business states, which may include reject/retry/manual approval.

## 10. ReleaseStrategy and MessageGroupProcessor

The two pure functions below separate **member completeness checks** from **result aggregation**.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

import org.springframework.integration.store.MessageGroup;
import org.springframework.messaging.Message;

final class OrderGroupRules {
    private OrderGroupRules() {
    }

    static boolean complete(MessageGroup group) {
        if (group.size() != PartKind.values().length) {
            return false;
        }
        Set<PartKind> found = EnumSet.noneOf(PartKind.class);
        for (Message<?> message : group.getMessages()) {
            if (!(message.getPayload() instanceof OrderPartEvent part)) {
                return false;
            }
            if (!found.add(part.kind())) {
                return false; // Two parts of the same kind: group is incomplete.
            }
        }
        return found.size() == PartKind.values().length;
    }

    static OrderReadiness summarize(MessageGroup group) {
        if (!complete(group)) {
            throw new IllegalStateException("INCOMPLETE_ORDER_GROUP");
        }

        List<Message<?>> messages =
                new ArrayList<>(group.getMessages());
        Message<?> first = messages.get(0);

        String key = (String) first.getHeaders()
                .get(OrderEventIngress.GROUP_KEY);
        String tenant = (String) first.getHeaders()
                .get(OrderEventIngress.TRUSTED_TENANT);
        Integer epoch = (Integer) first.getHeaders()
                .get(OrderEventIngress.WORKFLOW_EPOCH);

        if (key == null || tenant == null || epoch == null) {
            throw new IllegalStateException("MISSING_TRUSTED_METADATA");
        }

        List<OrderPartEvent> evidence = new ArrayList<>();
        for (Message<?> message : messages) {
            if (!Objects.equals(
                    key, message.getHeaders()
                            .get(OrderEventIngress.GROUP_KEY))
                    || !Objects.equals(
                            tenant, message.getHeaders()
                                    .get(OrderEventIngress.TRUSTED_TENANT))
                    || !Objects.equals(
                            epoch, message.getHeaders()
                                    .get(OrderEventIngress.WORKFLOW_EPOCH))) {
                throw new IllegalStateException(
                        "MIXED_WORKFLOW_METADATA");
            }
            evidence.add((OrderPartEvent) message.getPayload());
        }

        evidence.sort(Comparator.comparing(OrderPartEvent::kind));
        String order = evidence.get(0).orderRef()
                .trim().toUpperCase(java.util.Locale.ROOT);
        if (evidence.stream().anyMatch(
                part -> !part.orderRef()
                        .trim().toUpperCase(java.util.Locale.ROOT)
                        .equals(order))) {
            throw new IllegalStateException("MIXED_ORDER_REFS");
        }

        boolean ready = evidence.stream()
                .allMatch(OrderPartEvent::approved);

        return new OrderReadiness(
                key,
                tenant,
                order,
                epoch,
                ready ? "READY" : "REVIEW_REQUIRED",
                List.copyOf(evidence));
    }
}
~~~

**Why re-check metadata?** CorrelationStrategy groups by the computed key, but when building the output, verifying tenant/epoch/orderRef catches mapping bugs or an integration endpoint accidentally attaching the wrong header. An extra check does not replace ingress authorization, but helps **fail closed** if a group contains inconsistent data.

### 10.1. Duplicates Before the Group Is Complete

If a PAYMENT event is sent twice before INVENTORY/ADDRESS arrive:

~~~text
Group:
  PAYMENT(evt-1)
  PAYMENT(evt-1)   <-- duplicate
  INVENTORY(evt-2)
  ADDRESS(evt-3)
~~~

`complete()` returns false because the group has 4 messages. **That does not solve duplicates**; rather, it deliberately blocks an untrusted result. If redeliveries can occur, you need deduplication **before adding to the group** or a dedicated group processor/release policy with rules for duplicates and state repair. Otherwise, the group may sit waiting until timeout.

**At ingress**, a durable inbox with an appropriate key can identify a previously accepted eventId. If the same eventId arrives with a different payload, report **ID_CONFLICT** instead of treating the message as a normal duplicate. See the idempotency section.

### 10.2. Not All Outcomes Have to Succeed

If PAYMENT has approved=false but is a valid event, it is still **a terminal member of the group**. The Aggregator receives all three kinds and returns REVIEW_REQUIRED. Do not Filter out failed messages while still expecting three members, as doing so will keep the group incomplete.

For infrastructure errors without a terminal outcome yet, use PENDING/RETRYING state or a separate error/recovery flow; never fabricate APPROVED=false when the actual outcome is unknown.

## 11. IntegrationFlow Using a Custom CorrelationStrategy

In Spring Integration Java DSL, the Aggregator can read a dedicated header as its correlation key. This is useful when a Splitter, Scatter-Gather, or integration endpoint between ingress and the aggregator modifies technical sequence headers.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class OrderCorrelationFlowConfig {

    @Bean
    MessageChannel correlatedOrderInput() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel orderReadinessResults() {
        return new QueueChannel();
    }

    @Bean
    QueueChannel lateCorrelatedEvents() {
        return new QueueChannel();
    }

    @Bean
    OrderEventIngress orderEventIngress(
            WorkflowBindingResolver resolver,
            @org.springframework.beans.factory.annotation.Qualifier(
                    "correlatedOrderInput")
            MessageChannel input) {
        return new OrderEventIngress(resolver, input);
    }

    @Bean
    IntegrationFlow orderCorrelationFlow() {
        return IntegrationFlow.from("correlatedOrderInput")
                .aggregate(a -> a
                        .correlationStrategy(message -> {
                            Object key = message.getHeaders()
                                    .get(OrderEventIngress.GROUP_KEY);
                            if (!(key instanceof String text)
                                    || text.isBlank()) {
                                throw new IllegalArgumentException(
                                        "MISSING_BUSINESS_CORRELATION_KEY");
                            }
                            return text;
                        })
                        .releaseStrategy(OrderGroupRules::complete)
                        .outputProcessor(OrderGroupRules::summarize)
                        .groupTimeout(30_000)
                        .sendPartialResultOnExpiry(false)
                        .discardChannel("lateCorrelatedEvents"))
                .channel("orderReadinessResults")
                .get();
    }
}
~~~

**How to run:** provide a real WorkflowBindingResolver bean implementation; events are verified and passed to OrderEventIngress.accept(). A group containing PAYMENT, INVENTORY, and ADDRESS pushes an OrderReadiness into the QueueChannel. This channel is for examples/tests; real deployments require a consumer and proper persistence/ack strategies.

**Important:** groupTimeout(30_000) here is an illustrative limit for stalled groups; because sendPartialResultOnExpiry=false, it will not emit a READY result when members are missing. For real timeouts, mark the group INCOMPLETE/EXPIRED in the state store and maintain a late-arrival policy. Configuring discardChannel only handles messages the Aggregator actually discards under its own mechanism; it does not automatically create a durable failed-workflow state.

### 11.1. Configuring Based on the Default Header

When no component alters the technical correlationId, you can use the default:

~~~java
.aggregate(a -> a
        .releaseStrategy(OrderGroupRules::complete)
        .outputProcessor(OrderGroupRules::summarize))
~~~

Since OrderEventIngress already sets CORRELATION_ID, the default Aggregator groups by that header. However, in topologies with **nested splitters/recipient-lists** and multiple correlation scopes, a custom correlationStrategy reading businessCorrelationKey explicitly states that the Aggregator is joining the **parent workflow**, not a child sequence group.

### 11.2. When Is Relying Directly on Payload Appropriate?

You might write:

~~~java
.aggregate(a -> a
        .correlationStrategy(message -> {
            OrderPartEvent event =
                    (OrderPartEvent) message.getPayload();
            // Assumes an internal verified binding already exists.
            // Do not take tenant from an unauthenticated event.
            return event.orderRef();
        }))
~~~

**This is an anti-pattern if using raw orderRef**, because it lacks tenant and epoch. Using the payload directly is valid only when the payload is already **canonicalized, bound to a verified tenant identity and stable epoch**, or when correlationStrategy calls a trusted service rather than interpreting unauthorized input fields. Computing the key at ingress is generally easier to audit and test than having every Aggregator construct its own variants.

### 11.3. Custom Keys Must Be Immutable for the Same Group

CorrelationStrategy is invoked when each message arrives. If it depends on:

- Current time (LocalDateTime.now()).
- A new random UUID per message.
- Thread name, instance ID, or Kafka offset.
- The workflow registry's “latest epoch” instead of the **message's epoch**.
- Configuration that changes between event arrivals.

then the same workflow can be split across multiple groups. Keep the key/version/binding fixed on the message or use a lookup capable of recovering the original identity.

## 12. Unit Testing the Key Builder Function

Because key construction is a pure transformation, it can be tested without starting a Spring context.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class OrderCorrelationKeysTest {

    @Test
    void sameVerifiedIdentityProducesSameKey() {
        String first = OrderCorrelationKeys.from(
                new VerifiedWorkflowBinding(
                        "tenant-a", "ORD-101", 7));
        String second = OrderCorrelationKeys.from(
                new VerifiedWorkflowBinding(
                        "tenant-a", " ord-101 ", 7));

        assertEquals(first, second);
        assertEquals(
                "ordready:v1:tenant-a:ORD-101:7",
                first);
    }

    @Test
    void differentTenantsNeverShareAGroupKey() {
        String tenantA = OrderCorrelationKeys.from(
                new VerifiedWorkflowBinding(
                        "tenant-a", "ORD-101", 7));
        String tenantB = OrderCorrelationKeys.from(
                new VerifiedWorkflowBinding(
                        "tenant-b", "ORD-101", 7));

        assertNotEquals(tenantA, tenantB);
    }

    @Test
    void aNewWorkflowEpochGetsANewGroup() {
        String epoch7 = OrderCorrelationKeys.from(
                new VerifiedWorkflowBinding(
                        "tenant-a", "ORD-101", 7));
        String epoch8 = OrderCorrelationKeys.from(
                new VerifiedWorkflowBinding(
                        "tenant-a", "ORD-101", 8));

        assertNotEquals(epoch7, epoch8);
    }

    @Test
    void rejectsInvalidTenantAndDelimiter() {
        assertThrows(IllegalArgumentException.class,
                () -> OrderCorrelationKeys.from(
                        new VerifiedWorkflowBinding(
                                "tenant:admin", "ORD-101", 7)));

        assertThrows(IllegalArgumentException.class,
                () -> OrderCorrelationKeys.from(
                        new VerifiedWorkflowBinding(
                                "tenant-a", "ORD:101", 7)));
    }

    @Test
    void rejectsMissingOrInvalidWorkflowEpoch() {
        assertThrows(IllegalArgumentException.class,
                () -> OrderCorrelationKeys.from(
                        new VerifiedWorkflowBinding(
                                "tenant-a", "ORD-101", 0)));
    }
}
~~~

**These tests prove:** the key construction rules are stable, canonicalization behaves as published, tenants and epochs remain isolated, and inputs containing delimiter characters are rejected. They **do not prove** that WorkflowBindingResolver enforces permissions properly or that adapters/brokers preserve metadata across all retries.

## 13. Unit Test: Ingress Attaches Headers from Verified Binding

To test the message-creation boundary, use a MessageChannel that only records sent messages without starting the IntegrationFlow.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;

class OrderEventIngressTest {

    static class RecordingChannel implements MessageChannel {
        Message<?> last;

        @Override
        public boolean send(Message<?> message) {
            last = message;
            return true;
        }

        @Override
        public boolean send(Message<?> message, long timeout) {
            return send(message);
        }
    }

    @Test
    void derivesTrustedCorrelationAtIngress() {
        RecordingChannel channel = new RecordingChannel();

        WorkflowBindingResolver resolver = (actor, event) -> {
            assertEquals("tenant-a", actor.tenantId());
            assertEquals("ORD-500", event.orderRef());
            return new VerifiedWorkflowBinding(
                    actor.tenantId(), event.orderRef(), 4);
        };

        OrderEventIngress ingress =
                new OrderEventIngress(resolver, channel);
        OrderPartEvent input = new OrderPartEvent(
                "evt-payment-500", "ORD-500", 4,
                PartKind.PAYMENT, true);

        ingress.accept(
                input, new VerifiedActor("user-1", "tenant-a"));

        assertNotNull(channel.last);
        assertEquals(input, channel.last.getPayload());
        assertEquals(
                "ordready:v1:tenant-a:ORD-500:4",
                channel.last.getHeaders()
                        .get(OrderEventIngress.GROUP_KEY));
        assertEquals(
                channel.last.getHeaders()
                        .get(OrderEventIngress.GROUP_KEY),
                channel.last.getHeaders()
                        .get(IntegrationMessageHeaderAccessor
                                .CORRELATION_ID));
        assertEquals(
                "tenant-a",
                channel.last.getHeaders()
                        .get(OrderEventIngress.TRUSTED_TENANT));
    }

    @Test
    void rejectedWorkflowNeverPublishesAMessage() {
        RecordingChannel channel = new RecordingChannel();
        WorkflowBindingResolver resolver = (actor, event) -> {
            throw new SecurityException("ORDER_ACCESS_DENIED");
        };

        OrderEventIngress ingress =
                new OrderEventIngress(resolver, channel);

        assertThrows(SecurityException.class,
                () -> ingress.accept(
                        new OrderPartEvent(
                                "evt-denied", "ORD-999", 1,
                                PartKind.PAYMENT, true),
                        new VerifiedActor("user-2", "tenant-a")));
        assertNull(channel.last);
    }
}
~~~

In a real HTTP adapter, if the request already carries a "correlationId" header, the controller does not forward that header into OrderEventIngress: the ingress layer accepts only the **payload** and **verified actor**. Tests should include a request with a spoofed header to verify the adapter does not accidentally copy headers before calling ingress.

**Note on authentication errors:** production must return appropriate responses with controlled logging, never leaking raw internal exception details in the HTTP response.

## 14. Integration Test: Three Events Arriving Out of Order Still Join the Same Group

The following JUnit 5 example boots a Spring context using OrderCorrelationFlowConfig. The resolver in the test is a **stub**, used only to verify the grouping mechanism; it does not replace a production authorization/registry implementation.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OrderCorrelationFlowTest.TestConfig.class)
class OrderCorrelationFlowTest {

    @Configuration
    @Import(OrderCorrelationFlowConfig.class)
    static class TestConfig {
        @Bean
        WorkflowBindingResolver testBindings() {
            // Test double. In production, tenant/order/epoch must be verified.
            return (actor, event) ->
                    new VerifiedWorkflowBinding(
                            actor.tenantId(),
                            event.orderRef(),
                            event.claimedEpoch());
        }
    }

    @Autowired
    OrderEventIngress ingress;

    @Autowired
    @Qualifier("orderReadinessResults")
    QueueChannel reports;

    private static final VerifiedActor TENANT_A =
            new VerifiedActor("test-user-a", "tenant-a");
    private static final VerifiedActor TENANT_B =
            new VerifiedActor("test-user-b", "tenant-b");

    @BeforeEach
    void clearOutput() {
        while (reports.receive(0) != null) {
            // Drain output queue between tests.
        }
    }

    private void send(
            String eventId, String order, int epoch,
            PartKind kind, boolean approved,
            VerifiedActor actor) {
        ingress.accept(new OrderPartEvent(
                eventId, order, epoch, kind, approved), actor);
    }

    @Test
    void threeIndependentEventsJoinSameWorkflow() {
        send("evt-a-101", "ORD-101", 10,
                PartKind.ADDRESS, true, TENANT_A);
        send("evt-p-101", "ord-101", 10,
                PartKind.PAYMENT, true, TENANT_A);

        assertNull(reports.receive(0));

        send("evt-i-101", "ORD-101", 10,
                PartKind.INVENTORY, true, TENANT_A);

        Message<?> result = reports.receive(0);
        assertNotNull(result);
        OrderReadiness readiness =
                (OrderReadiness) result.getPayload();

        assertEquals(
                "ordready:v1:tenant-a:ORD-101:10",
                readiness.groupKey());
        assertEquals("tenant-a", readiness.tenantId());
        assertEquals(3, readiness.evidence().size());
        assertEquals("READY", readiness.decision());
        assertNull(reports.receive(0));
    }

    @Test
    void twoTenantsWithSameOrderRefAreNotMixed() {
        send("evt-a-payment", "ORD-202", 3,
                PartKind.PAYMENT, true, TENANT_A);
        send("evt-a-inventory", "ORD-202", 3,
                PartKind.INVENTORY, true, TENANT_A);

        send("evt-b-address", "ORD-202", 3,
                PartKind.ADDRESS, true, TENANT_B);
        assertNull(reports.receive(0));

        send("evt-a-address", "ORD-202", 3,
                PartKind.ADDRESS, true, TENANT_A);

        OrderReadiness result = (OrderReadiness)
                reports.receive(0).getPayload();
        assertEquals("tenant-a", result.tenantId());
        assertEquals(3, result.evidence().size());
        assertNull(reports.receive(0));
    }

    @Test
    void newEpochIsSeparateFromOldEpoch() {
        send("evt-e4-payment", "ORD-303", 4,
                PartKind.PAYMENT, true, TENANT_A);
        send("evt-e4-inventory", "ORD-303", 4,
                PartKind.INVENTORY, true, TENANT_A);
        send("evt-e5-address", "ORD-303", 5,
                PartKind.ADDRESS, true, TENANT_A);

        assertNull(reports.receive(0));

        send("evt-e4-address", "ORD-303", 4,
                PartKind.ADDRESS, true, TENANT_A);

        OrderReadiness result = (OrderReadiness)
                reports.receive(0).getPayload();
        assertEquals(4, result.epoch());
        assertNull(reports.receive(0));
    }

    @Test
    void negativeDomainOutcomeStillCompletesTheGroup() {
        send("evt-p-404", "ORD-404", 1,
                PartKind.PAYMENT, false, TENANT_A);
        send("evt-i-404", "ORD-404", 1,
                PartKind.INVENTORY, true, TENANT_A);
        send("evt-a-404", "ORD-404", 1,
                PartKind.ADDRESS, true, TENANT_A);

        OrderReadiness result = (OrderReadiness)
                reports.receive(0).getPayload();
        assertEquals("REVIEW_REQUIRED", result.decision());
        assertEquals(3, result.evidence().size());
    }
}
~~~

### 14.1. What the Integration Test Proves

- Independent events **do not need to arrive in a fixed order** to be combined.
- The correlation ID created at ingress is identical when verified tenant/orderRef/epoch match.
- Two tenants with the same orderRef are not merged.
- Two epochs of the same order are not merged.
- A terminal event with approved=false still **contributes to the group**, rather than being confused with a Filter-dropped message.

### 14.2. What the Integration Test Does Not Prove

- The real WorkflowBindingResolver prevents access spoofing.
- Duplicate/redelivered events are blocked at a durable inbox layer.
- MessageGroupStore recovers after a restart.
- All three broker-connected producers enforce the same identity policy.
- Downstream transactions/side effects are executed exactly once.
- Group timeouts/late arrivals behave within SLA.

For production, add tests covering these failure modes; never rely solely on a happy-path Spring context test.

## 15. When Messages Pass Through Router, Filter, Transformer, Splitter, and Gateway

Creating a correlation ID at ingress is only useful if downstream steps **preserve or properly re-establish the correlation contract**.

| Component | Common Impact | What to Check |
| --- | --- | --- |
| **Transformer** | Replaces payload or builds a new Message | Business key still passes through; verified data is unaltered |
| **Filter** | Can discard a message | Group needs a terminal outcome/timeout if a required member is dropped |
| **Content-Based Router** | Chooses a channel by content | Branches retain the parent group identity |
| **Recipient List** | Replicates a request to multiple recipients | Use a child group/sequence if waiting for every recipient to reply |
| **Splitter** | Emits multiple child messages and sequencing headers | Do not confuse child group with the parent business workflow |
| **Aggregator** | Combines messages by key and release policy | Pick the right CorrelationStrategy and check completeness |
| **Resequencer** | Orders sequences within a group | Epoch and sequence metadata are explicit |
| **Gateway** | Request/reply and temporary replyChannel | Do not conflate replyChannel with the business correlation key |
| **Error Channel** | Carries error info within the relevant flow | failedMessage/originalMessage may be absent; does not automatically become a group member |

### 15.1. Splitter Can Change the Correlation Scope

A Splitter typically attaches **CORRELATION_ID, SEQUENCE_NUMBER, SEQUENCE_SIZE** to child messages. In many topologies, the technical correlation value on children exists to rejoin **child items of the same parent Message**, not necessarily the same business group formed from multiple external events.

~~~mermaid
flowchart TD
    I["Ingress: businessCorrelationKey=Order-101"] --> S["Splitter"]
    S --> A["Child 1, technical correlation=split-X"]
    S --> B["Child 2, technical correlation=split-X"]
    A --> C["Child Aggregator"]
    B --> C
    C --> P["Business result: Order-101"]
~~~

Solution:

- Keep **businessCorrelationKey** in a dedicated header to trace the parent group.
- Use the Splitter's technical correlationId so the child Aggregator reassembles the sequence properly.
- If a business-level Aggregator needs to gather events from multiple producers, use a custom CorrelationStrategy based on the verified **businessCorrelationKey**.
- Test actual reply metadata after Transformers/Handlers instead of assuming every component preserves all headers.

**Do not force two correlation scopes into one if they mean different things.** An order may contain multiple packages, each with its own sequence, while all packages belong to the same order workflow.

### 15.2. Filtering Out a Member Can Prevent a Group from Ever Releasing

Suppose ADDRESS_VERIFIED is dropped by a Filter, yet the Aggregator requires PAYMENT/INVENTORY/ADDRESS. The group will stall waiting for ADDRESS.

If ADDRESS is invalid, the business can emit a **terminal rejection outcome** so the Aggregator outputs REVIEW_REQUIRED instead of silently discarding. If it is an infrastructure error with no final decision yet, use a retry/timeout/incomplete policy.

**Do not arbitrarily lower the expected member count to mask a missing member.** With three distinct sources, you must know exactly which kind arrived, which is missing, and why.

### 15.3. ErrorMessage Does Not Automatically Join the Aggregator

If a handler fails asynchronously, Spring Integration may send an ErrorMessage to errorChannel. ErrorMessage has a Throwable payload, not a domain-confirmed OrderPartEvent.

A recovery flow intending to produce a terminal failure outcome must:

1. Reliably identify the event/tenant/workflow group.
2. Classify the error: validation, timeout, transient, unexpected, or unknown.
3. Retry only the affected item/branch if recoverable.
4. If the business allows a terminal conclusion, emit an outcome with the proper type and identity.
5. Ensure it never emits **two terminal outcomes** if the worker succeeds late while recovery already emitted a failure.

Never map every Throwable to approved=false, because a transient DB error **does not prove** payment or inventory was declined.

## 16. Duplicates, Replays, and Idempotency Are Separate from Correlation

Suppose Kafka redelivers PAYMENT(evt-1) while the Aggregator is waiting for INVENTORY and ADDRESS. A proper correlation ID places both copies of PAYMENT into the **same group**, which by itself provides no deduplication.

~~~text
input:
  PAYMENT(evt-1)   -> group G
  INVENTORY(evt-2) -> group G
  PAYMENT(evt-1)   -> group G (duplicate)
  ADDRESS(evt-3)   -> group G

If only counting messages:
  group size = 4
  unique kinds = 3
~~~

Therefore **creating a group key** and **deduplicating logical events** are two distinct responsibilities.

### 16.1. Choosing the Right Deduplication Identity

For example, events whose eventId is unique within a tenant:

~~~text
dedupKey = trustedTenantId + ":" + eventId
~~~

If eventId is only unique per producer:

~~~text
dedupKey = trustedTenantId + ":" + producerId + ":" + eventId
~~~

If a workflow permits a **new version of the same event kind**, use an explicit revision or operationId:

~~~text
logicalPartKey =
    tenantId + ":" + orderRef + ":" + epoch
    + ":" + partKind + ":" + partRevision
~~~

Do not treat every new PAYMENT for an order as a permanent duplicate: systems may support legitimate corrections/reversals. Conversely, do not let a producer generate a fresh eventId for the same redelivery and bypass deduplication.

### 16.2. Durable Inbox/Ledger

Example PostgreSQL schema:

~~~sql
CREATE TABLE order_part_inbox (
    tenant_id VARCHAR(48) NOT NULL,
    producer_id VARCHAR(64) NOT NULL,
    event_id VARCHAR(80) NOT NULL,
    group_key VARCHAR(240) NOT NULL,
    part_kind VARCHAR(20) NOT NULL,
    payload_digest VARCHAR(128) NOT NULL,
    status VARCHAR(24) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, producer_id, event_id)
);

CREATE INDEX idx_order_part_inbox_group
    ON order_part_inbox (group_key);
~~~

An inbox transaction can:

1. Claim/look up identity by tenant, producer, and eventId using the unique constraint.
2. When the event already exists, check **payload_digest and group_key**: an exact match may be a redelivery, while differing content must be flagged as **ID_CONFLICT**.
3. Dispatch to the Aggregator only if the event is in a state/attempt eligible to proceed.
4. Record progress and appropriate terminal or retry states.

**Watch the transaction boundary:** if you save "seen" and then crash **before sending the event to the Aggregator**, redelivery must not be skipped in a way that drops the message. A transactional outbox, ack-after-commit, or an inbox state machine with **RECEIVED → DISPATCHED → COMPLETED** plus a recovery job are common solutions.

~~~text
Anti-pattern without recovery:
  if notSeen(eventId):
      markSeenInDatabase()
      sendToAggregator()    // crashing here loses the event
~~~

### 16.3. Correct Correlation Does Not Mean Exactly-Once

Even if the Aggregator produces a single OrderReadiness in one run, a downstream handler can be retried and send duplicate emails or place duplicate orders if a reply or ack is lost.

Apply **idempotency where side effects occur**, for example:

~~~text
effectKey =
    tenantId + ":" + orderRef + ":" + epoch
    + ":reserve-fulfillment"
~~~

The business operation ID must match the action being protected, not just a technical message ID. For external APIs, use provider-supported idempotency keys or an UNKNOWN/reconciliation state when a response is lost.

### 16.4. New Events for an Old Epoch After Group Completion

An event arrives very late for epoch 7 when the epoch 7 group has already completed. If completed-group metadata still exists, the Aggregator can recognize and discard it per policy. If metadata was purged or the process restarted with an in-memory store, the group could be recreated.

You need a **business ledger and event identity** that outlives `MessageGroupStore` retention if the contract requires long-term deduplication.

## 17. Timeouts, Incomplete Groups, and Late Arrivals

A group that has PAYMENT and INVENTORY but never receives ADDRESS must have an explicit operational state.

~~~text
Expected kinds: PAYMENT, INVENTORY, ADDRESS
Arrived:        PAYMENT, INVENTORY
Missing:        ADDRESS
State:          IN_PROGRESS -> INCOMPLETE after deadline
~~~

Never:

- Report READY merely because two events arrived.
- Assume ADDRESS=false when the source has not returned a result.
- Delete the group and pretend the failure was handled.
- Send an empty reply to the Gateway and treat it as success.

### 17.1. Easily Confused Timeouts

| Timeout | Location | Purpose |
| --- | --- | --- |
| **Source adapter timeout** | HTTP/Kafka/JMS or external client call | Bounds a single fetch/send attempt |
| **Aggregator groupTimeout** | MessageGroup lifecycle | Limits waiting for a group to gather members |
| **Gateway replyTimeout** | Request/reply caller | Limits waiting for a single reply |
| **Business deadline** | Workflow state | Governs whether events are still accepted to complete |
| **Retention/MessageGroupStoreReaper** | Storage cleanup | Purges stale metadata after an appropriate period |

These timers do not synchronize automatically. If the business deadline is 30 minutes, a 10-second HTTP Gateway timeout cannot mark the whole workflow FAILED. If groupTimeout fires before the business deadline, you need a way to resume or rely on persistent workflow state rather than an in-memory aggregator alone.

### 17.2. Reporting INCOMPLETE Status

If the business needs to know **which member is missing**, store a manifest:

~~~json
{
  "groupKey": "ordready:v1:tenant-a:ORD-101:7",
  "expectedKinds": ["PAYMENT", "INVENTORY", "ADDRESS"],
  "receivedKinds": ["PAYMENT", "INVENTORY"],
  "missingKinds": ["ADDRESS"],
  "status": "INCOMPLETE"
}
~~~

This is an **illustrative business state model**, not a default payload automatically generated by the Aggregator. If a group times out with only two messages, the MessageGroupStore/timeout handler knows which two arrived, but retaining long-term history still requires an appropriate store/ledger.

### 17.3. Late Events After a Group Has Completed or Expired

If the ADDRESS event arrives after the INCOMPLETE report was published, options include:

- **Freeze:** keep the old report and store the late event for audit.
- **Reconciliation:** emit a new report revision with the additional info and notify downstream.
- **Reopen workflow:** only when permitted by the business, using controlled state transitions.

Never assign a new epoch to a late event and mix it into a group processing events from a completely different workflow. Late arrivals must be resolved by **business identity + epoch + eventId**, not by timestamp alone.

### 17.4. Persistent Store and Multi-Instance Deployments

When events land on different instances:

- Use broker partitioning/routing by group key so one instance owns each group; or
- Use a shared MessageGroupStore with an appropriate LockRegistry/transaction; or
- Use a durable workflow coordinator storing each part's state by groupKey.

A **shared store** does not replace locking when two instances try to release the same group simultaneously. You must test failover, duplicate arrivals, timeout races, and crash recovery.

## 18. Preventing Correlation Collisions and Data Leaks

An incorrect correlation key leads to two opposite failure modes:

1. **False split:** events from the same real workflow produce different keys, so the group never completes.
2. **False join:** events from unrelated workflows produce the same key, causing data mixing or wrong decisions.

### 18.1. Common Collision Patterns

| Scenario | Example | Prevention |
| --- | --- | --- |
| Missing tenant namespace | Two tenants both have ORD-101 | Include trusted tenant or properly authorized opaque group ID mapping |
| Missing epoch | One order has multiple runs | Include workflow epoch/operation instance |
| Delimiter ambiguity | a:b + c vs a + b:c | Regex restrictions, escaping, or length-prefix encoding |
| Wrong case canonicalization | Orders ab and AB are distinct entities | Normalize only if the domain explicitly declares case-insensitivity |
| Timestamp as key component | Same workflow received across two different hours | Use stable epoch, never now() |
| New UUID per event | Three independent events get three keys | Generate once and persist mapping, or compute deterministically |
| Looking up latest epoch | Old epoch redelivery gets tagged with new epoch | Look up epoch by persisted workflow instance |
| Truncating long IDs | Two different IDs share a prefix | Reject oversized IDs; never truncate silently |
| Unversioned HMAC rotation | Same workflow yields two digests | Versioned HMAC keys with migration/drain |

### 18.2. Do Not Treat Correlation ID as an Access Token

An unguessable ID does not replace authorization. If a user knows another tenant's groupKey, a status-query API must still verify the principal owns that order/tenant before returning details.

Never treat the mere existence of a group in `MessageGroupStore` as proof an actor is allowed to submit events into it. Validate messages **before adding them to a group**, because once a group contains a forged message, filtering only the output is too late.

### 18.3. Avoid Exposing Business IDs via Metrics

Metrics labeled with per-order correlationId create **massive cardinality**, waste resources, and expose order codes. Instead:

- Use bounded labels such as component, ingress adapter, event type, result status, and reason code.
- Keep correlation keys in logs/traces with proper access control, masking, and retention.
- Never put raw correlation keys in public URLs or client-facing error text if they contain business identities.
- If a public tracking ID is needed, issue a separate opaque ID with explicit mapping and authorization.

### 18.4. Protecting Against Oversized Keys or Group Flooding

If a client can spawn unlimited group IDs:

~~~text
request 1 -> random correlation A
request 2 -> random correlation B
...
request 1,000,000 -> random correlation ...
~~~

The Aggregator could retain millions of incomplete MessageGroups. Beyond authorization, enforce:

- Per-tenant/per-producer rate limits and quotas.
- Caps on size and number of active workflows.
- Key length and structure validation.
- Group timeouts/expiry and MessageGroupStore capacity limits.
- Ingress backpressure and group-age monitoring.
- Policy-driven expiration/cleanup rather than infinite retention to hide missing members.

## 19. Observability: Seeing Why Messages Fail to Join

In environments with many Routers and Integrations, correlation bugs often surface as **the Aggregator producing no output**. Counting exceptions alone is insufficient, because no exception is necessarily thrown when a group sits at 1 of 3 members.

| Metric | What to Observe |
| --- | --- |
| **correlation_ingress_accepted_total{source}** | Events accepted into the pipeline |
| **correlation_binding_rejected_total{reason}** | Events denied binding to an order/workflow |
| **correlation_key_created_total{version}** | Keys attached by version |
| **correlation_key_validation_failed_total{reason}** | Invalid keys |
| **correlation_group_active** | Number of waiting groups |
| **correlation_group_size{stage}** | Members per group, reported as a histogram |
| **correlation_group_age_seconds** | Age of incomplete groups |
| **correlation_group_completed_total{decision}** | Completed groups by decision |
| **correlation_group_timeout_total** | Groups that expired before gathering all members |
| **correlation_missing_part_total{kind}** | Required members missing at timeout |
| **correlation_duplicate_event_total{source}** | Redeliveries/deduplications observed |
| **correlation_identity_conflict_total** | Duplicate eventId with different payload/group |
| **correlation_late_event_total{reason}** | Messages arriving after workflow closed |
| **correlation_recovery_failed_total** | Unrecoverable error-flow failures |

Never attach unbounded-cardinality tenantId, orderRef, eventId, or groupKey to metrics. Use controlled logs/traces to investigate a specific group.

### 19.1. Structured Ingress Log

~~~json
{
  "stage": "verified-ingress",
  "eventId": "evt-payment-101",
  "eventType": "PAYMENT",
  "correlationSchema": "ordready:v1",
  "groupKeyRef": "opaque-or-redacted-reference",
  "bindingVerified": true,
  "outcome": "ACCEPTED"
}
~~~

This is an **illustrative log**, not a default Spring Integration output. Never log raw tokens, user passwords, payment credentials, or full payloads in exceptions/logs.

### 19.2. Log When a Group Is Missing a Member

~~~json
{
  "stage": "order-readiness-aggregation",
  "correlationSchema": "ordready:v1",
  "groupStatus": "INCOMPLETE",
  "expectedKinds": ["PAYMENT", "INVENTORY", "ADDRESS"],
  "receivedKinds": ["PAYMENT", "INVENTORY"],
  "missingKinds": ["ADDRESS"],
  "timeoutReason": "BUSINESS_DEADLINE_EXPIRED"
}
~~~

Such logs distinguish a missing ADDRESS from a parser failure, wrong tenant, duplicate PAYMENT, or stripped routing header.

### 19.3. Alerts Worth Having

1. Active groups climbing steadily while completed groups stay flat.
2. One partKind missing across most groups right after a deploy.
3. Both v1 and v2 correlation key versions appearing for un-drained workflows.
4. Same eventId appearing with different payload digests.
5. Abnormal spike in unauthorized/missing binding rates.
6. Completed groups receiving late events with previously unseen eventIds.
7. Shared MessageGroupStore errors or lock timeouts.
8. A READY workflow causing duplicate downstream effects after replay.
9. One tenant spawning an excessive number of incomplete groups in a short window.
10. Group fragmentation across instances due to inconsistent routing/partition keys.

## 20. Runbook: An Order Has Three Events Yet the Aggregator Produces Nothing

**Scenario:** operators see Payment, Inventory, and Address all logged, yet no OrderReadiness appears.

### Step 1 — Trace the Three Event IDs

Check whether the three logical events belong to the **same order and same workflow epoch**. Do not compare orderRef by eye alone since two tenants can share the same code.

### Step 2 — Compare Group Keys at Ingress

Values to cross-check:

~~~text
eventId             tenant       orderRef    epoch   groupKey
evt-p-1             tenant-a     ORD-101     7       ...:ORD-101:7
evt-i-1             tenant-a     ORD-101     7       ...:ORD-101:7
evt-a-1             tenant-a     ORD-101     8       ...:ORD-101:8
~~~

Here Address is in epoch 8, so the Aggregator rightly refuses to merge it into the epoch 7 group. Investigate the **binding resolver/epoch lookup**; never manually edit correlation IDs to “force completion.”

### Step 3 — Inspect Metadata Across Endpoints

Check whether a Transformer/Router/Splitter dropped **businessCorrelationKey** or replaced the technical **CORRELATION_ID**. Confirm the Aggregator uses the **intended strategy** (default header vs custom header).

### Step 4 — Check the Release Strategy

If a group has three messages but all are PAYMENT, it **does not have all three kinds**. Look for duplicate events, misconfigured eventType mappings, or a failing INVENTORY/ADDRESS source. Never change the release policy to group.size() >= 3 to paper over missing members.

### Step 5 — Check Timeouts and State

Is the group still ACTIVE, already EXPIRED, or COMPLETED? Is metadata still in the store? Did a reaper/timeout fire before all members arrived, or did a late arrival occur after the group closed?

### Step 6 — Check the Inbox and Ack Handling

An event marked SEEN in the inbox but never DISPATCHED due to a crash will not reach the Aggregator on its own. Inspect transaction/outbox state and recovery jobs rather than just counting producer sends.

### Step 7 — Choose a Controlled Remediation

- Replay the **exact logical eventId** if unprocessed and within the retry contract.
- Reconcile when external effect status is UNKNOWN.
- Quarantine invalid or unauthorized events.
- Start a correction or new workflow epoch when business rules allow.
- Never hand-edit group keys in the database without checking which side effects have already occurred.

### Step 8 — Verify After Recovery

Confirm the group contains the exact PAYMENT/INVENTORY/ADDRESS set, releases once per policy, emits OrderReadiness with the right tenant and epoch, and creates no duplicate downstream side effects.

## 21. What If the Payload Lacks a Natural Business Key?

Not every workflow has an orderRef present in every message. A form submission routed across three providers might only have an internal **requestId** created when the request begins.

In that case, use an **opaque correlation ID generated once**:

~~~mermaid
flowchart LR
    N["Client requests new workflow"] --> A["Ingress authenticates"]
    A --> C["Create workflow"]
    C --> P["Persist workflowId + mapping"]
    P --> F["Emit 3 branch commands"]
    F --> R["Branches preserve workflowId"]
    R --> G["Gather by workflowId"]
~~~

### 21.1. Initialization Flow

1. Receive a create-workflow command carrying a stable business idempotency key.
2. Authenticate the tenant/actor and verify permission to create workflows.
3. Check the registry by **clientOperationId** or logical request identity to see if a workflow was already created.
4. If not, generate a UUID/ULID **once**, persisting the mapping and initial state with a unique constraint.
5. Commit state/outbox before dispatching tasks to branches.
6. All branch commands/replies carry the same **workflowId** from verified internal sources.
7. If the create command is retried, return the **existing workflowId** instead of spawning a second group.

~~~text
create(requestKey=tenant-a:signup-815)
  -> persisted workflowId=019f...a12

retry create(requestKey=tenant-a:signup-815)
  -> same workflowId=019f...a12
~~~

Here correlation is no longer computed directly by concatenating orderRef, but by **looking up a trusted mapping** from business content to a durably allocated ID.

### 21.2. Internal Keys Differ from External Tracking Tokens

A public tracking token only lets a client query status after authorization; it should not be treated as proof of access rights. The same opaque identifier may be used if the security contract allows, though permissions must still be checked. For sensitive workflows, separating the public tracking token from the internal correlation key reduces topology leakage.

### 21.3. Deciding When to Generate New vs Reuse

| Input | Action |
| --- | --- |
| First-time workflow creation, no prior state | Generate ID once, persist mapping |
| Retry of the same logical create request | Return existing ID |
| Subsequent message in the workflow | Look up mapping / attach existing ID |
| Intentional start of a new workflow | Create new generation/epoch per business rules |
| Late message from an old generation | Keep old generation, classify as late |
| Mapping not found for an old event | Quarantine/reconcile; never guess a new ID |

This is a key case showing that **creating a correlation ID at ingress** can mean **creating it once for the workflow** and then **restoring it on subsequent ingress events**, rather than generating an ID per message.

## 22. Hands-On Exercise: Customer Onboarding Intake

Design a new onboarding workflow with three evaluation sources:

~~~text
ApplicationSubmitted
  -> IdentityCheckResult
  -> CreditCheckResult
  -> RiskCheckResult
  -> OnboardingDecision
~~~

Requirements specify that Identity, Credit, and Risk results may arrive out of order from independent services. Two tenants may share externalApplicationRef="APP-100". A request may be retried through the broker; a re-evaluation of the same application receives a new epoch.

### 22.1. Identity Design

Define and distinguish:

- trustedTenantId from principal/ACL.
- externalApplicationRef from verified content.
- assessmentEpoch from the workflow registry.
- eventId of each event from each producer.
- producerId to scope eventId uniqueness.
- correlation key for one logical assessment.
- clientRequestId solely for tracing/idempotency of the create command where appropriate.

Example key:

~~~text
assessment:v1:tenant-a:APP-100:epoch-2
~~~

**Requirement**: tenant-a/APP-100/epoch-2 must never share a group with tenant-b/APP-100/epoch-2, or tenant-a/APP-100/epoch-3.

### 22.2. Implementing Ingress

1. Build VerifiedActor or VerifiedProducerContext from the security layer.
2. Write AssessmentBindingResolver to verify the application belongs to the tenant and the epoch is valid.
3. Write AssessmentCorrelationKeys to deterministically generate keys per contract.
4. Build a fresh Spring Message with verified tenant, eventId, workflowEpoch, and businessCorrelationKey.
5. Do not copy client-supplied errorChannel, replyChannel, role, or correlationId.
6. If creating a workflow without a natural key, generate an opaque ID once, persist the mapping, and reuse it on retries.
7. Write unit tests comparing matching/non-matching keys and rejecting unknown applications.

### 22.3. Implementing Aggregation

1. Use an Aggregator with a CorrelationStrategy based on businessCorrelationKey.
2. Write a ReleaseStrategy requiring IDENTITY, CREDIT, and RISK.
3. Verify each kind has exactly one terminal outcome.
4. Build AssessmentDecision independent of arrival order.
5. If one kind is REJECTED, complete the group with MANUAL_REVIEW/REJECTED per domain policy.
6. If one kind is lost due to an outage, keep IN_PROGRESS and report INCOMPLETE once the business deadline expires.
7. Persist state durably with per-event deduplication and a late-arrival policy.

### 22.4. Test Dataset

| Case | Tenant | Application | Epoch | Event Kinds | Expected |
| --- | --- | --- | --- | --- | --- |
| A | tenant-a | APP-100 | 2 | CREDIT, IDENTITY, RISK | One decision in the right group |
| B | tenant-b | APP-100 | 2 | IDENTITY | Does not join A |
| C | tenant-a | APP-100 | 3 | CREDIT | Does not join epoch 2 |
| D | tenant-a | APP-100 | 2 | CREDIT duplicate eventId | Dedup or conflict, not counted as 2 members |
| E | tenant-a | APP-100 | 2 | RISK missing after deadline | INCOMPLETE, not SUCCESS |
| F | tenant-a | APP-100 | 2 | Spoofed correlationId header | Ignored/replaced at ingress |
| G | tenant-a | APP-100 | 2 | One denied event | Excluded from group prior to authorization |
| H | tenant-a | APP-100 | 2 | Late event after completion | Audit/discard/correction per policy |

### 22.5. Acceptance Criteria

| Criterion | Evidence |
| --- | --- |
| Ingress trust boundary | Unauthorized events do not enter the channel |
| Deterministic key or durable mapping | Retries of the same workflow produce the same key |
| Tenant/epoch namespace | Different tenants/epochs never mix |
| Header ownership | Only trusted metadata reaches the Aggregator |
| Custom CorrelationStrategy | Reads the verified key accurately |
| ReleaseStrategy | Checks the exact required outcome types |
| Duplicate protection | Duplicates do not alter completeness |
| Error handling | Timeouts/unknowns do not become business rejections |
| Idempotency | Replays produce no duplicate effects |
| Observability | Possible to diagnose why a group remains pending |

## 23. Self-Check Questions

1. How does content-based correlation differ from a message ID or trace ID?
2. Why does generating a new UUID for every event prevent the Aggregator from grouping them?
3. When should you generate an opaque workflow ID once and store a mapping?
4. Why can using orderRef alone mix data in a multi-tenant system?
5. What problem does workflow epoch solve?
6. Why must an old redelivery never be automatically tagged with the current epoch?
7. When ingress receives a client-supplied correlationId, how should it be handled?
8. Why is String.toUpperCase() not safe by default for every business ID?
9. What properties must a deterministic key-builder function have?
10. What does Spring Integration's CorrelationStrategy return, and can it be null?
11. How do CorrelationStrategy and ReleaseStrategy have two different responsibilities?
12. If all three messages are PAYMENT, should group.size() == 3 allow release?
13. Why is a businessCorrelationKey needed alongside the technical CORRELATION_ID when a Splitter is present?
14. Is a Gateway replyChannel the group key for three external events?
15. What happens to the Aggregator if a Filter drops a required event?
16. If MessageGroupStore is in-memory, how does a restart affect it?
17. Why does accurate correlation not guarantee exactly-once side effects?
18. How do you detect an eventId reused with a different payload?
19. Where can an event recorded in the inbox but not yet dispatched be lost?
20. Why should a correlation key not be used as an authorization token?

## 24. Checklist Before Taking Ingress Correlation to Production

- A clear **logical workflow/group boundary** is defined.
- eventId, messageId, traceId, requestId, correlationId, and business entity ID are kept distinct.
- Tenant and access rights to the business object are verified **before building the group key**.
- Epoch/workflow generation is durably stored and stable across redeliveries.
- Canonicalization rules, delimiter escaping, or unambiguous key structures are in place.
- Keys are versioned with a migration strategy when the algorithm changes.
- For opaque IDs, mappings are created **once** and idempotently.
- Client-supplied correlationId/replyChannel/errorChannel are never trusted.
- MessageBuilder rebuilds internal headers using an allowlist.
- The business correlation key is preserved across Router/Transformer/Splitter per the appropriate scope.
- Aggregator uses a correlationStrategy matching the group to be assembled.
- ReleaseStrategy checks the **exact set of members**, not merely message count.
- Per-event dedup/inbox exists before the Aggregator when redeliveries are possible.
- Idempotency records and dispatch use transactions/outbox/recovery to prevent event loss.
- Failure/denied outcomes are explicitly represented rather than silently dropped by a Filter.
- Timeouts, late arrivals, partial results, and group cleanup have a business contract.
- MessageGroupStore, LockRegistry, and partition routing fit multi-instance deployments.
- Downstream side effects have idempotency independent of group metadata.
- High-cardinality group keys or business IDs are never put in metric labels.
- Tests cover same group, different tenant, different epoch, duplicates, spoofed headers, timeouts, and restarts.
- Dashboards/runbooks exist to investigate pending groups, false splits, and false joins.

**Conclusion:** Creating a correlation ID at ingress means establishing a **trustworthy identity for a workflow**, not slapping a random string onto every message. Once ingress verifies the tenant, business object, and workflow epoch, consistent content-based logic attaches the **same group key** to related events, even when they arrive from different adapters and are redelivered. Spring Integration's Aggregator can use the default header or a custom CorrelationStrategy to group messages, while ReleaseStrategy decides when all members have arrived. Combining trust boundaries, canonical keys, deduplication, persistent state, timeouts, and idempotency prevents both **lost results from split groups** and **mixed data from merged groups**.

## References

- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): default correlation by CORRELATION_ID, CorrelationStrategy, ReleaseStrategy, MessageGroupStore, and timeouts.
- [Spring Integration API — CorrelationHandlerSpec](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html): configuring correlationStrategy, releaseStrategy, and groupTimeout with Java DSL.
- [Spring Integration API — AggregatorSpec](https://docs.spring.io/spring-integration/docs/6.2.6/api/org/springframework/integration/dsl/AggregatorSpec.html): outputProcessor and Aggregator configuration.
- [Spring Integration Reference — Splitter](https://docs.spring.io/spring-integration/reference/splitter.html): sequence/correlation headers when splitting messages and nested grouping.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): how replyChannel/request-reply differs from business group correlation.
- [Spring Integration Reference — TCP Message Correlation](https://docs.spring.io/spring-integration/reference/ip/correlation.html): example linking replies to requests via business data across adapters.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): ErrorMessage/errorChannel and synchronous/asynchronous errors.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, ExecutorChannel, QueueChannel, and dispatch boundaries.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): endpoint-level deduplication and limits before side effects.
- [Enterprise Integration Patterns — Correlation Identifier](https://www.enterpriseintegrationpatterns.com/patterns/messaging/CorrelationIdentifier.html): meaning of keys linking messages within a workflow.
