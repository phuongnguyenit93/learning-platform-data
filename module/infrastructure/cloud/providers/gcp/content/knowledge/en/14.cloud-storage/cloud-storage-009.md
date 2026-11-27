# Consistency, Generation, and Preconditions When Updating Objects in Cloud Storage

Two instances of a Java service might both read `gs://commerce-data/orders/state.json`, compute a new state, and overwrite the object. If both processes update without checking the state they observed, one write can **silently erase the result of the other**. This issue does not happen because Cloud Storage "has not synced data yet"; it is a **race condition** caused by multiple actors operating on the same object.

Cloud Storage provides **strong consistency** for most read, write, delete, and object listing operations. To update safely in concurrent systems, Cloud Storage also provides two version numbers—**`generation`** and **`metageneration`**—along with **request preconditions** such as `ifGenerationMatch` and `ifMetagenerationMatch`. Combining these mechanisms lets you implement **optimistic concurrency control / compare-and-swap (CAS)** directly at the storage API layer.

This lesson belongs to the **Cloud Storage** chapter of the `CLOUD_PROVIDERS_GCP` module. In the context of learning project organization, IAM, VPC, Compute Engine, GKE, Cloud Run, storage, and databases, this forms the foundation for writing safe applications, automating deployments, protecting resources, ensuring consistent data, reducing retry bugs, and tracking incurred costs.

**Scope:** Cloud Storage consistency behavior, object version identifiers, preconditions, conditional read–modify–write, CLI/REST/Java operations, and contention scenarios. **Object Versioning, soft delete, retention, IAM, and caching** are discussed only where they impact this problem.

## Learning Objectives

After this lesson, you will be able to:

1. Explain which Cloud Storage operations are **strongly consistent** and when stale data may still be observed.
2. Distinguish `generation` (object content version) from `metageneration` (metadata version for a given generation).
3. Use `ifGenerationMatch=0` to **create an object only if no live object exists yet**.
4. Use `ifGenerationMatch=G` to **overwrite or delete only if the live version is still G**.
5. Use **both `generation` and `metageneration`** to update metadata without losing concurrent edits.
6. Recognize `412 Precondition Failed` as a condition conflict, distinguishing it from IAM errors, missing objects, and transient failures.
7. Design conditional retries, idempotency, multi-writer coordination, and stable generation-pinned reads.
8. Practice with `gcloud storage`, the REST JSON API, and the Cloud Storage Java client library.
9. Understand the boundaries of single-object atomicity, Object Versioning, soft delete, CDN/browser caching, and data protection.
10. Build concurrency testing workflows and observability for production applications.

## 1. Data Model: Bucket, Object Name, Live Version

Cloud Storage stores **objects** inside **buckets**. An object is identified by its name within a bucket; writing again under the same name creates a **new generation** of the object.

Example:

~~~text
Bucket: commerce-lab-data
Object name: orders/state.json
URI: gs://commerce-lab-data/orders/state.json

Current content:
{"orderId":"A100","status":"PENDING"}
~~~

Names containing `/` are part of the object name and do not imply a file inside a real POSIX directory. Hierarchical namespace and managed folders have separate features; this lesson focuses on **object reads and writes**.

### 1.1. Live Object and Noncurrent Generation

At any moment, there is normally only **one live version** for a given object name. If the bucket has **Object Versioning** enabled, a replaced copy can be retained as a **noncurrent version**, identified by its older generation. Without Object Versioning enabled, replacing an object does not mean you can read the previous version back as a noncurrent object.

~~~mermaid
flowchart LR
    W1["Upload state.json (1st time)"] --> G1["generation G1<br/>live"]
    W2["Overwrite same name"] --> G2["generation G2<br/>live"]
    G1 -. "Becomes noncurrent<br/>if Object Versioning is ON" .-> V["Version history"]
    W2 --> G2
~~~

**Generation does not depend on Object Versioning being enabled.** Every object has a generation. Versioning determines **whether old copies are retained**, not whether the API assigns generation numbers.

## 2. What Does Cloud Storage Strong Consistency Guarantee?

According to Google Cloud, the following operations provide **strong global consistency**:

| Operation | After the API Returns Success | Example |
| --- | --- | --- |
| **Object read-after-write** | Subsequent reads observe the newly written object/generation | After upload completes, `GET` returns new content |
| **Object read-after-metadata-update** | Reading metadata back reflects the update | Update `Cache-Control`, read updated metadata |
| **Object read-after-delete** | Deleted live object no longer appears in normal reads | After delete succeeds, reading the live name returns `404` |
| **Object listing** | Listing reflects successfully created/deleted objects | Upload, then `ls` immediately shows the new name |
| **Bucket read-after-create/update/delete** | Reading bucket metadata reflects the new state | Update bucket metadata and read back |
| **Bucket listing** | Bucket list updates consistently | Create a bucket, then list |
| **Supported folders / managed folders** | Supported create/read/delete/list operations are strongly consistent | Analyze per specific resource type |

These guarantees apply across regions, dual-regions, and multi-regions for the listed operations—not only within the zone where the upload occurred.

### 2.1. Single-Object Operation Atomicity

When uploading or overwriting an object, a partial upload never appears as a live object with **half-written content**. The new object becomes readable once the operation succeeds; readers never receive a stitched mix of two concurrent overwrites.

~~~mermaid
sequenceDiagram
    participant W as Writer
    participant S as Cloud Storage
    participant R as Reader
    R->>S: GET object
    S-->>R: Generation G1
    W->>S: Upload replacement G2
    Note over S: Write in progress
    R->>S: GET object
    S-->>R: Valid live generation
    S-->>W: 2xx (G2 completed)
    R->>S: GET object
    S-->>R: Generation G2
~~~

However, **single-object atomicity does not create a multi-object transaction**. If an application needs to update `manifest.json` and five data objects as a single atomic unit, those objects can become visible at different times. Design manifests that point to **fixed generations**, use immutable object names, or use an appropriate transactional system.

### 2.2. Strong Consistency Does Not Prevent Lost Updates

