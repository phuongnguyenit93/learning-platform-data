# Method Invocation Auditing

Method invocation auditing records who requested a gRPC method call, how the system authenticated the caller, which policy decided to allow or deny the request, and what outcome the RPC ended with. Auditing helps investigate unauthorized access, trace permission changes, detect anomalous behavior, and prove authorization decisions in operations.

In Spring gRPC, auditing typically coordinates with authentication/authorization interceptors, gRPC `Context`, the service layer, and a controlled audit sink. Both requests rejected before reaching the handler and permitted requests must be recorded; for streaming RPCs, stream start and completion must be tracked. Audit records must be sufficient to trace decisions without containing bearer tokens, private keys, or sensitive payloads.

## 1. How Auditing Differs from Logs and Metrics

These three types of telemetry serve distinct purposes:

| Type | Question Answered | Example |
| --- | --- | --- |
| Application log | What happened during processing? | Handler encountered an error reading order |
| Metrics | How is the system trending operationally? | Count of RPCs returning `PERMISSION_DENIED` per method |
| Security audit | Who requested which action, what did policy decide, and what was the outcome? | Principal `user-42` denied `OrderService/CancelOrder` by policy `orders-admin-v3` |

A log line reading "permission denied" is insufficient for auditing if it lacks caller identity, method, policy version, timestamp, and correlation ID. Aggregated metrics also cannot replace an audit event traceable to a specific request.

A method invocation audit should answer at minimum:

- Who called: verified principal/workload identity, issuer, or authentication type.
- What was called: full gRPC method name, such as `acme.orders.v1.OrderService/CancelOrder`.
- On which target: resource type/ID or tenant when policy enforces resource-level authorization.
- Why it was decided: `ALLOW`/`DENY`, policy/rule ID, and policy version.
- When and from where: UTC timestamp, request ID, peer identity, or connection source within permitted data-retention bounds.
- Outcome: gRPC status, duration, and necessary cancellation/stream completion details.

## 2. Auditing at the Method and Resource Boundaries

A gRPC method is a clean boundary for enforcing common policies. The full method name is formed from the proto package, service, and method; do not use the Java package or Spring bean name:

```text
acme.orders.v1.OrderService/GetOrder
acme.orders.v1.OrderService/CancelOrder
acme.orders.v1.OrderService/WatchOrderEvents
```

However, permission to call a method does not necessarily imply permission to act on every resource. A principal may be allowed to call `GetOrder` but only read orders belonging to their own tenant. An interceptor can check service/method-level permissions; the service/application layer must continue checking resource permissions once the actual order ID and tenant are known.

Therefore, auditing may involve two related events:

1. Method authorization: is the caller allowed to invoke this RPC method?
2. Resource authorization/business action: is the caller allowed to read, modify, or cancel this specific resource?

Do not record an `ALLOW` decision in an interceptor as if the entire business action succeeded. Record decision and outcome separately so investigations do not confuse "permitted to start" with "completed".

## 3. Designing the Audit Event

An audit schema should be stable, versioned, and queryable:

| Field | Meaning |
| --- | --- |
| `event_id` | Unique ID of the audit event |
| `schema_version` | Schema version for data evolution |
| `occurred_at` | UTC timestamp |
| `request_id` / `trace_id` | Correlates the event with the call and trace |
| `rpc_service` / `rpc_method` | Service and method invoked |
| `principal_id` | Verified subject/workload identity |
| `identity_issuer` / `authn_type` | Authentication source and method |
| `tenant_id` | Verified tenant if applicable |
| `peer_identity` | TLS/mTLS peer or gateway identity per trust model |
| `decision` | `ALLOW`, `DENY`, or `NOT_EVALUATED` |
| `policy_id` / `policy_version` | Rule that made the decision |
| `resource_type` / `resource_id` | Target object, if known to policy |
| `grpc_status` | Final status of the RPC |
| `duration_ms` | Elapsed time from call receipt to completion |
| `outcome` | `COMPLETED`, `FAILED`, `CANCELLED`, or `STREAM_OPEN`/`CLOSED` per schema |

Not every field is populated at every stage. If authentication fails, the principal may be anonymous/unknown; if an interceptor denies before reading the request, the resource ID may not yet be known. Use explicit values such as `NOT_AUTHENTICATED` or schema-defined nulls rather than guessing.

Timestamps should be recorded in UTC. Duration should use a monotonic clock such as `System.nanoTime` to avoid system clock adjustments skewing measurements. Never use a client-supplied timestamp as an authoritative audit timestamp.

## 4. Capturing Full Method Name and Request Identity

In a `ServerInterceptor`, obtain the method name from `MethodDescriptor`:

```java
String fullMethod =
    call.getMethodDescriptor().getFullMethodName();
```

