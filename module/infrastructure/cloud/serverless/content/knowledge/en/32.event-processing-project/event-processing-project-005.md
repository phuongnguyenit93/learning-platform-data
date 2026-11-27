# Partial Batch Failure Reporting and Routing Failed Files to Quarantine

An event-driven file processing pipeline often receives multiple notifications in a single function invocation. Each notification may point to a file in object storage; inside each file, there may be hundreds or thousands of records. A single malformed record should not forfeit the results of valid records, yet the system must preserve evidence of the faulty data and offer a way to reprocess it once the root cause is fixed.

This lesson builds a serverless Java pipeline capable of:

- Processing each message in a batch independently.
- Continuing to process valid records when some records are invalid.
- Returning only the exact messages that need retrying.
- Durably writing unprocessable records or files to quarantine.
- Acknowledging messages only after results and error records are safely stored.
- Preventing duplicate processing when the broker redelivers messages.
- Replaying data after fixes without producing repeated side effects.

One distinction runs throughout this lesson: **message-level partial batch failure** and **record-level partial failure inside a file** are two different mechanisms. With SQS-triggered Lambda, a partial batch response reports failures by message ID. If a single message represents an entire file, the function itself must persist failed records to quarantine; it cannot ask SQS to redeliver only specific lines inside a file.

## 1. Project Context and Goals

Suppose a system receives order or product data files uploaded by partners. Files are stored in object storage, and an object-created event is placed onto a queue. A Java function reads the file, validates each record, and writes valid data to the target system.

Example CSV file:

~~~csv
order_id,customer_id,amount,currency
ORD-1001,CUS-01,125.50,VND
ORD-1002,CUS-02,invalid,VND
ORD-1003,CUS-03,89.00,VND
ORD-1004,,42.00,VND
~~~

In this example:

- `ORD-1001` is valid and can be processed.
- `ORD-1002` has a non-numeric `amount`.
- `ORD-1003` is valid and can be processed.
- `ORD-1004` is missing `customer_id`.

If the entire batch is retried solely because of two bad rows, valid rows will be re-read and re-processed repeatedly. If the function ignores errors and acks the message, the two bad rows vanish from the workflow unnoticed.

The design must preserve outcomes at each level:

| Level | Processing Unit | Failure Outcome |
|---|---|---|
| Message batch | One SQS message or event message | Return message ID in partial batch response for retry |
| File | One object/file referenced by a message | Quarantine file if unreadable or unprocessable at the file level |
| Record | One row/entry inside a file | Write faulty record to a rejected-records artifact |
| Side effect | One record written to a database/API | Use idempotency keys and versions to avoid duplication |

The goal is not to make every error disappear from the queue. The goal is to classify errors accurately, retain data needing repair, and retry only work likely to succeed upon retry.

## 2. Overall Architecture

A reference architecture:

~~~mermaid
flowchart LR
    A["Uploader / partner"] --> B["Object storage: incoming/"]
    B --> C["Object-created event"]
    C --> D["Queue"]
    D --> E["Java serverless file processor"]
    E --> F["Validate file and records"]
    F --> G["Valid records"]
    F --> H["Rejected records"]
    G --> I["Database / downstream service"]
    H --> J["Quarantine storage"]
    E --> K["Durable job manifest"]
    E --> L["Partial batch response"]
    L --> D
    M["Replay / repair workflow"] --> J
    M --> E
~~~

| Component | Responsibility |
|---|---|
| Object storage | Stores immutable or versioned input files |
| Event notification | Signals new objects |
| Queue | Buffers, retries, and distributes messages |
| Java file processor | Reads files, classifies errors, and coordinates batches |
| Validator/parser | Validates file structure and individual records |
| Database/downstream | Persists outcomes of valid records |
| Quarantine storage | Stores unprocessable files or records |
| Job manifest | Tracks state, counts, and progress |
| Replay workflow | Repairs data and re-runs in a controlled manner |

S3 + SQS + AWS Lambda serves as a concrete example, though the pattern applies to equivalent object storage, event brokers, and function services. Response formats and trigger settings depend on the provider.

### 2.1. Decoupling Events from File Contents

The queue should carry an object reference rather than stuffing entire file contents into the message:

~~~json
{
  "bucket": "partner-ingestion",
  "key": "incoming/partner-17/orders-2026-11-17.csv",
  "versionId": "3Lg...example",
  "eventId": "evt-9c2f",
  "receivedAt": "2026-11-17T10:15:30Z"
}
~~~

This keeps messages small, avoids queue size limits, and lets the function stream files as needed. If object storage supports versioning, use `versionId` to read the exact object that triggered the event. Without a version ID, store another stable identifier and verify content checksums upon download.

Never rely on the object key alone if the same key can be overwritten. An older event could accidentally read newer contents and process the wrong file version.

