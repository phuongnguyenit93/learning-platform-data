# Using Discovery or Static Lists in Docker Compose

When deploying microservices with **Docker Compose**, containers can find one another over **internal DNS** using a service name such as `catalog-service`. However, that **does not mean** Spring Cloud LoadBalancer already has a list of `ServiceInstance` entries from which to pick replicas. Depending on your architecture, you can:

1. Declare a **static instance list** with `SimpleDiscoveryClient`, for example `catalog-a:8081` and `catalog-b:8081`.
2. Use a **dynamic service registry** such as Eureka/Consul so each container registers, updates, and leaves the instance list.
3. Call the **Compose DNS service name** directly and let Docker/networking or a proxy decide how to connect; in that case you may **not be using Spring Cloud LoadBalancer**.

This lesson in the **Deployment** chapter practices the first two options while clearly explaining the third. The scope is **client-side** Spring Cloud LoadBalancer using `RestClient` to call `catalog-service` from `order-service`, verifying discovery, health/failures, caching, and HTTP transport boundaries. The same knowledge applies to `WebClient` and OpenFeign when integrated properly.

> All examples are for local/dev environments. Before applying them to production, evaluate registry authentication, TLS, readiness/health, multi-host orchestration, resource limits, and recovery plans. Compose is convenient for labs/small setups, and does not provide the full feature set of an orchestration platform on its own.

## 1. Distinguishing three layers: Compose DNS, DiscoveryClient, and LoadBalancer

Suppose `order-service` wants to call `GET /whoami` on a `catalog-service` replica.

~~~mermaid
flowchart TD
    A["order-service<br/>RestClient: http://catalog-service/whoami"]
    B["Spring Cloud LoadBalancer<br/>selects ServiceInstance"]
    C["DiscoveryClient / InstanceListSupplier"]
    D["Static list or Eureka registry"]
    E["HTTP transport<br/>pool, DNS, TCP, timeout"]
    F["catalog instance A"]
    G["catalog instance B"]
    A --> B
    B <--> C
    C <--> D
    B --> E
    E --> F
    E --> G
~~~

In the diagram, **one request selects only one instance**; it is not sent simultaneously to both A and B. LoadBalancer picks a physical URI before HTTP transport executes.

| Component | Responsibility | Does not do automatically |
|---|---|---|
| **Compose internal DNS** | Lets containers resolve service/container names on the network to IPs | Does not populate Spring's `DiscoveryClient` list |
| **`SimpleDiscoveryClient`** | Returns the `ServiceInstance` list declared via properties | Does not know when a container dies or a new replica starts |
| **Eureka/Consul** | Tracks registrations/deregistrations and returns instances via registry protocol | Does not guarantee every change is visible to clients immediately |
| **`ServiceInstanceListSupplier`** | Fetches/optionally caches, filters, and orders the instance list | Does not execute TCP or decode responses |
| **Spring Cloud LoadBalancer** | Selects one `ServiceInstance` from the list | Does not replace connection pools, timeouts, retries, or authorization |
| **HTTP transport** | Resolves physical hostname if needed, borrows from pool, TCP/TLS, sends HTTP | Does not enforce discovery policies if LB is not attached |

Remember that the following two URLs **may look similar yet pass through different layers**:

~~~java
// Built from @LoadBalanced RestClient.Builder:
// "catalog-service" is a service ID used by Spring Cloud LoadBalancer.
RestClient clientSideLb = lbBuilder
        .baseUrl("http://catalog-service")
        .build();

// Plain RestClient:
// "catalog-service" is a hostname for DNS/HTTP transport.
RestClient directDns = RestClient.create("http://catalog-service:8081");
~~~

A Compose DNS hostname can resolve to multiple containers when a service is scaled. However, DNS caching, connection reuse, and network-level behavior mean actual distribution **is not equivalent to round-robin decided by Spring Cloud LoadBalancer**.

## 2. Static list or dynamic registry?

| Criterion | Static list / SimpleDiscoveryClient | Dynamic registry / Eureka |
|---|---|---|
| Target use | Local/dev, few instances, rarely changing topology | Many replicas, frequent scaling/recreation |
| Extra services | No registry server needed | Must deploy and operate a registry |
| Service ID name | Defined by caller in config | Registered by the app against the registry |
| Adding/removing instances | Edit config and reload/redeploy accordingly | Instances register/deregister; callers refresh periodically |
| Container IP changes on recreate | Use **stable DNS names** instead of fixed IPs | Registry must advertise reachable new IP/hostname |
| Health/liveness | No dynamic up/down state by default | Registry has lease/health semantics, with propagation delay |
| Independent testability | Very high, easy to reproduce | Needs a registry or fake registry |
| Risks | Stale list, unaware of scaling | Registry dependency, lease/cache lag, bad instance registration |
| Complexity | Low | Medium to high |

**Pragmatic rule:** start with a static list if you only have two stably named backends in Compose. Move to a registry when you need **membership changes without editing lists in every caller**. Do not add Eureka just to "have a service name" if Docker DNS already satisfies operational needs and you do not need client-side selection.

## 3. Lab model and source setup

We build a lab repository with three optional modules:

~~~text
compose-loadbalancer-demo/
├── settings.gradle.kts
├── compose-static.yml
├── compose-eureka.yml
├── catalog-service/
│   ├── Dockerfile
│   ├── build.gradle.kts
│   └── src/main/
│       ├── java/com/example/catalog/
│       │   ├── CatalogApplication.java
│       │   └── CatalogController.java
│       └── resources/
│           ├── application.yml
│           ├── application-compose-static.yml
│           └── application-compose-eureka.yml
├── order-service/
│   ├── Dockerfile
│   ├── build.gradle.kts
│   └── src/main/
│       ├── java/com/example/orders/
│       │   ├── OrderApplication.java
│       │   ├── CatalogClientConfiguration.java
│       │   └── ProbeController.java
│       └── resources/
│           ├── application.yml
│           ├── application-compose-static.yml
│           └── application-compose-eureka.yml
└── eureka-server/
    ├── Dockerfile
    ├── build.gradle.kts
    └── src/main/
        ├── java/com/example/registry/EurekaServerApplication.java
        └── resources/application-compose-registry.yml
~~~

**`eureka-server` is only needed for the dynamic registry option.** If running only the static list, you do not need to start this module.

### Dependencies and versions

The Gradle Kotlin DSL snippets below illustrate key dependencies. The root project must configure repositories, plugin versions, and a **Spring Cloud BOM compatible with Spring Boot**.

**catalog-service:**

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")

    // Needed for Eureka mode; disabled under the compose-static profile.
    implementation("org.springframework.cloud:spring-cloud-starter-netflix-eureka-client")
}
~~~

**order-service:**

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")

    // Included in the same artifact to test registry mode.
    implementation("org.springframework.cloud:spring-cloud-starter-netflix-eureka-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

**eureka-server:**

~~~kotlin
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-netflix-eureka-server")
}
~~~

In each module, produce a bootable jar with a predictable filename so the Dockerfile copies it cleanly. Example for `catalog-service`:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    archiveFileName.set("catalog-service.jar")
}
~~~

Similarly set `order-service.jar` and `eureka-server.jar` in the other two modules. Choose a JDK matching your dependencies; the Dockerfile later uses Java 21. **Do not assume all Spring Boot/Spring Cloud versions support the same Java/runtime versions**; verify against the release train compatibility matrix.

## 4. Shared catalog-service code for both options

### 4.1. Spring Boot application

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

### 4.2. Endpoint showing which instance handled the call

~~~java
package com.example.catalog;

import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CatalogController {

    private final String instanceId;

    CatalogController(
            @Value("${demo.instance-id:}") String configuredId) {

        this.instanceId = configuredId == null
                || configuredId.isBlank()
                ? UUID.randomUUID().toString().substring(0, 8)
                : configuredId;
    }

    @GetMapping("/whoami")
    CatalogReply whoami() {
        return new CatalogReply(instanceId, "catalog-service");
    }

    record CatalogReply(String instanceId, String service) {}
}
~~~

In the static option, the two containers pass `DEMO_INSTANCE_ID=catalog-a` and `catalog-b`. In the Eureka option, if no ID is supplied, the app generates a short value **per process**, enough to tell responses apart in the lab.

This is solely a debug endpoint. Do not expose internal topology or unnecessary instance identifiers in production APIs.

### 4.3. catalog's application.yml

~~~yaml
spring:
  application:
    name: catalog-service

server:
  port: 8081
~~~

All replicas **listen on port 8081 inside their containers**. Containers have separate network namespaces, so there is no need to change `server.port` to 8082 when scaling. Ports on the host (if published) are a separate concept.

## 5. order-service code calling via Spring Cloud LoadBalancer

### 5.1. Application

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

### 5.2. Load-balanced RestClient

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogClientConfiguration {

    @Bean("catalogLbBuilder")
    @LoadBalanced
    RestClient.Builder catalogLbBuilder() {
        return RestClient.builder();
    }

    @Bean("catalogClient")
    RestClient catalogClient(
            @Qualifier("catalogLbBuilder")
            RestClient.Builder builder) {
        return builder
                .baseUrl("http://catalog-service")
                .build();
    }
}
~~~

`@LoadBalanced RestClient.Builder` has an interceptor attached by Spring Cloud to resolve the **service ID**. That is what separates it from a plain `RestClient.create("http://catalog-service")`, which would go via DNS instead of Spring Cloud.

In Spring Boot applications with important observability/customizers, consider integrating `RestClientBuilderConfigurer` or a Boot-managed builder; this lab uses a minimal builder to illustrate the call path.

### 5.3. Probe endpoint

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
class ProbeController {

    private final RestClient catalog;