Suppose clients A and B both read G1:

~~~mermaid
sequenceDiagram
    participant A as Writer A
    participant S as Cloud Storage
    participant B as Writer B
    A->>S: GET state.json (G1)
    B->>S: GET state.json (G1)
    S-->>A: G1 = status PENDING
    S-->>B: G1 = status PENDING
    A->>S: PUT status PACKED (no precondition)
    S-->>A: Success: G2
    B->>S: PUT status CANCELLED (no precondition)
    S-->>B: Success: G3
    Note over S: G2 is replaced by G3
~~~

Both writes succeed and consistency remains intact: **G3 is the latest live version**. Yet A's update G2 was lost from a business standpoint. The solution is **optimistic concurrency control** via preconditions.

## 3. Important Exceptions When Saying "Consistent"

Not everything surrounding Cloud Storage is instantaneous.

### 3.1. Public Caches, Browsers, and CDNs

**Public objects can be cached.** A browser or caching layer can keep serving an older version until its TTL expires, even after the Cloud Storage origin received and overwrote the live object. If no cache duration is configured, a public object may be cached for up to **60 minutes** per documentation.

Never diagnose a stale browser response by concluding Cloud Storage lost strong consistency. Inspect `Cache-Control`, `Age`/cache headers, CDN config, URL versioning, and direct origin requests in an authorized environment.

**Best practice:** include a version or hash in object URLs for static assets (`app.4f2b.js`), or configure explicit cache policies and invalidations. For content needing immediate updates, design cache bypass / no-cache headers at the appropriate layers.

### 3.2. IAM Changes and Certain Bucket Configurations

**Granting or revoking IAM permissions** can incur propagation delay, unlike reading updated object metadata. **Recreating a bucket after deletion** can also involve delay. Certain bucket configuration changes, such as enabling **Object Versioning**, require waiting for propagation before relying on replacement/deletion behavior; documentation recommends waiting at least **30 seconds** after changing versioning settings.

A rare multi-region edge case: if the location holding a newly written copy becomes temporarily unavailable before replication completes, readers may receive a **retryable `500` error** rather than stale content. That is not a "stale read" result.

### 3.3. Strong Consistency Does Not Enforce Business Ordering

Storage guarantees you observe object state after a successful operation; **it does not enforce business rules** such as "an order must never transition from `SHIPPED` back to `NEW`." Applications must validate legal transitions and enforce preconditions at write time.

## 4. Generation: ID of an Object's Data Version

Each object generation has a numeric `generation` assigned by Cloud Storage.

~~~json
{
  "name": "orders/state.json",
  "bucket": "commerce-lab-data",
  "generation": "1735000000000123",
  "metageneration": "1",
  "contentType": "application/json",
  "size": "36"
}
~~~

The numbers above are **illustrative only**, not output captured from a live system.

Properties to remember:

1. `generation` identifies the **content version** of an object.
2. Recreating or overwriting a live object assigns a **different** generation from the old one.
3. Do not assume generations always increase monotonically over time: Google Cloud notes **a new generation's value is not guaranteed to be numerically larger than the old generation**.
4. Generations across two **different objects** are not a global clock; never compare them to determine event ordering.
5. To read a **specific version**, include the generation in the read request as supported by the API; reading by name alone targets the live version.
6. Updating metadata without changing object data **keeps the same generation**; only metageneration increments.

### 4.1. Generation Is Not a Timestamp

Never use `G2 > G1` as a business check for "newer." When business ordering is needed, store a sequence number, event timestamp, or logical version inside your application payload and apply CAS to the object. Generation detects **whether the object changed** since observation; it does not provide cross-object ordering.

### 4.2. Why Record the Generation?

When an application processes a message or task:

~~~text
Order A100
Object: orders/A100.json
Observed generation: G17
Message ID: event-8042
Proposed new status: PACKED
~~~

After processing, the app attempts to write the new version **only if the live generation is still G17**. If another writer already wrote G18, Cloud Storage rejects the update; the app reloads G18, re-evaluates business rules, and recomputes.

This is especially valuable when **GKE Pods**, **Cloud Run instances**, **Compute Engine VMs**, or CI/CD jobs have multiple writers touching the same object.

## 5. Metageneration: ID of the Metadata Version

`metageneration` is scoped to **each generation** and increments whenever that generation's metadata is updated.

Example:

| Event | Generation | Metageneration | Explanation |
| --- | --- | --- | --- |
| First upload of `state.json` | G1 | 1 | Creates initial content and metadata |
| Change custom metadata `owner` | G1 | 2 | Content unchanged |
| Change `Cache-Control` | G1 | 3 | Metadata updated again |
| Overwrite content | G2 | 1 | New generation gets its own metageneration |
| Update metadata on G2 | G2 | 2 | Unrelated to G1's metageneration |

**Metageneration is meaningful only together with generation.** Never compare `metageneration=2` of G1 with `metageneration=2` of G2 to infer identical metadata or matching state.

