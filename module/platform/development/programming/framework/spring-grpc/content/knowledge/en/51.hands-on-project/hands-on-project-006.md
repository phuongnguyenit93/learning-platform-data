# Building Client Streaming for Batch Uploads

In this project, you will build a batch inventory upload workflow using Spring gRPC. The client reads a CSV file, streams multiple records over a single client-streaming RPC, and receives a single summary result once the server finishes processing the entire batch.

This is a natural fit for client streaming: the record count can be large, the client wants to stream records sequentially rather than issuing one RPC per row, and the server needs to validate and record incoming data while the stream is open. The project also addresses common operational concerns including authentication metadata, deadlines, status codes, size limits, cancellation, backpressure, idempotency, and integration testing.

## 1. Expected Outcomes

Build two components:

- **Batch upload server:** a Spring gRPC service that receives a stream of inventory records, authenticates the caller, validates ordering and payloads, writes data into a staging area, and publishes the batch when the client completes the stream validly.
- **Batch upload client:** a Java program that reads a CSV line by line, opens a single RPC, sends the start frame followed by records, and awaits the final result from the server.

Example input data:

```csv
sku,warehouse_code,quantity
SKU-001,HCM-01,30
SKU-002,HCM-01,12
SKU-003,DN-02,7
```

Upon completion, the server returns the `batch_id`, the count of accepted records, and the commit state. If any record is invalid, the stream is cancelled, the deadline expires, or the server cannot commit, the batch must not be partially published. The client can look up batch status via a separate API if needed to track progress after a disconnection.

### First Version Scope

- One client-streaming RPC: multiple `UploadFrame` messages in, one `UploadResult` out.
- Each stream begins with exactly one `BatchStart` frame as its first message.
- Subsequent frames contain records with sequences incrementing consecutively starting from 1.
- A batch is either committed in full or aborted in full.
- Enforce limits on record count, total bytes, and upload duration.
- The client reuses the same `batch_id` when retrying a batch; the server ensures idempotent handling scoped by tenant and batch ID.

The first version does not support resuming from an arbitrary sequence after a dropped connection. When an upload is interrupted, the client resends the batch with the same `batch_id`; the server must recognize an already-committed batch or allow recreating an incomplete batch according to documented policy.

## 2. Designing the Protocol Buffers Contract

Create `src/main/proto/batch_upload.proto`:

```protobuf
syntax = "proto3";

package inventory.batch.v1;

option java_package = "com.example.inventory.batch.v1";
option java_multiple_files = true;

service BatchUploadService {
  rpc UploadBatch(stream UploadFrame) returns (UploadResult);
}

message UploadFrame {
  oneof frame {
    BatchStart start = 1;
    InventoryRecord record = 2;
  }
}

message BatchStart {
  string batch_id = 1;
  string source = 2;
  uint64 expected_records = 3;
}

message InventoryRecord {
  uint64 sequence = 1;
  string sku = 2;
  string warehouse_code = 3;
  int32 quantity = 4;
}

message UploadResult {
  string batch_id = 1;
  uint64 accepted_records = 2;
  UploadState state = 3;
}

enum UploadState {
  UPLOAD_STATE_UNSPECIFIED = 0;
  UPLOAD_STATE_COMMITTED = 1;
}
```

`oneof` lets the server distinguish the start frame from data frames and detect empty frames. `expected_records` lets the server verify the client sent all expected records before committing. `sequence` detects missing, duplicate, or out-of-order records.

Authentication credentials are not placed inside every record. The client sends an access token in gRPC metadata; the server validates the token and extracts the tenant from the verified principal. `batch_id` is an idempotency key scoped within the tenant, not an authentication credential.

After updating `.proto`, run the code-generation task configured by your project's Maven or Gradle protobuf plugin. `protoc`, the `grpc-java` plugin, and the runtime libraries must be compatible versions. Never manually edit generated classes.

## 3. Component Structure

You can organize the source code using the following structure:

```text
src/main/
  proto/
    batch_upload.proto
  java/com/example/inventory/
    grpc/
      BatchUploadGrpcService.java
      BatchUploadObserver.java
      AuthServerInterceptor.java
      GrpcTenantContext.java
    application/
      BatchUploadProcessor.java
      UploadSession.java
      UploadLimitExceededException.java
    infrastructure/
      StagingBatchUploadProcessor.java
  resources/
    application.yml
src/test/
  java/com/example/inventory/
    grpc/
      BatchUploadContractTest.java
      BatchUploadSpringIntegrationTest.java
```

