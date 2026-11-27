# Receiving Cloud Storage and Pub/Sub events via Eventarc

In the **Serverless on Google Cloud** chapter, Eventarc connects events from Google Cloud services to applications running on Cloud Run or Cloud Run functions. Instead of having each function poll a service's state itself, Eventarc receives events from the source, applies filters, and delivers events to targets in CloudEvents format. Two common sources are Cloud Storage, which emits events when objects are created or modified, and Pub/Sub, where producers publish messages for consumers to process asynchronously.

This lesson belongs to the **CLOUD_SERVERLESS** module, focusing on developing and deploying serverless applications, especially Java functions triggered by HTTP, messages, or events. When receiving events, learners need to handle triggers, state, access control, retries, idempotency, cold starts, scaling, and cost to determine how to use FaaS appropriately.

## 1. What problem does Eventarc solve?

A business service often needs to react when data or state in another service changes. For example:

- When a file is uploaded to Cloud Storage, a function checks its format, generates a thumbnail, or extracts metadata.
- When an order is published to Pub/Sub, a function updates status or kicks off a processing workflow.
- When an object is deleted, a function cleans up metadata or marks a resource as unavailable.

If every application called source APIs directly, managed its own webhooks, or ran periodic polling, components would become tightly coupled. Eventarc provides a managed event-routing layer:

1. A Google Cloud service emits an event.
2. Eventarc receives the event and applies trigger filters.
3. Eventarc delivers the event to the configured destination.
4. The destination receives an HTTP request formatted according to CloudEvents.
5. The function or service processes the payload and returns an HTTP response.

~~~mermaid
flowchart LR
    GCS["Cloud Storage"] -->|Object event| EA["Eventarc trigger"]
    PS["Pub/Sub topic"] -->|Message published| EA
    EA -->|CloudEvent over HTTP| RUN["Cloud Run / Cloud Run functions"]
    RUN --> JAVA["Java handler"]
    JAVA --> DB[("Database / downstream service")]
~~~

Eventarc decouples the event source from the processor. The producer does not need to know which function is receiving the event, and the function does not need to continuously poll the source.

Eventarc is an event router and delivery layer. It does not replace business logic, schema validation, idempotency, or persisting processing state. Those responsibilities remain with the application and source service.

## 2. Eventarc, Cloud Run, and Cloud Run functions

Eventarc can deliver events to supported targets, commonly including:

- **Cloud Run service:** an HTTP application deployed by the development team, managing its own routing and handlers.
- **Cloud Run functions / next-generation Cloud Functions:** a function packaged and deployed using the Functions Framework model with an explicit entry point.
- Other targets supported by Eventarc depending on trigger type and configuration.

With Java, the handler can implement the Functions Framework CloudEvents interface or accept an HTTP request and parse the CloudEvent directly. Using Functions Framework provides an adapter that handles the protocol and passes events into a Java method with clear types.

Distinguish two ways of receiving messages from Pub/Sub:

| Receiving method | Who initiates delivery? | When suitable |
|---|---|---|
| Eventarc trigger | Eventarc delivers the event to an HTTP target | When routing events to Cloud Run/functions under the unified CloudEvents model |
| Pub/Sub pull subscription | The application calls the pull API and ACKs messages | When you need direct control over polling, batching, flow control, and acknowledgements |

When using Eventarc, the target does not need to poll a Pub/Sub subscription itself. If the application requires message-level control over pulling and acking, you can use a Pub/Sub client directly; that is a different consumer architecture from Eventarc.

## 3. CloudEvents as the contract between Eventarc and the handler

Eventarc delivers events according to the CloudEvents 1.0 specification. A CloudEvent has an envelope carrying shared context and a `data` section containing the source-specific payload.

Key attributes:

| Attribute | Meaning |
|---|---|
| `specversion` | CloudEvents version, typically 1.0 |
| `id` | Event identifier |
| `source` | Event source |
| `type` | Event type |
| `subject` | Related subject, if any |
| `time` | Event timestamp |
| `datacontenttype` | Media type of the payload, if any |
| `data` | Business payload or source service data |

Illustrative envelope example:

~~~json
{
  "specversion": "1.0",
  "id": "1234567890123456",
  "source": "//storage.googleapis.com/projects/_/buckets/incoming-files",
  "type": "google.cloud.storage.object.v1.finalized",
  "subject": "objects/invoice-1001.pdf",
  "time": "2026-11-17T10:15:30Z",
  "datacontenttype": "application/json",
  "data": {
    "bucket": "incoming-files",
    "name": "invoice-1001.pdf",
    "generation": "1731840000000000",
    "contentType": "application/pdf",
    "size": "245760"
  }
}
~~~

The envelope provides ID, source, and type for routing, deduplication, and tracing. Data has its own schema per event type. Do not use a single payload DTO for both Cloud Storage and Pub/Sub because the two sources have different structures.

## 4. Receiving Cloud Storage events via Eventarc

Cloud Storage can emit events when an object is created, metadata is updated, deleted, or replaced according to the event types supported by Eventarc.

Commonly used event types:

| Event type | Meaning | Use case |
|---|---|---|
| `google.cloud.storage.object.v1.finalized` | A new object is created or a new generation finishes writing | File upload processing, thumbnails, document scanning |
| `google.cloud.storage.object.v1.deleted` | An object generation is deleted | Metadata cleanup, catalog updates |
| `google.cloud.storage.object.v1.archived` | An older object generation is archived/replaced under versioning | History tracking or state synchronization |
| `google.cloud.storage.object.v1.metadataUpdated` | Object metadata is updated | Syncing labels, content type, or business metadata |

Specific event types and emission capabilities depend on the trigger type and bucket configuration. Choose the right event type for the goal; do not use `finalized` as a substitute for all metadata changes.

### 4.1. Cloud Storage payload

An object event payload typically includes fields such as:

- `bucket`: bucket name.
- `name`: object name.
- `generation`: identifier of the object's content version.
- `metageneration`: metadata version.
- `contentType`: content type.
- `size`: object size.
- `timeCreated`: creation timestamp.
- `updated`: update timestamp.

Example Java DTO:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record StorageObjectData(
        String bucket,
        String name,
        String generation,
        String metageneration,
        String contentType,
        String size,
        String timeCreated,
        String updated) {
}
~~~

Some large numeric fields are represented as strings in the event payload. Using `String` for `generation` and `metageneration` avoids precision loss when converting to bounded numeric types. When comparison is needed, parse to `BigInteger` or compare as strings per the contract.

### 4.2. Generation and metageneration

Cloud Storage uses `generation` to identify an object's content version. When an object is overwritten, `generation` changes. `metageneration` increments when metadata of a generation changes.

These two values are critical when a function processes events asynchronously. For example, a `finalized` event for an older generation might arrive late after the object has already been overwritten with a new generation. If the function reads only by bucket and object name, it could accidentally process the new content while the event describes the old content.

When you need to read the exact version that emitted the event, pass `generation` from the payload as a condition when accessing the object with the Cloud Storage client. When detecting metadata changes, inspect `metageneration`. Do not use the object name alone as the idempotency key across all uploads.

### 4.3. File processing flow

A common workflow:

1. A user uploads a file to the incoming bucket.
2. Cloud Storage emits a `finalized` event.
3. Eventarc filters the event by bucket and type and delivers it to the Java function.
4. The function validates bucket, object name, generation, and content type.
5. The function reads the exact object generation if needed.
6. The function scans content, validates business rules, or generates a derived artifact.
7. The function saves the result and records the event as processed.
8. The function returns a success response after the required changes are durably saved.

Do not assume a `finalized` event is emitted only once. Retries or duplicate deliveries can cause the function to receive the same event again.

## 5. Receiving Pub/Sub events via Eventarc

Pub/Sub is an asynchronous messaging service. Producers publish messages to a topic; subscriptions manage message delivery to consumers. When integrated via Eventarc, Eventarc creates a trigger for message-published events and delivers CloudEvents to the target.

Commonly used event type:

~~~text
google.cloud.pubsub.topic.v1.messagePublished
~~~

The event payload contains subscription and message details. The Pub/Sub message's `data` field is Base64-encoded; consumers must decode it before parsing the business content.

Example CloudEvent `data` section:

