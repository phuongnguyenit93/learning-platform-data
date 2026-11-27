# Swallowing Status Codes into INTERNAL

## 1. Why is losing a gRPC status a serious mistake?

In **SPRING_GRPC**, the gRPC status is part of the contract between server and client. The status code tells the caller how the RPC failed so it can decide whether to fix the request, re-authenticate, wait for a dependency to recover, retry, or abort the operation.

A common mistake occurs when the server receives an error that already carries a specific status, catches the exception, and wraps it into a generic `INTERNAL` error. For instance, a downstream service returns `UNAVAILABLE`, an application wrapper catches it and throws a new `RuntimeException`; the exception mapper fails to recognize the cause and returns `INTERNAL`. The client loses the signal that the failure might be transient and recoverable.

Consequences:

- The client cannot distinguish request errors from infrastructure errors.
- Retry policies misbehave because `UNAVAILABLE`/`ABORTED`/`RESOURCE_EXHAUSTED` are turned into `INTERNAL`.
- `DEADLINE_EXCEEDED` or `CANCELLED` gets masked, causing callers to continue work that is no longer useful.
- Rich error details and metadata trailers may be lost.
- Dashboards show `INTERNAL` spikes without revealing where the failure originated.
- Clients may retry permanent business errors or fail to retry transient errors that should recover.

**`INTERNAL` is not the default status for every exception.** Use it only for unexpected errors for which the server has no specific mapping. When an exception already carries a gRPC status, preserve that status and its trailers across processing layers.

## 2. Status codes are contracts governing client behavior

Clients rely on status codes to decide their next step. Key codes include:

| Status | Typical meaning | Action callers typically consider |
| --- | --- | --- |
| INVALID_ARGUMENT | Invalid request | Fix input, do not retry the exact request |
| NOT_FOUND | Resource does not exist | Verify ID or handle missing resource |
| ALREADY_EXISTS | Resource already exists | Read existing resource or choose another key |
| PERMISSION_DENIED | Caller lacks permission | Do not retry unless permissions change |
| UNAUTHENTICATED | Missing/invalid authentication | Refresh credentials per policy |
| FAILED_PRECONDITION | Current state does not allow the operation | Wait or update business state |
| ABORTED | Workflow/concurrency conflict | Re-read and retry the entire workflow if contract permits |
| RESOURCE_EXHAUSTED | Quota or resource limit exhausted | Back off, shed load, or wait for quota |
| UNAVAILABLE | Service/dependency temporarily unavailable | Can retry with backoff and deadline |
| DEADLINE_EXCEEDED | Time budget exhausted | Determine outcome; commands require idempotency |
| CANCELLED | Caller cancelled the call | Stop cancellable work |
| INTERNAL | Unexpected internal error | Investigate server; do not retry by default |

Status does not merely serve error display. It drives retries, circuit breakers, telemetry, alerts, and how clients recover.

## 3. Anti-pattern: catching every exception and returning INTERNAL

Broken mapper example:

```java
public StatusRuntimeException toStatus(Throwable error) {
    return Status.INTERNAL
        .withDescription("Request failed")
        .asRuntimeException();
}
```

This turns every error into the exact same status, including `RequestValidationException`, `ResourceNotFoundException`, downstream `StatusRuntimeException`, and deadline errors.

An equally dangerous variant:

```java
try {
    return downstreamStub
        .withDeadlineAfter(300, TimeUnit.MILLISECONDS)
        .getOrder(request);
} catch (Exception ex) {
    throw new RuntimeException("Order lookup failed");
}
```

The new exception does not intentionally preserve the status as part of the contract. If the cause is dropped or the mapper only inspects the outermost exception class, `UNAVAILABLE`/`DEADLINE_EXCEEDED` can turn into `INTERNAL`. Generic messages also strip crucial diagnostic context.

Do not catch `Exception` or `Throwable` just to convert everything into `INTERNAL`. Catch only the error types that the layer can actually handle; unhandled errors should propagate along with their cause.

## 4. Preserve `StatusRuntimeException` and `StatusException`

gRPC Java uses `StatusRuntimeException` and `StatusException` to carry the status, description, and optional metadata trailers.

If the application or an adapter receives either of these, it should generally pass the original exception through:

```java
public Throwable preserveOrMap(Throwable error) {
    if (error instanceof StatusRuntimeException
            || error instanceof StatusException) {
        return error;
    }

    return mapApplicationError(error);
}
```

Returning the original exception preserves the original status and trailers. Do not create a new `Status.INTERNAL` simply because the exception was thrown by another service or a client stub.

If additional log context is needed, log the method, correlation ID, and cause on the server; replacing the exception is unnecessary. If a wrapper conversion is genuinely required, preserve the status code, publicly safe description, and trailers per contract.

## 5. Handling exceptions wrapped in `CompletionException` or `ExecutionException`

In asynchronous code, errors can be wrapped:

- `CompletableFuture` typically completes exceptionally with `CompletionException`.
- `Future.get()` throws `ExecutionException`.
- Reflection can wrap errors in `InvocationTargetException`.
- Framework/application wrappers can create another exception while retaining the cause.

If the mapper only checks the outermost class, it can miss a `StatusRuntimeException` in the cause chain.

One approach is to search the cause chain for a status exception before classifying domain exceptions:

```java
private Throwable findGrpcStatus(Throwable error) {
    Set<Throwable> seen =
        Collections.newSetFromMap(new IdentityHashMap<>());

    Throwable current = error;
    while (current != null && seen.add(current)) {
        if (current instanceof StatusRuntimeException
                || current instanceof StatusException) {
            return current;
        }
        current = current.getCause();
    }
    return null;
}
```

Then the mapper prioritizes preserving an existing status:

```java
public Throwable toGrpcError(Throwable error) {
    Throwable grpcStatus = findGrpcStatus(error);
    if (grpcStatus != null) {
        return grpcStatus;
    }

    Throwable cause = unwrapAsyncWrappers(error);
    return mapApplicationError(cause);
}
```

`unwrapAsyncWrappers` should only unwrap known technical wrappers and only when a cause exists. Do not walk the cause chain endlessly or discard the root exception arbitrarily. If an application wrapper carries its own business meaning, handle it according to that wrapper's type.

gRPC Java also provides `Status.fromThrowable` and `Status.trailersFromThrowable` to extract status/trailers from throwables containing a gRPC status in the cause chain. However, do not treat an `UNKNOWN` result from an ordinary throwable as proof that the original error was deliberately `UNKNOWN`; distinguish intentional gRPC errors from plain Java exceptions.

## 6. Map domain exceptions by type

Business exceptions that do not already carry a gRPC status can be mapped at the transport boundary:

```java
public Throwable mapApplicationError(Throwable error) {
    if (error instanceof RequestValidationException) {
        return Status.INVALID_ARGUMENT
            .withDescription("Request validation failed")
            .asRuntimeException();
    }

    if (error instanceof ResourceNotFoundException) {
        return Status.NOT_FOUND
            .withDescription("Resource not found")
            .asRuntimeException();
    }

    if (error instanceof BusinessPreconditionException) {
        return Status.FAILED_PRECONDITION
            .withDescription("Operation is not allowed")
            .asRuntimeException();
    }

    if (error instanceof AccessDeniedException) {
        return Status.PERMISSION_DENIED
            .withDescription("Permission denied")
            .asRuntimeException();
    }

    if (error instanceof TransientDependencyException) {
        return Status.UNAVAILABLE
            .withDescription("Dependency temporarily unavailable")
            .asRuntimeException();
    }

    return Status.INTERNAL
        .withDescription("Unexpected server error")
        .asRuntimeException();
}
```

This is an example policy; exception types and statuses must match your system contract. Do not map every `DataAccessException` to `UNAVAILABLE`: constraint violations, SQL syntax errors, or mapping bugs can be permanent errors. Likewise, do not map every `IllegalStateException` to `FAILED_PRECONDITION` if it is actually a programming bug.

Processing order matters: preserve an existing gRPC status first; next map business exceptions; finally fall back to `INTERNAL` only for unrecognized errors.

## 7. Distinguish server errors from downstream errors

A **SPRING_GRPC** service may call other services. When a downstream returns a status, the intermediary service must decide whether to propagate it as-is or translate it according to the current API's contract.

