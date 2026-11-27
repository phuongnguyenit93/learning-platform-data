# Retrying client streaming and batch duplicates

## 1. Why do client streaming and batches need a dedicated retry strategy?

In **Spring gRPC**, a client-streaming RPC lets the client send multiple request messages over a single call, after which the server returns one aggregated response. This pattern fits data imports, catalog synchronization, event uploads, or submitting a batch of commands.

Difficulty arises when the connection drops midway. The server may have processed part or all of the batch, while the client has not yet received the final response. If the client opens a new call and resends all the data, the server may process already-committed items twice.

Two concepts must be separated:

- **gRPC automatic retry:** the runtime can replay an RPC when the call is uncommitted, the request is still in the retry buffer, and the status matches the policy.
- **Application-layer replay/resubmit:** the client creates a new RPC and resends the batch or unacknowledged portion, using stable IDs so the server can deduplicate.

For batches with side effects, you cannot rely on `maxAttempts` to prevent duplicate processing. You need stable identifiers for the batch and each item, durable storage of idempotency outcomes, and a recovery procedure when the client does not know how much of the batch was processed.

## 2. Automatic retry is bounded by commitment and the retry buffer

gRPC can automatically replay a call only while the call is **uncommitted**. Two key events can commit a call:

- The client receives response headers from the server.
- Sent request data exceeds the retry buffer limit that the runtime can keep for replay.

With client streaming, the client sends multiple messages on the same call. If the entire request remains buffered and the server has not sent response headers, some retryable errors may allow the runtime to replay the call. However, when the stream is long or payloads are large enough to exceed the retry buffer, the call may commit before the client finishes sending. Once committed, subsequent errors will not cause gRPC to automatically resend the entire batch.

Therefore:

| Situation | Automatic retry | Application behavior |
| --- | --- | --- |
| Early failure, call uncommitted, retryable status | May replay if policy and deadline allow | Let the gRPC runtime handle it |
| Request stream exceeds retry buffer | Call may already be committed | Do not rely on automatic retry |
| Server has sent response headers | Call is committed | Query the batch or open a new call per contract |
| Server processed part of the batch then connection dropped | No guarantee of safe replay | Replay with stable item IDs and dedup |
| Server finished processing but final response was lost | Client does not know the outcome | Query receipt/status before resending |

Do not assume every client-streaming RPC will be retried automatically. Replayability depends on commitment timing, the retry buffer, status, policy, and deadline.

## 3. Identifying the batch and individual items

A batch needs at least two levels of identification:

- `batch_id`: identifies one logical import job, kept unchanged when resubmitting the batch.
- `item_id`: stable identifier for each record/command in the batch, unchanged when the item is resent.

Example:

```text
batch_id = import-2026-11-19-warehouse-17
item_id  = source-system:product:SKU-1042
item_id  = source-system:product:SKU-1043
item_id  = source-system:product:SKU-1044
```

The server should construct the dedup key scoped by `(tenant_id, method_name, batch_id, item_id)`. That way, the same item ID in a new batch is a separate operation, while an item resent within the same batch is still deduplicated. If the contract guarantees globally unique item IDs per tenant/method, a narrower key can be used; pick a single semantics and publish it clearly.

Do not generate a new UUID for an item on each retry. If the ID changes, the server cannot recognize the new item as a resubmission of the old item.

## 4. Protobuf contract for batch streaming

Example `batch_import.proto`:

```proto
syntax = "proto3";

package import.v1;

option java_multiple_files = true;
option java_package = "com.example.importing.v1";

service BatchImport {
  rpc UploadBatch(stream BatchItem) returns (BatchReceipt);
  rpc GetBatchStatus(GetBatchStatusRequest) returns (BatchStatus);
}

message BatchItem {
  string batch_id = 1;
  string item_id = 2;
  string source_version = 3;
  string payload = 4;
}

message BatchReceipt {
  string batch_id = 1;
  // The counters below describe the current upload RPC.
  int32 total_items = 2;
  int32 applied_items = 3;
  int32 duplicate_items = 4;
  int32 rejected_items = 5;
  string state = 6;
  int32 pending_items = 7;
}

message GetBatchStatusRequest {
  string batch_id = 1;
}

message BatchStatus {
  // Durable state and counters for the entire batch.
  string batch_id = 1;
  string state = 2;
  int32 total_items = 3;
  int32 applied_items = 4;
  int32 rejected_items = 5;
  string detail = 6;
  int32 pending_items = 7;
}
```

