# Do Not Hold Transactions Too Long While Streaming

## 1. Why are long transactions dangerous in streaming RPCs?

In **SPRING_GRPC**, a streaming RPC can exchange messages over many seconds or minutes. Clients can send chunks slowly, the server can experience backpressure when a client reads responses slowly, and a stream can be canceled or hit a deadline at any time.

Database transactions are designed to protect a finite unit of read/write work. Opening a transaction when the first message arrives and holding it until the stream finishes forces the system to hold a connection and potentially locks for the entire duration of data transfer. A slow stream can occupy the connection pool, forcing other requests to wait; long-held locks increase lock contention, deadlocks, and transaction timeouts. Long-lived snapshots/MVCC can also retain old row versions, increasing data cleanup pressure on some databases.

The design principle is **never tie transaction lifetime to network stream lifetime**. Open transactions close to when database operations actually execute, commit early once the unit of work is complete, and only then continue sending/receiving data over the network.

This lesson focuses on how to bound transaction duration in server streaming, client streaming, and bidirectional streaming; how to use pages, bounded batches, and staging; and practices for controlling connections, locks, timeouts, cancellation, and retries.

## 2. Transaction scope must be shorter than the stream

A stream does not necessarily correspond to a single transaction. Choose commit boundaries according to the business unit of work:

| Model | When does the transaction open? | When does the transaction end? | Best suited for |
| --- | --- | --- | --- |
| Per-message | When processing one command/chunk | Immediately after the command/chunk commits | Independent events or commands |
| Per-batch | When a bounded batch is ready | After finishing writing the batch | Imports/ingestion requiring throughput |
| Staging/finalize | Short transaction to save each chunk to staging; another transaction to finalize | After each chunk or after the finalize step | Uploads requiring atomic publication |
| Read page | When querying one page | As soon as the page DTO is materialized | Server streaming large datasets |

Avoid the pattern of opening a transaction and then waiting for the next message. During the wait, no database work happens, yet the connection and transaction may still be held.

Before choosing a model, determine what is allowed to happen if the stream breaks partway through. If earlier messages may remain in effect, per-message or per-batch is usually appropriate. If no partial data may be published before the entire upload is valid, use staging/finalize instead of holding one transaction across the stream.

## 3. Why @Transactional on the gRPC method does not protect callbacks

For client streaming and bidirectional streaming, the gRPC method typically returns a StreamObserver so the runtime invokes callbacks when messages arrive:

```java
@Override
public StreamObserver<UploadChunk> upload(
        StreamObserver<UploadResult> responseObserver) {
    return new StreamObserver<>() {
        @Override
        public void onNext(UploadChunk chunk) {
            // Invoked after upload() has returned.
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

If @Transactional is placed on upload(), the Spring proxy only wraps the duration of calling upload() to create and return the observer. The transaction ends when the method returns; subsequent onNext/onCompleted callbacks are not inside the original transaction.

The proper approach is for the callback to call a Spring application-service bean with a @Transactional method. Each call through the proxy opens a transaction, performs database work, and commits/rolls back before returning control to the callback.

```java
@Service
@RequiredArgsConstructor
public class ChunkWriter {
    private final ChunkRepository repository;

    @Transactional
    public void save(ChunkCommand command) {
        repository.insert(command);
    }
}
```

Do not call the transactional method via self-invocation inside the same object if you are relying on Spring proxy mode; internal calls can bypass the transaction interceptor. Place the transaction boundary on a separate bean and inject it via constructor.

## 4. Server streaming: read by page and close the transaction

A common mistake is opening a transaction, obtaining a database cursor/Stream, and calling observer.onNext() for each row. If the client reads slowly, the transaction and connection may be held for the entire transfer duration.

For large datasets, use keyset pagination: read one page at a time in a short transaction, materialize it into DTOs, close the transaction, and only then send the page over gRPC.

```java
@Service
@RequiredArgsConstructor
public class ExportQueryService {
    private final TransactionRepository repository;

