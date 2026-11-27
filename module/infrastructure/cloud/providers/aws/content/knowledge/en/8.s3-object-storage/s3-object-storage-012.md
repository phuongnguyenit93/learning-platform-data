# S3 Event Notifications and Object Event Processing

> **Chapter:** S3 Object Storage  
> **Module:** CLOUD_PROVIDERS_AWS — explore the AWS ecosystem across Region/Availability Zone (AZ) infrastructure, IAM, VPC, compute, storage, databases, integration, and serverless; practice selecting services and designing secure, observable, recoverable, and cost-controlled applications.

## Learning Objectives

After this lesson, you will be able to:

1. Explain what **Amazon S3 Event Notifications** are, and how **object-change events** differ from S3 API data reads/writes.
2. List common event categories such as **ObjectCreated**, **ObjectRemoved**, cold-storage restores, lifecycle, and replication.
3. Compare destinations—**Amazon SQS, Amazon SNS, AWS Lambda**, and **Amazon EventBridge**—and choose between queues and event routers.
4. Think through configurations across **buckets, event types, prefix/suffix filters, destinations, IAM/resource-based policies**, and Regions.
5. Parse S3 message payloads, decode object keys properly, and handle **at-least-once** delivery, duplicate messages, and **no ordering guarantees**.
6. Build safe, resilient object-processing architectures that prevent **Lambda trigger loops**, enforce least privilege, and handle errors via retries/DLQs.
7. Inspect configurations with read-only AWS CLI commands, monitor via CloudWatch/CloudTrail, and evaluate cost and scalability.

## 1. Why Should Applications React When Objects Change?

Imagine a website where users upload images to Amazon S3. Once an upload succeeds, the system must generate thumbnails, validate formats, update metadata, or send notifications. If the app constantly asks S3 "are there any new files yet?":

- It generates excessive unnecessary `LIST`/`HEAD` API calls.
- Processing lags behind polling intervals.
- As object counts and upload rates scale up, tracking state and scan cursors gets complicated.

**S3 Event Notifications** let you configure S3 to emit **notifications for supported object events** to a processing target. For instance, after a valid `PutObject`, S3 emits metadata about the newly created object, and a worker uses that information to process the payload.

~~~mermaid
flowchart LR
    U["User"] -->|"Upload image"| S3[("S3 bucket: incoming/")]
    S3 -->|"ObjectCreated event"| Q["SQS queue"]
    Q -->|"Poll"| L["Lambda image worker"]
    L -->|"Write thumbnail"| OUT[("S3 output bucket")]
    L -->|"Update result"| DB[("DynamoDB / database")]
~~~

This diagram is a **reference architecture**. S3 sends *event metadata* to the queue; **the full object payload is not embedded inside the event**. The worker calls S3 APIs to retrieve the actual object.

### 1.1. Event-Driven vs. Polling

| Aspect | Polling | S3 Event Notifications |
| --- | --- | --- |
| Change detection | Worker actively lists and inspects objects. | S3 emits a message when configured events occur. |
| Latency | Tied to polling interval. | Usually delivered quickly, yet asynchronous with no ordering guarantees—never treat as strictly instantaneous. |
| System load | Generates requests even when no new data arrives. | Scales with object events; downstream still needs concurrency/rate controls. |
| Error handling | Worker tracks checkpoints and schedules re-scans. | Destinations/consumers need retries, deduplication, and recovery workflows. |
| Use cases | Periodic sweeps, reconciliation, inventories. | Image processing, ETL, search indexing, log pipelines. |

**Key point:** Event-driven does not mean you will **never need reconciliation**. For critical datasets, maintain reconciliation capabilities (such as S3 Inventory or batch sweeps where appropriate), monitor DLQs, and support replay when pipelines fail.

## 2. Which Events Does S3 Emit Notifications For?

Notifications are configured by **event type** groups. The names below represent common types, not the exhaustive list of supported APIs/features.

| Category | Illustrative Event Types | When Used |
| --- | --- | --- |
| **Object creation** | **s3:ObjectCreated:Put**, **:Post**, **:Copy**, **:CompleteMultipartUpload**, **s3:ObjectCreated:*** | Detect newly created/overwritten objects or completed multipart uploads. |
| **Object removal** | **s3:ObjectRemoved:Delete**, **:DeleteMarkerCreated**, **s3:ObjectRemoved:*** | Clean up related metadata, update search indexes, audit. |
| **Cold storage restore** | **s3:ObjectRestore:Post**, **:Completed**, **:Delete** where supported | Track restore initiation, completion, or expiration per storage class. |
| **Lifecycle** | **s3:LifecycleTransition**, **s3:LifecycleExpiration:*** | Track objects transitioned or expired by lifecycle rules. |
| **Replication** | **s3:Replication:*** and supported sub-events | Track failures or status changes in replication workflows. |
| **Related metadata changes** | Tagging, ACL, Intelligent-Tiering, or newer feature-specific events | Sync indexes or data governance workflows on relevant events. |

For example, selecting **`s3:ObjectCreated:*`** captures all creation methods in that group. If you subscribe only to **`s3:ObjectCreated:Put`**, a **multipart upload** emits **`ObjectCreated:CompleteMultipartUpload`** instead, causing the pipeline to silently miss large uploads.

### 2.1. Overwrite Events and Object Versions

An S3 object is identified by **bucket + key**; when Versioning is enabled on the bucket, writes assign a new **`versionId`**. An **`ObjectCreated`** event does not imply the key never existed previously.

Example:

1. A user uploads **`incoming/report.csv`**.
2. Seconds later, the user overwrites the same key **`incoming/report.csv`**.
3. The system can receive **two `ObjectCreated` messages** for the same key.
4. A worker calling **`GET bucket/key`** without specifying a version may read the **latest** version rather than the exact bytes tied to the first message.

When processing *every exact version* matters, enable Versioning by design and pass the event's **`versionId`** (when present) along with matching IAM/KMS permissions. Never assume every event carries a usable `versionId` on an unversioned bucket.

### 2.2. Deletion Events and Delete Markers

In a versioned bucket, `DELETE` does not always permanently erase data: it may insert a **delete marker**. **`ObjectRemoved:DeleteMarkerCreated`** must be handled differently from permanently deleting an object version.

For example, a search index may hide a document when its current version becomes a delete marker, while an audit system retains records of prior versions. Designs should distinguish **hiding from business queries**, **deleting a version**, and **lifecycle expiration**.

### 2.3. Does Every Bucket Operation Emit an Event?

No. Notifications cover **specific supported S3 event types**. Editing a bucket policy, modifying IAM, reading objects via `GetObject`, or changing bucket settings do not become **`ObjectCreated`/`Removed`** events.

To audit configuration changes or data-plane API calls, use **AWS CloudTrail** (enabling S3 data events explicitly where required). Never treat S3 Event Notifications as a complete audit trail for all AWS operations.

## 3. Event Notification Destinations

Direct S3 Event Notifications support specific destination types. **EventBridge** provides an additional ingestion and routing path.

