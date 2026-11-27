# Global server exception handling

**Chapter:** Error handling  
**Scope:** Spring gRPC (SPRING_GRPC) using Protocol Buffers contracts, generated Java code, and unary or streaming RPCs. This lesson focuses on a centralized server-side exception handling mechanism, so errors raised at the RPC boundary are classified consistently and converted into safe gRPC statuses.

## 1. Why is centralized exception handling needed?

A service may have many RPCs: finding customers, creating orders, updating inventory, uploading batches, or streaming data. If every handler writes its own `try/catch` block, error mapping easily becomes inconsistent:

- The same domain error returns `NOT_FOUND` in one RPC and `INTERNAL` in another.
- An unexpected exception has its raw `getMessage()` sent to the client.
- A status intentionally created by a lower layer gets overwritten by another status.
- A streaming callback emits terminal signals multiple times.
- A method forgets to catch an error and ends with a default status outside the API contract.

Global server exception handling puts error classification logic at a shared boundary. Each handler remains responsible for business logic; the centralized mechanism only converts errors into the final RPC status and metadata.

```text
Unary / streaming gRPC service
             |
             v
      Application / domain
             |
             v
      Exception boundary
             |
      +------+------------------+
      |                         |
      v                         v
 Known exception           Unknown exception
      |                         |
      v                         v
 Status mapper             Controlled internal log
      |                         |
      +------------+------------+
                   |
                   v
       ServerCall.close(status, trailers)
                   |
                   v
             gRPC client
```

A global handler does not replace validation, authorization, or domain error handling. It provides a consistent place for classified errors to exit the server.

## 2. Classifying errors in a shared mapper

The mapper should follow clear rules:

1. If the exception already contains an intentionally created gRPC status, preserve its code and appropriate trailers.
2. If it is a known domain or dependency error, map it according to API semantics.
3. If it is an unexpected error, log diagnostics on the server and return `INTERNAL` with a generic description.

