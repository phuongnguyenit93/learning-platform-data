# Transactions in Streaming RPC

## 1. Why does a streaming RPC need its own transaction boundary?

In **SPRING_GRPC**, a streaming RPC allows a single gRPC call to exchange multiple messages over time. Server streaming sends multiple responses; client streaming receives multiple requests; bidirectional streaming both receives and sends messages. A stream can last from a few seconds to several minutes, experiencing backpressure, cancellation, deadlines, and mid-stream network failures.

Database transactions, on the other hand, are designed for a finite unit of work: begin, read/write, and commit or roll back. Keeping a transaction open for the entire lifetime of a stream can hold connections and locks for a long time, increasing transaction timeouts, deadlocks, and connection pool pressure. Annotating the gRPC method that creates a StreamObserver with @Transactional typically ends the transaction as soon as the method returns the observer; subsequent onNext/onCompleted callbacks run later and are not automatically part of the initial transaction.

Therefore, you need to choose the transaction scope based on the stream's semantics. Most systems use **short transactions per message or per batch**, committing before sending the corresponding acknowledgment. If the business logic requires the entire stream to be atomic, use staging and a short finalize step instead of holding a database transaction open while transferring data.

This lesson focuses on:

- Transaction differences between server streaming, client streaming, and bidirectional streaming.
- Why not to keep transactions open across the network or callbacks.
- Per-message, per-batch, and staging/finalize transactions.
- Commit ordering before emitting responses/acks.
- Partial commits, retries, idempotency, checkpoints, and cancellation.
- Spring transaction integration, outbox, and streaming testing.

## 2. The three streaming types and data flow directions

| RPC Type | Data Direction | Business Example | Typically Suitable Transaction |
| --- | --- | --- | --- |
| Server streaming | One request, multiple responses | Exporting transaction history, status monitoring | Short read transaction per snapshot/page |
| Client streaming | Multiple requests, one final response | Uploading data, importing a batch of records | Per-chunk transaction or staging then finalize |
| Bidirectional streaming | Multiple requests and responses in both directions | Event synchronization, device control sessions | Short transaction per command/message |

Choose the transaction scope according to the business unit of work, not the number of callbacks. A single onNext callback is not necessarily an independent business transaction; multiple chunks may together form one upload, while a bidi stream may contain multiple independent commands.

Before implementing, answer three questions:

1. If the stream is interrupted at the Nth message, are previous messages allowed to remain in effect?
2. Can the client retry or resume from a sequence/cursor?
3. When is the server allowed to confirm that a message has been durably persisted?

The answers determine whether you can commit per message, commit per batch, or must use staging.

## 3. Why @Transactional on the stream-creating method does not cover callbacks

Client streaming example in gRPC Java:

```java
@Override
public StreamObserver<UploadChunk> upload(
        StreamObserver<UploadResult> responseObserver) {
    // This method returns the observer immediately.
    return new StreamObserver<>() {
        @Override
        public void onNext(UploadChunk chunk) {
            // Callback is invoked after the upload method has returned.
        }

        @Override
        public void onError(Throwable error) {
        }

        @Override
        public void onCompleted() {
        }
    };
}
```

If @Transactional is placed on upload(), the Spring proxy only wraps the duration of calling upload() to create and return the StreamObserver. The transaction finishes before the gRPC runtime invokes onNext() or onCompleted(). An annotation on the outer method does not automatically propagate to callbacks invoked later.

Similarly, if a server streaming method starts an asynchronous producer and returns, a transaction attached to that method may finish before the producer queries the database or sends responses.

With an imperative Spring transaction manager, the transaction context is typically bound to the current thread. Do not assume a transaction automatically transfers to another executor, callback, or thread.

The safe approach is to call a transactional Spring bean method from each callback or from a specific worker. Calling through the bean proxy opens and closes the transaction within the same execution; the callback only emits the acknowledgment after the transactional call returns successfully.

## 4. Server streaming: reading data in short transactions

A server streaming RPC often exports many records. You should not hold a transaction and database cursor open for the entire duration of sending over the network, because the client may read slowly or stop receiving data.

For moderate datasets, you can read the required snapshot in an application service and close the transaction before sending:

```java
@Service
@RequiredArgsConstructor
public class ExportQueryService {
    private final TransactionRepository repository;

    @Transactional(readOnly = true)
    public List<TransactionRow> loadExport(String accountId) {
        return repository.findExportRows(accountId);
    }
}
```

The adapter receives the fully read list and sends each response:

```java
@Override
public void export(
        ExportRequest request,
        StreamObserver<ExportRow> observer) {
    try {
        List<TransactionRow> rows =
            exportQueryService.loadExport(request.getAccountId());

        for (TransactionRow row : rows) {
            observer.onNext(toProto(row));
        }
        observer.onCompleted();
    } catch (RuntimeException ex) {
        observer.onError(toStatus(ex));
    }
}
```

When loadExport() returns, the read transaction has ended. Network backpressure does not keep a database transaction or connection open.

Do not load millions of records into memory just to close the transaction early. For large datasets, use keyset pagination or a bounded cursor:

1. A transaction reads one page by ascending key.
2. Close the transaction and return the page DTO.
3. The adapter sends the page over the stream.
4. Read the next page using a short transaction.
5. Use a cursor/high-watermark to define the export boundary.

If data changes during the export, pages read in different transactions may not form a consistent snapshot. You can fix a high-watermark, use a version/as-of timestamp, create an export snapshot/staging table, or choose an isolation/snapshot strategy appropriate for the database. Do not assume multi-transaction pagination automatically shares the same snapshot.

## 5. Client streaming: choosing atomicity based on upload semantics

Client streaming typically receives multiple chunks and returns one aggregated result. There are two common semantic models.

**Each chunk is independent:** any chunk that commits successfully persists, and an error on a later chunk does not roll back earlier chunks. Suitable for telemetry, event ingestion, or resumable data processing.

**Entire upload is atomic:** no chunk is published to business state until the entire upload is valid. Do not keep one transaction open while the client transfers the file; use staging to store temporary data, then finalize.

Example callback interface that only coordinates each chunk:

```java
@Override
public StreamObserver<UploadChunk> upload(
        StreamObserver<UploadResult> responseObserver) {

    return new StreamObserver<>() {
        @Override
        public void onNext(UploadChunk chunk) {
            try {
                uploadChunkService.storeChunk(toCommand(chunk));
            } catch (RuntimeException ex) {
                responseObserver.onError(toStatus(ex));
                // Mark stream as failed; ignore subsequent callbacks
                // according to the implementation's lifecycle mechanism.
            }
        }

        @Override
        public void onError(Throwable error) {
            uploadSessionService.markInterruptedIfNeeded();
        }

        @Override
        public void onCompleted() {
            try {
                UploadResult result = uploadFinalizeService.finalizeUpload();
                responseObserver.onNext(result);
                responseObserver.onCompleted();
            } catch (RuntimeException ex) {
                responseObserver.onError(toStatus(ex));
            }
        }
    };
}
```

This is an illustrative structure; a real implementation must guard terminal state so the observer is not called multiple times and must bind every callback to the proper upload session. Do not use a global session ID or shared mutable field on a singleton service.

Each call to uploadChunkService.storeChunk() can open a short transaction. finalizeUpload() runs a separate transaction to validate the data and publish the upload.

## 6. Staging and finalize for atomic uploads

A staging design typically uses an upload ID and sequence number:

- The client starts an upload and receives an uploadId.
- Each chunk carries uploadId, sequence, checksum, and payload.
- The server stores the chunk in a staging table with a unique constraint on (upload_id, sequence).
- When the client completes, the server checks the chunk count, contiguous sequence, checksums, and business rules.
- A finalize transaction creates or updates the main data and marks the upload COMPLETED.
- A worker cleans up expired staging data or abandoned uploads.

Per-chunk transaction:

```java
@Service
@RequiredArgsConstructor
public class UploadChunkService {
    private final UploadChunkRepository chunks;

    @Transactional
    public void storeChunk(ChunkCommand command) {
        chunks.insertIfAbsent(
            command.uploadId(),
            command.sequence(),
            command.checksum(),
            command.payload()
        );
    }
}
```

Finalize transaction:

```java
@Service
@RequiredArgsConstructor
public class UploadFinalizeService {
    private final UploadSessionRepository sessions;
    private final UploadChunkRepository chunks;
    private final InventoryRepository inventory;

    @Transactional
    public UploadResult finalizeUpload(String uploadId) {
        UploadSession session = sessions.lockById(uploadId)
            .orElseThrow(UploadNotFoundException::new);

        if (session.isCompleted()) {
            return session.previousResult();
        }

        validateCompleteSequence(session, chunks);
        applyStagedChanges(session, chunks, inventory);
        session.markCompleted();

        return session.toResult();
    }
}
```

The example assumes the repository locks the session with a row lock. A unique constraint and locking are required so that two concurrent finalize callbacks do not apply the data twice. Promoting staging data to main data and marking COMPLETED must happen in the same transaction.

