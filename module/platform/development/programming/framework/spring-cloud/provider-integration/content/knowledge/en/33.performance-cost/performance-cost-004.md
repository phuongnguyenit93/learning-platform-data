# Streaming Data to Bound Memory

An endpoint receiving multi-gigabyte files must not turn the entire payload into a `byte[]` before calling cloud storage. Doing so grows the heap proportionally to file size, introduces extra copies during encoding/serialization, and risks Full GC or `OutOfMemoryError`. With streaming, the application reads one portion of data, forwards it to storage, releases the buffer, and only then requests the next portion. Memory stays roughly bounded by chunk size and concurrency rather than scaling with total object size.

This lesson focuses on large data transfers through Spring WebFlux and cloud storage SDKs. You will design pipelines with backpressure, choose chunk size and concurrency, release pooled buffers properly along their lifecycle, handle cancellation/retries, and compare streaming models across Amazon S3, Azure Blob Storage, and Google Cloud Storage.

This lesson belongs to the **Performance and Cost** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module covers integrating Spring Boot with managed services on AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries, including identity/permissions configuration, storage, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers.

## 1. Learning outcomes

After this lesson, you will be able to:

- Distinguish between streaming, buffering, aggregation, and file staging.
- Explain why `byte[]`, `readAllBytes()`, `collectList()`, and `downloadContent()` can make memory scale with object size.
- Build WebFlux endpoints that accept and return data in chunks.
- Manage `DataBuffer` lifecycles, especially with Reactor Netty pooled/direct buffers.
- Upload/download to S3 using AWS SDK for Java 2.x with async bodies, response publishers, and multipart transfers.
- Configure Azure Blob async uploads/downloads by block size and max concurrency.
- Use Google Cloud Storage `ReadChannel`, `WriteChannel`, and resumable uploads.
- Choose when to stream directly vs. stage to a temporary file for retry/replay support.
- Calculate memory budgets from chunk size, concurrency, and copy counts.
- Handle timeouts, cancellation, checksums, cleanup, and large-transfer load tests.

## 2. Buffering entire payloads scales memory with file size

An easy-to-write implementation that is unsuitable for large files:

~~~java
byte[] content = inputStream.readAllBytes();
s3Client.putObject(request, RequestBody.fromBytes(content));
~~~

`readAllBytes()` reads the entire stream onto the heap. For a 2 GiB file, the byte array alone requires roughly 2 GiB; in practice there can also be copies from HTTP decoders, byte arrays, compression, the SDK, and response processing. With multiple concurrent requests, memory grows with the combined size of all files.

APIs/operations to scrutinize carefully:

| Approach | Behavior | Risk |
| --- | --- | --- |
| `InputStream.readAllBytes()` | Reads the entire stream into one array | Heap scales with entire payload |
| `DataBufferUtils.join()` | Joins multiple buffers into one buffer | Aggregation; must enforce a byte limit |
| `Flux.collectList()` | Holds all items in a list | Memory scales with item count and payload |
| `Mono<byte[]>` / `@RequestBody byte[]` | Decodes entire body into an array | Unsuitable for large files |
| Azure `downloadContent()` | Reads entire blob into BinaryData | Not a streaming API |
| GCS `readAllBytes()` | Returns entire object in a `byte[]` | Memory scales with object size |
| S3 `AsyncResponseTransformer.toBytes()` | Collects full response body into bytes | Unsuitable when forwarding streams |

Streaming holds small portions of data for a brief window. Only after downstream finishes consuming a chunk does upstream emit the next chunk on demand.

## 3. Streaming model and backpressure

A WebFlux upload flow typically looks like this:

~~~mermaid
flowchart LR
    A[HTTP client] --> B[Flux DataBuffer]
    B --> C[Enforce request size]
    C --> D[Transform chunks]
    D --> E[Cloud SDK upload]
    E --> F[Storage service]
    E -. demand .-> D
    D -. request next .-> C
    C -. backpressure .-> B
~~~

Steps that avoid holding the entire object:

1. The web server receives a buffer.
2. The controller forwards the buffer to the SDK or a staging sink.
3. The SDK writes the chunk into the request/multipart part.
4. The buffer is consumed and released.
5. The pipeline requests the next chunk.

Backpressure only works when every layer honors Reactive Streams demand. If a controller calls `subscribe()` independently, pushes data into an unbounded queue, or collects all buffers before uploading, the application breaks flow control.

Never use an unbounded `onBackpressureBuffer()` to hide a slow downstream. If a queue is needed, bound both item count and bytes, and pick an explicit behavior when full: wait on upstream, reject requests, persist durably, or cancel the operation.

## 4. Spring WebFlux: receiving and returning chunked data

### 4.1. Using Flux<DataBuffer> for raw bodies

For endpoints receiving binary bodies, you can accept `Flux<DataBuffer>` directly:

~~~java
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
class UploadController {

    private final ObjectStorageService storage;