| Destination | How It Works | Advantages | Considerations |
| --- | --- | --- | --- |
| **AWS Lambda** | S3 invokes the function directly. | Minimal components; convenient for simple, short-lived tasks. | Retries, concurrency limits, traffic-spike throttling; watch out for loops. |
| **Amazon SQS queue** | S3 sends messages to a queue; consumers poll. | Buffers traffic spikes, decouples producers/consumers, retries, DLQ, rate control. | Queue costs, visibility timeouts, duplicates, retention limits. |
| **Amazon SNS topic** | S3 publishes notifications to a topic for subscribers. | Fan-out to multiple independent subscribers. | Subscriber/policy and retry differences; topics are not pull-based backlog queues. |
| **Amazon EventBridge** | S3 sends events to the **default event bus** in the account/Region; rules route to targets. | Rich multi-field filtering, diverse targets, Step Functions/cross-account routing. | Manage rules/bus/targets/permissions and per-event routing costs. |

### 3.1. Direct S3 → Lambda

Use when workflows are simple, upload volume is predictable, and a dedicated buffering queue is unnecessary.

Example:

~~~mermaid
flowchart LR
    S3[("S3 incoming bucket")] -->|"ObjectCreated"| L["Lambda metadata validator"]
    L --> D[("DynamoDB metadata")]
~~~

Notes:

- Lambda requires a **resource-based policy** allowing **`s3.amazonaws.com`** to invoke the function, scoped by the bucket's **`SourceArn`** and **`SourceAccount`**.
- Lambda receives the event asynchronously; monitor failures and retries via Lambda async invocation metrics/destinations.
- Upload spikes can trigger high concurrent invocations; manage quotas, timeouts, downstream limits, and idempotency.
- If the function writes back into the triggering scope, it can create an **infinite invocation loop**.

### 3.2. S3 → SQS → Worker/Lambda

Use when upload volumes fluctuate sharply and you need buffering, controlled retries, and a DLQ.

~~~mermaid
flowchart LR
    S3[("S3 uploads")] -->|"S3 event"| Q["SQS Standard queue"]
    Q -->|"Lambda event source mapping"| L["Lambda worker"]
    L --> OUT[("Output bucket")]
    Q -.->|"Redrive after max receives"| DLQ["Dead-letter queue"]
~~~

**SQS stores event messages for consumers to process**—it does not put object payloads into the queue. Workers read **bucket/key/versionId** and call S3 APIs to fetch content.

Traditional direct S3 Event Notifications support **SQS Standard** queues; if a workflow requires **SQS FIFO**, AWS recommends routing **S3 → EventBridge → SQS FIFO** where integration conditions are met. Always verify current destination limits and capabilities before building.

**Queues absorb load spikes, not duplicates:** S3 can emit duplicate notifications, and SQS Standard can deliver the same message more than once. Consumers must be idempotent.

### 3.3. S3 → SNS → Multiple Subscribers

Ideal when a single new object must trigger multiple independent workflows—such as content moderation, thumbnail generation, and analytics indexing.

~~~mermaid
flowchart TB
    S3[("S3 incoming/")] --> SNS["SNS topic"]
    SNS --> Q1["SQS queue — thumbnail"]
    SNS --> Q2["SQS queue — antivirus"]
    SNS --> Q3["SQS queue — indexing"]
    Q1 --> L1["Worker 1"]
    Q2 --> L2["Worker 2"]
    Q3 --> L3["Worker 3"]
~~~

Each subscriber maintains its own retry policy and concurrency limits. If one worker stalls, the others continue uninterrupted. Verify **SNS topic policies**, subscriptions, SQS queue policies, and message delivery settings.

For SNS FIFO topics and direct S3 notification constraints, verify supported topic types; FIFO ordering needs typically use EventBridge/SQS FIFO or another AWS-supported pattern.

### 3.4. S3 → EventBridge → Multiple Targets

When EventBridge delivery is enabled on a bucket, S3 sends **supported S3 events** to the account/Region's **default event bus**; EventBridge rules then decide which events route to which targets.

~~~mermaid
flowchart TB
    S3[("S3 bucket")] --> EB["EventBridge default bus"]
    EB -->|"Event pattern: Object Created, prefix/field"| R1["Image rule"]
    EB -->|"Event pattern: Object Deleted"| R2["Audit rule"]
    R1 --> L["Lambda / Step Functions"]
    R2 --> Q["SQS / other target"]
~~~

EventBridge shines when you need:

- Filtering on fields beyond simple prefix/suffix matching.
- Routing to diverse targets such as Lambda, Step Functions, SQS, or cross-account event buses.
- Cross-account integration and policy-governed event routing.
- Decoupling event emission from consumer selection logic.

EventBridge events **do not share the same JSON envelope** as direct S3 notifications. Consumers must parse the EventBridge schema properly when extracting keys and fields.

## 4. End-to-End Flow from Upload to Completion

Suppose a user uploads an image to **`incoming/avatar-001.jpg`**.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Amazon S3
    participant Q as SQS Standard
    participant L as Lambda
    participant O as S3 output
    C->>S: PutObject incoming/avatar-001.jpg
    S-->>C: Upload succeeded
    S-->>Q: ObjectCreated notification (asynchronous)
    Q-->>L: Message batch (via event source mapping)
    L->>S: GetObject by bucket/key/version if present
    S-->>L: Image bytes
    L->>O: PutObject thumbnail/output
    L-->>Q: Processing succeeded; message deleted by mapping
~~~

### Key Control Checkpoints

1. **Client writes object:** requires `s3:PutObject` and matching encryption settings if enforced.
2. **S3 emits event:** bucket notification configuration must match event type, filter, and destination.
3. **Destination receives event:** queue/topic/function resource policy must allow S3 to send or invoke.
4. **Consumer reads data:** worker needs `s3:GetObject`, plus `kms:Decrypt` if encrypted with SSE-KMS.
5. **Consumer writes output:** `s3:PutObject` on the target output bucket/prefix, plus KMS permissions if required.
6. **Consumer marks completion:** ensure re-running on redelivered messages stays safe.
7. **Observability and recovery:** monitor queue backlog, failed invocations, DLQs, and replay paths.

**A successful upload does not mean downstream processing is complete.** S3 notifications are asynchronous. For critical workflows, persist processing states (`received`, `processing`, `completed`, `failed`) in a database or tracking store.

## 5. Anatomy of an S3 Event Notification

A direct notification sent to SQS/SNS/Lambda contains a **`Records`** array, where each record describes an event. Abbreviated example:

~~~json
{
  "Records": [
    {
      "eventVersion": "2.1",
      "eventSource": "aws:s3",
      "awsRegion": "ap-southeast-1",
      "eventTime": "2026-11-20T02:10:00.000Z",
      "eventName": "ObjectCreated:Put",
      "userIdentity": {
        "principalId": "EXAMPLE"
      },
      "requestParameters": {
        "sourceIPAddress": "203.0.113.10"
      },
      "responseElements": {
        "x-amz-request-id": "EXAMPLE-REQUEST"
      },
      "s3": {
        "s3SchemaVersion": "1.0",
        "configurationId": "incoming-images",
        "bucket": {
          "name": "example-incoming-images",
          "arn": "arn:aws:s3:::example-incoming-images"
        },
        "object": {
          "key": "incoming/avatar+one.jpg",
          "size": 120481,
          "eTag": "example-etag",
          "versionId": "example-version-id",
          "sequencer": "0065F0000000000000"
        }
      }
    }
  ]
}
~~~