    ProbeController(
            @Qualifier("catalogClient") RestClient catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/probe/catalog")
    CatalogReply probe() {
        return catalog.get()
                .uri("/whoami")
                .retrieve()
                .body(CatalogReply.class);
    }

    record CatalogReply(String instanceId, String service) {}
}
~~~

When calling from the host:

~~~text
GET http://localhost:8080/probe/catalog

{"instanceId":"catalog-a","service":"catalog-service"}
~~~

The response above is **illustrative**: the chosen replica varies according to the LoadBalancer policy. Never hardcode an expectation that the first call always goes to `catalog-a`.

### 5.4. order's application.yml

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080
~~~

We will separate `compose-static` and `compose-eureka` configurations in later sections; do not declare both a static instance list and Eureka ambiguously in the same profile.

## 6. Dockerfile and building images

In each module, create a `Dockerfile` with the same contents, assuming the jar was built and named as in section 3:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
ARG JAR_FILE
COPY ${JAR_FILE} /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

The build contexts in Compose are `./catalog-service`, `./order-service`, and `./eureka-server`; hence `JAR_FILE` is resolved relative to each module. Do not use this Dockerfile before the jar is built.

From the project root directory:

~~~powershell
./gradlew :catalog-service:bootJar :order-service:bootJar
~~~

When testing Eureka, also build:

~~~powershell
./gradlew :eureka-server:bootJar
~~~

**Production note:** use version-tagged images, a non-root user, image scanning, secret management, and a controlled build pipeline. `eclipse-temurin:21-jre` works for demos but does not replace organizational image security policies.

## 7. Option A — Static list with SimpleDiscoveryClient

### 7.1. Docker Compose defining two separately named services

Create `compose-static.yml`:

~~~yaml
services:
  catalog-a:
    build:
      context: ./catalog-service
      args:
        JAR_FILE: build/libs/catalog-service.jar
    environment:
      SPRING_PROFILES_ACTIVE: compose-static
      DEMO_INSTANCE_ID: catalog-a
    expose:
      - "8081"

  catalog-b:
    build:
      context: ./catalog-service
      args:
        JAR_FILE: build/libs/catalog-service.jar
    environment:
      SPRING_PROFILES_ACTIVE: compose-static
      DEMO_INSTANCE_ID: catalog-b
    expose:
      - "8081"

