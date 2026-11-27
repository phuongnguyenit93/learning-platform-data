# Designing Event Schemas and Using CloudEvents

An e-commerce system can emit events when an order is created, payment is confirmed, goods are shipped, or a new file is uploaded. Those events are processed independently by multiple services: billing, inventory, email, analytics, and auditing. If each team invents its own field names, date-time formats, event IDs, and compatibility rules, the system will quickly break during new deployments or data replays.

An **event schema** is the contract describing the structure and meaning of an event message. **CloudEvents** is an open specification that standardizes the *envelope* (contextual metadata) of an event so systems can identify where an event came from, what type it is, and what ID it carries, instead of learning a custom wrapper format for every producer.

This lesson belongs to the **Events and Streaming Data** chapter of the **CLOUD_PROVIDERS_AZURE** module. It connects data contract design with Azure Event Grid, Event Hubs, Service Bus, Azure Functions, Java, Azure Storage, Microsoft Entra ID, private networking, monitoring, security, and cost control in Azure application architectures.

> **Scope:** this lesson uses **CloudEvents 1.0**, JSON Schema, and HTTP as illustrative examples. CloudEvents standardizes event formatting and context; it **does not** by itself guarantee ordering, exactly-once delivery, authentication, a schema registry, or idempotency. Azure CLI/SDK features and syntax must be verified for the exact version, resource type, SKU, and region during real deployment.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish *events*, *commands*, *state snapshots*, message transport, and streams.
2. Design events with clear business semantics, compact payloads, versioning, and ownership.
3. Explain the required and optional attributes of CloudEvents 1.0.
4. Read and write CloudEvents in **JSON structured mode** and **HTTP binary mode**.
5. Distinguish `data`, `data_base64`, `datacontenttype`, and `dataschema`.
6. Use **JSON Schema** to define and validate payloads, and plan compatibility across schema changes.
7. Design event IDs, correlation IDs, idempotent consumers, and the transactional outbox pattern.
8. Apply CloudEvents appropriately with Event Grid, Event Hubs, and Service Bus without confusing each service's role.
9. Write Java examples using the CloudEvents SDK to create/serialize events and build contract tests.
10. Design security, observability, replay, cost controls, and production schema governance processes.

## 2. Event-Driven Architecture Needs Data Contracts

Suppose the Order Service processes a purchase request. Once the database transaction commits, the service emits an `OrderCreated` event. Billing, Inventory, and Notification all care about the event, though they do not necessarily run on the same host or deploy at the same version.

~~~mermaid
flowchart LR
  API["Order API"] --> DB["Orders database"]
  DB --> OUT["Transactional outbox"]
  OUT --> PUB["Event publisher"]
  PUB --> BUS["Event Grid / broker / stream"]
  BUS --> B["Billing"]
  BUS --> I["Inventory"]
  BUS --> N["Notification"]
  PUB -.-> REG["Schema contract / catalog"]
~~~

Elements that producers and consumers must agree on include:

- **Meaning:** When did “Order created” occur? After durable persistence, or merely when the API received the request?
- **Identity:** source, type, ID, and occurrence timestamp.
- **Payload:** which fields are required, units of measurement, data types, and nullability rules.
- **Compatibility:** if the producer adds or removes a field, will older consumers keep working?
- **Delivery:** can messages be duplicated, delayed, or delivered out of order?
- **Governance:** who owns the schema, changes, deprecation, and error handling?

With JSON formatting alone and no business explanation, applications can still misinterpret data. For example, `amount: 1200` does not clarify whether it is 1,200 VND, 12.00 USD, or 1,200 cents. **A schema contract must describe semantics**, not just JSON syntax.

## 3. Distinguishing Events, Commands, and Snapshots

| Concept | Meaning | Example names | Consumer |
|---|---|---|---|
| **Event** | A fact that has already happened in the past | `OrderCreated`, `PaymentCaptured` | One or more interested parties |
| **Command** | A request to perform an action, which can fail | `CreateInvoice`, `ReserveInventory` | Usually a single responsible handler |
| **State snapshot** | Current state at a point in time | `OrderSnapshot` | State synchronization, cache, or projection |
| **Telemetry** | Technical observation from a system | `CpuSample`, `HttpRequestTrace` | Monitoring/analytics |

A **`PaymentCaptured`** event should only be emitted once the business logic has actually confirmed funds were captured. If the application has only sent a request to the payment gateway, the event should reflect that state—such as `PaymentCaptureRequested`—and must not claim success prematurely.

### Why are events typically past tense?

Events describe facts, so past-tense names prevent receivers from confusing them with commands. Yet naming is only a signal: the contract must still explain *when the event is emitted* and the governing business conditions.

### Events differ from API responses

An HTTP response is typically aimed at the immediate caller within a request/response context. Events are emitted so components can **react after something happens**. The same workflow can use a synchronous command API to accept requests and asynchronous events to announce outcomes.

## 4. What Does CloudEvents Solve?

**CloudEvents** is an open specification in the CNCF ecosystem. It defines an event model consisting of **context attributes** and **event data**, along with *format/protocol bindings* for representing events over HTTP or other protocols.

CloudEvents helps:

1. Producers and consumers share standard attributes like `id`, `source`, `type`, and `specversion`.
2. Intermediaries classify and route events without necessarily decoding the business payload.
3. Event metadata avoids complete coupling to a single Azure service's naming.
4. Provide extension points for tracing, correlation, or agreed-upon metadata.
5. Design transport-independent contracts as architectures evolve.

CloudEvents **does not**:

- Dictate which fields your business payload must contain.
- Automatically validate JSON payloads via a schema registry.
- Guarantee events are delivered exactly once or in order.
- Provide a broker, queue, durable storage, or replay.
- Solve auth, encryption, or data governance by itself.
- Turn any arbitrary JSON message into a valid CloudEvent if required context attributes are missing.

A valid CloudEvents message can be transported via Azure Event Grid or placed inside the body of a Service Bus message. Retry, DLQ, and ordering behaviors remain governed by the transport service and the application.

## 5. CloudEvents 1.0: Structure and Core Attributes

CloudEvents defines **four required context attributes**:

| Attribute | Required | Type/purpose | Example |
|---|---|---|---|
| `specversion` | Yes | CloudEvents specification version | `"1.0"` |
| `id` | Yes | Event identifier within the scope of `source` | `"evt-7f2a"` |
| `source` | Yes | URI-reference identifying the producer context | `"https://events.example.org/orders"` |
| `type` | Yes | Event type, defined by producer/system | `"com.example.orders.created.v1"` |

Commonly used **optional** attributes:

| Attribute | What it is for | Notes |
|---|---|---|
| `subject` | Distinguishes objects within the same source | E.g. `"orders/1024"`; not necessarily a fetchable URL |
| `time` | Timestamp when the event occurred, RFC 3339 | Prefer UTC; not identical to broker enqueue time |
| `datacontenttype` | Media type of the payload | E.g. `"application/json"` |
| `dataschema` | URI identifying the schema of `data` | Does not automatically trigger validation or fetch the schema |
| Extension attributes | Agreed-upon extension metadata | E.g. `traceparent`, `tenantid` where appropriate |

Beyond context, an event carries **event data**, such as an order's JSON. CloudEvents uses `data` in the JSON event format to represent payloads and provides `data_base64` when representing Base64-encoded byte data.

### Relationship between source and id

The combination **`source` + `id`** should uniquely identify an event within the producer's scope of responsibility. Two independent sources may use the same ID string without referring to the same event. When **redelivering the exact same event on retry**, keep `source` and `id` unchanged so consumers can detect duplicates.

A new business update—even for the same `orderId`—is **a new event** and should receive a new event ID. Never reuse `orderId` as `id` for all events about the same order.

### Source is an identifier, not necessarily an endpoint

`source` is a **URI-reference**; an absolute URI is readable and easy to govern. It does not have to be an actual HTTP URL consumers can call. For instance, `https://events.example.org/orders` can serve purely as a stable namespace with no API hosted there.

## 6. CloudEvent Example in JSON Structured Format

An order-created event:

~~~json
{
  "specversion": "1.0",
  "id": "evt-20261120-6d8c",
  "source": "https://events.example.org/commerce/orders",
  "type": "com.example.commerce.order.created.v1",
  "subject": "orders/order-1024",
  "time": "2026-11-20T08:15:00Z",
  "datacontenttype": "application/json",
  "dataschema": "https://schemas.example.org/commerce/order-created/v1.json",
  "data": {
    "orderId": "order-1024",
    "customerRef": "cust-90",
    "currency": "VND",
    "totalAmountMinor": 259000,
    "items": [
      {"sku": "SKU-17", "quantity": 2}
    ]
  }
}
~~~

From a consumer's perspective:

- `type` selects the handler for this event type.
- `source` tells who published it.
- `id` enables duplicate detection.
- `subject` links to the business resource.
- `time` helps measure emission latency.
- `dataschema` indicates the **payload** contract version.
- `data` holds the business details; actual schemas must verify field types and meanings.

`totalAmountMinor` denotes the **smallest currency unit** per the agreed domain convention. For VND, document conversion and rounding rules explicitly; do not rely solely on a field name and ignore currency properties. When working across multiple currencies, standardize currency exponents and amount rules in the contract documentation.

### Two distinct version layers

`specversion: "1.0"` is the **CloudEvents specification version**, not the OrderCreated event version. Business versioning can be expressed in `type`, `dataschema`, a contract catalog, or whatever governance scheme the organization adopts. Changing the payload does not automatically bump `specversion`.

## 7. data, data_base64, and datacontenttype

In the CloudEvents JSON Event Format:

- `data` expresses data representable directly as JSON types: object, array, string, number, boolean, or null depending on content.
- `data_base64` carries binary or byte data Base64-encoded inside the JSON format.
- `datacontenttype` describes the media type of the data; it **differs** from the media type of the overall CloudEvent envelope when sent in structured mode.

Example of a binary payload in CloudEvents JSON format:

~~~json
{
  "specversion": "1.0",
  "id": "evt-binary-01",
  "source": "https://events.example.org/files",
  "type": "com.example.file.sampled.v1",
  "datacontenttype": "application/octet-stream",
  "data_base64": "SGVsbG8="
}
~~~

The Base64 string above represents sample data `Hello`, not a production binary file. **Never set both `data` and `data_base64` to describe two different payloads in the same CloudEvent JSON**. Pick one representation and configure serializers/consumers consistently.

### JSON object, not a nested JSON string

For `datacontenttype: application/json`, prefer:

~~~json
"data": {"orderId": "order-1024", "status": "CREATED"}
~~~

over serializing the object into an escaped JSON string inside `data`. String-encoding forces consumers to parse twice and invites type mismatches.

### Large payloads

CloudEvents does not remove message size limits in Event Grid, Event Hubs, Service Bus, or HTTP receivers. If the payload is a video, image, or large document, use the **claim-check pattern**:

1. Store the file in Blob Storage.
2. Emit an event containing `blobRef`, size/checksum, version, or ETag as appropriate.
3. Consumer uses managed identity / granted permissions to read it.
4. Verify file readiness and checksum match.
5. Clean up files per retention once consumers finish.

Never embed long-lived SAS tokens or credentials inside `data`, `subject`, or extension attributes.

## 8. Structured Mode and Binary Mode over HTTP

CloudEvents defines multiple HTTP mappings. Two important ones are:

### Structured content mode

In **structured mode**, the entire CloudEvent—both context and data—lives in the body using an event format, typically the JSON Event Format.

~~~http
POST /events HTTP/1.1
Host: receiver.example.org
Content-Type: application/cloudevents+json

{
  "specversion": "1.0",
  "id": "evt-20261120-6d8c",
  "source": "https://events.example.org/commerce/orders",
  "type": "com.example.commerce.order.created.v1",
  "time": "2026-11-20T08:15:00Z",
  "datacontenttype": "application/json",
  "data": {"orderId": "order-1024"}
}
~~~

HTTP `Content-Type: application/cloudevents+json` describes the **entire CloudEvents envelope**. The field `datacontenttype: application/json` describes the **payload**. These two values serve different roles.

### Binary content mode

In **binary mode**, CloudEvents metadata is mapped to HTTP `ce-*` headers, while the body carries the business payload directly:

~~~http
POST /events HTTP/1.1
Host: receiver.example.org
ce-specversion: 1.0
ce-id: evt-20261120-6d8c
ce-source: https://events.example.org/commerce/orders
ce-type: com.example.commerce.order.created.v1
ce-time: 2026-11-20T08:15:00Z
Content-Type: application/json

{"orderId": "order-1024"}
~~~

In HTTP binary mapping, the request's `Content-Type` describes the `datacontenttype` of the **event data**. Never send `Content-Type: application/cloudevents+json` with a binary body containing only `{"orderId":...}` and expect the server to parse it.

### Which one to choose?

| Criterion | Structured JSON | Binary HTTP |
|---|---|---|
| Metadata location | Inside JSON body | Inside HTTP `ce-*` headers |
| HTTP Content-Type | `application/cloudevents+json` | Media type of the event data |
| When appropriate | Storing/forwarding whole events, broker bodies, gateways handling envelopes | HTTP endpoints reading context from headers with raw body |
| Testing | Validate full JSON event | Validate headers and body, normalize into an event |
| Risks | Double-encoding `data` as JSON string, missing context | Proxies stripping headers, wrong Content-Type mapping |

Producers and consumers must **agree on the format and HTTP binding**. Never assume a receiver supporting only structured mode will automatically accept binary mode or vice versa.

