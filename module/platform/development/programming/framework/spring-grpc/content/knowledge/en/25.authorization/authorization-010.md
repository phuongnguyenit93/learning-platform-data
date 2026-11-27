# Authorization for Streaming RPCs

## Learning Objectives

After this lesson, you will be able to:

- Explain why authorization for streaming RPCs must cover both stream open time and message exchange.
- Distinguish method-call permissions from access permissions for each resource referenced in a stream.
- Apply appropriate policies for server-streaming, client-streaming, and bidirectional streaming.
- Keep the verified principal, tenant, and permissions scoped to a single stream.
- Handle token expiry, permission revocation, revalidation, cancellation, and cleanup.
- Combine authorization with flow control, backpressure, and resource limits.
- Choose between terminating the stream with a gRPC status or returning message-level rejections per contract.
- Write tests proving streams never emit or process data outside the permitted scope.

## 1. Why Does Streaming Need Its Own Authorization Approach?

In **SPRING_GRPC**, gRPC supports unary RPCs and three streaming patterns: server-streaming, client-streaming, and bidirectional streaming. Unary typically has one request and one response; streaming keeps an RPC open while multiple messages are sent in one or both directions.

For unary RPCs, the server can usually determine the method, principal, and resource to check before executing the use case. For streaming, decisions at call open may only tell whether the caller is allowed to invoke the method. Subsequent messages may reference different resources, different tenants, or require actions with different sensitivity levels.

For example, a caller has permission to invoke **OrderService/WatchOrders**. That permission does not automatically let the caller watch every order across every tenant. Similarly, being allowed to open **EventService/UploadEvents** does not mean every event sent later is valid or within the caller's scope.

A safe design separates two layers:

- **Method authorization at stream open:** is the caller allowed to start this RPC?
- **Message/resource authorization during the stream:** is the caller allowed to operate on the resource or action requested by the current message?

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant I as Server interceptor
    participant S as Streaming service
    participant P as Resource policy
    participant D as Data / downstream
    C->>I: Open stream + credentials
    I->>I: Authenticate principal
    I->>I: Check permission for service/method
    alt Method denied
        I-->>C: PERMISSION_DENIED
    else Method allowed
        I->>S: Start stream with principal Context
        loop Each inbound message / resource
            C->>S: Message
            S->>P: Check tenant, resource and action
            alt Resource allowed
                P-->>S: Allow
                S->>D: Process / publish authorized data
                D-->>S: Result
                S-->>C: Response message (if applicable)
            else Resource denied
                P-->>S: Deny
                S-->>C: End stream or item-level rejection
            end
        end
    end
~~~

Not every stream needs to call a policy engine for every message. If a stream is bound to one fixed resource, you can check the resource at stream open and bind the entire subscription to that resource. If messages vary in resource or action, check accordingly before processing each message.

## 2. Three Streaming Patterns and Where Authorization Runs

| RPC Pattern | Message flow | Check on open | Check during stream |
| --- | --- | --- | --- |
| **Server-streaming** | One request, many responses | Method permission and permission to subscribe to resource/filter | Check each emitted resource/event if scope can change |
| **Client-streaming** | Many requests, one final response | Method permission and permission to start operation | Check each message before writing or creating side effects |
| **Bidirectional streaming** | Many requests and responses both ways | Method permission and permission to open session | Check each command/resource; emit response only after request is authorized |

### 2.1. Server-Streaming

For example, **WatchOrder** takes an order ID and streams multiple status updates for that order. The server must:

1. Authenticate the principal and check the **orders:watch** permission.
2. Load the order with a tenant-scoped query.
3. Verify the caller is allowed to view that order.
4. Create a subscription solely for the exact verified order and tenant.
5. When emitting events, ensure events belong to the authorized subscription.
6. Cancel the subscription when the client cancels, permissions are revoked, or the resource leaves scope.

