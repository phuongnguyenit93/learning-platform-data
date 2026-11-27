# 503 Due to Missing ServiceInstance or Unreachable Target

## 1. Correctly Distinguish the Two Different Scenarios

In the **SPRING_CLOUD_GATEWAY** module, the Gateway receives requests from clients, selects a route using predicates, executes the filter chain, transforms paths/headers, and then calls a microservice via a fixed URL or Spring Cloud LoadBalancer. When a route uses service discovery, the Gateway needs to find a **ServiceInstance** capable of serving the request. When a route uses a specific host/port, or after LoadBalancer selects an instance, the Gateway still has to open a network connection to that target.

Two errors often surface as HTTP 503 on the client side while having very different root causes:

1. **No ServiceInstance found:** LoadBalancer receives an empty instance list and cannot choose a host/port. With Gateway WebFlux using a `lb://SERVICE-ID` URI, the documented default behavior is to return **503 Service Unavailable**; 404 can be configured via the property for the running release.
2. **Target selected, but unreachable:** The Gateway has a host/port, yet TCP connect is refused, DNS fails to resolve, the TLS handshake fails, pool acquire times out, or the target fails to respond on time. This is a **transport failure**, not an empty ServiceInstance list. The final status depends on error handling, retry, circuit breaker, and application policy; do not assume every `ConnectException` is automatically turned into 503 by the Gateway.

In addition, the upstream can **return HTTP 503 itself** after receiving the request if it is overloaded or under maintenance. Therefore, seeing status 503 alone is insufficient to conclude whether the fault lies in discovery, network, or backend.

### 1.1. Three Paths That Produce Status 503

~~~mermaid
flowchart TD
    C["Client request"] --> R["Gateway route matched"]
    R --> LB{"URI uses lb:// ?"}
    LB -->|Yes| S{"LoadBalancer finds ServiceInstance?"}
    S -->|No| E["Gateway default: 503"]
    S -->|Yes| N["Connect to selected host:port"]
    LB -->|No, fixed http(s) URI| N
    N -->|Connection / DNS / TLS / timeout error| X["Gateway error pipeline<br/>status depends on handling"]
    N -->|HTTP response received| U{"Upstream status"}
    U -->|503| P["Proxy upstream 503"]
    U -->|Other status| O["Proxy or transform response"]
~~~

| Source of 503 / Transport Failure | Did Gateway Select an Instance? | HTTP Response from Upstream? | First Place to Investigate |
| --- | --- | --- | --- |
| LoadBalancer has no instance | No | No | DiscoveryClient, service ID, instance list, filters/cache |
| TCP connection refused | Possibly yes | No | Host/port, listener, endpoint, NetworkPolicy |
| DNS lookup failed | Possibly had hostname | No | DNS, service name, namespace, resolver |
| TLS handshake/certificate failed | Yes | No valid HTTP response yet | Scheme, certificate, truststore, SNI |
| Connect/response timeout | Yes | Either none or response arrived too late | Timeout, latency, pool, backend saturation |
| Upstream itself returned 503 | Yes | Yes, status 503 | Backend logs/health/capacity |
| Circuit breaker fallback | May not have called backend on this request | Not necessarily | Circuit state, fallback policy, prior failures |

**Principle of this lesson:** distinguish **having no target to select** from **having a target that cannot be reached**, and only then fix the right layer.

## 2. How Does Gateway's LoadBalancer Work?

### 2.1. Routes Using lb://SERVICE-ID

Example WebFlux route:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-api
              uri: lb://ORDER-SERVICE
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
~~~

With route `lb://ORDER-SERVICE`, `ReactiveLoadBalancerClientFilter` reads the service ID, asks Spring Cloud Reactor LoadBalancer to pick a `ServiceInstance`, and replaces the logical URL with the selected instance's host/port. Only then does the Gateway make the outbound HTTP request to that address.

For example, the service registry provides:

~~~text
ORDER-SERVICE
  instance A: 10.20.1.15:8081
  instance B: 10.20.2.18:8081
  instance C: 10.20.3.21:8081
~~~

Gateway picks an instance according to the LoadBalancer configuration, such as round-robin by default. If the returned instance list is empty, there is no host/port to open a connection to. This is the **no ServiceInstance** case.