## 3. Classifying Errors Before Choosing an Action

Not every error warrants a retry. Distinguish transient errors, data errors, whole-file errors, and infrastructure errors.

| Error Type | Examples | Action |
|---|---|---|
| Transient infrastructure | Object storage timeout, database throttling, network reset | Retry message |
| Transient downstream | Search/database temporarily unavailable, HTTP 503 | Retry with backoff |
| Invalid record | Missing required field, malformed amount, invalid enum | Write record to quarantine; continue other records |
| Invalid file | Corrupt encoding, wrong header, unsupported format | Quarantine the entire file |
| Unsupported schema | Schema version unsupported by consumer | Quarantine file or route to manual compatibility flow |
| Duplicate delivery | Same event/object redelivered | Recognize via idempotency and return prior result |
| Configuration/security | Bad credentials, revoked object read permission | Alert; bounded retry or halt per policy |

### 3.1. Transient vs. Permanent Errors

**Transient errors** are likely to clear on retry: timeouts, connection resets, throttling, or service unavailability. Do not immediately quarantine these because the data itself may be completely valid.

**Permanent record errors** typically do not change when retrying the same data: missing required fields, wrong types, non-existent reference codes, or out-of-domain values. Log the record and reason so the sender can fix it.

**Permanent file errors** prevent reading or interpreting any record: corrupted files, invalid encoding, headers violating contract, or unsupported formats. Quarantine the original file with metadata.

Never classify a downstream HTTP 500 as a data error. If infrastructure errors get written to quarantine, valid data gets discarded merely because a dependency had a temporary outage.

## 4. State Machine of a File Job

Tracking file state in a durable manifest lets the function recover after timeouts or restarts.

Reference states:

| State | Meaning |
|---|---|
| RECEIVED | Event received and job identity created |
| PROCESSING | Reading and processing the file |
| RETRY_PENDING | Encountered transient error; waiting for broker redelivery |
| COMPLETED | All valid records processed |
| COMPLETED_WITH_ERRORS | Valid records processed; faulty records saved to quarantine |
| QUARANTINED | Entire file unprocessable and original safely stored |
| REPLAY_PENDING | Repaired file or records queued for replay |
| REPLAYING | Replay job in progress |
| REPLAYED | Replay finished |

Illustrative state transitions:

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> PROCESSING
    PROCESSING --> COMPLETED
    PROCESSING --> COMPLETED_WITH_ERRORS
    PROCESSING --> QUARANTINED
    PROCESSING --> RETRY_PENDING: transient failure
    RETRY_PENDING --> PROCESSING: redelivery
    QUARANTINED --> REPLAY_PENDING: approved repair
    COMPLETED_WITH_ERRORS --> REPLAY_PENDING: corrected records
    REPLAY_PENDING --> REPLAYING
    REPLAYING --> REPLAYED
    COMPLETED --> [*]
    COMPLETED_WITH_ERRORS --> [*]
    QUARANTINED --> [*]
    REPLAYED --> [*]
~~~

The manifest should store at least:

- Job ID and object identity.
- Source bucket/container, key, and version.
- Content checksum.
- Schema version and processor version.
- Current state.
- Total records, succeeded count, and rejected count.
- Attempt count and processing timestamps.
- Quarantine object key if applicable.
- Normalized error reason.
- Start/end timestamps and correlation ID.

Never use static variables in a Java function to hold job state. Functions can scale out, restart, or execute across different instances.

`RETRY_PENDING` is an observable job state while the queue awaits redelivery. If the manifest store is also failing, do not make persisting retry state a prerequisite for returning a message failure; queue delivery metadata remains the source of truth for the next attempt.

## 5. SQS Message-Level Partial Batch Responses

A single Lambda invocation can receive multiple SQS messages. If one message fails, default handling depends on event source mapping settings. With partial batch responses, the function can specify exactly which messages the queue should redeliver.

For SQS, the identifier in the response is the SQS message's **messageId**. It is not the object key, producer event ID, or file line number.

Example:

~~~json
{
  "batchItemFailures": [
    {
      "itemIdentifier": "sqs-message-id-002"
    }
  ]
}
~~~

If a batch has 5 messages and only the second encounters a transient error, the function returns that message ID. The remaining messages are treated as successfully processed under the partial batch response protocol.

### 5.1. Configuring AWS Lambda Event Source Mapping

With AWS Lambda + SQS, enable the `ReportBatchItemFailures` response type on the event source mapping. CloudFormation example:

~~~yaml
FileProcessorMapping:
  Type: AWS::Lambda::EventSourceMapping
  Properties:
    EventSourceArn: !GetAtt InputQueue.Arn
    FunctionName: !Ref FileProcessorFunction
    BatchSize: 10
    FunctionResponseTypes:
      - ReportBatchItemFailures
    Enabled: true
