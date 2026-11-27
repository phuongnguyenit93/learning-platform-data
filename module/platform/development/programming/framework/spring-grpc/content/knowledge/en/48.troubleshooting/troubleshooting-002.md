# Server Is Running but Client Cannot Resolve Target

## 1. Understand Target Resolution Errors Properly

In **SPRING_GRPC**, a client calls a service using gRPC over HTTP/2 and uses a Protocol Buffers contract to exchange requests/responses. When the server is running yet the client reports that it cannot resolve the target, the problem usually lies in the target name, target URI syntax, DNS, or gRPC Java's name resolver.

The target is the information the client uses to find the server address. It typically consists of a hostname and port, or a URI with a scheme to select the resolution mechanism:

~~~text
dns:///orders-grpc.backend.svc.cluster.local:9090
~~~

The gRPC name resolver translates the target into one or more socket addresses. Only after that step can the channel attempt a TCP connection, perform TLS/HTTP2, and call the service.

~~~mermaid
flowchart TD
    A["gRPC target string"] --> B["Parse URI / resolver scheme"]
    B --> C["NameResolver"]
    C --> D["DNS / service discovery"]
    D --> E["Resolved socket addresses"]
    E --> F["TCP connect"]
    F --> G["TLS + HTTP/2"]
    G --> H["gRPC service / method"]
    B -->|invalid target / scheme| X["Target parse error"]
    C -->|provider missing| Y["Resolver provider error"]
    D -->|name not found / no records| Z["Resolution failure"]
~~~

Knowing "the server is running" only proves the server process is active somewhere. The client may still be using the wrong hostname, wrong port, a different DNS namespace, or an unsupported resolver scheme.

## 2. Distinguish Target Resolution from TCP Connection

Two stages are often confused:

- **Name resolution:** translating a hostname/service name into IP addresses.
- **Connection:** opening a TCP socket to the resolved IP address and port.

| Symptom | Likely Failing Stage | Direction to Check |
|---|---|---|
| `UnknownHostException`, `NameResolver` cannot find address | DNS/name resolution | Hostname, DNS search domain, namespace, resolver |
| `Unable to resolve host` or `No DNS records` | DNS/name resolution | A/AAAA records, service discovery, DNS cache |
| `No resolver found for scheme` | Resolver selection | Scheme in target and dependency/provider |
| `Invalid target URI` | Target parsing | URI syntax, slashes, hostname, and port |
| `Connection refused` | TCP after resolution | Listener, port, route, and bind address |
| `Connection timed out` | TCP/network after resolution | Firewall, route, security group |
| `SSLHandshakeException` | TLS after TCP connects | Certificate, SAN, SNI, trust chain |

An `UNAVAILABLE` error can wrap errors from multiple stages. Read the nested cause to determine whether the client has already resolved an address. If an IP is already present and the error is `Connection refused`, stop tweaking DNS.

## 3. Check the Target String the Client Actually Uses

Targets are often constructed from configuration, environment variables, or service discovery. Log the effective value at runtime (masking sensitive internal details if needed) and check:

- Does the hostname match the right service name?
- Does the port match the gRPC port the server listens on?
- Was an HTTP/actuator port accidentally used instead of the gRPC port?
- Does the target contain `http://` or `https://` like a REST URL?
- Are there extra spaces, slashes, colons, or improperly encoded characters?
- Is a profile, environment variable, or ConfigMap overriding the target?

A gRPC target is not a REST URL. For example, `https://orders.internal:9090` is not a standard target to pass to `ManagedChannelBuilder.forTarget(...)`. With the DNS resolver, use explicit syntax:

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///orders-grpc.backend.svc.cluster.local:9090")
        .usePlaintext()
        .build();
~~~

The example above uses plaintext to illustrate target resolution. In production, configure TLS/credentials according to your system's security policy. Do not enable `usePlaintext()` just to mask a TLS error.

## 4. Understand the `dns:///host:port` Syntax

The target `dns:///orders-grpc.backend.svc.cluster.local:9090` consists of:

| Component | Meaning |
|---|---|
| `dns` | Selects the DNS name resolver |
| `://` | URI scheme separator |
| Next `//` | Empty authority in the URI |
| `/orders-grpc.backend.svc.cluster.local:9090` | DNS address and port to resolve |

