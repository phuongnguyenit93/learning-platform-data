# Querying Services via Spring DiscoveryClient

In a microservice architecture, a calling application normally knows the logical name of the target service, such as inventory-service, yet should not hardcode the IP and port of each instance. When the instance count changes due to scaling, deployments, or failure recovery, addresses change accordingly. Spring Cloud provides DiscoveryClient as a common API for an application to resolve a service ID into a list of ServiceInstance objects.

With Spring Cloud Consul, DiscoveryClient fetches data from the Consul Service Catalog and Health API. Application code can rely on the same abstraction when switching to another discovery provider, while registration, health checks, and data queries are handled by the corresponding implementation.

## 1. What Problem Does DiscoveryClient Solve?

Suppose order-service needs to call inventory-service. If order-service hardcodes http://10.0.0.12:8080, replacing a host or running additional instances forces the caller to know and update the new addresses.

Service discovery reverses that dependency: the application requests instances by service name. The discovery provider returns the host, port, URI, and metadata of registered instances.

    order-service
         |
         | getInstances("inventory-service")
         v
    DiscoveryClient
         |
         v
    Consul Discovery implementation
         |
         v
    Consul Agent / Health API
         |
         v
    List<ServiceInstance>
         |
         v
    Application uses URI or LoadBalancer selects an instance

DiscoveryClient supplies information to locate a service. It does not send HTTP requests itself, does not guarantee the endpoint remains healthy after the lookup, and does not perform load balancing for a plain HTTP client on its own.

## 2. Adding Dependencies and Configuring Consul

To use Consul as the discovery provider, add the following starter to your Spring Boot application:

**Maven**

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-consul-discovery</artifactId>
    </dependency>

**Gradle**

    dependencies {
        implementation 'org.springframework.cloud:spring-cloud-starter-consul-discovery'
    }

Use a Spring Cloud BOM compatible with your project's Spring Boot version to manage dependency versions. This starter configures Consul Discovery and provides the Spring Cloud DiscoveryClient implementation.

Example configuration for order-service:

    spring:
      application:
        name: order-service
      cloud:
        consul:
          host: localhost
          port: 8500
          discovery:
            enabled: true
            register: true
            register-health-check: true
            health-check-path: /actuator/health

The Consul Agent is looked up at localhost:8500 by default. If the application runs in Docker or Kubernetes, use a Consul Agent address reachable from the application's network namespace. localhost inside a container points only to that container itself.

spring.application.name is normally used as the default service name upon registration. Thus, if inventory-service registers with Consul under inventory-service, consumers must query that exact service ID. If spring.cloud.consul.discovery.service-name is configured to change the registered name, consumers must use the overridden name.

An application that only needs to look up services without registering itself can set spring.cloud.consul.discovery.register=false. This does not disable DiscoveryClient; it only disables registering the application's own service.

## 3. Two Primary Lookup Methods

DiscoveryClient lives in the org.springframework.cloud.client.discovery package. The two most commonly used methods are:

| Method | Return Type | Purpose |
|---|---|---|
| getServices() | List<String> | Retrieve the list of service IDs known to the discovery client |
| getInstances(serviceId) | List<ServiceInstance> | Retrieve instances belonging to a service ID |

Example:

    List<String> serviceIds = discoveryClient.getServices();

    List<ServiceInstance> instances =
            discoveryClient.getInstances("inventory-service");

If the service ID does not exist or has no matching instances, the result is typically an empty list. Applications must handle this case rather than assuming at least one instance is always present.

DiscoveryClient also provides a probe() method to verify whether the discovery client can perform discovery operations. Implementations may execute a lighter query than getServices(). A successful probe only indicates the discovery client can reach the provider; it does not prove every service has healthy instances.

## 4. What Information Does ServiceInstance Contain?

Each element returned from getInstances() is a ServiceInstance. This interface represents a concrete service endpoint rather than the entire logical service.

Commonly used methods:

| Method | Meaning |
|---|---|
| getServiceId() | Service ID the instance belongs to |
| getInstanceId() | Instance identifier if supplied by the provider |
| getHost() | Host or IP of the instance |
| getPort() | Port the instance registered |
| getUri() | URI built from scheme, host, and port |
| isSecure() | Indicates whether the instance uses a secure connection |
| getMetadata() | Metadata map registered by the provider with the instance |

Not every provider supplies the same metadata. With Consul, registration details typically include service name, instance ID, address, port, tags, and metadata. Specific fields depend on registration configuration and provider version.

Example of a service with two instances:

    inventory-service
      - instance: inventory-1
        host: 10.0.0.21
        port: 8081
        metadata:
          zone: hcm-a
      - instance: inventory-2
        host: 10.0.0.22
        port: 8081
        metadata:
          zone: hcm-b

