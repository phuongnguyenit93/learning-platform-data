# DNS Resolver for gRPC

The DNS resolver helps a gRPC client find the network addresses of a service from a DNS name instead of hardcoding a single instance's IP. In Spring gRPC, the client places the logical name in the target URI, such as `dns:///orders.default.svc.cluster.local:8443`; the resolver queries DNS and supplies the addresses to the channel. When addresses change, the channel can receive new resolution results while the application keeps using the same stub.

The DNS resolver only solves the **service name → endpoint addresses** step. It does not authenticate the server, check application health, or decide how requests are distributed across instances. Those responsibilities belong to TLS, health checking, and load balancing.

## 1. How Does the DNS Resolver Work?

For a target using the `dns` scheme, gRPC selects the DNS `NameResolverProvider` registered in the runtime. The resolver extracts the hostname from the target, looks up DNS addresses, and sends the result to the channel as a list of `EquivalentAddressGroup` objects.

Basic flow:

```text
Spring gRPC client
       |
       | target: dns:///orders.default.svc.cluster.local:8443
       v
ManagedChannel
       |
       v
NameResolverRegistry
       |
       v
DNS NameResolver
       |
       | A / AAAA lookup
       v
IP:port address list
       |
       v
LoadBalancer and Subchannels
       |
       v
HTTP/2 connection to service instance
```

At the DNS step, the resolver may receive multiple addresses for the same hostname. It passes those addresses to the channel; the load balancer uses the result to create or update subchannels. The resolver does not directly pick an instance for each RPC.

grpc-java's standard DNS resolver typically resolves hostnames through the JVM/platform DNS infrastructure. Query, caching, and refresh details can depend on the grpc-java version, runtime, and deployment environment.

## 2. DNS Target Structure

A common target has the form:

```text
dns:///hostname:port
```

Examples:

```text
dns:///orders.internal.example:8443
dns:///inventory.default.svc.cluster.local:9090
dns:///payments.prod.svc.cluster.local:443
```

In `dns:///...`, the scheme is `dns`, the authority is empty, and the hostname and port are in the path. The three slashes are intentional syntax, not extra characters.

| Component | Meaning |
| --- | --- |
| `dns` | Selects the DNS resolver |
| Empty authority | The resolver takes no separate authority in this target form |
| Hostname | DNS name to resolve |
| Port | gRPC port the client will connect to |

Do not parse the target manually with `split(":")`. That easily breaks on IPv6 and URIs with an authority/path. Let the gRPC resolver parse the target according to URI syntax.

For an IPv6 literal, the address syntax requires square brackets, such as `[2001:db8::10]:8443`; however, if the goal is dynamic discovery, using a DNS hostname is usually easier to manage.

## 3. DNS A and AAAA Records

DNS typically returns:

- **A record:** maps a hostname to an IPv4 address.
- **AAAA record:** maps a hostname to an IPv6 address.

A hostname may return one or more addresses. The resolver provides the addresses returned by the DNS lookup to the channel. Exact results depend on the DNS server, network configuration, JVM, and client environment.

Example of a service with two addresses:

```text
orders.internal.example
    A     10.20.1.11
    A     10.20.1.12
    AAAA  2001:db8:20::11
```

If the channel receives multiple addresses, the load balancing policy determines how they are used. A policy like `pick_first` typically picks one ready subchannel; `round_robin` can distribute RPCs across ready subchannels. Which policy is chosen depends on configuration and the providers present at runtime.

**Multiple DNS records do not guarantee that requests are evenly split.** Inspect both the address list emitted by the resolver and the actual load balancing policy.

DNS SRV records should also not be assumed as the discovery mechanism for every gRPC DNS resolver. A standard `dns:///host:port` target specifies a hostname and port; if the system relies on SRV or a special DNS convention, verify that the deployed resolver implementation supports and is configured for that behavior.

## 4. Using the DNS Resolver in Spring gRPC

In grpc-java, `ManagedChannelBuilder.forTarget(...)` lets a channel accept a target URI and choose a resolver by scheme. `forAddress(...)` is appropriate when the client already knows a specific host/port address.

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrdersGrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel() {
        return ManagedChannelBuilder
            .forTarget(
                "dns:///orders.default.svc.cluster.local:8443")
            .useTransportSecurity()
            .build();
    }

    @Bean
    OrdersGrpc.OrdersBlockingStub ordersStub(
            ManagedChannel ordersChannel) {
        return OrdersGrpc.newBlockingStub(ordersChannel);
    }
}
```

`OrdersGrpc` is an illustrative name for a stub generated from Protobuf. In a real application, use the corresponding generated class. Spring manages the channel bean and calls `shutdown()` when the context closes; do not create a new channel per RPC because a channel is a long-lived object meant to be reused across many calls.

If the Spring gRPC starter already manages channels/clients automatically, declare the target in the configuration mechanism supported by your starter version. Avoid letting the starter create a channel while also manually creating a parallel channel for the same endpoint without reason.

Comparison:

```java
// DNS discovery: target is a stable service name.
ManagedChannel byDns = ManagedChannelBuilder
    .forTarget("dns:///orders.internal.example:8443")
    .useTransportSecurity()
    .build();