~~~json
{
  "subscription": "projects/demo/subscriptions/orders-eventarc-sub",
  "message": {
    "data": "eyJvcmRlcklkIjoiT1JELTEwMDEiLCJjdXN0b21lcklkIjoiQ1VTLTIwMDEifQ==",
    "messageId": "2070443601311540",
    "publishTime": "2026-11-17T10:15:30.123Z",
    "attributes": {
      "schemaVersion": "1",
      "eventType": "OrderPlaced"
    },
    "orderingKey": "ORD-1001"
  }
}
~~~

Java DTOs:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.Map;

@JsonIgnoreProperties(ignoreUnknown = true)
public record PubSubPublishedData(
        String subscription,
        PubSubMessage message) {
}

@JsonIgnoreProperties(ignoreUnknown = true)
public record PubSubMessage(
        String data,
        String messageId,
        String publishTime,
        Map<String, String> attributes,
        String orderingKey) {
}
~~~

After parsing `PubSubPublishedData`, the function decodes the `message.data` field:

~~~java
import java.util.Base64;
import java.nio.charset.StandardCharsets;

byte[] payloadBytes =
        Base64.getDecoder().decode(published.message().data());

String payloadJson =
        new String(payloadBytes, StandardCharsets.UTF_8);

OrderPlacedPayload payload =
        objectMapper.readValue(payloadJson, OrderPlacedPayload.class);
~~~

Do not parse the Base64 string directly as JSON. If the producer sends binary data instead of UTF-8 JSON, the consumer must handle it according to the content type or agreed contract.

### 5.1. Attributes and message data

A Pub/Sub message has two data regions:

- `data`: the primary content, Base64-encoded inside the event payload.
- `attributes`: string key/value pairs used for metadata, filtering, or routing.

Do not stuff the entire business payload into `attributes`. Attributes are suitable for small metadata such as `schemaVersion`, `eventType`, `tenant`, or `correlationId`. Structured business content belongs in `data` with a clear schema.

## 6. Creating an Eventarc trigger and region configuration

To create a trigger, specify:

- Event source: Cloud Storage bucket or Pub/Sub topic.
- Event type to receive.
- Destination: Cloud Run service or Cloud Run function.
- Region/location of the trigger and destination.
- Service account that Eventarc uses to invoke the destination.
- Additional filters such as bucket or supported source attributes.

For Cloud Storage, the trigger location must be compatible with the bucket location and Eventarc constraints. For Pub/Sub, choose a location compatible with the trigger, topic, and where the target is deployed. Do not select a region based solely on where end users live; consider data locality, latency requirements, source support, and data transfer costs.

Conceptual trigger creation workflow:

1. Enable the required APIs such as Eventarc, Cloud Run, Cloud Storage or Pub/Sub, and the build/deploy services in use.
2. Create a dedicated service account for the trigger.
3. Grant Eventarc event-receiving permissions and target-invoke permissions to the service account.
4. Deploy the Cloud Run service or Cloud Run function first.
5. Create the trigger with event type, source filters, location, and destination.
6. Verify the trigger is active and send a test event.
7. Confirm the target receives the CloudEvent and returns a success response.

Example command to create a Cloud Storage trigger targeting a Cloud Run service:

~~~bash
gcloud eventarc triggers create storage-finalized \
  --location=REGION \
  --destination-run-service=JAVA_SERVICE \
  --destination-run-region=REGION \
  --event-filters="type=google.cloud.storage.object.v1.finalized" \
  --event-filters="bucket=BUCKET_NAME" \
  --service-account=EVENTARC_TRIGGER_SA
~~~

This example illustrates a trigger for object finalized events. Replace the placeholders with real resources and verify location requirements, permissions, APIs, and current `gcloud` syntax before running. Different source types and `gcloud` versions may require transport parameters or additional configuration.

For Pub/Sub, choose the `messagePublished` event type and the topic as the source using the Eventarc syntax supported for the trigger type in use. Ensure producers publish to the exact topic the trigger watches. Do not confuse the source topic with the internal transport topic used by some Eventarc trigger types or configurations.

## 7. Java handler using CloudEventsFunction

With Java Functions Framework, you can implement the `CloudEventsFunction` interface. The framework converts the HTTP CloudEvent into a `CloudEvent` object so the handler can read metadata and data.