    UploadController(ObjectStorageService storage) {
        this.storage = storage;
    }

    @PostMapping(
        path = "/objects",
        consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    Mono<Void> upload(@RequestBody Flux<DataBuffer> body) {
        return storage.upload("incoming/object.bin", body);
    }
}
~~~

The controller returns a `Mono<Void>` tied to the entire operation. Do not call `subscribe()` inside the controller; subscribing manually can let the HTTP request lifecycle end before the upload finishes, and errors will not propagate to the HTTP response.

### 4.2. Codec memory limits

WebFlux configures `maxInMemorySize` for decoders/message readers that must buffer part or all of a body to materialize an object. You can explicitly set this cap on default codecs:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
class WebFluxCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(256 * 1024);
    }
}
~~~

This limit applies to data a codec must buffer, such as a JSON object or a section requiring decoding. It is not a total upload file size cap when the body is streamed. The application still needs to enforce total received bytes, user quotas, disk budgets, and concurrent upload limits.

Do not raise `maxInMemorySize` to hundreds of megabytes merely to silence `DataBufferLimitException` on a large payload. If the use case is large files, stream in chunks; if the use case is large JSON documents, bound document size by business rules.

### 4.3. Multipart uploads with PartEvent

When receiving both form fields and files in one multipart request, WebFlux supports `Flux<PartEvent>`. Large files can arrive as multiple events without assembling the entire file into a single `FilePart`/byte array before processing.

~~~java
import org.springframework.http.codec.multipart.FilePartEvent;
import org.springframework.http.codec.multipart.FormPartEvent;
import org.springframework.http.codec.multipart.PartEvent;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<Void> handleMultipart(Flux<PartEvent> events) {
    return events
        .windowUntil(PartEvent::isLast)
        .concatMap(part -> part.switchOnFirst((signal, partEvents) -> {
            if (!signal.hasValue()) {
                return partEvents.then();
            }

            PartEvent event = signal.get();
            if (event instanceof FormPartEvent form) {
                return saveFormField(form.name(), form.value());
            }
            if (event instanceof FilePartEvent file) {
                Flux<DataBuffer> content =
                    partEvents.map(PartEvent::content);
                return storage.upload(file.filename(), content);
            }
            return Mono.error(
                new IllegalArgumentException("Unsupported part"));
        }))
        .then();
}
~~~

This illustrates the structure; `saveFormField` and `storage.upload` are application services. Every part's content must be fully consumed, forwarded, or released. If a part is skipped, release its buffers to avoid leaking pooled memory.

## 5. DataBuffer lifecycle and pooled memory

### 5.1. Why must buffers be released?

WebFlux can use Netty pooled/direct buffers. Such a `DataBuffer` wraps memory managed by reference counting. If the application retains a buffer after a callback finishes or drops it without releasing, the memory may never return to the pool.

Rules:

- If you read/consume the buffer yourself, release it afterward.
- If you hand a buffer to another API that retains it asynchronously, do not release before that API finishes reading.
- If an operator discards buffers due to filter/skip/cancel/error, add `doOnDiscard(DataBuffer.class, DataBufferUtils::release)`.
- Never release the same buffer twice.
- If a buffer must span multiple callbacks, understand and pair retain/release reference counts properly.

### 5.2. Releasing buffers when converting to ByteBuffer

Azure Blob async accepts `Flux<ByteBuffer>`. The example below copies each chunk into an independent byte array and immediately releases the pooled `DataBuffer`:

~~~java
import java.nio.ByteBuffer;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import reactor.core.publisher.Flux;

Flux<ByteBuffer> toByteBuffers(Flux<DataBuffer> source) {
    return source
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
        .map(dataBuffer -> {
            byte[] copy = new byte[dataBuffer.readableByteCount()];
            dataBuffer.read(copy);
            DataBufferUtils.release(dataBuffer);
            return ByteBuffer.wrap(copy);
        });
}
~~~

In return, each chunk incurs one copy. This makes ownership clear; if optimizing for zero-copy, you must guarantee the SDK never reads the `ByteBuffer` after the underlying `DataBuffer` has been released.

### 5.3. DataBufferUtils.write does not release buffers automatically

When streaming to a `WritableByteChannel`, `OutputStream`, or `AsynchronousFileChannel`, `DataBufferUtils.write(...)` returns a `Flux` of written buffers and does not release them automatically. Attach `DataBufferUtils.releaseConsumer()` or an equivalent release after writes succeed:

~~~java
DataBufferUtils.write(source, channel)
    .doOnNext(DataBufferUtils.releaseConsumer())
    .then();
~~~

In production code, attach the discard hook on the source before calling `write`, then release each emitted buffer once writing succeeds. Example:

~~~java
Flux<DataBuffer> safeSource = source
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release);

return DataBufferUtils.write(safeSource, channel)
    .doOnNext(DataBufferUtils.releaseConsumer())
    .then();
~~~

