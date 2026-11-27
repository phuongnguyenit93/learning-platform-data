# Setting Up Eureka and Two Services to Observe the Full Discovery Cycle

## Practice Objectives

In this lesson, you will set up a Eureka Server and two Spring Boot microservices:

- **catalog-service:** a service providing catalog data; runs two instances on two different ports.
- **order-service:** a service consuming catalog; registers itself with Eureka, queries instances using DiscoveryClient, and calls catalog via Spring Cloud LoadBalancer.
- **eureka-server:** stores the registry, receives registrations/heartbeats, and provides the list of instances to clients.

After completing this, you can observe the entire flow:

1. Eureka Server starts on port 8761.
2. Two catalog instances register under the same service ID but with different instance IDs.
3. order-service registers with Eureka and fetches the list of catalog instances.
4. DiscoveryClient returns the list of ServiceInstance objects.
5. Spring Cloud LoadBalancer selects one instance when order-service makes a call using the service name.
6. When one catalog instance stops, its registration is canceled or expires, and the consumer updates its list.

This practice uses a Maven multi-module project so that the three applications share a single version management configuration. They can be split into three independent repositories once you understand how they work.

## 1. Architecture and Discovery Flow

~~~~mermaid
flowchart LR
    subgraph Registry
      E[Eureka Server :8761]
    end

    subgraph Providers
      C1[catalog-service :8081]
      C2[catalog-service :8082]
    end

    subgraph Consumer
      O[order-service :8090]
      D[DiscoveryClient]
      L[Spring Cloud LoadBalancer]
    end

    C1 -- register / heartbeat --> E
    C2 -- register / heartbeat --> E
    O -- register / heartbeat --> E
    O --> D
    D -- read registry cache --> E
    O --> L
    L -- choose one instance --> C1
    L -- choose one instance --> C2
~~~~

Both catalog instances share the same spring.application.name=catalog-service, so they belong to the same service ID. Each instance must have its own address, port, and instance ID. Eureka does not execute business requests on behalf of the provider; it supplies information so the consumer can find an appropriate address.

There are two distinct operations on the order-service side:

- **Direct discovery:** call DiscoveryClient.getInstances("catalog-service") to inspect the instance list.
- **Calling by service name:** send an HTTP request to http://catalog-service/...; Spring Cloud LoadBalancer selects one instance and forwards the request to the real address.

DiscoveryClient returns discovery information. LoadBalancer selects an instance for the request. These two roles are related, but they are not a single API.

## 2. Choosing Compatible Versions

This practice uses the current GA version stack at the time of writing:

| Component | Version |
| --- | --- |
| Java | 21 |
| Spring Boot | 4.2.0 |
| Spring Cloud Release Train | 2026.0.0 |
| Spring Cloud Netflix | 5.1.0 |
| Build | Maven |

Spring Cloud 2026.0.0 is released based on Spring Boot 4.2.0. This release train manages Spring Cloud Netflix 5.1.0 and Spring Cloud Commons 5.1.0. Use the BOM to manage dependencies rather than specifying separate versions for each starter. If your project is using Spring Boot 3.5.x, choose the corresponding compatible release train instead of mixing Boot 3.x with Cloud 2026.0.0.

Boot 4 has split several starters. This example uses spring-boot-starter-webmvc for REST APIs and spring-boot-starter-restclient for the synchronous HTTP client. The Eureka client in Spring Cloud Netflix 5.1.0 uses RestClient as the default HTTP client when the appropriate dependency is present.

Version documentation:

