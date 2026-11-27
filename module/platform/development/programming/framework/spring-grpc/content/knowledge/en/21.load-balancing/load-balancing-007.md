# Sticky routing and session state

## 1. Keeping related RPCs on the same backend

In **SPRING_GRPC**, a service can run across multiple instances and the client uses `ManagedChannel`, a name resolver, and a load balancing policy to select a backend. For stateful business flows, you sometimes want RPCs belonging to the same user, tenant, or job to keep going to the same instance. **Sticky routing** (session affinity) is how that affinity is maintained for a period or based on a routing key.

For example, a user starts an order checkout flow:

~~~text
Client sends:
  StartCheckout(session = S-42)
  AddItem(session = S-42)
  GetCheckout(session = S-42)

Goal with sticky routing:
  RPCs with session S-42 -> backend B
~~~

Sticky routing helps when a backend keeps local caches or session state, or when you want to benefit from a warm cache. However, **affinity is not a session storage mechanism**. If backend B restarts, a session stored only in B's RAM is lost. The system needs a state storage and recovery strategy independent of backend selection.

## 2. Distinguishing connection stickiness and RPC stickiness

gRPC uses HTTP/2 and can multiplex many RPCs over a single connection. Therefore, identify which layer is maintaining affinity:

| Mechanism | Unit kept sticky | Consequence |
|---|---|---|
| L4 load balancer / TCP proxy | TCP connection | Multiple RPCs multiplexed on the same HTTP/2 connection usually go to the same backend |
| gRPC client-side load balancing | Each new RPC via the chosen subchannel | RPCs on the same `ManagedChannel` may be distributed to different backends depending on policy |
| L7 proxy routing per HTTP/2 stream | Each RPC/stream | Proxy can inspect RPC metadata and pick a backend by routing key if configured |
| Affinity by session key | RPCs carrying the same key | Only works if the routing layer understands the key and uses the same algorithm/backend pool |

Keeping a long-lived TCP connection does not mean an entire business session stays on the same instance across all architectures. If client-side `round_robin` selects different subchannels for new RPCs, a downstream L4 proxy cannot infer a session key to keep those RPCs on one backend.

Conversely, if an L4 proxy pins one HTTP/2 connection to one backend, every RPC multiplexed on that connection goes to that backend, while other clients or new connections can still land on different instances. That is connection affinity, not routing by business session.

## 3. Routing keys must be stable and clearly scoped

Sticky routing needs a stable **routing key**. The key can be a session ID, job ID, or authenticated tenant identifier. RPCs belonging to the same scope must send the same key:

~~~text
session S-42:
  StartCheckout  -> x-routing-key: S-42
  AddItem        -> x-routing-key: S-42
  GetCheckout    -> x-routing-key: S-42

session S-99:
  StartCheckout  -> x-routing-key: S-99
~~~

A routing key should have these properties:

- Stable for the duration of the session or workflow requiring affinity.
- Properly uniquely scoped, e.g., combining tenant and session if session IDs are only unique per tenant.
- Unchanging across RPCs when calls in the same session should route identically.
- Free of personal data or secrets in plaintext.
- Derived from or verified against an authenticated identity rather than trusting an arbitrary caller-supplied header.

Do not use access tokens, emails, phone numbers, or sensitive data as routing keys. Use an opaque identifier or a controlled derived value. When combining tenant and session, encode/canonicalize the key pair consistently to prevent collisions.

## 4. Key-based routing methods

A load balancer or proxy can use a routing key in several ways:

| Selection method | Idea | Characteristics |
|---|---|---|
| Hash modulo backend count | `hash(key) % N` | Simple; changing N can remap many keys |
| Consistent hashing | Places backends and keys on a hash ring | Usually remaps only a fraction of keys when backends are added/removed |
| Ring hash / Maglev | Stable key distribution algorithms in proxy/control plane | Useful for affinity at large scale; depends on implementation |
| Cookie or header affinity | Proxy reads cookie/header to pick backend | In gRPC, metadata/headers are typically used; proxy must be configured to read that field |
| Server-side session lookup | Selected backend fetches session from shared store | May eliminate hard affinity needs; increases storage dependency |

Hash algorithms do not take effect automatically just because the client sends a metadata key. For instance, `round_robin` chooses subchannels in turn rather than hashing `x-routing-key`. To achieve sticky routing, configure a policy/proxy that supports key hashing, such as ring hash or an equivalent routing mechanism in the control plane.

With xDS/service mesh, the control plane can supply endpoints and route/hash policies to clients or proxies. Exact capabilities depend on gRPC Java xDS integration, versions, proxies, and deployment configuration. Do not assume an arbitrary JSON property will be understood by default policies.

## 5. Sending routing keys in gRPC metadata