`UploadBatch` receives multiple items and returns a single `BatchReceipt` once the request stream completes. `GetBatchStatus` helps the client query the result after a call drops or the final response is lost.

`BatchReceipt` counts items received/processed during **the current upload**: an item applied for the first time is applied, an item with an existing result is duplicate, and an item failing validation/conflict is rejected. `GetBatchStatus` reflects the durable state of the entire batch across uploads; do not blindly sum counters from individual attempts.

When querying status, the server must obtain the tenant from the authenticated security context and verify access rights to the batch; never trust a client-supplied `batch_id` alone to read another tenant's data.

The contract must specify clearly:

- One `batch_id` represents one logical batch; replays must keep the same ID.
- One `item_id` always represents the same business content.
- Same ID with the same payload fingerprint is a valid duplicate; the server returns the stored outcome and does not re-apply side effects.
- Same ID with a different payload is a conflict, and must not silently overwrite.
- `BatchReceipt` combines counters for the current upload with durable state; `GetBatchStatus` is the authoritative source for the overall batch state.
- Batch state may be `PROCESSING`, `COMPLETED`, `COMPLETED_WITH_ERRORS`, or `FAILED`; client and server must agree on the semantics.

For example, store per-item results in the database and return only counts in the receipt. For large batches, do not cram all detailed errors into a single response; provide a paginated or per-item query API.

## 5. Per-item duplicate handling

Do not deduplicate solely by `batch_id`. A batch can be resent after the server has already processed part of it; the server needs to know which items are committed and which are not.

A minimal idempotency table:

```sql
CREATE TABLE batch_item_result (
    tenant_id       VARCHAR(100) NOT NULL,
    method_name     VARCHAR(200) NOT NULL,
    batch_id        VARCHAR(160) NOT NULL,
    item_id         VARCHAR(200) NOT NULL,
    payload_hash    VARCHAR(64) NOT NULL,
    state           VARCHAR(32) NOT NULL,
    result_payload  BYTEA,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, method_name, batch_id, item_id)
);
```

The primary key guarantees the same item in the same batch cannot be claimed twice. A new batch can contain a similar item ID without being confused with a previous import.

Processing flow for one item:

1. Authenticate tenant and batch.
2. Canonicalize payload and compute fingerprint.
3. Attempt to claim the item with an atomic database operation backed by the unique constraint.
4. If the new claim succeeds, apply business changes and store the result in the same transaction.
5. If the item already exists and the fingerprint matches, return the stored state without re-executing side effects.
6. If the item already exists with a different fingerprint, mark conflict and reject the item.

Do not use `SELECT` then `INSERT` without a unique constraint. Two concurrent requests could both read "not found" and both apply side effects.

### 5.1. Handling concurrent items

When two uploads submit the same item simultaneously:

- The unique constraint allows only one transaction to claim the new item.
- The other request must read the claimed/committed state.
- If the item is already completed, return the old outcome.
- If the item is currently processing, do not start side effects a second time; return `IN_PROGRESS` or let the client query later.
- If the owner transaction rolls back, the item claim also rolls back so a subsequent request can process it.

If using an `IN_PROGRESS` state committed before side effects, you need a lease, owner token, and recovery mechanism if the worker dies. If side effects and outcomes can live in the same database transaction, keeping them in the same transaction is simpler and safer.

## 6. Spring service: stream processing and receipt aggregation

The example below processes each item synchronously inside the callback to illustrate transaction boundaries. In production, a dedicated worker/queue can be used, provided the queue is bounded, ordering is preserved when needed, and the receipt is returned only after all items have durable outcomes.

