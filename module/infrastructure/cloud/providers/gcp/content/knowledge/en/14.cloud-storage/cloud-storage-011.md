# Cloud Storage Notifications and Object Events

An e-commerce platform lets customers upload product images. Files are written to **Cloud Storage** by a Java application, yet thumbnail generation, format validation, and catalog updates should not run synchronously inside the upload request: those tasks can be slow, fail, or need retries. Instead, Cloud Storage emits notifications when new objects arrive, and an event-driven service receives those notifications to process files asynchronously.

**Cloud Storage notifications** connect object changes to **Pub/Sub**, triggering Cloud Run, GKE/Compute Engine workers, Dataflow, or other services. Within the **CLOUD_PROVIDERS_GCP** module, this topic in the **Cloud Storage** chapter connects project design, IAM, VPCs, release automation, fault tolerance, and cost management. This lesson focuses on **Pub/Sub notifications for object changes**, while also contrasting them with Eventarc and other integration options.

After this lesson, you will be able to:

- Describe the Cloud Storage bucket → Pub/Sub topic → subscription → consumer architecture.
- Distinguish `OBJECT_FINALIZE`, `OBJECT_DELETE`, `OBJECT_ARCHIVE`, `OBJECT_METADATA_UPDATE`, and `OBJECT_INITIALIZE` for zonal buckets.
- Parse `bucketId`, `objectId`, `objectGeneration`, `eventTime`, and notification payloads.
- Create a notification configuration with `gcloud storage`, configure IAM properly for the Cloud Storage service agent, and receive events via Pub/Sub.
- Handle **at-least-once**, potentially duplicate, and **unordered** event delivery using idempotent consumers.
- Compare Pub/Sub notifications with direct Eventarc triggers to Cloud Run.
- Design retries, dead-letter handling, observability, data security, and cost estimation.

> **Lab Note:** Project IDs, buckets, topics, and filenames in examples are placeholders. Commands creating resources or uploading data may incur Cloud Storage/Pub/Sub/Cloud Run charges. Run only in an authorized lab project; never modify notification configurations on a production bucket without inventorying existing consumers.

## 1. When Should You Emit Object Events?

Objects in Cloud Storage have a **name (object name)**, byte content, metadata, and a **generation**. Common changes include:

- Uploading a new object, e.g., `incoming/photo-001.jpg`.
- Re-uploading the same object name, creating a new **generation**.
- Deleting an object or turning the live generation into noncurrent under Object Versioning.
- Updating metadata (such as `contentType` or custom metadata) without changing bytes.
- Copying, rewriting, or restoring an object to create a new generation.

Many workloads should not run synchronously inside the upload path:

| Need | Event to Use | Consumer |
| --- | --- | --- |
| Generate thumbnails when an image upload succeeds | `OBJECT_FINALIZE` | Cloud Run worker / function |
| Extract text from PDFs | `OBJECT_FINALIZE` with `documents/` prefix | Java worker, Dataflow |
| Remove search index records when a file is permanently deleted | `OBJECT_DELETE` | Search indexing service |
| Record when a version becomes noncurrent | `OBJECT_ARCHIVE` | Audit/cleanup workflow |
| Sync metadata into a catalog | `OBJECT_METADATA_UPDATE` | Metadata indexer |
| Track upload start in a zonal bucket | `OBJECT_INITIALIZE` (specialized case) | Zonal-bucket-compatible pipeline |

**Do not treat a notification as the actual file content.** Notifications mainly deliver event attributes and metadata; consumers fetch **object bytes** via the Cloud Storage API when actually needed. Seeing an object name in a notification does not mean the consumer holds permission to read that object.

## 2. Pub/Sub Notifications Architecture

~~~mermaid
flowchart LR
    A["Uploader: Java / GKE / Cloud Run"] --> B["Cloud Storage bucket"]
    B --> C["Notification configuration"]
    C --> D["Pub/Sub topic"]
    D --> E["Pull subscription"]
    D --> F["Push subscription"]
    E --> G["Java worker on VM/GKE/Cloud Run"]
    F --> H["Cloud Run HTTP handler"]
    G --> I["Cloud Storage read + processing + DB"]
    H --> I
~~~

A **notification configuration** attached to a bucket specifies:

1. Target Pub/Sub topic, which can reside in **another project** given proper permissions.
2. Which event types are emitted (or all supported event types if omitted).
3. Optional **object name prefix** to emit only when object names start with the chosen string.
4. Payload format: `JSON_API_V1` or `NONE`.
5. Custom attributes attached to every message.

The **topic** holds the message stream for **subscriptions**. One topic can feed multiple independent subscriptions, each using pull or push. If two services both need every event, create **two subscriptions** (not just two workers sharing one subscription) so each service receives its own copy of the event stream.

Do not confuse:

- **Bucket notification configuration**: routes bucket events to a topic; has no application-level acknowledgment mechanism.
- **Pub/Sub subscription**: defines how consumers pull/receive, retry, ack, and retain messages.
- **Consumer**: performs business logic; must tolerate duplicate, delayed, or out-of-order messages.

### Timeline of a Single Upload

~~~text
T0  Client uploads incoming/photo.jpg
T1  Cloud Storage successfully creates a new generation
T2  Notification configuration emits OBJECT_FINALIZE to the Pub/Sub topic
T3  Subscription delivers the message to a worker
T4  Worker reads the exact generation, generates thumbnail, and records status
T5  Worker successfully acks the message
~~~

T2–T3 is usually fast, yet **there is no SLA on notification delivery latency**; noticeable delays can occur. Never build an HTTP upload endpoint that promises users processing finished within a few seconds.

## 3. Event Types and Trigger Conditions

| Event Type | When Does It Occur? | Example | What Not to Assume |
| --- | --- | --- | --- |
| `OBJECT_FINALIZE` | A new object generation is successfully created, including upload, copy/rewrite/restore | Upload a new version of `photo.jpg` | Never emitted for failed uploads |
| `OBJECT_METADATA_UPDATE` | Metadata of an existing generation changes | Update `contentType` or custom metadata | Does not mean payload bytes changed |
| `OBJECT_DELETE` | An object generation is **permanently** deleted per Pub/Sub notifications semantics | Hard-delete generation / lifecycle delete | Does not cover every archive/versioning action |
| `OBJECT_ARCHIVE` | A live generation becomes **noncurrent** when Object Versioning is enabled | Overwriting same name makes old version noncurrent | Not permanent data deletion |
| `OBJECT_INITIALIZE` | Object creation starts in a **zonal bucket** under specialized support | Starting an upload to a zonal bucket | Not upload completion; never trigger downstream processing expecting ready bytes |