*Data and IDs in the example are placeholders; do not assume every event includes the exact same subset of fields.*

| Field | Meaning | Coding Notes |
| --- | --- | --- |
| **Records** | Array of records; a single payload can hold multiple records. | Iterate over every record; never assume only index `0` exists. |
| **eventVersion** | S3 event schema version. | Check major version and ignore unknown fields for minor-version compatibility. |
| **eventSource** | Event source, typically **`aws:s3`**. | Filter on source if handlers receive mixed event types. |
| **eventName** | E.g., **`ObjectCreated:Put`**. | **Omits** the **`s3:`** prefix found in notification configuration types. |
| **awsRegion** | Region associated with the event. | Use for client/Region routing when needed. |
| **eventTime** | Event timestamp per schema. | Do not rely on it for strict global ordering across events. |
| **bucket.name / bucket.arn** | Associated bucket. | Validate the bucket against an allowlist. |
| **object.key** | Object key. | **Must URL-form-decode** before passing to S3 APIs. |
| **object.size / eTag** | Event metadata where present. | ETag is not always whole-object MD5; do not treat as a universal checksum. |
| **object.versionId** | Version ID when relevant and provided. | Handle missing or `"null"` values gracefully. |
| **object.sequencer** | Hex string for ordering events on the same key. | Never compare sequencers across different keys. |

### 5.1. Object Keys Are URL-Encoded

In traditional S3 notifications, **`object.key`** is **URL form encoded**. Spaces can appear as **`+`**. For example, if the real key is **`incoming/avatar one.jpg`**, the payload carries **`incoming/avatar+one.jpg`**.

In Python:

~~~python
from urllib.parse import unquote_plus

encoded_key = "incoming/avatar+one.jpg"
key = unquote_plus(encoded_key)
print(key)  # incoming/avatar one.jpg
~~~

Using **`unquote_plus`** for direct notification schemas handles both **`+`** for spaces and percent-encoded characters. Never decode multiple times; for other event schemas (like EventBridge), verify the exact encoding format before decoding.

### 5.2. `s3:TestEvent` Has a Different Shape

When configuring notifications to a destination, S3 may send a **test message** to verify delivery permissions. That test message **does not necessarily include a `Records` array like normal object events**.

Handlers must check payload structure gracefully instead of blindly accessing **`event["Records"][0]`** and crashing on test events.

### 5.3. SQS Messages Wrap S3 Events in an Envelope

When Lambda is triggered by **SQS**, the outer Lambda event looks like:

~~~json
{
  "Records": [
    {
      "messageId": "example-sqs-message-id",
      "eventSource": "aws:sqs",
      "body": "{\"Records\":[{\"eventSource\":\"aws:s3\",\"eventName\":\"ObjectCreated:Put\",\"s3\":{\"bucket\":{\"name\":\"example-incoming-images\"},\"object\":{\"key\":\"incoming%2Favatar.jpg\"}}}]}"
    }
  ]
}
~~~

The **`body`** field is a JSON string containing the S3 notification. With **S3 → SNS → SQS**, `body` can also wrap an SNS envelope whose **`Message`** field holds the S3 JSON. Always distinguish **SQS Records** from **S3 Records**.

### 5.4. EventBridge Events Use a Different Schema

An EventBridge event for an S3 object looks like (abbreviated):

~~~json
{
  "version": "0",
  "id": "example-event-id",
  "source": "aws.s3",
  "detail-type": "Object Created",
  "account": "111122223333",
  "time": "2026-11-20T02:10:00Z",
  "region": "ap-southeast-1",
  "resources": [
    "arn:aws:s3:::example-incoming-images"
  ],
  "detail": {
    "version": "0",
    "bucket": {
      "name": "example-incoming-images"
    },
    "object": {
      "key": "incoming/avatar.jpg",
      "size": 120481,
      "etag": "example-etag",
      "sequencer": "0065F0000000000000"
    },
    "request-id": "EXAMPLE-REQUEST",
    "reason": "PutObject"
  }
}
~~~

In EventBridge events, **`detail-type`** and **`detail.object`** replace **`Records[].eventName`** and **`Records[].s3.object`**. Never reuse a direct S3 notification parser without branching by schema.

## 6. Filtering Events by Prefix and Suffix

Not every object needs processing. Direct S3 notification configurations support filtering keys by **prefix** and **suffix** for supported notification targets.

Example:

- Only match objects under **`incoming/`**.
- Only match keys ending in **`.jpg`**.
- Event type **`s3:ObjectCreated:*`**.

~~~mermaid
flowchart LR
    B[("Bucket")] --> A{"ObjectCreated?"}
    A -->|"No"| X["Ignore"]
    A -->|"Yes"| P{"Key starts with incoming/?"}
    P -->|"No"| X
    P -->|"Yes"| S{"Key ends with .jpg?"}
    S -->|"No"| X
    S -->|"Yes"| Q["Send notification to queue"]
~~~

### 6.1. Sample JSON Matching the S3 API Format

Illustrative structure for the S3 API **`NotificationConfiguration`** parameter:

~~~json
{
  "QueueConfigurations": [
    {
      "Id": "incoming-jpg-events",
      "QueueArn": "arn:aws:sqs:ap-southeast-1:111122223333:image-processing-queue",
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
              "Value": ".jpg"
            }
          ]
        }
      }
    }
  ]
}
~~~

This is an **illustrative config example for learning structure**, not an operation on live resources. It only succeeds once the queue exists in a supported Region with a policy permitting S3 to send messages.

**Deployment warning:** **`PutBucketNotificationConfiguration` replaces the entire notification configuration** on the bucket with the submitted document. When using IaC or CLI, manage **all** active destinations together so you do not accidentally delete notifications configured by another team.

### 6.2. Overlapping Filter Rules

Within a single bucket, direct notification rules **must not have ambiguous overlapping prefix/suffix filters for the same event type**, per AWS rules.

For example, suppose you try to add two rules both matching **`ObjectCreated`**:

- Rule A: prefix **`incoming/`**, suffix **`.jpg`**.
- Rule B: prefix **`incoming/photos/`**, suffix **`.jpg`**.

Keys such as **`incoming/photos/a.jpg`** match both filters, so S3 rejects saving the configuration. Redesign disjoint prefixes or route via EventBridge for flexible multi-consumer filtering.

**Prefix/suffix filters use literal substring matching, not regex or globs.** Never put **`*`** into filter values as a wildcard; to match multiple extensions, define non-overlapping rules or use a router like EventBridge.

### 6.3. With EventBridge, Define Filters in Rules

When S3 emits events to EventBridge, use an **event pattern** to filter by source, detail-type, bucket, and object key.