    @Transactional(readOnly = true)
    public List<ExportRow> loadPage(
            String accountId, long afterId, int pageSize) {
        return repository.findNextPage(accountId, afterId, pageSize);
    }
}
```

Adapter coordinating pages:

```java
long cursor = 0;
while (true) {
    List<ExportRow> page =
        exportQueryService.loadPage(accountId, cursor, PAGE_SIZE);

    if (page.isEmpty()) {
        break;
    }

    for (ExportRow row : page) {
        observer.onNext(toProto(row));
    }

    cursor = page.get(page.size() - 1).id();
}
observer.onCompleted();
```

When loadPage() returns, the read transaction has ended; the observer sends data without holding a database connection. In production code, handle cancellation, mid-page errors, and observer terminal state.

Multi-transaction pagination does not automatically guarantee a consistent snapshot. If data changes during the export, choose a high-watermark, version/as-of timestamp, snapshot export, or appropriate isolation. Do not open a long transaction solely to get a snapshot without evaluating connection, MVCC, and lock costs.

## 5. Client streaming: do not open a transaction while waiting for chunks

Client streaming receives multiple request messages. Do not start a transaction in the first callback and keep it open while waiting for the client to send the next chunk.

There are three common approaches:

- **Per-chunk:** each chunk is validated and saved in a short transaction. Already-committed chunks remain if the stream stops at a later chunk.
- **Bounded batch:** buffer a limited count/size of chunks in memory or staging; only open a transaction when the batch is ready to write. Acknowledge the batch only after commit.
- **Staging/finalize:** save each chunk to a staging table using short transactions; when the client finishes, a finalize transaction validates and publishes the main data.

For batches, limit both message count and total bytes. If a batch is too large, write transactions take too long and memory grows; if a batch is too small, commit overhead increases. Choose thresholds based on throughput, lock time, and retry capability.

Do not buffer unbounded messages in RAM to avoid long transactions. For large uploads, durable staging is usually safer.

## 6. Staging/finalize instead of one transaction across the upload

If the business requirement is "the entire upload or nothing is published", use an upload session:

1. Create an uploadId and save state OPEN.
2. Each chunk carries uploadId, sequence, checksum, and payload.
3. Save the chunk to staging using a short transaction.
4. When the client completes, verify full sequence, checksums, and validation rules.
5. In one short transaction, apply staging data to business tables and transition the session to COMPLETED.
6. A worker cleans up expired sessions or unused staging data.

```java
@Service
@RequiredArgsConstructor
public class UploadFinalizeService {
    private final UploadSessionRepository sessions;
    private final StagingRepository staging;
    private final InventoryRepository inventory;

    @Transactional
    public UploadResult finalizeUpload(String uploadId) {
        UploadSession session = sessions.lockById(uploadId)
            .orElseThrow(UploadNotFoundException::new);

        if (session.isCompleted()) {
            return session.previousResult();
        }

        validateAllChunks(session, staging);
        applyToInventory(session, staging, inventory);
        session.markCompleted();

        return session.toResult();
    }
}
```

Locking the session, applying the data, and marking COMPLETED should happen in the same transaction. A unique constraint on (upload_id, sequence) prevents duplicate chunk writes; locking or optimistic versioning prevents two concurrent finalizes from applying the same upload twice.

Staging may retain data after a failed finalize, but the main business data has not been partially published. The client can retry finalize with the same uploadId if the operation is designed to be idempotent.

## 7. Bidirectional streaming: per-command transactions

In bidirectional streaming, each request is typically a command that can be processed independently. The callback should not open a transaction and hold it across the wait for the next command.

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

                // apply() returns after the transaction commits.
                responseObserver.onNext(toReply(result));
            } catch (RuntimeException ex) {
                responseObserver.onError(toStatus(ex));
            }
        }

        @Override
        public void onError(Throwable error) {
            // Already-committed commands remain in effect.
        }

        @Override
        public void onCompleted() {
            responseObserver.onCompleted();
        }
    };
}
```

deviceCommandService.apply() is a transactional method on another Spring bean. The transaction exists only while processing the command and does not span between two onNext calls.

If offloading callbacks to an executor, use a bounded queue and preserve ordering per stream/aggregate when business rules require it. Spring imperative transactions are typically thread-bound; call the transactional bean inside the worker thread. Do not hold a transaction on the callback thread and wait for a future to complete.

## 8. Limiting connections, locks, and transaction duration

Short transactions reduce connection and lock occupancy time, but explicit limits are still required:

- **Transaction timeout:** set limits by use case type; never let a batch write transaction hang indefinitely.
- **Query/statement timeout:** prevent SQL queries or lock waits from exceeding the time budget.
- **Pool sizing:** monitor active/idle/pending connections; do not treat pool starvation solely by increasing pool size if the root cause is long transactions.
- **Batch size:** limit the number of rows and bytes processed in one transaction.
- **Lock scope:** lock only the necessary rows, hold locks briefly, and avoid network calls while holding locks.
- **Read strategy:** use keyset pagination and appropriate indexes so pages do not scan increasingly more rows.
- **Isolation:** choose the isolation level required for consistency; higher isolation can increase locks/conflicts.

A long transaction can hold old snapshots or slow down vacuum/cleanup depending on the database. Monitor database-specific metrics rather than only looking at overall RPC duration.

## 9. Backpressure, deadlines, and cancellation

Backpressure regulates the producer/consumer rate of a stream. It must not cause a database transaction to stay open while waiting for the observer to become ready or waiting for the client to send more data.

For server streaming, read a page, close the transaction, and then send the page. For client/bidi streaming, only open a transaction when a chunk/command or batch is ready to process.

Deadlines and cancellation must be coordinated:

- Set reasonable RPC deadlines.
- Set query timeouts and transaction timeouts smaller than or aligned with the RPC budget.
- When the client cancels, stop creating new work if possible.
- Do not start a transaction for a message already known to be no longer needed.
- Use the server call's cancellation hook to stop producers/workers; durable cleanup still requires a TTL or worker because processes can exit abruptly.
- If a transaction has committed but the acknowledgment was lost, retries must be protected by an idempotency key.

Cancellation cannot roll back an already-committed transaction. It can only stop uncommitted work from continuing or request an in-flight transaction to stop according to driver/database support.