~~~

Without enabling this feature, partial failure responses may not be honored by the platform as intended. During deployment, verify actual event source mapping configuration, queue visibility timeout, function timeout, and retry/DLQ policies.

### 5.2. Java Handler Returning Partial Batch Responses

Skeleton example using AWS Lambda Java Events:

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.amazonaws.services.lambda.runtime.events.SQSBatchResponse;

import java.util.ArrayList;
import java.util.List;

public final class FileBatchHandler
        implements RequestHandler<SQSEvent, SQSBatchResponse> {

    private final FileJobService fileJobService =
            ApplicationServices.fileJobService();

    @Override
    public SQSBatchResponse handleRequest(
            SQSEvent event,
            Context context) {

        List<SQSBatchResponse.BatchItemFailure> failures =
                new ArrayList<>();

        for (SQSEvent.SQSMessage message : event.getRecords()) {
            try {
                ObjectReference reference =
                        ObjectReference.fromNotification(message.getBody());

                fileJobService.process(reference);

            } catch (RetryableProcessingException ex) {
                SQSBatchResponse.BatchItemFailure failure =
                        new SQSBatchResponse.BatchItemFailure();
                failure.setItemIdentifier(message.getMessageId());
                failures.add(failure);

                context.getLogger().log(
                        "Retryable file processing failure for message "
                                + message.getMessageId());
            } catch (Exception ex) {
                SQSBatchResponse.BatchItemFailure failure =
                        new SQSBatchResponse.BatchItemFailure();
                failure.setItemIdentifier(message.getMessageId());
                failures.add(failure);

                context.getLogger().log(
                        "Unexpected failure for message "
                                + message.getMessageId());
            }
        }

        return new SQSBatchResponse(failures);
    }
}
~~~

This is an illustrative skeleton; dependency wiring, notification parsing, and logging must connect to your real application. The handler returns success only when `FileJobService` completes or durably writes to quarantine. Unexpected unclassified errors should be retried and alerted, never silently dropped.

### 5.3. FIFO Queues

With SQS FIFO, message order matters. When one message fails, stop processing subsequent messages in the same batch and report the failed message plus all unprocessed messages following FIFO partial batch rules. Continuing past an error can break business ordering.

With standard queues, messages can be processed independently without global ordering guarantees. Regardless of queue type, consumers still require idempotency because deliveries may repeat.

## 6. Partial Failures Inside a File

SQS partial batch responses only identify messages. If one message points to a 1,000-row CSV, SQS has no awareness that rows 20 and 700 failed.

There are two strategies:

**One message per file:** the function reads the entire file, processes valid records, writes faulty records to a quarantine artifact, and acks the message only after all outcomes are durably persisted.

**One message per record:** the producer or a splitter step emits a separate message per record. The queue can retry individual records independently, though message count grows and file-completion tracking is required.

| Criterion | One message/file | One message/record |
|---|---|---|
| Queue volume | Lower | Higher |
| Partial retry | Per file | Per record |
| Progress tracking | Needs in-file manifest/checkpoint | Broker tracks individual messages |
| Best suited for | Small/medium files, batch imports | Independent records, high throughput |
| Risks | File retry may re-read many records | High message count and orchestration cost |

For large files or long processing times, use a splitter step: read the file, create small chunks, persist chunks durably, and emit messages per chunk. Message identity can then be file identity + chunk number.

### 6.1. Rules for Handling Files with Faulty Records

Example file with 1,000 records:

- 970 valid records.
- 25 invalid data records.
- 5 records hit transient database errors during write.

Correct outcome:

1. Commit the 970 valid records using idempotency keys.
2. Write the 25 invalid data records to a rejected-records artifact.
3. Do not mark the 5 infrastructure-error records as data errors.
4. If the 5 records cannot complete yet, fail the message or save a checkpoint to resume per design.
5. Transition the file to `COMPLETED_WITH_ERRORS` only once every record has a final outcome and the rejected artifact is durably persisted.

Never mark a file complete merely because most records succeeded. Distinguish records awaiting retry from permanently rejected records.

If a format can reveal structural corruption mid-file (such as an unclosed CSV quote or a corrupted archive tail), do not write business side effects immediately after reading just a few rows. Preflight the entire structure first, or stream parsed content into durable staging before applying records. If the business contract allows partial import even when the tail is corrupt, document that policy explicitly and checkpoint exact committed records.

## 7. Record-Level Results in Java

Separate per-record outcomes for testability and reporting:

~~~java
public record RecordError(
        long rowNumber,
        String errorCode,
        String safeMessage,
        String rawRecord) {
}

public record FileProcessingSummary(
        long totalRecords,
        long succeededRecords,
        long rejectedRecords,
        long retryableFailures) {
}
~~~

