# Reading serviceId, instanceId, host, port, URI, and metadata

In Spring Cloud Service Discovery, a consumer queries a service ID to receive a list of published instances. Each instance contains information that helps the consumer identify the service, distinguish individual running copies, determine the connection address, and understand additional deployment context. The fields most commonly read are service ID, instance ID, host, port, URI, and metadata.

This data is the view that the discovery client receives from the registry at query time. It can lag behind actual process or network state due to heartbeats, health checks, caching, and synchronization intervals. Therefore, you need to interpret each field properly and handle cases where data is missing or stale.

## 1. serviceId and instanceId are two different levels of identification

### serviceId: logical name of the service

`serviceId` is the name used to group instances that together provide a logical service. For example:

- `inventory-service`: inventory management service.
- `payment-service`: payment processing service.
- `order-service`: order management service.

A service can run multiple replicas. Compatible replicas typically register under the same `serviceId` so consumers only need to look up one stable name.

In a Spring Boot application, `spring.application.name` is usually the default source for generating the service name when the discovery client registers the application. However, a provider may allow overriding the service name with a dedicated configuration property. The name the consumer queries must match the name actually published in the registry.

### instanceId: identifier of a specific running copy

`instanceId` distinguishes one instance from other instances belonging to the same service ID. For example:

| serviceId | instanceId | host | port |
|---|---|---|---:|
| `inventory-service` | `inventory-pod-a81f` | `10.20.1.11` | 8080 |
| `inventory-service` | `inventory-pod-b92c` | `10.20.1.12` | 8080 |
| `inventory-service` | `inventory-pod-c73d` | `10.20.1.13` | 8080 |

Three instances serve `inventory-service`, each with its own ID and address. The registry uses the instance identifier to update heartbeats, status, or deregister the exact running copy.

How an instance ID is generated depends on the provider and environment. It may be based on hostname, port, application name, IP, pod UID, or a custom configured value. An instance ID should be sufficiently unique within the registry scope and stable throughout that registration's lifecycle. Do not assume the instance ID is always the hostname or always has the same format across Eureka and Consul.

**Important distinction:** service ID answers "which logical service is this?", while instance ID answers "which specific running copy is this?". Do not use an instance ID as the general lookup name when you want to call any available replica.

## 2. How DiscoveryClient reads the instance list

Spring Cloud Commons provides the `DiscoveryClient` abstraction for consumers to query the registry. Two commonly used operations are:

- `getServices()`: retrieves the list of service IDs currently visible to the discovery client.
- `getInstances(serviceId)`: retrieves the list of instances published under that service ID.

For example, an application can inspect the discovered services:

```java
List<String> serviceIds = discoveryClient.getServices();

for (String serviceId : serviceIds) {
    List<ServiceInstance> instances =
        discoveryClient.getInstances(serviceId);

    log.info("serviceId={}, instanceCount={}",
        serviceId, instances.size());
}
```

`getServices()` is useful for observability or administrative tools. In business flows, an application usually knows the service ID it needs to call in advance and queries `getInstances(serviceId)` directly.

The list may be empty if the provider has not registered yet, the consumer queried the wrong name, instances are not healthy yet, data has not synchronized, or the registry is experiencing an issue. Do not treat an empty list as sole proof that the provider application has shut down. Check the registry, discovery client logs, health checks, and network connectivity.

## 3. ServiceInstance and connection fields

`DiscoveryClient.getInstances()` returns `ServiceInstance` objects. This is the abstraction representing an instance, relatively independent of Eureka, Consul, or a specific discovery provider.

| Property | Meaning | How to use |
|---|---|---|
| `getServiceId()` | Logical name of the service | Check which service the instance belongs to |
| Instance ID | Identifier of a specific registration | Distinguish replicas and correlate logs |
| `getHost()` | Host/IP advertised by the provider | Diagnose instance address |
| `getPort()` | Published service port | Connect to the application's listener |
| `isSecure()` | Instance uses a secure connection per registration | Determine HTTP/HTTPS scheme |
| `getUri()` | Base URI of the instance | Use as the target address |
| `getMetadata()` | Additional key/value attributes | Filter or route by zone, version, tag |

Common methods of `ServiceInstance` include `getServiceId()`, `getHost()`, `getPort()`, `isSecure()`, `getUri()`, and `getMetadata()`. The ability to read the native instance ID depends on the Spring Cloud Commons version and provider implementation. If the API in use provides an instance ID accessor, read it through that accessor; otherwise, use a provider-specific API or a metadata convention explicitly published by the system. Do not assume every `ServiceInstance` has the same way to retrieve the native instance ID.

### Host and port

`host` is the address the provider advertises to consumers. It does not necessarily equal the internal bind address the process uses to open a socket. For example, an application may bind to `0.0.0.0` while advertising the container IP address or a hostname reachable by consumers.

