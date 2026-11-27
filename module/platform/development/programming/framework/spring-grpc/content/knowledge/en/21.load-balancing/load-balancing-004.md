# Pick first and failover

## 1. Pick first prefers one connectable backend

In **SPRING_GRPC**, the client uses `ManagedChannel` and gRPC Java stubs to call services described by Protocol Buffers contracts. When the name resolver returns multiple addresses for the same service, the load balancing policy decides which subchannel receives a new RPC.

The **`pick_first`** policy prefers an endpoint in the order provided by the resolver. The client tries connecting to that endpoint; if connecting fails, the policy can move on to the next address. Once a subchannel is `READY`, subsequent new RPCs typically continue over that selected connection. This is a way to use one active backend at a time while keeping other addresses as fallback options when connections fail.

Suppose the resolver returns three backends:

~~~text
Resolver order: [A, B, C]

A cannot connect
    -> try B
B connects successfully (READY)
    -> new RPCs are sent to B
    -> continue using B while B remains ready

B loses connection
    -> policy tries remaining addresses per list/state
    -> C may become the selected backend
~~~

`pick_first` does not spread requests evenly across A, B, and C. If you want a single client to utilize multiple backends at the same time, `round_robin` is usually a better fit. `pick_first` is useful when infrastructure already has a load balancer in front or when you want a primary connection with backup endpoints.

## 2. The resolver supplies the address list and order

`pick_first` can only fail over to addresses provided by the resolver. For example, a DNS target:

~~~text
dns:///orders.internal:9090
~~~

DNS may resolve the service name to:

~~~text
orders.internal
  1. 10.40.2.11:9090  (A)
  2. 10.40.2.12:9090  (B)
  3. 10.40.2.13:9090  (C)
~~~

The policy uses the endpoint list from the name resolver to create or update subchannels. Address ordering can affect which endpoint is tried first. If the system needs to prioritize a specific zone, group, or backend, the endpoint order/attributes must be supplied intentionally by the resolver or control plane.

Do not assume DNS always returns multiple distinct addresses. With Kubernetes ClusterIP, the client usually sees a single virtual IP, and pod selection happens at the networking/service proxy layer. With a headless Service, DNS can return individual pod IPs; in that case, the client can use `pick_first` to try endpoints according to the resolver result.

When a resolver returns only a single address, `pick_first` has no other endpoints to fail over to. The policy does not discover pods itself, does not scan subnets, and has no visibility into instances behind a virtual IP.

## 3. Configuring pick_first in gRPC Java

You can set `pick_first` as the default policy for a channel:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///orders.internal:9090")
        .defaultLoadBalancingPolicy("pick_first")
        .useTransportSecurity()
        .build();
~~~

Then use the generated stub as usual:

~~~java
OrdersGrpc.OrdersBlockingStub orders =
        OrdersGrpc.newBlockingStub(channel);

GetOrderReply reply = orders
        .withDeadlineAfter(2, java.util.concurrent.TimeUnit.SECONDS)
        .getOrder(GetOrderRequest.newBuilder()
                .setOrderId("ORD-42")
                .build());
~~~

`defaultLoadBalancingPolicy("pick_first")` is the default policy when the resolver does not provide a service config specifying another policy. If the resolver supplies a service config with a load balancing policy, that configuration can determine the active policy. The policy's provider must be present at runtime.

`useTransportSecurity()` enables TLS. Every backend that the resolver may select must present a certificate matching the authority/hostname verified by the client. Do not disable certificate verification to work around connection failures to a backup endpoint.

## 4. Failover happens when connection state changes

Subchannels have connection states such as `IDLE`, `CONNECTING`, `READY`, and `TRANSIENT_FAILURE`. `pick_first` uses those states to know which endpoint can accept RPCs:

| Scenario | Expected behavior |
|---|---|
| First address connects successfully | Selects that subchannel for new RPCs |
| First address fails to connect | Tries the next address according to policy list/state |
| Currently selected backend loses connection | Subchannel leaves `READY`; policy can try another endpoint |
| A backup backend becomes `READY` | New RPCs can be sent through that backend |
| All endpoints fail to connect | Channel has no ready subchannel; RPCs may fail or wait per wait-for-ready/deadline |
| Resolver updates the list | Policy receives the new result and adjusts subchannels |

Failover depends on **connection-state detection**, not a complete measurement of business health. A process can accept TCP/TLS connections and still return gRPC error statuses because a database is down or a dependency is unhealthy. A `READY` connection does not prove every function of the service is healthy.