In systems handling sensitive data, `rawRecord` should only be written to a restricted-access quarantine artifact. Logs should contain only row numbers, error codes, and correlation IDs.

An error enum helps classify actions:

~~~java
public enum FailureKind {
    INVALID_RECORD,
    INVALID_FILE,
    TRANSIENT_STORAGE,
    TRANSIENT_DATABASE,
    DOWNSTREAM_UNAVAILABLE,
    UNSUPPORTED_SCHEMA,
    CONFIGURATION
}
~~~

Validators should only emit data errors when evidence shows a record violates contract. Repository timeouts must map to retryable errors, never `INVALID_RECORD`.

## 8. File Processing and Quarantine Flow

Flow for a single message/file:

1. Create or fetch the job manifest by object identity.
2. If the job is already `COMPLETED`, `COMPLETED_WITH_ERRORS`, or `QUARANTINED`, return idempotently.
3. Read the exact object version and compute checksum.
4. Check size, encoding, headers, and schema.
5. If the file is unreadable, write the original plus metadata to quarantine.
6. If the file is valid, read record by record.
7. Validate and process valid records with idempotent operations.
8. Collect permanent data errors per record.
9. Write a rejected-records artifact if any records were rejected.
10. Update manifest and summary after artifacts/results are durable.
11. Return success for the message once the file reaches a terminal state.
12. On transient errors blocking progress, fail the message to trigger retry.

Crucially, **quarantine writes must complete before ACKing the message**. If a function merely logs an error and acks, faulty data has no recovery path.

### 8.1. Distinguishing Whole-File Errors from Per-Record Errors

| Scenario | Handling |
|---|---|
| Cannot open object due to timeout | Retry message |
| File has invalid encoding | Quarantine original file |
| Header missing required column | Quarantine original file |
| One row has malformed amount | Write row to rejected artifact, continue |
| One row references non-existent ID | Reject record per policy; optionally retry if reference arrives eventually |
| Database timeout writing valid record | Retry or checkpoint; do not quarantine record |
| Rejected artifact write fails | Retry message; do not ack |
| Manifest update fails after writing data | Safe retry via idempotency |

A missing reference can be a data error or a race/eventual consistency issue depending on business logic. For example, a customer created after an order event may require bounded retries or reference-readiness checks before quarantining.

## 9. Java `FileJobService`

Example adapter interfaces:

~~~java
public interface ObjectStorage {
    InputStream open(ObjectReference reference);
    void putIfAbsent(String key, byte[] content, Map<String, String> metadata);
}

public interface JobManifestRepository {
    Optional<FileJobManifest> find(String jobKey);
    void markProcessing(String jobKey);
    void markCompleted(
            String jobKey,
            FileProcessingSummary summary,
            String rejectedObjectKey);
    void markQuarantined(
            String jobKey,
            String quarantineObjectKey,
            String reasonCode);
}

public interface RecordRepository {
    void upsertIdempotently(
            String idempotencyKey,
            OrderRecord record);
}
~~~

The repository can implement `markCompleted` by setting `COMPLETED` when `rejectedRecords` is 0 and `COMPLETED_WITH_ERRORS` when records were rejected. Both are terminal states reached only after every record has an outcome and quarantine artifacts have been written successfully.

A condensed processing flow:

~~~java
public final class FileJobService {

    private final ObjectStorage storage;
    private final JobManifestRepository manifests;
    private final RecordRepository records;
    private final OrderFileParser parser;
    private final OrderValidator validator;
    private final QuarantineWriter quarantine;

    public void process(ObjectReference reference) {
        String jobKey = reference.stableIdentity();

        Optional<FileJobManifest> existing = manifests.find(jobKey);
        if (existing.isPresent() && existing.get().isTerminal()) {
            return;
        }

        manifests.markProcessing(jobKey);

        try (InputStream input = storage.open(reference)) {
            ParsedFile file = parser.parseAndValidateHeader(input);

            List<RecordError> rejected = new ArrayList<>();
            long succeeded = 0;

            for (ParsedRecord row : file.records()) {
                OrderRecord order;
                try {
                    order = validator.validate(row);
                } catch (InvalidRecordException ex) {
                    rejected.add(new RecordError(
                            row.rowNumber(),
                            ex.code(),
                            ex.safeMessage(),
                            row.rawValue()));
                    continue;
                }

                String idempotencyKey =
                        jobKey + ":row:" + row.rowNumber();
                records.upsertIdempotently(idempotencyKey, order);
                succeeded++;
            }

            String rejectedKey = null;
            if (!rejected.isEmpty()) {
                rejectedKey = quarantine.writeRejectedRecords(
                        reference,
                        rejected);
            }

            FileProcessingSummary summary =
                    new FileProcessingSummary(
                            file.totalRecords(),
                            succeeded,
                            rejected.size(),
                            0);

            manifests.markCompleted(
                    jobKey,
                    summary,
                    rejectedKey);

        } catch (InvalidFileException ex) {
            String quarantineKey =
                    quarantine.writeOriginalFile(reference, ex.code());

            manifests.markQuarantined(
                    jobKey,
                    quarantineKey,
                    ex.code());

        } catch (TransientProcessingException ex) {
            throw new RetryableProcessingException(ex);
        }
    }
}
~~~