- [Spring Cloud 2026.0.0 release announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Cloud release train compatibility](https://docs.spring.io/spring-cloud-release/reference/index.html)
- [Spring Cloud Netflix reference](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)

## 3. Creating the Maven Multi-Module Structure

Create a project directory with the following structure:

~~~~text
eureka-discovery-lab/
├── pom.xml
├── eureka-server/
│   ├── pom.xml
│   └── src/main/
│       ├── java/com/example/eurekaserver/
│       │   └── EurekaServerApplication.java
│       └── resources/
│           └── application.yml
├── catalog-service/
│   ├── pom.xml
│   └── src/main/
│       ├── java/com/example/catalog/
│       │   ├── CatalogServiceApplication.java
│       │   ├── CatalogController.java
│       │   └── CatalogResponse.java
│       └── resources/
│           └── application.yml
└── order-service/
    ├── pom.xml
    └── src/main/
        ├── java/com/example/order/
        │   ├── OrderServiceApplication.java
        │   ├── LoadBalancedClientConfiguration.java
        │   ├── OrderController.java
        │   ├── CatalogResponse.java
        │   └── DiscoveredInstance.java
        └── resources/
            └── application.yml
~~~~

### 3.1. Root POM

The pom.xml file manages the Spring Boot version, imports the Spring Cloud BOM, and declares the three modules:

~~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.2.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>eureka-discovery-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>eureka-server</module>
        <module>catalog-service</module>
        <module>order-service</module>
    </modules>

    <properties>
        <java.version>21</java.version>
        <spring-cloud.version>2026.0.0</spring-cloud.version>
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
</project>
~~~~

### 3.2. Eureka Server POM

File eureka-server/pom.xml:

~~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>eureka-discovery-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>eureka-server</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-restclient</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-netflix-eureka-server</artifactId>
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
</project>
~~~~

### 3.3. catalog-service POM

File catalog-service/pom.xml:

~~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>eureka-discovery-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>catalog-service</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-restclient</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
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
</project>
~~~~

### 3.4. order-service POM

File order-service/pom.xml:

~~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>eureka-discovery-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>order-service</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-restclient</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
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
</project>
~~~~

## 4. Building Eureka Server

Eureka Server is a Spring Boot application with the spring-cloud-starter-netflix-eureka-server starter and the @EnableEurekaServer annotation.

File EurekaServerApplication.java:

~~~~java
package com.example.eurekaserver;

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
~~~~

File eureka-server/src/main/resources/application.yml:

~~~~yaml
server:
  port: 8761

spring:
  application:
    name: eureka-server

eureka:
  client:
    register-with-eureka: false
    fetch-registry: false

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~~

The two properties register-with-eureka and fetch-registry are set to false because this is a standalone Eureka Server for the lab. Eureka Server can also act as a Eureka Client to register with peers and fetch the registry. In standalone mode, disabling these two behaviors prevents the logs from continuously reporting peer lookup errors.

Once the server starts, open:

- Dashboard: http://localhost:8761/
- Health: http://localhost:8761/actuator/health
- Registry REST API: http://localhost:8761/eureka/apps

Initially, the dashboard will show no application instances. This is normal because the two service clients have not started yet.

## 5. Building catalog-service

### 5.1. Main class

File CatalogServiceApplication.java:

~~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogServiceApplication.class, args);
    }
}
~~~~

There is no need to add @EnableEurekaClient or @EnableDiscoveryClient for standard modern configurations. When the Eureka Client starter is on the classpath and discovery is enabled, Spring Cloud automatically configures the client and registers the application.

### 5.2. Response to Identify Each Instance

File CatalogResponse.java:

~~~~java
package com.example.catalog;

public record CatalogResponse(
        String service,
        String instance,
        int port,
        String message
) {
}
~~~~

File CatalogController.java:

~~~~java
package com.example.catalog;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogController {

    private final int port;

    public CatalogController(@Value("${server.port}") int port) {
        this.port = port;
    }

    @GetMapping("/catalog")
    public CatalogResponse getCatalog() {
        return new CatalogResponse(
                "catalog-service",
                "catalog-service:" + port,
                port,
                "Catalog response from this service instance"
        );
    }
}
~~~~

The response includes the port and instance ID so you can see which replica LoadBalancer is calling. In a real application, the controller would return catalog data from the domain/service layer; the instance field here is strictly for observation.

### 5.3. Eureka Registration Configuration

File catalog-service/src/main/resources/application.yml:

~~~~yaml
server:
  port: ${SERVER_PORT:8081}

spring:
  application:
    name: catalog-service

eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_URL:http://localhost:8761/eureka/}
  instance:
    instance-id: ${spring.application.name}:${server.port}

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~~

Meaning:

- spring.application.name is the service ID that consumers use to look up catalog.
- defaultZone is the URL of the Eureka Server. The key name defaultZone uses camel case because it is a key in the serviceUrl map; do not change it to default-zone.
- instance-id must differ across processes. Here the port is embedded in the ID so two replicas on the same machine do not overwrite each other.
- SERVER_PORT and EUREKA_URL allow overriding configuration via environment variables when running in another environment.

Eureka Client automatically registers the instance and sends periodic heartbeats. The registry stores the host, port, service ID, instance ID, and metadata for consumers to use.

## 6. Building order-service