To avoid selecting a newly started instance that cannot serve yet, combine this with platform readiness/health checking or service discovery that only advertises eligible endpoints.

## 5. Failover does not migrate an in-flight RPC

This is an important limitation. `pick_first` chooses a subchannel when the RPC begins. If the selected backend loses connectivity mid-call, gRPC cannot transfer the remainder of that RPC to another backend seamlessly as if there were no interruption.

~~~text
RPC GetOrder #1
  Client -> backend A
  A processes request
  A loses connection
  RPC #1 may end with UNAVAILABLE

RPC GetOrder #2 (new call)
  Client -> backend B after failover
~~~

For unary RPCs, the client can retry if the request is safe and the retry policy permits it. However, if backend A already performed side effects before disconnecting, the client cannot infer from a transport error that the side effect did not happen. An idempotency key or status-checking API is needed before resending.

For server streaming, already received responses are not automatically replayed when the policy switches backends. If the stream is interrupted, the client must start a new RPC and send the committed cursor/sequence so the new backend reads the missing portion from shared storage.

Therefore, distinguish between:

- **Connection failover:** the channel switches its selection to another subchannel for new RPCs.
- **RPC retry:** the runtime/client makes another call attempt according to retry conditions.
- **Stream resume:** the application starts a new RPC with a cursor/checkpoint to continue data delivery.

These three mechanisms are related but do not replace one another.

## 6. Distinguishing connection errors from business errors

`pick_first` reacts primarily to subchannel state. It does not automatically resend a request to another backend simply because the server returned a business status:

| Result from backend | Is it a connection failover signal? | How to handle |
|---|---|---|
| Cannot open connection or transport error | Can cause the subchannel to leave `READY` | Policy can try another endpoint |
| Server returns `INVALID_ARGUMENT` | No | Fix the request; do not route to another backend |
| Server returns `PERMISSION_DENIED` | No | Handle authorization/identity |
| Server returns `NOT_FOUND` | No | Handle according to business logic |
| Server returns `INTERNAL` | Does not automatically mean backend disconnected | Observe application errors; retry only when safe and configured |
| Server returns `UNAVAILABLE` at the RPC layer | May be retried by retry policy if eligible | Distinguish application status from transport state; use controlled retry policies |

Do not treat every `UNAVAILABLE` as proof that the backend is dead. A server that is `READY` can still return `UNAVAILABLE` for a temporary downstream dependency issue. Conversely, TCP/TLS errors can happen before the server ever processes the request. Logs, tracing, and subchannel state help pinpoint the failure layer.

## 7. wait-for-ready and deadlines during failover

When no subchannel is `READY`, the client can fail immediately or wait if the RPC uses `withWaitForReady()`. Wait time is still bounded by the deadline:

~~~java
GetOrderReply reply = orders
        .withWaitForReady()
        .withDeadlineAfter(3, java.util.concurrent.TimeUnit.SECONDS)
        .getOrder(request);
~~~

`waitForReady` gives the channel a chance to wait for an endpoint to recover or a backup endpoint to connect. It does not create new backends, does not guarantee failover succeeds, and does not let the RPC wait indefinitely.

Set the deadline according to business budgets. If attempting connections to endpoints A, B, and C consumes nearly the entire deadline, the request may end with `DEADLINE_EXCEEDED` before a backup backend is ready. Do not set deadlines so short that every failover exhausts the budget, nor omit deadlines and let requests hang without limit.

## 8. Failover depends on ordering and resolver updates

With `pick_first`, endpoint ordering can create operational preference. If the resolver always returns a remote-region backend first, the client may routinely pick the remote region even when closer backends exist. Therefore:

- Define endpoint ordering intentionally if specific preference is desired.
- Do not treat DNS order as a guaranteed priority mechanism if the provider makes no such promise.
- Observe resolver output and which backend actually receives RPCs.
- When an endpoint is removed, wait for the resolver update to take effect; an in-flight RPC may still be affected separately.
- When the resolver emits a new list, re-selection behavior depends on policy implementation and subchannel state; do not assume immediate failback to the first address.

If the requirement is primary/standby with strict precedence rules, recovery back to primary, or zone-based failover, verify whether `pick_first` plus resolver ordering satisfies that policy in the active runtime or whether a dedicated policy/control plane is required.

