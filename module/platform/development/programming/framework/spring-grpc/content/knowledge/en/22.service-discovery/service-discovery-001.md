# Target URI and Resolver

In Spring gRPC, clients typically call a **logical service name** instead of hardcoding the IP of a single instance. That logical name is placed in the channel's target URI. The **name resolver** reads the URI, discovers the available endpoints, and notifies the gRPC channel of the address list. As a result, when instances change, the client can continue calling the service through the same target.

The target URI and the resolver are two distinct parts: the URI describes *the service to find*, while the resolver decides *where to find that service*. Understanding this relationship helps you properly configure DNS, Kubernetes Services, internal registries, or custom resolvers in Spring gRPC applications.

## 1. What is a Target URI?

A target is the identifier string passed into a gRPC channel. With the `ManagedChannelBuilder.forTarget(...)` API, the target is typically parsed as a URI to select the appropriate resolver provider.

General URI format:

```text
scheme://authority/path?query
```

Meaning of each component:

| Component | Role |
| --- | --- |
| `scheme` | Selects the resolver type, such as `dns` or an application-registered scheme |
| `authority` | Authority information for the resolver; the exact meaning depends on the scheme |
| `path` | The service name or target that the resolver needs to resolve |
| `query` | Optional parameters defined by a specific resolver |

Commonly used DNS target examples:

```text
dns:///orders.internal.example:8443
dns:///orders.default.svc.cluster.local:8443
```

In the `dns:///...` form, the scheme is `dns`, the authority is empty, and the path contains the hostname and port to resolve. The three slashes are intentional: they create a URI with an empty authority and a path starting with a slash.

Do not manually split the target string with `split(":")` or treat everything after `://` as a hostname. IPv6, authority, and path have their own URI rules; the resolver is responsible for parsing the target according to its scheme.

## 2. Which Resolver Does the Scheme Select?

grpc-java's `NameResolverRegistry` manages the registered `NameResolverProvider` instances. When a channel receives a target URI, the registry finds the provider with the matching scheme and asks the provider to create a resolver.

Examples:

| Target | Selected Resolver | Purpose |
| --- | --- | --- |
| `dns:///orders.example.net:8443` | DNS resolver | Resolves a DNS name into network addresses |
| `dns:///orders.default.svc.cluster.local:8443` | DNS resolver | Resolves a Kubernetes Service name via cluster DNS |
| `catalog:///orders` | Custom resolver with the `catalog` scheme | Queries an internal service registry or catalog |

`catalog` is just an example of an application scheme; it works when the application has registered the corresponding provider. A target with an unregistered scheme will not be understood automatically by the default resolver.

You should declare the scheme explicitly in the target. If the target has no scheme, gRPC must apply the registry's default scheme; the default can depend on which providers are present at runtime. Relying on an implicit default can cause different behavior across local, test, and production environments.

## 3. DNS Target vs. Direct Address

When service discovery is needed, distinguish `forTarget(...)` from `forAddress(...)`:

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

// Logical target: DNS resolver finds addresses for the service name.
ManagedChannel discoveredChannel =
    ManagedChannelBuilder
        .forTarget("dns:///orders.default.svc.cluster.local:8443")
        .useTransportSecurity()
        .build();

// Specific address: connects to a known host/port.
ManagedChannel directChannel =
    ManagedChannelBuilder
        .forAddress("10.20.1.15", 8443)
        .useTransportSecurity()
        .build();
```

`forTarget(...)` routes the target through the name resolution mechanism. `forAddress(...)` is suitable when the application already knows the specific socket address and does not need to resolve a service name that way. A direct address is often useful for tests or fixed endpoints; it reduces adaptability when instances change.

In production, a DNS target can point to a stable service name. The resolver fetches the current addresses; the channel's load balancing policy decides how to use them. DNS discovery alone does not guarantee that requests are evenly distributed across instances.

The examples above use TLS. Only use `usePlaintext()` in controlled development/test environments; never switch to plaintext just to work around DNS or resolver errors.

## 4. What Does a Resolver Do in the Channel Lifecycle?

A resolver does not directly handle RPC messages. It provides the address list to the channel:

1. The channel receives the target URI and selects a resolver provider by scheme.
2. The provider creates a `NameResolver` with the target and channel parameters.
3. The channel starts the resolver; the resolver queries the discovery source such as DNS or a service registry.
4. The resolver emits a `ResolutionResult` containing one or more addresses (`EquivalentAddressGroup`) along with attributes/service config if present.
5. The load balancer receives the endpoint list, creates or updates subchannels, and selects a connection path for RPCs.
6. When endpoints change or a refresh is needed, the resolver emits a new result; the channel and load balancer update connections.

Overview of the lifecycle:

```text
forTarget(target URI)
       |
       v
