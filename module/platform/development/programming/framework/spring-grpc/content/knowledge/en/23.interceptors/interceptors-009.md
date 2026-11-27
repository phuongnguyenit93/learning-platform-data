# Exception Handling in Interceptors

In Spring gRPC, errors can occur when an interceptor starts a call, when a service processes a request, or inside a callback of a streaming RPC. If every endpoint converts exceptions to gRPC statuses in its own way, clients receive inconsistent errors; if an exception escapes a callback, the transport may return a generic status that is hard to diagnose.

An **exception-mapping interceptor** establishes a centralized boundary to translate synchronous server exceptions into gRPC statuses, preserve explicitly created statuses, and ensure a call is closed only once. However, an interceptor only catches exceptions thrown inside the invocations/callbacks it wraps. Asynchronous work continuing after a callback returns must translate errors itself before calling `StreamObserver.onError`. On the client side, the client receives a status via `onClose`; it never directly receives the Java exception thrown on the server.

## 1. Exceptions and gRPC statuses are two different layers

Exceptions describe errors in Java code; gRPC statuses are RPC outcomes transmitted over the wire. Never let internal exception classes or stack traces become part of the API contract.

| Error in application | Common gRPC status | Meaning to client |
| --- | --- | --- |
| Malformed request or invalid parameter | `INVALID_ARGUMENT` | Client must fix the request |
| Resource not found | `NOT_FOUND` | Resource does not exist or is not visible |
| Unauthenticated caller | `UNAUTHENTICATED` | Valid credentials are required |
| Unauthorized caller | `PERMISSION_DENIED` | Caller is authenticated but not permitted |
| Conflicting business state | `ALREADY_EXISTS` or `FAILED_PRECONDITION` | Client needs to handle current state |
| Temporarily busy/overloaded resource | `RESOURCE_EXHAUSTED` or `UNAVAILABLE` | Can retry according to an appropriate policy |
| Unexpected server error | `INTERNAL` | Server error; do not expose internal details |

Choose statuses according to the semantics clients need to understand, not Java exception class names. For example, `IllegalStateException` does not automatically mean `FAILED_PRECONDITION`; you need to know which business condition failed.

## 2. Separating the exception mapper from the interceptor

The mapper serves as the single place defining how application exceptions translate into statuses. Example:

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusException;
import io.grpc.StatusRuntimeException;

public final class GrpcExceptionMapper {

    public MappedGrpcError map(Throwable error) {
        if (error instanceof StatusRuntimeException statusError) {
            return new MappedGrpcError(
                    statusError.getStatus(),
                    trailersOrEmpty(statusError.getTrailers()));
        }
        if (error instanceof StatusException statusError) {
            return new MappedGrpcError(
                    statusError.getStatus(),
                    trailersOrEmpty(statusError.getTrailers()));
        }
        if (error instanceof ProductNotFoundException) {
            return error(Status.NOT_FOUND, "Product not found");
        }
        if (error instanceof InvalidCatalogRequestException) {
            return error(Status.INVALID_ARGUMENT, "Invalid catalog request");
        }
        if (error instanceof AccessDeniedException) {
            return error(Status.PERMISSION_DENIED, "Permission denied");
        }
        return error(Status.INTERNAL, "Unexpected server error");
    }

    private static MappedGrpcError error(Status status, String description) {
        return new MappedGrpcError(
                status.withDescription(description), new Metadata());
    }

    private static Metadata trailersOrEmpty(Metadata trailers) {
        return trailers == null ? new Metadata() : trailers;
    }

