# Host, IP, port, URI, and the secure property of an instance

## 1. Service identity and the address of an instance

In a distributed system, a service typically has multiple instances handling requests concurrently. Service discovery helps consumers find registered instances without hardcoding each machine's address in source code. However, to communicate properly, consumers must understand the identity and networking information each instance publishes.

An instance typically exposes the following information:

- **Service ID:** the logical name of the service, for example `inventory-service`.
- **Instance ID:** the identifier of a specific registration, for example `inventory-service:pod-7f9c`.
- **Host:** the DNS name or hostname that consumers can resolve.
- **IP address:** the IP address to which consumers can route traffic.
- **Port:** the port on which the instance accepts connections.
- **URI:** the base address built from scheme, host, and port; typically `http://host:port` or `https://host:port`.
- **Secure flag:** indicates whether the instance is advertised to be accessed over a secure protocol such as HTTPS rather than HTTP.
- **Metadata:** supplementary information such as zone, version, rack, or deployment group.

These fields are related but not interchangeable. Service ID identifies the logical service; host and port point to the current network location of an instance. The secure flag describes the access protocol the instance advertises; it does not by itself configure TLS, authenticate users, or encrypt connections.

This lesson belongs to the **Identity and Networking** chapter of the **SPRING_CLOUD_CORE** module. The module focuses on Spring Cloud Commons foundations, Context, externalized configuration, discovery, service registry, service communication, and testing and operating shared abstractions.

After this lesson, learners will be able to:

- Distinguish service ID, instance ID, hostname, and IP address.
- Distinguish the bind address from the address advertised to consumers.
- Determine the actual port an instance registers in the service registry.
- Read and build URIs from `ServiceInstance`.
- Explain the meaning of `isSecure()` and its relationship with HTTPS.
- Recognize addressing issues when running in containers, Kubernetes, or behind a reverse proxy.
- Choose between DiscoveryClient or Spring Cloud LoadBalancer based on access needs.

## 2. ServiceInstance in Spring Cloud Commons

Spring Cloud Commons defines the `ServiceInstance` abstraction to describe a reachable instance. Discovery providers such as Eureka, Consul, or Kubernetes may have their own registration models, yet consumers can work against the shared abstraction.

Commonly used methods:

| Method | Meaning |
| --- | --- |
| `getServiceId()` | The Service ID to which the instance belongs. |
| `getInstanceId()` | The instance's own ID; may be null/absent depending on the provider. |
| `getHost()` | The hostname or IP advertised by the instance. |
| `getPort()` | The port consumers use to connect to the instance. |
| `isSecure()` | Indicates whether the instance is advertised as secure. |
| `getUri()` | The base URI of the instance, usually including scheme, host, and port. |
| `getMetadata()` | A key/value metadata map published by the provider or application. |

Example:

```java
ServiceInstance instance = ...;

String serviceId = instance.getServiceId();
String instanceId = instance.getInstanceId();
String host = instance.getHost();
int port = instance.getPort();
boolean secure = instance.isSecure();
URI baseUri = instance.getUri();
Map<String, String> metadata = instance.getMetadata();
```

Do not use an IP address as the long-term identity of an instance. IPs can change when containers are recreated, pods are rescheduled, or hosts change networks. Service ID is typically more stable for consumers; instance ID is used to distinguish individual registrations.

### 2.1. Service ID and instance ID are different

Suppose there are three instances of `inventory-service`:

| Service ID | Instance ID | Host | Port |
| --- | --- | --- | ---: |
| `inventory-service` | `inventory-01` | `inventory-01.internal` | 8080 |
| `inventory-service` | `inventory-02` | `inventory-02.internal` | 8080 |
| `inventory-service` | `inventory-03` | `10.20.4.18` | 8080 |

The consumer looks up by service ID `inventory-service`; discovery returns a matching set of instances. The load balancer picks an instance based on its algorithm and state. The instance ID helps identify a specific registration in logs, metrics, or the registry.