## 9. Designing Event Type Names and Sources

`type` names should be stable, domain-clear, and owned. Example:

~~~text
com.example.commerce.order.created.v1
com.example.commerce.order.cancelled.v1
com.example.billing.invoice.issued.v1
com.example.inventory.stock.reserved.v1
~~~

This is a **design convention**, not the only mandatory syntax in CloudEvents. Use an organization/namespace you control, and avoid vague names like `update`, `event1`, or `changed` without context.

### Scoping source to producer boundaries

One option:

~~~text
source: https://events.example.org/commerce/orders
type:   com.example.commerce.order.created.v1
subject: orders/order-1024
~~~

`source` is the logical publisher; `subject` is the specific entity within it. If the same Order Service emits events from multiple nodes, do not put a random pod hostname in `source`: that breaks deduplication, cataloging, and tracing every time instances scale.

### Do not name types after transient infrastructure

Names like `aks-node-42.order-event` or `queue-abc-update` couple the event contract to topology. Event types should reflect **business semantics**, while broker queue/topic names and node locations belong to operational config.

### One event should describe one coherent fact

If Order and Payment are separate bounded contexts, avoid cramming all changes into one giant `EverythingChanged` event. Small, well-defined events let consumers subscribe only to what they need, clarify ownership, and simplify versioning.

## 10. Writing JSON Schema for Payloads

CloudEvents defines the envelope; to validate the `data` payload, you can use **JSON Schema**. Example contract for `com.example.commerce.order.created.v1`:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://schemas.example.org/commerce/order-created/v1.json",
  "title": "OrderCreatedV1",
  "type": "object",
  "required": ["orderId", "currency", "totalAmountMinor", "items"],
  "properties": {
    "orderId": {"type": "string", "minLength": 1, "maxLength": 100},
    "customerRef": {"type": "string", "maxLength": 100},
    "currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
    "totalAmountMinor": {"type": "integer", "minimum": 0},
    "items": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["sku", "quantity"],
        "properties": {
          "sku": {"type": "string", "minLength": 1},
          "quantity": {"type": "integer", "minimum": 1}
        },
        "additionalProperties": true
      }
    }
  },
  "additionalProperties": true
}
~~~

Points to note:

- `required` specifies fields mandatory under the v1 contract.
- `type: integer` prevents monetary values from drifting into inconsistent string formats.
- `minimum`, `maxLength`, and `pattern` enforce baseline constraints.
- `additionalProperties: true` lets the sender add new fields without **this schema validator** rejecting them immediately. Consumers must still be coded to tolerate unknown fields.
- `$id` matches the URI in `dataschema` for traceability.
- This is a **schema for `data`**, not a schema wrapping the four CloudEvents context attributes.

A schema only validates declared structure and types. It does not prove `orderId` actually exists, `customerRef` is authorized, or `totalAmountMinor` matches the charged amount.

### Avoid over-tightening contracts too early

If producers plan to evolve by adding fields, setting `additionalProperties: false` at every level can cause strict-validating consumers to reject newer messages. Conversely, allowing unknown fields has a trade-off: typos in new fields become harder to catch. The solution is **strict producer validation at the current version** paired with **consumer validation matching the chosen compatibility rule**, rather than flipping one boolean and calling it solved.

## 11. dataschema Is Not an Automatic Validation Service

`dataschema` is a URI-reference identifying the schema of `data`. When a CloudEvent contains:

~~~json
"dataschema": "https://schemas.example.org/commerce/order-created/v1.json"
~~~

it does not automatically mean:

- That endpoint is publicly reachable by every consumer.
- The broker downloaded and validated the payload before accepting it.
- Azure's schema registry automatically registered the URI.
- Consumers are forced to run validation.
- Events will be rejected if the schema is deleted or edited.

Engineering teams must explicitly design **schema catalog/registry hosting, versioning, producer/consumer validation, and contract testing**.

### Where does Azure Schema Registry fit?

**Azure Schema Registry** in the Event Hubs ecosystem helps manage schemas and serialization for supported formats and SDKs. However, placing `dataschema` in a CloudEvent does not automatically trigger registration, compatibility checks, or verification with Azure Schema Registry.

If your pipeline requires a schema registry, explicitly design schema storage, mapping from `dataschema`/schema ID to artifacts, access permissions, and how serializers/consumers fetch schemas for your chosen stack.

## 12. Schema Evolution: Compatible and Breaking Changes

An event can sit in a stream or queue for a long time, and consumers do not all deploy simultaneously. Therefore, compatibility rules are required between **newer producers** and **older consumers**.

### Changes that are typically compatible

- Adding an **optional field** with clear defaults/semantics.
- Adding optional metadata without altering existing field meanings.
- Changing how the producer computes values internally while preserving the published contract.
- Adding a **new** event type instead of changing the meaning of an existing one.

### Changes that risk breaking consumers

- Changing `totalAmountMinor` from integer to string.
- Changing the currency unit of an existing field without changing the field/contract.
- Removing or renaming a required field.
- Turning `orderId` from a stable identifier into an ephemeral value.
- Changing `OrderCreated` meaning from “committed” to “pending commit.”
- Adding an enum value that older consumers reject if they validate closed enums.
- Changing array/object nesting in ways that break existing parsers.

### Versioning strategy

One clear approach is versioning in `type`:

~~~text
com.example.commerce.order.created.v1
com.example.commerce.order.created.v2
~~~

During an incompatible change, a producer may emit both v1 and v2 for a transition window or provide a translation adapter, **provided duplicate business effects are controlled** if consumers subscribe to both. Record transition timelines and v1 deprecation dates in the catalog.

If you choose to version via schema URI while keeping `type` constant, align on how consumers handle multiple schema versions under one type. **No single CloudEvents rule forces every system to adopt one method**; organization-wide consistency matters more than ad-hoc field or version naming.

### Illustrative Compatibility Matrix

| Change | Strict older consumer | Tolerant older consumer | Recommendation |
|---|---|---|---|
| Add optional `promotionCode` | May fail if unknown fields forbidden | Usually accepted | Test first and announce |
| Change `totalAmountMinor` to string | Fails | May fail or misinterpret | New version |
| Drop required `currency` | Fails | May lose meaning | New version or migration |
| Add enum value `PENDING_REVIEW` | May fail | Safe only with fallback | Test consumers |
| Change meaning of `OrderCreated` | May parse cleanly yet be **business-wrong** | Business-wrong | New type/contract |

**Successful parsing does not equal business compatibility.**

## 13. Designing Event IDs and Idempotent Consumers

In event-driven architectures, delivery can be **at least once**. A consumer may receive the same event multiple times due to broker retries, timeouts, or a worker crashing after persisting results but before acking.

Recommended duplicate detection key:

~~~text
dedupKey = source + "|" + id
~~~

This is a logical representation. In a database, use a **structured composite key** or a scoped hash with clear rules; avoid delimiter collisions or Unicode normalization issues from naive string concatenation.

Example tracking table:

| source | id | consumer | status |
|---|---|---|---|
| `https://events.example.org/commerce/orders` | `evt-6d8c` | billing | COMPLETED |
| `https://events.example.org/commerce/orders` | `evt-6d8c` | notifications | COMPLETED |

Each consumer maintains its own processing state. Billing finishing does not mean Notifications has sent the email.

### Safe idempotency workflow

1. Receive event; verify the four context attributes and source authorization.
2. Validate event schema, type, version, and business key.
3. Attempt a **conditional** deduplication insert in a data store with concurrency control.
4. Execute business side effects using appropriate transactions/unique constraints.
5. Record completed status in the same transaction whenever possible.
6. Ack/complete delivery only after results are durably persisted.
7. If already completed previously, skip creating new side effects; ack after verification.

If a consumer triggers side effects in an **external system** without shared transactions, use a partner-side idempotency key or compensating/reconciliation workflows. CloudEvents does not provide cross-service atomic commits.

### Deduplication retention window

Do not purge deduplication records too early while brokers or streams can still redeliver or replay older data. Retention must account for **message TTL, stream retention, DLQ replay, backup restores, and operator workflows**. Also enforce lifecycle cleanup once records expire per policy.

## 14. Transactional Outbox: Emitting Events After Commit

A classic failure window:

1. Order Service writes the order successfully to the database.
2. Before sending `OrderCreated` to Event Grid or Service Bus,
3. The process crashes.
4. Data changed, yet consumers never receive the event.

If you publish the event before the database commits, consumers may receive an event for data that does not exist yet or was rolled back.

### The outbox pattern

~~~mermaid
flowchart TD
  API["Create order"] --> TX["Database transaction"]
  TX --> ORDER["Orders table"]
  TX --> OUT["Outbox: eventId + payload"]
  OUT --> PUB["Publisher reads unsent records"]
  PUB --> GRID["Event Grid / Event Hubs / Service Bus"]
  GRID --> C["Idempotent consumers"]
  PUB --> MARK["Mark outbox record sent"]
~~~

The order row and outbox row are written inside the **same database transaction**. The publisher may resend if an acknowledgment is ambiguous; consumers must be idempotent. Outbox does not guarantee exactly-once delivery on its own, but it prevents **the database committing without recording the event to publish**.

For databases lacking the needed transaction model, use an equivalent mechanism such as change data capture or a reliable publish pattern, and analyze its specific failure modes.

### Consumer-side inbox

Some systems use the **inbox pattern**: persisting `source`, `id`, and processing status in the consumer database to prevent duplicates and support retries. Combining outbox and inbox helps when multiple services participate in a workflow without a distributed transaction.

## 15. CloudEvents and Azure Event Grid

**Azure Event Grid** is an event routing service that pushes events to matching subscribers/destinations. It supports **CloudEvents 1.0** on supported resource types and features, alongside other event schemas/formats.

A typical pattern:

~~~mermaid
flowchart LR
  P["Producer: Order Service"] --> T["Event Grid Topic accepting CloudEvents"]
  T --> SUB["Event Subscriptions + filters"]
  SUB --> F["Azure Functions / webhook"]
  SUB --> Q["Service Bus / target destination"]
  F --> DB["Business database"]
~~~

### Distinguishing CloudEvents schema and Event Grid schema

- **CloudEvents 1.0:** uses `specversion`, `id`, `source`, `type`, and standard attributes.
- **Event Grid event schema:** has its own structure and fields such as `eventType`, `subject`, `eventTime`, and `dataVersion` depending on event type.
- **Custom event schema:** may have custom mapping/config on supported resources.

**Never send an Event Grid schema event with only the HTTP `Content-Type` changed to `application/cloudevents+json` and call it a CloudEvent.** You must map the context and fields properly.

### Input schema and delivery schema

Depending on Event Grid topic, subscription, and API type, a producer may select CloudEvents input schema while consumers receive events in a configured/supported delivery schema. Do not assume arbitrary combinations of input/output schemas or endpoint bindings work interchangeably.

Verify the exact design of the **custom topic, domain topic, system topic, or namespace topic** your project uses; APIs, features, authentication, and quotas vary.

### Retry and ordering

Event Grid handles delivery per its service and destination retry/TTL/delivery policies; applications should be designed for **at-least-once** delivery without relying on global ordering. Events can arrive out of order or be redelivered. If `OrderUpdated` and `OrderCancelled` exist, consumers must track versions/states to avoid overwriting newer state with stale updates.

### Subscription filtering

You can filter by event type, subject, or supported attributes. Hence `type` and `subject` should be consistent and free of sensitive data. Filtering on payload `data` may depend on schema/destination type and feature support; do not design around unverified filter capabilities.

## 16. Azure CLI: Creating an Event Grid Topic Accepting CloudEvents

Examples target **Azure Cloud Shell Bash** or an authenticated Azure CLI session; run only in an authorized lab resource group. Creating a topic may incur charges.

### Check subscription

~~~bash
az account show \
  --query "{subscription:name,id:id,tenantId:tenantId}" \
  --output table
~~~

Set variables:

~~~bash
RG="rg-events-lab"
LOC="southeastasia"
TOPIC="<GLOBALLY_UNIQUE_TOPIC_NAME>"
~~~

**Assumes** the resource group exists, your identity has permission to create Event Grid topics, the topic name is valid, and the region supports the resource type. Check `az eventgrid topic create --help` on your current CLI version before running.

### Create custom topic with CloudEvents input schema

~~~bash
az eventgrid topic create \
  --resource-group "$RG" \
  --name "$TOPIC" \
  --location "$LOC" \
  --input-schema CloudEventSchemaV1_0
~~~

This example targets an **Event Grid custom topic** supporting that schema. Do not run this exact command for an Event Grid Namespace topic without adapting to that resource API.

### Inspect configuration

~~~bash
az eventgrid topic show \
  --resource-group "$RG" \
  --name "$TOPIC" \
  --query "{name:name,location:location,inputSchema:inputSchema,endpoint:endpoint}" \
  --output json
~~~

For real publishing, follow the **endpoint, authentication, and HTTP formatting requirements** of the Event Grid custom topic in use, and configure an event subscription so events have a destination. Do not take a generic HTTP snippet and assume an Azure endpoint accepts any batching, content mode, or token type.

**Never print or store Event Grid access keys in logs, source code, or public guides.** Prefer organization-approved authentication methods with least-privilege permissions.

## 17. CloudEvents in Event Hubs and Service Bus

CloudEvents is a **data format**; brokers and streams retain their own delivery semantics.