This is a stable identifier defined by the Protobuf contract and is suitable as an audit dimension. Avoid guessing the method from the request payload or taking the method name from a caller-supplied header.

A request ID may be passed by a gateway or client via metadata. If the system trusts the gateway, verify the connection to the gateway and specify that the gateway is authorized to set that header. If callers lie outside the trust boundary, the server should generate its own request ID or store both the caller-provided ID and server-generated ID in two distinct fields.

Never use a request ID as proof of authentication. Request IDs are solely for correlation; principals must come from verified tokens/certificates.

## 5. Combining Authentication, Authorization, and Audit Interceptors

A call pipeline can split responsibilities cleanly:

```text
Inbound gRPC call
       |
       v
Audit envelope interceptor (outer)
       | creates per-call audit state
       | wraps ServerCall.close
       v
Authentication interceptor
       | verifies token or peer identity
       | attaches principal to Context
       v
Authorization interceptor
       | checks full method and policy
       | writes ALLOW/DENY to audit state
       v
Service handler
       | checks resource-level permissions
       | executes business logic
       v
ServerCall.close(status)
       |
       v
Audit sink receives decision + outcome
```

The audit envelope must sit outside authentication/authorization so it observes calls rejected before the handler runs. Authentication/authorization write results into the call's isolated state. When `ServerCall` closes, the audit envelope combines the decision with the final status.

Actual interceptor ordering depends on how the server builds its chain. Do not infer ordering solely from Spring context bean order; configure it explicitly and write tests verifying the audit interceptor truly wraps denial branches.

## 6. Storing Per-Call State with Context

Never store principals, method decisions, or request IDs in shared mutable fields on a singleton interceptor. Many RPCs run concurrently on the same instance. Create a per-call audit state and propagate it via gRPC `Context`:

```java
import io.grpc.Context;

static final Context.Key<CallAuditState> AUDIT_STATE =
    Context.key("call-audit-state");

final class AuditEnvelopeInterceptor implements ServerInterceptor {
    private final AuditSink auditSink;

    AuditEnvelopeInterceptor(AuditSink auditSink) {
        this.auditSink = auditSink;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method = call.getMethodDescriptor()
            .getFullMethodName();
        CallAuditState state = new CallAuditState(
            method, System.nanoTime(), headers.get(REQUEST_ID));

        ServerCall<ReqT, RespT> wrapped =
            new ForwardingServerCall
                .SimpleForwardingServerCall<ReqT, RespT>(call) {
            private final AtomicBoolean recorded = new AtomicBoolean();

            @Override
            public void close(Status status, Metadata trailers) {
                try {
                    super.close(status, trailers);
                } finally {
                    if (recorded.compareAndSet(false, true)) {
                        state.complete(status, System.nanoTime());
                        try {
                            auditSink.tryPublish(state.toEvent());
                        } catch (RuntimeException auditFailure) {
                            auditMetrics.publishFailure();
                        }
                    }
                }
            }
        };

        Context context = Context.current()
            .withValue(AUDIT_STATE, state);
        return Contexts.interceptCall(
            context, wrapped, headers, next);
    }
}
```

This is a skeleton illustrating the architecture; `CallAuditState`, `AuditSink`, and metadata keys must be defined in the application. In a production implementation, `tryPublish` must not throw exceptions back into the gRPC call path. Catch sink errors, emit metrics/alerts, and apply the approved audit failure policy.

`Contexts.interceptCall` propagates the state into the `Context` of downstream listeners/handlers. Authentication and authorization interceptors can read the state via `AUDIT_STATE.get()`, then record the principal, policy, and decision on the exact call.

If a call is cancelled without the server invoking `close` on a specific code path, also observe listener `onCancel`/`onComplete` or the corresponding lifecycle hook so the state finalizes exactly once. Never emit two audit events for the same call due to multiple terminal callbacks.

## 7. Recording ALLOW/DENY Decisions from the Authorization Interceptor

The authorization interceptor should record the decision immediately after evaluating policy:

```java
CallAuditState audit = AUDIT_STATE.get();
String method = call.getMethodDescriptor().getFullMethodName();
Principal principal = authenticatedPrincipal();

if (principal == null) {
    audit.setIdentity("anonymous", "NOT_AUTHENTICATED");
    audit.setDecision("DENY", "authentication-required", policyVersion);
    call.close(Status.UNAUTHENTICATED, new Metadata());
    return new ServerCall.Listener<>() {};
}

AuthorizationDecision decision =
    policy.evaluate(principal, method);

audit.setIdentity(principal.id(), principal.issuer());
audit.setDecision(
    decision.allowed() ? "ALLOW" : "DENY",
    decision.policyId(),
    decision.policyVersion());

if (!decision.allowed()) {
    call.close(Status.PERMISSION_DENIED, new Metadata());
    return new ServerCall.Listener<>() {};
}

return next.startCall(call, headers);
```

