# Interceptor Order

An RPC may pass through multiple interceptors: tracing, correlation ID, metrics, authentication, logging, and method-level policies. Their order determines which interceptor runs first, which one sees early-rejected calls, and which context values are already available when the handler runs. An unintentionally ordered chain can drop metrics for blocked requests, write logs missing trace IDs, or allow requests deep into processing before authentication.

In Spring gRPC, interceptors execute via gRPC Java's chaining mechanism; Spring provides registration points and configuration management. You must distinguish **interceptor invocation order**, **callback order through listeners**, and **call closing order through ServerCall**. This lesson focuses on designing, registering, and testing that order.

## 1. The outer and inner model

A chain can be pictured as nested wrapping layers:

```text
Transport
  -> Interceptor A (outer)
      -> Interceptor B
          -> Interceptor C (inner)
              -> Service handler
```

In the request direction, the call flows from outer layers to inner layers. Interceptor A has the chance to inspect or enrich context before B and C. By the time an inner layer forwards to the handler, all outer layers have been traversed.

For server listeners, events from the transport such as `onMessage`, `onHalfClose`, and `onCancel` pass through the listener wrappers toward the handler. When the service finishes the call via `ServerCall.close`, the close call traverses the wrapped `ServerCall` layers. Consequently, each interceptor can observe different phases depending on whether it wraps the call, the listener, or both.

Do not infer ordering solely from bean names or configuration file order. Composition behavior in gRPC Java APIs and Spring gRPC extension points can differ; verify with tests on the exact version you run.

## 2. Recommended order for the server

A commonly useful logical order is:

```text
Incoming RPC
  -> Trace / Context propagation
      -> Metrics
          -> Authentication
              -> Method-level authorization
                  -> Service handler
```

Each layer has a clear purpose:

| Position | Responsibility | Reason |
| --- | --- | --- |
| Trace/context | Extract trace context, attach call context | Metrics, auth, and handler can use trace context |
| Metrics | Start timing and observe final status | Can also record calls rejected by auth inside |
| Authentication | Verify credentials, build principal | Invalid requests never reach the handler |
| Method-level authorization | Check if caller may invoke this RPC | Block method before business execution |
| Service handler | Execute use case | Receives only calls that passed shared policies |

This is the desired logical order along the request path. When registering, configure it so actual execution order matches this chain. If metrics sit inside authentication and authentication closes the call immediately, metrics may never see rejected calls. If tracing/context runs after metrics, metrics logs or spans may lack trace context.

Resource-specific authorization still belongs in the application service because generic interceptors do not yet know the specific object the request targets. Interceptors can enforce method-level access; the handler/application layer checks permissions on specific products, orders, or tenants.

Preserve accurate status semantics when rejecting: missing/invalid credentials usually map to `UNAUTHENTICATED`; an authenticated caller lacking permission for a method or resource maps to `PERMISSION_DENIED`. Outer metrics and tracing should record this actual status rather than replacing it with a generic code.

## 3. Order on the client

The client can also use multiple interceptors. Example logical chain:

```text
Application stub
  -> Trace propagation
      -> Credential attachment
          -> Client metrics
              -> Transport
```

| Position | Responsibility | Notes |
| --- | --- | --- |
| Trace propagation | Inject trace context into metadata | Use propagator, never manually assemble traceparent |
| Credential attachment | Attach appropriate credential for the call | Do not log tokens; fetch token per call |
| Client metrics | Measure client wait time and final status | Measure until onClose callback, not when start returns |

This order lets client metrics observe the call after metadata has been prepared. However, if metrics need to include token acquisition or span creation time, the position can shift. Define where the metric begins before choosing the order.

Do not attach a global credential to a channel if that channel is shared across multiple identities or audiences. Credential interceptors must apply to the right channel/call and must never forward tokens to backends not authorized to receive them.

## 4. Short-circuiting affects other interceptors

An interceptor can terminate a call without invoking the next interceptor—for example, authentication rejecting credentials:

```java
if (!credentialVerifier.isValid(token)) {
    call.close(
            Status.UNAUTHENTICATED.withDescription("credentials required"),
            new Metadata());
    return new ServerCall.Listener<>() {};
}
return next.startCall(call, headers);
```

When short-circuiting:

- Outer interceptors have already executed and can observe the call.
- Inner interceptors are never invoked.
- The service handler does not run.
- Outer interceptors only record the outcome if they properly wrapped ServerCall or the listener and handle the close path.

This is why metrics or tracing are typically placed outside policies that can reject calls. If an interceptor short-circuits without calling next, do not expect inner interceptors to log or record metrics.

## 5. Exceptions and status must flow through the chain

A service can end a call with statuses like NOT_FOUND, INVALID_ARGUMENT, or INTERNAL. Interceptors observe the status in ServerCall.close; client interceptors typically observe status in the onClose callback.

If an interceptor only logs or records metrics, it should preserve the original status and trailers:

```java
ServerCall<ReqT, RespT> monitored =
        new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
            @Override
            public void close(Status status, Metadata trailers) {
                metrics.record(status.getCode());
                super.close(status, trailers);
            }
        };
```

Do not convert every exception into INTERNAL across multiple interceptors. Pick one clear place to map business exceptions to gRPC statuses; observing interceptors should keep the already-determined status intact. If an interceptor catches an exception and rethrows it, ensure it does not call close twice or lose the original cause.

## 6. Ordering and Context propagation

Interceptors such as tracing or correlation create context used by the rest of the call. Therefore, they must run before any interceptor that needs to read that context.

Example:

1. Trace interceptor extracts W3C trace context and binds it to callbacks.
2. Correlation interceptor reads or creates a correlation ID and attaches it to gRPC Context.
3. Metrics/logging interceptor reads trace/correlation context to include in logs or span attributes.
4. Authentication verifies the token and attaches the principal.
5. Handler reads principal and context to execute the use case.

If work is offloaded to a custom executor, propagate context across the executor/task. Having the right interceptor order alone does not transfer context to a new thread. Never store principals, trace IDs, or request IDs in mutable fields of singleton interceptors/services, because concurrent RPCs will overwrite each other's data.

## 7. Registering order in gRPC Java and Spring gRPC

In gRPC Java, builders and helper APIs have specific interceptor registration semantics. When using helpers like `ServerInterceptors.intercept` or `ServerInterceptors.interceptForward`, read the exact contract of the API you are calling; helper names reflect how they compose the list and should not be assumed from another API. For clients, also check the documentation for the channel/intercept mechanism in use.

Example registration on the core server builder:

```java
Server server = ServerBuilder.forPort(9090)
        .intercept(traceInterceptor)
        .intercept(metricsInterceptor)
        .intercept(authenticationInterceptor)
        .addService(catalogService)
        .build();
```

This snippet shows interceptors registered on the server builder; the final execution order must be verified against the specific builder API and gRPC Java version. Do not copy this order blindly to `ServerInterceptors.intercept(...)` or Spring configuration without checking the semantics of that extension point.

In Spring gRPC, the server is usually auto-configured and interceptors are attached through the framework's extension point. Use the ordering mechanism supported by your exact Spring gRPC version. Do not assume that `@Order`, `@Bean` declaration order, or component scan order dictates the chain unless your version's documentation explicitly guarantees it.

If strict ordering is required and the framework does not provide an explicit guarantee, create a centralized registration configuration or explicit adapter for the interceptor list. The goal is having one single place to review ordering, rather than letting multiple modules register global interceptors independently.

## 8. Testing actual execution order

Write tests using interceptors that append events to a thread-safe list. Invoke both a successful RPC and a rejected RPC to verify both the normal path and short-circuiting:

```text
Successful call:
trace.enter
metrics.enter
auth.enter
service.invoke
auth.return
metrics.close(OK)
trace.exit

Rejected call:
trace.enter
metrics.enter
auth.enter
metrics.close(UNAUTHENTICATED)
trace.exit
```

