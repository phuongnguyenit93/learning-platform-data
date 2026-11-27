# Protocol- or Header-Based Router in Spring Integration Adapters

> **Chapter:** Design patterns  
> **Lesson:** Protocol- or header-based router  
> **Module context:** SPRING_INTEGRATION_ADAPTERS — connecting external systems via inbound/outbound adapters, gateways, pollers, and MessageChannels; integrating over File, SFTP, HTTP, JMS, AMQP/RabbitMQ, Kafka, and databases; managing message contracts, errors, and connection lifecycles.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain **Message Router** as an Enterprise Integration Pattern that selects processing branches based on rules, rather than an adapter automatically converting protocols.
2. Distinguish **protocol-based routing** (HTTP, SFTP, JMS, AMQP, Kafka, File, JDBC) from **header-based routing** (routeKey, tenant, eventType, destinationAlias).
3. Use **`HeaderValueRouter`**, method/`@Router` routers, and Java DSL inside an `IntegrationFlow` appropriately.
4. Design a **normalized message contract** decoupled from inbound-adapter-specific headers.
5. Control channel mappings, default routes, missing/unknown route errors, and auditable rejection paths.
6. Prevent **header spoofing, SSRF, unauthorized target access, cross-tenant misrouting**, and secret leakage across protocols.
7. Separate request–reply from one-way routing; understand channel boundaries, acks/offsets, transactions, retries, idempotency, and ordering.
8. Combine routers with transformers, splitters, gateways, adapters, recipient lists, and related patterns.
9. Build tests proving the right message reaches the right target without duplicates or data loss.

## 2. Context: One Source, Multiple Targets, and Multiple Protocols

A platform receives invoice events via HTTP webhooks, SFTP files, or Kafka. Depending on partner or domain rules, messages must reach:

- A REST API via an **HTTP outbound gateway**;
- An SFTP server via an **SFTP outbound adapter**;
- A JMS queue via a **JMS outbound adapter/gateway**;
- An AMQP exchange/queue via an **AMQP outbound adapter**;
- A Kafka topic via a **Kafka outbound adapter**;
- A file output directory, or a database via a **JDBC handler/adapter**.

~~~text
HTTP inbound ----\
SFTP inbound -----+--> Normalize --> RoutePolicy --> Router --> HTTP branch
Kafka inbound ----/                                  |-----> SFTP branch
                                                    |-----> JMS/AMQP branch
                                                    |-----> Kafka branch
                                                    |-----> File/JDBC branch
                                                    \-----> Rejected route
~~~

If each inbound flow uses ad-hoc if/else logic to pick adapters, rules scatter, security weakens, and metrics break. A **Router** separates “where does it go?” from “how is it sent?”.

**What a Router does:** inspects a route key or evaluates rules, selects the matching channel/recipient, and dispatches the message to the configured branch.

**What a Router does NOT do:** convert JSON to CSV, authenticate requests, open SFTP sessions, construct JMS messages, manage Kafka offsets, guarantee exactly-once, or provide distributed transactions.

## 3. Components in Spring Integration

| Component | Function | Caution |
|---|---|---|
| **Message** | Payload and headers | Headers arriving externally may be untrusted |
| **MessageChannel** | Connects endpoints/handlers | Sync, async, and queue channels carry different semantics |
| **MessageSource / poller** | Fetches File/SFTP/JDBC messages on schedule | Re-polling does not guarantee the exact same message |
| **Inbound adapter/gateway** | Receives from external systems | Ack/reply per source contract |
| **Transformer/enricher** | Normalizes payloads and headers | Separate raw headers from trusted route headers |
| **Router** | Picks one or more channels by router type | Never silently discard unknown routes |
| **Service activator** | Executes business logic | Side effects/idempotency |
| **Outbound adapter** | Sends one-way outward | Does not automatically return replies |
| **Outbound gateway** | Sends request and awaits response | Reply timeouts, error mapping |
| **ErrorMessage/errorChannel** | Propagates error details | Not a durable store by default |
| **DLQ/parking** | Holds failures for replay/triage | Event ID, owner, retention |
| **MessageStore** | Persists messages/state when configured | Does not create cross-system transactions |

**Message Router** is an EIP pattern; do not confuse it with **Filter** (may the message proceed?), **Transformer** (how does the message change shape?), **Gateway** (is there a response?), or **Adapter** (which protocol connects?).

## 4. What Is Protocol-Based Routing?

Protocol routing picks a branch by transport/adapter type:

~~~text
routeKey=HTTP  -> httpOutboundChannel   -> HTTP gateway
routeKey=SFTP  -> sftpOutboundChannel   -> SFTP adapter
routeKey=JMS   -> jmsOutboundChannel    -> JMS adapter
routeKey=AMQP  -> amqpOutboundChannel   -> AMQP adapter
routeKey=KAFKA -> kafkaOutboundChannel  -> Kafka adapter
routeKey=FILE  -> fileOutboundChannel   -> File adapter
routeKey=JDBC  -> jdbcOutboundChannel   -> JDBC handler
~~~

This is **selecting among preconfigured branches**, not an automatic protocol converter. Each branch requires its own serializers, target configurations, error handling, and transaction/ack semantics.

### Protocol is not the business destination

A system might send HTTP to ERP-A or ERP-B; two partners might both use SFTP with different directories and schemas. Therefore separate:

| Header | Example | Meaning |
|---|---|---|
| **targetProtocol** | HTTP | Adapter type |
| **destinationAlias** | billing-erp | Registered logical target |
| **eventType** | invoice.created | Business event type |
| **tenantId** | tenant-17 | Access/routing scope |
| **schemaVersion** | v3 | Message contract version |
| **routePolicyVersion** | 2026-11-r3 | Rule version |
| **businessEventId** | tenant-17:invoice-882:v3 | Idempotency/correlation |
| **replyRequired** | true | Request–reply vs. one-way |

Merely seeing HTTP in a header is **not sufficient** permission to send a payload to any arbitrary URL.

## 5. What Is Header-Based Routing?

Header routing selects channels using message metadata.

~~~yaml
# Illustrative internal contract, not Spring configuration YAML.
payload:
  invoiceId: INV-882
  amount: 120000
headers:
  businessEventId: tenant-17:INV-882:v3
  tenantId: tenant-17
  eventType: invoice.created
  schemaVersion: v3
  destinationAlias: billing-erp
  targetProtocol: HTTP
  routeKey: HTTP
  routePolicyVersion: 2026-11-r3
~~~

A **`HeaderValueRouter`** reads `routeKey` to choose a channel; the other headers guide policy checks and adapter handlers.

### Never trust raw source headers

HTTP headers, Kafka record headers, JMS properties, AMQP headers, SFTP filenames, or JDBC values can all be influenced by external senders. An HTTP client asserting `targetProtocol=JDBC` **must never automatically gain permission to write to a database**.

**Practice:** authenticate the source, validate payloads and business identity, look up the destination registry, verify authorization, and then **emit a trusted internal `routeKey`**. Never copy raw `targetProtocol` from clients and route on it directly.

### Single header or multiple headers?

- **One normalized `routeKey`:** `HeaderValueRouter` fits cleanly.
- **Tenant + eventType + destinationAlias + version:** compute an approved `routeKey` via a **policy resolver** prior to the router, or use a validating method/expression router.
- **Multiple targets must receive the same event:** use a Recipient List Router/fan-out tracking per-recipient state rather than forcing everything into one `routeKey`.

## 6. Normalizing Messages Before Routing

~~~mermaid
flowchart TD
    H["HTTP inbound"] --> V["Verify source + auth"]
    S["SFTP/File inbound"] --> V
    M["JMS/AMQP/Kafka inbound"] --> V
    D["JDBC poller"] --> V
    V --> N["Normalize canonical payload + trusted headers"]
    N --> P["Policy: tenant/event/destination authorization"]
    P --> R{"Router by routeKey"}
    R -->|"HTTP"| A["HTTP transform + gateway"]
    R -->|"SFTP"| B["File render + SFTP adapter"]
    R -->|"JMS/AMQP"| C["Message converter + broker adapter"]
    R -->|"KAFKA"| K["Record serializer + Kafka adapter"]
    R -->|"FILE/JDBC"| F["File/DB handler"]
    R -->|"UNKNOWN / DENIED"| X["Rejected + durable handling"]
~~~

### Internal header contract

| Header | Trusted source | Validation |
|---|---|---|
| businessEventId | Business origin and normalizer | Stable, non-blank, matches tenant |
| correlationId | Trusted trace context or ingress | Bounded length/format |
| sourceSystem | App-assigned adapter identity | Enum/registry |
| tenantId | Authenticated principal/tenant registry | Isolation/authorization |
| eventType | Payload/schema contract | Allowlist |
| schemaVersion | Schema validator | Supported versions |
| destinationAlias | Policy/registry | Exists and authorized |
| targetProtocol | Destination registry | Protocol enum |
| routeKey | Trusted classifier | Explicit mapping |
| replyRequired | Business/ingress contract | One-way vs. request–reply |
| deadlineAt | Business policy | Not expired |
| routePolicyVersion | Resolver | Audit/replay |

