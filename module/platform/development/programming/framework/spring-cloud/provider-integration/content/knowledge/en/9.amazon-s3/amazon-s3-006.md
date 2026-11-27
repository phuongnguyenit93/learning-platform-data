# Amazon S3: Pagination, conditional writes, and overwrite control

## Learning objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, Spring Boot connects to managed services from AWS, Azure, and Google Cloud to access storage, messaging, data, and protect identities, permissions, and secrets. For **Amazon S3**, two key problems after learning basic object PUT/GET are:

- **Pagination:** retrieving part of an object list at a time, handling large datasets without loading everything into RAM or holding HTTP requests open too long.
- **Conditional writes:** creating or replacing an object only when its current state satisfies a condition, preventing accidental overwrites when multiple clients update the same key.

This lesson explains `ListObjectsV2`, `continuationToken`, `prefix`, `delimiter`, AWS SDK for Java v2 paginators, `If-None-Match`, `If-Match`, `ETag`, S3 Versioning behavior, and limitations when coordinating with a business database. Examples use **Spring Cloud AWS** with **AWS SDK for Java v2** and include permission checks, error handling, integration testing, and comparisons with Azure/Google Cloud.

Upon completion, learners can:

1. Implement a document-listing API with page-size limits and continuation cursors.
2. Distinguish `ListObjectsV2` from database queries and explain why pagination does not provide a transactional snapshot.
3. Write objects with **create-only** or **replace-if-unchanged** semantics using preconditions.
4. Properly handle **HTTP 412 Precondition Failed** and **HTTP 409 ConditionalRequestConflict**.
5. Know when to use versioning, immutable keys, idempotency, and database optimistic locking.
6. Design concurrency tests proving two requests contending for the same key do not silently overwrite each other.

> Examples use the `io.awspring.cloud` namespace of Spring Cloud AWS and `software.amazon.awssdk` of AWS SDK v2. Choose a Spring Cloud AWS version compatible with your actual Spring Boot version; some conditional write options depend on the AWS SDK/S3 API version and must be verified during implementation.

## 1. S3 model to recall before paginating and updating

An S3 object is identified by **bucket + object key**. Example:

~~~text
s3://training-private-files/tenants/t-42/reports/2026/summary.pdf
     └────── bucket ─────┘└──────────── object key ─────────────┘
~~~

A bucket holds objects; a key is a **case-sensitive** string. Segments like `tenants/`, `reports/`, `2026/` are displayed like folders in the S3 Console, yet in reality are typically just **prefixes** inside the key. When listing, the application filters by prefix; when reading/writing, it uses the exact bucket and key.

In a bucket without versioning enabled, a new PUT to the same key replaces the current content. In a versioning-enabled bucket, PUT creates a new current version and can preserve previous versions. **Versioning keeps history, but does not by itself resolve conflicts when two people edit the same document**: whichever request arrives later can still become the current version.

~~~mermaid
flowchart LR
    A["Business document #42"] --> DB["Database: owner, tenant, key, version"]
    DB --> S["S3: bucket + object key"]
    S -->|"LIST by prefix"| L["Object page / continuationToken"]
    S -->|"PUT with If-Match or If-None-Match"| W["Condition check at S3"]
    W -->|"Condition met"| OK["Create/replace object"]
    W -->|"Condition failed"| ERR["HTTP 412 / conflict 409"]
~~~

**Authorization is a separate step:** if the backend has an IAM role able to read all objects under `tenants/*`, the application must still verify the user is allowed to access the corresponding tenant before listing or updating.

## 2. Why must LIST be paginated?

A bucket can hold millions of objects. If an API downloads the entire listing before returning a response:

- It consumes many S3 requests and processing time, risking web server timeouts.
- It can retain excessive metadata/keys in heap memory.
- It is unsuitable for UIs where users view only 20–100 items at a time.
- A bucket-wide listing can leak object names belonging to other tenants or workflows if authorization is weak.

S3 provides the **`ListObjectsV2`** API to fetch listings page by page. Each request can set `maxKeys`, up to **1,000** for general-purpose buckets; fewer items may be returned. When more items remain, the response sets `isTruncated` and provides a `nextContinuationToken` to fetch the next page.

### 2.1. Parameters of `ListObjectsV2`

| Property | Meaning | Things to watch |
| --- | --- | --- |
| `bucket` | Bucket to list | Must fall within granted IAM scope |
| `prefix` | Return only keys starting with this string | Not a SQL search filter or authorization boundary on its own |
| `delimiter` | Group keys by separator character, usually `/` | Produces `CommonPrefixes`; does not create real folders |
| `maxKeys` | Limit number of entries in one response | Standard API max 1,000; not an `offset` |
| `continuationToken` | Continuation token from previous response | Opaque token; do not decode, edit, or construct from keys |
| `startAfter` | Start after a specified key (when supported by API) | Not the same as continuation token; unsupported for directory buckets |
| `fetchOwner` | Request owner information | Usually unnecessary for standard user APIs |

