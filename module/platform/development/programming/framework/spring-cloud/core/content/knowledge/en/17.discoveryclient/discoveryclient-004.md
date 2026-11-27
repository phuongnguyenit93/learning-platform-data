# Instance Metadata and Implementation-Specific Interpretation Limits

## 1. What Is Instance Metadata Used For?

Service discovery returns instances that consumers can call. Beyond service ID, host, port, and URI, an instance can carry metadata: key/value pairs describing deployment version, zone, canary group, load-balancing weight, or details supporting instance-selection policies.

For example, two instances of `catalog-service` can both serve requests while running different versions:

| Instance | Host | Metadata |
| --- | --- | --- |
| `catalog-a` | `catalog-a.internal` | `version=v1`, `zone=zone-a`, `weight=80` |
| `catalog-b` | `catalog-b.internal` | `version=v2`, `zone=zone-b`, `weight=20` |

Consumers can use this information to observe rollouts, prefer instances in a nearby network zone, or distribute traffic by weight. However, metadata is only descriptive data for consumers. The meaning of any key depends on the component reading it. A registry can store and return metadata without changing routing on its own.

This lesson belongs to the **DiscoveryClient** chapter of the **SPRING_CLOUD_CORE** module. The module focuses on Spring Cloud Commons, Context, external configuration, discovery, service registries, service communication, and testing and operating common abstractions.

After this lesson, learners can:

- Explain the metadata contract of `ServiceInstance`.
- Distinguish generic Spring Cloud Commons metadata from Eureka-, Consul-, and Kubernetes-specific data.
- Identify keys that Spring Cloud LoadBalancer interprets out of the box.
- Understand why the same key may have no effect if the consumer does not enable the right supplier or integration.
- Design a metadata schema with namespaces, data types, and compatibility rules.
- Handle missing, malformed, stale, or untrusted metadata.
- Test metadata across provider, registry, and consumer layers.

## 2. The Common ServiceInstance Contract

Spring Cloud Commons defines `ServiceInstance` as an abstraction describing an instance in a discovery system. One of the abstraction's methods is:

```java
@Nullable
Map<String, String> getMetadata();
```

This contract indicates that metadata is a key/value map where both keys and values are strings. The method is annotated as nullable; consumers must not assume the map always exists or is non-empty.

A `ServiceInstance` typically provides the following information:

| Member | Meaning |
| --- | --- |
| `getServiceId()` | Logical name of the service. |
| `getInstanceId()` | Identifier of a specific registration; may be absent depending on implementation. |
| `getHost()` / `getPort()` | Address and port the consumer uses to connect. |
| `getUri()` | Base URI of the instance. |
| `isSecure()` | Whether the instance is published for HTTPS access. |
| `getMetadata()` | Metadata map supplied to consumers by the discovery implementation. |

The key point is that Commons standardizes the **data shape**, not the full business semantics of keys. `ServiceInstance` does not mandate that `version`, `zone`, `weight`, `team`, or `tenant` must be present. Nor does it require every concrete registry to map all native fields into metadata the same way.

Therefore, separate three layers:

1. **Source metadata:** labels, annotations, tags, or metadata maps declared in the registry/platform.
2. **Metadata projection:** the key/value pairs a discovery provider maps into `ServiceInstance.getMetadata()`.
3. **Metadata interpretation:** the consumer, LoadBalancer, or custom code that reads a key and applies a concrete behavior.

A key present in the first layer is not guaranteed to appear in the second layer. A key appearing in `ServiceInstance` also has no effect unless a component in the third layer interprets it.

## 3. Metadata Does Not Share Universal Meaning Across Implementations

Each discovery provider has its own data model and mapping rules. Never take one provider's configuration and apply it verbatim to another provider.

| Provider | Common Metadata Source | How It Enters `ServiceInstance` | Notes |
| --- | --- | --- | --- |
| Eureka | `eureka.instance.metadata-map` | The metadata map in the Eureka instance registration returned to clients. | Many keys are purely custom data; clients must know how to interpret them. |
| Consul | Service `meta`, `metadata`, and `management-metadata` config | Spring Cloud Consul maps service metadata into the `ServiceInstance` map. | Consul tags are no longer a supported way to populate the `ServiceInstance` metadata map in current versions. |
| Kubernetes | Service labels, annotations, and some port/namespace info | Spring Cloud Kubernetes can project enabled fields into the metadata map. | Prefixes, enable flags, and client implementation determine which keys appear. |
| SimpleDiscoveryClient | Metadata declared in instance configuration | Built from the statically configured instance list. | No registry server updates data automatically; changes depend on application configuration. |