**CLI note:** Reference docs for `gcloud storage buckets notifications create --event-types` currently list the four primary types `OBJECT_FINALIZE`, `OBJECT_METADATA_UPDATE`, `OBJECT_DELETE`, and `OBJECT_ARCHIVE`. `OBJECT_INITIALIZE` appears in overview docs for **zonal buckets**; verify specific API/client support before configuring it.

### Same-Name Overwrite: Why Multiple Events Fire

Suppose `images/avatar.jpg` has generation `100`, and an app uploads a new copy creating generation `101`.

| Bucket Mode | Event for New Generation | Event for Old Generation |
| --- | --- | --- |
| **Without Object Versioning** | `OBJECT_FINALIZE` for `101` | `OBJECT_DELETE` for `100` when the old version is permanently replaced/deleted |
| **With Object Versioning** | `OBJECT_FINALIZE` for `101` | `OBJECT_ARCHIVE` for `100` (becomes noncurrent) |

The `OBJECT_FINALIZE` notification may include `overwroteGeneration` = `100`. The corresponding `OBJECT_DELETE` or `OBJECT_ARCHIVE` notification may include `overwrittenByGeneration` = `101`.

**There is no delivery-order guarantee** between these two events. If a `DELETE` handler executes after `FINALIZE`, "deleting by object name" without checking generation can accidentally erase the new generation's outputs. Design idempotency and concurrency around **object generation**.

### Soft Delete, Versioning, and Lifecycle

**Object Versioning** and **Soft delete** are distinct features. In Eventarc direct events, the `deleted` event can correspond to soft-delete actions per Eventarc definitions—do not equate it blindly with Pub/Sub notifications' `OBJECT_DELETE`, which documentation defines as permanent deletion. Lifecycle rules, retention policies, object holds, and soft delete all alter when objects are physically removed.

When a business requirement says "when a user clicks delete, delete the DB record immediately," decide whether the system should react to **deletion intent**, **the object no longer being live**, or **permanent deletion**. Never guess behavior solely from event names.

### Why Not Use Notifications for Every Action?

Pub/Sub notifications track supported object mutations; by default they do not fire on **object reads/downloads**, IAM changes, or most bucket-level actions. To audit who read data or modified IAM, use **Cloud Audit Logs** (which can be routed to Pub/Sub via log sinks if needed). Never treat notifications as a complete audit system.

## 4. Message Structure: Attributes and Payload

Cloud Storage notifications arrive as **Pub/Sub messages**, containing:

- **Attributes:** key/value pairs describing the event, always including required fields.
- **Data payload:** depending on configuration, either empty or UTF-8 JSON object metadata.
- **Pub/Sub envelope:** `messageId`, `publishTime`, and ack metadata at the Pub/Sub layer—not a globally unique immutable ID for the object event itself.

### Key Attributes

| Attribute | Example | Meaning |
| --- | --- | --- |
| `notificationConfig` | `projects/_/buckets/shop-uploads/notificationConfigs/3` | Which config generated the notification |
| `eventType` | `OBJECT_FINALIZE` | Type of change |
| `payloadFormat` | `JSON_API_V1` | Payload format |
| `bucketId` | `shop-uploads` | Bucket emitting the event |
| `objectId` | `incoming/photo-001.jpg` | Object name, may contain `/` |
| `objectGeneration` | `1700000000000000` | Generation referenced by the event |
| `eventTime` | `2026-11-19T01:02:03Z` | Event timestamp in RFC 3339 |
| `overwroteGeneration` | `1699999999999999` | Previous generation replaced by this FINALIZE, if any |
| `overwrittenByGeneration` | `1700000000000000` | New generation that replaced the archived/deleted generation, if any |

`objectId` is the **object name**, not necessarily a real directory; `incoming/` is just a string prefix. If object names contain spaces or Unicode, consumers must URL-encode properly when building API requests rather than naively concatenating strings.

### Conceptual Message Example

~~~json
{
  "message": {
    "messageId": "1234567890123456",
    "publishTime": "2026-11-19T01:02:04Z",
    "attributes": {
      "notificationConfig": "projects/_/buckets/shop-uploads/notificationConfigs/3",
      "eventType": "OBJECT_FINALIZE",
      "payloadFormat": "JSON_API_V1",
      "bucketId": "shop-uploads",
      "objectId": "incoming/photo-001.jpg",
      "objectGeneration": "1700000000000000",
      "eventTime": "2026-11-19T01:02:03Z"
    },
    "data": "eyJraW5kIjoi..."
  }
}
~~~

When inspected via JSON API/CLI, a Pub/Sub message's `data` field is **Base64-encoded**. Once decoded under `JSON_API_V1`, it contains **Cloud Storage JSON API Object resource metadata**—fields like `name`, `bucket`, `generation`, `metageneration`, `size`, `contentType`, or `updated` depending on state/event. It is **not the image/PDF bytes**. The Base64 snippet above is illustrative only.

With `--payload-format=none`, Pub/Sub `data` carries no metadata body while `attributes` still carry the event fields. Choose `none` when consumers only need name/generation and will fetch fresh state from the Storage API; choose `json` when you want a metadata snapshot in the message—while watching message size limits and sensitive metadata exposure.

### Generation and Metageneration

**Generation** distinguishes **byte/object content** versions. **Metageneration** increments when metadata on a generation changes; metadata-update events can share the same generation with a different metageneration. Useful composite keys in design:

~~~text
bucket + objectName + generation  → keys one content version
bucket + objectName + generation + metageneration
                                 → keys one metadata version
eventType + above values          → keys event processing
~~~

To avoid accidental overwrites when processing older events, pass **generation/metageneration preconditions** supported by the Cloud Storage API (such as `ifGenerationMatch`/`ifMetagenerationMatch`), rather than blindly reading the "latest object" by name.

## 5. Delivery Semantics: Never Assume Exactly-Once or Ordered Delivery

Cloud Storage guarantees **at-least-once** notification delivery while configured properly. Pub/Sub can also redeliver messages if a subscriber fails to ack or its ack deadline expires. Consequently, **the same event can arrive multiple times**, sometimes with **different `messageId` values** if published twice at the source.