This method only illustrates buffer lifecycle; channels opened by the application must be closed separately. If using `DataBufferUtils.write(source, path)`, verify lifecycle behavior for your Spring version and still test for pooled buffer leaks on cancel or error.

### 5.4. subscriberInputStream with bounded demand

When an SDK only offers an `InputStream` API, Spring provides `DataBufferUtils.subscriberInputStream(publisher, demand)`. The `demand` parameter caps how many `DataBuffer`s are requested/held in the internal queue. Closing the `InputStream` cancels the subscription and releases queued buffers. This is a useful bridge between WebFlux request bodies and blocking/stream SDK APIs.

Example:

~~~java
InputStream input = DataBufferUtils.subscriberInputStream(requestBody, 4);
~~~

With `demand` of 4, the queue holds roughly up to four buffers under the API's demand mechanism, excluding buffers currently being read or buffered at other layers. Always close the `InputStream` on completion, error, or cancellation.

## 6. Bounding total request size

Codec limits are not total file limits. You can count bytes buffer by buffer before forwarding to storage:

~~~java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<DataBuffer> enforceMaxBytes(
        Flux<DataBuffer> source,
        long maxBytes) {
    return Flux.defer(() -> {
        AtomicLong received = new AtomicLong();
        return source.concatMap(buffer -> {
                long total = received.addAndGet(
                    buffer.readableByteCount());
                if (total > maxBytes) {
                    DataBufferUtils.release(buffer);
                    return Mono.error(new PayloadTooLargeException());
                }
                return Mono.just(buffer);
            }, 1)
            .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
    });
}
~~~

`PayloadTooLargeException` is an application exception and should map to HTTP 413. The counter is created inside `Flux.defer` so every subscription gets its own counter. When exceeded, the overflowing buffer is released and the subscription errors; the discard hook releases any buffers still sitting in operator queues.

In addition to max bytes, enforce:

- Concurrent upload limits per user/tenant.
- Overall upload deadline and per-request/chunk timeout.
- Limits on part count and form field sizes in multipart uploads.
- Storage quotas and temporary file cleanup policies.
- Validation of content types, file signatures, and object-key write permissions.

## 7. Memory budget for streaming

A simple estimate for a single upload:

**M_upload ≈ U × B + P × C + M_codec + M_copy**

Where:

- **U:** number of upstream `DataBuffer`s that may be held concurrently.
- **B:** average/p95 size of one `DataBuffer`.
- **P:** number of parts/chunks the cloud SDK processes in parallel.
- **C:** chunk size of a part.
- **M_codec:** HTTP decoder, TLS, and network stack buffers.
- **M_copy:** application-allocated byte array/`ByteBuffer` copies.

For example, the SDK uploads 4 parts in parallel, each 8 MiB:

**P × C = 4 × 8 MiB = 32 MiB**

This is only the estimated multipart buffer share, before request buffers, responses, direct memory, TLS, and other uploads.

With 20 concurrent uploads under the same settings:

**M_parts ≈ 20 × 4 × 8 MiB = 640 MiB**

Therefore, you must bound all of:

1. Concurrent active uploads.
2. Parallel parts per upload.
3. Chunk size.
4. Upstream buffering/prefetching.
5. Copies created in application code.

Streaming prevents memory from scaling with total file size, yet memory is not constant regardless of concurrency and chunk settings.

## 8. AWS S3: async streaming and multipart transfers

### 8.1. Enabling multipart on S3AsyncClient

The Java-based S3 async client supports parallel multipart uploads/downloads starting in AWS SDK for Java 2.x version 2.27.5. Configure `multipartEnabled(true)` to enable parallel transfers; the current default threshold and minimum part size are 8 MiB.

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;

S3AsyncClient s3 = S3AsyncClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .multipartEnabled(true)
    .build();
~~~

The client is a long-lived Spring-managed resource. Do not create/close an S3 client per upload request.

### 8.2. Uploading a file with AsyncRequestBody.fromFile

If the request has already been staged to a temporary file, the SDK can read the file on demand and split parts automatically:

~~~java
import java.nio.file.Path;
import java.util.concurrent.CompletableFuture;
import software.amazon.awssdk.core.async.AsyncRequestBody;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectResponse;

CompletableFuture<PutObjectResponse> uploadFile(
        Path stagedFile,
        String bucket,
        String key) {

    return s3.putObject(
        PutObjectRequest.builder()
            .bucket(bucket)
            .key(key)
            .build(),
        AsyncRequestBody.fromFile(stagedFile));
}
~~~

A file can be re-read when the SDK retries, making this suitable when retry/replay is required. File staging trades heap for disk; it requires disk quotas, directory permissions, cleanup on error/cancel, and a policy to purge orphaned files on process restart.

### 8.3. Uploading an InputStream with unknown content length

For streams of unknown length, the S3 async client can accept `AsyncRequestBody.fromInputStream(input, null, executor)`. When multipart is enabled, the SDK handles segmenting the stream:

~~~java
import java.io.InputStream;
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import software.amazon.awssdk.core.async.AsyncRequestBody;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectResponse;

InputStream input = obtainInputStream();

AsyncRequestBody body =
    AsyncRequestBody.fromInputStream(input, null, s3InputReaderExecutor);

CompletableFuture<PutObjectResponse> upload = s3.putObject(
    PutObjectRequest.builder().bucket(bucket).key(key).build(),
    body);

upload.whenComplete((result, error) -> {
    try {
        input.close();
    } catch (IOException closeError) {
        log.warn("Failed to close input stream", closeError);
    }
});
~~~

`obtainInputStream`, `log`, and `s3InputReaderExecutor` belong to the application; the executor should be a shared Spring bean with a bounded thread pool and queue, never a new pool per request. The SDK reads the `InputStream` on the supplied executor; never read a blocking stream on a Netty event loop. Close the `InputStream` when the future completes; Spring shuts down the executor on ApplicationContext shutdown. If the stream comes from a one-shot HTTP request, check cancellation and retry semantics. When reliable retries are required, stage to a file or use a reopenable source.

Example shared executor with 8 workers and a 32-task queue:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class S3InputReaderConfiguration {

    @Bean(destroyMethod = "shutdown")
    ExecutorService s3InputReaderExecutor() {
        return new ThreadPoolExecutor(
            8, 8, 0, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(32),
            new ThreadPoolExecutor.AbortPolicy());
    }
}
~~~

When the queue fills, the executor rejects tasks so the application can return a controlled overload error. Combine this bound with concurrent upload limits and the multipart memory budget.

### 8.4. Bridging a WebFlux request body to InputStream

Spring's bounded bridge avoids buffering the entire request body:

~~~java
import java.io.InputStream;
import java.io.IOException;
import java.util.concurrent.ExecutorService;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import software.amazon.awssdk.core.async.AsyncRequestBody;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectResponse;

Mono<PutObjectResponse> uploadRequestBody(
        String bucket,
        String key,
        Flux<DataBuffer> requestBody,
        ExecutorService reader) {

    return Mono.defer(() -> {
        InputStream input =
            DataBufferUtils.subscriberInputStream(requestBody, 4);

        AsyncRequestBody body =
            AsyncRequestBody.fromInputStream(input, null, reader);

        return Mono.fromFuture(() -> s3.putObject(
                PutObjectRequest.builder()
                    .bucket(bucket)
                    .key(key)
                    .build(),
                body))
            .doFinally(signal -> {
                try {
                    input.close();
                } catch (IOException ignored) {
                    // Already ended/canceled; log if needed.
                }
            });
    });
}
~~~

This is a one-shot direct streaming example. `subscriberInputStream` bounds prefetched `DataBuffer`s and, when closed, cancels upstream and releases queued buffers. Because the body cannot be replayed from the start, do not rely on automatic retries to replay the full HTTP request. If you need retries on network failure, stage the request to a temporary file first and use `AsyncRequestBody.fromFile`.

### 8.5. Downloading from S3 with ResponsePublisher

To stream an object out to an HTTP response without loading it all onto the heap, use `AsyncResponseTransformer.toPublisher()`:

~~~java
import java.nio.ByteBuffer;
import software.amazon.awssdk.core.async.AsyncResponseTransformer;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<ByteBuffer> downloadObject(String bucket, String key) {
    return Mono.fromFuture(() -> s3.getObject(
            GetObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .build(),
            AsyncResponseTransformer.toPublisher()))
        .flatMapMany(publisher -> Flux.from(publisher));
}
~~~

`ResponsePublisher` is an advanced API. The application must subscribe and drive backpressure; the publisher has a default 60-second timeout starting when the body begins streaming. If not subscribed within that window, the subscription may be canceled. The future completes when the response headers and stream publisher are ready, not when the entire body has been read; mid-stream errors must be handled at the stream layer—for example, resuming by byte range if offsets can be determined safely. If you only need to write to a file, use `AsyncResponseTransformer.toFile(path)` to stream straight to disk.

Do not use `AsyncResponseTransformer.toBytes()` for large objects if your goal is bounded memory.

## 9. Azure Blob Storage: Flux<ByteBuffer> and block transfers

### 9.1. Block-based uploads

The Azure Blob async SDK accepts `Flux<ByteBuffer>` in `BlobAsyncClient.upload`. `ParallelTransferOptions` sets block size and parallel request concurrency.

~~~java
import com.azure.storage.blob.BlobAsyncClient;
import com.azure.storage.blob.models.BlockBlobItem;
import com.azure.storage.blob.models.ParallelTransferOptions;
import java.nio.ByteBuffer;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<BlockBlobItem> uploadBlob(
        BlobAsyncClient blob,
        Flux<DataBuffer> requestBody) {

    ParallelTransferOptions transfer = new ParallelTransferOptions()
        .setBlockSizeLong(4L * 1024 * 1024)
        .setMaxConcurrency(2);

    Flux<ByteBuffer> chunks = requestBody
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
        .map(buffer -> {
            byte[] copy = new byte[buffer.readableByteCount()];
            buffer.read(copy);
            DataBufferUtils.release(buffer);
            return ByteBuffer.wrap(copy);
        });

    return blob.upload(chunks, transfer, true);
}
~~~

