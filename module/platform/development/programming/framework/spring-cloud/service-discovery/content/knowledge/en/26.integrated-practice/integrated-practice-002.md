# Running Multiple Instances and Proving the Caller Uses the Service Name

## 1. Practice Objectives

In microservices, the caller should look up a service by its service ID rather than hardcoding an instance's IP and port. When there are multiple replicas, the registry provides the list of instances; the client-side load balancer selects one instance from the list to send the request to.

This practice sets up a small environment using Spring Cloud Netflix Eureka:

- One **Eureka Server** running on port 8761.
- Two **inventory-service** processes both registered under the service ID inventory-service, running on ports 8081 and 8082 respectively.
- One **order-service** running on port 8080.
- order-service calls inventory-service using the logical URL http://inventory-service/api/instance.

Results to demonstrate:

1. Eureka displays two instances of the same service.
2. order-service's DiscoveryClient finds both addresses.
3. Requests from order-service use the service ID inventory-service, without containing a specific host/port.
4. Spring Cloud LoadBalancer distributes requests across the registered instances.
5. When one instance stops, subsequent requests can continue to be handled by the remaining instance after the registry state is updated.

## 2. Lab Architecture

~~~mermaid
flowchart TD
    E[Eureka Server :8761]
    I1[inventory-service instance A :8081]
    I2[inventory-service instance B :8082]
    O[order-service :8080]
    E <-->|register / heartbeat / fetch| I1
    E <-->|register / heartbeat / fetch| I2
    E <-->|registry fetch| O
    O -->|http://inventory-service/api/instance| LB[Spring Cloud LoadBalancer]
    LB --> I1
    LB --> I2
~~~

Eureka stores registration information and provides the instance list. order-service retrieves the list via discovery integration; LoadBalancer selects an instance for each request. The logical URL contains the service ID, while the physical address is selected at runtime.

## 3. Project Preparation

You can organize the three independent applications within the same workspace:

~~~text
service-discovery-lab/
  eureka-server/
    pom.xml
    src/main/java/...
    src/main/resources/application.yml
  inventory-service/
    pom.xml
    src/main/java/...
    src/main/resources/application.yml
  order-service/
    pom.xml
    src/main/java/...
    src/main/resources/application.yml
~~~

Each application has its own Spring Boot main class. Use the same Spring Cloud release train compatible with your project's Spring Boot version. Manage dependencies via the Spring Cloud BOM; do not mix Eureka, Commons, and LoadBalancer versions from different release trains.

### 3.1. Dependencies per Application

| Application | Key Dependencies |
|---|---|
| eureka-server | spring-boot-starter-web, spring-cloud-starter-netflix-eureka-server |
| inventory-service | spring-boot-starter-web, spring-cloud-starter-netflix-eureka-client |
| order-service | spring-boot-starter-web, spring-cloud-starter-netflix-eureka-client, spring-cloud-starter-loadbalancer |

Example Maven dependency management shared across all three applications:

~~~xml
<properties>
    <spring-cloud.version>YOUR_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
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
~~~

Replace YOUR_COMPATIBLE_RELEASE_TRAIN with the release train compatible with the Spring Boot version in use according to the official compatibility table. Application dependencies declare versions managed by the BOM.

Example dependencies section for Eureka Server:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-server</artifactId>
    </dependency>
</dependencies>
~~~

Inventory Client:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
~~~

Order Client:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
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
~~~

## 4. Creating Eureka Server

### 4.1. Main class

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

### 4.2. Configuring application.yml

~~~yaml
server:
  port: 8761

spring:
  application:
    name: eureka-server

eureka:
  client:
    register-with-eureka: false
    fetch-registry: false
~~~

The two properties register-with-eureka and fetch-registry are turned off because this lab uses this node as a standalone registry server, without registering it as a client service and without needing to fetch the registry from another peer.

You do not need to disable Eureka's self-preservation to complete the lab. This mechanism is part of protecting the registry when heartbeats drop abnormally; understand its impact before changing it in a real environment.

## 5. Creating inventory-service

Inventory service will return the identity of the specific instance receiving the request. Two processes run the same application and share the same service ID, but on different ports.

### 5.1. Main class

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

There is no need to create two codebases or rename the service for two replicas. Both processes use the same spring.application.name of inventory-service; the instance ID must be different so the registry can distinguish them.

### 5.2. Endpoint Returning the Current Instance

~~~java
package com.example.inventory.api;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InventoryController {

    @Value("${spring.application.name}")
    private String serviceName;

    @Value("${server.port}")
    private int port;

    @GetMapping("/api/instance")
    public String instance() {
        return serviceName + " | port=" + port;
    }
}
~~~

This endpoint returns the actual port of the instance receiving the request. This is visual proof of which replica LoadBalancer chose.

