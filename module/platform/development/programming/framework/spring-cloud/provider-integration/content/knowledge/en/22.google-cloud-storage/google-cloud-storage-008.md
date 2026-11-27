# Connecting Storage with Spring Integration and Object Change Notifications

## 1. From File Storage to Stream Processing

A Spring Boot application can upload files to Google Cloud Storage (GCS), but many business workflows require follow-up processing once an object appears: content validation, thumbnail generation, metadata extraction, virus scanning, search indexing, syncing data to other systems, or updating record statuses.

There are two common ways to bring objects into a Spring Integration flow:

- **Polling Storage:** the application periodically lists a bucket or prefix and receives new files via a MessageChannel. This fits small batch jobs, file synchronization, or systems that do not need immediate reactions when objects change.
- **Event-driven via Pub/Sub:** Cloud Storage emits notifications when an object is created, deleted, archived as noncurrent, or has its metadata updated. Pub/Sub delivers messages to a subscription; PubSubInboundChannelAdapter feeds messages into a Spring Integration flow. This fits event-driven reactions and scaling across multiple consumers.

Spring Framework on Google Cloud also provides GCS inbound/outbound channel adapters to read, stream, and write files over MessageChannels. These adapters work directly with Storage via polling/file transfer. They do not replace Pub/Sub notifications when business logic needs exact event types, generations, or metadata updates.

This lesson belongs to the **Google Cloud Storage** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module focuses on practicing Spring Boot integration with managed services on AWS, Azure, and Google Cloud through the corresponding Spring Cloud libraries; learning identity and permissions configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. This lesson focuses on Spring Integration channel adapters for GCS and object change notification flows via Pub/Sub.

After this lesson, you will be able to:

- Distinguish GCS polling adapters from Pub/Sub event notifications.
- Choose GcsInboundFileSynchronizingMessageSource, GcsStreamingMessageSource, or GcsMessageHandler.
- Configure Cloud Storage notifications for OBJECT_FINALIZE, OBJECT_DELETE, OBJECT_ARCHIVE, and OBJECT_METADATA_UPDATE.
- Grant proper permissions to the Cloud Storage service agent, Pub/Sub subscriber, and object-reading application.
- Connect a subscription to PubSubInboundChannelAdapter and MessageChannel.
- Read Pub/Sub attributes and JSON object metadata payloads.
- Handle ack/nack, retries, duplicate delivery, and out-of-order events.
- Use generation/metageneration to avoid processing the wrong object version.
- Design idempotency, dead-letter handling, observability, and integration tests.

> **Version scope:** Examples use Spring Framework on Google Cloud (Spring Cloud GCP) with current packages `com.google.cloud.spring...`, the Google Cloud Storage Java client, and Spring Integration. Manage versions using a Spring Framework on Google Cloud BOM compatible with your project's Spring Boot version. Do not mix legacy Spring Cloud GCP `org.springframework.cloud.gcp...` packages/APIs with the current major version. Check the Javadoc for your resolved BOM before applying.

## 2. Integration Architecture

### 2.1. Polling Files via GCS Channel Adapters

~~~mermaid
flowchart LR
    GCS["Cloud Storage bucket"] --> POLL["GcsInboundFileSynchronizingMessageSource<br/>or GcsStreamingMessageSource"]
    POLL --> CHANNEL["Spring Integration MessageChannel"]
    CHANNEL --> FILTER["Filter / Transformer"]
    FILTER --> SERVICE["ServiceActivator"]
    SERVICE --> DB["Database / downstream service"]
    OUT["Message<File>"] --> HANDLER["GcsMessageHandler"]
    HANDLER --> GCS
~~~

Polling adapters periodically query a bucket/prefix, fetch files, and emit messages. With the synchronizing adapter, files are downloaded to a local directory before emitting messages. With the streaming adapter, the payload is an InputStream and the application reads directly from the remote object.

### 2.2. Event-Driven via Pub/Sub Notifications

~~~mermaid
sequenceDiagram
    participant App as Spring Boot upload service
    participant GCS as Cloud Storage
    participant Topic as Pub/Sub topic
    participant Sub as Pub/Sub subscription
    participant Adapter as PubSubInboundChannelAdapter
    participant Flow as Spring Integration flow

    App->>GCS: Upload object
    GCS->>Topic: OBJECT_FINALIZE notification
    Topic->>Sub: Message delivery
    Sub->>Adapter: Streaming pull
    Adapter->>Flow: Spring Message + attributes + payload
    Flow->>Flow: Deduplicate / validate generation
    Flow->>GCS: Read exact object generation
    Flow->>Flow: Process business data
    Flow->>Sub: ACK after processing and committing
~~~

In this architecture, GCS does not call the Spring Boot endpoint directly. GCS publishes notifications to a Pub/Sub topic; the application receives messages via a subscription. Pub/Sub decouples the storage producer from consumers, allowing multiple services to process the same event independently through separate subscriptions.

### 2.3. Choosing the Right Mechanism

| Requirement | Appropriate mechanism | Reason |
| --- | --- | --- |
| Periodically ingest files from a prefix | GcsInboundFileSynchronizingMessageSource | Polls and syncs files to a local directory |
| Process large files without creating local copies | GcsStreamingMessageSource | Payload is an InputStream |
| Write files from Spring messages to a bucket | GcsMessageHandler | Outbound file adapter |
| React to object finalize/delete/metadata update | GCS Pub/Sub notification + PubSubInboundChannelAdapter | Includes event type, generation, and metadata |
| Multiple services receiving the same event | Pub/Sub topic with multiple subscriptions | Independent fan-out |
| Triggering only a small function | Cloud Run functions or Eventarc | Can reduce application-managed messaging boilerplate |

Do not treat polling as an event log. Polling can miss intermediate states if an object is modified or deleted between scans. Conversely, notifications carry event details but do not automatically download bytes; consumers must call the Storage API when object content is needed.

## 3. GCS Channel Adapters for Spring Integration

### 3.1. Dependencies

GCS channel adapters live in the `spring-cloud-gcp-storage` module. Add `spring-integration-file` because it is not pulled in transitively.

Maven:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-storage</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-file</artifactId>
</dependency>
~~~

If using the Spring Framework on Google Cloud starter:

~~~gradle
dependencies {
    implementation("com.google.cloud:spring-cloud-gcp-starter-storage")
    implementation("org.springframework.integration:spring-integration-file")
}
~~~

Use the Spring Framework on Google Cloud BOM to manage versions. If the starter already auto-configures a Storage bean, inject that bean rather than creating a separate client per adapter.

### 3.2. Synchronizing Files to a Local Directory