Your specific Spring gRPC starter determines how services, interceptors, ports, and TLS are registered. Use the auto-configuration or bean registration mechanism of your chosen starter; never create a second server manually when the starter manages the server lifecycle.

## 4. Building the Batch Processing Layer

Do not let the gRPC service manage SQL, transactions, and storage rules directly. Create an abstraction so the service only coordinates frames:

```java
public interface BatchUploadProcessor {

    UploadSession begin(String tenantId, BatchStart start);

    void append(UploadSession session, InventoryRecord record);

    UploadResult commit(UploadSession session);

    void abort(UploadSession session);
}
```

`UploadSession` represents an in-progress batch receiving data. The processor is responsible for checking limits, persisting staging records, and maintaining consistency. In a real implementation, the session should hold only an internal ID and required metadata rather than buffering the entire file in RAM.

### 4.1. Using Staging for Atomicity

A suitable implementation for large batches persists incoming rows into staging tables:

| Table | Suggested Columns | Purpose |
|---|---|---|
| `upload_batch` | `tenant_id`, `batch_id`, `source`, `expected_records`, `received_records`, `status`, `created_at`, `completed_at` | Tracks batch status and idempotency. |
| `upload_batch_record` | `tenant_id`, `batch_id`, `sequence`, `sku`, `warehouse_code`, `quantity` | Temporarily stores each record in order. |
| `inventory` | `tenant_id`, `warehouse_code`, `sku`, `quantity` | Published inventory data visible to business queries. |

Add unique constraints on `(tenant_id, batch_id)` and `(tenant_id, batch_id, sequence)`. On `begin`, the server creates or looks up the batch. On `append`, the server validates and writes the record to staging. On `commit`, a short transaction confirms the full row count, applies the data to the business table, and transitions the batch status to `COMMITTED`.

Business queries read only committed data. Thus, if the client disconnects midway, staged records never appear as partial inventory updates. A cleanup job can purge expired `RECEIVING` batches according to retention policy.

Do not hold a database transaction open for the entire duration while the client sends a long stream. Placing `@Transactional` on the gRPC method typically does not span the `onNext` and `onCompleted` callbacks the way newcomers assume: the method returns immediately after constructing the `StreamObserver`, while data arrives later. Use explicit transactions inside staging operations and especially the final commit operation.

### 4.2. Handling Idempotency

The client generates a stable `batch_id` before its first attempt and reuses that ID on retries. The processor must clearly handle each case:

- Batch already `COMMITTED` for the same tenant and batch ID: return the stored result if the request matches the same content.
- Batch currently `RECEIVING`: reject a concurrent upload with `ALREADY_EXISTS` or a controlled lease mechanism.
- Incomplete batch whose lease has expired: mark failed/expired and allow re-initialization per policy.
- Batch ID exists with different content: reject without overwriting the previous batch.

To verify identical content, store a checksum of normalized content or a client-supplied manifest verified by the server. Do not rely solely on filename, since two files with different contents can share the same name.

In the server state machine, the replay case can be represented by an `UploadSession` in verification-only mode: `begin` recognizes the committed batch, `append` computes checksums/compares replayed content without writing more inventory, and `commit` returns the stored result if contents match. If you do not implement this mode, provide a status lookup RPC so clients check status before re-uploading; never claim retries are safe solely because `batch_id` is unique.

## 5. Building the Server to Receive Client Streams

The server extends the generated `ImplBase` and returns a `StreamObserver` to receive frames. The example below focuses on the state machine and key status codes; `UploadSession`, logging, and limit exceptions are application types.

```java
@GrpcService
public final class BatchUploadGrpcService
        extends BatchUploadServiceGrpc.BatchUploadServiceImplBase {

    private final BatchUploadProcessor processor;

    public BatchUploadGrpcService(BatchUploadProcessor processor) {
        this.processor = processor;
    }

    @Override
    public StreamObserver<UploadFrame> uploadBatch(
            StreamObserver<UploadResult> responseObserver) {

        @SuppressWarnings("unchecked")
        ServerCallStreamObserver<UploadResult> serverCall =
                (ServerCallStreamObserver<UploadResult>) responseObserver;

        String tenantId = GrpcTenantContext.TENANT_ID.get();
        if (tenantId == null) {
            responseObserver.onError(Status.UNAUTHENTICATED
                    .withDescription("Missing authenticated tenant")
                    .asRuntimeException());
            return new StreamObserver<>() {
                @Override public void onNext(UploadFrame value) { }
                @Override public void onError(Throwable error) { }
                @Override public void onCompleted() { }
            };
        }

        return new BatchUploadObserver(serverCall, processor, tenantId);
    }
}
```