| Service | Role | How CloudEvents is used | Architectural notes |
|---|---|---|---|
| **Azure Event Grid** | Event routing/push | Native CloudEvents 1.0 schema on supported ingress/egress | Delivery retries, filtering, do not assume FIFO |
| **Azure Event Hubs** | High-volume ingestion/streaming | Apps serialize CloudEvents into event bodies and deserialize at consumers | Partitions, offsets, consumer groups, retention/replay |
| **Azure Service Bus** | Enterprise message broker, queues/topics | Can carry CloudEvents JSON inside message bodies per app contract | Peek-Lock, DLQ, sessions, per-entity duplicate detection |
| **Azure Queue Storage** | Simple task queue | Can store CloudEvents JSON as string/bytes per app convention | Visibility timeout, pop receipt, no equivalent broker DLQ |

### Event Hubs: partitions and replay

Event Hubs fits when you need **high ingestion throughput, multiple consumer groups, and stream processing**. Message bodies can hold serialized CloudEvents so consumers share a uniform envelope. If ordering within an entity group is needed, choose an appropriate partition key and remember ordering is **per partition**, not across the entire event hub.

Consumer group offsets/checkpoints track read position. **A checkpoint does not mean side effects committed exactly once.** If a consumer writes to a database and crashes before checkpointing, the event can be reprocessed. Idempotency is still required.

### Service Bus: routing and workflows

Service Bus Queue/Topic is useful when you need **Peek-Lock, dead-lettering, sessions, scheduling, or broker workflows**. A Service Bus message can carry CloudEvents JSON, though the Service Bus SDK does not automatically turn arbitrary bodies into CloudEvent objects unless your app parses them or uses a specific integration.

### Avoid confusing Event Grid with Event Hubs

Event Grid is suited for **pushing discrete notifications to subscribers**. Event Hubs is suited for **retaining event streams for multiple consumers to read/replay**. A system can use both, provided you document which stage retries, how long data is retained, and which consumer owns checkpointing.

## 18. Java CloudEvents SDK: Creating Strongly Typed Events

In Java applications, use the **CloudEvents Java SDK** to avoid hand-concatenating JSON envelopes as strings. Common Maven artifacts:

~~~xml
<dependencies>
  <dependency>
    <groupId>io.cloudevents</groupId>
    <artifactId>cloudevents-api</artifactId>
    <version>${cloudevents.version}</version>
  </dependency>
  <dependency>
    <groupId>io.cloudevents</groupId>
    <artifactId>cloudevents-core</artifactId>
    <version>${cloudevents.version}</version>
  </dependency>
  <dependency>
    <groupId>io.cloudevents</groupId>
    <artifactId>cloudevents-json-jackson</artifactId>
    <version>${cloudevents.version}</version>
  </dependency>
</dependencies>
~~~

Declare `cloudevents.version` with a **consistent, organization-tested version**, and verify compatibility with your current JDK and SDKs. This is a `pom.xml` snippet, not a full POM.

### Creating a CloudEvent in Java

~~~java
import io.cloudevents.CloudEvent;
import io.cloudevents.core.builder.CloudEventBuilder;
import io.cloudevents.core.format.EventFormat;
import io.cloudevents.core.provider.EventFormatProvider;
import io.cloudevents.jackson.JsonFormat;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.UUID;

public final class OrderCreatedEventFactory {

    private static final URI SOURCE =
        URI.create("https://events.example.org/commerce/orders");

    public static CloudEvent create(String orderId, String payloadJson) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        return CloudEventBuilder.v1()
            .withId(UUID.randomUUID().toString())
            .withSource(SOURCE)
            .withType("com.example.commerce.order.created.v1")
            .withSubject("orders/" + orderId)
            .withTime(OffsetDateTime.now(ZoneOffset.UTC))
            .withDataSchema(
                URI.create("https://schemas.example.org/commerce/order-created/v1.json")
            )
            .withData(
                "application/json",
                payloadJson.getBytes(StandardCharsets.UTF_8)
            )
            .build();
    }

    public static byte[] toStructuredJson(CloudEvent event) {
        EventFormat format = EventFormatProvider.getInstance()
            .resolveFormat(JsonFormat.CONTENT_TYPE);

        if (format == null) {
            throw new IllegalStateException(
                "CloudEvents JSON format provider is unavailable"
            );
        }
        return format.serialize(event);
    }
}
~~~

This example illustrates **event creation and structured serialization**; it does not yet perform JSON Schema validation, Azure transmission, or permission checks. `UUID.randomUUID()` is suitable when **creating a new event**; if a producer retries **an already created event**, reuse the event ID stored in the outbox instead of calling the factory to generate a new ID.

`payloadJson` must be built with a safe JSON serializer from validated data. **Never** concatenate JSON strings directly from user input and assume validity. The Java CloudEvents SDK assists with event modeling and formatting, but **does not run business validation** simply from a `dataschema` URI.

### Serialization and round-trip testing

~~~java
CloudEvent event = OrderCreatedEventFactory.create(
    "order-1024",
    "{\"orderId\":\"order-1024\",\"currency\":\"VND\",\"totalAmountMinor\":259000,\"items\":[{\"sku\":\"SKU-17\",\"quantity\":2}]}"
);

byte[] wire = OrderCreatedEventFactory.toStructuredJson(event);

EventFormat format = EventFormatProvider.getInstance()
    .resolveFormat(JsonFormat.CONTENT_TYPE);

CloudEvent restored = format.deserialize(wire);

assert restored.getSpecVersion().toString().equals("1.0");
assert restored.getId().equals(event.getId());
assert restored.getSource().equals(event.getSource());
~~~

The snippet above illustrates the assertions to make; in real tests, use **JUnit assertions** rather than Java's built-in `assert` keyword because the JVM may not enable assertions. Beyond round-trip checks, include contract tests for data fields/schemas, consumer tolerance of unknown fields, and duplicate retries.

## 19. Java HTTP Receiver: Reading CloudEvents with Validation

An HTTP receiver may accept structured JSON or binary mode depending on configuration. Minimal logic should:

1. Verify the requester passed endpoint authentication/authorization.
2. Detect content mode via `Content-Type`/headers, then **parse using a CloudEvents protocol binding** supported by your SDK/gateway.
3. Validate `specversion`, `source`, `type`, and `id`.
4. Confirm `type` belongs to the supported contract set.
5. Verify `datacontenttype` and deserialize/validate `data` against JSON Schema.
6. Deduplicate by `source` + `id`.
7. Enqueue the job or execute short processing; persist results before acking.
8. Return a response matching the event delivery system's expectations.

### Do not parse headers manually if the SDK supports it

Code like `request.getHeader("ce-type")` plus reading the body might work for a binary-mode demo, but it **cannot parse structured mode** and easily mishandles MIME types, encodings, or extension attributes.