Events are **not guaranteed to be published or received in object-creation order**. Under rapid overwrites, a consumer might receive `FINALIZE(g=103)` before `FINALIZE(g=102)`; late older events must never overwrite newer database state.

Guarantees to understand:

| Question | Answer |
| --- | --- |
| Is every event guaranteed to arrive within seconds? | **No**. Usually fast, yet long delays can happen; no delivery-time SLA exists |
| Does one object event always yield exactly one Pub/Sub message? | **No**. Duplicates can occur even at publish time |
| Does a Pub/Sub pull ack guarantee business-level "exactly once"? | **Not automatically**; consumers must implement idempotency and transactions |
| Do messages always arrive in generation order? | **No** |
| When adding a notification, are past events replayed? | **Do not expect it**. Configurations emit only for changes after taking effect |
| Can Pub/Sub exactly-once delivery subscriptions be used? | Yes for **pull** under supported conditions, yet it cannot deduplicate events published twice with different message IDs |
| Is `messageId` alone sufficient as an idempotency key? | **Insufficient** if one Cloud Storage event was published under multiple message IDs |

When creating a notification, it can take **up to roughly 30 seconds** before events begin firing; deleting a configuration can likewise have a brief lag before notifications stop. If Cloud Storage repeatedly fails to publish because the topic was deleted, Publisher permissions were revoked, or quotas failed, the notification configuration **may be deleted after roughly 7 days**. Monitoring must therefore check **configuration health**, not just consumer logs.

## 6. Designing Idempotent, Generation-Safe Consumers

Example thumbnail workflow:

~~~text
Upload incoming/A.jpg generation=100
      ↓ OBJECT_FINALIZE
Pub/Sub message (may repeat or arrive late)
      ↓
Worker checks eventType, prefix, bucket, generation
      ↓
Records processing key in database (atomic upsert)
      ↓
Reads object at exact generation, generates thumbnail
      ↓
Writes output with precondition / unique key
      ↓
Marks DONE, ACKs message
~~~

Suggested idempotency key:

~~~text
key = eventType + "|" + bucketId + "|" + objectId + "|" + objectGeneration
~~~

For metadata updates, include `metageneration` if each metadata revision matters. If multiple notification configurations point to the same topic, key on the **business event** rather than `notificationConfig`: if two configs emit the same event, you normally still want to process it once.

### Sample Processing Pseudocode

~~~text
onMessage(message):
  attrs = message.attributes
  validate attrs.eventType, bucketId, objectId, objectGeneration

  if attrs.eventType != "OBJECT_FINALIZE":
      ACK; return
  if not attrs.objectId.startsWith("incoming/"):
      ACK; return

  key = hash("thumbnail|" + attrs.bucketId + "|" +
             attrs.objectId + "|" + attrs.objectGeneration)

  if processingStore.hasStatus(key, DONE):
      ACK; return

  try:
      # Atomic claim, lease, or short-lived lock to prevent concurrent execution.
      claimJob(key)

      # READ EXACT generation; never default to a newer live version by name.
      source = storage.read(
          bucket=attrs.bucketId,
          name=attrs.objectId,
          generation=attrs.objectGeneration)

      thumbnail = transform(source)
      output = "thumbnails/" + hash(attrs.objectId) + "/" +
               attrs.objectGeneration + ".jpg"

      # Create-if-absent (ifGenerationMatch=0) or verify destination already exists.
      storage.write(output, thumbnail, precondition=createIfAbsent)

      markDone(key, output)
      ACK

  except TemporaryFailure:
      NACK or let ack deadline expire for Pub/Sub retry
  except PermanentInvalidInput:
      record auditable error status, then ACK / send to DLQ
~~~

**This is pseudocode**, not standalone Java code. Locking and `claimJob` must be **atomic** (e.g., a unique constraint/transaction in Cloud SQL or equivalent); a non-atomic `exists` check followed by a write still suffers race conditions. If a crash occurs between "upload thumbnail" and "markDone," the retry will see the output already exists—handle that cleanly as a valid completion rather than creating duplicates or overwriting another version.

### When the Source Generation Is No Longer Readable

If the bucket has Object Versioning disabled, an older generation may be replaced or deleted before the worker reads it. Reading by the event's generation then returns `404`. Consumers need an explicit policy:

- Accept **skipping as stale** when only the newest generation needs processing.
- Enable Object Versioning or write staging objects with immutable names if every generation must be processed.
- Retry transient errors, yet **never retry indefinitely** on a permanently deleted generation.
- Record skip/error reasons for auditing and out-of-band recovery.

**Never fall back to reading `gs://bucket/path` without a generation** for an old event if business logic requires the exact file content from that event.

## 7. Preparing IAM and Pub/Sub Before Creating Notifications

Assume the bucket and Pub/Sub topic start in the same project for learning. In production designs, they **can live in two different projects**; in that case, identify the service agent from the bucket's project and grant publish permissions in the **topic project**.

Distinct identities and permissions:

| Identity | Required Permissions | Recommended Scope |
| --- | --- | --- |
| Operator/pipeline creating notification config | Bucket update permission, e.g., `storage.buckets.update`; topic view/manage if needed | Target bucket and topic |
| **Cloud Storage service agent** of the bucket's project | `pubsub.topics.publish`, typically `roles/pubsub.publisher` | **Target topic only** |
| Operator/pipeline creating topics and subscriptions | `pubsub.topics.create`, `pubsub.subscriptions.create`, and related rights | Pub/Sub project/resources |
| Worker consuming subscription | `pubsub.subscriptions.consume`, typically `roles/pubsub.subscriber` | Specific subscription |
| Worker reading object bytes | `storage.objects.get`, e.g., scoped Object Viewer | Bucket or managed folder with authorized data |
| Cloud Run / Eventarc trigger identity | Event-receiving and Cloud Run invocation roles per config | Trigger and destination service |

**Crucial distinction:** the service agent publishing notifications **is different from** the service account your Java worker uses to read the bucket. Granting Pub/Sub Publisher to the Java worker will not let Cloud Storage emit events if the **service agent** lacks permission. Conversely, Pub/Sub Subscriber does not grant the worker permission to download images from Cloud Storage.

### Retrieving the Cloud Storage Service Agent

~~~bash
BUCKET_PROJECT="my-storage-project"
TOPIC_PROJECT="my-events-project"
TOPIC="object-events"

