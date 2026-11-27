# Amazon S3: S3 events and coordinating file processing via queues

## Learning objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, Spring Boot applications integrate with managed services across AWS, Azure, and Google Cloud to handle storage, messaging, data, identities, and permissions. When users upload documents to **Amazon S3**, the application frequently needs to continue with virus scanning, thumbnail generation, text extraction, format conversion, or business state updates. If the upload API had to wait for all of this work to finish, response times would be long and processing would be hard to scale.

S3 can emit **event notifications** when an object is created, deleted, or modified under supported event types. Events can be delivered to **Amazon SQS**, **Amazon SNS**, **AWS Lambda**, or **Amazon EventBridge**. A Spring Boot consumer reads messages from a queue, retrieves the corresponding object from S3, and processes it in a retryable workflow.

This lesson focuses on the **S3 → SQS → Spring Boot worker** pattern, while comparing SNS/EventBridge and explaining event delivery, duplicates/out-of-order arrivals, idempotency, dead-letter queues, and testing.

After this lesson, you will be able to:

1. Configure S3 event notifications by event type, prefix, and suffix.
2. Grant a queue policy so S3 is permitted to send messages to SQS.
3. Use a Spring Cloud AWS SQS listener to receive and parse S3 events.
4. Download the exact object version, process the file, and update business state.
5. Design a consumer resilient to duplicates, out-of-order events, retries, and processing failures.
6. Configure visibility timeouts, DLQs, IAM permissions, and queue monitoring.
7. Compare SQS, SNS, and EventBridge when building file-processing pipelines.

> **Scope:** Examples use modern Spring Cloud AWS (`io.awspring.cloud` namespace) and AWS SDK for Java v2 (`software.amazon.awssdk` namespace). Choose library versions compatible with your project's Spring Boot version. Buckets, queues, account IDs, and Regions in this lesson are illustrative.

## 1. Why event-driven file processing?

Suppose a user uploads a PDF to S3. After receiving the file, the system needs to:

- Validate file type and size.
- Scan for malware or quarantine the file.
- Extract text, perform OCR, or extract metadata.
- Generate previews/thumbnails.
- Save results and processing status into the database.
- Notify the user upon completion.

If the upload API invokes every step synchronously, the HTTP request can take many seconds or minutes. If OCR or the scanner fails, the user might have to re-upload even though the file was already saved.

An event-driven architecture decouples **file ingestion** from **file processing**:

~~~mermaid
flowchart LR
    U["Browser / mobile"] -->|"Upload"| API["Spring Boot API"]
    API -->|"PUT object"| S3["S3 bucket: incoming/"]
    API -->|"PENDING"| DB["Business database"]
    S3 -->|"ObjectCreated event"| Q["SQS standard queue"]
    Q --> W["Spring Boot worker"]
    W -->|"GET object"| S3
    W -->|"Scan / OCR / thumbnail"| P["Processing services"]
    W -->|"READY / FAILED"| DB
~~~

The upload API can return early with `PENDING` status. Workers process asynchronously and update `READY` or `FAILED`. SQS buffers messages while workers are busy, decoupling upload throughput from processing speed.

### 1.1. An event is a notification, not the file contents

S3 event notifications carry **reference information** such as:

- Bucket and object key.
- Event type (for example, object created or deleted).
- Version ID if versioning is enabled on the bucket and the event includes this field.
- Size, ETag, and sequencer on supported events.
- Related request/response metadata.

The message **does not embed all bytes of the file**. The consumer uses bucket/key/version ID to call S3 GET. This avoids stuffing large files into SQS messages and lets workers stream content cleanly.

### 1.2. Typical processing flow

~~~mermaid
sequenceDiagram
    actor User as User
    participant API as Spring Boot API
    participant DB as Database
    participant S3 as Amazon S3
    participant Q as Amazon SQS
    participant W as File worker

    User->>API: Upload document
    API->>DB: Create PENDING record
    API->>S3: PUT incoming/{tenant}/{uuid}
    S3-->>API: PUT succeeded
    API-->>User: 202 Accepted + documentId
    S3->>Q: ObjectCreated notification
    Q-->>W: Message with bucket/key/version
    W->>DB: Claim job/idempotency
    W->>S3: GET object
    S3-->>W: Stream content
    W->>W: Scan, OCR, generate result
    W->>DB: Update READY
    W-->>Q: Acknowledge message
~~~

In real systems, handle cases where the database writes `PENDING` successfully while S3 PUT fails, or PUT succeeds while the database update fails. S3 and the database do not share an ACID transaction; the design requires explicit states, retries, and reconciliation.

## 2. S3 event types and filter configuration

### 2.1. Common event types

S3 event notifications emit event families, most commonly:

| Event group | Example event name | Use case |
| --- | --- | --- |
| Object created | `s3:ObjectCreated:Put` | Process after single PUT |
| Object created | `s3:ObjectCreated:Post` | Process after browser form POST |
| Object created | `s3:ObjectCreated:Copy` | Process a copied object |
| Object created | `s3:ObjectCreated:CompleteMultipartUpload` | Process after multipart upload completes |
| Object removed | `s3:ObjectRemoved:Delete` | Sync state after deletion |
| Object removed | `s3:ObjectRemoved:DeleteMarkerCreated` | Track delete markers in versioned buckets |
| Restore | `s3:ObjectRestore:Completed` | Process archived object once restore finishes |
| Tagging | `s3:ObjectTagging:Put` | React to tag changes if business logic requires |

`s3:ObjectCreated:*` subscribes to the whole object-creation group. Subscribe only to events you actually need; if a worker only processes newly uploaded files, do not subscribe to delete/tagging/restore events unnecessarily.

Event names inside the payload like `ObjectCreated:Put` typically **omit the `s3:` prefix**. The `s3:` prefix is used in notification configuration.

### 2.2. Filtering by prefix and suffix

If a bucket has multiple data areas:

~~~text
incoming/          # Newly uploaded files awaiting processing
processed/         # Processed results
thumbnails/        # Preview images
archive/           # Archived copies
~~~

To have workers process only new PDFs under `incoming/`, configure filters:

- Prefix: `incoming/`
- Suffix: `.pdf`

Filters ensure S3 sends only matching notifications to the destination. Prefix/suffix filters use **exact substring matching**, not regex or globs. Do not put `*` wildcards in filter values. Overlapping filter rules for the same event can be rejected during configuration; keep prefixes/suffixes unambiguous.

**Important:** if a worker writes thumbnails under the same subscribed prefix, writing a thumbnail fires a new event and triggers the worker in a loop. Write outputs to a separate prefix, or scope the filter strictly to the upload-intake area.

### 2.3. Test events and event payloads

When configuring notifications, S3 may send a **test event** to verify the destination. The test event has an `Event` field such as `s3:TestEvent` and lacks the `Records` structure of object events. Consumers must not assume every message contains `Records`.

An event notification can also carry multiple records inside the `Records` array. Consumers should iterate through all records rather than assuming one message always corresponds to one object.

## 3. Choosing SQS, SNS, or EventBridge?

S3 can send events to multiple destination types. The choice depends on how the system distributes work.

| Destination | Model | Best fit when | Notes |
| --- | --- | --- | --- |
| **SQS standard** | Queue storing messages for consumers | A pool of workers pulls jobs at its own capacity | At-least-once; may duplicate and does not guarantee ordering |
| **SNS** | Publish/subscribe fan-out | One event must reach multiple independent subscribers | Each subscriber needs its own endpoint/queue; per-subscription retries and filters |
| **EventBridge** | Event bus and routing rules | Need filtering on event details, multiple targets, broader event-driven integration | EventBridge-specific schema and target retry/DLQ configuration |
| **Lambda** | Invoke function per event | Small, short-lived serverless processing | Requires managing concurrency, retries, and execution duration |

### 3.1. S3 → SQS standard

This fits file-processing workers well:

- S3 sends notifications to the queue.
- Multiple workers can poll the same queue to scale processing.
- Messages stay in the queue until received by a consumer.
- SQS visibility timeout temporarily hides a message while a worker processes it.
- Upon success, the consumer acknowledges/deletes the message; on failure, the message reappears after the visibility timeout.

S3 event notifications directly support **SQS standard queues**. Do not configure S3 to deliver directly to an **SQS FIFO queue**. If business logic requires FIFO ordering, route events through **EventBridge** to a FIFO queue via an appropriate target configuration; you still need idempotency and message grouping/ordering design per object.

### 3.2. S3 → SNS → multiple SQS queues

When the same file triggers multiple independent workflows:

~~~mermaid
flowchart LR
    S3["S3 ObjectCreated"] --> SNS["SNS topic"]
    SNS --> Q1["SQS: virus-scan"]
    SNS --> Q2["SQS: OCR"]
    SNS --> Q3["SQS: audit"]
    Q1 --> W1["Scanner worker"]
    Q2 --> W2["OCR worker"]
    Q3 --> W3["Audit worker"]
~~~

SNS fan-out lets each consumer run at its own pace with its own retry policy. Each subscriber queue can have its own DLQ so OCR failures never stall virus scanning or auditing. When SNS delivers to SQS, the default body can be an **SNS envelope** containing the S3 payload inside a `Message` field; enabling raw message delivery puts the S3 payload directly as the body. The consumer must know which subscription mode is configured and parse that exact format rather than guessing blindly.

### 3.3. S3 → EventBridge

Enable EventBridge on the bucket when you need flexible rule routing, diverse target types, or cross-service integration. EventBridge events use a **different schema** from S3 notification envelopes delivered directly to SQS/SNS. For instance, event details place bucket/key under `detail.bucket.name` and `detail.object.key`, rather than `Records[].s3.bucket.name`.

**Do not share a single parser for raw S3 notifications and EventBridge payloads without a normalizing adapter.** Build two adapters that translate both into one internal domain event such as `ObjectCreatedEvent`.

