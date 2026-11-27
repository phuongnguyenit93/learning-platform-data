# Generation Preconditions and Preventing Unintended Overwrites

## 1. Why Are Preconditions Needed?

Cloud Storage allows multiple service instances, workers, and users to access an object concurrently. An object may be overwritten, deleted, or have its metadata updated while another request is being processed. If an application reads object state, makes a decision based on that state, and then sends a write or delete command without re-checking, the state may have already changed before the command reaches Cloud Storage.

For example, two requests both read a document at generation 100. Request A updates the file and creates generation 101. Request B still holds the old state and sends its update. If B overwrites unconditionally, A's change can be lost. An even more dangerous scenario: a worker schedules deletion of an old object, but while waiting, a user uploads a new version under the same name. An unconditional delete could accidentally delete the new file.

A **request precondition** is a condition instructing Cloud Storage to execute an operation only when the object is in the exact state expected by the application. For objects, the two most important values are **generation** and **metageneration**. They enable compare-and-set operations, protect read-modify-write flows, prevent race conditions, and make certain requests safe to retry.

This lesson belongs to the **Google Cloud Storage** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module focuses on practicing Spring Boot integration with managed services on AWS, Azure, and Google Cloud through the corresponding Spring Cloud libraries; learning identity and permissions configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. This lesson focuses on generation preconditions and preventing unintended overwrites when using the Cloud Storage Java client.

After this lesson, you will be able to:

- Distinguish generation, metageneration, and ETag.
- Choose appropriate preconditions for create, overwrite, delete, read, and metadata updates.
- Use generation value 0 to create an object only when no live version exists.
- Use generation-match to replace or delete only the exact version that was read.
- Combine generation-match and metageneration-match when updating metadata.
- Handle HTTP 412 and 304 according to their exact semantics.
- Design safe retries when requests time out or responses are lost.
- Integrate optimistic concurrency control into Spring Boot services and databases.
- Test race conditions on a dedicated GCP bucket.

> **Version scope:** Examples use the Google Cloud Storage Java client, artifact com.google.cloud:google-cloud-storage. Manage versions using a BOM matching your project's Java/Spring baseline and check the Javadoc for the actual resolved version. Bucket names, object names, and generations in examples are illustrative data only.

## 2. Generation and Metageneration

A Cloud Storage object consists of data (bytes) and metadata. These two parts have linked lifecycles but are versioned separately.

### 2.1. Generation: Data Version

**Generation** is the version number of the object data. Whenever an object is created or a new data version is written, generation changes. Generation is assigned by Cloud Storage and cannot be chosen manually.

Example:

| Time | Operation | Generation | Content |
| --- | --- | ---: | --- |
| T1 | Initial document upload | 100 | Version A |
| T2 | Update bytes | 101 | Version B |
| T3 | Update bytes again | 102 | Version C |

The numbers 100, 101, 102 are illustrative only. Actual generations are large numbers issued by Cloud Storage; do not rely on them to infer timestamps, global ordering, or upload counts across another system.

If Object Versioning is enabled, old generations may remain as noncurrent versions. If versioning is disabled, older versions generally cannot be accessed as regular object versions after replacement. Regardless of versioning configuration, the object name always identifies the live object; to access an old generation, specify the generation explicitly.

### 2.2. Metageneration: Metadata Version

**Metageneration** is the metadata version number for a specific generation. When metadata such as Content-Type, Cache-Control, custom metadata, or other metadata fields is updated, metageneration increments. Changing bytes creates a new generation, and the metageneration of the new generation starts again at 1.

Example:

| Time | Operation | Generation | Metageneration |
| --- | --- | ---: | ---: |
| T1 | Upload initial bytes and metadata | 100 | 1 |
| T2 | Change Content-Type | 100 | 2 |
| T3 | Edit custom metadata | 100 | 3 |
| T4 | Upload new bytes | 101 | 1 |
| T5 | Change Cache-Control of the new version | 101 | 2 |

Therefore:

- Generation answers: **which version of the bytes is this?**
- Metageneration answers: **which version of that byte version's metadata is this?**

Buckets also have a metageneration for bucket metadata, though buckets do not have a generation like object data.

### 2.3. How Does ETag Differ from Generation?

ETag is a validator returned by Cloud Storage in responses. Applications should not assume ETag is always an MD5 or has the same representation between the JSON API and XML API. ETag is useful for HTTP conditional requests like If-Match and If-None-Match, but generation and metageneration are usually clearer choices for object operations in Cloud Storage.

