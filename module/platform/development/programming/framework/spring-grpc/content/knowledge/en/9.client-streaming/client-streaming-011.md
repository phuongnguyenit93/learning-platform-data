# Testing empty, partial, and complete client sends

**Chapter:** Client streaming  
**Scope:** Spring gRPC (`SPRING_GRPC`) with Protocol Buffers contracts, generated Java code, and client streaming RPCs that receive multiple requests and return one response.

## 1. Three cases that must be tested

A client streaming RPC can receive many request messages, yet the server returns only one success response after the client ends the send stream. When testing, distinguish three batch states:

| Case | What does the client send? | Expected result |
| --- | --- | --- |
| **Empty** | Declares a batch with 0 items then half-closes | Server rejects with `INVALID_ARGUMENT`; no receipt |
| **Partial** | Declares 3 expected items, sends only 2 then half-closes | Server rejects with `FAILED_PRECONDITION`; no success receipt |
| **Complete** | Declares 3 expected items, sends all 3 then half-closes | Server returns exactly one receipt, then ends `OK` |

The key point is that the **partial** case can still close the send direction normally: the client calls `requestObserver.onCompleted()`, yet the actual item count does not match the count promised in the manifest. This is a batch completeness error, distinct from the client disconnecting or cancelling before half-closing.

## 2. Putting batch rules in the contract

For the server to know whether a batch is complete, the client must declare the expected item count. Example contract:

```proto
syntax = "proto3";

package ingest.v1;
option java_package = "com.example.ingest.grpc";
option java_multiple_files = true;

service BatchService {
  rpc Upload(stream UploadRequest) returns (UploadReceipt);
}

message UploadRequest {
  oneof body {
    BatchStart start = 1;
    BatchItem item = 2;
  }
}

message BatchStart {
  string batch_id = 1;
  uint32 expected_count = 2;
}

message BatchItem {
  uint32 sequence = 1;
  string value = 2;
}

message UploadReceipt {
  string batch_id = 1;
  uint32 accepted_count = 2;
}
```

Example conventions:

1. The first message must be `BatchStart`, appearing exactly once.
2. `expected_count` must be greater than 0 and within the service's quota.
3. Subsequent messages must be `BatchItem`, with `sequence` contiguous starting from 0.
4. The client calls `onCompleted()` once it has finished sending its intended data.
5. The server returns a receipt only if the actual item count equals `expected_count`.

Without `expected_count`, the server cannot distinguish a fully sent batch from a truncated batch where the client still actively half-closed. For data sources whose item count is unknown ahead of time, you can use a manifest containing total bytes/hash or an explicit commit protocol; this lesson uses expected count to illustrate the three cases clearly.

## 3. Server checks count before returning a receipt

The core logic lives in the request-receiving observer: counting items, checking sequence numbers, and comparing counts upon receiving inbound `onCompleted()`.

```java
@GrpcService
public class BatchGrpcService extends BatchServiceGrpc.BatchServiceImplBase {

    private static final int MAX_ITEMS = 1_000;

    @Override
    public StreamObserver<UploadRequest> upload(
            StreamObserver<UploadReceipt> responseObserver) {

        return new StreamObserver<>() {
            private String batchId;
            private int expectedCount;
            private int receivedCount;
            private boolean started;
            private boolean terminated;

            @Override
            public void onNext(UploadRequest request) {
                if (terminated) return;

                switch (request.getBodyCase()) {
                    case START -> {
                        if (started) {
                            fail(Status.INVALID_ARGUMENT,
                                    "BatchStart may only be sent once");
                            return;
                        }
                        BatchStart start = request.getStart();
                        if (start.getBatchId().isBlank()
                                || start.getExpectedCount() > MAX_ITEMS) {
                            fail(Status.INVALID_ARGUMENT,
                                    "Invalid manifest");
                            return;
                        }
                        started = true;
                        batchId = start.getBatchId();
                        expectedCount = start.getExpectedCount();
                    }
                    case ITEM -> {
                        if (!started) {
                            fail(Status.INVALID_ARGUMENT,
                                    "BatchStart must be the first message");
                            return;
                        }
                        if (receivedCount >= expectedCount) {
                            fail(Status.INVALID_ARGUMENT,
                                    "Received more items than expected_count");
                            return;
                        }
                        BatchItem item = request.getItem();
                        if (item.getSequence() != receivedCount) {
                            fail(Status.INVALID_ARGUMENT,
                                    "Non-contiguous sequence");
                            return;
                        }
                        receivedCount++;
                    }
                    case BODY_NOT_SET -> fail(
                            Status.INVALID_ARGUMENT, "Missing request body");
                }
            }

            @Override
            public void onError(Throwable error) {
                // Client cancelled or inbound stream failed.
                terminated = true;
            }

            @Override
            public void onCompleted() {
                if (terminated) return;
                if (!started) {
                    fail(Status.INVALID_ARGUMENT, "Missing BatchStart");
                    return;
                }
                if (expectedCount == 0) {
                    fail(Status.INVALID_ARGUMENT, "Empty batch");
                    return;
                }
                if (receivedCount < expectedCount) {
                    fail(Status.FAILED_PRECONDITION,
                            "Batch is missing items");
                    return;
                }

                UploadReceipt receipt = UploadReceipt.newBuilder()
                        .setBatchId(batchId)
                        .setAcceptedCount(receivedCount)
                        .build();
                terminated = true;
                responseObserver.onNext(receipt);
                responseObserver.onCompleted();
            }

            private void fail(Status status, String description) {
                if (terminated) return;
                terminated = true;
                responseObserver.onError(status
                        .withDescription(description)
                        .asRuntimeException());
            }
        };
    }
}
```