Workflow:

1. **Authenticate the source** via mTLS/tokens/SSH/broker principals/DB service accounts per protocol.
2. Parse and **validate schema, size, and media type**.
3. Determine tenant/eventId/operation; never accept unverified self-assertions.
4. Look up **`destinationAlias`** in the registry.
5. Verify permission for that destination and operation type.
6. Set **trusted `routeKey` and `routePolicyVersion`**.
7. Send to the router; send unknown/denied routes to rejection or parking.
8. Persist the decision when needed for audits or replay.

**`MessageHeaders` itself is not a security boundary.** The trust boundary sits at normalization, authentication, and authorization.

## 7. Architecture: One Router, Multiple Adapters

~~~mermaid
flowchart LR
    I["Normalized input"] --> R{"Protocol Router"}
    R -->|"HTTP"| H["httpChannel"]
    R -->|"SFTP"| S["sftpChannel"]
    R -->|"JMS"| J["jmsChannel"]
    R -->|"AMQP"| A["amqpChannel"]
    R -->|"KAFKA"| K["kafkaChannel"]
    R -->|"FILE"| F["fileChannel"]
    R -->|"JDBC"| D["jdbcChannel"]
    R -->|"UNKNOWN"| X["routingRejectedChannel"]
    H --> HG["HTTP gateway"]
    S --> SA["SFTP adapter"]
    J --> JA["JMS adapter"]
    A --> AA["AMQP adapter"]
    K --> KA["Kafka adapter"]
    F --> FA["File adapter"]
    D --> DA["JDBC handler"]
~~~

Each branch must define:

- Payload/serializer contracts.
- Destination aliases, configuration, and permissions.
- Errors/timeouts/retries/parking.
- One-way vs. request–reply.
- Idempotency, acknowledgments, and transactions.
- Metrics and state for replay.

## 8. Java DSL Example: Routing by Normalized Header

Illustrative Java DSL example; actual channels and outbound adapter endpoints must be configured separately.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;

@Configuration
public class ProtocolRouterFlow {

    @Bean
    IntegrationFlow protocolRoutingFlow() {
        return IntegrationFlow.from("normalizedInputChannel")
            .route(Message.class,
                message -> message.getHeaders().get("routeKey"),
                mapping -> mapping
                    .channelMapping("HTTP", "httpOutboundChannel")
                    .channelMapping("SFTP", "sftpOutboundChannel")
                    .channelMapping("JMS", "jmsOutboundChannel")
                    .channelMapping("AMQP", "amqpOutboundChannel")
                    .channelMapping("KAFKA", "kafkaOutboundChannel")
                    .channelMapping("FILE", "fileOutboundChannel")
                    .channelMapping("JDBC", "jdbcOutboundChannel")
                    .resolutionRequired(true))
            .get();
    }
}
~~~

- The router reads `routeKey` set by the normalizer.
- Channel mappings point to **registered channel names**, never raw URLs, topics, or paths chosen by the source.
- For unresolvable keys, prefer explicit failure/rejection routes rather than silent drops.
- Every outbound channel must have a properly registered and configured handler.
- The snippet omits full dependencies, gateways, converters, transactions, and error flows.

**Compatibility note:** DSL syntax/classpath details may vary across Spring Integration versions; verify exact APIs and test real wiring for your target version.

## 9. `@Router` When Combining Multiple Headers

A method router fits when decisions depend on tenant/eventType/destinationAlias. The example below uses a policy service returning only an approved channel name from an allowlist.

~~~java
import org.springframework.integration.annotation.Router;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class TrustedProtocolRouter {

    private final RoutingPolicyService routingPolicy;

    public TrustedProtocolRouter(RoutingPolicyService routingPolicy) {
        this.routingPolicy = routingPolicy;
    }

    @Router(inputChannel = "normalizedInputChannel")
    public String route(Message<?> message) {
        RoutingDecision decision = routingPolicy.evaluate(
                message.getHeaders().get("tenantId"),
                message.getHeaders().get("eventType"),
                message.getHeaders().get("destinationAlias"),
                message.getHeaders().get("routeKey")
        );

        if (!decision.isAllowed()) {
            return "routingRejectedChannel";
        }
        return decision.getApprovedChannelName();
    }

    // RoutingPolicyService and RoutingDecision are application-defined.
}
~~~

This is an **architectural illustration** without domain class definitions, so it is not standalone-runnable.

- The policy must verify tenant, permissions, and destination registry.
- Returned channel names must strictly come from **existing/approved channel names**.
- Unknown routes go to `routingRejectedChannel`; never return arbitrary names from untrusted headers.
- When using `@Router`, **do not simultaneously register another Java DSL router reading the same input channel** without intentionally designing subscription semantics.

## 10. `HeaderValueRouter` for Single-Header Routing

**`HeaderValueRouter`** selects channels from a single header and supports fixed mappings:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.router.HeaderValueRouter;

// Configuration snippet inside a @Configuration class.
@Bean
HeaderValueRouter protocolHeaderRouter() {
    HeaderValueRouter router = new HeaderValueRouter("routeKey");
    router.setChannelMapping("HTTP", "httpOutboundChannel");
    router.setChannelMapping("SFTP", "sftpOutboundChannel");
    router.setChannelMapping("JMS", "jmsOutboundChannel");
    router.setChannelMapping("AMQP", "amqpOutboundChannel");
    router.setChannelMapping("KAFKA", "kafkaOutboundChannel");
    router.setChannelMapping("FILE", "fileOutboundChannel");
    router.setChannelMapping("JDBC", "jdbcOutboundChannel");
    router.setResolutionRequired(true);
    return router;
}
~~~

Defining the router bean alone **is not enough**; wire it into an endpoint/`IntegrationFlow`. Ensure `routeKey` is normalized (type, casing, whitespace) and mapped channels have subscribers.

| Problem | Choice |
|---|---|
| Single trusted `routeKey`, stable mapping | `HeaderValueRouter` |
| Multiple headers and authorization | Policy service + `@Router`/DSL |
| Routing based on payload fields | Content-Based Router |
| One event must go to multiple targets | Recipient List Router / fan-out |
| Sequential multi-step itinerary | Routing slip / workflow |
| No authorized route exists | Rejected/parking, never default discard |

## 11. Distinguishing Router, Filter, Transformer, Gateway, and Adapter

These patterns often sit on the same flow, yet never lump them all under “router.”

| Pattern/component | Question it solves | Example |
|---|---|---|
| **Filter** | Should the message proceed? | Off-contract files blocked from business flow |
| **Router** | Which branch should the message take? | Send to HTTP, SFTP, or Kafka |
| **Transformer** | How should payload/metadata change form? | Canonical JSON to CSV |
| **Header enricher** | Which trusted metadata to add? | `routeKey`, `destinationAlias`, correlation |
| **Splitter** | Split one message into many? | One file containing multiple orders |
| **Aggregator** | Combine results from multiple messages? | Consolidating per-file/per-recipient outcomes |
| **Bridge** | Connect two channels/segments unchanged? | Linking flow segments |
| **Outbound adapter** | One-way send to external system? | File, SFTP, Kafka publish |
| **Outbound gateway** | Send request and await reply? | HTTP request–reply |
| **Service activator** | Run business code? | Save to database or call policy service |

For example, **HTTP inbound → SFTP outbound** needs several steps: HTTP auth, parsing/validation, routing, partner-contract file rendering, filename selection, temp upload, publish/rename, status recording, and appropriate response. The Router **does not** perform those other steps itself.

## 12. Channel Mapping and Resolution: Where Do Unknown Keys Go?

A router can encounter:

- Missing `routeKey`;
- Non-String header type, non-canonical casing, or whitespace;
- Syntactically valid `routeKey` unauthorized for the tenant;
- Unmapped key;
- Unregistered channel bean;
- Channel without subscribers;
- Message delivered to channel whose payload mismatches the serializer;
- Target adapter returning I/O errors or timeouts.

### Error matrix

| Error | Responsible layer | Action |
|---|---|---|
| Missing `routeKey` | Message contract/normalizer | Reject with reason `MISSING_ROUTE` |
| Unsupported `targetProtocol` | Registry/policy | Reject; never guess a business destination |
| Unauthorized destination | Authorization | Security audit; do not route |
| Mapped channel not found | Deployment/config | Fail explicitly + alert |
| Channel has no subscriber | Topology/runtime | Alert, fail tests, preserve message |
| Incompatible payload/schema | Transformer/contract | Quarantine or transform properly |
| Remote connection timeout | Outbound adapter | Retry/recovery per contract |
| Request–reply timeout | Gateway | `OUTCOME_UNKNOWN` if side effects exist |

**Never default unknown routes to an HTTP partner or `nullChannel`** for business messages that must complete.

### How should a default route be used?

Some routers let you configure **`defaultOutputChannel`** and control resolution-failure handling. The best default target is usually a monitored **`routingRejectedChannel`**. Pushing rejections into an in-memory `DirectChannel` and assuming durability still risks losing messages on crash.

Policy example:

~~~yaml
# Pseudocode illustrating policy, not direct Spring Integration configuration.
route_resolution:
  allowed_keys: [HTTP, SFTP, JMS, AMQP, KAFKA, FILE, JDBC]
  unknown_route:
    action: REJECT
    reason_code: UNSUPPORTED_ROUTE
    destination: routingRejectedChannel
  unauthorized:
    action: ESCALATE
    reason_code: ROUTE_NOT_AUTHORIZED
  logging:
    include_business_event_id: true
    include_credentials: false
~~~

### Never use `nullChannel` to hide routing errors

**`NullChannel`** intentionally discards messages. It fits branches explicitly proven unnecessary, whereas unresolved route keys, mapping bugs, or missing destinations are **unresolved errors**. Use rejected/parking flows, exception/error channels, and durable state per source.

## 13. Security in Header-Based Routing

### 13.1. Header spoofing

~~~text
HTTP client sends:
   X-Target-Protocol: JDBC
   X-Destination-Alias: finance-write
~~~

If the app reads these values directly to pick a JDBC handler, the client can perform unauthorized writes. You must:

1. Authenticate the source and resolve principal/tenant;
2. Parse valid business fields;
3. Resolve destinations from a system-controlled registry;
4. Verify the tenant is authorized for that operation;
5. Generate trusted `routeKey` **after** authorization;
6. Re-verify permissions inside target handlers for sensitive operations.

### 13.2. SSRF in dynamic HTTP routing

If an outbound HTTP handler reads arbitrary URLs from upstream-controlled headers, senders can probe internal networks or metadata services. Use **`destinationAlias` → allowlisted URL registry**, restricting schemes/hosts/ports/redirects and egress policies.

### 13.3. Path/topic/destination injection

A tampered header can cause:

- SFTP writing into a remote directory outside the tenant's scope;
- File outbound writing outside root directories;
- JMS/AMQP pushing messages into another party's queue or exchange;
- Kafka publishing to unauthorized topics;
- JDBC interpolating untrusted strings into table names/SQL.

**Enforce allowlists, ACLs, and adapter-level checks.** Never interpolate user input into SQL identifiers, URLs, paths, or topics without strict policy enforcement.

### 13.4. Header propagation and secrets

Never forward all inbound HTTP/JMS/Kafka headers to external systems. Headers can contain bearer tokens, cookies, source IPs, `replyChannel`/`errorChannel` references, or sensitive content.

**Select only headers belonging to the outbound contract**; forward safe correlation IDs without leaking credentials or internal routing metadata.

### 13.5. Tenant routing must never trust self-declared `tenantId`

If a payload carries `tenantId=T2` while the authenticated principal only holds rights to `T1`, reject before the router. Never “route to T2 because the message header says so,” even if T2 maps to a valid channel.

## 14. Multi-Dimensional Routing: `tenant` + `eventType` + `protocol`

In production, protocol is only one dimension; target selection typically combines multiple dimensions.

| Tenant | Event | Destination alias | Protocol | Channel |
|---|---|---|---|---|
| Tenant A | invoice.created | ERP-X | HTTP | httpOutboundChannel |
| Tenant A | invoice.exported | Archive-X | SFTP | sftpOutboundChannel |
| Tenant A | order.changed | Fulfillment-Q | JMS | jmsOutboundChannel |
| Tenant B | order.changed | Broker-Y | AMQP | amqpOutboundChannel |
| Tenant B | shipment.event | Analytics-K | KAFKA | kafkaOutboundChannel |
| Tenant C | report.ready | Archive-Local | FILE | fileOutboundChannel |
| Tenant C | reconciliation | Internal-DB | JDBC | jdbcOutboundChannel |

These rows are illustrative examples, not rules of a real system.

### Two-tier router

~~~text
Ingress
  -> Normalize + authorize
  -> Business destination resolver(tenant,eventType,version)
  -> Protocol router(targetProtocol)
  -> Adapter handler
~~~

### Single-tier router

~~~text
Ingress
  -> Normalize + authorize
  -> RoutingPolicyService
  -> approvedChannelName
  -> Adapter handler
~~~

Two tiers help **reuse protocol branches** and separate business policy from transport. One tier centralizes decisions. Either way, maintain **`policyVersion`, rejected routes, and audits**.

## 15. Payload Contracts and Serializers per Protocol

One canonical business DTO is not automatically compatible with every outbound adapter.

| Branch | Expected adapter payload | Critical metadata |
|---|---|---|
| HTTP | JSON/XML/bytes per API contract | Method, path alias, content-type, idempotency key |
| SFTP | File content, `byte[]`/stream per adapter | Remote temp/final filename, checksum |
| JMS | Converted JMS message payload | Correlation, destination alias, delivery mode |
| AMQP | Encoded message body per converter | Exchange/routing key, message ID, confirm |
| Kafka | Schema-serialized key/value | Topic alias, record key, partition policy |
| File | Text/binary/document | Filename, directory, publish strategy |
| JDBC | Params/DTO for SQL operations | Transaction boundary, business key |

### Example post-router schema transformation

~~~text
CanonicalInvoiceV3
    -> Router: SFTP
    -> RenderPartnerCsvV2
    -> Produce manifest + checksum
    -> SFTP outbound adapter
~~~

The router picks the **SFTP branch**; it does not convert InvoiceV3 to CSV itself. Select transformers per destination contract rather than assuming “all SFTP targets share one CSV schema.”

### Headers assist, never replace validation

Header `contentType=application/json` does not prove valid JSON payload. Header `schemaVersion=v3` does not prove fields match v3. Parse/validate and handle errors rather than pushing invalid payloads into adapters to retry endlessly.

## 16. `DirectChannel`, `ExecutorChannel`, and `QueueChannel` at Target Branches

The `MessageChannel` type governs timing and failure semantics when the router dispatches a message.

### `DirectChannel`

Typically dispatches subscribers **synchronously** on the sender thread. If an outbound handler throws and exceptions propagate, upstream receives the exception in the same call stack.

An HTTP inbound gateway using `DirectChannel` can remain blocked while outbound HTTP retries. Configure connect/read timeouts and overall deadlines.

### `ExecutorChannel`

Offloads messages to an executor for asynchronous processing. The sender returns from `send` before the target handler completes.

**A successful send to `ExecutorChannel` does not prove the remote adapter succeeded**. You need async error flows and durable handoffs if crash recovery is required.

### `QueueChannel`

Durability depends on `MessageStore` and transaction/consumer semantics. Pollers pulling messages from the queue may require rollback/redelivery design if downstream fails.

| Channel | What does `send` success mean? | If target adapter fails |
|---|---|---|
| `DirectChannel` | Subscriber likely ran synchronously | Exception can propagate |
| `ExecutorChannel` | Work handed off/queued to executor | Async error path must handle separately |
| `QueueChannel` | Message queued per configuration | Retry/rollback/persistence must be defined |
| `PublishSubscribeChannel` | Dispatched to subscribers per mode | Explicit fan-out success/failure policy |

**A router is not a durable broker.** Define source ack boundaries, transactions, and persistence for each topology.

## 17. Single Branch or Multi-Target Fan-Out?

A protocol router usually selects **one destination**. Yet some domains require sending **the same event** to multiple recipients:

~~~text
invoice.created
    -> HTTP ERP
    -> Kafka analytics
    -> SFTP audit export
~~~

This calls for a Recipient List Router, `PublishSubscribeChannel`, or proper fan-out orchestration.

### Fan-out does not mean atomic delivery

If dispatching to three targets yields:

~~~text
eventId=invoice-882-v3
  HTTP recipient: DONE
  Kafka recipient: DONE
  SFTP recipient: RETRY_WAIT
~~~

Retrying the **entire fan-out** would re-send HTTP/Kafka that already succeeded. Track **per-recipient status** and retry SFTP individually using idempotency/transactional outboxes.

| Pattern | Target count | When appropriate |
|---|---|---|
| `HeaderValueRouter` | Usually one by key | Selecting protocol |
| Content-Based Router | Usually one by condition | Choosing by business content |
| Recipient List Router | Multiple by list | Sending to a defined recipient set |
| Publish–Subscribe | Broadcast per topology | Multi-subscriber eventing |
| Routing Slip | Ordered multi-step path | Sequential workflow steps |
| Scatter–Gather | Multiple requests, aggregate replies | Querying multiple backends |

### Do not confuse multiple subscribers on a channel with ordered routing

Attaching multiple subscribers to a `DirectChannel` does not mean every message reaches **all** of them. For fan-out, use components built for multi-recipient distribution and test failure semantics. Likewise, routing to a `PublishSubscribeChannel` does not guarantee all subscribers committed business logic.

## 18. Request–Reply vs. One-Way Routing

This is a frequent mistake when mixing protocols.

### One-way

Inbound event received via Kafka → written as an SFTP file. Routing to an SFTP outbound adapter creates a **one-way send**. It has no reply contract like an HTTP outbound gateway.

### Request–reply

HTTP inbound gateway receives request → router selects HTTP/JMS gateway → receives response → returns to caller.

If the router selects a branch **returning no reply** while the caller waits, the gateway times out. A router never turns a one-way adapter into request–reply.