One service ID can map to multiple host/port pairs. Do not hardcode a single host to a service ID in consumer code, unless the system truly has only one fixed endpoint and does not use discovery.

## 3. Hostname and IP address

### 3.1. Host can be a DNS name or an IP

Host is the machine name portion of a network address. Examples:

```text
inventory-01.internal
inventory.default.svc.cluster.local
10.20.4.18
2001:db8::18
```

A DNS name is generally preferable to a static IP when machine addresses can change. DNS lets infrastructure update the name-to-address mapping while consumers continue using the same service name. In container or Kubernetes environments, Service DNS is typically the stable access point.

An IP address is useful when the registry needs to advertise an instance's direct address or when the environment lacks suitable internal DNS. However, the IP must be routable from the consumer side. An address meaningful only inside a container's network namespace is not necessarily reachable from another container or another cluster.

### 3.2. Bind address and advertised address are two different concepts

An application can listen on one address while advertising a different address to consumers.

- **Bind address:** the interface address on which the server opens a socket to accept connections.
- **Advertised host/IP:** the address registered or published for consumers to use.

For example, an application inside a container binds to `0.0.0.0:8080`, meaning it listens on all IPv4 interfaces of the container. Consumers cannot call `0.0.0.0`; that is not a target address to advertise. The registry needs a hostname or IP that is actually routable to the container.

In Spring Boot, `server.address` controls the web server's bind address. This property does not by itself determine the hostname that a discovery provider registers. The registered address also depends on the provider, runtime environment, and the corresponding integration's instance configuration.

### 3.3. Selecting a network interface on multi-homed hosts

The machine running the application may have multiple interfaces: loopback, Ethernet, Wi-Fi, VPN, Docker bridge, Kubernetes interface, or management interface. If auto-detection picks the wrong interface, the registry may advertise an IP unreachable from consumers.

Spring Cloud Commons provides `InetUtils` and `spring.cloud.inetutils` properties to adjust how machine hostname/IP are discovered. Common properties:

| Property | Purpose |
| --- | --- |
| `spring.cloud.inetutils.ignored-interfaces` | Ignore interfaces matching the configured expressions. |
| `spring.cloud.inetutils.preferred-networks` | Prefer matching network ranges. |
| `spring.cloud.inetutils.use-only-site-local-interfaces` | Only consider interfaces with site-local addresses according to Java rules. |
| `spring.cloud.inetutils.default-hostname` | Fallback hostname value when no suitable hostname is found. |
| `spring.cloud.inetutils.default-ip-address` | Fallback IP value when no suitable IP is found. |

Example configuration preferring the internal network and ignoring bridge interfaces:

```yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - docker0
        - veth.*
      preferred-networks:
        - 10\.20\..*
      use-only-site-local-interfaces: true
```

Expressions and lists must match the actual network topology. Do not copy this example verbatim into every environment: IP ranges, interface names, and site-local address types vary by organization.

Spring Cloud also exposes common client properties such as `spring.cloud.client.hostname` and `spring.cloud.client.ip-address`. They support components that consume local machine info; do not assume every discovery provider will register these exact values without provider-specific rules.

### 3.4. Avoid advertising localhost or non-routable addresses

The following addresses commonly cause errors when used as the advertised host in multi-host systems:

- `localhost` or `127.0.0.1`: points only to the consumer's own loopback.
- `0.0.0.0`: wildcard bind address, not a target address for clients to call.
- A private IP reachable only inside a different network namespace.
- An IP of a management interface to which the consumer has no route.
- A hostname that resolves only inside the instance's own container.

Verify from the **consumer's network**: does DNS resolution succeed, is there a route to the IP, does the firewall allow the port, and does TLS validate the hostname properly?

## 4. Port: listening port and advertised port

The port identifies the application or endpoint accepting connections on a host. With Spring Boot, the web server listens on port `8080` by default unless configured otherwise.

Common properties:

| Property | Role |
| --- | --- |
| `server.port` | Port of the application web server. |
| `server.address` | Bind address of the web server. |
| `management.server.port` | Separate port for management/Actuator if configured separately. |
| `management.server.address` | Bind address for the separate management server. |

`ServiceInstance.getPort()` should reflect the port that consumers actually use to reach the instance under the chosen topology. Do not register the management port in place of the application port unless the service intentionally serves business APIs on that port.

### 4.1. Fixed port and random port

The port can be configured explicitly:

```yaml
server:
  port: 8085
```

Or the operating system can be asked to pick an available port:

```yaml
server:
  port: 0
```

`server.port=0` is useful in tests or when running multiple instances on the same host. Only after the server starts can the actual assigned port be used to construct URIs or register the instance. Never advertise `0` as the connection port.

In Spring Boot tests, the actual assigned port can be obtained via `@LocalServerPort`:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class InventoryApplicationTest {

    @LocalServerPort
    int port;

    @Test
    void serverUsesAnAvailablePort() {
        assertThat(port).isPositive();
    }
}
```

### 4.2. Ports in containers and Kubernetes

The port inside a container, the port published on the host, the Kubernetes Service port, and the targetPort can all differ.

| Network layer | Example port | Meaning |
| --- | ---: | --- |
| Application in container | 8080 | Spring Boot listening inside the container. |
| Kubernetes Service port | 80 | Port consumers use when calling the Kubernetes Service. |
| Kubernetes targetPort | 8080 | Target port of the container/pod. |
| NodePort or load balancer port | 30080 or 443 | Port exposed through another access layer. |

If the registry returns pod addresses directly, the port must be the port the pod listens on. If consumers call through a Kubernetes Service, consumers normally use the Service DNS and Service port. Never take a port from one network layer and pair it with a host from another layer.

Choose a consistent access model:

- Discovery registers each pod and the client-side load balancer selects a pod.
- Consumers call the Kubernetes Service DNS and let the Kubernetes Service distribute traffic.
- Consumers call a gateway/ingress, and the gateway routes to the service.

Avoid accidentally stacking multiple load-balancing layers or advertising pod addresses when consumers cannot reach the pod network.

## 5. URI and building endpoints from ServiceInstance

A URI is a structured resource address. For an HTTP instance, the base URI typically consists of:

```text
scheme://host:port
```

Examples:

```text
http://inventory-01.internal:8080
https://inventory.default.svc.cluster.local:443
```

In Spring Cloud, `ServiceInstance.getUri()` provides the instance's base URI. Consumers should use this URI instead of manually concatenating strings for host, port, and scheme. Doing so avoids bugs when handling IPv6, the secure scheme, or URI formatting.

### 5.1. Example of getting the URI and appending a path

```java
ServiceInstance instance = ...;

URI baseUri = instance.getUri();

URI itemsUri = UriComponentsBuilder.fromUri(baseUri)
        .pathSegment("api", "items")
        .build()
        .toUri();
```

The result has the form:

```text
https://inventory-01.internal:8443/api/items
```

`getUri()` is the instance's base URI; the application's context path or API path must be appended according to the endpoint contract. If the service runs under `server.servlet.context-path`, the consumer must know that base path or obtain it from explicitly managed configuration/metadata.

Avoid building URIs via string concatenation:

```java
// Error-prone when host is IPv6 or scheme/port changes.
String url = (instance.isSecure() ? "https://" : "http://")
        + instance.getHost() + ":" + instance.getPort() + "/api/items";
