# Service Appears on Dashboard but Callers Cannot Reach It

A service appearing on the Eureka, Consul, or registry observability Dashboard only proves that the registry holds a record or status for that instance. It does not guarantee that consumers can open a connection to the advertised address, nor that requests will pass through the right protocol, TLS, authentication, and network path.

The fault usually sits at one of these boundaries: the provider registered the wrong address; the registry shows healthy based on checks from a different network; the consumer resolves DNS or selects a different instance; firewall/NAT/port mapping blocks the connection; or the connection reaches the server yet TLS, authentication, context path, or the application rejects the request.

An effective diagnostic approach is to trace the exact request path from the failing consumer. Record the address and port the consumer actually receives from DiscoveryClient, then test DNS, routing, TCP, TLS, and HTTP from the consumer's own environment. Do not conclude based on a green Dashboard or a successful curl run on an admin workstation.

## 1. What Does the Dashboard Prove?

Dashboards typically display registration data, heartbeats, health checks, or node state. Each registry defines status differently:

| Registry | What the Dashboard may show | What is not yet proven |
|---|---|---|
| Eureka | Registered application/instance, status, lease, and heartbeat | Whether consumers can route to the hostname/IP and port |
| Consul | Service registration, node, check status such as passing/critical | Whether every consumer can reach the service address |
| ZooKeeper | Session, znode registration, and instance data | Whether the application's HTTP/TCP endpoint is actually working |
| Custom registry | Self-managed records and state | Real meaning of status without a probe from the consumer network |

For instance, Eureka can display an instance as UP because the client keeps sending heartbeats. A heartbeat proves the client is renewing its lease, not that any consumer has successfully called a business API.

Consul can show a check as passing because the Consul agent can reach an internal health URL. A consumer outside the Docker network may still be unable to reach the service address Consul returns.

ZooKeeper can still hold an ephemeral znode because the client session has not expired. The node's existence does not mean the process still handles requests or that the address in its payload is still valid.

Therefore, distinguish three questions:

1. **Registration:** does the registry contain an instance record?
2. **Health:** is the check performed by the registry passing?
3. **Reachability:** can a specific consumer connect to the advertised endpoint?

These three questions are related, yet none substitutes for the others.

## 2. Tracing the Path from Provider to Consumer

A request using service discovery typically goes through these steps:

1. Provider starts up and binds its web server to an interface/port.
2. Provider or agent registers serviceId, instanceId, host, port, and metadata.
3. Registry stores the record and may update health status.
4. Consumer calls DiscoveryClient or a load-balanced client to retrieve instances.
5. LoadBalancer picks an instance from the list.
6. HTTP client resolves the hostname, opens a TCP connection, negotiates TLS if applicable, and sends the request.
7. Provider receives the request, checks authentication/authorization, routes to the controller, and runs business logic.

Diagram:

~~~mermaid
sequenceDiagram
    participant P as Provider
    participant R as Registry
    participant C as Consumer
    participant N as DNS/Network
    participant A as Provider API

    P->>R: Register serviceId, host, port, metadata
    C->>R: Discover serviceId
    R-->>C: Return instance address
    C->>C: LoadBalancer selects instance
    C->>N: Resolve host and route to port
    N-->>C: IP / TCP connection
    C->>A: HTTP or HTTPS request
    A-->>C: HTTP response or connection error
~~~

If the service appears on the Dashboard yet requests fail, find the first step that does not work. For example:

- DiscoveryClient returns no instances: check serviceId, health filter, and cache.
- DiscoveryClient returns an instance but DNS fails to resolve: check the advertised hostname.
- DNS works but TCP times out: check routes, firewalls, security groups, and ports.
- TCP succeeds but TLS fails: check scheme, certificate, SNI, and truststore.
- HTTP returns 401/403: check credentials, tokens, ACLs, or mTLS identity.
- HTTP returns 404/503: check context path, reverse proxy, gateway, and upstream.

## 3. Recording the Exact Instance the Consumer Selects

Do not just look at the service name on the Dashboard. You need to know which instance the consumer actually receives and picks.

