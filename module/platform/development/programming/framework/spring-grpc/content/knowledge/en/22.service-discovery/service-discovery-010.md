# Local and Production Discovery

Service discovery must work consistently from a developer's laptop to production, even though endpoint sources and security requirements differ across environments. In Spring gRPC, clients should call a **logical target** configured per environment; the gRPC channel uses a resolver to locate endpoints, and then the load balancer manages connections and picks a backend.

Locally, endpoints are usually fixed and easy to inspect: a process on the development machine, a Docker Compose service, or a test server. In production, addresses can change with Pods, zones, rollouts, or registry leases. The goal is to keep how the application calls the service stable while explicitly configuring the target, TLS, readiness, and endpoint update mechanisms for each environment.

## 1. Separating Targets from Source Code

Do not hardcode production hostnames, IPs, or ports in client code. Place the target in external configuration so each profile selects the right discovery source:

| Environment | Illustrative Target | Meaning |
| --- | --- | --- |
| Local, server running on developer machine | `dns:///localhost:9090` | DNS resolver resolves loopback and connects to local port |
| Docker Compose, client and server in separate containers | `dns:///orders:9090` | Uses the service name on the Compose network |
| Kubernetes ClusterIP Service | `dns:///orders.default.svc.cluster.local:8443` | DNS resolves Service name to a virtual IP |
| Kubernetes headless Service | `dns:///orders-headless.default.svc.cluster.local:8443` | DNS can return Pod endpoints for client-side discovery |
| Proprietary registry | `catalog:///orders` | Uses a custom resolver registered for the `catalog` scheme |

`dns:///` selects the DNS resolver; the hostname and port are the target to resolve. The `catalog` scheme only works when the application has registered the corresponding `NameResolverProvider`. Do not put tokens or passwords in the target URI because the target may appear in logs and diagnostics.

A common local mistake is using `localhost` between two containers. Inside a container, `localhost` points to that container itself. If client and server run in separate containers, use the DNS service name on the shared network, such as `orders:9090`. If the client runs on the host and the server publishes a port to the host, `localhost:<published-port>` is the right address.

## 2. Configuration by Spring Profile

You can keep one property for the target and vary its value by profile or environment variable:

```yaml
# application-local.yml
clients:
  orders:
    target: dns:///localhost:9090

---
# application-prod.yml
clients:
  orders:
    target: dns:///orders.default.svc.cluster.local:8443
```

At deployment, activate the profile and inject configuration from environment/config management. Do not let production values act as an implicit fallback for local or vice versa. If a required target is missing, the application should fail fast at channel initialization rather than waiting until the first RPC.

Example channel reading the target from Spring configuration:

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;

@Configuration
class OrdersGrpcChannelConfiguration {

    @Bean(destroyMethod = "shutdown")
    @Profile("local")
    ManagedChannel localOrdersChannel(Environment environment) {
        String target =
            environment.getRequiredProperty("clients.orders.target");
        return ManagedChannelBuilder
            .forTarget(target)
            .usePlaintext()
            .build();
    }

    @Bean(destroyMethod = "shutdown")
    @Profile("prod")
    ManagedChannel productionOrdersChannel(Environment environment) {
        String target =
            environment.getRequiredProperty("clients.orders.target");
        return ManagedChannelBuilder
            .forTarget(target)
            .useTransportSecurity()
            .build();
    }
}
```

This example separates two profiles so plaintext mode is only created locally and production uses TLS. If your project has multiple profiles such as `staging`, `test`, or `devcontainer`, explicitly define which profile uses which transport; do not rely on a boolean that defaults to plaintext.

This is direct grpc-java configuration. If your project's Spring gRPC starter manages channels automatically, declare the target and transport through the properties/extension points of your exact starter version, and inject the stub provided by the starter. Do not manually create extra channels per RPC; `ManagedChannel` is a long-lived resource and must be closed when the Spring context shuts down.

## 3. Local Discovery: Choosing the Right Topology

Local does not always mean a single process on the machine:

| Setup | Suitable Target | What to Verify |
| --- | --- | --- |
| Client and server on same machine, two processes | `dns:///localhost:9090` | Server binds the right port; local firewall does not block |
| Client on host, server in container with published port | `dns:///localhost:19090` | Host port maps to container port `9090` |
| Client and server in Docker Compose | `dns:///orders:9090` | Both containers on the same network; service name and port match |
| Test client calling an in-process server | In-process channel/server test transport | No DNS or sockets needed; tests gRPC logic only |
| Multiple local instances | Local DNS/mock service registry or test custom resolver | Resolver returns all endpoints; LB policy is configured |

For a single fixed local server, `forAddress("localhost", 9090)` can also be appropriate. When you want to test the same target/resolver mechanism used in production, use `forTarget("dns:///localhost:9090")` so calls go through the DNS resolver.

