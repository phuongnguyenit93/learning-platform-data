# Using Metadata to Filter Instances by Zone or Version

A service in a microservice architecture may run multiple instances across different zones, regions, or application versions. Consumers typically look up a service using a shared service ID, yet not every request should be sent to every instance. For example, order-service may prioritize inventory-service in the same zone to reduce latency; a consumer relying on API contract v2 may only call instances serving version v2.

The service registry stores metadata alongside an instance's location information. Spring Cloud exposes that metadata in ServiceInstance, allowing consumers or Spring Cloud LoadBalancer to use it as selection criteria. However, metadata is only descriptive data. To filter by zone or version, the application must configure a supplier or routing policy that uses those fields.

This article explains how providers publish metadata, how to enable built-in zone preference in Spring Cloud LoadBalancer, how to build a version filter, and how to handle cases when no matching instance exists.

## 1. Metadata attached to each service instance

The service ID identifies the logical service, while metadata describes attributes of a specific instance. For example, three instances all register under service ID inventory-service but run in different zones and versions:

~~~text
inventory-service
  instance A: 10.0.1.11:8081  zone=zone-a  version=v1
  instance B: 10.0.1.12:8081  zone=zone-a  version=v2
  instance C: 10.0.2.21:8081  zone=zone-b  version=v2
~~~

Metadata usually consists of string key-value pairs. Some common keys include:

| Key | Example | Purpose |
|---|---|---|
| zone | zone-a | Deployment zone of the instance |
| region | ap-southeast-1 | Geographic or infrastructure region |
| version | v2 | Application or API version served by the instance |
| deployment-group | blue, green, canary | Rollout group |
| protocol | https | Additional connection attribute if needed by the system |

Key names and values must be standardized between providers and consumers. Prefer lowercase conventions, stable values, and avoid variants like Zone, availability-zone, and AZ for the same meaning unless mapping rules exist.

Metadata does not replace host, port, or URI. Nor does it establish a security boundary on its own. Consumers must still authenticate and authorize with providers according to the system's security mechanisms.

## 2. Providers publishing metadata in the registry

The provider declares metadata when registering an instance. Configuration syntax depends on the registry in use.

### With Eureka

Spring Cloud Netflix Eureka Client supports metadata-map in instance configuration:

~~~yaml
spring:
  application:
    name: inventory-service

eureka:
  instance:
    metadata-map:
      zone: zone-a
      region: ap-southeast-1
      version: v2
      deployment-group: green
~~~

These key-value pairs are published alongside the instance record. When a consumer receives a ServiceInstance, metadata can be read via getMetadata().

### With Consul

Spring Cloud Consul Discovery supports metadata and tags for service registration:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      discovery:
        service-name: inventory-service
        metadata:
          zone: zone-a
          region: ap-southeast-1
          version: v2
          deployment-group: green
        tags:
          - version-v2
          - deployment-green
~~~

Metadata is suited for consumers to read as instance attributes. Tags are useful for queries or Consul tools that filter by tag. The two mechanisms have different representations; choose the right data type and verify the behavior of the Spring Cloud Consul version in use.

### Inspecting metadata on the consumer

A consumer can inspect metadata on discovered instances:

~~~java
List<ServiceInstance> instances =
    discoveryClient.getInstances("inventory-service");

for (ServiceInstance instance : instances) {
    String zone = instance.getMetadata().get("zone");
    String version = instance.getMetadata().get("version");

    log.info(
        "Instance {}:{} zone={} version={}",
        instance.getHost(),
        instance.getPort(),
        zone,
        version
    );
}
~~~

DiscoveryClient returns the instance list currently known to the implementation. If metadata is missing, check whether the provider registered the right configuration, whether the registry stored those fields, and whether the consumer is reading the right registry/service ID.

## 3. Filtering by zone: prioritizing instances near the consumer

In multi-zone deployments, calling instances in the same zone can reduce latency and cross-zone data transfer costs. Spring Cloud LoadBalancer provides ZonePreferenceServiceInstanceListSupplier to prioritize instances whose zone metadata matches the consumer's zone.

Example provider declaration:

~~~yaml
eureka:
  instance:
    metadata-map:
      zone: zone-a
~~~

Consumer declares its own zone:

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
~~~

Then configure a supplier using zone preference for LoadBalancer:

~~~java
@Bean
ServiceInstanceListSupplier serviceInstanceListSupplier(
        ConfigurableApplicationContext context) {
    return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withZonePreference()
        .build(context);
}
~~~

