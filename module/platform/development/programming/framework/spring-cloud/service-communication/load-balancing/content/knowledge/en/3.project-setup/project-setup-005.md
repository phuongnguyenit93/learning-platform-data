# Creating a Single-Caller, Multi-Replica Target Service Model

This hands-on lab sets up a small system to observe Spring Cloud LoadBalancer selecting a target service instance for each HTTP request. The model consists of one **caller-service** application and multiple **inventory-service** processes running the same codebase on different ports.

The caller invokes the service solely by its service ID `inventory-service`. The list of instance addresses is declared on the caller side via `SimpleDiscoveryClient`. Spring Cloud LoadBalancer retrieves that list and selects an instance before the HTTP client sends the request.

This model verifies three things: a service can have multiple instances serving the same API; the caller does not need to hardcode a single instance in code; and instance selection happens on the client side.

## 1. The Model to Build

We create two Spring Boot applications:

- **inventory-service** exposes an API to check inventory. Run the same JAR file as two processes: ports 8081 and 8082.
- **caller-service** exposes an API for users to call. This application uses `RestClient` integrated with Spring Cloud LoadBalancer to call the service ID `inventory-service`.

~~~mermaid
flowchart LR
    U["Client / Browser"] -->|"GET :8080/api/inventory/SKU-001"| C["caller-service :8080"]
    C --> LB["Spring Cloud LoadBalancer"]
    SD["SimpleDiscoveryClient<br/>inventory-service"] --> LB
    LB -->|"selects instance"| I1["inventory-service :8081"]
    LB -->|"or"| I2["inventory-service :8082"]
~~~

| Service ID | Instance | Address |
|---|---|---|
| `inventory-service` | Inventory 1 | `http://localhost:8081` |
| `inventory-service` | Inventory 2 | `http://localhost:8082` |

The two inventory processes share the same application name and the same API, but run on two different ports. They are two instances of the same service, not two separate source code modules.

In this lab, the instance list is declared statically so it is easy to run on a local machine. There is no need to set up Eureka Server or Consul. When moving to an environment with a service registry, the caller obtains the instance list from the registry instead of declaring addresses itself.

## 2. Preparing the Environment and Project Structure

You need JDK 17 or later, Maven 3.8 or later, an IDE or terminal, and a compatible pair of Spring Boot and Spring Cloud versions. RestClient requires Spring Framework 6.1 or later, which typically comes with Spring Boot 3.2 or later. Select a Spring Cloud release train compatible with your Spring Boot version according to the official Spring Cloud compatibility matrix. Do not arbitrarily combine Boot, Cloud, and Spring Framework versions.

Create a multi-module Maven project:

~~~text
spring-cloud-load-balancing-lab/
├── pom.xml
├── inventory-service/
│   ├── pom.xml
│   └── src/main/
│       ├── java/com/example/inventory/
│       │   ├── InventoryApplication.java
│       │   └── InventoryController.java
│       └── resources/application.yml
└── caller-service/
    ├── pom.xml
    └── src/main/
        ├── java/com/example/caller/
        │   ├── CallerApplication.java
        │   ├── api/InventoryResponse.java
        │   ├── client/InventoryClient.java
        │   ├── config/HttpClientConfiguration.java
        │   └── web/CallerController.java
        └── resources/application.yml
~~~

Each module is a Spring Boot application that can be packaged and run independently. The parent project manages shared versions and build order.

## 3. Declaring the Maven Parent and Dependencies

In the root `pom.xml`, declare `pom` packaging, the two submodules, and dependency management for Spring Cloud. The parent project must inherit from the Spring Boot parent with a specific version chosen from the compatibility matrix.

Module declarations and Spring Cloud BOM section:

~~~xml
<packaging>pom</packaging>

<modules>
    <module>inventory-service</module>
    <module>caller-service</module>
</modules>

<properties>
    <java.version>17</java.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>REPLACE_WITH_COMPATIBLE_SPRING_CLOUD_RELEASE_TRAIN</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

`REPLACE_WITH_COMPATIBLE_SPRING_CLOUD_RELEASE_TRAIN` is a placeholder. Replace it with a concrete release train version compatible with the project's Spring Boot parent before building.

The `inventory-service/pom.xml` module only needs the web starter:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

The `caller-service/pom.xml` module needs the web starter to expose the API and the LoadBalancer starter to resolve the service ID and select instances:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

The LoadBalancer dependency only needs to be on the caller in this model, because the caller is where instance selection takes place. The inventory instances only receive HTTP requests and therefore do not need that starter.

There is no need to add Eureka Client for this static lab. `SimpleDiscoveryClient` can supply the instance list from configuration. When replacing the discovery source with Eureka, Consul, or another platform, dependencies and service registration configuration will change accordingly.