GcsInboundFileSynchronizingMessageSource is an inbound message source for files. It uses GcsInboundFileSynchronizer to access a bucket, download files to a local directory, and emit messages with a File payload.

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.spring.storage.integration.inbound.GcsInboundFileSynchronizer;
import com.google.cloud.spring.storage.integration.inbound.GcsInboundFileSynchronizingMessageSource;
import com.google.cloud.spring.storage.integration.filters.GcsRegexPatternFileListFilter;
import java.io.File;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.core.MessageSource;
import org.springframework.messaging.MessageChannel;
import org.springframework.integration.channel.DirectChannel;

@Configuration(proxyBeanMethods = false)
public class GcsPollingConfiguration {

    @Bean
    MessageChannel newGcsFiles() {
        return new DirectChannel();
    }

    @Bean
    @InboundChannelAdapter(
            channel = "newGcsFiles",
            poller = @Poller(fixedDelay = "5000"))
    MessageSource<File> gcsFileSource(Storage storage) {

        GcsInboundFileSynchronizer synchronizer =
                new GcsInboundFileSynchronizer(storage);

        synchronizer.setRemoteDirectory("training-documents");
        synchronizer.setFilter(
                new GcsRegexPatternFileListFilter("^incoming/.*"));

        GcsInboundFileSynchronizingMessageSource source =
                new GcsInboundFileSynchronizingMessageSource(synchronizer);

        source.setLocalDirectory(new File("./work/gcs-incoming"));
        source.setAutoCreateLocalDirectory(true);

        return source;
    }
}
~~~

The poller above runs every 5 seconds. This is an illustrative setting; real intervals should account for latency, object counts, and list/metadata read costs.

Processing files in the channel:

~~~java
import java.io.File;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class GcsFileProcessor {

    @ServiceActivator(inputChannel = "newGcsFiles")
    public void process(File file) {
        // Validate file, scan content, extract metadata, then persist result.
        // Delete the local file only after business processing succeeds and can be safely retried.
    }
}
~~~

Operational notes:

- The local directory must exist or allow the adapter to create it.
- Containers need adequate volume/disk capacity for large files.
- Use file filters to skip temporary files, non-matching patterns, or already-processed files.
- To avoid reprocessing after restarts, use a persistent metadata store/filter instead of relying solely on in-memory state.
- Do not delete local files before downstream processing finishes.
- For GCS adapters, the remote directory is the bucket name; filter object prefixes with a FileListFilter such as GcsRegexPatternFileListFilter. GCS object names may contain slashes, but they are not physical directories.
- Polling bucket listings can generate many requests on large buckets; narrow scope with filters and split buckets when necessary.

### 3.3. Streaming Inbound Adapter

GcsStreamingMessageSource emits an InputStream payload without downloading files to a local temporary directory first. The adapter uses GcsRemoteFileTemplate and GcsSessionFactory.

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.spring.storage.integration.GcsRemoteFileTemplate;
import com.google.cloud.spring.storage.integration.GcsSessionFactory;
import com.google.cloud.spring.storage.integration.filters.GcsRegexPatternFileListFilter;
import com.google.cloud.spring.storage.integration.inbound.GcsStreamingMessageSource;
import java.io.InputStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.core.MessageSource;

@Configuration(proxyBeanMethods = false)
public class GcsStreamingConfiguration {

    @Bean
    @InboundChannelAdapter(
            channel = "gcsStreamingFiles",
            poller = @Poller(fixedDelay = "10000"))
    MessageSource<InputStream> gcsStreamingSource(Storage storage) {

        GcsStreamingMessageSource source =
                new GcsStreamingMessageSource(
                        new GcsRemoteFileTemplate(
                                new GcsSessionFactory(storage)));

        source.setRemoteDirectory("training-documents");
        source.setFilter(
                new GcsRegexPatternFileListFilter("^large-files/.*"));
        return source;
    }
}
~~~

Streaming avoids creating intermediate local files, but the consumer must read and close the stream properly:

~~~java
import java.io.InputStream;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class GcsStreamingProcessor {

    @ServiceActivator(inputChannel = "gcsStreamingFiles")
    public void process(InputStream input) throws Exception {
        try (InputStream stream = input) {
            // Stream bytes to a parser or downstream service.
            // Do not read the entire file into byte[] if the size is large.
        }
    }
}
~~~

Do not hand an InputStream off to another thread and close the stream before that consumer completes. If asynchronous processing is needed, design explicit stream ownership and lifecycle management or stage the file in controlled storage.

GcsStreamingMessageSource can accept a `Comparator<BlobInfo>` to sort processed files. That ordering applies only within a single adapter poll; it provides no global ordering guarantee across polls or across multiple instances.

### 3.4. Outbound Adapter Writing Files to GCS

GcsMessageHandler receives Spring messages with a File payload and writes them to the configured bucket/prefix.

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.spring.storage.integration.GcsSessionFactory;
import com.google.cloud.spring.storage.integration.outbound.GcsMessageHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.expression.common.LiteralExpression;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.MessageHandler;

@Configuration(proxyBeanMethods = false)
public class GcsOutboundConfiguration {

    @Bean
    @ServiceActivator(inputChannel = "writeFilesToGcs")
    MessageHandler gcsOutboundHandler(Storage storage) {

        GcsMessageHandler handler =
                new GcsMessageHandler(new GcsSessionFactory(storage));

        handler.setRemoteDirectoryExpression(
                new LiteralExpression("training-documents"));
        handler.setFileNameGenerator(message ->
                "processed/" + ((java.io.File) message.getPayload()).getName());

        return handler;
    }
}
~~~

A MessagingGateway or service can send `Message<File>` to the `writeFilesToGcs` channel. Control filenames, remote directories, and behavior when an object with the same name already exists. If create-only or generation preconditions are needed for critical workflows, use the Storage client directly or a custom adapter that passes preconditions; do not assume every `Storage.create` option is exposed by GcsMessageHandler.

### 3.5. Polling Filters and Received State

Polling can observe the same object across multiple scans if filters do not persist state or if objects are updated. Built-in GCS filters in the module include:

- GcsSimplePatternFileListFilter: filters by filename pattern.
- GcsRegexPatternFileListFilter: filters by regular expression.
- GcsPersistentAcceptOnceFileListFilter: persists seen state via ConcurrentMetadataStore.

An accept-once filter reduces duplicate processing during polling, but it does not replace business idempotency. An object can be re-uploaded with the same name and a new generation; a name-only filter may not distinguish versions. When per-generation processing is needed, include generation in the processing key or use notification payloads.

## 4. Cloud Storage Pub/Sub Notifications

### 4.1. Notification Configuration

