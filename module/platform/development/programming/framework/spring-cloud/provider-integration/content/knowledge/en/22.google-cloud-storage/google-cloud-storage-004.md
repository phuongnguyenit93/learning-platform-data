# Large Data Transfers and Choosing Resumable Transfer Strategies

## 1. Why Do We Need a Large Data Transfer Strategy?

When a Spring Boot application stores videos, backups, analytics datasets, report exports, or large documents, a long-running upload or download can hit timeouts, connection drops, process restarts, or out-of-space errors in temporary storage. If the application always restarts from byte zero, previously consumed bandwidth and wait time are wasted.

Google Cloud Storage (GCS) provides multiple data transfer mechanisms: single-request uploads, resumable uploads, streaming reads, byte-range reads, and parallel multi-part downloads. The Java client library adds **WriteChannel**, **ReadChannel**, and **TransferManager** so applications can choose the right approach.

This lesson belongs to the **Google Cloud Storage** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module focuses on practicing Spring Boot integration with managed services on AWS, Azure, and Google Cloud through the corresponding Spring Cloud libraries; learning identity and permissions configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences between cloud providers. This lesson focuses on transferring large payloads, recovering from interruptions, and balancing speed, memory, reliability, and cost.

After this lesson, you will be able to:

- Choose between direct upload, resumable upload, or parallel composite upload.
- Tune chunk/buffer sizes based on file size, bandwidth, and concurrency.
- Capture and restore **WriteChannel**/**ReadChannel** state when resuming work.
- Download large files via streaming or parallel byte ranges.
- Use generation to ensure all downloaded parts belong to the same object version.
- Verify integrity using CRC32C/MD5 based on object type and API.
- Design retries, timeouts, checkpoints, temporary files, and cleanup in Spring Boot.
- Evaluate trade-offs of Java TransferManager, resumable uploads, and parallel strategies.

> **Version scope:** Examples use the Google Cloud Storage Java client and TransferManager. TransferManager APIs and transport configurations depend on library version. Pin versions using a BOM compatible with your project's Spring Boot/Java versions and check the Javadoc for the resolved version. Chunk size values in this lesson are starting points for experimentation, not optimal settings for every workload.

## 2. Classifying Data Transfer Strategies

Before selecting an API, distinguish three goals:

- **Streaming:** transferring data incrementally through bounded memory without holding the entire object on the heap.
- **Resumable:** continuing from a saved state or offset after a request or process interruption.
- **Parallel/sliced:** splitting data into multiple parts and transferring them concurrently to increase throughput.

A single technique may satisfy multiple goals, but they are not synonymous. For instance, **WriteChannel** both streams and uses resumable upload; **TransferManager** can parallelize downloads; **ReadChannel.seek()** allows resuming reads from a specific offset.

~~~mermaid
flowchart TD
    START["Large data to transfer"] --> DIR{"Transfer direction"}
    DIR --> UP["Upload"]
    DIR --> DOWN["Download"]
    UP --> SMALL["Small, already in RAM<br/>Storage.create"]
    UP --> RESUME["Large or unstable network<br/>Storage.writer / createFrom"]
    UP --> FASTUP["High throughput needed<br/>Parallel composite upload"]
    DOWN --> STREAM["Sequential processing / HTTP response<br/>ReadChannel"]
    DOWN --> RESUME_D["Resume from offset needed<br/>ReadChannel.seek / capture"]
    DOWN --> FASTDOWN["Accelerate full-object download<br/>TransferManager sliced download"]
~~~

### 2.1. Quick Selection Table

| Scenario | Preferred approach | Reason |
| --- | --- | --- |
| Small JSON or image already in memory | **Storage.create(BlobInfo, byte[])** | Fewer steps, simple |
| Large file from local disk or HTTP request | **Storage.writer** or **Storage.createFrom** | Resumable upload and streaming |
| Upload may be interrupted and needs process recovery | **WriteChannel.capture() / restore()** or resumable session | Can continue from saved state |
| Many independent files uploaded together | TransferManager upload | Manages multiple concurrent tasks |
| One very large file needing faster upload | Parallel composite upload when bucket is compatible | Splits into components, uploads in parallel, then composes |
| Sequential download to HTTP response | **ReadChannel** | Avoids buffering the entire file in heap |
| Single large file download that may be interrupted | **ReadChannel.seek()** or restored reader state | Resumes from byte offset |
| Full-object download needing high throughput | TransferManager sliced download | Multiple range requests run in parallel |

## 3. Direct Upload and Resumable Upload

### 3.1. Direct Upload with a Byte Array

**Storage.create(BlobInfo, byte[])** fits small payloads that the application already holds in memory. The Java client performs a direct upload; if the request fails mid-way, the application usually must resend the entire payload.

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.nio.charset.StandardCharsets;

public Blob uploadSmall(
        Storage storage,
        String bucket,
        String objectName,
        String text) {

    BlobInfo info = BlobInfo.newBuilder(
            BlobId.of(bucket, objectName))
        .setContentType("text/plain; charset=utf-8")
        .build();

    return storage.create(
            info,
            text.getBytes(StandardCharsets.UTF_8),
            Storage.BlobTargetOption.doesNotExist());
}
~~~

Do not use this approach for large files if payload size is unbounded. Several concurrent requests can allocate multiple byte array copies on the heap, causing GC pressure or OutOfMemoryError.

### 3.2. How Does Resumable Upload Work?

Resumable upload splits an object transfer into an upload session. The client initiates the session, receives a session URI, and sends data across one or more requests. If the connection drops, the client can ask the server up to which byte was received and send the remaining bytes.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant GCS as Cloud Storage
    App->>GCS: Initiate resumable upload
    GCS-->>App: Session URI
    App->>GCS: Send chunk 0..N
    GCS-->>App: Stored offset
    App-xGCS: Connection lost while sending next chunk
    App->>GCS: Query session status
    GCS-->>App: Last persisted byte
    App->>GCS: Continue from next offset
    GCS-->>App: Upload complete + object metadata
~~~

Key characteristics to remember:

- The object does not appear as a complete object in the bucket until the upload finishes successfully.
- Metadata is declared when initiating the upload and attached to the object upon completion.
- The session URI is sensitive information; transmit it over HTTPS and do not write it to logs.
- A GCS resumable session has a maximum lifetime of one week; if it expires or the session URI is lost, start a new session.
- A session is bound to the region where it was initiated. Initiate near the bucket's location and keep the client continuing the upload in an appropriate region to avoid unnecessary traffic loops.
- When retrying from an offset already persisted by the server, do not send different data for those bytes. Ensure the upload source is not modified mid-transfer.

### 3.3. Java Storage.writer Always Uses Resumable Upload

The Java Cloud Storage client provides resumable upload overloads such as **Storage.writer(...)** and **Storage.createFrom(...)**. For large files, **writer** is far better than allocating a byte array.

~~~java
import com.google.cloud.WriteChannel;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.channels.Channels;

public void uploadLarge(
        Storage storage,
        BlobInfo info,
        InputStream source) throws Exception {

    WriteChannel writer = storage.writer(
            info,
            Storage.BlobWriteOption.doesNotExist());

    writer.setChunkSize(15 * 1024 * 1024);

    try (OutputStream output = Channels.newOutputStream(writer)) {
        source.transferTo(output);
    }
}
~~~

In the example, the 15 MiB buffer is the default documented for the current Java client resumable upload. It can be changed via **WriteChannel.setChunkSize(int)**. The buffer has a minimum of 256 KiB; the library aligns the size to multiples of 256 KiB.

Closing the output stream closes the writer and finalizes the upload. If the **InputStream** source is owned by the caller, the calling layer must close the source stream. In real applications, define stream ownership clearly so resources are neither closed prematurely nor leaked.

### 3.4. Uploading from a File Path with createFrom

When the source is a local file and you do not need manual control over each write, you can use **Storage.createFrom(...)**:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.nio.file.Path;

public Blob uploadPath(
        Storage storage,
        BlobInfo info,
        Path sourceFile) {

    return storage.createFrom(
            info,
            sourceFile,
            15 * 1024 * 1024,
            Storage.BlobWriteOption.doesNotExist());
}
~~~

**createFrom** overloads accepting **Path** or **InputStream** perform resumable uploads per the Java client reference. Use the overload with a buffer size if you need to tune memory usage and request size. Do not assume every **Storage.create** overload is resumable: the byte-array overload performs a direct upload.

## 4. Choosing Chunk Size and Buffer Size

Chunk size determines how much data the client buffers before sending an RPC. It affects throughput, request count, latency, memory usage, and how much data must be reprocessed when a transfer fails.

### 4.1. Chunk Size Trade-Offs

| Chunk size | Advantages | Limitations |
| --- | --- | --- |
| Small | Small buffer; easy to fit within memory limits | More RPCs, higher overhead, and potentially lower throughput |
| Medium | Balances throughput and memory across many workloads | Still needs benchmarking against network and concurrent uploads |
| Large | Can increase throughput on fast networks | Increases memory per upload; retrying a large chunk takes longer |

Java example:

~~~java
WriteChannel writer = storage.writer(blobInfo);
writer.setChunkSize(8 * 1024 * 1024);
~~~

8 MiB is only an example configuration. Do not increase chunk size by guesswork; measure actual speed, memory footprint, concurrent connections, and retry rates.

### 4.2. Estimating Memory Under Concurrent Uploads

If each writer retains a buffer close to chunk size, buffer memory can scale as:

**Approximate buffer memory = concurrent uploads × chunk size per upload**

For example, 12 concurrent uploads with a 15 MiB buffer may require around 180 MiB just for those buffers, excluding application heap, streams, TLS, HTTP transport, and other components. This is a planning estimate, not an exact guarantee of client heap allocation.

Enforce concurrency limits using an executor/semaphore or TransferManager worker limits. Adding more threads can reduce throughput if network, disk, or quota is already the bottleneck.

### 4.3. Choosing Chunks Based on Data Source

- Replayable local files: easy to retry because the source is stable and seekable.
- HTTP multipart streams: usually cannot be re-read once consumed; spool to a temporary file or design a client-driven upload session to support resume.
- Dynamically generated data: consider writing to a temporary file or using a checkpointed writer; byte order and source content must remain consistent.
- Streams of unknown length: resumable upload can still work; manage end-of-stream and close the writer to finalize.

## 5. Saving and Restoring WriteChannel State

Java **WriteChannel** implements the **Restorable** interface. You can call **capture()** to snapshot the writer's state, persist the **RestorableState<WriteChannel>** object, and call **restore()** to resume a writer from the saved state.

~~~java
import com.google.cloud.RestorableState;
import com.google.cloud.WriteChannel;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;

public RestorableState<WriteChannel> captureUploadState(
        Storage storage,
        BlobInfo info) {

    WriteChannel writer = storage.writer(info);
    writer.setChunkSize(15 * 1024 * 1024);

    // Persist state using the application's durable checkpoint mechanism.
    return writer.capture();
}
~~~

When restoring:

~~~java
import com.google.cloud.RestorableState;
import com.google.cloud.WriteChannel;
import java.io.ObjectInputStream;
import java.nio.file.Files;
import java.nio.file.Path;

@SuppressWarnings("unchecked")
public WriteChannel restoreUploadState(Path checkpointFile)
        throws Exception {

    try (ObjectInputStream input = new ObjectInputStream(
            Files.newInputStream(checkpointFile))) {
        RestorableState<WriteChannel> state =
                (RestorableState<WriteChannel>) input.readObject();
        return state.restore();
    }
}
~~~

**RestorableState** is designed to be serialized and restored. However, follow these rules:

1. Do not continue writing concurrently on both the original writer and the restored writer. Only one of them may be used.
2. Closing one channel closes the other; subsequent writes will fail.
3. Save the checkpoint and business state atomically to avoid a new checkpoint metadata pointing to an old source file or offset.
4. Keep the data source intact or ensure the unsent bytes can be re-read accurately.
5. Protect the checkpoint because the state may contain upload session details. Encrypt at rest, restrict read access, and do not log the state.
6. Pin library versions in deployments and test restore across restarts before relying on this mechanism for critical jobs.

If the application does not need to manage checkpoints itself, let the Java client handle resumable uploads via **Storage.writer** or **createFrom**. Use **capture/restore** only when you need to resume tasks across process boundaries or hand off a writer between components.

## 6. Resumable Upload via REST API and Session URI

In some architectures, the backend initiates a resumable session and hands the session URI to a browser or client to upload directly to GCS. This reduces bandwidth passing through the backend, but permissions and session lifecycle must be tightly controlled.

~~~mermaid
sequenceDiagram
    participant Browser as Web client
    participant API as Spring Boot API
    participant GCS as Cloud Storage

    Browser->>API: Request upload for document ID
    API->>API: Authenticate user and check quota
    API->>GCS: Initiate resumable upload
    GCS-->>API: Session URI
    API-->>Browser: Time-limited Session URI
    Browser->>GCS: Send chunks over HTTPS
    GCS-->>Browser: Offset/progress
    Browser->>GCS: Send remaining part
    GCS-->>Browser: Upload complete
    Browser->>API: Notify completion, send object ID
    API->>GCS: Verify metadata/generation
~~~

A session URI grants permission to continue uploading the initiated object; treat it like a bearer credential. Do not expose the URI in analytics URLs, access logs, crash reports, or telemetry. Do not let clients choose arbitrary bucket/object names. The backend must bind the session to the user, tenant, object name, content type, maximum size, and validity window.

Consider the upload complete only after GCS confirms success and the backend verifies object metadata, generation, size, or checksums as required. Do not trust completion notifications from the browser alone.

## 7. Parallel Composite Upload: When High Throughput Is Needed

### 7.1. Mechanism

Parallel composite upload splits a large file into component objects, uploads the components in parallel, and uses compose to assemble the final object. Temporary components are cleaned up after compose succeeds.

~~~mermaid
flowchart TD
    FILE["Large source file"] --> SPLIT["Split into components"]
    SPLIT --> P1["Upload component 1"]
    SPLIT --> P2["Upload component 2"]
    SPLIT --> P3["Upload component 3"]
    P1 --> COMPOSE["Compose in exact order"]
    P2 --> COMPOSE
    P3 --> COMPOSE
    COMPOSE --> FINAL["Final complete object"]
    P1 -. "Cleanup" .-> CLEAN["Delete temporary components"]
    P2 -. "Cleanup" .-> CLEAN
    P3 -. "Cleanup" .-> CLEAN
~~~

Java TransferManager supports parallel composite uploads when appropriately configured and when chunking benefits the workload. Example:

~~~java
import com.google.cloud.storage.transfermanager.ParallelUploadConfig;
import com.google.cloud.storage.transfermanager.TransferManager;
import com.google.cloud.storage.transfermanager.TransferManagerConfig;
import com.google.cloud.storage.transfermanager.UploadResult;
import java.nio.file.Path;
import java.util.List;

public List<UploadResult> uploadFilesInParallel(
        String bucket,
        List<Path> files) throws Exception {

    TransferManager manager = TransferManagerConfig.newBuilder()
            .setAllowParallelCompositeUpload(true)
            .setMaxWorkers(8)
            .build()
            .getService();

    try (manager) {
        ParallelUploadConfig config = ParallelUploadConfig.newBuilder()
                .setBucketName(bucket)
                .build();

        return manager.uploadFiles(files, config).getUploadResults();
    }
}
~~~

**getUploadResults()** waits for uploads to finish and returns per-file results. Inspect each result's status; do not assume job completion means every file succeeded.

### 7.2. Important Conditions and Limitations

Parallel composite uploads can accelerate transfers but create extra temporary objects and operations:

- A single compose call accepts at most 32 source objects; TransferManager handles splitting and composing within service limits.
- The final object is a composite object, which has a CRC32C checksum but no MD5 hash.
- If downstream consumers require MD5, do not choose this strategy unless the integrity-checking contract can be changed.
- Uploading components and composing generates additional Class A operations; costs may increase.
- For storage classes other than Standard, temporary components may incur early deletion fees.
- Buckets with retention policies or default object holds may prevent component cleanup.
- Object Versioning and soft delete can retain deleted components, increasing storage costs.
- If the process stops mid-way, temporary components may remain; a monitoring and cleanup procedure is required.
- Permissions are needed to create, read/compose, and delete component objects; **roles/storage.objectUser** is typically a starting point for evaluating permissions.

Enable this technique only when benchmarks show throughput gains outweigh the added cost and complexity. For ordinary uploads, resumable **WriteChannel** is usually simpler to operate.

## 8. Sequential Download with ReadChannel

### 8.1. Streaming to a File

For large objects, do not call **getContent()** to load all bytes onto the heap. Use **ReadChannel** and transfer buffers to a file:

~~~java
import com.google.cloud.ReadChannel;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.io.OutputStream;
import java.nio.channels.Channels;
import java.nio.file.Files;
import java.nio.file.Path;

public void downloadToFile(
        Storage storage,
        String bucket,
        String objectName,
        Path destination) throws Exception {

    try (ReadChannel reader = storage.reader(
                BlobId.of(bucket, objectName));
         OutputStream output = Files.newOutputStream(destination)) {
        Channels.newInputStream(reader).transferTo(output);
    }
}
~~~

This example streams directly to the file. In production, write to a temporary file on the same filesystem, verify the checksum upon completion, and then atomically move it to the destination file. This prevents users from seeing an incomplete file under the final filename.

### 8.2. Tuning Read Chunk Size

**ReadChannel.setChunkSize(int)** sets the minimum size of an RPC read; data is buffered locally until consumed by the application. Larger chunks can reduce RPC count but increase memory usage and read-ahead volume. Smaller chunks fit tighter memory budgets but can increase overhead.

Do not use the same chunk size for every workload. Measure latency, throughput, heap usage, and concurrent downloads in a production-like environment.

## 9. Resuming Downloads from a Byte Offset

### 9.1. Why Must You Pin the Generation?

If a download is interrupted and the application resumes from the old offset using the live object name, the object may have been replaced. In that case, the start of the file comes from the old generation while the remainder comes from the new generation, creating silent corruption that is hard to detect.

Read metadata first, save the generation, and resume reading that exact generation. Generation is passed in **BlobId** to identify a specific data version.

### 9.2. Resuming with seek

Skeleton example of resuming a download from a checkpointed offset:

~~~java
import com.google.cloud.ReadChannel;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public void resumeDownload(
        Storage storage,
        String bucket,
        String objectName,
        long generation,
        long completedBytes,
        Path partialFile) throws Exception {

    BlobId pinnedVersion = BlobId.of(bucket, objectName, generation);

    try (ReadChannel reader = storage.reader(pinnedVersion);
         FileChannel output = FileChannel.open(
                 partialFile,
                 StandardOpenOption.CREATE,
                 StandardOpenOption.READ,
                 StandardOpenOption.WRITE)) {

        if (output.size() < completedBytes) {
            throw new IllegalStateException("Temporary file is shorter than checkpoint");
        }
        output.truncate(completedBytes);
        output.position(completedBytes);
        reader.seek(completedBytes);

        ByteBuffer buffer = ByteBuffer.allocate(8 * 1024 * 1024);
        int read;
        while ((read = reader.read(buffer)) != -1) {
            if (read == 0) {
                continue;
            }
            buffer.flip();
            while (buffer.hasRemaining()) {
                output.write(buffer);
            }
            buffer.clear();
        }
        output.force(true);
    }
}
~~~

This snippet illustrates the offset logic. In real implementations, use **FileChannel.position(completedBytes)** or a controlled append mechanism to write at the exact position. Before resuming, confirm the temporary file size matches the checkpoint; truncate any partially written trailing bytes after the checkpoint if necessary.

### 9.3. Resuming with ReadChannel capture/restore

**ReadChannel** also implements **Restorable**. You can call **capture()** to save the reader's state and restore it via **RestorableState.restore()**. This is useful when another worker resumes the task or the application needs to persist read state.

Do not use the original reader and the restored reader concurrently. Persist checkpoints durably, protect the state, pin the generation, and test recovery across process restarts. For straightforward tasks, persisting generation + byte offset and calling **seek()** is often easier to observe and operate.

## 10. Byte-Range Downloads over HTTP

Cloud Storage supports HTTP Range requests to read part of an object. Example header:

~~~http
Range: bytes=0-8388607
~~~

Byte ranges are inclusive: **bytes=0-8388607** requests the first 8 MiB. When a download is interrupted, the client can request the remaining bytes starting from the next byte offset.

A safe resume workflow requires:

1. Read generation and size before downloading.
2. Send range requests targeting the resolved generation.
3. Write data into the temporary file at the exact offset.
4. Persist the checkpoint after bytes are durably flushed to disk.
5. When resuming, use the same generation and offset.
6. After downloading all bytes, verify the size and full-object checksum.
7. Atomically move the temporary file to its final name.

If calling the JSON/XML API directly, handle status codes, **Content-Range**, response length, timeouts, and retries. When using Java **ReadChannel**, the client library manages the read protocol; the application still manages checkpoints and temporary files.

## 11. Sliced Object Downloads and TransferManager

### 11.1. When Should You Use It?

Sliced download splits a large object into multiple range GETs, downloads them in parallel into regions of a temporary file, and assembles the complete file. This can boost throughput when network and disk are fast enough.

Java TransferManager supports enabling divide-and-conquer downloads:

~~~java
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.transfermanager.DownloadResult;
import com.google.cloud.storage.transfermanager.ParallelDownloadConfig;
import com.google.cloud.storage.transfermanager.TransferManager;
import com.google.cloud.storage.transfermanager.TransferManagerConfig;
import java.nio.file.Path;
import java.util.List;

public List<DownloadResult> downloadInParallel(
        String bucket,
        List<BlobInfo> objects,
        Path destinationDirectory) throws Exception {

    TransferManager manager = TransferManagerConfig.newBuilder()
            .setAllowDivideAndConquerDownload(true)
            .setMaxWorkers(8)
            .build()
            .getService();

    try (manager) {
        ParallelDownloadConfig config = ParallelDownloadConfig.newBuilder()
                .setBucketName(bucket)
                .setDownloadDirectory(destinationDirectory)
                .build();

        return manager.downloadBlobs(objects, config).getDownloadResults();
    }
}
~~~

TransferManager accepts a list of BlobInfo objects and downloads them concurrently; divide-and-conquer allows splitting an object into slices when the library determines it is beneficial. **getDownloadResults()** waits for completion and provides status for each download.

### 11.2. Pinning Generation for Each Object

When downloading across multiple ranges, all slices must read the exact same generation. Construct BlobInfo with a BlobId containing the generation read earlier:

~~~java
BlobInfo sourceVersion = BlobInfo.newBuilder(
        BlobId.of(bucket, objectName, expectedGeneration))
    .build();
~~~

Include that BlobInfo in the download list. If the live object name changes while ranges are running, failing to pin generation can produce inconsistent data chunks. GCS documentation recommends providing the source generation for every sliced download request to prevent corruption.

### 11.3. Costs and Limitations

- Multiple range requests increase total request count and can increase costs.
- Concurrent slices consume threads, connections, buffers, and disk I/O.
- Random-offset writes to a file can be slow on disks with poor seek performance.
- Sliced download is suitable only when downloading the entire object; if only a segment is needed, use a single range read.
- CRC32C is needed to verify integrity of sliced downloads.
- Ensure sufficient disk space for temporary files and clean up on job failure.

If disk or network is already saturated, adding workers will not improve speed. Benchmark with a low worker count first and scale up gradually.

## 12. Checksums and Data Integrity

### 12.1. CRC32C and MD5

Cloud Storage supports checksums to detect data corruption during transit:

- **CRC32C:** recommended checksum for many data verification flows, especially with composite objects and sliced downloads.
- **MD5:** can be used to verify certain standard object uploads/downloads when the object has an MD5 value.
- **ETag:** is a validator; never assume ETag always equals MD5.

Parallel composite upload produces a composite object with only CRC32C and no MD5. If downstream applications require MD5, choose another upload strategy or update the integrity verification contract.

### 12.2. Do Not Validate Individual Chunks Against the Full-Object Checksum

An object's checksum applies to the entire object. Do not compare the full-object checksum against the checksum of a single byte range or chunk. With sliced downloads, verify CRC32C using mechanisms supported by the tool/client and ultimately verify the complete file.

### 12.3. Storing a Manifest for Transfer Jobs

A large transfer job can persist a manifest:

~~~json
{
  "jobId": "transfer-2026-001",
  "bucket": "training-large-files-dev",
  "objectName": "exports/archive-001.bin",
  "generation": 1740000000000000,
  "expectedSize": 10737418240,
  "checksumType": "CRC32C",
  "completedBytes": 5368709120,
  "state": "IN_PROGRESS"
}
~~~

This is illustrative data. Store the manifest in a database/job store rather than cramming full transfer state into object metadata. Useful fields include job ID, bucket/object, generation, size, checksum, checkpoint/offset, update timestamp, retry count, and state. Never log session URIs or RestorableState in plaintext.

## 13. Retries, Timeouts, and Idempotency

### 13.1. Retrying Transient Errors

The Java Cloud Storage client includes retry/backoff for operations determined to be idempotent. Common transient errors include:

- Connection reset or unexpectedly closed connections.
- HTTP 408 Request Timeout.
- HTTP 429 Too Many Requests.
- HTTP 500, 502, 503, and 504.

The Java client uses exponential backoff and allows configuring RetrySettings. Do not wrap every exception in an unbounded manual retry loop.

### 13.2. Distinguishing Retryable Errors

| Error | Handling approach |
| --- | --- |
| Timeout/connection drop | Check upload/download status and resume from checkpoint if available |
| 429 or 5xx | Retry with backoff and a total duration cap |
| 401 | Check ADC/tokens; do not keep retrying with invalid credentials |
| 403 | Check IAM/policies; do not retry if permissions have not changed |
| 404 | Check bucket/object/generation and data lifecycle |
| 412 Precondition Failed | Re-read generation and handle conflict; do not drop preconditions |
| Checksum mismatch | Do not publish file; re-download/re-initiate per chosen strategy |

### 13.3. Upload Idempotency

An upload request may already have been processed by GCS while the client lost the response. If retried without a precondition, the application could overwrite the completed object. Use **doesNotExist()** for new objects or generation preconditions for conditional replacements.

When encountering an ambiguous timeout, check the object/generation/checksum before starting a new upload. Do not assume a timeout means the server never received the data.

### 13.4. Per-Stage Timeouts

Set reasonable timeouts for:

- Session initiation.
- Each chunk or RPC.
- Total job duration.
- Graceful shutdown wait time.
- Retry/backoff total duration.

Large uploads should not share the same short timeout as metadata-read APIs. However, setting infinite timeouts holds workers and connections too long. Use overall deadlines, cancellation, and progress reporting so operators know whether a job is active or stuck.

## 14. Controlling Transfer Sources and Destinations

### 14.1. Sources Must Be Stable

If a source file changes during a resumable upload, retries may send inconsistent bytes. You can:

- Create a snapshot or copy the file into a staging directory.
- Record size, modification time, and checksum before starting.
- Keep the file immutable throughout the upload.
- Verify the final checksum before marking the job complete.

For non-replayable stream sources, write to a temporary file or design a pipeline with dedicated checkpointing.

### 14.2. Download Destinations Need Temporary Files

Do not download directly into a filename that users or other services are reading. Use a temporary file, track offsets, and rename only after integrity verification. If the job fails, retain the temporary file for resumption or clean it up according to policy.

### 14.3. Limiting Concurrency

Each concurrent job consumes:

- A portion of heap/buffers.
- Network connections.
- File descriptors.
- CPU for checksums/encryption.
- Disk bandwidth and IOPS.
- Cloud Storage request quota/operations.

Set max workers according to the container/VM resource budget. Isolate the upload/download pool from HTTP request threads so the API server is not starved.

## 15. Operations and Progress Observability

A transfer job should have explicit states:

| State | Meaning |
| --- | --- |
| PENDING | Job created, transfer not yet started |
| INITIATING | Creating resumable session or preparing file |
| IN_PROGRESS | Transferring bytes |
| PAUSED | Checkpointed, awaiting resumption |
| VERIFYING | Verifying size/checksum/generation |
| COMPLETED | Finished and verified |
| RETRYING | Handling transient error |
| FAILED | Unrecoverable error |
| CANCELLED | Stopped upon request |

Useful metrics:

- Bytes sent/received and total bytes.
- Average/current transfer rate.
- Chunk size and worker count.
- Retry count, error codes, and backoff durations.
- Time spent in initiation, transfer, verification, and cleanup.
- Heap/buffer usage, network throughput, free disk space.
- Remaining temporary components after parallel composite uploads.

Do not log session URIs, signed URLs, access tokens, file contents, or RestorableState. Use internal job IDs and object IDs to correlate logs and traces.

## 16. Example TransferJob Design in Spring Boot

A service can separate the orchestration API from data transfer workers:

~~~java
public interface TransferJobRepository {
    TransferJob findById(String jobId);
    void save(TransferJob job);
}

public record TransferJob(
        String jobId,
        String bucket,
        String objectName,
        long generation,
        long totalBytes,
        long completedBytes,
        String checksum,
        TransferState state) {}

public enum TransferState {
    PENDING,
    IN_PROGRESS,
    PAUSED,
    VERIFYING,
    COMPLETED,
    FAILED,
    CANCELLED
}
~~~

The orchestration service is responsible for:

1. Authenticating the user and verifying document access permissions.
2. Generating a stable job ID and object name.
3. Choosing the transfer method based on size, data source, and resume requirements.
4. Saving metadata/checkpoints.
5. Dispatching work to an executor/queue.
6. Updating bytes transferred and state at checkpoints.
7. Verifying generation/size/checksum upon completion.
8. Publishing the object for business use after verification.

Do not hold an HTTP request open for minutes just to upload a multi-GB file. Return a job ID so the client can track progress; the backend performs the transfer in resource-bounded workers.

## 17. Testing Failures and Recovery

### 17.1. Unit Tests

- Choosing upload strategy based on size and source type.
- Generating stable object names and metadata.
- Computing checkpoints/offsets accurately.
- Never advancing the offset before bytes are durably written.
- Mapping 403/404/412/5xx errors.
- Marking COMPLETED only after checksum/size verification.

### 17.2. Integration Tests with a GCP Test Project

1. Upload a file large enough to exercise the resumable writer.
2. Verify the object appears completely only after the writer closes successfully.
3. Capture state, restore the writer, and continue writing.
4. Download an object with a pinned generation, seek from an offset, and append to a temporary file.
5. Replace the live object between two reads; verify generation pinning protects the content.
6. Run a sliced download with TransferManager and verify CRC32C.
7. Check individual UploadResult/DownloadResult outcomes.
8. Verify IAM permissions, timeouts, and retries.
9. Clean up temporary components/files and confirm no unexpected resources remain.

### 17.3. Fault Injection

Simulate scenarios:

- Network drop mid-chunk.
- Process kill after a checkpoint is saved.
- Disk full during download.
- Source file modified mid-upload.
- Expired credentials.
- GCS returning 429/503.
- Object overwritten before resuming download.
- Component cleanup failure after parallel composite upload.

Expected outcomes: no corrupted final file produced, no mixed generations, no false job completion marks, no infinite retries, and controlled resumption or failure.

## 18. Common Errors and Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Upload restarts from zero after network drop | Using direct upload or not saving session/checkpoint | Use resumable writer or createFrom |
| Slow upload despite large file | Chunk too small, high network round-trip, or small buffer | Benchmark chunk size and bucket location |
| OOM during concurrent uploads | Buffer × worker count exceeds memory budget | Reduce chunk size or concurrency |
| Resumed upload fails with checksum mismatch | Source file changed between sends | Snapshot source and verify checksum |
| Session URI unusable | Expired, cancelled, or lost | Initiate a new session and re-upload |
| Resumed download produces corrupted file | Wrong offset or live object changed generation | Pin generation and verify temporary file size |
| Sliced download is slower | Slow disk seeks or too many workers | Reduce slice count, use sequential streaming |
| Composite upload missing MD5 | Final object is a composite object | Use CRC32C or choose non-composite upload |
| Temporary components left in bucket | Job died before cleanup | Monitor temporary prefix and run cleanup process |
| Parallel composite upload fails with 403 | Missing get/delete permissions on components | Grant properly scoped IAM object permissions |
| Uploaded components cannot be deleted | Retention, hold, soft delete, or versioning | Review bucket policy before enabling this technique |
| 412 when resuming/writing | Generation precondition no longer matches | Re-read state and make a business decision |
| Worker hangs | Excessively long timeout or unbounded retries | Set overall deadlines, cancellation, and progress metrics |

## 19. Comparison with AWS S3 and Azure Blob Storage

| Aspect | Google Cloud Storage | Amazon S3 | Azure Blob Storage |
| --- | --- | --- | --- |
| Resumable upload | Resumable upload session, Java WriteChannel | Multipart upload, upload ID and part number | Block blob staged blocks and commit block list |
| Resumable download | Range requests, ReadChannel seek/capture | Range GET and ETag/version conditions | Range download and ETag/version conditions |
| Parallel upload | TransferManager parallel composite upload | Multipart upload | Parallel block upload |
| Version token | Generation | Version ID / ETag | Version ID / ETag |
| Checksum | CRC32C and MD5 per object/API | CRC/checksum algorithms per API | Transactional/content checksum per API |
| Cleanup | Component objects after compose | Abort multipart upload and clean up parts | Uncommitted blocks/lifecycle per API |

Do not normalize session URIs, upload IDs, generations, ETags, and block IDs into a single token type assuming identical semantics. A multi-cloud adapter should expose business operations such as upload, resume, downloadRange, and verify; each provider's adapter encapsulates session, part/block, precondition, and cleanup details.

## 20. Key Takeaways

- Small files can use direct upload; large files should use resumable upload via **Storage.writer** or **Storage.createFrom**.
- Java **WriteChannel** and **ReadChannel** support **capture/restore**; checkpoints must be stored securely and only one channel instance may continue being used.
- Chunk size is a trade-off between throughput, RPC count, retries, and memory; account for concurrent workers.
- Resumed downloads must pin generation and write to a temporary file at verified offsets.
- TransferManager sliced downloads can accelerate transfers when network/disk allow; require CRC32C and worker limits.
- Parallel composite uploads can improve throughput but create temporary objects, extra operations, cleanup requirements, and provide no MD5 for the final object.
- Retries must rely on idempotency, preconditions, deadlines, and actual object state.
- Publish files only after verifying size/checksum; log progress without logging session URIs or sensitive payloads.

### References

- [Resumable uploads — Cloud Storage](https://docs.cloud.google.com/storage/docs/resumable-uploads)
- [Perform resumable uploads — Cloud Storage](https://docs.cloud.google.com/storage/docs/performing-resumable-uploads)
- [Retry strategy — Cloud Storage](https://docs.cloud.google.com/storage/docs/retry-strategy)
- [Sliced object downloads — Cloud Storage](https://docs.cloud.google.com/storage/docs/sliced-object-downloads)
- [Parallel composite uploads — Cloud Storage](https://docs.cloud.google.com/storage/docs/parallel-composite-uploads)
- [Object reads and downloads — Cloud Storage](https://docs.cloud.google.com/storage/docs/reads-and-downloads)
- [Java Storage interface](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage)
- [Java TransferManager](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.transfermanager.TransferManager)
- [Java TransferManagerConfig](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.transfermanager.TransferManagerConfig)
- [Java ReadChannel](https://docs.cloud.google.com/java/docs/reference/google-cloud-core/latest/com.google.cloud.ReadChannel)
- [Java WriteChannel](https://docs.cloud.google.com/java/docs/reference/google-cloud-core/latest/com.google.cloud.WriteChannel)
- [Java RestorableState](https://docs.cloud.google.com/java/docs/reference/google-cloud-core/latest/com.google.cloud.RestorableState)
