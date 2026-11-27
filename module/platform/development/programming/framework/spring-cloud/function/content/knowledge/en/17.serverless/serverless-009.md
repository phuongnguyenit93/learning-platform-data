# Comparing CloudEvents, Event Types, and Supported Runtime Generations

> **Chapter:** Serverless  
> **Module:** SPRING_CLOUD_FUNCTION  
> **Scope:** Standardize event envelopes using CloudEvents, distinguish event types from payload schema versions, compare event formats across AWS, Azure, and Google Cloud, and choose compatible Java runtime generations when deploying the same Spring Cloud Function logic.  
> **Runtime information baseline:** November 24, 2026. Runtime support tables may change by operating system, hosting plan, region, and each provider's deprecation schedule.

## 1. Why Do We Need a Common Standard for Events?

In an event-driven system, a business event can originate from many sources: a file created in object storage, a message published to a broker, a database record change, or a service completing a job. Each cloud provider typically defines its own envelope to describe events.

For example, a file-created event can appear in different forms:

- Azure Event Grid uses `eventType`, `eventTime`, `topic`, and `dataVersion` in the Event Grid schema; when CloudEvents is selected, fields are represented in the CloudEvents envelope.
- Google Eventarc delivers CloudEvents over HTTP; attributes like `ce-id`, `ce-source`, and `ce-type` reside in HTTP headers in binary mode.
- AWS EventBridge uses `detail-type`, `source`, `id`, and `detail` in the EventBridge event envelope. Input transformers can convert events to CloudEvents before sending to an API destination.

If a business function reads each platform's envelope directly, the code becomes coupled to the provider. Switching triggers or adding an event source forces mapping and test changes.

**CloudEvents standardizes event metadata and packaging. It does not standardize entire business payloads, replace brokers, or dictate delivery semantics.**

In Spring Cloud Function, the goal is to keep business beans as `Supplier`, `Function`, or `Consumer`. The adapter layer receives the provider envelope, translates the event into an application-level representation, and invokes the function through `FunctionCatalog`. When changing platforms, the adapter changes while business logic stays intact.

## 2. What CloudEvents Is and What It Is Not

CloudEvents is an open specification under the Cloud Native Computing Foundation defining a consistent way to describe event metadata. The spec separates two parts:

1. **Context attributes:** describe what the event is, where it came from, how it is identified, and which subject it concerns.
2. **Event data:** the payload carrying business information or occurrence details.

Example of an order-created event:

~~~json
{
  "specversion": "1.0",
  "id": "evt-2026-00042",
  "source": "urn:acme:commerce:orders",
  "type": "com.acme.order.created.v1",
  "subject": "orders/ORD-42",
  "time": "2026-11-24T09:15:00Z",
  "datacontenttype": "application/json",
  "dataschema": "https://schemas.acme.example/orders/order-created-v1.json",
  "data": {
    "orderId": "ORD-42",
    "customerId": "CUS-18",
    "total": 1250000,
    "currency": "VND"
  }
}
~~~

This envelope can travel over HTTP, brokers, or event routers. Consumers can inspect metadata without needing to understand the entire payload first.

CloudEvents does **not** specify:

- How long a broker must retain events.
- Whether events are delivered once or multiple times.
- Whether events are processed in order.
- How many times a consumer must retry.
- How producers are authenticated or consumers authorized.
- The concrete business schema inside `data`.
- How a provider maps every internal event to CloudEvents.

Thus, a valid CloudEvent can still arrive multiple times, arrive late, or carry a payload version a consumer does not yet support. Retry, idempotency, ordering, security, and schema compatibility policies still require explicit design.

## 3. Four Required Attributes of CloudEvents

Every CloudEvent must include these four context attributes:

| Attribute | Meaning | Example |
| --- | --- | --- |
| `id` | Identifies the event within the producer's scope. | `evt-2026-00042` |
| `source` | URI-reference identifying the context in which the event occurred. | `urn:acme:commerce:orders` |
| `specversion` | CloudEvents specification version used to interpret context. | `1.0` |
| `type` | Event type describing the occurrence that happened. | `com.acme.order.created.v1` |

### 3.1. `id` and `source` Must Be Evaluated Together

The producer must ensure the combination `source` + `id` is unique for each distinct event. If the same event is resent due to a network error, the producer may keep the same ID.

For example:

- First event: `source=urn:acme:orders`, `id=evt-42`.
- Redelivery: same `source` and `id`.
- New event for another order: must have a different ID.

Consumers can use the `(source, id)` pair as a deduplication key. Avoid using `id` alone when multiple producers might emit colliding IDs.

`id` identifies a single event occurrence; `subject` identifies the target object within the source's context. These two attributes are not interchangeable.

### 3.2. `source` Is Context, Not a URL to Fetch Payload

`source` is usually an absolute URI or URI-reference defined by the producer. It can be a URI, URN, or a meaningful system path.

Examples:

- `urn:acme:commerce:orders`
- `https://events.acme.example/inventory`
- `//storage.googleapis.com/projects/_/buckets/orders-archive`

Consumers should never blindly issue an HTTP GET to the `source` value. It is an event context identifier, not a guaranteed reachable endpoint.

### 3.3. `specversion` Is Not the Java Version or Payload Version

For CloudEvents 1.0, `specversion` is `1.0`. It tells consumers which specification version governs the envelope.

Never change `specversion` to `21` on Java 21 or `25` on Java 25. JDK version, provider runtime version, and CloudEvents version are three independent concepts.

### 3.4. `type` Is the Event Classification Contract

`type` describes the kind of occurrence. Producers define this name; consumers use it for routing, filtering, authorization policies, metrics, or decoder selection.