order-service acts as both a Eureka client (registering itself) and a consumer (querying catalog-service).

### 6.1. Main class

File OrderServiceApplication.java:

~~~~java
package com.example.order;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderServiceApplication.class, args);
    }
}
~~~~

### 6.2. DTO for Receiving the catalog-service Response

File CatalogResponse.java in order-service:

~~~~java
package com.example.order;

public record CatalogResponse(
        String service,
        String instance,
        int port,
        String message
) {
}
~~~~

This is the DTO matching the JSON returned by catalog-service. Two independent services can share contracts via a dedicated API library in larger projects; this practice keeps the DTO inside each module to reduce the number of artifacts to create.

### 6.3. Creating a LoadBalanced RestClient

File LoadBalancedClientConfiguration.java:

~~~~java
package com.example.order;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class LoadBalancedClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~~

@LoadBalanced marks the builder so Spring Cloud attaches the client-side load balancing mechanism. When using this builder, URLs can contain a logical service ID instead of a real hostname.

For example:

~~~~text
http://catalog-service/catalog
~~~~

LoadBalancer retrieves the instance list from DiscoveryClient, picks a ServiceInstance, and resolves the logical URL to the host and port of the chosen instance.

### 6.4. Querying Directly with DiscoveryClient and Calling via LoadBalancer

File DiscoveredInstance.java:

~~~~java
package com.example.order;

import java.util.Map;

public record DiscoveredInstance(
        String serviceId,
        String instanceId,
        String host,
        int port,
        String uri,
        Map<String, String> metadata
) {
}
~~~~

File OrderController.java:

~~~~java
package com.example.order;

import java.util.List;
import java.util.stream.IntStream;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final DiscoveryClient discoveryClient;
    private final RestClient catalogClient;

    public OrderController(
            DiscoveryClient discoveryClient,
            @LoadBalanced RestClient.Builder builder) {
        this.discoveryClient = discoveryClient;
        this.catalogClient = builder.build();
    }

    @GetMapping("/discovery/catalog")
    public List<DiscoveredInstance> discoverCatalogInstances() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances("catalog-service");

        return instances.stream()
                .map(instance -> new DiscoveredInstance(
                        instance.getServiceId(),
                        instance.getInstanceId(),
                        instance.getHost(),
                        instance.getPort(),
                        instance.getUri().toString(),
                        instance.getMetadata()
                ))
                .toList();
    }

    @GetMapping("/catalog")
    public CatalogResponse callCatalog() {
        return catalogClient.get()
                .uri("http://catalog-service/catalog")
                .retrieve()
                .body(CatalogResponse.class);
    }

    @GetMapping("/catalog/sequence")
    public List<CatalogResponse> callCatalogSeveralTimes(
            @RequestParam(defaultValue = "8") int count) {

        if (count < 1 || count > 50) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "count must be between 1 and 50"
            );
        }

        return IntStream.range(0, count)
                .mapToObj(index -> callCatalog())
                .toList();
    }
}
~~~~

The three endpoints demonstrate the two usage patterns:

- /orders/discovery/catalog calls DiscoveryClient directly and returns the instance list.
- /orders/catalog calls by service ID through LoadBalancer.
- /orders/catalog/sequence?count=8 sends multiple sequential requests to observe which instances are chosen.

Spring Cloud LoadBalancer uses RoundRobinLoadBalancer by default. Therefore, with two healthy instances and an updated list, sequential requests typically alternate between the two ports. This is a client-side instance selection algorithm; it does not mean Eureka Server proxies the requests.

### 6.5. Configuring order-service

File order-service/src/main/resources/application.yml:

~~~~yaml
server:
  port: 8090

spring:
  application:
    name: order-service
  cloud:
    loadbalancer:
      cache:
        enabled: false

eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_URL:http://localhost:8761/eureka/}
  instance:
    instance-id: ${spring.application.name}:${server.port}

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~~

In this lab, Spring Cloud LoadBalancer's own cache is disabled so you can easily observe the list fetched from the Eureka client. The Eureka client already maintains a registry cache. In other systems, the LoadBalancer cache can be useful; consider avoiding stacking multiple cache layers and test convergence time when instances are updated.

## 7. Building the Three Applications

Open a terminal in the root directory eureka-discovery-lab.

Check Java and Maven:

~~~~powershell
java -version
mvn -version
~~~~

Build the entire reactor:

~~~~powershell
mvn clean package
~~~~