A Pub/Sub notification is a configuration attached to a bucket. The configuration specifies:

- The Pub/Sub topic receiving notifications.
- Which event types to emit.
- Whether metadata payloads are attached.
- An object name prefix used to filter events.
- Optional custom attributes.

Cloud Storage publishes messages to the topic. Each message has two parts:

1. **Attributes:** key/value pairs describing the event.
2. **Payload:** a JSON metadata string of the object when configured with `JSON_API_V1`; `NONE` can be chosen if no payload is needed.

GCS Pub/Sub notifications cannot be managed via Google Cloud Console; use gcloud CLI, Terraform, or appropriate client libraries.

### 4.2. Event Types

| Event type | Meaning | When to use |
| --- | --- | --- |
| OBJECT_FINALIZE | New object or new generation successfully created | File scanning, thumbnail generation, indexing |
| OBJECT_METADATA_UPDATE | Existing object's metadata changed | Sync Content-Type, custom metadata, cache policies |
| OBJECT_DELETE | Object permanently deleted | Index cleanup, updating deleted status |
| OBJECT_ARCHIVE | Live version became a noncurrent version when Object Versioning is enabled | Tracking history or processing archived versions |
| OBJECT_INITIALIZE | Object creation started in a zonal bucket | Tracking object creation progress in zonal buckets |

OBJECT_FINALIZE fires only when upload/copy/rewrite/restore completes successfully; failed uploads do not emit this event.

OBJECT_DELETE represents permanent deletion under notification semantics. It covers objects replaced or deleted by lifecycle rules. When Object Versioning is enabled and a live object merely becomes a noncurrent version, the corresponding event is OBJECT_ARCHIVE, not OBJECT_DELETE.

When replacing an object with the same name, two events are typically emitted:

- OBJECT_FINALIZE for the new generation; the message includes the `overwroteGeneration` attribute.
- OBJECT_ARCHIVE or OBJECT_DELETE for the old generation; the message includes the `overwrittenByGeneration` attribute.

Do not collapse both events into a generic "file updated" action if business logic needs both the old and new generations.

### 4.3. Notification Attributes

Standard attributes include:

| Attribute | Example | Meaning |
| --- | --- | --- |
| notificationConfig | projects/_/buckets/docs/notificationConfigs/3 | Notification configuration that generated the event |
| eventType | OBJECT_FINALIZE | Event type |
| payloadFormat | JSON_API_V1 | Payload format |
| bucketId | training-documents | Bucket containing the object |
| objectId | incoming/invoice-01.pdf | Object name |
| objectGeneration | 1730000000000000 | Object generation |
| eventTime | 2026-11-24T03:15:00Z | Event timestamp in RFC 3339 format |

Some events also include `overwrittenByGeneration` or `overwroteGeneration`. A notification configuration can also attach up to 10 custom attributes.

With `JSON_API_V1` payloads, the body is JSON object metadata matching the JSON API schema. The payload of OBJECT_DELETE describes metadata prior to deletion and includes `timeDeleted`; payloads of other events describe metadata after the change.

### 4.4. Delivery Guarantees

Cloud Storage notifications have important characteristics:

- Delivery from Cloud Storage to Pub/Sub is at-least-once.
- Pub/Sub can also deliver a single event multiple times to subscribers.
- The same event can be delivered repeatedly with different Pub/Sub message IDs.
- Events are not guaranteed to be published to Pub/Sub in chronological order.
- Notifications usually arrive within seconds, but there is no delivery time SLA; delays can be substantial.
- After creating a notification configuration, it can take up to roughly 30 seconds before events start flowing.
- If a notification persistently fails to publish, Cloud Storage may delete the notification configuration after 7 days.
- Enabling notifications adds minor latency to operations that emit events, typically around 0.1 seconds.

Therefore, consumers must tolerate duplicates, delays, out-of-order arrivals, and object state changing before an event is processed.

## 5. Configuring Topic, IAM, and Notifications

### 5.1. Enabling APIs and Creating the Topic

Example using project `training-platform-dev`:

~~~bash
gcloud services enable pubsub.googleapis.com \
  --project=training-platform-dev

gcloud pubsub topics create gcs-object-events \
  --project=training-platform-dev
~~~

Create a subscription for the Spring Boot consumer:

~~~bash
gcloud pubsub subscriptions create gcs-object-events-sub \
  --topic=gcs-object-events \
  --project=training-platform-dev
~~~

The subscription is where the consumer receives messages. A topic does not buffer messages like a standalone application queue unless a matching subscription exists.

### 5.2. Granting Permissions to the Cloud Storage Service Agent

The Cloud Storage service agent for the project owning the bucket has the form:

`service-PROJECT_NUMBER@gs-project-accounts.iam.gserviceaccount.com`

Retrieve the service agent:

~~~bash
gcloud storage service-agent \
  --project=training-platform-dev
~~~

Grant Pub/Sub Publisher on the topic:

~~~bash
gcloud pubsub topics add-iam-policy-binding gcs-object-events \
  --project=training-platform-dev \
  --member="serviceAccount:service-PROJECT_NUMBER@gs-project-accounts.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"
~~~

Replace PROJECT_NUMBER with the actual project number. Grant the role on the specific topic rather than broadly across the project unless needed. If the topic lives in a different project than the bucket, the bucket project's service agent still needs Publisher permission on the target topic.

After granting the role via API/automation, you may need to wait around 30 seconds for the IAM binding to propagate before creating the notification configuration.

### 5.3. Granting Permissions to the Spring Boot Consumer

The application's runtime service account needs:

- `roles/pubsub.subscriber` on the subscription to pull/ack messages.
- `storage.objects.get` on the bucket if the application reads object bytes or metadata.
- `storage.objects.list` only if business logic needs to list objects.
- Other permissions such as create/delete only when the service actually performs those operations.

Do not grant `roles/storage.admin` just to read objects on events. The Cloud Storage service agent publishes events; the Spring Boot consumer subscribes to messages; these are two distinct principals.

The principal configuring notifications needs permission to update bucket metadata and view the Pub/Sub topic. Common roles in documentation are Storage Admin on the bucket and Pub/Sub Admin in the topic's project; narrower predefined or custom roles may be used once exact permissions are identified.

### 5.4. Creating Notifications for a Specific Prefix and Events

~~~bash
gcloud storage buckets notifications create \
  gs://training-documents \
  --topic=projects/training-platform-dev/topics/gcs-object-events \
  --event-types=OBJECT_FINALIZE,OBJECT_METADATA_UPDATE,OBJECT_DELETE,OBJECT_ARCHIVE \
  --payload-format=json \
  --object-prefix=incoming/