A common convention uses reverse-DNS namespaces with a version suffix:

- `com.acme.order.created.v1`
- `com.acme.order.cancelled.v1`
- `com.acme.inventory.reserved.v2`

This is an application design convention, not a mandatory CloudEvents naming format. What matters is that `type` stays stable, unambiguous, and paired with a clear payload contract.

## 4. Optional Attributes and Extension Attributes

CloudEvents defines common optional attributes:

| Attribute | Purpose | Example |
| --- | --- | --- |
| `subject` | Subject referenced within the source's context. | `orders/ORD-42` |
| `time` | Occurrence timestamp in RFC 3339 format. | `2026-11-24T09:15:00Z` |
| `datacontenttype` | Media type of event data. | `application/json` |
| `dataschema` | URI identifying the schema that `data` conforms to. | `https://schemas.acme.example/order-v1.json` |

Not every event needs every optional attribute. However, if consumers filter by subject, inspect timestamps, or decode payloads by schema, producers should emit the corresponding attributes consistently.

### 4.1. Extension Attributes

CloudEvents allows extension attributes to carry metadata outside the core specification. For example:

~~~json
{
  "specversion": "1.0",
  "id": "evt-42",
  "source": "urn:acme:orders",
  "type": "com.acme.order.created.v1",
  "tenantid": "tenant-7",
  "traceid": "trace-abc",
  "region": "ap-southeast-1",
  "data": {
    "orderId": "ORD-42"
  }
}
~~~

Extension names must follow CloudEvents naming rules. Use short, lowercase, meaningful names and avoid colliding with core attributes.

Extensions represent event-level metadata. Never stuff entire business payloads, authentication tokens, or personal data into extensions. Intermediaries can inspect, route, or log context attributes.

### 4.2. Do Not Turn Extensions into Per-Team Ad-Hoc Schemas

If every team invents fields like `tenant`, `tenant_id`, `tenantId`, and `org` for the same concept, interoperability breaks down.

Standardize:

- Extension name.
- Data type.
- Allowed value range.
- Which producer emits it.
- Which consumers may read it.
- Whether intermediaries preserve or strip extensions when forwarding events.

Unknown extensions should still be handled safely by consumers. If unused, consumers can ignore them; proxies/intermediaries should preserve extensions unaltered when feasible.

## 5. Distinguishing Event Type, Spec Version, and Data Schema Version

These three concepts are easily confused:

| Concept | Question it answers | Example |
| --- | --- | --- |
| CloudEvents `specversion` | Which spec version does the envelope follow? | `1.0` |
| CloudEvents `type` | Which business occurrence happened? | `com.acme.order.created.v1` |
| `dataschema` or app schema convention | Which structure does the payload data follow? | `order-created-v1.json` |

`specversion` generally stays `1.0` even as an application publishes many event types and payload versions.

### 5.1. When Should You Bump the Version in `type`?

When a change alters how consumers interpret the occurrence's meaning, introduce a new type, such as:

- `com.acme.order.created.v1`
- `com.acme.order.created.v2`

This is a producer/consumer contract decision. Not every payload addition forces a new event type.

### 5.2. When Should You Update `dataschema`?

If `type` still represents the same occurrence while the payload structure evolves under independently managed schemas, the producer updates `dataschema` per the system's versioning policy.

Consumers must either support multiple schema versions or reject/quarantine unsupported schemas. Never rely solely on JSON parsing succeeding: JSON can parse cleanly while a field's semantics changed.

### 5.3. Payload Evolution Rules

A safe evolution strategy typically includes:

1. Prefer adding optional fields rather than changing existing field semantics.
2. Have consumers ignore unknown fields when permitted by the contract.
3. Never change the data type of an active field without a migration plan.
4. Use a schema registry or versioned schema docs when multiple producers/consumers coordinate.
5. Maintain contract tests for every supported version.
6. Log and track event types and schema versions in observability telemetry.

CloudEvents gives you a place to declare the schema; it does not validate business-schema compatibility automatically.

## 6. CloudEvents Content Modes

The CloudEvents HTTP protocol binding defines content modes. The two most important modes in HTTP integrations are **structured** and **binary**. Batch mode applies only when both the event format and binding support it.

### 6.1. Structured Mode

Structured mode places the entire event envelope—both context attributes and data—inside a single body.

Example HTTP request:

~~~http
POST /events HTTP/1.1
Content-Type: application/cloudevents+json

{
  "specversion": "1.0",
  "id": "evt-42",
  "source": "urn:acme:orders",
  "type": "com.acme.order.created.v1",
  "datacontenttype": "application/json",
  "data": {
    "orderId": "ORD-42"
  }
}
~~~

Characteristics:

- A single JSON object carries both metadata and payload.
- Envelope `Content-Type` is `application/cloudevents+json`.
- Easy to archive, store as fixtures, and forward over HTTP.
- Consumers must decode the envelope before reading `data`.

Structured mode fits well when you want a self-contained representation of the event to store, replay, or forward to an API destination.

### 6.2. Binary Mode

Binary mode puts context attributes in HTTP headers while placing event data directly in the request body.

Example:

~~~http
POST / HTTP/1.1
Content-Type: application/json
ce-specversion: 1.0
ce-id: evt-42
ce-source: urn:acme:orders
ce-type: com.acme.order.created.v1
ce-subject: orders/ORD-42

{
  "orderId": "ORD-42"
}
~~~

Characteristics:

- Context attributes map to `ce-`-prefixed HTTP headers.
- The body holds event data alone.
- `Content-Type` describes the media type of the data (e.g., `application/json`).
- Adapters can map headers into Spring Message headers and the body into the payload.

