# Adding the Eureka Client Starter and Configuring the Service Name

## Objectives

After this lesson, you will be able to:

- Add Spring Cloud Netflix Eureka Client to a Spring Boot application using Maven or Gradle.
- Declare the service name using `spring.application.name` and the Eureka Server address.
- Explain how an instance registers, sends heartbeats, and fetches the service list from the registry.
- Verify registration and identify common configuration mistakes.

## What Does Eureka Client Do?

In a microservice architecture, a service typically runs as multiple instances. The IP address or port of each instance can change when the application is redeployed, scaled, or moved to another host. If one service calls another using a hardcoded address, the caller's configuration will quickly become stale.

In Spring Cloud Service Discovery, `DiscoveryClient` is the abstraction that allows an application to query instances by service ID, while `ServiceRegistry` standardizes registration and deregistration operations. Eureka and Consul provide different registry implementations for these abstractions. This lesson focuses on configuring Eureka Client so an application can participate in a Eureka registry.

Eureka Server maintains the registry containing information about registered instances. Eureka Client is the component running inside a Spring Boot application that enables it to participate in that registry. The client can register its own instance, send heartbeats to indicate that the instance is still alive, and fetch the instance list of other services.

The `spring-cloud-starter-netflix-eureka-client` starter brings Eureka Client and its Spring Cloud integration onto the classpath. When the application starts with the appropriate configuration, Spring Cloud auto-configures `DiscoveryClient` and the Eureka client to perform registration, registry updates, and service discovery.

Eureka Client does not turn an application into a Eureka Server by itself. A client application needs to connect to a running Eureka Server. The server side uses a separate starter, `spring-cloud-starter-netflix-eureka-server`.

## 1. Adding the Eureka Client Dependency

Spring Cloud manages its libraries by release train. The release train version must be compatible with your project's Spring Boot version. Use the Spring Cloud BOM to manage Spring Cloud dependency versions consistently; do not pick an individual version for Eureka Client arbitrarily.

### Maven

Declare the Spring Cloud BOM in `dependencyManagement`, then add the starter without specifying a version directly:

~~~~xml
<properties>
    <spring-cloud.version>REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
~~~~

Replace `REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN` with the release train compatible with your Spring Boot version. If the project already imports the Spring Cloud BOM at the parent level or in shared dependency management configuration, you do not need to import the BOM a second time.

### Gradle Kotlin DSL

With Gradle, you can import the BOM using `platform`:

~~~~kotlin
val springCloudVersion = "REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN"

dependencies {
    implementation(platform("org.springframework.cloud:spring-cloud-dependencies:$springCloudVersion"))
    implementation("org.springframework.cloud:spring-cloud-starter-netflix-eureka-client")
}
~~~~

After adding the dependency, re-sync the project and inspect the dependency tree if Gradle or Maven reports version conflicts. Do not mix different Spring Cloud release trains within the same application.

## 2. Setting the Service Name and Configuring Eureka Server

The service name is declared with `spring.application.name`. This is the logical identifier that other services use when looking up instances in the registry. This name is not a hostname, IP address, or network port of a single instance.

For example, an inventory management application can use the name `inventory-service`:

~~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: 8081

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
    register-with-eureka: true
    fetch-registry: true
~~~~

Key properties:

| Property | Meaning |
| --- | --- |
| `spring.application.name` | Logical name of the service. Instances belonging to the same service normally share this name. |
| `server.port` | HTTP port on which the instance listens. Each instance can use a different port. |
| `eureka.client.service-url.defaultZone` | URL of the Eureka Server the client connects to, usually ending with `/eureka/`. |
| `eureka.client.register-with-eureka` | Allows the instance to register itself with the registry. |
| `eureka.client.fetch-registry` | Allows the client to fetch the registry to discover other services. |

In YAML, keep `defaultZone` spelled exactly as shown for the final key. It is a map key in the Eureka URL configuration; do not change it to `default-zone`. You can specify the URL using environment variables during deployment so each environment points to its own registry, instead of hardcoding `localhost` in production configuration.

Both `register-with-eureka` and `fetch-registry` typically default to `true`; declaring them explicitly in the example helps clarify the client's role. An application that only needs to read the registry can disable registration with `register-with-eureka: false`. Keep `fetch-registry: true` if the application needs to look up other services.

Service names should be stable, readable, and consistent across environments—for example, `inventory-service`, `order-service`, or `payment-service`. Do not include a port or instance identifier in `spring.application.name`, because multiple instances of the same service must be grouped under the same service ID. Eureka may display the application name in uppercase on the dashboard; that does not mean the configured `spring.application.name` value has been changed.

## 3. Registration and Discovery Process

When the application starts, Spring Cloud creates the Eureka client based on the dependencies and configuration. The client reads the application name, server address, and instance metadata, then contacts the Eureka Server to register. At runtime, the client periodically sends heartbeats and updates the registry according to its configuration. The client also fetches the registry to learn which instances are currently published.

High-level flow:

~~~~mermaid
flowchart LR
    A[inventory-service application] -->|Registration and heartbeat| E[Eureka Server]
    E -->|Instance registry| B[order-service application]
    B -->|Lookup by service ID| D[DiscoveryClient]
    D -->|Instance list| B
    B -->|Send request to selected instance| A
~~~~

`spring.application.name` defines the service ID; each running process is an instance of that service. Therefore, when running three replicas of `inventory-service`, the registry can store three instances under the same service name, each with a different address or instance ID.