`port` is the instance's service port, not the registry server port. If the application runs behind NAT, a container network, a reverse proxy, or port mapping, it must advertise the port visible to consumers.

```text
Process bind:       0.0.0.0:8080
Advertised address: 10.20.1.11:8080
Consumer network:   10.20.1.11:8080
```

If the registry publishes `localhost` for an instance on another machine, the consumer will connect to the consumer machine itself instead of the provider machine. This is a common advertised-address configuration mistake.

### URI and scheme

`getUri()` returns the connection URI built from the instance information, typically in the form:

```text
http://10.20.1.11:8080
https://inventory.internal:8443
```

The URI is the base address of the instance. It does not normally include business API paths such as `/api/items/42`. The application must append the path matching the provider's HTTP contract.

Use `getUri()` when you need a complete connection address instead of manually concatenating host and port strings. This respects the secure scheme published by the implementation. However, a syntactically valid URI does not guarantee the address is reachable; DNS, routing, firewalls, TLS, and network policies must still permit the connection.

`isSecure()` indicates whether the registration marks the instance as secure. `getUri()` usually reflects this via the `https` or `http` scheme. Some versions also provide `getScheme()` to read the scheme directly.

Do not conclude that TLS is guaranteed to work just because `isSecure()` returns `true`. The consumer still needs an appropriate trust store, valid certificates, hostname verification, and TLS configuration. The secure flag in registration is routing metadata; it does not replace connection verification.

## 4. Reading metadata

`metadata` is a set of key/value pairs attached to the registration by the provider or deployment system. In `ServiceInstance`, metadata is typically represented as `Map<String, String>`.

For example:

```yaml
metadata:
  zone: ap-southeast-1a
  version: v2
  region: ap-southeast-1
  canary: "false"
  protocol: http
```

A consumer can read metadata to prefer instances in the same zone, pick a compatible version, split canary traffic, select instances with matching capabilities, or analyze instance distribution across zones.

```java
Map<String, String> metadata = instance.getMetadata();

String zone = metadata.get("zone");
String version = metadata.get("version");
String canary = metadata.get("canary");
```

Metadata does not have a unified schema across all providers. Eureka and Consul both support metadata, but configuration, size limits, data types, and update behavior depend on the implementation. Standardize key names, representations, and semantics in your own system.

Some guidelines:

- Metadata should hold descriptive or routing information, not passwords, tokens, or private keys.
- Values are typically strings; if representing booleans or numbers, the consumer must parse them and handle missing values.
- Do not assume every instance has the same keys.
- Avoid using metadata as a substitute for the service ID if that information is actually service identity.
- When changing metadata, understand how the provider updates its registration and how long it takes for consumers to receive the new data.

Metadata is input data for routing decisions. If a consumer trusts metadata without controlling who writes it, an instance could declare an incorrect zone or version and skew target selection policies.

## 5. Example of reading full information with DiscoveryClient

The following example queries instances of `inventory-service` and logs connection details. The code handles empty lists and missing optional metadata keys.

```java
import java.net.URI;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class InventoryInstanceInspector {

    private static final Logger log =
        LoggerFactory.getLogger(InventoryInstanceInspector.class);

    private final DiscoveryClient discoveryClient;

    public InventoryInstanceInspector(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public void inspect() {
        String requestedServiceId = "inventory-service";

        List<ServiceInstance> instances =
            discoveryClient.getInstances(requestedServiceId);

        if (instances.isEmpty()) {
            log.warn("No instances found for serviceId={}",
                requestedServiceId);
            return;
        }

        for (ServiceInstance instance : instances) {
            String serviceId = instance.getServiceId();
            String host = instance.getHost();
            int port = instance.getPort();
            boolean secure = instance.isSecure();
            URI uri = instance.getUri();

            Map<String, String> metadata = instance.getMetadata();
            String zone = metadata.get("zone");
            String version = metadata.get("version");

            log.info(
                "serviceId={}, host={}, port={}, secure={}, uri={}, zone={}, version={}, metadata={}",
                serviceId, host, port, secure, uri, zone, version, metadata
            );
        }
    }
}
```

This code reads the properties provided by the `ServiceInstance` abstraction. It does not assume the native instance ID is present in metadata. If the application needs to log the instance ID, obtain it from an accessor supported by the version/provider or add a metadata key following an agreed convention.

In production, avoid logging all metadata if providers might place sensitive data in it. Select approved observable keys and mask sensitive values before logging.

## 6. Reading the native instanceId properly

The native instance ID is generated and managed by the discovery provider. It may appear in the registry's dashboard or API, though it is not necessarily standardized the same way across providers.

- **Eureka:** the instance ID is stored in Eureka's instance info; the format is usually determined by the Eureka client and instance configuration.
- **Consul:** each service registration has its own ID provided by the agent/client or generated per configuration; service name and registration ID are two different concepts.
- **Other providers:** may use a UUID, hostname, pod UID, or custom identifier.