The following example illustrates a handler accepting both event types. The `StorageObjectData` and `PubSubPublishedData` DTOs are the records shown above.

~~~java
package com.example.events;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.cloud.functions.CloudEventsFunction;
import io.cloudevents.CloudEvent;
import java.util.Base64;

public class EventarcHandler implements CloudEventsFunction {
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private static final String STORAGE_FINALIZED =
            "google.cloud.storage.object.v1.finalized";

    private static final String PUBSUB_PUBLISHED =
            "google.cloud.pubsub.topic.v1.messagePublished";

    @Override
    public void accept(CloudEvent event) throws Exception {
        if (event.getData() == null) {
            throw new IllegalArgumentException("CloudEvent data is required");
        }

        byte[] eventData = event.getData().toBytes();

        switch (event.getType()) {
            case STORAGE_FINALIZED -> handleStorage(event, eventData);
            case PUBSUB_PUBLISHED -> handlePubSub(event, eventData);
            default -> throw new UnsupportedOperationException(
                    "Unsupported event type: " + event.getType());
        }
    }

    private void handleStorage(
            CloudEvent event,
            byte[] eventData) throws Exception {

        StorageObjectData object =
                MAPPER.readValue(eventData, StorageObjectData.class);

        storageProcessor().processOnce(
                event.getSource().toString(),
                event.getId(),
                object);
    }

    private void handlePubSub(
            CloudEvent event,
            byte[] eventData) throws Exception {

        PubSubPublishedData published =
                MAPPER.readValue(eventData, PubSubPublishedData.class);

        byte[] payload = Base64.getDecoder().decode(
                published.message().data());

        OrderPlacedPayload order =
                MAPPER.readValue(payload, OrderPlacedPayload.class);

        orderProcessor().processOnce(
                event.getSource().toString(),
                event.getId(),
                published.message().messageId(),
                order);
    }

    private StorageProcessor storageProcessor() {
        // Retrieve dependency from composition root or dependency injection.
        throw new UnsupportedOperationException("Wire application service");
    }

    private OrderProcessor orderProcessor() {
        // Retrieve dependency from composition root or dependency injection.
        throw new UnsupportedOperationException("Wire application service");
    }
}
~~~

The business types invoked by the handler can be declared according to internal contracts:

~~~java
public record OrderPlacedPayload(
        String orderId,
        String customerId) {
}

public interface StorageProcessor {
    void processOnce(
            String source,
            String eventId,
            StorageObjectData object) throws Exception;
}

public interface OrderProcessor {
    void processOnce(
            String source,
            String eventId,
            String messageId,
            OrderPlacedPayload order) throws Exception;
}
~~~

This is a skeleton illustrating the adapter boundary; the final two factory methods must be replaced with real dependency injection or a composition root. In production, do not stub business services by throwing `UnsupportedOperationException` as in this placeholder example.

The `default` branch in the `switch` also needs a clear policy. If an unsupported event type is a permanent contract error, you can record it to a controlled quarantine or dead-letter store and return success after durably saving it; if you simply throw an exception every time, Eventarc may keep retrying the same event until the retry policy is exhausted.

A production application should:

- Configure `ObjectMapper` once and register required modules.
- Validate event `source`, `type`, and schema.
- Check for null, empty, oversized, or malformed payloads.
- Invoke the use case only after validation succeeds.
- Persist idempotency state durably.
- Never log full payloads or file contents.
- Fail intentionally so Eventarc retries on transient errors.

If a trigger receives only one event type, use a dedicated handler and omit the `switch`. Separating handlers by event type reduces coupling and allows scoping permissions to each data source.

## 8. Safely processing Cloud Storage objects

When a function receives a `finalized` event, the object may already have been overwritten or deleted before the function reads it. Therefore, do not use only `bucket` and `name` to fetch the current version if the business logic requires processing the exact content that emitted the event.

A safe workflow:

1. Read `bucket`, `name`, and `generation` from the payload.
2. Verify the object belongs to an allowed bucket.
3. Construct a read request with a `generation` condition matching the event value.
4. Enforce file size and content type limits.
5. Stream rather than loading the entire file into the heap for large files.
6. Write results tied to the processed `generation`.
7. Save a deduplication key so redeliveries do not produce a second output.