**Binary mode does not require the payload to be a raw binary byte array.** The payload can be JSON, text, or binary; the mode name refers to separating metadata from data.

### 6.3. Batch Mode

Batch mode packs multiple CloudEvents into a single message. Events within a batch remain independent and need not share the same `source` or `type`, though all events in one batch must share the same `specversion`.

Not every event format or protocol binding supports batching. Never assume an arbitrary JSON array is a valid CloudEvents batch; verify the exact format and transport binding.

### 6.4. Comparing Content Modes

| Criterion | Structured | Binary | Batch |
| --- | --- | --- | --- |
| Metadata | Inside the body envelope. | Inside HTTP headers. | Inside each event in the batch format. |
| Payload | Inside `data` or `data_base64`. | Directly in the body. | Each event carries its own data. |
| `Content-Type` | `application/cloudevents+json` for JSON format. | Media type of event data. | Per batch event format. |
| Best suited for | APIs, storage, replay, API destinations. | HTTP event receivers, Eventarc. | Optimizing multi-event delivery when supported by binding. |
| Risks | Requires envelope decoding. | Proxies may filter or normalize headers. | One bad event can affect batch handling. |

## 7. Comparing Event Envelopes Across AWS, Azure, and Google Cloud

Cloud platforms do not emit one identical envelope across all services. Identify both the **provider event format** and the **CloudEvents binding** used by your trigger.

### 7.1. AWS EventBridge and Lambda

Default EventBridge events use their own envelope, typically containing:

~~~json
{
  "version": "0",
  "id": "event-id-42",
  "detail-type": "Object Created",
  "source": "aws.s3",
  "account": "123456789012",
  "time": "2026-11-24T09:15:00Z",
  "region": "ap-southeast-1",
  "resources": [
    "arn:aws:s3:::orders-archive"
  ],
  "detail": {
    "bucket": {
      "name": "orders-archive"
    },
    "object": {
      "key": "ORD-42.json"
    }
  }
}
~~~

Key points:

- EventBridge's `version` is not CloudEvents `specversion`.
- `detail-type` is EventBridge's event classifier; it is not automatically a CloudEvents `type`.
- `detail` carries the event-source-specific payload.
- EventBridge can use an input transformer to convert events into structured CloudEvents before sending to API destinations.
- If consumers expect CloudEvents, define explicit mappings and send `Content-Type: application/cloudevents+json`.

Example application-level mapping:

| EventBridge | CloudEvents | Notes |
| --- | --- | --- |
| `id` | `id` | Can keep source ID if unique alongside `source`. |
| `source` | `source` | Choose a stable producer URI-reference. |
| `detail-type` | `type` | Translate to a namespaced type per application contract. |
| `time` | `time` | Preserve timestamp if valid RFC 3339. |
| `detail` | `data` | Detailed event payload. |
| `region`, `account` | Extension attributes | Add only if consumers need this metadata. |
| `version` | Do not map directly to `specversion` | This is EventBridge's envelope version. |

AWS Lambda can receive events from EventBridge, SQS, S3, API Gateway, and more. Event source mappings and integrations deliver distinct payload shapes to handlers. Never assume every event arriving at Lambda is already a CloudEvent.

With Spring Cloud Function, place the translation from EventBridge/SQS envelopes into the application's event model inside the adapter. Business beans should not depend on `detail-type` field names or provider-specific `Records[]` layouts.

### 7.2. Azure Event Grid

Azure Event Grid supports two common schemas:

1. **Event Grid schema:** Azure's proprietary format with fields like `eventType`, `eventTime`, `topic`, `dataVersion`, `metadataVersion`, `id`, and `data`.
2. **CloudEvents schema:** JSON implementation of CloudEvents v1.0 supporting the HTTP protocol binding.

Example Blob Created CloudEvent:

~~~json
{
  "specversion": "1.0",
  "type": "Microsoft.Storage.BlobCreated",
  "source": "/subscriptions/sub-1/resourceGroups/rg-demo/providers/Microsoft.Storage/storageAccounts/acmefiles",
  "id": "9aeb0fdf-c01e-0131-0922-9eb54906e209",
  "time": "2026-11-24T09:15:00Z",
  "subject": "blobServices/default/containers/orders/blobs/ORD-42.json",
  "data": {
    "api": "PutBlockList",
    "contentType": "application/json",
    "contentLength": 812,
    "url": "https://acmefiles.blob.core.windows.net/orders/ORD-42.json"
  }
}
~~~

Differences when comparing Event Grid schema and CloudEvents:

| Event Grid schema | CloudEvents | Meaning |
| --- | --- | --- |
| `id` | `id` | Event identifier. |
| `topic` | `source` | Event-source context; preserve accurate semantics. |
| `eventType` | `type` | Occurrence type. |
| `eventTime` | `time` | Event timestamp. |
| `subject` | `subject` | Target object within source context. |
| `data` | `data` | Business payload. |
| `dataVersion` | `dataschema` or type/extension convention | Do not map automatically without an agreed contract. |
| `metadataVersion` | `specversion`? | Do not map directly. `metadataVersion` is Event Grid's schema metadata version; `specversion` is the CloudEvents spec version. |

Event Grid supports CloudEvents schema for both input and output, and can translate Event Grid schema to CloudEvents on event subscriptions. Event Grid schema cannot represent arbitrary CloudEvents extension attributes, so never treat both schemas as mere field-renamed equivalents.

With Azure Functions, verify the exact trigger and extension. Documentation shows Event Grid triggers can bind CloudEvents in certain programming models. For Java, check parameter types and supported Java Event Grid extension versions in your project; with HTTP triggers, the adapter can receive HTTP CloudEvents and translate them to Spring Messages.