# Retrieve the Google-managed service agent email for the BUCKET'S project.
gcloud storage service-agent --project="$BUCKET_PROJECT"
~~~

Example returned email format:

~~~text
service-123456789012@gs-project-accounts.iam.gserviceaccount.com
~~~

This identifier is illustrative, not a usable email for a real project. Grant permissions strictly on the **target topic**, after substituting the real email:

~~~bash
SERVICE_AGENT="service-123456789012@gs-project-accounts.iam.gserviceaccount.com"

gcloud pubsub topics add-iam-policy-binding "$TOPIC" \
  --project="$TOPIC_PROJECT" \
  --member="serviceAccount:$SERVICE_AGENT" \
  --role="roles/pubsub.publisher"
~~~

The notification-creation CLI can **automatically check and attempt to grant** Pub/Sub Publisher to the service agent if the operator holds sufficient permissions. In locked-down IAM environments, it is cleaner for platform pipelines to create the IAM binding explicitly and pass `--skip-topic-setup` when needed. After granting the role, allow for IAM propagation time before testing events.

**Cross-project:** bucket in project A, topic in project B → **A's** service agent must receive Publisher on **B's** topic; the notification configuration on bucket A references the full topic path `projects/B/topics/TOPIC`. Do not accidentally grant project B's service agent.

## 8. CLI Lab: From Bucket to Notification

The commands below use **Bash** with an authenticated Cloud SDK authorized in a lab project. Substitute a globally unique bucket name and real project IDs. To avoid needless bucket churn, assume bucket `shop-uploads-lab-unique` already exists with uniform bucket-level access and holds no critical data.

### Step 1 — Create Topic and Subscription Before Uploading

~~~bash
BUCKET_PROJECT="my-storage-project"
TOPIC_PROJECT="my-events-project"
BUCKET="shop-uploads-lab-unique"
TOPIC="object-events"
SUB="object-events-debug"

gcloud services enable pubsub.googleapis.com --project="$TOPIC_PROJECT"

gcloud pubsub topics create "$TOPIC" \
  --project="$TOPIC_PROJECT"

# Create subscription first so messages are not missed once testing begins.
gcloud pubsub subscriptions create "$SUB" \
  --project="$TOPIC_PROJECT" \
  --topic="$TOPIC"

gcloud pubsub topics describe "$TOPIC" --project="$TOPIC_PROJECT"
gcloud pubsub subscriptions describe "$SUB" --project="$TOPIC_PROJECT"
~~~

Creating an existing topic/subscription fails; in live systems, **inspect state first or manage via IaC**. One topic can have multiple independent subscriptions—for example, one for thumbnailing and one for search indexing.

### Step 2 — Grant Publisher Permission to the Service Agent

Retrieve `BUCKET_PROJECT`'s service agent email as shown in Section 7 and grant `roles/pubsub.publisher` on the topic in `TOPIC_PROJECT`. Inspect the topic's IAM policy before creating the notification:

~~~bash
gcloud pubsub topics get-iam-policy "$TOPIC" \
  --project="$TOPIC_PROJECT"
~~~

### Step 3 — Create a Notification Configuration Filtered by Event and Prefix

~~~bash
gcloud storage buckets notifications create "gs://$BUCKET" \
  --topic="projects/$TOPIC_PROJECT/topics/$TOPIC" \
  --event-types=OBJECT_FINALIZE,OBJECT_DELETE \
  --object-prefix="incoming/" \
  --payload-format=json

# List configurations on the bucket.
gcloud storage buckets notifications list "gs://$BUCKET"
~~~

This creates a configuration matching **only two event types**. With `--object-prefix=incoming/`, only objects whose names start with `incoming/` trigger notifications; `archive/photo.jpg` will not match. Prefix matching is a **literal string prefix**, not a regex, glob, or `.jpg` suffix filter. Check capitalization, slashes, and how apps construct object names.

To send all supported event types to the topic, omit `--event-types`. To omit the metadata JSON body, pass `--payload-format=none`. To attach custom attributes, see `--custom-attributes` in `gcloud storage buckets notifications create --help`.

**Important:** Cloud Storage **Pub/Sub notification configurations** cannot be managed through the Cloud Storage Console UI per current documentation; use the Cloud CLI, client libraries, or JSON API. The Console can still manage **Pub/Sub topics/subscriptions** and inspect messages, but does not replace bucket notification configuration commands.

### Step 4 — Inspect the Configuration Before Triggering Test Events

From `list`, each configuration has an **ID**. Using example ID `3`:

~~~bash
gcloud storage buckets notifications describe \
  "projects/_/buckets/$BUCKET/notificationConfigs/3"
~~~

Do not assume ID `3` for every bucket: Cloud Storage assigns the actual ID. Record it in your registry or Infrastructure as Code to track which configuration serves which pipeline.

### Step 5 — Upload a Test File and Check Pub/Sub

Wait for the configuration to take effect (up to ~30 seconds), then create a test file on your **lab machine**, not inside a code repository:

~~~bash
# Illustrative command run in a lab environment.
printf 'demo upload event\n' > upload-demo.txt

gcloud storage cp ./upload-demo.txt \
  "gs://$BUCKET/incoming/upload-demo.txt"

gcloud pubsub subscriptions pull "$SUB" \
  --project="$TOPIC_PROJECT" \
  --limit=10 \
  --auto-ack \
  --format=json
~~~

`--auto-ack` **is suitable only on a debug subscription**: pulled messages are acknowledged immediately and become unavailable to other workers on **that same subscription**. In production, consumers must ack **only after durable completion**. Use a dedicated debug subscription so you never steal messages from production workers.

CLI output should show `message.attributes.eventType` as `OBJECT_FINALIZE`, `objectId` as `incoming/upload-demo.txt`, and a real numeric `objectGeneration`. `message.data` (when present) is Base64-encoded metadata JSON—do not expect to see the literal file text `demo upload event` inside the payload.

### Step 6 — Test DELETE and Read the Event

~~~bash
# Delete ONLY the object just created in the lab bucket.
gcloud storage rm "gs://$BUCKET/incoming/upload-demo.txt"

gcloud pubsub subscriptions pull "$SUB" \
  --project="$TOPIC_PROJECT" \
  --limit=10 \
  --auto-ack \
  --format=json
~~~

