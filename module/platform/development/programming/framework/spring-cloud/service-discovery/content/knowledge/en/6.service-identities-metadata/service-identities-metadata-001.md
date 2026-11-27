# Logical Service Names and the `spring.application.name` Convention

In Spring Cloud Service Discovery, a consumer typically does not need to know the IP address or port of each instance it calls in advance. The consumer needs to know the **logical service** it wants to use, such as `inventory-service` or `payment-service`. The registry stores instances providing the service under that logical name; the client looks up the name to obtain the list of instances and selects an appropriate instance.

The `spring.application.name` property is a key configuration point for assigning a logical name to a Spring Boot application. This name is commonly used by Spring Cloud as the service ID when registering the application and is also the name consumers use to look up the service. Therefore, you should choose a name that is stable, consistent, and meaningful across the entire system.

## 1. What Is a Logical Service Name?

A service can run as multiple replicas. For example, a system has three instances of the inventory service:

- `inventory-service` at `10.0.1.21:8080`
- `inventory-service` at `10.0.1.22:8080`
- `inventory-service` at `10.0.1.23:8080`

The three processes have different network addresses and instance identifiers, yet fulfill the same business role. The registry groups them under a single logical name, `inventory-service`. Consumers only need to request the instances of that name.

Four concepts should be distinguished:

| Concept | Example | Meaning |
|---|---|---|
| Logical service name (service ID) | `inventory-service` | Groups instances providing the same service |
| Instance identifier (instance ID) | `inventory-service:pod-a81f` | Distinguishes a specific process or deployment unit |
| Network address | `10.0.1.21:8080` | Where the instance can be reached |
| Metadata | `zone=ap-southeast-1a`, `version=v2` | Additional information for describing or filtering instances |

A logical name is not a hostname, IP, port, Java class name, or UI display name. It is the shared lookup key between the service registrar and the service consumer.

## 2. Role of `spring.application.name`

Declare the name in the application configuration:

```yaml
spring:
  application:
    name: inventory-service

server:
  port: 8081
```

In a Spring Cloud configuration with service discovery enabled, `spring.application.name` is typically used as the default service ID when the application registers with the registry. For example:

- With Eureka, the application name is used as the application name in the registry.
- With Consul, this name is typically used as the registered service name. You can configure `spring.cloud.consul.discovery.service-name` if you need a different registration name.
- For consumers, the same service ID is used when calling `DiscoveryClient` or when constructing logical URLs for Spring Cloud LoadBalancer.

Simply declaring `spring.application.name` does not create a registry by itself or guarantee that the application has registered successfully. The application still requires the appropriate discovery client dependency and configuration for Eureka, Consul, or whichever registry provider is in use.

### Service Name Usage Flow

1. The application starts up and loads its configuration, including `spring.application.name`.
2. The discovery client builds the registration details for the instance. These details typically include the service ID, instance ID, host, port, status, and metadata.
3. The registry stores the instance under the corresponding service ID. Multiple instances can belong to the same service ID.
4. The consumer looks up the service ID to receive the list of instances.
5. Spring Cloud LoadBalancer or the application's selection logic picks an instance to send the request to.
6. When an instance stops or loses connectivity, the registry's deregistration, heartbeat, or health check mechanism updates that instance's status.

Logical names keep consumers from being hardcoded to a specific machine's address. When the number of instances changes, consumers still call the same service ID.

## 3. Service Naming Conventions

A good service name should be stable and reflect the service's role in the system. The following conventions can be applied:

- **Use lowercase letters and hyphens.** For example: `order-service`, `inventory-service`, `payment-service`. This style is readable and minimizes differences across environments.
- **Name after business capabilities.** The name should indicate what the service is responsible for, rather than the development team name, host name, or deployment technology.
- **Keep the name identical across replicas.** Every instance of the same logical service must register under the same service ID. Each instance is distinguished by its own instance ID and address.
- **Do not put per-deployment information in the service ID.** Do not use a pod name, hostname, IP, port, or build number as the service name.
- **Do not embed the version in the name unless you intend to split routes.** Version information is usually better suited for metadata or a version routing mechanism. Only use `inventory-v2` when the system genuinely needs to treat that version as an independent service target.
- **Avoid overly generic names.** Names such as `service`, `backend`, or `api` do not convey responsibility and easily collide.
- **Standardize the naming scope within the registry.** Two different applications should not register under the same service ID if consumers might mistakenly receive an instance of the wrong application.

Examples:

| Recommended | Avoid | Reason |
|---|---|---|
| `customer-service` | `CustomerService` | Lowercase, consistent convention |
| `order-service` | `order_service` | Hyphens are easier to standardize than underscores |
| `inventory-service` | `inventory-service-pod-7f9c` | Logical name should not depend on a specific pod |
| `payment-service` | `backend` | Name reflects the business capability |
| `notification-service` | `notification-service-v2026-11-24` | Changing builds should not change the logical identity |

Registries may have their own normalization or name-matching rules. Therefore, use a consistent spelling and ensure consumers use the exact service ID registered by the provider; do not rely on the assumption that the registry will automatically normalize uppercase letters, underscores, or spaces to the same name.

### Environment-Specific Names

If each environment has its own registry or namespace, you can keep the same name `inventory-service` across development, staging, and production. Environments are already separated at the registry layer, so the service name does not need to change.

If multiple environments share the same registry and namespace, they must be clearly separated so consumers in one environment do not see instances from another. You can use separate namespaces/datacenters or a prefix convention such as `dev-inventory-service`, depending on the platform's capabilities. Do not mechanically add environment prefixes when the registry already provides isolation boundaries.