Example rule matching only `Object Created` in **`example-incoming-images`** with keys starting with **`incoming/`**:

~~~json
{
  "source": ["aws.s3"],
  "detail-type": ["Object Created"],
  "detail": {
    "bucket": {
      "name": ["example-incoming-images"]
    },
    "object": {
      "key": [
        {
          "prefix": "incoming/"
        }
      ]
    }
  }
}
~~~

This is an EventBridge **event pattern**, distinct from **`NotificationConfiguration`** JSON in the S3 API. Rules can filter across many EventBridge-supported fields and conditions—verify actual event fields and schema behavior when testing.

## 7. At-Least-Once Delivery, Duplicates, and Ordering

**The most critical rule for S3 event pipelines:** notifications are delivered **at-least-once**; duplicate messages can arrive for a single operation, and **there is no ordering guarantee** across notifications.

Suppose a user overwrites **`incoming/report.csv`** three times:

- Event A occurs first, followed by Events B and C.
- Workers may receive **B, then A, then C**.
- Event B might arrive **twice**.
- A worker calling `GET` without a version ID might read C's payload even while processing Event A.

### 7.1. What Is Idempotency?

An **idempotent** operation produces the same intended business state even if executed multiple times for the same logical event.

Examples:

- Generating a deterministic thumbnail key from the exact source version → safe if output is deterministic and overwrites are controlled.
- Incrementing **`viewCount += 1`** on each event → **not idempotent** when duplicates arrive.
- Emailing an invoice to a customer on every event → sends duplicate emails without state tracking.
- Recording a payment or crediting a balance → requires application-level idempotency/transactions; never assume events arrive once.

### 7.2. Choosing an Idempotency Key

Depending on business needs:

| Goal | Suggested Key | Notes |
| --- | --- | --- |
| Process each object version exactly once logically | **bucket + key + versionId + job type** | Ideal when versioning is enabled and events carry usable `versionId`s. |
| Distinguish rapid successive changes on the same key | **bucket + key + sequencer + event type** | Sequencer appears on applicable PUT/DELETE events; check schema. |
| Deduplicate a business report | **business ID + workflow step** | Often better than infrastructure keys if identical files are re-uploaded. |
| Ensure thumbnails match exact source | **bucket + key + versionId + variant** | Generates deterministic output keys and prevents stale overwrites. |

Never rely solely on **SQS `messageId`** for S3 event deduplication if S3 can emit multiple messages for the same object change; each SQS message receives its own ID.

### 7.3. Using `sequencer` to Compare Events on the Same Key

For PUT/DELETE events carrying a **`sequencer`**, S3 provides a hex string usable to determine order **for changes on the same object key**. To compare two sequencers:

1. Compare only events sharing the exact same bucket, object key, and compatible event context.
2. If lengths differ, **left-pad with `0`** to equal length.
3. Compare lexicographically/hex-wise; the larger sequencer represents the later event for **that same key**.

Never use sequencers to establish order between **two different keys**. Not every event type includes a sequencer.

### 7.4. Race Conditions

If Worker X receives Event A first and Worker Y receives Event B second, yet X runs slower, X can overwrite Y's newer result with stale data.

Mitigations:

- With versioning, read the exact **`versionId`**.
- Persist the **latest processed sequencer/version** per bucket + key.
- Use conditional updates in DynamoDB or your database to **accept only newer states**.
- Include the input version in output keys or separate versioned outputs from a **`latest`** pointer.
- Limit per-key concurrency or introduce an orchestrator when strict sequential processing is mandatory.

**Beware marking "done" too early:** writing an idempotency marker before work finishes causes retries after crashes to skip incomplete work. Use **`PENDING`/`PROCESSING`/`COMPLETED`** states, leases/timeouts, or transactional outbox patterns.

## 8. Example Lambda Processing Events Directly

The Python snippet below demonstrates how to:

- Distinguish normal S3 events from test events.
- Decode object keys.
- Process only `ObjectCreated` events under **`incoming/`**.
- Write metadata to **a separate output bucket** to avoid loops.
- Derive deterministic output keys from key + version/sequencer for safe reprocessing.

This is a **flow illustration** without an atomic concurrency state store; production code must add atomic idempotency and failure testing.

~~~python
import json
import os
from urllib.parse import quote, unquote_plus

import boto3

s3 = boto3.client("s3")
OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]


