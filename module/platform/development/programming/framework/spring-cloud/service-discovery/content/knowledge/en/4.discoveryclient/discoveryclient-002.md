# Retrieving ServiceInstances with getInstances(serviceId)

In a microservice architecture, a consumer typically only knows the logical name of the service it needs to call, for example `order-service`. The number of instances, hosts, and ports can change when the system scales, deploys a new version, or replaces a failed container. Therefore, the consumer needs a mechanism to look up the addresses currently published in the Service Registry.

Spring Cloud provides the `DiscoveryClient` interface to perform service discovery operations. The `getInstances(serviceId)` method takes a service name and returns the corresponding list of `ServiceInstance` objects. This lesson explains the method's contract, how to read information for each instance, how to handle empty results, and how to combine discovery with load balancing in a Spring Cloud application.

## 1. DiscoveryClient in the Service Discovery flow

`DiscoveryClient` belongs to the `org.springframework.cloud.client.discovery` package. It is a consumer-side abstraction that allows an application to look up instances without directly calling the specific API of Eureka, Consul, or another registry.

A typical flow consists of the following steps:

1. The provider starts up and registers its instance with the registry.
2. The registry stores the instance's service ID, host, port, and metadata.
3. The consumer calls `DiscoveryClient.getInstances(serviceId)` to retrieve the published instances for that service ID.
4. The consumer or Spring Cloud LoadBalancer selects an appropriate instance to send the request to.

```mermaid
flowchart LR
    P[Provider: order-service] -->|Register instance| R[(Service Registry)]
    C[Consumer: payment-service] -->|getInstances("order-service")| D[DiscoveryClient]
    D -->|Look up| R
    R -->|List of ServiceInstance| D
    D --> C
    C -->|Select instance / call service| O[order-service instance]
```

`DiscoveryClient` is responsible for lookup. It is not the registry, does not register providers, and does not perform load balancing for individual requests on its own. Instance selection can be decided by the application itself or delegated to Spring Cloud LoadBalancer.

## 2. The getInstances(serviceId) contract

In Spring Cloud Commons, the core of `DiscoveryClient` looks like this:

```java
package org.springframework.cloud.client.discovery;

import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.core.Ordered;

public interface DiscoveryClient extends Ordered {

    String description();

    List<ServiceInstance> getInstances(String serviceId);

    List<String> getServices();
}
```

The point to focus on is the signature:

```java
List<ServiceInstance> getInstances(String serviceId);
```

- `serviceId` is the logical name of the service to look up, for example `order-service`.
- The return value is a list of `ServiceInstance`; each element describes a discoverable instance.
- If there are no matching instances, the result is typically an empty list. The consumer must check for this case before accessing the first element.
- The common contract does not guarantee element order, instantaneous refresh timing, or that the endpoint is still healthy at the exact moment the consumer sends a request.

`getServices()` returns the service IDs visible to the implementation. This method is useful when diagnosing a wrong service name. `description()` provides an implementation description. Neither replaces calling `getInstances(serviceId)` when you need instance addresses.

### 2.1. serviceId is a logical name, not a network address

The consumer passes the service name, not a URL, IP, or port:

```java
List<ServiceInstance> instances =
        discoveryClient.getInstances("order-service");
```

The registry maps that logical name to one or more instances. For example, `order-service` might correspond to `10.0.1.21:8080`, `10.0.1.22:8080`, and `10.0.2.15:8080`.

The service ID must match the name published by the provider. Case normalization rules, aliases, or name mapping behavior can depend on the registry and implementation. Therefore, services should agree on a stable identifier, and consumers should use that exact name instead of guessing variations.

Do not pass a Java class name, Spring bean name, database name, or the hostname of an instance into `getInstances`, unless the system intentionally uses that exact string as the service ID. The service ID represents the logical service, whereas hostname and port are properties of each individual instance.

### 2.2. The list can contain multiple instances

Suppose the registry currently records three instances:

| Service ID | Host | Port | Metadata |
|---|---|---:|---|
| `order-service` | `10.0.1.21` | 8080 | `zone=zone-a` |
| `order-service` | `10.0.1.22` | 8080 | `zone=zone-a` |
| `order-service` | `10.0.2.15` | 8080 | `zone=zone-b` |

