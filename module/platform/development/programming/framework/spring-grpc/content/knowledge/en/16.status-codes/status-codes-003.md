# UNKNOWN and Unclassified Errors

In gRPC, **`UNKNOWN` is status code `2`**, used when an error occurs that cannot be accurately classified into a more specific status. It tells the client that the RPC did not complete successfully, but the code itself does not pinpoint a cause such as an invalid request, insufficient permissions, a temporarily unavailable server, or corrupted data.

Therefore, `UNKNOWN` is usually a signal that further investigation is needed. When developing with **SPRING_GRPC**, the server should translate known business errors into appropriate statuses; unexpected errors should be logged on the server side while returning safe information to the client. The client needs to read the status, metadata/trailers, and correlation ID to find the root cause, rather than automatically retrying every `UNKNOWN` error.

## 1. Meaning of UNKNOWN

gRPC defines `UNKNOWN` with the numeric value **2**. This is a general status for an error that is unknown or lacks enough information to be mapped to a more specific code. In gRPC Java, it can be referenced via `io.grpc.Status.UNKNOWN`.

| Perspective | Meaning |
| --- | --- |
| Client | The RPC ended in error, but the status does not identify a specific cause |
| Server | An error occurred that was not explicitly classified or translated before terminating the RPC |
| gRPC runtime | Transmits the `UNKNOWN` status back to the client via the gRPC mechanism |
| Business | Cannot yet conclude whether the operation completely failed; further context is needed |

`UNKNOWN` does not mean "resource not found". Not-found cases typically use `NOT_FOUND`. Nor does it mean "server is down"; a service that is temporarily unable to serve requests is usually represented by `UNAVAILABLE`.

## 2. Why can an RPC finish with UNKNOWN?

Some common causes:

- The server throws an exception that is not mapped to a specific gRPC status.
- An integration layer or middleware forwards an exception while losing its original classification.
- The error originates from another system or another process, and the received information is insufficient to choose a more accurate status.
- An unexpected error occurs inside a handler, adapter, or asynchronous processing step.
- The client receives a throwable that does not contain a `StatusException`/`StatusRuntimeException` recognized by gRPC.

For example, Order Service calls Inventory Service to check stock. Inside the handler, an unexpected programming error occurs while processing the result. If the error is not classified and the runtime/integration converts it into `UNKNOWN`, the client only knows the RPC failed. The client should not guess that the SKU is invalid or that the database is definitely down.

**`UNKNOWN` describes our level of knowledge about the error, not the root cause.** Finding the root cause requires cross-referencing server logs, traces, the method, timestamp, status, and correlation ID.

## 3. Distinguishing UNKNOWN from nearby statuses

gRPC statuses carry different semantics. Choosing the right code helps clients know whether to fix the request, check permissions, wait and retry, or investigate the server.

| Status | Value | When it fits |
| --- | ---: | --- |
| `UNKNOWN` | 2 | Insufficient information to classify the error more specifically |
| `INTERNAL` | 13 | The server encountered a serious internal error or unexpected state/invariant violation |
| `UNAVAILABLE` | 14 | The service is temporarily unable to serve; may involve connectivity or overload |
| `DATA_LOSS` | 15 | Unrecoverable data loss or corruption |
| `INVALID_ARGUMENT` | 3 | The request contains invalid arguments |
| `NOT_FOUND` | 5 | The requested resource does not exist |
| `FAILED_PRECONDITION` | 9 | The system is not in the required state to execute the operation |
| `ABORTED` | 10 | The operation was aborted due to a conflict, such as a transaction conflict |
| `DEADLINE_EXCEEDED` | 4 | The RPC did not finish before the deadline |
| `CANCELLED` | 1 | The RPC was cancelled, typically by the caller |

### 3.1. UNKNOWN and INTERNAL

Use `INTERNAL` when the server knows it is an internal error, such as a broken invariant or an implementation bug preventing the server from completing the method. `UNKNOWN` is more appropriate when the error information is insufficient to classify it.

Do not use `UNKNOWN` as a blanket way to hide all exceptions. If you already know what kind of error it is, return the specific status. Conversely, do not attach `INTERNAL` to an error simply because an exception was thrown inside the server; for instance, invalid input data should be mapped to `INVALID_ARGUMENT`.

### 3.2. UNKNOWN and UNAVAILABLE