| Value | When does it change? | Used to protect |
| --- | --- | --- |
| Generation | Object bytes get a new version | Reading, overwriting, deleting the exact data version |
| Metageneration | Object metadata is updated | Metadata read-modify-write |
| ETag | According to service-returned validator | HTTP caching/conditional retrieval |

Do not use metageneration alone to guard an object metadata update. If the object data is replaced, the new generation may also have the same metageneration number (e.g., 1). For object requests, combine generation-match and metageneration-match whenever both data and metadata must match the snapshot read earlier.

## 3. Types of Preconditions

Cloud Storage supports four primary conditions on generation and metageneration.

| Precondition | Condition for request to proceed | When not met |
| --- | --- | --- |
| ifGenerationMatch = N | Current generation equals N | HTTP 412 Precondition Failed |
| ifGenerationNotMatch = N | Current generation differs from N | HTTP 304 Not Modified |
| ifMetagenerationMatch = M | Current metageneration equals M | HTTP 412 Precondition Failed |
| ifMetagenerationNotMatch = M | Current metageneration differs from M | HTTP 304 Not Modified |

ifGenerationMatch and ifGenerationNotMatch are mutually exclusive; the same applies to the two metageneration conditions. One generation condition and one metageneration condition can be combined in the same request. If either condition fails, the request is not executed.

### 3.1. Special Value generation = 0

ifGenerationMatch=0 has a special meaning when writing object data: the request succeeds only if the bucket currently has no **live object** with that name. If only noncurrent versions remain due to Object Versioning, the operation can still succeed. If a live version already exists, Cloud Storage returns 412.

Use value 0 only for object data write operations such as upload/insert. Do not use generationMatch(0) as a generic condition for read, delete, or metadata updates.

In the Java client, the doesNotExist() option expresses create-only intent more clearly than passing 0 directly.

### 3.2. JSON API and XML API

| API | Generation match | Metageneration match |
| --- | --- | --- |
| JSON API | Query parameter ifGenerationMatch | Query parameter ifMetagenerationMatch |
| XML API | Header x-goog-if-generation-match | Header x-goog-if-metageneration-match |

For not-match conditions, the JSON API supports corresponding query parameters. The XML API does not support every not-match variant. When using the Java client, choose the corresponding SDK option instead of assembling query strings or headers manually.

### 3.3. Preconditions Do Not Replace IAM

A precondition only checks resource state at the moment Cloud Storage processes the request. It does not grant permissions. The principal still needs appropriate IAM permissions:

- Uploading an object requires storage.objects.create.
- Overwriting an object may additionally require storage.objects.delete per operation semantics.
- Reading bytes/metadata requires storage.objects.get.
- Listing objects requires storage.objects.list.
- Deleting an object requires storage.objects.delete.

Retention policies, object holds, soft delete, and other policies still apply. A request with a valid generation match can still be rejected if the principal lacks permissions or the object is protected by retention/holds.

## 4. Creating an Object Only When the Name Does Not Yet Exist

This is the most common scenario: a user uploads a new document and the application must not overwrite an existing object with the same name.

### 4.1. Approach Prone to Race Conditions

A seemingly reasonable approach is to read first to check if the object exists and then upload:

~~~java
Blob existing = storage.get(bucket, objectName);

if (existing == null) {
    storage.create(blobInfo, content);
}
~~~

This approach leaves a time window between get and create. Two requests can both observe that the object does not exist and both upload. The later request can overwrite the earlier request's object.

### 4.2. Using doesNotExist()

Let Cloud Storage evaluate the condition atomically inside the write request:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;

public Blob createOnly(
        Storage storage,
        String bucket,
        String objectName,
        byte[] content) {

    BlobInfo info = BlobInfo.newBuilder(
            BlobId.of(bucket, objectName))
        .setContentType("application/pdf")
        .build();

    return storage.create(
            info,
            content,
            Storage.BlobTargetOption.doesNotExist());
}
~~~

If no live object exists, the upload succeeds. If the object already exists, Cloud Storage returns 412. The conditional check and write are executed by the service, leaving no gap between two application requests.

### 4.3. Uploading Large Files with WriteChannel

For large payloads, you still need a precondition during resumable uploads:

~~~java
import com.google.cloud.WriteChannel;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.channels.Channels;