When calling `getInstances("order-service")`, the consumer can receive three `ServiceInstance` objects. This count can change after each lookup due to scale up, scale down, deployments, or health checks. Do not hardcode an instance list in code or assume a service always has exactly one address.

## 3. Reading information from ServiceInstance

`ServiceInstance` belongs to the `org.springframework.cloud.client` package. It is the abstraction describing an instance of a service. Commonly used information includes:

| Method | Meaning |
|---|---|
| `getServiceId()` | Service ID that the instance belongs to. |
| `getHost()` | Host or network address of the instance. |
| `getPort()` | Listening port of the instance. |
| `isSecure()` | Indicates whether the instance uses a secure connection. |
| `getUri()` | Access URI of the instance, constructed from address and protocol details. |
| `getMetadata()` | Key-value metadata provided by the provider or registry. |

For example, an instance might provide the following values:

```text
serviceId = order-service
host      = order-7.internal
port      = 8080
secure    = false
uri       = http://order-7.internal:8080
metadata  = {
  zone: "zone-b",
  version: "v2"
}
```

The consumer can use `getUri()` to obtain the base address or use individual properties to apply routing rules. Avoid manually concatenating host and port strings when `getUri()` is available, because URI construction also involves protocol details and may have implementation-specific rules.

Metadata can help the consumer filter instances by zone, version, or deployment group. However, the presence of metadata on the object does not automatically activate routing policies. The application or a filter must explicitly read and apply those values.

## 4. Calling getInstances in a Spring Boot application

An application can inject `DiscoveryClient` via constructor injection. The following example illustrates a component that looks up the addresses of `order-service`:

```java
package com.example.payment.discovery;

import java.net.URI;
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class OrderServiceLocator {

    private static final String ORDER_SERVICE_ID = "order-service";

    private final DiscoveryClient discoveryClient;

    public OrderServiceLocator(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<URI> findOrderServiceUris() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances(ORDER_SERVICE_ID);

        return instances.stream()
                .map(ServiceInstance::getUri)
                .collect(Collectors.toList());
    }
}
```

This example only performs the lookup and converts the instance list into a list of URIs. It does not send an HTTP request yet and does not select a single instance to serve a request. Separating these two steps keeps the discovery responsibility and the service invocation responsibility clear in the code.

For `DiscoveryClient` to work, the application needs the appropriate registry integration dependency and configuration. Merely declaring the interface or having injection succeed does not mean the provider has registered properly or that the registry currently holds data. You must verify the actual implementation created by Spring and its connection to the registry.

### 4.1. Iterating through and inspecting the instance list

During system verification, you can log the necessary properties:

```java
List<ServiceInstance> instances =
        discoveryClient.getInstances("order-service");

if (instances.isEmpty()) {
    log.warn("No instances found for serviceId={}", "order-service");
} else {
    for (ServiceInstance instance : instances) {
        log.info("serviceId={}, host={}, port={}, secure={}, uri={}",
                instance.getServiceId(),
                instance.getHost(),
                instance.getPort(),
                instance.isSecure(),
                instance.getUri());
    }
}
```

In a production environment, logs should avoid recording sensitive metadata or data that could expose unnecessary internal details. Prefer metrics for instance counts, lookup errors, and processing durations; only log specific addresses when operational policy allows.

## 5. Handling empty lists and lookup failures

A consumer needs to distinguish at least three situations:

1. **Lookup succeeds and instances are present:** proceed to instance selection or pass the list to the LoadBalancer.
2. **Lookup succeeds but the list is empty:** no instances are currently returned for that service ID.
3. **Lookup fails:** the implementation encounters an error when accessing the registry, reading data, or processing the request. Depending on the implementation, errors may be represented as a runtime exception or a specific error mechanism.

An empty list does not necessarily prove the registry is broken. Possible causes include an unregistered provider, a wrong service ID, instances excluded by health checks, an unsynchronized registry, or the application using a different namespace/partition.

Example of handling an empty result in the business layer:

```java
public List<ServiceInstance> requireOrderInstances() {
    List<ServiceInstance> instances =
            discoveryClient.getInstances("order-service");

    if (instances.isEmpty()) {
        throw new IllegalStateException(
                "No available instances for order-service");
    }

    return instances;
}
```