Preserving the status is usually appropriate when:

- The intermediary RPC acts as a proxy/facade and the downstream status has the same meaning to the caller.
- `UNAVAILABLE` or `DEADLINE_EXCEEDED` reflects a dependency issue the caller needs to know about.
- Rich details are meaningful and safe to forward.

Intentional translation is appropriate when:

- The current API has its own contract and should not expose internal details.
- The downstream status does not share the same semantics as the public API.
- Internal domain errors need to map to stable public statuses.

When translating, do not turn every downstream error into `INTERNAL`. For example, a downstream `NOT_FOUND` might correspond to `ResourceNotFound` in the current API; downstream `PERMISSION_DENIED` may need handling at the authorization boundary; downstream `UNAVAILABLE` is usually still a temporary dependency failure.

Never forward raw internal descriptions or trailers to public clients if they contain hostnames, SQL, service names, tenant data, or sensitive operational details. You can preserve the status code while replacing descriptions/details with controlled public content.

## 8. Preserve metadata trailers and rich error details

A gRPC error can carry trailers in addition to a status code and description. Applications can use the rich error model such as `google.rpc.BadRequest`, `ErrorInfo`, or `RetryInfo` to supply field violations, reasons, or retry delays.

If a mapper constructs a new exception without transferring trailers, the client loses those details. When preserving an error as-is, pass the original `StatusException`/`StatusRuntimeException`. When translating, build new details only after deciding the contract and vetting publicly permitted data.

Example creating a rich `INVALID_ARGUMENT` detail:

```java
BadRequest detail = BadRequest.newBuilder()
    .addFieldViolations(
        BadRequest.FieldViolation.newBuilder()
            .setField("customer_id")
            .setDescription("customer_id is required")
    )
    .build();

com.google.rpc.Status richStatus =
    com.google.rpc.Status.newBuilder()
        .setCode(Code.INVALID_ARGUMENT_VALUE)
        .setMessage("Request validation failed")
        .addDetails(Any.pack(detail))
        .build();

throw StatusProto.toStatusRuntimeException(richStatus);
```

Compatible clients can use `StatusProto.fromThrowable` to read details. Even if a client does not understand the rich detail type, it must still handle the base status code. Never include sensitive data or stack traces inside error details.

## 9. Do not swallow statuses in asynchronous callbacks

With `CompletableFuture`, errors can pass through `exceptionally`/`handle` and get converted into a default value or a generic `RuntimeException`:

```java
future.exceptionally(error -> {
    log.error("Downstream failed", error);
    throw new CompletionException(error);
});
```

If you only log and return `null`/a default, the caller may receive a false success response. If you wrap the error without keeping its cause, the original gRPC status vanishes.

In an async gRPC service, when completing with an error, pass the preserved/mapped throwable to `observer.onError`:

```java
future.whenComplete((reply, error) -> {
    if (error != null) {
        observer.onError(exceptionMapper.toGrpcError(error));
        return;
    }

    observer.onNext(reply);
    observer.onCompleted();
});
```

Ensure there is only one terminal path per RPC. Never call `onNext` or `onCompleted` after `onError`; never call `onError` multiple times from competing callbacks. If the future was cancelled because the client cancelled, preserve `CANCELLED` semantics rather than turning it into `INTERNAL`.

## 10. Streaming RPCs must also preserve statuses

With server-streaming or bidirectional streaming, an error can occur after the server has already sent some messages. In that case, `observer.onError` terminates the stream with a status; already-sent messages cannot be retracted.

Guidelines:

- Do not send a generic `INTERNAL` if the root error already has a specific status.
- Call `onError` exactly once and stop the producer.
- Cancel upstream subscriptions/tasks when the client cancels.
- Never send further messages after a terminal signal.
- Document partial-result semantics in the API; an error status does not mean messages already sent were not processed by the client.
- For command streams with side effects, use sequence numbers/idempotency/checkpoints so the client knows what committed.

Do not attempt to "fix" a failed stream by sending an error message inside the response payload and calling `onCompleted` if the contract specifies transport errors must be gRPC statuses. Use status/trailers consistently with the client contract.

## 11. Cancellation and deadlines are not `INTERNAL`