Commonly returned fields:

- `contents()`: list of `S3Object` items with key, size, last-modified timestamp, ETag, and summary attributes.
- `commonPrefixes()`: grouped prefixes when using `delimiter`.
- `isTruncated()`: whether more results follow.
- `nextContinuationToken()`: token used to continue.
- `keyCount()`: number of returned items counted per API rules (may count each `CommonPrefixes` entry as one item); **not the total object count in the bucket**.

`ListObjectsV2` does not return object bodies and is not a way to run arbitrary queries on `Content-Type`, user metadata, JSON content, or business owners. Index those attributes in the **application database** or an appropriate search/query system.

### 2.2. Prefix and delimiter creating a "folder" view

Suppose a bucket contains:

~~~text
tenants/t-42/reports/2025/a.pdf
tenants/t-42/reports/2025/b.pdf
tenants/t-42/reports/2026/c.pdf
tenants/t-42/images/logo.png
tenants/t-99/reports/private.pdf
~~~

With `prefix = tenants/t-42/reports/`, S3 lists only report keys of tenant t-42 matching that exact string prefix. Adding `delimiter = "/"`, the response can return `commonPrefixes`:

~~~text
tenants/t-42/reports/2025/
tenants/t-42/reports/2026/
~~~

That is purely **key-string grouping**. S3 has no corresponding physical directories and does not require separate objects representing those prefixes.

## 3. Configuring Spring Boot to call S3

### 3.1. Dependencies and application configuration

A Maven project can import the Spring Cloud AWS BOM and add the S3 starter:

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
</dependencies>
~~~

The `spring-cloud-aws.version` property must be declared with a release compatible with Spring Boot. The starter configures an AWS SDK v2 `S3Client` bean ready to inject into Spring services.

~~~yaml
# application.yml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  storage:
    bucket: ${S3_BUCKET_NAME}
    list-page-size: 50
~~~

`app.storage.*` are **application-defined properties**, not automatic S3 starter settings. The Region must match the bucket. Supply credentials via the AWS default provider chain (profile/SSO during development, IAM role or workload identity in deployment), never hard-coding access keys/secret keys in config.

### 3.2. Required IAM permissions