Accordingly, if an application migrates from Eureka to Consul or Kubernetes, re-verify mappings and consumer contracts. Having identical key names does not prove data shares the same origin, scope, or update timing.

## 4. Eureka: Metadata Map and Consumer-Dependent Meaning

With Spring Cloud Netflix Eureka, instance metadata can be declared via `eureka.instance.metadata-map`.

Example:

```yaml
eureka:
  instance:
    metadata-map:
      zone: zone-a
      weight: "80"
      hint: canary
      API_VERSION: "2"
      com.example.owner: catalog-team
```

Metadata is registered with the instance and can be read by other Eureka clients. According to Spring Cloud Netflix documentation, most extra metadata does not alter client behavior unless the client is programmed to understand that key's meaning. A few cases have Spring Cloud-defined semantics, such as zone for instance selection.

For instance, `com.example.owner` is purely descriptive data. It does not grant ownership, send alerts to the team, or alter routing. Applications wishing to use it must read it and define behavior themselves.

### 4.1. Zone in Eureka

One case with built-in semantics is the `zone` key. Spring Cloud Netflix can use `eureka.instance.metadata-map.zone` to provide the instance's zone to Spring Cloud LoadBalancer. `ZonePreferenceServiceInstanceListSupplier` reads the `zone` key in metadata to filter instances in the same zone as the client when that supplier is configured.

Example:

```yaml
eureka:
  instance:
    metadata-map:
      zone: zone-a
```

Zone metadata must match the infrastructure's zone naming convention. `zone-a`, `Zone-A`, and `zone_a` are distinct strings under exact-match comparison. Standardize spelling and avoid assuming hostname or region automatically counts as zone.

### 4.2. Not All Eureka Metadata Configures Behavior

- `zone` can be understood by Spring Cloud Netflix/LoadBalancer when the proper integration is enabled.
- `weight` is read by Spring Cloud LoadBalancer when the weighted supplier is used.
- `hint` is read by the hint-based supplier when configured.
- `API_VERSION` is read by the API-version supplier when API version-based load balancing is enabled.
- `com.example.owner` has no built-in behavior automatically applied by Spring Cloud.

Do not infer that placing a key in the Eureka metadata map causes LoadBalancer to use it automatically. The consumer needs the right implementation and supplier configuration.

## 5. Consul: Service Metadata, Management Metadata, and Tags

Consul has a `meta` field for services. Spring Cloud Consul maps this data into `ServiceInstance.getMetadata()`. Metadata can be declared under `spring.cloud.consul.discovery.metadata`; for separate management services, `management-metadata` can be used.

Example:

```yaml
spring:
  cloud:
    consul:
      discovery:
        metadata:
          zone: zone-a
          weight: "80"
          release-track: stable
          com.example.owner: catalog-team
        management-metadata:
          endpoint-group: operations
```

Current Spring Cloud Consul also generates several metadata entries automatically:

| Key | Source | Meaning |
| --- | --- | --- |
| `group` | `spring.cloud.consul.discovery.instance-group` | Instance group if configured. |
| `secure` | Whether registration scheme is `https` | Value indicating the instance is published as secure. |
| `zone` (configurable key name) | `spring.cloud.consul.discovery.instance-zone` | Instance zone if configured. |

The default zone key name is `zone`, and can be changed via `spring.cloud.consul.discovery.default-zone-metadata-name`. Avoid creating custom keys that collide with provider-generated metadata without defining precedence and semantics.

### 5.1. Distinguishing Metadata and Tags

Older Spring Cloud Consul versions parsed tags formatted as `key=value` to simulate metadata. That legacy mapping is no longer supported for populating `ServiceInstance.getMetadata()` in current versions. Use the `spring.cloud.consul.discovery.metadata` map for metadata.

Tags can still be used as a separate concept within Consul and in provider filtering/tag mechanisms. However, do not assume a tag `zone=zone-a` will automatically appear in `ServiceInstance.getMetadata()` on current versions.

When upgrading Spring Cloud Consul, inspect where applications declare metadata. Configurations that previously relied on tags to pass data to consumers may need to migrate to the `metadata` map.

## 6. Kubernetes: Labels, Annotations, and Metadata Projection

