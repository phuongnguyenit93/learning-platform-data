# Running the Registry and Multiple Service Versions with Docker Compose

A microservice application typically has multiple instances providing the same service. Instances may be updated per version, restarted, or scaled up and down. Consumers need to call the service by its logical name instead of hardcoding IP addresses and ports of individual containers.

This lesson sets up a local lab environment using Docker Compose consisting of one Eureka Server, two versions of an inventory service, and one consumer. Both providers register under the same serviceId `inventory-service`, but have different instance IDs and application versions. The consumer calls `http://inventory-service`; Spring Cloud LoadBalancer queries the registry, selects an instance, and forwards the request to that container's network address.

This environment helps test configuration, Docker networking, service registration, and routing across multiple instances. It is a lab for learning and verifying integration, not a complete production configuration.

## 1. Checking Versions and Dependencies Before Running

Spring Boot and Spring Cloud are released in version lines with compatibility relationships. Before setting up the registry, choose a Spring Boot version and a Spring Cloud release train from the official Spring Cloud compatibility matrix. All modules in the lab should use the same release train to avoid providers and consumers loading different library versions.

Use the Spring Cloud BOM to manage dependency versions:

~~~groovy
plugins {
    id 'io.spring.dependency-management' version '<dependency-management-plugin-version>'
}

ext {
    // Replace with a release train compatible with your project's Spring Boot.
    set('springCloudVersion', '<compatible-spring-cloud-release-train>')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}
~~~

Key dependencies by role:

| Application | Required Dependency | Purpose |
|---|---|---|
| Eureka Server | `spring-cloud-starter-netflix-eureka-server` | Runs the registry |
| Inventory provider | `spring-cloud-starter-netflix-eureka-client` | Registers instance and communicates with the registry |
| Order consumer | `spring-cloud-starter-netflix-eureka-client` | Looks up the registry |
| Order consumer | `spring-cloud-starter-loadbalancer` | Selects an instance for calls by serviceId |
| Applications needing health endpoints | `spring-boot-starter-actuator` | Exposes health status for observation and checks |

A consumer using `WebClient` also needs `spring-boot-starter-webflux`. If using `RestClient` or `RestTemplate`, choose the web starter matching your application stack.

Example dependencies for Eureka Server:

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-server'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Example dependencies for provider and consumer:

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-client'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Add LoadBalancer and WebFlux dependencies in the consumer module if the application uses `@LoadBalanced WebClient.Builder`:

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Do not assign individual versions to Spring Cloud starters once the BOM is imported. Do not mix starters from multiple release trains. If you encounter missing classes, incompatible methods, or non-working auto-configuration, check the dependency tree and Boot/Cloud versions before modifying code.

## 2. Lab Environment Model

The lab has four roles:

- `eureka-server`: the registry that receives registrations and returns instance lists.
- `inventory-v1`: the first version of the provider, registering under `inventory-service`.
- `inventory-v2`: the second version of the same provider, also registering under `inventory-service`.
- `order-service`: the consumer calling inventory via serviceId and LoadBalancer.

~~~mermaid
flowchart TB
    subgraph DockerCompose["Docker Compose network: discovery"]
        E["eureka-server:8761"]
        V1["inventory-v1<br/>serviceId: inventory-service<br/>version: v1"]
        V2["inventory-v2<br/>serviceId: inventory-service<br/>version: v2"]
        O["order-service<br/>consumer"]
        V1 -->|"register / heartbeat"| E
        V2 -->|"register / heartbeat"| E
        O -->|"fetch registry"| E
        O -->|"LoadBalancer selects instance"| V1
        O -->|"LoadBalancer selects instance"| V2
    end
    Browser["Host browser / terminal"] -->|"localhost:8761"| E
    Caller["Host client"] -->|"localhost:8082"| O
~~~

Both providers share the same serviceId so the consumer treats them as instances of one service. Each instance has its own instance ID so the registry distinguishes the processes. The `APP_VERSION` field is metadata or a value returned by a version endpoint; it does not automatically create a separate serviceId.