Deletion event timing and type depend on bucket Object Versioning, Soft delete, and retention policies. If `OBJECT_DELETE` does not appear, inspect bucket settings, event filters, propagation delay, and actual deletion semantics rather than assuming the pipeline broke.

### Step 7 — Remove the Lab Configuration Safely

~~~bash
gcloud storage buckets notifications list "gs://$BUCKET"

# Delete ONLY the exact notification ID; DO NOT pass gs://BUCKET alone to delete.
gcloud storage buckets notifications delete \
  "projects/_/buckets/$BUCKET/notificationConfigs/3"
~~~

Critical warning: `gcloud storage buckets notifications delete gs://BUCKET` can **delete every notification configuration on the bucket**. Delete only the verified lab configuration ID; never delete configurations owned by other services. Deleting a notification configuration **does not automatically delete** the Pub/Sub topic or subscription. Review consumers and retention before cleaning those up; a few in-flight notifications may still arrive briefly after deletion.

## 9. Managing Configuration with Terraform

Across multiple projects and environments, manage notifications, topics, subscriptions, and service-agent IAM in Infrastructure as Code. Example HCL referencing an **existing bucket**, creating a topic and pull subscription for a pipeline:

~~~hcl
variable "bucket_project_id" {
  type = string
}

variable "topic_project_id" {
  type = string
}

variable "bucket_name" {
  type = string
}

# Look up the exact service agent of the BUCKET'S project.
data "google_storage_project_service_account" "bucket" {
  project = var.bucket_project_id
}

resource "google_pubsub_topic" "objects" {
  project = var.topic_project_id
  name    = "object-events"
}

resource "google_pubsub_topic_iam_member" "publisher" {
  project = var.topic_project_id
  topic   = google_pubsub_topic.objects.name
  role    = "roles/pubsub.publisher"
  member  = format(
    "serviceAccount:%s",
    data.google_storage_project_service_account.bucket.email_address
  )
}

resource "google_storage_notification" "incoming_finalized" {
  bucket             = var.bucket_name
  topic              = google_pubsub_topic.objects.id
  payload_format     = "JSON_API_V1"
  event_types        = ["OBJECT_FINALIZE"]
  object_name_prefix = "incoming/"

  depends_on = [google_pubsub_topic_iam_member.publisher]
}

resource "google_pubsub_subscription" "thumbnail_worker" {
  project = var.topic_project_id
  name    = "thumbnail-worker"
  topic   = google_pubsub_topic.objects.id
}
~~~

This is a **reference template**: you still need Terraform providers/credentials, enabled APIs, CI/CD permissions, retry/dead-letter policies, and object lifecycle handling. For buckets with manually created notifications, **import the existing resource or plan ownership handoff** so you do not create duplicate configurations that double-deliver every event.

If multiple apps need `OBJECT_FINALIZE`, prefer **one notification configuration → one topic → multiple subscriptions** over creating one notification configuration per application. This avoids hitting bucket limits and simplifies operations while still scoping Pub/Sub permissions per consumer.

### Notification Configuration Limits

Per Cloud Storage documentation, each bucket allows:

- Up to **100 notification configurations total**.
- Up to **10 configurations subscribed to any single specific event type**.
- Each configuration has a unique ID and can target a topic in another project.

Across multiple teams, treat the topic as a governed **event bus** (with clear ownership and retention). Never let individual teams create dozens of uncatalogued configurations on a shared production bucket; certain Cloud Run / Eventarc triggers may also consume notification slots depending on architecture.

## 10. How Do Direct Eventarc Triggers to Cloud Run Differ from Pub/Sub Notifications?

Cloud Storage can trigger **Eventarc Standard direct events** and Cloud Run functions without requiring users to manually provision topics and subscriptions. Pub/Sub may still operate under the hood, yet the developer interface differs.

| Criterion | Direct Pub/Sub Notifications | Eventarc Direct Events |
| --- | --- | --- |
| Input configuration | Bucket notification → topic → subscription | Eventarc trigger with filters and destination |
| Payload received by app | Pub/Sub message attributes/data | **CloudEvents** over HTTP in Eventarc format |
| Best fit | Multi-consumer fan-out, pull workers, batching, independent subscriptions | Direct delivery to Cloud Run and Eventarc-supported destinations |
| Retry / ack | Configured on Pub/Sub subscription and consumer | Eventarc manages delivery/retries per trigger |
| Location | Topic can reside in another project with proper IAM | Direct Storage triggers carry project/location constraints per service |
| Event names | `OBJECT_FINALIZE`, `OBJECT_DELETE`, etc. | `google.cloud.storage.object.v1.finalized`, `deleted`, etc. |
| Replay capability | Can leverage Pub/Sub retention/seek for received messages | Do not treat Eventarc as an indefinite event store |

Example paths:

~~~text
Cloud Storage OBJECT_FINALIZE
   → (A) Notification configuration → Pub/Sub topic → Pull Java worker

Cloud Storage object finalized
   → (B) Eventarc direct trigger → CloudEvents HTTP → Cloud Run
~~~

When using **Eventarc direct events for Cloud Storage**, the bucket must reside in the **same project** and a **compatible location** for the trigger per documentation (supported region, dual-region, or multi-region). The Cloud Run destination normally resides in the **same project** as the trigger, though it can run in another supported region. The trigger identity needs permissions to receive events and invoke Cloud Run; the service identity needs object-read permissions to process content.

Example Eventarc direct event types:

~~~text
google.cloud.storage.object.v1.finalized
google.cloud.storage.object.v1.deleted
google.cloud.storage.object.v1.archived
google.cloud.storage.object.v1.metadataUpdated
~~~

Never copy `OBJECT_FINALIZE` from Pub/Sub notifications straight into Eventarc's `--event-filters=type=...`, and **never pass a raw Pub/Sub envelope** into a CloudEvents handler without translation.

### When to Choose Each Approach

- **A single Cloud Run service** needs finalized-object events with minimal infrastructure wiring: evaluate an Eventarc direct trigger.
- **Multiple systems** (Java workers, Dataflow, search indexing, auditing) need the same events: a Pub/Sub topic with multiple subscriptions is usually cleaner.
- Need **backlog control, flow control, pull-based processing, custom retries, and DLQs**: Pub/Sub subscriptions give direct knobs.
- Need to monitor **object reads** or bucket actions outside object-change notifications: inspect Cloud Audit Logs routed via Pub/Sub or Eventarc.