### 7.3. Google Eventarc and Cloud Run Functions

Eventarc delivers events to targets over HTTP in CloudEvents 1.0 **binary mode**. Context attributes map to headers:

| HTTP header | CloudEvents attribute |
| --- | --- |
| `ce-id` | `id` |
| `ce-source` | `source` |
| `ce-specversion` | `specversion` |
| `ce-type` | `type` |
| `ce-time` | `time` (if present) |
| `ce-subject` | `subject` (if present) |

Example Pub/Sub event:

~~~http
POST / HTTP/1.1
Content-Type: application/json; charset=utf-8
ce-specversion: 1.0
ce-id: 2070443601311540
ce-source: //pubsub.googleapis.com/projects/demo/topics/orders
ce-type: google.cloud.pubsub.topic.v1.messagePublished
ce-time: 2026-11-24T09:15:00Z

{
  "message": {
    "data": "eyJvcmRlcklkIjoiT1JELTQyIn0=",
    "messageId": "2070443601311540",
    "publishTime": "2026-11-24T09:15:00Z",
    "attributes": {
      "producer": "checkout"
    }
  },
  "subscription": "projects/demo/subscriptions/orders-worker"
}
~~~

Here, the body carries a data message per the Pub/Sub event type's schema. `message.data` is Base64-encoded; the consumer must decode that inner payload per application contract. CloudEvents does not automatically decode nested Base64 fields.

Common Eventarc event types:

| Source | CloudEvents `type` | Data message |
| --- | --- | --- |
| Pub/Sub | `google.cloud.pubsub.topic.v1.messagePublished` | `MessagePublishedData` |
| Cloud Storage | `google.cloud.storage.object.v1.finalized` | `StorageObjectData` |
| Cloud Storage | `google.cloud.storage.object.v1.deleted` | `StorageObjectData` |
| Firestore | `google.cloud.firestore.document.v1.created` or corresponding types | `DocumentEventData` |
| Cloud Audit Logs | `google.cloud.audit.log.v1.written` | `LogEntryData` |

Always retrieve event type names and data schemas from Eventarc's official event types catalog rather than guessing from service names. Multiple event types can share the same data message while the envelope `type` distinguishes the occurrence.

### 7.4. Provider Summary Table

| Criterion | AWS EventBridge | Azure Event Grid | Google Eventarc |
| --- | --- | --- | --- |
| Default envelope | EventBridge event schema. | Event Grid schema, or CloudEvents when configured. | CloudEvents 1.0. |
| Native CloudEvents over HTTP | Can transform to structured CloudEvents before sending to API destinations. | Supports CloudEvents JSON v1.0 and HTTP binding. | Sends CloudEvents via HTTP binary mode. |
| Source type field | `detail-type` | `eventType` or CloudEvents `type` | `ce-type` |
| Source payload | `detail` | `data` | HTTP body; depends on event type. |
| Needs mapping adapter? | Yes when using EventBridge schema. | Yes for Event Grid schema; less so when configured for CloudEvents. | Still needs data decoding and conversion to app models. |
| What to verify | Event source, target input transformer, Lambda event type. | Input/output schemas, trigger extensions, `dataVersion`. | Event type, source, binary headers, data schema, nested Base64. |

## 8. Event Type Is Not Function Name

An event of type `com.acme.order.created.v1` might be handled by functions named `processOrderCreated`, `auditOrder`, or `notifyWarehouse`. The two concepts serve different purposes:

- Event type describes the business occurrence.
- Function name identifies a bean or function definition in the application.
- Routing policy decides which event type maps to which function.

Example mapping:

| CloudEvents `type` | Spring Cloud Function bean |
| --- | --- |
| `com.acme.order.created.v1` | `processOrderCreated` |
| `com.acme.order.cancelled.v1` | `processOrderCancelled` |
| `com.acme.inventory.reserved.v1` | `processInventoryReserved` |

Never pass raw producer-supplied `type` strings directly as bean names, letting arbitrary events invoke any function. Use an explicit allowlist mapping so untrusted events cannot hijack internal routing.

A function router may dispatch based on `ce-type`, provided it authenticates the event and checks the type against supported allowlisted routes before lookup.

## 9. Runtime Generation and Java Version Are Two Independent Axes

When deploying serverless workloads, separate:

1. **Runtime generation / host:** the execution environment generation managed by the cloud provider.
2. **Java runtime version:** the JDK version executing the function.
3. **Operating system / base image:** e.g., Amazon Linux 2, Amazon Linux 2023, Google buildpack stacks, or Azure's managed Linux image.
4. **Framework version:** Spring Boot, Spring Cloud Function, Spring Integration, and CloudEvents libraries.
5. **Event format version:** CloudEvents `specversion` or business event schemas.

These axes interact through compatibility, yet none substitutes for another. Selecting Java 25 does not automatically migrate an app to a newer generation; upgrading the Azure Functions host to v4 does not change CloudEvents `specversion`.

## 10. Java Runtime Matrix by Cloud Provider (as of November 24, 2026)

### 10.1. AWS Lambda

AWS uses a runtime identifier and underlying OS to specify Java execution environments.

| Java | Runtime identifier | Operating system | Status notes |
| --- | --- | --- | --- |
| Java 25 | `java25` | Amazon Linux 2023 | Current runtime. |
| Java 21 | `java21` | Amazon Linux 2023 | Current runtime. |
| Java 17 | `java17.al2023` | Amazon Linux 2023 | AL2023 option available. |
| Java 11 | `java11.al2023` | Amazon Linux 2023 | AL2023 option available. |
| Java 8 | `java8.al2023` | Amazon Linux 2023 | AL2023 option available. |
| Java 17 | `java17` | Amazon Linux 2 | Legacy; different deprecation schedule from AL2023. |
| Java 11 | `java11` | Amazon Linux 2 | Legacy; different deprecation schedule from AL2023. |
| Java 8 | `java8.al2` | Amazon Linux 2 | Legacy; different deprecation schedule from AL2023. |