  order-service:
    build:
      context: ./order-service
      args:
        JAR_FILE: build/libs/order-service.jar
    environment:
      SPRING_PROFILES_ACTIVE: compose-static
    ports:
      - "127.0.0.1:8080:8080"
    depends_on:
      - catalog-a
      - catalog-b
~~~

Compose creates a shared internal network by default. From the `order-service` container:

- `catalog-a` is the DNS hostname of Compose service `catalog-a`.
- `catalog-b` is the DNS hostname of Compose service `catalog-b`.
- Both open **container port 8081** with no conflict.
- Only `order-service` is published to the host on localhost port 8080.

`expose` primarily documents internal ports; on the default Compose network, containers on the same network can connect to listening ports **without publishing** ports to the host. `expose` does not open a host port.

### 7.2. Disable Eureka client in static mode

Because the Eureka client dependency is packaged in the jar for Option B, disable it in the static profile.

In `catalog-service/src/main/resources/application-compose-static.yml`:

~~~yaml
eureka:
  client:
    enabled: false
~~~

In `order-service/src/main/resources/application-compose-static.yml`:

~~~yaml
eureka:
  client:
    enabled: false

spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://catalog-a:8081
              - uri: http://catalog-b:8081
    loadbalancer:
      cache:
        enabled: false
      retry:
        enabled: false
~~~

This is the core configuration:

~~~text
serviceId = "catalog-service"

ServiceInstance 1: uri=http://catalog-a:8081
ServiceInstance 2: uri=http://catalog-b:8081
~~~

Spring Cloud LoadBalancer retrieves **this list** when the caller uses service ID `catalog-service`. **Docker DNS only resolves the physical hostnames** `catalog-a` and `catalog-b` at the HTTP transport step; it does not populate the two items for `SimpleDiscoveryClient`.

`spring.cloud.loadbalancer.cache.enabled=false` and `retry.enabled=false` are choices for a **single-attempt observation lab**, not a recommendation to disable both mechanisms in production. If the project has retries at another layer, control them separately.

### 7.3. Running static mode

After building the jars:

~~~powershell
docker compose -f compose-static.yml up -d --build
docker compose -f compose-static.yml ps
~~~

Send a request from the **host**:

~~~powershell
curl.exe -s http://127.0.0.1:8080/probe/catalog
~~~

Repeat with PowerShell:

~~~powershell
1..12 | ForEach-Object {
    (Invoke-RestMethod "http://127.0.0.1:8080/probe/catalog").instanceId
}
~~~

When both backends are running and no other policy applies, standard round-robin typically brings both `catalog-a` and `catalog-b` into the observed results. Do not require a strict A-B-A-B sequence or exact ratio over a small number of requests.

**Point to verify:** the response `instanceId` alternates between the two values while the caller always invokes the same logical URL `http://catalog-service` in Java code.

## 8. Failure experiments with the static list

### 8.1. Stop one replica

~~~powershell
docker compose -f compose-static.yml stop catalog-a
~~~

Then call `/probe/catalog` multiple times again. Notice:

- `catalog-a` remains an entry in `spring.cloud.discovery.client.simple.instances.catalog-service`.
- When LoadBalancer selects A, the HTTP client may encounter `Connection refused`, connect timeout, or a network error depending on the scenario.
- When B is selected, the request can still succeed.
- Because LoadBalancer retries are disabled, a request that picked A is not automatically retried against B.

**Stopping a container does not edit the caller's YAML.** Nor does `cache.enabled=false` shrink the discovery list down to one instance: the data source is still static.

### 8.2. Remove A from the list

Edit `application-compose-static.yml` in the **lab project**:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://catalog-b:8081
~~~

After rebuilding the order jar and recreating the container:

~~~powershell
./gradlew :order-service:bootJar
docker compose -f compose-static.yml up -d --build --force-recreate order-service
~~~

Now the caller knows only B. Editing a YAML file baked into a jar **does not automatically take effect in a running container**; you must repackage/redeploy or have an explicitly designed config refresh mechanism.

### 8.3. When is a static list good enough?

- Two or a few instances with **stable service DNS names**.
- Membership does not change frequently.
- Lab/integration test environments needing reproducible results.
- An operations team controls config changes and redeployments.
- Single-instance outages are handled by another layer or fit the SLA.

If replicas are added or removed frequently, updating lists in every caller is tedious and error-prone with stale data; that is when to consider a dynamic registry.

## 9. Do not confuse a static list with Compose DNS load balancing

In a Compose project with a service:

~~~yaml
services:
  catalog-service:
    build: ./catalog-service
    expose:
      - "8081"
~~~

and running `docker compose up --scale catalog-service=2`, Docker may return the container addresses of those replicas when a caller resolves hostname `catalog-service` via DNS.

Yet if the caller creates:

~~~java
RestClient dnsClient =
        RestClient.create("http://catalog-service:8081");
~~~

then the caller is using **DNS-layer resolution**; Spring Cloud LoadBalancer **is not proven to be involved**. DNS responses, JVM/HTTP resolver caches, connection keep-alive, and how multiple DNS records are consumed govern connection behavior. **No 50/50 distribution is guaranteed** from DNS.

Conversely, with:

~~~java
RestClient lbClient = catalogLbBuilder
        .baseUrl("http://catalog-service")
        .build();
~~~

Spring Cloud must have a **real `ServiceInstanceListSupplier`** for the service ID. Compose DNS knowing hostname `catalog-service` does not mean the supplier has a list of individual replicas.

### Why shouldn't container IPs be listed in a static list?

Docker assigns IPs dynamically. When a container is recreated, it may get a different address. A configuration like:

~~~yaml
# Not recommended:
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://172.20.0.7:8081
              - uri: http://172.20.0.8:8081
~~~

can break after recreation. Use stable Compose service/container network names when choosing a static list, or use a registry to store live endpoints.

## 10. Option B — Eureka as a dynamic registry

When you want to run multiple replicas of the **same Compose service**, instead of manually declaring `catalog-a` and `catalog-b` in the caller, use Eureka.

~~~mermaid
flowchart TD
    E["eureka-server:8761<br/>Service Registry"]
    A["catalog-service replica 1<br/>:8081"]
    B["catalog-service replica 2<br/>:8081"]
    O["order-service:8080"]
    LB["Spring Cloud LoadBalancer"]
    A -->|"register / heartbeat"| E
    B -->|"register / heartbeat"| E
    O --> LB
    LB -->|"DiscoveryClient fetches instances"| E
    LB -->|"selects 1 instance"| A
    LB -->|"or selects"| B
~~~

**Benefits:** the caller does not need two hardcoded URIs. Each catalog instance advertises its own address, and the Eureka client in the caller fetches the registered list.

**Trade-offs:** you must operate a registry, ensure instances advertise a host/IP **reachable from the caller**, handle non-instant updates, and plan for registry outages and transport security.

### 10.1. Eureka Server code

In `eureka-server/src/main/java/com/example/registry/EurekaServerApplication.java`:

~~~java
package com.example.registry;

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

`eureka-server/src/main/resources/application-compose-registry.yml`:

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
~~~

This is a **single-node registry for labs**. In production, design availability, dashboard access control, authentication/TLS, self-preservation/leases, and recovery plans rather than leaving an unprotected single registry.

### 10.2. Configuring catalog self-registration

In `catalog-service/src/main/resources/application-compose-eureka.yml`:

~~~yaml
spring:
  application:
    name: catalog-service

server:
  port: 8081

eureka:
  client:
    service-url:
      defaultZone: http://eureka-server:8761/eureka/
  instance:
    prefer-ip-address: true
    instance-id: "${spring.application.name}:${random.uuid}"
~~~

`eureka-server` is the **Compose service name**, with a DNS record on the default network. `prefer-ip-address: true` tells the Eureka client to advertise the IP rather than hostname upon registration. This lets the caller connect directly to each container IP on the same Compose network, provided that IP is actually reachable.

`instance-id` is made unique per JVM using Spring Boot's random value. It prevents two replicas from colliding on the same registration ID; it is not a health mechanism or persistent identity across restarts.

**Do not use `localhost:8761` in a container's Eureka URL**, because `localhost` there is the catalog container itself, not the registry container.

### 10.3. Configuring order to fetch instances from Eureka

In `order-service/src/main/resources/application-compose-eureka.yml`:

~~~yaml
eureka:
  client:
    service-url:
      defaultZone: http://eureka-server:8761/eureka/
    register-with-eureka: false
    fetch-registry: true

spring:
  cloud:
    loadbalancer:
      retry:
        enabled: false
      cache:
        enabled: false
~~~

In this mode **do not declare** `spring.cloud.discovery.client.simple.instances.catalog-service`. Eureka supplies the real `DiscoveryClient`, and LoadBalancer consumes discovery data via the supplier.

`register-with-eureka: false` on `order-service` simply illustrates that a caller does not need to be discovered by other services. It **can still fetch the registry** to call catalog.

Note: the Eureka client has its own registry list cache. Disabling LoadBalancer's cache in the lab does not clear the Eureka client's cache; account for fetch/refresh delays when observing failover.

## 11. Docker Compose for Eureka and scaling a single service

Create `compose-eureka.yml`:

~~~yaml
services:
  eureka-server:
    build:
      context: ./eureka-server
      args:
        JAR_FILE: build/libs/eureka-server.jar
    environment:
      SPRING_PROFILES_ACTIVE: compose-registry
    ports:
      - "127.0.0.1:8761:8761"

