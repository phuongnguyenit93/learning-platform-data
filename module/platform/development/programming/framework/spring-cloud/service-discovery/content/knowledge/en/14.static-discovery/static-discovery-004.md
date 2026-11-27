# Static Discovery Does Not Auto-Register or Auto-Detect Dead Instances

Static discovery is a way for a consumer to locate services from a pre-declared list of addresses in configuration. With Spring Cloud, `SimpleDiscoveryClient` can read URI lists by service ID and return `ServiceInstance` objects for the application or Spring Cloud LoadBalancer to use.

The advantage of this approach is simplicity: there is no need to deploy a Eureka Server, Consul, or a separate registry just to hold an instance list. However, a static list only describes the addresses that were configured. It does not automatically register when a provider starts, does not automatically deregister when a provider stops, and does not automatically determine whether an instance has died.

This is a limitation you must understand when choosing static discovery. If instance addresses or statuses change, the operations team must update the configuration source or add another health check and endpoint update mechanism. This article explains how `SimpleDiscoveryClient` works, how services are called, what it does not handle, and how to operate it safely.

## 1. How does static discovery work?

In the static discovery model, the consumer knows the list of instance URIs ahead of time. The list is placed in a configuration file, environment variables, or an externally managed configuration source.

For example, `order-service` needs to call `inventory-service`. Configuration contains two addresses:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://10.0.2.15:8081
              - uri: http://10.0.2.16:8081
~~~

The service ID is `inventory-service`. The two URIs are the two instances the consumer is configured to know about. When the consumer looks up this service ID, `SimpleDiscoveryClient` returns the corresponding list of `ServiceInstance` objects.

~~~mermaid
flowchart LR
    CFG["Static configuration<br/>inventory-service"]
    D["SimpleDiscoveryClient"]
    LB["Spring Cloud LoadBalancer"]
    A["Instance A<br/>10.0.2.15:8081"]
    B["Instance B<br/>10.0.2.16:8081"]
    CFG --> D
    D -->|"List of ServiceInstance"| LB
    LB -->|"Selects one instance"| A
    LB -.->|"Another request may select"| B
~~~

This list does not come from providers registering with a registry. It comes from the consumer's configuration. Therefore, a provider may be running yet absent from the list if not declared; conversely, an address may remain in the list even though the process at that address has stopped.

## 2. SimpleDiscoveryClient in Spring Cloud

Spring Cloud Commons provides the `DiscoveryClient` abstraction so applications can look up services by service ID. `SimpleDiscoveryClient` is an implementation that uses configuration properties as its data source.

The components play the following roles:

| Component | Role in static discovery |
|---|---|
| SimpleDiscoveryClient | Reads the declared instance list and returns it via DiscoveryClient |
| Service ID | Logical key used by the consumer to request the instance list |
| ServiceInstance | Describes an instance URI along with related metadata |
| Spring Cloud LoadBalancer | Selects an instance from the list supplied by discovery |
| Provider | Application actually handling requests at the declared URI |

SimpleDiscoveryClient is not a registry server. It does not accept registration requests from providers and does not manage instance lifecycles across different machines.

### Configuring the instance list

The configuration property takes the form:

~~~text
spring.cloud.discovery.client.simple.instances.<service-id>[<index>].uri
~~~

Example declaring multiple services:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://10.0.2.15:8081
              - uri: http://10.0.2.16:8081
            payment-service:
              - uri: https://10.0.4.20:8443
~~~

Each service ID can have one or more URIs. The list only applies to applications that have loaded that configuration. If another consumer does not share the same configuration, it may receive a different list or fail to find the service.

You do not have to configure every provider's addresses inside every application if your architecture uses a centralized configuration source. However, wherever the configuration source is stored, SimpleDiscoveryClient still needs to receive the current URI list at lookup time.

### Optional metadata

Instances can include metadata to describe deployment zones or groups:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://10.0.2.15:8081
                metadata:
                  zone: zone-a
                  version: v1
              - uri: http://10.0.3.21:8081
                metadata:
                  zone: zone-b
                  version: v2
~~~