~~~

The configuration above emits only events under the `incoming/` prefix and attaches JSON object metadata. To watch all prefixes, omit `--object-prefix`.

List notification configurations:

~~~bash
gcloud storage buckets notifications list \
  gs://training-documents
~~~

Describe a notification configuration:

~~~bash
gcloud storage buckets notifications describe \
  projects/_/buckets/training-documents/notificationConfigs/NOTIFICATION_ID
~~~

Delete a notification configuration:

~~~bash
gcloud storage buckets notifications delete \
  projects/_/buckets/training-documents/notificationConfigs/NOTIFICATION_ID
~~~

Each bucket can have up to 100 notification configurations and up to 10 configurations for the same event type. Creating or deleting a notification configuration increments the bucket's metageneration. Never create a new configuration per object or per request.

## 6. Connecting Pub/Sub with Spring Integration

### 6.1. Dependencies

To use Pub/Sub channel adapters, add the Pub/Sub starter and Spring Integration core:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-pubsub</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-core</artifactId>
</dependency>
~~~

The starter configures PubSubTemplate and subscriber operations using ADC/workload identity. Use the BOM to keep versions aligned.

### 6.2. Creating an Inbound Channel Adapter

PubSubInboundChannelAdapter uses Streaming Pull to receive messages from a subscription and convert them into Spring Messages. By default the payload is `byte[]`; message attributes are mapped to Spring headers.

~~~java
import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import com.google.cloud.spring.pubsub.integration.AckMode;
import com.google.cloud.spring.pubsub.integration.inbound.PubSubInboundChannelAdapter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration(proxyBeanMethods = false)
public class GcsPubSubConfiguration {

    @Bean
    MessageChannel gcsObjectEvents() {
        return new DirectChannel();
    }

    @Bean
    PubSubInboundChannelAdapter gcsObjectEventAdapter(
            @Qualifier("gcsObjectEvents") MessageChannel output,
            PubSubTemplate pubSubTemplate) {

        PubSubInboundChannelAdapter adapter =
                new PubSubInboundChannelAdapter(
                        pubSubTemplate,
                        "gcs-object-events-sub");

        adapter.setOutputChannel(output);
        adapter.setPayloadType(byte[].class);
        adapter.setAckMode(AckMode.MANUAL);

        return adapter;
    }
}
~~~

The subscription name can be a short name within the current project or the full resource name `projects/PROJECT_ID/subscriptions/SUBSCRIPTION_ID`.

Choose DirectChannel to process synchronously on the receiving thread. Use an ExecutorChannel or another queue/channel if offloading to separate threads, while carefully managing ack deadlines and passing the acknowledgment handle to where processing completes.

### 6.3. Attributes and JSON Payload

With the default adapter configuration:

- `message.getPayload()` is a `byte[]` containing the JSON metadata payload.
- Headers `eventType`, `bucketId`, `objectId`, `objectGeneration`, `eventTime`, and `payloadFormat` come from Pub/Sub message attributes.
- `GcpPubSubHeaders.ORIGINAL_MESSAGE` holds the original acknowledgment object for manual ack/nack.

You can set payload type to `String.class` if a Pub/Sub message converter is configured to convert byte payloads to String. This lesson keeps `byte[]` to parse UTF-8 explicitly with Jackson.

### 6.4. Processing Events and Manual Ack/Nack

The example below acks only after the processor finishes. On error, the message is nacked so Pub/Sub can redeliver according to subscription policy.

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.cloud.spring.pubsub.support.BasicAcknowledgeablePubsubMessage;
import com.google.cloud.spring.pubsub.support.GcpPubSubHeaders;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.stereotype.Component;

@Component
public class GcsObjectEventHandler {

    private final ObjectMapper objectMapper;
    private final GcsObjectEventProcessor processor;

    public GcsObjectEventHandler(
            ObjectMapper objectMapper,
            GcsObjectEventProcessor processor) {
        this.objectMapper = objectMapper;
        this.processor = processor;
    }

    @ServiceActivator(inputChannel = "gcsObjectEvents")
    public void handle(Message<byte[]> message) {
        BasicAcknowledgeablePubsubMessage original =
                message.getHeaders().get(
                        GcpPubSubHeaders.ORIGINAL_MESSAGE,
                        BasicAcknowledgeablePubsubMessage.class);

        try {
            String eventType =
                    String.valueOf(message.getHeaders().get("eventType"));
            String bucket =
                    String.valueOf(message.getHeaders().get("bucketId"));
            String objectName =
                    String.valueOf(message.getHeaders().get("objectId"));
            String generation =
                    String.valueOf(message.getHeaders().get("objectGeneration"));
            String eventTime =
                    String.valueOf(message.getHeaders().get("eventTime"));

            JsonNode objectMetadata =
                    objectMapper.readTree(message.getPayload());

            processor.process(
                    eventType,
                    bucket,
                    objectName,
                    Long.parseLong(generation),
                    eventTime,
                    objectMetadata);

            original.ack();
        }
        catch (Exception ex) {
            original.nack();
            throw new MessagingException(message, ex);
        }
    }
}
~~~

GcsObjectEventProcessor is the application's business service. Do not log entire messages if payloads contain sensitive metadata or custom attributes that should not appear in logs.

In real flows, dispatch by event type before processing:

- OBJECT_FINALIZE: read the new generation and start the file processing pipeline.
- OBJECT_METADATA_UPDATE: sync metadata or re-evaluate policy.
- OBJECT_DELETE: update indexes/status; do not try to download the deleted object.
- OBJECT_ARCHIVE: update old version status when versioning is enabled.

### 6.5. Ack Modes and Error Channels

PubSubInboundChannelAdapter has three modes:

| Ack mode | On success | On error |
| --- | --- | --- |
| AUTO | Adapter acks | Adapter nacks if the error propagates back to the adapter |
| AUTO_ACK | Adapter acks | Does not auto-ack/nack when errors are not handled successfully |
| MANUAL | No auto-ack | No auto-ack/nack; application decides explicitly |

In MANUAL mode, the application must call `ack()` or `nack()` on the original message. If both are omitted, the message will be redelivered once the ack deadline expires.

When using an error channel, an error handler that finishes normally is considered successful handling; under AUTO/AUTO_ACK, the message may be acked. If you want the adapter to apply default error handling, the error handler must rethrow the exception. Test error-flow behavior before picking an ack mode.

`nack()` resets the ack deadline to 0 and can trigger immediate redelivery. If the error is permanently invalid data, repeated nacks can create a tight loop. Use retry policies, dead-letter topics, or record rejected status according to business rules.

### 6.6. Ack Deadlines and Processing Duration