    public record MappedGrpcError(Status status, Metadata trailers) {
    }
}
```

`ProductNotFoundException`, `InvalidCatalogRequestException`, and `AccessDeniedException` are illustrative exceptions defined or used by the application. The mapper preserves status/trailers when downstream code intentionally threw `StatusException` or `StatusRuntimeException`; domain exceptions are mapped according to policy; unrecognized errors return `INTERNAL` with a safe description.

Do not use `Status.fromThrowable(error)` as the sole policy for all exceptions. That helper is useful for finding a status in a cause chain, but ordinary Java exceptions carrying no gRPC status become `UNKNOWN`. An explicit mapper distinguishes known business errors from unexpected server failures.

## 3. Server interceptor translating synchronous exceptions

A server interceptor needs to guard two regions:

1. `next.startCall`, because an inner interceptor or service binding can throw immediately while creating the listener.
2. Callbacks on `ServerCall.Listener`, because request handling code can throw when `onMessage`, `onHalfClose`, or another callback runs.

The concise example below wraps both `ServerCall` and the listener, using a per-call flag to avoid closing a call twice:

```java
import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class ExceptionMappingServerInterceptor
        implements ServerInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(ExceptionMappingServerInterceptor.class);

    private final GrpcExceptionMapper mapper;

    public ExceptionMappingServerInterceptor(GrpcExceptionMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        AtomicBoolean closed = new AtomicBoolean();
        Consumer<Throwable> fail = error -> {
            if (!closed.compareAndSet(false, true)) {
                log.debug("Ignoring exception after RPC was closed");
                return;
            }
            GrpcExceptionMapper.MappedGrpcError mapped = mapper.map(error);
            call.close(mapped.status(), mapped.trailers());
        };

        ServerCall<ReqT, RespT> wrappedCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        if (closed.compareAndSet(false, true)) {
                            super.close(status, trailers);
                        }
                    }
                };

        final ServerCall.Listener<ReqT> listener;
        try {
            listener = next.startCall(wrappedCall, headers);
        } catch (RuntimeException error) {
            fail.accept(error);
            return new ServerCall.Listener<>() {};
        }

        Consumer<Runnable> guard = action -> {
            try {
                action.run();
            } catch (RuntimeException error) {
                fail.accept(error);
            }
        };

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onMessage(ReqT message) {
                guard.accept(() -> super.onMessage(message));
            }

            @Override
            public void onHalfClose() {
                guard.accept(super::onHalfClose);
            }

            @Override
            public void onReady() {
                guard.accept(super::onReady);
            }

            @Override
            public void onComplete() {
                guard.accept(super::onComplete);
            }

            @Override
            public void onCancel() {
                closed.set(true);
                try {
                    super.onCancel();
                } catch (RuntimeException error) {
                    log.debug("Exception during cancelled RPC callback", error);
                }
            }
        };
    }
}
```

Key design decisions:

- `closed` is per-RPC state, not a shared field on the singleton interceptor.
- `close` is wrapped so the interceptor knows when the call has already ended normally or with a status.
- Exceptions in `startCall` or listener callbacks are mapped to a status and close the call if not yet closed.
- `onCancel` marks the call terminal; never attempt to send another status after the client cancels.
- Exceptions raised after the call is already closed are never used to close it a second time.

This is a synchronous exception-handling pattern at the callback boundary. In a real deployment, decide on logging/metrics for exceptions ignored post-termination and test against your gRPC Java version. Do not catch broad `Throwable` and swallow JVM `Error`s like `OutOfMemoryError`; serious JVM errors must follow runtime policy.

## 4. Exceptions in asynchronous tasks must be handled at completion

An interceptor cannot catch exceptions occurring after a callback has returned, for example:

```java
executor.execute(() -> {
    Product product = catalogService.loadProduct(productId);
    observer.onNext(toProto(product));
    observer.onCompleted();
});
```

If `loadProduct` throws on the executor, that stack is no longer inside the `onMessage` call wrapped by the interceptor. You must translate the error directly inside the task:

```java
executor.execute(() -> {
    try {
        Product product = catalogService.loadProduct(productId);
        observer.onNext(toProto(product));
        observer.onCompleted();
    } catch (RuntimeException error) {
        GrpcExceptionMapper.MappedGrpcError mapped =
                exceptionMapper.map(error);
        observer.onError(mapped.status().asRuntimeException(
                mapped.trailers()));
    }
});
```

With futures or reactive pipelines, place mapping in `exceptionally`, `onErrorMap`, or the corresponding error handler before completing `StreamObserver`. Guarantee a single terminal signal: never call `onError` after `onCompleted`, and never emit messages after a terminal signal.

## 5. Preserving intentionally created gRPC errors

A service may explicitly return a status:

```java
observer.onError(
        Status.NOT_FOUND
                .withDescription("Product not found")
                .asRuntimeException());
```

This is not an unexpected exception to overwrite with `INTERNAL`. The interceptor should preserve status codes and trailers explicitly set by the service. If structured error details are needed, use standardized trailers such as `google.rpc.Status` and detail types supported by clients; never stuff stack traces or sensitive data into descriptions.

When a service calls `StreamObserver.onError(...)`, the status is sent as the RPC's terminal signal rather than thrown out of the listener callback. Thus, an exception-mapping interceptor does not remap that path; the service or error handler calling `onError` must choose the right status there.

`StatusException` is a checked exception; `StatusRuntimeException` is unchecked. Both carry a status and optionally trailers. When translating in a mapper, preserve trailers if they contain approved error details. Allow only controlled keys/details, because trailers are also sent back to the client.

## 6. Clients receive statuses, not server exceptions

With an async stub, error outcomes arrive in `ClientCall.Listener.onClose` as a `Status`:

```java
@Override
public void onClose(Status status, Metadata trailers) {
    if (!status.isOk()) {
        log.warn("Catalog RPC failed with status={}", status.getCode());
    }
    delegate.onClose(status, trailers);
}
```

Blocking stubs typically throw `StatusRuntimeException` for non-`OK` statuses; future stubs complete the future exceptionally. A client interceptor should observe and preserve the status/trailers so callers handle them per contract.

If statuses need to be translated into client-side domain exceptions, do so at the adapter/application boundary calling the stub. Do not convert `NOT_FOUND` to `INTERNAL` inside a client interceptor just to unify logs; that strips semantics the application needs.

## 7. Status mapping and interceptor ordering

A server chain is commonly structured like:

```text
Tracing / Context
  -> Metrics / Logging
      -> Exception mapping
          -> Authentication / Authorization
              -> Service handler