AWS runtime documentation currently lists deprecation dates for AL2023 Java runtimes as June 30, 2029, and for AL2 Java runtimes as June 30, 2027. Function create/update block dates may differ from deprecation dates, so inspect every lifecycle column when planning upgrades.

Notes:

- `java17` and `java17.al2023` are two distinct runtime identifiers.
- Java 25 and Java 21 run on Amazon Linux 2023.
- For container images, your team manages the base image, JDK, and patches; do not apply managed-runtime schedules mechanically.
- Lambda's event source still dictates the payload passed to the handler; upgrading the JDK never turns an envelope into CloudEvents.

### 10.2. Azure Functions

At the reference baseline, Azure Functions supports only **Functions host runtime 4.x**. Host runtimes 2.x and 3.x are retired; older apps require migration.

Java versions listed by Azure docs at GA level:

| Java | Support level | Supported until |
| --- | --- | --- |
| Java 25 | GA | May 2029 |
| Java 21 | GA | September 2028 |
| Java 17 | GA | September 2027 |
| Java 11 | GA | September 2027 |
| Java 8 | GA | September 2027 |

Note a critical hosting-plan constraint: **Java 21 is the newest Java version supported on the Linux Consumption plan**. Newer Java releases are not added to that plan; if you need Java 25, choose a supported hosting plan.

Additionally:

- Functions host version is configured via settings like `FUNCTIONS_EXTENSION_VERSION`.
- The Java version in `pom.xml` must match the Java runtime configured on the function app.
- Trigger/binding extensions have independent lifecycles and version requirements.
- The Java programming model uses `@FunctionName`-annotated methods; triggers and bindings govern how events enter the method.
- Event Grid CloudEvents schema does not guarantee identical Java parameter types across every trigger extension. Verify Java bindings/extensions or receive HTTP CloudEvents directly.

Do not confuse Functions host v4.x with Java 21 or CloudEvents 1.0; they are three separate versions.

### 10.3. Google Cloud Run Functions

Google now uses the name **Cloud Run functions** for its Cloud Run-backed generation. Runtime docs distinguish `1st gen` and `Run functions`.

| Java | Runtime generation | Runtime ID | Base image stack | Deprecation |
| --- | --- | --- | --- | --- |
| Java 25 | Run functions | `java25` | `google-24` / `google-24-full` | October 2031 |
| Java 21 | Run functions | `java21` | `google-22` / `google-22-full` | September 2031 |
| Java 17 | 1st gen and Run functions | `java17` | `google-22` / `google-22-full` | October 2027 |
| Java 11 | 1st gen and Run functions (decommissioned) | `java11` | `google-18-full` | Decommissioned October 31, 2025 |

Key points:

- Java 25 and Java 21 belong to the Run functions generation.
- Java 17 remains listed for both 1st gen and Run functions.
- Java 11 is decommissioned; never choose it for new workloads.
- The base image stack is also part of the runtime; `google-24` and `google-22` are not Java versions.
- Eventarc sends CloudEvents 1.0 over HTTP binary mode; function generation does not alter the CloudEvents envelope.

### 10.4. Runtime Generation Comparison

| Provider | Generation / host concept | Current Java choices | Migration notes |
| --- | --- | --- | --- |
| AWS Lambda | Managed runtime ID + OS generation AL2/AL2023 | Java 25, Java 21 on AL2023 | Prefer AL2023; distinguish legacy vs. current runtime IDs. |
| Azure Functions | Functions host 4.x | Java 25, Java 21, Java 17, Java 11, Java 8 by plan | Host 2.x/3.x retired; Linux Consumption caps at Java 21. |
| Google Cloud Run functions | 1st gen and Run functions | Java 25, Java 21 on Run functions; Java 17 on both | Move new workloads to Run functions; Java 11 is decommissioned. |

**Recommended shared baseline:** Java 21 is the practical common baseline when the same artifact must run across all three providers and stay compatible with Azure's Linux Consumption plan. Without legacy plan constraints, evaluate Java 25 across AWS, Azure, and Google against your framework, dependencies, and build pipeline.

This table is a documentation snapshot as of November 24, 2026, not a guarantee that every region, hosting plan, or custom container follows the exact same timeline. Verify runtime lifecycles and specific regions/plans before deploying.

## 11. Runtime Compatibility Does Not Equal Framework Compatibility

A function that runs on Java 21 will not necessarily run on every Spring Boot or Spring Cloud Function version.

Before choosing a runtime, verify together:

- Java version supported by the Spring Boot release.
- Spring Cloud release train compatible with Spring Boot.
- Spring Cloud Function and corresponding adapter versions.
- Spring Integration version if using CloudEvents transformers.
- CloudEvents Java SDK or Event Format implementation versions.
- Provider handler contracts, reflection/AOT requirements, and startup behavior.
- Native images or container base images if deploying that way.

Never just bump `java.version` in Maven and declare migration complete. Build, test, and deploy to the target runtime generation.

A business module using Spring Cloud Function can keep its function code largely stable, yet entrypoints, request wrappers, dependencies, and deployment descriptors usually differ across AWS Lambda, Azure Functions, and Cloud Run functions.

## 12. Bringing CloudEvents into Spring Cloud Function