## 9. Integrating a shared channel in Spring

In a Spring application, channels should be created once per target and reused. Example:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersGrpcConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel() {
        return ManagedChannelBuilder
                .forTarget("dns:///orders.internal:9090")
                .defaultLoadBalancingPolicy("pick_first")
                .useTransportSecurity()
                .build();
    }
}
~~~

The stub can be injected into a client service:

~~~java
import com.example.orders.rpc.OrdersGrpc;
import io.grpc.ManagedChannel;
import org.springframework.stereotype.Component;

@Component
public class OrdersClient {
    private final OrdersGrpc.OrdersBlockingStub stub;

    public OrdersClient(ManagedChannel ordersChannel) {
        this.stub = OrdersGrpc.newBlockingStub(ordersChannel);
    }
}
~~~

Do not create a new channel for every request or every time a backend fails. A long-lived channel manages resolvers, subchannels, and connections; constantly creating channels increases DNS lookups, TCP/TLS handshakes, and resource consumption.

If the application has multiple targets, declare separate channel beans with clear qualifiers. Exact property configuration depends on the Spring gRPC starter in use; the example above shows the direct gRPC Java API.

## 10. Testing failover

A test with only one server cannot prove `pick_first` switches to a backup endpoint. You need multiple identifiable endpoints, a resolver returning a list in a known order, and the ability to stop the active backend:

| Scenario | What to verify |
|---|---|
| A is ready, B is ready | New RPCs go through A when A is selected first |
| A cannot open a connection, B is ready | Channel can connect to B and new RPCs succeed |
| A is serving and then stopped | In-flight RPCs may fail; new RPCs can use B after failover |
| A recovers after B was chosen | Re-selection behavior follows implementation/resolution; do not assume instant failback |
| Both A and B are unavailable | RPC fails or waits per wait-for-ready/deadline |
| Resolver removes A from the list | New RPCs stop picking A after the update is applied |
| Server returns `INVALID_ARGUMENT` | Not treated as a connection error for failover |
| B has invalid TLS | B cannot become a working connection; certificate error must be fixed |
| Server stream interrupted on A | Client opens a new RPC to the selected backend and resumes via cursor if needed |

In tests, you can use a custom `NameResolverProvider` to return A and B, plus two in-process servers or TCP test servers to simulate backends. To test real connection/TLS errors, use an appropriate TCP transport; in-process tests do not fully simulate handshakes, DNS, and network failures.

## 11. Observing failover behavior and limits

To verify whether failover is working, observe the resolver, subchannels, and RPCs together:

- Endpoint list and ordering returned by the resolver.
- Subchannel counts in `READY`, `CONNECTING`, and `TRANSIENT_FAILURE`.
- Actual backend receiving new RPCs.
- Time from when an endpoint fails until the replacement endpoint becomes `READY`.
- Rate of `UNAVAILABLE`, `DEADLINE_EXCEEDED`, and TLS errors.
- Number of in-flight RPCs that failed while a backend stopped.
- Retry/reconnect counts and stream resume outcomes.

An endpoint may still accept connections while processing very slowly. `pick_first` does not measure latency or CPU load on its own to switch to a faster endpoint. If selection based on load, zone priority, or weights is needed, use an appropriate policy/control plane and measure effectiveness in a realistic environment.

## 12. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| `pick_first` balances load across all backends | It prefers one active subchannel at a time |
| Failover lets an in-flight RPC continue on another backend | In-flight RPCs may fail; new RPCs use the replacement endpoint |
| Every server error triggers failover | Policy reacts primarily to connection state; business status does not mean connection failure |
| Having multiple IPs guarantees failover works | The resolver must supply distinct endpoints and the backup endpoint must be reachable |
| A `READY` backend means the application is completely healthy | `READY` mainly reflects connectivity; application-level health/readiness is still needed |
| `waitForReady` guarantees success | The deadline still limits waiting time |
| `pick_first` always returns to the first endpoint when it recovers | Failback depends on policy, resolver updates, and subchannel states |

**Key takeaway:** `pick_first` prefers one connectable subchannel and can try another endpoint when the chosen connection becomes unavailable. Failover gives **new RPCs** a chance to use a replacement backend; it does not migrate an active RPC to another backend. Ensure the resolver provides backup addresses, configure TLS/readiness/deadlines properly, separate connection errors from business errors, and design dedicated retry/resume logic for unary calls with side effects or server streams.