This is an illustrative skeleton. Add memory limits, streaming parsers, storage/database exception classification, timeouts, metrics, and proper transactions. Holding rejected lists in memory suits only small-to-medium files; for large files, stream or chunk rejected artifacts.

In the example, the parser must complete structural preflight before returning `ParsedFile` to the business-write loop. For large files, preflight can emit staged objects/chunks instead of holding all content in RAM. If the parser only detects structural corruption near the end, previously written records must not turn a file-level failure into `QUARANTINED` with unrecorded side effects.

### 9.1. Do Not Lump All Exceptions into `InvalidRecordException`

A database or object storage failure does not prove record data is invalid. Keep exception boundaries clear:

- Parsers/validators throw `InvalidRecordException` for errors provable from payload data.
- Parsers throw `InvalidFileException` for unprocessable file structures.
- Adapters throw `TransientProcessingException` for retryable infrastructure failures.
- Configuration/permission errors trigger alerts and dedicated policy handling.

Catching `Exception` and adding everything to the rejected list allows a database outage to turn an entire valid file into faulty records.

## 10. Designing Quarantine Storage

Quarantine is a storage area for data needing investigation or repair. Keep it separate from normal input and output locations.

Example object key layout:

~~~text
quarantine/
  partner-17/
    2026/11/17/
      job-8f2a/
        original-file.csv
        rejected-records.jsonl
        manifest.json
~~~

You can store:

- Original file for file-level failures.
- Rejected records for record-level failures.
- Manifest containing reason codes, row counts, and schema version.
- Processor version, source object version, and checksum.
- Correlation ID and processing timestamp.

Never place unsanitized user-supplied filenames directly into paths. Use system-generated job IDs or stable hashes to prevent path traversal and name collisions.

### 10.1. Example `rejected-records.jsonl`

~~~json
{"rowNumber":2,"errorCode":"INVALID_AMOUNT","message":"amount must be a decimal","record":{"order_id":"ORD-1002","customer_id":"CUS-02","amount":"invalid","currency":"VND"}}
{"rowNumber":4,"errorCode":"MISSING_CUSTOMER_ID","message":"customer_id is required","record":{"order_id":"ORD-1004","customer_id":"","amount":"42.00","currency":"VND"}}
~~~

Each line as standalone JSON simplifies streaming, grep, and record-level replay. Consider retaining raw records if operators need to fix them; if data contains PII, enforce encryption, restricted access, and retention policies.

### 10.2. Metadata and Reason Codes

Use stable reason codes rather than entire exception messages as identifiers:

| Reason code | Meaning |
|---|---|
| FILE_ENCODING_INVALID | Unsupported encoding |
| FILE_HEADER_MISMATCH | Header violates schema |
| FILE_FORMAT_UNSUPPORTED | Unsupported format |
| RECORD_REQUIRED_FIELD_MISSING | Missing required field |
| RECORD_VALUE_INVALID | Invalid type or out-of-range value |
| RECORD_REFERENCE_NOT_FOUND | Referenced data not found |
| SCHEMA_VERSION_UNSUPPORTED | Unsupported schema version |

Detailed messages can evolve across versions; reason codes should remain stable so dashboards and replay workflows keep working long-term.

## 11. How Does Quarantine Differ from a DLQ?

Both quarantine and dead-letter queues isolate failures, but they serve different purposes.

| Criterion | Quarantine | DLQ |
|---|---|---|
| Target | File or record payloads | Message/event deliveries |
| Cause | Invalid payload or needs repair | Message exceeded retry policy or unprocessable |
| Contents | Original data, rejected records, manifest | Original envelope/message and delivery metadata |
| Remediation | Fix data, transform schema, or drop record | Fix consumer/config/dependency then replay |
| Owner | Data operations/business owner | Platform/application operations |
| Replay | Create new job from repaired artifact | Redrive message per policy |

A file with a bad header can be written to quarantine and the message acked because the data is safely preserved for manual remediation. A message hitting a database timeout should retry; once retries exhaust, it moves to the DLQ for delivery failure investigation.

Never use a DLQ as a substitute for faulty business file storage. Queues have retention, message size limits, and payload inspection tools quite different from object storage.

## 12. Idempotency When Retrying Files and Records