**Not every trigger is "free" or exempt from notification quotas.** Review current rules and limits across Cloud Storage, Eventarc, Pub/Sub, and Cloud Run together.

## 11. Organizing Java Consumers and Cloud Run Workers

In Java systems, two patterns are common:

**Pull subscription:** Workers run on Compute Engine, GKE, or a long-lived service using the Google Cloud Pub/Sub library to pull, process, and ack messages. This gives tight control over concurrency, flow control, and high-volume throughput.

**Push subscription:** Pub/Sub sends HTTP POST requests to an endpoint such as Cloud Run. The service authenticates the request, processes the event, and returns a success status to ack; failures per Pub/Sub push semantics trigger redelivery. On Cloud Run, configure **authenticated push** with an OIDC service account holding `roles/run.invoker`; never leave event-processing endpoints unauthenticated publicly unless explicitly intended.

### Designing a Java Pull Subscriber

Interface-level pseudocode showing processing order—**not a standalone compilable Java project**:

~~~java
// Assumes Pub/Sub Subscriber, Cloud Storage client, and repository exist.
void onPubsubMessage(PubsubMessage message, AckReplyConsumer consumer) {
    Map<String, String> a = message.getAttributesMap();

    String type = a.get("eventType");
    String bucket = a.get("bucketId");
    String object = a.get("objectId");
    String generation = a.get("objectGeneration");

    if (!"OBJECT_FINALIZE".equals(type)
            || bucket == null || object == null
            || generation == null || !object.startsWith("incoming/")) {
        consumer.ack();
        return;
    }

    String jobKey = "thumbnail:" + bucket + ":" + object + ":" + generation;
    try {
        // Must be backed by a unique constraint/transaction or distributed lock.
        if (repository.isDone(jobKey)) {
            consumer.ack();
            return;
        }

        // Read the EXACT generation in Cloud Storage; never default to latest.
        BlobId blobId = BlobId.of(bucket, object, Long.parseLong(generation));
        Blob blob = storage.get(blobId);

        if (blob == null) {
            repository.markStale(jobKey, "Source generation is unavailable");
            consumer.ack();
            return;
        }

        byte[] bytes = blob.getContent();
        byte[] thumbnail = imageProcessor.resize(bytes);

        // Must write idempotently using a generation-scoped output name
        // and precondition so newer generations are never overwritten.
        repository.commitThumbnailOnce(jobKey, thumbnail);
        consumer.ack();
    } catch (RetryableProcessingException ex) {
        consumer.nack();
    } catch (InvalidImageException ex) {
        repository.recordPermanentError(jobKey, ex.getMessage());
        consumer.ack();
    }
}
~~~

`repository`, `storage`, `imageProcessor`, and exceptions represent **application-implemented** components; `getContent()` loads all bytes into RAM and suits small files only. For large videos or PDFs, stream data within memory/runtime bounds or offload heavy work to Dataflow or appropriately sized workers.

**Important:** checking `repository.isDone` alone before `commitThumbnailOnce` **does not prevent races**. Claim and commit must be atomic. If a consumer crashes after creating the output object but before acking, the retry must recognize the existing output and finish cleanly without creating duplicates.

### Ack Differences Across Pull and Push

| Subscriber Type | On Success | On Transient Failure | Key Watchpoints |
| --- | --- | --- | --- |
| **Pull** | Call `ack` after durable commit | `nack` or let ack deadline expire | Tune flow control and ack deadline extensions |
| **Push HTTP** | Return HTTP success per Pub/Sub push semantics | Return non-success status or timeout | Service must verify OIDC auth and handle retries |
| **Eventarc → Cloud Run** | Handler processes CloudEvent and returns success | Eventarc retries per trigger config | Payload is a CloudEvent, not the classic Pub/Sub notification envelope |

Never ack immediately after parsing JSON before committing durable state. Likewise, never retry permanently corrupt files forever: log errors, alert, or route to a **dead-letter topic (DLQ)** per Pub/Sub capabilities and operational policy.

## 12. Retries, Dead-Letter Handling, and Backlog Recovery

Common failure categories:

| Failure Type | Example | Handling |
| --- | --- | --- |
| **Transient** | Cloud SQL timeout, temporary quota, API 5xx | Retry with backoff; cap concurrency |
| **Poison message** | Malformed event, unsupported MIME, corrupt object bytes | Record error, route to DLQ, or ack once confirmed unprocessable |
| **Stale generation** | File overwritten before worker read the older version | Enable Object Versioning or skip and log as stale |
| **Duplicate delivery** | Ack deadline expired; Pub/Sub redelivers | Deduplicate via business key and idempotent writes |
| **Out-of-order delivery** | Generation 102 event arrives after 103 | Compare generations; enforce preconditions |
| **Slow consumer** | Large file takes several minutes | Flow control, streaming, extend ack deadlines, or split jobs |
| **Publisher unable to emit** | Topic deleted, service agent lost Publisher role | Check notification config, IAM, and Pub/Sub publish quotas |

### Dead-Letter Topic

Pub/Sub can forward messages to a **dead-letter topic** once delivery attempts exceed a configured threshold. Provision the DLQ, grant required IAM to the Pub/Sub service agent, set max delivery attempts, and attach a monitoring alert/replay workflow after fixing bugs.

**A DLQ is not a place to "ignore errors forever."** If 200 images landed in the DLQ due to a parser bug, you need a safe way to replay valid jobs once fixed. Use `jobKey` and persisted status to prevent duplicate side effects during replay. A growing DLQ means the system is unhealthy even if HTTP uploads return 200.

### Protecting Subscriptions During Consumer Outages

If workers stop for hours, messages accumulate in the subscription up to its **message retention policy** and backlog limits. When workers return, they can be flooded with stale or outdated events.

Recommendations:

1. Monitor `num_undelivered_messages` and `oldest_unacked_message_age`.
2. Align message retention and ack deadlines with your RTO and job duration.
3. Cap concurrent jobs so workers do not overwhelm Cloud SQL or downstream APIs.
4. Mark outdated generations as stale without blindly discarding audit-required work.
5. When messages are lost or a notification config was deleted, run **reconciliation**: list objects/generations to process, diff against the processing registry, and enqueue backfill jobs within authorized scope.

**Events alone cannot guarantee zero data drift.** Critical systems need periodic reconciliation comparing bucket inventory against the processing state table; Pub/Sub notifications drive fast reactions while reconciliation heals operational gaps.