### 5.3. Configuring application.yml

~~~yaml
server:
  port: 8081

spring:
  application:
    name: inventory-service

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
    register-with-eureka: true
    fetch-registry: true
    registry-fetch-interval-seconds: 5
  instance:
    instance-id: ${spring.application.name}:${server.port}
    prefer-ip-address: true
~~~

The key point is that the instance ID is constructed from the service name and port. If two processes use the same instance ID, they may conflict or overwrite registration information depending on how the registry handles it. Two ports generate two distinct IDs:

- inventory-service:8081
- inventory-service:8082

registry-fetch-interval-seconds is set low for quick observation in the lab. You should not automatically use such a short interval for every production workload; fetching too frequently increases registry traffic.

## 6. Running Two Inventory Instances

Package the application:

~~~powershell
cd inventory-service
mvn -DskipTests package
~~~

Open two separate terminals in the inventory-service directory. Run the first instance:

~~~powershell
java -jar target/inventory-service.jar --server.port=8081
~~~

Run the second instance:

~~~powershell
java -jar target/inventory-service.jar --server.port=8082
~~~

If the actual JAR filename includes a version, use the exact filename in the target directory. You can also run via the Maven plugin instead of the JAR:

~~~powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--server.port=8081"
~~~

Open a second terminal and use port 8082 for the other process.

Each process must:

1. Open an HTTP server on its own port.
2. Connect to Eureka Server.
3. Register under the same service ID inventory-service.
4. Advertise its own instance ID.
5. Send heartbeats according to the Eureka Client configuration.

## 7. Verifying the Registry Has Two Instances

Open the Eureka Dashboard:

~~~text
http://localhost:8761
~~~

In the application list, look for INVENTORY-SERVICE. The expected result is two instances with addresses/ports corresponding to 8081 and 8082.

You can query the Eureka REST API:

~~~powershell
$headers = @{ Accept = "application/json" }
Invoke-RestMethod -Uri "http://localhost:8761/eureka/apps/INVENTORY-SERVICE" -Headers $headers
~~~

The JSON response may contain the application name and the list of instances. The field structure depends on the Eureka version; what needs to be verified is that there are two distinct instances and each instance has the appropriate host/port and status.

If the dashboard does not yet display both instances:

- Check the startup logs of both inventory processes.
- Confirm both use the correct defaultZone.
- Confirm the instance IDs are different.
- Check that ports 8081 and 8082 are not occupied by another process.
- Wait for the client/server to update the registry according to the fetch and heartbeat intervals.

Do not move on to the caller step before the registry displays both instances. This helps separate registration errors from LoadBalancer errors.

## 8. Creating order-service to Call by Service Name

This is the main proof. Order service does not know whether the inventory instance is on port 8081 or 8082. It only knows the service ID inventory-service.

### 8.1. Main class

~~~java
package com.example.order;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

### 8.2. Declaring a LoadBalanced RestTemplate

~~~java
package com.example.order.config;

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
~~~

The LoadBalanced annotation attaches Spring Cloud LoadBalancer's interceptor to RestTemplate. When the URL has a service ID as its host, LoadBalancer looks up the instance list and selects an actual endpoint.

If you omit this annotation, a plain RestTemplate will treat inventory-service as a DNS hostname. In the lab there is no such DNS record, so requests typically fail with UnknownHostException.

### 8.3. Calling the Service by Logical Name

~~~java
package com.example.order.api;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;

@RestController
public class OrderController {

    private final RestTemplate restTemplate;