If the build succeeds, three executable JARs are produced:

~~~~text
eureka-server/target/eureka-server-1.0.0.jar
catalog-service/target/catalog-service-1.0.0.jar
order-service/target/order-service-1.0.0.jar
~~~~

If the project uses Maven Wrapper, on Windows you can run .\mvnw.cmd clean package; on macOS/Linux use ./mvnw clean package.

Do not specify separate versions for the Eureka starter or LoadBalancer starter in child POMs. The Spring Cloud BOM already manages them.

## 8. Starting in the Right Order

Open four separate terminals. Keep the processes running throughout observation.

### Terminal 1: Eureka Server

~~~~powershell
java -jar .\eureka-server\target\eureka-server-1.0.0.jar
~~~~

Wait for the Spring Boot log to report that the application has started, then open http://localhost:8761/.

### Terminal 2: First catalog-service Instance

~~~~powershell
java -jar .\catalog-service\target\catalog-service-1.0.0.jar --server.port=8081
~~~~

### Terminal 3: Second catalog-service Instance

~~~~powershell
java -jar .\catalog-service\target\catalog-service-1.0.0.jar --server.port=8082
~~~~

Both processes use the same JAR and the same service ID. The --server.port argument overrides the default port, and instance-id changes automatically based on the port.

### Terminal 4: order-service

~~~~powershell
java -jar .\order-service\target\order-service-1.0.0.jar --server.port=8090
~~~~

When order-service finishes starting, it also registers with Eureka. The dashboard will display the client applications.

## 9. Observing Registration in Eureka

Open the dashboard:

http://localhost:8761/

You will see applications such as:

- CATALOG-SERVICE: has two instances corresponding to ports 8081 and 8082.
- ORDER-SERVICE: has one instance on port 8090.

Eureka typically displays service IDs in uppercase. This is how the Eureka UI presents them; the configured name in Spring Boot remains catalog-service.

You can query the registry via the REST API:

~~~~powershell
Invoke-RestMethod -Uri "http://localhost:8761/eureka/apps" -Headers @{ Accept = "application/json" } | ConvertTo-Json -Depth 10
~~~~

View only the catalog application:

~~~~powershell
Invoke-RestMethod -Uri "http://localhost:8761/eureka/apps/CATALOG-SERVICE" -Headers @{ Accept = "application/json" } | ConvertTo-Json -Depth 10
~~~~

Or use curl:

~~~~bash
curl -H "Accept: application/json" \
  http://localhost:8761/eureka/apps/CATALOG-SERVICE
~~~~

Compare instanceId, hostName, ipAddr, port, status, and metadata. If only one instance appears, check the logs of the second process and verify that the two instances do not share the same instance ID.

Registrations do not necessarily appear simultaneously in every cache. Eureka has heartbeats, a server response cache, and a client registry cache. After initial startup, wait for the synchronization cycles before concluding that a client failed to register.

## 10. Observing Instances Returned by DiscoveryClient

Call the endpoint exposed by order-service:

~~~~powershell
Invoke-RestMethod "http://localhost:8090/orders/discovery/catalog" | ConvertTo-Json -Depth 6
~~~~

The expected result is an array with two elements. Abbreviated example:

~~~~json
[
  {
    "serviceId": "CATALOG-SERVICE",
    "instanceId": "catalog-service:8081",
    "host": "127.0.0.1",
    "port": 8081,
    "uri": "http://127.0.0.1:8081",
    "metadata": {}
  },
  {
    "serviceId": "CATALOG-SERVICE",
    "instanceId": "catalog-service:8082",
    "host": "127.0.0.1",
    "port": 8082,
    "uri": "http://127.0.0.1:8082",
    "metadata": {}
  }
]
~~~~

The host may differ from 127.0.0.1 depending on the network interface advertised by Eureka Client. The two fields to observe are instanceId and port.

You can also call each provider directly to compare:

~~~~powershell
Invoke-RestMethod "http://localhost:8081/catalog"
Invoke-RestMethod "http://localhost:8082/catalog"
~~~~

If the two direct URLs return two different instances but DiscoveryClient only returns one instance, check the registration ID and registry fetch on order-service.

## 11. Observing Instance Selection by Spring Cloud LoadBalancer

Make a request through order-service:

~~~~powershell
Invoke-RestMethod "http://localhost:8090/orders/catalog"
~~~~