If the request carries filters for multiple orders or multiple tenants, those filters are untrusted input. The server must validate every requested scope and restrict results at the data source. Never fetch all events and filter on the client; unauthorized data would have already left the server.

### 2.2. Client-Streaming

For example, **UploadEvents** receives multiple events within a single RPC. The **events:write** method permission lets the caller start the upload, yet each message may contain a different tenant ID, aggregate ID, or event type.

Before processing each message, the server must verify the tenant, aggregate/resource permissions, schema, and business invariants. Only then should it write the event or produce side effects. A rejected message may terminate the entire stream; if the contract allows continuing and returning per-item errors, the response schema must clearly report which items were accepted/rejected.

### 2.3. Bidirectional Streaming

Bidirectional streams are often used for continuous command/response flows, state synchronization, or event exchange. Each request message may request a different action and responses may contain sensitive data.

The server must authorize each command before executing it and verify read permissions before sending the corresponding response. Never infer that because the caller was authorized for the first message, every subsequent command is allowed. If the stream maintains session state, that state must be bound to the verified principal/tenant and must not be arbitrarily mutable by the client.

## 3. Authentication and Method Authorization at Stream Open

Every streaming RPC still begins with opening a call. The authentication interceptor verifies credentials, builds an immutable principal, and places it into **io.grpc.Context**. The authorization interceptor checks the actual method via **ServerCall.getMethodDescriptor().getFullMethodName()**.

Stream-open policy example:

~~~java
String method = call.getMethodDescriptor().getFullMethodName();
GrpcPrincipal principal = GrpcSecurityContext.PRINCIPAL.get();

if (principal == null) {
    call.close(
            Status.UNAUTHENTICATED
                    .withDescription("Authentication required"),
            new Metadata());
    return new ServerCall.Listener<ReqT>() {};
}

if (!policy.allows(principal, method)) {
    call.close(
            Status.PERMISSION_DENIED
                    .withDescription("Permission denied"),
            new Metadata());
    return new ServerCall.Listener<ReqT>() {};
}

return next.startCall(call, headers);
~~~

This is a **method-call** permission check. The interceptor knows which method is being dispatched, but does not necessarily have enough domain information to decide permissions for each order, document, or event inside messages. Do not confuse method authorization with resource authorization.

When the method is denied, the call must terminate before the streaming handler is invoked. If the handler starts running before permissions are checked, the service may already create subscriptions, allocate buffers, or trigger side effects.

## 4. Principal and Tenant Must Be Bound to the Right Stream

The principal produced after authentication must be immutable and bound to the RPC's own Context. Shared key example:

~~~java
public final class GrpcSecurityContext {

    public static final Context.Key<GrpcPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private GrpcSecurityContext() {}
}
~~~

Inside the streaming handler, retrieve the principal once at the start and hold the immutable reference for the stream's lifetime:

~~~java
GrpcPrincipal principal = GrpcSecurityContext.PRINCIPAL.get();

if (principal == null) {
    responseObserver.onError(
            Status.UNAUTHENTICATED
                    .withDescription("Authentication required")
                    .asRuntimeException());
    return;
}
~~~

If the principal has access to multiple tenants, the chosen tenant must be verified before creating subscriptions or processing messages. A tenant ID in a protobuf message is merely a tenant selector; the server must check membership/entitlement against the principal. Never allow later messages to arbitrarily switch the tenant of a stream already bound to a fixed tenant.

Never store the principal in a mutable field on a singleton service implementation. Multiple concurrent streams can execute on the same instance; fields like currentUser or currentTenant would be overwritten by other requests. Keep the principal in a local variable of the stream handler or pass explicit actor/tenant values into use cases.

## 5. Checking Each Message Before Processing

For client-streaming and bidirectional streaming, each inbound message may reference a different resource. The per-message workflow should be:

1. Validate message structure and size.
2. Check the tenant selector against the principal's verified tenants.
3. Load the resource using a query with a tenant predicate.
4. Check permissions and ownership/relationships for the specific action.
5. Check business invariants.
6. Only then write data, emit events, or call downstream services.