This is an illustration to make the condition explicit. In a real web application, an unavailable dependency should be translated into an appropriate response, typically `503 Service Unavailable`, or handled by a retry/circuit breaker mechanism at the service call layer according to system policy. Do not return `404 Not Found` just because an internal service has no instances; `404` generally indicates that the resource requested by the client does not exist.

Do not automatically turn every exception into an empty list. Doing so removes the application's ability to distinguish "no instances available" from "cannot reach the registry," skewing monitoring and diagnostics. Record lookup errors separately and apply timeouts, bounded retries, and backoff appropriate to the implementation.

## 6. Do not confuse discovery with load balancing

`getInstances(serviceId)` returns a list of instances. It does not promise to pick an instance via round-robin, least connections, or any other algorithm. List order is not a load-balancing contract; taking `instances.get(0)` is not a reliable load-balancing strategy.

If selecting instances manually, the application becomes responsible for request distribution, handling dead instances, refreshing the list, retries, timeouts, and zone rules. This is a substantial amount of operational logic and easily creates inconsistent behavior across consumers.

For HTTP calls by service ID, consider Spring Cloud LoadBalancer. Example using a `RestTemplate` annotated with `@LoadBalanced`:

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
    public RestTemplate orderRestTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
```

Then, the consumer can call using the service ID as the hostname:

```java
String response = orderRestTemplate.getForObject(
        "http://order-service/api/orders/42",
        String.class);
```

With the corresponding LoadBalancer configuration, Spring Cloud resolves the service ID to an instance selected from the discovery list before sending the request. Specific dependencies and configuration depend on the Spring Boot/Spring Cloud version in use. If the application uses `WebClient` or `RestClient`, use the corresponding LoadBalancer integration for that version.

`DiscoveryClient` remains useful when the application needs to inspect instance lists, check metadata, build administrative tools, or implement custom discovery rules. For normal requests, let the dedicated load-balancing component choose the instance.

## 7. Relationship with Eureka, Consul, and other implementations

`DiscoveryClient` is an abstraction from Spring Cloud Commons. A specific starter or integration provides the implementation to talk to the registry. A consumer can keep calling `getInstances(serviceId)` while the underlying implementation changes.

| Registry / implementation | Role when calling getInstances |
|---|---|
| Eureka | Looks up instances recorded by the Eureka client/registry for the corresponding service ID. |
| Consul | Looks up service instances from catalog data and health status per integration configuration. |
| Simple Discovery Client | Provides an instance list from static configuration, useful for simple environments or testing. |

The abstraction does not make every registry behave identically. The following points must be checked per implementation:

- How service IDs are normalized or mapped.
- Whether the registry returns all instances or only instances meeting specific health conditions.
- Whether the client caches the instance list and what the refresh interval is.
- How metadata is mapped.
- How registry connection errors, timeouts, and retries are surfaced.
- Whether multiple `DiscoveryClient` beans coexist or a composite layer aggregates results.

Therefore, when migrating from Eureka to Consul, code calling the abstraction may change very little, yet you still need to test the behavior, configuration, and health policies of the new registry.

## 8. Caching, data freshness, and consistency

Do not assume every call to `getInstances` sends a direct network request to the registry server. An implementation may hold a local copy, receive periodic updates, or use client-side caching. Spring Cloud LoadBalancer may also cache the instance list depending on configuration and version.

As a consequence, the returned list can lag behind actual state for a period of time. For example, an instance that has just stopped may still appear in the cache; or a newly registered instance may not yet appear on the consumer. This is why discovery does not replace health checks and request timeouts.

When investigating stale data, identify all layers that may hold a cache: registry server, registry client, DiscoveryClient adapter, LoadBalancer supplier, and application-created caches. Avoid adding your own cache without understanding existing ones; multiple caching layers can increase delay when updating or removing instances.

The consumer still needs to handle cases where connecting to an instance fails because it just became unavailable. Use reasonable timeouts, bounded retries for retry-safe operations, circuit breakers where appropriate, and track connection errors per service ID.

## 9. Metadata and contextual instance selection

Each `ServiceInstance` can carry metadata published by the provider. For example, a consumer might want to prefer instances in the same deployment zone:

```java
List<ServiceInstance> instances =
        discoveryClient.getInstances("order-service");