Pub/Sub subscriptions have an ack deadline. Streaming subscribers can extend the deadline during processing, subject to a maximum extension period limit.

If files take a long time to process:

- Do not download multi-GB files and process them synchronously inside a handler without accounting for deadlines.
- Decouple event ingestion from long-running processing using an internal queue/job table.
- Ack only after the follow-up work has been durably persisted to a database or another queue.
- Use `spring.cloud.gcp.pubsub.subscriber.max-ack-extension-period` when adjusting extension windows.
- Configure a dead-letter topic and maximum delivery attempts to isolate persistently failing messages.

When acking after inserting a job into the database, the job worker still needs its own idempotency. Acking the event does not mean final file processing is finished; it means the job has been durably accepted.

## 7. Reading the Exact Object from an Event

### 7.1. Use Generation, Not Just Object Name

Events can arrive late. For example:

1. Object `incoming/a.pdf` is uploaded as generation 100.
2. OBJECT_FINALIZE for generation 100 is published.
3. The object is re-uploaded as generation 101.
4. The consumer finally receives the generation 100 event.

If the consumer calls `storage.get(BlobId.of(bucket, objectName))`, it reads live object 101 instead of the bytes that triggered event 100.

Use the generation from the notification:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public Blob loadExactGeneration(
        Storage storage,
        String bucket,
        String objectName,
        long generation) {

    return storage.get(
            BlobId.of(bucket, objectName, generation));
}
~~~

If the old generation no longer exists because versioning is disabled or lifecycle rules deleted it, the result may be null. Treat that as a stale/missing state and handle per business logic; do not automatically substitute the newer live generation.

### 7.2. Use Metageneration for Metadata Events

With OBJECT_METADATA_UPDATE, generation may stay unchanged while metageneration increments. The `JSON_API_V1` payload contains the `metageneration` metadata field.

When performing an update based on a metadata snapshot, pass both generation and metageneration as preconditions:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;

public Blob updateMetadataFromEvent(
        Storage storage,
        String bucket,
        String objectName,
        long generation,
        long metageneration,
        String newCacheControl) {

    Blob current = storage.get(
            BlobId.of(bucket, objectName, generation));

    if (current == null) {
        return null;
    }

    BlobInfo updated = current.toBuilder()
            .setCacheControl(newCacheControl)
            .build();

    return storage.update(
            updated,
            Storage.BlobTargetOption.generationMatch(generation),
            Storage.BlobTargetOption.metagenerationMatch(metageneration));
}
~~~

If the object or metadata changed since the event was emitted, Cloud Storage rejects the precondition rather than overwriting newer state. Handle the conflict by re-reading metadata and re-evaluating business logic.

### 7.3. DELETE and ARCHIVE Events

For OBJECT_DELETE, the payload describes the object prior to deletion and includes `timeDeleted`. Consumers should use the payload to update indexes or business status. Do not assume the object can still be read via the Storage API.

For OBJECT_ARCHIVE, the live version became a noncurrent version. If Object Versioning is enabled, the old generation can still be read if retained. If only version status needs updating, the notification already supplies the object name and generation.

### 7.4. Handling Out-of-Order Events

Do not rely on message arrival order to infer current state. For example, a metadata update event for metageneration 5 may arrive before the event for metageneration 4.

Rules:

- Compare generation first; different generations represent different byte versions.
- Within the same generation, compare metageneration to identify the newer metadata snapshot.
- Never roll database state backward to an older generation/metageneration.
- When updating the object, use matching preconditions.
- If current live data is required, read the latest metadata from the Storage API and compare with the event.
- If an older event is no longer relevant to business logic, mark it stale and ack after recording the outcome.

Pub/Sub ordering keys cannot fix Cloud Storage's upstream event ordering because notifications are not guaranteed to be published in occurrence order. Generation and metageneration are the primary guards.

## 8. Idempotency and Preventing Duplicate Processing

### 8.1. Do Not Use Pub/Sub Message ID as the Unique Event Key

Cloud Storage and Pub/Sub deliver messages at-least-once. The exact same Cloud Storage event can be sent multiple times with different Pub/Sub message IDs. Therefore, storing only the Pub/Sub message ID is insufficient to deduplicate events.

Build an event fingerprint from:

- `bucketId`
- `objectId`
- `objectGeneration`
- `eventType`
- `metageneration` when the event involves metadata
- `notificationConfig` if business logic must distinguish identical events emitted from multiple notification configurations

Example:

~~~java
public String eventKey(
        String bucket,
        String objectName,
        long generation,
        long metageneration,
        String eventType) {

    return bucket + "|" + objectName + "|" + generation
            + "|" + metageneration + "|" + eventType;
}
~~~

This is an illustrative idempotency key. If the same object change is emitted by multiple notification configurations but business processing should run only once, omit `notificationConfig` from the fingerprint.

### 8.2. Inbox Table in the Database

You can track event state using a unique key:

~~~sql
CREATE TABLE gcs_event_inbox (
    event_key        VARCHAR(512) PRIMARY KEY,
    bucket_name      VARCHAR(255) NOT NULL,
    object_name      VARCHAR(1024) NOT NULL,
    generation       NUMERIC(20, 0) NOT NULL,
    metageneration   NUMERIC(20, 0),
    event_type       VARCHAR(64) NOT NULL,
    event_time       TIMESTAMP WITH TIME ZONE,
    status           VARCHAR(32) NOT NULL,
    processed_at     TIMESTAMP WITH TIME ZONE,
    error_message    VARCHAR(2000)
);
~~~

Processing flow:

1. Compute the event key.
2. Insert the inbox record under the unique constraint.
3. If the record already exists in `COMPLETED` state, ack the message and skip side effects.
4. If the record is new, execute business processing and update to `COMPLETED` in the appropriate transaction.
5. Ack after the state is durably committed.
6. On transient error, record error/retry status and nack or route to a retry workflow.

If side effects call a system outside the database, use an outbox or downstream service idempotency key. Never assume a database transaction can roll back completed GCS operations or HTTP calls.

### 8.3. Commit and Ack Ordering

| Sequence | Risk |
| --- | --- |
| Ack first, then write database | Process crash after ack drops the event from retry flow |
| Write database first, then ack | If crash occurs before ack, Pub/Sub redelivers; inbox dedupe prevents duplicate side effects |
| Write database and ack in one transaction | There is no shared distributed transaction between Pub/Sub and the database |

The safe pattern is usually to persist and commit the event/job first, then ack. If the ack fails, the message may be redelivered; the inbox unique key makes redelivery a no-op.

## 9. Retries, Dead-Letter Topics, and Error Handling