  catalog-service:
    build:
      context: ./catalog-service
      args:
        JAR_FILE: build/libs/catalog-service.jar
    environment:
      SPRING_PROFILES_ACTIVE: compose-eureka
    expose:
      - "8081"
    depends_on:
      - eureka-server

  order-service:
    build:
      context: ./order-service
      args:
        JAR_FILE: build/libs/order-service.jar
    environment:
      SPRING_PROFILES_ACTIVE: compose-eureka
    ports:
      - "127.0.0.1:8080:8080"
    depends_on:
      - eureka-server
      - catalog-service
~~~

**Do not set `container_name` on `catalog-service`**. Docker Compose cannot scale a service beyond one container when a fixed `container_name` is set.

**Do not publish** `"8081:8081"` on the host for catalog replicas in this mode: two containers cannot share host port 8081. Each container still listens internally on 8081 and Eureka advertises the corresponding endpoint.

`depends_on` in its basic form mainly orders startup/shutdown; **it does not prove Eureka or catalog is ready to serve HTTP**. In the lab, allow time for registration sync and retry requests. Real systems need health/readiness and controlled startup/retry policies.

### Run commands

First stop static mode if running to avoid colliding on host port 8080:

~~~powershell
docker compose -f compose-static.yml down
~~~

Build the jars:

~~~powershell
./gradlew :catalog-service:bootJar :order-service:bootJar :eureka-server:bootJar
~~~

Start the registry, caller, and **two catalog replicas**:

~~~powershell
docker compose -f compose-eureka.yml up -d --build --scale catalog-service=2
docker compose -f compose-eureka.yml ps
~~~

Check the Eureka dashboard at `http://127.0.0.1:8761` in the local lab, or watch registry logs. Wait until Eureka shows two `CATALOG-SERVICE` instances and the caller has fetched the list.

Call the caller from the host:

~~~powershell
curl.exe -s http://127.0.0.1:8080/probe/catalog
~~~

Repeat:

~~~powershell
1..20 | ForEach-Object {
    (Invoke-RestMethod "http://127.0.0.1:8080/probe/catalog").instanceId
}
~~~

Two distinct `instanceId` values prove two backend processes served requests. Do not assert strict alternation or an exact 50/50 split under all conditions.

## 12. Why must each replica have the right ID and address?

For LoadBalancer to call each instance, the registry must contain:

~~~text
serviceId = catalog-service

instance-1:
  instanceId = catalog-service:<unique-id-1>
  host/IP    = <reachable-container-ip-1>
  port       = 8081

instance-2:
  instanceId = catalog-service:<unique-id-2>
  host/IP    = <reachable-container-ip-2>
  port       = 8081
~~~

In Eureka mode:

- `spring.application.name=catalog-service` supplies the service name for registration.
- `instance-id` distinguishes replicas that share app name and port.
- `prefer-ip-address` advertises the container IP; critically, **that IP must be reachable from order-service on the same network**.
- `server.port=8081` is the port the process actually listens on inside the container.

### A common registration mistake

A catalog container registers `localhost:8081` or an unsuitable published host port. The Eureka dashboard may show the instance as "UP", yet the caller connects to its own `localhost` and gets `Connection refused`.

**The registry knowing an instance exists does not mean the advertised endpoint is reachable from the caller.** Inspect the actual returned instance addresses, not just the count on the dashboard.

When deploying across multiple hosts/networks, a container IP on one Compose bridge network may no longer be reachable from another host. In that case you need a suitable topology or proper address advertising/routing; `prefer-ip-address=true` does not magically solve cross-network routing.

## 13. Practicing scale-down, scale-up, and discovery latency

In Eureka mode currently running two replicas:

~~~powershell
docker compose -f compose-eureka.yml up -d --scale catalog-service=1
~~~

Compose reduces the service's container count as requested. Once the registry receives deregistration or lease/refresh updates, the caller will see **only one** remaining valid instance.

Run:

~~~powershell
docker compose -f compose-eureka.yml ps
docker compose -f compose-eureka.yml logs --tail=100 catalog-service
~~~

Observe over time intervals:

1. Number of running containers in Compose.
2. Number of instances shown by Eureka.
3. Number of instances returned by order-service's `DiscoveryClient`.
4. `instanceId` values appearing in `/probe/catalog` responses.
5. Connection error count while an old URI has not yet been fully evicted.

Then scale back up:

~~~powershell
docker compose -f compose-eureka.yml up -d --scale catalog-service=2
~~~

Do not expect **instantaneous changes**. Multiple independent delays apply: app startup, Eureka registration, heartbeat/lease, registry fetch, and client/LoadBalancer caching.

### Stale instances and retries

Right after a replica stops, the caller may still select the old URI and fail. Enabling retries can help in some transient scenarios, yet it:

- Cannot fix a wrongly registered address.
- Does not guarantee whether the server processed the request if the response was lost.
- Does not make the registry update immediately.
- Can multiply HTTP attempts and increase load if unbounded.
- For `POST` uploads/writes, requires evaluating idempotency and request-body replayability.

In the lab we turned off LB retries to distinguish discovery errors from retry behavior. Production needs timeouts, conditional retries, backoff, overall deadlines, and proper observability.

## 14. Health checks, readiness, and Docker Compose startup dependencies

Three kinds of health have different meanings:

| Mechanism | What does it check? | Limitations |
|---|---|---|
| Docker container running | Whether the process/container is running | Does not guarantee the app is ready to serve HTTP |
| Compose healthcheck | Whether the healthcheck command succeeds | Requires proper probe design and tooling inside the image |
| Eureka registration/lease | Client registration and status updates | Takes time to detect; can go stale |
| Spring Cloud LB health supplier | Polls instance health endpoints when configured | Has its own interval and fallback semantics |
| Backend readiness | App can serve requests and required dependencies are ready | Must reflect real business conditions |

Operational notes:

- Spring Boot Actuator `/actuator/health` and controlled healthchecks can be used, provided dependencies and configs are added properly.
- Plain `depends_on` does not wait for a service to become "ready"; when using `condition: service_healthy`, the dependency must define a working healthcheck.
- Probes must not leak credentials or internal metadata.
- When a backend prepares to shut down, stop accepting traffic, deregister/mark out-of-service appropriately, and drain in-flight requests within a deadline.
- Do not rely solely on `HealthCheckServiceInstanceListSupplier` to enforce hard constraints: when no healthy instances remain, the built-in supplier can **fall back to the source list** depending on configuration/version.

### Compose healthcheck example (conditional)

A `/actuator/health` healthcheck using `curl` works only if the image contains curl. Minimal Java runtime images may **have neither curl nor wget**. Therefore, do not copy a shell healthcheck without verifying the image; use a probe tool already present or an image-compatible check.

If the healthcheck relies on Actuator, add `spring-boot-starter-actuator` and verify the endpoint is enabled. **Do not treat a Docker healthcheck as the sole proof that discovery has evicted an instance.**

## 15. WebClient and OpenFeign in both modes

### WebClient

~~~java
@Bean
@LoadBalanced
WebClient.Builder lbWebClientBuilder() {
    return WebClient.builder();
}

@Bean
WebClient catalogWebClient(
        @LoadBalanced WebClient.Builder builder) {
    return builder.baseUrl("http://catalog-service").build();
}
~~~

Requires Spring WebFlux and the matching LoadBalancer starter. Across both static and Eureka modes, **the logical URL stays unchanged**; only the `ServiceInstance` source swaps by profile.

Reactor Netty connection pools are maintained by the HTTP transport, typically bounded per remote host/pool. This is **not** Spring Cloud LoadBalancer's instance list; multiple replicas can have separate physical connection pools.

### OpenFeign

~~~java
@FeignClient(name = "catalog-service")
interface CatalogFeign {
    @GetMapping("/whoami")
    CatalogReply whoami();
}
~~~

With `@EnableFeignClients`, compatible OpenFeign starter, and LoadBalancer starter, Feign by service ID picks instances via `DiscoveryClient`. However, if you set `@FeignClient(url=...)` or a fixed URL via property, Feign connects directly to that URL without service-name instance selection as in the example.

For Feign, verify `connectTimeout`, `readTimeout`, and the HTTP transport separately. Do not assume adding Eureka automatically enables retries or tunes connection pools.

## 16. Variant: calling Compose DNS directly instead of Spring Cloud LoadBalancer

If an application only needs to call a single **virtual endpoint** and Docker Compose DNS satisfies all requirements, you can omit `DiscoveryClient` and `@LoadBalanced`.

Example in the Eureka Compose mode where a `catalog-service` service exists:

~~~java
RestClient directByComposeDns =
        RestClient.create("http://catalog-service:8081");
~~~

The client delegates name resolution to the HTTP transport via Compose DNS. Docker may resolve a scaled service name to multiple container addresses, yet:

- The JVM/DNS resolver caches entries; IP ordering is not a distribution contract.
- Connection pools/keep-alive may continue reusing an old connection.
- There is no Spring Cloud `ServiceInstanceListSupplier`/zone/hint/weight on this call path.
- Replica failure handling and reconnection depend on the HTTP client, Docker networking, and retry policies.
- `127.0.0.1:8081` inside the order container **does not point to catalog**.

**Choose clear ownership:** either client-side LB selects instances from discovery, or DNS/gateway/mesh owns the virtual target. Avoid mixing two layers accidentally without knowing where requests flow.

## 17. Common error matrix in Docker Compose

| Symptom | Primary suspect | Check |
|---|---|---|
| `UnknownHostException: catalog-service` on plain call | DNS lacks that name on the network or client is on wrong network | Service names, networks, and actual URL |
| `No instances available for catalog-service` | LoadBalancer received no list from discovery/supplier | Profile, static config/Eureka fetch |
| `catalog-a` does not resolve | Wrong service name, container on different network | `docker compose ps`, Compose service names |
| Caller calls `localhost:8081` and fails | Localhost is the order container itself | Use `catalog-a:8081` or URIs from Eureka |
| Dead A still picked occasionally | Static list or stale Eureka/LoadBalancer cache | Compare registry list, refresh, and HTTP errors |
| Eureka dashboard shows instance yet caller fails to connect | Registry advertises unreachable host/IP/port | Check prefer-IP, port, and network |
| Scaling catalog service reports host port error | Fixed host port published on scaled service | Remove `ports: "8081:8081"` on replicas |
| Scaling fails due to `container_name` | Fixed container name forbids multiple replicas | Remove `container_name` |
| `depends_on` present yet caller fails at startup | Registry/backend not yet ready | Health/readiness, bounded startup retries |
| Static mode tries to connect to Eureka | Eureka client still enabled in static profile | `eureka.client.enabled=false` |
| Dynamic mode picks only one instance | Only one UP registration, duplicate instance ID, cache/health/filter | Compare Compose replicas, Eureka registry, and caller |
| DNS works yet LB metrics are missing | Client taking direct DNS path | Verify `@LoadBalanced` builder/filter |
| Responses change yet JVM reuses old socket | Connection pooling/keep-alive | Inspect HTTP transport, idle eviction |
| WebClient/Feign distributes differently from RestClient | Different adapters/filters or fixed URL | Check each client's bean and config |

Do not diagnose every error as "Docker DNS." If LoadBalancer already returned a `ServiceInstance` with IP/port and the backend returned 500, that may be a backend bug or HTTP contract issue.

## 18. Observing the instance list in a controlled way

In a lab environment, you can add an endpoint **enabled only under test profiles** to see which URIs the caller knows about:

~~~java
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile({"compose-static", "compose-eureka"})
class InstanceDiagnosticsController {