Kubernetes has labels and annotations on resources such as Services or Pods. Spring Cloud Kubernetes Discovery Client can project some of this data into `ServiceInstance.getMetadata()`.

Common properties controlling projection:

| Property | Effect |
| --- | --- |
| `spring.cloud.kubernetes.discovery.metadata.add-labels` | Includes Service labels in metadata. |
| `spring.cloud.kubernetes.discovery.metadata.add-annotations` | Includes Service annotations in metadata. |
| `spring.cloud.kubernetes.discovery.metadata.add-ports` | Includes named port information in metadata. |
| `spring.cloud.kubernetes.discovery.metadata.labels-prefix` | Adds a prefix to keys from labels. |
| `spring.cloud.kubernetes.discovery.metadata.annotations-prefix` | Adds a prefix to keys from annotations. |
| `spring.cloud.kubernetes.discovery.metadata.ports-prefix` | Adds a prefix to port keys; default is `port.`. |
| `spring.cloud.kubernetes.discovery.metadata.add-pod-labels` | Allows adding Pod labels if supported by the implementation. |
| `spring.cloud.kubernetes.discovery.metadata.add-pod-annotations` | Allows adding Pod annotations if supported by the implementation. |

In current Spring Cloud Kubernetes documentation, `add-labels`, `add-annotations`, and `add-ports` are enabled by default; projecting pod labels and pod annotations into metadata is disabled by default. Verify against your exact version and Kubernetes client implementation because support can vary.

Example:

```yaml
spring:
  cloud:
    kubernetes:
      discovery:
        metadata:
          add-labels: true
          add-annotations: true
          labels-prefix: "label."
          annotations-prefix: "annotation."
          add-pod-labels: false
          add-pod-annotations: false
```

Service manifest:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog
  labels:
    app: catalog
    release-track: canary
  annotations:
    com.example.owner: catalog-team
spec:
  selector:
    app: catalog
  ports:
    - name: http
      port: 80
      targetPort: 8080
```

With prefixes as shown, consumers can see keys such as `label.app`, `label.release-track`, or `annotation.com.example.owner`. Without prefixes, key names could collide with provider- or application-defined keys. Prefixes help distinguish sources and reduce collision risk.

Spring Cloud Kubernetes may also add keys such as `k8s_namespace`, `type`, and port metadata. How `ServiceInstance` is constructed can include additional fields depending on version and discovery client type. Do not assume all of these keys exist across all implementations.

## 7. Keys Interpreted by Spring Cloud LoadBalancer

Spring Cloud LoadBalancer includes several suppliers that know how to read metadata. This is the clearest demonstration that metadata meaning comes from the consumer implementation.

| Metadata Key | Supplier / Feature | Behavior |
| --- | --- | --- |
| `weight` | `WeightedServiceInstanceListSupplier` | Reads and parses the weight; if absent, defaults weight to `1`. |
| `zone` | `ZonePreferenceServiceInstanceListSupplier` | Filters instances by desired zone; if zone is missing or no instances match that zone, returns the original list. |
| `hint` | `HintBasedServiceInstanceListSupplier` | Filters instances whose hint matches the request hint; if no matching instance is found, returns the list provided by the delegate. |
| `API_VERSION` | Blocking/Reactive API version supplier | Finds instances whose version metadata matches the request version or default version. |

These keys do not take effect merely by appearing in the registry:

- The weighted supplier must be configured in the `ServiceInstanceListSupplier` chain.
- Zone preference requires the corresponding supplier. Eureka has an integration that automatically supplies zone to LoadBalancer; with other discovery clients, you may need to set `spring.cloud.loadbalancer.zone`.
- The hint-based supplier must be enabled; requests must supply a hint via the configured header or property.
- The API version-based supplier must be enabled, and requests must provide a version via the configured header, query parameter, path segment, or media type parameter.

With built-in configurations, you can select `weighted`, `zone-preference`, or `api-version` via `spring.cloud.loadbalancer.configurations` for the corresponding client. The hint-based supplier can be composed into a custom supplier chain using `withHints()`:

```yaml
spring:
  cloud:
    loadbalancer:
      configurations: weighted
```

```java
@Bean
ServiceInstanceListSupplier serviceInstanceListSupplier(
        ConfigurableApplicationContext context) {
    return ServiceInstanceListSupplier.builder()
            .withDiscoveryClient()
            .withCaching()
            .withHints()
            .build(context);
}
```

### 7.1. Weighted Load Balancing

When the weighted supplier is enabled, the `weight` metadata key is read as a number. Example:

```yaml
eureka:
  instance:
    metadata-map:
      weight: "80"
