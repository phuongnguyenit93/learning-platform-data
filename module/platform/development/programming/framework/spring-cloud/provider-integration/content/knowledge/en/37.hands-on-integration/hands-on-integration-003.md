# Asynchronous File Processing via Events, Queues, and Workers

## 1. Problem Statement and Objectives

An application receiving documents, images, or videos should not hold HTTP requests open while running virus scans, content extraction, thumbnail generation, OCR, indexing, or AI service calls. These tasks have variable processing times, can fail transiently, and require scaling workers independently from the upload API.

An appropriate architecture is event-driven file processing:

1. The client uploads an object to a bucket/container.
2. Object storage emits an event when the object is created or finalized.
3. The event is routed into a durable queue.
4. A Spring Boot worker receives the message, validates the event, and creates a processing job.
5. The worker reads the exact object version, runs the business pipeline, and persists results.
6. The message is ACKed/completed after the job has been durably accepted or processed successfully, depending on the chosen model.

This lab implements the same workflow across three providers:

- **AWS:** Amazon S3 Event Notifications or EventBridge → Amazon SQS → Spring Cloud AWS @SqsListener.
- **Google Cloud:** Cloud Storage notifications → Pub/Sub → Spring Integration's PubSubInboundChannelAdapter.
- **Azure:** Blob Storage events → Event Grid → Azure Service Bus → Spring Cloud Azure @ServiceBusListener.

Each provider has a different event envelope, retry mechanism, and message settlement model. We normalize events into a single internal work contract, while adapters handle data translation and broker communication.

This lesson belongs to the **Hands-on Integration** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with managed services on AWS, Azure, and Google Cloud via their corresponding Spring Cloud libraries; covering identity and permission configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. This lesson combines storage, messaging, identity, error handling, and testing into a complete pipeline.

After completing this lesson, you will be able to:

- Distinguish between storage events, broker messages, and business jobs.
- Design queues to decouple upload throughput from file processing throughput.
- Configure S3 → SQS, GCS → Pub/Sub, and Blob Storage → Event Grid → Service Bus.
- Write Spring Boot listeners/adapters to consume events from each broker.
- Normalize events into an internal work contract.
- Handle duplicates, out-of-order events, and overwritten objects.
- Use an inbox/idempotency key and job state to prevent duplicate side effects.
- Choose when to ACK/complete relative to processing duration.
- Configure retries, visibility timeouts, lock renewal, and dead-letter queues.
- Tune concurrency, backpressure, and worker capacity.
- Monitor queue backlog, processing latency, failure rate, and DLQs.
- Test end-to-end from object upload to processing results.

> **Scope:** Examples focus on object creation finalization events (ObjectCreated, OBJECT_FINALIZE, Microsoft.Storage.BlobCreated). Deletion or metadata update events can follow the same architecture but require separate business handlers. Dependency versions are managed via a BOM compatible with your Spring Boot version; do not mix BOMs across the three providers.

## 2. Overall Architecture

### 2.1. Components and responsibilities

~~~mermaid
flowchart LR
    CLIENT["Browser / upload API"] --> STORE["Object storage"]
    STORE --> EVENT["Storage event source"]
    EVENT --> BROKER["Durable message broker"]
    BROKER --> ADAPTER["Spring Boot message adapter"]
    ADAPTER --> INBOX["Inbox / job database"]
    INBOX --> WORKER["Processing workers"]
    WORKER --> READ["Read exact object version"]
    READ --> SCAN["Validate / scan / transform"]
    SCAN --> OUTPUT["Processed object storage"]
    SCAN --> RESULT["Database result"]
    RESULT --> DONE["Job completed"]
    BROKER -. "Retry / redelivery" .-> ADAPTER
    ADAPTER -. "Permanent failure" .-> DLQ["Dead-letter queue"]
~~~

| Component | Responsibility | Should not do |
| --- | --- | --- |
| Object storage | Store bytes and emit events when objects change | Run the entire business pipeline |
| Event router | Filter events and route to the right queue/topic | Read large files or process synchronously |
| Broker | Persist messages, deliver to consumers, retry/redeliver | Store large file payloads |
| Spring adapter | Receive messages, parse envelopes, validate event source | Blindly trust every field provided by the message |
| Inbox/job database | Deduplicate, store state, leases, and retry schedules | Store file bytes |
| Worker | Read objects, process, write outputs | Hold upload HTTP requests open |
| DLQ | Hold messages that cannot be processed after retry policy | Become an unmonitored error dumping ground |

### 2.2. Why place a queue between events and workers?

Storage events can arrive in bursts. Uploading thousands of files in a batch can generate thousands of events in seconds, whereas OCR or virus scanning can only process a small number per second.

A queue helps:

- Absorb bursts and buffer work while workers are busy or temporarily paused.
- Scale workers independently from the upload API.
- Tune concurrency according to CPU, memory, database connections, and downstream limits.
- Retry when workers fail or processes restart.
- Decouple the storage producer from file-processing consumers.
- Monitor backlog to detect whether processing lags behind ingestion rate.

Do not send file bytes inside messages. Messages should only carry object identifiers, version tokens, event types, and small metadata. Workers download files directly from storage using their workload identity.

### 2.3. Two processing styles

**Style A — process directly inside the listener:** the listener receives the message, downloads the file, runs the pipeline, and then ACKs. Suitable for small files with short, bounded processing times.

**Style B — listener durably persists the job:** the listener parses the event, writes an inbox/job row to the database, and then ACKs; an independent worker pool picks up jobs from the database for long-running processing. Suitable for OCR, video, AI inference, large files, or multi-step workflows.

This lesson uses Style B as the primary architecture. It shortens message lock/visibility hold times and ensures the broker is only responsible for guaranteeing durable job ingestion. If you choose Style A, configure visibility/ack deadline/lock renewal longer than processing time and remain idempotent.

## 3. Distinguishing Events, Messages, and Jobs

These three concepts are related but not identical:

- **Storage event:** describes what happened to an object, e.g., object incoming/report.pdf was created.
- **Broker message:** a delivery of the event held by the broker for a subscriber; it has delivery count, message ID, and ack/lock state.
- **Processing job:** a business task created by the application, e.g., virus scan, OCR, and thumbnail generation for a specific object generation.

One storage event can create multiple business jobs. For example, one uploaded file can create VIRUS_SCAN, OCR, and THUMBNAIL jobs. Conversely, a single job may be retried multiple times while remaining the same logical job.

~~~mermaid
flowchart TD
    E["ObjectCreated event"] --> M["Broker message"]
    M --> N["Normalize + deduplicate"]
    N --> J1["Job: virus scan"]
    N --> J2["Job: OCR"]
    N --> J3["Job: thumbnail"]
    J1 --> R["Document state"]
    J2 --> R
    J3 --> R
~~~

Do not use the broker message ID as the sole idempotency key for storage events. The same storage event may be redelivered with a different broker message ID.

## 4. Internal Work Contract

### 4.1. Normalizing events from three providers

The providers use different envelopes:

| Provider | Event identity | Object identity/version | Event type |
| --- | --- | --- | --- |
| S3 | eventName, eventTime, sequencer; EventBridge has id | bucket, key, versionId, ETag | s3:ObjectCreated:* |
| GCS | notificationConfig, eventTime, attributes | bucketId, objectId, objectGeneration, metageneration | OBJECT_FINALIZE |
| Azure Blob | Event Grid id, eventTime, subject | container/blob in subject, ETag, sequencer | Microsoft.Storage.BlobCreated |