This example uses 4 MiB blocks and up to 2 parallel requests per transfer. These are illustrative benchmark numbers, not universal optimal defaults. `upload(..., true)` enables overwriting an existing blob; if overwrites should be disallowed, pass `false` or use appropriate request conditions.

The Azure SDK may buffer each sub-upload's data to support retries. Consequently, smaller block sizes reduce how much data must be buffered/retried per request; higher `maxConcurrency` raises throughput at the expense of memory/network pressure. Do not let multiple processes write concurrently to the same blob key without concurrency control/ETag conditions.

### 9.2. Downloading with downloadStream

`downloadStream()` returns `Flux<ByteBuffer>` and is suited for streaming. The older `download()` API is deprecated in certain versions; prefer `downloadStream()`.

~~~java
import java.nio.ByteBuffer;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferFactory;
import org.springframework.http.server.reactive.ServerHttpResponse;
import reactor.core.publisher.Flux;

Flux<DataBuffer> downloadBlob(
        BlobAsyncClient blob,
        ServerHttpResponse response) {

    DataBufferFactory factory = response.bufferFactory();
    return blob.downloadStream().map(chunk -> {
        byte[] copy = new byte[chunk.remaining()];
        chunk.get(copy);
        return factory.wrap(copy);
    });
}
~~~

Each chunk is copied into a buffer allocated by the WebFlux response factory. WebFlux handles writing and releasing response `DataBuffer`s per server contract. If optimizing for zero-copy, verify `ByteBuffer` ownership and lifetime from the Azure SDK before returning it outside the callback.

## 10. Google Cloud Storage: ReadChannel and resumable uploads

### 10.1. Downloading with ReadChannel

Google Cloud Storage Java `Storage.reader(...)` returns a `ReadChannel`, which reads data buffer by buffer. `DataBufferUtils.readByteChannel` turns the channel into a `Flux<DataBuffer>` and closes the channel automatically on stream completion, error, or cancellation.

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferFactory;
import org.springframework.core.io.buffer.DataBufferUtils;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