A local fake registry should reproduce the production contract to the necessary degree: service name, instance ID, host/port, readiness, and endpoint updates. You do not need to emulate all production infrastructure, but you should test that the client handles endpoint additions/removals and registry unavailability.

## 4. Production Discovery in Kubernetes

In Kubernetes, DNS Services provide stable names while Pod IPs change. Two common topologies affect load balancing differently:

| Service | What DNS Typically Returns | Where Connections Are Distributed |
| --- | --- | --- |
| ClusterIP | One stable virtual IP | Kubernetes service dataplane chooses a backend when establishing connections |
| Headless (`clusterIP: None`) | List of eligible Pod IPs per Service configuration | gRPC client can open multiple subchannels and apply client-side load balancing |

With ClusterIP, a gRPC channel typically maintains a single long-lived HTTP/2 connection to one backend selected at the network layer. Many RPCs multiplexed over that connection can concentrate on that one backend; do not expect ClusterIP to distribute individual RPCs from a single channel automatically.

With a headless Service, DNS can return multiple Pod IPs. The resolver passes that list to the load balancer; policies such as `round_robin` can distribute new RPCs across `READY` subchannels if the policy is supported and properly configured. When choosing a topology, weigh readiness, certificate identity, DNS caching, and whether clients can connect directly to Pods.

Production targets must never point to fixed Pod IPs. Use service DNS or a custom resolver to track endpoints. Across multiple namespaces/clusters, use explicit FQDNs to avoid relying on Pod DNS search paths.

## 5. Production Discovery via a Proprietary Registry

Some platforms use Consul, Eureka, or an internal registry instead of plain DNS. In that case:

1. The server registers service name, instance ID, endpoint, zone, and readiness status once ready.
2. Leases/heartbeats keep the registration valid; deregistration removes the instance on normal shutdown.
3. A custom `NameResolverProvider` handles the target scheme, such as `catalog:///orders`.
4. The `NameResolver` queries/watches the registry and emits `ResolutionResult` snapshots.
5. The load balancer updates subchannels and the picker for new RPCs.

Do not register in parallel across multiple registries without defining which registry is the source of truth. If the platform already provides an official Spring integration for Consul/Eureka, prefer that integration instead of building duplicate heartbeats and registrations.

A registry is a discovery data source, not a security boundary. Clients still need TLS/mTLS, certificate verification, and authentication for RPCs. Only publish endpoints clients can reach; never place registry credentials in service metadata.

## 6. TLS and Authority Must Match the Logical Target

Local setups may use plaintext when the server binds only in a controlled development environment. Production must authenticate the server using TLS and an appropriate trust chain; use mTLS if the architecture requires mutual authentication.

If the target is `orders.default.svc.cluster.local`, the server certificate needs a SAN matching the identity the client verifies. DNS resolving a hostname to an IP does not change the TLS identity. Never disable hostname verification or switch production to plaintext to work around a certificate mismatch.

When a proxy or service mesh terminates TLS, clearly define each hop:

- Client → gateway/sidecar: protocol, TLS identity, and trust.
- Gateway/sidecar → gRPC server: HTTP/2, TLS/mTLS, or internal plaintext per policy.
- Authority used by the client to verify the server: must match the certificate SAN or an intentionally configured authority override.

Do not confuse the resolver's URI authority with the TLS authority. Changing the target hostname to dodge certificate errors can break discovery and routing.

## 7. Readiness, Endpoint Updates, and Rollouts

Production discovery must remove unready endpoints and add new endpoints to the pool in a controlled sequence:

1. The new instance starts, binds the gRPC port, and checks mandatory dependencies.
2. Readiness or gRPC Health transitions to `SERVING`.
3. The registry/EndpointSlice publishes the instance.
4. The resolver receives the new snapshot; the load balancer creates subchannels and connects.
5. On shutdown, the instance transitions to `NOT_SERVING`/`DRAINING`, is removed from discovery, and stops accepting new RPCs.
6. In-flight RPCs complete within the grace period; only then does the server shut down.

Resolvers and clients may receive updates with delay due to DNS TTL, registry watches, caches, or open HTTP/2 connections. Thus, a readiness failure does not mean every client immediately stops sending requests. Configure appropriate termination grace periods, connection draining, and retry policies.

Locally, test these state transitions using a fake registry or multiple test servers. In production, observe propagation delays and test real rollouts rather than merely confirming the registry deleted the record.

## 8. Failover and Behavior During Discovery Errors

Discovery may become temporarily unreachable while the service itself is still running. Client behavior must be defined:

| Scenario | Recommended Behavior |
| --- | --- |
| DNS/registry lookup fails at startup | Fail clearly; retry with backoff per policy without creating a tight spin loop |
| Registry errors after valid endpoints were already known | Decide whether to keep the latest snapshot during a grace period or transition to error; bound stale data age |
| No ready endpoints remain | Channel waits/reconnects or returns `UNAVAILABLE` per policy and deadline |
| One subchannel errors while another endpoint is `READY` | Load balancer keeps picking the ready endpoint |
| New endpoint appears | Resolver emits new snapshot; channel updates subchannels |
| An RPC returns `UNAVAILABLE` | Handle per retry policy, deadline, and idempotency; do not assume every error comes from discovery |

Do not retry indefinitely. RPC retries must respect deadlines and retryable statuses; non-idempotent operations need safeguards against duplicate execution. Retaining stale endpoints too long can send traffic to retired instances; dropping all endpoints on brief registry blips can hurt availability. Pick grace periods based on SLAs and real measurements.

## 9. Configuration and Testing Parity Between Local and Production

The goal of local/testing setups is to verify the same discovery contract without necessarily running full production infrastructure. Use explicit configuration and test impactful differences:

| Item | Local/Test | Production |
| --- | --- | --- |
| Target | localhost, Compose service, or test resolver | Service FQDN or registry scheme |
| Transport | Plaintext only in isolated environments; test TLS when needed | TLS/mTLS per policy |
| Discovery source | Local DNS, fake registry, test resolver | Cluster DNS, service registry, or control plane |
| Endpoint count | One or a few test servers | Multiple instances/zones |
| Health | Health service simulating states | Readiness, health `Watch`, and registry health |
| Failure | Stop server, change port, simulate lookup errors | Pod rollouts, zone failures, registry outages |
| Lifecycle | Close context/channel in tests | Graceful drain, termination grace period |

Important tests:

- **Config test:** local and production profiles select the expected targets and transports; no localhost fallback in production.
- **Resolver test:** target parses properly, DNS/registry returns expected endpoints, snapshot add/remove works.
- **Channel integration test:** generated stub calls server via the configured target.
- **TLS test:** valid hostname/SAN succeeds; mismatch fails.
- **Load balancing test:** multiple `READY` endpoints are used per the chosen policy.
- **Failure test:** DNS/registry unavailable, dead endpoint, no ready endpoints left, and reconnect.
- **Rollout test:** new endpoint added, old endpoint drained, and in-flight RPCs handled properly.

A passing local test against `localhost` does not prove a production FQDN resolves or that certificates are valid. Run smoke tests from the actual target network namespace/Pod using the same DNS and trust material as production clients.

## 10. Observing Discovery Across Environments

Use consistent metrics and logs to compare local, staging, and production:

- Target scheme and service name (do not log queries containing sensitive data).
- Number of endpoints in the resolver snapshot and timestamp of the latest update.
- Resolver lookup successes/failures, refresh counts, and latency.
- Subchannel counts by connectivity state.
- Active load balancing policy and RPC counts per backend if telemetry permits.
- Time from readiness/registry update until the endpoint stops being picked.
- RPC statuses, deadlines, and retry counts per service/method.

Avoid using IPs, Pod UIDs, or instance IDs as unbounded metric labels. Controlled logs can contain endpoint identities for investigation, but never log tokens, credentials, or full metadata.

## 11. Practice Exercise

A Spring gRPC client running locally calls `OrderService` using `localhost:9090`. When deploying to Kubernetes, the team only changed the port to `8443`, yet the client cannot connect; after rollouts, some requests still hit old Pods.

**Requirements:**

1. Design `clients.orders.target` for local, Docker Compose, and Kubernetes.
2. Explain why `localhost` inside a container does not refer to another container.
3. Choose ClusterIP or headless Service based on where load balancing should happen; explain the impact of long-lived HTTP/2 connections.
4. Configure production TLS and certificate SANs matching the service DNS name.
5. Define readiness, endpoint updates, resolver refresh, and graceful draining during rollouts.
6. Write tests confirming the production profile does not use plaintext or localhost, the DNS target resolves properly, and the client stops picking old endpoints after propagation.
7. Propose metrics to distinguish DNS/registry errors, transport/TLS errors, and RPC errors.

**Self-Check Questions:**

- Why should targets live in profile configuration rather than source code?
- When should `forAddress(...)` be used versus `forTarget(...)`?
- Why does `localhost` mean different things on a host versus inside a container?
- How do ClusterIP and headless Services differ for gRPC load balancing?
- Does the DNS resolver guarantee clients receive new endpoints the instant Pods change?
- Why must the TLS certificate match the logical hostname even after DNS returns an IP?
- When a registry errors, how long is it appropriate to retain the old snapshot?
- How do you ensure local tests adequately reflect production discovery behavior?

**Key Takeaways:** Local and production may use different discovery sources, but they should keep target, resolver, and channel contracts clear. Separate targets/transports by profile; use `localhost` only within the right network namespace; understand ClusterIP versus headless Services; protect production with TLS, readiness, endpoint updates, and graceful draining. Test from the actual network environment and trust configuration to catch discrepancies before rollout.