Metadata includes `Cache-Control`, `Content-Type`, custom metadata, hold/retention-related fields per API support, and other attributes. Some fields cannot be edited directly and only change on an **object rewrite**; consult [Object metadata](https://cloud.google.com/storage/docs/metadata) before choosing an operation.

### 5.1. Crucial Rule for Metadata CAS

**Whenever using `ifMetagenerationMatch` on an object, always combine it with `ifGenerationMatch`** to ensure you are editing metadata on the **exact intended generation**.

If you check only `metageneration=1`, another writer could delete and recreate the object. The new object G2 also starts at `metageneration=1`, so a lone metageneration check could match a **completely different** object than the one you observed. The pair `(generation, metageneration)` is the safe state-check key.

## 6. Preconditions: Comparing State Atomically with the Request

A **request precondition** is a condition attached to a Cloud Storage API call. Cloud Storage evaluates the condition **at the moment it processes the operation**. If the condition fails, the request is not applied.

| JSON API Parameter | Meaning | Result When Unmet |
| --- | --- | --- |
| `ifGenerationMatch=G` | Proceed only if live generation equals G | `412 Precondition Failed` |
| `ifGenerationMatch=0` | Write only if **no live version** exists for that name | `412` if a live object already exists |
| `ifMetagenerationMatch=M` | Proceed only if metageneration equals M | `412` |
| `ifGenerationNotMatch=G` | Proceed only if generation **differs from** G | For reads, usually returns `304 Not Modified` |
| `ifMetagenerationNotMatch=M` | Proceed only if metageneration differs from M | For reads, usually returns `304` |

The XML API uses corresponding headers such as `x-goog-if-generation-match`; the REST JSON API uses query parameters. HTTP `If-Match`/`If-None-Match` based on ETag can also work on certain requests, though generation/metageneration preconditions are typically cleaner to reason about in Cloud Storage.

### 6.1. Special Meaning of Generation `0`

~~~text
ifGenerationMatch=0

No live object with that name exists:
  → Object creation allowed.

A live object with that name exists:
  → 412 Precondition Failed.

Only noncurrent versions remain (versioned bucket):
  → Creating a new live object is still allowed.
~~~

**`0` does not mean "current generation equals 0"** and is not meant for deletes or metadata updates. Documentation recommends using this special value **only when writing object data**.

### 6.2. Combining Multiple Conditions

A metadata update request might succeed only when:

~~~text
ifGenerationMatch = G1
AND
ifMetagenerationMatch = 7
~~~

If **either condition** fails, the request is rejected. This prevents time-of-check to time-of-use (TOCTOU) races because validation and mutation occur together on the server inside the same request.

### 6.3. Never Use Unconditional "Check-Then-Write"

~~~text
Wrong:
  1. GET state.json, see G1
  2. if (G1 is the version to update)
  3. PUT state.json with no precondition

Right:
  1. GET state.json, save G1
  2. Compute new content
  3. PUT state.json with ifGenerationMatch=G1
  4. If 412: re-read and resolve conflict
~~~

**Key point:** the **PUT/PATCH/DELETE** request itself must carry the precondition. Reading beforehand alone does not stop another writer from slipping in between.

## 7. Three Most Important Safe Update Patterns

### 7.1. Create-if-Absent: Create Only If No Live Version Exists

Suppose a worker consumes an event and writes `results/event-8042.json`. If the event is redelivered, it should not overwrite the earlier result:

~~~bash
gcloud storage cp result.json \
  gs://BUCKET_NAME/results/event-8042.json \
  --if-generation-match=0
~~~

One writer succeeds; competing writers receive `412` once a live object exists with that name. This enforces "first writer wins" at the **object-name** level—not system-wide exactly-once execution by itself.

### 7.2. Update-if-Unchanged: Compare-and-Swap

Suppose an application read generation G1, computed a new status, and writes it back:

~~~bash
gcloud storage cp state-v2.json \
  gs://BUCKET_NAME/orders/state.json \
  --if-generation-match=GENERATION_OBSERVED
~~~

If nobody overwrote the object since G1 was read, the write succeeds and produces a new generation. If another writer modified the content, the request **fails with `412`** instead of silently overwriting.

### 7.3. Delete-Only-the-Observed-Version

A cleanup job lists older objects to delete. Between listing and deleting, another writer might replace an object under the same name. Deleting by name **without a precondition** risks deleting the brand-new copy.

~~~bash
gcloud storage rm gs://BUCKET_NAME/temp/result.json \
  --if-generation-match=GENERATION_OBSERVED
~~~

The precondition stops cleanup from deleting a live generation different from the one it evaluated. **`rm` genuinely deletes the object** (or moves it to soft-deleted/noncurrent per bucket configuration), so run it only after verifying bucket, name, generation, and retention.

## 8. Updating Metadata Without Losing Concurrent Edits

Suppose two actors read metadata concurrently:

~~~text
Initial:
  generation = G5
  metageneration = 3
  metadata = { owner: "team-commerce", stage: "draft" }

Writer A wants:
  stage = "approved"

Writer B wants:
  owner = "team-platform"
~~~

If both PATCH/UPDATE using stale metadata without preconditions, one update can overwrite or drop the other's fields depending on request construction. Safe pattern:

1. Read **both current generation and metageneration**.
2. Build the new metadata by **merging** changed fields without dropping unrelated keys.
3. Send the metadata update with **both `ifGenerationMatch=G5` and `ifMetagenerationMatch=3`**.
4. On `412`, re-read metadata, re-apply changes on the latest state, and retry per business rules.

~~~mermaid
sequenceDiagram
    participant A as Writer A
    participant B as Writer B
    participant S as Cloud Storage
    A->>S: GET metadata (G5, M3)
    B->>S: GET metadata (G5, M3)
    S-->>A: G5, M3
    S-->>B: G5, M3
    A->>S: PATCH stage, ifGen=G5, ifMeta=M3
    S-->>A: 2xx, G5/M4
    B->>S: PATCH owner, ifGen=G5, ifMeta=M3
    S-->>B: 412 (metadata changed)
    B->>S: Re-GET G5/M4, merge, then conditional PATCH
~~~

**Normal metadata updates do not create a new generation**, so using only `ifGenerationMatch=G5` would let both PATCHes succeed and clobber each other. To prevent **metadata** lost updates, add `ifMetagenerationMatch`.

## 9. CLI Lab: Observing Generations and Conflicts

This lab uses an **existing test bucket** where you are authorized to write. Never use a production bucket. Commands can incur **operation charges, storage charges**, and related fees. Ensure proper IAM permissions, and do not modify files outside the lesson scope if you are only reading.

### 9.1. Setup

~~~bash
gcloud auth list
gcloud config get-value project

# Read-only: inspect bucket in an approved project
gcloud storage buckets describe gs://BUCKET_NAME
~~~

Create two JSON files on your **lab machine**, containing no secrets or personal data:

~~~bash
printf '{"status":"PENDING","revision":1}\n' > state-v1.json
printf '{"status":"PACKED","revision":2}\n' > state-v2.json
~~~

### 9.2. Create Only If No Live Object Exists

~~~bash
gcloud storage cp state-v1.json \
  gs://BUCKET_NAME/lab-cas/state.json \
  --if-generation-match=0
~~~

If `lab-cas/state.json` already has a live version, the command returns `412`. **Do not remove the flag** to "bypass the error"; investigate why the object already exists.

### 9.3. Read Generation and Metageneration

~~~bash
gcloud storage objects describe \
  gs://BUCKET_NAME/lab-cas/state.json \
  --format="json(name,generation,metageneration,size,updated)"
~~~

Hypothetical output showing G1 and M1:

~~~json
{
  "name": "lab-cas/state.json",
  "generation": "1735000000000123",
  "metageneration": "1"
}
~~~

Record the **actual generation** from your output rather than copying the sample number above.

### 9.4. Overwrite Only If Generation Is Unchanged

~~~bash
gcloud storage cp state-v2.json \
  gs://BUCKET_NAME/lab-cas/state.json \
  --if-generation-match=GENERATION_V1
~~~

After success, read metadata again; the live object now has a **new generation**. Re-running the same command **still passing `GENERATION_V1`** returns `412` because the condition no longer holds. This is **expected behavior**, not a sign of Cloud Storage inconsistency.

### 9.5. Conditional Metadata Update

Read the new generation and metageneration (say G2 and M1), then run:

~~~bash
gcloud storage objects update \
  gs://BUCKET_NAME/lab-cas/state.json \
  --update-custom-metadata=reviewed-by=commerce \
  --if-generation-match=GENERATION_V2 \
  --if-metageneration-match=METAGENERATION_V2
~~~

On success, metadata updates and G2's metageneration increments. If another process edited metadata in the meantime, `412` prompts you to re-read before modifying.

### 9.6. Conditional Cleanup

~~~bash
# ONLY run in the lab after verifying exact name and generation!
gcloud storage rm gs://BUCKET_NAME/lab-cas/state.json \
  --if-generation-match=GENERATION_CURRENT
~~~

If **Object Versioning** or **soft delete** is enabled, deleted copies may remain stored per policy, so check billing and lifecycle rules instead of assuming every byte vanished. Avoid deleting buckets or using broad wildcards.

## 10. REST JSON API: Where Preconditions Are Passed

In the **Cloud Storage JSON API**, preconditions are passed as **query parameters**. Example create-if-absent upload:

~~~bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  --data-binary @state-v1.json \
  "https://storage.googleapis.com/upload/storage/v1/b/BUCKET_NAME/o?uploadType=media&name=lab-cas%2Fstate.json&ifGenerationMatch=0"
~~~

Here:

- `BUCKET_NAME` is your real lab bucket, URL-encoded if required by path rules.
- `name=lab-cas%2Fstate.json` is the URL-encoded object name.
- `ifGenerationMatch=0` is a **server-side** precondition, not a client-side pre-check.
- The access token comes from your authenticated CLI account; **never print tokens to logs or commit scripts containing tokens**.

Example replacement logic with generation G1:

~~~text
POST /upload/storage/v1/b/BUCKET_NAME/o
  ?uploadType=media
  &name=lab-cas%2Fstate.json
  &ifGenerationMatch=GENERATION_V1

If current live generation = G1:
  → 2xx + metadata of new generation.

If current live generation differs from G1:
  → HTTP 412 Precondition Failed.
~~~

For the **XML API**, the equivalent mechanism uses headers like `x-goog-if-generation-match`; do not mix JSON query parameters with XML headers when using a different API surface.

### 10.1. Conditional Reads and HTTP 304

If a client caches G1 locally and only wants to download when the live object changes, it can pass **`ifGenerationNotMatch=G1`** on supported read calls. While the object remains at G1, the API returns `304 Not Modified` so the client avoids re-downloading the bytes.

This differs from **`ifGenerationMatch=G1`**, which ensures "operate only if the version is still G1." Choose the condition matching your intent: **require unchanged** vs. **fetch only if changed**.

## 11. Java Example: Optimistic Concurrency When Writing JSON

This example uses the **Google Cloud Storage Java client library** (`com.google.cloud:google-cloud-storage`). It authenticates using **Application Default Credentials (ADC)**: prefer runtime identity on Cloud Run/GKE/Compute Engine, and local ADC or impersonation on developer workstations—never bundle service account JSON private keys.

### 11.1. Create or Replace Only If Unmodified

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageException;
import com.google.cloud.storage.StorageOptions;
import java.nio.charset.StandardCharsets;

public class ConditionalOrderWrite {
    public static void main(String[] args) {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                "Usage: ConditionalOrderWrite BUCKET OBJECT JSON_CONTENT");
        }

        String bucket = args[0];
        String object = args[1];
        byte[] data = args[2].getBytes(StandardCharsets.UTF_8);

        Storage storage = StorageOptions.getDefaultInstance().getService();

        // Read step can run concurrently with other writers.
        Blob observed = storage.get(bucket, object);

        // WRITE step carries precondition, so races after GET cannot cause lost updates.
        Storage.BlobTargetOption precondition =
            observed == null
                ? Storage.BlobTargetOption.doesNotExist()
                : Storage.BlobTargetOption.generationMatch(
                    observed.getGeneration());

        BlobInfo info = BlobInfo.newBuilder(BlobId.of(bucket, object))
            .setContentType("application/json")
            .build();

        try {
            Blob written = storage.create(info, data, precondition);
            System.out.println("Saved generation: " + written.getGeneration());
        } catch (StorageException e) {
            if (e.getCode() == 412) {
                System.err.println(
                    "Conflict: object changed; re-read and evaluate business rules.");
                return;
            }
            throw e;
        }
    }
}
~~~