~~~mermaid
sequenceDiagram
    participant C as HTTP caller
    participant I as Inbound gateway
    participant R as Router
    participant H as HTTP outbound gateway
    C->>I: Request + correlation
    I->>R: Normalized message, reply required
    R->>H: Approved route HTTP
    H-->>I: Partner response
    I-->>C: Reply per contract
~~~

### Mandatory checks

- Does the selected branch have an appropriate **reply contract**?
- Does the reply preserve correlation to the original request?
- Are timeouts/deadlines sufficient for the whole flow?
- Do downstream exceptions map cleanly back to the caller?
- If a branch is asynchronous, who owns the job ID/accepted response?
- Returning accepted/202 when a job is persisted **differs from** claiming the operation completed.

### `replyChannel`/`errorChannel` headers

Spring Integration uses `replyChannel` and `errorChannel` headers for internal flows. Never copy those references across untrusted boundaries or ship them arbitrarily to external brokers. Serialized channel headers have no meaning to consumers in another process.

## 19. Error Handling: Routing Failure vs. Delivery Failure

Separate two failure classes:

**Routing failure:** missing `routeKey`, invalid protocol, unauthorized target, missing channel mapping.

**Delivery/handler failure:** valid route yet HTTP 503, SFTP timeout, JMS broker unavailable, Kafka publish failure, or DB deadlock.

~~~mermaid
flowchart TD
    M["Normalized message"] --> V["Validate routing policy"]
    V --> Q{"Valid route?"}
    Q -->|"No"| X["ROUTING_REJECTED: reason + audit"]
    Q -->|"Yes"| R{"Protocol router"}
    R --> H["Adapter handler"]
    H --> O{"Delivery succeeded?"}
    O -->|"Yes"| D["Record DONE / reply"]
    O -->|"Transient"| T["Bounded retry + backoff"]
    T --> H
    O -->|"Permanent"| P["Quarantine / owner triage"]
    O -->|"Unknown outcome"| U["Query/reconcile / PARKED"]
    T -->|"Exhausted"| E["Durable delayed retry / DLQ"]
    X --> F["Durable reject handling"]
    P --> F
    U --> F
    E --> F
~~~

An `ErrorMessage`/`errorChannel` can be configured to observe or route errors. **`ErrorChannel` is not a DLQ by default**, and **`NullChannel`** is not recovery for invalid routes.

### Suggested error contract

| Field | Meaning |
|---|---|
| businessEventId | Stable business key |
| correlationId | Links ingress/router/adapter |
| sourceSystem | Authenticated origin |
| routeKey/destinationAlias | Approved target decision |
| routePolicyVersion | Mapping version |
| failureStage | `NORMALIZE`, `ROUTE`, `TRANSFORM`, `DELIVER`, `ACK` |
| errorCategory | `ROUTE_INVALID`, `AUTH_DENIED`, `TRANSIENT`, `PERMANENT`, `OUTCOME_UNKNOWN` |
| retryCount | Scoped attempt count |
| payloadReference | Reference to durable data store |
| finalOutcome | `DONE`, `REJECTED`, `PARKED`, `DLQ` |
| occurredAt | Error timestamp |
| owner | Owning responder team |

Never write secrets, PII, or raw payloads into failure logs unnecessarily. If persisted for redrive, protect with access controls and retention.

## 20. Retry at the Router or at the Adapter Handler?

A router **selects a route**; handlers then execute external I/O. On transient handler failures, retries should normally wrap **the external-I/O handler** rather than restarting from the top of the flow.

~~~text
Inbound -> Normalize -> Router -> HTTP gateway [retry advice] -> Save status
                           |
                           +-> SFTP adapter [matching retry policy]
~~~

Retrying the whole flow from Normalize risks:

- Producing a different route decision if the registry changed;
- Re-running side-effecting validation/enrichment;
- Re-sending to targets that already succeeded;
- Losing stable traces/correlation;
- Creating duplicates when remote committed yet the response was lost.

### `RetryPolicy`, `BackOffPolicy`, and `RequestHandlerRetryAdvice`

- **`RetryPolicy`:** which exceptions/conditions retry, and max attempts.
- **`BackOffPolicy`:** wait intervals between attempts; does not decide retryability.
- **`RequestHandlerRetryAdvice`:** wraps invocations of the attached handler.
- **`RecoveryCallback`:** handles exhaustion; returning normally can affect ack/commit semantics.
- **Delayed retry:** long retries persisted durably via brokers/job stores.

**Never assume a Kafka/JMS adapter re-acks or an SFTP poller re-fetches files merely because a handler has retry advice.**

## 21. Transactions, Acknowledgments, and Idempotency

Routing across protocols rarely shares one transaction.

### Three boundaries

1. **Source delivery:** File/SFTP scan, JMS/AMQP delivery, Kafka record/offset, HTTP request, or JDBC polled row.
2. **Routing/processing:** normalize, policy, channel dispatch, and handler.
3. **Destination side effect:** remote HTTP order, file transfer, broker publish, or DB transaction.

Acking a source early before downstream finishes risks **lost work**. Conversely, failing to ack after remote commit causes **duplicates** on source redelivery.

### Stable business event ID

~~~text
businessEventId = tenant-17:invoice-882:v3
routePolicyVersion = 2026-11-r3
destinationAlias = billing-erp

Attempt 1:
    HTTP POST creates invoice successfully, yet response is lost.

Attempt 2:
    Reuse the exact idempotency key or query status before retrying.
~~~

**Routers do not automatically create idempotency**. You need inboxes/dedupe, partner-contract idempotency keys, unique business keys, or reconciliation.

### Outbox/inbox

- **Inbox:** records business event IDs/outcomes so consumers handle duplicates safely.
- **Transactional outbox:** saves domain state and outbound event intent in one DB transaction; publisher retries safely.
- **Routing decision state:** persists targets/`routePolicyVersion` for messages needing retries or replays.
- **Recipient state:** in fan-out, tracks `DONE`/`RETRY_WAIT`/`PARKED` per destination.

### Route decisions during replay

If the destination registry changes between the first attempt and replay, messages could unexpectedly go to a different target. Define explicitly:

- **Pinned decision:** keeps `routeKey`, `destinationAlias`, and `policyVersion` from the initial decision and replays to the same target (usually safer for finance/auditing).
- **Re-evaluate decision:** recomputes routes under new policies only when business contracts allow with migration/auditing.
- **Manual override:** lets authorized admins switch targets with approvals, reasons, and idempotency checks.

Never automatically re-evaluate every pending message merely because a router method updated.

## 22. File and SFTP: Routers Do Not Manage File State

File inbound and SFTP inbound typically use **pollers** and filters. A routing scenario might look like:

~~~text
SFTP inbound:
    invoices/*.ready -> parse InvoiceV3
    reports/*.ready  -> parse ReportV2
        -> normalized event
        -> protocol router
~~~

### File/SFTP inbound

- **File ready:** source writes temp files then atomically renames or drops manifests. Never parse uploading files.
- **File filters:** accept-once/local/remote metadata do not guarantee once-only business processing.
- **Parsers:** validate schemas, encodings, and checksums before routing.
- **Splitters:** multi-record files need stable per-record eventIds or stable file+record keys.
- **Errors:** invalid files/records go to quarantine; unknown routes never go to `NullChannel`.
- **Pollers:** subsequent polls may not re-see already-marked/moved files.
- **Recovery:** downstream failures need durable message state or parking for replay.

### SFTP/File outbound

The router picks the SFTP/File branch, yet handlers control publishing mechanics and transfer state.

| Attribute | Example | Protection |
|---|---|---|
| Destination alias | archive-partner-A | Allowlist; never raw hostnames |
| Directory | /outgoing/invoices | Root allowlist/path validation |
| Temp filename | INV-882.v3.part | Stable ID, collision avoidance |
| Final filename | INV-882.v3.csv | Overwrite rules |
| Format | CSV v2 | Contract, charset |
| Checksum/manifest | SHA-256 | Transfer verification |
| Publish step | Rename/ready marker | Never assume atomic across filesystems |
| Recovery | RETRY_WAIT/PARKED | Never delete source automatically |

If upload succeeds yet the response drops, resending may overwrite or create a duplicate file. **Reconcile remote state** before retrying; picking the right channel never proves transfer completion.

## 23. HTTP: Picking the Right Endpoint and Preserving Request–Reply

HTTP inbound gateways typically handle request–reply. Outbound gateways call target APIs; distinguish from one-way Kafka/SFTP.

~~~text
Normalized event:
  tenantId=tenant-17
  eventType=invoice.created
  destinationAlias=billing-erp
  routeKey=HTTP

Registry:
  billing-erp -> approved HTTPS endpoint

HTTP outbound handler:
  InvoiceV3 -> ERP InvoiceRequestV2
  POST with stable Idempotency-Key
~~~

### Things the router does NOT guarantee

- URL/method/path allowlisting against SSRF;
- Proper authentication/tokens/mTLS;
- Request/response schema validity;
- Connect/read timeouts and total deadlines;
- Backoff/rate limits/circuit breakers on 429/503;
- Not pointlessly retrying 400/401/403;
- Recognizing POST timeouts as **`OUTCOME_UNKNOWN`**;
- Reply correlation and status mapping back to callers;
- Stripping Authorization/cookies so they never leak to partners.

### Valid route yet delivery fails

The router picks the HTTP channel and the partner returns 503. No need to loop back to the start of the flow and re-route endlessly. Retry at the **HTTP handler** with `maxAttempts`/backoff/budgets, then move to delayed retries with pinned `destinationAlias` on prolonged outages.

If the remote created an order and lost the response, use **idempotency contracts or status queries**. Never treat an exception as proof of no commit.

## 24. JMS and AMQP: Broker Routing Differs from Spring Integration Routing

A **Spring Integration router** picks an **internal `MessageChannel`**. JMS queues and AMQP exchanges/routing keys are **broker addresses** used by outbound adapters.

### JMS inbound/outbound

Typical sequence:

1. JMS listener receives delivery.
2. Inbound adapter converts to Spring Message.
3. Normalizer sets trusted eventId/headers.
4. Router selects channel.
5. Target handler executes operation.
6. Container handles ack/commit/rollback per config and outcome.

If an `ErrorMessage` is swallowed and the container acks before outbound completes, messages can be lost. JMS broker redelivery **is not** handler retry.

### AMQP outbound

~~~text
Spring Integration:
    routeKey=AMQP
      -> amqpOutboundChannel
      -> AMQP outbound adapter

AMQP broker:
    exchange=approved-exchange
    routingKey=approved-broker-routing-key
~~~

Upstream clients must never arbitrarily pick broker exchanges/routingKeys via headers. Use **`destinationAlias` → allowlisted registry** and producer permissions.

### Publisher confirms, retries, and duplicates

- A publish may reach the broker while the confirm is lost → **unknown outcome**.
- Retrying publishes can create duplicates.
- Publisher confirms do not prove consumers completed business logic.
- Consumers need stable eventIds and dedup.
- When events originate from DB transactions, consider transactional outboxes.
- Continuous immediate requeue creates AMQP hot loops; use delayed retries/DLQs per contract.

If a handler runs 4 attempts and the broker redelivers 5 times, that equals **20 handler invocations** before counting HTTP client retries.

## 25. Kafka: Selecting a Topic Is Not Managing Offsets

Kafka has topics, partitions, record keys, consumer groups, and offsets. Spring Integration routers still only select **internal channels**.

### Kafka outbound

~~~text
Normalized event:
  eventType=shipment.updated
  destinationAlias=analytics-kafka
  routeKey=KAFKA

Kafka handler:
  topic alias -> allowlisted topic
  key = stable aggregate ID
  value = serialized per schema contract
  headers = whitelisted correlation metadata
~~~

The router does not choose partitions, serializers, or producer guarantees; the adapter/client owns those properties.

### Kafka inbound

An inbound record carries Kafka-specific headers. The normalizer must translate them into trusted **`businessEventId`/`eventType`/`schemaVersion`/`tenantId`** instead of forcing every downstream protocol to understand Kafka headers.

**Offset commits** belong to the consumer/container. If a router dispatches to an `ExecutorChannel` and offsets commit early before outbound finishes, business events risk getting lost.

### Ordering

~~~text
Partition P:
  offset 100: order-created
  offset 101: order-updated
  offset 102: order-cancelled
~~~

If offset 100 hits a slow HTTP retry while 101 speeds down another Kafka branch, **business ordering** flips. Protect via aggregate/version guards or suitable topologies. Retry topics/DLTs can also alter order.

Kafka-scoped exactly-once never automatically spans HTTP partners or independent DB transactions.

## 26. JDBC: Routing to a Database Does Not Grant Arbitrary SQL

`RouteKey=JDBC` only picks the DB branch. Handlers must execute **governed operations**:

- Never read raw table names or SQL strings from client-supplied headers.
- Use approved **`operationAlias`** names, e.g., `markReconciled` or `saveInvoiceStatus`.
- Enforce tenant/business permissions and DB service-account scope.
- Use parameter binding for values with explicit transaction boundaries.
- Enforce unique business keys and idempotency.
- Retry deadlocks/serialization conflicts in fresh transactions as needed.
- JDBC inbound polling must manage row leases/states across restarts.

### JDBC inbound polling

~~~text
NEW -> CLAIMED -> PROCESSING -> DONE
                  |
                  +-> RETRY_WAIT -> PROCESSING
                  |
                  +-> PARKED
~~~

If a poller claims a row and a downstream HTTP handler fails, the row won't magically revert to `NEW` just because the router finished. Implement atomic claims, `leaseOwner`/`leaseUntil`, `attemptCount`/`nextAttemptAt`, and recovery policies.

## 27. Route Registry, Policy Versioning, and Replay

With many destinations, a **governed destination registry** is far better than hardcoding business aliases across dozens of routers.

### Sample registry record

~~~json
{
  "destinationAlias": "billing-erp",
  "targetProtocol": "HTTP",
  "channelName": "httpOutboundChannel",
  "allowedTenants": ["tenant-17"],
  "allowedEventTypes": ["invoice.created", "invoice.updated"],
  "schemaContract": "erp-invoice-v2",
  "enabled": true,
  "routingPolicyVersion": "2026-11-r3",
  "owner": "integration-platform",
  "sloClass": "business-critical"
}
~~~

This is a suggested schema, not a built-in Spring Integration configuration format.

### Governance rules

1. Only authorized principals may edit the registry.
2. `channelName`/adapter targets come from a testable **allowlist**.
3. Never build mappings from raw user-supplied URLs/paths/topics/queues.
4. Validate destinations before enabling.
5. Record **`routePolicyVersion`** on every decision for replay/auditing.
6. Support disabling a destination during incidents/open circuits.
7. Use canaries/rollbacks for tenant/`eventType` route changes.
8. Never silently redirect retrying messages without business approval.
9. Policy changes require regression tests for tenant isolation and protocol boundaries.
10. When the registry is unavailable, default to **fail safe**/parking rather than bypassing authorization.

### Routing decision record

~~~json
{
  "businessEventId": "tenant-17:INV-882:v3",
  "tenantId": "tenant-17",
  "eventType": "invoice.created",
  "destinationAlias": "billing-erp",
  "targetProtocol": "HTTP",
  "routeKey": "HTTP",
  "routePolicyVersion": "2026-11-r3",
  "decision": "APPROVED",
  "deliveryState": "RETRY_WAIT",
  "attemptCountPersisted": 3,
  "nextAttemptAt": "2026-11-23T10:30:00Z",
  "deadlineAt": "2026-11-24T00:00:00Z",
  "payloadReference": "secure-message-store/INV-882-v3"
}
~~~

### Pin or re-evaluate on replay?

- **Pinned route:** keeps initial `destinationAlias`/`targetProtocol`/`policyVersion`; usually safer for auditing and financial flows.
- **Re-evaluate:** runs updated policy only when business contracts allow redirection, with migration and reconciliation.
- **Manual override:** authorized operator picks a new target, logs approval/reason, and checks both old and new targets for duplicate effects.

Never redirect pending messages to another partner automatically simply because the registry changed between retries.

## 28. Observability: Separating Route Success from Delivery Success

**A successfully routed message** only proves it reached a topology channel. If that channel is `ExecutorChannel` or `QueueChannel`, external work may not have started yet.

| Metric | Definition | Purpose |
|---|---|---|
| **`route_decisions_total`** | Decisions by `routeKey`/flow | Protocol breakdown |
| **`route_rejected_total`** | Messages lacking valid routes | Catch policy/config bugs |
| **`route_unauthorized_total`** | Permission-denied routes | Security signal |
| **`route_resolution_errors_total`** | Unresolved mappings/channels | Catch deployment regressions |
| **`route_decision_latency_seconds`** | Policy resolver latency | Measure registry bottlenecks |
| **`delivery_attempts_total`** | Outbound send attempts | Separate attempts from message count |
| **`delivery_success_total`** | Target business deliveries completed | Avoid confusing with channel sends |
| **`delivery_exhausted_total`** | Deliveries exhausting retry budgets | Spot parking needs |
| **`unknown_outcome_total`** | Remote may have committed, response lost | Timely reconciliation |
| **`parked_backlog_age_seconds`** | Age of unresolved parked items | SLA/operational debt |
| **`broker_redelivery_total`** | Source/broker redeliveries | Separate from handler retries |
| **`duplicate_prevented_total`** | Duplicates caught by dedupe | Replay safety |
| **`destination_latency_seconds`** | P50/P95/P99 per protocol/alias | Bottleneck detection |
| **`queue_lag / queue_depth`** | Queued items per branch | Backpressure |
| **`incorrect_route_incidents_total`** | Verified misrouted incidents | Policy quality |

### Structured logging at the routing boundary

What to log:

- `businessEventId`, `correlationId`;
- Authenticated `sourceSystem`/tenant;
- `eventType`/`schemaVersion`;
- `destinationAlias`, `targetProtocol`, `routeKey`;
- `routePolicyVersion`, decision reason;
- `failureStage`/`errorCategory`;
- Terminal outcome and acknowledgment outcome when known;
- Elapsed time and attempt count.