## 4. Creating inventory-service

Startup class:

~~~java
package com.example.inventory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InventoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
~~~

API returning information about the instance handling the request:

~~~java
package com.example.inventory;

import java.util.Map;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/inventory")
public class InventoryController {

    private final String port;

    public InventoryController(Environment environment) {
        this.port = environment.getProperty("server.port", "8081");
    }

    @GetMapping("/{sku}")
    public Map<String, Object> getInventory(@PathVariable String sku) {
        return Map.of(
                "sku", sku,
                "available", 100,
                "instance", "inventory:" + port
        );
    }
}
~~~

The `instance` field helps identify which instance handled the request. In a real system, business responses normally do not need to expose internal ports; instance information should be observed through logs, metrics, or traces. In this lab, this field is strictly for verification.

Default configuration in `inventory-service/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8081

spring:
  application:
    name: inventory-service
~~~

When starting the second process, override the port via command-line arguments to 8082. Both processes use the same artifact and the same application configuration.

## 5. Creating caller-service and a Load-Balanced RestClient

Startup class:

~~~java
package com.example.caller;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CallerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CallerApplication.class, args);
    }
}
~~~

Declare a `RestClient.Builder` annotated with `@LoadBalanced`:

~~~java
package com.example.caller.config;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

The `@LoadBalanced` annotation marks the builder so Spring Cloud attaches the mechanism to resolve URIs containing a service ID. If you create a plain RestClient without this integration, the name `inventory-service` will be treated as a regular hostname and no instance selection from the discovery list will occur.

DTO receiving the response from inventory-service:

~~~java
package com.example.caller.api;

public record InventoryResponse(
        String sku,
        int available,
        String instance
) {
}
~~~

Service client calling the target service:

~~~java
package com.example.caller.client;

import com.example.caller.api.InventoryResponse;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryClient {

    private final RestClient restClient;

    public InventoryClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    public InventoryResponse getInventory(String sku) {
        return restClient.get()
                .uri("/api/inventory/{sku}", sku)
                .retrieve()
                .body(InventoryResponse.class);
    }
}
~~~

The base URL contains the service ID `inventory-service`, not port 8081 or 8082. The caller does not need to know which instance will handle the request. Choosing the instance is Spring Cloud LoadBalancer's responsibility.

External endpoint for test calls:

~~~java
package com.example.caller.web;

import com.example.caller.api.InventoryResponse;
import com.example.caller.client.InventoryClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/inventory")
public class CallerController {

    private final InventoryClient inventoryClient;

    public CallerController(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @GetMapping("/{sku}")
    public InventoryResponse getInventory(@PathVariable String sku) {
        return inventoryClient.getInventory(sku);
    }
}
~~~

The caller's endpoint shares the same business path so a tester only needs to call a single address. The request goes through the caller and is then forwarded to one of the inventory instances.

## 6. Declaring the Instance List on the Caller

In `caller-service/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: caller-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

This configuration declares two `ServiceInstance` entries belonging to the same service ID `inventory-service`. `SimpleDiscoveryClient` reads this list and provides it to Spring Cloud's discovery mechanism.

Three names should be distinguished:

- `caller-service` is the caller application's name.
- `inventory-service` is the service ID the caller uses to look up the target service.
- `localhost:8081` and `localhost:8082` are the physical addresses of the instances.

Do not hardcode instance URLs into `InventoryClient`. When scaling the number of replicas, update the discovery source or instance list configuration; the service-calling code continues using the service ID.

With a static list, operators must update addresses whenever instances are added or removed. This model is convenient for learning and running locally. Environments with autoscaling should use a service registry or orchestration platform to update instances automatically.

## 7. Building and Running the Three Processes

Open a terminal in the root directory `spring-cloud-load-balancing-lab` and build all modules:

~~~bash
mvn clean package
~~~

After the build succeeds, open three separate terminals.

Terminal 1 runs the first inventory instance:

~~~bash
java -jar inventory-service/target/inventory-service-1.0.0-SNAPSHOT.jar --server.port=8081
~~~

Terminal 2 runs the same JAR on port 8082:

~~~bash
java -jar inventory-service/target/inventory-service-1.0.0-SNAPSHOT.jar --server.port=8082
~~~

Terminal 3 runs the caller:

~~~bash
java -jar caller-service/target/caller-service-1.0.0-SNAPSHOT.jar
~~~

The JAR filename depends on `artifactId` and `version` in the POM. If the project uses a different version, substitute the exact filename generated in the `target` directory. You can run the applications using your IDE's Run configurations instead of `java -jar`, as long as each process uses a separate port.

Verify the two inventory instances directly:

~~~powershell
Invoke-RestMethod http://localhost:8081/api/inventory/SKU-001
Invoke-RestMethod http://localhost:8082/api/inventory/SKU-001
~~~

The results should have the same SKU and sample business data, while the `instance` field reports `inventory:8081` and `inventory:8082` respectively.

## 8. Verifying That the Caller Distributes Requests

Call the caller multiple times:

~~~powershell
1..8 | ForEach-Object {
    Invoke-RestMethod http://localhost:8080/api/inventory/SKU-001 |
        Select-Object sku, available, instance
}
~~~

Requests go through the caller and are routed by LoadBalancer to one of the two inventory instances. Under the default configuration, Spring Cloud LoadBalancer typically uses a Round Robin strategy, so repeated requests are distributed alternately across the instances remaining in the list.

Example observed output:

~~~text
sku      available instance
---      --------- --------
SKU-001  100       inventory:8081
SKU-001  100       inventory:8082
SKU-001  100       inventory:8081
SKU-001  100       inventory:8082
SKU-001  100       inventory:8081
SKU-001  100       inventory:8082
SKU-001  100       inventory:8081
SKU-001  100       inventory:8082
~~~

This illustrates the output for two healthy instances when requests are sent sequentially. In an environment with concurrent requests, retries, changing instance lists, or a different selection policy, the observed order may differ. What needs to be verified is that both instances can receive requests from the same caller via the service ID.

If you only see one instance, check these in order:

1. Both inventory processes have started and are listening on the correct ports.
2. Direct calls to both URLs 8081 and 8082 succeed.
3. The service ID in `baseUrl` matches the `inventory-service` key in discovery configuration exactly.
4. The `RestClient.Builder` bean is annotated with `@LoadBalanced`.
5. The caller has the `spring-cloud-starter-loadbalancer` dependency and was restarted after configuration changes.
6. No other configuration overrides the instance list or load balancing policy.

## 9. Testing Failures and Understanding Local Model Limitations

Try stopping the inventory process on port 8082, then continue calling the caller. The `SimpleDiscoveryClient` list still contains address 8082 because the list is statically declared. LoadBalancer can keep selecting that address, and requests will fail with connection errors.

This demonstrates that the discovery list and actual health status are two separate concerns. Declaring a URI in the list does not prove the instance is running. This lab does not yet configure health checks, retries, or a circuit breaker; add those mechanisms in their respective learning steps and observe the behavior when an instance fails.

Restart process 8082 and call again to confirm both instances respond normally. During testing, record the error timestamp, selected instance, and exception type to distinguish connection errors from HTTP or business errors.

Some limitations when running locally:

- `localhost` always points to the machine or network namespace of the calling process. If the caller runs in a container, `localhost:8081` is the caller container itself, not another inventory container. When using Docker Compose, declare addresses using service/container DNS names on the same network.
- Two instances cannot share the same port on the same host.
- The `SimpleDiscoveryClient` list does not automatically add or remove instances when processes start or stop.
- Both replicas in this lab share the same codebase and in-memory sample data. This is not yet a setup for shared databases or testing data consistency across multiple replicas.
- Load balancing distributes requests to instances. It does not by itself handle timeouts, retries, circuit breakers, authentication, or distributed transactions.

## 10. Extending the Model After It Runs Successfully

After verifying one caller calling multiple inventory instances, you can extend it step by step:

| Extension Step | Change | Goal |
|---|---|---|
| Add a third instance | Add port 8083 URI to the discovery list and run another process | Observe scaling by replica count |
| Use a service registry | Replace SimpleDiscoveryClient with Eureka or Consul | Dynamic instance registration and discovery |
| Switch HTTP client | Integrate WebClient or OpenFeign with LoadBalancer | Compare imperative, reactive, and declarative calling styles |
| Add timeouts/retries | Configure on the HTTP client and Spring Cloud LoadBalancer as needed | Bound wait times and handle transient errors |
| Add health checks | Filter unhealthy instances out of the selectable list | Avoid sending requests to unresponsive instances |
| Add observability | Log and collect metrics and traces for service ID, instance, latency, and status | Investigate request distribution and real errors |

When switching to WebClient or OpenFeign, the service ID remains the logical name of the target service. The corresponding integration mechanism uses the `ServiceInstance` list to select an address. Each client has its own configuration and return types, but the boundary between discovery and instance selection remains the same.

The single-caller, multi-replica model establishes the foundation for practicing Spring Cloud LoadBalancer. The caller depends only on the service ID; discovery supplies the instances; LoadBalancer chooses an instance; the HTTP client sends the request to the chosen address. Once this flow is clear, you can swap discovery sources, add replicas, and layer on fault-tolerance policies without putting physical instance addresses into business code.