This snippet illustrates the core logic; `principal` must come from a verified authentication layer and `policy` must check the appropriate method/resource. When the interceptor denies a call, the outer audit wrapper still observes `ServerCall.close` and can emit an event containing `DENY` along with `UNAUTHENTICATED` or `PERMISSION_DENIED`.

Never record `ALLOW` before policy evaluation completes. If the policy engine errors or times out, record decision `NOT_EVALUATED`/`ERROR` and map the failure per security policy; never turn a policy engine failure into `ALLOW`.

## 8. Auditing Outcomes When an RPC Completes

Authorization decision and RPC outcome are two separate facts:

| Decision | RPC Outcome | Interpretation |
| --- | --- | --- |
| `ALLOW` | `OK` | Allowed and RPC completed successfully |
| `ALLOW` | `INTERNAL` | Allowed but processing encountered an error |
| `ALLOW` | `CANCELLED` | Allowed but caller cancelled |
| `ALLOW` | `DEADLINE_EXCEEDED` | Allowed but exceeded deadline |
| `DENY` | `UNAUTHENTICATED` | Caller could not be authenticated |
| `DENY` | `PERMISSION_DENIED` | Valid caller lacks required permissions |
| `NOT_EVALUATED` | `UNAVAILABLE` | Policy/authentication dependency unavailable |

Status `OK` does not prove data changes committed if the handler returns a response before a transaction completes or while asynchronous work continues. For critical actions such as money transfers, permission changes, or order cancellations, business auditing should be recorded at the application/domain layer within the same transaction.

Do not emit a "business action succeeded" event solely because `ServerCall.close(Status.OK)` was called. That event must be grounded in transaction commit or a verified business state.

## 9. Auditing Server-Streaming and Bidirectional-Streaming RPCs

Streaming RPCs have a longer lifecycle than unary calls:

- Record an event when method authorization is decided.
- Record a completion event when the stream closes, errors, or is cancelled.
- Optionally record aggregate message or byte counts if needed for investigations.
- Do not log every individual payload/message by default, as doing so can expose sensitive data and generate excessive audit volume.
- For long-lived streams, track duration, inactivity timeouts, and resource limits.

A stream may be authorized when opened while the principal's permissions change mid-stream. For sensitive data or long-running streams, decide whether to re-evaluate permissions periodically, per message, or when credentials expire. Document this policy explicitly in the audit design.

If the server sends several messages and then ends with an error, the audit outcome must preserve the final status rather than treating earlier messages as a successful RPC. If you need to know which messages were processed/committed, emit separate domain events with appropriate sequence/correlation IDs.

## 10. Audit Sink: Durability, Ordering, and Backpressure

Auditing is only valuable if events are persisted durably and remain retrievable. A sink may be a durable queue, event broker, or dedicated audit storage. Decide explicitly:

1. Are events written synchronously or enqueued asynchronously?
2. When the queue is full or storage fails, should the RPC proceed?
3. Which events must be durable before executing the action?
4. Are retries and deduplication by `event_id` implemented?
5. Who can read/delete audit data, and what is the retention period?

Do not call a remote audit database with blocking I/O inside an interceptor on every RPC if doing so raises latency or starves server threads. You can enqueue into a bounded durable buffer and process asynchronously. Queues must never grow unbounded; add metrics for queue depth, publish failures, oldest event age, and alerts.

Fail-open vs. fail-closed is a risk-based decision:

| Operation Type | Possible Handling Approach |
| --- | --- |
| Routine read RPC, non-transactional audit telemetry | May proceed on transient sink failure if events are durably buffered and alerts fire |
| Permission changes, financial operations, or compliance-mandated actions | May require durable audit before commit or reject when unable to record |
| Security denial events | Prioritize retaining events via a durable queue/buffer to avoid losing traces of denied access |

For business actions requiring atomic auditing, a transactional outbox within the same database transaction is usually better than attempting to write to a remote audit sink from an interceptor. The interceptor does not know whether the transaction committed or rolled back; the application layer must emit the domain audit event at the right boundary.

## 11. Audit Integrity, Security, and Access Control

Audit stores can become targets for tampering or log deletion. Safeguards include:

- Append-only or WORM storage when compliance requires immutability.
- Role-separated permissions for writing, reading, exporting, and deleting.
- Encryption in transit and at rest.
- Hash chains/signatures or integrity proofs if the threat model requires tamper detection.
- Time synchronization and clock drift monitoring.
- Retention, legal hold, and deletion workflows per data policy.
- Auditing administrative actions performed on the audit system itself.