SQS standard queues have at-least-once delivery. A message can arrive multiple times, even when a prior run completed side effects before ACKing.

Derive job identity from object identity:

~~~text
jobKey = hash(bucket + key + versionId)
~~~

Without `versionId`, combine bucket, key, and content SHA-256 checksum. ETags can be saved as reference metadata, but should not be assumed to equal MD5 checksums across all upload/encryption modes.

Idempotency key per record:

~~~text
recordKey = jobKey + rowNumber
~~~

If business operations must deduplicate across different files, also use a business key or producer idempotency key. Job/row keys only prevent reprocessing the exact same position inside the exact same file.

### 12.1. Safe Database Writes During Function Retries

Example processed-record table with a unique key:

~~~sql
CREATE TABLE processed_input_record (
    idempotency_key VARCHAR(300) PRIMARY KEY,
    business_id VARCHAR(150) NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL
);
~~~

Within a transaction, write the idempotency key and business effect so they commit or roll back together. If the key exists, compare `payload_hash` and return the prior result. If the same key appears with a different `payload_hash`, treat it as a conflict requiring investigation rather than silently skipping.

Never write a completed marker before the business side effect actually commits. Writing the marker first and crashing leaves future retries skipping uncommitted records.

### 12.2. Manifests and Checkpoints

For large files, persist checkpoints by chunk or row range:

- File identity.
- Chunk number/range.
- Chunk status.
- Succeeded/rejected record counts.
- Quarantine artifact key.
- Chunk checksum.
- Processor version.

Checkpoints update only after the chunk's side effects commit and the chunk's reject artifact is durably written. On retry, read the checkpoint and resume only unfinished parts; keep operations idempotent because checkpoint updates themselves can repeat or fail.

## 13. Ordering Result Writes and Message ACKs

A key principle:

**Never ack a message before every required output is durably persisted.**

For a file with faulty records:

1. Write valid records to the database using idempotent writes.
2. Write the rejected-records artifact.
3. Write the `COMPLETED_WITH_ERRORS` manifest and summary.
4. Return success for the SQS message.

If step 2 or 3 fails, return a message failure. When redelivered, step 1 re-runs safely because idempotency prevents duplicate side effects.

If the object/file is invalid:

1. Copy the original to quarantine.
2. Verify the quarantined object exists with matching metadata/checksum.
3. Write the `QUARANTINED` manifest.
4. Ack the message.

If quarantine storage is unavailable, do not ack. Source data must remain in input storage or referenced by the queue for retry.

No single ACID transaction spans databases, object storage, and queue ACKs. The design must use durable state, idempotency, and operation ordering to recover from crashes at any point.

## 14. "Moving" Files in Object Storage

On conventional filesystems, renaming within the same filesystem can be atomic depending on OS/filesystem. On object storage like S3, moving is typically **copying the object to a new key and deleting the source object**; never assume atomic rename.

Safe procedure:

1. Read the exact source object version.
2. Copy to an immutable quarantine key.
3. Verify copy success and metadata/checksum.
4. Write the manifest pointing to the quarantined object.
5. Delete the source object only if retention/policy permits and all prior steps succeeded.

If the copy succeeds but the manifest update fails, retries may copy again. Use deterministic quarantine keys and conditional puts/copies or check the destination object so repeated runs stay safe.

Many systems retain source files in `incoming/archive` per retention policy and treat quarantine as a classified copy. Delete sources only when retention policies permit.

### 14.1. Avoiding Trigger Loops

If object-created events are configured across an entire bucket, writing files to quarantine can trigger the same file-processing function, creating an infinite loop.

Safeguards:

- Use a separate bucket for quarantine.
- Or restrict notifications strictly to the `incoming/` prefix.
- Never configure triggers on the `quarantine/` prefix.
- Use a separate `archive/` prefix.
- Check event source and object key before processing.
- Keep code guards, but never rely on code guards instead of proper notification filtering.

This is a common deployment mistake: the function writes bad files to the same bucket, and those bad files immediately become fresh inputs.

## 15. Batch Size, Timeouts, and Backpressure

Batch size impacts throughput, memory, and retry blast radius.

| Batch size | Benefits | Risks |
|---|---|---|
| Small | Good error isolation, short invocation duration | More invocations and overhead |
| Large | Less overhead, higher aggregation efficiency | Prone to timeouts, high memory, many messages retried on failure |
| By byte/chunk | Better resource predictability | Requires splitters and more complex manifests |

Measure:

- Object read duration.
- File size and record count.
- Parse/validation duration.
- Database write throughput.
- Quarantine write duration.
- Peak memory usage.
- SQS batch age and queue depth.
- Function timeouts/throttling.

Never pick batch size solely by message count. Ten messages pointing to ten 1 MB files differ completely from ten 500 MB files.

### 15.1. Visibility Timeouts

