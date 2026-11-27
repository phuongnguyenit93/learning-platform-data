# OK and Successful Outcomes

In gRPC, **`OK` is the status indicating that an RPC completed successfully according to the method's contract**. It is status code `0`. However, `OK` does not mean that every business condition matched what the user hoped for. For example, an inventory check call can return `available = false` and still finish with `OK`, because the server successfully checked stock and replied that there is not enough inventory.

When developing with **SPRING_GRPC**, you need to distinguish outcomes across three layers: transport/communication, RPC status, and business outcome. Protocol Buffers defines the messages, gRPC manages the call lifecycle and status, while the handler and Spring business service decide when an operation is considered successful. Understanding `OK` properly helps you design responses, error handling, retries, and service observability consistently.

## 1. What does `OK` represent?

gRPC defines a standard set of status codes. `OK` has the numeric value **0** and means: **the RPC completed successfully**. In gRPC Java, you can reference this status via `io.grpc.Status.OK`; on the client side, you usually do not need to read the number `0` directly, because the stub represents success with a response or a completion callback.

| Perspective | When the RPC finishes with `OK` |
| --- | --- |
| Client | The call completed successfully according to the gRPC protocol; there is no terminal RPC error |
| Server | The handler completed the call in a successful manner |
| Message | For a standard unary call, the client receives a response message; the response may be an empty message if specified by the contract |
| Streaming | The message stream ends normally |
| Business | Its meaning is defined by the contract and application; it does not necessarily mean "found", "in stock", or "approved" |

`OK` is not an HTTP status code. It is a **gRPC status code**, usually transmitted in HTTP/2 trailers when the RPC ends. A normal gRPC response may use HTTP/2 `:status = 200` while the RPC outcome is determined by `grpc-status`.

## 2. Distinguishing transport success, RPC success, and business success

These three concepts are related, but they are not interchangeable.

| Layer | Question | Example |
| --- | --- | --- |
| Transport/HTTP2 | Did connection and frame exchange succeed enough for gRPC to process? | An HTTP/2 stream is established and data is transmitted |
| RPC | Did the method complete with a successful gRPC status? | The client receives a response and terminal status `OK` |
| Business | Did the caller's request satisfy the desired business condition? | The warehouse has enough stock; payment is approved; the account exists |

For example, Order Service calls Inventory Service:

```protobuf
message CheckStockRequest {
  string sku = 1;
  int32 quantity = 2;
}

message CheckStockReply {
  bool available = 1;
  int32 remaining = 2;
}
```

If the SKU is valid but only one item remains while the buyer requests two, Inventory Service can return:

```text
CheckStockReply:
  available = false
  remaining = 1

gRPC status:
  OK
```

This is a successful check: the server understood the request, queried the data, and returned a valid result. `available = false` is a **business outcome**, not a communication error.

Conversely, if the request has `quantity = 0` when the contract requires a positive quantity, the server can return `INVALID_ARGUMENT`. In that case, the RPC fails because the request violates an input precondition, rather than returning a normal check result.

## 3. How is `OK` transmitted back to the client?

In gRPC over HTTP/2, business data and RPC termination status occupy different places:

- **Response message** carries the result according to the Protobuf schema.
- **gRPC status** indicates whether the RPC ended in success or error.
- **Trailers** typically carry `grpc-status` and may include `grpc-message` or other trailing metadata.

A successful unary response can be described at a logical level:

```text
HTTP/2 headers:
  :status = 200
  content-type = application/grpc

DATA:
  gRPC-framed CheckStockReply

HTTP/2 trailers:
  grpc-status = 0
```

This is a human-readable representation, not a raw HTTP/2 byte dump. `grpc-status = 0` is `OK`. The client gRPC runtime reads this status and returns the response to the corresponding stub API.

### Why is HTTP `200` not enough to conclude that an RPC succeeded?

With gRPC, HTTP status and gRPC status belong to two different layers. An RPC can have HTTP/2 `:status = 200` while trailers contain `grpc-status = 3` (`INVALID_ARGUMENT`) or another error code. Therefore:

- Use the gRPC client/stub to evaluate the RPC result.
- When inspecting at a proxy or in HTTP logs, check the gRPC trailers/status as well.
- Do not treat HTTP `200` alone as proof that the RPC succeeded.

In cases where an error occurs before the gRPC server can produce a normal response, the transport/proxy may return an HTTP status other than `200` or reset the stream. The client still needs to classify the error through the gRPC API it receives.

## 4. How a Java/Spring server finishes a unary RPC with `OK`

With the gRPC Java API generated from Protobuf, a unary handler typically receives a request and a `StreamObserver` to emit the response:

```java
@Override
public void checkStock(
        CheckStockRequest request,
        StreamObserver<CheckStockReply> observer) {

    int remaining = inventoryQuery.remaining(request.getSku());

    CheckStockReply reply = CheckStockReply.newBuilder()
        .setAvailable(remaining >= request.getQuantity())
        .setRemaining(remaining)
        .build();

    observer.onNext(reply);
    observer.onCompleted();
}
```

In this example:

1. The handler processes the request and builds a response message.
2. `onNext(reply)` emits the response.
3. `onCompleted()` signals that the RPC ended normally.
4. The gRPC runtime completes the call with status `OK` if no other error occurred during processing.

`onCompleted()` is not a response message; it is the stream completion signal. For unary calls, the server emits only one response. If the contract uses `google.protobuf.Empty`, the server can still complete successfully without needing a business payload containing fields.

### Do not call both `onError` and `onCompleted` for the same RPC

If validation fails, the handler can terminate with an error:

```java
if (request.getQuantity() <= 0) {
    observer.onError(
        Status.INVALID_ARGUMENT
            .withDescription("quantity must be greater than 0")
            .asRuntimeException());
    return;
}
```

After `onError(...)`, do not call `onNext(...)` or `onCompleted()` on the same observer. An RPC has only one terminal outcome: normal completion, or termination via error/cancellation according to the gRPC mechanism.

In a Spring application, the handler can inject business beans such as `InventoryQueryService`. Spring manages beans and dependencies; the gRPC runtime manages observers, dispatching, and status. The rule for choosing to return `OK` or an error status must come from the contract and processing result, not merely from whether the Java method threw an exception.

## 5. How does the client recognize success?

### 5.1. Blocking stub

With a unary blocking stub, if the RPC completes with `OK`, the call returns the response:

```java
CheckStockReply reply = inventoryStub
    .withDeadlineAfter(300, TimeUnit.MILLISECONDS)
    .checkStock(request);

if (reply.getAvailable()) {
    // Sufficient stock according to the result returned by the server.
} else {
    // RPC succeeded, but stock is insufficient.
}
```

If the RPC finishes with a status other than `OK`, the blocking stub usually throws `StatusRuntimeException`. Thus, receiving a response does not imply all business conditions are satisfied; the client needs to read the response fields.

### 5.2. Async stub

With the asynchronous API, the client receives responses via `onNext` and the successful completion signal via `onCompleted`:

```java
stub.checkStock(request, new StreamObserver<>() {
    @Override
    public void onNext(CheckStockReply reply) {
        // Read the business result.
    }

    @Override
    public void onError(Throwable error) {
        // The RPC ended with an error.
    }

    @Override
    public void onCompleted() {
        // The response stream completed normally.
    }
});
```

For unary calls, the client normally receives one `onNext` followed by `onCompleted`. For streaming, `onNext` may be called multiple times before completion. Do not use `onNext` as the sole signal proving the entire RPC succeeded; only the terminal status indicates the final outcome.

## 6. `OK` across RPC types

`OK` has the same general meaning across all four cardinalities: the RPC ended successfully. However, how responses are interpreted differs:

| RPC type | Message exchange | When is it considered completed with `OK`? |
| --- | --- | --- |
| Unary | One request, one response | The server returns the response and completes normally |
| Server streaming | One request, multiple responses | The server finishes sending the response sequence and completes normally |
| Client streaming | Multiple requests, one response | The client closes the send direction; the server processes and returns the final response successfully |
| Bidirectional streaming | Multiple requests and multiple responses | Both sides finish exchanging messages and the RPC completes normally |

### Server streaming: receiving messages does not prevent a later error

The client may receive several updates and then the stream terminates with a status other than `OK`, such as `UNAVAILABLE`. The messages already received do not disappear; however, the overall RPC is **not** considered to have completed successfully.

Therefore, for critical data streams, the client must decide whether each message can be consumed immediately upon receipt or only finalized once the stream completes with `OK`. That decision depends on application semantics.

### Client streaming and bidirectional streaming

With client streaming, finishing sending the request stream does not mean the server has processed it successfully. The client must wait for the final response and terminal status. With bidirectional streaming, each side can continue sending/receiving at its own pace; the final status is only determined when the RPC ends.

## 7. When should you return `OK`, and when should you return an error status?

Ask the question: **did the server successfully perform the operation that the method promised?**