Deadline expirations and client cancellations are normal occurrences in distributed systems, not necessarily server bugs:

- `DEADLINE_EXCEEDED`: caller exhausted its time budget.
- `CANCELLED`: caller no longer wishes to continue the call.
- `UNAVAILABLE`: service/dependency is temporarily unavailable.
- `RESOURCE_EXHAUSTED`: resource/quota limit reached.

Do not catch these errors and return `INTERNAL`. Preserving the status enables clients to stop, retry, or shed load appropriately.

If cancellation occurs in a worker thread, propagate the cancellation signal and stop cancellable work. JDBC drivers may need a separate query timeout; gRPC cancellation does not guarantee an in-flight query stops immediately. Never assume a command did not commit solely because the client cancelled.

## 12. Logging and observability during error mapping

Good status mapping must be observable from server to client. Record:

- RPC method and final status code.
- Original exception class and cause chain with sensitive data masked.
- Downstream target/service when the failure originates from a dependency.
- Correlation/trace ID.
- Remaining deadline or elapsed processing time at failure.
- Retry attempt and dependency outcome.
- Rich detail type or application error code if used by the contract.

Do not log bearer tokens, private keys, full request payloads, or SQL containing sensitive data. Status descriptions returned to clients should be short, stable, and free of stack traces or internal hostnames.

Do not alert solely on total exception count. Track status rates per method and dependency: rising `INTERNAL` may indicate a new bug; rising `UNAVAILABLE` may indicate an outage; sudden `INVALID_ARGUMENT` spikes may indicate a client regression.

## 13. Testing status mapping end-to-end

Unit testing the mapper alone is not enough. Invoke RPCs through a real server or integration harness to verify the actual status reaching the client:

| Scenario | What to verify |
| --- | --- |
| Application validation exception | Client receives INVALID_ARGUMENT |
| Resource missing | Client receives NOT_FOUND |
| Business precondition fails | Client receives FAILED_PRECONDITION |
| Downstream StatusRuntimeException UNAVAILABLE | Status preserved or translated per public contract |
| StatusException with trailers | Rich details preserved when policy requires |
| CompletionException wrapping status | Mapper finds the right status in cause chain |
| Unknown Java exception | Only this case falls back to INTERNAL |
| Client deadline expires | DEADLINE_EXCEEDED is not converted to INTERNAL |
| Client cancels | CANCELLED is preserved and work stops as possible |
| Stream fails after some messages | onError called once; no messages after terminal signal |
| Error description | Free of SQL, stack traces, secrets, or internal hostnames |

Example client-side assertion:

```java
StatusRuntimeException error = assertThrows(
    StatusRuntimeException.class,
    () -> blockingStub.getOrder(request)
);

assertEquals(
    Status.Code.UNAVAILABLE,
    Status.fromThrowable(error).getCode()
);
```

With rich details, verify both the status code and publicly allowed detail type/content. Test real wrapper errors like `CompletionException` to avoid verifying the mapper solely against direct exceptions.

## 14. Review checklist

- Do not catch all exceptions and convert them to `INTERNAL`.
- `StatusRuntimeException` and `StatusException` are preserved when the contract allows.
- The cause chain is inspected when errors pass through async/framework wrappers.
- Status codes and trailers are not lost during unwrapping or translation.
- Domain exceptions are mapped by type and public API contract.
- `INTERNAL` is used only for unexpected errors without a specific mapping.
- Downstream statuses are preserved or intentionally translated without masking outages.
- Rich error details contain no secrets or stack traces.
- Async callbacks do not swallow errors or return fake success responses.
- Streaming observers emit only one terminal signal.
- `DEADLINE_EXCEEDED` and `CANCELLED` are not turned into `INTERNAL`.
- Logs include correlation, method, status, and safe causes.
- gRPC integration tests cover direct, wrapped, async, and streaming errors.

In **SPRING_GRPC**, swallowing status codes and returning `INTERNAL` deprives clients of the ability to classify errors and recover properly. Preserve `StatusException`/`StatusRuntimeException` along with trailers whenever possible, inspect cause chains of async wrappers, and map domain exceptions only at the transport boundary. Reserve `INTERNAL` for truly unexpected failures, and verify final statuses with integration tests through a gRPC server.