Staging allows each chunk to be durably persisted without publishing business data yet. If finalize rolls back, the main data remains unchanged and the client can retry finalize using the same uploadId.

## 7. Bidirectional streaming: per-command/message transactions

A bidirectional stream often carries multiple independent commands over a single connection. Each command may need to update the database and return an acknowledgment or event.

One implementation approach is to process each command synchronously through an application service:

```java
@Override
public StreamObserver<DeviceCommand> control(
        StreamObserver<DeviceReply> responseObserver) {

    return new StreamObserver<>() {
        @Override
        public void onNext(DeviceCommand command) {
            try {
                DeviceResult result =
                    deviceCommandService.apply(toCommand(command));

                responseObserver.onNext(toReply(result));
            } catch (RuntimeException ex) {
                responseObserver.onError(toStatus(ex));
            }
        }

        @Override
        public void onError(Throwable error) {
            // Record that the stream was canceled; do not roll back already committed commands.
        }

        @Override
        public void onCompleted() {
            responseObserver.onCompleted();
        }
    };
}
```

DeviceCommandService.apply() is a Spring bean method annotated with @Transactional. When the method returns, the transaction has committed; only then does the adapter send the reply. If the transaction fails, the adapter sends an error and does not send a success acknowledgment for that command.

If callbacks are dispatched concurrently, do not assume multiple onNext() calls can safely update the same aggregate. Serialize commands per stream or aggregate, use sequence/version checks, and apply database locking. Do not allow two callbacks to mutate the same state in an indeterminate order.

A gRPC stream can send multiple responses; each response needs a correlation ID or command sequence so the client can match the acknowledgment with the corresponding command.

## 8. Partial commit and semantics when a stream fails

If each message uses its own transaction, the stream is not an atomic transaction. For example, suppose 10 commands were received:

- Commands 1–6 commit successfully and have been acknowledged.
- Command 7 hits a constraint error and rolls back.
- The stream terminates with an error status.
- Commands 1–6 remain committed; they cannot be rolled back simply by closing the stream.

This is **partial commit** semantics. The API must clearly document this so clients do not assume an error at the end of a stream means no data was saved.

With atomic uploads via staging, chunks can be saved in staging while the main data is only updated on finalize. If finalize fails, the client can fix or resend without having to reverse individual published changes.

Choose the appropriate semantics:

| Requirement | Model |
| --- | --- |
| Each event is independent and can continue after errors | Per-message transaction |
| Multiple messages form a business batch | Short per-batch transaction or staging/finalize |
| Incomplete data must never be published | Staging, validate, then finalize |
| Continuous control flow | Per-command and sequence transaction |

Do not claim an "atomic stream" if you only commit each callback individually.

## 9. Retries, idempotency, and resume

gRPC does not automatically guarantee exactly-once processing. A client may not know whether the server committed if the connection drops right after commit but before acknowledgment.

For streams with side effects:

- Each command/chunk needs an idempotency key or stable identifier.
- Use a unique constraint for the operation ID or (stream/session ID, sequence).
- Save the processing result in the same transaction as the business change.
- If the same key and same payload are received again, return the previous result.
- If the same key arrives with a different payload, reject as a conflict.
- Support resuming from a committed sequence/cursor instead of blindly resending the entire stream.

For example, a command receipt table has a unique key on client ID and command ID. When the command is processed, update domain state and save the receipt in the same transaction. Retries read the existing receipt to return the acknowledgment without running the side effect again.

For chunk uploads, a checksum helps detect when a client resends the same sequence with different content. A unique constraint also protects when two retry requests arrive concurrently.

## 10. Transactions and external side effects

Do not call an email provider, message broker, or RPC to another service inside a database transaction and assume everything can roll back together.

If a message has committed in the database and needs to emit an event, write an outbox record in the same transaction:

1. Process the command and update domain state.
2. Write the outbox event with an event ID/sequence.
3. Commit the transaction.
4. A worker publishes the event and marks it as sent.
5. Consumers process idempotently because publishing may repeat.

For long streams, the outbox creates a clean boundary between committing each command and emitting external side effects. If a multi-service workflow requires compensation, use saga/compensation and persist progress state instead of holding a transaction across RPCs.

## 11. Cancellation, deadlines, and thread lifecycle

A client can cancel a stream or a deadline can expire at any moment. That does not automatically reverse transactions that have already committed.

When cancellation occurs:

- Stop accepting or processing new messages if the lifecycle permits.
- Do not emit further success acknowledgments for uncommitted work.
- Allow in-flight transactions to finish or roll back according to database/runtime mechanisms.
- Mark the upload/session as interrupted if resume is needed.
- Clean up staging via TTL/worker; do not rely solely on the onError callback because the process could terminate abruptly.
- Maintain idempotency so clients can retry safely when the outcome is uncertain.

Set appropriate deadlines and query/transaction timeouts. Do not keep a transaction open while waiting for the client to send the next chunk or waiting on network backpressure.

With Spring imperative transactions, the context is typically bound to the thread. If a callback offloads work to an executor, invoke the transactional bean inside the worker thread to open the transaction there. If using a reactive stack with R2DBC, the transaction context is propagated in the Reactor Context; keep the work inside the reactive pipeline instead of mixing it arbitrarily with imperative StreamObserver callbacks.

## 12. Error mapping and stream state

A stream has only one terminal outcome: completion or error. After calling onError(), do not subsequently call onNext() or onCompleted(). After calling onCompleted(), do not emit another terminal signal.

Some statuses that can be used:

| Situation | gRPC status |
| --- | --- |
| Malformed chunk/request | INVALID_ARGUMENT |
| Upload/session does not exist | NOT_FOUND |
| Invalid sequence or session state | FAILED_PRECONDITION |
| Duplicate sequence with different payload | ALREADY_EXISTS or ABORTED per contract |
| Optimistic locking conflict | ABORTED |
| Deadline exceeded | DEADLINE_EXCEEDED |
| Unexpected internal/database error | INTERNAL |

Do not include SQL, stack traces, or sensitive data in status descriptions. Log internally with controlled stream ID, command ID, sequence, and correlation ID.

With partial commits, the final stream status does not fully describe the commands committed earlier. The API should provide receipts/checkpoints or a status query so the client knows how far processing progressed.

## 13. Testing transactions in streaming RPC

Test through a real gRPC server and a database with production-like semantics. H2 may not accurately reproduce the locking, isolation, constraints, or deferred commit behavior of the production database.

| Test | What to verify |
| --- | --- |
| Server streaming | Read transaction finishes before the response stream is sent |
| Client streaming chunk commit | Committed chunks remain persisted when a later chunk fails |
| Upload staging | Temporary chunks do not appear in main data before finalize |
| Finalize success | All data is published and the session is COMPLETED in the same transaction |
| Finalize rollback | No partial business changes occur |
| Duplicate chunk/command | Retrying with the same ID does not create duplicate side effects |
| Sequence conflict | Same ID with a different payload is rejected |
| Bidi concurrency | Commands on the same aggregate are serialized or properly locked |
| Cancellation | Incomplete work is not committed; session can resume/expire |
| Observer lifecycle | No messages emitted after a terminal signal |
| Outbox | Domain update and outbox record commit/roll back together |

For client streaming, test sending several valid chunks and then intentionally failing the next chunk. Verify the result matches the documented semantics: per-chunk mode preserves earlier chunks; staging mode does not publish main data before finalize.

For server streaming, test a slow-reading client and mid-stream cancellation; observe connections/transactions to verify the database transaction is not held open for the duration of the network stream.

## 14. Transaction design checklist for streaming RPC

- Identified whether the RPC is server, client, or bidirectional streaming.
- Defined atomicity per message, per batch, or for the entire upload.
- Database transactions are not kept open across the network, backpressure, or the entire stream lifecycle.
- Not relying on @Transactional on the method that merely creates and returns the StreamObserver.
- Each callback invokes the transactional application service through a Spring bean proxy.
- Acknowledgments are emitted only after the corresponding transaction commits.
- Server streaming uses a page/snapshot strategy suited to consistency and memory.
- Client streaming uses staging/finalize if atomic upload is required.
- Bidi streams handle ordering, sequences, and concurrency explicitly.
- Partial commits are documented and have checkpoints/resume.
- Retries have idempotency keys and database uniqueness.
- External side effects use outbox or saga/compensation.
- Deadlines/cancellation are not confused with rolling back committed transactions.
- Integration tests cover transactions, observer lifecycle, retries, and cancellation.

In **SPRING_GRPC**, a streaming RPC should not be treated as a single database transaction spanning from the first message to the last. Choose short transactions per command/chunk or staging/finalize for atomic uploads, and only send acknowledgments after commit. Explicitly designing partial commits, idempotency, checkpoints, and cancellation allows streams to retry or resume without creating duplicate data or inconsistent business state.
