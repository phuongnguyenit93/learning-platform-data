# Mapping URIs, Protocols, and ServiceInstance Information

In Spring Cloud, service discovery does not only return a service name—it must also describe each address capable of receiving requests. With static discovery configuration, `SimpleDiscoveryClient` retrieves the instance list from application configuration instead of querying Eureka, Consul, or ZooKeeper. Each URI is mapped to a `ServiceInstance` for components like `DiscoveryClient` and Spring Cloud LoadBalancer to use.

The URI specifies the endpoint's protocol, host, and port. From there, Spring Cloud exposes `serviceId`, `instanceId`, `host`, `port`, `secure`, `uri`, and `metadata` through the `ServiceInstance` abstraction. Understanding how this mapping works helps avoid calling the wrong host/port, confusing HTTP with HTTPS, or configuring the instance list under the wrong service ID.

This content belongs to the `SPRING_CLOUD_SERVICE_DISCOVERY` module, where service discovery is used to look up instances by service name and support load balancing. This section focuses on URI mapping in static discovery and how consumers use `ServiceInstance` information.

## 1. Static discovery and SimpleDiscoveryClient

`SimpleDiscoveryClient` is a `DiscoveryClient` implementation that uses configuration properties as the data source for the service instance list. According to the Spring Cloud Commons documentation, this implementation is auto-configured when there is no `DiscoveryClient` backed by a service registry on the classpath. If the application has Eureka, Consul, or another registry-backed discovery client, do not assume the Simple configuration will be the source used; verify the actual discovery implementation in the application context.

Basic property format:

```properties
spring.cloud.discovery.client.simple.instances.service1[0].uri=http://s11:8080
spring.cloud.discovery.client.simple.instances.service1[1].uri=https://s12:8443
spring.cloud.discovery.client.simple.instances.service2[0].uri=http://s21:8081
```

Where:

- `spring.cloud.discovery.client.simple.instances` is the configuration prefix.
- `service1` and `service2` are the service IDs used for lookup.
- `[0]`, `[1]` are instance indices in the list, starting at `0`.
- `uri` is the endpoint address of each instance.

Equivalent example in YAML format:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            payment-service:
              - uri: http://payment-01.internal:8081
              - uri: https://payment-02.internal:8443
            inventory-service:
              - uri: http://inventory.internal:8083
```

When a consumer calls `getInstances("payment-service")`, `SimpleDiscoveryClient` reads the list configured under the `payment-service` key and converts each element into a `ServiceInstance`. When `getServices()` is called, the client returns the service IDs present in the configuration map. If there is no key for the requested service ID, an empty list of instances is returned.

Static discovery is suited for environments with few and relatively stable endpoints, testing, demos, legacy system integration, or transition phases. The list does not change automatically when a new server appears or an endpoint stops working; configuration must be updated and the application redeployed/refreshed according to the chosen workflow.

## 2. Structure of a service instance URI

A typical HTTP URI has the form:

```text
scheme://host:port
```

Example:

```text
https://payment-02.internal.example:8443
```

| Component | Example Value | Meaning |
|---|---|---|
| Scheme | `https` | Connection protocol. |
| Host | `payment-02.internal.example` | Hostname or IP address of the instance. |
| Port | `8443` | Port the service is listening on. |

With static discovery, the URI is a concise way to declare an endpoint. Spring Cloud maps the URI to instance properties so consumers can obtain the host, port, and secure flag. Use an absolute URI with an explicit scheme and state the port explicitly, especially when the application runs on a non-default port.

### 2.1. Hostname and IP

The host can be a DNS name or an IP:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            payment-service:
              - uri: http://payment-01.internal.example:8081
              - uri: http://10.20.0.22:8081
```

The consumer must be able to resolve the hostname or route to the IP. Do not configure `localhost`, `127.0.0.1`, or `0.0.0.0` for an instance running on another machine or container. `localhost` points back to the consumer itself; `0.0.0.0` is a wildcard address used when binding a server, not a target address to call.

If the host is an IPv6 literal, the URI must enclose the address in square brackets, for example `http://[2001:db8::10]:8081`. Verify DNS, routes, and firewalls from the consumer's actual runtime environment, not only from the provider machine.

### 2.2. Port

The port in the URI must be the port the consumer can actually reach. With containers, the port inside the container may differ from the port published to the host. With Kubernetes, Pod ports, Service ports, and NodePorts may also differ. Choose the endpoint based on the network path the consumer uses.