When you need the native ID, use the specific API/adapter of the deployed provider and check the exact dependency version. Avoid casting every `ServiceInstance` object to a Eureka or Consul class in shared business code, because doing so couples the application to a vendor.

If you need a portable identifier that consumers can read across any implementation, you can standardize an extra metadata key such as `instance-key` in registration. This value is managed by your system and must be written consistently across all providers. However, `instance-key` is application-defined metadata and does not necessarily match the native ID that the registry uses to deregister a registration.

Example of reading a standardized metadata key:

```java
Map<String, String> metadata = instance.getMetadata();
String instanceKey = metadata.get("instance-key");

if (instanceKey == null || instanceKey.isBlank()) {
    log.warn("Instance has no portable instance-key");
} else {
    log.info("portableInstanceKey={}", instanceKey);
}
```

The snippet above reads an application-defined ID and does not claim it is the native Eureka or Consul ID. When you need the native ID to call administrative APIs or deregister a registration, use the provider's proper adapter and API.

## 7. Cross-checking data between provider, registry, and consumer

An instance can have three views:

1. **Provider configuration:** the address and metadata the application intends to publish.
2. **Registry record:** the registration currently stored by the registry and its health/lease status.
3. **Consumer result:** the list of `ServiceInstance` objects returned by the discovery client, which may be affected by caches or refresh intervals.

The three views do not necessarily match immediately. For example, an application may have changed its port while the old registration has not been replaced yet; the registry may have updated while the client cache still holds the previous address; or the advertised host may not be reachable from the consumer's network.

When investigating, compare the same instance ID and service ID across all three places. Check the fields in order:

- Does the service ID match the name requested by the consumer?
- Is the instance ID unique and associated with the right service?
- Is the host an address the consumer can route to?
- Is the port the actual port the application is listening on and exposing?
- Does the URI have the right scheme and port?
- Do metadata keys/values follow conventions and reflect the right environment?
- Does the health status allow the instance to appear in discovery results?

## 8. Common issues

| Symptom | Possible cause | Recommended handling |
|---|---|---|
| `getInstances()` returns an empty list | Wrong service ID, not registered yet, failing health check, or unsynchronized registry | Check name in registry, client logs, and health status |
| Two instances share the same instance ID | Non-unique ID configuration or multiple replicas sharing a hardcoded value | Generate a distinct ID for each registration |
| Returned host is `localhost` | Client advertises loopback instead of an address reachable by consumers | Configure an appropriate advertised host/IP |
| Returned port cannot be connected to | Wrong published port, port mapping, or network policy | Cross-check listener, container port, and service port |
| URI uses the wrong scheme | Incorrect secure flag or HTTPS configuration | Check registration and TLS configuration |
| Metadata is missing a key | Provider does not publish the key or stale registration has not refreshed | Handle null/defaults and check provider configuration |
| Metadata differs between replicas | Replicas run with different configurations/profiles | Standardize configuration and inspect rollout |
| Consumer still calls an old address | Discovery cache or refresh has not updated yet | Check cache, refresh interval, and registry state |

Do not use optional metadata values without null checks. For example, if code parses `metadata.get("weight")` as a number when the key does not exist or contains an invalid string, the consumer can throw an error right inside the instance selection flow.

## 9. Safety when using instance information

Information from the registry is input to connection decisions. Apply the following principles:

- Only trust a protected registry and clients with valid registration permissions.
- Do not place secrets in metadata or logs.
- Authenticate connections to instances with TLS and an appropriate service authentication mechanism; do not treat the service ID as proof of identity.
- Do not let clients arbitrarily choose hosts/ports from unvalidated metadata, preventing registry data from becoming a path to unintended addresses.
- Bound timeouts and handle connection errors because an instance can disappear right after being discovered.
- When using metadata to select a version or zone, validate values and have a safe fallback if no matching instance exists.

The instance list is a snapshot at query time, not a guarantee that the instance will stay alive until the request completes. Consumers still need timeouts, bounded retries, circuit breakers, or appropriate recovery mechanisms.

## 10. Checklist for reading ServiceInstance

Before using discovery data in application code, check:

1. Are you querying the right service ID?
2. Do you handle an empty instance list?
3. Do you distinguish service ID from instance ID?
4. Do you treat host and port as the address advertised to consumers?
5. Do you use URI and scheme properly?
6. Do you handle missing or invalid metadata?
7. Do you avoid depending on provider-specific APIs in shared business code?
8. Do you cross-check the registry with consumer data when investigating errors?
9. Do you protect metadata and logs from sensitive data?
10. Do you have timeouts and handling for instances disappearing after lookup?

When you read service ID, instance ID, host, port, URI, and metadata properly, the consumer has enough context to know which service an instance represents, where to connect, and which routing rules can be applied. These fields are also essential data for diagnosing mismatches between provider, registry, and consumer in a Spring Cloud Service Discovery system.