```

Use a URI builder to handle IPv6 brackets, encode path segments, and format URI components properly.

### 5.2. The URI is not always a public address

The URI in `ServiceInstance` is the address consumers are expected to use according to the discovery provider's network topology. It may be a pod address in the cluster network, internal service DNS, a VM's hostname/IP, or an address behind a reverse proxy/load balancer.

This URI does not automatically become a public URL. If a consumer outside the cluster needs to call the service, an endpoint reachable from the consumer's network must be exposed or an appropriate gateway must be placed in front.

### 5.3. Context path and query parameters

`ServiceInstance.getUri()` typically describes the instance's origin. API paths, query parameters, and fragments belong to a specific request, not to the instance's host/port identity.

Example:

```java
URI requestUri = UriComponentsBuilder.fromUri(instance.getUri())
        .pathSegment("api", "v1", "items")
        .queryParam("page", 0)
        .queryParam("size", 20)
        .build()
        .toUri();
```

Do not store queries containing tokens or personal data inside instance metadata. Credentials must go through proper authentication mechanisms and be managed as secrets.

## 6. The secure property and HTTPS

`ServiceInstance.isSecure()` indicates whether the instance is advertised as secure. In the standard HTTP/HTTPS model:

- `false`: the URI typically uses the `http` scheme.
- `true`: the URI typically uses the `https` scheme.

This is information about the protocol consumers should use when accessing the instance. It does not automatically enable TLS on the web server, generate certificates, or configure a trust store.

### 6.1. Three layers to distinguish

| Component | Responsibility |
| --- | --- |
| Server TLS configuration | Configures the application or proxy to actually accept HTTPS connections, certificates, and private keys. |
| ServiceInstance secure flag | Advertises to discovery consumers that the instance is accessed over a secure protocol. |
| Client TLS configuration | Verifies certificates/hostnames, trust chains, and the consumer's TLS policies. |

For example, if an instance listens on HTTPS at port `8443`, the registration needs to advertise the host, port `8443`, and the matching secure flag. Consumers will then build HTTPS URIs to connect.

If an instance only listens on HTTP at port `8080`, yet the registry marks `isSecure=true`, consumers may attempt HTTPS against an HTTP port and fail the handshake.

Conversely, if the server requires HTTPS while the instance is advertised as non-secure, consumers may call HTTP and receive redirect errors, connection failures, or security policy errors.

### 6.2. TLS termination at ingress or reverse proxy

A common pattern:

```text
Consumer -- HTTPS --> Ingress / Gateway -- HTTP --> Application Pod
```

The consumer uses HTTPS to the ingress, while the ingress connects over HTTP to the pod. In this model, the scheme and port consumers use depend on the endpoint advertised to consumers:

- If discovery returns the ingress address, that instance must reflect HTTPS and the ingress port.
- If discovery returns the pod address directly, the scheme/port must describe the pod's listener, which may be HTTP.

Do not mark secure just because the user's initial request to the ingress was HTTPS. Identify **the network hop the consumer is connecting to**. If end-to-end encryption is needed, configure TLS on the hop from ingress to pod as well and advertise the corresponding protocol.

### 6.3. The secure flag does not replace application security

`isSecure=true` does not prove that:

- The certificate is valid or signed by a trusted CA.
- The hostname in the certificate matches the URI hostname.
- The client has authenticated the server.
- The server has authenticated the client.
- The request is authorized.
- Metadata or payloads are protected on other hops.

TLS, authentication, authorization, and network policies are separate layers. Never use the secure flag as the sole condition for trusting an instance.

## 7. Metadata and supplementary instance information

`ServiceInstance.getMetadata()` returns a key/value map for information not covered by the standard fields. Examples:

```text
zone=zone-a
version=v2
weight=80
protocol=grpc
management-port=9091
```

Metadata can help a load balancer or consumer select instances by zone, version, canary group, or capacity. However:

- Metadata consists of key/value strings with no universal schema across all providers.
- Key names and meanings must be agreed upon between the registrant and consumers.
- Do not assume metadata is always present or always holds valid values.
- Do not put passwords, tokens, private keys, or secrets in metadata; registries often allow many components to read metadata.
- Do not use metadata instead of host, port, or the secure flag when standard fields already exist for that information.

Example reading zone with a fallback:

```java
String zone = instance.getMetadata().getOrDefault("zone", "unknown");
```

If an algorithm depends on metadata, define the behavior when keys are missing, malformed, or hold unsupported values.

## 8. Fetching instances directly or using Spring Cloud LoadBalancer?

### 8.1. DiscoveryClient

`DiscoveryClient` allows consumers to look up instances by service ID:

```java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");