```

The exception mapper needs to wrap interceptors/handlers that may throw exceptions so it can translate errors before the call closes. Metrics/logging outside the mapper can then observe the final mapped status. Actual ordering depends on gRPC Java and Spring gRPC interceptor registration; verify with integration tests rather than inferring from bean order.

An authentication interceptor may explicitly call `close(UNAUTHENTICATED)` without throwing an exception; the exception mapper does not need to alter that status. Outer metrics can still record it when the chain is composed properly.

## 8. Securing error information

Status descriptions and trailers are sent to the client. Only expose content the client needs in order to handle the error:

- Use short, stable descriptions such as `Product not found` or `Invalid request`.
- Never send stack traces, SQL, table names, file paths, internal hostnames, or tokens.
- Log stack traces in server logs with correlation/trace IDs after scrubbing credentials and sensitive data.
- Do not log full trailers if they might contain error details or caller-supplied data.
- Return appropriate statuses so clients make sound retry decisions—for example, never blindly retry `INVALID_ARGUMENT` or `PERMISSION_DENIED`.

For transient infrastructure errors, choose consistent statuses and retry policies. Do not map every exception to `UNAVAILABLE`, because clients may retry an operation that cannot succeed; likewise, do not return `INTERNAL` for request errors the client can fix.

## 9. Testing exception mapping

| Test case | Result to verify |
| --- | --- |
| Domain not-found exception | Client receives `NOT_FOUND` |
| Invalid request | Client receives `INVALID_ARGUMENT` |
| Invalid credentials | Preserves `UNAUTHENTICATED` returned by auth interceptor |
| Unauthorized caller | Preserves `PERMISSION_DENIED` |
| `StatusRuntimeException` with trailers | Status and trailers preserved per policy |
| Unexpected runtime exception | Client receives `INTERNAL` with safe description |
| Exception in listener callback | Call closes with mapped status, does not hang |
| Exception in executor/future | Async error handler emits exactly one terminal signal |
| Error occurs after call already closed | Call is not closed a second time |
| Multiple concurrent RPCs | Per-call state and statuses do not mix |
| Logs/trailers | No leaked stack traces or credentials |

Test the interceptor with an in-process server/channel to check wire statuses. Unit-test the mapper separately for each exception type; run Spring integration tests to confirm the interceptor is actually registered. Do not test only the mapper function directly and conclude the entire RPC pipeline is protected.

## 10. Implementation checklist

- [ ] Maintain a centralized mapper for domain exceptions and unexpected errors.
- [ ] Preserve explicitly constructed `StatusException`/`StatusRuntimeException`.
- [ ] Use `INVALID_ARGUMENT`, `NOT_FOUND`, `UNAUTHENTICATED`, `PERMISSION_DENIED`, and `INTERNAL` semantically.
- [ ] Wrap `next.startCall` and the required listener callbacks.
- [ ] Use per-call state to guarantee a call is closed at most once.
- [ ] Do not catch/swallow JVM `Error`s.
- [ ] Handle exceptions in executors/futures/reactive pipelines where tasks complete.
- [ ] Never include stack traces, SQL, or sensitive data in statuses/trailers.
- [ ] Client interceptors preserve statuses; translate to domain exceptions at the application adapter if needed.
- [ ] Test statuses, trailers, cancellation, async failures, concurrency, and Spring registration.

**Self-check**

**Question 1.** Why shouldn't every exception be converted to `INTERNAL`?

*Answer:* Clients must distinguish bad requests, missing resources, missing authentication, lack of permission, and server errors. Mapping everything to one generic code destroys semantics and causes clients to react incorrectly.

**Question 2.** Can `Status.fromThrowable` replace an exception mapper?

*Answer:* No. It searches for a gRPC status in the cause chain; ordinary Java exceptions become `UNKNOWN`. An explicit mapper is needed to translate domain exceptions and unexpected failures.

**Question 3.** Can a server interceptor catch an exception thrown from an executor after the listener callback has returned?

*Answer:* No. The task runs outside the callback boundary; you must catch and translate errors at executor/future/reactive completion before calling `StreamObserver.onError`.

**Question 4.** In what form does a client async interceptor receive server errors?

*Answer:* The `onClose` callback receives `Status` and trailers. Blocking stubs typically convert error statuses into a `StatusRuntimeException` for the caller.

**Question 5.** Why is a per-call flag needed when translating exceptions inside a listener?

*Answer:* The call may already be closed or cancelled before another callback throws. A per-call flag prevents the interceptor from calling close a second time and avoids mixing state across concurrent RPCs.

An exception-mapping interceptor standardizes synchronous error handling at the gRPC boundary, though it does not replace error handling inside asynchronous tasks. Use a centralized mapper, preserve explicit statuses, close each call once, and withhold internal details; clients then receive predictable errors to guide their handling logic.