The observer coordinates incoming frames and bounds how many messages are requested from the transport:

```java
final class BatchUploadObserver implements StreamObserver<UploadFrame> {

    private final ServerCallStreamObserver<UploadResult> response;
    private final BatchUploadProcessor processor;
    private final String tenantId;

    private UploadSession session;
    private long expectedRecords;
    private long nextSequence = 1;
    private boolean started;
    private boolean terminal;

    BatchUploadObserver(
            ServerCallStreamObserver<UploadResult> response,
            BatchUploadProcessor processor,
            String tenantId) {
        this.response = response;
        this.processor = processor;
        this.tenantId = tenantId;

        response.disableAutoRequest();
        response.setOnCancelHandler(this::cancel);
        response.request(1);
    }

    @Override
    public synchronized void onNext(UploadFrame frame) {
        if (terminal || response.isCancelled()) {
            cancel();
            return;
        }

        try {
            switch (frame.getFrameCase()) {
                case START -> acceptStart(frame.getStart());
                case RECORD -> acceptRecord(frame.getRecord());
                case FRAME_NOT_SET -> throw new IllegalArgumentException(
                        "Upload frame must contain start or record");
            }

            if (!terminal) {
                response.request(1);
            }
        } catch (UploadLimitExceededException ex) {
            fail(Status.RESOURCE_EXHAUSTED.withDescription(ex.getMessage()));
        } catch (IllegalArgumentException ex) {
            fail(Status.INVALID_ARGUMENT.withDescription(ex.getMessage()));
        } catch (BatchAlreadyExistsException ex) {
            fail(Status.ALREADY_EXISTS.withDescription(ex.getMessage()));
        } catch (Exception ex) {
            fail(Status.INTERNAL.withDescription("Batch upload failed"));
        }
    }

    private void acceptStart(BatchStart start) {
        if (started) {
            throw new IllegalArgumentException("BatchStart must be the first and only start frame");
        }
        if (start.getBatchId().isBlank() || start.getExpectedRecords() == 0) {
            throw new IllegalArgumentException("batch_id and expected_records are required");
        }

        expectedRecords = start.getExpectedRecords();
        session = processor.begin(tenantId, start);
        started = true;
    }

    private void acceptRecord(InventoryRecord record) {
        if (!started) {
            throw new IllegalArgumentException("BatchStart must precede records");
        }
        if (record.getSequence() != nextSequence) {
            throw new IllegalArgumentException("Record sequence is missing, duplicated or out of order");
        }
        if (record.getSku().isBlank() || record.getWarehouseCode().isBlank()
                || record.getQuantity() < 0) {
            throw new IllegalArgumentException("Invalid inventory record");
        }

        processor.append(session, record);
        nextSequence++;
    }

    @Override
    public synchronized void onCompleted() {
        if (terminal) {
            return;
        }
        if (!started || nextSequence - 1 != expectedRecords) {
            fail(Status.INVALID_ARGUMENT.withDescription("Uploaded record count does not match expected_records"));
            return;
        }

        try {
            UploadResult result = processor.commit(session);
            session = null;
            terminal = true;
            response.onNext(result);
            response.onCompleted();
        } catch (Exception ex) {
            fail(Status.INTERNAL.withDescription("Could not commit batch"));
        }
    }

    @Override
    public synchronized void onError(Throwable error) {
        abort();
        terminal = true;
    }

    private synchronized void cancel() {
        if (terminal) {
            return;
        }
        terminal = true;
        abort();
    }

    private void fail(Status status) {
        if (terminal) {
            return;
        }
        terminal = true;
        abort();
        response.onError(status.asRuntimeException());
    }

    private void abort() {
        if (session != null) {
            try {
                processor.abort(session);
            } catch (Exception cleanupError) {
                // Log cleanupError; preserve the original RPC status/cause.
            } finally {
                session = null;
            }
        }
    }
}
```