public void createOnlyFromStream(
        Storage storage,
        BlobInfo info,
        InputStream source) throws Exception {

    try (WriteChannel writer = storage.writer(
                info,
                Storage.BlobWriteOption.doesNotExist());
         OutputStream output = Channels.newOutputStream(writer)) {
        source.transferTo(output);
    }
}
~~~

The precondition is enforced on the final upload commit. Closing the writer finalizes the upload; if the condition no longer holds, the operation is not committed as a live object. In real applications, manage ownership of the source InputStream explicitly and close the stream only in the layer that created or owns it.

### 4.4. When Object Names Must Be Unique

Object names can be generated using UUIDs or internal document IDs. However, unique names do not replace preconditions: retries, bugs, or duplicate requests can still send the same object name. Use doesNotExist() as the final safeguard at Cloud Storage.

## 5. Overwriting Only When the Previously Read Version Is Still Current

Another business scenario allows replacing an existing object, but only if no one has updated it since the application read it.

### 5.1. Read-Modify-Write with Generation

Suppose the application reads metadata and gets generation 100. After processing the file, it uploads the new version with generationMatch(100):

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;

public Blob replaceIfUnchanged(
        Storage storage,
        String bucket,
        String objectName,
        long expectedGeneration,
        byte[] newContent) {

    BlobInfo info = BlobInfo.newBuilder(
            BlobId.of(bucket, objectName))
        .setContentType("application/pdf")
        .build();

    return storage.create(
            info,
            newContent,
            Storage.BlobTargetOption.generationMatch(
                    expectedGeneration));
}
~~~

If the live object is still at generation 100, the upload creates a new generation. If another worker already created generation 101, the request is rejected with 412. This prevents the application from silently overwriting newer changes.

### 5.2. Persisting Generation in the Database

When creating a document record, you can store the generation returned by GCS along with the bucket/object name:

~~~java
Blob created = storage.create(
        blobInfo,
        content,
        Storage.BlobTargetOption.doesNotExist());

documentRepository.save(new DocumentRecord(
        documentId,
        bucket,
        objectName,
        created.getGeneration(),
        created.getMetageneration()));
~~~

DocumentRecord is only an illustrative data type. In practice, database updates and GCS requests are not in a single ACID transaction. Design business states such as PENDING, UPLOADED, READY, FAILED and an appropriate reconciliation/outbox mechanism when coordinating the two systems.

### 5.3. Compare-and-Set with Two Workers

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant GCS as Cloud Storage

    A->>GCS: GET metadata
    GCS-->>A: generation 100
    B->>GCS: GET metadata
    GCS-->>B: generation 100
    A->>GCS: Upload with ifGenerationMatch=100
    GCS-->>A: Success, generation 101
    B->>GCS: Upload with ifGenerationMatch=100
    GCS-->>B: 412 Precondition Failed
    B->>B: Re-read and handle conflict
~~~

This is optimistic concurrency control: multiple workers can read concurrently, but only one worker succeeds in updating from a specific generation. The other worker must read the new state and decide whether to re-apply the business logic or report a conflict.

## 6. Deleting the Exact Confirmed Object

### 6.1. Risk of Deleting a Newer Version by Mistake

Suppose a job reads generation 200 and schedules object deletion a few minutes later. Meanwhile, a user uploads a new version at generation 201. If the job calls delete(bucket, objectName) unconditionally, it can delete live object 201 even though the job intended to delete version 200.

### 6.2. Delete with generationMatch

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public boolean deleteIfUnchanged(
        Storage storage,
        String bucket,
        String objectName,
        long expectedGeneration) {

    return storage.delete(
            BlobId.of(bucket, objectName),
            Storage.BlobSourceOption.generationMatch(
                    expectedGeneration));
}
~~~

If the live generation still matches, deletion proceeds. If the object has been replaced, the request fails with 412. If no live object remains, the outcome depends on current state and API response; handle not-found/false according to the contract of the method in use.

If you need to delete a specific noncurrent version when Object Versioning is enabled, create a BlobId with the specific generation and use the appropriate API/options to target that version. Do not confuse deleting the live object with deleting a noncurrent generation.

### 6.3. Delete and Retry After Timeout

Dangerous scenario:

1. The client sends a delete command and times out.
2. The application does not know whether the server deleted the object.
3. A new upload creates an object with the same name.
4. The client retries the delete command unconditionally.
5. The newly uploaded version can be accidentally deleted.