### 2.2. Fixed URI Without Service Discovery

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-fixed
              uri: http://orders.internal:8081
              predicates:
                - Path=/api/orders/**
~~~

This route calls the configured hostname/port directly. It does not ask LoadBalancer to select an instance from `lb://`. DNS failure, connection refused, or timeouts can still happen, but checks must focus on the target's DNS/network/host/port.

**If you think a route uses discovery when its actual URI is `http://...`, fixing Eureka/Consul/Kubernetes registry will have no effect on that route.** Check the effective route definition and route ID first.

### 2.3. Which Components Supply ServiceInstance?

Spring Cloud LoadBalancer uses the `DiscoveryClient` on the classpath to fetch instances; for example:

- Eureka Discovery Client.
- Consul Discovery Client.
- Kubernetes Discovery Client.
- Zookeeper or another discovery implementation.
- `SimpleDiscoveryClient` / statically configured list in appropriate environments.
- Application's custom `ServiceInstanceListSupplier`.

LoadBalancer uses `ServiceInstanceListSupplier` to obtain the list, after which `ReactiveLoadBalancer` selects an instance. Hence an empty list can come from the registry, supplier, zone/hint/version/health filters, or cache — not necessarily because the registry lost the entire service.

### 2.4. Ensure the Right Dependencies

A discovery setup typically requires:

- Gateway Server WebFlux starter compatible with the release train.
- `spring-cloud-starter-loadbalancer`.
- The corresponding discovery client starter if using a real registry.
- Correct registry endpoint/configuration, credentials, and network policies.
- Instance registration configuration on the backends.

Do not add an arbitrary DiscoveryClient dependency and assume every service ID will automatically have instances. Verify actual dependencies, auto-configuration, registry connectivity, and returned data.

## 3. Understand the Default 503 and the 404 Option Precisely

### 3.1. No Instance Found: Default Is 503

Spring Cloud Gateway documentation states: if `ReactorLoadBalancer` cannot find a service instance for a `lb://...` URI, the Gateway defaults to returning **503**. This is a reasonable response because the route exists, yet the service currently has no selectable instances.

**404 is a configuration option**, not a fix for discovery. It only changes the status when LoadBalancer fails to pick an instance; it does not create instances and does not fix connection refused.

### 3.2. Property by Release

Example of the new namespace in **Gateway Server WebFlux 5.x**:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          loadbalancer:
            use404: false
~~~

In Gateway docs/branches using the older namespace, the property is typically written as:

~~~yaml
spring:
  cloud:
    gateway:
      loadbalancer:
        use404: true
~~~

**Do not put both variants together via copy/paste.** The property name must match the actual Gateway version. Gateway 5.x Configuration Properties documentation lists `spring.cloud.gateway.server.webflux.loadbalancer.use404`; docs for some earlier branches list `spring.cloud.gateway.loadbalancer.use404`. Verify `configprops`/effective configuration after upgrading.

Choose 404 only when the public API contract genuinely intends to mask missing instances as "not found". For operating microservices, 503 usually separates **non-existent route** (404) from **temporarily unavailable service** (503) much better.

### 3.3. Do Not Turn Every Upstream Error into 404

| Scenario | Potentially Appropriate Status |
| --- | --- |
| No route matched | 404 |
| `lb://` route matched, no ServiceInstance | 503 default; 404 if option enabled |
| Backend received request and returned resource 404 | Keep 404 per business contract |
| Gateway cannot connect to upstream | 502 or other transport-error policy; configure/verify accordingly |
| Gateway waited for upstream past deadline | 504 is usually appropriate for gateway timeout |
| Upstream overloaded and returns 503 | Keep 503 if no retry/fallback succeeded |

**Do not use `use404` to cure DNS/connect/TLS/timeout errors.** This setting only affects the branch where LoadBalancer fails to pick an instance.

## 4. Read Logs to Separate Error Sources

### 4.1. Signs of No ServiceInstance

Logs often contain a message similar to:

~~~text
No servers available for service: ORDER-SERVICE
~~~

The exact message depends on implementation/version and log level. The key point is that LoadBalancer received an empty list or no server response.

Check:

1. Does the service ID in the route match the exact name published by DiscoveryClient?
2. Are any instances registered?
3. Did a health supplier/filter eliminate all instances?
4. Was the LoadBalancer context created and enabled?
5. Is the registry reachable from the Gateway?
6. Is a cache holding a stale/empty list?

### 4.2. Signs of Connection Refused

For example, logs may show:

~~~text
java.net.ConnectException: Connection refused
Caused by: io.netty.channel.AbstractChannel$AnnotatedConnectException
~~~

This indicates the Gateway attempted to connect to a specific address, but the TCP handshake was rejected. Check the selected host/port, listening process, Service/Endpoint, and network path.

### 4.3. Signs of DNS Failure

~~~text
java.net.UnknownHostException: orders-service.default.svc.cluster.local
~~~

The hostname does not resolve in the Gateway's environment. Check service DNS, namespace/search domain, DNS policy, CoreDNS/resolver, and target URI name.

### 4.4. Signs of Timeout

Logs may indicate a connect timeout, response timeout, pool acquire timeout, or cancellation. Distinguish:

- **Connect timeout:** failed to establish a TCP connection within the allowed time.
- **Response timeout:** connected/sent request, but did not receive a response soon enough.
- **Pool acquire timeout:** waited too long for a connection from the pool; the request may not have been sent to the backend yet.
- **TLS handshake timeout:** started a secure connection, but the handshake did not complete.

Exception names/messages vary by Netty, Gateway, and version. Record the **root cause**, route ID, selected target (redacted), timestamp, and upstream attempts, not just the outer `500 Server Error` log line.

### 4.5. Signs That Upstream Itself Returned HTTP 503

If the Gateway received HTTP status 503 from the backend, that is not a connection error. Check:

- Backend logs at the exact timestamp/trace ID.
- HTTP response headers/body returned by the backend.
- Recorded request or server access log proving the request reached the backend.
- Whether Gateway Retry/CircuitBreaker altered the final response.

Do not classify an upstream 503 as "No servers available" if LoadBalancer already selected an instance and the backend returned an HTTP response.

## 5. First Checklist When Seeing 503

Proceed in order, starting with non-invasive data collection:

1. Record timestamp, request path/method, route ID, trace/correlation ID, and final status.
2. Determine whether the route URI uses `lb://SERVICE-ID` or `http(s)://host:port`.
3. Check Gateway logs for `No servers available`, `ConnectException`, `UnknownHostException`, timeouts, or SSL errors.
4. Check route ID, target service ID, and path after `StripPrefix`/`RewritePath`.
5. If using LoadBalancer, verify how many instances DiscoveryClient returned at the time of failure.
6. If an instance was selected, verify hostname/port and connectivity from the Gateway's network namespace.
7. Check whether the upstream received the request and returned 503 itself.
8. Check whether retry, circuit breaker, and fallback altered the status/attempt count.
9. Compare a successful request against a failing request on the same route.
10. Only after isolating the layer should you change registry, network, timeouts, pool, or retry settings.

~~~text
Three questions to answer before making a fix:
  A. Did the Gateway have a ServiceInstance to choose?
  B. Was the Gateway able to open a connection to the selected host:port?
  C. If connected, did the upstream return an HTTP response?
~~~

## 6. Diagnosing an Empty ServiceInstance List

### 6.1. Confirm the Service ID Matches the Registry

Route:

~~~yaml
routes:
  - id: orders-api
    uri: lb://ORDER-SERVICE
    predicates:
      - Path=/api/orders/**
~~~

The service ID must match the value used by DiscoveryClient/LoadBalancer. For instance, the registry may publish `ORDER-SERVICE` while the route calls `lb://orders-service`. Do not assume every registry normalizes casing automatically.

When using Discovery Locator to auto-generate routes, Gateway provides a `lower-case-service-id` option in some discovery integrations to adjust service ID casing in paths/routes. This **does not automatically fix every explicit route URI**. Verify the service ID in the registry and the actual route instead of guessing casing.

### 6.2. Verify DiscoveryClient Is Present in the Application

Questions to answer:

- Does the Eureka/Consul/Kubernetes/Zookeeper starter match the Spring Cloud release train?
- Is `spring-cloud-starter-loadbalancer` on the runtime classpath?
- Are the registry URI, TLS, credentials, namespace, and network policy correct?
- Is the Gateway actually receiving metadata/instances from DiscoveryClient?
- Was LoadBalancer disabled via `spring.cloud.loadbalancer.enabled=false` or custom configuration?
- Was the application name confused with the registered service ID?

If an application uses `lb://ORDER-SERVICE` without any source of service instances, LoadBalancer cannot guess an IP/port from the name alone.

### 6.3. Check the Registry and Registration Status

For the service registry:

1. Open the registry dashboard/API on the management network.
2. Search for the exact service ID.
3. Inspect instance count, host, port, scheme/secure flag, and metadata.
4. Check health/lease/heartbeat status and registration timestamp.
5. Check whether instances recently restarted, changed IP, or left the registry.
6. Correlate when the Gateway started seeing an empty list against deploys/rollouts/config changes.

Do not expose the registry admin dashboard publicly for debugging. Use credentials and a private management network.

### 6.4. Check Service Registration on the Backend

A backend may be running yet fail to register with the registry because:

- Discovery client dependency is missing.
- Registration is disabled.
- The app started before the registry was reachable and did not retry registration properly.
- Wrong profile or application name/service ID.
- Invalid metadata/zone/health status.
- The service binds a port different from the registered port.
- The Pod is not Ready or readiness probe is failing.
- The instance was deregistered during shutdown/rollout.

Inspect the **backend service** logs, not just the Gateway. An empty registry list can happen simply because the upstream service never registered.

### 6.5. Check Service IDs with Discovery Locator

If you want the Gateway to auto-generate routes from DiscoveryClient, for example in Gateway 5.x:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          discovery:
            locator:
              enabled: true
              lower-case-service-id: true
~~~

Discovery Locator can generate URIs like `lb://serviceId` by default. Enable it only when you intentionally want to expose those services through the Gateway. Do not enable it broadly across all internal services without authentication, route allowlists, and path policies. If explicit routes are already declared, verify they do not collide with auto-generated routes or exhibit unintended precedence.

## 7. Registry Has Instances, Yet LoadBalancer Still Selects None

The registry dashboard showing instances does not always mean LoadBalancer receives a non-empty list. The following layers can filter the list:

~~~text
DiscoveryClient
    -> DiscoveryClientServiceInstanceListSupplier
    -> optional cache
    -> health / zone / hint / version / custom supplier filters
    -> ReactorLoadBalancer.choose()
    -> selected ServiceInstance or EmptyResponse
~~~

### 7.1. Caching May Hold Stale Data

Spring Cloud LoadBalancer caches instance lists. Spring Cloud Commons documentation notes a default built-in cache TTL of 35 seconds in the documented configuration; applications can tune `spring.cloud.loadbalancer.cache.ttl` and `capacity`.

During service deploys/scaling:

- The registry may already be updated while the Gateway still uses a cached list.
- An old instance may already be terminated before the cache refreshes.
- If the DiscoveryClient implementation already caches internally, adding LoadBalancer caching can cause **double caching**.
- Disabling caching completely can increase load on the registry; it is not the default solution.

Illustrative TTL configuration example:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        ttl: 15s
        capacity: 256
~~~

Choose the TTL based on instance churn rate, SLA, and registry capacity. If the provider already caches, check provider recommendations; `spring.cloud.loadbalancer.cache.enabled=false` may be needed to avoid caching twice.

### 7.2. Health Checks Can Eliminate Instances

`HealthCheckServiceInstanceListSupplier` probes instances from the delegate supplier and only provides those considered healthy per the mechanism/version. It is especially useful with `SimpleDiscoveryClient` or small setups; discovery-backed registries usually already return health status, so adding redundant health checks may be unnecessary.

A custom LoadBalancer configuration using the documented builder API:

~~~java
package example.gateway.lb;

import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

public class OrdersLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier discoveryClientServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withHealthChecks()
                .build(context);
    }
}
~~~

This is an example supplier configuration. When applying it to a single service, attach it via `@LoadBalancerClient` matching your release train, and ensure the configuration class is not accidentally component-scanned as a global configuration. Do not register the same custom supplier globally if only one service needs health checks.

### 7.3. Health Endpoint and Port Must Be Correct

The default health check typically uses `/actuator/health`; you can configure a default path or per-service path:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        path:
          default: /actuator/health
          ORDER-SERVICE: /actuator/health/readiness
        interval: 25s
        initial-delay: 10s
~~~

This is a property example; verify names/duration types per version. Inspect the endpoint:

- Does it actually exist on the instance?
- Does it require authentication that the health checker does not send?
- Is it running on a management port different from the service port?
- Does it return 200/healthy with the expected semantics?
- Is the health check request blocked by a gateway/network policy?
- Does the readiness path reflect traffic readiness rather than merely process liveness?

If the health check uses the wrong path/port, healthy running instances can be marked unhealthy. If a separate port is needed, LoadBalancer offers a health-check port property in supported releases; verify before configuring.

**Version note:** supplier behavior when all instances fail health checks can differ between releases/suppliers. Do not assume it always fails open or always fails closed; check your implementation/version and actual list metrics.

### 7.4. Zone, Hint, and Version Filtering

The list may become empty after filtering:

- Zone preference keeps only instances in the desired zone.
- Hint/header selects a subset with no matching instances.
- API version routing looks for version metadata that does not exist.
- Custom supplier drops instances lacking the right tenant/capability.
- Health filter marks everything unhealthy.

In particular, if using API versioning via metadata, a request selecting a version with no instances can yield an **empty list** even when the service has instances of another version. Check request headers/queries, LoadBalancer hints, zone metadata, and version metadata.

### 7.5. Do Not Confuse Gateway Health with Backend Health

Gateway `/actuator/health` returning UP does not prove every target service has instances. Some health indicators only reflect the Gateway process itself; each downstream's health requires its own metrics/health checks, and Gateway readiness should not depend on every downstream service unless the architecture explicitly wants cascading failure.

## 8. If a ServiceInstance Was Selected: Check Host and Port

### 8.1. Connection Refused Usually Means Wrong TCP Target or Nothing Listening

Suppose LoadBalancer selects:

~~~text
host = 10.20.1.15
port = 8081
secure = false
~~~

Yet the backend is actually listening on port 8080. Or the service process stopped, the container is restarting, port mapping is wrong, or the app only binds loopback. When the Gateway connects to an address with no listener, TCP can return `Connection refused`.

Check:

1. `ServiceInstance.host` and `ServiceInstance.port`.
2. The port the process actually listens on inside the container.
3. Service `port` and `targetPort` (if Kubernetes).
4. Whether registry metadata has the right port/scheme.
5. Whether the backend bind address accepts traffic from the Pod network.
6. Whether the instance just terminated while still remaining in registry/cache.
7. Whether a service mesh sidecar intercepts and forwards the right port.

### 8.2. Kubernetes: Service, EndpointSlice, Pod

For Kubernetes, inspect within the service's namespace:

~~~bash
kubectl get svc -n app
kubectl get endpointslices -n app \
  -l kubernetes.io/service-name=orders
kubectl get pods -n app -o wide
kubectl describe svc orders -n app
~~~

Cross-check the results:

- Does the Service selector match the Pod labels?
- Which endpoint addresses/ports does EndpointSlice list?
- What are the endpoint conditions (Ready/Serving/Terminating)?
- Does `targetPort` point to the right container port?
- Is the readiness probe passing?
- Is the Pod restarting/crashlooping?
- Does NetworkPolicy allow the Gateway namespace/pod to reach the service port?
- Is the Service in a different namespace, and is DNS/service discovery config correct?

**A Service existing does not mean ready endpoints exist.** A Kubernetes Service with no ready endpoints can result in connection failures or an empty discovery list, depending on the integration and routing path.

### 8.3. Test from the Gateway's Network Namespace

Do not only run curl on your laptop or a node. Test from where the Gateway actually runs, because DNS, routes, security groups, and NetworkPolicies differ.

~~~bash
# Replace hostname/port with the actual resolved target.
getent hosts orders.default.svc.cluster.local
nc -vz orders.default.svc.cluster.local 8081
curl -sv --connect-timeout 2 \
  http://orders.default.svc.cluster.local:8081/actuator/health
~~~

If the Gateway image lacks `curl`/`nc`, use an ephemeral debug container or organization-approved network tools in the same network namespace. Do not install debug packages into production images just for temporary checks.

### 8.4. Distinguish Refused from Timeout

| Result | Typical Meaning |
| --- | --- |
| Immediate connection refused | Host is reachable, but port has no listener or device actively rejects |
| Connect timeout | Packets dropped, wrong network path/ACL/security group, or target overloaded |
| DNS NXDOMAIN/UnknownHost | Wrong service/namespace/search domain or DNS failure |
| TLS handshake error | TCP connected, but TLS/certificate/protocol is incompatible |
| Fast HTTP 404/503 | An HTTP server already responded; check route/app/upstream |
| Response timeout after sending | Backend processing slowly, deadlock, queueing, or congested response path |

Do not rely on `ping` as sole proof: ICMP may be blocked while TCP works, or ping may succeed while the service port remains closed.

## 9. Check HTTP/HTTPS Scheme and Certificates

### 9.1. ServiceInstance isSecure Can Change the Scheme

Gateway LoadBalancer can use `ServiceInstance`'s `isSecure` value to decide the outbound scheme. For example, a client reaches Gateway via HTTPS, yet an instance marked non-secure causes downstream traffic to use HTTP; the reverse can also happen. If a route uses a `lb` scheme prefix with special semantics, the route's scheme may take precedence per documentation.

Therefore, verify:

- Does the route URI use `lb://...` or `lb:https://...`/scheme prefix per your release syntax?
- Is the ServiceInstance secure flag/metadata accurate?
- Does the backend actually serve TLS on the registered port?
- Does the certificate SAN match the hostname verified by the client?
- Is the certificate chain complete and the CA trusted?
- Is SNI sent properly for the target hostname?
- Is the certificate expired or not yet valid?
- Are TLS versions/ciphers compatible?

### 9.2. Do Not Disable Certificate Verification to "Fix 503"

The property `use-insecure-trust-manager` exists in some Netty HttpClient configurations, but documentation marks it **insecure and unsuitable for production**. Do not use it to hide CA/SAN errors. Configure the truststore/SSL bundle/certificates properly and verify hostnames.

Example timeout and trusted certificates config in Gateway WebFlux 5.x:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            ssl:
              trusted-x509-certificates:
                - classpath:certs/orders-ca.pem
              handshake-timeout: 10s
~~~

This is a property example that must be verified against your release and supported certificate formats. If using mTLS, also configure the client key/certificate via the appropriate SSL bundle/keystore; never commit passwords/keys to Git.

## 10. When Is It DNS vs. Service Discovery?

### 10.1. Two Name Resolution Paths

~~~text
Route: lb://ORDER-SERVICE
   -> DiscoveryClient
   -> ServiceInstance(host, port, secure, metadata)
   -> Netty HttpClient

Route: http://orders.default.svc.cluster.local:8081
   -> DNS resolver
   -> IP address
   -> Netty HttpClient
~~~

With `lb://`, the Gateway may not invoke DNS directly for the service ID; DiscoveryClient returns the actual host/port. With a fixed URI using a hostname, the Netty/DNS resolver must resolve that name. A service ID missing from the registry is distinct from an unresolvable hostname.

### 10.2. Questions When Seeing UnknownHostException

- Does the hostname come from route config or from a ServiceInstance?
- If from the registry, is the instance host a valid IP/hostname?
- If Kubernetes DNS, are service/namespace/domain suffix correct?
- Does the Gateway Pod have the right DNS policy and nameservers?
- Is CoreDNS erroring or throttling?
- Is a DNS cache/TTL holding an old IP?

### 10.3. Registry Reachable Does Not Mean Backend Reachable

The Gateway may successfully connect to Eureka/Consul yet fail to reach an instance IP due to a network ACL. The registry only supplies metadata; it does not guarantee an open data-plane path from Gateway to backend. Test both paths separately:

1. Gateway → Discovery Registry API.
2. Gateway → selected ServiceInstance host:port.

## 11. Timeouts, Connection Pool, and Stale Connections

### 11.1. Three Different Timeouts

Gateway WebFlux lets you configure connect timeout, response timeout, and connection-pool acquire timeout.

| Timeout | Waiting For What? | Symptom |
| --- | --- | --- |
| Connect timeout | TCP connection to target | Connect timeout / network unreachable |
| Response timeout | Downstream response | Read/response timeout |
| Pool acquire timeout | Acquiring a connection from pool | Pending acquire timeout, pool saturation |

Gateway WebFlux 5.x example:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            connect-timeout: 1000
            response-timeout: 5s
            pool:
              type: fixed
              max-connections: 200
              acquire-timeout: 1000
              metrics: true
~~~

These values are **illustrative examples**, not production sizing. Connect timeout is specified in milliseconds; response timeout uses a Duration; pool acquire timeout applies to pool type FIXED. Check your actual version and configuration.

### 11.2. Overly Short Timeouts Also Cause Perceived 503/5xx

If backend p99 is 2 seconds while Gateway response timeout is 500 ms, valid requests can be cut off before the backend responds. Conversely, raising timeouts indefinitely holds connections/in-flight requests longer, potentially causing overload when the backend is already slow.

Set timeouts according to a latency budget:

~~~text
Client deadline
  > Gateway processing + outbound budget
  > backend service budget
  > database/dependency budget
~~~

Deadlines must coordinate so downstream has time to return errors before the client gives up. Do not set identical timeouts at every layer or give the backend a longer timeout than the client without good reason.

### 11.3. Connection Pool and Idle Connections

Some failures appear after idle periods: the Gateway reuses a connection already closed by a load balancer/proxy/backend due to an idle timeout, causing the new request to fail. Check:

- Pool type and max connections.
- Gateway max idle time/lifetime.
- Idle timeouts at ingress/load balancer/backend.
- Pool pending acquire/active/idle metrics.
- TCP keepalive and server-side idle close behavior.
- Connection reset on reuse.

You can tune `max-idle-time` so connections are not kept longer than the upstream idle timeout. Do not disable pooling immediately as a default fix: doing so increases TCP/TLS handshakes and connection churn. Only test pool disabled in staging when evidence points to pool reuse as the culprit.

### 11.4. Pool Metrics Help Spot Connection Starvation

Gateway 5.x provides a property to enable Netty HttpClient pool metrics:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            pool:
              metrics: true
~~~

Observe active/idle/pending connections, pending acquire timeouts, and request latency. If pool acquire timeout triggers before a request even leaves the Gateway, adding backend replicas may not solve pool capacity/traffic policy constraints on the Gateway.

## 12. Retry and CircuitBreaker: Aid Recovery, Not Root-Cause Fixes

### 12.1. Retry Can Try Another Instance

Spring Cloud LoadBalancer supports retrying on the next instance. Common properties include:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        avoid-previous-instance: true
~~~

Names and behavior should be checked against your release train/integration. Retrying on the next instance helps when **multiple instances** exist and errors occur on only one instance. If the instance list is empty, retry cannot conjure a new instance. If every instance has the wrong port or is blocked by NetworkPolicy, retry merely multiplies attempts and latency.

Gateway has its own `Retry` GatewayFilter, while LoadBalancer has its own retry policy. Enabling both can produce more total attempts than expected. Track actual requests hitting upstream, separating Gateway retries from LoadBalancer retries.

### 12.2. Only Retry Operations with Appropriate Semantics

- GET/HEAD are generally safer to retry when backends are idempotent.
- A POST creating an order/payment may already have committed even if the Gateway received no response.
- Retrying after a connect failure differs from retrying after a timeout mid-processing on the backend.
- If retrying write requests, require idempotency keys, backend deduplication, and side-effect checks.
- Use appropriate backoff/jitter; prevent all Gateway replicas from retrying simultaneously.

### 12.3. Circuit Breaker Does Not Create a ServiceInstance

A circuit breaker can open when failure rate/slow calls exceed thresholds. While open, requests are short-circuited and may route to a fallback. If the fallback returns 503, the client sees 503 even though the backend **was not called** on that request.

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-api
              uri: lb://ORDER-SERVICE
              predicates:
                - Path=/api/orders/**
              filters:
                - name: CircuitBreaker
                  args:
                    name: ordersCircuit
                    fallbackUri: forward:/fallback/orders
~~~

This is a Gateway 5.x example; the fallback handler must be implemented and policy made explicit. A fallback should not return a fake 200 for an unconfirmed write operation. Returning Problem Details 503 or a business-specific response is appropriate if the contract accurately defines operation state.

### 12.4. When Retry/CircuitBreaker Are Enabled

1. Check circuit state (closed/open/half-open).
2. Count requests actually reaching upstream.
3. Check retry counts in both Gateway filter and LoadBalancer.
4. Check which instance was picked on each attempt.
5. Determine whether the final response came from upstream, fallback, or an exception handler.
6. Do not disable production circuit breakers to debug without limiting load; use staging/canary.

## 13. Observing Gateway and LoadBalancer

### 13.1. Metrics to Enable

Gateway Server WebFlux 5.x example:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          metrics:
            enabled: true
    loadbalancer:
      stats:
        include-path: false
~~~

An appropriate Actuator/Micrometer registry is required. Gateway documentation describes the `spring.cloud.gateway.requests` timer with tags such as route ID, route URI, outcome, status, HTTP status code, and method. Spring Cloud LoadBalancer exposes these meters:

- `loadbalancer.requests.success`: LoadBalancer requests ending with a response.
- `loadbalancer.requests.failed`: requests ending with an exception.
- `loadbalancer.requests.discard`: failed to acquire a ServiceInstance to execute the request.

**Discard** is a telling signal when suspecting an empty instance list. It differs from a failed connection to an already-selected instance.

### 13.2. Observability Matrix

| Metric / Log | Signal | How to Interpret |
| --- | --- | --- |
| Gateway requests status 503 | Client received 503 | Origin not yet isolated; check route/error source |
| LoadBalancer discard rising | Failed to obtain instance | Check registry, suppliers, cache/filters |
| LoadBalancer failed rising | LB request ended with exception | Check selected instance and transport |
| LoadBalancer success rising, upstream 503 | HTTP response received | Backend returned status or response pipeline |
| Connection refused logs | TCP connect rejected | Host/port/listener/network |
| UnknownHostException | Hostname did not resolve | DNS/service ID/registry host |
| Pool pending acquire rising | Waiting on connection pool | Capacity/pool saturation |
| Connect timeout | TCP handshake timed out | Network path/firewall/target |
| Response timeout | Target responded slowly | Backend latency/dependencies |
| TLS handshake error | Secure connection failed | Cert/SAN/SNI/truststore/scheme |

An aggregate 503 metric is not enough to isolate the cause. Combine **route ID + error category + LoadBalancer meters + upstream request count**.

### 13.3. Actuator Metrics on the Management Network

~~~bash
curl -s http://localhost:8080/actuator/metrics/spring.cloud.gateway.requests
curl -s http://localhost:8080/actuator/metrics/loadbalancer.requests.discard
curl -s http://localhost:8080/actuator/metrics/loadbalancer.requests.failed
~~~

Metric names/availability depend on dependencies, version, observations, and registry. If metrics are missing, verify Actuator, LoadBalancer stats instrumentation, and the Micrometer registry are configured.

Never expose Actuator metrics/routes/env to the Internet. Only expose needed endpoints on the management network with authentication/access control.

### 13.4. Temporary Log Levels

~~~yaml
logging:
  level:
    org.springframework.cloud.gateway: DEBUG
    org.springframework.cloud.loadbalancer: DEBUG
~~~

Enable only in staging/canary or during a short controlled window. Watch log volume and avoid dumping Authorization/cookies/bodies. Logger names and detail vary by version. Do not turn on full Netty DEBUG in production as a default measure; wiretap can generate huge log volumes and leak payloads.

### 13.5. Logging by Route and Error Category

A useful operational event:

~~~text
timestamp=...
routeId=orders-api
serviceId=ORDER-SERVICE
outcome=UPSTREAM_CONNECT_FAILURE
selectedInstance=orders-7.internal:8081
exceptionCategory=CONNECT_REFUSED
attempt=1
durationMs=18
traceId=...
~~~

This is an illustrative schema, not default output. Instance host/port should stay strictly in authorized internal logs; never return them to clients or use dynamic hostnames as metric labels.

## 14. Layer-by-Layer Diagnostic Workflow

### Step 1 — Verify the Effective Route

- Did the route ID match the request?
- Is the URI `lb://ORDER-SERVICE` or a fixed host?
- Are the service ID name and case right?
- Do path/method/host predicates match?
- Does StripPrefix/RewritePath affect the path?
- Is Discovery Locator generating overlapping routes or unexpected precedence?

If no route matched, it is a no-route 404, not a LoadBalancer 503.

### Step 2 — Check the Instance List

- Does DiscoveryClient recognize the service ID?
- Are there any instances?
- Are host/port/secure flags accurate?
- Are registry status/heartbeat/lease valid?
- Did zone/hint/version/health filters exclude everything?
- Is the cache holding stale data?
- Is there a custom ServiceInstanceListSupplier?

If the list is empty, fix discovery/supplier before checking ports.

### Step 3 — If an Instance Exists, Check Connectivity

- Does DNS resolve the target?
- Is the TCP port open?
- Is the backend process listening?
- Does the Kubernetes EndpointSlice have ready endpoints?
- Do NetworkPolicy/security groups permit traffic?
- Do Gateway and backend share compatible service mesh/TLS policies?
- Does the pool have stale connections/pending acquires?

### Step 4 — Inspect the Upstream Response

- Did the backend receive the request?
- Which HTTP status did the backend return?
- Did the response time out or was a streaming body interrupted?
- Did Retry/CircuitBreaker modify the final response?
- Can the request ID be correlated between Gateway and backend?

### Step 5 — Check Errors Inside the Gateway

- Do logs show ConnectException, UnknownHostException, or SSLException?
- Is a custom error handler/fallback mapping statuses?
- Are there pool acquire timeouts or event-loop pressure?
- Is the Gateway Pod experiencing CPU/memory/DNS/network pressure?

### Step 6 — Verify After Fixing

- Re-run the same request on the route.
- Confirm upstream request count increments as expected.
- Confirm the intended target instance is hit.
- Confirm response status/body match expectations.
- Test across multiple Gateway replicas.
- Monitor discard/failed/latency metrics after rollout.

## 15. Kubernetes: Service, EndpointSlice, and Pod Readiness

### 15.1. Inspect Service and Endpoints

~~~bash
kubectl get svc orders -n app -o yaml
kubectl get endpointslices -n app -l kubernetes.io/service-name=orders -o yaml
kubectl get pods -n app -l app=orders -o wide
kubectl describe svc orders -n app
~~~

Cross-check:

- Does the Service selector match Pod labels?
- Are `port` and `targetPort` correct?
- What endpoint addresses/ports are in EndpointSlice?
- What are the Ready/Serving/Terminating endpoint conditions?
- Is the Pod restarting/crashlooping/OOMKilled?
- Is the readiness probe passing?
- Does NetworkPolicy permit the Gateway namespace/pod to access the service port?

**A Service existing does not mean ready endpoints exist.** A Service with no ready endpoints can cause connection failures or empty discovery lists depending on the integration.

### 15.2. Inspect Pod and Logs

~~~bash
kubectl describe pod <orders-pod> -n app
kubectl logs <orders-pod> -n app --since=15m
kubectl logs <orders-pod> -n app --previous
~~~

Look for startup failures, readiness/liveness probes, port binding, restart count, and startup delays. If the app binds only loopback instead of the Pod interface, the Service/Pod IP cannot be reached even though the process is running.

### 15.3. Check NetworkPolicy

~~~bash
kubectl get networkpolicy -A
kubectl describe networkpolicy -n app
~~~

Verify egress from the Gateway to the backend port and ingress into the backend. Check that the CNI actually enforces policies, namespace labels, and pod selectors. A default-deny policy can cause timeouts even when Service and EndpointSlice are correct.

Do not loosen NetworkPolicies/ports in production via trial and error. Gather the selected endpoint, port, TCP probe, EndpointSlice, and effective network policy before making changes.

## 16. Distinguishing DNS from Service Discovery

### 16.1. Two Target Resolution Paths

~~~text
Route: lb://ORDER-SERVICE
   -> DiscoveryClient
   -> ServiceInstance(host, port, secure, metadata)
   -> Netty HttpClient

Route: http://orders.app.svc.cluster.local:8081
   -> DNS resolver
   -> IP address
   -> Netty HttpClient
~~~

With `lb://`, the Gateway queries DiscoveryClient for instances; DNS may not be invoked directly for the service ID. With a fixed URI using a hostname, Netty/DNS resolver must resolve that name. A service ID absent from the registry is different from an unresolvable hostname.

### 16.2. UnknownHostException

- Did the hostname come from route config or from a ServiceInstance?
- If from the registry, is the instance host a valid IP/hostname?
- If Kubernetes DNS, are service/namespace/domain suffix correct?
- Does the Gateway Pod have the right DNS policy/nameserver?
- Is CoreDNS erroring/throttling?
- Is DNS cache/TTL holding an old IP?

### 16.3. Registry Reachable Does Not Mean Backend Reachable

The Gateway may connect to Eureka/Consul yet fail to connect to an instance IP due to a network ACL. The registry only provides metadata; it does not guarantee the data-plane path from Gateway to backend. Test both paths separately:

1. Gateway → Discovery Registry API.
2. Gateway → selected ServiceInstance host:port.

## 17. Choose the Fix Based on Evidence

| Evidence | Remediation |
| --- | --- |
| Wrong route service ID | Fix URI/registry name |
| Missing registration in registry | Fix backend registration/registry connectivity |
| Empty EndpointSlice because Pod not Ready | Fix readiness/rollout/backend startup |
| Wrong registered host/port | Fix metadata/registration/service targetPort |
| All instances dropped by health filter | Fix health path/port/security/health policy |
| Stale LoadBalancer cache | Adjust cache TTL/refetch per evidence |
| Fixed-URI DNS error | Fix DNS/service name/resolver |
| Connection refused | Fix listener/port/target/endpoint |
| Network timeout | Fix routing/ACL/NetworkPolicy/firewall |
| TLS handshake error | Fix cert/truststore/SNI/scheme |
| Backend genuinely returns HTTP 503 | Fix capacity/dependency/maintenance or keep 503 per contract |
| Gateway pool acquire timeout | Fix pool capacity/concurrency/upstream latency |
| Circuit breaker constantly opening | Investigate underlying failures and thresholds |
| Retry generating excessive attempts | Fix retry scope/idempotency/backoff |

Do not raise timeouts if the service ID is wrong. Do not restart the Gateway if the registry has no instances. Do not enable retries if every instance returns connection refused. Do not turn 503 into 404 just to make a dashboard look less red.

## 18. Comprehensive Hands-On Lab

**Scenario:** Gateway Server WebFlux has an `lb://ORDER-SERVICE` route for `/api/orders/**`. After a backend deployment, clients begin receiving 503. You need to determine whether LoadBalancer lacks a ServiceInstance or selected an instance whose host/port connection fails.

### Requirements

1. Record the Gateway/Spring Boot/Spring Cloud release train and WebFlux runtime.
2. Declare the `orders-api` route using `lb://ORDER-SERVICE`.
3. Use a mock DiscoveryClient or test ServiceInstance supplier for three cases: empty list, valid instance, and wrong-port instance.
4. For the empty list, verify the default 503; test `use404` in a separate test.
5. For the valid instance, use MockWebServer or a local backend to verify requests are actually proxied.
6. For the wrong-port instance, capture the ConnectException/transport failure and the error handler's actual status.
7. Make the upstream actively return HTTP 503 and prove it differs from the no-instance case.
8. Test a service ID with mismatched casing.
9. Test an unreachable registry and a registry with a service that has zero healthy instances.
10. Test cache TTL to observe convergence time after instances change.
11. If using health checks, configure the proper path/port and demonstrate supplier behavior.
12. Test Gateway connect timeout and response timeout separately.
13. Test DNS unknown host and TCP refused separately.
14. Test untrusted certificates and mismatched hostname/SAN in a TLS test.
15. Enable metrics and inspect LoadBalancer discard/failed/success.
16. Inspect Retry/CircuitBreaker attempts and final status/fallback.
17. Write a runbook using logs/metrics/Actuator/kubectl/curl.
18. Never log tokens, secrets, private keys, or raw customer payloads.

### Acceptance Matrix

| ID | Scenario | Expected Outcome |
| --- | --- | --- |
| T01 | Route does not match | 404 no-route, no LB attempt |
| T02 | `lb://` empty list | Gateway default 503 |
| T03 | use404 enabled | 404 only for no-instance path per version |
| T04 | Valid instance present | Backend receives request |
| T05 | Wrong service ID | LB discard/empty selection observed |
| T06 | Instance wrong port | Transport error, not confused with empty list |
| T07 | TCP refused | Host/port/listener identified |
| T08 | DNS failure | Hostname/resolver identified |
| T09 | TLS certificate failure | Trust/SAN/SNI issue identified |
| T10 | Connect timeout | Distinguished from response timeout |
| T11 | Backend returns HTTP 503 | Upstream response and request record exist |
| T12 | Health filter drops all | Supplier/version behavior verified |
| T13 | Retry next instance | Attempt count accurate, no blind retries |
| T14 | Circuit breaker open | Clear fallback, no fake business success |
| T15 | Pool acquire timeout | Pool metrics show saturation |
| T16 | After rollout/refresh | Instance list converges and route works |

These are **test expectations**, not commands already executed on the current environment.

## 19. 503 Troubleshooting Checklist

- [ ] Identify route ID and effective URI.
- [ ] Distinguish `lb://SERVICE-ID` from fixed host/port URIs.
- [ ] Verify exact service ID and casing.
- [ ] Verify LoadBalancer and DiscoveryClient dependencies.
- [ ] Verify registry has instances and healthy registration status.
- [ ] Verify ServiceInstance host/port/secure metadata.
- [ ] Verify suppliers/filters for zone, hint, version, and health.
- [ ] Check cache TTL/double caching.
- [ ] If Kubernetes, check Service, EndpointSlice, Pod Ready, targetPort, and NetworkPolicy.
- [ ] If an instance was selected, test DNS and TCP from the Gateway network namespace.
- [ ] Distinguish refused, timeout, DNS, TLS, and pool acquire.
- [ ] Check connect/response/pool timeouts.
- [ ] Check whether the upstream actually returned HTTP 503.
- [ ] Check retry attempts and circuit breaker state/fallback.
- [ ] Enable LoadBalancer discard/failed/success and Gateway route status metrics.
- [ ] Keep Actuator/registry dashboards on the management network.
- [ ] Do not enable insecure trust managers or blind retries as firefighting workarounds.
- [ ] Verify fixes via upstream recorded requests and across multiple Gateway replicas.
- [ ] Have rollback and post-change monitoring in place.

## 20. Summary and References

When a client receives 503 from Spring Cloud Gateway, answer these in order:

1. **Does the route use `lb://`?**
2. **Did LoadBalancer receive a ServiceInstance to choose from?**
3. **If chosen, could the Gateway connect to that host/port?**
4. **If connected, did the upstream itself return 503 or did Retry/CircuitBreaker produce the final response?**

Finding no ServiceInstance in Gateway WebFlux defaults to 503; the `use404` property only changes the status for the empty instance list branch. Connection refused, DNS failure, TLS failure, and timeouts are distinct transport failures requiring investigation of endpoint/network/client configuration and actual error mapping. A backend returning 503 itself is an HTTP response that was successfully received.

Use **route ID, instance list, LoadBalancer metrics, upstream request count, and root-cause exception** to pinpoint the broken layer. Then fix the right piece: registry, supplier/cache/health, port/network, TLS, pool, or backend. Retry and CircuitBreaker only assist recovery; they cannot create missing instances or open a blocked TCP port.

### Official References

- [Spring Cloud Gateway Server WebFlux — Global Filters / ReactiveLoadBalancerClientFilter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html).
- [Spring Cloud Gateway Server WebFlux — HTTP timeouts configuration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/http-timeouts-configuration.html).
- [Spring Cloud Gateway — Configuration Properties 5.x](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html).
- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html).
- [Spring Cloud Commons — LoadBalancer Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html).
- [Spring Guide — Client-Side Load-Balancing with Spring Cloud LoadBalancer](https://spring.io/guides/gs/spring-cloud-loadbalancer/).