### 12.1. `FunctionCatalog` Does Not Automatically Decode Every CloudEvent

`FunctionCatalog` registers and wraps functional beans for lookup, composition, and type conversion. It is not a CloudEvents HTTP binding parser.

A CloudEvents request should pass through these steps:

1. Receive the HTTP request or provider envelope.
2. Inspect the content mode and CloudEvents context attributes.
3. Parse the envelope or map `ce-*` headers.
4. Decode event data according to `datacontenttype` and application schema.
5. Build a Spring `Message<?>` with the business payload and needed metadata.
6. Invoke the function through `FunctionCatalog`.

Never send raw CloudEvents JSON straight into a business bean expecting Spring to strip the envelope and dig into `data` automatically. That happens only when an adapter or converter is explicitly configured to do so.

### 12.2. Spring Integration Support for CloudEvents

Spring Integration offers the `spring-integration-cloudevents` module with two primary transformers:

- `FromCloudEventTransformer`: converts a CloudEvent into a Spring Integration Message; the payload becomes event data, while context attributes and extensions map to `ce-`-prefixed headers.
- `ToCloudEventTransformer`: converts a Spring Message into a CloudEvent; supports configuring an `EventFormat` to serialize the envelope.

The transformers support CloudEvents specification v1.0. For serialized CloudEvents, the transformer checks `content-type` to select an `EventFormat`. If no matching format or fallback is found, transformation fails.

Illustrative Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-cloudevents</artifactId>
    <version>7.1.1</version>
</dependency>
~~~

Choose a Spring Integration version compatible with your Spring Boot and Spring Framework versions. Do not assume the Spring Cloud Function BOM always manages this CloudEvents module's version.

### 12.3. Reading a Structured CloudEvent

The following example illustrates converting a serialized JSON CloudEvent into a Spring Message. This is an adapter step prior to calling the business function:

~~~java
Message<byte[]> rawMessage = MessageBuilder
        .withPayload(cloudEventJsonBytes)
        .setHeader(MessageHeaders.CONTENT_TYPE, "application/cloudevents+json")
        .build();

FromCloudEventTransformer transformer =
        new FromCloudEventTransformer();

Message<?> decoded = transformer.transform(rawMessage);

byte[] eventData = (byte[]) decoded.getPayload();
OrderCreated order = objectMapper.readValue(
        eventData, OrderCreated.class);

Message<OrderCreated> businessMessage = MessageBuilder
        .withPayload(order)
        .copyHeaders(decoded.getHeaders())
        .build();
~~~

In this example:

- `cloudEventJsonBytes` is the full structured envelope.
- `FromCloudEventTransformer` decodes the CloudEvents envelope.
- `eventData` is the event's `data` payload.
- `businessMessage` holds the `OrderCreated` payload along with metadata headers.

This snippet assumes `data` is serialized as a JSON byte array. For Protobuf or another media type, use the corresponding `EventFormat` and decoder.

### 12.4. Reading a Binary CloudEvent

With binary mode such as Eventarc, the HTTP adapter reads metadata from request headers and payload from the body. After validation, build a Spring Message:

~~~java
Message<OrderCreated> eventMessage = MessageBuilder
        .withPayload(orderCreated)
        .setHeader("ce-id", eventId)
        .setHeader("ce-source", eventSource)
        .setHeader("ce-specversion", specVersion)
        .setHeader("ce-type", eventType)
        .setHeader("ce-subject", subject)
        .setHeader("ce-time", eventTime)
        .build();
~~~

Here `orderCreated` has already been deserialized from the body per the event's `Content-Type`. Validate the four required attributes before calling the function:

~~~java
if (eventId == null || eventId.isBlank()
        || eventSource == null || eventSource.isBlank()
        || !"1.0".equals(specVersion)
        || eventType == null || eventType.isBlank()) {
    throw new IllegalArgumentException("Invalid CloudEvent context");
}
~~~

In production, use the CloudEvents SDK or a battle-tested HTTP binding implementation to handle URIs, timestamps, extensions, and serialization. The snippet above simply demonstrates moving received headers into a Spring Message.

### 12.5. Invoking the Function via `FunctionCatalog`

Suppose the application defines a business bean:

~~~java
@Bean
public Function<Message<OrderCreated>, OrderAccepted> processOrder() {
    return message -> {
        String eventId = (String) message.getHeaders().get("ce-id");
        String eventType = (String) message.getHeaders().get("ce-type");

        if (!"com.acme.order.created.v1".equals(eventType)) {
            throw new IllegalArgumentException("Unsupported event type");
        }

        OrderCreated order = message.getPayload();
        return new OrderAccepted(order.orderId(), eventId);
    };
}
~~~

The adapter looks up and invokes the function:

~~~java
Function<Message<OrderCreated>, OrderAccepted> function =
        functionCatalog.lookup("processOrder");

OrderAccepted result = function.apply(eventMessage);
~~~

Through `FunctionCatalog`, Spring Cloud Function can apply wrappers and type conversions. Because the business function accepts a Spring `Message`, it reads event metadata without depending directly on AWS EventBridge, Azure Event Grid, or Eventarc envelopes.

### 12.6. Keep Only Truly Necessary Metadata

Do not copy every CloudEvents header into domain objects. Categorize cleanly:

- Event identity: `ce-id`, `ce-source`.
- Event contract: `ce-type`, `ce-specversion`, `ce-dataschema`.
- Trace/correlation: agreed extensions like `ce-traceid`.
- Business payload: `data`.

Avoid letting business functions depend on pure HTTP headers like `Content-Length` or `User-Agent`. Forward only metadata belonging to the application contract.

## 13. Routing Safely by Event Type