    private final DiscoveryClient discoveryClient;

    InstanceDiagnosticsController(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @GetMapping("/lab/instances")
    List<String> catalogInstances() {
        return discoveryClient
                .getInstances("catalog-service").stream()
                .map(ServiceInstance::getUri)
                .map(Object::toString)
                .toList();
    }
}
~~~

When running `compose-static`, expected output (order not guaranteed):

~~~json
[
  "http://catalog-a:8081",
  "http://catalog-b:8081"
]
~~~

When running `compose-eureka`, the output may contain two URIs with **container IPs** on port 8081. Results update as Eureka refreshes the registry/client cache.

**Security:** do not expose `/lab/instances` in production: it can leak topology, internal URIs, and system metadata. For production investigations, use telemetry or controlled administrative access.

### Three places to cross-check

1. **Compose:** how many containers are currently alive?
2. **Registry/SimpleDiscoveryClient:** which URIs does the caller currently know?
3. **HTTP execution:** do response `instanceId` values or server traces confirm which replica actually received requests?

If these three observations disagree, determine whether registration delay, caching, proxies, routing policies, or HTTP connection reuse caused it before changing timeouts.

## 19. Integration testing across both configurations

Tests can share the same assertion set while swapping only how instances are supplied.

### Tests for the static profile

- Application context builds `@LoadBalanced RestClient.Builder` properly.
- `SimpleDiscoveryClient` returns the two URIs `catalog-a` and `catalog-b` (or equivalent mock servers).
- Backends A/B return distinct IDs; across multiple calls both appear in results.
- When the source contains only B, A is never picked.
- When one backend stops while the source is unchanged, the test proves errors can happen and does not assume automatic failover.

### Tests for the Eureka profile

- Two catalog replicas register **two distinct instance IDs**.
- Caller fetches the registry successfully and sees reachable URIs.
- Scale-down/up updates the candidate list **after a refresh interval**, without asserting a rigid millisecond threshold.
- Eureka outages are observed, without assuming the client immediately loses all ability to call backends (cached entries may remain).
- No fallback to disallowed regions/services when hard policies apply.

### Organizing the test pyramid

| Test type | Suggested tools | What it proves |
|---|---|---|
| Unit | JUnit, fake `ServiceInstanceListSupplier` | Selection and fallback logic |
| Static integration | `@SpringBootTest`, fake HTTP servers, `@DynamicPropertySource` | LB wiring and real HTTP |
| Registry integration | Testcontainers/Eureka test stack | Registration/deregistration and lookup |
| Load/smoke | k6 or similar through order-service | Distribution, latency, pools, retries under load |
| Failure test | Stop/recreate a backend in test | Stale discovery, timeouts, retries, and recovery |

For load tests, **send requests through the caller** `/probe/catalog`. Hitting backends directly measures only servers and fails to verify client-side LoadBalancer. Record request counts per instance, not just total duration.

## 20. Controlled migration guide from static to Eureka

A clean migration plan separates the **instance list source** from **business code**:

1. Ensure `order-service` calls by service ID via `@LoadBalanced RestClient.Builder` starting in static mode.
2. Add the Eureka starter to the relevant apps and configure Eureka server on the same network.
3. Register catalog replicas with app name `catalog-service`, unique instance IDs, and reachable endpoints.
4. Create a `compose-eureka` profile **without a static list**, and enable Eureka fetching on the caller.
5. Compare URIs from `DiscoveryClient` against the Eureka dashboard and verify `/probe/catalog`.
6. Practice scale-down/up, monitoring update latency, error rates, retry amplification, and connection pools.
7. Test failures and profile rollback in a test environment.
8. Before production, secure the registry, monitor leases/health, enforce access controls, and set resource limits.

Calling code:

~~~java
catalog.get()
       .uri("/whoami")
       .retrieve()
       .body(CatalogReply.class);
~~~

**Requires no changes** when switching from static to Eureka, because the same `catalog-service` service ID is resolved by a different discovery source.

### When not to migrate

If Docker Compose DNS/gateway is already chosen as the virtual endpoint, replica count is small, and callers have no per-instance selection needs, keeping a direct DNS client can be simpler. **Do not deploy two discovery layers just to look like a large microservices architecture.**

## 21. Security, networking, and real-world operations

In Compose labs, components typically sit on one default network. For serious deployments, mind:

- **Network scope:** do not expose databases/registries on public networks unnecessarily.
- **Registry authentication/TLS:** Eureka/Consul dashboards and registration APIs expose topology and must enforce access control.
- **Service credentials:** use secret management rather than hardcoding passwords/tokens in Compose YAML or logs.
- **Container identity:** never assume durable IPs; rely on service names/registries and design for recreation.
- **Image security:** pin image versions, scan dependencies, run non-root when feasible.
- **Health/readiness:** separate "process running" from "HTTP dependencies ready"; configure graceful shutdown.
- **Observability:** record service ID, selected instance, error category, and latency; avoid logging `Authorization`, cookies, raw URLs, or sensitive response bodies.
- **Retry/timeouts:** bound attempts, backoff, and overall deadlines; tune to capacity and idempotency semantics.
- **Caching:** account for both registry client caching and LoadBalancer caching; double caching increases staleness.
- **Host vs. container ports:** internal Compose calls target the **container port**, not host-published ports as default URIs.

A single-node Eureka in Option B can become a single point of failure in the lab. Production requires high availability, backup/recovery, and suitable orchestration platforms or managed registry services rather than simply scaling a Compose file.

## 22. Acceptance checklist

Before concluding this lab, verify:

1. Did you distinguish Compose DNS, Spring `DiscoveryClient`, and Spring Cloud LoadBalancer?
2. Is the client genuinely built from `@LoadBalanced RestClient.Builder`, not a plain DNS RestClient?
3. Does static mode define two Compose services `catalog-a` and `catalog-b` on container port 8081?
4. Does `SimpleDiscoveryClient` return URIs using **service names** rather than fixed container IPs?
5. Does the static profile disable the Eureka client when the jar includes the Eureka starter?
6. Does stopping A leave A's URI in the static list as expected?
7. Are static list edits paired with proper reload/redeployment?
8. Does Eureka mode have two catalog replicas registered with **distinct instance IDs**?
9. Does Eureka advertise an address/port reachable by the caller inside the Compose network?
10. Can `catalog-service` scale with `--scale catalog-service=2` without `container_name` or host port conflicts?
11. During scale-down, did you observe registry/client refresh lag and errors from stale instances?
12. Is `depends_on` properly understood not to replace readiness?
13. Is instance distribution verified from responses/metrics rather than inferred from hostnames?
14. Are retries, timeouts, health, connection pools, and idempotency separated from discovery?
15. Are debug endpoints and registry dashboards restricted from production exposure?

**Conclusion:** In Docker Compose, you can use **`SimpleDiscoveryClient` with a static `catalog-a`/`catalog-b` list** for fast setup and verifying `ServiceInstance` selection; or add **Eureka** so replicas self-register and callers refresh lists via the registry. **Docker Compose DNS does not turn into a Spring Cloud `DiscoveryClient` on its own**, and Spring Cloud LoadBalancer **does not replace HTTP transport, timeouts, retries, or health/readiness**. Choose the approach matching your replica churn, availability targets, operational budget, and how much control you need over request routing.

**Official references:**

- [Docker Docs – Networking in Compose](https://docs.docker.com/compose/how-tos/networking/)
- [Docker Docs – Compose services, container_name and scaling](https://docs.docker.com/reference/compose-file/services/)
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Commons – RestClient as a LoadBalancer Client](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Netflix – Eureka Client and Server](https://docs.spring.io/spring-cloud-netflix/docs/current/reference/html/)