**This example focuses on the precondition and omits business transition validation.** In real applications, deserialize G1 into a Java object, verify business invariants, construct new JSON, and write back with the observed generation. Never blindly overwrite with stale data just because `412` occurred.

### 11.2. Why Does `doesNotExist()` Correspond to Generation `0`?

The client library provides `Storage.BlobTargetOption.doesNotExist()` to express **upload only if no live object with that name exists**. Server-side, this corresponds to **`ifGenerationMatch=0`**.

Never write "check `storage.get(...) == null`, then upload unconditionally." Between GET and PUT, another writer could create the object. Only a **precondition on the write request itself** prevents that race.

## 12. Java Example: Updating Metadata with Version Pairs

Metadata updates can affect caches, downstream processors, or business attributes. The pattern below uses **both generation and metageneration**:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageException;
import com.google.cloud.storage.StorageOptions;
import java.util.HashMap;
import java.util.Map;

public class ConditionalMetadataUpdate {
    public static void main(String[] args) {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: ConditionalMetadataUpdate BUCKET OBJECT");
        }

        Storage storage = StorageOptions.getDefaultInstance().getService();
        Blob current = storage.get(args[0], args[1]);
        if (current == null) {
            throw new IllegalStateException("Object does not exist");
        }

        // Merge to preserve other existing custom metadata keys.
        Map<String, String> updatedMetadata = new HashMap<>();
        if (current.getMetadata() != null) {
            updatedMetadata.putAll(current.getMetadata());
        }
        updatedMetadata.put("reviewed-by", "commerce-platform");