## 4. Configuring S3 to send events to SQS

### 4.1. Creating the queue and DLQ

Create an SQS standard queue for work items and a dead-letter queue:

~~~text
file-processing-dlq
file-processing-queue
  └── redrive policy → file-processing-dlq
~~~

The main queue receives new events. If a message is received multiple times and keeps failing, the redrive policy moves it to the DLQ after the configured maximum receives. The DLQ lets you inspect payloads and errors and perform redrives once the root cause is fixed.

### 4.2. Queue policy allowing S3 to send messages

S3 must be permitted to call `sqs:SendMessage` on the queue. Example resource policy for the queue:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowS3BucketNotifications",
      "Effect": "Allow",
      "Principal": {
        "Service": "s3.amazonaws.com"
      },
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:file-processing-queue",
      "Condition": {
        "ArnLike": {
          "aws:SourceArn": "arn:aws:s3:::training-private-files"
        },
        "StringEquals": {
          "aws:SourceAccount": "111122223333"
        }
      }
    }
  ]
}
~~~

Replace Region, account ID, queue ARN, and bucket ARN with your environment's values. The `aws:SourceArn` and `aws:SourceAccount` conditions restrict which bucket can send messages, mitigating confused-deputy risks.

The bucket and SQS queue must reside in the **same AWS Region** for direct notification configuration. If the queue uses SSE-KMS with a customer-managed key, also check the KMS key policy so S3 is permitted to encrypt messages under the queue's configuration.

### 4.3. Notification configuration

Example configuration sending ObjectCreated events under prefix `incoming/` and suffix `.pdf` to the queue:

~~~json
{
  "QueueConfigurations": [
    {
      "Id": "incoming-pdf-created",
      "QueueArn": "arn:aws:sqs:ap-southeast-1:111122223333:file-processing-queue",
      "Events": [
        "s3:ObjectCreated:*"
      ],
      "Filter": {
        "Key": {
          "FilterRules": [
            {
              "Name": "prefix",
              "Value": "incoming/"
            },
            {
              "Name": "suffix",
              "Value": ".pdf"
            }
          ]
        }
      }
    }
  ]
}
~~~

Save this configuration as a JSON file and apply via AWS CLI in a sandbox:

~~~bash
aws s3api put-bucket-notification-configuration \
  --bucket training-private-files \
  --notification-configuration file://notification.json
~~~

`put-bucket-notification-configuration` replaces the bucket's **entire notification configuration** with the submitted payload—it does not merely append one rule. On shared buckets, manage all retained notifications together and verify destination/queue policies first.

### 4.4. Destination verification workflow

S3 validates destinations when saving notification configuration. If the queue policy lacks permission or the ARN is wrong, the configuration call fails. The recommended order is:

1. Create the queue and DLQ.
2. Configure the redrive policy on the main queue.
3. Update the queue resource policy allowing S3 from the right bucket/account.
4. Configure notifications on the bucket.
5. Upload a test object matching the prefix/suffix.
6. Verify the message arrives in the queue and the worker processes it successfully.

Do not enable events on a production bucket before having an idempotent consumer, proper queue policy, DLQ, and monitoring in place.

## 5. S3 event payload and reading it in Spring Boot

### 5.1. Direct notification structure example

Abbreviated illustrative payload:

~~~json
{
  "Records": [
    {
      "eventVersion": "2.1",
      "eventSource": "aws:s3",
      "awsRegion": "ap-southeast-1",
      "eventTime": "2026-11-24T02:15:30.000Z",
      "eventName": "ObjectCreated:Put",
      "s3": {
        "bucket": {
          "name": "training-private-files"
        },
        "object": {
          "key": "incoming%2Ftenant-42%2Fdocument-123.pdf",
          "size": 8192,
          "eTag": "example-etag",
          "versionId": "example-version-id",
          "sequencer": "0067A123456789ABCD"
        }
      }
    }
  ]
}
~~~

Fields vary by event type, versioning configuration, and schema version. `versionId`, `size`, or `sequencer` are not guaranteed on every record. `eventName` such as `ObjectCreated:Put` omits the `s3:` prefix.

**Object keys in S3 notifications are URL-encoded using form encoding.** Spaces in keys can appear as `+`; decode using UTF-8 properly before calling S3. Never pass the raw JSON-encoded key straight into `GetObjectRequest`.

### 5.2. Spring Cloud AWS SQS dependencies