An event router can use `ce-type` to pick a function. However, routing requires an explicit allowlist and clear contracts.

For example:

~~~java
Map<String, String> routes = Map.of(
        "com.acme.order.created.v1", "processOrderCreated",
        "com.acme.order.cancelled.v1", "processOrderCancelled",
        "com.acme.inventory.reserved.v1", "processInventoryReserved"
);

String functionName = routes.get(eventType);

if (functionName == null) {
    throw new UnsupportedEventTypeException(eventType);
}

Function<Message<?>, ?> function = functionCatalog.lookup(functionName);
Object result = function.apply(eventMessage);
~~~

This is routing pseudo-code; concrete payload types per function must be enforced safely. Never cast every function to a single generic type if their input/output schemas differ.

Rules to follow:

1. Authenticate the producer and authorize event submission before routing.
2. Verify `specversion` is supported.
3. Verify `type` is in the allowlist.
4. Verify `dataschema` or payload version compatibility.
5. Reject or quarantine unsupported events per policy.
6. Log event identity and type while omitting sensitive payloads.

Never allow external producers to pass arbitrary bean names via headers directly as function definitions. Event type is untrusted input data; it must never become an unrestricted function invocation directive.

## 14. Testing CloudEvents Contracts

A solid test suite covers envelopes, transports, and business functions.

### 14.1. Envelope Checks

- Missing `id`, `source`, `specversion`, or `type` must be rejected.
- Duplicate `source` + `id` must be detected per idempotency policy.
- Unsupported `specversion` must be handled explicitly.
- Malformed RFC 3339 `time` must be rejected or quarantined.
- Unknown extensions should not crash the parser when unused.
- `data` and `data_base64` must not both appear in the JSON event format.

### 14.2. Structured and Binary Checks

Create fixtures for both representations of the same event:

- Structured: envelope in body with `Content-Type: application/cloudevents+json`.
- Binary: context attributes in `ce-*` headers, data in body.

Both fixtures should yield the exact same business `Message` after the adapter step. That way, the business function never cares which content mode delivered the event.

### 14.3. Type and Schema Version Checks

- Supported event types route to the intended function.
- Unknown event types are rejected or quarantined per policy.
- Older supported payload schema versions decode via their matching decoder.
- Newer unsupported payload schema versions must never silently parse into old objects and corrupt logic.
- Verify whether extension attributes are preserved when forwarding events.

### 14.4. Runtime and Provider Checks

| Test layer | Goal |
| --- | --- |
| Unit tests | Validate context attributes, `type`, and data schemas. |
| Transformer tests | Structured envelope converts into a Spring `Message`. |
| HTTP contract tests | Binary headers and body map accurately. |
| `FunctionCatalog` tests | Message payload reaches the right functional bean. |
| Provider integration | AWS, Azure, and Eventarc emit expected envelopes per trigger config. |
| Runtime integration | App boots and processes events on the target Java/host generation. |
| Migration tests | Compare event fixtures before and after upgrading JDK or runtime. |

Never test only locally on Java 21 and deploy straight to Java 25 or another runtime generation without a smoke test. Runtime base images, classpaths, TLS providers, reflection, native libraries, and startup times can all differ.

## 15. Common CloudEvents Integration Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating `specversion` as payload version | Consumer rejects or misinterprets events. | Use `dataschema` or a payload versioning convention. |
| Checking `id` while ignoring `source` | False deduplication across distinct producers. | Key on the `(source, id)` pair. |
| Treating `source` as a callable URL | Consumer issues invalid HTTP requests. | Treat `source` purely as a context identifier. |
| Treating `type` as a function name | Producers can hijack internal routing. | Use an allowlisted type-to-function mapping. |
| Confusing EventBridge `version` with CloudEvents `specversion` | Broken envelope mapping. | Write explicit mappings in transformers. |
| Confusing Event Grid `dataVersion` with `specversion` | Misread payload schemas. | Track data schemas separately. |
| Parsing Eventarc body while ignoring `ce-*` headers | Loses event identity, source, and type. | Copy `ce-*` headers into Spring `Message` headers. |
| Assuming Pub/Sub `message.data` is already JSON | Decoder receives raw Base64 instead of payload. | Decode Base64 per Pub/Sub contract. |
| Assuming `FunctionCatalog` parses CloudEvents automatically | Business function receives the raw envelope. | Insert a CloudEvents adapter/transformer before the catalog. |
| Picking a new Java version without checking plan/runtime | Deployment fails or runtime unsupported. | Verify runtime IDs, host generations, OS, and hosting plans. |
| Upgrading Spring Boot while keeping old integration modules | Dependency/classpath errors. | Check the compatibility matrix and run integration tests. |
| Logging entire event envelopes | Leaks PII or sensitive metadata. | Log only permitted identity, type, correlation, and safe fields. |

## 16. Scenario Exercises

### Exercise 1 — Identify Three Version Types

A CloudEvent contains:

~~~json
{
  "specversion": "1.0",
  "type": "com.acme.invoice.issued.v2",
  "dataschema": "https://schemas.acme.example/invoice/v2.json",
  "id": "evt-99",
  "source": "urn:acme:billing",
  "data": {
    "invoiceId": "INV-99"
  }
}
~~~

Explain:

1. Which version does `specversion` represent?
2. Which occurrence does `type` describe?
3. What is `dataschema` used for?
4. When upgrading JDK from 21 to 25, which attribute in the event must change?

**Hint:** `specversion` is the CloudEvents version; `type` is the event contract; `dataschema` identifies the payload schema. JDK version requires zero changes to the CloudEvents envelope.

### Exercise 2 — Translating EventBridge to CloudEvents