if (instances.isEmpty()) {
    throw new IllegalStateException(
            "No instance available for inventory-service");
}
```

This API is suitable when observing the instance list, building admin tooling, or implementing specialized discovery logic. Empty lists and changing registry state must be handled.

Do not pick the first element in the list as a production load-balancing strategy. Return order carries no load-balancing guarantee, and consumers must handle failing instances, retries, zones, health, and registry changes.

### 8.2. Spring Cloud LoadBalancer

For business requests targeting a service ID, Spring Cloud LoadBalancer is usually the better abstraction. Consumers use the logical service name in the URI; LoadBalancer picks an instance and forwards the request to the corresponding host/port.

Example using `WebClient` with a load-balancer filter:

```java
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
```

This example requires WebFlux for `WebClient` and the `spring-cloud-starter-loadbalancer` dependency for load-balancer integration. Use a Spring Cloud BOM compatible with the application's Spring Boot version to manage versions.

Consumers can call the service using its service ID:

```java
webClientBuilder.build()
        .get()
        .uri("http://inventory-service/api/items")
        .retrieve()
        .bodyToMono(ItemList.class);
```

LoadBalancer selects a `ServiceInstance` from the discovery client and uses host, port, URI, secure, and metadata according to the active configuration and integration. The initial scheme in the URI is part of the input request; final scheme behavior also depends on the service instance and load balancer configuration. Explicitly test HTTPS cases when services have secure instances.

When multiple instances exist, use LoadBalancer or the platform's load-balancing mechanism. Only select instances directly when the application genuinely requires custom selection control and has fully implemented timeouts, retries, health checks, circuit breakers, and handling for disappearing instances.

## 9. Complete instance model example

Suppose a `payment-service` has two instances:

| Property | Instance A | Instance B |
| --- | --- | --- |
| Service ID | `payment-service` | `payment-service` |
| Instance ID | `payment-a` | `payment-b` |
| Host | `payment-a.internal` | `payment-b.internal` |
| Port | 8443 | 8443 |
| Secure | `true` | `true` |
| Base URI | `https://payment-a.internal:8443` | `https://payment-b.internal:8443` |
| Metadata | `zone=zone-a`, `version=v2` | `zone=zone-b`, `version=v2` |

The consumer looks up `payment-service`. LoadBalancer picks instance A or B per policy. With instance A, the request URI can be constructed as:

```text
https://payment-a.internal:8443/api/payments
```

If instance A is redeployed and receives a new IP, the registry updates the host or IP in the new registration. The consumer still looks up by service ID and needs no hardcoded URL change in source code.

## 10. Verifying addresses from the consumer's perspective

When an instance registers successfully yet consumers cannot reach it, check in order:

1. **Service ID:** is the consumer looking up the right service name?
2. **Instance ID:** does the registry hold an active registration without unintended duplicates?
3. **Host:** does the hostname resolve from the consumer's network?
4. **IP and route:** is the IP on a network reachable by the consumer?
5. **Port:** is the port the exact listener the consumer needs to call? Do firewalls/network policies allow it?
6. **URI/scheme:** does the URI use the right HTTP or HTTPS scheme?
7. **TLS:** is the certificate valid and does the hostname match?
8. **Path:** are the context path and API path accurate?
9. **Metadata:** if the load balancer uses zone/version/weight, do values match the expected schema?

You can test DNS and port from the consumer's runtime environment:

```bash
nslookup payment-a.internal
```

```bash
curl -vk https://payment-a.internal:8443/actuator/health
```

The `curl -k` flag skips certificate verification and is suitable only for isolating issues in a controlled test environment. When verifying TLS properly, omit `-k` and supply the proper CA/trust store. Never use commands that skip certificate verification as production configuration.