## 4. Configuring the Name in Spring Boot

The base configuration should be placed in the application's common configuration file:

```yaml
spring:
  application:
    name: order-service
```

Profiles can change the port, registry endpoint, or environment parameters while keeping the logical name:

```yaml
# application-dev.yml
server:
  port: 8082
```

The name can also be passed via an environment variable:

```bash
SPRING_APPLICATION_NAME=order-service
```

Or via a command-line argument:

```bash
java -jar order-service.jar --spring.application.name=order-service
```

When using externalized configuration, ensure the name value is loaded before the discovery client constructs the registration information. If multiple configuration sources set this property, check Spring Boot's configuration precedence order to determine the final value.

### Eureka Example

An application can declare its name and Eureka server address as follows:

```yaml
spring:
  application:
    name: order-service

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
```

When the Eureka client is enabled and connects successfully, the application registers under the corresponding application name. Multiple running copies of `order-service` appear as instances of the same application.

### Consul Example

You can declare the service name explicitly:

```yaml
spring:
  application:
    name: order-service
  cloud:
    consul:
      host: localhost
      port: 8500
      discovery:
        service-name: ${spring.application.name}
```

Setting `service-name` to `spring.application.name` makes the registered name explicit in the configuration. If you intentionally set `service-name` to a different value, consumers must look up the actual name in Consul; do not assume the two properties are always identical once overridden.

## 5. Consumer Lookup by Service ID

Spring Cloud provides `DiscoveryClient` to query the list of instances by service name. The following example illustrates how to read the instances of `inventory-service`:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class InventoryDiscovery {

    private final DiscoveryClient discoveryClient;

    public InventoryDiscovery(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
```

The result is the list of instances visible to the discovery client at query time. Each `ServiceInstance` provides information such as the service ID, host, port, URI, and metadata. An empty list may indicate that the service is not yet registered, the lookup name does not match, the instance is not ready, or the registry has not updated yet.

In real applications, you should not default to picking the first element in the list and using it for every request. That bypasses load balancing and can funnel all traffic to a single instance. For HTTP calls between services, you should typically use a client integrated with Spring Cloud LoadBalancer.

Example with `RestTemplate`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.web.client.RestTemplate;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate restTemplate() {
        return new RestTemplate();
    }
}
```

The consumer calls using the logical name:

```java
String url = "http://inventory-service/api/items/42";
Item item = restTemplate.getForObject(url, Item.class);
```

With a `@LoadBalanced` bean and the appropriate Spring Cloud LoadBalancer configuration, the host segment `inventory-service` is interpreted as a service ID. LoadBalancer retrieves instances from the discovery client and selects an instance for the request. This example requires the corresponding LoadBalancer dependency in the project.

## 6. Common Naming Pitfalls

**Provider and consumer use two different names.** The provider registers `inventory-service`, while the consumer calls `inventories-service`. The registry cannot find any instances for the name requested by the consumer, resulting in an empty list or a no-suitable-instance error.

**Each replica generates its own distinct name.** If each pod registers using its hostname or pod ID, replicas are no longer grouped under a shared service ID. Consumers would have to know each individual name, making load balancing across a logical service difficult.

**Multiple incompatible applications share the same name.** If `billing-service` and another application both register under `billing-service`, LoadBalancer may select the wrong instance. Sharing the same name is only appropriate when the instances genuinely fulfill the same service contract expected by consumers.

**The registration name is overridden in the provider's configuration.** A Eureka- or Consul-specific property can cause the actual name in the registry to differ from `spring.application.name`. When troubleshooting errors, check the name displayed in the registry and the provider's discovery configuration, then compare it against the service ID the consumer is querying.

**Using the service ID to represent metadata.** Avoid creating names like `inventory-service-zone-a-v2` just to describe a zone or version if that is not an intentional routing boundary. Metadata is better suited for supplementary attributes; the service ID should represent a stable logical identity.

## 7. Pre-Deployment Checklist

When configuring a new service, check each item in order:

1. `spring.application.name` is clearly declared and follows naming conventions.
2. Every replica of the same service uses the same logical name.
3. Each instance has unique identification and address details so the registry can distinguish them.
4. The service name in the registry matches the name looked up by consumers.
5. If the provider uses an override property such as `service-name`, the final value has been verified.
6. Environments are isolated using an appropriate registry or namespace.
7. Consumers receive the expected list of instances and the HTTP client has load balancing configured.

Do not place passwords, tokens, secret keys, or sensitive data in the service ID or metadata. Metadata may be displayed in the registry and read by many components across the system.

## 8. End-to-End Example

Suppose an e-commerce system has three services:

| Application | `spring.application.name` | Responsibility |
|---|---|---|
| Order | `order-service` | Create and track orders |
| Inventory | `inventory-service` | Check and update stock levels |
| Payment | `payment-service` | Process payments |

When `order-service` needs to check inventory, it sends a request to the logical address `http://inventory-service/api/items/42`. The registry supplies the instances registered under `inventory-service`; LoadBalancer picks an instance and forwards the request to the corresponding network address.

If the operations team scales the inventory replicas from two to five, the consumer still calls `inventory-service`. The new addresses are added to the registry as each instance registers successfully. The consumer does not need to update URLs for new IPs or ports.

That is the purpose of a logical service name: keeping how microservices reference each other stable while instance counts and locations change during deployment and operations.