        BlobInfo next = current.toBuilder()
            .setMetadata(updatedMetadata)
            .build();

        try {
            Blob saved = storage.update(
                next,
                Storage.BlobTargetOption.generationMatch(
                    current.getGeneration()),
                Storage.BlobTargetOption.metagenerationMatch(
                    current.getMetageneration()));
            System.out.println(
                "Metadata metageneration: " + saved.getMetageneration());
        } catch (StorageException e) {
            if (e.getCode() == 412) {
                System.err.println("Metadata conflict: re-GET and merge again.");
                return;
            }
            throw e;
        }
    }
}
~~~

If another writer **overwrote data** from G1 to G2, the generation precondition blocks the update. If another writer **only edited metadata** from G1/M3 to G1/M4, the metageneration precondition blocks the update. Together they prevent updating the wrong target or losing metadata edits.

**Note:** Never blindly copy old metadata into a retry after `412`. Refresh the object, verify permissions/conditions, and merge against the latest state.

## 13. Safe Deletes, Retries, and Idempotency

### 13.1. Why Retrying a Write Operation Can Be Dangerous

Suppose a client sends an upload, the server commits G2, and **the network drops before the client receives the response**. Thinking the upload failed, the client sends an unconditional retry—potentially creating G3 or overwriting a subsequent update from another writer.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Cloud Storage
    participant W as Other writer
    C->>S: PUT if generation=G1
    S-->>C: Server committed G2 (response lost)
    W->>S: PUT if generation=G2
    S-->>W: Success, G3
    C->>S: Unconditional retry PUT
    S-->>C: Succeeds yet overwrites G3 (unintended)
~~~

If the client **keeps `ifGenerationMatch=G1` on the retry**, the retry cannot overwrite G3. However, the retry may return `412` because **the client's own first attempt already succeeded**.

Therefore:

- **`412` does not by itself prove the initial write failed.**
- Re-read the object and compare **content/checksum, request ID, or a business operation marker** before concluding failure or success.
- If the current state no longer matches expectations, reconcile per business rules rather than dropping the precondition.

### 13.2. Errors That Should vs. Should Not Be Retried Identically

| Status | Typical Meaning | Action |
| --- | --- | --- |
| `412 Precondition Failed` | Generation or metageneration no longer matches observed state | **Conflict/reconcile**: re-GET, recompute, write only if still valid |
| `304 Not Modified` | Read "not match" condition was false | Reuse locally cached version |
| `404 Not Found` | Live object does not exist or target resource/generation is gone | Verify create/delete logic and permissions; do not blindly overwrite |
| `401 Unauthenticated` | Invalid or expired credentials | Check ADC/token |
| `403 Permission Denied` | IAM, policy, retention/hold, or other restriction | Check permissions and constraints; **never** bypass |
| `408, 429, 5xx` | Timeout, rate/quota limit, or transient error | Controlled retry with backoff and idempotency |
| `409 Conflict` | Other operation/API conflict type | Read exact message; do not treat identically to CAS `412` |

**Exponential backoff with jitter** helps for transient errors or retryable contention. However, blindly retrying the exact same precondition **after a `412`** will never make it succeed; you must re-read current state and recompute.

### 13.3. Retry Policies in the Java Client

The Cloud Storage Java client library retries idempotent and **conditionally idempotent** operations when appropriate preconditions/generations are present. Retry and timeout thresholds are configurable per library and environment.

**Never enable blind retries for unconditional writes.** If an operation has side effects outside Storage (publishing Pub/Sub messages, updating databases, or calling payment APIs), a Storage precondition **does not make the whole workflow exactly-once**. Use event IDs, deduplication keys, or transactional outboxes as needed.

## 14. Stable Object Reads and Ranged Reads

A large object may be downloaded across multiple **range** requests. If a client reads bytes 0–999 of G1, a writer overwrites the object with G2 in between, and the client requests bytes 1000–1999 **by name** without pinning the generation, the client can stitch bytes from **two different versions**.

~~~text
GET Range 0-999       → G1
Writer overwrite      → G2
GET Range 1000-1999   → G2
Reassembled           → Potentially corrupted data
~~~

Safe approach:

1. Read metadata and record generation G1.
2. When downloading multiple ranges, **pin generation G1** or use a generation-match precondition as supported by the API.
3. Verify responses and checksums; if that generation is no longer available, **never stitch** ranges from different versions.
4. If older versions must stay readable for long-running reads, consider **Object Versioning** or immutable object names.

**Strong consistency does not prevent an app from stitching ranges fetched across two separate points in time.** Generation pinning is the client's responsibility.

## 15. Source and Destination Preconditions for Copy and Compose