The URL used in code is http://catalog-service/catalog. There is no DNS hostname named catalog-service on the machine; the service ID is resolved by Spring Cloud LoadBalancer to a real instance.

Send multiple sequential requests:

~~~~powershell
1..10 | ForEach-Object {
    (Invoke-RestMethod "http://localhost:8090/orders/catalog").instance
}
~~~~

The output usually shows the two instance IDs catalog-service:8081 and catalog-service:8082 being selected alternately. The default algorithm is round-robin. If one instance is removed from the list, subsequent requests will select from the remaining instances.

Things to observe:

1. DiscoveryClient provides the instance list.
2. ServiceInstanceListSupplier supplies the list to LoadBalancer.
3. RoundRobinLoadBalancer selects one instance.
4. BlockingLoadBalancerClient rewrites the logical URL into a physical URL.
5. RestClient sends the request to the chosen host/port.

If you call http://localhost:8081/catalog directly, you bypass discovery and load balancing. That is a direct request, not a request via service ID.

## 12. Observing the Lifecycle When an Instance Stops

### 12.1. Graceful Shutdown

Select the terminal running catalog-service on port 8081 and press Ctrl+C. Spring Boot starts its shutdown lifecycle; Eureka Client gets a chance to send cancel/deregister to the server.

Afterward:

1. Open the Eureka dashboard and check the application status.
2. Query /eureka/apps/CATALOG-SERVICE again.
3. Call /orders/discovery/catalog to inspect the consumer's list.
4. Call /orders/catalog/sequence?count=10 to confirm requests still go to port 8082.

Data may take some time to propagate through the registry response cache and client fetch cache. Do not conclude a failure just because the consumer endpoint still sees the instance during the first few seconds.

### 12.2. Restarting the Instance

Run the catalog JAR on port 8081 again. Observe the registration reappearing and the consumer being able to call both instances once the registry/cache updates.

### 12.3. Abrupt Termination for Comparison

In a private lab environment, you can forcefully terminate a catalog-service process to observe the difference compared to graceful shutdown. When a process does not send cancel, Eureka relies on heartbeat leases and eviction to clean up the registration.

Common default settings are a heartbeat around 30 seconds and lease expiration around 90 seconds; actual values depend on configuration and version. Self-preservation may delay eviction when the server assumes heartbeats are being lost across a wide area. Therefore, a process crash does not mean the instance disappears immediately.

Do not disable self-preservation just to make a quick demo. In production, this mechanism protects the registry when a network partition prevents many healthy instances from sending heartbeats temporarily.

## 13. Observing Health Status in Eureka

By default, Eureka primarily uses heartbeats to determine whether a client is alive. If you want to propagate Spring Boot Actuator health status to Eureka, add this configuration to the provider's application.yml:

~~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~~

Keep the spring-boot-starter-actuator dependency and the health endpoint active. When an application's health status is other than UP, Eureka can receive the corresponding status and consumers can filter out non-UP instances.

Only enable this configuration after understanding your application's composite health indicator. A failing auxiliary dependency can change the overall health status and cause the instance to be removed from traffic. Do not place this property in bootstrap.yml; Spring Cloud Netflix documentation requires placing it in application.yml.

## 14. Troubleshooting Common Errors

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Eureka dashboard does not open | Server has not started or port 8761 is occupied. | Check server logs, processes, and ports. |
| Client does not appear in Eureka | Wrong URL, wrong service ID, or connection error. | Check defaultZone, Eureka client logs, and call the server URL from the client process. |
| Client repeatedly logs inability to connect to Eureka | Wrong defaultZone, server not running, or network unreachable. | Verify http://localhost:8761/eureka/ and the trailing /eureka/. |
| Two catalog processes running but UI shows only one instance | Duplicate instance ID or one process failed to register. | Include the port in eureka.instance.instance-id; check logs for each process. |
| DiscoveryClient returns an empty list | Incorrect spring.application.name, client hasn't fetched registry yet, or registry not synced. | Compare the service ID in the UI and call /orders/discovery/catalog after waiting for a fetch. |
| UnknownHostException: catalog-service | Request uses a plain RestClient without @LoadBalanced or missing LoadBalancer starter. | Check the RestClient.Builder bean, qualifier, and dependencies. |
| Consumer calls wrong host/port | Provider advertises an address unreachable by the consumer. | Check host, port, prefer-ip-address, and network topology. |
| Old instance remains in registry after killing process | Lease not expired yet, self-preservation active, or caches not updated. | Check heartbeat, eviction, client fetch, and server cache. |
| Calling provider directly succeeds but calling by service ID fails | Registry has no instance or LoadBalancer is not configured. | Check DiscoveryClient first, then check LoadBalancer. |

