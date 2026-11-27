# Configuring Service Name, Port, and Replica Instance Identity

In the `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING` module, the project needs to clearly define which service is running, where each process listens, and how each replica is identified. These three pieces of information allow Spring Cloud LoadBalancer to find the right group of instances by service ID, and then select a specific instance to send the request to.

This hands-on lab uses `order-service` calling `inventory-service`. We run multiple replicas of `inventory-service` sharing the same service name but with distinct instance identities. Upon completion, you will be able to configure an application running on multiple ports on a development machine or across multiple containers/pods in a deployment environment, and verify that the registry distinguishes each replica.

## Distinguishing Service Name, Port, and Instance ID

These three values serve different roles and should not be conflated:

| Property | Example | Meaning | Rule When Running Multiple Replicas |
|---|---|---|---|
| `spring.application.name` | `inventory-service` | Logical name of the application; usually used as the service ID in discovery and client URIs | Keep identical across replicas of the same service |
| `server.port` | `8081`, `8082` | HTTP port on which the Spring Boot process listens | On the same machine, each process needs an unused port; in separate containers, they can share the same internal port |
| Instance ID | `inventory-8081`, `inventory-8082` | Unique identifier for a replica in the registry or logs | Each replica must have a unique value within the registry scope |
| Host or network address | `localhost`, container IP, or pod hostname | Address the client actually connects to after LoadBalancer selects an instance | Must be reachable from the calling service's network |

For example, the registry can store two records under the same service ID `inventory-service`:

| Service ID | Instance ID | Registered Address |
|---|---|---|
| `inventory-service` | `inventory-8081` | `http://localhost:8081` |
| `inventory-service` | `inventory-8082` | `http://localhost:8082` |

When `order-service` calls `http://inventory-service/api/inventory/SKU-01`, the `inventory-service` segment is the logical name. LoadBalancer retrieves the list of instances belonging to that service ID, selects one replica, and sends the request to its registered address. Therefore, do not name the applications `inventory-service-1` and `inventory-service-2` if the two processes are actually replicas of the same service; doing so creates two separate service IDs and leaves no shared instance group to load balance across.

## Preparing Dependencies and Projects

Create Spring Boot projects for `inventory-service` and `order-service`. The two applications can live in two Maven modules or two separate projects. Use a Spring Cloud BOM compatible with the project's Spring Boot version to manage library versions.

Example declaring the release train in `pom.xml`:

```xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>YOUR_COMPATIBLE_SPRING_CLOUD_VERSION</spring-cloud.version>
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
```

Replace `YOUR_COMPATIBLE_SPRING_CLOUD_VERSION` with a release train compatible with the Spring Boot version in use. Do not copy an arbitrary version number from another project because Spring Boot and Spring Cloud have their own compatibility matrix.

In `order-service`, add LoadBalancer and the discovery starter corresponding to your chosen registry. For example, if using Eureka:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
```

In `inventory-service`, add the discovery client starter if the service needs to self-register with the registry. With Eureka, use `spring-cloud-starter-netflix-eureka-client`; if using Consul or Kubernetes, substitute the corresponding starter. `spring-cloud-starter-loadbalancer` is the client-side instance selection component; it does not create a registry nor replace a discovery provider.

## Setting the Logical Name for Each Application

In `inventory-service/src/main/resources/application.yml`, declare the service name once:

```yaml
spring:
  application:
    name: inventory-service

server:
  port: ${SERVER_PORT:8081}

app:
  instance-id: ${INSTANCE_ID:${spring.application.name}:${server.port}}
```

`spring.application.name` is the shared logical name for all replicas. `SERVER_PORT` is an environment variable for changing the port at startup. `app.instance-id` is a project-defined application property to hold the unique identifier; if `INSTANCE_ID` is not passed, the example combines the service name and port as the default value. This default works well for a lab running multiple processes on the same machine on different ports.

In `order-service`, use a distinct name and port:

```yaml
spring:
  application:
    name: order-service

server:
  port: ${SERVER_PORT:8080}