If the object has already been deleted or the generation is no longer available, distinguish whether that is a valid business case or a transient error. Do not infinitely retry an object that was permanently deleted.

Object names can contain spaces, Unicode, or special characters. Use the Cloud Storage client library to access objects rather than manually concatenating URLs without proper encoding. Validate bucket and prefix so the function cannot be tricked into reading out-of-scope objects.

## 9. Retries and acknowledgements

Eventarc delivers events under a redelivery-capable model. The target must return an HTTP success response after processing and persisting required outputs. If the target returns an error or fails to respond within the allowed timeout, Eventarc may retry delivery according to the trigger and source retry policy.

Principles:

- Return 2xx when the event has been processed or durably persisted into an internal processing queue.
- Return an error on transient failures when you want Eventarc to retry.
- Do not return success before the required data has been durably saved.
- Do not infinitely retry schema errors or unsupported event types.
- Configure retries, retention, and dead-lettering according to source/trigger capabilities.

For Cloud Run targets, the service's HTTP response serves as the delivery signal. For Cloud Run functions, exceptions thrown from the handler are typically converted into error responses by the framework. Verify how your runtime/framework maps exceptions to ensure retries behave as intended.

Eventarc and Pub/Sub have distinct retry policies depending on the source type and configuration. Do not assume a fixed retry interval across all triggers; check the actual configuration and current service documentation.

## 10. Idempotency and duplicate event handling

An event may be delivered multiple times due to retries, timeouts, or lost responses. Consumers must ensure repeated processing does not create duplicate business side effects.

For CloudEvents, you can use the pair `source` and `id` as the event identification key. For Cloud Storage, include `bucket`, `object name`, and `generation` to identify specific content. For Pub/Sub, `messageId` is useful metadata; CloudEvent `id` also identifies the event emission in the envelope.

Example deduplication table:

~~~sql
CREATE TABLE processed_events (
    source VARCHAR(500) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (source, event_id)
);
~~~

The consumer records the key and business changes within the same transaction if supported by the same database. If the key already exists, treat the event as already processed and exit safely.

Do not rely solely on in-memory variables or local caches for deduplication. Cloud Run instances can run in parallel, restart, or move to other hosts. Idempotency state must be stored durably with a unique constraint to handle concurrency.

For Cloud Storage, the same object name can have multiple generations. If the key includes only `bucket` and `name`, a new upload could be mistaken for an old event. Include `generation` in the key when business logic processes each content version.

## 11. Event ordering and business state

Eventarc should not be treated as a global ordering guarantee. Events can arrive late or be processed concurrently. With Pub/Sub, ordering keys can help preserve order within an appropriate configuration scope, yet consumers must still tolerate retries and duplicate processing.

If business logic requires ordering:

- Use an ordering key scoped by aggregate ID, such as `orderId`.
- Store a version or sequence number in the payload.
- Apply an event only if its version matches the current state.
- Store early-arriving events for deferred processing if needed.
- Define compensating actions when events arrive out of order.

For Cloud Storage, `generation` indicates the object version; for Pub/Sub, producers can include `aggregateVersion` in the payload. Do not use timestamps alone to infer strict global order across producers because clocks can skew.

## 12. IAM and security for Eventarc

Eventarc invokes targets using a configured service identity. Targets should require authentication rather than allowing public access unless there is an explicit reason.

Common roles in configurations:

- The trigger's service account needs event-receiving permissions required by Eventarc, typically `roles/eventarc.eventReceiver`.
- The trigger's service account needs permission to invoke the Cloud Run target, typically `roles/run.invoker` on the exact service.
- The producer needs permission to write objects to the bucket or publish messages to the Pub/Sub topic.
- The Java service account needs permission to read objects or call downstream services as required by business logic.
- Google Cloud service agents need managed service permissions to operate the integration.

Do not grant `roles/editor` or broad project-wide permissions to the trigger service account just to make the trigger work. Bind permissions at the resource level whenever possible.

For Cloud Storage, separate bucket write permissions from the function's object read permissions. For Pub/Sub, separate producer publish permissions from subscribe/pull permissions if the application uses a direct consumer. When using Eventarc, do not automatically grant Pub/Sub Subscriber to the function if the function does not call the pull API directly.