Normalized into a single record:

~~~java
import java.time.Instant;

public record FileWorkItem(
        String provider,
        String eventKey,
        String eventType,
        String bucketOrContainer,
        String objectKey,
        String versionToken,
        String eTag,
        String sequencer,
        String contentType,
        Long sizeBytes,
        Instant occurredAt,
        String correlationId) {
}
~~~

Meaning:

- eventKey: stable deduplication key constructed by the adapter from provider data.
- versionToken: version ID or generation if provided by the provider.
- eTag: token to verify the object has not changed.
- sequencer: helps determine event ordering on the same object when provided.
- correlationId: links the upload request, event, job, and logs.

Do not force versionToken, ETag, and sequencer into identical semantics. Adapters preserve raw values and only convert when equivalent rules apply.

### 4.2. Constructing the event key

Some suggestions:

| Provider | Suggested event key |
| --- | --- |
| S3 notification | bucket + key + versionId (if versioning enabled) + eventName + sequencer |
| S3 EventBridge | EventBridge id; also store bucket/key/versionId for traceability |
| GCS | bucketId + objectId + objectGeneration + eventType; add metageneration for metadata updates |
| Azure Event Grid | Event Grid id; also store source + subject + eTag + sequencer |

You can hash the normalized string with SHA-256 to produce a short key. If the same object event is emitted from multiple notification configurations and business logic only wants to process it once, do not include the notification configuration ID in the key. If each subscription is an independent workflow, include the workflow name in the job key.

### 4.3. Small job messages, explicit object pointers

An internal job payload may look like:

~~~json
{
  "jobId": "7d9f9e36-3d91-4c2b-9c11-1d8b7c9c5a20",
  "eventKey": "sha256:...",
  "provider": "gcs",
  "bucketOrContainer": "training-documents",
  "objectKey": "incoming/report.pdf",
  "versionToken": "1730000000000000",
  "operation": "DOCUMENT_INGEST",
  "attempt": 0,
  "correlationId": "upload-req-9c3f"
}
~~~

The message contains no file bytes, access tokens, signed URLs, or credentials. Never pass a URL supplied by an event to an arbitrary HTTP client. The backend must map buckets/containers and endpoints from trusted configuration, then validate the object key against a prefix allowlist.

## 5. Inbox and Job State Design

### 5.1. Inbox table

The inbox records ingested events to prevent duplicates:

~~~sql
CREATE TABLE storage_event_inbox (
    event_key          VARCHAR(128) PRIMARY KEY,
    provider           VARCHAR(32) NOT NULL,
    event_type         VARCHAR(128) NOT NULL,
    bucket_name        VARCHAR(255) NOT NULL,
    object_key         VARCHAR(1024) NOT NULL,
    version_token      VARCHAR(256),
    e_tag              VARCHAR(256),
    sequencer          VARCHAR(256),
    occurred_at        TIMESTAMP WITH TIME ZONE,
    received_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    status             VARCHAR(32) NOT NULL,
    last_error         VARCHAR(2000)
);
~~~

### 5.2. Job table

~~~sql
CREATE TABLE file_processing_jobs (
    job_id             UUID PRIMARY KEY,
    event_key          VARCHAR(128) NOT NULL,
    job_type           VARCHAR(64) NOT NULL,
    status             VARCHAR(32) NOT NULL,
    attempt_count      INTEGER NOT NULL DEFAULT 0,
    next_attempt_at    TIMESTAMP WITH TIME ZONE,
    lease_owner        VARCHAR(128),
    lease_until        TIMESTAMP WITH TIME ZONE,
    created_at         TIMESTAMP WITH TIME ZONE NOT NULL,
    started_at         TIMESTAMP WITH TIME ZONE,
    completed_at       TIMESTAMP WITH TIME ZONE,
    last_error         VARCHAR(2000),
    CONSTRAINT uq_file_job UNIQUE (event_key, job_type)
);
~~~

Common statuses:

| Status | Meaning |
| --- | --- |
| PENDING | Accepted, waiting for worker |
| RUNNING | Worker claimed job with a lease |
| RETRY_WAIT | Transient error, waiting for next_attempt_at |
| COMPLETED | Processed successfully |
| REJECTED | Invalid file or event, do not retry |
| DEAD | Exhausted retry policy, needs investigation or replay |
| CANCELLED | Job cancelled per business rules |

### 5.3. Accepting events in a single transaction

The listener executes:

1. Parse and validate the event envelope.
2. Verify that source account/project/bucket/container is in the allowlist.
3. Generate the event key.
4. Insert the inbox row.
5. Insert the job row with a unique constraint.
6. Commit the transaction.
7. ACK/complete the broker message.

If the message is redelivered after commit but before ACK, the unique constraint makes the subsequent ingestion a no-op. The listener can ACK the duplicate after confirming the event is durably stored.

Example service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EventInboxService {

    private final StorageEventInboxRepository inbox;
    private final FileProcessingJobRepository jobs;

    public EventInboxService(
            StorageEventInboxRepository inbox,
            FileProcessingJobRepository jobs) {
        this.inbox = inbox;
        this.jobs = jobs;
    }

    @Transactional
    public void accept(FileWorkItem item) {
        if (inbox.existsByEventKey(item.eventKey())) {
            return;
        }

        inbox.insertReceived(item);
        jobs.insertPending(
                item.eventKey(),
                "DOCUMENT_INGEST");
    }
}
~~~

The illustrative repositories must perform unique-constraint inserts safely when two listeners receive duplicates concurrently. You can use INSERT ... ON CONFLICT DO NOTHING on PostgreSQL or catch unique violations appropriately for your database.

## 6. Worker Pool and State Machine

### 6.1. Claiming jobs with a lease

Workers do not hold a database transaction open for the entire duration of reading and processing a file. A worker claims a job, writes RUNNING and a lease, commits the transaction, and only then processes it.

With PostgreSQL, one way to claim is:

~~~sql
WITH candidate AS (
    SELECT job_id
    FROM file_processing_jobs
    WHERE
        (status IN ('PENDING', 'RETRY_WAIT')
         AND COALESCE(next_attempt_at, now()) <= now())
        OR
        (status = 'RUNNING' AND lease_until < now())
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE file_processing_jobs j
SET status = 'RUNNING',
    attempt_count = attempt_count + 1,
    lease_owner = :worker_id,
    lease_until = now() + interval '5 minutes',
    started_at = now()
FROM candidate c
WHERE j.job_id = c.job_id
RETURNING j.*;
~~~

Leases allow another worker to reclaim the job if a process crashes mid-flight. Lease duration must exceed the expected processing interval or be renewed via a heartbeat during processing.

### 6.2. Processing pipeline

~~~mermaid
flowchart TD
    A["Claim PENDING job"] --> B["Validate object reference"]
    B --> C["Read exact object version"]
    C --> D["Check size / content type"]
    D --> E["Virus scan / file signature"]
    E --> F["Parse / OCR / transform"]
    F --> G["Write output to processed/"]
    G --> H["Persist metadata and result"]
    H --> I["Mark COMPLETED"]
    C -->|Transient error| R["RETRY_WAIT"]
    D -->|Invalid file| X["REJECTED"]
    E -->|Malware detected| X
    F -->|Transient error| R
    G -->|Transient error| R
~~~

A worker service can be written as follows:

~~~java
import org.springframework.stereotype.Service;

@Service
public class FileProcessingWorker {

    private final ObjectVersionReader objectReader;
    private final DocumentPipeline pipeline;
    private final FileProcessingJobRepository jobs;

    public FileProcessingWorker(
            ObjectVersionReader objectReader,
            DocumentPipeline pipeline,
            FileProcessingJobRepository jobs) {
        this.objectReader = objectReader;
        this.pipeline = pipeline;
        this.jobs = jobs;
    }

    public void process(ClaimedFileJob job) {
        try {
            try (var input = objectReader.open(job.objectReference())) {
                pipeline.process(job, input);
            }

            jobs.markCompleted(job.jobId());
        }
        catch (PermanentFileException ex) {
            jobs.markRejected(job.jobId(), ex.getMessage());
        }
        catch (Exception ex) {
            jobs.scheduleRetry(job.jobId(), ex.getMessage());
        }
    }
}
~~~

ObjectVersionReader, DocumentPipeline, ClaimedFileJob, and the repository are illustrative domain abstractions. scheduleRetry should calculate backoff, increment attempt count, and transition to DEAD when retries are exhausted.

### 6.3. Why use leases instead of long transactions?

A large file can take several minutes to scan or convert. Holding a database transaction open during that time causes:

- Rapid connection pool exhaustion.
- Long-lived row locks.
- Extra pressure on database vacuum/maintenance.
- Worker crashes potentially holding transactions open until timeout.
- Difficulty scaling workers independently.

Claiming a lease and committing ensures the database only holds locks briefly. Worker heartbeats extend the lease when needed; if a worker disconnects, the lease expires so the job can be reclaimed.

## 7. AWS — S3 Event Notifications and SQS

### 7.1. Event flow

~~~mermaid
flowchart LR
    S3["Amazon S3 bucket"] -->|ObjectCreated| SQS["SQS Standard queue"]
    SQS --> LISTENER["@SqsListener"]
    LISTENER --> INBOX["Inbox + job DB"]
    INBOX --> WORKER["Worker pool"]
    WORKER -->|GetObject| S3
    SQS -. "maxReceiveCount exceeded" .-> DLQ["SQS dead-letter queue"]
~~~

Amazon S3 can send notifications to SQS Standard, SNS, or Lambda. If you need EventBridge rules, enable S3 events to EventBridge and route to SQS. S3 does not send notifications directly to SQS FIFO; if FIFO is needed, use EventBridge as the routing layer.

S3 event notifications are designed for at-least-once delivery and do not guarantee ordering. Events usually arrive within seconds but can occasionally be delayed. Therefore, workers must deduplicate and check version/sequencer.

### 7.2. Configuring notifications

Example notification configuration filtered by the incoming/ prefix:

~~~json
{
  "QueueConfigurations": [
    {
      "Id": "document-created",
      "QueueArn": "arn:aws:sqs:ap-southeast-1:123456789012:file-events",
      "Events": [
        "s3:ObjectCreated:*"
      ],
      "Filter": {
        "Key": {
          "FilterRules": [
            {
              "Name": "prefix",
              "Value": "incoming/"
            }
          ]
        }
      }
    }
  ]
}
~~~

Apply the configuration using put-bucket-notification-configuration after the queue and queue policy are ready. The queue policy must allow the S3 service principal to send messages, restricted by aws:SourceArn to the exact bucket and by aws:SourceAccount.

The S3 bucket and target SQS queue must be in the same AWS Region. Direct S3 notifications use an SQS Standard queue; if FIFO is required, route via EventBridge as noted in the architecture section.

Example policy statement:

~~~json
{
  "Effect": "Allow",
  "Principal": {
    "Service": "s3.amazonaws.com"
  },
  "Action": "sqs:SendMessage",
  "Resource": "arn:aws:sqs:ap-southeast-1:123456789012:file-events",
  "Condition": {
    "ArnEquals": {
      "aws:SourceArn": "arn:aws:s3:::training-documents"
    },
    "StringEquals": {
      "aws:SourceAccount": "123456789012"
    }
  }
}
~~~

If using EventBridge as the source, configure EventBridge targets and IAM roles per EventBridge documentation; the event envelope differs from S3 notification JSON.

### 7.3. Spring Cloud AWS dependencies and configuration

Use the Spring Cloud AWS BOM compatible with Spring Boot and add the SQS and S3 starters:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_AWS_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-sqs</artifactId>
    </dependency>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-s3</artifactId>
    </dependency>
</dependencies>
~~~

Queue configuration:

~~~yaml
app:
  queue:
    file-events: file-events
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
~~~

The application uses the AWS SDK default credentials provider. The runtime identity needs sqs:ReceiveMessage, sqs:DeleteMessage, and sqs:GetQueueAttributes on the queue; if using SQS encryption with KMS, appropriate KMS permissions are also required. The worker needs s3:GetObject on the processing prefix; only grant s3:ListBucket if objects are actually listed.

### 7.4. Listener for S3 events

S3 notification bodies typically contain Records. Object keys in records are URL-encoded; decode them before calling S3 APIs. Test events like s3:TestEvent may not contain Records, so the parser must handle them separately.

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class S3NotificationNormalizer {

    private final ObjectMapper mapper;

    public S3NotificationNormalizer(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public List<FileWorkItem> parse(String body) throws Exception {
        JsonNode root = mapper.readTree(body);
        JsonNode records = root.path("Records");

        List<FileWorkItem> result = new ArrayList<>();

        for (JsonNode record : records) {
            String eventName = record.path("eventName").asText();
            if (!eventName.startsWith("ObjectCreated:")) {
                continue;
            }

            JsonNode s3 = record.path("s3");
            JsonNode object = s3.path("object");

            String bucket = s3.path("bucket").path("name").asText();
            String encodedKey = object.path("key").asText();
            String key = URLDecoder.decode(
                    encodedKey, StandardCharsets.UTF_8);

            String versionId = object.path("versionId").asText(null);
            String eTag = object.path("eTag").asText(null);
            String sequencer = object.path("sequencer").asText(null);
            String eventTime = record.path("eventTime").asText();

            String eventKey = bucket + "|" + key + "|"
                    + (versionId != null ? versionId : sequencer)
                    + "|" + eventName;

            result.add(new FileWorkItem(
                    "aws-s3",
                    eventKey,
                    eventName,
                    bucket,
                    key,
                    versionId,
                    eTag,
                    sequencer,
                    null,
                    null,
                    java.time.Instant.parse(eventTime),
                    record.path("responseElements")
                            .path("x-amz-request-id").asText(null)));
        }

        return result;
    }
}
~~~

If using EventBridge, create a separate normalizer for the EventBridge schema; do not feed EventBridge events into the S3 notification parser as if the two payloads were identical.

The listener only ingests events and persists jobs:

~~~java
import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.stereotype.Component;

@Component
public class S3FileEventListener {

    private final S3NotificationNormalizer normalizer;
    private final EventInboxService inbox;

    public S3FileEventListener(
            S3NotificationNormalizer normalizer,
            EventInboxService inbox) {
        this.normalizer = normalizer;
        this.inbox = inbox;
    }

    @SqsListener("${app.queue.file-events}")
    public void receive(String body) throws Exception {
        for (FileWorkItem item : normalizer.parse(body)) {
            inbox.accept(item);
        }
    }
}
~~~

With the default ON_SUCCESS acknowledgement mode, Spring Cloud AWS ACKs the message after the listener completes successfully. If the listener throws an exception, the message is not deleted from the queue and can be redelivered after the visibility timeout. Do not catch and swallow exceptions before the job has been durably persisted.

### 7.5. Reading the exact object version

If the bucket has versioning enabled, pass versionId from the S3 event when calling GetObject. If no version ID is present, use ETag as an If-Match condition to avoid processing replaced bytes:

~~~java
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import java.io.InputStream;

public InputStream openS3Object(
        S3Client client,
        String bucket,
        String key,
        String versionId,
        String eTag) {

    GetObjectRequest.Builder request = GetObjectRequest.builder()
            .bucket(bucket)
            .key(key);

    if (versionId != null) {
        request.versionId(versionId);
    }
    else if (eTag != null) {
        request.ifMatch(eTag);
    }

    return client.getObject(request.build());
}
~~~

Close the stream once the worker finishes processing. Do not load large files into a byte[] if the pipeline can stream them.

### 7.6. Visibility timeout, retries, and DLQ

SQS keeps a message invisible for the visibility timeout after a consumer receives it. If the worker does not ACK/delete the message before the timeout, the message can be redelivered. Set the visibility timeout longer than expected processing time if processing directly in the listener; for very large files, persist the job, ACK early, and process via a worker pool.

Configure a redrive policy on the queue:

~~~json
{
  "deadLetterTargetArn": "arn:aws:sqs:ap-southeast-1:123456789012:file-events-dlq",
  "maxReceiveCount": 5
}
~~~

maxReceiveCount defines how many times a message can be received before moving to the DLQ. Separate transient and permanent errors at the job layer:

- Network errors, throttling, or temporary database outages: retry with backoff.
- Corrupted file, unsupported format, or malware: mark REJECTED, record the reason, and do not retry indefinitely.
- Malformed event schema or bucket outside allowlist: quarantine/DLQ for investigation.

Spring Cloud AWS 3.4 provides ExponentialBackoffErrorHandler to increase visibility timeout with each receive count. Configure backoff with jitter to avoid many messages retrying simultaneously. When the listener only persists database jobs, SQS retries mainly protect the ingestion step; file-processing retries are managed by job state.

## 8. Google Cloud — Cloud Storage Notifications and Pub/Sub

### 8.1. Event flow

~~~mermaid
flowchart LR
    GCS["Cloud Storage bucket"] -->|OBJECT_FINALIZE| TOPIC["Pub/Sub topic"]
    TOPIC --> SUB["Subscription"]
    SUB --> ADAPTER["PubSubInboundChannelAdapter"]
    ADAPTER --> INBOX["Inbox + job DB"]
    INBOX --> WORKER["Worker pool"]
    WORKER -->|Read exact generation| GCS
    SUB -. "Delivery attempts exceeded" .-> DLQ["Dead-letter topic"]
~~~

Cloud Storage notifications attach to a bucket and publish object events to a Pub/Sub topic. Each message contains attributes describing the event and JSON_API_V1 metadata payload if configured.

Important events:

| Event | Meaning |
| --- | --- |
| OBJECT_FINALIZE | A new object or new generation has been finalized |
| OBJECT_METADATA_UPDATE | Object metadata changed |
| OBJECT_DELETE | Object permanently deleted |
| OBJECT_ARCHIVE | Live generation became noncurrent when Object Versioning is enabled |

When an object with the same name is overwritten, GCS may emit OBJECT_FINALIZE for the new generation and OBJECT_ARCHIVE or OBJECT_DELETE for the old generation. Event ordering is not guaranteed; generation is the critical token for reading the right bytes.

### 8.2. Creating topic, subscription, and notification

Example:

~~~bash
gcloud services enable pubsub.googleapis.com \
  --project=training-platform-dev

gcloud pubsub topics create file-object-events \
  --project=training-platform-dev

gcloud pubsub subscriptions create file-object-events-sub \
  --topic=file-object-events \
  --project=training-platform-dev

gcloud storage buckets notifications create \
  gs://training-documents \
  --topic=projects/training-platform-dev/topics/file-object-events \
  --event-types=OBJECT_FINALIZE \
  --payload-format=json \
  --object-prefix=incoming/
~~~

The Cloud Storage service agent for the project owning the bucket needs roles/pubsub.publisher on the topic. The Spring Boot application needs roles/pubsub.subscriber on the subscription; the worker reading objects needs storage.objects.get at bucket scope.

Do not grant roles/storage.admin just to receive notifications. Separate the service agent publishing events from the runtime service account consuming events.

### 8.3. Dependencies and adapter

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_GCP_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-pubsub</artifactId>
    </dependency>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-storage</artifactId>
    </dependency>
</dependencies>
~~~

Project configuration:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: training-platform-dev
app:
  pubsub:
    file-events-subscription: file-object-events-sub
~~~

Use ADC and workload identity in production. Do not package a service account JSON key inside the container.

### 8.4. Receiving messages via Spring Integration

PubSubInboundChannelAdapter pulls messages from a subscription and converts them into Spring Messages. Example using MANUAL ACK to acknowledge only after the event is durably persisted:

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
    MessageChannel gcsFileEvents() {
        return new DirectChannel();
    }

    @Bean
    PubSubInboundChannelAdapter gcsFileEventAdapter(
            @Qualifier("gcsFileEvents") MessageChannel output,
            PubSubTemplate pubSubTemplate,
            @org.springframework.beans.factory.annotation.Value(
                    "${app.pubsub.file-events-subscription}") String subscription) {

        PubSubInboundChannelAdapter adapter =
                new PubSubInboundChannelAdapter(
                        pubSubTemplate,
                        subscription);

        adapter.setOutputChannel(output);
        adapter.setPayloadType(byte[].class);
        adapter.setAckMode(AckMode.MANUAL);
        return adapter;
    }
}
~~~

Message handling:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.cloud.spring.pubsub.support.BasicAcknowledgeablePubsubMessage;
import com.google.cloud.spring.pubsub.support.GcpPubSubHeaders;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class GcsFileEventHandler {

    private final ObjectMapper mapper;
    private final GcsEventNormalizer normalizer;
    private final EventInboxService inbox;

    public GcsFileEventHandler(
            ObjectMapper mapper,
            GcsEventNormalizer normalizer,
            EventInboxService inbox) {
        this.mapper = mapper;
        this.normalizer = normalizer;
        this.inbox = inbox;
    }

    @ServiceActivator(inputChannel = "gcsFileEvents")
    public void handle(Message<byte[]> message) throws Exception {
        BasicAcknowledgeablePubsubMessage original =
                message.getHeaders().get(
                        GcpPubSubHeaders.ORIGINAL_MESSAGE,
                        BasicAcknowledgeablePubsubMessage.class);

        try {
            JsonNode payload = mapper.readTree(message.getPayload());

            FileWorkItem item = normalizer.fromNotification(
                    message.getHeaders(),
                    payload);

            inbox.accept(item);
            original.ack();
        }
        catch (Exception ex) {
            original.nack();
            throw ex;
        }
    }
}
~~~

GcsEventNormalizer reads headers eventType, bucketId, objectId, objectGeneration, eventTime, and payloadFormat; the JSON payload contains object metadata. Only accept supported event types and buckets on the allowlist.

### 8.5. Reading the exact generation

Do not use only bucket and object name. If an event for generation 100 is delivered after the object has already been replaced by generation 101, reading the live object will process the wrong bytes.

Use the generation from the event:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public Blob readExactGeneration(
        Storage storage,
        String bucket,
        String objectKey,
        long generation) {

    return storage.get(
            BlobId.of(bucket, objectKey, generation));
}
~~~

If the old generation was deleted by lifecycle rules or versioning is disabled, the object may no longer be readable. Mark the event stale or handle per policy; do not silently substitute the newer live generation.

### 8.6. ACK deadline, retries, and dead-letter topics

Pub/Sub subscriptions have an ack deadline. The subscriber library can automatically extend the deadline during processing; however, avoid holding a message in a listener for tens of minutes when you can persist the job durably and ACK.

- Call ack() after the inbox/job commit succeeds.
- Call nack() or let the ack deadline expire when the event cannot be accepted.
- Configure an exponential backoff retry policy for transient errors.
- Configure a dead-letter topic on the subscription to retain unprocessable messages.
- Grant Publisher to the Pub/Sub service agent on the dead-letter topic and Subscriber to the DLQ consumer.

Maximum delivery attempts for a dead-letter topic range from 5–100 and are enforced on a best-effort basis; do not treat them as an exact counter. When replaying from the DLQ, keep the original event key so the inbox continues deduplicating.

Spring Integration's adapter supports AUTO, AUTO_ACK, and MANUAL. With MANUAL, the application must explicitly call ACK/NACK; never forget both, otherwise the message will be redelivered after the ack deadline.

## 9. Azure — Blob Storage, Event Grid, and Service Bus

### 9.1. Event flow

~~~mermaid
flowchart LR
    BLOB["Azure Blob Storage"] -->|BlobCreated| GRID["Event Grid"]
    GRID -->|Managed identity| SB["Service Bus queue"]
    SB --> LISTENER["@ServiceBusListener"]
    LISTENER --> INBOX["Inbox + job DB"]
    INBOX --> WORKER["Worker pool"]
    WORKER -->|Conditional read| BLOB
    GRID -. "Delivery failure" .-> EGDLQ["Event Grid dead-letter storage"]
    SB -. "Max delivery count" .-> SBDLQ["Service Bus DLQ"]
~~~

The storage account must be a type that supports Event Grid, such as StorageV2, BlockBlobStorage, or BlobStorage. The Microsoft.Storage.BlobCreated event is emitted when a blob is created or replaced completely. With Data Lake Storage Gen2, if you only want to process once a file is fully committed, filter on the FlushWithClose API corresponding to the upload pattern.

Event Grid can route events directly into a Service Bus queue to act as a buffering layer. There are two distinct dead-letter layers:

- **Event Grid dead-letter:** events that could not be delivered to the queue/endpoint.
- **Service Bus DLQ:** messages that entered the queue but workers repeatedly failed to process/settle.

### 9.2. Event schema and filters

Event Grid schemas typically arrive as a JSON array where each element includes fields:

| Field | Meaning |
| --- | --- |
| id | Event ID |
| eventType | For example Microsoft.Storage.BlobCreated |
| subject | Container/blob path |
| eventTime | Event timestamp |
| data.url | Blob URL |
| data.eTag | ETag at event time |
| data.sequencer | Logical sequence for the same blob |
| data.contentLength | Object size |

Use subject filters to receive only blobs under the incoming/ container/prefix and filter on event type Microsoft.Storage.BlobCreated. Exclude events from the output prefix processed/ to prevent event loops.

### 9.3. Routing Event Grid to Service Bus

Create a Service Bus queue, then create an Event Grid subscription with endpoint type Service Bus queue. Enable managed identity for Event Grid and assign the Azure Service Bus Data Sender role at queue or namespace scope. The worker identity needs Azure Service Bus Data Receiver on the queue and Storage Blob Data Reader on the container holding files.

Illustrative CLI example using Azure resource IDs:

~~~bash
az eventgrid event-subscription create \
  --name file-created-to-servicebus \
  --source-resource-id "$EVENT_GRID_SYSTEM_TOPIC_RESOURCE_ID" \
  --delivery-identity-endpoint-type servicebusqueue \
  --delivery-identity systemassigned \
  --delivery-identity-endpoint "$SERVICE_BUS_QUEUE_RESOURCE_ID"
~~~

This example assumes you have created an Event Grid system topic for the Storage account and enabled system-assigned identity on the system topic. Assign Azure Service Bus Data Sender to that identity at queue/namespace scope before creating the subscription. Parameter names and identity options depend on the Event Grid topic/subscription type and API version; verify against the Azure CLI command reference you are using. If managed identity is not enabled for delivery, Event Grid may use another configured authentication mechanism; production should prefer Microsoft Entra and RBAC.

### 9.4. Spring Cloud Azure dependencies and configuration

Spring Cloud Azure supports Spring Messaging for Service Bus:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_AZURE_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-messaging-azure-servicebus</artifactId>
    </dependency>
</dependencies>
~~~

Namespace and entity type configuration:

~~~yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        # Only specify client-id if using a user-assigned managed identity.
        # client-id: ${AZURE_CLIENT_ID}
      servicebus:
        namespace: YOUR_SERVICE_BUS_NAMESPACE
        entity-type: queue
app:
  servicebus:
    file-events-queue: file-events
~~~

Use managed identity or DefaultAzureCredential instead of a connection string containing a SAS key. Newer Spring Cloud Azure versions auto-enable messaging infrastructure; older versions may require declaring EnableAzureMessaging per the corresponding documentation.

### 9.5. Listener for Event Grid messages

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.azure.spring.messaging.servicebus.annotation.ServiceBusListener;
import org.springframework.stereotype.Component;

@Component
public class AzureFileEventListener {

    private final ObjectMapper mapper;
    private final AzureBlobEventNormalizer normalizer;
    private final EventInboxService inbox;

    public AzureFileEventListener(
            ObjectMapper mapper,
            AzureBlobEventNormalizer normalizer,
            EventInboxService inbox) {
        this.mapper = mapper;
        this.normalizer = normalizer;
        this.inbox = inbox;
    }

    @ServiceBusListener(destination = "file-events")
    public void receive(String body) throws Exception {
        JsonNode events = mapper.readTree(body);

        if (events.isArray()) {
            for (JsonNode event : events) {
                FileWorkItem item = normalizer.fromEventGrid(event);
                inbox.accept(item);
            }
        }
        else {
            inbox.accept(normalizer.fromEventGrid(events));
        }
    }
}
~~~

By default Event Grid typically delivers a single event inside an array, though subscriptions can enable batching. The listener should handle both a single event object and an array of multiple events. If one item fails, the batch message may be redelivered; the inbox unique key makes already-committed events no-ops on redelivery.

In Service Bus Peek-Lock mode, a message is locked upon receipt and only deleted after completion. If the listener fails or the lock expires, the broker can redeliver it. Do not swallow exceptions before the listener container completes settlement. Check the acknowledgement/settlement mode of the Spring Cloud Azure version you are using.

### 9.6. Using ETag and sequencer

Event Grid does not guarantee ordering. For the same blob, sequencer is a string representing logical order; strings can be compared ordinally to determine which event is newer. ETag is the version token at the time of the event.

When the worker reads the blob, use an If-Match condition to ensure the contents still match the ETag described in the event:

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.options.BlobInputStreamOptions;
import com.azure.storage.blob.models.BlobRequestConditions;
import java.io.InputStream;

public InputStream openBlobAtExpectedEtag(
        BlobClient blobClient,
        String eventETag) {

    BlobInputStreamOptions options = new BlobInputStreamOptions()
            .setRequestConditions(
                    new BlobRequestConditions().setIfMatch(eventETag));

    return blobClient.openInputStream(options);
}
~~~

If the blob has been replaced, Storage returns a precondition error instead of silently letting the worker read newer bytes. If blob versioning is enabled and older versions must be processed, store the version ID in business metadata or look up the appropriate version; basic Event Grid BlobCreated payloads provide ETag and sequencer, so do not assume version ID is always present in every schema.

### 9.7. Retries, lock renewal, and DLQ

Event Grid delivery is at-least-once and does not guarantee ordering. Its default retry policy can retry up to 30 times or 24 hours. Some endpoint types treat configuration errors such as 400/403 as non-retryable; if no dead-letter destination is configured, events can be dropped. Check the retry table for your exact endpoint type and configure an Event Grid dead-letter destination to retain undeliverable events.

Service Bus has its own Peek-Lock and DLQ:

- Default lock duration is 1 minute; configurable higher, up to 5 minutes.
- Workers taking longer than the lock duration must renew the lock.
- When a message is abandoned or its lock expires repeatedly, delivery count increases.
- Default max delivery count is 10; exceeding it moves the message to the Service Bus DLQ.
- Complete deletes the message; Abandon unlocks it for redelivery; DeadLetter moves the message to the DLQ.

If the listener only writes the job to the database and finishes quickly, lock expiration is rarely an issue. If processing files directly inside the listener, configure auto lock renewal and sensible processing durations.

## 10. Handling Duplicates and Out-of-Order Events

### 10.1. At-least-once is normal

All three providers can redeliver events:

- S3 notifications are at-least-once, and can be duplicated or out-of-order.
- GCS notifications are at-least-once; the same event may be delivered multiple times with different Pub/Sub message IDs.
- Event Grid is at-least-once; duplicates and out-of-order deliveries can occur.

This is not a rare error to ignore. Workers must be designed to be idempotent from day one.

### 10.2. Inbox unique constraint

A single transaction should persist both the inbox entry and the job:

~~~sql
INSERT INTO storage_event_inbox (
    event_key, provider, event_type, bucket_name,
    object_key, version_token, e_tag, sequencer,
    occurred_at, received_at, status
)
VALUES (
    :eventKey, :provider, :eventType, :bucket,
    :objectKey, :versionToken, :eTag, :sequencer,
    :occurredAt, now(), 'RECEIVED'
)
ON CONFLICT (event_key) DO NOTHING;
~~~

Only create the job when the new insert succeeds. If the event already exists, the listener ACKs the message because the corresponding work was already accepted earlier.

### 10.3. Do not rely on eventTime alone for ordering

Timestamps can be delayed, vary in precision, and events can arrive out of order. Use the object's version token:

- S3: versionId if versioning is enabled; otherwise compare sequencer for the same object key. Sequencers are hex strings of varying length; normalize length before comparing values.
- GCS: generation for object contents; metageneration for metadata. Never regress database state to an older generation/metageneration.
- Azure: sequencer to compare event order for the same blob; ETag to verify the object is still the expected version.

Never compare sequencers across two different objects.

### 10.4. Idempotent side effects

If the pipeline generates a thumbnail, the output key should be derived deterministically from the document ID and source version:

~~~text
processed/{documentId}/{sourceVersion}/thumbnail.webp
~~~

If a worker retries, the output for the same source version can be overwritten deterministically or guarded with a create-only precondition. Do not generate a random output key on every retry because it leaves duplicate files behind.

When calling downstream APIs, pass an idempotency key if the service supports it. When updating the database, use unique constraints or optimistic locking. Never assume broker ACK and database commit belong to a single distributed transaction.

## 11. Retries, Poison Messages, and Dead-Lettering

### 11.1. Classifying failures

| Failure | Examples | Handling |
| --- | --- | --- |
| Transient infrastructure | Timeout, 429, 5xx, database unavailable | Retry with exponential backoff and jitter |
| Permission/config | 403 due to missing IAM/RBAC | Alert and fix permissions; do not retry indefinitely |
| Stale object | Version no longer exists or ETag mismatch | Mark stale, reconcile, or handle per policy |
| Invalid event | Missing bucket/key/version/event type | Quarantine or DLQ |
| Invalid file | Wrong format, oversized, malware | Mark REJECTED; store reason and audit |
| Duplicate | Event key already ingested | ACK/complete after confirming inbox entry |
| Permanent business failure | Document cancelled or invalid tenant | Mark rejected/cancelled; do not retry |

### 11.2. Separating broker retries from job retries

If the listener writes the job to the database and ACKs, broker retries only protect the ingestion step. The worker job runner manages file-processing retries using attempt_count, next_attempt_at, and RETRY_WAIT state.

If the listener processes files directly, broker retries depend on:

- SQS visibility timeout and redrive policy.
- Pub/Sub ack deadline, nack, and subscription retry policy.
- Service Bus lock duration, abandon, and max delivery count.

Do not configure two layers of retries without bounding the total attempts. For example, 5 broker retries multiplied by 5 job retries can result in 25 attempts on the same file.

### 11.3. Dead-letter queues are for investigation

DLQs need dashboards/alerts and a replay procedure:

1. Detect messages entering the DLQ.
2. Inspect event metadata and error category.
3. Determine whether the failure is transient, permission-related, or payload-related.
4. Fix the root cause.
5. Check the idempotency key and job state.
6. Perform controlled replay.
7. Audit who replayed, when, and how many times.

Do not automatically replay the entire DLQ in a tight loop. A single poison message can cause workers to fail continuously and waste resources.

## 12. Concurrency, Backpressure, and Scaling Workers

### 12.1. Tuning concurrency

Worker concurrency is constrained by multiple resources:

- CPU for OCR, image processing, and virus scanning.
- Memory for parsers or buffered files.
- Database connection count.
- Storage request rate and throughput.
- OCR/AI service rate limits.
- Network bandwidth and disk I/O.

Do not set maxConcurrentMessages to CPU count times an arbitrary multiplier while ignoring downstream limits. Measure p95 processing time and resource usage before increasing concurrency.

### 12.2. AWS SQS

Spring Cloud AWS @SqsListener supports maxConcurrentMessages, maxMessagesPerPoll, pollTimeoutSeconds, and messageVisibilitySeconds. maxConcurrentMessages defaults to 10. Start small, increase gradually, and watch queue backlog.

~~~java
@SqsListener(
        value = "${app.queue.file-events}",
        maxConcurrentMessages = "8",
        messageVisibilitySeconds = "120")
public void receive(String body) throws Exception {
    // Normalize and persist jobs.
}
~~~

When the listener only persists jobs into the database, 120 seconds visibility is an illustrative example; choose a value aligned with parse/commit time and retries. When processing files directly, visibility must match processing duration and be extended if exceeded.

### 12.3. Google Pub/Sub

The streaming subscriber manages flow control and can auto-extend the ack deadline within configured bounds. Tune maximum outstanding messages and the worker executor according to capacity. For long processing, persist the job and ACK; avoid letting the subscriber pull too many messages while workers have no free slots.

### 12.4. Azure Service Bus

Service Bus listeners can configure concurrency and client processor options. Lock renewal must cover the processing time if listeners perform long work. Excessive prefetch can cause messages to hold locks before workers even start processing them, increasing the likelihood of lock expiration.

### 12.5. Backpressure by queue depth

Signals to guide scaling include:

- Queue depth / active message count.
- Age of oldest message.
- Processing time p95/p99.
- Worker CPU/memory.
- Downstream 429/5xx rates.
- Database connection pool utilization.

Scale out when backlog grows and workers still have headroom. If a downstream service is rate-limiting requests, scaling out too aggressively can worsen errors; reducing concurrency and backing off is better.

## 13. Preventing Event Loops and Unwanted Events

A worker may write outputs to the same bucket/container. If notifications filter across the entire bucket, new outputs generate new events and workers process their own outputs again.

How to prevent this:

- Upload inputs to incoming/.
- Write outputs to processed/.
- Filter events strictly to incoming/.
- Use a separate output bucket for large workflows.
- Check object metadata markers to skip worker-generated files.

Additionally, only subscribe to event types supported by the workflow. For example, OBJECT_METADATA_UPDATE should not re-trigger OCR if metadata does not affect contents. Delete events can update search indices or cancel pending jobs, but should never attempt to download a deleted object.

## 14. Security and IAM

### 14.1. Separating principals by role

| Provider | Event publisher/router | Worker consumer | Object reader |
| --- | --- | --- | --- |
| AWS | S3 service principal or EventBridge role sending to SQS | IAM role with sqs:ReceiveMessage, sqs:DeleteMessage, sqs:GetQueueAttributes | s3:GetObject on the processing prefix |
| GCP | Cloud Storage service agent with roles/pubsub.publisher | Service account with roles/pubsub.subscriber on subscription | storage.objects.get on the bucket |
| Azure | Event Grid managed identity with Azure Service Bus Data Sender | Workload identity with Azure Service Bus Data Receiver | Storage Blob Data Reader at container scope |

Separate the Event Grid principal sending to the queue from the worker reading the queue. Do not grant storage or broker administration permissions to workers unnecessarily.

### 14.2. Validating event sources

Do not trust bucket/container/object URLs inside an event simply because the message came from a queue:

- Allowlist account/project/bucket/container.
- Validate event type.
- Validate object prefix.
- Never allow events to specify arbitrary hosts or URLs.
- Build clients from trusted configuration rather than initializing endpoints from payloads.
- Validate object keys before using them in local paths.
- Never execute commands or fetch URLs driven by untrusted metadata.

### 14.3. Protecting files and outputs

- Keep buckets/containers private.
- Use workload identities instead of long-lived keys.
- Scan files before publishing results.
- Enforce file size, content type, and tenant quotas.
- Never log file bytes, signed URLs, SAS tokens, or access tokens.
- Store processed outputs in a prefix/bucket with dedicated policies when data has been transformed.
- Use encryption at rest and TLS per organizational policy.

## 15. Observability and Operations

### 15.1. Metrics

Track at minimum:

| Metric | Purpose |
| --- | --- |
| Events received | Measure incoming event rate |
| Events deduplicated | Detect duplicate deliveries |
| Jobs pending/running/retry/dead | Observe the state machine |
| Queue depth | Measure backlog |
| Age of oldest message | Detect workers falling behind |
| Processing latency p50/p95/p99 | Measure pipeline duration |
| Retry count | Detect recurring errors |
| DLQ count/rate | Detect poison messages |
| Object read errors | Track 403/404/412/429/5xx |
| Stale version count | Detect old events or overwritten objects |
| Worker lease expired | Detect crashed processes or overly long processing |

### 15.2. Structured logging

Log fields:

- eventKey, jobId, correlationId.
- Provider, bucket/container, protected object key.
- Version ID/generation/ETag/sequencer when applicable.
- Event type and event time.
- Worker ID, attempt count, and job state.
- Processing duration, bytes read, and outcome.

Never log sensitive payloads, file contents, access tokens, signed URLs, or full messages that may contain untrusted metadata.

### 15.3. Tracing

Propagate correlation IDs from the upload API through events, queues, jobs, and outputs. Brokers have their own message IDs; record message IDs as observability metadata rather than replacing the event key.

Separate spans for steps: receive-event, persist-job, read-object, scan, transform, write-output, persist-result. This helps pinpoint whether bottlenecks lie in storage, parsing, or downstream services.

## 16. Integration Testing

### 16.1. Unit tests

Verify:

- S3 parser properly decodes URL-encoded object keys.
- GCS parser reads attributes and JSON payloads.
- Event Grid parser supports multi-event arrays.
- Unsupported event types are ignored or quarantined.
- Duplicate event keys do not create a second job.
- Older generation/ETag/sequencer values do not regress state.
- Workers read the exact version token.
- Transient failures transition to RETRY_WAIT.
- Invalid files transition to REJECTED.
- Worker outputs do not trigger event loops.

### 16.2. Integration tests with emulators

LocalStack for S3/SQS and Azurite for Blob Storage can test storage API integration. The Pub/Sub emulator tests subscribers, message payloads, and ACK/NACK. Emulators do not fully prove real cloud event notification services or production IAM policies.

Test adapters by publishing synthetic event messages into the queue/topic. Test workers using test object storage or mock clients supporting version/ETag conditions.

### 16.3. End-to-end tests on a cloud test account

1. Create a private bucket/container and incoming/ prefix.
2. Create broker queues/topics/subscriptions and DLQs.
3. Grant IAM/RBAC to the event source and workers.
4. Configure notifications/event subscriptions filtered by prefix.
5. Upload a small file.
6. Verify the event arrives in the broker.
7. Verify the Spring listener ingests the job and ACKs/completes.
8. Verify the worker reads the exact version and writes output.
9. Re-upload to the same object key and verify the new event does not duplicate side effects.
10. Simulate a transient error and verify retries.
11. Send a malformed event schema or invalid file and verify quarantine/DLQ.
12. Restart a worker mid-processing and verify lease/redelivery recovers the job.
13. Verify events on the output prefix do not re-enter the pipeline.
14. Inspect queue backlog and metrics.
15. Clean up queues, DLQs, notification configs, and test objects.

### 16.4. Failure matrix

| Scenario | Expected outcome |
| --- | --- |
| Event delivered twice | One event key, one logical job |
| Worker crashes after claim | Lease expires, another worker reclaims |
| Worker crashes after writing output | Retry does not produce duplicate outputs |
| Old event arrives after newer event | Version state does not regress |
| Object overwritten | Exact version token read or marked stale |
| Broker unavailable | Storage events buffered/retried per provider; backlog observed |
| Worker loses object read permission | Job retries up to limit and triggers IAM alert |
| DLQ grows | Alert fires and controlled replay procedure runs |
| Downstream rate-limit | Backoff/jitter, reduce concurrency |
| Output written to input prefix | Test catches event loop |

## 17. Comparing the Three Providers

| Aspect | AWS | Google Cloud | Azure |
| --- | --- | --- | --- |
| Object event source | S3 Event Notifications / EventBridge | Cloud Storage notifications | Blob Storage events |
| Durable broker | SQS | Pub/Sub | Service Bus |
| Spring consumer | @SqsListener | PubSubInboundChannelAdapter | @ServiceBusListener |
| Event envelope | S3 Records or EventBridge event | Pub/Sub attributes + JSON metadata payload | Event Grid event array / CloudEvents |
| Object version guard | Version ID, ETag, sequencer | Generation, metageneration | ETag, sequencer, blob versioning if enabled |
| Delivery | At-least-once, unordered | At-least-once, unordered | At-least-once, unordered |
| Retry | Visibility timeout, redrive policy | Ack deadline, retry policy | Event Grid retry, Service Bus lock/abandon |
| Dead-letter | SQS DLQ | Pub/Sub dead-letter topic | Event Grid dead-letter storage and Service Bus DLQ |
| IAM | SQS receive/delete + S3 get | Pub/Sub subscriber + Storage get | Service Bus Data Receiver + Blob Data Reader |

Key differences lie in event envelopes, version tokens, and settlement semantics:

- SQS ACK actually deletes the message from the queue.
- Pub/Sub ACK tells the broker the subscriber finished processing the message.
- Service Bus Complete confirms the message was processed and removes it from the queue; Abandon unlocks it for redelivery.

Do not force these operations into a generic ACK function without understanding adapter semantics. Keep the business contract shared and implement settlement details inside each provider adapter.

## 18. Comprehensive Hands-On Exercise

**Context:** Build a document processing service that receives PDFs under the incoming/ prefix, scans for viruses, extracts metadata, and generates thumbnails. The upload API returns immediately once storage confirms the upload; processing runs asynchronously and the frontend can poll status.

### Task A — Design the event pipeline

1. Choose AWS S3/SQS, GCS/Pub/Sub, or Azure Blob/Event Grid/Service Bus.
2. Diagram storage event → broker → Spring listener → inbox/job DB → worker.
3. Define FileWorkItem and the event key.
4. Explain why queue messages carry object references rather than file bytes.

### Task B — Configure the provider

1. Create a private bucket/container and incoming/ prefix.
2. Create queues/topics/subscriptions and DLQs.
3. Configure event filters by prefix and event type.
4. Grant publish/send permissions to the event source.
5. Grant consume and object read permissions to the workload identity.

### Task C — Write the Spring Boot adapter

1. Add the provider BOM and starters.
2. Write the event envelope parser.
3. Write the listener receiving broker messages.
4. Normalize events into FileWorkItem.
5. Persist inbox/job inside a transaction.
6. ACK/complete after the job commits.

### Task D — Write the worker

1. Claim jobs using a lease.
2. Read objects by version ID/generation/ETag.
3. Verify size, content type, and file signature.
4. Run virus scanning.
5. Extract metadata and generate thumbnails.
6. Write output to the processed/ prefix.
7. Update the database and mark the job COMPLETED.

### Task E — Retries and observability

- Test duplicate and out-of-order events.
- Test worker crashes before and after output writes.
- Test objects overwritten before worker reads.
- Test broker visibility/ack deadline/lock expiry.
- Test retries and DLQ.
- Monitor queue depth, oldest message age, and processing latency.
- Compare settlement semantics across the three providers.

**Acceptance criteria:** The system ingests object events via a durable broker; the Spring Boot listener creates idempotent jobs; workers process files independently; exact object versions are read; transient errors retry with bounds; invalid files are quarantined/DLQed; and integration tests verify the entire pipeline.

## 19. Key Takeaways

- Storage events describe object changes; broker messages are deliveries; processing jobs are business requests.
- Queues carry object pointers and small metadata, never file bytes.
- AWS uses S3 Event Notifications/EventBridge with SQS; GCS uses Cloud Storage notifications with Pub/Sub; Azure uses Event Grid with Service Bus.
- S3 direct notifications do not support SQS FIFO; use EventBridge when a FIFO target is needed.
- Spring Boot provides @SqsListener, PubSubInboundChannelAdapter, and @ServiceBusListener for each broker.
- At-least-once delivery is normal; always design an inbox and idempotency.
- Use version ID/generation/ETag/sequencer to avoid processing wrong versions or stale events.
- ACK/complete only after the job is durably persisted or finished; never ACK before commit.
- Visibility timeouts, ack deadlines, and message locks must align with processing times.
- Retries need backoff, jitter, and limits; DLQs need alerts, investigation, and controlled replay.
- Workers need concurrency/backpressure tuned to storage, database, and downstream capacity.
- Separate output prefixes from input prefixes to avoid event loops.
- Do not trust bucket/object URLs from events; validate the source, resource scope, and object key.
- Monitor backlog, oldest message age, processing latency, retries, DLQs, and stale-version counts.

### References

- [Amazon S3 Event Notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventNotifications.html)
- [S3 event notification types and destinations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-how-to-event-types-and-destinations.html)
- [Using dead-letter queues in Amazon SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [Spring Cloud AWS — SQS integration and listeners](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html)
- [Spring Cloud AWS — SQS acknowledgement, error handling and backpressure](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html)
- [Cloud Storage Pub/Sub notifications](https://docs.cloud.google.com/storage/docs/pubsub-notifications)
- [Spring Framework on Google Cloud — Spring Integration and Pub/Sub](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/spring-integration.html)
- [Pub/Sub subscription retry policy](https://docs.cloud.google.com/pubsub/docs/subscription-retry-policy)
- [Pub/Sub dead-letter topics](https://docs.cloud.google.com/pubsub/docs/dead-letter-topics)
- [Pub/Sub subscription properties](https://docs.cloud.google.com/pubsub/docs/subscription-properties)
- [Azure Blob Storage as an Event Grid source](https://learn.microsoft.com/en-us/azure/event-grid/event-schema-blob-storage)
- [Reacting to Azure Blob storage events](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blob-event-overview)
- [Event Grid delivery and retry](https://learn.microsoft.com/en-us/azure/event-grid/delivery-and-retry)
- [Configure Service Bus as an Event Grid handler](https://learn.microsoft.com/en-us/azure/event-grid/handler-service-bus)
- [Enable managed identities for Event Grid delivery](https://learn.microsoft.com/en-us/azure/event-grid/managed-service-identity)
- [Spring Cloud Azure — Spring Messaging for Service Bus](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/spring-messaging-service-bus-support)
- [Azure Service Bus message transfers, locks and settlement](https://learn.microsoft.com/en-us/azure/service-bus-messaging/message-transfers-locks-settlement)
- [Azure Service Bus dead-letter queues](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-dead-letter-queues)
- [Azure Blob Java — BlobInputStreamOptions](https://learn.microsoft.com/en-us/java/api/com.azure.storage.blob.options.blobinputstreamoptions?view=azure-java-stable)
- [Azure Blob Java — BlobRequestConditions](https://learn.microsoft.com/en-us/java/api/com.azure.storage.blob.models.blobrequestconditions?view=azure-java-stable)