Cloud Storage supports **copy/rewrite** and **compose** from multiple source objects. These also face race conditions if a source or destination changes mid-operation.

### 15.1. Copy/Rewrite Object

Suppose a job copies `staging/report.json` to `published/report.json`. There are **two states to guard**:

- **Source:** is it still the exact generation the job validated?
- **Destination:** does it still not exist, or still match the old generation the job intends to replace?

The JSON API provides source preconditions prefixed with `ifSource...` such as `ifSourceGenerationMatch`, while the destination uses standard `ifGenerationMatch`. Verify support for those options in your API/client library before deploying.

~~~text
copy source Gsrc -> destination

Conditions:
  source generation == Gsrc
  AND destination generation == Gdst
or destination has no live object (generation-match=0).

If either fails:
  412, preventing writes against stale assumptions.
~~~

### 15.2. Composing Multiple Sources

When combining chunks into one object via **compose**, you can specify **generation-match per source object** plus a precondition on the destination. If another writer alters a source beforehand, `412` prevents assembling mismatched parts.

~~~mermaid
flowchart TD
    S1["part-a: generation A1"] --> C["Compose destination"]
    S2["part-b: generation B1"] --> C
    P["source gen A1 + B1<br/>destination generation guard"] -. "Preconditions" .-> C
    C --> D["result.json: new generation"]
~~~

Compose is a **single operation creating the destination object**, not a transaction synchronizing external systems. Source objects still require their own lifecycle rules and IAM.

## 16. Object Versioning, Soft Delete, and Retention: Three Distinct Problems

Preconditions protect a **single operation**. They do not replace version history or protect against accidental deletions.

| Mechanism | Question Answered | Does Not Solve |
| --- | --- | --- |
| **Preconditions** | "Write/delete only if the object still matches the state I observed?" | Does not automatically retain old versions |
| **Object Versioning** | "Keep noncurrent versions when the live version is overwritten/deleted?" | Does not block an authorized writer from writing bad data; does not protect bucket deletion |
| **Soft delete** | "Can deleted/overwritten objects or buckets be restored within a window?" | Does not prevent lost updates at write time |
| **Retention policy / object hold** | "Block deletion/overwrite before an expiration period or while held?" | Does not replace generation-based concurrency control |
| **IAM** | "Who is authorized to read/write/delete objects?" | Does not verify whether a writer acted on stale data |
| **Lifecycle rules** | "Which objects/versions transition classes or delete on schedule?" | Does not provide multi-object transactions |

### 16.1. Versioning and Generation

With Object Versioning enabled, overwrites create a **new live generation** and demote the old generation to **noncurrent**. This fits apps needing programmatic access to historical versions by generation. Noncurrent versions still incur **storage charges**; pair with lifecycle management.

**Important:** `ifGenerationMatch=0` can still create an object when only noncurrent versions exist. It checks for a **live object**, not "whether this name ever existed in history."

### 16.2. Soft Delete Differs from Noncurrent Versions

Cloud Storage generally enables soft delete by default on supported buckets with a **default 7-day retention** at the time of referenced documentation; exceptions and overrides vary by bucket type and policy. Once an object is soft-deleted, it **cannot be read or written normally**, though it can be **restored** within permissions and the retention window. In versioned buckets, deleting a live version moves it to **noncurrent** first, unlike non-versioned buckets.

Never assume from a `generation` value that a soft-deleted copy remains directly readable like a noncurrent version. Check exact state and APIs.

### 16.3. Retention and Object Lock Can Block Overwrites Even When CAS Matches

If an object is protected by a **retention policy, object retention lock, or hold**, an overwrite or delete request can be rejected **even when the generation precondition matches**. CAS is necessary for concurrency safety, not a bypass around retention controls.

## 17. Designing Safe State Objects for Multi-Replica Java Apps

Suppose an application runs on **Cloud Run**, where each instance processes Pub/Sub messages and updates `orders/A100.json` in Cloud Storage.

### 17.1. Unsafe Design

~~~text
1. Instance A reads status=PENDING.
2. Instance B also reads status=PENDING.
3. A updates status=PACKED, uploads unconditionally.
4. B updates status=CANCELLED, uploads unconditionally.
5. One update is lost, yet both instances report success.
~~~

### 17.2. Safer Design with CAS

~~~mermaid
flowchart TD
    E["Receive event/order ID"] --> G["GET object + generation"]
    G --> V{"Valid transition from observed state?"}
    V -->|No| N["Reject/ignore per business rule"]
    V -->|Yes| U["Build new state payload"]
    U --> C["PUT with ifGenerationMatch=G"]
    C --> R{"Result?"}
    R -->|2xx| OK["Save new generation + ack processing"]
    R -->|412| GET["Re-GET and decide merge/reject/bounded retry"]
    GET --> V
    R -->|429/5xx| RET["Exponential backoff, keep precondition"]
    RET --> C
~~~

Production systems also need:

1. **Business invariants:** enforce valid state-machine transitions so delayed messages never revert state.
2. **Deduplication:** record event IDs or logical revisions to recognize already-processed messages.
3. **Read pinning:** pin generation whenever downloading multi-chunk objects.
4. **Bounded retries:** cap reconciliation attempts, monitor contention, and route persistent conflicts to a dead-letter queue.
5. **Metrics:** track `412` rates, retries, payload conflicts, end-to-end latency, and skipped events.
6. **Access control:** grant runtime service accounts least-privilege permissions on buckets/prefixes; avoid long-lived JSON keys and broad roles.
7. **Data recovery:** enable soft delete/versioning where suitable, maintain clear retention/lifecycle policies, and test restores.

### 17.3. When Should You Not Use an Object as a Transactional Database?

If many writers constantly update the **same object** like a hot counter or ledger row, CAS conflicts and retries will spike. Cloud Storage is not a row-level transactional database and does not support atomic multi-object compare-and-swap.

Evaluate **Firestore, Cloud SQL, Spanner**, or another transactional/locking store when you need multi-record updates, indexed queries, atomic counters, or cross-record invariants. Cloud Storage excels at **immutable blobs, artifacts, backups, large objects**, and low-contention or retryable updates.