Metadata is descriptive data. It does not automatically create filters, automatically pick the nearest zone, or automatically route requests to compatible versions. If you want to route by zone or version, an explicit policy is needed in the load balancer or the application's routing component.

## 3. Static discovery does not auto-register providers

In a dynamic registry model such as Eureka or Consul, providers typically register their instances at startup and deregister upon graceful shutdown. The registry holds instance details for consumers to look up.

With SimpleDiscoveryClient, the instance list is read by the consumer from configuration. Providers do not need to send a register request to SimpleDiscoveryClient, and SimpleDiscoveryClient does not provide a registration lifecycle equivalent to `ServiceRegistry`.

| Activity | Dynamic registry | Static discovery |
|---|---|---|
| Provider startup | Can auto-register via starter | Does not automatically add URI to consumer config |
| Graceful provider shutdown | Can deregister | Does not automatically remove declared URI |
| Adding an instance | Provider or platform updates registry | Operators update configuration list |
| Host/port change | Registry receives new registration | URI must be updated in configuration source |
| Consumer lookup | Reads discovery data from registry/client cache | Reads configured list |

For example, `inventory-service` has a new instance deployed at `10.0.2.17:8081`. If the consumer's configuration still contains only the two old URIs, SimpleDiscoveryClient has no way of knowing the new instance appeared.

Similarly, if instance `10.0.2.16:8081` stops, that URI remains in configuration until the configuration source is updated and the application receives the new list. A provider stopping does not trigger any deregister operation in static discovery.

## 4. Static discovery does not auto-detect dead instances

SimpleDiscoveryClient returns the declared instances. By default, it does not send periodic requests to each URI to verify whether the process is still alive. A successful lookup only proves the configuration contains a matching entry; it does not prove the endpoint is healthy.

Suppose the list has two instances:

~~~text
inventory-service
  http://10.0.2.15:8081
  http://10.0.2.16:8081
~~~

If the second instance crashes while configuration has not changed, the discovery list can still contain both URIs. When the LoadBalancer selects the second instance, the request can fail with connection refused, timeout, or TLS errors.

~~~mermaid
flowchart TD
    A["Static URI list"] --> B["SimpleDiscoveryClient returns two instances"]
    B --> C["LoadBalancer selects an instance"]
    C --> D{"Is endpoint healthy?"}
    D -->|"Yes"| E["Request is processed"]
    D -->|"No"| F["Request fails or times out"]
    F --> G["Consumer handles error via timeout/retry/circuit breaker"]
    G --> H["Operator or external mechanism updates configuration"]
~~~

The following concepts must be distinguished:

- **Discovery:** finding the addresses an application is configured to call.
- **Health check:** verifying whether an endpoint meets health criteria.
- **Failure detection:** detecting that an instance or connection is no longer working.
- **Deregistration:** removing an instance from the registration source so consumers stop receiving that address.

Static discovery addresses looking up addresses from configuration. Health checks, failure detection, and deregistration require additional mechanisms.

## 5. Calling services via Spring Cloud LoadBalancer

Static discovery can still be combined with Spring Cloud LoadBalancer. The LoadBalancer receives the `ServiceInstance` list from the discovery client and selects an instance for the request.

Example declaring a load-balanced `RestTemplate`:

~~~java
@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    public RestTemplate restTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
~~~

Consumer calling by service ID:

~~~java
@Service
public class InventoryClient {

    private final RestTemplate restTemplate;

    public InventoryClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public ItemDto getItem(String itemId) {
        return restTemplate.getForObject(
            "http://inventory-service/api/items/{id}",
            ItemDto.class,
            itemId
        );
    }
}
~~~

In this example, `inventory-service` is the service ID. Spring Cloud LoadBalancer uses `DiscoveryClient` to fetch the configured instances and then picks one for the request. The application needs a Spring Cloud LoadBalancer dependency compatible with the Spring Cloud release train in use.

Load balancing is not synonymous with health checking. A selection algorithm can distribute requests across the URIs in the list, but if the list is not filtered or updated based on health status, a dead instance can still be chosen.

### Querying directly with DiscoveryClient

When you need to inspect the instance list, the application can call `DiscoveryClient`:

~~~java
@Service
public class InventoryDiscovery {