Never log raw Authorization headers, bearer tokens, SSH keys, broker credentials, or full customer payloads.

### Cardinality

Never use `eventId`/`orderId`/`correlationId` as metric labels due to high cardinality. Keep those in logs/traces; keep metric labels to `routeKey`, `endpointAlias`, `errorCategory`, `outcome`, and bounded `eventType` categories.

### The misleading “100% route success” alert

If dashboards measure only `message.send` into `QueueChannel`, they can report 100% while consumers are stopped or outbound adapters return 503. Maintain independent **business completion**, backlog, and unknown-outcome metrics.

## 29. Unit-Testing Route Policies and Header Normalization

A trustworthy router needs tests for valid routes, rejecting invalid routes, and blocking spoofed headers.

| Input | Expected |
|---|---|
| tenant-17 + invoice.created + billing-erp | HTTP approved |
| tenant-17 + invoice.exported + archive-x | SFTP approved |
| tenant-17 + unknown event | `ROUTING_REJECTED` |
| Unauthorized `destinationAlias` for tenant | `ROUTE_NOT_AUTHORIZED` |
| Missing `routeKey` after normalization | `MISSING_ROUTE` |
| `routeKey` with bad casing/whitespace | Consistently normalized or rejected |
| HTTP client sends `routeKey=JDBC` | Blocked by policy |
| `destinationAlias` holds raw internal URL | Rejected SSRF |
| SFTP path contains traversal | Rejected |
| Kafka topic outside allowlist | Rejected |
| Unsupported `schemaVersion` | Rejected or converted per contract |
| Business event past deadline | `CANCELLED`/`PARKED` per policy |
| Registry temporarily unavailable | Fail-safe/parking |
| Route policy changes mid-retry | Audited pinned/migrated decision |
| Destination disabled | Rejected/`PARKED`, never defaults elsewhere |
| Duplicate event with different version | Not wrongly deduplicated |

### Testing message contracts

For each inbound adapter:

1. Raw headers translate to trusted metadata matching origin.
2. Principal/tenant verified before generating `routeKey`.
3. `businessEventId` stays stable across retries/redeliveries/replays.
4. `schemaVersion` validated against payload, not header alone.
5. Correlation ID preserved without leaking credentials.
6. Unknown routes rejected with reasons, never sent to `nullChannel`.
7. Kafka/SFTP/JMS-specific headers never leak to HTTP partners.
8. Route decisions include the proper policy version.

## 30. Integration Testing: Proving the Right `MessageChannel` and Adapter

A test topology:

~~~text
testInputChannel
    -> normalizer
    -> protocolRouter
       -> mockHttpChannel
       -> mockSftpChannel
       -> mockKafkaChannel
       -> mockJdbcChannel
       -> rejectedChannel
~~~

**Pure routing tests need no real network calls**; use test endpoints, spies/`ChannelInterceptor`, mock handlers, or test application contexts.

For a `routeKey=HTTP` message:

- Only `mockHttpChannel` receives one message under single-branch semantics.
- All other channels receive nothing.
- Payload/headers preserve the contract.
- `rejectedChannel` receives nothing.
- If the mocked HTTP adapter fails, error/recovery triggers on the HTTP branch without re-sending to SFTP/Kafka.
- On missing mappings, the error flow records a reason without silent drops.

### Testing request–reply

A synchronous HTTP inbound gateway needs tests verifying:

- Replies return when the routed gateway responds.
- Clear error statuses return when no valid route exists.
- One-way branches are never treated as reply paths unless an async job-acceptance contract exists.
- Correlation IDs stay accurate under concurrency.
- Timeouts/deadlines are enforced; caller retries create no duplicates.

### Testing asynchronous boundaries

For `ExecutorChannel` or `QueueChannel`, never assert only `send` succeeded. Wait for **destination completion or durable status** with bounded timeouts, verifying `errorChannel`, storage/recovery, and shutdown lifecycles.

## 31. Multi-Protocol End-to-End Test Matrix

| ID | Scenario | Expected outcome |
|---|---|---|
| R1 | Valid `routeKey=HTTP` | HTTP branch only |
| R2 | Valid `routeKey=SFTP` | SFTP branch only |
| R3 | Valid `routeKey=JMS` | JMS branch only |
| R4 | Valid `routeKey=AMQP` | AMQP branch only |
| R5 | Valid `routeKey=KAFKA` | Kafka branch only |
| R6 | Valid `routeKey=FILE` | File branch only |
| R7 | Valid `routeKey=JDBC` | JDBC branch only |
| R8 | Missing `routeKey` | `ROUTING_REJECTED` with reason |
| R9 | Unsupported key | Never falls back to default business destination |
| R10 | Channel mapping typo | Explicit failure/alert |
| R11 | Channel has no subscriber | Test catches broken topology |
| R12 | Wrong header casing/type | Normalized/rejected per policy |
| R13 | HTTP client tries picking JDBC | Blocked by authorization |
| R14 | Tenant A picks tenant B's destination | Rejected |
| R15 | Raw URL to metadata/internal host | Blocked by SSRF guard |
| R16 | Raw SFTP path escapes root | Blocked by path guard |
| R17 | Raw JMS queue/AMQP exchange off allowlist | Not published |
| R18 | Unauthorized raw Kafka topic | Not published |
| R19 | Valid HTTP route yet bad schema | Quarantine/transform error |
| R20 | HTTP 503 then success | Bounded retry, single outcome |
| R21 | POST commits then response lost | Idempotency/reconciliation |
| R22 | SFTP upload times out after remote write | Reconcile remote state |
| R23 | SFTP file actively uploading | Partial not parsed |
| R24 | Duplicate file after restart | Stable `eventId` dedup |
| R25 | JMS listener rollback | Redelivery per contract |
| R26 | AMQP confirm lost | Consumer/idempotency handles duplicate |
| R27 | Uncommitted Kafka offset and handler failure | Proper redelivery/recovery |
| R28 | Kafka ordering per aggregate | Never processes stale version |
| R29 | JDBC deadlock | Fresh transaction, valid commit |
| R30 | JDBC row claimed then app crashes | Lease/recovery works |
| R31 | Policy changes mid-retry | Audited pinned/migrated decision |
| R32 | Destination disabled | Clear `PARKED`/rejection |
| R33 | `DirectChannel` downstream throws | Correct exception path |
| R34 | `ExecutorChannel` downstream throws | Proper `ErrorMessage`/parking |
| R35 | HTTP inbound routes to one-way adapter | Reply/job contract, no pointless timeout |
| R36 | Three-recipient fan-out, SFTP fails | Retries only non-`DONE` recipient |
| R37 | DLQ/parking write fails | Never acks away source message |
| R38 | Replayed `businessEventId` | No duplicate ERP order |
| R39 | Header holds bearer token during bridge | Redacted in outbound/logs |
| R40 | Metric includes `eventId` label | Test flags high cardinality |
| R41 | Unsupported `schemaVersion` | Properly rejected/transformed |
| R42 | Destination credentials expired | Alerts; no infinite retries |
| R43 | `RecoveryCallback` swallows exception | Ack/commit test catches bug |
| R44 | Nested client/handler/broker retries | Total attempts bounded |
| R45 | Crash between DB commit and broker publish | Outbox recovers |
| R46 | Trace from HTTP to SFTP/Kafka | Correlation kept, secrets not leaked |
| R47 | Unknown route → `nullChannel` | Negative test must fail |
| R48 | One event needs two protocols | Fan-out per recipient state |
| R49 | Default route changes in release | Contract test detects change |
| R50 | Registry unavailable | Fail-safe, auth never bypassed |

### Crash-point tests

Cleanly stop the application at:

1. After inbound receive, before inbox/normalization.
2. After approved route decision, before adapter send.
3. After remote HTTP commit, before response.
4. After DB commit/outbox write, before broker publish.
5. After durable DLQ write, before source ack.
6. After source ack, before emitting telemetry.

Each case must establish `DONE`/`PARKED`/`OUTCOME_UNKNOWN`/redelivery status, an owner, and proof against lost or doubled side effects—not merely asserting `routeKey` mapped right.

## 32. Case Study: Multi-Protocol Routing in an Order Hub

### Context

An enterprise operates an **Order Hub** on Spring Integration. Orders arrive from:

- Sales channel HTTP webhooks;
- Partner SFTP batch files;
- Kafka topic carrying order lifecycle events;
- JMS queue carrying inventory update requests.

Order Hub must select:

- **HTTP ERP** for order create/update commands;
- **SFTP** for end-of-day reconciliation files;
- **AMQP** for warehouse notifications;
- **Kafka** for analytics;
- **JDBC** for persisting internal order status;
- **File** for exporting internal reports.

### Business requirements

1. Never misroute tenant A into a destination belonging exclusively to tenant B.
2. Order events carry stable IDs; replays never create duplicate ERP orders.
3. Raw HTTP headers never choose URLs/SQL/topics.
4. Events from diverse sources normalize into one internal contract.
5. One-way destinations track completion in separate states.
6. Transient failures retry within bounds; permanent/unknown errors persist for investigation.
7. When route policies change, pending jobs hold **pinned or explicitly migrated decisions**.
8. Never leak Authorization tokens when bridging from HTTP to Kafka.
9. Telemetry proves accurate destination and completion status.
10. One failing SFTP partner must never stall unrelated HTTP/Kafka flows.