A URI may omit the port when using the scheme's default port. However, when parsing a URI, `getPort()` may return `-1` if the port is not specified explicitly; how a client or URI builder applies default ports depends on the implementation. To ensure `ServiceInstance` and the HTTP client agree on an explicit endpoint, specify the port explicitly. The default port for `http` is `80`, and for `https` is `443`.

## 3. Scheme and HTTP/HTTPS protocols

The scheme affects how Spring Cloud describes whether an instance uses a secure connection.

| URI | `host` | `port` | `isSecure()` |
|---|---|---:|---|
| `http://payment-01:8081` | `payment-01` | 8081 | `false` |
| `https://payment-02:8443` | `payment-02` | 8443 | `true` |

With `SimpleDiscoveryClient`, an `https` URI maps to an instance with `secure=true`; an `http` URI represents an unencrypted connection. When Spring Cloud LoadBalancer constructs the physical address for a request, the instance's secure flag is used to choose the corresponding scheme.

For example, two instances of the same service can be configured:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            payment-service:
              - uri: http://payment-01.internal:8081
                instance-id: payment-http-01
              - uri: https://payment-02.internal:8443
                instance-id: payment-https-02
```

Although instances can be described with different schemes, only mix HTTP and HTTPS when the consumer, security policy, and client configuration explicitly support both. In production, you should generally standardize on HTTPS to prevent some requests from inadvertently going over an unencrypted endpoint.

Custom schemes such as `tcp`, `grpc`, or `h2c` are not automatically translated into corresponding protocol behavior by a standard `ServiceInstance`. `isSecure()` primarily describes HTTPS connections. If you use another protocol, you need a client and routing mechanism that support that protocol; do not assume changing the URI scheme will automatically configure a gRPC or TCP client.

## 4. Mapping to ServiceInstance

`ServiceInstance` is Spring Cloud's common abstraction for describing a concrete endpoint. Key methods include:

| Method | Returned Information | Source in Static Discovery |
|---|---|---|
| `getServiceId()` | Logical service name. | Key under `instances`, e.g., `payment-service`. |
| `getInstanceId()` | Instance identifier. | `instance-id` property if configured; may be absent if omitted. |
| `getHost()` | Hostname or IP. | Host parsed from URI or dedicated host configuration. |
| `getPort()` | Instance port. | Port parsed from URI or dedicated port configuration. |
| `isSecure()` | Whether HTTPS is used. | `https` scheme or the instance's secure flag. |
| `getUri()` | Instance URI. | Endpoint constructed from instance properties. |
| `getMetadata()` | Additional key-value map. | `metadata` property in the instance configuration. |

Complete configuration example:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            payment-service:
              - instance-id: payment-01
                uri: http://payment-01.internal:8081
                metadata:
                  zone: zone-a
                  version: "2.4.1"
                  api-level: v1
              - instance-id: payment-02
                uri: https://payment-02.internal:8443
                metadata:
                  zone: zone-b
                  version: "2.5.0"
                  api-level: v2
```

Here the service ID is `payment-service`, and the two instance IDs are `payment-01` and `payment-02`. Metadata helps consumers or the load balancer distinguish zone, software version, and API level. These values do not automatically create health checks or filtering policies; the consuming component must read the metadata and enforce the corresponding rules.

### 4.1. Service ID is not a host

The service ID is the logical name the consumer uses for lookup. Host and port are the physical address of each instance. For example:

```text
serviceId = payment-service
instanceId = payment-01
host = payment-01.internal
port = 8081
uri = http://payment-01.internal:8081
```

When a request goes through the load balancer, the consumer sends it to a logical URI using the service ID, while the load balancer picks a `ServiceInstance` and replaces the service ID with the actual host/port.

## 5. Example reading ServiceInstance via DiscoveryClient