## 18. Observability, Security, and Cost

### 18.1. Metrics to Monitor

| Signal | Purpose | Action |
| --- | --- | --- |
| `412` rate on writes/PATCH/DELETE | Measure contention and stale-client attempts | Inspect business logic, hot objects, and retry loops |
| `429` and `5xx` | Distinguish quota limits from transient failures | Backoff with jitter; inspect quotas and throttling |
| Pre-write GET count | Measure CAS overhead | Cache valid generations where safe to cut round trips |
| Download range mismatches | Detect multi-version range stitching | Pin generations and verify checksums |
| Object Versioning / soft-delete storage | Cost of retained versions and deleted objects | Tune lifecycle and retention policies |
| Egress and operation counts | Cost of metadata GETs, retries, and data transfer | Inspect Billing Reports; optimize payload size and frequency |
| IAM/policy errors | Verify runtime identity and boundaries | Audit IAM, deny policies, and VPC Service Controls if used |

**Do not treat every `412` as an infrastructure outage.** Under a proper CAS design, occasional conflicts are an **expected signal**. Track whether the rate breaches acceptable thresholds, inflates latency, or stalls progress.

### 18.2. Preconditions Have Costs

The read-metadata-then-conditional-write pattern adds an **extra request** and network round trip. For latency- or cost-sensitive workloads:

- When creating a known-new object by design, pass `ifGenerationMatch=0` without a prior GET.
- When the app already received the generation in an upload response, keep it for the next step.
- Do not poll at high frequency just to detect whether a generation changed.
- Review **Cloud Storage operation pricing, egress, and retry amplification** when tuning strategies.

### 18.3. IAM and VPC Service Controls Still Apply

Preconditions do not bypass access control. A request with a matching generation still needs appropriate `storage.objects.get/create/delete/update` permissions and must pass VPC Service Controls, org policies, and retention/hold rules.

Across GCP services in this module, use **ADC, Workload Identity Federation, runtime-bound service accounts**, least-privilege IAM, and Cloud Audit Logs. Never write access tokens, signed URLs with secrets, PII, or sensitive object payloads into debug logs just to troubleshoot `412`s.

## 19. Troubleshooting Common Errors

| Symptom | Likely Cause | Priority Check |
| --- | --- | --- |
| Create-if-absent upload gets `412` | Live object with that name already exists | Read current generation; check duplicate event handling |
| Overwrite gets `412` | Another writer updated the generation | Re-read, validate transition, retry with new generation if valid |
| Metadata patch gets `412` | Metadata changed or object was overwritten | Compare both generation and metageneration |
| GET returns `404` after DELETE | Live object was deleted (expected with strong consistency) | Check soft delete / noncurrent versions if recovery is needed |
| Browser still displays old image | Public cache / CDN TTL | Check `Cache-Control`, cache keys, and invalidation |
| Object appears in listing, yet worker saw "lost update" | Two writers overwrote unconditionally | Check generation logs; add CAS preconditions |
| Large download fails checksum | Ranged reads stitched multiple generations | Pin generation across every range request |
| Retry upload with same request token hits `412` | First attempt succeeded, changing the generation | Reconcile via checksum/event ID; never drop precondition |
| `403` despite matching generation | IAM/deny/VPC SC/retention block | Check principal, permissions, and policies |
| Cannot read old generation | Versioning disabled, or version deleted/soft-deleted | Inspect bucket policy and object history |
| Generation changed while metageneration reset to 1 | Object was rewritten | Normal behavior for a new generation |
| `304 Not Modified` | Read non-match condition was not met | Use locally cached copy of that version |
| Errors rise when scaling Cloud Run | Many instances editing a hot object concurrently | Partition objects, move state to a DB, or coordinate writes |

### 19.1. Repeatable Debugging Sequence

~~~mermaid
flowchart TD
    A["Object update behaved unexpectedly"] --> B{"Did API return 412?"}
    B -->|Yes| C["Compare observed G/M with live G/M"]
    C --> D["Identify competing writer or duplicate retry"]
    D --> E["Re-read + reconcile per business rules"]
    B -->|No| F{"401/403/404/429/5xx?"}
    F -->|401/403| G["Check ADC, IAM, deny/VPC SC/retention"]
    F -->|404| H["Check live/noncurrent/soft-deleted state"]
    F -->|429/5xx| I["Retry with idempotency and backoff"]
    E --> J["Record metrics, verify post-handling state"]
    G --> J
    H --> J
    I --> J
~~~

## 20. Self-Check Exercises

**Question 1.** A G1 upload returns success, and another client immediately runs GET by name yet receives old G0. Is this expected behavior from the Cloud Storage origin?

*Hint:* No. Origin object read-after-write is strongly consistent; inspect caches/CDNs, how the client resolves resources, or special system errors.

**Question 2.** Two workers both read G1. Worker A writes G2 first; worker B attempts to write with `ifGenerationMatch=G1`. What happens?

*Hint:* Worker B receives `412`; it is prevented from silently overwriting G2.

**Question 3.** Does `ifGenerationMatch=0` mean the object has generation 0?

*Hint:* No. It is a special condition meaning "no live object exists with this name," even if noncurrent versions exist.

**Question 4.** Writer A updates only metadata from G1/M3 to G1/M4. Writer B checks only `ifGenerationMatch=G1` and PATCHes metadata it read earlier. Is that safe?

*Hint:* Not yet. Generation is still G1; Writer B must also pass `ifMetagenerationMatch=M3` to detect the metadata change.

**Question 5.** Why should you never use metageneration alone?

*Hint:* When an object is overwritten with a new generation, the new generation's metageneration can restart at 1; pair it with generation.

**Question 6.** A client sent a PUT with `ifGenerationMatch=G1`, lost connectivity, and got `412` on retry. Is it certain the first PUT failed?

*Hint:* No. The first attempt may have succeeded in writing G2 before the response dropped. Re-read and compare operation markers/checksums.