Alongside the S3 starter, add the SQS starter to use the listener:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>${spring-cloud-aws.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-s3</artifactId>
    </dependency>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-sqs</artifactId>
    </dependency>
</dependencies>
~~~

Use the BOM to align Spring Cloud AWS module versions. Versions must be compatible with Spring Boot; do not mix legacy starters with AWS SDK v2 in these examples.

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  storage:
    bucket: training-private-files
  sqs:
    file-events-queue: file-processing-queue
~~~

`app.storage.bucket` and `app.sqs.file-events-queue` are custom application properties. The queue name must refer to the queue created in the same Region. Worker credentials come from the AWS SDK provider chain, preferring the workload's IAM role.

### 5.3. Receiving messages with `@SqsListener`

Spring Cloud AWS SQS provides the `@SqsListener` annotation. You can receive the raw JSON string to parse the S3 notification envelope explicitly:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.stereotype.Component;

@Component
public class S3EventQueueListener {
    private final ObjectMapper objectMapper;
    private final S3ObjectEventHandler handler;

    public S3EventQueueListener(
            ObjectMapper objectMapper,
            S3ObjectEventHandler handler) {
        this.objectMapper = objectMapper;
        this.handler = handler;
    }

    @SqsListener("${app.sqs.file-events-queue}")
    public void receive(String message) throws Exception {
        JsonNode root = objectMapper.readTree(message);

        // S3 may send a test event when verifying the destination.
        if ("s3:TestEvent".equals(root.path("Event").asText())) {
            return;
        }

        JsonNode records = root.path("Records");
        if (!records.isArray()) {
            throw new IllegalArgumentException(
                    "S3 notification is missing Records array");
        }

        for (JsonNode record : records) {
            handler.handle(record);
        }
    }
}
~~~

The queue name in the example comes from `app.sqs.file-events-queue`. In production applications, configure the listener container factory for concurrency, acknowledgement, and error handling matching your Spring Cloud AWS version. With multiple event sources, separate listeners per queue or normalize payloads via dedicated adapters.

**Acknowledgement:** with `ON_SUCCESS` acknowledgement mode (or equivalent configuration in your Spring Cloud AWS version), a message is acknowledged only after the listener succeeds. If the listener throws an exception, the message is not marked complete and becomes visible again after the visibility timeout. Verify ack modes and error handlers for your library version; never delete a message before the business transaction completes.

### 5.4. Normalizing each record

One SQS message can contain multiple records. The handler should:

1. Verify `eventSource` is `aws:s3`.
2. Process only allowlisted `eventName` values, such as those starting with `ObjectCreated:`.
3. Read the bucket name and encoded object key.
4. Decode the key with UTF-8.
5. Extract `versionId`, `sequencer`, and optional metadata.
6. Verify the bucket/prefix falls within configured allowed scopes; never use arbitrary bucket/key values from a payload to access out-of-scope resources.

Payloads carry an `eventVersion` field in major/minor format. Consumers should verify the **major version** is supported; for newer minor versions, ignore unknown fields and proceed if required fields remain present. Avoid rigid closed-schema deserialization that breaks whenever an unrelated field is added.

Example key decoding snippet:

~~~java
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

String encodedKey = record.path("s3")
        .path("object")
        .path("key")
        .asText();

String objectKey = URLDecoder.decode(
        encodedKey, StandardCharsets.UTF_8);
~~~

`URLDecoder` turns `+` into spaces, matching S3 notification key encoding. Never decode twice; keys containing literal `%` characters were already encoded once, and a second decode corrupts the object name.

## 6. Consumer downloading objects and processing files

### 6.1. Worker service using `S3Client`

The consumer must only download objects from configured buckets/prefixes. The example below demonstrates fetching by version ID when supplied by the event:

~~~java
import java.io.InputStream;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;

@Service
public class S3ObjectEventHandler {
    private final S3Client s3;
    private final FileProcessingService processor;

    public S3ObjectEventHandler(
            S3Client s3,
            FileProcessingService processor) {
        this.s3 = s3;
        this.processor = processor;
    }

    public void handle(JsonNode record) throws Exception {
        if (!"aws:s3".equals(record.path("eventSource").asText())) {
            throw new IllegalArgumentException("Event source is not S3");
        }

        String eventName = record.path("eventName").asText();
        if (!eventName.startsWith("ObjectCreated:")) {
            return; // This queue handles only created objects.
        }

        JsonNode s3Record = record.path("s3");
        JsonNode object = s3Record.path("object");
        String bucket = s3Record.path("bucket").path("name").asText();
        String encodedKey = object.path("key").asText();
        String key = java.net.URLDecoder.decode(
                encodedKey, java.nio.charset.StandardCharsets.UTF_8);
        String versionId = object.hasNonNull("versionId")
                ? object.path("versionId").asText() : null;

        processObject(bucket, key, versionId);
    }

    public void processObject(
            String bucket, String key, String versionId) throws Exception {

        if (!"training-private-files".equals(bucket)
                || !key.startsWith("incoming/")) {
            throw new IllegalArgumentException(
                    "Bucket/prefix is outside the allowed processing scope");
        }

        GetObjectRequest.Builder request = GetObjectRequest.builder()
                .bucket(bucket)
                .key(key);

        if (versionId != null && !versionId.isBlank()) {
            request.versionId(versionId);
        }

        try (InputStream input = s3.getObject(request.build())) {
            processor.process(input, key);
        }
    }
}
~~~

`FileProcessingService` is an application-defined business service. This pattern streams bytes to avoid loading entire files into RAM; if the scanner/OCR tool requires seeking or re-reading, stream into a controlled temporary area with explicit quotas and cleanup.

`handle` shows wiring the parser to `processObject`. In production, perform an **idempotency claim** step before `processObject` and mark the event complete only after side effects and database state are persisted. If an SQS message contains multiple records and a later record fails, the whole message can be redelivered; already-processed records must be recognized as duplicates so side effects are not repeated.

The worker IAM role needs `s3:GetObject` on the input prefix, plus `s3:GetObjectVersion` when reading specific versions. For SSE-KMS objects, the role also needs appropriate KMS permissions like `kms:Decrypt` and matching key-policy authorization.

### 6.2. Why does version ID matter?

Suppose the same key is uploaded twice before the worker runs:

~~~text
10:00 PUT incoming/report.pdf → version v1
10:01 S3 emits event for v1
10:02 PUT incoming/report.pdf → version v2
10:03 Worker receives v1 event and calls default GET key
~~~

If the worker calls GET **without `versionId`**, it may read v2's content instead of the bytes that triggered event v1. When versioning is enabled and the event carries a version ID, the worker should GET that exact version.

If versioning is not enabled, a simple alternative is an **immutable key per upload**, such as `incoming/{tenant}/{uuid}.pdf`. Never reuse keys across distinct uploads in pipelines that must process each event accurately.

### 6.3. Do not treat every event type as a new file

Consumers should branch on `eventName`:

- `ObjectCreated:*`: start the new-file processing workflow.
- `ObjectRemoved:*`: update state or sync search indexes; do not call GET as if newly created.
- `ObjectRestore:Completed`: archived object has been restored; handle per restore use case.
- Tagging/ACL events: process only if business logic relies on those changes.

Ignore non-allowlisted events intentionally; never turn unsupported events into infinite retry loops. Unsupported schema major versions should be routed to a DLQ/investigation path rather than misprocessed silently.

## 7. Duplicates and out-of-order arrivals: designing idempotent consumers

### 7.1. S3 events are not exactly-once

S3 event notifications use **at-least-once delivery**. Events can be delivered multiple times and ordering is not guaranteed. SQS standard queues can also deliver duplicate messages and do not guarantee strict ordering.

Therefore, workers must assume:

- An event can be reprocessed after already succeeding.
- An event for an older object creation can arrive after an event for a newer one.
- A single message can carry multiple records.
- A worker can crash after performing side effects but before acknowledging the message.
- Retries can re-execute a job.

**Never build a consumer assuming each object emits exactly one message or that messages arrive in upload order.**

### 7.2. Idempotency key

One way to construct an event identity for S3 object notifications combines:

~~~text
bucket + decodedKey + versionId + sequencer + eventName
~~~

Where:

- `bucket + key` identifies the object.
- `versionId` distinguishes versions when versioning is enabled.
- `sequencer` establishes event ordering for **the same object key** when provided.
- `eventName` distinguishes action types.

Store the composite key or its hash in a processing table with a **unique constraint**. Do not rely solely on the SQS message ID: the same S3 event re-delivered or re-published can get a different SQS message ID.

Example database table:

~~~sql
CREATE TABLE processed_s3_events (
    event_key       VARCHAR(128) PRIMARY KEY,
    bucket_name     VARCHAR(255) NOT NULL,
    object_key      TEXT NOT NULL,
    version_id      VARCHAR(1024),
    sequencer       VARCHAR(128),
    event_name      VARCHAR(128) NOT NULL,
    status          VARCHAR(32) NOT NULL,
    processed_at    TIMESTAMP NULL
);
~~~

`event_key` is a normalized hash/identifier for the event. Upon receiving an event:

1. Attempt to insert the event record with status `PROCESSING`.
2. If the unique constraint reports it already exists with `COMPLETED`, skip the duplicate.
3. If `PROCESSING` by another worker, use a lease/lock or wait per policy.
4. If a prior attempt `FAILED` or its lease expired, decide whether to retry/reclaim.
5. Mark `COMPLETED` only after processing and business state updates succeed.

**Never mark COMPLETED before executing side effects.** If the process dies after writing COMPLETED but before generating thumbnails, retried messages will be skipped and the work remains undone. Conversely, if side effects finish before DB marks COMPLETED, retries must be able to produce the same output without duplication.

### 7.3. Sequencer compares only within the same object key

S3 events can supply `sequencer` to compare event order for **the same object key**. Never use `sequencer` to order events across two different keys.

When comparing two hexadecimal values of different lengths, left-pad the shorter value with `0`s and compare lexicographically. Do not treat `sequencer` as a timestamp or version ID.

In many pipelines, the safer option is **immutable keys + independent per-upload processing**, eliminating the need to reason about whether an older event should overwrite a newer object state. If business workflows process a mutable current object by key, store the latest accepted state and apply updates only from events no older than the accepted state.

### 7.4. Side effects must be retryable

Example of a worker creating thumbnails:

~~~text
incoming/tenant-42/file-123.pdf
        ↓
processed/tenant-42/file-123.pdf
thumbnails/tenant-42/file-123/page-1.png
~~~

Use output keys **deterministic from the input version/event**, or track output completion in the DB. If the worker re-runs, it can check whether the output already exists/completed to avoid duplicate artifacts. If side effects call external APIs or send emails, use target idempotency keys or a transactional outbox.

No single transaction spans SQS acknowledgement, S3 PUT, and database commit. Design each step with explicit states, retries, and reconciliation.

## 8. SQS visibility timeout, retries, and dead-letter queues

### 8.1. Visibility timeout

When SQS delivers a message to a consumer, it temporarily **hides the message from other consumers** for the visibility timeout duration. If the worker completes and acknowledges/deletes it, the message is removed. If the worker crashes or fails to acknowledge before timeout, the message reappears.

Set the visibility timeout longer than typical processing duration, leaving headroom for network latency and retries. For long-running jobs, consumers can extend visibility timeout while working via heartbeat/extension mechanisms; never let a message reappear while the original worker is still producing side effects.

### 8.2. Redrive and DLQ

Conceptual configuration example:

~~~text
Main queue: file-processing-queue
  visibility timeout: appropriate for processing duration
  maxReceiveCount: 5
  redrive target: file-processing-dlq

DLQ: file-processing-dlq
  retains failed messages for investigation
  does not retry endlessly automatically
~~~

`maxReceiveCount` is an illustrative threshold that must be tuned to retry/backoff policies and SLAs. When messages land in the DLQ, investigate:

- Does the payload match expected schema and supported event types?
- Do the bucket/key exist and does the role have GET permission?
- Is the file malformed, oversized, or rejected by the scanner?
- Does the KMS key allow decryption?
- Did the worker fail due to a code bug or an unavailable downstream dependency?

Once the root cause is fixed, redrive messages back to the main queue through a controlled workflow. Never bulk-redrive without understanding the failure, as that can create backlogs or duplicate side effects.

### 8.3. Long polling and concurrency

SQS long polling reduces empty receive calls and message-wait latency. Tune consumer concurrency to match:

- Number of worker instances and listener threads.
- CPU/RAM capacity for antivirus/OCR/conversion.
- Connection pools and S3 throughput.
- KMS quotas if objects use SSE-KMS.
- Capacity of the database and downstream dependencies.

Increasing concurrency does not always speed up the pipeline; it can overwhelm scanners, KMS, or the database. Monitor queue age and processing duration to tune safely.

## 9. IAM and permissions for each component

A pipeline has at least three independent permission sets:

| Component | Typical required permissions | Do not grant by default |
| --- | --- | --- |
| S3 bucket sending events to SQS | Queue resource policy granting service principal `s3.amazonaws.com` `sqs:SendMessage` | Permissions to read/delete objects |
| Spring Boot worker polling queue | `sqs:GetQueueUrl`, `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes`; optionally `sqs:ChangeMessageVisibility` | `sqs:*` on all queues |
| Worker downloading from S3 | `s3:GetObject` on input prefix; `s3:GetObjectVersion` if GETting by version | `s3:PutObject`/`s3:DeleteObject` if worker does not write/delete |
| Worker writing results | `s3:PutObject` on required output prefix | Write access to entire bucket |
| Worker reading SSE-KMS objects | `kms:Decrypt` and matching key policy/grant | `kms:*` on all keys |

The S3 service principal receives permission to send messages via the **SQS queue policy**. The worker uses its workload IAM role to receive/delete messages and access objects. These are two distinct identities.

If the queue has SSE-KMS enabled, workers need permissions to decrypt queue messages per configuration, and S3 needs permission to use the KMS key as required by SQS encryption. Inspect queue and key policies, not just the Spring Boot IAM role.

### 9.1. Separating processing permissions from admin permissions

The upload API does not need `s3:PutBucketNotification` or `sqs:SetQueueAttributes` at runtime. Notification rules, queue policies, redrive policies, and lifecycle rules should be managed by IaC or dedicated deployment roles. Workers should hold only the permissions needed to poll the queue, fetch inputs, and write outputs.

## 10. Avoiding event loops and managing business state

### 10.1. Separating input and output prefixes

A common misconfiguration:

~~~text
Notification: ObjectCreated:* for entire bucket
Worker receives event → writes thumbnail to same bucket
Thumbnail triggers new ObjectCreated event
Worker processes thumbnail → creates another thumbnail
...
~~~

To prevent infinite loops:

- Subscribe only to the `incoming/` prefix.
- Have workers write outputs to `processed/` or `thumbnails/`.
- For multiple pipelines, use distinct prefixes/suffixes or separate queues/topics.
- Do not rely on self-attached metadata to break loops if filters/policies do not already isolate inputs cleanly.

### 10.2. File state management

A simple state machine:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING_UPLOAD
    PENDING_UPLOAD --> UPLOADED: PUT succeeded
    UPLOADED --> PROCESSING: Worker claims event
    PROCESSING --> READY: Scan/OCR succeeded
    PROCESSING --> FAILED: Non-retryable business error
    PROCESSING --> RETRY_WAIT: Transient error
    RETRY_WAIT --> PROCESSING: Message re-delivered
    PENDING_UPLOAD --> EXPIRED: Not completed before deadline
    FAILED --> PROCESSING: Controlled redrive
~~~

Database state is the source of truth for the UI and business logic. SQS only holds pending work; a message deleted from the queue does not guarantee the file is `READY`. Conversely, an object existing in S3 does not mean it has been scanned and accepted.

### 10.3. Handling invalid files

Never let consumers endlessly retry unsupported formats or policy violations:

1. Transition the object record to `REJECTED` or `QUARANTINED`.
2. Record a normalized reason without logging sensitive contents.
3. If moving/copying the object, follow dedicated permissions and policies; do not auto-delete the original if audit retention requires it.
4. Acknowledge the message once the rejection state is durably saved.
5. Expose the outcome to the API/UI via the database or a separate business event.

Transient errors such as S3 timeouts, database unavailability, or temporary scanner outages warrant retries. Permanent data failures belong in a business rejection branch rather than cycling into the DLQ without useful feedback.

## 11. Monitoring and operating the pipeline

An event-driven pipeline must be observable from upload through completion:

| Metric | Meaning | When to investigate |
| --- | --- | --- |
| SQS `ApproximateNumberOfMessagesVisible` | Messages waiting in queue | Backlog growing steadily |
| `ApproximateNumberOfMessagesNotVisible` | Messages currently in flight | Sustained spikes or near visibility timeout |
| `ApproximateAgeOfOldestMessage` | Age of oldest queued message | Work delayed; SLA at risk |
| DLQ visible messages | Failed messages moved to DLQ | Sudden spike or repeated identical errors |
| Processing duration | Worker time per file | Increase after scanner/OCR changes |
| Success/failure/retry count | Outcome and retry rates | Credential errors, corrupt files, or dependency outages |
| S3/KMS error rate | Object/key access failures | AccessDenied, throttling, or key policy errors |
| Pending file age | Age of records not yet READY | Lost events, queue backlog, or failing workers |

Logs/traces should include `documentId`, normalized bucket/prefix, `eventName`, version ID/sequencer if present, SQS message ID, attempt count, and correlation ID. Never log presigned URLs, access keys, secrets, session tokens, or content bytes.

Even with S3 event notifications, run a periodic **reconciliation job**: find `UPLOADED/PENDING` records stuck too long, inspect object and processing status, and re-enqueue work idempotently. This catches misconfigured notifications or interrupted pipelines.

## 12. Testing S3 → SQS → Spring Boot

### 12.1. Testing layers

| Layer | Verifies | Limitations |
| --- | --- | --- |
| Unit tests | Event parsing, key decoding, `eventName` filtering, idempotency, state transitions | Does not test real S3/SQS delivery |
| LocalStack or suitable emulator | Bucket notifications, queues, listeners, and basic upload flow where supported | Event schemas, retries, and IAM/KMS may differ from AWS |
| AWS sandbox | Queue policy, S3 notifications, delivery, IAM, visibility timeout, DLQ, and KMS | Requires dedicated bucket/queue, cost tracking, and cleanup |

### 12.2. Integration test scenario

1. Create a sandbox bucket, SQS standard queue, and DLQ in the same Region.
2. Configure the queue policy allowing only that bucket to call `sqs:SendMessage`.
3. Register S3 notifications for prefix `incoming/` and suffix `.pdf`.
4. Upload a test PDF; verify the message arrives in the queue.
5. Run the worker and verify the database transitions `UPLOADED` → `PROCESSING` → `READY`.
6. Upload a file under another prefix; verify no job enters this queue.
7. Re-send the same event or simulate a duplicate; verify side effects do not repeat.
8. Deliver an event for an older version after a newer version; verify the worker reads the exact version ID or uses immutable keys.
9. Have the worker throw a transient exception; verify the message reappears after the visibility timeout.
10. Trigger repeated failures exceeding `maxReceiveCount`; verify the message lands in the DLQ.
11. Send an `s3:TestEvent` without `Records`; verify the listener does not misprocess it as an object event.
12. Verify workers do not receive output-object events because the prefix filter prevents loops.

### 12.3. Testing the parser with a mocked payload

~~~java
String json = """
{
  "Records": [{
    "eventSource": "aws:s3",
    "eventName": "ObjectCreated:Put",
    "s3": {
      "bucket": {"name": "training-private-files"},
      "object": {
        "key": "incoming%2Ftenant-42%2Fmy+file.pdf",
        "versionId": "version-123",
        "sequencer": "0067A123"
      }
    }
  }]
}
""";

JsonNode root = objectMapper.readTree(json);
JsonNode record = root.path("Records").get(0);

String encoded = record.path("s3")
        .path("object").path("key").asText();

String decoded = java.net.URLDecoder.decode(
        encoded, java.nio.charset.StandardCharsets.UTF_8);

// decoded = "incoming/tenant-42/my file.pdf"
~~~

Tests should assert `+` decodes to spaces and decoding happens only once. Also test keys with Unicode characters, already-encoded `%` sequences, and records missing optional fields.

## 13. Comparison with Azure and Google Cloud

Other cloud providers also support event-driven file processing, though event emission and queuing mechanisms differ:

| Concept | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Object storage | Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| Event source | S3 Event Notifications / EventBridge | Event Grid for Blob Storage | Cloud Storage notifications / Eventarc per use case |
| Queue/messaging | Amazon SQS, SNS | Azure Service Bus, Storage Queue, Event Grid | Pub/Sub |
| Spring consumer | Spring Cloud AWS SQS | Spring Cloud Azure messaging | Spring Cloud GCP Pub/Sub |
| Retry/dead-letter | SQS visibility/redrive/DLQ | Service Bus delivery count/DLQ or matching queue policy | Pub/Sub retry/dead-letter policy |
| Identity | IAM role + queue/bucket policy | Managed Identity + Azure RBAC | Service account + Google IAM |

Never assume event payloads, ordering, retries, retention, or dead-letter semantics are identical. An internal domain event can normalize them as:

~~~java
public record ObjectCreatedEvent(
        String provider,
        String bucketOrContainer,
        String objectKey,
        String versionOrGeneration,
        String eventType,
        String eventIdentity) {}
~~~

The AWS adapter translates S3 notifications/EventBridge into the domain event; the Azure adapter translates Event Grid; the GCP adapter translates Cloud Storage/Pub/Sub events. Document-processing business logic remains shared, while provider-specific details (version ID/generation, identity, retries, queue acks, and event schemas) stay inside adapters.

## 14. Practice exercises

### Exercise A — S3 sending events to SQS

Create a sandbox bucket, SQS standard queue, and queue policy. Configure `s3:ObjectCreated:*` with prefix `incoming/`. Upload a test file and confirm the queue receives the notification. Explain why S3 needs `sqs:SendMessage` in the queue policy.

### Exercise B — Spring Boot worker

Add `spring-cloud-aws-starter-sqs`, write an `@SqsListener` receiving JSON messages, parse each record, and download objects with `S3Client`. Update file state in the database. Verify the worker refuses to read keys outside allowed buckets/prefixes.

### Exercise C — Duplicates and retries

Send the same event twice. Use a unique constraint/idempotency key to prove only one business result is produced. Then force the worker to fail once and succeed on redelivery; observe visibility timeout and acknowledgement behavior.

### Exercise D — Versioning and out-of-order events

Enable versioning in a test bucket, upload two payloads to the same key, and simulate out-of-order events. Have the worker GET by version ID or use immutable keys. Explain why `sequencer` comparisons apply only within the same object key.

### Exercise E — DLQ and event loops

Intentionally trigger repeated processing errors until a message reaches the DLQ. Inspect the payload and fix the bug before redriving. Write outputs under a different prefix from inputs, confirming the worker never re-triggers itself.

### Exercise F — Multi-cloud comparison

Design the same document-processing pipeline on AWS (S3 + SQS), Azure (Blob + Event Grid/Service Bus), and GCP (Cloud Storage + Pub/Sub/Eventarc). Build a mapping table covering events, queues, identities, retries, DLQs, and version references.

### Self-check questions

1. Do S3 event notifications contain file bytes or object reference metadata?
2. When do you need `ObjectCreated:Put` vs. `ObjectCreated:CompleteMultipartUpload`?
3. How do prefix/suffix filters help, and why should outputs never live under the input prefix?
4. Why does S3 need a queue policy granting `sqs:SendMessage`?
5. Can S3 event notifications deliver directly to an SQS FIFO queue?
6. Do S3 event notifications and EventBridge events share the same JSON envelope?
7. Why can S3 events and SQS standard queues produce duplicates or out-of-order delivery?
8. Why should you not rely solely on SQS message ID as the idempotency key for S3 events?
9. When versioning is enabled, why should workers GET by version ID?
10. Within what scope can `sequencer` be used to compare event ordering?
11. Which two problems do visibility timeout and DLQs solve?
12. Why must events be marked `COMPLETED` only after side effects and database state are safely persisted?
13. When should you prefer SNS fan-out over a single SQS queue?
14. Why is a reconciliation job needed for stuck `UPLOADED` records?
15. Which parts of the pipeline can be shared across AWS, Azure, and GCP, and which must remain provider-specific?

**Expected outcome:** learners can configure S3 event notifications to SQS, build a Spring Boot worker that receives and processes files asynchronously, handle duplicates/out-of-order events/retries safely, manage visibility timeouts and DLQs, and map event-driven file processing across Azure and Google Cloud.