List<ServiceInstance> sameZone = instances.stream()
        .filter(instance -> "zone-a".equals(
                instance.getMetadata().get("zone")))
        .collect(Collectors.toList());
```

This snippet illustrates data filtering; it is not a complete load-balancing algorithm. If `sameZone` is empty, the application needs to decide whether to fall back to another zone or report that no instances are available. This rule should be configured consistently and tested to avoid silently dropping all instances.

Metadata can be missing, malformed, or inconsistent across provider versions. Always handle null/missing values and standardize key names. Do not put secrets, tokens, or credentials in metadata; this data is typically stored in the registry and can be read by many components.

## 10. Security when using discovery results

Discovery results directly affect where the consumer sends requests. Therefore:

1. Only look up internal service IDs that the component is allowed to call; do not use arbitrary strings from external requests as a service ID.
2. Protect connections between providers, consumers, and the registry with authentication, authorization, and TLS according to environment requirements.
3. Respect `isSecure()` and the URI provided by `ServiceInstance`; do not downgrade HTTPS connections to HTTP.
4. Do not treat metadata as unconditionally trusted data. Validate values used in routing decisions.
5. Apply network policies so consumers can only reach the required services and ports.
6. Do not expose the full list of internal hosts, ports, and metadata to end users or public APIs without a clear need.

Service Discovery provides instance addresses and context. It does not replace service-to-service authentication, business authorization, or access control checks at the target endpoint.

## 11. Common issues when calling getInstances

### The list is always empty

Check whether the service ID matches the name registered by the provider, whether the provider has registration enabled, whether the registry holds the record, and whether the consumer is connecting to the right cluster, namespace, or datacenter. Use `getServices()` to see the service names currently visible to the client, and check the registry dashboard and logs.

### The list has instances but requests fail

Discovery only provides instance information according to the registry/client. The host might not resolve from the consumer's network, the port might be blocked by a firewall, or the application might not be ready yet. Check `getUri()`, DNS, routing, network policies, TLS, and health checks. Add timeouts and error handling on the HTTP client.

### Only one instance appears even though the provider is scaled to multiple replicas

Check whether each provider registers with a distinct instance ID, whether the registry receives all records, and whether the implementation filters by status or zone. Also check caching and synchronization timing on the consumer.

### Old instances still appear after deployment

The provider may not have deregistered according to its lifecycle, the process may have terminated abruptly, or caches may not have refreshed yet. Check graceful shutdown, heartbeat/TTL, health checks, and cache layers. Do not delete records manually without understanding the registry's ownership and self-healing mechanisms.

### Consumer uses the wrong service ID

Cross-check the name in the provider configuration, the name in the registry, and the constant the consumer passes to `getInstances`. Do not infer the service ID from a package name or class name. Centralize service IDs in configuration or shared constants appropriate to the project architecture.

## 12. Checklist before taking discovery to production

| Item | Verification question |
|---|---|
| Dependency | Does the application have the right starter and DiscoveryClient implementation? |
| Service ID | Do provider and consumer use the same service ID? |
| Registration | Does the provider appear in the registry with a valid host/port? |
| Empty results | Does the consumer handle empty lists and return a dependency-unavailable response? |
| Multiple instances | Can the system handle a changing list when scaling? |
| Load balancing | Does instance selection use a clear strategy and is it tested? |
| Health | Are readiness, health checks, heartbeats, and deregistration coordinated? |
| Cache | Are the refresh intervals of the registry client and LoadBalancer understood? |
| Resilience | Are timeouts, bounded retries, and appropriate circuit breakers configured? |
| Security | Are service IDs, metadata, registry connections, and endpoints protected? |
| Observability | Are there metrics/logs to distinguish no-instance cases from registry access errors? |

## Conclusion

`DiscoveryClient.getInstances(serviceId)` is the operation for looking up instances by service name in Spring Cloud. The method accepts a service ID and returns `List<ServiceInstance>`; each element provides address details along with metadata for an instance. Consumers must handle empty lists, understand that data can be stale, and not assume list order is a load-balancing policy.

In microservice applications, use `DiscoveryClient` when you need to look up or inspect instances. For ordinary request calls, combine it with Spring Cloud LoadBalancer to select an instance while maintaining timeouts, health checks, security, and observability. This organization allows consumers to find services by logical name while the system can still change the number and addresses of instances throughout the deployment lifecycle.