This example focuses on completeness checking without persisting business data. In a real service, per-item validation and data commit must happen before sending the receipt. If the commit fails, the server terminates with an error status; never return a success receipt solely because the message count matched.

### Why choose two different statuses?

- `INVALID_ARGUMENT`: the client declared an empty batch, omitted the manifest, sent messages out of order, or sent more items than declared. The request violated input rules.
- `FAILED_PRECONDITION`: the client half-closed, but the number of items received is fewer than promised. The batch has not met the precondition to complete.

This is the example's API policy. A system may pick different statuses if clearly specified in the contract, as long as classification remains consistent across server, client, and tests.

## 4. Writing tests for all three cases with in-process gRPC

In-process testing runs the gRPC server and channel in the same process while still going through real gRPC stubs, internal transport, and callbacks. That lets tests assert the final status, response count, and behavior when the client half-closes.

A test helper can open the stream, send the manifest, send the specified number of items, and call `onCompleted()`:

```java
record Outcome(
        UploadReceipt receipt,
        Status.Code error,
        int responseCount,
        boolean completed) {}

private Outcome upload(int expected, int actual) throws Exception {
    CompletableFuture<Outcome> result = new CompletableFuture<>();
    AtomicInteger responseCount = new AtomicInteger();

    StreamObserver<UploadReceipt> responses = new StreamObserver<>() {
        private UploadReceipt receipt;

        @Override
        public void onNext(UploadReceipt value) {
            receipt = value;
            responseCount.incrementAndGet();
        }

        @Override
        public void onError(Throwable error) {
            result.complete(new Outcome(
                    null,
                    Status.fromThrowable(error).getCode(),
                    responseCount.get(),
                    false));
        }

        @Override
        public void onCompleted() {
            result.complete(new Outcome(
                    receipt, null, responseCount.get(), true));
        }
    };

    StreamObserver<UploadRequest> requests =
            BatchServiceGrpc.newStub(channel).upload(responses);

    requests.onNext(UploadRequest.newBuilder()
            .setStart(BatchStart.newBuilder()
                    .setBatchId("test-batch")
                    .setExpectedCount(expected))
            .build());

    for (int i = 0; i < actual; i++) {
        requests.onNext(UploadRequest.newBuilder()
                .setItem(BatchItem.newBuilder()
                        .setSequence(i)
                        .setValue("value-" + i))
                .build());
    }

    requests.onCompleted();
    return result.get(3, TimeUnit.SECONDS);
}
```

The helper assumes the test already started an in-process `channel` and registered `BatchGrpcService`. Each call creates a new RPC; `CompletableFuture` waits for the terminal callback instead of using `Thread.sleep()`.

### Test 1: client sends an empty batch

```java
@Test
void rejectsEmptyBatch() throws Exception {
    Outcome outcome = upload(0, 0);

    assertEquals(Status.Code.INVALID_ARGUMENT, outcome.error());
    assertNull(outcome.receipt());
    assertEquals(0, outcome.responseCount());
    assertFalse(outcome.completed());
}
```

Here the client still sends `BatchStart(expected_count = 0)` and then half-closes. This is an explicitly declared empty batch, distinct from sending zero request messages altogether. You can add a separate test for a stream without even `BatchStart`; the server must reject that too for missing the manifest.

### Test 2: client sends a partial batch