    public OrderController(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    @GetMapping("/orders/check-inventory")
    public String checkInventory() {
        return restTemplate.getForObject(
                "http://inventory-service/api/instance",
                String.class);
    }
}
~~~

The target URL contains inventory-service instead of localhost:8081 or localhost:8082. This is code-level proof that the caller uses the service name. The concrete address is only chosen after LoadBalancer receives the instance list from discovery.

### 8.4. Configuring application.yml

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
    register-with-eureka: true
    fetch-registry: true
    registry-fetch-interval-seconds: 5

logging:
  level:
    org.springframework.cloud.loadbalancer: DEBUG
~~~

DEBUG logging is optional to help observe the instance selection process. In production, choose an appropriate log level to avoid excessive logging.

## 9. Running the Entire Lab in Order

From the root directory service-discovery-lab, package all three applications:

~~~powershell
cd eureka-server
mvn -DskipTests package
cd ..\inventory-service
mvn -DskipTests package
cd ..\order-service
mvn -DskipTests package
cd ..
~~~

The JAR filename depends on the artifactId, version, and build configuration in each POM. The java -jar commands below use illustrative names; replace them with the actual filenames in the target directory or configure a custom finalName for each application.

Open separate terminals and start:

| Order | Application | Port |
|---|---|---:|
| 1 | Eureka Server | 8761 |
| 2 | inventory-service instance A | 8081 |
| 3 | inventory-service instance B | 8082 |
| 4 | order-service | 8080 |

Start Eureka Server:

~~~powershell
cd eureka-server
java -jar target/eureka-server.jar
~~~

Wait for the server to be ready at http://localhost:8761.

Start the two inventory processes using the two commands in section 6. Then verify Eureka displays both instances.

Start order-service:

~~~powershell
cd order-service
java -jar target/order-service.jar
~~~

If using the Maven plugin, run:

~~~powershell
mvn spring-boot:run
~~~

## 10. Sending Multiple Requests and Observing LoadBalancer

Call the order-service endpoint multiple times:

~~~powershell
1..10 | ForEach-Object {
    Invoke-RestMethod -Uri "http://localhost:8080/orders/check-inventory"
}
~~~

Illustrative output:

~~~text
inventory-service | port=8081
inventory-service | port=8082
inventory-service | port=8081
inventory-service | port=8082
inventory-service | port=8081
...
~~~

With Spring Cloud LoadBalancer defaulting to RoundRobinLoadBalancer, sequential requests typically alternate between the instances currently in the list. The initial order is not fixed. Results may vary when there are retries, cache updates, instance state changes, or concurrent requests.

What needs to be proven is that multiple requests reached both port 8081 and port 8082 through the same order-service endpoint.

## 11. Proving Discovery Returns Two Instances

You can add a diagnostic endpoint to order-service to read the list from DiscoveryClient. This endpoint does not replace LoadBalancer requests; it simply shows the discovery data received by the caller.

~~~java
package com.example.order.api;

import java.util.List;
import java.util.stream.Collectors;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DiscoveryDiagnosticsController {

    private final DiscoveryClient discoveryClient;

    public DiscoveryDiagnosticsController(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @GetMapping("/orders/inventory-instances")
    public List<String> inventoryInstances() {
        return discoveryClient.getInstances("inventory-service")
                .stream()
                .map(ServiceInstance::getUri)
                .map(Object::toString)
                .collect(Collectors.toList());
    }
}
~~~

Call the endpoint:

~~~powershell
Invoke-RestMethod -Uri "http://localhost:8080/orders/inventory-instances"
~~~

The expected result has two URIs corresponding to ports 8081 and 8082. This endpoint uses the explicit service ID to query DiscoveryClient.

Do not expose an endpoint listing internal topology like this to a public production API without an operational purpose and proper access control.

## 12. Testing Stopping an Instance

To verify list changes:

1. Send several requests and confirm both 8081 and 8082 are being selected.
2. Stop the inventory-service process running on port 8081 using Ctrl+C.
3. Watch the Eureka Dashboard to see instance 8081 get deregistered or change status.
4. Wait for order-service to receive the updated list.
5. Call the check-inventory endpoint again multiple times.
6. Confirm new responses come from port 8082.

Eureka Client typically sends deregistration during normal shutdown. If the process is killed abruptly or the network is partitioned, the registry may only detect the lost instance after heartbeat/lease expiration and eviction. Self-preservation can delay eviction when the number of heartbeats drops abnormally.

Therefore, do not expect the instance to disappear in the exact same millisecond the process stops. Observe the status, deregistration timing, and client cache refresh.

After verifying, you can restart instance A:

~~~powershell
java -jar target/inventory-service.jar --server.port=8081
~~~

Wait for Eureka to show two instances again and repeat the requests.

## 13. Evidence to Collect

A practice session is considered complete when the following evidence is gathered:

| Evidence | How to Verify | Expected Result |
|---|---|---|
| Eureka Server running | Open dashboard on port 8761 | Dashboard is accessible |
| Two instances registered under the same service ID | Dashboard or REST API | INVENTORY-SERVICE has two instances |
| Different instance IDs | Dashboard/REST API | One ID for port 8081, one ID for port 8082 |
| DiscoveryClient sees two instances | Diagnostics endpoint | Two URIs in the list |
| Caller uses service name | Read OrderController | URL contains inventory-service, no fixed port |
| LoadBalancer selects multiple instances | Call endpoint repeatedly | Responses include both 8081 and 8082 |
| One instance stops | Stop port 8081 and observe | After update, new requests use port 8082 |

You can capture screenshots of the dashboard, output of the diagnostics endpoint, output of repeated calls, and the OrderController code snippet as evidence for your practice report.

## 14. Distinguishing Layers When Errors Occur

| Symptom | Layer to Check | How to Handle |
|---|---|---|
| Eureka Dashboard does not open | Eureka Server | Check process, port 8761, and startup logs |
| Inventory does not appear | Registration | Check defaultZone, client logs, service name, and network |
| Only one instance appears | Instance identity | Check port, instance-id, and process conflicts |
| DiscoveryClient returns an empty list | Registry fetch/cache | Check fetch-registry, last fetch time, and Eureka REST API |
| Caller reports No instances available | Discovery/LoadBalancer | Confirm registry has instances and caller has fetched |
| Caller reports UnknownHostException | HTTP client is not load-balanced | Check @LoadBalanced and starter-loadbalancer |
| Caller only calls one port | Registry list or policy/cache | Check instance list seen by caller, LoadBalancer logs, and cache |
| Stopped instance is still called by caller | Cache/eviction | Check graceful deregistration, lease, self-preservation, and fetch interval |
| Caller times out to an instance | Data plane | Check host/port advertised by Eureka, firewall, and instance listener |

## 15. Common Configuration Mistakes

### 15.1. Using a Physical Address in the Caller URL

Example that does not demonstrate service discovery:

~~~java
restTemplate.getForObject(
        "http://localhost:8081/api/instance",
        String.class);
~~~

This URL always calls port 8081 and bypasses the service ID. When the port or host changes, the caller must update its configuration.

### 15.2. Forgetting @LoadBalanced

A RestTemplate without the LoadBalancer interceptor treats inventory-service as a DNS hostname. Add the LoadBalancer dependency and annotate the exact bean injected into the controller with @LoadBalanced.

### 15.3. Two Replicas Sharing the Same Instance ID

If the instance ID is static, the registry may treat both processes as the same registration. Generate distinct IDs based on port, hostname, or a unique replica identifier.

### 15.4. Starting the Caller Too Early

If order-service fetches the registry before inventory registers, the initial list may be empty. Wait until the registry has two instances or wait for the next fetch and check again. In production, the caller must handle the case where a service has no instances yet at startup.

### 15.5. Eureka Advertising an Unreachable Address

In Docker or across multiple machines, prefer-ip-address only helps if the IP advertised by Eureka is reachable from the caller. Do not use localhost as the advertised address across containers because localhost inside each container points to that container itself. Use a hostname or IP on the network to which the caller has a route.

### 15.6. Expecting Immediate Removal of Stale Instances

Graceful shutdown can deregister quickly, but a crash or partition requires lease expiration/eviction. The client also has its own fetch interval and cache. Inspect each milestone in time rather than concluding discovery is broken just because one request right after shutdown still picks the old instance.

## 16. Extending the Practice

Once the basic lab runs successfully, you can extend it in the following directions:

- Add a third instance on port 8083 and verify LoadBalancer distributes across three replicas.
- Add zone metadata to instances and explore Spring Cloud LoadBalancer zone preference.
- Test an unready instance and observe how the provider/health check updates the registry.
- Stop Eureka Server while clients remain running to observe the registry cache and ability to continue serving requests.
- Try restarting order-service and verify the client re-fetches the registry.
- Add timeout, retry, and circuit breaker to business calls.
- Port the lab to Consul or Kubernetes Discovery to compare how the instance list is provided.

Change only one factor at a time and record before/after results. This helps distinguish the behavior of the registry, DiscoveryClient, LoadBalancer, and network.

## 17. Completion Checklist

- [ ] Eureka Server started and dashboard is accessible.
- [ ] Two inventory processes running on ports 8081 and 8082.
- [ ] Both registered under the service ID inventory-service.
- [ ] Both instances have different instance IDs.
- [ ] Eureka displays both instances.
- [ ] order-service started and fetched the registry.
- [ ] RestTemplate bean is annotated with @LoadBalanced.
- [ ] Caller invokes URL http://inventory-service/api/instance.
- [ ] Multiple requests return both port 8081 and 8082.
- [ ] Discovery diagnostics return two URIs.
- [ ] After stopping one instance and registry/cache updating, new requests use the remaining instance.
- [ ] Recorded dashboard, outputs, and code as evidence.

## 18. Summary

This practice uses Eureka as the registry, runs two inventory-service processes with the same service ID but different instance IDs, and has order-service call via the logical URL http://inventory-service/api/instance. The @LoadBalanced annotation enables RestTemplate to resolve the service ID to a concrete instance through Spring Cloud LoadBalancer and DiscoveryClient.

When both instances appear in Eureka and requests from order-service reach both ports, you have proven that the caller depends on the service name rather than fixed addresses. When stopping an instance, observe deregistration, heartbeat/eviction, and client cache before confirming that LoadBalancer only selects the remaining instance.

## 19. References

- [Spring Cloud Netflix — Eureka Client and Server](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Commons — LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Commons — DiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud — Release Train and Spring Boot Compatibility](https://spring.io/projects/spring-cloud)

Choose a release train compatible with Spring Boot and check APIs/configuration properties according to your project's exact version.