## 13. Security: Events Can Carry Sensitive Metadata

Object names can contain customer IDs, emails, report titles, or internal directory structures. `JSON_API_V1` payloads also carry content types, custom metadata, and other attributes. Event messages are therefore **sensitive data requiring protection**.

Security checklist:

- **Bucket permissions:** uploaders write only to allowed prefixes; workers read only objects they must process, without unnecessary delete access.
- **Topic Publisher:** grant `roles/pubsub.publisher` on the exact target topic to the **bucket project's Cloud Storage service agent**—never project-wide by habit.
- **Subscription Consumer:** worker identity holds `roles/pubsub.subscriber` only on its assigned subscription, not unrelated topics.
- **Compute / Cloud Run identity:** dedicate a service account per pipeline; avoid long-lived JSON keys where Workload Identity or short-lived tokens work.
- **Cloud Run push authentication:** validate OIDC tokens from Pub/Sub/Eventarc; never trust internet requests merely because their JSON matches the schema.
- **Encryption and retention:** review CMEK, Cloud Storage/Pub/Sub IAM, message retention, logs, and derived data per compliance rules.
- **Treat event object names as untrusted input:** validate prefix, file type, size, and disallowed characters to prevent path traversal or SQL injection when writing to DBs/filesystems.
- **Never log raw file bytes or sensitive info**; log event type, hashed/safe object IDs, generation, status, and trace/correlation IDs.

When processing untrusted user files (PDFs, images, CSVs), sandbox parsers, enforce CPU/RAM limits, inspect raw magic bytes, and defend against archive bombs rather than trusting `contentType` metadata.

## 14. Monitoring, Logging, and Event Alerts

To run event pipelines reliably, observe **all three tiers**:

1. **Cloud Storage:** bucket notification configurations, IAM changes, new object counts, and operation errors.
2. **Pub/Sub:** publish throughput, subscription backlog, unacked age, push errors, DLQ counts, quotas, and retention.
3. **Consumer:** request counts, success/failure rates, latency, retry counts, duplicate/stale counts, and backend cost.

| Metric / Signal | Observation Target | Actionable Symptom |
| --- | --- | --- |
| Notification configuration inventory | Config still exists and points to right topic | Config disappears after prolonged publish failures |
| `subscription/num_undelivered_messages` | Waiting message count | Backlog climbs continuously |
| `subscription/oldest_unacked_message_age` | Age of oldest unacked message | File-processing SLO breached |
| Push errors / ack deadline expirations | Subscribers receive and ack reliably | Rising 4xx/5xx/timeouts |
| DLQ message count | Persistent failures needing attention | Repeated poison messages |
| `processed / failed / stale / duplicate` by event type | Business processing quality | Falling success rate or anomalous stale spike |
| Cloud Run CPU / memory / concurrency | Workers have adequate resources | OOMs or throttling on large images |
| Storage operations and Pub/Sub throughput | Cost tracking | Sudden spike in events or object reads |

### Structured Consumer Log Example

~~~json
{
  "severity": "INFO",
  "eventType": "OBJECT_FINALIZE",
  "bucket": "shop-uploads",
  "objectKeyHash": "sha256:example",
  "generation": "1700000000000000",
  "jobState": "DONE",
  "attempt": 1,
  "durationMs": 340,
  "correlationId": "thumbnail-job-001"
}
~~~

Never log full `PubsubMessage.data` payloads or file contents. For every event, capture enough context to trace `ACK`, `NACK`, `DLQ`, and data outcomes while protecting logs with IAM and appropriate retention.

### Runbook When Events Are Missing

1. Confirm the object changed **after** the notification configuration took effect.
2. Verify bucket name, event type, prefix, and Object Versioning / Soft delete settings.
3. Run `gcloud storage buckets notifications list gs://BUCKET` and verify the configuration ID in your registry.
4. Check that the target topic exists, the exact service agent holds Pub/Sub Publisher, and publish quotas are healthy.
5. Verify the subscription exists on the right topic; a topic without a subscription will not retain old messages for later workers.
6. Check whether another consumer already acked the message on **the same subscription**.
7. Inspect subscription backlog, DLQ messages, Cloud Run/worker logs, and time ranges.
8. If business records are missing, run reconciliation to backfill rather than "re-uploading every object," which generates new generations and storms of new events.

## 15. Costs and Operational Limits

An event pipeline spans multiple cost categories:

| Component | Potential Costs | Controls |
| --- | --- | --- |
| **Cloud Storage** | Object storage, API ops, network/data reads, versioning/soft delete | Lifecycle rules, storage classes, retention, operation tracking |
| **Pub/Sub** | Message volume, retention, delivery attempts, and features | Filter events at the source; optimize subscriptions |
| **Cloud Run / worker** | CPU, memory, processing time, requests, network | Tune concurrency, timeouts, streaming, autoscaling |
| **Eventarc** | Routed event volume per service pricing | Provision only genuinely needed triggers |
| **Cloud Logging / Monitoring** | Log ingestion, retention, and metrics | Intentional sampling; avoid logging payloads |
| **Downstream** | Cloud SQL, BigQuery, media processing, partner APIs | Batching, idempotency, retry/backoff |

For example, if 1 million images are uploaded daily and **two notification configurations** both emit `OBJECT_FINALIZE` to one topic, Pub/Sub messages and downstream work multiply even though each image has one generation. Conversely, if one topic feeds two **subscriptions**, each subscription gets its own stream for fan-out—which is expected, yet still bills delivery and processing twice.

Cost-saving practices:

- Scope `--event-types` and `--object-prefix` **tightly** to suppress irrelevant events.
- Use one topic with multiple subscriptions instead of overlapping notification configurations.
- Read object bytes only when needed; `JSON_API_V1` metadata often suffices for metadata-sync jobs.
- Use caching or a DB processing registry to skip expensive work on duplicate events.
- Cap worker concurrency, retries, and retention; alert on billing anomalies.
- Configure Cloud Billing budgets/alerts, remembering **budget alerts are not hard stops** on event processing.

Never cut costs by blindly turning off logging or retention if doing so destroys recoverability or incident forensics.

## 16. Integration Scenario: Product Image Processing

A Java platform lets sellers upload product images:

~~~text
Seller Web/Mobile
     ↓
Java API → issues upload URL / upload grant to Cloud Storage
     ↓