### Data flow

~~~mermaid
flowchart TD
    HTTP["HTTP webhook"] --> N["Canonical normalizer"]
    SFTP["SFTP batch + poller"] --> N
    KIN["Kafka inbound"] --> N
    JMSIN["JMS inbound"] --> N
    N --> V["Validate identity/schema/eventId"]
    V --> P["Destination policy: tenant/eventType/version"]
    P --> R{"Protocol Router"}
    R -->|"HTTP"| H["ERP HTTP gateway"]
    R -->|"SFTP"| S["Render CSV + SFTP adapter"]
    R -->|"AMQP"| A["AMQP outbox publisher"]
    R -->|"KAFKA"| K["Kafka adapter"]
    R -->|"FILE"| F["File adapter"]
    R -->|"JDBC"| D["JDBC transaction handler"]
    R -->|"UNKNOWN / DENIED"| X["Rejected + audit + parking"]
    H --> O["Per-destination status"]
    S --> O
    A --> O
    K --> O
    F --> O
    D --> O
    X --> O
~~~

Arrows do not imply every source goes to every destination. **Destination policy** selects one or more recipients per contract.

### Sample event

~~~json
{
  "eventId": "tenant-17:order-882:v3",
  "tenantId": "tenant-17",
  "eventType": "order.updated",
  "schemaVersion": "v3",
  "occurredAt": "2026-11-23T08:00:00Z",
  "payload": {
    "orderId": "order-882",
    "businessVersion": 3,
    "status": "CONFIRMED"
  }
}
~~~

Inbound adapters may attach auxiliary metadata, yet the normalizer decides which fields are trustworthy and strips unsuitable transport-specific headers and secrets.

### Events over a day

| Time | Event | Routing risk |
|---|---|---|
| 08:00 | Valid webhook requesting ERP sync | Pick right tenant HTTP, preserve reply |
| 08:02 | Client spoofs `targetProtocol=JDBC` | Unauthorized route |
| 08:04 | SFTP file still uploading | Poller/partial file handling |
| 08:06 | Kafka receives `order.updated` v3 | Normalization/version/ordering |
| 08:08 | HTTP ERP returns 503 | Retry right branch handler |
| 08:09 | ERP committed yet response lost | Unknown outcome/duplicate |
| 08:10 | AMQP publisher down | Outbox and per-recipient retries |
| 08:11 | Registry swaps ERP endpoint | Replay should pin decision |
| 08:12 | `routeKey=KAFKA` with disabled topic | Parking/alert, not `NullChannel` |
| 08:14 | JDBC hits deadlock | Transaction retry on fresh boundary |
| 08:16 | Duplicate copy with same `eventId` arrives | Inbox/dedupe |
| 08:20 | Consumer restarts between publish and ack | At-least-once/idempotency |

### Practice tasks

1. Sketch inbound adapters and the **trusted normalization boundary**.
2. Define at least 8 internal headers covering identity, routing, and correlation.
3. Choose protocol branches for the six operations and explain why `routeKey` cannot replace `destinationAlias`.
4. Build an **allowlist table of `tenantId` + `eventType` + `destinationAlias`**.
5. Write policies for missing/unknown `routeKey`, disabled destinations, and unavailable registries.
6. Explain why client-supplied `targetProtocol=JDBC` must be rejected.
7. Design separate payload transformers for HTTP, SFTP, Kafka, and JDBC.
8. Identify branches needing **replies** vs. **one-way completion**.
9. For fan-out to ERP + Kafka + SFTP, how do you persist per-recipient statuses?
10. When HTTP POST ERP commits yet the response times out, how do you avoid creating duplicate orders?
11. If route policy changes during replay, pick pinned vs. migrated decisions and justify why.
12. Propose the 6 most important metrics and 10 integration tests.

### Solution guide

**1. Normalization:** HTTP/SFTP/Kafka/JMS ingress authenticates sources, parses schemas, normalizes `businessEventId`/`tenantId`/`eventType`/`schemaVersion`; policy resolver queries the destination registry and emits `routeKey`. Never let raw client `targetProtocol` bypass policy.

**2. Contract:** `businessEventId`, `correlationId`, `sourceSystem`, `tenantId`, `eventType`, `schemaVersion`, `destinationAlias`, `targetProtocol`, `routeKey`, `routePolicyVersion`, `deadlineAt`. Broker/HTTP headers serve only as source metadata once verified.

**3. Route branches:** HTTP for ERP, SFTP for partner exports, AMQP for warehouse, Kafka for analytics, JDBC for internal state, File for reports. Each branch has distinct serializers, timeouts, error handling, and delivery semantics.

**4. Authorization:** tenant-17 can only route to registered aliases. If an alias belongs to tenant-99, reject prior to channel mapping. Re-check permissions in adapter handlers for sensitive data.

**5. Missing/unknown:** `routingRejectedChannel` with reason codes and durable recovery. Never default to an HTTP partner or `NullChannel`.

**6. Spoofed headers:** raw JDBC protocol/headers cannot substitute for principal permissions. Trusted `routeKey` must be policy-generated.

**7. Transformers:** canonical event to ERP JSON v2, SFTP CSV v2, Kafka key/value schema, JDBC prepared parameters. Routers never convert formats themselves.

**8. Reply semantics:** HTTP inbound gateways require request–reply; SFTP/Kafka/AMQP publishes are usually one-way, needing separate completion status if business needs confirmation.

**9. Fan-out:** e.g., `ERP=DONE`, `Kafka=DONE`, `SFTP=RETRY_WAIT`; retry only SFTP instead of blindly re-sending ERP/Kafka. Use outboxes/per-recipient state and idempotency.

**10. Unknown outcomes:** query ERP by `orderId`/idempotency key, hold `OUTCOME_UNKNOWN` until resolved; retry POST with the same stable key only if the partner supports that contract.

**11. Route policy changes:** pin `destinationAlias` and `routePolicyVersion` on pending events when audit/correctness requires it; migrate via controlled review if switching targets.

**12. Metrics and tests:** `route_decisions_total`, `route_rejected_total`, `route_unauthorized_total`, `delivery_success_total`, `unknown_outcome_total`, `parked_backlog_age_seconds`; test HTTP/SFTP/Kafka correct channels, tenant isolation, header spoofing, unknown routes, payload mismatches, reply paths, timeout-after-commit, retry-only-failed-recipient, and restarts.

### State persistence sketch

~~~text
businessEventId = tenant-17:order-882:v3

INGESTED
   -> VALIDATED
   -> ROUTE_APPROVED
   -> PER_RECIPIENT_PENDING
       ERP_HTTP: DONE
       KAFKA_ANALYTICS: DONE
       SFTP_EXPORT: RETRY_WAIT
   -> DONE once all mandatory recipients complete

If route is invalid:
   -> ROUTING_REJECTED + reason + owner

If remote outcome is unknown:
   -> OUTCOME_UNKNOWN + reconciliation

If retries exhaust:
   -> PARKED/DLQ + audit + controlled redrive
~~~

Never mark the whole event `DONE` merely because the router successfully sent a message to an `ExecutorChannel`.

## 33. Common Anti-Patterns

| Anti-pattern | Consequence | Fix |
|---|---|---|
| Routing directly on raw HTTP headers | Header spoofing, unauthorized routing | Normalize + authorize |
| `protocol=HTTP` means any URL is allowed | SSRF / wrong target | `destinationAlias` + allowlisted registry |
| Taking `MessageChannel` names from clients | Unintended access to internal handlers | Map keys to static approved channels |
| Defaulting unknown routes to HTTP | Side effects at wrong destination | Rejected/parking |
| Routing unknown keys to `NullChannel` | Silent data loss | Durable rejection/audit |
| Sending one canonical DTO straight to all adapters | Schema mismatches | Per-destination transformers |
| Conflating JMS routing keys with Spring `routeKey` | Wrong broker destinations | Separate two mapping layers |
| Reading Kafka topic names from untrusted headers | Unauthorized publishes | Topic aliases + ACLs |
| Building SFTP paths from raw tenant strings | Path traversal / cross-tenant leaks | Root allowlists + validation |
| Reading JDBC tables/SQL from headers | SQL injection / broken permissions | Prepared params + operation allowlists |
| Measuring only channel send success | Blind to outbound completion | Business delivery status |
| Using one-way adapters to reply to HTTP gateways | Caller timeouts | Reply / 202-job contracts |
| Duplicate router policies per inbound source | Duplicated logic, weak governance | Canonical normalizer + shared policy |
| Retrying whole flow when one adapter fails | Repeats already-`DONE` side effects | Retry specific handler/recipient |
| Always re-routing replays under new policies | Unexpectedly switches targets | Pinned decisions/migrations |
| Fan-out without per-recipient status | Cannot tell which target missed | Per-recipient state/outbox |
| Committing Kafka offsets after async enqueue | Lost work on crash | Durable handoff/ack boundaries |
| Swallowing JMS/AMQP exceptions | Acks unprocessed messages | Rethrow/durable recovery |
| Mixing route errors and delivery errors | Pointlessly retries config bugs | Failure stages + classifiers |
| Logging full `MessageHeaders` | Token/credential leaks | Header allowlists/redaction |
| Missing wrong-tenant tests | Cross-tenant data leaks | Negative authorization tests |
| Treating pollers as unconditional retry sources | Fails to re-pick already-claimed items | Durable metadata/parking |
| Unversioned destination registries | Unauditable replays | Policy versions/auditing |
| Dynamic routing without circuit breakers/bulkheads | One down partner drags down platform | Isolation/backpressure |

