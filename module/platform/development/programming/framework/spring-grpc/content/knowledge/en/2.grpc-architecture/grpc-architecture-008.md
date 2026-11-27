# Load balancing and name resolution

## Learning objectives

After this lesson, you can:
- Explain name resolution and client-side load balancing in gRPC.
- Distinguish NameResolver, LoadBalancer, Subchannel, and connection.
- Configure a DNS target and the `round_robin` policy in Spring.

## 1. Why does gRPC need name resolution and load balancing?

A Spring application typically calls a logical target like **orders.internal:8443** rather than hardcoding a single server's IP. In deployment environments, a service can have multiple instances, addresses change during scaling or restarts, and an instance may become temporarily unavailable.

Two mechanisms work together to solve this:

- **Name resolution** discovers available backend addresses from a logical target, such as DNS or a discovery system.
- **Load balancing** picks an appropriate backend for each RPC based on the address list and connection states.

In grpc-java, both mechanisms are managed inside **ManagedChannel**. The application creates the Channel and stubs; each RPC passes through the LoadBalancer's picker to select an available Subchannel/transport.

~~~mermaid
flowchart LR
    A["Spring service"] --> B["Generated stub"]
    B --> C["ManagedChannel"]
    C --> D["NameResolver"]
    D --> E["Backend list"]
    E --> F["LoadBalancer"]
    F --> G["Picker chooses Subchannel"]
    G --> H["HTTP/2 connection"]
    H --> I["gRPC server instance"]
~~~

For example, the logical target **dns:///orders.internal:8443** can resolve to three addresses:

~~~text
orders.internal:8443
  - 10.20.1.11:8443
  - 10.20.1.12:8443
  - 10.20.1.13:8443
~~~

That list is a discovery result, not a guarantee that all three backends are healthy. The LoadBalancer and transport continue monitoring states to select a viable path.

## 2. NameResolver: from target to addresses

### 2.1. Targets with scheme and authority

A gRPC Channel is created from a target. The target may include a **scheme** to choose the NameResolver:

| Example target | Typical resolver | Meaning |
| --- | --- | --- |
| **dns:///orders.internal:8443** | DNS resolver | Resolves host addresses via DNS |
| **static/custom target** | Application/framework-provided resolver | Uses a custom endpoint list or service discovery |
| **xds:///orders** | xDS resolver if integrated | Receives endpoint/policy configuration from a control plane |

Supported URI syntax and schemes depend on the resolver providers loaded at runtime. Standard grpc-java includes a built-in DNS resolver. Never assume a custom scheme works automatically just because it appears in a target string.

**Authority** is the logical identity/destination of the service. It can be used to determine the resolver and verify TLS; it is not synonymous with the chosen backend's IP.

### 2.2. What does the resolver return?

The NameResolver does not call the service directly. It notifies the Channel about resolved addresses and optionally a service config:

~~~text
Target: dns:///orders.internal:8443

NameResolver:
  address group A: 10.20.1.11:8443
  address group B: 10.20.1.12:8443
  address group C: 10.20.1.13:8443
  optional service config: round_robin
~~~

In grpc-java, resolution results are represented by objects such as **EquivalentAddressGroup** and **ResolvedAddresses**. The resolver can emit updated results as addresses change, rather than resolving only once at Channel creation.

An **address group** can contain one or more equivalent socket addresses. The LoadBalancer takes these groups to create or update Subchannels. Do not equate the number of DNS IPs with the number of RPCs or connections.

### 2.3. DNS is not complete load balancing

DNS can return multiple addresses, yet having multiple IPs does not automatically distribute every RPC evenly:

- The resolver may return multiple addresses to the Channel.
- The LoadBalancer policy decides which address is chosen for an RPC.
- The transport can maintain long-lived connections to selected backends.
- DNS cache/TTL and refresh intervals affect when the Channel sees changes.

Thus, **DNS round-robin** at the name-resolution layer and the **round_robin policy** at the gRPC client layer are two different mechanisms. DNS supplies addresses; the policy decides how those addresses are used.


## 3. Components in client-side load balancing

| Component | Responsibility |
| --- | --- |
| **NameResolver** | Resolves targets and reports addresses/service configs |
| **LoadBalancer** | Creates/updates Subchannels and determines backend selection strategy |
| **Subchannel** | Represents a logical connection path to an address group |
| **Connection/transport** | Actual network connection, usually TCP/TLS and HTTP/2 |
| **Picker** | Chooses a Subchannel for a new RPC based on current state |
| **ManagedChannel** | Coordinates resolver, policy, subchannels, and RPC lifecycle |