This illustrative snippet should be completed with your application's exception types and logging. In production, `abort()` must be idempotent when called repeatedly and must never mask the original error; catch and log cleanup errors separately. Also enforce limits on `expected_records`, total bytes, individual field lengths, and upload duration in the processor or request validation layer. `response.disableAutoRequest()` together with `request(1)` implements inbound flow control: the server requests the next frame only after processing the current one.

Never call `response.onNext()` after `onError()` or after the stream has terminated. Cancellation must stop processing as early as possible and abort staging. If the processor offloads work to another executor, propagate cancellation explicitly and do not assume `Context.current()` automatically carries over across arbitrary async tasks.

## 6. Authenticating Metadata and Tenant

The client sends an access token in the `authorization` metadata header. A server interceptor validates the token, extracts the tenant from the verified principal, and attaches the tenant to the gRPC `Context`. Never trust a client-supplied `tenant-id` header because a caller can tamper with metadata to access another tenant's data.

Example context and metadata key declarations:

```java
public final class GrpcTenantContext {
    public static final Context.Key<String> TENANT_ID = Context.key("tenant-id");

    private GrpcTenantContext() {
    }
}

public final class AuthServerInterceptor implements ServerInterceptor {

    public static final Metadata.Key<String> AUTHORIZATION =
            Metadata.Key.of("authorization", Metadata.ASCII_STRING_MARSHALLER);

    private final TokenVerifier tokenVerifier;

    public AuthServerInterceptor(TokenVerifier tokenVerifier) {
        this.tokenVerifier = tokenVerifier;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {
        try {
            AuthenticatedPrincipal principal =
                    tokenVerifier.verify(headers.get(AUTHORIZATION));
            Context context = Context.current().withValue(
                    GrpcTenantContext.TENANT_ID, principal.tenantId());
            return Contexts.interceptCall(context, call, headers, next);
        } catch (AuthenticationException ex) {
            call.close(Status.UNAUTHENTICATED
                    .withDescription("Invalid credentials"), new Metadata());
            return new ServerCall.Listener<>() { };
        }
    }
}
```

`TokenVerifier` and `AuthenticatedPrincipal` are application components. Register the interceptor using your Spring gRPC starter's mechanism. Never log access tokens. If you need a correlation ID, use a dedicated metadata key, validate its length, and sanitize the value before putting it into logs or traces.

In deployed environments, enable TLS and verify certificates on both sides per your chosen security model. Only use plaintext in isolated local environments. TLS secures the transport; the interceptor must still authenticate and authorize the caller.

## 7. Building the Client to Read CSV and Stream Records

The client uses the generated asynchronous stub because a client-streaming RPC receives its result asynchronously. The example below shows the basic sending flow; `parseCsvRecord` should use a proper CSV parser supporting quoting and escaping rather than splitting strings manually on commas.

`expectedRecords` must be known before sending the first frame—for instance, by reading a manifest generated alongside the file or performing a CSV counting pass with the parser. If reading the file in two passes, verify the file was not modified between counting and uploading; you can store file size, modification time, or a checksum to detect changes.