```

A value of `80` does not mean the instance automatically receives 80% of traffic under every configuration. It is only used when LoadBalancer is running the weighted supplier. If the application uses the default round-robin supplier, the `weight` key does not alter the algorithm on its own.

### 7.2. Zone Preference

Metadata:

```yaml
eureka:
  instance:
    metadata-map:
      zone: zone-a
```

The consumer side needs to know the desired zone, for example via `spring.cloud.loadbalancer.zone` or via the corresponding Eureka integration. Zone preference does not strictly guarantee every request stays in the same zone: if no instances exist in that zone, the supplier can fall back to the original list so the system remains available.

### 7.3. Hint-Based Routing

Metadata:

```yaml
eureka:
  instance:
    metadata-map:
      hint: canary
```

The hint-based supplier can read the default `X-SC-LB-Hint` header or a per-service configured hint. When a request carries hint `canary`, the supplier looks for instances with metadata `hint=canary`. If no matching instance exists, the default behavior is to return the delegate's list rather than returning an empty list.

Do not use hints as an authorization or data-isolation mechanism. A hint is an instance-selection signal, not a security boundary.

### 7.4. API Version-Based Routing

Spring Cloud LoadBalancer provides a supplier for API versions. When enabled, requests carry a version and the supplier looks for a matching `API_VERSION` metadata key.

Example:

```yaml
eureka:
  instance:
    metadata-map:
      API_VERSION: "2"
```

If no instance with a matching version is found, the returned list may be empty by default. You can configure `spring.cloud.load-balancer.clients.<serviceId>.api-version.fallbackToAvailableInstances=true` for the relevant service if policy allows falling back to any available instance. Only enable fallback when API versions are genuinely compatible; otherwise fallback can produce subtle runtime errors.

## 8. Custom Metadata: Defining Your Own Contract

Applications may need custom keys such as:

```text
com.example.owner=catalog-team
com.example.release-track=canary
com.example.routing-policy=low-latency
com.example.capability=bulk-read
```

Because the metadata map only holds strings, applications must explicitly specify:

- Key names and key ownership namespaces.
- Logical data types: boolean, integer, enum, version, or string.
- Units for numbers, such as milliseconds or requests/second.
- Valid values and default values when a key is missing.
- Behavior when a key is malformed or unsupported.
- Metadata schema version and rollout compatibility rules.

Avoid generic keys like `mode`, `team`, or `version` if multiple systems could interpret them differently. Use a namespace such as `com.example.*` for internal metadata. For keys defined by Spring Cloud LoadBalancer like `zone`, `weight`, `hint`, and `API_VERSION`, keep the exact names expected by the suppliers.

### 8.1. Value Conventions

Example schema:

| Key | Logical Type | Example | When Missing |
| --- | --- | --- | --- |
| `com.example.release-track` | Enum | `stable`, `canary` | `stable` |
| `com.example.max-payload-bytes` | Integer | `1048576` | Unlimited or reject per policy |
| `com.example.supports-bulk-read` | Boolean | `true`, `false` | `false` |
| `com.example.config-schema` | Version | `1` | Use defined legacy schema |

Do not mix ambiguous values like `yes`, `on`, `enabled` if the consumer only accepts `true`/`false`. Do not use unitless numbers for timeouts or sizes when multiple teams could interpret them differently.

### 8.2. Consumers Must Parse Safely

Since `getMetadata()` can return `null` and values can be malformed, parse defensively:

```java
Map<String, String> metadata = instance.getMetadata();
String rawWeight = metadata == null ? null : metadata.get("weight");