Flow when a new RPC starts:

1. Caller invokes a method on the generated stub.
2. The stub creates an RPC through ManagedChannel.
3. The Channel uses the LoadBalancer's current picker.
4. The picker selects a ready Subchannel or instructs waiting/failing per policy.
5. The RPC travels over the Subchannel's connection to the backend.
6. When resolver results or Subchannel states change, the LoadBalancer updates the picker for subsequent RPCs.

**The picker does not re-select a backend per message inside a streaming RPC.** A streaming RPC stays bound to a single transport/HTTP/2 stream for its entire lifetime. Load balancing primarily chooses the backend when the RPC begins.

## 4. Two core policies: pick_first and round_robin

### 4.1. pick_first

**pick_first** tries addresses in order and picks one ready connection path. While that path stays healthy, subsequent RPCs usually keep using the selected backend.

Advantages:

- Simple model, typically maintains fewer connections.
- Suitable when there is a single stable endpoint or an upstream proxy/LB already distributes load.
- Can try the next address if the current one cannot connect, depending on state and implementation.

Limitations:

- When multiple backends are healthy, load can concentrate on a single backend.
- A single Channel does not necessarily rotate RPCs across addresses.
- If the chosen backend remains healthy yet overloaded, this policy does not automatically spread load to other instances.

### 4.2. round_robin

**round_robin** maintains Subchannels for address groups and cycles through ready Subchannels. For example, when all three backends are READY:

~~~text
RPC 1 -> backend A
RPC 2 -> backend B
RPC 3 -> backend C
RPC 4 -> backend A
RPC 5 -> backend B
~~~

When a backend is not ready, the picker skips it and distributes across the remaining backends according to their current state.

Advantages:

- Distributes new RPCs across multiple backends.
- Useful when the client connects directly to multiple instances.
- Does not require opening a new Channel per backend or per request.

Limitations:

- Does not guarantee equal CPU load, RPC duration, or streaming message counts.
- Long-lived RPCs continue occupying their chosen backend until completion.
- Requires the resolver to return sufficient endpoints and Subchannels to actually be ready.
- Does not replace health checks, concurrency limits, or server-side admission control.

### 4.3. Quick comparison

| Criterion | pick_first | round_robin |
| --- | --- | --- |
| Typical backend usage | One selected ready Subchannel | Rotates across READY Subchannels |
| Distribution of new RPCs | Not aimed at spreading evenly across instances | Yes, cyclic across ready instances |
| Connections | Usually fewer | May maintain multiple connections |
| Best suited for | Single endpoint or pre-balanced proxy | Client directly aware of multiple backends |
| Key precondition | Address resolves and is reachable | Resolver returns multiple address groups; policy is supported |

Neither policy is universally better. If the client only sees **a single proxy VIP address**, client-side `round_robin` cannot know about the backends hidden behind that VIP.

## 5. Configuring round_robin in Spring with grpc-java

Example using the DNS resolver and service config to select **round_robin**. The Channel is a shared bean across RPCs:

~~~java
package dev.example.orders.client;

import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.List;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderGrpcClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel orderChannel() {
        Map<String, ?> serviceConfig = Map.of(
                "loadBalancingConfig",
                List.of(Map.of("round_robin", Map.of())));

        return ManagedChannelBuilder
                .forTarget("dns:///orders.internal:8443")
                .defaultServiceConfig(serviceConfig)
                .build();
    }
}
~~~

Points to note:

- **forTarget(...)** retains the logical target; the DNS resolver resolves the hostname into addresses.
- **defaultServiceConfig(...)** provides a default service config where **loadBalancingConfig** selects the **round_robin** policy. Exact APIs and configurability depend on the grpc-java version; use compatible dependencies.
- The resolver must return multiple address groups for `round_robin` to have multiple backends to choose from.
- The Channel should be reused and shut down when the Spring context stops.
- This example omits TLS credential setup; production environments must use proper security configuration and avoid plaintext for endpoints outside trusted boundaries.

If no policy is specified and the resolver provides no service config, grpc-java typically defaults to **pick_first**. Verify behavior for the version and providers loaded in your application.


### 5.1. Service config and scope of application

Service config can describe load-balancing policies and per-service/method behaviors. Minimal policy configuration example:

~~~json
{
  "loadBalancingConfig": [
    { "round_robin": {} }
  ]
}
~~~

If the NameResolver supplies its own service config, precedence between the resolver's config and the default service config depends on Channel APIs/settings. Ensure configuration comes from trusted sources and prevent untrusted discovery sources from arbitrarily altering policies or RPC behavior.

Do not add manual IP-selection logic inside business services. Doing so couples callers to topology and bypasses the Subchannel state tracked by the gRPC runtime.

## 6. Client-side LB vs. infrastructure proxy/load balancer

There are two common places to distribute traffic:

- **Client-side load balancing:** the resolver gives each client the endpoint list; the gRPC client's LoadBalancer picks a backend for each new RPC.
- **Proxy/server-side load balancing:** the client connects to a proxy/VIP address; the proxy or service mesh infrastructure distributes RPCs to backends.

~~~mermaid
flowchart TB
    subgraph ClientSide["Client-side load balancing"]
      C1["Spring client"] --> CH["ManagedChannel"]
      CH --> R["Resolver: A, B, C"]
      R --> LB["round_robin picker"]
      LB --> A["Backend A"]
      LB --> B["Backend B"]
      LB --> C["Backend C"]
    end
    subgraph ProxySide["Proxy / server-side load balancing"]
      C2["Spring client"] --> VIP["Proxy / VIP"]
      VIP --> D["Backend A"]
      VIP --> E["Backend B"]
      VIP --> F["Backend C"]
    end
~~~

| Criterion | Client-side | Proxy/server-side |
| --- | --- | --- |
| Client knows backends | Yes, resolver provides endpoints | Usually only knows proxy/VIP |
| Decision maker | gRPC LoadBalancer inside client | Proxy, gateway, or service mesh |
| Backend state visibility | Via client-managed Subchannels | Via proxy health/endpoint state |
| Operations | Requires consistent resolver/config on clients | Requires operating proxy and route configs |
| Good fit when | Client accesses multiple endpoints directly | Centralizing policy, auth, or routing in infrastructure |

gRPC usually holds long-lived HTTP/2 connections. An **L4 load balancer** that only distributes TCP connections can pin a long-lived Channel to one backend, so it does not necessarily balance individual RPCs inside that connection. If per-RPC distribution is needed, use client-side LB or a gRPC/HTTP2-aware proxy at the appropriate layer.

Both models can coexist, but avoid unintended double load balancing. For instance, client `round_robin` across multiple proxy endpoints where each proxy also picks backends can make paths hard to observe and predict.

## 7. Resolver address updates and connection states

Name resolution is not a one-shot operation. When DNS records or a service registry change, the resolver can emit a new address list. The LoadBalancer compares that list against existing Subchannels to add, update, or remove connection paths.

Common connection states in grpc-java:

| State | Meaning |
| --- | --- |
| **IDLE** | No activity requiring a connection, or idle |
| **CONNECTING** | Establishing transport |
| **READY** | Subchannel has a ready connection |
| **TRANSIENT_FAILURE** | Connection temporarily failed; may retry with backoff |
| **SHUTDOWN** | Channel/Subchannel is shutting down or shut down |

When a backend disappears from resolver results, the LoadBalancer can stop selecting its Subchannel and clean up resources once associated RPCs finish or close per policy. Active streaming RPCs do not migrate to another backend mid-stream; if the connection drops, the stream usually fails and the application must decide whether to open a new RPC.

### 7.1. DNS TTL, caching, and convergence time

Updating a DNS record does not mean every client sees the new address immediately. Convergence time depends on:

- TTL and caches of the DNS resolver, OS, and runtime.
- Resolver refresh frequency and how it publishes updates.
- DNS negative caching when a hostname does not yet exist.
- Backoff when DNS queries or backend connections fail.
- Proxy or service mesh caches/routes at other layers.

Do not set an ultra-short TTL expecting every client to switch backends instantly; overly frequent refreshes also increase DNS load. For environments needing fast discovery and rich health states, a dedicated resolver/service discovery system may fit better than plain DNS.

### 7.2. When a backend fails

If a READY Subchannel loses its connection, gRPC can transition it into transient failure, attempt reconnection with backoff, and update the picker. With `round_robin`, remaining READY Subchannels can still accept new RPCs.