The three slashes in `dns:///` are intentional: the URI uses the `dns` scheme, an empty authority, and puts the address in the path. Do not shorten it to `dns://orders-grpc:9090` without verifying the syntax used by your resolver.

You should specify the port explicitly. If you omit the port, the resolver or channel default port may differ from the server configuration, making diagnosis harder.

Different targets can select different resolvers. For example, `dns:///...` selects the DNS resolver; a custom scheme only works when the application has the corresponding `NameResolverProvider`.

## 5. Check the Hostname from the Exact Client Environment

DNS on a developer's machine may differ from DNS inside a Docker container, Kubernetes pod, VM, or production network. Run checks in the exact same environment and network namespace as the JVM creating the gRPC channel.

Windows PowerShell:

~~~powershell
Resolve-DnsName orders-grpc.backend.svc.cluster.local
~~~

Linux:

~~~bash
getent hosts orders-grpc.backend.svc.cluster.local
nslookup orders-grpc.backend.svc.cluster.local
~~~

If `dig` is available:

~~~bash
dig A orders-grpc.backend.svc.cluster.local
dig AAAA orders-grpc.backend.svc.cluster.local
~~~

Check both IPv4 (A) and IPv6 (AAAA) records if the client can select either. An existing AAAA record without a working IPv6 route can cause some environments to fail or stall before trying another address.

If DNS returns multiple addresses, verify that they belong to the right service/backend and are still available. If no addresses are returned, check the name, search domain, DNS server, and service discovery before changing the port.

## 6. Kubernetes DNS: Service Name and Namespace

In Kubernetes, a DNS name typically has the form:

~~~text
<service>.<namespace>.svc.<cluster-domain>
~~~

Example:

~~~text
orders-grpc.backend.svc.cluster.local
~~~

`cluster.local` is the common cluster domain, though it can be customized. Use the actual domain of your cluster.

Short-name rules:

- Client and Service in the same namespace: can call `orders-grpc`.
- Different namespaces: use at least `orders-grpc.backend`.
- For an explicit target with minimal reliance on search paths: use the full FQDN.

A short name can resolve to the wrong target if the client is in another namespace and a service with the same name exists in the current namespace. Using the FQDN removes that ambiguity.

Check the service and endpoints:

~~~bash
kubectl get svc orders-grpc -n backend -o wide
kubectl get endpointslice -n backend -l kubernetes.io/service-name=orders-grpc
kubectl get pods -n backend -o wide
kubectl get pods -n backend --show-labels
~~~

Service DNS can exist even when the selector matches no pods or there are no Ready endpoints. In that case, DNS resolves normally, yet connecting to the service still fails. That is a post-resolution endpoint/routing error, not a DNS lookup failure.

## 7. Headless Services and Multiple Returned Addresses

A standard Kubernetes Service usually resolves to a ClusterIP. A Headless Service (`clusterIP: None`) can resolve to multiple pod addresses. The DNS resolver may receive a list of IPs instead of a single IP.

This affects how the client distributes connections:

- With ClusterIP, the Kubernetes Service/network dataplane typically chooses the backend.
- With a headless Service, the client resolver can see multiple pod addresses and the gRPC load balancing policy decides how to use them.
- Pods change IPs when restarted; the resolver needs to refresh addresses via DNS refresh.
- If a client keeps a long-lived channel, do not assume an address list resolved once remains valid forever.

If using a headless Service, check readiness, pod DNS records, and the channel's load balancing policy. If load balancing across multiple backends is needed, decide clearly whether the Kubernetes Service or gRPC client-side load balancing should select backends.

## 8. Name Resolver Schemes and Providers

gRPC Java picks a resolver based on the scheme in the target. The DNS resolver is the common default; schemes like `consul`, `xds`, or internal schemes require a provider registered at runtime.

If you encounter an error like "no resolver available for scheme", check:

1. Is the scheme in the target spelled properly and in lowercase?
2. Is the dependency containing the resolver provider on the runtime classpath?
3. Is the provider registered properly via the `NameResolverProvider`/ServiceLoader mechanism?
4. Is the provider version compatible with gRPC Java core?
5. When packaging an executable JAR or native image, is ServiceLoader metadata preserved?