// Direct address: the client already knows the specific address.
ManagedChannel direct = ManagedChannelBuilder
    .forAddress("10.20.1.11", 8443)
    .useTransportSecurity()
    .build();
```

`forAddress(...)` does not provide the same hostname-based discovery behavior as a DNS target. If instance addresses change, an application using a direct address must update its configuration or recreate the channel itself.

## 5. DNS Resolver in Kubernetes

In Kubernetes, DNS Services allow clients to use a stable name instead of Pod IPs. You must distinguish a **ClusterIP Service** from a **headless Service** because they produce different discovery behavior.

| Service Type | What DNS Typically Returns | Who Distributes Traffic? |
| --- | --- | --- |
| ClusterIP | A single stable virtual IP of the Service | Kubernetes service dataplane (e.g., kube-proxy or an equivalent implementation) |
| Headless (`clusterIP: None`) | Pod endpoint addresses matching the Service configuration | The gRPC client/load balancer can choose among the resolved addresses |

Example internal DNS name:

```text
orders.default.svc.cluster.local
```

If a client calls a ClusterIP Service, the DNS resolver usually sees only the virtual IP. In that case, the gRPC client-side load balancer does not see individual Pods; connection distribution is handled by the Kubernetes dataplane.

With a headless Service, DNS can return multiple Pod IPs. The channel can receive the endpoint list and apply a policy such as `round_robin` if that policy is configured and supported. This is useful when you want the gRPC client to manage endpoint selection, but it requires understanding readiness, endpoint publication, and DNS updates in the cluster.

Example headless Service:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: orders
  namespace: default
spec:
  clusterIP: None
  selector:
    app: orders
  ports:
    - name: grpc
      port: 8443
      targetPort: 8443
```

This is an illustrative manifest. The FQDN and namespace must match the actual cluster. Settings like `publishNotReadyAddresses`, readiness probes, and endpoint lifecycles can affect which addresses DNS publishes; do not assume a DNS record always equates to healthy application state.

## 6. Resolver Refresh, DNS Cache, and Endpoint Changes

A DNS change does not mean every channel sees the new endpoints immediately. Update propagation depends on multiple layers:

1. The DNS record is updated in authoritative DNS or Kubernetes DNS.
2. Recursive resolvers/caches may continue returning old results until the TTL expires or cache policy allows a refresh.
3. The JVM/platform DNS cache may retain results according to runtime settings.
4. The gRPC `NameResolver` must perform the next resolution and send the new result via its listener.
5. The load balancer updates subchannels; old connections may remain open for some time.

Therefore, **DNS TTL does not guarantee the exact moment a client switches to new endpoints**. You must inspect JVM DNS caching, resolver implementation/version, refresh behavior, cluster DNS caching, and connection lifecycles.

`NameResolver` has important lifecycle points:

- `start(listener)`: starts resolution and delivers `ResolutionResult`.
- `refresh()`: requests re-resolution when the channel needs an update.
- `shutdown()`: stops the resolver and releases resources.

Typical applications do not need to call these APIs directly when using the standard DNS resolver. They are useful when investigating resolver behavior or implementing a custom resolver.

Do not set the DNS TTL excessively low just to force fast discovery updates. Doing so can increase DNS queries and load on the control plane. Balance update speed, caching, connection lifetime, and resilience.

## 7. DNS Discovery Does Not Replace Health Checking

The DNS resolver tells you which addresses a hostname resolves to. That does not necessarily prove the gRPC server at each address is accepting requests or processing business logic healthily.

Distinguish between:

- **DNS resolution:** finding addresses from a name.
- **Transport connectivity:** whether the channel can establish a connection to an address.
- **gRPC health checking:** whether the service reports a serving status according to the health protocol.
- **Application readiness:** whether the instance is ready to handle a specific type of business traffic.

A Pod's address may still remain in DNS while the application is shutting down or not ready, depending on configuration and update timing. Conversely, DNS may already have removed an endpoint while the client still caches the old address. Combine readiness, graceful shutdown, connection draining, and bounded retry policies.

Do not treat `UNAVAILABLE` as sole proof that DNS is wrong. This status can originate from DNS, TCP connectivity, TLS, proxies, server shutdown, or other infrastructure failures.

## 8. TLS Authority and DNS Names

The DNS resolver turns a hostname into IPs, but TLS still needs to verify **service identity**. If the client target is:

```text
dns:///orders.default.svc.cluster.local:8443
```