DiscoveryClient returns the corresponding list of ServiceInstance objects. The application can read metadata to display info, log details, or apply custom filtering if business logic requires it.

## 5. Injecting DiscoveryClient Into a Service

Spring Boot auto-configures the DiscoveryClient implementation when the Consul Discovery starter is present and discovery is enabled. You can inject the abstraction into a bean via constructor injection:

    import java.net.URI;
    import java.util.Collections;
    import java.util.List;
    import java.util.stream.Collectors;

    import org.springframework.cloud.client.ServiceInstance;
    import org.springframework.cloud.client.discovery.DiscoveryClient;
    import org.springframework.stereotype.Service;

    @Service
    public class InventoryDiscoveryService {

        private final DiscoveryClient discoveryClient;

        public InventoryDiscoveryService(DiscoveryClient discoveryClient) {
            this.discoveryClient = discoveryClient;
        }

        public List<URI> findInventoryUris() {
            List<ServiceInstance> instances =
                    discoveryClient.getInstances("inventory-service");

            if (instances.isEmpty()) {
                return Collections.emptyList();
            }

            return instances.stream()
                    .map(ServiceInstance::getUri)
                    .collect(Collectors.toList());
        }
    }

The method above returns the URIs of all instances returned by the provider at query time. This list may change on the next call as new instances register, get deregistered, or change health check status.

Do not hold the instance list indefinitely in a static field. If the application caches results manually, define a TTL, refresh mechanism, and behavior when Consul is unreachable. Normally, let the discovery client and load balancer manage instance retrieval via their built-in mechanisms.

## 6. Listing Services and Inspecting Instances

You can create a small helper class to observe which service IDs Consul returns:

    @Service
    public class DiscoveryCatalog {

        private final DiscoveryClient discoveryClient;

        public DiscoveryCatalog(DiscoveryClient discoveryClient) {
            this.discoveryClient = discoveryClient;
        }

        public List<String> listServices() {
            return discoveryClient.getServices();
        }

        public List<ServiceInstance> findInstances(String serviceId) {
            return discoveryClient.getInstances(serviceId);
        }
    }

When debugging, log the service ID, instance ID, URI, and necessary metadata. Never log secrets or sensitive data stored in metadata.

    for (ServiceInstance instance :
            discoveryClient.getInstances("inventory-service")) {
        log.info(
                "serviceId={}, instanceId={}, uri={}, metadata={}",
                instance.getServiceId(),
                instance.getInstanceId(),
                instance.getUri(),
                instance.getMetadata()
        );
    }

The output helps identify which services the application sees and which addresses are returned. If getServices() includes inventory-service while getInstances("inventory-service") is empty, check registration state, health checks, and service ID spelling.

## 7. Impact of Consul Health Checks

Spring Cloud Consul registers an HTTP health check for the service by default. The Consul Agent periodically calls /actuator/health; if the check fails, the instance can be marked critical in Consul.

The spring.cloud.consul.discovery.query-passing property controls appending the passing parameter to Consul Health API queries. The default value is false. When set to true, Consul returns only instances with passing health checks for that query:

    spring:
      cloud:
        consul:
          discovery:
            query-passing: true

This directly affects getInstances() results. When query-passing=false, query results can include instances in warning or critical states depending on health data and the API used. When query-passing=true, Consul filters to return only passing instances.

Do not confuse getInstances() with the health endpoint. DiscoveryClient asks Consul for the instance list; Consul relies on previously recorded health checks to build the result. An application's health endpoint may change immediately, whereas Consul updates status only after the next check cycle.

## 8. Direct Lookup vs. Calling Services via LoadBalancer

These are two separate steps:

1. Looking up the instance list via DiscoveryClient.
2. Selecting an instance and sending an HTTP request to it.

When using DiscoveryClient alone, the application must pick an instance itself and handle timeouts, retries, connection errors, and instances going down after the lookup. Picking the first element in the list is not a reliable load-balancing policy.

In typical service-calling applications, pair it with Spring Cloud LoadBalancer. Add the starter:

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>

Configure a load-balanced RestTemplate:

    import org.springframework.cloud.client.loadbalancer.LoadBalanced;
    import org.springframework.context.annotation.Bean;
    import org.springframework.context.annotation.Configuration;
    import org.springframework.web.client.RestTemplate;

    @Configuration
    public class HttpClientConfiguration {

        @Bean
        @LoadBalanced
        public RestTemplate loadBalancedRestTemplate() {
            return new RestTemplate();
        }
    }

Call the service by service ID instead of a hardcoded host:

    @Service
    public class InventoryClient {

        private final RestTemplate restTemplate;

        public InventoryClient(
                @LoadBalanced RestTemplate restTemplate) {
            this.restTemplate = restTemplate;
        }

        public String getItem(String itemId) {
            return restTemplate.getForObject(
                    "http://inventory-service/api/items/{id}",
                    String.class,
                    itemId
            );
        }
    }