### 9.1. Classifying Errors

| Error group | Examples | Handling approach |
| --- | --- | --- |
| Transient | Storage timeout, 429, 5xx, database unavailable | Retry with backoff/jitter |
| Permission/configuration | 403 missing storage.objects.get, wrong topic IAM | Fix IAM/config; avoid infinite nack loops |
| Stale event | Generation already deleted or no longer exists | Record stale, ack if business rules allow |
| Invalid payload | Missing bucket/object/generation or malformed JSON | Route to dead-letter/quarantine |
| Business rejection | Unsupported file format, invalid tenant | Record rejected status; ack after persisting result |
| Duplicate | Event fingerprint already COMPLETED | Skip side effects and ack |

### 9.2. Dead-Letter Topic

Configure a dead-letter topic on the subscription to forward unprocessable messages after the maximum delivery attempts. The runtime service account needs appropriate permissions on the topic/subscription; the Pub/Sub service agent also needs permission to publish to the dead-letter topic per configuration.

Do not use a dead-letter topic as a substitute for error handling. Establish a procedure:

- Monitor dead-lettered message counts.
- Classify failures into permission, payload, schema, and business errors.
- Fix the root cause.
- Replay in a controlled manner after confirming idempotency.
- Record who replayed, when, and how many times.

### 9.3. Backoff and Retry Policy

Pub/Sub subscriptions support retry policies for redelivery with exponential backoff. Manual `nack()` can trigger immediate redelivery; if backoff is desired, configure a retry policy and avoid continuously nacking while a downstream dependency is down.

With AUTO mode, exceptions must propagate back to the adapter to trigger nack. If an error channel catches an exception and exits normally, the adapter may treat the flow as successful and ack. With MANUAL mode, the application must explicitly decide ack/nack on both happy and error paths.

### 9.4. Exactly-Once and the Reality of Spring Adapters

Cloud Storage notifications are at-least-once and can arrive out of order. Spring Framework on Google Cloud Pub/Sub integration does not expose `AckReplyConsumerWithResponse`, which is required to leverage the Pub/Sub Java client's exactly-once feature in applicable scenarios.

Therefore, always design idempotent consumers. Do not rely on delivery guarantees to ensure a side effect occurs only once. Inbox/outbox tables, generation tokens, and unique constraints provide the protection at the application layer.

## 10. Complete Workflow Example: Generating Thumbnails After Upload

### 10.1. Business Model

A document system has bucket `training-documents`, with prefixes `incoming/` and `processed/`:

1. A client uploads a file into `incoming/`.
2. GCS emits `OBJECT_FINALIZE`.
3. Pub/Sub delivers the event to the subscription.
4. Spring Integration receives the event and checks the event key.
5. The processor reads the exact object generation.
6. Validates file type, size, and scans for malware.
7. Generates thumbnail/metadata.
8. Persists results to the database and uploads the output.
9. Acks the event after the work is durably accepted.

~~~mermaid
flowchart TD
    A["Upload incoming/file.pdf"] --> B["OBJECT_FINALIZE"]
    B --> C["Pub/Sub topic"]
    C --> D["Subscription"]
    D --> E["PubSubInboundChannelAdapter"]
    E --> F["Validate attributes + JSON payload"]
    F --> G["Insert idempotency key"]
    G --> H{"Event already completed?"}
    H -->|Yes| ACK["ACK"]
    H -->|No| I["Read exact generation"]
    I --> J["Scan / validate file"]
    J --> K["Generate thumbnail"]
    K --> L["Persist result / outbox"]
    L --> M["Mark completed"]
    M --> ACK
~~~

### 10.2. Processor Reading a Specific Generation

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import org.springframework.stereotype.Service;

@Service
public class GcsObjectEventProcessor {

    private final Storage storage;
    private final DocumentJobService jobs;

    public GcsObjectEventProcessor(
            Storage storage,
            DocumentJobService jobs) {
        this.storage = storage;
        this.jobs = jobs;
    }

    public void process(
            String eventType,
            String bucket,
            String objectName,
            long generation,
            String eventTime,
            com.fasterxml.jackson.databind.JsonNode metadata) {

        if (!"OBJECT_FINALIZE".equals(eventType)) {
            return;
        }

        String eventKey = bucket + "|" + objectName + "|"
                + generation + "|" + eventType;

        if (!jobs.tryStart(eventKey)) {
            return;
        }

        Blob object = storage.get(
                BlobId.of(bucket, objectName, generation));

        if (object == null) {
            jobs.markStale(eventKey);
            return;
        }

        jobs.processExactGeneration(
                eventKey,
                object,
                eventTime,
                metadata);
    }
}
~~~

DocumentJobService illustrates a service persisting inbox/job state. `tryStart` must be guarded by a unique constraint/transaction so two concurrent deliveries cannot launch the same side effect.

### 10.3. Preventing Event Loops

If the processor uploads thumbnails back into the same bucket and notifications watch the entire bucket, uploading the thumbnail triggers another OBJECT_FINALIZE, invoking the processor again.

How to prevent this:

- Subscribe only to the `incoming/` prefix.
- Write outputs to a `processed/` prefix outside the notification filter.
- Or filter events inside the handler based on object name.
- Use metadata markers to distinguish processor-generated outputs when appropriate.

Prefix filtering in the notification configuration reduces unnecessary messages; filtering in code provides an extra safety net.

## 11. Integration Testing

### 11.1. Unit Tests

Verify all logic branches:

- OBJECT_FINALIZE triggers file processing.
- OBJECT_METADATA_UPDATE does not re-run thumbnail generation unnecessarily.
- OBJECT_DELETE updates status and does not call download.
- Duplicate events do not execute side effects a second time.
- Events for older generations do not overwrite newer generation state.
- Metadata updates use the right generation/metageneration.
- Invalid payloads are quarantined/dead-lettered.
- Processor errors do not ack.
- Output uploads do not trigger an event loop.

Mock Storage, ObjectMapper, DocumentJobService, and the acknowledgment object. Unit tests do not prove real GCS notifications are actually published.

### 11.2. Integration Tests with the Pub/Sub Emulator

The Pub/Sub emulator can test subscriber wiring, payload conversion, and ack/nack. You can publish synthetic Cloud Storage notification messages to an emulator topic and verify the Spring Integration flow.

Emulators do not replace the real Cloud Storage notification service; uploading an object to a GCS emulator does not automatically emit real notifications to a Pub/Sub emulator. Separate adapter/message consumer tests from tests of actual GCS notification configuration on a cloud project.

### 11.3. Integration Tests on a Dedicated GCP Project