Hash chains require an external anchor or protected signature; simply chaining hashes inside the same database where an administrator can alter both data and hashes provides weak immutability guarantees. Select control strength based on threat model and regulatory requirements.

Never log access tokens, refresh tokens, private keys, passwords, full request payloads, or unnecessary personal data. Prefer principal IDs, categorized resource IDs, policy IDs, and statuses. If storing IP/peer addresses is required, document the purpose, retention, and access controls.

## 12. Spring gRPC Integration and Audit Testing

In Spring, the audit interceptor, authentication interceptor, authorization policy, and `AuditSink` can be managed via dependency injection. Verify they are wired into the actual starter-managed gRPC server:

1. Write unit tests for policies: principal, method, resource, and decision.
2. Spin up an in-process server with the audit envelope wrapping authentication/authorization interceptors.
3. Invoke allowed and denied RPCs; assert audit events include principal, method, decision, and status.
4. Invoke two concurrent RPCs with different principals to verify per-call state does not leak.
5. Verify stream completion, error, and cancellation emit terminal events exactly once.
6. Simulate audit sink timeout/full queue and verify fail-open/closed policy.
7. Boot the Spring context to verify interceptor beans and sinks are actually registered.
8. Run TCP/TLS tests when verifying peer identity from certificates or gateways.

Do not merely test that `AuditSink` was invoked. Assert event contents, policy version, correlation ID, outcome, and redaction. Use a fake clock or injected clock for deterministic timestamp/duration assertions; avoid assertions tied to exact wall-clock timing.

## 13. Test Matrix and Applied Exercise

| Category | Test Case | Pass Criteria |
| --- | --- | --- |
| Allowed call | Principal authorized to call method | Audit records `ALLOW` and exact method |
| Missing identity | No credentials provided | `DENY`/`UNAUTHENTICATED`, handler does not run |
| Invalid identity | Invalid token/certificate | `DENY` and identity failure categorized |
| Permission denied | Principal lacks role | `DENY`/`PERMISSION_DENIED`, policy ID recorded |
| Resource policy | Principal accesses cross-tenant resource | Resource decision denied |
| Outcome | Call allowed but handler errors | Decision `ALLOW`, separate error status |
| Cancellation | Caller cancels call | Audit records `CANCELLED` once |
| Streaming | Stream ends after multiple messages | Has both decision and terminal outcome |
| Concurrency | Multiple principals call concurrently | No identity/request ID leakage across calls |
| Sink unavailable | Queue/storage failure | Behavior matches fail-open/closed policy |
| Integrity | Event modified/deleted | Detection mechanism or storage policy triggers |
| Privacy | Sensitive token/payload | Absent from audit records |
| Spring wiring | Starter-managed server | Audit/authz interceptors actually execute |
| Transport identity | mTLS/gateway | Peer identity verified and bound to right principal |

**Exercise:** `OrderService` exposes `GetOrder`, `CancelOrder`, and `WatchOrderEvents`. `ORDER_READ` may read orders within the principal's tenant; `ORDER_ADMIN` may cancel orders. Every call must have a request ID, policy version, and audit event.

1. Design an audit event schema separating `decision` and `outcome`.
2. Implement authentication/authorization interceptors and an audit envelope using per-call `Context` state.
3. Verify `GetOrder` is allowed, `CancelOrder` is denied, and the handler does not run on `DENY`.
4. Verify resource-level authorization when an order belongs to another tenant.
5. Emit audits for `WatchOrderEvents` on stream completion, error, and cancellation.
6. Simulate a full/unavailable audit sink and verify the chosen policy.
7. Add a transactional outbox for order cancellation if business success auditing must be atomic with commit.
8. Verify redaction, retention, audit read permissions, and integrity controls.
9. Write a Spring context test verifying the interceptor chain runs in the proper order.

**Self-check questions:**

- How do audits differ from application logs and metrics in purpose?
- Why must the full gRPC method name be recorded?
- Why does `ALLOW` not imply the business action committed?
- How do you audit requests rejected before the service handler?
- Why must audit state be isolated per call?
- Which start and completion events does a streaming RPC require?
- When should a transactional outbox be used?
- How do fail-open and fail-closed policies affect auditing?
- Why do hash chains require a protected anchor/signature?
- Which data must never be written to audit records?

**Takeaway:** Method invocation auditing must link verified identity, full method name, policy decision, and RPC outcome. Wrap the audit interceptor around authentication/authorization to capture denied calls; isolate state per call with `Context`; separate method permissions from resource/business authorization; and protect sinks, integrity, and sensitive data. In Spring gRPC, verify the interceptor chain inside the real server and record domain audits at transaction boundaries when atomic commit guarantees are required.