`UNAVAILABLE` generally indicates that the service is temporarily unable to serve requests or the client cannot establish/maintain the required connection. Some operations can be retried after a backoff if safe.

`UNKNOWN` does not assert that the error is transient. Automatically retrying based solely on this code can duplicate a write operation that was partially executed or already committed.

### 3.3. UNKNOWN and DATA_LOSS

`DATA_LOSS` is reserved for severe data loss or corruption. If the server knows data has been corrupted, it should not downgrade the severity to `UNKNOWN` just to send a generic notice. `UNKNOWN` reflects an inability to classify; `DATA_LOSS` is a specific and critical error category.

## 4. Exception mapping on a Spring gRPC server

In a Spring application, errors can originate from multiple layers:

```text
gRPC handler
    |
    +-- request validation / mapping
    |
    +-- Spring business service
    |
    +-- repository / database / downstream
    |
    +-- exception mapping
    |
    +-- gRPC status + response trailers
```

You should define a clear boundary for translating exceptions into statuses, typically at the gRPC adapter or a shared error-handling mechanism provided by the integration library. Known errors should be mapped explicitly:

| Application error category | Status typically considered |
| --- | --- |
| Invalid argument | `INVALID_ARGUMENT` |
| Resource not found | `NOT_FOUND` |
| Unauthenticated | `UNAUTHENTICATED` |
| Permission denied | `PERMISSION_DENIED` |
| Update conflict | `ABORTED` |
| Business state precondition not met | `FAILED_PRECONDITION` |
| Downstream temporarily unavailable | `UNAVAILABLE` if semantically accurate |
| Identified internal error | `INTERNAL` |
| Unclassifiable after inspection | `UNKNOWN` or a general status matching policy |

### 4.1. Mapping example in a handler

The following snippet illustrates separating input errors, known business errors, and unexpected errors:

```java
@Override
public void checkStock(
        CheckStockRequest request,
        StreamObserver<CheckStockReply> observer) {
    try {
        if (request.getSku().isBlank() || request.getQuantity() <= 0) {
            observer.onError(Status.INVALID_ARGUMENT
                .withDescription("SKU and quantity must be valid")
                .asRuntimeException());
            return;
        }

        int remaining = inventoryQuery.remaining(request.getSku());
        CheckStockReply reply = CheckStockReply.newBuilder()
            .setAvailable(remaining >= request.getQuantity())
            .setRemaining(remaining)
            .build();

        observer.onNext(reply);
        observer.onCompleted();
    } catch (InventoryNotFoundException ex) {
        observer.onError(Status.NOT_FOUND
            .withDescription("Item not found")
            .asRuntimeException());
    } catch (IllegalStateException ex) {
        log.error("Inventory state is invalid", ex);
        observer.onError(Status.INTERNAL
            .withDescription("Unable to complete request")
            .asRuntimeException());
    } catch (Exception ex) {
        log.error("Unexpected error in CheckStock", ex);
        observer.onError(Status.UNKNOWN
            .withDescription("An unknown error occurred")
            .asRuntimeException());
    }
}
```

This example assumes `InventoryNotFoundException`, `inventoryQuery`, and `log` are already defined in the application. It illustrates a classification policy; a project might choose `FAILED_PRECONDITION` or another status depending on its contract. For unexpected errors, server-side logs retain the stack trace for investigation, while the description returned to the client does not expose SQL, table names, internal paths, or secrets.

In some gRPC Java server stacks, unhandled exceptions may be converted to `UNKNOWN` when the runtime translates a throwable to a status. Do not rely on that default behavior: actively map known errors and test the exact status received by the client.

### 4.2. Do not convert every exception into UNKNOWN

A `catch (Exception)` at the handler boundary can act as a last line of defense to avoid leaking error details. However, if every exception becomes `UNKNOWN`, the client loses the ability to distinguish invalid requests, permission failures, conflicts, or service unavailability.

Prioritize:

1. Preserving statuses created intentionally, such as `StatusRuntimeException` or `StatusException`.
2. Mapping known business exceptions to specific statuses.
3. Logging unexpected exceptions with the method and correlation ID.
4. Using `UNKNOWN` only as a fallback when no appropriate classification truly exists.

## 5. Java client reading and diagnosing UNKNOWN