Containers connect to the same Docker bridge network. Docker Compose provides internal DNS by service name, so providers and consumers can locate Eureka Server using the hostname `eureka-server`. Inside a container, `localhost` always points to that container itself. Do not configure the consumer to call `localhost:8761` to reach the registry, as that address points to the consumer itself.

An illustrative directory structure:

~~~text
service-discovery-lab/
├── compose.yaml
├── eureka-server/
│   ├── Dockerfile
│   └── Eureka Server application
├── inventory-v1/
│   ├── Dockerfile
│   └── version 1 source code
├── inventory-v2/
│   ├── Dockerfile
│   └── version 2 source code
└── order-service/
    ├── Dockerfile
    └── consumer application
~~~

Each Dockerfile must package the corresponding application into an image runnable in a container. The two inventory directories can be two checkouts or two build artifacts from different revisions. If you only use the exact same source code and change the `APP_VERSION` variable, the lab simulates two instances with different version labels rather than proving two genuinely distinct release binaries.

## 3. Configuring Eureka Server

Eureka Server is a Spring Boot application with the `spring-cloud-starter-netflix-eureka-server` dependency. Enable the server via annotation:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;

@SpringBootApplication
@EnableEurekaServer
public class EurekaServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(EurekaServerApplication.class, args);
    }
}
~~~

`application.yml` configuration:

~~~yaml
spring:
  application:
    name: eureka-server

server:
  port: 8761

eureka:
  client:
    register-with-eureka: false
    fetch-registry: false

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Eureka Server does not need to register itself with its own registry in this standalone lab. Both `register-with-eureka` and `fetch-registry` are set to `false` to clearly represent a single-registry role.

The default dashboard is reachable from the host at `http://localhost:8761` if Compose publishes port 8761. The Actuator health endpoint is used in the Compose health check; ensure the image includes `curl` if using the exact health check command below.

## 4. Configuring the Provider to Register the Right Container Address

Both provider versions share the same base configuration:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: 8080

eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:http://localhost:8761/eureka/}
    healthcheck:
      enabled: true
  instance:
    prefer-ip-address: true
    instance-id: ${spring.application.name}:${HOSTNAME:local}:${random.value}

management:
  endpoints:
    web:
      exposure:
        include: health,info

app:
  version: ${APP_VERSION:local}
~~~

In Compose, environment variables override the default values:

- `SPRING_APPLICATION_NAME=inventory-service` makes both providers register under the same serviceId.
- `EUREKA_CLIENT_SERVICEURL_DEFAULTZONE` points to `http://eureka-server:8761/eureka/`.
- `EUREKA_INSTANCE_PREFER_IP_ADDRESS=true` tells Eureka to advertise the IP address the container uses on the network.
- `EUREKA_INSTANCE_INSTANCE_ID` provides a distinct ID for each container.
- `APP_VERSION` indicates which build the application is running.

The address Eureka advertises must be reachable from the consumer. If a provider registers `localhost`, a host-only address, or a hostname unresolvable inside the Docker network, the registry may still show the instance while real requests fail.

Do not set a fixed `container_name` for providers if you plan to scale the service. Each container needs its own identity; duplicate instance IDs can cause one registration to overwrite or mask another.

## 5. Declaring the Full Lab in Docker Compose

Create `compose.yaml` in the root directory:

~~~yaml
name: spring-cloud-discovery-lab