Partial example of processing an upload message:

~~~java
private void processEvent(
        GrpcPrincipal principal,
        UploadEventRequest request) {

    String tenantId = tenantAccess.requireTenant(
            principal,
            request.getTenantId());

    eventAuthorization.requireCanAppend(
            principal,
            tenantId,
            request.getAggregateId());

    eventUseCase.append(
            principal.subject(),
            tenantId,
            request);
}
~~~

tenantAccess verifies the caller may operate in the selected tenant; eventAuthorization checks permissions on the aggregate; eventUseCase runs only after both decisions succeed. The underlying repository must still scope reads/writes by tenant. Never check the tenant once in an interceptor and blindly trust all subsequent messages.

When a message is invalid, the contract must clearly decide:

- **Terminate stream:** return a status such as **PERMISSION_DENIED**, **INVALID_ARGUMENT**, or **FAILED_PRECONDITION**; appropriate when the error renders the whole operation unsafe.
- **Reject item and continue:** return a response item with accepted=false and a stable error code; appropriate when items are independent and the contract supports partial success.

Never return internal policy details inside response items. If continuing the stream, never execute side effects for a rejected item.

## 6. Client-Streaming Example with Per-Message Authorization

A client-streaming method may return a summary after receiving all requests. The core snippet below illustrates checking each message before invoking the use case:

~~~java
@Override
public StreamObserver<UploadEventRequest> uploadEvents(
        StreamObserver<UploadSummary> responseObserver) {

    GrpcPrincipal principal =
            GrpcSecurityContext.PRINCIPAL.get();

    if (principal == null) {
        responseObserver.onError(
                Status.UNAUTHENTICATED
                        .withDescription("Authentication required")
                        .asRuntimeException());
        return new StreamObserver<>() {
            @Override public void onNext(UploadEventRequest value) {}
            @Override public void onError(Throwable error) {}
            @Override public void onCompleted() {}
        };
    }

    if (!principal.hasPermission("events:write")) {
        responseObserver.onError(
                Status.PERMISSION_DENIED
                        .withDescription("Permission denied")
                        .asRuntimeException());
        return new StreamObserver<>() {
            @Override public void onNext(UploadEventRequest value) {}
            @Override public void onError(Throwable error) {}
            @Override public void onCompleted() {}
        };
    }

    return new StreamObserver<>() {
        private int accepted;
        private boolean terminal;

        @Override
        public void onNext(UploadEventRequest request) {
            if (terminal) {
                return;
            }
            try {
                processEvent(principal, request);
                accepted++;
            } catch (AuthorizationDeniedException denied) {
                terminal = true;
                responseObserver.onError(
                        Status.PERMISSION_DENIED
                                .withDescription("Permission denied")
                                .asRuntimeException());
                cleanupUpload(principal);
            }
        }

        @Override
        public void onError(Throwable error) {
            if (!terminal) {
                terminal = true;
                cleanupUpload(principal);
            }
        }

        @Override
        public void onCompleted() {
            if (terminal) {
                return;
            }
            terminal = true;
            responseObserver.onNext(
                    UploadSummary.newBuilder()
                            .setAcceptedCount(accepted)
                            .build());
            responseObserver.onCompleted();
            cleanupUpload(principal);
        }
    };
}
~~~

This skeleton illustrates where checks live. Production implementations must ensure callbacks are serialized or protect terminal state in a thread-safe manner; cleanup must be idempotent. When denied, stop processing the inbound stream; do not continue accepting messages and accidentally invoke the use case.

For recoverable item errors, instead of terminating the stream in the catch block, return an item-level result per contract and continue. Never both call onError to terminate the RPC and continue sending responses or processing subsequent messages.

## 7. Server-Streaming Must Also Control Emitted Data