NameResolverRegistry
       |
       v
NameResolverProvider by scheme
       |
       v
NameResolver.start(listener)
       |
       v
DNS / service registry lookup
       |
       v
ResolutionResult: endpoint list + attributes
       |
       v
LoadBalancer -> Subchannels -> RPC
       |
       +---- refresh / endpoint update ----> Resolver
```

A resolver typically has these key lifecycle points:

- `start(listener)`: begins resolution and sends results through the listener.
- `refresh()`: requests a refresh when the channel needs an update.
- `shutdown()`: stops the resolver and releases resources.
- `getServiceAuthority()`: provides the service authority that the resolver represents.

Lookups are usually asynchronous. Do not perform DNS lookups, registry calls, or synchronous network waits directly on an RPC processing thread. The resolver must manage executors, timeouts, retry/backoff, and task cancellation on shutdown.

## 5. Resolver and Load Balancer Are Not the Same

This is an important architectural boundary:

| Component | Question It Answers | Example Responsibilities |
| --- | --- | --- |
| Target URI | Which logical service does the client want to call? | `dns:///orders.internal:8443` |
| Name resolver | Which endpoints currently exist for that service? | `10.0.1.8:8443`, `10.0.1.9:8443` |
| Load balancer | Which endpoint should be chosen for an RPC/subchannel? | `pick_first`, `round_robin` if the policy is supported/configured |
| Channel/transport | Establishes and manages connections to endpoints | HTTP/2, TLS, reconnect, call lifecycle |

The resolver returns endpoints; it does not necessarily choose a single endpoint for each request. The load balancer uses the resolution result to decide how to pick connections. For example, the resolver might return three addresses; the `round_robin` policy can distribute RPCs sequentially across ready subchannels, whereas `pick_first` typically picks one suitable subchannel first.

If there is only one endpoint in the resolution result, the resolver is still performing discovery; the load balancer simply has fewer choices. If a registry returns unhealthy endpoints, appropriate health filtering or discovery policies are needed; do not assume the resolver inherently knows application health if the data source does not provide it.

## 6. Integrating Target URIs in Spring gRPC

In a Spring application, a channel or client stub can be managed by Spring gRPC configuration or beans. Whether the channel is created manually or managed by a starter, the target has the same meaning: it specifies the scheme and logical name that the resolver needs to resolve.

Example of creating a channel with grpc-java:

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderGrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel orderChannel() {
        return ManagedChannelBuilder
            .forTarget("dns:///orders.default.svc.cluster.local:8443")
            .useTransportSecurity()
            .build();
    }
}
```

This is an example of managing a channel as a Spring bean at the grpc-java layer. If your project's Spring gRPC starter already manages the channel lifecycle automatically, declare the target in the client configuration mechanism supported by that version and inject the corresponding channel/stub; do not create a new channel per RPC.

Checklist for application configuration:

- Does the target have the right scheme for an available resolver provider?
- Does the DNS name/registry key have the right namespace, domain, and port?
- Does the channel use TLS and trust material matching the endpoint?
- Is the resolver registered before the channel is created?
- Is the channel closed when the Spring context shuts down?
- Is the load balancing policy supported and appropriate for the endpoint list?

Do not conflate URI authority with TLS authority. The resolver authority is part of the target URI and is interpreted by the resolver. The TLS/HTTP/2 authority is the service identity used when establishing the connection. If you need to override the authority, use a supported TLS authority API/configuration and ensure the server certificate is valid; do not alter the hostname in the target just to bypass certificate verification errors.

## 7. When Is a Custom Resolver Needed?

The DNS resolver is suitable when service names are provided by DNS. A custom resolver is useful when endpoints come from:

- An internal service registry with its own API.
- A platform control plane or catalog.
- Dynamic configuration by tenant/region/environment.
- A discovery source that needs to return additional attributes or service config.

A custom resolver usually consists of two parts:

1. **`NameResolverProvider`:** registers the scheme, receives the target URI, and creates the appropriate resolver.
2. **`NameResolver`:** parses the service key, looks up endpoints, converts the result into a `ResolutionResult`, and handles refresh and shutdown according to the lifecycle.

Illustrative processing flow:

```text
Target: catalog:///orders?region=ap-southeast
       |
       v
CatalogNameResolverProvider
       |
       v
CatalogNameResolver("orders", "ap-southeast")
       |
       v
Registry client (timeout + authentication)
       |
       v
EquivalentAddressGroup list
       |
       v