| Scenario | Outcome to consider | Reason |
| --- | --- | --- |
| Stock check succeeded, sufficient inventory | Response `available = true`, status `OK` | The request was processed successfully |
| Stock check succeeded, insufficient inventory | Response `available = false`, status `OK` | This is a valid business outcome |
| SKU does not exist | `NOT_FOUND` or a "not found" response | Choose based on the contract and how clients need to handle it |
| Invalid negative or zero quantity | `INVALID_ARGUMENT` | The request violates an input condition |
| Caller is not authenticated | `UNAUTHENTICATED` | Identity cannot be verified |
| Caller lacks permission | `PERMISSION_DENIED` | Identity may be valid, but the caller is not authorized |
| Database temporarily unavailable | `UNAVAILABLE` or an appropriate mapping | The server cannot complete the operation right now |
| Server succeeded, but client lost the response | Client may see a transport error; business outcome is unknown | Must not infer that the server did not commit |

There is no rule that every "not found" case must be an error. If the method is defined as a search operation and "no results" is normal, the response can represent that state with `OK`. If the method requires a specific resource to exist, `NOT_FOUND` may be more appropriate. **The contract must define consistent semantics for clients.**

## 8. `OK` does not mean a write operation is durable in every sense

A server should report `OK` only after completing the work promised by the contract. For write operations, this usually means the transaction must be committed before the handler signals successful completion.

For example:

1. `ReserveStock` receives the request.
2. The server validates and updates the database.
3. The transaction commits successfully.
4. The handler returns the response and finishes the RPC with `OK`.

If the handler emits `OK` before the commit completes or before an important asynchronous task is guaranteed, the client may interpret the call as successful even though the system has not fulfilled its published guarantee. Therefore, be explicit about whether `OK` means:

- Data has been checked/read.
- The transaction has been written and committed.
- The task has been accepted into a queue, though not yet finished.
- The entire workflow has completed.

These semantics are different. If the API only **accepts** a background job, an `OK` response should accompany a task identifier or an `accepted` status, rather than implying that the workflow has finished.

Even when the server has committed and returned `OK`, the client may still fail to receive the response due to a network drop. This is why write operations with side effects need an idempotency key or a way to look up the result after a timeout; `OK` does not eliminate partial failure.

## 9. Common design mistakes

| Misconception | Correct understanding |
| --- | --- |
| `OK` means stock is available or payment is approved | `OK` means the RPC completed; response fields carry the business outcome |
| HTTP/2 `200` always means gRPC succeeded | Must check `grpc-status`, typically in trailers |
| Server calling `onNext` means the RPC already succeeded | Terminal completion/status is required; streaming can emit messages and then end in error |
| `onCompleted()` is an empty response | It is a completion signal, not a response message |
| Every undesirable case should return a gRPC error | Valid business outcomes can return a response with `OK` |
| If the server did not throw an exception, it should definitely return `OK` | Must confirm the method fulfilled its business contract |
| `OK` proves the client received the response | The server may have finished sending while the response was lost in transit |
| Having `OK` means a write operation cannot be duplicated | The client may time out or lose the response and retry; idempotency is needed |

## 10. Success design checklist for a gRPC method

Before publishing a method, answer these questions:

1. **What defines success for the method?** Read completed, commit completed, or merely task accepted?
2. **What states make up normal business outcomes?** Which states are represented by response fields?
3. **Which conditions are RPC errors?** Invalid argument, not found, permissions, unavailable, or internal?
4. **At what point does the server report `OK`?** After fulfilling the exact guarantee in the contract.
5. **What does the client read to decide?** Response fields, not just the absence of an exception.
6. **For streaming, how is the terminal status handled?** Received messages might not represent a fully successful stream.
7. **What happens if the response is lost after commit?** Is there idempotency or a way to query the status?
8. **Does telemetry distinguish status from business outcomes?** Measure RPC success rate separately from business rates such as "in stock".

## 11. Takeaways

`OK` is gRPC status code `0`, indicating that **the RPC ended successfully according to the method's semantics**. It does not by itself mean that the business outcome is positive. A response with `available = false` can still come with `OK`; an RPC returning `INVALID_ARGUMENT` fails at the RPC level because the request is invalid.

In Spring gRPC, the handler decides the response and status according to the contract; the gRPC runtime transmits the status back to the client; the client stub represents success via a response or completion callback. Keep the three concepts **transport**, **RPC status**, and **business outcome** separate. When they are clearly designed, clients handle results more easily, retries are safer, and dashboards do not confuse "the RPC ran fine" with "the business goal was achieved".

### References

- [gRPC – Status codes](https://grpc.io/docs/guides/status-codes/)
- [gRPC – Core concepts, architecture and lifecycle](https://grpc.io/docs/what-is-grpc/core-concepts/)
- [gRPC – Java basics](https://grpc.io/docs/languages/java/basics/)
- [gRPC – Deadlines](https://grpc.io/docs/guides/deadlines/)
- [Protocol Buffers – Proto3 language guide](https://protobuf.dev/programming-guides/proto3/)