A consumer can use `DiscoveryClient` to obtain the list of declared endpoints:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class PaymentInstanceInspector {

    private final DiscoveryClient discoveryClient;

    public PaymentInstanceInspector(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public void printInstances() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances("payment-service");

        for (ServiceInstance instance : instances) {
            System.out.printf(
                    "serviceId=%s, instanceId=%s, host=%s, port=%d, secure=%s, uri=%s, metadata=%s%n",
                    instance.getServiceId(),
                    instance.getInstanceId(),
                    instance.getHost(),
                    instance.getPort(),
                    instance.isSecure(),
                    instance.getUri(),
                    instance.getMetadata()
            );
        }
    }
}
```

This snippet shows that the consumer does not need to know the details of the YAML configuration. It works with the `ServiceInstance` abstraction, so it can use the same API style when switching from Simple Discovery to Eureka, Consul, or ZooKeeper. Specific metadata values still depend on the provider.

If `getInstances("payment-service")` returns an empty list, check the service ID key in configuration, active profiles, loaded configuration files, and the actual discovery client Spring is using.

## 6. Using ServiceInstance with Spring Cloud LoadBalancer

`DiscoveryClient` supplies the instance list. Spring Cloud LoadBalancer picks an instance from the list and resolves the request from the service ID to a real address.

Example with `RestTemplate`:

```java
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate paymentRestTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
```

The consumer can call by service ID:

```java
String response = paymentRestTemplate.getForObject(
        "http://payment-service/api/payments/42",
        String.class
);
```

For this example to work, the application needs Spring Cloud LoadBalancer on the classpath and `SimpleDiscoveryClient` configured with service ID `payment-service`. `@LoadBalanced` causes the client to treat `payment-service` as a logical name to resolve; the load balancer retrieves a `ServiceInstance` and builds the physical address from the instance's host, port, and secure flag.

If you use a `RestTemplate` without `@LoadBalanced`, `http://payment-service/...` is treated as a regular hostname and will usually fail DNS resolution. Do not confuse the logical URI in the request with the physical URI in static discovery configuration.

### 6.1. Load balancing is not a health check

Static discovery returns the configured endpoints. It does not automatically ping endpoints or remove dead instances from the list just because a previous request failed. If an address stops working, the static list continues to contain that address until configuration is updated or another health-aware mechanism is added.

You can combine Spring Cloud LoadBalancer's health-check supplier or a custom endpoint checking mechanism, depending on version and configuration. Whichever approach is used, you need to determine the check interval, timeout, and behavior when all instances are unhealthy.

## 7. Metadata and routing usage

`metadata` in an instance configuration is a key-value map. Example:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            payment-service:
              - uri: http://payment-a.internal:8081
                metadata:
                  zone: zone-a
                  version: "2.4.1"
              - uri: http://payment-b.internal:8081
                metadata:
                  zone: zone-b
                  version: "2.4.1"
```

Consumers can use metadata to:

- Prefer instances in the same zone.
- Choose instances with a compatible API level.
- Observe the configured software version.
- Group instances for canary or testing environments.

Declaring metadata does not automatically enable the policies above. To filter by zone or version, you need a custom `ServiceInstanceListSupplier`, gateway policy, or dedicated instance-selection logic. A fallback is needed when no matching instance is found; avoid letting a misconfigured metadata filter produce an always-empty result list.

Do not store passwords, access tokens, private keys, or sensitive data in metadata. Metadata values frequently appear in logs or management endpoints.

## 8. URIs with paths, queries, and credentials

A general URI can also contain a path, query, fragment, or user information. However, for service discovery and load balancing, the core parts needed to identify an endpoint are normally scheme, host, and port.

Endpoint example:

```text
https://payment.internal.example:8443
```

The request path is appended on the consumer side:

```text
https://payment-service/api/payments/42
```

Do not embed username/password in a discovery URI, such as `https://user:password@host:8443`. Credentials must be managed via a secret store, OAuth2, mTLS, or an appropriate security mechanism.

If the application needs a specific base path per endpoint, verify whether the `ServiceInstance` implementation, LoadBalancer, and HTTP client preserve and merge paths as expected. Do not assume every discovery provider handles URIs with paths the same way. For standard configurations, keep instance URIs in `scheme://host:port` form and manage API paths in client requests.

## 9. Multiple DiscoveryClients and selection order

If an application has multiple discovery implementations on the classpath, such as Eureka and Simple Discovery, do not assume Simple is always the client supplying results. Spring Cloud has a composite discovery mechanism and client ordering; results depend on configuration and version.

Spring Cloud Commons documentation describes `SimpleDiscoveryClient` as the choice when no service-registry-backed `DiscoveryClient` is on the classpath. When combining or prioritizing multiple discovery clients, check the `order` and composite behavior for your version.

With static discovery, keep configuration simple and avoid declaring the same service ID across multiple sources unless intentional. If one source returns duplicate instances relative to another, the consumer may see repeated entries or unexpected endpoint selection depending on composite behavior.