With this configuration, the supplier prioritizes instances whose zone metadata matches the zone configured for the consumer. Zone preference behaves as a **preference**, not necessarily a hard filter: if no same-zone instance is found, the supplier can return instances from other zones so the request still has a chance to be served.

This usually fits locality-based routing well. If a business requirement strictly forbids cross-zone calls, a dedicated hard filter is needed and you must accept the case where no instances are available.

### Zone preference differs from region filtering

Zones and regions are not always at the same level. A region can contain multiple zones. If only zone is configured, the consumer usually prioritizes a specific zone; if you want to restrict within a region, you need region metadata and a corresponding filtering policy.

~~~text
region ap-southeast-1
  zone-a
    inventory instance A
  zone-b
    inventory instance B

region ap-southeast-2
  zone-c
    inventory instance C
~~~

If the consumer is in ap-southeast-1, matching zone alone without checking region may fail to express the intended policy in a system where zone names are not unique across regions. When needed, use a region/zone pair or a globally unique zone identifier per infrastructure conventions.

## 4. Filtering by application or API version

Zone is typically a preference criterion to optimize locality. Version can be a mandatory compatibility criterion. For example, a consumer using API v2 should not send requests to an instance supporting only API v1 if the two contracts are incompatible.

An exact version filtering policy might look like:

~~~text
Consumer requires version=v2
  Instance A version=v1      -> exclude
  Instance B version=v2      -> keep
  Instance C missing version -> exclude
~~~

If no instance carries a matching version, the resulting list should be empty so LoadBalancer reports that no instance is available. Do not silently fall back to returning all versions when version is a strict compatibility requirement.

### Creating a metadata-filtering supplier

Spring Cloud LoadBalancer allows customizing ServiceInstanceListSupplier. The following example wraps a discovery-backed supplier and keeps only instances whose metadata matches the required version.

~~~java
public final class MetadataFilterServiceInstanceListSupplier
        implements ServiceInstanceListSupplier {

    private final ServiceInstanceListSupplier delegate;
    private final String metadataKey;
    private final String requiredValue;

    public MetadataFilterServiceInstanceListSupplier(
            ServiceInstanceListSupplier delegate,
            String metadataKey,
            String requiredValue) {
        this.delegate = delegate;
        this.metadataKey = metadataKey;
        this.requiredValue = requiredValue;
    }

    @Override
    public String getServiceId() {
        return delegate.getServiceId();
    }

    @Override
    public Flux<List<ServiceInstance>> get() {
        return delegate.get().map(this::filter);
    }

    @Override
    public Flux<List<ServiceInstance>> get(Request request) {
        return delegate.get(request).map(this::filter);
    }

    private List<ServiceInstance> filter(
            List<ServiceInstance> instances) {
        return instances.stream()
            .filter(instance -> requiredValue.equals(
                instance.getMetadata().get(metadataKey)))
            .collect(Collectors.toList());
    }
}
~~~

A supplier configured for inventory-service can wrap the discovery supplier as follows:

~~~java
@Configuration(proxyBeanMethods = false)
public class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier serviceInstanceListSupplier(
            ConfigurableApplicationContext context,
            Environment environment) {

        String requiredVersion = environment.getRequiredProperty(
            "app.discovery.inventory.required-version");

        ServiceInstanceListSupplier delegate =
            ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .build(context);

        return new MetadataFilterServiceInstanceListSupplier(
            delegate, "version", requiredVersion);
    }
}
~~~

Attach the configuration to the service-specific LoadBalancer:

~~~java
@SpringBootApplication
@LoadBalancerClient(
    name = "inventory-service",
    configuration = InventoryLoadBalancerConfiguration.class
)
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

The consumer declares the desired version:

~~~yaml
app:
  discovery:
    inventory:
      required-version: v2
~~~

Key imports for the supplier include ServiceInstance, Request, ServiceInstanceListSupplier, Flux, List, and Collectors. LoadBalancer configuration should reside outside the application's default component scan scope, or be placed in a package not scanned as global configuration. If a supplier bean meant solely for inventory-service is scanned as an application-wide default configuration, it can affect other services.

This is an exact-match filtering example for one service ID. Specific Spring Cloud LoadBalancer APIs may vary across release trains; use the same Spring Cloud BOM version as your application and verify interface signatures when implementing. If the application needs different versions per request or caller group, pass the requirement in the request context/hint and build a request-aware supplier instead of pinning one version in service-wide configuration.

## 5. Combining zone and version

A common policy is filtering by version first, then prioritizing zone among the remaining instances. For example, a consumer requiring version=v2 located in zone-a:

~~~text
Discovery list
  A: zone-a, version=v1
  B: zone-a, version=v2
  C: zone-b, version=v2
  D: zone-b, version=v1

After filtering version=v2
  B: zone-a, version=v2
  C: zone-b, version=v2

After zone preference zone-a
  B is prioritized
~~~

Supplier order affects the outcome because each supplier consumes the output of the preceding one. When treating version as mandatory and zone as a preference, ensure the version filter is not widened back by a downstream fallback. If no v2 exists in zone-a but v2 exists in zone-b, zone preference can fall back to zone-b; if no v2 exists in any zone, the result remains empty.

When mixing built-in zone preference with a custom version filter, inspect the actual supplier chain created in your exact Spring Cloud version. You can configure a custom supplier combining both steps if you need exact control over ordering and fallback.

## 6. Filtering by other metadata

The same technique can be applied to deployment-group, region, protocol, or other operational labels.

Example filtering specifically for the green group:

~~~yaml
eureka:
  instance:
    metadata-map:
      deployment-group: green
      version: v2
      zone: zone-a
~~~

A consumer can use a supplier filtering deployment-group=green in a testing or rollout flow. For canary releases, merely filtering by a canary label is insufficient for traffic percentage splitting; you also need controlled traffic distribution policies, outcome observability, and rollback capability.

If metadata represents a list of values or feature sets, define clear formatting and comparison rules. Avoid stuffing multiple meanings into a hard-to-parse string like zone-a-v2-green.

## 7. Handling when no matching instance exists

Metadata filtering can produce an empty list. This is a valid outcome when no instance meets the criteria. Consumers must handle this case as a no-available-target condition.

| Situation | Behavior to consider |
|---|---|
| No same-zone instance | If zone is only a preference, fall back to another zone |
| No instance with required version | Return an error indicating no compatible instance; do not automatically call another version |
| Missing metadata | Exclude the instance if that field is mandatory; alert on provider configuration |
| Typo or convention mismatch in metadata | Does not match filter; fix convention and registration |
| Registry has not updated new metadata | Wait for refresh or renew discovery cache per deployment mechanism |
| Cache holds stale metadata | Check TTL and cache layers of registry client/LoadBalancer |

Do not apply the same fallback across all metadata types. Zone may be a preference because the goal is reducing latency; version may be a mandatory contract condition. Fallback policies must reflect the semantics of each field.

## 8. Metadata does not replace security

Metadata registered by a provider is data for discovery and routing. It is not proof of identity or authorization. An instance can declare version=v2 or environment=production, yet consumers should not rely on that label to grant access to sensitive data or functionality.

Continue using TLS, service-to-service authentication, authorization, and network policies. If metadata is used to select endpoints with differing security requirements, verify certificates and service identity at the connection layer.

## 9. Testing filtering policies

Before deployment, test these scenarios:

1. All instances have complete metadata and only one version matches.
2. Multiple instances share the same version but are in different zones.
3. No same-zone instance exists, while a matching version exists in another zone.
4. No matching version exists in any zone.
5. An instance lacks metadata or uses a non-conforming value.
6. Provider updates metadata and consumer receives the new data after refresh.
7. Cache TTL has not expired while metadata has changed.
8. Other service IDs are unaffected by the LoadBalancer configuration dedicated to inventory-service.

Verify both the list returned by the supplier and which instance actually receives requests. Logs can record the service ID, requested version/zone, and instance counts before and after filtering; avoid logging sensitive data or creating high-cardinality metric labels.

## 10. Design principles

- Providers publish consistent metadata in Eureka or Consul.
- Use ServiceInstance.getMetadata() to read instance attributes on the consumer.
- Use ZonePreferenceServiceInstanceListSupplier when zone is a preference and cross-region fallback is acceptable.
- Use a custom metadata-filtering supplier when version, region, or deployment group is a mandatory condition.
- Distinguish hard filtering from preference; do not apply zone-style fallback to version compatibility rules.
- Define behavior when metadata is missing or no matching instance exists.
- Keep LoadBalancer configuration scoped to the right service ID and verify supplier order.
- Refresh caches when metadata changes and monitor synchronization lag.
- Do not use metadata as an authentication or authorization mechanism.

Metadata allows consumers to choose instances by deployment attributes instead of relying solely on address lists. By combining provider metadata with ServiceInstanceListSupplier, Spring Cloud LoadBalancer can prioritize nearby zones or filter exact versions. What matters most is clearly distinguishing which fields are preferences versus mandatory conditions, and how the system should react when no matching instance remains.