```

The name `order-service` helps the registry and logs distinguish the calling application from the target application. When calling inventory, the client still uses the service ID `inventory-service`, not the instance ID or port of a specific replica.

## Configuring Addresses and Identity for Discovery

`app.instance-id` is a shared value in this example so you do not have to tie business logic to a specific discovery provider. When registering the service, map it to the instance ID property supported by the provider.

### If Using Eureka

In `inventory-service` and `order-service`, configure the Eureka server address. The following example assumes the registry runs on the development machine at port `8761`:

```yaml
eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_URL:http://localhost:8761/eureka/}
  instance:
    instance-id: ${app.instance-id}
    prefer-ip-address: true
```

`eureka.instance.instance-id` gives each replica a human-readable identifier in Eureka. `prefer-ip-address` tells the instance to advertise its IP instead of its hostname; only enable this when the advertised IP is reachable from other services. In Docker or Kubernetes, the registered address must be valid within the container/cluster network and must not point to a container's `localhost` if the client resides in another container.

For a lab running two processes on the same machine, you can start them sequentially with `INSTANCE_ID=inventory-8081` and `INSTANCE_ID=inventory-8082`. Both processes still use `spring.application.name=inventory-service`.

### If Using Consul

With Consul, map the identifier into Consul's discovery configuration:

```yaml
spring:
  cloud:
    consul:
      host: ${CONSUL_HOST:localhost}
      port: ${CONSUL_PORT:8500}
      discovery:
        service-name: ${spring.application.name}
        instance-id: ${app.instance-id}
```

`service-name` groups replicas into the same service; `instance-id` distinguishes each replica in Consul. If the project uses another provider, look up that provider's instance registration properties and map the same `app.instance-id`; do not configure Eureka and Consul simultaneously just to test a simple lab.

### If You Only Want to Test with a Static List

To test LoadBalancer before setting up a registry, you can use `SimpleDiscoveryClient` with a static URI list in `order-service`:

```yaml
spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082

server:
  port: 8080
```

This list gives the client two addresses to choose from without needing a registry. It does not automatically register or monitor the lifecycle of `inventory-service` processes; when stopping an instance, you must update the configuration list or switch to a discovery provider capable of updating instances. Use this approach for the initial lab step, then practice with a registry to understand instance registration and deregistration.

## Running Multiple Replicas on a Development Machine

Assume `inventory-service.jar` has been built. Open two terminals and start two processes with the same artifact and same service name, but different ports and instance IDs.

First terminal on Bash:

```bash
SERVER_PORT=8081 INSTANCE_ID=inventory-8081 java -jar inventory-service.jar
```

Second terminal on Bash:

```bash
SERVER_PORT=8082 INSTANCE_ID=inventory-8082 java -jar inventory-service.jar
```

On PowerShell, set the environment variables in each terminal before running:

```powershell
$env:SERVER_PORT = "8081"
$env:INSTANCE_ID = "inventory-8081"
java -jar .\inventory-service.jar
```

In the other terminal, change the two values to `8082` and `inventory-8082`. Environment variables apply only to processes launched from that terminal. If running via an IDE, create two Run Configurations using the same main class and artifact but different environment values.

When running in containers or Kubernetes, replicas can usually use the same internal port, such as `8080`, because each container/pod has its own network namespace. In that case, the host address or pod IP distinguishes endpoints; set `INSTANCE_ID` from the pod name, UID, or a platform-assigned unique value. Do not use service name plus internal port as the instance ID if every replica shares the same port and the registry requires unique IDs.

## Returning the Instance ID for Verification

In the lab, make each replica return its own identity. A simple way is to add a verification-only endpoint:

```java
@RestController
class InstanceInfoController {

    private final String serviceId;
    private final String instanceId;
    private final int port;

    InstanceInfoController(
            @Value("${spring.application.name}") String serviceId,
            @Value("${app.instance-id}") String instanceId,
            @Value("${server.port}") int port) {
        this.serviceId = serviceId;
        this.instanceId = instanceId;
        this.port = port;
    }