When encountering a URL whose host is inventory-service, LoadBalancer uses the service ID to fetch the instance list from the discovery client and selects one instance per configured strategy. The request is sent to the actual URI of the chosen instance.

LoadBalancer does not turn discovery into a guarantee that a request will succeed. An instance can fail after a health check or between selection and request transmission. The application still needs timeouts, bounded retries, circuit breakers, and error handling suited to the request type.

## 9. Filtering Services by Tag, Datacenter, and Metadata

Consul supports tags to categorize services. Spring Cloud Consul can configure tags at registration and configure server-list queries by tag. Registration example:

    spring:
      cloud:
        consul:
          discovery:
            tags:
              - api
              - internal
              - version-v2

When queries need to be restricted by tag, you can configure server-list-query-tags per service ID. Example:

    spring:
      cloud:
        consul:
          discovery:
            server-list-query-tags:
              inventory-service: api

This option applies a tag filter when querying the instance list for the corresponding service. Ensure the tag is properly registered in Consul; if the tag does not match, results may be empty.

In a multi-datacenter Consul cluster, the service ID alone is not enough to specify the target datacenter. Spring Cloud Consul supports configuring datacenters per service ID, for example:

    spring:
      cloud:
        consul:
          discovery:
            datacenters:
              inventory-service: dc-west

Verify the datacenter name in Consul and cross-datacenter reachability before using it. Do not treat metadata or tags as a security mechanism; this data only supports categorization and filtering.

## 10. DiscoveryClientHealthIndicator

When Consul Discovery is enabled in a Spring Boot Actuator application, Spring Cloud can configure DiscoveryClientHealthIndicator. This indicator uses the discovery client to verify service discovery query capability.

By default, the health indicator may call getServices() to check and report status. In a system with many services, querying the full service list on every health check can be expensive. You can configure:

    spring:
      cloud:
        discovery:
          client:
            health-indicator:
              use-services-query: false

When use-services-query=false, the indicator uses probe() instead of querying the entire service list. This is a useful option when you only need to confirm the discovery client can reach the provider.

DiscoveryClientHealthIndicator reflects the discovery client's capability, not that all service instances are healthy. Each service's own health check in Consul remains the source of truth for instance status.

## 11. Troubleshooting Common Errors

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| getServices() returns an empty list | Consul has no services yet or application cannot reach Consul | Check Consul Agent, service catalog, and logs |
| getInstances() returns empty | Wrong service ID, service not registered, or query-passing filtered all instances out | Match spring.application.name/service-name and health status |
| Returned URI is unreachable | Registered hostname/IP is unreachable from consumer | Check DNS, network, prefer-ip-address, and registered address |
| LoadBalancer call reports no instances | Discovery returns empty list or service ID in URL is wrong | Check hostname in URL and discovery client |
| A critical instance still appears | query-passing=false or query does not filter passing | Check query-passing config and Consul Health API |
| Works only on the host machine | Containerized app misuses localhost | Use DNS/service name on the Docker network |
| Discovery health indicator is slow | getServices() loads a large list on every check | Consider use-services-query=false and probe() |

Diagnostic steps should flow from provider to consumer:

1. Verify the Consul Agent is running and the application can call the Consul API.
2. Verify the service appears in the Consul Catalog with the exact service ID.
3. Check each instance's health check and status (passing, warning, or critical).
4. Call getServices() and getInstances(serviceId) to inspect the data received by the application.
5. Verify URI, DNS, and connectivity from the consumer's actual runtime environment.
6. If using LoadBalancer, check the service ID in the URL, the LoadBalancer dependency, and instance selection logs.

## 12. Conclusion

Spring Cloud DiscoveryClient provides a unified API to list service IDs via getServices() and retrieve instances via getInstances(serviceId). With Consul, the implementation queries Consul data and converts it into ServiceInstance objects containing URI, host, port, and metadata.

DiscoveryClient decouples application code from registry-specific APIs, yet does not send requests itself or guarantee an instance remains healthy after lookup. For service-to-service calls, combine it with Spring Cloud LoadBalancer to select instances and handle network errors. In operations, verify the service ID, health status, query-passing, instance addresses, and reachability from the consumer's network.

## References

- [Spring Cloud Commons — DiscoveryClient API](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/DiscoveryClient.java)
- [Spring Cloud Consul — Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Consul — Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [Spring Cloud Consul — Discovery Client Usage](https://docs.spring.io/spring-cloud-consul/docs/current/reference/html/quickstart.html)
- [Spring Cloud — SimpleDiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