## 10. Common errors when mapping URIs

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `getInstances()` returns an empty list | Wrong service ID or `instances` configuration was not loaded. | Match the key in YAML/properties against the service ID the consumer queries. |
| Host in `ServiceInstance` is wrong | Wrong hostname/IP in URI or DNS does not fit the consumer's network. | Check the URI and DNS resolution from the consumer's environment. |
| Port returns `-1` or is wrong | URI is missing a port or port does not match the actual endpoint. | Declare the port explicitly and verify container/gateway port mappings. |
| HTTPS request calls HTTP instead | Configured URI uses `http` or secure flag is incorrect. | Use `https://` and verify the instance's `isSecure()`. |
| TLS handshake fails | Certificate SAN does not match hostname/IP or truststore lacks CA. | Issue a certificate matching the endpoint and configure the truststore; do not disable hostname verification. |
| `payment-service` cannot be resolved | HTTP client is not annotated with `@LoadBalanced` or LoadBalancer dependency is missing. | Check the client bean and Spring Cloud LoadBalancer dependency. |
| Dead endpoint still gets selected | Static list does not auto-update health. | Update configuration or add a health-aware supplier/monitoring. |
| URI changed but application still calls old address | Configuration not reloaded or instance cache still holds stale data. | Check profiles/property sources, restart/refresh lifecycle, and client cache. |
| Instance appears twice | Multiple DiscoveryClients return the same service ID or duplicate endpoints in config. | Inspect composite discovery, client order, and instance lists per source. |
| URI contains a path but request loses the path | LoadBalancer/client only uses host, port, and scheme when rebuilding the URI. | Put the API path in the request or implement a tested base-path mechanism. |

## 11. Configuration verification checklist

After declaring static discovery, you can verify using these steps:

1. Confirm `spring.cloud.discovery.client.simple.instances` is loaded from the right profile and property source.
2. Call `DiscoveryClient.getServices()` to inspect known service IDs.
3. Call `getInstances(serviceId)` to retrieve the instance list.
4. Print `getInstanceId()`, `getServiceId()`, `getHost()`, `getPort()`, `isSecure()`, `getUri()`, and `getMetadata()`.
5. Check DNS, routes, and ports from the consumer's environment.
6. If using HTTPS, verify the TLS certificate and trust chain.
7. Send a request through a `@LoadBalanced` client to verify the service ID is resolved to a physical address.
8. Test nonexistent service IDs and stopped endpoints to confirm the application handles errors properly.

To quickly check endpoints from the command line, you can run:

```bash
curl -v http://payment-01.internal:8081/actuator/health
curl -v https://payment-02.internal:8443/actuator/health
```

The health endpoints above are examples only. They must exist and be accessible in your actual environment. Do not expose Actuator or internal endpoints to the public Internet just to test discovery.

## 12. Production design principles

- Use stable service IDs as keys in the `instances` map.
- Every URI must be an endpoint reachable from the consumer; do not use loopback or wildcard addresses.
- Specify scheme and port explicitly, especially with HTTPS or custom ports.
- Keep a consistent protocol convention across instances of the same service, unless mixed-protocol support is required.
- Use distinct `instance-id` values when tracing individual endpoints is needed.
- Use metadata for structured attributes; do not confuse metadata with health status.
- Understand that static lists do not self-register, heartbeat, or evict dead instances.
- Update configuration through version control/CI/CD workflows and verify endpoints before rollout.
- If endpoints must change frequently, consider a dynamic registry like Eureka, Consul, or ZooKeeper instead of a static list.
- Verify the active discovery implementation when multiple providers exist on the classpath.
- Protect URIs, metadata, and internal endpoints; never embed credentials in URIs.

## Conclusion

In static discovery, the key of `spring.cloud.discovery.client.simple.instances` is the service ID, each element in the list is an instance, and the `uri` field describes the instance's endpoint. The `http`/`https` scheme determines the protocol and secure flag; host and port identify the connection address. The `instance-id` and `metadata` properties add identification and descriptive capabilities for instances.

`SimpleDiscoveryClient` maps the configuration list into `ServiceInstance` objects, enabling consumers to use `DiscoveryClient` and Spring Cloud LoadBalancer without querying a registry server. Because the list is static, endpoint updates and health checking must be managed separately. Verify service IDs, URIs, `isSecure()`, metadata, and real connectivity before moving configuration into production.

## References

- [Spring Cloud Commons — Common Abstractions and SimpleDiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons — ServiceInstance API](https://docs.spring.io/spring-cloud-commons/docs/current/api/org/springframework/cloud/client/ServiceInstance.html)
- [Spring Cloud Commons — SimpleDiscoveryClient property mapping tests](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/test/java/org/springframework/cloud/client/discovery/simple/SimpleDiscoveryClientPropertiesMappingTests.java)