int weight = 1;
if (rawWeight != null) {
    try {
        int parsed = Integer.parseInt(rawWeight);
        if (parsed > 0 && parsed <= 100) {
            weight = parsed;
        }
    }
    catch (NumberFormatException ex) {
        // Record sanitized metric/log; apply agreed fallback policy.
    }
}
```

This is an example for a custom consumer. When using a built-in Spring Cloud supplier, adhere to that supplier's contract and test malformed values as well. Do not assume all suppliers share the same fallback when parsing fails.

Do not mutate the map returned by `getMetadata()` directly. Treat metadata as read-only input data; if transformation is required, create a separate map or object.

## 9. Interpretation Limits and Design Risks

### 9.1. Metadata Is Not a Universal Schema

A `version` key could mean application version, API version, image version, or schema version. Without a clear definition, consumers may compare incorrectly or route requests to incompatible instances.

Use specific keys like `API_VERSION` when integrating with suppliers that define that contract; use a dedicated namespace for internal metadata.

### 9.2. Metadata Is Not Health Status

Metadata `healthy=true` is merely a string supplied by the registration source. It does not prove the instance is alive or ready to receive traffic. Use health checks and the registry/discovery provider's status. If a special capability or operational state is needed, clearly distinguish it from liveness/readiness.

### 9.3. Metadata Is Not a Security Mechanism

Never store passwords, access tokens, private keys, session IDs, or personal data in metadata. Registries typically allow many clients to read registration data. Metadata is also not a trustworthy source for deciding whether a user is authorized to access a resource.

If metadata is used to select a tenant, role, or processing group, the consumer must still authenticate requests and verify permissions using dedicated security mechanisms. Never let a client self-declare metadata and treat it as an authorization basis.

### 9.4. Metadata Can Be Missing or Heterogeneous

A cluster may contain instances running multiple application versions simultaneously. Older versions may not emit a new key yet while newer consumers have already started reading it. Consumers must have a policy for absent keys, and rollouts must maintain backward compatibility.

When changing a metadata schema:

1. Deploy consumers that understand both the old and new schemas.
2. Start registering the new metadata.
3. Monitor the percentage of instances publishing the new key.
4. Drop support for the old schema only after all instances have transitioned.

### 9.5. Metadata Can Be Stale Due to Caching

Registries, discovery clients, and Spring Cloud LoadBalancer may all cache data. Current Spring Cloud LoadBalancer documentation sets the default cache TTL to 35 seconds when using default settings; discovery clients may also maintain their own caches. Consequently, metadata updates in the registry may not immediately appear in every consumer.

If metadata affects routing, determine acceptable staleness, configure caching appropriately, and avoid unnecessary double caching. When debugging, compare registry data, `DiscoveryClient.getInstances()` results, and the instance list actually used by LoadBalancer.

### 9.6. Metadata Does Not Replace Standard Connection Fields

Do not store host, port, or secure flags as custom metadata when `ServiceInstance` already provides standard fields for them. Do not use metadata instead of URI or service ID. Custom keys may be ignored by clients or conflict with provider-generated keys.

## 10. Layer-by-Layer Metadata Testing

A test that only checks whether YAML contains a metadata key does not prove the consumer receives and uses that key properly. You need to test the full chain from declaration to interpretation.

| Test Layer | Scope | Example Assertions |
| --- | --- | --- |
| Provider configuration | Config binds properly into the provider's metadata map | Eureka/Consul/Kubernetes creates a registration with the expected keys and values. |
| Registry integration | Metadata is stored and returned | Read instance from registry; verify key presence and value accuracy. |
| Discovery projection | Provider maps metadata onto `ServiceInstance` | `getMetadata()` contains keys with the expected prefix/format. |
| Consumer parsing | Handles missing, null, malformed, and out-of-range values | Does not throw unhandled errors; falls back per contract. |
| LoadBalancer supplier | Supplier reads the key properly when enabled | Weighted/zone/hint/API-version selects or filters the right instances. |
| Compatibility | Old and new instances coexist | Consumer does not fail when older instances lack the new metadata. |
| Security | Metadata contains no secrets or sensitive data | Inspect registration payloads and logs. |
| Cache | New metadata appears after the configured cache window | Verify update latency matches cache configuration. |

### 10.1. Consumer Unit Tests

Use mock `ServiceInstance` instances covering:

- Metadata map with all valid keys.
- Empty map.
- `null` metadata.
- Non-numeric `weight` value.
- `zone` value outside supported zones.
- Missing or incompatible `API_VERSION`.

Verify that the consumer does not turn invalid data into unhandled errors or out-of-policy instance choices.

### 10.2. Provider Integration Tests

For each discovery implementation, start a test provider or use an appropriate test registry:

- Register the instance.
- Read the registration from the registry.
- Call the discovery client to retrieve `ServiceInstance`.
- Compare the metadata map against the defined contract.

Do not rely solely on unit testing a hand-built `Map` if the goal is verifying Eureka, Consul, or Kubernetes mappings. Those mappings belong to the provider implementation.

### 10.3. LoadBalancer Tests

If metadata is used for routing, verify the corresponding supplier is actually registered:

- Weighted: verify the supplier enables weighted selection and processes `weight`.
- Zone: verify local zone and `zone` metadata follow the convention.
- Hint: verify request hints are passed and `hint` metadata is filtered.
- API version: verify request version matches `API_VERSION` metadata; also test the case where no matching version is found.

If a test only instantiates the default `RoundRobinLoadBalancer`, having `weight` metadata will not prove weighted routing works.

## 11. Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Metadata is in YAML but missing in `ServiceInstance` | Wrong property name, provider does not map that source, or projection config not enabled | Check registration in the registry, then check `getMetadata()`. |
| Consul tags do not appear in metadata map | Relying on legacy tags mechanism | Switch to `spring.cloud.consul.discovery.metadata`. |
| Kubernetes label lacks expected prefix | Prefix or `add-labels` flag differs from config | Check metadata projection and key namespaces. |
| `weight` is present but traffic remains round-robin | Weighted supplier is not enabled | Inspect the active `ServiceInstanceListSupplier`. |
| Zone preference does not filter instances | Supplier not configured, client zone unset, or wrong key | Check `spring.cloud.loadbalancer.zone` and metadata key `zone`. |
| Hint fails to select canary | Request does not pass hint or instance lacks matching `hint` key | Check header/property and hint-based supplier. |
| API version finds no instances | `API_VERSION` missing or differs from request value | Check version parser, metadata, and fallback policy. |
| Consumer reads stale metadata after update | Registry/discovery/load-balancer cache | Check TTL and caches at each layer. |
| A key has different values across providers | Provider auto-generates metadata or uses different prefix rules | Inspect source metadata and implementation-specific projection. |
| Metadata misused as health or access permission | Consumer assigns semantics beyond contract | Separate health/authentication from custom metadata. |

## 12. Design Guidelines

1. **Treat `ServiceInstance.getMetadata()` as an optional data map.** Handle null, missing keys, and malformed values.
2. **Identify the provider before writing configuration.** Eureka, Consul, Kubernetes, and SimpleDiscoveryClient map metadata differently.
3. **Document a metadata contract for consumers.** Specify keys, logical types, units, valid values, defaults, and schema version.
4. **Use standard keys when integrating built-in suppliers.** `weight`, `zone`, `hint`, and `API_VERSION` carry concrete semantics in their respective features.
5. **Enable the right LoadBalancer supplier.** Metadata does not replace the default load-balancing algorithm on its own.
6. **Namespace custom keys.** Avoid colliding with provider-generated keys or keys reserved by Spring Cloud.
7. **Maintain compatibility during rollouts.** Consumers must handle older instances that do not yet publish new keys.
8. **Never store secrets or authorize from metadata.** Discovery data does not replace security systems.
9. **Account for caching and propagation delay.** Do not assume updating metadata in the registry takes effect instantaneously in all consumers.
10. **Test end-to-end across provider → registry → DiscoveryClient → consumer.** Unit testing an isolated map does not verify implementation mappings.

## 13. Self-Check Questions

1. What data shape does `ServiceInstance.getMetadata()` standardize, and what are its limitations?
2. Why might metadata stored in a registry not appear in `ServiceInstance.getMetadata()`?
3. Why does extra Eureka metadata usually not alter client behavior?
4. How does current Spring Cloud Consul map service metadata, and why shouldn't tags continue to be used in the old way?
5. Which resource fields can Spring Cloud Kubernetes pull metadata from?
6. What conditions must be met for the `weight` key to actually affect Spring Cloud LoadBalancer?
7. Which suppliers interpret `zone`, `hint`, and `API_VERSION`?
8. Why does `healthy=true` metadata not replace a health check?
9. How do you maintain compatibility when older instances have not yet registered a new metadata key?
10. Design an integration test that verifies metadata from Eureka registration through LoadBalancer instance selection.

## 14. Official References

- [Spring Cloud Commons — ServiceInstance API](https://docs.spring.io/spring-cloud-commons/docs/current/api/org/springframework/cloud/client/ServiceInstance.html)
- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Netflix — Eureka Metadata for Instances and Clients](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Consul — Service Discovery and Metadata](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Kubernetes — Discovery Metadata Properties](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html)

Metadata contracts, key mappings, and semantics can vary by implementation and release train. Before relying on metadata to drive routing, verify against the documentation of the provider, Spring Cloud Commons, and the actual supplier running in your application.