1. Create a dedicated test bucket, topic, and subscription.
2. Enable the Pub/Sub API and grant `roles/pubsub.publisher` to the Cloud Storage service agent.
3. Create a notification configuration scoped to the `test-incoming/` prefix.
4. Run the Spring Boot consumer using a service account with `roles/pubsub.subscriber`.
5. Upload a test object and wait for `OBJECT_FINALIZE`.
6. Verify payload attributes, generation, and JSON metadata.
7. Re-upload the same object name; verify the new generation and corresponding archive/delete event.
8. Update metadata; verify `OBJECT_METADATA_UPDATE`.
9. Delete the object; verify delete/archive events according to versioning policy.
10. Send the same event twice; verify idempotency.
11. Inject an out-of-order event; verify the generation guard.
12. Temporarily revoke object read permission; verify retry/dead-letter behavior.
13. Clean up notification configurations, subscriptions, topics, and test objects after verification.

Notifications can be delayed and have no delivery time SLA. Tests should wait with reasonable deadlines and assert final state rather than assuming messages arrive within a fixed number of milliseconds.

### 11.4. Failure and Recovery Tests

| Scenario | Expectation |
| --- | --- |
| Pub/Sub delivers duplicate | Only one business side effect executes |
| Consumer crashes after DB commit, before ack | Event is redelivered, but inbox deduplicates it |
| Object replaced before consumer reads | Consumer reads the event's generation or marks stale |
| Older metadata event arrives after newer event | Metageneration is never rolled backward |
| Service agent loses Publisher role | Notification delivery fails; configuration/IAM alert fires |
| Consumer loses Subscriber role | Subscription health/errors reflect permission failure |
| Downstream service times out | Retried with backoff or routed to dead-letter |
| Invalid file | Recorded as rejected/quarantined without infinite retries |
| Notification config deleted | Events stop arriving; drift detection flags it |

## 12. Observability and Operations

### 12.1. Metrics

Monitor at minimum:

- Pub/Sub messages received by event type.
- Ack, nack, redelivery, and dead-letter counts.
- Latency from `eventTime` to when the consumer starts processing.
- Object processing duration and bytes read.
- Duplicate rate by event fingerprint.
- Stale generation rate.
- Storage 403/404/429/5xx error counts.
- Outstanding messages and ack deadline extensions.
- Successful/failed events by bucket/prefix.

### 12.2. Logging and Tracing

Log event type, bucket, policy-safe object name, generation, metageneration, eventTime, Pub/Sub message ID, and event fingerprint. Never log file contents, signed URLs, secrets, or sensitive metadata.

Use trace/correlation IDs from the upload request or internal document IDs to correlate upload, notification, file processing, and database updates.

### 12.3. Health Checks

PubSubInboundChannelAdapter can integrate with a Pub/Sub subscriber health indicator. To expose subscriber health in Spring Boot Actuator, configure the health tracker registry for the adapter according to your release documentation.

Health checks should distinguish:

- Application started.
- Subscriber connected.
- Subscription has message backlog.
- Processor can still read objects.
- Downstream dependencies are healthy.

A healthy subscriber does not automatically mean business processing is keeping up with backlog.

## 13. IAM and Security

| Principal | Permissions | Scope |
| --- | --- | --- |
| Cloud Storage service agent | `roles/pubsub.publisher` | Topic receiving notifications |
| Spring Boot event consumer | `roles/pubsub.subscriber` | Specific subscription |
| Spring Boot object processor | `storage.objects.get` | Bucket/prefix to read |
| Spring Boot polling source | `storage.objects.list`, `storage.objects.get` | Bucket/prefix to synchronize |
| Spring Boot outbound writer | `storage.objects.create` and overwrite permissions if needed | Output bucket |
| Provisioning identity | Manage bucket notifications, topics, subscriptions | Managed resources |

Principles:

- Use workload identity/ADC instead of storing service account JSON keys in containers.
- Separate the notification-configuring principal from the runtime principal.
- Grant Publisher to the service agent only on the target topic.
- Grant Subscriber to the app only on the subscription it consumes.
- Restrict Storage object permissions to required buckets.
- Never let event payloads pick arbitrary buckets; allowlist buckets/prefixes accepted by the application.
- Validate event attributes and payloads before calling the Storage API.
- Never trust `objectId` as a local file path; sanitize when writing to the filesystem.
- Never let events trigger arbitrary URLs or commands.

## 14. Limits, Quotas, and Costs

- A bucket can have up to 100 notification configurations and up to 10 configurations per event type.
- Creating/deleting a notification configuration increments the bucket's metageneration.
- Notifications have latency, no delivery SLA, and can experience significant delays.
- Both GCS notifications and Pub/Sub are at-least-once; consumers must deduplicate.
- Polling generates periodic list/metadata requests; large buckets or aggressive polling intervals raise load and cost.
- Pub/Sub incurs publish/delivery/storage costs based on configuration and usage.
- A single GCS event can trigger multiple downstream services; fanning out across many subscriptions multiplies processed messages.
- GCS notifications report only supported object events. Bucket operations, object reads, and other actions require Cloud Audit Logs or other mechanisms.
- GCS notifications do not guarantee event order; never use message receipt timestamps for data ordering.

For buckets with millions of objects, prefer prefix filters and event-driven processing over scanning the entire bucket every few seconds. When polling is used, design prefix partitioning, fetch limits, and filter state.

## 15. Comparing Pub/Sub Notifications, Eventarc, and Cloud Audit Logs

| Mechanism | Payload | When to use | Considerations |
| --- | --- | --- | --- |
| GCS Pub/Sub notifications | Pub/Sub attributes + `JSON_API_V1` object metadata | Need topics/subscriptions, multiple consumers, explicit ack/retry control | At-least-once, no ordering guarantee |
| Eventarc Cloud Storage triggers | CloudEvents | Route events to Cloud Run/functions or target services | Event envelope differs from Pub/Sub notification payloads |
| Cloud Audit Logs routed to Pub/Sub | Audit log entry | Monitor bucket operations, object reads, or actions lacking GCS notification events | Requires audit log and log sink/filter setup |

Do not parse CloudEvents as `JSON_API_V1` notifications. If choosing Eventarc, handlers must read the CloudEvent envelope and its corresponding data schema. If choosing Pub/Sub notifications, consumers read message attributes and metadata payloads as shown earlier.

## 16. Comparison with AWS S3 and Azure Blob Storage