For example, if an application uses the target `consul:///orders`, yet the runtime only has the DNS resolver, the client cannot understand Consul on its own. You need to add the appropriate resolver integration or switch the target to a DNS name if the architecture allows.

Do not change the scheme to `dns` just to silence the error if service discovery genuinely requires a custom resolver. Doing so can cause the client to bypass routing, health, or service config provided by the specialized resolver.

## 9. Create a Channel with the Right Target in Java

A channel is usually created once and reused, not created per RPC:

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///orders-grpc.backend.svc.cluster.local:9090")
        .defaultLoadBalancingPolicy("round_robin")
        .useTransportSecurity()
        .build();

OrdersIngressGrpc.OrdersIngressBlockingStub stub =
        OrdersIngressGrpc.newBlockingStub(channel);

try {
    GetOrderReply reply = stub
            .withDeadlineAfter(2, TimeUnit.SECONDS)
            .getOrder(request);
} finally {
    channel.shutdown();
}
~~~

This is a standalone example illustrating the lifecycle. In a Spring application, the channel is typically managed as a bean/singleton according to starter configuration for reuse across many requests; do not shut down the channel after each RPC. Only shut down when the application stops or the channel needs controlled replacement.

`defaultLoadBalancingPolicy("round_robin")` is only useful when the resolver returns multiple addresses and the policy is supported/configured properly. It cannot fix an unresolvable hostname.

## 10. Distinguish Target Host from TLS Authority/SNI

The target hostname usually participates in address selection and determines the connection authority. With TLS, the certificate must be valid for the server name the client verifies. Successful DNS resolution does not guarantee the certificate is valid.

For example, the client target is `orders-grpc.backend.svc.cluster.local`, while the certificate only has SAN `orders.example.internal`. TCP may connect and DNS may be right, yet TLS hostname verification will still fail.

Do not fix certificate errors by changing the target to an IP if the certificate does not have a matching IP SAN. The right fix is issuing a certificate with an appropriate SAN or intentionally configuring an authority override per topology while still verifying the certificate chain and expected hostname.

`overrideAuthority(...)` affects the authority used in gRPC; it is not a DNS resolver and cannot fix an unresolvable hostname. Use it only when you clearly understand its effect on HTTP/2 `:authority`, TLS verification, and SNI in your transport.

## 11. IPv4, IPv6, and Literal IPs

Some target errors stem from how addresses are formatted:

- Hostnames should have the port clearly separated, e.g. `orders.internal:9090`.
- IPv4 literals take the form `10.20.1.15:9090`.
- IPv6 literals must be enclosed in square brackets, e.g. `[2001:db8::15]:9090`.
- Do not split IPv6 and port by guessing the last colon position without using a standard URI parser.

Connecting via an IP literal can help isolate a DNS issue, but it is only a diagnostic test. With TLS, the certificate must have a matching IP SAN or use a proper authority/certificate design. Production should generally rely on stable DNS/service identity rather than pinning pod IPs that can change.

## 12. DNS Caching and Long-Lived Channels

DNS record changes are not necessarily visible to all clients immediately. Results can be affected by:

- DNS TTL and DNS server caches.
- JVM/OS name resolution caches.
- Refresh behavior of the gRPC name resolver.
- Channels still holding connections to an old backend.
- Slow endpoint updates in service discovery.

Do not continuously create new channels to force DNS refreshes; that wastes sockets, threads, and handshakes. First verify TTL/caching and the resolver behavior of your current version. When endpoints change, the gRPC resolver can update addresses for the channel via its refresh mechanism; the application should not create a channel per request.

If you need to switch targets or credentials, manage the channel lifecycle: create a new channel, shift traffic, and gracefully shut down the old channel. Do not change DNS configuration and expect every running channel to immediately switch to the new address.

## 13. Diagnose with grpcurl and DNS Tools

`grpcurl` helps test a target from a shell environment:

~~~bash
# Plaintext server, reflection enabled.
grpcurl -plaintext orders-grpc.backend.svc.cluster.local:9090 list

# TLS server, verifying certificate against the trust store.
grpcurl orders-grpc.backend.svc.cluster.local:9090 list
~~~

If `getent hosts` does not resolve, fix DNS first. If DNS resolves yet `grpcurl` reports connection refused, move to checking TCP/listener. If `grpcurl` succeeds yet the Java application fails to resolve, focus on the target string, resolver scheme/provider, JVM/container DNS, proxies, and channel configuration.