If delete is bound to the generation read earlier, the retried request targets only that generation. Once the live object changes generation, the precondition no longer holds and the request does not delete the new version.

## 7. Updating Metadata with Metageneration

Metadata updates can hit race conditions even when bytes do not change. For example, two services concurrently edit Cache-Control and Content-Disposition. If each service reads the old metadata and sends an unconditional update, the first service's change can be overwritten by the second service's stale update.

### 7.1. Using Generation and Metageneration Together

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public Blob updateContentType(
        Storage storage,
        String bucket,
        String objectName,
        String newContentType) {

    Blob current = storage.get(
            BlobId.of(bucket, objectName));

    if (current == null) {
        throw new IllegalStateException("Object does not exist");
    }

    BlobInfo updated = current.toBuilder()
            .setContentType(newContentType)
            .build();

    return storage.update(
            updated,
            Storage.BlobTargetOption.generationMatch(
                    current.getGeneration()),
            Storage.BlobTargetOption.metagenerationMatch(
                    current.getMetageneration()));
}
~~~

The two conditions guard two assumptions:

- Generation match ensures the metadata being edited still belongs to the exact byte version that was read.
- Metageneration match ensures the metadata has not been modified by another service since it was read.

If only metageneration is checked, a new generation can also have metageneration 1 just like the previous version. Therefore, for object metadata updates, combine both when acting on a previously read metadata snapshot.

### 7.2. Updating a Single Metadata Field

If the application only wants to change one field, it must still preserve the needed fields in the BlobInfo sent. Using current.toBuilder() starts from the metadata snapshot that was read. If another worker modifies metadata before the request executes, the precondition prevents overwriting with a stale snapshot.

Do not construct a BlobInfo containing only one field and assume all other metadata will remain untouched. Check PATCH/UPDATE semantics of the API and SDK version.

## 8. Protecting Metadata and Byte Reads

A workflow often reads metadata first to get size, Content-Type, or generation, and then downloads bytes in a subsequent request. The object may change between those two requests.

### 8.1. Pinning Generation When Reading Bytes

~~~java
import com.google.cloud.ReadChannel;
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.io.InputStream;
import java.nio.channels.Channels;
import java.nio.file.Files;
import java.nio.file.Path;

public void downloadSameGeneration(
        Storage storage,
        String bucket,
        String objectName,
        Path destination) throws Exception {

    Blob metadata = storage.get(
            BlobId.of(bucket, objectName));

    if (metadata == null) {
        throw new IllegalStateException("Object does not exist");
    }

    BlobId pinnedVersion = BlobId.of(
            bucket,
            objectName,
            metadata.getGeneration());

    try (ReadChannel reader = storage.reader(pinnedVersion);
         InputStream input = Channels.newInputStream(reader);
         var output = Files.newOutputStream(destination)) {
        input.transferTo(output);
    }
}
~~~

Pinning the generation guarantees the downloaded bytes belong to the exact version described by the initial metadata. If that generation is no longer retained, the request may return not found. Using only the object name could read metadata from an old version while downloading bytes from a new version.

### 8.2. Using generationMatch on Read

You can use Storage.BlobSourceOption.generationMatch(expectedGeneration) when calling read APIs that support source options. Passing a BlobId that already includes generation also explicitly targets the version to read. Check the Javadoc of the specific method to select the right overload and option type.

### 8.3. Caching and Detecting Object Changes

If a local cache currently holds generation 100, the application can use ifGenerationNotMatch=100 to download only when the object in the bucket differs from the local generation. When the object has not changed, the JSON API returns 304 Not Modified and avoids re-downloading bytes. This is a cache validation technique; do not confuse 304 with 412 from a match precondition.

## 9. Integrating the Java Storage Client in Spring Boot

### 9.1. Dependency

If the project already manages Google Cloud libraries with a BOM:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-storage</artifactId>
</dependency>
~~~

Do not pin an independent version if the project's BOM already manages versions.