the server certificate must have an identity matching the hostname the client uses, typically expressed via a Subject Alternative Name (SAN). A successful DNS lookup does not make a hostname mismatch valid.

Do not switch to plaintext or disable hostname verification to fix certificate errors. Issue a certificate with an appropriate SAN, configure the trust chain properly, and verify the authority gRPC uses for TLS. Resolver URI authority and TLS authority are separate concepts; do not arbitrarily override TLS authority to bypass certificate verification.

## 9. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `UNAVAILABLE` immediately on channel creation/call | Provider not found for scheme or resolver cannot resolve target | Check scheme, target URI, and resolver registry |
| DNS returns NXDOMAIN | Wrong hostname, namespace, or search domain | Query DNS from the exact container/pod running the client |
| DNS returns SERVFAIL/timeout | Issue with DNS server or network path | Check cluster DNS, resolver config, and network policy |
| DNS returns addresses but connection fails | Wrong port, firewall, Pod not listening, or TLS mismatch | Check endpoint, port, transport, and certificate |
| Only one instance receives traffic | DNS returns only one address or policy is `pick_first` | Observe resolution result and load balancer policy |
| New endpoints are not used | Cache, refresh, or old subchannels still active | Check TTL, JVM DNS cache, resolver refresh, and connection state |
| Failures after Pod replacement | Client uses a fixed IP or retains stale endpoints | Use a stable DNS target and test updates |
| TLS hostname mismatch | SAN does not match target hostname | Check certificate SAN and TLS authority |

Diagnose in order: **target URI → DNS lookup → resolver result → load balancer/subchannel → TCP/HTTP2 → TLS → gRPC status**. This sequence separates discovery failures from transport errors and RPC handling errors.

## 10. Testing the DNS Resolver

Tests should cover URIs, DNS, endpoint updates, TLS, and channel lifecycle:

| Test Case | Setup | Expected Result |
| --- | --- | --- |
| Valid DNS target | Use a hostname with A/AAAA records | Resolver returns the expected addresses and port |
| Invalid hostname target | Use a nonexistent name | Diagnosable resolution/connectivity failure |
| Multiple DNS records | Hostname returns multiple addresses | Resolver emits the endpoint list from DNS results |
| DNS record changes | Change addresses in a controlled test DNS | After refresh/cache propagation, channel updates endpoints |
| Headless Service | Call from a pod in the same cluster | DNS returns endpoints per Kubernetes configuration |
| ClusterIP Service | Call via virtual IP | Confirm Kubernetes dataplane distributes traffic |
| TLS SAN mismatch | Use a certificate with the wrong hostname | TLS handshake fails; verification is not skipped |
| Resolver/channel shutdown | Close Spring context | Channel and associated resources are released |
| DNS temporarily unavailable | Make test DNS server unresponsive | Client recovers per the defined retry/refresh policy |

Unit tests can check target construction and channel configuration. To test resolver address changes, use a controllable test DNS server or a resolver test double; do not rely on public DNS, which changes outside your control. With Kubernetes, run tests from the same namespace/network policy as the real client. In-process gRPC tests do not test DNS, HTTP/2 network paths, or TLS.

## 11. Practice Exercise

`OrderService` runs multiple Pods in Kubernetes. The Spring gRPC client currently configures a Pod IP directly, so when a Pod is replaced, calls can fail.

**Requirements:**

1. Change the target to `dns:///orders.default.svc.cluster.local:8443` and explain the URI parts.
2. Compare DNS for a ClusterIP Service versus a headless Service; identify where load balancing happens in each case.
3. Inspect DNS A/AAAA records, caching, and the time it takes for the client to pick up new endpoints after a rollout.
4. Configure an appropriate load balancing policy if DNS returns multiple Pod IPs; verify supported providers and service config.
5. Ensure the certificate SAN matches the DNS hostname and the channel is closed by Spring on context shutdown.
6. Write tests for NXDOMAIN, multiple addresses, endpoint updates, TLS hostname mismatch, and temporary DNS unavailability.

**Self-Check Questions:**

- What does the DNS resolver take from the target URI and what does it return to the channel?
- Why do multiple A/AAAA records not guarantee that requests are evenly distributed?
- How do ClusterIP and headless Services differ for client-side load balancing?
- Why does a DNS TTL not mean the client switches endpoints at the exact moment the TTL expires?
- Does the DNS resolver verify that a service is healthy?
- Why must the TLS certificate match the target hostname even after DNS resolves it to an IP?
- When should `forTarget(...)` be used instead of `forAddress(...)`?

**Key Takeaways:** The DNS resolver turns the hostname in a target URI into a list of addresses for the gRPC channel. The load balancer decides how to use those endpoints; DNS does not replace health checking, TLS, or readiness. In Spring gRPC, use stable DNS targets, understand ClusterIP/headless Services, verify caching and refresh in the real environment, and verify certificates against the logical hostname.