With DiscoveryClient, you can log the instance list for a serviceId in a diagnostic environment:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class DiscoveryDiagnostics {

    private final DiscoveryClient discoveryClient;

    public DiscoveryDiagnostics(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public void inspect(String serviceId) {
        List<ServiceInstance> instances =
                discoveryClient.getInstances(serviceId);

        for (ServiceInstance instance : instances) {
            System.out.printf(
                    "serviceId=%s instanceId=%s host=%s port=%d secure=%s uri=%s zone=%s%n",
                    instance.getServiceId(),
                    instance.getInstanceId(),
                    instance.getHost(),
                    instance.getPort(),
                    instance.isSecure(),
                    instance.getUri(),
                    instance.getMetadata().get("routing.zone"));
        }
    }
}
~~~

This snippet is a diagnostic tool; only log metadata keys on an allowlist such as routing.zone. Do not dump all metadata if it might contain sensitive info, and mask internal endpoints when logs are shipped externally.

Cross-check each field with the Dashboard or registry API:

| Field | What to verify |
|---|---|
| serviceId | Does it match the exact name requested by the consumer? |
| instanceId | Is this the failing replica? |
| host | Which hostname/IP is it; can the caller resolve and route to it? |
| port | Is it the container port, host published port, or proxy port? |
| isSecure / scheme | Is the consumer using HTTP or HTTPS? |
| metadata | Are zone, version, canary, or filter attributes causing wrong instance selection? |
| health/status | Does the consumer filter for passing/healthy instances? |

If there are multiple replicas, log both the full list and the instance chosen by LoadBalancer. A request may fail only on one replica due to a stale registration or a node with a different firewall rule.

Do not assume element ordering in the DiscoveryClient list is fixed. Match by instanceId/host/port and correlate with the actual request.

## 4. Checking the Bind Address and Advertised Address

A provider has two addresses to distinguish:

- **Bind address:** the interface the web server listens on.
- **Advertised/service address:** the hostname/IP and port written into the registry for consumers to call.

Binding to 0.0.0.0 means the server listens on all IPv4 interfaces in the current network namespace. This is not a valid destination address to register for consumers.

Binding to 127.0.0.1 accepts connections only on the provider's loopback namespace. Consumers in another container or machine cannot use their own loopback to reach the provider.

| Configuration / address | Meaning | Risk |
|---|---|---|
| server.address=127.0.0.1 | Listens only on process/container loopback | Other containers cannot reach it |
| server.address=0.0.0.0 | Listens on namespace IPv4 interfaces | Needs firewall restricting allowed sources |
| Service address=127.0.0.1 | Advertises loopback to consumers | Consumers call their own localhost |
| Service address=0.0.0.0 | Advertises wildcard address | Routing destination is ambiguous |
| Container IP | Address inside bridge network | Callers outside that network may lack a route |
| Host IP + published port | Host address forwarding into container | Requires correct port mapping and firewall |
| Private DNS/IP | Endpoint on internal network | Callers must have matching route and DNS |

Example web server configuration inside a container:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

Then register the address that consumers can actually reach. If consumers are on the same Docker network, that may be the service DNS name and container port. If consumers are outside the Docker network, you may need to advertise the host IP/DNS and published port or a reverse proxy endpoint.

Do not replace the registration address with 0.0.0.0 just because the app binds on 0.0.0.0. Those two values serve two different purposes.

## 5. Checking Docker, Port Mapping, and Network Namespaces

A common mistake is registering a container IP or localhost when the consumer resides in a different network.

Suppose:

- inventory-service runs in a container and listens on port 8080.
- The Docker host publishes port 18080 to port 8080.
- order-service runs in another container on the same Docker network.
- A consumer outside Docker connects via the host's private IP.

Access paths:

| Caller | Appropriate address |
|---|---|
| Container order-service on same network | inventory-api:8080 |
| Host | localhost:18080 |
| Another machine on private network | 10.20.1.15:18080, if firewall permits |

Illustrative Compose file:

~~~yaml
services:
  inventory-api:
    image: inventory-service:1.0
    ports:
      - "18080:8080"
    networks:
      - backend

  order-api:
    image: order-service:1.0
    environment:
      INVENTORY_URL: http://inventory-api:8080
    networks:
      - backend

networks:
  backend:
    driver: bridge
~~~

Within the same Docker network, containers call each other using service DNS and container ports. The host or external machines use the published host port. If the registry advertises a 172.x container IP to a consumer outside the network, the record looks valid yet callers have no route.

Also remember localhost always belongs to the caller's network namespace. If the Consul agent runs in its own container, a check URL using localhost will point to the agent container, not the provider container.

Check from the consumer container:

~~~bash
docker exec order-api getent hosts inventory-api
docker exec order-api curl -v --connect-timeout 3 http://inventory-api:8080/actuator/health
~~~

Check the published port from the host:

~~~bash
curl -v --connect-timeout 3 http://127.0.0.1:18080/actuator/health
~~~

If the host can call it but the consumer container cannot, inspect the container's network attachment and DNS. If the container can call it but another machine cannot, check the host's publish binding, routes, and firewall.

## 6. Checking Kubernetes Service and Pod Addresses

In Kubernetes, each Pod has its own network namespace; containers in the same Pod share that network namespace. Pod IPs are usually routable only within the cluster network.

In-cluster consumers should generally call Kubernetes Service DNS, for example:

~~~text
http://inventory-service.default.svc.cluster.local:8080
~~~

If Eureka or Consul registers Pod IPs while a consumer sits outside the cluster, the caller may have no route to the Pod CIDR. If the consumer is inside the cluster, Pod IPs may be reachable, though you must check NetworkPolicy and CNI.

When combining Kubernetes Services with Spring Cloud Discovery, decide which layer is responsible for instance selection:

- Kubernetes Service picks Pod endpoints via Service/EndpointSlice.
- Spring Cloud LoadBalancer picks instances from a registry such as Eureka/Consul.
- A service mesh or ingress may add yet another routing layer.

If both layers select endpoints yet the registry returns an old Pod IP, data mismatch can occur. Check EndpointSlice, Pod readiness, registry records, and consumer caches.

Diagnostic commands from the consumer Pod:

~~~bash
kubectl exec -n default deploy/order-service -- nslookup inventory-service.default.svc.cluster.local
kubectl exec -n default deploy/order-service -- curl -v --connect-timeout 3 http://inventory-service.default.svc.cluster.local:8080/actuator/health
~~~

If the image lacks nslookup or curl, use an ephemeral debug container or a debug pod in the same namespace/network policy. Results must come from the exact network context of the failing consumer.

## 7. Checking DNS, Routes, and Firewalls from the Caller's Side

A hostname can resolve differently across host, container, pod, VPN, and machines on a private network. Split-horizon DNS can also return different addresses per network zone.

Check DNS on Linux:

~~~bash
getent hosts inventory.internal
nslookup inventory.internal
~~~

Check TCP:

~~~bash
nc -vz -w 3 inventory.internal 8081
~~~

Check HTTP:

~~~bash
curl -v --connect-timeout 3 --max-time 8 http://inventory.internal:8081/actuator/health
~~~

On Windows PowerShell:

~~~powershell
Resolve-DnsName inventory.internal
Test-NetConnection -ComputerName inventory.internal -Port 8081
~~~

When TCP fails to connect, verify:

1. Does the caller have a route to the destination subnet?
2. Is the provider bound to an interface accepting connections from that subnet?
3. Does the host firewall allow the application port?
4. Do security groups or network ACLs allow the caller's source?
5. Does NAT/port mapping forward to the right container and port?
6. Is a NetworkPolicy or service mesh policy blocking traffic?
7. Does DNS point to an old endpoint or an unreachable interface?

Do not inspect only the provider's inbound firewall. Some environments have consumer egress policies, bidirectional network ACLs, or intermediate firewalls. You need to know whether SYN packets reach the provider and whether replies return to the caller.

## 8. Checking HTTP, HTTPS, TLS, and Authentication

A successful TCP connect only proves a socket can be opened. It does not prove business requests will be accepted.

| Result | Possible cause | Check |
|---|---|---|
| TLS handshake failure | Incompatible protocol/cipher, wrong TLS termination | TLS versions, ciphers, and proxy config |
| Certificate path/PKIX error | Consumer does not trust CA or missing intermediate certificate | Truststore and certificate chain |
| Hostname verification failed | Certificate SAN does not match registry-advertised hostname | DNS/SAN/SNI and advertised hostname |
| 401 Unauthorized | Missing or invalid credentials/token | Authentication filter and token |
| 403 Forbidden | Authenticated but insufficient permissions | Roles, scopes, ACLs, and policies |
| 404 Not Found | Wrong context path or route | server.servlet.context-path, gateway path, and controller mapping |
| 405 Method Not Allowed | Wrong HTTP method used | Endpoint's allowed HTTP method |
| 503 Service Unavailable | Proxy/load balancer has no healthy upstream | Upstream pool and health filter |
| 502 Bad Gateway | Gateway received an invalid response from upstream | Proxy logs, upstream connection, and protocol |
| 200 health but API fails | Health endpoint checks a narrower scope than business logic | Dependencies, auth, and actual endpoint |

Test HTTPS using the real hostname so TLS SNI and hostname verification work properly:

~~~bash
curl -v --connect-timeout 3 https://inventory.internal:8443/actuator/health
~~~

Do not disable certificate verification in production to hide errors. If you need to isolate a problem in a lab, perform controlled tests only and re-enable TLS verification immediately afterward.

If a gateway terminates TLS and forwards HTTP to the provider, the registry may need to advertise the gateway's HTTPS endpoint to consumers instead of the internal HTTP address. In that setup, internal health checks and the service address can differ, yet both must match the right network and trust boundary.

## 9. Distinguishing Health Check URL from Service Address in Consul

Consul has two addresses that are frequently confused:

- Service address and port are the endpoint consumers receive from the catalog.
- Check URL is the endpoint the Consul agent actively calls to check the service.

Example:

~~~json
{
  "service": {
    "name": "inventory-service",
    "id": "inventory-node-a",
    "address": "10.20.1.15",
    "port": 18080,
    "checks": [
      {
        "http": "http://inventory-api:8080/actuator/health",
        "interval": "10s",
        "timeout": "2s"
      }
    ]
  }
}
~~~

The agent can call inventory-api:8080 inside the Docker network and report the check as passing. External consumers receive 10.20.1.15:18080. If port 18080 is not published or is blocked by a firewall, the Dashboard still shows passing while consumers cannot connect.

Test both paths from their proper origins:

- From the Consul agent's network, call the check URL.
- From the consumer's network, call the catalog service address and port.

If the consumer only retrieves passing instances, verify whether the query filters for passing properly. If the consumer queries the catalog without health filtering, critical instances may still be returned depending on the API and client.

## 10. Specific Checks for Eureka

The Eureka Dashboard shows registered instances and heartbeats/leases. When the Dashboard shows UP yet consumers cannot call the service, check:

1. Is the instance hostname/IP stored by Eureka reachable from the consumer?
2. Is the registered port the application port or advertised proxy port?
3. If using prefer-ip-address, is there a route to that IP from the consumer?
4. If using hostname, does DNS from the consumer resolve it properly?
5. If there are multiple networks, is Eureka advertising an address from another network?
6. Is the consumer using the exact application name/serviceId?
7. Are registry fetch and LoadBalancer caches holding onto an old instance?
8. Is the instance filtered out by zone, metadata, or health policy?

Illustrative provider configuration on a shared network:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  address: 0.0.0.0
  port: 8080

eureka:
  client:
    service-url:
      defaultZone: http://eureka-server:8761/eureka/
  instance:
    prefer-ip-address: true
    instance-id: inventory-node-a
~~~

prefer-ip-address merely chooses an IP instead of a hostname in instance metadata; it does not guarantee the chosen IP is reachable by every consumer. If consumers sit on a different network, advertise a routable hostname/IP or use a shared gateway/load balancer.

instance-id in the example is a fixed ID for a single illustrative instance. When running multiple replicas, each replica needs its own instance ID; do not copy this exact static value across all providers.

Eureka status UP is also not an HTTP health check from each consumer. You can configure health check integration depending on your Spring Cloud Netflix version, yet you still must verify the advertised endpoint and the consumer network path.

## 11. Specific Checks for ZooKeeper

ZooKeeper typically stores service registrations under a znode, often an ephemeral node tied to a session. Seeing a znode on a dashboard or admin tool only proves the record exists in the data tree.

Check:

- Does the registration path match the right service name and instance ID?
- Which host/port does the znode payload contain?
- Is that address reachable from the consumer?
- Is the provider's session still valid or is the record stale?
- Has the consumer received watcher events or resynced after a reconnect?
- Is the consumer cache retaining an old instance?
- Do ACLs allow the consumer to read the required path?
- Does the payload have a schema issue or stale metadata?

ZooKeeper does not automatically probe the HTTP endpoint just because the znode exists. If you want business-level health state, you need a separate health check or mechanism to exclude unhealthy instances from the list consumers use.

After a LOST session, old ephemeral nodes are deleted. When the client reconnects and creates a new node, consumers must update their instance lists. If a consumer keeps a cache or its watcher has not re-registered, the dashboard and consumer view can diverge temporarily.

## 12. Checking Whether the Consumer Actually Uses Spring Cloud LoadBalancer

An application may be able to query DiscoveryClient while its HTTP client is not configured to treat serviceId as a logical hostname.

For example, when using a load-balanced WebClient.Builder:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

The consumer can inject the LoadBalanced-annotated builder into its own client:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class InventoryClient {

    private final WebClient webClient;

    public InventoryClient(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    public Mono<String> getItems() {
        return webClient.get()
                .uri("http://inventory-service/api/items")
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

This is an example for WebFlux and a compatible Spring Cloud LoadBalancer version; the project requires the corresponding LoadBalancer and discovery integration dependencies. Using a WebClient.Builder without @LoadBalanced can send the hostname inventory-service straight to normal DNS instead of routing through service discovery.

With RestTemplate, RestClient, or other HTTP clients, use the load-balancing integration/adapter appropriate for your Spring Cloud version. Do not assume simply putting serviceId in a URL makes every HTTP client understand it automatically.

Check LoadBalancer logs to inspect:
- the requested serviceId;
- the number of instances retrieved;
- the selected instance;
- the final host/port;
- whether the error occurs before or after opening the connection.

If DiscoveryClient returns an empty list, inspect the registry, serviceId, and filters. If it returns the right instances yet LoadBalancer fails to select one, check the supplier, health filter, zone preference, retries, and bean configuration.

## 13. Checking Caches and Stale Registry Data

The Dashboard and consumers can observe data at different points in time. A consumer may hold a cached instance list while the provider has already changed IP or port.

Causes include:

- Long registry fetch intervals.
- LoadBalancer cache TTL not yet expired.
- DNS cache holding an old IP.
- Consumer not yet processing watcher events.
- Provider restarted while an old instance ID/hostname lingered.
- Health status changed while the consumer did not filter by status.
- Multiple registries or clusters exist and the consumer is querying the wrong source.

Compare timestamps:
- when the provider registered;
- when the instance address changed;
- when the registry received the update;
- when the consumer refreshed;
- when the last request went to the old endpoint.

Do not flush caches blindly without knowing which source holds bad data. If the registry is returning the wrong address, refreshing repeatedly just gives the consumer the same bad data. Fix the registration or advertised address first, then verify the consumer picks up the new record.

## 14. Symptom-Based Diagnostic Table

| Symptom | First suspect layer | Next check |
|---|---|---|
| Dashboard shows instance, DiscoveryClient returns empty | ServiceId/filter/cache | Service name, health filter, registry endpoint, and client cache |
| DiscoveryClient returns host 127.0.0.1 | Registration address | Provider's advertised host and network namespace |
| Host can call it, consumer container cannot | Docker network/DNS | Network attachment, service DNS, and internal port |
| Container can call it, VPN machine cannot | Private routing/firewall | VPN routes, split DNS, security groups |
| DNS fails to resolve | DNS | Search domains, DNS zones, and registered hostname |
| TCP connection refused | Listener/port | Bind address, port, NAT, and firewall reject rules |
| TCP timeout | Route/filter/drop | Firewall, NetworkPolicy, security group, NAT |
| TLS handshake error | TLS/protocol | Scheme, truststore, certificate chain, SAN, SNI |
| HTTP 401/403 | Authentication/authorization | Token, role, ACL, mTLS identity |
| HTTP 404 | Path/routing | Context path, gateway rewrite, controller mapping |
| HTTP 502/503 | Proxy/upstream | Target pool, health filter, proxy logs |
| Only one replica fails | Instance-specific config | InstanceId, host, port, zone, metadata, and firewall |
| Dashboard passing but business API fails | Health scope | Health endpoint, dependencies, and readiness |
| Still calls old IP after reconnect | Cache/propagation | Registry update, fetch interval, DNS TTL, and watcher |

## 15. Runbook from the Failing Consumer

Execute in order and record the result at each step:

1. **Capture the actual request:** serviceId, path, scheme, method, timestamp, error, and correlation ID.
2. **Read the instance list:** call DiscoveryClient.getInstances(serviceId), logging redacted host/port/instanceId.
3. **Identify the selected instance:** enable LoadBalancer logs or tracing to see which endpoint the request used.
4. **Test DNS from caller:** does the hostname resolve to the expected IP?
5. **Test TCP from caller:** is the port open and does routing work?
6. **Test HTTP/TLS:** do both the health endpoint and business endpoint respond properly?
7. **Cross-check provider:** is the server bound to the right interface/port and do logs show the incoming request?
8. **Cross-check registry:** are service address, check URL, health status, and timestamps consistent?
9. **Check security:** firewalls, ACLs, tokens, certificates, and network policies.
10. **Check caches:** after fixing registration, has the consumer picked up the new address?
11. **Check all replicas:** not just one example instance seen on the Dashboard.
12. **Confirm recovery:** send a request from the real consumer and observe the provider logs receiving it.

Record findings in a table:

| Step | Result | Evidence |
|---|---|---|
| DiscoveryClient returns instances | PASS/FAIL | serviceId, instanceId, host, port |
| DNS resolve | PASS/FAIL | hostname and resolved IP |
| TCP connect | PASS/FAIL | port and connect latency |
| TLS handshake | PASS/FAIL/N/A | certificate/SAN/protocol |
| HTTP health | PASS/FAIL | status code and latency |
| Business API | PASS/FAIL | status code, correlation ID |
| Provider logs request | YES/NO | timestamp and trace |
| Cache updated | PASS/FAIL | refresh time and new endpoint |

## 16. Things Not to Do During Incident Response

- Do not conclude a service is healthy just because the Dashboard shows UP or passing.
- Do not register localhost or 0.0.0.0 as an address for consumers on another network.
- Do not change ports or IPs in multiple places at once without recording what the registry currently returns.
- Do not open firewalls to an entire subnet or expose registry APIs to the Internet just for a quick test.
- Do not disable TLS verification or authentication in production to make requests succeed.
- Do not bulk-delete registrations before identifying which instances are stale.
- Do not retry infinitely when the failure is DNS/configuration/authorization.
- Do not introduce a new cache layer before inspecting the existing caches of the discovery client and LoadBalancer.
- Do not test only from an admin host; test from the exact consumer container/pod/machine.
- Do not treat an internal health check URL as proof that the service address advertised to consumers is reachable.

## 17. Prevention Checklist

Before deploying a new service, confirm:

1. Provider binds on an interface accepting traffic from the intended network.
2. Registry advertises a hostname/IP and port routable from consumers.
3. Neither localhost nor 0.0.0.0 is used as a destination address.
4. Docker port mapping, Kubernetes Service, or gateway is configured properly.
5. DNS resolves the endpoint accurately for every consumer group.
6. Firewalls, security groups, and NetworkPolicies allow the required flows.
7. HTTP/HTTPS, TLS certificates, SNI, and authentication align.
8. Health checks are tested from the network of the agent executing the check.
9. Consumer requests are tested from the real network namespace.
10. DiscoveryClient and LoadBalancer use the right serviceId and filters.
11. Caches/refresh have bounded staleness and update after registration changes.
12. Logs/metrics include instanceId, endpoint, connection errors, and latency for traceability.
13. Every replica is verified, avoiding confirming only a single instance.
14. A runbook exists for DNS, TCP, TLS, HTTP, and registry state.

The key takeaway is: **The Dashboard proves the registry holds data; a consumer can reach the service only when the instance address it receives can be resolved, routed, and accepted by the provider from the consumer's own network.** Grab the endpoint from DiscoveryClient, test each layer from caller to provider, and cross-check with registration/health checks to pinpoint the exact failing boundary.