### Note on defaultZone

In YAML, use:

~~~~yaml
eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
~~~~

defaultZone is a key in the URL map and is case-sensitive. If changed to default-zone, the client may fail to pick up the intended URL.

### Note When Running with Docker

Inside a container, localhost points to the container itself. If Eureka Server and clients run in different containers, do not use localhost:8761 for clients. Use the DNS/service name within the same Docker network, for example http://eureka-server:8761/eureka/.

At the same time, the address the provider registers with Eureka must be reachable from the consumer container. Publishing a port to the host does not automatically make the container address reachable in the way the consumer expects. Check eureka.instance.prefer-ip-address, hostname, network, and port mappings before concluding that LoadBalancer is broken.

## 15. Extension Exercises

### Exercise 1: Add a Third Instance

Start catalog-service on port 8083. Do not modify order-service. Verify:

- Eureka displays three instances.
- DiscoveryClient returns three elements.
- /orders/catalog/sequence?count=12 returns all three ports.

The goal is to observe that a provider can scale out without the consumer having to update its URL list.

### Exercise 2: Modify Metadata

Add metadata to catalog-service:

~~~~yaml
eureka:
  instance:
    metadata-map:
      zone: lab-a
      version: v1
~~~~

Observe the metadata via /orders/discovery/catalog. Try running another replica with zone: lab-b and compare the results. Metadata only affects routing when the consumer or LoadBalancer is configured to interpret those keys.

### Exercise 3: Test Health Status

Enable Eureka health check integration and trigger a condition that changes Actuator health status. Observe the status in Eureka and the instance list received by the consumer. Restore the condition and verify the instance returns to serving traffic.

### Exercise 4: Measure Convergence Delay

Record timestamps at the following points:

- Provider stops.
- Eureka receives deregistration or the lease expires.
- Eureka REST API no longer returns the instance.
- Consumer DiscoveryClient no longer returns the instance.
- The last LoadBalancer request goes to the stopped instance.

From this, distinguish cleanup time in the registry from cache update time on the consumer side.

## 16. Completion Checklist

- [ ] Created Maven multi-module project with three applications.
- [ ] Imported a Spring Cloud BOM compatible with Spring Boot.
- [ ] Eureka Server runs on port 8761 with client registration/fetch disabled in standalone mode.
- [ ] Two catalog instances share the same service ID but have different instance IDs.
- [ ] order-service successfully registers with Eureka.
- [ ] DiscoveryClient.getInstances("catalog-service") returns two instances.
- [ ] RestClient uses a @LoadBalanced builder and calls by service ID.
- [ ] Observed LoadBalancer selecting instances across sequential requests.
- [ ] Gracefully stopped one provider and verified registry/consumer updates.
- [ ] Distinguished graceful deregistration from crash/lease expiration.
- [ ] Tested querying the Eureka REST API and Actuator health.
- [ ] Checked hostname/port configuration when running across multiple machines or Docker.

## Key Takeaways

- Eureka Server stores the registry; Eureka Client registers itself and can query the registry.
- spring.application.name defines the service ID; eureka.instance.instance-id distinguishes each replica.
- defaultZone points to the Eureka Server and must remain camel case.
- DiscoveryClient returns the instance list; Spring Cloud LoadBalancer selects one instance for a request.
- @LoadBalanced RestClient.Builder enables calling via logical URLs such as http://catalog-service/catalog.
- Spring Cloud LoadBalancer defaults to round-robin.
- Eureka uses heartbeats, leases, caches, and self-preservation; registration changes do not necessarily appear immediately at every consumer.
- Graceful shutdown lets the client deregister; crashes rely on leases/eviction.
- The address advertised by the provider must be reachable from the consumer; pay special attention to localhost when using Docker.
- In production, you need multiple Eureka peers, registry security, heartbeat/renewal monitoring, and appropriate timeouts.

## Official References

- [Spring Cloud 2026.0.0 Release](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Cloud Release Train Reference](https://docs.spring.io/spring-cloud-release/reference/index.html)
- [Spring Cloud Netflix – Eureka Client and Server](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Commons – DiscoveryClient and ServiceRegistry](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Boot – Build Systems and Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