gRPC metadata is the right place to carry a non-sensitive routing hint per RPC. Metadata is transmitted with the call and can be used by an L7 proxy configured to hash on that header.

Example client interceptor attaching the key to metadata:

~~~java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;

public final class RoutingKeyClientInterceptor
        implements ClientInterceptor {

    private static final Metadata.Key<String> ROUTING_KEY =
            Metadata.Key.of(
                    "x-routing-key",
                    Metadata.ASCII_STRING_MARSHALLER);

    private final String routingKey;

    public RoutingKeyClientInterceptor(String routingKey) {
        if (routingKey == null || routingKey.isBlank()) {
            throw new IllegalArgumentException("routingKey is required");
        }
        this.routingKey = routingKey;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> delegate =
                next.newCall(method, callOptions);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<ReqT, RespT>(delegate) {
            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {
                headers.put(ROUTING_KEY, routingKey);
                super.start(responseListener, headers);
            }
        };
    }
}
~~~

You can apply the interceptor to a stub/channel wrapper:

~~~java
import io.grpc.ClientInterceptors;

OrdersGrpc.OrdersBlockingStub sessionStub =
        OrdersGrpc.newBlockingStub(
                ClientInterceptors.intercept(
                        sharedOrdersChannel,
                        new RoutingKeyClientInterceptor(sessionKey)));
~~~

`sharedOrdersChannel` remains the shared long-lived channel; `ClientInterceptors.intercept` creates a channel wrapper for the call without opening a new transport connection. If each RPC has a different routing key, create an interceptor with that RPC's key or pass metadata per request. Do not store a single global routing key inside a singleton interceptor if multiple concurrent sessions share the client service.

**Metadata only carries the key.** It does not make gRPC select backends by key on its own. An L7 proxy, xDS policy, or custom load balancer must be configured to read `x-routing-key` and apply the same affinity algorithm. Without that configuration, requests are still routed by the active policy such as `round_robin` or `pick_first`.

## 6. Where should session state be stored?

Three common models exist:

| Model | Where state lives | When a backend restarts or changes instance |
|---|---|---|
| Local session | RAM of one backend | State is lost without snapshot/replication |
| Shared session store | Redis, database, or shared storage | Another backend can reload state |
| Stateless token | Client carries signed/encrypted data in token | No lookup needed for small state; requires expiry, version, and revocation management |

**Local session + sticky routing** can reduce shared store reads and keep caches warm. However, it introduces coupling to instance lifetime, making scale-in, deployments, and failover more complex.

**Shared session store** is generally more resilient across multiple replicas. Any backend can access state by session ID; sticky routing becomes purely a cache or contention optimization.

**Stateless token** works when state is small, independently verifiable, and infrequently updated. Never put secrets or sensitive data inside unencrypted tokens; signatures protect integrity, not confidentiality.

In practice, you can combine approaches: primary session state lives in a database/Redis, backends cache part of it, and tokens carry only an identifier and version. On cache miss or backend change, another instance reloads state from the shared source.

## 7. Consistency and session updates

Sticky routing does not guarantee that two RPCs in the same session execute sequentially. A client can send `AddItem` and `ApplyCoupon` concurrently; both route to the same backend yet may still run on two different threads or two different connections.

If operations mutate shared state, consistency mechanisms are required:

- Optimistic locking via version or compare-and-set.
- Transactions in the shared store.
- Idempotency keys to handle duplicate requests.
- Serializing commands per session if ordering is a business requirement.
- Setting TTL/expiry and cleanup rules for sessions.

Example of versioned state:

~~~text
Session S-42, version 7
  RPC A reads version 7
  RPC B reads version 7
  RPC A writes version 8 successfully
  RPC B writes with expected version 7 -> conflict

Client/service re-reads version 8 and decides how to proceed
~~~

Do not use affinity as a substitute for concurrency locks or transactions. A single session can be accessed from multiple devices, channels, or client processes.

## 8. When a backend fails or topology changes

Sticky routing cannot keep a session on one instance forever. Backends can crash, be ejected, scale in, or be removed from service discovery. When the backend set changes, hash algorithms may remap some keys to another instance:

~~~text
Before:
  key S-42 -> backend B

Backend B is removed:
  key S-42 -> backend C

Backend C needs to:
  load the session from the shared store
  or restore from snapshot/replica
~~~

With consistent hashing, adding or removing a backend typically reduces the number of remapped keys compared to simple modulo hashing, but does not guarantee a key always stays on the same backend. If a session exists only in RAM, remapping can lose the session.

When a backend is about to stop:

1. Stop accepting new sessions/RPCs via draining.
2. Allow in-flight RPCs to complete within the grace period.
3. Persist or synchronize state needed for recovery.
4. Remove the endpoint from the resolver/control plane.
5. Let clients reconnect and have the new backend load state by session key.