**Question 7.** Can a program downloading a large object in multiple ranges assemble corrupted data despite Cloud Storage's strong consistency?

*Hint:* Yes, if an overwrite happens between range requests. Pin the generation so every range belongs to the same version.

**Question 8.** Object Versioning is enabled; the live object was deleted and became noncurrent. Will a new upload with `ifGenerationMatch=0` succeed?

*Hint:* Yes, if no live version exists with that name; precondition `0` does not require an empty version history.

**Question 9.** Why does enabling Object Versioning not replace preconditions?

*Hint:* Versioning saves old copies, yet another writer can still overwrite the live version inconsistently with business rules. Preconditions block the race at write time.

**Question 10.** Should a `412` immediately trigger infinite retries?

*Hint:* No. It usually signals a conflict requiring re-read/reconciliation; retrying forever with the old expected generation cannot succeed.

**Question 11.** A public webpage still displays an old image after an overwrite, while the `gcloud` API reads new metadata. What is the likely cause?

*Hint:* Public cache, browser cache, or CDN, governed by `Cache-Control` and TTLs.

**Question 12.** A job copying an object from staging to production wants to guard against both source edits and unexpected destination changes. What must it check?

*Hint:* Source generation and destination generation/existence via API-supported preconditions, alongside proper IAM.

**Question 13.** An API updates two objects A and B; both PUTs are atomic. Does that make the pair a transaction?

*Hint:* No. Atomicity applies per individual object, not across multiple objects.

**Question 14.** A live object has generation G2 and metageneration M1. Should you compare M1 with G1's M5 to conclude G2 has "older" metadata?

*Hint:* No. Metageneration is only meaningful within the same generation.

**Question 15.** Which use case fits Cloud Storage CAS better: updating a low-contention manifest or a hot counter updated thousands of times/second by many workers?

*Hint:* Low-contention manifest. Hot counters need dedicated transactional/atomic-counter stores like a database.

## 21. Production Preconditions Checklist

- [ ] Every critical overwritten object has a **CAS or immutable-naming** strategy.
- [ ] New uploads use **`ifGenerationMatch=0`** when preventing duplicate creation.
- [ ] Read-based overwrites/deletes use **`ifGenerationMatch=G`**.
- [ ] Metadata updates pass **both G and M** to protect observed state.
- [ ] Never treat generation numbers as cross-object timestamps or sequences.
- [ ] Never perform GET followed by an unconditional PUT.
- [ ] Handle `412` as a conflict with a reconciliation policy—never drop conditions.
- [ ] Network retries preserve idempotency, use backoff, and check ambiguous successes.
- [ ] Multi-range downloads pin generation or use matching read preconditions.
- [ ] Copy/compose operations guard both **source and destination preconditions** when contention is possible.
- [ ] Tested concurrent writers and dropped-response failure modes.
- [ ] Team clearly understands Object Versioning, soft delete, retention, and lifecycle do not replace CAS.
- [ ] Cache-Control/CDN and IAM propagation are separated from origin object strong consistency.
- [ ] Least-privilege IAM, ADC/WIF, and audit logs are configured without logging secrets.
- [ ] Monitoring tracks 412 rates, retries, operation charges, and RTO/RPO for recovery.
- [ ] Multi-object transactions are offloaded to a database rather than abusing object updates.

## 22. Key Takeaways

- **Cloud Storage strong consistency** for reads/writes, deletes, metadata, and object listings **does not stop two writers from overwriting each other**.
- **`generation`** identifies an object's data version; each overwrite produces a different generation without guaranteeing monotonically increasing values.
- **`metageneration`** counts metadata revisions for **a single generation**; it starts at 1 and must always be evaluated alongside generation.
- **`ifGenerationMatch=0`** implements create-if-absent for **live objects**.
- **`ifGenerationMatch=G`** implements compare-and-swap for writes/deletes while state G holds.
- **`ifMetagenerationMatch=M`** should accompany generation-match when updating metadata.
- **`412 Precondition Failed`** protects against conflicts; apps must re-read and decide rather than blindly overwriting.
- **Conditional retries** prevent non-idempotent operations or dropped responses from corrupting data.
- **Single-object atomicity differs from multi-object transactions**; ranged reads must pin generations to avoid mixing versions.
- **Object Versioning, soft delete, IAM, retention, caching, and Billing** are distinct complementary layers that do not replace preconditions.

In Java systems running on Compute Engine, GKE, or Cloud Run, the critical question before writing an object is not only **"Do I have write permission?"**, but also **"Is this still the exact version I read, and if someone else wrote first, how should business logic handle it?"** Preconditions turn that answer into an invariant enforced directly by Cloud Storage.

## Official Reference Documentation

- [Cloud Storage consistency](https://cloud.google.com/storage/docs/consistency)
- [Request preconditions](https://cloud.google.com/storage/docs/request-preconditions)
- [Object metadata: generation and metageneration](https://cloud.google.com/storage/docs/metadata)
- [Cloud Storage retry strategy](https://cloud.google.com/storage/docs/retry-strategy)
- [Object Versioning](https://cloud.google.com/storage/docs/object-versioning)
- [Soft delete](https://cloud.google.com/storage/docs/soft-delete)
- [Object Lifecycle Management](https://cloud.google.com/storage/docs/lifecycle)
- [Control data lifecycles](https://cloud.google.com/storage/docs/control-data-lifecycles)
- [Upload objects from memory — Java sample](https://cloud.google.com/storage/docs/samples/storage-file-upload-from-memory)
- [Set object metadata — Java sample](https://cloud.google.com/storage/docs/samples/storage-set-metadata)
- [gcloud storage cp](https://cloud.google.com/sdk/gcloud/reference/storage/cp)
- [gcloud storage objects update](https://cloud.google.com/sdk/gcloud/reference/storage/objects/update)
- [gcloud storage rm](https://cloud.google.com/sdk/gcloud/reference/storage/rm)
- [Cloud Storage pricing](https://cloud.google.com/storage/pricing)