def lambda_handler(event, context):
    # TestEvent or other non-record payloads may lack Records.
    records = event.get("Records", [])
    processed = 0

    for record in records:
        if record.get("eventSource") != "aws:s3":
            continue

        name = record.get("eventName", "")
        if not name.startswith("ObjectCreated:"):
            continue

        data = record["s3"]
        bucket = data["bucket"]["name"]
        obj = data["object"]
        key = unquote_plus(obj["key"])

        if not key.startswith("incoming/"):
            continue

        # Do not assume versionId exists or is never "null".
        version_id = obj.get("versionId")
        if version_id == "null":
            version_id = None

        read_args = {"Bucket": bucket, "Key": key}
        if version_id:
            read_args["VersionId"] = version_id

        # HEAD verifies permissions and object metadata.
        # If bucket is unversioned and the key is rapidly overwritten,
        # HEAD may reflect a newer object than the event being processed.
        source = s3.head_object(**read_args)

        revision = version_id or obj.get("sequencer") or "unversioned"
        safe_key = quote(key, safe="")
        out_key = f"manifests/{safe_key}/{quote(revision, safe='')}.json"

        manifest = {
            "sourceBucket": bucket,
            "sourceKey": key,
            "sourceVersion": version_id,
            "sourceETag": source.get("ETag"),
            "eventName": name,
        }

        s3.put_object(
            Bucket=OUTPUT_BUCKET,
            Key=out_key,
            Body=json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        processed += 1

    return {"processed": processed}
~~~

### 8.1. What Else Is Needed for Production?

- **Version consistency:** without versioning, delayed events can read overwritten bytes; choose latest-only or version-specific handling explicitly.
- **Atomic idempotency:** use conditional writes and completion states; prevent duplicate side effects such as emails or billing charges.
- **Least-privilege permissions:** read only the input bucket/prefix and write only the output bucket/prefix; avoid **`s3:*`**.
- **IAM/KMS:** grant the execution role CloudWatch Logs, S3, and required KMS permissions; grant S3 `lambda:InvokeFunction` if directly invoked.
- **Validation:** never trust file contents just because they sit in an internal bucket; validate size, format, parsers, and scan for malware.
- **Concurrency/timeouts:** tune memory, timeout, reserved concurrency, and retries for expected object sizes.
- **Loop prevention:** write outputs to a separate bucket or strictly enforce disjoint input prefix filters.
- **Auditing:** log bucket/key/version and correlation IDs while avoiding logging sensitive file payloads.

### 8.2. Why Use a Separate Output Bucket?

If a function processes **`incoming/photo.jpg`** and writes **`processed/photo.jpg`** **back into the same bucket** while the trigger listens to **`s3:ObjectCreated:*`** with no prefix filter, every output write triggers a fresh invocation.

~~~mermaid
flowchart LR
    S3["S3 bucket"] -->|"ObjectCreated"| L["Lambda"]
    L -->|"PutObject back into same bucket"| S3
~~~

This infinite loop rapidly burns compute, requests, and money. Using a **separate input bucket and output bucket** is the cleanest defense; if sharing one bucket, use disjoint prefix filters plus defensive prefix guards in code.

## 9. Retries, SQS Visibility Timeout, and DLQs

### 9.1. Why Do Queues Make Pipelines More Resilient?

Suppose 10,000 images arrive in a short burst while Lambda workers can process only 50 images/second.

With direct invocation, Lambda can hit concurrency limits or throttling, forcing async retries to absorb the spike. With SQS:

1. S3 pushes notifications into the queue.
2. The queue buffers the backlog within its retention window.
3. Workers pull batches at a sustainable pace.
4. Successfully processed messages are deleted.
5. Failed messages reappear after the **visibility timeout** and move to a **DLQ** once `maxReceiveCount` is exceeded.

### 9.2. Visibility Timeout Is Not Max Execution Time

**Visibility timeout** is how long a received message stays **hidden from other consumers**. If a worker takes longer than the visibility timeout, the message becomes visible again and another worker processes it concurrently, causing duplicate work.

With Lambda SQS event source mappings, set visibility timeout well above **function timeout, batch window, and retry overhead** per AWS guidance. Never treat a long visibility timeout as a substitute for idempotency.

### 9.3. Dead-Letter Queues (DLQs)

A **DLQ** captures messages that repeatedly fail past `maxReceiveCount`. It helps:

- Keep poison messages from stalling the rest of the pipeline.
- Diagnose root causes such as deleted objects, missing KMS rights, or corrupt images.
- Fix the issue and **redrive/reprocess** messages safely.

Set alarms whenever messages land in a DLQ and configure adequate retention for investigation. **Having an unmonitored DLQ** still quietly loses critical events.

### 9.4. Partial Batch Responses

When Lambda pulls an SQS batch of multiple messages, throwing an exception for one bad message causes the entire batch to retry.

AWS Lambda supports **partial batch responses** for SQS via **`ReportBatchItemFailures`**. The handler returns only the failed message IDs so successful items are deleted and only failures retry.

Example response format:

~~~json
{
  "batchItemFailures": [
    {
      "itemIdentifier": "failed-sqs-message-id"
    }
  ]
}
~~~

This response format belongs to **Lambda SQS event source mappings**, not direct S3 → Lambda invocations. When SNS/SQS wraps payloads or an SQS message carries multiple S3 records, define retry granularity and idempotency clearly.

### 9.5. Limits of Retries

If the source object has already been deleted or an unversioned version is gone, replaying the message fails permanently. You must:

- Configure appropriate retention and versioning.
- Separate transient errors (throttling, network) from permanent errors (unsupported file, unrecoverable 404).
- Route permanent errors to recorded failure states instead of retrying infinitely.
- Maintain a DLQ redrive or event-store replay workflow where appropriate.

## 10. Security, Permissions, and Regional Boundaries

### 10.1. Permission Layers to Distinguish

| Flow | Who Needs Permission? | Typical Permissions |
| --- | --- | --- |
| Manage bucket notifications | Deployment user/role | **`s3:GetBucketNotification`**, **`s3:PutBucketNotification`** on the bucket. |
| S3 sends to SQS | **`s3.amazonaws.com`** via queue resource policy | **`sqs:SendMessage`** on target queue. |
| S3 publishes to SNS | **`s3.amazonaws.com`** via topic policy | **`sns:Publish`** on target topic. |
| S3 invokes Lambda directly | **`s3.amazonaws.com`** via Lambda resource-based policy | **`lambda:InvokeFunction`** on function, scoped to source bucket. |
| Worker reads object | Worker execution role | **`s3:GetObject`** on bucket/object ARN, **`kms:Decrypt`** if SSE-KMS. |
| Worker writes output | Worker execution role | **`s3:PutObject`**, **`kms:GenerateDataKey`** or needed key permissions. |
| Lambda polls SQS | Lambda execution role | **`sqs:ReceiveMessage`**, **`sqs:DeleteMessage`**, **`sqs:GetQueueAttributes`**. |
| EventBridge invokes target | EventBridge service/rule role and target resource policy | `Invoke`/`Send`/`StartExecution` depending on target type. |

Authorizing **S3 to send to a queue/topic/function** is distinct from authorizing the **worker to read S3 objects**. A queue receiving events while Lambda fails to read S3 objects still breaks at the processing stage.

### 10.2. Sample SQS Queue Policy for S3

Illustrative queue policy allowing only S3 events from a specific bucket in the source account:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOnlyExampleBucketEvents",
      "Effect": "Allow",
      "Principal": {
        "Service": "s3.amazonaws.com"
      },
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:image-processing-queue",
      "Condition": {
        "ArnEquals": {
          "aws:SourceArn": "arn:aws:s3:::example-incoming-images"
        },
        "StringEquals": {
          "aws:SourceAccount": "111122223333"
        }
      }
    }
  ]
}
~~~

**`SourceArn`** and **`SourceAccount`** prevent resources in other accounts from abusing the `s3.amazonaws.com` service principal. Real policies must use exact bucket ARNs, account IDs, queue ARNs, and required service conditions.

**Buckets do not need to be public for S3 to send messages to SQS.** Public bucket access is an unrelated data-exposure setting inappropriate for sensitive user uploads.

### 10.3. SSE-KMS Encryption

If an SQS queue or SNS topic is encrypted with a **customer managed KMS key**, the KMS key policy must allow `s3.amazonaws.com` to use actions such as **`kms:GenerateDataKey`** and **`kms:Decrypt`** per destination integration guidance. AWS managed keys for queues/topics do not always allow editing key policies for service integrations.

If the source S3 object uses **SSE-KMS**, the worker reading the object also needs KMS permissions on that object's key. Note these are **two different keys**:

- The KMS key encrypting **SQS/SNS notification messages**.
- The KMS key encrypting the **S3 objects** read and written by the worker.

Scope KMS permissions to exact keys, roles, and conditions rather than account-wide wildcards.

### 10.4. Regions and Cross-Account Routing

For **direct notification destinations**, AWS requires **Regional alignment** between the S3 bucket and targets like Lambda/SNS/SQS. To forward events to another Region or account, design a supported path using EventBridge/SNS/SQS with matching resource policies.

**Cross-account delivery does not work merely by knowing an ARN.** Both destination resource policies and source/target account governance must permit it.

For example, EventBridge can route events to an event bus in another account with matching rules, roles, and bus policies. For cross-Region routing, verify supported routes, target delivery, and inter-Region event transfer pricing.

### 10.5. Least Privilege and Data Protection

For an image-processing pipeline:

- Uploaders only hold write access to the incoming prefix (e.g., via scoped presigned URLs).
- Workers only read the designated input prefix.
- Workers only write to the output prefix/bucket.
- Metadata DB access is scoped strictly to required tables/records.
- CloudWatch Logs record operational diagnostics without logging raw file payloads or unnecessary PII.
- Bucket policies, Block Public Access, encryption at rest/in transit, versioning, and lifecycle rules are reviewed independently.