Server-streaming usually receives no further request messages after opening the call, yet the server can emit many responses over a long period. Authorization does not merely protect subscription creation; it must also ensure all emitted data stays within the permitted scope.

For **WatchOrders**, for example:

- Principal holds the **orders:watch** permission.
- Tenant is resolved from the principal or a membership-verified selector.
- Queries/subscriptions filter by tenant at the repository or event source.
- If filters allow multiple orders, each order must fall within the caller's scope.
- Never emit events whose access was removed or that belong to another tenant.
- When permissions or memberships are revoked, cancel the subscription or re-evaluate per policy.

Push tenant filters down to the data source instead of subscribing to everything and filtering later. This lowers the risk of unauthorized data entering buffers, logs, caches, or callbacks before being discarded.

For long-lived streams, a policy snapshot at open time can grow stale. Define a maximum stream lifetime, periodic revalidation intervals, or push revocation mechanisms. If policy only takes effect at stream open, API documentation and the threat model must explicitly state that limitation.

## 8. Permission Revocation, Token Expiry, and Revalidation

Authentication typically verifies credentials when the RPC opens. A token expiring later does not automatically close an existing stream. Likewise, permissions or memberships can be revoked while a stream remains open.

Choose an intentional model:

| Model | How it works | Suitable when |
| --- | --- | --- |
| **Authorize at open** | Permissions checked at open; stream lives at most for a bounded duration | Short streams, rarely changing permissions |
| **Periodic revalidation** | Re-check principal/policy periodically or before message batches | Long streams, permissions may change |
| **Event-driven revocation** | Receive revocation signals and cancel affected streams | Rapid revocation required |
| **Per-message authorization** | Check permissions/resource before each message or action | Messages target different resources/actions |

You do not necessarily have to call a remote policy engine for every message. You can use verified permission snapshots, short-TTL caches, or batch evaluation; however, account for permission revocation windows and data scope. For sensitive operations, revalidate right before side effects if policy can change during the stream.

When a token expires, define a clear policy for active streams: terminate with **UNAUTHENTICATED**, allow completion within a published grace window, or require the client to open a new stream with fresh credentials. Do not automatically refresh client credentials on the server side without an explicitly designed flow.

## 9. Cancellation, Cleanup, and Resource Limits

Streams hold subscriptions, buffers, callbacks, and potentially downstream resources for extended periods. When the client cancels, deadlines expire, or authorization is revoked, the server must halt associated work.

With grpc-java, **ServerCallStreamObserver** provides cancellation inspection and cancellation callback registration. Example:

~~~java
if (responseObserver instanceof ServerCallStreamObserver<?> serverObserver) {
    serverObserver.setOnCancelHandler(() -> {
        subscription.cancel();
        releaseStreamResources();
    });
}
~~~

Verify exact API names and usage against your project's grpc-java version. Whichever API is used, cleanup must be idempotent because cancellation, downstream failures, and authorization errors can occur close together.

Resources to release:

- Subscriptions to brokers or event sources.
- Database cursors, change streams, or reactive subscriptions.
- Buffers and queues holding messages.
- Scheduled revalidation/heartbeat tasks.
- Cancelable futures and async tasks.
- Tenant-allocated quotas/concurrency slots.

Never allow a denied stream to retain subscriptions or workers. Never keep an RPC's principal/Context in long-lived jobs after the stream finishes; transfer minimal actor/tenant data into a job envelope if independent processing is needed.

## 10. Flow Control and Backpressure Are Part of Isolation

A caller authorized to open a stream can still send messages too quickly or fail to read responses. If the server accepts messages faster than it can process them, queues can grow unbounded and impact other tenants.

- Cap message sizes and pending message counts.
- Apply concurrent stream quotas per principal/tenant.
- Use flow control to regulate inbound/outbound traffic rather than unbounded buffering.
- Check authorization before enqueuing work that creates side effects.
- Do not emit sensitive responses when the outbound stream is not ready.
- Cancel or throttle streams exceeding quotas per contract.
- Enforce fairness so one tenant cannot monopolize all workers, connections, or buffers.