Flux<DataBuffer> downloadGcsObject(
        Storage storage,
        String bucket,
        String objectName,
        DataBufferFactory factory) {

    return DataBufferUtils.readByteChannel(
            () -> storage.reader(BlobId.of(bucket, objectName)),
            factory,
            64 * 1024)
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

`ReadChannel` is a blocking API; `subscribeOn(boundedElastic())` moves reads off the event loop. Application buffers here are capped at 64 KiB per `DataBuffer`. When the HTTP client cancels the response, the `Flux` cancels and `DataBufferUtils` closes the channel.

### 10.2. Uploading with a resumable InputStream

The Java Storage client supports resumable uploads via `Storage.createFrom(BlobInfo, InputStream, bufferSize)` or `Storage.writer(BlobInfo)`. For a WebFlux request body, use a bounded `InputStream` bridge and run the blocking call on `boundedElastic`:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.io.InputStream;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<Blob> uploadGcsObject(
        Storage storage,
        BlobInfo blobInfo,
        Flux<DataBuffer> requestBody) {

    return Mono.fromCallable(() -> {
        try (InputStream input =
                 DataBufferUtils.subscriberInputStream(requestBody, 4)) {
            return storage.createFrom(blobInfo, input, 8 * 1024 * 1024);
        }
    }).subscribeOn(Schedulers.boundedElastic());
}
~~~

This is a blocking bridge with a 4-buffer input demand cap. `createFrom` uses resumable upload; the example sets an 8 MiB buffer size. The Java client currently defaults to a 15 MiB buffer with a 256 KiB minimum; larger chunks often raise throughput while increasing memory held for retries. Choose a buffer size that is a suitable multiple of 256 KiB and benchmark at realistic upload concurrency.

### 10.3. WriteChannel and close semantics

If the application produces data chunk by chunk, `Storage.writer(BlobInfo)` returns a `WriteChannel`. You can call `setChunkSize` to tune the flush threshold; data is buffered and transmitted once the threshold is reached or when the channel closes. `WriteChannel` is blocking, so use it only on a worker thread/`boundedElastic`, never on the WebFlux event loop.

`WriteChannel.close()` flushes any remaining buffered data and finalizes the object write. Therefore, do not treat `close()` as a safe abort for a producer that failed mid-way: try-with-resources can invoke `close()` when unwinding an exception and finalize partially written data. Clearly distinguish normal EOF from cancellation/error; if you need to resume/cancel an upload session, use the corresponding resumable session mechanism. For one-shot HTTP request bodies, the `Storage.createFrom(..., InputStream, bufferSize)` approach above is simpler because the SDK manages the resumable upload.

### 10.4. Checksum caveats during streaming reads

Cloud Storage streaming/range reads do not always provide verified checksums for arbitrary byte slices before the application processes them. If business requirements demand verifying the whole-object checksum before consuming data, download/read enough of the object to compute and compare the checksum before triggering side effects, or use APIs supporting end-to-end per-chunk checksums. Do not assume an arbitrary range stream has been validated against the full-object checksum.

## 11. Choosing direct streaming vs. staging to a temporary file

| Option | Advantages | Limitations |
| --- | --- | --- |
| Direct stream from HTTP to SDK | No temp files needed; lower latency | One-shot body, complex retry/replay; must coordinate cancellation across both systems |
| Stage to temp file then upload | Replayable, easier retries, known content length | Needs disk quota, cleanup, and an extra I/O pass |
| Buffer everything in RAM | Simple for small payloads | Unsuitable for large files or high concurrency |

Choose direct streaming when upstream/downstream support backpressure, requests have clear deadlines, and one-shot error semantics are acceptable. Choose staging when you need antivirus scanning, full-file checksums before publishing, reliable retries, resumption after process restart, or exact size upfront before uploading.

If using temporary files:

- Generate random filenames in a dedicated directory; never derive paths directly from client-supplied filenames.
- Cap maximum file size and total staging disk usage.
- Delete files on success/error/cancel and run a sweeper job for orphaned files after process crashes.
- Never return temporary file paths to clients.
- Upload via file/path APIs on the storage client so the source is replayable on retry.

## 12. Chunk size and concurrency

Chunk size affects request count, memory, retry cost, and throughput:

| Chunk size | Typical impact |
| --- | --- |
| Small | Lower memory per part, fewer bytes to retry; more requests and higher overhead |
| Large | Fewer requests, potentially higher throughput; higher memory per part and retry cost |

Concurrency controls how many chunks/requests transfer in parallel. Raising concurrency when network bandwidth is underutilized can raise throughput; raising it too far increases memory, sockets, TLS buffers, and cloud throttling.

An estimation formula for SDK transfers:

**M_transfer ≈ uploadConcurrency × partConcurrency × chunkSize**

For example, 6 concurrent uploads, each with 3 parallel parts and 8 MiB chunks:

**M_transfer ≈ 6 × 3 × 8 MiB = 144 MiB**

This is only the estimated chunk buffer portion, excluding WebFlux buffers, SDK metadata, direct memory, and copies. If each request also retains 4 `DataBuffer`s of 64 KiB:

**M_ingress ≈ 6 × 4 × 64 KiB = 1.5 MiB**

Actual total memory exceeds both figures; use them to understand scaling and budget headroom, then measure heap/direct memory/RSS under load tests.

## 13. Backpressure, cancellation, and timeouts

### 13.1. Propagating cancellation

When an HTTP client disconnects, WebFlux can cancel the subscription. The pipeline must propagate cancellation down to the SDK, close `InputStream`s/channels, and stop reading new data. Do not spawn detached background uploads via `subscribe()` without a proper job model and durable state.

### 13.2. Layer-by-layer timeouts

- Request body receive timeout: bounds how long the client may take to send data.
- Upload overall deadline: bounds total upload duration.
- Per-request/chunk timeout: bounds a single block/part transfer.
- Idle timeout: detects stalled streams making no progress.
- Cleanup timeout: bounds how long resource closing may wait.

Do not set timeouts shorter than valid upload times for large files. For long uploads, use upload sessions/resumable protocols and let clients resume from confirmed offsets.

### 13.3. Retry only when byte ranges are safely known

Retrying an entire one-shot stream can fail because the source cannot replay. With multipart/resumable transfers, retrying by known offset and checksum per part/chunk is safer. For direct client streams where the source cannot replay, mid-stream failures typically require the client to resend or the application to stage data so a replayable source exists.

Never retry validation, permission, or permanent quota errors. For throttling/transient network errors, use backoff and jitter, with a capped retry count and overall deadline.

## 14. Checksums, content length, and integrity

### 14.1. Content length must be exact

If an SDK requires content length, supply the exact byte count. Too low a value can produce truncated objects; too high a value can fail uploads or leave connections hanging. When size is unknown, use APIs supporting unknown-length/multipart/resumable uploads rather than guessing.

### 14.2. Per-chunk and full-object checksums

For large files, you can compute checksums incrementally as chunks are read:

~~~java
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import org.springframework.core.io.buffer.DataBuffer;

MessageDigest digest = MessageDigest.getInstance("SHA-256");

void updateDigest(DataBuffer buffer) {
    ByteBuffer view = buffer.asByteBuffer(
        buffer.readPosition(),
        buffer.readableByteCount());
    digest.update(view);
}
~~~

This illustrates updating a digest from a buffer view without retaining the whole file. Once the stream finishes, finalize the digest and compare against a client-supplied checksum or validated metadata. With pooled buffers, read only while the buffer remains valid and still release according to ownership.

`MessageDigest` is not thread-safe; update chunks of the same object sequentially along an ordered pipeline, or use a parallel checksum scheme with a well-defined combination step.

### 14.3. Do not publish completion metadata prematurely

Mark an upload as READY only after the cloud SDK confirms object completion, the multipart/resumable session is committed, and checksum/size checks pass. In staging workflows, you can upload to a temporary object key and then update status/metadata or copy to the final key after validation.

## 15. Security when streaming files

- Never trust client-supplied filenames or `Content-Type` headers.
- Use server-generated object keys or strictly validate prefixes/tenants.
- Bound bytes and upload duration to defend against resource exhaustion.
- Never log access tokens, signed URLs, or sensitive contents.
- Use workload identity/managed identity with least-privilege permissions per bucket/container.
- Validate file signatures (magic bytes) when file type affects business logic.
- When antivirus/DLP scanning is required, stage into quarantine before publishing objects.
- Configure lifecycle rules to clean up incomplete multipart uploads and temporary objects.

## 16. Observing streaming in production

Monitor these metrics:

| Metric | Question to answer |
| --- | --- |
| Active uploads/downloads | How many transfers are running concurrently? |
| Bytes received/sent | What is actual stream throughput? |
| Chunk size and part concurrency | How much buffer is each transfer holding? |
| Backpressure wait time | How long must upstream wait for downstream? |
| Upload duration p50/p95/p99 | Does tail latency scale cleanly with file size? |
| Retry count and failed part count | Are network/service issues forcing frequent retries? |
| Cancellation count | Are client disconnects propagating properly? |
| Heap/direct memory/RSS | Are there leaks or buffer accumulations? |
| Temp disk usage | Is staging filling up or leaving orphaned files? |
| Incomplete multipart/resumable sessions | Are transfers being abandoned mid-way? |

Do not watch heap alone. Netty pooled buffers and SDKs can use direct/native memory; container RSS and direct buffer metrics catch leaks that heap charts miss.

## 17. Testing streaming and memory bounds

1. Upload small files, near-limit files, and files larger than the JVM heap in a controlled test.
2. Compare direct streaming against `byte[]`/aggregation to observe memory differences.
3. Scale upload concurrency across 1, 4, 8, and 16; measure peak memory and throughput.
4. Vary chunk sizes across 1, 4, 8, and 16 MiB and observe retries/latency.
5. Throttle the cloud endpoint or use a mock server to verify backpressure.
6. Disconnect clients mid-upload and verify upstream subscription, `InputStream`, channel, and multipart cleanup.
7. Inject part/chunk errors and verify retries do not send incorrect byte ranges.
8. Send payloads exceeding max bytes and verify HTTP 413 plus buffer cleanup.
9. Send files with mismatched checksums and verify objects are never marked READY.
10. Run multi-hour soak tests to detect direct-memory leaks and uncleaned staging files.

## 18. Common pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| `readAllBytes()` or `collectList()` | Heap scales with file size | Use `Flux`/chunked streams |
| Unbounded `DataBufferUtils.join()` | Large aggregation and `DataBufferLimitException`/OOM | Join small payloads only, enforce max bytes |
| Failing to release pooled `DataBuffer`s | Direct memory leak | Release after consumption and add `doOnDiscard` |
| Releasing a buffer before SDK finishes reading | Corrupted data / use-after-release | Transfer ownership or copy chunk |
| Using `downloadContent()` for large objects | Buffers entire object | Use `downloadStream()` or channels |
| AWS `toBytes()` | Retains full response body in memory | Use `ResponsePublisher` or `toFile` |
| Retrying one-shot S3 `AsyncRequestBody` publisher | Retry cannot replay full body | Use a file/replayable source or upload session |
| Azure block size/concurrency too high | Too many chunks buffered concurrently | Lower block size/concurrency |
| Running GCS `ReadChannel` on event loop | Blocks other requests | Run on `boundedElastic` |
| Not closing `InputStream`/channels | Resource leaks and hung uploads | Use `using`/try-with-resources/`doFinally` |
| Not propagating cancel | Cloud transfers keep running after client leaves | Tie SDK operation to subscription lifecycle |
| No disk quota for staging | Disk fills up | Cap bytes/concurrency and clean up |

## 19. Streaming design workflow

~~~mermaid
flowchart TD
    A[Measure file sizes, throughput, and concurrency] --> B[Choose direct stream vs staging]
    B --> C[Set max request bytes and codec limits]
    C --> D[Choose chunk size and part concurrency]
    D --> E[Enforce DataBuffer ownership/release]
    E --> F[Configure retries, checksums, and cancellation]
    F --> G[Load test with slow/disconnecting clients]
    G --> H{Are memory and disk within budget?}
    H -->|No| I[Lower chunk/concurrency or staging budget]
    I --> G
    H -->|Yes| J[Finalize metrics, alerts, and cleanup policies]
~~~

Pre-production checklist:

1. Can any operation accidentally materialize the whole object?
2. Are total request bytes bounded at the application layer?
3. Is every `DataBuffer` released exactly once across success/error/cancel?
4. Do SDK chunk size and parallelism fit the memory budget?
5. Do blocking SDKs/channels run on an appropriate worker thread?
6. Do retries have a replayable source or safe resume offsets?
7. Does cancellation close streams/channels and halt transfers?
8. Are incomplete multipart/resumable uploads cleaned up?
9. Are checksum/size verified before objects transition to READY?
10. Are metrics in place for heap, direct memory, disk usage, and transfer concurrency?

## 20. Hands-on exercises

**Exercise 1 — WebFlux streaming.** Build an endpoint accepting `Flux<DataBuffer>` and upload a 1 GiB file. Verify heap does not grow linearly with file size.

**Exercise 2 — DataBuffer lifecycle.** Build a pipeline with filtering/cancellation; enable Netty leak detection and prove buffers are released on success, error, and cancel.

**Exercise 3 — AWS S3 multipart.** Enable `multipartEnabled(true)`, upload an unknown-length stream, and measure part concurrency, throughput, and retries.

**Exercise 4 — AWS ResponsePublisher.** Stream an object from S3 to an HTTP response. Have the client read slowly and test backpressure/cancellation; compare against `toBytes()`.

**Exercise 5 — Azure Blob.** Test block sizes of 2, 4, and 8 MiB with `maxConcurrency` 1, 2, and 4. Calculate the memory budget and measure timeouts/retries.

**Exercise 6 — Google Cloud Storage.** Upload using resumable `createFrom` with an 8 MiB buffer; download using `ReadChannel` and `DataBufferUtils`. Verify the channel closes when the client cancels.

**Exercise 7 — Direct stream vs. staging.** Compare one-shot direct uploads against staging to a file then uploading. Interrupt the network mid-transfer and verify retry/replay behavior.

**Exercise 8 — Size guard.** Enforce a 100 MiB cap, send a 101 MiB file, and verify HTTP 413, buffer release, and no finalized object.

**Exercise 9 — Checksums.** Compute SHA-256 chunk by chunk, compare against the expected checksum, and ensure an object with a mismatched checksum never transitions to READY.

**Exercise 10 — Concurrency.** Run 10, 50, and 100 concurrent uploads; monitor heap/direct memory/RSS and select concurrency appropriate for container limits.

## 21. Key takeaways

- Streaming keeps data chunked; `byte[]`, `readAllBytes()`, `collectList()`, and `downloadContent()` can materialize entire objects.
- Backpressure protects memory only when every layer honors demand and has no unbounded queues.
- `DataBuffer`s may be pooled/direct buffers; release with clear ownership and attach `doOnDiscard` for dropped buffers.
- `DataBufferUtils.write` for channels/`OutputStream` does not auto-release buffers; attach `releaseConsumer()` or an equivalent release.
- AWS S3 async multipart supports streams of unknown content length; `AsyncRequestBody.fromPublisher` requires a replayable source if the SDK retries.
- AWS `AsyncResponseTransformer.toPublisher()` enables streaming downloads, but the application must subscribe and manage backpressure.
- Azure Blob `upload(Flux<ByteBuffer>, ...)` and `downloadStream()` support reactive streams; block size and `maxConcurrency` directly drive memory usage.
- Google Cloud Storage `ReadChannel`/`WriteChannel` are channel APIs; the Java client supports resumable uploads with configurable buffer sizes.
- Chunk size × concurrency × concurrent uploads largely determines transfer buffer memory.
- Cancellation, checksums, retry/replay, disk quotas, and cleanup are integral parts of streaming design.

## 22. References

- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Spring Framework — WebFlux Reactive Core and codec memory limits](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Framework — Multipart streaming with PartEvent](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html)
- [Spring Framework — DataBufferUtils API](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [AWS SDK for Java 2.x — Uploading streams to S3](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/best-practices-s3-uploads.html)
- [AWS SDK for Java 2.x — Async client streaming](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/asynchronous.html)
- [AWS SDK for Java 2.x — S3 async multipart transfers](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/s3-async-client-multipart.html)
- [AWS SDK for Java 2.x — AsyncRequestBody API](https://docs.aws.amazon.com/java/api/latest/software/amazon/awssdk/core/async/AsyncRequestBody.html)
- [Azure Storage — Performance tuning for Java uploads and downloads](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blobs-tune-upload-download-java)
- [Azure Storage — BlobAsyncClient Java API](https://learn.microsoft.com/en-us/java/api/com.azure.storage.blob.blobasyncclient)
- [Google Cloud Storage — Java Storage API](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage)
- [Google Cloud Storage — Resumable uploads](https://docs.cloud.google.com/storage/docs/resumable-uploads)
- [Google Cloud Storage — Streaming reads and checksum limitations](https://docs.cloud.google.com/storage/docs/streaming-reads)