| Aspect | Google Cloud Storage | Amazon S3 | Azure Blob Storage |
| --- | --- | --- | --- |
| Object change events | Pub/Sub notifications | S3 Event Notifications | Event Grid events |
| Message transport | Pub/Sub topic/subscription | SNS, SQS, Lambda, or EventBridge | Event Grid, Queue Storage, or Service Bus |
| Spring consumer | PubSubInboundChannelAdapter | Spring Cloud AWS SQS listener/adapter | Azure Spring integration or Service Bus/Event Grid integration |
| Payload identity | bucket, object, generation, event type | bucket, key, version ID, event name | account/container/blob, ETag/version ID, event type |
| Delivery | At-least-once, unordered | At-least-once across many notification destinations | At-least-once and retries per Event Grid |
| Duplicate handling | Event fingerprint + inbox | Event key/version ID + inbox | Event ID + inbox |
| Object version guard | Generation/metageneration | Version ID/ETag | Version ID/ETag |

All providers decouple object storage from event transport. However, event envelopes, identity tokens, and retry semantics differ. In multi-cloud adapters, normalize internal events such as ObjectCreated, ObjectDeleted, ObjectMetadataChanged, and ObjectVersionArchived while retaining provider event IDs, version tokens, and raw payloads for traceability.

## 17. Comprehensive Hands-On Exercise

**Context:** Build the Spring Boot `document-api` application that receives uploaded files under the `incoming/` prefix, validates files, generates thumbnails, and updates the database. When users modify metadata or delete files, the system must synchronize state accordingly.

### Task A — GCS Polling Adapter

1. Add `spring-cloud-gcp-storage` and `spring-integration-file`.
2. Create a Storage bean via ADC/workload identity.
3. Configure `GcsInboundFileSynchronizingMessageSource` to poll a test prefix.
4. Configure `GcsStreamingMessageSource` and process the InputStream.
5. Use filters to avoid re-reading files unnecessarily.
6. Create `GcsMessageHandler` to write files to an output prefix.

### Task B — Pub/Sub Notifications

1. Enable the Pub/Sub API and create a topic/subscription.
2. Grant `roles/pubsub.publisher` to the Cloud Storage service agent.
3. Create a notification configuration for OBJECT_FINALIZE, OBJECT_METADATA_UPDATE, and OBJECT_DELETE.
4. Scope it to the `incoming/` prefix.
5. Configure `PubSubInboundChannelAdapter` and `MessageChannel`.
6. Parse event attributes and JSON metadata payloads.

### Task C — Safe Processing

1. Read objects using the generation from the event.
2. Use generation/metageneration preconditions when updating objects.
3. Create an inbox table with a unique event key.
4. Ack after committing the event/job to the database.
5. Nack transient errors and configure a dead-letter topic.
6. Handle duplicates and out-of-order events.
7. Prevent event loops when the processor writes outputs.

### Task D — Testing and Observability

- Test duplicate events and ack failures.
- Test objects overwritten before the event is processed.
- Test metadata updates and deletions.
- Test missing IAM permissions.
- Test the Pub/Sub emulator with synthetic notifications.
- Test real GCS notifications on a dedicated project.
- Monitor backlog, processing latency, dead-letter counts, and stale generations.
- Compare with S3 Event Notifications and Azure Event Grid.

**Pass criteria:** The application distinguishes polling from event-driven flows; configures GCS notifications and Pub/Sub IAM properly; receives events via Spring Integration; reads the exact object generation; handles duplicates/out-of-order arrivals; acks/nacks at the right time; and includes integration tests proving the real event flow.

## 18. Key Takeaways

- GCS channel adapters read/write files over Spring MessageChannels; inbound adapters are polling-based, not event streams.
- `GcsInboundFileSynchronizingMessageSource` downloads files to a local directory; `GcsStreamingMessageSource` emits InputStreams; `GcsMessageHandler` writes files to GCS.
- Object change notifications flow along Cloud Storage → Pub/Sub topic → subscription → `PubSubInboundChannelAdapter` → Spring Integration flow.
- The Cloud Storage service agent needs `roles/pubsub.publisher` on the topic; the Spring Boot consumer needs `roles/pubsub.subscriber` on the subscription and `storage.objects.get` if reading files.
- OBJECT_FINALIZE, OBJECT_METADATA_UPDATE, OBJECT_DELETE, and OBJECT_ARCHIVE have distinct semantics; replacing an object can emit two events.
- Pub/Sub messages carry attributes and metadata payloads; `JSON_API_V1` describes post-change metadata, whereas delete payloads describe pre-delete state and include `timeDeleted`.
- Notifications are at-least-once, can duplicate, arrive late, and arrive out of order; do not rely on Pub/Sub message IDs or arrival timestamps for deduplication or ordering.
- Use bucket/object/generation/eventType and metageneration when needed to build idempotency keys and read the exact object version.
- Ack only after side effects or jobs are durably persisted; handle duplicates via an inbox/unique constraint.
- Use retry policies, dead-letter topics, metrics, and Cloud Audit Logs for reliable operations.

### References

- [Pub/Sub notifications for Cloud Storage](https://docs.cloud.google.com/storage/docs/pubsub-notifications)
- [Configure Pub/Sub notifications for Cloud Storage](https://docs.cloud.google.com/storage/docs/reporting-changes)
- [gcloud storage buckets notifications create](https://docs.cloud.google.com/sdk/gcloud/reference/storage/buckets/notifications/create)
- [Spring Integration — Spring Framework on Google Cloud](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/spring-integration.html)
- [Using Pub/Sub in Spring applications](https://docs.cloud.google.com/pubsub/docs/spring)
- [Spring Cloud GCP PubSubInboundChannelAdapter API](https://googleapis.dev/java/spring-cloud-gcp/latest/com/google/cloud/spring/pubsub/integration/inbound/PubSubInboundChannelAdapter.html)
- [GcsInboundFileSynchronizingMessageSource API](https://googleapis.dev/java/spring-cloud-gcp/latest/com/google/cloud/spring/storage/integration/inbound/GcsInboundFileSynchronizingMessageSource.html)
- [GcsStreamingMessageSource API](https://googleapis.dev/java/spring-cloud-gcp/latest/com/google/cloud/spring/storage/integration/inbound/GcsStreamingMessageSource.html)
- [GcsMessageHandler API](https://googleapis.dev/java/spring-cloud-gcp/latest/com/google/cloud/spring/storage/integration/outbound/GcsMessageHandler.html)
- [Cloud Storage data consistency](https://docs.cloud.google.com/storage/docs/consistency)
- [Pub/Sub subscription retry policy](https://docs.cloud.google.com/pubsub/docs/subscription-retry-policy)
- [Pub/Sub dead-letter topics](https://docs.cloud.google.com/pubsub/docs/dead-letter-topics)
- [Eventarc Cloud Storage events](https://docs.cloud.google.com/eventarc/docs/cloudevents)