If sessions must survive deployments, shared state or replication/snapshots must be the primary foundation. Sticky routing merely reduces backend switches under normal conditions.

## 9. Server streaming and affinity

A server streaming RPC stays attached to the backend that accepted the RPC when it started. A routing key can help pick the right backend when opening the stream, but does not migrate the stream to another backend if the connection drops.

~~~text
WatchSession(session = S-42, routing key = S-42)
  -> backend B
  <- event 1
  <- event 2
  <- event 3
  <- transport error

Reconnect:
  WatchSession(after_sequence = 2, routing key = S-42)
  -> backend C after topology change
  <- replay event 3, event 4, ...
~~~

To resume:

- Events need a stable sequence or cursor.
- The client persists a checkpoint after durably applying events.
- The new backend reads events from shared storage.
- Event replay requires idempotency/deduplication.

Do not keep the sole event source in the RAM of the backend chosen by sticky routing. If the instance is lost, clients cannot resume from a vanished source.

## 10. Security and limits of routing keys

Routing keys can influence which backend handles a request, so treat them as operationally impactful input:

- Authenticate callers before honoring a key for routing decisions.
- Derive keys from verified principal/tenant/session data at a trusted gateway or service.
- Do not let callers pick arbitrary keys to bypass quotas or concentrate load on one backend.
- Do not put tokens, emails, phone numbers, or sensitive data in metadata.
- Bound key length and format; avoid excessive random values that blow up metric/cache cardinality.
- Do not use routing keys in place of authorization; backends must still verify the caller is authorized to access that session.

If multiple tenants can share the same session ID, the key must include tenant scope or a globally unique identifier to avoid collisions and cross-tenant data leaks.

## 11. Testing sticky routing and session recovery

A test with one backend cannot prove affinity. You need multiple identifiable instances, a resolver/proxy supporting metadata-based hashing, and visibility into which backend receives each RPC.

| Scenario | What to verify |
|---|---|
| Two RPCs with the same routing key | Routed to the same backend while topology and policy stay unchanged |
| Two different session keys | Can be distributed across multiple backends |
| Missing routing key | Uses fallback policy or rejects per chosen contract |
| Caller-spoofed key | Gateway/service authenticates and normalizes key before routing |
| Backend holding local session stops | Session recovers from shared store or returns a clear error |
| Backend added/removed | Keys may remap; state remains accessible |
| Two concurrent RPCs for the same session | No state overwrite; versioning/transactions handle contention |
| Stream interrupted | Client resumes with cursor on the new backend |
| One session sends excessive requests | Quotas/rate limits still apply even when hitting the same backend |
| Rolling upgrade | Session state and schema stay compatible across old/new versions |

Tests must verify both sides: the routing key genuinely influences backend selection, and state remains intact when affinity breaks. Checking only that two requests reach the same instance does not prove sessions survive failover.

## 12. Operational observability

Metrics to monitor:

- RPC share per backend and per routing policy.
- Number of cached keys/sessions per instance.
- Cache hit/miss rates and shared-store state loads.
- Number of sessions remapped during endpoint changes.
- Session recovery counts after backend restarts/ejections.
- Version conflicts/retries and idempotency duplicates.
- Stream reconnect/resume counts and replayed sequence ranges.
- Load distribution by tenant/backend to detect hot keys.

Do not export raw routing keys as metric labels, as cardinality can grow unboundedly and expose data. Log a controlled hashed fingerprint or record only instance ID, policy type, and remap outcomes.

## 13. Common design mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Assuming metadata automatically creates sticky routing | RPCs still use the active policy | Configure proxy/xDS/custom policy to read the routing key |
| Using `round_robin` while expecting identical keys on one backend | RPCs in the same session hit different instances | Use a suitable hash/affinity policy |
| Storing sessions only in RAM | Sessions lost on backend restart or remap | Shared store, snapshots, or stateless tokens |
| Treating sticky routing as authorization | Callers can spoof keys to access wrong sessions | Authenticate and check permissions on the backend |
| Using routing keys containing PII/tokens | Data leakage via metadata/logs | Use verified opaque keys |
| Assuming same backend means sequential processing | Concurrent RPCs still face race conditions | Use transactions, versioning, or serialization |
| Assuming streams automatically migrate backends | Active RPC may fail mid-stream | Reconnect/resume via cursor |
| Modulo hashing by backend count | Many sessions remap when topology changes | Consider consistent hashing and shared state |

**Key takeaway:** Sticky routing keeps RPCs sharing a routing key on the same backend when policy and topology allow it; it is neither session storage nor a sequential execution guarantee. In gRPC, distinguish TCP connection affinity from per-RPC affinity, send routing keys via metadata, and configure an L7 proxy/xDS/custom policy that actually acts on that key. Critical sessions must have shared state or a recovery mechanism; backend changes or broken streams still require recovery, idempotency, and checkpoints.