```java
@Test
void rejectsPartialBatchAfterHalfClose() throws Exception {
    // Committed to 3 items but sent only 2, then closed request direction.
    Outcome outcome = upload(3, 2);

    assertEquals(Status.Code.FAILED_PRECONDITION, outcome.error());
    assertNull(outcome.receipt());
    assertEquals(0, outcome.responseCount());
    assertFalse(outcome.completed());
}
```

This is a critical test: the client called `onCompleted()`, yet the server still rejects because the batch is incomplete. **Closing the send direction does not prove the batch is valid.**

### Test 3: client sends a complete batch

```java
@Test
void acceptsCompleteBatchWithOneReceipt() throws Exception {
    Outcome outcome = upload(3, 3);

    assertNull(outcome.error());
    assertTrue(outcome.completed());
    assertNotNull(outcome.receipt());
    assertEquals("test-batch", outcome.receipt().getBatchId());
    assertEquals(3, outcome.receipt().getAcceptedCount());
    assertEquals(1, outcome.responseCount());
}
```

The complete-batch test verifies the server returns exactly **one** response and then terminates normally. Do not assert `completed == true` alone: verify the receipt, batch ID, and accepted count.

## 5. Distinguishing a partial batch from an interrupted stream

These two scenarios are not the same:

| Scenario | Did client call `onCompleted()`? | Outcome |
| --- | --- | --- |
| Sends 2/3 items then half-closes | Yes | Server receives inbound `onCompleted()`, detects missing item, returns `FAILED_PRECONDITION` |
| Sends 2/3 items then disconnects/cancels | Not necessarily | RPC ends via transport/cancellation; server cleans up staging, client gets corresponding status |

The partial-batch test in section 4 tests **incomplete input with normal stream closure**. To test interruption, write a separate test: send the manifest and one item, then call cancel or let the deadline expire before half-closing; verify no success receipt arrives and staging resources are cleaned up.

Do not merge both tests into one because they verify two distinct termination paths: one is the server actively rejecting a business precondition, while the other is RPC cancellation or transport failure.

## 6. Minimum test matrix

| Test case | Request | What to assert |
| --- | --- | --- |
| Completely empty stream | No BatchStart, half-close | `INVALID_ARGUMENT`, no receipt |
| Batch declaring 0 items | Start with expected_count = 0, half-close | `INVALID_ARGUMENT`, no receipt |
| Partial batch | expected = 3, actual = 2, half-close | `FAILED_PRECONDITION`, no receipt |
| Complete batch | expected = 3, actual = 3, half-close | `OK`, one receipt, accepted_count = 3 |
| Extra items sent | expected = 2, actual = 3 | `INVALID_ARGUMENT`, no receipt |
| Wrong sequence | Send 0 then 2 | `INVALID_ARGUMENT` |
| Missing BatchStart | Send item before manifest | `INVALID_ARGUMENT` |
| Mid-stream cancellation | Send partially then cancel | No success receipt; cleanup runs |
| Two concurrent clients | Two different batch IDs | State and receipts do not mix |

For every error test, assert **zero success response messages**. For success tests, assert exactly one response. This catches bugs where the server accidentally calls `onNext(receipt)` before checking item count.

## 7. Common mistakes when writing tests

- **Checking only the status:** tests can miss cases where the server emitted a receipt before returning an error. Count the response messages.
- **Confusing half-close with success:** partial tests must call `onCompleted()` to prove the server still checks the actual count.
- **No manifest:** if the server has no expected count, tests cannot clearly define "partial."
- **Using sleep to wait for callbacks:** leads to flaky tests. Use `CompletableFuture`, latches, or barriers with bounded timeouts.
- **Testing only a single RPC:** test two concurrent batches to detect state shared across observers.
- **Ignoring storage state:** if the service writes staging/database rows, verify record counts and cleanup after partial, empty, and cancel tests.

## 8. Self-practice

1. Write a test for a stream that sends no `BatchStart` at all and then half-closes. What should the status be?
2. If a client declares 4 items and sends 4 items with sequences 0, 1, 3, 4, what should the server return? Why must it not return a receipt?
3. Add a test sending one item more than `expected_count`; verify the server does not emit a receipt before reporting the error.
4. Add a simulated staging layer and verify a partial batch is cleaned up when half-closed with missing items; contrast this with cancellation before half-close.
5. If the server returns a receipt after enough items arrive but the database commit fails, which processing order and assertions must be updated?

**Remember:** Client streaming tests must cover **empty batches, partial batches, and complete batches**. Declare the expected item count in the manifest, check the actual message count on inbound `onCompleted()`, and verify both status and response count: empty/incomplete batches must be rejected with no receipt; complete batches return exactly one receipt and finish `OK`.