With a blocking stub, an RPC finishing with a status other than `OK` is typically surfaced via `StatusRuntimeException`:

```java
try {
    CheckStockReply reply = inventoryStub
        .withDeadlineAfter(400, TimeUnit.MILLISECONDS)
        .checkStock(request);

    // Process the business response.
} catch (StatusRuntimeException ex) {
    Status.Code code = ex.getStatus().getCode();

    if (code == Status.Code.UNKNOWN) {
        log.warn("Inventory RPC returned UNKNOWN; requestId={}", requestId);
        // Look up traces/logs using requestId; do not retry blindly.
    } else {
        // Handle other statuses according to policy.
    }
}
```

At a minimum, the client should record:

- The service and method called.
- The gRPC status code.
- Applied deadline/call options.
- Non-sensitive correlation ID or trace ID.
- Endpoint/target and client version if compatibility investigation is needed.

Do not log access tokens or full payloads containing sensitive data. If the status description contains information sent by the server, treat it as diagnostic data rather than trustworthy input for access control decisions.

### 5.1. When the throwable is wrapped in multiple layers

An error can pass through `CompletionException`, `ExecutionException`, or framework wrappers. gRPC Java provides `Status.fromThrowable(Throwable)` to search for a status in the cause chain; if no gRPC status is found, the result is typically `UNKNOWN` with the cause attached:

```java
Status status = Status.fromThrowable(error);

if (status.getCode() == Status.Code.UNKNOWN) {
    log.warn("No specific gRPC status found", error);
}
```

This is useful when handling callbacks or futures. However, `UNKNOWN` from `Status.fromThrowable` can also simply mean the original throwable carried no gRPC status; it does not by itself prove the server sent a `grpc-status = 2` trailer. When you need the actual status from the RPC, prefer reading the `StatusRuntimeException`/`StatusException` received by the client and preserving the error context.

## 6. UNKNOWN is not enough to decide on retries

Clients must not follow a rule like "if `UNKNOWN`, retry three times". This code neither tells you whether the error is transient nor reveals how far the server got with side effects.

| Operation type | How to handle when receiving `UNKNOWN` |
| --- | --- |
| Read query, no side effects | May retry under a bounded policy if deadline remains and retrying helps; still requires backoff |
| Idempotent write operation | May retry with the same idempotency key per the contract |
| Non-idempotent write operation | Do not resend blindly; query status or require reconciliation |
| Streaming | Determine which messages were received, where the stream ended, and whether a cursor/resume exists |
| Repeated errors across multiple methods | Investigate server, dependencies, and rollout; do not mask with retries |

For example, `ReserveStock` may have committed to the database while the response was lost. Receiving `UNKNOWN` on the client does not prove the reservation does not exist. You need a `request_id`/idempotency key or a status lookup method before deciding to resend.

## 7. UNKNOWN in streaming RPCs

In server streaming or bidirectional streaming, the client may receive several messages before the stream terminates with `UNKNOWN`.

For example:

```text
Client receives:
  StockUpdate(sequence=1)
  StockUpdate(sequence=2)

RPC ends:
  grpc-status = 2
```

The two updates already sent and received do not disappear, but the overall stream did not complete successfully. The application must define its semantics:

- Can each update be applied immediately as received, or must it wait until the stream finishes?
- Is there a sequence/cursor to identify the last processed point?
- Upon reconnecting, can it resume from the last sequence or will it replay?
- Is the consumer idempotent if it receives duplicate updates?

For critical streams, design cursors/sequences and resume rules at the application layer. gRPC does not automatically persist and replay all messages after a stream fails.

## 8. Observability and root-cause analysis

`UNKNOWN` is a general code, so server logs and distributed tracing are especially important. When this status appears, cross-check:

| Telemetry data | Purpose |
| --- | --- |
| Service/method | Identify the affected RPC |
| Trace ID/correlation ID | Link client, server, and downstream logs |
| Server-side exception class and stack trace | Identify the root error when the status lacks detail |
| gRPC status and description | Verify what information the client actually received |
| Timestamp, latency, and deadline | Distinguish instant failures from failures after long waits |
| Application/contract version | Detect rollouts or client-server version skew |
| Dependency health | Check databases, other services, DNS, proxies, and network |

Metrics should count `UNKNOWN` per service/method and track the rate over time. Do not attach high-cardinality exception messages, request IDs, or user IDs to metric labels. Use logs/traces to investigate individual cases.