ResolutionResult -> gRPC channel
```

This is an illustrative URI; query parameters only have meaning if the `catalog` resolver defines and validates them. Do not put registry tokens in the URI because the target may appear in logs, exceptions, or diagnostics.

When implementing a custom resolver, you need to:

- Validate scheme, authority, path, and query; reject invalid targets instead of silently resolving the wrong service.
- Use a registry client with its own timeout, TLS, and authentication.
- Push new results through the listener when endpoints change.
- Report errors with an appropriate status; distinguish a temporarily unavailable registry from a malformed target.
- Use bounded retry/backoff and avoid creating tight lookup loops.
- Stop watchers, schedulers, and executors in `shutdown()`.
- Do not keep stale endpoints indefinitely after they expire; clearly define a stale-result policy.

## 8. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `UNAVAILABLE` immediately on channel creation/call | Provider not found for scheme or resolver cannot resolve target | Check scheme, target URI, and resolver registry |
| DNS returns NXDOMAIN | Wrong service name, namespace, or domain | Query DNS from the exact client runtime environment |
| DNS returns addresses but connection fails | Wrong port, firewall, endpoint not listening, or TLS mismatch | Check endpoint, network path, and certificate |
| Channel always calls one instance | Resolver returns only one endpoint or LB policy behaves unexpectedly | Observe the resolution result and actual policy |
| New endpoints are not used | Resolver does not refresh or registry watcher does not emit updates | Check refresh lifecycle and listener callbacks |
| Works locally but fails in Kubernetes | Different DNS search domain, namespace, or network policy | Check target FQDN and DNS from the pod/client runtime |
| TLS hostname mismatch | Certificate authority/SAN does not match server identity | Check certificate SAN and authority; do not disable TLS verification |
| Custom resolver leaks threads | Executors/watchers not stopped on channel shutdown | Check `shutdown()` and bean lifecycle |

Diagnose in order: parse target → select provider → resolver result → load balancer/subchannel → transport connection → TLS → RPC status. This separates discovery errors from connection errors and business-logic errors.

## 9. Testing Target URIs and Resolvers

You should have unit tests for URI/parser and resolver logic, along with integration tests for a channel actually using the resolution result.

| Test Case | Expected Result |
| --- | --- |
| Valid DNS target | Selects DNS resolver and resolves hostname/port |
| Unregistered scheme | Fails clearly; does not silently fall back to another resolver |
| Malformed URI | Rejected with a diagnosable target error |
| Target missing port | Follows the defined default port behavior; does not guess implicitly in the app |
| Resolver returns multiple endpoints | Resolution result contains the exact address list |
| Registry unavailable | Resolver reports error and applies bounded retry/backoff |
| Endpoints change | Resolver emits new result and channel updates subchannels |
| Channel shutdown | Resolver stops watchers/executors and emits no further results |
| TLS authority mismatch | Connection fails; does not bypass certificate verification |
| Spring context shutdown | Channel is closed and resources are released |

For custom resolvers, use a fake registry in tests to control endpoints and updates. Integration tests should verify that RPCs actually reach the expected endpoints after the initial resolution and after the endpoint list changes. Production-like DNS tests must run in an environment with matching DNS/network policies; a URI parsing unit test does not prove cluster DNS works.

## 10. Practice Exercise

`OrderService` has multiple instances in Kubernetes. The Spring gRPC client currently configures a pod IP directly, so when a pod is replaced, calls can fail.

**Requirements:**

1. Switch the client to a logical target of the form `dns:///orders.default.svc.cluster.local:8443`.
2. Explain the scheme, authority, and path of the target URI; verify the DNS name from the client's runtime environment.
3. Distinguish between the resolver returning endpoints and the load balancer selecting subchannels.
4. Ensure the channel uses TLS with the appropriate certificate identity and has its lifecycle managed by Spring.
5. Design tests for DNS failure, endpoint updates, TLS hostname mismatch, and channel shutdown.
6. If DNS does not meet discovery needs, outline a custom scheme and `NameResolverProvider`/`NameResolver` lifecycle for an internal registry.

**Self-Check Questions:**

- Does a target URI describe a logical service or an RPC message?
- Which component does the scheme in the URI determine?
- Why is `forTarget(...)` better suited for discovery than a fixed IP address?
- How does a resolver's responsibility differ from a load balancer's?
- What does `dns:///host:port` mean in terms of authority and path?
- Why should a target URI authority not be confused with a TLS authority?
- Which resources must a custom resolver stop when the channel shuts down?

**Key Takeaways:** A target URI selects the resolver and specifies the logical service to find; the resolver turns the target into an endpoint list; the load balancer uses that list to choose connections for RPCs. In Spring gRPC, use explicit schemes, manage channels according to the application lifecycle, verify DNS/registry and TLS in the real environment, and test both endpoint updates and shutdown.