When using the Java CloudEvents SDK, select the HTTP binding/transport module matching your framework (Spring, Vert.x, servlet, etc.) for your SDK version, and write **contract tests for both modes** if the endpoint claims to support both.

### Data validation is a separate step

Business pseudo-code:

~~~java
void handle(CloudEvent event) {
    validateRequiredContext(event);
    authorizeLogicalSource(event.getSource());
    Contract contract = registry.resolve(
        event.getType(), event.getDataSchema());
    contract.validate(event.getData());

    String dedupKey = event.getSource() + "|" + event.getId();
    if (inbox.alreadyCompleted(dedupKey)) {
        return;
    }

    businessHandler.processIdempotently(event);
    inbox.markCompleted(dedupKey);
}
~~~

Types such as `Contract`, `registry`, `inbox`, and `businessHandler` are **illustrative architectural components**, not built-in SDK classes. Production workflows need transaction/concurrency control so two workers do not simultaneously see “not completed” and execute duplicate side effects.

For HTTP event delivery, ack only after the event is durably persisted or queued per receiver responsibility. Returning 2xx before durable persistence can stop broker retries while the receiver loses data.

## 20. HTTP Smoke Test for Structured Mode

After building a **lab HTTP receiver supporting structured CloudEvents**, save a sample CloudEvent in a test file `event.json` (your **personal lab file**, not a lesson module file to create at this step).

Example Bash calling a test receiver you control:

~~~bash
curl --fail-with-body --silent --show-error \
  --request POST "http://localhost:8080/events" \
  --header "Content-Type: application/cloudevents+json" \
  --data-binary @event.json
~~~

`curl --fail-with-body` requires a supporting curl version; if unavailable, inspect HTTP status and response body using your available tools.

**`http://localhost:8080/events` is only a hypothetical lab receiver**, not a default Azure Event Grid endpoint. When publishing to Azure Event Grid, use the actual resource's **topic endpoint, authentication, request format, and batching rules**—do not swap the host and assume the protocol is identical.

A solid smoke test suite covers:

| Test | Input | Expected behavior |
|---|---|---|
| Valid | CloudEvent with complete context, schema-valid payload | Accepted, result persisted |
| Missing `id` | Event missing required attribute | Rejected |
| Wrong `specversion` | `"2.0"` when only 1.0 is supported | Explicitly rejected/routed |
| Unknown `type` | Unsupported contract | Not silently mishandled |
| Wrong payload type | `totalAmountMinor: "259000"` | Validation failure |
| Duplicate event | Same `source` + `id` redelivered | No duplicate side effects |
| Late event | `time` older than already applied event | Handled via business version |
| JSON binary `data_base64` | Bytes matching media type | Deserialized accurately, not treated as plain string |
| Unauthenticated sender | Missing/invalid credential | Processing denied |
| Receiver crash before ack | Same event delivered again | Idempotency protects state |

## 21. Schema Contract Testing and CI/CD

A good pipeline does not stop at checking whether a JSON Schema file parses. It verifies **producers and consumers share the same meaning**.

~~~mermaid
flowchart TD
  PR["Producer/schema change"] --> LINT["Validate schema syntax + conventions"]
  LINT --> COMP["Compatibility check against published contract"]
  COMP --> PTEST["Producer example contract tests"]
  PTEST --> CTEST["Consumer contract tests"]
  CTEST --> STAGE["Staging: publish, deliver, retry, replay"]
  STAGE --> OK{"Passes criteria?"}
  OK -->|Yes| PUB["Register/version contract, controlled rollout"]
  OK -->|No| FIX["Fix schema or plan migration"]
~~~

### What to store in an event catalog

- Event type, source, and description of producer guarantees.
- Schema URI/version and location of immutable artifacts.
- Owner / owning team and change notification channels.
- List of critical consumers or subscriptions.
- Retention, PII classification, and validation rules.
- Compatibility policy: tolerant readers, required fields, enum handling.
- Event identification and deduplication method, deprecation milestones.
- Examples of valid and invalid events.
- Freshness SLOs, delivery expectations, and replay instructions.

### Key contract tests

1. Producer always emits the four valid context attributes.
2. `source` / `id` stay identical when the same event is retried.
3. `data` conforms to schema and exposes no secrets.
4. Type/version are accurate and older field meanings do not shift.
5. Older consumers still parse events containing **new optional fields** if policy requires it.
6. Consumers handle **unknown new event types** via explicit ignore/DLQ paths without crashing the whole worker.
7. Duplicate deliveries do not trigger side effects twice.
8. Replaying older events does not corrupt newer state.
9. Both HTTP structured and binary modes work if the public contract claims support for both.

## 22. Ordering, Late Events, and Replay

CloudEvents includes `time`, but **no global processing order is guaranteed by the spec itself**. Delivery over Event Grid, Event Hubs, or Service Bus carries different semantics.

Example:

~~~text
T1: OrderCreated
T2: OrderPaid
T3: OrderCancelled

Consumer might receive: OrderPaid -> OrderCreated -> OrderCancelled
or receive OrderCreated twice.
~~~

If a consumer applies last-write-wins by **arrival time**, it can produce corrupted state. Instead consider:

- A monotonically increasing **aggregate version** owned by the producer, e.g., `orderVersion: 3`.
- Idempotent state transitions that accept only valid state moves.
- Partition/session-key ordering where the broker supports it appropriately.
- Bounded buffering/reordering with timeouts in stream processing where applicable.
- Versioned event sourcing/replay and snapshots when the business genuinely needs them.

### Do not use time as an absolute ordering key

Machine clocks drift; two events can share the same timestamp, and deliveries can be delayed. `time` is useful for measuring freshness, **not as a sequence number**. For domains requiring ordering, choose a domain sequence or version with clear semantics.

### Replay and DLQ

When replaying an event from a DLQ or stream retention, preserve the **original ID and source** if it is the same event, and track replay-attempt metadata separately in logs/workflows. Only generate a new ID/type when emitting a **new business event** such as `OrderReprocessed`. Avoid keeping an old ID while silently altering the meaning of `data`.

## 23. Security and Data Protection

CloudEvents metadata is not identity proof. An untrusted caller can craft:

~~~json
{
  "specversion": "1.0",
  "id": "forged",
  "source": "https://events.example.org/payments",
  "type": "com.example.billing.payment.captured.v1",
  "data": {"orderId": "order-1024"}
}
~~~

**Never trust `source` just because the string looks like an internal URL.** Receivers and brokers must verify sender identity/credentials at the transport or gateway layer and check mappings between **authorized identities** and **permitted sources/types**.

### Security layers