    private final DiscoveryClient discoveryClient;

    public InventoryDiscovery(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> getInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
~~~

The result reflects the declared list currently known to the client. Do not treat this list as a list of endpoints that have passed health checks.

## 6. Managing address and instance count changes

Because a static list does not sync automatically with provider lifecycles, the operations team needs a clear update procedure.

When adding an instance:

1. Deploy the provider and confirm the API is reachable from the consumer.
2. Check the health endpoint or external check mechanism.
3. Add the URI to the configuration of relevant consumers.
4. Release or refresh configuration using the mechanism supported by the application.
5. Verify the consumer has picked up the new URI and the LoadBalancer can select that instance.

When removing an instance:

1. Stop routing new requests to the instance according to the rollout procedure.
2. Wait for in-flight requests to finish if needed.
3. Remove the URI from the configuration source.
4. Ensure consumers have loaded the updated list and relevant caches are refreshed.
5. Only then stop the provider process.

If you stop the instance before consumers update their configuration, requests can still be sent to the old address. Therefore, updating the list and stopping the provider must be coordinated.

### File-based configuration vs. centralized configuration

For small systems, the list can live directly in `application.yml`. When there are many consumers, duplicating the same list into every repository easily causes drift.

You can manage the list in a centralized configuration source, such as Spring Cloud Config or an internal configuration management system. However, changing the configuration source does not guarantee every running application updates its list immediately. You need to determine the refresh mechanism, when properties rebind, how `DiscoveryClient` or its supplier is refreshed, and LoadBalancer caching behavior for the version in use.

Do not simply replace a configuration file on a server and assume the application has picked up the new URI. Check the configuration values after refresh and the `getInstances` output from the consumer.

## 7. Adding health checks and failure detection

If you want to detect dead instances, you can add one of the following mechanisms:

| Mechanism | How it works | Things to note |
|---|---|---|
| Load balancer / proxy health check | Routing component probes endpoints and excludes unhealthy targets | Requires configuring probes, timeouts, and recovery criteria |
| Client-side health-check supplier | Supplier probes instances and gives a filtered list to LoadBalancer | Must be configured explicitly; not default SimpleDiscoveryClient behavior |
| Orchestrator readiness probe | Platform evaluates readiness and updates endpoints/service routing | Consumers must go through the orchestrator's endpoint mechanism or sync state accordingly |
| Dynamic registry | Providers register, and health checks or heartbeats update registry state | Requires operating Eureka, Consul, or the corresponding registry |
| External monitoring | Monitor checks endpoints and updates configuration source | Must avoid race conditions and erroneous instance updates |

A simple health check can call an Actuator endpoint:

~~~bash
curl --fail --max-time 2 http://10.0.2.15:8081/actuator/health
~~~

This command only illustrates a manual check. To automate checking, a component must run probes periodically, interpret results, and update target lists or routing state. Do not write a standalone check script and assume it has removed an instance from SimpleDiscoveryClient.

### Client-side health checks with LoadBalancer

Spring Cloud LoadBalancer can be configured with a health-check-capable supplier in appropriate versions. This mechanism requires explicitly configuring the endpoint, check interval, and how the HTTP client is created. It adds an instance-filtering step to the LoadBalancer, but it does not turn SimpleDiscoveryClient into a registry with registration/deregistration.

When using a health-check supplier, evaluate:

- Does the health endpoint reflect the readiness of the API being called?
- Can probes running from the consumer's network reach the instance?
- Are timeouts and probe intervals appropriate for the number of instances?
- When an endpoint recovers, how is the instance returned to the list?
- Is there any cache causing new status updates to take effect slowly?

Do not run health checks too frequently if the number of consumers and instances is large, because the total probe volume can put significant load on providers.

## 8. Timeouts, retries, and circuit breakers are still necessary

Even with health checks, an instance's state can change between two probes. An instance that was healthy during a check can stop right before receiving a request. Therefore, the consumer must handle connection errors during actual request execution.

- **Connection timeout:** limits the time spent waiting to establish a connection.
- **Response timeout:** limits the time spent waiting for a response.
- **Retry:** bounded retries on appropriate errors when the operation is safe.
- **Circuit breaker:** temporarily blocks requests to a target or dependency that is failing continuously.
- **Fallback:** returns an alternative result or controlled error message when the provider cannot be reached.

Retries must pay attention to idempotency. If an order-creation or payment-deduction request reached the provider but the response was lost, resending the request can cause duplicate actions without an idempotency key or deduplication mechanism.

Do not use unbounded retries to mask a stale URI list. If an instance has been removed from the system, update the configuration source or health-check mechanism to stop selecting that address.

## 9. When is static discovery a good fit?

Static discovery is a good fit when:

- The instance count is small and addresses are relatively stable.
- Development, demo, or integration test environments need simple configuration.
- The system has a few fixed endpoints managed by the operations team.
- Consumers call a stable virtual IP or DNS name of an external load balancer.
- Provider self-registration is unnecessary and topology changes are infrequent.

Static discovery is a poor fit when:

- Instances are autoscaled frequently.
- Containers or pods are continuously recreated with changing addresses.
- Multiple consumers need near-real-time endpoint updates.
- Dead instances need to be removed automatically from the discovery list.
- The system requires health status, metadata, and complex routing policies.

In those situations, a dynamic registry or an orchestration platform with automatically updated service endpoints is usually better suited.

## 10. Comparing static discovery and dynamic registries

| Criterion | Static discovery | Dynamic registry |
|---|---|---|
| Instance list source | Declared configuration | Registry receiving registrations from providers |
| Provider registration | Not automatic | Typically integrated via starter/API |
| Deregistration | Manual config update or external mechanism | Can deregister on shutdown |
| Dead instance detection | Not built-in | Can use heartbeats/health checks |
| Address changes | Update config and refresh consumers | Provider registers new address |
| Additional infrastructure | Fewer components | Requires registry or corresponding platform |
| Operations | Simple when topology is stable | Suited for frequently changing topologies |

Static discovery is not a flawed design. It simply has a narrower scope of responsibility. If the endpoint list is stable and well managed, this approach can be simple, easy to test, and sufficient.

## 11. Static discovery operations checklist

Before deployment:

1. Confirm each service ID has the exact URI list needed.
2. Verify host, port, scheme, and TLS certificates from the consumer's network.
3. Confirm each provider is ready before adding its URI.
4. Verify the LoadBalancer actually uses SimpleDiscoveryClient.
5. Set appropriate connection and response timeouts.
6. Define who is responsible for updating the list when instances are added, replaced, or removed.
7. If using health checks, identify which component runs probes and how failing targets are excluded.
8. Check caches and refresh mechanisms to know when a new list takes effect.
9. Have a rollback procedure if configuration contains an incorrect address.
10. Monitor connection errors, timeouts, retry counts, and failure rates per instance.

During an incident:

- Inspect the URI list the consumer is actually using.
- Call the endpoint directly from the consumer's runtime environment.
- Distinguish between DNS, TCP, TLS, HTTP, and business errors.
- Check whether the instance is still in configuration.
- If the endpoint has been decommissioned, update the configuration source and confirm consumers refreshed.
- If the endpoint is intentionally retained, add appropriate health checks or routing policies.

## 12. Key principles to remember

- SimpleDiscoveryClient reads instance lists from configuration by service ID.
- Static discovery does not auto-register providers and does not auto-deregister when providers stop.
- The URI list does not inherently reflect whether instances are alive or dead.
- Spring Cloud LoadBalancer selects instances from the list but does not automatically turn a static list into a health-checked list.
- To detect dead instances, you must add health checks, a health-aware load balancer/proxy, an orchestrator, or a dynamic registry.
- When changing the list, update configuration, refresh discovery, and account for caching according to your Spring Cloud version.
- Always configure timeouts and request error handling because health checks cannot completely eliminate race conditions.

Static discovery is a simple way to look up services based on a known address list. It fits stable topologies and small environments, but does not replace registration lifecycles, heartbeats, or health checks. Once the system starts scaling frequently or requires automatic removal of failing instances, add an appropriate endpoint management mechanism or migrate to a dynamic registry like Eureka, Consul, or your deployment platform's discovery.