With SQS, visibility timeouts must be long enough for the function to process the batch and finish side effects. If the visibility timeout is too short, messages can be delivered to another invocation while the first is still running.

Coordinate:

- Lambda timeout.
- SQS visibility timeout.
- Batch size.
- Maximum concurrency.
- Retry/backoff policies.
- Possible downstream slowdowns.

If files are too large to process within function limits, use chunking or workflow orchestration rather than pushing timeouts to unmanageable extremes.

### 15.2. Limiting Concurrency to Protect Downstream Systems

Serverless platforms can spin up invocations faster than databases can absorb writes. Cap concurrency, batch sizes, connection pools, and rate limits so an import spike does not take down target systems.

When queue backlog climbs while the database is already saturated, lowering concurrency or pausing consumers is safer than spinning up more functions.

## 16. Quarantine Security and Retention

Quarantine often holds unvalidated data. It may contain PII, malformed payloads, or malicious content.

Requirements:

- Encrypt objects at rest and in transit.
- Separate IAM permissions for writers, reviewers, and replay workers.
- Never grant broad public-like read permissions on quarantine buckets.
- Scan for malware when files may contain executables or archives.
- Cap file size, decompression ratios, and allowed formats.
- Never log raw payloads or secrets.
- Store only minimal required reason codes and metadata.
- Set retention/lifecycle rules aligned with data policy.
- Audit all read, edit, download, and replay actions.
- Verify tenant isolation when multiple partners share a pipeline.

Object names should avoid containing emails, phone numbers, or identifying data. Use opaque job IDs and keep mapping metadata inside access-controlled manifests.

### 16.1. Controlled Replay

Never let arbitrary users download quarantined files and push them straight back into incoming. Replay workflows should:

1. Identify owner and failure reason.
2. Repair the payload or deploy an updated parser/schema.
3. Verify checksum and repaired contents.
4. Create a new replay job ID linked to the original job.
5. Preserve provenance and prior attempt history.
6. Run back through the same validation and idempotency mechanisms.
7. Reconcile succeeded, rejected, and pending record counts.
8. Close the incident once outcomes are verified.

When replaying the exact same file, job identity can stay unchanged to continue the same workflow or intentionally create a new generation. This decision must align with idempotency keys; never alter keys arbitrarily to dodge conflicts and accidentally double-write business data.

A clean management approach keeps the original job identity immutable and creates a separate `replayJobId`/generation to track repairs. Unchanged records reuse original idempotency keys; modified records receive a new correction identity/payload hash and follow business-key update rules. Never overwrite old rejected-artifact history.

## 17. Observability and Batch Reporting

A useful dashboard shows where batches stand and why errors happen.

| Metric | Meaning |
|---|---|
| Messages received | Messages pulled from queue |
| Messages retried | Messages returned for retry |
| Files completed | Completed files |
| Files quarantined | Persisted file-level failures |
| Records processed | Processed records |
| Records rejected | Records with data errors |
| Quarantine write failures | Failures saving faulty artifacts |
| Oldest message age | Age of oldest queued message |
| Processing duration | File/batch processing duration |
| Duplicate jobs | Jobs recognized as duplicates |
| DLQ depth | Messages exceeding retry policy |
| Replay success rate | Percentage of completed replays |

Logs should include:

- `jobId` and `correlationId`.
- Normalized or hashed object key.
- Object version/checksum.
- SQS `messageId`.
- Row number.
- Reason code.
- Processor/schema version.
- Attempt number.
- Quarantine object key.

Avoid using high-cardinality `jobId`, object keys, or tenant IDs as metric labels. Use logs/traces for detailed drill-downs.

### 17.1. Reporting Results for a File

A manifest summary might look like:

~~~json
{
  "jobId": "job-8f2a",
  "source": {
    "bucket": "partner-ingestion",
    "key": "incoming/partner-17/orders.csv",
    "versionId": "3Lg...example",
    "sha256": "a4f2...example"
  },
  "status": "COMPLETED_WITH_ERRORS",
  "totalRecords": 1000,
  "succeededRecords": 975,
  "rejectedRecords": 25,
  "retryableFailures": 0,
  "rejectedObjectKey": "quarantine/partner-17/2026/11/17/job-8f2a/rejected-records.jsonl"
}
~~~

In this example, 970 records succeeded on the first pass and 5 transient-error records succeeded on retry, yielding 975 `succeededRecords`. Together with 25 rejected records, the outcome buckets sum to exactly 1,000 records. In real manifests, if files have headers, trailers, blank lines, or policy-skipped records, track separate counts for reconciliation.

## 18. Testing Partial Failures and Quarantine

Tests must cover both message-level and record-level behavior.