1. **Authentication:** Entra ID, managed identity, workload identity, or authentication mechanisms supported by Event Grid/receivers.
2. **Authorization:** producers can only publish types/sources in their scope; consumers only read required subscriptions.
3. **Network:** Private Endpoints, firewalls, VNet integration, DNS, and egress controls per service/SKU.
4. **Transport security:** TLS, hostname/cert validation, and downgrade protection over the wire.
5. **Payload protection:** classify sensitive data, minimize/anonymize, and encrypt per policy.
6. **Schema validation:** reject unknown event types or malformed field types before unsafe execution.
7. **Audit:** log event ID, type, source, and outcome; avoid logging full payloads containing PII.
8. **Retention/deletion:** satisfy enterprise retention, erasure, and replay policies.

### Extension attributes

CloudEvents allows extending context with valid names/values, such as `traceparent` in compatible tracing systems. Prefer community- or tool-standardized extensions, and never arbitrarily add emails, phone numbers, or access tokens to metadata: attributes may be logged or filtered by brokers and gateways.

### Multi-tenant

If an event carries `tenantid`, still verify the producer **is authorized to emit for that tenant** and the consumer is authorized to process it. A string in a header does not replace token claims, RBAC, and business authorization checks.

## 24. Observability: Measuring End-to-End Latency and Success

Track the entire path: **publish → deliver → process → business effect**.

| Metric | Purpose |
|---|---|
| Events produced/s | Detect unexpected producer spikes or drops |
| Publish failure rate | Catch auth, quota, timeout, or network errors |
| Broker delivery attempts | Spot retries or unstable endpoints |
| Event freshness | Processing time minus event `time`, accounting for clock skew |
| Consumer processing duration | Identify business logic bottlenecks |
| Duplicate/drop count | Track deduplication and rejected events |
| Dead-letter/unhandled events | Find unknown schemas, persistent errors, or policy expirations |
| Schema validation failures | Detect producer contract violations |
| End-to-end completed business events | Measure real outcomes, not just HTTP 2xx |
| Costs | Broker, storage, compute, network, and log ingestion |

### Correlation

- `id`: event identity for deduplication.
- `traceparent` / trace context per active tracing standard: links cross-service spans where implemented.
- `correlationId`: business or request-chain ID per organization convention.
- `orderId` / subject: related business aggregate, not a unique event identifier.

Do not overload a single string for all purposes indiscriminately. One order can have many events, one trace can contain many spans, and one event can be delivered multiple times.

### Actionable alerts

- Spike in topic publish errors or event delivery failures.
- DLQ / subscription backlog exceeding thresholds or aged events.
- Schema validation failures after a new release.
- Consumer p95 latency breaching SLO.
- Unusual surge in duplicate events or slow outbox publishing.
- Critical event type stops arriving from a producer within expected windows.
- Operations/logging costs rising faster than completed business volume.

When building Azure Monitor dashboards, retrieve **metric definitions from the exact Event Grid / Event Hubs / Service Bus resource type**; do not assume metric names are identical across services.

## 25. Performance, Event Size, and Cost

### Envelope overhead

CloudEvents adds metadata attributes, making messages slightly larger than bare JSON payloads. This overhead is usually worthwhile for observability and interoperability, though in high-volume telemetry streams you should measure average event size, batching strategy, and broker/storage costs.

### Do structured and binary modes differ in real cost?

They differ in how metadata and payloads are laid out; **neither mode is universally faster or cheaper** without measuring network, serialization, HTTP headers, batching, and broker/receiver limits. Optimize first for **compatibility and operational simplicity**.

### Cost drivers

- Event Grid events, operations, and deliveries per pricing tier and resource type.
- Event Hubs namespace/throughput or capacity, retention, and consumer processing.
- Service Bus tier, operations, subscriptions/forwarding, and capacity.
- Blob Storage when using claim-check or long-term payload retention.
- Azure Functions, Container Apps, AKS, or VMs processing events.
- Application Insights / Log Analytics, distributed tracing, and log retention.
- Network transfer, Private Endpoints, Firewall/NAT, and cross-region replication.
- Retries, duplicate deliveries, schema errors, and replays.

Calculate **cost per successfully processed business event**, not just the cost of a single publish request. If a schema bug triggers thousands of retries, compute and logging costs can easily exceed original transport costs.

## 26. Troubleshooting: Schema Error or Transport Error?

| Symptom | Possible cause | How to investigate |
|---|---|---|
| Receiver reports missing `specversion` | JSON is not a CloudEvent or wrong parse mode | Inspect structured body, binary headers, and Content-Type |
| HTTP 415 Unsupported Media Type | Sender used incompatible Content-Type | Check `application/cloudevents+json` vs. binary body media type |
| HTTP 400 invalid CloudEvent | Missing `id`/`source`/`type`, invalid timestamp, malformed data | Validate envelope and JSON serialization |
| Valid JSON but business failure | Missing required fields, wrong units/enum | Check JSON Schema and semantic contract |
| Event Grid topic rejects event | Input schema / resource API / auth mismatch | Verify topic `inputSchema`, endpoint, permissions, format |
| Consumer receives no events | Wrong subscription filter or failing endpoint | Inspect type/subject, subscription state, delivery metrics |
| Duplicate events arrive | Retries, timeouts, DLQ replay | Deduplicate `source`+`id`, enforce business idempotency |
| Consumer misses event after DB commit | Publish failure window | Implement transactional outbox + check publisher health |
| Events processed out of order | Broker delivery lacks global ordering | Use aggregate version, session/partition design |
| Data parsed as a string | JSON object double-serialized | Fix `data` JSON and deserializer |
| Consumer fails on binary payload | Invalid Base64 or media type | Inspect `data_base64`, `datacontenttype`, and decoded bytes |
| Broken distributed tracing | Trace context or correlation not propagated | Check extension headers/metadata and sampling |
| 403 on publish | Missing permissions, SAS/token, or firewall | Verify identity, RBAC, resource access, and error details |
| Event Hubs replay creates duplicates | Consumer checkpoint decoupled from side effects | Use inbox/idempotency and proper checkpoint strategy |
| Schema URI unreachable | Broken link, DNS/firewall, or registry design | Check artifact retention, catalog, and local schema cache |
| Costs jump after enabling debug | Logging full payloads, retries, or stream throughput | Check Cost Management, telemetry sampling, and retention |

**Recommended investigation order:** CloudEvents format → transport/binding → authentication → source/type/schema → broker routing → consumer validation → idempotency/business side effects → monitoring/cost.

## 27. Case Study: Order Lifecycle with CloudEvents

### Context

A retail system running on Azure has:

- Order API and Orders Database.
- Event Grid for announcing order state changes.
- Billing, Inventory, Email, and Analytics consumers.
- Blob Storage for large files or reports.
- Java Azure Functions / Container Apps as consumers.
- Entra ID permissions and private networking per policy.

Requirement: events must be clearly identifiable, replayable/auditable, and never issue duplicate invoices on broker retries.

### Contract design