services:
  eureka-server:
    build: ./eureka-server
    ports:
      - "8761:8761"
    environment:
      SPRING_APPLICATION_NAME: eureka-server
      SERVER_PORT: "8761"
      EUREKA_CLIENT_REGISTER_WITH_EUREKA: "false"
      EUREKA_CLIENT_FETCH_REGISTRY: "false"
      MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE: health,info
    healthcheck:
      test:
        - CMD-SHELL
        - curl -fsS http://localhost:8761/actuator/health >/dev/null || exit 1
      interval: 10s
      timeout: 3s
      retries: 12
      start_period: 25s
    networks:
      - discovery

  inventory-v1:
    build: ./inventory-v1
    environment:
      SPRING_APPLICATION_NAME: inventory-service
      SERVER_PORT: "8080"
      APP_VERSION: v1
      EUREKA_CLIENT_SERVICEURL_DEFAULTZONE: http://eureka-server:8761/eureka/
      EUREKA_INSTANCE_PREFER_IP_ADDRESS: "true"
      EUREKA_INSTANCE_INSTANCE_ID: inventory-service-v1
    depends_on:
      eureka-server:
        condition: service_healthy
    networks:
      - discovery

  inventory-v2:
    build: ./inventory-v2
    environment:
      SPRING_APPLICATION_NAME: inventory-service
      SERVER_PORT: "8080"
      APP_VERSION: v2
      EUREKA_CLIENT_SERVICEURL_DEFAULTZONE: http://eureka-server:8761/eureka/
      EUREKA_INSTANCE_PREFER_IP_ADDRESS: "true"
      EUREKA_INSTANCE_INSTANCE_ID: inventory-service-v2
    depends_on:
      eureka-server:
        condition: service_healthy
    networks:
      - discovery

  order-service:
    build: ./order-service
    ports:
      - "8082:8080"
    environment:
      SPRING_APPLICATION_NAME: order-service
      SERVER_PORT: "8080"
      EUREKA_CLIENT_SERVICEURL_DEFAULTZONE: http://eureka-server:8761/eureka/
      EUREKA_INSTANCE_PREFER_IP_ADDRESS: "true"
    depends_on:
      eureka-server:
        condition: service_healthy
    networks:
      - discovery

networks:
  discovery:
    driver: bridge
~~~

Key points to understand in the Compose file:

1. `build` points to the directory containing each application's Dockerfile. The two providers can be built from two different revisions.
2. Only the registry and consumer ports are published to the host in this example. Providers still listen on port 8080 inside the Docker network; there is no need to occupy two identical host ports.
3. `eureka-server` is an internal hostname resolved by Docker DNS. Consumer and providers use this hostname to reach the registry.
4. `depends_on: condition: service_healthy` waits for Eureka Server's health check to succeed before starting dependent services.
5. Each provider has its own instance ID in the example. When scaling multiple replicas of the same service, remove this static ID and use an ID generated from the hostname or a unique value.
6. The health check uses `curl`; the Eureka Server image needs `curl` and the Actuator health endpoint exposed. If the image lacks `curl`, replace it with a tool available in the image or another suitable health check.

`depends_on` only resolves startup ordering and Eureka Server's readiness condition. It does not guarantee that providers have finished registering before the consumer receives requests. The consumer still needs to handle moments when the registry has no instances yet, using bounded timeouts and retries.

If you want to access each provider directly from the host for debugging, you can publish different host ports, such as `18081:8080` for v1 and `18082:8080` for v2. These are only debug ports; service-to-service calls must still go through serviceId to test discovery and load balancing.

## 6. Calling by serviceId from the Consumer

The consumer also needs to connect to Eureka to query the registry. `order-service`'s configuration in Compose already provides the service URL. In Spring, declare a load-balanced WebClient builder:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

The consumer calls the serviceId:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Component
public class InventoryClient {

    private final WebClient webClient;