An EventBridge event carries `detail-type=Object Created`, `source=aws.s3`, and payload inside `detail`.

1. Which fields can populate CloudEvents attributes?
2. Why should EventBridge `version` never map to `specversion`?
3. Who is responsible for defining the CloudEvents `type`?
4. Which `Content-Type` must be set when sending a structured JSON CloudEvent?

### Exercise 3 — Azure Event Grid

An application uses the Event Grid schema with `eventType` and `dataVersion`, while a consumer wants CloudEvents.

1. How should input/output schemas be configured?
2. Which CloudEvents attribute does `eventType` map to?
3. Is `dataVersion` equivalent to `specversion`?
4. Why can CloudEvents inputs not always convert back into Event Grid output schema without losing extension info?

### Exercise 4 — Google Eventarc Binary Mode

An HTTP request arrives with `ce-id`, `ce-source`, `ce-specversion`, `ce-type`, and a JSON body.

1. Why does the body not contain the full CloudEvents envelope?
2. How should the adapter construct a Spring `Message`?
3. When the event type is Pub/Sub `messagePublished`, why may extra Base64 decoding be required?
4. How should unsupported event types be handled?

### Exercise 5 — Choosing Runtimes for One Java App

A team wants to deploy a Spring Cloud Function app to AWS Lambda, Azure Functions, and Google Cloud Run functions.

1. Which Java 25 runtimes are available on each platform?
2. Why is Azure's Linux Consumption plan not an option for Java 25?
3. Which generations can Java 17 run on in Google Cloud Run functions?
4. How do AWS Java 17 AL2 and Java 17 AL2023 differ?
5. If aiming for one shared baseline across all three clouds, why is Java 21 a strong candidate?

### Exercise 6 — Designing an Adapter

Build an adapter that receives a structured CloudEvent and invokes `processOrder` via `FunctionCatalog`:

1. Validate the four required attributes.
2. Decode `data` into `OrderCreated`.
3. Preserve `ce-id`, `ce-source`, and `ce-type` in Spring Message headers.
4. Invoke the function.
5. Write tests for duplicate events and unsupported types.

### Exercise 7 — Upgrading Runtime While Keeping the Event Contract

An application upgrades from Java 17 to Java 21 and from Azure Functions runtime 3.x to 4.x while producers keep emitting CloudEvents 1.0.

Determine:

- Which parts of the event envelope need zero changes?
- Which dependencies and trigger extensions must be checked?
- Why are contract tests and runtime integration tests needed?
- How should rollout be structured to allow rollback if adapter or serialization behavior shifts?

## 17. Deployment Checklist

| Item | What to verify |
| --- | --- |
| CloudEvents core | Valid `specversion` and all four required attributes. |
| Event identity | `source` + `id` unique within producer scope. |
| Event type | Namespacing, naming convention, versioning, and allowlist. |
| Payload schema | `datacontenttype`, `dataschema`, and schema evolution rules. |
| Content mode | Structured, binary, or batch per supported binding. |
| Provider envelope | Explicit EventBridge, Event Grid, or Eventarc mapping. |
| Spring adapter | Parses envelope/headers prior to calling `FunctionCatalog`. |
| Metadata propagation | Retains required identity/type/trace; drops irrelevant headers. |
| Security | Authenticates producers; never trusts `source`/`type` purely from headers. |
| Runtime generation | AWS runtime ID/OS, Azure host/plan, Google generation/base image. |
| Java/framework compatibility | JDK, Boot, Spring Cloud Function, Spring Integration, CloudEvents SDK. |
| Tests | Envelope, payload, duplicate, routing, provider, and runtime integration tests. |
| Operations | Logs event identity, type, schema version, and runtime version; configures DLQ/quarantine. |

## 18. Official Documentation

1. CloudEvents Specification — Core attributes, event identity, extensions, and examples: https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md
2. CloudEvents HTTP Protocol Binding — Structured, binary, and batch content modes: https://github.com/cloudevents/spec/blob/main/cloudevents/bindings/http-protocol-binding.md
3. CloudEvents JSON Event Format: https://github.com/cloudevents/spec/blob/main/cloudevents/formats/json-format.md
4. CloudEvents Java SDK: https://github.com/cloudevents/sdk-java
5. Spring Cloud Function — Programming Model and `FunctionCatalog`: https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html
6. Spring Integration — CloudEvents Support, `FromCloudEventTransformer`, and `ToCloudEventTransformer`: https://docs.spring.io/spring-integration/reference/cloudevents.html
7. AWS Lambda — Java runtimes: https://docs.aws.amazon.com/lambda/latest/dg/lambda-java.html
8. AWS Lambda — Runtime lifecycle: https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html
9. Amazon EventBridge — Sending CloudEvents to API destinations: https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-api-destinations-cloudevents.html
10. Azure Functions — Compare runtime versions: https://learn.microsoft.com/en-us/azure/azure-functions/functions-versions
11. Azure Functions — Supported languages and Java versions: https://learn.microsoft.com/en-us/azure/azure-functions/supported-languages?pivots=programming-language-java
12. Azure Functions — Java developer reference: https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-java
13. Azure Event Grid — CloudEvents v1.0 schema: https://learn.microsoft.com/en-us/azure/event-grid/cloud-event-schema
14. Google Cloud Run functions — Runtime support: https://docs.cloud.google.com/functions/docs/runtime-support
15. Google Eventarc — CloudEvents HTTP protocol binding: https://docs.cloud.google.com/eventarc/docs/cloudevents
16. Google Eventarc — Event format and CloudEvents payload examples: https://docs.cloud.google.com/eventarc/docs/event-format