This is the expected order for the example chain; actual callbacks may interleave depending on asynchronous execution. Tests should assert essential relationships, such as trace.enter occurring before metrics.enter, auth running before service, and metrics observing the status from auth rejection.

Cases to verify:

| Test case | What to verify |
| --- | --- |
| Successful RPC | All required interceptors run in the right order |
| Missing/invalid credential | Authentication blocks handler; outer metrics/tracing still observe the call |
| Context propagation | Handler and downstream client calls read the established context |
| Exception in handler | Final status is preserved and metrics record exactly once |
| Client cancellation | Listener callbacks and call close do not produce duplicate logs/metrics |
| Two concurrent RPCs | No shared state or event ordering bleed between calls |
| Multiple channels/servers | Each endpoint receives the intended interceptor set |

Prefer an in-process server/channel for pure gRPC chain tests. For Spring integration tests, boot the application context and perform RPCs through real beans/channels to verify the framework registers the intended interceptor list.

## 9. Common ordering mistakes

- **Metrics placed after authentication:** early-rejected calls are excluded from overall metrics.
- **Logging runs before trace extraction:** logs lack trace IDs even though metadata was sent.
- **Authorization placed after service logic:** business logic may execute before permissions are checked.
- **Multiple interceptors mapping exceptions:** status gets overwritten multiple times or the root cause is lost.
- **Two interceptors injecting trace context:** metadata gets overwritten or propagation becomes inconsistent.
- **Relying on bean scan order:** ordering is not guaranteed across environments or builds.
- **Interceptor holding per-call state in fields:** concurrent requests cause context leaks or corrupted counts.

When debugging, emit short markers in `interceptCall`, `startCall`, `onMessage`, `onCancel`, and `close` in test environments only. Do not log sensitive metadata or payloads just to observe ordering.

## 10. Chain review checklist

- [ ] Drawn the chain from outer to inner along the request path.
- [ ] Identified which interceptors can short-circuit.
- [ ] Metrics/tracing sit far enough outside to observe rejected calls as required.
- [ ] Authentication and method-level authorization run before the service handler.
- [ ] Trace/correlation context is ready before interceptors that read it.
- [ ] Status and trailers are preserved through observing interceptors.
- [ ] Checked the ordering contract of the gRPC Java/Spring APIs in use.
- [ ] Not relying on component scan order or bean declaration order without a guarantee.
- [ ] Integration tests cover success, rejection, error, cancellation, and concurrency.
- [ ] Interceptors do not hold per-call mutable state in shared fields.

**Self-check**

**Question 1.** Why does the metrics interceptor usually need to sit outside the authentication interceptor?

*Answer:* So metrics can also observe calls rejected early by authentication. If metrics sit inside, short-circuiting prevents them from being invoked.

**Question 2.** When a request enters the chain, does the outer or inner interceptor run first?

*Answer:* In the chain model, the call travels from outer to inner. Listener callbacks and response wrappers traverse the layers in the corresponding direction; test the specific composition behavior.

**Question 3.** Why can't you assume `@Bean` order equals interceptor order?

*Answer:* Chain ordering is governed by the framework extension point and gRPC Java API. Unless the framework guarantees bean ordering, bean creation order is insufficient to prove execution order.

**Question 4.** If an authentication interceptor rejects a call without calling next, do inner interceptors run?

*Answer:* No. Inner interceptors and the service handler are skipped; outer interceptors only observe the outcome if they wrapped the call/listener properly.

**Question 5.** How do you verify the chain order is right in Spring gRPC?

*Answer:* Write integration tests that boot the actual Spring configuration, invoke both successful and rejected RPCs, and assert marker order, statuses, and that metrics/tracing observe the calls.

Interceptor order is part of both the security and operational behavior of Spring gRPC. Design chains by responsibility, place observability layers far enough outside, run authentication before handlers, preserve statuses, and verify order against your real configuration with integration tests.