## 34. Implementation Checklist

- [ ] Inbound adapters/gateways and `MessageChannels` are explicitly diagrammed.
- [ ] Canonical message contract includes `businessEventId`, `tenantId`, `eventType`, and `schemaVersion`.
- [ ] Raw headers are separated from trusted routing headers.
- [ ] Source identity/principals are authenticated before deciding destinations.
- [ ] `destinationAlias` and operations are authorized per tenant.
- [ ] `targetProtocol` comes strictly from an allowlisted protocol enum.
- [ ] `routeKey` is normalized; arbitrary raw channel names are never used.
- [ ] `HeaderValueRouter`/`@Router`/DSL mappings fit and wiring is tested.
- [ ] Unknown/missing/unauthorized routes go to rejected/parking with reasons.
- [ ] `NullChannel` is never used as a default for business messages.
- [ ] HTTP URLs, SFTP paths, JMS/AMQP destinations, Kafka topics, and JDBC operations use approved registries.
- [ ] Dedicated transformers/serializers exist per destination/`schemaVersion`.
- [ ] Authorization/secret/PII headers never leak across protocols.
- [ ] One-way vs. request–reply is defined per branch.
- [ ] Error semantics for `DirectChannel`/`ExecutorChannel`/`QueueChannel` are tested.
- [ ] Retries wrap appropriate outbound handlers/recipients rather than blindly re-running orchestration.
- [ ] `RetryPolicy`/`BackOffPolicy` define timeouts, `maxAttempts`, and total deadlines.
- [ ] Source acks/offsets and transactions align with durable outcomes.
- [ ] Inbox/outbox/idempotency or reconciliation protects against duplicate effects.
- [ ] Fan-out tracks per-recipient statuses and retries only missing recipients.
- [ ] SFTP/File enforces ready markers, partial-file handling, and stable filenames.
- [ ] Kafka ordering and offset/commits honor contracts.
- [ ] JDBC transaction retries use fresh boundaries where needed and unique business keys.
- [ ] Route decisions/`routePolicyVersion` are persisted for replays/audits.
- [ ] Destination registry changes have owners, approvals, canaries, and rollbacks.
- [ ] Unavailable registries never bypass authorization.
- [ ] Routing metrics and delivery metrics are tracked separately.
- [ ] Alerts exist for `ROUTING_REJECTED`, unauthorized routes, unknown outcomes, and parked backlogs.
- [ ] Tests cover contracts, negative security, crashes/restarts, duplicate deliveries, and target outages.
- [ ] Per-protocol triage/replay runbooks and error procedures exist.

## 35. Glossary and Further Reading

| Term | Meaning |
|---|---|
| **Message Router** | Pattern selecting branches/channels based on rules |
| **`HeaderValueRouter`** | Spring Integration router picking channels from a header value |
| **Content-Based Router** | Chooses targets based on message contents |
| **Recipient List Router** | Distributes one message to a selected list of recipients |
| **Dynamic Router** | Routing driven by runtime policies/registries |
| **Routing Slip** | Ordered multi-step processing itinerary |
| **`MessageChannel`** | Conduit passing messages between endpoints |
| **Inbound/Outbound adapter** | Connects external sources/targets, typically one-way |
| **Gateway** | Request–reply integration component |
| **Route key** | Value selecting a routing branch |
| **Destination alias** | Logical identifier of a registered target |
| **Policy version** | Auditable version of routing rules |
| **Canonical message** | Standardized internal message contract |
| **Header spoofing** | Forging metadata to manipulate routing decisions |
| **SSRF** | Forcing an app to make unauthorized network calls |
| **Idempotency key** | Stable key identifying the same business operation |
| **Outbox/Inbox** | Patterns preserving outbound intent and/or inbound dedupe |
| **DLQ/PARKED** | Status/destination holding failed messages for triage |
| **Redelivery** | Broker/source re-sending a message |
| **Unknown outcome** | Remote may have committed while caller lacks confirmation |
| **`ReplyChannel`/`ErrorChannel`** | Channels returning responses/errors per Spring Messaging semantics |
| **Backpressure** | Throttling upstream to prevent downstream overload |

### Further reading

- **Spring Integration Reference — Routers:** `HeaderValueRouter`, Content-Based Router, recipient lists, expressions, method routers.
- **Spring Integration Reference — Java DSL:** `IntegrationFlow`, channel mappings, router endpoint configuration.
- **Spring Integration Reference — Message Channels:** `DirectChannel`, `ExecutorChannel`, `QueueChannel`, and `PublishSubscribeChannel`.
- **Spring Integration Reference — Message Headers and Header Enrichment:** metadata, `replyChannel`/`errorChannel`, and header propagation.
- **Spring Integration Reference — HTTP, File, SFTP, JMS, AMQP, Kafka, JDBC adapters/gateways:** connection traits per protocol.
- **Spring Integration Reference — Error Handling and Message Handler Advice:** error channels, retry advice, and recovery.
- **Spring Retry Reference:** `RetryTemplate`, `RetryPolicy`, `BackOffPolicy`.
- **Spring AMQP / Spring for Apache Kafka References:** acknowledgments, redelivery, offsets, and DLQ/DLT.
- **Enterprise Integration Patterns:** Message Router, Content-Based Router, Recipient List, Routing Slip, Idempotent Receiver, and Dead Letter Channel.

## 36. Self-Check Questions

1. How does a router picking a channel differ from an adapter executing a protocol?
2. Why is `routeKey=HTTP` insufficient to identify which partner receives a message?
3. When should you use `HeaderValueRouter` vs. a `@Router` method?
4. Why can't raw `X-Target-Protocol` from an HTTP client act as a trusted `routeKey`?
5. If a `routeKey` has no mapping, what risk arises from defaulting to HTTP?
6. How does a single-branch router differ from a Recipient List Router?
7. Why doesn't a successful `message.send` to `ExecutorChannel` prove the HTTP ERP processed it?
8. When an HTTP inbound gateway routes to a one-way SFTP adapter, what response contract is needed?
9. If a JMS/Kafka source acks/commits before the outbound handler finishes, what is the consequence?
10. Why might a message retried after a route policy change need a pinned decision?
11. When Kafka offsets 100 and 101 route through two branches running at different speeds, what happens to ordering?
12. How do you test against cross-tenant misrouting and SSRF?
13. When a fan-out shows HTTP=DONE, Kafka=DONE, SFTP=RETRY_WAIT, where should retries occur?
14. Where should route policy/version be stored if a message awaits delayed replay?
15. Why is `NullChannel` not a valid default recovery path for unsupported routes?

### Summary answers

1. The router selects a `MessageChannel` branch; adapters/transformers handle I/O and format conversions.
2. Multiple targets can share the same protocol; you need `destinationAlias`/`tenant`/`eventType` and authorization.
3. `HeaderValueRouter` fits a single trusted header; method routers fit multi-dimensional conditions and policies.
4. Clients can spoof headers; authenticate, normalize, and authorize destinations before generating keys.
5. Messages may hit the wrong target, causing wrong side effects or data leaks.
6. Single-branch routers select one destination; Recipient List Routers target multiple destinations and need per-recipient tracking.
7. Async channels only confirm executor handoff; the remote handler may not have run yet.
8. Return a contract-defined response/job ID/accepted status rather than leaving callers waiting for a nonexistent reply.
9. Business events risk being lost if the process crashes or outbound fails.
10. Registry changes could redirect replays to another target, causing duplicates or wrong business actions.
11. The later event can process before the earlier one; use ordering/version guards.
12. Negative tests covering tenant permissions, raw URL/path/topic/channel injection, and allowlists.
13. Retry only the SFTP recipient; preserve DONE for HTTP/Kafka and keep stable event IDs.
14. In durable message/job state or an audit store tied to `eventId`/approved destination/policy version.
15. `NullChannel` drops messages; unknown routes need rejection/parking/alerts and evidence.

**Key takeaway:** A **protocol- or header-based router** in Spring Integration is a **mechanism for selecting a `MessageChannel` based on a trusted routing contract**, not a component that automatically converts every protocol or guarantees every delivery. A reliable design always **normalizes/authorizes before routing**, maps onto **approved destinations**, transforms payloads per contract, protects **request–reply/transactions/acks/idempotency**, handles invalid routes via **rejected/parking** flows, and preserves **policy versions + observability** for safe retries and replays.