| Scenario | Expected Outcome |
|---|---|
| All messages and records valid | Empty `batchItemFailures` |
| One SQS message hits storage timeout | Only that message ID is returned for retry |
| File has malformed records | Faulty records saved to quarantine; valid records still processed |
| File has invalid header | Original quarantined and message acked after durable save |
| Quarantine storage timeout | Message fails for retry |
| Database timeout mid-file | Retry/chunk resume; already-committed records not duplicated |
| Function crashes after DB writes before ack | Redelivery produces no duplicate side effects |
| Duplicate object event | Job manifest/idempotency blocks duplicate work |
| Same key, different object version | Exact object version processed |
| Quarantine copy succeeds, manifest update fails | Safe retry without uncontrolled duplicates |
| Quarantined object emits new event | Triggers ignore the quarantine prefix |
| Mid-batch FIFO message fails | Order preserved; subsequent messages handled per FIFO policy |
| DLQ replay | Repaired data processed while preserving history |
| Payload contains PII | Logs omit raw data; quarantine enforces access control |

### 18.1. Failure Injection Testing

Simulate stopping the process at each point:

- After reading the file but before writing records.
- After writing some records but before checkpointing.
- After writing the rejected artifact but before updating the manifest.
- After updating the manifest but before the function returns.
- After quarantine copy but before deleting the source.
- After downstream commit but before ACKing the message.

At each point, replay the same event and verify zero data loss, zero duplication, and an accurate final manifest state.

## 19. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Throwing on any error in a batch | Valid messages retried alongside failing ones | Partial batch responses |
| ACKing before quarantine finishes writing | Faulty data lost | Ack only after durable write |
| Quarantining whole file for one bad row | Valid data discarded | Separate record-level rejection |
| Infinitely retrying data-invalid records | Queue backlog and costs spike | Route permanent errors to quarantine |
| Quarantining database timeouts | Valid data misclassified | Separate transient from permanent |
| In-memory deduplication only | Duplicates after cold starts/restarts | Durable manifests and idempotency |
| Using object key as sole job ID | Overwrites or misses new versions | Key + version/checksum |
| Moving objects assuming atomic rename | Can lose sources or leave half-states | Copy, verify, update manifest, then delete |
| Triggering on the entire bucket | Quarantined files re-trigger the pipeline | Prefix/bucket filters |
| Logging raw records | Leaks PII/secrets | Log reason codes and safe metadata |
| Oversized batches | Timeouts and memory exhaustion | Chunking, streaming, concurrency limits |
| Replaying without history | Unknown provenance and repair lineage | Replay job IDs and lineage |

## 20. Project Implementation Workflow

1. **Define input contracts.** Specify file formats, encoding, headers, schema versions, size limits, and record bounds.
2. **Choose event transport.** Object storage emits events via a queue for buffering and retries.
3. **Establish job identity.** Combine object key with version/checksum.
4. **Design manifests.** Store state, record counts, checkpoints, and artifact references.
5. **Classify errors.** Separate transient, invalid record, invalid file, and configuration failures.
6. **Build Java parser/validator.** Stream files, validate records independently, and emit stable reason codes.
7. **Build idempotent writer.** Give every record an idempotency key; keep business writes and markers consistent.
8. **Build quarantine writer.** Persist original files or rejected records with deterministic keys and metadata.
9. **Implement partial batch responses.** Return only messages needing retry; enable the matching event source mapping flag.
10. **Configure DLQ and retry policies.** Set retry caps, backoff, and alerts.
11. **Configure storage notifications.** Trigger only on the incoming prefix; exclude quarantine/archive.
12. **Test crashes/replays.** Verify side effects, checkpoints, quarantine, and acks at every failure point.
13. **Set up observability.** Monitor queue age, file statuses, rejected counts, and quarantine write failures.
14. **Implement replay workflow.** Enforce ownership, approvals, lineage, and idempotency policies.
15. **Operate under retention.** Retain files/quarantine per policy, restrict access, and purge on schedule.

## 21. Self-Check Questions

- Does an SQS partial batch response identify failures by `messageId` or row number?
- Why does message-level partial failure not automatically solve record-level failures inside a file?
- When should a message be retried vs. a record quarantined?
- What happens if a message is acked before the rejected artifact is durably persisted?
- Why should a database timeout not be classified as an invalid record?
- How should a file with a bad header be handled differently from a CSV row with a bad amount?
- How does quarantine differ from a DLQ in purpose and stored data?
- Why does job identity require object version or checksum?
- How do you prevent duplicate processing if a function crashes before acking?
- Why must object storage moves usually be performed as copy-then-delete?
- How do you prevent quarantined objects from re-triggering the processing function?
- When should you use one message per file vs. splitting into one message per record?
- Why do large files need chunking and checkpoints?
- What access control, encryption, and retention safeguards does quarantine require?
- Which crash points should be tested before deploying to production?