```java
package com.example.importing;

import com.example.importing.v1.BatchImportGrpc;
import com.example.importing.v1.BatchItem;
import com.example.importing.v1.BatchReceipt;
import com.example.importing.v1.BatchStatus;
import com.example.importing.v1.GetBatchStatusRequest;
import io.grpc.Status;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;

@Service
public class BatchImportGrpcService
        extends BatchImportGrpc.BatchImportImplBase {

    private final BatchItemHandler itemHandler;
    private final BatchResultStore resultStore;

    public BatchImportGrpcService(
            BatchItemHandler itemHandler,
            BatchResultStore resultStore) {
        this.itemHandler = itemHandler;
        this.resultStore = resultStore;
    }

    @Override
    public StreamObserver<BatchItem> uploadBatch(
            StreamObserver<BatchReceipt> responseObserver) {
        ServerCallStreamObserver<BatchReceipt> output =
                (ServerCallStreamObserver<BatchReceipt>) responseObserver;
        return new StreamObserver<>() {
            private String batchId;
            private boolean terminated;
            private int totalItems;
            private int appliedItems;
            private int duplicateItems;
            private int rejectedItems;
            private int pendingItems;

            {
                output.setOnCancelHandler(() -> {
                    synchronized (this) {
                        terminated = true;
                        if (batchId != null) {
                            resultStore.markInterruptedIfOpen(batchId);
                        }
                    }
                });
            }

            @Override
            public synchronized void onNext(BatchItem item) {
                if (terminated) return;
                if (item.getBatchId().isBlank()
                        || item.getItemId().isBlank()) {
                    fail(Status.INVALID_ARGUMENT
                            .withDescription("batch_id and item_id are required"));
                    return;
                }
                if (batchId == null) {
                    batchId = item.getBatchId();
                } else if (!batchId.equals(item.getBatchId())) {
                    fail(Status.INVALID_ARGUMENT
                            .withDescription("A stream must contain only one batch_id"));
                    return;
                }

                totalItems++;
                try {
                    // Atomic dedup + business effect + stored outcome.
                    switch (itemHandler.applyOnce(item)) {
                        case APPLIED -> appliedItems++;
                        case DUPLICATE -> duplicateItems++;
                        case REJECTED -> rejectedItems++;
                        case IN_PROGRESS -> pendingItems++;
                    }
                } catch (ItemConflictException conflict) {
                    // Conflict is an item-level error; handler records the rejected outcome.
                    rejectedItems++;
                    itemHandler.recordConflict(item, conflict);
                } catch (RuntimeException error) {
                    fail(Status.INTERNAL
                            .withDescription("Failed to process batch item"));
                }
            }

            @Override
            public synchronized void onError(Throwable error) {
                terminated = true;
                // Batch may still be in PARTIAL/PROCESSING state.
                // Client queries by batchId before resubmitting.
                if (batchId != null) {
                    resultStore.markInterruptedIfOpen(batchId);
                }
            }

            @Override
            public synchronized void onCompleted() {
                if (terminated) return;
                if (output.isCancelled()) {
                    terminated = true;
                    if (batchId != null) {
                        resultStore.markInterruptedIfOpen(batchId);
                    }
                    return;
                }
                if (batchId == null) {
                    fail(Status.INVALID_ARGUMENT
                            .withDescription("Batch contains no items"));
                    return;
                }
                try {
                    BatchReceipt receipt = resultStore.buildReceipt(
                            batchId, totalItems, appliedItems,
                            duplicateItems, rejectedItems, pendingItems);
                    terminated = true;
                    output.onNext(receipt);
                    output.onCompleted();
                } catch (RuntimeException error) {
                    fail(Status.INTERNAL
                            .withDescription("Failed to assemble batch receipt"));
                }
            }

            private synchronized void fail(Status status) {
                if (!terminated) {
                    terminated = true;
                    if (batchId != null) {
                        resultStore.markInterruptedIfOpen(batchId);
                    }
                    if (!output.isCancelled()) {
                        output.onError(status.asRuntimeException());
                    }
                }
            }
        };
    }

    @Override
    public void getBatchStatus(
            GetBatchStatusRequest request,
            StreamObserver<BatchStatus> responseObserver) {
        try {
            responseObserver.onNext(
                    resultStore.getStatus(request.getBatchId()));
            responseObserver.onCompleted();
        } catch (BatchNotFoundException error) {
            responseObserver.onError(Status.NOT_FOUND
                    .withDescription("Batch not found")
                    .asRuntimeException());
        }
    }
}
```

`BatchItemHandler.applyOnce()` returns `APPLIED`, `DUPLICATE`, `REJECTED`, or `IN_PROGRESS`, while performing claim, dedup, side effects, and outcome persistence using the transaction/unique constraint from the previous section. `IN_PROGRESS` means another request currently owns the item; side effects must not be executed a second time. `recordConflict()` logs the conflict for the current upload in a separate attempt log/receipt without overwriting the canonical fingerprint or result of a previously processed item. `BatchResultStore.buildReceipt()` combines counters of the current upload with durable batch state; `GetBatchStatus` is the authoritative source for reconciliation after a lost response.