`grpcurl` and the JVM may use different resolvers/runtimes. Therefore, a successful `grpcurl` result does not prove the Java resolver has identical behavior; it simply helps isolate differences between the tool and the application.

If reflection is disabled, `grpcurl list` may fail even though the target and gRPC server work. Use `.proto` or a protoset to invoke a method; do not conclude DNS is broken solely from a reflection-unavailable message.

## 14. Checklist When the Client Cannot Resolve the Target

Follow these steps in order:

1. **Log the runtime target:** log host, port, scheme, and effective profile; do not log credentials.
2. **Check syntax:** a gRPC target is not a REST URL; confirm `dns:///host:port` if using the DNS resolver.
3. **Check DNS from client runtime:** `Resolve-DnsName`, `getent`, `nslookup`, or `dig`.
4. **Check Kubernetes namespace/FQDN:** service name, cluster domain, and DNS search path.
5. **Check endpoints:** Service selector, EndpointSlice, pod readiness, and headless service behavior.
6. **Check resolver provider:** scheme, dependencies, ServiceLoader, and gRPC version.
7. **Check addresses and port:** A/AAAA records, IPv4/IPv6, actual gRPC port.
8. **Check TLS identity:** SAN, SNI, and authority once resolution succeeds.
9. **Compare with grpcurl:** run from the same environment and compare against the Java client.

Record each result to identify the first failing step. Do not change hostname, port, TLS, and load balancing simultaneously, or you will lose visibility into which change fixed the issue.

## 15. Symptom and Resolution Table

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `UnknownHostException` | Wrong hostname or DNS does not know the name | Check FQDN and DNS from client runtime |
| Service name resolves only in one namespace | Using short name in a different namespace | Use `service.namespace` or FQDN |
| `No resolver found for scheme` | Missing resolver provider or wrong scheme in target | Check scheme and runtime dependencies |
| Target URI parse error | Wrong slashes, port, or URL syntax | Use properly formatted target URI |
| DNS resolves but TCP refused | No listener/endpoint or wrong port | Check Service, EndpointSlice, targetPort |
| DNS returns multiple IPs but some fail | Stale endpoint, pod not Ready, or stale record | Check endpoint health and resolver refresh |
| Java fails but grpcurl succeeds | Different target, JVM DNS, provider, or proxy | Compare runtime config and resolver |
| DNS succeeds but TLS hostname fails | SAN does not match authority | Issue certificate with right identity or intentional authority config |
| Only IPv6 fails | AAAA record exists but IPv6 route does not work | Check IPv6 path and resolver/address policy |
| Old channel does not switch backends | DNS cache/resolver refresh or connection still alive | Check TTL, resolver policy, and channel lifecycle |

## 16. Common Configuration Mistakes

| Wrong Practice | Consequence | Right Practice |
|---|---|---|
| Passing `https://host:port` to `forTarget` | Resolver does not accept the target as expected | Use a resolver target URI, e.g. `dns:///host:port` |
| Using short Service name from another namespace | DNS searches wrong suffix or cannot find the name | Use Kubernetes FQDN |
| Using `localhost` to call another pod/service | Resolves to client's own loopback | Use DNS service name |
| Using a custom scheme without a provider | No resolver available to handle the target | Add the appropriate resolver dependency/registration |
| Fixing DNS when the real error is TLS | Does not resolve SAN/SNI mismatch | Separate resolution and TLS into two steps |
| Pinning pod IP in production | Pod restart breaks the target | Use Service DNS/service discovery |
| Creating a channel per RPC to refresh DNS | Leaks sockets and increases handshakes | Reuse channels and manage resolver/lifecycle |
| Using `overrideAuthority` to fix DNS | Authority changes yet hostname still does not resolve | Fix target DNS; only override authority intentionally for TLS/authority |

**Remember:** When the server is running but the client cannot resolve the target, inspect the target string and name resolver before checking TCP. Use `dns:///host:port` for the DNS resolver, verify DNS from the exact container/pod, use an FQDN across Kubernetes namespaces, and ensure custom schemes have providers at runtime. Separate DNS resolution from endpoint/TCP and TLS authority/SNI; channels should be reused so the resolver updates addresses via its own mechanism.