Bucket: product-uploads (prefix incoming/)
     ↓ OBJECT_FINALIZE
Cloud Storage notification configuration
     ↓
Pub/Sub topic: product-image-events
     ├── Subscription A: thumbnail-worker
     │       ↓ Cloud Run/GKE Java worker
     │       ↓ thumbnails/ + DB status
     │
     └── Subscription B: security-scanner
             ↓ Scans file and classifies result
     ↓
Catalog API publishes only processed/verified images
~~~

Every event carries `bucketId`, `objectId`, and `objectGeneration`. Worker A processes `incoming/` by generation; Worker B evaluates file safety. Both consumers use **separate subscriptions** because each must process every upload independently.

### Re-Uploading Under the Same Name

A seller uploads `incoming/item-42.jpg` generation `100`, then uploads a replacement generating `101`. Because order is not guaranteed, a worker might process `101` before `100`.

Safe design:

- Write thumbnails to generation-scoped keys, e.g., `thumbnails/item-42/101.jpg`.
- Store the published generation in the catalog DB with a conditional update: advance only to a newer generation and never let an older event regress it.
- If a source generation is gone, log `STALE` instead of reading another version's bytes under the old key.
- If a worker finishes processing before crashing prior to ack, the retry sees the output and registry state and finishes idempotently.
- Until the scanner finishes, keep the catalog item in `PENDING_REVIEW` rather than assuming new images are safe.

**Separation of responsibilities:** Pub/Sub notifications orchestrate event-driven execution; they do not perform image resizing, virus scanning, uploader authentication, Cloud Storage authorization, CDN cache invalidation, or transactional sync with Cloud SQL. Those must be built explicitly in your application and workflows.

## 17. Pre-Production Checklist

- [ ] Determined whether business logic needs finalize, metadata update, archive, or permanent delete events.
- [ ] Distinguished Pub/Sub notifications from Eventarc direct CloudEvents.
- [ ] Assigned clear owners for buckets, topics, subscriptions, projects/locations, and IAM.
- [ ] **Bucket project's Cloud Storage service agent** holds Publisher on the target topic.
- [ ] Workers hold Subscriber on their subscription and scoped Object Viewer on data.
- [ ] Configured event-type and prefix filters; avoided duplicate configs or bucket limits.
- [ ] Created subscriptions before triggering test events; never assume historical replay from notifications.
- [ ] Consumers use business idempotency keys incorporating generation/metageneration where appropriate.
- [ ] Consumers read objects by exact generation when required by business logic.
- [ ] Ack only after durable commit; configured backoff, retries, DLQs, and permanent-error handling.
- [ ] Tested out-of-order events, duplicate deliveries, and same-name overwrites.
- [ ] Accounted for Object Versioning, Soft delete, and retention semantics.
- [ ] Built reconciliation to recover from missed events or prolonged pipeline outages.
- [ ] Configured logs, metrics, and alerts for backlog, oldest unacked age, DLQ, and processing SLOs.
- [ ] Verified payloads and object names do not leak sensitive info into logs or subscriptions.
- [ ] Estimated costs across Cloud Storage, Pub/Sub, Eventarc/Cloud Run, Logging, and downstream services.
- [ ] Documented rollback steps: updating configs, switching topics, pausing consumers, and post-incident recovery.

**Practice Exercise:** A team builds a PDF analytics service: users upload into `gs://training-pdfs/incoming/`, and Java workers extract text into Cloud SQL. Some users re-upload files with the same name, Object Versioning is enabled, and thousands of files arrive daily.

1. Diagram the Bucket → notification configuration → Pub/Sub topic → Java pull subscriber → Cloud SQL architecture.
2. Choose appropriate event types, prefix filter, and payload format; justify your choices.
3. Write the commands to create the topic/subscription, grant IAM to the Cloud Storage service agent, and create and list the notification.
4. Describe the `OBJECT_FINALIZE` event structure and how to read the exact generation during processing.
5. Design a unique idempotency key and database transaction so two duplicate events never produce two result rows.
6. Explain how event order can invert when version `101` is uploaded before workers process `100`.
7. Handle corrupt PDFs, temporary Cloud SQL quota errors, worker crashes before ACK, and growing subscription backlogs.
8. Compare using an Eventarc Cloud Run trigger instead of Pub/Sub pull for this use case.
9. Propose monitoring, DLQ handling, reconciliation, metadata security, and cost controls.

## Official Reference Documentation

- [Pub/Sub notifications for Cloud Storage](https://cloud.google.com/storage/docs/pubsub-notifications) — event definitions, attributes, payloads, and delivery guarantees.
- [Configure Pub/Sub notifications](https://cloud.google.com/storage/docs/reporting-changes) — IAM requirements and creating/listing/deleting notification configurations.
- [gcloud storage buckets notifications create](https://cloud.google.com/sdk/gcloud/reference/storage/buckets/notifications/create) — event filters, prefix, payload, and topic flags.
- [gcloud storage buckets notifications delete](https://cloud.google.com/sdk/gcloud/reference/storage/buckets/notifications/delete) — deleting a single configuration or all configurations by target.
- [Get the Cloud Storage service agent](https://cloud.google.com/storage/docs/getting-service-agent) — identifying the exact publisher identity.
- [Cloud Storage Object Versioning](https://cloud.google.com/storage/docs/object-versioning) — generations and archiving of previous versions.
- [Cloud Storage soft delete](https://cloud.google.com/storage/docs/soft-delete) — object lifecycle and recoverability.
- [Cloud Storage preconditions](https://cloud.google.com/storage/docs/request-preconditions) — `ifGenerationMatch`/`ifMetagenerationMatch` and safe updates.
- [Pub/Sub subscribe best practices](https://cloud.google.com/pubsub/docs/subscribe-best-practices) — acks, retries, flow control, and duplicate handling.
- [Pub/Sub exactly-once delivery](https://cloud.google.com/pubsub/docs/exactly-once-delivery) — scope of exactly-once delivery and pull limitations.
- [Route Cloud Storage events to Cloud Run with Eventarc](https://cloud.google.com/eventarc/standard/docs/run/route-trigger-cloud-storage) — CloudEvents, filters, IAM, and locations.
- [Pub/Sub pricing](https://cloud.google.com/pubsub/pricing) — message delivery and retention.
- [Cloud Storage pricing](https://cloud.google.com/storage/pricing) — object operations, storage classes, and data transfer.