## 10. Retries, idempotency, and partial commits

If each message or batch commits individually, the stream has **partial commit** semantics. For example, batches 1 and 2 committed; batch 3 failed; data from the first two batches still exists. An error status at the end of a stream does not mean all prior operations rolled back.

So clients can retry/resume safely:

- Each command/chunk/batch has a stable ID or sequence.
- Save the receipt/processing result in the same transaction as the business change.
- Use a unique constraint on operation ID or (stream_id, sequence).
- Same ID and same payload returns the previous result.
- Same ID with a different payload returns a conflict.
- Provide checkpoints so the client knows the last committed sequence.

If a command updates the database and the server loses connection before sending the ack, the client may resend. Idempotency prevents the resend from repeating the side effect.

For atomic uploads via staging, chunks can be persisted durably without being published yet; finalize is the business commit point. Clearly distinguish between "chunk received", "chunk staged", and "upload completed".

## 11. External side effects and transactional outbox

Do not hold a database transaction open while waiting on a broker, email provider, or RPC to another service. Those systems do not automatically participate in the database transaction.

If a command needs to update the database and emit an event, write an outbox record in the same transaction:

1. Update domain state.
2. Write the outbox event with an event ID/sequence.
3. Commit.
4. A worker publishes the event and marks it as sent.
5. Consumers process idempotently because publishing can repeat.

Outbox lets each command's transaction end quickly while durably saving the intent to emit an event. For multi-service workflows needing compensation, use saga/compensation instead of holding a single transaction across RPCs.

## 12. Measuring transaction duration and finding connection-holding streams

Do not measure only total RPC duration. A stream can last 10 minutes while each transaction takes only 20 ms; conversely, a 2-second RPC can hold a transaction for 1.8 seconds and occupy a connection most of the time.

Monitor at minimum:

- Transaction duration p50/p95/p99 by use case.
- Number of open transactions and the longest-running transaction.
- Connection pool active, idle, pending/acquire wait.
- Lock waits, deadlocks, statement timeouts, and rollback counts.
- Batch size, page size, and commit time.
- Chunks/messages processed, retries, duplicates, and resumes.
- Stream duration, cancellations, and backpressure wait time.
- Number of expired OPEN staging uploads and failed finalizes.

Use low-cardinality metric labels such as RPC method, transaction operation, and outcome. Do not put arbitrary stream IDs, user IDs, or sequences into metric labels. Log correlation IDs to investigate specific sessions.

Set alert thresholds for transaction duration separately from RPC duration. If the RPC is long but transactions are short, investigate network/backpressure; if transactions are long, inspect query plans, locks, and code holding transactions across I/O.

## 13. Testing to prove transactions are not held too long

Test through a real gRPC server and a database close to production. H2 may not accurately reproduce the locking, isolation, pool behavior, or statement timeouts of the deployed database.

| Test | What to verify |
| --- | --- |
| Server stream, slow-reading client | Page transaction finishes before sending the page over the network |
| Multi-page export | Does not hold a single connection/cursor across the entire stream |
| Client stream, spaced-out chunks | No transaction is open while waiting for the next chunk |
| Bounded batch | Transaction only starts when the batch is ready and bounded |
| Upload staging | Chunks saved to staging in short transactions; main data only changes on finalize |
| Idle bidi stream | No transaction held between commands |
| Cancellation/deadline | No new transactions started after stream cancellation; staging cleaned up per policy |
| Retry after lost ack | Idempotency prevents duplicate side effects |
| Pool saturation | Slow streams do not exhaust the connection pool |
| Concurrent finalize | Upload is published only once |

A useful test is intentionally slowing down client reads or pausing chunk sends while observing transactions/connections from database and pool metrics. Verify that stream duration grows while transaction duration stays within the bounds of each page/chunk/batch.

## 14. Review checklist

- Transaction scope is chosen per message, batch, page, or finalize; not for the entire stream lifecycle.
- Not placing @Transactional on the method that merely creates and returns StreamObserver and expecting callbacks to share the transaction.
- Callbacks invoke the transactional application service through a Spring proxy.
- Server streaming materializes pages/DTOs and closes the transaction before sending over the network.
- Client streaming does not hold a transaction while waiting for the next chunk.
- Batches are bounded by message count, bytes, and processing time.
- Uploads requiring atomicity use staging/finalize.
- Bidi commands have clear ordering, sequence, and concurrency policies.
- Connection, lock, query, and transaction timeouts are configured.
- Backpressure does not keep transactions open.
- Cancellation is not confused with rolling back committed transactions.
- Retries have idempotency keys, receipts, and checkpoints.
- External side effects use outbox or sagas.
- Metrics distinguish RPC duration from transaction duration.
- Integration tests verify pool behavior, transaction lifetime, cancellation, and retries.

In **SPRING_GRPC**, keeping transactions short while streaming lets the connection pool serve more RPCs, reduces lock contention, and prevents network speed from dictating how long database resources are held. Read by page, write per message or bounded batch, or use staging/finalize; open transactions only when data is ready to process and close them before waiting on the network. Measure transaction duration separately from stream duration to pinpoint true bottlenecks.
