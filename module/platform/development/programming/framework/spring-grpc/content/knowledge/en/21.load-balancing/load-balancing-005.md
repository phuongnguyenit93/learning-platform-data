# Connecting to multiple server instances

## 1. A service can run on multiple instances

In **SPRING_GRPC**, the client calls the server using gRPC Java, with stubs generated from Protocol Buffers contracts and typically managed inside a Spring application. When higher throughput or availability is needed, the same service can run across multiple server instances. Each instance implements the same API, while having its own address and process lifecycle.

For example, an order management service has three instances:

~~~text
orders service
  ├── instance A: 10.50.0.11:9090
  ├── instance B: 10.50.0.12:9090
  └── instance C: 10.50.0.13:9090
~~~

The client needs a target representing the service, a mechanism to discover endpoints, and a policy to select backends. Each new RPC is dispatched by the gRPC channel to an appropriate subchannel. As a result, the application does not have to pick IPs manually inside each business method.

Three concepts to distinguish:

- **Server instance:** a process/replica serving the gRPC service.
- **Endpoint:** an address the client can connect to, usually a host and port.
- **ManagedChannel:** a long-lived client object managing name resolution, load balancing, subchannels, and transports for RPCs.

One channel does not mean one server instance. One channel can know about multiple endpoints and manage multiple subchannels. Conversely, creating three channels to three fixed addresses does not by itself provide discovery, instance updates, or resilient load distribution.

## 2. Instances must be compatible with the same contract

Before connecting to multiple instances, backends must expose the same service/methods and be compatible with the protobuf schema used by the client. Example:

~~~proto
syntax = "proto3";

package orders.v1;

option java_multiple_files = true;
option java_package = "com.example.orders.rpc";

service OrdersService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderReply);
}

message GetOrderRequest {
  string order_id = 1;
}

message GetOrderReply {
  string order_id = 1;
  string status = 2;
}
~~~

Instances A, B, and C must register service `orders.v1.OrdersService` and handle method `GetOrder` under the same contract. Versions can be rolled out via rolling upgrades, but the schema must maintain compatibility per Protocol Buffers rules: never reuse deleted field numbers, never make breaking field-type changes, and plan carefully when adding or removing fields.

Multiple instances using the same port in the example does not mean they run on the same machine. Each instance can reside on a different host, container, or pod; the port is the port advertised by the endpoint to the client.

If an instance runs an incompatible API version, the load balancer may treat it as a normal backend and the client will receive unpredictable errors. Therefore, rollouts must ensure every instance published into discovery is compatible with active clients.

## 3. One channel connects to a service target, not hard-coded replicas

In most applications, the client should connect to a **service target**:

~~~text
dns:///orders.internal:9090
~~~

The resolver resolves the target into endpoints. The load balancing policy creates/updates subchannels and picks a backend for each new RPC. With DNS returning multiple addresses and the `round_robin` policy, a single channel can distribute RPCs across ready instances.

~~~mermaid
flowchart TD
    A["OrdersClient / generated stub"] --> B["Single ManagedChannel"]
    B --> C["Name resolver"]
    C --> D["Endpoint list A, B, C"]
    D --> E["Load balancing policy"]
    E --> F["Subchannel A"]
    E --> G["Subchannel B"]
    E --> H["Subchannel C"]
    F --> I["Server instance A"]
    G --> J["Server instance B"]
    H --> K["Server instance C"]
~~~

This model allows the resolver to add or remove endpoints while the client keeps the channel. When the list changes, the channel receives a new resolution result and the policy adjusts subchannels.

Do not create a new channel for each request or manually rotate IPs using a counter inside a service method. That approach bypasses readiness, connection errors, endpoint updates, TLS, and transport lifecycle management.

## 4. DNS can provide multiple addresses

If the service's DNS returns multiple A/AAAA records, gRPC's DNS resolver can provide multiple endpoints to the channel. Example:

~~~text
orders.internal. A 10.50.0.11
orders.internal. A 10.50.0.12
orders.internal. A 10.50.0.13
~~~

Client uses the target:

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///orders.internal:9090")
        .defaultLoadBalancingPolicy("round_robin")
        .useTransportSecurity()
        .build();
~~~

The resolver returns addresses; the policy chooses how to use them. `round_robin` can distribute new RPCs across `READY` subchannels. If there is only one endpoint or only one subchannel ready, the client cannot distribute across other instances.

DNS does not always expose individual replicas. In Kubernetes, DNS for a ClusterIP Service usually returns one virtual IP; further distribution to pods is handled by the network/service proxy. A headless Service can return individual pod IPs so client-side load balancing sees each instance.

Test DNS from the exact network/namespace where the client runs. TTL and caches can cause clients to continue seeing old addresses for some time after a deployment changes.

## 5. Connecting directly to multiple endpoints with a custom resolver

A system with its own service registry or control plane can use a custom `NameResolver` to turn an instance list into a `ResolutionResult`. Example constructing the result:

~~~java
import io.grpc.Attributes;
import io.grpc.EquivalentAddressGroup;
import io.grpc.NameResolver;

import java.net.InetSocketAddress;
import java.util.List;

List<EquivalentAddressGroup> addresses = List.of(
        new EquivalentAddressGroup(
                new InetSocketAddress("10.50.0.11", 9090)),
        new EquivalentAddressGroup(
                new InetSocketAddress("10.50.0.12", 9090)),
        new EquivalentAddressGroup(
                new InetSocketAddress("10.50.0.13", 9090))
);

NameResolver.ResolutionResult result =
        NameResolver.ResolutionResult.newBuilder()
                .setAddresses(addresses)
                .setAttributes(Attributes.EMPTY)
                .build();

// Custom NameResolver delivers the result to the listener:
listener.onResult(result);
~~~

This snippet illustrates creating a result inside a custom resolver; `listener` is provided through the `NameResolver` lifecycle. Applications using the built-in DNS resolver do not need to construct `ResolutionResult` manually.

A custom resolver needs to:

- Fetch endpoints from an authoritative discovery source.
- Publish only instances meeting the chosen readiness/health criteria.
- Emit updates when instances are added, removed, or change addresses.
- Report meaningful resolution errors if the registry is unreachable.
- Close watchers, subscriptions, or registry clients when the resolver shuts down.

Do not create a resolver that polls the registry on every RPC. The resolver lives alongside the channel and updates the endpoint list according to the provider's mechanism.

## 6. Choosing a policy with multiple instances

| Policy | How multiple instances are used | Best suited when |
|---|---|---|
| `pick_first` | Prefers one connectable subchannel; tries others when needed | Infrastructure already load-balances or you want a primary connection with backup addresses |
| `round_robin` | Distributes new RPCs across `READY` subchannels | Client directly sees multiple replicas and wants to utilize them |
| Control-plane policy | Can apply weighted, priority, locality, or advanced routing if provider supports it | Canary rollouts, zone preference, or policies based on endpoint attributes are needed |

No policy automatically measures total CPU load or business cost to guarantee even distribution. Round robin distributes in turn among ready subchannels; one backend may still become busier if it receives heavier requests or long-lived streams.

If the resolver provides a service config containing a policy, the policy in the service config can determine the active behavior instead of the channel's default value. Check which policy/providers are loaded and what configuration the resolver delivers to the client.

## 7. Integrating a shared ManagedChannel in Spring

A channel is a long-lived, thread-safe resource capable of serving multiple stubs/RPCs. In Spring, declare one bean per service target:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersGrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel() {
        return ManagedChannelBuilder
                .forTarget("dns:///orders.internal:9090")
                .defaultLoadBalancingPolicy("round_robin")
                .useTransportSecurity()
                .build();
    }
}
~~~

Client service uses the injected channel:

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