For outbound streaming, grpc-java's **isReady()** and on-ready callbacks help producers send only when the transport can accept more data. For inbound streaming, manual flow control can limit how many messages are requested next. Whichever mechanism is used, authorization must run before data enters business processing queues.

**RESOURCE_EXHAUSTED** is appropriate when quotas or resource limits are exceeded. Never use this status to indicate missing permissions; missing permissions remain **PERMISSION_DENIED**.

## 11. Statuses and Errors Inside an Open Stream

A stream may terminate with a status after exchanging several messages. Clients need to know whether earlier messages may already have been processed; a final error status does not automatically roll back committed side effects.

| Situation | Commonly used status | Note |
| --- | --- | --- |
| No principal at stream open | **UNAUTHENTICATED** | Do not invoke streaming handler |
| Lacking method permission | **PERMISSION_DENIED** | Deny before creating subscription |
| A message accesses an out-of-scope resource | **PERMISSION_DENIED** or **NOT_FOUND** | Per resource concealment policy |
| Malformed message | **INVALID_ARGUMENT** | Can end stream or return item-level error |
| Resource in unsuitable state | **FAILED_PRECONDITION** | Do not perform action for that message |
| Policy dependency unavailable | **UNAVAILABLE** | Fail closed; do not process unauthorized messages |
| Call deadline expired | **DEADLINE_EXCEEDED** | Stop work and clean up |
| Client cancels stream | **CANCELLED** | Stop subscriptions and cancelable work |
| Stream/message quota exceeded | **RESOURCE_EXHAUSTED** | Throttle or terminate per contract |

With the server async API, terminate the stream via **responseObserver.onError(Status.PERMISSION_DENIED.asRuntimeException())**. After a terminal signal, do not send any more onNext or onCompleted calls. To continue after a single message error, represent the error inside a response message instead of terminating the RPC.

Do not expose internal permission names, tenant memberships, or policy expressions in status descriptions. Use stable reason codes and minimal information the caller is allowed to see.

## 12. Common Implementation Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Only checking permissions at stream open | Later messages accessing other resources still run | Authorize each resource/action when needed |
| Trusting tenant ID in messages | Caller switches tenants mid-stream | Verify selector against principal; bind stream to tenant |
| Using a mutable principal on a singleton service | Two concurrent streams mix identities | Immutable principal, stream-local state |
| Subscribing to everything then filtering responses | Out-of-scope data enters buffers/caches/logs | Filter tenant at the data source |
| Not revalidating long-lived streams | Revoked permissions stay effective | TTL, periodic checks, or revocation cancellation |
| Failing to clean up on cancel/deny | Leaks subscriptions, workers, and buffers | Idempotent cleanup on every terminal path |
| Unbounded inbound buffering | One tenant causes noisy-neighbor impact | Flow control, quotas, and bounded queues |
| Calling onError and still sending responses | Violates stream terminal state | Track terminal state, emit exactly one terminal signal |
| Using PERMISSION_DENIED for quotas | Client misinterprets cause | Use RESOURCE_EXHAUSTED for quotas |
| Returning detailed policy errors in status | Leaks security structure | Generic status, controlled internal auditing |

## 13. Testing Authorization for Streaming RPCs

Tests must cover both stream opening and individual messages. A unary test for an interceptor does not prove streaming is secure.

| Scenario | Expected result |
| --- | --- |
| Missing credential | **UNAUTHENTICATED**; handler not called |
| Principal lacks method permission | **PERMISSION_DENIED**; no subscription created |
| Client-streaming sends message in granted tenant | Message processed |
| Client-streaming sends message in another tenant | Message rejected; no side effects |
| Bidirectional stream switches resources across messages | Each resource authorized independently |
| Server-streaming filter requests out-of-scope tenant | Stream not opened or denied |
| Resource permission revoked during long stream | Revalidation/revocation policy terminates or bounds stream |
| Client cancels | Subscriptions, queues, and workers cleaned up |
| Deadline expires | Background work does not continue indefinitely |
| Client sends messages faster than processing capacity | Flow control/quotas bound buffers |
| One item rejected per partial-success contract | Item-level error returned; no side effects for that item |
| Two concurrent streams from two tenants | No mixing of principal, tenant, responses, or caches |