Do not trust a payload merely because it arrived via Eventarc. Verify `source`, `type`, expected bucket/topic, and business data. Avoid logging tokens, personal data, or file contents.

## 13. Regions, latency, and integration constraints

An Eventarc trigger has a location. Cloud Storage buckets, Pub/Sub topics, and targets also have their own locations or deployment scopes. Some direct sources require the trigger to be in the same location as the source resource or only support specific region combinations.

Before deploying, confirm:

- Location of the bucket or topic.
- Region of the Eventarc trigger.
- Region of the Cloud Run service or function.
- Event provider and event types supported in that location.
- Same-project requirements or cross-project permissions.
- Data transfer costs and latency between source and target.

Placing the function close to the data source generally reduces latency and data transfer costs, but must not violate service location requirements. For multi-region or dual-region buckets, check Eventarc's specific location rules before choosing the trigger region.

## 14. Scaling and concurrency control

Cloud Run can scale out instances as event traffic rises. This helps clear backlogs faster, but can also overload dependent databases or APIs.

Configure and monitor:

- Maximum instances to bound instance count.
- Concurrency per instance.
- CPU and memory sized appropriately for payload volume.
- Request timeouts.
- Database connection limits.
- Event processing rate versus publish rate.
- Backlog, retries, and event age.

If a single instance handles multiple concurrent requests, Java code and shared dependencies must be thread-safe. `ObjectMapper` can be shared once configured; mutable business state in static fields must not be used to coordinate invocations.

For large files, avoid loading the entire content into heap when streaming is possible. For Pub/Sub batches or large messages, bound payload size and processing time. If downstream cannot sustain rapid traffic spikes, use a concurrency cap or intermediate queue to apply backpressure.

## 15. Observability and diagnostics

An Eventarc pipeline needs observability across the source, trigger, and target.

Signals to capture:

- CloudEvent `id`, `source`, `type`, and `subject`.
- Bucket/object/generation or Pub/Sub `messageId`.
- Correlation ID and trace context if available.
- Receipt time and processing duration.
- Processing outcome, retries, and errors.
- Counts of processed, skipped, or dead-lettered events.

Use Cloud Logging to search logs by event ID or correlation ID. Use Cloud Monitoring to track request counts, error rates, latency, instance counts, and metrics related to Eventarc, Cloud Run, Pub/Sub, or Cloud Storage. Use Cloud Trace or OpenTelemetry if you need to stitch processing time across multiple services.

Do not create high-cardinality metric labels such as object name, `orderId`, or `messageId`. Place those identifiers in logs or traces. Set alerts for error rate, latency, backlog, retries, and dead-letter counts aligned with service targets.

## 16. Cost and architectural trade-offs

Costs can come from:

- Eventarc triggers and delivered events under the current pricing model.
- Cloud Run/Cloud Run functions based on requests, CPU, memory, and duration.
- Pub/Sub based on message volume, throughput, and retention.
- Cloud Storage based on capacity, operations, and networking.
- Logging, Monitoring, and Trace.
- Databases or downstream services called by the function.

Eventarc reduces the need to run your own webhooks or polling, yet every event still carries delivery and processing costs. If a bucket emits millions of tiny events or a producer publishes messages too frequently, evaluate event filtering, batching, payload sizes, and retention.

Choose Eventarc when you want to route service events as CloudEvents to an HTTP target. Choose a Pub/Sub pull consumer when you need client-level control over polling, flow control, ack deadlines, and batching. For file-processing workloads, Cloud Storage events combined with Eventarc are typically more natural than continuous bucket polling.

## 17. Workflow for deploying a Java function receiving Eventarc events