```java
// Place this snippet inside a method declared with throws Exception.
ManagedChannel channel = ManagedChannelBuilder
        .forAddress(host, port)
        .useTransportSecurity()
        .build();

CountDownLatch completed = new CountDownLatch(1);
AtomicReference<UploadResult> resultRef = new AtomicReference<>();
AtomicReference<Throwable> errorRef = new AtomicReference<>();

try {
    BatchUploadServiceGrpc.BatchUploadServiceStub stub =
            BatchUploadServiceGrpc.newStub(channel);

    Metadata headers = new Metadata();
    Metadata.Key<String> authorization = Metadata.Key.of(
            "authorization", Metadata.ASCII_STRING_MARSHALLER);
    headers.put(authorization, "Bearer " + accessToken);
    stub = stub.withInterceptors(
            MetadataUtils.newAttachHeadersInterceptor(headers));

    StreamObserver<UploadResult> responseObserver = new StreamObserver<>() {
        @Override
        public void onNext(UploadResult result) {
            resultRef.set(result);
        }

        @Override
        public void onError(Throwable error) {
            errorRef.set(error);
            completed.countDown();
        }

        @Override
        public void onCompleted() {
            completed.countDown();
        }
    };

    StreamObserver<UploadFrame> requestObserver = stub
            .withDeadlineAfter(20, TimeUnit.MINUTES)
            .uploadBatch(responseObserver);

    requestObserver.onNext(UploadFrame.newBuilder()
            .setStart(BatchStart.newBuilder()
                    .setBatchId(batchId)
                    .setSource("inventory-csv")
                    .setExpectedRecords(expectedRecords))
            .build());

    long sequence = 1;
    try (BufferedReader reader = Files.newBufferedReader(csvPath)) {
        String line = reader.readLine(); // Skip header.
        while ((line = reader.readLine()) != null) {
            CsvInventoryRow row = parseCsvRecord(line);
            InventoryRecord record = InventoryRecord.newBuilder()
                    .setSequence(sequence++)
                    .setSku(row.sku())
                    .setWarehouseCode(row.warehouseCode())
                    .setQuantity(row.quantity())
                    .build();

            requestObserver.onNext(UploadFrame.newBuilder()
                    .setRecord(record)
                    .build());
        }
    } catch (Exception ex) {
        requestObserver.onError(ex);
        throw ex;
    }

    requestObserver.onCompleted();

    if (!completed.await(21, TimeUnit.MINUTES)) {
        throw new TimeoutException("Timed out waiting for batch result");
    }
    if (errorRef.get() != null) {
        throw new RuntimeException("Batch upload failed", errorRef.get());
    }
    UploadResult result = Objects.requireNonNull(resultRef.get());
    if (result.getState() != UploadState.UPLOAD_STATE_COMMITTED) {
        throw new IllegalStateException("Server did not commit the batch");
    }
} finally {
    channel.shutdown();
    if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
        channel.shutdownNow();
    }
}
```

This is a basic streaming example for moderate file sizes. For large files, never read the whole file into a `List` before sending. Additionally, a naive `onNext` loop can push frames into buffers faster than the transport can send them. Upgrade the client to use `ClientResponseObserver` and `ClientCallStreamObserver.isReady()`/`setOnReadyHandler()`: read and send more records only when the channel is ready, using a single producer and a bounded buffer. The producer pattern looks like: register `setOnReadyHandler(this::pump)`, inside `pump()` send the next record while `call.isReady()` remains true, and call `call.onCompleted()` only after the iterator is exhausted. If the user cancels the upload or the deadline expires, cancel the call and retain the `batch_id` for lookup or retry per policy.

Never blindly retry a client-streaming RPC. The server may have committed the batch while the response was lost on the wire. Use the idempotent `batch_id` and a status lookup API to determine the outcome before resending. Set deadlines generous enough for expected batch sizes and network speeds, while the server still enforces a maximum duration to prevent streams from tying up resources indefinitely.

## 8. Status and Error Conventions

Choose stable statuses so the client can handle failures consistently:

| Status | When Used | Suggested Client Behavior |
|---|---|---|
| `INVALID_ARGUMENT` | Missing start frame, bad sequence, invalid record, or mismatched count. | Fix the input file; do not retry as-is. |
| `UNAUTHENTICATED` | Token missing, expired, or invalid. | Refresh credentials, then decide whether to resend with the same batch ID. |
| `PERMISSION_DENIED` | Caller is not allowed to upload for that tenant or data source. | Stop and request appropriate permissions. |
| `RESOURCE_EXHAUSTED` | Exceeded record count, byte size, quota, or concurrent upload limit. | Split into smaller batches or wait per quota policy. |
| `ALREADY_EXISTS` | Batch ID is currently in progress or conflicts with another batch. | Look up batch status; do not automatically generate a new ID. |
| `DEADLINE_EXCEEDED` | Upload did not finish within the deadline. | Look up batch status before retrying, as the server may have committed. |
| `CANCELLED` | Client cancelled or connection dropped. | Check whether the batch committed before resending. |
| `UNAVAILABLE` | Transient infrastructure failure or server unavailable. | Retry with backoff after checking idempotency and batch status. |
| `INTERNAL` | Unexpected server error. | Record the correlation ID; do not retry infinitely. |

Never return stack traces or database details in status descriptions. Log the full exception on the server with a correlation ID; return only enough information to the client for handling and operational support.

## 9. Contract and Integration Testing

### 9.1. Testing with an In-Process Server

Use the generated stub and gRPC in-process transport to verify the contract quickly without opening sockets. You can mock downstream repositories or processors, while keeping the real service implementation. Test at least:

- `BatchStart` is the first frame and appears only once.
- Records have contiguous sequences starting from 1.
- `expected_records` matches the actual count of received records.
- Final result contains the expected `batch_id`, count, and `COMMITTED` state.
- Invalid frames return `INVALID_ARGUMENT` and invoke abort.
- Exceeding limits returns `RESOURCE_EXHAUSTED`.
- Client cancellation triggers abort and does not publish the batch.

### 9.2. Spring Integration Testing

Boot the Spring application context and gRPC server on a test port. Use a generated client to connect to the real server and verify that the service bean is registered, interceptors execute, metadata is read, tenant is extracted from the principal, and lifecycle configuration works. If your starter supports dynamic/random ports, prefer that over hardcoded ports that can collide.

### 9.3. Transaction and Idempotency Testing

Verify that staged records do not appear in the inventory table before commit. When the last record is invalid or commit fails, zero partial data is published. Resending the same batch ID after a successful commit must return the stored result without doubling inventory. Concurrent uploads with the same tenant and batch ID must have deterministic outcomes.

### 9.4. Limit and Transport Testing

- Upload right at the limit and above the maximum record count.
- Send records with oversized fields or total bytes exceeding quota.
- Let an upload run until the deadline expires.
- Disconnect the client mid-stream.
- Run multiple concurrent upload clients to verify quotas and backpressure.
- Test invalid tokens, valid tokens for the wrong tenant, and untrusted TLS certificates.
- Test CSV files with commas inside quoted fields, blank lines, invalid encoding, and malformed numeric values.

Do not check only the status code. Verify that the session is aborted, staging data is cleaned up per policy, and business tables have no partial updates.

## 10. Observability and Operations

Record metrics by method and status, for example:

- `grpc_server_handled_total` by method and status.
- Active upload count.
- Succeeded/failed batch counts and accepted record counts.
- Upload duration, commit duration, and batch size.
- Cancellation counts, deadline expirations, and quota rejections.
- Expired staging batches awaiting cleanup.

Do not use `batch_id`, access tokens, SKUs, or tenant IDs as high-cardinality metric labels. Batch IDs can be included in structured logs or traces when data policies allow. Use correlation IDs to tie client and server logs together.

Set alerts when rates of `RESOURCE_EXHAUSTED`, `DEADLINE_EXCEEDED`, `UNAVAILABLE`, or expired staging batches spike unexpectedly. Track commit duration separately from data transfer duration to pinpoint whether bottlenecks lie in the network, parsing/validation, or the database.

## 11. Project Implementation Sequence

1. Create `.proto`, configure code generation, and verify generated services/stubs are placed in the right package.
2. Implement `BatchUploadProcessor` with staging, commit, abort, and idempotency mechanisms.
3. Write the server implementation using a frame-handling state machine; validate start, sequence, counts, and limits.
4. Register the auth interceptor; validate metadata and place the verified tenant into the gRPC context.
5. Write the client to read CSV line by line, generate a batch ID, send the start frame, stream records, and await the result.
6. Add deadlines, cancellation handling, bidirectional flow control, and resource limits.
7. Write contract tests, Spring integration tests, transaction tests, and transport/TLS tests.
8. Add metrics, structured logging, cleanup jobs, and operational runbooks.

## 12. Acceptance Criteria

- [ ] Client sends multiple records over a single client-streaming RPC and receives one final response.
- [ ] Server rejects out-of-order frames, invalid sequences, and mismatched record counts.
- [ ] Batch is published only after the entire stream is validated and the commit transaction succeeds.
- [ ] Client cancellation, validation errors, and commit failures all safely abort staging.
- [ ] Metadata is authenticated; tenant is derived from the verified principal.
- [ ] Deadlines, record/byte/time limits, and two-way backpressure are enforced.
- [ ] Retrying with the same batch ID never duplicates inventory data.
- [ ] Client handles statuses consistently and never blindly retries unsafe errors.
- [ ] Integration tests run against a real Spring gRPC server; TLS is verified when secure transport is enabled.
- [ ] Metrics and logs track batch counts, record counts, processing latency, and failure causes.

When finished, you have a controlled batch upload pipeline from CSV file to business data. Client streaming eliminates the overhead of one RPC per record; staging, idempotency, deadlines, flow control, and integration testing keep the upload pipeline safe even with large datasets, dropped connections, or server failures.