If the application calls multiple services, create a separate channel bean for each target and use qualifiers to prevent mis-injection. Configuring endpoints, TLS credentials, resolvers, and policies via properties depends on the specific Spring gRPC starter; the snippet above demonstrates the direct gRPC Java API.

When the application shuts down, Spring calls `shutdown()` so the channel stops accepting new RPCs and closes resources per lifecycle. For services requiring controlled shutdown, you can wait with `awaitTermination(...)` for a bounded timeout and then call `shutdownNow()` if needed.

## 8. Each RPC is sent to one instance

The load balancer selects a backend when the RPC starts. One unary RPC goes to one instance; a server streaming RPC also stays pinned to the instance that accepted that call for the duration of the RPC:

~~~text
GetOrder RPC #1  -> instance A -> response
GetOrder RPC #2  -> instance B -> response
WatchProgress    -> instance C -> event 1, 2, 3, ...
~~~

gRPC does not split individual messages of a single server stream across multiple instances. HTTP/2 allows multiplexing many RPCs over a connection, but each RPC still has one handling backend.

If instance C stops mid-stream, the RPC may fail. The channel can choose another instance for a new RPC, but cannot automatically move the rest of the stream to instance D. The client must reconnect and send a cursor/checkpoint if it needs to continue without missing events.

Similarly, if a unary RPC already caused side effects on A before the connection dropped, retrying on B can duplicate side effects. Use an idempotency key or status-query API to handle uncertain outcomes.

## 9. State must be shared across instances

When a client can send two consecutive RPCs to two different replicas, the application should not rely on state stored only in one instance's RAM if business logic requires continuity.

Example:

~~~text
RPC 1 -> instance A: create job J-42
RPC 2 -> instance B: read progress of job J-42
~~~

If job state is kept only in A's memory, B cannot return accurate progress. Data that may need sharing includes:

- Job/session state and processing status.
- Event logs, sequences, and checkpoints so streams can resume.
- Idempotency keys and processed results.
- Business configuration or data requiring consistency across replicas.

Common choices include a database, distributed cache, or suitable event broker. Local caches remain useful for reconstructible data, but should not be the sole source of truth for state needed across all instances.

Sticky sessions can reduce backend switching, but do not replace durable storage: instances can still restart or be removed from service. Use affinity only when clearly required and backed by a fallback plan.

## 10. Readiness, health checking, and load limits

An endpoint appearing in DNS/registry does not mean the instance is ready. The path from instance discovery to accepting RPCs can include:

1. Resolver receives the address.
2. Channel creates a subchannel.
3. TCP connects and TLS handshake completes.
4. Health/readiness checks confirm the instance can serve.
5. Policy puts the `READY` subchannel into the picker.

If no subchannel is ready, RPCs can fail or wait when using `withWaitForReady()`. The deadline still caps total waiting time:

~~~java
GetOrderReply reply = stub
        .withWaitForReady()
        .withDeadlineAfter(3, java.util.concurrent.TimeUnit.SECONDS)
        .getOrder(request);
~~~

`waitForReady` does not add more instances and does not let requests wait forever. It simply gives the channel a chance to wait for a suitable connection within the deadline budget.

Having multiple instances also does not mean load can be distributed without limits. Track concurrent RPCs, processing time, long-lived stream counts, connection pool/HTTP2 concurrency, and per-replica resource limits. Under overload, apply admission control, quotas, or return appropriate statuses instead of letting queues grow without bound.

## 11. Graceful shutdown and updating the instance list

When rolling out a new version, platforms usually add new instances before removing old ones. To avoid routing new RPCs to an instance about to stop:

- Advertise an instance only after the service has bound its port and is ready.
- During shutdown, mark the instance as no longer accepting new traffic before stopping the process.
- Allow in-flight RPCs a grace period to finish.
- Cancel or close long-lived streams according to a documented policy; clients reconnect with a cursor if needed.
- Close channels/transports and registry subscriptions cleanly per lifecycle.