The example uses sequential callbacks and synchronous processing. If offloading processing to an executor:

- Use a bounded queue and manual inbound flow control or an appropriate backpressure mechanism.
- Do not emit the final response before every item has finished or recorded its outcome.
- Synchronize batch state updates and avoid concurrent response writes from callbacks.
- When the RPC is cancelled, stop accepting new items; do not delete already-committed results.

## 7. Client: preserve batch identity across resubmits

The client must persist `batch_id`, the list of `item_id` values, and payloads before sending. When the stream finishes normally, read the receipt. When receiving an error or losing connection, do not generate new IDs and do not assume the batch failed.

Recovery flow:

1. Call `GetBatchStatus(batch_id)` against a status source with appropriate consistency, scoped to the authenticated tenant.
2. If `COMPLETED`, use the stored receipt/status; do not upload again.
3. If `PROCESSING`, wait or poll with bounds.
4. If the batch still has missing items and the server supports safe replay, open a new RPC with **the same batch ID and item IDs**.
5. The server deduplicates already-committed items and processes only items without a result.
6. If status cannot be determined, keep the client state as `UNKNOWN`; do not submit a new batch with a different ID.

If the status store reads from an eventual-consistent replica, `NOT_FOUND` or stale counters do not prove the batch has not been processed. When deciding whether to replay, status lookups must read from a consistent source or use a reconciliation mechanism that can confirm state.

Example client-streaming stub:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import io.grpc.stub.StreamObserver;
import com.example.importing.v1.BatchItem;
import com.example.importing.v1.BatchReceipt;

String batchId = persistedBatch.batchId();
CountDownLatch completed = new CountDownLatch(1);
AtomicReference<BatchReceipt> receiptRef = new AtomicReference<>();
AtomicReference<Throwable> failureRef = new AtomicReference<>();

StreamObserver<BatchReceipt> responseObserver = new StreamObserver<>() {
    @Override
    public void onNext(BatchReceipt receipt) {
        receiptRef.set(receipt);
    }

    @Override
    public void onError(Throwable error) {
        failureRef.set(error);
        completed.countDown();
    }

    @Override
    public void onCompleted() {
        completed.countDown();
    }
};

StreamObserver<BatchItem> requestObserver = batchStub
        .withDeadlineAfter(30, TimeUnit.SECONDS)
        .uploadBatch(responseObserver);

for (PersistedItem item : persistedBatch.items()) {
    requestObserver.onNext(BatchItem.newBuilder()
            .setBatchId(batchId)
            .setItemId(item.itemId())
            .setSourceVersion(item.sourceVersion())
            .setPayload(item.payload())
            .build());
}
requestObserver.onCompleted();