However, reconnection does not mean automatic retry of every sent RPC. A unary RPC may have already been processed by the server before the connection dropped; a streaming RPC may have already exchanged many messages. Re-invoking must consider idempotency, business state, and retry policies.

## 8. Health checking and readiness

**Connection READY** only indicates the transport can send RPCs; it does not guarantee the backend application is healthy at the business level. A server can have an open port while its backing database is broken.

gRPC defines a **Health Checking Protocol** with a standard service such as **grpc.health.v1.Health**. Clients or load-balancing policies can use health state to decide which endpoints are eligible if the client, server, and resolver/policy support that mechanism.

Distinguish clearly:

- **Transport readiness:** a connection/HTTP2 transport is up.
- **Application health:** server reports SERVING status for a specific service.
- **Infrastructure readiness:** orchestration/proxy permits the endpoint to receive traffic.
- **Liveness:** process is alive and may need restarting if hung.

Do not treat Subchannel READY as a health check result. When using health checking, enable the corresponding health service and verify policy configuration; merely adding a dependency or declaring the service does not automatically make clients filter out unhealthy backends.

## 9. Spring integration: Channel lifecycle and configuration

In a Spring application, **ManagedChannel** should be managed as a shared bean. Stubs are created from the Channel and injected into business services. Do not create a Channel per HTTP request or per RPC, as that increases connection counts, TLS handshakes, and discovery overhead.

Stub wiring example:

~~~java
@Bean
OrderServiceGrpc.OrderServiceBlockingStub orderStub(
        ManagedChannel orderChannel) {
    return OrderServiceGrpc.newBlockingStub(orderChannel);
}
~~~

The Channel bean in section 5 has **destroyMethod = "shutdown"** to request closure when the Spring context stops. In production, you may need to wait for in-flight RPCs to complete within a bounded timeout before forcing shutdown.

If using a Spring gRPC starter, configure targets, name resolvers, load-balancing policies, and TLS using that starter version's API. The grpc-java example above illustrates the foundational Channel mechanism; do not assume all starters share the exact same property names or auto-register custom resolvers.

### 9.1. When is a custom NameResolver needed?

DNS works well when hostnames/records suffice to describe endpoints. A custom resolver may be needed when addresses come from:

- An internal service registry.
- A control plane or discovery system with custom metadata.
- Dynamic endpoint lists in test environments.
- Configuration sources needing to attach attributes for the LoadBalancer.

A custom resolver must publish address results via the grpc-java API, report resolution errors, refresh when data changes, and release resources on shutdown. It **should not** choose a backend per RPC itself; that is the LoadBalancer's responsibility.

If a custom policy is needed, implement **LoadBalancerProvider** and register the provider via the service-loader/runtime mechanism. Do not write custom resolvers or policies if DNS or built-in policies already meet requirements.

## 10. Security during resolution and backend selection

Name resolution directly affects where clients send data. A misconfigured resolver or untrusted discovery source can direct clients to unintended endpoints.

- Use DNS/service registry sources inside trusted zones with controlled record-update permissions.
- Configure TLS to verify server identity; never disable hostname verification just because backends have dynamic IPs.
- When connecting to IPs returned by a resolver, preserve the proper **authority/hostname** for certificate verification and architecture-level routing.
- Do not treat a resolved IP address as proof that the backend is authorized.
- If the resolver receives service config from a control plane, authenticate the source and restrict accepted policies.
- Avoid logging tokens or sensitive data in resolution logs or endpoint attributes.

In mTLS environments, certificate identity and authorization must still be checked on the server/gateway. The LoadBalancer only chooses the path; it does not replace authentication and authorization.


## 11. Diagnosing load balancing issues

| Symptom | Common cause | What to check |
| --- | --- | --- |
| All RPCs hit a single backend | `pick_first` policy; resolver returns one address group; or client only sees a VIP | Check target, resolver output, and service config |
| `round_robin` does not spread load | Only one Subchannel READY; policy not loaded; resolver not returning multiple endpoints | Check service config, provider, and individual Subchannel states |
| DNS changes yet client keeps calling old IP | DNS cache/TTL or resolver has not refreshed | Inspect resolution output and refresh cadence |
| Failing backend still receives traffic | No health checking/readiness or connection state not updated | Distinguish transport READY from application health |
| Losing one backend fails many RPCs | RPCs bound to that connection; retries not configured appropriately | Check statuses, reconnects, and idempotency |
| Backend change breaks active streams | Streaming RPCs do not migrate between backends | Design application-level resume/cursor and reconnect |
| TLS fails after DNS returns new IP | Authority/certificate mismatch or wrong trust chain | Check hostname verification, SAN, and TLS config |
| Client CPU/resources climb with `round_robin` | Too many endpoints/connections or constant refreshes | Bound endpoint count, refresh rate, and Channel lifecycle |