A service that both LISTs and PUTs objects under `tenants/` can use this illustrative policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListTenantPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::training-private-files",
      "Condition": {
        "StringLike": {
          "s3:prefix": ["tenants/", "tenants/*"]
        }
      }
    },
    {
      "Sid": "ReadWriteTenantObjects",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::training-private-files/tenants/*"
    }
  ]
}
~~~

`s3:ListBucket` applies to the **bucket ARN**; `s3:GetObject` and `s3:PutObject` apply to the **object ARN**. `s3:prefix` constrains only the LIST request parameter, not GET/PUT. The role in this example has **no** delete permission.

This policy is still broader than a single application user's permissions: the backend must verify the user/tenant before constructing a prefix or key. If using SSE-KMS, KMS permissions/key policies and explicit denies in bucket policies also apply. In production, scope IAM down to actual data and tasks rather than using this sample policy to grant broad tenant access unnecessarily.

## 4. Implementing single-page LIST with `S3Client`

### 4.1. Service bounding page size and prefix

The following example returns **one page** of objects. `tenantId` must be verified from authentication or the database before calling the service so users cannot pick another tenant.

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.ListObjectsV2Request;
import software.amazon.awssdk.services.s3.model.ListObjectsV2Response;
import software.amazon.awssdk.services.s3.model.S3Object;

@Service
public class S3TenantListingService {
    private final S3Client s3;
    private final String bucket;

    public S3TenantListingService(
            S3Client s3,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    public record ObjectSummary(
            String key, long size, Instant modifiedAt, String eTag) {}

    public record ObjectPage(
            List<ObjectSummary> items, String nextToken) {}

    public ObjectPage listOnePage(
            String authorizedTenantId,
            String continuationToken,
            int requestedSize) {

        if (authorizedTenantId == null ||
                !authorizedTenantId.matches("[a-zA-Z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid Tenant ID");
        }
        if (requestedSize < 1 || requestedSize > 100) {
            throw new IllegalArgumentException("pageSize must be between 1 and 100");
        }

        String prefix = "tenants/" + authorizedTenantId + "/";
        ListObjectsV2Request.Builder builder =
                ListObjectsV2Request.builder()
                        .bucket(bucket)
                        .prefix(prefix)
                        .maxKeys(requestedSize);

        if (continuationToken != null &&
                !continuationToken.isBlank()) {
            builder.continuationToken(continuationToken);
        }

        ListObjectsV2Response response =
                s3.listObjectsV2(builder.build());

        List<ObjectSummary> items =
                response.contents().stream()
                        .map(this::toSummary)
                        .toList();

        String nextToken =
                Boolean.TRUE.equals(response.isTruncated())
                        ? response.nextContinuationToken() : null;

        return new ObjectPage(items, nextToken);
    }

    private ObjectSummary toSummary(S3Object object) {
        return new ObjectSummary(
                object.key(),
                object.size(),
                object.lastModified(),
                object.eTag());
    }
}
~~~

This snippet targets Java versions supporting `Stream.toList()` (Java 16+, fitting most modern Spring Boot projects). `ObjectSummary` contains no object body; `size` is in bytes. `nextToken` is S3-returned data, not a page number or value you can increment by `+1`.

**Important cursor safety note:** the example passes S3's token straight through for API clarity. When exposing tokens to clients in production, treat them as **untrusted input**: enforce length limits, re-verify tenant and filters on every request, and never rely on a token to bypass authorization. To prevent clients from tampering with or reusing tokens across queries, wrap the token with `tenantId + prefix + pageSize/filters` and HMAC-sign it on the backend or store session-bound cursors; avoid logging tokens indiscriminately.

### 4.2. Exposing the list as a cursor API

A business API might receive:

~~~http
GET /api/documents?pageSize=50
Authorization: Bearer <application-token>
~~~

And return:

~~~json
{
  "items": [
    {
      "key": "tenants/t-42/reports/2026/a.pdf",
      "size": 8192,
      "modifiedAt": "2026-11-24T02:00:00Z",
      "eTag": "\"sample-etag\""
    }
  ],
  "nextToken": "<opaque-token>"
}
~~~

The values in the example are mocked; real tokens are generated by S3 and must be passed back **verbatim** on the next request. A standard endpoint may **omit raw S3 keys** and return `documentId` plus metadata from the database, especially if key names carry internal structure.

The controller flow should be:

1. Authenticate the user.
2. Determine tenant/prefix from trusted application data.
3. Enforce `pageSize` within a reasonable bound.
4. Call `listOnePage` with the constrained prefix.
5. Return `items + nextToken`; on the final page `nextToken = null`.

There is no reason to eagerly read additional pages if the user only asks for the first page.

## 5. Paginator: iterating multiple pages in batch jobs

When a **bounded job** needs to scan all keys under a prefix, AWS SDK v2 provides a paginator:

~~~java
ListObjectsV2Request request =
        ListObjectsV2Request.builder()
                .bucket(bucket)
                .prefix("tenants/t-42/reports/")
                .maxKeys(100)
                .build();

for (ListObjectsV2Response page :
        s3.listObjectsV2Paginator(request)) {
    for (S3Object object : page.contents()) {
        processOneKey(object.key());
    }
}
~~~

`processOneKey` is batch job logic; the example just shows iteration. The paginator manages continuation tokens between pages automatically, yet **each page is still an S3 network call**. Avoid collecting all paginator results into a massive `List` if the bucket has many objects.

Batch design notes:

- Enforce limits on total keys/pages, deadlines, cancellation, and controlled retries.
- `processOneKey` should have **idempotency** or checkpointing because jobs can stop and restart.
- LIST is a read operation with request charges; large key counts produce many requests.
- Objects added or deleted mid-job can affect subsequent pages; do not treat all pages as a single point-in-time snapshot.
- If a batch job needs business data in a deterministic order, use a database/query or an explicit snapshot source instead of assuming LIST provides transactional isolation.

### 5.1. When to use `StartAfter`?

With **general-purpose buckets**, `StartAfter` can start listing after a known key, such as in sequential processing jobs. However:

- `StartAfter` is **not** `ContinuationToken`.
- `StartAfter` is not supported in **S3 directory buckets**.
- When the bucket changes concurrently, a key checkpoint does not produce a stable snapshot.
- If your code is simply paging through `ListObjectsV2` results, prefer `NextContinuationToken` returned by S3.

Do not manually substitute `lastKey` as a continuation token: the token is an **opaque** string generated by S3 and cannot be derived from object names.

### 5.2. Ordering and consistency

S3 provides **strong read-after-write consistency** for PUT/DELETE and subsequent GET/LIST after operations succeed. However, that does not mean consecutive LIST pages observe a **consistent snapshot of the whole bucket**.

Example:

~~~text
09:00 Page 1: a.pdf, b.pdf, c.pdf
09:01 Another app creates aa.pdf, deletes b.pdf
09:02 Page 2: uses continuationToken from page 1
~~~

Page 2 is not guaranteed to reflect the exact state of the bucket at 09:00. For general-purpose buckets, LIST results are generally in lexicographical key order; **directory buckets do not guarantee the same lexicographic ordering**. If the UI needs sorting by timestamp, display name, or approval status, query a database/index supporting explicit sorting.

### 5.3. `Delimiter` can affect page size

When `delimiter("/")` is supplied, S3 can return `CommonPrefixes` alongside `contents`. When paginating a folder-like view, do not count only `contents().size()` and assume the page was short: each `CommonPrefixes` entry counts toward the returned item limit.

If an API must list both logical folders and direct objects under a prefix, design the response with both sections:

~~~json
{
  "objects": [
    {"key": "tenants/t-42/reports/readme.txt"}
  ],
  "prefixes": [
    "tenants/t-42/reports/2025/",
    "tenants/t-42/reports/2026/"
  ],
  "nextToken": "<opaque-token>"
}
~~~

## 6. Overwrite issues when multiple clients PUT concurrently

Suppose two users edit the same report simultaneously:

~~~text
09:00 Object reports/status.json contains version A
09:01 Client 1 reads A
09:01 Client 2 reads A
09:02 Client 1 writes content B
09:03 Client 2 writes content C from stale A

Result with unconditional PUT: C becomes current content;
change B is logically overwritten.
~~~

S3 Versioning can retain version B in history, yet client 2 remains unaware it edited stale data. This is a **lost update**. Solutions depend on your goal:

| Goal | Solution |
| --- | --- |
| Every upload must create a new object | Random/immutable key, optionally combined with `If-None-Match: *` |
| Create object only if key does not exist yet | Conditional PUT with `If-None-Match: *` |
| Replace content only if object has not changed since read | Conditional PUT with `If-Match` using the read ETag |
| Retain content history across edits | S3 Versioning and store version IDs when needed |
| Maintain accurate permissions/owner/business state | Optimistic locking/transactions in the database |
| Recover after retries/timeouts | Idempotency keys, request state verification, and appropriate checksums |

**Do not rely on HEAD followed by a normal PUT to guarantee a key is unused.** Between those two requests, another client can create the object. Send the precondition to **S3 itself inside the write request** so it is evaluated atomically at write time.

## 7. `If-None-Match: *` — create only when no current object exists

The HTTP header **`If-None-Match: *`** is a precondition for PUT: the request succeeds only if S3 determines no current object exists for that key at evaluation time. With AWS SDK v2 supporting conditional writes, use the builder:

~~~java
import java.nio.charset.StandardCharsets;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

byte[] bytes = "New report".getBytes(StandardCharsets.UTF_8);

PutObjectRequest put = PutObjectRequest.builder()
        .bucket(bucket)
        .key("tenants/t-42/reports/new-report.txt")
        .contentType("text/plain; charset=UTF-8")
        .ifNoneMatch("*")
        .build();

s3.putObject(put, RequestBody.fromBytes(bytes));
~~~

If the key has no current object, the request creates it; if a current object already exists, S3 rejects the precondition with **HTTP 412 Precondition Failed**. Under concurrent writes, S3 may also return **HTTP 409 ConditionalRequestConflict**; handle retries after checking state rather than treating it as a generic network failure.

**Common points of confusion:**

1. `If-None-Match` is a condition on a **specific PUT request**, not a bucket-level setting enabled automatically.
2. The `*` means checking whether any current object exists, not a wildcard over keys or prefixes.
3. If the bucket has versioning enabled and the **current version is a delete marker**, a conditional create can succeed per current-object rules; older versions may still remain in history.
4. If the first request succeeded on S3 but the client timed out before receiving the response, retrying the same key can receive **412**. In that case, consult your **idempotency record/checksum** to distinguish "previously completed" from "another object took the key".
5. Do not infer from a 412 response that the principal has GET permission on the object; PUT and GET permissions are independent.

### 7.1. Create-only with UUID key names

In a document storage system, a controllable key pattern is:

~~~text
tenants/{trustedTenantId}/documents/{serverGeneratedUuid}.pdf
~~~

Generating UUIDs on the backend minimizes collisions; adding `If-None-Match: *` turns the "probably new" assumption into a **condition enforced by S3**. The database records owner, tenant, documentId, and key; the API never lets users choose keys outside their permissions.

## 8. `If-Match: ETag` — replace only if the object is unchanged

For a document editable at the **same key**, the backend can use optimistic concurrency control:

1. Read the object and its current **ETag** via GET or HEAD.
2. Allow the user to make edits based on that state.
3. Send PUT with **`If-Match` set to the ETag that was read**.
4. If the object changed in the meantime and the condition no longer holds, S3 returns **412** instead of silently overwriting.

~~~mermaid
sequenceDiagram
    participant C1 as Client 1
    participant C2 as Client 2
    participant S3 as S3
    C1->>S3: HEAD key
    S3-->>C1: ETag = E1
    C2->>S3: HEAD key
    S3-->>C2: ETag = E1
    C1->>S3: PUT B, If-Match: E1
    S3-->>C1: Success; new ETag E2
    C2->>S3: PUT C, If-Match: E1
    S3-->>C2: 412 Precondition Failed
~~~

To edit after a conflict, client 2 must fetch the newer version, compare/merge changes, and submit a PUT with the new ETag. Never auto-retry a failed precondition by stripping `If-Match`.

### 8.1. Java example: HEAD and conditional PUT

~~~java
import java.nio.charset.StandardCharsets;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

String key = "tenants/t-42/reports/status.json";

// Client/API already verified read and edit permissions for the business document.
var head = s3.headObject(HeadObjectRequest.builder()
        .bucket(bucket)
        .key(key)
        .build());

String expectedEtag = head.eTag(); // Keep the exact value returned by the SDK.

byte[] replacement = """
        {"state":"approved"}
        """.getBytes(StandardCharsets.UTF_8);

var result = s3.putObject(
        PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType("application/json")
                .ifMatch(expectedEtag)
                .build(),
        RequestBody.fromBytes(replacement));

System.out.println("New ETag: " + result.eTag());
~~~

In real products, **`expectedEtag` must come from the read that the client actually edited**, not from a fresh HEAD executed right before PUT regardless of what version the client saw. If the backend always runs HEAD right before PUT and uses the latest ETag, an edit based on stale data will still overwrite someone else's update. Therefore, return the ETag to the client with the data, and accept it back when the client requests an update.

**ETag is not always the content MD5.** With multipart uploads, encryption, or other mechanisms, ETag may not be a plain MD5 hash. Use ETag as a **condition token** per S3 semantics; do not treat it as a cryptographic checksum or assume ETags are monotonically increasing version numbers. When content integrity checks are needed, use checksums supported by the SDK/S3.

### 8.2. Distinguishing ETag and Version ID

| Attribute | Role | Interchangeable? |
| --- | --- | --- |
| `ETag` | Identifies content state per S3 semantics, used with HTTP `If-Match` | No |
| `Version ID` | Identifies a specific version in a versioning-enabled bucket | No |
| `Content-Length` | Object body length in bytes | No |
| `Checksum` | Verifies byte integrity under a supported algorithm | No |
| `rowVersion` in DB | Prevents lost updates on business records | No |

S3 Versioning **does not automatically generate an `If-Match` condition** for PUT requests. A system can store both `versionId` and `ETag` if it needs both version recovery and update concurrency control. If you need to distinguish logical revisions even when body bytes happen to be identical, using a **database revision number** or immutable key per revision is clearer than relying solely on ETag.

## 9. Handling HTTP 412 and 409 on conditional writes

Conditional writes require different error handling from permission or network errors.

| Result | Practical meaning | Handling suggestion |
| --- | --- | --- |
| 2xx | Conditional PUT/Complete succeeded | Store new ETag/version ID; mark business step complete |
| **412 Precondition Failed** | Condition no longer matches current object state | Return **409 Conflict** from the business API or a dedicated error code; prompt reload/merge |
| **409 ConditionalRequestConflict** | S3 detected a concurrent race during conditional write | Re-read state, perform bounded retry when appropriate |
| 403 AccessDenied | Missing S3/KMS permissions or denied by policy | Inspect IAM, bucket policy, KMS, explicit deny |
| 404/NoSuchKey on HEAD/GET | Object does not exist or is invisible in current state | Check key, LIST permissions, and versioning |
| Timeout/5xx | Possibly transient error; PUT outcome may be ambiguous to caller | Check state/idempotency before re-issuing |

Example response branching:

~~~java
import software.amazon.awssdk.services.s3.model.S3Exception;

try {
    s3.putObject(putRequest, RequestBody.fromBytes(payload));
} catch (S3Exception ex) {
    if (ex.statusCode() == 412) {
        // Current version does not satisfy If-Match/If-None-Match.
        throw new DocumentConflictException(
                "Object already exists or has been modified", ex);
    }
    if (ex.statusCode() == 409) {
        // Concurrent write conflict: re-check state before retrying.
        throw new ConcurrentObjectWriteException(
                "Object write conflict", ex);
    }
    throw ex;
}
~~~

`DocumentConflictException` and `ConcurrentObjectWriteException` are **application-defined business exceptions**, not built-in AWS SDK classes. The snippet illustrates error mapping; real code should confirm the error actually came from a conditional write before mapping every 409/412 to the same business exception.

### 9.1. Should you retry immediately on 412?

**Never retry unconditionally** with the same payload by dropping the precondition:

- For **create-only**, 412 may mean another request already created the object. Check your idempotency session and verify the object.
- For **replace-if-unchanged**, 412 means someone else modified it. The client must load the new version and merge; blindly overwriting recreates the lost-update bug.
- For **409**, you may retry PUT after re-reading/evaluating state per API guidance; cap retry attempts and use backoff.
- For **`CompleteMultipartUpload`** receiving 409 due to a conditional conflict, you typically need to **initiate a new multipart upload and re-upload the parts** per S3 requirements, rather than reusing the stale upload state arbitrarily.

If a timeout occurs after PUT succeeded on S3 but before the client received the response, a retry may receive 412. Maintain an **application request ID/idempotency record** to distinguish your own completed request from another caller contending for the key.

## 10. Conditional multipart uploads and overwrite limits

For large files, an object can be uploaded to S3 via:

~~~text
CreateMultipartUpload
      ↓
UploadPart(1), UploadPart(2), ...
      ↓
CompleteMultipartUpload
      ↓
Current object appears at bucket/key
~~~

**Conditions like "create only if key does not exist" or "replace only if ETag still matches" must be checked when completing the multipart upload**, not merely via HEAD before initiating it. The `CompleteMultipartUpload` API supports conditional headers in matching S3/SDK versions, such as `If-None-Match` and `If-Match`.

Conceptual illustration with AWS SDK v2 supporting conditional fields:

~~~java
var completeRequest = CompleteMultipartUploadRequest.builder()
        .bucket(bucket)
        .key(key)
        .uploadId(uploadId)
        .multipartUpload(completedMultipartUpload)
        .ifNoneMatch("*")  // Complete only if no current object exists.
        .build();

s3.completeMultipartUpload(completeRequest);
~~~

Above, `completedMultipartUpload` holds `CompletedPart` entries containing **partNumber and ETag from each UploadPart** in ascending order; `uploadId` comes from `CreateMultipartUpload`. The snippet illustrates only the conditional **Complete** call, not a full uploader.

When Complete fails:

1. Do not assume parts were automatically deleted; incomplete multiparts can incur storage costs.
2. On 412, check whether the object exists/changed and handle the conflict.
3. On 409 conditional conflict, follow the workflow to initiate a new multipart upload and re-upload if still required by business logic.
4. Attempt `AbortMultipartUpload` on the unfinished upload while still valid.
5. Configure an S3 Lifecycle rule **`AbortIncompleteMultipartUpload`** to clean up uploads abandoned due to killed processes or disconnected clients.

Do not mistake a successful `CreateMultipartUpload` for a completed object ready to GET.

## 11. Designing overwrite control at the business layer

S3 preconditions are powerful, yet they do not create a **shared ACID transaction between S3 and the database**. In invoice or report management systems, users normally interact via `documentId`, while `objectKey` lives in a database record.

### 11.1. Option A: one immutable key per revision

~~~text
Document ID = doc-42
Revision 1 → tenants/t-42/documents/doc-42/rev-001.json
Revision 2 → tenants/t-42/documents/doc-42/rev-002.json
Revision 3 → tenants/t-42/documents/doc-42/rev-003.json

Database:
documentId = doc-42
currentRevision = 3
currentObjectKey = .../rev-003.json
rowVersion = 3
~~~

Advantages:

- Never overwrites bytes of older revisions.
- PUT can use `If-None-Match: *` to guarantee the new revision key does not already exist.
- Database updates the current revision pointer via **optimistic locking** (`UPDATE ... WHERE row_version = expectedVersion`).
- Easy auditing and business rollback by selecting an already-stored revision.

The trade-off is more objects and needing lifecycle/retention rules. If S3 PUT succeeds while the database update fails, the new object can become an **orphan**; a reconciliation/cleanup job or stateful upload workflow is needed.

### 11.2. Option B: one mutable key combined with If-Match

Use the same key for current content and send `If-Match` with the ETag from the read. Versioning can be enabled to keep history. This is simpler at the object level, though:

- You must store/return the exact ETag from the read the client edited.
- You must handle 412 in the UI via reload/merge.
- You must manage old versions, delete markers, and costs if versioning is enabled.
- The database must still guard against lost updates on independent business fields like approval status, document title, or owner.

### 11.3. Coordinating S3 and the database

~~~mermaid
sequenceDiagram
    actor User as User
    participant API as Spring Boot
    participant DB as Database
    participant S3 as Amazon S3

    User->>API: Edit documentId + expectedRevision
    API->>DB: Check permissions + currentRevision
    DB-->>API: Current revision matches
    API->>S3: PUT new key, If-None-Match: *
    S3-->>API: Success + ETag/version ID
    API->>DB: CAS update currentRevision
    alt CAS succeeds
        DB-->>API: Pointer updated
        API-->>User: 200 + new revision
    else CAS fails
        DB-->>API: Someone else updated first
        API->>API: Record orphan + schedule cleanup/reconciliation
        API-->>User: 409 Conflict
    end
~~~

**CAS (compare-and-swap)** at the database here is a conditional update on revision/version, such as:

~~~sql
UPDATE documents
SET current_object_key = :newKey,
    row_version = row_version + 1
WHERE id = :documentId
  AND row_version = :expectedRowVersion;
~~~

If the updated row count is 0, a concurrent modification occurred or the record is invalid; do not conclude the S3 PUT failed. Clean up the newly written object according to policy. This workflow illustrates one design pattern, not a fully automatic distributed transaction.

## 12. Combining IAM and bucket policies to enforce write conditions

Checks in Java help avoid accidental overwrites, yet **another caller with PUT permission** can still write unconditionally if policies do not enforce it. For buckets holding critical data, AWS S3 offers **condition keys** for enforcing conditional writes in bucket policies, such as `s3:if-none-match` or `s3:if-match` on supported requests.

Implementation principles:

- Separate roles that only upload new objects from roles allowed to modify or delete.
- Consider a bucket policy that **denies** PUT requests missing the required precondition, depending on the APIs and bucket features in use.
- Test multipart separately, since `CreateMultipartUpload`, `UploadPart`, and `CompleteMultipartUpload` apply conditions at different stages; an imprecise policy can block valid workflows.
- Test with real roles in an AWS sandbox, including direct uploads via presigned URLs.
- Enable versioning/retention as needed, but **do not treat versioning as a substitute for permissions and write preconditions**.

Example identity policy allowing only reading and creating objects under one prefix:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::training-private-files/incoming/*"
    }
  ]
}
~~~

This policy **does not enforce `If-None-Match`**; it only grants actions and restricts the object ARN. If create-only enforcement is a mandatory data-protection requirement, design the matching bucket policy/role and test it on real AWS. Never assume that merely passing the header in a Java service protects the bucket from all other callers.

## 13. Handling idempotency, retries, and correctness on timeouts

Network failures can happen at inconvenient moments:

~~~text
Client → PUT If-None-Match: * → S3 saves successfully
                                 ↘ response lost due to network
Client → retries same key    → S3 returns 412
~~~

If 412 is treated as "upload failed", the app reports an error even though the object exists. If 412 is blindly treated as "success", the app may mistakenly accept data written by **another caller**.

A safer workflow:

1. The backend generates an **operation ID/idempotency key** and a backend-generated object key tied to the user/tenant.
2. Persist `PENDING` state before PUT.
3. On successful PUT, store ETag/version ID, size, and checksum if applicable, marking `READY`.
4. On timeout, look up the operation ID and inspect object state via HEAD/GET plus recorded metadata; decide whether to retry, finalize, or report conflict.
5. Never silently refresh `If-Match` and resend a stale payload; the client must decide based on the current object.
6. Clean up objects created successfully on S3 that lack a database reference, per retention policy.

If the application runs multiple instances, the idempotency record must live in shared durable storage, not a local `ConcurrentHashMap` as the source of truth.

## 14. Testing functionality and concurrency scenarios

### 14.1. Three testing layers

| Layer | Verifies | Limitations |
| --- | --- | --- |
| Unit tests with mocked SDK | Prefix/size, token forwarding, presence of If-Match/If-None-Match, 412/409 mapping | Does not prove S3 enforces the condition |
| S3-compatible emulator (if supported) | LIST, paginator, conditional PUT, GET/HEAD, conflicts | May not reproduce AWS concurrency, policies, directory buckets, or KMS accurately |
| AWS sandbox | Real IAM, bucket policies, strong consistency, conditional PUT/Complete, versioning, and retries | Requires dedicated test permissions/resources and post-test cleanup |

### 14.2. Recommended test cases

**Pagination:**

1. Create more than 20 test objects under a random prefix `tenants/test-.../`.
2. Call `ListObjectsV2` with `maxKeys=5`; follow `nextContinuationToken` until pages finish.
3. Verify no out-of-prefix keys appear and counts match on a stable bucket.
4. Test an empty prefix, keys with `/` characters, and `delimiter("/")`.
5. Insert/delete objects **between pages** to observe why multi-page listing is not a snapshot.
6. Enforce API `pageSize` bounds and test invalid tokens/tenants.

**Conditional PUT:**

1. PUT a new key with `If-None-Match: *`: first call succeeds; second call returns 412.
2. HEAD to get ETag `E1`, PUT new content with `If-Match: E1`: succeeds.
3. Re-send the old ETag after the object changed: expect 412 as the condition no longer holds.
4. Run two concurrent PUTs using the same old ETag to observe one succeed and the other fail/conflict (distinguishing 412/409).
5. Enable versioning in a dedicated test bucket to observe version history across successful PUTs.
6. When using multipart, test conditional `CompleteMultipartUpload` and Abort/lifecycle cleanup on failure.
7. Simulate a timeout after PUT succeeds to test idempotency records and reconciliation.

### 14.3. Illustrative create-only test

The snippet below shows an SDK test (using a random key in a sandbox bucket):

~~~java
String key = "incoming/test-" + java.util.UUID.randomUUID();

byte[] body = "hello".getBytes(
        java.nio.charset.StandardCharsets.UTF_8);

PutObjectRequest request = PutObjectRequest.builder()
        .bucket(testBucket)
        .key(key)
        .ifNoneMatch("*")
        .build();

s3.putObject(request, RequestBody.fromBytes(body));

try {
    s3.putObject(request, RequestBody.fromBytes(body));
    throw new AssertionError("Expected a conditional write conflict");
} catch (software.amazon.awssdk.services.s3.model.S3Exception ex) {
    if (ex.statusCode() != 412) {
        throw ex; // Do not confuse IAM/network errors with precondition failures.
    }
}
~~~

In real tests, clean up the object in teardown/finally and never run against keys holding real data. If the bucket has versioning enabled, apply proper version cleanup; deleting the current key does not necessarily remove history.

## 15. Comparison with Azure Blob Storage and Google Cloud Storage

This module targets Spring Boot integration across three cloud providers. Pagination and conditional writes exist in all three, though **parameters and semantics differ**:

| Problem | Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| --- | --- | --- | --- |
| List by prefix | `ListObjectsV2(prefix)` | List blobs by prefix | List objects by prefix |
| Pagination | Opaque continuation token | Azure paging continuation token | Google Cloud Storage page token |
| Create only if absent | `If-None-Match: *` on supported PUT | `If-None-Match: *`/matching request conditions | Preconditions such as `ifGenerationMatch(0)` |
| Write if version unchanged | `If-Match` with ETag | `If-Match` with ETag | `ifGenerationMatch(generation)` |
| Version history | S3 Versioning + version ID | Blob versioning | Object version/generation |
| Workload identity | IAM role / AWS credentials | Managed identity / Azure RBAC | Service account / Google IAM |

What should stay shared in the **domain service**: tenant authorization, page size, cursor contract, idempotency ID, and `CONFLICT` errors. Each cloud adapter handles translating to provider APIs, respecting provider limits, and interpreting ETags/generations/tokens.

A business interface might look like:

~~~java
public interface ObjectCatalogPort {
    ObjectPage list(String trustedPrefix, String pageToken, int limit);

    CreatedObject createIfAbsent(
            String trustedKey, byte[] body, String contentType);

    UpdatedObject replaceIfUnchanged(
            String trustedKey, byte[] body,
            String contentType, String expectedRevision);
}
~~~

In this interface, `ObjectPage`, `CreatedObject`, and `UpdatedObject` are **custom domain types**. `expectedRevision` may represent an ETag (S3/Azure) or a generation (GCP) at the adapter layer, yet the business API should never assume revision strings are comparable across providers.

## 16. Practice exercises and review questions

### Exercise 1 — Building a paginated API

Create a `GET /api/documents?pageSize=10&cursor=...` endpoint in Spring Boot. The backend authenticates the user, retrieves a trusted `tenantId`, calls `ListObjectsV2` with the tenant prefix, and returns the next page. With over 30 test objects, verify cursor pagination works, `pageSize` is bounded, and other tenants' objects are never exposed.

### Exercise 2 — Creating an object exactly once

Create a new report upload endpoint: the backend generates a UUID key and sends PUT with `If-None-Match: *`. Intentionally resend the same key to observe 412. Design business error/idempotency handling so a retried request after timeout is not confused with another caller's request.

### Exercise 3 — Editing a document without lost updates

Two clients read the same object and ETag `E1`. Client A sends PUT `If-Match: E1` with content B; client B sends PUT `If-Match: E1` with content C. Observe the outcome and build a UI flow that displays the conflict and prompts reload/merge instead of blindly overwriting.

### Exercise 4 — Versioning and conditional writes

In a versioning-enabled sandbox bucket, create two versions for the same key, then HEAD and download each version by version ID. Next, test `If-Match` with an old ETag and `If-None-Match: *` when a current object exists vs. when the current version is a delete marker. Record the differences among **ETag, version ID, and current-object state**.

### Exercise 5 — Conditional multipart Complete

Upload multiple parts to a new key; before Complete, have another task create an object at that same key. Send a conditional Complete to observe 412/409 depending on the race, then abort/clean up the incomplete multipart upload. Explain why simply calling HEAD before starting multipart is insufficient.

### Exercise 6 — Multi-cloud design

Design an `ObjectCatalogPort` serving S3, Azure Blob Storage, and Google Cloud Storage. Choose common cursor and revision types; explain why you cannot increment page numbers or treat an AWS ETag like a GCP generation. Describe how to test concurrency on each provider.

### Self-check questions

1. How do `maxKeys` and `nextContinuationToken` differ?
2. Why must `continuationToken` never be derived from the last key of the previous page?
3. Which two needs do `prefix` and `delimiter` address?
4. Does multi-page LIST guarantee a transactional snapshot when objects change concurrently?
5. When is `StartAfter` used, and why must you be careful with directory buckets?
6. Why does normal HEAD followed by PUT still have a race condition?
7. How do `If-None-Match: *` and `If-Match: ETag` express two different write intents?
8. How should 412 and 409 in conditional writes be handled?
9. When should ETag not be used as an MD5 checksum?
10. Does Versioning automatically prevent updating from stale data?
11. Why must conditional multipart writes be enforced at Complete time?
12. How does an idempotency record resolve a timeout after a successful PUT?
13. If an S3 PUT succeeds while the database optimistic update fails, how should the leftover object be handled?
14. Does an IAM role with `s3:PutObject` guarantee every caller uses conditional writes?
15. Which mechanisms do Azure and Google Cloud use for cursors and conditional create/update?

Completing this lesson equips learners to implement S3 listings with **cursor pagination**, PUT operations with **preconditions** to prevent accidental overwrites, distinguish conflict errors from permission/network errors, and coordinate **S3 Versioning + database optimistic locking** per business requirements. This is a vital foundation when deploying Spring Boot with managed object storage across cloud providers.