if (!completed.await(35, TimeUnit.SECONDS)) {
    throw new IllegalStateException("Terminal callback not received");
}
if (failureRef.get() != null) {
    // Query GetBatchStatus(batchId); do not generate a new batch_id.
    reconcileBatch(batchId, failureRef.get());
} else {
    persistReceipt(receiptRef.get());
}
```

This is an example for a single upload. `persistedBatch` must keep the batch ID and item IDs stable across process restarts; `reconcileBatch()` performs the status lookup and decides whether to resubmit. In real applications, ensure channel/stub lifecycle management, interruption handling, and call cancellation when the caller is no longer interested.

## 8. Retry the whole batch or only unfinished items?

The two approaches have different trade-offs:

| Approach | Advantage | Condition |
| --- | --- | --- |
| Replay whole batch with same IDs | Simple; server deduplicates already-processed items | Server stores item results durably and handles duplicates safely |
| Resubmit only unfinished items | Saves bandwidth and processing cost | Client has reliable per-item receipts/statuses |
| Split batch into small chunks | Bounds replay volume and retry buffer usage | Each chunk has its own ID/sequence and receipt |

For small or medium batches, replaying the entire batch with the same item IDs can be simple and reliable. For large batches, split into chunks with stable identifiers such as `batch_id + chunk_number`, and save per-chunk receipts. That way the client only needs to resume from unfinished chunks.

Do not partially resubmit based on client-side counters if the client has not received a durable acknowledgment. If the final response is lost, the client does not know which item was the last one committed by the server; query server state or replay with dedup.

## 9. Partial success and batch state

A batch can contain both valid and rejected items. The contract must distinguish:

- **Transport/RPC failure:** the call ends with a gRPC status; the client may not receive a receipt.
- **Item rejection:** one item is rejected due to validation or conflict; other items can still be processed.
- **Batch completion:** all items have final outcomes; the receipt reflects applied, duplicate, and rejected counts.
- **Batch processing:** the server has not finished yet or workers are still executing.

Do not call `onError()` for every item error if the policy allows partial batch success. Validation failure of a single item should be recorded as that item's outcome; only infrastructure failures preventing the batch from continuing should terminate the entire RPC.

If the batch is processed concurrently, the receipt should only be emitted once every item has reached a final state or the batch is marked partial according to the contract. An item that is still `IN_PROGRESS` must not be counted as completed.

## 10. Testing retry and batch duplicates

Tests must verify side-effect counts, not just RPC invocation counts:

| Scenario | Expected result |
| --- | --- |
| First batch upload succeeds | Each item is applied once; accurate receipt is received |
| Resend entire batch with same IDs and payloads | Old items are deduplicated; no new side effects occur |
| Same item ID with different payload | Item conflict; does not overwrite old result |
| Disconnect after part of items committed | Status reflects partial progress; replay with same IDs does not double-apply |
| Server finishes processing but receipt is lost | Status lookup returns completed result |
| Two uploads of the same batch run concurrently | Unique constraint prevents an item from being processed twice |
| Executor/database error while processing one item | Does not leave item in a false completed state; reconcilable |
| Request stream exceeds retry buffer | Do not expect automatic retry; application uses status lookup/replay |
| Deadline expires mid-batch | Client does not assume batch rollback; queries status |
| Chunked batch | Completed chunks are not reprocessed; missing chunks resume |

Use a real test database or repository with an actual unique constraint to test race conditions. Sequential in-memory tests are insufficient to prove dedup safety when multiple replicas receive batches concurrently. Simulate a lost response after commit to verify ambiguous outcomes.

## 11. Common mistakes

1. **Increasing `maxAttempts` and assuming client streams always replay.** Retry buffers and commitment can commit the call before the stream finishes.
2. **Deduplicating using only `batch_id`.** You need to know which items inside the batch were committed.
3. **Generating new item IDs on resubmit.** The server treats resent items as brand-new items.
4. **Using in-memory counters as a receipt.** Process restarts or multiple replicas break correctness.
5. **Using SELECT then INSERT without a unique constraint.** Two concurrent requests can both apply side effects.
6. **Returning the receipt before all items have durable outcomes.** The client may assume the batch finished while items are still running.
7. **Treating an RPC error as a batch rollback.** Part or all of the batch may have committed.
8. **Nesting unbounded retries across client, service, and dependencies.** One batch can amplify into many downstream executions.
9. **Not capping batch size.** Oversized batches strain the retry buffer, memory, processing time, and replay cost.

## 12. Practice exercises

For `import.v1.BatchImport/UploadBatch`:

1. Create a batch of 100 items with stable `batch_id` and `item_id` values.
2. Store each item's fingerprint and result using a unique constraint; side effects and outcomes must share the same transaction.
3. Disconnect the client after the server commits part of the batch; call `GetBatchStatus` and identify missing items.
4. Resubmit the entire batch with the same IDs; verify committed items become duplicates and are not re-applied.
5. Send the same item ID with a different payload; verify conflict.
6. Run two concurrent uploads of the same batch to test atomic dedup.
7. Split a large batch into chunks and compare replay cost against resending the whole batch.

**Completion criteria:** learners explain the limits of client-streaming automatic retry, design stable batch/item identities, deduplicate each item atomically, handle partial/ambiguous outcomes, and recover batches without repeating side effects.

### References

- [gRPC Retry](https://grpc.io/docs/guides/retry/): retry commitment, retry buffer, and replay limits.
- [gRPC Core Concepts](https://grpc.io/docs/what-is-grpc/core-concepts/): client streaming and RPC lifecycle.
- [gRPC Service Config](https://grpc.io/docs/guides/service-config/): retry policy per service and method.
- [Spring Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transactions and atomicity in Spring.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): gRPC client/server integration in Spring.