Use in-process gRPC tests or transport integration tests with generated stubs and production interceptors. For client-streaming/bidi, send multiple messages with different resource IDs and verify repository/downstream mocks. For server-streaming, verify the event source is subscribed with a scoped tenant/resource. Add cancellation, deadline, revalidation, and terminal-signal tests to catch resource leaks.

Key assertions:

1. Method authorization happens before the streaming handler creates subscriptions.
2. Per-message authorization happens before repository mutations or downstream calls.
3. Denied messages emit no events, write nothing to the database, and send no responses containing sensitive data.
4. Stream terminal signals occur only once; no new messages follow afterward.
5. Cancellation/revocation releases all subscriptions and buffers.
6. Two concurrent streams do not share mutable principal or tenant state.

## 14. Hands-On Exercise and Self-Check Questions

### Hands-On Exercise

1. Define **EventService/UploadEvents** as client-streaming and **OrderService/WatchOrders** as server-streaming.
2. Add an authentication interceptor creating an immutable principal in shared **io.grpc.Context**.
3. Add method authorization checking **events:write** and **orders:watch** before the handler runs.
4. For each UploadEventRequest, verify tenant, aggregate, and append permissions before writing the event.
5. For WatchOrders, scope subscriptions by the verified tenant and emit only events within scope.
6. Add terminal state handling and cleanup on deny, error, cancellation, or deadline.
7. Set limits on message size, stream concurrency, and inbound/outbound buffering.
8. Write integration tests for cross-tenant messages, revoked permissions, client cancellation, deadlines, and two concurrent streams.

### Self-Check Questions

**1. Why is method authorization at stream open insufficient?**  
Because later messages can reference different resources or tenants; method-call permission does not grant access to all resources.

**2. What must server-streaming check beyond method permission?**  
Permission to subscribe to the filter/resource and ensuring every emitted event belongs to the authorized scope.

**3. What must client-streaming check before each message?**  
Tenant, resource/aggregate, action permission, and business invariants before writing or producing side effects.

**4. Must a remote policy engine be called for every message?**  
Not necessarily. You can use snapshots/caches/batching per the threat model, provided TTLs and revocation timing meet security requirements.

**5. Does an expired token automatically close an open stream?**  
Never assume so. Applications must define max stream lifetimes, revalidation, or revocation and cancellation mechanisms.

**6. When one message is denied, must the stream terminate?**  
Depends on the contract. It can terminate with a gRPC status or return an item-level rejection; both approaches must guarantee zero unauthorized side effects.

**7. Why is cleanup needed when the client cancels?**  
To free subscriptions, buffers, workers, cursors, and quotas; otherwise, finished streams continue consuming resources.

**8. How does RESOURCE_EXHAUSTED differ from PERMISSION_DENIED?**  
RESOURCE_EXHAUSTED represents quotas/resource limits; PERMISSION_DENIED represents policy permission denial.

## Summary

Authorization for streaming RPCs has two scopes: method-call permission at stream open and per-resource/action permission during message exchange. Server-streaming must scope subscriptions and emitted data; client-streaming and bidirectional streaming must check each message before side effects whenever messages may reference different resources. Principal and tenant must bind to the exact stream, while revoked permissions, deadlines, and cancellation require explicit revalidation/cleanup policies. Flow control, quotas, and bounded buffers protect both availability and tenant boundaries. Tests must prove out-of-scope messages produce no side effects, streams terminate cleanly, and resources are released.