Example mapper:

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusException;
import io.grpc.StatusRuntimeException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class GrpcExceptionMapper {

    private static final Logger log =
            LoggerFactory.getLogger(GrpcExceptionMapper.class);

    public StatusRuntimeException map(Throwable failure) {
        // Preserve status already created by a lower layer, even when the exception is wrapped.
        for (Throwable current = failure;
                current != null;
                current = current.getCause()) {
            if (current instanceof StatusRuntimeException
                    || current instanceof StatusException) {
                Status status = Status.fromThrowable(current);
                Metadata trailers =
                        Status.trailersFromThrowable(current);
                return trailers == null
                        ? status.asRuntimeException()
                        : status.asRuntimeException(trailers);
            }
        }

        if (hasCause(failure, CustomerNotFoundException.class)) {
            return Status.NOT_FOUND
                    .withDescription("Customer not found")
                    .asRuntimeException();
        }
        if (hasCause(failure, RequestValidationException.class)) {
            return Status.INVALID_ARGUMENT
                    .withDescription("Invalid request data")
                    .asRuntimeException();
        }
        if (hasCause(failure, ConcurrentUpdateException.class)) {
            return Status.ABORTED
                    .withDescription("Data has changed; reload and retry")
                    .asRuntimeException();
        }
        if (hasCause(failure, DependencyUnavailableException.class)) {
            return Status.UNAVAILABLE
                    .withDescription("Dependent service is temporarily unavailable")
                    .asRuntimeException();
        }

        // Only unclassified errors use INTERNAL.
        // Do not put exception messages or stack traces into the response.
        log.error("Unhandled exception at gRPC boundary, type={}",
                failure.getClass().getName(), failure);
        return Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException();
    }

    private boolean hasCause(
            Throwable failure,
            Class<? extends Throwable> expectedType) {
        for (Throwable current = failure;
                current != null;
                current = current.getCause()) {
            if (expectedType.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
```

The domain exceptions in the example represent error types defined in the application layer. Replace them with your project's real exceptions; do not map every `RuntimeException` or every `DataAccessException` to the same status.

The mapper does not use `failure.getMessage()` as the description. Public messages should be stable and free of SQL, tokens, PII, or infrastructure details. If a support reference or error code is needed, add controlled trailers.

## 3. Using ServerInterceptor as a server-wide boundary

gRPC Java provides `ServerInterceptor` to wrap RPC handling. An interceptor can:

- Catch exceptions thrown synchronously when initializing the handler.
- Wrap `ServerCall.Listener` to catch synchronous exceptions in callbacks such as `onMessage`, `onHalfClose`, and `onReady`.
- Close the call with the status produced by the mapper.

The example below illustrates a general interceptor. The wrapper tracks closed state so `ServerCall.close()` is never called twice:

```java
import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import java.util.concurrent.atomic.AtomicBoolean;

public final class GlobalExceptionInterceptor
        implements ServerInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(GlobalExceptionInterceptor.class);

    private final GrpcExceptionMapper exceptionMapper;

    public GlobalExceptionInterceptor(
            GrpcExceptionMapper exceptionMapper) {
        this.exceptionMapper = exceptionMapper;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        AtomicBoolean closed = new AtomicBoolean(false);

        ServerCall<ReqT, RespT> guardedCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        if (closed.compareAndSet(false, true)) {
                            super.close(status, trailers);
                        }
                    }
                };

        try {
            ServerCall.Listener<ReqT> delegate =
                    next.startCall(guardedCall, headers);

            return new ForwardingServerCallListener
                    .SimpleForwardingServerCallListener<>(delegate) {

                private void invoke(Runnable callback) {
                    try {
                        callback.run();
                    } catch (RuntimeException failure) {
                        StatusRuntimeException mapped =
                                exceptionMapper.map(failure);
                        Metadata trailers =
                                Status.trailersFromThrowable(mapped);
                        guardedCall.close(
                                mapped.getStatus(),
                                trailers == null ? new Metadata() : trailers);
                    }
                }

                @Override
                public void onMessage(ReqT message) {
                    invoke(() -> delegate.onMessage(message));
                }

                @Override
                public void onHalfClose() {
                    invoke(delegate::onHalfClose);
                }

                @Override
                public void onReady() {
                    invoke(delegate::onReady);
                }

                @Override
                public void onCancel() {
                    // Call was cancelled by client: only record/clean up,
                    // do not attempt to send another status on an already-cancelled call.
                    try {
                        delegate.onCancel();
                    } catch (RuntimeException cleanupError) {
                        log.warn("Exception during gRPC cancellation cleanup",
                                cleanupError);
                    }
                }

                @Override
                public void onComplete() {
                    try {
                        delegate.onComplete();
                    } catch (RuntimeException cleanupError) {
                        log.warn("Exception during gRPC completion callback",
                                cleanupError);
                    }
                }
            };
        } catch (RuntimeException failure) {
            StatusRuntimeException mapped =
                    exceptionMapper.map(failure);
            Metadata trailers = Status.trailersFromThrowable(mapped);
            guardedCall.close(
                    mapped.getStatus(),
                    trailers == null ? new Metadata() : trailers);
            return new ServerCall.Listener<>() {};
        }
    }
}
```

This is an illustrative pattern for synchronous exception interception. In production, add logging for cleanup failures, verify the behavior of the server builder in use, and ensure interceptors are registered in the right order. Do not catch `Error` or serious JVM errors and pretend the RPC can continue normally.

### Why must terminal state be tracked?

An RPC has only one final result. Once the service has called `onError` or `onCompleted`, the interceptor must not try to close the call a second time. The `guardedCall` wrapper uses an `AtomicBoolean` to protect `close` when callbacks and cancellation race.

Nor should the interceptor emit a response message on behalf of the service. Its job is to turn errors into the final status; producing business responses belongs to the handler.

## 4. Registering the global interceptor in Spring gRPC

Making the interceptor a Spring bean only provides an instance; you must **register the instance into the server interceptor chain** so every RPC passes through it.

In Spring gRPC, perform registration using the server configuration extension point of the starter/version in use (a server configurer or global interceptor registration if provided by the starter). In gRPC Java terms, the final operation is equivalent to:

```java
serverBuilder.intercept(globalExceptionInterceptor);
```

Do not assume a `@Component` bean automatically becomes a global interceptor if the starter has no corresponding discovery mechanism. Also do not use Spring MVC's `@ControllerAdvice` as if it automatically catches exceptions from gRPC services; the two request types run through two different execution pipelines.

If a project uses a starter with dedicated gRPC annotations or advice, you can use that API instead of a hand-written interceptor. Verify exception-catching scope, interceptor ordering, and streaming callback support for your exact version; do not mix multiple mechanisms that both close the same call.

## 5. Async errors must be handled where they occur

A global interceptor catches exceptions only while execution is still on the call stack wrapped by the interceptor. It **cannot automatically catch every error occurring on any thread**.

For example, a service offloads work to an executor:

```java
executor.execute(() -> {
    try {
        Result result = applicationService.process(request);
        responseObserver.onNext(toProto(result));
        responseObserver.onCompleted();
    } catch (Exception failure) {
        responseObserver.onError(exceptionMapper.map(failure));
    }
});
```

Exceptions in async tasks must be caught inside the task and forwarded via `responseObserver.onError()`. If an exception simply escapes the thread pool, the original interceptor is no longer on the call stack to convert it into a gRPC status.

With streaming RPCs, the same principle applies to:

- Errors in the `onNext()` callback: catch inside the callback or let the interceptor catch if the callback runs synchronously inside the wrapped listener.
- Errors when aggregating in `onCompleted()`: convert to a terminal status before sending a receipt.
- Errors in futures, schedulers, or reactive pipelines: attach an error handler in that pipeline and terminate the response observer once.
- Client cancellation/deadline: stop work and clean up; do not send new responses when the call is already cancelled.

The global handler is a safety net for missed synchronous exceptions, not a replacement for explicit error handling in async tasks.

## 6. Preserving statuses and avoiding double mapping

A service may intentionally return `NOT_FOUND`, `INVALID_ARGUMENT`, or `PERMISSION_DENIED`. The global handler must not turn those statuses into `INTERNAL` just because they were wrapped in another exception.

Rules:

- Search for status exceptions in the cause chain and preserve code/trailers if created intentionally.
- Only map domain/dependency exceptions that have not yet been converted to a gRPC status.
- If the call is already closed, do not send a second terminal signal.
- Do not turn cancellation exceptions into server errors.
- Do not expose internal exception messages, stack traces, or causes to the client.

Do not map statuses based solely on description strings. Use status codes and defined domain exception types.

## 7. Testing global exception handling

Tests must verify both the mapper and server-wide behavior:

| Case | Expected |
| --- | --- |
| Domain not found thrown synchronously | Client receives `NOT_FOUND` |
| Validation exception | Client receives `INVALID_ARGUMENT` |
| Existing status exception | Code/trailers are preserved |
| Unexpected exception | Client receives `INTERNAL` with safe description |
| Exception in listener callback | Interceptor closes call with mapped status |
| Exception in executor/future | Task catches error and calls observer `onError` |
| Client cancels stream | Cleanup runs; server sends no second terminal status |
| Two error paths race | Only one terminal close executes |

Mapper unit test:

```java
class GrpcExceptionMapperTest {

    private final GrpcExceptionMapper mapper =
            new GrpcExceptionMapper();

    @Test
    void mapsKnownDomainError() {
        var mapped = mapper.map(
                new CustomerNotFoundException("customer-1"));

        assertEquals(Status.Code.NOT_FOUND,
                mapped.getStatus().getCode());
    }

    @Test
    void mapsUnknownErrorToSafeInternal() {
        var mapped = mapper.map(
                new IllegalStateException("database password leaked"));

        assertEquals(Status.Code.INTERNAL,
                mapped.getStatus().getCode());
        assertEquals("Internal server error",
                mapped.getStatus().getDescription());
    }

    @Test
    void preservesExistingGrpcStatus() {
        var original = Status.PERMISSION_DENIED
                .withDescription("Operation is not permitted")
                .asRuntimeException();

        var mapped = mapper.map(original);

        assertEquals(Status.Code.PERMISSION_DENIED,
                mapped.getStatus().getCode());
    }
}
```

Integration tests should stand up an in-process server with the global interceptor registered, invoke a test service that intentionally throws synchronous exceptions, and inspect the status on the client. Add a separate test for executors to prove async errors are handled inside the task, because the interceptor cannot directly observe exceptions escaping onto another thread.

## 8. Observing errors and operations

The global handler is the right place to emit consistent metrics:

- Total exceptions by gRPC method and status code.
- Errors mapped by domain/dependency vs. `INTERNAL` fallback counts.
- Calls cancelled or expired due to deadlines.
- Errors in listener callbacks and errors from async tasks.
- Multiple attempts to invoke the mapper/terminal close.

Logs should include method, status, application error code, and correlation ID. Stack traces should only be written to internal diagnostic channels with proper access controls and retention. Do not log tokens, payloads, or raw PII; do not put exception messages into descriptions.

If the `INTERNAL` fallback rate rises, that is a signal that the mapper is missing a known error type or a new programming bug appeared. Do not "fix" it by mapping all exceptions to an "easy-to-retry" status.

## 9. Self-practice

1. Why is a Spring bean containing a mapper insufficient to guarantee all RPCs go through global exception handling?
2. An interceptor can catch exceptions in `onHalfClose()`, yet why can't it automatically catch exceptions in a task running on an executor?
3. A lower layer throws `StatusRuntimeException(PERMISSION_DENIED)`. Should the global mapper preserve or change the status? Why?
4. Design a test proving a failing streaming callback closes the call only once.
5. If a service already committed data and an error occurs while sending the response, why can't the global handler automatically roll back the transaction or guarantee the client can safely retry?

**Remember:** Global server exception handling centralizes mapping exceptions to gRPC statuses at the RPC boundary, preserving existing statuses and using a safe `INTERNAL` for unexpected errors. A server interceptor can catch synchronous errors during initialization and listener callbacks; async errors must still be caught in the originating task/pipeline. Register the interceptor in the server chain, guard terminal state, and test both responses and cancellations.