Monitor **resolved address count**, **Subchannels by state**, **RPCs per backend if instrumented**, **connection churn**, **reconnect/backoff**, latency, and status codes. Do not rely on server CPU alone to judge whether a policy balances evenly; one backend may receive fewer RPCs yet handle very long-lived streams.

## 12. Testing name resolution and load balancing

Effective testing verifies both layers:

1. **Resolver test:** logical target returns expected endpoints when the discovery source changes; handles DNS errors and refreshes.
2. **Policy test:** when multiple Subchannels are READY, the picker chooses according to policy; when one Subchannel fails, new RPCs stop going to the unready path.
3. **Integration test:** start multiple test servers, call through a Channel, and observe distribution; do not infer from a single call.
4. **Failure test:** stop one backend, observe status/reconnect, and verify remaining backends continue serving new RPCs.
5. **Streaming test:** kill the backend holding a stream, verify the client gets an error and resumes with a cursor if the use case requires it.
6. **TLS test:** verify every backend presents a valid identity/certificate matching the authority used.

**In-process transport** is useful for testing services and statuses, but does not prove DNS, TCP, TLS, or proxies work correctly. Testing load balancing over the network requires multiple real endpoints or a controllable test resolver plus instrumentation identifying which backend received each RPC.

## 13. Hands-on lab and self-check questions

### Hands-on lab

1. Create a Spring client using **dns:///orders.internal:8443** and a shared ManagedChannel.
2. Configure **pick_first**, then **round_robin** via service config. Record the difference when the resolver returns one versus multiple address groups.
3. Run three backends hosting the same service, send multiple unary RPCs, and observe which backend receives each call. Ensure all Subchannels are READY before evaluating distribution.
4. Stop one backend; track Subchannel states, RPC errors, and how `round_robin` continues picking the remaining backends.
5. Change the DNS record or custom resolver output; measure how long it takes the client to see the new address rather than assuming TTL equals exact convergence time.
6. Open a server-streaming RPC and then stop the backend serving that stream. Verify the stream does not automatically migrate to another backend, and design cursor/reconnect logic if needed.
7. Enable TLS with the proper hostname/authority and verify certificates across all backends.

### Self-check questions

**1. How do NameResolver and LoadBalancer differ?**  
NameResolver discovers endpoints from a target; LoadBalancer selects an endpoint/Subchannel to serve a new RPC.

**2. If DNS returns three IPs, does each RPC go to a different IP?**  
No. It depends on the policy. With **pick_first**, many RPCs may keep using one backend; **round_robin** distributes across ready Subchannels.

**3. Does round_robin equalize CPU or processing time?**  
No. It cycles new RPCs across READY Subchannels; duration and cost per RPC can differ.

**4. Why might an L4 load balancer fail to distribute gRPC RPCs evenly?**  
Because gRPC typically uses long-lived HTTP/2 connections. An L4 LB distributes TCP connections, not necessarily individual RPCs inside a connection.

**5. Does a Channel automatically migrate an active streaming RPC to another backend when its current backend dies?**  
No. An active stream usually fails with an error. The application must open a new RPC and resume via cursor/sequence if the domain supports it.

**6. Does Subchannel READY mean the backend is healthy at the business level?**  
No. READY reflects transport readiness; application-level health checking/readiness is a separate signal.

**7. Why shouldn't you create a new ManagedChannel per request?**  
Doing so increases connection counts, handshakes, and discovery overhead, and forfeits transport reuse and continuous LB management.

## Summary

**Name resolution** turns a logical target into backend addresses; **LoadBalancer** uses that list and Subchannel states to choose a path for each new RPC. In grpc-java, **ManagedChannel** coordinates the resolver, policy, picker, and connections; Spring should manage a shared Channel and configure policies deliberately. **pick_first** typically sticks to one ready backend, whereas **round_robin** spreads new RPCs across READY Subchannels when the resolver supplies multiple endpoints. DNS, health checking, proxies, TLS, and stream lifecycles all shape real-world outcomes, so test failure/reconnection and measure distribution on a running system.