In containers, run checks from the actual consumer container or pod. DNS and routes on a developer laptop do not prove that the production application's network namespace can reach the same address.

## 11. Common errors

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| Registry returns `localhost` | Host inferred from local environment or misconfigured advertised host | Advertise a DNS/IP reachable from consumers. |
| Instance has right host but wrong port | Confused container, Service, NodePort, or management port | Identify which network layer consumers call and register that layer's port. |
| URI constructed as HTTP even though server requires HTTPS | Incorrect secure flag or registration scheme | Synchronize `isSecure`, port, and TLS listener. |
| HTTPS handshake fails | Port is serving HTTP, untrusted certificate, or hostname mismatch | Inspect listener, CA chain, SAN, and client trust configuration. |
| IP changes after deploy | Dynamic IP used in static configuration | Use service ID/DNS and update registrations through discovery. |
| Malformed IPv6 URI | Manual string concatenation of host and port | Use `ServiceInstance.getUri()` and a URI builder. |
| Consumer cannot reach host returned by registry | Registry advertised an unroutable interface or network namespace | Test from consumer network and configure advertised address. |
| Management health works but business API unreachable | Management port registered instead of application port, or wrong path | Separate management endpoints from service endpoints. |
| Multiple instances exist yet traffic always hits one address | Picking first instance or load balancing not enabled | Use Spring Cloud LoadBalancer or platform load balancing. |
| HTTPS outside ingress but HTTP to pod | Confused TLS termination with end-to-end TLS | Advertise the endpoint for the hop consumers call and configure TLS on each hop needing encryption. |

## 12. Design and operations guidelines

- Use service ID as the logical lookup name; never hardcode a single instance's IP in consumers.
- Choose an advertised host that consumers can actually resolve and route to.
- Distinguish `server.address` (bind address) from the address registered by the discovery provider.
- Register the port of the listener consumers need to call; never use port `0` or the management port as the application port.
- Use `ServiceInstance.getUri()` for consistent scheme/host/port; use a URI builder to append paths and queries.
- Set the secure flag to match the protocol on the hop consumers connect to. Configure TLS and certificate verification separately.
- Put only necessary metadata into the registry; never store secrets.
- Use Spring Cloud LoadBalancer for service-ID-based access in standard cases.
- Verify addresses from the consumer's network, not only from a development machine.
- Monitor registration, health, DNS, port, and TLS as parts of a single connection path.

## 13. Self-check questions

1. How does Service ID differ from instance ID?
2. Why can `0.0.0.0` be a bind address but not a valid advertised host for consumers?
3. How are `server.address` and the host in `ServiceInstance` related?
4. When `server.port=0`, how do you determine the actual port after the server starts?
5. Why can a container's port differ from a Service port or NodePort?
6. What bugs does `ServiceInstance.getUri()` help avoid when constructing URLs?
7. What does `isSecure()` describe and what does it not guarantee?
8. If TLS terminates at the ingress while the pod receives HTTP, which endpoint should the secure flag reflect?
9. When should you use `DiscoveryClient` directly and when should you use Spring Cloud LoadBalancer?
10. How do you verify host, port, and TLS from the consumer's actual network?

## 14. Official references

- [Spring Cloud Commons — Common Abstractions and Service Discovery](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons — ServiceInstance API](https://docs.spring.io/spring-cloud-commons/docs/current/api/org/springframework/cloud/client/ServiceInstance.html)
- [Spring Boot — Embedded Web Servers and Server Properties](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Kubernetes — Services, Networking, and Service DNS](https://kubernetes.io/docs/concepts/services-networking/service/)

Property names for registering host, port, and secure may differ across Eureka, Consul, Kubernetes, or other discovery providers. Always cross-check the configuration of the provider and Spring Cloud version in use; `ServiceInstance` is a common abstraction, not a universal set of registration properties shared by all registries.