1. **Identify the source:** Cloud Storage or Pub/Sub, which event types, and which filter conditions.
2. **Design the contract:** CloudEvent envelope, payload schema, event ID, and version.
3. **Choose the target:** Cloud Run service or Cloud Run function depending on your Java deployment model.
4. **Write the handler:** Use `CloudEventsFunction` or an HTTP adapter; separate business logic from the wrapper.
5. **Validate:** Check source, type, schema, size, and data access permissions.
6. **Design idempotency:** Store `source` + event ID and business keys in durable storage.
7. **Configure IAM:** Trigger service account, event receiver, run invoker, and source read/write permissions.
8. **Choose locations:** Verify compatibility across source, trigger, and target.
9. **Create the trigger:** Configure event type, filters, destination, and retries.
10. **Test:** Upload a test file or publish a test message; confirm Java parses the payload properly.
11. **Failure testing:** Simulate timeouts, duplicates, malformed events, and unavailable downstream services.
12. **Observe:** Set up logs, metrics, alerts, and dashboards.
13. **Deploy safely:** Bound concurrency, timeout, memory, and review costs.

## 18. Common mistakes

**Confusing Eventarc with Pub/Sub pull:** Functions using Eventarc do not need to poll subscriptions themselves. Use the Pub/Sub pull client only when explicitly choosing a pull consumer model.

**Mis-parsing Pub/Sub payloads:** The `message.data` field is Base64-encoded. Decode it before parsing JSON or processing bytes.

**Using the same DTO for Storage and Pub/Sub:** The two event types have different schemas. Parse by type and then map into internal commands.

**Using object name as the deduplication key:** One object can have multiple generations. Use event identity and generation.

**Reading the current object version:** An older event can arrive after the object has been overwritten. Read by generation if business logic requires the exact content of the event.

**Returning 2xx too early:** Eventarc considers delivery successful even if processing has not been durably saved. Acknowledge only after committing or safely persisting the work.

**Retrying permanent errors:** Malformed payloads or unsupported types get redelivered repeatedly. Quarantine, alert, or handle according to a permanent-error policy.

**Lacking deduplication:** Retries produce duplicate file processing, orders, or payments. Use durable idempotency.

**Assuming events always arrive in order:** Consumers can receive events late or concurrently. Use generation, aggregate version, or ordering keys when needed.

**Granting overly broad IAM permissions:** Triggers or functions hold project-wide roles. Scope permissions to specific resources and roles.

**Not bounding concurrency:** Event spikes overwhelm the database. Set max instances/concurrency and monitor backlogs.

**Observing only the target and not the source:** Looking only at function logs misses congested triggers or queues. Monitor the entire event path.

## 19. Checklist before taking Eventarc to production

- [ ] Correct Cloud Storage or Pub/Sub source has been identified.
- [ ] Event types and filters accept only necessary events.
- [ ] Source, trigger, and target locations are compatible.
- [ ] Target accepts CloudEvents and checks `specversion`, `source`, `type`, and `id`.
- [ ] Storage and Pub/Sub payloads are mapped with separate DTOs.
- [ ] Pub/Sub `message.data` is Base64-decoded before parsing.
- [ ] Cloud Storage `generation` is used when reading exact object versions is required.
- [ ] Idempotency is implemented using a durable event identifier.
- [ ] Retries and permanent errors have distinct policies.
- [ ] Target returns success only after processing or durable persistence.
- [ ] Trigger service account has least-privilege permissions.
- [ ] Function has permissions to read/write only the required data.
- [ ] Concurrency, timeout, memory, and payload size are bounded.
- [ ] Logs include event ID, source, type, and correlation ID without exposing sensitive payloads.
- [ ] Metrics exist for latency, errors, retries, backlog, and dead-letter counts.
- [ ] Tested duplicates, out-of-order events, malformed events, and downstream failures.
- [ ] Costs for Eventarc, Cloud Run, Pub/Sub, Storage, and observability are estimated.

## Conclusion

Eventarc connects events from Cloud Storage and Pub/Sub to Cloud Run or Cloud Run functions using the CloudEvents contract. For Cloud Storage, the payload describes the object and its generation; for Pub/Sub, the payload contains message metadata and a Base64-encoded `data` field. Java handlers must inspect the event type, parse the right DTO, validate the source, execute business logic idempotently, and return success only after results are durably saved.

To operate in production, pick compatible locations, grant least-privilege IAM permissions, configure retries, bound concurrency, and observe the entire path from source to target. Eventarc reduces coupling and eliminates application-side polling in a push-event model, yet correctness still depends on schemas, state management, deduplication, and the resilience of the Java function.