| Event | When emitted | Consumers | Minimal data |
|---|---|---|---|
| `OrderCreated.v1` | Order committed | Billing, Inventory, Analytics | orderId, currency, total, items |
| `PaymentCaptured.v1` | Payment gateway confirms capture | Order, Analytics | orderId, paymentRef, amount |
| `InventoryReserved.v1` | Stock reserved successfully | Fulfillment | orderId, reservationRef |
| `OrderCancelled.v1` | Order cancellation committed | Billing, Inventory, Email | orderId, reasonCode, aggregateVersion |

Table names are shortened for readability; wire `type` values should use full namespaced conventions like `com.example.commerce.order.created.v1`.

### Key design choices

1. **Event ID separate from order ID:** every new event gets its own `id`; retries of the same event keep that ID.
2. **Version-immutable schemas:** `dataschema` points to v1/v2 contracts that never mutate silently.
3. **Outbox:** Orders Database and event records commit in the same transaction.
4. **Independent consumers:** each consumer deduplicates and manages errors/timeouts independently.
5. **No global FIFO:** `aggregateVersion` prevents stale updates from overwriting newer state.
6. **Replay:** preserve original IDs for the same event, with governance and observability.
7. **Security:** Billing never blindly trusts a spoofed `PaymentCaptured`; it verifies source identity and business state.
8. **SLO:** define latency from order commit to Billing completion.
9. **DLQ/runbook:** schema-invalid events or persistently failing consumers have isolation targets and owners.

### Processing flow

~~~mermaid
flowchart LR
  ORDER["Order API"] --> DB["Orders DB + outbox"]
  DB --> PUB["Outbox publisher"]
  PUB --> GRID["Event Grid CloudEvents 1.0"]
  GRID --> SUB1["Billing consumer"]
  GRID --> SUB2["Inventory consumer"]
  GRID --> SUB3["Analytics consumer"]
  SUB1 --> BDB["Billing DB + inbox"]
  SUB2 --> IDB["Inventory DB + inbox"]
  SUB3 --> AD["Analytics store"]
~~~

This is a logical diagram and does not imply Event Grid has a durable inbox or a Service Bus-style DLQ. Error storage and retry behavior must be configured according to actually supported destination/delivery features, or paired with an appropriate broker/storage.

## 28. Synthesis Exercise

### Part A — Define an event

Design `DocumentProcessed` for a system ingesting PDF files:

1. Choose a stable domain-based `source`, not a VM/pod hostname.
2. Choose a namespaced `type` and versioning strategy.
3. Generate a unique `id` when emitting new events.
4. Set `subject` as a document reference without unnecessary PII.
5. Format `time` in UTC RFC 3339.
6. Include `data` with documentId, status, outputBlobRef, size, and checksum.
7. Write a JSON Schema for the payload; specify required and optional fields.
8. Point `dataschema` to the versioned schema URI.
9. Write one valid event and at least three invalid events.

### Part B — CloudEvents HTTP

1. Convert the event to **structured JSON** with `application/cloudevents+json`.
2. Convert the same event to **binary HTTP** with `ce-specversion`, `ce-id`, `ce-source`, `ce-type`, and body data.
3. Explain why `Content-Type` differs between the two modes.
4. Build a lab receiver or use an authorized test receiver.
5. Verify parsing works for both modes if the receiver advertises dual support.
6. Test events with missing `source`, malformed `time`, and schema-invalid payloads.
7. Verify redelivering the same event produces no duplicate outputs.

### Part C — Azure Integration

1. Verify authorized subscription, resource group, and region.
2. Create an **Event Grid custom topic** with CloudEvents input schema in the lab if appropriate.
3. Create a subscription targeting an endpoint supporting the matching delivery schema, validation, and auth.
4. Publish a test event using the Event Grid resource's authentication mechanism.
5. Inspect delivery success/failure/retry metrics and consumer logs.
6. Create a v1 event variant adding an optional field; test older consumers.
7. Create a breaking variant changing a field's type; demonstrate how older consumers reject or misprocess it without versioning.
8. Practice outbox/inbox on a lab database or transactional mock.
9. Evaluate **Event Hubs** if large stream replay is needed, or **Service Bus** if DLQ/session/broker transactions are needed.
10. Clean up lab resources, check costs, and avoid impacting shared subscriptions.

### Self-Check Questions

**Question 1.** What are the four required CloudEvents 1.0 attributes?

**Question 2.** How do `specversion` and `dataschema` represent two different types of versioning?

**Question 3.** Why is `source` neither a guarantee of a callable endpoint nor proof of authentication?

**Question 4.** Can the same `orderId` have multiple event IDs? Which ID is used when retrying the same event?

**Question 5.** What is the difference between `data`, `data_base64`, and `datacontenttype`?

**Question 6.** Where do structured mode and HTTP binary mode place CloudEvents metadata? What role does `Content-Type` play?

**Question 7.** Why does JSON Schema validation for `data` not replace validation of CloudEvents context attributes?

**Question 8.** Is adding an optional field always backward-compatible with every consumer? What condition must hold?

**Question 9.** When changing `totalAmountMinor` from a number to a string, how should versioning be handled?

**Question 10.** Does CloudEvents guarantee ordering or exactly-once delivery? If not, what must the application do?

**Question 11.** When a database commits but the producer crashes before publishing, which pattern should be used?

**Question 12.** How do Event Grid, Event Hubs, and Service Bus differ in their transport/broker/stream roles?

**Question 13.** Why does `dataschema` not automatically make Azure Schema Registry fetch and validate payloads?

**Question 14.** When a consumer receives `PaymentCaptured` with an internal-looking `source`, what must it verify before trusting it?

**Question 15.** How does replaying an old event differ from emitting a new business event in terms of `source` and `id`?

**Completion criteria:** learners can design valid CloudEvents 1.0 messages with JSON Schema and a versioning policy; distinguish structured/binary HTTP modes; explain Event Grid/Event Hubs/Service Bus roles; build a Java serializer/test suite; and explain idempotency, outbox, replay, security, and monitoring.

## Conclusion

**Designing an event schema** establishes a durable business contract between producers and consumers, while **CloudEvents** standardizes event context representation using attributes like `specversion`, `id`, `source`, and `type`. JSON Schema validates payload structure; versioning strategies and contract tests protect consumers as systems evolve.

On Azure, you can use CloudEvents with **Event Grid** for event routing, or carry serialized CloudEvents over **Event Hubs/Service Bus** when streaming or broker capabilities are required. However, **CloudEvents does not provide exactly-once delivery, ordering, authentication, or business validation on its own**. Production architectures must pair it with **outbox/inbox patterns, idempotent consumers, versioned data, identity/network controls, monitoring, replay, and schema governance**. Clarifying these boundaries upfront lets Azure systems scale across multiple services while preserving data meaning, preventing integration bugs, and keeping operational costs under control.