If `UNKNOWN` spikes suddenly after a deploy, compare server/client versions, exception mapping changes, dependencies, and logs alongside traces. If only an isolated request fails, inspect that request's data and path before concluding there is a widespread outage.

## 9. Testing UNKNOWN mapping

A test should verify both the status received by the client and server logs/telemetry:

| Scenario | Outcome to verify |
| --- | --- |
| Malformed/semantically invalid request | Server returns `INVALID_ARGUMENT`, not collapsed into `UNKNOWN` |
| Resource does not exist | Status or response matches contract, e.g., `NOT_FOUND` |
| Unexpected exception | Client receives the defined fallback; server log has stack trace and correlation |
| Exception already carrying a gRPC status | Original status is preserved, not overwritten with `UNKNOWN` |
| Client receives wrapped throwable | `Status.fromThrowable` is used properly, without mistaking fallback for a server trailer |
| Streaming emits messages then errors | Client knows the stream did not finish successfully and handles the cursor |
| Write operation loses response | Does not retry in a way that duplicates side effects; looks up via idempotency key |

Unit tests calling the handler directly can verify mapping. Integration tests through a gRPC client/server confirm the status reaches the client as expected. With Spring, you can also test exception advice/interceptors or the mapping mechanism of the starter in use.

## 10. Common design mistakes

| Mistake | Consequence | Better practice |
| --- | --- | --- |
| Using `UNKNOWN` for every exception | Clients cannot distinguish known errors | Map business and infrastructure errors to specific statuses |
| Treating `UNKNOWN` as always transient | Retries can duplicate side effects | Evaluate the method, idempotency, and server state |
| Returning exception messages/stack traces to clients | May leak internal structure or secrets | Log thoroughly on the server, return a safe description |
| Relying on status without a correlation ID | Hard to correlate client and server logs | Propagate trace/correlation metadata |
| Confusing `Status.fromThrowable` fallback with an actual status trailer | Misdiagnoses the error source | Distinguish throwables without status from statuses received from the RPC |
| Grouping `UNKNOWN` into `UNAVAILABLE` | Wrong retries and alerts | Preserve the exact semantics of each status |
| Ignoring errors after a partial stream | Already-received data may be processed inconsistently | Use sequences/cursors and resume rules |

## 11. UNKNOWN troubleshooting checklist

When a client receives `UNKNOWN`, check in order:

1. Identify the service/method, timestamp, endpoint, and correlation/trace ID.
2. Confirm whether `UNKNOWN` is an RPC status received from the server or a fallback from converting a throwable that carried no gRPC status.
3. Find the matching server logs to identify the original exception.
4. Inspect exception mapping in the handler, interceptor, advice, or starter.
5. Check dependencies, database, proxy, and client/server versions around the time of the error.
6. Determine whether the server may already have executed side effects.
7. Retry only if the method is safe, idempotent, or its state has been verified.
8. Add tests so known errors are not turned into `UNKNOWN` and unexpected errors do not leak sensitive information.

## 12. Takeaways

`UNKNOWN` is gRPC status code `2`, used for unknown errors or errors lacking enough information for a more specific classification. It signals that the RPC failed, but it does not reveal the root cause, assert the error is transient, or prove the server did not execute business work.

In Spring gRPC, map known errors to specific statuses, log unexpected exceptions on the server, and return safe descriptions to clients. Clients should combine the status with the method, deadline, trace, and correlation ID to investigate. **Do not retry `UNKNOWN` blindly**, especially for write operations or streams that have already emitted partial data. Keeping a clear boundary between exceptions, gRPC statuses, and business outcomes makes systems easier to diagnose and more reliable.

### References

- [gRPC – Status codes](https://grpc.io/docs/guides/status-codes/)
- [gRPC – Error handling](https://grpc.io/docs/guides/error/)
- [gRPC Java – Status](https://grpc.github.io/grpc-java/javadoc/io/grpc/Status.html)
- [gRPC Java – StatusRuntimeException](https://grpc.github.io/grpc-java/javadoc/io/grpc/StatusRuntimeException.html)
- [gRPC – Retry](https://grpc.io/docs/guides/retry/)
- [gRPC – Metadata](https://grpc.io/docs/guides/metadata/)