Eureka Client normally registers automatically on startup; the application does not need to call a registration REST endpoint manually. In modern Spring Cloud versions, having Eureka Client on the classpath already enables the corresponding discovery auto-configuration. You do not need to add `@EnableEurekaClient` or `@EnableDiscoveryClient` just to turn on this default behavior.

## 4. Verifying That the Application Is Registered

Suppose Eureka Server is running at `http://localhost:8761` and the `inventory-service` application is running on port `8081`:

1. Start Eureka Server and verify that the dashboard is reachable.
2. Start the application with Eureka Client.
3. Check the startup logs to verify whether the client can connect to the configured URL.
4. Open the Eureka dashboard and look for `INVENTORY-SERVICE` in the instances list.
5. Verify that the published address and port are reachable from the services that need to call it.

A successful application startup alone does not prove registration succeeded. If the instance does not appear on the dashboard, check the registry URL, network connectivity, and Eureka client logs. In development, Eureka Server commonly uses port `8761`; in real deployments, the URL must point to a server address reachable from the container or host running the application.

You can also inspect the registry from code using Spring Cloud Commons' `DiscoveryClient`:

~~~~java
import java.net.URI;
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class ServiceLookup {

    private final DiscoveryClient discoveryClient;

    public ServiceLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<URI> findInstances(String serviceId) {
        return discoveryClient.getInstances(serviceId)
                .stream()
                .map(ServiceInstance::getUri)
                .collect(Collectors.toList());
    }
}
~~~~

For example, calling `findInstances("inventory-service")` returns the URIs of the instances that the client currently knows about in the registry. The result may be empty if the service has not registered yet, the registry has not been fetched yet, or the service ID does not match.

`DiscoveryClient` only provides instance information. If you want to call a service by logical name and automatically choose an instance per request, applications typically combine Spring Cloud LoadBalancer with a load-balancer-enabled HTTP client. Adding Eureka Client alone does not automatically turn every HTTP call using a service name into a load-balanced request.

## 5. Distinguishing Service Name and Instance ID

`spring.application.name` represents the entire service. `eureka.instance.instance-id` represents a specific process within that service. When running multiple replicas, each instance needs a unique identifier in the registry. In simple setups, Spring Cloud can generate a default instance ID. If the dashboard shows instances overwriting one another or makes them hard to tell apart, configure `eureka.instance.instance-id` with a unique value, such as a combination of hostname and port.

The advertised instance address also needs to match the deployment network. Setting `eureka.instance.prefer-ip-address: true` tells the client to publish its IP address instead of its hostname. Only enable this option when that IP address is reachable by other clients. In Kubernetes, Docker, or multi-subnet networks, an internal IP may not be reachable from callers; in those cases, choose a hostname or configure an advertised address suited to your network topology.

## 6. Integrating Health Checks

Heartbeats indicate that the client is still communicating with Eureka Server; they do not necessarily prove that all business capabilities of the application are healthy. If you want Spring Boot's health status to be reflected in the instance status, you can add Spring Boot Actuator and enable Eureka's health check integration:

~~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~~

When enabling this option, ensure health indicators accurately reflect readiness to serve requests and configure Actuator endpoints appropriately. Do not expose management endpoints or detailed health information to public networks without access controls. Status updates in the registry can also lag behind actual state changes because the client and server need time for heartbeat exchanges, updates, and expiration eviction.

## 7. Common Issues

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Application missing from dashboard | Wrong server URL, unreachable network, or client not registering | Check `defaultZone`, DNS, firewall rules, and Eureka connection logs. |
| Logs report failure to contact Eureka Server | Wrong URL, server not running, or address only reachable from another host | Test accessing the URL from the application's runtime environment; verify port and `/eureka/` path. |
| Unexpected application name | Missing or misconfigured `spring.application.name` | Check profile-specific configuration and the `SPRING_APPLICATION_NAME` environment variable. |
| Multiple instances overwrite each other or look identical | Duplicate instance IDs | Set a unique `eureka.instance.instance-id` per process. |
| Instance is discovered but calls fail | Published hostname/IP or port is unreachable from the calling service | Check the address in the dashboard from the caller's network perspective; adjust advertised hostname/IP and port. |
| Stopped instance remains in registry for a while | Registry has not detected missed heartbeats yet or self-preservation delays eviction | Check heartbeat intervals, leases, and server logs; do not assume an instance disappears immediately when the process stops. |
| Service not found via `DiscoveryClient` | Registry not synced yet or mismatched service ID | Check `fetch-registry`, service name, and the instance list seen by the client. |

In production deployments, protect Eureka Server with a private network, authentication, and TLS according to your infrastructure requirements. Only allow required services to access the registry; never treat the dashboard or registration endpoints as public resources. Likewise, manage registry URLs and credentials via environment configuration or a secret store, and never commit secrets to a repository.

## Key Takeaways

- Add `spring-cloud-starter-netflix-eureka-client` so a Spring Boot application participates in Eureka discovery.
- Use a Spring Cloud BOM compatible with your Spring Boot version to manage dependency versions.
- Set `spring.application.name` to a stable service ID; port and instance ID describe each individual instance.
- Configure `eureka.client.service-url.defaultZone` to point to a Eureka Server reachable from the application's runtime environment.
- Verify registration on the dashboard and via `DiscoveryClient`; check the advertised address before assuming the service is callable.
- Eureka Client provides discovery; client-side load balancing requires an appropriate component such as Spring Cloud LoadBalancer.