S3 Event Notifications are **not an authorization mechanism**; an event indicates an S3 action occurred, yet workers must still validate object integrity and business rules before processing.

## 11. Inspecting Configurations via AWS CLI (Read-Only)

These commands do not create, modify, delete, or invoke workflows. Ensure the AWS CLI is configured for the right account/Region with read permissions, and replace placeholder names/IDs with authorized resources.

### 11.1. Check Caller Identity

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

Each S3 bucket lives in a specific Region; inspect associated destinations in their corresponding Regions.

### 11.2. Inspect Bucket Notification Configuration

~~~bash
aws s3api get-bucket-notification-configuration \
  --bucket example-incoming-images
~~~

Inspect these fields:

- **`LambdaFunctionConfigurations`**: function ARN, `Events`, and `Filter`.
- **`QueueConfigurations`**: queue ARN, `Events`, and `Filter`.
- **`TopicConfigurations`**: topic ARN, `Events`, and `Filter`.
- **`EventBridgeConfiguration`**: whether EventBridge delivery is enabled.

If `{}` is returned or a destination array is absent, that notification type is not configured. If `AccessDenied` occurs, check read permissions rather than assuming no notifications exist.

### 11.3. Inspect Bucket Versioning

~~~bash
aws s3api get-bucket-versioning \
  --bucket example-incoming-images
~~~

Check **`Status`** (`Enabled`, `Suspended`, or absent) to design idempotency properly. Suspended versioning creates `null` versions with distinct overwrite behavior; never assume every object carries a usable unique `versionId`.

### 11.4. Inspect Queue and DLQ Attributes

~~~bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/image-processing-queue \
  --attribute-names QueueArn Policy VisibilityTimeout RedrivePolicy ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
  --region ap-southeast-1
~~~

**`ApproximateNumberOfMessages`** estimates backlog depth; **`ApproximateNumberOfMessagesNotVisible`** estimates in-flight hidden messages, not completed work. Verify **`VisibilityTimeout`**, **`RedrivePolicy`**, DLQ ARN, and queue policy.

### 11.5. Inspect Lambda Policy and Mapping

~~~bash
aws lambda get-function-configuration \
  --function-name image-worker \
  --region ap-southeast-1

aws lambda get-policy \
  --function-name image-worker \
  --region ap-southeast-1

aws lambda list-event-source-mappings \
  --function-name image-worker \
  --region ap-southeast-1
~~~

For **direct S3 → Lambda**, inspect **`get-policy`** for S3 invoke permission. For **S3 → SQS → Lambda**, inspect **`event-source-mappings`**, SQS permissions on the execution role, and partial batch failure settings. Resource policies and event source mappings are separate mechanisms.

### 11.6. Inspect EventBridge Rules and Targets

~~~bash
aws events list-rules \
  --event-bus-name default \
  --region ap-southeast-1

aws events describe-rule \
  --name process-s3-objects \
  --event-bus-name default \
  --region ap-southeast-1

aws events list-targets-by-rule \
  --rule process-s3-objects \
  --event-bus-name default \
  --region ap-southeast-1
~~~

Not every rule on the default bus relates to S3. Inspect **`EventPattern`** for source **`aws.s3`**, `detail-type`, and bucket filters, and confirm **`get-bucket-notification-configuration`** shows EventBridge delivery enabled.

### 11.7. Read S3 Object Metadata

~~~bash
aws s3api head-object \
  --bucket example-incoming-images \
  --key incoming/example.jpg

aws s3api list-object-versions \
  --bucket example-incoming-images \
  --prefix incoming/example.jpg \
  --max-items 20
~~~

`head-object` without `VersionId` inspects the **current version**, which may be newer than an older notification. If a worker must inspect an exact historical version, pass the event's `versionId` (where versioning retains it and permissions allow).

## 12. Monitoring and Troubleshooting

### 12.1. Key Signals to Monitor

| Component | Signals | Usage |
| --- | --- | --- |
| S3 | Upload/PUT success, notification config, CloudTrail data events (if enabled). | Confirm the object actually landed in the right bucket. |
| SQS | Queue depth, `AgeOfOldestMessage`, `NumberOfMessagesSent`/`Received`/`Deleted`, DLQ depth. | Detect backlogs, failing consumers, and throughput imbalances. |
| Lambda | `Invocations`, `Errors`, `Duration`, `Throttles`, `ConcurrentExecutions`, async failures. | Identify handler bugs, timeouts, and concurrency caps. |
| SNS | Published/Delivered/Failed notifications per protocol. | Spot failing subscriber deliveries. |
| EventBridge | `MatchedEvents`/`Invocations`/`FailedInvocations` and target DLQ (if set). | Diagnose pattern mismatches, permission errors, and target failures. |
| Worker/app | Bucket/key/version, processing status, data errors, output results. | Trace business impact and coordinate replays. |

CloudWatch metrics, CloudTrail, and logs are only useful when properly configured and permissioned. **CloudTrail data events for S3 objects must be explicitly enabled**—never assume every `ObjectCreated` call is logged in default audit trails.

### 12.2. No Event Appears After Upload

Check in order:

1. Did the upload truly succeed into the expected **bucket and key**?
2. Does **`get-bucket-notification-configuration`** include the right event type? Are multipart uploads captured by **`ObjectCreated:CompleteMultipartUpload`** or **`ObjectCreated:*`**?
3. Do prefix/suffix filters match the exact key (case-sensitive)?
4. Are the destination ARN, Region, and resource policy accurate?
5. For SSE-KMS encrypted SQS/SNS, does the KMS key policy allow S3 to use the key?
6. If using EventBridge, is EventBridge delivery enabled on the bucket and do the rule pattern and targets match?
7. Inspect test messages, queue metrics, Lambda metrics, EventBridge metrics, and allow for asynchronous propagation delay.

**Never fix missing events by making the S3 bucket public.** S3 → destination delivery is governed by destination resource policies, not bucket public access.

### 12.3. Events Sit in SQS, Yet Lambda Is Not Processing Them

Verify:

- The event source mapping is **`Enabled`** and points to the exact queue.
- The execution role has permission to poll and delete messages.
- The function isn't failing due to timeouts, memory limits, concurrency limits, or missing environment variables.
- Queue `VisibilityTimeout` fits the function runtime and batch window.
- The parser unwraps the **SQS `body`** JSON to reach the S3 event.
- If the queue uses KMS encryption, the Lambda execution role has KMS permissions.
- Check whether messages moved to the DLQ and verify alarms.

Rising queue depth signals ingestion outpacing processing or failing workers. Increasing Lambda concurrency can boost throughput, but can also overwhelm downstream S3 APIs, databases, or services.

### 12.4. Lambda Infinite Invocation Loop

Symptom: invocations skyrocket right after deploying a thumbnail job, continuously generating new output objects.

Typical cause: the notification triggers on objects the function **writes back into the source bucket**. Fix:

1. Pause or throttle the loop using authorized operational controls.
2. Move outputs to a **separate bucket** or a prefix excluded from the trigger filter.
3. Add defensive prefix/format guards inside handler code.
4. Audit the notification config and clean up unintended generated objects.
5. Review logs and Lambda/S3/SQS charges, and add automated tests to prevent regressions.

### 12.5. The Same Event Is Processed Twice

This is **expected behavior under at-least-once delivery**, not necessarily an S3 bug. Check idempotency state, `sequencer`/`versionId`, retries, visibility timeout, and queue receive counts. If non-idempotent side effects occur, fix processing logic with conditional state/transactions rather than hoping duplicates stop arriving.

### 12.6. Event A Is Processed After Event B

Under rapid overwrites to the same key, delivery order is not guaranteed. Solve using `sequencer` comparisons on eligible events, version-specific processing, and conditional state writes.

Never rely on **`eventTime`** to establish reliable global ordering across multiple keys or services.

## 13. Costs, Limits, and Scaling

Event pipelines incur charges across multiple services even though each notification message is tiny.

| Component | Costs to Estimate | Cost Controls |
| --- | --- | --- |
| S3 | `PUT`/`GET`/`HEAD`/`LIST`, storage, transfer, versioning/lifecycle. | Filter events tightly, avoid redundant `HEAD`/`GET` calls, pick right storage classes. |
| SQS | API requests, payload volume, DLQ/backlog storage. | Use batching, long polling, and sensible retention. |
| SNS | Publish/delivery fees per protocol and traffic volume. | Avoid unnecessary fan-out and duplicate subscriptions. |
| Lambda | Invocations, duration/GB-seconds, concurrency, logs, retries. | Tune memory/runtime, batch size, and concurrency caps. |
| EventBridge | Events/target deliveries, rules/pipes/archives/replays per config. | Write selective patterns; avoid redundant rules/targets. |
| KMS | Key/API call volume when encryption is integrated. | Evaluate request counts and S3 Bucket Keys where relevant. |
| Monitoring | CloudWatch Logs, metrics, CloudTrail data events, log retention. | Log only fields needed for diagnostics; avoid logging raw payloads. |

For example, 1 million images/day can generate 1 million or more event deliveries (due to retries/duplicates), plus worker `HEAD`, `GET`, and `PUT` calls. Never estimate total pipeline requests from **new object count alone**.

### 13.1. Sample Capacity Calculation

Suppose average load is **120 objects/minute**, and each worker handles **1 object in 2 seconds**:

- One worker handles roughly **30 objects/minute** under ideal conditions.
- Keeping up with 120 objects/minute requires roughly **4 concurrent workers**, before overhead, variance, and retries.
- Surviving a 10x traffic spike requires queue buffering and scaling/concurrency headroom.

This is a **theoretical capacity estimate**. Real bottlenecks also arise from networking, object size, SDKs, Lambda concurrency quotas, databases, KMS, and downstream services. Measure live traffic and alarm on backlog age.

### 13.2. Limits to Verify

- Supported S3 bucket types, event types, and destinations; specialized buckets like **directory buckets / S3 Express One Zone** differ from general purpose buckets.
- Regional and cross-account permissions.
- Quotas on notification rules/filters and Lambda/SQS/SNS/EventBridge quotas.
- Target limits and FIFO capabilities where ordering is required.
- Timeouts, message retention, and payload size limits across each service.
- Overlapping filter restrictions and full-config replacement behavior on bucket notification updates.

When scaling for production, consult **Service Quotas** and Regional documentation rather than relying on memorized fixed numbers.

## 14. Real-World Scenarios

### Scenario A — Generating User Image Thumbnails

**Requirement:** App accepts JPG/PNG images, generates thumbnails asynchronously after upload, and updates asset URLs.

**Reference design:**

1. Users upload into **`uploads-original/`** via authorized API/role/presigned URLs.
2. S3 emits `ObjectCreated` to **SQS Standard** filtered by input prefix and image extensions.
3. Lambda parses the event, URL-decodes the key, validates file type/size, and fetches the exact version if versioned.
4. Lambda writes thumbnails to a **separate output bucket**, keying outputs by source version and variant.
5. Worker updates the database conditionally so retries never create duplicate metadata.
6. Monitor queue backlog, DLQ, Lambda errors, and output image quality.

**Takeaway:** Use queues to absorb bursts, separate input/output buckets to prevent recursion, and design for idempotency because duplicates are normal.

### Scenario B — Ingesting CSVs into a Data Lake

**Requirement:** Every new CSV under **`landing/`** must undergo schema validation and trigger ETL.

**Design:** S3 EventBridge delivery → rule matching `Object Created` on bucket/prefix → Step Functions or queue/worker; workflow validates schema, tracks job status, and routes failures to DLQ/error queues. For large batches or heavy compute, hand off to ECS, AWS Glue, or AWS Batch.

**Takeaway:** An S3 event does **not** guarantee valid business data. Schema validation, versioning, retries, idempotency, and auditing remain the application's responsibility.

### Scenario C — Updating a Search Index

**Requirement:** Index documents on upload and remove them from search results upon deletion.

**Design:** Subscribe to **`ObjectCreated`** and **`ObjectRemoved`**, store state keyed by bucket/key/version or latest sequencer, and update the search index conditionally so delayed older events never overwrite newer state.

**Takeaway:** Without ordering guarantees, naive "last arrival wins" indexing leads to stale or ghost search entries.

### Scenario D — Multiple Teams Sharing One Bucket

**Requirement:** Thumbnail, Compliance, and Analytics teams all need events from the same bucket.

**Design:** S3 → SNS fanning out to per-team SQS queues, or S3 → EventBridge with per-team rules, managed with clear ownership, IAM, logging, and DLQs. Never let individual teams independently call **`PutBucketNotificationConfiguration`** and overwrite each other's rules.

**Takeaway:** Centralized fan-out routing and configuration ownership let consumer teams evolve independently.

### Scenario E — Continuously Overwritten Input Files

**Requirement:** **`report.csv`** is re-uploaded frequently; only outputs from the latest version should be displayed.

**Design:** Enable S3 Versioning where appropriate, process by `versionId`, use `sequencer` for same-key PUT/DELETE ordering where available, and update the `"latest"` pointer conditionally by comparing version/sequencer. Workers finishing old events can still store versioned outputs without rolling back the `"latest"` pointer.

**Takeaway:** Never equate worker completion order with object creation order.