    public InventoryClient(
            @LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    public Mono<String> getInventoryVersion() {
        return webClient.get()
                .uri("http://inventory-service/api/version")
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

To test calling from the host through order-service, expose a small endpoint forwarding the call:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/inventory")
public class InventoryController {

    private final InventoryClient inventoryClient;

    public InventoryController(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @GetMapping("/version")
    public Mono<String> version() {
        return inventoryClient.getInventoryVersion();
    }
}
~~~

In the URI, `inventory-service` is the logical name. Spring Cloud LoadBalancer fetches the instances for that serviceId, applies an instance selection policy, and sends the request to the actual host and port. If you use a WebClient without `@LoadBalanced`, the hostname `inventory-service` may be resolved as a standard DNS hostname instead of being looked up via Eureka.

The provider's `/api/version` endpoint should return version details for easy observation, for example:

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class VersionController {

    @Value("${app.version:local}")
    private String version;

    @GetMapping("/api/version")
    public Map<String, String> version() {
        return Map.of(
                "service", "inventory-service",
                "version", version,
                "container", System.getenv().getOrDefault("HOSTNAME", "local"));
    }
}
~~~

The response from v1 may look like this:

~~~json
{
  "service": "inventory-service",
  "version": "v1",
  "container": "<container-id>"
}
~~~

Provider v2 returns `version: v2` and its own instance ID. When sending multiple requests through the consumer, responses may arrive from v1 and v2 in turn according to the LoadBalancer policy. Request distribution does not promise an equal count of v1/v2 in every short sequence of requests; it also depends on the instance list, registry refresh timing, caching, and selection policy.

## 7. Starting and Verifying the Environment

Run the following commands in the directory containing `compose.yaml`:

~~~bash
# Validate Compose configuration after variable interpolation
docker compose config

# Build images and start the entire lab
docker compose up --build -d

# View container status
docker compose ps

# Follow logs of the registry and providers
docker compose logs -f eureka-server inventory-v1 inventory-v2
~~~

Once Eureka Server is ready:

1. Open `http://localhost:8761` on the host.
2. Locate the application/instance list section on the dashboard.
3. Confirm `INVENTORY-SERVICE` is present with two distinct instance IDs.
4. Confirm `ORDER-SERVICE` is registered if the consumer is configured for auto-registration.
5. Call the consumer endpoint at `http://localhost:8082/api/inventory/version`.
6. Send multiple requests to the consumer endpoint calling inventory and observe the `version` or `instanceId` field in responses/logs.

If only one instance appears, check the logs of the other provider, its serviceId, Eureka URL, and instance ID. If the dashboard shows two instances but requests only go to one version, inspect the LoadBalancer policy, cache, and health status of the instances.

You can view logs for an individual service:

~~~bash
docker compose logs --tail=100 inventory-v1
docker compose logs --tail=100 inventory-v2
docker compose logs --tail=100 order-service
~~~

When finishing the lab:

~~~bash
docker compose down
~~~

This command stops and removes the containers and network created by Compose. If you added volumes storing lab data, only remove volumes once you are certain no data needs to be retained.

## 8. Scaling Instances and Deploying Versions

Two distinct operations must be differentiated:

- **Scaling the same version:** increasing the number of containers running the same image, e.g., scaling up to three v1 instances. The containers must register under the same serviceId with different instance IDs.
- **Running multiple versions:** deploying two different images or revisions, e.g., v1 and v2, while still registering under the same serviceId if you want LoadBalancer to distribute requests across them.

You can scale a service in Compose with:

~~~bash
docker compose up -d --scale inventory-v1=3
~~~

Do not use a fixed `container_name` and do not bind the same host port for all replicas. Each container uses the same internal port 8080 but gets its own IP on the bridge network. When scaling, do not use a static instance ID like the v1/v2 example; configure a unique ID derived from the hostname or a unique container identifier. You can use the fallback configuration `instance-id: ${spring.application.name}:${HOSTNAME:local}:${random.value}` in `application.yml` and remove environment variables overriding a static ID.

If you want v1 and v2 to be two real releases, build two images from the two corresponding revisions and configure two Compose services pointing to the respective image tags. Do not use the same image while only changing the `APP_VERSION` label and conclude you have tested a version upgrade. During rolling updates, test API and data compatibility between the consumer and both old and new versions.

Having multiple versions under one serviceId at the same time also means the consumer can send requests to any healthy instance in the list. If the APIs between v1 and v2 are incompatible, you need a separate version-based, canary, or blue/green routing strategy; basic service discovery does not guarantee protocol compatibility on its own.

## 9. Common Issues When Running in Docker

| Symptom | Common Cause | Resolution |
|---|---|---|
| Provider cannot connect to Eureka | Using `localhost:8761` inside the container | Use `http://eureka-server:8761/eureka/` |
| Eureka does not display the provider | Wrong serviceId, wrong registry URL, or client has not finished starting | Check environment variables and registration logs |
| Dashboard shows instance, but HTTP times out | Provider advertises an IP/hostname unreachable from the consumer | Check shared network and registered instance address |
| Two containers overwrite each other in the registry | Duplicate instance ID | Generate a unique ID per hostname/container |
| Consumer calls v1 successfully but never sees v2 | v2 not registered, failed health check, or different serviceId | Compare configuration and status of both providers |
| Compose reports unhealthy check | Image lacks `curl`, Actuator does not expose health, or app is not ready | Install an appropriate probe tool and inspect registry logs |
| Consumer starts before any instance exists | Registry is healthy, but provider has not registered yet | Use bounded retries, handle empty lists, and check readiness |
| Scaling fails with port bind error | Multiple replicas publish the same fixed host port | Use internal ports only or configure separate host ports for debugging |

When investigating, proceed from the outside in: is the container running, are both containers on the same network, does internal DNS resolve, did the provider register under the right serviceId, does the registry return the instance, and can the consumer connect to the instance address. This sequence helps pinpoint whether the fault lies in Docker, the registry, or the HTTP client.

## 10. Health Checks, Security, and Lab Limitations

Docker Compose health checks inspect the process or endpoint you configure. Eureka health checks and instance status in the registry serve instance selection. The two mechanisms are related but do not replace each other. A container can be healthy according to Docker before the application registers with Eureka; an instance can remain in the registry for some time after the process has died.

In real environments, you need to:

- Design health/readiness endpoints that accurately reflect request-handling capacity and critical dependencies.
- Configure timeouts, bounded retries, and circuit breakers on the consumer where appropriate.
- Protect the registry with network policies, authentication, ACLs, and TLS per your deployment model.
- Never expose the registry dashboard or management APIs to the public Internet.
- Never bake passwords, tokens, or secrets into images or commit them in Compose files; use a secret store or the environment's secret management mechanism.
- Monitor instance counts, registrations/deregistrations, heartbeats, health status, and inter-service connection errors.
- Design a highly available registry and evaluate behavior when the registry temporarily loses connectivity.

The lab above runs a single Eureka Server, making the registry a single point of failure. The sample registry also has no authentication configured and should only run in local development environments. For Consul, replace the registry service image/configuration with a Consul agent/server and configure corresponding health checks; the principles of Docker DNS, shared networks, serviceId, and reachable instance addresses remain the same.

## 11. Completion Checklist

Before considering the environment working properly, verify each item:

1. Spring Boot and Spring Cloud release train are compatible; modules share the BOM.
2. Eureka Server starts up and passes its health check.
3. Providers v1 and v2 register under the same serviceId `inventory-service`.
4. Each provider has a distinct instance ID and an address reachable from the consumer.
5. Consumer registers successfully and retrieves the instance list.
6. Consumer calls via `@LoadBalanced` using serviceId, without hardcoded IPs or container names.
7. Responses coming from different versions can be observed.
8. When stopping one provider, the registry and consumer gradually reflect the change according to heartbeat, health check, and cache cycles.
9. When restarting a provider, the new instance re-registers without leaving persistent duplicate records.

Once these steps work, the lab flow is complete: Docker Compose creates the network and containers; providers register their serviceId and instance metadata with Eureka; the consumer looks up the serviceId; Spring Cloud LoadBalancer selects an instance; and the HTTP client sends requests to the chosen instance's network address.