### 9.2. Configuring the Storage Bean

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GcsConfiguration {

    @Bean
    Storage storage() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

If the Spring Framework on Google Cloud starter already auto-configures a Storage bean, inject the existing bean. Never create a new client per request.

### 9.3. Putting the Bucket in Configuration

~~~yaml
app:
  gcs:
    bucket: training-documents-dev
~~~

Environment-specific bucket names should be managed through configuration or environment variables. Do not let clients arbitrarily pass bucket names in requests.

### 9.4. Separating the Adapter from Business Logic

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GcsDocumentAdapter {

    private final Storage storage;
    private final String bucket;

    public GcsDocumentAdapter(
            Storage storage,
            @Value("#{environment['app.gcs.bucket']}") String bucket) {
        this.storage = storage;
        this.bucket = bucket;
    }

    public Blob create(
            String objectName,
            byte[] content,
            String contentType) {

        BlobInfo info = BlobInfo.newBuilder(
                BlobId.of(bucket, objectName))
            .setContentType(contentType)
            .build();

        return storage.create(
                info,
                content,
                Storage.BlobTargetOption.doesNotExist());
    }

    public Blob replace(
            String objectName,
            long expectedGeneration,
            byte[] content,
            String contentType) {

        BlobInfo info = BlobInfo.newBuilder(
                BlobId.of(bucket, objectName))
            .setContentType(contentType)
            .build();

        return storage.create(
                info,
                content,
                Storage.BlobTargetOption.generationMatch(
                        expectedGeneration));
    }

    public boolean delete(
            String objectName,
            long expectedGeneration) {

        return storage.delete(
                BlobId.of(bucket, objectName),
                Storage.BlobSourceOption.generationMatch(
                        expectedGeneration));
    }
}
~~~

The adapter receives the generation from the business service. Controllers should not choose generation or bucket from arbitrary input; the service must retrieve them from an access-checked document record.

## 10. Optimistic Locking Model Between Database and Cloud Storage

An application often stores document metadata in a database and bytes in GCS. Generation can serve as a version token for object storage, similar to a version column in a database.

### 10.1. New Upload Flow

1. Create a document record in PENDING state with a unique object name.
2. Upload using doesNotExist().
3. Receive generation and metageneration from GCS.
4. Update the database record to READY, storing generation and size.
5. If the database update fails after upload succeeds, a reconciliation job finds orphaned objects or completes the record using an idempotency key.

### 10.2. Document Update Flow

1. Read the document record and stored generation.
2. Verify edit permissions and business state.
3. Upload new bytes using generationMatch(expectedGeneration).
4. If successful, store the new generation in the database.
5. On 412, re-read the object and document record; return a conflict or re-run business logic against the new version.

### 10.3. No Automatic Distributed Transactions

Database transactions do not span Cloud Storage requests. Do not assume `@Transactional` will roll back a GCS upload if a subsequent SQL statement fails. Use state machines, outbox/jobs, idempotency keys, controlled retries, and reconciliation to coordinate both systems.

## 11. Retries, Idempotency, and HTTP Status Codes

### 11.1. Why Do Preconditions Make Retries Safer?

A timed-out request may have already been processed by Cloud Storage while the response failed to reach the client. If the client retries an unconditional write/delete, the second request could affect a newly created object created after the first request. Generation preconditions ensure the request only takes effect against the state the application intended.

Examples:

- Create-only upload with doesNotExist() succeeds only when no live object exists.
- Replace with generationMatch(expected) succeeds only if the object is still at the generation read earlier.
- Delete with generationMatch(expected) deletes only that exact generation.
- Metadata update with metagenerationMatch(expected) updates metadata only if it has not changed.

The Java Cloud Storage client supports retrying transient errors and automatically retries only operations configured as idempotent. For conditionally idempotent operations, pass the corresponding generation or metageneration precondition so the SDK recognizes retry safety.

### 11.2. Error Handling Table

| Status/error | Meaning | Resolution |
| --- | --- | --- |
| 200/201 | Request succeeded | Persist returned generation/metageneration |
| 304 Not Modified | Not-match condition failed because resource still matches comparison value | Use existing cache or finish download |
| 404 Not Found | Object/version does not exist | Check object name, generation, and lifecycle |
| 403 Forbidden | Principal lacks permission or blocked by policy | Check IAM, retention/holds, and policies |
| 412 Precondition Failed | Resource changed relative to assumption | Re-read state and handle conflict |
| 408/429/5xx | Transient error or overload | Retry with exponential backoff if operation is idempotent |
| Timeout/connection drop | Uncertain whether server processed request | Check state via generation/metadata before deciding to retry |

Do not retry 403 or 412 indefinitely. 412 usually signals another writer modified the object; re-read and decide based on business rules. If a timeout occurs on a create-only upload, a retry may return 412 because the first attempt succeeded. In that case, read the object and compare the operation ID, size/checksum, or application-stored metadata to determine whether your previous request succeeded or another writer created the object.

### 11.3. Exponential Backoff

For transient errors such as 408, 429, 500, 502, 503, 504, and connection errors, use exponential backoff with jitter. Cap retry count or overall deadline. Never use retries to mask permission errors or data conflicts.

## 12. Object Versioning, Soft Delete, and Preconditions

Object Versioning preserves old generations as noncurrent versions when the live object is overwritten or deleted. Soft delete can retain deleted objects for a period. Retention policies and holds can block deletion before the required duration.

These mechanisms add recoverability, but they do not replace preconditions:

- Generation match still targets the live generation or the specific requested generation.
- Versioning preserves old generations if the bucket is configured appropriately.
- Soft delete affects object recovery after deletion.
- Retention/holds can cause deletion to fail even when generation match is accurate.
- ifGenerationMatch=0 checks the live object; existing noncurrent versions do not necessarily block creating a new live version.

Clearly define whether business logic requires "replace live object," "retain old versions," "hide document," "delete live object," or "permanently delete." These are distinct behaviors.

## 13. Cost and Performance

Preconditions usually require knowing the current generation/metageneration. If the application has not cached or persisted these values, it may need an extra metadata read request before the main operation.

The costs of doing so include:

- An extra network round trip and increased latency.
- An extra billable operation and potential network cost.
- Additional load on Cloud Storage if every request reads metadata before writing.

Overhead can be reduced by storing generation/metageneration alongside the document record after each object creation/update. Use the stored value only when the application manages record consistency; if the database can become stale, the precondition still protects the object and returns 412 on stale tokens.

Do not omit preconditions just to save one metadata request in flows prone to accidental overwrites or deletes. Measure latency and choose where to store version tokens based on business requirements.

## 14. Testing Generation Preconditions

### 14.1. Unit Tests

Verify the service passes the right preconditions to the adapter:

- New uploads must use doesNotExist().
- Replacements must use the stored generation.
- Deletions must use the generation of the confirmed object.
- Metadata updates must use both generation and metageneration.
- 412 is mapped to a business conflict.
- Timeouts are not automatically treated as failed uploads.
- Retries must not drop preconditions.
- Controllers must not let clients pass arbitrary buckets or generations.

Mocks can verify which options are passed to the SDK, but they do not prove real Cloud Storage behavior.

### 14.2. Integration Tests on a Dedicated Bucket

1. Upload an object with doesNotExist() and store its generation.
2. Upload again to the same name with doesNotExist(); expect 412.
3. Upload a new version with the current generation match; expect success.
4. Attempt to replace using the old generation; expect 412.
5. Attempt to delete using the old generation after the object changed; confirm the new live version remains intact.
6. Read metadata and update Content-Type with generation + metageneration match.
7. Update metadata using the stale metageneration; expect 412.
8. Read current generation, replace bytes before downloading; verify reading the pinned generation does not mix data.
9. Test Object Versioning/soft delete if enabled on the test bucket.
10. Clean up test objects and verify no unexpected data remains in the bucket.

### 14.3. Simulating Race Conditions

Use two workers or two test threads:

- Both read generation G.
- Worker A updates with generationMatch(G).
- Worker B updates with generationMatch(G).
- Only one worker succeeds; the other receives 412.
- Worker B re-reads the new generation and decides whether to retry or report a conflict.

Do not test simply by running two commands sequentially in a single thread; create a synchronization barrier so both workers read the same snapshot before writing.

## 15. Using gcloud to Test Preconditions

### 15.1. Create Only When the Object Does Not Exist

~~~bash
gcloud storage cp ./report.pdf \
  gs://training-documents-dev/reports/report.pdf \
  --if-generation-match=0
~~~

### 15.2. Overwrite Exact Generation Read Earlier

~~~bash
gcloud storage cp ./report-updated.pdf \
  gs://training-documents-dev/reports/report.pdf \
  --if-generation-match=1234567890123456
~~~

### 15.3. View Metadata and Generation

~~~bash
gcloud storage objects describe \
  gs://training-documents-dev/reports/report.pdf
~~~

These commands are for practicing on a test bucket only. Verify project, principal, and bucket before running. Never test delete or overwrite on production data.

## 16. Comparison with AWS S3 and Azure Blob Storage

| Aspect | Google Cloud Storage | Amazon S3 | Azure Blob Storage |
| --- | --- | --- | --- |
| Version token | Generation | Version ID, ETag | Version ID, ETag |
| Create-only | ifGenerationMatch=0 | Conditional request with If-None-Match: * or equivalent mechanism | Conditional request with If-None-Match: * |
| Replace-if-unchanged | ifGenerationMatch | If-Match ETag or version-aware request | If-Match ETag or lease |
| Metadata update | ifGenerationMatch + ifMetagenerationMatch | ETag/version conditional headers | ETag conditional headers |
| Conditional delete | Generation match | Version ID / conditional request | ETag condition / lease |
| Conflict | HTTP 412 | HTTP 412 or conditional error per API | HTTP 412 |

All providers support conditional requests, though tokens and semantics are not fully equivalent. Generation is GCS's version number; S3 Version ID and Azure version ID follow their own models. ETag can be used as a validator, but never treat ETag as generation. Multi-cloud adapters should express business behaviors such as create-if-absent, replace-if-version, update-metadata-if-current, and delete-if-version; each provider adapter maps those to its native preconditions.

## 17. Comprehensive Hands-On Exercise

**Context:** The Spring Boot application `document-api` stores per-tenant files in bucket `training-documents-dev`. Multiple workers may update or delete the same document; users may also upload a new version while an older processing job is still running.

### Task A — Understand Version Tokens

1. Upload an object and record its generation/metageneration.
2. Update only Content-Type; observe metageneration changing.
3. Upload new bytes; observe generation changing and metageneration resetting.
4. Explain why generation and metageneration solve two different kinds of race conditions.

### Task B — Create and Replace

1. Upload an object using doesNotExist().
2. Attempt a duplicate upload to the same object name and handle 412.
3. Read the current generation.
4. Replace using generationMatch(expectedGeneration).
5. Attempt to replace using the stale token and return a conflict.

### Task C — Delete and Metadata Update

1. Read object generation G.
2. Create version G+1.
3. Run delete with generation G; confirm G+1 is not deleted.
4. Read generation + metageneration and update metadata with both conditions.
5. Simulate another worker updating metadata between the two requests; confirm 412.

### Task D — Retries and Integration Tests

- Simulate a timeout after upload and verify the object before retrying.
- Test that create-only retries do not produce duplicate records.
- Test two workers updating concurrently from the same generation.
- Test 412, 304, 403, and 404.
- Test a bucket with Object Versioning or soft delete.
- Verify individual IAM permissions for create/get/delete.

**Pass criteria:** The application prevents duplicate creations, overwrites from stale snapshots, and accidental deletion of newer generations; metadata updates use the proper generation/metageneration pair; 412 responses are handled per business rules; and integration tests verify race conditions on Cloud Storage.

## 18. Key Takeaways

- Generation represents the byte version; metageneration represents the metadata version of that generation.
- ifGenerationMatch=0 is a create-only precondition for object data writes; noncurrent versions may still exist.
- doesNotExist() is the clearest way to express create-only intent in the Java Storage client.
- Replacements and deletions should use the previously read generation so only the intended version is affected.
- Metadata updates should combine generation-match and metageneration-match.
- Failed match preconditions usually return 412; failed not-match preconditions may return 304.
- Preconditions make certain operations conditionally idempotent and make retries safer.
- Preconditions do not replace IAM, retention, holds, or business authorization.
- Persist version tokens alongside document records to reduce round trips; manage database/GCS consistency via state machines or reconciliation.

### References

- [Request preconditions — Cloud Storage](https://docs.cloud.google.com/storage/docs/request-preconditions)
- [Retry strategy — Cloud Storage](https://docs.cloud.google.com/storage/docs/retry-strategy)
- [Storage Java interface](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage)
- [Storage.BlobTargetOption Java API](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage.BlobTargetOption)
- [Storage.BlobSourceOption Java API](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage.BlobSourceOption)
- [Storage.BlobWriteOption Java API](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage.BlobWriteOption)
- [Upload objects from a file system](https://docs.cloud.google.com/storage/docs/uploading-objects)
- [Upload objects from memory](https://docs.cloud.google.com/storage/docs/uploading-objects-from-memory)
- [Object Versioning — Cloud Storage](https://docs.cloud.google.com/storage/docs/object-versioning)