Resolvers may take time to receive DNS/registry updates; caches and TTLs prevent endpoint removal from being instantaneous across all clients. Therefore, server-side graceful shutdown must still reject new RPCs in a controlled way and give existing RPCs time to finish.

Do not assume removing a pod from a registry immediately closes all existing connections. Subchannels with active transports may continue being used until the channel receives an update or transport state changes.

## 12. Testing multi-instance connections

A test with a single server cannot prove the channel connects to multiple instances. Test suites need at least two backends distinguishable by instance ID and a resolver returning the corresponding endpoints.

| Scenario | What to verify |
|---|---|
| Resolver returns A, B, C | Channel receives all endpoints |
| `round_robin`, all backends `READY` | New unary RPCs are distributed across multiple instances |
| `pick_first` with multiple endpoints | One backend is preferred; others may be tried when needed |
| One instance cannot connect | New RPCs can use another ready instance per policy |
| Resolver adds/removes an instance | Channel updates subchannels according to the new list |
| Instance removed while RPC is running | Verify both in-flight RPCs and new RPCs have expected outcomes |
| Server stream interrupted | Client reconnects and resumes via cursor if contract supports it |
| Two instances run different schemas | Detect compatibility issues during rollout |
| TLS across all endpoints | Every instance authenticates with matching authority/trust |
| Spring context shutdown | Channel and resources close per lifecycle |

For custom resolvers, use a test provider emitting multiple `EquivalentAddressGroup` entries. For DNS, Kubernetes, and TLS, write integration tests in a corresponding network environment; in-process tests do not fully simulate DNS caches, TCP, certificates, or proxies.

## 13. Observing distribution and errors per instance

To know whether clients truly use multiple server instances, record which backend handled each RPC rather than just looking at replica counts in deployment manifests:

- RPC count by service, method, and instance ID.
- Subchannel counts by state (`READY`, `CONNECTING`, `TRANSIENT_FAILURE`).
- Endpoint count returned by the resolver and timestamps when lists change.
- Latency, status codes, and error rate per instance.
- Open stream count, stream age, and reconnect count.
- Time from when an instance is advertised until its subchannel becomes ready.
- Count of graceful shutdowns ending with in-flight RPCs still running.

Do not log tokens or sensitive payloads just to distinguish backends. Use a non-sensitive instance ID in logs/metrics and a correlation ID to link an RPC to a trace.

If one instance receives fewer requests, check whether the resolver returns its address, whether its subchannel is `READY`, whether a service config overrides the policy, and whether requests are pinned to one backend by affinity.

## 14. Common implementation mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Hard-coding one replica IP | Client misses new instances or address changes | Use a service target and resolver |
| Creating a new channel for every request | Wastes connections, TLS handshakes, and resources | Use a long-lived channel bean |
| Having multiple replicas while resolver returns one virtual IP | Client does not distribute directly to replicas | Decide whether load balancing lives at client or infrastructure |
| Using `round_robin` when only one subchannel is `READY` | RPCs still concentrate on one instance | Check readiness and connection states |
| Storing session/job state only in one instance's RAM | Next RPC hitting another instance loses state | Use a shared state store or controlled affinity |
| Assuming streams migrate automatically when an instance stops | Current RPC fails and data may be disrupted | Reconnect/resume via cursor |
| Removing an instance immediately at shutdown start | In-flight RPCs are cut off abruptly | Use graceful shutdown and a grace period |
| Skipping cross-replica schema compatibility checks | Clients see inconsistent behavior depending on backend | Perform compatible rollouts and multi-version tests |

**Key takeaway:** To connect to multiple server instances, clients should use a single `ManagedChannel` pointing to a service target, a resolver providing endpoints, and a load balancing policy selecting subchannels for each new RPC. Instances must share compatible contracts, have proper readiness and TLS configuration, and share required state. An active RPC remains pinned to the backend that accepted it; failover for new RPCs does not automatically recover streams or side effects. Manage channels through the Spring lifecycle, test with multiple real backends, and monitor per-instance distribution.