## 15. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| "S3 delivers events strictly once." | S3 Event Notifications use **at-least-once** delivery and can duplicate; workers must be idempotent. |
| "S3 preserves upload order in notifications." | Notifications have no ordering guarantee; `sequencer` only helps order eligible events on the **same key**. |
| "`ObjectCreated` events include the full file." | Events carry metadata; workers call S3 APIs to fetch payload bytes. |
| "The payload `eventName` is `s3:ObjectCreated:Put`." | In notification records, `eventName` is **`ObjectCreated:Put`** (without the `s3:` prefix). |
| "Keys in events can be passed directly without decoding." | Direct S3 notifications URL-form-encode keys (e.g., spaces become `+`). |
| "Selecting `ObjectCreated:Put` catches all uploads." | Completed multipart uploads emit **`CompleteMultipartUpload`**; choose the broader event group as needed. |
| "Writing Lambda outputs back to the same bucket is always safe." | Can trigger infinite loops if output keys match trigger filters. |
| "SQS eliminates duplicate processing." | SQS Standard still allows duplicate/redelivered messages; queues primarily buffer and manage retries. |
| "No DLQ is needed because Lambda retries automatically." | Retries are bounded and can exhaust; DLQs, monitoring, and recovery remain essential. |
| "A bucket must be public to send events to SQS." | S3 sends via service principal authorized by queue/topic/function policies; public buckets are unrelated. |
| "Lambda's IAM execution role is enough for S3 to invoke it." | Lambda needs a **resource-based policy** granting S3 invoke rights; the execution role governs code inside Lambda. |
| "EventBridge uses the same `Records[]` schema as S3 notifications." | EventBridge uses a different `source`/`detail-type`/`detail` schema. |
| "S3 events are already captured in CloudTrail by default." | CloudTrail S3 data events must be explicitly configured; notifications do not replace auditing. |
| "Enabling versioning removes the need for idempotency." | Versioning identifies versions, yet does not stop duplicate processing or repeated side effects. |
| "Once S3 stores the file, image processing is done." | Notifications and downstream processing are asynchronous and can lag or fail. |
| "Any consumer team can edit notification config safely on its own." | Updating notification configuration can overwrite the bucket's entire rule set. |

## 16. Self-Check Questions

**Question 1.** Once an object upload succeeds, is Lambda guaranteed to have finished processing it immediately?  
**Answer:** No. S3 notifications and downstream pipelines are asynchronous; track processing state separately.

**Question 2.** Why must pipelines handle duplicate events?  
**Answer:** S3 Event Notifications use at-least-once delivery and can redeliver events, and SQS Standard can also deliver messages more than once.

**Question 3.** Which event type captures objects uploaded via multipart upload?  
**Answer:** **`s3:ObjectCreated:CompleteMultipartUpload`** or **`s3:ObjectCreated:*`** depending on requirements.

**Question 4.** From a direct S3 notification record, how do you recover the exact key **`incoming/photo one.jpg`**?  
**Answer:** Read **`record.s3.object.key`** and URL-form-decode it, e.g., using Python's **`unquote_plus`**.

**Question 5.** Can you use `sequencer` to compare Object A against Object B with a different key?  
**Answer:** No. `sequencer` only orders eligible PUT/DELETE events for the **same key**.

**Question 6.** Where should a thumbnail worker write outputs to avoid infinite loops?  
**Answer:** Preferably to a separate output bucket, or to an output prefix excluded from trigger filters with defensive code guards.

**Question 7.** When S3 sends notifications to an SSE-KMS encrypted SQS queue, what additional permissions are needed?  
**Answer:** A queue resource policy granting **`sqs:SendMessage`** to S3 and a KMS key policy allowing S3 to use the key per documentation.

**Question 8.** When messages pile up in SQS, does SQS automatically process the S3 objects?  
**Answer:** No. Queues only hold and deliver metadata messages; Lambda or another consumer must poll and call S3 APIs.

**Question 9.** With EventBridge, where do you filter keys by prefix?  
**Answer:** In the EventBridge rule's event pattern on **`detail.object.key`**, alongside `source`, `detail-type`, and bucket filters.

**Question 10.** Why shouldn't you use SQS `messageId` as your sole S3 deduplication key?  
**Answer:** The same logical S3 event can generate or deliver multiple SQS messages with distinct IDs; key deduplication on object/version/sequencer or business IDs.

**Question 11.** If a key is overwritten after an older event was emitted and the bucket is unversioned, what does a worker calling `GET` receive?  
**Answer:** Typically the current object state, which may be newer than the event; pre-overwrite bytes cannot be reliably recovered.

**Question 12.** What is the main difference between S3 → Lambda and S3 → SQS → Lambda?  
**Answer:** Adding SQS provides durable buffering/backlog, visibility timeouts, DLQs, and rate control, at the cost of managing queue settings and queue fees.

**Question 13.** If multiple teams need the same events with centralized routing, what should you consider?  
**Answer:** SNS fan-out or EventBridge rules/targets, typically feeding dedicated per-team consumer queues with clear permissions and monitoring.

**Question 14.** Why don't S3 notifications replace CloudTrail?  
**Answer:** Notifications cover only supported and configured object events, whereas API/config/data-plane auditing has distinct scope, mechanisms, and compliance guarantees.

**Question 15.** What are the most important checks when notifications fail to arrive?  
**Answer:** Verify the upload succeeded, event type, prefix/suffix filters, Region/destination ARN, resource policies/KMS, EventBridge rules if used, and then check queue/Lambda/metrics/logs.

## 17. Key Takeaways

**S3 Event Notifications** bridge object storage with event-driven and serverless architectures. S3 emits **metadata about object changes** to Lambda, SQS, SNS, or EventBridge so systems can automate image processing, document pipelines, ETL, indexing, and other workflows.

Strong designs address five pillars:

1. **Right events:** choose exact event types, buckets, prefix/suffix filters, or EventBridge patterns.
2. **Right destination:** direct Lambda for simple tasks, SQS for buffering/recovery, SNS for fan-out, EventBridge for flexible routing.
3. **Right permissions:** bucket notification config, destination resource policies, IAM execution roles, KMS key policies, and Regions.
4. **Fault tolerance:** handle at-least-once delivery, duplicates, out-of-order events, versioning/sequencers, retries/DLQs, and testable idempotency.
5. **Operations:** prevent output-write loops, monitor backlogs/Errors/DLQs, test replays, and estimate costs across the entire pipeline.

When building real AWS systems, treat **object stored**, **event emitted**, **worker succeeded**, and **business state updated** as distinct states tracked independently. That discipline keeps applications secure, resilient, scalable, and cost-controlled.

### AWS Reference Documentation

- [Amazon S3 Event Notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventNotifications.html) — Concepts, event types, and destinations.
- [Event notification types and destinations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-how-to-event-types-and-destinations.html) — Event types, targets, and conditions.
- [Event message structure](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-content-structure.html) — `Records` schema, key encoding, and `sequencer`.
- [Configuring event notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/enable-event-notifications.html) — Setup and testing.
- [Filtering event notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-how-to-filtering.html) — Prefixes, suffixes, and overlap rules.
- [Granting permissions to publish messages](https://docs.aws.amazon.com/AmazonS3/latest/userguide/grant-destinations-permissions-to-s3.html) — Policies for SQS, SNS, Lambda, and KMS.
- [Using EventBridge with Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventBridge.html) — Routing S3 events to EventBridge.
- [Process Amazon S3 event notifications with Lambda](https://docs.aws.amazon.com/lambda/latest/dg/with-s3.html) — Lambda triggers and recursion safeguards.
- [Lambda with SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html) — Batching, visibility timeouts, partial failures, and retries.