    @GetMapping("/internal/instance")
    Map<String, Object> instance() {
        return Map.of(
                "serviceId", serviceId,
                "instanceId", instanceId,
                "port", port);
    }
}
```

When accessing `http://localhost:8081/internal/instance` directly, the result should show `instanceId` as `inventory-8081`; port `8082` must return `inventory-8082`. This endpoint is for lab verification and observation. In real systems, consider restricting access to internal endpoints and avoiding exposing unnecessary infrastructure details.

## Connecting from order-service by Service ID

Once discovery has two instances, configure a load-balanced client in `order-service`:

```java
@Configuration
class InventoryClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
```

```java
@Service
class InventoryClient {
    private final RestClient restClient;

    InventoryClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    Map<?, ?> getInstanceInfo() {
        return restClient.get()
                .uri("http://inventory-service/internal/instance")
                .retrieve()
                .body(Map.class);
    }
}
```

The key point is that the URI uses `inventory-service`. LoadBalancer uses this service ID to fetch candidates from discovery and then picks an address. If you replace the URI with `http://localhost:8081`, requests call one replica directly and you can no longer verify load balancing.

## Step-by-Step Configuration Verification

Perform the following steps before moving on to the lesson on instance selection policies:

1. Start the registry if the project uses Eureka, Consul, or another provider.
2. Start two replicas of `inventory-service` with the same `spring.application.name`, two different `INSTANCE_ID` values, and valid reachable addresses.
3. Access `/internal/instance` directly on each port to confirm each process returns the right ID.
4. Open the registry UI or API and verify there are two instances under the same service ID `inventory-service`.
5. Start `order-service` and check that it can retrieve the instance list and call the URI containing the service ID.
6. Send multiple requests to the endpoint through `order-service`; record `instanceId` in the responses to observe which replicas are selected.
7. Stop one replica, wait for the registry and client to refresh the list according to the configured interval, then send more requests. Verify requests are served by the remaining available instance.

Expected outcomes of the initial setup step:

| Check | Expected Result |
|---|---|
| Service name of both replicas | Both are `inventory-service` |
| Ports when running two processes on the same machine | Different, e.g., `8081` and `8082` |
| Instance ID | Unique, e.g., `inventory-8081` and `inventory-8082` |
| Registry | Displays two instances under the same service ID |
| URI from order-service | Uses `http://inventory-service/...` |
| Registered address | Reachable from order-service's network |

## Common Configuration Mistakes

- **Setting different application names across replicas:** the registry creates two different service IDs; LoadBalancer calling one service ID will not see the other group of replicas.
- **Duplicate instance IDs:** the registry may overwrite, reject, or inaccurately display records. Generate a unique ID for each process.
- **Duplicate port on the same machine:** the second process cannot bind the socket and typically exits immediately on startup. Change `SERVER_PORT` or run in separate network namespaces.
- **Registering `localhost` inside a container:** a container's `localhost` is that container itself, not another container. Use service DNS, hostname, or an IP reachable from the caller.
- **Confusing instance ID with service ID:** instance ID identifies a single replica; clients still call using the shared service ID.
- **Configuring LoadBalancer without discovery:** LoadBalancer cannot know replica addresses on its own. You need a discovery provider or a static list for the lab.
- **Using the same default ID for every pod:** in container environments, derive the ID from the pod name or UID instead of just combining service name with the internal port.
- **Changing configuration without restarting the process:** environment variables and `application.yml` are loaded at application startup; re-check configuration logs and the registry after restarting.

## Completion Criteria

You complete this lesson when you can demonstrate that two `inventory-service` replicas share the same service ID, listen on valid endpoints, and have distinct instance IDs; the registry or discovery list shows both; `order-service` calls via service ID instead of a hardcoded address; and you can explain how configuration differs between running multiple processes on one machine and deploying multiple containers/pods.

These configurations are the foundation for upcoming lessons on `ServiceInstance` selection, health checks, retries, timeouts, and routing. If the service name, registered address, or instance identity is wrong, request distribution and error investigation in later steps will be inaccurate.
